"""`upgrade_anonymous_to_registered`: the endpoint half of `POST /auth/upgrade-anonymous`.

The shared procedures own the barrier checks, the challenge lookup, the claim, the consuming
transaction and the audit write. This module holds what the upgrade itself decides: its two
purposes, the stranded state it repairs, the entry conditions a completion must meet, the one
mandatory Firebase Admin confirmation, the complete case matrix the flip and the idempotent
no-op follow, and the endpoint's own rejection classes and audit record.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import ChallengeRow
from nativespeaker.api.auth.create_user import (
    AdminLookupResult,
    ProviderNotLinkedCause,
    firebase_admin_get_user,
    provider_not_linked_details,
)
from nativespeaker.api.auth.entitlement import GrantMutation, guard_grant_mutation
from nativespeaker.api.auth.external_identities import (
    PROVIDER_CONFLICT_MUTATIONS,
    PROVIDER_CONFLICT_REMEDY,
    PROVIDER_UID_ASSIGNING_OPERATION,
    REGISTERED_PROVIDERS,
    RESERVATION_INDEX_COLUMNS,
    RESERVATION_INDEX_PREDICATE,
    RESERVED_IDENTITY_STATES,
    ExternalIdentityRow,
    IdentityState,
    ProviderAccountAlreadyLinkedError,
    ProviderClassificationError,
    ProviderConsumer,
    ProviderDataReadPoint,
    ProviderLookupFailedError,
    assert_may_write_provider_fields,
    authoritative_provider,
    matches_identity,
    provider_account_conflict,
    revokes_refresh_tokens,
)
from nativespeaker.api.auth.integration import FirebaseIntegrations
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.movement import MovementClassification, movement_audit_details
from nativespeaker.api.auth.onboarding import (
    assert_no_upgrade_restore_proof,
    assert_pre_consumption_checks_first,
    upgrade_authentication,
    upgrade_declared_provider,
    upgrade_success,
)
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    is_challenge_bearing,
    route_for,
)
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.profile import (
    AdminUserRecord,
    assert_registered_at_pairing,
    email_on_upgrade,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass, surface
from nativespeaker.api.auth.users import (
    ProviderNotConfirmedError,
    UpgradeBranch,
    UpgradeDecision,
    assert_no_secondary_auth_state,
    context_pair,
    firebase_identity_lookup,
    issuer_selected_admin_client,
    upgrade_audit_context,
    upgrade_completion_decision,
    upgrade_prepare_constraints,
)
from nativespeaker.api.exceptions import ErrorCode
from nativespeaker.api.ratelimit.ordering import AdmissionLedger, BudgetVerdict


class UpgradeError(RuntimeError):
    """An `upgrade_anonymous_to_registered` rule was about to be broken."""


# --- What the operation is for -----------------------------------------------------------------


class UpgradePurpose(StrEnum):
    """The two purposes the one operation serves."""
    link_completion = "link_completion"
    stranded_repair = "stranded_repair"


@dataclass(frozen=True, slots=True)
class UpgradeUser:
    """The `core.users` row the completion locks, and the two profile fields it may fill in."""
    id: UUID
    email: str | None = None
    registered_at: datetime | None = None
    display_name: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class StrandedUpgrade:
    """A crash-stranded or abandoned upgrade: the same account and the same identity row, live
    Firebase already showing a registered provider, the backend still storing `anonymous`."""
    identity: ExternalIdentityRow
    user: UpgradeUser
    live_provider: IdentityProvider


# Stranding is a valid state, so it triggers nothing on its own: no automatic `historical`
# transition, no forced sign-out, and no registered grant until a repair completion succeeds.
STRANDING_SIDE_EFFECTS: frozenset[str] = frozenset()
STRANDED_ACCOUNT_GRANTS: frozenset[str] = frozenset()


def stranded_upgrade(identity: ExternalIdentityRow, user: UpgradeUser, *,
                     live_provider: IdentityProvider) -> StrandedUpgrade | None:
    """The stranded state, as the backend can see it: after a successful `linkWithCredential`
    and before a successful backend completion, live `providerData` shows one supported
    registered provider while the existing identity row still stores `provider = 'anonymous'`
    and the user still has `registered_at = NULL`. It is the same account and identity row —
    neither historical nor blocked, linked rather than pre-auth.

    That state is valid rather than broken: between a successful `linkWithCredential` and a
    successful backend upgrade it is expected, it marks no identity `historical`, and it forces no
    sign-out in this version."""
    # [impl->req~users-stranded-upgrade-definition~1]
    # [impl->req~sessions-stranded-account-state~1]
    if STRANDING_SIDE_EFFECTS or STRANDED_ACCOUNT_GRANTS:
        raise UpgradeError("stranding causes no historical transition, sign-out or grant")
    if live_provider not in REGISTERED_PROVIDERS:
        return None
    if identity.provider is not IdentityProvider.anonymous or user.registered_at is not None:
        return None
    # The stranded account is untouched by the stranding itself: the row stays `active` and the
    # user stays active, so nothing about it is historical, blocked or signed out.
    if identity.identity_state is not IdentityState.active or not user.active:
        raise UpgradeError("a stranded upgrade leaves the account active and the row linked")
    if identity.user_id != user.id:
        raise UpgradeError("a stranded upgrade is the same account throughout")
    return StrandedUpgrade(identity=identity, user=user, live_provider=live_provider)


@dataclass(frozen=True, slots=True)
class StrandedExposure:
    """What a stranded account can and cannot do until a repair completion succeeds."""
    registered_grant_available: bool
    sign_out_all_effective: bool
    residual_exposure: str


# The one residual exposure of the stranding window: the already-accepted lifetime of ID tokens
# already minted. Nothing else is exposed by it.
STRANDING_RESIDUAL_EXPOSURE: str = "already_minted_id_token_lifetime"


def stranded_exposure(stranded: StrandedUpgrade) -> StrandedExposure:
    """Until a repair succeeds the stranded account receives no registered grant, because claims
    stay gated on the stored classification rather than on live `providerData`, and sign-out
    everywhere stays fully effective, because refresh-token revocation is unconditional for every
    account. The residual exposure of the window is the already-accepted lifetime of ID tokens
    already minted, and nothing more."""
    # [impl->req~sessions-stranded-account-no-registered-grant~1]
    stored = authoritative_provider(stranded.identity, ProviderConsumer.registered_grant_gating)
    if stored is not IdentityProvider.anonymous:
        raise UpgradeError("a stranded row still stores the anonymous classification")
    if STRANDED_ACCOUNT_GRANTS:
        raise UpgradeError("a stranded account receives no registered grant")
    if not revokes_refresh_tokens(stranded.identity):
        raise UpgradeError("sign-out everywhere stays unconditional while stranded")
    return StrandedExposure(registered_grant_available=False,
                            sign_out_all_effective=True,
                            residual_exposure=STRANDING_RESIDUAL_EXPOSURE)


# The repair role is required. Nothing may remove it, however idempotent a completed upgrade is.
REPAIR_ROLE_OPTIMIZATIONS: frozenset[str] = frozenset()


def upgrade_purpose(stranded: StrandedUpgrade | None) -> UpgradePurpose:
    """Which of the two purposes this completion serves: ordinary account linking, or the repair
    of a crash-stranded or abandoned upgrade whose client-side link succeeded while backend
    completion did not. The repair role is required and must not be optimized away even though
    completed upgrades are idempotent.

    This one endpoint is therefore also the repair path for an upgrade whose Firebase link
    succeeded but whose backend call crashed, lost connectivity or was abandoned: its idempotence
    is what carries that repair."""
    # [impl->req~users-upgrade-purpose-repair~1]
    # [impl->req~sessions-upgrade-repair-path~1]
    if REPAIR_ROLE_OPTIMIZATIONS:
        raise UpgradeError("the crash-stranded repair role is never optimized away")
    return (UpgradePurpose.stranded_repair if stranded is not None
            else UpgradePurpose.link_completion)


def linking_flip(row: ExternalIdentityRow, decision: UpgradeDecision, *,
                 context: VerifiedIdentityContext, transaction: object) -> ExternalIdentityRow:
    """Complete same-Firebase-UID account linking: the existing anonymous identity row for the
    verified `(issuer, subject)` flips to the confirmed `google` or `apple` in place. The same
    Firebase UID keeps the same row and the same user; nothing is created and nothing moves.

    This endpoint records the same-Firebase-UID upgrade `linkWithCredential` performs and nothing
    else: the anonymous identity and the registered identity it becomes are one row, sharing the
    one verified `(issuer, subject)`. The flip stores the declared, Admin-confirmed provider and
    takes that row's `provider_uid` from the matching `providerData` entry in this same
    transaction."""
    # [impl->req~users-upgrade-purpose-link~1]
    # [impl->req~sessions-upgrade-same-uid-only~1]
    # [impl->req~sessions-upgrade-branch-anonymous-flip~1]
    # [impl->req~sessions-transition-in-place-provider-flip~1]
    if decision.branch is not UpgradeBranch.mutable:
        raise UpgradeError("only the mutable branch flips the stored provider")
    if row.provider is not IdentityProvider.anonymous:
        raise UpgradeError("the linking flip starts from the stored anonymous provider")
    flipped = upgrade_success(row, decision, context=context, transaction=transaction)
    if (flipped.id != row.id or flipped.user_id != row.user_id
            or flipped.issuer != row.issuer or flipped.subject != row.subject):
        raise UpgradeError("the same Firebase UID keeps its identity row and its user")
    if flipped.provider not in REGISTERED_PROVIDERS or not flipped.provider_uid:
        raise UpgradeError("the flip stores the confirmed registered provider and its uid")
    return flipped


# --- Entry conditions at completion time -------------------------------------------------------


# Where the confirmed registered provider may come from: the Firebase Admin `providerData` read
# alone. The client's declaration is what that read is checked against, never the confirmation
# itself, and no token claim, request header or already-stored row value stands in for it.
CONFIRMATION_SOURCE: str = "firebase_admin_provider_data"
REJECTED_CONFIRMATION_SOURCES: frozenset[str] = frozenset({
    "token_claim", "request_header", "client_declaration", "stored_provider",
    "firebase_sign_in_provider", "id_token_auth_time"})


def assert_confirmation_source(source: str = CONFIRMATION_SOURCE) -> str:
    """The flip's content comes from server-verified `providerData` and from nothing else. No
    token claim and no request header drives the provider or grant decision, which is why a stale
    anonymous-era token cannot drive one: token possession is the entry condition, and the live
    Admin read is the content."""
    # [impl->req~sessions-upgrade-token-freshness-irrelevant~1]
    # [impl->req~sessions-repair-providerdata-source-of-truth~1]
    if source in REJECTED_CONFIRMATION_SOURCES or source != CONFIRMATION_SOURCE:
        raise UpgradeError(f"the confirmed provider is never taken from {source}")
    return source


def entry_linked_identity(context: VerifiedIdentityContext, *,
                          row: ExternalIdentityRow | None = None) -> UUID:
    """The request uses a Firebase ID token from the unchanged client `Authorization` header
    that the shared pre-handler barrier verified cryptographically; its verified `iss` and `sub`
    yield `(issuer, subject)` and must match an existing linked active identity row. Possession
    of any valid token for that pair suffices, at any freshness.

    This is not a pre-auth endpoint: it operates on the existing linked identity for the verified
    pair, and any valid token for that pair is enough however stale it is."""
    # [impl->req~users-upgrade-entry-token-resolves-linked-identity~1]
    # [impl->req~sessions-upgrade-linked-identity-flip~1]
    # [impl->req~sessions-upgrade-token-freshness-irrelevant~1]
    issuer, subject = context_pair(context)
    identity_id = upgrade_authentication(context, row=row)
    if row is not None and not matches_identity(row, issuer, subject):
        raise UpgradeError("the identity row is the one the verified pair resolves to")
    return identity_id


def entry_target_provider(declared: str | None, *, phase: RequestMode,
                          row: ChallengeRow | None = None) -> IdentityProvider:
    """The request carries a client-declared target provider of `google` or `apple`."""
    # [impl->req~users-upgrade-entry-declared-target-provider~1]
    provider = upgrade_declared_provider(declared, phase=phase, row=row)
    if provider not in REGISTERED_PROVIDERS:
        raise UpgradeError(f"{provider} is not an upgrade target provider")
    return provider


def entry_no_restore_proof(body: Mapping[str, Any] | None) -> None:
    """`restore_proof` is absent."""
    # [impl->req~users-upgrade-entry-no-restore-proof~1]
    assert_no_upgrade_restore_proof(body)


def upgrade_branch(row: ExternalIdentityRow, *, lookups: int) -> UpgradeBranch:
    """The mutable anonymous-to-registered path applies when the row's stored provider is
    `anonymous`. Idempotent success, when the row already stores the declared provider, is
    allowed only after the mandatory live Admin confirmation on this same call.

    Every call resolves to exactly one of these branches, and each is evaluated against this
    call's live `providerData` read: a stored provider that already equals the declared one is
    never a reason to skip that read."""
    # [impl->req~users-upgrade-entry-mutable-vs-idempotent~1]
    # [impl->req~sessions-upgrade-branch-selection~1]
    if lookups != 1:
        raise UpgradeError("every branch performs the mandatory live confirmation on this call")
    return (UpgradeBranch.mutable if row.provider is IdentityProvider.anonymous
            else UpgradeBranch.idempotent)


def link_completed(provider_data: Sequence[Any]) -> bool:
    """The mutable path's entry condition: the client has completed same-Firebase-UID account
    linking — `linkWithCredential` on the existing anonymous Firebase user — before completion.
    Empty live `providerData` means that link never succeeded."""
    # [impl->req~users-upgrade-entry-client-link-completed~1]
    return bool(provider_data)


# --- The endpoint's rejections -------------------------------------------------------------------


class TransitionDivergence(StrEnum):
    """The three divergences that are the one `provider_transition_not_allowed` conflict."""
    stored_provider_differs = "stored_provider_differs"
    live_provider_data_divergence = "live_provider_data_divergence"
    live_provider_uid_differs = "live_provider_uid_differs"


# Every internal `core.auth_event_result` this endpoint's rules and the barrier and challenge
# checks it inherits can produce.
UPGRADE_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.invalid_external_jwt,
    AuthEventResult.firebase_user_unresolved,
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.historical_identity,
    AuthEventResult.blocked_user,
    AuthEventResult.challenge_not_found,
    AuthEventResult.challenge_expired,
    AuthEventResult.challenge_consumed,
    AuthEventResult.challenge_identity_mismatch,
    AuthEventResult.challenge_operation_mismatch,
    AuthEventResult.policy_rejected,
    AuthEventResult.provider_not_linked,
    AuthEventResult.provider_transition_not_allowed,
    AuthEventResult.provider_account_already_linked,
    AuthEventResult.firebase_lookup_unavailable,
})


def upgrade_client_class(result: AuthEventResult) -> ErrorCode:
    """The opaque client-visible class a rejection returns, mapped from the underlying internal
    `core.auth_event_result`. Every provider rejection is audited under an internal result more
    specific than the shared `operation_not_allowed` class it surfaces as."""
    # [impl->req~users-upgrade-error-class-mapping~1]
    if result not in UPGRADE_RESULTS:
        raise UpgradeError(f"{result} is no rejection of POST /auth/upgrade-anonymous")
    client_class, _status = surface(result)
    return client_class


def audited_upgrade_result(result: AuthEventResult, client_class: ErrorCode) -> AuthEventResult:
    """The audit row records the specific internal `core.auth_event_result` regardless of which
    client class is returned, and that audited value is never less specific than the class: two
    results that share a class stay distinct in the row."""
    # [impl->req~users-upgrade-audit-specific-result~1]
    if result not in UPGRADE_RESULTS:
        raise UpgradeError(f"{result} is no rejection of POST /auth/upgrade-anonymous")
    sharing = {other for other in UPGRADE_RESULTS
               if other is not result and surface(other)[0] == client_class}
    if str(result) == client_class and sharing:
        raise UpgradeError(f"{result} is less specific than {client_class}")
    return result


class UpgradeRejection(ChallengeRejection):
    """An upgrade rejection: the specific internal result for the audit row, and the shared
    client class it surfaces as."""

    def __init__(self, result: AuthEventResult, *,
                 cause: ProviderNotLinkedCause | None = None,
                 divergence: TransitionDivergence | None = None,
                 detail: str | None = None,
                 audit_details: Mapping[str, Any] | None = None):
        reason = detail or (cause.value if cause else None) or (
            divergence.value if divergence else None)
        super().__init__(result, detail=reason)
        self.cause = cause
        self.divergence = divergence
        # The movement context this rejection resolved, folded into its single audit row by the
        # shared writer. It stays `None` only where the attempt resolved nothing at all.
        # [impl->req~users-upgrade-audit-row-requirements~1]
        self.audit_details = dict(audit_details) if audit_details is not None else None
        # [impl->req~users-upgrade-error-class-mapping~1]
        self.error_code = upgrade_client_class(result)
        audited_upgrade_result(result, self.error_code)


def lookup_rejection(failure: ProviderLookupFailedError) -> UpgradeRejection:
    """A failed mandatory confirmation, taken on the claimed row: the distinct internal result
    the shared lookup-failure handling assigned — `firebase_user_unresolved` for the subject
    deleted at Firebase, `firebase_lookup_unavailable` for every indeterminate cause — audited
    as itself and surfaced through the class that result maps to."""
    # [impl->req~users-upgrade-firebase-user-not-found~1]
    # [impl->req~users-upgrade-lookup-unavailable~1]
    rejection = UpgradeRejection(failure.result)
    if rejection.error_code != failure.client_class:
        raise UpgradeError(f"{failure.result} surfaces as {failure.client_class}")
    return rejection


def mutable_path_rejection(cause: ProviderNotLinkedCause) -> UpgradeRejection:
    """On the mutable path, any live result that does not confirm the declaration is audited as
    `provider_not_linked`, carrying the bounded cause that distinguishes the empty, invalid-shape
    and supported-provider-mismatch cases, and surfaces as `operation_not_allowed`."""
    # [impl->req~users-upgrade-mutable-path-provider-not-linked-audit~1]
    if cause not in set(ProviderNotLinkedCause):
        raise UpgradeError(f"{cause} is no bounded provider_not_linked cause")
    rejection = UpgradeRejection(AuthEventResult.provider_not_linked, cause=cause)
    if rejection.error_code != ClientErrorClass.operation_not_allowed:
        raise UpgradeError("a mutable-path provider rejection surfaces as operation_not_allowed")
    provider_not_linked_details(cause)
    return rejection


# What a `provider_transition_not_allowed` rejection changes: nothing. A wrong stored registered
# value is never automatically rewritten; only a manual operator repair fixes it.
TRANSITION_REJECTION_MUTATIONS: frozenset[str] = frozenset()
TRANSITION_REJECTION_REMEDY: str = "manual_operator_repair"


def transition_rejection(divergence: TransitionDivergence) -> UpgradeRejection:
    """A stored registered provider different from the declared, Admin-confirmed provider, a
    live `providerData` divergence on an idempotent repeat, and a live provider UID different
    from the immutable stored binding are the one `provider_transition_not_allowed` conflict:
    audited distinctly, surfaced as `operation_not_allowed`, and causing no mutation.

    A stored registered binding that diverges from the declared, Admin-confirmed one is not an
    identity transition at all: registered-to-registered migration is unsupported, so the stored
    `provider` and `provider_uid` are left exactly as they are even though live `providerData` has
    moved on. Nothing converges by retrying — the same conflict returns on every repeat call until
    a one-off administrative update repairs the stored row."""
    # [impl->req~users-upgrade-provider-transition-not-allowed-audit~1]
    # [impl->req~sessions-upgrade-branch-transition-conflict~1]
    # [impl->req~sessions-divergent-binding-not-a-transition~1]
    if divergence not in set(TransitionDivergence):
        raise UpgradeError(f"{divergence} is no registered-binding divergence")
    if TRANSITION_REJECTION_MUTATIONS:
        raise UpgradeError("a divergent stored binding is never automatically rewritten")
    rejection = UpgradeRejection(AuthEventResult.provider_transition_not_allowed,
                                 divergence=divergence)
    if rejection.error_code != ClientErrorClass.operation_not_allowed:
        raise UpgradeError("a divergent binding surfaces as operation_not_allowed")
    return rejection


def provider_conflict_rejection() -> UpgradeRejection:
    """`provider_account_already_linked` — the target `(issuer, provider, provider_uid)` already
    reserved by another identity row — is audited distinctly, surfaces as
    `operation_not_allowed`, and causes no mutation.

    Nothing is mutated by it: no user, identity, grant or profile state changes, and the remedy is
    an operator's, never an automatic rewrite."""
    # [impl->req~users-upgrade-provider-account-already-linked-audit~1]
    # [impl->req~sessions-upgrade-provider-account-already-linked~1]
    conflict = provider_account_conflict(AuthOperation.upgrade_anonymous_to_registered)
    if PROVIDER_CONFLICT_MUTATIONS or PROVIDER_CONFLICT_REMEDY != "manual_operator_fix":
        raise UpgradeError("a provider-account conflict mutates nothing and needs an operator")
    rejection = UpgradeRejection(conflict.result)
    if rejection.error_code != ClientErrorClass.operation_not_allowed:
        raise UpgradeError("the conflict surfaces as operation_not_allowed")
    return rejection


