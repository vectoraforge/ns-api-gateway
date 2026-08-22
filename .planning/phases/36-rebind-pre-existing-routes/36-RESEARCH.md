# Phase 36: Rebind Pre-existing Routes - Research

**Researched:** 2026-08-21
**Domain:** In-repo rewiring — FastAPI dependency wiring, SQLModel/PostgreSQL row locking, entitlement/quota resolution
**Confidence:** HIGH (codebase-grounded; every load-bearing claim read from source or executed in this session)

## Summary

This phase adds **no new dependency**. Everything it needs already exists in the repo: the barrier,
the error registry, the bounded counter, the route registry, the seeded tier rows, and the grant /
usage tables. The work is a `GrantsDB` + resolver + `require_quota` seam, three SQLModel classes, a
registry cross-check, and test coverage. Treat any recommendation to install a package as out of scope.

Four of the six REBIND requirements already hold in the working tree, exactly as `36-CONTEXT.md`
predicts — I verified each against source rather than assuming. The phase's real content is
REBIND-05 (the grant-backed quota flow) plus the *proof* obligations for the four already-done ones.

Three findings materially change the plan and are not in CONTEXT.md:

1. **There are eight pre-existing routes, not nine.** The roadmap goal and success criterion 2
   disagree with each other; criterion 2 (1 + 2 + 5 = 8) matches the code.
2. **Under D-04, a malformed request body burns a credit** — a behaviour change from v1.6, which
   rolled the increment back. Verified empirically both ways in this session. A four-line mitigation
   exists and is also verified.
3. **Six existing e2e tests will start returning 429** the moment `require_quota` is attached,
   because D-08 makes every chat POST 429 until a grant exists. A grant-seeding fixture is
   mandatory, not discretionary.

**Primary recommendation:** Build `database/grants.py` + a resolver module + `require_quota` as a
decorator-level dependency that **declares the route's body model** (closing the 422 credit burn),
lock grant-then-usage with two separate `select(...).with_for_update()` statements, and land the
grant-seeding e2e fixture in the same wave as the dependency attachment so the suite never goes red.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `core.access_tiers` is seeded **as reference data in the initial migration**, not from
  config at startup. Three rows, one per v2.0 grant source: `anonymous` (10 credits),
  `registered` (50), `paid` (1000). `manual` grants name whichever tier the issuance chooses rather
  than having their own. This **overrides `00-schema.md:249`**, and is recorded as the required
  SHARED-INVARIANTS conflict flag rather than resolved silently. — **Reversibility:** costly.
- **D-02:** `registered` (50) is deliberately larger than `anonymous` (10). That ordering is what
  makes `07-claim-registered-grant.md:59`'s carry-over safe.
- **Executor: D-01 is already applied to the working tree and the developer's database. Do not
  redo it. Verify, then carry it into the phase's commits.**
- **D-03:** The flow lives in a **shared resolver module over a `database/grants.py` DB class, with
  `require_quota` as a thin `Depends()` seam**. Phase 38 imports this seam by name. — **Reversibility:** costly.
- **D-04:** **The quota transaction commits before the LLM call.** `require_quota` opens its own
  session from `app.state.session_factory`, runs the locked transaction, and commits — it does not
  use `Depends(get_db)`. — **Reversibility:** reversible.
- **D-05:** `require_quota` is **attached per-route on the two chat POSTs**, `quota_checked=True` is
  set on their registry entries, and **the lifespan assertion is extended to verify the two agree**.
- **D-06:** The flow reads **`RequestContext.evaluated_at`** and never calls `datetime.now()`.
- **D-07:** `GET /chats`, `GET /chats/{chat_id}`, and `DELETE /chats/{chat_id}` are **not**
  quota-checked. Only the two POSTs consume credits.
- **D-08:** **No effective grant → `quota_exceeded` (429).** Consequence: after Phase 36 lands,
  every chat POST returns 429 until the claim phases exist. That is correct behavior, not a regression.
- **D-09:** **Missing `core.user_monthly_usage` row → `internal_error` (500).** Never lazily minted.
- **D-10:** **More than one effective grant is read defensively with no rejection path.** Query
  without `LIMIT 1`, assert at most one row, and on violation log and raise `internal_error`.
- **D-11:** **A failed LLM call burns the credit.** Matches v1.6.
- **D-12:** **Fix D-35-11-A in this phase** by defaulting both fields in `models/llm.py::AnalyzeResponse`
  — `issues: list[Issue] = []` and `suggestions: list[str] = []`.
- **D-13:** **Constrained decoding is a documentation defect, corrected here and fixed later.**
  Correct the two PROJECT.md claims; file restoring strict structured output as a backlog item.

### Claude's Discretion

- Whether the `quota_exceeded` 429 carries `Retry-After`.
- What `require_quota` returns — a pure gate (`None`) or a small result carrying `remaining`/`allowance`.
- Module and file naming above `database/grants.py`, and the names of the resolver functions.
- What the structured security log records on each fail-closed branch, and whether the existing
  rejection counter is reused for quota rejections or left to auth rejections only.
- How e2e tests seed grants now that tier rows are real.
- Exact SQL form of the grant-then-usage lock (two statements vs a single locking join), provided
  the fixed ascending-grant-id order holds.

### Deferred Ideas (OUT OF SCOPE)

- **Restore `with_structured_output(strict=True)`** — file as a backlog item per D-13.
- **`Retry-After` on the quota 429** — raised and explicitly passed over.
- **Proactive quota warnings via `X-RateLimit-Remaining`**.
- **`pyproject.toml:72` sets pogo `schema = 'api'`** but history lives in `public._pogo_migration`.
- **`uv.lock` is stale** (D-35-05-A). Still unowned.
- **The Envoy gateway contract (§9 / FOUND-09)** — deferred to v2.1 per Phase 35 D-08.

