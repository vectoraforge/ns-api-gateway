---
phase: 22
slug: apple-subscription-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0 with pytest-asyncio >=1.3 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `python3 -m pytest tests/unit/ -x` |
| **Full suite command** | `python3 -m pytest -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/unit/ -x`
- **After every plan wave:** Run `python3 -m pytest -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | SUBS-01 | unit | `python3 -m pytest tests/unit/test_webhooks.py::TestAppleWebhook::test_receives_notification -x` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | SUBS-02 | unit | `python3 -m pytest tests/unit/test_webhooks.py::TestAppleWebhook::test_invalid_jws_rejected -x` | ❌ W0 | ⬜ pending |
| 22-02-01 | 02 | 1 | SUBS-03 | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestSubscriptionLifecycle -x` | ❌ W0 | ⬜ pending |
| 22-02-02 | 02 | 1 | SUBS-04 | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestIdempotency -x` | ❌ W0 | ⬜ pending |
| 22-02-03 | 02 | 1 | SUBS-05 | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestPlanTierUpdate -x` | ❌ W0 | ⬜ pending |
| 22-03-01 | 03 | 2 | SUBS-06 | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestFirebaseSync -x` | ❌ W0 | ⬜ pending |
| 22-03-02 | 03 | 2 | SUBS-07 | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestFirebaseSync::test_uses_to_thread -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_webhooks.py` — stubs for SUBS-01, SUBS-02
- [ ] `tests/unit/test_subscriptions.py` — stubs for SUBS-03, SUBS-04, SUBS-05, SUBS-06, SUBS-07
- [ ] Unit test fixtures for mocking `SignedDataVerifier` and `FirebaseService`
- [ ] Framework install: `uv add app-store-server-library firebase-admin` — new dependencies required

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Apple sandbox webhook delivery | SUBS-01 | Requires Apple sandbox environment | Configure sandbox URL in App Store Connect, trigger test notification |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending