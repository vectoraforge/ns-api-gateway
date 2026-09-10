---
phase: 45-post-auth-restore-subscription
reviewed: 2026-09-10T02:00:00Z
depth: standard
diff_base: f4c006c51aac81a3cb9e9879f5fb44730a3050a4
files_reviewed: 141
files_reviewed_list:
  - .dockerignore
  - .env.example
  - .gitignore
  - AGENTS.md
  - Dockerfile
  - config/config.yaml
  - docker-compose.yml
  - k8s/Chart.yaml
  - k8s/templates/NOTES.txt
  - k8s/templates/deployment.yaml
  - k8s/templates/httproute-app.yaml
  - k8s/templates/httproute-auth.yaml
  - k8s/templates/httproute-health.yaml
  - k8s/templates/httproute-webhooks.yaml
  - k8s/templates/security-policy.yaml
  - k8s/values.yaml
  - migrations/20260818_01_initial-release.sql
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/error_handlers.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/devicecheck.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/chats.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/crud/violations.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/logs.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/schemas/api.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/schemas/llm.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/llm.py
  - src/nativespeaker/api/services/quota.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/services/sync.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/auth.py
  - src/nativespeaker/api/tables/chats.py
  - src/nativespeaker/api/tables/grants.py
  - src/nativespeaker/api/tables/identities.py
  - src/nativespeaker/api/tables/purchases.py
  - tests/e2e/conftest.py
  - tests/e2e/refusal_sites.py
  - tests/e2e/test_app_store_webhook.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/e2e/test_create_user.py
  - tests/e2e/test_google_play_webhook.py
  - tests/e2e/test_llm_schema.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/e2e/test_sign_out_all.py
  - tests/e2e/test_sync.py
  - tests/e2e/test_users_me.py
  - tests/schema/conftest.py
  - tests/schema/test_apply_rollback.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_constraints.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_harness_guards.py
  - tests/schema/test_inventory.py
  - tests/schema/test_registration_pairing.py
  - tests/schema/test_restore_race.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/schema/test_sync_lock_freedom.py
  - tests/unit/conftest.py
  - tests/unit/error_tree.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_chats_crud.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_config.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_conversion_carries_usage.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_identities_crud.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_identity_flip.py
  - tests/unit/test_jwks_offload.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_logging.py
  - tests/unit/test_models.py
  - tests/unit/test_monthly_period.py
  - tests/unit/test_purchases_crud.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_services.py
  - tests/unit/test_spent_free_grant_refusal.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_subscription_grant_write.py
  - tests/unit/test_subscription_store_clock.py
  - tests/unit/test_sync_clock_capture.py
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_tables_metadata.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users.py
  - tests/unit/test_users_me.py
  - uv.lock
findings:
  critical: 1
  warning: 13
  info: 39
  total: 53
status: issues_found
---

# Phase 45: Code Review Report (re-review)

