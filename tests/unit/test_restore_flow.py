"""The restore flow's six steps, its branching and reject policy, and the authorization
conjunction."""

from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.invariants import DevicePlatform, StoreProvider
from nativespeaker.api.auth.proof_restore import InvalidRestoreProof, VerifiedStoreProof
from nativespeaker.api.auth.restore import RestoreBranch, RestoreContractError, RestoreRejection
from nativespeaker.api.auth.restore_flow import (
    PURCHASE_ROW_INSERT_ONCE,
    PURCHASE_ROW_MUTATIONS,
    RESOLUTION_KEY,
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
    apply_lifetime_binding,
    assert_carried_uuid_matches,
    assert_product_entitled,
    assert_purchase_row_immutable,
    authorize_restore,
    internal_purchase_uuid,
    missing_purchase_row_path,
    missing_subscription_row_path,
    resolve_canonical_subscription,
    resolve_purchase_row,
    select_branch,
    verify_signed_transaction,
)
from nativespeaker.api.auth.restore_proof_policy import BindingOutcome
from nativespeaker.api.models import SubscriptionStatus

DESTINATION = uuid7()
OTHER = uuid7()
EXTERNAL_ID = "2000000123456789"
TOKEN = "11111111-2222-3333-4444-555555555555"
APPLE_CHECKS = ("jws_certificate_chain", "bundle_id", "product_id", "environment")
VERIFIED = VerifiedTransaction(provider=StoreProvider.apple, external_id=EXTERNAL_ID,
                               carried_purchase_uuid=TOKEN)


def fake_verifier(provider: StoreProvider, artifact: str) -> VerifiedStoreProof:
    del artifact
    return VerifiedStoreProof(provider=provider, external_id=EXTERNAL_ID, purchase_uuid=uuid7())


def subscription(*, user_id: UUID | None = None,
                 status: SubscriptionStatus = SubscriptionStatus.active,
                 bound: UUID | None = None,
                 external_id: str = EXTERNAL_ID) -> SubscriptionRow:
    return SubscriptionRow(subscription_id=uuid7(), provider=StoreProvider.apple,
                           external_id=external_id, status=status, tier_id="gold",
                           user_id=user_id, restore_bound_user_id=bound)


def purchase(*, identity_value: str = TOKEN,
             purchase_user_id: UUID | None = None,
             external_id: str = EXTERNAL_ID) -> PurchaseRow:
    return PurchaseRow(purchase_id=uuid7(), provider=StoreProvider.apple,
                       external_id=external_id, identity_value=identity_value,
                       purchase_user_id=purchase_user_id)


class TestStep01VerifySignedTransaction:

    def test_the_backend_verifies_the_artifact_server_side(self):
        # [utest->req~restore-flow-01-verify-signed-transaction~1]
        verified = verify_signed_transaction(DevicePlatform.ios,
                                            {"restore_proof": "signed.storekit.tx",
                                             "carried_purchase_uuid": TOKEN},
                                            fake_verifier,
                                            performed_checks=APPLE_CHECKS)
        assert verified.provider is StoreProvider.apple
        assert verified.external_id == EXTERNAL_ID
        assert verified.carried_purchase_uuid == TOKEN

    def test_an_unverifiable_artifact_yields_nothing(self):
        # [utest->req~restore-flow-01-verify-signed-transaction~1]
        def empty(provider: StoreProvider, artifact: str) -> VerifiedStoreProof:
            del artifact
            return VerifiedStoreProof(provider=provider, external_id="", purchase_uuid=uuid7())

        with pytest.raises(InvalidRestoreProof):
            verify_signed_transaction(DevicePlatform.ios, {"restore_proof": "x"}, empty,
                                     performed_checks=APPLE_CHECKS)


