"""Failure handling for `claim_registered_grant`, and the registered alternate path.

Three questions live here. Which client-visible class a registered claim that cannot complete
surfaces, and from which condition. What the in-request retry policy is, and which rejections spend
no budget at all. And what the client must do when `claim_anonymous_grant` closes durably — the
registered account grant being the specified alternate free-credit path, with its own gates and no
guarantee of success.

Every mapping is one-way and single-sourced: the registry itself is `taxonomy.py`'s, the shared
catalog classes are `00-overview-and-shared-contracts.md`'s, the anonymous claim's own conditions
are `grant_failures`', and the operation's rules are `registered_grants`'. This module adds no
second copy of any of them.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    ProviderLookupFailedError,
)
from nativespeaker.api.auth.free_grants import (
    FreeGrantError,
    FreeGrantRejected,
    further_free_credit_path,
    non_accusatory_copy,
)
from nativespeaker.api.auth.grant_failures import (
    VENDOR_STATE_RECONCILERS,
    AnonFailureCondition,
    BurnedSlotCause,
    GrantFailureError,
    accepted_burned_slot,
    anonymous_remediation,
    assert_retries_not_bounded_by_expiry,
    classify_anonymous_failure,
    completion_rejection,
    grants_client_class,
    transient_failure_class,
    whole_claim_retry,
)
from nativespeaker.api.auth.invariants import GateConsumptionKind
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_adapters import (
    COMPLETION_ATTEMPT_CAP,
    ClaimRejection,
    stranded_slot_remediation,
)
from nativespeaker.api.auth.proof_endpoints import (
    UPGRADE_IS_IN_PLACE,
    ClaimBranch,
    GateDenied,
    web_anonymous_grant_gate,
)
from nativespeaker.api.auth.registered_grants import (
    ACCOUNT_LAYER_BINDINGS,
    DEVICE_CHECKED_KINDS,
    REGISTERED_GRANT_GATE,
    RegisteredDestinationBlocked,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass, client_response, remediation_for
from nativespeaker.api.ratelimit.ordering import DeviceBitWrite, assert_grant_row_permitted

# --- The classes `claim_registered_grant` may surface ---------------------------------------------

# Every client-visible class this operation surfaces when the user cannot complete a registered
# account grant claim. The set is closed: `registered_emitted_classes` reads the condition table
# back and refuses if the two ever disagree.
# [impl->req~grants-reg-failure-classes~1]
REG_CLIENT_CLASSES: tuple[ClientErrorClass, ...] = (
    ClientErrorClass.auth_required,
    ClientErrorClass.preauth_identity_not_allowed,
    ClientErrorClass.account_unavailable,
    ClientErrorClass.operation_not_allowed,
    ClientErrorClass.verification_required,
    ClientErrorClass.device_grant_exhausted,
    ClientErrorClass.account_already_claimed,
    ClientErrorClass.verification_temporarily_unavailable,
    ClientErrorClass.proof_rejected,
)


class RegClaimCondition(StrEnum):
    """Every condition that stops a `claim_registered_grant` from completing."""
    preauth_or_unlinked_caller = "preauth_or_unlinked_caller"
    blocked_or_inactive_user = "blocked_or_inactive_user"
    historical_identity = "historical_identity"
    destination_incompatible_active_grant = "destination_incompatible_active_grant"
    structural_policy_block = "structural_policy_block"
    stored_provider_not_google_or_apple = "stored_provider_not_google_or_apple"
    stored_provider_uid_absent = "stored_provider_uid_absent"
    ios_registered_bit_set = "ios_registered_bit_set"
    android_registered_recall_set = "android_registered_recall_set"
    registered_gate_consumed = "registered_gate_consumed"
    device_check_vendor_outage = "device_check_vendor_outage"
    registered_bit_write_failed = "registered_bit_write_failed"
    firebase_provider_data_unavailable = "firebase_provider_data_unavailable"
    firebase_user_not_found = "firebase_user_not_found"
    turnstile_denied = "turnstile_denied"
    turnstile_dependency_failed = "turnstile_dependency_failed"
    incomplete_platform_proof_set = "incomplete_platform_proof_set"
    evidence_set_shape_invalid = "evidence_set_shape_invalid"


@dataclass(frozen=True, slots=True)
class RegFailure:
    """One condition, the internal result its audit row records, the class it surfaces as, and
    whether it is durable, retryable, or reached only after the in-request retry budget."""
    condition: RegClaimCondition
    result: AuthEventResult
    client_class: ClientErrorClass
    durable: bool = False
    retryable: bool = False
    after_retry_budget: bool = False


REG_FAILURES: dict[RegClaimCondition, RegFailure] = {
    # A pre-auth or otherwise unlinked caller of this linked-only endpoint.
    # [impl->req~grants-reg-class-preauth-identity-not-allowed~1]
    RegClaimCondition.preauth_or_unlinked_caller: RegFailure(
        RegClaimCondition.preauth_or_unlinked_caller,
        AuthEventResult.preauth_identity_not_allowed,
        ClientErrorClass.preauth_identity_not_allowed, durable=True),
    # An inactive or blocked user and a historical identity: distinct internal audit results under
    # the one shared class.
    # [impl->req~grants-reg-class-account-unavailable~1]
    RegClaimCondition.blocked_or_inactive_user: RegFailure(
        RegClaimCondition.blocked_or_inactive_user, AuthEventResult.blocked_user,
        ClientErrorClass.account_unavailable, durable=True),
    # [impl->req~grants-reg-class-account-unavailable~1]
    RegClaimCondition.historical_identity: RegFailure(
        RegClaimCondition.historical_identity, AuthEventResult.historical_identity,
        ClientErrorClass.account_unavailable, durable=True),
    # An active grant that blocks the destination, and the other structural policy blocks.
    # [impl->req~grants-reg-class-operation-not-allowed~1]
    RegClaimCondition.destination_incompatible_active_grant: RegFailure(
        RegClaimCondition.destination_incompatible_active_grant,
        AuthEventResult.registered_grant_destination_incompatible,
        ClientErrorClass.operation_not_allowed),
    # [impl->req~grants-reg-class-operation-not-allowed~1]
    RegClaimCondition.structural_policy_block: RegFailure(
        RegClaimCondition.structural_policy_block, AuthEventResult.policy_rejected,
        ClientErrorClass.operation_not_allowed),
    # The stored binding is not `google`/`apple`, or carries no `provider_uid`.
    # [impl->req~grants-reg-class-verification-required~1]
    RegClaimCondition.stored_provider_not_google_or_apple: RegFailure(
        RegClaimCondition.stored_provider_not_google_or_apple,
        AuthEventResult.idp_account_not_eligible, ClientErrorClass.verification_required,
        durable=True),
    # [impl->req~grants-reg-class-verification-required~1]
    RegClaimCondition.stored_provider_uid_absent: RegFailure(
        RegClaimCondition.stored_provider_uid_absent, AuthEventResult.idp_account_not_eligible,
        ClientErrorClass.verification_required, durable=True),
    # An already-set registered-claimed device state on the two device-checked kinds.
    # [impl->req~grants-reg-class-device-grant-exhausted~1]
    RegClaimCondition.ios_registered_bit_set: RegFailure(
        RegClaimCondition.ios_registered_bit_set, AuthEventResult.native_claim_already_claimed,
        ClientErrorClass.device_grant_exhausted, durable=True),
    # [impl->req~grants-reg-class-device-grant-exhausted~1]
    RegClaimCondition.android_registered_recall_set: RegFailure(
        RegClaimCondition.android_registered_recall_set,
        AuthEventResult.native_claim_already_claimed, ClientErrorClass.device_grant_exhausted,
        durable=True),
    # The registered gate is already consumed for this provider account.
    # [impl->req~grants-reg-class-account-already-claimed~1]
    RegClaimCondition.registered_gate_consumed: RegFailure(
        RegClaimCondition.registered_gate_consumed, AuthEventResult.idp_account_already_claimed,
        ClientErrorClass.account_already_claimed, durable=True),
    # The transient dependency failures, each reached only after the in-request retry budget.
    # [impl->req~grants-reg-class-verification-temporarily-unavailable~1]
    RegClaimCondition.device_check_vendor_outage: RegFailure(
        RegClaimCondition.device_check_vendor_outage, AuthEventResult.native_claim_unavailable,
        ClientErrorClass.verification_temporarily_unavailable, retryable=True,
        after_retry_budget=True),
    # A pre-activation registered-bit *write* whose budget is spent is the distinct write result:
    # only the write case can have burned the device slot, and it is the one the burned-slot
    # `manual`-grant remediation points at. The client class is the same as the read's.
    # [impl->req~grants-reg-class-verification-temporarily-unavailable~1]
    # [impl->req~grants-reg-retry-budget-exhausted~1]
    RegClaimCondition.registered_bit_write_failed: RegFailure(
        RegClaimCondition.registered_bit_write_failed, AuthEventResult.native_claim_write_failed,
        ClientErrorClass.verification_temporarily_unavailable, retryable=True,
        after_retry_budget=True),
    # [impl->req~grants-reg-class-verification-temporarily-unavailable~1]
    RegClaimCondition.firebase_provider_data_unavailable: RegFailure(
        RegClaimCondition.firebase_provider_data_unavailable,
        AuthEventResult.firebase_lookup_unavailable,
        ClientErrorClass.verification_temporarily_unavailable, retryable=True,
        after_retry_budget=True),
    # Firebase user-not-found at that read is non-retryable and surfaces as `auth_required`.
    # [impl->req~grants-reg-class-verification-temporarily-unavailable~1]
    RegClaimCondition.firebase_user_not_found: RegFailure(
        RegClaimCondition.firebase_user_not_found, AuthEventResult.firebase_user_unresolved,
        ClientErrorClass.auth_required, durable=True),
    # A Turnstile denial — invalid, expired, duplicate or replayed token, or a hostname mismatch
    # — is the web kind's unsatisfied sign-in gate: a durable `verification_required` rejection,
    # never the structural `operation_not_allowed` a *structural* policy block takes.
    # [impl->req~grants-reg-gate-resolve-claim-kind~1]
    RegClaimCondition.turnstile_denied: RegFailure(
        RegClaimCondition.turnstile_denied, AuthEventResult.policy_rejected,
        ClientErrorClass.verification_required, durable=True),
    # A Cloudflare Turnstile dependency failure records the class value itself as the result.
    # [impl->req~grants-reg-class-verification-temporarily-unavailable~1]
    RegClaimCondition.turnstile_dependency_failed: RegFailure(
        RegClaimCondition.turnstile_dependency_failed,
        AuthEventResult.verification_temporarily_unavailable,
        ClientErrorClass.verification_temporarily_unavailable, retryable=True,
        after_retry_budget=True),
    # Missing, malformed or partial platform proof for the selected kind, and the request-shape
    # error the zero-, multiple- or partial-evidence-set request is.
    # [impl->req~grants-reg-class-proof-rejected~1]
    RegClaimCondition.incomplete_platform_proof_set: RegFailure(
        RegClaimCondition.incomplete_platform_proof_set, AuthEventResult.proof_malformed,
        ClientErrorClass.proof_rejected, durable=True),
    # [impl->req~grants-reg-class-proof-rejected~1]
    RegClaimCondition.evidence_set_shape_invalid: RegFailure(
        RegClaimCondition.evidence_set_shape_invalid, AuthEventResult.proof_malformed,
        ClientErrorClass.proof_rejected, durable=True),
}


def classify_registered_failure(condition: RegClaimCondition) -> RegFailure:
    """The audited internal result and client-visible class one condition produces, read back
    through the shared registry so the two can never disagree."""
    # [impl->req~grants-reg-failure-classes~1]
    failure = REG_FAILURES.get(condition)
    if failure is None:
        raise GrantFailureError(f"{condition} classifies no registered-claim failure")
    structural = failure.client_class is ClientErrorClass.operation_not_allowed
    registered = grants_client_class(failure.result,
                                     operation=AuthOperation.claim_registered_grant,
                                     structural=structural)
    if registered is not failure.client_class:
        raise GrantFailureError(f"{failure.result} surfaces as {registered}, not "
                                f"{failure.client_class}")
    return failure


def registered_emitted_classes() -> frozenset[ClientErrorClass]:
    """The classes `claim_registered_grant` surfaces, checked exhaustively against the condition
    table: every declared class has at least one condition, and no condition produces a class
    outside the declared set."""
    # [impl->req~grants-reg-failure-classes~1]
    emitted = {classify_registered_failure(condition).client_class
               for condition in RegClaimCondition}
    declared = frozenset(REG_CLIENT_CLASSES)
    if emitted != declared:
        raise GrantFailureError(
            f"claim_registered_grant emits {sorted(str(name) for name in emitted)}")
    return declared


def registered_failure_class(condition: RegClaimCondition) -> ClientErrorClass:
    """The one class a condition surfaces as. The internal result stays behind."""
    # [impl->req~grants-reg-failure-classes~1]
    return classify_registered_failure(condition).client_class


def preauth_caller_rejection() -> RegFailure:
    """`preauth_identity_not_allowed` for a pre-auth or otherwise unlinked caller of this
    linked-only endpoint."""
    # [impl->req~grants-reg-class-preauth-identity-not-allowed~1]
    failure = classify_registered_failure(RegClaimCondition.preauth_or_unlinked_caller)
    if remediation_for(failure.client_class).next_route != "/auth/create-user":
        raise GrantFailureError("the unlinked caller is sent to create-user, then back here")
    return failure


def account_unavailable_results() -> tuple[AuthEventResult, ...]:
    """`account_unavailable` for an inactive or blocked user or a historical identity, with
    distinct internal audit results under the shared class."""
    # [impl->req~grants-reg-class-account-unavailable~1]
    conditions = (RegClaimCondition.blocked_or_inactive_user, RegClaimCondition.historical_identity)
    results = tuple(classify_registered_failure(condition).result for condition in conditions)
    if len(set(results)) != len(results):
        raise GrantFailureError("the two account states keep distinct internal results")
    classes = {classify_registered_failure(condition).client_class for condition in conditions}
    if classes != {ClientErrorClass.account_unavailable}:
        raise GrantFailureError("both states surface as the one shared account_unavailable class")
    return results


def verification_required_conditions() -> tuple[RegClaimCondition, ...]:
    """`verification_required` for `idp_account_not_eligible`: the stored provider is not `google`
    or `apple`, or its stored `provider_uid` is absent. The client signs in with, upgrades to, or
    links a Google or Apple identity and retries."""
    # [impl->req~grants-reg-class-verification-required~1]
    conditions = (RegClaimCondition.stored_provider_not_google_or_apple,
                  RegClaimCondition.stored_provider_uid_absent)
    for condition in conditions:
        failure = classify_registered_failure(condition)
        if failure.result is not AuthEventResult.idp_account_not_eligible:
            raise GrantFailureError(f"{condition} audits as idp_account_not_eligible")
    return conditions


def device_grant_exhausted_conditions() -> tuple[RegClaimCondition, ...]:
    """`device_grant_exhausted` for an already-set registered-claimed device state on the iOS and
    Android device-checked kinds. The web kind has no such state, so it produces none of these."""
    # [impl->req~grants-reg-class-device-grant-exhausted~1]
    conditions = (RegClaimCondition.ios_registered_bit_set,
                  RegClaimCondition.android_registered_recall_set)
    if len(DEVICE_CHECKED_KINDS) != len(conditions):
        raise GrantFailureError("one already-set condition per device-checked kind")
    for condition in conditions:
        if classify_registered_failure(condition).client_class \
                is not ClientErrorClass.device_grant_exhausted:
            raise GrantFailureError(f"{condition} surfaces as device_grant_exhausted")
    if non_accusatory_copy() == "":
        raise GrantFailureError("the exhausted copy is non-accusatory, not empty")
    return conditions


def account_already_claimed_block(kind: GateConsumptionKind = REGISTERED_GRANT_GATE
                                 ) -> RegFailure:
    """`account_already_claimed` for `idp_account_already_claimed`: the resolved provider account's
    registered gate is already consumed. The block is final for that provider account across all
    Firebase users, external identities, internal users, reinstalls and devices — and it is the
    registered gate's alone: a web anonymous-grant conflict is a different kind and a different
    class."""
    # [impl->req~grants-reg-class-account-already-claimed~1]
    if kind is not REGISTERED_GRANT_GATE:
        raise GrantFailureError(f"{kind} is not the registered account grant gate")
    failure = classify_registered_failure(RegClaimCondition.registered_gate_consumed)
    if not remediation_for(failure.client_class).terminal:
        raise GrantFailureError("the duplicate block is final for that provider account")
    web = classify_anonymous_failure(AnonFailureCondition.web_gate_already_consumed)
    if web.client_class is failure.client_class:
        raise GrantFailureError("a web anonymous-gate conflict is not account_already_claimed")
    return failure


def verification_temporarily_unavailable_conditions() -> tuple[RegClaimCondition, ...]:
    """`verification_temporarily_unavailable` for a registered device-check vendor outage after the
    retry budget, and for `firebase_lookup_unavailable` when the mandatory `providerData`
    confirmation fails transiently after its budget. Firebase user-not-found at that read is
    non-retryable, audited as `firebase_user_unresolved`, and surfaces as `auth_required`."""
    # [impl->req~grants-reg-class-verification-temporarily-unavailable~1]
    # [impl->req~grants-reg-proof-vs-dependency-mapping~1]
    conditions = (RegClaimCondition.device_check_vendor_outage,
                  RegClaimCondition.firebase_provider_data_unavailable,
                  RegClaimCondition.turnstile_dependency_failed)
    for condition in conditions:
        failure = classify_registered_failure(condition)
        if not (failure.retryable and failure.after_retry_budget):
            raise GrantFailureError(f"{condition} fails closed only after the retry budget")
    not_found = classify_registered_failure(RegClaimCondition.firebase_user_not_found)
    if not_found.retryable or not_found.client_class is not ClientErrorClass.auth_required:
        raise GrantFailureError("Firebase user-not-found is non-retryable and is auth_required")
    return conditions


def proof_rejected_conditions() -> tuple[RegClaimCondition, ...]:
    """`proof_rejected` for a missing, malformed or partial platform proof set for the selected
    kind — omitted DeviceCheck query or update material on iOS, an omitted Play Integrity verdict
    on Android — so omitting native material never turns a native claim into an account-only
    claim. The zero-, multiple- or partial-evidence-set shape is the same class but a request-shape
    error, rejected before any eligibility check, vendor call or ledger write. Server-to-server and
    Turnstile dependency failures map to `verification_temporarily_unavailable` instead."""
    # [impl->req~grants-reg-class-proof-rejected~1]
    # [impl->req~grants-reg-proof-vs-dependency-mapping~1]
    conditions = (RegClaimCondition.incomplete_platform_proof_set,
                  RegClaimCondition.evidence_set_shape_invalid)
    for condition in conditions:
        failure = classify_registered_failure(condition)
        if failure.result is not AuthEventResult.proof_malformed:
            raise GrantFailureError(f"{condition} audits as proof_malformed")
    for dependency in (RegClaimCondition.device_check_vendor_outage,
                       RegClaimCondition.turnstile_dependency_failed):
        if classify_registered_failure(dependency).client_class \
                is ClientErrorClass.proof_rejected:
            raise GrantFailureError(f"{dependency} is a dependency failure, not proof_rejected")
    return conditions


# --- The destination rejection's disclosure ----------------------------------------------------------

# The one machine-readable field the destination rejection adds to the shared response shape, and
# the facts about the held grant it never discloses.
HELD_GRANT_FIELD: str = "held_grant_ends_at"
NEVER_DISCLOSED: frozenset[str] = frozenset({"source", "tier_id", "tier", "grant_id", "id",
                                             "subscription_id", "status"})


@dataclass(frozen=True, slots=True)
class RegisteredRejection:
    """One rejection, on both sides of the boundary: the shared response shape the client sees —
    with the destination rejection's one extra machine-readable field — and the specific internal
    result the audit row records."""
    status: int
    body: dict[str, Any]
    headers: dict[str, str]
    audit_result: AuthEventResult
    client_class: ClientErrorClass
    retry_after_held_grant_ends: bool = False
    contact_support: bool = False


def destination_incompatible_rejection(blocked: RegisteredDestinationBlocked
                                       ) -> RegisteredRejection:
    """`operation_not_allowed` for an active grant that blocks the destination. The rejection
    carries, in the shared response shape, the machine-readable field `held_grant_ends_at`: the
    held grant's `ends_at`, or `null` when the grant is open-ended and ends only on operator
    revocation. It discloses nothing else about the held grant. The client tells the user when the
    free grant becomes claimable and retries after that time rather than blind-retrying; where the
    value is `null` the user is directed to support instead of to a retry loop."""
    # [impl->req~grants-reg-class-operation-not-allowed~1]
    ends_at = blocked.held_grant_ends_at
    base = client_response(ClientErrorClass.operation_not_allowed.value, blocked_until=ends_at)
    body: dict[str, Any] = {"code": base.body["code"],
                            HELD_GRANT_FIELD: ends_at.isoformat() if ends_at is not None else None}
    disclosed = sorted(NEVER_DISCLOSED & set(body))
    if disclosed:
        raise GrantFailureError(f"the rejection discloses {disclosed} about the held grant")
    return RegisteredRejection(status=base.status, body=body, headers=base.headers,
                               audit_result=blocked.result,
                               client_class=ClientErrorClass.operation_not_allowed,
                               retry_after_held_grant_ends=ends_at is not None,
                               contact_support=ends_at is None)


def structural_block_rejection(result: AuthEventResult = AuthEventResult.policy_rejected
                               ) -> RegisteredRejection:
    """The other structural policy blocks take the same class through the one shared shape, with
    no held-grant field to report."""
    # [impl->req~grants-reg-class-operation-not-allowed~1]
    rejection = completion_rejection(result, operation=AuthOperation.claim_registered_grant,
                                     structural=True)
    return RegisteredRejection(status=rejection.status, body=dict(rejection.body),
                               headers=rejection.headers, audit_result=rejection.audit_result,
                               client_class=rejection.client_class)


# --- The in-request retry policy ---------------------------------------------------------------------

# One attempt plus at most two additional attempts of the same step, inside the same request.
# [impl->req~grants-reg-retry-three-attempts~1]
REG_RETRY_TOTAL_ATTEMPTS: int = COMPLETION_ATTEMPT_CAP
REG_RETRY_ADDITIONAL_ATTEMPTS: int = REG_RETRY_TOTAL_ATTEMPTS - 1


class RegRetryableStep(StrEnum):
    """The registered claim's steps a retryable dependency failure may be retried on."""
    devicecheck_read = "devicecheck_read"
    devicecheck_write = "devicecheck_write"
    device_recall_read = "device_recall_read"
    device_recall_write = "device_recall_write"
    firebase_provider_data = "firebase_provider_data"
    turnstile_validation = "turnstile_validation"