# The rejection conditions this endpoint owes at minimum, and the internal result each takes.
UPGRADE_FAILURE_RESULTS: dict[str, AuthEventResult] = {
    "identity_not_resolved": AuthEventResult.preauth_identity_not_allowed,
    "identity_inactive": AuthEventResult.historical_identity,
    "user_inactive": AuthEventResult.blocked_user,
    "declared_provider_missing_or_invalid": AuthEventResult.challenge_operation_mismatch,
    "live_confirmation_failed": AuthEventResult.provider_not_linked,
    "stored_live_binding_divergence": AuthEventResult.provider_transition_not_allowed,
    "provider_account_uniqueness_conflict": AuthEventResult.provider_account_already_linked,
    "lookup_failed_after_retry_budget": AuthEventResult.firebase_lookup_unavailable,
    "lookup_non_retryable": AuthEventResult.firebase_user_unresolved,
    "policy_rejected": AuthEventResult.policy_rejected,
}


def upgrade_failure_result(condition: str) -> AuthEventResult:
    """The internal result each named rejection condition takes. Rejection includes at minimum
    every condition named here; each one is a real rejection of this endpoint rather than an
    unhandled error."""
    # [impl->req~users-upgrade-failure-scope~1]
    result = UPGRADE_FAILURE_RESULTS.get(condition)
    if result is None:
        raise UpgradeError(f"{condition} is no named rejection condition of this endpoint")
    if result not in UPGRADE_RESULTS:
        raise UpgradeError(f"{result} is no rejection of POST /auth/upgrade-anonymous")
    return result


