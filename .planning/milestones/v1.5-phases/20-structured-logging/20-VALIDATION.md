---
phase: 20
slug: structured-logging
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0 with pytest-asyncio >= 1.3 |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/unit/ -x` |
| **Full suite command** | `python -m pytest tests/unit/ -x && python -m pytest tests/e2e/ -m e2e -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -x`
- **After every plan wave:** Run `python -m pytest tests/unit/ -x && python -m pytest tests/e2e/ -m e2e -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | LOG-01 | unit | `python -m pytest tests/unit/test_logging.py::test_json_output -x` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | LOG-02 | unit | `python -m pytest tests/unit/test_logging.py::test_console_output -x` | ❌ W0 | ⬜ pending |
| 20-01-03 | 01 | 1 | LOG-03 | unit | `python -m pytest tests/unit/test_logging.py::test_request_id_context -x` | ❌ W0 | ⬜ pending |
| 20-01-04 | 01 | 1 | LOG-04 | unit | `python -m pytest tests/unit/test_logging.py::test_log_levels -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_logging.py` — stubs for LOG-01 through LOG-04 using `structlog.testing.capture_logs()`
- [ ] `uv add "structlog>=25.5"` — structlog not yet in dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Console output readability | LOG-02 | Visual formatting quality | Run app, trigger request, inspect terminal output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
