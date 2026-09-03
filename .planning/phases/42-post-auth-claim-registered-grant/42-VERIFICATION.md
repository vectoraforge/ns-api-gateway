---
phase: 42-post-auth-claim-registered-grant
verified: 2026-09-03T23:15:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
behavior_unverified_items: []
re_verification:
  previous_status: human_needed
  previous_score: 4/4
  gaps_closed:
    - "CR-01 — a `status='active'` row past `ends_at` no longer costs the caller an irreversible DeviceCheck bit on a claim that cannot land; the route now refuses 403 before Apple is reached, on both claim routes"
    - "WR-01 — the crud writers' `IntegrityError` catch is narrowed to SQLSTATE 23505 (unique violation); a CHECK violation is re-raised and surfaces as a 500, proven against real PostgreSQL"
    - "WR-02 — a revoked `registered_account_grant` beside an active `anonymous_device_grant` now refuses the conversion with a 403 instead of answering 200 with the unchanged anonymous entitlement"
    - "WR-03 — both crud writers return a three-valued `ActivationOutcome` (activated/lost_race/refused) instead of `bool`; the route maps `refused` to 403 and `lost_race` to the repeat's 200"
    - "WR-04 — both writers and the registered preflight raise `MultipleEffectiveGrantsError` on a second effective grant, matching the tripwire `SyncService`/`QuotaService` already raise"
  gaps_remaining: []
  regressions: []
---

# Phase 42: POST /auth/claim-registered-grant Verification Report

**Phase Goal:** Ship the sole creator of `registered_account_grant` grants, including supersession of an active anonymous device grant.
**Verified:** 2026-09-03T23:15:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (plan 42-07)

## What Changed Since the Last Verification