**Out of scope (from `## Phase Boundary`):** any `/auth/*` route, `GET /users/me`, the
provider-callback routes, grant or identity *mutation* of any kind (this phase only reads grants and
increments usage), and the Envoy contract.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REBIND-01 | Partition membership declared for every pre-existing route; enumeration assertion passes both directions | **Already holds.** `auth/registry.py:68-77` declares all eight; `assert_route_enumeration` (`registry.py:117-189`) is set-equality in both directions and runs in the lifespan (`app/lifespan.py:37`). Phase adds only `quota_checked=True` on the two POSTs + the D-05 cross-check. |
| REBIND-02 | Off the audited attempt path; no `audit.auth_events` row ever; counter + security log instead | **Already holds.** Audited-path entry is gated solely on `meta.operation is not None` (`auth/barrier.py:176`); all eight entries declare `operation=None`. Counter/log via `record_rejection` (`auth/telemetry.py:49-68`). Existing proof: `tests/e2e/test_audit_writer.py::TestOffPathRequestsWriteNothing`. |
| REBIND-03 | Auth rejections use the shared taxonomy; non-auth business contracts unchanged | **Already holds.** Unified registry at `errors.py`; barrier returns `error_response(...)`; handlers unchanged. Note D-12 is a *knowing, narrow exception* to "business contracts unchanged". |
| REBIND-04 | **Void** (Phase 35 D-05 deleted backend rate limiting) | No work. The `quota_checked_request` admission entry does not exist. |
| REBIND-05 | Effective-grant resolution, grant-then-usage lock in ascending grant id, fail closed on missing usage row, lazy rollover in the same locked transaction, `remaining` never negative | **The whole phase.** See § Quota Path and § Lazy Rollover. No model, DB layer, or dependency exists yet for the three tables. |
| REBIND-06 | App starts; every pre-existing route behaves as in v1.6 apart from auth rejections | Handlers already read `get_linked_identity()`. Two deltas to declare explicitly: D-12 (response shape) and the 422-credit-burn (§ Pitfall 1) — the latter is an *unintended* v1.6 delta unless mitigated. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| JWT acceptance, identity resolution | ASGI middleware (barrier) | — | Already owned by `AuthBarrierMiddleware`; §1.5 makes it the only place. Untouched by this phase. |
| Route partition membership | Declarative registry + lifespan assertion | — | `auth/registry.py`; boot-time fail-closed, not request-time. |
| Quota admission (gate decision) | FastAPI dependency (`require_quota`) | — | D-05: evaluated *after* barrier admission, *before* the handler body. Not middleware — §8.4 sequences it as a separate step. |
| Effective-grant resolution + allowance arithmetic | Policy/resolver module | — | D-03: shared with Phase 38 sync so the two cannot drift. |
| Row locking, SQL, transaction boundary | `database/grants.py` (`GrantsDB`) | — | Session-in-init convention, mirroring `ChatsDB`. |
| Usage increment + lazy rollover write | `GrantsDB` inside one locked transaction | — | §8.4 step 4: same transaction as the lock. |
| LLM invocation | Service layer (`ChatService` → `LLMService`) | — | Must run **after** the quota transaction commits (D-04). |
| Error → HTTP response mapping | `errors.py` classes + one data-driven handler | `app/errors.py` | Established pattern; quota rejections need **no** handler change. |
| Rejection telemetry | `auth/telemetry.py` | — | Bounded counter + structlog. |

## Standard Stack

### Core — all already installed; this phase adds nothing

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | `0.135.1` (pinned, `pyproject.toml:6`) | Dependency seam for `require_quota` | Already the app framework |
| `sqlmodel` | `>=0.0.22` | ORM models + `select(...).with_for_update()` | Established: "Zero raw `text()` SQL, ORM constructs only" (v1.6) |
| `asyncpg` | `>=0.30` | Async PG driver | Existing engine driver |
| `structlog` | `>=25.5` | Structured security log on fail-closed branches | Already used by `telemetry.py` |
| `pytest` / `pytest-asyncio` | `9.0.2` / `>=1.3` | Test framework | `asyncio_mode = "auto"` |

**Installation:** none. `uv sync` only.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Two `select(...).with_for_update()` statements | One locking join | A join's *intra-statement* lock acquisition order is not guaranteed to be grant-then-usage, so it does not visibly satisfy SHARED-INVARIANTS:33. Two statements make the order auditable. **Recommend two statements.** |
| `with_for_update()` | Advisory locks / `SELECT ... SKIP LOCKED` | Out of scope: SHARED-INVARIANTS' global deletions forbid distributed locks and multi-phase-commit machinery. |

## Package Legitimacy Audit

**Not applicable — this phase installs no external packages.** Every symbol it needs is either
already a declared dependency in `pyproject.toml` or in-repo. If a plan proposes a new package,
treat that as scope creep and run the legitimacy gate before accepting it.

## The Eight Pre-existing Routes

⚠️ **The phase goal says "nine". The code says eight, and success criterion 2 also says eight**
(`GET /health/ready` + `GET /` + `GET /examples` + five `/chats` = 8). The missing ninth is
`GET /users/me`, **deleted in Phase 35 D-16** and re-declared by Phase 39.
`36-CONTEXT.md:17` already says "all eight routes". The planner should use eight and correct the
roadmap wording.

[VERIFIED: src/nativespeaker/api/auth/registry.py:68-77] — verbatim:

```python
REGISTRY: tuple[RouteMetadata, ...] = (
    RouteMetadata(method="GET", path="/health/ready", category=Category.public),
    RouteMetadata(method="GET", path="/", category=Category.authenticated),
    RouteMetadata(method="GET", path="/examples", category=Category.authenticated),
    RouteMetadata(method="GET", path="/chats", category=Category.authenticated),
    RouteMetadata(method="POST", path="/chats", category=Category.authenticated),
    RouteMetadata(method="GET", path="/chats/{chat_id}", category=Category.authenticated),
    RouteMetadata(method="POST", path="/chats/{chat_id}", category=Category.authenticated),
    RouteMetadata(method="DELETE", path="/chats/{chat_id}", category=Category.authenticated),
)
```

| # | Route | Handler | Current wiring | Must become |
|---|-------|---------|----------------|-------------|
| 1 | `GET /health/ready` | `routers/health.py:7-11` | No `Depends()` at all; `Category.public` → barrier passes through at `barrier.py:94-96` | **Unchanged.** Already unauthenticated by category, not by a router/route dependency. |
| 2 | `GET /` | `routers/root.py:11-19` | `Depends(get_chat_service)` only | **Unchanged.** Authenticated by category. |
| 3 | `GET /examples` | `routers/examples.py:10-16` | `Depends(get_chat_service)` | **Unchanged.** |
| 4 | `GET /chats` | `routers/chats.py:18-27` | `get_linked_identity` + `get_chat_service` | **Unchanged** (D-07: not quota-checked). |
| 5 | `GET /chats/{chat_id}` | `routers/chats.py:30-43` | same | **Unchanged** (D-07). |
| 6 | `POST /chats` | `routers/chats.py:46-59` | same; **no quota enforcement at all today** | Add `dependencies=[Depends(require_quota_...)]` to the decorator; `quota_checked=True` in the registry. Handler body unchanged. |
| 7 | `POST /chats/{chat_id}` | `routers/chats.py:62-76` | same; **no quota enforcement** | Same as #6. |
| 8 | `DELETE /chats/{chat_id}` | `routers/chats.py:79-87` | same | **Unchanged** (D-07). |

**Router-level vs route-level for the `/health/ready` exemption:** the exemption is **already
handled by category in the barrier and needs no dependency change**. `health.py`'s router declares
no dependencies and its handler takes no `Depends()`. Do **not** introduce a router-level auth
dependency anywhere — it would duplicate the barrier and create the second acceptance path §1.1
exists to forbid (the exact defect the deleted `get_current_user` had, per `app/dependencies.py:91-96`).

## Phase 34/35 API Surface — real symbols

All signatures below read from source this session.

### Identity and request context

[VERIFIED: src/nativespeaker/api/auth/context.py:81-93] — verbatim:

```python
@dataclass(frozen=True, slots=True)
class RequestContext:
    identity: LinkedIdentity | PreAuthIdentity
    route_metadata: RouteMetadata
    client_ip_bucket_kind: ClientIpBucketKind
    evaluated_at: datetime
    attempt_id: UUID
```

