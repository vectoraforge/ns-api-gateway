# Phase 23: Envoy Gateway Rate Limiting - Research

**Researched:** 2026-03-21
**Domain:** Infrastructure-level rate limiting (Envoy Gateway) + backend monthly quota enforcement (PostgreSQL) + Helm chart + project rename
**Confidence:** HIGH

## Summary

This phase implements a two-layer rate limiting model: Envoy Gateway handles per-minute burst protection using local (in-memory, per-pod) rate limiting, while the backend enforces authoritative monthly quotas in PostgreSQL. Only LLM call endpoints (`POST /chats`, `POST /chats/{id}`) are rate-limited. The project also introduces a Helm chart for Kubernetes deployment and renames `sn-api-gateway` to `ns-api-gateway`.

Envoy Gateway v1.7.1 (released 2026-03-12) is the latest stable version, confirmed on GitHub releases. It uses the `gateway.envoyproxy.io/v1alpha1` API version for SecurityPolicy and BackendTrafficPolicy CRDs. Local rate limiting is fully supported with per-header `clientSelectors` to differentiate rate limits by the `x-user-plan` header value (extracted from JWT `plan` claim). The design specifically avoids Redis by using local rate limiting -- the backend PostgreSQL quota is the authoritative enforcement layer.

**Primary recommendation:** Use separate HTTPRoutes (one for webhooks without JWT, one for the main app with JWT + rate limiting), SecurityPolicy with `claimToHeaders` to extract the JWT `plan` claim as `x-user-plan`, BackendTrafficPolicy with local rate limiting rules per plan tier, and responseOverride to return JSON `{"code":"rate_limited"}` on 429. Backend quota uses an atomic `UPDATE ... WHERE used < quota` pattern in a new `UsageDB` class.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Two-layer rate limiting: Envoy burst (local, in-memory, per-pod, per minute) + backend monthly quota (PostgreSQL)
- Only LLM call endpoints rate-limited: `POST /chats` and `POST /chats/{id}`
- Read endpoints, `GET /users/me`, health checks are unrestricted
- Webhook endpoint (`POST /webhooks/apple`) bypasses both JWT auth and rate limiting
- Burst values: Free=5, Silver=50, Gold=100, Platinum=1000 per minute
- Monthly quotas: Free=150, Silver=1,500, Gold=3,000, Platinum=30,000
- Per-pod local rate limiting acceptable (backend quota is authoritative)
- Error contract expansion: 429 + `rate_limited` error code
- Envoy returns 429 with `{"code": "rate_limited"}` for burst, app returns 429 for monthly quota
- `plans` table: static config seeded in pogo-migrate migration
- `usage_monthly` table: user_id, month (YYYY-MM text), used counter
- Atomic check-and-increment: single query with JOIN to plans table
- Lazy row creation via INSERT ON CONFLICT
- Quota check in ChatService before LLM call
- Failed LLM call rolls back increment
- Tier upgrade mid-month: new limit, usage zeroed
- Tier downgrade: usage zeroed, new (lower) limit
- Zero-out happens in SubscriptionService
- `GET /users/me` adds: requests_used, monthly_limit, resets_at
- Local rate limiting (no Redis, no global rate limit service)
- SecurityPolicy extracts JWT `plan` claim to `x-user-plan` header via Firebase JWKS
- Separate HTTPRoute for `/webhooks/apple` bypassing JWT and rate limiting
- Envoy Gateway already installed in cluster -- chart deploys policies only
- Helm chart name: `ns-api-gateway`, flat `k8s/` directory
- Namespace: `native-speaker`
- No database subchart, no Envoy Gateway controller install, no HPA
- Project rename: `sn-api-gateway` -> `ns-api-gateway` (pyproject.toml, FastAPI title, Helm chart)
- New `UsageDB` class following session-in-init pattern
- Existing Dockerfile used as-is

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

