---
phase: 23
reviewers: [gemini, codex]
reviewed_at: 2026-03-22T00:00:00Z
plans_reviewed: [23-01-PLAN.md, 23-02-PLAN.md, 23-03-PLAN.md, 23-04-PLAN.md]
---

# Cross-AI Plan Review — Phase 23

## Gemini Review

This review covers the implementation plans for **Phase 23: Envoy Gateway Rate Limiting**.

### 1. Summary
The plan provides a robust, multi-layered approach to rate limiting that correctly distinguishes between infrastructure-level burst protection (Envoy) and application-level quota management (PostgreSQL). The use of atomic SQL updates for quota enforcement is a highlight, ensuring data integrity without the overhead of distributed locking. The Helm chart configuration is well-structured, leveraging modern Envoy Gateway CRDs (`SecurityPolicy`, `BackendTrafficPolicy`) to handle JWT claim extraction and tier-based limits. However, there is a significant performance risk regarding database connection lifecycle management during long-running LLM calls.

### 2. Strengths
- **Atomic Quota Management:** The `INSERT ON CONFLICT + UPDATE ... WHERE used < quota` pattern in `UsageDB` is the gold standard for thread-safe, performant quota tracking in PostgreSQL.
- **Modern Envoy Integration:** Using `claimToHeaders` in `SecurityPolicy` to map JWT claims to internal headers is the idiomatic way to implement "tier-aware" infrastructure.
- **Clean Separation of Concerns:** Routing `/webhooks` and `/health` to separate `HTTPRoutes` ensures they bypass security policies without complex regex exclusions.
- **Opaque Error Consistency:** Mapping Envoy's 429 response body to match the backend's `rate_limited` error code maintains a consistent API contract for frontend consumers.

### 3. Concerns

- **DB Connection Exhaustion (HIGH):**
  Plan 23-02 suggests performing `try_increment` within a transaction that rolls back if `ask_llm` fails. Because LLM calls are high-latency (often seconds), holding a database connection open for the duration of the `ask_llm` call will rapidly exhaust the connection pool under even moderate load.
- **Envoy Header Spoofing (MEDIUM):**
  While Envoy extracts the `plan` claim to `x-user-plan`, the plan doesn't explicitly mention stripping `x-user-plan` if it is provided by the client. An attacker could potentially bypass limits by manually injecting a `Gold` header if the `SecurityPolicy` doesn't strictly override or sanitize incoming headers.
- **Timezone Ambiguity (LOW):**
  The `resets_at` logic (first of next month) needs to be strictly UTC to avoid "double-reset" windows or premature resets for users in different time zones. The plan should specify `datetime.now(UTC)`.
- **Tier Downgrade Edge Case (LOW):**
  When a user changes tiers, the plan zeroes the usage. If a user consumes their `Gold` quota and then "downgrades" to `Free`, they technically get a fresh start. While acceptable for a v1.5, it's a potential exploit vector for "resetting" usage.

### 4. Suggestions

- **Optimize Connection Lifecycle:** Instead of holding a transaction during the LLM call, use a "Commit-then-Compensate" pattern:
  1. **Commit:** `try_increment` usage in its own short-lived transaction.
  2. **Act:** Call `ask_llm`.
  3. **Compensate:** If `ask_llm` fails with a transient error, run a `decrement_usage` call in a new transaction.
- **Header Sanitization:** Ensure the `SecurityPolicy` or a `URLRewrite` filter in Envoy explicitly removes any client-provided `x-user-plan` headers before the JWT extraction logic runs.
- **Validation of `month` format:** In `UsageMonthly`, enforce a strict `YYYY-MM` string format to ensure the `UNIQUE(user_id, month)` constraint works reliably across year boundaries.
- **Envoy Local Limits:** Note in the documentation that since rate limiting is local (per-pod), the effective burst limit is `burst_value * number_of_replicas`.

### 5. Risk Assessment
**Risk Level: MEDIUM**

The architectural split between Envoy and the Backend is sound. The primary risk is **operational**: the current plan to wrap LLM calls in a DB transaction will likely lead to service-wide 503/504 errors (connection timeouts) under load. If the connection lifecycle is optimized as suggested, the risk drops to **LOW**. The security model for JWT extraction is standard, and the migration/model changes are straightforward and well-tested.

