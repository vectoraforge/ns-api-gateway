---
phase: "49"
slug: "delete-the-single-implementation-auth-protocols"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: true
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

**Correction, measured in 49-04 Task 2.** The `-m ''` passed count of 2572 was already stale when
this phase opened: plans 49-01, 49-02 and 49-03 each measured 2563, and 49-04 measures 2563 again.
Every other baseline figure holds. The `-m ''` number above is kept as written so the drift stays
visible.

---

## Sampling Rate

- **After every task commit:** the quick run command and `.venv/bin/ruff check src tests`
- **After every seam commit:** `.venv/bin/pytest -q -m ''`; also `-m e2e` and `-m schema` when the commit touches `crud/challenges.py`
- **Before `/gsd:verify-work`:** the three suites, ruff and ty, all run again

---

## Per-Task Verification Map

| Behavior | Task | Test Type | Automated Command | File Exists | Status |
|----------|------|-----------|-------------------|-------------|--------|
| The four Protocol names are gone from `src/` and `tests/` | 49-01 T1, 49-01 T2, 49-02 T1, 49-02 T2 | grep | `test -z "$(grep -rn 'PlaySubscriptionSource\|FirebaseAdminAdapter\|DeviceCheckAdapter\|TokenVerifier' src tests)"` | ✅ | ✅ green — 0 tracked lines, word-scoped (note A) |
| `auth/adapters.py` is gone; `VerifiedProviderIdentity` comes from `auth/firebase.py` | 49-02 T2 | grep | `test ! -e src/nativespeaker/api/auth/adapters.py && test -z "$(grep -rn 'nativespeaker.api.auth.adapters' src tests)"` | ✅ | ✅ green — module absent; 0 tracked lines (note B) |
| Each annotation names the concrete class | 49-01 T1, 49-01 T2, 49-02 T1, 49-02 T2 | unit | `.venv/bin/pytest -q tests/unit/test_devicecheck_adapter.py tests/unit/test_google_play_notifications.py tests/unit/test_firebase_adapter.py tests/unit/test_claim_ordering.py` | ✅ | ✅ green — 295 passed |
| The auth package measures the recorded shape at each seam commit (D-08) | 49-01 T1, 49-01 T2, 49-02 T1, 49-02 T2 | unit | `.venv/bin/pytest -q tests/unit/test_auth_package_shape.py` | ✅ | ✅ green — 2 passed |
| The relocated SDK-isolation guard and value-type guard still run | 49-02 T2 | unit | `.venv/bin/pytest -q tests/unit/test_firebase_adapter.py` | ✅ | ✅ green — 74 passed |
| `get_challenge_store` and `challenge_store` do not exist | 49-03 T1 | grep | `test -z "$(grep -rn 'challenge_store' src tests)"` | ✅ | ✅ green — 0 lines, exit 0 |
| The challenge route issues one row and refuses a bad body first | 49-03 T1, 49-04 T1 | unit | `.venv/bin/pytest -q tests/unit/test_challenge_endpoint.py tests/unit/test_create_user_body.py` | ✅ | ✅ green — 73 passed |
| The four precedence orders do not change under the monkeypatch | 49-03 T1, 49-04 T1 | unit | `.venv/bin/pytest -q tests/unit/test_create_user_precedence.py tests/unit/test_upgrade_precedence.py tests/unit/test_claim_precedence.py tests/unit/test_claim_precedence_registered.py` | ✅ | ✅ green — 136 passed |
| No `ChallengesDB` method takes a session | 49-04 T1 | grep | `test -z "$(grep -n 'async def issue(self, session\|async def locate(self, session\|async def claim(self, session\|async def consume(self, session' src/nativespeaker/api/crud/challenges.py)"` | ✅ | ✅ green — 0 lines, exit 0 |
| `ChallengesDB` behavior does not change against PostgreSQL | 49-04 T1 | e2e | `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py` | ✅ | ✅ green — 32 passed |
| The handle, TTL and binding rules do not change | 49-04 T1 | unit | `.venv/bin/pytest -q tests/unit/test_challenge_ids.py` | ✅ | ✅ green — 40 passed |
| Each race commits one row with `AuthService` building its own crud | 49-03 T1, 49-04 T1 | schema | `.venv/bin/pytest -q -m schema tests/schema/test_claim_race.py tests/schema/test_create_atomicity.py tests/schema/test_create_race.py` | ✅ | ✅ green — 55 passed |
| The type gate does not rise above its 306 baseline | 49-03 T2, 49-04 T2 | CLI | `.venv/bin/ty check` | ✅ | ✅ green — 306 diagnostics |

