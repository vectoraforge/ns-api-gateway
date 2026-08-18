# Phase 26: Service and Database Rewiring - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-23
**Phase:** 26-service-and-database-rewiring
**Areas discussed:** Quota config threading, User plan passing, /users/me rewrite

---

## Quota Config Threading

| Option | Description | Selected |
|--------|-------------|----------|
| QuotaConfig in constructor | dependencies.py passes config.quotas (QuotaConfig) to ChatService constructor | |
| Resolved int per method call | Router resolves quota integer and passes it to create_chat/send_message each time | |
| Remove QuotaConfig, use dict | Drop QuotaConfig model, use bare dict[SubscriptionPlan, int] on AppConfig, pass to ChatService constructor | ✓ |

**User's choice:** Remove QuotaConfig model entirely, use `dict[SubscriptionPlan, int]` as the config type, pass to ChatService constructor
**Notes:** User proactively chose to simplify beyond the presented options — removing the Pydantic wrapper model in favor of a bare dict. This loses the exhaustiveness model_validator but is simpler.

---

## User Plan Passing

| Option | Description | Selected |
|--------|-------------|----------|
| subscription_plan param | Add SubscriptionPlan parameter to create_chat and send_message | |
| Pass full User object | Replace user_id with User in method signatures | ✓ |

**User's choice:** Pass full User object
**Notes:** Cleaner API — access to both user.id and user.subscription_plan from one object. No extra DB query needed since routers already have User from Depends(get_current_user).

---

## /users/me Rewrite

| Option | Description | Selected |
|--------|-------------|----------|
| Depends(get_config) | Add config: AppConfig = Depends(get_config) to handler | ✓ |
| Dedicated quota dependency | New get_quota(user, config) dependency returning resolved int | |

**User's choice:** Depends(get_config)
**Notes:** Consistent with how other service factories access config. Simple one-line addition.

---

## Claude's Discretion

- SQL rewrite approach for try_increment
- Whether UsageDB.get_usage signature changes
- Import cleanup after QuotaConfig removal

## Deferred Ideas

None — discussion stayed within phase scope.
