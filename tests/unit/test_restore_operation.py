"""Restore's purpose, its common entry conditions, the two-phase split, audit placement per
phase, and the grant-mutation ordering that keeps the one-active-grant index satisfied."""

from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.audit import AttemptPhase, AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.external_identities import ExternalIdentityRow
from nativespeaker.api.auth.invariants import DevicePlatform, StoreProvider
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.proof_restore import VerifiedStoreProof
from nativespeaker.api.auth.restore import (
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
)
from nativespeaker.api.auth.restore_flow import (
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
)
from nativespeaker.api.auth.restore_operation import (
    ONE_ACTIVE_GRANT_INDEX,
    PROOF_AUTHORITATIVE_FOR,
    RESTORE_EXPIRY_REASON,
    RESTORE_PURPOSE,
    SERVER_DETERMINED_BRANCHES,
    RestoreGrantMutations,
    RestoreOrderingError,
    RestorePhase,
    assert_phase_work,
    audit_placement,
    entry_current_state_product_entitled,
    entry_destination,
    entry_proof_server_verified,
    entry_proof_supplied,
    entry_purchase_row_resolved_or_created,
    entry_subscription_identity_resolves,
    missing_row_is_not_a_rejection,
    ordering_binds,
    proof_authority,
    restore_entry_conditions,
    restore_purpose,
    two_server_determined_branches,
)
from nativespeaker.api.auth.restore_phases import (
    PreTransactionLedger,
    step_05_determine_branch,
    step_07_adoption_entitlement_short_circuit,
    step_08_live_store_state_verification,
)
from nativespeaker.api.models import SubscriptionStatus

DESTINATION = uuid7()
OTHER = uuid7()
EXTERNAL_ID = "2000000123456789"
TOKEN = "11111111-2222-3333-4444-555555555555"
APPLE_CHECKS = ("jws_certificate_chain", "bundle_id", "product_id", "environment")
VERIFIED = VerifiedTransaction(provider=StoreProvider.apple, external_id=EXTERNAL_ID,
                               carried_purchase_uuid=TOKEN)
PROOF_BODY = {"restore_proof": "signed.storekit.tx"}


def fake_verifier(provider: StoreProvider, artifact: str) -> VerifiedStoreProof:
    del artifact
    return VerifiedStoreProof(provider=provider, external_id=EXTERNAL_ID,
                              purchase_uuid=UUID(TOKEN))


def identity_rows(*, registered: bool = True) -> list[ExternalIdentityRow]:
    provider = IdentityProvider.google if registered else IdentityProvider.anonymous
    return [ExternalIdentityRow(id=uuid7(), user_id=DESTINATION, issuer="iss", subject="sub",
                                provider=provider,
                                provider_uid="google-uid" if registered else None)]


def context(user_id: UUID | None = DESTINATION) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer="iss", subject="sub",
                                   outcome=ResolutionOutcome.linked, user_id=user_id,
                                   external_identity_id=uuid7(),
                                   provider=IdentityProvider.google)


def subscription(*, user_id: UUID | None = None,
                 status: SubscriptionStatus = SubscriptionStatus.active,
                 bound: UUID | None = None) -> SubscriptionRow:
    return SubscriptionRow(subscription_id=uuid7(), provider=StoreProvider.apple,
                           external_id=EXTERNAL_ID, status=status, tier_id="gold",
                           user_id=user_id, restore_bound_user_id=bound)


def purchase(*, identity_value: str = TOKEN) -> PurchaseRow:
    return PurchaseRow(purchase_id=uuid7(), provider=StoreProvider.apple,
                       external_id=EXTERNAL_ID, identity_value=identity_value)


