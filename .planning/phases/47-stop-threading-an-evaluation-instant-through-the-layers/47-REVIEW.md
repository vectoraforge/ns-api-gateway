---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
reviewed: 2026-09-12T10:04:39Z
depth: standard
files_reviewed: 52
files_reviewed_list:
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/crud/challenges.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/quota.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/services/sync.py
  - src/nativespeaker/api/tables/grants.py
  - tests/e2e/conftest.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_restore_race.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/schema/test_sync_lock_freedom.py
  - tests/unit/conftest.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_challenge_ids.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_conversion_carries_usage.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_identity_flip.py
  - tests/unit/test_instant_is_not_threaded.py
  - tests/unit/test_open_term.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_spent_free_grant_refusal.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_subscription_grant_write.py
  - tests/unit/test_subscription_store_clock.py
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_upgrade_precedence.py
  - migrations/20260818_01_initial-release.sql
findings:
  critical: 2
  warning: 8
  info: 1
  total: 11
status: issues_found
---

# Phase 47: Code Review Report

**Reviewed:** 2026-09-12T10:04:39Z
**Depth:** standard
**Files Reviewed:** 52
**Status:** issues_found

## Summary

The refactor is mechanically clean. `get_evaluated_at` is gone, no comparison direction moved,
no clock reaches a partial index predicate, and the pure helpers that survive are pinned by new
boundary cases. Ruff, `ty` and the default test run (1921 passed) are all green.

Two problems remain in the entitlement path. First, `RestoreService.restore` reads its clock
before an eight-second store round trip and then judges the term with that stale value; a term
that closes inside the window makes restore expire the caller's free grant and write a grant that
is already over. Second, grants are stamped with the API pod's clock but selected with the
database's `clock_timestamp()`; the two are different machines, and only the pod clock was in
play before this phase.

Six test findings follow. Three are lost coverage: the strict expiry boundary is now guarded only
by a case the default run deselects, the uncapped `Retry-After` is no longer exercised through
`charge`, and one rewritten assertion now restates a database CHECK.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Restore attaches a term that closed during the store round trip and spends the free-grant slot for good

**File:** `src/nativespeaker/api/services/restore.py:57,73,87,105`

**Issue:**
`restore` reads `instant` on line 57, then awaits `self._verify(...)` on line 58. On the Google
Play arm that await is a live HTTPS read capped at `PLAY_HTTP_TIMEOUT_SECONDS = 8`
(`auth/google_play.py:44`), plus a credential refresh capped at the same eight seconds
(`auth/google_play.py:393-398`). Every decision below then uses the stale value: the term gate
`_open_term((*recorded_term, term_end_for(status, proof)), instant)` on line 105, the `starts_at`
clamp on line 73, and the transfer-month cap on line 87.

If the subscription's term ends inside that window, `_open_term` still reports it open, and line
150 calls `write_subscription_grant` with an `ends_at` that is already in the past.
`write_subscription_grant` has no term-vs-now guard of its own. It expires **every** grant the
destination holds, the free one included (`crud/subscriptions.py:338-352`), and then inserts a
grant that `_effective_grants_statement` (`crud/grants.py:34-36`) never returns. The account is
left holding nothing.

The loss is permanent. `ix_access_grants_one_free_grant_per_user_source`
(`migrations/20260818_01_initial-release.sql:266-268`) carries no status predicate, so expiry
never reopens the slot, and `activate_registered_account_grant` refuses with `prior_free_grant`
afterwards.

The ingestion path carries exactly this guard (`services/subscriptions.py:105-109` refuses when
`term_ends_at <= instant`). Restore does not.

**Fix:**
```python
async def restore(self, identity: LinkedIdentity, provider: PurchaseProvider,
                  restore_proof: str) -> None:
    proof = await self._verify(provider, restore_proof)
    # Read after the store call: the verify above can hold the request for the Play timeout.
    instant = datetime.now(UTC)
    ...
    term_ends_at = _open_term((*recorded_term, term_end_for(status, proof)), instant)
    if term_ends_at is None:
        raise RestoreSubscriptionNotEntitled(cause="term_closed")
    ...
    # Refused before the writer supersedes anything: an ended term must write no grant.
    if term_ends_at <= starts_at:
        raise RestoreSubscriptionNotEntitled(cause="term_closed")
```

