---
phase: 35
slug: foundation
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-20
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `35-RESEARCH.md` § Validation Architecture. The Per-Task
> Verification Map is populated by `/gsd:validate-phase` once plans exist.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 9.0.2 + `pytest-asyncio` 1.3.0 (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `addopts = "-v --tb=short -m 'not e2e and not schema'"`, markers `e2e` and `schema` |
| **Quick run command** | `.venv/bin/python -m pytest -q` (unit only — 163 tests, all green today) |
| **Full suite command** | `.venv/bin/python -m pytest -q -m ""` (273 collected: 163 unit + 33 e2e + 77 schema) |
| **Lint / type gate** | `.venv/bin/ruff check src tests && .venv/bin/ty check src` |
| **Estimated runtime** | ~2.5 seconds (quick) |

**Conventions new e2e modules must follow** (`tests/e2e/test_health.py:1-5`): set
`pytestmark = pytest.mark.e2e` at module level and decorate classes with
`@pytest.mark.asyncio(loop_scope="module")` to match the module-scoped
`_app_lifespan` fixture. Omitting `loop_scope="module"` binds the wrong event loop.

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest -q` plus `.venv/bin/ruff check src tests`
- **After every plan wave:** Run `.venv/bin/python -m pytest -q -m ""` plus `.venv/bin/ty check src`
- **Before `/gsd:verify-work`:** Full suite green, zero xfail, ruff and ty clean, and the real app starts
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

*Populated by `/gsd:validate-phase` once PLAN.md task IDs exist. The requirement →
test mapping below is the contract those task rows must satisfy.*

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | Four-outcome admission matrix: linked-active admits; pre-auth on a non-preauth route → `preauth_identity_not_allowed`; `identity_state != 'active'` → `account_unavailable`; `users.active IS NOT TRUE` → `account_unavailable` | e2e | `pytest -m e2e tests/e2e/test_barrier_admission.py -x` | ❌ W0 |
| FOUND-01 | A route reached with no identity context fails loudly as `auth_required` (D-02 accessors raise) | unit | `pytest tests/unit/test_identity_accessors.py -x` | ❌ W0 |
| FOUND-02 | Zero / duplicate-instance / differently-cased-duplicate / comma-joined / empty-token / trailing-content each reject with identical status, body, and copy | unit | `pytest tests/unit/test_barrier_wire_contract.py -x` | ❌ W0 |
| FOUND-02 | The same six cases over a real ASGI transport (proves duplicates survive the wire) | e2e | `pytest -m e2e tests/e2e/test_barrier_wire_contract.py -x` | ❌ W0 |
| FOUND-03 | Set-equality assertion passes for the real app; zero-category, two-category, and declared-but-unregistered each fail; all nine `§2.3` conditions | unit | `pytest tests/unit/test_route_registry.py -x` | ❌ W0 |
| FOUND-03 | The assertion executes at real startup against the real router (success criterion 5) | e2e | `pytest -m e2e tests/e2e/test_startup_assertion.py -x` | ❌ W0 |
| FOUND-04 | Registry totality: every declared class has exactly one status; no two share a code; `unauthorized` absent; `_STATUS_REMAP` gone; 404/405/422/500 each map to exactly one declared class | unit | `pytest tests/unit/test_error_registry.py -x` | ❌ W0 |
| FOUND-05 | A barrier rejection produces exactly one `audit.auth_events` row with all three actor fields NULL and a bounded reason in `details.failure` (success criterion 4) | e2e | `pytest -m e2e tests/e2e/test_audit_writer.py -x` | ❌ W0 |
| FOUND-05 | `details` top-level shape is exactly `{schema_version, context, verification, resolved, mutation, failure}`; redaction drops raw tokens and the public `challenge_id` | unit | `pytest tests/unit/test_audit_details.py -x` | ❌ W0 |
| FOUND-05 | `actor_subject_hash` is 32 bytes, stable for a fixed `(key, issuer, subject)`, and differs across key versions | unit | `pytest tests/unit/test_hmac_keys.py -x` | ❌ W0 |
| FOUND-06 | `check_all` is non-destructive; nothing charged when any budget is exhausted; all charge together on success; broadest-to-narrowest order; exhaustion → `firebase_lookup_unavailable` | unit | `pytest tests/unit/test_budgets.py -x` | ❌ W0 |
| FOUND-07 | Claim is atomic: exactly one of N concurrent claims wins; expired rejects `challenge_expired`; claimed rejects `challenge_consumed`; consume requires this `claim_attempt_id` and clears `preauth_subject_hash` | e2e | `pytest -m e2e tests/e2e/test_challenge_store.py -x` | ❌ W0 |
| FOUND-07 | `challenge_id` is 16 CSPRNG bytes base64url-unpadded; TTL exactly 300 s from server clock; `locate` compares byte-for-byte | unit | `pytest tests/unit/test_challenge_ids.py -x` | ❌ W0 |
| FOUND-08 | Adapter module declares interfaces only — no `firebase_admin` import, no concrete class | unit | `pytest tests/unit/test_adapter_interfaces.py -x` | ❌ W0 |
| D-22 | Missing/empty active key aborts config load; a missing older version only warns | unit | `pytest tests/unit/test_hmac_keys.py -x` | ❌ W0 |
| D-03 / D-04 | Middleware order is `[RequestLoggingMiddleware, AuthBarrierMiddleware]` outermost-first; no doc routes registered | unit | `pytest tests/unit/test_app_wiring.py -x` | ❌ W0 |
| D-14 | `import nativespeaker.api.app.main` succeeds and the lifespan runs clean | e2e | `pytest -m e2e tests/e2e/test_startup_assertion.py -x` | ❌ W0 |
| D-18 | Whole suite green with no xfail | all | `pytest -q -m "" && ruff check src tests && ty check src` | ✅ gate exists |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

**New unit modules:**

- [ ] `tests/unit/test_barrier_wire_contract.py` — FOUND-02
- [ ] `tests/unit/test_route_registry.py` — FOUND-03 (all nine `§2.3` conditions)
- [ ] `tests/unit/test_error_registry.py` — FOUND-04 (or extend `test_error_contract.py`)
- [ ] `tests/unit/test_audit_details.py` — FOUND-05 (shape + redaction)
- [ ] `tests/unit/test_hmac_keys.py` — FOUND-05, D-21, D-22
- [ ] `tests/unit/test_budgets.py` — FOUND-06
- [ ] `tests/unit/test_challenge_ids.py` — FOUND-07 (pure logic)
- [ ] `tests/unit/test_adapter_interfaces.py` — FOUND-08
- [ ] `tests/unit/test_identity_accessors.py` — FOUND-01 fail-loudly
- [ ] `tests/unit/test_app_wiring.py` — D-03, D-04

**New e2e modules:**

- [ ] `tests/e2e/test_barrier_admission.py` — FOUND-01 four-outcome matrix
- [ ] `tests/e2e/test_barrier_wire_contract.py` — FOUND-02 over the wire
- [ ] `tests/e2e/test_startup_assertion.py` — FOUND-03 + D-14
- [ ] `tests/e2e/test_audit_writer.py` — FOUND-05
- [ ] `tests/e2e/test_challenge_store.py` — FOUND-07 atomicity

**Harness extension (extend, do not replace):**

- [ ] `tests/e2e/conftest.py` — add a `seed_identity(state, user_active)` helper writing `core.users` + `core.external_identities`, and a `stub_verifier` fixture swapping `app.state.jwt_verifier` for an ephemeral-RSA verifier so four distinct subjects are exercisable without four Firebase accounts. Repair the existing `create_chat` helper (it builds `User(jwt_sub=…)`).

**Deletions (D-18 — dead tests go with their surfaces):**

- [ ] Delete `tests/unit/test_usage.py`, `tests/unit/test_subscriptions.py`, `tests/unit/test_webhooks.py`, `tests/e2e/test_users.py`, and the `/users/me` cases in `tests/unit/test_users.py`
- [ ] Narrow `tests/unit/test_auth_security.py`, `tests/unit/test_exception_handlers.py`, `tests/unit/conftest.py` (drop `TEST_USER`, `mock_usage_db`, `webhook_client`, and the `get_current_user`/`require_quota` overrides), `tests/e2e/test_error_cases.py`, `tests/e2e/test_chats.py`, `tests/e2e/test_chat_queries.py`, `tests/e2e/test_isolation.py`

**Framework install:** none — `pytest`, `pytest-asyncio`, and `httpx` are installed.

**Two harness properties that make this work unchanged, both verified in research:**

1. `_db_transaction` swaps `app.state.session_factory` for a connection-bound factory with `join_transaction_mode="create_savepoint"` (`tests/e2e/conftest.py:66-89`). Because D-19 routes the barrier and audit writer through that same attribute, both land inside the per-test rollback — **provided neither caches it in `__init__`**. A standalone-durable audit `commit()` under `create_savepoint` releases a savepoint, not the outer transaction, so the row is visible to a session on the same connection and still rolls back. Assertions must read through the swapped `test_factory`, not a fresh engine.
2. httpx `ASGITransport` and Starlette `TestClient` both deliver duplicate, differently-cased, and comma-joined `Authorization` fields to `scope["headers"]` byte-for-byte, so the FOUND-02 wire-contract matrix is exercisable through the ordinary client.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Anti-oracle timing indistinguishability between `historical_identity` and `blocked_user` | FOUND-04 / D-13 | Deliberately **not** implemented — D-13 scopes anti-oracle enforcement to structural identity (same code path, same single query) and explicitly rejects timing normalization as unjustified for this product. No test asserts timing parity. | Confirm by code reading that both branches leave the same identity query through the same path; assert body/status/copy equality in `test_barrier_admission.py`. Do not add a latency assertion. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
