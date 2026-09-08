---
phase: 45-post-auth-restore-subscription
reviewed: 2026-09-08T21:42:08Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/services/restore.py
  - tests/e2e/test_restore_subscription.py
  - tests/schema/test_restore_race.py
  - tests/unit/test_restore_proof.py
findings:
  critical: 1
  warning: 4
  info: 7
  total: 12
status: issues_found
---

# Phase 45: Code Review Report (gap closure)

**Reviewed:** 2026-09-08T21:42:08Z
**Depth:** standard
**Files Reviewed:** 7
**Diff base:** 086b84cc682915ce9ee59f77bd32ceba14a9fe9c
**Status:** issues_found

## Summary

Incremental review of the 45-06 / 45-07 / 45-08 gap closure. Verdict on the three prior findings:

| Prior finding | Claimed closed by | Verdict |
| --- | --- | --- |
| CR-01 — unescaped caller value in the Play GET path | 45-06, `auth/google_play.py::_get` | **NOT closed.** `quote(..., safe="")` does not escape `.`, and httpx removes dot segments. A purchase token of `.` or `..` still walks out of the intended resource. Proven empirically through the production class — see CR-01 below. |
| CR-02 — status from the row, `ends_at` from the proof, never reconciled | 45-07, `services/restore.py` | **Closed.** `term_ends_at` is derived once from the pair, checked against the captured instant before any write, and reused verbatim for `ends_at`. The NULL-`ends_at` permanent grant the prior report named is now unreachable. One residual behavioural gap: WR-01. |
| CR-03 — a move expired every active grant of both accounts | 45-08, `crud/subscriptions.py` | **Closed.** `superseded` is now `user_id == user_id or subscription_id == subscription_id`. The webhook path is unchanged (its `marked_active` is single-account). `tests/schema/test_restore_race.py::TestAMoveTakesOnlyTheGrantForTheSubscriptionItMoves` verifies the protective half on real PostgreSQL with the production writer. One residual asymmetry: WR-03. |

The new code is otherwise disciplined: read ordering, lock ordering, the `23505`-only race guard and the single-commit rule all hold. `ruff` is clean and `tests/unit/test_restore_proof.py` passes (39 cases). The findings below concentrate on the one unclosed control, one user-visible behavioural regression the closure introduced, one latent writer asymmetry, and a boundary case the new tests claim to pin but do not.

## Critical Issues

### CR-01: The Play read path is still escapable — a `.` or `..` purchase token leaves the `tokens/` resource

**Resolved:** 513ef70 — see 45-06-SUMMARY.md addendum.

**File:** `src/nativespeaker/api/auth/google_play.py:303-307`
**Also:** `tests/unit/test_restore_proof.py:246-287` (the test that guards this invariant misses the input that breaks it)

The fix escapes both interpolated values with `quote(value, safe="")`. `quote` never escapes the unreserved characters `A-Za-z0-9_.-~`, so `.` survives — and httpx performs RFC 3986 dot-segment removal when it builds the `URL`. The result is that a caller-supplied token still changes the *shape* of the path, not just one segment. Verified by driving the real `PlayDeveloperSubscriptions.read_for_restore` over a recording transport:

```
'..' -> /androidpublisher/v3/applications/com.nativespeaker.app/purchases/subscriptionsv2
'.'  -> /androidpublisher/v3/applications/com.nativespeaker.app/purchases/subscriptionsv2/tokens
```

Both requests are sent with the deployment's own OAuth bearer. The code comment on line 303 ("a caller's token names one segment and never a path") and the docstring claim of T-45-06-01 are therefore both false as written.

The guarding test picks an input that passes rather than the input that breaks the rule: `test_a_token_carrying_path_traversal_names_one_segment_and_no_other_path` (line 249) uses `"a/../../../../v3/applications/evil/edits"`, whose `/` characters *are* escaped, so the traversal is neutralised for the wrong reason. Feeding `".."` to the same test fails its `path.startswith(PLAY_TOKENS_PATH)` assertion.

Impact today is bounded — only one dot-segment removal is possible (the `/` separators inside the token are escaped, so the token is always exactly one segment), so the reachable set is the two paths above, both on the same host, and `androidpublisher` v3 exposes no collection GET there. Both answer 404, which `read_for_restore` maps to `ProofRejected` — the same answer a genuinely gone token earns. But the security control does not hold, the claimed closure is not a closure, and the mitigation rests on Google's API surface rather than on this code.

