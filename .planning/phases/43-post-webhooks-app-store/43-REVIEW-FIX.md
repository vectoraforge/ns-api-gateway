---
phase: 43-post-webhooks-app-store
fixed_at: 2026-09-09
review_path: .planning/phases/43-post-webhooks-app-store/43-REVIEW.md
iteration: 1
fix_scope: critical_warning
findings_in_scope: 24
fixed: 24
skipped: 0
waves: 3
status: all_fixed
verification_ran_in: main checkout (no worktree; this directory is a git submodule)
verification:
  ruff: clean
  unit: 1867 passed (baseline 1831)
  schema: 277 passed (baseline 277)
  e2e: 357 passed (baseline 356)
  ty: 0 diagnostics
---

# Phase 43: Code Review Fix Report

**Scope:** Critical + Warning (no `--all`). 1 Critical and 23 Warnings were in scope; all 24 were
fixed and none were skipped. The 27 Info findings were out of scope by the fix policy.

**Execution:** three fixer waves run STRICTLY SEQUENTIALLY, never in parallel, so no two fixers ever
shared the git index. Wave 1 took CR-60 and WR-01..WR-23, wave 2 took WR-40..WR-82, wave 3 took the
eight test-tier findings WR-100..WR-122.

**Corrections to the review.** The review was wrong or incomplete on ten findings, and each was
fixed at its real root cause rather than as its text described. CR-60's stated remedy was
self-defeating (`services/restore.py` calls the same crud writer, so an unconditional guard would
have blocked the one path allowed to reactivate). WR-04's proposed 503 would have overturned
ratified D-14/D-21. WR-40 was already closed by wave 1's WR-04 fix except for one wording point.
WR-41's suggested `bool` predicate would have cost a `ty` diagnostic. WR-61 named a `case_id` that
does not exist. WR-102's four suggested assertions do not catch its own probe. WR-120's "union over
`REFUSAL_FILES`" mixes the two routes and cannot hold. WR-121's `COMPUTED` marker is not fail-closed.
WR-20's guard had to sit below the `rawStatus is None` arm to preserve a ratified 200. WR-21 had to
move `UnknownStoreSubscriptionStatus` as well as `_tier_for`. Details are in each wave below.

**Load-bearing proof.** Every test added or repaired for WR-80, WR-81, WR-82 and WR-100..WR-122 was
mutation-probed — the source or fixture it covers was broken, the test was confirmed to fail, and
the mutation was reverted in the same tool call. Wave 3 additionally ran each mutation against the
pre-fix test to prove the old case was blind.

---

# Wave 1 of 3

Nine findings in scope: CR-60, WR-01, WR-02, WR-03, WR-04, WR-20, WR-21, WR-22, WR-23.
All nine fixed. No findings skipped.

## Verification

Run in the main checkout of `ns-api-gateway` (no worktree was created — this directory is a
submodule, so `IS_WORKTREE` detection off the `.git` file is wrong here).

| Gate | Baseline | After |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1831 passed | 1846 passed |
| `pytest tests/schema -m schema` | 277 passed | 277 passed |
| `pytest tests/e2e -m e2e` | 356 passed | 357 passed |
| `ty check src` | 0 diagnostics | 0 diagnostics |

`git status --short` is clean.

## CR-60 — ingestion reactivates a lapsed entitlement

**Commit:** `604f837`

