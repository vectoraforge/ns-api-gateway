# Phase 25: Config and Model Foundation - Research

**Researched:** 2026-03-23
**Domain:** Python StrEnum refactoring, Pydantic config modeling, SQLModel field narrowing
**Confidence:** HIGH

## Summary

This phase is a rename-and-restructure of application models and configuration. The core work involves: (1) renaming `Role` to `ChatRole` and `Tier` to `SubscriptionPlan`, propagating those renames through all imports, field references, local variables, config keys, and API response fields; (2) adding a `QuotaConfig` Pydantic model to `AppConfig` and a corresponding `quotas` section to `config.yaml`; (3) narrowing `str` fields to their StrEnum types on `User`, `Subscription`, `SubscriptionEvent`, and `UserProfileResponse`; (4) deleting the `Plan` SQLModel class and removing FK references to it; (5) fixing the `Message.__tablename__` double-prefix bug.

All changes are application-code-only. No database migrations (Phase 27), no query rewrites (Phase 26), no test updates (Phase 28). The codebase will be temporarily broken at the test level after this phase, which is expected and intentional.

**Primary recommendation:** Execute as a staged rename -- enum class renames first, then field-type narrowing, then config additions, then Plan removal, then the tablename bugfix. Each stage should leave `models.py` in a consistent state even if later stages haven't been applied yet.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Dedicated `QuotaConfig` Pydantic model with `tiers: dict[SubscriptionPlan, int]` and a `model_validator` that checks all `SubscriptionPlan` members have entries
- **D-02:** `QuotaConfig` added as `quotas: QuotaConfig` field on `AppConfig` (top-level in YAML)
- **D-03:** Quota values: free=10, silver=50, gold=200, platinum=1000
- **D-04:** YAML structure: `quotas.tiers.{plan}: {limit}` at root level of config.yaml
- **D-05:** ENUM-02 dropped -- no `sa_type=PG_ENUM(...)` on SQLModel fields. SQLAlchemy auto-infers native PG enum behavior from StrEnum annotations. Migrations own `CREATE TYPE`; runtime queries work without explicit `sa_type`
- **D-06:** PG enum type names (for Phase 27 migration): `core.chat_role`, `core.subscription_plan`, `core.subscription_provider`, `core.subscription_status`
- **D-07:** `Role` class renamed to `ChatRole`
- **D-08:** `Tier` class renamed to `SubscriptionPlan`
- **D-09:** Full rename across all layers (columns, config keys, API fields, local variables)
- **D-10:** `SubscriptionProvider` and `SubscriptionStatus` keep their current names
- **D-11:** Delete `Plan` SQLModel class and remove `foreign_key="core.plans.tier"` from `User.subscription_plan` and `Subscription.plan`
- **D-12:** Test imports and plan seeding left for Phase 28
- **D-13:** `Message.__tablename__` corrected from `"core.messages"` to `"messages"`

### Claude's Discretion
- Import organization and ordering after renames
- Whether to update `Field(description=...)` strings that reference old names

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUOTA-01 | QuotaConfig Pydantic model maps Tier enum values to monthly quota integers | Verified: `dict[SubscriptionPlan, int]` with Pydantic v2.12 correctly coerces YAML string keys to StrEnum members |
| QUOTA-02 | YAML config includes `quotas` section with tier-to-limit mapping | Verified: `yaml.safe_load` produces `dict[str, int]` which Pydantic coerces to `dict[SubscriptionPlan, int]` |
| QUOTA-05 | Plan SQLModel class and `core.plans` table eliminated | Code-side only: delete class, remove FK references. Table DROP is Phase 27 |
| ENUM-01 | PostgreSQL CREATE TYPE for role, tier, subscription_provider, subscription_status in core schema | Phase 25 prep: StrEnum classes renamed to match PG type conventions. Actual CREATE TYPE is Phase 27 migration |
| ENUM-02 | ~~All SQLModel enum fields use `sa_type=PG_ENUM`~~ | **DROPPED per D-05.** SQLAlchemy auto-infers `Enum` type with `native_enum=True` from StrEnum annotations |
| ENUM-03 | User.plan and Subscription.plan narrowed from `str` to `Tier` | Change field type annotations; rename `User.plan` to `User.subscription_plan` per D-09 |
| ENUM-04 | SubscriptionEvent.old_tier and new_tier narrowed from `str \| None` to `Tier \| None` | Rename fields to `old_plan`/`new_plan` per D-09, change type to `SubscriptionPlan \| None` |
| ENUM-05 | UserProfileResponse.plan typed as `Tier` | Rename to `subscription_plan: SubscriptionPlan` per D-09 |
| SCHEMA-02 | Message.__tablename__ corrected from "core.messages" to "messages" | Single-line fix in `models.py` line 65 |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Opening delimiter alignment style** for multiline constructs (func defs one arg per line, func calls collapse into 1+ line)
- **Do not commit `.planning` dir**
- **Do not use string-based module references** in Python tests
- **Context7 MCP** for library/API documentation
- **Shorter branch names** for git branches
- Python 3.12+ features (though pyproject says `>=3.14`)

