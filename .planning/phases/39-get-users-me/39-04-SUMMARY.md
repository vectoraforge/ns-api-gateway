---
phase: 39-get-users-me
plan: 04
subsystem: testing
tags: [pytest, e2e, postgres, httpx, sqlalchemy, firebase]

requires:
  - phase: 39-get-users-me
    provides: "plan 39-01's route, PurchasesDB.read_tokens, MissingPurchaseTokenError and the seed_purchase_tokens fixture"
  - phase: 38-auth-sync
    provides: "tests/e2e/test_sync.py — _stored_provider, the barrier-rejection template and the snapshot shape this plan mirrors"
  - phase: 35-foundation
    provides: "the pre-handler auth barrier that produces the 401 and the 403 this plan asserts reach /users/me"
provides:
  - "Nine committed e2e cases over the real database and the real transport for GET /users/me"
  - "The permanent fail-closed assertions 39-01 could only prove with a deleted probe: zero rows and one row, both the same opaque 500"
  - "Cross-endpoint agreement: /users/me and /auth/sync proven to report the same stored identity_provider in one run"
  - "_account_snapshot — the token/user/identity SELECT * snapshot plus whole-table counts, the writes-nothing assertion for this route"
affects: [restore-subscription, app-store-webhook]

actuals:
  tokens: 2659
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A readback helper that names the table in raw SQL rather than reading through the same ORM mapping the route reads through"
    - "Cross-endpoint agreement asserted in one test against one seeded caller, both sides also pinned to the stored row"

key-files:
  created: []
  modified:
    - tests/e2e/test_users_me.py

key-decisions:
  - "_stored_tokens was converted from the ORM projection to a raw SELECT over core.store_purchase_tokens, so the readback cannot inherit a wrong column mapping from the code under test"
  - "The two provider cases live in their own TestTheProviderComesFromTheStoredColumn class mirroring test_sync.py, rather than inside the happy-path class, while the token-value readback extends the happy-path class"
  - "apple_linked_identity is defined locally in test_users_me.py; the analog in test_sync.py is a module fixture, not a conftest one, and importing a fixture across test modules would be an implicit dependency"
  - "_stored_provider is imported from .test_sync rather than reimplemented, as the plan requires — it is a plain async helper, so the import is explicit and carries nothing else"

patterns-established:
  - "Cross-endpoint agreement case: two routes reading one stored column asserted equal to each other and to the row, in one test"
  - "Partial-account fail-closed case: seed_purchase_tokens(providers=[one member]) is the sharp edge an emptiness check passes and completeness refuses"

requirements-completed: [PROF-01, PROF-02]

coverage:
  - id: D1
    description: "identity_provider is the value stored in core.external_identities for the caller, not a default or a token claim"
    requirement: PROF-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheProviderComesFromTheStoredColumn::test_a_non_google_caller_reports_its_stored_provider"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /users/me and POST /auth/sync report the same identity_provider for the same caller within one run, for a non-default provider"
    requirement: PROF-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheProviderComesFromTheStoredColumn::test_both_routes_report_the_same_provider_for_the_same_caller"
        status: pass
    human_judgment: false
  - id: D3
    description: "Each purchase_tokens value equals the identity_value read back out of core.store_purchase_tokens for that provider"
    requirement: PROF-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheProfileHappyPath::test_every_token_value_is_the_one_stored_for_that_store"
        status: pass
    human_judgment: false
  - id: D4
    description: "A caller with no token rows receives 500 with the body exactly {\"code\": \"internal_error\"}"
    requirement: PROF-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheFailClosedFiveHundred::test_a_caller_with_no_token_rows_is_an_opaque_500"
        status: pass
    human_judgment: false
  - id: D5
    description: "A caller with exactly one of the two token rows receives the same opaque 500 — the partial-account case"
    requirement: PROF-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheFailClosedFiveHundred::test_a_caller_holding_one_of_the_two_rows_is_the_same_500"
        status: pass
    human_judgment: false
  - id: D6
    description: "A request with no credential receives 401 auth_required; a verified but unlinked caller receives 403 preauth_identity_not_allowed"
    requirement: PROF-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheRouteInheritsTheBarriersRejections::test_a_caller_with_no_credential_is_rejected"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheRouteInheritsTheBarriersRejections::test_a_verified_but_unlinked_caller_is_rejected"
        status: pass
    human_judgment: false
  - id: D7
    description: "Table state for core.store_purchase_tokens, core.external_identities and core.users, plus the whole-table counts, is byte-identical before and after a 200"
    requirement: PROF-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheRequestChangesNothing::test_a_successful_read_leaves_every_row_untouched"
        status: pass
    human_judgment: false
  - id: D8
    description: "A repeated request answers byte-identical bodies over rows that are still unchanged — assumption E4 made executable"
    requirement: PROF-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_users_me.py#TestTheRequestChangesNothing::test_a_repeated_request_answers_the_same_bytes_over_the_same_rows"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-09-02
