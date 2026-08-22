---
phase: 37
slug: post-auth-create-user
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-22
---

# Phase 37 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `37-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest -q` |
| **Full suite command** | `.venv/bin/pytest -q -m ""` |
| **Estimated runtime** | ~30 seconds (quick) |

`addopts = "-v --tb=short -m 'not e2e and not schema'"` — every e2e/schema command MUST pass `-m`
explicitly (`.venv/bin/pytest -q -m e2e` · `.venv/bin/pytest -q -m schema`).

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -q` (unit only)
- **After every plan wave:** Run `.venv/bin/pytest -q -m ""` (unit + e2e + schema)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _(filled by validate-phase from PLAN.md task IDs)_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Requirement → Test Map (from RESEARCH.md)

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CREATE-01 | Route declares `preauth_callable=True`; it is the only one that may | unit | `pytest tests/unit/test_route_registry.py -q` | ✅ extend |
| CREATE-01 | Unlinked caller admitted here, `preauth_identity_not_allowed` elsewhere | e2e | `pytest -m e2e tests/e2e/test_create_user.py -q` | ❌ W0 |
| CREATE-02 | Mode-signal partition incl. duplicate/wrong-valued `challenge`, bad `challenge_id` → 400, no audit row | unit | `pytest tests/unit/test_create_user_modes.py -q` | ❌ W0 |
| CREATE-02 | Prepare returns exactly `{challenge_id, expires_at}`, `Cache-Control: no-store`, no business mutation | e2e | `pytest -m e2e tests/e2e/test_create_user.py -q` | ❌ W0 |
| CREATE-02 | Completion rejection precedence follows §02 numbering (3→4→5→6→8→9) | unit | `pytest tests/unit/test_create_user_precedence.py -q` | ❌ W0 |
| CREATE-03 | Closed classifier: 7 shapes (empty, 1×google, 1×apple, both, 2×google, unrecognized, empty-uid) | unit | `pytest tests/unit/test_provider_classifier.py -q` | ❌ W0 |
| CREATE-03 | One transaction → user + 1 ACTIVE identity + 2 attribution tokens | e2e | `pytest -m e2e tests/e2e/test_create_user.py -q` | ❌ W0 |
| CREATE-03 | Forced mid-transaction failure leaves no partial account | unit + schema | `pytest tests/unit/test_create_user_rollback.py -q` · `pytest -m schema tests/schema/test_create_atomicity.py -q` | ❌ W0 |
| CREATE-04 | Two concurrent completions for one `(issuer, subject)` → one account; loser gets `identity_already_linked` | schema | `pytest -m schema tests/schema/test_create_race.py -q` | ❌ W0 |
| CREATE-04 | Conflict classification by `constraint_name` maps 3 names → 2 internal results | unit | `pytest tests/unit/test_conflict_classification.py -q` | ❌ W0 |
| D-04 | tenacity: 3 attempts on retryable, 1 on `user_not_found`, exhaustion returns last result never `RetryError` | unit | `pytest tests/unit/test_firebase_retry.py -q` | ❌ W0 |
| D-05 | `on_admitted` at most once across retries; `record_failure` not called on `_AdmissionRejected`; transient/permanent preserved | unit | `pytest tests/unit/test_services.py -q` | ✅ must stay green |
| D-06 | `tenacity` is a direct dependency and `uv.lock` consistent | manual | `uv lock --check` | n/a |

---

## Wave 0 Requirements

- [ ] `tests/unit/test_create_user_modes.py` — stubs for CREATE-02
- [ ] `tests/unit/test_create_user_precedence.py` — stubs for CREATE-02
- [ ] `tests/unit/test_provider_classifier.py` — stubs for CREATE-03
- [ ] `tests/unit/test_create_user_rollback.py` — stubs for CREATE-03
- [ ] `tests/unit/test_conflict_classification.py` — stubs for CREATE-04
- [ ] `tests/unit/test_firebase_retry.py` — stubs for D-04
- [ ] `tests/e2e/test_create_user.py` — CREATE-01/02/03 over real transport
- [ ] `tests/schema/test_create_race.py` — CREATE-04 (two real connections)
- [ ] `tests/schema/test_create_atomicity.py` — CREATE-03 criterion 3
- [ ] Fake `FirebaseAdminAdapter` fixture (D-09) in `tests/unit/conftest.py` — shared by every substituted test
- [ ] Anonymous Firebase token fixture in `tests/e2e/conftest.py`
- [ ] Delete `tests/unit/test_budgets.py` alongside `auth/budgets.py` (D-04)
- [ ] Framework install: none needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-anonymous Firebase e2e (D-09) | CREATE-01/03 | No Firebase service-account credential exists in the repo or `.env` | Provision a service account, set credentials, then run `pytest -m e2e tests/e2e/test_create_user.py -q` |
| `uv lock --check` consistency | D-06 | Lockfile state, not a runtime behavior | `uv lock --check` exits 0 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
