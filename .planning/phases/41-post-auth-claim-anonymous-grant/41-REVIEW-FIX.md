---
phase: 41-post-auth-claim-anonymous-grant
fixed_at: 2026-09-10T02:38:43Z
review_path: .planning/phases/41-post-auth-claim-anonymous-grant/41-REVIEW.md
fix_scope: critical_warning
iteration: 1
findings_in_scope: 38
fixed: 38
skipped: 0
status: all_fixed
---

# Phase 41: Code Review Fix Report

**Fixed:** 2026-09-10T02:38:43Z
**Fix scope:** Critical + Warning (1 critical, 37 warning)
**Findings in scope:** 38 · **Fixed:** 38 · **Skipped:** 0

The 38 in-scope findings were applied by five `gsd-code-fixer` agents run STRICTLY SEQUENTIALLY (never in parallel — concurrent fixers share one git index and corrupt each other), each owning a disjoint block of findings. One `fix(41): <finding-id> ...` commit per finding, 38 commits total, `acfbb43` through `b442eef`.

## Verification (orchestrator, re-run independently after all fixes)

| Gate | Baseline `9ee7523` | After |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1743 passed | 1791 passed |
| `pytest tests/schema -m schema` | 250 passed | 251 passed |
| `pytest tests/e2e -m e2e` | 354 passed | 355 passed |
| `ty check src` | 3 diagnostics | 0 diagnostics |

No test was weakened. Where a fix changed behaviour a test asserted, the test was updated to the corrected expectation. Every test finding was mutation-proved: the named source mutation was applied, the suite confirmed red, then the mutation reverted and the suite confirmed green.

## Corrections to the review

Four findings were fixed at their real root cause rather than as written, because the review's stated remedy was wrong or self-defeating. Each correction is recorded in its part below: WR-23 (a second log line would break the one-line refusal invariant), WR-60 (the literal predicate would refuse every adoption-with-creation), WR-140/WR-141 (the deferred constraints are foreign keys, so COMMIT raises 23503, never the 23505 the review named), and WR-116 (the assertion was right and the test name was wrong). WR-21 has no in-bounds code fix — Apple offers no compare-and-set and SHARED-INVARIANTS bans both a device-keyed limit and any lease — so it was recorded as accepted residual threat T-41-31 / AR-41-03.

## Part 1 of 5

# Phase 41: Code Review Fix Report — part 1 of 5

