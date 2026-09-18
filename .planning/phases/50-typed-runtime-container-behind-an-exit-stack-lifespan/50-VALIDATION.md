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
| 50-xx-xx | — | — | Criteria 1, 3 | — | N/A | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ W0 | ⬜ pending |
| 50-xx-xx | — | — | Criterion 2 | — | N/A | unit | `.venv/bin/pytest -q tests/unit/test_config.py` | ✅ | ⬜ pending |
| 50-xx-xx | — | — | Criterion 4 | — | N/A | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ W0 | ⬜ pending |
| 50-xx-xx | — | — | Criterion 5 | — | N/A | unit | `.venv/bin/pytest -q tests/unit/test_app_wiring.py` | ❌ W0 | ⬜ pending |
| 50-xx-xx | — | — | Criterion 6 | — | N/A | unit | `.venv/bin/pytest -q -m ''` | ❌ W0 | ⬜ pending |
| 50-xx-xx | — | — | Criterion 7 | — | N/A | all | `.venv/bin/pytest -q -m ''` | ✅ | ⬜ pending |
| 50-xx-xx | — | — | Criterion 8 (50 D-08, D-09) | — | A transient failure stops boot; `None` only for absent settings | unit | `.venv/bin/pytest -q tests/unit/test_google_play_notifications.py tests/unit/test_config.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/e2e/test_restore_subscription.py` — the restore case that fails at HEAD since commit `275bd8e` (expects log event `proof_rejected`, the code emits `purchase_proof_rejected`)
- [ ] `tests/unit/test_app_wiring.py` — a case that pins the exit-stack shape (criteria 1 and 3)
- [ ] `tests/unit/test_app_wiring.py` — a case that pins `Runtime` as frozen and slotted with eight fields (criterion 4)
- [ ] `tests/unit/test_app_wiring.py` — a case that pins one `app.state` read in `dependencies.py` and the route clause of criterion 5
- [ ] A `Runtime` factory for unit tests that fills the fields a case does not name

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