# --- The complete case matrix ---------------------------------------------------------------------


def classify_live_provider(lookup: AdminLookupResult, declared: IdentityProvider, *,
                           row: ExternalIdentityRow,
                           branch: UpgradeBranch) -> UpgradeDecision:
    """Apply the same closed classifier `create_user` uses, then the case matrix's confirmation
    rule: the classified provider must equal the declaration for a successful mutable or
    idempotent branch, and a matching registered entry must carry a non-empty `uid` — a missing
    or empty one is a malformed lookup result that rejects with no persistence under the shared
    lookup-failure handling. Neither branch takes the first recognized entry, classifies
    non-empty data as anonymous, or reads `firebase.sign_in_provider`.

    The classified provider must equal the client's declaration; a mismatch rejects the upgrade
    with no mutation. The `providerData` read the Admin lookup returned is the sole source of
    truth for what is confirmed here — the client's Firebase state is only the trigger and the
    declaration."""
    # [impl->req~users-upgrade-step-03~1]
    # [impl->req~sessions-upgrade-linked-identity-flip~1]
    # [impl->req~sessions-repair-providerdata-source-of-truth~1]
    assert_confirmation_source()
    try:
        decision = upgrade_completion_decision(row, declared,
                                               provider_data=list(lookup.provider_data))
    except ProviderNotConfirmedError:
        raise _unconfirmed(branch, lookup.provider_data) from None
    except ProviderClassificationError:
        raise _unconfirmed(branch, lookup.provider_data, invalid_shape=True) from None
    except ProviderLookupFailedError as failure:
        # A matching registered entry with a missing or empty `uid` is a malformed lookup
        # result: it rejects with no persistence under the shared lookup-failure handling.
        raise lookup_rejection(failure) from None
    except ChallengeRejection as rejection:
        raise UpgradeRejection(rejection.result, detail=rejection.detail) from None
    if decision.branch is not branch:
        raise UpgradeError(f"{decision.branch} is not the branch the stored provider selects")
    return decision


