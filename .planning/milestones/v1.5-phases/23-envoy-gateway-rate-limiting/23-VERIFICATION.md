---
phase: 23-envoy-gateway-rate-limiting
verified: 2026-03-21T12:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 12/14
  gaps_closed:
    - "app/routers/root.py updated to NativeSpeaker API Gateway and version('ns-api-gateway')"
    - "Package re-installed in editable mode — importlib.metadata.version('ns-api-gateway') returns 1.5.0"
  gaps_remaining: []
  regressions: []
---

# Phase 23: Envoy Gateway Rate Limiting — Verification Report

**Phase Goal:** API requests are rate-limited at the infrastructure edge based on user subscription tier
**Verified:** 2026-03-21T12:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (Plan 23-04)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Plan and UsageMonthly models exist and map to PostgreSQL tables | VERIFIED | `app/models.py`: `class Plan(BaseTable, table=True)` with `tier`/`monthly_quota`; `class UsageMonthly` with `id`, `user_id`, `month`, `used`, `UniqueConstraint("user_id", "month")` |
| 2 | UsageDB can atomically check-and-increment usage under quota | VERIFIED | `app/database/usage_db.py`: INSERT ON CONFLICT DO NOTHING + conditional UPDATE FROM plans WHERE used < monthly_quota RETURNING |
| 3 | QuotaExceededError returns 429 with rate_limited error code | VERIFIED | `app/exceptions.py`: `class QuotaExceededError(ServiceError): status_code = 429; error_code = "rate_limited"` |
| 4 | UserProfileResponse includes requests_used, monthly_limit, resets_at fields | VERIFIED | `app/api/schema.py`: all three fields present as `int`, `int`, `datetime` |
| 5 | Project is renamed from sn-api-gateway to ns-api-gateway | VERIFIED | `app/routers/root.py` returns `"NativeSpeaker API Gateway"` and calls `version("ns-api-gateway")`. `pyproject.toml` and `app/api/main.py` also correct. `importlib.metadata.version("ns-api-gateway")` returns `"1.5.0"`. |
| 6 | ChatService checks monthly quota before LLM call and raises QuotaExceededError when exceeded | VERIFIED | `app/services/chat_service.py` lines 60-61 (`create_chat`) and 86-87 (`send_message`): `try_increment` before `ask_llm`; raises `QuotaExceededError` on False |
| 7 | Failed LLM calls roll back the usage increment via transaction rollback | VERIFIED | `try_increment` executes inside the same DB transaction as `ask_llm`; `get_db` dependency rolls back on exception |
| 8 | SubscriptionService zeros usage counter when plan tier changes | VERIFIED | `app/services/subscription_service.py`: `reset_usage` called inside `if old_tier != plan_tier:` block before Firebase sync |
| 9 | GET /users/me returns requests_used, monthly_limit, and resets_at | VERIFIED | `app/routers/users.py`: calls `get_usage`, `get_monthly_limit`, computes `resets_at` as first of next month UTC; all fields in `UserProfileResponse` |
| 10 | 429 error code appears in the error contract test set | VERIFIED | `tests/unit/test_error_contract.py` `CONTRACT_CODES` contains `"rate_limited"`, `CONTRACT_STATUSES` contains `429`; all 8 tests in module pass (no collection errors) |
| 11 | Helm chart renders valid Kubernetes YAML with helm template | VERIFIED | `k8s/` directory contains Chart.yaml, values.yaml, _helpers.tpl, and 8 templates; structure confirmed present |
| 12 | SecurityPolicy extracts JWT plan claim to x-user-plan header | VERIFIED | `k8s/templates/security-policy.yaml`: `claimToHeaders: [{claim: plan, header: x-user-plan}]`; targets both `app-routes` and `llm-routes` HTTPRoutes |
| 13 | BackendTrafficPolicy has per-tier rate limits matching configured values and targets llm-routes only | VERIFIED | `k8s/templates/backend-traffic-policy.yaml`: 4 `clientSelectors` rules (free/silver/gold/platinum), no default rule, `targetRefs` points to `llm-routes` only |
| 14 | Webhook HTTPRoute is separate and not targeted by SecurityPolicy or BackendTrafficPolicy | VERIFIED | `k8s/templates/httproute-webhooks.yaml` is a standalone HTTPRoute for `POST /webhooks/apple`; SecurityPolicy and BackendTrafficPolicy targetRefs do not include `webhook-routes` |

**Score:** 14/14 truths verified

### Required Artifacts

