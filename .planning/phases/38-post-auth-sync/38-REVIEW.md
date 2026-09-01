---
phase: 38-post-auth-sync
reviewed: 2026-09-01T09:10:01Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/sync.py
  - tests/e2e/test_sync.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_sync_audit_removal.py
  - tests/unit/test_sync_resolver.py
findings:
  critical: 0
  warning: 6
  info: 4
  total: 10
status: issues_found
---

# Phase 38: Code Review Report

**Reviewed:** 2026-09-01T09:10:01Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

`POST /auth/sync` was reviewed against the five contract points the phase claims, with a
deliberate attempt to falsify each one:

- **Read-only.** Traced. `SyncService.read_entitlement` issues three `select` statements and
  performs no ORM attribute assignment, no `session.add`, and no `flush`. The stale-period
  branch (`sync.py:56`) selects past a stale count rather than assigning it, so `get_db`'s
  commit-on-exit has nothing to flush. Verified independently by `test_sync_resolver.py`
  (object attributes unchanged) and `test_sync.py::TestTheRequestChangesNothing` (all columns
  of all three tables plus whole-table counts identical before and after). **This holds.**
- **`identity_provider` from the stored column.** Traced. `routers/auth.py:86` reads
  `identity.identity.provider`, which originates only in `IdentitiesDB.resolve`'s
  `select(ExternalIdentity, User)`. No token claim, header, or body value reaches it.
  **This holds** — but the guard protecting the dereference does not cover it (WR-01).
- **One captured instant, inclusive/exclusive bounds.** Traced. `grants.py:18-20` is `<=` /
  `>`; `sync.py` contains no `datetime.now` and neither does `grants.py`. **This holds** at
  the application layer; it does *not* hold at the database-snapshot layer (WR-06).
- **Predicate exists exactly once.** Traced. `_effective_grants_statement` is the single
  definition, `Select` is generative so `.with_for_update()` cannot mutate the shared object,
  and `test_sync_resolver.py::TestThePredicateIsOneDefinition` proves it against compiled
  PostgreSQL text rather than by inspection. **This holds.**
- **Fail closed, no internal class on the wire.** Traced through `app_error_handler`: all
  three tripwires inherit `InternalError` and answer `{"code": "internal_error"}` with 500.
  `vars(cls).get("answers_framework_status")` in `class_answering_status` correctly refuses to
  see the inherited `True`, so none of the three can be recruited as the generic 500 answer.
  **This holds.**

`ruff check` is clean. `uv run pytest tests/unit` is 761 passed. `uv run ty check src/` reports
7 `unresolved-attribute` errors, **2 of them newly introduced by this phase** (`auth.py:85`
and `auth.py:86`); the other 5 are the same pre-existing pattern in `routers/chats.py`. No CI
workflow was found, so nothing gates on `ty` despite it being a pinned production dependency.

No Critical findings. The six Warnings are, in order of how much they matter: a guard that
covers one of the two fields its consumer dereferences; a rule now duplicated in two files
that each still claim to be its only home; a hand-mirrored enum converted by raw string value
with no coupling test; a dead session handle; a load-bearing invariant enforced by tests where
it could be enforced structurally; and an atomicity claim in the OpenAPI description that the
implementation does not deliver.

## Narrative Findings (AI reviewer)

### Warnings

#### WR-01: The linked-identity guard checks `user`, but the route dereferences `identity` too

**File:** `src/nativespeaker/api/app/dependencies.py:57-61`, `src/nativespeaker/api/routers/auth.py:86`

**Issue:** `get_linked_identity` is the route's entire safety argument for the two
dereferences on the next lines, and it only tests one of them:

```python
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> Identity:
    if identity.user is None:
        raise PreAuthIdentityNotAllowed
    return identity
```

The route then does both:

```python
entitlement = await service.read_entitlement(identity.user.id)          # guarded
return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)  # NOT guarded
```

`Identity.identity` is typed `ExternalIdentity | None`. `ty` reports this as an error:

```
error[unresolved-attribute]: Attribute `provider` is not defined on `None` in union `ExternalIdentity | None`
  --> src/nativespeaker/api/routers/auth.py:86:68
```

