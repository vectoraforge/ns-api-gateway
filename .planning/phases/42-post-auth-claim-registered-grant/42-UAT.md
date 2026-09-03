---
status: testing
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
awaiting: user response

## Tests

### 1. Decide the disposition of CR-01 (code review, critical)

expected: A recorded decision — fix now in a 42-07 closure plan, or accept-and-track with an explicit gate on Phase 43 not landing a subscription or manual grant writer until the predicate mismatch and the overloaded `return False` are reconciled.

why_human: This is a severity and timing product decision, not a fact a verifier can resolve. The bug is real and was reproduced against the live database, but it is not reachable through any write path shipped by this phase or any prior phase — no code under `src/` writes a `manual` or `subscription` grant yet, and nothing flips `status` to `expired` when `ends_at` elapses. It becomes reachable the moment Phase 43 ships a subscription-grant writer with a term `ends_at`. Whether that risk is acceptable to carry into Phase 43 unfixed is the developer's call.

result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
