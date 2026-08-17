# Phase 26: Service and Database Rewiring - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Quota enforcement reads from configuration instead of the plans table. Rewrite UsageDB, ChatService, and GET /users/me so no query JOINs `core.plans`. No migration DDL (Phase 27), no test updates (Phase 28).

</domain>

<decisions>
## Implementation Decisions

### Quota Config Model
- **D-01:** Remove `QuotaConfig` Pydantic model entirely — replace with bare `dict[SubscriptionPlan, int]` as the config type on `AppConfig.quotas`
- **D-02:** Move or drop the exhaustiveness validator (`model_validator` that checks all SubscriptionPlan members have entries) — future requirement QUOTA-06 may reintroduce it at `AppConfig` level

### Quota Config Threading
- **D-03:** Pass `quotas: dict[SubscriptionPlan, int]` to ChatService constructor via `dependencies.py`, following the established pattern for `examples`, `chats_limit`, `messages_limit`

### User Plan Passing
- **D-04:** Replace `user_id: UUID` with `user: User` in ChatService method signatures (`create_chat`, `send_message`) — router already has `User` from `Depends(get_current_user)`
- **D-05:** ChatService resolves quota internally: `self.quotas[user.subscription_plan]` then passes integer to `UsageDB.try_increment`

### UsageDB Rewrite
- **D-06:** `UsageDB.try_increment` gains a `monthly_quota: int` parameter — SQL rewritten to use the parameter instead of JOINing `plans`
- **D-07:** `UsageDB.get_monthly_limit` deleted entirely (QUOTA-04)

### /users/me Rewrite
- **D-08:** Add `config: AppConfig = Depends(get_config)` to the `/users/me` handler — resolve `monthly_limit = config.quotas[user.subscription_plan]`
- **D-09:** Remove `UsageDB.get_monthly_limit` call — replaced by config lookup

### Claude's Discretion
- SQL rewrite approach for `try_increment` (parameterized comparison vs CTE) — as long as no JOIN to `core.plans`
- Whether `UsageDB.get_usage` signature changes (currently takes `user_id` — may stay since it doesn't involve quota)
- Import cleanup after QuotaConfig removal

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Service Layer
- `src/nativespeaker/api/database/usage.py` — UsageDB class with try_increment (JOIN to rewrite), get_monthly_limit (to delete), get_usage, reset_usage
- `src/nativespeaker/api/services/chats.py` — ChatService with create_chat/send_message that call try_increment
- `src/nativespeaker/api/app/dependencies.py` — get_chat_service factory, get_config dependency

### Config and Models
- `src/nativespeaker/api/config.py` — QuotaConfig model to remove, AppConfig.quotas field to simplify
- `src/nativespeaker/api/models.py` — User model (subscription_plan field), SubscriptionPlan enum

### Routers
- `src/nativespeaker/api/routers/users.py` — GET /users/me handler that calls get_monthly_limit
- `src/nativespeaker/api/routers/chats.py` — Chat routers that pass user.id to ChatService methods

### Requirements
- `.planning/REQUIREMENTS.md` — QUOTA-03, QUOTA-04

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_config` dependency in `dependencies.py:15` — already returns `AppConfig`, reusable in users router
- `AppConfig` already has `quotas: QuotaConfig` field — simplify to `dict[SubscriptionPlan, int]`
- `UsageDB.get_usage` and `UsageDB.reset_usage` — no plans JOIN, stay as-is

### Established Patterns
- Constructor injection via `dependencies.py` — ChatService receives config fields, not raw config
- Session-in-init for DB classes — `UsageDB(session)` pattern unchanged
- `Depends(get_current_user)` returns full `User` object — subscription_plan already available in routers

### Integration Points
- `dependencies.py:get_chat_service` — add `quotas=config.quotas` kwarg
- `ChatService.__init__` — add `quotas: dict[SubscriptionPlan, int]` param
- `ChatService.create_chat` / `send_message` — change `user_id: UUID` to `user: User`
- Chat routers — change `user.id` to `user` in service calls
- `routers/users.py:get_me` — add `config` dependency, remove `get_monthly_limit` call

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose to remove QuotaConfig model in favor of bare dict — simpler, less ceremony
- User chose full User object over subscription_plan param — cleaner API, access to user.id and user.subscription_plan from one object
- User chose Depends(get_config) for /users/me — consistent with how other service factories access config

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 26-service-and-database-rewiring*
*Context gathered: 2026-03-23*
