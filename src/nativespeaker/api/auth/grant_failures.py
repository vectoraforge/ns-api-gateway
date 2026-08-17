"""Failure handling for `claim_anonymous_grant`, and the grants half of the client error taxonomy.

Three questions live here. Which client-visible class a claim that cannot complete surfaces, and
from which condition. What the client must then do — the normative remediation, per class. And
which internal `core.auth_event_result` the audit row records while that class goes out, for all
four auth completion endpoints.

Everything this module decides is a mapping, and every mapping is one-way: a condition names its
class, a class names its remediation, and the internal result stays behind. The registry itself is
`taxonomy.py`'s and the shared catalog classes are `00-overview-and-shared-contracts.md`'s; this
module adds only the grants domain's own post-barrier cases through the taxonomy's declared
extension point, so there is never a second result-to-class registry to disagree with the first.

The mechanics it composes belong to their owners: the vendor read-write-activate sequence and its
whole-claim retry rule are `proof_adapters`', the platform gates and the two ledgers are
`free_grants`', the device-bit budgets are `ratelimit/`'s, and the shared response shape is
`taxonomy`'s.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
)
from nativespeaker.api.auth.free_grants import (
    MAX_ACTIVE_GRANTS_PER_USER,
    MAX_WEB_GATES_PER_PROVIDER_ACCOUNT,
    assert_database_bounds,
    assert_device_check_is_anti_abuse_only,
    assert_no_enrolled_key,
    assert_no_raw_vendor_material_stored,
    non_accusatory_copy,
    registered_backstop,
)
from nativespeaker.api.auth.invariants import GateConsumptionKind, ProofUse
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_adapters import (
    COMPLETION_ATTEMPT_CAP,
    ClaimRejection,
    assert_completion_unbounded_by_clock,
    assert_fail_closed_scope,
    retry_after_failed_claim,
    stranded_slot_remediation,
)
from nativespeaker.api.auth.proof_endpoints import ClaimBranch
from nativespeaker.api.auth.proof_material import assert_anti_abuse_row_prohibitions
from nativespeaker.api.auth.taxonomy import (
    REMEDIATIONS,
    RESULT_TO_CLASS,
    ClientErrorClass,
    ProviderDataReadPoint,
    Remediation,
    client_response,
    device_grant_exhausted_next_path,
    register_client_class,
    remediation_for,
    surface,
)
from nativespeaker.api.ratelimit.ordering import (
    DEVICE_BIT_BUDGET,
    DeviceBitCall,
    DeviceBitWrite,
    assert_grant_row_permitted,
)


class GrantFailureError(RuntimeError):
    """A free-grant failure was about to be classified, audited or remediated wrongly."""


# The grants domain's own additions to the one shared internal-result-to-class mapping, made
# through the taxonomy's declared extension point. Everything else this module needs is already
# registered by `invariants` and `proof_adapters`, and nothing here re-registers it: there is one
# registry, and `taxonomy.surface` is how every class is read back out of it.
_GRANT_TAXONOMY_CLASSES: dict[AuthEventResult, ClientErrorClass] = {
    # The registered claim's stored binding is not `google`/`apple`, or carries no
    # `provider_uid`: a durable block on the free-credit path for this user state.
    # [impl->req~grants-class-verification-required~1]
    AuthEventResult.idp_account_not_eligible: ClientErrorClass.verification_required,
    # An active grant blocks the registered destination: structural, and a wait rather than a
    # permanent block.
    # [impl->req~grants-class-operation-not-allowed~1]
    AuthEventResult.registered_grant_destination_incompatible:
        ClientErrorClass.operation_not_allowed,
}

for _result, _class in _GRANT_TAXONOMY_CLASSES.items():
    if _result not in RESULT_TO_CLASS:
        register_client_class(_result, _class.value, REMEDIATIONS[_class].http_status)


# --- The classes `claim_anonymous_grant` may surface ----------------------------------------------

# The three classes the grants domain owns for a claimant who cannot complete the grant.
# [impl->req~grants-anon-failure-classes~1]
ANON_GRANT_CLASSES: tuple[ClientErrorClass, ...] = (
    ClientErrorClass.device_grant_exhausted,
    ClientErrorClass.verification_required,
    ClientErrorClass.verification_temporarily_unavailable,
)

# The shared token-acceptance, identity, account, challenge, proof and structural cases the
# taxonomy defines, which this endpoint uses exactly as defined there.
# [impl->req~grants-anon-failure-classes~1]
ANON_SHARED_CLASSES: tuple[ClientErrorClass, ...] = (
    ClientErrorClass.auth_required,
    ClientErrorClass.preauth_identity_not_allowed,
    ClientErrorClass.account_unavailable,
    ClientErrorClass.challenge_required,
    ClientErrorClass.proof_rejected,
    ClientErrorClass.operation_not_allowed,
)

ANON_CLIENT_CLASSES: frozenset[ClientErrorClass] = frozenset(ANON_GRANT_CLASSES
                                                             + ANON_SHARED_CLASSES)


# --- The conditions, and the class each maps to ---------------------------------------------------


class AnonFailureCondition(StrEnum):
    """Every condition that stops a `claim_anonymous_grant` from completing."""
    client_proof_missing_or_malformed = "client_proof_missing_or_malformed"
    ios_anonymous_bit_set = "ios_anonymous_bit_set"
    android_recall_anonymous_state_set = "android_recall_anonymous_state_set"
    web_gate_already_consumed = "web_gate_already_consumed"
    device_check_read_denied = "device_check_read_denied"
    anonymous_grant_policy_rejected = "anonymous_grant_policy_rejected"
    web_stored_binding_mismatch = "web_stored_binding_mismatch"
    cloudflare_bot_check_denied = "cloudflare_bot_check_denied"
    devicecheck_read_unavailable = "devicecheck_read_unavailable"
    play_integrity_recall_read_unavailable = "play_integrity_recall_read_unavailable"
    device_state_write_failed = "device_state_write_failed"
    firebase_provider_data_unavailable = "firebase_provider_data_unavailable"
    cloudflare_dependency_failed = "cloudflare_dependency_failed"
    devicecheck_read_budget_exhausted = "devicecheck_read_budget_exhausted"
    devicecheck_write_budget_exhausted = "devicecheck_write_budget_exhausted"
    device_recall_read_budget_exhausted = "device_recall_read_budget_exhausted"
    device_recall_write_budget_exhausted = "device_recall_write_budget_exhausted"


@dataclass(frozen=True, slots=True)
class AnonFailure:
    """One condition, the internal result its audit row records, and the class it surfaces as."""
    condition: AnonFailureCondition
    result: AuthEventResult
    client_class: ClientErrorClass
    # Whether the condition is only reached once the in-request retry budget is spent.
    after_retry_budget: bool = False
    # The device-bit provider budget whose exhaustion produced it, where that is the cause.
    budget_entry: str | None = None


# Every condition's audited internal result and client-visible class, in one table. The class is
# the whole of what the client sees; the result is the whole of what the audit row records.
ANON_FAILURES: dict[AnonFailureCondition, AnonFailure] = {
    # Malformed or missing client-supplied vendor material, and the ambiguous or partial
    # evidence-set shape with it: the proof half of the split.
    # [impl->req~grants-anon-proof-state-dependency-split~1]
    AnonFailureCondition.client_proof_missing_or_malformed: AnonFailure(
        AnonFailureCondition.client_proof_missing_or_malformed,
        AuthEventResult.proof_malformed, ClientErrorClass.proof_rejected),
    # `device_grant_exhausted`: the durable already-claimed outcomes.
    # [impl->req~grants-exhausted-cond-ios-bit-set~1]
    AnonFailureCondition.ios_anonymous_bit_set: AnonFailure(
        AnonFailureCondition.ios_anonymous_bit_set,
        AuthEventResult.native_claim_already_claimed, ClientErrorClass.device_grant_exhausted),
    # [impl->req~grants-exhausted-cond-android-recall-set~1]
    AnonFailureCondition.android_recall_anonymous_state_set: AnonFailure(
        AnonFailureCondition.android_recall_anonymous_state_set,
        AuthEventResult.native_claim_already_claimed, ClientErrorClass.device_grant_exhausted),
    # The web gate-consumption conflict: a different mechanism, its own internal result, and the
    # same client-visible class.
    # [impl->req~grants-exhausted-cond-web-gate-consumed~1]
    AnonFailureCondition.web_gate_already_consumed: AnonFailure(
        AnonFailureCondition.web_gate_already_consumed,
        AuthEventResult.anti_abuse_already_claimed, ClientErrorClass.device_grant_exhausted),
    # `verification_required`: the durable blocks with no more specific class.
    # [impl->req~grants-vr-cond-device-check-denied~1]
    AnonFailureCondition.device_check_read_denied: AnonFailure(
        AnonFailureCondition.device_check_read_denied,
        AuthEventResult.policy_rejected, ClientErrorClass.verification_required),
    # [impl->req~grants-vr-cond-policy-rejected~1]
    AnonFailureCondition.anonymous_grant_policy_rejected: AnonFailure(
        AnonFailureCondition.anonymous_grant_policy_rejected,
        AuthEventResult.policy_rejected, ClientErrorClass.verification_required),
    # [impl->req~grants-vr-cond-web-binding-mismatch~1]
    AnonFailureCondition.web_stored_binding_mismatch: AnonFailure(
        AnonFailureCondition.web_stored_binding_mismatch,
        AuthEventResult.policy_rejected, ClientErrorClass.verification_required),
    # [impl->req~grants-vr-cond-cloudflare-denial~1]
    AnonFailureCondition.cloudflare_bot_check_denied: AnonFailure(
        AnonFailureCondition.cloudflare_bot_check_denied,
        AuthEventResult.policy_rejected, ClientErrorClass.verification_required),
    # `verification_temporarily_unavailable`: the transient dependency failures, each of them
    # reached only once the in-request retry budget is spent.
    # [impl->req~grants-vtu-cond-devicecheck-read~1]
    AnonFailureCondition.devicecheck_read_unavailable: AnonFailure(
        AnonFailureCondition.devicecheck_read_unavailable,
        AuthEventResult.native_claim_unavailable,
        ClientErrorClass.verification_temporarily_unavailable, after_retry_budget=True),
    # [impl->req~grants-vtu-cond-play-integrity-read~1]
    AnonFailureCondition.play_integrity_recall_read_unavailable: AnonFailure(
        AnonFailureCondition.play_integrity_recall_read_unavailable,
        AuthEventResult.native_claim_unavailable,
        ClientErrorClass.verification_temporarily_unavailable, after_retry_budget=True),
    # A write that failed, timed out, was cancelled, was ambiguous, or could not be attempted.
    # [impl->req~grants-vtu-cond-write-failure~1]
    AnonFailureCondition.device_state_write_failed: AnonFailure(
        AnonFailureCondition.device_state_write_failed,
        AuthEventResult.native_claim_write_failed,
        ClientErrorClass.verification_temporarily_unavailable, after_retry_budget=True),
    # [impl->req~grants-vtu-cond-firebase-lookup~1]
    AnonFailureCondition.firebase_provider_data_unavailable: AnonFailure(
        AnonFailureCondition.firebase_provider_data_unavailable,
        AuthEventResult.firebase_lookup_unavailable,
        ClientErrorClass.verification_temporarily_unavailable, after_retry_budget=True),
    # A Cloudflare Turnstile dependency failure records the class value itself as the audit
    # row's result: no `cloudflare_lookup_unavailable` result exists.
    # [impl->req~grants-vtu-cond-cloudflare-dependency~1]
    AnonFailureCondition.cloudflare_dependency_failed: AnonFailure(
        AnonFailureCondition.cloudflare_dependency_failed,
        AuthEventResult.verification_temporarily_unavailable,
        ClientErrorClass.verification_temporarily_unavailable, after_retry_budget=True),
    # A device-bit provider budget exhausted at the point its vendor read or write would be
    # issued: audited as the matching budget-exhausted result, never as an admission `429`.
    # [impl->req~grants-vtu-cond-device-bit-budget~1]
    AnonFailureCondition.devicecheck_read_budget_exhausted: AnonFailure(
        AnonFailureCondition.devicecheck_read_budget_exhausted,
        AuthEventResult.devicecheck_read_budget_exhausted,
        ClientErrorClass.verification_temporarily_unavailable,
        budget_entry=DEVICE_BIT_BUDGET[DeviceBitCall.devicecheck_read]),
    # [impl->req~grants-vtu-cond-device-bit-budget~1]
    AnonFailureCondition.devicecheck_write_budget_exhausted: AnonFailure(
        AnonFailureCondition.devicecheck_write_budget_exhausted,
        AuthEventResult.devicecheck_write_budget_exhausted,
        ClientErrorClass.verification_temporarily_unavailable,
        budget_entry=DEVICE_BIT_BUDGET[DeviceBitCall.devicecheck_write]),
    # [impl->req~grants-vtu-cond-device-bit-budget~1]
    AnonFailureCondition.device_recall_read_budget_exhausted: AnonFailure(
        AnonFailureCondition.device_recall_read_budget_exhausted,
        AuthEventResult.device_recall_read_budget_exhausted,
        ClientErrorClass.verification_temporarily_unavailable,
        budget_entry=DEVICE_BIT_BUDGET[DeviceBitCall.device_recall_read]),
    # [impl->req~grants-vtu-cond-device-bit-budget~1]
    AnonFailureCondition.device_recall_write_budget_exhausted: AnonFailure(
        AnonFailureCondition.device_recall_write_budget_exhausted,
        AuthEventResult.device_recall_write_budget_exhausted,
        ClientErrorClass.verification_temporarily_unavailable,
        budget_entry=DEVICE_BIT_BUDGET[DeviceBitCall.device_recall_write]),
}

# The three condition sets, as the spec enumerates them. Each is closed: `_conditions_for` reads
# the table above back and refuses if the two ever disagree, so a new condition cannot be added
# to the table without being placed in its set.
# [impl->req~grants-exhausted-condition-set~1]
EXHAUSTED_CONDITIONS: tuple[AnonFailureCondition, ...] = (
    AnonFailureCondition.ios_anonymous_bit_set,
    AnonFailureCondition.android_recall_anonymous_state_set,
    AnonFailureCondition.web_gate_already_consumed,
)
# [impl->req~grants-verification-required-condition-set~1]
VERIFICATION_REQUIRED_CONDITIONS: tuple[AnonFailureCondition, ...] = (
    AnonFailureCondition.device_check_read_denied,
    AnonFailureCondition.anonymous_grant_policy_rejected,
    AnonFailureCondition.web_stored_binding_mismatch,
    AnonFailureCondition.cloudflare_bot_check_denied,
)
# [impl->req~grants-vtu-condition-set~1]
VTU_CONDITIONS: tuple[AnonFailureCondition, ...] = (
    AnonFailureCondition.devicecheck_read_unavailable,
    AnonFailureCondition.play_integrity_recall_read_unavailable,
    AnonFailureCondition.device_state_write_failed,
    AnonFailureCondition.firebase_provider_data_unavailable,
    AnonFailureCondition.cloudflare_dependency_failed,
    AnonFailureCondition.devicecheck_read_budget_exhausted,
    AnonFailureCondition.devicecheck_write_budget_exhausted,
    AnonFailureCondition.device_recall_read_budget_exhausted,
    AnonFailureCondition.device_recall_write_budget_exhausted,
)

_DECLARED_CONDITION_SETS: dict[ClientErrorClass, tuple[AnonFailureCondition, ...]] = {
    ClientErrorClass.device_grant_exhausted: EXHAUSTED_CONDITIONS,
    ClientErrorClass.verification_required: VERIFICATION_REQUIRED_CONDITIONS,
    ClientErrorClass.verification_temporarily_unavailable: VTU_CONDITIONS,
}


def _conditions_for(client_class: ClientErrorClass) -> tuple[AnonFailureCondition, ...]:
    """The declared condition set for one class, checked against the failure table."""
    declared = _DECLARED_CONDITION_SETS.get(client_class)
    if declared is None:
        raise GrantFailureError(f"{client_class} has no declared condition set")
    mapped = {failure.condition for failure in ANON_FAILURES.values()
              if failure.client_class is client_class}
    if mapped != set(declared):
        raise GrantFailureError(
            f"{client_class} maps {sorted(str(name) for name in mapped)}, "
            f"not {sorted(str(name) for name in declared)}")
    return declared


def exhausted_conditions() -> tuple[AnonFailureCondition, ...]:
    """The conditions that map to `device_grant_exhausted`, and the whole of them."""
    # [impl->req~grants-exhausted-condition-set~1]
    return _conditions_for(ClientErrorClass.device_grant_exhausted)


def verification_required_conditions() -> tuple[AnonFailureCondition, ...]:
    """The conditions that map to `verification_required`, and the whole of them."""
    # [impl->req~grants-verification-required-condition-set~1]
    return _conditions_for(ClientErrorClass.verification_required)


def vtu_conditions() -> tuple[AnonFailureCondition, ...]:
    """The conditions that map to `verification_temporarily_unavailable`, and the whole of
    them — the five dependency failures and the four device-bit budget exhaustions."""
    # [impl->req~grants-vtu-condition-set~1]
    return _conditions_for(ClientErrorClass.verification_temporarily_unavailable)


def classify_anonymous_failure(condition: AnonFailureCondition) -> AnonFailure:
    """The proof-versus-state-versus-dependency split, normatively: malformed or missing client
    proof returns `proof_rejected`; per-device already-claimed state and a web anonymous-grant
    gate conflict map to `device_grant_exhausted`; a durable device-check denial, a
    server-validated bot-check denial and a completed web `providerData` lookup that fails the
    closed-classifier-and-stored-binding check map to `verification_required`; a device-check,
    Cloudflare, Firebase Admin `providerData` or pre-activation device-state write outage after
    the retry budget maps to `verification_temporarily_unavailable`. There is no enrolled-key
    conflict branch."""
    # [impl->req~grants-anon-proof-state-dependency-split~1]
    # [impl->req~grants-anon-failure-classes~1]
    # [impl->req~grants-anon-failure-rejection-conditions~1]
    # [impl->req~grants-anon-failure-class-mapping~1]
    # [impl->req~grants-invariant-05~1]
    assert_no_enrolled_key()
    failure = ANON_FAILURES.get(condition)
    if failure is None:
        raise GrantFailureError(f"{condition} classifies no claim_anonymous_grant failure")
    if failure.client_class not in ANON_CLIENT_CLASSES:
        raise GrantFailureError(f"{failure.client_class} is no claim_anonymous_grant class")
    if failure.client_class in _DECLARED_CONDITION_SETS:
        _conditions_for(failure.client_class)
    return failure


# The internal results a `claim_anonymous_grant` attempt can also audit, beyond this file's own
# failure conditions: the shared token-acceptance, identity, account and challenge cases, whose
# classes the canonical catalog defines.
ANON_SHARED_RESULTS: tuple[AuthEventResult, ...] = (
    AuthEventResult.invalid_external_jwt,
    AuthEventResult.firebase_user_unresolved,
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.blocked_user,
    AuthEventResult.historical_identity,
    AuthEventResult.challenge_not_found,
    AuthEventResult.challenge_expired,
    AuthEventResult.challenge_consumed,
    AuthEventResult.challenge_identity_mismatch,
    AuthEventResult.challenge_operation_mismatch,
)


def anonymous_failure_class(condition: AnonFailureCondition) -> ClientErrorClass:
    """The one class this condition surfaces as, cross-checked against the one shared registry:
    the condition table and `taxonomy.surface` must agree, or the classification refuses."""
    # [impl->req~grants-anon-failure-classes~1]
    failure = classify_anonymous_failure(condition)
    client_class = grants_client_class(failure.result,
                                       operation=AuthOperation.claim_anonymous_grant)
    if client_class is not failure.client_class:
        raise GrantFailureError(
            f"{condition} maps to {failure.client_class}, but {failure.result} surfaces as "
            f"{client_class}")
    if client_class not in ANON_CLIENT_CLASSES:
        raise GrantFailureError(f"{client_class} is no claim_anonymous_grant class")
    return client_class


def anonymous_emitted_classes() -> frozenset[ClientErrorClass]:
    """Every class `claim_anonymous_grant` can emit, derived from the results it can audit — the
    three the grants domain owns plus the six shared cases, and nothing else. A claimant who
    cannot complete the grant always receives one of them."""
    # [impl->req~grants-anon-failure-classes~1]
    emitted = {anonymous_failure_class(condition) for condition in ANON_FAILURES}
    emitted |= {grants_client_class(result, operation=AuthOperation.claim_anonymous_grant)
                for result in ANON_SHARED_RESULTS}
    # The structural completion-time invariant violation, whose class is decided by the cause
    # rather than by the internal result alone.
    emitted.add(grants_client_class(AuthEventResult.policy_rejected,
                                    operation=AuthOperation.claim_anonymous_grant,
                                    structural=True))
    if emitted != ANON_CLIENT_CLASSES:
        raise GrantFailureError(
            f"claim_anonymous_grant emits {sorted(str(name) for name in emitted)}")
    return frozenset(emitted)


# --- The three grants-owned classes, as `claim_anonymous_grant` defines them ---------------------


@dataclass(frozen=True, slots=True)
class AnonOutcome:
    """What one rejected claim produces: the audited internal result, the client-visible class,
    the copy where the class carries any, and whether a free-credit alternate remains."""
    condition: AnonFailureCondition
    result: AuthEventResult
    client_class: ClientErrorClass
    durable: bool
    copy: str | None = None
    next_route: str | None = None
    guaranteed_alternate: bool = False


# The operations fail-closed free-grant handling must never block. A dependency failure denies
# the free grant and nothing else.
PROTECTED_OPERATIONS: frozenset[AuthOperation] = frozenset({
    AuthOperation.create_user,
    AuthOperation.upgrade_anonymous_to_registered,
    AuthOperation.sync,
    AuthOperation.restore_subscription,
})


def device_grant_exhausted_outcome(condition: AnonFailureCondition) -> AnonOutcome:
    """`device_grant_exhausted` is the durable already-claimed outcome: the per-device
    anonymous-claimed state is already set on a platform that has such state, or the web
    uniqueness rule shows the provider account already consumed the web anonymous gate. The
    client copy is non-accusatory and directs the user to the registered account grant path."""
    # [impl->req~grants-anon-class-device-grant-exhausted~1]
    failure = classify_anonymous_failure(condition)
    if failure.client_class is not ClientErrorClass.device_grant_exhausted:
        raise GrantFailureError(f"{condition} is no already-claimed outcome")
    next_route = device_grant_exhausted_next_path(AuthOperation.claim_anonymous_grant)
    if next_route is None:
        raise GrantFailureError("the exhausted anonymous claim names the registered grant path")
    return AnonOutcome(condition=condition, result=failure.result,
                       client_class=failure.client_class, durable=True,
                       copy=non_accusatory_copy(), next_route=next_route)


def verification_required_outcome(condition: AnonFailureCondition) -> AnonOutcome:
    """`verification_required` is a durable block under anonymous-grant policy, or a
    non-retryable platform-gate denial that has no more specific class: a completed web
    `providerData` lookup whose complete result has an invalid closed-classifier shape, whose
    resulting provider is not the stored provider, or whose sole entry's non-empty `uid` is not
    the stored `provider_uid` is an unsatisfied sign-in gate and maps here. The anonymous device
    grant path is closed for this user state with no guarantee that another free-credit path
    succeeds."""
    # [impl->req~grants-anon-class-verification-required~1]
    # [impl->req~grants-anon-alt-verification-required-no-alternate~1]
    # [impl->req~grants-anon-step-03-gate-state-and-dependencies~1]
    failure = classify_anonymous_failure(condition)
    if failure.client_class is not ClientErrorClass.verification_required:
        raise GrantFailureError(f"{condition} is no durable anonymous-grant block")
    if failure.after_retry_budget:
        raise GrantFailureError(f"{condition} is a retryable dependency failure, not a denial")
    if condition in EXHAUSTED_CONDITIONS:
        raise GrantFailureError(f"{condition} has the more specific device_grant_exhausted class")
    return AnonOutcome(condition=condition, result=failure.result,
                       client_class=failure.client_class, durable=True,
                       guaranteed_alternate=False)


def verification_temporarily_unavailable_outcome(condition: AnonFailureCondition,
                                                 *,
                                                 retry_budget_exhausted: bool = True,
                                                 blocks: Sequence[AuthOperation] = (),
                                                 http_status: int | None = None) -> AnonOutcome:
    """`verification_temporarily_unavailable` is a transient backend-to-provider dependency
    failure. A device-check vendor outage, a Cloudflare validation dependency failure and a web
    Firebase Admin `providerData` lookup failure each fail the grant closed only after the retry
    budget, and only the free grant: never login, account creation, upgrade, sync, subscription
    restore, or any paid entitlement path. A device-bit budget exhausted at the point its vendor
    call would be issued takes the matching budget-exhausted result and is never an admission
    `429`."""
    # [impl->req~grants-anon-class-verification-temporarily-unavailable~1]
    # [impl->req~grants-vtu-cond-device-bit-budget~1]
    # [impl->req~grants-anon-taxonomy-shared-never-blocks-paid~1]
    failure = classify_anonymous_failure(condition)
    if failure.client_class is not ClientErrorClass.verification_temporarily_unavailable:
        raise GrantFailureError(f"{condition} is no transient dependency failure")
    if failure.after_retry_budget and not retry_budget_exhausted:
        raise GrantFailureError(f"{condition} fails the grant closed only after the retry budget")
    # The fail-closed behaviour gates the free grant and nothing else.
    assert_fail_closed_scope(AuthOperation.claim_anonymous_grant)
    blocked = sorted(str(operation) for operation in blocks if operation in PROTECTED_OPERATIONS)
    if blocked:
        raise GrantFailureError(f"a free-grant dependency failure never blocks {blocked}")
    if failure.budget_entry is not None and http_status == 429:
        raise GrantFailureError(
            f"{failure.budget_entry} exhaustion is audited as {failure.result}, not an admission "
            "429")
    return AnonOutcome(condition=condition, result=failure.result,
                       client_class=failure.client_class, durable=False,
                       guaranteed_alternate=False)


def firebase_provider_data_read_points() -> tuple[ProviderDataReadPoint, ...]:
    """The complete closed set of Firebase Admin `providerData` reads the grants file names: the
    web anonymous-grant gate, anonymous and registered `create-user` completion,
    `upgrade-anonymous` completion, and the `claim_registered_grant` confirmation. A lookup
    dependency failure at any of them fails that operation retryably, and the web gate's failure
    fails only the free grant."""
    # [impl->req~grants-anon-class-verification-temporarily-unavailable~1]
    points = tuple(ProviderDataReadPoint)
    if len(points) != 5:
        raise GrantFailureError("the providerData read points are a closed set of five")
    return points


# --- The in-request retry policy ------------------------------------------------------------------

# One attempt plus at most two additional attempts of the same step, inside the same request. The
# three-attempt cap is the completion's, shared with the rest of the post-claim sequence.
# [impl->req~grants-anon-retry-three-attempts~1]
ANON_RETRY_TOTAL_ATTEMPTS: int = COMPLETION_ATTEMPT_CAP
ANON_RETRY_ADDITIONAL_ATTEMPTS: int = ANON_RETRY_TOTAL_ATTEMPTS - 1


class RetryableStep(StrEnum):
    """The steps of a claim that a retryable dependency failure may be retried on."""
    devicecheck_read = "devicecheck_read"
    devicecheck_write = "devicecheck_write"
    device_recall_read = "device_recall_read"
    device_recall_write = "device_recall_write"
    cloudflare_validation = "cloudflare_validation"
    web_firebase_provider_data = "web_firebase_provider_data"


# The condition each step's exhausted retry budget produces.
# [impl->req~grants-anon-retry-budget-exhausted~1]
STEP_EXHAUSTED_CONDITION: dict[RetryableStep, AnonFailureCondition] = {
    RetryableStep.devicecheck_read: AnonFailureCondition.devicecheck_read_unavailable,
    RetryableStep.devicecheck_write: AnonFailureCondition.device_state_write_failed,
    RetryableStep.device_recall_read:
        AnonFailureCondition.play_integrity_recall_read_unavailable,
    RetryableStep.device_recall_write: AnonFailureCondition.device_state_write_failed,
    RetryableStep.cloudflare_validation: AnonFailureCondition.cloudflare_dependency_failed,
    RetryableStep.web_firebase_provider_data:
        AnonFailureCondition.firebase_provider_data_unavailable,
}


class ClaimStepFailed(RuntimeError):
    """One attempt at a claim step failed. `retryable` says whether the cause is a retryable
    backend-to-provider dependency failure or a rejection that is final for the claim."""

    def __init__(self, step: RetryableStep, *, retryable: bool, message: str = ""):
        self.step = step
        self.retryable = retryable
        super().__init__(message or f"{step} failed")


@dataclass(frozen=True, slots=True)
class RetryOutcome:
    """What a retried step produced, and how many attempts it spent."""
    value: Any
    attempts: int


def retry_claim_step(step: RetryableStep,
                     run: Callable[[int], Any],
                     *,
                     attempts: int = ANON_RETRY_TOTAL_ATTEMPTS,
                     grants_written: int = 0) -> RetryOutcome:
    """Run one retryable claim step under its in-request retry budget.

    A retryable pre-grant device-check read or write, a retryable Cloudflare validation
    dependency failure and a retryable web Firebase Admin `providerData` lookup failure are each
    retried on the same step, inside the same request, up to two additional times — three
    attempts in all. A non-retryable rejection is raised on the spot and spends no retry budget.
    Once the budget is spent the claim rejects with `verification_temporarily_unavailable` and no
    grant.
    """
    # [impl->req~grants-anon-retry-three-attempts~1]
    # [impl->req~grants-anon-non-retryable-immediate~1]
    # [impl->req~grants-anon-retry-budget-exhausted~1]
    # [impl->req~grants-anon-step-03-gate-state-and-dependencies~1]
    if step not in STEP_EXHAUSTED_CONDITION:
        raise GrantFailureError(f"{step} carries no in-request retry budget")
    if attempts < 1 or attempts > ANON_RETRY_TOTAL_ATTEMPTS:
        raise GrantFailureError(
            f"a claim step is attempted at most {ANON_RETRY_TOTAL_ATTEMPTS} times per request")
    spent = 0
    while True:
        spent += 1
        try:
            return RetryOutcome(value=run(spent), attempts=spent)
        except ClaimStepFailed as failure:
            if not failure.retryable:
                # A non-retryable rejection is immediate: no further attempt is made, so the
                # retry budget is untouched.
                raise
            if spent >= attempts:
                raise retry_budget_exhausted(step, grants_written=grants_written) from None


def retry_budget_exhausted(step: RetryableStep, *, grants_written: int = 0) -> ClaimRejection:
    """The rejection a spent retry budget produces: `verification_temporarily_unavailable`, the
    step's own internal result on the audit row, and no grant."""
    # [impl->req~grants-anon-retry-budget-exhausted~1]
    # [impl->req~grants-anon-step-03-gate-state-and-dependencies~1]
    if grants_written:
        raise GrantFailureError("a spent retry budget leaves no grant behind")
    outcome = verification_temporarily_unavailable_outcome(STEP_EXHAUSTED_CONDITION[step],
                                                          retry_budget_exhausted=True)
    return ClaimRejection(outcome.result, f"{step} is unavailable after "
                                          f"{ANON_RETRY_TOTAL_ATTEMPTS} attempts")


