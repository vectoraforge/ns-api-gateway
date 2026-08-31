# ns-api-gateway

## Comments and docstrings

These rules bind all code in this repository. They supersede the dense prose
register introduced by Phase 37.1 (D-16).

**Docstrings — three lines maximum.** State what the function, class, or module
does. Nothing else.

Do not describe what lives somewhere else, what the entity is not, or how the
application works in general. A docstring like `"The getUser providerData read,
and nothing else: token verification and revocation live elsewhere."` fails on
every count: it is not a sentence, and it defines the subject by naming code
that is not in it.

**Comments — only where they are necessary**, to resolve a genuine ambiguity or
prevent a misreading. Default to none.

**One line each.** A comment explains the specific line or lines below it. It
never explains the design, the request lifecycle, a rule enforced in another
module, or a decision that was made elsewhere.

## Package layout

Every file has exactly one home, decided by what the file is and not by which
feature it serves.

- `services/` — business logic: orchestration, rules, transaction boundaries.
- `crud/` — database access.
- `schemas/` — Pydantic request and response bodies, and domain value types.
- `tables/` — SQLModel tables and the enums mirroring database types.
- `routers/` — HTTP handlers, `Depends()` only.
- `auth/` — external-SDK seams only: `adapters.py`, `firebase.py` and
  `jwt_verifier.py`.

Four exceptions, each a rule and not a story:

1. `errors.py` owns the client-visible error response shape, the statuses, the
   copy and the handlers. Nothing about errors moves to `schemas/`. Ground:
   `SHARED-INVARIANTS.md` § Errors — one shared registry.
2. `BoundedReason` stays in `auth/jwt_verifier.py`. Moving it to `schemas/`
   creates an import cycle, because `errors.py` imports it.
3. `commit()` and `rollback()` are transaction boundaries and therefore
   business logic; they live in `services/`, not in `crud/`.
4. A fail-closed read may raise its own rejection, so the rejection stays with
   the query in `crud/`.

## Function shape

Delete a function that is only a step. Keep one that states a rule or marks a
boundary, where a boundary is a lock, a transaction, or a callable a library
requires.

**The check:** inline it, then read the call site. If the call site now needs a
comment to explain what the code does, the name was carrying meaning and the
function stays.

A recursive function is never a step, because it cannot be inlined.

## Resilience

`CircuitBreaker` and `LLMExecutionGate` in `resilience.py` are deliberate. They
are not awaiting replacement.

The retry loop is already `tenacity`, and `tenacity` bounds one request — three
attempts at a 30s timeout plus backoff, about 91.5s. It bounds nothing across
requests, so without the breaker every request during a provider outage pays
that from scratch. Nothing installed replaces a circuit breaker, so finishing
the idea means a new dependency. And without the breaker a client is told to
retry in 2 seconds while the provider is down.

The `limits` library is mandated by `SHARED-INVARIANTS.md` § Rate limits and was
overridden by Phase 35 D-05: the backend rate-limit engine is deleted from the
product, not deferred.
