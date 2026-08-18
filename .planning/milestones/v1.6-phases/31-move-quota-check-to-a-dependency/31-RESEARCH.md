# Phase 31: Move Quota Check to a Dependency - Research

**Researched:** 2026-03-25
**Domain:** FastAPI dependency injection, cross-cutting quota enforcement
**Confidence:** HIGH

## Summary

The quota check currently lives inside `ChatService.create_chat()` and `ChatService.send_message()` as duplicated inline logic. Each method resolves the user's monthly quota from `self.quotas[user.subscription_plan]`, calls `self.usage_db.try_increment()`, and raises `QuotaExceededError` on failure. Additionally, the `/users/me` endpoint manually instantiates `UsageDB(db)` in the router to display usage info. The `SubscriptionService` also creates its own `UsageDB` instance for `reset_usage`.

This phase extracts quota enforcement into a FastAPI dependency that runs before route handlers. The dependency will call `UsageDB.try_increment()` and raise `QuotaExceededError` if the quota is exceeded -- keeping the enforcement centralized, testable, and aligned with the project's key decision: "All FastAPI dependencies in `app/dependencies.py`; routes use `Depends()` only."

**Primary recommendation:** Create a `require_quota` dependency in `dependencies.py` that accepts the current user, DB session, and config, performs the atomic increment, and raises `QuotaExceededError` on failure. Apply it only to the two chat-mutating endpoints (`POST /chats` and `POST /chats/{chat_id}`). Remove all quota logic from `ChatService`.

## Project Constraints (from CLAUDE.md)

- **Don't commit .planning dir** -- planning docs stay local
- **Opening delimiter alignment style** for multiline constructs (func defs one arg per line, calls collapse)
- **Always use Context7 MCP** for library/API docs, code gen, setup, configuration
- **Don't use string-based module references** in Python tests
- **Shorter branch names**
- Python 3.12+ features, FastAPI with Uvicorn, Pydantic for validation

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Relevance |
|---------|---------|---------|-----------|
| FastAPI | 0.135.1 | Web framework with `Depends()` DI system | The dependency injection mechanism for quota check |
| SQLModel | >=0.0.22 | ORM for UsageMonthly model | UsageDB.try_increment stays the same |
| Pydantic | >=2.12 | Config validation | `AppConfig.quotas` dict stays the same |

No new libraries are needed. This is a pure refactoring of existing code using existing FastAPI dependency injection.

## Architecture Patterns

### Current Architecture (BEFORE)

```
Router (POST /chats)
  -> get_current_user dependency (returns User)
  -> get_chat_service dependency (creates ChatService with quotas dict)
     -> ChatService.__init__ creates UsageDB(db)
     -> ChatService.create_chat() checks quota inline
     -> ChatService.send_message() checks quota inline

Router (GET /users/me)
  -> manually creates UsageDB(db) in router body
  -> reads config.quotas[user.subscription_plan] in router body
```

**Problems:**
1. Quota enforcement duplicated in `create_chat()` (line 61-64) and `send_message()` (line 88-91)
2. `ChatService` owns quota concern (violates single responsibility)
3. `ChatService.__init__` requires `quotas` parameter solely for enforcement
4. `/users/me` router directly instantiates `UsageDB` (inconsistent with DI pattern)
5. Testing quota enforcement requires mocking deep inside `ChatService`

### Target Architecture (AFTER)

```
Router (POST /chats)
  -> get_current_user dependency (returns User)
  -> require_quota dependency (calls try_increment, raises on failure)
  -> get_chat_service dependency (no quotas param)
     -> ChatService no longer has UsageDB or quotas

Router (GET /users/me)
  -> get_current_user dependency
  -> get_usage_info dependency (returns usage data)
```

### Pattern: Cross-Cutting Enforcement via FastAPI Dependency

**What:** A dependency function that performs a side effect (quota increment) and raises an HTTP exception on failure. Does not return a value consumed by the route -- it acts as a guard.

**When to use:** When enforcement must happen before route logic, is shared across multiple endpoints, and must be independently testable/mockable.

**Implementation shape:**

```python
# In dependencies.py
async def require_quota(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        config: AppConfig = Depends(get_config)) -> None:
    month = datetime.now(UTC).strftime("%Y-%m")
    monthly_quota = config.quotas[user.subscription_plan]
    usage_db = UsageDB(db)
    if not await usage_db.try_increment(user.id, month, monthly_quota):
        raise QuotaExceededError("Monthly quota exceeded")
```

