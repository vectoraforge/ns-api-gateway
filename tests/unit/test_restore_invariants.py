"""Restore's own invariants: the properties every restore outcome must leave true."""

from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import InvariantError, StoreProvider
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreAttemptAudit,
    RestoreBranch,
    RestoreRejection,
)
from nativespeaker.api.auth.restore_flow import (
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
)
from nativespeaker.api.auth.restore_invariants import (
    CANONICAL_STATE_TABLE,
    CROSS_ACCOUNT_TRANSFER_PATHS,
    OBSERVATION_HISTORY_TABLE,
    OWNERSHIP_ESTABLISHING_BRANCH,
    RESTORE_PROOF_DOES_NOT_PROVE,
    RestoreInvariantError,
    assert_adoption_preconditions,
    assert_entitlement_never_moved_away,
    assert_grant_settled_in_place,
    assert_never_two_active_grants,
    assert_no_device_check_state,
    assert_owner_mismatch_rejection,
    assert_paid_entitlement_only,
    assert_proof_is_bearer_credential_only,
    assert_proof_material_not_persisted,
    assert_purchase_rows_immutable,
    assert_same_account_ownership_established,
    assert_updated_in_place,
    audited_source_user,
    canonical_current_state,
    purchase_row_attribution,
    select_restore_outcome,
)
from nativespeaker.api.models import SubscriptionStatus

APPLE = StoreProvider.apple
EXTERNAL_ID = "2000000123456789"
VERIFIED = VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID)
DESTINATION = uuid7()
OTHER = uuid7()


def subscription_row(user_id=None, *, external_id: str = EXTERNAL_ID) -> SubscriptionRow:
    return SubscriptionRow(subscription_id=uuid7(), provider=APPLE, external_id=external_id,
                           status=SubscriptionStatus.active, tier_id="pro", user_id=user_id)


def purchase_row(user_id=None) -> PurchaseRow:
    return PurchaseRow(purchase_id=uuid7(), provider=APPLE, external_id=EXTERNAL_ID,
                       identity_value="token-1", purchase_user_id=user_id)


# --- 2. The canonical row --------------------------------------------------------------------------


# [utest->req~restore-invariant-02~1]
def test_the_canonical_row_is_exactly_one_row_per_store_subscription():
    row = subscription_row(DESTINATION)
    state = canonical_current_state([row, subscription_row(OTHER, external_id="other")], VERIFIED)
    assert state.row is row
    assert (state.user_id, state.status, state.tier_id) == (DESTINATION,
                                                            SubscriptionStatus.active, "pro")
    with pytest.raises(Exception, match="exactly one canonical subscription row"):
        canonical_current_state([row, subscription_row(OTHER)], VERIFIED)


# [utest->req~restore-invariant-02~1]
def test_an_existing_canonical_row_is_updated_in_place_and_history_stays_append_only():
    existing = CurrentSubscriptionState(row=subscription_row(DESTINATION))
    assert_updated_in_place(existing=existing, rows_updated=1, history_rows_appended=1)
    with pytest.raises(RestoreInvariantError, match=CANONICAL_STATE_TABLE):
        assert_updated_in_place(existing=existing, rows_inserted=1)
    with pytest.raises(RestoreInvariantError, match=OBSERVATION_HISTORY_TABLE):
        assert_updated_in_place(existing=existing, rows_updated=1, history_rows_updated=1)


# --- 5. What the restore proof proves ----------------------------------------------------------------


# [utest->req~restore-invariant-05~1]
def test_a_restore_proof_proves_entitlement_and_not_prior_account_ownership():
    assert assert_proof_is_bearer_credential_only(claims=("subscription_entitlement",))
    for overclaim in RESTORE_PROOF_DOES_NOT_PROVE:
        with pytest.raises(RestoreInvariantError, match="does not show"):
            assert_proof_is_bearer_credential_only(claims=(overclaim,))


