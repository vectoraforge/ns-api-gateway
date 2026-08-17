# Phase 25: Config and Model Foundation - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Application models and configuration are type-safe with config-driven quota mapping, class renames for clarity, and Plan model removal. No query rewrites (Phase 26), no migration DDL (Phase 27), no test updates (Phase 28).

</domain>

<decisions>
## Implementation Decisions

### Quota Configuration
- **D-01:** Dedicated `QuotaConfig` Pydantic model with `tiers: dict[SubscriptionPlan, int]` and a `model_validator` that checks all `SubscriptionPlan` members have entries
- **D-02:** `QuotaConfig` added as `quotas: QuotaConfig` field on `AppConfig` (top-level in YAML)
- **D-03:** Quota values: free=10, silver=50, gold=200, platinum=1000
- **D-04:** YAML structure: `quotas.tiers.{plan}: {limit}` at root level of config.yaml

### Enum Handling
- **D-05:** ENUM-02 dropped -- no `sa_type=PG_ENUM(...)` on SQLModel fields. SQLAlchemy auto-infers native PG enum behavior from StrEnum annotations. Migrations own `CREATE TYPE`; runtime queries work without explicit `sa_type`
- **D-06:** PG enum type names (for Phase 27 migration): `core.chat_role`, `core.subscription_plan`, `core.subscription_provider`, `core.subscription_status`

### Class and Field Renames
- **D-07:** `Role` class renamed to `ChatRole`
- **D-08:** `Tier` class renamed to `SubscriptionPlan`
- **D-09:** Full rename -- not just classes but also columns, config keys, API fields, and local variables:
  - `SubscriptionEvent.old_tier` -> `old_plan`, `new_tier` -> `new_plan` (field + DB column rename in Phase 27)
  - `AppleConfig.product_id_to_tier` -> `product_id_to_plan`
  - `config.yaml`: `product_id_to_tier` -> `product_id_to_plan`
  - `UserProfileResponse.plan` -> `subscription_plan` (breaking API change)
  - `User.plan` field -> `subscription_plan` (DB column `users.plan` -> `users.subscription_plan` in Phase 27)
  - `Subscription.plan` field stays as `plan` (DB column unchanged)
  - Local variables: `plan_tier` -> `plan`, `old_tier` -> `old_plan`, `tier_str` -> `plan_str`
- **D-10:** `SubscriptionProvider` and `SubscriptionStatus` keep their current names

### Plan Model Removal
- **D-11:** Delete `Plan` SQLModel class and remove `foreign_key="core.plans.tier"` from `User.subscription_plan` and `Subscription.plan` in this phase
- **D-12:** Test imports and plan seeding left for Phase 28 (TEST-01, TEST-02)

### Bug Fix
- **D-13:** `Message.__tablename__` corrected from `"core.messages"` to `"messages"` (SCHEMA-02)

### Claude's Discretion
- Import organization and ordering after renames
- Whether to update `Field(description=...)` strings that reference old names

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Models and Config
- `src/nativespeaker/api/models.py` -- All SQLModel classes, StrEnum definitions, Plan model to delete
- `src/nativespeaker/api/config.py` -- AppConfig, AppleConfig (product_id_to_tier), QuotaConfig target location
- `src/nativespeaker/api/schema.py` -- UserProfileResponse.plan field to rename
- `config/config.yaml` -- YAML config file, quotas section to add, product_id_to_tier to rename

### Service Layer (rename references)
- `src/nativespeaker/api/services/subscriptions.py` -- Tier imports, plan_tier locals, product_id_to_tier usage
- `src/nativespeaker/api/services/chats.py` -- Role.human/Role.ai references
- `src/nativespeaker/api/database/subscriptions.py` -- Tier import, old_tier/new_tier params
- `src/nativespeaker/api/app/dependencies.py` -- product_id_to_tier kwarg

### Requirements
- `.planning/REQUIREMENTS.md` -- QUOTA-01, QUOTA-02, QUOTA-05, ENUM-01, ENUM-03, ENUM-04, ENUM-05, SCHEMA-02 (ENUM-02 dropped)

No external specs -- requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PydanticJSONB` TypeDecorator in `models.py:13` -- established pattern for custom SA types
- `BaseTable(SQLModel)` base class -- all table models inherit from this
- `MainConfig.load_config` model_validator -- pattern for loading YAML into nested Pydantic models

### Established Patterns
- Nested Pydantic `BaseModel` classes for config sections (`DatabaseConfig`, `ResilienceConfig`, `JWTConfig`, `AppleConfig`)
- `Field(default_factory=...)` for config section defaults on `AppConfig`
- StrEnum classes defined at module top, before SQLModel classes
- `model_validator(mode="after")` for cross-field validation

### Integration Points
- `AppConfig` in `config.py` -- add `quotas: QuotaConfig` field
- `config.yaml` -- add `quotas` section
- `dependencies.py:46` -- passes `product_id_to_tier` to subscription service (rename needed)
- `services/subscriptions.py:63` -- constructor accepts `product_id_to_tier` param (rename needed)

</code_context>

<specifics>
## Specific Ideas

- QuotaConfig preview confirmed by user:
  ```python
  class QuotaConfig(BaseModel):
      tiers: dict[SubscriptionPlan, int]

      @model_validator(mode='after')
      def check_all_tiers(self):
          missing = set(SubscriptionPlan) - self.tiers.keys()
          if missing:
              raise ValueError(f'Missing: {missing}')
          return self
  ```
- User explicitly chose "full rename" over "class only" -- consistency across all layers preferred
- User chose `users.subscription_plan` but `subscriptions.plan` stays -- asymmetric by design (plan is natural in subscription context)

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 25-config-and-model-foundation*
*Context gathered: 2026-03-23*