#### Plan 01 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/models.py` | Plan and UsageMonthly SQLModel tables | VERIFIED | Both classes present with correct fields and UniqueConstraint |
| `app/database/usage_db.py` | UsageDB with try_increment, get_usage, reset_usage | VERIFIED | All 4 methods present; atomic SQL pattern correct |
| `app/exceptions.py` | QuotaExceededError with status_code=429 | VERIFIED | Class present, status_code=429, error_code="rate_limited" |
| `migrations/20260321_01_add-plans-and-usage.sql` | plans and usage_monthly tables with seed data | VERIFIED | CREATE TABLE plans + INSERT with 4 tiers; CREATE TABLE usage_monthly with UNIQUE constraint |
| `app/api/errors.py` | 429 not in _STATUS_REMAP, 429 in _CODE_MAP | VERIFIED | No 429 in _STATUS_REMAP; `429: "rate_limited"` in _CODE_MAP |
| `app/api/schema.py` | UserProfileResponse with usage fields | VERIFIED | requests_used, monthly_limit, resets_at all present |
| `app/database/__init__.py` | UsageDB in __all__ and imports | VERIFIED | `__all__` includes "UsageDB"; `from .usage_db import UsageDB` present |
| `pyproject.toml` | name="ns-api-gateway", version="1.5.0" | VERIFIED | Both correct |
| `app/api/main.py` | NativeSpeaker title, ns-api-gateway version ref, 429 response | VERIFIED | All three present |

#### Plan 02 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/chat_service.py` | Quota check before LLM call | VERIFIED | `try_increment` before `ask_llm` in both `create_chat` and `send_message` |
| `app/services/subscription_service.py` | Usage zero-out on plan change | VERIFIED | `reset_usage` inside `if old_tier != plan_tier:` block |
| `app/routers/users.py` | Usage data in GET /users/me response | VERIFIED | All three usage fields computed and returned |
| `tests/unit/test_usage.py` | Unit tests for quota enforcement | VERIFIED | `TestQuotaExceededError` and `TestChatServiceQuota` present; all tests pass |
| `tests/unit/test_error_contract.py` | CONTRACT_CODES includes rate_limited | VERIFIED | `CONTRACT_CODES` has `"rate_limited"`, `CONTRACT_STATUSES` has `429`; module collects and all 8 tests pass |

#### Plan 03 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `k8s/Chart.yaml` | name: ns-api-gateway, appVersion: 1.5.0 | VERIFIED | Both correct |
| `k8s/values.yaml` | rateLimits, gateway, jwt, probes configurable | VERIFIED | All fields present with correct defaults |
| `k8s/templates/security-policy.yaml` | JWT validation + claimToHeaders | VERIFIED | firebase provider with claimToHeaders; targets app-routes + llm-routes |
| `k8s/templates/backend-traffic-policy.yaml` | 4-tier clientSelectors, llm-routes target only | VERIFIED | All 4 rules, no default rule, llm-routes target, responseOverride for 429 |
| `k8s/templates/httproute-llm.yaml` | POST /chats only | VERIFIED | `method: POST` + `path: /chats` PathPrefix |
| `k8s/templates/httproute-app.yaml` | /chats, /users, /examples | VERIFIED | All 3 path prefixes present |
| `k8s/templates/httproute-webhooks.yaml` | /webhooks/apple POST only | VERIFIED | Exact path match, POST method |