---

### CR-02: Grants are stamped from the API pod's clock and selected by the database's

**File:** `src/nativespeaker/api/crud/grants.py:34-36,169,195-200,231,287-292`

**Issue:**
`_effective_grants_statement` now decides with `func.clock_timestamp()`, which PostgreSQL
evaluates on the database server:

```python
col(AccessGrant.starts_at) <= func.clock_timestamp(),
or_(col(AccessGrant.ends_at).is_(None),
    col(AccessGrant.ends_at) > func.clock_timestamp()))
```

Every writer of `starts_at` stamps it from `datetime.now(UTC)` on the API pod:
`activate_anonymous_device_grant` (line 169 into line 198), `activate_registered_account_grant`
(line 231 into line 290), and the subscription writer through
`RestoreService.restore` (`services/restore.py:73`) and
`crud/subscriptions.py:382-389`.

Before this phase both sides took the one Python value, so `starts_at <= <cutoff>` held by
construction. The two sides are now different machines. When the pod's clock leads the
database's by more than the few milliseconds between the write and the read-back, the
just-committed grant is not effective:

- `routers/auth.py:121`, `:144` and `:172` call `sync_service.read_entitlement` immediately after
  the completion commits, so a caller whose claim or restore returned 200 is told
  `type: none, monthly_used: 0`.
- `QuotaService.charge` refuses the same account with `branch="no_effective_grant"`
  (`services/quota.py:54-57`).
- A retry cannot recover. The row already holds `ix_access_grants_one_active_per_user`, so
  `activate_anonymous_device_grant` answers `refused, "active_grant_or_spent_slot"`
  (`crud/grants.py:189-190`).

The condition clears itself once the database clock passes `starts_at`, but for that window a
paying account is refused every request.

The same coupling exists on the challenge TTL: `issue` writes `expires_at` from the Python clock
(`crud/challenges.py:46-48`) and `_claim_statement` compares it to `clock_timestamp()`
(`crud/challenges.py:31`). The 300-second TTL absorbs any realistic skew there, so that site is
sound as written.

**Fix:** stamp the row from the same clock that selects it. One database read per writer keeps
the single-read rule the phase set and removes the coupling:

```python
async def _now(self) -> datetime:
    """The database's own clock, which is what the effective predicate compares against."""
    return (await self.session.exec(select(func.clock_timestamp()))).one()

async def activate_anonymous_device_grant(self, ...):
    instant = await self._now()
```

Stamping `starts_at=func.statement_timestamp()` in the `AccessGrant(...)` constructor is the
smaller change, but it leaves `created_at`, the usage period and
`free_grant_consumed_at` on the other clock, so the single read above is preferable.

## Warnings

### WR-01: One predicate, two clock reads

**File:** `src/nativespeaker/api/crud/grants.py:34-36`, `src/nativespeaker/api/crud/challenges.py:31-32`

**Issue:** `clock_timestamp()` is VOLATILE. PostgreSQL re-evaluates it for each call site and for
each row, so it changes inside one statement. Two consequences:

- `_effective_grants_statement` emits it twice. The lower bound and the upper bound of
  "effective now" are two different instants, and a multi-row scan compares different rows
  against different instants.
- `_claim_statement` decides with one read (`expires_at > func.clock_timestamp()`) and records
  another (`claimed_at=func.clock_timestamp()`). The recorded claim time is not the instant the
  expiry was judged at.

Neither is currently harmful — `status == active` plus `ix_access_grants_one_active_per_user`
keeps the grant scan to one row, and `claimed_at` is only read for null-ness at
`services/auth.py:135`. But the tests now enshrine the double read
(`tests/unit/test_sync_resolver.py:246` and `tests/unit/test_quota_resolver.py:372`:
`count("clock_timestamp()") == 2`), which makes a future second effective row decide against two
clocks.

**Fix:** use `func.statement_timestamp()`. It is fixed for the whole statement, and — unlike
`now()`/`transaction_timestamp()` — it still advances inside the e2e harness's outer transaction,
so D-01 holds. Update the two tests to assert `statement_timestamp()` instead.

---

### WR-02: Ingestion judges term-openness against an instant read before an unbounded lock wait