**Source review:** `41-REVIEW.md`
**Assigned findings:** CR-80, WR-01, WR-02, WR-03, WR-04
**Iteration:** 1

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0
- Review corrections recorded: 0 factually wrong findings; 1 remedy adapted (WR-01's
  test fallout), 1 remedy compressed to satisfy `AGENTS.md` § Comments and docstrings
  (CR-80's five-line docstring).

## Fixed Issues

### CR-80: The e2e lifespan fixture leaks `setup_logging`'s global state

**Files modified:** `tests/e2e/conftest.py`
**Commit:** `acfbb43`

The finding holds and was reproduced first:

```
$ .venv/bin/pytest tests/e2e/test_challenge_store.py tests/unit/test_logging.py -q -m ""
FAILED tests/unit/test_logging.py::test_no_quieted_library_level_outlives_the_test_that_set_it
1 failed, 66 passed
```

Root cause confirmed at the line: `_app_lifespan` enters
`app.router.lifespan_context(app)`, whose `setup_logging` runs
`root.handlers.clear()`, `root.setLevel(...)` and
`logging.getLogger(name).setLevel(WARNING)` for the nine `_QUIETED_LIBRARIES`
(`src/nativespeaker/api/logs.py:58-64`). `grep` confirmed `_app_lifespan` is the only
place in `tests/` that enters the real lifespan, so it is the sole polluter.

**Applied fix:** snapshot the root handler list, the root level, and the nine library
levels before entering the lifespan, and restore all three in a `finally`. This is the
same shape as the unit suite's own `_reset_logging` fixture
(`tests/unit/test_logging.py:22-38`), so the two now agree.

**Correction to the review's remedy:** its suggested docstring is five lines, which
`AGENTS.md` § "Comments and docstrings" caps at three and
`tests/unit/test_docstring_bar.py` enforces at zero-baseline. Compressed to one line,
with the single ambiguity-resolving comment moved to the line it explains.

Verified with the review's own acceptance command — `pytest -q -m ""` went from
`1 failed, 2346 passed` to `2347 passed`.

### WR-01: The circuit breaker relights its whole tally after every reset window

**Files modified:** `src/nativespeaker/api/resilience.py`, `tests/unit/test_resilience_retry.py`
**Commit:** `99efd4f`

The finding holds. `before_call`'s elapsed arm set `_failure_count = 0`, so a provider
still down after `circuit_breaker_reset_seconds` needed a fresh
`circuit_breaker_failure_threshold` failures to reopen, each costing a full ~91.5s
`tenacity` chain (`AGENTS.md` § Resilience).

**Applied fix:** the elapsed arm now primes the tally at `self._failure_threshold - 1`
instead of clearing it, so one failure after the window reopens the breaker.
`circuit_breaker_failure_threshold` is `Field(ge=1)` (`config.py:55`), so the primed
value is never negative. `record_success` is unchanged and still clears the tally for a
current-generation success, so a genuinely recovered provider resets on its first good
answer and a stale straggler still cannot.

**Test fallout, handled rather than worked around** (the review did not mention it):

- `test_a_success_stamped_after_the_reset_still_clears_the_tally` asserted the old
  semantics — under half-open its `record_failure` now trips before the success is
  recorded. The success was moved ahead of the failure, which is what the case is named
  for ("a success stamped after the reset clears the tally") and still fails if
  `record_success`'s generation guard is removed.
- `test_a_straggler_landing_after_the_reset_does_not_clear_the_fresh_tally` needed one
  fewer post-reset failure to reach the same trip count; the redundant failure and the
  stale comment were dropped. It remains discriminating: without the generation guard the
  straggler's success would zero the primed tally and the reopen would not happen.
- Added `test_one_failure_after_the_reset_window_reopens_the_breaker`, which names the
  new behaviour directly.

Proven discriminating by reverse-applying the source hunk: with
`self._failure_count = 0` restored, the new case and the straggler case both fail.

### WR-02: An empty configured Play package name makes the package-name pin vacuous

**Files modified:** `src/nativespeaker/api/app/dependencies.py`, `tests/unit/test_google_play_notifications.py`
**Commit:** `f013c56`

The finding holds, and each supporting claim was checked at the line:

- `GooglePlayConfig.package_name` is `str | None` with no emptiness handling (`config.py:119`).
- `DeveloperNotification.packageName` is bare `str` with no `min_length`
  (`auth/google_play.py:112`), so a body carrying `""` validates.
- `PlayDeveloperSubscriptions.read` guards `purchase_token` with
  `_names_one_path_segment` (`google_play.py:254`) but applies no guard to
  `package_name`; only `read_for_restore` does (`google_play.py:312`). So `""` would
  reach the Play URL as an empty path segment.
- The three sibling optional settings do guard on truthiness (`lifespan.py:60`, `:81`,
  `:159`), and the boot warning already tests `not config.google_play.package_name`
  (`lifespan.py:184`). This was the only place in the boot path reading `""` as configured.

**Applied fix:** the review's — hoist the configured value into `expected_package` and
refuse when it is falsy, before the equality.

**Added test:** `test_an_empty_configured_package_refuses_a_delivery_that_names_none_either`.
The existing `test_an_unconfigured_package_refuses_every_delivery` uses `package_name=None`,
which the bare equality already caught; the empty-string case was the gap. The new case
had to carry `**SUBSCRIPTION_BODY`, because the package check sits after
`subscription_notification_from` and a body-less RTDN returns `None` before reaching it.
Proven discriminating by reverse-applying the source hunk.

### WR-03: `.env.example` ships `GOOGLE_APPLICATION_CREDENTIALS` uncommented

**Files modified:** `.env.example`, `tests/unit/test_config.py`
**Commit:** `9cbd6b1`

The finding holds. The block at `:70-74` offers a `gcloud auth application-default login`
session as an equal route, and `google.auth.default()` prefers an explicitly set
`GOOGLE_APPLICATION_CREDENTIALS` over the well-known session file — so a developer who
took the second route and copied this file loses their working credential to a
placeholder path, and `_application_default_credential` degrades it to `None`
(`auth/firebase.py:59-67`) behind a warning indistinguishable from an unconfigured
environment.

**Applied fix:** the line now ships commented out, with the "uncomment and fill this, or
leave it out entirely" paragraph the two store blocks (`:122-123`, `:164-165`) already
carry, naming the specific consequence.

**Added test:** `TestTheAdcPlaceholderCannotShadowAGcloudSession`. Checking that the file
ships no *uncommented* assignment of the name, with a control asserting the commented
placeholder is still present — otherwise deleting the variable outright would pass.
`_assignments` (`tests/unit/test_config.py:663`) deliberately reads commented assignments
too, so the existing `.env.example` cases are unaffected; verified by running the file.
Proven discriminating by un-commenting the line and re-running.

### WR-04: The container process owns its own code and virtualenv

**Files modified:** `Dockerfile`, `tests/unit/test_config.py`
**Commit:** `a8acb5f`

The finding holds. Its load-bearing premise — "`uv sync` writes world-readable files" —
was checked empirically against this repository's own uv-created virtualenv rather than
taken on trust: `.venv`, `.venv/bin` and `site-packages` are all `drwxrwxr-x`, and
`find site-packages -name '*.py' ! -perm -o=r` returns nothing. Nothing under `/app` is
written at runtime: the venv is built in the builder stage, `config/` is only read, and
`useradd -m` already provides a writable `/home/appuser`. The chart's
`readOnlyRootFilesystem: true` (`k8s/templates/deployment.yaml:38`) already prevents any
runtime write under `/app` in the cluster, so dropping the `chown` changes nothing there
and makes a plain `docker run` match it.

**Applied fix:** the review's — drop `chown -R appuser:appuser /app`, keep
`useradd -m -u 1000 appuser` and `USER appuser`.

**Added test:** `TestTheImageNeverGivesTheProcessOwnershipOfItsOwnCode`, following the
existing precedent of `TestTheComposeDatabaseIsNotPublishedToTheWholeNetwork`, which
already asserts on a deployment artifact from `tests/unit/test_config.py`. It scans
non-comment Dockerfile lines only, so the explanatory comment may name `chown -R`, with
a control asserting the non-root user is still created. Proven discriminating by
restoring the `chown` line and re-running.

## Skipped Issues

None.

## Verification

Run from `/home/init/native-speaker/ns-api-gateway` (the main checkout — no worktree; this
repository is a git submodule, so worktree detection misreports it), on branch
`gsd/v2.0-authentication-entitlements`, after the last commit:

| Gate | Baseline at HEAD | After |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1743 passed | 1747 passed (+4 new cases) |
| `pytest tests/schema -m schema` | 250 passed | 250 passed |
| `pytest tests/e2e -m e2e` | 354 passed | 354 passed |
| `ty check src` | 3 diagnostics | 3 diagnostics |

Plus CR-80's own acceptance command, `pytest -q -m ""` (every marker, which is what
exposes the cross-suite logging pollution): `1 failed, 2346 passed` before, all green
after.

No test was weakened. The three pre-existing cases the WR-01 behaviour change touched were
updated to the correct new expectation and each was re-checked against a reverse-applied
source hunk.

---

_Fixer: gsd-code-fixer, part 1 of 5_
_Iteration: 1_

---

## Part 2 of 5

# Phase 41 — Code Review Fix Report (fixer 2 of 5)

**Source review:** `41-REVIEW.md`
**Scope:** WR-20, WR-21, WR-22, WR-23, WR-24, WR-40, WR-41, WR-42 only.
**Iteration:** 1

**Summary:**
- Findings in scope: 8
- Fixed: 8
- Skipped: 0

All work was done directly in `/home/init/native-speaker/ns-api-gateway` on
`gsd/v2.0-authentication-entitlements`. No worktree was created, no branch was
made, and nothing was pushed.

---

## Fixed Issues

### WR-20: `ty` reports three errors, all in the auth adapters

**Files modified:** `src/nativespeaker/api/auth/app_store.py`,
`src/nativespeaker/api/auth/devicecheck.py`
**Commit:** `55ef60d`

`app_store.py:145` now reads
`status = None if data.status is None else _APPLE_STATUSES.get(data.status)`, so
the `None` case is stated rather than resting on `dict.get(None)`. The refusal
path is unchanged: an unknown Apple status still leaves `status is None` and
still raises `UnknownStoreSubscriptionStatus`.

`devicecheck.py` moves the object-shape test into `_decoded`, which now returns
`dict[str, object] | None`; `_parse_bit_state` tests `payload is None`. The two
`Never` key-type diagnostics go with the bare `isinstance(payload, dict)`
narrowing that caused them. `_decoded` has exactly one caller, and the outcome
for every input class is identical.

`ty check src` went from 3 diagnostics to **All checks passed!**

### WR-21: two concurrent claims on one device silently reopen each other's slot