# The condition each step's exhausted budget produces.
# [impl->req~grants-reg-retry-budget-exhausted~1]
REG_STEP_EXHAUSTED: dict[RegRetryableStep, RegClaimCondition] = {
    RegRetryableStep.devicecheck_read: RegClaimCondition.device_check_vendor_outage,
    RegRetryableStep.devicecheck_write: RegClaimCondition.registered_bit_write_failed,
    RegRetryableStep.device_recall_read: RegClaimCondition.device_check_vendor_outage,
    RegRetryableStep.device_recall_write: RegClaimCondition.registered_bit_write_failed,
    RegRetryableStep.firebase_provider_data:
        RegClaimCondition.firebase_provider_data_unavailable,
    RegRetryableStep.turnstile_validation: RegClaimCondition.turnstile_dependency_failed,
}

# The rejections that are final for the claim: they reject immediately and spend no retry budget.
# [impl->req~grants-reg-non-retryable-immediate~1]
NON_RETRYABLE_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.idp_account_not_eligible,
    AuthEventResult.idp_account_already_claimed,
    AuthEventResult.registered_grant_destination_incompatible,
    AuthEventResult.policy_rejected,
})


class RegisteredStepFailed(RuntimeError):
    """One attempt at a registered-claim step failed. `retryable` says whether the cause is a
    retryable backend-to-provider dependency failure or a rejection final for the claim."""

    def __init__(self, step: RegRetryableStep, *, retryable: bool,
                 result: AuthEventResult | None = None, message: str = ""):
        self.step = step
        self.retryable = retryable
        self.result = result
        super().__init__(message or f"{step} failed")


