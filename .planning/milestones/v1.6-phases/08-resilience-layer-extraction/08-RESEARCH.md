# Phase 8: Resilience Layer Extraction - Research

**Researched:** 2026-02-27
**Domain:** Structural refactor -- extracting resilience concerns from service orchestration
**Confidence:** HIGH

## Summary

Phase 8 is a structural refactor, not a technology adoption task. The goal is to extract the retry loop, circuit breaker coordination, and concurrency gating out of `AnalysisService._invoke()` and into a unified resilience layer that the service calls opaquely (e.g., `policy.invoke(operation)`). The service should not know about retries, circuit breaker state, or queue management -- it should just submit a callable and get back a result or an exception.

The current `AnalysisService.__init__` takes 12 parameters, 6 of which are resilience-related (`gate`, `circuit_breaker`, `timeout_seconds`, `retry_max_attempts`, `retry_backoff_base_seconds`, `retry_backoff_max_seconds`). The `_invoke` method is 28 lines of interleaved retry/circuit-breaker/timeout/gate logic. After this phase, `_invoke` should be a one-liner delegating to the resilience layer, and the constructor should accept a single resilience policy object instead of 6 separate parameters.

**Primary recommendation:** Build a custom `ResiliencePolicy` class in `app/resilience.py` that composes `CircuitBreaker`, `LLMExecutionGate`, retry-with-backoff, and timeout into a single `async invoke(operation)` method. Do not adopt external libraries (tenacity, pybreaker, etc.) -- the existing hand-rolled implementations are small, well-tested, and purpose-fit.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `asyncio` | 3.12 | Semaphore, timeout, sleep | Already used; no external dep needed |
| Pydantic `BaseModel` | 2.12+ | Config grouping for resilience settings | Already used for all config in this project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 9.1.4 | Retry with decorators | NOT recommended here -- adds dependency for 10 lines of retry logic |
| pybreaker | 2.0+ | Circuit breaker | NOT recommended -- existing CircuitBreaker is purpose-fit |
| circuitbreaker | 2.0+ | Circuit breaker decorator | NOT recommended -- same reason |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom `ResiliencePolicy` | tenacity + pybreaker + asyncio.Semaphore composed | Adds 2 runtime deps for ~80 lines of existing code that works; composition glue still needed |
| Single policy class | Decorator-based approach (tenacity `@retry`) | Decorators don't compose well with circuit breaker + gate; policy object gives explicit control |
| Moving retry into resilience.py | Keeping retry in service, extracting only CB+gate | Partial extraction -- service still knows about retries, violating the phase goal |

**Installation:**
```bash
# No new dependencies needed
```

## Architecture Patterns

### Current State (Before)
```
AnalysisService.__init__(
    ...
    gate: LLMExecutionGate,           # resilience
    circuit_breaker: CircuitBreaker,   # resilience
    timeout_seconds: float,            # resilience
    retry_max_attempts: int,           # resilience
    retry_backoff_base_seconds: float, # resilience
    retry_backoff_max_seconds: float,  # resilience
    ...
)

AnalysisService._invoke():
    for attempt in range(retry_max_attempts):
        circuit_breaker.before_call()
        try:
            gate.run(asyncio.wait_for(chain.ainvoke(...), timeout))
            circuit_breaker.record_success()
        except:
            circuit_breaker.record_failure()
            classify + backoff + retry
```

### Target State (After)
```
app/resilience.py:
    ResiliencePolicy(config: ResilienceConfig)
        async invoke(operation: Callable) -> T

app/config.py:
    ResilienceConfig(BaseModel):  # passive config, no behavior
        pool_size, queue_size, queue_retry_after_seconds,
        timeout_seconds, retry_max_attempts, retry_backoff_base_seconds,
        retry_backoff_max_seconds, circuit_breaker_failure_threshold,
        circuit_breaker_reset_seconds

app/services.py:
    AnalysisService.__init__(
        prompt, examples, llm, policy: ResiliencePolicy,
        history_max_*, message_max_chars, chats
    )

    AnalysisService._invoke():
        return await self.policy.invoke(lambda: chain.ainvoke(params))
```

