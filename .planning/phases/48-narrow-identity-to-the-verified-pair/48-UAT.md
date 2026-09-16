---
status: complete
phase: 48-narrow-identity-to-the-verified-pair
source: 48-01-SUMMARY.md, 48-02-SUMMARY.md, 48-03-SUMMARY.md, 48-04-SUMMARY.md, 48-05-SUMMARY.md, 48-06-SUMMARY.md, 48-07-SUMMARY.md, 48-08-SUMMARY.md
started: 2026-09-16T22:55:08Z
updated: 2026-09-16T22:56:54Z
---

## Current Test

[testing complete]

## Tests

### 1. Looking up an account by token still rejects the three bad states
expected: Run this command: `.venv/bin/pytest -q tests/unit/test_identities_crud.py`. It prints `35 passed`. This proves the account lookup still rejects a deleted user, a retired identity, and a blocked user. It also proves the lookup no longer has the old `allow_preauth` switch.
result: pass
source: automated

### 2. Creating a user still behaves the same on the wire
expected: Start PostgreSQL on localhost. Run this command: `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py`. It prints `22 passed`. This proves every create-user response is the same as before. In particular, a caller who already has an account gets `409 identity_already_linked`.
result: pass
source: automated

### 3. A challenge issued to one account cannot be spent by another
expected: Start PostgreSQL on localhost. Run this command: `.venv/bin/pytest -q -m e2e tests/e2e/test_challenge_store.py`. It prints `32 passed`. This proves a challenge tied to one account is refused when a different caller presents it.
result: pass
source: automated

### 4. Grant records store the token's issuer and subject
expected: When a caller claims a grant, the grant row must store the issuer and subject from the caller's token. No unit test asserts the stored values directly. The upgrade test checks the provider is read with the token's issuer and subject. The database race test builds the token from the same values as the seeded account. Tell me if this coverage is enough, or describe the check you want added.
result: pass

### 5. 48-01 D1 — LinkedIdentity carries exactly user and identity, both required, frozen, slotted, over no base class
expected: LinkedIdentity carries exactly user and identity, both required, frozen, slotted, over no base class
result: pass
source: automated
coverage_id: 48-01 D1
verified_by: tests/unit/test_identity_accessors.py#TestTheLinkedIdentityShape::test_it_carries_both_rows_frozen_slotted_and_over_no_base_class

### 6. 48-01 D2 — AuthIdentity is gone from src/; the token result is VerifiedClaims from auth/jwt_verifier.py
expected: AuthIdentity is gone from src/; the token result is VerifiedClaims from auth/jwt_verifier.py
result: pass
source: automated
coverage_id: 48-01 D2
verified_by: grep -rn '\\bAuthIdentity\\b' src

### 7. 48-01 D3 — get_claims refuses the same five token arms and opens no session
expected: get_claims refuses the same five token arms and opens no session
result: pass
source: automated
coverage_id: 48-01 D3
verified_by: tests/unit/test_identity_accessors.py#TestTheWireArmsRaiseAndTheHandlerRecordsThemOnce::test_each_arm_logs_one_record_naming_its_class_and_its_bounded_reason; tests/unit/test_identity_accessors.py#TestAccessorsCannotProvision::test_the_admitting_declaration_reads_no_table_at_all

### 8. 48-01 D4 — get_identity answers 403 preauth_identity_not_allowed for a caller with no row, and resolves in its own short session closed before the handler
expected: get_identity answers 403 preauth_identity_not_allowed for a caller with no row, and resolves in its own short session closed before the handler
result: pass
source: automated
coverage_id: 48-01 D4
verified_by: tests/unit/test_identity_accessors.py#TestTheNarrowingHoldsInBothDirections::test_a_caller_with_no_row_on_a_linked_route_answers_403; tests/unit/test_identity_accessors.py#TestAccessorsCannotProvision::test_the_declaration_resolves_once

### 9. 48-01 D6 — The declaration matrix matches D-08's table, read off the live app
expected: The declaration matrix matches D-08's table, read off the live app
result: pass
source: automated
coverage_id: 48-01 D6
verified_by: tests/unit/test_app_wiring.py#TestEveryRouteIsAuthenticated

### 10. 48-01 D7 — A route declaring both dependencies verifies the token once and queries once
expected: A route declaring both dependencies verifies the token once and queries once
result: pass
source: automated
coverage_id: 48-01 D7
verified_by: tests/unit/test_app_wiring.py#TestTheAuthDependencyIsResolvedOncePerRequest::test_one_verify_and_one_query_for_a_doubly_declared_route

