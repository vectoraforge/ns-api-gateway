---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
plan: 06
subsystem: api
tags: [postgres, sqlalchemy, sqlmodel, fastapi, pytest, auth, challenges]

requires:
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-01: D-01, the rule that a SQL comparison against the current time uses func.clock_timestamp()"
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-03: AuthService hands no crud writer an instant, so only the two challenge calls were left"
  - phase: 47-stop-threading-an-evaluation-instant-through-the-layers
    provides: "Plan 47-05: no test overrides get_evaluated_at, and app/dependencies.py is down to three occurrences"
provides:
  - ChallengesDB.issue, .claim and .consume take no datetime
  - The claim's expiry predicate and its claimed_at write are one func.clock_timestamp() evaluation
  - The claim UPDATE is the module-level _claim_statement, so a test compiles the production statement
  - routers/auth.py declares no datetime dependency and imports no datetime
  - AuthService takes and holds no datetime, and get_auth_service declares none
affects: [47-07, 48, 49, 50]

actuals:
  tokens: 11811
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "A SQL comparison against the current time uses func.clock_timestamp(), never func.now()"
    - "A statement a test must read is a module-level function, so the test compiles it and never mirrors it"
    - "An expiry case arranges the stored row with a direct UPDATE, because the store reads its own clock"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/challenges.py
    - src/nativespeaker/api/routers/auth.py
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/app/dependencies.py
    - tests/unit/conftest.py
    - tests/unit/test_challenge_ids.py
    - tests/unit/test_create_user_body.py
    - tests/unit/test_challenge_endpoint.py
    - tests/unit/test_create_user_rollback.py
    - tests/unit/test_conflict_classification.py
    - tests/unit/test_sync_clock_capture.py
    - tests/e2e/test_challenge_store.py
    - tests/schema/test_create_atomicity.py
    - tests/schema/test_create_race.py
    - tests/schema/test_claim_race.py

key-decisions:
  - "The claim UPDATE moved to a module-level _claim_statement, mirroring _effective_grants_statement in crud/grants.py. Without it the compiled-SQL case would compile a copy of the statement and could pass while production drifted."
  - "issue keeps a Python clock read because expires_at is returned to the caller and goes into the response body. claim and consume use the database clock."
  - "The compiled-SQL case sits in its own class, not in the asyncio-marked class, because it touches no database. Inside the marked class pytest-asyncio warned on a sync function."
  - "Three schema helpers now seed expires_at from the live clock. Their NOW is 2026-08-23, so the database clock reads every seeded challenge as expired and 44 schema cases failed."
  - "test_sync_clock_capture.py lost get_auth_service from one parametrized row, which is what plan 47-01 did for get_chat_service. The unit count is 1935, one below the 1936 baseline, for that reason alone."
  - "The plan says uv run pytest. The project rule is .venv/bin/pytest with the schema and e2e markers, which is what was run."

patterns-established:
  - "Pattern 1: a statement that carries a property a test must assert is built by a module-level function; the test compiles that function's result with literal_binds"
  - "Pattern 2: a compiled-SQL assertion carries a positive control, so an empty compile cannot pass the negative check"
  - "Pattern 3: a repeat-write case reads the first write back, repeats, and compares, instead of pinning an instant"

requirements-completed: []