**File:** `src/nativespeaker/api/services/subscriptions.py:32,103,105-109`

**Issue:** `ingest` reads `instant` on line 32. Lines 46-64 then issue several statements,
including `lock_grants(owner)`, which takes `FOR UPDATE` on the buyer's grant rows
(`crud/subscriptions.py:100`) and blocks for as long as a rival transaction holds them. No
`lock_timeout` is set on the request session. The guard on lines 105-109 and the `starts_at`
clamp on line 103 then run against the stale value.

A term that closes during the lock wait passes `term_ends_at <= instant` and reaches
`write_subscription_grant`, which supersedes every grant the buyer holds and inserts one already
outside its term — the same end state as CR-01, reached through a different await.

**Fix:** re-read the clock after `lock_grants` returns and evaluate both the clamp and the guard
against that value.

---

### WR-03: `upsert_subscription` stamps one row from three clock reads, and the flush writes the oldest

**File:** `src/nativespeaker/api/crud/subscriptions.py:180,198-211,216-226,236,250`

**Issue:** `upsert_subscription` reads `instant` on line 180. It then calls
`claim_subscription_owner`, which reads its own clock on line 236 and writes
`updated_at` on the row, and `hold_subscription_clock`, which reads a third on line 250 and
writes `updated_at` again. The flush at line 226 then writes `stored.updated_at = instant` —
the oldest of the three — back over both. The committed column names an instant earlier than the
last write that touched the row.

`updated_at` is never read as a predicate anywhere in the package, which is the only reason this
is not a correctness break.

**Fix:** read once in `upsert_subscription` and pass that datetime down, restoring the parameter
`_hold_clock_statement` already takes:

```python
async def claim_subscription_owner(self, *, ..., instant: datetime) -> bool: ...
async def hold_subscription_clock(self, *, ..., instant: datetime) -> bool: ...
```

---

### WR-04: The only guard on the claim's strict expiry boundary no longer runs in the default suite

**File:** `tests/e2e/test_challenge_store.py:20,183-193`

**Issue:** `test_a_row_claimed_exactly_at_its_expiry_is_refused` was deleted. Its replacement is
`TestTheExpiryBoundaryIsPinnedInTheCompiledSQL`, which compiles `_claim_statement` and asserts
`"expires_at > clock_timestamp()" in rendered`. That class needs no database, but it sits in a
module carrying `pytestmark = pytest.mark.e2e` (line 20), and `pyproject.toml:71` runs
`-m 'not e2e and not schema'` by default. It is deselected on every ordinary run.

No unit-level case covers the comparison: `FakeChallengeStore` in `tests/unit/conftest.py:261`
reimplements `row.expires_at <= instant` rather than exercising the production statement. Flipping
`_claim_statement` to `>=` passes `uv run pytest`.

**Fix:** move the class to `tests/unit/test_challenge_ids.py`, which already imports from
`crud.challenges` and carries no marker.

---

### WR-05: `Retry-After` no longer has a case that drives the uncapped value through `charge`

**File:** `tests/unit/test_quota_resolver.py:433-453`

**Issue:** `test_a_rollover_closer_than_the_ceiling_is_the_value_sent` used to call `charge` near a
month boundary and assert `{"Retry-After": "60"}`. Its replacement,
`test_a_rollover_closer_than_the_ceiling_is_below_the_cap`, calls `seconds_until_rollover`
directly and never touches `QuotaService`. Both remaining charge-driven cases
(`test_an_exhausted_allowance_names_the_capped_wait`, `test_an_absent_grant_names_the_same_instant`)
expect `RETRY_AFTER_CEILING_SECONDS`.

Deleting the `min(...)` at `services/quota.py:44-45` and sending the constant unconditionally now
passes the whole suite, except on a run inside the last 300 seconds of a UTC month. The bracket
the replacement chose is wide enough to pass under the defect the case was written for.

**Fix:** keep one case that drives the real `charge` and asserts the wiring, deriving the expected
value from the same rule:

```python
async def test_the_header_is_the_rollover_when_it_is_nearer_than_the_ceiling(self):
    before = datetime.now(UTC)
    refusal = await self._refusal(grants=(), usage=None)
    after = datetime.now(UTC)
    assert refusal.extra_headers()["Retry-After"] in {
        str(min(seconds_until_rollover(edge), RETRY_AFTER_CEILING_SECONDS))
        for edge in (before, after)}
```

