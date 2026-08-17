"""The free-credit grant invariants of `03-free-credit-grants-and-anti-abuse.md`.

Most of that section's numbered items refer their rule to the schema file and are covered where the
rule is enforced. Three of them state a rule of their own: the `claim_anonymous_grant` failure-class
split (5), the registered account grant as the specified alternate path (11), and the one-free-grant
cap per account for the account's lifetime (12). This file exercises those three.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.derived_identifiers import (
    HmacKey,
    IdpAccountAliasIndex,
    KeyFamily,
    KeyRing,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import (
    TOMBSTONE_RETAINED_COLUMNS,
    ExternalIdentityRow,
    IdentityError,
    IdentityState,
    NativeClaimPlatform,
    assert_conversion_same_lineage,
    clear_free_grant_marker,
    erase_account,
    free_grant_available,
    mark_free_grant_consumed,
)
from nativespeaker.api.auth.free_grants import (
    FreeGrantError,
    FreeGrantRejected,
    android_anonymous_path_available,
    assert_claimant_eligible,
    consume_free_grant_gate,
    recall_absence_alternate,
    reconfirm_claimant,
    registered_backstop,
)
from nativespeaker.api.auth.grant_failures import (
    AnonFailureCondition,
    GrantFailureError,
    anonymous_failure_class,
    anonymous_remediation,
    classify_anonymous_failure,
    exhausted_alternate_path,
    transient_failure_class,
)
from nativespeaker.api.auth.invariants import (
    GateAlreadyConsumedError,
    GateConsumptionKind,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_adapters import ClaimRejection
from nativespeaker.api.auth.proof_endpoints import ClaimBranch
from nativespeaker.api.auth.registered_grants import (
    RegisteredDestination,
    assert_account_grant_history,
    reconfirm_registered_claimant,
    registered_eligibility,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
ISSUER = "https://securetoken.google.com/test-project"
GOOGLE_UID = "google-account-1"


def identity_row(**overrides: Any) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.anonymous, "provider_uid": None,
                              "identity_state": IdentityState.active}
    fields.update(overrides)
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=ISSUER,
                              subject="firebase-subject", **fields)


def google_row(**overrides: Any) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.google, "provider_uid": GOOGLE_UID}
    fields.update(overrides)
    return identity_row(**fields)


GOOGLE_PROVIDER_DATA: tuple[dict[str, str], ...] = (
    {"providerId": "google.com", "uid": GOOGLE_UID},
)


# --- Invariant 5: the three `claim_anonymous_grant` failure classes -------------------------------


# [utest->req~grants-invariant-05~1]
def test_already_claimed_state_and_web_gate_conflicts_are_device_grant_exhausted() -> None:
    # Per-device anonymous-claimed state already set, on either native platform.
    for condition in (AnonFailureCondition.ios_anonymous_bit_set,
                      AnonFailureCondition.android_recall_anonymous_state_set):
        failure = classify_anonymous_failure(condition)
        assert failure.client_class is ClientErrorClass.device_grant_exhausted
        assert failure.result is AuthEventResult.native_claim_already_claimed
    # A web anonymous-grant `idp_account_hash` uniqueness conflict: a different mechanism, its own
    # internal result, the same client-visible class.
    web = classify_anonymous_failure(AnonFailureCondition.web_gate_already_consumed)
    assert web.client_class is ClientErrorClass.device_grant_exhausted
    assert web.result is AuthEventResult.anti_abuse_already_claimed
    assert anonymous_failure_class(
        AnonFailureCondition.web_gate_already_consumed) is ClientErrorClass.device_grant_exhausted


# [utest->req~grants-invariant-05~1]
def test_durable_policy_blocks_are_verification_required() -> None:
    durable = (AnonFailureCondition.anonymous_grant_policy_rejected,
               AnonFailureCondition.device_check_read_denied,
               AnonFailureCondition.cloudflare_bot_check_denied,
               AnonFailureCondition.web_stored_binding_mismatch)
    for condition in durable:
        failure = classify_anonymous_failure(condition)
        assert failure.client_class is ClientErrorClass.verification_required
        assert failure.after_retry_budget is False
    # A durable block has no guaranteed free-credit alternate and is never retried blindly.
    remediation = anonymous_remediation(ClientErrorClass.verification_required)
    assert remediation.durably_closed is True
    assert remediation.guaranteed_alternate is False
    assert remediation.retry_same_endpoint is False


# [utest->req~grants-invariant-05~1]
def test_transient_provider_failures_are_verification_temporarily_unavailable() -> None:
    transient = (AnonFailureCondition.firebase_provider_data_unavailable,
                 AnonFailureCondition.device_state_write_failed,
                 AnonFailureCondition.devicecheck_read_unavailable,
                 AnonFailureCondition.cloudflare_dependency_failed)
    for condition in transient:
        failure = classify_anonymous_failure(condition)
        assert failure.client_class is ClientErrorClass.verification_temporarily_unavailable
        # Reached only once the in-request retry budget is spent.
        assert failure.after_retry_budget is True
        assert transient_failure_class(condition) is \
            ClientErrorClass.verification_temporarily_unavailable
    # It is never surfaced as a durable class on the strength of the dependency failure alone.
    assert transient_failure_class(
        AnonFailureCondition.firebase_provider_data_unavailable,
        durable_state_observed=True) is ClientErrorClass.device_grant_exhausted
    with pytest.raises(GrantFailureError):
        # A durable condition is no transient dependency failure.
        transient_failure_class(AnonFailureCondition.ios_anonymous_bit_set)


# [utest->req~grants-invariant-05~1]
def test_native_admits_anonymous_or_registered_claimants_and_web_only_registered() -> None:
    anonymous = identity_row()
    registered = google_row()
    for branch in (ClaimBranch.native_ios, ClaimBranch.native_android):
        assert assert_claimant_eligible(branch, anonymous) is IdentityProvider.anonymous
        assert assert_claimant_eligible(branch, registered) is IdentityProvider.google
    assert assert_claimant_eligible(ClaimBranch.web, registered) is IdentityProvider.google
    with pytest.raises(FreeGrantRejected) as rejected:
        assert_claimant_eligible(ClaimBranch.web, anonymous)
    assert rejected.value.error_code == "verification_required"
    # A historical identity is the shared account case, not one of the three grant classes.
    with pytest.raises(FreeGrantRejected) as historical:
        assert_claimant_eligible(ClaimBranch.native_ios,
                                 identity_row(identity_state=IdentityState.historical))
    assert historical.value.result is AuthEventResult.historical_identity


# [utest->req~grants-invariant-05~1]
def test_exhausted_directs_to_the_registered_claim_without_guaranteeing_it() -> None:
    remediation = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    assert remediation.alternate_operation is AuthOperation.claim_registered_grant
    assert set(remediation.obtain_identity_by) >= {"sign_in", "create", "upgrade"}
    assert exhausted_alternate_path(google_row(), active_grant_source=None) is \
        AuthOperation.claim_registered_grant
    # The registered path has its own gates: naming it is not a promise that it will issue.
    with pytest.raises(FreeGrantRejected):
        exhausted_alternate_path(identity_row(), active_grant_source=None)
    with pytest.raises(FreeGrantRejected):
        exhausted_alternate_path(google_row(),
                                 active_grant_source=AccessGrantSource.subscription)


# --- Invariant 11: the registered account grant as the specified alternate path -------------------


# [utest->req~grants-invariant-11~1]
def test_registered_path_is_the_alternate_whenever_the_anonymous_path_is_closed() -> None:
    row = google_row()
    # Exhausted per-device state, an exhausted web provider-account gate, and a platform with no
    # supported anonymous gate at all all name the same alternate.
    assert registered_backstop(row, active_grant_source=None) is \
        AuthOperation.claim_registered_grant
    assert registered_backstop(
        row, active_grant_source=AccessGrantSource.anonymous_device_grant) is \
        AuthOperation.claim_registered_grant
    assert android_anonymous_path_available(device_recall_available=False) is False
    assert recall_absence_alternate() is AuthOperation.claim_registered_grant
    # The client must hold a Google or Apple account to take it.
    with pytest.raises(FreeGrantRejected):
        registered_backstop(identity_row(), active_grant_source=None)
    # It is an alternate for a closed anonymous gate, not a parallel path to an open one.
    with pytest.raises(FreeGrantError):
        registered_backstop(row, active_grant_source=None, anonymous_gate_exhausted=False)


# [utest->req~grants-invariant-11~1]
def test_registered_path_is_gated_on_the_accounts_own_grant_history() -> None:
    # A fresh account may claim; any committed free grant of either source refuses a new issuance.
    assert_account_grant_history(())
    for held in (AccessGrantSource.anonymous_device_grant,
                 AccessGrantSource.registered_account_grant):
        with pytest.raises(FreeGrantRejected):
            assert_account_grant_history((held,))
    # An upgraded account cannot hold carried anonymous credits and receive a fresh grant.
    with pytest.raises(FreeGrantRejected):
        assert_account_grant_history((), carried_anonymous_credits=True)
    # Converting the user's own active anonymous grant is the one permitted transition.
    assert_account_grant_history((AccessGrantSource.anonymous_device_grant,),
                                 converting_active_anonymous=True)


# [utest->req~grants-invariant-11~1]
def test_registered_eligibility_never_depends_on_the_original_claim_channel() -> None:
    # The native pin records which channel the original claim used. Eligibility never reads it: the
    # inputs are the stored provider, the stored `provider_uid` and the account's grant history.
    native = google_row(native_claim_platform=NativeClaimPlatform.ios_devicecheck)
    web = google_row(native_claim_platform=None)
    assert registered_eligibility(native, provider_data_confirmed=True) == \
        registered_eligibility(web, provider_data_confirmed=True)
    with pytest.raises(FreeGrantError):
        registered_eligibility(web, provider_data_confirmed=True,
                               consulted=("registered_at",))


# --- Invariant 12: one free entitlement per account, for the account's lifetime -------------------


# [utest->req~grants-invariant-12~1]
def test_the_marker_is_set_in_the_grant_transaction_and_never_re_stamped() -> None:
    transaction = object()
    marked = mark_free_grant_consumed(identity_row(), now=NOW, grant_transaction=transaction,
                                      marker_transaction=transaction)
    assert marked.free_grant_consumed_at == NOW
    # Set atomically in the transaction that commits the grant, and nowhere else.
    with pytest.raises(IdentityError):
        mark_free_grant_consumed(identity_row(), now=NOW, grant_transaction=transaction,
                                 marker_transaction=object())
    # A retry finds the same lineage already marked: no second lineage, no re-stamp.
    again = mark_free_grant_consumed(marked, now=NOW + timedelta(days=2),
                                     grant_transaction=transaction,
                                     marker_transaction=transaction)
    assert again.free_grant_consumed_at == NOW
    # And it is never cleared.
    with pytest.raises(IdentityError):
        clear_free_grant_marker(marked)


# [utest->req~grants-invariant-12~1]
def test_after_a_success_on_either_endpoint_the_other_refuses() -> None:
    consumed = google_row(free_grant_consumed_at=NOW)
    for endpoint in (AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant):
        assert free_grant_available(consumed, endpoint) is False
        assert free_grant_available(google_row(), endpoint) is True
    # The anonymous endpoint refuses under the lock, whichever branch it took.
    for branch in (ClaimBranch.native_ios, ClaimBranch.web):
        with pytest.raises(ClaimRejection) as rejected:
            reconfirm_claimant(consumed, branch)
        assert rejected.value.result is AuthEventResult.anti_abuse_already_claimed
    # So does the registered endpoint, on the new-grant destination.
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid=GOOGLE_UID)
    with pytest.raises(FreeGrantRejected):
        reconfirm_registered_claimant(consumed, account, NOW + timedelta(days=1),
                                      destination=RegisteredDestination.new_grant)


# [utest->req~grants-invariant-12~1]
def test_conversion_transitions_the_same_lineage_rather_than_issuing_a_second_one() -> None:
    consumed = google_row(free_grant_consumed_at=NOW)
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid=GOOGLE_UID)
    # An already-marked lineage is exactly what the conversion expects.
    assert reconfirm_registered_claimant(
        consumed, account, NOW + timedelta(days=1),
        destination=RegisteredDestination.supersession_conversion) is consumed
    assert_conversion_same_lineage(consumed, converted_at=NOW + timedelta(days=1))
    # A conversion never precedes the lineage it transitions, and never invents one.
    with pytest.raises(IdentityError):
        assert_conversion_same_lineage(consumed, converted_at=NOW - timedelta(days=1))
    with pytest.raises(IdentityError):
        assert_conversion_same_lineage(google_row(), converted_at=NOW)


# [utest->req~grants-invariant-12~1]
def test_the_marker_survives_retirement_and_erasure_and_outlives_the_gate_ledgers() -> None:
    assert "free_grant_consumed_at" in TOMBSTONE_RETAINED_COLUMNS
    consumed = google_row(free_grant_consumed_at=NOW)
    tombstone, profile = erase_account(consumed, profile={"email": "a@example.com"})
    # A tombstoned grant still counts as consumed: the marker is non-PII and survives erasure.
    assert tombstone.identity_state is IdentityState.historical
    assert tombstone.free_grant_consumed_at == NOW
    assert profile["email"] is None
    assert free_grant_available(tombstone, AuthOperation.claim_anonymous_grant) is False
    # The ledger rows beside it remain per-key abuse brakes in their own right.
    gates = ProviderAccountGates()
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid=GOOGLE_UID)
    gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
    with pytest.raises(GateAlreadyConsumedError):
        gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())


# [utest->req~grants-invariant-12~1]
def test_a_rejection_consumes_no_gate_slot_and_a_retry_takes_no_second_one() -> None:
    gates = ProviderAccountGates()
    ring = KeyRing(KeyFamily.k_idp_account, current=HmacKey(version=1, secret=b"i" * 32))
    index = IdpAccountAliasIndex(gates, ring)
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid=GOOGLE_UID)
    index.register(account)
    transaction = object()
    # A consumption the rules refuse burns no slot: the gate is still open afterwards.
    with pytest.raises(FreeGrantError):
        consume_free_grant_gate(index, account, GateConsumptionKind.registered_account_grant,
                                uuid7(), transaction=transaction, grant_transaction=object())
    assert gates.consumed_grant(account, GateConsumptionKind.registered_account_grant) is None
    grant_id = uuid7()
    consume_free_grant_gate(index, account, GateConsumptionKind.registered_account_grant, grant_id,
                            transaction=transaction, grant_transaction=transaction)
    assert gates.consumed_grant(account, GateConsumptionKind.registered_account_grant) == grant_id
    # A retry conflicts rather than opening a second slot, and the first grant keeps the row.
    with pytest.raises(GateAlreadyConsumedError):
        consume_free_grant_gate(index, account, GateConsumptionKind.registered_account_grant,
                                uuid7(), transaction=transaction, grant_transaction=transaction)
    assert gates.consumed_grant(account, GateConsumptionKind.registered_account_grant) == grant_id
    # The web anonymous gate is a separate row for the same provider account.
    assert gates.consumed_grant(account, GateConsumptionKind.web_anonymous_gate) is None


# [utest->req~grants-invariant-12~1]
def test_the_marker_is_authoritative_across_both_endpoints_for_one_account() -> None:
    # One account, one free entitlement: whichever endpoint set the marker, both then refuse.
    transaction = object()
    row = identity_row()
    after_anonymous = mark_free_grant_consumed(row, now=NOW, grant_transaction=transaction,
                                               marker_transaction=transaction)
    flipped = replace(after_anonymous, provider=IdentityProvider.google,
                      provider_uid=GOOGLE_UID)
    assert free_grant_available(flipped, AuthOperation.claim_registered_grant) is False
    with pytest.raises(IdentityError):
        free_grant_available(flipped, AuthOperation.create_user)