### 11. 48-02 D1 — resolve answers None when the joined query returns no row
expected: resolve answers None when the joined query returns no row
result: pass
source: automated
coverage_id: 48-02 D1
verified_by: tests/unit/test_identities_crud.py#TestOutcomeOneNoMatchingRow::test_resolve_answers_none_when_no_row_exists

### 12. 48-02 D2 — resolve answers a LinkedIdentity holding both rows when the row is active and its user is active
expected: resolve answers a LinkedIdentity holding both rows when the row is active and its user is active
result: pass
source: automated
coverage_id: 48-02 D2
verified_by: tests/unit/test_identities_crud.py#TestOutcomeFourLinkedAndActive::test_it_admits_with_the_resolved_rows; tests/unit/test_identities_crud.py#TestOutcomeFourLinkedAndActive::test_the_classifier_is_the_stored_provider_column

### 13. 48-02 D3 — An identity row with no user raises IdentityUnresolvable; a non-active row raises HistoricalIdentity; a non-active user raises BlockedUser — all three re-run against the new signature
expected: An identity row with no user raises IdentityUnresolvable; a non-active row raises HistoricalIdentity; a non-active user raises BlockedUser — all three re-run against the new signature
result: pass
source: automated
coverage_id: 48-02 D3
verified_by: tests/unit/test_identities_crud.py#TestUnresolvableUser; tests/unit/test_identities_crud.py#TestOutcomeTwoIdentityStateIsNotExactlyActive; tests/unit/test_identities_crud.py#TestOutcomeThreeUserIsNotExactlyTrue

### 14. 48-02 D4 — No test in either file passes the deleted flag or asserts a None row field
expected: No test in either file passes the deleted flag or asserts a None row field
result: pass
source: automated
coverage_id: 48-02 D4
verified_by: grep -n 'allow_preauth\\|preauth_callable' tests/unit/test_identities_crud.py tests/unit/test_exception_handlers.py

### 15. 48-02 D5 — The handler suite still answers 403 account_unavailable on both admission arms and logs one record each, driven through the real resolution
expected: The handler suite still answers 403 account_unavailable on both admission arms and logs one record each, driven through the real resolution
result: pass
source: automated
coverage_id: 48-02 D5
verified_by: tests/unit/test_exception_handlers.py#TestAnAccountUnavailableArmTravelsTheWholeErrorPath

### 16. 48-03 D1 — The challenge route resolves the caller itself, after the operation check, and a body refusal still issues no statement
expected: The challenge route resolves the caller itself, after the operation check, and a body refusal still issues no statement
result: pass
source: automated
coverage_id: 48-03 D1
verified_by: tests/unit/test_challenge_endpoint.py#TestEveryRefusalLeavesNothingBehind::test_nothing_is_issued_read_or_looked_up

### 17. 48-03 D2 — A caller with no row is refused every operation but create_user, and that refusal costs exactly one read
expected: A caller with no row is refused every operation but create_user, and that refusal costs exactly one read
result: pass
source: automated
coverage_id: 48-03 D2
verified_by: tests/unit/test_challenge_endpoint.py#TestTheAccountLessCallerPreparesCreateUserAndNothingElse::test_every_other_operation_is_the_preauth_refusal; tests/unit/test_challenge_endpoint.py#TestTheAccountLessCallerPreparesCreateUserAndNothingElse::test_create_user_is_issued_to_a_caller_with_no_account

### 18. 48-03 D3 — issue binds to linked.identity.id when the route resolved a row, and to claims otherwise
expected: issue binds to linked.identity.id when the route resolved a row, and to claims otherwise
result: pass
source: automated
coverage_id: 48-03 D3
verified_by: tests/unit/test_challenge_endpoint.py#TestTheIssuedChallengeIsBoundToWhatTheRouteResolved::test_a_caller_with_a_row_is_bound_to_that_row; tests/unit/test_challenge_endpoint.py#TestTheIssuedChallengeIsBoundToWhatTheRouteResolved::test_a_caller_with_no_row_is_bound_to_nothing; tests/unit/test_challenge_ids.py#TestTheBindingWrittenAtIssuance

### 19. 48-03 D4 — verify_binding's two branches and its rejection ordering are driven through the new signature
expected: verify_binding's two branches and its rejection ordering are driven through the new signature
result: pass
source: automated
coverage_id: 48-03 D4
verified_by: tests/unit/test_challenge_ids.py#TestTheCompletionComparison

