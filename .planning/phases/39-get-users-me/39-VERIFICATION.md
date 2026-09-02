---
phase: 39-get-users-me
verified: 2026-09-02T12:00:00Z
status: passed
score: 13/13 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification: false
---

# Phase 39: GET /users/me Verification Report

**Phase Goal:** Rewrite the profile endpoint to return profile fields, stored registration
state, and per-store purchase-attribution tokens.
**Verified:** 2026-09-02T12:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 (RM-SC1) | Response carries an entry for every store provider regardless of client platform, User-Agent, or any client-supplied signal | ✓ VERIFIED | `src/nativespeaker/api/crud/purchases.py:22-25` raises on `set(PurchaseProvider) - set(tokens)`; `tests/unit/test_users_me.py::TestTheBodyIgnoresEveryClientSignal` (5 parametrised cases, byte-identical to baseline) and `tests/e2e/test_users_me.py::TestTheProfileHappyPath::test_the_token_map_carries_one_key_per_store` both pass. Ran locally: 33/33 `test_users_me.py`+`test_purchases_crud.py` unit cases pass, 12/12 e2e cases pass. |
| 2 (RM-SC2) | `identity_provider` comes from the stored column and matches what `/auth/sync` reports | ✓ VERIFIED | `src/nativespeaker/api/routers/users.py:27` reads `identity.identity.provider` (barrier-resolved row, no second query). `tests/e2e/test_users_me.py::TestTheProviderComesFromTheStoredColumn::test_a_non_google_caller_reports_its_stored_provider` and `::test_both_routes_report_the_same_provider_for_the_same_caller` (calls both `GET /users/me` and `POST /auth/sync` against one seeded caller and asserts agreement) — both pass. |
| 3 (RM-SC3) | No `audit.auth_events` row is ever written by this route, including on admission rejection | ✓ VERIFIED | Confirmed trivially true per Phase 37.1: `grep -rn "audit.auth_events\|auth_events" src/` returns nothing; no audit table, writer, or call site exists anywhere in `src/`. `tests/unit/test_sync_audit_removal.py` (guards the removal) is green and its source is unchanged by this phase. |
| 4 (RM-SC4) | A missing purchase-token row fails closed as an internal error rather than returning a null entry | ✓ VERIFIED | `crud/purchases.py`'s completeness check (`set(PurchaseProvider) - set(tokens)`, never an emptiness check) raises `MissingPurchaseTokenError`. Zero-row and one-row-only cases both proven at unit level (`tests/unit/test_purchases_crud.py::TestAnIncompleteAccountIsRefused`, 3 parametrised cases) and at route/e2e level (`tests/unit/test_users_me.py::TestAnIncompleteAccountIsAnOpaqueFailure`, `tests/e2e/test_users_me.py::TestTheFailClosedFiveHundred` — both the zero-row and the one-row-of-two case assert the whole body `{"code": "internal_error"}` as a literal). This discharges 39-01-SUMMARY's coverage item D4 (previously proven only by a deleted throwaway probe); the permanent tests now exist, are committed, and pass. |
| 5 (D-01) | The 200 body's top-level key set is exactly `{profile, identity_provider, purchase_tokens}`, asserted as a whole literal | ✓ VERIFIED | `src/nativespeaker/api/schemas/auth.py:73-77` (`MeResponse`). `tests/unit/test_users_me.py::TestTheProfileBodyIsClosed::test_a_linked_caller_reads_the_whole_body_and_nothing_more` asserts `response.json() ==` a whole literal; `tests/e2e/test_users_me.py::TestTheProfileHappyPath` does the same against the real stack. |
| 6 (D-03) | `identity_provider` is typed `IdentityProvider` (not derived from a store key) and the handler issues exactly one statement, never one that names `core.users` | ✓ VERIFIED | `schemas/auth.py:76` types the field `IdentityProvider`; `routers/users.py:27` reads it off the barrier's already-loaded identity. `tests/unit/test_users_me.py::TestTheProfileTakesOneQuery` and `tests/unit/test_purchases_crud.py::TestTheReadTakesOneUnlockedStatement::test_no_statement_reads_the_users_table` both pass, asserting the statement count and compiled text via a recording session. |
| 7 (D-09) | The 200 response carries `Cache-Control: no-store` | ✓ VERIFIED | `routers/users.py:24`. Asserted by equality (not containment) in `tests/unit/test_users_me.py::TestTheProfileBodyIsClosed::test_the_body_is_never_stored_by_a_cache` and `tests/e2e/test_users_me.py::TestTheProfileHappyPath::test_the_body_is_never_stored_by_a_cache`. |
| 8 (D-08) | `/users/me` is a registered route declaring `get_linked_identity` and appears in neither `PUBLIC_PATHS` nor `PREAUTH_CALLABLE_PATHS`; the barrier's 401/403 reach it | ✓ VERIFIED | `app/main.py` registers `users_router`; `routers/users.py:10` declares `dependencies=[Depends(get_linked_identity)]` at router level. `tests/unit/test_app_wiring.py` parametrises both named cases over `("/auth/sync", "/users/me")` — confirmed by `grep`, both pass. `tests/e2e/test_users_me.py::TestTheRouteInheritsTheBarriersRejections` proves 401 (`auth_required`, built on a fresh client, not the pre-authenticated fixture) and 403 (`PreAuthIdentityNotAllowed.status`/`.code`, read off the class) both pass. |
| 9 (D-lock) | The purchase-token statement compiles under the PostgreSQL dialect with no lock clause | ✓ VERIFIED | `tests/unit/test_purchases_crud.py::TestTheReadTakesOneUnlockedStatement::test_the_statement_takes_no_lock`, compiled via `postgresql.dialect()`, paired with a positive companion assertion so the check cannot pass vacuously on an empty string. Passes. |
| 10 (D-06) | The raised exception's message names the user id and missing providers, never the token value; neither reaches the response body or headers | ✓ VERIFIED | `errors.py:247-255` (`MissingPurchaseTokenError`) formats only `user_id` and provider names; declares neither `status` nor `code` (both inherited) and does not override `log_fields()`. `tests/unit/test_purchases_crud.py::TestAnIncompleteAccountIsRefused::test_no_token_value_reaches_the_message` and `tests/unit/test_error_contract.py::TestTheBodyStaysOneFieldAndCarriesNoIdentifier[missing_purchase_token]` (3 cases) both pass. |
| 11 (PROF-02 / write) | A successful request leaves `core.store_purchase_tokens`, `core.users`, `core.external_identities` (full `SELECT *` snapshot) and their whole-table counts byte-identical; a repeated request returns identical bytes | ✓ VERIFIED | `tests/e2e/test_users_me.py::TestTheRequestChangesNothing` (`test_a_successful_read_leaves_every_row_untouched`, `test_a_repeated_request_answers_the_same_bytes_over_the_same_rows`) — both pass against the real database. |
| 12 (D-05) | `AGENTS.md` § "Package layout" states a router may call `crud/` directly, a `services/` class is earned by complexity, the `Depends()`-only clause survives, and all four numbered exceptions survive | ✓ VERIFIED | Read `AGENTS.md:24-58` directly: contains "A router may call `crud/` directly", "Introduce a `services/` class when the router body would otherwise become too big or complicated: a service is earned by complexity, not assumed by category", the restated `Depends()` only paragraph, and all four numbered exceptions including "the rejection stays with the query in `crud/`" (exception 4). `grep` counts match plan acceptance criteria exactly. |
| 13 (REQ-amend) | `.planning/REQUIREMENTS.md` PROF-01 carries a dated Phase 39 amendment recording D-02/D-03; PROF-02's Phase 37.1 block is untouched; no file under `specs/` was edited | ✓ VERIFIED | Read `.planning/REQUIREMENTS.md:211-221` directly: one `"Amended by Phase 39 (D-02/D-03), 2026-09-01"` block sits between the PROF-01 and PROF-02 bullets, naming `expire_on_commit=False` and the rate-limit-engine omission; the pre-existing `"Amended by Phase 37.1"` PROF-02 block is present and unchanged. |

