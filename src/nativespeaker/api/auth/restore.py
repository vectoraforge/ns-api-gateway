"""`POST /auth/restore-subscription`: the endpoint contract, and the registered destination.

Restore is one call. It performs `restore_subscription` and nothing else; it is native-only, with
the store fixed by the calling platform; the store artifact is its whole proof; and the branch it
takes is a conclusion the backend draws from verified server state, never something the client
asks for. Its destination is always the current authenticated user, and that user must hold an
active, registered account.

This module owns the endpoint's shape — route, operation, request material, surface gate,
destination rules, and the single audit row an attempt owes. The branch decision itself is
`restore_flow`, the proof properties `restore_proof_policy`, and the two purchase tables
`store_purchases`.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import (
    NO_ACTOR,
    AttemptPhase,
    AuthActor,
    AuthEvent,
    AuthEventResult,
    movement_details,
    terminal_event,
)
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    assert_provider_uid_check,
)
from nativespeaker.api.auth.invariants import DevicePlatform, StoreProvider
from nativespeaker.api.auth.operations import (
    CHALLENGE_BEARING_OPERATIONS,
    AdmissionRejection,
    AuthOperation,
    IdentityProvider,
    is_admission_phase,
    match_operation,
    normalize_variant,
    route_for,
    supports_prepare,
)
from nativespeaker.api.auth.proof_endpoints import NATIVE_STORE_ARTIFACTS, RestoreRejected
from nativespeaker.api.auth.proof_restore import PLATFORM_STORE


class RestoreContractError(RuntimeError):
    """The endpoint was about to break its own contract. A server-side bug, not client input."""


class RestoreRejection(RuntimeError):
    """A rejected restore attempt, carrying the internal `core.auth_event_result` it audits as.

    Which client-visible class that internal result surfaces through is Client Error Mapping's
    business; what a rejection carries here is the internal result its single audit row records.
    """

    def __init__(self, result: AuthEventResult, message: str) -> None:
        super().__init__(message)
        self.result = result


# --- The endpoint contract -----------------------------------------------------------------------

# The one route and the one operation, read from the shared operation inventory rather than
# restated: the inventory holds exactly one entry for `restore_subscription`.
RESTORE_METHOD, RESTORE_PATH = route_for(AuthOperation.restore_subscription)

# Neither branch has an endpoint of its own, and there is no transfer endpoint: the client cannot
# select a branch by choosing where to post.
BRANCH_ENDPOINTS: frozenset[tuple[str, str]] = frozenset()

# Request fields that would let a client pick the branch, ask for a transfer, or name a source or
# destination account. None of them exists: the branch is a conclusion, not a parameter, and the
# destination is the authenticated user.
CLIENT_BRANCH_SELECTORS: frozenset[str] = frozenset({
    "branch", "transfer", "transfer_flag", "allow_transfer", "cross_account", "same_account",
    "adoption", "adopt", "movement", "movement_classification", "source_user_id",
    "source_account", "destination_user_id",
})


def assert_restore_endpoint_contract(method: str, path: str,
                                     *, body: Mapping[str, Any] | None = None) -> AuthOperation:
    """`POST /auth/restore-subscription` performs only `restore_subscription`, and the branch is
    resolved from verified server state alone: the client requests it neither with a separate
    endpoint nor with an explicit transfer flag."""
    # [impl->req~restore-endpoint-operation-and-branch-selection~1]
    # [impl->req~restore-branches-server-selected~1]
    operation = match_operation(method, path)
    if ((method.upper(), path) != (RESTORE_METHOD, RESTORE_PATH)
            or operation is not AuthOperation.restore_subscription):
        raise RestoreContractError(f"{method} {path} does not perform restore_subscription")
    if BRANCH_ENDPOINTS:
        raise RestoreContractError("neither restore branch has an endpoint of its own")
    offending = sorted(set(body or {}) & CLIENT_BRANCH_SELECTORS)
    if offending:
        raise RestoreContractError(f"the client does not request the branch with {offending}")
    return operation


# --- The native-only surface gate ----------------------------------------------------------------

# The store each platform fixes, derived from the proof file's platform-to-store map so the two
# cannot drift: iOS restores Apple subscriptions, Android restores Google Play subscriptions, and
# the web platform has no store at all.
PLATFORM_STORE_PROVIDER: dict[DevicePlatform, StoreProvider] = {
    platform: StoreProvider(str(store)) for platform, store in PLATFORM_STORE.items()
}

# The surface gate is a routing rejection, not a restore internal result: it has no
# `core.auth_event_result` value of its own, so it enters no entry of restore's client error
# mapping table and leaves that table's exhaustiveness untouched.
SURFACE_GATE_RESULTS: frozenset[AuthEventResult] = frozenset()


def native_only_surface_gate(platform: DevicePlatform,
                             *,
                             artifact_family: str | None = None,
                             store_artifact: str | None = None) -> StoreProvider:
    """`restore_subscription` is reachable from the iOS and Android apps only, with the store fixed
    by the calling platform.

    A web call, or any call presenting no native store-artifact family, is rejected with
    `operation_not_allowed` rather than `proof_rejected`: there is no proof to evaluate, not a
    failed one. One store's artifact presented from the other platform is rejected the same way,
    with the same code, deterministically — cross-store restore is out of scope.
    """
    # [impl->req~restore-native-only-surface-gate~1]
    if SURFACE_GATE_RESULTS:
        raise RestoreContractError("the surface gate is no restore internal result")
    expected = NATIVE_STORE_ARTIFACTS.get(platform)
    store = PLATFORM_STORE_PROVIDER.get(platform)
    if expected is None or store is None:
        raise RestoreRejected(f"restore_subscription is not reachable from {platform}")
    if artifact_family is not None and artifact_family != expected:
        raise RestoreRejected(f"{platform} presents {expected}, never {artifact_family}")
    if not store_artifact or not str(store_artifact).strip():
        raise RestoreRejected("restore presented no native store-artifact family")
    return store


# --- The request material ------------------------------------------------------------------------

# Non-store proof material a request might try to substitute for the store artifact. None of it is
# required or accepted on this endpoint.
NON_STORE_PROOF_FIELDS: frozenset[str] = frozenset({
    "app_attest_attestation", "app_attest_assertion", "attestation", "attestation_object",
    "play_integrity_token", "integrity_token", "device_check_token", "devicecheck_token",
    "safetynet_token", "turnstile_token", "webauthn_assertion",
})

# Prior-account recovery credentials that would authorize or parameterize restore. No such
# credential exists: restore is authorized by the verified ID token together with server-verifiable
# store proof, and by nothing else.
RESTORE_RECOVERY_CREDENTIALS: frozenset[str] = frozenset()
RESTORE_AUTHORIZERS: tuple[str, ...] = ("backend_verified_id_token", "store_restore_proof")


def require_store_proof(platform: DevicePlatform, body: Mapping[str, Any] | None) -> str:
    """`restore_proof` is required, and it is the store artifact alone: the signed StoreKit
    transaction on iOS or the Google Play purchase token on Android. No App Attest or Play
    Integrity proof is required or accepted on this endpoint, and no such material stands in for
    server-verifiable store proof."""
    # [impl->req~restore-request-proof-store-artifact-only~1]
    # [impl->req~restore-single-audit-row-per-attempt~1]
    fields = dict(body or {})
    artifact = fields.get("restore_proof")
    native_only_surface_gate(platform,
                             artifact_family=fields.get("store_artifact_family"),
                             store_artifact=artifact if isinstance(artifact, str) else None)
    substituted = sorted(set(fields) & NON_STORE_PROOF_FIELDS)
    if substituted:
        raise RestoreRejection(AuthEventResult.invalid_restore_proof,
                               f"restore requires and accepts no {substituted}")
    return str(artifact)


def assert_no_recovery_credential(body: Mapping[str, Any] | None = None,
                                  *, authorizers: Iterable[str] | None = None) -> tuple[str, ...]:
    """No prior-account recovery credential of any kind authorizes restore or parameterizes its
    behaviour; no such restore credential exists."""
    # [impl->req~restore-no-prior-account-recovery-credential~1]
    if RESTORE_RECOVERY_CREDENTIALS:
        raise RestoreContractError("no prior-account restore recovery credential exists")
    presented = sorted(set(body or {}) & RESTORE_RECOVERY_CREDENTIALS)
    if presented:
        raise RestoreContractError(f"{presented} does not authorize restore")
    offered = tuple(authorizers) if authorizers is not None else RESTORE_AUTHORIZERS
    if tuple(sorted(offered)) != tuple(sorted(RESTORE_AUTHORIZERS)):
        raise RestoreContractError(f"restore is authorized by {RESTORE_AUTHORIZERS} alone")
    return RESTORE_AUTHORIZERS


# --- Not challenge-bearing -----------------------------------------------------------------------

# The rows, phases and signals a challenge-bearing operation carries, and which restore has none
# of: no prepare phase, no `challenge=true` mode signal, no operation variant, no
# `core.auth_challenges` row.
RESTORE_CHALLENGE_ROWS: int = 0


def assert_restore_not_challenge_bearing(*,
                                         prepare_phase: bool = False,
                                         mode_signal: str | None = None,
                                         declared_variant: str | None = None,
                                         challenge_row_id: UUID | None = None) -> None:
    """`restore_subscription` is a canonical state-changing auth operation and is not
    challenge-bearing: a single call with no prepare phase, no mode signal, no operation variant
    and no `core.auth_challenges` row. The store artifact is its only proof."""
    # [impl->req~restore-not-challenge-bearing~1]
    # [impl->req~restore-proof-no-challenge-binding~2]
    operation = AuthOperation.restore_subscription
    if operation in CHALLENGE_BEARING_OPERATIONS or supports_prepare(operation):
        raise RestoreContractError("restore_subscription is not challenge-bearing")
    if RESTORE_CHALLENGE_ROWS:
        raise RestoreContractError("restore writes no core.auth_challenges row")
    if prepare_phase or mode_signal is not None or challenge_row_id is not None:
        raise RestoreContractError("restore is a single call with no prepare phase")
    # An operation with no variants accepts none; the inventory is what refuses a declared one.
    normalize_variant(operation, declared_variant)


# --- The registered destination ------------------------------------------------------------------

# No identity-kind field exists or is added: every anonymous-source and anonymous-destination rule
# keys off the absence of provider-bearing `core.external_identities` rows.
IDENTITY_KIND_FIELDS: frozenset[str] = frozenset()

# The remediation for an anonymous destination: complete registration, then retry restore.
REGISTRATION_REMEDIATIONS: tuple[tuple[str, str], ...] = (
    ("POST", "/auth/upgrade-anonymous"),
    ("POST", "/auth/create-user"),
)

# Registration itself reserves nothing: no path parks or tentatively moves the subscription for a
# destination that is not registered yet.
REGISTRATION_SUBSCRIPTION_RESERVATIONS: frozenset[str] = frozenset()


def provider_bearing_rows(rows: Sequence[ExternalIdentityRow]
                          ) -> tuple[ExternalIdentityRow, ...]:
    """The account's provider-bearing identity rows: those whose stored `provider` is `google` or
    `apple`."""
    # [impl->req~restore-anonymous-account-definition~1]
    return tuple(row for row in rows if row.provider in REGISTERED_PROVIDERS)


def is_anonymous_account(rows: Sequence[ExternalIdentityRow]) -> bool:
    """An account is anonymous exactly when it has zero provider-bearing rows in
    `core.external_identities`. There is no identity-kind field to consult."""
    # [impl->req~restore-anonymous-account-definition~1]
    if IDENTITY_KIND_FIELDS:
        raise RestoreContractError("no identity-kind field exists; the absence is the definition")
    return not provider_bearing_rows(rows)


def anonymous_own_identity_row(rows: Sequence[ExternalIdentityRow]) -> ExternalIdentityRow | None:
    """An anonymous account holds its own provider-less identity row — `provider = 'anonymous'`
    with a `NULL` `provider_uid` — because every account is created atomically with its
    `core.external_identities` row. An account with zero rows altogether is the exceptional case
    noted for the record; it is still anonymous by the same keying rule."""
    # [impl->req~restore-anonymous-account-definition~1]
    for row in rows:
        if row.provider is IdentityProvider.anonymous:
            assert_provider_uid_check(row.provider, row.provider_uid)
            return row
    return None


def registration_remediation_routes() -> tuple[tuple[str, str], ...]:
    """The two remediations, and only these: the in-place `POST /auth/upgrade-anonymous` flip, or
    registered `POST /auth/create-user` where no existing anonymous user is being upgraded. Both
    are canonical operations, and restore is retried afterwards rather than resumed."""
    # [impl->req~restore-destination-must-be-registered~1]
    for method, path in REGISTRATION_REMEDIATIONS:
        if match_operation(method, path) is None:
            raise RestoreContractError(f"{method} {path} is no canonical remediation")
    return REGISTRATION_REMEDIATIONS


def assert_registered_destination(*,
                                  destination_user_id: UUID,
                                  identity_rows: Sequence[ExternalIdentityRow],
                                  destination_active: bool = True,
                                  mutations_performed: Iterable[str] = (),
                                  client_declared_registered: bool | None = None) -> UUID:
    """Restore requires a registered destination: an active, registered account.

    An anonymous-destination attempt is audited as `restore_destination_anonymous` and rejected
    before any ownership, grant or cap change. The backend enforces this from stored identity
    state, never from anything the client declares, so an old or modified client cannot bypass it.
    """
    # [impl->req~restore-destination-must-be-registered~1]
    # [impl->req~restore-endpoint-operation-and-branch-selection~1]
    if client_declared_registered is not None:
        raise RestoreContractError("the backend reads stored identity state, not client claims")
    if REGISTRATION_SUBSCRIPTION_RESERVATIONS:
        raise RestoreContractError("registration reserves no subscription")
    if is_anonymous_account(identity_rows):
        changed = sorted(mutations_performed)
        if changed:
            raise RestoreContractError(
                f"an anonymous destination is rejected before {changed}")
        raise RestoreRejection(AuthEventResult.restore_destination_anonymous,
                               "restore requires a registered destination")
    if not destination_active:
        raise RestoreRejection(AuthEventResult.blocked_user,
                               "the destination must be an active account")
    return destination_user_id


def restore_destination(context: VerifiedIdentityContext,
                        *,
                        barrier_admitted: bool,
                        restore_logic_started: bool = False) -> UUID:
    """The destination of any restore is the current authenticated user, resolved from the
    client's Firebase ID token — cryptographically verified by the backend under the shared
    per-request authentication-and-identity-resolution contract before any restore logic runs, and
    resolving to a linked identity."""
    # [impl->req~restore-request-firebase-id-token~1]
    # [impl->req~restore-endpoint-operation-and-branch-selection~1]
    if restore_logic_started or not barrier_admitted:
        raise RestoreContractError("the barrier verifies the ID token before any restore logic")
    if context.outcome is not ResolutionOutcome.linked or context.user_id is None:
        raise RestoreContractError(
            f"{context.outcome} never reaches restore; the barrier decides it")
    return context.user_id


# --- The single audit row an attempt owes --------------------------------------------------------

class RestoreBranch(StrEnum):
    """The two server-determined branches."""
    same_account = "same_account"
    adoption = "adoption"


class MovementClassification(StrEnum):
    """What `audit.auth_events.details` records about the attempt's movement."""
    same_account = "same_account"
    adoption = "adoption"
    unclassified = "unclassified"