# [utest->req~restore-invariant-05~1]
def test_same_account_ownership_needs_the_owner_and_the_purchase_row():
    owned = CurrentSubscriptionState(row=subscription_row(DESTINATION))
    assert assert_same_account_ownership_established(
        subscription=owned, destination_user_id=DESTINATION,
        purchase_row=purchase_row(DESTINATION)) is RestoreBranch.same_account
    assert assert_same_account_ownership_established(
        subscription=owned, destination_user_id=DESTINATION, purchase_row=None,
        purchase_row_created=True) is RestoreBranch.same_account
    with pytest.raises(RestoreInvariantError, match="canonical owner"):
        assert_same_account_ownership_established(
            subscription=CurrentSubscriptionState(row=subscription_row(OTHER)),
            destination_user_id=DESTINATION, purchase_row=purchase_row(OTHER))
    with pytest.raises(RestoreInvariantError, match="insert_once"):
        assert_same_account_ownership_established(
            subscription=owned, destination_user_id=DESTINATION, purchase_row=None)


# [utest->req~restore-invariant-05~1]
def test_adoption_needs_every_precondition_and_never_transfers_across_accounts():
    unclaimed = CurrentSubscriptionState(row=subscription_row(None))
    assert assert_adoption_preconditions(subscription=unclaimed, live_verified=True,
                                         lifetime_binding_checked=True) is RestoreBranch.adoption
    with pytest.raises(RestoreInvariantError, match="unclaimed"):
        assert_adoption_preconditions(
            subscription=CurrentSubscriptionState(row=subscription_row(OTHER)),
            live_verified=True, lifetime_binding_checked=True)
    with pytest.raises(RestoreInvariantError, match="lifetime store-transaction"):
        assert_adoption_preconditions(subscription=unclaimed, live_verified=True,
                                      lifetime_binding_checked=False)
    with pytest.raises(RestoreInvariantError, match="live store-state verification"):
        assert_adoption_preconditions(subscription=unclaimed, live_verified=False,
                                      lifetime_binding_checked=True)
    assert CROSS_ACCOUNT_TRANSFER_PATHS == frozenset()


# [utest->req~restore-invariant-05~1]
def test_raw_proof_material_goes_nowhere_but_the_verification_path():
    assert assert_proof_material_not_persisted("store_verification_call")
    for sink in ("application_logs", "audit_rows", "durable_application_storage"):
        with pytest.raises(Exception, match="never written"):
            assert_proof_material_not_persisted(sink)


# --- 6. Purchase-row immutability -----------------------------------------------------------------


# [utest->req~restore-invariant-06~1]
def test_no_restore_branch_ever_mutates_a_purchase_row():
    for branch in RestoreBranch:
        assert_purchase_rows_immutable(branch=branch, actions=("read",))
        for action in ("reassign", "revoke", "rewrite", "mutate", "update", "delete"):
            with pytest.raises(RestoreInvariantError, match=action):
                assert_purchase_rows_immutable(branch=branch, actions=(action,))


# [utest->req~restore-invariant-06~1]
def test_insert_once_creation_only_writes_a_row_that_never_existed():
    assert_purchase_rows_immutable(branch=RestoreBranch.adoption, created=True, existing_row=None)
    with pytest.raises(RestoreInvariantError, match="never existed"):
        assert_purchase_rows_immutable(branch=RestoreBranch.adoption, created=True,
                                       existing_row=purchase_row(OTHER))


# [utest->req~restore-invariant-06~1]
def test_purchase_user_id_identifies_the_user_at_write_time():
    assert purchase_row_attribution(purchase_row(OTHER)) == OTHER
    # An unattributed ingestion row keeps its NULL for the lifetime of the row.
    assert purchase_row_attribution(purchase_row(None)) is None


# --- 7. What selects the outcome ---------------------------------------------------------------------


# [utest->req~restore-invariant-07~1]
def test_the_canonical_owner_alone_selects_the_outcome():
    owned = CurrentSubscriptionState(row=subscription_row(DESTINATION))
    unclaimed = CurrentSubscriptionState(row=subscription_row(None))
    # A purchase row attributed to somebody else does not make this a cross-account case.
    assert select_restore_outcome(subscription=owned, destination_user_id=DESTINATION,
                                  purchase_row=purchase_row(OTHER)) is RestoreBranch.same_account
    # And one attributed to the caller does not make an unclaimed subscription theirs by
    # attribution: it is adoption, under adoption's own preconditions.
    assert select_restore_outcome(subscription=unclaimed, destination_user_id=DESTINATION,
                                  purchase_row=purchase_row(DESTINATION)) is RestoreBranch.adoption