status: complete
---

# Phase 39 Plan 04: The Real-Stack Properties of GET /users/me Summary

**Nine e2e cases over real PostgreSQL and a real Firebase credential proving `identity_provider` comes from the stored column and agrees with `/auth/sync`, that zero and one token rows both fail closed as the same opaque 500, and that a 200 leaves every asserted table byte-identical.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-09-02T03:33Z
- **Completed:** 2026-09-02T03:46Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments

- `identity_provider` is proven to be the stored `core.external_identities.provider` value: an apple-seeded caller is asserted different from the happy-path default first, so the case cannot pass while proving nothing, and then asserted equal to the readback.
- `GET /users/me` and `POST /auth/sync` are proven to report the same provider for the same caller in a single test, both pinned to the row — Phase 38 D-06's standing obligation, now executable.
- The fail-closed arm is permanent. Zero token rows and exactly one token row both answer 500 with `{"code": "internal_error"}` asserted as a whole literal, replacing the throwaway probe 39-01 deliberately did not commit.
- The barrier's 401 and 403 are proven to reach the new route, with the no-credential case built on its own `ASGITransport` client so the pre-authenticated fixture cannot turn it into a silent pass, and the 403 read off `PreAuthIdentityNotAllowed.status`/`.code`.
- A successful read is proven to change nothing: every column of the caller's token, user and identity rows via `SELECT *`, plus three whole-table counts, identical before and after — and identical again after a repeated request whose body is byte-for-byte the same.

## Task Commits

Each task was committed atomically:

1. **Task 1: The stored column, read back, and agreeing across both endpoints** — `6c31a53` (test)
2. **Task 2: The fail-closed arm and the barrier's rejections** — `e017e0d` (test)
3. **Task 3: The route writes nothing** — `4b6d30c` (test)

## Files Created/Modified

- `tests/e2e/test_users_me.py` — grew from 3 cases to 12. Added `TestTheProviderComesFromTheStoredColumn` (2), `TestTheFailClosedFiveHundred` (2), `TestTheRouteInheritsTheBarriersRejections` (2), `TestTheRequestChangesNothing` (2), one token-readback case on the happy-path class, the local `apple_linked_identity` fixture, and the `_account_snapshot` helper with its four `text()` statements. `_stored_tokens` was rewritten to read the table by name.

## Decisions Made

- **`_stored_tokens` reads raw SQL, not the ORM projection.** It previously selected `StorePurchaseToken.provider, .identity_value` — the same mapping `PurchasesDB.read_tokens` reads through, so a wrong column mapping would have been invisible to the readback. It now issues `SELECT provider, identity_value FROM core.store_purchase_tokens`, which is also what makes the table's name appear in the file at task 1's commit rather than only at task 3's.
- **The provider cases got their own class.** The plan said "extend the happy-path class"; `tests/e2e/test_sync.py:255` puts the identical rule in `TestTheProviderComesFromTheStoredColumn`, and the pattern map names test_sync as the exact analog. The token-value readback did extend `TestTheProfileHappyPath`, where it belongs. Class-per-rule with a docstring stating the rule is the file's register.
- **`apple_linked_identity` is defined locally.** The plan's `read_first` located it in `tests/e2e/conftest.py`; it is actually a module-level fixture in `tests/e2e/test_sync.py:245`. Importing a fixture across test modules works only as an implicit namespace side effect and would need a `noqa` for the unused import, so the six-line fixture is defined in this file instead.
- **`_stored_provider` is imported from `.test_sync`.** It is a plain async helper with no fixture semantics, so the import is explicit and reuses the helper verbatim as the plan requires.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The worktree had no `.env`, so no e2e test could run**