Plan 42-07 closed CR-01 (critical, escalated to human decision in the prior verification) and the four
related warnings WR-01…WR-04. The developer's decision was fix-now rather than accept-and-gate. I did
not carry forward the prior verification's evidence for the writer or the service — both files changed
— and re-read `src/nativespeaker/api/crud/grants.py` and `src/nativespeaker/api/services/auth.py` in
full, along with `errors.py`'s two new leaves.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | This is the only code path that writes a grant row with `source='registered_account_grant'` | VERIFIED | Read `crud/grants.py` in full: exactly one `AccessGrant(source=AccessGrantSource.registered_account_grant, ...)` literal remains, at line 245 — Task 1/2's edits added reads and outcome mapping, not a second construction site. `tests/unit/test_grant_sources.py::TestTheRegisteredAccountGrantHasExactlyOneWriter` and its mutation-tested `TestTheRegisteredWalkFires` sibling: `pytest -q tests/unit/test_grant_sources.py` — 21 passed. |
| 2 | Superseding an active anonymous grant happens in one transaction and never leaves two `status='active'` grants | VERIFIED | The flush boundary between the conversion's expiry `UPDATE` and the registered `INSERT` (`crud/grants.py:231-243`) is unchanged from before 42-07. `tests/schema/test_grant_locks.py::TestTheConversionExpiresBeforeItInserts` (order proof from emitted SQL) and `tests/schema/test_claim_race.py::TestTwoSimultaneousConversionsSupersedeOnce` (two real connections, real PostgreSQL) both re-run green: 154 schema passed overall, 30 of them from `test_claim_race.py` alone, with `git diff --stat tests/schema/test_claim_race.py` empty — this file was not in 42-07's `files_modified` and I confirmed it is untouched. |
| 3 | The supersession honors the same fixed global lock order as Phase 41 | VERIFIED | `activate_registered_account_grant` now takes three lock statements instead of two: `lock_active_grants` (new, status-only) first, then `lock_effective_grants`, then `lock_usage` per grant — but the first two both target `core.access_grants` (grant tier), so the tier count is unchanged: two tiers, grant before usage, never `core.external_identities` or `core.users`. Verified live against real PostgreSQL: `tests/schema/test_grant_locks.py::TestTheRegisteredWriterAddsNoThirdLockTier` (5 cases) and `TestTheActivationAddsNoThirdLockTier` (the anonymous writer's sibling, still 2 tiers) — `pytest -m schema tests/schema/test_grant_locks.py -v` — 22/22 passed. |
| 4 | An account that already consumed its free grant as anonymous does not receive a second free entitlement | VERIFIED | `holds_grant_of_source` (index-shaped, status-free) now backstops `has_prior_free_grant` on both the preflight (`services/auth.py:220-222`, WR-02) and the writer (`crud/grants.py:227-228`); `has_prior_free_grant`/`FREE_GRANT_SOURCES` are untouched. `tests/unit/test_claim_precedence_registered.py`, `tests/schema/test_grant_locks.py::TestTheRegisteredWriterNamesWhyItRefused`, and `tests/e2e/test_claim_registered_grant.py::TestASpentRegisteredSlotRefusesTheConversion` all pass. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### CR-01 Disposition — Independently Re-Verified as Closed

I re-read the prior verification's fact pattern, then re-derived it from the current code rather than
trusting the summary:

- `_effective_grants_statement` still carries the time window; `ix_access_grants_one_active_per_user`
  still has none. That predicate mismatch is architectural and, per the plan, cannot be closed by
  editing the index (a partial index predicate must be IMMUTABLE). The fix instead gives the
  application a second, index-shaped read (`_active_grants_statement` / `read_active_grants` /
  `lock_active_grants`) that asks the index's own question on the mark alone.
- Both `_claim_registered_grant` (`services/auth.py:224-226`) and `_claim_anonymous_grant`
  (`services/auth.py:185-186`) now call `read_active_grants` and raise `ActiveGrantOutsideItsTerm`
  **before** `read_bits_with_retry`/`write_bits_with_retry` are reached. This was confirmed both by
  reading the code (the guard sits ahead of the `if not held:`/pre-Apple block on both routes) and by
  running `tests/unit/test_claim_ordering.py::TestBothVendorCallsPrecedeTheRegisteredActivation` —
  15/15 passed, including the case that the conversion arm reaches neither vendor seam.

**Live-database reproduction, run independently of the phase's own test suite.** I wrote and ran a
standalone script against the real dev PostgreSQL (`DB_HOST=localhost`, `DB_NAME=nativespeaker` from
`.env`, the same instance the e2e suite itself uses): seeded a `google`-linked user with one `manual`
grant row `status='active'`, `starts_at` an hour back, `ends_at` a minute back — the exact shape the
original CR-01 finding used — and called `GrantsDB.activate_registered_account_grant` directly.

```
OUTCOME: refused
ROW COUNT: 1
ROW STATUS: [('active', 'manual', <the seeded, unchanged ends_at>)]
```

The writer refuses rather than reporting an activation with nothing to read back, and the seeded row is
untouched. I then ran the phase's own end-to-end reproduction of the same scenario through the real
HTTP route (`tests/e2e/test_claim_registered_grant.py::TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple::test_a_term_lapsed_active_grant_is_refused_and_no_bit_is_read_or_written`
and its anonymous-route sibling in `test_claim_anonymous_grant.py`) — both pass against the same live
database, asserting 403, the exact refusal body, `scripted_devicecheck_adapter.read_calls == []`,
`write_calls == []`, and the seeded row's `updated_at` unchanged.

**CR-01 is closed**, verified from source, from a hand-seeded reproduction against the live database at
the writer, and from the same reproduction through the full route. The Apple-write-before-database-write
order was confirmed unchanged (`git diff --stat` on the writer shows no reordering of the bit write
relative to the flush; the objective states this explicitly and the code matches).

### The Three Executor Self-Reports, Judged

**1. The dropped case (unseedable).** The plan's third CR-01 case asked to seed an account holding both
an active `anonymous_device_grant` and a lapsed active `manual` row simultaneously. I reproduced the
attempt independently against the live database: inserting a second `status='active'` row for a user
already holding one raises `UniqueViolationError`, SQLSTATE `23505`, against
`ix_access_grants_one_active_per_user`. **Confirmed: genuinely unseedable.** The index the executor
cites is exactly the index that forbids it — this is not a rationalized skip, it is a correct reading of
the schema. The seedable equivalent (WR-02's revoked-registered-beside-active-anonymous shape, one
active row) was substituted and is covered at both the route and the writer.

**2. The writer's branch order — `lost_race` before `refused`.** Read directly from
`crud/grants.py:223-228`: `if superseded is None and await self.has_prior_free_grant(user_id): return
ActivationOutcome.lost_race` precedes `if await self.holds_grant_of_source(...): return
ActivationOutcome.refused`. This matches the plan's own listed order only for the *preflight* (which
does ask WR-02's question before CR-01's); inside the *writer*, the executor's stated reason — that
under READ COMMITTED a conversion-race loser blocked on `FOR UPDATE` would, once unblocked, see the
winner's freshly committed `registered_account_grant` row via `holds_grant_of_source` and be
misclassified as `refused` (a 403) instead of `lost_race` (the 200 the phase already proved) — is a real
hazard given the writer's per-statement snapshot behavior under READ COMMITTED, and
`test_claim_race.py::TestTwoSimultaneousConversionsSupersedeOnce` (30 collected, all passing, file
byte-identical) is the exact case that would have caught a misordering. **Agreed: this ordering is
correct and the deviation is justified**, not a shortcut.

