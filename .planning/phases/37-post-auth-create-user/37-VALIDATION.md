---
phase: 37
slug: post-auth-create-user
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: true
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
| 37-01 T1-T3 | 37-01 | 1 | CREATE-02 | T-37-25 | `ChallengeStore.issue` drops `operation_variant`; binding verified before the claim | unit | `.venv/bin/pytest -q tests/unit/test_challenges.py` | ✅ | ✅ green |
| 37-02 T1-T2 | 37-02 | 1 | D-04 | T-37-18 | tenacity: 3 attempts on retryable, 1 on `user_not_found`, exhaustion returns a result never `RetryError` | unit | `.venv/bin/pytest -q tests/unit/test_firebase_retry.py` | ✅ | ✅ green |
| 37-03 T1-T2 | 37-03 | 1 | CREATE-02 | T-37-16 | `IDENTITY_ALREADY_LINKED` / `OPERATION_NOT_ALLOWED` registered; `credential_dict()` returns `dict \| None`, absent is supported | unit | `.venv/bin/pytest -q tests/unit/test_errors.py tests/unit/test_config.py` | ✅ | ✅ green |
| 37-04 T1-T2 | 37-04 | 1 | CREATE-03 | T-37-30 | `PurchaseProvider` / `StorePurchaseToken` map onto the pre-existing `subscription_*` database names | unit + schema | `.venv/bin/pytest -q tests/unit/test_users.py` · `.venv/bin/pytest -q -m schema` | ✅ | ✅ green |
| 37-05 T1-T3 | 37-05 | 2 | CREATE-03 | T-37-14, T-37-15, T-37-17, T-37-19 | Closed classifier over 7 shapes; `email_to_persist`'s two ANDed conditions; no `[DEFAULT]` app; exact-match issuer selection | unit | `.venv/bin/pytest -q tests/unit/test_provider_classifier.py tests/unit/test_firebase_adapter.py` | ✅ | ✅ green |
| 37-06 T1-T2 | 37-06 | 2 | CREATE-01 | T-37-24 | The barrier resolves identity and admits a pre-auth caller only where the registry declares it | unit + e2e | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py` · `.venv/bin/pytest -q -m e2e` | ✅ | ✅ green |
| 37-07 T1-T3 | 37-07 | 3 | CREATE-01/02/03 | T-37-26, T-37-28, T-37-31, T-37-32 | Tracer: prepare + completion end to end; claim commits before the provider read; no transaction open across it | unit + e2e | `.venv/bin/pytest -q tests/unit/test_create_user_modes.py tests/unit/test_route_registry.py` · `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py` | ✅ | ✅ green |
| 37-08 T1-T3 | 37-08 | 4 | CREATE-01/02 | T-37-36 | Nine internal results over four client classes; precedence proven by compound conflict; every post-lookup rejection consumes | unit + e2e | `.venv/bin/pytest -q tests/unit/test_create_user_precedence.py` · `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py` | ✅ | ✅ green |
| 37-09 T1-T3 | 37-09 | 4 | CREATE-03/04 | T-37-29 | Rollback-to-savepoint then classify; constraint-name discrimination; criteria 3 and 4 against real PostgreSQL | unit + schema | `.venv/bin/pytest -q tests/unit/test_conflict_classification.py tests/unit/test_create_user_rollback.py` · `.venv/bin/pytest -q -m schema tests/schema/test_create_atomicity.py tests/schema/test_create_race.py` | ✅ | ✅ green |
| 37-10 T1 | 37-10 | 5 | CREATE-01/03 | T-37-51 | Registered flow for google and apple; step 10's field rules incl. the email copy rule; the provider-account reservation, active and historical | e2e | `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py` | ✅ | ✅ green |
| 37-10 T2 | 37-10 | 5 | CREATE-03 | T-37-47, T-37-48 | Admin credential provisioned to the gitignored `.env` only, for the project `JWT_PROJECT_ID` names | manual | checkpoint — resolved as ADC (`GOOGLE_APPLICATION_CREDENTIALS`), no key mintable under org policy | n/a | ✅ green |
| 37-10 T3 | 37-10 | 5 | CREATE-01/03 | T-37-49, T-37-50 | A genuinely anonymous Firebase user completes through the **real** Admin SDK, and the real SDK's `entries == ()` is asserted rather than assumed | e2e | `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py -k RealAnonymous` | ✅ | ✅ green |

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

- [x] `tests/unit/test_create_user_modes.py` — stubs for CREATE-02
- [x] `tests/unit/test_create_user_precedence.py` — stubs for CREATE-02
- [x] `tests/unit/test_provider_classifier.py` — stubs for CREATE-03
- [x] `tests/unit/test_create_user_rollback.py` — stubs for CREATE-03
- [x] `tests/unit/test_conflict_classification.py` — stubs for CREATE-04
- [x] `tests/unit/test_firebase_retry.py` — stubs for D-04
- [x] `tests/e2e/test_create_user.py` — CREATE-01/02/03 over real transport
- [x] `tests/schema/test_create_race.py` — CREATE-04 (two real connections)
- [x] `tests/schema/test_create_atomicity.py` — CREATE-03 criterion 3
- [x] Fake `FirebaseAdminAdapter` fixture (D-09) in `tests/unit/conftest.py` — shared by every substituted test
- [x] Anonymous Firebase token fixture in `tests/e2e/conftest.py`
- [x] Delete `tests/unit/test_budgets.py` alongside `auth/budgets.py` (D-04)
- [x] Framework install: none needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ~~Real-anonymous Firebase e2e (D-09)~~ — **now automated** (37-10 Task 3) | CREATE-01/03 | ~~No Firebase service-account credential exists in the repo or `.env`~~ Resolved by Application Default Credentials, not by a key: this project's org policy sets `iam.disableServiceAccountKeyCreation`, so no service-account key can be minted at all | `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py -k RealAnonymous`. Skips with a reason naming both `FIREBASE_SERVICE_ACCOUNT_JSON` and `GOOGLE_APPLICATION_CREDENTIALS` when neither is set. **Each run creates a permanent anonymous user in the shared project** (T-37-50, accepted) |
| Firebase Admin `httpTimeout` bound on `get_user` (RESEARCH A5) | — | Left UNMEASURED by 37-05 for want of a live credential; **measured and closed by 37-10** | Measured against a blackholed `FIREBASE_AUTH_EMULATOR_HOST`: `httpTimeout=3s` → `DeadlineExceededError` at 6.01s, `httpTimeout=8s` → 16.02s. Exactly 2.00× both times — the option bounds each transport attempt, and one `get_user` makes two. See 37-10-SUMMARY § RESEARCH A5 |
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
