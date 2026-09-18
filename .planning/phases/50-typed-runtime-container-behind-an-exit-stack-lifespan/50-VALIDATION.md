---
phase: "50"
slug: "typed-runtime-container-behind-an-exit-stack-lifespan"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-17"
---

# Phase 50 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest with `pytest-asyncio` in auto mode |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest -q` |
| **Full suite command** | `.venv/bin/pytest -q -m ''` |
| **Estimated runtime** | ~60 seconds quick, ~180 seconds full |

A bare run is unit-only. The schema and e2e suites use a live localhost PostgreSQL and need
`-m schema`, `-m e2e` or `-m ''`.

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -q` and `.venv/bin/ruff check src tests`
- **After every plan wave:** Run `.venv/bin/pytest -q -m ''`
- **Before `/gsd:verify-work`:** `-m ''`, `-m e2e` and `-m schema` exit 0, `ruff` prints `All checks passed!`, `ty check` is re-read against the 295 baseline
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

The planner fills this map from the PLAN.md tasks. The criteria below are the acceptance surface; no requirement ID maps to this phase.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 50-01-01 | 50-01 | 1 | Criterion 7 (inherited red case) | T-50-01-02 | The restore refusal keeps its 403 body | e2e | `.venv/bin/pytest -q -m e2e tests/e2e/test_restore_subscription.py` | ✅ | ⬜ pending |
| 50-01-02 | 50-01 | 1 | Criterion 8 (D-09, D-10) | T-50-01-01 | One Play class, each entry point refusing with `Unavailable` when its value is `None` | unit + e2e | `.venv/bin/pytest -q tests/unit/test_google_play_notifications.py tests/unit/test_auth_package_shape.py` | ✅ | ⬜ pending |
| 50-02-01 | 50-02 | 2 | Criterion 8 (D-08) | T-50-02-01 | A transient JWKS or ADC failure stops boot; `None` only for absent settings | unit | `.venv/bin/pytest -q tests/unit/test_config.py tests/unit/test_google_play_notifications.py` | ✅ | ⬜ pending |
| 50-02-02 | 50-02 | 2 | Criterion 8 (D-08, D-07) | T-50-02-02, T-50-02-04 | An unreadable root certificate stops boot; the message names no secret | unit | `.venv/bin/pytest -q tests/unit/test_config.py tests/unit/test_firebase_adapter.py tests/unit/test_auth_package_shape.py` | ✅ | ⬜ pending |
| 50-03-01 | 50-03 | 3 | Criteria 4, 5 (D-01 to D-04) | T-50-03-01 | The container is never logged | unit + e2e | `.venv/bin/pytest -q` | ✅ | ⬜ pending |
| 50-03-02 | 50-03 | 3 | Criterion 4 (test factory) | — | N/A | unit | `.venv/bin/pytest -q` | ✅ | ⬜ pending |
| 50-03-03 | 50-03 | 3 | Criterion 4 | T-50-03-02 | Frozen and slotted: a handler cannot rebind a boot-built field | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ W0 → created here | ⬜ pending |
| 50-04-01 | 50-04 | 4 | Criteria 5, 6 (D-01, D-04) | T-50-04-01, T-50-04-02 | The identity barrier and the session open are unchanged in behaviour | all | `.venv/bin/pytest -q` + `-m e2e` + `-m schema` | ✅ | ⬜ pending |
| 50-04-02 | 50-04 | 4 | Type baseline (D-04) | — | N/A | type report | `.venv/bin/ty check` | ✅ | ⬜ pending |
| 50-05-01 | 50-05 | 5 | Criterion 5 (D-05) | T-50-05-01, T-50-05-02 | `sign_out_all` keeps both barrier dependencies and the request-verified pair | unit + e2e | `.venv/bin/pytest -q` | ✅ | ⬜ pending |
| 50-05-02 | 50-05 | 5 | Criterion 5 (route clause) | T-50-05-03 | No other route declares `get_runtime` | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ W0 → created here | ⬜ pending |
| 50-06-01 | 50-06 | 6 | Criteria 5, 6 (D-01, D-02, D-09) | T-50-06-01, T-50-06-02 | Both webhook verifiers still resolve before `get_db` | unit + e2e | `.venv/bin/pytest -q` | ✅ | ⬜ pending |
| 50-06-02 | 50-06 | 6 | Criterion 5 (counting clause) | T-50-06-03 | Exactly one `request.app.state` read, in `get_runtime` | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ W0 → created here | ⬜ pending |
| 50-06-03 | 50-06 | 6 | Criterion 6 | — | N/A | unit | `.venv/bin/pytest -q -m ''` | ❌ W0 → created here | ⬜ pending |
| 50-07-01 | 50-07 | 7 | Criteria 1, 2, 3 (D-06) | T-50-07-02, T-50-07-03, T-50-07-04 | `dispose` before the probe; the started line names three scalars; boot-fatal builders first | unit + all | `.venv/bin/pytest -q -m ''` | ✅ | ⬜ pending |
| 50-07-02 | 50-07 | 7 | Criteria 1, 2, 3 | T-50-07-01 | A raising teardown does not stop the remaining callbacks and propagates | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ W0 → created here | ⬜ pending |
| 50-07-03 | 50-07 | 7 | Criterion 7 (phase gate) | T-50-07-SC | No package installed; `uv.lock` untouched | all | `.venv/bin/pytest -q -m ''` + `-m e2e` + `-m schema` + `ruff` + `ty` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Each gap below is assigned to the task that closes it. There is no separate wave 0: every missing
case is created by the plan that makes its subject exist, which is what keeps the case honest.

- [ ] `tests/e2e/test_restore_subscription.py` — the restore case that fails at HEAD since commit `275bd8e` (expects log event `proof_rejected`, the code emits `purchase_proof_rejected`) → **task 50-01-01**
- [ ] `tests/unit/test_app_wiring.py` — a case that pins the exit-stack shape (criteria 1 and 3) → **task 50-07-02**
- [ ] `tests/unit/test_app_wiring.py` — a case that pins `Runtime` as frozen and slotted with eight fields (criterion 4) → **task 50-03-03**
- [ ] `tests/unit/test_app_wiring.py` — a case that pins one `app.state` read in `dependencies.py` (→ **task 50-06-02**) and the route clause of criterion 5 (→ **task 50-05-02**)
- [ ] `tests/unit/test_app_wiring.py` — a case that pins criterion 6, with an `opened_sessions` control → **task 50-06-03**
- [ ] A `Runtime` factory for unit tests that fills the fields a case does not name → **task 50-03-02**

**Spec-less probe fallback: skipped, recorded.** This phase has no requirement IDs to probe and no
SPEC file, so no probe predicates were generated in this planning run. The eight ROADMAP success
criteria are the acceptance surface.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
