# Phase 42: POST /auth/claim-registered-grant - Research

**Researched:** 2026-09-03
**Domain:** FastAPI + SQLModel/asyncpg entitlement writer; PostgreSQL partial unique indexes as race arbiter; Apple DeviceCheck bit gate; a migration deletion.
**Confidence:** HIGH — every claim below is read out of this repository's source this session. No new dependency, no new vendor, no new external API.

## Summary

This phase adds one route to an already-built machine. `AuthService._complete` is a generic
locate → claim → commit → post-claim → consume sequence over an injected `PostClaim` callable
(`services/auth.py:94-139`), and `_claim_anonymous_grant` (`services/auth.py:147-180`) is the
working model for the new post-claim work. `GrantsDB.activate_anonymous_device_grant`
(`crud/grants.py:86-133`) is the working model for the writer: lock grants ascending, lock each
usage row, plain re-read of the identity row, build rows, one `flush()` inside a bare `try`,
`IntegrityError` → `return False`. The route handler `claim_anonymous_grant`
(`routers/auth.py:99-119`) is the working model for the HTTP shape.

The new work that is genuinely new is the **conversion**: expire an active
`anonymous_device_grant` and insert a `registered_account_grant` in one transaction, carrying the
usage counters across. `ix_access_grants_one_active_per_user` is a non-deferrable partial unique
index (`migrations/20260818_01_initial-release.sql:266-269`), so the UPDATE must precede the
INSERT — as D-10 already states. The second new thing is a **deletion**: three tables and
everything only they need leave the single migration, which cascades into six test files.

The hardest correctness trap is that neither `free_grant_consumed_at` nor `has_prior_free_grant`
can guard this route, because both are already true on the conversion path. The guard is the
grant history read *by source and status*.

**Primary recommendation:** grow `AuthService` with a `_claim_registered_grant` post-claim seam
mirroring `_claim_anonymous_grant`, add one `GrantsDB` writer with an internal two-destination
branch, land the D-07 schema deletion as its own first wave, and prove the conversion with a
two-connection race in `tests/schema/test_claim_race.py`.

<user_constraints>
## User Constraints (from CONTEXT.md)

Source: `.planning/phases/42-post-auth-claim-registered-grant/42-CONTEXT.md`. **The planner must
read that file in full.** The operative clauses are reproduced here.

### Locked Decisions

**The device gate**
- **D-01:** A new registered grant burns DeviceCheck **bit1**. Read bits with the one body token
  before the transaction; if `bit1` is set, refuse with Phase 41's 403 `device_grant_exhausted`; if
  clear, write `bit1=True` carrying `bit0` forward from the read. Fail-closed, load-bearing, retried
  through `tenacity`, no cache, every post-claim outcome consumes the challenge, a crash after the
  write burns the slot and is not compensated. One-way.
- **D-02:** The **conversion path makes no Apple call.** The device token in the body goes unused
  there. Accepted consequence: one device can pay for two allowances. FLAGGED CONFLICT against
  `07-claim-registered-grant.md` steps 7–8 and 10.
- **D-03:** **The database decides before Apple is asked.** Order after the claim: read the stored
  identity row and the grant history → choose the destination (D-09) → **only** for a new grant:
  Apple read → Apple write → the activation transaction.
- **D-04:** **One device token, always required.** Body carries `challenge_id` and one DeviceCheck
  token; absent or empty is the framework's 422. FLAGGED CONFLICT against the brief's two tokens.

**Who claims**
- **D-05:** **Registered identities only, from the stored row, with no Firebase read.** Route sits
  behind `get_linked_identity`; the service requires `identity.identity.provider` to be `google` or
  `apple`. An anonymous caller is refused 403 `operation_not_allowed` through a new `ClaimRefused`
  leaf. `verification_required` is not added. Inside the transaction the identity row is re-read by
  a plain read; a row that is no longer `google`/`apple` is refused the same way. FLAGGED CONFLICT
  against brief steps 2 and 6.
- **D-06:** **Account uniqueness rests on what the schema already has** —
  `ix_external_identities_provider_account`, `UNIQUE (user_id)`,
  `ix_access_grants_one_free_grant_per_user_source` and `free_grant_consumed_at`. Nothing new.
  `account_already_claimed` is not added. FLAGGED CONFLICT against brief step 5.

**The schema deletion**
- **D-07:** Delete `core.access_grants_anti_abuse`, `core.provider_accounts` and
  `core.provider_account_gate_consumptions` from `migrations/20260818_01_initial-release.sql`, with
  everything only they need: the `core.gate_consumption_kind` enum,
  `ix_access_grants_anti_abuse_idp_account_hash`, `ix_gate_consumptions_grant_id`, the generated
  columns `anti_abuse_required_grant_id` and `active_registered_account_grant_id` and their two
  deferred foreign keys, and `UNIQUE (id, source)` **if the planner confirms it exists only as that
  composite FK target** (it does — see Architecture Patterns below). `core.native_claim_provider`
  stays. In code: remove `AccessGrantAntiAbuse` from `tables/grants.py` and `tables/__init__.py`,
  remove the anti-abuse row from `crud/grants.py::activate_anonymous_device_grant` and the comments
  describing the CHECK, and update the six named test files. The development database is rebuilt.
  FLAGGED CONFLICT against `06-schema-reference.md` and brief steps 3 and 5. One-way.
- **D-08:** **No HMAC, no key, `provider_uid` stays raw.**

**Destinations and the transaction**
- **D-09:** Destination selection, run in the preflight **and again inside the locked transaction**,
  in this order: (a) active `registered_account_grant` → **repeat**, nothing written, 200 with the
  current entitlement; (b) any other active grant that is not `anonymous_device_grant` → 403
  through `OtherActiveGrantHeld`, **no field**; (c) active `anonymous_device_grant` →
  **conversion**; (d) no free-grant row in history and no active grant → **new grant**; (e)
  free-grant history with no active free grant → 403 through `FreeGrantAlreadyConsumed`.
  **Trap:** `free_grant_consumed_at` is already set and `has_prior_free_grant` is already true on
  the conversion path; neither can be the blanket guard. The guard is the grant history read by
  source and status. FLAGGED CONFLICT against brief step 11.2(b).
- **D-10:** **Conversion, in one transaction.** Lock the effective grants ascending by id, then
  their usage rows. Re-read the identity row by a plain read and re-check D-05. Then set the
  anonymous row to `status='expired'`, `ends_at = evaluated_at`, `source` unchanged; **then** insert
  the registered grant — the update must precede the insert because
  `ix_access_grants_one_active_per_user` is not deferrable. Insert the new usage row with the old
  row's `monthly_period` and `monthly_used` copied exactly. Set `free_grant_consumed_at` where
  unset. `IntegrityError` is caught without naming a constraint; the loser re-reads and answers 200.