# Outcomes that record `unclassified` even where a branch had been determined: the locked-phase
# owner disagreement, the locked-phase divergence from the pre-transaction determination, and the
# already-linked rejection, which performs and classifies no movement.
UNCLASSIFIED_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.restore_subscription_grant_owner_mismatch,
    AuthEventResult.restore_branch_inconsistent,
    AuthEventResult.store_transaction_already_linked,
})


def movement_classification_for(*,
                                branch: RestoreBranch | None,
                                result: AuthEventResult) -> MovementClassification:
    """Attempts whose branch is known record `same_account` or `adoption`; attempts that fail
    before the branch is knowable, or that are rejected in the locked phase on owner disagreement
    or outcome divergence, record `unclassified`."""
    # [impl->req~restore-single-audit-row-per-attempt~1]
    if branch is None or result in UNCLASSIFIED_RESULTS:
        return MovementClassification.unclassified
    return MovementClassification(str(branch))


def restore_admission_rejection_is_audited(rejection: AdmissionRejection) -> bool:
    """A request stopped earlier by backend restore admission control follows the shared
    admission-control carve-out: it never reaches the audited attempt path, so it owes no
    `audit.auth_events` row."""
    # [impl->req~restore-single-audit-row-per-attempt~1]
    return not is_admission_phase(rejection)