- **Found during:** Setup, before task 1
- **Issue:** `.env` is gitignored, so this parallel worktree was created without it. `pytest-dotenv` reads `.env` relative to rootdir; without it the e2e fixtures reach neither PostgreSQL nor Firebase, and every verification in this plan is an e2e run.
- **Fix:** Symlinked the main checkout's `.env` (`/home/init/native-speaker/ns-api-gateway/.env`) into the worktree root — the same resolution 39-01 recorded. Confirmed the infrastructure with the pre-existing `tests/e2e/test_sync.py` (14 passed) before writing anything.
- **Files modified:** none tracked — `.env` is gitignored and was not committed.
- **Verification:** `uv run pytest -q -m e2e tests/e2e/test_sync.py` → 14 passed.
- **Committed in:** nothing; the symlink is a test-environment fixture, not a source change.

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** None on scope. It is a precondition of running any e2e test in a fresh worktree, and it will recur for every future worktree agent until `.env` provisioning is handled by the harness.

## Issues Encountered

- **The plan's `read_first` mislocated two symbols.** `apple_linked_identity` and `_stored_provider` were cited at `tests/e2e/conftest.py:163-199`; both actually live in `tests/e2e/test_sync.py` (`:245` and `:71`). Resolved by reading the real source first, as the wave brief instructed: the helper is imported from where it is, the fixture is defined locally.
- **No red case to report.** The plan's prohibition against patching the route around a red case never came into play — all nine new cases passed against 39-01's committed source on their first run, including both fail-closed arms.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | 12 passed |
| `uv run pytest -q -m ""` | 1096 passed |
| `uv run ruff check` | All checks passed |
| `uv run pytest -q tests/unit/test_sync_audit_removal.py` | 6 passed, source unchanged |
| `uv run pytest -q tests/unit/test_docstring_bar.py` | 9 passed — `tests/e2e` still at a baseline of 0 |
| `git status --porcelain migrations/ specs/` | empty |
| `grep -cF '_stored_provider'` / `'/auth/sync'` / `'store_purchase_tokens'` | 4 / 2 / 4 |
| `grep -cF '{"code": "internal_error"}'` / `'PreAuthIdentityNotAllowed.status'` / `'providers='` | 2 / 1 / 1 |
| `grep -cF 'SELECT *'` / `'count(*)'` | 4 / 3 |

## Known Stubs

None. Every case added asserts against the real stack and passes; nothing is skipped, xfailed or placeholdered.

## Prohibitions Observed

No audit table, writer or call site is referenced. No test drives `POST /auth/create-user`. No test asserts a purchase token is absent from a log line. No assertion accepts a null or partial `purchase_tokens` entry. No test seeds one token row and expects a 200 — the one case that seeds a subset expects the 500. `identity_provider` is never derived from a `purchase_tokens` key or the reverse. The route's source is untouched: this plan's diff is one file under `tests/`.

## Threat Flags

None. The register's five rows were implemented as written — T-39-01 and T-39-03 by task 2, T-39-04 by task 1's per-caller readbacks, T-39-12 by task 3's snapshot, T-39-13 accepted with `test_sync_audit_removal.py` asserted green and unchanged. No new endpoint, auth path, file access or schema change was introduced.

## User Setup Required

None — no external service configuration required. Note for any future worktree agent: `.env` is gitignored and must be symlinked or copied in before any e2e run.

## Next Phase Readiness

- Roadmap criteria 2 and 4 now have committed e2e proof; 39-01's coverage item D4, recorded `human_judgment: true` pending exactly these tests, is satisfied by D4 and D5 above.
- `STATE.md`, `ROADMAP.md` and `REQUIREMENTS.md` were deliberately left untouched — the orchestrator owns them, and PROF-01/PROF-02 are claimed by all four plans in this phase, so neither is complete until the phase is.
- No blockers.

## Self-Check: PASSED

`tests/e2e/test_users_me.py` exists on disk with all 12 cases collected; all three commit hashes (`6c31a53`, `e017e0d`, `4b6d30c`) are present in `git log`.

---
*Phase: 39-get-users-me*
*Completed: 2026-09-02*