## Standard Stack

### Core (already installed, no new dependencies)

| Library | Version | Purpose | Verified |
|---------|---------|---------|----------|
| pydantic | 2.12.5 | Config validation, QuotaConfig model, StrEnum coercion | Installed |
| pydantic-settings | 2.13.1 | BaseSettings with env vars and YAML loading | Installed |
| sqlmodel | 0.0.37 | ORM models with StrEnum field type narrowing | Installed |
| sqlalchemy | 2.0.46 | Underlying SA Enum type inference from StrEnum | Installed |
| pyyaml | 6.0+ | YAML config loading | Installed |

No new packages required. All changes use existing dependencies.

## Architecture Patterns

### Rename Propagation Map

The full rename touches these files (source code only, tests are Phase 28):

```
src/nativespeaker/api/
  models.py             # Enum class renames, field type narrowing, Plan deletion, tablename fix
  config.py             # QuotaConfig class, AppConfig.quotas field, AppleConfig rename
  schema.py             # UserProfileResponse field rename + type
  services/
    subscriptions.py    # All Tier->SubscriptionPlan imports, local vars, type hints
    chats.py            # Role->ChatRole imports and references
    firebase.py         # set_plan_claim param type (str -> SubscriptionPlan)
  database/
    subscriptions.py    # Tier->SubscriptionPlan imports, param types, field renames
  app/
    dependencies.py     # product_id_to_tier -> product_id_to_plan kwarg
config/
  config.yaml           # product_id_to_tier -> product_id_to_plan, add quotas section
```

### Pattern 1: StrEnum Field Narrowing (no `sa_type`)

**What:** Change SQLModel field type from `str` to a StrEnum subclass.
**When:** D-05 -- SQLAlchemy auto-infers `Enum(native_enum=True)` from StrEnum annotations.
**Verified behavior:** SQLAlchemy infers `Enum('free', 'silver', ..., name='subscriptionplan')` with `schema=None`, `native_enum=True`, `create_constraint=False`. At runtime with asyncpg, the PG enum codec handles encoding/decoding by string value -- the SA enum name is only used for DDL (which migrations handle).

```python
# BEFORE
plan: str = Field(default="free", foreign_key="core.plans.tier")

# AFTER
subscription_plan: SubscriptionPlan = Field(default=SubscriptionPlan.free)
```

**Important:** Removing `foreign_key="core.plans.tier"` is required since the `plans` table is being dropped. The actual FK constraint drop is Phase 27 migration, but the SQLModel declaration must not reference a table that no longer has a model class.

### Pattern 2: QuotaConfig with Exhaustiveness Validator

**What:** Pydantic BaseModel with `dict[SubscriptionPlan, int]` that validates all enum members are present.
**Verified:** Pydantic v2.12 coerces YAML string keys (e.g., `"free"`) to `SubscriptionPlan.free` automatically.

```python
class QuotaConfig(BaseModel):
    tiers: dict[SubscriptionPlan, int]

    @model_validator(mode='after')
    def check_all_tiers(self):
        missing = set(SubscriptionPlan) - self.tiers.keys()
        if missing:
            raise ValueError(f'Missing quota for: {missing}')
        return self
```

### Pattern 3: Config Field with Default Factory

**What:** Add `quotas` field to `AppConfig` following established pattern.

```python
class AppConfig(BaseConfig):
    # ... existing fields ...
    quotas: QuotaConfig = Field(default_factory=QuotaConfig)  # Will fail without YAML data -- intentional
```

