---
phase: 45-post-auth-restore-subscription
reviewed: 2026-09-08T02:38:38Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - tests/e2e/conftest.py
  - tests/e2e/test_restore_subscription.py
  - tests/schema/test_restore_race.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_subscription_attribution.py
findings:
  critical: 3
  warning: 7
  info: 4
  total: 14
status: issues_found
---

# Phase 45: Code Review Report

**Reviewed:** 2026-09-08T02:38:38Z
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

`POST /auth/restore-subscription` was reviewed end to end: the two store proof checks, the
service's four branches (same-account replay, adoption, adoption-with-creation, capped move),
the crud writers they call, the error tree, the route, and the three test suites.

The claims the phase makes about itself hold up under inspection:

- Store verification does run before the first statement (`restore.py:49` precedes every read),
  so no network call happens under a lock.
- The two `RestoreRefused` leaves share one status, one code and one body, and the e2e suite
  compares the two bodies byte for byte rather than each to a literal.
- `write_subscription_grant`'s account conjunct (`crud/subscriptions.py:245`) does fix the
  dropped destination grant on a move.
- The deferred-constraint case lives in `tests/schema/test_restore_race.py:445`, not in the e2e
  suite. No e2e assertion about a deferred constraint exists. Nothing to flag there.

Three defects nevertheless ship. One is a security hole: the Google purchase token is
client-supplied and is interpolated into the Play API URL path with no percent-encoding, so a
caller can redirect the deployment's OAuth-signed GET to a different `androidpublisher` endpoint.
The other two are correctness: the entitled decision is taken from the stored row while the grant
term is taken from the proof, which mints a never-expiring paid grant in one reachable
combination; and the cross-account move supersedes *every* grant of both accounts, which can
silently strip the source account of an active grant for an unrelated subscription it still pays
for.

No structural pre-pass was supplied with this review, so this report carries narrative findings
only.

## Narrative Findings (AI reviewer)

### Critical Issues

#### CR-01: Client-supplied purchase token is path-injected into the Play API URL

**File:** `src/nativespeaker/api/auth/google_play.py:34-35,296-304` (reached from
`src/nativespeaker/api/services/restore.py:172-174`)

**Issue:** `restore_proof` arrives straight from the request body
(`schemas/auth.py:42` — a plain `str` with no pattern and no maximum), is passed unmodified as
`purchase_token` to `read_for_restore`, and lands in `PLAY_URL.format(...)`. `str.format` does no
percent-encoding, so every structural URL character the caller sends is honoured. Verified against
the installed httpx:

```
'a/../../../../v3/applications/evil/edits'
  -> https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.ns.app/v3/applications/evil/edits
'../../../../../../etc'
  -> https://androidpublisher.googleapis.com/androidpublisher/etc
'x?alt=media'
  -> .../tokens/x?alt=media
```

