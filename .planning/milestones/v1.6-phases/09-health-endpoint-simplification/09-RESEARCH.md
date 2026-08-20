# Phase 9: Health Endpoint Simplification - Research

**Researched:** 2026-02-27
**Domain:** FastAPI health endpoint, ReadinessCache removal
**Confidence:** HIGH

## Summary

Phase 9 is a straightforward deletion-and-simplification task. The current health endpoint at `/health/ready` performs active backend connectivity checks (database `SELECT 1` query via SQLAlchemy, LLM model probe via OpenAI API) and uses a `ReadinessCache` class with TTL-based caching and async locking. The goal is to replace all of this with a trivial endpoint that returns UP/DOWN based solely on whether the FastAPI lifespan completed initialization successfully.

The scope of change is small and well-contained: one route file (`app/routers/health.py`), its import in `app/main.py`, the `readiness_cache_seconds` config field in `app/config.py`, the corresponding line in `config/config.yaml`, and the `readiness_cache` assignment in the lifespan function. No existing tests reference the health endpoint (the old `test_health_endpoints.py` was already deleted, only its `.pyc` cache remains), so no test modifications are needed -- only new tests should be added for the simplified endpoint.

**Primary recommendation:** Delete `ReadinessCache`, `_probe_llm`, and the current `readiness` handler entirely. Replace with a minimal endpoint that returns 200/UP unconditionally (lifespan already prevents serving if initialization fails).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.129 | Web framework | Already in use; health endpoints are standard FastAPI routes |
| Pydantic | >=2.12 | Response models | Already in use; optional for simple health response |

### Supporting
No additional libraries needed. This phase removes dependencies (openai, sqlalchemy from health.py) rather than adding them.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Boolean flag on `app.state` | Lifespan exception handling | Flag is simpler and explicit; lifespan exceptions already prevent startup |

## Architecture Patterns

### Recommended Project Structure
No structural changes needed. The file layout remains:
```
app/
  routers/
    health.py          # Simplified (gutted and rewritten)
  main.py              # Remove ReadinessCache import and instantiation
  config.py            # Remove readiness_cache_seconds field
```

### Pattern 1: Initialization-Only Health Check
**What:** The health endpoint checks a boolean flag that is set to `True` after the lifespan context manager completes initialization. If initialization fails (exception in lifespan), FastAPI raises and the server never starts serving, so the flag remains `False` / the app is unreachable.
**When to use:** When external health checkers (Kubernetes, load balancers) only need to know "is the process alive and initialized?"
**Example:**
```python
# app/routers/health.py
from fastapi import APIRouter
from starlette.responses import JSONResponse

router = APIRouter()

@router.get("/health/ready")
async def readiness() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "up"})
```

**Key insight:** In the current codebase, if the lifespan fails (e.g., config not found, DB engine creation fails, LLM init fails), FastAPI raises and the server never starts. This means any request that reaches the health endpoint already implies successful initialization. The endpoint can simply return 200/UP unconditionally. A boolean flag is only needed if there's a desire to track partial initialization failure while still serving (which is not the case here).

### Pattern 2: Minimal Flag-Based Health (if future-proofing desired)
**What:** Set `app.state.initialized = True` at the end of lifespan setup, check it in the endpoint.
**When to use:** If the lifespan might complete partially (some services up, some down) and the app should still start but report degraded status.
**Example:**
```python
# In lifespan (app/main.py):
app.state.initialized = True

# In health endpoint:
@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    if not getattr(request.app.state, "initialized", False):
        return JSONResponse(status_code=503, content={"status": "down"})
    return JSONResponse(status_code=200, content={"status": "up"})
```

**Recommendation:** Use the simpler Pattern 1. The lifespan context manager already guarantees that if any initialization step fails, FastAPI won't serve requests. Adding a flag adds complexity without benefit in this architecture.

### Anti-Patterns to Avoid
- **Backend probing in health checks:** Checking DB/LLM connectivity on every health request adds latency, creates false negatives (transient network blips), and couples health to backend availability. This is exactly what we're removing.
- **Caching health results:** The `ReadinessCache` pattern adds complexity (TTL, async locks) to compensate for expensive backend probes. Remove the probes and the cache becomes unnecessary.
- **Importing backend clients in health module:** The current `health.py` imports `AsyncOpenAI` and `sqlalchemy.text`. The simplified version should have zero backend dependencies.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Health response format | Custom response dict | Simple `{"status": "up"}` JSON | No need for complex status objects; orchestrators check HTTP status code |

**Key insight:** The entire ReadinessCache class (40 lines with async lock, TTL, error tracking) is being removed, not replaced. The simplification IS the solution.

## Common Pitfalls

### Pitfall 1: Forgetting to Remove Config Field
**What goes wrong:** `readiness_cache_seconds` remains in `AppConfig` as a dead field that still validates input and appears in config.yaml
**Why it happens:** Config fields are easy to miss when removing the feature they support
**How to avoid:** Remove `readiness_cache_seconds` from `AppConfig` in `app/config.py` AND from `config/config.yaml` (line 6: `readiness_cache_seconds: 60`)
**Warning signs:** Field exists in config class but is never referenced

