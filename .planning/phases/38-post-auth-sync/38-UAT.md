---
status: complete
phase: 38-post-auth-sync
source: [38-VERIFICATION.md]
started: 2026-09-01T00:00:00Z
updated: 2026-09-01T21:16:08Z
---

## Current Test

[testing complete]

## Tests

### 1. Sync is lock-free under genuine concurrency

expected: Run two genuinely concurrent requests against a committed (non-transactional) test
database — one `POST /auth/sync` and one concurrent `QuotaService.charge` or grant-flip on the
same user/grant, using two real, independent connections (NOT the e2e harness's
single-connection uncommitted-transaction fixture). Sync's statements must neither block on nor
be blocked by the concurrent charge's locks, and both sync's response and the post-charge table
state must be internally consistent.

why_human: This is a state/ordering invariant that static analysis and the existing e2e harness
cannot exercise. `tests/e2e/conftest.py`'s `_db_transaction` binds every session to one
connection inside an uncommitted transaction, so a second connection cannot see the seeded rows.
Proving it needs a harness with committed fixtures.

tracked_as: WINDOWS.md entry 9 (open, unwaived); 38-06 coverage block D10 (human_judgment: true)

result: pass

verified_by: tests/schema/test_sync_lock_freedom.py — three cases against the committed
`tests/schema` scratch database (`_schema_db_uri`) on two real, independent connections,
driving the real `SyncService.read_entitlement` and `QuotaService.charge` rather than
mirrored SQL. `SET LOCAL lock_timeout = '500ms'` is the instrument: a statement that takes no
lock is unaffected by it, so surviving it is the assertion.

evidence: |
  - test_sync_reads_through_the_locks_a_charge_is_holding — a charge holds the grant row and the
    usage row FOR UPDATE, uncommitted; sync answers anyway, reporting the pre-charge count.
  - test_a_charge_is_not_blocked_by_an_open_sync_read — the converse: an open sync transaction
    does not stall the authoritative writer, which acquires both locks and commits.
  - test_a_racing_sync_lands_on_one_side_of_the_commit_or_the_other — 12 raced rounds; the count
    read is always the pre- or post-charge value, and tier/allowance always cohere.
  - Mutation control: flipping read_effective_grants/read_usage to the lock_* variants in
    services/sync.py fails cases 1 and 2 with LockNotAvailableError and TimeoutError. Source
    reverted clean.
  - ruff clean; 117 passed in tests/schema; 761 passed in tests/unit.

scope_note: Consistency was proven against a concurrent charge, which moves the usage count and
nothing else. The revoke-and-reissue tier/usage skew remains WR-06's accepted READ COMMITTED
warning and is out of scope here, as this checkpoint's wording allows.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
