"""Rejection and telemetry: what a rejection returns and what it must not leave behind."""

import pytest

from nativespeaker.api.auth.audit import AuthAttempt, AuthEventResult
from nativespeaker.api.auth.challenges import ChallengeState
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.ratelimit.config import DEVICE_BIT_BUDGET_ENTRIES, TURNSTILE_ENTRY
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.rejection import (
    ADMISSION_REJECTION_STATUS,
    DEVICE_BIT_BUDGET_RESULTS,
    FIREBASE_LOOKUP_BUDGETS,
    AdmissionPhase,
    AdmissionPhaseError,
    BudgetExhaustionError,
    CoarseActor,
    FailClosedScopeError,
    RateLimitMetrics,
    SecurityTelemetry,
    admission_rejection,
    assert_aggregate_only,
    assert_fail_closed_scope,
    budget_denies,
    budget_exhaustion_class,
    device_bit_budget_rejection,
)

RESTORE = ("POST", "/auth/restore-subscription")
CLAIM = ("POST", "/auth/claim-anonymous-grant")


def refused(limiter: str = "claim_anonymous_grant",
            retry_after: int | None = 42) -> LimitDecision:
    return LimitDecision(allowed=False, limiter=limiter, retry_after_seconds=retry_after,
                         exhausted=(limiter,))


# --- The 429 ------------------------------------------------------------------------------------

# [utest->req~ratelimit-reject-429-with-retry-after~1]
def test_a_rejection_is_a_429_carrying_retry_after():
    error = admission_rejection(refused(retry_after=42))
    assert error.status_code == 429
    assert error.extra_headers() == {"Retry-After": "42"}


# [utest->req~ratelimit-reject-429-with-retry-after~1]
def test_no_retry_after_when_the_backend_cannot_compute_a_reset_time():
    # A storage failure that fails closed rejects with no computable reset time: the response is
    # still a 429, and it carries no fabricated header.
    error = admission_rejection(LimitDecision(allowed=False, limiter="create_user",
                                              storage_failed=True))
    assert error.status_code == 429
    assert error.extra_headers() is None


# [utest->req~ratelimit-reject-429-with-retry-after~1]
def test_an_admitted_verdict_is_no_rejection():
    with pytest.raises(ValueError, match="admitted"):
        admission_rejection(LimitDecision(allowed=True, limiter="create_user"))


# --- Budget exhaustion classes ------------------------------------------------------------------

# [utest->req~ratelimit-firebase-budget-exhaustion-class~1]
@pytest.mark.parametrize("entry", FIREBASE_LOOKUP_BUDGETS)
def test_every_firebase_lookup_budget_maps_to_verification_temporarily_unavailable(entry):
    assert budget_exhaustion_class(entry) is ClientErrorClass.verification_temporarily_unavailable


# [utest->req~ratelimit-firebase-budget-exhaustion-class~1]
def test_the_firebase_budgets_are_the_four_this_file_defines():
    assert set(FIREBASE_LOOKUP_BUDGETS) == {
        "create_user_firebase_identity_lookup",
        "create_user_firebase_identity_lookup_ip",
        "upgrade_anonymous_to_registered_firebase_identity_lookup",
        "adapter_firebase_lookup"}
    with pytest.raises(BudgetExhaustionError):
        budget_exhaustion_class("claim_anonymous_grant")


# [utest->req~ratelimit-device-bit-budget-exhaustion-class~1]
@pytest.mark.parametrize("entry", DEVICE_BIT_BUDGET_ENTRIES)
def test_a_device_bit_budget_is_a_verification_capacity_condition_not_a_429(entry):
    rejection = device_bit_budget_rejection(entry, AuthOperation.claim_anonymous_grant,
                                            challenge_state=ChallengeState.claimed)
    assert rejection.client.body["code"] == ClientErrorClass.verification_temporarily_unavailable
    assert rejection.client.status != ADMISSION_REJECTION_STATUS


# [utest->req~ratelimit-device-bit-budget-exhaustion-class~1]
def test_each_budget_names_its_own_internal_result_in_order():
    assert list(DEVICE_BIT_BUDGET_RESULTS) == list(DEVICE_BIT_BUDGET_ENTRIES)
    assert list(DEVICE_BIT_BUDGET_RESULTS.values()) == [
        AuthEventResult.devicecheck_read_budget_exhausted,
        AuthEventResult.devicecheck_write_budget_exhausted,
        AuthEventResult.device_recall_read_budget_exhausted,
        AuthEventResult.device_recall_write_budget_exhausted]


# [utest->req~ratelimit-device-bit-budget-exhaustion-class~1]
def test_the_rejection_is_audited_consumes_the_challenge_and_issues_no_grant():
    rejection = device_bit_budget_rejection("adapter_devicecheck_write",
                                            AuthOperation.claim_anonymous_grant,
                                            challenge_state=ChallengeState.claimed)
    # Already on the audited attempt path: one row for the attempt, naming the exhausted budget.
    assert rejection.audit_rows == 1
    assert rejection.result is AuthEventResult.devicecheck_write_budget_exhausted
    # Fails closed against the free grant alone, and the call whose budget was unavailable is
    # not performed.
    assert rejection.grant_issued is False
    assert rejection.vendor_call_performed is False
    # The claimed challenge is consumed with the rejection and never returned to `issued`.
    assert rejection.challenge_state is ChallengeState.consumed


# [utest->req~ratelimit-device-bit-budget-exhaustion-class~1]
def test_a_device_bit_budget_is_never_checked_before_the_challenge_is_claimed():
    for state in (ChallengeState.issued, ChallengeState.consumed):
        with pytest.raises(BudgetExhaustionError, match="claimed"):
            device_bit_budget_rejection("adapter_devicecheck_read",
                                        AuthOperation.claim_anonymous_grant,
                                        challenge_state=state)