coverage:
  - id: D1
    description: "ChallengesDB.issue, .claim and .consume take no datetime, and issue reads the clock once"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py#TestTheUniversalTTL (10 cases)"
        status: pass
      - kind: other
        ref: "grep -c 'now: datetime' src/nativespeaker/api/crud/challenges.py == 0; grep -c 'datetime.now(UTC)' == 1"
        status: pass
    human_judgment: false
  - id: D2
    description: "The claim's expiry predicate and its claimed_at write both come from func.clock_timestamp() in one statement"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_challenge_store.py#TestTheExpiryBoundaryIsPinnedInTheCompiledSQL::test_the_expiry_comparison_is_strict_in_the_compiled_sql"
        status: pass
      - kind: other
        ref: "grep -c 'clock_timestamp' src/nativespeaker/api/crud/challenges.py == 3; grep -c 'func.now()' == 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "The > versus >= boundary is asserted over the compiled SQL, with a control against an empty compile"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_challenge_store.py:186-192 (the table-name control, the strict comparison, the refusal of >=)"
        status: pass
      - kind: other
        ref: "grep -c 'literal_binds' tests/e2e/test_challenge_store.py == 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "An expired challenge is still refused, and a claim and a consume are each still single-use"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_challenge_store.py#TestTheClaimIsTheOnlyPlaceExpiryIsEvaluated, #TestTheLifecycleRunsOneDirectionOnly (32 passed)"
        status: pass
      - kind: integration
        ref: ".venv/bin/pytest tests/schema -m schema (291 passed, the measured baseline)"
        status: pass
    human_judgment: false
  - id: D5
    description: "routers/auth.py declares no datetime dependency and imports no datetime"
    verification:
      - kind: other
        ref: "grep -c 'get_evaluated_at' src/nativespeaker/api/routers/auth.py == 0; grep -c 'datetime' == 0"
        status: pass
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py, tests/unit/test_create_user_body.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "AuthService takes and holds no datetime, and get_auth_service declares none"
    verification:
      - kind: other
        ref: "grep -c 'evaluated_at' src/nativespeaker/api/services/auth.py == 0; grep -c 'get_evaluated_at' src/nativespeaker/api/app/dependencies.py == 2"
        status: pass
      - kind: integration
        ref: ".venv/bin/pytest tests/schema/test_create_atomicity.py tests/schema/test_create_race.py tests/schema/test_claim_race.py -m schema (55 passed)"
        status: pass
    human_judgment: false
  - id: D7
    description: "The binding checks still raise the same two rejections on the same branches"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py#TestTheCompletionComparison (9 cases)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_challenge_store.py#TestTheBindingAgainstRealRows (5 cases)"
        status: pass
    human_judgment: false

duration: 26 min
completed: 2026-09-12
status: complete
---

# Phase 47 Plan 06: The challenge store reads its own time Summary

**`ChallengesDB.issue`, `.claim` and `.consume` take no datetime, the claim's expiry predicate and its
`claimed_at` write are one `func.clock_timestamp()` evaluation in one statement, and `AuthService`
holds no instant at all.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-09-12T07:15:00Z
- **Completed:** 2026-09-12T07:41:00Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- The three challenge methods lost their `now: datetime` parameter. `issue` reads
  `datetime.now(UTC)` once and derives both `created_at` and `expires_at` from that one read.
  It stays a Python read because `expires_at` goes into the response body and a database
  expression could not be read back without a round trip.
- `claim` moved to the database clock. Its predicate is
  `col(AuthChallenge.expires_at) > func.clock_timestamp()` and its write is
  `.values(claimed_at=func.clock_timestamp())`, in the one `update(...)` statement, so the
  value that decides and the value that is recorded cannot disagree. `consume` stamps
  `consumed_at` from the same clock. `grep -c 'clock_timestamp'` prints `3` and
  `grep -c 'func.now()'` prints `0`.
- The `claimed_at IS NULL`, `claimed_at IS NOT NULL` and `consumed_at IS NULL` arms, the
  `.returning(...)` and the `len(result.all()) == 1` answer are byte-identical. They are what
  make claim and consume single-use, and no operator moved.
- `routers/auth.py` declares no datetime dependency, imports no datetime and names
  `get_evaluated_at` nowhere. `challenge_store: ChallengesDB = Depends(get_challenge_store)`
  and every `AuthIdentity` annotation are untouched, so Phase 48 and Phase 49 see the shapes
  they planned against.
- `AuthService` takes and holds no datetime. Its constructor parameter, its field, the
  one-instant comment and the module's `datetime` import are gone, and `get_auth_service`
  declares nothing. `app/dependencies.py` is down to two `get_evaluated_at` occurrences: the
  definition and `get_sync_service`, both plan 47-07's.
- The `>` boundary did not get dropped. It is asserted over the compiled SQL, with a control
  that the rendered text names the `auth_challenges` table so an empty compile cannot pass the
  negative check.
- Suites: **1935 unit / 360 e2e / 291 schema**, `ruff check src tests` clean, `ty check` **313**
  diagnostics against a **314** baseline measured from a clean checkout of `de9a491`.

## Task Commits