### Pattern 1: Policy Object (Facade Pattern)
**What:** A single class that composes circuit breaker, gate, and retry logic behind one `invoke()` method. The caller provides a zero-argument async callable; the policy handles all resilience wrapping.
**When to use:** When multiple resilience concerns must be applied in a specific order to every external call.
**Example:**
```python
class ResiliencePolicy:
    def __init__(self, config: ResilienceConfig):
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            reset_seconds=config.circuit_breaker_reset_seconds,
        )
        self._gate = LLMExecutionGate(
            max_concurrency=config.pool_size,
            max_queue=config.queue_size,
            retry_after_seconds=config.queue_retry_after_seconds,
        )
        self._timeout_seconds = config.timeout_seconds
        self._retry_max_attempts = config.retry_max_attempts
        self._retry_backoff_base = config.retry_backoff_base_seconds
        self._retry_backoff_max = config.retry_backoff_max_seconds

    async def invoke(self, operation: Callable[[], Awaitable]) -> Any:
        for attempt in range(1, self._retry_max_attempts + 1):
            await self._circuit_breaker.before_call()
            try:
                async def timed_op():
                    return await asyncio.wait_for(operation(), timeout=self._timeout_seconds)

                result = await self._gate.run(timed_op)
                await self._circuit_breaker.record_success()
                return result
            except (QueueFullError, CircuitOpenError):
                raise
            except Exception as e:
                await self._circuit_breaker.record_failure()
                if attempt >= self._retry_max_attempts or not _is_transient_error(e):
                    if _is_transient_error(e):
                        raise TransientLLMError(str(e)) from e
                    raise PermanentLLMError(str(e)) from e
                backoff = min(
                    self._retry_backoff_max,
                    self._retry_backoff_base * (2 ** (attempt - 1)),
                )
                if backoff > 0:
                    await asyncio.sleep(backoff)
        raise TransientLLMError("LLM request failed after all retries")
```

### Pattern 2: Passive Config Grouping
**What:** A Pydantic `BaseModel` that groups all resilience-related settings without any behavior -- just data.
**When to use:** When config fields are scattered across a parent model and need to be extracted into a cohesive group.
**Example:**
```python
class ResilienceConfig(BaseModel):
    pool_size: int = Field(default=5, ge=1)
    queue_size: int = Field(default=25, ge=1)
    queue_retry_after_seconds: int = Field(default=2, ge=1)
    timeout_seconds: float = Field(default=30.0, gt=0)
    retry_max_attempts: int = Field(default=3, ge=1)
    retry_backoff_base_seconds: float = Field(default=0.5, ge=0)
    retry_backoff_max_seconds: float = Field(default=4.0, ge=0)
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_reset_seconds: int = Field(default=60, ge=1)
```

### Anti-Patterns to Avoid
- **Config object with behavior:** `AnalysisSettings` (or similar) should NOT contain `invoke()`, `run()`, or factory methods. Config is data; policy is behavior. Keep them separate.
- **Half-extraction:** Moving only CircuitBreaker/Gate out but leaving retry loop in `_invoke` defeats the goal. The service should not contain ANY resilience logic.
- **Leaking exception classification into the service:** `_is_transient_error` belongs in the resilience layer. The service should not import or call it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with backoff | New retry framework | Existing retry loop (move it into ResiliencePolicy) | 10 lines, already correct, tested |
| Circuit breaker | New CB implementation | Existing CircuitBreaker class (already in resilience.py) | Purpose-fit, async-native, tested |
| Concurrency limiting | New gate system | Existing LLMExecutionGate (already in resilience.py) | Semaphore + queue pattern, tested |

**Key insight:** This phase is about reorganization, not reimplementation. The existing resilience code works. The task is to compose it behind a facade and remove it from the service's awareness.

## Common Pitfalls

### Pitfall 1: Breaking Exception Semantics
**What goes wrong:** The error handler layer (`app/errors.py`) catches `QueueFullError`, `CircuitOpenError`, `TransientLLMError`, and `PermanentLLMError` specifically. If the resilience policy swallows these or wraps them differently, HTTP status codes change.
**Why it happens:** When moving exception handling code, it's easy to accidentally catch exceptions too broadly or re-wrap them.
**How to avoid:** The resilience policy must re-raise `QueueFullError` and `CircuitOpenError` as-is (not wrapped). It must raise `TransientLLMError` and `PermanentLLMError` as the final classification -- exactly as `_invoke` does today.
**Warning signs:** Tests that check HTTP 503 with `Retry-After` headers start failing.

### Pitfall 2: Breaking Test Mock Paths
**What goes wrong:** Tests patch `app.services._is_transient_error`. After moving the function call into `ResiliencePolicy`, the patch path changes.
**Why it happens:** Python `mock.patch` targets the namespace where the name is looked up, not where it's defined.
**How to avoid:** If `_is_transient_error` is now called inside `ResiliencePolicy` (in `app.resilience`), patch `app.resilience._is_transient_error` instead. Update `tests/unit/test_services.py` line 133.
**Warning signs:** `test_transient_llm_error_exhausted` fails because the mock doesn't intercept the call.

