---
phase: 34
slug: schema
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-19
---

# Phase 34 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (lines 51-60) |
| **Quick run command** | `pytest tests/schema -m schema -x -q` |
| **Full suite command** | `pytest tests/schema -m schema && pytest tests/unit` |
| **Estimated runtime** | ~5 seconds (one-time scratch-DB apply, then sub-second per test) |

**New marker required:** `schema: schema-conformance tests requiring a real PostgreSQL` must be added to
`[tool.pytest.ini_options] markers`. **Do not** reuse `e2e` — the default
`addopts = "-v --tb=short -m 'not e2e'"` would deselect this phase's only proof.

**Resolved by plan 34-03 task 2 (orchestrator DIRECTIVE-2):** the marker is registered and `addopts`
is now `-v --tb=short -m 'not e2e and not schema'`, so a bare `pytest` stays green on a machine with
no PostgreSQL. The consequence is that **every command below must select the marker explicitly with
`-m schema`** — a bare `pytest tests/schema` now collects nothing. All commands in this file were
updated accordingly.

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/schema -m schema -x -q`
- **After every plan wave:** Run `pytest tests/schema -m schema && pytest tests/unit`
- **Before `/gsd:verify-work`:** Full suite must be green, plus a manual `pogo apply` against a genuinely
  empty PostgreSQL 17 (satisfies success criterion 1 outside the fixture)
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 0 | SCHEMA-01 | — | N/A | integration | `pytest tests/schema/test_apply_rollback.py -m schema -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCHEMA-02 | — | `(issuer,subject)` uniqueness prevents identity collision across providers | unit (DDL) | `pytest tests/schema/test_constraints.py -m schema -k identity -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCHEMA-03 | — | At most one `status='active'` grant per user — blocks entitlement stacking | unit (DDL) | `pytest tests/schema/test_constraints.py -m schema -k grant -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCHEMA-04 | — | Generated column rejects direct writes — entitlement cannot be forged | unit (DDL) | `pytest tests/schema/test_constraints.py -m schema -k subscription -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCHEMA-05 | — | Challenge claim/consume CHECKs reject replay-shaped rows | unit (DDL) | `pytest tests/schema/test_constraints.py -m schema -k challenge -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCHEMA-06 | — | Partial actor fields rejected — audit rows cannot be written unattributable | unit (DDL) | `pytest tests/schema/test_constraints.py -m schema -k audit -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCHEMA-07 | — | Legacy `jwt_sub` / `subscription_plan` / `promo` paths are absent, not merely unused | unit (introspection) | `pytest tests/schema/test_inventory.py -m schema -k legacy -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCHEMA-08 | — | N/A | unit (introspection) | `pytest tests/schema/test_inventory.py -m schema -x` | ❌ W0 | ⬜ pending |

*Task IDs are filled in by the planner; rows above are the requirement-level coverage contract.*

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] A reachable PostgreSQL 17 instance — **gates every other task in this phase**
- [ ] `tests/schema/__init__.py`
- [ ] `tests/schema/conftest.py` — scratch DB + `pogo_core.util.testing.apply` + per-test rollback
- [ ] `tests/schema/helpers.py` — `insert_user()`, `insert_tier()`, `insert_grant()` per D-15
- [ ] `tests/schema/test_inventory.py` — covers SCHEMA-07, SCHEMA-08
- [ ] `tests/schema/test_constraints.py` — covers SCHEMA-02 … SCHEMA-06
- [ ] `tests/schema/test_apply_rollback.py` — covers SCHEMA-01, D-20
- [ ] `pyproject.toml` — add the `schema` marker to `[tool.pytest.ini_options] markers`
- [ ] Framework install: none needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fresh `pogo apply` against a genuinely empty PostgreSQL 17 | SCHEMA-01 | Success criterion 1 must hold outside the pytest fixture, on the real target version (research verified on PG 16.2 only) | Create an empty database on PG 17, run `pogo apply`, confirm exit 0 and that `migrations/` holds exactly one `.sql` file |
| Re-capture inventory constants from the first real PG 17 apply | SCHEMA-08 | Index names and `pg_get_expr` predicate text are version- and `search_path`-sensitive | After the PG 17 apply, re-read the 54-index set and 7 predicate strings; reconcile against the constants in RESEARCH.md |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