class TestPurpose:

    def test_entitlement_lands_on_the_current_authenticated_user(self):
        # [utest->req~restore-purpose-restore-paid-entitlement~1]
        assert restore_purpose(destination_user_id=DESTINATION) == RESTORE_PURPOSE
        with pytest.raises(RestoreContractError):
            restore_purpose(destination_user_id=DESTINATION, attaches_to=OTHER)

    def test_proof_is_authoritative_for_entitlement_only(self):
        # [utest->req~restore-purpose-proof-authoritative-for-entitlement-only~1]
        assert proof_authority() == PROOF_AUTHORITATIVE_FOR
        for overreach in ("app_account_ownership", "chats", "external_identities", "free_grants"):
            with pytest.raises(RestoreContractError):
                proof_authority(["subscription_entitlement", overreach])

    def test_two_branches_are_chosen_from_verified_server_state(self):
        # [utest->req~restore-purpose-two-server-determined-branches~1]
        assert SERVER_DETERMINED_BRANCHES == frozenset(RestoreBranch)
        same = two_server_determined_branches(
            subscription=CurrentSubscriptionState(subscription(user_id=DESTINATION)),
            destination_user_id=DESTINATION, destination_registered=True)
        assert same is RestoreBranch.same_account
        adoption = two_server_determined_branches(
            subscription=CurrentSubscriptionState(subscription(user_id=None)),
            destination_user_id=DESTINATION, destination_registered=True)
        assert adoption is RestoreBranch.adoption

    def test_a_different_linked_account_is_never_transferred(self):
        # [utest->req~restore-purpose-two-server-determined-branches~1]
        with pytest.raises(RestoreRejection) as refused:
            two_server_determined_branches(
                subscription=CurrentSubscriptionState(subscription(user_id=OTHER)),
                destination_user_id=DESTINATION, destination_registered=True)
        assert refused.value.result is AuthEventResult.store_transaction_already_linked

    def test_an_unregistered_destination_never_reaches_branch_selection(self):
        # [utest->req~restore-purpose-two-server-determined-branches~1]
        with pytest.raises(RestoreContractError):
            two_server_determined_branches(
                subscription=CurrentSubscriptionState(subscription(user_id=None)),
                destination_user_id=DESTINATION, destination_registered=False)

    def test_the_owner_must_agree_with_the_subscription_backed_grant(self):
        # [utest->req~restore-purpose-two-server-determined-branches~1]
        with pytest.raises(RestoreRejection) as refused:
            two_server_determined_branches(
                subscription=CurrentSubscriptionState(subscription(user_id=DESTINATION)),
                destination_user_id=DESTINATION, destination_registered=True,
                grant_user_id=OTHER)
        assert refused.value.result is AuthEventResult.restore_subscription_grant_owner_mismatch


