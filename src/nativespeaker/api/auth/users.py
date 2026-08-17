"""User creation and in-place anonymous upgrade: what these two endpoints add.

`POST /auth/create-user` and `POST /auth/upgrade-anonymous` run under the shared pre-handler
barrier, the shared operation-challenge contract, the shared completion and single-use
procedures and the shared audit contract. This module holds only what the two operations add on
top of those: how a pre-auth identity is defined and promoted, where their handler admission
controls sit, and the identity constraints each phase enforces. Rules with a normative home
elsewhere — the identity row's own semantics, the challenge mechanics, the limiter entries — are
delegated to that home rather than restated here.
"""

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AuthAttempt, AuthEventResult
from nativespeaker.api.auth.barrier import (
    ResolutionOutcome,
    VerifiedIdentityContext,
    barrier_result_for,
)
from nativespeaker.api.auth.challenges import ChallengeRow, variants_equal
from nativespeaker.api.auth.external_identities import (
    BindingDivergenceError,
    ExternalIdentityRow,
    IdentityFieldSource,
    IdentityState,
    ProviderDeclarationMismatchError,
    ProviderLookupFailedError,
    ProviderSource,
    assert_declared_provider,
    assert_provider_source,
    classify_provider,
    confirm_stored_binding,
    create_account,
    identity_key,
    matches_identity,
    provider_uid_for,
    upgrade_to_registered,
)
from nativespeaker.api.auth.flow import assert_challenge_bearing
from nativespeaker.api.auth.integration import AdminCallSite, FirebaseIntegrations
from nativespeaker.api.auth.modes import (
    CHALLENGE_QUERY_PARAM,
    CHALLENGE_QUERY_VALUE,
    RequestMode,
    classify_mode,
)
from nativespeaker.api.auth.movement import (
    MovementClassification,
    MovementContext,
    movement_audit_details,
    upgrade_movement_context,
)
from nativespeaker.api.auth.operations import (
    AdmissionRejection as AdmissionRejectionKind,
)
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    is_admission_phase,
    is_challenge_bearing,
    match_operation,
    normalize_variant,
    route_for,
    supports_prepare,
)
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.routes import is_pre_auth_callable
from nativespeaker.api.auth.taxonomy import RATE_LIMITED_CLASS, ClientErrorClass, surface
from nativespeaker.api.auth.tokens import InvalidExternalJwtError
from nativespeaker.api.exceptions import ErrorCode
from nativespeaker.api.ratelimit.config import (
    CREATE_USER_SECONDARY_ENTRY,
    FIREBASE_LOOKUP_ENTRY_KEYS,
    GatewayRateLimitEntry,
    complete_entries,
    is_blocking,
    prepare_entries,
    required_entry_names,
)
from nativespeaker.api.ratelimit.keys import (
    IDENTITY_COMPONENTS,
    GatewayResolvedAddress,
    KeyComponent,
    KeyMaterial,
    LimiterLayer,
    build_key,
    canonical_client_ip_key,
    parse_key_policy,
)
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import (
    AdmissionLedger,
    BudgetVerdict,
    ExpensiveStep,
    GetUserCallSite,
    evaluate_getuser_budgets,
)
from nativespeaker.api.ratelimit.rejection import (
    AdmissionPhase,
    AdmissionRejection,
    SecurityTelemetry,
)


class UsersError(RuntimeError):
    """A `create_user` or `upgrade_anonymous_to_registered` rule was about to be broken."""


class ProviderNotConfirmedError(UsersError):
    """The live Firebase Admin classification does not confirm the client declaration. It
    carries the internal audit result; the client class it surfaces as is decided by each
    endpoint's own error-class mapping."""

    result = AuthEventResult.provider_not_linked


# --- The two endpoints ---------------------------------------------------------------------

# The state-changing auth endpoints this split covers are operation-specific: each performs
# exactly the operation the shared inventory names for its route and method, and never falls
# through to another.
# [impl->req~users-state-changing-endpoints-are-operation-specific~1]
USERS_OPERATIONS: tuple[AuthOperation, ...] = (
    # `POST /auth/create-user`
    # [impl->req~users-challenge-endpoint-create-user~1]
    AuthOperation.create_user,
    # `POST /auth/upgrade-anonymous`
    # [impl->req~users-challenge-endpoint-upgrade-anonymous~1]
    AuthOperation.upgrade_anonymous_to_registered,
)

CREATE_USER_ROUTE: tuple[str, str] = route_for(AuthOperation.create_user)
UPGRADE_ROUTE: tuple[str, str] = route_for(AuthOperation.upgrade_anonymous_to_registered)


def users_operation(method: str, path: str) -> AuthOperation:
    """The operation this split's route names, read from the shared inventory alone."""
    # [impl->req~users-state-changing-endpoints-are-operation-specific~1]
    operation = match_operation(method, path)
    if operation is None or operation not in USERS_OPERATIONS:
        raise UsersError(f"{method} {path} is no user-creation or anonymous-upgrade endpoint")
    return operation


def create_user_operation(method: str, path: str) -> AuthOperation:
    """`POST /auth/create-user` performs only `create_user`."""
    # [impl->req~users-create-user-endpoint-single-operation~1]
    operation = users_operation(method, path)
    if operation is not AuthOperation.create_user:
        raise UsersError(f"{method} {path} performs {operation}, not create_user")
    return operation


def assert_shared_challenge_contracts(operation: AuthOperation) -> AuthOperation:
    """Both endpoints use the shared operation-challenge preparation, completion, single-use and
    audit contracts; this split defines only their operation-specific constraints and identity
    mutations. Handler admission-control rejections that occur before the normal audited attempt
    path follow the shared admission-control carve-out and the shared rejection behaviour, not a
    rule of this split's own."""
    # [impl->req~users-shared-challenge-contracts-apply~1]
    # [impl->req~users-completion-shared-contracts~1]
    if operation not in USERS_OPERATIONS:
        raise UsersError(f"{operation} is not an operation of this split")
    assert_challenge_bearing(operation)
    if not is_challenge_bearing(operation) or not supports_prepare(operation):
        raise UsersError(f"{operation} uses the shared prepare and completion procedures")
    if not is_admission_phase(AdmissionRejectionKind.backend_rate_limited):
        raise UsersError("an admission rejection stays in the shared admission-control phase")
    return operation


# --- Pre-auth identities and promotion -------------------------------------------------------


