---
phase: 38
slug: post-auth-sync
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: false
wave_0_complete: true
created: 2026-09-01
reconstructed_from: [38-01..38-06 PLAN/SUMMARY, 38-VERIFICATION.md, 38-UAT.md]
---

# Phase 38 — Validation Strategy

> Reconstructed retroactively from phase artifacts (State B). Every behavioral must-have truth
> in plans 38-01…38-06 is mapped to an executable command below. `nyquist_compliant: false`
> reflects three *document-state* obligations only — see Manual-Only Verifications. No behavior
> of the shipped endpoint is manual.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` → `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/test_sync_resolver.py tests/unit/test_sync_audit_removal.py tests/unit/test_sync_clock_capture.py tests/unit/test_sync_error_reuse.py tests/unit/test_app_wiring.py -q` |
| **Full suite command** | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` |
| **Estimated runtime** | ~28s default suite · ~1s sync e2e · ~2s sync schema |

> **Marker gotcha:** `addopts = "-v --tb=short -m 'not e2e and not schema'"`. A bare `uv run pytest`
> silently deselects both real-PostgreSQL tiers (311 deselected). The concurrency proof for this
> phase lives in the `schema` tier and **will not run** unless `-m schema` is passed explicitly.

---

## Sampling Rate

- **After every task commit:** Run the quick run command (~1s)
- **After every plan wave:** Run `uv run pytest -q` (~28s)
- **Before `/gsd:verify-work`:** All three tiers green + `uv run ruff check src tests`
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 38-01-T1 | 01 | 1 | SYNC-01 | — | Response body key set is exactly `{entitlement, identity_provider}`; a seventh field fails | e2e | `uv run pytest -m e2e tests/e2e/test_sync.py::TestTheEntitlementHappyPath -q` | ✅ | ✅ green |
| 38-01-T2 | 01 | 1 | SYNC-01 | — | `current_period` derives from the one captured instant; nothing below the dependency reads the clock | unit | `uv run pytest tests/unit/test_sync_clock_capture.py tests/unit/test_sync_resolver.py::TestTheZeroGrantAnswer -q` | ✅ | ✅ green |
| 38-01-T3 | 01 | 1 | SYNC-01 | — | `identity_provider` read from the stored column, never rederived from a token claim or header | e2e | `uv run pytest -m e2e tests/e2e/test_sync.py::TestTheProviderComesFromTheStoredColumn -q` | ✅ | ✅ green |
| 38-01-T4 | 01 | 1 | SYNC-01 | — | Inclusive lower / exclusive upper grant bound, asserted on compiled PostgreSQL | unit | `uv run pytest tests/unit/test_sync_resolver.py::TestThePredicateBoundaries -q` | ✅ | ✅ green |
| 38-01-T5 | 01 | 1 | SYNC-01 | — | `ORDER BY id ASC`, no `LIMIT` — a second effective grant stays visible to fail closed on | unit | `uv run pytest "tests/unit/test_sync_resolver.py::TestThePredicateBoundaries::test_it_orders_by_the_grant_id_ascending_and_takes_no_row_limit" -q` | ✅ | ✅ green |
| 38-01-T6 | 01 | 1 | SYNC-02 | — | Locking and non-locking reads compile to identical SQL apart from trailing `FOR UPDATE` | unit | `uv run pytest tests/unit/test_sync_resolver.py::TestThePredicateIsOneDefinition -q` | ✅ | ✅ green |
| 38-01-T7 | 01 | 1 | SYNC-01 | — | `/auth/sync` declares `get_linked_identity`; in neither `PUBLIC_PATHS` nor `PREAUTH_CALLABLE_PATHS` | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ | ✅ green |
| 38-02-T1 | 02 | 2 | SYNC-01 | — | Zero effective grants → all six no-grant fields, no error, no row created | unit | `uv run pytest tests/unit/test_sync_resolver.py::TestTheZeroGrantAnswer -q` | ✅ | ✅ green |
| 38-02-T2 | 02 | 2 | SYNC-02 | — | Stale-period usage row reports 0 without being written; session never committed | unit | `uv run pytest tests/unit/test_sync_resolver.py::TestTheRolloverIsComputedNeverWritten -q` | ✅ | ✅ green |
| 38-02-T3 | 02 | 2 | SYNC-01 | — | Missing usage row raises rather than reporting an allowance quota would refuse | unit | `uv run pytest tests/unit/test_sync_resolver.py::TestTheUsageRowIsMissing -q` | ✅ | ✅ green |
| 38-02-T4 | 02 | 2 | SYNC-01 | — | Two effective grants / unknown tier both fail closed to 500 with no detail on the wire | unit | `uv run pytest tests/unit/test_sync_resolver.py::TestMultipleEffectiveGrants tests/unit/test_sync_resolver.py::TestTheTierHasNoRow -q` | ✅ | ✅ green |
| 38-02-T5 | 02 | 2 | SYNC-02 | — | The three tripwires reuse quota's existing classes; **no new error class added** | unit | `uv run pytest tests/unit/test_sync_error_reuse.py -q` | ✅ | ✅ green |
| 38-03-T1 | 03 | 3 | SYNC-01 | — | Zero grants and a lapsed grant return byte-identical bodies, compared to each other | e2e | `uv run pytest -m e2e tests/e2e/test_sync.py::TestTwoAbsentEntitlementsAreIndistinguishable -q` | ✅ | ✅ green |
| 38-03-T2 | 03 | 3 | SYNC-02 | — | Raw `SELECT *` snapshots of the three `core.*` tables identical before and after | e2e | `uv run pytest -m e2e tests/e2e/test_sync.py::TestTheRequestChangesNothing -q` | ✅ | ✅ green |
| 38-03-T3 | 03 | 3 | SYNC-02 | — | Under genuine two-connection concurrency, sync neither blocks nor is blocked by a live charge | schema | `uv run pytest -m schema tests/schema/test_sync_lock_freedom.py -q` | ✅ | ✅ green |
| 38-03-T4 | 03 | 3 | SYNC-01 | — | Unauthenticated → 401 `auth_required`; verified-but-unlinked → 403 `preauth_identity_not_allowed` | e2e | `uv run pytest -m e2e tests/e2e/test_sync.py::TestTheRouteInheritsTheBarriersRejections -q` | ✅ | ✅ green |
| 38-03-T5 | 03 | 3 | SYNC-01 | — | Fail-closed path answers exactly `{"code": "internal_error"}` end to end | e2e | `uv run pytest -m e2e tests/e2e/test_sync.py::TestTheFailClosedFiveHundred -q` | ✅ | ✅ green |
| 38-04-T1 | 04 | 1 | SYNC-03 | — | `SHARED-INVARIANTS.md` carries no audit-row obligation; non-audit substance survives | — | **manual** — see Manual-Only | n/a | 🖐 manual |
| 38-05-T1 | 05 | 2 | SYNC-03 | — | `REQUIREMENTS.md`/`ROADMAP.md` record the decision; conflict count drops six → five | — | **manual** — see Manual-Only | n/a | 🖐 manual |
| 38-06-T1 | 06 | 4 | SYNC-03 | — | Migration unmodified; audit-table expectation still the one-member set | unit | `uv run pytest tests/unit/test_sync_audit_removal.py -q` | ✅ | ✅ green |
| 38-06-T2 | 06 | 4 | SYNC-03 | — | `services/sync.py` imports no logging library and makes no logging call (AST walk) | unit | `uv run pytest "tests/unit/test_sync_audit_removal.py::TestTheSyncServiceEmitsNoEventOfItsOwn" -q` | ✅ | ✅ green |
| 38-06-T3 | 06 | 4 | SYNC-03 | — | No new log-event name or deleted-table string anywhere under `src/`; walk proven non-vacuous | unit | `uv run pytest "tests/unit/test_sync_audit_removal.py::TestNoPerAttemptSyncEventNameWasAdded" "tests/unit/test_sync_audit_removal.py::TestTheSourceWalkIsNotVacuous" -q` | ✅ | ✅ green |
| 38-06-T4 | 06 | 4 | SYNC-03 | — | One `request` line per attempt with its own request id (backstop: shared middleware, not sync) | unit | `uv run pytest tests/unit/test_logging.py -q` | ✅ | ✅ green |
| 38-06-T5 | 06 | 4 | SYNC-01/02/03 | — | All three tiers green and ruff clean at phase close | full | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q && uv run ruff check src tests` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · 🖐 manual*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No framework install or fixture scaffolding
was needed — `tests/unit`, `tests/e2e` (real PostgreSQL, rolled-back transaction) and `tests/schema`
(committed scratch database, independent connections) were all already in place.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `SHARED-INVARIANTS.md` contains no clause requiring an `audit.auth_events` row, an audited attempt path, route→operation metadata readable before the barrier, an `actor_subject_hash`, or a details shape — while the two mixed clauses' non-audit substance survives | SYNC-03 | The file lives at `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — **outside this repository**, deliberately untracked per 38-04-PLAN.md's `<repository_boundary>`. A test in this repo asserting on it would either fail in CI or encode a path that does not exist for any other checkout. | `grep -ic audit /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` → expect `0`. Then confirm both survivors are present under `## Fail-closed defaults`: a rejection leaves exactly one structured security-log line, and admission-phase rejections write no per-rejection database row. |
| `REQUIREMENTS.md` SYNC-03 records the decision (names option (b), dated 2026-09-01); the three siblings APPLEHOOK-02 / PLAYHOOK-03 / SIGNOUT-02 each carry a dated note; the flagged-conflict count reads five; FOUND-05 is marked resolved by removal rather than deleted | SYNC-03 | Planning-document state, not product behavior. Asserting on `.planning/` prose from the test suite would couple the suite to editorial wording and break on every legitimate reword. | `grep -n "Amended again by Phase 38" .planning/REQUIREMENTS.md`; check `.planning/REQUIREMENTS.md:198-200` all `- [x]`; check the conflict count reads **Five** at `:34` and `:489`; check FOUND-05's "RESOLVED BY REMOVAL" paragraph at `:120-124`. |
| No phase brief under `specs/auth-refactor-phases/` was edited, and no migration file was touched | SYNC-03 | Half the claim spans the parent repository (see above). The in-repo half **is** automated — `tests/unit/test_sync_audit_removal.py` pins the single-migration and no-auth-event-name guards. | `git -C /home/init/native-speaker status --short specs/` → the directory is untracked as a whole; confirm no brief was modified. In-repo half needs no manual step. |

