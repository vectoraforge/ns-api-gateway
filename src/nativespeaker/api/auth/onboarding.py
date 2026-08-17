"""The two onboarding operations as the endpoints wire them, and the
`POST /auth/upgrade-anonymous` request contract.

The operation-to-endpoint inventory, the shared-contract wiring both endpoints depend on, and
the request contract of the upgrade endpoint live here. The `create_user` operation itself is
in `create_user.py`; the identity rules both operations share are in `users.py`, and the
challenge mechanics they run on are the shared procedures in `procedures.py`.
"""

from collections.abc import Mapping
from datetime import timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.challenges import ChallengeRow, ChallengeState, variants_equal
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    IdentityState,
)
from nativespeaker.api.auth.modes import (
    CHALLENGE_QUERY_PARAM,
    CHALLENGE_QUERY_VALUE,
    RequestMode,
    classify_mode,
)
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    normalize_variant,
    route_for,
)
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.users import (
    UPGRADE_ROUTE,
    UpgradeBranch,
    UpgradeDecision,
    UsersError,
    apply_upgrade,
    assert_no_secondary_auth_state,
    assert_shared_challenge_contracts,
    context_pair,
    resolves_as_linked,
    upgrade_linked_identity,
    users_operation,
    variant_mismatch,
)

# --- Operation logic: the operations and the endpoints that perform them -----------------------

# The state-changing auth operations of this split and the endpoint each one is performed by.
# One operation per endpoint, taken from the shared inventory rather than restated here.
ONBOARDING_ENDPOINTS: dict[AuthOperation, tuple[str, str]] = {
    # 1. `create_user` -- `POST /auth/create-user`
    # [impl->req~users-operation-create-user-endpoint~1]
    AuthOperation.create_user: route_for(AuthOperation.create_user),
    # 2. `upgrade_anonymous_to_registered` -- `POST /auth/upgrade-anonymous`
    # [impl->req~users-operation-upgrade-anonymous-endpoint~1]
    AuthOperation.upgrade_anonymous_to_registered: route_for(
        AuthOperation.upgrade_anonymous_to_registered),
}


def operation_for_endpoint(method: str, path: str) -> AuthOperation:
    """The operation the named endpoint performs, and no other."""
    # [impl->req~users-operation-create-user-endpoint~1]
    # [impl->req~users-operation-upgrade-anonymous-endpoint~1]
    operation = users_operation(method, path)
    if ONBOARDING_ENDPOINTS[operation] != (method.upper(), path):
        raise UsersError(f"{operation} is not performed by {method} {path}")
    return operation


def assert_endpoint_uses_shared_contract(endpoint: Any) -> AuthOperation:
    """Each endpoint half of this split uses the shared operation-challenge contract: it names
    one of the two operations, and it implements the shared procedures' hooks rather than a
    prepare, completion, single-use or audit path of its own."""
    # [impl->req~users-endpoints-use-shared-challenge-contract~1]
    operation = getattr(endpoint, "operation", None)
    if not isinstance(operation, AuthOperation) or operation not in ONBOARDING_ENDPOINTS:
        raise UsersError(f"{endpoint} performs no operation of this split")
    assert_shared_challenge_contracts(operation)
    missing = [hook for hook in ("check_prepare_eligibility", "verify_proof",
                                 "confirm_live_state", "mutate")
               if not callable(getattr(endpoint, hook, None))]
    if missing:
        raise UsersError(f"{operation} does not use the shared challenge contract: {missing}")
    # A second prepare, completion, consumption or audit path would be a second contract.
    private = [own for own in ("prepare", "complete", "consume_challenge", "write_audit_row")
               if getattr(endpoint, own, None) is not None]
    if private:
        raise UsersError(f"{operation} must not carry its own {private}")
    return operation