### Pitfall 2: Stale Import in main.py
**What goes wrong:** `from app.routers.health import ReadinessCache` remains in `app/main.py` after class deletion, causing ImportError at startup
**Why it happens:** The import is separate from the router import (which comes via `app/routers/__init__.py`)
**How to avoid:** Remove the explicit `ReadinessCache` import from `main.py` and the `app.state.readiness_cache = ...` line in lifespan

### Pitfall 3: Leftover .pyc Files
**What goes wrong:** Old compiled `test_health_endpoints.pyc` in `tests/integration/__pycache__/` causes confusion
**Why it happens:** Test file was deleted but cache wasn't cleaned
**How to avoid:** Not a blocker, but can be cleaned up with `find . -name "*.pyc" -delete` or `__pycache__` cleanup

### Pitfall 4: Breaking the /health/ready Contract
**What goes wrong:** Changing the URL path or response format could break existing monitoring/deployment configs
**Why it happens:** Refactoring the endpoint path along with the simplification
**How to avoid:** Keep the route path `/health/ready` unchanged. The response body simplifies but the HTTP status code semantics (200=healthy, 503=unhealthy) stay the same.

### Pitfall 5: Pydantic Extra Fields Rejection
**What goes wrong:** If `readiness_cache_seconds` is removed from `AppConfig` but left in `config.yaml`, Pydantic will raise a validation error on startup (depending on `model_config` settings for extra fields)
**Why it happens:** Pydantic v2 `BaseSettings` rejects unknown fields by default
**How to avoid:** Remove `readiness_cache_seconds: 60` from `config/config.yaml` (confirmed present at line 6)

## Code Examples

### Current State (to be removed)

```python
# app/routers/health.py -- CURRENT (75 lines, complex)
# - ReadinessCache class (40 lines: async lock, TTL, error tracking)
# - _probe_llm function (creates AsyncOpenAI client, calls models.retrieve)
# - readiness handler (DB SELECT 1, LLM probe, composite status)
# Imports: asyncio, time, openai.AsyncOpenAI, sqlalchemy.text, sqlalchemy.ext.asyncio.AsyncSession
```

### Target State (replacement)

```python
# app/routers/health.py -- TARGET (~10 lines)
from fastapi import APIRouter
from starlette.responses import JSONResponse

router = APIRouter()


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "up"})
```

### Changes in app/main.py

```python
# REMOVE this import:
from routers.health import ReadinessCache

# REMOVE this line from lifespan():
app.state.readiness_cache = ReadinessCache(config.readiness_cache_seconds)
```

### Changes in app/config.py

```python
# REMOVE from AppConfig:
readiness_cache_seconds: int = Field(default=60, ge=1)
```

### Changes in config/config.yaml

```yaml
# REMOVE this line:
readiness_cache_seconds: 60
```

### New Test

```python
# tests/integration/test_health_endpoints.py
class TestHealthEndpoint:
    def test_health_ready_returns_up(self, client):
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "up"}
```

Note: The `client` fixture in `tests/conftest.py` does not currently include `health_router`. It will need to be added for health endpoint tests to work.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Deep health checks (DB, LLM probes) | Liveness/readiness separation | Industry standard | Kubernetes readiness probes should be fast and cheap; deep checks belong in separate monitoring |
| ReadinessCache with TTL | No cache needed | This phase | Removing the need for caching by removing expensive operations |

**Deprecated/outdated:**
- `ReadinessCache`: Purpose-built for caching expensive backend probes. Being removed entirely.
- `_probe_llm`: Instantiates a new `AsyncOpenAI` client per check. Wasteful and being removed.
- `readiness_cache_seconds` config: Dead config with no consumer after this phase.

## Open Questions

None. All questions resolved during research:
- `config/config.yaml` confirmed to contain `readiness_cache_seconds: 60` at line 6 -- must be removed
- `app/routers/__init__.py` exports only `router as health_router` -- no cleanup needed there
- No existing tests reference health endpoints -- only new tests needed

## Inventory of Changes

| File | Action | Details |
|------|--------|--------|
| `app/routers/health.py` | Rewrite | Remove ReadinessCache, _probe_llm, rewrite readiness handler (~75 lines -> ~10 lines) |
| `app/main.py` | Edit | Remove `ReadinessCache` import (line 16), remove `app.state.readiness_cache` assignment (line 48) |
| `app/config.py` | Edit | Remove `readiness_cache_seconds` field from `AppConfig` (line 59) |
| `config/config.yaml` | Edit | Remove `readiness_cache_seconds: 60` (line 6) |
| `tests/conftest.py` | Edit | Add `health_router` to the test `client` fixture's app |
| `tests/integration/test_health_endpoints.py` | Create | New test file for simplified health endpoint |

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of `app/routers/health.py`, `app/main.py`, `app/config.py`, `config/config.yaml`
- Direct analysis of `tests/conftest.py` and `tests/integration/conftest.py`
- Project ROADMAP.md phase 9 success criteria

### Secondary (MEDIUM confidence)
- FastAPI health endpoint patterns (standard practice, well-established)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries; purely deletion and simplification
- Architecture: HIGH - Trivial endpoint pattern; no design decisions beyond "return 200"
- Pitfalls: HIGH - All identified from direct codebase analysis of imports and references

**Research date:** 2026-02-27
**Valid until:** Indefinite (stable patterns, no external dependencies)