> **Not manual, despite `38-VERIFICATION.md` routing to `human_needed`:** the no-lock-under-genuine-
> concurrency claim (WINDOWS.md entry 9) was closed during UAT by `tests/schema/test_sync_lock_freedom.py`
> — three cases on two real independent connections, with `SET LOCAL lock_timeout` as the instrument
> and a recorded mutation control. It is row 38-03-T3 above, automated.

---

## Validation Audit 2026-09-01

| Metric | Count |
|--------|-------|
| Behavioral truths mapped | 23 |
| Gaps found | 2 |
| Resolved | 2 |
| Escalated | 0 |
| Manual-only (document-state) | 3 |

**Gaps closed this pass**

1. **38-01-T2 (PARTIAL → COVERED)** — the "nothing below the dependency reads the clock again" claim
   had no structural guard; only the injected-instant equality in `test_sync_resolver.py` stood behind it.
   Added `tests/unit/test_sync_clock_capture.py` (4 cases): an AST walk proving `services/sync.py` makes
   no `datetime.now`/`utcnow`/`date.today`/`time.time` call and uses its `datetime` import only as a type
   annotation; a walk proving `get_sync_service` calls the clock exactly once; and a non-vacuity control.
2. **38-02-T5 (MISSING → COVERED)** — "no new error class is added to `errors.py`" was shown only by
   import, so a fourth class would have failed nothing. Added `tests/unit/test_sync_error_reuse.py`
   (2 cases): the AST-derived set of classes `sync.py` raises equals exactly the three D-07 names, and
   every class sync raises is also raised by `quota.py`. Narrowed deliberately — `test_error_registry.py`
   already pins the error tree's totality.