def assert_pre_consumption_checks_first(row: ChallengeRow) -> ChallengeRow:
    """The shared pre-consumption checks — the barrier, the challenge lookup, the binding and
    operation checks, and the atomic claim — all run before any mutation rule of this split.
    A mutation rule therefore only ever sees a row this attempt already holds the claim on;
    this split adds only endpoint-specific identity resolution, promotion and audit."""
    # [impl->req~users-shared-pre-consumption-checks-first~1]
    if row.state is not ChallengeState.claimed or row.claim_attempt_id is None:
        raise UsersError("the shared pre-consumption checks run before every mutation rule")
    if row.operation not in ONBOARDING_ENDPOINTS:
        raise UsersError(f"{row.operation} is not an operation of this split")
    return row


# --- The `POST /auth/upgrade-anonymous` request contract ---------------------------------------


class AuthorizationHeaderSource(StrEnum):
    """Where the Bearer token the upgrade endpoint authenticates with came from."""
    unchanged_client_header = "unchanged_client_header"
    gateway_rewritten_header = "gateway_rewritten_header"
    gateway_jwt_filter_metadata = "gateway_jwt_filter_metadata"


# Possession of any valid token for the bound pair suffices, so no re-authentication window,
# `auth_time` bound, or other freshness requirement exists on this endpoint.
UPGRADE_TOKEN_FRESHNESS_REQUIREMENTS: frozenset[str] = frozenset()

# The completion body: the challenge handle and the declared target provider, and nothing else.
UPGRADE_REQUEST_FIELDS: frozenset[str] = frozenset({"challenge_id", "provider"})

# Attestation-key material, in every name it could arrive under.
UPGRADE_ATTESTATION_FIELDS: frozenset[str] = frozenset({
    "attestation", "attestation_key", "attestation_key_proof", "attestation_key_id",
    "app_attest_assertion", "app_attest_key_id", "assertion", "integrity_proof",
    "integrity_token", "devicecheck_token", "play_integrity_token"})

UPGRADE_RESTORE_PROOF_FIELDS: frozenset[str] = frozenset({"restore_proof"})


def upgrade_operation(method: str, path: str) -> AuthOperation:
    """`POST /auth/upgrade-anonymous` performs only `upgrade_anonymous_to_registered`."""
    # [impl->req~users-upgrade-endpoint-single-operation~1]
    operation = operation_for_endpoint(method, path)
    if operation is not AuthOperation.upgrade_anonymous_to_registered:
        raise UsersError(f"{method} {path} performs {operation}, not the anonymous upgrade")
    return operation


def upgrade_authentication(context: Any, *,
                           header: AuthorizationHeaderSource =
                           AuthorizationHeaderSource.unchanged_client_header,
                           token_age: timedelta | None = None,
                           row: ExternalIdentityRow | None = None) -> UUID:
    """The Firebase ID token arrives in the unchanged client `Authorization` header, is
    cryptographically verified by the backend's shared pre-handler barrier, and must resolve to
    an existing linked *active* identity row for the backend-verified `(issuer, subject)`.
    Possession of any valid token for that pair suffices, at any freshness."""
    # [impl->req~users-upgrade-request-token~1]
    if header is not AuthorizationHeaderSource.unchanged_client_header:
        raise UsersError(f"{header} does not authenticate the anonymous upgrade")
    if UPGRADE_TOKEN_FRESHNESS_REQUIREMENTS:
        raise UsersError("any valid token for the verified pair suffices, at any freshness")
    context_pair(context)
    identity_id = upgrade_linked_identity(context)
    if row is not None:
        if row.identity_state is not IdentityState.active:
            raise UsersError("the anonymous upgrade needs an active linked identity row")
        if row.id != identity_id:
            raise UsersError("the resolved identity row is the one the token resolves to")
    # `token_age` is accepted and deliberately not compared against anything.
    _ = token_age
    return identity_id


