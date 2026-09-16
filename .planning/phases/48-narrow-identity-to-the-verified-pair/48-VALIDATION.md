---
phase: "48"
slug: "narrow-identity-to-the-verified-pair"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-16"
---

# Phase 48 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0 with pytest-asyncio >=1.3, `asyncio_mode = "auto"` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` |
| **Full suite command** | `.venv/bin/pytest -q -m ''` then `.venv/bin/pytest -q -m e2e` then `.venv/bin/pytest -q -m schema` |
| **Estimated runtime** | ~5 seconds quick; ~130 seconds for `-m ''`; `-m e2e` and `-m schema` need PostgreSQL on localhost:5432 |

`addopts` carries `-m 'not e2e and not schema'`. A bare `pytest` deselects the e2e and schema
cases. An all-deselected run is not a pass. Tools live in `.venv/bin` and are not on PATH.

Baseline at HEAD `937864c`: `-m ''` 2579 passed 1 failed; `-m e2e` 360 passed 1 failed;
`-m schema` 297 passed; `ruff check src tests` clean. The one failure is the pre-existing
restore case named in STATE.md. Criterion 5 is not charged for it.

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_app_wiring.py` and `.venv/bin/ruff check src tests`
- **After every plan wave:** Run `.venv/bin/pytest -q -m ''`
- **Before `/gsd:verify-work`:** All three suites, `ruff` and `ty` must be run, not copied
- **Max feedback latency:** 130 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 48-01-T1 | 01 | 1 | none mapped | T-48-04 | the developer decides what an already-linked caller gets at create-user | checkpoint | none — `gate="blocking-human"` | n/a | ⬜ pending |
| 48-01-T2 | 01 | 1 | none mapped | T-48-01, T-48-03, T-48-06 | a caller with no row is refused; a refused token opens no session | integration | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py` | yes | ⬜ pending |
| 48-01-T3 | 01 | 1 | none mapped | T-48-07 | every route's declaration matches D-08's table; one verify, one query | integration | `.venv/bin/pytest -q tests/unit/test_app_wiring.py tests/unit/test_identity_accessors.py` | yes | ⬜ pending |
| 48-02-T1 | 02 | 2 | none mapped | T-48-02-01, T-48-02-02 | the three rejections stand; no row answers `None` | unit | `.venv/bin/pytest -q tests/unit/test_identities_crud.py` | yes | ⬜ pending |
| 48-02-T2 | 02 | 2 | none mapped | T-48-02-01 | the admission fixture keeps every status and code | unit | `.venv/bin/pytest -q tests/unit/test_exception_handlers.py` | yes | ⬜ pending |
| 48-03-T1 | 03 | 2 | none mapped | T-48-03-02 | a body refusal issues no statement; a caller with no row is refused every other operation | integration | `.venv/bin/pytest -q tests/unit/test_challenge_endpoint.py` | yes | ⬜ pending |
| 48-03-T2 | 03 | 2 | none mapped | T-48-03-01 | both binding branches are driven | unit | `.venv/bin/pytest -q tests/unit/test_challenge_ids.py` | yes | ⬜ pending |
| 48-03-T3 | 03 | 2 | none mapped | T-48-03-01 | a handle bound to one row stays unspendable by another caller | e2e | `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` | yes | ⬜ pending |
| 48-04-T1 | 04 | 2 | none mapped | T-48-04-01 | the upgrade route's precedence is unchanged with both overrides | integration | `.venv/bin/pytest -q tests/unit/test_upgrade_precedence.py` | yes | ⬜ pending |
| 48-04-T2 | 04 | 2 | none mapped | T-48-04-01, T-48-04-02 | both grant routes' precedence is unchanged; the writers record `claims` | integration | `.venv/bin/pytest -q tests/unit/test_claim_precedence.py tests/unit/test_claim_precedence_registered.py` | yes | ⬜ pending |
| 48-05-T1 | 05 | 2 | none mapped | T-48-05-01, T-48-05-02 | the completion path issues exactly one statement; every rejection keeps its place | integration | `.venv/bin/pytest -q tests/unit/test_create_user_precedence.py` | yes | ⬜ pending |
| 48-05-T2 | 05 | 2 | none mapped | T-48-05-01 | the 422 partition and the rollback arms are unchanged | unit | `.venv/bin/pytest -q tests/unit/test_create_user_body.py tests/unit/test_create_user_rollback.py` | yes | ⬜ pending |
| 48-05-T3 | 05 | 2 | none mapped | T-48-05-01 | the SQLSTATE classification is unchanged | unit | `.venv/bin/pytest -q tests/unit/test_conflict_classification.py` | yes | ⬜ pending |
| 48-06-T1 | 06 | 2 | none mapped | T-48-06-01 | the restore destination is still the caller's own user | unit | `.venv/bin/pytest -q tests/unit/test_restore_proof.py` | yes | ⬜ pending |
| 48-06-T2 | 06 | 2 | none mapped | T-48-06-02, T-48-06-03 | the users route reads its own account; the JWKS fetch stays off the loop | unit | `.venv/bin/pytest -q tests/unit/test_users_me.py tests/unit/test_auth_security.py tests/unit/test_jwks_offload.py` | yes | ⬜ pending |
| 48-07-T1 | 07 | 2 | none mapped | T-48-07-01, T-48-07-02 | each race commits exactly one row | schema | `.venv/bin/pytest -q -m schema tests/schema/test_claim_race.py tests/schema/test_create_atomicity.py tests/schema/test_create_race.py` | yes | ⬜ pending |
| 48-07-T2 | 07 | 2 | none mapped | T-48-07-01 | the restore race commits exactly one grant | schema | `.venv/bin/pytest -q -m schema tests/schema/test_restore_race.py` | yes | ⬜ pending |
| 48-08-T1 | 08 | 3 | none mapped | T-48-08-02 | no deleted name survives anywhere | cli | `test -z "$(grep -rn '\bAuthIdentity\b' src tests)"` | n/a | ⬜ pending |
| 48-08-T2 | 08 | 3 | none mapped | T-48-08-01, T-48-08-03 | the three suites are measured, not copied | e2e | `.venv/bin/pytest -q -m ''`, `-m e2e`, `-m schema` | yes | ⬜ pending |
| 48-08-T3 | 08 | 3 | none mapped | T-48-08-01 | the one behavior question is recorded with its answer | cli | `.venv/bin/python -c "import json,re,pathlib; json.loads(...)"` | yes | ⬜ pending |