**Note:** `QuotaConfig` has no defaults on `tiers`, so `default_factory=QuotaConfig` will raise a validation error if the YAML lacks the `quotas` section. This is correct -- quotas must be explicitly configured.

### Pattern 4: YAML Config Addition

```yaml
# Add at root level of config/config.yaml
quotas:
  tiers:
    free: 10
    silver: 50
    gold: 200
    platinum: 1000
```

### Anti-Patterns to Avoid

- **Partial rename:** Renaming the class but not local variables or config keys. D-09 mandates full rename for consistency.
- **Adding `sa_type=PG_ENUM(...)`:** D-05 explicitly dropped ENUM-02. Do not add explicit SA type decorators.
- **Forgetting FK removal:** `User.plan` and `Subscription.plan` both have `foreign_key="core.plans.tier"`. Both FKs must be removed from the SQLModel field declarations when deleting the Plan class.
- **Default value as string:** After narrowing, defaults must use the enum member (`SubscriptionPlan.free`) not the string `"free"`.

## Runtime State Inventory

> This phase involves rename/refactor of enum classes, fields, and config keys.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | PostgreSQL columns `users.plan`, `subscriptions.plan`, `subscription_events.old_tier`, `subscription_events.new_tier` store string values that match enum members. Values are valid for both old and new Python enum class names. | No data migration needed -- string values unchanged. Column renames are Phase 27. |
| Live service config | Firebase custom claims store `{"plan": "<tier_value>"}` per user. The claim key is `"plan"` and values are enum member strings (e.g., `"gold"`). | No action -- the claim key and values are unaffected by Python class renames. `firebase.py` still writes `{"plan": plan}`. |
| OS-registered state | None -- no OS-level registrations reference `Tier`, `Role`, or `Plan` names. | None |
| Secrets/env vars | None -- no env vars or secret keys reference the renamed identifiers. `product_id_to_tier` in config.yaml is file-based (renamed in this phase). | Code rename only. |
| Build artifacts | `egg-info` under `src/nativespeaker/` may cache old module metadata, but class renames within modules don't affect package-level artifacts. | None |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Enum exhaustiveness check | Manual if/elif for all tiers | `set(SubscriptionPlan) - dict.keys()` in `model_validator` | Automatically catches new enum members |
| StrEnum-to-PG-enum mapping | Custom TypeDecorator | SQLAlchemy native Enum inference from StrEnum | SA + asyncpg handle codec registration transparently |
| YAML key coercion to enum | Manual string-to-enum conversion | Pydantic `dict[SubscriptionPlan, int]` type annotation | Pydantic v2 auto-coerces string keys to StrEnum |

## Common Pitfalls

### Pitfall 1: Asymmetric Field Naming

**What goes wrong:** `User.plan` becomes `User.subscription_plan` but `Subscription.plan` stays as `plan`. Easy to accidentally rename both or neither.
**Why it happens:** D-09 specifies asymmetric renaming by design -- `plan` is natural in subscription context.
**How to avoid:** Reference D-09 explicitly when touching these two models. The `Subscription.plan` field keeps its name AND its column name.
**Warning signs:** If `Subscription` model has field named `subscription_plan`, it was renamed incorrectly.

### Pitfall 2: SubscriptionEvent Field + Column Rename Mismatch

**What goes wrong:** Renaming `old_tier`/`new_tier` Python fields to `old_plan`/`new_plan` in SQLModel, but the DB column names won't change until Phase 27 migration.
**Why it happens:** SQLModel uses the Python field name as the column name by default.
**How to avoid:** After renaming the Python field, the DB column will also need renaming in Phase 27. For this phase, the Python field rename is sufficient -- the column rename will happen via ALTER TABLE.
**Warning signs:** If someone adds `sa_column_kwargs={"name": "old_tier"}` to preserve the old column name -- don't. Let both the Python field and the future column use the new name.

### Pitfall 3: Foreign Key String References

**What goes wrong:** Removing the `Plan` class but leaving `foreign_key="core.plans.tier"` on `User` or `Subscription` fields causes SQLModel/SQLAlchemy metadata errors.
**Why it happens:** SQLModel validates FK references against registered table metadata.
**How to avoid:** Remove all `foreign_key="core.plans.tier"` strings when deleting the `Plan` class. The actual DB FK constraint persists until Phase 27 migration drops it.
**Warning signs:** `NoReferencedTableError` or `InvalidRequestError` at import time.