- **D-11:** **New grant.** `tier_id='registered'`, `starts_at = evaluated_at`, `ends_at` NULL, usage
  row with the current period and `monthly_used = 0`, `free_grant_consumed_at = evaluated_at`. The
  unique indexes are the arbiter of the race.
- **D-12:** Response is `SyncResponse`, `Cache-Control: no-store`, read after commit by
  `SyncService.read_entitlement`, `identity_provider` = the stored provider. Repeat and race loser
  return the same body by construction.
- **D-13:** **A live two-connection race in `tests/schema`,** for both destinations.

**Documentation**
- **D-14:** Amend REGGRANT-01 … REGGRANT-03 in `.planning/REQUIREMENTS.md` with dated entries;
  amend the ANONGRANT entries and any STATE.md decision describing Phase 41's anti-abuse row;
  update the header's conflict counts.
- **D-15:** `07-claim-registered-grant.md` and `06-schema-reference.md` are **NOT edited**.
- **D-16:** Record the Apple exposure for this route as Phase 41 D-20 did.

**Carried forward — binding, do NOT rebuild:** no rate limiting and no vendor budgets; no
`audit.auth_events` row; no `?challenge=true` mode and no `classify_mode_signal`; no route registry
and no `BudgetGate`; no `claim_attempt_id`; no HMAC keyring; no Firebase read on any claim route; no
success log line and no new HTTP status; consume on every post-claim outcome and nothing consumes
before the claim; lock order is grant rows ascending then usage rows, identity and user rows by
plain re-read.

### Claude's Discretion

- How `AuthService` grows the completion — a `partial` post-claim seam; whether the preflight is
  shared with the anonymous claim or written beside it.
- The `crud/grants.py` writer(s) for the two destinations — one method with a branch or two methods.
- The request model — reuse `AnonymousGrantClaimRequest` under a shared name, or a sibling.
- The `ClaimRefused` leaf name for the anonymous-caller refusal.
- Whether the schema deletion (D-07) is its own plan wave — but it lands **before or with** the new
  writer, never after.
- How the migration edit is verified; test placement and depth.

### Deferred Ideas (OUT OF SCOPE)

The web branch's account record; the Android and web branches; registered claimants on the anonymous
route; `held_grant_ends_at`; `verification_required`; a real-device check of the Apple round trip;
rate limiting the auth surface; one test asserting each Python enum's values equal its `core.*`
type's labels.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REGGRANT-01 | The endpoint is the only creator of `source='registered_account_grant'` rows, across prepare and completion modes | `tests/unit/test_grant_sources.py` is a working AST walk that already proves exactly this property for `anonymous_device_grant` [VERIFIED: tests/unit/test_grant_sources.py:67-85]. Mirror it for the registered member. "Prepare mode" does not exist here — prepare is `POST /auth/challenge`, which writes only `core.auth_challenges` [VERIFIED: src/nativespeaker/api/crud/challenges.py:32-57]. |
| REGGRANT-02 | Supersession conversion happens inside one transaction under the same fixed global lock order, never leaving two active grants | Lock order is `lock_effective_grants` → `lock_usage`, proven over emitted SQL in `tests/schema/test_grant_locks.py:286-316`. `ix_access_grants_one_active_per_user` makes "two active grants" unrepresentable [VERIFIED: migrations/20260818_01_initial-release.sql:266-269]. |
| REGGRANT-03 | The one-free-grant-per-account interplay with an existing anonymous device grant resolves without double-allocating entitlement | The conversion issues no second allowance: it expires one row and inserts one. `ix_access_grants_one_free_grant_per_user_source` is `UNIQUE (user_id, source)` and therefore does **not** by itself prevent a second free entitlement of a *different* source — see Pitfall 3. The application's history-by-source read is the guard. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bearer verification, identity resolution, linked-caller narrowing | API — `app/dependencies.py` | — | `get_linked_identity` is a route-level `Depends`; the route body never re-verifies [VERIFIED: src/nativespeaker/api/app/dependencies.py:58-62] |
| Request body shape and the 422 for an absent token | API — `schemas/auth.py` (Pydantic) | — | `Field(..., min_length=1)` produces the framework 422 [VERIFIED: src/nativespeaker/api/schemas/auth.py:31-35] |
| Challenge lifecycle (locate, claim, consume) | API — `crud/challenges.py` + `services/auth.py::_complete` | Database (the conditional UPDATE is the serialization point) | `claim()`'s WHERE is the only expiry evaluation anywhere [VERIFIED: src/nativespeaker/api/crud/challenges.py:64-75] |
| Destination selection (repeat / conversion / new / refuse) | API — `services/auth.py` preflight | API — `crud/grants.py` re-check inside the lock | D-03 and D-09; a preflight refusal costs no Apple round trip |
| Device slot accounting | External — Apple DeviceCheck | — | bit1 is the only durable record of a registered-grant device slot |
| Grant/usage/marker writes and lock ordering | API — `crud/grants.py` | Database | `commit()`/`rollback()` stay in `services/` per AGENTS.md exception 3 |
| Race arbitration between two simultaneous claims | Database — partial unique indexes | — | With no grant row to lock, `FOR UPDATE` locks nothing [VERIFIED: tests/schema/test_claim_race.py:1] |
| Entitlement reporting after commit | API — `services/sync.py` | — | One read path shared by claim, repeat and loser [VERIFIED: src/nativespeaker/api/routers/auth.py:115-119] |

## Standard Stack

### Core — no new dependency

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.135.1 | route, `Depends`, 422 | Already the app [VERIFIED: pyproject.toml:6] |
| sqlmodel | >=0.0.22 | tables, `select`, `with_for_update` | Already every `crud/` module [VERIFIED: pyproject.toml:16] |
| asyncpg | >=0.30 | driver; schema suite uses it directly | [VERIFIED: pyproject.toml:15] |
| tenacity | >=9.1.4 | the three-attempt DeviceCheck budget | Already wraps both Apple calls [VERIFIED: pyproject.toml:26, src/nativespeaker/api/auth/devicecheck.py:154-171] |
| pydantic | >=2.12 | request/response bodies | [VERIFIED: pyproject.toml:9] |
| structlog | >=25.5 | one log line per rejection, event name from the class name | [VERIFIED: pyproject.toml:22, src/nativespeaker/api/app/error_handlers.py:40] |

### Supporting — test-side only

`pytest >=9.0`, `pytest-asyncio >=1.3` (`asyncio_mode = "auto"`), `pogo-migrate>=0.4.2`
(the schema suite applies `migrations/` in-process through `pogo_core.util.testing.apply`)
[VERIFIED: pyproject.toml:32-41, tests/schema/conftest.py:82-84].

**Installation:** none. `uv sync` is already satisfied; this phase adds no package.

## Package Legitimacy Audit