# The branches that carry a per-device bit, and so a write the vendor must confirm before a grant
# row exists. The web branch has no such bit: its gate is the stored-binding match plus the bot
# check, so a web retry has no write to confirm.
DEVICE_BIT_BRANCHES: frozenset[ClaimBranch] = frozenset({ClaimBranch.native_ios,
                                                         ClaimBranch.native_android})


def whole_claim_retry(material: Any,
                      *,
                      branch: ClaimBranch = ClaimBranch.native_ios,
                      previous_material: Any = None,
                      challenge_id: Any,
                      previous_challenge_id: Any = None,
                      write: DeviceBitWrite | None = None) -> Any:
    """A client retries a failed claim only as a whole new claim, with a fresh operation
    challenge and fresh platform proof material. The server never activates around a failed or
    ambiguous write: on a branch that carries a per-device bit, only this attempt's own
    vendor-confirmed write permits a grant row. The web branch carries no such bit — its retry
    brings fresh Turnstile and `providerData` material and no write to confirm."""
    # [impl->req~grants-anon-retry-whole-claim~1]
    if branch not in set(ClaimBranch):
        raise GrantFailureError(f"{branch} is no claim branch")
    if previous_challenge_id is not None and challenge_id == previous_challenge_id:
        raise GrantFailureError("a retry is a whole new claim with a fresh operation challenge")
    fresh = retry_after_failed_claim(material, previous_material=previous_material)
    if branch in DEVICE_BIT_BRANCHES:
        # Never around the failed write: the grant row hangs on a confirmed write of this attempt.
        assert_grant_row_permitted(write)
    elif write is not None:
        raise GrantFailureError(f"{branch} carries no per-device bit write")
    return fresh