### 20. 48-03 D6 — Every test in the three files builds a VerifiedClaims or a LinkedIdentity
expected: Every test in the three files builds a VerifiedClaims or a LinkedIdentity
result: pass
source: automated
coverage_id: 48-03 D6
verified_by: grep -rn '\\bAuthIdentity\\b' over the three files

### 21. 48-04 D1 — The upgrade route's rejection precedence is unchanged with both values supplied
expected: The upgrade route's rejection precedence is unchanged with both values supplied
result: pass
source: automated
coverage_id: 48-04 D1
verified_by: tests/unit/test_upgrade_precedence.py

### 22. 48-04 D2 — Both grant routes' rejection precedence is unchanged with both values supplied
expected: Both grant routes' rejection precedence is unchanged with both values supplied
result: pass
source: automated
coverage_id: 48-04 D2
verified_by: tests/unit/test_claim_precedence.py; tests/unit/test_claim_precedence_registered.py

### 23. 48-04 D3 — Each of the three suites overrides get_claims and get_identity, so no case runs the real account dependency against no database (T-48-04-01)
expected: Each of the three suites overrides get_claims and get_identity, so no case runs the real account dependency against no database (T-48-04-01)
result: pass
source: automated
coverage_id: 48-04 D3
verified_by: grep -c 'dependency_overrides\\[get_claims\\]\\|dependency_overrides\\[get_identity\\]' over the three files prints 2 each

### 24. 48-04 D4 — Every test in the three files builds a VerifiedClaims or a LinkedIdentity (D-11)
expected: Every test in the three files builds a VerifiedClaims or a LinkedIdentity (D-11)
result: pass
source: automated
coverage_id: 48-04 D4
verified_by: grep -n '\\bAuthIdentity\\b' over the three files

### 25. 48-05 D1 — The completion path issues exactly one statement, the identity query option B added
expected: The completion path issues exactly one statement, the identity query option B added
result: pass
source: automated
coverage_id: 48-05 D1
verified_by: tests/unit/test_create_user_precedence.py#TestTheCompletionPathIssuesOneStatement::test_the_whole_success_path_issues_exactly_one_statement; tests/unit/test_create_user_precedence.py#TestTheCompletionPathIssuesOneStatement::test_a_rejected_presentation_issues_the_same_one_statement; tests/unit/test_create_user_body.py#TestTheHandleReachesTheStore::test_a_body_handle_is_located_byte_for_byte

### 26. 48-05 D2 — The five challenge rejections keep their status, code, event name and place in the precedence
expected: The five challenge rejections keep their status, code, event name and place in the precedence
result: pass
source: automated
coverage_id: 48-05 D2
verified_by: tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections; tests/unit/test_create_user_precedence.py#TestThePrecedenceItself

### 27. 48-05 D3 — The four provider-stage rejections keep their status, code and stage, and every one of them consumes
expected: The four provider-stage rejections keep their status, code and stage, and every one of them consumes
result: pass
source: automated
coverage_id: 48-05 D3
verified_by: tests/unit/test_create_user_precedence.py#TestTheProviderStageRejections; tests/unit/test_create_user_precedence.py#TestEveryProviderStageRejectionConsumes

### 28. 48-05 D4 — The 422 validation partition is unchanged: an unusable handle issues nothing, locates nothing and reads nothing
expected: The 422 validation partition is unchanged: an unusable handle issues nothing, locates nothing and reads nothing
result: pass
source: automated
coverage_id: 48-05 D4
verified_by: tests/unit/test_create_user_body.py#TestTheValidationPartition; tests/unit/test_create_user_body.py#TestTheRejectionHasNoSideEffects

### 29. 48-05 D5 — The rollback arms and the SQLSTATE conflict classification are unchanged under `claims=`, including the 409 arm
expected: The rollback arms and the SQLSTATE conflict classification are unchanged under `claims=`, including the 409 arm
result: pass
source: automated
coverage_id: 48-05 D5
verified_by: tests/unit/test_create_user_rollback.py; tests/unit/test_conflict_classification.py#TestTheInsertsUniqueViolationIsTheSubjectRace; tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms

### 30. 48-05 D6 — T-48-05-01: `_reject_existing_identity` keeps all three arms, each asserted by the suite
expected: T-48-05-01: `_reject_existing_identity` keeps all three arms, each asserted by the suite
result: pass
source: automated
coverage_id: 48-05 D6
verified_by: tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms::test_an_active_linked_row_raises_already_linked_and_inserts_nothing; tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms::test_a_historical_row_raises_account_unavailable; tests/unit/test_conflict_classification.py#TestTheReResolutionsThreeNoMutationArms::test_an_active_row_whose_user_is_blocked_raises_account_unavailable