**Not applicable — this phase installs no external package.** Every module it touches is either
first-party or already pinned in `pyproject.toml` and present in `uv.lock`. No registry lookup was
needed and none was performed.

## Architecture Patterns

### Call flow (new grant)

```
POST /auth/claim-registered-grant
  Depends(get_identity) -> Depends(get_linked_identity)        # 403 preauth_identity_not_allowed
  body: {challenge_id, device_token}                           # 422 on absent/empty
  AuthService._complete(operation=claim_registered_grant)
    locate -> verify_binding -> operation match                # nothing consumed yet
    claim()  -> commit()                                       # the serialization point
    post_claim = _claim_registered_grant:
      provider is google|apple?                     no -> ClaimRefused leaf (403)
      read_effective_grants(user, evaluated_at)     -> destination (D-09)
        (a) registered active                        -> return, nothing written
        (b) other active source                      -> OtherActiveGrantHeld (403)
        (e) free-grant history, none active          -> FreeGrantAlreadyConsumed (403)
        (c) anonymous active                         -> conversion, NO Apple call
        (d) clean                                    -> read_bits -> bit1 set? DeviceGrantExhausted
                                                     -> write_bits(bit0=state.bit0, bit1=True)
      GrantsDB.<writer>(...)                                   # opens the transaction
        False -> session.rollback()                            # loser answers as the repeat does
    consume() -> commit()                                      # every post-claim outcome
  SyncService.read_entitlement(user_id)  +  Cache-Control: no-store
```

### Pattern 1: the post-claim seam

```python
# Source: src/nativespeaker/api/services/auth.py:83-92 (verbatim shape to mirror)
async def complete_claim_anonymous_grant(self, *,
                                         identity: Identity,
                                         challenge_id: str,
                                         device_token: str) -> None:
    """Claim the caller's one anonymous device grant; the entitlement is read back after commit."""
    await self._complete(identity=identity,
                         challenge_id=challenge_id,
                         operation=AuthOperation.claim_anonymous_grant,
                         post_claim=partial(self._claim_anonymous_grant,
                                            device_token=device_token))
```

`AuthOperation.claim_registered_grant` already exists in both the Python enum and the database type
[VERIFIED: migrations/20260818_01_initial-release.sql:18-23 — `CREATE TYPE core.auth_operation AS
ENUM ('create_user', 'upgrade_anonymous_to_registered', 'claim_anonymous_grant',
'claim_registered_grant');`]. `POST /auth/challenge` therefore issues for it today with no edit
[VERIFIED: src/nativespeaker/api/routers/auth.py:49-61].

### Pattern 2: the writer — lock, re-read, decide, write, one flush

```python
# Source: src/nativespeaker/api/crud/grants.py:86-133 (the model; the registered writer mirrors it)
grants = await self.lock_effective_grants(user_id, evaluated_at)
for grant in grants:
    await self.lock_usage(grant.id)

# A plain re-read, never `lock_identity_and_user`.
stored = await IdentitiesDB(self.session).resolve_existing(issuer=..., subject=...)
...
try:
    await self.session.flush()
except IntegrityError:
    return False
return True
```

Two rules this shape encodes, both load-bearing:
- `lock_effective_grants` uses `.with_for_update()` with **no eager-loading option**, because
  Postgres rejects `FOR UPDATE` combined with the join those emit [VERIFIED:
  src/nativespeaker/api/crud/grants.py:59-60].
- `_effective_grants_statement` tests `status == active` positively and carries **no `.limit()`**,
  so a second effective grant is visible and fails closed [VERIFIED:
  src/nativespeaker/api/crud/grants.py:23-35].

### Pattern 3: conversion ordering inside the transaction

The order is forced by the schema, not by taste:

```
UPDATE core.access_grants SET status='expired', ends_at=:evaluated_at  -- the anonymous row
INSERT INTO core.access_grants (... source='registered_account_grant', status='active' ...)
INSERT INTO core.user_monthly_usage (grant_id=<new>, monthly_period=<copied>, monthly_used=<copied>)
UPDATE core.external_identities SET free_grant_consumed_at=:evaluated_at  -- where unset
```

`ix_access_grants_one_active_per_user` is verbatim:

```sql
-- Source: migrations/20260818_01_initial-release.sql:266-269
-- Non-deferrable and per-statement; a correct caller makes it unreachable by expiring before activating.
CREATE UNIQUE INDEX ix_access_grants_one_active_per_user
    ON core.access_grants (user_id)
    WHERE status = 'active';
```

Because SQLAlchemy orders a unit of work as inserts-before-updates by default, an ORM attribute
assignment plus `session.add()` in one flush would emit the INSERT **first** and violate this index.
The writer must therefore either flush the expiry separately before adding the new grant, or emit
the expiry as an explicit `update()` statement. This is the single highest-risk implementation
detail in the phase.

### Pattern 4: the tier constant

```python
# Source: src/nativespeaker/api/services/auth.py:45-46
# The seeded `core.access_tiers` row an anonymous device grant points at.
ANONYMOUS_TIER_ID = "anonymous"
```

Add `REGISTERED_TIER_ID = "registered"` beside it. The row is seeded by the migration:

```sql
-- Source: migrations/20260818_01_initial-release.sql:124-128
-- Reference data, one tier per grant source; registered (50) >= anonymous (10) keeps a claim's carry-over safe.
INSERT INTO core.access_tiers (id, monthly_credits) VALUES
    ('anonymous', 10),
    ('registered', 50),
    ('paid', 1000);
```

`registered` (50) ≥ `anonymous` (10) is what makes D-10's `monthly_used` carry-over safe: the
carried count can never exceed the new tier's allowance.

### Pattern 5: the D-07 deletion, by line

`UNIQUE (id, source)` **is** confirmed to exist only as the anti-abuse composite FK target — the
migration says so and nothing else references it:

```sql
-- Source: migrations/20260818_01_initial-release.sql:243-244
    -- A composite FK target for the anti-abuse table only.
    UNIQUE (id, source),
```
```sql
-- Source: migrations/20260818_01_initial-release.sql:304-307
    FOREIGN KEY (grant_id, grant_source)
        REFERENCES core.access_grants (id, source)
        ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
```

Deletion set, with line ranges in `migrations/20260818_01_initial-release.sql`:

| What | Lines | Note |
|------|-------|------|
| `CREATE TYPE core.gate_consumption_kind` | 40 | only `provider_account_gate_consumptions` uses it |
| generated cols `anti_abuse_required_grant_id`, `active_registered_account_grant_id` | 221-227 | referenced only by the ALTER at 316-322 |
| `UNIQUE (id, source)` + its comment | 243-244 | confirmed sole use above |
| `CREATE TABLE core.access_grants_anti_abuse` | 271-308 | |
| `ix_access_grants_anti_abuse_idp_account_hash` | 310-313 | |
| `ALTER TABLE core.access_grants ADD FOREIGN KEY ...` (both) | 315-322 | |
| `CREATE TABLE core.provider_accounts` | 339-346 | never written by any code |
| `CREATE TABLE core.provider_account_gate_consumptions` | 348-355 | never written by any code |
| `ix_gate_consumptions_grant_id` | 357-358 | |