@dataclass(frozen=True, slots=True)
class RegRetryOutcome:
    """What a retried step produced, how many attempts it spent, and what it wrote."""
    value: Any
    attempts: int


def retry_registered_step(step: RegRetryableStep,
                          run: Callable[[int], Any],
                          *,
                          attempts: int = REG_RETRY_TOTAL_ATTEMPTS,
                          grants_written: int = 0) -> RegRetryOutcome:
    """Run one retryable registered-claim step under its in-request retry budget: retried on the
    same step, inside the same request, up to two additional times — three attempts in all. A
    non-retryable rejection is raised on the spot and spends no budget."""
    # [impl->req~grants-reg-retry-three-attempts~1]
    # [impl->req~grants-reg-non-retryable-immediate~1]
    if step not in REG_STEP_EXHAUSTED:
        raise GrantFailureError(f"{step} carries no in-request retry budget")
    if attempts < 1 or attempts > REG_RETRY_TOTAL_ATTEMPTS:
        raise GrantFailureError(
            f"a registered-claim step is attempted at most {REG_RETRY_TOTAL_ATTEMPTS} times")
    spent = 0
    while True:
        spent += 1
        try:
            return RegRetryOutcome(value=run(spent), attempts=spent)
        except RegisteredStepFailed as failure:
            if not failure.retryable:
                assert_non_retryable_immediate(failure.result, attempts_spent=spent)
                raise
            if spent >= attempts:
                raise registered_retry_budget_exhausted(
                    step, grants_written=grants_written) from None


