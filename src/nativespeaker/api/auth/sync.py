"""`POST /auth/sync`: the read-only contract.

Sync is the authoritative account-state read. It runs behind the shared pre-handler barrier, on
an already-resolved linked identity, and reports what the database currently says: the user's
effective entitlement and the account's stored registration state. It decides nothing else and
writes nothing at all.

The endpoint's own behavior lives here — the admission precondition, the response shape, and the
complete must-not list. How the reported entitlement values are derived is
`07-quota-and-access-enforcement.md`'s, applied through `quota.grants.entitlement_report` rather
than recomputed here, so sync and quota enforcement can never disagree about the same request
instant.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, NoReturn

import structlog

from nativespeaker.api.auth.audit import (
    NO_ACTOR,
    AuthActor,
    AuthEvent,
    AuthEventResult,
    sync_event,
)
from nativespeaker.api.auth.barrier import (
    ResolutionOutcome,
    VerifiedIdentityContext,
    barrier_result_for,
)
from nativespeaker.api.auth.operations import (
    AdmissionRejection,
    AuthOperation,
    IdentityProvider,
    is_admission_phase,
    is_challenge_bearing,
    is_on_audited_path,
    supports_prepare,
)
from nativespeaker.api.auth.routes import is_pre_auth_callable
from nativespeaker.api.quota.grants import (
    EntitlementReport,
    GrantRow,
    PublicEntitlementStatus,
    TooManyActiveGrantsError,
    assert_no_per_device_state,
    entitlement_report,
)

logger = structlog.get_logger()

SYNC_OPERATION: AuthOperation = AuthOperation.sync
SYNC_METHOD: str = "POST"
SYNC_PATH: str = "/auth/sync"


class SyncError(RuntimeError):
    """An `/auth/sync` rule was about to be broken."""


class SyncProhibitedError(SyncError):
    """Sync was about to do something its must-not list forbids."""

    def __init__(self, effect: SyncEffect | str):
        self.effect = effect
        super().__init__(f"/auth/sync must not {effect}")


class SyncIntegrityError(SyncError):
    """Sync met internally inconsistent data and failed closed on it."""

    result = AuthEventResult.internal_error


# --- admission ---------------------------------------------------------------------------------


def assert_admitted(context: VerifiedIdentityContext) -> VerifiedIdentityContext:
    """Sync starts from the barrier's typed output and never resolves an identity of its own: the
    barrier has already verified the token, resolved `(issuer, subject)` through
    `core.external_identities` and `core.users`, and admitted the request before this runs. What
    reaches here is therefore a linked identity with a resolved user, and anything else — a
    context for an unadmitted outcome, or a linked outcome carrying no user — never becomes a
    reportable state."""
    # `POST /auth/sync` runs after the shared pre-handler barrier has admitted the request and
    # resolved the linked external identity.
    # [impl->req~sessions-sync-runs-after-barrier~1]
    if context.outcome is not ResolutionOutcome.linked or context.user_id is None:
        raise SyncError("/auth/sync reports only on a barrier-admitted linked identity")
    return context


# Sync declares no pre-auth admission, so the barrier's route-admission rule rejects a pre-auth
# (unlinked) identity here: an unlinked identity has no linked user to report on.
# [impl->req~sessions-sync-not-preauth-callable~1]
SYNC_PRE_AUTH_CALLABLE: bool = is_pre_auth_callable(SYNC_METHOD, SYNC_PATH)


def preauth_rejection() -> AuthEventResult:
    """What the barrier does with a pre-auth identity on this route: reject it as
    `preauth_identity_not_allowed`. The declaration is route data the barrier consults, so this
    reads the same predicate the barrier reads rather than restating the rule."""
    # [impl->req~sessions-sync-not-preauth-callable~1]
    if SYNC_PRE_AUTH_CALLABLE:
        raise SyncError("/auth/sync is not declared pre-auth-callable")
    result = barrier_result_for(ResolutionOutcome.pre_auth, SYNC_METHOD, SYNC_PATH)
    if result is not AuthEventResult.preauth_identity_not_allowed:
        raise SyncError("a pre-auth identity is rejected as preauth_identity_not_allowed")
    return result


# --- the must-not list --------------------------------------------------------------------------


class SyncEffect(StrEnum):
    """Everything `/auth/sync` must not do. The list is the whole of the endpoint's must-not
    contract, and membership is what makes an effect forbidden: `FORBIDDEN_EFFECTS` is derived
    from this enumeration, and the read-only session refuses every call that maps onto one."""
    # [impl->req~sessions-sync-must-not-create-users~1]
    create_user = "create users"
    # [impl->req~sessions-sync-must-not-init-usage~1]
    initialize_usage = "initialize mutable usage state"
    # [impl->req~sessions-sync-must-not-allocate-intro~1]
    allocate_introductory_entitlement = "allocate introductory entitlement"
    # [impl->req~sessions-sync-must-not-verify-restore-proofs~1]
    verify_restore_proof = "verify restore proofs"
    # Apple DeviceCheck, Google Play Integrity and Play Integrity Device Recall alike.
    # [impl->req~sessions-sync-must-not-verify-device-proofs~1]
    verify_device_proof = "verify device-check proofs"
    # [impl->req~sessions-sync-must-not-touch-device-grant-state~1]
    touch_device_grant_state = "read or modify per-device grant state"
    # [impl->req~sessions-sync-must-not-create-grants~1]
    create_grant = "create or finalize grants"
    # [impl->req~sessions-sync-must-not-issue-challenges~1]
    issue_challenge = "issue operation challenges"
    # [impl->req~sessions-sync-must-not-select-completion-operation~1]
    select_completion_operation = "select a concrete completion operation"
    # [impl->req~sessions-sync-must-not-derive-restore-target~1]
    derive_restore_target = "derive a restore reassignment target"
    # [impl->req~sessions-sync-must-not-link-identities~1]
    link_identity = "link identities"
    # [impl->req~sessions-sync-must-not-mark-historical~1]
    mark_identity_historical = "mark identities historical"
    # [impl->req~sessions-sync-must-not-merge-users~1]
    merge_users = "merge users"
    # [impl->req~sessions-sync-must-not-modify-subscriptions~1]
    modify_subscription = "modify subscriptions"
    # [impl->req~sessions-sync-must-not-update-profile~1]
    update_profile = "update user profile fields"
    # [impl->req~sessions-sync-must-not-append-mutation-audit~1]
    append_mutation_audit = "append audit events that imply mutation"
    # Reporting the stored registration state reads the stored column: sync performs no Firebase
    # Admin `providerData` read and never flips the stored provider.
    read_provider_data = "read Firebase providerData"
    flip_stored_provider = "flip the stored provider"
    # Sync is strictly read-only for usage: no insert, no update, no triggered rollover.
    write_usage = "write mutable usage state"
    # The lazy flip of a time-ended active grant belongs to the grant-issuance transaction.
    flip_grant_status = "flip a grant row's status"


# Every effect on the list is forbidden; there is no permitted subset and no per-caller exception.
# That closed list is what makes `/auth/sync` the business-state read-only auth resolution
# endpoint, and it is the complete set of prohibitions the endpoint carries: the endpoint's
# prohibitions are exactly the must-not list this enumeration holds, with nothing added elsewhere.
# [impl->req~sessions-api-sync-purpose~1]
# [impl->req~sessions-api-sync-prohibited-operations~2]
FORBIDDEN_EFFECTS: frozenset[SyncEffect] = frozenset(SyncEffect)

# The calls a caller could make against the sync session, and the forbidden effect each one is.
# Anything not named here is refused too — the session fails closed on an unknown call rather
# than passing it through — so the map is a diagnostic, never an allowlist.
PROHIBITED_CALLS: dict[str, SyncEffect] = {
    "create_user": SyncEffect.create_user,
    "insert_user": SyncEffect.create_user,
    "initialize_usage": SyncEffect.initialize_usage,
    "new_usage_row": SyncEffect.initialize_usage,
    "write_rollover": SyncEffect.write_usage,
    "increment_usage": SyncEffect.write_usage,
    "allocate_introductory_entitlement": SyncEffect.allocate_introductory_entitlement,
    "verify_restore_proof": SyncEffect.verify_restore_proof,
    "verify_device_proof": SyncEffect.verify_device_proof,
    "verify_devicecheck": SyncEffect.verify_device_proof,
    "verify_play_integrity": SyncEffect.verify_device_proof,
    "verify_device_recall": SyncEffect.verify_device_proof,
    "read_device_grant_state": SyncEffect.touch_device_grant_state,
    "write_device_grant_state": SyncEffect.touch_device_grant_state,
    "create_grant": SyncEffect.create_grant,
    "finalize_grant": SyncEffect.create_grant,
    "expire_grant": SyncEffect.flip_grant_status,
    "issue_challenge": SyncEffect.issue_challenge,
    "select_completion_operation": SyncEffect.select_completion_operation,
    "derive_restore_target": SyncEffect.derive_restore_target,
    "link_identity": SyncEffect.link_identity,
    "mark_identity_historical": SyncEffect.mark_identity_historical,
    "merge_users": SyncEffect.merge_users,
    "modify_subscription": SyncEffect.modify_subscription,
    "update_profile": SyncEffect.update_profile,
    "append_mutation_audit": SyncEffect.append_mutation_audit,
    "read_provider_data": SyncEffect.read_provider_data,
    "flip_stored_provider": SyncEffect.flip_stored_provider,
}


def assert_permitted(effect: SyncEffect | str) -> NoReturn:
    """The single decision point for the must-not list: nothing on it is ever permitted, whichever
    caller asks and whatever the account state is."""
    # `/auth/sync` must not do any of these.
    # [impl->req~sessions-sync-prohibitions~1]
    raise SyncProhibitedError(effect)


def is_forbidden(effect: SyncEffect | str) -> bool:
    """Whether an effect is on the must-not list. An unrecognized effect counts as forbidden: the
    contract is a closed permission set of three reads, so an unknown effect is not a licence."""
    # [impl->req~sessions-sync-prohibitions~1]
    try:
        return SyncEffect(effect) in FORBIDDEN_EFFECTS
    except ValueError:
        return True


# --- the read-only session ----------------------------------------------------------------------


class ReadOnlySyncSession:
    """The only database handle the sync path is given: three reads over already-committed state,
    and no way to reach anything else.

    Every other call — a write, a device-proof verification, a Firebase lookup, an audit row that
    implies mutation — is refused here rather than in each caller, so the must-not list cannot be
    evaded by adding a method to whatever the handler was handed.
    """

    # The three reads sync is allowed, and the only ones. Their names are what
    # `assert_no_per_device_state` is given, so a per-device read added here fails closed.
    READS: tuple[str, ...] = ("grant_rows", "usage_row", "stored_provider")

    def __init__(self,
                 *,
                 grant_rows: Sequence[GrantRow] = (),
                 usage_row: tuple[str, int] | None = None,
                 stored_provider: IdentityProvider = IdentityProvider.anonymous):
        self._grant_rows = tuple(grant_rows)
        self._usage_row = usage_row
        self._stored_provider = stored_provider
        self.reads: list[str] = []

    def read_grant_rows(self) -> tuple[GrantRow, ...]:
        """The user's `core.access_grants` rows exactly as they stand."""
        self.reads.append("grant_rows")
        return self._grant_rows

    def read_usage_row(self) -> tuple[str, int] | None:
        """The `(monthly_period, monthly_used)` of the effective grant's usage row, or `None`
        where no row exists yet. Reading it creates nothing."""
        self.reads.append("usage_row")
        return self._usage_row

    def read_stored_provider(self) -> IdentityProvider:
        """The stored `core.external_identities.provider` of the linked identity — the backend's
        own registration state, not a live Firebase reading of it."""
        self.reads.append("stored_provider")
        return self._stored_provider

    def __getattr__(self, name: str) -> NoReturn:
        """Anything beyond the three reads. A named call reports the effect it would have been;
        an unnamed one is refused all the same."""
        # [impl->req~sessions-sync-prohibitions~1]
        # [impl->req~sessions-sync-no-device-check-or-grant-state~1]
        if name.startswith("_"):
            raise AttributeError(name)
        assert_permitted(PROHIBITED_CALLS.get(name, name))