def assert_retries_not_bounded_by_expiry(*,
                                         elapsed_seconds: float,
                                         attempts: int,
                                         expiry_extended: bool = False,
                                         expiry_evaluations: int = 1) -> None:
    """Retries neither lengthen the challenge's expiry nor are bounded by it. Expiry was
    evaluated once, when the challenge was claimed, so the retry budgets and the fixed per-call
    provider timeouts are the only bound on the post-claim steps."""
    # [impl->req~grants-anon-retry-not-bounded-by-expiry~1]
    if expiry_extended:
        raise GrantFailureError("a retry never lengthens the challenge's expiry")
    if expiry_evaluations != 1:
        raise GrantFailureError("expiry is evaluated once, when the challenge is claimed")
    assert_completion_unbounded_by_clock(elapsed_seconds, attempts=attempts)


# --- The burned device slot, as an accepted outcome ------------------------------------------------


class BurnedSlotCause(StrEnum):
    """The only causes that can burn a physical device's slot without issuing a grant."""
    crash_after_confirmed_write = "crash_after_confirmed_write"
    lost_or_ambiguous_write_acknowledgment = "lost_or_ambiguous_write_acknowledgment"
    comparable_operational_failure = "comparable_operational_failure"


BURNED_SLOT_CAUSES: frozenset[BurnedSlotCause] = frozenset(BurnedSlotCause)