def registered_retry_budget_exhausted(step: RegRetryableStep,
                                      *, grants_written: int = 0) -> ClaimRejection:
    """After the retry budget is exhausted for a pre-activation registered-bit read or write,
    reject with `verification_temporarily_unavailable`, audit the specific dependency result, and
    create no grant."""
    # [impl->req~grants-reg-retry-budget-exhausted~1]
    if grants_written:
        raise GrantFailureError("a spent retry budget leaves no grant behind")
    failure = classify_registered_failure(REG_STEP_EXHAUSTED[step])
    if failure.client_class is not ClientErrorClass.verification_temporarily_unavailable:
        raise GrantFailureError(f"{step} exhaustion is verification_temporarily_unavailable")
    return ClaimRejection(failure.result,
                          f"{step} is unavailable after {REG_RETRY_TOTAL_ATTEMPTS} attempts")


def assert_non_retryable_immediate(result: AuthEventResult | None,
                                   *, attempts_spent: int = 1) -> None:
    """The non-retryable rejections reject immediately without consuming retry budget:
    `idp_account_not_eligible`, `idp_account_already_claimed`,
    `registered_grant_destination_incompatible` and `policy_rejected`. Each of the four is a
    durable rejection of the claim, so no step may be attempted a second time for one."""
    # [impl->req~grants-reg-non-retryable-immediate~1]
    if result is None:
        return
    if result in NON_RETRYABLE_RESULTS and attempts_spent != 1:
        raise GrantFailureError(f"{result} spends no retry budget: it rejects immediately")
    retryable = {failure.result for failure in REG_FAILURES.values() if failure.retryable}
    if result in NON_RETRYABLE_RESULTS & retryable:
        raise GrantFailureError(f"{result} is non-retryable and is never retried")


