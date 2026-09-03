---
phase: "42"
slug: "post-auth-claim-registered-grant"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-09-03"
---

# Phase 42 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0 + pytest-asyncio >=1.3, `asyncio_mode = "auto"` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q && uv run ruff check src tests` |
| **Estimated runtime** | ~35s for the unit suite, measured 2026-09-03 at 952 passed in 33.31s; the marked suites need a live PostgreSQL |

`addopts` is `-v --tb=short -m 'not e2e and not schema'`, so the default invocation is the unit suite
alone and every marked command must pass its marker explicitly. The `-m e2e` suite additionally needs
Firebase credentials in `.env`; the `-m schema` suite creates, migrates and drops its own
`ns_schema_test` database per session and needs only a reachable PostgreSQL 17.

---

## Sampling Rate

- **After every task commit:** `uv run pytest -q` and `uv run ruff check src tests`
- **After every plan wave:** the full suite command above. Wave 1 additionally requires `-m schema`
  and `-m e2e` green, because the migration edit is what those two suites measure; wave 2 requires
  both for the same reason.
- **Before `/gsd:verify-work`:** all three markers green with zero skipped
- **Max feedback latency:** ~35 seconds on the unit suite

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 42-01-01 | 01 | 1 | REGGRANT-03 | — | N/A — blocking decision gate on a one-way migration edit and a destructive local rebuild | checkpoint | none (human gate) | n/a | ⬜ pending |
| 42-01-02 | 01 | 1 | REGGRANT-03 | T-42-01-01 / T-42-01-02 / T-42-01-03 | The surviving unique indexes and the free-grant marker remain the account-level controls; no hash, key or key-version surface is introduced; the dev database is provably rebuilt | unit + live probe | `uv run pytest -q` · `uv run ruff check src tests` · the `pg_tables` core-table probe | ✅ | ⬜ pending |
| 42-01-03 | 01 | 1 | REGGRANT-03 | T-42-01-01 / T-42-01-05 | Every test reading a deleted object is updated or deleted with its disposition recorded; no control on the free-grant rules is weakened | schema + e2e + unit | `uv run pytest -m schema -q` · `uv run pytest -m e2e -q` · `uv run pytest -q` | ✅ | ⬜ pending |
| 42-02-01 | 02 | 2 | REGGRANT-01, REGGRANT-02, REGGRANT-03 | T-42-02-01 … T-42-02-06 | The stored provider is the only classifier and is re-checked under lock; the history-by-source read is the eligibility guard; one device token serves both Apple calls; the four refusals share one answer | e2e (tracer) | `uv run pytest -m e2e tests/e2e/test_claim_registered_grant.py -q` | ❌ W0 | ⬜ pending |
| 42-02-02 | 02 | 2 | REGGRANT-02 | T-42-02-03 / T-42-02-07 | Exactly two lock tiers and never a third; the conversion's expiry statement is emitted before its insert, captured from real SQL | schema | `uv run pytest -m schema tests/schema/test_grant_locks.py -q` | ✅ | ⬜ pending |
| 42-03-01 | 03 | 3 | REGGRANT-01, REGGRANT-03 | T-42-03-04 / T-42-03-05 | Every post-claim outcome spends the handle exactly once and no pre-claim rejection spends anything; a permissive stub cannot hide the detached-row defect | unit | `uv run pytest tests/unit/test_claim_precedence_registered.py -q` | ❌ W0 | ⬜ pending |
| 42-03-02 | 03 | 3 | REGGRANT-01, REGGRANT-03 | T-42-03-01 / T-42-03-02 / T-42-03-03 | The four refusals are byte-identical on the wire; no Apple failure arm leaves grant state touched; a revoked anonymous grant never reopens the slot | e2e | `uv run pytest -m e2e tests/e2e/test_claim_registered_grant.py -q` | ❌ W0 | ⬜ pending |
| 42-04-01 | 04 | 3 | REGGRANT-01 | T-42-04-01 / T-42-04-03 / T-42-04-04 | Exactly one construction site for a registered grant, inside the writer that takes both lock tiers, mutation-tested; the free-source set is not narrowed | unit (AST walk) | `uv run pytest tests/unit/test_grant_sources.py -q` | ✅ | ⬜ pending |
| 42-04-02 | 04 | 3 | REGGRANT-02 | T-42-04-02 / T-42-04-03 | Both Apple calls precede the writer on the arm that reaches them, the conversion arm reaches neither, and the crud module cannot import a network client | unit (AST order + subprocess) | `uv run pytest tests/unit/test_claim_ordering.py -q` | ✅ | ⬜ pending |
| 42-05-01 | 05 | 3 | REGGRANT-03 | T-42-05-01 / T-42-05-03 / T-42-05-05 | Two parallel claims allocate exactly one grant; the loser answers 200 doing nothing; both challenges are consumed | schema (2 connections) | `uv run pytest -m schema tests/schema/test_claim_race.py -q` | ✅ | ⬜ pending |
| 42-05-02 | 05 | 3 | REGGRANT-02 | T-42-05-02 / T-42-05-04 | Supersession under contention expires exactly once and leaves exactly one active grant with its counters carried once | schema (2 connections) | `uv run pytest -m schema tests/schema/test_claim_race.py -q` | ✅ | ⬜ pending |
| 42-06-01 | 06 | 4 | REGGRANT-01, REGGRANT-02, REGGRANT-03 | T-42-06-01 / T-42-06-04 | Divergences are recorded in the ledger and the specification is untouched | doc + CLI | `git -C /home/init/native-speaker/ns-api-gateway status --porcelain -- .planning/REQUIREMENTS.md` | ✅ | ⬜ pending |
| 42-06-02 | 06 | 4 | REGGRANT-03 | T-42-06-02 | No active planning document points at a deleted table | doc + CLI | the planning-directory grep for the deleted table and model names | ✅ | ⬜ pending |
| 42-06-03 | 06 | 4 | REGGRANT-01, REGGRANT-02, REGGRANT-03 | T-42-06-03 | Suite counts in the ledger are measured in this task, not copied | full suite | `uv run pytest -q` · `uv run pytest -m e2e -q` · `uv run pytest -m schema -q` · `uv run ruff check src tests` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Sampling continuity: no three consecutive tasks lack an automated verify. The only task without one
is `42-01-01`, which is a blocking human decision gate and produces no code.

