---
phase: 49-delete-the-single-implementation-auth-protocols
plan: 04
subsystem: auth
tags: [refactor, crud, constructor, dependency-injection, phase-gate, validation]

requires:
  - phase: 49-delete-the-single-implementation-auth-protocols
    provides: "Plan 49-03's three no-argument `ChallengesDB()` constructions, waiting for this constructor"
  - phase: 48-narrow-identity-to-the-verified-pair
    provides: "D-10, the comment rule every edit here follows"
provides:
  - "`ChallengesDB(session)` holds the session, as `IdentitiesDB(db)` and `GrantsDB(db)` do"
  - "`issue`, `locate`, `claim` and `consume` take no session parameter and read `self.session`"
  - "`verify_binding` and `_claim_statement` byte-unchanged, proven by diff"
  - "The re-measured Phase 49 gate in 49-VALIDATION.md, every row green"
  - "The measured fact that a `grep -rn` name check answers for substrings and for gitignored build output"
affects: [50-typed-runtime-container]

actuals:
  tokens: 31207
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A crud class takes its session in the constructor; one crud object per session, never shared across two"
    - "A test that opens its own session builds its own crud object inside the `async with` block"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/crud/challenges.py
    - src/nativespeaker/api/services/auth.py
    - src/nativespeaker/api/routers/auth.py
    - tests/unit/conftest.py
    - tests/unit/test_challenge_endpoint.py
    - tests/unit/test_create_user_body.py
    - tests/unit/test_challenge_ids.py
    - tests/e2e/test_challenge_store.py
    - .planning/phases/49-delete-the-single-implementation-auth-protocols/49-VALIDATION.md

key-decisions:
  - "The `store()` helper in tests/unit/test_challenge_ids.py takes an unannotated `session` parameter, so no `# ty: ignore` was needed. The type gate reads 306, unmoved. The precedent 49-03 established was measured for, not applied on faith."
  - "Nine unit cases and five e2e cases that reach only `verify_binding` still construct the crud object with a session, because the constructor requires one. In e2e that means an `async with` block the case did not need before."
  - "The two plain greps in the phase gate both matched something that is not the thing they check: a substring (`FakeDeviceCheckAdapter`) and a gitignored build index (`egg-info/SOURCES.txt`). Both rows are green on the word-scoped, tracked-file form."
  - "A docstring in tests/e2e/test_challenge_store.py claimed the store 'reads its session per call rather than caching one'. This plan makes that false, so the sentence was rewritten to what the class actually proves."

patterns-established:
  - "A crud constructor lands with its call sites in one commit; the count of call sites is measured before the edit and re-measured after"

requirements-completed: []