It is unreachable *today* — `IdentitiesDB.resolve` is the only construction site and sets both
fields together or neither, and `Identity` is `frozen=True` — but the invariant lives in a
different module from the guard, and nothing enforces it. A third construction site that sets
`user` without `identity` turns `/auth/sync` into an `AttributeError` caught by
`generic_error_handler`, i.e. an opaque 500 on an auth endpoint for a fully valid caller. This
is also the first place in the codebase where the *second* field is dereferenced, so the
pre-existing `chats.py` precedent does not cover it.

**Fix:** make the guard cover exactly what its consumers use, which also clears the new `ty`
error and lets the route stay dereference-free:

```python
async def get_linked_identity(identity: Identity = Depends(get_identity)) -> Identity:
    """The resolved user and identity row; rejects an unlinked caller with 403."""
    # Both fields, because both are dereferenced downstream: `resolve` sets them together,
    # and this is the one place that fact is depended on rather than assumed.
    if identity.user is None or identity.identity is None:
        raise PreAuthIdentityNotAllowed
    return identity
```

#### WR-02: The period rule is derived in two places, each commented as the only one

**File:** `src/nativespeaker/api/services/sync.py:26-27`, `src/nativespeaker/api/services/quota.py:54-55`

**Issue:** `grep -rn strftime src/` returns exactly two hits, and both carry the identical
comment:

```
sync.py:26   # The only place the period is derived, and always from the request's captured instant.
sync.py:27   period = self.evaluated_at.strftime("%Y-%m")
quota.py:54  # The only place the period is derived, and always from the request's captured instant.
quota.py:55  period = evaluated_at.strftime("%Y-%m")
```

The comment was true when quota was the sole site; this phase made it false in both files
without touching either comment. That is not cosmetic. The period string is the join key
between what `/auth/sync` reports and what the charge enforces: sync answers `monthly_used: 0`
for a stale row *because* it computes the same `"%Y-%m"` the charge would roll over to. Change
the granularity, the timezone basis, or the format in one file — say to a billing-anniversary
period — and sync silently reports usage against a period the charge never uses, with no test
failing, because `test_sync_resolver.py` and `test_quota_resolver.py` each assert their own
side's format independently.

The phase deduplicated the *statement* (`_effective_grants_statement`) and left the *rule*
duplicated. Note the same duplication applies to the whole resolution ladder — the
no-grant / more-than-one / missing-usage / unknown-tier sequence is written out twice, in the
same order, with near-identical comments.

**Fix:** give the period one definition and have both services call it, so the comment becomes
true again:

```python
# nativespeaker/api/services/period.py
def monthly_period(evaluated_at: datetime) -> str:
    """The billing period `evaluated_at` falls in. The only place the period is derived."""
    return evaluated_at.strftime("%Y-%m")
```

Then `sync.py` and `quota.py` both `period = monthly_period(evaluated_at)`, and delete both
now-false comments. At minimum, if the duplication is deliberate, fix the two comments so they
name each other rather than each claiming uniqueness.

#### WR-03: `EntitlementType` hand-mirrors `AccessGrantSource` and is converted by raw string value

**File:** `src/nativespeaker/api/schemas/auth.py:35-41`, `src/nativespeaker/api/services/sync.py:58`

**Issue:** `EntitlementType` restates the four `AccessGrantSource` members by hand, and the
service converts across the two enums by string value at runtime:

```python
return Entitlement(type=EntitlementType(grant.source.value), ...)
```

Nothing couples them. Add a fifth member to `AccessGrantSource` and its Postgres enum — the
obvious next step for a product that will grow grant kinds — and `EntitlementType(...)` raises
`ValueError`. That is not one of the three deliberate fail-closed branches: it escapes as a
bare `ValueError`, is caught by `generic_error_handler`, and logs `"Unhandled exception"`. The
user is a legitimate caller holding a legitimate grant, and `/auth/sync` returns 500 for them
until someone notices the log.

Coverage makes this worse rather than better. `tests/unit/test_sync_resolver.py:95` seeds
`source=AccessGrantSource.manual` and `tests/e2e/conftest.py:222` defaults
`source: AccessGrantSource = AccessGrantSource.manual`. **Only one of the four mappings is
exercised anywhere.** `subscription`, `anonymous_device_grant` and `registered_account_grant`
have never been through `EntitlementType(...)` in any test.

**Fix:** make enum drift a test failure rather than a production 500, and cover the mapping:

```python
# tests/unit/test_sync_resolver.py
class TestTheWireTypeCoversEveryGrantSource:
    """A source member with no wire member is a 500 for a valid caller, so it fails here first."""

    def test_every_grant_source_has_a_wire_member(self):
        assert {s.value for s in AccessGrantSource} <= {e.value for e in EntitlementType}

    @pytest.mark.parametrize("source", list(AccessGrantSource))
    async def test_each_source_is_reported_as_its_own_type(self, source):
        grant = _grant(source=source)
        entitlement = await _read(_StubSession(grants=(grant,), usage=_usage(grant)))
        assert entitlement.type.value == source.value
```

(`_grant` needs a `source=AccessGrantSource.manual` keyword to support this.)

#### WR-04: `SyncService.session` is assigned, never read, and is a live handle to the committing session

**File:** `src/nativespeaker/api/services/sync.py:19`

**Issue:**

```python
self.session = db
self.grants_db = GrantsDB(db)
```

`self.session` is never referenced again — `read_entitlement` goes exclusively through
`self.grants_db`. Confirmed by grep over the file. `QuotaService` deliberately keeps no
session attribute; `AuthService` keeps one and uses it for `commit`/`rollback`/`refresh`.

Dead on its own, but it is dead code of a specific and unhelpful kind: it parks a directly
callable handle to the commit-on-exit request session on the one service in the codebase whose
entire contract is that it writes nothing. The next edit inside this class has
`self.session.add(...)` and `self.session.commit()` in scope with no friction at all. Removing
it costs nothing and means the class physically cannot reach the session except through
`GrantsDB`'s four read methods.

**Fix:**

```python
def __init__(self, db: AsyncSession, evaluated_at: datetime) -> None:
    # No session attribute: this service reaches the database only through GrantsDB's reads.
    self.grants_db = GrantsDB(db)
    # One instant for this request; nothing below it reads the clock again.
    self.evaluated_at = evaluated_at
```

#### WR-05: The read-only property is enforced by tests where it could be enforced structurally

**File:** `src/nativespeaker/api/app/dependencies.py:111-114`, `src/nativespeaker/api/app/dependencies.py:22-29`

**Issue:** `get_sync_service` takes `Depends(get_db)`, and `get_db` commits on exit:

```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()      # <-- every sync request ends here
```

So a read-only endpoint runs inside a write-capable, commit-on-exit transaction, and the
"nothing is written" guarantee rests entirely on nobody ever assigning an ORM attribute inside
the request. The phase clearly knows this — three separate tests exist solely to detect it
(`test_the_request_session_is_left_clean`, `test_a_stale_row_is_left_exactly_as_it_was_found`,
`TestTheRequestChangesNothing`), and both test files carry comments explaining the hazard.
That is a lot of machinery guarding a property the dependency could simply not have.

`QuotaService` already demonstrates the alternative in this codebase: it takes
`session_factory` rather than `get_db` and owns its transaction boundary. Note this also
means a sync request currently holds two pooled connections concurrently — `get_identity`'s
own short session plus `get_db`'s — for what is three `SELECT`s.

**Fix:** add a rollback-on-exit dependency and point sync at it. The commit-on-exit hazard then
does not exist to be tested for, and any future write inside the service is discarded rather
than persisted:

```python
async def get_readonly_db(request: Request) -> AsyncGenerator[AsyncSession]:
    """A session that always rolls back: a read-only route cannot persist an incidental write."""
    async with request.app.state.session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


def get_sync_service(db: AsyncSession = Depends(get_readonly_db)) -> SyncService:
    ...
```

The existing tests stay valuable as regression guards; they stop being the *only* guard.

#### WR-06: "at this request's instant" is assembled from four separate snapshots

**File:** `src/nativespeaker/api/routers/auth.py:80-81`, `src/nativespeaker/api/services/sync.py:25`

**Issue:** The OpenAPI description shipped to clients and the service docstring both make an
atomicity claim:

```
description="Reads the caller's effective grant, the current period's usage and the "
            "stored registration state. Nothing is written."
"""Report the entitlement `user_id` holds at the captured instant, taking no lock and writing nothing."""
```

What actually happens: the identity row is read in `get_identity`'s **own separate session and
transaction**, which is closed before the handler runs; then the grant, usage and tier are read
as three unsynchronized statements in a second transaction at PostgreSQL's default READ
COMMITTED, where every statement takes a fresh snapshot. The response is therefore composed
from up to four different database states. `evaluated_at` pins the *predicate*, not the
*snapshot* — the phase's "ONE captured instant" invariant is an application-clock invariant
only, and the wording invites it to be read as more.

