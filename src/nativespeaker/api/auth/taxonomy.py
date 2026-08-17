"""The shared client-visible error contract.

One registry of client-visible classes, one normative remediation per class, and one response
shape. Every authenticated route rejects through this module, including the shared pre-handler
barrier, so no `core.auth_event_result` value ever reaches a client.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.tokens import JwtRejectionReason
from nativespeaker.api.exceptions import ErrorCode


class ClientErrorClass(StrEnum):
    """The client-visible classes. This enumeration is the whole registry."""
    # [impl->req~shared-error-class-registry~1]
    # [impl->req~shared-error-registry-exhaustive~1]
    # [impl->req~shared-error-class-auth-required~1]
    auth_required = "auth_required"
    # [impl->req~shared-error-class-preauth-identity-not-allowed~1]
    preauth_identity_not_allowed = "preauth_identity_not_allowed"
    # [impl->req~shared-error-class-account-unavailable~1]
    account_unavailable = "account_unavailable"
    # [impl->req~shared-error-class-identity-already-linked~1]
    identity_already_linked = "identity_already_linked"
    # [impl->req~shared-error-class-challenge-required~1]
    challenge_required = "challenge_required"
    # [impl->req~shared-error-class-invalid-request~1]
    invalid_request = "invalid_request"
    # [impl->req~shared-error-class-proof-rejected~1]
    proof_rejected = "proof_rejected"
    # [impl->req~shared-error-class-operation-not-allowed~1]
    operation_not_allowed = "operation_not_allowed"
    # [impl->req~shared-error-class-verification-required~1]
    verification_required = "verification_required"
    # [impl->req~shared-error-class-device-grant-exhausted~1]
    device_grant_exhausted = "device_grant_exhausted"
    # [impl->req~shared-error-class-account-already-claimed~1]
    account_already_claimed = "account_already_claimed"
    # [impl->req~shared-error-class-verification-temporarily-unavailable~1]
    verification_temporarily_unavailable = "verification_temporarily_unavailable"
    # [impl->req~shared-error-class-registration-temporarily-unavailable~1]
    registration_temporarily_unavailable = "registration_temporarily_unavailable"


class TaxonomyError(RuntimeError):
    """A rejection was about to leave the backend outside the shared error contract."""


@dataclass(frozen=True, slots=True)
class Remediation:
    """The normative client remediation a class carries. It is part of the client contract, not
    a hint inferred from the class name, so every class names its own action and no two classes
    share one: a client that collapsed two of them would lose a required behaviour."""
    action: str
    http_status: int
    transient: bool = False
    terminal: bool = False
    retry_same_request: bool = False
    next_route: str | None = None
    fresh_challenge: bool = False
    fresh_proof: bool = False
    discard_credentials: bool = False
    reuse_unexpired_challenge: bool = False
    carries_blocking_end: bool = False
    sends_retry_after: bool = False
    switch_flow: bool = False


# Each class's normative remediation. The action strings are the contract's own vocabulary.
# [impl->req~shared-error-remediation-normative~1]
REMEDIATIONS: dict[ClientErrorClass, Remediation] = {
    # Re-authenticate through the Firebase client SDK and retry with a fresh ID token.
    # [impl->req~shared-auth-required-grouping~1]
    ClientErrorClass.auth_required: Remediation(
        action="reauthenticate_and_retry_with_fresh_id_token", http_status=401),
    # An unlinked identity called a linked-only route: complete create-user, then retry.
    # [impl->req~shared-preauth-not-allowed-remediation~1]
    ClientErrorClass.preauth_identity_not_allowed: Remediation(
        action="create_user_then_retry_linked_only_route", http_status=403,
        next_route="/auth/create-user"),
    # Terminal: discard tokens, stop refreshing, stop every further authenticated call —
    # retries of the same route and of sign-out-all included — and show "contact support".
    # Re-authentication and create-user are not remedies; there is no in-band unblock.
    # [impl->req~shared-account-unavailable-remediation~1]
    ClientErrorClass.account_unavailable: Remediation(
        action="stop_all_authenticated_calls_and_contact_support", http_status=403,
        terminal=True, discard_credentials=True),
    # Call `/auth/sync` and proceed on the linked account.
    # [impl->req~shared-identity-already-linked-remediation~1]
    ClientErrorClass.identity_already_linked: Remediation(
        action="sync_then_proceed_on_linked_account", http_status=409, next_route="/auth/sync"),
    # Prepare a fresh challenge and retry.
    # [impl->req~shared-challenge-required-remediation~1]
    ClientErrorClass.challenge_required: Remediation(
        action="prepare_fresh_challenge_and_retry", http_status=403, fresh_challenge=True),
    # Correct the request and resend it. The rejection has no side effects, so the corrected
    # retry may reuse the same challenge while that challenge is unexpired.
    # [impl->req~shared-invalid-request-remediation~1]
    ClientErrorClass.invalid_request: Remediation(
        action="correct_the_request_shape_and_resend", http_status=400,
        reuse_unexpired_challenge=True),
    # Retrying the same material cannot succeed: obtain fresh proof material and retry as a
    # whole new attempt, with a fresh challenge where the operation is challenge-bearing.
    # [impl->req~shared-proof-rejected-remediation~1]
    ClientErrorClass.proof_rejected: Remediation(
        action="obtain_fresh_proof_material_and_retry_whole_attempt", http_status=403,
        fresh_proof=True, fresh_challenge=True),
    # Remedy the underlying structural state before retrying, never blind-retry from the same
    # state; where the blocking state is a held grant with a known end, wait for that end.
    # [impl->req~shared-operation-not-allowed-remediation~1]
    ClientErrorClass.operation_not_allowed: Remediation(
        action="remedy_structural_state_before_retrying", http_status=403,
        carries_blocking_end=True),
    # Durable for the current user state and never retried on a timer: sign in with, upgrade
    # to, or link a Google or Apple identity and retry only where that changes the state.
    # [impl->req~shared-verification-required-remediation~1]
    ClientErrorClass.verification_required: Remediation(
        action="obtain_registered_identity_then_retry_only_if_state_changed", http_status=403),
    # The requested free-grant path is closed for this caller or device; retrying the same
    # request cannot succeed. Which path closed decides where the client goes next.
    # [impl->req~shared-device-grant-exhausted-remediation~1]
    ClientErrorClass.device_grant_exhausted: Remediation(
        action="stop_this_grant_path_and_follow_the_paths_own_next_step", http_status=403),
    # Final for that provider account across every user, identity, reinstall and device.
    # [impl->req~shared-account-already-claimed-remediation~1]
    ClientErrorClass.account_already_claimed: Remediation(
        action="stop_no_further_free_credit_for_this_provider_account", http_status=403,
        terminal=True),
    # Transient: retry the whole operation later with backoff, with fresh proof material and a
    # fresh challenge where the operation is challenge-bearing.
    # [impl->req~shared-verification-temporarily-unavailable-remediation~1]
    ClientErrorClass.verification_temporarily_unavailable: Remediation(
        action="retry_whole_operation_later_with_backoff", http_status=503,
        transient=True, fresh_proof=True, fresh_challenge=True),
    # Transient registration rate-limiting: wait at least until `Retry-After`, or a default
    # backoff when the header is absent, then retry registration.
    # [impl->req~shared-registration-temporarily-unavailable-remediation~1]
    ClientErrorClass.registration_temporarily_unavailable: Remediation(
        action="wait_for_retry_after_then_retry_registration", http_status=429,
        transient=True, sends_retry_after=True),
}


# Operation-specific classes an endpoint contract adds under the extension rule. They live
# outside the shared registry and are part of the same response shape, never a second contract.
# [impl->req~shared-error-classes-govern-all-routes~1]
RATE_LIMITED_CLASS = "rate_limited"

_ENDPOINT_REMEDIATIONS: dict[str, Remediation] = {
    # The generic backend admission-control rejection. Its remediation is genuinely distinct
    # from `registration_temporarily_unavailable`, which tells the client to retry registration
    # specifically, and from `verification_temporarily_unavailable`, which is a verification-path
    # failure this must never be confused with.
    # [impl->req~ratelimit-reject-429-with-retry-after~1]
    RATE_LIMITED_CLASS: Remediation(
        action="wait_for_retry_after_then_retry_request", http_status=429,
        transient=True, sends_retry_after=True, retry_same_request=True),
}


def remediation_for(client_class: str) -> Remediation:
    """The class's normative remediation, shared or endpoint-specific."""
    # [impl->req~shared-error-remediation-normative~1]
    if client_class in set(ClientErrorClass):
        return REMEDIATIONS[ClientErrorClass(client_class)]
    remediation = _ENDPOINT_REMEDIATIONS.get(client_class)
    if remediation is None:
        raise TaxonomyError(f"{client_class} is no client-visible class")
    return remediation


