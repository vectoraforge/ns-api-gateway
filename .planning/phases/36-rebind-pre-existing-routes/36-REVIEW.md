---
phase: 36-rebind-pre-existing-routes
reviewed: 2026-08-21T00:00:00Z
depth: standard
files_reviewed: 29
files_reviewed_list:
  - migrations/20260818_01_initial-release.sql
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/auth/registry.py
  - src/nativespeaker/api/database/grants.py
  - src/nativespeaker/api/database/__init__.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/models/grants.py
  - src/nativespeaker/api/models/__init__.py
  - src/nativespeaker/api/models/llm.py
  - src/nativespeaker/api/quota.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/services/chats.py
  - tests/e2e/conftest.py
  - tests/e2e/test_audit_writer.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_error_cases.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_isolation.py
  - tests/e2e/test_quota.py
  - tests/schema/conftest.py
  - tests/schema/helpers.py
  - tests/schema/test_apply_rollback.py
  - tests/schema/test_constraints.py
  - tests/schema/test_grant_locks.py
  - tests/unit/conftest.py
  - tests/unit/test_models.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_route_registry.py
  - tests/unit/test_users.py
findings:
  critical: 2
  warning: 7
  info: 5
  total: 14
status: issues_found
---

# Phase 36: Code Review Report

**Reviewed:** 2026-08-21
**Depth:** standard
**Files Reviewed:** 29
**Status:** issues_found

## Summary

The quota core is, on its own terms, correct. I traced the lock path end to end and could not
break it: `lock_effective_grants` takes `FOR UPDATE` on the grant rows with `ORDER BY id ASC`
(PostgreSQL puts `LockRows` above `Sort`, so rows really are locked in sorted order), `lock_usage`
runs second on a row the grant lock already serialises, and two concurrent POSTs for the same user
therefore cannot double-spend — the second blocks on the grant row and re-reads `monthly_used`
after the first commits. The `max(allowance - used, 0)` floor is right, rollover happens strictly
before the comparison and inside the same transaction, and every fail-closed branch (`no grant`,
`>1 grant`, `missing usage row`, `unknown tier`) resolves to the intended status. I also verified
against the installed FastAPI 0.135.1 that the D-14 mitigation actually works: `solve_dependencies`
does `if solved_result.errors: errors.extend(...); continue`, so a wrapper whose own body/path
params fail validation is never called — no credit is spent on a 422.

What the phase got wrong is not inside `consume_quota`. It is the **boundary**: the credit is
committed unconditionally before dispatch, and the executors reasoned about only one of the ways
the request can then fail. D-11's justification ("a rare provider failure") does not cover
`CircuitOpenError` and `QueueFullError`, which are raised as **backpressure before any provider
call is made**, return 503 with a `Retry-After` that instructs the client to retry, and are by
design a sustained multi-request state — so a single circuit-open window charges every request in
it and delivers nothing (CR-01). Nor does it cover the 400s the app itself produces after the
charge; `ChatRequest.lang` is unvalidated free text, so a one-character typo drains a paying user's
allowance one 400 at a time (CR-02). The recorded REBIND-06 divergence covers only the 404 arm of
this same family.

On the test side, the suite is unusually strong (the deadlock/lock-order schema tests and the
compiled-SQL assertions are genuinely load-bearing), but it has a specific hole worth naming: the
compiled-predicate assertions pin `starts_at`, `ends_at`, `FOR UPDATE` and `ORDER BY` but **not
`user_id`**, and no e2e case ever has two users holding active grants at once — so a regression
that let one user spend another user's allowance would pass the entire suite (WR-01).

`ruff check` and `ty check src` are both clean.

## Critical Issues

### CR-01: 503 backpressure rejections spend a credit and tell the client to retry

**File:** `src/nativespeaker/api/app/dependencies.py:133-144`, `src/nativespeaker/api/resilience.py:56`, `src/nativespeaker/api/resilience.py:86`, `src/nativespeaker/api/quota.py:22-26`

**Issue:** `require_quota` commits the increment in its own transaction before the handler body is
entered. Two of the failure modes downstream of that commit never touch the provider at all:

- `CircuitBreaker.before_call()` (`resilience.py:56`) raises `CircuitOpenError` for the whole
  `reset_seconds` window, before any LLM work.
- `LLMExecutionGate._inflight_slot()` (`resilience.py:86`) raises `QueueFullError` when the local
  in-process slot queue is exhausted, before any LLM work.

