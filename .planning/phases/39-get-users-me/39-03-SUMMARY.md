---
phase: 39-get-users-me
plan: 03
subsystem: api
tags: [pytest, fastapi, testclient, sqlalchemy, unit-tests, characterization]

requires:
  - phase: 39-get-users-me
    plan: 01
    provides: "`routers/users.py::me`, `crud/purchases.py::PurchasesDB.read_tokens`, `get_purchases_db`, `MissingPurchaseTokenError`, `Profile`/`MeResponse` — every symbol these tests import"
  - phase: 35-foundation
    provides: "`get_linked_identity`, the barrier these tests override rather than exercise"
provides:
  - The closed-body ratchet on GET /users/me — whole-literal equality, so a fourth key fails
  - The client-signal invariance ratchet — five signals compared as bytes against a baseline
  - The one-unlocked-query proof at both route and crud level
  - The permanent fail-closed assertions for the 500 arm, replacing 39-01's deleted probe
affects: [39-04, restore-subscription, app-store-webhook]

actuals:
  tokens: 9800
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A recording session behind the real crud class, injected at the `get_purchases_db` seam: the route unit test keeps a real statement to assert on while touching no database"
    - "A positive companion assertion beside every negative substring assertion, so a compiled-to-empty-string regression cannot pass vacuously"
    - "Byte-level baseline comparison as the executable form of client-signal invariance"

key-files:
  created:
    - tests/unit/test_users_me.py
    - tests/unit/test_purchases_crud.py
  modified: []

key-decisions:
  - "`get_purchases_db` is overridden with a real `PurchasesDB` over a recording session rather than with a crud double — a pure crud double records no statements, and the plan's own behaviour list requires asserting the statement count and compiled text"
  - "Every negative substring assertion is paired with a positive one (`core.store_purchase_tokens` is present) so an empty compiled string cannot pass the `core.users` and lock checks vacuously"
  - "`set(PurchaseProvider)` is bound once to `EVERY_STORE` and compared via `{store.value for store in EVERY_STORE}` on the wire side, so the wire comparison is against strings and never relies on `StrEnum` hashing coinciding with member names"
  - "The route-level 500 arm was included in Task 1 even though its behaviour list does not name it: the plan mandates `raise_server_exceptions=False` specifically so that arm renders, which would otherwise be dead configuration"

patterns-established:
  - "Characterization tests for a tracer's already-landed code commit as `test(...)` alone — there is no GREEN commit because the plan forbids editing `src/`"

requirements-completed: []

coverage:
  - id: D-01
    description: "The 200 body equals a whole literal — a fourth top-level key or a fifth profile field fails"
    requirement: PROF-01
    verification:
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestTheProfileBodyIsClosed::test_a_linked_caller_reads_the_whole_body_and_nothing_more"
        status: pass
    human_judgment: false
  - id: D-07a
    description: "set(purchase_tokens) equals the PurchaseProvider member set on every 200"
    requirement: PROF-01
    verification:
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestTheProfileBodyIsClosed::test_the_token_map_carries_one_key_per_store"
        status: pass
      - kind: unit
        ref: "tests/unit/test_purchases_crud.py#TestACompleteAccountReadsBackItsTokens::test_the_mapping_carries_one_entry_per_store"
        status: pass
    human_judgment: false
  - id: D-02
    description: "The body is identical across a differing User-Agent, an unknown platform header, and an unknown query parameter"
    requirement: PROF-01
    verification:
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestTheBodyIgnoresEveryClientSignal::test_the_response_is_byte_identical_to_the_baseline (5 cases)"
        status: pass
    human_judgment: false
  - id: D-03
    description: "The handler issues exactly one statement and none of them names the users table"
    requirement: PROF-01
    verification:
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestTheProfileTakesOneQuery (3 cases)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_purchases_crud.py#TestTheReadTakesOneUnlockedStatement::test_no_statement_reads_the_users_table"
        status: pass
    human_judgment: false
  - id: D-09
    description: "The 200 carries Cache-Control: no-store, by equality and not containment"
    requirement: PROF-01
    verification:
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestTheProfileBodyIsClosed::test_the_body_is_never_stored_by_a_cache"
        status: pass
    human_judgment: false
  - id: D-07b
    description: "Zero token rows raises, one row raises, and both rows return the mapping — 39-01's D4, now with committed assertions"
    requirement: PROF-01
    verification:
      - kind: unit
        ref: "tests/unit/test_purchases_crud.py#TestAnIncompleteAccountIsRefused::test_an_unrepresented_store_raises (3 cases: no-store-row, apple-only, google-play-only)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_users_me.py#TestAnIncompleteAccountIsAnOpaqueFailure::test_a_missing_store_row_answers_the_generic_500 (3 cases)"
        status: pass
    human_judgment: false
  - id: D-lock
    description: "The purchase-token statement compiles under the PostgreSQL dialect with no lock clause"
    requirement: PROF-01
    verification:
      - kind: unit
        ref: "tests/unit/test_purchases_crud.py#TestTheReadTakesOneUnlockedStatement::test_the_statement_takes_no_lock"
        status: pass
    human_judgment: false
  - id: D-06
    description: "The raised exception names the user id and the missing provider values and never the token column value"
    requirement: PROF-02
    verification:
      - kind: unit
        ref: "tests/unit/test_purchases_crud.py#TestAnIncompleteAccountIsRefused::test_the_message_names_the_user_and_every_missing_store (3 cases)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_purchases_crud.py#TestAnIncompleteAccountIsRefused::test_no_token_value_reaches_the_message (3 cases)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-01