class TestEntryConditions:

    def test_the_destination_is_the_verified_active_registered_user(self):
        # [utest->req~restore-entry-verified-id-token-active-registered-user~1]
        assert entry_destination(context(), identity_rows=identity_rows()) == DESTINATION

    def test_an_anonymous_destination_is_rejected(self):
        # [utest->req~restore-entry-verified-id-token-active-registered-user~1]
        with pytest.raises(RestoreRejection) as refused:
            entry_destination(context(), identity_rows=identity_rows(registered=False))
        assert refused.value.result is AuthEventResult.restore_destination_anonymous

    def test_an_inactive_destination_is_rejected(self):
        # [utest->req~restore-entry-verified-id-token-active-registered-user~1]
        with pytest.raises(RestoreRejection) as refused:
            entry_destination(context(), identity_rows=identity_rows(),
                              destination_active=False)
        assert refused.value.result is AuthEventResult.blocked_user

    def test_restore_logic_never_runs_before_the_barrier(self):
        # [utest->req~restore-entry-verified-id-token-active-registered-user~1]
        with pytest.raises(RestoreContractError):
            entry_destination(context(), identity_rows=identity_rows(), barrier_admitted=False)

    def test_restore_proof_must_be_supplied(self):
        # [utest->req~restore-entry-proof-supplied~1]
        assert entry_proof_supplied(DevicePlatform.ios, PROOF_BODY) == "signed.storekit.tx"
        for body in ({}, {"restore_proof": ""}, {"restore_proof": "   "}, None):
            with pytest.raises(RestoreRejection) as refused:
                entry_proof_supplied(DevicePlatform.ios, body)
            assert refused.value.result is AuthEventResult.invalid_restore_proof

    def test_the_proof_is_server_verified_including_the_signed_transaction(self):
        # [utest->req~restore-entry-proof-server-verified~1]
        verified = entry_proof_server_verified(DevicePlatform.ios, PROOF_BODY, fake_verifier,
                                               performed_checks=APPLE_CHECKS)
        assert verified.external_id == EXTERNAL_ID
        # An incomplete store-side check set is not a server-verified proof.
        with pytest.raises(Exception):
            entry_proof_server_verified(DevicePlatform.ios, PROOF_BODY, fake_verifier,
                                        performed_checks=("bundle_id",))

    def test_the_subscription_identity_resolves_or_is_created(self):
        # [utest->req~restore-entry-subscription-identity-resolves~1]
        row = subscription(user_id=DESTINATION)
        state, creating = entry_subscription_identity_resolves([row], VERIFIED)
        assert state.row is row and creating is False
        empty, creating = entry_subscription_identity_resolves([], VERIFIED)
        assert empty.row is None and creating is True

    def test_the_current_state_must_be_product_entitled(self):
        # [utest->req~restore-entry-current-state-product-entitled~1]
        entitled = CurrentSubscriptionState(subscription(status=SubscriptionStatus.grace_period))
        assert entry_current_state_product_entitled(entitled) is SubscriptionStatus.grace_period
        stale = CurrentSubscriptionState(subscription(status=SubscriptionStatus.expired))
        with pytest.raises(RestoreRejection) as refused:
            entry_current_state_product_entitled(stale)
        assert refused.value.result is AuthEventResult.restore_subscription_not_entitled

    def test_the_creation_path_takes_its_entitlement_from_live_verification(self):
        # [utest->req~restore-entry-current-state-product-entitled~1]
        missing = CurrentSubscriptionState(None)
        assert entry_current_state_product_entitled(
            missing, live_verified_status=SubscriptionStatus.active) is SubscriptionStatus.active
        with pytest.raises(RestoreRejection):
            entry_current_state_product_entitled(
                missing, live_verified_status=SubscriptionStatus.revoked)

    def test_the_purchase_row_resolves_or_is_created(self):
        # [utest->req~restore-entry-purchase-row-resolved-or-created~1]
        row, value = entry_purchase_row_resolved_or_created([purchase()], VERIFIED)
        assert row is not None and value == TOKEN
        created, generated = entry_purchase_row_resolved_or_created([], VERIFIED)
        assert created is None and generated == TOKEN

    def test_a_carried_uuid_that_differs_from_the_recorded_one_rejects(self):
        # [utest->req~restore-entry-purchase-row-resolved-or-created~1]
        with pytest.raises(RestoreRejection) as refused:
            entry_purchase_row_resolved_or_created(
                [purchase(identity_value="99999999-2222-3333-4444-555555555555")], VERIFIED)
        assert refused.value.result is AuthEventResult.restore_purchase_uuid_mismatch

    def test_the_entry_conjunction_resolves_the_whole_attempt(self):
        # [utest->req~restore-entry-verified-id-token-active-registered-user~1]
        # [utest->req~restore-entry-proof-supplied~1]
        # [utest->req~restore-entry-proof-server-verified~1]
        entry = restore_entry_conditions(context(), identity_rows=identity_rows(),
                                         platform=DevicePlatform.ios, body=PROOF_BODY,
                                         verifier=fake_verifier,
                                         performed_checks=APPLE_CHECKS,
                                         subscriptions=[subscription(user_id=DESTINATION)],
                                         purchases=[purchase()])
        assert entry.destination_user_id == DESTINATION
        assert entry.adoption_with_creation is False
        assert entry.purchase_uuid == TOKEN


class TestTwoPhaseSplit:

    def test_each_phase_does_only_its_own_work(self):
        # [utest->req~restore-two-phase-pre-transaction-and-locked~1]
        assert assert_phase_work(RestorePhase.pre_transaction,
                                 ["verify_restore_proof", "read_local_state"]) == (
            "verify_restore_proof", "read_local_state")
        with pytest.raises(RestoreContractError):
            assert_phase_work(RestorePhase.pre_transaction, ["restore_mutation"])

    def test_the_locked_phase_makes_no_provider_call_and_no_retry(self):
        # [utest->req~restore-two-phase-pre-transaction-and-locked~1]
        for forbidden in ("provider_call", "live_store_state_verification"):
            with pytest.raises(RestoreContractError):
                assert_phase_work(RestorePhase.locked_mutation, [forbidden])

    def test_only_adoption_makes_the_pre_transaction_provider_call(self):
        # [utest->req~restore-two-phase-pre-transaction-and-locked~1]
        assert assert_phase_work(RestorePhase.pre_transaction, ["provider_call"],
                                 branch=RestoreBranch.adoption) == ("provider_call",)
        with pytest.raises(RestoreContractError):
            assert_phase_work(RestorePhase.pre_transaction, ["provider_call"],
                              branch=RestoreBranch.same_account)

    def test_the_barrier_admits_the_request_before_phase_one(self):
        # [utest->req~restore-two-phase-pre-transaction-and-locked~1]
        with pytest.raises(RestoreContractError):
            assert_phase_work(RestorePhase.pre_transaction, ["read_local_state"],
                              barrier_admitted=False)