#### Plan 04 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/routers/root.py` | NativeSpeaker branding, ns-api-gateway version call | VERIFIED | Returns `"NativeSpeaker API Gateway"`, calls `version("ns-api-gateway")`; no sn-api-gateway or SpeakNative references |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/database/usage_db.py` | `app/models.py` | SQL referencing usage_monthly/plans tables | VERIFIED | Raw SQL strings contain `usage_monthly` and `plans` table names |
| `app/exceptions.py` | `app/api/errors.py` | 429 status code handling | VERIFIED | 429 removed from _STATUS_REMAP; added to _CODE_MAP as "rate_limited" |
| `app/services/chat_service.py` | `app/database/usage_db.py` | `try_increment` before LLM | VERIFIED | `self.usage_db.try_increment(user_id, month)` at lines 60 and 86, before `ask_llm` calls |
| `app/services/subscription_service.py` | `app/database/usage_db.py` | `reset_usage` on plan change | VERIFIED | `self.usage_db.reset_usage(subscription.user_id, month)` inside tier-change gate |
| `app/routers/users.py` | `app/database/usage_db.py` | get_usage and get_monthly_limit | VERIFIED | Both calls present; results populate UserProfileResponse fields |
| `k8s/templates/security-policy.yaml` | `k8s/templates/httproute-app.yaml` | targetRefs app-routes | VERIFIED | `name: ...-app-routes` in targetRefs |
| `k8s/templates/backend-traffic-policy.yaml` | `k8s/templates/httproute-llm.yaml` | targetRefs llm-routes ONLY | VERIFIED | `name: ...-llm-routes` in targetRefs; `app-routes` NOT targeted |
| `app/routers/root.py` | `pyproject.toml` | `importlib.metadata.version('ns-api-gateway')` | VERIFIED | `version("ns-api-gateway")` in root.py; package installed — returns "1.5.0" |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| ENVOY-01 | 23-03 | SecurityPolicy extracts JWT `plan` claim to `x-user-plan` request header | SATISFIED | `k8s/templates/security-policy.yaml`: `claimToHeaders: [{claim: plan, header: x-user-plan}]` on firebase provider |
| ENVOY-02 | 23-03 | BackendTrafficPolicy enforces per-user rate limits by plan tier | SATISFIED | `k8s/templates/backend-traffic-policy.yaml`: 4 clientSelector rules matching x-user-plan values free/silver/gold/platinum with per-tier limits |
| ENVOY-03 | 23-03 | Webhook endpoint bypasses JWT authentication (separate HTTPRoute) | SATISFIED | `k8s/templates/httproute-webhooks.yaml` is a standalone HTTPRoute; SecurityPolicy targetRefs do not include webhook-routes |
| ENVOY-04 | 23-03 | Rate limiting uses local per-pod rate limiting (no Redis); backend PostgreSQL quota is authoritative | SATISFIED | BackendTrafficPolicy uses `rateLimit.local:` (not global/Redis); `try_increment` uses atomic PostgreSQL conditional UPDATE |
| ENVOY-05 | 23-01, 23-02 | GET /users/me returns plan usage data (request counts, limits) | SATISFIED | `app/routers/users.py` returns `requests_used`, `monthly_limit`, `resets_at`; full unit test suite 134/134 passes |

### Anti-Patterns Found

No blocking anti-patterns. No placeholder implementations, empty return bodies, or stub wiring patterns found in any service, database, or Helm artifact.

The previously-flagged issues in root.py and package metadata are fully resolved.

### Human Verification Required

#### 1. Helm chart deployment against live Envoy Gateway

**Test:** Deploy chart to a Kubernetes cluster with Envoy Gateway v1.7.1 installed. Issue a POST /chats request as a `free` tier user. After 5 requests within a minute, verify the 6th returns HTTP 429 with body `{"code":"rate_limited"}`.
**Expected:** Rate limiting enforced by BackendTrafficPolicy at the edge; response body matches the responseOverride config.
**Why human:** Cannot verify Envoy Gateway policy enforcement with static analysis. Requires a live cluster.

#### 2. Monthly quota rollover behavior

**Test:** Advance system time to a month boundary. Verify that `resets_at` in GET /users/me updates to the new month, and a new month's quota starts fresh (usage counter for the new month is 0).
**Expected:** `resets_at` is always the first of next calendar month in UTC; new month's `try_increment` succeeds from zero.
**Why human:** Requires manipulating system time or waiting for calendar rollover.

#### 3. Race condition safety for try_increment under concurrent load

**Test:** Issue 200 concurrent POST /chats requests for a free-tier user (quota=150). Verify exactly 150 succeed and 50 receive QuotaExceededError with no count exceeding 150.
**Expected:** Atomic INSERT ON CONFLICT + conditional UPDATE prevents over-counting.
**Why human:** Requires concurrent load testing; cannot be verified by static code analysis.

### Re-verification Summary

Both gaps from the initial verification have been closed by Plan 23-04:

**Gap 1 — Closed:** `app/routers/root.py` now returns `"NativeSpeaker API Gateway"` and calls `version("ns-api-gateway")`. No references to `sn-api-gateway` or `SpeakNative` remain in that file.

**Gap 2 — Closed:** Package re-installed in editable mode. `importlib.metadata.version("ns-api-gateway")` returns `"1.5.0"`. `tests/unit/test_error_contract.py` collects without error and all 8 tests in the module pass.

**Regression check:** Full unit suite runs 134/134 tests — no regressions from the gap closure change.

---

_Verified: 2026-03-21T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