---

## Wave 0 Requirements

Three test modules do not exist yet and are created by the plans that first need them, rather than by
a separate wave — each is created in the same task that produces the behaviour it measures, so no
task is left with a `MISSING` verify.

- [ ] `tests/e2e/test_claim_registered_grant.py` — created by task `42-02-01` (the two happy paths and
      the three guards) and extended by task `42-03-02` (the repeat, the four refusals, the three
      Apple arms). Model: `tests/e2e/test_claim_anonymous_grant.py`.
- [ ] `tests/unit/test_claim_precedence_registered.py` — created by task `42-03-01`. Model:
      `tests/unit/test_claim_precedence.py`, whose stubs and fixtures are reused rather than forked.
- [ ] `tests/e2e/conftest.py::seed_grant` without its companion-row parameter — delivered by task
      `42-01-03`, and a precondition of every registered e2e case, which needs a free-source grant
      seedable with no companion row.

No framework install is needed. Every other file this phase verifies against already exists:
`tests/schema/test_grant_locks.py`, `tests/schema/test_claim_race.py`,
`tests/schema/test_inventory.py`, `tests/schema/test_constraints.py`,
`tests/unit/test_grant_sources.py`, `tests/unit/test_claim_ordering.py`,
`tests/unit/test_app_wiring.py`, `tests/unit/test_rejection_vocabulary.py` and
`tests/unit/test_docstring_bar.py`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| The Apple DeviceCheck round trip against a real device | REGGRANT-01 | No iOS app exists, so nothing can produce a real DeviceCheck device token. Every wire shape in `auth/devicecheck.py` is marked assumed and carries that provenance in its module docstring. Deferred by `42-CONTEXT.md` § Deferred Ideas | When an iOS app exists: obtain a real device token, call the claim on a device whose bit1 is clear, and confirm Apple's response shape against the five parse arms. The first real 400 or 401 from Apple is authoritative over anything in this repository |
| The destructive rebuild of the developer's local dev database | REGGRANT-03 | The gate is a human decision about local data loss, not a check. The rebuild's *result* is verified automatically by the `pg_tables` probe in task `42-01-02` | Task `42-01-01` presents the gate; select `rebuild-now` or `hold` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are the one human decision gate
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing modules, each created in the task that needs it
- [x] No watch-mode flags
- [x] Feedback latency < 42s on the quick run (measured 33.31s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