class TestAuditPlacementPerPhase:

    def test_a_pre_transaction_rejection_writes_its_row_in_its_own_transaction(self):
        # [utest->req~restore-audit-placement-per-phase~1]
        placement = audit_placement(phase=RestorePhase.pre_transaction,
                                    result=AuthEventResult.restore_store_state_unverified)
        assert placement.own_transaction is True
        assert placement.beside_mutation is False
        assert placement.attempt_phase is AttemptPhase.business

    def test_a_pre_transaction_rejection_performs_no_restore_mutation(self):
        # [utest->req~restore-audit-placement-per-phase~1]
        with pytest.raises(RestoreContractError):
            audit_placement(phase=RestorePhase.pre_transaction,
                            result=AuthEventResult.invalid_restore_proof,
                            mutation_performed=["access_grants_write"])

    def test_a_locked_phase_outcome_writes_its_row_beside_the_mutation(self):
        # [utest->req~restore-audit-placement-per-phase~1]
        placement = audit_placement(phase=RestorePhase.locked_mutation,
                                    result=AuthEventResult.succeeded,
                                    mutation_performed=["subscriptions_owner_change",
                                                        "access_grants_write"])
        assert placement.beside_mutation is True
        assert placement.own_transaction is False
        assert placement.attempt_phase is AttemptPhase.success

    def test_a_locked_phase_rejection_takes_the_business_phase(self):
        # [utest->req~restore-audit-placement-per-phase~1]
        placement = audit_placement(phase=RestorePhase.locked_mutation,
                                    result=AuthEventResult.restore_branch_inconsistent)
        assert placement.attempt_phase is AttemptPhase.business

    def test_a_locked_phase_result_is_not_a_pre_transaction_rejection(self):
        # [utest->req~restore-audit-placement-per-phase~1]
        with pytest.raises(RestoreContractError):
            audit_placement(phase=RestorePhase.pre_transaction,
                            result=AuthEventResult.restore_branch_inconsistent)

    def test_every_pre_transaction_rejection_is_placed_in_its_own_transaction(self):
        """The five results the placement rule names are examples, not the whole set: every
        rejection the entry conditions and steps 1 to 8 produce writes its row in the
        pre-transaction rejection transaction."""
        # [utest->req~restore-audit-placement-per-phase~1]
        raised: set[AuthEventResult] = set()

        def collect(call):
            with pytest.raises(RestoreRejection) as refused:
                call()
            raised.add(refused.value.result)

        # The entry conditions: an anonymous destination, and a destination that is not active.
        collect(lambda: entry_destination(context(), identity_rows=identity_rows(registered=False)))
        collect(lambda: entry_destination(context(), identity_rows=identity_rows(),
                                          destination_active=False))
        collect(lambda: entry_proof_supplied(DevicePlatform.ios, {}))
        # Step 5: a store transaction linked to a different account, and one whose linked source
        # account is inactive.
        for source_user_active in (True, False):
            collect(lambda active=source_user_active: step_05_determine_branch(
                CurrentSubscriptionState(subscription(user_id=OTHER)),
                destination_user_id=DESTINATION, ledger=PreTransactionLedger(),
                source_user_active=active))
        # Step 7: an obviously non-entitled current state, short-circuited before any provider call.
        collect(lambda: step_07_adoption_entitlement_short_circuit(
            CurrentSubscriptionState(subscription(status=SubscriptionStatus.expired)),
            branch=RestoreBranch.adoption, ledger=PreTransactionLedger()))
        # Step 8: a live store state that is not entitlement.
        collect(lambda: step_08_live_store_state_verification(
            VERIFIED, CurrentSubscriptionState(subscription(user_id=None)),
            branch=RestoreBranch.adoption, ledger=PreTransactionLedger(),
            lookup=lambda provider, external_id: "expired", now=datetime.now(UTC)))

        assert raised >= {AuthEventResult.restore_destination_anonymous,
                          AuthEventResult.blocked_user,
                          AuthEventResult.store_transaction_already_linked,
                          AuthEventResult.restore_source_user_inactive,
                          AuthEventResult.invalid_restore_proof,
                          AuthEventResult.restore_subscription_not_entitled,
                          AuthEventResult.restore_store_state_unverified}
        for result in raised:
            placement = audit_placement(phase=RestorePhase.pre_transaction, result=result)
            assert placement.own_transaction is True
            assert placement.beside_mutation is False

    def test_a_missing_row_is_the_creation_path_not_a_rejection(self):
        # [utest->req~restore-audit-placement-per-phase~1]
        assert missing_row_is_not_a_rejection("missing_canonical_subscription_row")
        assert missing_row_is_not_a_rejection("missing_store_purchase_row")
        assert not missing_row_is_not_a_rejection("invalid_restore_proof")