# [utest->req~restore-invariant-07~1]
def test_a_different_linked_account_rejects_whatever_the_purchase_row_says():
    linked = CurrentSubscriptionState(row=subscription_row(OTHER))
    with pytest.raises(RestoreRejection) as refused:
        select_restore_outcome(subscription=linked, destination_user_id=DESTINATION,
                               purchase_row=purchase_row(DESTINATION))
    assert refused.value.result is AuthEventResult.store_transaction_already_linked


# --- 8. The source user an audit row may record --------------------------------------------------------


# [utest->req~restore-invariant-08~1]
def test_a_recorded_source_user_is_the_canonical_owner_never_the_purchase_attribution():
    assert audited_source_user(subscription_user_id=DESTINATION, grant_user_id=DESTINATION,
                               purchase_user_id=OTHER,
                               recorded_source_user_id=DESTINATION) == DESTINATION
    # Recording the purchase row's attribution as the source user would hide the real owner.
    with pytest.raises(RestoreInvariantError, match="current owner"):
        audited_source_user(subscription_user_id=DESTINATION, grant_user_id=DESTINATION,
                            purchase_user_id=OTHER, recorded_source_user_id=OTHER)
    # No source user recorded at all is the ordinary same-account row.
    assert audited_source_user(subscription_user_id=DESTINATION, grant_user_id=DESTINATION) is None


# [utest->req~restore-invariant-08~1]
def test_a_recorded_source_user_needs_the_grant_and_subscription_to_agree():
    with pytest.raises(InvariantError, match="share one owner"):
        audited_source_user(subscription_user_id=DESTINATION, grant_user_id=OTHER,
                            recorded_source_user_id=DESTINATION)


# --- 9. What restore does not touch ---------------------------------------------------------------------


# [utest->req~restore-invariant-09~1]
def test_restore_settles_paid_subscription_entitlement_and_nothing_else():
    assert_paid_entitlement_only(("core.subscriptions", "core.access_grants"),
                                 branch=RestoreBranch.same_account,
                                 grant_sources_written=(AccessGrantSource.subscription,))
    for touched in ("core.chats", "core.messages", "core.external_identities",
                    "anonymous_device_grant", "manual_grant",
                    "non_subscription_user_monthly_usage"):
        with pytest.raises(RestoreInvariantError, match="does not move"):
            assert_paid_entitlement_only((touched,))
    with pytest.raises(RestoreInvariantError, match="writes no"):
        assert_paid_entitlement_only(grant_sources_written=(AccessGrantSource.manual,))


# [utest->req~restore-invariant-09~1]
def test_adoption_has_no_source_user_to_take_anything_from():
    with pytest.raises(RestoreInvariantError, match="no source user"):
        assert_paid_entitlement_only(branch=RestoreBranch.adoption, source_user_id=OTHER)


# --- 10. The grant stays in place ----------------------------------------------------------------------


# [utest->req~restore-invariant-10~1]
def test_same_account_restore_settles_the_grant_in_place_with_its_usage_row():
    grant_id = uuid7()
    assert assert_grant_settled_in_place(grant_id_before=grant_id, grant_id_after=grant_id,
                                         grant_user_id_before=DESTINATION,
                                         grant_user_id_after=DESTINATION,
                                         usage_grant_id_before=grant_id,
                                         usage_grant_id_after=grant_id) == grant_id
    with pytest.raises(RestoreInvariantError, match="another user"):
        assert_grant_settled_in_place(grant_id_before=grant_id, grant_id_after=grant_id,
                                      grant_user_id_before=DESTINATION,
                                      grant_user_id_after=OTHER)
    with pytest.raises(RestoreInvariantError, match="same id"):
        assert_grant_settled_in_place(grant_id_before=grant_id, grant_id_after=uuid7(),
                                      grant_user_id_before=DESTINATION,
                                      grant_user_id_after=DESTINATION)
    # A fresh monthly counter would mean a new grant_id on the usage row.
    with pytest.raises(RestoreInvariantError, match="same grant_id"):
        assert_grant_settled_in_place(grant_id_before=grant_id, grant_id_after=grant_id,
                                      grant_user_id_before=DESTINATION,
                                      grant_user_id_after=DESTINATION,
                                      usage_grant_id_before=grant_id,
                                      usage_grant_id_after=uuid7())