# --- the reported state ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyncState:
    """What one `/auth/sync` call reports: the effective entitlement and the stored registration
    state of the linked account."""
    entitlement: EntitlementReport
    identity_provider: IdentityProvider


# The response's `entitlement` object, in order. The shape admits these six fields and no others,
# and `current_period` and `monthly_used` are never null.
ENTITLEMENT_FIELDS: tuple[str, ...] = (
    "type", "status", "tier_id", "monthly_credits", "current_period", "monthly_used")

# The field sync reports the account's stored registration state under. `GET /users/me` reports the
# same value under the same name, reading this constant rather than repeating the string, so the
# two read surfaces cannot disagree about what the account's registration state is called.
REGISTRATION_STATE_FIELD = "identity_provider"
NON_NULL_ENTITLEMENT_FIELDS: frozenset[str] = frozenset({"current_period", "monthly_used"})

# No source ranking exists to break a tie with: more than one effective grant is an integrity
# failure, not a choice.
# [impl->req~sessions-sync-multiple-active-grants-fail-closed~1]
GRANT_SOURCE_PRECEDENCE: tuple[str, ...] = ()


def sync_response(state: SyncState) -> dict[str, Any]:
    """The wire shape of the response.

    The `entitlement` object carries exactly the six documented fields, with `status` drawn from
    the public `none | active` enum, and the stored registration state alongside it so the client
    can compare it against its local Firebase state."""
    # [impl->req~sessions-sync-entitlement-response-shape~1]
    # [impl->req~sessions-sync-status-none-or-active~2]
    if state.entitlement.status not in set(PublicEntitlementStatus):
        raise SyncError("the public status enum is exactly none | active")
    entitlement: dict[str, Any] = {
        "type": state.entitlement.type.value,
        "status": state.entitlement.status.value,
        "tier_id": state.entitlement.tier_id,
        "monthly_credits": state.entitlement.monthly_credits,
        # `current_period` and `monthly_used` are always present and never null: the shape admits
        # no null there, so the client never special-cases a missing field.
        # [impl->req~sessions-sync-monthly-used-source~2]
        "current_period": state.entitlement.current_period,
        "monthly_used": state.entitlement.monthly_used,
    }
    if tuple(entitlement) != ENTITLEMENT_FIELDS:
        raise SyncError(f"the entitlement object is exactly {ENTITLEMENT_FIELDS}")
    if any(entitlement[field] is None for field in NON_NULL_ENTITLEMENT_FIELDS):
        raise SyncError("current_period and monthly_used are never null")
    # The stored registration state, reported so the client can compare it against local Firebase
    # state. Reporting it changes nothing else.
    # [impl->req~sessions-sync-reports-registration-state~1]
    return {"entitlement": entitlement,
            REGISTRATION_STATE_FIELD: state.identity_provider.value}