class IdentityContextSource(StrEnum):
    """Where an identity context was offered from. Only the first establishes one."""
    backend_verified_id_token = "backend_verified_id_token"
    gateway_jwt_filter_metadata = "gateway_jwt_filter_metadata"
    request_header = "request_header"
    client_field = "client_field"


def identity_pair(issuer: str, subject: str, *, source: IdentityContextSource) -> tuple[str, str]:
    """Every identity context in this split is the backend-verified `(issuer, subject)` taken
    from the Firebase ID token's `iss` and `sub`, which the shared pre-handler barrier verifies
    cryptographically on every request. The gateway forwards the client's `Authorization` header
    unchanged and its JWT filter serves edge admission and rate-limit keying alone, so gateway
    metadata never establishes this pair; only the source of the pair changed, and every
    downstream rule keyed on it remains in force."""
    # [impl->req~users-identity-context-from-backend-verified-token~1]
    if source is not IdentityContextSource.backend_verified_id_token:
        raise UsersError(f"{source} does not establish the backend identity context")
    return identity_key(issuer, subject, source=IdentityFieldSource.verified_id_token)


def context_pair(context: VerifiedIdentityContext) -> tuple[str, str]:
    """The verified pair as the handlers consume it, from the barrier's typed output alone."""
    # [impl->req~users-identity-context-from-backend-verified-token~1]
    return identity_pair(context.issuer, context.subject,
                         source=IdentityContextSource.backend_verified_id_token)


# Admitting a pre-auth principal is the shared pre-handler barrier's responsibility. No
# per-endpoint step of this split takes that decision.
PREAUTH_ADMISSION_OWNER = "shared_pre_handler_barrier"


def preauth_outcome(row: ExternalIdentityRow | None) -> ResolutionOutcome:
    """A backend-verified `(issuer, subject)` that resolves to no `core.external_identities` row
    is pre-auth (unlinked). An existing `historical` row is never pre-auth: it is a permanent
    tombstone whose retained `(issuer, subject)` reservation is what keeps a retired subject out
    of pre-auth creation."""
    # [impl->req~users-preauth-identity-definition~1]
    if row is None:
        return ResolutionOutcome.pre_auth
    if row.identity_state is IdentityState.historical:
        return ResolutionOutcome.historical_identity
    return ResolutionOutcome.linked


def assert_preauth_admission_owner(site: str) -> None:
    """Admission of a pre-auth principal belongs to the shared barrier, not to a per-endpoint
    step, so no endpoint of this split may decide it."""
    # [impl->req~users-preauth-identity-definition~1]
    if site != PREAUTH_ADMISSION_OWNER:
        raise UsersError(f"{site} does not admit a pre-auth identity; the shared barrier does")


def preauth_context(context: VerifiedIdentityContext) -> tuple[str, str]:
    """The pre-auth context is the backend-verified `(issuer, subject)` and nothing else: no
    user, no identity row, and no stored provider, because none of them exists yet."""
    # [impl->req~users-preauth-context-is-verified-pair~1]
    if context.outcome is not ResolutionOutcome.pre_auth:
        raise UsersError("a pre-auth context belongs to an unlinked identity")
    if (context.user_id is not None or context.external_identity_id is not None
            or context.provider is not None):
        raise UsersError("a pre-auth context carries no user, identity row or provider")
    return context_pair(context)


# Both phases of `POST /auth/create-user` are the same URL, selected by the shared mode signal.
PREAUTH_ADMITTED_PHASES: tuple[RequestMode, ...] = (RequestMode.prepare, RequestMode.completion)


def preauth_admitted(method: str, path: str, *, phase: RequestMode | None = None) -> bool:
    """The barrier admits a pre-auth identity only to the prepare and complete phases of
    `POST /auth/create-user`, and to no other route."""
    # [impl->req~users-barrier-admits-preauth-to-create-user-only~1]
    if phase is not None and phase not in PREAUTH_ADMITTED_PHASES:
        raise UsersError(f"{phase} is not a phase of {method} {path}")
    admitted = is_pre_auth_callable(method, path)
    if admitted and (method.upper(), path) != CREATE_USER_ROUTE:
        raise UsersError(f"{method} {path} is not the pre-auth callable route")
    return admitted


# Every other route a pre-auth identity may present a token to. The barrier rejects it on all of
# them, `POST /auth/upgrade-anonymous` included.
# [impl->req~users-barrier-rejects-preauth-elsewhere~1]
PREAUTH_REJECTED_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/auth/sync"),
    ("POST", "/auth/claim-anonymous-grant"),
    ("POST", "/auth/restore-subscription"),
    ("POST", "/auth/upgrade-anonymous"),
    ("GET", "/users/me"),
    ("GET", "/chats"),
    ("POST", "/chats"),
    ("GET", "/users/me/quota"),
    ("POST", "/auth/sign-out-all"),
)


def preauth_rejection(method: str, path: str) -> tuple[AuthEventResult, ErrorCode]:
    """What a pre-auth identity receives anywhere but `create-user`: the barrier's own
    `preauth_identity_not_allowed`, surfaced through the client class of the same name."""
    # [impl->req~users-barrier-rejects-preauth-elsewhere~1]
    if preauth_admitted(method, path):
        raise UsersError(f"{method} {path} admits a pre-auth identity")
    result = barrier_result_for(ResolutionOutcome.pre_auth, method, path)
    if result is not AuthEventResult.preauth_identity_not_allowed:
        raise UsersError(f"{method} {path} does not reject a pre-auth identity")
    client_class, _status = surface(result)
    if client_class != ClientErrorClass.preauth_identity_not_allowed:
        raise UsersError("a pre-auth rejection surfaces as preauth_identity_not_allowed")
    return result, client_class


# The two account states that are unavailable everywhere, each keeping its own internal result.
UNAVAILABLE_ACCOUNT_RESULTS: dict[ResolutionOutcome, AuthEventResult] = {
    ResolutionOutcome.historical_identity: AuthEventResult.historical_identity,
    ResolutionOutcome.blocked_user: AuthEventResult.blocked_user,
}