### Deferred Ideas (OUT OF SCOPE)
- HPA (Horizontal Pod Autoscaler)
- Global rate limiting via Redis
- Proactive quota warnings via `X-RateLimit-Remaining` header (v2 USAGE-01)
- Grace period transparency in `GET /users/me` (v2 USAGE-02)
- TLS certificate management details
- Container registry setup
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENVOY-01 | SecurityPolicy extracts JWT `plan` claim to `x-user-plan` request header | SecurityPolicy `claimToHeaders` field verified in Envoy Gateway v1.7.1 docs -- maps `claim: plan` to `header: x-user-plan` using Firebase JWKS URL |
| ENVOY-02 | BackendTrafficPolicy enforces per-user rate limits by plan tier | BackendTrafficPolicy local rate limiting with `clientSelectors` header matching verified -- separate rules per plan tier with different `requests`/`unit` limits |
| ENVOY-03 | Webhook endpoint bypasses JWT authentication (separate HTTPRoute) | Separate HTTPRoute without SecurityPolicy targeting confirmed as the standard pattern -- SecurityPolicy only applies to targeted routes |
| ENVOY-04 | Rate limiting uses Redis-backed global rate limit service | **Decision override**: CONTEXT.md explicitly chose local rate limiting (no Redis). Per-pod in-memory limits are acceptable because backend PostgreSQL quota is authoritative. This resolves the STATE.md Redis blocker |
| ENVOY-05 | `GET /users/me` returns plan usage data (request counts, limits) | Extend UserProfileResponse with `requests_used`, `monthly_limit`, `resets_at` -- data from `usage_monthly` + `plans` PostgreSQL tables |
</phase_requirements>

## Standard Stack

### Core
| Library/Tool | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Envoy Gateway | v1.7.1 | Kubernetes Gateway API implementation | Latest stable (2026-03-12), already deployed in cluster |
| Kubernetes Gateway API | v1.4.1 | Standard API for traffic routing | Compatible with Envoy Gateway v1.7 |
| Helm | v3.x | Kubernetes package manager | Standard for K8s app deployment |
| pogo-migrate | >=0.4.2 | SQL migrations | Already in project dev dependencies |
| SQLModel + asyncpg | existing | PostgreSQL ORM + driver | Already in project |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| SecurityPolicy CRD | v1alpha1 | JWT validation + claim extraction | Extract `plan` claim from Firebase JWT |
| BackendTrafficPolicy CRD | v1alpha1 | Local rate limiting per plan tier | Per-minute burst protection |
| HTTPRoute | v1 | Path-based routing | Separate webhook route from authenticated routes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Local rate limiting | Global rate limiting (Redis) | Global is more accurate across pods but adds Redis dependency -- deferred per user decision |
| Envoy response override | Custom Lua filter | responseOverride is declarative and simpler; Lua adds complexity |

## Architecture Patterns

### Recommended Project Structure
```
k8s/
  Chart.yaml           # Helm chart metadata (name: ns-api-gateway)
  values.yaml           # Configurable defaults (replicas, image, rate limits, quotas)
  templates/
    _helpers.tpl         # Helm template helpers (labels, selectors, fullname)
    deployment.yaml      # App Deployment
    service.yaml         # ClusterIP Service
    gateway.yaml         # Gateway resource (optional, may already exist)
    httproute-app.yaml   # HTTPRoute for /chats, /users, etc.
    httproute-webhooks.yaml  # HTTPRoute for /webhooks/apple (no JWT)
    httproute-health.yaml    # HTTPRoute for /health (no JWT, no rate limit)
    security-policy.yaml # SecurityPolicy (JWT + claimToHeaders)
    backend-traffic-policy.yaml  # BackendTrafficPolicy (local rate limiting)
    NOTES.txt            # Post-install notes
app/
  database/
    usage_db.py          # New: UsageDB (session-in-init pattern)
  models.py              # Add: Plan, UsageMonthly models
  exceptions.py          # Add: QuotaExceededError, rate_limited error code
migrations/
  YYYYMMDD_NN_xxxxx-add-plans-and-usage.sql  # New migration
```

### Pattern 1: Two-Layer Rate Limiting
**What:** Envoy Gateway provides coarse per-minute burst protection (local, per-pod). Backend PostgreSQL provides authoritative monthly quota enforcement.
**When to use:** When you need both fast edge rejection and accurate business-logic quota enforcement.
**Key insight:** Local rate limiting is per-pod. With 3 replicas and a free tier limit of 5/min, a user could theoretically get 15/min. This is acceptable because the monthly quota (150 total) is the real gate.