---

## Codex Review

## Plan 23-01: Backend foundation

**Summary**

This is the right foundation for Phase 23: it introduces the quota data model, extends the error contract, and adds the response fields needed for `GET /users/me`. The main risk is that the plan mixes core rate-limiting groundwork with unrelated rename/versioning work, and it leaves some important schema and transactional details implicit. The success of later waves depends heavily on the exact correctness of `UsageDB.try_increment`, so that part needs tighter specification.

**Strengths**

- Introduces the minimum backend primitives needed for monthly quota enforcement.
- Expands the public error contract to support `429` and `rate_limited`, which aligns with the milestone.
- Adds explicit usage fields to `UserProfileResponse`, directly covering ENVOY-05.
- Uses a dedicated `UsageDB` abstraction instead of scattering quota logic through services.
- Recognizes the need for seeded plan metadata in the database rather than hardcoding quotas only in app code.

**Concerns**

- **HIGH**: `UsageMonthly` as `(user_id, month, used)` plus separate `Plan.monthly_quota` does not explain how user tier is joined at enforcement time. If quota lookup depends on current subscription state, historical usage rows for a month can become ambiguous after a tier change.
- **HIGH**: "Atomic INSERT ON CONFLICT + UPDATE WHERE used < quota RETURNING" is directionally correct, but the exact SQL shape matters. If quota is read in a separate query, the operation is no longer fully atomic.
- **HIGH**: The plan says tier change zeroes usage, but the schema does not say whether usage is tied only to `(user_id, month)` or also to plan/tier version. Reset semantics need to be explicit or later behavior will be inconsistent.
- **MEDIUM**: `month TEXT` is underspecified. Text keys are easy to misuse (`2026-3` vs `2026-03`, timezone edge cases). A date/month anchor would be safer.
- **MEDIUM**: `resets_at` is added to the response, but timezone semantics are not specified. Since quotas are "calendar month", the reset boundary must be defined consistently.
- **MEDIUM**: Removing `429: 503` from `_STATUS_REMAP` may be right, but the plan does not confirm whether any existing opaque-error behavior depends on remapping unknown 4xx/5xx statuses.
- **LOW**: Project/package rename and title changes are unrelated to rate limiting and add avoidable migration risk in the same wave.

**Suggestions**

- Specify `UsageDB.try_increment` as a single statement or single transaction that both resolves the user's effective quota and conditionally increments usage.
- Prefer `month_start DATE` or equivalent normalized month key instead of free-form `TEXT`.
- Define the authoritative source for the user's current plan during quota checks: subscription table, user profile column, or joined plan table.
- Make tier-change semantics explicit in schema/logic: either reset the current month row in place or recreate it deterministically.
- Separate rename/version changes from quota foundation unless they are already required by another committed milestone.
- Add a migration constraint/checks for non-negative `used` and valid quota values.

**Risk Assessment**

**MEDIUM** -- The plan is conceptually sound, but the atomic enforcement path and tier-change semantics are not specified tightly enough. Those are correctness-critical for the backend-authoritative quota model.

---

## Plan 23-02: Backend integration

**Summary**

This plan connects the backend quota mechanism to the actual write-paths and exposes usage in `/users/me`, which is necessary for the feature to be user-visible. The broad direction is correct, but it currently treats quota as a simple pre-check in `ChatService` without enough attention to rollback guarantees, endpoint coverage, and consistency with the stated "failed LLM calls roll back usage increment via transaction rollback" requirement.

**Strengths**

- Applies quota checks at the service layer for the two LLM endpoints, matching the design decision that only those routes are quota-controlled.
- Puts the quota check before `ask_llm`, which avoids unnecessary model calls when already over quota.
- Resets usage on plan change in `SubscriptionService`, matching the stated product rule.
- Adds targeted unit coverage for quota rejection and `/users/me` response changes.
- Updates contract tests for `429`/`rate_limited`, which protects the API surface.

**Concerns**

