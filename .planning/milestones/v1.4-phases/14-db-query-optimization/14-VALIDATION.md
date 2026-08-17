---
phase: 14
slug: db-query-optimization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0+ with pytest-asyncio |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q -m 'not llm and not db'` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q -m 'not llm and not db'` + `ruff check`
- **Before `/gsd:verify-work`:** Full suite must be green + grep verification for all DEAD-* requirements
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | QOPT-01 | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite | ⬜ pending |
| 14-01-02 | 01 | 1 | QOPT-02 | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite | ⬜ pending |
| 14-01-03 | 01 | 1 | QOPT-03 | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite | ⬜ pending |
| 14-01-04 | 01 | 1 | QOPT-04 | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite | ⬜ pending |
| 14-01-05 | 01 | 1 | QOPT-05 | unit | `python -m pytest tests/unit/test_services.py -x -q` | Needs rewrite | ⬜ pending |
| 14-02-01 | 02 | 2 | DEAD-01 | grep | `grep -r 'get_chat_owned' app/ tests/` | Verification step | ⬜ pending |
| 14-02-02 | 02 | 2 | DEAD-02 | grep | `grep -r 'get_message_counts' app/ tests/` | Verification step | ⬜ pending |
| 14-02-03 | 02 | 2 | DEAD-03 | grep | `grep -r '_ensure_history_capacity' app/ tests/` | Verification step | ⬜ pending |
| 14-02-04 | 02 | 2 | DEAD-04 | grep | `grep -r 'ChatOwnershipError' app/ tests/` | Verification step | ⬜ pending |
| 14-02-05 | 02 | 2 | DEAD-05 | unit | `python -m pytest tests/ -x -q -m 'not llm and not db'` | Needs rewrite | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. Tests need rewriting (not new infrastructure).*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