coverage:
  - id: D1
    description: "`ChallengesDB` takes the session in its constructor and no method takes one (D-01)"
    verification:
      - kind: other
        ref: "grep -c 'def __init__(self, session: AsyncSession)' src/nativespeaker/api/crud/challenges.py prints 1; grep -c 'self.session' prints 6"
        status: pass
      - kind: other
        ref: "test -z \"$(grep -n 'async def issue(self, session\\|async def locate(self, session\\|async def claim(self, session\\|async def consume(self, session' src/nativespeaker/api/crud/challenges.py)\" → exit 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "`verify_binding` keeps its three parameters and its body byte-for-byte, and `_claim_statement` is untouched (D-01, T-49-13, T-49-15)"
    verification:
      - kind: other
        ref: "git diff HEAD~1 -- src/nativespeaker/api/crud/challenges.py shows no changed line inside either function; the only `_claim_statement` line in the diff is its call site in `claim`"
        status: pass
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py (40 passed), the four precedence suites (136 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "`AuthService` builds `ChallengesDB(db)` and the challenge handler builds `ChallengesDB(session)`"
    verification:
      - kind: other
        ref: "grep -c 'ChallengesDB(db)' src/nativespeaker/api/services/auth.py prints 1; grep -c 'ChallengesDB(session)' src/nativespeaker/api/routers/auth.py prints 1"
        status: pass
      - kind: unit
        ref: "tests/unit/test_challenge_endpoint.py, tests/unit/test_create_user_body.py (73 passed)"
        status: pass
    human_judgment: false
  - id: D4
    description: "No crud object spans two sessions; the e2e module fixture is gone (T-49-16)"
    verification:
      - kind: other
        ref: "grep -c 'def store' tests/e2e/test_challenge_store.py prints 0"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py (32 passed, the Phase 48 case count)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The claim UPDATE, the consume UPDATE and the expiry predicate are unchanged against live PostgreSQL (T-49-13, T-49-14)"
    verification:
      - kind: e2e
        ref: ".venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py (32 passed, including the 8-contender claim race and the compiled-SQL expiry case)"
        status: pass
      - kind: integration
        ref: ".venv/bin/pytest -q -m schema tests/schema/test_claim_race.py test_create_atomicity.py test_create_race.py (55 passed)"
        status: pass
    human_judgment: false
  - id: D6
    description: "The crud module still holds no logger and no handle reaches a log call (T-49-17)"
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py::TestTheStoreHoldsNoLogger (passed within the 40)"
        status: pass
    human_judgment: false
  - id: D7
    description: "The three suites, ruff and ty are re-measured at the phase gate rather than copied"
    verification:
      - kind: e2e
        ref: ".venv/bin/pytest -q -m '' (1 failed, 2563 passed); -m e2e (1 failed, 360 passed); -m schema (297 passed); ruff `All checks passed!`; ty `Found 306 diagnostics`"
        status: pass
    human_judgment: false
  - id: D8
    description: "49-VALIDATION.md carries a fully green verification map naming the one pre-existing failure"
    verification:
      - kind: other
        ref: "grep -c '⬜ pending' on the record returns 1, the symbol legend only, no row; frontmatter reads nyquist_compliant: true"
        status: pass
    human_judgment: false

duration: 19 min
completed: 2026-09-17
status: complete
---

# Phase 49 Plan 04: Delete the single-implementation auth Protocols Summary

**`ChallengesDB` now takes its session in the constructor like its two sibling crud classes, its four methods read `self.session`, the binding check and both UPDATE statements are byte-unchanged, and the Phase 49 gate was re-measured end to end rather than copied — which is how two false-positive greps in the record were caught.**

## Performance

- **Duration:** 19 min
- **Started:** 2026-09-17T23:38:00Z
- **Completed:** 2026-09-17T23:57:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- `ChallengesDB.__init__(self, session: AsyncSession)` is a required positional parameter with no default and no `| None`, in the exact shape `crud/identities.py:25-28` uses. The three crud classes `AuthService` builds now have one shape.
- `issue`, `locate`, `claim` and `consume` dropped their `session` parameter; every `session.add`, `session.flush` and `session.exec` in their bodies reads `self.session`. The keyword-only markers and the keyword parameter names are unchanged.
- `verify_binding` and `_claim_statement` are byte-for-byte what they were. `git diff HEAD~1` shows no changed line inside either; the one `_claim_statement` line in the diff is its call site inside `claim`.
- `AuthService` builds `ChallengesDB(db)` beside `IdentitiesDB(db)` and `GrantsDB(db)`, and the four read sites dropped `self.session`. `issue_challenge` builds `ChallengesDB(session)` from its own request session, as it builds `IdentitiesDB(session)` five lines above.
- The e2e module-scoped fixture is gone. Each `async with factory() as session:` block builds its own crud object, including every session of the second engine factory the 8-contender claim race opens. No object spans two sessions.
- **The phase gate was re-measured, and two of its greps were answering the wrong question.** One matched a test double by substring, one matched a gitignored packaging index. Both are recorded in 49-VALIDATION.md with the word-scoped form that answers correctly.

## Task Commits

1. **Task 1: The challenge crud class takes the session in its constructor** — `46a92ad` (refactor, 8 files, +162/−158)
2. **Task 2: Measure the phase gate and record it** — `e999992` (docs, 1 file, +88/−22)

## Files Created/Modified

- `src/nativespeaker/api/crud/challenges.py` — the constructor added under the class docstring; the docstring clause "and the session is a parameter on every one of them" removed and the rest of the sentence kept. `__repr__` and its TTL stay: the sibling crud classes declare no `__repr__`, so there was nothing to copy, and the TTL is the one fact the repr carries.
- `src/nativespeaker/api/services/auth.py` — `self.challenges_db = ChallengesDB(db)`; the `locate`, `claim` and `consume` calls dropped `self.session`. The `verify_binding` call keeps its three arguments exactly.
- `src/nativespeaker/api/routers/auth.py` — the issue call reads `await ChallengesDB(session).issue(...)`, wrapped so its three keyword arguments stay within the 120-character limit. The `session.commit()` and `Cache-Control` lines are untouched.
- `tests/unit/conftest.py` — `FakeChallengeStore.locate`, `.claim` and `.consume` and the three replacement functions in the `store` fixture all dropped the `session` parameter. Each replacement still takes `self` first, because it is set on the class.
- `tests/unit/test_challenge_endpoint.py`, `tests/unit/test_create_user_body.py` — each recorder's methods and each fixture's replacement functions dropped the parameter.
- `tests/unit/test_challenge_ids.py` — `store()` became `store(session)` and returns `ChallengesDB(session)`. All 15 call sites carry a session: three pass the `_RecordingSession` the case already builds, nine construct one for `verify_binding`, and three pass the stub the `locate` case seeds.
- `tests/e2e/test_challenge_store.py` — the module fixture deleted; `issue` dropped its crud-object parameter; `_contended_challenge` dropped it too. Blocks that make two or more calls bind `crud = ChallengesDB(session)`; single-call blocks construct inline. Five `verify_binding` cases gained an `async with` block, because the constructor needs a session the case did not open before.
- `.planning/phases/.../49-VALIDATION.md` — all 13 map rows green with the figure each command printed, the measured phase gate, the five phase-wide greps, the two grep notes, and the sign-off.

## Decisions Made

- **The type gate was measured before assuming 49-03's marking precedent applied.** 49-03 warned that `ty` checks `tests/` and that each new concrete annotation costs one diagnostic per test double it meets. The `store(session)` helper here leaves its parameter unannotated, so `ChallengesDB(session)` inside it is checked against an unknown, not against `AsyncSession`. `ty check` reads **306**, unmoved. No `# ty: ignore` was added anywhere; an unnecessary one would itself be a diagnostic.
- **The nine `verify_binding` unit cases construct with `_RecordingSession()`.** `verify_binding` reads no session, but the constructor requires one, and the acceptance criterion asks each of the 15 call sites to carry a session argument. The alternative — a default of `None` on the constructor — is closed by D-01: a default would make this class a different shape from its two siblings, which is the whole reason for the change.
- **e2e blocks with more than one call bind a local `crud`.** Writing `ChallengesDB(session)` twice inside one `async with` would build two objects around one session, which reads as if two were needed. One object per session, named `crud`, is the codebase term.
- **The record keeps the stale `-m ''` baseline visible rather than overwriting it.** 49-VALIDATION.md still shows the Phase-48 figure of 2572 with a correction note under it, because four plans in a row measured 2563 and the drift is the fact worth keeping.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A docstring asserted a property this plan deletes**

- **Found during:** Task 1
- **Issue:** `tests/e2e/test_challenge_store.py`, class `TestTheRollbackIsolatesEveryRow`, read "The operational proof that the store reads its session per call rather than caching one." After this plan the crud object holds exactly one session for its whole life, so the sentence states the opposite of the shipped design and would mislead the next reader of the rollback cases.
- **Fix:** Rewritten to "The operational proof that no row this module wrote outlives the test that wrote it", which is what the two cases in the class assert. One line, within the 120-character limit, so the docstring-bar ratchet 49-03 tripped stayed green.
- **Files modified:** `tests/e2e/test_challenge_store.py`
- **Verification:** `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` → 32 passed; `.venv/bin/ruff check src tests` → `All checks passed!`; the whole `-m ''` run carries no docstring-bar failure.
- **Committed in:** `46a92ad` (part of the task commit)

**2. [Rule 3 - Blocking] Two of the plan's own phase-gate greps could not pass as written**

- **Found during:** Task 2
- **Issue:** The plan's `test -z "$(grep -rn 'PlaySubscriptionSource\|FirebaseAdminAdapter\|DeviceCheckAdapter\|TokenVerifier\|challenge_store' src tests)"` exits non-zero, and so does the adapters-module grep. Neither is a real regression. `DeviceCheckAdapter` matches three lines of `FakeDeviceCheckAdapter` in `tests/e2e/conftest.py:301, 335, 504` — a different identifier that carries the deleted one as a substring. `nativespeaker.api.auth.adapters` matches one line of `src/ns_api_gateway.egg-info/SOURCES.txt`, a stale packaging index that `.gitignore:7` excludes and that names a module no longer on disk.
- **Fix:** Diagnosed each match to its line, then re-ran the check in the form that answers the question the row asks: `git grep -nwE 'PlaySubscriptionSource|FirebaseAdminAdapter|DeviceCheckAdapter|TokenVerifier|challenge_store' -- src tests` → 0 lines, and `git grep -n 'nativespeaker\.api\.auth\.adapters' -- src tests` → 0 lines. Both forms and both explanations are written into 49-VALIDATION.md as notes A and B, so the next reader does not re-diagnose them. Neither the fake nor the egg-info directory was touched: the fake belongs to no plan in this phase, and the egg-info is build output.
- **Files modified:** `.planning/phases/49-delete-the-single-implementation-auth-protocols/49-VALIDATION.md`
- **Verification:** `test ! -e src/nativespeaker/api/auth/adapters.py` → the module is absent; `git check-ignore -v src/ns_api_gateway.egg-info/SOURCES.txt` → `.gitignore:7 *.egg-info/`; `git ls-files src/ns_api_gateway.egg-info` → nothing tracked.
- **Committed in:** `e999992`

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 3 blocking).
**Impact on plan:** No scope creep and no changed behavior. Deviation 1 was caused by this plan's own edit. Deviation 2 is the third time in this phase that a `grep -rn` name check answered for something other than the name — 49-01 hit a missing test path, 49-02 hit the egg-info directory, and this plan hit both a substring and the egg-info again. The phase-wide lesson is recorded in the validation record, not only here.