class TestStep02ResolveCanonicalSubscription:

    def test_resolution_is_by_provider_and_external_id(self):
        # [utest->req~restore-flow-02-resolve-canonical-subscription~1]
        assert RESOLUTION_KEY == ("provider", "external_id")
        row = subscription(user_id=DESTINATION)
        state = resolve_canonical_subscription([subscription(external_id="other"), row], VERIFIED)
        assert state.row is row

    def test_the_row_supplies_the_current_owner_status_and_tier(self):
        # [utest->req~restore-flow-02-resolve-canonical-subscription~1]
        state = resolve_canonical_subscription([subscription(user_id=DESTINATION)], VERIFIED)
        assert state.user_id == DESTINATION
        assert state.status is SubscriptionStatus.active
        assert state.tier_id == "gold"

    def test_no_row_is_the_adoption_with_creation_case_not_a_rejection(self):
        # [utest->req~restore-flow-02-resolve-canonical-subscription~1]
        state = resolve_canonical_subscription([], VERIFIED)
        assert state.row is None
        assert state.user_id is None

    def test_a_second_row_for_the_same_key_is_a_contract_failure(self):
        # [utest->req~restore-flow-02-resolve-canonical-subscription~1]
        with pytest.raises(RestoreContractError):
            resolve_canonical_subscription([subscription(), subscription()], VERIFIED)


class TestStep03ResolvePurchaseRow:

    def test_the_purchase_row_resolves_by_provider_and_external_id(self):
        # [utest->req~restore-flow-03-resolve-purchase-row-by-provider-external-id~1]
        wanted = purchase()
        older = purchase(external_id="1000000000000000")
        assert resolve_purchase_row([older, wanted], VERIFIED) is wanted

    def test_older_rows_carrying_the_same_token_are_irrelevant(self):
        """One token spans an account's whole purchase history; only this key selects the row."""
        # [utest->req~restore-flow-03-resolve-purchase-row-by-provider-external-id~1]
        older = purchase(external_id="1000000000000000")
        assert resolve_purchase_row([older], VERIFIED) is None

    def test_token_only_resolution_is_not_used(self):
        # [utest->req~restore-flow-03-resolve-purchase-row-by-provider-external-id~1]
        with pytest.raises(RestoreContractError):
            resolve_purchase_row([purchase()], VERIFIED, by_token=True)


class TestStep04CarriedPurchaseUuid:

    def test_a_matching_carried_uuid_passes(self):
        # [utest->req~restore-flow-04-carried-uuid-must-match-identity-value~1]
        assert assert_carried_uuid_matches(VERIFIED, purchase()) == TOKEN

    def test_a_differing_carried_uuid_rejects_as_purchase_uuid_mismatch(self):
        # [utest->req~restore-flow-04-carried-uuid-must-match-identity-value~1]
        # [utest->req~restore-policy-purchase-uuid-mismatch-rejects~1]
        with pytest.raises(RestoreRejection) as caught:
            assert_carried_uuid_matches(VERIFIED, purchase(identity_value="another-token"))
        assert caught.value.result is AuthEventResult.restore_purchase_uuid_mismatch

    def test_no_carried_uuid_and_no_row_are_both_fine(self):
        # [utest->req~restore-flow-04-carried-uuid-must-match-identity-value~1]
        assert assert_carried_uuid_matches(
            VerifiedTransaction(StoreProvider.apple, EXTERNAL_ID), purchase()) is None
        assert assert_carried_uuid_matches(VERIFIED, None) == TOKEN


class TestMissingEchoedToken:

    def test_a_missing_echoed_token_does_not_reject(self):
        """Store-initiated transactions legitimately omit the echoed token."""
        # [utest->req~restore-policy-missing-echoed-token-not-rejected~1]
        internal = internal_purchase_uuid(VerifiedTransaction(StoreProvider.apple, EXTERNAL_ID))
        assert UUID(internal)

    def test_a_carried_token_is_used_as_it_stands(self):
        # [utest->req~restore-policy-missing-echoed-token-not-rejected~1]
        assert internal_purchase_uuid(VERIFIED) == TOKEN