def _unconfirmed(branch: UpgradeBranch, provider_data: Sequence[Any], *,
                 invalid_shape: bool = False) -> UpgradeRejection:
    """Which rejection an unconfirming live classification is. On the idempotent-repeat path any
    `providerData` divergence from the stored registered binding is the transition conflict; on
    the mutable path it is the ordinary `provider_not_linked`, with its bounded cause."""
    if branch is UpgradeBranch.idempotent:
        return transition_rejection(TransitionDivergence.live_provider_data_divergence)
    if invalid_shape:
        cause = ProviderNotLinkedCause.invalid_provider_data_shape
    elif not link_completed(provider_data):
        # Empty `providerData`: client-side linking never succeeded, so the mutable path's entry
        # condition was never met and the client must run `linkWithCredential` first.
        cause = ProviderNotLinkedCause.empty_provider_data
    else:
        cause = ProviderNotLinkedCause.supported_provider_mismatch
    return mutable_path_rejection(cause)


# `display_name` is populated from neither auth context nor the Firebase Admin user record.
UPGRADE_DISPLAY_NAME_SOURCES: frozenset[str] = frozenset()


def upgraded_user(user: UpgradeUser, record: AdminUserRecord | None, *,
                  provider: IdentityProvider, now: datetime) -> UpgradeUser:
    """The `core.users` half of the flip: `registered_at` is set only if it is `NULL`, and the
    `email` is copied only if the stored email is `NULL` and the same Admin response reports a
    non-empty address with `emailVerified = true`. A stored value of either is never
    overwritten, and `display_name` is not populated at all — neither from auth context nor from
    the Admin record."""
    # [impl->req~users-upgrade-step-07~1]
    # [impl->req~sessions-upgrade-linked-identity-flip~1]
    registered_at = user.registered_at if user.registered_at is not None else now
    email = email_on_upgrade(user.email, record)
    if UPGRADE_DISPLAY_NAME_SOURCES:
        raise UpgradeError("display_name is not populated from auth context or the Admin record")
    upgraded = replace(user, registered_at=registered_at, email=email)
    if user.registered_at is not None and upgraded.registered_at != user.registered_at:
        raise UpgradeError("a non-NULL registered_at is never overwritten")
    if user.email is not None and upgraded.email != user.email:
        raise UpgradeError("a non-NULL stored email is never overwritten")
    if upgraded.display_name != user.display_name:
        raise UpgradeError("display_name is left exactly as it was")
    # `registered_at IS NOT NULL` because and only because the stored provider is registered.
    # [impl->req~users-upgrade-step-10~1]
    assert_registered_at_pairing(provider, upgraded.registered_at)
    return upgraded


# The one upgrade transaction: no cross-table constraint trigger and no third authorization,
# grant or audit state enforces the provider/`registered_at` pairing — the code above does.
PAIRING_ENFORCEMENT_STATES: frozenset[str] = frozenset()


def assert_upgrade_transaction(session: Any, *used: Any) -> Any:
    """One database transaction is started for the upgrade completion, and every write of the
    completion — the flip, the profile fields, the challenge consumption and the audit row —
    shares it. The endpoint opens none of its own.

    Because the provider flip, the `registered_at` write and the conditional email copy all commit
    in this one transaction, a partial failure leaves no half-upgraded account: a mid-completion
    Admin failure or classifier rejection rolls the transaction back and mutates nothing."""
    # [impl->req~users-upgrade-step-04~1]
    # [impl->req~sessions-upgrade-single-transaction~1]
    for transaction in used:
        if transaction is not session:
            raise UpgradeError("every upgrade write shares the one completion transaction")
    return session


def assert_commits_together(identity: ExternalIdentityRow, user: UpgradeUser, *,
                            transaction: Any, identity_transaction: Any,
                            user_transaction: Any) -> None:
    """The classified provider, `provider_uid`, `registered_at` and any email copy commit
    together, and code in the transaction — not a cross-table constraint trigger and not a third
    authorization, grant or audit state — enforces the provider/`registered_at` pairing."""
    # [impl->req~users-upgrade-step-10~1]
    assert_upgrade_transaction(transaction, identity_transaction, user_transaction)
    if PAIRING_ENFORCEMENT_STATES:
        raise UpgradeError("no trigger or third state enforces the pairing; the code does")
    if identity.provider in REGISTERED_PROVIDERS and not identity.provider_uid:
        raise UpgradeError("the provider and its provider_uid commit together")
    assert_registered_at_pairing(identity.provider, user.registered_at)


# The reservation the flip writes under, and the states it spans.
UPGRADE_RESERVATION: tuple[tuple[str, str, str], str] = (RESERVATION_INDEX_COLUMNS,
                                                         RESERVATION_INDEX_PREDICATE)


def assert_reservation_scope() -> None:
    """The flip persists `provider` and `provider_uid` under the partial unique index over
    `(issuer, provider, provider_uid)` for rows whose `provider_uid` is not `NULL`, historical
    rows included, and this upgrade is the only path that fills `provider_uid` in on an existing
    row."""
    # [impl->req~users-upgrade-step-08~1]
    columns, predicate = UPGRADE_RESERVATION
    if columns != ("issuer", "provider", "provider_uid") or predicate != "provider_uid IS NOT NULL":
        raise UpgradeError("the flip writes under the partial provider-account reservation")
    if RESERVED_IDENTITY_STATES != frozenset(IdentityState):
        raise UpgradeError("the reservation spans historical rows too")
    if PROVIDER_UID_ASSIGNING_OPERATION is not AuthOperation.upgrade_anonymous_to_registered:
        raise UpgradeError("this upgrade is the only path that fills provider_uid in")