`LinkedIdentity` (`context.py:53-65`) carries `user: User`, `identity: ExternalIdentity`,
`issuer: str`, `subject: str`, `kind`. The quota flow needs `identity.user.id` and `evaluated_at`.

| Symbol | Location | Signature |
|--------|----------|-----------|
| `get_request_context` | `app/dependencies.py:58` | `(request: Request) -> RequestContext` — raises `AuthenticationError` if barrier did not run |
| `get_linked_identity` | `app/dependencies.py:68` | `(request: Request) -> LinkedIdentity` — raises if absent or pre-auth |
| `get_preauth_identity` | `app/dependencies.py:81` | `(request: Request) -> PreAuthIdentity` |
| `get_db` | `app/dependencies.py:21` | `(request: Request) -> AsyncGenerator[AsyncSession]` — **yield-dep; commits after the handler returns.** D-04 says `require_quota` must NOT use this. |
| `get_config` | `app/dependencies.py:17` | `(request: Request) -> AppConfig` |
| `REQUEST_CONTEXT_SCOPE_KEY` | `auth/context.py:37` | `= "ns_request_context"` |

`evaluated_at` is captured once at [VERIFIED: src/nativespeaker/api/auth/barrier.py:100] — verbatim
`evaluated_at = datetime.now(UTC)` — so it is already UTC-aware and `.strftime("%Y-%m")` yields the
UTC calendar month directly.

### Error classes (reuse verbatim; no new class needed)

[VERIFIED: src/nativespeaker/api/errors.py:171-190] — verbatim:

```python
INTERNAL_ERROR = register_class(ErrorClass(
    name="internal_error",
    status=500,
    code="internal_error",
    copy="The request could not be completed. Retry later.",
))
...
QUOTA_EXCEEDED = register_class(ErrorClass(
    name="quota_exceeded",
    status=429,
    code="quota_exceeded",
    copy="The allowance for the current period is used up. It refreshes next period.",
))
```

[VERIFIED: src/nativespeaker/api/errors.py:364-365] — verbatim:

```python
class QuotaExceededError(ServiceError):
    error_class = QUOTA_EXCEEDED
```

`QuotaExceededError` inherits `extra_headers() -> None` from `ServiceError` (`errors.py:285-286`),
so it currently sends no `Retry-After` — matching v1.6 and the discretion note. `ServiceError`
subclasses are handled by `service_error_handler` (`app/errors.py:28-35`), registered at
`app/errors.py:66`. **No handler change is needed for the quota path.**

For D-09's missing-usage-row 500 and D-10's multi-grant 500, raise a `ServiceError` subclass whose
`error_class = INTERNAL_ERROR`. `DatabaseNotInitializedError` (`errors.py:401-407`) is the shape to
copy — note it sets `log_level = logging.ERROR`, which makes `service_error_handler` log with
`exc_info=True`. That is the right level for both fail-closed branches.

### Bounded counter metric

[VERIFIED: src/nativespeaker/api/auth/telemetry.py:30-68] — the class and function, verbatim in part:

```python
class RejectionCounter:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, str | None, str], int] = {}

    def increment(self, *, result: str, bounded_reason: str | None, route: str) -> None:
        key = (result, bounded_reason, route)
        self._counts[key] = self._counts.get(key, 0) + 1

    def snapshot(self) -> dict[tuple[str, str | None, str], int]:
        return dict(self._counts)


def record_rejection(app_state: State, *,
                     result: AuthEventResult,
                     bounded_reason: BoundedReason | None,
                     route: str) -> None:
```

Instantiated at `app/lifespan.py:44` as `app.state.rejection_counter = RejectionCounter()`.

⚠️ `record_rejection`'s `result` parameter is typed `AuthEventResult` — a **closed
`core.auth_event_result` enum** with no quota-related member. Reusing it for *quota* rejections
would require passing a non-member string (breaking the bounded-cardinality-by-closed-sets
guarantee `telemetry.py:12-16` documents) or inventing an enum value (forbidden — `migration:84-88`
says "Exactly 44 values; closed and exact. Do not add a spare"). **Recommendation for the
discretion item:** leave `RejectionCounter` to auth rejections; if quota rejections need a metric,
add a separate small counter rather than widening this one.

### Registry cross-check seam (D-05)

`assert_route_enumeration(app, registry=REGISTRY, *, verifiers=None) -> None`
(`auth/registry.py:117-120`) accumulates into a `problems: list[str]` and raises `RuntimeError`
listing every problem (`registry.py:188-189`). D-05's cross-check appends to the same list. The
`quota_checked` field already exists at [VERIFIED: src/nativespeaker/api/auth/registry.py:36] —
verbatim `quota_checked: bool = False`.

To cross-check the flag against the actual dependency, the assertion must inspect the live route's
dependant. Each `fastapi.routing.APIRoute` exposes `route.dependant.dependencies` (solved
sub-dependants) and `route.dependencies` (the raw `Depends(...)` list from the decorator). Matching
`require_quota` **by identity** against `dep.call` is the robust form — a name-string match would
silently pass a renamed function. `enumerate_registered` (`registry.py:97-114`) already walks
`app.routes` and isinstance-checks `APIRoute`, so the walk exists.

### Grant / usage / tier table shapes

[VERIFIED: migrations/20260818_01_initial-release.sql:71-82] — enums, verbatim:

```sql
CREATE TYPE core.access_grant_source AS ENUM (
    'subscription',
    'anonymous_device_grant',
    'registered_account_grant',
    'manual'
);

CREATE TYPE core.access_grant_status AS ENUM (
    'active',
    'revoked',
    'expired'
);
```

[VERIFIED: migrations/20260818_01_initial-release.sql:260-283] — tiers + seed, verbatim:

```sql
CREATE TABLE core.access_tiers (
    id TEXT PRIMARY KEY,
    monthly_credits INTEGER NOT NULL CHECK (monthly_credits >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
...
INSERT INTO core.access_tiers (id, monthly_credits) VALUES
    ('anonymous', 10),
    ('registered', 50),
    ('paid', 1000);
```

[VERIFIED: migrations/20260818_01_initial-release.sql:578-585] — usage, verbatim:

```sql
CREATE TABLE core.user_monthly_usage (
    grant_id UUID PRIMARY KEY REFERENCES core.access_grants (id) ON DELETE CASCADE,
    monthly_period TEXT NOT NULL,
    monthly_used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (monthly_used >= 0)
);
```

⚠️ `created_at` and `updated_at` here are **`NOT NULL` with no `DEFAULT`** — unlike every other
table in the migration. The SQLModel class must supply both explicitly on insert. (This phase never
inserts a usage row — D-09 forbids it — but the model still needs the fields, and Phases 41/42/45
will insert.)

`core.access_grants` columns the flow reads [VERIFIED: migrations/20260818_01_initial-release.sql:392-418]:
`id UUID PRIMARY KEY`, `user_id UUID NOT NULL`, `tier_id TEXT NOT NULL`, `source`, `subscription_id UUID`,
`status ... NOT NULL DEFAULT 'active'`, `starts_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`,
`ends_at TIMESTAMPTZ` (nullable), plus four `GENERATED ALWAYS AS (...) STORED` columns
(`anti_abuse_required_grant_id`, `active_registered_account_grant_id`,
`active_subscription_grant_subscription_id`, `active_subscription_grant_user_id`) and
`created_at` / `updated_at`.