## Issues Encountered

- **The plan's own `<verify>` block carries the two greps above.** Both are recorded as green on the word-scoped form and red on the literal form, with the diagnosis. Neither hides a regression.
- **The plan's stated baseline was stale again.** It records `1 failed, 2572 passed` for `-m ''`; the measured figure at this commit is `1 failed, 2563 passed`, which is where 49-02 and 49-03 both left it. This plan adds and removes no case, so the count is unchanged by it.
- **The plan says `issue`, `read`, `row_count` and `expire` each carry a crud-object parameter.** Only `issue` did; `read`, `row_count` and `expire` never took one. The three are unchanged.
- **Every test path this plan names exists.** No run reported "file or directory not found" and none collected zero items. `-m e2e` selected 361 cases and `-m schema` selected 297; neither marked run was an all-deselected run.

## Verification Results

Run from the repository root at commit `46a92ad`, re-measured in Task 2:

| Check | Result |
|---|---|
| `.venv/bin/pytest -q -m ''` | `1 failed, 2563 passed` — the failure is the pre-existing restore four-arms case and no other |
| `.venv/bin/pytest -q -m e2e` | `1 failed, 360 passed, 2203 deselected` — the same case |
| `.venv/bin/pytest -q -m schema` | `297 passed, 2267 deselected` — exit 0 |
| `.venv/bin/ruff check src tests` | `All checks passed!` |
| `.venv/bin/ty check` | `Found 306 diagnostics` — the Phase 48 baseline, unmoved by this plan |
| `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` | `32 passed` — the Phase 48 case count |
| `git grep -nwE '<the four Protocols>\|challenge_store' -- src tests` | 0 lines |
| `test ! -e src/nativespeaker/api/auth/adapters.py` | exit 0 |