status: complete
---

# Phase 39 Plan 03: The Route's Closed Body and the Completeness Rule Summary

**Thirty-three unit cases that pin what the tracer only demonstrated once — the payload as a whole literal, the key set read off the enum, five client signals proven inert byte for byte, one unlocked statement, and the one-row partial account refused exactly as a zero-row one is.**

## Performance

- **Duration:** 12 min
- **Tasks:** 2
- **Files created:** 2 (no file modified, no file under `src/` touched)
- **Cases added:** 33 (18 + 15); quick suite went from 773 to 806 passing

## Accomplishments

- `tests/unit/test_users_me.py` (18 cases) holds the route's contract: the body as one literal, the token key set derived from `PurchaseProvider`, `cache-control` by equality, exactly one statement that names `core.store_purchase_tokens` and never `core.users`, five client-supplied signals whose responses are byte-identical to a baseline, a both-fields-null caller still reading both store keys, and all three incomplete-account arms answering the opaque `{"code": "internal_error"}`.
- `tests/unit/test_purchases_crud.py` (15 cases) holds the read's contract: the complete mapping, the three incomplete seeds each raising with the missing stores named and the user id present, neither stubbed token value reaching `str(error)`, and the statement proven singular, lock-free and table-scoped under `postgresql.dialect()`.
- **39-01's coverage item D4 is now discharged by committed tests.** The tracer proved the fail-closed 500 with a throwaway probe that was deleted; both arms (zero rows, and each single-store partial account) now have named, reported cases at crud level and at route level.
- Both files run in well under a second and are inside the default `uv run pytest -q` selection — no marker, no infrastructure, no `.env`.

## Task Commits

1. **Task 1: The route's closed, unconditional body** — `7e37ae3`
2. **Task 2: The completeness rule and the unlocked read** — `c048dfd`

## Files Created

- `tests/unit/test_users_me.py` — the route unit file: `_RecordingSession`/`_RecordingResult`, the `_client_for` context manager building a bare `FastAPI()` with `users_router`, `register_exception_handlers` and the two dependency overrides, and five test classes
- `tests/unit/test_purchases_crud.py` — the crud unit file: `_StubSession`/`_StubResult` yielding `(provider, identity_value)` tuples, the `_compiled` helper over `postgresql.dialect()`, and three test classes

## Decisions Made

- **The `get_purchases_db` override injects a real `PurchasesDB` over a recording session, not a crud double.** The plan's action text asks for "a recording double for the crud class rather than a real session", but its own behaviour list requires asserting that "the recording double saw exactly one statement, and no statement's compiled text names the users table" — a pure crud double is handed no statements and could satisfy neither. Substituting at the `get_purchases_db` seam (as the fixture instruction requires) while letting the real `read_tokens` run over a recording session satisfies both halves and makes the route-level 500 arm arise genuinely rather than from a double that was told to raise.
- **Every negative substring assertion has a positive companion.** `test_the_statement_reads_the_token_table` exists in both files purely so that `"core.users" not in _compiled(...)` and `LOCK_CLAUSE not in _compiled(...)` cannot pass on an empty string if `_compiled` ever degrades. Without it the no-lock and no-users proofs are vacuously satisfiable.
- **The wire-side key set compares strings, not enum members.** `EVERY_STORE = set(PurchaseProvider)` supplies the enum-derived source the acceptance grep asks for, but the assertion is `{store.value for store in EVERY_STORE}`. Comparing a JSON key set directly against `set(PurchaseProvider)` would only pass because `Enum.__hash__` hashes the member *name*, which coincides with the value for these two members — a coincidence a third store named differently from its value would break. The crud-side assertion, whose keys really are enum members, compares against `EVERY_STORE` directly.
- **The route-level 500 arm is in Task 1 despite not being in its behaviour list.** The plan mandates `raise_server_exceptions=False` and states it "is required so the 500 arm renders through the shared handler"; without a case exercising that arm the flag is dead configuration. Six cases were added (three seeds x two assertions). This is additive and violates no prohibition — none expects a 200 from a partial seed.
- **`_INCOMPLETE_SEEDS` carries its expected `missing` list alongside each seed** so `error.missing` is asserted per case rather than only the exception type, which is what makes the apple-only and google-play-only cases distinguishable in the report.