### Pitfall 3: Constructor Signature Breakage
**What goes wrong:** Every place that constructs `AnalysisService` (main.py, tests/conftest.py, tests/unit/test_services.py, tests/integration/conftest.py) must be updated. Missing one causes `TypeError`.
**Why it happens:** 4 separate files construct `AnalysisService` with the full parameter list.
**How to avoid:** Search for all `AnalysisService(` occurrences and update them all. Use `grep -r "AnalysisService(" app/ tests/` to find them.
**Warning signs:** Import or instantiation errors in tests.

### Pitfall 4: Timeout Closure Bug
**What goes wrong:** The `timed_op` closure inside `invoke()` captures `operation` by reference. If `operation` is redefined in a loop, all closures point to the same callable.
**Why it happens:** Python closures capture variables, not values.
**How to avoid:** `operation` is a parameter, not a loop variable, so this is safe in the current design. But be careful if refactoring to process multiple operations.
**Warning signs:** Wrong operation executed under timeout.

## Code Examples

### Current _invoke (to be replaced)
```python
# Source: app/services.py lines 84-112 (current state)
async def _invoke(self, chain, params: dict):
    for attempt in range(1, self.retry_max_attempts + 1):
        await self.circuit_breaker.before_call()
        try:
            async def operation():
                return await asyncio.wait_for(chain.ainvoke(params), timeout=self.timeout_seconds)
            response = await self.gate.run(operation)
            await self.circuit_breaker.record_success()
            return response
        except QueueFullError:
            raise
        except CircuitOpenError:
            raise
        except Exception as e:
            await self.circuit_breaker.record_failure()
            if attempt >= self.retry_max_attempts or not _is_transient_error(e):
                if _is_transient_error(e):
                    raise TransientLLMError(str(e)) from e
                else:
                    raise PermanentLLMError(str(e)) from e
            backoff = min(
                self.retry_backoff_max_seconds,
                self.retry_backoff_base_seconds * (2 ** (attempt - 1)),
            )
            if backoff > 0:
                await asyncio.sleep(backoff)
    raise TransientLLMError("LLM request failed after all retries")
```

### Target _invoke (after refactor)
```python
# Target: app/services.py after Phase 8
async def _invoke(self, chain, params: dict):
    return await self.policy.invoke(lambda: chain.ainvoke(params))
```

### Target main.py wiring

```python
# Target: app/main.py lifespan after Phase 8
from resilience import ResiliencePolicy
from config import ResilienceConfig  # or however config is structured

# ResilienceConfig extracted from ModelConfig or co-located
resilience_config = ResilienceConfig(
    pool_size=config.model.pool_size,
    queue_size=config.model.queue_size,
    # ... all resilience fields
)
policy = ResiliencePolicy(resilience_config)

app.state.service = AnalysisService(
    prompt=config.prompt,
    examples=config.examples,
    llm=llm,
    policy=policy,
    history_max_human_messages=config.history_max_human_messages,
    history_max_assistant_messages=config.history_max_assistant_messages,
    message_max_chars=config.message_max_chars,
    chats=chats,
)
```

### Target test fixture

