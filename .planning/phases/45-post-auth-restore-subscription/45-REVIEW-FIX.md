---
phase: 45-post-auth-restore-subscription
fixed_at: 2026-09-10
review_path: .planning/phases/45-post-auth-restore-subscription/45-REVIEW.md
fix_scope: critical_warning
iteration: 1
findings_in_scope: 14
fixed: 14
skipped: 0
status: all_fixed
commits:
  - f53dd9a — CR-01 — fix(45): CR-01 refuse only when no recorded or signed term is still open
  - 83efb4c — WR-01 — fix(45): WR-01 record the charged answer both late checks discard
  - d0b0905 — WR-20 — fix(45): WR-20 report the lapse guard's no-op write as replayed
  - 879d87f — WR-21 — fix(45): WR-21 refuse an absent usage row only for the counted account
  - ed03376 — WR-35 — fix(45): WR-35 answer an unreadable Play line item count as the restore path's 503
  - b8f687c — WR-36 — fix(45): WR-36 answer a Play 400 as a rejected proof, not as retryable
  - fbf3095 — WR-50 — fix(45): WR-50 name the restore route in the two store boot warnings (with IN-51, IN-52)
  - 56a5dc2 — WR-51 — fix(45): WR-51 rebuild the Play credential a boot blip could not read
  - d37ca78 — WR-65 — fix(45): WR-65 assert the grant-tier lock, its ascending order and its one statement
  - 35d9b88 — WR-66 — fix(45): WR-66 date the Apple restore payloads against the captured instant
  - 529fe1f — WR-67 — fix(45): WR-67 assert the purchase row the first restore of an unrecorded pair writes
  - e24cec5 — WR-80 — fix(45): WR-80 pin the restore move's grant lock to one ascending statement
  - d6157a5 — WR-81 — fix(45): WR-81 assert the Play restore read uses the configured application name
  - fc0cca2 — WR-82 — fix(45): WR-82 cover the create branch's lost race and correct the backstop docstring
verification:
  ruff: clean
  unit: 1920 passed (baseline 1898)
  schema: 291 passed (baseline 282)
  e2e: 362 passed (baseline 360)
  ty: 0 diagnostics
---

# Phase 45: Code Review Fix Report

**Fix scope:** Critical + Warning (`--fix` without `--all`) — 14 findings, 14 fixed, 0 skipped.  
**Review:** `.planning/phases/45-post-auth-restore-subscription/45-REVIEW.md` (commit `5a3892c`)  
**Branch:** `gsd/v2.0-authentication-entitlements`

The 14 in-scope findings were applied by three `gsd-code-fixer` agents run STRICTLY SEQUENTIALLY — never in parallel, because concurrent fixers share one git index. Batch A took the source layer, batch B the adapters and app wiring, batch C the test layer last, so its tests were written against the already-fixed source. One commit per finding, that finding's files only.

| Commit | Finding | Subject |
| --- | --- | --- |
| `f53dd9a` | CR-01 | refuse only when no recorded or signed term is still open |
| `83efb4c` | WR-01 | record the charged answer both late checks discard |
| `d0b0905` | WR-20 | report the lapse guard's no-op write as replayed |
| `879d87f` | WR-21 | refuse an absent usage row only for the counted account |
| `ed03376` | WR-35 | answer an unreadable Play line item count as the restore path's 503 |
| `b8f687c` | WR-36 | answer a Play 400 as a rejected proof, not as retryable |
| `fbf3095` | WR-50 | name the restore route in the two store boot warnings (with IN-51, IN-52) |
| `56a5dc2` | WR-51 | rebuild the Play credential a boot blip could not read |
| `d37ca78` | WR-65 | assert the grant-tier lock, its ascending order and its one statement |
| `35d9b88` | WR-66 | date the Apple restore payloads against the captured instant |
| `529fe1f` | WR-67 | assert the purchase row the first restore of an unrecorded pair writes |
| `e24cec5` | WR-80 | pin the restore move's grant lock to one ascending statement |
| `d6157a5` | WR-81 | assert the Play restore read uses the configured application name |
| `fc0cca2` | WR-82 | cover the create branch's lost race and correct the backstop docstring |

## Verification after the last commit

Run by the orchestrator, not by a fixer. All five gates green; no suite was allowed to report "deselected".

| Gate | Baseline at `0b0f92b` | After the fixes |
| --- | --- | --- |
| `ruff check src tests` | clean | **clean** |
| `pytest tests/unit` | 1898 passed | **1920 passed** (+22 new cases) |
| `pytest tests/schema -m schema` | 282 passed | **291 passed** (+9 new cases) |
| `pytest tests/e2e -m e2e` | 360 passed | **362 passed** (+2 new cases) |
| `ty check src` | 0 diagnostics | **0 diagnostics** |