Concretely: sync can read grant G (tier `registered`, 50 credits), then read a usage row after
a concurrent revoke-and-reissue moved the user to a different grant on a different tier, and
answer with a tier/usage pair that never coexisted. The blast radius is bounded — the charge
path is authoritative and locks, the client self-corrects on the next sync, and no data is
corrupted — which is why this is a Warning and not a Blocker.

**Fix:** either make the claim true, or make the wording match. The cheap correct-the-claim
option is honest and costs nothing:

```python
description="Reports the caller's effective grant, the current period's usage and the "
            "stored registration state as of this request. Advisory: the charge path is "
            "authoritative. Nothing is written."
```

The make-it-true option, if a consistent snapshot is wanted later, is one statement on the sync
session before the reads:

```python
await session.exec(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
```

Do not do both; pick one and say so in the comment.

### Info

#### IN-01: e2e period assertions re-read the clock after the request

**File:** `tests/e2e/test_sync.py:107`, `tests/e2e/test_sync.py:137`, `tests/e2e/test_sync.py:165`

**Issue:** The expected `current_period` is computed with a second `datetime.now(UTC)` taken
*after* the response, e.g. `"current_period": datetime.now(UTC).strftime("%Y-%m")` at line 107
and `_absent_entitlement_body(identity, datetime.now(UTC))` at lines 137 and 165. A request
issued at `23:59:59.999` on the last day of a month is answered with the old period and
asserted against the new one. Narrow window, but it is a real month-boundary flake and it is
avoidable at zero cost. `test_an_open_ended_grant_that_has_started_is_present` (line 170) shows
the correct shape: capture `now` once, before the request, and reuse it.

**Fix:** capture the instant before the call and assert against that single value, matching the
pattern already used at line 170.

#### IN-02: `status` carries no information `type` does not already carry

**File:** `src/nativespeaker/api/schemas/auth.py:44-56`

**Issue:** `EntitlementStatus` has exactly two members and `sync.py` sets `status=none` on
precisely the branch where `type=none` and `status=active` on precisely the branch where
`type != none`. Two wire fields encode one bit, and they can only ever drift apart by mistake.
Clients that check `status == "active"` and clients that check `type != "none"` will disagree
the first time a bug puts them out of step.

**Fix:** if `status` exists for forward compatibility (a future `grace_period` or `past_due`),
say so in the docstring so a later reader does not "simplify" it away. Otherwise drop it and
let `type` be the single discriminator.

#### IN-03: `/auth/sync` returns per-account data without `Cache-Control: no-store`

**File:** `src/nativespeaker/api/routers/auth.py:77-86`

**Issue:** `/auth/challenge` sets `no-store` explicitly and explains why. `/auth/sync` returns
a per-account tier, allowance and usage count and sets no cache directive. Real exposure is
low — it is a `POST`, so no conforming shared cache stores it absent explicit freshness, and
Envoy will not cache it — which is why this is Info and not a security finding. It is listed
because the two adjacent routes now handle the question differently with no comment saying the
difference is deliberate.

**Fix:** either add `headers={"Cache-Control": "no-store"}` for consistency, or add one comment
noting that a POST response needs no directive and the challenge route's `no-store` is about
the secret handle specifically.

#### IN-04: sync reports raw `monthly_used`; quota floors `remaining` at zero

**File:** `src/nativespeaker/api/services/sync.py:56-63`, `src/nativespeaker/api/services/quota.py:68-69`

**Issue:** `QuotaService` deliberately floors — `remaining = max(allowance - usage.monthly_used, 0)`
with the comment "a stored count above the allowance is ordinary exhaustion". `/auth/sync`
hands the client the raw pair, so a client doing the obvious `monthly_credits - monthly_used`
gets a negative remaining in exactly the case the server has already decided means zero. The
two surfaces describe the same state differently.

**Fix:** no code change strictly required, but document the intent on `Entitlement`: state that
`monthly_used` is the raw stored count, may exceed `monthly_credits`, and that remaining is
`max(monthly_credits - monthly_used, 0)`. A client contract that leaves this to be discovered
will have it discovered wrong.

---

_Reviewed: 2026-09-01T09:10:01Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