1. **Task 1 RED: drive the three challenge methods with no datetime** - `7510431` (test)
2. **Task 1 GREEN: the challenge store reads its own time** - `cabc7e3` (feat)
3. **Task 2: the e2e suite arranges rows, not clocks** - `a89352f` (test)
4. **Task 3: AuthService holds no instant and its factory declares none** - `411fe58` (feat)

## Files Created/Modified

- `src/nativespeaker/api/crud/challenges.py` - three signatures, one Python read, two database reads,
  and the new module-level `_claim_statement`
- `src/nativespeaker/api/routers/auth.py` - `issue_challenge` declares no instant; two imports deleted
- `src/nativespeaker/api/services/auth.py` - the constructor field, its comment, both call sites and
  the `datetime` import
- `src/nativespeaker/api/app/dependencies.py` - `get_auth_service` declares no instant
- `tests/unit/conftest.py` - `FakeChallengeStore.claim` and `.consume` read their own instant
- `tests/unit/test_challenge_ids.py` - the helper, three TTL cases rewritten, `FIXED_NOW` renamed
- `tests/unit/test_create_user_body.py`, `tests/unit/test_challenge_endpoint.py` - the two `issue` fakes
- `tests/unit/test_create_user_rollback.py`, `tests/unit/test_conflict_classification.py` - the service
  construction
- `tests/unit/test_sync_clock_capture.py` - one parametrized row lost `get_auth_service`
- `tests/e2e/test_challenge_store.py` - the helper, every call site, the three expiry cases, the
  repeat-claim case and the replaced boundary case
- `tests/schema/test_create_atomicity.py`, `tests/schema/test_create_race.py`,
  `tests/schema/test_claim_race.py` - the service construction and the seeded `expires_at`

## Decisions Made

**The claim UPDATE is now the module-level `_claim_statement`.** The plan's Task 2 asks a case to
compile "`ChallengesDB.claim`'s `update` statement" to literal SQL. The statement was built inline
inside the method, so it was not a value a test could reach. A test that rebuilt it would be a mirror:
it would keep passing while the production predicate drifted to `>=`, which is the exact failure the
case exists to catch. `crud/grants.py` already carries this pattern as `_effective_grants_statement`,
and `tests/schema/test_grant_locks.py` already compiles it. `claim` now issues
`_claim_statement(challenge_id)` and the e2e case compiles that same function's result. The plan's
phase boundary was respected: `__init__`, `__repr__`, the `challenge_store` constructor argument,
`get_challenge_store` and every `AuthIdentity` annotation are untouched.

**`issue` reads a Python clock and the other two read the database clock.** This is the plan's
split and it holds for the reason the plan gives: `expires_at` is returned to the caller and goes
into the `PrepareResponse` body, so a database expression would need a round trip to be read back.
`consume` has no comparison against the current time, so a Python read would also have satisfied
criterion 3; the database expression was chosen so `claimed_at` and `consumed_at` on one row can
never come from two different clocks.

**The compiled-SQL case has its own class.** Placed inside `TestTheClaimIsTheOnlyPlaceExpiryIsEvaluated`
it raised a `PytestWarning`: that class carries `@pytest.mark.asyncio(loop_scope="module")` and the
case is a synchronous function. It is now `TestTheExpiryBoundaryIsPinnedInTheCompiledSQL`, still in the
same file and still under the module's `e2e` marker, and the file still collects 32 cases — one
deleted, one added, in the same commit.

**The repeat-claim case reads the first write back instead of bracketing a clock.** The old case
asserted `row.claimed_at == now`. The replacement claims once, commits, reads the stored `claimed_at`,
claims again, commits and asserts the value is unchanged. `clock_timestamp()` advances between
statements, so a second claim that matched would move the value. This needs no wall-clock bracket and
no `timing` marker, and it is not sensitive to any skew between the test process and the database.

**`FIXED_NOW` in `tests/unit/test_challenge_ids.py` is now `SEEDED_AT`.** The constant was the instant
handed to the store; it is now only the date the in-memory `AuthChallenge` rows carry. Its comment
said "a store reading its own wall clock fails by years", which the store now does, so the comment was
false and was deleted rather than reworded. This is the rename plan 47-03 made twice.