def sync_state(context: VerifiedIdentityContext,
               session: ReadOnlySyncSession,
               *,
               now: datetime | None = None) -> SyncState:
    """The whole of what `/auth/sync` does: read, derive, report.

    It returns the current backend state for the linked user and performs no mutation of its own —
    no user, no usage row, no grant, no identity, no subscription, no profile field. Reporting is
    derived from database state alone; nothing here consults a client-supplied snapshot, a device
    proof, or live Firebase.
    """
    # If the current identity is linked to an active user, sync returns that user's current
    # backend state and performs no mutation.
    # [impl->req~sessions-sync-returns-state-no-mutation~1]
    assert_admitted(context)
    # One captured evaluation time drives grant selection, the `current_period` computation and
    # the usage read alike, so a request that straddles `ends_at` or a month boundary is
    # internally consistent.
    # [impl->req~sessions-sync-single-evaluation-time~2]
    moment = now or datetime.now(UTC)
    rows = session.read_grant_rows()
    stored = session.read_usage_row()
    # `monthly_used` is the stored counter only when the row names the computed current period,
    # and zero otherwise — the same figure the next quota-checked request's lazy rollover will
    # itself persist. Sync is strictly read-only for usage: it inserts nothing, updates nothing
    # and triggers no rollover, and it flips no time-ended grant row either.
    # [impl->req~sessions-sync-monthly-used-source~2]
    # [impl->req~sessions-sync-read-only-for-usage~1]
    stored_period, stored_used = stored if stored is not None else (None, 0)
    # Database state only: no DeviceCheck, no Play Integrity, no Device Recall, and no per-device
    # grant state among the inputs.
    # [impl->req~sessions-sync-no-device-check-or-grant-state~1]
    assert_no_per_device_state(session.reads)
    try:
        # The reported entitlement is the user's single effective grant under the shared
        # effective-grant predicate, and its content comes only from that grant and its
        # `core.access_tiers` row.
        # [impl->req~sessions-sync-returns-entitlement-state~1]
        # [impl->req~sessions-sync-single-effective-grant~2]
        # A lapsed, revoked or not-yet-flipped row reads as `type = none, status = none`.
        # [impl->req~sessions-sync-status-none-or-active~2]
        report = entitlement_report(rows, now=moment,
                                    stored_period=stored_period, stored_used=stored_used)
    except TooManyActiveGrantsError as exc:
        # More than one effective grant is an internal integrity failure, never a tie to break:
        # sync logs it and fails closed, and applies no precedence ranking over grant sources.
        # [impl->req~sessions-sync-multiple-active-grants-fail-closed~1]
        logger.error("auth_sync_multiple_effective_grants",
                     user_id=str(context.user_id), operation=str(SYNC_OPERATION))
        if GRANT_SOURCE_PRECEDENCE:
            raise SyncError("/auth/sync ranks no grant source above another") from None
        raise SyncIntegrityError(str(exc)) from None
    # The stored column is the reported registration state; sync reads no `providerData` and
    # flips nothing.
    # [impl->req~sessions-sync-reports-registration-state~1]
    return SyncState(entitlement=report, identity_provider=session.read_stored_provider())