⚠️ **The four STORED generated columns must not be written by the SQLModel class.** PostgreSQL
rejects an explicit value for a generated column. Either omit them from the model or mark them
read-only (e.g. `sa_column_kwargs={"server_default": ...}` is *not* right here — the correct form is
to exclude them from inserts). Simplest safe option: **omit all four from the model**, since this
phase only reads and Phases 41/42 can add them if ever needed.

[VERIFIED: migrations/20260818_01_initial-release.sql:455-460] — the index behind D-10, verbatim:

```sql
-- A plain, NON-deferrable, per-statement partial unique index. Do not convert it to a
-- deferrable exclusion constraint and do not write an application rejection path for it;
-- correct callers make it unreachable by expiring before activating.
CREATE UNIQUE INDEX ix_access_grants_one_active_per_user
    ON core.access_grants (user_id)
    WHERE status = 'active';
```

## Quota Path: today vs. the grant model

### Today

**There is no quota enforcement.** `require_quota` was deleted in Phase 35 D-16; the comment block
that records why is [VERIFIED: src/nativespeaker/api/app/dependencies.py:98-100] — verbatim:

```
#   require_quota          -- backend quota enforcement is Phase 36 REBIND-05, and the named
#                             `quota_checked_request` admission entry §8.4 described is void
#                             because D-05 deleted backend rate limiting from the product.
```

`routers/chats.py:46-59` and `62-76` carry **no** quota dependency. `ChatService.create_chat` /
`send_message` (`services/chats.py:65-108`) enforce `chats_limit` and `messages_limit` only.

### The v1.6 shape being replaced

[VERIFIED: git show b16c25b:src/nativespeaker/api/app/dependencies.py:70-78] — verbatim:

```python
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

Four things change: allowance moves from `config.quotas[user.subscription_plan]` to the grant's
tier; `datetime.now(UTC)` becomes `RequestContext.evaluated_at` (D-06); `Depends(get_db)` becomes an
own session that commits (D-04); and the usage row is keyed by `grant_id`, not `user_id`.

Note the period format is **`strftime("%Y-%m")`**, matching §8.4 step 4's `YYYY-MM` and
`migration:575`'s "monthly_period is free text in YYYY-MM (UTC calendar month) with **NO** format
CHECK — do not invent one".

### The target flow (§8.4 steps 1-5, with the CONTEXT decisions applied)

```
require_quota (decorator dependency on the two POSTs)
  ├─ read RequestContext.evaluated_at + identity.user.id      (D-06; no datetime.now())
  ├─ open OWN session from app.state.session_factory          (D-04; NOT Depends(get_db))
  │   └─ BEGIN
  │      1. SELECT grants WHERE user_id=? AND status='active'
  │              AND starts_at <= :t AND (ends_at IS NULL OR ends_at > :t)
  │         ORDER BY id ASC  FOR UPDATE            ← no LIMIT 1 (D-10)
  │         ├─ 0 rows  → QuotaExceededError (429)             (D-08)
  │         └─ >1 rows → log + internal_error (500)           (D-10; structurally unreachable)
  │      2. SELECT user_monthly_usage WHERE grant_id=? FOR UPDATE   ← grant-then-usage
  │         └─ 0 rows → log + internal_error (500)            (D-09; NEVER mint)
  │      3. period = evaluated_at.strftime("%Y-%m")
  │         if usage.monthly_period != period:
  │             usage.monthly_period = period; usage.monthly_used = 0   (D-06, §8.4 step 4)
  │      4. allowance = tier.monthly_credits (join core.access_tiers)
  │         remaining = max(0, allowance - usage.monthly_used)
  │         if remaining == 0 → QuotaExceededError (429)
  │         usage.monthly_used += 1
  │      COMMIT                                    ← before the handler body is entered
  └─ (session closed; NO lock held)
handler body → ChatService → LLMService  ← the network call, outside every lock
```

**Where "missing usage row fails closed" is enforced:** step 2, inside `GrantsDB`, immediately after
the `FOR UPDATE` select returns `None` — before any rollover write and before any increment. §8.4
step 3 is explicit that it is "never lazily minted". The enforcement point must be in the resolver
(or `GrantsDB`), **not** in the handler — the handler never sees the usage row.

## Lazy Rollover: transactions, lock order, no network under lock

### Lock ordering — the binding invariant

[VERIFIED: /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md:33] — verbatim:

> Fixed global lock order on every path touching grants, binding every current and future path:
> grant row(s) `FOR UPDATE` first in ascending grant id, then their `core.user_monthly_usage` rows
> in the same order. Never the reverse, and never an account/user-row lock tier ahead of the grant
> locks.

This phase is the **first** implementation, so its shape becomes the reference Phases 41, 42 and 45
copy. Get it explicit and readable.

### SQL form

`select(...).with_for_update()` compiles correctly under this stack. Verified in-session against the
project's own models:

```
SELECT core.users.id, ... FROM core.users ORDER BY core.users.id ASC FOR UPDATE
```

[VERIFIED: executed in session — `select(User).order_by(col(User.id).asc()).with_for_update()`
compiled against `sqlalchemy.dialects.postgresql`]

**Recommend two separate statements**, not a locking join:

```python
# 1. grants first, ascending id
grant_stmt = (select(AccessGrant)
              .where(col(AccessGrant.user_id) == user_id,
                     col(AccessGrant.status) == GrantStatus.active,
                     col(AccessGrant.starts_at) <= evaluated_at,
                     or_(col(AccessGrant.ends_at).is_(None),
                         col(AccessGrant.ends_at) > evaluated_at))
              .order_by(col(AccessGrant.id).asc())
              .with_for_update())          # no LIMIT 1 -- D-10

# 2. then the usage row
usage_stmt = (select(UserMonthlyUsage)
              .where(col(UserMonthlyUsage.grant_id) == grant.id)
              .with_for_update())