Both map to `SERVICE_UNAVAILABLE` (503) and both attach a `Retry-After` header
(`errors.py:350-351`, `errors.py:361-362`) whose copy is *"The service is busy. Wait for the
indicated interval and retry."* So the service charges a credit, delivers nothing, and explicitly
instructs the client to spend another one.

`quota.py:22-26` justifies non-refund as *"this product would rather lose one credit on a rare
provider failure than serialise every caller behind a network call."* That reasoning does not hold
here. Circuit-open and queue-full are not rare single-request failures — they are sustained states
that reject **every** request for their duration, by design. A `paid` user (1000 credits) behind a
5-minute circuit-open window with a client honouring `Retry-After` loses credits at the retry rate
for the whole window while receiving zero analyses. That is direct loss of purchased value on a
subscription product, and it is invisible: nothing in the 503 body or headers tells the client a
credit was taken.

No test covers it. `tests/e2e/test_quota.py` asserts the counter after 200, 429, 422 and 500, but
never after a 503.

**Fix:** Move the backpressure admission ahead of the charge, or compensate. The cheapest correct
option is to have `require_quota` refund on the two pre-provider rejections, since they are
distinguishable by class and carry no provider cost:

```python
# routers/chats.py -- gate admission before the credit is committed
@router.post("/chats", dependencies=[Depends(require_quota_create_chat)], ...)
```
becomes, in `app/dependencies.py`:

```python
async def require_quota(request: Request, context: RequestContext) -> None:
    ...
    # Backpressure is not a provider failure and costs the provider nothing. Refuse
    # BEFORE the charge so a circuit-open window cannot drain a paying allowance.
    request.app.state.llm_service.assert_admitting()   # raises CircuitOpenError / QueueFullError

    async with request.app.state.session_factory() as session:
        ...
```

with a matching non-consuming probe on `ResiliencePolicy` (peek at `_opened_at` and at
`_slots.qsize()`), and a `tests/e2e` case that forces the circuit open and asserts
`monthly_used` is unchanged across the 503. If a probe is judged too racy, the alternative is an
explicit compensating decrement in an exception handler for `CircuitOpenError`/`QueueFullError`
only — but a probe is preferable because it keeps the "never refund" rule intact for genuine
provider failures.

### CR-02: `lang` is unvalidated free text, so a 400 the app itself produces still burns a credit

**File:** `src/nativespeaker/api/models/api.py:18`, `src/nativespeaker/api/services/chats.py:85-90`, `tests/e2e/test_error_cases.py:60-71`

**Issue:** `ChatRequest.lang: str | None = Field(default=None)` accepts any string. The supported
set is only checked inside `ChatService.create_chat`:

```python
if lang and lang not in self.supported_languages:
    raise UnsupportedLanguageError(lang, self.supported_languages)
```

That runs *after* `require_quota` has already committed. So
`POST /chats {"phrase": "x", "lang": "zz"}` returns **400 `invalid_request`** and permanently
consumes one credit, with no LLM call and no service rendered. The same shape applies to
`ChatHistoryLimitError` (`services/chats.py:88-90`, chats-limit) and `ChatHistoryLimitError` on
`send_message` (`services/chats.py:112-113`) — both are 400s the app produces from state it could
have consulted before charging.

This is the same root cause as the recorded REBIND-06 divergence, but it is a *different, cheaper
and more reachable* arm: REBIND-06 needs a syntactically valid UUID naming a nonexistent chat;
this needs a two-character typo in a language code that the API never told the client was invalid.
A client with a stale language list drains the allowance in as many requests as it has credits.

`quota.py:143-147` states the intended rule explicitly — *"a request the service refused must
never be charged"* — and this violates it. Worse, `tests/e2e/test_error_cases.py:60-71` was
*modified in this phase* to seed `quota_grant` so the 400 branch is reachable, and asserts only the
status code; the charge it now makes is silently accepted and untested.

**Fix:** Move the language check ahead of the charge by making it a request-model constraint, so
FastAPI rejects it while solving the wrapper (the same D-14 mechanism that already protects the
body and path):

```python
# models/api.py -- the supported set is config-driven, so validate against it at the seam
class ChatRequest(BaseModel):
    phrase: str = Field(..., max_length=4096)
    context: str | None = Field(default=None, max_length=4096)
    lang: str | None = Field(default=None, max_length=8, pattern=r"^[a-z]{2}$")
```

The pattern alone reduces the blast radius to two-letter codes; the complete fix is to have
`require_quota_create_chat` consult `config.examples` before calling `require_quota`, and to add an
e2e case asserting `monthly_used` is unchanged across the 400. The chats-limit and messages-limit
checks should likewise be hoisted ahead of the charge (both are pure reads).