No test was weakened. Every added case was mutation-proved: the production line it guards was broken, the case was confirmed red, and the probe was reverted in the same tool call.

## Batch A — source layer — restore service, chats service, subscriptions crud

# Phase 45 code review fix report — batch A

Four findings, all fixed. No skips. The review was factually correct on all four
cited call sites; two corrections to its supporting claims are on record below.

## CR-01 — a grant marked active past its term refuses a current proof

**Commit:** `f53dd9a`
**Files:** `src/nativespeaker/api/services/restore.py`,
`tests/e2e/test_restore_subscription.py`

**Root cause.** `_active_grants_of_statement` (`crud/grants.py:47-54`) selects on
`status == 'active'` and carries no time window, and its docstring says so. So a
grant whose `ends_at` has already passed stays in `marked_active`. `restore.py:108`
read `recorded_term[0]` whenever the list was non-empty, then tested that single
value for `None` and for `<= evaluated_at`. A closed recorded term therefore
short-circuited the proof, and the restore answered `404 restore_not_found` with
`cause=term_closed`. Between a paid term ending and the store's renewal
notification arriving, that is the ordinary state of the row: nothing sweeps it,
and only the ingestion path flips the mark.

**Change.** The recorded term still comes first, but it is now read as the answer
only while it is open; the signed proof is the next candidate:

```python
term_ends_at = next((end for end in (*recorded_term, term_end_for(status, proof))
                     if end is not None and end > self.evaluated_at), None)
if term_ends_at is None:
    raise RestoreSubscriptionNotEntitled(cause="term_closed")
```

`term_end_for` is a two-branch attribute read (`auth/store_notifications.py:58-63`),
so evaluating it eagerly inside the tuple costs nothing and raises nothing.

**Why no ratified decision blocks it.** D-06 binds the *status* to the canonical
row and forbids restore rewriting it. The status decision is untouched. D-07 keeps
the term as "the paid period's end (grace window during grace)", which is exactly
what the proof carries.

**Behaviour that is unchanged, checked case by case.**
- Recorded term open: picked first, so the stale-proof-against-a-live-grant case
  still answers `replayed`
  (`test_a_dead_proof_refuses_where_nothing_records_the_term_and_replays_where_one_does`).
- No recorded term: falls to the proof exactly as before, so a grace row with no
  grant still refuses (an Apple proof carries no grace window).
- Boundary: `> self.evaluated_at`, so a term ending at the captured instant is still
  closed.

**Pin.** New parametrized e2e case
`TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_a_closed_recorded_term_never_outranks_a_current_proof_under_either_mark`,
running both arms the report tabulated: the grant left marked `active` and the
grant a webhook already marked `expired`. Both now answer 200 with the proof's
term. **Mutation-proved:** with the old `recorded_term[0] if recorded_term else ...`
hunk restored, the `active` arm fails and the `expired` arm passes — the exact
asymmetry CR-01 named.

**Correction on record.** The report's suggested patch asserts the two arms are
otherwise identical. They are not, and the test states the real difference: the
`active` arm's stale row is in `marked_active`, so `write_subscription_grant`
supersedes it and `mine` carries this month's count forward (4 in the test); the
`expired` arm's row is outside the locked set, so `carried` is 0 and the new term
starts the month at zero. That is pre-existing behaviour of the writer, not
something this fix introduced, and the parametrized case pins both numbers rather
than pretending they agree.

## WR-01 — two charged writes discard an answer with no log line

**Commit:** `83efb4c`
**Files:** `src/nativespeaker/api/services/chats.py`, `tests/unit/test_services.py`

**Root cause.** Both late re-reads run after `quota_service.charge` has committed a
credit in its own session and after the provider round trip.
`ChatHistoryLimitError` extends `InvalidRequest` and `InvalidChatError` extends
`NotFound`; both bases set `log_level = None` (`errors.py:81-86`, `:96-101`), so
`app_error_handler` writes nothing (`app/error_handlers.py:34`). The only line that
names a charged request is `charged_write_failed`, which sits below both raises in
`_commit_the_charged_write`. The case was therefore indistinguishable in the logs
from a client mistake that cost nothing.

**Change.** One `logger.warning("charged_answer_discarded", ...)` before each raise,
with the same closed-set fields `charged_write_failed` already uses
(`user_id`, `branch`). No refund is implied; the policy in `services/quota.py`
stands.

