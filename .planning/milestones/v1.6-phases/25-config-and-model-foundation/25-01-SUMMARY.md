---
phase: 25-config-and-model-foundation
plan: 01
subsystem: api
tags: [pydantic, sqlmodel, strenum, config, enum-rename]

requires:
  - phase: none
    provides: baseline models.py, config.py, schema.py, config.yaml
provides:
  - ChatRole and SubscriptionPlan enum classes (renamed from Role and Tier)
  - QuotaConfig Pydantic model with exhaustiveness validator
  - AppConfig.quotas field for config-driven quota lookup
  - AppleConfig.product_id_to_plan with SubscriptionPlan type
  - UserProfileResponse.subscription_plan with SubscriptionPlan type
  - Plan SQLModel class deleted, FK references removed
  - Message.__tablename__ fixed to "messages"
affects: [25-02, 26-query-rewrites, 27-migration, 28-test-updates]

tech-stack:
  added: []
  patterns:
    - "Deferred annotation resolution via __future__.annotations + model_rebuild() for circular import"
    - "Pydantic model_validator(mode='after') for enum exhaustiveness checking"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/models.py
    - src/nativespeaker/api/config.py
    - src/nativespeaker/api/schema.py
    - config/config.yaml

key-decisions:
  - "Used from __future__ import annotations + model_rebuild(_types_namespace=...) to break schema<->models circular import"
  - "QuotaConfig placed between JWTConfig and AppleConfig in config.py"

patterns-established:
  - "Circular import resolution: from __future__ import annotations in schema.py, model_rebuild() in models.py bottom"

requirements-completed: [QUOTA-01, QUOTA-02, QUOTA-05, ENUM-01, ENUM-02, ENUM-03, ENUM-04, ENUM-05, SCHEMA-02]

duration: 7min
completed: 2026-03-23
---

# Phase 25 Plan 01: Config and Model Foundation Summary

**Renamed enums (Role->ChatRole, Tier->SubscriptionPlan), narrowed model fields to StrEnum types, deleted Plan model, added config-driven QuotaConfig with exhaustiveness validator**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-23T21:57:19Z
- **Completed:** 2026-03-23T22:04:52Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Renamed Role to ChatRole and Tier to SubscriptionPlan across all model references
- Narrowed User.subscription_plan, Subscription.plan, SubscriptionEvent.old_plan/new_plan to SubscriptionPlan type
- Deleted Plan SQLModel class and removed all foreign_key="core.plans.tier" references
- Fixed Message.__tablename__ from "core.messages" to "messages"
- Added QuotaConfig with dict[SubscriptionPlan, int] and model_validator exhaustiveness check
- Renamed AppleConfig.product_id_to_tier to product_id_to_plan with SubscriptionPlan value type
- Added quotas section to config.yaml with free:10, silver:50, gold:200, platinum:1000
- Renamed UserProfileResponse.plan to subscription_plan with SubscriptionPlan type

## Task Commits

Each task was committed atomically:

1. **Task 1: Rename enums, narrow model fields, delete Plan, fix tablename** - `2ef2c93` (feat)
2. **Task 2: Add QuotaConfig, update AppleConfig, update config.yaml** - `9243260` (feat)
3. **Task 3: Update UserProfileResponse in schema.py** - `a97d589` (feat)

## Files Created/Modified
- `src/nativespeaker/api/models.py` - Renamed enums, narrowed field types, deleted Plan class, fixed Message tablename, added model_rebuild for circular import
- `src/nativespeaker/api/config.py` - Added QuotaConfig class, renamed AppleConfig field, added quotas to AppConfig, imported SubscriptionPlan
- `src/nativespeaker/api/schema.py` - Renamed plan to subscription_plan with SubscriptionPlan type, added future annotations
- `config/config.yaml` - Added quotas.tiers section, renamed product_id_to_tier to product_id_to_plan

## Decisions Made
- Used `from __future__ import annotations` in schema.py combined with `model_rebuild(_types_namespace={'SubscriptionPlan': SubscriptionPlan})` at the bottom of models.py to resolve the circular import between schema.py (which imports Issue from models.py) and the new SubscriptionPlan reference in UserProfileResponse. This pattern defers annotation evaluation until model_rebuild is called.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Resolved circular import between schema.py and models.py**
- **Found during:** Task 3 (Update UserProfileResponse)
- **Issue:** Plan stated the import was safe, but adding `from nativespeaker.api.models import SubscriptionPlan` to schema.py caused a circular import because models.py imports Issue from schema.py
- **Fix:** Used `from __future__ import annotations` in schema.py for deferred annotation evaluation, then called `UserProfileResponse.model_rebuild(_types_namespace=...)` at the bottom of models.py after SubscriptionPlan is defined
- **Files modified:** src/nativespeaker/api/schema.py, src/nativespeaker/api/models.py
- **Verification:** Both import orders verified (schema-first and models-first)
- **Committed in:** a97d589 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Circular import fix was necessary for correctness. The approach uses standard Pydantic v2 patterns. No scope creep.

## Issues Encountered
None beyond the circular import deviation documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All enum and model definitions are final for downstream use
- QuotaConfig ready for Phase 26 query rewrites (UsageDB will read quotas from config instead of JOINing plans)
- Field renames (subscription_plan, old_plan/new_plan, product_id_to_plan) ready for Phase 25-02 service layer updates
- Note: downstream service/database files still reference old names (Role, Tier, plan_tier, etc.) -- Phase 25-02 handles those renames

## Self-Check: PASSED

All 4 modified files exist. All 3 task commits verified. SUMMARY.md created. No stubs detected.

---
*Phase: 25-config-and-model-foundation*
*Completed: 2026-03-23*