**Fix** — refuse a token that is nothing but dots, before the request is built, so the token can never be a dot segment:

```python
# `quote` leaves `.` unescaped and httpx removes dot segments, so a dot-only
# token would rewrite the path rather than name a resource in it.
_DOT_ONLY = str.maketrans("", "", ".")


async def _get(self, package_name: str, purchase_token: str) -> httpx.Response:
    """Send one signed read; each entry point classifies a transport failure its own way."""
    if not purchase_token.translate(_DOT_ONLY):
        # No live purchase token is dots alone, so this is a rejected proof and never a read.
        raise ProofRejected(stage=RESTORE_TOKEN_GONE_STAGE)
    ...
```

Guard `package_name` the same way at construction (it is operator config, so an assertion or a config-time check is enough). Then extend `TestThePlayRequestUrlIsConfinedToOneResource` with the input that actually breaks the rule:

```python
@pytest.mark.parametrize("token", [".", "..", "...."])
async def test_a_dot_only_token_never_rewrites_the_path(self, token):
    sent, reader = _capturing_reader()
    with pytest.raises(ProofRejected):
        await reader.read_for_restore(package_name=PACKAGE_NAME, purchase_token=token)
    assert sent == []
```

## Warnings

### WR-01: An Apple subscriber inside a billing grace period can never restore

**File:** `src/nativespeaker/api/services/restore.py:62-67`

`AppStoreNotifications.verify_transaction` sets `grace_period_expires_at=None` unconditionally (`auth/app_store.py:143-145`) — the grace window lives in Apple's renewal payload, which a client-presented signed transaction does not carry. `tests/unit/test_restore_proof.py:137-145` pins that as a fact.