Every figure above was read from a command run in plan 49-04 Task 2, on 2026-09-17, at commit
`46a92ad`. No number is copied from a plan, a summary or a research file.

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Note A — the plain grep matches a test double, not the deleted Protocol

`grep -rn 'DeviceCheckAdapter' src tests` prints 3 lines, all of them
`FakeDeviceCheckAdapter` in `tests/e2e/conftest.py:301, 335, 504`. That is a different identifier
that carries the deleted one as a substring. The word-scoped, tracked-file form reads 0:

`git grep -nwE 'PlaySubscriptionSource|FirebaseAdminAdapter|DeviceCheckAdapter|TokenVerifier|challenge_store' -- src tests` → 0 lines.

The name is gone. Renaming the e2e fake is not this phase's work; no plan in 49 touches it.

### Note B — the plain grep matches a gitignored build artifact

`grep -rn 'nativespeaker.api.auth.adapters' src tests` prints one line,
`src/ns_api_gateway.egg-info/SOURCES.txt:14`. That file is gitignored (`.gitignore:7 *.egg-info/`)
and is a stale packaging index naming a module that is no longer on disk.
`test ! -e src/nativespeaker/api/auth/adapters.py` passes, and
`git grep -n 'nativespeaker\.api\.auth\.adapters' -- src tests` reads 0 lines.

Both notes record the same lesson plans 49-01 and 49-02 met: a `grep -rn` over a working tree
answers for substrings and for untracked build output, so a "the name is gone" check uses
`git grep -nw <name> -- src tests`.

---

## Wave 0 Requirements

Existing infrastructure covers all phase behaviors. This phase writes no new test file.

**Spec-less probe fallback: skipped (visible skip).** Phases 47 to 50 are refactors added after the
spec phases closed, so there is no SPEC, and the ROADMAP maps no requirement ID to this phase. The
fallback needs requirement IDs to probe, so no probe predicate is generated this run. The five
ROADMAP success criteria and the eight CONTEXT decisions are the contract instead.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## The Phase Gate, Measured

Run from the repository root at commit `46a92ad`, on 2026-09-17. Each line is this run's own output.

| Gate | Command | Result |
|---|---|---|
| Unit and everything | `.venv/bin/pytest -q -m ''` | `1 failed, 2563 passed` |
| End to end | `.venv/bin/pytest -q -m e2e` | `1 failed, 360 passed, 2203 deselected` |
| Schema | `.venv/bin/pytest -q -m schema` | `297 passed, 2267 deselected` |
| Lint | `.venv/bin/ruff check src tests` | `All checks passed!` |
| Types | `.venv/bin/ty check` | `Found 306 diagnostics` |

**The one failing case is
`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`.**
It is not this phase's. The log event name comes from the exception class name while the case
asserts the error code; Phases 47 and 48 both recorded it and neither fixed it. Phase 49 does not
fix it either. It is the only failed case in either suite.

Neither marked run was an all-deselected run: `-m e2e` selected 361 cases and `-m schema` selected
297.

### The five phase-wide greps

| Grep | Result |
|---|---|
| `PlaySubscriptionSource` in `src` and `tests` | 0 lines |
| `FirebaseAdminAdapter` in `src` and `tests` | 0 lines |
| `DeviceCheckAdapter` in `src` and `tests` | 0 lines word-scoped; 3 substring lines, all `FakeDeviceCheckAdapter` (note A) |
| `TokenVerifier` in `src` and `tests` | 0 lines |
| `challenge_store` in `src` and `tests` | 0 lines |
| `src/nativespeaker/api/auth/adapters.py` on disk | absent |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references — this phase declares none and writes no new test file
- [x] No watch-mode flags
- [x] `nyquist_compliant: true` set in frontmatter

`status:` and `wave_0_complete:` are left as they stand: `/gsd:validate-phase` §6 owns them, and
this plan measured neither.

**Approval:** 2026-09-17 — every row green, re-measured at commit `46a92ad`, with the one
pre-existing restore four-arms failure named above and not fixed.