- **HIGH**: "try_increment before `ask_llm`" is not enough to satisfy "failed LLM calls roll back usage increment via transaction rollback" unless the increment and the rest of chat creation/message persistence are guaranteed to share the same database transaction boundary.
- **HIGH**: If `ask_llm` is an external network call, holding an open DB transaction across that call can be expensive and failure-prone. The plan does not address that tradeoff.
- **HIGH**: Only `POST /chats` and `POST /chats/{id}` are supposed to be quota-limited. The plan references `create_chat` and `send_message`, but it should verify there are no alternate LLM-invoking paths that bypass these methods.
- **MEDIUM**: Constructing `UsageDB(db)` directly inside services continues the existing pattern, but it weakens centralized DI and makes testing/mocking less clean than injecting the dependency.
- **MEDIUM**: `get_usage + get_monthly_limit` in `/users/me` risks inconsistency if plan changes between calls. Not severe, but avoidable with a combined query or service method.
- **MEDIUM**: Unit tests listed are useful, but there is no explicit test for "failed LLM call does not consume usage".
- **MEDIUM**: Resetting usage in `if old_tier != plan_tier` may be correct for subscription changes, but it can be dangerous if webhook processing is retried/idempotency is imperfect.
- **LOW**: Patching `UsageDB` in router tests verifies shape, but misses integration-level assurance that usage values come from the actual DB queries.

**Suggestions**

- Specify the exact transaction strategy for quota increment + chat/message persistence + rollback on LLM failure.
- Add a test for failed `ask_llm` ensuring usage is not consumed.
- Add a test for plan change reset behavior, especially around idempotent/replayed subscription events.
- Prefer injecting a quota service or `UsageDB` through DI rather than constructing it ad hoc in multiple places.
- Consider a single service method for `/users/me` that returns `used`, `limit`, and `resets_at` consistently.
- Confirm that every LLM-consuming path is routed through the quota-checked service methods.

**Risk Assessment**

**MEDIUM-HIGH** -- This wave is where quota correctness becomes real. If transaction boundaries are wrong, users will either lose quota on failed calls or bypass quota unintentionally.

---

## Plan 23-03: Helm chart

**Summary**

This plan covers the infrastructure side of the milestone well: route separation, JWT enforcement, header extraction, and tier-based edge rate limiting are all present and aligned with the design. The main risks are Envoy Gateway API correctness, especially around whether `BackendTrafficPolicy` can actually express the intended per-user-per-plan behavior using `x-user-plan` alone, and whether the LLM route matching is precise enough to include both required endpoints without accidentally rate-limiting more traffic than intended.

**Strengths**

- Cleanly separates app, LLM, webhook, and health traffic into different `HTTPRoute`s.
- Explicitly keeps JWT off the webhook route, which matches ENVOY-03.
- Applies SecurityPolicy to both normal and LLM routes, which is necessary for claim extraction and auth continuity.
- Intentionally avoids a default rate limit rule, matching the stated design decision.
- Keeps rate limiting local/per-pod and leaves monthly quota to PostgreSQL, which fits the two-layer model.
- Includes a custom 429 response body, which helps maintain a consistent client experience.

**Concerns**

- **HIGH**: The plan says "per-user rate limits differ by plan tier", but the proposed rate-limit rules only mention `clientSelector` on `x-user-plan`. Plan alone is not per-user; that enforces per-tier buckets, not per-user-per-tier, unless another unique identity descriptor is also part of the rate-limit key.
- **HIGH**: Requirements say only `POST /chats` and `POST /chats/{id}` are rate-limited, but the plan only explicitly lists `POST /chats`. `POST /chats/{id}` may be missed.
- **HIGH**: Envoy Gateway feature support is version-sensitive. The plan assumes `claimToHeaders`, local rate limiting, and header-based matching all work together as described, but does not pin or validate against the chart's target Envoy Gateway API version.
- **MEDIUM**: If unknown/missing `x-user-plan` bypasses Envoy by design, then malformed JWTs or unexpected plan values shift all protection to the backend. That is acceptable only if backend quota enforcement is guaranteed on all LLM paths.
- **MEDIUM**: Separate `app-routes` and `llm-routes` can create route precedence ambiguity if path/method matches overlap and the Gateway implementation resolves them unexpectedly.
- **MEDIUM**: Returning a JSON 429 from Envoy may not fully match the backend opaque error contract unless headers/body structure are intentionally mirrored.
- **LOW**: Putting monthly quotas in `values.yaml` may create configuration drift if the backend database remains the true source of monthly limits.

**Suggestions**