class TestStep05BranchSelection:

    def test_the_same_owner_selects_the_same_account_branch(self):
        # [utest->req~restore-flow-05-branch-selection~1]
        # [utest->req~restore-policy-same-owner-selects-same-account~1]
        state = CurrentSubscriptionState(subscription(user_id=DESTINATION))
        assert select_branch(subscription=state, destination_user_id=DESTINATION,
                             grant_user_id=DESTINATION) is RestoreBranch.same_account

    def test_an_unclaimed_subscription_selects_adoption(self):
        # [utest->req~restore-flow-05-branch-selection~1]
        # [utest->req~restore-policy-unclaimed-selects-adoption~1]
        assert select_branch(subscription=CurrentSubscriptionState(subscription(user_id=None)),
                             destination_user_id=DESTINATION) is RestoreBranch.adoption

    def test_no_canonical_row_at_all_selects_adoption(self):
        # [utest->req~restore-policy-unclaimed-selects-adoption~1]
        assert select_branch(subscription=CurrentSubscriptionState(None),
                             destination_user_id=DESTINATION) is RestoreBranch.adoption

    def test_a_different_owner_rejects_and_never_transfers(self):
        # [utest->req~restore-flow-05-branch-selection~1]
        # [utest->req~restore-policy-different-owner-rejects~1]
        state = CurrentSubscriptionState(subscription(user_id=OTHER))
        with pytest.raises(RestoreRejection) as caught:
            select_branch(subscription=state, destination_user_id=DESTINATION,
                          grant_user_id=OTHER)
        assert caught.value.result is AuthEventResult.store_transaction_already_linked

    def test_an_inactive_linked_source_audits_as_source_user_inactive(self):
        # [utest->req~restore-policy-different-owner-rejects~1]
        state = CurrentSubscriptionState(subscription(user_id=OTHER))
        with pytest.raises(RestoreRejection) as caught:
            select_branch(subscription=state, destination_user_id=DESTINATION,
                          grant_user_id=OTHER, source_user_active=False)
        assert caught.value.result is AuthEventResult.restore_source_user_inactive

    def test_adoption_is_untouched_by_the_source_active_precondition(self):
        """Adoption of an unclaimed subscription has no source account."""
        # [utest->req~restore-policy-different-owner-rejects~1]
        assert select_branch(subscription=CurrentSubscriptionState(subscription(user_id=None)),
                             destination_user_id=DESTINATION,
                             source_user_active=False) is RestoreBranch.adoption

    def test_owner_disagreement_with_the_grant_rejects(self):
        """The canonical owner must agree with the subscription-backed grant's `user_id`."""
        # [utest->req~restore-flow-05-branch-selection~1]
        state = CurrentSubscriptionState(subscription(user_id=DESTINATION))
        with pytest.raises(RestoreRejection) as caught:
            select_branch(subscription=state, destination_user_id=DESTINATION,
                          grant_user_id=OTHER)
        assert caught.value.result is \
            AuthEventResult.restore_subscription_grant_owner_mismatch


class TestLifetimeBindingAppliesToEveryAttempt:

    @pytest.mark.parametrize("owner", [None, DESTINATION, OTHER])
    def test_the_binding_is_evaluated_whatever_the_branch_would_be(self, owner):
        # [utest->req~restore-policy-lifetime-binding-applies-to-every-attempt~1]
        state = CurrentSubscriptionState(subscription(user_id=owner, bound=DESTINATION))
        assert apply_lifetime_binding(subscription=state,
                                     destination_user_id=DESTINATION) \
            is BindingOutcome.idempotent

    def test_a_destination_differing_from_the_binding_rejects_on_any_branch(self):
        # [utest->req~restore-policy-lifetime-binding-applies-to-every-attempt~1]
        state = CurrentSubscriptionState(subscription(user_id=None, bound=OTHER))
        with pytest.raises(RestoreRejection) as caught:
            apply_lifetime_binding(subscription=state, destination_user_id=DESTINATION)
        assert caught.value.result is AuthEventResult.store_transaction_already_linked

    def test_a_null_binding_is_set_by_this_restore(self):
        # [utest->req~restore-policy-lifetime-binding-applies-to-every-attempt~1]
        state = CurrentSubscriptionState(subscription(user_id=None, bound=None))
        assert apply_lifetime_binding(subscription=state,
                                     destination_user_id=DESTINATION) is BindingOutcome.bound