class TestGrantMutationOrdering:

    def test_validation_completes_before_any_grant_mutation(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        mutations = RestoreGrantMutations()
        with pytest.raises(RestoreOrderingError):
            mutations.activate(uuid7())
        with pytest.raises(RestoreOrderingError):
            mutations.expire(uuid7(), same_subscription=True)

    def test_every_stale_row_of_the_same_subscription_is_expired_first(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        stale, fresh = uuid7(), uuid7()
        mutations = RestoreGrantMutations()
        mutations.validate()
        with pytest.raises(RestoreOrderingError):
            mutations.activate(fresh, stale_grant_ids=[stale])
        mutations.expire(stale, same_subscription=True)
        mutations.activate(fresh, stale_grant_ids=[stale])
        assert mutations.statements == [f"expire_grant:{RESTORE_EXPIRY_REASON}",
                                        "activate_subscription_grant"]

    def test_no_expiry_follows_the_activation(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        mutations = RestoreGrantMutations()
        mutations.validate()
        mutations.activate(uuid7())
        with pytest.raises(RestoreOrderingError):
            mutations.expire(uuid7(), same_subscription=True)

    def test_a_different_active_grant_is_never_expired_to_make_room(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        mutations = RestoreGrantMutations()
        mutations.validate()
        with pytest.raises(RestoreRejection) as refused:
            mutations.expire(uuid7(), same_subscription=False)
        assert refused.value.result is AuthEventResult.restore_destination_already_entitled
        with pytest.raises(RestoreRejection):
            mutations.expire(uuid7(), same_subscription=True,
                             destination_holds_different_active_grant=True)

    def test_each_expiry_carries_a_reason_code(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        mutations = RestoreGrantMutations()
        mutations.validate()
        with pytest.raises(RestoreOrderingError):
            mutations.expire(uuid7(), same_subscription=True, reason="")

    def test_a_failed_transaction_rolls_back_the_earlier_expiry(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        stale = uuid7()
        mutations = RestoreGrantMutations()
        mutations.validate()
        mutations.expire(stale, same_subscription=True)
        with pytest.raises(RestoreOrderingError):
            mutations.commit(ownership_writes_succeeded=False)
        assert mutations.rolled_back is True
        assert mutations.expired == []
        assert mutations.committed is False

    def test_the_index_is_plain_and_binds_restore_alone(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        assert ONE_ACTIVE_GRANT_INDEX == "ix_access_grants_one_active_per_user"
        assert ordering_binds("restore_subscription")
        for other in ("upgrade_anonymous_to_registered", "grant_issuance", "manual_issuance"):
            assert not ordering_binds(other)

    def test_a_grant_free_destination_needs_no_expiry_at_all(self):
        # [utest->req~restore-grant-mutation-ordering~1]
        grant = uuid7()
        mutations = RestoreGrantMutations()
        mutations.validate()
        mutations.activate(grant)
        mutations.commit()
        assert mutations.expired == []
        assert mutations.activated == grant
        assert mutations.committed is True