## Warnings

### WR-01: Nothing constrains the `user_id` scoping of the effective-grant predicate

**File:** `src/nativespeaker/api/database/grants.py:38`, `tests/unit/test_quota_resolver.py:286-330`, `tests/e2e/test_quota.py:1-30`

**Issue:** `TestTheLockingStatements` asserts the compiled predicate contains
`starts_at <= `, `ends_at > `, `ends_at IS NULL`, `FOR UPDATE` and `ORDER BY ... ASC`. It does not
assert `core.access_grants.user_id = `. The stub session (`_StubSession.exec`) ignores the `WHERE`
clause entirely and dispatches rows by target entity, so it cannot notice a missing filter either.

The e2e suite does not close the gap: `linked_firebase_identity` seeds a fresh user per test, and
in every case at most **one** active grant exists inside the per-test transaction — including
`tests/e2e/test_isolation.py`, where only `STRANGER` gets a grant. Delete
`col(AccessGrant.user_id) == user_id` from `grants.py:38` and the whole suite still passes: the
single active grant is found and charged regardless of who asked. The `status` filter *is* covered
(`test_a_grant_whose_status_is_not_active_is_no_grant` seeds revoked/expired rows), so the hole is
specifically the tenant scoping — the one predicate term whose failure is a cross-user
entitlement leak rather than a self-inflicted error.

**Fix:** Add the missing compiled-SQL assertion, and a behavioural control with two users:

```python
# tests/unit/test_quota_resolver.py::TestTheLockingStatements
async def test_the_predicate_is_scoped_to_the_caller(self):
    session = await self._admitted_session()
    sql = _compiled(session.statements[0])
    assert "core.access_grants.user_id = " in sql
    assert "core.access_grants.status = " in sql

# tests/e2e/test_quota.py -- the behavioural control
async def test_another_users_grant_is_not_spendable(self, async_client,
                                                    linked_firebase_identity, _db_transaction):
    other, _ = await seed_identity(_db_transaction, issuer=..., subject="someone-else")
    other_grant, _ = await seed_grant(_db_transaction, user_id=other.id)   # caller has none

    response = await async_client.post("/chats", json=PHRASE)

    assert response.status_code == 429
    assert [r.monthly_used for r in await usage_rows(_db_transaction, other_grant.id)] == [0]
```

### WR-02: Registry condition 10 accepts *any* quota wrapper on *any* flagged route

**File:** `src/nativespeaker/api/auth/registry.py:147`, `src/nativespeaker/api/auth/registry.py:215-231`

**Issue:** `quota_wrappers` is a flat tuple and the membership test is
`any(dependency.dependency is wrapper for dependency in route.dependencies for wrapper in quota_wrappers)`.
The resulting `attached` set records only `(method, path)`. So a route that declares
`quota_checked=True` and carries the **wrong** wrapper passes boot cleanly. Concretely, putting
`Depends(require_quota_send_message)` on `POST /chats` satisfies condition 10, but the wrapper
declares `chat_id: UUID`, which on a path with no `{chat_id}` placeholder becomes a **required
query parameter** — every request to the product's primary route would 422. The assertion that
exists precisely to stop wrapper/flag drift would not have said a word.

`tests/unit/test_route_registry.py::TestCondition10QuotaFlagAndDependencyDisagree` covers both set
directions but has no wrong-wrapper case, so the gap is unpinned in either direction.

**Fix:** Key the wrapper table by route rather than by set membership:

```python
QUOTA_WRAPPERS: dict[tuple[str, str], Callable[..., Any]] = {
    ("POST", "/chats"): require_quota_create_chat,
    ("POST", "/chats/{chat_id}"): require_quota_send_message,
}
...
for route in app.routes:
    if not isinstance(route, APIRoute):
        continue
    for method in route.methods:
        expected = QUOTA_WRAPPERS.get((method, route.path))
        got = [d.dependency for d in route.dependencies
               if d.dependency in QUOTA_WRAPPERS.values()]
        if expected is not None and expected not in got:
            problems.append(f"{(method, route.path)} carries {got}, expected {expected.__name__}")
```

### WR-03: `ask_llm` calls `.get()` on unvalidated provider output

**File:** `src/nativespeaker/api/services/chats.py:53`