**Stays:** `core.native_claim_provider` (line 38) — `external_identities.native_claim_platform`
binds it [VERIFIED: migrations/20260818_01_initial-release.sql:86-87]. The two remaining generated
columns `active_subscription_grant_subscription_id` / `active_subscription_grant_user_id`
(228-233) and their deferred FKs (245-251) stay, as does `subscriptions.UNIQUE (id, user_id)` (149).

Code consequences: `AccessGrantAntiAbuse` leaves `tables/grants.py:71-86` and both mentions in
`tables/__init__.py:2,32`; the row build leaves `crud/grants.py:113-117` and the import at
`crud/grants.py:14`; `NativeClaimProvider` stays imported by `crud/grants.py` because
`stored.native_claim_platform` is still written at `crud/grants.py:124`.

### Anti-Patterns to Avoid

- **Calling `session.refresh()` on `identity.user` or `identity.identity` after a rollback.** Those
  rows are **detached**, not expired — `get_identity` resolves them on its own short session and
  returns from inside the `async with` [VERIFIED: src/nativespeaker/api/app/dependencies.py:51-54].
  `refresh()` on a detached instance raises `InvalidRequestError`, which is not an `AppError`, so it
  escapes `_complete` and answers 500 where D-12 requires 200. This exact defect shipped and was
  caught in review during Phase 41 [CITED: .planning/phases/41-post-auth-claim-anonymous-grant/41-LEARNINGS.md, "Detached is not expired"].
- **A nested `try`, or a `try` holding more than the statement that can raise.** `activate_...`
  puts only `await self.session.flush()` inside [VERIFIED: crud/grants.py:128-132].
- **Naming the violated constraint or parsing the `IntegrityError` message.** [VERIFIED: crud/grants.py:130-132]
- **Locking the identity or user row ahead of the grant rows.** `test_grant_locks.py:298-304`
  asserts exactly two distinct lock tiers and that neither is `core.external_identities` nor
  `core.users`.
- **Any network call inside the writer.** `tests/unit/test_claim_ordering.py:22-30` fences
  `crud/grants.py` to the import roots `{datetime, uuid, sqlalchemy, sqlmodel, nativespeaker}` and
  runs a subprocess proving no HTTP client is transitively importable.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Two simultaneous claims | An advisory lock, a lease, or read-then-check | `ix_access_grants_one_active_per_user` + `ix_access_grants_one_free_grant_per_user_source`, catch `IntegrityError`, return `False` | With no grant row to lock, `FOR UPDATE` locks nothing [VERIFIED: tests/schema/test_claim_race.py:1] |
| Apple retry/backoff | A loop | `read_bits_with_retry` / `write_bits_with_retry` | Three attempts, only `RetryableDeviceCheckError` retried, exhaustion converted to `Unavailable` [VERIFIED: src/nativespeaker/api/auth/devicecheck.py:154-171] |
| A new error status or class for ambiguity | A `RegisteredGrantX` error | The existing tree: `DeviceGrantExhausted`, `ProofRejected`, `Unavailable`, `ClaimRefused` + one new leaf | Every refusal here is a 403 already registered; the base declares status and code once so leaves cannot become an oracle [VERIFIED: src/nativespeaker/api/errors.py:436-453] |
| The completion sequence | A second locate/claim/commit/consume | `AuthService._complete(post_claim=partial(...))` | [VERIFIED: src/nativespeaker/api/services/auth.py:94-139] |
| The post-commit response | Constructing an `Entitlement` in the handler | `SyncService.read_entitlement` | Makes claim, repeat and loser identical by construction [VERIFIED: src/nativespeaker/api/routers/auth.py:115-119] |
| A "has the free grant been used" boolean | A new column or cache | The grant history read by source and status | See Pitfall 3 |

**Key insight:** every control this phase needs already exists and is already tested. The phase's
risk is not "what to build" — it is the four ordering facts in Pitfalls 1, 2, 4 and 6.

## Runtime State Inventory

This phase deletes schema objects, so the inventory applies.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | The **development database** (`DB_NAME` from `.env`) holds `core.access_grants_anti_abuse`, `core.provider_accounts`, `core.provider_account_gate_consumptions`, the `core.gate_consumption_kind` type, the two generated columns and the two deferred FKs, applied from the pre-edit migration. The migration is edited in place with a single `-- migrate: apply` block and no `depends:` chain [VERIFIED: migrations/20260818_01_initial-release.sql:1-4], so **`pogo` will not re-apply it** to an already-migrated database. | **Rebuild the development database** (drop + re-apply), as D-07 states. This is a real manual step; nothing automates it. |
| Stored data (tests) | The schema suite's scratch database `ns_schema_test` is **dropped and recreated per session** and the migration applied in-process [VERIFIED: tests/schema/conftest.py:60-102]. | None — it picks the edit up automatically. |
| Live service config | None. No n8n workflow, no dashboard, no external service names any of these tables. `grep` over the repo finds the three names only in the migration, `tables/`, `crud/grants.py` and six test files. | None — verified by repo-wide grep. |
| OS-registered state | None — no scheduled task, no pm2 process, no systemd unit references grant schema. | None. |
| Secrets / env vars | None. D-08 adds no secret and removes none; `idp_account_hash_key_version` was never populated by any code. | None. |
| Build artifacts / installed packages | None. The package is installed from `src/` in editable layout; no generated SQL, no compiled schema artifact, no ORM cache. | None. |

**Rows at risk:** zero. `core.provider_accounts` and `core.provider_account_gate_consumptions` have
no writer anywhere in `src/` (verified by grep). `core.access_grants_anti_abuse` has exactly one
writer, `crud/grants.py:114-117`, added by Phase 41; the project has no users yet.

## Common Pitfalls

### Pitfall 1: the ORM will emit the INSERT before the UPDATE
**What goes wrong:** the conversion writes the new grant before expiring the old one and
`ix_access_grants_one_active_per_user` refuses it, so every conversion looks like a race loss and
answers a stale 200.
**Why:** SQLAlchemy's unit of work orders inserts before updates within one flush, regardless of the
order of the Python statements. The index is non-deferrable and per-statement.
**How to avoid:** flush the expiry first, or issue it as an explicit `update()`. D-10 states the
requirement; the flush boundary is what implements it.
**Warning signs:** the conversion race test reports both attempts as `lost_at_flush`; a single-user
conversion returns `anonymous_device_grant` in the response body.