Success criterion to test map (from 48-RESEARCH.md § Validation Architecture):

| Criterion | Pinned by | Automated command |
|-----------|-----------|-------------------|
| 1 | `grep -rn '\bAuthIdentity\b' src tests` prints nothing; a new case over `LinkedIdentity.__dataclass_fields__` | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py` |
| 2 | `test_identity_accessors.py`, `test_identities_crud.py`, `test_exception_handlers.py` | `.venv/bin/pytest -q tests/unit/test_identity_accessors.py tests/unit/test_identities_crud.py tests/unit/test_exception_handlers.py` |
| 3 | `test_app_wiring.py`, `test_challenge_endpoint.py`, `tests/e2e/test_admission.py`; `grep -rn 'LinkedIdentity | None' src` returns `crud/challenges.py` alone | `.venv/bin/pytest -q tests/unit/test_app_wiring.py tests/unit/test_challenge_endpoint.py`; `.venv/bin/pytest -q -m e2e tests/e2e/test_admission.py` |
| 4 | `grep -rn 'allow_preauth\|preauth_callable' tests` prints nothing | `grep` |
| 5 | the whole suite | the three pytest commands |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase criteria. Two cases must be written, not renamed:

- [ ] `tests/unit/test_identity_accessors.py` — a case asserting `sorted(LinkedIdentity.__dataclass_fields__) == ["identity", "user"]`, frozen, slotted, no base class beyond `object`; replaces `TestTheIdentityShape`
- [ ] `tests/unit/test_identities_crud.py` — a case asserting `resolve` returns `None` when no `ExternalIdentity` row exists; replaces the two deleted `identity.user is None` cases

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — the one exception is 48-01-T1, a `gate="blocking-human"` decision that writes nothing
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references — no `MISSING` sentinel is used; both cases that must be written are inside 48-01-T2 and 48-02-T1
- [x] No watch-mode flags
- [x] Feedback latency < 130s — every per-task command is a single file or a small set
- [ ] `nyquist_compliant: true` set in frontmatter — set by `/gsd:validate-phase` after execution

**Approval:** pending