def _assert_registry_complete() -> None:
    """Every declared class carries its own remediation, and no two classes share one: two
    classes with different remediations can never be collapsed into a single client handler."""
    # [impl->req~shared-error-remediation-normative~1]
    missing = set(ClientErrorClass) - set(REMEDIATIONS)
    if missing:
        raise TaxonomyError(f"{sorted(missing)} carry no remediation")
    actions = [remediation.action for remediation in REMEDIATIONS.values()]
    if len(set(actions)) != len(actions):
        raise TaxonomyError("two client-visible classes share one remediation")


_assert_registry_complete()


# --- The shared response shape --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClientRejection:
    """What the client sees: a status, the shared body naming the class, and headers."""
    status: int
    body: dict[str, str]
    headers: dict[str, str]


def client_response(client_class: str,
                    *,
                    retry_after_seconds: Sequence[int] = (),
                    blocked_until: datetime | None = None) -> ClientRejection:
    """Build the one shared response shape. The body names the class and carries nothing else:
    no internal result, no bounded rejection reason, no issuer, integration or failed check, no
    device-check state, hash, anti-abuse result, or other diagnostic detail."""
    # [impl->req~shared-error-no-internal-results-exposed~1]
    # [impl->req~shared-invalid-external-jwt-reasons~1]
    # [impl->req~shared-device-grant-exhausted-remediation~1]
    remediation = remediation_for(client_class)
    body = {"code": client_class}
    headers: dict[str, str] = {}
    if retry_after_seconds:
        if not remediation.sends_retry_after:
            raise TaxonomyError(f"{client_class} carries no Retry-After")
        # The header reflects the limiting bucket's true wait — the longest known wait when
        # more than one limit applies — and never identifies which bucket fired.
        # [impl->req~shared-registration-temporarily-unavailable-remediation~1]
        headers["Retry-After"] = str(max(retry_after_seconds))
    if blocked_until is not None:
        if not remediation.carries_blocking_end:
            raise TaxonomyError(f"{client_class} carries no blocking end")
        # Where the blocking state is a held grant with a known end, the response carries that
        # end so the client waits for it instead of retrying earlier.
        # [impl->req~shared-operation-not-allowed-remediation~1]
        body["blocked_until"] = blocked_until.isoformat()
    return ClientRejection(status=remediation.http_status, body=body, headers=headers)


