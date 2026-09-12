---
phase: "47"
slug: "stop-threading-an-evaluation-instant-through-the-layers"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-11"
---

# Phase 47 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`), Python 3.14 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`, lines 65-76 |
| **Quick run command** | `uv run pytest -q` — 1917 cases, no database. `addopts` already carries `-m 'not e2e and not schema'`. |
| **Full suite command** | `.venv/bin/pytest -q -m ''` (2570, database), then `-m e2e` (362), then `-m schema` (291) |
| **Estimated runtime** | ~20 s for the unit suite; the three database suites together run in minutes |

`uv run pytest` and `.venv/bin/pytest` are the same interpreter and the same environment. `-m ''` is
**not** the unit suite — it is everything, and it needs the live localhost PostgreSQL.

---

## Sampling Rate

- **After every task commit:** `uv run pytest -q` (no database, catches every signature break at once)
- **After every plan wave:** `uv run pytest -q -m e2e` and `-m schema`, and at **every wave that touches
  `crud/grants.py`** the e2e quota file specifically, because that is where the effective-grant
  predicate hazard surfaces
- **Before `/gsd:verify-work`:** all three suites green, measured in plan 47-08's own run
- **Max feedback latency:** ~20 seconds (the unit suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 47-01-01 | 01 | 1 | criterion 3 (D-01) | T-47-01 | The effective-grant window neither widens nor narrows when the compared value becomes a database clock | e2e | `uv run pytest -q -m e2e tests/e2e/test_quota.py` | ✅ | ⬜ pending |
| 47-01-02 | 01 | 1 | criteria 1, 2, 3 | T-47-02 | One clock read decides the window, the period and the Retry-After together | unit | `uv run pytest -q tests/unit/test_quota_resolver.py tests/unit/test_quota_seam.py` | ✅ | ⬜ pending |
| 47-01-03 | 01 | 1 | criterion 3 | T-47-01 | The two predicate boundary cases still refuse a term not begun and a term over | e2e | `uv run pytest -q -m e2e tests/e2e/test_quota.py` | ✅ | ⬜ pending |
| 47-02-01 | 02 | 1 | D-02 | T-47-06, T-47-08 | The invariant is struck in one bullet only, and nothing outside the submodule is staged | CLI | `test "$(grep -c 'ONE captured evaluation time' /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md)" = "0"` | ✅ | ⬜ pending |
| 47-02-02 | 02 | 1 | D-02 | T-47-07 | The requirement is amended and dated, never withdrawn | CLI | `test "$(grep -c 'Amended by Phase 47 (D-02), 2026-09-11' .planning/REQUIREMENTS.md)" -ge "1"` | ✅ | ⬜ pending |
| 47-03-01 | 03 | 2 | criteria 2, 3 | T-47-09 | The grant's `starts_at` and the identity's marker come from one read, so a second free grant cannot be claimed against a mismatched marker | e2e | `uv run pytest -q -m e2e tests/e2e/test_claim_anonymous_grant.py tests/e2e/test_claim_registered_grant.py` | ✅ | ⬜ pending |
| 47-03-02 | 03 | 2 | criteria 2, 3 | T-47-10 | An anonymous provider still leaves `registered_at` unset | unit | `uv run pytest -q tests/unit/test_identity_flip.py tests/unit/test_upgrade_precedence.py` | ✅ | ⬜ pending |
| 47-03-03 | 03 | 2 | criterion 4 | T-47-09 | The two equality assertions survive the comment deletion | schema + e2e | `uv run pytest -q -m schema tests/schema/test_grant_locks.py` | ✅ | ⬜ pending |
| 47-04-01 | 04 | 2 | criteria 2, 3 | T-47-11, T-47-04 | An Apple term ending at the instant is over, pinned over `_transaction_status` | unit | `uv run pytest -q tests/unit/test_restore_proof.py` | ✅ | ⬜ pending |
| 47-04-02 | 04 | 2 | criteria 1, 2, 3 | T-47-12, T-47-13 | The Protocol and the concrete class change together, so no fake conforms by accident | unit | `uv run pytest -q tests/unit/test_google_play_notifications.py tests/unit/test_adapter_interfaces.py` | ✅ | ⬜ pending |
| 47-04-03 | 04 | 2 | criterion 2 | T-47-12 | The scripted seams match the real signatures | e2e | `uv run pytest -q -m e2e tests/e2e/test_restore_subscription.py` | ✅ | ⬜ pending |
| 47-05-01 | 05 | 3 | criteria 2, 3 | T-47-15, T-47-05 | `clock_read` stays the store's clock and keeps deciding which write takes the row | schema | `uv run pytest -q -m schema tests/schema/test_restore_race.py tests/schema/test_subscription_race.py` | ✅ | ⬜ pending |
| 47-05-02 | 05 | 3 | criteria 1, 2, 3 | T-47-14, T-47-16 | A term ending exactly at the instant is closed, proved over `_open_term` | unit | `uv run pytest -q tests/unit/test_open_term.py` | ❌ W0 — created by this task | ⬜ pending |
| 47-05-03 | 05 | 3 | criteria 2, 3 | T-47-05 | Ingestion brackets what the writer stamps and keeps exact equality for what the notification carries | schema | `uv run pytest -q -m schema tests/schema/test_subscription_ingestion.py` | ✅ | ⬜ pending |
| 47-06-01 | 06 | 4 | criteria 1, 2, 3 (D-01) | T-47-03, T-47-18 | The expiry predicate and `claimed_at` come from one `clock_timestamp()` evaluation, so a replayed handle cannot win twice | unit + e2e | `test "$(grep -c 'clock_timestamp' src/nativespeaker/api/crud/challenges.py)" = "3"` | ✅ | ⬜ pending |
| 47-06-02 | 06 | 4 | criterion 3 | T-47-17 | The comparison is `>` and not `>=`, asserted over compiled SQL with a vacuity control | e2e | `uv run pytest -q -m e2e tests/e2e/test_challenge_store.py` | ✅ | ⬜ pending |
| 47-06-03 | 06 | 4 | criteria 1, 2 | T-47-18 | `AuthService` holds no instant and every route still answers as before | e2e | `uv run pytest -q -m e2e` | ✅ | ⬜ pending |
| 47-07-01 | 07 | 5 | criteria 1, 2, 3 | T-47-20 | Sync reports only what the charge would honor at the same moment, and both fail-closed raises survive | e2e + schema | `uv run pytest -q -m e2e tests/e2e/test_sync.py` | ✅ | ⬜ pending |
| 47-07-02 | 07 | 5 | criterion 4 | — | The protected IMMUTABLE-index comment survives the sweep | CLI | `test "$(grep -c 'a partial index predicate must be IMMUTABLE' src/nativespeaker/api/crud/grants.py)" = "1"` | ✅ | ⬜ pending |
| 47-07-03 | 07 | 5 | criteria 1, 2, 4 | T-47-21, T-47-22 | The guard fails on a reintroduction and is not vacuous | unit | `uv run pytest -q tests/unit/test_instant_is_not_threaded.py` | ❌ W0 — created by this task | ⬜ pending |
| 47-08-01 | 08 | 6 | criterion 5 | T-47-23, T-47-24 | The three suites are measured here, never copied, and never on a deselected run | regression | `.venv/bin/pytest -q -m ''` | ✅ | ⬜ pending |
| 47-08-02 | 08 | 6 | criteria 1-5 | T-47-21 | Every criterion is re-derived with its own command against the finished tree | regression | `test "$(grep -rl 'get_evaluated_at' src/ tests/ \| wc -l)" = "0"` | ✅ | ⬜ pending |
| 47-08-03 | 08 | 6 | — | T-47-25, T-47-08 | The ROADMAP diff touches only the Phase 47 entry, and nothing outside the submodule is staged | CLI | `test "$(grep -c '#### Phase 4[89]:\|#### Phase 50:' .planning/ROADMAP.md)" = "3"` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No framework install and no new dependency. `freezegun` and `time_machine` are deliberately **not**
added — RESEARCH Finding 6 measured zero time-freezing code in this repository, and every relocated
case has a cheaper replacement. Two test modules are new and each is created by the task that first
needs it, so neither is a blocking Wave 0 item:

- [ ] `tests/unit/test_open_term.py` — created by task 47-05-02, carrying the restore term boundary the
      e2e suite loses in the same commit
- [ ] `tests/unit/test_instant_is_not_threaded.py` — created by task 47-07-03, covering criteria 1, 2
      and 4 with a positive control, a matcher control and a near-miss control

Existing infrastructure covers every other phase behavior.

---

## Manual-Only Verifications

All phase behaviors have automated verification. Two properties changed how they are proved rather
than whether they are proved, and both are recorded here so a later reader does not read the change as
a gap:

| Behavior | Criterion | Why it moved | What proves it now |
|----------|-----------|--------------|--------------------|
| A restore term ending exactly at the evaluated instant is closed | 3 | The route no longer takes a pinned instant, so the equality is unreachable end to end | A parametrized unit case over `_open_term`, which takes the datetime it compares against |
| A challenge claimed exactly at `expires_at` is refused | 3 | A live database clock never lands on a stored value | An assertion over the compiled SQL that the predicate is `>` and not `>=`, with a positive control that the compile produced real text |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or a Wave 0 dependency named in the task that creates it
- [x] Sampling continuity: every task carries at least one automated command; no three consecutive
      tasks run without one
- [x] Wave 0 covers both new modules, each created by the task that needs it
- [x] No watch-mode flags
- [x] Feedback latency < 30 s for the per-task gate
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