httpx's dot-segment normalisation collapses the traversal, so an authenticated caller chooses
the path (and the query string) of a GET that carries this deployment's `androidpublisher`-scoped
bearer token. The `package_name` guard the comment at `google_play.py:261-262` relies on ("a token
of another application answers 404") is defeated by the same input, because the caller can escape
the `applications/{package_name}` segment entirely. This is not the low-value-product threat
model — it is the service's own Google credential being pointed at attacker-chosen endpoints.

The same `_get` is used by the webhook `read()`, where the token comes from a Google-signed RTDN;
fixing it in `_get` covers both callers.

**Fix:**

```python
from urllib.parse import quote

async def _get(self, package_name: str, purchase_token: str) -> httpx.Response:
    """Send one signed read; each entry point classifies a transport failure its own way."""
    if not self._credential.valid:
        await run_in_threadpool(self._credential.refresh,
                                google.auth.transport.requests.Request())
    return await self._client.get(
        # Every path segment is escaped: a caller-supplied token names one segment and never a path.
        PLAY_URL.format(package_name=quote(package_name, safe=""),
                        purchase_token=quote(purchase_token, safe="")),
        headers={"Authorization": f"Bearer {self._credential.token}"})
```

Add a unit case in `tests/unit/test_restore_proof.py` asserting that a token containing `../` and
`?` produces a request URL whose path is still
`/androidpublisher/v3/applications/{package}/purchases/subscriptionsv2/tokens/...` and whose query
is empty.

---

#### CR-02: The entitled decision comes from the stored row, the term comes from the proof — the pair can mint a grant that never ends

**File:** `src/nativespeaker/api/services/restore.py:58,133-139`

**Issue:** Line 58 takes `status` from `stored.status` when a canonical row exists (D-06), but
lines 134-138 take `starts_at`/`ends_at` from `proof`. The two sources are never reconciled, and
`write_subscription_grant` writes whatever it is handed. `core.access_grants` has
`CHECK (ends_at IS NULL OR ends_at > starts_at)` and nothing more, and
`_effective_grants_statement` (`crud/grants.py:32-33`) treats `ends_at IS NULL` as effective
forever. Two reachable combinations:

1. **Never-expiring paid grant.** `stored.status is grace_period` (a webhook set it) and the
   caller presents an Apple proof. `AppStoreNotifications.verify_transaction` hardcodes
   `grace_period_expires_at=None` (`app_store.py:146-147`), so line 137-138 selects `None` and the
   grant is inserted with `ends_at = NULL`. The account holds the `paid` tier (1000
   credits/month) indefinitely, with no store event able to end it except a later notification for
   the same subscription. The Google path reaches the same state whenever the stored row says
   `grace_period` but the live read reports another state, because `read_for_restore` sets
   `grace_period_expires_at` only when `subscriptionState == GRACE_STATE`
   (`google_play.py:270,284`). `expires_at` is likewise `datetime | None` on both paths, so a
   proof carrying no expiry does the same for `status is active`.

2. **Bricked grant slot.** Apple's `originalTransactionId` is stable across renewals, so a client
   may present a *stale* signed transaction. `stored.status` is `active`, so the restore proceeds,
   but `proof.expires_at` is in the past. The grant is inserted `status='active'` with a past
   `ends_at`: it satisfies the CHECK, occupies the one slot
   `ix_access_grants_one_active_per_user` allows, and is effective for nothing. If the account
   held a free grant, `superseded` expired it first, and
   `ix_access_grants_one_free_grant_per_user_source` has no status predicate — that free grant is
   gone for the account's lifetime. A repeat restore answers `replayed` (`ends_at` matches), so the
   account cannot self-heal.

Neither combination is covered: `tests/unit/test_restore_proof.py:134` proves grace is unreachable
*from a proof*, and the only e2e grace case (`test_restore_subscription.py:290-297`) goes down the
adoption-with-creation branch where `status` comes from the proof, so the mismatch never arises.

**Fix:** refuse before any write when the term the proof carries does not support the status the
stored row claims. In `RestoreService.restore`, after line 60:

```python
        # The term is the proof's and the status is the row's, so the pair is checked before it is written.
        term_ends_at = (proof.grace_period_expires_at
                        if status is SubscriptionStatus.grace_period else proof.expires_at)
        if term_ends_at is None or term_ends_at <= self.evaluated_at:
            # A proof carrying no open term entitles nothing, whatever the canonical row still says.
            raise RestoreSubscriptionNotEntitled
```

and pass `ends_at=term_ends_at` at line 137. It joins the existing `restore_not_found` family, so
the refusal body stays byte-identical to the other two arms and adds no oracle.

---

#### CR-03: A cross-account move supersedes every grant of the source account, including one for an unrelated subscription

**File:** `src/nativespeaker/api/crud/subscriptions.py:240-259` (line 252)

**Issue:** On a move, `marked_active` holds the active grants of *both* accounts
(`restore.py:94-95`). `held` correctly narrows to the destination's own rows for this subscription
(line 245), but line 252 then discards that narrowing:

```python
superseded = list(marked_active) if entitled else held
```

Every row of both accounts is expired. For the destination that is right (one active grant per
user). For the source it is right only if the source's active grant *is* the grant for this
subscription. It need not be:

- `O` restores `S1` → `O` owns `S1`, active grant `G1(S1)`.
- `O` restores `S2` → `G1` is superseded, `O` now holds `G2(S2)`. `O` still owns `S1`, whose row
  still says `active`.
- `D` restores `S1` with an unattributed proof → `current_owner = O`, `marked_active = [G2, ...]`,
  `held = []`, and line 252 expires `G2`.

`O` is left with zero active grants while still owning — and paying for — the active subscription
`S2`. The write commits silently: an expired grant's generated columns go NULL, so neither
deferred foreign key fires, and `ix_access_grants_one_per_subscription` is satisfied. Nothing in
`tests/schema/test_restore_race.py` or `tests/e2e/test_restore_subscription.py` gives the source
account a second subscription, so the case is untested.

**Fix:**

```python
        # Every held grant goes, the free one included: `ix_access_grants_one_active_per_user` allows one.
        # On a move that is the destination's whole set plus the old owner's row for *this*
        # subscription; the old owner's grant for any other subscription is not this write's to end.
        superseded = ([grant for grant in marked_active
                       if grant.user_id == user_id or grant.subscription_id == subscription_id]
                      if entitled else held)
```

Add a schema case: seed the source account with an active grant for a second subscription, run the
move, and assert that grant is untouched and still active.

---

### Warnings

#### WR-01: `restore_bound_user_id` is designed and provisioned but never written; two migration comments now state the opposite of what the code does

**File:** `migrations/20260818_01_initial-release.sql:136-139`,
`src/nativespeaker/api/tables/purchases.py:61`,
`src/nativespeaker/api/services/restore.py` (whole file)

**Issue:** The schema declares `restore_bound_user_id` as the "Lifetime restore binding: NULL
until the first successful restore, then never changed." No code writes it — `grep` finds it only
in the table model and in assertions that it stays `None`
(`tests/e2e/test_restore_subscription.py:617,661,687,708,724`;
`tests/schema/test_restore_race.py:243`). The designed lifetime binding — the control that stops
one leaked store artifact from walking a subscription between accounts month after month — is
absent, and D-10's monthly cap is the only thing left. In the same block,
`last_cross_account_transfer_month` still carries the comment "Written by nothing: cross-account
restore transfer is never performed, so this stays NULL", which this phase falsified. A reader of
the schema is now actively misled about both columns.

**Fix:** either implement the binding (set it inside `claim_subscription_owner` on the first
successful restore, and refuse in `RestoreService.restore` when it is set and is not the
destination), or drop the column in a follow-up migration. Either way, correct both comments in
the same change — `last_cross_account_transfer_month` should read "Written by the capped
cross-account move only (D-10); one move per subscription per UTC month."

---

#### WR-02: Caller-controlled `provider` and `restore_proof` have no length bound, and the route logs `provider` claiming it is bounded

**File:** `src/nativespeaker/api/schemas/auth.py:41-42`,
`src/nativespeaker/api/routers/auth.py:166-169`

**Issue:** `RestoreRequest` declares `min_length=1` and no `max_length` on either field. The route
then does:

```python
logger.warning("restore_provider_not_served", provider=body.provider)
# The rejected string is caller-supplied and bounded, so logging it is safe; a proof never is.
```

The comment's premise is false: nothing bounds `body.provider`. An authenticated caller can put a
multi-megabyte string — or newlines and structured-log-shaped text — into the log pipeline on
every refused request. `restore_proof` is likewise unbounded and is handed to Apple's JWS decoder
or into an outbound URL. Envoy rate-limits requests, not payload size per field.

**Fix:**

```python
class RestoreRequest(BaseModel):
    """The restore body: the store the artifact came from, and the artifact itself."""
    # Bounded here, so the handler's refusal log really is the bounded value its comment claims.
    provider: str = Field(..., min_length=1, max_length=32)
    # A signed transaction and a purchase token are both far below this; nothing legitimate exceeds it.
    restore_proof: str = Field(..., min_length=1, max_length=8192)
```

---

#### WR-03: `ingest` locks grants for an owner read before the transaction, but grants to the owner `upsert_subscription` re-reads

**File:** `src/nativespeaker/api/services/subscriptions.py:43-52,120-121`,
`src/nativespeaker/api/crud/subscriptions.py:117,131`

**Issue:** `owner` (line 48) comes from the read at line 43, and `marked_active` is locked for that
account (line 52). `upsert_subscription` then performs its *own* `read_subscription` (line 117)
and recomputes the owner from what it sees. Under READ COMMITTED the two reads can differ: a
concurrent restore that adopts the subscription commits between them. When it does,
`subscription.user_id` is the restore's destination while `marked_active` holds a different
account's grants. `write_subscription_grant` is then called with `user_id` = the new owner and
`marked_active` = someone else's rows, and (per CR-03) supersedes them — expiring an unrelated
account's active grant, then failing the unique index for the real owner and answering 500.

Restore is what made this reachable: before this phase nothing but the webhook wrote
`subscriptions.user_id`, so the two reads could not disagree on the owner.

**Fix:** have `upsert_subscription` return the owner it actually resolved, and refuse the delivery
rather than write across accounts:

```python
        subscription, outcome = await self.subscriptions_db.upsert_subscription(...)
        await self._settle(outcome, notification)
        if subscription.user_id != owner:
            # The owner moved between the pre-lock read and this write: the locks held are the wrong ones.
            await self.session.rollback()
            logger.warning("store_notification_owner_moved_under_read")
            raise InternalError
```

CR-03's narrowed `superseded` removes the silent-corruption half of this on its own; this guard
removes the rest.

---

#### WR-04: A restore writes no `audit.subscription_events` row, so a cross-account move leaves no audit trail

**File:** `src/nativespeaker/api/services/restore.py:46-143`

**Issue:** `SubscriptionsService.ingest` appends an event for every notification it applies
(`services/subscriptions.py:112-118`), including the superseded-payload arm. `RestoreService`
appends none. The one operation in the system that moves paid entitlement from one account to
another therefore records nothing in `audit.subscription_events` — the only durable evidence is
`core.subscriptions.updated_at` and `last_cross_account_transfer_month`, both of which the next
webhook overwrites or leaves ambiguous. There is no way after the fact to answer "which account
did this subscription come from, and when".

**Fix:** append one event per applied restore, after the owner claim and before the grant write.
`notification_uuid` is UNIQUE and shared with the store keys, so give restore its own prefixed
key, e.g. `f"restore:{subscription_id}:{self.evaluated_at.isoformat()}"`, with
`event_type="restore_move"` / `"restore_adopt"` and `old_tier_id == new_tier_id == tier_id`.

---

#### WR-05: A restore adopting a subscription leaves `store_purchases.purchase_user_id` NULL

**File:** `src/nativespeaker/api/services/restore.py:113-124` (line 122)

**Issue:** `purchase_user_id=attributed` — the account the *token* resolved to, which on the whole
adoption branch is `None` (the branch runs precisely when no token bound the purchase). The
destination account is known at that point and is written to `core.subscriptions.user_id` a few
lines earlier, so the purchase row ends up disagreeing with the subscription row about who owns
the purchase, and `ix_store_purchases_purchase_user_id` cannot find it. `purchase_user_id` carries
a plain single-column FK to `core.users` — the two composite FKs are on `(provider, external_id)`
and `(provider, resolved_token_value)` — so writing the destination is legal. The comment on line
123 correctly explains why `resolved_token_value` must stay NULL, but that reason does not extend
to `purchase_user_id`.

**Fix:**

```python
                # The account this restore attached it to: the row is written once, so it is written right.
                purchase_user_id=destination,
                # Set only when the token resolved: the second foreign key needs a binding to point at.
                resolved_token_value=None if attributed is None else token,
```

---

#### WR-06: Two devices of one account restoring at once answer 500 to a correct request

**File:** `src/nativespeaker/api/services/restore.py:89,113,140,178-187`

**Issue:** `_settle` is copied from the webhook service, where the caller is a store that retries
on its own schedule and where "a lost race is a 5xx whose retry then finds the rows" is a
reasonable contract. On `/auth/restore-subscription` the caller is the app. The realistic race —
the same user tapping Restore on two devices, or a client retry crossing the original — takes the
adoption-with-creation branch on both connections, one loses the unique index in
`upsert_subscription`, and that user is shown `internal_error`. `_answer_as_the_winner_left_it`
already implements the right behaviour for the owner-claim race; the writer races are not routed
through it.

**Fix:** on the restore path, treat `WriteOutcome.lost_race` the way the owner-claim loser is
treated — roll back, re-read, and answer as the winner's committed state earns:

```python
    async def _settle(self, outcome: WriteOutcome, proof: RestoredSubscription,
                      destination: UUID) -> None:
        if outcome is not WriteOutcome.lost_race:
            return
        logger.warning("restore_grant_race_lost", provider=str(proof.provider))
        # The client is a phone, not a retrying store: answer as the winner left it, as D-08 does.
        return await self._answer_as_the_winner_left_it(proof, destination)
```

---

#### WR-07: The loser of an adoption race is refused 404, but its immediate retry is a move that spends the D-10 cap

**File:** `src/nativespeaker/api/services/restore.py:150-161`

**Issue:** When two accounts adopt one unowned subscription, the loser reaches
`_answer_as_the_winner_left_it`, finds the row owned by the winner, and raises
`RestoreSubscriptionNotEntitled` — asserted at `tests/schema/test_restore_race.py:340-345`. But
the state that produced the 404 is exactly the state a *move* is defined over: the loser's next
attempt (same second, same proof) takes the `current_owner is not None` branch, succeeds, and
consumes that subscription's one move for the whole UTC month. So a lost race silently converts a
would-be adoption into a cap-spending transfer, and the client sees 404-then-200 for two identical
requests. The 404 also tells the loser nothing actionable.

**Fix:** decide the intended semantics and make them explicit. Either treat the loser as a move
attempt in the same request (re-run the branch decision once against the re-read row, so the cap
is spent knowingly), or refuse the retry as well by recording that this subscription was just
adopted. Whichever is chosen, add a schema case that runs the loser's retry and asserts what the
transfer month reads afterwards — no test currently exercises it.

---

### Info

#### IN-01: The Play read decides status against a second clock

**File:** `src/nativespeaker/api/auth/google_play.py:280-281` vs
`src/nativespeaker/api/services/restore.py:43-44`

**Issue:** `RestoreService` captures one instant and its comment states "nothing below it reads
the clock again", but `read_for_restore` calls `self._evaluated_at_source()` to classify
`SUBSCRIPTION_STATE_CANCELED`. Two instants decide one request. The skew is milliseconds and no
current case turns on it, but the invariant the service documents is not actually held.

**Fix:** pass the captured instant down — `read_for_restore(..., evaluated_at=self.evaluated_at)`
— and keep `_evaluated_at_source` for the webhook path, which has no request instant to inherit.

---

#### IN-02: `restore()` returns the value of a `-> None` coroutine

**File:** `src/nativespeaker/api/services/restore.py:109`

**Issue:** `return await self._answer_as_the_winner_left_it(proof, destination)` reads as though
the helper produces the method's result; it is declared `-> None` and produces nothing. The intent
is "stop here".

**Fix:**

```python
            if not claimed:
                await self._answer_as_the_winner_left_it(proof, destination)
                return
```

---

#### IN-03: `identity.user.id` is dereferenced without a guard

**File:** `src/nativespeaker/api/services/restore.py:50`

**Issue:** `Identity.user` is `User | None` (`schemas/auth.py:99`). The route guarantees it is set
via `get_linked_identity`, but the service accepts the whole `Identity` and states no
precondition, so the guarantee lives one module away from the dereference. `tests/schema` already
constructs `Identity` by hand (`test_restore_race.py:216`), which is exactly the caller that could
get it wrong.

**Fix:** take `destination: UUID` as a parameter instead of `identity`, so the type states the
requirement. The service uses nothing else from `Identity`.

---

#### IN-04: The flush/`23505` block is duplicated eight times, and the Play value-type assembly twice

**File:** `src/nativespeaker/api/crud/subscriptions.py:146-153,193-200,219-226,262-270,292-300`;
`src/nativespeaker/api/crud/grants.py:187-194,246-252,274-281`;
`src/nativespeaker/api/auth/google_play.py:219-243` vs `267-285`

**Issue:** The same nine lines — `try: await self.session.flush()` / `except IntegrityError` /
`if violation.orig.sqlstate != "23505": raise` / `return ...lost_race` — appear eight times with
identical comments. `read()` and `read_for_restore()` likewise repeat the whole
`_product_of` → `in_grace` → `identifiers` → value-type assembly. Eight copies of a rule mean
eight places to fix when the rule changes; `tests/schema/test_restore_race.py:469-471` already
notes that a `23503` at commit is a code this guard does not cover, which is exactly the kind of
change that would have to be made eight times.

**Fix:** extract one helper in each module, e.g.

```python
async def _flush_or_lost_race(session: AsyncSession) -> bool:
    """Flush, answering False where a unique index says a concurrent writer won."""
    try:
        await session.flush()
    except IntegrityError as violation:
        # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
        if violation.orig.sqlstate != "23505":
            raise
        return False
    return True
```

---

_Reviewed: 2026-09-08T02:38:38Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