# --- Internal results grouped by client remediation -----------------------------------------


class ProviderDataReadPoint(StrEnum):
    """The closed set of Firebase Admin `providerData` read points the identity files define."""
    anonymous_create_user_completion = "anonymous_create_user_completion"
    registered_create_user_completion = "registered_create_user_completion"
    upgrade_anonymous_completion = "upgrade_anonymous_completion"
    web_anonymous_grant_gate = "web_anonymous_grant_gate"
    claim_registered_grant_completion = "claim_registered_grant_completion"


# Backend token-verification failure, and the non-retryable Firebase Admin `user-not-found`
# outcome at any of the five required `providerData` read points.
# [impl->req~shared-auth-required-grouping~1]
AUTH_REQUIRED_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.invalid_external_jwt,
    AuthEventResult.firebase_user_unresolved,
})

# Not grouped under `auth_required`, each with its own class and its own remediation.
# [impl->req~shared-auth-required-exclusions~1]
AUTH_REQUIRED_EXCLUSIONS: dict[AuthEventResult, ClientErrorClass] = {
    AuthEventResult.blocked_user: ClientErrorClass.account_unavailable,
    AuthEventResult.preauth_identity_not_allowed: ClientErrorClass.preauth_identity_not_allowed,
    AuthEventResult.identity_already_linked: ClientErrorClass.identity_already_linked,
}