# Nothing routine burns a slot, and nothing repairs one either: vendor bits are never
# auto-cleared, no pending-state machine exists, and the backend never reconciles or repairs
# vendor state from database grant state.
# [impl->req~grants-burned-slot-accepted-outcome~1]
PENDING_STATE_MACHINES: frozenset[str] = frozenset()
VENDOR_STATE_RECONCILERS: frozenset[str] = frozenset()


def accepted_burned_slot(cause: BurnedSlotCause,
                         *,
                         write_confirmed: bool,
                         grant_activated: bool) -> AccessGrantSource:
    """A crash after a confirmed vendor write but before activation burns that device's slot with
    no grant, and so can a lost write acknowledgment. Both are accepted over-enforcement
    outcomes, and only these operational failures produce them. The remediation is the existing
    `manual` grant source: bits are never auto-cleared and nothing reconciles them."""
    # [impl->req~grants-burned-slot-accepted-outcome~1]
    # [impl->req~grants-anon-step-08-crash-outcomes~1]
    if cause not in BURNED_SLOT_CAUSES:
        raise GrantFailureError(f"{cause} does not burn a device slot")
    if not write_confirmed:
        raise GrantFailureError("an unconfirmed write burns nothing: no bit was set")
    if grant_activated:
        raise GrantFailureError("a burned slot is a confirmed write with no grant")
    if PENDING_STATE_MACHINES or VENDOR_STATE_RECONCILERS:
        raise GrantFailureError("no pending-state machine and no vendor-state reconciler exists")
    # Fail-closed over-enforcement gates the free grant alone.
    assert_fail_closed_scope(AuthOperation.claim_anonymous_grant)
    return stranded_slot_remediation()


def burned_slot_retry_outcome(branch: ClaimBranch) -> AnonOutcome:
    """The whole-claim retry after a lost write acknowledgment reads the now-set bit and returns
    `device_grant_exhausted`, even though that user received nothing."""
    # [impl->req~grants-burned-slot-accepted-outcome~1]
    # [impl->req~grants-anon-step-08-crash-outcomes~1]
    condition = (AnonFailureCondition.ios_anonymous_bit_set
                 if branch is ClaimBranch.native_ios
                 else AnonFailureCondition.android_recall_anonymous_state_set)
    if branch is ClaimBranch.web:
        raise GrantFailureError("web has no per-device bit to burn")
    return device_grant_exhausted_outcome(condition)


def assert_activation_never_rejects_on_expiry(*,
                                              write_confirmed: bool,
                                              vendor_latency_seconds: float,
                                              expiry_evaluations: int = 1) -> None:
    """Ordinary vendor latency after a confirmed write causes no time-based rejection: expiry was
    evaluated once, at the claim, and the activation transaction never rejects on expiry
    grounds."""
    # [impl->req~grants-burned-slot-accepted-outcome~1]
    if not write_confirmed:
        return
    assert_retries_not_bounded_by_expiry(elapsed_seconds=vendor_latency_seconds,
                                        attempts=1,
                                        expiry_evaluations=expiry_evaluations)