### Pattern 2: SecurityPolicy + claimToHeaders for Plan Extraction
**What:** Envoy Gateway SecurityPolicy validates Firebase JWT and extracts the `plan` claim into an `x-user-plan` request header forwarded to the backend.
**When to use:** When the backend needs claim-based routing or business logic without re-parsing the JWT.
**Example:**
```yaml
# Source: Envoy Gateway docs - JWT Authentication + API Reference
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: jwt-auth
  namespace: ns-api-gateway
spec:
  targetRefs:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: app-routes
  jwt:
    providers:
    - name: firebase
      issuer: "https://securetoken.google.com/PROJECT_ID"
      remoteJWKS:
        uri: "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
      claimToHeaders:
      - claim: plan
        header: x-user-plan
```

### Pattern 3: Local Rate Limiting with Per-Header Rules
**What:** BackendTrafficPolicy with local rate limiting uses `clientSelectors` to match `x-user-plan` header values and apply different limits per plan tier.
**When to use:** Per-tier rate limiting at the edge without external dependencies.
**Critical behavior:** When multiple rules exist, ALL matching rules apply independently with separate buckets. A rule without `clientSelectors` acts as a default/catch-all. When a request does not match any `clientSelector`, the rate limit for that rule does NOT apply to it.
**Example:**
```yaml
# Source: Envoy Gateway docs - Local Rate Limit
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: BackendTrafficPolicy
metadata:
  name: rate-limit-by-plan
  namespace: ns-api-gateway
spec:
  targetRefs:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: app-routes
  rateLimit:
    local:
      rules:
      # Default: if x-user-plan header is missing or unrecognized, use free tier
      - limit:
          requests: 5
          unit: Minute
      # Free tier
      - clientSelectors:
        - headers:
          - name: x-user-plan
            value: free
        limit:
          requests: 5
          unit: Minute
      # Silver tier
      - clientSelectors:
        - headers:
          - name: x-user-plan
            value: silver
        limit:
          requests: 50
          unit: Minute
      # Gold tier
      - clientSelectors:
        - headers:
          - name: x-user-plan
            value: gold
        limit:
          requests: 100
          unit: Minute
      # Platinum tier
      - clientSelectors:
        - headers:
          - name: x-user-plan
            value: platinum
        limit:
          requests: 1000
          unit: Minute
  responseOverride:
  - match:
      statusCodes:
      - type: Value
        value: 429
    response:
      contentType: application/json
      body:
        type: Inline
        inline: '{"code":"rate_limited"}'
```

### Pattern 4: Separate HTTPRoutes for Auth Bypass
**What:** Create separate HTTPRoute resources for endpoints that need different auth policies. Only attach SecurityPolicy to the route that requires JWT.
**When to use:** When webhook endpoints must be publicly accessible without JWT.
**Example:**
```yaml
# Webhook route - NO SecurityPolicy targets this
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: webhook-routes
  namespace: ns-api-gateway
spec:
  parentRefs:
  - name: eg-gateway
  rules:
  - matches:
    - path:
        type: Exact
        value: /webhooks/apple
      method: POST
    backendRefs:
    - name: ns-api-gateway
      port: 8000
---
# App route - SecurityPolicy + BackendTrafficPolicy target this
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: app-routes
  namespace: ns-api-gateway
spec:
  parentRefs:
  - name: eg-gateway
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /chats
    - path:
        type: PathPrefix
        value: /users
    - path:
        type: PathPrefix
        value: /examples
    backendRefs:
    - name: ns-api-gateway
      port: 8000
```

### Pattern 5: Atomic Check-and-Increment for Monthly Quota
**What:** Single SQL query that checks quota AND increments usage atomically, preventing race conditions on concurrent requests.
**When to use:** Any counter-based quota enforcement in PostgreSQL.
**Example:**
```sql
-- Atomic check-and-increment: returns 1 row if incremented, 0 if quota exceeded
UPDATE usage_monthly
SET used = used + 1
FROM plans
WHERE usage_monthly.user_id = :user_id
  AND usage_monthly.month = :month
  AND plans.tier = (SELECT plan FROM users WHERE id = :user_id)
  AND usage_monthly.used < plans.monthly_quota
RETURNING usage_monthly.used;
```

### Pattern 6: Lazy Row Creation for Usage Tracking
**What:** First LLM request of the month creates the `usage_monthly` row via INSERT ON CONFLICT, matching the existing JIT user provisioning pattern.
**When to use:** When usage rows are sparse and created on-demand.
**Example:**
```sql
INSERT INTO usage_monthly (user_id, month, used)
VALUES (:user_id, :month, 0)
ON CONFLICT (user_id, month) DO NOTHING;
```