# Every unknown, expired, wrong-operation, wrong-operation-variant, wrong-nonce, wrong-identity,
# malformed, already-claimed or already-consumed challenge. Exactly these five internal results
# exist for it: there is no `challenge_replayed` result and none for the claimed state.
# [impl->req~shared-challenge-required-remediation~1]
CHALLENGE_REQUIRED_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.challenge_not_found,
    AuthEventResult.challenge_identity_mismatch,
    AuthEventResult.challenge_operation_mismatch,
    AuthEventResult.challenge_expired,
    AuthEventResult.challenge_consumed,
})

# The bounded machine-readable reason enumeration an `invalid_external_jwt` rejection carries.
# It lives in the audit row's `details` and in metric labels; it is never client-visible.
# [impl->req~shared-invalid-external-jwt-reasons~1]
INVALID_EXTERNAL_JWT_REASONS: frozenset[str] = frozenset(str(reason)
                                                         for reason in JwtRejectionReason)

# The shared internal-result-to-class mapping every authenticated route rejects through,
# including the shared pre-handler barrier. Endpoint contracts extend it; they never replace
# or rename a shared class.
# [impl->req~shared-error-classes-govern-all-routes~1]
RESULT_TO_CLASS: dict[AuthEventResult, ErrorCode] = {
    AuthEventResult.invalid_external_jwt: "auth_required",
    AuthEventResult.firebase_user_unresolved: "auth_required",
    AuthEventResult.preauth_identity_not_allowed: "preauth_identity_not_allowed",
    AuthEventResult.historical_identity: "account_unavailable",
    AuthEventResult.blocked_user: "account_unavailable",
    AuthEventResult.identity_already_linked: "identity_already_linked",
    AuthEventResult.challenge_not_found: "challenge_required",
    AuthEventResult.challenge_expired: "challenge_required",
    AuthEventResult.challenge_consumed: "challenge_required",
    AuthEventResult.challenge_identity_mismatch: "challenge_required",
    AuthEventResult.challenge_operation_mismatch: "challenge_required",
    AuthEventResult.proof_malformed: "proof_rejected",
    AuthEventResult.invalid_restore_proof: "proof_rejected",
    AuthEventResult.policy_rejected: "operation_not_allowed",
    AuthEventResult.provider_account_already_linked: "operation_not_allowed",
    AuthEventResult.firebase_lookup_unavailable: "verification_temporarily_unavailable",
    AuthEventResult.verification_temporarily_unavailable: "verification_temporarily_unavailable",
}

# The only results this specification names identically on both sides.
_NAMED_IDENTICALLY: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.identity_already_linked,
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.verification_temporarily_unavailable,
})