# No path creates a second identity row for the pair, and none marks the source row historical.
UPGRADE_CREATED_IDENTITY_ROWS: frozenset[str] = frozenset()
UPGRADE_RETIRED_IDENTITY_ROWS: frozenset[str] = frozenset()


def assert_in_place(before: ExternalIdentityRow, after: ExternalIdentityRow) -> None:
    """No new `core.external_identities` row is created and the source row is not marked
    `historical`. No path flips a registered row back to `anonymous`, and registered-to-registered
    rebinding remains unsupported.

    Beyond the idempotent success branch — where the stored provider and the stored `provider_uid`
    both match the declared, Admin-confirmed binding — an already registered row is never modified
    here: a divergent call is refused rather than applied, no identity is retired, no new
    registered identity row appears and no historical row is produced."""
    # [impl->req~users-upgrade-step-09~1]
    # [impl->req~sessions-upgrade-no-reverse-transition~1]
    # [impl->req~sessions-transition-no-retirement-or-new-row~1]
    if UPGRADE_CREATED_IDENTITY_ROWS or UPGRADE_RETIRED_IDENTITY_ROWS:
        raise UpgradeError("the upgrade creates no identity row and retires none")
    if after.id != before.id or after.user_id != before.user_id:
        raise UpgradeError("the upgrade stays on the one existing identity row")
    if after.identity_state is not before.identity_state:
        raise UpgradeError("the upgrade marks no identity row historical")
    if before.provider in REGISTERED_PROVIDERS and after.provider is not before.provider:
        raise UpgradeError(
            f"{before.provider} to {after.provider} is not a supported rebinding")


# Everything this operation preserves because it is the same logical user throughout.
PRESERVED_BUSINESS_STATE: tuple[str, ...] = (
    "chats", "access_grants", "introductory_value", "grant_monthly_usage",
    "subscriptions", "core.store_purchase_tokens")

# What the operation does to purchase-attribution tokens: nothing at all.
ATTRIBUTION_TOKEN_MUTATIONS: frozenset[str] = frozenset()


def assert_state_preserved(before: Mapping[str, Any], after: Mapping[str, Any], *,
                           user_id: UUID | None = None,
                           attribution_owners: Sequence[UUID] = ()) -> None:
    """Chats, existing access grants, introductory value, grant-attached monthly usage state,
    subscription records and purchase-attribution tokens are all preserved, because this is the
    same logical user throughout. The operation generates no new attribution token, moves none
    between users and retires none: the existing `core.store_purchase_tokens` rows continue to
    belong to the same `core.users` row.

    The upgrade therefore preserves the user's chats, credits and grants on the same `core.users`
    and `core.external_identities` rows, and that same `core.users` row remains the owner of all of
    it after the transition."""
    # [impl->req~users-upgrade-step-11~1]
    # [impl->req~sessions-upgrade-preserves-account-state~1]
    # [impl->req~sessions-transition-users-row-remains-owner~1]
    if ATTRIBUTION_TOKEN_MUTATIONS:
        raise UpgradeError("the upgrade generates, moves and retires no attribution token")
    changed = [name for name in PRESERVED_BUSINESS_STATE if before.get(name) != after.get(name)]
    if changed:
        raise UpgradeError(f"{changed} are preserved across the upgrade")
    if user_id is not None and any(owner != user_id for owner in attribution_owners):
        raise UpgradeError("store purchase tokens keep belonging to the same user row")


# What this completion, repair completions included, writes towards grants and device state.
UPGRADE_GRANT_WRITES: frozenset[str] = frozenset()
UPGRADE_DEVICE_GRANT_BITS: frozenset[str] = frozenset()


def assert_identity_metadata_only(*, grants: Sequence[str] = (),
                                  device_bits: Sequence[str] = (),
                                  registered_grant_claimed: bool = False) -> None:
    """This completion, including a repair completion, updates identity metadata only: it
    creates no access grant, mints no free-credit grant, reads or writes no per-device grant
    bits, and never counts as a fresh registered-grant claim. A later `claim_registered_grant`
    runs under its own rules, including the account-grant-history gating.

    That is the whole of a repair completion's effect too: it updates identity metadata only, mints
    no free-credit grant, and the `linkWithCredential` in-place flip neither reads nor modifies
    per-device grant bits."""
    # [impl->req~users-upgrade-step-12~1]
    # [impl->req~sessions-upgrade-preserves-account-state~1]
    # [impl->req~sessions-repair-updates-metadata-only~1]
    if grants or UPGRADE_GRANT_WRITES:
        guard_grant_mutation(AuthOperation.upgrade_anonymous_to_registered,
                             GrantMutation.access_grant_write)
    if device_bits or UPGRADE_DEVICE_GRANT_BITS:
        raise UpgradeError("the upgrade reads and writes no per-device grant bits")
    if registered_grant_claimed:
        raise UpgradeError("no upgrade completion counts as a fresh registered-grant claim")


# --- The audit record ------------------------------------------------------------------------------

# The one durable row an attempt writes, and the fact that it is not best-effort.
UPGRADE_AUDIT_ROWS: tuple[str, ...] = ("audit.auth_events",)
UPGRADE_AUDIT_BEST_EFFORT: bool = False


def upgrade_attempt_audit(*, result: AuthEventResult, occurred_at: datetime,
                          user_id: UUID | None = None,
                          external_identity_id: UUID | None = None,
                          challenge_row_id: UUID | None = None,
                          current_identity_provider: IdentityProvider | None = None,
                          rows_written: Sequence[str] = UPGRADE_AUDIT_ROWS) -> dict[str, Any]:
    """The `details` body of the single `audit.auth_events` row every attempt that reaches the
    normal audited attempt path owes, successful or rejected: movement classification `upgrade`,
    source and destination identity context for the same identity row where known, and the
    resolved user where known. Challenge correlation records only the non-secret server-side
    challenge row ID in its dedicated field; `details` never carries the public `challenge_id`.
    Fields that cannot be resolved at the rejection point are recorded as `NULL`."""
    # [impl->req~users-upgrade-audit-row-requirements~1]
    if UPGRADE_AUDIT_BEST_EFFORT:
        raise UpgradeError("the upgrade's audit write is never best-effort")
    extra = sorted(set(rows_written) - set(UPGRADE_AUDIT_ROWS))
    if extra:
        raise UpgradeError(f"an upgrade attempt writes only {UPGRADE_AUDIT_ROWS}: {extra}")
    context = upgrade_audit_context(result=result, occurred_at=occurred_at, user_id=user_id,
                                    external_identity_id=external_identity_id,
                                    challenge_row_id=challenge_row_id)
    details = movement_audit_details(context)
    if current_identity_provider is not None:
        details["mutation"]["current_identity_provider"] = str(current_identity_provider)
    if "challenge_id" in str(details):
        raise UpgradeError("details never carries the public challenge_id handle")
    return details


def upgrade_success_audit(*, identity: ExternalIdentityRow, user: UpgradeUser,
                          challenge_row_id: UUID | None, occurred_at: datetime,
                          transaction: Any, mutation_transaction: Any) -> dict[str, Any]:
    """The success record: `result = 'succeeded'`, movement classification `upgrade`, the source
    and destination user and identity — one and the same row and user, before and after the flip
    or the idempotent no-op decision — and `current_identity_provider` sourced from the stored
    `core.external_identities.provider` value after that decision. It is appended in the same
    transaction as the challenge consumption and the decision, and is not best-effort."""
    # [impl->req~users-upgrade-step-13~1]
    assert_upgrade_transaction(transaction, mutation_transaction)
    details = upgrade_attempt_audit(result=AuthEventResult.succeeded, occurred_at=occurred_at,
                                    user_id=user.id, external_identity_id=identity.id,
                                    challenge_row_id=challenge_row_id,
                                    current_identity_provider=identity.provider)
    resolved = details["resolved"]
    if resolved["source_user_id"] != resolved["destination_user_id"]:
        raise UpgradeError("the upgraded user is both source and destination")
    if resolved["source_external_identity_id"] != resolved["destination_external_identity_id"]:
        raise UpgradeError("the same identity row is both source and destination")
    if details["mutation"]["movement_classification"] != MovementClassification.upgrade:
        raise UpgradeError("an upgrade classifies its movement as upgrade")
    if details["mutation"]["current_identity_provider"] != str(identity.provider):
        raise UpgradeError("current_identity_provider is the stored provider after the decision")
    return details