**Pin.** New `TestADiscardedAnswerTheCallerPaidForIsFindable` in
`tests/unit/test_services.py`, mirroring the sibling `TestAChargedWriteThatFailsIsFindable`:
one case per branch driving the *second* read to fail (`count_chats` side effect
`[0, chats_limit]`; `get_chat` side effect `[chat, None]`), plus a control asserting
an ordinary chat writes no line.

## WR-20 — the lapse guard reported a no-op write as `applied`

**Commit:** `d0b0905`
**Files:** `src/nativespeaker/api/crud/subscriptions.py`,
`tests/unit/test_subscription_grant_write.py`

**Root cause.** `WriteOutcome`'s own docstring (`crud/subscriptions.py:34`) defines
`applied` as "it changed a row" and `replayed` as "it changed nothing". The CR-60
lapse guard ends no grant and inserts none, and returned `applied`. Four lines
below, the `not entitled` arm gets the same distinction right.

**Change.** The guard returns `WriteOutcome.replayed`.

**Blast radius, checked.** `grep -rn "WriteOutcome\." src/` outside the writer
returns four hits, all of them `is not WriteOutcome.lost_race` in
`SubscriptionsService._settle` and `RestoreService._settle`. Nothing in `src/`
reads `applied` versus `replayed`, so both commits and every response body are
byte-identical.

**Test updated to the correct expectation, not weakened.**
`TestALapsedTermIsNeverBroughtBackByIngestion::test_an_entitled_notification_after_a_lapse_inserts_nothing`
and `::test_the_winning_subscriptions_live_grant_is_left_alone` pinned the old
value; both now assert `replayed` alongside the unchanged `session.added == []`,
which is the assertion that carries the real claim. The two `applied` controls in
the same class (a first purchase and a restore reactivation) are untouched, because
those writes do insert.

## WR-21 — a broken usage row in the source account denied the destination its restore

**Commit:** `879d87f`
**Files:** `src/nativespeaker/api/crud/subscriptions.py`,
`src/nativespeaker/api/services/restore.py`,
`tests/unit/test_subscription_grant_write.py`, `tests/unit/test_restore_proof.py`

**Root cause.** `lock_grants_of` raised `MissingUsageRowError` for every active
grant of every account handed to it, and `RestoreService.restore` hands it
`[current_owner, destination]` on a move. The invariant the raise protects is the
one `write_subscription_grant` states at `crud/subscriptions.py:411-412`: `mine`
excludes `grant.user_id != user_id`, so only the destination's own subscription
rows have their counter read. The source account's row is locked and superseded but
its `monthly_used` is never read, so the raise was strictly wider than the rule it
enforced — and a break in a stranger's account became a permanent 500 for a paying
customer, with no signal naming the account at fault.

**Change.** `lock_grants_of` takes `counted_for` and refuses only for that account;
every other account's break is recorded and refuses nothing.

```python
if usage is None:
    if grant.user_id == counted_for:
        raise MissingUsageRowError(grant.id)
    logger.error("source_grant_without_usage_row", grant_id=str(grant.id),
                 user_id=str(grant.user_id))
```

The lock itself is unchanged, so SHARED-INVARIANTS § Locks and D-08 hold: the same
rows are locked, in the same one ascending statement, with the usage tier second.

**Deviation from the report's suggested patch, deliberate.** The report proposed
`counted_for: UUID | None = None`, defaulting to today's raise-for-everything. I
made it a **required** keyword argument instead. An optional parameter whose default
is the wrong behaviour is a defect waiting for the next caller; there are exactly two
production call sites (`lock_grants` passes `counted_for=user_id`, restore passes
`counted_for=destination`) and both now state which account's counter the write under
the locks carries. The log line also carries `user_id`, which the report's version
omitted — without it the record names a grant id and nothing an operator can look up
the broken account by, which was half of the reported harm.

**Pins.** Two new cases in `TestTheSecondLockTierRefusesAnAbsentUsageRow`: the
source account's break is locked, recorded and not raised; and the control that the
destination's own break still raises and writes no line. The stub logger in that
module recorded only `warning`, so it was renamed `_LogSpy` / `_writer_records` and
given `error`; the three existing assertions over its list are unchanged. The three
`lock_grants_of` doubles in `tests/unit/test_restore_proof.py` grew the keyword.

## Verification

All five gates were run in the **main checkout** (`/home/init/native-speaker/ns-api-gateway`,
branch `gsd/v2.0-authentication-entitlements`), not in a worktree, after the last
commit `879d87f`. The numbers are reproducible from the tree as committed.

| gate | baseline `5a3892c` | after batch A |
| --- | --- | --- |
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1898 passed | 1903 passed (+5 new) |
| `pytest tests/schema -m schema` | 282 passed | 282 passed |
| `pytest tests/e2e -m e2e` | 360 passed | 362 passed (+2 new) |
| `ty check src` | clean | clean |