**3. `enum` added to `ALLOWED_IMPORT_ROOTS`; `asyncpg` withheld.** Confirmed directly:
`tests/unit/test_claim_ordering.py:34` now reads `{"datetime", "enum", "uuid", "sqlalchemy", "sqlmodel",
"nativespeaker"}` — six roots, not five as the plan's literal acceptance criterion asked for (the
executor documented this as a Rule-3 deviation rather than silently passing it). `enum` is required
because `ActivationOutcome` is a `StrEnum` defined in `crud/grants.py`. The guard's actual security
property — no HTTP-capable module reachable from the crud layer — is enforced by
`FORBIDDEN_MODULES = ("httpx", "requests", "aiohttp", "urllib3")` and
`test_importing_the_module_pulls_in_no_http_client`, both untouched and both still passing. `enum` is
zero-I/O stdlib and cannot reach a network; `asyncpg` — the actually risky addition the plan forbids —
was not added, and the SQLSTATE is read via `getattr(violation.orig.__cause__, "sqlstate", None)`
without importing the driver. **Judgment: this does not weaken the guard.** The list widened by exactly
the module the new type requires, and the property the guard exists to protect is unchanged and still
tested.

### Required Artifacts (42-07 scope)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/crud/grants.py` | Two index-shaped reads, `ActivationOutcome`, narrowed catch, tripwire | VERIFIED | Read in full. `_active_grants_statement`, `_grants_of_source_statement`, `read_active_grants`, `lock_active_grants`, `holds_grant_of_source` all present; `ActivationOutcome` StrEnum with exactly `activated`/`lost_race`/`refused`; both writers return it; both `except IntegrityError` blocks narrow on `UNIQUE_VIOLATION = "23505"`; `MultipleEffectiveGrantsError` raised in both writers. |
| `src/nativespeaker/api/errors.py` | Fifth and sixth `ClaimRefused` leaves | VERIFIED | `ActiveGrantOutsideItsTerm` and `ClaimRefusedUnderLock`, each declaring nothing beyond a docstring; `ErrorCode` still has exactly 18 members (confirmed by direct import and `len(get_args(...))`). |
| `src/nativespeaker/api/services/auth.py` | Both preflights ask the index question before Apple; both loser arms branch on outcome | VERIFIED | Read in full. `_settle` is the one place an outcome becomes an answer: `activated` → return, `lost_race` → rollback + re-read + return-or-raise, otherwise → rollback + raise. No `session.refresh()` on either arm (grep confirms exactly one refresh call in the whole file, pre-existing and unrelated). |
| `tests/e2e/test_claim_registered_grant.py`, `test_claim_anonymous_grant.py` | CR-01/WR-02 reproduced end to end, 403, zero Apple calls | VERIFIED | Ran directly: both `TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple` classes pass against the live database. |
| `tests/schema/test_grant_locks.py` | Three outcomes + narrowed catch, measured against real PostgreSQL | VERIFIED | 22/22 passed live, including a real `CHECK` violation asserted to raise and a real unique violation asserted to map to `lost_race`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `services/auth.py::_claim_registered_grant` | `crud/grants.py::read_active_grants` | preflight asks the index's own question before Apple | VERIFIED | Line 224, ahead of the `if not held:` block at 228. |
| `services/auth.py::_claim_anonymous_grant` | `crud/grants.py::read_active_grants` | same guard, bit0 side | VERIFIED | Line 185, ahead of `read_bits_with_retry` at 189. |
| `crud/grants.py::_active_grants_statement` | `migrations/...sql::ix_access_grants_one_active_per_user` | predicate mirrors the index exactly, no time window | VERIFIED | Read both side by side: `WHERE status='active'`, no `starts_at`/`ends_at` term, matches `UNIQUE (user_id) WHERE status = 'active'`. |
| `crud/grants.py` writers | `services/auth.py::_settle` | `ActivationOutcome` return value | VERIFIED | Both `outcome = await self.grants_db.activate_...(...)` call sites feed directly into `await self._settle(identity, outcome)`. |