# --- The client's repair obligation and the two accounts it leaves alone ------------------------------


class RepairRetry(StrEnum):
    """How the client treats a failed repair attempt."""
    retry = "retry"
    fresh_challenge = "fresh_challenge"
    terminal = "terminal"


# The two read surfaces the client compares Firebase's cached local `providerData` against.
REPAIR_READ_SURFACES: tuple[tuple[str, str], ...] = (route_for(AuthOperation.sync),
                                                     ("GET", "/users/me"))

# Recovery uses the existing prepare/complete challenge model with linked-identity binding: it
# introduces no challenge type, webhook, polling mechanism or scheduled reconciliation job.
REPAIR_MECHANISMS: frozenset[str] = frozenset()


def repair_needed(*, backend_provider: IdentityProvider,
                  firebase_provider: IdentityProvider) -> bool:
    """Whenever Firebase shows a supported registered provider while the backend still reports
    `anonymous`, the client invokes `POST /auth/upgrade-anonymous` again — after every successful
    `linkWithCredential`, and on every app start and authenticated bootstrap — until the backend
    reports the completed transition.

    The comparison is against the Firebase SDK's cached `currentUser` `providerData`, a free local
    read, and the registration state the backend reports on the two read surfaces. It covers a
    crash, a reinstall with a surviving keychain and a new device signing in to the same Firebase
    account, where the shared UID makes the call an idempotent no-op if the flip already happened.
    Repair reuses the existing auth-challenge prepare and complete model with linked-identity
    binding and the challenge flow's existing rate limits: no new challenge type, no webhook, no
    polling and no scheduled reconciliation job."""
    # [impl->req~users-client-repair-obligation~1]
    # [impl->req~sessions-client-driven-repair-loop~1]
    # [impl->req~sessions-repair-providerdata-source-of-truth~1]
    if REPAIR_MECHANISMS:
        raise UpgradeError("repair adds no challenge type, webhook, polling or scheduled job")
    if not is_challenge_bearing(AuthOperation.upgrade_anonymous_to_registered):
        raise UpgradeError("repair reuses the existing prepare/complete challenge model")
    assert_confirmation_source()
    return firebase_provider in REGISTERED_PROVIDERS \
        and backend_provider is IdentityProvider.anonymous


def repair_disposition(client_class: str) -> RepairRetry:
    """What the client does with a failed repair. An `operation_not_allowed` conflict from this
    endpoint is terminal rather than transient — no repeat converges until an operator repairs
    the stored binding — while a consumed or expired challenge is prepared afresh and every
    other failure is retried. The loop stops at a terminal conflict rather than retrying it."""
    # [impl->req~users-client-repair-obligation~1]
    # [impl->req~sessions-client-driven-repair-loop~1]
    if client_class == ClientErrorClass.operation_not_allowed:
        return RepairRetry.terminal
    if client_class == ClientErrorClass.challenge_required:
        return RepairRetry.fresh_challenge
    return RepairRetry.retry


# What a failed client-side link does to the source anonymous account, and what the design adds
# around the abandoned one: nothing, on both counts.
ABANDONED_ACCOUNT_MUTATIONS: frozenset[str] = frozenset()
ABANDONED_ACCOUNT_MECHANISMS: frozenset[str] = frozenset()
NON_TRANSFER_COPY_IS_DISPLAY_ONLY: bool = True


def credential_already_in_use_route(outcome: ResolutionOutcome) -> tuple[str, str] | None:
    """`credential-already-in-use` is a failed client-side link followed by an ordinary sign-in,
    so the upgrade endpoint is not involved and the client must not report the failure as a
    completed upgrade. The resulting token for the different `(issuer, subject)` goes through
    normal per-request resolution with no special case: an identity linked to an active user
    continues as that user, a subject with no identity row is pre-auth and completes the normal
    registered `POST /auth/create-user` flow, and a historical identity or an identity linked to
    a blocked user is rejected normally.

    A call attempted anyway fails the mandatory Admin confirmation, because the anonymous subject's
    `providerData` carries no registered provider, and is rejected with no mutation of the source
    anonymous account: the upgrade merges no accounts. The failed upgrade mints no free-credit
    grant either, and a user created afterwards receives only what the normal registered-grant
    rules independently allow."""
    # [impl->req~users-credential-already-in-use-handling~1]
    # [impl->req~sessions-upgrade-credential-already-in-use~1]
    # [impl->req~sessions-upgrade-fallback-sign-in-resolution~1]
    if outcome is ResolutionOutcome.linked:
        return None
    if outcome is ResolutionOutcome.pre_auth:
        return ("POST", "/auth/create-user")
    if outcome in (ResolutionOutcome.historical_identity, ResolutionOutcome.blocked_user):
        raise UpgradeRejection(AuthEventResult.historical_identity
                               if outcome is ResolutionOutcome.historical_identity
                               else AuthEventResult.blocked_user)
    raise UpgradeError(f"{outcome} is no per-request resolution outcome")


def abandoned_anonymous_account(identity: ExternalIdentityRow, user: UpgradeUser, *,
                                grants: Sequence[str] = ()) -> tuple[ExternalIdentityRow,
                                                                     UpgradeUser]:
    """The abandoned anonymous account is deliberately left untouched: it stays `active` and
    keeps its user row, credits and grant bound to its own `(issuer, subject)`. Nothing is
    merged, transferred, retired or stripped, and the design adds no server-side confirmation
    step, no challenge binding to the target account and no invalidation of that grant.

    The product copy that states registering with an already-used account transfers neither
    anonymous history nor remaining credits is display-only: it adds no acknowledgment step."""
    # [impl->req~users-abandoned-anonymous-account-untouched~1]
    # [impl->req~sessions-abandoned-anonymous-account-untouched~1]
    if ABANDONED_ACCOUNT_MUTATIONS or ABANDONED_ACCOUNT_MECHANISMS:
        raise UpgradeError("nothing is merged, transferred, retired or stripped")
    if not NON_TRANSFER_COPY_IS_DISPLAY_ONLY:
        raise UpgradeError("the required non-transfer product copy is display-only")
    if identity.identity_state is not IdentityState.active or not user.active:
        raise UpgradeError("the abandoned anonymous account remains active")
    if identity.provider is not IdentityProvider.anonymous:
        raise UpgradeError("the abandoned account is the anonymous one")
    if grants and identity.user_id != user.id:
        raise UpgradeError("the abandoned grant stays bound to its own account")
    return identity, user


# --- The endpoint --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfirmedUpgrade:
    """What the mandatory live confirmation produced, before the write transaction opens."""
    declared: IdentityProvider
    lookup: AdminLookupResult
    identity_id: UUID
    lookups: int = 1


@dataclass(frozen=True, slots=True)
class LockedRows:
    """The identity row and its user row, locked for the completion transaction."""
    identity: ExternalIdentityRow
    user: UpgradeUser
    locked: tuple[str, ...] = ()
    transaction: Any = None


@dataclass(frozen=True, slots=True)
class UpgradeLiveState:
    """The re-resolved, locked and active rows the mutation runs against."""
    rows: LockedRows