`git status --short` is empty. No failure was attributed to a pre-existing cause,
because there was none: every suite is green.

## Batch B — adapters and app wiring — Google Play adapter, lifespan

# Phase 45 code review fixes — batch B

## WR-35 — a Play answer this build cannot read is a 500 on one branch and a 503 on every other

**Root cause.** `_product_of` is shared verbatim by `read()` (webhook) and `read_for_restore()`
(restore). It raises a plain `InternalError` for a line-item count other than one, and
`UnmappedStoreProduct` — which subclasses `InternalError` (`errors.py:275`) — for an unmapped
product. `read_for_restore` classified the transport and the parse itself but let the helper's
refusal travel out unclassified, so the restore route answered `500 internal_error` for a body
shape it cannot read while answering `503 verification_temporarily_unavailable` for every other
unreadable 2xx. The review is factually correct on all counts, verified against the classes.

**What changed** (`src/nativespeaker/api/auth/google_play.py`). The `_product_of` call in
`read_for_restore` is wrapped: `UnmappedStoreProduct` is re-raised by name (D-11 keeps it a 500 on
both paths), and the remaining `InternalError` becomes `Unavailable(stage=RESTORE_UNPARSEABLE_STAGE)`
— the same answer the unparseable body already earns. `read()` is byte-identical, so Pub/Sub still
gets its 500 and its redelivery. The stale comment at the head of `read_for_restore`, which said the
refusal was "never [classified] by a caught base class", now states what the code does.

**Test.** `test_the_restore_read_refuses_the_same_shape` pinned the old 500; it is now
`test_the_restore_read_refuses_it_as_a_body_it_cannot_read` and asserts `(stage, status) ==
(play_restore_unparseable, 503)` plus the unchanged `google_play_unexpected_line_item_count`
operator line. `test_restore_proof.py`'s existing `UnmappedStoreProduct` case
(`assert not isinstance(failure.value, Unavailable)`) pins the preserved D-11 arm.

## WR-36 — a Play 400 is a terminal condition reported as retryable

**Root cause.** `read_for_restore` peeled 404/410 off as `proof_rejected` and swept every other
non-2xx into `Unavailable`, on the stated premise that "a 4xx is a credential or scope an operator
repairs". That premise holds for 401 and 403 only. Play answers 400 for a purchase token that does
not parse and for one that does not name the addressed `packageName` — the caller's own proof, which
no later attempt fixes. A junk `restore_proof` therefore bought a billed `androidpublisher` call and
a `verification_temporarily_unavailable` telling a well-behaved client to retry forever.

**What changed** (`src/nativespeaker/api/auth/google_play.py`). A new terminal arm above the general
non-2xx branch: `_UNUSABLE_TOKEN_STATUS = 400` raises `ProofRejected(stage=
RESTORE_TOKEN_UNUSABLE_STAGE)` (`"play_restore_token_unusable"`). 401/403/429/5xx keep the 503 and
their `cause` words. Its own stage rather than `play_token_gone`, because "Play cannot read this
token" is a different support reading from "this token is gone".

**Decision check.** This is inside D-11 rather than against it: D-11 lists *package mismatch* among
the `proof_rejected` stages, and D-05 enumerates 404/410 and transport failures and says nothing
about 400. `.planning/REQUIREMENTS.md:511` open question (3) records that D-11's "package mismatch"
stage did not exist in the code; it now does. REQUIREMENTS.md is not edited here — that is the
orchestrator's amendment to make, and it is only a record either way.

**Test.** `test_every_other_non_2xx_status_is_temporarily_unavailable` drops its `400` parameter and
a new `test_a_token_play_cannot_read_is_a_rejected_proof` asserts `(stage, status) ==
(play_restore_token_unusable, 403)` and that the stage differs from the gone-token one.

## WR-50 — the two boot warnings name only the webhook routes (with IN-51 and IN-52)

**Root cause.** Both `consequence=` strings were written when `config.app_store.*` fed one route and
`config.google_play.*` fed one route. Phase 45 added a second consumer to each: verified by reading
the path, `dependencies.py:188-190` → `RestoreService` → `AppStoreNotifications.verify_transaction`
(`app_store.py:153-155`, `Unavailable(stage="app_store_verify")` when `_verifier is None`) and →
`PlayDeveloperSubscriptions.read_for_restore` (`Unavailable(stage=RESTORE_UNCONFIGURED_STAGE)` on the
same conditions the warning fires for). So a supported "webhooks off" deployment silently refuses
every "Restore purchases" tap, and the one line an operator greps names the webhook alone.