def _assert_grouping_consistent() -> None:
    """`auth_required` groups the token-verification and Firebase `user-not-found` results and
    nothing else; a historical identity, a blocked user, an unlinked caller on a linked-only
    route and an already-linked create-user caller each keep their own class."""
    # [impl->req~shared-auth-required-grouping~1]
    # [impl->req~shared-auth-required-exclusions~1]
    grouped = {result for result, klass in RESULT_TO_CLASS.items()
               if klass == ClientErrorClass.auth_required}
    if grouped != AUTH_REQUIRED_RESULTS:
        raise TaxonomyError(f"auth_required groups {sorted(grouped)}")
    for result, expected in AUTH_REQUIRED_EXCLUSIONS.items():
        if RESULT_TO_CLASS[result] != expected:
            raise TaxonomyError(f"{result} must surface as {expected}")
    # A historical identity is indistinguishable from a blocked user and must never surface
    # `preauth_identity_not_allowed`.
    # [impl->req~shared-account-unavailable-remediation~1]
    if RESULT_TO_CLASS[AuthEventResult.historical_identity] != ClientErrorClass.account_unavailable:
        raise TaxonomyError("a historical identity surfaces as account_unavailable")
    # A required Firebase Admin lookup that definitively returned `user-not-found` is an
    # `auth_required`, never a transient verification failure.
    if (RESULT_TO_CLASS[AuthEventResult.firebase_user_unresolved]
            == ClientErrorClass.verification_temporarily_unavailable):
        raise TaxonomyError("firebase_user_unresolved is not a transient verification failure")
    # Every challenge rejection surfaces as `challenge_required`, and no result exists for the
    # claimed state or for a replay.
    # [impl->req~shared-challenge-required-remediation~1]
    for result in CHALLENGE_REQUIRED_RESULTS:
        if RESULT_TO_CLASS[result] != ClientErrorClass.challenge_required:
            raise TaxonomyError(f"{result} must surface as challenge_required")
    for forbidden in ("challenge_replayed", "challenge_claimed"):
        if forbidden in AuthEventResult.__members__:
            raise TaxonomyError(f"no {forbidden} result exists")


_assert_grouping_consistent()


class UnsurfacedResultError(RuntimeError):
    """An internal result reached the client boundary with no shared class mapped to it."""


def surface(result: AuthEventResult) -> tuple[ErrorCode, int]:
    """Map an internal `core.auth_event_result` onto its shared client-visible class. Fails
    closed rather than leaking the internal value, and enforces that the audited internal result
    is never less specific than the class returned."""
    # [impl->req~shared-error-classes-govern-all-routes~1]
    # [impl->req~shared-error-no-internal-results-exposed~1]
    client_class = RESULT_TO_CLASS.get(result)
    if client_class is None:
        raise UnsurfacedResultError(f"{result} has no shared client-visible class")
    if str(result) == client_class and result not in _NAMED_IDENTICALLY:
        raise UnsurfacedResultError(f"{result} must audit more specifically than {client_class}")
    return client_class, remediation_for(client_class).http_status


def register_client_class(result: AuthEventResult,
                          client_class: ErrorCode,
                          status: int,
                          *,
                          remediation: Remediation | None = None) -> None:
    """The extension point for the endpoint- and domain-specific halves of the contract — the
    grants domain owns the detailed mapping between its internal audit results and these
    classes, including its alternate-path and transient-failure remediation rules. An extension
    adds only its own post-barrier, operation-specific cases: it never redefines a shared class,
    never remaps a result the shared contract owns, and may introduce a new class only with a
    remediation genuinely distinct from every existing one."""
    # [impl->req~shared-error-grant-mapping-owner~1]
    # [impl->req~shared-error-classes-govern-all-routes~1]
    # [impl->req~shared-error-no-internal-results-exposed~1]
    if result in RESULT_TO_CLASS:
        raise UnsurfacedResultError(f"{result} already maps to a shared class")
    known = (REMEDIATIONS[ClientErrorClass(client_class)]
             if client_class in set(ClientErrorClass)
             else _ENDPOINT_REMEDIATIONS.get(client_class))
    if known is not None:
        if remediation is not None and remediation != known:
            raise UnsurfacedResultError(f"{client_class} already carries its own remediation")
        if known.http_status != status:
            raise UnsurfacedResultError(f"{client_class} already carries a different status")
    else:
        if remediation is None:
            raise UnsurfacedResultError(f"{client_class} needs its own distinct remediation")
        register_endpoint_class(client_class, remediation, status)
    RESULT_TO_CLASS[result] = client_class