### Pitfall 4: AppleConfig Type Narrowing Side Effect

**What goes wrong:** Changing `product_id_to_tier: dict[str, str]` to `product_id_to_plan: dict[str, SubscriptionPlan]` means the dict values are now SubscriptionPlan enum members, not raw strings.
**Why it happens:** Pydantic coerces string values from YAML to the enum type.
**How to avoid:** This is actually desirable -- downstream code that does `Tier(tier_str)` conversion can be simplified. The `_map_lifecycle_event` method's `tier_str = self.product_id_to_tier.get(...)` pattern can be simplified since values are already enum members.
**Warning signs:** Double-conversion like `SubscriptionPlan(already_an_enum_value)` -- the value is already coerced.

### Pitfall 5: Circular Import Risk

**What goes wrong:** `models.py` imports from `schema.py` (for `Issue`). If `schema.py` needs to import `SubscriptionPlan` from `models.py` for the `UserProfileResponse.subscription_plan` type annotation, this creates a circular import.
**Why it happens:** `SubscriptionPlan` is defined in `models.py` alongside SQLModel classes.
**How to avoid:** `schema.py` can import `SubscriptionPlan` from `models.py` because the import in `models.py` (`from nativespeaker.api.schema import Issue`) only uses `Issue`, which is defined early in `schema.py` before any model imports. Python resolves this at module load time without circularity because `schema.py` doesn't import from `models.py` currently. The new import of `SubscriptionPlan` in `schema.py` works because `models.py` is loaded first (it's imported by everything).
**Warning signs:** `ImportError: cannot import name 'SubscriptionPlan' from partially initialized module`.

### Pitfall 6: insert_event_idempotent Column Name Mismatch

**What goes wrong:** The `insert_event_idempotent` method in `database/subscriptions.py` uses `pg_insert(SubscriptionEvent).values(old_tier=..., new_tier=...)`. After renaming the SQLModel fields to `old_plan`/`new_plan`, the `.values()` kwargs must also change to match.
**Why it happens:** SQLModel/SQLAlchemy maps `.values()` kwargs to column names via the model's field names.
**How to avoid:** Rename both the function parameters AND the `.values()` kwargs to `old_plan`/`new_plan`.
**Warning signs:** `CompileError: Unconsumed column names: old_tier` at runtime.

## Code Examples

### models.py -- Enum Renames and Field Narrowing

```python
# BEFORE
class Role(StrEnum):
    human = "human"
    ai = "ai"

class Tier(StrEnum):
    free = "free"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"

# AFTER
class ChatRole(StrEnum):
    human = "human"
    ai = "ai"

class SubscriptionPlan(StrEnum):
    free = "free"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"
```

### models.py -- User Field Rename and Narrowing

```python
# BEFORE
class User(BaseTable, table=True):
    plan: str = Field(default="free", foreign_key="core.plans.tier")

# AFTER
class User(BaseTable, table=True):
    subscription_plan: SubscriptionPlan = Field(default=SubscriptionPlan.free)
```

### models.py -- SubscriptionEvent Field Rename

```python
# BEFORE
class SubscriptionEvent(BaseTable, table=True):
    old_tier: str | None = Field(default=None)
    new_tier: str | None = Field(default=None)

# AFTER
class SubscriptionEvent(BaseTable, table=True):
    old_plan: SubscriptionPlan | None = Field(default=None)
    new_plan: SubscriptionPlan | None = Field(default=None)
```

### models.py -- Subscription Field Narrowing (name stays)

```python
# BEFORE
class Subscription(BaseTable, table=True):
    plan: str = Field(foreign_key="core.plans.tier")

# AFTER
class Subscription(BaseTable, table=True):
    plan: SubscriptionPlan = Field()
```

### models.py -- Message Tablename Fix

```python
# BEFORE
class Message(BaseTable, table=True):
    __tablename__ = "core.messages"

# AFTER
class Message(BaseTable, table=True):
    __tablename__ = "messages"
```

### config.py -- QuotaConfig and AppConfig

