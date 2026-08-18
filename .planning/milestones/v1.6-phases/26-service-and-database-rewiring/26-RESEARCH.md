# Phase 26: Service and Database Rewiring - Research

**Researched:** 2026-03-23
**Domain:** Python/FastAPI service-layer refactoring -- quota enforcement rewiring from database JOIN to config-driven lookup
**Confidence:** HIGH

## Summary

Phase 26 eliminates the `core.plans` table dependency from all runtime queries by rewiring quota enforcement to read from `AppConfig.quotas` (a `dict[SubscriptionPlan, int]`) instead of JOINing `core.plans`. The changes span four layers: config model simplification, service constructor injection, SQL rewrite, and router updates. No database migration DDL is in scope (Phase 27), and no test updates are in scope (Phase 28).

The codebase is well-structured with established dependency injection patterns in `dependencies.py`. The `get_config` dependency already exists and returns `AppConfig`, and the `ChatService` constructor already accepts scalar config values (`examples`, `chats_limit`, `messages_limit`). Adding `quotas` follows the identical pattern. The `User` model already has `subscription_plan: SubscriptionPlan`, so resolving quota is a simple dict lookup.

**Primary recommendation:** Execute changes bottom-up: config model first, then UsageDB SQL rewrite, then ChatService signature change, then router updates. Each layer can be verified independently.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Remove `QuotaConfig` Pydantic model entirely -- replace with bare `dict[SubscriptionPlan, int]` as the config type on `AppConfig.quotas`
- **D-02:** Move or drop the exhaustiveness validator (`model_validator` that checks all SubscriptionPlan members have entries) -- future requirement QUOTA-06 may reintroduce it at `AppConfig` level
- **D-03:** Pass `quotas: dict[SubscriptionPlan, int]` to ChatService constructor via `dependencies.py`, following the established pattern for `examples`, `chats_limit`, `messages_limit`
- **D-04:** Replace `user_id: UUID` with `user: User` in ChatService method signatures (`create_chat`, `send_message`) -- router already has `User` from `Depends(get_current_user)`
- **D-05:** ChatService resolves quota internally: `self.quotas[user.subscription_plan]` then passes integer to `UsageDB.try_increment`
- **D-06:** `UsageDB.try_increment` gains a `monthly_quota: int` parameter -- SQL rewritten to use the parameter instead of JOINing `plans`
- **D-07:** `UsageDB.get_monthly_limit` deleted entirely (QUOTA-04)
- **D-08:** Add `config: AppConfig = Depends(get_config)` to the `/users/me` handler -- resolve `monthly_limit = config.quotas[user.subscription_plan]`
- **D-09:** Remove `UsageDB.get_monthly_limit` call -- replaced by config lookup