def unavailable_account(outcome: ResolutionOutcome, method: str,
                        path: str) -> tuple[AuthEventResult, ErrorCode]:
    """An existing `historical` identity is never treated as pre-auth. The shared barrier rejects
    historical identities and identities linked to blocked users on every route, both phases of
    `POST /auth/create-user` included, with the shared `account_unavailable` client class, while
    the two states retain distinct internal audit results."""
    # [impl->req~users-historical-and-blocked-account-unavailable~1]
    expected = UNAVAILABLE_ACCOUNT_RESULTS.get(outcome)
    if expected is None:
        raise UsersError(f"{outcome} is not an unavailable-account state")
    result = barrier_result_for(outcome, method, path)
    if result is not expected:
        raise UsersError(f"{outcome} is rejected as {expected} on {method} {path}")
    client_class, _status = surface(result)
    if client_class != ClientErrorClass.account_unavailable:
        raise UsersError("both states surface as the shared account_unavailable class")
    return result, client_class


def upgrade_linked_identity(context: VerifiedIdentityContext) -> UUID:
    """`POST /auth/upgrade-anonymous` is not a pre-auth endpoint: it operates on the existing
    linked identity row for the backend-verified `(issuer, subject)` after same-Firebase-UID
    account linking."""
    # [impl->req~users-upgrade-anonymous-not-preauth-endpoint~1]
    if preauth_admitted(*UPGRADE_ROUTE):
        raise UsersError("upgrade-anonymous is not a pre-auth callable route")
    if context.outcome is not ResolutionOutcome.linked or context.external_identity_id is None:
        raise UsersError("upgrade-anonymous requires an existing linked identity row")
    return context.external_identity_id


def upgrade_target_provider(declared: IdentityProvider,
                            provider_data: Sequence[object]) -> IdentityProvider:
    """The target registered provider is established server-side, through Firebase Admin
    `providerData` verification of the client-declared provider, and is never read from the
    token.

    `upgrade-anonymous` completion requires the same successful lookup and the same classifier
    agreement with the declaration as registered creation does — the idempotent repeat, where the
    stored provider already equals the declaration, included: the agreement is checked through the
    shared declaration-match stage on every branch."""
    # [impl->req~users-upgrade-anonymous-not-preauth-endpoint~1]
    # [impl->req~sessions-declaration-upgrade-anonymous~1]
    assert_provider_source(ProviderSource.firebase_admin_provider_data)
    confirmed = classify_provider(provider_data)
    try:
        assert_declared_provider(confirmed, declared)
    except ProviderDeclarationMismatchError as mismatch:
        raise ProviderNotConfirmedError(
            f"the live lookup confirms {confirmed}, not {declared}") from mismatch
    return confirmed


# --- What a successful `create_user` owes ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateUserOutcome:
    """The backend state a successful `POST /auth/create-user` returns, and no token with it."""
    user_id: UUID
    identity: ExternalIdentityRow
    transaction: object
    backend_token: None = None


# There is no secondary backend auth state to update and no generation counter to advance.
SECONDARY_AUTH_STATE: frozenset[str] = frozenset()


def assert_no_secondary_auth_state(state: Mapping[str, Any] | None = None, *,
                                   generation: int | None = None) -> None:
    """No secondary backend auth state and no generation exist, so the same Firebase ID token
    resolves as linked on the next request purely by being verified again."""
    # [impl->req~users-no-secondary-auth-state-or-generation~1]
    if SECONDARY_AUTH_STATE or state or generation is not None:
        raise UsersError("no secondary backend auth state or generation exists to advance")


def complete_create_user(*, user_id: UUID, identity: ExternalIdentityRow,
                         completion_transaction: object, identity_transaction: object,
                         backend_token: object | None = None,
                         secondary_auth_state: Mapping[str, Any] | None = None,
                         grant_writes: Iterable[str] = ()) -> CreateUserOutcome:
    """The obligations a `create_user` success from a pre-auth identity owes."""
    # The corresponding `core.external_identities` row is created as `create_user` defines it,
    # [impl->req~users-create-user-success-obligations~1]
    # [impl->req~users-create-user-creates-identity-row~1]
    # inside the completion transaction, together with the `core.users` row, so a failure of
    # either insert rolls the whole transaction back and no account exists.
    # [impl->req~users-identity-row-in-completion-transaction~1]
    # [impl->req~users-account-and-identity-row-atomic~1]
    if identity_transaction is not completion_transaction:
        raise UsersError("the identity row is created inside the completion transaction")
    creation = create_account(user_id=user_id, identity=identity,
                              user_transaction=completion_transaction,
                              identity_transaction=identity_transaction)
    # The response carries the resulting backend state, with no backend token in it.
    # [impl->req~users-create-user-returns-no-backend-token~1]
    if backend_token is not None:
        raise UsersError("create_user returns no backend token")
    assert_no_secondary_auth_state(secondary_auth_state)
    assert_no_free_credits(grant_writes)
    return CreateUserOutcome(user_id=user_id, identity=creation.identity,
                             transaction=creation.transaction)


def resolves_as_linked(identity: ExternalIdentityRow,
                       context: VerifiedIdentityContext) -> bool:
    """On success the backend has linked the external identity, so after the shared barrier
    verifies the same Firebase ID token again it resolves as linked on the next request; no
    backend token was issued and none is needed."""
    # [impl->req~users-create-user-success-links-identity~1]
    # [impl->req~users-no-secondary-auth-state-or-generation~1]
    assert_no_secondary_auth_state()
    return (matches_identity(identity, *context_pair(context))
            and identity.identity_state is IdentityState.active)


# --- The challenge-bound provider variant -------------------------------------------------------


def prepare_variant(operation: AuthOperation, declared: str | None) -> IdentityProvider:
    """Both operations have a challenge-bound provider variant. Prepare normalizes the client
    declaration once — for `create_user` to `anonymous`, `google` or `apple`, defaulting to
    `anonymous`; for `upgrade_anonymous_to_registered` to the declared `google` or `apple`
    target — and that exact value is what the challenge persists as its `operation_variant`."""
    # [impl->req~users-challenge-bound-provider-variant~1]
    # [impl->req~users-create-user-request-provider-field~1]
    assert_shared_challenge_contracts(operation)
    variant = normalize_variant(operation, declared)
    if variant is None:
        raise UsersError(f"{operation} binds a provider variant at prepare")
    return variant


