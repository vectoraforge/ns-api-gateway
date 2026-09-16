---
phase: 48-narrow-identity-to-the-verified-pair
plan: 08
subsystem: testing
tags: [pytest, ruff, ty, refactor, ledger]

# Dependency graph
requires:
  - phase: 48-01
    provides: the two types, the two dependencies and every src caller, and option B inside AuthService.complete
  - phase: 48-07
    provides: a tree that collects end to end again, which is criterion 5's precondition
provides:
  - the three suites, ruff and ty measured at this phase's HEAD rather than copied
  - the four criterion greps, two of them in the corrected form three earlier plans asked for
  - WINDOWS.md entry 33, which records the create-user ordering with the answer it was given
  - a WINDOWS.md ledger that accepts writes again, after two pre-existing defects were repaired
affects: [49-delete-the-single-implementation-auth-protocols, 50-typed-runtime-container-behind-an-exit-stack-lifespan]

actuals:
  tokens: 2090
  tasks: 3
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A gate that cannot pass as written is measured in the form its own locked decision mandates, and the plan's wording is recorded as a deviation"

key-files:
  created: []
  modified:
    - .planning/WINDOWS.md
    - .planning/phases/48-narrow-identity-to-the-verified-pair/deferred-items.md

key-decisions:
  - "The two unsatisfiable criterion greps were measured in the corrected form 48-01 and 48-02 each carried forward, and both corrections are recorded as deviations rather than as passes"
  - "The ledger counters were set to what the entries yield, 19/2/12/33, rather than to the 20 and 11 the plan copied from the stale frontmatter; the plan's own acceptance criteria check only waived_count and total_count, which 19/2/12/33 satisfies"
  - "A second pre-existing ledger defect, the unrendered reason cell on row 31, was repaired in the same file rather than deferred, because leaving it would have kept every append refused and made the resolved deferred item only half-true"

patterns-established:
  - "A blocked tool is proved unblocked by running it, not by reasoning about the fix: the probe append was run and reverted in the same command"

requirements-completed: []

coverage:
  - id: D1
    description: "Criterion 1: AuthIdentity is named nowhere in src or tests, and LinkedIdentity has two required fields over no base class"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn '\\bAuthIdentity\\b' src tests)\""
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py#TestTheLinkedIdentityShape::test_it_carries_both_rows_frozen_slotted_and_over_no_base_class"
        status: pass
    human_judgment: false
  - id: D2
    description: "Criterion 4: no test passes the deleted flag and none names a deleted dependency"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn 'get_linked_identity\\|allow_preauth=\\|preauth_callable(' src tests)\""
        status: pass
    human_judgment: false
  - id: D3
    description: "Criterion 3: only crud/challenges.py and AuthService._complete take LinkedIdentity | None as a parameter"
    verification:
      - kind: other
        ref: "grep -rn 'LinkedIdentity | None' src | grep -v -- '-> LinkedIdentity | None' yields two files"
        status: pass
    human_judgment: false
  - id: D4
    description: "Criterion 5: the three suites are re-run at this phase's HEAD and the only failing case is the pre-existing restore case"
    verification:
      - kind: e2e
        ref: ".venv/bin/pytest -q -m '' (1 failed, 2572 passed)"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -m e2e (1 failed, 360 passed)"
        status: pass
      - kind: integration
        ref: ".venv/bin/pytest -q -m schema (297 passed)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The controls hold: ruff is clean and ty does not rise above 311 diagnostics"
    verification:
      - kind: other
        ref: ".venv/bin/ruff check src tests (All checks passed!)"
        status: pass
      - kind: other
        ref: ".venv/bin/ty check (Found 306 diagnostics)"
        status: pass
    human_judgment: false
  - id: D6
    description: "48-01 coverage D8, carried to the gate: every create-user wire outcome is unchanged under option B, at the e2e layer"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_create_user.py (22 passed)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_create_user.py#TestCompletionRejectsAnAlreadyLinkedCaller::test_an_active_linked_identity_is_rejected_at_completion"
        status: pass
    human_judgment: false
  - id: D7
    description: "D-07 is recorded with the answer it was given, as WINDOWS.md entry 33"
    verification:
      - kind: other
        ref: "grep -c '\"phase\": \"48\"' .planning/WINDOWS.md prints 1; the entry parses and its status is waived"
        status: pass
    human_judgment: false
  - id: D8
    description: "D-09: the ROADMAP entry already carries the amended goal and criteria; REQUIREMENTS.md maps nothing to this phase"
    verification:
      - kind: other
        ref: "git diff --name-only HEAD -- .planning/REQUIREMENTS.md is empty; no traceability row names phase 48"
        status: pass
    human_judgment: false