### Suite Counts (measured directly, not taken from SUMMARY.md)

| Suite | Command | Result |
|---|---|---|
| unit | `.venv/bin/python -m pytest -q` | **1016 passed**, 395 deselected |
| schema | `.venv/bin/python -m pytest -q -m schema` | **154 passed**, 1257 deselected |
| e2e | `.venv/bin/python -m pytest -q -m e2e` | **241 passed**, 1170 deselected |
| lint | `.venv/bin/ruff check src tests` | **All checks passed!** |
| `test_claim_race.py` alone | `.venv/bin/python -m pytest -q -m schema tests/schema/test_claim_race.py` | **30 passed** |

All match the orchestrator's pre-verification measurement exactly. `git diff --stat` on
`tests/schema/test_claim_race.py` and `migrations/20260818_01_initial-release.sql` is empty — both
byte-identical to before the fix, confirmed directly rather than assumed.

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|---|---|---|---|
| REGGRANT-01 | Sole creator, across prepare/completion | SATISFIED | One construction site confirmed post-fix; `.planning/REQUIREMENTS.md:326` marked `[x]`. |
| REGGRANT-02 | Supersession in one transaction, fixed lock order | SATISFIED | Flush-boundary and lock-tier proofs re-run green against real PostgreSQL; `:341` marked `[x]`. |
| REGGRANT-03 | One-free-grant-per-account interplay resolves without double-allocation | SATISFIED | `holds_grant_of_source` backstop closes WR-02; `:352` marked `[x]`. |
| ANONGRANT-02 | Database decided before Apple is asked (D-03) | SATISFIED (strengthened) | CR-01's bit0 half closed on the same terms; `read_active_grants` now runs ahead of `read_bits_with_retry` on the anonymous route too. |

No orphaned requirements.

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers in any of the 11 files 42-07 modified
(grepped directly). No stub returns, no hardcoded empty data flowing to a response.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| CR-01 refused at the writer, live DB, hand-seeded, independent of phase test suite | standalone script against `.env`'s real PostgreSQL | `OUTCOME: refused`, row untouched | PASS |
| The plan's dropped third case is genuinely unseedable | standalone script, seed 2nd active row | `UniqueViolationError 23505` on `ix_access_grants_one_active_per_user` | PASS |
| CR-01 refused at the route, registered | `pytest -m e2e tests/e2e/test_claim_registered_grant.py -k term_lapsed` | 2 passed | PASS |
| CR-01 refused at the route, anonymous | `pytest -m e2e tests/e2e/test_claim_anonymous_grant.py -k term_lapsed` | 1 passed | PASS |
| Vendor calls still precede activation on the new-grant arm; conversion still reaches neither | `pytest -q tests/unit/test_claim_ordering.py` | 15 passed | PASS |
| Sole-writer guard still holds post-fix | `pytest -q tests/unit/test_grant_sources.py` | 21 passed | PASS |
| Lock-tier order unchanged (two tiers, grant before usage) | `pytest -m schema tests/schema/test_grant_locks.py -v` | 22 passed | PASS |
| Race classes pass unedited | `pytest -m schema tests/schema/test_claim_race.py` | 30 passed, diff empty | PASS |
| `ErrorCode` gained no member | `python -c "...len(get_args(ErrorCode))"` | `18` | PASS |

### Probe Execution

Not applicable — no `scripts/*/tests/probe-*.sh` declared for this phase.

## Gaps Summary

None. All four ROADMAP success criteria hold under direct re-reading of the changed code, all measured
suite counts match exactly, and CR-01 plus WR-01…WR-04 are independently confirmed closed — at the
writer via a hand-seeded live-database reproduction I ran myself (not reused from the phase's test
suite), and at the route via the phase's own end-to-end reproduction re-run against the same live
database. All three of the executor's self-reported deviations were checked against source and the live
database and are judged sound: the dropped case is genuinely unseedable, the writer's branch reordering
is a correct fix for a real READ COMMITTED hazard proven by the still-passing race suite, and the
`enum` import-allowlist addition does not weaken the guard's actual security property.

No further human decision is outstanding for this phase.

---

*Verified: 2026-09-03T23:15:00Z*
*Verifier: Claude (gsd-verifier)*