```python
# Target: tests/conftest.py and tests/unit/test_services.py
from resilience import ResiliencePolicy

policy = ResiliencePolicy(ResilienceConfig(
    pool_size=1,
    queue_size=1,
    queue_retry_after_seconds=1,
    timeout_seconds=1,
    retry_max_attempts=1,
    retry_backoff_base_seconds=0,
    retry_backoff_max_seconds=0,
    circuit_breaker_failure_threshold=3,
    circuit_breaker_reset_seconds=60,
))
service = AnalysisService(
    prompt="...",
    examples=examples,
    llm=mock_llm,
    policy=policy,
    history_max_human_messages=50,
    history_max_assistant_messages=50,
    message_max_chars=4096,
    chats=mock_chats,
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline retry/CB in service methods | Policy object pattern (Polly/.NET, resilience4j/Java) | ~2018 (Polly v7), ~2019 (resilience4j) | Python ecosystem never unified; hand-roll composition is standard |
| Separate retry + CB + gate libraries | Compose behind facade | Ongoing | No Python "Polly" exists; custom facade is the pragmatic pattern |
| tenacity decorators for retry | tenacity still standard for general retry | Stable since 2020 | Not applicable here -- existing retry logic is tightly coupled with CB state |

**Deprecated/outdated:**
- None relevant -- the existing code doesn't use any deprecated APIs.

## Open Questions

1. **Config naming: `ResilienceConfig` vs keeping fields in `ModelConfig`**
   - What we know: Currently all resilience fields live in `ModelConfig`. Phase goal says "AnalysisSettings (or equivalent) is a passive config grouping."
   - What's unclear: Whether to extract a new `ResilienceConfig` from `ModelConfig`, or rename `ModelConfig`, or nest `ResilienceConfig` inside `ModelConfig`.
   - Recommendation: Extract `ResilienceConfig` as a separate `BaseModel` and nest it inside `ModelConfig` as `resilience: ResilienceConfig`. This preserves YAML structure compatibility and makes the config grouping explicit. Alternatively, keep fields flat in `ModelConfig` and just pass them to `ResiliencePolicy` constructor -- simpler, less structural change.

2. **Where does timeout belong?**
   - What we know: `timeout_seconds` is currently a service parameter that wraps the chain invocation in `asyncio.wait_for`. It's a resilience concern (preventing hung calls).
   - What's unclear: Whether the caller should apply timeout or the policy should.
   - Recommendation: Timeout belongs in the policy. The policy already handles retry and circuit breaker; timeout is the third leg of the resilience triangle.

## Impact Inventory

Files that reference resilience components and need changes:

| File | Current References | Required Change |
|------|-------------------|-----------------|
| `app/resilience.py` | `CircuitBreaker`, `LLMExecutionGate`, `_is_transient_error`, `_extract_status_code` | Add `ResiliencePolicy` class; keep internal classes |
| `app/services.py` | Imports `CircuitBreaker`, `LLMExecutionGate`, `_is_transient_error`; constructor takes 6 resilience params; `_invoke` has 28-line resilience loop | Replace 6 params with `policy: ResiliencePolicy`; reduce `_invoke` to 1-line delegation; remove resilience imports |
| `app/config.py` | `ModelConfig` contains all resilience fields | Optionally extract `ResilienceConfig`; or leave as-is and construct policy from `ModelConfig` fields |
| `app/main.py` | Constructs `CircuitBreaker`, `LLMExecutionGate`, passes 6 params to `AnalysisService` | Construct `ResiliencePolicy` instead; pass single `policy` param |
| `tests/conftest.py` | Imports `CircuitBreaker`, `LLMExecutionGate`; constructs with 6 resilience params | Import `ResiliencePolicy`; construct with policy |
| `tests/unit/test_services.py` | Imports `CircuitBreaker`, `LLMExecutionGate`; constructs with 6 resilience params; patches `app.services._is_transient_error` | Import `ResiliencePolicy`; update patch path to `app.resilience._is_transient_error` |
| `tests/integration/conftest.py` | Imports `CircuitBreaker`, `LLMExecutionGate`; constructs with 6 resilience params | Import `ResiliencePolicy`; construct with policy |
| `app/exceptions.py` | Defines `CircuitOpenError`, `QueueFullError`, `TransientLLMError`, `PermanentLLMError` | No change -- exceptions stay where they are |
| `app/errors.py` | Handles `CircuitOpenError`, `QueueFullError`, `TransientLLMError`, `PermanentLLMError` | No change -- handlers stay as-is |

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis -- `app/resilience.py`, `app/services.py`, `app/config.py`, `app/main.py`, all test files
- Existing quick plan `.planning/quick/2-move-circuitbreaker-and-other-non-busine/2-PLAN.md` -- confirms resilience code was already extracted to `app/resilience.py` in a prior step

### Secondary (MEDIUM confidence)
- [Polly resilience pipelines documentation](https://www.pollydocs.org/pipelines/) -- inspiration for the policy/pipeline pattern
- [tenacity documentation](https://tenacity.readthedocs.io/) -- confirmed tenacity 9.1.4 is current; not recommended for this refactor
- [pybreaker GitHub](https://github.com/danielfm/pybreaker) -- confirmed existing; not recommended for this refactor

### Tertiary (LOW confidence)
- None -- all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries needed; pure structural refactor using existing code
- Architecture: HIGH - policy object/facade pattern is well-understood; target state is clear from codebase analysis
- Pitfalls: HIGH - all 4 pitfalls identified from direct code inspection of import paths, exception handlers, and constructor call sites

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable -- no external dependencies to track)