```

A single locking join would lock both tables but gives no guarantee that the grant row is locked
*before* the usage row within the statement — so it cannot be shown to satisfy the invariant. Two
statements make the order auditable by reading the code, which is what the later phases need.

⚠️ **Never combine `with_for_update()` with `selectinload`/`joinedload`.** PostgreSQL rejects
`FOR UPDATE` with outer joins, and SQLAlchemy will emit it. `ChatsDB.get_chat` uses
`selectinload(Chat.messages)` (`database/chats.py:21`) — do not copy that idiom into the locking
queries.

### Keeping the network call out of the locked section

D-04 makes this **structural rather than careful**, and I verified the mechanism empirically on the
pinned FastAPI:

[VERIFIED: executed in session, FastAPI 0.135.1] — dependency execution order is
`['router', 'decorator', 'param', 'yield-enter', 'HANDLER-BODY', 'yield-exit-commit']`.

So a decorator-level `require_quota` that opens, commits and closes its **own** session finishes
entirely before the handler body — and therefore before `ChatService` reaches `LLMService`. The
locks are released at its `COMMIT`. This also confirms the D-04 rationale against the v1.6 shape:
with `Depends(get_db)`, the commit is the `yield-exit-commit` step, i.e. **after** the handler
returned — so the v1.6 `try_increment` locks genuinely did span the whole OpenAI round trip.

[CITED: https://fastapi.tiangolo.com/tutorial/bigger-applications] — "Router-level dependencies
execute first, followed by decorator-level dependencies, and finally normal parameter dependencies."

## Proving no audit row, and observing the counter

### No `audit.auth_events` row

The mechanism: audited-path entry is gated on exactly one condition,
[VERIFIED: src/nativespeaker/api/auth/barrier.py:176] — verbatim `if meta.operation is not None:`.
All eight registry entries leave `operation` at its default `None`
(`registry.py:31` — verbatim `operation: AuthOperation | None = None`). So no route in this phase
can reach `_audit`.

**Proof already exists** at `tests/e2e/test_audit_writer.py::TestOffPathRequestsWriteNothing`, using
helper `row_count(factory)` (`test_audit_writer.py:101-102`) — verbatim:

```python
async def row_count(factory) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(AuthEvent))
```

⚠️ **Coverage gap.** The parametrize list at `test_audit_writer.py:339-345` covers six pairs:
`("GET","/")`, `("GET","/examples")`, `("GET","/chats")`, `("POST","/chats")`,
`("GET","/chats/{id}")`, `("DELETE","/chats/{id}")`. **`("POST", "/chats/{chat_id}")` is missing** —
and it is one of the two quota-checked routes. The planner should add it; success criterion 3 says
"any of these routes".

Also note criterion 3 says "including on barrier rejection". A *quota* rejection (429) is not a
barrier rejection, but it happens on the same routes and must also write no audit row. Since
`require_quota` never touches `AuditWriter`, this holds by construction — but assert it, because it
is cheap and it is the new code path.

### Counter observation in tests

Established pattern, three variants already in the suite:

| Pattern | Example |
|---------|---------|
| Exact snapshot equality | `assert audited_app.state.rejection_counter.snapshot() == {("invalid_external_jwt", "missing_token", "/auth/sync"): 1}` (`test_audit_writer.py:390-391`) |
| Before/after delta (module-scoped app, counts accumulate) | `test_audit_writer.py:395-403` |
| Key membership | `assert ("invalid_external_jwt", "missing_token", "/chats/{chat_id}") in counter.snapshot()` (`test_barrier_admission.py:301`) |

⚠️ `snapshot()` returns a **copy** (`telemetry.py:44-46`), so mutating it does not clear the live
counter — `test_identity_resolution.py:289-290` already pins that. And because `_app_lifespan` is
**module-scoped**, counts accumulate across tests in a module: prefer the before/after delta form
over exact equality against the real app.

## Common Pitfalls

### Pitfall 1 — A malformed request body burns a credit (a real v1.6 regression)

**What goes wrong:** with `require_quota` as a decorator dependency that commits its own
transaction, FastAPI runs and commits the increment **before** it validates the request body. A
client that posts `{"lang": "en"}` (no `phrase`) gets a 422 *and* loses a credit.

**Verified both ways in this session:**

| Shape | Invalid body result |
|-------|---------------------|
| D-04 shape (own session, commits inside the dependency) | `status: 422 \| calls: ['QUOTA-RAN']` — **committed, credit burned** |
| v1.6 shape (`Depends(get_db)` yield-dep) | `['open', 'increment', 'ROLLBACK(RequestValidationError)']` — **rolled back, no burn** |

So this is not a pre-existing behaviour: v1.6's yield-dependency `except Exception: rollback`
(`app/dependencies.py:26-28`) caught the `RequestValidationError` and undid the increment. D-04
removes that protection as a side effect. Under REBIND-06 ("behaves as it did in v1.6") this is a
delta the phase must either fix or consciously accept and record.

**How to avoid — verified mitigation:** have the quota dependency **declare the route's body model**.
FastAPI then validates the body while solving that dependency, so the 422 fires before its function
body runs:

```
invalid body -> 422 | calls: []          # quota never ran
valid body   -> 200 | calls: ['QUOTA-RAN', 'handler']
```

[VERIFIED: executed in session, FastAPI 0.135.1]

Cost: the two POSTs take different bodies (`ChatRequest`, `MessageRequest`), so this needs two thin
per-route wrappers over the one shared resolver — which the D-05 per-route attachment already
implies. `POST /chats/{chat_id}` also has a `chat_id: UUID` path param that 422s on a malformed
UUID; declaring it in the wrapper covers that too.

**Recommendation:** take the mitigation. It is ~8 lines, it preserves v1.6 behaviour, and without it
a buggy client silently drains a paying user's monthly allowance. Escalate to the user only if the
planner wants to spend the decision.

**Warning signs:** `tests/e2e/test_error_cases.py:63` and `:99` and `tests/e2e/test_chats.py:170`
send exactly this malformed body today.

### Pitfall 2 — Six existing e2e tests go red the moment `require_quota` is attached

**What goes wrong:** D-08 makes every chat POST return 429 until a grant exists. These currently
expect 2xx:

| File | Tests |
|------|-------|
| `tests/e2e/test_chats.py` | `TestCreateChat` (5: lines 35, 47, 58, 82, 94) and `TestFollowup` (1: line 118) |
| `tests/e2e/test_flows.py` | line 28 create + line 37 follow-up |
| `tests/e2e/test_isolation.py` | line 92 follow-up on an owned chat |
| `tests/e2e/test_error_cases.py` | lines 49, 56, 63, 92, 99 — expect business 4xx, which quota now pre-empts |

`test_chats.py:20-21` says so in its own words — verbatim: *"No case here asserts a quota outcome.
The chat quota path reads a grant model Phase 36 wires (D-15)."*

**How to avoid:** land a grant-seeding e2e fixture in the **same wave** as the dependency
attachment, not a later one. It must insert a `core.access_grants` row **and** its
`core.user_monthly_usage` row (D-09 means a grant without usage is a 500, so seeding only the grant
turns every test into a 500 instead of a 429 — a worse failure).

This resolves the "how e2e tests seed grants" discretion item: **use the seeded `registered` tier id
(50 credits)**, not `insert_tier`'s randomised id. `tests/schema/helpers.py:30-42` `insert_tier`
is asyncpg-based and lives in the schema package; the e2e package uses SQLModel sessions
(`tests/e2e/conftest.py:146-178` `seed_identity` is the model to copy). 50 credits is comfortably
above any single test's consumption.

### Pitfall 3 — The e2e transaction fixture cannot test lock contention

`tests/e2e/conftest.py:81-104` `_db_transaction` binds the replacement `async_sessionmaker` to **one
`connection`** with `join_transaction_mode="create_savepoint"`. Every session in a test — including
the one `require_quota` opens from `app.state.session_factory` — shares that single connection.

Consequences:
- ✅ `require_quota`'s own commit is a savepoint release, so it still rolls back. The D-04 design is
  testable here.
- ❌ Two "concurrent" requests cannot contend for a row lock — they serialize on one connection. A
  deadlock or lock-order test written here would pass vacuously.

**Where lock-ordering tests belong:** `tests/schema/`, which creates a real scratch database
(`tests/schema/conftest.py:111-122`) and opens a fresh `asyncpg.connect` per test
(`conftest.py:125-138`). A two-connection contention test can open a second connection against
`_schema_db_uri`. Note the `conn` fixture's rollback already tolerates a poisoned transaction
(`conftest.py:134-137`).

### Pitfall 4 — `FOR UPDATE` + eager loading

Covered above: PostgreSQL rejects `FOR UPDATE` with outer joins. Keep the locking selects free of
`selectinload`/`joinedload`, and fetch the tier's `monthly_credits` either by a separate select or by
an **inner** join (which is `FOR UPDATE`-compatible, but then use `of=` to avoid locking
`core.access_tiers` rows too — locking a shared reference row on every chat POST would serialize all
users on one tier).

**Recommendation:** read the tier in a separate, unlocked select. It is reference data that this
phase never writes.

### Pitfall 5 — Generated columns on `core.access_grants`

Four `GENERATED ALWAYS AS (...) STORED` columns exist (migration:405-416). An `INSERT`/`UPDATE`
naming any of them fails. This phase never writes a grant row, so the safe move is to omit them from
the SQLModel class entirely.

### Pitfall 6 — `dependency_overrides` and the `require_quota` seam

`tests/unit/conftest.py:162-164` overrides `get_db`, `get_chat_service`, `get_linked_identity`.
Overrides are keyed on the **exact callable object**, and they do **not** cascade: overriding
`get_linked_identity` does not affect a `require_quota` that calls `get_request_context` directly.
Two consequences:

- The unit `client` fixture (`tests/unit/conftest.py:146-167`) builds its own `FastAPI()` and
  includes the real routers. Once the decorator carries `Depends(require_quota_...)`, **every unit
  test through that fixture hits the real quota code** — which will fail, because that app has no
  `state.session_factory`. The fixture must override the quota dependency too.
- If the two per-route wrappers are distinct callables, **each** needs its own override entry.
  Keeping the wrappers thin and overriding the *shared resolver* they call is not enough — FastAPI
  overrides the `Depends()` callable, not what it calls internally.

### Pitfall 7 — `assert_route_enumeration` runs against the real router at boot

`app/lifespan.py:36-37` puts `REGISTRY` on `app.state` and asserts against it. Adding
`quota_checked=True` alone will not fail boot, but D-05's new cross-check will fail boot if the
registry and the decorators disagree — which is the point. Make sure the cross-check is added in the
**same commit** as the decorator change, or the app will not start between commits.

### Anti-Patterns to Avoid

- **Driving quota from the registry flag inside the barrier.** Explicitly rejected by D-05: it puts
  DB locking and mutation in middleware, and §8.4 sequences quota as a step after barrier admission.
- **`LIMIT 1` on the effective-grant query.** Rejected by D-10 — it silently tie-breaks if the index
  is ever changed, the exact behaviour §8.4 forbids.
- **Lazily minting a usage row.** Forbidden by §8.4 step 3 and D-09.
- **Refunding a credit after a failed LLM call.** Rejected by D-11; SHARED-INVARIANTS' global
  deletions forbid the reserve/settle machinery too.
- **A router-level auth dependency for the `/health/ready` exemption.** The barrier's category check
  already handles it; adding one creates a second acceptance path.
- **Raw `text()` SQL.** v1.6 established ORM-constructs-only; the locks must be
  `select(...).with_for_update()`.

## Runtime State Inventory

This is a rewiring phase, not a rename, but it does change database-touching behaviour, so the
categories are answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `core.access_tiers` now holds three seeded rows (`anonymous`/`registered`/`paid`) in the **developer's** database, applied by a `pogo rollback -c 1 && pogo apply` during the Phase 36 discussion. No other developer/CI database has been re-applied. | Any other environment needs the same rollback+apply. Note `pogo`'s apply loop gates on `if not migration.applied` keyed on the filename stem, so an edited file under an already-applied id is **silently skipped** — an environment that already applied the old file will not pick up the seed. |
| Live service config | None — no external service holds this phase's configuration. Envoy config is untouched (§9 deferred). | None |
| OS-registered state | None — no scheduled tasks, pm2 processes, or systemd units reference the quota path. | None |
| Secrets / env vars | None new. `DB_*` and the existing JWT/HMAC config are unchanged. Verified: `.env` declares `DB_HOST`, `DB_NAME`, `DB_PASSWORD`, `DB_PORT`, `DB_USER`. | None |
| Build artifacts | None — no package rename, no new console script. | None |

⚠️ **Uncommitted working tree, wider than CONTEXT.md D-01 records.** `git diff --stat` shows five
modified files: `migrations/20260818_01_initial-release.sql`, `tests/schema/conftest.py`,
`tests/schema/test_apply_rollback.py` (the three D-01 names) **plus two D-01 does not mention**:

- `docker-compose.yml` — replaces literal `{DB_USER}`/`{DB_PASSWORD}`/`{DB_NAME}` placeholders with
  `env_file: [.env]`. A genuine fix (the placeholders were never interpolated), unrelated to D-01.
- `uv.lock` — `version 1.5.0 → 1.6.0` and `revision 2 → 3`. This is **D-35-05-A**, which
  `35-foundation/deferred-items.md` says was deliberately *reverted rather than committed* and is
  "still unowned". It has reappeared in the tree.

The planner must decide who owns each. The `uv.lock` `revision` bump in particular is the
locally-installed-uv artefact deferred-items.md warned about.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.2 + `pytest-asyncio` >=1.3 (`asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (lines 51-61) — `testpaths=["tests"]`, `pythonpath=["."]`, `env_files=[".env"]`, `addopts = "-v --tb=short -m 'not e2e and not schema'"` |
| Quick run command | `uv run pytest -q` (unit only — **912 passing, 250 deselected, ~26s**, confirmed this session) |
| Full suite command | `uv run pytest -q -m ""` (1162 collected: 912 unit + e2e + schema) |
| Lint / type gate | `uv run ruff check src tests && uv run ty check src` |