def upgrade_declared_provider(declared: str | None, *, phase: RequestMode,
                              row: ChallengeRow | None = None) -> IdentityProvider:
    """The client declares a target provider of `google` or `apple` on both prepare and
    completion. Prepare normalizes and binds it; completion must carry a declaration equal to
    that challenge-bound variant, so a missing or differing value is the variant mismatch and
    never something completion resolves."""
    # [impl->req~users-upgrade-request-provider-field~1]
    operation = AuthOperation.upgrade_anonymous_to_registered
    if phase is RequestMode.prepare:
        variant = normalize_variant(operation, declared)
        if variant not in REGISTERED_PROVIDERS:
            raise UsersError(f"{variant} is not an upgrade target provider")
        return variant
    if row is None or row.operation is not operation:
        raise UsersError("a completion compares its declaration against its own challenge row")
    if not variants_equal(declared, row.operation_variant):
        raise ChallengeRejection(variant_mismatch().result)
    bound = row.operation_variant
    if bound not in REGISTERED_PROVIDERS:
        raise UsersError("an upgrade challenge binds a registered target provider")
    return bound


def upgrade_challenge_source() -> str:
    """The operation challenge is the one `POST /auth/upgrade-anonymous?challenge=true`
    returned, prepared on the endpoint's own URL."""
    # [impl->req~users-upgrade-request-challenge~1]
    method, path = UPGRADE_ROUTE
    signal = classify_mode([(CHALLENGE_QUERY_PARAM, CHALLENGE_QUERY_VALUE)], None)
    if signal.mode is not RequestMode.prepare:
        raise UsersError("challenge=true on the endpoint's own URL prepares the challenge")
    return f"{method} {path}?{CHALLENGE_QUERY_PARAM}={CHALLENGE_QUERY_VALUE}"


def assert_no_attestation_key_proof(body: Mapping[str, Any] | None) -> None:
    """The upgrade request carries no attestation-key proof."""
    # [impl->req~users-upgrade-request-no-attestation-key-proof~1]
    _reject_upgrade_fields(body, UPGRADE_ATTESTATION_FIELDS, "an attestation-key proof")


def assert_no_upgrade_restore_proof(body: Mapping[str, Any] | None) -> None:
    """The upgrade request carries no `restore_proof`."""
    # [impl->req~users-upgrade-request-no-restore-proof~1]
    _reject_upgrade_fields(body, UPGRADE_RESTORE_PROOF_FIELDS, "a restore_proof")


def _reject_upgrade_fields(body: Mapping[str, Any] | None, forbidden: frozenset[str],
                           what: str) -> None:
    offending = sorted(set(body or {}) & forbidden)
    if offending:
        raise UsersError(f"POST /auth/upgrade-anonymous takes no {what}: {offending}")


def upgrade_success(row: ExternalIdentityRow, decision: UpgradeDecision, *,
                    context: Any, transaction: object,
                    backend_token: object | None = None) -> ExternalIdentityRow:
    """On success the existing identity row's provider is flipped in place to the
    Admin-confirmed declared provider and its `provider_uid` assigned on the same user; where
    the stored provider, the stored `provider_uid` and the mandatory live confirmation all
    agree with the declaration, the operation is idempotent success and mutates nothing.
    Either way the same Firebase ID token resolves as linked on the next request, and no
    backend token is issued."""
    # [impl->req~users-upgrade-success-flip-or-idempotent~1]
    if decision.provider not in REGISTERED_PROVIDERS or not decision.provider_uid:
        raise UsersError("an upgrade succeeds only onto a confirmed registered provider")
    upgraded = apply_upgrade(row, decision, transaction=transaction)
    if decision.branch is UpgradeBranch.idempotent:
        if upgraded != row:
            raise UsersError("idempotent success mutates nothing")
    else:
        if upgraded.provider is not decision.provider \
                or upgraded.provider_uid != decision.provider_uid:
            raise UsersError("the flip stores the confirmed provider and its provider_uid")
        if upgraded.user_id != row.user_id or upgraded.id != row.id:
            raise UsersError("the flip stays on the same identity row and the same user")
    # No backend token is issued, and the same verified token resolves as linked afterwards.
    if backend_token is not None:
        raise UsersError("the anonymous upgrade returns no backend token")
    assert_no_secondary_auth_state()
    if not resolves_as_linked(upgraded, context):
        raise UsersError("the upgraded identity resolves as linked on the next request")
    return upgraded