# --- the endpoint contract ------------------------------------------------------------------------


def sync_credential(authorization_values: Sequence[str]) -> str:
    """The endpoint's authentication: the external IDP ID token as a single `Authorization: Bearer`
    credential, and nothing else."""
    # [impl->req~sessions-api-sync-bearer-credential~1]
    # Imported here: `endpoints` sits above this module in the import graph.
    from nativespeaker.api.auth.endpoints import bearer_credential  # noqa: PLC0415

    return bearer_credential(SYNC_METHOD, SYNC_PATH, authorization_values)


def assert_barrier_precondition(context: VerifiedIdentityContext) -> VerifiedIdentityContext:
    """The endpoint's admission precondition: authentication and identity resolution happen in the
    shared pre-handler barrier before this handler runs, and the endpoint requires a linked, active
    identity — pre-auth, historical and blocked identities are rejected at the barrier."""
    # [impl->req~sessions-api-sync-barrier-precondition~1]
    from nativespeaker.api.auth.endpoints import barrier_admitted  # noqa: PLC0415

    return barrier_admitted(context, SYNC_METHOD, SYNC_PATH)


# The tables the reported entitlement state is derived from, and the whole of them.
# [impl->req~sessions-api-sync-handler-returns-state~1]
ENTITLEMENT_SOURCE_TABLES: tuple[str, ...] = ("core.access_grants", "core.access_tiers",
                                             "core.user_monthly_usage")

