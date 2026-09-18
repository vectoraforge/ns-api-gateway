---
status: complete
phase: 49-delete-the-single-implementation-auth-protocols
source: 49-01-SUMMARY.md, 49-02-SUMMARY.md, 49-03-SUMMARY.md, 49-04-SUMMARY.md
started: 2026-09-18T02:25:53Z
updated: 2026-09-18T02:49:02Z
---

## Current Test

[testing complete]

## Tests

### 1. Confirm the automated coverage of Phase 49
expected: All 27 deliverables are covered by automated checks re-run at HEAD c6eb771 (suite 1 failed pre-existing / 2563 passed, ruff clean, ty 295 < 306). Three descriptions are stale after review-fix commits IN-04, WR-01, WR-03; one residual (IN-04 guard unreplaced) is open. User confirms or reports.
result: pass

### 2. PlaySubscriptionSource is deleted and RestoreService annotates play as PlayDeveloperSubscriptions
expected: PlaySubscriptionSource is deleted and RestoreService annotates play as PlayDeveloperSubscriptions
result: pass
source: automated
coverage_id: 49-01 D1

### 3. TokenVerifier is deleted and PubSubPushTokens annotates verifier and build as JWTVerifier
expected: TokenVerifier is deleted and PubSubPushTokens annotates verifier and build as JWTVerifier
result: pass
source: automated
coverage_id: 49-01 D2

### 4. Each seam commit carries its own re-measured auth package-shape tuple (D-08)
expected: Each seam commit carries its own re-measured auth package-shape tuple (D-08)
result: pass
source: automated
coverage_id: 49-01 D3

### 5. The whole suite carries only the pre-existing restore four-arms failure
expected: The whole suite carries only the pre-existing restore four-arms failure
result: pass
source: automated
coverage_id: 49-01 D4

### 6. DeviceCheckAdapter is deleted and both retry helpers plus both dependency sites annotate AppleDeviceCheck
expected: DeviceCheckAdapter is deleted and both retry helpers plus both dependency sites annotate AppleDeviceCheck
result: pass
source: automated
coverage_id: 49-02 D1

### 7. FirebaseAdminAdapter is deleted, auth/adapters.py is removed, and VerifiedProviderIdentity is re-homed
expected: FirebaseAdminAdapter is deleted, auth/adapters.py is removed, and VerifiedProviderIdentity is declared in auth/firebase.py (moved again to schemas/auth.py by IN-04, 0ee572f)
result: pass
source: automated
coverage_id: 49-02 D2

### 8. The package-wide SDK-isolation guard still walks every surviving auth module, from its new home
expected: The package-wide SDK-isolation guard still walks every surviving auth module, from its new home
result: pass
source: automated
coverage_id: 49-02 D3

### 9. The frozen and slotted properties of VerifiedProviderIdentity are still asserted, from their new home
expected: The frozen and slotted properties of VerifiedProviderIdentity are still asserted, from their new home
result: pass
source: automated
coverage_id: 49-02 D4

### 10. Each of the two seam commits carries its own re-measured auth package-shape tuple (D-08)
expected: Each of the two seam commits carries its own re-measured auth package-shape tuple (D-08)
result: pass
source: automated
coverage_id: 49-02 D5

### 11. All three suites carry only the pre-existing restore four-arms failure
expected: All three suites carry only the pre-existing restore four-arms failure
result: pass
source: automated
coverage_id: 49-02 D6

### 12. The lifespan builds no challenge crud object and the request-scoped accessor is gone
expected: The lifespan builds no challenge crud object and the request-scoped accessor is gone
result: pass
source: automated
coverage_id: 49-03 D1

### 13. AuthService holds self.challenges_db and builds it itself (D-02)
expected: AuthService holds self.challenges_db and builds it itself (D-02)
result: pass
source: automated
coverage_id: 49-03 D2