class TestStep06ProductEntitled:

    @pytest.mark.parametrize("status", [SubscriptionStatus.active,
                                        SubscriptionStatus.grace_period])
    def test_entitled_statuses_pass(self, status):
        # [utest->req~restore-flow-06-product-entitled-required~1]
        assert assert_product_entitled(status) is None

    @pytest.mark.parametrize("status", [SubscriptionStatus.billing_retry,
                                        SubscriptionStatus.expired,
                                        SubscriptionStatus.revoked])
    def test_non_entitled_statuses_reject(self, status):
        # [utest->req~restore-flow-06-product-entitled-required~1]
        with pytest.raises(RestoreRejection) as caught:
            assert_product_entitled(status)
        assert caught.value.result is AuthEventResult.restore_subscription_not_entitled

    def test_the_creation_path_uses_the_live_verified_state(self):
        # [utest->req~restore-flow-06-product-entitled-required~1]
        assert assert_product_entitled(
            None, live_verified_status=SubscriptionStatus.active) is None
        with pytest.raises(RestoreRejection):
            assert_product_entitled(None, live_verified_status=None)


class TestMissingRowPolicies:

    def test_a_missing_subscription_row_takes_adoption_with_creation(self):
        # [utest->req~restore-policy-missing-subscription-row-adoption-with-creation~1]
        assert missing_subscription_row_path(CurrentSubscriptionState(None)) \
            is RestoreBranch.adoption

    def test_an_existing_subscription_row_is_no_creation_path(self):
        # [utest->req~restore-policy-missing-subscription-row-adoption-with-creation~1]
        assert missing_subscription_row_path(
            CurrentSubscriptionState(subscription(user_id=DESTINATION))) is None

    def test_a_missing_purchase_row_is_created_the_same_way(self):
        # [utest->req~restore-policy-missing-purchase-row-created~1]
        assert missing_purchase_row_path(None) is RestoreBranch.adoption
        assert missing_purchase_row_path(purchase()) is None

    def test_only_a_failed_store_verification_rejects_for_proof_reasons(self):
        # [utest->req~restore-policy-missing-purchase-row-created~1]
        with pytest.raises(RestoreRejection) as caught:
            missing_purchase_row_path(None, store_verified=False)
        assert caught.value.result is AuthEventResult.invalid_restore_proof


class TestPurchaseRowsImmutable:

    def test_restore_defines_no_purchase_row_mutation(self):
        # [utest->req~restore-policy-purchase-rows-immutable~1]
        assert PURCHASE_ROW_MUTATIONS == frozenset()

    @pytest.mark.parametrize("operation", ["reassign", "revoke", "rewrite", "update"])
    @pytest.mark.parametrize("branch", [RestoreBranch.same_account, RestoreBranch.adoption])
    def test_neither_branch_may_mutate_a_purchase_row(self, operation, branch):
        # [utest->req~restore-policy-purchase-rows-immutable~1]
        with pytest.raises(RestoreContractError):
            assert_purchase_row_immutable(purchase_row=purchase(), operation=operation,
                                          branch=branch)

    def test_insert_once_creation_applies_only_where_no_row_exists(self):
        # [utest->req~restore-policy-purchase-rows-immutable~1]
        assert assert_purchase_row_immutable(purchase_row=None,
                                            operation=PURCHASE_ROW_INSERT_ONCE,
                                            branch=RestoreBranch.adoption) is None
        with pytest.raises(RestoreContractError):
            assert_purchase_row_immutable(purchase_row=purchase(),
                                          operation=PURCHASE_ROW_INSERT_ONCE,
                                          branch=RestoreBranch.adoption)

    def test_purchase_user_id_survives_an_owner_change(self):
        """`purchase_user_id` keeps naming the user the echoed token resolved to at ingestion."""
        # [utest->req~restore-policy-purchase-rows-immutable~1]
        row = purchase(purchase_user_id=OTHER)
        state = CurrentSubscriptionState(subscription(user_id=None))
        authorize_restore(subscription=state, purchase_row=row, verified=VERIFIED,
                          destination_user_id=DESTINATION, live_store_verified=True,
                          live_verified_status=SubscriptionStatus.active)
        assert row.purchase_user_id == OTHER