**Correction to the review.** The suggested remedy — put the lapse guard inside
`SubscriptionsDB.write_subscription_grant` unconditionally — is self-defeating as written.
`services/restore.py:157` calls the *same* writer ("The webhook's own writer, called unchanged, so
both paths mint one term the same way"), and restore is the one path spec 08:42 and D-18 reserve
reactivation for. An unconditional guard there would make restore unable to bring a lapsed term
back, which is the opposite of the rule.

**What I did instead.** The writer takes a new keyword-only `may_reactivate: bool`. Ingestion
(`services/subscriptions.py`) passes `False`; restore (`services/restore.py`) passes `True`. Under
`may_reactivate=False`, when the status is entitled and the subscription holds no active grant in
`marked_active`, the writer asks the new
`GrantsDB.has_prior_subscription_grant(subscription_id)` — a sibling of `has_prior_free_grant`,
selecting `AccessGrant` by `subscription_id` with no status predicate — and returns
`WriteOutcome.applied` having ended nothing and inserted nothing. The canonical row and the event
row still commit. Restore short-circuits before the read, so it issues no extra statement and its
behaviour is byte-identical.

Both inputs the review names are now covered by unit cases in
`tests/unit/test_subscription_grant_write.py::TestALapsedTermIsNeverBroughtBackByIngestion`:
lapse-then-renew, and a later notification about a newest-wins-superseded subscription (the
winner's live grant keeps `status=active` and its own `ends_at`). Two controls: a first verified
purchase still inserts, and `may_reactivate=True` still reactivates.

The file's stub session had to learn the second read. It now dispatches on
`statement.column_descriptions[0]["entity"]` and counts `usage_reads` and `grant_reads`
separately; `test_the_old_owners_count_is_never_inherited_on_a_move` now asserts
`usage_reads == 0`, which is what it always meant.

## WR-01 — `.dockerignore` credential patterns root-anchored

**Commit:** `3aee6e7`

Finding holds. Docker's ignore patterns are `filepath.Match` over the whole relative path, so `*`
does not cross `/`: `*.p8` never excluded `config/AuthKey_*.p8`, while `.gitignore:20-23` does
match at any depth. `Dockerfile:29` is `COPY config ./config/`.

Every credential shape is now `**`-prefixed (`**/.env`, `**/.env.*`, `!**/.env.example`,
`**/*.p8`, `**/*.pem`, `**/*.key`, `**/application_default_credentials.json`), and so are
`**/__pycache__/` and `**/*.egg-info/`, which were silently inert for everything under `src/`. The
header's claim that "the credential shapes are the ones `.gitignore` names" is now true, and one
line records why the `**` is load-bearing.

## WR-02 — `cryptography` imported but not declared

**Commit:** `4d63404`

Finding holds: `app/lifespan.py:11` is `from cryptography import x509`, used at `:67`, and the lock
carried it only as a transitive of `PyJWT[crypto]`. Added `"cryptography >=46,<47"` to
`[project].dependencies` and re-ran `uv lock` (offline; the resolution is unchanged — the lock diff
is the two dependency entries only, still `cryptography 46.0.5`). The comment above the
`starlette`/`sqlalchemy` pair now covers three imports rather than two and names the `x509` API the
ceiling is for.

## WR-03 — `str.isdigit()` lets a malformed value reach a boot crash

**Commit:** `d6a1223`

Finding holds; reproduced in this tree — `APP_STORE_APP_APPLE_ID='²'` raised
`int_parsing` out of `EnvironmentConfig()`.

`_numeric_or_absent` now classifies by the parse that actually runs: a `bool` is absent, an `int`
is kept, anything else goes through `int()` and a `TypeError`/`ValueError` is absent. This also
closes the >4300-digit case the review names, and (beyond the review's own snippet) the `bool`
case, which pydantic refuses for an `int` field and which the suggested version would have
silently coerced to `1`.

Pinned by a parametrized case over `²`, `₁`, a 4301-digit string and `True` in
`tests/unit/test_config.py::TestAMalformedAppStoreValueCostsTheRouteAndNotTheBoot`.

## WR-04 — an unusable App Store product map produces no boot signal

**Commit:** `721099d`

Finding holds. `build_app_store_verifier` never looks at `products`, and the Play arm one screen
below already tests its own map. The condition at `lifespan.py` is now
`if app_store_verifier is None or not config.app_store.products:`.

**Correction to the review's remedy.** The review says this makes the unusable-map case "degrade to
the same 503". It does not, and must not: D-14/D-21 ratify that an unmapped product is a 500 Apple
retries until an operator adds the line. Widening the *warning* is the whole fix; forcing the
verifier to `None` would overturn a ratified decision. Because the old consequence text asserted
`verification_temporarily_unavailable`, which is false for the empty-map case, the text now mirrors
the Play arm's status-agnostic wording and names the product map:
"POST /webhooks/app-store refuses every notification until this pod is restarted with the App Store
bundle id, environment, product map, app id and root certificate available in this environment".

Note for waves 2/3: **WR-40 is the same defect at the same line** and is now fixed. The only part
of WR-40 left is its second point — that `app_apple_id` is required in production only, so the text
could say "app id (production only)".

## WR-20 — a verified transaction with no `originalTransactionId` is 200'd and dropped

**Commit:** `5b87b37`

Finding holds. `AppStoreNotifications.verify` now raises
`NotificationRejected(stage="transaction_without_original_id")`, the same stage the restore path
already uses at `verify_transaction`.

**Placement differs from the review's snippet.** The review puts the guard immediately after the
transaction is decoded. I put it immediately *after* the `data.rawStatus is None` arm. That arm is
ratified: a statusless type (CONSUMPTION_REQUEST, ONE_TIME_CHARGE, EXTERNAL_PURCHASE_TOKEN,
RESCIND_CONSENT) deliberately drops its transaction and answers 200, and guarding above it would
change that ratified answer for a case that produces no loss. Below it, the guard covers exactly
the silent-loss path the finding describes and nothing else.

`tests/unit/test_app_store_notifications.py` gains
`TestAVerifiedTransactionWithoutItsLifecycleKeyIsRefused` (the refusal, plus two controls: the
library really does verify the same transaction, and the restore path names the same stage), and
`_transaction()` takes `original_transaction_id`. The e2e control
`test_every_reachable_arm_is_covered_by_one_parameter` reads the module's raise sites, so
`REFUSAL_STAGES` in `tests/e2e/test_app_store_webhook.py` gained the new stage — which also gives
it a 401-body case.

## WR-21 — the product→tier lookup runs before the renewal is verified

**Commit:** `d22b36e`

Finding holds. `verify` now verifies the renewal payload first and resolves both business values
last, in a single exit:

```
renewal = None
if data.signedRenewalInfo is not None:
    try: renewal = ...verify_and_decode_renewal_info(...)
    except ...: raise NotificationRejected(...)
status = ...
if status is None: raise UnknownStoreSubscriptionStatus(...)
return _crossed(payload, transaction, renewal, status=status,
                tier_id=self._tier_for(transaction.productId))
```

**Extension beyond the review.** The review names `_tier_for` only. `UnknownStoreSubscriptionStatus`
is the identical defect — also an `InternalError` → 500, also raised above the renewal verification
— so moving only `_tier_for` would leave the same 500-and-retry loop reachable by a second route. I
moved both; that is one rule, not two. This also collapses the two duplicate `_crossed` returns the
review's snippet would have created.

Two cases pin it (unmapped product under an unverifiable renewal, unknown status under an
unverifiable renewal, both answering `INVALID_ENVIRONMENT`), plus a control proving the ratified
`UnmappedStoreProduct` 500 still happens once everything verifies. `_notifications()` takes a
`products` override for this.

## WR-22 — `record_failure` carries no generation guard

**Commit:** `6aa79fa`

Finding holds. `record_failure(generation)` now discards a stamp from before the last trip, exactly
as `record_success` does, and `attempt()` passes the stamp it already takes.

One structural change the review's snippet does not mention: `generation` was assigned *inside* the
`try`, so passing it to `record_failure` in the `except` arm would be a possibly-unbound read. The
per-attempt `before_call()` and the stamp now sit above the `try`, which leaves the `try` covering
`operation()` alone. Behaviour is unchanged — the old `except (QueueFullError, CircuitOpenError):
raise` arm did nothing but re-raise `before_call`'s refusal.

I did **not** take the alternative the finding offers (a `ResilienceConfig` validator asserting
`timeout_seconds < circuit_breaker_reset_seconds`). The asymmetry is the root cause; a validator
would enforce a coincidence instead of removing the dependence on it.

Tests: `BreakerSpy.counting_failure` takes the stamp; a module-level `_fail(breaker)` helper stamps
at the current generation for the twelve direct call sites; and
`test_a_straggler_failure_landing_after_the_reset_does_not_reopen_the_breaker` is new. Its
assertion is on the trip counter, not on a subsequent `before_call()` — I checked empirically that
with `reset_seconds=0` the pre-fix reopen is immediately cleared again by the elapsed arm, so only
the counter discriminates (pre-fix `straggler + 2`, post-fix `straggler + 1`).

## WR-23 — multi-line comment runs

**Commit:** `af6f0a6`

Finding holds, and its count is exact: a token-level detector found **50** comment runs of three
lines or more across the twelve files (`auth/` ×6, `schemas/` ×3, `resilience.py`). All 50 are gone;
the detector now reports 0 for `src/nativespeaker/api/auth/`,
`src/nativespeaker/api/schemas/` and `src/nativespeaker/api/resilience.py`. In each case the one
clause that resolves the ambiguity at the line below was kept and the design narrative dropped.

**Two departures from the review's remedy, both deliberate.**

1. *"Extend the existing `services`/`routers` detector to these paths."* There is no committed
   detector to extend — nothing under `tests/` measures comment runs; 41-REVIEW-FIX WR-79's
   "detector" was an ad-hoc script. I did not add one. A new ratchet would have to record a nonzero
   baseline (`services/auth.py:307-309` and `services/chats.py:104-106` are three-line runs today)
   or force edits in files WR-23 does not name, and AGENTS.md asks that programming this app not
   consume many tokens.
2. *Scope.* 61 two-line runs remain in the twelve files. That is the same standard the ratified
   `services`/`routers` sweep left behind — those two packages still carry 28 two-line runs — so
   these files are now at least as clean as the ones WR-79 finished. Driving every comment to a
   strict one line is a repo-wide change, not this finding's.

No docstring was written or edited past three lines; `test_docstring_bar.py` stays at its recorded
zeros.
---

# Wave 2 of 3

Seven findings in scope: WR-40, WR-41, WR-60, WR-61, WR-80, WR-81, WR-82. All seven fixed.
No findings skipped. Wave 1's nine commits were treated as current intended code.

## Verification

Run in the main checkout of `ns-api-gateway` (no worktree — this directory is a submodule, so
`IS_WORKTREE` detection off the `.git` file is wrong here). Every number below was re-measured
after the last commit.

| Gate | Baseline (after wave 1) | After wave 2 |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1846 passed | 1859 passed |
| `pytest tests/schema -m schema` | 277 passed | 277 passed |
| `pytest tests/e2e -m e2e` | 357 passed | 357 passed |
| `ty check src` | 0 diagnostics | 0 diagnostics |

`test_docstring_bar.py` stays at its recorded zeros: every docstring written here is ≤3 lines.
`git status --short` is clean apart from this report.

## WR-40 — the App Store boot warning does not test the product map

**Commit:** `5bd2acd`

**Almost entirely done by wave 1.** Wave 1's WR-04 fix is the same defect at the same line: the
condition is already `if app_store_verifier is None or not config.app_store.products:` and the
consequence text already names the product map. Nothing was left of the finding's first point.

The residual second point holds and is now fixed: `build_app_store_verifier` requires
`app_apple_id` only when `store.environment is StoreEnvironment.production` (`lifespan.py:60-61`),
so the warning sent a sandbox operator looking for a setting that is not theirs. The text now says
"app id (production only)". No behaviour changed and nothing under `tests/` asserts either
warning's text, so no test moved.

## WR-41 — a transient JWKS failure disables Play ingestion for the pod's life

**Commit:** `4bb7918`

Finding holds, in both halves. `JWTVerifier.__init__` fetches, `build_google_push_verifier`
converts a `PyJWTError` to `None`, `PubSubPushTokens` stored that `None` once, and nothing
rebuilt it — while `/health/ready` answers 200 unconditionally, so Kubernetes never restarts the
pod. The warning emitted named a configuration absence that was not the cause.

**Root cause, and what I did.** The cause is caching a transient result as if it were a permanent
one. `PubSubPushTokens` now takes an optional `build` alongside `verifier`; when it holds no
verifier it rebuilds through `run_in_threadpool` before refusing, so the next delivery recovers
without a restart. `lifespan` hands it `lambda: build_google_push_verifier(config.google_play)`.
A genuinely unconfigured deployment costs nothing: the builder returns `None` before any fetch,
and the 503 is the one it always was. No lock: at this product's delivery rate two concurrent
rebuilds are idempotent and the last writer wins.

The misleading log line is fixed at its own root — the builder collapsed two different states into
`None`. `google_push_pins(play)` is now the one place the two pinned values are tested; `lifespan`
warns `google_play_configuration_absent` when they (or the package name, product map or ADC) are
absent, and `google_push_verifier_warm_up_failed` when everything is present and only the warm-up
failed, whose consequence text says the next delivery retries without a restart.

**Correction to the review's snippet.** The review writes the predicate as a `bool`. That loses
pydantic's `str | None` narrowing inside the builder and cost one `ty` diagnostic
(`Expected str, found str | None` at the `audience=` argument), so `google_push_pins` returns the
narrowed pair instead of a boolean. `ty` is back to zero.

Four cases in `tests/unit/test_google_play_notifications.py::
TestAWarmUpFailureIsRetriedRatherThanCachedForThePodsLife`: the rebuild recovers, the rebuilt
verifier is kept (two deliveries, two total JWKS fetches), a still-unreachable key set is the 503
it was, and an unconfigured deployment rebuilds without reaching for Google's keys. Mutation-probed:
deleting the rebuild arm fails the first two.

## WR-60 — free-tier usage copied into the paid counter

**Commit:** `f9c7ce0`

Finding holds, and I reproduced it against the real writer before touching it: an
`anonymous_device_grant` holding `monthly_used=45` in the current period seeded the paid usage row
at `45`. `08-webhook-app-store.md:38` forbids it in as many words. `mine` at
`crud/subscriptions.py` now also requires `grant.source is AccessGrantSource.subscription`; the
same probe after the fix seeds `0`, and a subscription-source supersession still carries `45`, so
WR-48's grace bounce and mid-term tier change are untouched.

**Test-side note for wave 3.** The review files the test gap separately as WR-100, which is wave
3's. I deliberately did not write it, so WR-100 is still owed — and it is load-bearing as the
review words it: before this commit it reads `[45]`, after it reads `[0]`.

**One test updated, not weakened.** `test_grant_sources.py::
test_the_one_site_is_inside_the_crud_subscription_writer` counts mentions of
`AccessGrantSource.subscription` inside the writer and expected 2. The carry filter is a third
mention, so the count is now 3 with the reason on the line. The stronger sibling —
`test_the_whole_tree_holds_exactly_one_construction_site` — is untouched and still pins one
construction site.

## WR-61 — a store notification silently expires an operator-issued manual grant

**Commit:** `a4858b2`

Finding holds. When the status is entitled, `superseded` is every grant the destination holds, and
`08-webhook-app-store.md:40` enumerates only "the buyer's active free grant, or previously active
subscription grant". The non-deferrable `ix_access_grants_one_active_per_user` leaves no
alternative to expiring it, so — as the review says — the fix is to make the loss visible.
`crud/subscriptions.py` now logs one WARNING `manual_grant_superseded` naming `grant_id` and
`source` before the sweep writes the row.

**Two corrections to the review's remedy.**

1. *"…and the `manual_grant_issuances.case_id`".* There is no `case_id` to log.
   `core.manual_grant_issuances` exists in the migration (`:273-280`) but has no SQLModel table, no
   crud and no reader — 37.4 IN-40 filed exactly that. Reading it would mean a new model plus a new
   query for one log line. The DDL makes `grant_id UUID NOT NULL UNIQUE`, so the grant id *is* the
   key the case is looked up by; the line carries it, and one comment says so.
2. *The line does not carry the status it wrote.* I tried to, and the case failed: outside the
   entitled set `superseded` is `held`, which is this subscription's own subscription-source rows,
   so a `revoked` status never reaches a `manual` grant at all. A `status` field would have been a
   constant. That property is pinned instead as the control.

Three cases in `TestAnOperatorsGrantIsNotEndedSilently`: the line and its exact fields, a
withdrawal reaching the operator's grant neither to end it nor to record it, and an ordinary free-
grant supersession writing no line. Mutation-probed: deleting the warning fails the first.

## WR-80 — `lost_race_to_another_source` is asserted nowhere

**Commit:** `a3d53e7`

Finding holds exactly as written, including its probe. Both cases named
`test_a_race_lost_to_another_source_is_the_refusal_the_preflight_gives` now take `monkeypatch`,
install `_handler_warnings`, and assert
`[("claim_refused_under_lock", "lost_race_to_another_source")]` — the shape the sibling case
`test_a_race_the_re_read_cannot_answer_is_named_apart_from_those_refusals` already uses.
`_handler_warnings` is imported into the registered file rather than copied, like the rest of that
file's scaffolding.

Mutation-probed: deleting the whole `if held: raise ClaimRefusedUnderLock(
cause="lost_race_to_another_source")` block from `services/auth.py` now fails both cases
(1851 passed, 2 failed) where before it left the suite green.

## WR-81 — the DeviceCheck transport-failure conversion is tested by nothing

**Commit:** `07d60e3`

Finding holds: `Recorder` always answers, so `devicecheck.py`'s `except httpx.HTTPError` pair was
the file's only uncovered lines. `_unreachable` is a mock-transport handler that raises
`httpx.ConnectError`, and `_adapter`'s annotation is widened from `Recorder` to
`Callable[[httpx.Request], httpx.Response]` — honest, since `MockTransport` only ever needs the
call.

`TestATransportFailureIsRetryableAndNamesOnlyItsClass` drives four properties the summary claims:
the marker is raised and stringifies to `ConnectError`; it carries neither the device token nor
`DEVICECHECK_HOST`; and both entry points exhaust their budget to `Unavailable`, each with its own
stage. Mutation-probed: replacing the conversion with a bare `raise` fails all four.

## WR-82 — the unconfigured-Play-credential arm has no test

**Commit:** `c0e4de0`

Finding holds, sentinel and all: `_play_reader`'s `credential=None` default was substituted with
`_FakeCredential()`, so the real `None` was unsayable. The default is now `_UNSET`, and
`TestAnUnconfiguredCredentialIsNeverAcknowledged` passes `credential=None` through to the real
reader over a `_never_reached` transport, asserting `Unavailable` with
`stage == "play_subscriptions_read"` — a stage that appeared nowhere under `tests/` before. A
control pins that the sentinel default still stands a credential in, so the other 127 cases in the
file are not silently measuring this refusal.

Mutation-probed: replacing the raise with `return None` — the mutation that makes an unconfigured
pod acknowledge every RTDN — now fails this case where before it left 1831 green.

**One part of the remedy not taken.** The review adds "splitting the e2e `unconfigured_google_play`
fixture into its two halves would close the same hole from the other side". The arm is now driven
directly and mutation-proven at the unit tier; a second e2e fixture plus its case would buy a
second proof of one branch, which AGENTS.md's "do not over-engineer" does not pay for. The e2e
fixture is not itself defective — it nulls both halves, which is a real deployment state.

---

_Fixed: 2026-09-09_
_Fixer: Claude (gsd-code-fixer), wave 2 of 3_
_Iteration: 1_
---

# Wave 3 of 3

Eight findings in scope: WR-100, WR-101, WR-102, WR-103, WR-104, WR-120, WR-121, WR-122.
All eight fixed. None skipped. Waves 1 and 2 (sixteen commits) were treated as current,
intended code. No source file changed in this wave: every finding is a test-tier gap, and no
repaired test caught a source defect.

## Verification

Run in the main checkout of `ns-api-gateway`. No worktree was created — this directory is a
submodule, so worktree detection off its `.git` file is wrong here. Every number was
re-measured after the last commit.

| Gate | Baseline (after wave 2) | After wave 3 |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1859 passed | 1867 passed |
| `pytest tests/schema -m schema` | 277 passed | 277 passed |
| `pytest tests/e2e -m e2e` | 357 passed | 357 passed |
| `ty check src` | 0 diagnostics | 0 diagnostics |

`test_docstring_bar.py` stays at its recorded zeros: every docstring written here is ≤3 lines.
`git status --short` is clean apart from the three report files.

## WR-100 — the free-grant supersession case cannot detect the usage carry

**Commit:** `0f77e5f`

Finding holds exactly as worded, and wave 2's note is right: the source side (WR-60) is fixed,
the test side was still owed. `test_a_free_grant_is_superseded_too` seeds `monthly_used=0`, so
its assertion holds either way.

`TestTheMonthsCountSurvivesATermChangeInsideIt` — the class that pins the carry rule — gains
`test_a_free_grants_count_is_never_carried_into_the_paid_counter`: an
`anonymous_device_grant` holding `monthly_used=45` in the current period, asserting
`_minted(session) == [0]`. Its control,
`test_a_term_change_inside_the_month_carries_the_count`, sits three lines above it and still
reads `[45]`, so the two sources are told apart rather than the carry being switched off.

**Mutation probe.** Removing `and grant.source is AccessGrantSource.subscription` from `mine`
in `crud/subscriptions.py` — the whole of wave 2's WR-60 fix: 24 passed → 1 failed, and the
failure is the new case. Reverted in the same call.

## WR-101 — `PurchasesDB.resolve_user` has no unit case at all

**Commit:** `717d4ab`

Finding holds, including its probe. Every consumer test replaces this read with a stub that
ignores its arguments.

`TestTheAttributionReadIsKeyedOnTheStoreAndTheToken` in `test_purchases_crud.py` drives the
real method over the file's own recording stub: `_bound(...) == [PurchaseProvider.apple,
APPLE_TOKEN]`, the bound owner is what the read answers, and the statement is one and
unlocked. `_StubResult` gained the `first()` the review names, plus the `owner` it answers
with — `all()` is the token read's shape and `first()` the attribution read's. The module
docstring named only the token read and now names both.

**Mutation probe.** Deleting `col(StorePurchaseToken.provider) == provider` from
`crud/purchases.py::resolve_user` — one store's token resolving the other store's binding: 20
passed → 1 failed. Reverted in the same call.

## WR-102 — the replay key's own statement is unpinned

**Commit:** `08f8dff`

Finding holds: the only replay case measures what the service does after a dict lookup in the
test has answered.

**Placement differs from the review.** The review files this against
`test_subscription_attribution.py`, whose module docstring is "Each case asserts the values the
writer was asked to persist, **never the statements it emitted**" — a compiled-statement case
contradicts the file's own standard. `test_subscription_store_clock.py` is already the
`SubscriptionsDB`-over-a-stub-session statement file, with `_compiled`, a statement-keeping
session and `first()`; the case went there, its `_bound` sibling was added, and the module
docstring now names the replay read alongside the clock and the owner.

**Correction to the review's remedy.** The four assertions it lists — one statement,
`audit.subscription_events` present, no `FOR UPDATE`, `_bound == ["uuid-under-test"]` — do
**not** catch the review's own probe. Re-keying `_event_statement` onto
`SubscriptionEvent.event_type` leaves the table, the statement count, the lock and the bound
value all unchanged, and I measured that: 11 passed with the mutation live. The keyed
**column** is what discriminates, so the case asserts
`"audit.subscription_events.notification_uuid = " in _compiled(...)`, the shape
`TestTheReadIsScopedToOneOwner` already uses for the owner predicate.

**Mutation probe.** Re-keying `_event_statement` onto `event_type`: 12 passed → 1 failed
(`test_the_statement_is_keyed_on_the_uuid_column`). Reverted in the same call.

## WR-103 — the secrecy case checks a narrower scope than its docstring

**Commit:** `9001dad`

Finding holds. Lines 427-429 asserted three absences from `repr(log_fields())` under an exact
dict equality on the line above, so none could fail on its own; meanwhile the docstring's "no
store value is in the record" was never checked on the exception's message, which is where a
store value could actually reach an operator. The three lines are gone, replaced by the loop
over `str(refusal.value)` the review names and the restore path's
`TestThePlayRefusalNamesNoPartOfTheToken` already uses.

**Mutation probe.** `AttributionConflict` given the presented value in its message
(`f"...another attribution value: {presented}"`, with the raise site in
`services/subscriptions.py` passing `token`) — the "put the value in the message for
debuggability" drift the case exists for. Post-fix: 56 passed, 1 failed. Pre-fix, under the
identical mutation: **57 passed**, so the deleted assertions really were blind to it. Both
source files reverted in the same call.

## WR-104 — the recorder copies both store transaction ids and no case reads either

**Commit:** `87a9cbf`

Finding holds, probe and all. `TestTheSinglePurchaseArms` gains
`test_the_two_store_ids_land_in_their_own_columns`, asserting
`store_original_transaction_id == notification.external_id` and
`store_transaction_id == notification.transaction_id` against a named notification.

**One departure.** The review puts the two lines inside
`test_the_attributed_shape_carries_the_owner_and_the_resolved_token`. They are a different
property — D-08's column assignment, not the CHECK's attributed half — so they are their own
case and the attributed-shape case is untouched.

**Mutation probe.** Swapping the two arguments at the `insert_purchase` call site in
`services/subscriptions.py`: 57 passed → 1 failed, and it is the new case. Reverted in the
same call.

## WR-120 — both completeness controls are blind to a new raise site in `app/dependencies.py`

**Commit:** `a8d52e5`

Finding holds, and I reproduced its proof before touching anything: appending
`def _probe_never_called(): raise NotificationRejected(stage="a_stage_no_case_covers")` to
`app/dependencies.py` left all four control cases green (**4 passed**).

**Root cause.** The scan was function-level (`inspect.getsource`) while the control that was
supposed to close its gap was file-level, so every raise site in a file already named by
`REFUSAL_FILES` but outside the one scanned function was invisible to both. Half the Apple
tuple contributed nothing at all: `verify_app_store_notification` carries no raise.

`raised_refusal_stages` now takes package-relative file names and reads each file whole;
`inspect` and the two imports that existed only to be scanned are gone from both webhook
modules.

**Correction to the review's remedy.** It says each module should "assert its parametrised
arms equal the union over `REFUSAL_FILES`". Taken literally that mixes the two routes: the
union carries Google's bounded reasons into Apple's equality and vice versa, and neither
equality can hold. `refusal_sites.py` instead declares `APP_STORE_REFUSAL_FILES` and
`GOOGLE_PLAY_REFUSAL_FILES`, each route scanning its own, with `REFUSAL_FILES` **derived** as
their union so the whole-package file control is unchanged in force.
`app/dependencies.py` belongs to the Play set, because today it carries only that route's two
dependency raises; a refusal added anywhere in it — including an Apple one — now fails the
Play route's equality rather than passing both. Failing the wrong route's control is still a
failure that names the file, which is what the control owes.

**Mutation probe.** The review's own probe, re-run against the fix: the same appended raise
site now gives 3 passed, 1 failed (`test_every_reachable_arm_is_covered_by_one_parameter` on
the Play route) where it gave 4 passed before. Reverted in the same call.

## WR-121 — the stage scanner reads only the `stage=` keyword

**Commit:** `430bd89`

Finding holds: a positional `NotificationRejected("...")` contributed no member to `raised`,
so the completeness equality still held while the new arm had no parameter and no case.

**Correction to the review's remedy.** It says to record `COMPUTED` for an unreadable call
shape, and concedes the arm is then "covered by the computed-stage arm". That is not
fail-closed: both routes subtract `COMPUTED` out of the equality on purpose, because it stands
for the library's enum and for the bounded reason set, so a positional raise would be absorbed
and add nothing — the very defect. `refusal_sites.py` declares a second marker, `UNREADABLE`,
which is in no route's expected set, so an unreadable raise site **breaks** the equality and
has to be made a literal or given a parameter. `COMPUTED` keeps its one meaning: a `stage=`
whose value is computed at the raise site.

**Mutation probe.** Appending
`def _probe_never_called(): raise NotificationRejected("a_stage_no_case_covers")` to
`auth/app_store.py`. Post-fix: 3 passed, 1 failed. Pre-fix (at the WR-120 commit, where the
scan returned `COMPUTED` for it): **4 passed**. Both reverted in the same call. I deliberately
did not probe by converting an existing keyword raise to a positional one — that also removes
its literal from `raised`, so the equality would fail for the wrong reason and prove nothing.

## WR-122 — the Apple "a valid Firebase token buys nothing" case never establishes validity

**Commit:** `f585292`

Finding holds: the case requested `stub_verifier` and never used it, so it passed for any
bearer string. The token is now minted once, verified through `stub_verifier`, and asserted
`claims is not None` before it is posted — the exact control the Google twin at
`test_google_play_webhook.py` already carries, comment included.

**Mutation probe.** Drifting `make_token`'s default `aud` off `TEST_PROJECT_ID`, so the
premise "valid" silently stops holding. Post-fix: 1 failed. Pre-fix, same drift: **1 passed**.
Reverted in the same call.

---

_Fixed: 2026-09-09_
_Fixer: Claude (gsd-code-fixer), wave 3 of 3_
_Iteration: 1_