---

### WR-06: A rewritten assertion now restates a database CHECK instead of the property it names

**File:** `tests/schema/test_claim_race.py:544-552`

**Issue:** `test_the_seeded_grant_started_strictly_before_the_instant_that_expires_it` was
`assert started_at < NOW`. It is now:

```python
started_at, ended_at = rows[0]
assert started_at < ended_at
```

`core.access_grants` already declares `CHECK (ends_at IS NULL OR ends_at > starts_at)`
(`migrations/20260818_01_initial-release.sql:234`). The row could not have committed otherwise,
and the `raced` fixture would have failed before this case ran. The assertion cannot fail for the
reason its name and docstring state — it can only fail if the schema is gone.

**Fix:** bracket the driven writer and assert the seed really precedes it:

```python
# `raced` records the two live reads that bracket the conversion.
before, after = raced["bracket"]
assert started_at < before <= ended_at <= after
```

---

### WR-07: More module-import month constants compared against a service that reads its own clock

**File:** `tests/schema/test_restore_race.py:28,31`, `tests/unit/test_quota_resolver.py:33`, `tests/unit/test_sync_resolver.py:29`, `tests/unit/test_subscription_grant_write.py:28`, `tests/unit/test_conversion_carries_usage.py:26`

**Issue:** These are siblings of the tracked `tests/schema/test_claim_race.py` window. Each
derives a month at module import and compares it against a month the production code derives when
it runs, so a run that crosses a UTC month boundary between collection and assertion fails for the
wrong reason.

- `test_restore_race.py`: `NOW = datetime.now(UTC)` then `THIS_MONTH = NOW.date().replace(day=1)`,
  compared at lines 485, 598 and 657 against `last_cross_account_transfer_month`, which
  `RestoreService._this_month(instant)` writes from its own read.
- `test_quota_resolver.py` and `test_sync_resolver.py`: `PERIOD = monthly_period_for(datetime.now(UTC))`,
  compared against `monthly_period_for(instant)` derived inside `charge` and `read_entitlement`.
- `test_subscription_grant_write.py`: `THIS_MONTH` seeds the usage rows whose
  `monthly_period == period` decides whether `write_subscription_grant` carries the count forward
  (`crud/subscriptions.py:379-380`). Across a boundary the count is silently not carried and the
  case fails.
- `test_conversion_carries_usage.py`: `FRESH_PERIOD`, asserted at line 194.

**Fix:** derive the expected month inside the case, from reads bracketing the call, as
`tests/schema/test_subscription_ingestion.py:345-348` now does:

```python
assert usage["monthly_period"] in {monthly_period_for(before), monthly_period_for(after)}
```

---

### WR-08: A surviving docstring names an instant its case no longer uses

**File:** `tests/unit/test_quota_resolver.py:434-436`

**Issue:** `test_an_exhausted_allowance_names_the_capped_wait` still reads:

> WR-41: 2026-09-01T00:00Z is 10 days and 12 hours away, and that raw rollover is what both
> branches used to send.

The case no longer supplies `EVALUATED_AT`; `charge` reads the live clock. Nothing in the case is
ten days and twelve hours from anything, and the arithmetic the prose asks the next reader to
check is not the arithmetic the case runs.

**Fix:** restate the claim without a date — the branch is refused, and the header carries the
ceiling because the next rollover is further away than it.

## Info

### IN-01: A kept comment names `now()` where the module now uses `clock_timestamp()`

**File:** `src/nativespeaker/api/crud/grants.py:50-51`

**Issue:** The comment on `_active_grants_of_statement` reads "a partial index predicate must be
IMMUTABLE, so `now()` cannot appear in `ix_access_grants_one_active_per_user`". The rule is held
and the reasoning is right, but the function the module would otherwise reach for is now
`clock_timestamp()`, so the named function is no longer the one a reader would be tempted to add.

**Fix:** name the class rather than one member — "no clock function is IMMUTABLE, so none can
appear in `ix_access_grants_one_active_per_user`".

---

_Reviewed: 2026-09-12T10:04:39Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