## Deviations from Plan

### Auto-fixed Issues

None. No bug, no missing critical functionality and no blocker was encountered; both files were written, run and committed as planned.

**Total deviations:** 0.

## TDD Gate Compliance

Both tasks are marked `tdd="true"`, but **neither has a GREEN commit, and this is correct rather than a skipped gate.** The units under test — `routers/users.py::me` and `crud/purchases.py::read_tokens` — were landed by plan 39-01 in wave 1; this plan's frontmatter prohibits touching them (`"The route's source is not modified by this plan — if a case goes red, report it rather than edit src/"`). There is therefore no implementation for a GREEN commit to contain. Both commits are `test(...)`, and both files were green on their first run.

Because a genuine RED phase was impossible, non-vacuity was defended structurally instead: every negative substring assertion is paired with a positive one that would fail if the compiled text degraded, the invariance cases compare against a baseline captured from the same live client rather than a hard-coded blob, and the incomplete-account cases are parametrised per seed so a single arm silently passing is visible in the report. No case went red, so nothing had to be reported back as a source bug — the handler branches on no client signal, issues one statement, and fails closed on a partial account exactly as 39-01 claimed.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -q tests/unit/test_users_me.py` | 18 passed |
| `uv run pytest -q tests/unit/test_purchases_crud.py` | 15 passed |
| `uv run pytest -q` | 806 passed, 314 deselected (32.04s) |
| `uv run ruff check` | All checks passed |
| `uv run pytest -q tests/unit/test_docstring_bar.py` | 9 passed — `tests/unit` still at baseline 0 |
| `grep -c 'response.json() ==' tests/unit/test_users_me.py` | 2 (≥1) |
| `grep -cF 'headers["cache-control"] == "no-store"' tests/unit/test_users_me.py` | 1 (≥1) |
| `grep -cF 'set(PurchaseProvider)' tests/unit/test_users_me.py` | 1 (≥1) |
| `grep -c 'parametrize' tests/unit/test_users_me.py` | 3 (≥1) |
| `test_users_me.py --collect-only` | 18 collected (≥8) |
| `grep -cF 'MissingPurchaseTokenError' tests/unit/test_purchases_crud.py` | 2 (≥2) |
| `grep -cF 'set(PurchaseProvider)' tests/unit/test_purchases_crud.py` | 1 (≥1) |
| `grep -cF 'postgresql.dialect()' tests/unit/test_purchases_crud.py` | 1 (≥1) |
| `test_purchases_crud.py --collect-only` | 15 collected (≥5, includes both single-provider seeds) |
| `git diff --name-only HEAD~2 HEAD` | `tests/unit/test_purchases_crud.py`, `tests/unit/test_users_me.py` — nothing outside `tests/` |

## Known Stubs

None. Both files exercise real production symbols; the only doubles are the session stand-ins the plan prescribes, and each is asserted against rather than merely satisfied.

## Threat Flags

None. The four mitigations the plan's register assigns to this plan are all implemented as written: T-39-01 by the three incomplete-seed raising cases, T-39-02 by `test_no_token_value_reaches_the_message`, T-39-05 by the five parametrised invariance cases, T-39-06 by the `cache-control` equality case. T-39-11 stays accepted — both token constants are fixtures, and no live credential enters either file. No new surface was introduced; these commits add only test files.

## Prohibitions Observed

No branch on a User-Agent, a platform header or a query parameter was introduced into the route — nothing under `src/` was touched at all, and no invariance case went red. No test asserts a purchase token is absent from a log line. No test seeds one token row and expects a 200; the two single-store seeds each expect a raise (crud) or a 500 (route). No null or partial `purchase_tokens` entry is accepted by any assertion.

## Notes for the Orchestrator

- `.env` was **not** needed and was not created or symlinked. Both files are pure unit tests inside the default marker selection, and the whole quick suite ran green in this worktree without one.
- `STATE.md`, `ROADMAP.md` and `REQUIREMENTS.md` are untouched, as the parallel-executor contract requires. `requirements-completed` is deliberately empty: PROF-01 and PROF-02 are claimed by all four plans in this phase, so neither closes until 39-04 lands.
- 39-01's coverage item D4 was recorded with `human_judgment: true` pending exactly these tests. They now exist and are committed; the verifier can resolve D4 against `TestAnIncompleteAccountIsRefused` and `TestAnIncompleteAccountIsAnOpaqueFailure` rather than against the deleted probe.

## Self-Check: PASSED

Both created files exist on disk; both commit hashes (`7e37ae3`, `c048dfd`) are present in `git log`.

---
*Phase: 39-get-users-me*
*Completed: 2026-09-01*
