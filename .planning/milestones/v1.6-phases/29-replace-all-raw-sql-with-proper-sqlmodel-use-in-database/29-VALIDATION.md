---
phase: 29
slug: replace-all-raw-sql-with-proper-sqlmodel-use-in-database
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.3+ |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python3 -m pytest tests/unit/test_usage.py -x` |
| **Full suite command** | `python3 -m pytest tests/unit/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/unit/test_usage.py -x`
- **After every plan wave:** Run `python3 -m pytest tests/unit/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 29-01-01 | 01 | 1 | ORM rewrite | unit (mock) | `python3 -m pytest tests/unit/test_usage.py -x` | ✅ | ⬜ pending |
| 29-01-02 | 01 | 1 | Import smoke | smoke | `python3 -c "from nativespeaker.api.database.usage import UsageDB"` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. The rewrite is behavior-preserving and all service-level tests remain valid. No new test files are needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ORM constructs match original SQL semantics | Correctness | No DB-level integration tests for usage.py | Code review: compare old text() SQL with new ORM constructs, verify same WHERE clauses, same RETURNING, same ON CONFLICT |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
