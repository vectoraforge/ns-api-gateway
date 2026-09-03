---
phase: 42-post-auth-claim-registered-grant
reviewed: 2026-09-03T20:55:40Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - migrations/20260818_01_initial-release.sql
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/tables/grants.py
  - src/nativespeaker/api/tables/__init__.py
  - tests/e2e/conftest.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_constraints.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_inventory.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_rejection_vocabulary.py
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: issues_found
---

# Phase 42: Code Review Report

**Reviewed:** 2026-09-03T20:55:40Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

`POST /auth/claim-registered-grant` was reviewed end to end: the route, the completion
sequence, the crud writer, the schema it writes against, and the twenty test files that
pin them. `ruff check src tests` passes, `pytest -q` passes (1001 unit tests) and
`pytest -m schema` passes (147 tests) against the live database.

The phase decisions recorded in `42-CONTEXT.md` (D-01 … D-16) and in the six SUMMARY
files were read first. Findings below do not re-litigate settled choices: the redundant
flush boundary, the conversion path's skipped device gate, and the conversion loser
raising no `IntegrityError` are all accepted as designed. What is reported is where the
implementation does not match those decisions, and where two predicates that must agree
do not.

The central defect is a predicate mismatch: `_effective_grants_statement` filters grants
by a time window, `ix_access_grants_one_active_per_user` does not. When they disagree the
service walks the new-grant arm, burns Apple's one-way DeviceCheck bit1, and then reports
the writer's refusal to the client as `200 OK`. Both halves were reproduced against the
real schema. Two further probes confirmed that the bare `except IntegrityError: return
False` reports non-race failures as success.

Findings CR-01, WR-01, WR-02, WR-03 and WR-04 share one root cause: `return False` from
the crud writer is overloaded to mean both "you lost a race, and the winner's row is what
you will read back" and "your write was impossible, and nothing exists to read back". The
route cannot tell the two apart, so it answers 200 for both.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: The new-grant arm burns an irreversible DeviceCheck bit and then answers 200 with no grant

**File:** `src/nativespeaker/api/services/auth.py:211-231`, `src/nativespeaker/api/crud/grants.py:190-195`, `migrations/20260818_01_initial-release.sql:256`

**Issue:** Two predicates that must agree do not.

- `_effective_grants_statement` (`crud/grants.py:22-34`) selects a grant only when
  `status = active` **and** `starts_at <= evaluated_at` **and**
  `(ends_at IS NULL OR ends_at > evaluated_at)`.
- `ix_access_grants_one_active_per_user` (`migration:256-258`) is
  `UNIQUE (user_id) WHERE status = 'active'` — **no time window at all**.

A row with `status = 'active'` whose `ends_at` has already passed therefore sits inside
the index but outside the effective-grant read. The schema permits such a row: `ends_at`
is nullable, its only `CHECK` (`migration:227`) merely orders it after `starts_at`, and
no trigger or job moves `status` when `ends_at` elapses. `core.manual_grant_issuances`
and the subscription lifecycle both produce term-bounded grants.

For such an account `_claim_registered_grant` runs the new-grant arm:

1. `read_effective_grants` returns `[]`, so `held` is empty (`auth.py:203`).
2. `has_prior_free_grant` is `False` — the lapsed grant is `manual`/`subscription`,
   not a free source (`auth.py:213`).
3. `write_bits_with_retry(..., bit1=True)` runs. **This is irreversible** — D-01 records
   "one-way — a set bit1 cannot be cleared by this system" (`auth.py:222`).
4. `activate_registered_account_grant` inserts the grant, the unique index rejects it,
   `except IntegrityError: return False` swallows it (`crud/grants.py:192-194`).
5. `auth.py:229-231` rolls back and returns normally, so the route falls through to
   `sync_service.read_entitlement` and answers **200** with `type: none`,
   `status: none` (`routers/auth.py:136-143`).

The caller's device slot is permanently spent, the account received nothing, and the only
record is a caught-and-discarded exception. No log line is emitted on this path.

