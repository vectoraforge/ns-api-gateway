# Phase 25: Config and Model Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-03-23
**Phase:** 25-config-and-model-foundation
**Areas discussed:** Quota config structure, PG_ENUM placement, core.role naming, Plan removal scope

---

## Quota Config Structure

### Question: How should the tier-to-quota mapping be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| Flat dict | `quotas: dict[Tier, int]` on AppConfig. Simple, one-liner. | |
| Dedicated QuotaConfig model | Separate model with `tiers: dict[Tier, int]` + model_validator for exhaustiveness check | ✓ |
| You decide | Claude picks based on codebase patterns | |

**User's choice:** Dedicated QuotaConfig model
**Notes:** User selected the preview with model_validator that checks all SubscriptionPlan members have entries.

### Question: What are the actual monthly quota values per tier?

| Option | Description | Selected |
|--------|-------------|----------|
| 10 / 50 / 200 / 1000 | free=10, silver=50, gold=200, platinum=1000 | ✓ |
| 5 / 30 / 100 / 500 | free=5, silver=30, gold=100, platinum=500 | |
| Placeholder values | Use obvious placeholder values and adjust later | |

**User's choice:** 10 / 50 / 200 / 1000

### Question: YAML nesting for quotas?

| Option | Description | Selected |
|--------|-------------|----------|
| Top-level | At root level alongside model:, resilience:, etc. | ✓ |
| Nested under apple | Alongside subscription config | |
| You decide | Claude picks | |

**User's choice:** Top-level

---

## PG_ENUM Placement

### Question: Where should PG_ENUM type objects be defined?

**User rejected the question.** User clarified: "What do you mean by putting PG_ENUM to Python code? It's a part of the SQL migration script, not Python."

Discussion pivoted to whether `sa_type=PG_ENUM(...)` is needed at all. After Context7 research into SQLAlchemy docs:
- SQLAlchemy auto-maps StrEnum to native PG enum with `native_enum=True` by default
- Without `sa_type`, queries still work (string values are wire-compatible with PG enums)
- `sa_type=PG_ENUM(...)` is only needed for schema correctness in `create_all()` (not used in this project)

**Outcome:** ENUM-02 requirement dropped entirely. No PG_ENUM objects in Python. CREATE TYPE stays in migration.

---

## core.role Naming

### Question: What should the PG enum type be named for the Role enum?

| Option | Description | Selected |
|--------|-------------|----------|
| core.role | Matches Python class name, safe when schema-qualified | |
| core.message_role | Avoids keyword entirely | |
| You decide | Claude picks | |

**User's choice:** (Other) "Rename class Role to ChatRole and class Tier to SubscriptionPlan"
**Notes:** User wanted to rename the Python classes themselves, not just the PG type names.

### Question: SubscriptionProvider and SubscriptionStatus keep current names?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, keep as-is | Only rename Role and Tier | ✓ |
| Rename those too | Suggest new names | |

**User's choice:** Yes, keep as-is

### Question: How far should the rename go?

| Option | Description | Selected |
|--------|-------------|----------|
| Class only | Rename Python classes, keep column/config names unchanged | |
| Full rename | Rename class + all field/column/config references | ✓ |

**User's choice:** Full rename -- columns (old_tier->old_plan, new_tier->new_plan), config (product_id_to_tier->product_id_to_plan), API response field

### Question: API response field name?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep plan | JSON stays {"plan": "free"}, no breaking change | |
| Rename to subscription_plan | JSON becomes {"subscription_plan": "free"}, breaking change | ✓ |
| You decide | Claude picks | |

**User's choice:** Rename to subscription_plan (accepted breaking API change)

### Question: DB column names for users.plan and subscriptions.plan?

| Option | Description | Selected |
|--------|-------------|----------|
| Rename to subscription_plan | Both columns rename | |
| Keep plan column name | DB columns stay as plan | |
| You decide | Claude picks | |

**User's choice:** (Other) "users.subscription_plan, but keep subscriptions.plan"
**Notes:** Asymmetric by design -- "plan" is natural in subscription context.

### Question: Local variable names?

| Option | Description | Selected |
|--------|-------------|----------|
| Use plan | plan_tier->plan, old_tier->old_plan, tier_str->plan_str | ✓ |
| Use subscription_plan | Fully explicit but verbose for locals | |
| You decide | Claude picks | |

**User's choice:** Use plan (short, context makes it clear)

---

## Plan Removal Scope

### Question: Remove both Plan class and FK annotations in Phase 25?

| Option | Description | Selected |
|--------|-------------|----------|
| Remove both | Delete Plan class + remove FK annotations. Models reflect target state. | ✓ |
| Plan class only | Delete class, keep FK annotations for later | |
| You decide | Claude picks | |

**User's choice:** Remove both

### Question: Test cleanup in Phase 25 or Phase 28?

| Option | Description | Selected |
|--------|-------------|----------|
| Clean up in Phase 25 | Remove Plan imports from tests now | |
| Leave for Phase 28 | Phase 25 only touches src/. Tests scoped to Phase 28. | ✓ |
| You decide | Claude picks | |

**User's choice:** Leave for Phase 28

---

## Claude's Discretion

- Import organization and ordering after renames
- Whether to update `Field(description=...)` strings referencing old names

## Deferred Ideas

None -- discussion stayed within phase scope.