**Conventions new e2e modules must follow:** module-level `pytestmark = pytest.mark.e2e` and
`@pytest.mark.asyncio(loop_scope="module")` on classes, to match the module-scoped `_app_lifespan`
fixture. Omitting `loop_scope="module"` binds the wrong event loop. Schema modules use
`pytest.mark.schema` and the function-scoped `conn` fixture.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REBIND-01 | Enumeration passes both directions with `quota_checked` set | unit | `uv run pytest tests/unit/test_route_registry.py -x` | ✅ extend |
| REBIND-01 | D-05 cross-check fails boot when flag and decorator disagree | unit | `uv run pytest tests/unit/test_route_registry.py -k quota_checked -x` | ❌ Wave 0 |
| REBIND-01 | Assertion passes against the live started app | e2e | `uv run pytest tests/e2e/test_startup_assertion.py -x -m e2e` | ✅ |
| REBIND-02 | Zero audit rows on all **eight** routes incl. `POST /chats/{chat_id}` | e2e | `uv run pytest tests/e2e/test_audit_writer.py -k OffPath -x -m e2e` | ✅ extend (add the missing pair) |
| REBIND-02 | Counter increments on barrier rejection off-path | e2e | `uv run pytest tests/e2e/test_audit_writer.py -k Telemetry -x -m e2e` | ✅ |
| REBIND-02 | Zero audit rows on a **quota** (429) rejection | e2e | `uv run pytest tests/e2e/test_quota.py -k audit -x -m e2e` | ❌ Wave 0 |
| REBIND-03 | Auth rejections carry the shared body/status | unit + e2e | `uv run pytest tests/unit/test_error_contract.py tests/e2e/test_startup_assertion.py -x` | ✅ |
| REBIND-05 | No effective grant → 429 `quota_exceeded` | e2e | `uv run pytest tests/e2e/test_quota.py -k no_grant -x -m e2e` | ❌ Wave 0 |
| REBIND-05 | Missing usage row → 500 `internal_error`, and **no row is minted** | e2e | `uv run pytest tests/e2e/test_quota.py -k missing_usage -x -m e2e` | ❌ Wave 0 |
| REBIND-05 | Lazy rollover resets `monthly_used` when the stored period is stale | e2e | `uv run pytest tests/e2e/test_quota.py -k rollover -x -m e2e` | ❌ Wave 0 |
| REBIND-05 | `remaining` never negative; exhaustion → 429 | unit | `uv run pytest tests/unit/test_quota_resolver.py -x` | ❌ Wave 0 |
| REBIND-05 | Grant-then-usage lock order under real contention | schema | `uv run pytest tests/schema/test_grant_locks.py -x -m schema` | ❌ Wave 0 (needs 2 connections — see Pitfall 3) |
| REBIND-05 | Multi-grant tripwire raises rather than tie-breaks | unit | `uv run pytest tests/unit/test_quota_resolver.py -k multiple -x` | ❌ Wave 0 |
| REBIND-06 | App starts; the eight routes serve as in v1.6 | e2e | `uv run pytest tests/e2e -x -m e2e` | ✅ needs grant-seeding fixture (Pitfall 2) |
| REBIND-06 | A correct phrase returns 200 with empty arrays (D-12) | unit + e2e | `uv run pytest tests/unit/test_models.py -k analyze -x` | ❌ Wave 0 |
| REBIND-06 | A malformed body does **not** burn a credit (Pitfall 1) | e2e | `uv run pytest tests/e2e/test_quota.py -k malformed -x -m e2e` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -q` + `uv run ruff check src tests`
- **Per wave merge:** `uv run pytest -q -m ""` + `uv run ty check src`
- **Phase gate:** full suite green, ruff and ty clean, and the real app starts, before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/e2e/test_quota.py` — the new module: 429-no-grant, 500-missing-usage, rollover,
      exhaustion, no-audit-row-on-429, malformed-body-no-burn. Covers REBIND-02/05/06.