### Anti-Patterns to Avoid
- **Application-level rate limiting (slowapi):** Envoy Gateway owns rate limiting. Do not add Python-level rate limiters.
- **Per-request Firebase claim reads:** Adds 100-300ms latency. JWT already carries the plan claim; Envoy extracts it.
- **Non-atomic quota checks:** Do NOT do `SELECT used ... if used < limit ... UPDATE used = used + 1`. Race condition under concurrent requests.
- **Global rate limiting without need:** Local per-pod rate limiting is explicitly acceptable here. Adding Redis is unnecessary complexity.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT validation at edge | Custom middleware | Envoy Gateway SecurityPolicy | Validated, performant, declarative |
| Claim extraction to headers | Custom Envoy filter | SecurityPolicy `claimToHeaders` | Built-in, zero code |
| Per-tier rate limiting | Python rate limiter (slowapi) | BackendTrafficPolicy local rate limiting | Edge enforcement, no app code |
| Custom 429 response body | Lua filter / custom filter | BackendTrafficPolicy `responseOverride` | Declarative, matches error contract |
| Helm chart from scratch | Raw K8s manifests | `helm create` scaffold + customize | Standard structure, helper templates |

**Key insight:** Envoy Gateway CRDs handle the entire edge layer declaratively. The app only needs to handle monthly quota enforcement (which requires DB access) and reading the `x-user-plan` header if needed.

## Common Pitfalls

### Pitfall 1: Local Rate Limit is Per-Pod
**What goes wrong:** Assuming the configured rate limit is global. With 3 pods and a 5/min limit, a user could theoretically get 15/min.
**Why it happens:** Misunderstanding local vs. global rate limiting.
**How to avoid:** Accept this by design. The backend monthly quota is the authoritative limit. Document clearly in values.yaml comments.
**Warning signs:** If a user exceeds the configured per-minute limit in total across pods.

### Pitfall 2: Default Rule Stacks with Header-Specific Rules
**What goes wrong:** A default rule (no clientSelectors) applies to ALL traffic including requests that ALSO match header-specific rules. Both rules' limits apply independently.
**Why it happens:** Envoy evaluates ALL matching rules, not first-match.
**How to avoid:** Make the default rule use the same limit as the most restrictive tier (free), so the overlap is harmless. A free user hits 5/min from both the default and free rule -- effectively still 5/min. A platinum user hits 5/min from default AND 1000/min from platinum, but the default is the binding constraint.
**Warning signs:** Platinum users getting 429 at 5 requests/minute.
**CRITICAL DECISION:** The default rule (catch-all for missing/unknown `x-user-plan` header) should NOT be more restrictive than the free tier. Actually, it SHOULD match the free tier exactly (5/min). But the stacking means platinum users would be limited to 5/min by the default rule. **Solution: Do NOT use a default rule. Only use per-header rules. Unknown/missing headers will simply not be rate-limited at the Envoy layer, which is fine because the backend quota is authoritative.**

### Pitfall 3: responseOverride on Wrong Resource
**What goes wrong:** Applying responseOverride on a BackendTrafficPolicy that targets the Gateway instead of the specific HTTPRoute, causing all 429 responses across all routes to be overridden.
**Why it happens:** BackendTrafficPolicy scopes to the targeted resource.
**How to avoid:** Target the specific HTTPRoute for LLM endpoints with both the rate limit and the response override.
**Warning signs:** Non-rate-limit 429 responses getting overridden.

### Pitfall 4: Forgetting to Roll Back Usage on LLM Failure
**What goes wrong:** User is "charged" for a request where the LLM call failed (circuit breaker, timeout).
**Why it happens:** Incrementing the counter before the LLM call and not rolling back on failure.
**How to avoid:** Use the existing transaction pattern: `get_db` dependency commits on success, rolls back on exception. If LLM call raises, the entire transaction (including the usage increment) rolls back.
**Warning signs:** Usage counter growing faster than actual successful requests.

### Pitfall 5: Webhook Route Accidentally Getting JWT/Rate Limiting
**What goes wrong:** SecurityPolicy or BackendTrafficPolicy targeting a Gateway applies to ALL routes including webhooks.
**Why it happens:** Policy precedence: gateway-level policies apply to all routes under that gateway.
**How to avoid:** Target SecurityPolicy and BackendTrafficPolicy at specific HTTPRoute resources, NOT at the Gateway. Keep webhook HTTPRoute separate and untargeted.
**Warning signs:** Apple webhook calls getting 401 or 429.