The one failing case is
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`.
It is not this phase's, Phases 47 and 48 both recorded it, and this plan did not fix it.

### Task acceptance criteria, re-run

| Criterion | Measured |
|---|---|
| `grep -c 'def __init__(self, session: AsyncSession)' challenges.py` is `1` | 1 ✓ |
| `grep -c 'self.session' challenges.py` is at least `5` | 6 ✓ |
| `verify_binding` signature present once; no changed line inside it or `_claim_statement` | 1, and the diff touches neither ✓ |
| `grep -c 'ttl_seconds' challenges.py` is `1` | 1 ✓ |
| `grep -c 'store(' tests/unit/test_challenge_ids.py` is `16` | 16 — one definition, 15 calls, each with a session ✓ |
| `grep -c 'ChallengesDB(db)' services/auth.py` is `1` | 1 ✓ |
| `grep -c 'ChallengesDB(session)' routers/auth.py` is `1` | 1 ✓ |
| `grep -c 'def store' tests/e2e/test_challenge_store.py` is `0` | 0 ✓ |
| `-m e2e tests/e2e/test_challenge_store.py` reports 32 cases | 32 ✓ |
| `git log -1 --stat` covers all eight files | `46a92ad`, 8 files ✓ |
| `49-VALIDATION.md` carries no `⬜ pending` row | 0 rows; the one remaining mention is the symbol legend ✓ |
| `nyquist_compliant: true` in the record's front matter | true ✓ |
| The record names the restore four-arms case and says it is not this phase's | named at full node id ✓ |
| The record's validation commit stands alone | `e999992`, 1 file ✓ |

## Known Stubs

None. No placeholder, no hardcoded empty value and no unwired component was written.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or schema change.

- **T-49-13 (Elevation of Privilege, `_claim_statement`):** mitigated. Not one line inside it changed, proven by `git diff HEAD~1`. The 8-contender e2e claim race and the three schema race suites ran live: 32 and 55 cases green.
- **T-49-14 (Tampering, `consume`):** mitigated. The UPDATE that clears the pre-auth subject is unedited; only the `await` receiver in front of it moved to `self.session`. The claimed-to-consumed move is exercised against live PostgreSQL by six cases.
- **T-49-15 (Elevation of Privilege, `verify_binding`):** mitigated. Byte-unchanged, asserted by diff, and exercised by the four precedence suites (136 cases) and by nine cases in `tests/unit/test_challenge_ids.py`.
- **T-49-16 (Tampering, one crud object shared by two sessions):** mitigated. The module fixture that held one object for the whole file is deleted; every session, including each of the 8 contenders' own sessions from the second engine factory, builds its own.
- **T-49-17 (Information Disclosure, the handle):** mitigated. The crud module still imports neither `structlog` nor `logging`, asserted by `TestTheStoreHoldsNoLogger`, and no handle was added to any log call.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 49 is executed. Every ROADMAP criterion has a measured row in 49-VALIDATION.md, so `/gsd:verify-work 49` has a record to read rather than a claim to re-derive.
- `CURRENT` in `tests/unit/test_auth_package_shape.py` still reads `(7, 20, 60)`. This plan changed no module, class or function count under `auth/`, so D-08 did not apply to either commit.
- Two facts for Phase 50, which rewrites `lifespan.py` and `dependencies.py`: the three crud classes `AuthService` builds now share one constructor shape, and the lifespan holds no crud object at all.
- The restore four-arms failure is still open and still not this phase's. It has survived Phases 47, 48 and 49 as a named, explained red.

## Self-Check: PASSED

- All nine modified files exist on disk.
- Both commits exist: `46a92ad`, `e999992`. Neither deleted a tracked file (`git diff --diff-filter=D HEAD~1 HEAD` is empty for each).
- Every task acceptance criterion re-run and passing, with the two corrections recorded as deviations.

---
*Phase: 49-delete-the-single-implementation-auth-protocols*
*Completed: 2026-09-17*