### Claude's Discretion
- SQL rewrite approach for `try_increment` (parameterized comparison vs CTE) -- as long as no JOIN to `core.plans`
- Whether `UsageDB.get_usage` signature changes (currently takes `user_id` -- may stay since it doesn't involve quota)
- Import cleanup after QuotaConfig removal

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUOTA-03 | UsageDB.try_increment accepts `monthly_quota` parameter instead of JOINing plans table | D-06: SQL rewrite with parameterized limit; Architecture Patterns section provides exact SQL |
| QUOTA-04 | UsageDB.get_monthly_limit removed; quota resolved from config in service/router layer | D-07/D-08/D-09: Method deletion + config lookup in ChatService and /users/me router |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Don't commit .planning dir** -- `commit_docs: false` in config.json aligns
- **Opening delimiter alignment style** for multiline constructs (func defs one param per line, func calls collapse)
- **Don't use string-based module references** in Python tests -- relevant because existing unit tests use `patch("app.routers.users.UsageDB")` which is a string-based module reference (Phase 28 scope to fix, NOT this phase)
- **Context7 MCP** for library/API docs
- **Python 3.12+** with latest features (project actually runs 3.14 per pyproject.toml)
- **FastAPI + Pydantic** for config and validation
- **Shorter branch names** for git

## Standard Stack

No new libraries are introduced in this phase. All changes use existing dependencies:

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.1 | Web framework, dependency injection | Already in use, `Depends()` pattern |
| Pydantic | >=2.12 | Config validation | `AppConfig` field type change |
| SQLAlchemy | (via sqlmodel >=0.0.22) | Raw SQL via `text()` | `UsageDB` SQL rewrite |
| SQLModel | >=0.0.22 | ORM models | `User.subscription_plan` field access |

### Alternatives Considered
None -- this phase modifies existing code, no new dependencies needed.

## Architecture Patterns

### Affected File Structure
```
src/nativespeaker/api/
  config.py              # Remove QuotaConfig, simplify AppConfig.quotas type
  database/
    usage.py             # Rewrite try_increment SQL, delete get_monthly_limit
  services/
    chats.py             # Add quotas param, change user_id -> user in signatures
  app/
    dependencies.py      # Pass quotas to ChatService constructor
  routers/
    users.py             # Add config dependency, remove get_monthly_limit call
    chats.py             # Pass user instead of user.id to service methods
```

### Pattern 1: Config Simplification (D-01, D-02)

**What:** Replace `QuotaConfig` Pydantic model with bare `dict[SubscriptionPlan, int]` on `AppConfig.quotas`.

**Current state** (`config.py:58-66,93`):
```python
class QuotaConfig(BaseModel):
    tiers: dict[SubscriptionPlan, int]

    @model_validator(mode='after')
    def check_all_tiers(self):
        missing = set(SubscriptionPlan) - self.tiers.keys()
        if missing:
            raise ValueError(f'Missing quota for: {missing}')
        return self

# In AppConfig:
    quotas: QuotaConfig
```

**Target state:**
```python
# QuotaConfig class: DELETED
# model_validator: DROPPED (QUOTA-06 deferred)

# In AppConfig:
    quotas: dict[SubscriptionPlan, int]
```

**YAML impact:** The current config.yaml has nested `quotas.tiers`:
```yaml
quotas:
  tiers:
    free: 10
    silver: 50
    gold: 200
    platinum: 1000
```
After removing the `QuotaConfig` wrapper, the YAML must flatten to:
```yaml
quotas:
  free: 10
  silver: 50
  gold: 200
  platinum: 1000
```
Pydantic parses `dict[SubscriptionPlan, int]` directly from the YAML mapping under `quotas`.

### Pattern 2: Constructor Injection for Quotas (D-03)

**What:** Thread `quotas` dict from config into `ChatService` via `dependencies.py`, matching the established pattern.

**Current** (`dependencies.py:29-36`):
```python
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit)
```

**Target:** Add `quotas=config.quotas` to the call. Add `quotas: dict[SubscriptionPlan, int]` parameter to `ChatService.__init__`.

### Pattern 3: User Object Passing (D-04, D-05)

**What:** Replace `user_id: UUID` with `user: User` in `ChatService.create_chat` and `ChatService.send_message`.

**Key change points:**
- `ChatService.create_chat(user_id=..., ...)` becomes `create_chat(user=..., ...)`
- `ChatService.send_message(chat_id=..., user_id=..., ...)` becomes `send_message(chat_id=..., user=..., ...)`
- Inside these methods, use `user.id` where `user_id` was used, and `self.quotas[user.subscription_plan]` for quota lookup
- `chats.py` router calls change from `user_id=user.id` to `user=user`

**Methods that do NOT change:** `get_messages`, `list_chats`, `delete_chat` -- these take `user_id: UUID` and don't involve quota. Keeping them as `user_id` avoids unnecessary churn.

### Pattern 4: SQL Rewrite for try_increment (D-06)

**What:** Rewrite `UsageDB.try_increment` to accept `monthly_quota: int` and remove the JOIN to `plans`.

**Current SQL** (the UPDATE statement):
```sql
UPDATE usage_monthly u
SET used = u.used + 1
FROM plans p
WHERE u.user_id = :user_id
  AND u.month = :month
  AND p.tier = (SELECT plan FROM users WHERE id = :user_id)
  AND u.used < p.monthly_quota
RETURNING u.used
```

**Target SQL** (parameterized comparison, Claude's discretion):
```sql
UPDATE usage_monthly u
SET used = u.used + 1
WHERE u.user_id = :user_id
  AND u.month = :month
  AND u.used < :monthly_quota
RETURNING u.used
```

This is simpler, faster (no JOIN, no subquery), and the atomicity guarantee is preserved: the `WHERE u.used < :monthly_quota` condition ensures the increment only happens if under quota, and PostgreSQL's row-level locking on UPDATE prevents races.

**Recommendation:** Use the simple parameterized comparison. A CTE adds complexity with zero benefit here since the single UPDATE with WHERE condition is already atomic.

The INSERT (upsert) statement stays unchanged -- it only creates the usage_monthly row and does not reference plans.

### Pattern 5: /users/me Config Dependency (D-08, D-09)

**What:** Add `config: AppConfig = Depends(get_config)` to the `/users/me` handler. Replace `await usage_db.get_monthly_limit(user.id)` with `config.quotas[user.subscription_plan]`.

**Current** (`routers/users.py:14-34`):
```python
@router.get("/users/me", response_model=UserProfileResponse)
async def get_me(user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)) -> UserProfileResponse:
    usage_db = UsageDB(db)
    month = datetime.now(UTC).strftime("%Y-%m")
    requests_used = await usage_db.get_usage(user.id, month)
    monthly_limit = await usage_db.get_monthly_limit(user.id)
    ...
```

**Target:** Add `config` dependency, replace `get_monthly_limit` call. Note that `UsageDB(db)` is still needed for `get_usage`, and `get_db` is still needed for the session. The `UsageDB` import may remain (for `get_usage`), but the `get_monthly_limit` call is removed.

### Anti-Patterns to Avoid
- **Do not pass `AppConfig` to ChatService** -- pass the extracted `dict[SubscriptionPlan, int]` to keep the service decoupled from config shape (follows established pattern with `examples`, `chats_limit`, `messages_limit`)
- **Do not add quota validation in this phase** -- D-02 explicitly defers the exhaustiveness validator to QUOTA-06
- **Do not modify test files** -- TEST-02 is Phase 28 scope
- **Do not write migration DDL** -- SCHEMA-01 is Phase 27 scope

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic quota increment | Custom lock/transaction logic | PostgreSQL UPDATE WHERE condition | Row-level locking is built into UPDATE; the WHERE clause makes it conditional and atomic |
| Config parsing for dict type | Manual YAML-to-dict conversion | Pydantic `dict[SubscriptionPlan, int]` field | Pydantic handles StrEnum key coercion from YAML strings automatically |

## Common Pitfalls

### Pitfall 1: YAML Structure Mismatch After QuotaConfig Removal
**What goes wrong:** After removing `QuotaConfig`, the YAML still has `quotas.tiers.free: 10` nesting, but `AppConfig.quotas: dict[SubscriptionPlan, int]` expects `quotas.free: 10`.
**Why it happens:** The `QuotaConfig` model had a `tiers` field that added a nesting level. Removing the model changes the expected YAML shape.
**How to avoid:** Update `config/config.yaml` to remove the `tiers:` nesting level in the same task as the config model change.
**Warning signs:** `ValidationError` on startup: "Input should be a valid dictionary" for the `quotas` field.

### Pitfall 2: Forgetting user.id Substitution in ChatService Methods
**What goes wrong:** After changing `user_id: UUID` to `user: User`, existing code inside the methods still references `user_id` (e.g., `self.usage_db.try_increment(user_id, month)`).
**Why it happens:** The parameter name changed but internal usage was not updated.
**How to avoid:** After renaming the parameter, search-and-replace every `user_id` reference within `create_chat` and `send_message` to `user.id`. Other usages like `Chat(user_id=user_id, ...)` become `Chat(user_id=user.id, ...)`.
**Warning signs:** `AttributeError: 'User' object has no attribute ...` or type errors from passing a User where UUID was expected.

### Pitfall 3: SubscriptionService Also Uses UsageDB
**What goes wrong:** `SubscriptionService` (subscriptions.py:66) instantiates `UsageDB(db)` and calls `self.usage_db.reset_usage()`. If `try_increment` signature changes, does `SubscriptionService` need updating?
**Why it happens:** `SubscriptionService` only calls `reset_usage`, which does NOT change in this phase (no plans JOIN, no quota param). But the concern is worth verifying.
**How to avoid:** Verify that `SubscriptionService` only uses `reset_usage` and `get_usage` -- both are unaffected by this phase. Confirmed: `subscriptions.py:163` calls `self.usage_db.reset_usage(subscription.user_id, month)` only.
**Warning signs:** None expected -- this is a false alarm, documented for completeness.

### Pitfall 4: KeyError When Subscription Plan Missing from Config
**What goes wrong:** `self.quotas[user.subscription_plan]` raises `KeyError` if a user has a plan value not present in config.
**Why it happens:** The exhaustiveness validator was dropped (D-02), so there's no startup-time check that all enum values have quota entries.
**How to avoid:** Ensure `config/config.yaml` lists all four plan tiers (`free`, `silver`, `gold`, `platinum`). The current YAML already does. QUOTA-06 will add the validator back at `AppConfig` level in a future milestone.
**Warning signs:** 500 errors on `/chats` or `/users/me` with `KeyError: 'free'` in logs.

### Pitfall 5: Pydantic StrEnum Key Coercion From YAML
**What goes wrong:** YAML keys are plain strings (`free`, `silver`, etc.). The `dict[SubscriptionPlan, int]` type annotation requires Pydantic to coerce string keys to `SubscriptionPlan` enum values.
**Why it happens:** Pydantic v2 handles StrEnum coercion in dict keys automatically -- this is a non-issue, but worth verifying.
**How to avoid:** Pydantic v2 with `StrEnum` keys in dict types works correctly. The existing `QuotaConfig.tiers: dict[SubscriptionPlan, int]` field already proves this pattern works in the codebase.
**Warning signs:** `ValidationError` mentioning "unexpected value; permitted: ...".

## Code Examples

Verified patterns from the existing codebase:

### Config Model Change (config.py)
```python
# BEFORE (lines 58-66, 93):
class QuotaConfig(BaseModel):
    tiers: dict[SubscriptionPlan, int]
    @model_validator(mode='after')
    def check_all_tiers(self): ...

class AppConfig(BaseConfig):
    quotas: QuotaConfig

# AFTER:
# QuotaConfig class removed entirely
# model_validator removed entirely

class AppConfig(BaseConfig):
    quotas: dict[SubscriptionPlan, int]
```

### YAML Config Change (config/config.yaml)
```yaml
# BEFORE:
quotas:
  tiers:
    free: 10
    silver: 50
    gold: 200
    platinum: 1000

# AFTER:
quotas:
  free: 10
  silver: 50
  gold: 200
  platinum: 1000
```

### UsageDB.try_increment Rewrite (database/usage.py)
```python
# AFTER -- monthly_quota is a plain int parameter
async def try_increment(self,
                        user_id: UUID,
                        month: str,
                        monthly_quota: int) -> bool:
    """Atomically increment usage if under quota. Returns True if allowed."""
    await self.session.exec(text(
        "INSERT INTO usage_monthly (id, user_id, month, used) "
        "VALUES (:id, :user_id, :month, 0) "
        "ON CONFLICT (user_id, month) DO NOTHING"
    ), params={"id": uuid7(), "user_id": user_id, "month": month})

    result = await self.session.exec(text(
        "UPDATE usage_monthly u "
        "SET used = u.used + 1 "
        "WHERE u.user_id = :user_id "
        "  AND u.month = :month "
        "  AND u.used < :monthly_quota "
        "RETURNING u.used"
    ), params={"user_id": user_id, "month": month, "monthly_quota": monthly_quota})
    return result.first() is not None
```

### ChatService Constructor and Method Signatures (services/chats.py)
```python
class ChatService:
    def __init__(self,
                 db: AsyncSession,
                 llm_service: LLMService,
                 examples: dict[str, list[str]],
                 messages_limit: int,
                 chats_limit: int,
                 quotas: dict[SubscriptionPlan, int]) -> None:
        ...
        self.quotas = quotas

    async def create_chat(self,
                          user: User,
                          phrase: str,
                          comment: str | None = None,
                          lang: str | None = None) -> Message:
        ...
        monthly_quota = self.quotas[user.subscription_plan]
        if not await self.usage_db.try_increment(user.id, month, monthly_quota):
            raise QuotaExceededError("Monthly quota exceeded")
        ...

    async def send_message(self,
                           chat_id: UUID,
                           user: User,
                           content: str) -> Message:
        ...
        monthly_quota = self.quotas[user.subscription_plan]
        if not await self.usage_db.try_increment(user.id, month, monthly_quota):
            raise QuotaExceededError("Monthly quota exceeded")
        ...
```

### Dependencies (app/dependencies.py)
```python
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit,
                       quotas=config.quotas)
```

### Router Updates (routers/chats.py)
```python
# create_chat call changes:
ai_message = await service.create_chat(user=user, phrase=body.phrase,
                                       comment=body.comment, lang=body.lang)

# send_message call changes:
ai_message = await service.send_message(chat_id=chat_id, user=user,
                                        content=body.content)
```

### /users/me Router (routers/users.py)
```python
from nativespeaker.api.app.dependencies import get_config, get_current_user, get_db
from nativespeaker.api.config import AppConfig

@router.get("/users/me", response_model=UserProfileResponse)
async def get_me(user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db),
                 config: AppConfig = Depends(get_config)) -> UserProfileResponse:
    usage_db = UsageDB(db)
    month = datetime.now(UTC).strftime("%Y-%m")
    requests_used = await usage_db.get_usage(user.id, month)
    monthly_limit = config.quotas[user.subscription_plan]
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JOIN `plans` table at query time | Config-driven quota lookup | This phase (26) | Eliminates runtime dependency on `core.plans` table |
| `get_monthly_limit` DB method | Direct dict lookup from config | This phase (26) | One fewer DB round-trip on `/users/me` |
| `user_id: UUID` param in service | `user: User` object param | This phase (26) | Service has access to subscription_plan without extra query |

## Open Questions

1. **Import cleanup for QuotaConfig**
   - What we know: `QuotaConfig` is only referenced in `config.py` (line 58 definition, line 93 usage). No other file imports it.
   - What's unclear: Whether `model_validator` import should be removed from `config.py` -- it may be used elsewhere in the file.
   - Recommendation: Check if `model_validator` is used by `MainConfig.load_config` (yes, line 110). Keep the import; only remove `QuotaConfig` class.

2. **`get_usage` still needs `UsageDB` in `/users/me`**
   - What we know: The `UsageDB` import and `get_db` dependency remain in `routers/users.py` because `get_usage` is still called.
   - What's unclear: Nothing -- this is confirmed.
   - Recommendation: Keep `UsageDB` import and `get_db` dependency. Only `get_monthly_limit` call is removed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 with pytest-asyncio >=1.3 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `pytest tests/unit/ -x` |
| Full suite command | `pytest tests/unit/` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUOTA-03 | try_increment accepts monthly_quota param, SQL has no JOIN to plans | unit | `pytest tests/unit/test_usage.py -x` | Yes (but tests need updating -- Phase 28) |
| QUOTA-04 | get_monthly_limit deleted; quota from config in service/router | unit | `pytest tests/unit/test_users.py -x` | Yes (but tests need updating -- Phase 28) |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/ -x` (expected: some failures due to signature changes -- Phase 28 fixes tests)
- **Per wave merge:** `pytest tests/unit/`
- **Phase gate:** Code changes verified via manual review of success criteria; test fixes in Phase 28

### Wave 0 Gaps
None in this phase -- test infrastructure exists. Test updates are Phase 28 scope (TEST-02). This phase's verification relies on success criteria checks:
1. `UsageDB.try_increment` accepts `monthly_quota: int` and SQL has no JOIN to `core.plans`
2. `UsageDB.get_monthly_limit` method no longer exists
3. `ChatService` resolves quota from `QuotaConfig` and passes int to `try_increment`
4. `GET /users/me` returns monthly limit from config, not DB

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all 7 canonical files from CONTEXT.md
- `config/config.yaml` -- current YAML structure with `quotas.tiers` nesting
- `pyproject.toml` -- dependency versions and test configuration
- `tests/unit/conftest.py` + `tests/unit/test_usage.py` + `tests/unit/test_users.py` -- current test patterns and mock setup

### Secondary (MEDIUM confidence)
- Pydantic v2 StrEnum dict key coercion -- verified by existing `QuotaConfig.tiers: dict[SubscriptionPlan, int]` working in production

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all changes in existing code
- Architecture: HIGH -- patterns established in codebase, changes follow existing conventions
- Pitfalls: HIGH -- all pitfalls identified from direct code analysis, no speculation

**Research date:** 2026-03-23
**Valid until:** Indefinite (codebase-specific research, no external dependency volatility)