### Pitfall 6: Migration Dependency Chain
**What goes wrong:** New migration fails because pogo-migrate cannot find the dependency.
**Why it happens:** The `depends:` header must reference the exact filename ID of the previous migration.
**How to avoid:** The existing migration is `20260317_01_bvi4l-initial-release`. New migration must have `depends: 20260317_01_bvi4l-initial-release` in the header.
**Warning signs:** `pogo migrate apply` fails with dependency error.

### Pitfall 7: Error Contract Expansion -- _STATUS_REMAP Conflict
**What goes wrong:** The existing `_STATUS_REMAP` in `app/api/errors.py` maps 429 to 503. If the app returns 429 for quota exceeded, the error handler will remap it to 503.
**Why it happens:** The original error contract had only 5 status codes; 429 was mapped to 503.
**How to avoid:** Remove `429: 503` from `_STATUS_REMAP` and add `429: "rate_limited"` to `_CODE_MAP`. Add `rate_limited` to the `ErrorCode` Literal.
**Warning signs:** App returning 503 instead of 429 for quota exceeded.

## Code Examples

### UsageDB: Atomic Check-and-Increment (Claude's discretion)
```python
# Source: Project pattern (session-in-init from ChatsDB/SubscriptionDB)
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import text

class UsageDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def try_increment(self, user_id: UUID, month: str) -> bool:
        """Atomically increment usage if under quota. Returns True if allowed."""
        # Ensure row exists (lazy creation)
        await self.session.exec(text(
            "INSERT INTO usage_monthly (id, user_id, month, used) "
            "VALUES (:id, :user_id, :month, 0) "
            "ON CONFLICT (user_id, month) DO NOTHING"
        ), params={"id": uuid7(), "user_id": user_id, "month": month})

        # Atomic check-and-increment
        result = await self.session.exec(text(
            "UPDATE usage_monthly u "
            "SET used = u.used + 1 "
            "FROM plans p "
            "WHERE u.user_id = :user_id "
            "  AND u.month = :month "
            "  AND p.tier = (SELECT plan FROM users WHERE id = :user_id) "
            "  AND u.used < p.monthly_quota "
            "RETURNING u.used"
        ), params={"user_id": user_id, "month": month})
        return result.first() is not None

    async def get_usage(self, user_id: UUID, month: str) -> int:
        """Get current usage count for a user in a given month."""
        result = await self.session.exec(text(
            "SELECT used FROM usage_monthly "
            "WHERE user_id = :user_id AND month = :month"
        ), params={"user_id": user_id, "month": month})
        row = result.first()
        return row[0] if row else 0

    async def reset_usage(self, user_id: UUID, month: str) -> None:
        """Zero out usage counter (called on plan change)."""
        await self.session.exec(text(
            "UPDATE usage_monthly SET used = 0 "
            "WHERE user_id = :user_id AND month = :month"
        ), params={"user_id": user_id, "month": month})
```

### QuotaExceededError (extends error contract)
```python
# Source: Project pattern (app/exceptions.py)
# ErrorCode Literal must add "rate_limited"
ErrorCode = Literal["invalid_request",
                    "validation_error",
                    "unauthorized",
                    "not_found",
                    "service_unavailable",
                    "internal_error",
                    "rate_limited"]

class QuotaExceededError(ServiceError):
    status_code = 429
    error_code = "rate_limited"
```

### Plan and UsageMonthly Models
```python
# Source: Project pattern (app/models.py -- BaseTable, existing StrEnums)
class Plan(BaseTable, table=True):
    __tablename__ = "plans"

    tier: str = Field(primary_key=True, sa_type=Text())  # PlanTier value
    monthly_quota: int = Field()

class UsageMonthly(BaseTable, table=True):
    __tablename__ = "usage_monthly"
    __table_args__ = (
        UniqueConstraint("user_id", "month"),
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    month: str = Field(sa_type=Text())  # "YYYY-MM"
    used: int = Field(default=0)
```

### Migration SQL (plans + usage_monthly)
```sql
-- depends: 20260317_01_bvi4l-initial-release

-- migrate: apply

CREATE TABLE plans (
    tier TEXT PRIMARY KEY,
    monthly_quota INTEGER NOT NULL
);

INSERT INTO plans (tier, monthly_quota) VALUES
    ('free', 150),
    ('silver', 1500),
    ('gold', 3000),
    ('platinum', 30000);

CREATE TABLE usage_monthly (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, month)
);

CREATE INDEX ix_usage_monthly_user_month ON usage_monthly (user_id, month);

-- migrate: rollback

DROP TABLE IF EXISTS usage_monthly;
DROP TABLE IF EXISTS plans;
```