- [ ] `tests/unit/test_quota_resolver.py` — pure policy: allowance arithmetic, `max(0, ...)`,
      period comparison, multi-grant tripwire. Covers REBIND-05.
- [ ] `tests/schema/test_grant_locks.py` — two-connection lock-order/contention test. Covers REBIND-05.
- [ ] **Grant-seeding e2e fixture** in `tests/e2e/conftest.py` (grant **+** usage row against the
      seeded `registered` tier) — blocks Pitfall 2; must land in the same wave as the attachment.
- [ ] Unit `client` fixture override for the quota dependency (`tests/unit/conftest.py:146-167`) —
      blocks Pitfall 6.
- [ ] Add `("POST", "/chats/{chat_id}")` to `test_audit_writer.py:339-345` parametrize list.
- [ ] Framework install: none required.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (unchanged) | Barrier owns it (Phase 35); this phase adds no acceptance path |
| V3 Session Management | no | No backend-minted sessions — SHARED-INVARIANTS global deletion |
| V4 Access Control | **yes** | Per-user data isolation via `identity.user.id`; quota is per-`user_id` grant. Object-level checks already in `ChatsDB` (`user_id` in every WHERE) |
| V5 Input Validation | **yes** | Pydantic models on both POST bodies; `chat_id: UUID` coercion. See Pitfall 1 for the validation-vs-quota ordering |
| V6 Cryptography | no | No new crypto; HMAC keyring untouched |
| V7 Error Handling & Logging | **yes** | Shared error registry; fail-closed branches log at ERROR without leaking internals to the client (`errors.py` copy strings are generic) |
| V13 API | **yes** | 429/500 use the shared body; internal `core.auth_event_result` values never exposed (§8.3) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection | Tampering | ORM constructs only; zero `text()`. Already an established v1.6 rule |
| Quota bypass via concurrent requests | Elevation of Privilege | `SELECT ... FOR UPDATE` on grant then usage serializes increments per grant |
| Deadlock via inconsistent lock order | Denial of Service | Fixed global order (grant ascending id, then usage) — SHARED-INVARIANTS:33 |
| Self-inflicted quota drain via malformed bodies | Denial of Service | **Pitfall 1** — the 422 burn. Mitigate by declaring the body in the quota dependency |
| Quota drain via LLM failure | Denial of Service | Accepted (D-11); bounded because circuit-breaker trips and out-of-scope rejections fire before the LLM call |
| IDOR on `chat_id` | Elevation of Privilege | Every `ChatsDB` query filters on `user_id`; `tests/e2e/test_isolation.py` covers it |
| Telemetry cardinality explosion | Denial of Service | Counter labels come from closed sets only (`telemetry.py:12-16`); do not add a quota result to `AuthEventResult` |
| Error-message oracle | Information Disclosure | Distinct 429 vs 500 is intentional (D-08/D-09) and leaks only entitlement state to the authenticated owner |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14 in `.venv` (system `python3` is 3.13.5; `requires-python = ">=3.14"`) | — |
| `uv` | dependency/venv management | ✓ | 0.12.5 | — |
| `pytest` | unit + e2e + schema | ✓ | 9.0.2 | — |
| `pogo-migrate` | migration apply/rollback | ✓ | 0.4.2 | — |
| PostgreSQL 17 | e2e + schema suites | ⚠️ not verifiable from this sandbox (`pg_isready` absent, `docker info` unavailable) | — | `docker-compose.yml` provisions `postgres:17`; the developer's DB was re-applied during the Phase 36 discussion, so it exists outside this sandbox |
| Real Firebase credentials | e2e suite | ⚠️ not verified | — | `FIREBASE_TEST_EMAIL` / `FIREBASE_TEST_PASSWORD` / `JWT_API_KEY` env vars; `stub_verifier` fixture covers non-credential cases |
| OpenAI API | e2e chat POSTs | ⚠️ not verified | — | The 6 chat e2e tests make real LLM calls |