**Score:** 13/13 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/crud/purchases.py` | `PurchasesDB.read_tokens` — one unlocked read, completeness check | ✓ VERIFIED | Exists, substantive, wired via `get_purchases_db`, real query against `StorePurchaseToken` |
| `src/nativespeaker/api/routers/users.py` | `GET /users/me` handler | ✓ VERIFIED | Exists, registered, narrowed, builds `MeResponse` from real barrier + crud reads |
| `src/nativespeaker/api/errors.py` | `MissingPurchaseTokenError(InternalError)` | ✓ VERIFIED | Present at `:247-255`, `log_level = logging.ERROR`, no status/code override |
| `src/nativespeaker/api/schemas/auth.py` | `Profile`, `MeResponse` | ✓ VERIFIED | Present at `:67-77`, correctly typed (`IdentityProvider`, `dict[PurchaseProvider, str]`) |
| `src/nativespeaker/api/app/dependencies.py` | `get_purchases_db` | ✓ VERIFIED | Present, `Depends(get_db)` seam |
| `tests/e2e/test_users_me.py` | e2e proof suite | ✓ VERIFIED | 12 cases across 5 classes, all pass against real PostgreSQL + Firebase |
| `tests/unit/test_users_me.py` | route unit proof | ✓ VERIFIED | 18 cases, all pass |
| `tests/unit/test_purchases_crud.py` | crud unit proof | ✓ VERIFIED | 15 cases, all pass |
| `AGENTS.md` | § Package layout amendment | ✓ VERIFIED | Amended as described, constraints intact |
| `.planning/REQUIREMENTS.md` | PROF-01 dated amendment | ✓ VERIFIED | Present, PROF-02 block untouched |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `app/main.py` | `routers/users.py` | `app.include_router(users_router)` | ✓ WIRED | `grep -c "app.include_router(users_router)" app/main.py` = 1 |
| `routers/users.py` | `app/dependencies.py::get_purchases_db` | `Depends(get_purchases_db)` | ✓ WIRED | Parameter present, real `PurchasesDB(db)` returned |
| `errors.py::MissingPurchaseTokenError` | `tests/unit/test_rejection_vocabulary.py` | `EVENT_NAMES` + `CONSTRUCTOR_ARGUMENTS` | ✓ WIRED | `missing_purchase_token_error` present, same-commit per SUMMARY |
| `crud/purchases.py` | `tables/purchases.py` | `PurchaseProvider`, `StorePurchaseToken` import | ✓ WIRED | `IdentitiesDB` not widened; separate class confirmed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `MeResponse.profile` | `identity.user.email`/`.display_name` | Barrier-resolved `core.users` row (detached, `expire_on_commit=False`) | Yes | ✓ FLOWING |
| `MeResponse.identity_provider` | `identity.identity.provider` | Barrier-resolved `core.external_identities` row | Yes | ✓ FLOWING |
| `MeResponse.purchase_tokens` | `purchases.read_tokens(...)` | Real `SELECT` over `core.store_purchase_tokens` | Yes | ✓ FLOWING |

### Behavioral Spot-Checks / Full Runs

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full workspace suite (unit + e2e + schema) | `uv run pytest -q -m ""` | 1129 passed, 0 failed | ✓ PASS |
| Default (quick) suite | `uv run pytest -q` | 806 passed, 323 deselected | ✓ PASS |
| Lint | `uv run ruff check` | All checks passed | ✓ PASS |
| e2e proof file | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | 12 passed | ✓ PASS |
| New unit proof files | `uv run pytest -q tests/unit/test_purchases_crud.py tests/unit/test_users_me.py -v` | 33 passed | ✓ PASS |
| Wiring ratchet | `grep` + `pytest tests/unit/test_app_wiring.py` | both `/users/me` parametrised cases present and passing | ✓ PASS |
| Redaction ratchet | `grep` + `pytest tests/unit/test_error_contract.py` | fourth `missing_purchase_token` case present and passing | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| PROF-01 | 39-01, 39-02, 39-03, 39-04 | Profile fields, stored `identity_provider`, per-store tokens, unconditionally, no client-signal branching | ✓ SATISFIED | Truths 1, 2, 4, 5, 6, 8, 9 above; checkbox in REQUIREMENTS.md left `[ ]` (deliberate per 39-02 prohibition "no requirement checkbox is ticked by this plan"; phase-level ticking is an orchestrator/phase-completion step, not blocked by anything found here) |
| PROF-02 | 39-01, 39-04 | Off the audited attempt path, writes no `audit.auth_events` row ever | ✓ SATISFIED | Truth 3 (trivially true per Phase 37.1) and truth 11 (writes-nothing e2e proof) above; checkbox likewise left `[ ]` |

No orphaned requirements: `.planning/REQUIREMENTS.md` maps only PROF-01/PROF-02 to Phase 39, and both are claimed by all four plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `tests/unit/test_purchases_crud.py` / `tests/unit/test_users_me.py` | stub `.exec()` methods | No test asserts the token-read statement filters on `user_id`; both stubs return the seeded token map regardless of the compiled `WHERE` clause; no e2e case seeds a second user's tokens and asserts isolation | ⚠️ WARNING | Deleting `.where(col(StorePurchaseToken.user_id) == user_id)` from `crud/purchases.py:19` leaves all 806 quick-suite tests (and the full 1129) green. This is a real regression-guard gap on the single most security-relevant property of the route (cross-tenant token disclosure), independently confirmed by re-reading `test_purchases_crud.py` and `test_users_me.py` and by the already-committed `39-REVIEW.md` (WR-03, `issues_found`, 0 Critical / 7 Warning / 6 Info). It does **not** map to any roadmap success criterion or any plan `must_haves` truth/prohibition, so it does not block this verification, but it is a genuine gap the phase leaves open. **Recommendation:** land WR-03's suggested fix (a statement-filter assertion plus a `_FilteringSession`/second-seeded-user e2e case) as a fast-follow, ideally before Phase 40 reuses the same read pattern. |
| — | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any file this phase modified | ℹ️ INFO | Debt-marker gate: clean |

No 🛑 Blocker anti-patterns found.

### Human Verification Required

None. All must-haves were verifiable programmatically (grep, direct file reads, and live test runs), including the two items the plan 39-02 SUMMARY flagged `human_judgment: true` (the AGENTS.md prose reading against D-05's wording, and coverage item D4's permanent tests) — both were confirmed directly rather than deferred.

### Gaps Summary

No gaps block the phase goal. All four roadmap success criteria and all 13 merged must-haves across the four plans are verified against the live codebase and a live full-suite run (1129 passed, `ruff check` clean). The one open item — WR-03's missing cross-tenant regression guard on `PurchasesDB.read_tokens` — is a real, independently-confirmed test-coverage gap on a security-relevant invariant, but it is out of scope for every declared must-have and roadmap success criterion for this phase, so it is recorded as a WARNING rather than a blocking gap. It is already tracked in the phase's own code review (`39-REVIEW.md`, WR-03) and is recommended as a fast-follow before Phase 40 reuses the same read-and-filter pattern.

`PROF-01`/`PROF-02` checkboxes in `.planning/REQUIREMENTS.md` remain unticked — this was a deliberate, plan-enforced choice (39-02's prohibition: "No requirement checkbox is ticked by this plan — the phase is not complete at this point"), left for the orchestrator to close out at phase completion.

---

_Verified: 2026-09-02T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