**Issue:** `llm_response` comes from a plain `JsonOutputParser()` (`services/llm.py:29`) with no
schema binding, so it is whatever JSON value the model emitted — including a list, a string or a
number. `llm_response.get("resolved_mode")` then raises `AttributeError`, which is not a
`ServiceError`, so it falls to `generic_error_handler` and surfaces as an unlabelled 500 — plus a
burned credit under D-11.

This function was edited in this phase for exactly this class of defect (D-35-11-A: "the product's
primary route answered 500 for an already-correct sentence"), and the same fix was applied only to
the missing-list case. The non-dict case is one line away and was left open.

**Fix:**

```python
if not isinstance(llm_response, dict):
    raise AnalysisError(f"Provider returned {type(llm_response).__name__}, not an object")
resolved_mode = llm_response.get("resolved_mode")
```

### WR-04: `docker-compose.yml` now depends on undocumented env vars and sprays every secret into the DB container

**File:** `docker-compose.yml:2-4`, `.env.example`

**Issue:** The phase replaced the (admittedly broken) literal `POSTGRES_USER: {DB_USER}` block with
`env_file: - .env`. Two consequences:

1. **Broken from a clean clone.** `.env.example` defines `DB_USER`/`DB_PASSWORD`/`DB_NAME`, not
   `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`. The developer's working `.env` happens to
   carry both sets, which is why nobody noticed. `cp .env.example .env && docker compose up db`
   exits with *"Database is uninitialized and superuser password is not specified"*, and the
   schema and e2e suites — which both need a live Postgres — cannot be run at all.
2. **Least privilege.** `env_file` injects the *entire* file, so `OPENAI_API_KEY`, `JWT_API_KEY`
   and `FIREBASE_TEST_PASSWORD` are now present in the Postgres container's environment and
   readable via `docker inspect` / `/proc/1/environ`. The database needs none of them. AGENTS.md
   permits skipping high-value-theft defences, not handing every secret to every container.

**Fix:** Name only what Postgres needs, and add the three vars to `.env.example`:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
```

`${VAR}` interpolation reads the same `.env` Compose already loads, keeps the existing `DB_*` names
that `[tool.pogo]` in `pyproject.toml` also uses, and passes nothing else through.

### WR-05: A live-LLM assertion on empty `issues`/`suggestions` is flaky by construction

**File:** `tests/e2e/test_quota.py:386-394`

**Issue:** `test_a_correct_phrase_returns_200_with_empty_issue_and_suggestion_lists` sends
`"I am going home."` to the real model and asserts `content["issues"] == []` **and**
`content["suggestions"] == []`. Nothing constrains the model to return neither. An unconstrained
chain (the module's own premise) may legitimately volunteer a stylistic suggestion for a correct
sentence, and the case then fails for a reason unrelated to D-12. The property actually under test
— that the two keys are *present* and default to `[]` when the provider omits them — is already
proven deterministically at the model layer by
`tests/unit/test_models.py::TestAnalyzeResponse::test_validates_payload_omitting_both_lists`.

**Fix:** Assert presence and type over the transport, and leave emptiness to the unit case:

```python
assert response.status_code == 200
content = response.json()["content"]
assert isinstance(content["issues"], list)        # the keys exist -- D-12's transport claim
assert isinstance(content["suggestions"], list)
assert set(content) == {"resolved_mode", "response", "issues", "suggestions"}  # extras dropped
```

### WR-06: The schema lock suite commits into a shared database with no pre-clean

**File:** `tests/schema/test_grant_locks.py:82-122`

**Issue:** `committed_grant` is the only fixture in the repo that commits outside the rolled-back
`conn` harness (necessarily so — uncommitted rows are invisible to the second connection). Cleanup
is a `finally`, which covers assertion failures and deadlocks, but not process death: a `Ctrl-C`, a
`pytest-timeout` kill, or an OOM between the commit and the `finally` leaves a `core.users`, a
`core.access_grants`, a `core.user_monthly_usage` and a `core.access_tiers` row behind. The next
run then fails in a *different module* —
`test_apply_rollback.py::TestHarnessIsolation::test_previous_test_rows_were_rolled_back` and
`test_only_the_seeded_tiers_survive` — with a message that points at transaction rollback rather
than at the module that actually leaked.

**Fix:** Make the fixture self-healing at setup, so a leak from a previous run is repaired rather
than inherited:

```python
setup = await asyncpg.connect(_schema_db_uri)
try:
    # Repair a leak from an interrupted previous run before seeding this one.
    await setup.execute("DELETE FROM core.access_tiers WHERE id LIKE 'tier_%'")
    user_id = await insert_user(setup)
    ...
```

(`core.users` / `core.access_grants` cascade from the tier delete's dependents only if the grant is
removed first, so delete grants-by-tier before the tier.)

### WR-07: The e2e harness cannot prove D-04's independent commit

**File:** `tests/e2e/conftest.py:92-115`

**Issue:** `_db_transaction` binds every session — `require_quota`'s "own" session and the
handler's `get_db` session — to a single connection with
`join_transaction_mode="create_savepoint"`. Both "commits" are savepoint releases inside one outer
transaction. That is correct for rollback isolation, but it means the property D-04 exists to buy
is untestable here: *the quota increment is durable even when the handler's transaction rolls
back*. Every e2e assertion in `test_quota.py` would read identically if `require_quota` had taken
`Depends(get_db)` instead — the exact wiring the module docstring forbids. The suite therefore
constrains the *observable ordering* of the charge but not its *transactional independence*, which
is the load-bearing half of the decision (and the half whose failure would silently reintroduce
grant locks held across the provider round trip).

**Fix:** Prove it in `tests/schema/`, which is the one package with genuinely independent
connections — e.g. two asyncpg connections replicating the charge-then-fail sequence, asserting
`monthly_used` survives after connection B's transaction rolls back. Failing that, record the gap
explicitly in the module docstring so a later phase does not read `test_quota.py` as covering it.

## Info

### IN-01: `_StubSession` / `_StubResult` are duplicated across two test packages

**File:** `tests/unit/test_quota_resolver.py:51-100`, `tests/e2e/test_quota.py:495-510`

**Issue:** Two independent stub-session implementations with the same names and overlapping
purpose. The e2e copy is a degenerate version (always returns `[]`). Its one test —
`TestTheEffectiveGrantStatement` — duplicates
`tests/unit/test_quota_resolver.py::TestTheLockingStatements` and needs no database, so it does not
belong in an `e2e`-marked module at all.

**Fix:** Delete `TestTheEffectiveGrantStatement` and both stub classes from `tests/e2e/test_quota.py`;
the unit module already asserts `FOR UPDATE`, `ORDER BY ... ASC` and the absence of a cap.

### IN-02: The grants model layer reads the system clock its own data layer forbids

**File:** `src/nativespeaker/api/models/grants.py:86-87`, `:105`, `:108-109`, `:125-126`

**Issue:** `database/grants.py:12-14` states *"Nothing here reads the system clock"* as a module
invariant, but the models it returns carry `default_factory=lambda: datetime.now(UTC)` on
`starts_at`, `created_at` and `updated_at`. Nothing on the quota path constructs these (the
resolver only mutates rows it loaded), so it is currently harmless — but Phases 41/42/45 will
construct them, and the ambient clock is exactly what D-06 exists to eliminate.

**Fix:** Note in the model docstring that construction sites must pass `evaluated_at` explicitly
and that the factories are an insert-time backstop only, or drop the factory on `starts_at` (the
database already has `DEFAULT CURRENT_TIMESTAMP` for it).

### IN-03: `require_quota`'s pre-auth guard is unreachable

**File:** `src/nativespeaker/api/app/dependencies.py:124-129`

**Issue:** Both quota-checked routes are `Category.authenticated` with `preauth_callable=False`,
and the barrier rejects a pre-auth principal on such a route at step 5. The `isinstance` branch is
therefore dead. The comment says so explicitly and justifies keeping it as a fail-closed narrowing;
recorded here only so it is not mistaken for live coverage.

### IN-04: `pyproject.toml` still declares version 1.6.0

**File:** `pyproject.toml:3`

**Issue:** `version = "1.6.0"` while the codebase describes itself throughout as v2.0 and treats
v1.6 as the previous release. `app.main` reads `version("ns-api-gateway")` into the OpenAPI
document, so the served API version is wrong.

**Fix:** Bump to `2.0.0` (or a `2.0.0.devN`) as part of the milestone.

### IN-05: `QuotaExceededError` carries no `Retry-After`

**File:** `src/nativespeaker/api/errors.py:365-366`

**Issue:** Every other 429/503 in the registry that a client should back off from
(`QueueFullError`, `CircuitOpenError`) implements `extra_headers()`; `QuotaExceededError` does not.
The distinct `code` (`quota_exceeded` vs `rate_limited`) is enough for a client to tell the two
apart, so this is not a correctness defect — but a client doing generic 429 backoff has nothing to
wait on. Given the period is a UTC calendar month, the seconds to the next period boundary are
computable from the already-captured `evaluated_at`.

---

_Reviewed: 2026-08-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
