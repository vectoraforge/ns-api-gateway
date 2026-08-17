"""Handler-side admission control and damping for the two free-credit grant claims."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from nativespeaker.api.auth.audit import AuthAttempt, AuthEventResult
from nativespeaker.api.auth.challenges import ChallengeState
from nativespeaker.api.auth.derived_identifiers import (
    HmacKey,
    IdpAccountAliasIndex,
    KeyFamily,
    KeyRing,
)
from nativespeaker.api.auth.external_identities import ExternalIdentityRow, IdentityState
from nativespeaker.api.auth.free_grants import FreeGrantRejected
from nativespeaker.api.auth.grant_admission import (
    ABUSE_SENSITIVE_HANDLER_WORK,
    DEVICE_BIT_BUDGETS,
    GRANT_ADMISSION_KEYS,
    NOT_ABUSE_SENSITIVE_HANDLER_WORK,
    REGISTERED_COMPLETE_ENTRY,
    REGISTERED_PREPARE_ENTRY,
    GrantAdmissionError,
    admission_rejection_leaves_challenge_unclaimed,
    anonymous_challenge_issuance_admission,
    anonymous_completion_admission,
    assert_admission_precedes_challenge_claim,
    assert_budgets_are_not_handler_admission,
    assert_configured_admission_keys,
    assert_exhausted_budget_stops_the_grant,
    assert_failed_challenge_charges_nothing,
    assert_handler_admission_required,
    assert_no_new_web_gate_entry,
    budget_call_kinds,
    device_bit_budget_step,
    handler_admission_entries,
    is_abuse_sensitive_handler_work,
    registered_challenge_issuance_admission,
    registered_completion_admission,
    web_provider_data_lookup,
)
from nativespeaker.api.auth.invariants import ProviderAccount, ProviderAccountGates
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_endpoints import ClaimBranch
from nativespeaker.api.ratelimit.config import RateLimitsConfig
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import (
    AdmissionLedger,
    AdmissionOrderError,
    DeviceBitCall,
)
from nativespeaker.api.ratelimit.rejection import DeviceBitBudgetExhausted, SecurityTelemetry

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
ANON_ROUTE = ("POST", "/auth/claim-anonymous-grant")
REG_ROUTE = ("POST", "/auth/claim-registered-grant")


def ledger_for(route: tuple[str, str], *,
               mode: RequestMode | None = None,
               barrier: bool = True) -> AdmissionLedger:
    ledger = AdmissionLedger(route[0], route[1], mode=mode)
    ledger.verify_jwt()
    if barrier:
        ledger.admit_barrier()
    return ledger


def alias_index() -> IdpAccountAliasIndex:
    ring = KeyRing(KeyFamily.k_idp_account, current=HmacKey(version=1, secret=b"i" * 32))
    return IdpAccountAliasIndex(ProviderAccountGates(), ring)


def google_row(*, provider_uid: str | None = "google-account-1",
               provider: IdentityProvider = IdentityProvider.google) -> ExternalIdentityRow:
    from uuid import uuid7

    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(),
                               issuer="https://securetoken.google.com/test-project",
                               subject="firebase-subject", provider=provider,
                               provider_uid=provider_uid,
                               identity_state=IdentityState.active)


def registered_alias(row: ExternalIdentityRow) -> Any:
    index = alias_index()
    return index.alias(ProviderAccount(provider=row.provider,
                                       provider_uid=row.provider_uid or ""))


def claimed_ledger(route: tuple[str, str], entries: tuple[str, ...]) -> AdmissionLedger:
    """A ledger that has passed completion admission and claimed its challenge."""
    ledger = ledger_for(route, mode=RequestMode.completion)
    for name in entries:
        ledger.evaluate(name, GRANT_ADMISSION_KEYS[name])
    ledger.challenge_state = ChallengeState.issued
    ledger.claim_challenge(entries)
    return ledger


# --- Which handler work is abuse-sensitive ----------------------------------------------------


# [utest->req~grants-handler-admission-required~1]
def test_the_named_entries_damp_every_piece_of_abuse_sensitive_handler_work() -> None:
    for operation in (AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant):
        entries = assert_handler_admission_required(operation)
        assert entries
        assert handler_admission_entries(operation, "prepare")
        assert handler_admission_entries(operation, "complete")
    assert set(ABUSE_SENSITIVE_HANDLER_WORK) == {
        "operation_challenge_issuance", "device_check_vendor_query",
        "fail_closed_vendor_bit_write", "cloudflare_bot_check_validation",
        "web_anonymous_grant_firebase_lookup", "grant_activation"}
    for work in ABUSE_SENSITIVE_HANDLER_WORK:
        assert is_abuse_sensitive_handler_work(work) is True


# [utest->req~grants-handler-admission-required~1]
def test_the_handler_side_limits_are_additional_to_the_shared_budgets() -> None:
    for operation in (AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant):
        entries = set(assert_handler_admission_required(operation))
        assert not entries & set(DEVICE_BIT_BUDGETS)
        assert "adapter_cloudflare_turnstile_siteverify" not in entries
        assert "adapter_firebase_lookup" not in entries
    with pytest.raises(GrantAdmissionError):
        assert_handler_admission_required(AuthOperation.sync)
    with pytest.raises(GrantAdmissionError):
        handler_admission_entries(AuthOperation.claim_anonymous_grant, "activation")


def test_app_attest_verification_is_not_abuse_sensitive_handler_work() -> None:
    assert NOT_ABUSE_SENSITIVE_HANDLER_WORK == frozenset({"app_attest_verification"})
    assert is_abuse_sensitive_handler_work("app_attest_verification") is False
    assert is_abuse_sensitive_handler_work("device_check_vendor_query") is True
    assert is_abuse_sensitive_handler_work("fail_closed_vendor_bit_write") is True
    assert is_abuse_sensitive_handler_work("grant_activation") is True


def test_the_shipped_configuration_carries_the_declared_admission_keys() -> None:
    shipped = yaml.safe_load(CONFIG_PATH.read_text())["rate_limits"]
    assert_configured_admission_keys(RateLimitsConfig(**shipped))


# --- `claim_anonymous_grant` admission --------------------------------------------------------


# [utest->req~grants-anon-challenge-issuance-admission~1]
def test_challenge_issuance_admission_runs_before_the_challenge_is_issued() -> None:
    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.prepare)
    ip_entry, user_entry = anonymous_challenge_issuance_admission(ledger)
    assert ledger.evaluated.index(ip_entry) < ledger.evaluated.index(user_entry)
    assert ledger.challenge_state is ChallengeState.issued
    assert GRANT_ADMISSION_KEYS[user_entry] == (KeyComponent.user,)
    assert GRANT_ADMISSION_KEYS[ip_entry] == (KeyComponent.ip,)


# [utest->req~grants-anon-challenge-issuance-admission~1]
def test_a_refused_challenge_issuance_admission_issues_no_challenge() -> None:
    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.prepare)
    anonymous_challenge_issuance_admission(ledger, user_allowed=False)
    assert ledger.refused is True
    assert ledger.challenge_issued is False

    already = ledger_for(ANON_ROUTE, mode=RequestMode.prepare)
    anonymous_challenge_issuance_admission(already)
    with pytest.raises(GrantAdmissionError):
        anonymous_challenge_issuance_admission(already)


# [utest->req~grants-anon-challenge-issuance-admission~1]
def test_the_user_counter_runs_only_once_the_barrier_admitted_the_caller() -> None:
    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.prepare, barrier=False)
    with pytest.raises(AdmissionOrderError):
        anonymous_challenge_issuance_admission(ledger)


# [utest->req~grants-anon-completion-admission~1]
def test_completion_admission_is_keyed_by_user_identically_on_every_branch() -> None:
    for branch in ClaimBranch:
        ledger = ledger_for(ANON_ROUTE, mode=RequestMode.completion)
        ip_entry, user_entry = anonymous_completion_admission(ledger, identity_resolved=True,
                                                             branch=branch)
        assert (ip_entry, user_entry) == ("claim_anonymous_grant_ip", "claim_anonymous_grant")
        assert GRANT_ADMISSION_KEYS[user_entry] == (KeyComponent.user,)
        assert GRANT_ADMISSION_KEYS[ip_entry] == (KeyComponent.ip,)


# [utest->req~grants-anon-completion-admission~1]
def test_completion_admission_runs_after_identity_and_before_expensive_work() -> None:
    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.completion)
    with pytest.raises(GrantAdmissionError):
        anonymous_completion_admission(ledger, identity_resolved=False)

    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.completion)
    entries = handler_admission_entries(AuthOperation.claim_anonymous_grant, "complete")
    for name in entries:
        ledger.evaluate(name, GRANT_ADMISSION_KEYS[name])
    ledger.challenge_state = ChallengeState.issued
    ledger.claim_challenge(entries)
    web_provider_data_lookup(ledger)
    with pytest.raises(GrantAdmissionError):
        anonymous_completion_admission(ledger, identity_resolved=True)


# [utest->req~grants-anon-completion-admission~1]
def test_no_admission_key_carries_a_device_check_or_bot_check_component() -> None:
    for policy in GRANT_ADMISSION_KEYS.values():
        assert set(policy) <= {KeyComponent.user, KeyComponent.ip, KeyComponent.idp_account_hash}
    assert_no_new_web_gate_entry()


# [utest->req~grants-anon-completion-admission~1]
def test_the_web_provider_data_lookup_runs_behind_the_completion_boundary() -> None:
    entries = handler_admission_entries(AuthOperation.claim_anonymous_grant, "complete")
    ledger = claimed_ledger(ANON_ROUTE, entries)
    assert web_provider_data_lookup(ledger).value == "firebase_lookup"

    unguarded = ledger_for(ANON_ROUTE, mode=RequestMode.completion)
    with pytest.raises(AdmissionOrderError):
        web_provider_data_lookup(unguarded)


# --- `claim_registered_grant` admission -------------------------------------------------------


# [utest->req~grants-reg-challenge-issuance-admission~1]
def test_registered_challenge_issuance_admission_is_keyed_by_user() -> None:
    ledger = ledger_for(REG_ROUTE, mode=RequestMode.prepare)
    assert registered_challenge_issuance_admission(ledger) == REGISTERED_PREPARE_ENTRY
    assert GRANT_ADMISSION_KEYS[REGISTERED_PREPARE_ENTRY] == (KeyComponent.user,)
    assert ledger.challenge_state is ChallengeState.issued

    refused = ledger_for(REG_ROUTE, mode=RequestMode.prepare)
    registered_challenge_issuance_admission(refused, allowed=False)
    assert refused.challenge_issued is False


# [utest->req~grants-reg-completion-admission~1]
def test_registered_completion_admission_is_keyed_by_user_and_account_alias() -> None:
    row = google_row()
    ledger = ledger_for(REG_ROUTE, mode=RequestMode.completion)
    entry = registered_completion_admission(ledger, row, registered_alias(row))
    assert entry == REGISTERED_COMPLETE_ENTRY
    assert GRANT_ADMISSION_KEYS[entry] == (KeyComponent.user, KeyComponent.idp_account_hash)
    assert ledger.evaluated == [REGISTERED_COMPLETE_ENTRY]


# [utest->req~grants-reg-completion-admission~1]
def test_registered_completion_admission_precedes_the_provider_data_confirmation() -> None:
    row = google_row()
    ledger = ledger_for(REG_ROUTE, mode=RequestMode.completion)
    with pytest.raises(GrantAdmissionError):
        registered_completion_admission(ledger, row, registered_alias(row),
                                        provider_data_lookups=1)
    with pytest.raises(GrantAdmissionError):
        registered_completion_admission(ledger, row, registered_alias(row),
                                        firebase_calls_for_alias=1)


# [utest->req~grants-reg-completion-admission~1]
def test_a_row_without_provider_uid_follows_the_policy_rejection_path() -> None:
    ledger = ledger_for(REG_ROUTE, mode=RequestMode.completion)
    # A stored row that lost its `provider_uid` is the case the rejection path exists for; the
    # row invariant forbids writing one, so it is simulated here rather than constructed.
    row = google_row()
    object.__setattr__(row, "provider_uid", "")
    with pytest.raises(FreeGrantRejected) as absent:
        registered_completion_admission(ledger, row, registered_alias(google_row()))
    assert absent.value.result is AuthEventResult.idp_account_not_eligible
    assert absent.value.error_code == "verification_required"
    assert ledger.evaluated == []

    anonymous = google_row(provider=IdentityProvider.anonymous, provider_uid=None)
    with pytest.raises(FreeGrantRejected) as ineligible:
        registered_completion_admission(ledger, anonymous, registered_alias(google_row()))
    assert ineligible.value.result is AuthEventResult.idp_account_not_eligible
    assert ledger.evaluated == []


# --- The boundary -----------------------------------------------------------------------------


# [utest->req~grants-admission-before-challenge-claim~1]
def test_the_named_admission_limits_are_placed_before_the_challenge_claim() -> None:
    entries = handler_admission_entries(AuthOperation.claim_anonymous_grant, "complete")
    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.completion)
    with pytest.raises(GrantAdmissionError):
        assert_admission_precedes_challenge_claim(ledger, AuthOperation.claim_anonymous_grant)
    anonymous_completion_admission(ledger, identity_resolved=True)
    assert assert_admission_precedes_challenge_claim(
        ledger, AuthOperation.claim_anonymous_grant) == entries
    ledger.challenge_state = ChallengeState.issued
    ledger.claim_challenge(entries)
    with pytest.raises(GrantAdmissionError):
        assert_admission_precedes_challenge_claim(ledger, AuthOperation.claim_anonymous_grant)


# [utest->req~grants-admission-before-challenge-claim~1]
def test_an_admission_rejection_leaves_the_challenge_unclaimed_and_unaudited() -> None:
    attempt = AuthAttempt(*ANON_ROUTE)
    decision = LimitDecision(allowed=False, limiter="claim_anonymous_grant")
    rejection = admission_rejection_leaves_challenge_unclaimed(attempt, SecurityTelemetry(),
                                                               decision)
    assert rejection.challenge_state is ChallengeState.issued
    assert rejection.audit_rows == 0
    assert rejection.database_rows == 0
    assert rejection.telemetry.reason == "claim_anonymous_grant"
    with pytest.raises(GrantAdmissionError):
        admission_rejection_leaves_challenge_unclaimed(
            AuthAttempt(*ANON_ROUTE), SecurityTelemetry(), decision,
            challenge_state=ChallengeState.claimed)


# --- The device-bit budgets, on the other side of the boundary ---------------------------------


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_the_four_budgets_are_provider_budgets_not_handler_admission_limits() -> None:
    assert_budgets_are_not_handler_admission()
    assert DEVICE_BIT_BUDGETS == ("adapter_devicecheck_read", "adapter_devicecheck_write",
                                  "adapter_play_integrity_device_recall_read",
                                  "adapter_play_integrity_device_recall_write")
    reads, writes = budget_call_kinds()
    assert reads == {DeviceBitCall.devicecheck_read, DeviceBitCall.device_recall_read}
    assert writes == {DeviceBitCall.devicecheck_write, DeviceBitCall.device_recall_write}


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_a_budget_is_checked_only_after_the_challenge_has_been_claimed() -> None:
    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.completion)
    anonymous_completion_admission(ledger, identity_resolved=True)
    with pytest.raises(AdmissionOrderError):
        device_bit_budget_step(ledger, DeviceBitCall.devicecheck_read,
                               operation=AuthOperation.claim_anonymous_grant)


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_each_budget_is_checked_immediately_before_the_call_it_budgets() -> None:
    entries = handler_admission_entries(AuthOperation.claim_anonymous_grant, "complete")
    ledger = claimed_ledger(ANON_ROUTE, entries)
    assert device_bit_budget_step(ledger, DeviceBitCall.devicecheck_read,
                                  operation=AuthOperation.claim_anonymous_grant) is None
    write = device_bit_budget_step(ledger, DeviceBitCall.devicecheck_write,
                                   operation=AuthOperation.claim_anonymous_grant)
    assert write is not None and write.confirmed is True
    assert ledger.budgets_checked == ["adapter_devicecheck_read", "adapter_devicecheck_write"]
    ledger.insert_grant_row()


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_an_exhausted_read_budget_stops_every_later_step_of_the_claim() -> None:
    entries = handler_admission_entries(AuthOperation.claim_anonymous_grant, "complete")
    ledger = claimed_ledger(ANON_ROUTE, entries)
    with pytest.raises(DeviceBitBudgetExhausted) as exhausted:
        device_bit_budget_step(ledger, DeviceBitCall.devicecheck_read,
                               operation=AuthOperation.claim_anonymous_grant, allowed=False)
    rejection = exhausted.value.rejection
    assert rejection.result is AuthEventResult.devicecheck_read_budget_exhausted
    assert rejection.client.status != 429
    assert rejection.client.body["code"] == "verification_temporarily_unavailable"
    assert rejection.challenge_state is ChallengeState.consumed
    assert rejection.audit_rows == 1
    assert ledger.device_bit_calls == []
    assert_exhausted_budget_stops_the_grant(ledger)


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_an_exhausted_write_budget_stops_the_write_and_the_grant() -> None:
    entries = handler_admission_entries(AuthOperation.claim_anonymous_grant, "complete")
    ledger = claimed_ledger(ANON_ROUTE, entries)
    device_bit_budget_step(ledger, DeviceBitCall.device_recall_read,
                           operation=AuthOperation.claim_anonymous_grant)
    with pytest.raises(DeviceBitBudgetExhausted) as exhausted:
        device_bit_budget_step(ledger, DeviceBitCall.device_recall_write,
                               operation=AuthOperation.claim_anonymous_grant, allowed=False)
    assert exhausted.value.rejection.result \
        is AuthEventResult.device_recall_write_budget_exhausted
    assert ledger.device_bit_writes == []
    assert_exhausted_budget_stops_the_grant(ledger)


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_one_internal_result_per_budget_entry_in_that_order() -> None:
    entries = handler_admission_entries(AuthOperation.claim_registered_grant, "complete")
    expected = (AuthEventResult.devicecheck_read_budget_exhausted,
                AuthEventResult.devicecheck_write_budget_exhausted,
                AuthEventResult.device_recall_read_budget_exhausted,
                AuthEventResult.device_recall_write_budget_exhausted)
    calls = (DeviceBitCall.devicecheck_read, DeviceBitCall.devicecheck_write,
             DeviceBitCall.device_recall_read, DeviceBitCall.device_recall_write)
    for call, result in zip(calls, expected, strict=True):
        ledger = claimed_ledger(REG_ROUTE, entries)
        if call in {DeviceBitCall.devicecheck_write, DeviceBitCall.device_recall_write}:
            device_bit_budget_step(ledger, DeviceBitCall.devicecheck_read,
                                   operation=AuthOperation.claim_registered_grant)
        with pytest.raises(DeviceBitBudgetExhausted) as exhausted:
            device_bit_budget_step(ledger, call,
                                   operation=AuthOperation.claim_registered_grant,
                                   allowed=False)
        assert exhausted.value.rejection.result is result


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_a_challenge_that_fails_validation_charges_no_device_bit_budget() -> None:
    ledger = ledger_for(ANON_ROUTE, mode=RequestMode.completion)
    anonymous_completion_admission(ledger, identity_resolved=True)
    ledger.challenge_state = ChallengeState.issued
    ledger.fail_challenge_validation()
    with pytest.raises(AdmissionOrderError):
        device_bit_budget_step(ledger, DeviceBitCall.devicecheck_read,
                               operation=AuthOperation.claim_anonymous_grant)
    assert_failed_challenge_charges_nothing(ledger)


# [utest->req~grants-device-bit-budgets-post-claim~1]
def test_only_a_free_credit_claim_charges_a_device_bit_budget() -> None:
    entries = handler_admission_entries(AuthOperation.claim_anonymous_grant, "complete")
    ledger = claimed_ledger(ANON_ROUTE, entries)
    with pytest.raises(GrantAdmissionError):
        device_bit_budget_step(ledger, DeviceBitCall.devicecheck_read,
                               operation=AuthOperation.sync)
