"""The same-account branch: entry condition, the four mutation rules, and the postconditions."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantStatus
from nativespeaker.api.auth.invariants import InvariantError, StoreProvider
from nativespeaker.api.auth.restore import RestoreBranch, RestoreRejection
from nativespeaker.api.auth.restore_flow import (
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
)
from nativespeaker.api.auth.restore_operation import RestoreGrantMutations
from nativespeaker.api.auth.restore_same_account import (
    GrantSettlement,
    PaidPeriod,
    SameAccountError,
    StateRefresh,
    SubscriptionGrant,
    already_owned_is_this_branch,
    entry_destination_active,
    entry_owner_equals_destination,
    mutation_01_validate_before_mutation,
    mutation_02_settle_grant_status,
    mutation_03_purchase_row_insert_once,
    mutation_04_audit_row,
    postcondition_grant_id_preserved,
    postcondition_usage_row_attached,
)
from nativespeaker.api.models import SubscriptionStatus

DESTINATION = uuid7()
OTHER = uuid7()
EXTERNAL_ID = "2000000123456789"
TOKEN = "11111111-2222-3333-4444-555555555555"
APPLE = StoreProvider.apple
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
VERIFIED = VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID,
                               carried_purchase_uuid=TOKEN)
SUBSCRIPTION_ID = uuid7()


def state(*, user_id: UUID | None = DESTINATION,
          status: SubscriptionStatus = SubscriptionStatus.active,
          bound: UUID | None = None) -> CurrentSubscriptionState:
    return CurrentSubscriptionState(row=SubscriptionRow(
        subscription_id=SUBSCRIPTION_ID, provider=APPLE, external_id=EXTERNAL_ID,
        status=status, tier_id="gold", user_id=user_id, restore_bound_user_id=bound))


def purchase(*, purchase_user_id: UUID | None = DESTINATION,
             identity_value: str = TOKEN) -> PurchaseRow:
    return PurchaseRow(purchase_id=uuid7(), provider=APPLE, external_id=EXTERNAL_ID,
                       identity_value=identity_value, purchase_user_id=purchase_user_id)


def grant(*, status: AccessGrantStatus = AccessGrantStatus.active,
          user_id: UUID = DESTINATION,
          grant_id: UUID | None = None) -> SubscriptionGrant:
    return SubscriptionGrant(grant_id=grant_id or uuid7(), user_id=user_id, status=status,
                             subscription_id=SUBSCRIPTION_ID, tier_id="gold")


def validated() -> RestoreGrantMutations:
    mutations = RestoreGrantMutations()
    mutations.validate()
    return mutations


# --- Entry condition ------------------------------------------------------------------------------


# [utest->req~restore-same-account-entry-owner-equals-destination~1]
def test_the_entry_condition_needs_the_owner_to_be_the_destination():
    assert entry_owner_equals_destination(state(), destination_user_id=DESTINATION) is True
    assert entry_owner_equals_destination(state(user_id=OTHER),
                                          destination_user_id=DESTINATION) is False
    assert entry_owner_equals_destination(state(user_id=None),
                                          destination_user_id=DESTINATION) is False


# [utest->req~restore-same-account-entry-owner-equals-destination~1]
def test_the_owner_must_agree_with_the_subscription_backed_grant():
    with pytest.raises(RestoreRejection) as raised:
        entry_owner_equals_destination(state(), destination_user_id=DESTINATION,
                                       grant=grant(user_id=OTHER))
    assert raised.value.result is AuthEventResult.restore_subscription_grant_owner_mismatch
    assert entry_owner_equals_destination(state(), destination_user_id=DESTINATION,
                                          grant=grant()) is True


# [utest->req~restore-same-account-entry-destination-active~1]
def test_an_inactive_destination_is_blocked():
    assert entry_destination_active(destination_user_id=DESTINATION,
                                    destination_active=True) == DESTINATION
    with pytest.raises(RestoreRejection) as raised:
        entry_destination_active(destination_user_id=DESTINATION, destination_active=False)
    assert raised.value.result is AuthEventResult.blocked_user


# [utest->req~restore-same-account-already-owned-is-this-branch~1]
def test_an_already_owned_restore_with_a_foreign_purchase_user_is_still_same_account():
    assert already_owned_is_this_branch(subscription=state(),
                                        purchase_row=purchase(purchase_user_id=OTHER),
                                        destination_user_id=DESTINATION) is RestoreBranch.same_account


# [utest->req~restore-same-account-already-owned-is-this-branch~1]
def test_an_already_owned_restore_is_never_rejected_as_already_entitled():
    with pytest.raises(SameAccountError):
        already_owned_is_this_branch(
            subscription=state(), purchase_row=purchase(), destination_user_id=DESTINATION,
            rejected_as=AuthEventResult.restore_destination_already_entitled)


# [utest->req~restore-same-account-already-owned-is-this-branch~1]
def test_an_already_owned_restore_updates_no_transfer_month_and_names_no_token_bound_source():
    with pytest.raises(InvariantError):
        already_owned_is_this_branch(
            subscription=state(), purchase_row=purchase(), destination_user_id=DESTINATION,
            subscription_columns_written=("last_cross_account_transfer_month",))
    assert already_owned_is_this_branch(
        subscription=state(), purchase_row=purchase(), destination_user_id=DESTINATION,
        subscription_columns_written=("user_id",)) is RestoreBranch.same_account
    with pytest.raises(SameAccountError):
        already_owned_is_this_branch(subscription=state(),
                                     purchase_row=purchase(purchase_user_id=OTHER),
                                     destination_user_id=DESTINATION,
                                     recorded_source_user_id=OTHER)
    assert already_owned_is_this_branch(subscription=state(), purchase_row=purchase(),
                                        destination_user_id=DESTINATION,
                                        recorded_source_user_id=DESTINATION)


# --- Mutation rule 1 ------------------------------------------------------------------------------


# [utest->req~restore-same-account-mutation-01-validate-before-mutation~1]
def test_validation_completes_before_any_grant_mutation():
    mutations = RestoreGrantMutations()
    assert mutation_01_validate_before_mutation(
        subscription=state(), purchase_row=purchase(), verified=VERIFIED,
        destination_user_id=DESTINATION, grant=grant(), mutations=mutations) == DESTINATION
    assert mutations.validated is True
    assert mutations.statements == []


# [utest->req~restore-same-account-mutation-01-validate-before-mutation~1]
def test_same_account_validation_performs_no_owner_or_ownership_change():
    with pytest.raises(SameAccountError):
        mutation_01_validate_before_mutation(
            subscription=state(), purchase_row=purchase(), verified=VERIFIED,
            destination_user_id=DESTINATION, grant=grant(), mutations=RestoreGrantMutations(),
            performed=("subscriptions_owner_change",))
    with pytest.raises(SameAccountError):
        mutation_01_validate_before_mutation(
            subscription=state(), purchase_row=purchase(), verified=VERIFIED,
            destination_user_id=DESTINATION, grant=grant(), mutations=RestoreGrantMutations(),
            performed=("grant_ownership_change",))


# [utest->req~restore-same-account-mutation-01-validate-before-mutation~1]
def test_validation_decides_the_binding_and_the_entitlement_before_mutating():
    with pytest.raises(RestoreRejection) as raised:
        mutation_01_validate_before_mutation(
            subscription=state(bound=OTHER), purchase_row=purchase(), verified=VERIFIED,
            destination_user_id=DESTINATION, grant=grant(), mutations=RestoreGrantMutations())
    assert raised.value.result is AuthEventResult.store_transaction_already_linked
    with pytest.raises(RestoreRejection) as not_entitled:
        mutation_01_validate_before_mutation(
            subscription=state(status=SubscriptionStatus.expired), purchase_row=purchase(),
            verified=VERIFIED, destination_user_id=DESTINATION, grant=grant(),
            mutations=RestoreGrantMutations())
    assert not_entitled.value.result is AuthEventResult.restore_subscription_not_entitled


# [utest->req~restore-same-account-mutation-01-validate-before-mutation~1]
def test_a_permitted_state_refresh_updates_row_and_grant_in_one_deduped_transaction():
    transaction = object()
    assert mutation_01_validate_before_mutation(
        subscription=state(), purchase_row=purchase(), verified=VERIFIED,
        destination_user_id=DESTINATION, grant=grant(), mutations=RestoreGrantMutations(),
        state_refresh=StateRefresh(status=SubscriptionStatus.grace_period,
                                   subscription_transaction=transaction,
                                   grant_transaction=transaction)) == DESTINATION
    with pytest.raises(SameAccountError):
        mutation_01_validate_before_mutation(
            subscription=state(), purchase_row=purchase(), verified=VERIFIED,
            destination_user_id=DESTINATION, grant=grant(), mutations=RestoreGrantMutations(),
            state_refresh=StateRefresh(status=SubscriptionStatus.grace_period,
                                       subscription_transaction=transaction,
                                       grant_transaction=object()))
    with pytest.raises(SameAccountError):
        mutation_01_validate_before_mutation(
            subscription=state(), purchase_row=purchase(), verified=VERIFIED,
            destination_user_id=DESTINATION, grant=grant(), mutations=RestoreGrantMutations(),
            state_refresh=StateRefresh(status=SubscriptionStatus.grace_period,
                                       subscription_transaction=transaction,
                                       grant_transaction=transaction, deduped=False))


# --- Mutation rule 2: the four settlement cases, and the corruption case --------------------------


# [utest->req~restore-same-account-mutation-02-settle-grant-status~1]
def test_an_entitled_already_active_grant_settles_idempotently():
    mutations = validated()
    existing = grant()
    settled = mutation_02_settle_grant_status(status=SubscriptionStatus.active, grant=existing,
                                              mutations=mutations)
    assert settled.settlement is GrantSettlement.idempotent_success
    assert settled.grant_id == existing.grant_id
    assert mutations.statements == []
    assert mutations.activated is None


# [utest->req~restore-same-account-mutation-02-settle-grant-status~1]
def test_an_entitled_expired_grant_is_reactivated_on_the_same_row():
    mutations = validated()
    existing = grant(status=AccessGrantStatus.expired)
    period = PaidPeriod(tier_id="platinum", ends_at=NOW + timedelta(days=30))
    settled = mutation_02_settle_grant_status(status=SubscriptionStatus.grace_period,
                                              grant=existing, mutations=mutations,
                                              paid_period=period)
    assert settled.settlement is GrantSettlement.reactivated
    assert settled.grant_id == existing.grant_id
    assert settled.status is AccessGrantStatus.active
    assert (settled.tier_id, settled.ends_at) == ("platinum", period.ends_at)
    assert mutations.activated == existing.grant_id


# [utest->req~restore-same-account-mutation-02-settle-grant-status~1]
def test_reactivation_never_mints_a_new_row_and_never_replaces_attribution_tokens():
    with pytest.raises(SameAccountError):
        mutation_02_settle_grant_status(status=SubscriptionStatus.active,
                                        grant=grant(status=AccessGrantStatus.expired),
                                        mutations=validated(), mint_new_grant_row=True)
    with pytest.raises(SameAccountError):
        mutation_02_settle_grant_status(status=SubscriptionStatus.active,
                                        grant=grant(status=AccessGrantStatus.expired),
                                        mutations=validated(), replace_attribution_tokens=True)


# [utest->req~restore-same-account-mutation-02-settle-grant-status~1]
def test_a_different_active_grant_is_the_already_entitled_conflict_and_is_never_expired():
    mutations = validated()
    with pytest.raises(RestoreRejection) as raised:
        mutation_02_settle_grant_status(status=SubscriptionStatus.active,
                                        grant=grant(status=AccessGrantStatus.expired),
                                        mutations=mutations,
                                        different_active_grant_id=uuid7())
    assert raised.value.result is AuthEventResult.restore_destination_already_entitled
    assert mutations.expired == []
    assert mutations.statements == []


# [utest->req~restore-same-account-mutation-02-settle-grant-status~1]
def test_a_non_entitled_subscription_never_activates_the_grant():
    mutations = validated()
    with pytest.raises(RestoreRejection) as raised:
        mutation_02_settle_grant_status(status=SubscriptionStatus.revoked,
                                        grant=grant(status=AccessGrantStatus.expired),
                                        mutations=mutations)
    assert raised.value.result is AuthEventResult.restore_subscription_not_entitled
    assert mutations.activated is None


# [utest->req~restore-same-account-mutation-02-settle-grant-status~1]
def test_an_entitled_owned_subscription_with_no_grant_row_fails_closed_and_creates_nothing():
    mutations = validated()
    with pytest.raises(RestoreRejection) as raised:
        mutation_02_settle_grant_status(status=SubscriptionStatus.active, grant=None,
                                        mutations=mutations)
    assert raised.value.result is AuthEventResult.internal_error
    assert mutations.activated is None
    assert mutations.statements == []


# --- Mutation rules 3 and 4 -----------------------------------------------------------------------


# [utest->req~restore-same-account-mutation-03-purchase-row-insert-once~1]
def test_a_resolved_purchase_row_is_neither_updated_nor_revoked():
    assert mutation_03_purchase_row_insert_once(
        purchase_row=purchase(), verified=VERIFIED, destination_user_id=DESTINATION,
        current_owner=DESTINATION) is None
    for operation in ("update", "revoke", "reassign"):
        with pytest.raises(SameAccountError):
            mutation_03_purchase_row_insert_once(
                purchase_row=purchase(), verified=VERIFIED, destination_user_id=DESTINATION,
                current_owner=DESTINATION, operation=operation)


# [utest->req~restore-same-account-mutation-03-purchase-row-insert-once~1]
def test_a_missing_purchase_row_is_inserted_once_for_the_destination():
    written = mutation_03_purchase_row_insert_once(
        purchase_row=None, verified=VERIFIED, destination_user_id=DESTINATION,
        current_owner=DESTINATION)
    assert written is not None
    assert (written.provider, written.external_id) == (APPLE, EXTERNAL_ID)
    assert written.identity_value == TOKEN
    assert written.purchase_user_id == DESTINATION


# [utest->req~restore-same-account-mutation-03-purchase-row-insert-once~1]
def test_a_transaction_carrying_no_uuid_gets_a_server_generated_internal_one():
    written = mutation_03_purchase_row_insert_once(
        purchase_row=None,
        verified=VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID),
        destination_user_id=DESTINATION, current_owner=DESTINATION)
    assert written is not None
    assert UUID(written.identity_value)


# [utest->req~restore-same-account-mutation-04-audit-row~1]
def test_the_audit_row_classifies_as_same_account_with_no_token_bound_source_user():
    details = mutation_04_audit_row(current_owner=DESTINATION, destination_user_id=DESTINATION,
                                    purchase_row=purchase(purchase_user_id=OTHER),
                                    subscription_id=SUBSCRIPTION_ID)
    assert details["mutation"]["movement_classification"] == "same_account"
    assert details["resolved"]["source_user_id"] is None
    with pytest.raises(SameAccountError):
        mutation_04_audit_row(current_owner=DESTINATION, destination_user_id=DESTINATION,
                              purchase_row=purchase(purchase_user_id=OTHER),
                              recorded_source_user_id=OTHER)
    owned = mutation_04_audit_row(current_owner=DESTINATION, destination_user_id=DESTINATION,
                                  recorded_source_user_id=DESTINATION)
    assert owned["resolved"]["source_user_id"] == DESTINATION


# --- Postconditions -------------------------------------------------------------------------------


# [utest->req~restore-same-account-postcondition-grant-id-preserved~1]
def test_the_grant_keeps_its_id_and_its_destination_owner():
    before = grant()
    assert postcondition_grant_id_preserved(before=before, after=before,
                                            destination_user_id=DESTINATION) == before.grant_id
    with pytest.raises(SameAccountError):
        postcondition_grant_id_preserved(before=before, after=grant(),
                                         destination_user_id=DESTINATION)
    with pytest.raises(SameAccountError):
        postcondition_grant_id_preserved(
            before=before,
            after=SubscriptionGrant(grant_id=before.grant_id, user_id=OTHER,
                                    status=before.status, subscription_id=SUBSCRIPTION_ID,
                                    tier_id="gold"),
            destination_user_id=DESTINATION)


# [utest->req~restore-same-account-postcondition-usage-row-attached~1]
def test_the_monthly_usage_row_stays_on_the_same_grant_id():
    grant_id = uuid7()
    assert postcondition_usage_row_attached(grant_id=grant_id,
                                            usage_row_grant_id=grant_id) == grant_id
    with pytest.raises(Exception):
        postcondition_usage_row_attached(grant_id=grant_id, usage_row_grant_id=uuid7())
    with pytest.raises(Exception):
        postcondition_usage_row_attached(grant_id=grant_id, usage_row_grant_id=grant_id,
                                         minted_fresh=True)