**The unit count is 1935, one below the 1936 baseline, and no case was deleted for convenience.**
`tests/unit/test_sync_clock_capture.py::test_every_service_dependency_takes_the_one_captured_instant`
is parametrized over the factories that declare the dependency. `get_auth_service` no longer does, so
the row shrank from two to one. Plan 47-01 did exactly this for `get_chat_service`, and plan 47-07
deletes the file. `TestTheUniversalTTL` gained nothing and lost nothing: three cases changed subject.

**The type-checker baseline improved by one.** `ty check` reads 313 against 314. The diagnostic sets
were diffed, not counted: two new `unresolved-attribute` diagnostics appeared from reading
`.expires_at` and `.claimed_at` off an `AuthChallenge | None`, both were closed with an
`is not None` assertion, and closing the second also removed a diagnostic the old case carried.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 also changed two unit files the plan does not name**
- **Found during:** Task 1
- **Issue:** `tests/unit/test_create_user_body.py:32` and `tests/unit/test_challenge_endpoint.py:41`
  each hold a `_RecordingChallengeStore.issue` fake declaring `now` as a required keyword. Once the
  router stopped passing it, both routes raised `TypeError`. Task 1's own `<verify>` is the whole
  unit suite.
- **Fix:** Both fakes dropped the parameter, in Task 1's RED commit with the other fakes.
- **Files modified:** `tests/unit/test_create_user_body.py`, `tests/unit/test_challenge_endpoint.py`
- **Verification:** 1936 unit passed at Task 1's GREEN, which is the measured baseline exactly
- **Committed in:** `7510431` and `cabc7e3`

**2. [Rule 3 - Blocking] `_claim_statement` was extracted so the compiled-SQL case is not a mirror**
- **Found during:** Task 2
- **Issue:** Described in full under Decisions. The plan's Task 2 requires compiling the claim's own
  `update` statement, and an inline statement is not reachable from a test.
- **Fix:** A module-level `_claim_statement(challenge_id)` built the way `crud/grants.py` builds
  `_effective_grants_statement`. `claim` issues it; the case compiles it.
- **Files modified:** `src/nativespeaker/api/crud/challenges.py`, `tests/e2e/test_challenge_store.py`
- **Verification:** the case passes, and the three grep gates over `challenges.py` still print
  `3`, `0` and `1`
- **Committed in:** `cabc7e3` and `a89352f`

**3. [Rule 1 - Bug] Three schema helpers seeded challenges the database clock reads as expired**
- **Found during:** Task 3
- **Issue:** `tests/schema/test_create_atomicity.py`, `tests/schema/test_create_race.py` and
  `tests/schema/test_claim_race.py` each seed a challenge with
  `expires_at = NOW + timedelta(seconds=300)`, where `NOW` is `2026-08-23`. With the predicate on
  `clock_timestamp()` every such row is expired, and the schema suite fell from 291 to 247 passed.
  `tests/schema/test_registration_pairing.py` failed for the same seed although it does not hold one.
- **Fix:** Each helper seeds `expires_at` from `datetime.now(UTC)` at call time. `created_at` stays
  `NOW`, because several cases in those files scan `core.users` by that stamp.
- **Files modified:** the three schema files named above
- **Verification:** 291 schema passed, which is the measured baseline exactly
- **Committed in:** `411fe58`

**4. [Rule 3 - Blocking] `tests/unit/test_sync_clock_capture.py` asserts a dependency this plan removes**
- **Found during:** Task 3
- **Issue:** `test_every_service_dependency_takes_the_one_captured_instant` is parametrized over
  `get_sync_service` and `get_auth_service` and asserts each declares `Depends(get_evaluated_at)`.
  The file is not in the plan's list.
- **Fix:** The row is now `("get_sync_service",)`. `test_no_service_dependency_reads_the_clock_itself`
  still covers `get_auth_service` and still passes. Plan 47-07 deletes the file.
- **Files modified:** `tests/unit/test_sync_clock_capture.py`
- **Verification:** 1935 unit passed
- **Committed in:** `411fe58`

**5. [Rule 1 - Bug] Two new optional-row reads raised two `ty` diagnostics**
- **Found during:** the plan-level verification
- **Issue:** `(await read(...)).expires_at` in the expired-row case and
  `(await read(...)).claimed_at` in the repeat-claim case read an attribute off `AuthChallenge | None`.
  The diagnostic set was diffed against a clean checkout of `de9a491` in `/tmp`, not counted.