class TestOwnershipAuthorizationConjunction:

    def test_same_account_authorization_needs_owner_and_purchase_row(self):
        # [utest->req~restore-ownership-authorization-conjunction~1]
        state = CurrentSubscriptionState(subscription(user_id=DESTINATION))
        outcome = authorize_restore(subscription=state, purchase_row=purchase(),
                                    verified=VERIFIED, destination_user_id=DESTINATION,
                                    grant_user_id=DESTINATION)
        assert outcome.branch is RestoreBranch.same_account
        assert outcome.binding is BindingOutcome.bound

    def test_a_mismatched_carried_uuid_breaks_the_conjunction(self):
        # [utest->req~restore-ownership-authorization-conjunction~1]
        state = CurrentSubscriptionState(subscription(user_id=DESTINATION))
        with pytest.raises(RestoreRejection) as caught:
            authorize_restore(subscription=state,
                              purchase_row=purchase(identity_value="other-token"),
                              verified=VERIFIED, destination_user_id=DESTINATION,
                              grant_user_id=DESTINATION)
        assert caught.value.result is AuthEventResult.restore_purchase_uuid_mismatch

    def test_adoption_requires_live_store_state_verification(self):
        # [utest->req~restore-ownership-authorization-conjunction~1]
        state = CurrentSubscriptionState(subscription(user_id=None))
        with pytest.raises(RestoreRejection) as caught:
            authorize_restore(subscription=state, purchase_row=purchase(), verified=VERIFIED,
                              destination_user_id=DESTINATION, live_store_verified=False,
                              live_verified_status=SubscriptionStatus.active)
        assert caught.value.result is AuthEventResult.restore_store_state_unverified

    def test_adoption_requires_a_destination_with_no_different_active_grant(self):
        # [utest->req~restore-ownership-authorization-conjunction~1]
        state = CurrentSubscriptionState(subscription(user_id=None))
        with pytest.raises(RestoreRejection) as caught:
            authorize_restore(subscription=state, purchase_row=purchase(), verified=VERIFIED,
                              destination_user_id=DESTINATION,
                              destination_holds_different_active_grant=True,
                              live_store_verified=True,
                              live_verified_status=SubscriptionStatus.active)
        assert caught.value.result is AuthEventResult.restore_destination_already_entitled

    def test_a_different_current_owner_is_never_transferred(self):
        # [utest->req~restore-ownership-authorization-conjunction~1]
        state = CurrentSubscriptionState(subscription(user_id=OTHER))
        with pytest.raises(RestoreRejection) as caught:
            authorize_restore(subscription=state, purchase_row=purchase(), verified=VERIFIED,
                              destination_user_id=DESTINATION, grant_user_id=OTHER)
        assert caught.value.result is AuthEventResult.store_transaction_already_linked

    def test_a_non_entitled_state_is_not_authorized(self):
        # [utest->req~restore-ownership-authorization-conjunction~1]
        state = CurrentSubscriptionState(subscription(user_id=DESTINATION,
                                                     status=SubscriptionStatus.expired))
        with pytest.raises(RestoreRejection) as caught:
            authorize_restore(subscription=state, purchase_row=purchase(), verified=VERIFIED,
                              destination_user_id=DESTINATION, grant_user_id=DESTINATION)
        assert caught.value.result is AuthEventResult.restore_subscription_not_entitled

    def test_adoption_of_an_unclaimed_subscription_is_authorized(self):
        # [utest->req~restore-ownership-authorization-conjunction~1]
        state = CurrentSubscriptionState(subscription(user_id=None))
        outcome = authorize_restore(subscription=state, purchase_row=None, verified=VERIFIED,
                                    destination_user_id=DESTINATION, live_store_verified=True,
                                    live_verified_status=SubscriptionStatus.active)
        assert outcome.branch is RestoreBranch.adoption
