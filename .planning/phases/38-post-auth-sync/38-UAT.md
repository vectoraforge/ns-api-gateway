---
status: testing
phase: 38-post-auth-sync
source: [38-VERIFICATION.md]
started: 2026-09-01T00:00:00Z
updated: 2026-09-01T00:00:00Z
---

## Current Test

number: 1
name: Sync is lock-free under genuine concurrency
expected: |
  Sync's statements (no FOR UPDATE) neither block on nor are blocked by the concurrent
  charge's locks, and sync's response and the post-charge table state are each internally
  consistent — no partial read straddling the charge's commit that produces an impossible
  tier/usage pairing worse than the already-accepted READ COMMITTED skew noted in
  38-REVIEW.md WR-06.
awaiting: user response

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

result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
