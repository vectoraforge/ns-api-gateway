---
title: An admitted request burns all retries against a provider the breaker already opened
area: resilience
created: 2026-08-31
source: Phase 37.5 code review (WR-02), 37.5-REVIEW.md
status: open
---

# An admitted request burns all retries against a dead provider

`before_call()` used to be the first line of `attempt()`, so the circuit breaker was
consulted on every attempt. Phase 37.5's admission refactor moved it to run once, at
admission time.

**Consequence:** a request that passes admission and then sees the breaker open
mid-flight still spends all three attempts (~91.5s) against a provider already
declared dead. `AGENTS.md` § Resilience names avoiding exactly that cost as the
breaker's purpose, so the code now contradicts the rule this phase wrote down.

Related dead code: `except (QueueFullError, CircuitOpenError): raise` in `attempt()`
is now unreachable — neither exception can originate inside that `try` any more
(WR-03). Remove it with the fix, or restore the per-attempt check that makes it
reachable again.

**Scope when picked up:** decide whether the breaker is an admission-time gate or a
per-attempt gate, make the code say so, and align the `AGENTS.md` § Resilience
wording with whichever is chosen.
