"""Live store-state verification: the adoption branch's one provider call, its recorded outcome,
and the Apple and Google rules it runs under."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid7

import pytest
import yaml

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.restore import RestoreBranch, RestoreRejection
from nativespeaker.api.auth.restore_flow import VerifiedTransaction
from nativespeaker.api.auth.restore_live_verification import (
    APPLE_API_SURFACE,
    GOOGLE_API_SURFACE,
    LIVE_VERIFICATION_CALLS_PER_REQUEST,
    NON_RETRYABLE_FAILURES,
    AppleCredentials,
    AppleSubscriptionStatusResponse,
    GoogleLookupInputs,
    GooglePlayCredentials,
    GoogleSubscriptionStateResponse,
    LiveDecision,
    LiveVerificationError,
    apple_credentials,
    apple_entitled_state_required,
    apple_live_verification_call,
    apple_verify_and_decode,
    assert_adoption_only,
    assert_after_barrier_and_proof,
    assert_backend_credentials_and_inputs,
    assert_before_locked_transaction,
    assert_no_cached_state,
    assert_no_canonical_state_update,
    assert_no_raw_response_persistence,
    assert_no_retry_budget,
    assert_non_entitled_rejects,
    assert_non_retryable_failure_rejects,
    assert_one_call_rule,
    assert_within_freshness_bound,
    confirm_currently_entitled,
    consume_recorded_outcome,
    fail_closed_on_failure,
    freshness_bound,
    google_credentials,
    google_entitled_state_required,
    google_live_verification_call,
    google_service_account_credentials,
    record_outcome,
    verification_audit_context,
)
from nativespeaker.api.auth.restore_phases import LockedPhaseLedger, LockTier
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.ratelimit.providers import ProviderDampingConfig

EXTERNAL_ID = "2000000123456789"
TOKEN = "11111111-2222-3333-4444-555555555555"
APPLE = StoreProvider.apple
GOOGLE = StoreProvider.google_play
KEY = (APPLE, EXTERNAL_ID)
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
SUBSCRIPTION_ID = uuid7()
VERIFIED = VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID,
                               carried_purchase_uuid=TOKEN)
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"

APPLE_KEYS = AppleCredentials(bundle_id="com.example.nativespeaker", team_id="ABCDE12345")
GOOGLE_KEYS = GooglePlayCredentials(package_name="com.example.nativespeaker",
                                    service_account_email="play@example.iam.gserviceaccount.com",
                                    service_account_private_key="-----BEGIN PRIVATE KEY-----")
GOOGLE_INPUTS = GoogleLookupInputs(purchase_token="opaque-play-token",
                                   subscription_product_id="com.example.nativespeaker.gold")


def damping() -> ProviderDampingConfig:
    return ProviderDampingConfig(**yaml.safe_load(CONFIG_PATH.read_text())["provider_damping"])


def recorded(*, at: datetime = NOW):
    return record_outcome(VERIFIED, status=SubscriptionStatus.active,
                          subscription_id=SUBSCRIPTION_ID, canonical_row_absent=False,
                          verified_at=at)


def locked_ledger() -> LockedPhaseLedger:
    ledger = LockedPhaseLedger()
    ledger.acquire(LockTier.store_subscription_serialization)
    return ledger


# --- Common rules ---------------------------------------------------------------------------------


# [utest->req~restore-live-verification-adoption-only~1]
def test_only_adoption_live_verifies_and_same_account_never_does():
    assert assert_adoption_only(RestoreBranch.adoption, verification_performed=True) is True
    assert assert_adoption_only(RestoreBranch.same_account,
                                verification_performed=False) is False
    with pytest.raises(RestoreRejection) as raised:
        assert_adoption_only(RestoreBranch.adoption, verification_performed=False)
    assert raised.value.result is AuthEventResult.restore_store_state_unverified
    with pytest.raises(LiveVerificationError):
        assert_adoption_only(RestoreBranch.same_account, verification_performed=True)


# [utest->req~restore-live-verification-before-locked-transaction~1]
def test_the_call_is_made_before_the_locks_and_the_locked_phase_only_consumes_the_record():
    assert assert_before_locked_transaction("apple_live_store_verification",
                                            locks_held=False) == "apple_live_store_verification"
    with pytest.raises(LiveVerificationError):
        assert_before_locked_transaction("apple_live_store_verification", locks_held=True)
    with pytest.raises(LiveVerificationError):
        assert_before_locked_transaction("apple_live_store_verification", locks_held=False,
                                         locked_phase_consumes="fresh_provider_call")


# [utest->req~restore-live-verification-after-barrier-and-proof~1]
def test_live_verification_runs_after_the_barrier_and_after_proof_verification():
    assert assert_after_barrier_and_proof(barrier_admitted=True, proof_verified=True) is None
    with pytest.raises(LiveVerificationError):
        assert_after_barrier_and_proof(barrier_admitted=False, proof_verified=True)
    with pytest.raises(LiveVerificationError):
        assert_after_barrier_and_proof(barrier_admitted=True, proof_verified=False)


# [utest->req~restore-live-verification-after-barrier-and-proof~1]
def test_its_rejection_audits_unverified_in_its_own_transaction_with_no_mutation():
    assert assert_after_barrier_and_proof(
        barrier_admitted=True, proof_verified=True, rejected=True,
        rejection_result=AuthEventResult.restore_store_state_unverified,
        rejection_transaction=object()) is None
    with pytest.raises(LiveVerificationError):
        assert_after_barrier_and_proof(
            barrier_admitted=True, proof_verified=True, rejected=True,
            rejection_result=AuthEventResult.restore_store_state_unverified,
            rejection_transaction=None)
    with pytest.raises(LiveVerificationError):
        assert_after_barrier_and_proof(
            barrier_admitted=True, proof_verified=True, rejected=True,
            rejection_result=AuthEventResult.restore_subscription_not_entitled,
            rejection_transaction=object())
    with pytest.raises(LiveVerificationError):
        assert_after_barrier_and_proof(barrier_admitted=True, proof_verified=True,
                                       mutations_performed=("access_grants_write",))


# [utest->req~restore-live-verification-no-cached-state~1]
def test_no_cached_or_webhook_state_stands_in_for_the_live_call():
    assert assert_no_cached_state() is True
    for source in ("cached_subscription_state", "prior_webhook_delivery",
                   "core_subscriptions_status_alone"):
        with pytest.raises(LiveVerificationError):
            assert_no_cached_state(sources=(source,))
    with pytest.raises(RestoreRejection) as raised:
        assert_no_cached_state(live_verification_performed=False)
    assert raised.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-live-verification-backend-credentials-and-inputs~1]
def test_the_credentials_are_backend_held_and_come_from_configuration():
    raw = {"apple": {"bundle_id": "com.example.nativespeaker", "team_id": "ABCDE12345"},
           "google_play": {"package_name": "com.example.nativespeaker",
                           "service_account_email": "play@example.iam.gserviceaccount.com",
                           "service_account_private_key": "-----BEGIN PRIVATE KEY-----"}}
    assert apple_credentials(raw).team_id == "ABCDE12345"
    assert google_credentials(raw).package_name == "com.example.nativespeaker"
    with pytest.raises(LiveVerificationError):
        apple_credentials({"apple": {"bundle_id": "com.example.nativespeaker"}})
    with pytest.raises(LiveVerificationError):
        google_credentials({"google_play": {"package_name": "com.example.nativespeaker"}})


# [utest->req~restore-live-verification-backend-credentials-and-inputs~1]
def test_client_input_never_parameterizes_the_provider_call():
    assert assert_backend_credentials_and_inputs(credentials=APPLE_KEYS) == (
        "server_verified_restore_material",)
    with pytest.raises(LiveVerificationError):
        assert_backend_credentials_and_inputs(
            credentials=AppleCredentials(bundle_id="x", team_id="y", backend_held=False))
    with pytest.raises(LiveVerificationError):
        assert_backend_credentials_and_inputs(credentials=APPLE_KEYS,
                                              client_supplied_parameters=("body.external_id",))
    with pytest.raises(LiveVerificationError):
        assert_backend_credentials_and_inputs(credentials=APPLE_KEYS,
                                              input_sources=("request_body",))


# [utest->req~restore-live-verification-confirm-currently-entitled~1]
def test_only_a_product_entitled_live_state_confirms():
    assert confirm_currently_entitled("active") is SubscriptionStatus.active
    assert confirm_currently_entitled("grace_period") is SubscriptionStatus.grace_period
    for observed in ("billing_retry", "not_a_state", None):
        with pytest.raises(RestoreRejection) as raised:
            confirm_currently_entitled(observed)
        assert raised.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-live-verification-non-entitled-rejects~1]
def test_every_non_entitled_live_state_rejects_and_mutates_nothing():
    for observed in ("missing", "unknown", "expired", "revoked", "refunded_voiding"):
        with pytest.raises(RestoreRejection) as raised:
            assert_non_entitled_rejects(observed)
        assert raised.value.result is AuthEventResult.restore_store_state_unverified
    with pytest.raises(LiveVerificationError):
        assert_non_entitled_rejects("expired", mutations_performed=("subscriptions_owner_change",))


# [utest->req~restore-live-verification-one-call-rule~1]
def test_exactly_one_call_per_request_with_no_retry_and_no_knob():
    assert assert_one_call_rule(calls_made=1, admission_checks_passed=True,
                                proof_verified=True) == LIVE_VERIFICATION_CALLS_PER_REQUEST
    with pytest.raises(LiveVerificationError):
        assert_one_call_rule(calls_made=2, admission_checks_passed=True, proof_verified=True)
    with pytest.raises(LiveVerificationError):
        assert_one_call_rule(calls_made=1, admission_checks_passed=True, proof_verified=True,
                             retries=1)
    with pytest.raises(LiveVerificationError):
        assert_one_call_rule(calls_made=1, admission_checks_passed=True, proof_verified=True,
                             retry_knobs=("live_verification_retries",))
    with pytest.raises(LiveVerificationError):
        assert_one_call_rule(calls_made=1, admission_checks_passed=True, proof_verified=True,
                             locks_held=True)
    with pytest.raises(LiveVerificationError):
        assert_one_call_rule(calls_made=1, admission_checks_passed=False, proof_verified=True)
    with pytest.raises(LiveVerificationError):
        assert_one_call_rule(calls_made=1, admission_checks_passed=True, proof_verified=False)


# [utest->req~restore-live-verification-one-call-rule~1]
def test_the_shipped_damping_gives_live_verification_no_retry_budget():
    config = damping()
    for provider in (APPLE, GOOGLE):
        assert assert_no_retry_budget(config, provider) is None


# [utest->req~restore-live-verification-fail-closed-on-failure~1]
def test_a_failed_or_timed_out_call_fails_closed_without_an_in_request_retry():
    rejection = fail_closed_on_failure("timeout")
    assert rejection.result is AuthEventResult.restore_store_state_unverified
    with pytest.raises(LiveVerificationError):
        fail_closed_on_failure("timeout", retried=True)


# [utest->req~restore-live-verification-non-retryable-failure-rejects~1]
def test_the_declared_non_retryable_failures_reject_as_unverified():
    for failure in NON_RETRYABLE_FAILURES:
        assert assert_non_retryable_failure_rejects(failure).result is (
            AuthEventResult.restore_store_state_unverified)
    with pytest.raises(LiveVerificationError):
        assert_non_retryable_failure_rejects("connection_reset")


# [utest->req~restore-live-verification-record-outcome-and-recheck~1]
def test_the_outcome_records_the_store_subscription_and_a_server_issued_timestamp():
    record = recorded()
    assert record.key == KEY
    assert record.subscription_id == SUBSCRIPTION_ID
    assert record.verified_at == NOW
    absent = record_outcome(VERIFIED, status=SubscriptionStatus.active, subscription_id=None,
                            canonical_row_absent=True, verified_at=NOW)
    assert absent.canonical_row_absent is True
    with pytest.raises(LiveVerificationError):
        record_outcome(VERIFIED, status=SubscriptionStatus.active,
                       subscription_id=SUBSCRIPTION_ID, canonical_row_absent=True,
                       verified_at=NOW)


# [utest->req~restore-live-verification-record-outcome-and-recheck~1]
def test_the_locked_phase_consumes_the_record_and_rejects_a_mismatch():
    consumed = consume_recorded_outcome(recorded(), ledger=locked_ledger(), locked_key=KEY,
                                        locked_subscription_id=SUBSCRIPTION_ID,
                                        now=NOW + timedelta(seconds=5), freshness_seconds=60)
    assert consumed is not None and consumed.subscription_id == SUBSCRIPTION_ID
    mismatches = (((GOOGLE, EXTERNAL_ID), SUBSCRIPTION_ID, NOW),
                  (KEY, uuid7(), NOW),
                  (KEY, SUBSCRIPTION_ID, NOW + timedelta(seconds=600)))
    for key, subscription_id, now in mismatches:
        with pytest.raises(RestoreRejection) as raised:
            consume_recorded_outcome(recorded(), ledger=locked_ledger(), locked_key=key,
                                     locked_subscription_id=subscription_id, now=now,
                                     freshness_seconds=60)
        assert raised.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-live-verification-freshness-bound~1]
def test_the_freshness_bound_is_configured_and_a_stale_record_is_rejected():
    config = damping()
    for provider in (APPLE, GOOGLE):
        assert freshness_bound(config, provider) == 60
    record = recorded()
    assert assert_within_freshness_bound(record, now=NOW + timedelta(seconds=30),
                                         freshness_seconds=60) == 30
    with pytest.raises(RestoreRejection) as raised:
        assert_within_freshness_bound(record, now=NOW + timedelta(seconds=61),
                                      freshness_seconds=60)
    assert raised.value.result is AuthEventResult.restore_store_state_unverified


# [utest->req~restore-live-verification-freshness-bound~1]
def test_the_locked_phase_never_extends_refreshes_or_re_runs_the_verification():
    record = recorded()
    with pytest.raises(LiveVerificationError):
        assert_within_freshness_bound(record, now=NOW, freshness_seconds=60, extended=True)
    with pytest.raises(LiveVerificationError):
        assert_within_freshness_bound(record, now=NOW, freshness_seconds=60, re_run=True)


# [utest->req~restore-live-verification-no-raw-response-persistence~1]
def test_no_raw_provider_material_reaches_a_stored_row():
    assert assert_no_raw_response_persistence({"decision": "entitled"},
                                              table="audit.auth_events")
    for field in ("raw_response", "signed_payload", "signed_transaction_info",
                  "signed_renewal_info", "jws", "provider_payload"):
        with pytest.raises(LiveVerificationError):
            assert_no_raw_response_persistence({field: "..."}, table="core.subscriptions")
    with pytest.raises(LiveVerificationError):
        assert_no_raw_response_persistence({"decision": "entitled"}, table="core.store_purchases")


# [utest->req~restore-live-verification-no-canonical-state-update~1]
def test_live_verification_updates_no_canonical_state_but_may_reject_on_contradiction():
    assert assert_no_canonical_state_update() is True
    with pytest.raises(LiveVerificationError):
        assert_no_canonical_state_update(("core_subscriptions_status_write",))
    with pytest.raises(RestoreRejection) as raised:
        assert_no_canonical_state_update(live_status=SubscriptionStatus.expired,
                                         current_status=SubscriptionStatus.active)
    assert raised.value.result is AuthEventResult.restore_store_state_unverified
    assert assert_no_canonical_state_update(live_status=SubscriptionStatus.grace_period,
                                            current_status=SubscriptionStatus.active) is True


# --- Apple-provider rules --------------------------------------------------------------------------


# [utest->req~restore-apple-live-verification-api-call~1]
def test_the_apple_call_names_a_current_endpoint_the_bundle_and_the_team():
    call = apple_live_verification_call(VERIFIED, credentials=APPLE_KEYS)
    assert call.api_surface == APPLE_API_SURFACE
    assert dict(call.configured) == {"apple.bundle_id": "com.example.nativespeaker",
                                     "apple.team_id": "ABCDE12345"}
    assert dict(call.lookup) == {"originalTransactionId": EXTERNAL_ID}
    with pytest.raises(LiveVerificationError):
        apple_live_verification_call(VERIFIED, credentials=APPLE_KEYS,
                                     api_surface="Verify Receipt")
    with pytest.raises(LiveVerificationError):
        apple_live_verification_call(
            VerifiedTransaction(provider=GOOGLE, external_id=EXTERNAL_ID),
            credentials=APPLE_KEYS)


# [utest->req~restore-apple-live-verification-signature-and-decode~1]
def test_apples_signature_is_verified_and_its_jws_decoded():
    response = AppleSubscriptionStatusResponse(signature_verified=True,
                                               signed_transaction_info="jws.tx",
                                               signed_renewal_info="jws.renewal",
                                               status=SubscriptionStatus.active)
    assert apple_verify_and_decode(response) == ("jws.tx", "jws.renewal")
    with pytest.raises(RestoreRejection):
        apple_verify_and_decode(AppleSubscriptionStatusResponse(
            signature_verified=False, signed_transaction_info="jws.tx",
            signed_renewal_info="jws.renewal", status=SubscriptionStatus.active))
    with pytest.raises(RestoreRejection):
        apple_verify_and_decode(AppleSubscriptionStatusResponse(
            signature_verified=True, signed_transaction_info=None,
            signed_renewal_info="jws.renewal", status=SubscriptionStatus.active))
    with pytest.raises(LiveVerificationError):
        apple_verify_and_decode(response, client_supplied_state={"status": "active"})


# [utest->req~restore-apple-live-verification-entitled-state-required~1]
def test_apples_response_must_report_a_product_entitled_state():
    def response(status):
        return AppleSubscriptionStatusResponse(signature_verified=True,
                                               signed_transaction_info="jws.tx",
                                               signed_renewal_info="jws.renewal", status=status)

    assert apple_entitled_state_required(response("active")) is SubscriptionStatus.active
    for status in ("expired", "revoked", "refunded_voiding", "billing_retry"):
        with pytest.raises(RestoreRejection) as raised:
            apple_entitled_state_required(response(status))
        assert raised.value.result is AuthEventResult.restore_store_state_unverified


# --- Google Play-provider rules ----------------------------------------------------------------------


# [utest->req~restore-google-live-verification-api-call~1]
def test_the_google_call_names_a_current_endpoint_the_package_and_the_verified_inputs():
    call = google_live_verification_call(GOOGLE_INPUTS, credentials=GOOGLE_KEYS)
    assert call.api_surface == GOOGLE_API_SURFACE
    assert dict(call.configured) == {"google_play.package_name": "com.example.nativespeaker"}
    assert dict(call.lookup) == {"purchaseToken": "opaque-play-token",
                                 "subscriptionId": "com.example.nativespeaker.gold"}
    with pytest.raises(LiveVerificationError):
        google_live_verification_call(GOOGLE_INPUTS, credentials=GOOGLE_KEYS,
                                      api_surface="purchases.products.get")
    with pytest.raises(LiveVerificationError):
        google_live_verification_call(
            GoogleLookupInputs(purchase_token="t", subscription_product_id="p",
                               source="request_body"),
            credentials=GOOGLE_KEYS)


# [utest->req~restore-google-live-verification-service-account-credentials~1]
def test_google_runs_under_a_backend_held_service_account_and_ignores_client_state():
    assert google_service_account_credentials(GOOGLE_KEYS) is GOOGLE_KEYS
    with pytest.raises(LiveVerificationError):
        google_service_account_credentials(GOOGLE_KEYS,
                                           client_supplied_state={"state": "active"})
    with pytest.raises(LiveVerificationError):
        google_service_account_credentials(
            GooglePlayCredentials(package_name="p", service_account_email="e",
                                  service_account_private_key="k", backend_held=False))
    with pytest.raises(LiveVerificationError):
        google_service_account_credentials(
            GooglePlayCredentials(package_name="p", service_account_email="",
                                  service_account_private_key="k"))


# [utest->req~restore-google-live-verification-entitled-state-required~1]
def test_googles_response_must_report_a_product_entitled_state():
    assert google_entitled_state_required(
        GoogleSubscriptionStateResponse(state="active")) is SubscriptionStatus.active
    for state in ("expired", "revoked", "refunded_voiding", "on_hold_without_entitlement",
                  "paused", "billing_retry"):
        with pytest.raises(RestoreRejection) as raised:
            google_entitled_state_required(GoogleSubscriptionStateResponse(state=state))
        assert raised.value.result is AuthEventResult.restore_store_state_unverified
    with pytest.raises(LiveVerificationError):
        google_entitled_state_required(GoogleSubscriptionStateResponse(state="active"),
                                       client_supplied_state={"state": "active"})


# --- Audit rules ------------------------------------------------------------------------------------


# [utest->req~restore-live-verification-audit-non-secret-context~1]
def test_the_audit_context_is_non_secret_and_carries_no_raw_payload():
    context = verification_audit_context(provider=APPLE, api_surface=APPLE_API_SURFACE,
                                         decision=LiveDecision.entitled,
                                         result_codes=("status_1",))
    assert context == {"provider": "apple", "api_surface": APPLE_API_SURFACE,
                       "decision": "entitled", "result_codes": ["status_1"]}
    assert verification_audit_context(provider=GOOGLE, api_surface=GOOGLE_API_SURFACE,
                                      decision=LiveDecision.unavailable)["decision"] == (
        "unavailable")
    with pytest.raises(LiveVerificationError):
        verification_audit_context(provider=APPLE, api_surface=APPLE_API_SURFACE,
                                   decision=LiveDecision.not_entitled,
                                   raw={"signed_payload": "..."})
