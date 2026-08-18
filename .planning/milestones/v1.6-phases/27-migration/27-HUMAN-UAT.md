---
status: partial
phase: 27-migration
source: [27-VERIFICATION.md]
started: "2026-03-24T00:00:00Z"
updated: "2026-03-24T00:00:00Z"
---

## Current Test

[awaiting human testing]

## Tests

### 1. pogo apply succeeds against fresh PostgreSQL
expected: `pogo apply` exits 0, creates 6 tables + 4 enum types in `core` schema, no `core.plans` table
result: [pending]

### 2. Enum enforcement rejects invalid values
expected: INSERT with invalid enum string (e.g., `'invalid'`) into `subscription_plan`, `role`, `provider`, `status` columns is rejected by PostgreSQL with `invalid input value for enum`
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
