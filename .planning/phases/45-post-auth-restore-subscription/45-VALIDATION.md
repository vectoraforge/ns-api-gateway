---
phase: "45"
slug: "post-auth-restore-subscription"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-07"
---

# Phase 45 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 with pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q && uv run ruff check src tests` |
| **Estimated runtime** | ~60 s for the quick run; ~4 min for the full set |

Measured baseline before this phase: **1190 unit / 298 e2e / 205 schema**, `ruff check src tests`
clean. Every plan's final task re-runs the full set, and 45-05 records the new counts.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run the full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 45-01-01 | 01 | 1 | RESTORE-01, RESTORE-02 | T-45-01 / T-45-02 / T-45-05 | A proof that does not verify attaches nothing; an unserved store name answers a byte-identical 403 | e2e | `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q` | created by the task | ⬜ pending |
| 45-01-02 | 01 | 1 | RESTORE-01, RESTORE-02 | T-45-02 / T-45-04 | The chain walk is non-vacuous against the vendored root; no stage carries the proof | unit | `uv run pytest tests/unit/test_restore_proof.py -q` | created by the task | ⬜ pending |
| 45-02-01 | 02 | 2 | RESTORE-01 | T-45-03 / T-45-04 | An unmapped product stays a 500; the purchase token reaches no log field | unit | `uv run pytest tests/unit/test_restore_proof.py -q` | ✅ after 45-01 | ⬜ pending |
| 45-02-02 | 02 | 2 | RESTORE-01, RESTORE-02 | T-45-05 / T-45-06 | Every refusal of both stores answers one byte-identical body | e2e | `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q` | ✅ after 45-01 | ⬜ pending |
| 45-03-01 | 03 | 3 | RESTORE-01 | T-45-07 | Ingestion keeps an owner that is already set | unit | `uv run pytest tests/unit/test_subscription_attribution.py -q` | ✅ | ⬜ pending |
| 45-03-02 | 03 | 3 | RESTORE-01 | T-45-01 / T-45-05 / T-45-09 | The two 404 refusals are one answer, and neither writes a row | e2e | `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q` | ✅ after 45-01 | ⬜ pending |
| 45-04-01 | 04 | 4 | RESTORE-01 | T-45-01 / T-45-10 | The cap refuses before any lock and writes nothing | unit | `uv run pytest tests/unit/test_error_contract.py tests/unit/test_error_registry.py tests/unit/test_rejection_vocabulary.py -q` | ✅ | ⬜ pending |
| 45-04-02 | 04 | 4 | RESTORE-01 | T-45-01 | The moved-from account loses access at that moment | e2e | `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q` | ✅ after 45-01 | ⬜ pending |
| 45-04-03 | 04 | 4 | RESTORE-01 | T-45-09 / T-45-11 | Exactly one grant survives a race; the deferred keys refuse at COMMIT | schema | `uv run pytest -m schema tests/schema/test_restore_race.py -q` | created by the task | ⬜ pending |
| 45-05-01 | 05 | 5 | RESTORE-01, RESTORE-02 | T-45-12 | The binding brief is unedited | doc | `echo "<pinned sha256 pair>" \| sha256sum -c --status` | ✅ | ⬜ pending |
| 45-05-02 | 05 | 5 | RESTORE-01, RESTORE-02 | T-45-06 / T-45-13 | The accepted exposure and the open product questions are recorded, not silently dropped | doc | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No separate Wave 0 is needed. The three new test files are created by the tasks that need them,
and the tracer carries its own end-to-end case rather than depending on a scaffolding wave:

- `tests/e2e/test_restore_subscription.py` and the `seed_subscription` fixture — created inside
  45-01 Task 1, which is the tracer and cannot be verified without them.
- `tests/unit/test_restore_proof.py` — created by 45-01 Task 2, extended by 45-02 Task 1.
- `tests/schema/test_restore_race.py` — created by 45-04 Task 3.
- No framework install: `pytest`, `pytest-asyncio`, `asyncpg` and `httpx` are all present, and
  `pyproject.toml` is unchanged by this phase.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A real StoreKit 2 signed transaction from a real iOS app verifies | RESTORE-01 | No iOS app exists, so nothing can produce one (RESEARCH A1/A2). Recorded as a standing fact, not a gap. | When the iOS app ships, send one real `Transaction.jwsRepresentation` and confirm 200. The first real refusal from Apple is authoritative over this repository. |
| A real Play purchase token from a real Android app verifies | RESTORE-01 | No `GOOGLE_PLAY_*` configuration and no Android app exists. | When the app ships, restore with a real purchase token against the configured package. |

All other phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references — none is owed; the creating task carries each file
- [x] No watch-mode flags
- [x] Feedback latency < 60s for the quick run
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
