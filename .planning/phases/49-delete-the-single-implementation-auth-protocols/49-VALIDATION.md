---
phase: "49"
slug: "delete-the-single-implementation-auth-protocols"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-16"
---

# Phase 49 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest, `asyncio_mode = "auto"` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest -q <the files this commit touched> tests/unit/test_auth_package_shape.py` |
| **Full suite command** | `.venv/bin/pytest -q -m ''`, `.venv/bin/pytest -q -m e2e`, `.venv/bin/pytest -q -m schema` |
| **Lint and type gates** | `.venv/bin/ruff check src tests`, `.venv/bin/ty check` |

The default `addopts` deselects `e2e` and `schema`. Those two suites run only with `-m`, and they
use the live localhost PostgreSQL.

Phase-48 baseline: `-m ''` 1 failed, 2572 passed; `-m e2e` 1 failed, 360 passed; `-m schema`
297 passed; ruff clean; ty 306 diagnostics. The one failure is the restore four-arms case. It is
not from this phase. Each gate measures against this baseline and names that case.

---

## Sampling Rate

- **After every task commit:** the quick run command and `.venv/bin/ruff check src tests`
- **After every seam commit:** `.venv/bin/pytest -q -m ''`; also `-m e2e` and `-m schema` when the commit touches `crud/challenges.py`
- **Before `/gsd:verify-work`:** the three suites, ruff and ty, all run again

---

## Per-Task Verification Map

| Behavior | Test Type | Automated Command | File Exists | Status |
|----------|-----------|-------------------|-------------|--------|
| The four Protocol names are gone from `src/` and `tests/` | grep | `test -z "$(grep -rn 'PlaySubscriptionSource\|FirebaseAdminAdapter\|DeviceCheckAdapter\|TokenVerifier' src tests)"` | ✅ | ⬜ pending |
| `auth/adapters.py` is gone; `VerifiedProviderIdentity` comes from `auth/firebase.py` | grep | `test ! -e src/nativespeaker/api/auth/adapters.py && test -z "$(grep -rn 'auth.adapters' src tests)"` | ✅ | ⬜ pending |
| Each annotation names the concrete class | unit | `.venv/bin/pytest -q tests/unit/test_devicecheck_adapter.py tests/unit/test_google_play_notifications.py tests/unit/test_firebase_adapter.py tests/unit/test_claim_ordering.py` | ✅ | ⬜ pending |
| The auth package measures the recorded shape at each seam commit (D-08) | unit | `.venv/bin/pytest -q tests/unit/test_auth_package_shape.py` | ✅ | ⬜ pending |
| `get_challenge_store` and `challenge_store` do not exist | grep | `test -z "$(grep -rn 'challenge_store' src tests)"` | ✅ | ⬜ pending |
| The challenge route issues one row and refuses a bad body first | unit | `.venv/bin/pytest -q tests/unit/test_challenge_endpoint.py tests/unit/test_create_user_body.py` | ✅ | ⬜ pending |
| The four precedence orders do not change under the monkeypatch | unit | `.venv/bin/pytest -q tests/unit/test_create_user_precedence.py tests/unit/test_upgrade_precedence.py tests/unit/test_claim_precedence.py tests/unit/test_claim_precedence_registered.py` | ✅ | ⬜ pending |
| `ChallengesDB` behavior does not change against PostgreSQL | e2e | `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` | ✅ | ⬜ pending |
| The handle, TTL and binding rules do not change | unit | `.venv/bin/pytest -q tests/unit/test_challenge_ids.py` | ✅ | ⬜ pending |
| Each race commits one row with `AuthService` building its own crud | schema | `.venv/bin/pytest -q -m schema tests/schema/test_claim_race.py tests/schema/test_create_atomicity.py tests/schema/test_create_race.py` | ✅ | ⬜ pending |

The planner fills the task IDs.

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase behaviors. This phase writes no new test file.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