- **Fix:** Each binds the row and asserts `is not None` first. Closing the second also removed the
  diagnostic the old form of that case carried, so the baseline is 313 against 314.
- **Files modified:** `tests/e2e/test_challenge_store.py`
- **Verification:** `diff` of the two sorted diagnostic sets shows one removal and no addition
- **Committed in:** `411fe58`

---

**Total deviations:** 5 auto-fixed (3 blocking, 2 bugs).
**Impact on plan:** No scope creep. Three deviations are call sites or cases that name a shape this
plan changes, pulled into the commit that changes it. One extracts a production statement so a test
asserts the real thing rather than a copy. One keeps the type checker's baseline flat. The plan's
content stands.

## Issues Encountered

**The challenge-store e2e file was red for one commit, by the plan's own task split.** Task 1 removed
the parameter and Task 2 rewrote the file that passes it. The plan gives Task 1 a `<verify>` over the
unit suite and one e2e file only, so this is the split as written rather than an oversight. Every
other commit in this plan leaves all three suites at their baseline.

**One acceptance criterion is unreachable and was recorded rather than forced.** Task 3's
"`uv run pytest -q -m e2e` exits 0" cannot hold while
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`
fails. It expects the log event `proof_rejected` while the code emits `purchase_proof_rejected`. Plans
47-01, 47-03, 47-04 and 47-05 each measured it at HEAD before this phase started and recorded it in
`deferred-items.md` and in `.planning/WINDOWS.md`. The e2e suite is 360 passed / 1 failed and the 1 is
not this plan's. Task 3's other clause — "fewer than 340 passed" would mean the suite shrank — holds
at 360.

**The e2e suite is no longer able to observe an exact expiry, and that is permanent.** A live database
clock never lands on a stored value. The property is now read off the compiled SQL. What is lost is
the round trip through PostgreSQL, not the guarantee: the case asserts the rendered statement carries
`expires_at > clock_timestamp()` and carries no `expires_at >=`, with a control that the render is
not empty.

**Three schema modules now derive a challenge expiry from the wall clock at call time.** The window is
300 seconds and the whole schema suite runs in 34 seconds, so no ordinary run straddles it. A session
paused for five minutes between the seed and the claim would fail.

## Known Stubs

None. No hardcoded empty value, placeholder string or unwired component was written.

## Threat Flags

None. No new endpoint, auth path, file access pattern or schema change was introduced.

- **T-47-03 (replay of an expired challenge) held.** The predicate and the `claimed_at` write are in
  the same statement and both are `func.clock_timestamp()`. The source gate prints `3` uses of
  `clock_timestamp` and `0` of `now()`.
- **T-47-17 (the `>` versus `>=` comparison) held.** Asserted over the compiled SQL with a positive
  control, because the round-trip case became unreachable.
- **T-47-18 (single-use semantics) held.** All four pinned fragments are byte-identical, and the
  rewritten e2e cases still assert `True` then `False` on a repeated claim and on a repeated consume.
- **T-47-19** is unchanged: the module still holds no logger, no handle is logged, and the issued
  response still carries `Cache-Control: no-store`.
- **T-47-SC:** no package was installed and no manifest was touched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Roadmap criteria 1, 2 and 3 are met for the challenge store and the auth service. No challenge
  method, no auth service method and no auth service constructor carries a datetime.
- `app/dependencies.py` carries two `get_evaluated_at` occurrences: the definition and
  `get_sync_service`. Plan 47-07 owns both, plus `SyncService` and
  `tests/unit/test_sync_clock_capture.py`. Nothing blocks it.
- `crud/challenges.py` gained one module-level function, `_claim_statement`. Phase 49 changes only
  how `ChallengesDB` is built, and `__init__`, `__repr__` and the constructor argument are untouched.
- `tests/unit/test_auth_package_shape.py` is byte-identical, so Phase 49's ratchet rewrite is
  unaffected.
- One thing to carry forward: `tests/unit/test_sync_clock_capture.py` now asserts the
  one-captured-instant discipline over one factory. Plan 47-07 deletes the file; until then it is a
  weaker guard than it was.

---
*Phase: 47-stop-threading-an-evaluation-instant-through-the-layers*
*Completed: 2026-09-12*

## Self-Check: PASSED

Every file named in `key-files.modified` exists on disk and all four task commits of this plan are
reachable in `git log`.
