---
phase: "44"
slug: "post-webhooks-google-play-rtdn"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-05"
---

# Phase 44 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0 with pytest-asyncio >=1.3 (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q && uv run ruff check src tests` |
| **Estimated runtime** | ~60 seconds (full suite; quick run is a few seconds) |

The `e2e` and `schema` markers are deselected by default (`addopts = "-v --tb=short -m 'not e2e and not schema'"`). A task that runs only `uv run pytest -q` proves nothing about database behaviour — schema-level claims need `-m schema` explicitly.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q`
- **Before `/gsd:verify-work`:** Full suite must be green, including `uv run ruff check src tests`, run in-plan rather than copied forward
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Seeded from `44-RESEARCH.md` § Validation Architecture. Task IDs are assigned by the planner; `/gsd:validate-phase` binds each row to its task.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | PLAYHOOK-01 | — | Invalid OIDC token refused 401, nothing written | unit | `uv run pytest tests/unit/test_google_play_notifications.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-01 | — | `email != push_service_account_email` and `email_verified is false` both refuse | unit | `uv run pytest tests/unit/test_google_play_notifications.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-01 | — | Every refusal arm answers a byte-identical body (anti-oracle) | e2e | `uv run pytest tests/e2e/test_google_play_webhook.py -m e2e -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-01 | — | Verified token + undecodable `message.data` answers 200, writes nothing (D-04) | e2e | `uv run pytest tests/e2e/test_google_play_webhook.py -m e2e -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-01 | — | Non-`subscriptionNotification` body answers 200 with no Play call (D-05) | unit | `uv run pytest tests/unit/test_google_play_notifications.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-01 | — | `packageName` mismatch refuses before any Play call (D-18) | unit | `uv run pytest tests/unit/test_google_play_notifications.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-01 | — | Absent config/credential answers 503 (D-14/D-18) | e2e | `uv run pytest tests/e2e/test_google_play_webhook.py -m e2e -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-01 | — | JWKS warm-up failure yields `None`, not a raised lifespan (F-04) | unit | `uv run pytest tests/unit/test_google_play_notifications.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-02 | — | Google path reaches `SubscriptionsService.ingest`; grace-period subscription writes an effective grant (P-01) | schema | `uv run pytest tests/schema/test_subscription_ingestion.py -m schema -q` | ✅ extend | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-02 | — | Out-of-order guard refuses an older `eventTimeMillis` for Google (D-12) | schema | `uv run pytest tests/schema/test_subscription_ingestion.py -m schema -q` | ✅ extend | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-02 | — | Redelivery under the same `notification_uuid` writes nothing (D-17, OQ-4) | schema | `uv run pytest tests/schema/test_subscription_ingestion.py -m schema -q` | ✅ extend | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-02 | — | Nine `subscriptionState` values map to five `SubscriptionStatus` members (F-08) | unit | `uv run pytest tests/unit/test_google_play_notifications.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-02 | — | Apple's five `Status` values still map one-to-one (D-11) | unit | `uv run pytest tests/unit/test_app_store_notifications.py -q` | ✅ extend | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-03 | — | Router route set equals `PROVIDER_CALLBACK_PATHS`, now two members | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ edit | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-03 | — | Each callback route declares its own mapped verifier, and neither identity accessor | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ edit | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-03 | — | Neither verifier appears off the partition | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ edit | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-03 | — | `PUBLIC_PATHS == {"/health/ready"}` still holds | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ unchanged | ⬜ pending |
| TBD | TBD | TBD | PLAYHOOK-03 | — | Verifier is dependency element 0 and `get_db` resolves after it (D-02) | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-09 | — | Firebase `JWTVerifier` tests pass unchanged | unit | `uv run pytest tests/unit/test_jwks_offload.py -q` | ✅ must not be edited | ⬜ pending |
| TBD | TBD | TBD | D-16 | — | `google_play.products` values are a subset of the three tier ids | unit | `uv run pytest tests/unit/test_config.py -q` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_google_play_notifications.py` — RS256-against-a-fake-JWKS harness plus `httpx.MockTransport` for Play. Extend `tests/unit/test_jwks_offload.py`'s `CountedJwksTransport` / `jwks_body()` / `install_counted_transport` rather than writing a second harness.
- [ ] `tests/e2e/test_google_play_webhook.py` — modelled on `tests/e2e/test_app_store_webhook.py`.
- [ ] Two fixtures in `tests/e2e/conftest.py` beside `scripted_app_store_notifications` and `unconfigured_app_store_notifications`, scripting the two Google classes behind the Protocol.
- [ ] New cases in `tests/unit/test_app_wiring.py` for D-02's dependency ordering.
- [ ] No framework install needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A real Pub/Sub push subscription delivers to the deployed route and is acknowledged | PLAYHOOK-01 | Needs a live Google Cloud project, a real push subscription, and a publicly reachable gateway — none exist in CI | Configure the push endpoint against a deployed environment, trigger a test subscription event in Play Console, confirm the message is acknowledged and not redelivered |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