def assert_registered_retries_write_once(*,
                                         attempts: int,
                                         grants_inserted: int,
                                         anti_abuse_inserted: int,
                                         destination_mutations: int,
                                         elapsed_seconds: float = 0.0,
                                         expiry_extended: bool = False,
                                         expiry_evaluations: int = 1) -> None:
    """Retries must not insert duplicate grants or anti-abuse rows and must not invoke the
    destination mutation more than once per attempt. They never lengthen challenge expiry and are
    not bounded by it, because expiry was evaluated once when the challenge was claimed."""
    # [impl->req~grants-reg-retry-no-duplicate-rows~1]
    if grants_inserted > 1 or anti_abuse_inserted > 1:
        raise GrantFailureError("a retried claim inserts no duplicate grant or anti-abuse row")
    if destination_mutations > attempts:
        raise GrantFailureError("the destination mutation runs at most once per attempt")
    assert_retries_not_bounded_by_expiry(elapsed_seconds=elapsed_seconds, attempts=attempts,
                                        expiry_extended=expiry_extended,
                                        expiry_evaluations=expiry_evaluations)


# --- A registered-bit write failure is always pre-activation ------------------------------------------


def registered_write_failure(write: DeviceBitWrite | None,
                             *,
                             grants_written: int = 0,
                             reconciled_from_database: bool = False) -> AccessGrantSource:
    """A registered-bit write failure is always a pre-activation refusal: a failed, timed-out,
    cancelled, ambiguous or unattemptable write permits no grant row, and this raises rather than
    returning a remedy. A client retry is a whole new claim with fresh vendor material; the backend
    never reconciles vendor state against database grant state and never grants around a failed
    write. Where the write was confirmed but activation never happened, the same accepted
    burned-slot outcome and `manual`-source remediation described for the anonymous bit apply."""
    # [impl->req~grants-reg-write-failure-pre-activation~1]
    if grants_written:
        raise GrantFailureError("a failed registered-bit write leaves no grant behind")
    if reconciled_from_database or VENDOR_STATE_RECONCILERS:
        raise GrantFailureError("vendor state is never reconciled against database grant state")
    if write is not None and write.confirmed:
        # A confirmed write with no activation burns the slot; the remedy is a `manual` grant.
        assert_grant_row_permitted(write)
        return accepted_burned_slot(BurnedSlotCause.lost_or_ambiguous_write_acknowledgment,
                                    write_confirmed=True, grant_activated=False)
    # The failed write itself: no grant row may follow it, in this attempt or a later one.
    assert_grant_row_permitted(write)
    return stranded_slot_remediation()


