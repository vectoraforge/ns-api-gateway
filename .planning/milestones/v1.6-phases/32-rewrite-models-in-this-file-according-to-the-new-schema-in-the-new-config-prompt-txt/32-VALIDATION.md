---
phase: 32
slug: rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 32-01-01 | 01 | 1 | D-08/D-10 | unit | `python -m pytest tests/unit/test_exception_handlers.py -x -q` | ✅ | ⬜ pending |
| 32-01-02 | 01 | 1 | D-14/D-15/D-16/D-17 | unit | `python -m pytest tests/unit/test_models.py -x -q` | ✅ | ⬜ pending |
| 32-02-01 | 02 | 1 | D-01/D-02/D-03/D-04/D-18/D-19 | unit | `python -m pytest tests/unit/test_services.py -x -q` | ✅ | ⬜ pending |
| 32-03-01 | 03 | 2 | D-05/D-06/D-07/D-11/D-12 | unit | `python -m pytest tests/unit/ -x -q` | ✅ | ⬜ pending |
| 32-03-02 | 03 | 2 | D-13 | e2e | `python -m pytest tests/e2e/ -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