### 14. The challenge handler builds its own crud object inline, as it builds the identities one (D-03)
expected: The challenge handler builds its own crud object inline (superseded by WR-01, a4be3cd: it now takes ChallengesDB from the get_challenges_db dependency)
result: pass
source: automated
coverage_id: 49-03 D3

### 15. One fixture in tests/unit/conftest.py serves the four precedence suites by monkeypatching the crud class (D-04)
expected: One fixture in tests/unit/conftest.py serves the four precedence suites by monkeypatching the crud class (D-04)
result: pass
source: automated
coverage_id: 49-03 D4

### 16. The two recorder suites each keep their own recorder and patch the issue method (D-05)
expected: The two recorder suites each keep their own recorder and patch the issue method (D-05)
result: pass
source: automated
coverage_id: 49-03 D5

### 17. The four rejection precedence orders are unchanged and the binding check stays the real method (T-49-08, T-49-09)
expected: The four rejection precedence orders are unchanged and the binding check stays the real method (T-49-08, T-49-09)
result: pass
source: automated
coverage_id: 49-03 D6

### 18. Single-use consume and the claim race are unchanged against live PostgreSQL (T-49-10)
expected: Single-use consume and the claim race are unchanged against live PostgreSQL (T-49-10)
result: pass
source: automated
coverage_id: 49-03 D7

### 19. The type-gate count is measured against the 306 baseline and has not risen (T-49-12)
expected: The type-gate count is measured against the 306 baseline and has not risen (T-49-12)
result: pass
source: automated
coverage_id: 49-03 D8

### 20. All three suites carry only the pre-existing restore four-arms failure
expected: All three suites carry only the pre-existing restore four-arms failure
result: pass
source: automated
coverage_id: 49-03 D9

### 21. ChallengesDB takes the session in its constructor and no method takes one (D-01)
expected: ChallengesDB takes the session in its constructor and no method takes one (D-01)
result: pass
source: automated
coverage_id: 49-04 D1

### 22. verify_binding keeps its three parameters and its body byte-for-byte, and _claim_statement is untouched (D-01, T-49-13, T-49-15)
expected: verify_binding keeps its three parameters and its body byte-for-byte, and _claim_statement is untouched (verify_binding later moved out of the class by WR-03, 1150793)
result: pass
source: automated
coverage_id: 49-04 D2

### 23. AuthService builds ChallengesDB(db) and the challenge handler builds ChallengesDB(session)
expected: AuthService builds ChallengesDB(db) and the challenge handler builds ChallengesDB(session) (handler side superseded by WR-01, a4be3cd)
result: pass
source: automated
coverage_id: 49-04 D3

### 24. No crud object spans two sessions; the e2e module fixture is gone (T-49-16)
expected: No crud object spans two sessions; the e2e module fixture is gone (T-49-16)
result: pass
source: automated
coverage_id: 49-04 D4

### 25. The claim UPDATE, the consume UPDATE and the expiry predicate are unchanged against live PostgreSQL (T-49-13, T-49-14)
expected: The claim UPDATE, the consume UPDATE and the expiry predicate are unchanged against live PostgreSQL (T-49-13, T-49-14)
result: pass
source: automated
coverage_id: 49-04 D5

### 26. The crud module still holds no logger and no handle reaches a log call (T-49-17)
expected: The crud module still holds no logger and no handle reaches a log call (T-49-17)
result: pass
source: automated
coverage_id: 49-04 D6

### 27. The three suites, ruff and ty are re-measured at the phase gate rather than copied
expected: The three suites, ruff and ty are re-measured at the phase gate rather than copied
result: pass
source: automated
coverage_id: 49-04 D7

### 28. 49-VALIDATION.md carries a fully green verification map naming the one pre-existing failure
expected: 49-VALIDATION.md carries a fully green verification map naming the one pre-existing failure
result: pass
source: automated
coverage_id: 49-04 D8

## Summary

total: 28
passed: 28
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
