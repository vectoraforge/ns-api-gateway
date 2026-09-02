---
status: testing
phase: 40-post-auth-upgrade-anonymous
source: [40-VERIFICATION.md]
started: 2026-09-02T21:26:22Z
updated: 2026-09-02T21:26:22Z
---

## Current Test

number: 1
name: Decide whether WR-01's post-lock revalidation of identity_state and active is required before closing the phase
expected: |
  Either a follow-up plan lands the revalidation (mirroring _reject_existing_identity's
  admission-time check), or a WINDOWS.md entry records the accepted risk with a reason,
  per the ledger's own convention.
awaiting: user response

## Tests

### 1. WR-01 — revalidate identity_state and active under the lock, or accept the risk
expected: Either a follow-up plan lands the revalidation (mirroring `_reject_existing_identity`'s admission-time check), or a WINDOWS.md entry records the accepted risk with a reason.
context: `_apply_upgrade`'s docstring claims it revalidates the caller's locked rows, but only the provider is re-checked. An account blocked or retired during the challenge-commit + Firebase round-trip window can still complete the upgrade. Nothing writes either field today, so only a manual ops action triggers it. D-15 explicitly declined to write the live concurrent-mutation test that would exercise this.
result: [pending]

### 2. WR-05 — fix, retire, or accept the "no second race arbiter" guard test
expected: Either the parametrize list is widened (which also requires an explicit narrow exemption for the one intentional lock), or the docstring is corrected to state that a lock exists and the test is retired/renamed so it no longer claims to guard an absence it cannot detect.
context: `tests/unit/test_conflict_classification.py:279` asserts `"for update"` and `"select_for_update"` are absent from a blob including `crud/identities.py`, which now calls `.with_for_update()` at line 69. Neither literal matches the token `ast.unparse` emits. The test would pass regardless of how many locks exist. A rationalising paragraph was added to the class docstring instead of updating the list.
result: [pending]

### 3. WR-02 — confirm D-11's acceptance covers the weakened vocabulary oracle
expected: Either a follow-up plan narrows `/auth/challenge`'s issuance test to spendable operations, or WINDOWS.md/REQUIREMENTS.md is confirmed to already carry this acceptance explicitly enough that no further action is needed.
context: D-11 already accepts unspent handles for `claim_anonymous_grant` and `claim_registered_grant` as a documented one-phase cost. What is not disclosed anywhere is the second-order effect: `claim_anonymous_grant` was removed from the test's `_NOT_ISSUABLE` list, and that list exists per its own docstring so "the route cannot be asked which operation names are real". Low severity — the labels are public in the committed migration — but the specific regression was never named in the acceptance.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