**What changed.** Both `consequence=` strings in `src/nativespeaker/api/app/lifespan.py` name
`POST /auth/restore-subscription` and its arm alongside the webhook route. IN-51 and IN-52 are the
same sentence in the two operator-facing documents, so they are in this commit and not their own:
`.env.example`'s two block headers and their two "everything except the notification runs" paragraphs
now name both routes and state plainly that a user tapping "Restore purchases" is refused; and
`k8s/templates/NOTES.txt`'s ADC paragraph adds the `google_play` arm of the restore route to "every
account-creation route".

**One correction to the review's text.** The Apple warning also fires for an empty product map, and
in that sub-case the restore route answers `500 internal_error` (`UnmappedStoreProduct`, D-11) rather
than 503. The wording committed says "refuses every apple restore" and names no status, so it is true
of both sub-cases; the review's proposed string was not copied verbatim for that reason.

## WR-51 — a transient ADC failure at boot disables Google restore and RTDN for the pod's life

**D-14 was read first, as instructed, and it does not settle this case.** 44 D-14 says: *"An absent
credential logs a warning at boot and the route answers 503, the shape of
`firebase_admin_credential_absent` and 43 D-02."* That is the **absent** case, and it is preserved
exactly by this fix — an unconfigured pod still logs `google_play_configuration_absent` at boot and
still answers 503 on every call, because the rebuild reads the same absent environment and answers
`None` again. D-14 decides nothing about a `RefreshError`/`TransportError` from a metadata server
that answered badly, so the finding stands. Not skipped.

**Root cause.** `_play_credential()` caught the whole `GoogleAuthError` family and returned the same
`None` for a transient failure as for absence; `lifespan.py` then froze that `None` into
`PlayDeveloperSubscriptions._credential`, which had no rebuild path. Both entry points raise
`Unavailable` on `self._credential is None` forever, so a ~2 s metadata-server blip during a cold
start cost every RTDN delivery and every `google_play` restore on that pod until a human restarted
it, with `/health/ready` at 200 throughout.

**What changed.**

- `PlayDeveloperSubscriptions` gains the seam its neighbour `PubSubPushTokens` already has:
  `build`, `rebuild_interval_seconds` (new module constant
  `PLAY_CREDENTIAL_REBUILD_INTERVAL_SECONDS = 30.0`), an `asyncio.Lock` and a monotonic floor. The
  new `_credential_in_hand()` rebuilds once off the loop through `run_in_threadpool`, re-reads under
  the lock, and stamps the floor before the read. `read()` and `read_for_restore()` call it in place
  of their `self._credential is None` test; both refusals keep their existing stages.
- `lifespan.py` passes `build=_play_credential`.
- `_play_credential()` now splits `DefaultCredentialsError` (absence — silent, D-14's boot warning
  covers it) from the rest of the family, which logs `play_credential_warm_up_failed` naming the two
  affected routes and stating that the next call retries without a restart. This is the second half
  of the same root cause: the two failures had become indistinguishable, and the boot line for a
  correctly configured pod said "configuration absent".

**Tests.** Seven cases in `tests/unit/test_google_play_notifications.py`
(`TestACredentialBootCouldNotReadIsRebuiltRatherThanCachedForThePodsLife`): the restore read and the
webhook read both recover; the rebuilt credential is read once and kept; an environment still
supplying none is the same 503 with the same stage; a failed rebuild is not retried inside the
interval; eight concurrent callers share one rebuild; the interval elapsing still recovers; and a
pod wired with no builder behaves exactly as before. Four cases in `tests/unit/test_config.py` pin
the split log line and its absent-credential control.

**Mutation-proved, not assumed.** With `build = self._build` replaced by `build = None`, five of the
seven fail and the two controls pass. With `async with self._rebuild_lock` replaced by `if True`,
`test_one_burst_of_callers_shares_a_single_rebuild` fails alone. Both probes were reverted from the
file, not from git.

**Ratchet.** `tests/unit/test_auth_package_shape.py`'s recorded shape moves from `(8, 25, 69)` to
`(8, 25, 70)` for the one new method, with the note the file's own convention requires.

## Verification

Run after the last commit (`56a5dc2`), from `/home/init/native-speaker/ns-api-gateway`:

| gate | result | baseline at `879d87f` |
| --- | --- | --- |
| `ruff check src tests` | All checks passed | clean |
| `pytest tests/unit` | 1914 passed | 1903 passed |
| `pytest tests/schema -m schema` | 282 passed | 282 passed |
| `pytest tests/e2e -m e2e` | 362 passed | 362 passed |
| `ty check src` | All checks passed | clean |