```python
from nativespeaker.api.models import SubscriptionPlan

class QuotaConfig(BaseModel):
    tiers: dict[SubscriptionPlan, int]

    @model_validator(mode='after')
    def check_all_tiers(self):
        missing = set(SubscriptionPlan) - self.tiers.keys()
        if missing:
            raise ValueError(f'Missing quota for: {missing}')
        return self

class AppleConfig(BaseModel):
    # ... other fields ...
    product_id_to_plan: dict[str, SubscriptionPlan] = Field(
        description="Maps Apple product IDs to SubscriptionPlan values"
    )

class AppConfig(BaseConfig):
    # ... existing fields ...
    quotas: QuotaConfig
```

### config.yaml -- Additions and Renames

```yaml
apple:
  # ... other fields ...
  product_id_to_plan:                    # renamed from product_id_to_tier
    com.example.nativespeaker.silver: silver
    com.example.nativespeaker.gold: gold
    com.example.nativespeaker.platinum: platinum

quotas:                                  # new section
  tiers:
    free: 10
    silver: 50
    gold: 200
    platinum: 1000
```

### schema.py -- UserProfileResponse

```python
from nativespeaker.api.models import SubscriptionPlan

class UserProfileResponse(BaseModel):
    email: str
    name: str | None = None
    subscription_plan: SubscriptionPlan    # renamed from plan: str
    created_at: datetime
    requests_used: int
    monthly_limit: int
    resets_at: datetime
```

### services/subscriptions.py -- Local Variable Renames

```python
# BEFORE
from nativespeaker.api.models import Tier, ...
status, plan_tier = self._map_lifecycle_event(...)
old_tier = subscription.plan if subscription else None
tier_str = self.product_id_to_tier.get(product_id, Tier.free)
tier = Tier(tier_str) if tier_str in Tier.__members__ else Tier.free

# AFTER
from nativespeaker.api.models import SubscriptionPlan, ...
status, plan = self._map_lifecycle_event(...)
old_plan = subscription.plan if subscription else None
# product_id_to_plan values are already SubscriptionPlan (Pydantic coerced)
plan = self.product_id_to_plan.get(product_id, SubscriptionPlan.free)
```

### routers/users.py -- Response Field Rename

```python
# BEFORE
return UserProfileResponse(email=user.email,
                           name=user.name,
                           plan=user.plan, ...)

# AFTER
return UserProfileResponse(email=user.email,
                           name=user.name,
                           subscription_plan=user.subscription_plan, ...)
```

## Complete File Change Inventory

| File | Changes | Complexity |
|------|---------|------------|
| `src/nativespeaker/api/models.py` | Rename `Role`->`ChatRole`, `Tier`->`SubscriptionPlan`; narrow 5 fields; delete `Plan` class; fix `Message.__tablename__` | HIGH -- most changes |
| `src/nativespeaker/api/config.py` | Add `QuotaConfig` class; add `quotas` field to `AppConfig`; rename `product_id_to_tier`->`product_id_to_plan` with type narrowing | MEDIUM |
| `src/nativespeaker/api/schema.py` | Rename `plan`->`subscription_plan`, narrow type, add import | LOW |
| `src/nativespeaker/api/services/subscriptions.py` | Rename imports, local vars (`plan_tier`->`plan`, `old_tier`->`old_plan`, `tier_str` removed), type hints, simplify `_map_lifecycle_event` | HIGH -- many rename sites |
| `src/nativespeaker/api/services/chats.py` | Rename `Role`->`ChatRole` import and 4 references | LOW |
| `src/nativespeaker/api/services/firebase.py` | Optionally narrow `plan: str` param to `plan: SubscriptionPlan` | LOW |
| `src/nativespeaker/api/database/subscriptions.py` | Rename `Tier`->`SubscriptionPlan` import; rename `old_tier`/`new_tier` params to `old_plan`/`new_plan`; update `.values()` kwargs | MEDIUM |
| `src/nativespeaker/api/app/dependencies.py` | Rename `product_id_to_tier`->`product_id_to_plan` kwarg | LOW |
| `config/config.yaml` | Rename `product_id_to_tier`->`product_id_to_plan`; add `quotas` section | LOW |
| `src/nativespeaker/api/routers/users.py` | Rename `plan=`->`subscription_plan=` in UserProfileResponse construction | LOW |

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUOTA-01 | QuotaConfig validates all SubscriptionPlan members | unit | `python -m pytest tests/unit/test_config.py -x -k quota` | Wave 0 |
| QUOTA-02 | YAML config loads quotas section | unit | `python -m pytest tests/unit/test_config.py -x -k main_config` | Existing (needs update in P28) |
| QUOTA-05 | Plan class removed, no FK reference errors | smoke | `python -c "from nativespeaker.api.models import *"` | N/A (import check) |
| ENUM-01 | Enum class names match PG convention (prep only) | manual-only | Verify class names in models.py | N/A |
| ENUM-03 | User.subscription_plan and Subscription.plan typed as SubscriptionPlan | unit | `python -c "from nativespeaker.api.models import User; assert User.model_fields['subscription_plan'].annotation is not str"` | N/A (import check) |
| ENUM-04 | SubscriptionEvent.old_plan/new_plan typed SubscriptionPlan \| None | unit | `python -c "from nativespeaker.api.models import SubscriptionEvent"` | N/A (import check) |
| ENUM-05 | UserProfileResponse.subscription_plan typed as SubscriptionPlan | unit | `python -c "from nativespeaker.api.schema import UserProfileResponse"` | N/A (import check) |
| SCHEMA-02 | Message.__tablename__ is "messages" not "core.messages" | unit | `python -c "from nativespeaker.api.models import Message; assert Message.__tablename__ == 'messages'"` | N/A (import check) |