- Rework the rate-limit design so the local Envoy bucket key includes user identity, not just plan. If JWT claim extraction can also forward user ID, use both user ID and plan.
- Ensure the LLM route set explicitly matches both `POST /chats` and `POST /chats/{id}`.
- Validate the design against the exact Envoy Gateway CRD version before implementation.
- Document expected behavior for unknown plan values so operations teams understand that Envoy may bypass while backend quota remains authoritative.
- Keep monthly quota configuration out of Helm unless it is actually needed there; otherwise only burst limits belong at the edge.
- Add at least one deployment/integration test step that proves webhook bypass, JWT enforcement, and differentiated limits by tier.

**Risk Assessment**

**HIGH** -- This plan is close to the goal but may fail the core requirement if rate limiting keys only on plan instead of user identity. That would materially change behavior from "per-user by plan tier" to "shared per-tier bucket".

---

## Plan 23-04: Gap closure

**Summary**

This is a narrow cleanup plan focused on rename fallout. It is reasonable as a small follow-up, but it is not materially part of Phase 23 rate limiting and introduces packaging churn into a milestone that already has enough moving parts.

**Strengths**

- Identifies likely leftover rename artifacts in a concrete file.
- Keeps the scope intentionally small.
- Recognizes that package metadata lookup needs to match the renamed distribution name.

**Concerns**

- **MEDIUM**: Running `uv pip install -e .` is environment/setup work, not implementation plan content, and may not belong in an autonomous code wave.
- **MEDIUM**: Rename cleanup is orthogonal to the phase goal and can distract from validating rate-limiting behavior.
- **LOW**: There may be rename references outside `root.py`; this plan assumes a single-file fix.

**Suggestions**

- Treat this as optional cleanup unless broken metadata/version reporting is actively blocking the release.
- Search for all `sn-api-gateway` and "SpeakNative" references before limiting the scope to one file.
- Keep this wave independent so it cannot delay Phase 23 validation.

**Risk Assessment**

**LOW** -- The technical risk is small, but the value-to-risk ratio is also low because it does not advance the actual feature.

---

## Consensus Summary

### Agreed Strengths
- **Atomic quota enforcement pattern** -- Both reviewers praise the `INSERT ON CONFLICT + UPDATE WHERE used < quota RETURNING` approach as the correct solution for concurrent quota tracking
- **Clean HTTPRoute separation** -- Both approve separating webhook, health, app, and LLM routes into distinct HTTPRoutes for proper policy targeting
- **Two-layer rate limiting model** -- Both confirm the Envoy burst + PostgreSQL monthly quota architecture is sound in concept
- **Error contract consistency** -- Both note the 429/rate_limited expansion and Envoy responseOverride alignment as well-designed

### Agreed Concerns
- **DB connection exhaustion during LLM calls (HIGH)** -- Both flag that holding a database transaction open across `ask_llm` (which can take seconds) will exhaust the connection pool under load. Gemini suggests "commit-then-compensate", Codex calls for explicit transaction scope specification.
- **Transaction rollback semantics underspecified (HIGH)** -- Both identify that "failed LLM calls roll back usage increment" requires the quota increment and LLM call to share a transaction boundary, which conflicts with the connection exhaustion concern. The plan must explicitly resolve this tension.
- **Timezone/month format ambiguity (MEDIUM)** -- Both note that `month TEXT` and `resets_at` need explicit UTC semantics to avoid edge cases across time zones and year boundaries.
- **Rename work mixed into rate limiting phase (LOW-MEDIUM)** -- Both suggest the rename (23-01 Task 2 + 23-04) is orthogonal to the phase goal and adds avoidable risk.

### Divergent Views
- **Per-user vs per-tier rate limiting (Codex HIGH, Gemini silent)**: Codex raises a critical concern that Envoy's clientSelectors on `x-user-plan` alone creates shared per-tier buckets, not per-user limits. Gemini does not flag this. Codex recommends adding user identity to the rate limit key.
- **Header spoofing (Gemini MEDIUM, Codex silent)**: Gemini flags potential `x-user-plan` header injection by clients if Envoy doesn't strip client-provided headers before JWT extraction. Codex does not mention this.
- **Overall risk**: Gemini rates MEDIUM overall, Codex rates MEDIUM-HIGH. The divergence centers on whether the Envoy rate-limit keying model actually satisfies the per-user requirement.
