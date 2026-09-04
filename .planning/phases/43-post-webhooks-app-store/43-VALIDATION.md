---
phase: "43"
slug: "post-webhooks-app-store"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-04"
---

# Phase 43 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x with pytest-asyncio 1.3 (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -q && uv run ruff check src tests` |
| **Full suite command** | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` |
| **Estimated runtime** | ~34 seconds (quick); full suite needs a reachable PostgreSQL |

Markers: `e2e` and `schema`, both deselected by `addopts`. Baseline at research time: 1016 unit / 241 e2e / 154 schema passed, ruff clean.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q && uv run ruff check src tests`
- **After every plan wave:** Run `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q`
- **Before `/gsd:verify-work`:** Full suite must be green, quoted with counts as Phases 41 and 42 did
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | APPLEHOOK-01 | — | Chain rooting in the configured root verifies; vendored Apple root refuses the throwaway chain; every `VerificationStatus` outcome is 401 with its own `stage`; bad nested payload is 401 even when the envelope verifies | unit | `uv run pytest tests/unit/test_app_store_notifications.py -q` | ❌ W0 | ⬜ pending |
| — | — | — | APPLEHOOK-01 | — | Absent or incomplete config answers 503; Firebase token plus bad payload is still 401 | unit + e2e | `uv run pytest tests/unit/test_app_store_notifications.py tests/e2e/test_app_store_webhook.py -q` | ❌ W0 | ⬜ pending |
| — | — | — | APPLEHOOK-02 | — | Partition equals routes on the webhooks router; each callback route declares the verifier and no identity accessor; no route outside the partition declares the verifier; `PUBLIC_PATHS` stays `{"/health/ready"}` | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ extend | ⬜ pending |
| — | — | — | APPLEHOOK-02 | — | Route reachable with no Authorization header | e2e | `uv run pytest tests/e2e/test_unauthenticated_access.py -q` | ✅ extend | ⬜ pending |
| — | — | — | D-13/D-15/D-17–D-20 | — | Writer outcomes on real PostgreSQL; replay writes nothing and answers 200; concurrent race has one winner | schema | `uv run pytest tests/schema/test_subscription_ingestion.py tests/schema/test_subscription_race.py -q` | ❌ W0 | ⬜ pending |
| — | — | — | D-16 | — | Grant locks before usage locks, no third tier | schema | `uv run pytest tests/schema/test_grant_locks.py -q` | ✅ extend | ⬜ pending |
| — | — | — | D-21/D-22 | — | `AttributionConflict` and `UnmappedStoreProduct` answer 500 and write nothing; TEST notification answers 200 and writes nothing | e2e | `uv run pytest tests/e2e/test_app_store_webhook.py -q` | ❌ W0 | ⬜ pending |

*Task IDs are bound by `/gsd:validate-phase` once PLAN.md files exist. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_app_store_notifications.py` — the seam; needs a throwaway X.509 chain fixture (RESEARCH § Code Example 6)
- [ ] `tests/e2e/test_app_store_webhook.py` — the route; needs a `scripted_app_store_notifications` fixture in `tests/e2e/conftest.py` mirroring `scripted_devicecheck_adapter`
- [ ] `tests/schema/test_subscription_ingestion.py` — the writer on real PostgreSQL; needs `insert_subscription` / `insert_store_purchase` helpers in `tests/schema/helpers.py`
- [ ] `tests/schema/test_subscription_race.py` — the two-connection race; extend the `tests/schema/test_claim_race.py` harness
- [ ] Framework install: none — pytest, pytest-asyncio and PostgreSQL are present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Apple's production delivery reaches the route through Envoy Gateway | APPLEHOOK-01 | Apple's servers and the cluster are not reachable from the test environment | Send a sandbox notification from App Store Connect; confirm one `request` log line and a 200 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
