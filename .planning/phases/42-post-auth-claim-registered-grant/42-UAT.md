---
status: passed
phase: 42-post-auth-claim-registered-grant
source: [42-VERIFICATION.md]
started: 2026-09-03T22:15:00Z
updated: 2026-09-03T22:15:00Z
---

## Current Test

number: 1
name: Decide whether CR-01 must be fixed before Phase 42 is closed, or accepted and tracked as a blocking prerequisite for Phase 43
expected: |
  A recorded decision: fix now in a 42-07 closure plan, or accept-and-track with an
  explicit gate on Phase 43 (POST /webhooks/app-store) not landing a subscription or
  manual grant writer until the crud writer's `IntegrityError -> False` and the
  `read_effective_grants` / index predicate mismatch are reconciled.
awaiting: none — answered 2026-09-03: fix now

## Tests

### 1. Decide the disposition of CR-01 (code review, critical)

expected: A recorded decision — fix now in a 42-07 closure plan, or accept-and-track with an explicit gate on Phase 43 not landing a subscription or manual grant writer until the predicate mismatch and the overloaded `return False` are reconciled.

why_human: This is a severity and timing product decision, not a fact a verifier can resolve. The bug is real and was reproduced against the live database, but it is not reachable through any write path shipped by this phase or any prior phase — no code under `src/` writes a `manual` or `subscription` grant yet, and nothing flips `status` to `expired` when `ends_at` elapses. It becomes reachable the moment Phase 43 ships a subscription-grant writer with a term `ends_at`. Whether that risk is acceptable to carry into Phase 43 unfixed is the developer's call.

result: passed — developer decision 2026-09-03: FIX NOW. CR-01 is to be closed inside Phase 42 by a 42-07 gap-closure plan, not deferred to Phase 43. Phase 43's requirements (APPLEHOOK-01, APPLEHOOK-02) cover webhook signature verification and exact-path route enumeration only; they do not touch grant writes, so deferring would have added new scope to 43 rather than relying on existing scope.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
