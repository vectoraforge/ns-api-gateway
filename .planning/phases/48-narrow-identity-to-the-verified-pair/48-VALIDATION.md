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
| (seeded by plan-phase; the planner fills one row per task from the PLAN.md `<automated>` commands) | | | none mapped | — | | | | | ⬜ pending |

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 130s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
