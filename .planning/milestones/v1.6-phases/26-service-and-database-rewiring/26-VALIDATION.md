---
phase: 26
slug: service-and-database-rewiring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0 with pytest-asyncio >=1.3 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `pytest tests/unit/ -x` |
| **Full suite command** | `pytest tests/unit/` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit/ -x`
- **After every plan wave:** Run `pytest tests/unit/`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 26-01-01 | 01 | 1 | QUOTA-03 | unit | `pytest tests/unit/test_usage.py -x` | Yes (Phase 28 updates) | ⬜ pending |
| 26-01-02 | 01 | 1 | QUOTA-04 | unit | `pytest tests/unit/test_users.py -x` | Yes (Phase 28 updates) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Test updates are Phase 28 scope (TEST-02). This phase's verification relies on success criteria checks against code.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `UsageDB.try_increment` SQL has no JOIN to `core.plans` | QUOTA-03 | Code inspection — SQL is in string literal | `grep -c "plans" src/nativespeaker/api/database/usage.py` should return 0 in try_increment |
| `UsageDB.get_monthly_limit` deleted | QUOTA-04 | Code inspection — method absence | `grep -c "get_monthly_limit" src/nativespeaker/api/database/usage.py` should return 0 |
| `ChatService` resolves quota from config | QUOTA-03 | Code inspection — quota resolution path | Verify `self.quotas[user.subscription_plan]` in `create_chat` and `send_message` |
| `/users/me` reads limit from config | QUOTA-04 | Code inspection — config lookup | Verify `config.quotas[user.subscription_plan]` in `get_me` handler |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