def registered_retry_is_whole_new_claim(material: Any,
                                        *,
                                        previous_material: Any,
                                        challenge_id: Any,
                                        previous_challenge_id: Any,
                                        write: DeviceBitWrite | None) -> Any:
    """A client retry after a registered-bit write failure is a whole new claim: fresh vendor
    material and a fresh operation challenge, with the grant row hanging on that new attempt's own
    vendor-confirmed write. The backend never finishes the previous write later."""
    # [impl->req~grants-reg-write-failure-pre-activation~1]
    return whole_claim_retry(material, previous_material=previous_material,
                             challenge_id=challenge_id,
                             previous_challenge_id=previous_challenge_id, write=write)


# --- A durable registered rejection promises no alternate ----------------------------------------------

# The durable rejections after which no further free-credit path is specified.
DURABLE_REGISTERED_CLASSES: frozenset[ClientErrorClass] = frozenset({
    ClientErrorClass.verification_required,
    ClientErrorClass.account_already_claimed,
})
# What continued access requires once the free paths are closed.
PAID_CONTINUATIONS: tuple[str, ...] = ("active_subscription", "non_free_entitlement")


def registered_durable_rejection(client_class: ClientErrorClass) -> tuple[None, tuple[str, ...]]:
    """A durable `verification_required` or `account_already_claimed` rejection from
    `claim_registered_grant` does not promise an alternate free-credit path: continued access
    requires an active subscription or another non-free entitlement."""
    # [impl->req~grants-reg-durable-rejection-no-alternate~1]
    # [impl->req~grants-reg-durable-rejections-final~1]
    if client_class not in DURABLE_REGISTERED_CLASSES:
        raise GrantFailureError(f"{client_class} is no durable registered-claim rejection")
    result = (AuthEventResult.idp_account_not_eligible
              if client_class is ClientErrorClass.verification_required
              else AuthEventResult.idp_account_already_claimed)
    if further_free_credit_path(result) is not None:
        raise GrantFailureError(f"{result} leaves no further free-credit path")
    return None, PAID_CONTINUATIONS


# --- The registered account alternate path for anonymous grant closure ---------------------------------

# The specified product alternate free-credit path for `claim_anonymous_grant` closure, and the
# route the client takes to it. Both are read from the shared taxonomy's own remediation.
# [impl->req~grants-alternate-path-definition~1]
ALTERNATE_PATH_OPERATION: AuthOperation = AuthOperation.claim_registered_grant
ALTERNATE_PATH_ROUTE: str = "/auth/claim-registered-grant"


def alternate_path() -> tuple[AuthOperation, str]:
    """The alternate free-credit path this section defines, and the route that reaches it."""
    # [impl->req~grants-alternate-path-definition~1]
    remediation = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    if remediation.alternate_operation is not ALTERNATE_PATH_OPERATION:
        raise GrantFailureError("the alternate path is the registered account grant")
    if remediation.alternate_route != ALTERNATE_PATH_ROUTE:
        raise GrantFailureError(f"the alternate path is reached at {ALTERNATE_PATH_ROUTE}")
    return ALTERNATE_PATH_OPERATION, ALTERNATE_PATH_ROUTE


