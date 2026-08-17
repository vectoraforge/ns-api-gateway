# Phase 23: Envoy Gateway Rate Limiting - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Infrastructure-level rate limiting by subscription tier plus backend monthly quota enforcement. Two-layer model: Envoy Gateway handles coarse per-minute burst protection using local rate limiting (no Redis), backend enforces authoritative monthly quotas in PostgreSQL. Only LLM call endpoints are rate-limited (`POST /chats`, `POST /chats/{id}`). `GET /users/me` returns usage data. Helm chart for full app deployment + Envoy Gateway policies. Project rename from `sn-api-gateway` to `ns-api-gateway`.

</domain>

<decisions>
## Implementation Decisions

### Two-layer rate limiting model

| Layer | Purpose | Store | Window | Authority |
|-------|---------|-------|--------|-----------|
| Envoy | Burst protection | Local (in-memory, per-pod) | Per minute | JWT `plan` claim |
| Backend | Monthly quota | PostgreSQL | Calendar month | DB subscription + account status |

- Only LLM call endpoints are rate-limited: `POST /chats` and `POST /chats/{id}`
- Read endpoints (`GET /chats`, `GET /chats/{id}`, `GET /users/me`, etc.) are unrestricted
- Webhook endpoint (`POST /webhooks/apple`) bypasses both JWT auth and rate limiting

### Rate limit values

**Envoy burst (per minute):**

| Free | Silver | Gold | Platinum |
|------|--------|------|----------|
| 5 | 50 | 100 | 1000 |

**Backend monthly quota:**

| Free | Silver | Gold | Platinum |
|------|--------|------|----------|
| 150 | 1,500 | 3,000 | 30,000 |

- Per-pod local rate limiting is acceptable — real enforcement is monthly quota in PostgreSQL
- With `replicaCount > 1`, burst limits are per-pod (e.g., 3 pods = user could get 15/min on free). Acceptable since backend quota is authoritative

### Error contract expansion

- New status code 429 + new error code `RATE_LIMITED` — expands error contract from 5 to 6 codes
- Envoy returns 429 with `{"code": "rate_limited"}` for burst limit (custom error response in Envoy config)
- App returns 429 with `{"code": "rate_limited"}` for monthly quota exhausted
- No reset time in error body — client knows reset from `GET /users/me` response
- Two distinct errors: burst-limit hit (Envoy) vs monthly quota exhausted (app) — same error code, different source

### Monthly quota enforcement (backend)

- `plans` table: static config mapping `tier` → `monthly_quota`. Seeded in pogo-migrate migration. Rows for free/silver/gold/platinum
- `usage_monthly` table: `user_id`, `month` (YYYY-MM text string), `used` counter
- Atomic check-and-increment: single query with JOIN to `plans` table — `UPDATE ... SET used = used + 1 WHERE used < monthly_quota` (via subquery/JOIN)
- Lazy row creation: first LLM request of the month creates the `usage_monthly` row via INSERT ON CONFLICT (same pattern as JIT user provisioning)
- Quota check happens inside ChatService before calling the LLM
- Failed LLM call (circuit breaker, timeout, etc.) rolls back the increment — user is not charged for failed requests
- Request ID generated internally for idempotency — not client-facing
- New `UsageDB` class following session-in-init pattern

### Subscription change behavior

- Tier upgrade mid-month: user immediately gets new tier's limit, usage counter is zeroed
- Tier downgrade (expiration/revocation): usage counter is zeroed, measured against new (lower) tier
- Zero-out happens when subscription status changes in SubscriptionService

### Usage data in `GET /users/me`

- Minimal response fields added: `requests_used`, `monthly_limit`, `resets_at` (first of next month, ISO timestamp)
- Data source: PostgreSQL `usage_monthly` table + `plans` table
- `GET /users/me` does NOT count toward rate limit (only LLM calls count)
- Platinum users see `monthly_limit: 30000` (real number, not pretend-unlimited)

### Envoy Gateway configuration

- Local rate limiting (no Redis, no global rate limit service) — resolves STATE.md Redis blocker
- SecurityPolicy: extracts JWT `plan` claim → `x-user-plan` request header, using Firebase JWKS URL
- BackendTrafficPolicy: per-minute rate limits by `x-user-plan` header value
- Separate HTTPRoute for `/webhooks/apple` — bypasses JWT validation and rate limiting
- Envoy Gateway already installed in cluster — chart only deploys policies, not the controller
- Envoy Gateway serves as the ingress controller (external traffic → Envoy → app)
- TLS: standard GCP/Envoy pattern (GCP load balancer or Envoy TLS termination)
- Researcher should verify latest stable Envoy Gateway version (STATE.md noted v1.7.1)

### Helm chart

- Chart name: `ns-api-gateway`
- Flat `k8s/` directory in this repo
- Chart includes: app Deployment, Service, Envoy Gateway policies (SecurityPolicy, BackendTrafficPolicy, HTTPRoutes)
- No database subchart — Google Cloud PostgreSQL provisioned separately
- No Envoy Gateway controller install — already in cluster
- Namespace: `native-speaker`
- Secrets: Kubernetes provides GCP secrets (DB creds, Firebase service account, JWT config)
- Probes: existing `GET /health/ready` for readiness/liveness
- Container port: configurable in `values.yaml` (default 8000, aligns with existing Dockerfile)
- `replicaCount` supported from the start
- Resource requests/limits: sensible defaults in values
- Rate limit numbers and monthly quotas: configurable via `values.yaml`
- Envoy only for deployed environments — no local dev Envoy setup
- No HPA for now
- Existing Dockerfile used as-is (already multi-stage with uv)
- Container image reference: TBD in values