So when the canonical row says `grace_period` (written by a `DID_FAIL_TO_RENEW` webhook), the new check computes `term_ends_at = proof.grace_period_expires_at` → `None` → `RestoreSubscriptionNotEntitled` → 404 `restore_not_found`. A paying subscriber whose card failed, who reinstalls or switches device and taps "Restore Purchases", is refused for the whole grace window (Apple's is up to 16 days). Falling back to `proof.expires_at` would not help either: in grace the paid term has by definition already lapsed, so that value is also in the past.

This contradicts the module's own D-06 premise on line 57 ("a row that exists decides with its own status"): the row says the caller is entitled, and the code then refuses because the *proof* carries no term for that status. The gap closure traded an over-grant (a permanent `ends_at IS NULL` grant, the prior CR-02) for an under-grant, and the e2e case at line 323 encodes the under-grant as intended behaviour without recording it as a known denial.

**Fix** — the only honest source for an Apple grace window is the server's own record of it. Either persist it when the webhook writes `grace_period`:

```sql
ALTER TABLE core.subscriptions ADD COLUMN grace_period_expires_at TIMESTAMPTZ;
```

```python
term_ends_at = (proof.grace_period_expires_at or (None if stored is None
                                                  else stored.grace_period_expires_at)
                if status is SubscriptionStatus.grace_period else proof.expires_at)
```

or, if the column is judged too much for this milestone, accept the denial explicitly: log a closed-set event on this branch (see WR-02) so support can see it, and record it in the phase's known-limitations note.

### WR-02: All three restore refusals are silent server-side

**File:** `src/nativespeaker/api/services/restore.py:59-60, 65-67, 73-75`

`RestoreSubscriptionNotEntitled` is now raised from two different places and `RestoreAttributionMismatch` from a third, and none of them logs anything. The client body is deliberately identical for all three (T-45-05, correctly), which means the server-side log is the *only* place the three can be told apart — and it is empty. `RestoreTransferRejected` (line 83) is silent too. Compare `routers/auth.py:169` and `services/restore.py:191`, which do log with closed-set labels.

The new term check (WR-01) is the branch most likely to refuse a legitimate paying caller, and it is undiagnosable: a support ticket "restore says not found" cannot be resolved from the logs.

**Fix** — one closed-set label per branch, carrying the store name only (never the proof, never the external id):

```python
if status not in ENTITLED_STATUSES:
    logger.info("restore_refused", stage="status_not_entitled", provider=str(proof.provider))
    raise RestoreSubscriptionNotEntitled
...
if term_ends_at is None or term_ends_at <= self.evaluated_at:
    logger.info("restore_refused", stage="no_open_term", provider=str(proof.provider))
    raise RestoreSubscriptionNotEntitled
...
if attributed is not None and attributed != destination:
    logger.info("restore_refused", stage="attribution_mismatch", provider=str(proof.provider))
    raise RestoreAttributionMismatch
```

### WR-03: The replay predicate and the supersede predicate now disagree on a move

**File:** `src/nativespeaker/api/crud/subscriptions.py:240-255`

45-08 widened `superseded` to `grant.user_id == user_id or grant.subscription_id == subscription_id`, but left the replay short-circuit above it keyed on `held`, which is still narrowed to `grant.user_id == user_id`. The two predicates no longer cover the same rows.

Consequence: on a move, if the destination happens to hold an active subscription grant for the moved subscription with a matching `ends_at` and `tier_id`, line 249 returns `WriteOutcome.replayed` — and the source's active grant for that same subscription, which the widened `superseded` set exists to expire, is never touched. `claim_subscription_owner` has already moved the owner column by then (`services/restore.py:107-116`), so the transaction would commit with the row owned by the destination while the source still holds an active grant for it.

I could not construct a reachable sequence to this state (`ix_access_grants_one_active_per_user` allows the destination only one active grant, and every writer that could create the required combination expires it in the same transaction), so this is latent rather than live. But it is a new asymmetry the closure introduced, and it is exactly the invariant CR-03 was about.

**Fix** — ask the replay question over the same set the supersede question is asked over:

```python
# The rows this write is responsible for, asked once and used by both questions below.
owned = [grant for grant in marked_active
         if grant.user_id == user_id or grant.subscription_id == subscription_id]
mine = [grant for grant in owned
        if grant.source is AccessGrantSource.subscription
        and grant.subscription_id == subscription_id
        and grant.user_id == user_id]
if entitled and len(owned) == len(mine) and [grant for grant in mine
                                             if grant.ends_at == ends_at
                                             and grant.tier_id == tier_id]:
    return WriteOutcome.replayed
superseded = owned if entitled else mine
```

### WR-04: The boundary the closure claims to pin is not tested

**File:** `tests/e2e/test_restore_subscription.py:382-400`

`test_a_term_ending_at_the_captured_instant_is_not_open` is named for the `==` case and its docstring calls it "the closed side of the boundary", but it scripts `expires_at = datetime.now(UTC) - timedelta(milliseconds=1)` and the service captures `evaluated_at` strictly later still. The case therefore only exercises `term_ends_at < evaluated_at`. Changing `services/restore.py:65` from `<=` to `<` leaves the whole suite green, so the boundary the gap closure was written to establish is unpinned.

The `==` case is not reachable from e2e (the test cannot know the service's captured instant), but it is trivially reachable from the unit level, where `EVALUATED_AT` is fixed.

**Fix** — add the case in `tests/unit/test_restore_proof.py`, where the instant is a constant:

```python
async def test_a_term_ending_exactly_at_the_captured_instant_is_not_open(self):
    session = _CountingSession()
    store = _ScriptedAppStore(session, replace(_restored(), expires_at=EVALUATED_AT))
    with pytest.raises(RestoreSubscriptionNotEntitled):
        await _service(session, store).restore(identity=_caller(),
                                               provider=PurchaseProvider.apple,
                                               restore_proof="a-signed-transaction")
    assert session.statements == 1
```

(`_CountingSession.exec` raises `_Stop` on the first statement, so the case needs a session that answers `read_subscription`/`read_purchase` with `None` — a two-statement stand-in — for the assertion to reach the term check.) Then rename the e2e case to what it actually measures.

## Info

### IN-01: `write_subscription_grant`'s lock contract in its docstring is now wrong

**File:** `src/nativespeaker/api/crud/subscriptions.py:238` (and `85-92`)

The docstring still says "under locks `lock_grants` took". The restore path calls `lock_grants_of`, which takes a *different* set: it locks usage rows for every marked-active grant rather than for the effective ones only, and it spans two accounts. The wider set is correct (it is a superset, so no lock is lost and the ascending-by-id order still holds), but a reader auditing the lock order is sent to the wrong method. Say "under the locks `lock_grants` or `lock_grants_of` took".

`lock_grants_of`'s own docstring says "for two accounts at once"; restore passes a one-element list on the adoption and same-account branches (`services/restore.py:101`). Say "for one or two accounts".

### IN-02: e2e helpers are defined ~440 lines below their first use

**File:** `tests/e2e/test_restore_subscription.py:795-823`, used at `372`, `380`, `555`, `565`

`_account_snapshot`, `_sync_as`, `_this_month`, `_earlier_month` and `_subscription_snapshot` sit at the bottom of the module but are called by `TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach` and `TestTheTwoRefusalsOfTheRestoreNotFoundFamily` far above. It resolves at call time, so it works, but a reader following the first `_account_snapshot` call has to scan past six classes to find it. Move the shared helpers up with the other module-level helpers (lines 122-199).

### IN-03: `None` is passed where a `PlaySubscriptionSource` is declared

**File:** `tests/schema/test_restore_race.py:232`

`RestoreService(..., play=None, ...)` contradicts the declared type `play: PlaySubscriptionSource` (`services/restore.py:34`). It is safe because every attempt in the file names Apple, but it makes the parameter effectively `PlaySubscriptionSource | None` in practice with no annotation to say so. Either widen the annotation with a comment, or pass a stand-in that raises:

```python
class _PlayIsNeverRead:
    async def read_for_restore(self, **_):
        raise AssertionError("an Apple attempt reached the Play seam")
```

### IN-04: `_proof(expires_at=None)` cannot express "no expiry"

**File:** `tests/e2e/test_restore_subscription.py:100, 111-112`

`expires_at=None` is the "use the default open term" sentinel, so a case that wants a genuinely absent expiry has to reach around the helper with `dataclasses.replace` (line 353). Use a distinct sentinel (`_UNSET = object()`) so the helper can express both, and drop the `replace` import.

### IN-05: Response bodies are asserted as `str` in one place and `bytes` everywhere else

**File:** `tests/e2e/test_restore_subscription.py:61, 605, 628`

`REFUSED_BODY` is a `str` compared against `refused.text`, while `PROOF_REJECTED_BODY`, `RESTORE_NOT_FOUND_BODY` and `TRANSFER_REJECTED_BODY` are `bytes` compared against `.content`. The comments on lines 604 and 627 claim the `.text` comparisons are "as bytes", which they are not. Make all four `bytes`/`.content` so the stated rule holds uniformly.

### IN-06: One move-side assertion is vacuous by construction

**File:** `tests/schema/test_restore_race.py:566-574`

`test_the_source_holds_no_active_grant_for_the_moved_subscription` asserts an absence that the fixture already established: `hold-the-unrelated-one` supersedes every one of the source's active grants (including the one for the moved subscription) before the move runs. The docstring says so. The assertion therefore passes whether or not the move expires anything, and would still pass against the pre-45-08 writer. The genuine source-side coverage is `test_the_source_keeps_its_active_grant_for_the_unrelated_subscription` (line 533) plus the e2e move at `tests/e2e/test_restore_subscription.py:850`. Either delete the vacuous case or re-shape the fixture so the source really does hold an active grant for the moved subscription at move time (which requires dropping the unrelated restore, since `ix_access_grants_one_active_per_user` allows the source only one active row).

### IN-07: `restore_bound_user_id` is dead, and the new tests add five more assertions on it

**File:** `src/nativespeaker/api/tables/purchases.py:61`; `tests/e2e/test_restore_subscription.py:823, 867, 911, 937, 958, 974`; `tests/schema/test_restore_race.py:249`

No code path writes `core.subscriptions.restore_bound_user_id` — D-10 replaced the binding it was for, as the comments say. The column, the model field and the `is None` assertions are all inert. They are cheap regression tripwires for "nothing started writing this column", but they read as coverage of a live invariant. Either add a one-line comment at the model field marking it unwritten and scheduled for removal, or drop the column in the next migration and the assertions with it.

---

_Reviewed: 2026-09-08T21:42:08Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
