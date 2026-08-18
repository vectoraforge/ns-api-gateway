---
phase: 21
slug: user-management
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -m 'not e2e' -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -m 'not e2e' -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | USER-01 | unit | `python -m pytest tests/unit/test_users.py::test_jit_provisioning -x` | ❌ W0 | ⬜ pending |
| 21-01-02 | 01 | 1 | USER-01 | unit | `python -m pytest tests/unit/test_users.py::test_user_identity_from_jwt -x` | ❌ W0 | ⬜ pending |
| 21-01-03 | 01 | 1 | USER-02 | unit | `python -m pytest tests/unit/test_users.py::test_get_users_me -x` | ❌ W0 | ⬜ pending |
| 21-01-04 | 01 | 1 | USER-02 | unit | `python -m pytest tests/unit/test_users.py::test_profile_no_internal_id -x` | ❌ W0 | ⬜ pending |
| 21-01-05 | 01 | 1 | USER-03 | unit | `python -m pytest tests/unit/test_users.py::test_concurrent_provisioning -x` | ❌ W0 | ⬜ pending |
| 21-01-06 | 01 | 1 | USER-04 | unit | `python -m pytest tests/unit/test_users.py::test_user_isolation -x` | ❌ W0 | ⬜ pending |
| 21-01-07 | 01 | 1 | USER-04 | unit | `python -m pytest tests/unit/test_users.py::test_inactive_user_rejected -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_users.py` — stubs for USER-01 through USER-04
- [ ] Update `tests/unit/conftest.py` — _FixedKeyVerifier returns UserIdentity, dependency override returns User model
- [ ] Update `tests/e2e/conftest.py` — create_chat helper uses UUID user_id with User FK

*Existing infrastructure covers framework install — pytest already configured.*

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