# Metrics
duration: 9 min
completed: 2026-09-16
status: complete
---

# Phase 48 Plan 08: The phase gate and the records Summary

**Criterion 5 is measured at this phase's HEAD and the failing set is exactly the one pre-existing
restore case: 2572 passed under the bare marker, 360 under `-m e2e`, 297 under `-m schema`, `ruff`
clean and `ty` down to 306 — and the broken-windows ledger, refused since 48-01, accepts writes
again.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-09-16T22:38:52Z
- **Completed:** 2026-09-16T22:48:35Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- **The four criterion greps are measured, and two of them only pass in the corrected form** three
  earlier plans predicted. Both corrections are recorded below as deviations with their full
  occurrence lists, never as passes.
- **The three suites were run here, not copied.** `-m ''` answers 1 failed and 2572 passed; the one
  failure is the named pre-existing restore case, and it is the same single failure `-m e2e`
  reports beside 360 passed. `-m schema` exits 0 at 297, the figure RESEARCH measured at `937864c`.
- **The seven-case collection difference against the baseline is accounted for case by case**, from
  the SUMMARY files and confirmed by a per-file measurement, rather than treated as a regression.
- **48-01's coverage entry D8 is discharged at the e2e layer.** `tests/e2e/test_create_user.py`
  answers 22 passed, including the case that asserts an already-linked caller is answered 409
  `identity_already_linked` under option B.
- **The ledger is repaired at its root, twice.** The counter drift 48-01 hit is corrected to what
  the entries yield, and a second defect sitting behind it — an unrendered reason cell on row 31 —
  was found only because the first fix let the tool reach its next gate. `windows append` now
  answers `ok: true`, measured by a probe that was reverted in the same command.

## Task Commits

1. **Task 1: The four criterion greps** — no commit of its own; the task writes nothing but this
   SUMMARY
2. **Task 2: The three suites, ruff and ty** — no commit of its own; the same
3. **Task 3: Record what shipped** — `de3777f` (docs), plus `dda9344` (docs) closing the deferred
   ledger item with that hash

**Plan metadata:** the `docs(48-08)` commit below.

Tasks 1 and 2 manufactured no empty commit. This follows 47-08, which recorded the same thing for
the same reason: a task whose only product is prose in the SUMMARY commits when the SUMMARY does.

## Files Created/Modified

- `.planning/WINDOWS.md` — entry 33 in both the markdown table and the fenced JSON array; the
  frontmatter counters set to what the entries yield; row 31's reason cell rendered from the JSON
- `.planning/phases/48-narrow-identity-to-the-verified-pair/deferred-items.md` — the item 48-01
  logged is marked `status: resolved` and names `de3777f`

## Task 1 — the four criterion greps, measured

Every command below was run in this session at `61d4a8f`.

