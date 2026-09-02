---
status: complete
phase: 40-post-auth-upgrade-anonymous
source: [40-VERIFICATION.md]
started: 2026-09-02T21:26:22Z
updated: 2026-09-02T22:32:00Z
---

## Current Test

[testing complete]

## Tests

### 1. WR-01 — revalidate identity_state and active under the lock, or accept the risk
expected: Either a follow-up plan lands the revalidation (mirroring `_reject_existing_identity`'s admission-time check), or a WINDOWS.md entry records the accepted risk with a reason.
context: `_apply_upgrade`'s docstring claims it revalidates the caller's locked rows, but only the provider is re-checked. An account blocked or retired during the challenge-commit + Firebase round-trip window can still complete the upgrade. Nothing writes either field today, so only a manual ops action triggers it. D-15 explicitly declined to write the live concurrent-mutation test that would exercise this.
result: pass
resolution: "Risk accepted. Ledger window 12 recorded and waived with reason; _apply_upgrade docstring corrected to state that only provider is re-checked."

### 2. WR-05 — fix, retire, or accept the "no second race arbiter" guard test
expected: Either the parametrize list is widened (which also requires an explicit narrow exemption for the one intentional lock), or the docstring is corrected to state that a lock exists and the test is retired/renamed so it no longer claims to guard an absence it cannot detect.
context: `tests/unit/test_conflict_classification.py:279` asserts `"for update"` and `"select_for_update"` are absent from a blob including `crud/identities.py`, which now calls `.with_for_update()` at line 69. Neither literal matches the token `ast.unparse` emits. The test would pass regardless of how many locks exist. A rationalising paragraph was added to the class docstring instead of updating the list.
result: pass
resolution: "Guard repaired. The two never-matching spellings were dropped from the parametrize list; a new test asserts `with_for_update` appears exactly once, so a second row lock now fails the build. Class docstring corrected to state that one lock exists deliberately."

### 3. WR-02 — confirm D-11's acceptance covers the weakened vocabulary oracle
expected: Either a follow-up plan narrows `/auth/challenge`'s issuance test to spendable operations, or WINDOWS.md/REQUIREMENTS.md is confirmed to already carry this acceptance explicitly enough that no further action is needed.
context: D-11 already accepts unspent handles for `claim_anonymous_grant` and `claim_registered_grant` as a documented one-phase cost. What is not disclosed anywhere is the second-order effect: `claim_anonymous_grant` was removed from the test's `_NOT_ISSUABLE` list, and that list exists per its own docstring so "the route cannot be asked which operation names are real". Low severity — the labels are public in the committed migration — but the specific regression was never named in the acceptance.
result: pass
resolution: "D-11's acceptance covered the unspendable handle but not the disclosure. Narrowing the issuance test was rejected: it would reintroduce the written-down issuable list D-11 exists to avoid. The second-order effect is now recorded in REQUIREMENTS.md against D-11's accepted-cost note, accepted on the same terms (the four labels are already public in the committed migration). The overclaiming docstring in tests/unit/test_challenge_endpoint.py:159 was corrected."

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