### Project rename

- `sn-api-gateway` → `ns-api-gateway` everywhere (`sn` was a typo, `ns` = nativespeaker)
- Update: `pyproject.toml` project name, FastAPI `title`, Helm chart name
- Python package stays as `app` — no import path changes

### Claude's Discretion

- Exact SQL for atomic check-and-increment query
- UsageDB method signatures
- Helm template structure and helpers
- Envoy Gateway YAML manifest details (SecurityPolicy spec, BackendTrafficPolicy spec)
- `plans` table migration SQL and seed data
- `usage_monthly` table schema details
- How the usage rollback integrates with ChatService's existing transaction flow
- How SubscriptionService zeros usage on plan change
- Envoy custom error response configuration
- values.yaml structure and defaults

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Rate limiting (new)
- `app/services/chat_service.py` — ChatService where quota check + atomic increment will live
- `app/database/chats_db.py` — ChatsDB session-in-init pattern to follow for UsageDB
- `app/exceptions.py` — ErrorCode Literal, ServiceError hierarchy. Add `rate_limited` code + `QuotaExceededError` exception

### Usage data (extend users endpoint)
- `app/routers/users.py` — `GET /users/me` route, currently returns basic profile. Add usage fields
- `app/api/schema.py` — `UserProfileResponse` needs `requests_used`, `monthly_limit`, `resets_at` fields
- `app/api/dependencies.py` — Dependency injection. May need usage-related dependencies

### Models (add plans + usage_monthly)
- `app/models.py` — All SQLModel tables, PlanTier StrEnum. Add `Plan` and `UsageMonthly` models

### Subscription integration (zero-on-change)
- `app/services/subscription_service.py` — SubscriptionService. Add usage zero-out when plan changes
- `app/database/subscriptions_db.py` — SubscriptionDB. May need to coordinate with UsageDB

### Config + rename
- `pyproject.toml` — Project name `sn-api-gateway` → `ns-api-gateway`, version bump
- `app/api/main.py` — FastAPI title, lifespan, router registration

### Infrastructure (new)
- `Dockerfile` — Existing, multi-stage, port 8000. Chart references this image
- `docker-compose.yml` — Local dev only, no Envoy
- `k8s/` — New directory for Helm chart (does not exist yet)

### Migration
- `migrations/` — pogo-migrate. Add `plans` table (with seed data) and `usage_monthly` table

### Error handling
- `app/exceptions.py` — Add 429 status code and `rate_limited` to ErrorCode
- `app/api/errors.py` — Error handler, may need to handle new 429

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PlanTier` StrEnum in models.py — used as FK-like reference in `plans` table
- `BaseTable(SQLModel)` — base class for Plan and UsageMonthly models
- `get_db` dependency — transactional session (commit/rollback) covers quota increment + LLM call atomically
- Session-in-init DB pattern (ChatsDB, UsersDB, SubscriptionDB) — follow for UsageDB
- `ServiceError` with `status_code`/`error_code` class attrs — extend for QuotaExceededError (429)
- `QueueFullError.extra_headers()` pattern — reuse for Retry-After on quota errors if needed
- `UserProfileResponse` in schema.py — extend with usage fields
- `GET /health/ready` — Kubernetes probe ready to use

### Established Patterns
- All FastAPI dependencies in `app/api/dependencies.py`
- HTTP metadata on exception classes, single data-driven error handler
- Session-in-init on DB classes
- `__init__.py` re-export with `__all__` in services/ and database/
- `dependency_overrides` for DI swapping in tests
- INSERT ON CONFLICT for idempotent operations (users, subscription events)
- pogo-migrate for schema changes

### Integration Points
- `app/services/chat_service.py` — Add quota check before LLM call, rollback on failure
- `app/services/subscription_service.py` — Zero usage counter on plan tier change
- `app/routers/users.py` — Extend to return usage data
- `app/api/schema.py` — Extend UserProfileResponse
- `app/exceptions.py` — Add rate_limited error code, QuotaExceededError
- `app/models.py` — Add Plan, UsageMonthly models
- `app/database/__init__.py` — Add UsageDB re-export
- `app/services/__init__.py` — Update if new service needed
- `pyproject.toml` — Rename + version bump
- `app/api/main.py` — Update title
- `migrations/` — New migration for plans + usage_monthly tables
- `k8s/` — New Helm chart directory

</code_context>

<specifics>
## Specific Ideas

- Two-layer model: Envoy burst is a safety net, PostgreSQL monthly quota is the real entitlement gate
- Local rate limiting in Envoy avoids Redis dependency entirely — acceptable because backend is authoritative
- Atomic DB operation (single query with JOIN) prevents race conditions on concurrent requests
- Internal request ID for idempotency prevents double-charging on retries
- Usage zeroed on any plan change — clean slate whether upgrading or downgrading
- `plans` table is static config seeded in migration — plan changes without code deploy
- The project has always been `ns-api-gateway` — `sn` was a typo throughout

</specifics>

<deferred>
## Deferred Ideas

- HPA (Horizontal Pod Autoscaler) — add when scaling needs are understood
- Global rate limiting via Redis — if multi-pod burst protection becomes important
- Proactive quota warnings via `X-RateLimit-Remaining` header — v2 (USAGE-01)
- Grace period transparency in `GET /users/me` — v2 (USAGE-02)
- TLS certificate management details — infrastructure team concern
- Container registry setup — TBD separately from this phase

</deferred>

---

*Phase: 23-envoy-gateway-rate-limiting*
*Context gathered: 2026-03-21*