def device_state_set_closure(kind: ClaimBranch) -> tuple[AuthEventResult, ClientErrorClass]:
    """When `claim_anonymous_grant` is rejected because the per-device anonymous-claimed state is
    already set, the backend audits a specific already-claimed device-state result and surfaces
    `device_grant_exhausted`."""
    # [impl->req~grants-alt-cond-device-state-set~1]
    if kind not in DEVICE_CHECKED_KINDS:
        raise GrantFailureError(f"{kind} carries no per-device anonymous-claimed state")
    condition = (AnonFailureCondition.ios_anonymous_bit_set if kind is ClaimBranch.native_ios
                 else AnonFailureCondition.android_recall_anonymous_state_set)
    failure = classify_anonymous_failure(condition)
    if failure.result is not AuthEventResult.native_claim_already_claimed:
        raise GrantFailureError(f"{condition} audits the specific already-claimed device state")
    if failure.client_class is not ClientErrorClass.device_grant_exhausted:
        raise GrantFailureError(f"{condition} surfaces as device_grant_exhausted")
    return failure.result, failure.client_class


def web_stored_binding_closure(row: ExternalIdentityRow,
                               provider_data: Sequence[object] | None,
                               *,
                               lookup_failure: ProviderLookupFailedError | None = None
                               ) -> ClientErrorClass:
    """On web, the claimant's stored provider must be `google` or `apple` and the complete live
    `providerData` result must pass the closed classifier with the classified provider and sole
    entry's non-empty `uid` equal to the stored provider and stored `provider_uid`. An empty,
    invalid-shape or mismatching result follows the durable `verification_required` unsatisfied
    sign-in-gate path rather than the alternate path's duplicate branch.

    The rule itself belongs to the web anonymous-grant gate, so this runs that gate rather than
    re-deciding it from booleans — which is also what keeps a *lookup failure* on its own
    transient path instead of collapsing into the durable sign-in-gate class.
    """
    # [impl->req~grants-alt-cond-web-stored-binding~1]
    if row.provider not in REGISTERED_PROVIDERS or not row.provider_uid:
        return _unsatisfied_web_sign_in_gate()
    try:
        web_anonymous_grant_gate(row, provider_data, lookup_failure=lookup_failure)
    except GateDenied:
        return _unsatisfied_web_sign_in_gate()
    except ProviderLookupFailedError as failed:
        # An indeterminate or failed Admin lookup keeps its own class: it is not an empty,
        # invalid-shape or mismatching result and never reads as the durable sign-in-gate denial.
        if failed.client_class is ClientErrorClass.verification_required:
            raise GrantFailureError("a failed lookup is no unsatisfied sign-in gate") from None
        return ClientErrorClass(failed.client_class)
    return ClientErrorClass.device_grant_exhausted


def _unsatisfied_web_sign_in_gate() -> ClientErrorClass:
    """The one class an unsatisfied web sign-in gate takes, read from the anonymous condition
    table that owns it."""
    # [impl->req~grants-alt-cond-web-stored-binding~1]
    failure = classify_anonymous_failure(AnonFailureCondition.web_stored_binding_mismatch)
    if failure.client_class is not ClientErrorClass.verification_required:
        raise GrantFailureError("an unsatisfied web sign-in gate is verification_required")
    return failure.client_class


def web_gate_conflict_closure() -> tuple[AuthEventResult, ClientErrorClass]:
    """When `claim_anonymous_grant` on web is rejected because the web anonymous-grant
    `idp_account_hash` uniqueness rule conflicts, the backend audits the web gate as already
    consumed for that provider account and surfaces `device_grant_exhausted`."""
    # [impl->req~grants-alt-cond-web-gate-conflict~1]
    failure = classify_anonymous_failure(AnonFailureCondition.web_gate_already_consumed)
    if failure.result is not AuthEventResult.anti_abuse_already_claimed:
        raise GrantFailureError("the web gate conflict audits as anti_abuse_already_claimed")
    if failure.client_class is not ClientErrorClass.device_grant_exhausted:
        raise GrantFailureError("the web gate conflict surfaces as device_grant_exhausted")
    return failure.result, failure.client_class


def no_qualifying_native_evidence() -> tuple[ClientErrorClass, AuthOperation]:
    """When the client cannot present qualifying native evidence — including an Android device
    whose verified Play Integrity verdict lacks Device Recall, indistinguishable from withheld
    material and rejected as `proof_rejected` — the registered account grant path is the specified
    alternate."""
    # [impl->req~grants-alt-cond-no-qualifying-native-evidence~1]
    failure = classify_anonymous_failure(AnonFailureCondition.client_proof_missing_or_malformed)
    if failure.client_class is not ClientErrorClass.proof_rejected:
        raise GrantFailureError("absent qualifying native evidence is proof_rejected")
    operation, _route = alternate_path()
    return failure.client_class, operation


def other_durable_closure(condition: AnonFailureCondition) -> tuple[ClientErrorClass, bool]:
    """Other durable `claim_anonymous_grant` rejections surface according to the taxonomy and carry
    no guarantee that the registered account grant will succeed."""
    # [impl->req~grants-alt-cond-other-durable-rejections~1]
    failure = classify_anonymous_failure(condition)
    if failure.after_retry_budget:
        raise GrantFailureError(f"{condition} is a transient dependency failure, not a closure")
    return failure.client_class, False


@dataclass(frozen=True, slots=True)
class AlternateRemediation:
    """The client remediation for `device_grant_exhausted` or a platform with no anonymous path."""
    obtain_identity_by: tuple[str, ...]
    upgrade_route: str
    upgrade_in_place: bool
    create_user_route: str
    claim_route: str
    retry_anonymous_claim: bool
    guaranteed: bool


# The four ways to obtain the Google or Apple identity, and the routes that produce one.
IDENTITY_ACTIONS: tuple[str, ...] = ("sign_in", "create", "upgrade", "link")
UPGRADE_ROUTE: str = "/auth/upgrade-anonymous"
CREATE_USER_ROUTE: str = "/auth/create-user"