**Route usage:**

```python
@router.post("/chats", response_model=MessageResponse)
async def create_chat(body: ChatRequest,
                      user: User = Depends(get_current_user),
                      _quota: None = Depends(require_quota),
                      service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ...
```

**Key detail:** FastAPI deduplicates dependencies by default. When both `require_quota` and `get_chat_service` depend on `get_current_user` and `get_db`, they share the same instances. The user is fetched once, and the DB session is the same across all dependencies in a single request.

### Pattern: Usage Info Dependency for /users/me

The `/users/me` endpoint currently creates `UsageDB(db)` inline. This should also become a dependency to stay consistent:

```python
async def get_usage_db(db: AsyncSession = Depends(get_db)) -> UsageDB:
    return UsageDB(db)
```

Or, since the users router only needs usage info (not enforcement), a higher-level dependency could be created. However, the simplest approach is to let `require_quota` handle enforcement and keep `/users/me` reading usage directly via a `get_usage_db` dependency -- or just leave the `UsageDB` instantiation in the router since it is read-only and only used in one place.

**Recommendation:** Introduce `get_usage_db` as a dependency for the `/users/me` endpoint to maintain consistency with the project convention. This is optional and low priority compared to the core quota enforcement extraction.

### Anti-Patterns to Avoid

- **Middleware for quota checking:** Middleware runs on EVERY request (including GET /chats, DELETE /chats, health checks). Quota enforcement only applies to the two chat-mutation endpoints. A dependency is more precise.
- **Returning quota data from the dependency:** The enforcement dependency is a guard. If a route needs quota info (like /users/me), use a separate read-only dependency -- don't conflate enforcement with data retrieval.
- **Making require_quota a class:** Unnecessary complexity. A plain async function is idiomatic FastAPI.
- **Using `use_cache=False` on require_quota:** The default cache behavior is correct here -- a single quota check per request is exactly what we want.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dependency deduplication | Custom caching of user/db across deps | FastAPI built-in `use_cache=True` (default) | FastAPI automatically shares dependency results within a request |
| Quota atomicity | Python-level counter check | `UsageDB.try_increment` (existing) | Already uses PostgreSQL atomic UPDATE...WHERE...RETURNING |
| DI override for testing | Custom mock injection | `app.dependency_overrides[require_quota]` | FastAPI's built-in testing pattern |

## Common Pitfalls

### Pitfall 1: Dependency Evaluation Order Matters
**What goes wrong:** If `require_quota` is listed after `get_chat_service` in the route signature, ChatService might begin constructing before quota is checked. In the current design this would not cause a functional bug (ChatService construction has no side effects), but it is semantically incorrect -- the guard should be evaluated first.
**Why it happens:** FastAPI evaluates dependencies in signature order.
**How to avoid:** List `require_quota` before `get_chat_service` in the route signature. Or, since `require_quota` depends on `get_current_user` which is also shared, FastAPI will resolve the shared sub-dependencies first regardless.
**Warning signs:** Quota increment happening after LLM invocation.

### Pitfall 2: Double Quota Increment on Shared Dependencies
**What goes wrong:** If `require_quota` is accidentally listed as a sub-dependency of `get_chat_service` AND as a direct route dependency, it could run twice.
**Why it happens:** Dependency deduplication works on identity, but a lambda wrapper or intermediate function creates a new identity.
**How to avoid:** Use `require_quota` only as a direct route dependency, never as a sub-dependency of another dependency.
**Warning signs:** Usage counter incrementing by 2 per request.

### Pitfall 3: Forgetting to Remove Quota Logic from ChatService
**What goes wrong:** If quota logic stays in both the dependency AND ChatService, the quota is checked twice (and incremented twice via `try_increment`).
**Why it happens:** Incomplete refactoring.
**How to avoid:** After adding the dependency, remove: (1) `quotas` parameter from `ChatService.__init__`, (2) `self.usage_db` from ChatService, (3) all `try_increment` calls and `QuotaExceededError` raises from `create_chat` and `send_message`, (4) `quotas=config.quotas` from `get_chat_service` in `dependencies.py`.
**Warning signs:** `QuotaExceededError` import still in `services/chats.py`.