Reproduced against the live database (`activate_registered_account_grant` driven directly
on an account holding one `status='active'`, `ends_at`-in-the-past manual grant):

```
effective grants seen by the preflight = []
has_prior_free_grant = False
activated = False
grants after = [('manual', 'active')]
```

The same shape exists on `_claim_anonymous_grant` (`auth.py:177-195`) with bit0, so the
fix belongs in both arms.

**Fix:** Do not let the writer's refusal be reported as success when nothing was granted,
and do not spend the vendor bit on a state the writer will reject. Make the writer say
*why* it refused, and make the new-grant arm re-check under the same predicate the index
uses. Minimal shape:

```python
# crud/grants.py — replace the bool with the reason, so the caller can branch.
class ActivationOutcome(StrEnum):
    activated = "activated"
    lost_race = "lost_race"        # another writer holds the slot; the caller re-reads it
    refused = "refused"            # nothing to re-read; the caller must not answer 200

# ... in activate_registered_account_grant, before the vendor-visible side effects are
# already spent, take the status-only view the index enforces:
blocking = await self.session.exec(
    select(AccessGrant).where(col(AccessGrant.user_id) == user_id,
                              col(AccessGrant.status) == AccessGrantStatus.active)
                       .with_for_update())
if [g for g in blocking.all() if g.id not in {grant.id for grant in grants}]:
    return ActivationOutcome.refused
```

```python
# services/auth.py::_claim_registered_grant — and the same in _claim_anonymous_grant.
outcome = await self.grants_db.activate_registered_account_grant(...)
if outcome is ActivationOutcome.refused:
    await self.session.rollback()
    raise OtherActiveGrantHeld          # 403, the answer D-09(b) already specifies
if outcome is ActivationOutcome.lost_race:
    await self.session.rollback()       # 200, the repeat's body, as today
```

If changing the writer's return type is judged too large for this phase, the minimum
acceptable stopgap is to run the status-only blocking read in the service **before**
`read_bits_with_retry`, so the one-way bit is never spent on a claim that cannot land.

## Warnings

### WR-01: `except IntegrityError` cannot tell a race from an impossible write, and reports both as 200

**File:** `src/nativespeaker/api/crud/grants.py:164-168`, `src/nativespeaker/api/crud/grants.py:192-194`

**Issue:** Both handlers catch the base `IntegrityError` and return `False`, with the
comment "The unique indexes are the arbiter; the constraint is never named and the message
never parsed." `IntegrityError` is not index-specific: SQLAlchemy raises it for
`UniqueViolation`, `CheckViolation`, `ForeignKeyViolation` and `NotNullViolation` alike.

The supersession flush at `:159-168` is the clearest case. Its `UPDATE` can violate
`CHECK (ends_at IS NULL OR ends_at > starts_at)` (`migration:227`) whenever the anonymous
grant's `starts_at` is not strictly earlier than `evaluated_at`. The test suite is aware
of this — `tests/schema/test_grant_locks.py` seeds an hour back with the comment "a
same-instant expiry would roll the conversion back and read as a race loss", and
`tests/e2e/test_claim_registered_grant.py:199` and `tests/schema/test_claim_race.py:518`
say the same. That is the defect stated in the tests' own words: a `CHECK` violation is
indistinguishable from a race loss, and both answer 200.

Clock skew between pods makes this reachable without a same-microsecond collision: a
grant written by pod A with `starts_at` ahead of pod B's `evaluated_at` fails the
`CHECK`, and the conversion silently no-ops.

**Fix:** Narrow the catch to the one violation the design actually delegates to the
database, and let everything else surface as the 500 it is:

```python
from asyncpg.exceptions import UniqueViolationError

try:
    await self.session.flush()
except IntegrityError as violation:
    if not isinstance(violation.orig.__cause__, UniqueViolationError):
        raise          # a CHECK or FK failure is a broken invariant, not a lost race
    return False
```

This still never names a constraint or parses a message.

### WR-02: A revoked registered grant makes every conversion a silent no-op that answers 200