def completion_variant_matches(row: ChallengeRow, declared: str | None) -> bool:
    """Completion carries the same declaration in its `provider` field, and the backend compares
    it byte-equal against the stored variant — no re-normalization, no defaulting, no other
    interpretation — before any Firebase Admin lookup or mutation."""
    # [impl->req~users-challenge-bound-provider-variant~1]
    # [impl->req~users-create-user-request-provider-field~1]
    if row.operation not in USERS_OPERATIONS:
        raise UsersError(f"{row.operation} is not an operation of this split")
    return variants_equal(declared, row.operation_variant)


@dataclass(frozen=True, slots=True)
class VariantMismatch:
    """What a declaration that differs from the challenge-bound variant produces."""
    result: AuthEventResult
    client_class: ErrorCode
    consumes_challenge: bool = True


def variant_mismatch() -> VariantMismatch:
    """A mismatch is rejected as `challenge_operation_mismatch`, surfaced as `challenge_required`
    and consumes the claimed challenge under the shared completion contract, so the client must
    prepare a fresh one: an anonymous creation challenge cannot complete registered creation, and
    neither operation may change providers after prepare."""
    # [impl->req~users-challenge-bound-provider-variant~1]
    result = AuthEventResult.challenge_operation_mismatch
    client_class, _status = surface(result)
    if client_class != ClientErrorClass.challenge_required:
        raise UsersError("a variant mismatch surfaces as challenge_required")
    return VariantMismatch(result=result, client_class=client_class)


# --- Handler admission control ------------------------------------------------------------------

# Every configured admission control these two endpoints enforce. Each name is a named entry of
# `08-rate-limits-and-admission-control.md`, which owns its key policy, rejection behaviour and
# recommended values; this split adds only their endpoint-local placement.
USERS_ADMISSION_ENTRIES: tuple[str, ...] = (
    "create_user_prepare",
    "upgrade_anonymous_prepare",
    "create_user",
    "create_user_firebase_identity_lookup",
    "create_user_firebase_identity_lookup_ip",
    "upgrade_anonymous_to_registered_firebase_identity_lookup",
)


def assert_admission_entries_named_in_08(names: Sequence[str] = USERS_ADMISSION_ENTRIES) -> None:
    """The shared Envoy limits do not cover the handler-specific placement and ordering these
    endpoints need, so the backend additionally enforces the configured per-operation admission
    controls inside the completion handlers. This split introduces no configured key or limit
    that lacks a matching named entry in `08`."""
    # [impl->req~users-handler-admission-controls-required~1]
    declared = set(required_entry_names())
    unknown = sorted(name for name in names if name not in declared)
    if unknown:
        raise UsersError(f"{unknown} have no named entry in 08")


def prepare_admission(ledger: AdmissionLedger, operation: AuthOperation,
                      policies: Mapping[str, Sequence[KeyComponent]], *,
                      allowed: bool = True) -> tuple[str, ...]:
    """For the prepare phases of `POST /auth/create-user?challenge=true` and
    `POST /auth/upgrade-anonymous?challenge=true`, the configured per-operation prepare limit is
    enforced after the shared barrier has cryptographically verified the Firebase ID token and
    resolved the identity context, and before the backend issues or persists a challenge. The
    `create_user_prepare` and `upgrade_anonymous_prepare` entries in `08` own their names, key
    policies and values."""
    # [impl->req~users-per-operation-prepare-limit~1]
    assert_shared_challenge_contracts(operation)
    if not ledger.jwt_verified:
        raise UsersError("the prepare limit runs after the barrier verified the token")
    if ledger.challenge_issued:
        raise UsersError("the prepare limit runs before a challenge is issued or persisted")
    names = prepare_entries(operation)
    for name in names:
        ledger.evaluate(name, policies[name], allowed=allowed)
    return names


def completion_admission(ledger: AdmissionLedger, operation: AuthOperation, *,
                         address: GatewayResolvedAddress | None,
                         ipv6_prefix: int = 64,
                         allowed: bool = True) -> str | None:
    """The completion phase of `POST /auth/create-user` enforces the configured per-operation
    completion limit defined by the `create_user` entry in `08`, which keys it on the canonical
    client IP. `POST /auth/upgrade-anonymous` completion has no backend per-operation entry: its
    authoritative per-subject bound is the standalone gateway limit, and this split adds no
    backend counter behind it.

    The client-IP counter is enforced at request receipt, as soon as the route and the resolved
    client address are known — before the `Authorization` JWT is decoded, before any Firebase
    Admin call, and before any database write. The address is the one the gateway resolved
    through its explicitly configured trusted-proxy chain, never a client-supplied forwarding
    header, and a request whose address could not be resolved is keyed into the one shared
    unresolved-address bucket at the single-address ceiling."""
    # [impl->req~users-per-operation-completion-limit~1]
    # [impl->req~users-completion-client-ip-counter-at-receipt~1]
    assert_shared_challenge_contracts(operation)
    names = complete_entries(operation)
    if operation is AuthOperation.upgrade_anonymous_to_registered:
        # Its authoritative per-subject bound is the standalone gateway limit, and this split
        # adds no backend counter behind it.
        if names:
            raise UsersError("upgrade completion has no backend per-operation entry")
        return None
    if names != ("create_user",):
        raise UsersError("create_user completion is bounded by the create_user entry")
    if ledger.jwt_verified:
        raise UsersError("the client-IP counter is charged at request receipt, before the JWT")
    if ledger.expensive_steps:
        raise UsersError("the client-IP counter precedes every Firebase call and database write")
    key = canonical_client_ip_key(address, ipv6_prefix=ipv6_prefix)
    ledger.evaluate(names[0], (KeyComponent.ip,), allowed=allowed)
    return key


def barrier_verification_next(ledger: AdmissionLedger, *, request_shape_valid: bool,
                              identity_source: IdentityContextSource) -> None:
    """Cheap request-shape validation and the shared pre-handler barrier's own cryptographic
    verification of the passed-through `Authorization` JWT run next; the backend never takes
    identity from a request header."""
    # [impl->req~users-request-shape-and-barrier-verification-next~1]
    if "create_user" not in ledger.evaluated:
        raise UsersError("the client-IP counter is charged before request-shape validation")
    if not request_shape_valid:
        raise UsersError("a malformed request is rejected before the barrier verifies the token")
    if identity_source is not IdentityContextSource.backend_verified_id_token:
        raise UsersError("the backend never takes identity from a request header")
    ledger.verify_jwt()