# --- 12. Device-check state ------------------------------------------------------------------------------


# [utest->req~restore-invariant-12~1]
def test_restore_neither_reads_nor_writes_per_device_free_grant_state():
    assert_no_device_check_state(reads=("core.subscriptions", "core.store_purchases"))
    with pytest.raises(RestoreInvariantError, match="reads"):
        assert_no_device_check_state(reads=("devicecheck_bit",))
    with pytest.raises(RestoreInvariantError, match="writes"):
        assert_no_device_check_state(writes=("play_integrity_device_recall",))


# --- 13. Entitlement never moves away ----------------------------------------------------------------------


# [utest->req~restore-invariant-13~1]
def test_entitlement_never_moves_away_and_only_adoption_establishes_ownership():
    assert OWNERSHIP_ESTABLISHING_BRANCH is RestoreBranch.adoption
    assert assert_entitlement_never_moved_away(branch=RestoreBranch.adoption, prior_owner_id=None,
                                               destination_user_id=DESTINATION) is (
        RestoreBranch.adoption)
    assert assert_entitlement_never_moved_away(branch=RestoreBranch.same_account,
                                               prior_owner_id=DESTINATION,
                                               destination_user_id=DESTINATION) is (
        RestoreBranch.same_account)
    with pytest.raises(RestoreInvariantError, match="store_transaction_already_linked"):
        assert_entitlement_never_moved_away(branch=RestoreBranch.adoption, prior_owner_id=OTHER,
                                            destination_user_id=DESTINATION)


# [utest->req~restore-invariant-13~1]
def test_the_rejected_owner_mismatch_writes_one_unclassified_row_and_mutates_nothing():
    audit = RestoreAttemptAudit()
    classification = assert_owner_mismatch_rejection(audit, branch=RestoreBranch.same_account,
                                                     audit_transaction=object())
    assert classification is MovementClassification.unclassified
    assert len(audit.rows) == 1
    assert audit.rows[0].result is AuthEventResult.restore_subscription_grant_owner_mismatch
    with pytest.raises(RestoreInvariantError, match="performs no"):
        assert_owner_mismatch_rejection(RestoreAttemptAudit(), branch=RestoreBranch.same_account,
                                        audit_transaction=object(),
                                        mutations_performed=("access_grants_write",))


# --- 14. Never two active grants ---------------------------------------------------------------------------


# [utest->req~restore-invariant-14~2]
def test_a_restore_never_leaves_the_destination_holding_two_active_grants():
    existing = uuid7()
    # The existing active grant is ended as part of the restore.
    assert assert_never_two_active_grants(existing_active_grant_id=existing,
                                          existing_grant_status_after=AccessGrantStatus.expired,
                                          restored_grant_active=True) == 1
    # Or the restore is rejected and the existing grant stands alone.
    assert assert_never_two_active_grants(existing_active_grant_id=existing,
                                          existing_grant_status_after=AccessGrantStatus.active,
                                          restored_grant_active=False, rejected=True) == 1
    with pytest.raises(RestoreInvariantError, match="two active grants"):
        assert_never_two_active_grants(existing_active_grant_id=existing,
                                       existing_grant_status_after=AccessGrantStatus.active,
                                       restored_grant_active=True)
    with pytest.raises(RestoreInvariantError, match="ended as part of the restore"):
        assert_never_two_active_grants(existing_active_grant_id=existing,
                                       restored_grant_active=True)
    with pytest.raises(RestoreInvariantError, match="rejected restore"):
        assert_never_two_active_grants(existing_active_grant_id=existing,
                                       existing_grant_status_after=AccessGrantStatus.active,
                                       restored_grant_active=True, rejected=True)


# [utest->req~restore-invariant-14~2]
def test_no_precedence_ranking_between_the_two_grants_exists():
    from nativespeaker.api.auth.restore_invariants import GRANT_PRECEDENCE_RANKING

    assert GRANT_PRECEDENCE_RANKING == ()