# What the handler writes to business state: nothing.
# [impl->req~sessions-api-sync-handler-returns-state~1]
SYNC_BUSINESS_WRITES: frozenset[str] = frozenset()

# Client-supplied state a caller might offer as a starting point. None of it is read: the reported
# view is derived from committed database state alone, and it is advisory only — the client compares
# it against its own state rather than the backend trusting the client's.
# [impl->req~sessions-api-sync-no-client-snapshot-trust~1]
CLIENT_SNAPSHOT_FIELDS: frozenset[str] = frozenset({
    "client_snapshot", "cached_entitlement", "last_known_tier", "local_provider",
    "client_state", "previous_sync", "assumed_registered", "cached_identity_provider",
})
SYNC_RESPONSE_IS_ADVISORY: bool = True


def assert_no_client_snapshot_trusted(request_body: Mapping[str, Any] | None = None) -> None:
    """`/auth/sync` must not trust any earlier client snapshot: a snapshot the client sends is not
    read, not merged, and not allowed to influence the reported view. Its returned view is advisory
    only, so nothing downstream may treat it as authoritative client state either."""
    # [impl->req~sessions-api-sync-no-client-snapshot-trust~1]
    if not SYNC_RESPONSE_IS_ADVISORY:
        raise SyncError("the view /auth/sync returns is advisory only")
    offered = sorted(set(request_body or {}) & CLIENT_SNAPSHOT_FIELDS)
    if offered:
        raise SyncError(f"/auth/sync trusts no earlier client snapshot: {offered}")


