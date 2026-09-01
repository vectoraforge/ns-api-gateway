---
phase: 39
slug: get-users-me
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-01
seeded_from: 39-RESEARCH.md § Validation Architecture
task_map_filled: 2026-09-01 by plan-phase (task ids bound to 39-01..39-04)
---

# Phase 39 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded by plan-phase from `39-RESEARCH.md`. The Per-Task Verification Map is filled once
> PLAN task IDs exist; every row below is already bound to a requirement and a command.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`), pytest-dotenv 0.5.2 |
| **Config file** | `pyproject.toml` → `[tool.pytest.ini_options]` (`:52-62`) |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest -q -m ""` |
| **Marked suites** | `uv run pytest -q -m e2e` · `uv run pytest -q -m schema` |
| **Lint / types** | `uv run ruff check` · `ty` |
| **Estimated runtime** | 29.2s quick (measured: 767 passed, 311 deselected) · ~30.4s wall |

**Load-bearing detail:** `addopts = "-v --tb=short -m 'not e2e and not schema'"` — every e2e or
schema command MUST pass `-m` explicitly, or the cases silently deselect.

---

## Sampling Rate

- **After every task commit:** `uv run pytest -q` (~29s) plus `uv run ruff check`
- **After every plan wave:** `uv run pytest -q -m ""` (unit + e2e + schema)
- **Before `/gsd:verify-work`:** full suite green and `ruff check` clean
- **Max feedback latency:** 35 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 39-03-T1 | 39-03 | 2 | PROF-01 | T-39-05 | Body is exactly `{profile:{email,display_name}, identity_provider, purchase_tokens}` — whole-body equality, a fourth key fails | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-03-T1 | 39-03 | 2 | PROF-01 | — | Key set equals `set(PurchaseProvider)` for every caller | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-03-T1 | 39-03 | 2 | PROF-01 (crit. 1) | T-39-05 | Body byte-identical across differing `User-Agent`, `X-Platform` header, `?platform=` query | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-04-T1 | 39-04 | 2 | PROF-01 (crit. 2) | T-39-04 | `identity_provider` equals stored `core.external_identities.provider`, read back from the row | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-04-T1 | 39-04 | 2 | PROF-01 (crit. 2) | — | `/users/me` and `/auth/sync` report the same `identity_provider` in one run | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-03-T1 | 39-03 | 2 | PROF-01 (D-03) | — | Request issues exactly one query — no second `core.users` read | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-03-T2 · 39-04-T2 | 39-03 · 39-04 | 2 | crit. 4 (D-06) | T-39-01 | Zero token rows → 500 `{"code":"internal_error"}`, one ERROR log, no null entry | unit + e2e | `uv run pytest -q tests/unit/test_purchases_crud.py` · `-m e2e tests/e2e/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-03-T2 | 39-03 | 2 | crit. 4 (D-07) | T-39-01 | One row present, one missing → same 500 (the case an emptiness check would pass) | unit | `uv run pytest -q tests/unit/test_purchases_crud.py` | ❌ W0 | ⬜ pending |
| 39-01-T3 | 39-01 | 1 | D-06 | T-39-02 | `user_id` and missing providers never reach response body or headers | unit | `uv run pytest -q tests/unit/test_error_contract.py` | ✅ extend | ⬜ pending |
| 39-01-T1 | 39-01 | 1 | D-06 | — | New error class joins recorded log vocabulary and constructor table | unit | `uv run pytest -q tests/unit/test_rejection_vocabulary.py` | ✅ extend | ⬜ pending |
| 39-01-T3 | 39-01 | 1 | D-06 | — | Error tree stays total (new class declares neither status nor code) | unit | `uv run pytest -q tests/unit/test_error_registry.py` | ✅ unchanged | ⬜ pending |
| 39-01-T2 | 39-01 | 1 | D-08 | T-39-03 | `/users/me` declares `get_linked_identity`, sits in neither exemption set | unit | `uv run pytest -q tests/unit/test_app_wiring.py` | ✅ extend | ⬜ pending |
| 39-04-T2 | 39-04 | 2 | D-08 | T-39-03 | Unauthenticated → 401 `auth_required`; unlinked → 403 `preauth_identity_not_allowed` | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-03-T1 | 39-03 | 2 | D-09 | T-39-06 | 200 carries `Cache-Control: no-store` | unit | `uv run pytest -q tests/unit/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-04-T2 | 39-04 | 2 | PROF-02 | — | No audit table, writer or call site reintroduced | unit | `uv run pytest -q tests/unit/test_sync_audit_removal.py` | ✅ unchanged | ⬜ pending |
| 39-04-T3 | 39-04 | 2 | PROF-02 | T-39-12 | Route writes nothing: table state identical before and after | e2e | `uv run pytest -q -m e2e tests/e2e/test_users_me.py` | ❌ W0 | ⬜ pending |
| 39-01-T1 · 39-03 · 39-04 | all | 1-2 | repo rule | — | Every new docstring ≤ 3 lines on every root (baselines are 0, must stay 0) | unit | `uv run pytest -q tests/unit/test_docstring_bar.py` | ✅ unchanged | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_users_me.py` — route over substituted identity + fake crud: body shape, both
      keys, `Cache-Control`, one-query, client-signal invariance. Build the client as
      `tests/unit/test_challenge_endpoint.py:73-80` does.
- [ ] `tests/unit/test_purchases_crud.py` — completeness rule: both rows → mapping; zero → raise;
      **one → raise**; statement takes no lock (`" FOR UPDATE" not in str(compiled)`).
- [ ] `tests/e2e/test_users_me.py` — real transport + database: happy path, stored-provider agreement
      with `/auth/sync`, fail-closed 500, barrier 401/403, unchanged-table-state.
- [ ] `tests/e2e/conftest.py` — add `seed_purchase_tokens` helper (existing `seed_identity` inserts
      no token rows at all).
- [ ] `tests/unit/test_rejection_vocabulary.py` — extend `EVENT_NAMES` and `CONSTRUCTOR_ARGUMENTS`
      **in the same commit** the new error class lands, or the suite goes red.
- [ ] `tests/unit/test_app_wiring.py` — `/users/me` assertions (parametrise over
      `("/auth/sync", "/users/me")`).
- [ ] `tests/unit/test_error_contract.py` — extend `_id_carrying_cases`.
- [ ] Framework install: **none needed.**

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `AGENTS.md` § Package layout states the router-to-crud rule; no `ProfileService` exists | D-05 | Documentation state, not runtime behavior | `grep -rn "ProfileService" src/` returns nothing; confirm the AGENTS.md wording was amended |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 35s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
