---
phase: 28
slug: test-updates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (auto mode) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/unit/ -x --tb=short` |
| **Full suite command** | `python -m pytest tests/unit/ -v --tb=short` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -x --tb=short`
- **After every plan wave:** Run `python -m pytest tests/unit/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 28-01-01 | 01 | 1 | TEST-01 | code inspection | `grep -c "ensure_tables" tests/e2e/conftest.py` (expect 0) | ✅ | ⬜ pending |
| 28-01-02 | 01 | 1 | TEST-02 | unit | `python -m pytest tests/unit/test_subscriptions.py -x --tb=short` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| E2E tests run against pre-migrated DB | TEST-01 | Requires live PostgreSQL with migration applied | Apply migration, run `python -m pytest tests/e2e/ -v -m e2e --tb=short` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