# --- The normative client remediation, per class ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnonRemediation:
    """What the client must do on receiving one of the three grants-owned classes. It is part of
    the client contract, not a hint inferred from the class name."""
    client_class: ClientErrorClass
    durably_closed: bool
    transient: bool
    retry_same_endpoint: bool
    fresh_challenge: bool = False
    fresh_proof: bool = False
    backoff: bool = False
    alternate_operation: AuthOperation | None = None
    alternate_route: str | None = None
    obtain_identity_by: tuple[str, ...] = ()
    guaranteed_alternate: bool = False
    registered_backstop: bool = False


# The four ways a client may obtain the Google or Apple identity the registered path needs.
IDENTITY_ACTIONS: tuple[str, ...] = ("sign_in", "create", "upgrade", "link")

ANON_REMEDIATION: dict[ClientErrorClass, AnonRemediation] = {
    # Client remediation when `device_grant_exhausted` is returned.
    # [impl->req~grants-remediation-device-grant-exhausted~1]
    ClientErrorClass.device_grant_exhausted: AnonRemediation(
        client_class=ClientErrorClass.device_grant_exhausted,
        # The anonymous path is durably closed for the device state or web provider-account gate
        # the backend observed, and the specified alternate free-credit path is the registered
        # claim, itself subject to the registered-grant gates.
        # [impl->req~grants-remediation-exhausted-alternate-path~1]
        durably_closed=True,
        transient=False,
        # The client must not retry the anonymous claim under the same already-claimed condition.
        # [impl->req~grants-remediation-exhausted-no-retry~1]
        retry_same_endpoint=False,
        alternate_operation=AuthOperation.claim_registered_grant,
        # Sign in with, create, upgrade to, or link a Google or Apple identity, then call
        # `POST /auth/claim-registered-grant`.
        # [impl->req~grants-remediation-exhausted-direct-to-registered~1]
        alternate_route=device_grant_exhausted_next_path(AuthOperation.claim_anonymous_grant),
        obtain_identity_by=IDENTITY_ACTIONS,
        registered_backstop=True),
    # Client remediation when `verification_required` is returned.
    # [impl->req~grants-remediation-verification-required~1]
    ClientErrorClass.verification_required: AnonRemediation(
        client_class=ClientErrorClass.verification_required,
        # The anonymous device grant path is durably closed for this user state, with no
        # guaranteed free-credit alternate: continued access then needs a subscription or another
        # non-free entitlement.
        # [impl->req~grants-remediation-vr-durably-closed~1]
        # [impl->req~grants-invariant-11~1]
        durably_closed=True,
        guaranteed_alternate=False,
        transient=False,
        # No blind retry from the same device or web provider-account state under the same
        # identity state.
        # [impl->req~grants-remediation-vr-no-blind-retry~1]
        retry_same_endpoint=False,
        obtain_identity_by=IDENTITY_ACTIONS),
    # Client remediation when `verification_temporarily_unavailable` is returned.
    # [impl->req~grants-remediation-verification-temporarily-unavailable~1]
    ClientErrorClass.verification_temporarily_unavailable: AnonRemediation(
        client_class=ClientErrorClass.verification_temporarily_unavailable,
        # A transient backend-to-provider dependency, not durable anti-abuse state.
        # [impl->req~grants-remediation-vtu-transient~1]
        durably_closed=False,
        transient=True,
        # The client may retry the same endpoint with a fresh operation challenge and fresh
        # platform proof material, with backoff between attempts.
        # [impl->req~grants-remediation-vtu-retry-fresh-material~1]
        retry_same_endpoint=True,
        fresh_challenge=True,
        fresh_proof=True,
        backoff=True,
        # The registered account grant remains the platform-independent backstop.
        # [impl->req~grants-remediation-vtu-registered-backstop~1]
        registered_backstop=True),
}


def anonymous_remediation(client_class: ClientErrorClass) -> AnonRemediation:
    """The normative remediation for one of the three grants-owned classes, checked against the
    shared registry: a durable block is never retried on a timer, a transient failure always is,
    and the two are never collapsed into one handler."""
    # [impl->req~grants-remediation-device-grant-exhausted~1]
    # [impl->req~grants-remediation-verification-required~1]
    # [impl->req~grants-remediation-verification-temporarily-unavailable~1]
    remediation = ANON_REMEDIATION.get(client_class)
    if remediation is None:
        raise GrantFailureError(f"{client_class} carries no anonymous-claim remediation")
    shared = remediation_for(client_class)
    if shared.transient is not remediation.transient:
        raise GrantFailureError(f"{client_class} disagrees with the shared registry on transience")
    if remediation.durably_closed and remediation.retry_same_endpoint:
        raise GrantFailureError(f"{client_class} is durable: the same request is never retried")
    if remediation.transient and not (remediation.fresh_challenge and remediation.fresh_proof):
        raise GrantFailureError(f"{client_class} retries with fresh challenge and proof material")
    return remediation


def exhausted_alternate_path(row: ExternalIdentityRow,
                             *,
                             active_grant_source: AccessGrantSource | None) -> AuthOperation:
    """The specified alternate free-credit path after `device_grant_exhausted`: the registered
    account grant, which requires the current user to be linked to a Google or Apple identity and
    to satisfy the registered-grant gate rules. It is a path, not a guarantee."""
    # A `device_grant_exhausted` rejection directs the client to complete registration or sign in
    # with a Google or Apple account and then call `claim_registered_grant`.
    # [impl->req~grants-remediation-exhausted-alternate-path~1]
    # [impl->req~grants-anon-alt-exhausted-to-registered~1]
    # [impl->req~grants-anon-alt-not-guaranteed~1]
    # [impl->req~grants-invariant-05~1]
    # [impl->req~grants-invariant-11~1]
    remediation = anonymous_remediation(ClientErrorClass.device_grant_exhausted)
    if remediation.alternate_operation is None:
        raise GrantFailureError("device_grant_exhausted names an alternate free-credit path")
    return registered_backstop(row, active_grant_source=active_grant_source,
                              anonymous_gate_exhausted=True)


def vtu_registered_backstop(row: ExternalIdentityRow,
                            *,
                            active_grant_source: AccessGrantSource | None,
                            anonymous_gate_exhausted: bool = True,
                            held_grant_ends_at: datetime | None = None
                            ) -> tuple[AuthOperation | None, datetime | None]:
    """The registered account grant remains available as the platform-independent backstop
    whenever the anonymous device state or the web provider-account gate is exhausted, or the
    platform has no anonymous path — provided the user holds no active grant other than a
    convertible anonymous device grant. While such a grant is held the registered claim is
    refused until it ends, and the free grant is not forfeited by the wait."""
    # [impl->req~grants-remediation-vtu-registered-backstop~1]
    if not anonymous_remediation(
            ClientErrorClass.verification_temporarily_unavailable).registered_backstop:
        raise GrantFailureError("the registered backstop survives a transient dependency failure")
    if (active_grant_source is not None
            and active_grant_source is not AccessGrantSource.anonymous_device_grant):
        # Refused until the held grant ends, and the claim is reachable again afterwards: waiting
        # forfeits nothing.
        return None, held_grant_ends_at
    return registered_backstop(row, active_grant_source=active_grant_source,
                               anonymous_gate_exhausted=anonymous_gate_exhausted), None


# --- The client error taxonomy for the auth completion endpoints -----------------------------------

# The four endpoints this taxonomy governs. It is one shared taxonomy across all of them, not a
# per-endpoint error contract.
# [impl->req~grants-taxonomy-opaque-classes~1]
# [impl->req~grants-anon-taxonomy-shared-never-blocks-paid~1]
COMPLETION_ENDPOINTS: dict[AuthOperation, str] = {
    AuthOperation.create_user: "/auth/create-user",
    AuthOperation.upgrade_anonymous_to_registered: "/auth/upgrade-anonymous",
    AuthOperation.claim_anonymous_grant: "/auth/claim-anonymous-grant",
    AuthOperation.claim_registered_grant: "/auth/claim-registered-grant",
}

# The classes this file owns the grant-specific internal-result mapping and remediation detail
# for, under the canonical catalog's delegation.
# [impl->req~grants-taxonomy-owned-classes~1]
GRANTS_OWNED_CLASSES: frozenset[ClientErrorClass] = frozenset({
    ClientErrorClass.proof_rejected,
    ClientErrorClass.operation_not_allowed,
    ClientErrorClass.verification_required,
    ClientErrorClass.device_grant_exhausted,
    ClientErrorClass.account_already_claimed,
    ClientErrorClass.verification_temporarily_unavailable,
})

# The classes defined once, with their code, status, retry meaning and remediation, in the
# canonical error catalog in `00-overview-and-shared-contracts.md`. This module keeps no copy of
# them: it holds no remediation of its own for any of them.
# [impl->req~grants-taxonomy-shared-catalog-classes~1]
SHARED_CATALOG_CLASSES: frozenset[ClientErrorClass] = frozenset({
    ClientErrorClass.auth_required,
    ClientErrorClass.preauth_identity_not_allowed,
    ClientErrorClass.account_unavailable,
    ClientErrorClass.identity_already_linked,
    ClientErrorClass.challenge_required,
})