### Sampling Rate

- **Per task commit:** `python -c "from nativespeaker.api.models import *; from nativespeaker.api.config import *; from nativespeaker.api.schema import *"` (import smoke test)
- **Per wave merge:** `python -c "from nativespeaker.api.models import *; from nativespeaker.api.config import *; from nativespeaker.api.schema import *; from nativespeaker.api.services.subscriptions import *; from nativespeaker.api.services.chats import *"` (full import chain)
- **Phase gate:** Full import chain passes + QuotaConfig unit test

### Wave 0 Gaps

- [ ] `tests/unit/test_config.py` needs a `test_quota_config_*` section -- covers QUOTA-01 (deferred to Phase 28 per D-12, but import smoke test covers Phase 25)
- No framework install needed -- pytest already configured

**Note:** Per D-12, comprehensive test updates are deferred to Phase 28. Phase 25 validation relies on import smoke tests and the QuotaConfig model being constructable from YAML data.

## Open Questions

1. **`_map_lifecycle_event` simplification scope**
   - What we know: After renaming `product_id_to_tier` to `product_id_to_plan` and narrowing its type to `dict[str, SubscriptionPlan]`, the values are already `SubscriptionPlan` members. The current code does `tier_str = self.product_id_to_tier.get(product_id, Tier.free)` then `tier = Tier(tier_str) if tier_str in Tier.__members__ else Tier.free`.
   - What's unclear: Should the double-conversion be simplified to just `.get(product_id, SubscriptionPlan.free)` since values are pre-validated, or should defensive coding remain?
   - Recommendation: Simplify. Pydantic already validated the dict values. The `.get()` fallback to `SubscriptionPlan.free` is sufficient. Remove the `if tier_str in Tier.__members__` check.

2. **`AppConfig.quotas` default behavior**
   - What we know: `QuotaConfig` has a required `tiers` field (no default). Using `Field(default_factory=QuotaConfig)` on AppConfig would fail at config load if YAML lacks `quotas`.
   - What's unclear: Whether to use `default_factory` or make it required.
   - Recommendation: Make it required (no default). The YAML must include the quotas section. This matches the intent -- quotas should never silently default.

## Sources

### Primary (HIGH confidence)
- **Local verification** -- Pydantic v2.12.5 `dict[StrEnum, int]` coercion tested with actual installed packages
- **Local verification** -- SQLModel v0.0.37 StrEnum field inference tested: produces `Enum(native_enum=True)` with `create_constraint=False`
- **Local verification** -- asyncpg codec behavior: auto-discovers PG enum types from catalog, string-based encoding
- **Codebase inspection** -- All 10 source files read and analyzed for rename scope

### Secondary (MEDIUM confidence)
- SQLAlchemy Enum type behavior with asyncpg dialect -- verified via `dialect_impl()` producing `AsyncPgEnum`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages already installed, versions verified
- Architecture: HIGH -- all patterns verified with actual code execution against installed libraries
- Pitfalls: HIGH -- rename scope fully mapped with grep, edge cases identified through code analysis

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (stable -- no library upgrades expected during this milestone)