The unit count moves by +11: four new cases for WR-51's log split (three parameters plus one
control), seven for the rebuild seam. WR-35 and WR-36 are net zero (one case rewritten; one
parameter dropped and one case added). `git status --short` is clean and the branch is unchanged.

## Batch C — test layer — unit, schema and e2e coverage

# Phase 45 code review fix report — batch C

Six findings, six fixes, no skips. Every added or changed test was mutation-proved: the
production line it claims to guard was broken, the test was run and confirmed red, and the probe
was reverted in the same tool call. Every probe below was reverted; `git diff src/` was empty
after each one and the tree is clean.

## WR-65 — the grant-tier lock statement is asserted by nothing

**Root cause.** `_LockStubSession.exec` in `tests/unit/test_subscription_grant_write.py` took the
statement and discarded it (`# noqa: ARG002`), so the only test driving
`SubscriptionsDB.lock_grants_of` measured the answer and the read *count*. The lock, the ascending
order and the one-statement-for-two-accounts property all live in the statement text and in no
answer, so all three were unobserved at the unit tier.

**Changed** (`tests/unit/test_subscription_grant_write.py` only):
- `_LockStubSession` keeps every statement in `self.statements`.
- Added `_compiled` (the `postgresql` dialect helper `test_quota_resolver.py:125-127` already
  uses) and `_locked_accounts`, which reads the postcompile `IN` list out of the bound params —
  the compiled text renders it only as `__[POSTCOMPILE_user_id_1]`.
- New `TestTheGrantTierLockIsOneAscendingStatement`, three cases.

`_locked_accounts` asserts the **set** `{OLD_OWNER, DESTINATION}`, not the review's suggested list
`[OLD_OWNER, DESTINATION]`. The order of the ids inside the `IN` list is not the lock order —
`ORDER BY id ASC` is — so a list assertion would pin caller order, which is not an invariant.

**Mutation probes.**
1. Dropped `.order_by(col(AccessGrant.id).asc())` from `_active_grants_of_statement`
   (`crud/grants.py:52-54`) **and** `.with_for_update()` from `lock_active_grants_of`
   (`crud/grants.py:129-130`) → `test_the_grant_tier_locks_and_orders_ascending_by_id` FAILED
   (1 failed, 28 passed).
2. Replaced the single statement in `lock_grants_of` with a per-user loop over
   `lock_active_grants` → `test_both_accounts_are_taken_in_one_statement` FAILED, plus 3 others
   (4 failed, 25 passed).
3. Dropped `.with_for_update()` from `GrantsDB.lock_usage` → `test_the_usage_tier_locks_too`
   FAILED (1 failed, 28 passed).

**Correction on record.** The review states "a lost `ORDER BY` … is observable by no test at any
level". That is true only of the unit tier. At the schema tier
`tests/schema/test_grant_locks.py` already catches it through the shared builder: dropping the
`ORDER BY` reddens `TestTheRegisteredWriterAddsNoThirdLockTier` (2 cases) and
`TestTheSubscriptionWriterAddsNoThirdLockTier` (1 case), because
`_active_grants_statement` delegates to `_active_grants_of_statement`. The genuinely unobserved
property was the **restore's** two-account single statement, which is WR-80.

## WR-66 — the module declared a captured instant it did not have

**Root cause.** `tests/unit/test_restore_proof.py:67` claims "one captured instant for every case
below, so no assertion here depends on the wall clock", but the imported Apple fixture
`_transaction()` (`tests/unit/test_app_store_notifications.py:189-203`) built `purchaseDate` and
`expiresDate` from `datetime.now(UTC)`. Measured on the run day: `EVALUATED_AT` was `2026-06-01`
while the fixture minted `2026-09-10` / `2026-10-10`.

**Changed.**
- `tests/unit/test_app_store_notifications.py`: `_transaction` grows a `now: datetime | None`
  keyword, defaulting to `datetime.now(UTC)` so that module's own cases are untouched.
- `tests/unit/test_restore_proof.py`: the base helper is imported as `_wall_clock_transaction`
  and a module-local `_transaction(**fields)` pins `now=EVALUATED_AT`. This is a root-cause fix
  rather than a call-site sweep: a bare `_transaction()` added to this module later is dated
  against the captured instant by construction, so the declaration cannot go stale again.
- Added two assertions to
  `test_a_transaction_minted_by_the_chain_verifies_and_names_its_subscription`, pinning
  `purchased_at == EVALUATED_AT` and `expires_at == EVALUATED_AT + 30 days`. Without them a
  regression that re-introduces the wall clock passes silently.
- `_build_chain` is untouched: the library checks certificate validity against the real clock,
  as the review notes.