### 31. 48-05 D7 — T-48-05-03: the handle reaches neither logger
expected: T-48-05-03: the handle reaches neither logger
result: pass
source: automated
coverage_id: 48-05 D7
verified_by: tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections::test_every_rejection_is_recorded_exactly_once_and_never_names_the_handle; tests/unit/test_create_user_precedence.py#TestTheTransactionRejectionIsObservedAtTheHandler::test_the_handle_never_reaches_either_log

### 32. 48-06 D1 — RestoreService.restore is driven by the renamed parameter at all 11 call sites, with every refusal unchanged
expected: RestoreService.restore is driven by the renamed parameter at all 11 call sites, with every refusal unchanged
result: pass
source: automated
coverage_id: 48-06 D1
verified_by: tests/unit/test_restore_proof.py; test \"$(grep -c 'linked=' tests/unit/test_restore_proof.py)\" = \"11\"

### 33. 48-06 D2 — Every LinkedIdentity in these four files is built with two keywords and carries no token value (D-02)
expected: Every LinkedIdentity in these four files is built with two keywords and carries no token value (D-02)
result: pass
source: automated
coverage_id: 48-06 D2
verified_by: grep -n 'issuer=' tests/unit/test_restore_proof.py returns only the ExternalIdentity row field; grep -n 'get_linked_identity|\\bAuthIdentity\\b' over the three Task 2 files

### 34. 48-06 D3 — The users route suite overrides get_identity, and the handler's reads of linked.user and linked.identity stay pinned (D-08)
expected: The users route suite overrides get_identity, and the handler's reads of linked.user and linked.identity stay pinned (D-08)
result: pass
source: automated
coverage_id: 48-06 D3
verified_by: tests/unit/test_users_me.py#TestTheProfileTakesOneQuery::test_the_read_is_keyed_on_the_barrier_resolved_caller; tests/unit/test_users_me.py#TestTheProfileBodyIsClosed

### 35. 48-06 D4 — Both probe routes declare the account dependency by its new name, and neither suite's subject moved (D-05)
expected: Both probe routes declare the account dependency by its new name, and neither suite's subject moved (D-05)
result: pass
source: automated
coverage_id: 48-06 D4
verified_by: tests/unit/test_auth_security.py#test_the_probe_route_declares_the_dependency; tests/unit/test_jwks_offload.py