**Missing dependencies with no fallback:** none identified. **Note:** unit tests (912) run fully
green in this sandbox with no database, so the quick-feedback loop is unaffected.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PostgreSQL 17 and the Firebase/OpenAI e2e credentials are reachable in the developer's environment | Environment Availability | e2e and schema waves cannot run; unit-only verification would understate coverage |
| A2 | `route.dependant.dependencies` / `route.dependencies` is a stable enough FastAPI surface for the D-05 cross-check on 0.135.1 | Registry cross-check seam | The cross-check needs a different inspection strategy; the flag would document intent without enforcing it. **Verify against the installed FastAPI before planning the task.** |
| A3 | The full suite is currently green including e2e and schema (only the 912 unit tests were run this session) | Validation Architecture | The "six tests go red" estimate in Pitfall 2 could be under- or over-counted |
| A4 | No environment other than the developer's has applied the pre-seed version of the migration | Runtime State Inventory | A CI or teammate database silently lacks the tier rows, and every grant FK fails there |
| A5 | 50 credits (`registered`) is comfortably above any single e2e test's consumption | Pitfall 2 | A long test module could exhaust the seeded grant mid-run and produce confusing 429s |

## Open Questions (RESOLVED)

> All four were closed during `/gsd:plan-phase 36` on 2026-08-21. Each carries its resolution and
> the deciding artifact inline below. Nothing here is still open.

1. **Does the phase accept the 422 credit burn, or take the body-declaring mitigation?**
   - **RESOLVED — take the mitigation.** Put to the developer during plan-phase and answered;
     recorded as **D-14** in `36-CONTEXT.md` § Plan-phase addenda. Implemented by `36-03` Step 3
     (`body: ChatRequest` on `require_quota_create_chat`) and `36-05` Task 1
     (`require_quota_send_message`); proved by `36-05` Task 2 (`test_quota.py -k malformed`).
   - What we know: the burn is real and is a v1.6 regression (both verified); the mitigation is
     verified and costs ~8 lines plus two thin wrappers.
   - What's unclear: whether the user considers this worth the extra seam, given AGENTS.md's
     "do not over-engineer".
   - Recommendation: **take the mitigation.** It restores v1.6 behaviour, which REBIND-06 asks for,
     and the alternative lets a client bug drain a paying user's allowance. If the planner would
     rather not spend the decision, surface it to the user in one line — it is a product call.

2. **Who owns the two extra uncommitted files (`docker-compose.yml`, `uv.lock`)?**
   - **RESOLVED — neither; both are out of scope.** Put to the developer during plan-phase and
     answered "leave both alone"; recorded as **D-15** in `36-CONTEXT.md` § Plan-phase addenda.
     No plan stages, commits, or reverts either file, and every plan carries the scoped-`git add`
     constraint (no `git add -A`, no `git commit -a`) with grep-level acceptance criteria. The
     deferred D-35-05-A `uv.lock` change stays unowned and uncommitted.

3. **Does the roadmap's "nine routes" get corrected?**
   - **RESOLVED — yes, by a task rather than silently.** `36-02` Task 3 corrects the ROADMAP goal
     line from nine to eight, the same way D-13 corrects PROJECT.md. The `REBIND-04` void marker
     was added to the Requirements line during planning. Until `36-02` executes, the ROADMAP goal
     line still reads "nine".

4. **Should quota rejections increment a metric at all (discretion item)?**
   - **RESOLVED — no counter; structured log only.** Recorded in `36-03`'s discretion table.
     `record_rejection`'s `result` is typed to the closed 44-value `AuthEventResult` enum that the
     migration forbids widening, and a parallel counter was judged not worth the telemetry surface
     for a first-version app. `AuthEventResult` is **not** widened.

## Sources

### Primary (HIGH confidence)

- **Codebase, read this session** — `auth/registry.py`, `auth/barrier.py`, `auth/context.py`,
  `auth/telemetry.py`, `app/dependencies.py`, `app/lifespan.py`, `app/main.py`, `app/errors.py`,
  `errors.py`, `routers/{root,examples,health,chats}.py`, `services/chats.py`, `database/chats.py`,
  `models/{users,llm,__init__}.py`, `migrations/20260818_01_initial-release.sql`,
  `tests/{unit,e2e,schema}/conftest.py`, `tests/e2e/test_audit_writer.py`, `tests/schema/helpers.py`,
  `pyproject.toml`
- **Executed in session** — FastAPI 0.135.1 dependency-ordering probe; body-validation-vs-dependency
  probe (both shapes); `with_for_update()` SQL compilation against the project's models;
  `uv run pytest -q` (912 passed); `git diff --stat`; `git show b16c25b:.../dependencies.py`
- **Specs** — `01-foundation.md §8` (lines ~396-434), `SHARED-INVARIANTS.md:33`, `03-sync.md §38-45`
- **Planning** — `36-CONTEXT.md`, `36-DISCUSSION-LOG.md`, `.planning/REQUIREMENTS.md`,
  `.planning/ROADMAP.md`, `.planning/STATE.md`, `35-foundation/deferred-items.md`,
  `35-foundation/35-VALIDATION.md`

### Secondary (MEDIUM confidence)

- Context7 `/websites/fastapi_tiangolo` — dependencies in path operation decorators; router-level
  ordering. Cross-checked by running it.
- Context7 `/sqlalchemy/sqlalchemy` — `with_for_update()` options. Cross-checked by compiling it.

### Tertiary (LOW confidence)

- None. No claim in this document rests on an unverified web search.

## Project Constraints (from CLAUDE.md / AGENTS.md)

`/home/init/native-speaker/CLAUDE.md` includes `AGENTS.md`. Actionable directives:

- **First version, no users yet, few users at first** → do not build for scale that is not here.
- **Sub-$5/month product; the threat model does not justify anti-theft engineering** — but **do not
  skip normal security measures**. Applied above: the quota lock ordering and fail-closed branches
  are normal measures and stay; nothing exotic is proposed.
- **Keep specs short; programming this app should not consume many tokens** → the planner should
  prefer few, dense plans. This phase is genuinely small in code: three models, one DB class, one
  resolver, one dependency, one registry cross-check, plus tests.
- **Runs in Kubernetes behind Envoy Gateway, which authenticates by JWT and rate-limits by IP, user,
  URL** → consistent with REBIND-04 being void and with §9 being deferred. Do not add backend rate
  limiting.

No `.claude/skills/` or `.agents/skills/` directory exists in this repo — checked.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — no new packages; every library already pinned in `pyproject.toml`
- Route inventory & current wiring: **HIGH** — read from source, verbatim
- Phase 34/35 API surface: **HIGH** — signatures and line ranges read this session
- Table shapes / enums: **HIGH** — quoted verbatim from the migration
- Lock semantics: **HIGH** — SQL compilation executed against the project's own models
- Dependency ordering & the 422 burn: **HIGH** — executed both shapes on the pinned FastAPI
- Test-breakage estimate (Pitfall 2): **MEDIUM** — enumerated by grep; e2e suite not executed here (A3)
- D-05 cross-check mechanism: **MEDIUM** — the FastAPI introspection surface is assumed (A2)
- Environment (PG/Firebase/OpenAI): **LOW** — not probeable from this sandbox (A1)

**Research date:** 2026-08-21
**Valid until:** 2026-09-20 (30 days — the stack is pinned and the findings are codebase-internal;
re-verify only if `pyproject.toml` pins change)