**Reviewed:** 2026-09-10  
**Depth:** standard  
**Files Reviewed:** 141  
**Diff base:** `f4c006c51aac81a3cb9e9879f5fb44730a3050a4` (the phase's previous REVIEW.md commit)  
**Status:** issues_found

Incremental re-review of everything that changed since the phase's last review commit. The identical scope was split by module across six parallel `gsd-code-reviewer` agents with disjoint finding-id blocks (R1 01-19, R2 20-34, R3 35-49, R4 50-64, R5 65-79, R6 80-94), then merged here. Every reviewer ran the ratified-overrides gate against `.planning/REQUIREMENTS.md`, `.planning/STATE.md` and the phase decision records before filing; the candidates that gate removed are recorded verbatim at the end of this report.

| Reviewer | Module | Critical | Warning | Info |
| --- | --- | --- | --- | --- |
| R1 | services + routers | 1 | 1 | 5 |
| R2 | crud + tables + migration SQL | 0 | 2 | 7 |
| R3 | auth adapters + schemas | 0 | 2 | 6 |
| R4 | app wiring + cross-cutting + deployment/config | 0 | 2 | 8 |
| R5 | unit test suite | 0 | 3 | 5 |
| R6 | e2e + schema test suites | 0 | 3 | 8 |
| **Total** | **141 files** | **1** | **13** | **39** |

## Deferred item verdicts

### R1 — services + routers

### 1. Phase 37 WR-02 — "an Apple subscription in `grace_period` can never be restored"

**Verdict: the claim is FALSIFIED against current code as stated. No finding is filed for it. One
narrow sub-case survives, and it is the correct fail-closed answer. A different, adjacent defect
does survive and is filed as CR-01.**

Settled empirically, not from prose — three throwaway e2e probes were driven through the real
router, `RestoreService`, `SubscriptionsDB` and PostgreSQL, each deleted in the same tool call.

*Case (a) — an Apple subscription that HAS a `core.subscriptions` row whose status is
`grace_period`.* Split in two by whether a grant records the window:

- **A grant records it → restore succeeds.** Probe: seed the row, restore once so the route writes
  the grant, flip `core.subscriptions.status` to `grace_period`, present a bare Apple proof
  (`grace_period_expires_at=None` by construction, `auth/app_store.py:170-171`). Result: **200**,
  `entitlement.type=subscription`, `tier_id=paid`, the grant kept its own open `ends_at`. This is
  exactly what CR-25 (`559deaa`) bought: `restore.py:101-108` reads the term from
  `marked_active`, so `term_end_for(grace_period, proof)` — which would be `None` — is never asked.
  The 37 WR-02 failure mode is gone.
- **No grant records it → restore refuses `404 restore_not_found`, `cause=term_closed`.**
  Reachable when the row is unowned (an unattributed webhook wrote no grant) or the grant was
  already superseded. Pinned by `tests/e2e/test_restore_subscription.py:359-381`. This is correct:
  the only alternative is a grant carrying `ends_at = NULL`, i.e. paid access no store event can
  ever end. Fail-closed, and covered by SHARED-INVARIANTS § Fail-closed defaults. **No finding.**

*Case (b) — adoption where no local row exists and the StoreKit 2 signed transaction carries no
grace signal.* Unreachable by construction, so there is nothing to refuse.
`_transaction_status` (`auth/app_store.py:52-60`) returns only `revoked`, `active` or `expired` —
`grace_period` cannot come out of a bare transaction — and `verify_transaction` hard-sets
`grace_period_expires_at=None` (`:170-171`). An adopted row is therefore created at `active` or
refused at the `ENTITLED_STATUSES` test; a "grace adoption" does not exist. D-04 ratifies the
underlying blind spot (no `Get All Subscription Statuses` call). **No finding.**

*What does survive.* The CR-25 remedy tests the recorded term only for `None`, never for whether it
is still open, and `lock_grants_of` deliberately carries lapsed-but-marked-active rows. That is
CR-01 above, proven on both arms. It is the same class of harm 37 WR-02 named — a paying customer
refused — reached by a different route, and it is the one thing from this deferred item that a
fixer should act on.

### 2. Phase 37.2 critical — anonymous restore permanently setting `restore_bound_user_id`

**Verdict: fully settled by D-03 + D-10. No real gap remains. No finding.**

`grep -rn "restore_bound_user_id" src/` over the whole tree returns exactly **one** hit:

```
src/nativespeaker/api/tables/purchases.py:61:    restore_bound_user_id: UUID | None = Field(default=None, foreign_key="core.users.id")
```

the column declaration itself. There is no write path anywhere in `src/` — not in
`services/restore.py`, not in `crud/subscriptions.py`'s `claim_subscription_owner`, not in the
ingestion path. The other hits are the migration (`migrations/20260818_01_initial-release.sql:144`),
the schema inventory, and five e2e assertions that the column is still `NULL` after adoption, after
a move and after a repeat (`tests/e2e/test_restore_subscription.py:933,977,1003,1024,1040`). D-10's
"`restore_bound_user_id` is not written and stays NULL" is true of the code, so the
*permanence* half of the 37.2 critical has no mechanism left.

The *unreachability* half also does not survive. The tie is `core.subscriptions.user_id`, which
`claim_subscription_owner` can move again. Whether a user who restored onto an anonymous account
and then signed out can recover turns on `last_cross_account_transfer_month`, and
`restore.py:136-137` writes it **only** on a move (`transfer_month=None if current_owner is None
else self._this_month()`). Adoption — the ordinary anonymous case, since the account had no
subscription before — writes nothing, so the recovery restore onto a new account is the
subscription's *first* move and succeeds in the same calendar month.

The one residual is D-10's cap acting as designed: if the anonymous account acquired the
subscription by a *move* rather than by adoption, the month is spent and a second move is refused
`restore_transfer_rejected` until the first of the next UTC month, with the owning account
unreachable. D-03 ratifies precisely this trade — *"with D-10's cap, one receipt serves at most two
accounts in a month, an accepted loss on a sub-$5 subscription"* — so it is a ratified product
choice, not a defect. **No finding.**

## Critical Issues

### CR-01: A subscription grant still *marked* active but past its term makes restore refuse a genuinely current proof

_Reported by reviewer R1 (services + routers)._

**File:** `src/nativespeaker/api/services/restore.py:101-111`

**Issue.** After CR-25 the term comes from the grant the subscription's own webhook wrote:

```python
# At most one row answers: an entitled write supersedes this subscription's active grants first.
recorded_term = [grant.ends_at for grant in marked_active
                 if stored is not None
                 and grant.source is AccessGrantSource.subscription
                 and grant.subscription_id == stored.id]
term_ends_at = recorded_term[0] if recorded_term else term_end_for(status, proof)
if term_ends_at is None or term_ends_at <= self.evaluated_at:
    raise RestoreSubscriptionNotEntitled(cause="term_closed")
```

`marked_active` is `SubscriptionsDB.lock_grants_of`, which is
`GrantsDB.lock_active_grants_of` → `_active_grants_of_statement`
(`src/nativespeaker/api/crud/grants.py:47-54`). That statement selects on
`status == 'active'` and **no time window** — its own docstring says "whatever its term". So a
grant whose `ends_at` is already in the past is still in `marked_active`, `recorded_term[0]` is
that closed term, and the `elif` to the proof at line 108 is never reached. The restore is refused
`404 restore_not_found`.

That state is ordinary, not exotic: between a paid term ending and the store's renewal or expiry
notification arriving, the grant row keeps `status='active'` with a past `ends_at` — nothing sweeps
it, and the ingestion path is the only thing that flips it
(`services/subscriptions.py:159-171` → `crud/subscriptions.py:371-379`). During exactly that
window the subscriber also has **no** entitlement, because `/auth/sync` reads
`read_effective_grants`, which does filter on `ends_at > evaluated_at`
(`crud/grants.py:26-38`). So the customer has lost access and the recovery route refuses them.

**Proven empirically.** Two throwaway e2e cases were driven through the real router, service and
PostgreSQL, then deleted in the same tool call (tree left clean). Both seed one account, restore
once so the grant is one the route itself wrote, then age the grant's `ends_at` five minutes into
the past and present a fresh proof carrying a term one month out:

| grant row after ageing | answer |
|---|---|
| `status='active'`, `ends_at` 5 min past | `404 {"code":"restore_not_found"}`, log `restore_subscription_not_entitled cause=term_closed` |
| `status='expired'`, `ends_at` 5 min past | `200`, entitlement `subscription/active/paid` restored |

The only difference between the two rows is which enum label the *webhook* has got round to
writing. The customer, the proof and the canonical row are identical.

This is a residual of the CR-25 fix, not a ratified behaviour. The 37.5 fix report states the
prohibition the fix was written under — *"a refusal must not be so broad that it strands a paying
customer who presents a genuinely current proof"*
(`.planning/phases/37.5-machine-generated-code-refactoring-part-4/37.5-REVIEW-FIX.md:531-534`) —
and that prohibition is violated here. D-06 binds the **status** to the canonical row; it says
nothing that requires a *closed* recorded window to outrank an open one the store has just signed.

**Fix.** Prefer the first term that is actually open at the captured instant, keeping the recorded
grant ahead of the proof whenever it is open — that leaves every currently-passing case unchanged
(the stale-proof-against-a-live-grant case still answers `replayed`, and the grace row with no
grant still refuses, because an Apple proof carries no grace window):

```python
recorded_term = [grant.ends_at for grant in marked_active
                 if grant.source is AccessGrantSource.subscription
                 and stored is not None and grant.subscription_id == stored.id]
# The recorded window first, because the webhook verified it -- but a closed one strands a
# subscriber whose renewal notification has not arrived, and the signed proof is then the newer word.
term_ends_at = next((end for end in (*recorded_term, term_end_for(status, proof))
                     if end is not None and end > self.evaluated_at), None)
if term_ends_at is None:
    raise RestoreSubscriptionNotEntitled(cause="term_closed")
```

`write_subscription_grant` then supersedes the stale-active row and inserts the new term with the
month's counter carried over (`crud/subscriptions.py:370-421`), which is the same shape the
already-`expired` arm produces today. Pin it with an e2e case on both arms so the two can never
diverge again.

_The other five reviewers each reported no Critical issue in their own module:_

- **R2 (crud + tables + migration SQL)** — None. I could not construct an input that produces incorrect committed state, loses data, or bypasses an authorization rule in these twelve files.
- **R4 (app wiring + cross-cutting + deployment/config)** — None.  ---
- **R5 (unit test suite)** — None.
- **R6 (e2e + schema test suites)** — None.

## Warnings

### WR-01: Two paths throw away an answer the caller was already charged for, and leave no log line at all

_Reported by reviewer R1 (services + routers)._

**File:** `src/nativespeaker/api/services/chats.py:107-108` and `:140-141`
(with `:150-157`)

**Issue.** In both write paths the order is: commit the read transaction, take an admission slot,
`quota_service.charge(...)` — which commits a spent credit in its own session
(`services/quota.py:100`) — then the provider round trip. Only after the answer is in hand does the
second read run:

```python
        if await self.chats_db.count_chats(user_id) >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)
```

```python
        if await self.chats_db.get_chat(chat_id, user_id) is None:
            raise InvalidChatError(chat_id)
```

Both raises discard a paid-for AI answer. That trade is defensible. What is not is that neither is
recorded anywhere: `ChatHistoryLimitError` extends `InvalidRequest` and `InvalidChatError` extends
`NotFound`, and both of those set `log_level = None` (`errors.py:81-86`, `errors.py:96-101`), so
`app_error_handler` writes nothing (`app/error_handlers.py:35`). The one line an operator could
find the case by is `_commit_the_charged_write`'s `charged_write_failed`
(`services/chats.py:155-156`) — and it sits *below* both raises, so it never runs for them.

Concrete scenario: an account one chat below `chats_limit` fires four concurrent `POST /chats`.
All four pass the first count, all four charge a credit, all four call the provider, one is stored
and three answer `400 invalid_request`. Three credits are gone, three provider calls are paid for,
and the service's own logs contain nothing but three `request` lines at 400 — indistinguishable
from an ordinary client mistake that cost nothing.

**Fix.** Emit the same signal these two paths were built to be findable by, before the raise, with
the closed-set fields the file already uses:

```python
        if await self.chats_db.count_chats(user_id) >= self.chats_limit:
            # The credit is already committed and the provider already answered: this is the only
            # line that finds a charged request whose answer was thrown away.
            logger.warning("charged_answer_discarded", user_id=str(user_id), branch="create_chat")
            raise ChatHistoryLimitError(self.chats_limit)
```

and the same with `branch="send_message"` at `:140`. No refund is implied — `services/quota.py:1-2`
states the policy — only that the case stops being invisible.

### WR-20: the lapse guard returns `applied` for a write that changed nothing, contradicting the same function four lines later

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/crud/subscriptions.py:365-368`

**Issue:** `WriteOutcome` states its own contract at `crud/subscriptions.py:34`: *"What one write
did: it changed a row, it changed nothing, or a concurrent writer won."* — `applied` means a row
changed, `replayed` means nothing changed. The CR-60 lapse guard writes nothing at all (it ends no
grant and inserts none, exactly as `43-REVIEW-FIX.md` describes) and returns `WriteOutcome.applied`:

```python
if (entitled and not held and not may_reactivate
        and await self.grants_db.has_prior_subscription_grant(subscription_id)):
    return WriteOutcome.applied
```

Four lines of code later the same function gets this distinction right for the structurally
identical case:

```python
if not entitled:
    return WriteOutcome.applied if superseded else WriteOutcome.replayed   # :402-404
```

**Failure scenario:** the label is unread today — `SubscriptionsService._settle` and
`RestoreService._settle` both branch on `lost_race` alone — so this commits no wrong row *now*.
It becomes a live defect the moment any caller reads the writer's only observable for what it
says it means. The concrete shape: a caller that emits `store_subscription_grant_written` metrics,
or a caller that decides whether to append `audit.subscription_events` on `applied`, will count and
record a grant write for the exact case the CR-60 fix exists to make a no-op — the store-recovered
subscription whose grant ingestion deliberately did not bring back. That is a silently wrong
operational signal for the one branch nobody looks at.

**Fix:** return the value the enum's own docstring defines for "it changed nothing", which the
`not entitled` arm already uses, and which leaves `_settle` and both commits byte-identical:

```python
if (entitled and not held and not may_reactivate
        and await self.grants_db.has_prior_subscription_grant(subscription_id)):
    # Nothing ended and nothing inserted: the canonical row and the event row still commit.
    return WriteOutcome.replayed
```

Then update `tests/unit/test_subscription_grant_write.py::TestALapsedTermIsNeverBroughtBackByIngestion`,
which pins the current value.

### WR-21: on a move, a broken usage row in the *source* account denies the *destination* account its restore, permanently

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/crud/subscriptions.py:101-112` (reached from
`src/nativespeaker/api/services/restore.py:90`)

**Issue:** `lock_grants_of` raises `MissingUsageRowError` for **every** active grant of **every**
account it was handed:

```python
marked_active = await self.grants_db.lock_active_grants_of(user_ids)
for grant in marked_active:
    usage = await self.grants_db.lock_usage(grant.id)
    if usage is None:
        raise MissingUsageRowError(grant.id)          # :109-111
```

`RestoreService.restore:89` passes `[current_owner, destination]` on a move. The fail-closed
justification the comment gives — *"never mint … no row is written and no lock is spent"* — is the
rule for the **buyer's own** rows, whose counter `write_subscription_grant` reads at
`crud/subscriptions.py:418-424`. It does not hold for the source account's rows: `mine` at
`crud/subscriptions.py:411-412` deliberately excludes `grant.user_id != user_id`, so the source
account's usage row is locked but its `monthly_used` is **never read**. The raise is therefore
strictly wider than the invariant it protects.

**Failure scenario:** the DDL ships `core.manual_grant_issuances`
(`migrations/20260818_01_initial-release.sql:273-280`) and `write_subscription_grant:382-386` has a
live branch for `AccessGrantSource.manual`, but no code in `src/` writes either table — an operator
issues a manual grant by hand. If that operator inserts `core.access_grants` and forgets
`core.user_monthly_usage` (no constraint requires it; `grant_id` is the usage table's PK, not the
grant table's obligation), then account A holds an active grant with no usage row. Account B — an
unrelated paying customer whose store subscription happens to sit on A — presents a valid proof.
`lock_grants_of([A, B])` locks A's manual grant, finds no usage row, and raises. B gets a 500 on
every single restore attempt, forever, for a data break in a stranger's account, with no signal
that names A. A never notices, because A's own `QuotaService.charge` fails on the same row and A is
an operator-granted account.

**Fix:** keep the lock (the lock order requires it), and narrow the raise to the rows this writer
will actually read. Pass the account whose counter is carried, and log rather than raise for the
others:

```python
async def lock_grants_of(self, user_ids: list[UUID], *,
                         counted_for: UUID | None = None) -> list[AccessGrant]:
    marked_active = await self.grants_db.lock_active_grants_of(user_ids)
    for grant in marked_active:
        usage = await self.grants_db.lock_usage(grant.id)
        if usage is None:
            if counted_for is None or grant.user_id == counted_for:
                # Fail closed on the account whose counter this write carries forward.
                raise MissingUsageRowError(grant.id)
            # The source account's row is expired, never read: recorded, never a refusal for the destination.
            logger.error("source_grant_without_usage_row", grant_id=str(grant.id))
    return marked_active
```

`RestoreService` then passes `counted_for=destination`; `lock_grants(user_id)` passes
`counted_for=user_id`, which preserves today's behaviour for the single-account callers exactly.

### WR-35: A Play answer this build cannot read is a 500 on one branch and a 503 on every other

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/auth/google_play.py:391-398` (raised), reached from
`src/nativespeaker/api/auth/google_play.py:373` (`read_for_restore`)

`_product_of` is shared verbatim by the webhook `read()` and by `read_for_restore`. On the webhook
path its `raise InternalError` is correct: a 500 is what makes Pub/Sub redeliver. On the restore
path the same statement becomes a **500 `internal_error`** answered to the app, while every other
"this 2xx body is not one I can read" outcome on that same path is deliberately routed to
`Unavailable(stage=RESTORE_UNPARSEABLE_STAGE)` — a 503 `verification_temporarily_unavailable`
(`google_play.py:367-372`).

The comment at `google_play.py:339-340` shows the author reasoned about exactly this hazard and
covered only half of it: *"Classified here and never by a caught base class, which would turn
`UnmappedStoreProduct` into a 503."* `UnmappedStoreProduct` is a deliberate 500 under D-11. The
plain `InternalError` for the line-item count is not named by any decision, and it rides the same
`InternalError` base out of the same helper.

Proven by driving the real class over a recording transport (all 200 responses):

```
2xx, 0 line items          -> InternalError        http=500 code=internal_error                    stage=None
2xx, 2 line items          -> InternalError        http=500 code=internal_error                    stage=None
2xx, unmapped product      -> UnmappedStoreProduct http=500 code=internal_error                    stage=None   (ratified, D-11)
2xx, non-JSON body         -> Unavailable          http=503 code=verification_temporarily_unavailable stage=play_restore_unparseable
2xx, missing subscriptionState -> Unavailable      http=503 code=verification_temporarily_unavailable stage=play_restore_unparseable
```

**Failure scenario:** a subscriber taps "Restore Purchases". Play answers 200 for a purchase whose
`lineItems` this build does not expect (a multi-line purchase, or a state where Play returns the
list empty). The app receives `500 internal_error` — the one code the client is told nothing about
and cannot retry against — instead of the 503 the same route gives for every other unreadable 2xx.
The operator log line (`google_play_unexpected_line_item_count`) is written either way, so nothing
is lost by classifying it as the restore path's own 503.

**Fix** — let each entry point classify the shared helper's refusal, the way each already classifies
the transport and the parse. Smallest change that keeps `_product_of` shared and keeps the webhook
behaviour byte-identical:

```python
# read_for_restore, replacing line 373
try:
    product_id, tier_id, expiry = self._product_of(subscription)
except UnmappedStoreProduct:
    # D-11: an unmapped product stays the operator's 500 on both paths.
    raise
except InternalError:
    # A line-item shape this build cannot read is as unusable as a body it cannot parse.
    raise Unavailable(stage=RESTORE_UNPARSEABLE_STAGE) from None
```

### WR-36: A Play 400 — the answer a token that does not parse earns — is reported as retryable

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/auth/google_play.py:361-365`

```python
if response.status_code // 100 != 2:
    # Our own two words, never Play's status: a 4xx is a credential or scope an operator
    # repairs, and a 5xx is Play's own outage, which is waited out rather than repaired.
    raise Unavailable(stage=RESTORE_READ_STAGE,
                      cause="refused" if response.status_code // 100 == 4 else "failed")
```

The comment's premise — *"a 4xx is a credential or scope an operator repairs"* — is false for the
one 4xx a *caller* can cause. `purchases.subscriptionsv2.get` answers **400** for a purchase token
that is not a well-formed token and for a token that does not belong to the addressed
`packageName`; 401/403 are the credential and scope cases the comment describes. Only 404 and 410
are peeled off above (`google_play.py:357-360`).

Verified against the real class:

```
status 400 -> Unavailable http=503 code=verification_temporarily_unavailable stage=play_restore_read
status 401 -> Unavailable http=503 ...
status 403 -> Unavailable http=503 ...
status 404 -> ProofRejected http=403 code=proof_rejected stage=play_token_gone
status 410 -> ProofRejected http=403 code=proof_rejected stage=play_token_gone
```

**Failure scenario:** a client (buggy, or an attacker probing) sends a junk `restore_proof` under
`provider: google_play`. The server spends a real, billed `androidpublisher` call, Play answers
400, and the app is told `verification_temporarily_unavailable` — a code whose whole meaning is
"this will work later". A well-behaved client retries a proof that can never verify, and every
retry buys another Play call. The terminal answer the same route already has for a token that
cannot resolve is `proof_rejected`.

This does not contradict D-05, which enumerates 404/410 as `proof_rejected` and "a transport
failure or absent credential" as 503, and says nothing about 400. Classifying 400 is Claude's
Discretion territory, and the current choice is the wrong half of it.

**Fix** — split the caller-fault 400 from the operator-fault 401/403, keeping one stage label per
repair as this module's vocabulary requires:

```python
RESTORE_TOKEN_UNUSABLE_STAGE = "play_restore_token_unusable"
...
if response.status_code == 400:
    # Play's answer for a token that does not parse or does not name this package: the caller's
    # proof, never this deployment's credential, and no later attempt changes it.
    raise ProofRejected(stage=RESTORE_TOKEN_UNUSABLE_STAGE)
if response.status_code // 100 != 2:
    raise Unavailable(stage=RESTORE_READ_STAGE,
                      cause="refused" if response.status_code // 100 == 4 else "failed")
```

If the operator-side reading of 400 (a `packageName` mismatch caused by misconfiguration) is
judged the more likely one, the minimum acceptable change is to give 400 its own `cause` label so
the two are separable in the log — today they share `cause="refused"` with 401 and 403.

### WR-50: The two boot warnings name only the webhook routes, so an unconfigured store now breaks a user-facing route silently

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `src/nativespeaker/api/app/lifespan.py:214-218` and `src/nativespeaker/api/app/lifespan.py:227-231`

**Issue:** Before phase 45, `config.app_store.*` fed exactly one route and
`config.google_play.*` fed exactly one route, and both warnings say so in their
`consequence=` field — the one field an operator reads:

```
consequence="POST /webhooks/app-store refuses every notification until "
            "this pod is restarted with the App Store bundle id, ..."
```

```
consequence="POST /webhooks/google-play/rtdn refuses every delivery until "
            "this pod is restarted with the Play package name, product map, ..."
```

Phase 45 added a second consumer to each. Trace it:

- Apple restore: `dependencies.py:188` → `RestoreService.app_store` → `restore.py:_verify`
  → `AppStoreNotifications.verify_transaction` (`auth/app_store.py:154-155`), which raises
  `Unavailable(stage="app_store_verify")` — 503 `verification_temporarily_unavailable` —
  when `self._verifier is None`. `_verifier` is `None` exactly when
  `build_app_store_verifier` returned `None`, which is the same condition
  `lifespan.py:213` warns on.
- Play restore: `dependencies.py:189-190` → `RestoreService.play` →
  `PlayDeveloperSubscriptions.read_for_restore` (`auth/google_play.py:341-345`), which
  raises `Unavailable` when `self._credential is None` or `package_name` is falsy — again
  the same conditions `lifespan.py:225-226` warns on.

**Failure scenario:** A deployment ships with `APP_STORE_*` unset (a supported mode: the
warning explicitly promises "everything except the store notification runs"). Every
iOS user tapping "Restore purchases" gets 503 `verification_temporarily_unavailable`
forever. The operator greps the boot log, finds one warning that names
`POST /webhooks/app-store` and nothing else, and concludes restore is unrelated. The
`stage="app_store_verify"` label on the 503 is the only other signal, and it names no
setting. The same holds for Play: an operator who deliberately runs without RTDN now
silently has no Android restore either.

**Fix:** Name both consumers in each `consequence` string.

```python
if app_store_verifier is None or not config.app_store.products:
    logger.warning("app_store_configuration_absent",
                   consequence="POST /webhooks/app-store refuses every notification and "
                               "POST /auth/restore-subscription refuses every apple restore "
                               "until this pod is restarted with the App Store bundle id, "
                               "environment, product map, app id (production only) and "
                               "root certificate available in this environment")
```

```python
    logger.warning("google_play_configuration_absent",
                   consequence="POST /webhooks/google-play/rtdn refuses every delivery and "
                               "POST /auth/restore-subscription refuses every google_play "
                               "restore until this pod is restarted with the Play package "
                               "name, product map, push audience, push service account and "
                               "Application Default Credentials available in this environment")
```

---

### WR-51: A transient ADC failure at boot disables Google restore and RTDN for the pod's whole life, with both probes green

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `src/nativespeaker/api/app/lifespan.py:164-172` (and its one call site, `:224`)

**Issue:** `_play_credential()` catches the whole `GoogleAuthError` family and returns
`None`, and its own comment states why: "`google.auth.default()` also raises `RefreshError`
and `TransportError` when the metadata server answers badly at pod start." That `None` is
then frozen into `PlayDeveloperSubscriptions._credential` at `:244-247` and is never
re-read. `PlayDeveloperSubscriptions` has no rebuild path — compare
`auth/google_play.py:280-282` (`read`) and `:341-342` (`read_for_restore`), both of which
just raise `Unavailable` on `self._credential is None` forever.

The immediately adjacent seam was given exactly this fix already: `PubSubPushTokens` takes
a `build=lambda: build_google_push_verifier(config.google_play)` (`lifespan.py:240-243`)
with a serialized, rate-floored rebuild (`auth/google_play.py:230-245`), and the comment
there says "A JWKS blip at boot is transient, so the verifier is rebuilt rather than cached
as absent." The credential has the identical transient-at-boot failure mode and no such
treatment.

Blast radius grew in phase 45: this used to cost only redeliverable webhook traffic
(Pub/Sub retries until retention). It now also costs `POST /auth/restore-subscription`
for `google_play`, which is a paying user pressing a button.

**Failure scenario:** The GKE metadata server is slow or unreachable during the ~2 s window
in which this pod starts (a routine cold-start race on a scaling node pool).
`google.auth.default()` raises `TransportError`, `_play_credential` swallows it,
`lifespan.py:225` logs `google_play_configuration_absent` — the *misconfiguration* warning,
for a correctly configured deployment — and boot continues. `/health/ready` returns 200,
liveness passes, the rollout completes. Every Android restore and every RTDN delivery on
that pod answers 503 until someone notices and restarts it. Nothing recovers on its own.

Counter-argument, stated honestly: 44 D-14 ratified "an absent credential logs a warning at
boot and the route answers 503", and this is a pre-launch startup. But D-14 settled the
*absent* case; it did not decide that a transient transport failure should be
indistinguishable from absence, and the sibling seam's fix shows the project already treats
that distinction as worth one lock and one timestamp.

**Fix:** Give `PlayDeveloperSubscriptions` the same lazy rebuild `PubSubPushTokens` has —
pass the builder rather than the result, and re-attempt behind a lock with a rate floor:

```python
# lifespan.py
app.state.play_subscriptions = PlayDeveloperSubscriptions(
    credential=play_credential,
    # A metadata-server blip at boot is transient, so the credential is rebuilt rather
    # than cached as absent, as the push verifier above is.
    build=_play_credential,
    client=play_client,
    products=config.google_play.products)
```

Alternatively, if the rebuild is judged too much for this milestone, at minimum tell the
two failures apart at boot so an operator can act, as the Google push verifier already
does at `lifespan.py:232-237`:

```python
def _play_credential():
    try:
        credential, _project = google.auth.default(scopes=[PLAY_SCOPE])
    except google.auth.exceptions.DefaultCredentialsError:
        return None
    except google.auth.exceptions.GoogleAuthError:
        logger.warning("play_credential_warm_up_failed",
                       consequence="POST /webhooks/google-play/rtdn and the google_play arm "
                                   "of POST /auth/restore-subscription answer 503 until this "
                                   "pod is restarted; the credential is not absent, the "
                                   "metadata server answered badly at boot")
        return None
    return credential
```

---

### WR-65: The grant-tier lock statement is asserted by nothing — `FOR UPDATE` and the ascending id order can both be deleted with the suite green

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_subscription_grant_write.py:398-408` (and the whole suite)

**Issue.** `_LockStubSession.exec` takes the statement and discards it:

```python
    async def exec(self, statement):  # noqa: ARG002
        self.reads += 1
        return _LockStubResult(self.grants if self.reads == 1 else self.usage)
```

`TestTheSecondLockTierRefusesAnAbsentUsageRow` (lines 411-440) is therefore the only test that runs
`SubscriptionsDB.lock_grants_of`, and it measures the absent-usage-row refusal and the read *count*
(`session.reads == 2`) — never that either read takes a lock, and never the order they take it in.
Grepping the whole unit tree for `FOR UPDATE` finds assertions for
`_effective_grants_statement` (`test_quota_resolver.py:314`), `_usage_statement`
(`test_quota_resolver.py:328`) and the three negative cases in `test_sync_resolver.py:147-155` —
and nothing for `_active_grants_of_statement`, the statement phase 45 D-08 introduced and the one
SHARED-INVARIANTS § Locks names *first* in the lock order.

**Mutation proof.** Removing `.order_by(col(AccessGrant.id).asc())` from
`crud/grants.py:52-54` **and** `.with_for_update()` from `crud/grants.py:129-130` leaves
`tests/unit/test_subscription_grant_write.py tests/unit/test_restore_proof.py
tests/unit/test_claim_precedence.py tests/unit/test_claim_precedence_registered.py
tests/unit/test_quota_resolver.py tests/unit/test_sync_resolver.py` at **284 passed**. Note the
blast radius is wider than restore: `_active_grants_statement` (`grants.py:57-60`) delegates to the
same builder, so the claim and webhook paths lose their grant-tier lock in the same edit.

A lost `FOR UPDATE` here is not caught downstream either: `tests/schema/test_restore_race.py`'s
adopter race is arbitrated by the conditional owner update and by
`ix_access_grants_one_per_subscription`, and it has a class
(`TestTheUniqueIndexArbitratesWhereTheOwnerUpdateCannot`) that treats the index arbitration as a
legitimate outcome. A lost `ORDER BY` — the deadlock-avoidance half of the invariant — is
observable by no test at any level.

**Fix.** Capture the statement in `_LockStubSession` and assert its compiled text, using the
`_compiled` helper the sibling suites already use (`test_quota_resolver.py:125-127`):

```python
from sqlalchemy.dialects import postgresql

class _LockStubSession:
    def __init__(self, grants, usage):
        ...
        self.statements: list = []

    async def exec(self, statement):
        self.statements.append(statement)
        self.reads += 1
        return _LockStubResult(self.grants if self.reads == 1 else self.usage)


def _compiled(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


    async def test_the_grant_tier_locks_and_takes_one_ascending_order_for_both_accounts(self):
        held = _grant(subscription_id=SUBSCRIPTION_A)
        session = _LockStubSession([held], _usage(held, monthly_period=THIS_MONTH, monthly_used=0))

        await SubscriptionsDB(session).lock_grants_of([DESTINATION, OLD_OWNER])

        sql = _compiled(session.statements[0])
        assert "FOR UPDATE" in sql
        assert "ORDER BY core.access_grants.id ASC" in sql
        # One statement over both accounts, so the pair is taken in one ascending order and not two.
        assert "core.access_grants.user_id IN (" in sql
        assert "FOR UPDATE" in _compiled(session.statements[1])
```

Verified against its own probe: with production intact the compiled statement reads
`... user_id IN (__[POSTCOMPILE_user_id_1]) AND ... status = %(status_1)s ORDER BY
core.access_grants.id ASC FOR UPDATE`; with the two mutations above applied,
`"FOR UPDATE" in sql` and `"ORDER BY core.access_grants.id ASC" in sql` are both `False`.

---

### WR-66: `test_restore_proof.py` declares a captured instant it does not have — the Apple fixture mints its dates from the wall clock

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_restore_proof.py:67-68`

**Issue.** The module states:

```python
# One captured instant for every case below, so no assertion here depends on the wall clock.
EVALUATED_AT = datetime(2026, 6, 1, tzinfo=UTC)
```

That is false for every case that mints a bare `_transaction()`. The imported helper
(`tests/unit/test_app_store_notifications.py:189-203`) builds its stamps from `datetime.now(UTC)`,
not from `EVALUATED_AT`:

```python
def _transaction(*, ..., expires_in: timedelta = timedelta(days=30), ...) -> dict:
    now = datetime.now(UTC)
    return {..., "purchaseDate": _milliseconds(now),
                 "expiresDate": _milliseconds(now + expires_in), ...}
```

Measured today: `EVALUATED_AT` is `2026-06-01`, while the fixture's `purchaseDate` is `2026-09-10`
and its `expiresDate` is `2026-10-10`.

Two consequences:

* `test_grace_period_is_unreachable_from_a_proof_that_carries_no_renewal_payload`
  (lines 169-177) needs the bare `_transaction()` element to map to `active`. It does — but only
  because `now + 30 days` happens to be later than a constant three months in the past. Bump
  `EVALUATED_AT` forward past `now + 30 days` (the ordinary maintenance edit when a fixed date
  starts to look stale) and the set collapses to `{expired, revoked}`, failing with a message about
  grace periods for a reason that has nothing to do with grace.
* `test_a_transaction_minted_by_the_chain_verifies_and_names_its_subscription` (line 117) validates
  a `RestoredSubscription` whose `purchased_at` is three months *after* the instant that produced
  it — a shape the restore path itself treats as impossible and clamps
  (`services/restore.py:70`, and `TestTheRestoredGrantNeverBeginsAfterTheInstantThatWroteIt` is the
  test for that clamp).

**Fix.** Give `_transaction()` an explicit base instant so its callers can pin it, and pass
`EVALUATED_AT` from the restore module:

```python
# tests/unit/test_app_store_notifications.py
def _transaction(*, bundle_id: str = BUNDLE_ID, environment: str = "Sandbox",
                 revocation_date: int | None = None, expires_in: timedelta = timedelta(days=30),
                 original_transaction_id: str | None = ORIGINAL_TRANSACTION_ID,
                 # The captured instant this payload is dated against; never the wall clock, so a
                 # case that names an instant is the one that decides the status.
                 now: datetime | None = None) -> dict:
    now = datetime.now(UTC) if now is None else now
    ...

# tests/unit/test_restore_proof.py
def _proof_through(chain, transaction, *, evaluated_at=EVALUATED_AT):
    ...

def _dated(offset: timedelta) -> dict:
    return _transaction(now=EVALUATED_AT) | {"expiresDate": _milliseconds(EVALUATED_AT + offset)}
```

then replace each bare `_transaction()` in this module with `_transaction(now=EVALUATED_AT)`. Note
`_build_chain` must keep the real clock — the library checks certificate validity against it — so
only the payload dates move.

---

### WR-67: Restore's `core.store_purchases` write is executed by no unit test, and the e2e only counts the rows

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_restore_proof.py:752-754`, `tests/unit/test_restore_proof.py:661-683`
(the two stand-ins), against `src/nativespeaker/api/services/restore.py:142-155`

**Issue.** Restore inserts the purchase row on the branch where none exists:

```python
        if recorded is None:
            await self._settle(await self.subscriptions_db.insert_purchase(
                provider=proof.provider,
                identity_value=str(uuid7()) if token is None else token,
                ...
                purchase_user_id=attributed,
                # Set only when the token resolved: the second foreign key needs a binding to point at.
                resolved_token_value=None if attributed is None else token,
                evaluated_at=self.evaluated_at), proof)
```

No unit test reaches it. `_GrantRecorder.read_purchase` answers with a row on purpose
("Not `None`, so the purchase insert is skipped and the grant writer is the one write",
line 753), and `_InsertOnlyRecorder` raises `_Stop` at `insert_subscription` (line 679), long
before. The webhook sibling has the column-level coverage this branch lacks —
`test_subscription_attribution.py:292-350` asserts `purchase_user_id`, `resolved_token_value`, the
two store ids and the generated `identity_value` one by one — so the asymmetry is not a house style.

**Mutation proof.** Renaming the call at `services/restore.py:144` to
`insert_purchase_NEVER_REACHED(` — a method that does not exist on any stand-in or on
`SubscriptionsDB` — leaves `tests/unit/test_restore_proof.py
tests/unit/test_subscription_grant_write.py tests/unit/test_subscription_attribution.py` at
**163 passed**. The line is dead to the unit suite.

It is not covered downstream at column level either: `tests/e2e/test_restore_subscription.py`
reads `core.store_purchases` only through `_four_counts` (lines 185-193), which returns
`len(purchases)` — a count, never a column.

This is a reachable defect surface, not a coverage nag. `resolved_token_value` is one half of the
DEFERRABLE INITIALLY DEFERRED foreign key pair: setting it on the unattributed branch (where
`attributed is None` and there is no `core.store_purchase_tokens` row to point at) produces a
`23503` at COMMIT — precisely the opaque failure
`TestTheDeferredKeysAreClassifiedWhereTheyAreEvaluated` (lines 817-879) exists to make visible, and
the client sees a 500 after the grant has already been written in the same transaction.
`identity_value` is NOT NULL.

**Fix.** Give `_GrantRecorder` an unrecorded-purchase mode and assert the fields, mirroring
`test_subscription_attribution.py::TestTheSinglePurchaseArms`:

```python
class _GrantRecorder:
    def __init__(self, destination, settled_status=SubscriptionStatus.active,
                 settled_tier: str = TIER_ID, *, purchase_recorded: bool = True) -> None:
        ...
        self._purchase_recorded = purchase_recorded
        self.purchases: list[dict] = []

    async def read_purchase(self, provider, external_id):
        if not self._purchase_recorded:
            return None
        return SimpleNamespace(id=uuid4(), resolved_token_value=None)

    async def insert_purchase(self, **fields):
        self.purchases.append(fields)
        return WriteOutcome.applied


class TestTheFirstRestoreOfAnUnrecordedPurchaseWritesItsRow:
    async def test_a_proof_whose_token_binds_to_nobody_points_the_deferred_key_at_nothing(self):
        """The token resolved to no account, so `resolved_token_value` has no binding to name and
        naming one reaches the deferred foreign key at COMMIT as an opaque 500."""
        recorder, _ = await _same_account_restore(EVALUATED_AT - timedelta(days=1),
                                                  purchase_recorded=False)

        written = recorder.purchases[0]
        assert (written["purchase_user_id"], written["resolved_token_value"]) == (None, None)
        assert written["identity_value"] == ATTRIBUTION_TOKEN
        assert written["store_original_transaction_id"] == ORIGINAL_TRANSACTION_ID
        assert written["store_transaction_id"] is None
```

(`_same_account_restore` grows the same keyword and forwards it to `_GrantRecorder`. Its
`purchases_db` is `_NoAttribution`, so `attributed` is `None` and this is the unbound branch; a
second case wiring a resolver that answers the caller's own id pins the attributed branch, where
both fields must be set.) Probe check: with `resolved_token_value=None if attributed is None else
token` changed to `resolved_token_value=token`, the first assertion above fails
(`('a-…-token' != None)`); with `identity_value=str(uuid7()) if token is None else token` changed
to `identity_value=str(uuid7())`, the third fails.

### WR-80: Restore's two-account grant lock is pinned by no test, and a deadlocking regression passes the whole repo

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/schema/test_grant_locks.py:645-694` (and the file as a whole)
**Also:** `src/nativespeaker/api/crud/subscriptions.py:101-112`, `src/nativespeaker/api/crud/grants.py:45-52`

`test_grant_locks.py` exists to prove SHARED-INVARIANTS § Locks from the statements a writer
emits. It does so for three writers — the anonymous claim
(`TestTheActivationAddsNoThirdLockTier`), the registered conversion
(`TestTheRegisteredWriterAddsNoThirdLockTier`) and the store ingestion
(`TestTheSubscriptionWriterAddsNoThirdLockTier`, line 694). Restore is absent, and restore is the
one writer D-08 gives two accounts to lock: `accounts = [current_owner, destination]`
(`services/restore.py:89-90`).

`TestTheIssuedStatementsAreProductionsOwn` (line 51) pins `_effective_grants_statement` and
`_usage_statement`. It does **not** pin `_active_grants_of_statement`, which is the statement the
restore path actually issues.

**Mutation proof.** I replaced the single ascending statement in
`SubscriptionsDB.lock_grants_of` with a per-user loop in list order:

```python
marked_active = []
for one in user_ids:
    marked_active.extend(await self.grants_db.lock_active_grants(one))
```

Result: `tests/e2e/test_restore_subscription.py` 35 passed, `tests/schema/test_restore_race.py` +
`tests/schema/test_grant_locks.py` 70 passed, `tests/unit` 1898 passed. Nothing went red. Reverted.

**Failure scenario the suite would miss.** Accounts A and B each hold a paid subscription. A user
restores B's subscription onto A at the same moment another restores A's onto B. Under the mutated
(list-order) lock, request 1 locks A's grants then waits for B's; request 2 locks B's then waits
for A's. PostgreSQL kills one with `40P01` and the caller gets a 500 that a retry reproduces.
The single `IN (:a, :b) ORDER BY id ASC` statement is what prevents this, and nothing asserts it.

**Fix.** Add a restore fixture to `tests/schema/test_grant_locks.py` on the same terms as
`_ingestion_run`, driving `RestoreService.restore` for a move (two accounts) with a
`before_cursor_execute` recorder, then assert with the existing helpers:

```python
async def test_the_move_locks_both_accounts_grant_rows_in_one_ascending_statement(self, move_statements):
    taken = locking(move_statements["statements"])
    assert [relations_of(s) for s in taken] == [["core.access_grants"],
                                                ["core.user_monthly_usage"],
                                                ["core.user_monthly_usage"]]
    assert "ORDER BY core.access_grants.id ASC" in taken[0]
    # One statement for the pair: two grant-tier locks are two orders, which is the deadlock.
    assert len([s for s in taken if "core.access_grants" in s]) == 1
```

I confirmed the first three assertions fail under the mutation above and pass on HEAD.

---

### WR-81: Nothing asserts the Play restore read uses the configured package name; a wrong one passes every test

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/e2e/test_restore_subscription.py:753-757`
**Also:** `src/nativespeaker/api/app/dependencies.py:186-190`

`FakePlaySubscriptions.read_for_restore` records `package_name`
(`tests/e2e/conftest.py:517-519`), and before this phase's re-review the test asserted it — the
deleted line read *"The proof itself is the token the read was made with, and the package name is
the config's."* The replacement assertion (753-757) drops `package_name` and asserts
`(purchase_token, evaluated_at)` instead. No other e2e, schema or unit test covers it: the unit
suite passes `PACKAGE_NAME` in by hand (`tests/unit/test_restore_proof.py:233` and friends), which
says nothing about the route's wiring, and `real_google_play_seam` answers any URL.

**Mutation proof.** I replaced
`package_name=request.app.state.config.google_play.package_name` in `get_restore_service` with
`package_name="com.wrong.package"`. Result: `tests/e2e` + `tests/unit`, **2258 passed**. Reverted.

**Failure scenario.** A mis-wired or renamed config field sends
`GET .../applications/com.wrong.package/purchases/subscriptionsv2/tokens/...` to Google. Every
Google Play restore answers `403 proof_rejected` for every paying Android customer, and no test in
the repo goes red.

**Fix.** Restore the dropped element to the same tuple:

```python
assert [(call["package_name"], call["purchase_token"], call["evaluated_at"]) for call in
        scripted_play_subscriptions.restore_calls] == [(GOOGLE_PACKAGE_NAME, purchase_token,
                                                        pinned_evaluation_instant)]
```

`GOOGLE_PACKAGE_NAME` is already exported from `tests/e2e/conftest.py:423`. The Play fake fixture
`scripted_play_subscriptions` does not set `play.package_name`, so the test must either add
`scripted_google_play` (which pins it, conftest:561-569) or read
`_app_lifespan.state.config.google_play.package_name`. I verified the assertion above fails under
the `com.wrong.package` mutation.

---

### WR-82: The adoption-with-creation lost race is untested, and the class docstring that dismisses it is wrong

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/schema/test_restore_race.py:361-363`
**Also:** `src/nativespeaker/api/services/restore.py:112-124`

`TestTheUniqueIndexArbitratesWhereTheOwnerUpdateCannot` says: *"The backstop the class above names,
**on the one path that reaches it**: 23505 and nothing else."* That is not true. Restore has a
second 23505 path, and it is the one D-06's adoption-with-creation branch names in the code itself:

```python
if stored is None:
    # Insert-only and written unowned: a row a webhook committed since the read above is a lost race.
    stored, outcome = await self.subscriptions_db.insert_subscription(...)
    await self._settle(outcome, proof)
```

`insert_subscription` → `_flush_or_lose` → `WriteOutcome.lost_race` fires when a webhook commits the
canonical row for `(provider, external_id)` between restore's plain read (`restore.py:57`) and this
insert — i.e. `ix_subscriptions_provider_external_id`, not `ix_access_grants_one_active_per_user`.
`tests/schema/test_subscription_race.py` covers the ingestion side of exactly this race; the
restore side has no case on any tier.

**Mutation proof.** I replaced `await self._settle(outcome, proof)` on that branch with
`_ = outcome`. Result: `tests/e2e/test_restore_subscription.py` +
`tests/schema/test_restore_race.py` + `tests/unit`, **1962 passed**. Reverted. With that line gone
the service carries on inside a PostgreSQL-aborted transaction and the caller gets an opaque 500
whose only log line is `restore_commit_refused` — the wrong event name for a lost race.

**Fix.** Two changes, both small.

1. Correct the docstring at line 363: this class covers the *grant* backstop, not "the one path".
2. Add a case to `tests/schema/test_restore_race.py`, reusing `_RecordingSession`'s
   `before_first_commit` hook shape but on the flush that matters — commit the row from a second
   connection while the attempt holds at its barrier, then assert the attempt answers 500 with
   `sqlstate == "23505"` and `integrity_at_flush is True`, and that exactly one
   `core.subscriptions` row exists for the key. The `_CommitsBeforeTheFlush` wrapper in
   `tests/schema/test_grant_locks.py:747-758` is the existing pattern for this.

## Info

### IN-01: `/auth/sync` is still the only `SyncResponse` route without `Cache-Control: no-store`

_Reported by reviewer R1 (services + routers)._

**File:** `src/nativespeaker/api/routers/auth.py:183-192`

**Issue.** `claim_anonymous_grant` (`:128`), `claim_registered_grant` (`:151`),
`restore_subscription` (`:179`) and `/users/me` (`routers/users.py:24`) all take
`response: Response` and set `no-store`. `/auth/sync` returns the same `SyncResponse` body — the
tier, the allowance and the month's usage — and sets nothing. This was filed as phase-38 IN-34
(`.planning/phases/38-post-auth-sync/38-REVIEW.md:2035`), was never fixed, and no ratified decision
drops it; D-12 requires the header on the restore answer and gives no reason sync should differ.

**Fix.** Take `response: Response` and set `response.headers["Cache-Control"] = "no-store"`,
matching its three siblings exactly.

### IN-02: A loop-invariant `None` test sits inside the term comprehension

_Reported by reviewer R1 (services + routers)._

**File:** `src/nativespeaker/api/services/restore.py:102-105`

**Issue.** `if stored is not None` is re-evaluated for every grant in `marked_active`, and it
guards the attribute access on the following line rather than the iteration. It reads as if it
were a per-grant condition.

**Fix.** Hoist it: `recorded_term = [] if stored is None else [grant.ends_at for grant in ... ]`,
or fold it into the `term_ends_at` expression. (If CR-01 is fixed, this disappears with it.)

### IN-03: Two read-only routes open a database session and build a `QuotaService` they never use

_Reported by reviewer R1 (services + routers)._

**File:** `src/nativespeaker/api/routers/root.py:15` and
`src/nativespeaker/api/routers/examples.py:16`

**Issue.** Both depend on `get_chat_service`, which depends on `get_db` (opening a pooled session
for the whole request) and on `get_quota_service` (`app/dependencies.py:124-138`). `root()` reads
`service.supported_languages` — `list(self.examples.keys())` — and `get_examples()` reads
`self.examples[lang]`. Neither touches the session, the quota or the LLM. A pooled connection is
held for the life of every `GET /` and `GET /examples`.

**Fix.** Give both routes a dependency that returns only what they use, e.g.
`def get_examples_map(config: AppConfig = Depends(get_config)) -> dict[str, list[str]]`, and move
`get_examples`/`supported_languages` onto it or onto a plain function. `ChatService` keeps its
session for the four routes that write.

### IN-04: The `resolved_mode` fallthrough in `ask_llm` is unreachable

_Reported by reviewer R1 (services + routers)._

**File:** `src/nativespeaker/api/services/chats.py:74-75`

**Issue.** `llm_response` is `ChatModelResponse.model_dump()` produced by
`create_chain`'s `RunnableLambda` (`services/llm.py:34-35`), and `ChatModelResponse.resolved_mode`
is `Literal["analyze", "follow_up", "reject"]` validated by pydantic before the dump
(`schemas/llm.py:34-40`). All three values are handled at `:67`, `:69` and `:72`, so the `else`
cannot be reached. It is also the only arm that would answer `500` at `log_level = ERROR`
(`errors.py:211-213`) with the value interpolated into the traceback.

**Fix.** Keep it as a tripwire but say so in a comment (the codebase's own convention for
`MultipleEffectiveGrantsError` and the two `settled` checks), or drop it and let the union be
exhaustive. Do not leave it looking like a live branch.

### IN-05: Two handlers carry no return annotation while every sibling does

_Reported by reviewer R1 (services + routers)._

**File:** `src/nativespeaker/api/routers/chats.py:21-22` and
`src/nativespeaker/api/routers/root.py:15`

**Issue.** `list_chats` and `root` are the only handlers across the five routers without a return
type; the other twelve all have one, and `ty` therefore checks the other twelve against their
`response_model` and not these two.

**Fix.** `-> list[ChatResponse]` on `list_chats`; `-> dict[str, object]` (or a declared response
model) on `root`.

### IN-22: the unique-violation classification is copy-pasted five times in one file, beside a helper that already does it

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/crud/subscriptions.py:141-153` (the helper), duplicated at
`:304-313`, `:330-339`, `:391-400`, `:442-451`; the same seven lines appear again at
`crud/grants.py:237-246`, `:316-323`, `:346-355` and `crud/identities.py:124-138`, `:164-175`.

**Issue:** `_flush_or_lose` exists in `SubscriptionsDB` for exactly this and is used by two of the
six writers in the file. `insert_purchase`, `append_event` and both flushes inside
`write_subscription_grant` restate it verbatim, comment lines included. This is the most
security-relevant classification in the package (it is what decides whether a violation is a lost
race or a broken invariant); a future change to it — say, admitting 40001 serialization failures —
must be made in nine places, and one miss silently converts a broken invariant into a "race".

**Fix:** route every writer in `SubscriptionsDB` through `_flush_or_lose`, and lift the
`grants.py` / `identities.py` variants to a shared `crud/violations.py` helper such as
`async def flush_or_lose(session) -> bool`.

### IN-23: two of the five no-lock readers in `grants.py` omit `populate_existing` with no reason given

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/crud/grants.py:111-115` (`read_effective_grants`) and `:133-135`
(`read_active_grants`)

**Issue:** every other reader in this package carries `populate_existing=True` with a written
justification — `lock_effective_grants:104-108`, `lock_active_grants:120-122`,
`lock_active_grants_of:128-130`, `lock_usage:144-146`, `read_usage:151-153`,
`SubscriptionsDB.read_subscription:121-125`. These two do not, and say nothing about why. I traced
both and neither is wrong today (`SyncService.read_entitlement` runs after a `commit()` or a
`rollback()`, and the two `services/auth.py` call sites are pre-transaction), but the omission is
indistinguishable from an oversight, which is precisely the trap `read_usage`'s own comment was
added to close.

**Fix:** either add `populate_existing=True` for symmetry, or add one line naming why these two
readers do not need it.

### IN-24: `ExternalIdentity` mints its own wall clock, which the entitlement-table guard forbids for the same shape

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/tables/identities.py:55-56`

**Issue:**

```python
created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```

`tables/grants.py:70-71` states the opposite rule for the entitlement tables — *"No default on any
timestamp in this module: the creating transaction owns the clock, so a forgotten value is a NOT
NULL violation rather than a second reading of it"* — and
`tests/unit/test_tables_metadata.py::TestTheEntitlementTablesHoldNoSecondClock` enforces it. That
test's `_ENTITLEMENT_TABLES` tuple is `(AccessTier, AccessGrant, UserMonthlyUsage)` only, so
`ExternalIdentity` (and `User`, `Chat`, `Message`) sit outside it. SHARED-INVARIANTS § "Grants and
evaluation time" states the rule without that scoping: *"Derive every time-dependent value from ONE
captured evaluation time … per request."* The DDL agrees with `grants.py`, not with the model:
`migrations/20260818_01_initial-release.sql:88-89` gives `created_at`/`updated_at` on
`core.external_identities` **no** `DEFAULT`. No live caller relies on the factory —
`IdentitiesDB.insert_account:114-115` passes `evaluated_at` for both — so this is latent, not
broken.

**Fix:** drop both `default_factory`s so a forgotten value is a 23502 rather than a second clock
reading, matching the DDL and `grants.py`. If the four non-entitlement tables are a deliberate
exception, widen the guard test's tuple and record the exception in the module docstring.

### IN-25: `lock_active_grants` is a second spelling of `lock_active_grants_of([user_id])`

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/crud/grants.py:117-123` (with `:57-60`)

**Issue:** `_active_grants_statement(user_id)` was already collapsed to
`_active_grants_of_statement([user_id])` for the stated reason *"so the two callers can never drift
apart"* (`:59`), and `SubscriptionsDB.lock_grants` was collapsed to `lock_grants_of([user_id])` for
the same reason (`crud/subscriptions.py:95-99`). `lock_active_grants` is the one member of that
family still restating the `.with_for_update().execution_options(populate_existing=True)` chain
rather than delegating, so it is the one place a future change to the lock statement can miss.

**Fix:** `return await self.lock_active_grants_of([user_id])`.

### IN-26: the one-active-per-user index comment claims unreachability that the phase's own test disproves

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `migrations/20260818_01_initial-release.sql:262`

**Issue:** the comment reads *"Non-deferrable and per-statement; a correct caller makes it
unreachable by expiring before activating."* Phase 45 D-08 makes a unique index the deliberate
**backstop** for the restore race, and
`tests/schema/test_restore_race.py::TestTheUniqueIndexArbitratesWhereTheOwnerUpdateCannot` proves
`ix_access_grants_one_active_per_user` firing between two *correct* concurrent restores of one
account — 23505 at the flush, one attempt answering 500. The comment reads as though a 23505 from
this index is a caller bug, which is the opposite of the design.

**Fix:** amend to name both roles, e.g. *"Non-deferrable and per-statement. One caller makes it
unreachable by expiring before activating; between concurrent callers it is the arbiter, read as
SQLSTATE 23505 only."*

### IN-27: `Chat.human_messages` is dead, and has been reported dead in four prior phases

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/tables/chats.py:57-59`

**Issue:** `grep -rn "human_messages" src tests` returns the definition and nothing else; only
`ai_messages` has a reader (`services/chats.py:127`). Filed already as 37.1 `:57-58`, 38, 39 IN-20
and 40 IN-40, and still present. There are also two consecutive blank lines inside the `Chat` class
body at `:36-37`, which no other table in the package has.

**Fix:** delete the property and one blank line, or record it as accepted so the next reviewer stops
re-filing it.

### IN-28: `count_chats` is the one crud method that leaves `session.scalar`'s `None` unhandled, and the one that bypasses `exec`

_Reported by reviewer R2 (crud + tables + migration SQL)._

**File:** `src/nativespeaker/api/crud/chats.py:26-28`

**Issue:**

```python
async def count_chats(self, user_id: UUID) -> int:
    statement = select(func.count()).select_from(Chat).where(Chat.user_id == user_id)
    return await self.session.scalar(statement)
```

`AsyncSession.scalar` is typed `Any | None`, so the declared `-> int` is unverified — `ty` passes
only because `Any` absorbs it. Every other read in the package goes through `session.exec(...)`
with an explicit `.first()`/`.all()`. The `.where(Chat.user_id == ...)` also drops the `col(...)`
wrapper used on the two lines above and below it.

**Fix:**

```python
async def count_chats(self, user_id: UUID) -> int:
    statement = select(func.count()).select_from(Chat).where(col(Chat.user_id) == user_id)
    return (await self.session.exec(statement)).one()
```

### IN-35: A comment names a consumer of `linkedPurchaseToken` that does not exist

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/auth/google_play.py:101-102`

```python
# Parsed and not acted on: an upgrade's old token is the restore route's to read.
linkedPurchaseToken: str | None = None
```

The restore route does not read it. `grep -rn "linkedPurchaseToken\|linked_purchase" src/ tests/`
returns exactly one hit — this declaration. The field is parsed and discarded by both entry points.
A reader of `read_for_restore` will go looking for the upgrade handling the comment promises and
find none.

**Fix** — say what is true: `# Parsed and not acted on: no path reads an upgrade's old token today.`
Or delete the field, since nothing consumes it and pydantic ignores unknown keys here anyway.

### IN-36: The JWKS negative cache is keyed on a PyJWT message string that no test pins

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:63` and `src/nativespeaker/api/auth/jwt_verifier.py:203`

```python
_DEFINITIVE_KID_MISS = "Unable to find a signing key that matches"
...
if _DEFINITIVE_KID_MISS not in str(exc):
    logger.error("jwks_endpoint_unusable", failure=type(exc).__name__)
elif cache_key is not None:
    self._record_unknown(cache_key)
```

The substring is PyJWT's own wording, not a public API. `grep -rn "_DEFINITIVE_KID_MISS\|Unable to
find a signing key" tests/` returns nothing, so no test would fail if PyJWT reworded it. On a
reword the branch inverts silently: the negative cache stops recording (every bogus-`kid` token
re-fetches JWKS) **and** every such token writes an ERROR line labelled `jwks_endpoint_unusable`,
which is precisely the alert a token-spike is supposed to distinguish itself from.

**Fix** — pin the coupling with one unit case that raises the real `PyJWKClientError` PyJWT raises
for an absent key id and asserts the entry landed in `_unknown_kids`, so a dependency bump fails
loudly rather than degrading.

### IN-37: One stage label in this module is a bare literal while the rest are named constants

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/auth/google_play.py:283`

`read()` raises `Unavailable(stage="play_subscriptions_read")` as a literal, while the six restore
stages are module constants (`google_play.py:55-60`) precisely so the log vocabulary is a closed,
greppable set. The literal is the one member of that vocabulary an operator cannot find by reading
the constants block.

**Fix** — add `NOTIFICATION_READ_STAGE = "play_subscriptions_read"` beside the other six and use it.

### IN-38: `restore_proof`'s bound carries a much thinner margin than the same certificate chain gets on the webhook

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/schemas/auth.py:47`

```python
restore_proof: str = Field(..., min_length=1, max_length=8192)
```

`webhooks.py:4-6` bounds the App Store envelope at 65536 and reasons: *"Apple sends its certificate
chain three times in one envelope, so a real V2 notification lands in the 18-24 KB range."* That
same reasoning puts one Apple JWS — which is what `restore_proof` carries on the Apple arm — at
roughly 5-7 KB, against an 8192 bound. The webhook takes a ~3x margin over its own estimate; the
restore proof takes well under 2x.

I did not prove a real Apple `Transaction.jwsRepresentation` exceeds 8192: the throwaway chain in
`tests/unit/test_app_store_notifications.py` mints a 2828-character JWS (2288 of it header/x5c),
and its certificates are minimal compared to Apple's, so this is an estimate and not a measurement.
Recording it as Info rather than a Warning for that reason. The consequence if the estimate is
wrong in the tight direction is a hard 422 on every Apple restore, with no server log, the moment
Apple lengthens a certificate or adds one to the chain.

**Fix** — bound it against the same envelope reasoning the webhook already wrote down, e.g.
`max_length=APP_STORE_ENVELOPE_LIMIT // 2` with a comment tying it to `webhooks.py:4-6`; or measure
one production `jwsRepresentation` and record the number in the comment.

### IN-39: Play test purchases restore as paid, while Apple sandbox transactions are refused

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/auth/google_play.py:95-104`

`PlaySubscription` does not declare `testPurchase`, the field `subscriptionsv2.get` returns
("only present if this subscription purchase is a test purchase"). A license-tester purchase — free
and renewing every few minutes — therefore reads as an ordinary entitled subscription and mints a
real grant through `read_for_restore`.

The asymmetry is what makes this worth recording rather than the exposure: on the Apple arm the
library's `environment` check (`SignedDataVerifier.verify_and_decode_signed_transaction`, driven
with `enable_online_checks=False` and the configured `Environment`) refuses a sandbox transaction
outright, and `tests/unit/test_restore_proof.py` pins that. The two stores are held to different
standards for the same "this is not a real purchase" signal.

Deliberately Info, not Warning: Play license testers are a closed list the developer maintains in
Play Console, nobody can self-enrol, and refusing test purchases would break the developer's own
restore testing on the internal track — which is an argument for leaving it as is, not just an
argument about blast radius. AGENTS.md's "do not over-engineer for theft" applies. Record the
choice rather than change it.

**Fix** — either declare `testPurchase: dict | None = None` and refuse it on the restore arm only,
or add one line to the module docstring stating that a Play test purchase is accepted by design and
that the Apple arm's environment check has no Play counterpart.

### IN-40: A redundant operand hides which guard actually rejects an empty package name

_Reported by reviewer R3 (auth adapters + schemas)._

**File:** `src/nativespeaker/api/auth/google_play.py:284` and `src/nativespeaker/api/auth/google_play.py:343`

```python
if not package_name or not _names_one_path_segment(package_name):
```

`_names_one_path_segment("")` is `bool("".strip("."))` → `False`, so the second operand already
rejects the empty string; the first can never be the deciding one. The token guards on lines 289
and 346 correctly use the predicate alone, so the two pairs read as if they enforce different
rules when they enforce the same one.

**Fix** — drop `not package_name or` from both, leaving `if not _names_one_path_segment(package_name):`.

### IN-50: `get_restore_service` passes `str | None` into a parameter annotated `str`

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `src/nativespeaker/api/app/dependencies.py:190`

**Issue:** `config.google_play.package_name` is `str | None` (`config.py:128`), but
`RestoreService.__init__` declares `package_name: str` (`services/restore.py:41`) and
forwards it to `read_for_restore(*, package_name: str, ...)`
(`auth/google_play.py:336`). `ty` cannot see the mismatch because `request.app.state` is
untyped, so the annotation is a claim nothing checks. It is currently harmless — the
falsy value is caught at `auth/google_play.py:343` — but the annotation is the thing a
future caller will trust.

Secondary: this dependency reaches into `request.app.state.config` while its sibling
`get_chat_service` (`dependencies.py:126`) takes `config: AppConfig = Depends(get_config)`.

**Fix:** Widen the annotations to `str | None` on `RestoreService.__init__` and
`read_for_restore`, since the falsy branch is a supported input, and take the config
through `Depends(get_config)`:

```python
def get_restore_service(request: Request,
                        db: AsyncSession = Depends(get_db),
                        config: AppConfig = Depends(get_config),
                        evaluated_at: datetime = Depends(get_evaluated_at)) -> RestoreService:
    return RestoreService(db=db,
                          evaluated_at=evaluated_at,
                          app_store=request.app.state.app_store_notifications,
                          play=request.app.state.play_subscriptions,
                          package_name=config.google_play.package_name)
```

---

### IN-51: `.env.example`'s two store blocks still promise that only the webhook degrades

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `.env.example:123-125` and `.env.example:149-152`

**Issue:** Same defect as WR-50, in the document a deployer actually reads before setting
anything:

- `:123-125` — "Everything except the store notification runs without these: the service
  boots, it logs one `app_store_configuration_absent` warning, and the route fails closed
  as 503".
- `:149-152` — "Everything except the notification runs without these three ... the route
  stays registered in both cases."

Both are now false: `POST /auth/restore-subscription` fails closed on the same settings.
`grep -rn restore .env.example` returns nothing.

**Fix:** In each block, replace "the route" with the two routes by name, e.g. "the webhook
route and the matching arm of `POST /auth/restore-subscription` fail closed as 503".

---

### IN-52: NOTES.txt's ADC paragraph names "every account-creation route" and misses restore

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `k8s/templates/NOTES.txt:40-44`

**Issue:** "Firebase Admin and the Play Developer API both authenticate through ADC, so
with neither set the pod becomes Ready and every account-creation route answers 503".
Restore is not an account-creation route, but it is now the second consumer of the Play
Developer credential (`auth/google_play.py:341-342`), so it answers 503 too. An operator
reading this after `helm install` will not check restore.

**Fix:** "... every account-creation route and the `google_play` arm of
`POST /auth/restore-subscription` answer 503".

---

### IN-53: `httproute-auth.yaml` justifies itself against `llm-routes`, a template deleted three phases ago

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `k8s/templates/httproute-auth.yaml:14`

**Issue:** The comment reads "Under the JWT SecurityPolicy, as app-routes and llm-routes
are." `k8s/templates/httproute-llm.yaml` was removed by commit `918816e`
("fix(37.4): WR-81 delete the duplicate llm-routes that silently outranked app-routes"),
and `security-policy.yaml:11-15` lists exactly two `targetRefs`: `-app-routes` and
`-auth-routes`. The comment cites a resource that does not exist, which is the worst kind
of stale: it reads as a cross-check and is not one.

**Fix:** `# Under the JWT SecurityPolicy, as app-routes is.`

---

### IN-54: `errors.py`'s "no generic 403" note claims two classes at that status; there are fifteen

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `src/nativespeaker/api/errors.py:155`

**Issue:** "No generic 403: neither class at that status is the generic answer." "Neither"
asserts exactly two. Counting `status = 403` in this module today:
`PreAuthIdentityNotAllowed`, `AccountUnavailable` + `HistoricalIdentity` + `BlockedUser`,
`NotLinked`, `UpgradeRefused` + `ProviderTransitionNotAllowed` +
`ProviderAccountAlreadyLinked`, `ProofRejected`, `DeviceGrantExhausted`, `ClaimRefused` +
its six leaves, and — added by this phase — `RestoreProviderUnknown` (`errors.py:586-593`).
The *rule* the comment states is still correct and load-bearing (`class_answering_status`
returns `None` for 403 by design); only the count is wrong, and phase 45 made it wronger.

**Fix:** `# No generic 403: no class at that status declares itself the generic answer.`

---

### IN-55: `Chart.yaml` advertises removed rate limiting and an `appVersion` one minor behind

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `k8s/Chart.yaml:4` and `k8s/Chart.yaml:6`

**Issue:** Two independent staleness defects in the chart's own metadata:

- `:4` — `description: NativeSpeaker API Gateway - Linguistic analysis API with Envoy
  Gateway rate limiting`. `NOTES.txt:26-32` states plainly that the BackendTrafficPolicy
  carrying the only gateway rate limit was removed, and `k8s/templates/` contains no such
  file. `helm search` / `helm show chart` advertises a feature the chart does not install.
- `:6` — `appVersion: "1.5.0"` against `pyproject.toml:3`'s `version = "1.6.0"`. It is
  informational only (`image.tag` is `required` at install, `deployment.yaml:43`), but it
  is the one field a reader treats as "which build does this chart deploy".

**Fix:** Drop "with Envoy Gateway rate limiting" from the description and set
`appVersion: "1.6.0"`.

---

### IN-56: The pod hardening stops one line short of `automountServiceAccountToken: false`

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `k8s/templates/deployment.yaml:17-22`

**Issue:** The pod spec sets `runAsNonRoot`, `runAsUser`, `fsGroup`, `seccompProfile`,
`allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true` and
`capabilities.drop: ["ALL"]` — a deliberate Restricted-PSS posture — but leaves
`automountServiceAccountToken` at its default `true`. No code in `src/` talks to the
Kubernetes API, and GKE Workload Identity resolves through the metadata server rather than
the projected token, so nothing here needs it.

Honest sizing per `AGENTS.md`: impact is low (the default KSA's RBAC is near-empty and the
threat model here is not worth over-engineering for). It is one line, and it is the only
member of the standard hardening set this spec omits.

**Fix:**

```yaml
    spec:
      # Nothing here calls the Kubernetes API, and Workload Identity resolves through the
      # metadata server, so the projected token is a credential with no consumer.
      automountServiceAccountToken: false
```

---

### IN-57: The image ships two Apple root CAs nothing loads

_Reported by reviewer R4 (app wiring + cross-cutting + deployment/config)._

**File:** `Dockerfile:29` (source: `config/certs/`)

**Issue:** `COPY config ./config/` puts `config/certs/AppleIncRootCertificate.cer` and
`config/certs/AppleRootCA-G2.cer` in the runtime image. `config.py:174` pins
`_APPLE_ROOT_CERTIFICATE = Path("certs") / "AppleRootCA-G3.cer"`, and
`lifespan.py:77` passes `root_certificates=[root_bytes]` — a single-element list. A
repo-wide grep for `AppleRootCA-G2` and `AppleIncRootCertificate` outside `.planning/`
returns nothing. They are inert, but a reader inspecting `config/certs/` will reasonably
read the directory as "the trusted set", which it is not — and this is precisely the
directory phase 43 D-10 made load-bearing.

**Fix:** Delete both files, or add a one-line `config/certs/README` naming G3 as the only
loaded root. (Deleting is preferable: `APP_STORE_ROOT_CERTIFICATE_PATH` already exists for
a deployment that needs a different root.)

---

### IN-65: Two assertions restate the fixture the test itself constructed one line earlier

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_restore_proof.py:832`, `tests/unit/test_subscription_attribution.py:840`

Both read:

```python
        session = _CommittingSession(IntegrityError("COMMIT", {}, _Orig(DEFERRED_KEY_VIOLATION)))
        with pytest.raises(IntegrityError) as refused:
            ...
        assert refused.value.orig.sqlstate == DEFERRED_KEY_VIOLATION
```

`_Orig.__init__` stores exactly that string and the session raises exactly that exception, so the
assertion is true by construction and holds for any behaviour of the code under test. The real
claims in both cases are the lines under it (`(commits, rollbacks) == (1, 0)`, `race_warnings ==
[]`, and the `commit_errors` assertion in the sibling case). Delete the line, or replace it with the
claim it is standing in for — that the exception the caller sees is the *same object* the driver
raised and not a re-wrap:

```python
        assert refused.value is session.refusal
```

(with `_CommittingSession` keeping its `_refusal` on a public attribute).

### IN-66: The "no part of the proof reaches the label" case cannot fail

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_restore_proof.py:211-219`

```python
        for segment in proof.split("."):
            assert segment not in refusal.value.stage
            assert segment not in str(refusal.value)
```

Measured on the case's own inputs: the three JWS segments are 2288, 451 and 86 characters, while
`refusal.value.stage` is `'INVALID_APP_IDENTIFIER'` (22 characters) and `str(refusal.value)` is
`'proofrejected at INVALID_APP_IDENTIFIER'` (39). A shorter string can never contain a longer one,
so the assertion passes for every `stage` drawn from `VerificationStatus.name` regardless of what
the adapter does. The claim worth keeping is the closed-set one the neighbouring case already makes
(`set(stages) <= {status.name for status in VerificationStatus}`, line 208); assert that here too,
or test a substring the label could plausibly leak — e.g. the decoded `bundleId` and
`originalTransactionId`, which are short enough to fit:

```python
        assert "com.example.someone-else" not in str(refusal.value)
        assert ORIGINAL_TRANSACTION_ID not in str(refusal.value)
        assert refusal.value.stage in {status.name for status in VerificationStatus}
```

### IN-67: A stale docstring undercounts the 403 family by fifteen classes

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_error_registry.py:193-195`

```python
    def test_403_has_no_answering_class(self):
        """Three classes now sit at 403 and none of them is the generic answer."""
```

Eighteen classes carry `status == 403` today (`AccountUnavailable`, `ActiveGrantOutsideItsTerm`,
`BlockedUser`, `ClaimRefused`, `ClaimRefusedUnderLock`, `ClaimantNotAnonymous`,
`ClaimantNotRegistered`, `DeviceGrantExhausted`, `FreeGrantAlreadyConsumed`, `HistoricalIdentity`,
`NotLinked`, `OtherActiveGrantHeld`, `PreAuthIdentityNotAllowed`, `ProofRejected`,
`ProviderAccountAlreadyLinked`, `ProviderTransitionNotAllowed`, `RestoreProviderUnknown`,
`UpgradeRefused`), and phase 45 added the last of them. The same file already enumerates the five
403 *codes* at lines 318-321, so the prose contradicts a literal twenty lines below it. Restate it
without a count: `"""No class at 403 is the generic answer, whatever else sits there."""`

### IN-68: The restore module re-introduces the `credential=None` shadowing its sibling fixed with a sentinel

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_restore_proof.py:222-228`

```python
def _play_reader(handler, *, products: dict[str, str] | None = None,
                 credential=None) -> PlayDeveloperSubscriptions:
    return PlayDeveloperSubscriptions(
        credential=_FakeCredential() if credential is None else credential, ...)
```

`tests/unit/test_google_play_notifications.py:130-138` carries the same helper with a comment
naming this exact defect — *"A sentinel and not `None`: the default substitutes the fake, so `None`
was unsayable here"* — and a `_UNSET` object. The restore copy drops the sentinel, so
`_play_reader(handler, credential=None)` silently means "use the fake", and the unconfigured case
has to hand-build the class instead (lines 442-445). Import the sibling's helper, or copy its
sentinel.

### IN-69: The restore-proof length bound's control holds with exactly zero margin, against a guessed constant

_Reported by reviewer R5 (unit test suite)._

**File:** `tests/unit/test_models.py:344`, `tests/unit/test_models.py:373-380`

`REALISTIC_RESTORE_PROOF = 4 * 1024` is documented as arithmetic rather than a measurement, and the
control is `assert limit >= 2 * realistic`, i.e. `8192 >= 8192` — true only at the boundary, so any
future re-estimate of the constant fails a test about the *bound* rather than about the estimate.
The suite already mints a real ES256 signed transaction with a three-certificate `x5c`
(`unit.test_app_store_notifications._mint`); it measures 2828 characters on the throwaway chain
(header 2288, `x5c` entries 580/588/504). Apple's own certificates are larger than the throwaway
ones, so 4096 is a defensible upper estimate — but say so against the measurement rather than
leaving the control at zero margin, e.g. record the minted length as the documented lower bound and
loosen the control to `assert limit > realistic`.

### IN-83: `REFUSED_BODY` is a `str`, and three comments call it bytes

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/e2e/test_restore_subscription.py:63-64`, `662-663`, `685-686`

Line 63 reads *"The same body as bytes, so the gate refusal is compared on the wire and not after
parsing"*, but line 64 defines `REFUSED_BODY = '{"code":"operation_not_allowed"}'` — a `str`. Both
use sites assert `refused.text == REFUSED_BODY` under a comment that says *"Compared as bytes"*
(662, and 685 without the comment). The module's other three refusal constants
(`PROOF_REJECTED_BODY:67`, `RESTORE_NOT_FOUND_BODY:70`, `TRANSFER_REJECTED_BODY:73`) are `bytes`
compared with `.content`, so the module contradicts itself.

The comparison is still exact, so no coverage is lost today. Fix: make it bytes and use `.content`
like its three siblings.

```python
REFUSED_BODY = b'{"code":"operation_not_allowed"}'
...
assert refused.content == REFUSED_BODY
```

(`tests/e2e/test_claim_anonymous_grant.py:141` and `test_claim_registered_grant.py:40` carry the
same `str` constant, but without the misleading comment.)

---

### IN-84: The D-10 cap tests compare a live clock against the request's captured instant

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/e2e/test_restore_subscription.py:868-875`, used at `931`, `976`, `989`

`_this_month()` and `_earlier_month()` read `datetime.now(UTC)` at assertion time, while the
service derives the month from the request's `evaluated_at`
(`services/restore.py:126-129`). A run straddling a UTC month boundary between the seed and the
assertion makes `test_a_stored_month_equal_to_this_one_answers_the_conflict_and_writes_nothing`
allow the move and `test_a_stored_month_earlier_than_this_one_is_allowed_and_moves` compute the
wrong expectation. The window is milliseconds once a month, but the module already has the tool
for it.

Fix: take `pinned_evaluation_instant` in the three cap cases and derive the month from it:

```python
def _month_of(instant: datetime) -> date:
    return instant.astimezone(UTC).date().replace(day=1)
```

---

### IN-85: Two `restore_bound_user_id is None` assertions sit on branches that run no owner UPDATE

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/e2e/test_restore_subscription.py:1002-1003`, `1040`

I mutation-proved the other five copies are live: adding
`values["restore_bound_user_id"] = destination` to `claim_subscription_owner` turns three e2e cases
and five schema cases red. But `test_a_same_account_repeat_leaves_the_transfer_month_unwritten`
(1026-1040) and the capped case at 1002-1003 stayed green, because neither branch runs the owner
UPDATE at all — `TestTheSameAccountBranchRunsNoOwnerUpdate` (628-647) proves precisely that. Those
two copies are vacuous by construction.

Not harmful; drop them or leave them. Do **not** drop the other five: they are the only guard on
the migration's own promise (`migrations/20260818_01_initial-release.sql:141-143`).

---

### IN-86: `test_the_two_refusals_answer_bodies_equal_to_each_other` is a strict subset of the case below it

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/e2e/test_restore_subscription.py:570-594` versus `596-626`

Both seed an unentitled row and a token-mismatch row, drive both, and assert the bodies are
byte-equal and that nothing was written. The second adds the third arm and pins the literal body,
so it subsumes the first entirely, including its `_row_counts == (0, 0)` tail. One duplicated
seed-and-drive block for no additional claim.

Fix: delete 570-594.

---

### IN-87: The refusal-log assertion reads one field, so a log line carrying the artifact would pass

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/e2e/test_restore_subscription.py:807-809`

```python
assert [(event, fields["stage"]) for event, fields in refusal_records.entries] == [...]
```

Only `stage` is read. `restore_proof` is a bearer credential — anyone reading the log could restore
the subscription onto their own account — and the route comment at
`src/nativespeaker/api/routers/auth.py:172` promises it is *"never logged"*. Today it cannot leak
(`ProofRejected` carries no proof and `validation_error_handler` logs only `loc` and `type`), so
this is a strengthening, not a defect.

Fix: compare the whole record, which costs nothing and makes the promise executable.

```python
assert refusal_records.entries == [
    *(("proof_rejected", {"stage": stage}) for stage in APPLE_REJECTION_STAGES),
    ("proof_rejected", {"stage": PLAY_REJECTION_STAGE})]
```

---

### IN-88: Two spellings of the same status comparison in one module

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/schema/test_restore_race.py:407` versus `551`

Line 407 uses `str(row[1]) == "active"`; the module's own `active_grants` helper at 551 uses
`row[1] == "active"` on the same column of the same query. Use the helper at 407.

---

### IN-89: One blank line between two module-level classes

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/e2e/test_restore_subscription.py:627-628`

Removing `test_a_repeat_of_a_proof_whose_term_has_passed_is_refused_and_changes_nothing` in this
phase left a single blank line between the end of `TestTheTwoRefusalsOfTheRestoreNotFoundFamily`
and the `@pytest.mark.asyncio` decorator of `TestTheSameAccountBranchRunsNoOwnerUpdate`. Every
other class boundary in the file has two. `ruff check tests/e2e tests/schema` passes, so this is
cosmetic only.

---

### IN-90: The inventory asserts index predicates for six named indexes, and exact sets for everything else

_Reported by reviewer R6 (e2e + schema test suites)._

**File:** `tests/schema/test_inventory.py:158-172`, `434-443`

`TestIndexPredicates` is parametrized over `EXPECTED_INDEX_PREDICATES`, which names six indexes.
Every other axis of this suite is an exact-set assertion — the enum set, the table set, the index
name set, the whole column set with types and defaults, the index-key set, the foreign-key set. The
predicate axis is the one that is not: a `WHERE` clause added to, say, `ix_subscriptions_user_id`
or `ix_store_purchases_provider_identity_value` is invisible to the entire file. I verified the
34 cases pass against the live migration and that `EXPECTED_COLUMNS`, `EXPECTED_INDEX_KEYS` and
`EXPECTED_FK_DELETE_ACTIONS` agree with `migrations/20260818_01_initial-release.sql` line by line —
this is the one gap.

Fix: make it an exact map like its neighbours, with `None` for the unpredicated indexes.

```python
async def test_every_index_predicate_matches_capture(self, conn):
    await conn.execute(f"SET search_path TO {PINNED_SEARCH_PATH}")
    actual = {r["index_name"]: r["predicate"] for r in await conn.fetch(INDEXES)}
    differing = {n: (p, EXPECTED_INDEX_PREDICATES.get(n)) for n, p in actual.items()
                 if EXPECTED_INDEX_PREDICATES.get(n) != p}
    assert not differing, f"index predicates differ (found, expected): {differing}"
```

(`EXPECTED_INDEX_PREDICATES` would grow the remaining 35 `None` entries.)

## Per-reviewer summaries

### R1 — services + routers

**Part-report header and scope note:**

# Phase 45 — Code Review Report, part 1 (services + routers)

**Depth:** standard
**Scope:** the twelve files listed above. Cross-file reads for context only:
`crud/subscriptions.py`, `crud/grants.py`, `crud/chats.py`, `auth/app_store.py`,
`auth/google_play.py`, `auth/store_notifications.py`, `app/dependencies.py`,
`app/error_handlers.py`, `errors.py`, `schemas/*`, `resilience.py`,
`migrations/20260818_01_initial-release.sql`.

**Summary:**


The restore transaction is careful and its lock order, its race arms and its refusal vocabulary all
hold up under reading. One real defect survives the phase-37.5 CR-25 fix: the term a restore
attaches is read from a grant that is only *marked* active, with no test that its term is still
open, so a paying subscriber whose renewal notification has not arrived is refused on the one route
that exists to give access back. That is proven below with a probe against the production code, and
the same customer is proven to get `200` once the grant row happens to be marked `expired` — the
answer depends on webhook timing, not on what the customer holds.

The rest is sound. `services/subscriptions.py`, `services/auth.py`, `services/quota.py` and
`services/sync.py` were traced against their crud and their indexes and produced no new defect.
Two thin routers do more work per request than they use, and `/auth/sync` still lacks the
`no-store` header its three sibling `SyncResponse` routes set — a phase-38 finding that was never
fixed and never dropped.

Ten candidate findings were dropped against ratified decisions; they are listed with citations.

### R2 — crud + tables + migration SQL

**Part-report header and scope note:**

# Phase 45 (R2): crud + tables + migration — Code Review Report

**Reviewed:** 2026-09-10
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found
**Finding id block:** 20-34

**Summary:**


I traced every focus area named in the brief against the file text and, where the reasoning
depended on library behaviour, against the installed library source.

What I verified and could **not** break:

- **Lock ordering.** `GrantsDB._active_grants_of_statement` (`crud/grants.py:47-54`) emits one
  `SELECT ... WHERE user_id IN (...) AND status='active' ORDER BY id ASC FOR UPDATE`. PostgreSQL
  places `LockRows` above `Sort`, so both accounts of a move are taken in one global ascending
  id order, and `lock_grants_of` (`crud/subscriptions.py:101-112`) then walks that same list for
  tier two. No path in `src/` takes a usage row before a grant row, and the only user-row lock
  tier (`IdentitiesDB.lock_identity_and_user`) is reached from `services/auth.py:334` alone, which
  touches no grant row — so there is no cycle with `activate_registered_account_grant`, whose flush
  takes an `core.external_identities` row lock *after* the grant tier.
- **The D-08 CAS.** `_claim_owner_statement` (`crud/subscriptions.py:54-65`) restates both nullable
  columns with `IS NOT DISTINCT FROM`, and PostgreSQL re-evaluates that predicate against the
  latest committed row version under READ COMMITTED, so a rival that adopted or moved the row in
  the window drives `rowcount` to 0. I checked the two ways a CAS is usually defeated and neither
  applies: (a) `synchronize_session=False` means the ORM emits exactly one statement and reads
  nothing back; (b) the id-keyed ORM `UPDATE` that follows in `upsert_subscription:249-252` runs
  *under the row lock the CAS statement itself holds*, so it cannot overwrite a rival. `sqlmodel`'s
  `AsyncSession.exec` has an explicit `UpdateBase` overload returning `CursorResult`
  (`.venv/.../sqlmodel/ext/asyncio/session.py:56-66`), so `.rowcount` is the real matched count.
- **23505-only classification.** The driver is `asyncpg` (`config.py:39`), and SQLAlchemy's asyncpg
  shim sets `translated_error.pgcode = translated_error.sqlstate` at
  `.venv/.../dialects/postgresql/asyncpg.py:794-795`. So `getattr(violation.orig, "sqlstate", None)`
  in `crud/violations.py:13` reads a real value on this driver; a CHECK (23514), a NOT NULL (23502)
  and a deferred FK (23503) all classify as "not a race" and re-raise. Correct.
- **DDL ↔ model agreement.** I walked all twelve mapped tables against the migration column by
  column. Nullability, enum type names and schemas, `DEFAULT 'active'` on both `status` columns,
  the two unmapped `GENERATED ALWAYS AS ... STORED` columns, the PK-less
  `core.store_purchase_tokens` and its ORM-only composite key, and the `date` mapping of
  `last_cross_account_transfer_month` (which the D-10 cap compares) all agree. Every enum member's
  `.name` equals its `.value`, which matters because SQLAlchemy's `Enum(PyEnum)` persists `.name`.
- **D-09.** `upsert_subscription:202` (`owner = stored.user_id if stored.user_id is not None else
  user_id`) keeps a set owner, and `services/subscriptions.py:161` passes `subscription.user_id`
  (not the token-resolved user) to the grant writer, so the failure D-09 describes — owner flipped
  back to A, nothing of B's expired, a 23505 on every retry — is genuinely closed.
- **`ix_access_grants_one_per_subscription` as backstop.** I constructed the one path that reaches
  it through restore (same account, owns the row, holds no active grant, two concurrent restores
  with `may_reactivate=True`): `lock_grants_of` locks nothing, no CAS runs because
  `owner_read == destination`, both insert, one takes 23505 and answers `lost_race`. Exactly one
  active grant survives. Correct.
- **`write_subscription_grant` supersede/replay predicates.** `held` is correctly narrowed to
  `grant.user_id == user_id` (so the old owner's row on a move is never read as a replay), `mine`
  is correctly narrowed to the destination's own `subscription` rows (so the old owner's counter is
  never inherited and a free tier's count never reaches the paid counter), and `superseded` reaches
  the old owner's row for *this* subscription only. All three are right.

What I could break is below: one wrong `WriteOutcome` label that contradicts the convention four
lines later in the same function, and one fail-closed raise whose blast radius crosses accounts.

### R3 — auth adapters + schemas

**Part-report header and scope note:**

# Phase 45: Code Review Report — Part 3 (auth adapters + schemas)

**Reviewed:** 2026-09-10T01:50:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

**Summary:**


### Verdict on the prior CR-01 (Play path escape) — **genuinely closed**

The instruction was to re-prove, not to take `513ef70` on trust. I drove the production
`PlayDeveloperSubscriptions.read_for_restore` over an `httpx.MockTransport` recorder with a fake
credential and read `request.url.raw_path` for every input the prior finding named, plus the ones
a fixer would worry about next:

```
token='.'                                  -> ProofRejected(play_token_gone)   raw_path=<no request sent>
token='..'                                 -> ProofRejected(play_token_gone)   raw_path=<no request sent>
token='....'                               -> ProofRejected(play_token_gone)   raw_path=<no request sent>
token='a/../..'                            -> read OK   /androidpublisher/v3/applications/com.example.app/purchases/subscriptionsv2/tokens/a%2F..%2F..
token='a/..'                               -> read OK   .../tokens/a%2F..
token='a/../../../../v3/applications/evil/edits'
                                           -> read OK   .../tokens/a%2F..%2F..%2F..%2F..%2Fv3%2Fapplications%2Fevil%2Fedits
token='%2e%2e'                             -> read OK   .../tokens/%252e%252e
token='..%2f..'                            -> read OK   .../tokens/..%252f..
token='.%2e'                               -> read OK   .../tokens/.%252e
```

The escape is closed, and it is closed for the right reason on both halves:

1. `_names_one_path_segment` (`google_play.py:185-187`) refuses a token that is dots alone, so `.`
   and `..` never reach the transport at all — the two inputs that previously rewrote the path.
2. For every mixed token, `quote(value, safe="")` percent-encodes `/` as `%2F`, and httpx
   **preserves** that encoding rather than decoding it before dot-segment removal. Because no real
   `/` survives, httpx sees exactly one path segment and there is no dot segment to delete. Every
   `raw_path` above still starts with `.../subscriptionsv2/tokens/`.

I also probed the header/query escape hatches that a path-confinement fix commonly misses:
`'a\r\nX-Evil: 1'` → `a%0D%0AX-Evil%3A%201` (no CRLF injection), `'a?q=1'` → `a%3Fq%3D1` with
`url.query == b""`, `'a#frag'` → `a%23frag`, `'a\x00b'` → `a%00b`, `'ü'` → `%C3%BC`. All confined.
The same guards are present on the webhook `read()` path (`google_play.py:289-293`), which answers
`None` rather than raising — verified by the same probe.

**CR-01 needs no further work.** Do not re-open it.

### What I did find

Two real defects, both in the Play restore read's *error classification* — the area D-05 names but
does not fully enumerate. Neither is a security hole; both make the route answer the wrong HTTP
contract for a condition that is not what the answer claims. Six Info items on comment accuracy,
brittle string coupling, and an asymmetric bound.

I found no defect in the Apple local-verification path (`app_store.py::verify_transaction`), in
`store_notifications.py`, in `jwt_verifier.py`'s decode contract, in `devicecheck.py`, in
`firebase.py`, or in the `RestoreRequest` contract. `RestoreRequest` (`schemas/auth.py:41-47`)
matches D-01 exactly: `provider` and `restore_proof`, both required, both `min_length=1`,
`provider` a plain `str`.

I filed no Critical. The one candidate that looked like one — a stolen Apple JWS restoring onto a
thief's account when its `appAccountToken` resolves to nobody — is ratified by D-03/D-10 and is in
the Dropped section.

### R4 — app wiring + cross-cutting + deployment/config

**Part-report header and scope note:**

# Phase 45 (R4): Code Review Report — app wiring, cross-cutting modules, deployment/config

**Depth:** standard
**Finding id block:** 50-64

**Summary:**


The end-to-end wiring of `POST /auth/restore-subscription` is sound, and I could not
break it:

- `main.py:48` includes `auth_router`; `routers/auth.py:155` registers the path once.
- The handler declares `Depends(get_linked_identity)` (`routers/auth.py:163`), which
  narrows to a linked caller through `dependencies.py:98-105`. `tests/unit/test_app_wiring.py:74`
  and `:85` pin that narrowing by name, and the whole wiring suite passes.
- Both store singletons the restore service reads (`app.state.app_store_notifications`,
  `app.state.play_subscriptions`) are set **unconditionally** in `lifespan.py:220` and
  `:244`, so the route set does not change with configuration and the degraded case is a
  503, not a missing route. `get_restore_service` (`dependencies.py:183-190`) reads exactly
  those two plus `google_play.package_name`.
- The two new codes are registered: `restore_not_found` and `restore_transfer_rejected`
  are in the `ErrorCode` literal (`errors.py:32-33`), carried by `RestoreRefused`
  (`errors.py:562-567`, 404) and `RestoreTransferRejected` (`errors.py:596-601`, 409).
  Neither declares `answers_framework_status`, so `class_answering_status` still resolves
  404 to `NotFound` and 409 to `ChallengeRequired` — I checked `vars(cls)` semantics at
  `errors.py:73` and the framework mapping is not shadowed. `main.py:34,36` already declare
  404 and 409 in the shared `responses` block.
- `app_error_handler` (`error_handlers.py:33-50`) covers every new leaf through the single
  `AppError` registration, and `camel_to_snake` yields correct event names for all four new
  classes.
- The access-log line (`logs.py:94-107`) is written for the new path (it is not in
  `_EXCLUDED_PATHS`) and lands at WARNING for the 403/404/409 refusals.
- Gateway: `httproute-auth.yaml:20-24` matches `/auth` by `PathPrefix`, so the new path is
  routed, and `security-policy.yaml:14-15` targets `-auth-routes`, so the JWT filter applies.
  No manifest change was needed and none is missing.
- `uv.lock:871` declares `version = "1.6.0"`, matching `pyproject.toml:3`, so
  `uv sync --frozen` in the Dockerfile will not fail.

No new configuration key is required by this phase, and none is missing from `config.py`,
`config/config.yaml` or `.env.example`.

What I did find is a consistent class of defect: **phase 45 gave two existing configuration
blocks a second consumer and updated none of the operator-facing text that names their
consumers.** A deployment that is App-Store- or Play-unconfigured now silently breaks a
user-facing route, and every boot warning, every `.env.example` block and the chart's
NOTES.txt still say only "the webhook". That is WR-50, plus IN-51/IN-52. One genuine
availability defect (WR-51) is a boot-time-only ADC read whose sibling already got the
fix it lacks.

---

### R5 — unit test suite

**Part-report header and scope note:**

# Phase 45 — Code Review Report, part 5 (unit test suite)

**Reviewed:** 2026-09-10
**Depth:** standard
**Files Reviewed:** 50
**Status:** issues_found

**Summary:**


The suite is unusually disciplined: nearly every claim carries a named control, the stand-ins run
the real writer where they can (`_UpsertSession`, `_LockStubSession`), and the log-vocabulary and
error-tree files are exhaustive rather than sampled. I mutation-probed the phase-45 claims that
matter and most of them are load-bearing: the status re-read under the grant locks
(`restore.py:94-96`), the tier re-read (`97-99`), the `starts_at` clamp (`70`), the insert-only
create branch (`113-123`), and both URL escapes in `google_play.py:416-417` each fail their tests
when removed.

Three real holes remain, all of the "the test does not reach or does not control what it claims"
kind:

1. The grant-tier lock statement phase 45 added (`_active_grants_of_statement`) is asserted by
   nothing — the one stub that runs it throws the statement away, so `FOR UPDATE` and the ascending
   id order can both be deleted with 284 unit tests still green.
2. `test_restore_proof.py` states that no assertion in it depends on the wall clock; every bare
   `_transaction()` it mints derives its dates from `datetime.now(UTC)`, not from the captured
   instant, so two cases get their `active` outcome by accident.
3. Restore's `core.store_purchases` write is executed by no unit test at all — the method can be
   renamed to a nonexistent one and 163 tests still pass — and the e2e only counts the rows, never
   their columns.

Every mutation probe below was reverted in the same tool call that made it; `restore.py`,
`grants.py` and `google_play.py` are at HEAD. (Concurrent siblings left probes of their own in
`crud/subscriptions.py` and `app/dependencies.py` during the run; those are not mine and I did not
touch them.)

### R6 — e2e + schema test suites

**Part-report header and scope note:**

# Phase 45 (part 6): e2e and schema test suites

**Depth:** standard
**Status:** issues_found

**Summary:**


No Critical finding. The phase-45 assertions I attacked hardest hold up under mutation: the
`evaluated_at == term_ends_at` boundary, both sides of the D-10 same-month cap equality, the
23505-at-commit branch, `restore_proof`'s `min_length`, and — contrary to the brief's suspicion —
every `restore_bound_user_id is None` assertion on a branch that runs the owner UPDATE. All were
mutation-proved live (see **Dropped by ratified decision** and the per-finding proofs).

What I did find are three holes where the suite claims coverage it does not have, all three
mutation-proved by breaking the production line and watching the whole repo stay green:

1. Restore is the only writer that locks two accounts' grant rows, and nothing pins the statement
   it uses. Reverting it to two per-user statements in list order — a real deadlock — passes 2258
   tests (WR-80).
2. The assertion that the Play restore read is made with the *configured* package name was deleted
   in this phase's re-review and replaced by the `evaluated_at` assertion. Hard-coding a wrong
   package name now passes every e2e and unit test (WR-81).
3. The adoption-with-creation lost race (`insert_subscription` → 23505) has no test on any tier,
   and `TestTheUniqueIndexArbitratesWhereTheOwnerUpdateCannot`'s docstring calls its own case "the
   one path that reaches it", which is false (WR-82).

Every mutation was reverted in the same tool call; `git status --porcelain` is empty.

## Dropped by ratified decision

### R1 — services + routers

| # | Candidate | Dropped under |
|---|---|---|
| 1 | `restore.py:212-214` verifies the Apple proof only against the vendored root and never calls `Get All Subscription Statuses`, so a subscription refunded after the transaction was signed still earns a grant until the next webhook | **45 D-04** (and 44 D-13); a documented FLAGGED CONFLICT against brief steps 8 and 17 |
| 2 | `routers/auth.py:161-165` puts `/auth/restore-subscription` behind `get_linked_identity` only, so an anonymous account may restore a paid subscription | **45 D-03**; FLAGGED CONFLICT against the brief's "active, **registered** account" and its `restore_destination_anonymous` result |
| 3 | The route runs no in-app rate limit, so one caller can drive one live Play `subscriptionsv2.get` per attempt | **45-CONTEXT § Carried forward** (35 D-05, 41 D-20, 42 D-16) and `AGENTS.md` — Envoy Gateway rate-limits by IP/user/URL |
| 4 | `services/subscriptions.py:117-122` raises `InternalError` for an entitled status with an absent, inverted or closed term, so a self-contradicting store payload is a permanent 500 the store redelivers until retention | **SHARED-INVARIANTS § Fail-closed defaults**, applied explicitly at `.planning/phases/37.5-…/37.5-REVIEW-FIX.md:600-622` — both proposed remedies (derive the status from the dates; converge on redelivery) are forbidden by that clause verbatim |
| 5 | `restore.py:63` never updates `core.subscriptions.status` from the proof, so a row a stale webhook left `expired` refuses a proof the store signed as `active` | **45 D-06** — canonical state belongs to the webhooks, one rule for both providers |
| 6 | `restore.py:220-221` `raise RestoreProviderUnknown` is unreachable — `routers/auth.py:167` rejects an unserved store name first | **45 D-01** puts the gate in the handler; the service leaf is the fail-closed backstop the enum fork requires. Not a defect |
| 7 | The route writes no `audit.auth_events` row and `AuthOperation` gains no `restore_subscription` label | **45-CONTEXT § Carried forward** (37.1 D-01, 38 D-03, 40 D-11) and **D-13** ("no label is needed") |
| 8 | Nothing detects one store's artifact presented from the other platform, and no `native_claim_platform` comparison runs | **45 D-02**; FLAGGED CONFLICT against `10-restore-subscription.md` § Request contract |
| 9 | `restore.py:158-170` mints a new grant id and a fresh `core.user_monthly_usage` row instead of reactivating the same row with `ends_at IS NULL` | **45 D-07**; FLAGGED CONFLICT against the brief's adoption grant and its UPDATE reactivation |
| 10 | `restore.py:57-59` takes no `FOR UPDATE` on `core.subscriptions`; the owner change is a conditional UPDATE behind the grant locks | **45 D-08** (and 43 D-16); FLAGGED CONFLICT against brief step 9(a) |

### R2 — crud + tables + migration SQL

Each of these was a candidate finding I traced to a real behaviour and then dropped, because a
ratified decision or a binding spec line settles it. Recorded so a later reviewer does not re-file
them.

- **A store-driven resubscribe leaves a paying customer with no entitlement until they press
  "restore"** (`crud/subscriptions.py:365-368`, the `may_reactivate=False` arm). Ratified:
  `specs/auth-refactor-phases/08-webhook-app-store.md:42` (*"ingestion never reactivates the grant
  … the entitled-subscription/expired-grant state persists until restore"*), 43 D-18, and the
  landed fix `604f837`.
- **A free grant's `monthly_used` is not carried into the paid grant that supersedes it**
  (`crud/subscriptions.py:411-412`). Ratified: `08-webhook-app-store.md:38` and the landed fix
  `f9c7ce0` (43 WR-60).
- **A move strands the destination's *other* live paid subscription** — `superseded` at
  `crud/subscriptions.py:372-374` ends every grant the destination holds. Ratified: 37.2 WR-43 was
  fixed *and then reverted* by `9f3e3c5` ("keep the ratified supersession set, pinned by
  T-45-08-01/02"), and `tests/schema/test_restore_race.py::TestTheDestinationStillLosesEverythingItHeld`
  pins it.
- **The old owner loses all access at the instant of a move, and its already-spent lifetime free
  slot is never reopened** (`ix_access_grants_one_free_grant_per_user_source` carries no status
  predicate, `migrations/…:267-270`). Ratified: 45 D-10 (*"the old owner loses access at that
  moment"*) and the DDL's own stated rule.
- **No `FOR UPDATE` on `core.subscriptions`, so a webhook committing `expired` between restore's
  under-the-locks re-read and its COMMIT produces a deferred-FK 23503 and a 500.** Ratified: 45 D-08
  (*"No `FOR UPDATE` on `core.subscriptions` (43 D-16 stands)"*) and
  `tests/schema/test_restore_race.py::TestTheDeferredForeignKeysFireAtCommitAndNotAtAFlush`.
- **The CAS loser on a contested move answers `restore_not_found` rather than
  `restore_transfer_rejected`.** Ratified: 45 D-08 leaves the shape open (*"answer as the new state
  earns … otherwise the refusal"*) and D-11 defines both codes as terminal 4xx.
- **`restore_bound_user_id` is mapped (`tables/purchases.py:61`) but written by nothing.** Ratified:
  45 D-10 (*"`restore_bound_user_id` is not written and stays NULL"*), and dropping the column is an
  open Deferred Idea in 45-CONTEXT, not a defect.
- **`transfer_month=None` in `claim_subscription_owner` conflates "do not write" with "write NULL".**
  Ratified: 45 D-10 (*"adoption … does not write the month"*); no caller ever wants to write NULL,
  and `crud/subscriptions.py:269-271` states the rule inline.
- **No in-app rate limit bounds the Play read per restore attempt.** Ratified: Phase 35 D-05, 41
  D-20, 42 D-16 and `AGENTS.md` (Envoy Gateway limits by IP/user/URL).
- **No test asserts each Python enum's members equal its `core.*` type's labels.** Ratified: an
  explicit Deferred Idea in 45-CONTEXT § Deferred. (Note for the record: it is currently safe only
  because every member's `.name` equals its `.value` — SQLAlchemy's `Enum(PyEnum)` persists `.name`,
  not `.value`.)

---

_Reviewed: 2026-09-10_
_Reviewer: Claude (gsd-code-reviewer), R2 — crud + tables + migration SQL_
_Depth: standard_
_Finding id block: 20-34_

### R3 — auth adapters + schemas

### An Apple subscriber inside a billing grace period cannot restore — DROPPED

`app_store.py:178-179` sets `grace_period_expires_at=None` on every Apple restore, so
`term_end_for` (`store_notifications.py:58-63`) returns `None` whenever the deciding status is
`grace_period`, and `services/restore.py` refuses with `restore_not_found`. I confirmed the case is
reachable: `core.subscriptions` (`tables/purchases.py:46-65`) carries **no** term column, so an
unowned Apple row written at `grace_period` by a `DID_FAIL_TO_RENEW` webhook (43 D-17's
"unattributed case restore links later") has no grant recording a term and no row recording one
either.

Dropped on three grounds, all of them prior and explicit:

- **45-CONTEXT § Deferred:** *"The renewal-info JWS as a second Apple proof field — would make grace
  and billing retry visible on restore. **Not this phase.**"* — the only remedy that reads the term
  from the proof.
- **45-CONTEXT D-14 / D-04 Claude's Discretion:** *"Grace and billing retry are not visible without
  the renewal-info JWS; do not ask the app for it this phase."* The alternative remedy — persisting
  the grace window — is a migration, and D-14 keeps the spec and schema out of this phase.
- **45-07-PLAN.md:22 and 45-07-SUMMARY.md:48** designed the refusal deliberately, chose it over the
  `ends_at IS NULL` unbounded grant it replaced, and pinned it with
  `tests/e2e/test_restore_subscription.py::TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_a_stored_grace_row_and_an_apple_proof_attaches_nothing`.

It is already on record as **prior 45-REVIEW.md WR-01**, whose fallback remedy ("log a closed-set
event on this branch so support can see it") is now satisfied: the current
`RestoreSubscriptionNotEntitled(cause="term_closed")` reaches the log through
`ProviderLookupError.log_fields` (`errors.py:427-431`). Nothing further is in scope for phase 45.

### A stolen Apple signed transaction restores onto the thief's account — DROPPED

`verify_transaction` returns `attribution_token=transaction.appAccountToken`, and
`services/restore.py` only refuses when that token *resolves to a different user*. A proof whose
`appAccountToken` is absent or unknown to `core.store_purchase_tokens` passes unchecked.

Dropped under **D-03**: *"a stolen proof is a risk of restore in any form and anonymous adds none"*,
and **D-10**, which caps the exposure at one move per subscription per UTC month and calls it *"an
accepted loss on a sub-$5 subscription"*. AGENTS.md agrees: the product's value is not great enough
to justify engineering against theft.

### No live "Get All Subscription Statuses" call on the Apple restore path — DROPPED

Ratified by **D-04**, with the refund blind spot named as an accepted consequence and the
reversibility recorded. Not re-filed, per the review instruction.

### The Apple chain is verified with `enable_online_checks=False`, so the chain's validity window is read from the payload's own `signedDate` — DROPPED

`appstoreserverlibrary/signed_data_verifier.py:170-172` sets `effective_date` from the *unverified*
`signedDate` when online checks are off, and skips OCSP entirely. The behaviour is ratified by
**D-04** ("verified locally, never live"), the flag is set in `app/lifespan.py:79` (outside this
reviewer's assigned files), and the practical consequence — replay of a genuinely signed old proof —
is already bounded by `_transaction_status` requiring `expiresDate > evaluated_at`.

### `UnmappedStoreProduct` answering `internal_error` on the restore path — DROPPED

Ratified verbatim by **D-11**: *"`internal_error` for an unmapped store product
(`UnmappedStoreProduct`, an operator error as on the webhooks)"*. WR-35 above is careful to preserve
this arm unchanged.

### No in-app rate limiting on the Play call per restore attempt — DROPPED

Ratified by **Phase 35 D-05**, carried forward in 45-CONTEXT § "Carried forward — do NOT rebuild",
and by the project context: Envoy Gateway rate-limits by IP, user and URL.

---

_Reviewed: 2026-09-10T01:50:00Z_
_Reviewer: R3 — auth adapters + request/response schemas_
_Depth: standard_
_Finding ID block: 35-49 (used WR-35, WR-36, IN-35..IN-40)_

### R4 — app wiring + cross-cutting + deployment/config

Candidate findings I formed and then dropped, each against the decision that settles it:

- **"`/auth/restore-subscription` admits anonymous callers; the destination should be a
  registered account."** Dropped — **45 D-03** ("Anonymous accounts may restore. The route
  sits behind `get_linked_identity` and reads no provider column.
  `restore_destination_anonymous` is not built."). `dependencies.py:98-105` is exactly what
  D-03 specifies, and the flagged conflict against the brief is recorded there.
- **"Nothing bounds the Play Developer API call per restore attempt — one caller can spend
  the daily quota."** Dropped — **45 D-13 carried-forward** ("No rate limiting, no provider
  budgets, no coalescing, no proof fingerprints (Phase 35 D-05). The Play call per restore
  attempt is bounded by nothing but the proof check before it; record the exposure ...") and
  the project brief (Envoy Gateway rate-limits by IP/user/URL).
- **"The restore route writes no success log line and no audit row, so a subscription
  transfer leaves no trail."** Dropped — **45 D-13 carried-forward** ("No
  `audit.auth_events` row, no operation enum value, no audit result value (37.1 D-01,
  38 D-03, 40 D-11)" and "No success log line (Phase 38 D-02);
  `RequestLoggingMiddleware` writes the one request line"). `logs.py:94-107` is that line.
- **"`app/main.py` has no route registry / category metadata, so route auth is asserted
  nowhere structural."** Dropped — **37.1 D-06/D-10**, carried forward by 45 ("No route
  registry, no `Category`, no `RouteMetadata`, no named-verifier table ... the route joins
  `routers/auth.py` under `get_linked_identity`"). `tests/unit/test_app_wiring.py` is the
  ratified substitute and it does cover the new path.
- **"The Apple restore proof is verified only locally; a refunded subscription is granted
  until the next webhook."** Dropped — **45 D-04** ("Apple is verified locally, never live
  ... Accepted blind spot"). `lifespan.py:79` (`enable_online_checks=False`) is the
  ratified configuration.
- **"No in-app JWT check on `/auth/restore-subscription` beyond the shared barrier."**
  Dropped — project brief (Envoy Gateway authenticates by JWT) plus
  `security-policy.yaml:14-15`, which already targets `-auth-routes`.
- **"`config/config.yaml` and the chart declare no `restore` block."** Dropped — not a
  defect: phase 45's domain section lists no new configuration, and the route reuses
  `app_store.*` and `google_play.*` verbatim (45 D-04, D-05, and 44 D-18 for
  `package_name`).

---

_Reviewed: 2026-09-10_
_Reviewer: Claude (gsd-code-reviewer), part 4 of 6_
_Depth: standard_
_Finding id block: 50-64 (used CR: none, WR-50..WR-51, IN-50..IN-57)_

### R5 — unit test suite

* **"No unit test asserts the account set passed to `lock_grants_of`."** Mutation-proved
  (`services/restore.py:89`, `accounts = [destination] if current_owner is None else
  [current_owner, destination]` → `accounts = [destination]`, 103 unit tests still green; every
  stub in the suite signs `lock_grants_of(self, user_ids)` and discards the argument). Dropped:
  **45-CONTEXT § Claude's Discretion — "Test shape, on the 43 D-24 / 44 model"** ratifies that the
  move cases are measured in `tests/schema` on real PostgreSQL, and
  `tests/schema/test_restore_race.py::TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves` and
  `::TestTheDestinationStillLosesEverythingItHeld` do catch this mutation. WR-65 above is the part
  that survives, because it is the lock statement's *shape*, which no schema case observes.
* **"`restore_bound_user_id` is asserted but never written."** The assertions live only in
  `tests/e2e/` and `tests/schema/`, outside my scope, and they assert `is None` — which is exactly
  what **D-10** ("`restore_bound_user_id` is not written and stays NULL") requires of them. No unit
  file references the column.
* **"The transfer cap, the attribution mismatch and the unserved-store 403 have no unit test of
  their raising path."** Dropped for the same ratified test-shape reason: **D-10**'s cap is listed
  by name among the `tests/schema` cases, and the surface gate is an e2e route concern
  (`tests/e2e/test_restore_subscription.py::TestTheSurfaceGateIsTheStoreNameAndTheProof`). The
  classes themselves are pinned at unit level by `test_rejection_vocabulary.py:432-513`.

---

_Reviewed: 2026-09-10_
_Reviewer: Claude (gsd-code-reviewer), R5 — unit test suite_
_Depth: standard_

### R6 — e2e + schema test suites

- **"Assertions on `restore_bound_user_id` are assertions on a dead field."** Dropped on two
  grounds. D-10 states the column "is not written and stays NULL", and
  `migrations/20260818_01_initial-release.sql:141-143` names these very e2e cases as its guard.
  More decisively, the claim is false as stated: I added
  `values["restore_bound_user_id"] = destination` to
  `SubscriptionsDB.claim_subscription_owner` and three e2e cases plus five schema cases turned red.
  Only the two copies in IN-85 are vacuous.
- **The surface gate does not detect an Apple artifact presented from an Android device, and does
  not read `native_claim_platform`.** D-02, explicitly, with the conflict against
  `10-restore-subscription.md` § Request contract already flagged.
- **Anonymous accounts may restore; no `restore_destination_anonymous` refusal exists or is
  tested.** D-03, with the conflict against the brief already flagged.
- **The Apple proof is never checked against live App Store state, so a refunded subscription can
  earn a grant.** D-04, recorded as an accepted blind spot; also re-declined in § Deferred Ideas.
- **The Play read is made once per restore attempt with no rate limit, budget or coalescing.**
  Phase 35 D-05, carried forward in 45-CONTEXT § "Carried forward" and § Deferred Ideas; closes
  with the v2.1 gateway contract.
- **A restore never writes an `audit.auth_events` row, so a move between accounts leaves no audit
  trail.** 37.1 D-01 / 38 D-03 / 40 D-11, carried forward; D-13 answers the Phase 40 forward flag
  with "no label is needed".
- **`core.subscriptions` is read twice without `FOR UPDATE`.** 43 D-16, restated by D-08:
  "No `FOR UPDATE` on `core.subscriptions`", with the conflict against brief step 9(a) flagged.
- **A stolen proof can reach a second account.** D-10 accepts this explicitly as a product choice
  capped at one move per UTC month, and `AGENTS.md` rules out over-engineering for that threat
  model.

---

_Reviewer: R6 — e2e and schema test suites_
_Depth: standard. Every central claim mutation-proved; tree left clean._

## Notes for the orchestrator

### R1 — services + routers

- **No source file was modified by this reviewer.** Four throwaway probes were written under
  `tests/e2e/` and removed in the same tool call each time; `git status --porcelain` was clean after
  the first three.
- After the fourth probe run, `git status --porcelain` reported
  `M src/nativespeaker/api/crud/subscriptions.py` — a one-line edit adding
  `"restore_bound_user_id": destination` to `claim_subscription_owner`'s `values` dict. That is a
  **concurrent sibling reviewer's probe, not mine and not in my assigned scope.** It was left
  untouched. It is orthogonal to the CR-01 probes (which ran before it appeared and touched only
  `access_grants`), so no result above depends on it. If it is still present when the orchestrator
  runs, it must be reverted before any commit.

---

_Reviewer: R1 (services + routers), gsd-code-reviewer_
_Depth: standard_
_Finding id block: 01-19_