### Pitfall 4: Breaking Existing Tests
**What goes wrong:** Unit tests for `ChatService` currently mock `usage_db.try_increment`. After extraction, those tests need updating: quota enforcement is now a dependency concern, not a service concern.
**Why it happens:** Tests are tightly coupled to the old architecture.
**How to avoid:** Update test fixtures: (1) remove `mock_usage_db` from `service` fixture, (2) update `TestChatServiceQuota` to test the dependency directly, (3) the `client` fixture should override `require_quota` with a no-op lambda.
**Warning signs:** Tests importing `QuotaExceededError` for ChatService tests.

### Pitfall 5: SubscriptionService Still Needs UsageDB
**What goes wrong:** Removing UsageDB from ChatService does NOT mean UsageDB is unused elsewhere. `SubscriptionService` uses `UsageDB.reset_usage()` on plan changes.
**Why it happens:** Confusing "move quota check" with "remove UsageDB entirely."
**How to avoid:** Only remove UsageDB from ChatService. Leave it in SubscriptionService unchanged.
**Warning signs:** `SubscriptionService` tests breaking.

### Pitfall 6: The /users/me Router Inline UsageDB
**What goes wrong:** The `/users/me` endpoint manually creates `UsageDB(db)` in the router body (line 19 of routers/users.py). This is a read-only usage, not enforcement, but it's inconsistent with the "all deps in dependencies.py" rule.
**Why it happens:** It was not originally part of the quota enforcement scope.
**How to avoid:** Either accept this inconsistency (it's read-only) or extract a `get_usage_db` dependency. Low-priority item.
**Warning signs:** None -- this is a style concern, not a bug risk.

## Code Examples

### New Dependency: require_quota

```python
# In app/dependencies.py
from datetime import UTC, datetime

from nativespeaker.api.database import UsageDB
from nativespeaker.api.exceptions import QuotaExceededError


async def require_quota(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        config: AppConfig = Depends(get_config)) -> None:
    """Atomically increment usage counter; raise 429 if monthly quota exhausted."""
    month = datetime.now(UTC).strftime("%Y-%m")
    monthly_quota = config.quotas[user.subscription_plan]
    usage_db = UsageDB(db)
    if not await usage_db.try_increment(user.id, month, monthly_quota):
        raise QuotaExceededError("Monthly quota exceeded")
```

### Updated Route Signature

```python
# In routers/chats.py
@router.post("/chats", response_model=MessageResponse)
async def create_chat(body: ChatRequest,
                      user: User = Depends(get_current_user),
                      _quota: None = Depends(require_quota),
                      service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ai_message = await service.create_chat(user=user, phrase=body.phrase,
                                           comment=body.comment, lang=body.lang)
    ...
```

### Simplified ChatService.__init__

```python
# In services/chats.py -- quotas and usage_db removed
class ChatService:

    def __init__(self,
                 db: AsyncSession,
                 llm_service: LLMService,
                 examples: dict[str, list[str]],
                 messages_limit: int,
                 chats_limit: int) -> None:
        self.llm_service = llm_service
        self.chats_db = ChatsDB(db)
        self.examples = examples
        self.messages_limit = messages_limit
        self.chats_limit = chats_limit
```

### Updated get_chat_service Dependency

```python
# In app/dependencies.py -- quotas removed
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit)
```

### Test: Override require_quota in Unit Tests

```python
# In unit/conftest.py -- updated client fixture
from nativespeaker.api.app.dependencies import require_quota

# Inside client fixture:
app.dependency_overrides[require_quota] = lambda: None
```

### Test: Direct Dependency Test

```python
# In unit/test_usage.py or a new test_quota_dependency.py
@pytest.mark.asyncio
async def test_require_quota_raises_when_exhausted():
    """require_quota raises QuotaExceededError when try_increment returns False."""
    # Mock db, config, user to drive the dependency function directly
    ...

@pytest.mark.asyncio
async def test_require_quota_passes_when_under_limit():
    """require_quota completes silently when under quota."""
    ...
```

## Scope of Changes

### Files to Modify

| File | Change | Complexity |
|------|--------|------------|
| `app/dependencies.py` | Add `require_quota` dependency | Low |
| `routers/chats.py` | Add `_quota: None = Depends(require_quota)` to POST endpoints | Low |
| `services/chats.py` | Remove `quotas`, `usage_db`, and quota check from `create_chat`/`send_message` | Medium |
| `tests/unit/conftest.py` | Update `service` fixture (remove mock_usage_db from ChatService), update `client` fixture (override require_quota) | Medium |
| `tests/unit/test_usage.py` | Move quota enforcement tests to target the dependency | Medium |
| `tests/unit/test_services.py` | Remove/update quota-related assertions | Low |

### Files NOT Modified

| File | Reason |
|------|--------|
| `database/usage.py` | `UsageDB` class is unchanged -- it's the data layer |
| `services/subscriptions.py` | Still needs `UsageDB.reset_usage()` -- separate concern |
| `routers/users.py` | `/users/me` reads usage (not enforcement) -- optional cleanup |
| `config.py` | `quotas` dict stays in AppConfig |
| `exceptions.py` | `QuotaExceededError` unchanged |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0 with pytest-asyncio >= 1.3 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `pytest tests/unit/ -x -q` |
| Full suite command | `pytest tests/unit/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEP-01 | `require_quota` raises `QuotaExceededError` when `try_increment` returns False | unit | `pytest tests/unit/test_usage.py -x -k "quota_exceeded"` | Partially (needs rewrite) |
| DEP-02 | `require_quota` passes silently when under quota | unit | `pytest tests/unit/test_usage.py -x -k "under_quota"` | Partially (needs rewrite) |
| DEP-03 | POST /chats returns 429 when quota exhausted (via dependency) | unit | `pytest tests/unit/test_usage.py -x -k "create_chat_quota"` | Needs rewrite |
| DEP-04 | POST /chats/{id} returns 429 when quota exhausted (via dependency) | unit | `pytest tests/unit/test_usage.py -x -k "send_message_quota"` | Needs rewrite |
| DEP-05 | ChatService no longer has quotas or usage_db attributes | unit | `pytest tests/unit/test_services.py -x` | Needs update |
| DEP-06 | SubscriptionService still works with UsageDB.reset_usage | unit | `pytest tests/unit/test_subscriptions.py -x` | Exists (should pass unchanged) |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/ -x -q`
- **Per wave merge:** `pytest tests/unit/ -v`
- **Phase gate:** Full unit suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_usage.py` -- rewrite quota enforcement tests to target dependency instead of ChatService
- [ ] `tests/unit/conftest.py` -- update `service` fixture to remove `mock_usage_db`, update `client` to override `require_quota`

## Open Questions

1. **Should `/users/me` also use a dependency for UsageDB?**
   - What we know: Currently instantiates `UsageDB(db)` inline in the router. This is read-only, not enforcement.
   - What's unclear: Whether the project owner considers this a problem worth fixing in this phase.
   - Recommendation: Include as optional cleanup task. The primary goal is enforcement extraction.

2. **Should the `_quota` parameter use a more descriptive name?**
   - What we know: Convention varies. `_quota` signals "unused return value" with the underscore prefix.
   - Recommendation: Use `_quota: None = Depends(require_quota)` -- the underscore clearly indicates it's a side-effect-only dependency.

## Sources

### Primary (HIGH confidence)
- Project source code -- `app/dependencies.py`, `services/chats.py`, `routers/chats.py`, `routers/users.py`, `database/usage.py` -- direct reading
- FastAPI documentation on [dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/) -- built-in `Depends()` deduplication, `use_cache` behavior
- Project key decisions from STATE.md -- "All FastAPI dependencies in app/dependencies.py; routes use Depends() only"

### Secondary (MEDIUM confidence)
- [FastAPI Dependency Injection 2026 Playbook](https://thelinuxcode.com/dependency-injection-in-fastapi-2026-playbook-for-modular-testable-apis/) -- confirms pattern of using dependencies for cross-cutting enforcement
- [Production-Ready FastAPI Project Structure 2026](https://dev.to/thesius_code_7a136ae718b7/production-ready-fastapi-project-structure-2026-guide-b1g) -- router-level dependencies for shared concerns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, pure refactoring of existing code
- Architecture: HIGH -- well-understood FastAPI dependency pattern, project already uses this pattern for auth
- Pitfalls: HIGH -- identified from direct code reading, all concrete and verifiable

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable refactoring, no external dependency changes)