def lookup_admission(ledger: AdmissionLedger, site: GetUserCallSite, *,
                     test: Callable[[str], bool],
                     charge: Callable[[Sequence[str]], None]) -> BudgetVerdict:
    """The deployment-wide `create_user_firebase_identity_lookup` counter and its paired
    client-IP counter are charged before the mandatory Firebase Admin lookup, and therefore
    before any database mutation or other costly completion work."""
    # [impl->req~users-firebase-identity-lookup-counters-before-lookup~1]
    verdict = evaluate_getuser_budgets(site, test=test, charge=charge)
    if not verdict.allowed:
        return verdict
    for name in verdict.charged:
        if name in FIREBASE_LOOKUP_ENTRY_KEYS:
            ledger.evaluate(name, FIREBASE_LOOKUP_ENTRY_KEYS[name])
    ledger.expensive_step(ExpensiveStep.firebase_lookup)
    return verdict


def secondary_subject_entry(ledger: AdmissionLedger, *, allowed: bool = True) -> str:
    """The optional `issuer+subject_hash` secondary entry, where configured, is evaluated only
    after the barrier's verification has succeeded. It is non-blocking, is never fused with a
    client-IP counter into a composite key, and never substitutes for one."""
    # [impl->req~users-optional-subject-hash-secondary-entry~1]
    if not ledger.jwt_verified:
        raise UsersError("the secondary entry is evaluated only after verification succeeded")
    if "create_user" not in ledger.evaluated:
        raise UsersError("the secondary entry never substitutes for the client-IP counter")
    if is_blocking(CREATE_USER_SECONDARY_ENTRY):
        raise UsersError("the secondary entry is non-blocking")
    policy = (KeyComponent.issuer, KeyComponent.subject_hash)
    if KeyComponent.ip in policy:
        raise UsersError("the secondary entry is never fused with a client-IP counter")
    ledger.evaluate(CREATE_USER_SECONDARY_ENTRY, policy, allowed=allowed)
    if ledger.refused:
        raise UsersError("the non-blocking secondary entry never refuses a request")
    return CREATE_USER_SECONDARY_ENTRY


# The two counters that stand alone: the deployment-wide lookup counter and every client-IP
# counter on the route, each keyed on exactly one component.
UNFUSED_COUNTER_POLICIES: dict[str, tuple[KeyComponent, ...]] = {
    "create_user": (KeyComponent.ip,),
    "create_user_prepare": (KeyComponent.ip,),
    "create_user_firebase_identity_lookup": (KeyComponent.deployment,),
    "create_user_firebase_identity_lookup_ip": (KeyComponent.ip,),
}


def assert_counters_not_fused(policies: Mapping[str, Sequence[KeyComponent]]) -> None:
    """Neither the client-IP counter nor the deployment-wide counter is ever fused into a
    composite key or deferred to wait for an issuer or subject value."""
    # [impl->req~users-counters-never-fused-or-deferred~1]
    for name, expected in UNFUSED_COUNTER_POLICIES.items():
        policy = tuple(policies.get(name, expected))
        if policy != expected:
            raise UsersError(f"{name} keys on {'+'.join(expected)} alone")
        if any(component in IDENTITY_COMPONENTS for component in policy):
            raise UsersError(f"{name} would be deferred to wait for an issuer or subject value")


# --- The gateway limits on these routes ----------------------------------------------------------

# The standalone per-linked-subject gateway limit on the upgrade route: keyed per linked subject,
# defaulting to 3 requests per hour, and configuration-tunable.
UPGRADE_GATEWAY_KEY_POLICY: tuple[KeyComponent, ...] = (KeyComponent.issuer,
                                                        KeyComponent.subject_hash)
UPGRADE_GATEWAY_DEFAULT_LIMIT = "3/hour"
GATEWAY_JWT_VERIFICATION = "envoy_jwt_verification"


def assert_upgrade_gateway_limit(entry: GatewayRateLimitEntry) -> None:
    """`POST /auth/upgrade-anonymous` must also carry a load-bearing gateway rate limit keyed per
    linked subject as `issuer+subject_hash`. It is a standalone value, never defined by reference
    to another endpoint's quota, and it bounds the endpoint's outbound Firebase Admin fan-out;
    `08-rate-limits-and-admission-control.md` remains the source of truth for the configured
    entry."""
    # [impl->req~users-standalone-gateway-upgrade-limit~1]
    method, path = UPGRADE_ROUTE
    if entry.route != f"{method} {path}":
        raise UsersError(f"the standalone limit is the one on {method} {path}")
    if parse_key_policy(entry.key) != UPGRADE_GATEWAY_KEY_POLICY:
        raise UsersError("the standalone limit is keyed per linked subject as issuer+subject_hash")
    if complete_entries(AuthOperation.upgrade_anonymous_to_registered):
        raise UsersError("the standalone limit stands alone: no backend counter sits behind it")


def upgrade_gateway_admission(ledger: AdmissionLedger, *, jwt_filter_verified: bool,
                              allowed: bool = True) -> None:
    """The standalone limit runs before the endpoint's Firebase Admin call; an over-limit request
    receives the normal rate-limit response and never reaches Firebase."""
    # [impl->req~users-standalone-gateway-upgrade-limit~1]
    if not jwt_filter_verified:
        raise UsersError("an identity-keyed gateway limit evaluates after JWT-filter verification")
    if ledger.expensive_steps:
        raise UsersError("the standalone limit runs before the endpoint's Firebase Admin call")
    if not allowed:
        ledger.refused = True


def gateway_limit_key(entry: GatewayRateLimitEntry, material: KeyMaterial) -> str:
    """Every identity-keyed gateway limit on these routes, the standalone one included, derives
    its key only from token metadata Envoy's JWT filter verified for edge admission and
    rate-limit keying, and evaluates only after that route's gateway JWT-filter verification. It
    never supplies the backend identity context, which the shared backend barrier establishes
    independently from the unchanged `Authorization` header. IP-keyed limits need no verified
    identity and may run at any position."""
    # [impl->req~users-identity-keyed-gateway-limit-keying~1]
    policy = parse_key_policy(entry.key)
    if any(component in IDENTITY_COMPONENTS for component in policy):
        if entry.evaluate_after != GATEWAY_JWT_VERIFICATION:
            raise UsersError("an identity-keyed gateway limit evaluates after JWT verification")
    return build_key(policy, material, layer=LimiterLayer.gateway)


# --- The mandatory Firebase Admin lookup ----------------------------------------------------------