**Files modified:** `src/nativespeaker/api/auth/devicecheck.py`,
`.planning/phases/41-post-auth-claim-anonymous-grant/41-SECURITY.md`
**Commit:** `f093b49`
**Status:** fixed as a recorded residual — there is no in-bounds code fix.

The race is real and I confirmed it against the current code. The anonymous
claim reads the pair at `services/auth.py:206` and writes it back at `:232` as
`bit0=True, bit1=state.bit1`; the registered claim reads at `:277` and writes at
`:298` as `bit0=state.bit0, bit1=True`. Both reads are taken before their own
transaction opens (SHARED-INVARIANTS forbids a provider call under a lock), the
two routes run against different `core.users` rows, and the per-user grant locks
therefore never intersect. Interleaved, the later write carries the earlier
writer's stale member and one device slot reopens.

Per rule 9 I weighed the remedy against the threat model before building
anything, and built nothing:

- Apple's `update_two_bits` offers no compare-and-swap, so a merge is not
  available at the vendor.
- SHARED-INVARIANTS § Global deletions forbids the two things that would close
  it: "No device-fingerprint or device-check component in any rate-limit key, in
  any form" and "no distributed lock, lease, or multi-phase-commit machinery".
- Re-reading the bits immediately before the write narrows the window but leaves
  it a read-modify-write race, at the cost of an extra Apple round trip on every
  claim. That is a subsystem's cost for no property, so it was rejected.
- The loss is one anonymous-tier grant (10 monthly credits) on a sub-$5 product.

**Corrections to the review's suggested remedy — both applied differently:**

