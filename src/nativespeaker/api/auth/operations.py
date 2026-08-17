"""The canonical state-changing auth operation inventory and the audited attempt path.

Membership is read from the inventory table alone — never inferred from a path name or from
whether a handler writes business state.
"""

from dataclasses import dataclass
from enum import StrEnum

from nativespeaker.api.exceptions import ErrorCode, ServiceError


class AuthOperation(StrEnum):
    """`core.auth_operation`."""
    create_user = "create_user"
    upgrade_anonymous_to_registered = "upgrade_anonymous_to_registered"
    claim_anonymous_grant = "claim_anonymous_grant"
    claim_registered_grant = "claim_registered_grant"
    restore_subscription = "restore_subscription"
    sign_out_all = "sign_out_all"
    sync = "sync"


class IdentityProvider(StrEnum):
    """`core.identity_provider`; also the domain of the client-selected operation variant. The
    only allowed provider values are `anonymous`, `google` and `apple`."""
    # The closed set of allowed `provider` values, and the whole of it: a fourth member would be
    # a fourth allowed value, which this enumeration is what forbids.
    # [impl->req~users-allowed-provider-values~1]
    # [impl->req~sessions-provider-allowed-values~1]
    # [impl->req~sessions-provider-value-anonymous~1]
    anonymous = "anonymous"
    # [impl->req~sessions-provider-value-google~1]
    google = "google"
    # [impl->req~sessions-provider-value-apple~1]
    apple = "apple"


@dataclass(frozen=True, slots=True)
class OperationEntry:
    method: str
    path: str
    operation: AuthOperation
    challenge_bearing: bool
    variants: tuple[IdentityProvider, ...] = ()
    default_variant: IdentityProvider | None = None


# The canonical enumeration: route and method that select each operation, the
# `core.auth_operation` value it records, and whether it is challenge-bearing.
# [impl->req~shared-operation-inventory-table~1]
# [impl->req~shared-sync-owned-by-sessions-and-quota-files~1]
OPERATION_INVENTORY: tuple[OperationEntry, ...] = (
    OperationEntry("POST", "/auth/create-user", AuthOperation.create_user, True,
                   (IdentityProvider.anonymous, IdentityProvider.google, IdentityProvider.apple),
                   IdentityProvider.anonymous),
    OperationEntry("POST", "/auth/upgrade-anonymous", AuthOperation.upgrade_anonymous_to_registered,
                   True, (IdentityProvider.google, IdentityProvider.apple)),
    OperationEntry("POST", "/auth/claim-anonymous-grant", AuthOperation.claim_anonymous_grant, True),
    OperationEntry("POST", "/auth/claim-registered-grant", AuthOperation.claim_registered_grant, True),
    OperationEntry("POST", "/auth/restore-subscription", AuthOperation.restore_subscription, False),
    OperationEntry("POST", "/auth/sign-out-all", AuthOperation.sign_out_all, False),
    OperationEntry("POST", "/auth/sync", AuthOperation.sync, False),
)

_BY_ROUTE: dict[tuple[str, str], OperationEntry] = {
    (entry.method, entry.path): entry for entry in OPERATION_INVENTORY
}
_BY_OPERATION: dict[AuthOperation, OperationEntry] = {
    entry.operation: entry for entry in OPERATION_INVENTORY
}

# The four challenge-bearing operations. Challenge issuance, presentation, validation and
# consumption bind this subset alone.
# [impl->req~shared-challenge-bearing-subset~1]
CHALLENGE_BEARING_OPERATIONS: frozenset[AuthOperation] = frozenset(
    entry.operation for entry in OPERATION_INVENTORY if entry.challenge_bearing)


def match_operation(method: str, path: str) -> AuthOperation | None:
    """Exact route-and-method lookup against the inventory. Everything else is routine
    authenticated traffic."""
    # [impl->req~shared-inventory-membership-authoritative~1]
    entry = _BY_ROUTE.get((method.upper(), path))
    return entry.operation if entry is not None else None


def is_on_audited_path(method: str, path: str) -> bool:
    """A request is on the audited attempt path if and only if it matched a canonical
    state-changing auth operation. A property of the matched route and method alone."""
    # [impl->req~shared-audited-path-entry~1]
    # [impl->req~shared-sync-canonical-operation~1]
    return match_operation(method, path) is not None