# One attempt plus at most two additional retries inside the same logical read.
FIREBASE_LOOKUP_ATTEMPTS = 3


def issuer_selected_admin_client(integrations: FirebaseIntegrations, issuer: str) -> Any:
    """Every Firebase Admin lookup in this split executes through the Admin client of the single
    configured Firebase integration selected by matching the request's backend-verified issuer.
    No default or ambient Admin client exists. An issuer mismatch cannot reach this stage — the
    shared barrier rejects it as `invalid_external_jwt` — and a matched integration whose Admin
    client is unavailable, misconfigured or otherwise unselectable fails closed as
    `firebase_lookup_unavailable`, surfaced as `verification_temporarily_unavailable`.

    This is a request-driven Admin call site: the issuer it selects on is the one verified for the
    current request, the same issuer that passed external-JWT acceptance and keys the identity
    lookup. It is never derived from `subject`, from the provider, or from client input."""
    # [impl->req~users-issuer-selected-admin-client~1]
    # [impl->req~sessions-admin-client-by-issuer-match~1]
    # [impl->req~sessions-integration-select-request-driven~1]
    # [impl->req~sessions-integration-selection-fails-closed~1]
    try:
        client = integrations.admin_client_for_request(verified_issuer=issuer,
                                                      site=AdminCallSite.provider_data_read)
    except InvalidExternalJwtError:
        raise
    except Exception as cause:
        raise lookup_unavailable() from cause
    if client is None:
        raise lookup_unavailable()
    return client


def lookup_unavailable() -> ProviderLookupFailedError:
    """The fail-closed lookup failure: audited as `firebase_lookup_unavailable` and surfaced as
    `verification_temporarily_unavailable`."""
    # [impl->req~users-issuer-selected-admin-client~1]
    result = AuthEventResult.firebase_lookup_unavailable
    client_class = ClientErrorClass(surface(result)[0])
    if client_class is not ClientErrorClass.verification_temporarily_unavailable:
        raise UsersError("a lookup failure surfaces as verification_temporarily_unavailable")
    return ProviderLookupFailedError(result, client_class, retryable=True)


async def firebase_identity_lookup(lookup: Callable[[], Awaitable[Any]], *,
                                   ledger: AdmissionLedger | None = None,
                                   admit: Callable[[], BudgetVerdict] | None = None,
                                   attempts: int = FIREBASE_LOOKUP_ATTEMPTS) -> Any:
    """Every `create_user` completion, anonymous or registered, and every
    `upgrade_anonymous_to_registered` completion performs one mandatory Firebase Admin lookup
    operation, so the configured Firebase-lookup admission check runs before `getUser(subject)`
    and the lookup runs before the write transaction. After admission passes, all lookup paths
    reuse the existing failure machinery: a retryable Firebase Admin outage, a malformed or
    indeterminate response and a backend integration-authentication failure are retried within
    that same logical read up to two additional times, three attempts in all; a non-retryable
    cause rejects immediately and consumes no retry budget.

    `admit` is the applicable budgets' joint gate. It runs immediately before every outbound
    attempt — including before each permitted retry — because the budgets meter calls actually
    issued, not logical reads: without that, one admitted request could fan three calls out
    against one unit during a Firebase outage.
    """
    # [impl->req~users-firebase-lookup-admission-and-retry~1]
    # [impl->req~ratelimit-getuser-budget-evaluation-order~1]
    if ledger is not None:
        if ExpensiveStep.firebase_lookup not in ledger.expensive_steps:
            raise UsersError("the Firebase-lookup admission check runs before getUser")
        if ExpensiveStep.database_mutation in ledger.expensive_steps:
            raise UsersError("the lookup runs before the write transaction")
    remaining = attempts
    while True:
        remaining -= 1
        if admit is not None and not admit().allowed:
            # An exhausted budget refuses the attempt the same way an exhausted lookup does.
            # [impl->req~ratelimit-firebase-budget-exhaustion-class~1]
            raise lookup_unavailable()
        try:
            return await lookup()
        except ProviderLookupFailedError as failure:
            if not failure.retryable or remaining <= 0:
                raise


# --- Admission rejection behaviour ------------------------------------------------------------------


def admission_phase_rejection(attempt: AuthAttempt, telemetry: SecurityTelemetry,
                              decision: LimitDecision,
                              *more: LimitDecision) -> AdmissionRejection:
    """Admission-control rejections that happen before the endpoint enters its normal audited
    attempt path use the shared rejection behaviour defined in `08` and are outside the
    state-changing audit attempt path. Requests turned away that way follow the shared
    admission-control carve-out: they create no state-changing audit row."""
    # [impl->req~users-admission-rejection-behavior~1]
    # [impl->req~users-admission-rejections-no-audit-row~1]
    if not is_admission_phase(AdmissionRejectionKind.backend_rate_limited):
        raise UsersError("an admission rejection belongs to the admission phase")
    # An over-limit `create_user` names the shared registration class; every other operation
    # takes the generic admission class. Neither is ever `quota_exceeded`, which is monthly
    # entitlement quota and a different condition entirely.
    # [impl->req~shared-registration-temporarily-unavailable-remediation~1]
    client_class = (ClientErrorClass.registration_temporarily_unavailable
                    if attempt.operation is AuthOperation.create_user else RATE_LIMITED_CLASS)
    rejection = AdmissionPhase(attempt, telemetry).reject(decision, *more,
                                                          client_class=client_class)
    if rejection.audit_rows or rejection.database_rows or attempt.audited:
        raise UsersError("an admission rejection creates no state-changing audit row")
    return rejection


# --- The upgrade's account-movement audit context ------------------------------------------------------


def upgrade_audit_context(*, result: AuthEventResult, occurred_at: datetime,
                          user_id: UUID | None, external_identity_id: UUID | None,
                          challenge_row_id: UUID | None = None) -> MovementContext:
    """`POST /auth/upgrade-anonymous` records its movement context inside the single
    `audit.auth_events` row for each attempt and writes no second durable row for the same
    attempt. That context is the source and destination identity context for the same identity
    row before and after the in-place provider flip or the idempotent no-op decision, the
    resolved user where known, the non-secret server-side challenge row ID, the result, and the
    movement classification `upgrade`. The public `challenge_id` capability handle is never
    written to audit or logs."""
    # [impl->req~users-upgrade-movement-audit-context~1]
    context = upgrade_movement_context(result=result,
                                       occurred_at=occurred_at,
                                       user_id=user_id,
                                       external_identity_id=external_identity_id,
                                       challenge_row_id=challenge_row_id)
    if context.classification is not MovementClassification.upgrade:
        raise UsersError("an upgrade attempt classifies its movement as upgrade")
    if context.source_external_identity_id != context.destination_external_identity_id:
        raise UsersError("the upgrade's movement context is the same identity row on both sides")
    # `movement_audit_details` fails closed on a missing minimum field and on the public handle.
    movement_audit_details(context)
    return context