@dataclass(frozen=True, slots=True)
class UpgradedAccount:
    """The resulting backend state, with no backend token in it."""
    identity: ExternalIdentityRow
    user: UpgradeUser
    branch: UpgradeBranch
    purpose: UpgradePurpose
    audit_details: Mapping[str, Any] = field(default_factory=dict)
    backend_token: None = None


# The two rows the completion locks, in the order it locks them.
IDENTITY_LOCK_ORDER: tuple[str, str] = ("core.external_identities", "core.users")


def resolved_and_locked(rows: LockedRows | None, *, issuer: str, subject: str,
                        session: Any) -> LockedRows:
    """Resolve the existing `core.external_identities` row by the backend-verified
    `(issuer, subject)` and lock that row and its `core.users` row for the completion
    transaction.

    The one write transaction opens by locking and revalidating the identity row, so every write
    that follows it sees the state it decided on."""
    # [impl->req~users-upgrade-step-05~1]
    # [impl->req~sessions-upgrade-single-transaction~1]
    if rows is None:
        raise UpgradeRejection(upgrade_failure_result("identity_not_resolved"))
    if not matches_identity(rows.identity, issuer, subject):
        raise UpgradeError("the row is resolved by the backend-verified pair alone")
    if rows.identity.user_id != rows.user.id:
        raise UpgradeError("the locked user row is the identity row's own user")
    if rows.locked != IDENTITY_LOCK_ORDER:
        raise UpgradeError(f"the completion locks {IDENTITY_LOCK_ORDER}")
    assert_upgrade_transaction(session, rows.transaction)
    return rows


def assert_rows_active(rows: LockedRows) -> LockedRows:
    """Confirm that the resolved identity and the resolved user are active."""
    # [impl->req~users-upgrade-step-06~1]
    if rows.identity.identity_state is not IdentityState.active:
        raise UpgradeRejection(upgrade_failure_result("identity_inactive"))
    if not rows.user.active:
        raise UpgradeRejection(upgrade_failure_result("user_inactive"))
    return rows


class IdentityStore(Protocol):
    """The database half of the upgrade transaction, as this endpoint calls it."""

    async def lock_identity(self, session: Any, issuer: str,
                            subject: str) -> LockedRows | None:
        """Resolve the identity row for the verified pair and lock it and its user row."""
        ...

    async def preserved_state(self, session: Any, user_id: UUID) -> Mapping[str, Any]:
        """The business state this operation must leave exactly as it found it."""
        ...

    async def flip_provider(self, session: Any, *, identity: ExternalIdentityRow,
                            user: UpgradeUser) -> None:
        """Persist the flipped identity row and its user row. Raises
        `ProviderAccountAlreadyLinkedError` on the provider-account reservation."""
        ...