| # | Command | Result | Verdict |
|---|---|---|---|
| 1 | `test -z "$(grep -rn '\bAuthIdentity\b' src tests)"` | no output, grep exit 1, test **exit 0** | PASS as written |
| 2 | `test -z "$(grep -rn 'get_linked_identity\|allow_preauth\|preauth_callable' src tests)"` | prints `tests/unit/test_app_wiring.py:65`, test **exit 1** | FAIL as written — deviation 2 |
| 2' | `test -z "$(grep -rn 'get_linked_identity\|allow_preauth=\|preauth_callable(' src tests)"` | no output, **exit 0** | PASS corrected |
| 3 | `test "$(grep -rln 'LinkedIdentity \| None' src \| sort \| tr '\n' ' ')" = "…challenges.py …auth.py "` | prints three files, test **exit 1** | FAIL as written — deviation 1 |
| 3' | `grep -rn 'LinkedIdentity \| None' src \| grep -v -- '-> LinkedIdentity \| None'` | two files, **exit 0** | PASS corrected |
| 4 | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` | `80 passed`, **exit 0** | PASS |

**Criterion 1, and pitfall 1's control.** `grep -rn '\bAuthIdentity\b' src tests` prints nothing.
The plain, unbounded `grep -rn 'AuthIdentity' src tests` still prints **16** lines, every one of
them `PreAuthIdentityNotAllowed` — the class that stays at `errors.py:362` and is raised from
exactly two places, `app/dependencies.py:84` and `routers/auth.py:66`. The word-boundary form is
what criterion 1 needs; the plain form can never print nothing.

**Criterion 3, the full occurrence list.** Four occurrences in `src/`:

```
src/nativespeaker/api/services/auth.py:129:                           linked: LinkedIdentity | None,
src/nativespeaker/api/crud/challenges.py:46:                    linked: LinkedIdentity | None) -> tuple[str, datetime]:
src/nativespeaker/api/crud/challenges.py:93:                       linked: LinkedIdentity | None) -> AuthChallenge:
src/nativespeaker/api/crud/identities.py:30:    async def resolve(self, *, issuer: str, subject: str) -> LinkedIdentity | None:
```

Three are parameters, in the two files criterion 3 names — `crud/challenges.py` twice, and
`services/auth.py:129`, which is `_complete`'s own parameter, exactly what the amended criterion 3
names. The fourth is `resolve`'s return type, which **D-03 mandates**.

**Criterion 4, the one surviving line.** `tests/unit/test_app_wiring.py:65` is
`def test_the_preauth_callable_route_still_verifies_the_token`, a **test method name** describing
the `PREAUTH_CALLABLE_PATHS` set that 48-01 Task 3 deliberately keeps. Read in context, the case
parametrizes over `sorted(PREAUTH_CALLABLE_PATHS)` and asserts `get_claims in calls` for
`/auth/create-user` and `/auth/challenge` — a live assertion about the phase's own design, not a
call site, not a flag and not a deleted identifier. The last real call site,
`tests/schema/test_claim_race.py:251`, went in 48-07.

**The two docstrings that need no edit, confirmed.** `src/nativespeaker/api/auth/google_play.py:240`
and `tests/unit/test_google_play_notifications.py:843` both say an uncapped refresh "holds one
thread of the pool `get_identity` shares". `get_identity` is the name D-05 gives the account
dependency, and it exists in `app/dependencies.py`. Both sentences are still true; neither file was
edited.

**D-09, confirmed and not edited.** The Phase 48 entry in `ROADMAP.md` already carries the goal that
names `VerifiedClaims`, `LinkedIdentity`, `get_claims` and `get_identity`, marked "Amended
2026-09-16 by the phase discussion", and criterion 3 carries planning's amendment naming
`AuthService._complete`. **`REQUIREMENTS.md` was read and not edited:** no traceability row and no
requirement names phase 48 (`grep -nE '\| *(Phase )?48 *\||Phase 48'` exits 1), and
`git diff --name-only HEAD -- .planning/REQUIREMENTS.md` is empty.

## Task 2 — the gate, measured at this phase's HEAD

Every command below was run in this session at `61d4a8f`, and every number is this run's own.

| Command | Result | Baseline at `937864c` |
|---|---|---|
| `.venv/bin/pytest -q -m ''` | **1 failed, 2572 passed**, 132.18 s, exit 1 | 1 failed, 2579 passed |
| `.venv/bin/pytest -q -m e2e` | **1 failed, 360 passed**, 2212 deselected, 45.89 s, exit 1 | 1 failed, 360 passed, 2219 deselected |
| `.venv/bin/pytest -q -m schema` | **297 passed**, 2276 deselected, 35.96 s, **exit 0** | 297 passed, 2283 deselected |
| `.venv/bin/ruff check src tests` | **`All checks passed!`**, exit 0 | All checks passed! |
| `.venv/bin/ty check` | **`Found 306 diagnostics`** | Found 311 diagnostics |

**The failing set is exactly one case, and it is the named one.** Both the bare marker and `-m e2e`
print a single line under `short test summary info`:

```
FAILED tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing
```

That is the pre-existing failure recorded in STATE.md, in `47-VERIFICATION.md` and as ledger entry
29. Criterion 5 is not charged for it, and the exit code is not the measure — the short test summary
is, as the plan requires. **No second failing case appeared**, so nothing in this phase is owed a
root-cause diagnosis.

**`ty` is a control and it fell.** 306 against a ceiling of 311. No new diagnostic to name.

**The collection count, and the seven-case difference.** `-m ''` collects 2573 (1 + 2572), against
2580 at `937864c`. The plan's threshold is 2570, so the run passes it. The difference is not a
regression and is accounted for case by case. Measured per file — `git show 937864c:<file>` against
the working tree — only four files moved:

| File | Collected delta | What moved |
|---|---|---|
| `tests/unit/test_identity_accessors.py` | **−6** | `TestTheIdentityShape`'s 6 cases replaced by `TestTheLinkedIdentityShape`'s 1 (−5, 48-01 / D-11); `test_the_only_string_fields_are_the_verified_pair` deleted (−1); `test_the_declaration_resolves_once` de-parametrized from two paths to one (−1, 48-01 deviation 2); `test_the_admitting_declaration_reads_no_table_at_all` added (+1) |
| `tests/unit/test_identities_crud.py` | **−4** | `TestOutcomeOneNoMatchingRow`'s four cases became the single `test_resolve_answers_none_when_no_row_exists` (−3, 48-02); `test_the_admitted_identity_carries_the_verified_pair` deleted (−1, 48-02 deviation 2) |
| `tests/unit/test_challenge_endpoint.py` | **+1** | the two binding cases added (+2, 48-03); the preauth arm left the six-arm body-refusal parametrization (−1, 48-03 deviation 1) |
| `tests/unit/test_create_user_precedence.py` | **+2** | `TestTheCompletionPathIssuesOneStatement`'s two cases (48-05) |

Net **−7**, which is 2580 − 2573 exactly. Every other changed file holds its pre-phase count, as
48-04, 48-06 and 48-07 each recorded. The four arms of the `-m ''` accounting were measured here,
not copied: a `def test_` count at both commits over all 23 changed test files gives −5, and the two
remaining cases are the two parametrized arms named above, each confirmed by reading the decorator
at both commits.

**48-01's coverage entry D8, discharged at the e2e layer.**
`.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py` answers **22 passed, exit 0**. Named
explicitly, because the plan and three sibling SUMMARYs carried it to this gate:
`TestCompletionRejectsAnAlreadyLinkedCaller::test_an_active_linked_identity_is_rejected_at_completion`
**PASSED**, asserting `completion.status_code == 409` and
`completion.json() == {"code": "identity_already_linked"}`, and its sibling
`test_the_rejection_mints_no_second_account_and_spends_the_challenge` **PASSED**. That is option B's
wire-level proof: the already-linked caller still earns 409 `identity_already_linked`, not the 409
`challenge_required` the unguarded ordering would have produced.

## Task 3 — the record, and the ledger's two defects

`.planning/WINDOWS.md` carries entry 33 in both places it carries an entry: one row at the end of
the markdown table and one object at the end of the fenced JSON array, with the last entry's field
set. `kind` is `deviation`, `phase` is `48`, `file` is `src/nativespeaker/api/services/auth.py`, and
`status` is `waived`.

Its description states the three facts the plan names: D-07 gives create-user the token dependency
only; planning found that a caller with an active row presents a challenge bound to that row, which
the completion path could no longer confirm, so `ChallengesDB.verify_binding` would answer 409
`challenge_required` where the route answers 409 `identity_already_linked` today; and the developer
chose option B, recorded in `48-01-SUMMARY.md`. Its reason states what option B preserves, and the
entry also records that ROADMAP criterion 3 was amended on 2026-09-16 at plan time to name
`AuthService._complete` beside `crud/challenges.py`.

**Option B's claim was checked against the source, not assumed.** `services/auth.py:77-87` shows
`complete` calling `self.identities_db.resolve(...)` **before** `_complete`, so the three rejections
still refuse a caller before the claim spends its challenge — which is why D-07's accepted cost of
one spent challenge does not ship.

**Task 3's verify set:**

| Command | Result | Verdict |
|---|---|---|
| `python -c "json.loads(re.search(r'\[[\s\S]*\]', …))"` | `JSONDecodeError: Expecting value: line 1 column 2` | FAIL as written — deviation 3 |
| the same, anchored `r'^\[[\s\S]*^\]'` with `re.M` | parses **33 entries**; statuses `{open: 19, fixed: 12, waived: 2}` | PASS corrected |
| `test "$(grep -c '"phase": "48"' …)" = "1"` | exit 0 | PASS |
| `test "$(grep -c 'waived_count: 2' …)" = "1"` | exit 0 | PASS |
| `test "$(grep -c 'total_count: 33' …)" = "1"` | exit 0 | PASS |
| `test "$(grep -c '^\| 33 \| 48 \|' …)" = "1"` | exit 0 | PASS |
| `git diff --name-only HEAD -- .planning/REQUIREMENTS.md` | no output | PASS |

Frontmatter now reads `open_count: 19`, `waived_count: 2`, `fixed_count: 12`, `total_count: 33`, and
`last_updated: 2026-09-16T22:46:00.665Z`. The parsed entries yield the same 19/2/12/33, so the
counters and the entries agree for the first time in this phase.

**The ledger accepts writes again, proved by running it.**
`gsd-tools windows status` exits 0 and reports 19/2/12/33. A probe `windows append` — the exact call
that has refused since 48-01 — now answers `"ok": true`, exit 0. The probe was reverted inside the
same command with a pre-image copy, and the file diffed byte-identical to its pre-probe state
afterwards; the probe is in no commit.

## Decisions Made

- **The plan's stale counter instruction was not followed, and the correct counters satisfy the
  plan's own criteria.** The plan says `open_count` stays 20 and `fixed_count` stays 11, both copied
  from the frontmatter that was already wrong. Writing them would have re-broken the ledger the same
  edit was meant to repair. The entries yield 19 open and 12 fixed, so the frontmatter says that.
  The plan's acceptance criteria check only `waived_count: 2` and `total_count: 33`, and 19/2/12/33
  satisfies both.
- **The second ledger defect was repaired here rather than deferred.** It lives in the one file this
  plan owns, it is the same root cause class as the counters — a rendered view that drifted from the
  record — and leaving it would have meant marking the deferred item resolved while every append
  still failed.
- **Tasks 1 and 2 make no commit.** Their whole product is the prose above, which commits with this
  SUMMARY. 47-08 and 47-02 each recorded the same.
- **The corrected grep forms are the ones 48-01 and 48-02 published**, not new inventions: the
  parameter-only filter and the `allow_preauth=` / `preauth_callable(` call-site form.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 1's third verify contradicts D-03, exactly as 48-01 predicted**

- **Found during:** Task 1
- **Issue:** The command asserts `grep -rln 'LinkedIdentity | None' src` returns exactly
  `crud/challenges.py` and `services/auth.py`. Measured, it returns a third file,
  `crud/identities.py`, because **D-03 requires** `resolve` to be annotated
  `-> LinkedIdentity | None`. The grep counts every occurrence of the spelling, including the return
  type the phase's own locked decision mandates, so it can never pass.
- **Fix:** No source change; the source is right and the check is wrong. The invariant criterion 3
  states is that only `crud/challenges.py` and `AuthService._complete` take the optional as a
  **parameter**. Measured with 48-01's published form,
  `grep -rn 'LinkedIdentity | None' src | grep -v -- '-> LinkedIdentity | None'`, which returns the
  two expected files and nothing else. The full four-line occurrence list is quoted above.
- **Files modified:** none
- **Verification:** the corrected command, exit 0; three parameters in two files, one mandated
  return type
- **Committed in:** n/a — a check correction, carried here rather than into the source

**2. [Rule 1 - Bug] Task 1's second verify counts a test method name as a call site, exactly as 48-02 predicted**

- **Found during:** Task 1
- **Issue:** `grep -rn 'get_linked_identity\|allow_preauth\|preauth_callable' src tests` prints one
  line, `tests/unit/test_app_wiring.py:65`. It is the method name
  `test_the_preauth_callable_route_still_verifies_the_token`, which describes the
  `PREAUTH_CALLABLE_PATHS` set 48-01 Task 3 keeps on purpose — not a call site, not a flag, not a
  deleted identifier. As written the gate reads a passing tree as failing.
- **Fix:** No source change. Measured with a form that distinguishes a call site from a name:
  `grep -rn 'get_linked_identity\|allow_preauth=\|preauth_callable(' src tests`, which prints
  nothing at exit 1, so the `test -z` wrapper exits 0.
- **Files modified:** none
- **Verification:** the corrected command, exit 0; the surviving line quoted in context above, with
  the live assertion it carries
- **Committed in:** n/a — a check correction

**3. [Rule 1 - Bug] Task 3's JSON verify cannot parse this ledger, and could not before this plan either**

- **Found during:** Task 3
- **Issue:** `re.search(r'\[[\s\S]*\]', …)` is greedy from the **first** `[` anywhere in the file.
  The first `[` is not the one that opens the JSON array at line 53 — it is inside entry 8's
  markdown-table description, `error_response(CLIENT_CLASS_FOR_RESULT[result])`, at line 25. The
  matched span therefore begins `[result]` and is not JSON:
  `JSONDecodeError: Expecting value: line 1 column 2 (char 1)`. Diagnosed to the line, and proved
  pre-existing: the identical command fails the same way on the **committed** file at `HEAD`, before
  any edit of mine. Entry 8 landed in phase 37.
- **Fix:** No edit to entry 8, whose description is a legitimate record. The array is anchored at a
  line-start bracket instead: `re.search(r'^\[[\s\S]*^\]', text, re.M)`. It parses 33 entries and
  yields the status counts quoted above.
- **Files modified:** none
- **Verification:** corrected command exits 0 and parses 33 entries; the as-written command's
  traceback is quoted above and reproduced against `git show HEAD:.planning/WINDOWS.md`
- **Committed in:** n/a — a check correction

**4. [Rule 3 - Blocking] The plan's counter instruction would have re-broken the ledger it repairs**

- **Found during:** Task 3
- **Issue:** The plan says `open_count` reads 20 and `fixed_count` reads 11 and "neither moves". Both
  are copied from the frontmatter that has been wrong since before this phase: the entries yield 19
  open and 12 fixed, which is precisely why `gsd-tools windows append` has refused since 48-01 with
  `frontmatter open/waived/fixed/total=20/1/11/32 but entries yield 19/1/12/32`. Writing 20 and 11
  beside the new entry would have left the counters disagreeing with the entries and the tool still
  blocked.
- **Fix:** The statuses were counted from the entries themselves — 19 open, 12 fixed, 2 waived with
  entry 33, 33 total — and the frontmatter set to that. The plan's acceptance criteria check only
  `waived_count: 2` and `total_count: 33`, both of which hold.
- **Files modified:** `.planning/WINDOWS.md`
- **Verification:** `windows status` exits 0 and reports 19/2/12/33; the parsed entries yield the
  same
- **Committed in:** `de3777f`

**5. [Rule 1 - Bug] A second, deeper ledger defect sat behind the counters**

- **Found during:** Task 3, verifying that the tool was unblocked
- **Issue:** With the counters corrected, `windows append` reached its **next** gate and refused
  again, with a different message: *"Ledger table … disagrees with the fenced JSON entries (the sole
  source of truth) for row id(s): 31."* Diagnosed: the markdown row for id 31 carries an **empty**
  `reason` cell, while the JSON entry 31 carries a full reason. Entry 31 was marked `fixed` with a
  reason in phase 47 and the rendered table row was never regenerated. Pre-existing, and invisible
  until now because the counter gate fired first. Left alone, every append in phases 48 to 50 would
  still have failed — the exact cost the deferred item names.
- **Fix:** Row 31's `reason` cell now renders the JSON reason verbatim, produced by rendering the row
  from the parsed entry rather than by retyping it. No record changed: the source of truth is the
  JSON, and the JSON is untouched.
- **Files modified:** `.planning/WINDOWS.md`
- **Verification:** the probe `windows append` afterwards answers `"ok": true`, exit 0, and was
  reverted in the same command; the file diffs identical to its pre-probe state
- **Committed in:** `de3777f`

---

**Total deviations:** 5 auto-fixed (4 bugs, 1 blocking).
**Impact on plan:** No scope creep — every edit is inside `.planning/WINDOWS.md`, this plan's one
declared file, plus the `deferred-items.md` line the phase gate was told to close. Deviations 1, 2
and 3 are the same class this phase has now recorded seven times: a plan artifact contradicting a
locked decision or the working tree, with the decision winning and the check corrected rather than
the source bent. Deviations 4 and 5 are the ones that mattered: the plan asked for a repair and
supplied the numbers that would have undone it, and the repair only revealed its second half when
the first half let the tool run.

## Broken-windows ledger

Entry **33** is written, and the ledger is healthy again. It is this plan's only ledger entry, as the
plan requires: the earlier executors' deviations live in their own SUMMARY files by this phase's
convention, and this plan's own five deviations are documented above rather than appended, because
they are check corrections in planning artifacts rather than defects in the shipped tree.

The deferred item 48-01 logged is marked `status: resolved` in
`.planning/phases/48-narrow-identity-to-the-verified-pair/deferred-items.md`, naming `de3777f`.

## Issues Encountered

None beyond the five deviations above. Each was found by running a command and reading its output,
and the two ledger defects were each diagnosed to the line — entry 8's bracketed description at
line 25 for the parse failure, and row 31's empty reason cell for the append refusal — rather than
worked around.

## Known Stubs

None. This plan writes no source, no placeholder, no hardcoded empty value and no TODO.

## TDD Gate Compliance

No task carries `tdd="true"`, and this plan writes no source, so no RED/GREEN sequence applies. Both
commits are `docs(48-08)`, which is the right type: the only files changed are planning records.

## Threat Flags

None. The plan's `<threat_model>` names no surface this execution added to.

- **T-48-08-01** (repudiation — a copied count would hide a regression) is carried by the whole of
  Task 2: every one of the five commands was run in this session at `61d4a8f`, and each result above
  is this run's own output. The baseline column is labelled as the baseline and is never the measure.
- **T-48-08-02** (a surviving deleted name) is carried by the four greps, each run over `src` and
  `tests` together, with the word-boundary form used for criterion 1 and the call-site form for
  criterion 4.
- **T-48-08-03** (an all-deselected run) is carried by the collected counts: 2573, 360 + 1, and 297,
  none of them 0, and each deselection figure quoted.
- **T-48-08-SC** holds: no package was installed and `pyproject.toml` is untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Criterion 5 is met** on this phase's terms: the failing set is exactly the one pre-existing
  restore case, which is ledger entry 29 and belongs to no phase from 47 onward. `ruff` is clean and
  `ty` fell from 311 to 306.
- **Criteria 1, 3 and 4 are met by command**, two of them in corrected forms this SUMMARY publishes
  so `/gsd:verify-work 48` does not re-hit the same two unsatisfiable greps. Anyone re-deriving the
  gate should use the parameter-only filter for criterion 3 and the call-site filter for criterion 4.
- **The ledger is usable again for phases 49 and 50.** The deferred item is closed and `append`
  answers `ok: true`.
- **One carried note for whoever owns the ledger tooling:** the `windows` table is a rendered view of
  the fenced JSON, and two separate drifts between them have now cost this phase a blocked tool. The
  JSON stays the source of truth; the table should be regenerated by the tool rather than edited.

## Self-Check: PASSED

- `.planning/WINDOWS.md` — FOUND; parses at 33 entries; frontmatter 19/2/12/33 matches the entries;
  exactly one `"phase": "48"`; exactly one `^| 33 | 48 |` row
- `.planning/phases/48-narrow-identity-to-the-verified-pair/deferred-items.md` — FOUND, item marked
  `status: resolved` naming `de3777f`
- Commits `de3777f` and `dda9344` — both present in `git log`
- Every `<acceptance_criteria>` of all three tasks re-run above: ten pass outright, three are
  recorded failed-as-written with their measurement and passing in corrected form
- Plan-level `<verification>` re-run above; all three lines pass
- Neither commit deletes a tracked file (`git diff --diff-filter=D --name-only 61d4a8f..HEAD` is
  empty)
- No file outside this plan's scope was edited (`git diff --name-only 61d4a8f..HEAD` lists
  `.planning/WINDOWS.md` and the phase's `deferred-items.md`, and nothing else)
- `.planning/REQUIREMENTS.md` is unchanged, and no source or test file was touched

---
*Phase: 48-narrow-identity-to-the-verified-pair*
*Completed: 2026-09-16*