# `policy_rejected` is the one internal result whose class is not a function of the result alone.
# On the two free-credit claims a structural completion-time invariant violation is
# `operation_not_allowed` and everything else the result covers is that claim's own durable
# free-credit block: the anonymous claim's unsatisfied web sign-in gate and Cloudflare denial, and
# the registered claim's web-kind Turnstile denial, which `03` maps to `verification_required`.
# `create-user` and `upgrade-anonymous` are not free-credit paths, so their policy rejection is
# structural either way.
_POLICY_REJECTED_CLASS: dict[AuthOperation, ClientErrorClass] = {
    # [impl->req~grants-class-verification-required~1]
    # [impl->req~grants-vr-cond-policy-rejected~1]
    AuthOperation.claim_anonymous_grant: ClientErrorClass.verification_required,
    # [impl->req~grants-class-operation-not-allowed~1]
    AuthOperation.create_user: ClientErrorClass.operation_not_allowed,
    # [impl->req~grants-class-operation-not-allowed~1]
    AuthOperation.upgrade_anonymous_to_registered: ClientErrorClass.operation_not_allowed,
    # [impl->req~grants-reg-gate-resolve-claim-kind~1]
    AuthOperation.claim_registered_grant: ClientErrorClass.verification_required,
}


def grants_client_class(result: AuthEventResult,
                        *,
                        operation: AuthOperation,
                        structural: bool = False) -> ClientErrorClass:
    """The opaque client-visible class one internal result surfaces as on an auth completion
    endpoint. The classes group internal results by remediation, so the client can route between
    re-auth, re-challenge, retry, the switch to the registered-account path, stopping on the same
    account, and waiting on a transient dependency — without any internal state leaking."""
    # [impl->req~grants-taxonomy-opaque-classes~1]
    # [impl->req~grants-anon-failure-class-mapping~1]
    if operation not in COMPLETION_ENDPOINTS:
        raise GrantFailureError(f"{operation} is no auth completion endpoint")
    if result is AuthEventResult.succeeded:
        raise GrantFailureError("succeeded is no rejection")
    if structural and result in NOT_STRUCTURAL_RESULTS:
        # [impl->req~grants-class-operation-not-allowed~1]
        raise GrantFailureError(f"{result} is not a structural completion-time violation")
    if result is AuthEventResult.policy_rejected:
        # [impl->req~grants-class-operation-not-allowed~1]
        client_class = (ClientErrorClass.operation_not_allowed if structural
                        else _POLICY_REJECTED_CLASS[operation])
    else:
        client_class = ClientErrorClass(surface(result)[0])
    if client_class not in GRANTS_OWNED_CLASSES | SHARED_CATALOG_CLASSES:
        raise GrantFailureError(f"{client_class} is outside this taxonomy's classes")
    return client_class


# The results this specification names identically on both sides. Everywhere else the audited
# internal value is strictly more specific than the class.
_NAMED_IDENTICALLY: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.identity_already_linked,
    AuthEventResult.verification_temporarily_unavailable,
})


@dataclass(frozen=True, slots=True)
class CompletionRejection:
    """One rejection, on both sides of the boundary: the shared response shape the client sees,
    and the specific internal result the audit row records."""
    status: int
    body: dict[str, str]
    headers: dict[str, str]
    audit_result: AuthEventResult
    client_class: ClientErrorClass


def completion_rejection(result: AuthEventResult,
                         *,
                         operation: AuthOperation,
                         structural: bool = False,
                         blocked_until: datetime | None = None) -> CompletionRejection:
    """Build a completion endpoint's rejection. One response shape is shared by all four
    endpoints, and the endpoint-specific classes are part of it rather than a second error
    contract. The audit row records the specific internal result — never a generic placeholder —
    and that audited value is never less specific than the class returned."""
    # [impl->req~grants-taxonomy-shared-response-shape~1]
    # [impl->req~grants-anon-audit-specific-internal-result~1]
    client_class = grants_client_class(result, operation=operation, structural=structural)
    response = client_response(client_class, blocked_until=blocked_until)
    # The body names the class and nothing else: no internal result reaches the client.
    if str(result) in set(response.body.values()) and result not in _NAMED_IDENTICALLY:
        raise GrantFailureError(f"{result} must not be surfaced to the client")
    if set(response.body) - {"code", "blocked_until"}:
        raise GrantFailureError("every completion endpoint uses the one shared response shape")
    return CompletionRejection(status=response.status, body=response.body,
                               headers=response.headers, audit_result=result,
                               client_class=client_class)


def assert_remediations_distinct(*classes: ClientErrorClass) -> None:
    """Each class carries its own normative remediation, and clients must not collapse classes
    with different remediations into one handler: durable blocks, cause-specific durable blocks
    with a specified alternate path, and structural blocks each direct the client to stop
    retrying the current path and take their own action."""
    # [impl->req~grants-taxonomy-normative-remediation~1]
    actions = [remediation_for(client_class).action for client_class in classes]
    if len(set(actions)) != len(actions):
        raise GrantFailureError(f"{sorted(str(name) for name in classes)} share one remediation")


def transient_failure_class(condition: AnonFailureCondition,
                            *,
                            durable_state_observed: bool = False) -> ClientErrorClass:
    """A transient backend-to-provider failure surfaces as
    `verification_temporarily_unavailable`, whose remediation is to retry the same operation with
    a fresh challenge and fresh proof material, with backoff. It is never surfaced as
    `device_grant_exhausted`, `verification_required` or `account_already_claimed` unless the
    backend has independently observed durable state that denies the grant."""
    # [impl->req~grants-taxonomy-normative-remediation~1]
    # [impl->req~grants-class-verification-temporarily-unavailable~1]
    # [impl->req~grants-invariant-05~1]
    failure = classify_anonymous_failure(condition)
    if failure.client_class is not ClientErrorClass.verification_temporarily_unavailable:
        raise GrantFailureError(f"{condition} is no transient dependency failure")
    if durable_state_observed:
        # The durable observation is a separate, independently established fact; it — not the
        # dependency failure — is what denies the grant.
        return ClientErrorClass.device_grant_exhausted
    remediation = anonymous_remediation(failure.client_class)
    if not (remediation.retry_same_endpoint and remediation.backoff):
        raise GrantFailureError("a transient failure is retried later, with backoff")
    return failure.client_class


def shared_catalog_remediation(client_class: ClientErrorClass) -> Remediation:
    """The five shared catalog classes are defined once in the canonical error catalog and this
    file keeps no copy: their remediation is read straight out of the shared registry, and on any
    of them the client stops the completion flow and follows that shared remediation."""
    # [impl->req~grants-taxonomy-shared-catalog-classes~1]
    if client_class not in SHARED_CATALOG_CLASSES:
        raise GrantFailureError(f"{client_class} is no shared catalog class")
    if client_class in ANON_REMEDIATION or client_class in GRANTS_OWNED_CLASSES:
        raise GrantFailureError(f"{client_class} keeps no grants-domain copy of its remediation")
    return remediation_for(client_class)


# --- `proof_rejected`: the single class for every vendor-material failure --------------------------


class VendorMaterialCause(StrEnum):
    """Every client-supplied-proof failure on `claim_anonymous_grant`."""
    invalid_devicecheck_query_token = "invalid_devicecheck_query_token"
    invalid_devicecheck_update_token = "invalid_devicecheck_update_token"
    invalid_play_integrity_token = "invalid_play_integrity_token"
    verdict_lacks_device_recall = "verdict_lacks_device_recall"
    insufficient_recall_verdict = "insufficient_recall_verdict"
    invalid_cloudflare_evidence = "invalid_cloudflare_evidence"
    inconsistent_app_identity = "inconsistent_app_identity"
    malformed_proof = "malformed_proof"
    ambiguous_or_partial_evidence_set = "ambiguous_or_partial_evidence_set"


# No per-cause attestation code exists, none enters the shared error registry, and the endpoint
# never emits an attestation-family error: the cause lives only in the audit row.
# [impl->req~grants-class-proof-rejected~1]
PER_CAUSE_PROOF_CLASSES: frozenset[str] = frozenset()
ATTESTATION_FAMILY_CLASSES: frozenset[str] = frozenset()


class ProviderTransaction(StrEnum):
    """The backend-to-provider interactions a claim makes. They are not client-supplied proof."""
    devicecheck_read = "devicecheck_read"
    devicecheck_write = "devicecheck_write"
    device_recall_read = "device_recall_read"
    device_recall_write = "device_recall_write"
    cloudflare_siteverify = "cloudflare_siteverify"
    firebase_provider_data = "firebase_provider_data"


# Each transaction's own dependency-class condition. A device-check server-to-server transaction,
# a Cloudflare validation transaction and a Firebase lookup transaction map to dependency classes
# rather than to `proof_rejected`.
# [impl->req~grants-class-proof-rejected~1]
TRANSACTION_CONDITION: dict[ProviderTransaction, AnonFailureCondition] = {
    ProviderTransaction.devicecheck_read: AnonFailureCondition.devicecheck_read_unavailable,
    ProviderTransaction.devicecheck_write: AnonFailureCondition.device_state_write_failed,
    ProviderTransaction.device_recall_read:
        AnonFailureCondition.play_integrity_recall_read_unavailable,
    ProviderTransaction.device_recall_write: AnonFailureCondition.device_state_write_failed,
    ProviderTransaction.cloudflare_siteverify: AnonFailureCondition.cloudflare_dependency_failed,
    ProviderTransaction.firebase_provider_data:
        AnonFailureCondition.firebase_provider_data_unavailable,
}