1. The review proposes a six-line docstring on `write_bits_with_retry`.
   `AGENTS.md` § "Comments and docstrings" caps docstrings at three lines and
   forbids a docstring that describes what the entity is *not* ("Do not read this
   helper as making the pair atomic") or how the application works in general;
   `tests/unit/test_docstring_bar.py` enforces the three-line bar at baseline 0.
   The contract is carried instead by a single comment above the helper, which is
   the form AGENTS.md allows:
   `# Blind on both bits: Apple has no compare-and-swap, so a carried-forward bit can overwrite a newer value.`

2. The review proposes reopening T-41-06 as `residual`. `41-SECURITY.md` has no
   such status — its vocabulary is `open · closed · open — below high threshold
   (non-blocking)`. More importantly, T-41-06's own threat ("destroying Phase
   42's bit1 state") genuinely *is* mitigated: the write carries the queried bit1
   rather than fabricating one, which is exactly what `TestTheBit1CarryForward`
   proves. Reopening it as `high` would also have flipped `threats_open` off 0
   and marked the phase blocking for a threat that is not the one at issue.

   Recorded instead as a distinct threat, following the file's own precedent for
   T-41-08/T-41-09 (a risk with no in-bounds mitigation is `accept` + an
   Accepted Risks Log entry):
   - **T-41-31** — Tampering, medium, `accept`, `closed`, naming the two
     read→write spans and the two forbidding clauses.
   - **AR-41-03** — the acceptance, quoting both SHARED-INVARIANTS prohibitions.
   - T-41-06's mitigation cell rescoped to fabrication only, cross-referencing
     T-41-31, and its stale `services/auth.py:194` citation corrected to `:232`.
   - One audit-trail row added; the 2026-09-04 row was left intact because it
     records what that audit saw.

### WR-22: five cross-file line citations point at the wrong lines

**Files modified:** `src/nativespeaker/api/schemas/api.py`,
`src/nativespeaker/api/schemas/auth.py`, `src/nativespeaker/api/auth/firebase.py`,
`src/nativespeaker/api/auth/store_notifications.py`,
`src/nativespeaker/api/auth/app_store.py`
**Commit:** `6547819`

I read all five cited lines. All five were wrong as reported, and each now cites
the symbol instead of the number:

| Comment | Was | Now |
|---|---|---|
| `schemas/api.py:10` | `services/chats.py:96` (`human_message = Message(...)`) | `services/chats.py::ChatService.create_chat`'s `quota_service.charge` |
| `schemas/auth.py:41` | `devicecheck.py:93` (`return text` in `read_private_key`) | `devicecheck.py::_shared_body` |
| `firebase.py:163` | `crud/identities.py:155` (the `registered_at` guard) | `crud/identities.py::IdentitiesDB.upgrade_identity` and its `if user.email is None:` guard |
| `store_notifications.py:31` | `crud/subscriptions.py:300` (an argument in `append_event`) | `crud/subscriptions.py::SubscriptionsDB.write_subscription_grant` |
| `app_store.py:141` | "exactly as line 98 above" (`self._products = products`) | "exactly as the data-less arm above" |

**Correction:** the review's suggested rewrite of the `firebase.py` block also
silently drops the `04-users-me.md:53` reference. I checked it — line 53 is the
"Explicit DELETIONS" bullet carrying "no email sync or provenance tracking",
which is the correct target, and a spec file is not the moving target this
finding is about. It was kept.

### WR-23: four operator faults on the restore read collapse into one log line

**Files modified:** `src/nativespeaker/api/auth/google_play.py`,
`tests/unit/test_restore_proof.py`, `tests/unit/test_google_play_notifications.py`
**Commit:** `6a3eb60`

`read_for_restore` now names each repair on the one log line it already writes:

- no Play credential → `play_restore_unconfigured`
- `package_name` absent or dot-only → `play_restore_package_unusable`
- transport failure or refused credential refresh → `play_restore_transport`
- a non-2xx that is not 404/410 → `play_restore_read`, with `cause="refused"`
  (4xx) or `cause="failed"` (5xx)
- a 2xx body this build cannot read → `play_restore_unparseable`

The client-visible answer is unchanged everywhere: one class (`Unavailable`), one
status (503), one code. `stage` and `cause` reach `log_fields()` only, and
`ErrorResponse` carries exactly one field, so nothing new is disclosed.

**Two corrections to the review:**

1. The review counts **four** collapsed arms. There are **five** — it missed the
   unparseable-2xx arm at the end of the function, which also raised
   `Unavailable(stage=RESTORE_READ_STAGE)`. All five are now distinguished.

2. The review's remedy adds
   `logger.error("google_play_restore_read_refused", status_code=...)` before the
   raise. That was **not applied**, because it would break the invariant this
   very review cites elsewhere. SHARED-INVARIANTS § Fail-closed defaults: "A
   rejection leaves exactly one structured security-log line carrying its stable
   internal result." `Unavailable` has `log_level = WARNING` and writes its own
   line, so an added `logger.error` makes that branch two lines. (The webhook arm
   `_play_answer_is_usable` may do this only because `InternalError` logs nothing
   of its own — its comment says exactly that.) WR-62 in the same review
   independently forbids it: "Do not add a second `logger` call: Phase 40 WR-51
   already removed a double log line for a refusal, and the invariant allows
   exactly one."

   The status distinction is carried instead on the existing single line, as
   `cause`, using two words this codebase owns rather than Play's own status —
   `ProviderLookupError.__init__`'s comment binds both fields to "Plain strings,
   both of them ours: no provider text is ever admissible in either field", and
   `TestTheLookupArmsCarryStageAndOnlyABoundedCause` holds it to a closed set.

Eight test expectations were updated to the corrected stages, and the non-2xx
case now asserts the full `log_fields()` dict rather than the stage alone.

### WR-24: `claims_from_payload` raises `KeyError` on a missing `iss`

**Files modified:** `src/nativespeaker/api/auth/jwt_verifier.py`,
`tests/unit/test_jwt_security.py`
**Commit:** `29e925b`

Confirmed: `claims_from_payload` is called at `:235` and `:246`, both **after**
the `try` block closes, so a `KeyError` from `payload["iss"]` escapes
`JWTVerifier.verify`'s bare `except Exception` and 500s a caller owed a 401 —
the precise outcome the `:227` comment says cannot happen. `iss` is now fetched
with `.get` like `sub` and answered with `_MISSING_CLAIM_REASONS["iss"]`,
sourced from the map rather than restating `BoundedReason.issuer_mismatch`, so
the two paths cannot drift.

Added `TestClaimsFromPayloadIsTotalOnEveryShape` (6 cases: absent/empty `iss`,
absent/empty `sub`, agreement with `_MISSING_CLAIM_REASONS`, and a
complete-payload control). **Proven to fire:** reverse-applying the source hunk
turns 3 of the 6 red; restoring it turns them green.

### WR-40: both grant writers take a detached ORM row

**Files modified:** `src/nativespeaker/api/crud/grants.py`,
`src/nativespeaker/api/services/auth.py`, `tests/unit/test_claim_precedence.py`,
`tests/unit/test_claim_ordering.py`, `tests/unit/test_spent_free_grant_refusal.py`,
`tests/unit/test_conversion_carries_usage.py`, `tests/schema/test_grant_locks.py`
**Commit:** `6195235`

`activate_anonymous_device_grant` and `activate_registered_account_grant` now
take `issuer: str, subject: str` instead of `identity_row: ExternalIdentity`.
Both read only `.issuer`/`.subject` off it before re-resolving into their own
session as `stored`, so nothing was lost — and the stale, detached, barrier-time
copy can no longer reach a writer whose platform pin (`:170-175`) and
lifetime-slot refusal (`:182`) are the two refusals the endpoint exists to
enforce. `ExternalIdentity` is no longer imported by `crud/grants.py` at all.

Callers pass `issuer=identity.issuer, subject=identity.subject`, which are plain
`str` fields on `Identity` (`schemas/auth.py:104-105`), not ORM attributes.

The schema fixtures in `test_grant_locks.py` had been calling
`resolve_existing(...)` purely to hand the row straight back to the writer, which
then resolved it again; those setup reads are now gone and the pair is passed
directly. `_Account` carries `issuer`/`subject` instead of `identity_row: object`.

Added `TestTheWritersTakeTheVerifiedPairAndNoOrmRow` to `test_claim_ordering.py`:
both writers must annotate `issuer`/`subject` as `str`, and no parameter of
either may be a mapped `SQLModel` row — with a control proving the walk fires on
a synthetic widened signature.

### WR-41: the conversion's usage carry-over relies on an unasserted seed relationship

**Files modified:** `src/nativespeaker/api/crud/grants.py`,
`tests/schema/test_constraints.py`
**Commit:** `bf10c00`

Confirmed: the relationship (`registered` ≥ `anonymous`) was stated twice in
prose — `migrations/20260818_01_initial-release.sql:122` and the code comment —
and enforced by nothing executable.

Added `TestTheTierSizingInvariantTheConversionRelisOn` to the schema suite,
bound the way `TestTheFreeGrantSourceSetMatchesTheIndex` binds its sibling: it
reads the **applied seed rows** rather than restating them, and keys off the
production constants `ANONYMOUS_TIER_ID` / `REGISTERED_TIER_ID` rather than
string literals, so a renamed tier id fails here too. It asserts both keys are
present before comparing, so a renamed seed row cannot make the comparison
vacuous. The code comment now names the test that holds it.

**Proven to fire:** temporarily lowering the seeded `registered` allowance from
50 to 5 in the migration turns the case red; the migration was restored and
`git diff migrations/` is empty.

### WR-42: `Chat.user` is an unused lazy relationship

**Files modified:** `src/nativespeaker/api/tables/chats.py`,
`tests/unit/test_tables_metadata.py`
**Commit:** `e9ee128`

Confirmed unread: `grep` over `src/` and `tests/` finds no access, and
`ChatsDB.get_chat` eager-loads `Chat.messages` alone. Deleted, along with the
now-unused `User` import — `tables/__init__.py` imports `User` directly, so the
model stays registered in `SQLModel.metadata` and the `core.users.id` foreign key
still resolves (the schema suite's 251 cases confirm it).

The review suggests leaving a three-line tombstone comment naming the
`lazy: "raise"` shape a future link would need. Not applied: that is the
multi-line narrating comment block `AGENTS.md` forbids and WR-63 is removing
elsewhere in this same review. The rule is held as structure instead —
`TestTheOnlyRelationshipIsTheOneAQueryEagerLoads` walks every mapped model in the
package and asserts the declared relationship set is exactly `{"Chat.messages"}`,
so a second one fails at the test rather than at runtime.

---

## Verification

All five gates were run against the final tree, in the main checkout (no
worktree was created, so these numbers are reproducible from the tree as it
stands):

| Gate | Baseline | Result |
|---|---|---|
| `.venv/bin/ruff check src tests` | clean | **All checks passed!** |
| `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1747 passed | **1759 passed** (+12 new cases) |
| `.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema` | 250 passed | **251 passed** (+1 new case) |
| `.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e` | 354 passed | **354 passed** |
| `.venv/bin/ty check src` | 3 diagnostics | **0 diagnostics** |

No test was weakened. Eight expectations in `test_restore_proof.py` and one in
`test_google_play_notifications.py` were updated to the corrected stage labels
required by WR-23, and one was strengthened from a stage comparison to a full
`log_fields()` comparison.

Twelve new unit cases: 6 for WR-24, 5 for WR-40, 1 for WR-42. One new schema
case for WR-41. Every docstring written here is three lines or fewer, and
`test_docstring_bar.py` stays at baseline 0 for both `src` and `tests`.

`git status --short` is clean apart from the two partial fix reports. Branch is
still `gsd/v2.0-authentication-entitlements`. Nothing was pushed.

---

_Fixer: Claude (gsd-code-fixer), fixer 2 of 5_
_Iteration: 1_

---

## Part 3 of 5

# Phase 41: Code Review Fix Report (part 3 of 5)

Findings WR-60, WR-61, WR-62, WR-63, WR-80, WR-81, WR-82, WR-83, WR-84 and WR-85.

**Summary:** 10 in scope, 10 fixed, 0 skipped. No finding in this batch was factually wrong,
but two remedies were narrowed on the merits — see the corrections under WR-60 and WR-63.

## Fixed Issues

### WR-60: the restore wrote the grant at the pre-lock tier

**Files:** `src/nativespeaker/api/services/restore.py`,
`src/nativespeaker/api/crud/subscriptions.py`, `tests/unit/test_restore_proof.py`
**Commit:** 6f7be47

The tier was copied out of the pre-lock read and never refreshed, while only the status was
re-read under the grant locks. The re-read is now `read_subscription` (the whole row) rather
than `read_status` (one column); the tier is captured into `tier_read` *before* that read,
because `populate_existing=True` refreshes `stored` in place and would otherwise make the two
sides of the comparison the same object. `read_status` lost its only caller and was deleted
along with its two test doubles.

**Correction to the suggested remedy.** The review's code refuses whenever
`settled is not None and (settled.status != status or settled.tier_id != tier_read)`. With
`stored is None` — adoption-with-creation — `tier_read` is `None`, so that expression refuses
on *every* row a webhook inserted inside the window, including one that agrees on status. That
silently deletes the documented insert-only lost-race path (`restore.py`, the `if stored is
None:` arm), which routes that exact state to `insert_subscription` -> `lost_race` -> 500 so
the client retries. The tier comparison is therefore gated on `tier_read is not None`; the
status comparison keeps its existing shape. Behaviour on the adoption path is unchanged.

Regression guard: `tests/unit/test_restore_proof.py::TestTheTierIsReReadUnderTheGrantLocksAsWell`.
`_GrantRecorder` now counts its reads and mutates the row on the second one, which is what
`populate_existing` does in production. Reverse-applying the source hunk turns both new cases red.

### WR-61: the appended event named a tier the row no longer carried

**Files:** `src/nativespeaker/api/services/subscriptions.py`,
`tests/unit/test_subscription_attribution.py`
**Commit:** f17d7ea

`old_tier_id` moved from the pre-lock read to the row read under the grant locks. It has no
reader between the two points, so the move is behaviour-preserving except in the race it fixes.

Regression guard: `TestTheAppendedEventNamesTheTierTheLocksSettledOn` — a rival that *moves*
the tier and a rival whose *insert* the pre-lock read missed, plus a no-rival control. Proven
to discriminate: reverse-applying the source hunk fails exactly the two rival cases (the
control stays green).

### WR-62: nine refusals collapsed into one field-less log line

**Files:** `src/nativespeaker/api/errors.py`, `src/nativespeaker/api/crud/grants.py`,
`src/nativespeaker/api/services/auth.py`, `src/nativespeaker/api/services/restore.py`,
`tests/unit/test_spent_free_grant_refusal.py`, `tests/unit/test_claim_precedence.py`,
`tests/unit/test_rejection_vocabulary.py`, `tests/unit/test_conversion_carries_usage.py`,
`tests/schema/test_grant_locks.py`
**Commit:** 5f4bde9

`ClaimRefused` and `RestoreRefused` take an optional `cause` and surface it through
`log_fields()`, exactly as `ProviderLookupError` already does. **One** line per refusal, still —
no second `logger` call anywhere, as SHARED-INVARIANTS § Fail-closed defaults requires and as
the review's own note insists. `status`, `code` and the response body are untouched, so the
anti-oracle rule holds: the client still cannot distinguish the branches.

The two writers now return `tuple[ActivationOutcome, str | None]` rather than splitting
`ActivationOutcome.refused` into named members. That was chosen because it leaves every existing
`is ActivationOutcome.refused` assertion in five test files intact — only the four helper
call sites unwrap the pair. The nine labels:

| Site | cause |
|---|---|
| anonymous writer, non-anonymous stored row | `identity_not_anonymous` |
| anonymous writer, platform pin | `platform_pinned_to_another` |
| anonymous writer, grant held or slot spent | `active_grant_or_spent_slot` |
| anonymous writer, prior free grant | `prior_free_grant` |
| registered writer, claimant not registered | `identity_not_registered` |
| registered writer, other source held | `other_grant_held` |
| registered writer, row this window cannot see | `unseen_active_grant` |
| registered writer, spent slot | `spent_slot_without_a_registered_grant` |
| registered writer, registered grant held | `registered_grant_held` |
| `AuthService._settle`, race with nothing to re-read | `lost_race_without_a_readable_grant` |

The restore's four `RestoreSubscriptionNotEntitled` sites carry `status_not_entitled`,
`status_moved_under_the_locks`, `tier_moved_under_the_locks` (WR-60's new arm) and
`term_closed`; `_answer_as_the_winner_left_it` carries `another_account_won_the_race`.

Regression guards: `TestEachRefusalNamesTheArmThatFiredIt` (two arms, two labels, and a
lost race that names none), the two new `test_the_base_s_cause_is_the_one_channel_and_it_moves_no_body`
parametrisations, and two service-level cases asserting the handler's single line carries the
label end to end.

### WR-63: multi-line narrating comment runs

**Files:** `src/nativespeaker/api/services/{auth,chats,quota,restore,subscriptions,sync}.py`,
`src/nativespeaker/api/errors.py`
**Commit:** 6c6a1d4

All 21 remaining runs of three to seven lines are gone (the 22nd, `restore.py:93-98`, was
already compressed by WR-60's commit). A detector over `services/` and `routers/` now reports
none. Each block kept the one clause that resolves the ambiguity at the line below it; the
design rationale stays in the phase context files, which already hold it. `routers/` had no
run of three or more.

**Scope correction.** AGENTS.md § "Comments and docstrings" says *One line each*, and 25
**two**-line runs remain across `services/`, `routers/` and `llm.py`. Those were left alone:
the finding names runs "of three to seven lines" and counts 22, and sweeping every two-line
comment in the package would touch files outside this finding's list for no stated defect. The
comments this batch *wrote* are all single lines, per the batch rule — including the ones
introduced by WR-60 and WR-62, which were collapsed here.

### WR-80: `spy_on` froze a structlog level onto the module logger

**Files:** `tests/e2e/conftest.py`, `tests/unit/test_claim_precedence.py`
**Commit:** 4beab68

Reproduced first, against the real proxy:

```
before: False        # `warning` is not in the proxy's __dict__
during: True
after undo: True     # <- monkeypatch re-setattr'd it instead of deleting it
frozen attr: <bound method ... of <BoundLoggerFilteringAtNotset(...)>>
```

`spy_on` now replaces the whole `logger` name — which does live in the module `__dict__`, so
monkeypatch restores it exactly — with a `_SpyLogger` carrying only the levels asked for. Every
call site already passes `<module>.logger`, so none changed.

The same defect was in the two service-level cases WR-62 added an hour earlier; they now go
through a `_handler_warnings` helper that replaces the whole name. Fixed here rather than left
for a later review.

### WR-81: both Firebase credential fixtures could leak a permanent user

**File:** `tests/e2e/conftest.py`
**Commit:** d9b6e0a

In both fixtures the `try` now opens at the statement after `httpx.post` returns, with
`raise_for_status`, the body parse and the `localId` subscript inside it, and `delete_user`
guarded on `local_id is not None`.

### WR-82: the restore term boundary never reached the boundary

**File:** `tests/e2e/test_restore_subscription.py`
**Commit:** 1bc99ef

The case now takes `pinned_evaluation_instant` and scripts `expires_at=pinned_evaluation_instant`,
so `term_ends_at == evaluated_at` is what the predicate sees.

Mutation proof (`restore.py:108`, `<=` -> `<`): 35 passed before the fix; 1 failed / 34 passed
after it, failing on this case; 35 passed again after reverting. No mutation left in the tree.

### WR-83: the three Apple-failure arms never asserted the lifetime marker

**File:** `tests/e2e/test_claim_anonymous_grant.py`
**Commit:** 0e40ebe

One line added to each of the three cases, as the registered twin already has.

Mutation proof (the review's own mutant — burn `free_grant_consumed_at` on the `state.bit0`
arm): 11 passed before the fix; 1 failed / 10 passed after it; 11 passed again after reverting.

### WR-84: the D-09 repeat case proved counts, not "writes nothing"

**File:** `tests/e2e/test_claim_anonymous_grant.py`
**Commit:** 55d3216

Added `_usage_of` (identical to the registered twin's) and read the rows: the grant's id,
status, `ends_at` and `updated_at`, and the usage row's period, count and `updated_at`.

Mutation proof (the review's own mutant — the repeat arm rewrites `held[0].updated_at` and
commits): 11 passed before the fix; 1 failed / 10 passed after it; 11 passed again after reverting.

### WR-85: the challenge-expiry boundary was a magic 299

**File:** `tests/e2e/test_challenge_store.py`
**Commit:** ebc3d3d

`299` is now `CHALLENGE_TTL_SECONDS - 1`, imported from the crud, and the closed half of the
boundary has its own case claiming at the row's own `expires_at`.

Mutation proof (`challenges.py:72`, `>` -> `>=`): 31 passed before the fix; 1 failed / 31 passed
after it, failing on the new case; 32 passed again after reverting.

## Skipped Issues

None.

## Verification

Run in the main checkout (`workflow.use_worktrees` was overridden to false for this run: the
repository is a git submodule, so worktree detection misreads its `.git` file). No worktree was
created and no branch was switched; every commit is on `gsd/v2.0-authentication-entitlements`.

| Gate | Baseline | After |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1759 passed | 1777 passed |
| `pytest tests/schema -m schema` | 251 passed | 251 passed |
| `pytest tests/e2e -m e2e` | 354 passed | 355 passed |
| `ty check src` | 0 diagnostics | 0 diagnostics |

The 18 new unit cases are the regression guards listed above. The e2e suite gains exactly one
case, WR-85's closed half of the challenge boundary; WR-82, WR-83 and WR-84 strengthened
existing cases in place.

---

_Fixer: Claude (gsd-code-fixer), part 3 of 5_
_Iteration: 1_

---

## Part 4 of 5

# Phase 41: Code Review Fix Report — part 4 (WR-110 .. WR-116)

**Source review:** `.planning/phases/41-post-auth-claim-anonymous-grant/41-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 7
- Fixed: 7
- Skipped: 0

Verification ran in the main checkout (`/home/init/native-speaker/ns-api-gateway`), not in a
worktree — this repository is a git submodule, so its `.git` is a file and worktree detection
misreads it. The numbers below are reproducible from that tree.

## Fixed Issues

### WR-110: three suites mirror `get_db` with the commit that WR-01 deleted from production

**Files modified:** `tests/unit/test_claim_precedence.py`,
`tests/unit/test_claim_precedence_registered.py`, `tests/unit/test_create_user_precedence.py`
**Commit:** `cdc05bf`

Deleted the hand-written `_db` generator and its `dependency_overrides[get_db]` entry from all
three `client` fixtures, gave `_StubSession` (in `test_claim_precedence.py` and
`test_create_user_precedence.py`) `__aenter__`/`__aexit__`, and set
`app.state.session_factory = lambda: session` so the production `get_db` runs — the same shape
`test_exception_handlers.py::generator_session_client` already uses. The now-unused `get_db`
import went with it.

**Correction to the finding's framing.** The review is right that the mirror had drifted and that
its comment ("Mirrors `app/dependencies.py::get_db` exactly") was false. It is also right that this
is drift, not a false pass — and the fix therefore does **not** newly discriminate any mutation.
Proven both ways:

- With the fix applied, deleting the `except Exception: await session.rollback()` arm from
  `get_db` leaves all 106 cases in the three files green (their `session.rollbacks >= 1`
  assertions are satisfied by `AuthService`'s own rollback, not by the dependency's).
- With the fix applied, re-introducing the WR-01 bug (`await session.commit()` after the yield)
  also leaves all 106 green — no case in these files asserts `session.commits`.
- The dependency's own behaviour is owned elsewhere and is guarded: the same rollback-arm deletion
  fails `test_exception_handlers.py::TestARejectionSurvivesTheSessionsRollbackOnTheWayOut::
  test_the_generators_rollback_arm_really_ran`.

So the root cause fixed here is the duplication itself: there is no longer a second copy of
`get_db` that can drift, and no comment claiming a fidelity it did not have. Adding a
`session.commits` assertion to these three suites was rejected as over-engineering — their subject
is claim/creation precedence, and `test_exception_handlers.py` already owns `get_db`.

### WR-111: `_verify()` omits `evaluated_at`, forwarding a `Depends` object into `play_subscriptions.read`

**Files modified:** `tests/unit/test_google_play_notifications.py`
**Commit:** `de16931`

`_verify` now takes `evaluated_at: datetime = EVALUATED_AT` and passes it as the dependency's
fourth positional argument, so no case runs against the `Depends` sentinel. Added
`TestTheEntitlementDecisionUsesTheInstantTheRequestCaptured::
test_the_dependency_forwards_the_solver_resolved_instant_to_the_read`, which drives a distinct
instant (`LAPSED`) through the dependency and asserts `play.calls[0]["evaluated_at"] == LAPSED`.

**Discrimination proved:** replacing `evaluated_at=evaluated_at` with `evaluated_at=datetime.now(UTC)`
at `src/nativespeaker/api/app/dependencies.py:234` fails exactly the new case (1 failed, 116
passed); reverted, 117 passed.

### WR-112: `_stub_request`'s `tokens=` hook supplied by no case; `dependencies.py:208` untested

**Files modified:** `tests/unit/test_google_play_notifications.py`
**Commit:** `a3b326c`

Added `_RefusingTokens` (raises `NotificationRejected(stage="bad_signature")`) and
`TestTheTokenIsCheckedBeforeTheBodyIsParsed::
test_an_unverifiable_token_refuses_before_the_body_is_decoded`, which sends an undecodable body
with a refusing token and asserts the stage plus `play_logs.records("error") == []` — the decode's
own ERROR line is the observable a body parsed ahead of the token check would leave.

**Discrimination proved:** moving `developer_notification_from(body.message.data)` above the
`google_push_tokens.verify` call fails exactly the new case (1 failed, 117 passed); reverted, 118
passed.

### WR-113: anonymous race-loss case requests `devicecheck` and never reads it

**Files modified:** `tests/unit/test_claim_precedence.py`
**Commit:** `2025d2f`

Added `assert devicecheck.write_calls == []` to
`test_the_race_loser_answers_two_hundred_and_still_consumes` and to
`test_a_lost_race_whose_re_read_finds_nothing_is_refused_rather_than_reported_as_a_grant`, with a
one-line comment each (AGENTS.md's comment rule; the registered sibling's three-line block was not
copied).

**Discrimination proved:** replacing the `if wrote:` guard at
`src/nativespeaker/api/services/auth.py:219` with `if True:` fails
`test_the_race_loser_answers_two_hundred_and_still_consumes`; reverted, 41 passed.

**Note on the second case.** The mutation does not reach it: with `won_by == []` the service raises
`ClaimRefusedUnderLock` before the write block, so its `write_calls == []` is a backstop rather
than a live guard on the `wrote` branch. It still removes the unused-parameter defect and pins that
the refusing arm burns no device slot, so it was kept.

### WR-114: `ActiveGrantOutsideItsTerm` is the only claim arm with no route-level status/body assertion

**Files modified:** `tests/unit/test_claim_precedence.py`,
`tests/unit/test_claim_precedence_registered.py`
**Commit:** `75b8f27`

Added a named case to each file beside its siblings:
`test_a_grant_marked_active_outside_its_term_is_refused_and_still_consumes` (anonymous) and
`test_a_grant_marked_active_outside_this_window_is_refused_and_still_consumes` (registered), each
asserting `403`, `REFUSED`, one consumption, no activation and no DeviceCheck read.

**Discrimination proved:** replacing both `raise ActiveGrantOutsideItsTerm` sites
(`services/auth.py:196` and `:252`) with `raise MultipleEffectiveGrantsError(...)` fails exactly
the two new cases (2 failed, 79 passed); reverted, 81 passed.

### WR-115: six wall-clock tests lack `@pytest.mark.timing`

**Files modified:** `tests/unit/test_devicecheck_adapter.py`, `tests/unit/test_firebase_retry.py`
**Commit:** `fd1216b`

Marked both `TestTheAttemptsAreSeparatedInTime` classes with `@pytest.mark.timing`, matching
`test_jwks_offload.py`'s use of the marker `pyproject.toml:68` declares.

**Discrimination:** this is a reporting convention, not an assertion, so the check is selection:
`pytest tests/unit -m timing` now selects 8 cases (the 2 pre-existing jwks ones plus these 6),
where it previously selected 2. The default `addopts` does not deselect `timing`, so all six still
run in the ordinary unit sweep — the unit total rose only by the four cases added under WR-111,
WR-112 and WR-114 (1777 -> 1781).

### WR-116: `test_the_two_forbidden_arms_answer_the_same_status_and_body` asserts the bodies DIFFER

**Files modified:** `tests/unit/test_exception_handlers.py`
**Commit:** `653d3ac`

Renamed to `test_the_two_forbidden_arms_share_a_status_and_keep_distinct_codes` and extended the
docstring by one line to say why. The assertion was left alone.

**Spec check (rule 5), which settles which side is wrong.** SHARED-INVARIANTS § Errors scopes the
anti-oracle rule *within* a class: "Within a class, body, status, and copy are identical across
every triggering branch (anti-oracle)" and "Every error branch of the same class returns identical
status, body, and timing". `NotLinked` (`errors.py:456`, `operation_not_allowed`) and `BlockedUser`
(`errors.py:402`, a subclass of `AccountUnavailable`, `account_unavailable`) are two different
classes, so nothing requires them to match. The barrier section is explicit that an unlinked caller
and a blocked one carry different codes: "On every other route an unlinked caller rejects
`preauth_identity_not_allowed`; historical/blocked reject `account_unavailable` (mutually
indistinguishable to clients)" — "mutually" binds historical to blocked, which is the pair
`test_the_two_arms_are_indistinguishable_to_the_client` (line 405) already pins. So the `!=` is
correct and the name was wrong.

**Discrimination proved:** changing `NotLinked.code` to `"account_unavailable"` fails the renamed
case (and, as a second signal, the duplicate-code startup tripwire); reverted, 55 passed.

## Skipped Issues

None.

## Verification (main checkout, end of part 4)

| Gate | Result | Baseline |
|---|---|---|
| `ruff check src tests` | All checks passed | clean |
| `pytest tests/unit` | 1781 passed | 1777 passed (+4 new cases) |
| `pytest tests/schema -m schema` | 251 passed | 251 passed |
| `pytest tests/e2e -m e2e` | 355 passed | 355 passed |
| `ty check src` | All checks passed (0 diagnostics) | 0 |

`tests/unit/test_docstring_bar.py`: 9 passed. `git status --short` clean apart from the partial fix
reports. Branch: `gsd/v2.0-authentication-entitlements`. No mutation left in the tree —
`git diff src/` is empty at every checkpoint above.

---

_Fixer: Claude (gsd-code-fixer), part 4 of 5_
_Iteration: 1_

---

## Part 5 of 5

# Phase 41: Code Review Fix Report — part 5 (WR-140 … WR-147)

**Source review:** `41-REVIEW.md`
**Scope:** WR-140, WR-141, WR-142, WR-143, WR-144, WR-145, WR-146, WR-147.
Every fix was mutation-proved: the production code the case guards was broken, the case was
observed failing, and the mutation was reverted. No mutation is left in the tree.

## Fixed Issues

### WR-140: the restore's COMMIT case carried no SQLSTATE — fixed, remedy corrected

**Files:** `tests/unit/test_restore_proof.py` **Commit:** `fda8b08`

The defect is real: `Exception("23503")` carries the code only in its message, so the case
certified that a violation carrying *no readable code at all* is a lost race. Fixed by hoisting
the file's own `_Orig` stand-in above its first use and driving the arm with
`_Orig(DEFERRED_KEY_VIOLATION)`.

**Correction to the review.** The review asks for `_violation(UNIQUE_VIOLATION)` and for
`restore.py:185` to be narrowed to `if not is_unique_violation(conflict): raise`. That is
self-defeating. The two `DEFERRABLE INITIALLY DEFERRED` constraints on `core.access_grants` are
**foreign keys** (`migrations/20260818_01_initial-release.sql:241-247`), so COMMIT evaluates them
into `23503`, never `23505`. Applying the suggested narrowing was tried and it refuses the one
violation the arm exists to catch:

```
FAILED test_a_deferred_foreign_key_at_commit_is_the_lost_race_the_flushes_report
FAILED test_a_violation_carrying_no_readable_code_at_commit_is_the_lost_race_too
```

`23505` also cannot reach COMMIT: every writer flushes its own statement and classifies it there
(`crud/subscriptions.py:126-139, 266-276, 292-302, 344-348, 390-396`). The production arm is
therefore left unconditional, and — per the review's own stated fallback — a second case now says
so out loud rather than leaving the file looking as though it tested a code.

No contradiction with the flush arms exists either: an FK at the **flush** is a broken invariant,
an FK at **COMMIT** is the deferred pair. That is exactly what the class name already claims —
"the deferred keys are classified where they are evaluated".

Mutation proof: replacing the arm with `raise` fails both cases; the suggested narrowing fails
both cases; reverted.

### WR-141: the same defect in the subscriptions suite

**Files:** `tests/unit/test_subscription_attribution.py` **Commit:** `6512c9c`

Added the `_Orig` stand-in this file lacked and gave `_RefusingSession` a `sqlstate` parameter
defaulting to the deferred keys' own `23503`, plus the explicit unreadable-code case. The
review's proposed `UNIQUE_VIOLATION` default is wrong for the same reason as WR-140.

Mutation proof: replacing `services/subscriptions.py:181-185` with `raise` fails both cases;
reverted.

### WR-142: `_UpsertResult.rowcount` pinned to 1

**Files:** `tests/unit/test_subscription_attribution.py` **Commit:** `3636f03`

`_UpsertResult` now takes its row count, `_UpsertSession` takes `claim_wins`, and
`_RecordingSubscriptions.claim_wins` threads it in. New class
`TestTheUpsertsOwnLostClaimIsAnsweredByTheService`: a restore that adopted the unowned row first
makes the writer answer `lost_race`, and the service rolls back, writes
`store_notification_race_lost` and raises `InternalError` having reached neither the purchase row
nor the grant. A control asserts the winning claim still records the owner.

Mutation proof: dropping the `_settle` after the upsert fails the case; making the crud's
`if not claimed:` a no-op fails it; both reverted.

### WR-143: the lost owner claim and `_answer_as_the_winner_left_it` had no default-run case

**Files:** `tests/unit/test_restore_proof.py` **Commit:** `bd99f31`

Added `_UnownedRecorder` (an unowned canonical row, so `restore.py:139` is entered) with
`claim_subscription_owner` scripted both ways, and `TestALostAdoptionClaimIsAnsweredAsTheWinnerLeftIt`:
a claim this same account already won returns quietly, another account's win raises
`RestoreSubscriptionNotEntitled`, and both roll back once having written no grant. The control
also pins that adoption spends none of D-10's month cap.

Mutation proof: making `if not claimed:` a no-op fails two cases; loosening the re-read to
`if settled is not None:` fails the other-account case; both reverted.

### WR-144: the restore suite drove the service with a shape the barrier cannot produce

**Files:** `tests/unit/test_restore_proof.py` **Commit:** `c05b7a8`

`_caller()` now returns a `LinkedIdentity` carrying both rows, as `tests/unit/conftest.py:119-121`
requires of every double for `get_linked_identity`.

Mutation proof: adding a linked-only dereference (`identity.identity.provider`) to
`RestoreService.restore` fails 21 cases against the old `Identity(identity=None)` double and
passes against the fixed one; reverted.

### WR-145: the period scan matched one quoting only

**Files:** `tests/unit/test_monthly_period.py` **Commit:** `30cce0f`

`FORMAT` became `SPELLINGS = ('"%Y-%m"', "'%Y-%m'", ":%Y-%m}")` and the walk matches any of them.
Two controls were added: one that all three spellings of the derivation are matched, one that
`logs.py`'s `"%Y-%m-%d %H:%M:%S"` is matched by none.

Mutation proof: a single-quoted second copy planted in `services/restore.py` fails
`test_only_the_one_function_formats_a_period`; so does an f-string format-spec copy; both
reverted. Both were invisible to the old scan.

### WR-146: the flip's `email` fill had no case

**Files:** `tests/unit/test_identity_flip.py` **Commit:** `e52b321`

Added `test_an_unset_email_takes_the_verified_address` beside its `registered_at` sibling, the
other half of the `req~users-upgrade-step-07~1` fold point.

Mutation proof: deleting `crud/identities.py:160-162` fails the new case and nothing else in the
default run; reverted.

### WR-147: the `/users/me` refusal never asserted a header

**Files:** `tests/unit/test_users_me.py` **Commit:** `b442eef`

`assert "cache-control" not in response.headers` now backs the first half of the case's name.

Mutation proof: making the shared handler set `Cache-Control: no-store` fails all three
parametrisations; reverted.

## Skipped Issues

None.

## Verification

Run in the main checkout (`workflow.use_worktrees` treated as false: this repository is a git
submodule, so its `.git` is a file and worktree detection is unreliable here).

| Gate | Baseline | After |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1781 passed | 1791 passed |
| `pytest tests/schema -m schema` | 251 passed | 251 passed |
| `pytest tests/e2e -m e2e` | 355 passed | 355 passed |
| `ty check src` | 0 diagnostics | 0 diagnostics |

The ten new unit cases are the coverage WR-140 … WR-147 asked for. No source file outside the
tests was changed by this part.

---

_Fixer: gsd-code-fixer, part 5 of 5_

---

_Fixer: Claude (gsd-code-fixer x5, sequential; merged by orchestrator)_
_Iteration: 1_