### Pitfall 2: `CHECK (ends_at IS NULL OR ends_at > starts_at)`
**What goes wrong:** the conversion sets `ends_at = evaluated_at` on the anonymous row. If that row
was created at the same instant, the CHECK fires and the whole transaction rolls back — which the
writer catches as `IntegrityError` and reports as a race loss.
**Why:** verbatim, `migrations/20260818_01_initial-release.sql:236` — `CHECK (ends_at IS NULL OR
ends_at > starts_at)`. Strict `>`, not `>=`.
**How to avoid:** in tests, seed the anonymous grant with a `starts_at` strictly earlier than the
`evaluated_at` the claim runs at. `tests/schema/test_claim_race.py` uses a fixed
`NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)` [VERIFIED: tests/schema/test_claim_race.py:27] —
seed `NOW - timedelta(...)`.
**Warning signs:** a conversion test that passes for the wrong reason. Phase 41 hit precisely this
class of failure and recorded it [CITED: 41-LEARNINGS.md, "A control can pass for the wrong reason"].

### Pitfall 3: the lifetime index does not enforce "one free grant per account"
**What goes wrong:** the planner assumes `ix_access_grants_one_free_grant_per_user_source` prevents
success criterion 4, and omits the application guard.
**Why:** the index is verbatim `UNIQUE (user_id, source)` with predicate `source IN
('anonymous_device_grant','registered_account_grant')` [VERIFIED:
migrations/20260818_01_initial-release.sql:324-327]. The key includes `source`, so **one user may
hold one row of each free source** — which is exactly what the conversion needs. It prevents a
second *registered* grant; it does not prevent a registered grant after a spent anonymous one.
**How to avoid:** D-09(e) is the guard, and it must read history by source **and** status:
`anonymous_device_grant` present in history at any status, with no active free grant → refuse.
**Warning signs:** an account with a revoked anonymous grant receives a registered grant.

### Pitfall 4: `free_grant_consumed_at` and `has_prior_free_grant` are both true on the conversion path
**What goes wrong:** the preflight is copied from `_claim_anonymous_grant`, which refuses on exactly
these two signals [VERIFIED: src/nativespeaker/api/services/auth.py:158-161 — `consumed =
identity.identity.free_grant_consumed_at is not None; if consumed or await
self.grants_db.has_prior_free_grant(...)`: raise `FreeGrantAlreadyConsumed`]. Copied unchanged, the
conversion path — the phase's whole point — is refused 403.
**How to avoid:** write the preflight for this route rather than reusing that condition. Reuse
`read_effective_grants` and `_prior_free_grant_statement`, not the anonymous claim's branch order.
**Warning signs:** every conversion e2e case answers 403 `operation_not_allowed`.

### Pitfall 5: `FREE_GRANT_SOURCES` must not be narrowed
**What goes wrong:** a "cleanup" narrows it to one member.
**Why:** it is bound to the live index predicate by a schema test that reads `pg_get_expr` and
compares [VERIFIED: tests/schema/test_grant_locks.py:319-331]. Narrowing reopens a spent lifetime
slot for every account that already used one.
**How to avoid:** leave `tables/grants.py:29-30` alone. Its two-member assertion also lives in
`tests/unit/test_grant_sources.py:91-94`.

### Pitfall 6: the docstring bar is an equality check at zero
**What goes wrong:** the router module docstring grows to four lines while naming a sixth route, and
`tests/unit/test_docstring_bar.py` fails on every root.
**Why:** `BASELINE = {"src": 0, "tests": 0, "tests/e2e": 0, "tests/schema": 0, "tests/unit": 0}` and
the assertion is `==`, not `<=` [VERIFIED: tests/unit/test_docstring_bar.py:42-62]. The current
router docstring already occupies exactly three lines [VERIFIED: src/nativespeaker/api/routers/auth.py:1-3].
**How to avoid:** rewrite the module docstring to cover six routes in three lines. Every new
function, class and test class in this phase is under the same three-line cap.

### Pitfall 7: three test literal sets must gain the new route and the new leaf
**What goes wrong:** the suite fails in places unrelated to the feature.
**Why and where:**
- `tests/unit/test_app_wiring.py:40-41` and `:48-49` — two `@pytest.mark.parametrize` lists of
  narrowed paths. Add `/auth/claim-registered-grant`. Do **not** add it to `PUBLIC_PATHS` or
  `PREAUTH_CALLABLE_PATHS` (`:12-13`).