def exhausted_or_no_anonymous_path_remediation() -> AlternateRemediation:
    """Client remediation for `device_grant_exhausted` or a platform with no anonymous path: obtain
    a Google or Apple linked identity, then call the registered claim. The anonymous claim is not
    retried under the same already-claimed or unsupported condition, and the registered path is not
    guaranteed to succeed."""
    # [impl->req~grants-remediation-exhausted-or-no-anonymous-path~1]
    # [impl->req~grants-alt-remediation-obtain-linked-identity~1]
    # [impl->req~grants-alt-remediation-upgrade-in-place~1]
    # [impl->req~grants-alt-remediation-create-user~1]
    # [impl->req~grants-alt-remediation-call-registered-grant~1]
    # [impl->req~grants-alt-remediation-no-retry~1]
    shared = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    if shared.obtain_identity_by != IDENTITY_ACTIONS:
        raise GrantFailureError("the client obtains the identity by signing in, creating, "
                                "upgrading or linking")
    if not UPGRADE_IS_IN_PLACE:
        raise GrantFailureError("upgrade-anonymous is an in-place provider flip")
    if shared.retry_same_endpoint:
        raise GrantFailureError(
            "the client must not retry claim-anonymous-grant under the same condition")
    operation, route = alternate_path()
    if operation is not ALTERNATE_PATH_OPERATION:
        raise GrantFailureError("the remediation ends at the registered claim")
    return AlternateRemediation(obtain_identity_by=IDENTITY_ACTIONS,
                               upgrade_route=UPGRADE_ROUTE,
                               upgrade_in_place=UPGRADE_IS_IN_PLACE,
                               create_user_route=CREATE_USER_ROUTE,
                               claim_route=route,
                               retry_anonymous_claim=False,
                               guaranteed=False)


def registered_path_gates() -> tuple[str, ...]:
    """`claim_registered_grant` is not guaranteed to succeed after `device_grant_exhausted` or a
    platform fallback: it has its own gates — a current stored Google or Apple identity, a stored
    `provider_uid` confirmed by the mandatory fail-closed `providerData` read, no consumed
    registered gate for the provider account, the account's own grant history under the
    one-free-grant-per-account rule, an active linked user, and no incompatible active grant."""
    # [impl->req~grants-alt-guarantee-registered-gates~1]
    if exhausted_or_no_anonymous_path_remediation().guaranteed:
        raise GrantFailureError("the registered path is a path, not a guarantee")
    if "mandatory_turnstile_pass" not in ACCOUNT_LAYER_BINDINGS:
        raise GrantFailureError("the web kind's Turnstile pass is one of the account bindings")
    return ("stored_google_or_apple_identity",
            "stored_provider_uid_confirmed_by_provider_data",
            "registered_gate_unconsumed_for_provider_account",
            "account_own_grant_history",
            "active_linked_user",
            "no_incompatible_active_grant")


def assert_no_transient_as_exhausted(condition: AnonFailureCondition,
                                     *,
                                     durable_state_observed: bool = False) -> ClientErrorClass:
    """The backend must not surface a transient device-check, Cloudflare or Firebase Admin
    `providerData` lookup failure as `device_grant_exhausted` unless it has independently observed
    durable already-claimed state or a web provider-account uniqueness conflict."""
    # [impl->req~grants-alt-guarantee-no-transient-as-exhausted~1]
    return transient_failure_class(condition, durable_state_observed=durable_state_observed)


def registered_failure_rejection(condition: RegClaimCondition,
                                 *,
                                 held_grant_ends_at: datetime | None = None
                                 ) -> RegisteredRejection:
    """The client-visible rejection one condition produces, through the one shared response
    shape."""
    # [impl->req~grants-reg-failure-classes~1]
    failure = classify_registered_failure(condition)
    if condition is RegClaimCondition.destination_incompatible_active_grant:
        return destination_incompatible_rejection(
            RegisteredDestinationBlocked(held_grant_ends_at))
    if condition is RegClaimCondition.structural_policy_block:
        return structural_block_rejection()
    rejection = completion_rejection(failure.result,
                                     operation=AuthOperation.claim_registered_grant)
    return RegisteredRejection(status=rejection.status, body=dict(rejection.body),
                               headers=rejection.headers, audit_result=rejection.audit_result,
                               client_class=rejection.client_class)


def registered_condition_rejected(condition: RegClaimCondition,
                                  message: str = "") -> FreeGrantRejected:
    """The exception one registered-claim condition raises, carrying the audited internal result
    and the class the condition table pairs with it — so the class the client sees and the class
    anything re-deriving it from the audited result computes are the same one."""
    # [impl->req~grants-reg-failure-classes~1]
    failure = classify_registered_failure(condition)
    return FreeGrantRejected(failure.result, failure.client_class.value,
                             message or str(condition),
                             status_code=remediation_for(failure.client_class).http_status)


def registered_claim_rejected(result: AuthEventResult, message: str = "") -> FreeGrantRejected:
    """The exception one registered-claim rejection raises, carrying the audited internal result
    and the class it surfaces as."""
    # [impl->req~grants-reg-failure-classes~1]
    structural = result in {AuthEventResult.registered_grant_destination_incompatible,
                            AuthEventResult.policy_rejected}
    client_class = grants_client_class(result, operation=AuthOperation.claim_registered_grant,
                                       structural=structural)
    if client_class not in REG_CLIENT_CLASSES:
        raise FreeGrantError(f"{client_class} is outside the registered claim's classes")
    return FreeGrantRejected(result, client_class.value, message or str(result),
                             status_code=remediation_for(client_class).http_status)