**File:** `src/nativespeaker/api/crud/grants.py:148-156`, `src/nativespeaker/api/services/auth.py:203-211`

**Issue:** `ix_access_grants_one_free_grant_per_user_source` (`migration:261-263`) is
`UNIQUE (user_id, source)` with **no status predicate** — one
`registered_account_grant` row per user, ever. Neither the service preflight nor the crud
writer consults free-grant history on the conversion path: `has_prior_free_grant` is
gated behind `if not held` (`auth.py:211-213`) and behind `if superseded is None`
(`crud/grants.py:155`), both deliberate per D-09's "trap for the planner".

The consequence is unhandled. An account holding a **revoked** `registered_account_grant`
plus an **active** `anonymous_device_grant` passes every check — the revoked row is not
effective, so `sources` contains only `anonymous_device_grant` — and is routed to
conversion. The insert then hits the lifetime index, `IntegrityError` is swallowed, and
the route answers 200 with the unchanged anonymous entitlement. D-09(e) says this account
should get 403 `FreeGrantAlreadyConsumed`.

Reproduced against the live database:

```
activated = False
grants after = [('registered_account_grant', 'revoked'), ('anonymous_device_grant', 'active')]
free_grant_consumed_at = None
```

Nothing writes `status='revoked'` today, so this is latent rather than live — but it is
the exact case D-09(e) was written for, and the answer is wrong.

**Fix:** Guard the conversion on the registered slot specifically, rather than on free-grant
history in general, in both the preflight and the writer:

```python
# crud/grants.py, after the `held` checks and before `superseded` is chosen:
spent = await self.session.exec(
    select(AccessGrant).where(col(AccessGrant.user_id) == user_id,
                              col(AccessGrant.source)
                              == AccessGrantSource.registered_account_grant))
if spent.first() is not None:
    return False    # or the `refused` outcome of CR-01, so the route answers 403
```

### WR-03: In-transaction eligibility refusals are answered 200, contradicting D-05

**File:** `src/nativespeaker/api/crud/grants.py:144-152`, `src/nativespeaker/api/services/auth.py:229-231`

**Issue:** `activate_registered_account_grant` re-checks eligibility under the locks and
returns `False` for four distinct reasons that are not races:

- `stored is None` — the identity row vanished (`:145`)
- `stored.provider` is no longer `google`/`apple` (`:145`)
- an active `registered_account_grant` appeared (`:149`)
- an active grant of another source appeared (`:151`)

All four collapse into the same `return False` the race loser uses, so
`auth.py:229-231` rolls back and the route answers 200. D-05 states: "Inside the
transaction the identity row is re-read by a plain read, as Phase 41 does; a row that is
no longer `google`/`apple` is refused the same way." It is not refused the same way — the
preflight raises 403 `ClaimantNotRegistered` (`auth.py:200-201`) while the in-transaction
re-check answers 200. The same asymmetry applies to `OtherActiveGrantHeld`.

Only the third case (an active registered grant appeared) is genuinely a repeat and
correctly answers 200.

**Fix:** Fold into CR-01's outcome enum. `refused` maps to the same 403
`ClaimRefused` leaf the preflight raises; only the repeat and the true index race map to
200.

### WR-04: The writer supersedes `grants[0]` with no tripwire on a second effective grant

**File:** `src/nativespeaker/api/crud/grants.py:153`, `src/nativespeaker/api/services/auth.py:203-209`

**Issue:** `_effective_grants_statement` carries an explicit contract in its own comment
(`crud/grants.py:32`): "No `.limit(...)`: the caller must see a second effective grant and
fail closed on it." Two callers honour it — `SyncService.read_entitlement`
(`services/sync.py:39-41`) and `QuotaService.charge` (`services/quota.py:40-43`) both
raise `MultipleEffectiveGrantsError` on `len(grants) > 1`.