# --- Operation-specific identity constraints ------------------------------------------------------------


def create_user_prepare_constraints(context: VerifiedIdentityContext,
                                    declared: str | None) -> IdentityProvider:
    """`create_user` requires a pre-auth identity for the backend-verified `(issuer, subject)`
    and accepts a client-declared provider, defaulting to `anonymous`, validated against the
    identity-provider enum and bound as the challenge's exact operation variant at prepare.
    Prepare performs a best-effort fail-fast linked-identity check and issues no challenge when
    that check finds one; that rejection is the `identity_already_linked` conflict class and
    audit result, never `preauth_identity_not_allowed` and never idempotent success. Historical
    identities and identities linked to blocked users are rejected by the shared barrier as
    `account_unavailable` before either phase."""
    # [impl->req~users-create-user-identity-constraints~1]
    _assert_create_user_admissible(context.outcome)
    preauth_context(context)
    return prepare_variant(AuthOperation.create_user, declared)


def create_user_completion_constraints(context: VerifiedIdentityContext, row: ChallengeRow,
                                       declared: str | None, *,
                                       live: ResolutionOutcome) -> IdentityProvider:
    """Completion re-resolves the identity authoritatively inside the completion/consumption
    transaction: prepare-time pre-auth status never suffices, and an identity found active there
    takes the same `identity_already_linked` conflict. The `provider` field is required at
    completion and must equal the challenge-bound variant byte-for-byte."""
    # [impl->req~users-create-user-identity-constraints~1]
    _assert_create_user_admissible(context.outcome)
    # The shared completion order is normative and a rejection names the earliest failed step:
    # step 09 compares the variant, before the step 10 Firebase Admin lookup and the step 11
    # re-resolution `live` can only be known after.
    # [impl->req~shared-completion-rejection-precedence~1]
    # [impl->req~users-challenge-bound-provider-variant~1]
    if not completion_variant_matches(row, declared):
        raise ChallengeRejection(variant_mismatch().result)
    _assert_create_user_admissible(live)
    variant = row.operation_variant
    if variant is None:
        raise UsersError("a create_user challenge binds its normalized provider variant")
    return variant


def _assert_create_user_admissible(outcome: ResolutionOutcome) -> None:
    """The one place both phases judge a resolved outcome, so the two can never drift."""
    # [impl->req~users-create-user-identity-constraints~1]
    method, path = CREATE_USER_ROUTE
    if outcome in UNAVAILABLE_ACCOUNT_RESULTS:
        result, _client_class = unavailable_account(outcome, method, path)
        raise ChallengeRejection(result)
    if outcome is ResolutionOutcome.linked:
        # Never `preauth_identity_not_allowed`, and never idempotent success.
        raise ChallengeRejection(AuthEventResult.identity_already_linked)
    if outcome is not ResolutionOutcome.pre_auth:
        raise UsersError(f"{outcome} is no resolution outcome create_user admits")


class UpgradeBranch(StrEnum):
    """Which branch an admitted `upgrade_anonymous_to_registered` completion takes."""
    mutable = "mutable"
    idempotent = "idempotent"


@dataclass(frozen=True, slots=True)
class UpgradeDecision:
    """The branch, and the confirmed registered binding it commits or re-confirms."""
    branch: UpgradeBranch
    provider: IdentityProvider
    provider_uid: str


def upgrade_prepare_constraints(context: VerifiedIdentityContext,
                                declared: str | None) -> IdentityProvider:
    """`upgrade_anonymous_to_registered` requires an existing linked active identity row for the
    backend-verified `(issuer, subject)`, and its declared target provider is bound as the
    challenge's exact operation variant at prepare. It does not operate on a pre-auth identity."""
    # [impl->req~users-upgrade-identity-constraints~1]
    upgrade_linked_identity(context)
    return prepare_variant(AuthOperation.upgrade_anonymous_to_registered, declared)


def upgrade_completion_decision(row: ExternalIdentityRow, declared: IdentityProvider, *,
                                provider_data: Sequence[Mapping[str, object]]) -> UpgradeDecision:
    """The target provider is established by the live server-side Firebase Admin lookup on this
    same call. The mutable path requires the stored provider to be `anonymous`. Idempotent
    success requires all of: the stored provider equals the declared registered provider, the
    live lookup confirms that provider, and the matching live `providerData.uid` equals the
    immutable stored `provider_uid`. A stored registered binding that differs from the declared,
    live-confirmed one — a different provider, or a different live provider UID — is rejected
    with the distinct `provider_transition_not_allowed` conflict, and the stored provider and
    `provider_uid` remain unchanged."""
    # [impl->req~users-upgrade-identity-constraints~1]
    if row.identity_state is not IdentityState.active:
        raise ChallengeRejection(AuthEventResult.historical_identity)
    if row.provider is not IdentityProvider.anonymous:
        # A stored registered binding is confirmed against the live one and never rewritten.
        # Every divergence on this branch — a different declared provider, a live classification
        # that does not confirm the declaration, or a different live provider UID — is the one
        # distinct `provider_transition_not_allowed` conflict, never `provider_not_linked`.
        if row.provider is not declared:
            raise ChallengeRejection(AuthEventResult.provider_transition_not_allowed)
        try:
            confirmed = upgrade_target_provider(declared, list(provider_data))
        except ProviderNotConfirmedError:
            raise ChallengeRejection(
                AuthEventResult.provider_transition_not_allowed) from None
        live_uid = provider_uid_for(confirmed, provider_data)
        if not live_uid:
            raise lookup_unavailable()
        try:
            confirm_stored_binding(row, live_provider=confirmed, live_provider_uid=live_uid)
        except BindingDivergenceError as divergence:
            raise ChallengeRejection(divergence.result) from None
        return UpgradeDecision(UpgradeBranch.idempotent, row.provider, live_uid)
    # The mutable path: a stored `anonymous` binding, where an unconfirming live classification
    # is the ordinary `provider_not_linked` rejection.
    confirmed = upgrade_target_provider(declared, list(provider_data))
    live_uid = provider_uid_for(confirmed, provider_data)
    if not live_uid:
        raise lookup_unavailable()
    return UpgradeDecision(UpgradeBranch.mutable, confirmed, live_uid)