**Mutation probes.**
1. Removed the pin (`_wall_clock_transaction(**fields)`), `EVALUATED_AT` unchanged →
   `test_a_transaction_minted_by_the_chain_verifies_and_names_its_subscription` FAILED.
2. The review's stated failure mode, reproduced exactly. Bumped `EVALUATED_AT` to
   `2027-06-01` (the ordinary maintenance edit): **with** the pin, 79 passed; **without** it,
   `test_grace_period_is_unreachable_from_a_proof_that_carries_no_renewal_payload` FAILED
   alongside the case above — the collapse the review predicted.

## WR-67 — restore's `core.store_purchases` write was executed by no unit test

**Root cause.** Both stand-ins skipped the branch: `_GrantRecorder.read_purchase` returned a row
on purpose, and `_InsertOnlyRecorder` raised `_Stop` at `insert_subscription`. The branch sets
`resolved_token_value`, one half of a DEFERRABLE INITIALLY DEFERRED foreign-key pair — a value set
where no `core.store_purchase_tokens` row exists produces a `23503` at COMMIT, after the grant has
already been written in the same transaction.

**Changed** (`tests/unit/test_restore_proof.py` only):
- `_GrantRecorder` grows `purchase_recorded` (answering `read_purchase` with `None`),
  `insert_purchase`, a `purchases` list and a `destination` attribute.
- `_same_account_restore` grows `purchase_recorded` and `attributed_to_caller`.
- New `_AttributedToTheCaller` purchases stand-in and
  `TestTheFirstRestoreOfAnUnrecordedPurchaseWritesItsRow`: the unbound branch (both key columns
  `None`, `identity_value == ATTRIBUTION_TOKEN`, `store_transaction_id is None`), the bound branch
  (both key columns set), and a control that a recorded purchase is never written twice.

