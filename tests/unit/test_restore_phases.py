"""Restore's nineteen common steps: the eight pre-transaction steps that hold no lock, and the
eleven locked-phase steps that make no provider call."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.audit import AttemptPhase, AuthEventResult
from nativespeaker.api.auth.invariants import DevicePlatform, StoreProvider
from nativespeaker.api.auth.proof_restore import VerifiedStoreProof
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreAuditContext,
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
from nativespeaker.api.auth.restore_operation import RestoreGrantMutations, RestorePhase
from nativespeaker.api.auth.restore_phases import (
    LIVE_VERIFICATION_STEPS,
    LOCK_ORDER,
    MAX_LOCKED_RETRIES,
    LiveStoreVerification,
    LockedPhaseLedger,
    LockedState,
    LockTier,
    PreTransactionLedger,
    RestoreContention,
    RestorePhaseError,
    assert_barrier_and_audit_scope,
    assert_locks_not_held,
    assert_no_provider_calls,
    creation_purchase_uuid,
    step_01_reverify_proof,
    step_02_resolve_subscription,
    step_03_extract_purchase_uuid,
    step_04_resolve_purchase_row,
    step_05_determine_branch,
    step_06_same_account_skips_live_verification,
    step_07_adoption_entitlement_short_circuit,
    step_08_live_store_state_verification,
    step_09_acquire_locks_and_retry,
    step_10_re_resolve_locked_state,
    step_11_confirm_product_entitled,
    step_12_confirm_canonical_row_correspondence,
    step_13_confirm_purchase_row,
    step_14_confirm_destination_and_binding,
    step_15_owner_grant_agreement,
    step_16_resolve_outcome_and_divergence,
    step_17_live_verification_freshness,
    step_18_branch_mutation_and_binding,
    step_19_write_audit_row,
)
from nativespeaker.api.models import SubscriptionStatus

DESTINATION = uuid7()
OTHER = uuid7()
EXTERNAL_ID = "2000000123456789"
TOKEN = "11111111-2222-3333-4444-555555555555"
APPLE = StoreProvider.apple
KEY = (APPLE, EXTERNAL_ID)
APPLE_CHECKS = ("jws_certificate_chain", "bundle_id", "product_id", "environment")
VERIFIED = VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID,
                               carried_purchase_uuid=TOKEN)
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
PROOF_BODY = {"restore_proof": "signed.storekit.tx"}


def fake_verifier(provider: StoreProvider, artifact: str) -> VerifiedStoreProof:
    del artifact
    return VerifiedStoreProof(provider=provider, external_id=EXTERNAL_ID,
                              purchase_uuid=UUID(TOKEN))


def subscription(*, user_id: UUID | None = None,
                 status: SubscriptionStatus = SubscriptionStatus.active,
                 bound: UUID | None = None,
                 subscription_id: UUID | None = None) -> SubscriptionRow:
    return SubscriptionRow(subscription_id=subscription_id or uuid7(), provider=APPLE,
                           external_id=EXTERNAL_ID, status=status, tier_id="gold",
                           user_id=user_id, restore_bound_user_id=bound)


def purchase(*, identity_value: str = TOKEN) -> PurchaseRow:
    return PurchaseRow(purchase_id=uuid7(), provider=APPLE, external_id=EXTERNAL_ID,
                       identity_value=identity_value)


def locked(*, row: SubscriptionRow | None,
           purchase_row: PurchaseRow | None = None,
           grant_user_id: UUID | None = None,
           destination_active: bool = True,
           destination_registered: bool = True,
           identity_linked: bool = True) -> LockedState:
    return LockedState(subscription=CurrentSubscriptionState(row),
                       purchase_row=purchase_row,
                       grant_user_id=grant_user_id,
                       grant_id=None,
                       destination_active=destination_active,
                       destination_registered=destination_registered,
                       identity_linked=identity_linked)


class TestPreTransactionLocksNotHeld:

    def test_no_restore_mutation_lock_is_held_while_the_steps_run(self):
        # [utest->req~restore-pre-transaction-locks-not-held~1]
        ledger = PreTransactionLedger()
        assert assert_locks_not_held(ledger) is ledger
        ledger.locks_held = True
        with pytest.raises(RestorePhaseError):
            assert_locks_not_held(ledger)

    def test_the_steps_apply_to_both_branches(self):
        # [utest->req~restore-pre-transaction-locks-not-held~1]
        for branch in RestoreBranch:
            assert assert_locks_not_held(PreTransactionLedger(), branch=branch) is not None

    def test_every_pre_transaction_step_refuses_to_run_under_a_lock(self):
        # [utest->req~restore-pre-transaction-locks-not-held~1]
        ledger = PreTransactionLedger(locks_held=True)
        with pytest.raises(RestorePhaseError):
            step_02_resolve_subscription([], VERIFIED, ledger=ledger)
        with pytest.raises(RestorePhaseError):
            step_04_resolve_purchase_row([], VERIFIED, ledger=ledger)


class TestPreTransactionBarrierAndAuditScope:

    def test_the_barrier_admits_the_request_before_step_one(self):
        # [utest->req~restore-pre-transaction-barrier-and-audit-scope~1]
        with pytest.raises(RestorePhaseError):
            assert_barrier_and_audit_scope(PreTransactionLedger(barrier_admitted=False))

    def test_a_rejection_writes_its_row_in_its_own_rejection_transaction(self):
        # [utest->req~restore-pre-transaction-barrier-and-audit-scope~1]
        ledger = PreTransactionLedger()
        assert_barrier_and_audit_scope(ledger, rejected=True, rejection_transaction=object())
        assert ledger.audit_rows == 1
        with pytest.raises(RestorePhaseError):
            assert_barrier_and_audit_scope(PreTransactionLedger(), rejected=True,
                                           rejection_transaction=None)

    def test_perform_no_mutation_means_no_restore_mutation_not_no_audit_write(self):
        # [utest->req~restore-pre-transaction-barrier-and-audit-scope~1]
        ledger = PreTransactionLedger()
        ledger.mutate("access_grants_write")
        with pytest.raises(RestorePhaseError):
            assert_barrier_and_audit_scope(ledger, rejected=True,
                                           rejection_transaction=object())


class TestStep01ReverifyProof:

    def test_the_proof_is_re_verified_server_side(self):
        # [utest->req~restore-pre-transaction-step-01-reverify-proof~1]
        ledger = PreTransactionLedger()
        verified = step_01_reverify_proof(DevicePlatform.ios, PROOF_BODY, fake_verifier,
                                          performed_checks=APPLE_CHECKS, ledger=ledger)
        assert verified.external_id == EXTERNAL_ID
        assert ledger.steps == ["01_reverify_proof"]

    def test_it_runs_before_branch_determination(self):
        # [utest->req~restore-pre-transaction-step-01-reverify-proof~1]
        with pytest.raises(RestorePhaseError):
            step_01_reverify_proof(DevicePlatform.ios, PROOF_BODY, fake_verifier,
                                   performed_checks=APPLE_CHECKS,
                                   ledger=PreTransactionLedger(),
                                   branch=RestoreBranch.adoption)

    def test_an_unverifiable_proof_rejects_before_any_resolution(self):
        # [utest->req~restore-pre-transaction-step-01-reverify-proof~1]
        with pytest.raises(Exception):
            step_01_reverify_proof(DevicePlatform.ios, PROOF_BODY, fake_verifier,
                                   performed_checks=("bundle_id",),
                                   ledger=PreTransactionLedger())


class TestStep02ResolveSubscription:

    def test_the_canonical_row_is_read_without_locking_it(self):
        # [utest->req~restore-pre-transaction-step-02-resolve-subscription~1]
        row = subscription(user_id=DESTINATION)
        state, creating = step_02_resolve_subscription([row], VERIFIED,
                                                       ledger=PreTransactionLedger())
        assert state.row is row and creating is False
        with pytest.raises(RestorePhaseError):
            step_02_resolve_subscription([row], VERIFIED, ledger=PreTransactionLedger(),
                                         locking=True)

    def test_a_missing_row_marks_adoption_with_creation_rather_than_rejecting(self):
        # [utest->req~restore-pre-transaction-step-02-resolve-subscription~1]
        state, creating = step_02_resolve_subscription([], VERIFIED,
                                                       ledger=PreTransactionLedger())
        assert state.row is None and creating is True


class TestStep03ExtractPurchaseUuid:

    def test_a_carried_uuid_is_extracted_from_the_verified_transaction(self):
        # [utest->req~restore-pre-transaction-step-03-extract-purchase-uuid~1]
        assert step_03_extract_purchase_uuid(VERIFIED, ledger=PreTransactionLedger()) == TOKEN

    def test_a_transaction_carrying_none_is_not_rejected(self):
        # [utest->req~restore-pre-transaction-step-03-extract-purchase-uuid~1]
        bare = VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID)
        assert step_03_extract_purchase_uuid(bare, ledger=PreTransactionLedger()) is None
        generated = creation_purchase_uuid(bare)
        assert generated and generated != TOKEN


class TestStep04ResolvePurchaseRow:

    def test_the_row_is_resolved_by_provider_and_external_id_without_locking(self):
        # [utest->req~restore-pre-transaction-step-04-resolve-purchase-row~1]
        row = purchase()
        assert step_04_resolve_purchase_row([row], VERIFIED,
                                            ledger=PreTransactionLedger()) is row
        with pytest.raises(RestorePhaseError):
            step_04_resolve_purchase_row([row], VERIFIED, ledger=PreTransactionLedger(),
                                         locking=True)

    def test_a_missing_row_is_no_rejection(self):
        # [utest->req~restore-pre-transaction-step-04-resolve-purchase-row~1]
        assert step_04_resolve_purchase_row([], VERIFIED,
                                            ledger=PreTransactionLedger()) is None

    def test_a_differing_recorded_attribution_rejects(self):
        # [utest->req~restore-pre-transaction-step-04-resolve-purchase-row~1]
        with pytest.raises(RestoreRejection) as refused:
            step_04_resolve_purchase_row(
                [purchase(identity_value="99999999-2222-3333-4444-555555555555")],
                VERIFIED, ledger=PreTransactionLedger())
        assert refused.value.result is AuthEventResult.restore_purchase_uuid_mismatch


class TestStep05DetermineBranch:

    def test_the_owner_read_in_step_two_selects_the_branch(self):
        # [utest->req~restore-pre-transaction-step-05-determine-branch~1]
        same = step_05_determine_branch(
            CurrentSubscriptionState(subscription(user_id=DESTINATION)),
            destination_user_id=DESTINATION, ledger=PreTransactionLedger())
        assert same is RestoreBranch.same_account
        adoption = step_05_determine_branch(
            CurrentSubscriptionState(subscription(user_id=None)),
            destination_user_id=DESTINATION, ledger=PreTransactionLedger())
        assert adoption is RestoreBranch.adoption
        creating = step_05_determine_branch(
            CurrentSubscriptionState(None),
            destination_user_id=DESTINATION, ledger=PreTransactionLedger())
        assert creating is RestoreBranch.adoption

    def test_a_different_linked_account_rejects_as_already_linked(self):
        # [utest->req~restore-pre-transaction-step-05-determine-branch~1]
        with pytest.raises(RestoreRejection) as refused:
            step_05_determine_branch(CurrentSubscriptionState(subscription(user_id=OTHER)),
                                     destination_user_id=DESTINATION,
                                     ledger=PreTransactionLedger())
        assert refused.value.result is AuthEventResult.store_transaction_already_linked

    def test_an_inactive_linked_source_audits_as_source_user_inactive(self):
        # [utest->req~restore-pre-transaction-step-05-determine-branch~1]
        with pytest.raises(RestoreRejection) as refused:
            step_05_determine_branch(CurrentSubscriptionState(subscription(user_id=OTHER)),
                                     destination_user_id=DESTINATION,
                                     ledger=PreTransactionLedger(),
                                     source_user_active=False)
        assert refused.value.result is AuthEventResult.restore_source_user_inactive

    def test_a_binding_to_another_account_rejects_even_on_an_unclaimed_row(self):
        # [utest->req~restore-pre-transaction-step-05-determine-branch~1]
        with pytest.raises(RestoreRejection) as refused:
            step_05_determine_branch(
                CurrentSubscriptionState(subscription(user_id=None, bound=OTHER)),
                destination_user_id=DESTINATION, ledger=PreTransactionLedger())
        assert refused.value.result is AuthEventResult.store_transaction_already_linked


class TestStep06SameAccountSkipsLiveVerification:

    def test_same_account_skips_steps_seven_and_eight(self):
        # [utest->req~restore-pre-transaction-step-06-same-account-skips-live-verification~1]
        assert step_06_same_account_skips_live_verification(
            RestoreBranch.same_account, ledger=PreTransactionLedger()) == LIVE_VERIFICATION_STEPS
        assert LIVE_VERIFICATION_STEPS == (7, 8)

    def test_adoption_skips_nothing(self):
        # [utest->req~restore-pre-transaction-step-06-same-account-skips-live-verification~1]
        assert step_06_same_account_skips_live_verification(
            RestoreBranch.adoption, ledger=PreTransactionLedger()) == ()

    def test_same_account_makes_no_provider_call(self):
        # [utest->req~restore-pre-transaction-step-06-same-account-skips-live-verification~1]
        called: list[str] = []
        assert step_08_live_store_state_verification(
            VERIFIED, CurrentSubscriptionState(subscription(user_id=DESTINATION)),
            branch=RestoreBranch.same_account, ledger=PreTransactionLedger(),
            lookup=lambda provider, external_id: called.append("call"), now=NOW) is None
        assert called == []


class TestStep07AdoptionEntitlementShortCircuit:

    def test_an_entitled_row_passes_the_short_circuit(self):
        # [utest->req~restore-pre-transaction-step-07-adoption-entitlement-short-circuit~1]
        assert step_07_adoption_entitlement_short_circuit(
            CurrentSubscriptionState(subscription(status=SubscriptionStatus.grace_period)),
            branch=RestoreBranch.adoption, ledger=PreTransactionLedger()) is True

    def test_a_non_entitled_row_rejects_before_any_provider_call(self):
        # [utest->req~restore-pre-transaction-step-07-adoption-entitlement-short-circuit~1]
        for status in (SubscriptionStatus.expired, SubscriptionStatus.revoked,
                       SubscriptionStatus.billing_retry):
            with pytest.raises(RestoreRejection) as refused:
                step_07_adoption_entitlement_short_circuit(
                    CurrentSubscriptionState(subscription(status=status)),
                    branch=RestoreBranch.adoption, ledger=PreTransactionLedger())
            assert refused.value.result is AuthEventResult.restore_subscription_not_entitled

    def test_the_creation_path_has_no_row_to_short_circuit_on(self):
        # [utest->req~restore-pre-transaction-step-07-adoption-entitlement-short-circuit~1]
        assert step_07_adoption_entitlement_short_circuit(
            CurrentSubscriptionState(None), branch=RestoreBranch.adoption,
            ledger=PreTransactionLedger()) is False

    def test_same_account_does_not_run_it(self):
        # [utest->req~restore-pre-transaction-step-07-adoption-entitlement-short-circuit~1]
        ledger = PreTransactionLedger()
        assert step_07_adoption_entitlement_short_circuit(
            CurrentSubscriptionState(subscription(status=SubscriptionStatus.expired)),
            branch=RestoreBranch.same_account, ledger=ledger) is False
        assert ledger.steps == []


class TestStep08LiveStoreStateVerification:

    def test_an_entitled_live_state_is_recorded_with_its_subject_and_timestamp(self):
        # [utest->req~restore-pre-transaction-step-08-live-store-state-verification~1]
        row = subscription(user_id=None)
        record = step_08_live_store_state_verification(
            VERIFIED, CurrentSubscriptionState(row), branch=RestoreBranch.adoption,
            ledger=PreTransactionLedger(),
            lookup=lambda provider, external_id: SubscriptionStatus.active, now=NOW)
        assert record is not None
        assert record.key == KEY
        assert record.subscription_id == row.subscription_id
        assert record.canonical_row_absent is False
        assert record.verified_at == NOW

    def test_the_creation_path_notes_the_absence_of_a_canonical_row(self):
        # [utest->req~restore-pre-transaction-step-08-live-store-state-verification~1]
        record = step_08_live_store_state_verification(
            VERIFIED, CurrentSubscriptionState(None), branch=RestoreBranch.adoption,
            ledger=PreTransactionLedger(),
            lookup=lambda provider, external_id: SubscriptionStatus.active, now=NOW)
        assert record is not None
        assert record.subscription_id is None
        assert record.canonical_row_absent is True

    def test_a_non_entitled_or_failed_lookup_rejects_as_unverified(self):
        # [utest->req~restore-pre-transaction-step-08-live-store-state-verification~1]
        def timing_out(provider, external_id):
            raise TimeoutError("the store did not answer")

        for lookup in (lambda p, e: None,
                       lambda p, e: "revoked",
                       lambda p, e: SubscriptionStatus.billing_retry,
                       timing_out):
            with pytest.raises(RestoreRejection) as refused:
                step_08_live_store_state_verification(
                    VERIFIED, CurrentSubscriptionState(None), branch=RestoreBranch.adoption,
                    ledger=PreTransactionLedger(), lookup=lookup, now=NOW)
            assert refused.value.result is AuthEventResult.restore_store_state_unverified

    def test_the_lookup_takes_only_server_verified_inputs_and_backend_credentials(self):
        # [utest->req~restore-pre-transaction-step-08-live-store-state-verification~1]
        with pytest.raises(RestorePhaseError):
            step_08_live_store_state_verification(
                VERIFIED, CurrentSubscriptionState(None), branch=RestoreBranch.adoption,
                ledger=PreTransactionLedger(),
                lookup=lambda p, e: SubscriptionStatus.active, now=NOW,
                backend_held_credentials=False)
        with pytest.raises(RestorePhaseError):
            step_08_live_store_state_verification(
                VERIFIED, CurrentSubscriptionState(None), branch=RestoreBranch.adoption,
                ledger=PreTransactionLedger(),
                lookup=lambda p, e: SubscriptionStatus.active, now=NOW,
                input_sources=["client_supplied_purchase_token"])


class TestLockedPhaseMakesNoProviderCall:

    def test_a_provider_call_under_the_locks_is_refused(self):
        # [utest->req~restore-locked-phase-no-provider-calls~1]
        ledger = LockedPhaseLedger()
        assert assert_no_provider_calls(ledger, None) is None
        ledger.acquire(LockTier.store_subscription_serialization)
        for call in ("apple_get_transaction_info", "play_subscriptionsv2_get"):
            with pytest.raises(RestorePhaseError):
                assert_no_provider_calls(ledger, call)

    def test_the_locked_steps_refuse_a_provider_call(self):
        # [utest->req~restore-locked-phase-no-provider-calls~1]
        ledger = LockedPhaseLedger()
        ledger.acquire(LockTier.store_subscription_serialization)
        with pytest.raises(RestorePhaseError):
            step_10_re_resolve_locked_state(ledger=ledger, subscriptions=[], purchases=[],
                                            verified=VERIFIED,
                                            provider_call="play_subscriptionsv2_get")


class TestStep09AcquireLocksAndRetry:

    def test_the_locks_are_taken_in_the_deterministic_order(self):
        # [utest->req~restore-locked-step-09-acquire-locks-and-retry~1]
        ledger = LockedPhaseLedger()
        row = subscription(user_id=DESTINATION)
        grants = [uuid7(), uuid7()]
        step_09_acquire_locks_and_retry(ledger=ledger, store_subscription_key=KEY,
                                        canonical_row=row, grant_ids=grants,
                                        purchase_row=purchase(), run=lambda held: "done")
        assert ledger.tiers == list(LOCK_ORDER)
        assert list(ledger.locks.grant_locks) == sorted(grants)
        assert list(ledger.locks.usage_locks) == sorted(grants)

    def test_the_creation_path_takes_the_serialization_without_a_canonical_row(self):
        # [utest->req~restore-locked-step-09-acquire-locks-and-retry~1]
        ledger = LockedPhaseLedger()
        step_09_acquire_locks_and_retry(ledger=ledger, store_subscription_key=KEY,
                                        canonical_row=None, grant_ids=[],
                                        purchase_row=None, run=lambda held: None)
        assert ledger.tiers == [LockTier.store_subscription_serialization]

    def test_contention_is_retried_exactly_once_and_re_resolves(self):
        # [utest->req~restore-locked-step-09-acquire-locks-and-retry~1]
        runs: list[int] = []

        def flaky(held: LockedPhaseLedger):
            runs.append(held.attempts)
            if len(runs) == 1:
                raise RestoreContention("deadlock detected")
            return "settled"

        ledger = LockedPhaseLedger()
        assert step_09_acquire_locks_and_retry(ledger=ledger, store_subscription_key=KEY,
                                               canonical_row=subscription(user_id=DESTINATION),
                                               grant_ids=[], purchase_row=None,
                                               run=flaky) == "settled"
        assert runs == [1, 2]
        assert ledger.attempts == MAX_LOCKED_RETRIES + 1

    def test_the_rolled_back_attempt_still_leaves_exactly_one_audit_row(self):
        # [utest->req~restore-locked-step-09-acquire-locks-and-retry~1]
        transaction = object()

        def writes_then_fails(held: LockedPhaseLedger):
            held.audit.record(phase=AttemptPhase.success,
                              result=AuthEventResult.succeeded,
                              audit_transaction=transaction,
                              branch=RestoreBranch.same_account,
                              mutation_transaction=transaction)
            if held.attempts == 1:
                raise RestoreContention("lock wait timeout")
            return held.audit.rows

        ledger = LockedPhaseLedger()
        rows = step_09_acquire_locks_and_retry(ledger=ledger, store_subscription_key=KEY,
                                               canonical_row=None, grant_ids=[],
                                               purchase_row=None, run=writes_then_fails)
        assert len(rows) == 1

    def test_persistent_contention_surfaces_as_transient_contention(self):
        # [utest->req~restore-locked-step-09-acquire-locks-and-retry~1]
        def always_contends(held: LockedPhaseLedger):
            raise RestoreContention("serialization failure")

        with pytest.raises(RestoreContention):
            step_09_acquire_locks_and_retry(ledger=LockedPhaseLedger(),
                                            store_subscription_key=KEY, canonical_row=None,
                                            grant_ids=[], purchase_row=None,
                                            run=always_contends)

    def test_the_restore_path_adds_no_other_contention_management(self):
        # [utest->req~restore-locked-step-09-acquire-locks-and-retry~1]
        with pytest.raises(RestorePhaseError):
            step_09_acquire_locks_and_retry(
                ledger=LockedPhaseLedger(), store_subscription_key=KEY, canonical_row=None,
                grant_ids=[], purchase_row=None, run=lambda held: None,
                added_contention_management=["restore_job_queue"])

    def test_no_user_row_lock_runs_ahead_of_the_grant_locks(self):
        # [utest->req~restore-locked-step-09-acquire-locks-and-retry~1]
        from nativespeaker.api.auth.locks import LockOrderError

        ledger = LockedPhaseLedger()
        step_09_acquire_locks_and_retry(ledger=ledger, store_subscription_key=KEY,
                                        canonical_row=None, grant_ids=[uuid7()],
                                        purchase_row=None, run=lambda held: None)
        with pytest.raises(LockOrderError):
            ledger.locks.lock_user(DESTINATION)


class TestStep10ReResolveLockedState:

    def test_every_piece_of_state_comes_from_the_locked_rows(self):
        # [utest->req~restore-locked-step-10-re-resolve-locked-state~1]
        row, row_purchase = subscription(user_id=DESTINATION), purchase()
        state = step_10_re_resolve_locked_state(ledger=LockedPhaseLedger(),
                                                subscriptions=[row], purchases=[row_purchase],
                                                verified=VERIFIED, grant_user_id=DESTINATION)
        assert state.subscription.row is row
        assert state.purchase_row is row_purchase
        assert state.grant_user_id == DESTINATION


class TestStep11ConfirmProductEntitled:

    def test_locked_state_must_still_be_product_entitled(self):
        # [utest->req~restore-locked-step-11-confirm-product-entitled~1]
        entitled = locked(row=subscription(status=SubscriptionStatus.active))
        assert step_11_confirm_product_entitled(
            entitled, ledger=LockedPhaseLedger()) is SubscriptionStatus.active
        for status in (SubscriptionStatus.expired, SubscriptionStatus.revoked):
            with pytest.raises(RestoreRejection) as refused:
                step_11_confirm_product_entitled(locked(row=subscription(status=status)),
                                                 ledger=LockedPhaseLedger())
            assert refused.value.result is AuthEventResult.restore_subscription_not_entitled

    def test_the_creation_path_checks_the_state_the_row_is_created_at(self):
        # [utest->req~restore-locked-step-11-confirm-product-entitled~1]
        assert step_11_confirm_product_entitled(
            locked(row=None), ledger=LockedPhaseLedger(),
            creation_status=SubscriptionStatus.active) is SubscriptionStatus.active
        with pytest.raises(RestoreRejection):
            step_11_confirm_product_entitled(locked(row=None), ledger=LockedPhaseLedger(),
                                             creation_status=SubscriptionStatus.expired)


class TestStep12ConfirmCanonicalRowCorrespondence:

    def test_the_same_row_still_stands_behind_the_store_subscription(self):
        # [utest->req~restore-locked-step-12-confirm-canonical-row-correspondence~1]
        row = subscription(user_id=DESTINATION)
        assert step_12_confirm_canonical_row_correspondence(
            locked(row=row), ledger=LockedPhaseLedger(),
            pre_transaction_subscription_id=row.subscription_id,
            adoption_with_creation=False) is row

    def test_a_vanished_or_different_row_rejects_as_unlinked(self):
        # [utest->req~restore-locked-step-12-confirm-canonical-row-correspondence~1]
        row = subscription(user_id=DESTINATION)
        for state, pre in ((locked(row=None), row.subscription_id),
                           (locked(row=row), uuid7())):
            with pytest.raises(RestoreRejection) as refused:
                step_12_confirm_canonical_row_correspondence(
                    state, ledger=LockedPhaseLedger(),
                    pre_transaction_subscription_id=pre, adoption_with_creation=False)
            assert refused.value.result is AuthEventResult.restore_subscription_unlinked

    def test_a_row_that_appeared_becomes_the_resolved_row_on_the_creation_path(self):
        # [utest->req~restore-locked-step-12-confirm-canonical-row-correspondence~1]
        appeared = subscription(user_id=None)
        assert step_12_confirm_canonical_row_correspondence(
            locked(row=appeared), ledger=LockedPhaseLedger(),
            pre_transaction_subscription_id=None, adoption_with_creation=True) is appeared
        assert step_12_confirm_canonical_row_correspondence(
            locked(row=None), ledger=LockedPhaseLedger(),
            pre_transaction_subscription_id=None, adoption_with_creation=True) is None


class TestStep13ConfirmPurchaseRow:

    def test_a_present_row_with_matching_attribution_passes(self):
        # [utest->req~restore-locked-step-13-confirm-purchase-row~1]
        row = purchase()
        assert step_13_confirm_purchase_row(locked(row=subscription(), purchase_row=row),
                                            VERIFIED, ledger=LockedPhaseLedger(),
                                            creating_purchase_row=False) is row

    def test_a_missing_row_rejects_as_purchase_uuid_unknown(self):
        # [utest->req~restore-locked-step-13-confirm-purchase-row~1]
        with pytest.raises(RestoreRejection) as refused:
            step_13_confirm_purchase_row(locked(row=subscription()), VERIFIED,
                                         ledger=LockedPhaseLedger(),
                                         creating_purchase_row=False)
        assert refused.value.result is AuthEventResult.restore_purchase_uuid_unknown

    def test_a_changed_attribution_rejects_as_mismatch(self):
        # [utest->req~restore-locked-step-13-confirm-purchase-row~1]
        drifted = purchase(identity_value="99999999-2222-3333-4444-555555555555")
        with pytest.raises(RestoreRejection) as refused:
            step_13_confirm_purchase_row(locked(row=subscription(), purchase_row=drifted),
                                         VERIFIED, ledger=LockedPhaseLedger(),
                                         creating_purchase_row=False)
        assert refused.value.result is AuthEventResult.restore_purchase_uuid_mismatch

    def test_the_creation_path_accepts_no_row_and_adopts_one_that_appeared(self):
        # [utest->req~restore-locked-step-13-confirm-purchase-row~1]
        assert step_13_confirm_purchase_row(locked(row=None), VERIFIED,
                                            ledger=LockedPhaseLedger(),
                                            creating_purchase_row=True) is None
        appeared = purchase()
        assert step_13_confirm_purchase_row(locked(row=None, purchase_row=appeared), VERIFIED,
                                            ledger=LockedPhaseLedger(),
                                            creating_purchase_row=True) is appeared


class TestStep14ConfirmDestinationAndBinding:

    def test_an_active_linked_registered_destination_passes(self):
        # [utest->req~restore-locked-step-14-confirm-destination-and-binding~1]
        assert step_14_confirm_destination_and_binding(
            locked(row=subscription(user_id=DESTINATION, bound=DESTINATION)),
            ledger=LockedPhaseLedger(), destination_user_id=DESTINATION) == DESTINATION

    def test_an_inactive_destination_rejects_as_blocked_user(self):
        # [utest->req~restore-locked-step-14-confirm-destination-and-binding~1]
        with pytest.raises(RestoreRejection) as refused:
            step_14_confirm_destination_and_binding(
                locked(row=subscription(), destination_active=False),
                ledger=LockedPhaseLedger(), destination_user_id=DESTINATION)
        assert refused.value.result is AuthEventResult.blocked_user

    def test_an_unlinked_identity_rejects(self):
        # [utest->req~restore-locked-step-14-confirm-destination-and-binding~1]
        with pytest.raises(RestoreRejection):
            step_14_confirm_destination_and_binding(
                locked(row=subscription(), identity_linked=False),
                ledger=LockedPhaseLedger(), destination_user_id=DESTINATION)

    def test_an_anonymous_destination_rejects_under_registered_destination(self):
        # [utest->req~restore-locked-step-14-confirm-destination-and-binding~1]
        with pytest.raises(RestoreRejection) as refused:
            step_14_confirm_destination_and_binding(
                locked(row=subscription(), destination_registered=False),
                ledger=LockedPhaseLedger(), destination_user_id=DESTINATION)
        assert refused.value.result is AuthEventResult.restore_destination_anonymous

    def test_a_binding_to_another_account_rejects_as_already_linked(self):
        # [utest->req~restore-locked-step-14-confirm-destination-and-binding~1]
        with pytest.raises(RestoreRejection) as refused:
            step_14_confirm_destination_and_binding(
                locked(row=subscription(bound=OTHER)),
                ledger=LockedPhaseLedger(), destination_user_id=DESTINATION)
        assert refused.value.result is AuthEventResult.store_transaction_already_linked


class TestStep15OwnerGrantAgreement:

    def test_an_agreeing_owner_pair_passes(self):
        # [utest->req~restore-locked-step-15-owner-grant-agreement~1]
        state = locked(row=subscription(user_id=DESTINATION), grant_user_id=DESTINATION)
        assert step_15_owner_grant_agreement(state, ledger=LockedPhaseLedger()) == DESTINATION

    def test_a_divergent_owner_pair_rejects_and_classifies_unclassified(self):
        # [utest->req~restore-locked-step-15-owner-grant-agreement~1]
        locked_transaction = object()
        state = locked(row=subscription(user_id=DESTINATION), grant_user_id=OTHER)
        with pytest.raises(RestoreRejection) as refused:
            step_15_owner_grant_agreement(state, ledger=LockedPhaseLedger())
        assert refused.value.result \
            is AuthEventResult.restore_subscription_grant_owner_mismatch
        ledger = LockedPhaseLedger()
        classification = step_19_write_audit_row(
            ledger=ledger, phase=RestorePhase.locked_mutation,
            result=AuthEventResult.restore_subscription_grant_owner_mismatch,
            branch=RestoreBranch.same_account, transaction=locked_transaction,
            mutation_transaction=locked_transaction)
        assert classification is MovementClassification.unclassified

    def test_it_runs_before_the_source_check_and_before_any_mutation(self):
        # [utest->req~restore-locked-step-15-owner-grant-agreement~1]
        state = locked(row=subscription(user_id=DESTINATION), grant_user_id=DESTINATION)
        with pytest.raises(RestorePhaseError):
            step_15_owner_grant_agreement(state, ledger=LockedPhaseLedger(),
                                          source_user_checked=True)
        with pytest.raises(RestorePhaseError):
            step_15_owner_grant_agreement(state, ledger=LockedPhaseLedger(),
                                          mutations_performed=["access_grants_write"])


class TestStep16ResolveOutcomeAndDivergence:

    def test_the_locked_outcome_must_match_the_pre_transaction_determination(self):
        # [utest->req~restore-locked-step-16-resolve-outcome-and-divergence~1]
        state = locked(row=subscription(user_id=DESTINATION))
        assert step_16_resolve_outcome_and_divergence(
            state, ledger=LockedPhaseLedger(), destination_user_id=DESTINATION,
            pre_transaction_branch=RestoreBranch.same_account) is RestoreBranch.same_account

    def test_a_divergence_rejects_as_branch_inconsistent(self):
        # [utest->req~restore-locked-step-16-resolve-outcome-and-divergence~1]
        unclaimed = locked(row=subscription(user_id=None))
        with pytest.raises(RestoreRejection) as refused:
            step_16_resolve_outcome_and_divergence(
                unclaimed, ledger=LockedPhaseLedger(), destination_user_id=DESTINATION,
                pre_transaction_branch=RestoreBranch.same_account)
        assert refused.value.result is AuthEventResult.restore_branch_inconsistent

    def test_a_different_locked_owner_rejects_as_already_linked(self):
        # [utest->req~restore-locked-step-16-resolve-outcome-and-divergence~1]
        with pytest.raises(RestoreRejection) as refused:
            step_16_resolve_outcome_and_divergence(
                locked(row=subscription(user_id=OTHER)), ledger=LockedPhaseLedger(),
                destination_user_id=DESTINATION,
                pre_transaction_branch=RestoreBranch.adoption)
        assert refused.value.result is AuthEventResult.store_transaction_already_linked

    def test_divergence_is_decided_before_the_freshness_recheck(self):
        # [utest->req~restore-locked-step-16-resolve-outcome-and-divergence~1]
        ledger = LockedPhaseLedger()
        ledger.record("17_live_verification_freshness")
        with pytest.raises(RestorePhaseError):
            step_16_resolve_outcome_and_divergence(
                locked(row=subscription(user_id=DESTINATION)), ledger=ledger,
                destination_user_id=DESTINATION,
                pre_transaction_branch=RestoreBranch.same_account)


class TestStep17LiveVerificationFreshness:

    def _record(self, *, subscription_id=None, absent=True, at=NOW,
                key=KEY) -> LiveStoreVerification:
        return LiveStoreVerification(provider=key[0], external_id=key[1],
                                     subscription_id=subscription_id,
                                     canonical_row_absent=absent, verified_at=at,
                                     status=SubscriptionStatus.active)

    def test_a_fresh_corresponding_record_passes(self):
        # [utest->req~restore-locked-step-17-live-verification-freshness~1]
        row_id = uuid7()
        record = self._record(subscription_id=row_id, absent=False)
        assert step_17_live_verification_freshness(
            record, ledger=LockedPhaseLedger(), branch=RestoreBranch.adoption,
            locked_key=KEY, locked_subscription_id=row_id,
            now=NOW + timedelta(seconds=10), freshness_seconds=60) is record

    def test_a_stale_record_rejects_as_unverified(self):
        # [utest->req~restore-locked-step-17-live-verification-freshness~1]
        with pytest.raises(RestoreRejection) as refused:
            step_17_live_verification_freshness(
                self._record(), ledger=LockedPhaseLedger(), branch=RestoreBranch.adoption,
                locked_key=KEY, locked_subscription_id=None,
                now=NOW + timedelta(seconds=120), freshness_seconds=60)
        assert refused.value.result is AuthEventResult.restore_store_state_unverified

    def test_a_record_for_another_store_subscription_rejects(self):
        # [utest->req~restore-locked-step-17-live-verification-freshness~1]
        with pytest.raises(RestoreRejection):
            step_17_live_verification_freshness(
                self._record(key=(APPLE, "2000000999999999")), ledger=LockedPhaseLedger(),
                branch=RestoreBranch.adoption, locked_key=KEY, locked_subscription_id=None,
                now=NOW, freshness_seconds=60)

    def test_a_record_for_another_canonical_row_rejects(self):
        # [utest->req~restore-locked-step-17-live-verification-freshness~1]
        with pytest.raises(RestoreRejection):
            step_17_live_verification_freshness(
                self._record(subscription_id=uuid7(), absent=False),
                ledger=LockedPhaseLedger(), branch=RestoreBranch.adoption, locked_key=KEY,
                locked_subscription_id=uuid7(), now=NOW, freshness_seconds=60)

    def test_the_creation_path_needs_only_the_store_subscription_to_match(self):
        # [utest->req~restore-locked-step-17-live-verification-freshness~1]
        record = self._record()
        assert step_17_live_verification_freshness(
            record, ledger=LockedPhaseLedger(), branch=RestoreBranch.adoption, locked_key=KEY,
            locked_subscription_id=uuid7(), now=NOW, freshness_seconds=60) is record

    def test_same_account_runs_no_recheck(self):
        # [utest->req~restore-locked-step-17-live-verification-freshness~1]
        assert step_17_live_verification_freshness(
            None, ledger=LockedPhaseLedger(), branch=RestoreBranch.same_account,
            locked_key=KEY, locked_subscription_id=None, now=NOW,
            freshness_seconds=60) is None

    def test_adoption_without_a_record_rejects_rather_than_calling_the_store(self):
        # [utest->req~restore-locked-step-17-live-verification-freshness~1]
        with pytest.raises(RestoreRejection) as refused:
            step_17_live_verification_freshness(
                None, ledger=LockedPhaseLedger(), branch=RestoreBranch.adoption,
                locked_key=KEY, locked_subscription_id=None, now=NOW, freshness_seconds=60)
        assert refused.value.result is AuthEventResult.restore_store_state_unverified


class TestStep18BranchMutationAndBinding:

    def test_a_successful_mutation_sets_the_binding_where_it_is_still_null(self):
        # [utest->req~restore-locked-step-18-branch-mutation-and-binding~1]
        grant = uuid7()
        mutations = RestoreGrantMutations()
        outcome = step_18_branch_mutation_and_binding(
            locked(row=subscription(user_id=None)), ledger=LockedPhaseLedger(),
            branch=RestoreBranch.adoption, destination_user_id=DESTINATION,
            grant_id=grant, mutations=mutations)
        assert outcome.restore_bound_user_id == DESTINATION
        assert outcome.grant_id == grant
        assert mutations.committed is True

    def test_an_established_binding_is_never_changed(self):
        # [utest->req~restore-locked-step-18-branch-mutation-and-binding~1]
        outcome = step_18_branch_mutation_and_binding(
            locked(row=subscription(user_id=DESTINATION, bound=DESTINATION)),
            ledger=LockedPhaseLedger(), branch=RestoreBranch.same_account,
            destination_user_id=DESTINATION, grant_id=uuid7(),
            mutations=RestoreGrantMutations())
        assert outcome.restore_bound_user_id == DESTINATION
        with pytest.raises(RestorePhaseError):
            step_18_branch_mutation_and_binding(
                locked(row=subscription(user_id=DESTINATION, bound=OTHER)),
                ledger=LockedPhaseLedger(), branch=RestoreBranch.same_account,
                destination_user_id=DESTINATION, grant_id=uuid7(),
                mutations=RestoreGrantMutations())

    def test_stale_rows_are_expired_before_the_grant_is_activated(self):
        # [utest->req~restore-locked-step-18-branch-mutation-and-binding~1]
        stale, grant = uuid7(), uuid7()
        mutations = RestoreGrantMutations()
        step_18_branch_mutation_and_binding(
            locked(row=subscription(user_id=DESTINATION)), ledger=LockedPhaseLedger(),
            branch=RestoreBranch.same_account, destination_user_id=DESTINATION,
            grant_id=grant, mutations=mutations, stale_grant_ids=[stale])
        assert mutations.statements.index("activate_subscription_grant") == 1
        assert mutations.expired == [stale]

    def test_it_makes_no_provider_call(self):
        # [utest->req~restore-locked-step-18-branch-mutation-and-binding~1]
        ledger = LockedPhaseLedger()
        ledger.acquire(LockTier.store_subscription_serialization)
        with pytest.raises(RestorePhaseError):
            step_18_branch_mutation_and_binding(
                locked(row=subscription(user_id=DESTINATION)), ledger=ledger,
                branch=RestoreBranch.same_account, destination_user_id=DESTINATION,
                grant_id=uuid7(), mutations=RestoreGrantMutations(),
                provider_call="apple_get_transaction_info")


class TestStep19WriteAuditRow:

    def test_a_locked_outcome_writes_its_row_in_the_mutation_transaction(self):
        # [utest->req~restore-locked-step-19-write-audit-row~1]
        transaction = object()
        ledger = LockedPhaseLedger()
        classification = step_19_write_audit_row(
            ledger=ledger, phase=RestorePhase.locked_mutation,
            result=AuthEventResult.succeeded, branch=RestoreBranch.same_account,
            transaction=transaction, mutation_transaction=transaction,
            context=RestoreAuditContext(destination_user_id=DESTINATION))
        assert classification is MovementClassification.same_account
        assert len(ledger.audit.rows) == 1
        with pytest.raises(RestorePhaseError):
            step_19_write_audit_row(ledger=LockedPhaseLedger(),
                                    phase=RestorePhase.locked_mutation,
                                    result=AuthEventResult.succeeded,
                                    branch=RestoreBranch.adoption,
                                    transaction=transaction,
                                    mutation_transaction=object())

    def test_adoption_records_its_own_classification(self):
        # [utest->req~restore-locked-step-19-write-audit-row~1]
        transaction = object()
        assert step_19_write_audit_row(
            ledger=LockedPhaseLedger(), phase=RestorePhase.locked_mutation,
            result=AuthEventResult.succeeded, branch=RestoreBranch.adoption,
            transaction=transaction,
            mutation_transaction=transaction) is MovementClassification.adoption

    def test_an_already_linked_rejection_records_unclassified(self):
        # [utest->req~restore-locked-step-19-write-audit-row~1]
        locked_transaction = object()
        assert step_19_write_audit_row(
            ledger=LockedPhaseLedger(), phase=RestorePhase.locked_mutation,
            result=AuthEventResult.store_transaction_already_linked,
            branch=RestoreBranch.adoption, transaction=locked_transaction,
            mutation_transaction=locked_transaction) is MovementClassification.unclassified

    def test_a_divergence_records_unclassified(self):
        # [utest->req~restore-locked-step-19-write-audit-row~1]
        locked_transaction = object()
        assert step_19_write_audit_row(
            ledger=LockedPhaseLedger(), phase=RestorePhase.locked_mutation,
            result=AuthEventResult.restore_branch_inconsistent,
            branch=RestoreBranch.same_account, transaction=locked_transaction,
            mutation_transaction=locked_transaction) is MovementClassification.unclassified

    def test_a_pre_transaction_rejection_writes_its_own_row_with_no_mutation(self):
        # [utest->req~restore-locked-step-19-write-audit-row~1]
        rejection_transaction = object()
        ledger = LockedPhaseLedger()
        assert step_19_write_audit_row(
            ledger=ledger, phase=RestorePhase.pre_transaction,
            result=AuthEventResult.invalid_restore_proof, branch=None,
            transaction=rejection_transaction) is MovementClassification.unclassified
        with pytest.raises(RestorePhaseError):
            step_19_write_audit_row(ledger=LockedPhaseLedger(),
                                    phase=RestorePhase.pre_transaction,
                                    result=AuthEventResult.invalid_restore_proof,
                                    branch=None, transaction=rejection_transaction,
                                    mutation_transaction=rejection_transaction)

    def test_one_attempt_writes_one_row(self):
        # [utest->req~restore-locked-step-19-write-audit-row~1]
        transaction = object()
        ledger = LockedPhaseLedger()
        step_19_write_audit_row(ledger=ledger, phase=RestorePhase.locked_mutation,
                                result=AuthEventResult.succeeded,
                                branch=RestoreBranch.adoption, transaction=transaction,
                                mutation_transaction=transaction)
        with pytest.raises(RestoreContractError):
            step_19_write_audit_row(ledger=ledger, phase=RestorePhase.locked_mutation,
                                    result=AuthEventResult.succeeded,
                                    branch=RestoreBranch.adoption, transaction=transaction,
                                    mutation_transaction=transaction)