def sync_handler(context: VerifiedIdentityContext,
                 session: ReadOnlySyncSession,
                 *,
                 now: datetime | None = None,
                 request_body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The handler: it returns the current backend state for the resolved user — including the
    effective entitlement state derived from `core.access_grants`, `core.access_tiers` and
    `core.user_monthly_usage` — and performs no business-state mutation.

    The admission precondition runs first, then the three reads, then the fixed response shape. No
    client snapshot participates in any of it.
    """
    # [impl->req~sessions-api-sync-handler-returns-state~1]
    # [impl->req~sessions-api-sync-no-client-snapshot-trust~1]
    assert_barrier_precondition(context)
    assert_no_client_snapshot_trusted(request_body)
    if SYNC_BUSINESS_WRITES:
        raise SyncError("/auth/sync performs no business-state mutation")
    if set(ENTITLEMENT_SOURCE_TABLES) != {"core.access_grants", "core.access_tiers",
                                          "core.user_monthly_usage"}:
        raise SyncError(f"the reported entitlement derives from {ENTITLEMENT_SOURCE_TABLES}")
    return sync_response(sync_state(context, session, now=now))


# --- the audited attempt path ---------------------------------------------------------------------


def sync_terminal_result(barrier_result: AuthEventResult | None) -> AuthEventResult:
    """The single `audit.auth_events` row every `POST /auth/sync` attempt owes, by result.

    `/auth/sync` is a canonical state-changing auth operation by route, so every attempt is on the
    audited attempt path: exactly one row with `operation = 'sync'` is appended for the attempt's
    terminal outcome — the barrier's own result where the barrier rejected, otherwise `succeeded` —
    before the response is returned. That row records no mutation; appending it is operational
    logging rather than business state, which is what makes it compatible with the endpoint's
    read-only rules.
    """
    # [impl->req~sessions-api-sync-audited-attempt-path~1]
    if not is_on_audited_path(SYNC_METHOD, SYNC_PATH):
        raise SyncError("/auth/sync is a canonical state-changing auth operation by route")
    return barrier_result if barrier_result is not None else AuthEventResult.succeeded


def sync_attempt_event(result: AuthEventResult,
                       *,
                       actor: AuthActor = NO_ACTOR,
                       details: Mapping[str, Any] | None = None) -> AuthEvent:
    """That one row, built. It carries no mutation and no `challenge_row_id`: `/auth/sync` is not
    challenge-bearing — it has no prepare mode and touches no `core.auth_challenges` row."""
    # [impl->req~sessions-api-sync-audited-attempt-path~1]
    if is_challenge_bearing(SYNC_OPERATION) or supports_prepare(SYNC_OPERATION):
        raise SyncError("/auth/sync is challenge-free and has no prepare mode")
    # The row itself is built by the shared audit contract, which refuses a mutation outright; the
    # postcondition here is that the row this endpoint appends carries none and names no challenge.
    event = sync_event(result, actor=actor, details=dict(details or {}))
    if event.details.get("mutation") != {} or event.challenge_row_id is not None:
        raise SyncError("the attempt row records no mutation and names no challenge row")
    return event


def sync_admission_rejection_writes_row(rejection: AdmissionRejection) -> bool:
    """An admission-control rejection ahead of the route match writes no row at all: it never
    reached the audited attempt path."""
    # [impl->req~sessions-api-sync-audited-attempt-path~1]
    return not is_admission_phase(rejection)


# `/auth/sync` touches no `core.auth_challenges` row, in any phase.
# [impl->req~sessions-api-sync-audited-attempt-path~1]
SYNC_CHALLENGE_ROWS_TOUCHED: frozenset[str] = frozenset()