@dataclass(frozen=True, slots=True)
class RestoreAuditContext:
    """The non-secret context a restore attempt's one row carries.

    `expired_grants` names every grant the mutation expired together with the reason code it
    carried, so no expiry made to clear the one-active-grant index is a silent side effect.
    """
    subscription_id: UUID | None = None
    access_grant_id: UUID | None = None
    store_purchase_id: UUID | None = None
    source_user_id: UUID | None = None
    destination_user_id: UUID | None = None
    expired_grants: tuple[Mapping[str, Any], ...] = ()
    proof_fingerprints: tuple[str, ...] = ()
    store_state_verification: str | None = None


class RestoreAttemptAudit:
    """One restore attempt's audit obligation: exactly one `audit.auth_events` row, written in the
    same transaction as any restore mutation, or in its own rejection transaction where the attempt
    is rejected before that transaction is entered.

    Restore enters the audited attempt path at the route match, so every attempt owes the row —
    successful or rejected, same-account, adoption, barrier-rejected, or rejected before the branch
    was determined.
    """

    def __init__(self) -> None:
        self._rows: list[AuthEvent] = []

    @property
    def rows(self) -> tuple[AuthEvent, ...]:
        return tuple(self._rows)

    def record(self, *,
               phase: AttemptPhase,
               result: AuthEventResult,
               audit_transaction: object,
               branch: RestoreBranch | None = None,
               mutation_transaction: object | None = None,
               actor: AuthActor = NO_ACTOR,
               context: RestoreAuditContext | None = None,
               challenge_row_id: UUID | None = None) -> AuthEvent:
        """Write the attempt's one row and return it."""
        # [impl->req~restore-single-audit-row-per-attempt~1]
        # [impl->req~restore-not-challenge-bearing~1]
        if self._rows:
            raise RestoreContractError("one restore attempt writes one audit row")
        if challenge_row_id is not None:
            raise RestoreContractError("restore consumes no challenge, so it names no row")
        if mutation_transaction is not None and mutation_transaction is not audit_transaction:
            raise RestoreContractError(
                "the row is written in the same transaction as the restore mutation")
        if mutation_transaction is None and audit_transaction is None:
            raise RestoreContractError("a rejected attempt writes its row in its own transaction")
        held = context or RestoreAuditContext()
        classification = movement_classification_for(branch=branch, result=result)
        event = terminal_event(phase, result,
                               operation=AuthOperation.restore_subscription,
                               actor=actor,
                               details=movement_details(
                                   movement_classification=str(classification),
                                   source_user_id=held.source_user_id,
                                   destination_user_id=held.destination_user_id,
                                   subscription_id=held.subscription_id,
                                   access_grant_id=held.access_grant_id,
                                   store_purchase_id=held.store_purchase_id,
                                   # [impl->req~restore-grant-mutation-ordering~1]
                                   expired_grants=[dict(expiry)
                                                   for expiry in held.expired_grants],
                                   proof_fingerprints=list(held.proof_fingerprints),
                                   store_state_verification=held.store_state_verification))
        self._rows.append(event)
        return event
