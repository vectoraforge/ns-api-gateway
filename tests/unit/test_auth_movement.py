"""The shared account-movement audit contract: one row per movement attempt, the minimum
`details` record it carries, destination anchoring, and the restore ownership rules."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.audit import (
    AttemptPhase,
    AuditAlreadyWrittenError,
    AuditRowError,
    AuthActor,
    AuthAttempt,
    AuthEventResult,
    auth_event_row,
    resolved_actor,
    terminal_event,
)
from nativespeaker.api.auth.movement import (
    MOVEMENT_MINIMUM_DETAIL_KEYS,
    MovementClassification,
    MovementContext,
    MovementError,
    MovementKind,
    assert_destination_anchored,
    assert_movement_details_minimum,
    movement_audit_details,
    movement_event,
    movement_kind_of,
    record_movement_attempt,
    restore_branch,
    restore_movement_context,
    settled_subscription_owner,
    upgrade_movement_context,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from unit.test_auth_barrier import FakeSession, RecordingSink, make_writer

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
ISSUER = "https://securetoken.google.com/test-project"
SUBJECT_HASH = bytes(range(32))

USER = uuid7()
OTHER_USER = uuid7()
IDENTITY = uuid7()
CHALLENGE_ROW = uuid7()


def actor(provider: IdentityProvider = IdentityProvider.google) -> AuthActor:
    return resolved_actor(ISSUER, SUBJECT_HASH, 1, stored_provider=provider)


def restore_context(**overrides: Any) -> MovementContext:
    fields: dict[str, Any] = {
        "result": AuthEventResult.succeeded,
        "occurred_at": NOW,
        "destination_user_id": USER,
        "destination_external_identity_id": IDENTITY,
        "classification": MovementClassification.adoption,
        "subscription_id": uuid7(),
        "store_purchase_id": uuid7(),
        "access_grant_id": uuid7(),
        "proof_fingerprints": ("sha256:abc",),
        "store_state_verification": "verified_active",
    }
    fields.update(overrides)
    return restore_movement_context(**fields)


def upgrade_context(**overrides: Any) -> MovementContext:
    fields: dict[str, Any] = {
        "result": AuthEventResult.succeeded,
        "occurred_at": NOW,
        "user_id": USER,
        "external_identity_id": IDENTITY,
        "challenge_row_id": CHALLENGE_ROW,
    }
    fields.update(overrides)
    return upgrade_movement_context(**fields)


def flat(details: dict[str, Any]) -> dict[str, Any]:
    """Every detail key in one mapping, whichever section it landed in."""
    merged: dict[str, Any] = {}
    for section in details.values():
        if isinstance(section, dict):
            merged.update(section)
    return merged


class TestSingleAuditRow:
    # [utest->req~shared-movement-single-audit-row~1]
    async def test_a_movement_attempt_is_one_row_and_a_second_is_refused(self):
        sink = RecordingSink()
        writer = make_writer(sink=sink)
        attempt = AuthAttempt("POST", "/auth/restore-subscription")
        event = movement_event(AttemptPhase.success, restore_context(), actor=actor())
        session = FakeSession()

        await record_movement_attempt(writer, attempt, event, session=session)
        assert [row["operation"] for row in sink.rows] == [AuthOperation.restore_subscription]

        with pytest.raises(AuditAlreadyWrittenError):
            await record_movement_attempt(writer, attempt, event, session=session)
        assert len(sink.rows) == 1

    # [utest->req~shared-movement-single-audit-row~1]
    async def test_a_rejected_movement_attempt_is_recorded_as_that_one_row(self):
        sink = RecordingSink()
        writer = make_writer(sink=sink)
        attempt = AuthAttempt("POST", "/auth/upgrade-anonymous")
        context = upgrade_context(result=AuthEventResult.provider_transition_not_allowed)
        event = movement_event(AttemptPhase.business, context, actor=actor())

        returned = await record_movement_attempt(writer, attempt, event,
                                                 error=RuntimeError("rejected"))
        assert isinstance(returned, RuntimeError)
        assert len(sink.rows) == 1
        assert sink.rows[0]["result"] is AuthEventResult.provider_transition_not_allowed

    # [utest->req~shared-movement-single-audit-row~1]
    async def test_only_the_two_movement_operations_use_the_movement_path(self):
        writer = make_writer()
        attempt = AuthAttempt("POST", "/auth/sync")
        event = movement_event(AttemptPhase.success, restore_context(), actor=actor())
        with pytest.raises(MovementError):
            await record_movement_attempt(writer, attempt, event, session=FakeSession())


class TestDetailsMinimum:
    # [utest->req~shared-movement-details-minimum~1]
    def test_every_minimum_key_is_recorded(self):
        details = movement_audit_details(restore_context())
        present = set(flat(details))
        assert set(MOVEMENT_MINIMUM_DETAIL_KEYS) <= present

    # [utest->req~shared-movement-details-minimum~1]
    @pytest.mark.parametrize("key", MOVEMENT_MINIMUM_DETAIL_KEYS)
    def test_a_missing_minimum_key_fails_closed(self, key):
        details = movement_audit_details(restore_context())
        for section in details.values():
            if isinstance(section, dict):
                section.pop(key, None)
        with pytest.raises(MovementError):
            assert_movement_details_minimum(details)

    # [utest->req~shared-movement-detail-operation-kind~1]
    def test_the_operation_and_movement_kind_are_recorded(self):
        assert movement_kind_of(AuthOperation.restore_subscription) \
            is MovementKind.subscription_restore
        assert movement_kind_of(AuthOperation.upgrade_anonymous_to_registered) \
            is MovementKind.identity_upgrade
        with pytest.raises(MovementError):
            movement_kind_of(AuthOperation.sync)

        recorded = flat(movement_audit_details(upgrade_context()))
        assert recorded["operation"] == "upgrade_anonymous_to_registered"
        assert recorded["movement_kind"] == "identity_upgrade"

    # [utest->req~shared-movement-detail-result-code~1]
    def test_the_result_code_is_recorded_on_success_and_rejection(self):
        succeeded = flat(movement_audit_details(restore_context()))
        assert succeeded["result"] == "succeeded"
        rejected = flat(movement_audit_details(restore_context(
            result=AuthEventResult.restore_store_state_unverified,
            classification=MovementClassification.unclassified)))
        assert rejected["result"] == "restore_store_state_unverified"

    # [utest->req~shared-movement-detail-source-context~1]
    def test_the_source_user_and_identity_context_are_recorded(self):
        same_account = flat(movement_audit_details(restore_context(
            classification=MovementClassification.same_account, source_user_id=USER)))
        assert same_account["source_user_id"] == USER
        assert "source_external_identity_id" in same_account
        # An adoption has no source user at all, and never claims one.
        assert flat(movement_audit_details(restore_context()))["source_user_id"] is None
        with pytest.raises(MovementError):
            restore_context(source_user_id=OTHER_USER)

    # [utest->req~shared-movement-detail-destination-context~1]
    def test_the_destination_user_and_identity_context_are_recorded(self):
        recorded = flat(movement_audit_details(restore_context()))
        assert recorded["destination_user_id"] == USER
        assert recorded["destination_external_identity_id"] == IDENTITY

    # [utest->req~shared-movement-detail-challenge-row-id~1]
    def test_the_challenge_row_id_is_recorded_and_the_public_handle_is_not(self):
        recorded = flat(movement_audit_details(upgrade_context()))
        assert recorded["challenge_row_id"] == CHALLENGE_ROW
        assert "challenge_id" not in recorded
        # Restore holds no challenge, so the field is NULL rather than absent.
        assert flat(movement_audit_details(restore_context()))["challenge_row_id"] is None
        with pytest.raises(MovementError):
            movement_audit_details(upgrade_context(challenge_row_id="ZmFrZS1oYW5kbGUtdmFsdWU"))

    # [utest->req~shared-movement-detail-touched-rows~1]
    def test_the_touched_subscription_purchase_and_grant_rows_are_recorded(self):
        subscription, purchase, grant = uuid7(), uuid7(), uuid7()
        recorded = flat(movement_audit_details(restore_context(subscription_id=subscription,
                                                              store_purchase_id=purchase,
                                                              access_grant_id=grant)))
        assert recorded["subscription_id"] == subscription
        assert recorded["store_purchase_id"] == purchase
        assert recorded["access_grant_id"] == grant

    # [utest->req~shared-movement-detail-proof-fingerprints~1]
    def test_proof_fingerprints_are_recorded_and_raw_proof_is_not(self):
        recorded = flat(movement_audit_details(
            restore_context(proof_fingerprints=("sha256:aaa", "sha256:bbb"))))
        assert recorded["proof_fingerprints"] == ["sha256:aaa", "sha256:bbb"]
        # The redaction pass keeps the fingerprints and drops any raw proof that rides along.
        event = movement_event(AttemptPhase.success, restore_context(),
                               actor=actor(), details={"verification": {"restore_proof": "raw"}})
        row = auth_event_row(event, created_at=NOW)
        assert row["details"]["verification"]["restore_proof"] == "[redacted]"
        assert row["details"]["verification"]["proof_fingerprints"] == ["sha256:abc"]

    # [utest->req~shared-movement-detail-timestamp~1]
    def test_the_attempt_timestamp_is_recorded(self):
        recorded = flat(movement_audit_details(restore_context(occurred_at=NOW)))
        assert recorded["occurred_at"] == NOW.isoformat()


class TestDestinationAnchoring:
    # [utest->req~shared-movement-destination-anchoring~1]
    def test_an_upgrade_is_anchored_on_the_same_resolved_identity_before_and_after(self):
        context = upgrade_context()
        assert_destination_anchored(context)
        recorded = flat(movement_audit_details(context))
        assert recorded["source_external_identity_id"] == IDENTITY
        assert recorded["destination_external_identity_id"] == IDENTITY

    # [utest->req~shared-movement-destination-anchoring~1]
    def test_an_upgrade_without_a_resolved_destination_identity_is_refused(self):
        with pytest.raises(MovementError):
            upgrade_context(external_identity_id=None)
        unanchored = MovementContext(operation=AuthOperation.upgrade_anonymous_to_registered,
                                     result=AuthEventResult.succeeded,
                                     classification=MovementClassification.upgrade,
                                     occurred_at=NOW,
                                     source_user_id=USER,
                                     source_external_identity_id=IDENTITY,
                                     destination_user_id=USER,
                                     destination_external_identity_id=uuid7())
        with pytest.raises(MovementError):
            assert_destination_anchored(unanchored)

    # [utest->req~shared-movement-destination-anchoring~1]
    # [utest->req~shared-movement-detail-destination-context~1]
    def test_a_restore_is_anchored_on_its_own_destination_identity(self):
        recorded = flat(movement_audit_details(restore_context()))
        assert recorded["destination_external_identity_id"] == IDENTITY
        # A restore is not an upgrade, so the same-row anchoring rule does not bind it: its
        # destination is its own resolved identity, not the source row.
        assert_destination_anchored(restore_context(source_user_id=None))

    # [utest->req~shared-movement-destination-anchoring~1]
    # [utest->req~shared-movement-detail-destination-context~1]
    def test_a_successful_restore_with_no_resolved_destination_is_refused(self):
        # A restore is a linked flow too: its destination is a registered user's resolved
        # identity, so a success that resolved neither is not a row this contract will build.
        no_identity = restore_movement_context(
            result=AuthEventResult.succeeded, occurred_at=NOW,
            classification=MovementClassification.adoption,
            destination_user_id=USER, destination_external_identity_id=None)
        with pytest.raises(MovementError):
            assert_destination_anchored(no_identity)
        with pytest.raises(MovementError):
            movement_event(AttemptPhase.success, no_identity, actor=actor())

        no_user = restore_movement_context(
            result=AuthEventResult.succeeded, occurred_at=NOW,
            classification=MovementClassification.adoption,
            destination_user_id=None, destination_external_identity_id=IDENTITY)
        with pytest.raises(MovementError):
            assert_destination_anchored(no_user)

        # A rejected restore resolves nothing and is still recorded, classification included.
        unresolved = restore_movement_context(
            result=AuthEventResult.invalid_restore_proof, occurred_at=NOW,
            destination_user_id=None, destination_external_identity_id=None)
        row = auth_event_row(movement_event(AttemptPhase.business, unresolved, actor=actor()),
                             created_at=NOW)
        assert flat(row["details"])["movement_classification"] == "unclassified"


class TestUpgradePreservesUser:
    # [utest->req~shared-upgrade-preserves-user~1]
    def test_source_and_destination_are_the_same_user_and_identity_row(self):
        context = upgrade_context()
        assert context.source_user_id == context.destination_user_id == USER
        assert context.source_external_identity_id == context.destination_external_identity_id

    # [utest->req~shared-upgrade-preserves-user~1]
    def test_no_identity_is_retired_and_no_identity_row_is_created(self):
        with pytest.raises(MovementError):
            upgrade_context(retired_identity_ids=(IDENTITY,))
        with pytest.raises(MovementError):
            upgrade_context(created_identity_ids=(uuid7(),))

    # [utest->req~shared-upgrade-preserves-user~1]
    def test_the_flip_keeps_the_same_issuer_and_subject(self):
        upgrade_context(issuer_before=ISSUER, issuer_after=ISSUER,
                        subject_before="uid-1", subject_after="uid-1")
        with pytest.raises(MovementError):
            upgrade_context(subject_before="uid-1", subject_after="uid-2")
        with pytest.raises(MovementError):
            upgrade_context(issuer_before=ISSUER, issuer_after="https://elsewhere.example")


class TestUpgradeMovementContextRequired:
    # [utest->req~shared-upgrade-movement-context-required~1]
    def test_a_rejected_upgrade_still_carries_the_whole_movement_context(self):
        context = upgrade_context(result=AuthEventResult.challenge_expired)
        row = auth_event_row(movement_event(AttemptPhase.business, context, actor=actor()),
                             created_at=NOW)
        recorded = flat(row["details"])
        assert set(MOVEMENT_MINIMUM_DETAIL_KEYS) <= set(recorded)
        assert recorded["movement_classification"] == "upgrade"

    # [utest->req~shared-upgrade-movement-context-required~1]
    def test_an_upgrade_row_without_movement_context_is_refused(self):
        bare = terminal_event(AttemptPhase.business, AuthEventResult.challenge_expired,
                              operation=AuthOperation.upgrade_anonymous_to_registered,
                              actor=actor(), details={"route": "/auth/upgrade-anonymous"})
        with pytest.raises(AuditRowError):
            auth_event_row(bare, created_at=NOW)


class TestRestoreMovementClassification:
    # [utest->req~shared-restore-movement-classification~1]
    def test_a_known_branch_records_same_account_or_adoption(self):
        assert restore_branch(None, USER) == (MovementClassification.adoption, None)
        assert restore_branch(USER, USER) == (MovementClassification.same_account, None)

    # [utest->req~shared-restore-movement-classification~1]
    def test_a_transaction_linked_elsewhere_is_rejected_and_never_transferred(self):
        classification, result = restore_branch(OTHER_USER, USER)
        assert classification is MovementClassification.unclassified
        assert result is AuthEventResult.store_transaction_already_linked
        recorded = flat(movement_audit_details(restore_context(
            result=AuthEventResult.store_transaction_already_linked,
            classification=classification)))
        assert recorded["movement_classification"] == "unclassified"
        # It must never be recorded as a completed movement of either classified kind.
        with pytest.raises(MovementError):
            restore_context(result=AuthEventResult.store_transaction_already_linked,
                            classification=MovementClassification.same_account)

    # [utest->req~shared-restore-movement-classification~1]
    def test_an_attempt_that_never_reached_the_branch_records_unclassified(self):
        context = restore_movement_context(result=AuthEventResult.invalid_restore_proof,
                                           occurred_at=NOW,
                                           destination_user_id=USER,
                                           destination_external_identity_id=IDENTITY)
        assert context.classification is MovementClassification.unclassified
        assert flat(movement_audit_details(context))["movement_classification"] == "unclassified"

    # [utest->req~shared-restore-movement-classification~1]
    def test_an_upgrade_classification_is_not_a_restore_classification(self):
        with pytest.raises(MovementError):
            restore_context(classification=MovementClassification.upgrade)


class TestRestoreOwnershipImmutable:
    # [utest->req~shared-restore-ownership-immutable~1]
    def test_only_adoption_of_an_unclaimed_subscription_establishes_ownership(self):
        adopted = settled_subscription_owner(restore_context(), current_owner_id=None)
        assert adopted == USER

    # [utest->req~shared-restore-ownership-immutable~1]
    def test_an_already_linked_subscription_is_never_adopted_again(self):
        with pytest.raises(MovementError):
            settled_subscription_owner(restore_context(), current_owner_id=OTHER_USER)

    # [utest->req~shared-restore-ownership-immutable~1]
    @pytest.mark.parametrize(("result", "classification"), [
        (AuthEventResult.succeeded, MovementClassification.same_account),
        (AuthEventResult.store_transaction_already_linked, MovementClassification.unclassified),
        (AuthEventResult.restore_branch_inconsistent, MovementClassification.unclassified),
        (AuthEventResult.invalid_restore_proof, MovementClassification.unclassified),
    ])
    def test_no_other_outcome_changes_the_owner(self, result: AuthEventResult,
                                                classification: MovementClassification):
        context = restore_context(result=result, classification=classification,
                                  source_user_id=USER if classification
                                  is MovementClassification.same_account else None)
        assert settled_subscription_owner(context, current_owner_id=OTHER_USER) == OTHER_USER
        assert settled_subscription_owner(context, current_owner_id=None) is None

    # [utest->req~shared-restore-ownership-immutable~1]
    def test_a_failed_adoption_establishes_nothing(self):
        failed = restore_context(result=AuthEventResult.restore_store_state_unverified,
                                 classification=MovementClassification.unclassified)
        assert settled_subscription_owner(failed, current_owner_id=None) is None

    # [utest->req~shared-restore-ownership-immutable~1]
    def test_only_restore_settles_subscription_ownership(self):
        with pytest.raises(MovementError):
            settled_subscription_owner(upgrade_context(), current_owner_id=None)


def test_movement_context_ids_are_uuids() -> None:
    """A guard on the fixtures themselves: the recorded ids are internal row ids."""
    assert isinstance(USER, UUID) and isinstance(IDENTITY, UUID)
