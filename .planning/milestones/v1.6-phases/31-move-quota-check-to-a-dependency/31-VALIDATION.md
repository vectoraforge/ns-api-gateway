---
phase: 31
slug: move-quota-check-to-a-dependency
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0 with pytest-asyncio >= 1.3 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `pytest tests/unit/ -x -q` |
| **Full suite command** | `pytest tests/unit/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit/ -x -q`
- **After every plan wave:** Run `pytest tests/unit/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 31-01-01 | 01 | 1 | DEP-01 | unit | `pytest tests/unit/test_usage.py -x -k "quota_exceeded"` | Partially (needs rewrite) | ⬜ pending |
| 31-01-02 | 01 | 1 | DEP-02 | unit | `pytest tests/unit/test_usage.py -x -k "under_quota"` | Partially (needs rewrite) | ⬜ pending |
| 31-01-03 | 01 | 1 | DEP-03 | unit | `pytest tests/unit/test_usage.py -x -k "create_chat_quota"` | Needs rewrite | ⬜ pending |
| 31-01-04 | 01 | 1 | DEP-04 | unit | `pytest tests/unit/test_usage.py -x -k "send_message_quota"` | Needs rewrite | ⬜ pending |
| 31-01-05 | 01 | 1 | DEP-05 | unit | `pytest tests/unit/test_services.py -x` | Needs update | ⬜ pending |
| 31-01-06 | 01 | 1 | DEP-06 | unit | `pytest tests/unit/test_subscriptions.py -x` | Exists (should pass unchanged) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_usage.py` — rewrite quota enforcement tests to target dependency instead of ChatService
- [ ] `tests/unit/conftest.py` — update `service` fixture to remove `mock_usage_db`, update `client` to override `require_quota`

*Existing infrastructure covers framework and config — only test rewrites needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