def vendor_material_rejection(cause: VendorMaterialCause,
                              *,
                              parseable: bool = False,
                              transaction: ProviderTransaction | None = None
                              ) -> tuple[AuthEventResult, ClientErrorClass]:
    """Classify a proof failure on `claim_anonymous_grant`.

    Every vendor-material failure returns the single class `proof_rejected`; the specific cause —
    an insufficient recall verdict as against the Device Recall structure being absent entirely —
    lives only in the audit row's internal result, and unparseable material is audited as the
    unified `proof_malformed` value. `proof_malformed` covers local decoding or structural
    validation failure only, so a structurally valid proof that fails verification takes the
    operation's existing verification-failure result instead: the failing backend-to-provider
    transaction's own dependency result.
    """
    # [impl->req~grants-class-proof-rejected~1]
    if PER_CAUSE_PROOF_CLASSES or ATTESTATION_FAMILY_CLASSES:
        raise GrantFailureError("no per-cause attestation code enters the shared registry")
    if cause not in set(VendorMaterialCause):
        raise GrantFailureError(f"{cause} is no vendor-material failure")
    if transaction is not None:
        # A provider transaction is a backend-to-provider interaction: a dependency class.
        failure = classify_anonymous_failure(TRANSACTION_CONDITION[transaction])
        return failure.result, failure.client_class
    if parseable:
        raise GrantFailureError(
            f"{cause} is structurally valid: its verification failure takes the operation's own "
            "verification-failure result, never proof_malformed")
    failure = classify_anonymous_failure(AnonFailureCondition.client_proof_missing_or_malformed)
    return failure.result, failure.client_class


# --- `operation_not_allowed`: structural completion-time invariants --------------------------------


class StructuralBlock(StrEnum):
    """The completion-time invariant violations that structurally prevent an operation."""
    anon_completion_invariant = "anon_completion_invariant"
    registered_grant_destination_incompatible = "registered_grant_destination_incompatible"
    registered_grant_policy_block = "registered_grant_policy_block"
    upgrade_provider_transition_conflict = "upgrade_provider_transition_conflict"
    upgrade_active_anonymous_invariant = "upgrade_active_anonymous_invariant"
    registered_create_user_provider_account_linked = \
        "registered_create_user_provider_account_linked"
    upgrade_provider_account_linked = "upgrade_provider_account_linked"
    create_user_policy_rejected = "create_user_policy_rejected"
    upgrade_policy_rejected = "upgrade_policy_rejected"


# Each structural block's operation and audited internal result.
# [impl->req~grants-class-operation-not-allowed~1]
OPERATION_NOT_ALLOWED_BLOCKS: dict[StructuralBlock,
                                   tuple[AuthOperation, AuthEventResult]] = {
    StructuralBlock.anon_completion_invariant: (AuthOperation.claim_anonymous_grant,
                                                AuthEventResult.policy_rejected),
    StructuralBlock.registered_grant_destination_incompatible: (
        AuthOperation.claim_registered_grant,
        AuthEventResult.registered_grant_destination_incompatible),
    StructuralBlock.registered_grant_policy_block: (AuthOperation.claim_registered_grant,
                                                    AuthEventResult.policy_rejected),
    StructuralBlock.upgrade_provider_transition_conflict: (
        AuthOperation.upgrade_anonymous_to_registered,
        AuthEventResult.provider_transition_not_allowed),
    StructuralBlock.upgrade_active_anonymous_invariant: (
        AuthOperation.upgrade_anonymous_to_registered, AuthEventResult.policy_rejected),
    StructuralBlock.registered_create_user_provider_account_linked: (
        AuthOperation.create_user, AuthEventResult.provider_account_already_linked),
    StructuralBlock.upgrade_provider_account_linked: (
        AuthOperation.upgrade_anonymous_to_registered,
        AuthEventResult.provider_account_already_linked),
    StructuralBlock.create_user_policy_rejected: (AuthOperation.create_user,
                                                  AuthEventResult.policy_rejected),
    StructuralBlock.upgrade_policy_rejected: (AuthOperation.upgrade_anonymous_to_registered,
                                              AuthEventResult.policy_rejected),
}

# What the class does not cover: create-user's already-linked-subject case, pre-auth or otherwise
# unlinked callers, and inactive, blocked or historical accounts.
# [impl->req~grants-class-operation-not-allowed~1]
NOT_STRUCTURAL_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.identity_already_linked,
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.blocked_user,
    AuthEventResult.historical_identity,
})


def operation_not_allowed_block(block: StructuralBlock,
                                *,
                                blocked_until: datetime | None = None) -> CompletionRejection:
    """A structural completion-time invariant violation, as `operation_not_allowed`. The
    destination case is a wait rather than a permanent block: the response reports when the held
    grant ends and the client retries after that point. The required client action is to remedy
    the underlying structural state and never to blind-retry from the same state."""
    # [impl->req~grants-class-operation-not-allowed~1]
    entry = OPERATION_NOT_ALLOWED_BLOCKS.get(block)
    if entry is None:
        raise GrantFailureError(f"{block} is no structural completion-time block")
    operation, result = entry
    rejection = completion_rejection(result, operation=operation, structural=True,
                                     blocked_until=blocked_until)
    if rejection.client_class is not ClientErrorClass.operation_not_allowed:
        raise GrantFailureError(f"{block} surfaces as {rejection.client_class}")
    if (block is StructuralBlock.registered_grant_destination_incompatible
            and blocked_until is None):
        raise GrantFailureError("the destination block is a wait and reports when it ends")
    return rejection


def anonymous_structural_scope(branch: ClaimBranch,
                               *,
                               registered_claimant: bool = False,
                               native_gate_missing: bool = False,
                               web_binding_unsatisfied: bool = False) -> ClientErrorClass | None:
    """For `claim_anonymous_grant`, `operation_not_allowed` covers structural completion-time
    invariant violations only. A registered `google`/`apple` identity on a native path is
    legitimate rather than a structural rejection; a missing or insufficient native gate is a
    vendor-material `proof_rejected` failure; and a web claimant that does not satisfy the
    registered stored-binding gate follows `verification_required` instead."""
    # [impl->req~grants-class-operation-not-allowed~1]
    if registered_claimant and branch is not ClaimBranch.web:
        return None
    if native_gate_missing:
        if branch is ClaimBranch.web:
            raise GrantFailureError("the web branch has no native gate")
        return vendor_material_rejection(VendorMaterialCause.verdict_lacks_device_recall)[1]
    if web_binding_unsatisfied:
        return verification_required_outcome(
            AnonFailureCondition.web_stored_binding_mismatch).client_class
    return ClientErrorClass.operation_not_allowed


# --- `verification_required`, `device_grant_exhausted` and `account_already_claimed` ---------------


def verification_required_scope(operation: AuthOperation,
                                *,
                                condition: AnonFailureCondition | None = None
                                ) -> tuple[AuthEventResult, ClientErrorClass]:
    """`verification_required` means a free-credit path is durably blocked for the current user
    state with no guaranteed free-credit alternate. On `claim_anonymous_grant` it covers durable
    anonymous-grant policy blocks, durable device-check denials other than an already-claimed
    state, a server-validated Cloudflare denial on web, and a completed web `providerData` lookup
    that fails the closed-classifier-and-stored-binding check. On `claim_registered_grant` it
    covers `idp_account_not_eligible`: the linked identity is not `google` or `apple`, or its
    stored `provider_uid` is absent."""
    # [impl->req~grants-class-verification-required~1]
    if operation is AuthOperation.claim_anonymous_grant:
        if condition is None:
            raise GrantFailureError("the anonymous claim names the condition it blocks on")
        outcome = verification_required_outcome(condition)
        return outcome.result, outcome.client_class
    if operation is AuthOperation.claim_registered_grant:
        result = AuthEventResult.idp_account_not_eligible
        return result, grants_client_class(result, operation=operation)
    raise GrantFailureError(f"{operation} has no free-credit verification_required case")


def device_grant_exhausted_scope(operation: AuthOperation) -> tuple[str | None, tuple[str, ...]]:
    """`device_grant_exhausted` means the requested free-grant path is durably closed: the
    relevant per-device claimed state is already set, or the web uniqueness rule shows the
    provider account already consumed the web gate. From an anonymous grant the client obtains a
    Google or Apple identity and calls `POST /auth/claim-registered-grant`; from a registered
    grant no further free-credit path is specified for that device state."""
    # [impl->req~grants-class-device-grant-exhausted~1]
    next_route = device_grant_exhausted_next_path(operation)
    if next_route is None:
        return None, ()
    return next_route, IDENTITY_ACTIONS


def account_already_claimed_scope(kind: GateConsumptionKind
                                  ) -> tuple[AuthEventResult, ClientErrorClass]:
    """`account_already_claimed` is the registered-account-grant gate: the resolved Google or
    Apple provider account has already backed a successful registered free-credit claim, and
    `idp_account_already_claimed` maps here. A web anonymous-grant uniqueness conflict must not
    map here — it is `device_grant_exhausted`."""
    # [impl->req~grants-class-account-already-claimed~1]
    if kind is GateConsumptionKind.registered_account_grant:
        result = AuthEventResult.idp_account_already_claimed
        client_class = grants_client_class(result,
                                           operation=AuthOperation.claim_registered_grant)
        if client_class is not ClientErrorClass.account_already_claimed:
            raise GrantFailureError(f"{result} surfaces as account_already_claimed")
        return result, client_class
    if kind is GateConsumptionKind.web_anonymous_gate:
        failure = classify_anonymous_failure(AnonFailureCondition.web_gate_already_consumed)
        if failure.client_class is ClientErrorClass.account_already_claimed:
            raise GrantFailureError(
                "a web anonymous-gate conflict is device_grant_exhausted, never "
                "account_already_claimed")
        return failure.result, failure.client_class
    raise GrantFailureError(f"{kind} is no free-grant gate")