def register_endpoint_class(client_class: ErrorCode, remediation: Remediation,
                            status: int) -> Remediation:
    """Declare an operation-specific class whose internal result is chosen per rejection rather
    than by a fixed result-to-class entry. A brand-new class is permitted only where its
    remediation is genuinely distinct from every class already declared; re-declaring an
    identical one is idempotent, so import order cannot matter."""
    # [impl->req~shared-error-classes-govern-all-routes~1]
    known = (REMEDIATIONS[ClientErrorClass(client_class)] if client_class in set(ClientErrorClass)
             else _ENDPOINT_REMEDIATIONS.get(client_class))
    if known is not None:
        if known != remediation:
            raise UnsurfacedResultError(f"{client_class} already carries its own remediation")
        return known
    existing = ({entry.action for entry in REMEDIATIONS.values()}
                | {entry.action for entry in _ENDPOINT_REMEDIATIONS.values()})
    if remediation.action in existing:
        raise UnsurfacedResultError(f"{client_class} duplicates an existing remediation")
    if remediation.http_status != status:
        raise UnsurfacedResultError(f"{client_class} carries a different status")
    _ENDPOINT_REMEDIATIONS[client_class] = remediation
    return remediation


class ClassNotEmittableError(RuntimeError):
    """An endpoint was about to emit a class the shared registry does not declare, or one it
    never mapped."""


def assert_emitted_subset(emitted: Iterable[str],
                          mapped_results: Iterable[AuthEventResult]) -> None:
    """An endpoint's emitted subset is its own: it need not emit every shared class, and it may
    emit only classes this registry declares and the endpoint explicitly maps. `invalid_request`
    is the one exception — every challenge-bearing endpoint emits it through the shared
    mode-signal partition, which has no internal result and so appears in no mapping."""
    # [impl->req~shared-error-registry-exhaustive~1]
    mapped = {RESULT_TO_CLASS[result] for result in mapped_results}
    declared = set(ClientErrorClass) | set(_ENDPOINT_REMEDIATIONS)
    for client_class in emitted:
        if client_class not in declared:
            raise ClassNotEmittableError(f"{client_class} is no declared client-visible class")
        if client_class == ClientErrorClass.invalid_request:
            continue
        if client_class not in mapped:
            raise ClassNotEmittableError(f"{client_class} is not mapped by this endpoint")


def _assert_invalid_request_unmapped() -> None:
    """The mode-signal partition belongs to the admission phase and has no internal result, so
    no endpoint carries `invalid_request` in an internal-result-to-class mapping."""
    # [impl->req~shared-error-registry-exhaustive~1]
    if ClientErrorClass.invalid_request in RESULT_TO_CLASS.values():
        raise TaxonomyError("invalid_request has no internal core.auth_event_result")


_assert_invalid_request_unmapped()


# --- Path-specific remediation ---------------------------------------------------------------

# Which free-grant path a `device_grant_exhausted` closed decides where the client goes next:
# from the anonymous claim, on to the registered-account grant path; from the registered claim,
# nowhere — no further free-credit path is specified for that device state.
# [impl->req~shared-device-grant-exhausted-remediation~1]
_EXHAUSTED_NEXT_PATH: dict[AuthOperation, str | None] = {
    AuthOperation.claim_anonymous_grant: "/auth/claim-registered-grant",
    AuthOperation.claim_registered_grant: None,
}


def device_grant_exhausted_next_path(operation: AuthOperation) -> str | None:
    """The next free-credit path after an exhausted device grant, or `None` where the client
    must stop. Only the two grant operations can produce this class."""
    # [impl->req~shared-device-grant-exhausted-remediation~1]
    if operation not in _EXHAUSTED_NEXT_PATH:
        raise TaxonomyError(f"{operation} does not emit device_grant_exhausted")
    return _EXHAUSTED_NEXT_PATH[operation]


def next_route_for(client_class: str) -> str | None:
    """The single route the class's remediation names, or `None` where the remediation is
    terminal and the client must stop: after `account_unavailable` there is no retry of the
    same route, no alternate endpoint, and `POST /auth/sign-out-all` is never recovery."""
    # [impl->req~shared-account-unavailable-remediation~1]
    # [impl->req~shared-account-already-claimed-remediation~1]
    remediation = remediation_for(client_class)
    return None if remediation.terminal else remediation.next_route