# --- Fail-closed scope --------------------------------------------------------------------------

# [utest->req~ratelimit-fail-closed-scoped-to-free-grant~1]
@pytest.mark.parametrize("entry", [*DEVICE_BIT_BUDGET_ENTRIES, TURNSTILE_ENTRY])
@pytest.mark.parametrize("operation", list(AuthOperation))
def test_a_fail_closed_budget_denies_only_the_free_grant(entry, operation):
    denies = budget_denies(entry, operation)
    assert denies is (operation in {AuthOperation.claim_anonymous_grant,
                                    AuthOperation.claim_registered_grant})


# [utest->req~ratelimit-fail-closed-scoped-to-free-grant~1]
@pytest.mark.parametrize("operation", [AuthOperation.create_user,
                                       AuthOperation.upgrade_anonymous_to_registered,
                                       AuthOperation.sync,
                                       AuthOperation.restore_subscription])
def test_it_never_blocks_creation_upgrade_sync_or_a_paid_entitlement_path(operation):
    with pytest.raises(FailClosedScopeError):
        assert_fail_closed_scope(TURNSTILE_ENTRY, operation)
    with pytest.raises(FailClosedScopeError):
        device_bit_budget_rejection("adapter_devicecheck_read", operation,
                                    challenge_state=ChallengeState.claimed)


# --- Admission rejections stay off the audited attempt path -------------------------------------

# [utest->req~ratelimit-admission-rejections-off-audited-path~1]
def test_an_admission_rejection_on_a_state_changing_route_writes_no_audit_row():
    attempt = AuthAttempt(*RESTORE)
    assert attempt.on_audited_path
    phase = AdmissionPhase(attempt, SecurityTelemetry())
    rejection = phase.reject(refused("restore_subscription_user"))
    assert rejection.audit_rows == 0
    assert rejection.database_rows == 0
    assert attempt.audited is False


# [utest->req~ratelimit-admission-rejections-off-audited-path~1]
def test_an_admission_rejection_consumes_no_operation_challenge():
    attempt = AuthAttempt(*CLAIM)
    phase = AdmissionPhase(attempt, SecurityTelemetry(),
                           challenge_state=ChallengeState.issued)
    rejection = phase.reject(refused())
    assert rejection.challenge_state is ChallengeState.issued


# [utest->req~ratelimit-admission-rejections-off-audited-path~1]
def test_a_request_already_audited_is_no_admission_rejection():
    attempt = AuthAttempt(*CLAIM)
    attempt.audited = True
    with pytest.raises(AdmissionPhaseError):
        AdmissionPhase(attempt, SecurityTelemetry()).reject(refused())


# --- Pre-admission telemetry --------------------------------------------------------------------

# [utest->req~ratelimit-pre-admission-aggregate-telemetry~1]
def test_a_suppressed_rejection_leaves_one_aggregate_record_and_nothing_else():
    attempt = AuthAttempt(*RESTORE)
    telemetry = SecurityTelemetry()
    phase = AdmissionPhase(attempt, telemetry)
    phase.reject(refused("restore_subscription_user"), actor=CoarseActor.authenticated)
    # It carries the name of the limiter that fired, keyed by route and coarse actor.
    assert telemetry.value(route="/auth/restore-subscription",
                           reason="restore_subscription_user",
                           actor=CoarseActor.authenticated) == 1
    assert telemetry.labels() == [("/auth/restore-subscription",
                                   "restore_subscription_user",
                                   "authenticated")]


# [utest->req~ratelimit-pre-admission-aggregate-telemetry~1]
def test_the_aggregate_is_bounded_by_route_reason_and_coarse_actor():
    telemetry = SecurityTelemetry()
    for _ in range(5):
        telemetry.record(route="/auth/create-user", reason="create_user",
                         actor=CoarseActor.anonymous)
    assert len(telemetry.labels()) == 1
    with pytest.raises(ValueError):
        telemetry.record(route="/auth/create-user", reason="create_user",
                         actor="user-42")  # ty: ignore[invalid-argument-type]


# [utest->req~ratelimit-pre-admission-aggregate-telemetry~1]
def test_no_raw_proof_provider_payload_or_restore_audit_data_is_stored():
    assert_aggregate_only({"route": "/auth/restore-subscription", "reason": "x",
                           "actor": "anonymous"})
    for forbidden in ("restore_proof", "provider_payload", "auth_event"):
        with pytest.raises(AdmissionPhaseError, match=forbidden):
            assert_aggregate_only({"route": "/r", "reason": "x", "actor": "anonymous",
                                   forbidden: "..."})


# --- Operational counters ------------------------------------------------------------------------

# [utest->req~ratelimit-operational-counters~1]
def test_the_backend_exposes_the_five_operational_counters():
    metrics = RateLimitMetrics()
    assert set(metrics.counters()) == {"allowed_requests", "rejections_429", "storage_failures",
                                       "provider_budget_rejections", "coalesced_provider_reuse"}
    metrics.observe(LimitDecision(allowed=True, limiter="users_me"))
    metrics.observe(refused())
    metrics.observe(LimitDecision(allowed=False, limiter="create_user", storage_failed=True))
    metrics.provider_budget_rejected("adapter_firebase_lookup")
    metrics.coalesced_reuse()
    assert metrics.counters() == {"allowed_requests": 1, "rejections_429": 2,
                                  "storage_failures": 1, "provider_budget_rejections": 1,
                                  "coalesced_provider_reuse": 1}
    assert metrics.exhausted("adapter_firebase_lookup") == 1