# Every internal result that maps to `verification_temporarily_unavailable`, and the audit result
# a Cloudflare Turnstile dependency failure records: the class value itself, because no
# `cloudflare_lookup_unavailable` result exists.
# [impl->req~grants-class-verification-temporarily-unavailable~1]
VTU_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.native_claim_unavailable,
    AuthEventResult.native_claim_write_failed,
    AuthEventResult.firebase_lookup_unavailable,
    AuthEventResult.devicecheck_read_budget_exhausted,
    AuthEventResult.devicecheck_write_budget_exhausted,
    AuthEventResult.device_recall_read_budget_exhausted,
    AuthEventResult.device_recall_write_budget_exhausted,
    AuthEventResult.verification_temporarily_unavailable,
})
TURNSTILE_AUDIT_RESULT: AuthEventResult = AuthEventResult.verification_temporarily_unavailable
DEVICE_BIT_BUDGET_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.devicecheck_read_budget_exhausted,
    AuthEventResult.devicecheck_write_budget_exhausted,
    AuthEventResult.device_recall_read_budget_exhausted,
    AuthEventResult.device_recall_write_budget_exhausted,
})


def verification_temporarily_unavailable_results() -> frozenset[AuthEventResult]:
    """The internal results that map to `verification_temporarily_unavailable`: the native claim
    read and write failures, the Firebase lookup failure — at the anonymous `create-user`
    completion as much as at the web gate — the four device-bit budget exhaustions, written by
    either free-credit claim, and the Turnstile dependency failure that records the class value
    itself. No `cloudflare_lookup_unavailable` result exists."""
    # [impl->req~grants-class-verification-temporarily-unavailable~1]
    if "cloudflare_lookup_unavailable" in AuthEventResult.__members__:
        raise GrantFailureError("no cloudflare_lookup_unavailable result exists")
    for result in VTU_RESULTS:
        if ClientErrorClass(surface(result)[0]) \
                is not ClientErrorClass.verification_temporarily_unavailable:
            raise GrantFailureError(f"{result} surfaces as verification_temporarily_unavailable")
    if grants_client_class(AuthEventResult.firebase_lookup_unavailable,
                           operation=AuthOperation.create_user) \
            is not ClientErrorClass.verification_temporarily_unavailable:
        raise GrantFailureError(
            "firebase_lookup_unavailable at create-user completion is the same class")
    return VTU_RESULTS


# --- The registered claim's state-versus-duplicate-versus-dependency split -------------------------


class RegFailureCondition(StrEnum):
    """`claim_registered_grant`'s three failure families."""
    identity_not_google_or_apple = "identity_not_google_or_apple"
    stored_provider_uid_absent = "stored_provider_uid_absent"
    registered_gate_conflict = "registered_gate_conflict"
    device_check_dependency_failed = "device_check_dependency_failed"


# [impl->req~grants-reg-state-duplicate-dependency-split~1]
REG_FAILURES: dict[RegFailureCondition, AuthEventResult] = {
    RegFailureCondition.identity_not_google_or_apple: AuthEventResult.idp_account_not_eligible,
    RegFailureCondition.stored_provider_uid_absent: AuthEventResult.idp_account_not_eligible,
    RegFailureCondition.registered_gate_conflict: AuthEventResult.idp_account_already_claimed,
    RegFailureCondition.device_check_dependency_failed: AuthEventResult.native_claim_unavailable,
}


def registered_split(condition: RegFailureCondition) -> tuple[AuthEventResult, ClientErrorClass]:
    """The state-versus-duplicate-versus-dependency split for `claim_registered_grant`, normatively:
    a non-Google/Apple current identity or an absent stored `provider_uid` maps to
    `verification_required` / `idp_account_not_eligible`; a registered-account-grant gate conflict
    maps to `account_already_claimed` / `idp_account_already_claimed`; a registered device-check
    dependency failure, where that platform path participates, maps to
    `verification_temporarily_unavailable`."""
    # [impl->req~grants-reg-state-duplicate-dependency-split~1]
    result = REG_FAILURES.get(condition)
    if result is None:
        raise GrantFailureError(f"{condition} classifies no registered-claim failure")
    return result, grants_client_class(result, operation=AuthOperation.claim_registered_grant)


def assert_grant_time_and_write_time_distinct() -> None:
    """Grant-time `account_already_claimed` / `idp_account_already_claimed` and identity-write-time
    `provider_account_already_linked` / `operation_not_allowed` are distinct outcomes and must
    never be conflated."""
    # [impl->req~grants-reg-state-duplicate-dependency-split~1]
    grant_time = registered_split(RegFailureCondition.registered_gate_conflict)
    write_time = (AuthEventResult.provider_account_already_linked,
                  grants_client_class(AuthEventResult.provider_account_already_linked,
                                      operation=AuthOperation.create_user))
    if grant_time[0] is write_time[0] or grant_time[1] is write_time[1]:
        raise GrantFailureError("the grant-time and identity-write-time outcomes are distinct")
    assert_remediations_distinct(grant_time[1], write_time[1])


def assert_no_raw_provider_account_ids(columns: Iterable[str]) -> None:
    """Raw provider account identifiers are never stored on an audit, grant or anti-abuse row:
    only `idp_account_hash` and `idp_account_hash_key_version` may be persisted there."""
    # [impl->req~grants-reg-state-duplicate-dependency-split~1]
    names = list(columns)
    raw = sorted({name for name in names
                  if name.lower() in {"provider_uid", "provider_account_id", "idp_account_id",
                                      "google_uid", "apple_sub", "sub"}})
    if raw:
        raise GrantFailureError(f"{raw} is a raw provider account identifier")
    assert_anti_abuse_row_prohibitions(names)


# --- Accepted limitations: what would make this a vulnerability ------------------------------------

# The conditions that turn the accepted limitations above into a real vulnerability. Each one is
# a rule some guard already enforces; this is where they are checked together.
# [impl->req~grants-accepted-limitations-vulnerability-conditions~1]
VULNERABILITY_CONDITIONS: tuple[str, ...] = (
    "grants_before_reading_device_state",
    "grants_before_vendor_confirms_write",
    "grants_before_verifying_web_binding_and_bot_gate",
    "treats_device_or_bot_check_as_ownership_proof",
    "persists_raw_vendor_tokens_or_device_principal",
    "omits_user_source_or_web_provider_account_uniqueness",
    "creates_multiple_active_free_grants_for_one_user",
    "creates_registered_grant_when_allowance_already_used",
)


def assert_not_vulnerable(branch: ClaimBranch,
                          *,
                          device_state_read: bool,
                          write: DeviceBitWrite | None,
                          web_binding_verified: bool,
                          bot_gate_verified: bool,
                          proof_use: ProofUse,
                          persisted_columns: Iterable[str] = (),
                          uniqueness_domains: Iterable[str] = (),
                          committed_free_sources: Sequence[AccessGrantSource] = (),
                          active_grants: int = 0,
                          registered_claim: bool = False) -> None:
    """The accepted limitations are not a vulnerability unless the implementation does one of the
    things below. Every clause is checked, and each delegates to the guard that owns the rule."""
    # [impl->req~grants-accepted-limitations-vulnerability-conditions~1]
    if len(VULNERABILITY_CONDITIONS) != 8:
        raise GrantFailureError("the vulnerability list has eight conditions")
    if branch in {ClaimBranch.native_ios, ClaimBranch.native_android}:
        if not device_state_read:
            raise GrantFailureError("a grant is never issued before the device state is read")
        # Only this attempt's vendor-confirmed write permits the grant row.
        assert_grant_row_permitted(write)
    elif not (web_binding_verified and bot_gate_verified):
        raise GrantFailureError(
            "a web grant is never issued before the stored-binding match and the bot gate")
    # Neither the device check nor the bot check is ever account-ownership proof.
    assert_device_check_is_anti_abuse_only(proof_use)
    # No raw DeviceCheck, Play Integrity or Cloudflare token, and no synthetic stable
    # device-check principal hash, is persisted.
    assert_no_raw_vendor_material_stored(persisted_columns)
    required = {"user_grant_source"}
    if branch is ClaimBranch.web:
        required.add("web_anonymous_gate_provider_account")
    missing = sorted(required - set(uniqueness_domains))
    if missing:
        raise GrantFailureError(f"{missing} uniqueness must not be omitted")
    # At most one active grant per user, and at most one committed grant per free source.
    assert_database_bounds(committed_free_sources=committed_free_sources,
                           active_grants=active_grants)
    if active_grants > MAX_ACTIVE_GRANTS_PER_USER:
        raise GrantFailureError("a user never holds multiple active free grants")
    if MAX_WEB_GATES_PER_PROVIDER_ACCOUNT != 1:
        raise GrantFailureError("one web anonymous gate per provider account")
    if registered_claim:
        assert_registered_allowance_unused(committed_free_sources)


# The free allowance is one grant per user across both free sources: a user whose own history
# already carries either has spent it.
FREE_ALLOWANCE_SOURCES: frozenset[AccessGrantSource] = frozenset({
    AccessGrantSource.anonymous_device_grant,
    AccessGrantSource.registered_account_grant,
})


def assert_registered_allowance_unused(committed_free_sources: Sequence[AccessGrantSource],
                                       row: ExternalIdentityRow | None = None) -> None:
    """A registered grant is never created for a user whose own grant history already carries the
    free allowance, and never for an identity that is not `google` or `apple`."""
    # [impl->req~grants-accepted-limitations-vulnerability-conditions~1]
    if any(source in FREE_ALLOWANCE_SOURCES for source in committed_free_sources):
        raise GrantFailureError("this user's grant history already carries the free allowance")
    if row is not None and row.provider not in REGISTERED_PROVIDERS:
        raise GrantFailureError("the registered grant needs a google or apple stored provider")