class UpgradeEndpoint:
    """The endpoint half `SharedChallengeService` drives for `POST /auth/upgrade-anonymous`."""

    operation = AuthOperation.upgrade_anonymous_to_registered

    def __init__(self, *,
                 integrations: FirebaseIntegrations,
                 identities: IdentityStore,
                 lookup: Callable[[Any, str], Awaitable[AdminLookupResult]] | None = None,
                 clock: Callable[[], datetime] | None = None,
                 ledger: AdmissionLedger | None = None,
                 admit: Callable[[], BudgetVerdict] | None = None):
        self._integrations = integrations
        self._identities = identities
        self._lookup = lookup or firebase_admin_get_user
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ledger = ledger
        self._admit = admit
        self.lookups = 0

    # --- prepare ---------------------------------------------------------------------------

    async def check_prepare_eligibility(self, identity: VerifiedIdentityContext,
                                        variant: IdentityProvider | None) -> None:
        """Prepare needs the existing linked active identity row and the declared target."""
        # [impl->req~users-upgrade-entry-declared-target-provider~1]
        entry_target_provider(variant.value if variant else None, phase=RequestMode.prepare)
        upgrade_prepare_constraints(identity, variant.value if variant else None)

    # --- completion ------------------------------------------------------------------------

    async def verify_proof(self, identity: VerifiedIdentityContext, challenge: ChallengeRow,
                           body: Mapping[str, Any] | None) -> ConfirmedUpgrade:
        """The entry conditions, then mutation rules 1 to 3: the declared provider against the
        bound variant and the one mandatory Firebase Admin confirmation."""
        # No endpoint work runs unless this attempt already holds the claim, so every rejection
        # from here on — the ones at and after the mandatory Admin lookup included — is taken on
        # a claimed row and consumes the challenge under the shared completion requirements. A
        # retry therefore needs a freshly prepared challenge.
        # [impl->req~users-upgrade-rejection-consumes-challenge~1]
        assert_pre_consumption_checks_first(challenge)
        try:
            identity_id = entry_linked_identity(identity)
            entry_no_restore_proof(body)
            declared = self.declared_provider(challenge, body)
            lookup = await self.mandatory_lookup(identity)
        except UpgradeRejection as rejection:
            # This endpoint runs on a linked identity, so the barrier context already carries
            # the user and the identity row the movement moves: a rejection here records them
            # rather than the all-`NULL` pre-resolution context.
            # [impl->req~users-upgrade-audit-row-requirements~1]
            raise self.resolved_rejection(rejection, challenge,
                                          user_id=identity.user_id,
                                          external_identity_id=identity.external_identity_id,
                                          provider=identity.provider) from None
        # The provider fields this completion may write come from this read point alone.
        assert_may_write_provider_fields(ProviderDataReadPoint.upgrade_anonymous_completion)
        return ConfirmedUpgrade(declared=declared, lookup=lookup, identity_id=identity_id,
                                lookups=self.lookups)

    def resolved_rejection(self, rejection: UpgradeRejection, challenge: ChallengeRow, *,
                           user_id: UUID | None,
                           external_identity_id: UUID | None,
                           provider: IdentityProvider | None) -> UpgradeRejection:
        """Give a rejection the movement context the attempt had already resolved when it was
        taken: the same identity row as source and destination, the resolved user, the stored
        provider, and the non-secret challenge row id. Fields the attempt could not resolve stay
        `NULL`, and the shared writer folds the result into the attempt's single audit row."""
        # [impl->req~users-upgrade-audit-row-requirements~1]
        rejection.audit_details = upgrade_attempt_audit(
            result=rejection.result, occurred_at=self._clock(),
            user_id=user_id, external_identity_id=external_identity_id,
            challenge_row_id=challenge.id, current_identity_provider=provider)
        return rejection

    def declared_provider(self, challenge: ChallengeRow,
                          body: Mapping[str, Any] | None) -> IdentityProvider:
        """1. Require the completion's `provider` field to equal the provider variant prepare
        persisted, compared byte-for-byte and with no re-normalization. The shared completion
        check rejects a mismatch as `challenge_operation_mismatch` — a consuming rejection —
        before this operation performs a Firebase Admin lookup."""
        # [impl->req~users-upgrade-step-01~1]
        declared = (body or {}).get("provider")
        try:
            variant = entry_target_provider(declared if isinstance(declared, str) else None,
                                            phase=RequestMode.completion, row=challenge)
        except ChallengeRejection as mismatch:
            raise UpgradeRejection(mismatch.result) from None
        if self.lookups:
            raise UpgradeError("the variant is compared before the Firebase Admin lookup")
        return variant

    async def mandatory_lookup(self, identity: VerifiedIdentityContext) -> AdminLookupResult:
        """2. After the completion and Firebase-lookup admission checks pass, perform exactly one
        mandatory, fail-closed Firebase Admin `getUser(subject)` read immediately before the write
        transaction. Every branch, an idempotent repeat included, performs this live confirmation
        through the issuer-selected Admin client, and no branch may skip it — not even one whose
        stored row already carries the declared provider. The integration it runs on is the one
        Firebase Integration Selection picks from the verified issuer, never a token claim or a
        request header."""
        # [impl->req~users-upgrade-step-02~1]
        # [impl->req~sessions-upgrade-linked-identity-flip~1]
        if self.lookups:
            raise UpgradeError("exactly one getUser read is performed per completion")
        # Firebase user-not-found is non-retryable and consumes no retry budget; a transient,
        # infrastructure, matched-integration selection, malformed or otherwise indeterminate
        # failure is retried inside this one logical read and then surfaces as
        # `firebase_lookup_unavailable`. Neither persists anything. An issuer mismatch never
        # reaches here: the shared barrier rejects it as `invalid_external_jwt`.
        # [impl->req~users-upgrade-firebase-user-not-found~1]
        # [impl->req~users-upgrade-lookup-unavailable~1]
        try:
            client = issuer_selected_admin_client(self._integrations, identity.issuer)
            self.lookups += 1
            return await firebase_identity_lookup(lambda: self._lookup(client, identity.subject),
                                                  ledger=self._ledger, admit=self._admit)
        except ProviderLookupFailedError as failure:
            raise lookup_rejection(failure) from None

    async def confirm_live_state(self, session: Any, identity: VerifiedIdentityContext,
                                 challenge: ChallengeRow) -> UpgradeLiveState:
        """Mutation rules 4 to 6: the one transaction, the resolved and locked rows, and their
        active state."""
        assert_pre_consumption_checks_first(challenge)
        # 4. one database transaction for the upgrade completion — the shared consuming one.
        # [impl->req~users-upgrade-step-04~1]
        assert_upgrade_transaction(session)
        issuer, subject = context_pair(identity)
        try:
            rows = resolved_and_locked(
                await self._identities.lock_identity(session, issuer, subject),
                issuer=issuer, subject=subject, session=session)
        except UpgradeRejection as rejection:
            # Nothing was resolved: the barrier context is all this rejection knows.
            # [impl->req~users-upgrade-audit-row-requirements~1]
            raise self.resolved_rejection(rejection, challenge, user_id=identity.user_id,
                                          external_identity_id=identity.external_identity_id,
                                          provider=identity.provider) from None
        try:
            return UpgradeLiveState(rows=assert_rows_active(rows))
        except UpgradeRejection as rejection:
            # The step-06 inactive-identity and inactive-user rejections are taken on rows this
            # transaction has already resolved and locked, so both ends are known.
            # [impl->req~users-upgrade-audit-row-requirements~1]
            raise self.resolved_rejection(rejection, challenge, user_id=rows.user.id,
                                          external_identity_id=rows.identity.id,
                                          provider=rows.identity.provider) from None

    async def mutate(self, session: Any, identity: VerifiedIdentityContext,
                     challenge: ChallengeRow, proof: ConfirmedUpgrade,
                     live: UpgradeLiveState) -> UpgradedAccount:
        """Mutation rules 7 to 14, all inside that one transaction."""
        assert_pre_consumption_checks_first(challenge)
        rows = live.rows
        try:
            return await self._mutate(session, identity, challenge, proof, live)
        except UpgradeRejection as rejection:
            # Every rejection from here on is taken with the identity row and its user locked:
            # the conflict, the transition divergence and the live-classification rejections all
            # record the resolved movement context rather than an all-`NULL` one.
            # [impl->req~users-upgrade-audit-row-requirements~1]
            raise self.resolved_rejection(rejection, challenge, user_id=rows.user.id,
                                          external_identity_id=rows.identity.id,
                                          provider=rows.identity.provider) from None

    async def _mutate(self, session: Any, identity: VerifiedIdentityContext,
                      challenge: ChallengeRow, proof: ConfirmedUpgrade,
                      live: UpgradeLiveState) -> UpgradedAccount:
        rows = live.rows
        before = await self._identities.preserved_state(session, rows.user.id)

        # 7. the complete case matrix: the branch the stored provider selects, then the live
        # classification that must confirm the declaration on either branch. Exactly one branch
        # runs, and the live `providerData` read this call already performed decides it.
        # [impl->req~users-upgrade-step-07~1]
        # [impl->req~sessions-upgrade-branch-selection~1]
        # A success here is the whole of the recorded identity transition: the effects below are
        # everything `upgrade_anonymous_to_registered` changes.
        # [impl->req~sessions-upgrade-transition-effects~1]
        branch = upgrade_branch(rows.identity, lookups=proof.lookups)
        decision = classify_live_provider(proof.lookup, proof.declared, row=rows.identity,
                                          branch=branch)
        stranded = stranded_upgrade(rows.identity, rows.user, live_provider=decision.provider)
        purpose = upgrade_purpose(stranded)

        if branch is UpgradeBranch.idempotent:
            # The stored provider, the stored `provider_uid` and the live confirmation all
            # agree: idempotent no-op success, mutating nothing at all — whatever the row's
            # history, rows created directly as registered and never anonymous included.
            # [impl->req~users-upgrade-step-07~1]
            # [impl->req~sessions-upgrade-branch-idempotent-success~1]
            # [impl->req~sessions-transition-idempotent-no-mutation~1]
            flipped, user = rows.identity, rows.user
        else:
            # 8. the flip persists `provider` and `provider_uid` under the provider-account
            # reservation; a conflict rejects and leaves every other business state unchanged.
            # [impl->req~users-upgrade-step-08~1]
            # [impl->req~sessions-upgrade-branch-anonymous-flip~1]
            # [impl->req~sessions-upgrade-provider-account-already-linked~1]
            assert_reservation_scope()
            flipped = linking_flip(rows.identity, decision, context=identity, transaction=session)
            user = upgraded_user(rows.user, proof.lookup.record, provider=decision.provider,
                                 now=self._clock())
            assert_commits_together(flipped, user, transaction=session,
                                    identity_transaction=session, user_transaction=session)
            try:
                await self._identities.flip_provider(session, identity=flipped, user=user)
            except ProviderAccountAlreadyLinkedError:
                raise provider_conflict_rejection() from None
            # 9. no new identity row, no `historical` marking, no backwards or sideways rebinding.
            # [impl->req~users-upgrade-step-09~1]
            assert_in_place(rows.identity, flipped)

        # 11 and 12: the same logical user keeps everything, and this completion writes identity
        # metadata only.
        # [impl->req~users-upgrade-step-11~1]
        # [impl->req~users-upgrade-step-12~1]
        assert_state_preserved(before,
                               await self._identities.preserved_state(session, rows.user.id),
                               user_id=rows.user.id)
        assert_identity_metadata_only()

        # 13. the success audit record, in this same transaction.
        # [impl->req~users-upgrade-step-13~1]
        details = upgrade_success_audit(identity=flipped, user=user,
                                        challenge_row_id=challenge.id,
                                        occurred_at=self._clock(),
                                        transaction=session, mutation_transaction=session)
        return self.resulting_state(flipped, user, branch=branch, purpose=purpose,
                                    details=details)

    def resulting_state(self, identity: ExternalIdentityRow, user: UpgradeUser, *,
                        branch: UpgradeBranch, purpose: UpgradePurpose,
                        details: Mapping[str, Any]) -> UpgradedAccount:
        """14. Return the resulting backend state without issuing a backend token.

        No secondary backend auth-state revocation, generation advancement or token issuance is
        part of an identity transition."""
        # [impl->req~users-upgrade-step-14~1]
        # [impl->req~sessions-no-secondary-auth-state-revocation~1]
        account = UpgradedAccount(identity=identity, user=user, branch=branch, purpose=purpose,
                                  audit_details=details)
        if account.backend_token is not None:
            raise UpgradeError("the anonymous upgrade issues no backend token")
        assert_no_secondary_auth_state()
        return account