`activate_registered_account_grant` does not. It takes `grants[0]` unconditionally
(`:153`), expires exactly that one row, and inserts a registered grant beside whatever
else was in the list. `_claim_registered_grant` has the same gap. Today
`ix_access_grants_one_active_per_user` makes the list at most one long, so the bug is
unreachable — but that is the same index the two other callers already have, and they
still assert. This writer is the one caller where a missed second row silently leaves a
user holding two active grants rather than raising, which is precisely the state the
tripwire exists to prevent.

**Fix:** Assert the same invariant the reading services assert, before choosing
`superseded`:

```python
if len(grants) > 1:
    # A tripwire, not a recovery branch: a partial unique index makes it unreachable.
    raise MultipleEffectiveGrantsError(len(grants), user_id)
superseded = grants[0] if grants else None
```

### WR-05: The conversion's `free_grant_consumed_at` guard is not covered by any test

**File:** `src/nativespeaker/api/crud/grants.py:184-186`

**Issue:** The branch

```python
if stored.free_grant_consumed_at is None:
    stored.free_grant_consumed_at = evaluated_at
```

carries a comment explaining why the existing timestamp is preserved ("the instant it
spent it is the record"), but no test exercises either half on the conversion arm:

- `tests/e2e/test_claim_registered_grant.py::TestTheConversionOfAnActiveAnonymousGrant`
  (`:193-243`) never reads `free_grant_consumed_at`.
- `tests/schema/test_claim_race.py::TestTwoSimultaneousConversionsSupersedeOnce`
  (`:487-603`) has no `test_the_lifetime_marker_is_set_once`, unlike the two sibling race
  classes at `:334` and `:421`.
- `tests/unit/test_claim_precedence_registered.py:425-438` sets the field but mocks the
  writer out entirely (`grants` fixture, `:120-127`), so the branch never runs.

Deleting the `if` and assigning unconditionally passes the whole suite, as does deleting
the assignment altogether. In a suite that elsewhere states its mutation-testing intent
(`42-04-SUMMARY.md`), this branch is unguarded.

**Fix:** Add to the e2e conversion test, and a second case that seeds the marker first:

```python
identity = await _identity_of(_db_transaction, subject)
assert identity.free_grant_consumed_at == registered.starts_at   # set when NULL

# and, on an account seeded with an earlier marker:
assert identity.free_grant_consumed_at == seeded_marker          # never overwritten
```

### WR-06: D-02's recorded consequence understates the device exposure it accepts

**File:** `src/nativespeaker/api/services/auth.py:211-222` (behaviour), `.planning/phases/42-post-auth-claim-registered-grant/42-CONTEXT.md` D-02 (record)

**Issue:** The decision to skip the device gate on the conversion path is settled and is
not challenged here. What is wrong is the consequence D-02 records: "one device can pay
for two allowances (one anonymous, one registered-new) instead of one. Accepted."

That describes the path where no conversion happens. Because the conversion leaves bit1
clear, a device that converts is left with a *free* registered slot:

| sequence | bits spent | allowances the device funded |
|---|---|---|
| account A claims anonymous, account B claims registered-new | bit0, bit1 | 10 + 50 = 60 |
| account A claims anonymous, A converts, then B claims registered-new | bit0, bit1 | 10 + 50 + 50 = 110 |

The conversion path yields one extra 50-credit registered grant per device over the case
D-02 documents. A future reader relying on D-02's table will size the exposure at 60 when
it is 110.

**Fix:** Either write bit1 on the conversion path too (one line, and it costs the
conversion nothing since the grant is being issued anyway), or amend D-02's consequence
to state the three-allowance case explicitly so it is accepted knowingly.

### WR-07: The two claim routes emit byte-identical `device_grant_exhausted` diagnostics

**File:** `src/nativespeaker/api/services/auth.py:219` and `src/nativespeaker/api/services/auth.py:183`

**Issue:** Both routes raise the same class with the same fields:

```python
raise DeviceGrantExhausted(stage="devicecheck_read", cause="already_set")
```

`ProviderLookupError.log_fields` (`errors.py:357-361`) contributes only `stage` and
`cause`, and the log event name is derived from the class name, which is also shared. The
resulting log line is identical whether bit0 (the anonymous slot) or bit1 (the registered
slot) was the one already set. Apple's two bits are the only device-level control this
system has, they are one-way, and operations cannot answer "which slot did this device
spend?" from the logs.

**Fix:** Distinguish the stage per route; nothing about the client answer changes.

```python
# _claim_anonymous_grant
raise DeviceGrantExhausted(stage="devicecheck_read_bit0", cause="already_set")
# _claim_registered_grant
raise DeviceGrantExhausted(stage="devicecheck_read_bit1", cause="already_set")
```

## Info

### IN-01: Stale comment names the deleted anti-abuse row

**File:** `tests/e2e/test_claim_anonymous_grant.py:236`

**Issue:** `# The revoked row and its anti-abuse row are still the only ones: nothing was
written.` D-07 deleted `core.access_grants_anti_abuse`, and the assertion under this
comment was changed from `(1, 1, 1)` to `(1, 1)` in the same commit. The comment now
describes a row that does not exist.

**Fix:** `# The revoked row and its usage row are still the only ones: nothing was written.`

### IN-02: Stale docstring promises an anti-abuse test that no longer exists

**File:** `tests/schema/test_constraints.py:220`

**Issue:** `"""One active grant per user, the lifetime free-grant slot, and the anti-abuse
lower bound."""` — `TestAccessGrantConstraints` no longer contains any anti-abuse case;
D-07 removed them along with the table.

**Fix:** `"""One active grant per user, the lifetime free-grant slot, and the usage row's key."""`

### IN-03: "per-statement" mis-describes how a non-deferrable unique index is enforced

**File:** `migrations/20260818_01_initial-release.sql:255`, `src/nativespeaker/api/crud/grants.py:163`, `tests/schema/test_grant_locks.py` (`TestTheConversionExpiresBeforeItInserts` docstring)

**Issue:** All three say the index is checked "per statement". Postgres inserts index
tuples and checks uniqueness **per row**, as each row version is written inside the
statement — a single statement can violate the index against a row it inserted earlier in
that same statement. The operative property is that the index is *immediate* (not
`DEFERRABLE`), which is what actually forces the UPDATE to be flushed before the INSERT.
The conclusion the three comments draw is right; the stated reason is not, and this
comment is the only documentation of why the flush is split.

**Fix:** Replace "non-deferrable and per-statement" with "non-deferrable, so it is checked
as each row is written".

### IN-04: `GrantClaimRequest` bounds its fields below but not above

**File:** `src/nativespeaker/api/schemas/auth.py:31-35`

**Issue:** Both fields carry `min_length=1` and no `max_length`. An oversized
`challenge_id` reaches the `core.auth_challenges` lookup and an oversized `device_token`
is forwarded to Apple across three retry attempts (`DEVICECHECK_ATTEMPTS`). Neither is an
injection risk — the lookup is parameterised and the token is opaque — but both values
are attacker-controlled and unbounded before they reach a dependency.

**Fix:** Both values have known shapes; bound them.

```python
challenge_id: str = Field(..., min_length=1, max_length=128)
device_token: str = Field(..., min_length=1, max_length=4096)
```

### IN-05: `locked_usage` is built over every grant though only one entry is ever read

**File:** `src/nativespeaker/api/crud/grants.py:137-139`, `src/nativespeaker/api/crud/grants.py:158`

**Issue:** The dict is populated for every locked grant, but the only read is
`locked_usage.get(superseded.id)` where `superseded` is always `grants[0]`. The lock
itself is required by the global lock order; the map is not. The generality suggests the
writer handles several superseded grants, which it does not (see WR-04).

**Fix:** Keep the loop for the locks and bind the one row that is used:

```python
carried = None
for position, grant in enumerate(grants):
    usage = await self.lock_usage(grant.id)
    if position == 0:
        carried = usage
```

---

_Reviewed: 2026-09-03T20:55:40Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