- `tests/unit/test_rejection_vocabulary.py:46` `CLAIM_ARMS`, `:56` `EVENT_NAMES`, and `:369`
  `assert set(_family(ClaimRefused)) == set(CLAIM_ARMS)`, plus `:383-388` which asserts the exact
  three event-name strings and the class docstring `TestTheThreeClaimArmsAnswerOneThingAndLogThree`.
  A fourth leaf changes all of these — by design ("A fourth arm added without coming here would be a
  refusal nobody checked the answer of").
- The log event name is derived mechanically from the class name by `camel_to_snake` [VERIFIED:
  src/nativespeaker/api/app/error_handlers.py:26,40], so the leaf's name **is** the log vocabulary.

### Pitfall 8: the D-07 test cascade is larger than the six named files suggest
`tests/schema/test_inventory.py` holds four exact-set literals whose sizes change:

| Literal | Now | After D-07 |
|---------|-----|-----------|
| `EXPECTED_ENUM_LABELS` | 10 | 9 (drop `gate_consumption_kind`) |
| `EXPECTED_CORE_TABLES` | 15 | 12 |
| `EXPECTED_CORE_INDEXES` | 46 | 38 (drop `access_grants_anti_abuse_pkey`, `access_grants_anti_abuse_registered_account_grant_id_key`, `access_grants_id_source_key`, `ix_access_grants_anti_abuse_idp_account_hash`, `ix_gate_consumptions_grant_id`, `provider_account_gate_consumptions_pkey`, `provider_accounts_pkey`, `provider_accounts_provider_provider_uid_key`) |
| `EXPECTED_INDEX_PREDICATES` | 7 | 6 |

[VERIFIED: counted by parsing tests/schema/test_inventory.py this session]

**Two class docstrings in that file are already wrong today** and will be wrong differently
afterwards: `TestEnumTypes` says "Exactly the 11 declared core enum types" (the dict holds 10) and
`TestIndexes` says "Exactly the 54 captured indexes" (46 core + 3 audit = 49). Fix them while
editing; keep each to three lines.

Also cascading, beyond the six files D-07 names:
- `tests/schema/test_constraints.py` — the whole `TestAntiAbuseEvidenceConstraints` class
  (`:325-475`), the two deferred-FK cases at `:304-323`, the `_insert_anti_abuse` helper
  (`:137-155`), the `INSERT` literal at `:48-50` and the constant names at `:19,21`.
- `tests/e2e/conftest.py` — the `with_anti_abuse` parameter and its branch in `seed_grant`
  (`:334,348-353`), the `AccessGrantAntiAbuse` / `NativeClaimProvider` imports (`:23,32`), and every
  caller passing `with_anti_abuse=True`.
- `tests/schema/test_claim_race.py` — the `DELETE FROM core.access_grants_anti_abuse` statement in
  `clean_up` (`:67-68`), its docstring (`:58`), and `test_exactly_one_anti_abuse_row_carries_the_ios_provider`
  (`:292-301`). The final case at `:340-344` mentions "the deferred anti-abuse FKs are never
  reached" — the assertion still holds, the prose does not.
- `tests/unit/test_grant_sources.py:120` — a synthetic source string naming `AccessGrantAntiAbuse`
  in a near-miss parametrize. It is parsed by `ast`, not imported, so it still passes; the `id`
  `another_table` becomes misleading.

### Pitfall 9: three unrelated things are called "apple"
`IdentityProvider.apple` (an IdP), `PurchaseProvider.apple` (a store), and Apple as the DeviceCheck
vendor. `AuthService.__init__` already comments on this [VERIFIED: src/nativespeaker/api/services/auth.py:62-63].
D-05 tests `identity.identity.provider is IdentityProvider.apple`; D-01 talks to the DeviceCheck
seam. Keep them apart at every seam and in every test name.

## Code Examples

### The two-connection race harness the conversion case extends

```python
# Source: tests/schema/test_claim_race.py:212-235 (the production entry point, per attempt)
async def run_attempt(harness, attempt, before_first_flush=None):
    store = ChallengesDB()
    identity = await resolve_identity(harness, attempt.subject)   # its own session, closed first
    async with harness.factory() as real_session:
        session = _RacingSession(real_session, before_first_flush)
        attempt.caller_rows_detached = all(
            object_session(row) is None for row in (identity.user, identity.identity))
        service = AuthService(db=session, challenge_store=store, adapter=None,
                              evaluated_at=NOW, devicecheck=_NeverSetDevice())
        ...
```

For Phase 42 the harness needs three changes, all mechanical:
1. `commit_anonymous_account` → a registered variant. The table CHECK is verbatim
   `(provider = 'anonymous' AND provider_uid IS NULL) OR (provider IN ('google','apple') AND
   provider_uid IS NOT NULL AND provider_uid <> '')` [VERIFIED:
   migrations/20260818_01_initial-release.sql:94-100], so a `google` row **must** carry a non-empty
   `provider_uid`.
2. `commit_issued_challenge` — the operation literal becomes `'claim_registered_grant'`.
3. For the conversion case, seed one active `anonymous_device_grant` with its usage row and a
   `starts_at` strictly before `NOW` (Pitfall 2).

Note the harness resolves the caller on a **separate** session and asserts both caller rows are
detached (`:276-278`). That premise is itself a test, added after the Phase 41 review; preserve it.

### The lock-order proof, captured from emitted SQL

```python
# Source: tests/schema/test_grant_locks.py:298-304
async def test_exactly_two_distinct_lock_tiers_are_taken_on_the_claim_path(self, activation_statements):
    taken = [relation_of(statement) for statement in locking(activation_statements["statements"])]
    assert len(set(taken)) == 2
    assert "core.external_identities" not in taken
    assert "core.users" not in taken
```

This asserts over what the writer actually emits at `before_cursor_execute`, not over a mirrored
literal, so it detects a *third* tier a future writer adds. Add a sibling fixture for the registered
writer rather than a mirrored literal.

### The refusal leaf

```python
# Source: src/nativespeaker/api/errors.py:436-453 (the base and its three current leaves)
class ClaimRefused(AppError):
    """The claim's refusals share this shape, and its leaves add only their own name."""

    # The 403 is declared here and nowhere below, so the refusal cannot become an enumeration oracle.
    status = 403
    code = "operation_not_allowed"
```

The new leaf declares **no** `status`, **no** `code`, **no** `__init__` and **no** fields — those
four absences are asserted per-arm at `tests/unit/test_rejection_vocabulary.py:371-382`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| An anti-abuse receipt row per free grant | The grant's own `source`, the identity row's `native_claim_platform` and `provider_uid`, plus Apple's bits | This phase (D-07) | Fewer copies of one fact; the receipt decided nothing |
| Two DeviceCheck tokens (`query_token`, `update_token`) | One `device_token` for read and write | Phase 41 review, commit `e2e18de` | Two opaque tokens cannot be bound to one device |
| Fork the completion sequence per route | `_complete(post_claim=...)` | Phase 41 | [CITED: 41-LEARNINGS.md] |
| Backend rate limiting via `limits` | Deleted from the product | Phase 35 D-05 | Envoy Gateway rate-limits at the edge [CITED: ns-api-gateway/AGENTS.md:92-95] |
| Startup totality walk of the error tree | `tests/unit/test_error_registry.py` | Phase 37.5 D-09 | A defective tree fails the test run, not the boot |

**Deprecated / dead for this phase:** `audit.auth_events` (deleted, Phase 37.1 D-01);
`claim_attempt_id` (Phase 37.4 D-03); the HMAC keyring (Phase 37.4 D-11); the route registry and
`BudgetGate` (Phase 37.1 D-06, Phase 37 D-04); `?challenge=true` prepare mode (Phase 37.2 D-01).

## Project Constraints (from AGENTS.md)

`/home/init/native-speaker/AGENTS.md` (via the parent `CLAUDE.md`):
- First version, no users, low-value product. **Do not over-engineer for theft.** D-08's refusal of
  an HMAC keyring is this rule applied.
- **Do not skip normal security measures** because there are no users.
- **Keep specs short.**
- The app runs behind **Envoy Gateway**, which authenticates by JWT and rate-limits by IP, user and
  URL — which is why this phase adds no rate limiting.

`/home/init/native-speaker/ns-api-gateway/AGENTS.md`:
- **Docstrings — three lines maximum.** Comments only where necessary; one line each; a comment
  explains the lines below it, never the design.
- **Package layout:** `services/` = orchestration and transaction boundaries; `crud/` = database
  access; `schemas/` = Pydantic bodies; `tables/` = SQLModel + enums; `routers/` = `Depends()` only;
  `auth/` = external-SDK seams only.
- **Exception 3:** `commit()` and `rollback()` live in `services/`, never `crud/`.
- **Exception 4:** a fail-closed read may raise its own rejection, so the rejection stays with the
  query in `crud/`.
- **Function shape:** delete a function that is only a step; keep one that states a rule or marks a
  boundary (a lock, a transaction, or a callable a library requires).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 + pytest-asyncio >=1.3, `asyncio_mode = "auto"` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (:55-68) |
| Default selection | `addopts = "-v --tb=short -m 'not e2e and not schema'"` — unit only |
| Quick run | `uv run pytest -q` |
| Schema suite | `uv run pytest -m schema -q` (needs a live PostgreSQL; creates and drops `ns_schema_test`) |
| E2E suite | `uv run pytest -m e2e -q` (needs PostgreSQL, real Firebase credentials, `.env`) |
| Lint | `uv run ruff check src tests` (line-length 120, `select = ["E","W","F","I","UP"]`, `target-version = "py314"`) |

### Phase Requirements → Test Map

| Req | Behavior | Layer | Command | File |
|-----|----------|-------|---------|------|
| REGGRANT-01 | `registered_account_grant` is constructed at exactly one site, inside the crud writer | unit (AST walk) | `uv run pytest tests/unit/test_grant_sources.py -q` | ❌ Wave 0 — new sibling of the anonymous walk |
| REGGRANT-01 | The route exists, is narrowed to linked callers, and is in neither exemption set | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ edit two parametrize lists |
| REGGRANT-01 | The happy path answers `SyncResponse` with `type=registered_account_grant`, `tier_id='registered'`, `monthly_credits=50`, `no-store` | e2e | `uv run pytest tests/e2e/test_claim_registered_grant.py -m e2e -q` | ❌ Wave 0 |
| REGGRANT-02 | Exactly two lock tiers, grants then usage, neither identity nor users, asserted over emitted SQL | schema | `uv run pytest tests/schema/test_grant_locks.py -m schema -q` | ✅ add a registered-writer fixture |
| REGGRANT-02 | Conversion race: the anonymous row expired exactly once, one active grant, usage carried exactly once, both challenges consumed, loser 200 | schema | `uv run pytest tests/schema/test_claim_race.py -m schema -q` | ✅ extend (D-13) |
| REGGRANT-02 | No vendor call under a lock; both Apple calls precede the writer on the new-grant path | unit (AST order) | `uv run pytest tests/unit/test_claim_ordering.py -q` | ✅ extend |
| REGGRANT-03 | All post-claim outcomes consume exactly once; the five destinations answer their documented status | unit | `uv run pytest tests/unit/test_claim_precedence.py -q` | ❌ Wave 0 — a sibling module for the registered route |
| REGGRANT-03 | New-grant race: exactly one grant row, one usage row, `free_grant_consumed_at` set once, loser 200 | schema | `uv run pytest tests/schema/test_claim_race.py -m schema -q` | ✅ extend (D-13) |
| REGGRANT-03 | Conversion issues no second allowance; a revoked anonymous grant is refused | e2e | `uv run pytest tests/e2e/test_claim_registered_grant.py -m e2e -q` | ❌ Wave 0 |
| D-07 | Exact object inventory after the deletion | schema | `uv run pytest tests/schema/test_inventory.py tests/schema/test_constraints.py -m schema -q` | ✅ edit four literals + the CHECK cases |
| D-05 | The fourth `ClaimRefused` leaf declares nothing, logs its own name, and answers 403 `operation_not_allowed` | unit | `uv run pytest tests/unit/test_rejection_vocabulary.py -q` | ✅ edit `CLAIM_ARMS`, `EVENT_NAMES`, the class |

### Sampling Rate

- **Per task commit:** `uv run pytest -q` and `uv run ruff check src tests`.
- **Per wave merge:** the D-07 wave additionally requires `uv run pytest -m schema -q`; the writer
  wave requires `-m schema` and `-m e2e`.
- **Phase gate:** all three markers green before `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] `tests/e2e/test_claim_registered_grant.py` — happy path (both destinations), the repeat, the
      four refusals, the three Apple arms. Model: `tests/e2e/test_claim_anonymous_grant.py`.
- [ ] A registered sibling of `tests/unit/test_claim_precedence.py` — the stub-session precedence
      and consumption matrix.
- [ ] A registered sibling walk in `tests/unit/test_grant_sources.py` (or a new module) — the
      single-writer property for `registered_account_grant`. **Mutation-test it before trusting it**,
      as Phase 41 did three times.
- [ ] A conversion fixture in `tests/schema/test_claim_race.py` seeding an active anonymous grant
      with `starts_at < NOW`.
- [ ] `tests/e2e/conftest.py::seed_grant` — `with_anti_abuse` removed; a free-source grant becomes
      seedable without a companion row.

No framework install is needed.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Envoy + `get_identity` JWT verification; `get_linked_identity` narrows the route. No new auth code. |
| V3 Session Management | yes | The single-use challenge: 300s TTL, CSPRNG 16-byte base64url handle, claimed-then-consumed, `preauth_subject` cleared on consume [VERIFIED: src/nativespeaker/api/crud/challenges.py:15-23,77-88] |
| V4 Access Control | yes | D-05's stored-provider test; `verify_binding` ties the handle to the presenter [VERIFIED: crud/challenges.py:90-105] |
| V5 Input Validation | yes | Pydantic `Field(..., min_length=1)` on both body fields → framework 422 |
| V6 Cryptography | yes | ES256 bearer minted per DeviceCheck call by `jwt.encode`, never a hand-rolled signature [VERIFIED: src/nativespeaker/api/auth/devicecheck.py:66-70]. D-08 adds no key. |
| V7 Error Handling & Logging | yes | One 403 `operation_not_allowed` for every refusal; the leaf name is the only distinguishing signal and it goes to the log, not the wire |
| V8 Data Protection | yes | `auth/devicecheck.py` and `crud/challenges.py` each hold **no logger at all**, so no code path can log a device token or a handle [VERIFIED: their module docstrings and the absence of any `structlog` import] |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Two devices split the gate (one token read, another written) | Spoofing | One `device_token` for both calls (D-04); the Phase 41 review found this as a live defect |
| Replaying a challenge handle | Spoofing | `claim()`'s conditional UPDATE is the single serialization point; consume on every post-claim outcome |
| Refusal messages as an account-state oracle | Information disclosure | `ClaimRefused` declares 403 + `operation_not_allowed` once at the base; leaves carry no field and no `__init__` |
| Two concurrent claims double-allocating | Tampering | Two partial unique indexes arbitrate; `IntegrityError` → `False` → 200 with the winner's entitlement |
| Two active grants after a conversion | Tampering | `ix_access_grants_one_active_per_user`, non-deferrable; expiry flushed before the insert |
| Bit1 written for a device that got no grant | Repudiation | Accepted and documented (D-01): a crash after the write burns the slot and is not compensated |
| One device paying for two allowances | Tampering | **Accepted** (D-02). The conversion makes no Apple call. |
| SQL injection | Tampering | Every value binds through SQLModel/asyncpg parameters; the only interpolation is a database name behind `_SAFE_IDENTIFIER` in the test conftest |

**Deliberate residual risk, restated for the planner:** D-02 lets one physical device obtain two free
allowances (one anonymous, one registered-new). At under $5/month for a grammar assistant, and with
`registered` capped at 50 monthly credits, this is within the threat model `AGENTS.md` sets.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | every command | ✓ | 0.12.5 | — |
| Python 3.14 | `requires-python = ">=3.14"`, `ruff target-version = "py314"` | see note | system `python3` is 3.13.5 | uv manages the project interpreter; the venv, not the system Python, is what runs |
| PostgreSQL 17 | `-m schema`, `-m e2e` | ✗ not probed | — | `docker compose up` (`docker-compose.yml:5` pins `postgres:17`) |
| Docker | starting PostgreSQL | ✓ binary present | 26.1.5 | daemon socket permission denied for this agent — the developer starts it |
| `.env` | e2e Firebase credentials, `DB_*` | ✓ present | — | — |
| Firebase project + Google OAuth refresh token | `-m e2e` only | not probed | — | e2e module skips without an admin credential [VERIFIED: tests/e2e/conftest.py:70-78] |

**Missing with no fallback:** none.
**Missing with fallback:** a running PostgreSQL. `tests/schema/conftest.py` falls back to
`localhost:5432 postgres/postgres` when `DB_*` are unset (`:21-27`), so `docker compose up -d`
is sufficient for the schema suite. The unit suite — the default `uv run pytest` — needs no
database at all.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SQLAlchemy orders INSERTs before UPDATEs within one flush, so the conversion needs an explicit flush boundary or an `update()` statement | Pattern 3, Pitfall 1 | If the ORM happens to emit them in statement order, the extra flush is harmless overhead. If the assumption is right and ignored, every conversion fails. **The plan should include a task that proves the emitted order against real PostgreSQL before relying on either shape.** |
| A2 | `pogo` will not re-apply an edited migration to an already-migrated development database, so a manual rebuild is required | Runtime State Inventory | If pogo detects the change, the rebuild step is redundant. If it does not and the step is skipped, e2e runs against a schema that no longer matches the migration. D-07 already calls for the rebuild. |
| A3 | Nothing outside this repository (dashboard, external service, fixture dump) reads the three deleted tables | Runtime State Inventory | Verified by repo-wide grep only. A consumer outside the repo would break silently. Low risk: the project has no users and the two provider tables were never written by any code. |
| A4 | The e2e suite's Firebase and Google credentials in `.env` are live | Environment Availability | Not probed this session. If stale, e2e cases skip or fail for environmental reasons rather than code reasons. |
| A5 | `07-claim-registered-grant.md` and `06-schema-reference.md` say what 42-CONTEXT.md reports they say | User Constraints | Those files live outside this submodule and were not read this session. The CONTEXT file is the authority the planner works from, and D-15 forbids editing them regardless. |

## Open Questions (RESOLVED)

1. **One writer with a branch, or two writers?**
   - What we know: D-09 requires the destination to be re-decided inside the lock, after the same
     `lock_effective_grants` + `lock_usage` + plain identity re-read. Both destinations share that
     entire prologue.
   - What's unclear: whether `tests/unit/test_grant_sources.py`'s single-construction-site property
     reads more cleanly with one site or two.
   - Recommendation: **one writer with an internal branch.** Re-deciding inside the lock is the
     requirement, and two writers would have to duplicate the prologue or share a private helper —
     which AGENTS.md § "Function shape" would then ask to inline. One writer keeps exactly one
     `AccessGrant(source=AccessGrantSource.registered_account_grant)` construction site.
   - RESOLVED: one writer with an internal branch, carried by plan 42-02 as
     `GrantsDB.activate_registered_account_grant` — the single writer holding both destination
     branches.

2. **Does the D-07 deletion land as its own wave?**
   - What we know: it edits Phase 41's writer and six test files, and D-07 says it lands before or
     with the new writer.
   - Recommendation: **its own first wave.** It is a large, mechanical, independently verifiable
     diff (`-m schema` green with no new feature), and merging it with the writer would make a
     failure ambiguous between "the deletion broke something" and "the new writer is wrong."
   - RESOLVED: the deletion is plan 42-01, planned as wave 1 with no dependencies; every other plan
     in the phase runs at wave 2 or later.

3. **Is `identity.identity` re-read inside the transaction enough for D-05?**
   - What we know: `resolve_existing` is a plain read with no lock [VERIFIED: crud/identities.py:55-59],
     and `activate_anonymous_device_grant` uses exactly that. A concurrent provider flip between the
     re-read and the flush is theoretically possible.
   - Recommendation: accept it. Locking the identity row would violate the fixed lock order, and
     `ix_external_identities_provider_account` guards uniqueness regardless (D-06). Worth one
     sentence in the phase's threat notes rather than a design change.
   - RESOLVED: accepted as recommended, and recorded as threat `T-42-02-11` in plan 42-02's STRIDE
     register rather than changed in the design.

## Sources

### Primary (HIGH confidence) — read this session
- `migrations/20260818_01_initial-release.sql` (405 lines, read in full)
- `src/nativespeaker/api/{crud/grants.py, crud/identities.py, crud/challenges.py, tables/grants.py, tables/identities.py, tables/__init__.py, services/auth.py, services/sync.py, routers/auth.py, schemas/auth.py, errors.py, auth/devicecheck.py, app/dependencies.py}`
- `tests/schema/{conftest.py, helpers.py, test_inventory.py, test_claim_race.py, test_grant_locks.py}`; `tests/e2e/conftest.py`; `tests/unit/{test_grant_sources.py, test_claim_ordering.py, test_app_wiring.py, test_docstring_bar.py, error_tree.py}`
- `pyproject.toml`, `docker-compose.yml`, `AGENTS.md` (both levels)
- `.planning/phases/42-post-auth-claim-registered-grant/42-CONTEXT.md`
- `.planning/phases/41-post-auth-claim-anonymous-grant/41-LEARNINGS.md`
- `.planning/REQUIREMENTS.md` § REGGRANT (:318-322), `.planning/STATE.md` § Decisions

### Secondary (MEDIUM confidence)
- Outlines (grep/AST) of `tests/unit/{test_claim_precedence.py, test_rejection_vocabulary.py, test_error_contract.py, test_error_registry.py}`, `tests/schema/{test_constraints.py, test_apply_rollback.py}`, `tests/e2e/test_claim_anonymous_grant.py` — structure confirmed, bodies not read line by line.

### Tertiary (LOW confidence)
- None. No web search was performed and none was needed: this phase adds no dependency and no vendor API beyond one already integrated and tested.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency; every version read from `pyproject.toml`.
- Architecture: HIGH — every pattern quoted from the file and line that implements it.
- Pitfalls: HIGH for 2–9 (each read out of the schema or a test literal); MEDIUM for 1 (A1 is an
  ORM-behaviour assumption that the plan should prove empirically).
- Deletion scope: HIGH — the migration was read in full and the cascade counted by parsing the test
  literals.

**Research date:** 2026-09-03
**Valid until:** 2026-10-03 (stable — an internal codebase with pinned dependencies)
