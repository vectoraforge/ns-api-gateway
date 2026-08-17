---
phase: 27
slug: migration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/unit -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Visual diff review of SQL against models.py
- **After every plan wave:** `pogo apply` against fresh PG instance (Docker)
- **Before `/gsd:verify-work`:** Full suite must be green + `pogo apply` succeeds
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 27-01-01 | 01 | 1 | SCHEMA-01 | manual-only | `pogo apply` against test PG instance | N/A | pending |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files needed — migration validation is via `pogo apply` against a live PostgreSQL instance.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration SQL creates correct schema with enum types | SCHEMA-01 | Raw SQL DDL cannot be validated by Python unit tests — requires live PostgreSQL | 1. Start fresh PG instance via Docker 2. Run `pogo apply` 3. Verify enum types exist: `SELECT typname FROM pg_type WHERE typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'core') AND typtype = 'e'` 4. Verify no plans table: `SELECT 1 FROM information_schema.tables WHERE table_schema = 'core' AND table_name = 'plans'` returns empty 5. Attempt inserting invalid enum value — PG rejects it |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
