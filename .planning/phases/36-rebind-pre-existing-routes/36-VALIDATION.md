---
phase: 36
slug: rebind-pre-existing-routes
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-21
---

# Phase 36 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `36-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 9.0.2 + `pytest-asyncio` >=1.3 (`asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (lines 51-61) — `testpaths=["tests"]`, `pythonpath=["."]`, `env_files=[".env"]`, `addopts = "-v --tb=short -m 'not e2e and not schema'"` |
| **Quick run command** | `uv run pytest -q` (unit only — 912 passing, 250 deselected) |
| **Full suite command** | `uv run pytest -q -m ""` (1162 collected: 912 unit + e2e + schema) |
| **Lint / type gate** | `uv run ruff check src tests && uv run ty check src` |
| **Estimated runtime** | ~26 seconds (quick) |

**Conventions new e2e modules must follow:** module-level `pytestmark = pytest.mark.e2e` and
`@pytest.mark.asyncio(loop_scope="module")` on classes, to match the module-scoped `_app_lifespan`
fixture. Omitting `loop_scope="module"` binds the wrong event loop. Schema modules use
`pytest.mark.schema` and the function-scoped `conn` fixture.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q` + `uv run ruff check src tests`
- **After every plan wave:** Run `uv run pytest -q -m ""` + `uv run ty check src`
- **Before `/gsd:verify-work`:** Full suite green, ruff and ty clean, and the real app starts
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Seeded by plan-phase from the requirement→test map below. Task IDs are filled in by
> `/gsd:validate-phase` once PLAN.md task numbering exists.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | REBIND-01 | — | Enumeration passes both directions with `quota_checked` set | unit | `uv run pytest tests/unit/test_route_registry.py -x` | ✅ extend | ⬜ pending |
| TBD | TBD | TBD | REBIND-01 | — | D-05 cross-check fails boot when flag and decorator disagree | unit | `uv run pytest tests/unit/test_route_registry.py -k quota_checked -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-01 | — | Assertion passes against the live started app | e2e | `uv run pytest tests/e2e/test_startup_assertion.py -x -m e2e` | ✅ | ⬜ pending |
| TBD | TBD | TBD | REBIND-02 | T-36-telemetry | Zero audit rows on all eight routes incl. `POST /chats/{chat_id}` | e2e | `uv run pytest tests/e2e/test_audit_writer.py -k OffPath -x -m e2e` | ✅ extend | ⬜ pending |
| TBD | TBD | TBD | REBIND-02 | T-36-telemetry | Counter increments on barrier rejection off-path | e2e | `uv run pytest tests/e2e/test_audit_writer.py -k Telemetry -x -m e2e` | ✅ | ⬜ pending |
| TBD | TBD | TBD | REBIND-02 | T-36-telemetry | Zero audit rows on a quota (429) rejection | e2e | `uv run pytest tests/e2e/test_quota.py -k audit -x -m e2e` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-03 | T-36-oracle | Auth rejections carry the shared body/status | unit + e2e | `uv run pytest tests/unit/test_error_contract.py tests/e2e/test_startup_assertion.py -x` | ✅ | ⬜ pending |
| TBD | TBD | TBD | REBIND-05 | T-36-bypass | No effective grant → 429 `quota_exceeded` | e2e | `uv run pytest tests/e2e/test_quota.py -k no_grant -x -m e2e` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-05 | T-36-mint | Missing usage row → 500 `internal_error`, and no row is minted | e2e | `uv run pytest tests/e2e/test_quota.py -k missing_usage -x -m e2e` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-05 | — | Lazy rollover resets `monthly_used` when the stored period is stale | e2e | `uv run pytest tests/e2e/test_quota.py -k rollover -x -m e2e` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-05 | T-36-bypass | `remaining` never negative; exhaustion → 429 | unit | `uv run pytest tests/unit/test_quota_resolver.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-05 | T-36-deadlock | Grant-then-usage lock order under real contention | schema | `uv run pytest tests/schema/test_grant_locks.py -x -m schema` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-05 | — | Multi-grant tripwire raises rather than tie-breaks | unit | `uv run pytest tests/unit/test_quota_resolver.py -k multiple -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-06 | — | App starts; the eight routes serve as in v1.6 | e2e | `uv run pytest tests/e2e -x -m e2e` | ✅ needs grant-seeding fixture | ⬜ pending |
| TBD | TBD | TBD | REBIND-06 | — | A correct phrase returns 200 with empty arrays (D-12) | unit + e2e | `uv run pytest tests/unit/test_models.py -k analyze -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | REBIND-06 | T-36-drain | A malformed body does not burn a credit | e2e | `uv run pytest tests/e2e/test_quota.py -k malformed -x -m e2e` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**REBIND-04 note:** no row above, and none is owed. `REQUIREMENTS.md:49` marks REBIND-04 **Void** —
the `quota_checked_request` admission entry it required no longer exists (Phase 35 D-05 deleted
backend rate limiting from the product). REBIND-05's grant resolution, lock order, and lazy
rollover are unaffected.

---

## Wave 0 Requirements

- [ ] `tests/e2e/test_quota.py` — new module: 429-no-grant, 500-missing-usage, rollover, exhaustion, no-audit-row-on-429, malformed-body-no-burn. Covers REBIND-02/05/06.
- [ ] `tests/unit/test_quota_resolver.py` — pure policy: allowance arithmetic, `max(0, ...)`, period comparison, multi-grant tripwire. Covers REBIND-05.
- [ ] `tests/schema/test_grant_locks.py` — two-connection lock-order/contention test. Covers REBIND-05. Must live in `tests/schema/` (the e2e `_db_transaction` fixture pins every session to one connection via `join_transaction_mode="create_savepoint"`, so a contention test there would pass vacuously).
- [ ] **Grant-seeding e2e fixture** in `tests/e2e/conftest.py` — seeds grant **and** usage row against the seeded `registered` tier. Must land in the **same wave** as `require_quota` attachment; seeding only the grant turns six existing e2e tests from 429s into 500s.
- [ ] Unit `client` fixture override for the quota dependency (`tests/unit/conftest.py:146-167`).
- [ ] Add `("POST", "/chats/{chat_id}")` to the `test_audit_writer.py:339-345` parametrize list.
- [ ] Framework install: none required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| The real application boots against a live PostgreSQL 17 + Firebase + OpenAI | REBIND-06 | Assumption A1 — the sandbox cannot reach PostgreSQL, Firebase, or OpenAI, so e2e/schema greenness is unverified from the planning environment | `docker compose up -d db && uv run pogo migrate && uv run uvicorn nativespeaker.api.app.main:app`, then `curl -f localhost:8000/health/ready` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