### 36. 48-06 D5 — The whole e2e suite collects again, which 48-03 named as this plan's gating effect
expected: The whole e2e suite collects again, which 48-03 named as this plan's gating effect
result: pass
source: automated
coverage_id: 48-06 D5
verified_by: .venv/bin/pytest -q -m e2e --collect-only tests/e2e; tests/e2e/test_challenge_store.py (48-03's unscaffolded re-run)

### 37. 48-07 D1 — The claim race resolves with two keywords and drives both claim completions with claims and linked, and each race still commits exactly one grant row
expected: The claim race resolves with two keywords and drives both claim completions with claims and linked, and each race still commits exactly one grant row
result: pass
source: automated
coverage_id: 48-07 D1
verified_by: tests/schema/test_claim_race.py#TestTwoSimultaneousFirstClaimsAllocateOnce::test_exactly_one_grant_row_exists_on_the_anonymous_tier; tests/schema/test_claim_race.py#TestTwoSimultaneousRegisteredClaimsAllocateOnce::test_exactly_one_grant_row_exists_on_the_registered_tier

### 38. 48-07 D2 — Both create suites drive AuthService.complete with claims, and the create race still yields exactly one account
expected: Both create suites drive AuthService.complete with claims, and the create race still yields exactly one account
result: pass
source: automated
coverage_id: 48-07 D2
verified_by: tests/schema/test_create_race.py; tests/schema/test_create_atomicity.py

### 39. 48-07 D3 — The restore race builder carries both rows, and the raced restore still commits exactly one grant
expected: The restore race builder carries both rows, and the raced restore still commits exactly one grant
result: pass
source: automated
coverage_id: 48-07 D3
verified_by: tests/schema/test_restore_race.py

### 40. 48-07 D4 — D-03: no schema test passes the deleted flag
expected: D-03: no schema test passes the deleted flag
result: pass
source: automated
coverage_id: 48-07 D4
verified_by: test -z \"$(grep -rn 'allow_preauth' tests/schema)\"

### 41. 48-07 D5 — D-11: every schema test builds a VerifiedClaims or a LinkedIdentity
expected: D-11: every schema test builds a VerifiedClaims or a LinkedIdentity
result: pass
source: automated
coverage_id: 48-07 D5
verified_by: grep -rn '\\bAuthIdentity\\b' src tests

### 42. 48-07 D6 — The two schema files this plan does not own, which fail at import only through these four, are green again
expected: The two schema files this plan does not own, which fail at import only through these four, are green again
result: pass
source: automated
coverage_id: 48-07 D6
verified_by: .venv/bin/pytest -q -m schema tests/schema (297 passed)

### 43. 48-08 D1 — Criterion 1: AuthIdentity is named nowhere in src or tests, and LinkedIdentity has two required fields over no base class
expected: Criterion 1: AuthIdentity is named nowhere in src or tests, and LinkedIdentity has two required fields over no base class
result: pass
source: automated
coverage_id: 48-08 D1
verified_by: test -z \"$(grep -rn '\\bAuthIdentity\\b' src tests)\"; tests/unit/test_identity_accessors.py#TestTheLinkedIdentityShape::test_it_carries_both_rows_frozen_slotted_and_over_no_base_class

### 44. 48-08 D2 — Criterion 4: no test passes the deleted flag and none names a deleted dependency
expected: Criterion 4: no test passes the deleted flag and none names a deleted dependency
result: pass
source: automated
coverage_id: 48-08 D2
verified_by: test -z \"$(grep -rn 'get_linked_identity\\|allow_preauth=\\|preauth_callable(' src tests)\"

### 45. 48-08 D3 — Criterion 3: only crud/challenges.py and AuthService._complete take LinkedIdentity | None as a parameter
expected: Criterion 3: only crud/challenges.py and AuthService._complete take LinkedIdentity | None as a parameter
result: pass
source: automated
coverage_id: 48-08 D3
verified_by: grep -rn 'LinkedIdentity | None' src | grep -v -- '-> LinkedIdentity | None' yields two files

### 46. 48-08 D4 — Criterion 5: the three suites are re-run at this phase's HEAD and the only failing case is the pre-existing restore case
expected: Criterion 5: the three suites are re-run at this phase's HEAD and the only failing case is the pre-existing restore case
result: pass
source: automated
coverage_id: 48-08 D4
verified_by: .venv/bin/pytest -q -m '' (1 failed, 2572 passed); .venv/bin/pytest -q -m e2e (1 failed, 360 passed); .venv/bin/pytest -q -m schema (297 passed)

### 47. 48-08 D5 — The controls hold: ruff is clean and ty does not rise above 311 diagnostics
expected: The controls hold: ruff is clean and ty does not rise above 311 diagnostics
result: pass
source: automated
coverage_id: 48-08 D5
verified_by: .venv/bin/ruff check src tests (All checks passed!); .venv/bin/ty check (Found 306 diagnostics)

### 48. 48-08 D6 — 48-01 coverage D8, carried to the gate: every create-user wire outcome is unchanged under option B, at the e2e layer
expected: 48-01 coverage D8, carried to the gate: every create-user wire outcome is unchanged under option B, at the e2e layer
result: pass
source: automated
coverage_id: 48-08 D6
verified_by: tests/e2e/test_create_user.py (22 passed); tests/e2e/test_create_user.py#TestCompletionRejectsAnAlreadyLinkedCaller::test_an_active_linked_identity_is_rejected_at_completion

### 49. 48-08 D7 — D-07 is recorded with the answer it was given, as WINDOWS.md entry 33
expected: D-07 is recorded with the answer it was given, as WINDOWS.md entry 33
result: pass
source: automated
coverage_id: 48-08 D7
verified_by: grep -c '\"phase\": \"48\"' .planning/WINDOWS.md prints 1; the entry parses and its status is waived

### 50. 48-08 D8 — D-09: the ROADMAP entry already carries the amended goal and criteria; REQUIREMENTS.md maps nothing to this phase
expected: D-09: the ROADMAP entry already carries the amended goal and criteria; REQUIREMENTS.md maps nothing to this phase
result: pass
source: automated
coverage_id: 48-08 D8
verified_by: git diff --name-only HEAD -- .planning/REQUIREMENTS.md is empty; no traceability row names phase 48

## Summary

total: 50
passed: 50
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
