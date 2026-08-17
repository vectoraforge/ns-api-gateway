"""The `core.auth_challenges` column semantics: what the row admits, what it binds, what state
its columns carry, and what it never records."""

from dataclasses import fields
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from nativespeaker.api.auth.challenges import (
    AUTH_CHALLENGE_COLUMNS,
    CHALLENGE_FREE_OPERATIONS,
    CHALLENGE_PURGE_JOBS,
    CONSUMED_OUTCOME_LOG,
    EXPIRY_ENFORCEMENT_POINTS,
    OUTCOME_COLUMN_NAMES,
    ChallengeError,
    ChallengeRow,
    ChallengeState,
    IdentityBinding,
    PrepareResponse,
    assert_challenge_row_operation,
    assert_expiry_enforcement_point,
    assert_no_key_version_column,
    assert_no_outcome_column,
    assert_no_raw_subject_column,
    assert_operation_variant,
    assert_row_id_not_disclosed,
    challenge_retention_deadline,
    challenge_state_from_columns,
    completion_capability,
    preauth_binding,
    preauth_subject_hash,
    preauth_subject_matches,
    replay_authority,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider

EXPIRES = datetime(2099, 1, 1, tzinfo=UTC)
ISSUER = "https://securetoken.google.com/test-project"


def hasher(key: bytes):
    """A stand-in for the shared `actor_subject_hash` keyed hasher, versioned like the real one."""
    import hashlib
    import hmac

    def _hash(subject: str) -> tuple[bytes, int]:
        return hmac.new(key, subject.encode("utf-8"), hashlib.sha256).digest(), 7

    return _hash


def row(**overrides) -> ChallengeRow:
    values: dict[str, Any] = {"challenge_id": "handle-1",
              "operation": AuthOperation.claim_anonymous_grant,
              "operation_variant": None,
              "binding": IdentityBinding(bound_external_identity_id=uuid4()),
              "expires_at": EXPIRES,
              "id": uuid4()}
    values.update(overrides)
    return ChallengeRow(**values)


class TestWhichOperationsGetARow:

    # [utest->req~schema-auth-challenges-purpose~1]
    def test_the_four_challenge_bearing_operations_are_admitted(self):
        for operation in (AuthOperation.create_user,
                          AuthOperation.upgrade_anonymous_to_registered,
                          AuthOperation.claim_anonymous_grant,
                          AuthOperation.claim_registered_grant):
            assert assert_challenge_row_operation(operation) is operation

    # [utest->req~schema-auth-challenges-purpose~1]
    def test_the_three_challenge_free_operations_get_no_row(self):
        assert CHALLENGE_FREE_OPERATIONS == {AuthOperation.restore_subscription,
                                             AuthOperation.sign_out_all,
                                             AuthOperation.sync}
        for operation in CHALLENGE_FREE_OPERATIONS:
            with pytest.raises(ChallengeError):
                assert_challenge_row_operation(operation)


class TestOperationVariantRules:

    # [utest->req~schema-auth-challenges-operation-variant-rules~1]
    def test_create_user_takes_all_three_variants(self):
        for variant in (IdentityProvider.anonymous, IdentityProvider.google,
                        IdentityProvider.apple):
            assert assert_operation_variant(AuthOperation.create_user, variant) is variant

    # [utest->req~schema-auth-challenges-operation-variant-rules~1]
    def test_the_upgrade_takes_only_the_two_registered_variants(self):
        for variant in (IdentityProvider.google, IdentityProvider.apple):
            assert assert_operation_variant(
                AuthOperation.upgrade_anonymous_to_registered, variant) is variant
        with pytest.raises(ChallengeError):
            assert_operation_variant(AuthOperation.upgrade_anonymous_to_registered,
                                     IdentityProvider.anonymous)

    # [utest->req~schema-auth-challenges-operation-variant-rules~1]
    def test_the_variant_is_required_where_the_operation_defines_one(self):
        for operation in (AuthOperation.create_user,
                          AuthOperation.upgrade_anonymous_to_registered):
            with pytest.raises(ChallengeError):
                assert_operation_variant(operation, None)

    # [utest->req~schema-auth-challenges-operation-variant-rules~1]
    def test_the_two_variant_free_operations_take_null(self):
        for operation in (AuthOperation.claim_anonymous_grant,
                          AuthOperation.claim_registered_grant):
            assert assert_operation_variant(operation, None) is None
            with pytest.raises(ChallengeError):
                assert_operation_variant(operation, IdentityProvider.google)

    # [utest->req~schema-auth-challenges-operation-variant-rules~1]
    def test_no_other_auth_operation_may_appear_in_operation_at_all(self):
        with pytest.raises(ChallengeError):
            assert_operation_variant(AuthOperation.sync, None)


class TestLifecycleStateInColumns:

    # [utest->req~schema-auth-challenges-binds-lifecycle-state~2]
    def test_issued_while_claimed_at_is_null(self):
        assert challenge_state_from_columns(claimed_at=None, claim_attempt_id=None,
                                            consumed_at=None) is ChallengeState.issued

    # [utest->req~schema-auth-challenges-binds-lifecycle-state~2]
    def test_claimed_once_claimed_at_and_the_attempt_id_are_set(self):
        assert challenge_state_from_columns(claimed_at=EXPIRES, claim_attempt_id=uuid4(),
                                            consumed_at=None) is ChallengeState.claimed

    # [utest->req~schema-auth-challenges-binds-lifecycle-state~2]
    def test_consumed_once_consumed_at_is_set(self):
        assert challenge_state_from_columns(claimed_at=EXPIRES, claim_attempt_id=uuid4(),
                                            consumed_at=EXPIRES) is ChallengeState.consumed

    # [utest->req~schema-auth-challenges-binds-lifecycle-state~2]
    def test_a_half_written_claim_is_refused(self):
        with pytest.raises(ChallengeError):
            challenge_state_from_columns(claimed_at=EXPIRES, claim_attempt_id=None,
                                         consumed_at=None)
        with pytest.raises(ChallengeError):
            challenge_state_from_columns(claimed_at=None, claim_attempt_id=uuid4(),
                                         consumed_at=None)


class TestIdentityBinding:

    # [utest->req~schema-auth-challenges-exactly-one-identity-binding~1]
    def test_exactly_one_identity_context_is_set(self):
        IdentityBinding(bound_external_identity_id=uuid4())
        IdentityBinding(preauth_issuer=ISSUER, preauth_subject_hash=b"x" * 32)
        with pytest.raises(ChallengeError):
            IdentityBinding()
        with pytest.raises(ChallengeError):
            IdentityBinding(bound_external_identity_id=uuid4(), preauth_issuer=ISSUER)

    # [utest->req~schema-auth-challenges-exactly-one-identity-binding~1]
    def test_a_linked_binding_stores_no_preauth_verifier(self):
        with pytest.raises(ChallengeError):
            IdentityBinding(bound_external_identity_id=uuid4(), preauth_subject_hash=b"x" * 32)

    # [utest->req~schema-auth-challenges-exactly-one-identity-binding~1]
    def test_the_cleared_verifier_is_admitted_only_once_consumed(self):
        cleared = IdentityBinding(preauth_issuer=ISSUER, preauth_subject_hash=None)
        consumed = row(binding=cleared, state=ChallengeState.consumed,
                       claim_attempt_id=uuid4())
        assert consumed.verifier_cleared is True
        assert consumed.binding.preauth_issuer == ISSUER
        with pytest.raises(ChallengeError):
            row(binding=cleared, state=ChallengeState.claimed, claim_attempt_id=uuid4())
        with pytest.raises(ChallengeError):
            row(binding=cleared)


class TestPreauthSubjectHash:

    # [utest->req~schema-auth-challenges-preauth-subject-hash-derivation~1]
    def test_prepare_stores_a_keyed_verifier_and_a_plaintext_issuer(self):
        binding = preauth_binding(ISSUER, "sub-1", hasher(b"key-a"))
        assert binding.preauth_issuer == ISSUER
        assert binding.preauth_subject_hash == preauth_subject_hash("sub-1", hasher(b"key-a"))
        assert b"sub-1" not in (binding.preauth_subject_hash or b"")

    # [utest->req~schema-auth-challenges-preauth-subject-hash-derivation~1]
    def test_completion_recomputes_and_compares(self):
        current = hasher(b"key-a")
        stored = row(binding=preauth_binding(ISSUER, "sub-1", current))
        assert preauth_subject_matches(stored, "sub-1", current) is True
        assert preauth_subject_matches(stored, "other-subject", current) is False

    # [utest->req~schema-auth-challenges-preauth-subject-hash-derivation~1]
    def test_the_raw_subject_is_never_a_column_on_this_table(self):
        assert_no_raw_subject_column()
        with pytest.raises(ChallengeError):
            assert_no_raw_subject_column(AUTH_CHALLENGE_COLUMNS | {"subject"})

    # [utest->req~schema-auth-challenges-no-key-version-recorded~1]
    def test_the_row_records_no_key_version(self):
        assert_no_key_version_column()
        with pytest.raises(ChallengeError):
            assert_no_key_version_column(AUTH_CHALLENGE_COLUMNS | {"subject_hash_key_version"})

    # [utest->req~schema-auth-challenges-no-key-version-recorded~1]
    def test_a_challenge_prepared_before_a_rotation_fails_its_identity_comparison(self):
        stored = row(binding=preauth_binding(ISSUER, "sub-1", hasher(b"old-key")))
        assert preauth_subject_matches(stored, "sub-1", hasher(b"new-key")) is False
        assert preauth_subject_matches(stored, "sub-1", hasher(b"old-key")) is True


class TestRowIdAndReplay:

    # [utest->req~schema-auth-challenges-id-internal-only~1]
    def test_the_completion_capability_is_the_handle_not_the_row_id(self):
        stored = row()
        assert completion_capability(stored) == "handle-1"
        assert completion_capability(stored) != str(stored.id)
        with pytest.raises(ChallengeError):
            completion_capability(row(challenge_id=str(stored.id), id=stored.id))

    # [utest->req~schema-auth-challenges-id-internal-only~1]
    def test_the_prepare_response_never_discloses_the_row_id(self):
        stored = row()
        assert_row_id_not_disclosed(PrepareResponse(challenge_id="handle-1", expires_at=EXPIRES),
                                    stored)
        leaking = PrepareResponse(challenge_id=f"handle-{stored.id}", expires_at=EXPIRES)
        with pytest.raises(ChallengeError):
            assert_row_id_not_disclosed(leaking, stored)

    # [utest->req~schema-auth-challenges-source-of-truth-replay~1]
    def test_the_stored_record_decides_whether_a_handle_may_still_be_completed(self):
        assert replay_authority("handle-1", row()) is ChallengeState.issued
        consumed = row(state=ChallengeState.consumed, claim_attempt_id=uuid4())
        assert replay_authority("handle-1", consumed) is ChallengeState.consumed

    # [utest->req~schema-auth-challenges-source-of-truth-replay~1]
    def test_a_handle_with_no_stored_record_completes_nothing(self):
        with pytest.raises(ChallengeError):
            replay_authority("handle-1", None)
        with pytest.raises(ChallengeError):
            replay_authority("some-other-handle", row())


class TestOutcomeAndRetention:

    # [utest->req~schema-auth-challenges-consumed-outcome-in-audit~1]
    def test_the_row_records_no_completion_outcome(self):
        assert assert_no_outcome_column() == CONSUMED_OUTCOME_LOG == "audit.auth_events"
        for column in ("result", "outcome", "auth_event_result"):
            with pytest.raises(ChallengeError):
                assert_no_outcome_column(AUTH_CHALLENGE_COLUMNS | {column})

    # [utest->req~schema-auth-challenges-consumed-outcome-in-audit~1]
    def test_a_consumed_row_carries_no_field_saying_which_outcome_it_was(self):
        consumed = row(state=ChallengeState.consumed, claim_attempt_id=uuid4())
        assert consumed.state is ChallengeState.consumed
        names = {field.name for field in fields(consumed)} | AUTH_CHALLENGE_COLUMNS
        assert names & OUTCOME_COLUMN_NAMES == set()

    # [utest->req~schema-auth-challenges-no-purge-indefinite-retention~1]
    def test_nothing_purges_the_table_and_retention_is_indefinite(self):
        assert CHALLENGE_PURGE_JOBS == frozenset()
        assert challenge_retention_deadline(row()) is None
        expired = row(expires_at=datetime(2020, 1, 1, tzinfo=UTC))
        assert challenge_retention_deadline(expired) is None

    # [utest->req~schema-auth-challenges-no-purge-indefinite-retention~1]
    def test_expiry_is_evaluated_only_by_the_claiming_conditional_update(self):
        assert EXPIRY_ENFORCEMENT_POINTS == {"claim_conditional_update"}
        assert_expiry_enforcement_point("claim_conditional_update")
        for point in ("purge_job", "recovery_scan", "consume_conditional_update", "read"):
            with pytest.raises(ChallengeError):
                assert_expiry_enforcement_point(point)