### Extended UserProfileResponse
```python
# Source: Project pattern (app/api/schema.py)
class UserProfileResponse(BaseModel):
    email: str
    name: str | None = None
    plan: str
    created_at: datetime
    # New usage fields (ENVOY-05)
    requests_used: int
    monthly_limit: int
    resets_at: datetime  # First of next month, ISO timestamp
```

### ChatService Quota Integration Point

```python
# In ChatService.create_chat() and ChatService.send_message(),
# before calling self.ask_llm():
from datetime import UTC, datetime
from exceptions import QuotaExceededError

month = datetime.now(UTC).strftime("%Y-%m")
allowed = await self.usage_db.try_increment(user_id, month)
if not allowed:
    raise QuotaExceededError("Monthly quota exceeded")
# If ask_llm() raises, the transaction rolls back (including the increment)
```

### Helm values.yaml Structure
```yaml
# k8s/values.yaml
replicaCount: 1
namespace: ns-api-gateway

image:
  repository: ""  # TBD
  tag: ""
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

container:
  port: 8000

resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: "1"
    memory: 512Mi

probes:
  readiness:
    path: /health/ready
    port: 8000
  liveness:
    path: /health/ready
    port: 8000

gateway:
  name: eg-gateway  # Existing Envoy Gateway resource name

jwt:
  issuer: ""  # https://securetoken.google.com/PROJECT_ID
  jwksUri: "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"

rateLimits:
  burst:
    free: 5
    silver: 50
    gold: 100
    platinum: 1000
    unit: Minute
  monthly:
    free: 150
    silver: 1500
    gold: 3000
    platinum: 30000
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global rate limiting (Redis required) | Local rate limiting (no external deps) | Envoy Gateway v1.0+ | Simpler deployment, per-pod limits acceptable when backend is authoritative |
| Ingress + custom annotations | Gateway API + CRDs (SecurityPolicy, BackendTrafficPolicy) | Kubernetes Gateway API GA (2023) | Standardized, portable, richer policy model |
| Application-level rate limiting | Edge rate limiting + backend quota | Current best practice | Separation of concerns, lower latency rejections |
| `targetRef` (singular) | `targetRefs` (plural, array) | Envoy Gateway v1.1+ | Multiple targets per policy |

**Deprecated/outdated:**
- Envoy Gateway `v1alpha1` API is still current as of v1.7.1 -- has not graduated to v1beta1 yet
- `targetRef` (singular) still works but `targetRefs` (plural) is preferred

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 + pytest-asyncio >=1.3 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/unit/ -x -q` |
| Full suite command | `pytest tests/unit/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENVOY-01 | JWT plan claim extracted to x-user-plan header | manual-only | N/A (requires live Envoy Gateway) | N/A |
| ENVOY-02 | Per-user rate limits by plan tier at edge | manual-only | N/A (requires live Envoy Gateway) | N/A |
| ENVOY-03 | Webhook bypasses JWT authentication | manual-only | N/A (requires live Envoy Gateway) | N/A |
| ENVOY-04 | Rate limiting uses local (not Redis) | manual-only | N/A (infrastructure config) | N/A |
| ENVOY-05 | GET /users/me returns usage data | unit | `pytest tests/unit/test_users.py -x` | Exists (extend) |
| -- | QuotaExceededError returns 429 | unit | `pytest tests/unit/test_error_contract.py -x` | Exists (extend) |
| -- | Atomic quota check-and-increment | unit | `pytest tests/unit/test_usage.py -x` | Wave 0 |
| -- | ChatService rejects when quota exceeded | unit | `pytest tests/unit/test_services.py -x` | Exists (extend) |
| -- | Usage zeroed on plan change | unit | `pytest tests/unit/test_subscriptions.py -x` | Exists (extend) |
| -- | Helm chart renders valid YAML | unit | `helm template k8s/ --values k8s/values.yaml` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/ -x -q`
- **Per wave merge:** `pytest tests/unit/ -v`
- **Phase gate:** Full suite green + `helm template` renders without errors