**Mutation probes** (all against `src/nativespeaker/api/services/restore.py`).
1. Renamed the call to `insert_purchase_NEVER_REACHED(` (the review's own dead-line probe) →
   both new cases FAILED. Pre-fix this probe left the file at 82 green; the line is no longer dead.
2. `resolved_token_value=token` unconditionally → the unbound case FAILED.
3. `identity_value=str(uuid7())` unconditionally → the unbound case FAILED.
4. `purchase_user_id=None` unconditionally → the bound case FAILED.

## WR-80 — restore's two-account grant lock was pinned by no test

**Root cause.** `tests/schema/test_grant_locks.py` proves SHARED-INVARIANTS § Locks from emitted
statements for three writers; restore — the one writer D-08 gives two accounts
(`accounts = [current_owner, destination]`) — was absent. A per-user loop in list order passes the
whole repo and deadlocks two simultaneous opposite moves with `40P01`.

**Changed** (`tests/schema/test_grant_locks.py` only):
- New `_restore_move_run` async context manager on the same terms as `_ingestion_run`: two
  committed accounts, a subscription owned by the old one, one held grant plus usage row in each
  account, then `RestoreService.restore` driven as a move under a `before_cursor_execute` recorder.
- `move_statements` fixture and `TestTheRestoreLocksBothAccountsInOneAscendingStatement`, four
  cases: the tier order (`access_grants`, then two `user_monthly_usage`), the ascending order, the
  single grant-tier statement carrying `user_id IN (`, no third tier, and a `writes(...)` control.
- Reuses `_ScriptedAppStore` and `identity_of` from `schema.test_restore_race` rather than
  duplicating them, matching the module's existing cross-import of `_clean` / `_notification`.

**Mutation probes.**
1. The review's per-user loop in `SubscriptionsDB.lock_grants_of` →
   `test_the_move_takes_the_grant_tier_first_then_the_usage_rows` and
   `test_both_accounts_grant_rows_are_taken_in_one_statement` FAILED (2 failed, 43 passed). Only
   the new class caught it, confirming the writer was unobserved.
2. Dropped the `ORDER BY` from `_active_grants_of_statement` →
   `test_the_move_takes_the_grant_tier_first_then_the_usage_rows` FAILED, alongside the three
   pre-existing writer cases (6 failed, 39 passed).

## WR-81 — nothing asserted the Play restore read uses the configured application name

**Root cause.** The assertion at `tests/e2e/test_restore_subscription.py` compared only
`(purchase_token, evaluated_at)`; `FakePlaySubscriptions.read_for_restore` records
`package_name` but nobody read it. A mis-wired `get_restore_service` sends
`.../applications/<wrong>/purchases/...` to Google and every Android restore answers 403.

**Changed** (`tests/e2e/test_restore_subscription.py` only):
`test_a_live_purchase_token_attaches_the_paid_grant_and_the_body_reports_it` now takes
`scripted_google_play` instead of `scripted_play_subscriptions` (the same fake, but it pins
`config.google_play.package_name` to `GOOGLE_PACKAGE_NAME`, which
`scripted_play_subscriptions` does not — the review flagged this), and the tuple gains
`call["package_name"]` against `GOOGLE_PACKAGE_NAME`.

**Mutation probe.** Replaced `package_name=request.app.state.config.google_play.package_name`
in `get_restore_service` with `package_name="com.wrong.package"` → that case FAILED (1 failed,
36 passed). Pre-fix the review measured 2258 green under the same probe.

## WR-82 — the adoption-with-creation lost race was untested and the docstring dismissing it was wrong

**Root cause.** `TestTheUniqueIndexArbitratesWhereTheOwnerUpdateCannot` claimed to cover the
backstop "on the one path that reaches it". Restore has a second 23505 path: on `stored is None`,
`insert_subscription` → `_flush_or_lose` returns `lost_race` when a webhook commits the canonical
row for `(provider, external_id)` between restore's plain read (`restore.py:57`) and the insert.
That is `ix_subscriptions_provider_external_id`, not `ix_access_grants_one_active_per_user`.

**Changed** (`tests/schema/test_restore_race.py` only):
1. Corrected the class docstring: it covers the *grant* backstop where the owner UPDATE refuses
   nobody, and it names the create branch as the other 23505 path.
2. `_RecordingSession` and `run_attempt` gain a `before_first_flush` hook — the existing
   `before_first_update` hook fires at the conditional owner UPDATE, which is *after* the insert,
   so it could not hold at the flush that matters. `_RacingSession` already carried the parameter;
   `_RecordingSession` was passing `None` through to it.
3. New `TestTheCreateBranchLosesToAWebhookThatCommittedFirst`: no committed canonical row, a
   second connection commits one at the insert's first flush, then five cases — the premise
   (`flushes == 1`), `sqlstate == "23505"` with `(integrity_at_flush, integrity_at_commit) ==
   (True, False)`, a 500, exactly one canonical row holding the lifecycle key, and no grant left
   in the account.

**Mutation probe.** Replaced `await self._settle(outcome, proof)` on the create branch with
`_ = outcome` (the review's own probe) → all five new cases went red (29 passed, 5 errors). They
surface as fixture ERRORs rather than assertion failures because, unsettled, the service carries
on inside a PostgreSQL-aborted transaction and the resulting driver exception is not an `AppError`,
so `run_attempt` does not catch it. That is precisely the opaque failure the finding describes,
and an ERROR is red. Pre-fix the review measured 1962 green under the same probe.

**Ratchet repaired in-run.** The new class docstring was four lines and broke the
`tests/schema` docstring bar in `tests/unit/test_docstring_bar.py` (baseline `0`, not a number to
bump — the bar is held at zero). Shortened to three lines and amended into the same commit rather
than raising the baseline.

## Ratified decisions honoured

- **D-08** — every assertion added reads the ascending grant-tier statement, the usage tier behind
  it and the conditional-CAS arbitration. Nothing added asserts or requires `FOR UPDATE` on
  `core.subscriptions`; WR-80's `test_the_move_adds_no_third_lock_tier` asserts the opposite.
- **D-06** — WR-82 covers the adoption-with-creation branch as written; the docstring correction
  names it rather than changing it.
- **D-10** — no assertion added reads `restore_bound_user_id`. WR-80's fixture leaves
  `last_cross_account_transfer_month` NULL at seed and asserts nothing about either column.
- No production source file was changed by this batch. Every probe was reverted;
  `git diff src/` was empty after each.

## Verification (after the last commit)

| Gate | Result | Baseline at `56a5dc2` |
|---|---|---|
| `ruff check src tests` | All checks passed | clean |
| `pytest tests/unit` | **1920 passed** | 1914 (+6: WR-65 ×3, WR-67 ×3) |
| `pytest tests/schema -m schema` | **291 passed** | 282 (+9: WR-80 ×4, WR-82 ×5) |
| `pytest tests/e2e -m e2e` | **362 passed** | 362 (WR-81 changed an existing case) |
| `ty check src` | All checks passed | fully clean |

`git status --short` is empty. `tests/unit/test_auth_package_shape.py`'s method-count ratchet
needed no bump: this batch added no source method.

Gates were run in the **main checkout** at
`/home/init/native-speaker/ns-api-gateway`, on branch `gsd/v2.0-authentication-entitlements`.
No worktree was created (per the instruction that this submodule's `.git` file makes the
workflow's worktree detection wrong), so the numbers above are reproducible from the tree as it
stands.
