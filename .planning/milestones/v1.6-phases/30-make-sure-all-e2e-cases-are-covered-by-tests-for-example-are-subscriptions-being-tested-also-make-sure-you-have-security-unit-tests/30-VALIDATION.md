---
phase: 30
slug: make-sure-all-e2e-cases-are-covered-by-tests-for-example-are-subscriptions-being-tested-also-make-sure-you-have-security-unit-tests
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-asyncio |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/ -x --tb=short -q` |
| **Full suite command** | `python -m pytest tests/ -v --tb=long` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x --tb=short -q`
- **After every plan wave:** Run `python -m pytest tests/ -v --tb=long`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 30-01-01 | 01 | 1 | Fix broken imports | unit | `python -m pytest tests/unit/test_models.py tests/unit/test_services.py -v` | ✅ | ⬜ pending |
| 30-01-02 | 01 | 1 | E2E subscriptions | e2e | `python -m pytest tests/e2e/test_subscriptions.py -v` | ❌ W0 | ⬜ pending |
| 30-01-03 | 01 | 1 | E2E users/me | e2e | `python -m pytest tests/e2e/test_users.py -v` | ❌ W0 | ⬜ pending |
| 30-01-04 | 01 | 1 | E2E webhooks | e2e | `python -m pytest tests/e2e/test_webhooks.py -v` | ❌ W0 | ⬜ pending |
| 30-01-05 | 01 | 1 | E2E error paths | e2e | `python -m pytest tests/e2e/ -k "error or 404 or 401" -v` | ❌ W0 | ⬜ pending |
| 30-01-06 | 01 | 1 | Security unit tests | unit | `python -m pytest tests/unit/test_security.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/e2e/test_subscriptions.py` — e2e subscription endpoint tests
- [ ] `tests/e2e/test_users.py` — e2e user profile endpoint tests
- [ ] `tests/e2e/test_webhooks.py` — e2e webhook endpoint tests
- [ ] `tests/unit/test_security.py` — security-focused unit tests for auth edge cases

*Existing infrastructure (pytest, httpx AsyncClient, conftest fixtures) covers framework needs.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
