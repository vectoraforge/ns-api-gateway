"""The unclaimed-subscription adoption branch: entry, the two precondition sets, the nine mutation
rules, and the postconditions."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest
import yaml

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreBranch,
    RestoreRejection,
)
from nativespeaker.api.auth.restore_adoption import (
    ADOPTION_PRECONDITION_STEPS,
    ADOPTION_REPORTING_ROUTE,
    ATTACH,
    CREATE,
    CROSS_ACCOUNT_NAMES,
    SHARED_BARRIER_STEP,
    AdoptionError,
    adoption_notifications,
    assert_mutations_inside_locked_transaction,
    assert_precondition_split_and_audit,
    assert_shared_barrier_runs_first,
    entry_destination_active_and_grant_free,
    entry_product_entitled_and_live_verified,
    entry_unclaimed_or_no_row,
    governs_adoption,
    locked_precondition_02_still_unclaimed,
    locked_precondition_03_different_active_grant,
    locked_precondition_04_live_verification_freshness_recheck,
    mutation_01_attach_or_create_canonical_row,
    mutation_02_create_grant_and_usage,
    mutation_03_grant_active_only_if_verified,
    mutation_04_never_mutate_existing_active_grant,
    mutation_05_no_non_subscription_data_moved,
    mutation_06_purchase_row_insert_once_only,
    mutation_07_no_free_or_manual_grant,
    mutation_08_no_external_identity_mutation,
    mutation_09_audit_row_details,
    postcondition_entitlement_follows_destination,
    postcondition_owner_binding_grant,
    postcondition_purchase_row_immutable,
    pre_transaction_precondition_01_live_store_state_verification,
)
from nativespeaker.api.auth.restore_flow import (
    CurrentSubscriptionState,
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
)
from nativespeaker.api.auth.restore_operation import RestoreGrantMutations, RestorePhase
from nativespeaker.api.auth.restore_phases import (
    LiveStoreVerification,
    LockedPhaseLedger,
    LockedState,
    LockTier,
    PreTransactionLedger,
    RestorePhaseError,
)
from nativespeaker.api.models import SubscriptionStatus

DESTINATION = uuid7()
OTHER = uuid7()
EXTERNAL_ID = "2000000123456789"
TOKEN = "11111111-2222-3333-4444-555555555555"
APPLE = StoreProvider.apple
KEY = (APPLE, EXTERNAL_ID)
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
SUBSCRIPTION_ID = uuid7()
VERIFIED = VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID,
                               carried_purchase_uuid=TOKEN)
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def row(*, user_id: UUID | None = None,
        status: SubscriptionStatus = SubscriptionStatus.active,
        bound: UUID | None = None) -> SubscriptionRow:
    return SubscriptionRow(subscription_id=SUBSCRIPTION_ID, provider=APPLE,
                           external_id=EXTERNAL_ID, status=status, tier_id="gold",
                           user_id=user_id, restore_bound_user_id=bound)


def state(**kwargs) -> CurrentSubscriptionState:
    return CurrentSubscriptionState(row=row(**kwargs))


def purchase(*, purchase_user_id: UUID | None = DESTINATION) -> PurchaseRow:
    return PurchaseRow(purchase_id=uuid7(), provider=APPLE, external_id=EXTERNAL_ID,
                       identity_value=TOKEN, purchase_user_id=purchase_user_id)


def locked(*, subscription: CurrentSubscriptionState | None = None,
           purchase_row: PurchaseRow | None = None) -> LockedState:
    return LockedState(subscription=subscription or state(),
                       purchase_row=purchase_row,
                       grant_user_id=None, grant_id=None, destination_active=True,
                       destination_registered=True, identity_linked=True)


def verification(*, subscription_id: UUID | None = SUBSCRIPTION_ID,
                 absent: bool = False,
                 at: datetime = NOW,
                 status: SubscriptionStatus = SubscriptionStatus.active
                 ) -> LiveStoreVerification:
    return LiveStoreVerification(provider=APPLE, external_id=EXTERNAL_ID,
                                 subscription_id=subscription_id, canonical_row_absent=absent,
                                 verified_at=at, status=status)


def locked_ledger() -> LockedPhaseLedger:
    ledger = LockedPhaseLedger()
    ledger.acquire(LockTier.store_subscription_serialization)
    return ledger


# --- The branch that succeeds the cross-account branch ---------------------------------------------


# [utest->req~restore-adoption-succeeds-cross-account-branch~1]
def test_the_cross_account_named_entries_still_govern_the_adoption_path():
    shipped = yaml.safe_load(CONFIG_PATH.read_text())["rate_limits"]
    for name in CROSS_ACCOUNT_NAMES:
        assert governs_adoption(name), name
        assert name in shipped, f"{name} is missing from the shipped configuration"
    assert not governs_adoption("restore_subscription_user")


# [utest->req~restore-adoption-succeeds-cross-account-branch~1]
def test_an_owned_store_subscription_is_never_transferred():
    with pytest.raises(RestoreRejection) as raised:
        entry_unclaimed_or_no_row(state(user_id=OTHER), destination_user_id=DESTINATION)
    assert raised.value.result is AuthEventResult.store_transaction_already_linked


# --- Entry condition ------------------------------------------------------------------------------


# [utest->req~restore-adoption-entry-unclaimed-or-no-row~1]
def test_an_unclaimed_row_enters_the_branch_and_a_missing_row_creates_one():
    assert entry_unclaimed_or_no_row(state(), destination_user_id=DESTINATION) is False
    assert entry_unclaimed_or_no_row(CurrentSubscriptionState(row=None),
                                     destination_user_id=DESTINATION) is True
    with pytest.raises(RestoreRejection):
        entry_unclaimed_or_no_row(state(bound=OTHER), destination_user_id=DESTINATION)
    with pytest.raises(AdoptionError):
        entry_unclaimed_or_no_row(state(user_id=DESTINATION), destination_user_id=DESTINATION)


# [utest->req~restore-adoption-entry-destination-active-no-other-grant~1]
def test_no_grant_source_is_exempt_from_the_different_active_grant_rejection():
    assert entry_destination_active_and_grant_free(
        destination_user_id=DESTINATION, destination_active=True) == DESTINATION
    for source in AccessGrantSource:
        with pytest.raises(RestoreRejection) as raised:
            entry_destination_active_and_grant_free(destination_user_id=DESTINATION,
                                                    destination_active=True,
                                                    active_grant_sources=(source,))
        assert raised.value.result is AuthEventResult.restore_destination_already_entitled


# [utest->req~restore-adoption-entry-destination-active-no-other-grant~1]
def test_an_inactive_destination_is_blocked_and_nothing_is_expired_to_make_room():
    with pytest.raises(RestoreRejection) as raised:
        entry_destination_active_and_grant_free(destination_user_id=DESTINATION,
                                                destination_active=False)
    assert raised.value.result is AuthEventResult.blocked_user
    with pytest.raises(AdoptionError):
        entry_destination_active_and_grant_free(destination_user_id=DESTINATION,
                                                destination_active=True,
                                                expired_to_make_room=(uuid7(),))


# [utest->req~restore-adoption-entry-product-entitled-and-live-verified~1]
def test_entitlement_is_required_at_both_reads_and_the_verification_must_hold():
    assert entry_product_entitled_and_live_verified(
        pre_transaction=state(), locked=state(), verification=verification(),
        recheck_passed=True, adoption_with_creation=False) is SubscriptionStatus.active
    with pytest.raises(RestoreRejection) as pre:
        entry_product_entitled_and_live_verified(
            pre_transaction=state(status=SubscriptionStatus.expired), locked=state(),
            verification=verification(), recheck_passed=True, adoption_with_creation=False)
    assert pre.value.result is AuthEventResult.restore_subscription_not_entitled
    with pytest.raises(RestoreRejection) as inside:
        entry_product_entitled_and_live_verified(
            pre_transaction=state(), locked=state(status=SubscriptionStatus.revoked),
            verification=verification(), recheck_passed=True, adoption_with_creation=False)
    assert inside.value.result is AuthEventResult.restore_subscription_not_entitled


# [utest->req~restore-adoption-entry-product-entitled-and-live-verified~1]
def test_the_creation_path_takes_its_entitlement_from_the_live_verification():
    assert entry_product_entitled_and_live_verified(
        pre_transaction=CurrentSubscriptionState(row=None),
        locked=CurrentSubscriptionState(row=None),
        verification=verification(subscription_id=None, absent=True,
                                  status=SubscriptionStatus.grace_period),
        recheck_passed=True, adoption_with_creation=True) is SubscriptionStatus.grace_period
    with pytest.raises(RestoreRejection) as unrun:
        entry_product_entitled_and_live_verified(
            pre_transaction=state(), locked=state(), adoption_with_creation=False,
            verification=None, recheck_passed=True)
    assert unrun.value.result is AuthEventResult.restore_store_state_unverified
    with pytest.raises(RestoreRejection) as stale:
        entry_product_entitled_and_live_verified(
            pre_transaction=state(), locked=state(), adoption_with_creation=False,
            verification=verification(), recheck_passed=False)
    assert stale.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-adoption-no-user-facing-notification~1]
def test_a_successful_adoption_notifies_nobody():
    assert adoption_notifications() == ADOPTION_REPORTING_ROUTE
    with pytest.raises(AdoptionError):
        adoption_notifications(sent=("push_notification",))


# --- The two precondition sets ---------------------------------------------------------------------


# [utest->req~restore-adoption-precondition-split-and-audit~1]
def test_each_precondition_audits_in_the_phase_it_belongs_to():
    pre = assert_precondition_split_and_audit(
        number=1, result=AuthEventResult.restore_store_state_unverified,
        classification=MovementClassification.unclassified)
    assert (pre.phase, pre.own_transaction, pre.beside_mutation) == (
        RestorePhase.pre_transaction, True, False)
    inside = assert_precondition_split_and_audit(
        number=3, result=AuthEventResult.restore_destination_already_entitled,
        classification=MovementClassification.adoption)
    assert (inside.phase, inside.own_transaction, inside.beside_mutation) == (
        RestorePhase.locked_mutation, False, True)
    with pytest.raises(AdoptionError):
        assert_precondition_split_and_audit(number=9,
                                            result=AuthEventResult.restore_store_state_unverified,
                                            classification=MovementClassification.unclassified)
    with pytest.raises(AdoptionError):
        assert_precondition_split_and_audit(number=1, result=AuthEventResult.succeeded,
                                            classification=MovementClassification.adoption)


# [utest->req~restore-adoption-precondition-split-and-audit~1]
def test_a_failed_precondition_rejects_without_mutation():
    with pytest.raises(Exception):
        assert_precondition_split_and_audit(
            number=1, result=AuthEventResult.restore_store_state_unverified,
            classification=MovementClassification.unclassified, mutation_performed=("access_grants_write",))


# [utest->req~restore-adoption-shared-barrier-runs-first~1]
def test_the_shared_barrier_checks_run_before_the_restore_specific_preconditions():
    assert assert_shared_barrier_runs_first()[0] == SHARED_BARRIER_STEP
    with pytest.raises(AdoptionError):
        assert_shared_barrier_runs_first((ADOPTION_PRECONDITION_STEPS[0], SHARED_BARRIER_STEP))
    with pytest.raises(AdoptionError):
        assert_shared_barrier_runs_first(barrier_admitted=False)


# [utest->req~restore-pre-transaction-precondition-01-live-store-state-verification~1]
def test_precondition_one_records_the_store_subscription_it_covered():
    ledger = PreTransactionLedger()
    recorded = pre_transaction_precondition_01_live_store_state_verification(
        VERIFIED, state(), ledger=ledger, lookup=lambda provider, external: "active", now=NOW)
    assert recorded.key == KEY
    assert recorded.subscription_id == SUBSCRIPTION_ID
    assert recorded.canonical_row_absent is False
    assert recorded.verified_at == NOW


# [utest->req~restore-pre-transaction-precondition-01-live-store-state-verification~1]
def test_precondition_one_notes_the_absent_row_and_rejects_a_non_entitled_or_failing_call():
    absent = pre_transaction_precondition_01_live_store_state_verification(
        VERIFIED, CurrentSubscriptionState(row=None), ledger=PreTransactionLedger(),
        lookup=lambda provider, external: "grace_period", now=NOW)
    assert (absent.canonical_row_absent, absent.subscription_id) == (True, None)

    def boom(provider, external):
        raise TimeoutError("the provider call timed out")

    for lookup in (lambda provider, external: "revoked", boom):
        with pytest.raises(RestoreRejection) as raised:
            pre_transaction_precondition_01_live_store_state_verification(
                VERIFIED, state(), ledger=PreTransactionLedger(), lookup=lookup, now=NOW)
        assert raised.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-locked-precondition-02-still-unclaimed~1]
def test_the_subscription_must_still_be_unclaimed_under_locked_state():
    assert locked_precondition_02_still_unclaimed(
        locked(), ledger=locked_ledger(), destination_user_id=DESTINATION) is True
    with pytest.raises(RestoreRejection) as linked:
        locked_precondition_02_still_unclaimed(
            locked(subscription=state(user_id=OTHER)), ledger=locked_ledger(),
            destination_user_id=DESTINATION)
    assert linked.value.result is AuthEventResult.store_transaction_already_linked
    with pytest.raises(RestoreRejection) as diverged:
        locked_precondition_02_still_unclaimed(
            locked(subscription=state(user_id=DESTINATION)), ledger=locked_ledger(),
            destination_user_id=DESTINATION)
    assert diverged.value.result is AuthEventResult.restore_branch_inconsistent
    with pytest.raises(RestoreRejection) as bound:
        locked_precondition_02_still_unclaimed(
            locked(subscription=state(bound=DESTINATION)), ledger=locked_ledger(),
            destination_user_id=DESTINATION)
    assert bound.value.result is AuthEventResult.store_transaction_already_linked


# [utest->req~restore-locked-precondition-02-still-unclaimed~1]
def test_the_purchase_user_id_is_context_only_and_gets_no_active_user_check():
    with pytest.raises(AdoptionError):
        locked_precondition_02_still_unclaimed(
            locked(purchase_row=purchase(purchase_user_id=OTHER)), ledger=locked_ledger(),
            destination_user_id=DESTINATION, purchase_user_active=False)
    assert locked_precondition_02_still_unclaimed(
        locked(purchase_row=purchase(purchase_user_id=OTHER)), ledger=locked_ledger(),
        destination_user_id=DESTINATION) is True


# [utest->req~restore-locked-precondition-03-different-active-grant~1]
def test_the_locked_different_active_grant_check_is_a_hard_reject_for_every_source():
    assert locked_precondition_03_different_active_grant(
        destination_user_id=DESTINATION) == DESTINATION
    for source in AccessGrantSource:
        with pytest.raises(RestoreRejection) as raised:
            locked_precondition_03_different_active_grant(destination_user_id=DESTINATION,
                                                          active_grant_sources=(source,))
        assert raised.value.result is AuthEventResult.restore_destination_already_entitled
    for verb in ("expire", "replace", "revoke", "mutate"):
        with pytest.raises(AdoptionError):
            locked_precondition_03_different_active_grant(destination_user_id=DESTINATION,
                                                          attempted=(verb,))


# [utest->req~restore-locked-precondition-04-live-verification-freshness-recheck~1]
def test_the_locked_recheck_rejects_a_stale_or_non_corresponding_record():
    assert locked_precondition_04_live_verification_freshness_recheck(
        verification(), ledger=locked_ledger(), locked_key=KEY,
        locked_subscription_id=SUBSCRIPTION_ID, now=NOW + timedelta(seconds=10),
        freshness_seconds=60).status is SubscriptionStatus.active
    stale = (NOW + timedelta(seconds=90), KEY, SUBSCRIPTION_ID)
    wrong_key = (NOW, (StoreProvider.google_play, EXTERNAL_ID), SUBSCRIPTION_ID)
    wrong_row = (NOW, KEY, uuid7())
    for now, key, subscription_id in (stale, wrong_key, wrong_row):
        with pytest.raises(RestoreRejection) as raised:
            locked_precondition_04_live_verification_freshness_recheck(
                verification(), ledger=locked_ledger(), locked_key=key,
                locked_subscription_id=subscription_id, now=now, freshness_seconds=60)
        assert raised.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-locked-precondition-04-live-verification-freshness-recheck~1]
def test_the_locked_recheck_makes_no_provider_call():
    with pytest.raises(RestorePhaseError):
        locked_precondition_04_live_verification_freshness_recheck(
            verification(), ledger=locked_ledger(), locked_key=KEY,
            locked_subscription_id=SUBSCRIPTION_ID, now=NOW, freshness_seconds=60,
            provider_call="apple_live_store_verification")


# --- Mutation rules -------------------------------------------------------------------------------


# [utest->req~restore-adoption-mutation-inside-locked-transaction~1]
def test_adoption_mutates_only_inside_the_lock_with_every_precondition_passed():
    ledger = locked_ledger()
    assert assert_mutations_inside_locked_transaction(
        ledger=ledger, preconditions_passed=(1, 2, 3, 4)) == (1, 2, 3, 4)
    with pytest.raises(AdoptionError):
        assert_mutations_inside_locked_transaction(ledger=ledger, preconditions_passed=(1, 2, 3))
    with pytest.raises(AdoptionError):
        assert_mutations_inside_locked_transaction(ledger=LockedPhaseLedger(),
                                                   preconditions_passed=(1, 2, 3, 4))
    with pytest.raises(RestorePhaseError):
        assert_mutations_inside_locked_transaction(
            ledger=locked_ledger(), preconditions_passed=(1, 2, 3, 4),
            provider_call="google_play_live_store_verification")


# [utest->req~restore-adoption-mutation-01-attach-or-create-canonical-row~1]
def test_an_unclaimed_row_is_attached_in_place_at_its_current_state():
    written = mutation_01_attach_or_create_canonical_row(
        locked(), VERIFIED, destination_user_id=DESTINATION, adoption_with_creation=False)
    assert written.operation == ATTACH
    assert (written.subscription_id, written.user_id) == (SUBSCRIPTION_ID, DESTINATION)
    assert (written.status, written.tier_id) == (SubscriptionStatus.active, "gold")
    with pytest.raises(AdoptionError):
        mutation_01_attach_or_create_canonical_row(
            locked(subscription=state(user_id=OTHER)), VERIFIED,
            destination_user_id=DESTINATION, adoption_with_creation=False)


# [utest->req~restore-adoption-mutation-01-attach-or-create-canonical-row~1]
def test_the_creation_path_writes_the_live_verified_state_and_the_mapped_tier():
    empty = LockedState(subscription=CurrentSubscriptionState(row=None), purchase_row=None,
                        grant_user_id=None, grant_id=None, destination_active=True,
                        destination_registered=True, identity_linked=True)
    written = mutation_01_attach_or_create_canonical_row(
        empty, VERIFIED, destination_user_id=DESTINATION, adoption_with_creation=True,
        live_verified_status=SubscriptionStatus.grace_period,
        store_product_id="com.example.nativespeaker.gold",
        product_tier_mapping={"com.example.nativespeaker.gold": "gold"})
    assert written.operation == CREATE
    assert (written.status, written.tier_id) == (SubscriptionStatus.grace_period, "gold")
    assert (written.provider, written.external_id) == (APPLE, EXTERNAL_ID)
    with pytest.raises(AdoptionError):
        mutation_01_attach_or_create_canonical_row(
            empty, VERIFIED, destination_user_id=DESTINATION, adoption_with_creation=True,
            live_verified_status=SubscriptionStatus.active,
            store_product_id="com.example.nativespeaker.unknown",
            product_tier_mapping={"com.example.nativespeaker.gold": "gold"})


# [utest->req~restore-adoption-mutation-01-attach-or-create-canonical-row~1]
def test_the_first_linkage_names_no_source_user():
    with pytest.raises(AdoptionError):
        mutation_01_attach_or_create_canonical_row(
            locked(), VERIFIED, destination_user_id=DESTINATION, adoption_with_creation=False,
            source_user_id=OTHER)


# [utest->req~restore-adoption-mutation-02-create-grant-and-usage~1]
def test_the_grant_and_its_usage_row_are_created_in_the_same_transaction():
    transaction = object()
    mutations = RestoreGrantMutations()
    mutations.validate()
    grant_id = uuid7()
    created = mutation_02_create_grant_and_usage(
        destination_user_id=DESTINATION, subscription_id=SUBSCRIPTION_ID, tier_id="gold",
        grant_id=grant_id, subscription_transaction=transaction, grant_transaction=transaction,
        usage_transaction=transaction, mutations=mutations)
    assert (created.grant_id, created.usage_grant_id) == (grant_id, grant_id)
    assert created.user_id == DESTINATION
    assert mutations.activated == grant_id
    with pytest.raises(AdoptionError):
        mutation_02_create_grant_and_usage(
            destination_user_id=DESTINATION, subscription_id=SUBSCRIPTION_ID, tier_id="gold",
            grant_id=uuid7(), subscription_transaction=transaction, grant_transaction=transaction,
            usage_transaction=object(), mutations=RestoreGrantMutations())


# [utest->req~restore-adoption-mutation-02-create-grant-and-usage~1]
def test_the_grant_activating_statement_runs_against_a_grant_free_destination():
    transaction = object()
    with pytest.raises(AdoptionError):
        mutation_02_create_grant_and_usage(
            destination_user_id=DESTINATION, subscription_id=SUBSCRIPTION_ID, tier_id="gold",
            grant_id=uuid7(), subscription_transaction=transaction, grant_transaction=transaction,
            usage_transaction=transaction, mutations=RestoreGrantMutations(),
            destination_active_grant_ids=(uuid7(),))


# [utest->req~restore-adoption-mutation-03-grant-active-only-if-verified~1]
def test_the_created_grant_is_active_only_behind_both_confirmations():
    assert mutation_03_grant_active_only_if_verified(
        locked_status=SubscriptionStatus.active, verification=verification(),
        recheck_passed=True, starts_at=NOW, now=NOW) is AccessGrantStatus.active
    with pytest.raises(RestoreRejection) as entitled:
        mutation_03_grant_active_only_if_verified(
            locked_status=SubscriptionStatus.expired, verification=verification(),
            recheck_passed=True, starts_at=NOW, now=NOW)
    assert entitled.value.result is AuthEventResult.restore_subscription_not_entitled
    with pytest.raises(RestoreRejection) as verified:
        mutation_03_grant_active_only_if_verified(
            locked_status=SubscriptionStatus.active, verification=verification(),
            recheck_passed=False, starts_at=NOW, now=NOW)
    assert verified.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-adoption-mutation-03-grant-active-only-if-verified~1]
def test_the_created_grant_has_started_and_carries_no_end():
    with pytest.raises(AdoptionError):
        mutation_03_grant_active_only_if_verified(
            locked_status=SubscriptionStatus.active, verification=verification(),
            recheck_passed=True, starts_at=NOW + timedelta(minutes=1), now=NOW)
    with pytest.raises(AdoptionError):
        mutation_03_grant_active_only_if_verified(
            locked_status=SubscriptionStatus.active, verification=verification(),
            recheck_passed=True, starts_at=NOW, now=NOW, ends_at=NOW + timedelta(days=30))


# [utest->req~restore-adoption-mutation-04-never-mutate-existing-active-grant~1]
def test_no_existing_active_grant_is_touched_by_the_mutation_step():
    assert mutation_04_never_mutate_existing_active_grant() is None
    with pytest.raises(AdoptionError):
        mutation_04_never_mutate_existing_active_grant(existing_active_grant_id=uuid7())
    for verb in ("expire", "replace", "revoke", "mutate"):
        with pytest.raises(AdoptionError):
            mutation_04_never_mutate_existing_active_grant(attempted=(verb,))


# [utest->req~restore-adoption-mutation-05-no-non-subscription-data-moved~1]
def test_adoption_moves_no_non_subscription_data():
    assert "chats" in mutation_05_no_non_subscription_data_moved()
    for touched in ("chats", "messages", "external_identities", "profile_fields",
                    "anonymous_device_grants", "manual_grants",
                    "non_subscription_user_monthly_usage"):
        with pytest.raises(AdoptionError):
            mutation_05_no_non_subscription_data_moved(touched=(touched,))


# [utest->req~restore-adoption-mutation-06-purchase-row-insert-once-only~1]
def test_the_missing_purchase_row_is_written_once_on_the_creation_path_only():
    written = mutation_06_purchase_row_insert_once_only(
        purchase_row=None, verified=VERIFIED, destination_user_id=DESTINATION,
        adoption_with_creation=True, store_transaction_id="1000000",
        store_original_transaction_id=EXTERNAL_ID)
    assert written is not None
    assert written.purchase_user_id == DESTINATION
    assert written.identity_value == TOKEN
    assert written.store_transaction_id == "1000000"
    assert mutation_06_purchase_row_insert_once_only(
        purchase_row=purchase(), verified=VERIFIED, destination_user_id=DESTINATION,
        adoption_with_creation=False) is None
    with pytest.raises(AdoptionError):
        mutation_06_purchase_row_insert_once_only(
            purchase_row=None, verified=VERIFIED, destination_user_id=DESTINATION,
            adoption_with_creation=False)
    for operation in ("update", "revoke", "insert"):
        with pytest.raises(AdoptionError):
            mutation_06_purchase_row_insert_once_only(
                purchase_row=purchase(), verified=VERIFIED, destination_user_id=DESTINATION,
                adoption_with_creation=False, operation=operation)


# [utest->req~restore-adoption-mutation-06-purchase-row-insert-once-only~1]
def test_a_transaction_without_an_echoed_token_gets_an_internal_purchase_uuid():
    written = mutation_06_purchase_row_insert_once_only(
        purchase_row=None,
        verified=VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID),
        destination_user_id=DESTINATION, adoption_with_creation=True)
    assert written is not None
    assert UUID(written.identity_value)


# [utest->req~restore-adoption-mutation-07-no-free-or-manual-grant~1]
def test_adoption_allocates_only_the_subscription_backed_grant():
    assert mutation_07_no_free_or_manual_grant() is AccessGrantSource.subscription
    for source in (AccessGrantSource.anonymous_device_grant,
                   AccessGrantSource.registered_account_grant, AccessGrantSource.manual):
        with pytest.raises(AdoptionError):
            mutation_07_no_free_or_manual_grant(allocated=(source,))


# [utest->req~restore-adoption-mutation-08-no-external-identity-mutation~1]
def test_adoption_writes_nothing_to_external_identities():
    assert mutation_08_no_external_identity_mutation() is None
    for attempted in ("retire", "mark_historical", "update", "delete", "rebind"):
        with pytest.raises(AdoptionError):
            mutation_08_no_external_identity_mutation(attempted=(attempted,))


# [utest->req~restore-adoption-mutation-09-audit-row-details~1]
def test_the_adoption_audit_row_carries_the_full_non_secret_context():
    identity_id = uuid7()
    grant_id = uuid7()
    row_id = uuid7()
    details = mutation_09_audit_row_details(
        result=AuthEventResult.succeeded, operation=AuthOperation.restore_subscription,
        destination_user_id=DESTINATION, destination_external_identity_id=identity_id,
        subscription_id=SUBSCRIPTION_ID, grant_id=grant_id, provider=APPLE,
        external_id=EXTERNAL_ID, purchase_row_id=row_id,
        verification={"provider": "apple", "decision": "entitled"},
        proof_fingerprints=("sha256:abc",))
    assert details["mutation"]["movement_classification"] == "adoption"
    assert details["resolved"]["source_user_id"] is None
    assert details["resolved"]["destination_external_identity_id"] == identity_id
    assert details["mutation"]["subscription_id"] == SUBSCRIPTION_ID
    assert details["mutation"]["access_grant_id"] == grant_id
    assert details["mutation"]["store_purchase_id"] == row_id
    assert details["mutation"]["provider"] == "apple"
    assert details["mutation"]["external_id"] == EXTERNAL_ID
    assert details["verification"]["proof_fingerprints"] == ["sha256:abc"]
    assert details["verification"]["store_state_verification"]["decision"] == "entitled"


# [utest->req~restore-adoption-mutation-09-audit-row-details~1]
def test_the_adoption_audit_row_names_no_source_user_and_no_challenge():
    def audit(**overrides):
        return mutation_09_audit_row_details(
            result=overrides.pop("result", AuthEventResult.succeeded),
            operation=AuthOperation.restore_subscription,
            destination_user_id=DESTINATION, destination_external_identity_id=uuid7(),
            subscription_id=SUBSCRIPTION_ID, grant_id=uuid7(), provider=APPLE,
            external_id=EXTERNAL_ID, purchase_row_id=uuid7(),
            verification=overrides.pop("verification", {"decision": "entitled"}),
            **overrides)

    with pytest.raises(AdoptionError):
        audit(source_user_id=OTHER)
    with pytest.raises(AdoptionError):
        audit(challenge_row_id=uuid7())
    with pytest.raises(AdoptionError):
        audit(verification={"challenge_nonce": "abc"})
    with pytest.raises(AdoptionError):
        audit(result=AuthEventResult.blocked_user)


# --- Postconditions -------------------------------------------------------------------------------


# [utest->req~restore-adoption-postcondition-owner-binding-grant~1]
def test_the_owner_the_binding_and_the_grant_all_name_the_destination():
    assert postcondition_owner_binding_grant(
        canonical_user_id=DESTINATION, restore_bound_user_id=DESTINATION,
        grant_user_id=DESTINATION, destination_user_id=DESTINATION) == DESTINATION
    with pytest.raises(AdoptionError):
        postcondition_owner_binding_grant(canonical_user_id=OTHER,
                                          restore_bound_user_id=DESTINATION,
                                          grant_user_id=DESTINATION,
                                          destination_user_id=DESTINATION)
    with pytest.raises(AdoptionError):
        postcondition_owner_binding_grant(canonical_user_id=DESTINATION,
                                          restore_bound_user_id=None,
                                          grant_user_id=DESTINATION,
                                          destination_user_id=DESTINATION)
    with pytest.raises(Exception):
        postcondition_owner_binding_grant(canonical_user_id=DESTINATION,
                                          restore_bound_user_id=DESTINATION,
                                          grant_user_id=OTHER,
                                          destination_user_id=DESTINATION)


# [utest->req~restore-adoption-postcondition-entitlement-follows-destination~1]
def test_later_restores_are_same_account_for_the_destination_and_rejected_for_anyone_else():
    assert postcondition_entitlement_follows_destination(
        destination_user_id=DESTINATION,
        requester_user_id=DESTINATION) is RestoreBranch.same_account
    with pytest.raises(RestoreRejection) as raised:
        postcondition_entitlement_follows_destination(destination_user_id=DESTINATION,
                                                      requester_user_id=OTHER)
    assert raised.value.result is AuthEventResult.store_transaction_already_linked
    with pytest.raises(AdoptionError):
        postcondition_entitlement_follows_destination(destination_user_id=DESTINATION,
                                                      requester_user_id=OTHER,
                                                      requester_holds_grant=True)


# [utest->req~restore-adoption-postcondition-purchase-row-immutable~1]
def test_the_resolved_purchase_row_is_unchanged_and_keeps_its_purchase_user():
    before = purchase(purchase_user_id=OTHER)
    assert postcondition_purchase_row_immutable(before=before, after=before) == OTHER
    changed = PurchaseRow(purchase_id=before.purchase_id, provider=APPLE,
                          external_id=EXTERNAL_ID, identity_value=TOKEN,
                          purchase_user_id=DESTINATION)
    with pytest.raises(AdoptionError):
        postcondition_purchase_row_immutable(before=before, after=changed)