### Wave 0 Gaps
- [ ] `tests/unit/test_usage.py` -- covers quota check-and-increment, lazy row creation, usage reset
- [ ] Helm template validation via `helm template` command (no test file needed, use CLI)

## Open Questions

1. **Envoy Gateway name in cluster**
   - What we know: Chart assumes an existing Gateway resource. The name used in HTTPRoute `parentRefs` must match.
   - What's unclear: The exact name of the Gateway resource in the cluster.
   - Recommendation: Make configurable in `values.yaml` as `gateway.name` (default: `eg-gateway`).

2. **Default rule stacking behavior**
   - What we know: All matching rules apply independently. A default rule (no clientSelectors) applies to ALL requests.
   - What's unclear: Whether a request matching a specific plan tier rule will ALSO be limited by the default rule.
   - Recommendation: Based on Envoy proxy documentation ("all matched descriptors are sorted by tokens per second"), YES both apply. **Do NOT add a default rule.** Only use per-header rules. Unmatched requests (no/unknown header) bypass Envoy rate limiting, which is fine since backend quota is authoritative. Alternatively, treat unknown headers at the backend level.

3. **Firebase JWKS URL format for Envoy Gateway**
   - What we know: Firebase JWKS is at `https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com` (JWK format) or `https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com` (x509 format).
   - What's unclear: Whether Envoy Gateway's `remoteJWKS.uri` expects JWK or x509 format.
   - Recommendation: Use the JWK format URL (`/jwk/`) as that is the standard JWKS format. The x509 URL returns certificates, not a JWKS. Verify during deployment.

## Sources

### Primary (HIGH confidence)
- [Envoy Gateway GitHub Releases](https://github.com/envoyproxy/gateway/releases) - v1.7.1 confirmed as latest stable (2026-03-12)
- [Envoy Gateway Compatibility Matrix](https://gateway.envoyproxy.io/news/releases/matrix/) - v1.7 with Gateway API v1.4.1
- [Envoy Gateway Local Rate Limit docs](https://gateway.envoyproxy.io/docs/tasks/traffic/local-rate-limit/) - BackendTrafficPolicy YAML, clientSelectors, per-header rules
- [Envoy Gateway JWT Authentication docs](https://gateway.envoyproxy.io/docs/tasks/security/jwt-authentication/) - SecurityPolicy YAML, JWT providers
- [Envoy Gateway API Reference](https://gateway.envoyproxy.io/docs/api/extension_types/) - claimToHeaders field confirmed
- [Envoy Gateway Response Override docs](https://gateway.envoyproxy.io/docs/tasks/traffic/response-override/) - responseOverride YAML for custom 429 body
- [Envoy Proxy Local Rate Limit Filter](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/local_rate_limit_filter) - All-match behavior confirmed

### Secondary (MEDIUM confidence)
- [Envoy Gateway SecurityPolicy Concept](https://gateway.envoyproxy.io/docs/concepts/gateway_api_extensions/security-policy/) - Policy targeting and precedence
- [Envoy Gateway BackendTrafficPolicy Concept](https://gateway.envoyproxy.io/docs/concepts/gateway_api_extensions/backend-traffic-policy/) - Policy merging, precedence rules
- [Envoy Gateway Rate Limiting Concepts](https://gateway.envoyproxy.io/docs/concepts/rate-limiting/) - Local vs. global explanation
- [Kubernetes Gateway API HTTPRoute](https://gateway-api.sigs.k8s.io/api-types/httproute/) - HTTPRoute spec, path matching

### Tertiary (LOW confidence)
- [Envoy Gateway Rate Limit Design Doc](https://gateway.envoyproxy.io/contributions/design/rate-limit/) - Older design doc, local rate limiting noted as "future" but now implemented; used for understanding rule evaluation semantics

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions verified against GitHub releases and compatibility matrix
- Architecture (Envoy patterns): HIGH - YAML examples verified against official Envoy Gateway docs
- Architecture (backend quota): HIGH - follows established project patterns (session-in-init, INSERT ON CONFLICT, transaction rollback)
- Architecture (Helm chart): MEDIUM - standard Helm patterns, but chart structure is Claude's discretion
- Pitfalls: HIGH - verified through official docs (rule stacking, per-pod behavior, response override)
- Code examples: MEDIUM - follow project conventions but exact SQL/signatures are Claude's discretion

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (Envoy Gateway is stable; no expected breaking changes in 30 days)