def apply_upgrade(row: ExternalIdentityRow, decision: UpgradeDecision, *,
                  transaction: object) -> ExternalIdentityRow:
    """The mutable branch flips the existing row's provider in place and assigns its
    `provider_uid`; the idempotent branch mutates nothing."""
    # [impl->req~users-upgrade-identity-constraints~1]
    # [impl->req~users-upgrade-flips-provider-in-place~1]
    if decision.branch is UpgradeBranch.idempotent:
        return row
    return upgrade_to_registered(row, provider=decision.provider,
                                 provider_uid=decision.provider_uid, transaction=transaction)


# The internal results this split's rules produce. Each surfaces through a shared client class,
# and each is more specific than the class it surfaces as.
USERS_INTERNAL_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.invalid_external_jwt,
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.historical_identity,
    AuthEventResult.blocked_user,
    AuthEventResult.identity_already_linked,
    AuthEventResult.challenge_operation_mismatch,
    AuthEventResult.provider_transition_not_allowed,
    AuthEventResult.provider_account_already_linked,
    AuthEventResult.firebase_user_unresolved,
    AuthEventResult.firebase_lookup_unavailable,
})


def client_class_for(result: AuthEventResult) -> ErrorCode:
    """`POST /auth/create-user` and `POST /auth/upgrade-anonymous` surface rejections through the
    shared client-error taxonomy and must not expose `core.auth_event_result` values directly.
    Each rejected attempt that reaches the audited attempt path still audits the specific
    internal result, and the audited value is never less specific than the class returned."""
    # [impl->req~users-client-error-taxonomy-not-internal-results~1]
    if result not in USERS_INTERNAL_RESULTS:
        raise UsersError(f"{result} is not an internal result of these endpoints")
    client_class, _status = surface(result)
    return client_class


# --- The `POST /auth/create-user` request ----------------------------------------------------------

# The completion body: the challenge handle and the declared provider, and nothing else.
CREATE_USER_REQUEST_FIELDS: frozenset[str] = frozenset({"challenge_id", "provider"})

# Proof for a prior anonymous identity, in every name it could arrive under.
ANONYMOUS_PROOF_FIELDS: frozenset[str] = frozenset({
    "anonymous_proof", "prior_anonymous_identity", "source_anonymous_identity",
    "anonymous_subject", "anonymous_id_token", "anonymous_refresh_token"})

# Attestation and integrity material.
ATTESTATION_FIELDS: frozenset[str] = frozenset({
    "attestation", "attestation_key", "attestation_key_proof", "integrity_proof",
    "integrity_token", "device_token", "devicecheck_token", "play_integrity_token",
    "app_attest_assertion", "assertion"})

RESTORE_PROOF_FIELDS: frozenset[str] = frozenset({"restore_proof"})


def create_user_authentication(context: VerifiedIdentityContext, *,
                               token_provider: str | None = None) -> tuple[str, str]:
    """The Firebase ID token arrives in the unchanged client `Authorization` header, is
    cryptographically verified by the backend's shared pre-handler barrier, and resolves to a
    pre-auth identity for the verified `iss`/`sub` pair, with no dependency on a token-presented
    provider."""
    # [impl->req~users-create-user-request-token~1]
    if token_provider is not None:
        raise UsersError("create_user depends on no token-presented provider")
    return preauth_context(context)


def create_user_challenge_source() -> str:
    """The operation challenge is the one returned by `POST /auth/create-user?challenge=true`."""
    # [impl->req~users-create-user-request-challenge~1]
    method, path = CREATE_USER_ROUTE
    signal = classify_mode([(CHALLENGE_QUERY_PARAM, CHALLENGE_QUERY_VALUE)], None)
    if signal.mode is not RequestMode.prepare:
        raise UsersError("challenge=true on the endpoint's own URL prepares the challenge")
    return f"{method} {path}?{CHALLENGE_QUERY_PARAM}={CHALLENGE_QUERY_VALUE}"


def assert_no_anonymous_proof(body: Mapping[str, Any] | None) -> None:
    """The request carries no proof for any prior anonymous identity."""
    # [impl->req~users-create-user-request-no-anonymous-proof~1]
    _reject_fields(body, ANONYMOUS_PROOF_FIELDS, "proof for a prior anonymous identity")


def assert_no_attestation(body: Mapping[str, Any] | None) -> None:
    """The request carries no attestation or integrity proof."""
    # [impl->req~users-create-user-request-no-attestation~1]
    _reject_fields(body, ATTESTATION_FIELDS, "an attestation or integrity proof")


def assert_no_restore_proof(body: Mapping[str, Any] | None) -> None:
    """The request carries no `restore_proof`."""
    # [impl->req~users-create-user-request-no-restore-proof~1]
    _reject_fields(body, RESTORE_PROOF_FIELDS, "a restore_proof")


def _reject_fields(body: Mapping[str, Any] | None, forbidden: frozenset[str],
                   what: str) -> None:
    offending = sorted(set(body or {}) & forbidden)
    if offending:
        raise UsersError(f"POST /auth/create-user takes no {what}: {offending}")


# What `create_user` writes towards free credits and device grants: nothing.
CREATE_USER_GRANT_WRITES: frozenset[str] = frozenset()

_FORBIDDEN_GRANT_WRITES: frozenset[str] = frozenset({
    "access_grant", "free_credit_grant", "anonymous_free_credits", "anonymous_device_grant",
    "device_grant_state", "grant_ledger"})


def assert_no_free_credits(writes: Iterable[str] = ()) -> None:
    """`create_user` must not allocate anonymous free credits or create anonymous device
    grants."""
    # [impl->req~users-create-user-no-free-credits~1]
    if CREATE_USER_GRANT_WRITES:
        raise UsersError("create_user allocates no free credits and no device grants")
    offending = sorted(set(writes) & _FORBIDDEN_GRANT_WRITES)
    if offending:
        raise UsersError(f"create_user creates no {offending}")