def requires_attempt_audit(operation: AuthOperation) -> bool:
    """The audited-path entry, mandatory attempt audit and admission carve-out bind all seven
    inventory operations uniformly."""
    # [impl->req~shared-inventory-obligations-bind-all-seven~1]
    return operation in _BY_OPERATION


def is_challenge_bearing(operation: AuthOperation) -> bool:
    return operation in CHALLENGE_BEARING_OPERATIONS


def supports_prepare(operation: AuthOperation) -> bool:
    """Only the challenge-bearing subset has a prepare phase."""
    return is_challenge_bearing(operation)


def variants_for(operation: AuthOperation) -> tuple[IdentityProvider, ...]:
    return _BY_OPERATION[operation].variants


def route_for(operation: AuthOperation) -> tuple[str, str]:
    """The method and path the inventory names for this operation."""
    entry = _BY_OPERATION[operation]
    return entry.method, entry.path


class InvalidOperationVariantError(ServiceError, ValueError):
    """The client-declared operation variant is not one this operation defines.

    The request's shape is wrong before any operation-specific meaning can be assigned to it,
    so it takes the shared `invalid_request` class under the request-shape partition rather
    than escaping as an unhandled error and becoming a 500. Like every other request-shape
    rejection it carries no internal `core.auth_event_result`."""
    # [impl->req~shared-error-class-invalid-request~1]
    # [impl->req~shared-error-classes-govern-all-routes~1]
    # [impl->req~shared-invalid-request-remediation~1]
    status_code = 400
    error_code: ErrorCode = "invalid_request"


def normalize_variant(operation: AuthOperation,
                      declared: str | None) -> IdentityProvider | None:
    """Normalize a client-declared variant once, at prepare, by exact case-sensitive match
    against the identity-provider enumeration. Operations without a variant accept none."""
    # [impl->req~shared-challenge-binds-variant~1]
    entry = _BY_OPERATION[operation]
    if not entry.variants:
        if declared is not None:
            raise InvalidOperationVariantError(f"{operation} defines no operation variant")
        return None
    if declared is None:
        if entry.default_variant is None:
            raise InvalidOperationVariantError(f"{operation} requires a declared provider")
        return entry.default_variant
    for variant in entry.variants:
        if declared == variant.value:
            return variant
    raise InvalidOperationVariantError(f"{declared!r} is not a variant of {operation}")


# --- The admission phase -----------------------------------------------------------------

class AdmissionRejection(StrEnum):
    """Rejections taken before the backend has selected a recognized auth operation, plus the
    checks this specification keeps in the admission phase wherever they sit."""
    gateway_rate_limited = "gateway_rate_limited"
    backend_rate_limited = "backend_rate_limited"
    provider_budget_exhausted = "provider_budget_exhausted"
    overload_shed = "overload_shed"
    http_parse_error = "http_parse_error"
    body_too_large = "body_too_large"
    unsupported_content_type = "unsupported_content_type"
    json_syntax_error = "json_syntax_error"
    route_or_method_mismatch = "route_or_method_mismatch"
    mode_signal_invalid = "mode_signal_invalid"


# The four free-grant device-bit provider budgets are the single exception: each is checked
# inside the claim, after the challenge has been claimed, so its exhaustion is a
# verification-dependency outcome on the audited attempt path, not an admission rejection.
FREE_GRANT_DEVICE_BIT_BUDGETS: frozenset[str] = frozenset({
    "adapter_devicecheck_read",
    "adapter_devicecheck_write",
    "adapter_play_integrity_device_recall_read",
    "adapter_play_integrity_device_recall_write",
})


def is_admission_phase(rejection: AdmissionRejection, *, budget: str | None = None) -> bool:
    """Admission-control rejections are never on the audited attempt path and write no
    `audit.auth_events` row; their rejection, telemetry and ordering behaviour is governed by
    `08-rate-limits-and-admission-control.md`."""
    # [impl->req~shared-admission-phase-precedes-path~1]
    # [impl->req~shared-rate-limit-contract-delegation~1]
    if rejection is AdmissionRejection.provider_budget_exhausted:
        return budget not in FREE_GRANT_DEVICE_BIT_BUDGETS
    return True