**Fault injection (both guards proven non-vacuous; `src/` reverted clean, `git diff src/` empty)**

| Injection | Observed failure |
|---|---|
| `datetime.now()` added in `sync.py::read_entitlement` | `test_sync_service_makes_no_clock_call_on_any_path` + `test_the_datetime_import_is_used_only_as_a_type_annotation` fail *(independently re-run by the orchestrator, not taken from the auditor's report)* |
| Second `datetime.now(UTC)` added in `get_sync_service` | `test_get_sync_service_calls_the_clock_exactly_once` fails `assert 2 == 1` |
| Dead `raise ValueError(...)` added in `sync.py` | `test_sync_service_raises_exactly_three_named_classes` + `test_every_class_sync_raises_is_also_raised_by_quota` fail |

**Suite state at sign-off:** `uv run pytest -q` → **767 passed**, 311 deselected (761 baseline + 6 new).
`-m e2e tests/e2e/test_sync.py` → 14 passed. `-m schema tests/schema/test_sync_lock_freedom.py` → 3 passed.
`uv run ruff check src tests` → All checks passed.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or a recorded manual-only justification
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none needed — infrastructure pre-existed)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [ ] `nyquist_compliant: true` — **not set.** Three document-state obligations remain manual, two of
      them spanning a second, deliberately untracked repository. Every *behavioral* requirement of
      SYNC-01, SYNC-02 and SYNC-03 is automated.

**Approval:** approved 2026-09-01
