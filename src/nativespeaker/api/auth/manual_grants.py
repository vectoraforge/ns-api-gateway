"""Operator-issued `manual` grants: the remediation procedure for a burned device slot.

This is not an endpoint. It is the procedure an operator runs — directly against the database or
through an internal, operator-authenticated action that runs the same steps — and everything it
may do is here: the eight ordered steps, the inputs it takes, the terms it derives rather than
accepts, and the revocation half that ends a grant early.

What it deliberately does not do is undo anything. The vendor bit that burned the slot stays
burned, the anti-abuse ledgers are untouched, and the grant this procedure inserts is what
compensates for the loss. Everything downstream then treats it as an ordinary grant: the shared
effective-grant predicate in `quota.grants` decides its currentness, `/auth/sync` reports it as
`type = manual`, and restore sees an active grant like any other.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import IdentityState
from nativespeaker.api.auth.invariants import assert_grant_columns_entitlement_only
from nativespeaker.api.auth.locks import LockingPath, LockLedger, lock_grant_set, takes_user_row_lock
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.registry_schema import RegistryError, manual_issuance_row
from nativespeaker.api.auth.routes import (
    AUTHENTICATED_ROUTES,
    PROVIDER_CALLBACK_ROUTES,
    PUBLIC_ROUTES,
)
from nativespeaker.api.auth.schema_invariants import assert_anti_abuse_pairing
from nativespeaker.api.quota.grants import (
    GrantRow,
    PublicEntitlementType,
    assert_billing_separation,
    is_effective,
)
from nativespeaker.api.quota.usage import NewUsageRow, new_usage_row


class ManualGrantError(RuntimeError):
    """A rule of the operator issuance procedure was about to be broken."""


class ManualIssuanceRefused(ManualGrantError):
    """The procedure refused to issue, creating nothing."""


# --- What a `manual` grant is for -------------------------------------------------------------

# The one purpose, and the one thing a slot-burning failure is remedied with. A `manual` grant
# repairs a documented lost claim and nothing else.
MANUAL_PURPOSE: str = "repair_documented_lost_claim"
MANUAL_REMEDIES: tuple[str, ...] = ("manual_grant",)

# What never happens to the vendor bit that burned the slot: it is not cleared, not reconciled
# from database state, and the slot never silently becomes re-usable.
VENDOR_BIT_CLEARERS: frozenset[str] = frozenset()
VENDOR_BIT_RECONCILERS: frozenset[str] = frozenset()
SLOT_REUSE_PATHS: frozenset[str] = frozenset()


def slot_burned(*, vendor_bit_set: bool, grant_activated: bool) -> bool:
    """Whether the device slot counts as consumed. The vendor bit for the grant class is the whole
    answer: from the moment it is set the slot is burned, even where the backend's own records show
    that no grant was ever activated. That divergence is the case a `manual` grant exists for."""
    # [impl->req~grants-manual-remediation-purpose~1]
    del grant_activated  # the backend's own record never un-burns the slot
    return vendor_bit_set


def manual_remedy_for_burned_slot(*, vendor_bit_set: bool,
                                  grant_activated: bool = False) -> tuple[str, ...]:
    """The remedies available for a burned slot: a `manual` grant, and nothing else. Clearing the
    bit, reconciling it against database state, and re-using the slot are all absent by
    construction, so no caller can reach for one."""
    # [impl->req~grants-manual-remediation-purpose~1]
    if VENDOR_BIT_CLEARERS or VENDOR_BIT_RECONCILERS or SLOT_REUSE_PATHS:
        raise ManualGrantError("a burned bit is never cleared, reconciled or silently re-used")
    if not slot_burned(vendor_bit_set=vendor_bit_set, grant_activated=grant_activated):
        raise ManualGrantError("no slot is burned, so there is nothing to remediate")
    return MANUAL_REMEDIES


# --- The issuance surface ----------------------------------------------------------------------


class IssuanceSurface(StrEnum):
    """Where an issuance may come from, and the surfaces it may never come from."""
    direct_database_procedure = "direct_database_procedure"
    operator_authenticated_internal_action = "operator_authenticated_internal_action"
    client_endpoint = "client_endpoint"
    support_facing_api = "support_facing_api"
    admin_ui = "admin_ui"
    other_web_surface = "other_web_surface"


OPERATOR_SURFACES: frozenset[IssuanceSurface] = frozenset({
    IssuanceSurface.direct_database_procedure,
    IssuanceSurface.operator_authenticated_internal_action,
})

# It is not a canonical state-changing auth operation: no operation names it, it appears in no
# route table, and it writes no `audit.auth_events` row.
MANUAL_ISSUANCE_OPERATIONS: frozenset[AuthOperation] = frozenset()
MANUAL_ISSUANCE_AUDIT_ROWS: int = 0
_ROUTE_MARKERS: tuple[str, ...] = ("manual", "grant-issuance", "issue-grant")


def assert_operator_only_surface(surface: IssuanceSurface) -> IssuanceSurface:
    """Issuance is performed by an operator: directly against the database under the procedure
    below, or through an internal, operator-authenticated action that runs that same procedure.
    Never a client-reachable endpoint, a support-facing API, an admin UI or any other web
    surface — and never a canonical state-changing auth operation either, so it appears in no
    route table and writes no `audit.auth_events` row."""
    # [impl->req~grants-manual-operator-only-surface~1]
    if surface not in OPERATOR_SURFACES:
        raise ManualGrantError(f"{surface} never issues a manual grant")
    if MANUAL_ISSUANCE_OPERATIONS or MANUAL_ISSUANCE_AUDIT_ROWS:
        raise ManualGrantError("manual issuance is no canonical state-changing auth operation")
    assert_no_issuance_route()
    return surface


def assert_no_issuance_route() -> None:
    """No registry entry exposes the procedure: not the public allowlist, not a provider-callback
    route, and not an authenticated route."""
    # [impl->req~grants-manual-operator-only-surface~1]
    paths = [path for _, path in PUBLIC_ROUTES]
    paths += [route.path for route in PROVIDER_CALLBACK_ROUTES]
    paths += [route.path for route in AUTHENTICATED_ROUTES]
    offending = sorted({path for path in paths
                        for marker in _ROUTE_MARKERS if marker in path.lower()})
    if offending:
        raise ManualGrantError(f"{offending} would make manual issuance client-reachable")


class OperatorAuth(StrEnum):
    """How the caller of an internal issuance action is authenticated."""
    shared_administrative_secret = "shared_administrative_secret"
    iam_bound_internal_route = "iam_bound_internal_route"
    ordinary_user_credentials = "ordinary_user_credentials"
    none = "none"


# Either of these is sufficient at this stage; a role-based access-control system is not required.
SUFFICIENT_OPERATOR_AUTH: frozenset[OperatorAuth] = frozenset({
    OperatorAuth.shared_administrative_secret,
    OperatorAuth.iam_bound_internal_route,
})
RBAC_REQUIRED: bool = False


def assert_operator_authenticated(auth: OperatorAuth) -> OperatorAuth:
    """A deployment whose operator authentication is not distinct from ordinary users must
    establish one before this procedure is callable."""
    # [impl->req~grants-manual-operator-auth-required~1]
    if RBAC_REQUIRED:
        raise ManualGrantError("a role-based access-control system is not required at this stage")
    if auth not in SUFFICIENT_OPERATOR_AUTH:
        raise ManualGrantError(
            f"{auth} is not distinct from ordinary users; establish operator authentication first")
    return auth


# No per-user or per-operator manual-grant rate cap exists in the backend: the callers are staff
# rather than the public.
MANUAL_GRANT_RATE_CAPS: frozenset[str] = frozenset()


def assert_no_manual_rate_cap(configured_entries: Iterable[str] = ()) -> None:
    """The backend enforces no manual-grant rate cap, per user or per operator."""
    # [impl->req~grants-manual-no-rate-cap~1]
    offending = sorted({name for name in configured_entries if "manual" in name.lower()})
    if offending or MANUAL_GRANT_RATE_CAPS:
        raise ManualGrantError(f"no manual-grant rate cap is enforced in the backend: {offending}")


# --- The issuance inputs ----------------------------------------------------------------------

# What the procedure derives and therefore never accepts, in every name it could arrive under.
DERIVED_NEVER_INPUT: frozenset[str] = frozenset({
    "tier", "tier_id", "credits", "credit_amount", "monthly_credits", "duration",
    "duration_days", "expiry", "expires_at", "ends_at", "starts_at", "status", "source"})


@dataclass(frozen=True, slots=True)
class ManualIssuanceRequest:
    """The whole issuance input: who it is for, which case it repairs, who issued it, and why."""
    user_id: UUID
    case_id: str
    operator: str
    reason: str


def issuance_inputs(payload: Mapping[str, Any]) -> ManualIssuanceRequest:
    """The issuance input is the target user, a unique support case identifier, the issuing
    operator's identity, and a reason or ticket reference. Tier, credit amount, duration and
    expiry are never inputs: the procedure derives them, so a payload offering one is refused
    rather than honored."""
    # [impl->req~grants-manual-issuance-inputs~1]
    offered = sorted(set(payload) & DERIVED_NEVER_INPUT)
    if offered:
        raise ManualGrantError(f"{offered} is derived by the procedure, never an input")
    user_id = payload.get("user_id")
    if not isinstance(user_id, UUID):
        raise ManualGrantError("the issuance names its target user")
    values = {name: payload.get(name) for name in ("case_id", "operator", "reason")}
    missing = sorted(name for name, value in values.items()
                     if not isinstance(value, str) or not value.strip())
    if missing:
        raise ManualGrantError(f"the issuance carries {missing}")
    return ManualIssuanceRequest(user_id=user_id,
                                 case_id=str(values["case_id"]),
                                 operator=str(values["operator"]),
                                 reason=str(values["reason"]))


# --- The terms the procedure derives ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LostClaim:
    """What the burned or lost claim would have activated: its free-grant source, the tier and
    monthly credits that source's claim configures, and the duration and lifecycle it would have
    run under. All of it is read from the claim being repaired, never chosen at issuance."""
    source: AccessGrantSource
    tier_id: str
    monthly_credits: int
    starts_at: datetime
    ends_at: datetime | None = None


FREE_CLAIM_SOURCES: frozenset[AccessGrantSource] = frozenset({
    AccessGrantSource.anonymous_device_grant,
    AccessGrantSource.registered_account_grant,
})


def derived_terms(lost: LostClaim) -> LostClaim:
    """The terms of the grant to insert, reproduced from the claim being repaired. There is no
    operator discretion over the amount or the expiry: this returns what the lost claim would have
    activated, and the insert has nowhere else to get those values from."""
    # [impl->req~grants-manual-step-06-insert-grant~1]
    if lost.source not in FREE_CLAIM_SOURCES:
        raise ManualGrantError(f"{lost.source} is no free-credit claim to repair")
    if not lost.tier_id or lost.monthly_credits <= 0:
        raise ManualGrantError("the repaired claim names its tier and monthly credits")
    return lost


# --- The procedure, in order ------------------------------------------------------------------


class ManualStep(StrEnum):
    """The eight steps of one issuance, in the one order they may run in."""
    resolve_case = "resolve_case"
    lock = "lock"
    refuse_blocked = "refuse_blocked"
    establish_eligibility = "establish_eligibility"
    one_active_grant = "one_active_grant"
    insert_grant = "insert_grant"
    record_issuance = "record_issuance"
    leave_vendor_state = "leave_vendor_state"


MANUAL_PROCEDURE_STEPS: tuple[ManualStep, ...] = tuple(ManualStep)


@dataclass(frozen=True, slots=True)
class ManualIssuance:
    """One issuance's result: the grant row, its usage row, and the `core.manual_grant_issuances`
    row that records it. `repeated` marks the result a retried issuance for an already-recorded
    case gets back."""
    grant: dict[str, Any]
    usage: NewUsageRow
    issuance: dict[str, Any]
    repeated: bool = False


class ManualGrantIssuance:
    """One run of the operator issuance procedure.

    Each step records itself and refuses to run out of order, twice, or without its predecessors,
    so the ordering the specification fixes is enforced where the steps are taken.
    """

    def __init__(self, request: ManualIssuanceRequest, *,
                 surface: IssuanceSurface = IssuanceSurface.direct_database_procedure,
                 operator_auth: OperatorAuth = OperatorAuth.shared_administrative_secret):
        self.request = request
        # The surface and the operator authentication are checked before any step runs.
        assert_operator_only_surface(surface)
        assert_operator_authenticated(operator_auth)
        assert_not_promotional(request.reason)
        self.steps: list[ManualStep] = []
        self.terms: LostClaim | None = None
        self.locks: LockLedger | None = None

    # --- ordering ---------------------------------------------------------------------------

    def _record(self, step: ManualStep) -> None:
        position = MANUAL_PROCEDURE_STEPS.index(step)
        if self.steps and position <= MANUAL_PROCEDURE_STEPS.index(self.steps[-1]):
            raise ManualGrantError(f"{step} cannot run after {self.steps[-1]}")
        self.steps.append(step)

    def _require(self, *steps: ManualStep) -> None:
        missing = [step for step in steps if step not in self.steps]
        if missing:
            raise ManualGrantError(f"{missing} must run first")

    # --- the steps --------------------------------------------------------------------------

    def resolve_case(self,
                     recorded: Mapping[str, ManualIssuance] | None = None) -> ManualIssuance | None:
        """1. Resolve the support case identifier. A case that already produced a grant returns
        that original result and issues nothing further, so a retried or repeated issuance for the
        same case never yields a second grant."""
        # [impl->req~grants-manual-step-01-resolve-case~1]
        # `case_id` is the table's primary key, so the repeat cannot insert a second row: the
        # recorded grant comes back instead of a new issuance.
        # [impl->req~schema-manual-grant-issuances-case-id-primary-key~1]
        self._record(ManualStep.resolve_case)
        if not self.request.case_id:
            raise ManualGrantError("the issuance resolves a support case identifier")
        existing = (recorded or {}).get(self.request.case_id)
        if existing is None:
            return None
        # The original result, and nothing new: no second grant, no second issuance row.
        return ManualIssuance(grant=dict(existing.grant), usage=existing.usage,
                              issuance=dict(existing.issuance), repeated=True)

    def lock(self, *, live_grant_ids: Sequence[UUID]) -> LockLedger:
        """2. Lock the target user, then that user's whole live `core.access_grants` set
        `FOR UPDATE` in ascending grant `id` order and their `core.user_monthly_usage` rows in that
        same order, under the fixed grant-then-usage lock order the shared contract owns. That lock
        set serializes the checks below and the insert against concurrent issuance and against the
        claim endpoints."""
        # [impl->req~grants-manual-step-02-lock-order~1]
        self._require(ManualStep.resolve_case)
        self._record(ManualStep.lock)
        if not takes_user_row_lock(LockingPath.manual_issuance):
            raise ManualGrantError("manual issuance locks the target user first")
        ledger = LockLedger(LockingPath.manual_issuance)
        ledger.lock_user(self.request.user_id)
        lock_grant_set(ledger, list(live_grant_ids))
        self.locks = ledger
        return ledger

    def refuse_blocked(self, *, user_blocked: bool,
                       identity_state: IdentityState = IdentityState.active) -> None:
        """3. Refuse for a blocked user or a permanently retired identity, creating nothing."""
        # [impl->req~grants-manual-step-03-refuse-blocked~1]
        self._require(ManualStep.lock)
        self._record(ManualStep.refuse_blocked)
        if user_blocked:
            raise ManualIssuanceRefused("a blocked user receives no manual grant")
        if identity_state is not IdentityState.active:
            raise ManualIssuanceRefused(
                "a permanently retired identity receives no manual grant; this is no undelete")

    def establish_eligibility(self, *,
                              claim_would_have_succeeded: bool | None = None,
                              anti_abuse_denial: str | None = None,
                              operator_judgment: str = "") -> str:
        """4. Establish that the claim being repaired would otherwise have succeeded. Issuance
        never overrides an ordinary eligibility denial, a rate limit, a reused-account restriction
        or any other anti-abuse decision. Where machine-verifiable evidence is unavailable, the
        operator's recorded support judgment is sufficient."""
        # [impl->req~grants-manual-step-04-establish-eligibility~1]
        self._require(ManualStep.refuse_blocked)
        self._record(ManualStep.establish_eligibility)
        if anti_abuse_denial:
            raise ManualIssuanceRefused(
                f"issuance never overrides {anti_abuse_denial}")
        if claim_would_have_succeeded is True:
            return "machine_verifiable_evidence"
        if claim_would_have_succeeded is False:
            raise ManualIssuanceRefused("the repaired claim would not otherwise have succeeded")
        if not operator_judgment.strip():
            raise ManualIssuanceRefused(
                "with no machine-verifiable evidence the operator's recorded judgment is required")
        return "operator_recorded_judgment"

    def check_one_active_grant(self, grants: Sequence[GrantRow], now: datetime) -> None:
        """5. From that locked grant set, re-check the one-active-grant-per-user invariant and
        refuse when the target already holds an active grant of any source. The procedure never
        creates a second active grant and never ranks precedence between grants."""
        # [impl->req~grants-manual-step-05-one-active-grant~1]
        self._require(ManualStep.establish_eligibility, ManualStep.lock)
        self._record(ManualStep.one_active_grant)
        if self.locks is None:
            raise ManualGrantError("the checks read the locked grant set")
        locked = set(self.locks.grant_locks)
        unlocked = sorted(str(grant.grant_id) for grant in grants
                          if grant.grant_id not in locked)
        if unlocked:
            raise ManualGrantError(f"{unlocked} was not locked FOR UPDATE for this check")
        held = [grant for grant in grants if is_effective(grant, now)]
        if held:
            raise ManualIssuanceRefused(
                f"the target already holds an active {held[0].source} grant; resolving that "
                "conflict is the operator's business outside this procedure")

    def insert_grant(self, *,
                     grant_id: UUID,
                     lost: LostClaim,
                     transaction: object,
                     now: datetime | None = None) -> tuple[dict[str, Any], NewUsageRow]:
        """6. Insert exactly one `core.access_grants` row with `source = 'manual'`, reproducing
        what the burned or lost claim would have activated — the same tier and monthly credits, the
        same duration and lifecycle, and the same owning `core.users.id` — together with that
        grant's `core.user_monthly_usage` row in the same transaction."""
        # [impl->req~grants-manual-step-06-insert-grant~1]
        self._require(ManualStep.one_active_grant)
        self._record(ManualStep.insert_grant)
        terms = derived_terms(lost)
        self.terms = terms
        grant: dict[str, Any] = {
            "id": grant_id,
            "user_id": self.request.user_id,
            "tier_id": terms.tier_id,
            "source": AccessGrantSource.manual,
            "status": AccessGrantStatus.active,
            "starts_at": terms.starts_at,
            "ends_at": terms.ends_at,
            "subscription_id": None,
        }
        assert_billing_separation(AccessGrantSource.manual, None)
        assert_grant_columns_entitlement_only(grant)
        # The grant is remediation, not a claim: no anti-abuse row pairs with it.
        assert_excluded_from_anti_abuse()
        # The usage row is created by the one creation point every grant source shares, in the
        # transaction that inserts the grant.
        usage = new_usage_row(grant_id, now=now,
                              grant_transaction=transaction, usage_transaction=transaction)
        return grant, usage

    def record_issuance(self, grant: Mapping[str, Any], *,
                        transaction: object,
                        usage_transaction: object | None = None) -> dict[str, Any]:
        """7. Record the issuance in that same transaction as one `core.manual_grant_issuances`
        row carrying the case identifier, the operator's identity, the reason or ticket reference,
        and the grant produced."""
        # [impl->req~grants-manual-step-07-record-issuance~1]
        self._require(ManualStep.insert_grant)
        self._record(ManualStep.record_issuance)
        # The same transaction as the grant and its usage row: one commit or none.
        if usage_transaction is not None and usage_transaction is not transaction:
            raise ManualGrantError("the issuance row is written in the grant's own transaction")
        # The row's own contract — the `case_id` primary key, the unique `grant_id`, the target
        # owner and the required non-empty audit trail — belongs to `registry_schema`.
        try:
            return manual_issuance_row(case_id=self.request.case_id,
                                       grant=grant,
                                       operator=self.request.operator,
                                       reason=self.request.reason,
                                       target_user_id=self.request.user_id,
                                       transaction=transaction,
                                       grant_transaction=transaction)
        except RegistryError as refusal:
            raise ManualGrantError(str(refusal)) from None

    def leave_vendor_state(self, *,
                           read: Sequence[str] = (),
                           cleared: Sequence[str] = (),
                           rewritten: Sequence[str] = ()) -> tuple[str, ...]:
        """8. Leave vendor and per-device state untouched. The procedure never clears, resets or
        rewrites a device bit or Device Recall state: the burned bit stays burned, and the grant is
        what compensates for it. Reading that state is permitted, since step 4 treats
        machine-verifiable evidence as the preferred basis for the eligibility judgment."""
        # [impl->req~grants-manual-step-08-leave-vendor-state~1]
        self._require(ManualStep.record_issuance)
        self._record(ManualStep.leave_vendor_state)
        touched = sorted(set(cleared) | set(rewritten))
        if touched:
            raise ManualGrantError(f"the procedure never clears, resets or rewrites {touched}")
        if VENDOR_BIT_CLEARERS or VENDOR_BIT_RECONCILERS:
            raise ManualGrantError("the burned bit stays burned")
        return tuple(read)


def issue_manual_grant(request: ManualIssuanceRequest,
                       *,
                       grant_id: UUID,
                       lost: LostClaim,
                       live_grant_ids: Sequence[UUID],
                       grants: Sequence[GrantRow],
                       now: datetime,
                       transaction: object,
                       recorded: Mapping[str, ManualIssuance] | None = None,
                       user_blocked: bool = False,
                       identity_state: IdentityState = IdentityState.active,
                       claim_would_have_succeeded: bool | None = None,
                       operator_judgment: str = "",
                       surface: IssuanceSurface = IssuanceSurface.direct_database_procedure,
                       operator_auth: OperatorAuth = OperatorAuth.shared_administrative_secret,
                       device_state_read: Sequence[str] = ()) -> ManualIssuance:
    """The whole procedure, in its fixed order, as one call."""
    # [impl->req~grants-manual-step-01-resolve-case~1]
    # [impl->req~grants-manual-step-02-lock-order~1]
    procedure = ManualGrantIssuance(request, surface=surface, operator_auth=operator_auth)
    repeat = procedure.resolve_case(recorded)
    if repeat is not None:
        return repeat
    procedure.lock(live_grant_ids=live_grant_ids)
    procedure.refuse_blocked(user_blocked=user_blocked, identity_state=identity_state)
    procedure.establish_eligibility(claim_would_have_succeeded=claim_would_have_succeeded,
                                    operator_judgment=operator_judgment)
    procedure.check_one_active_grant(grants, now)
    grant, usage = procedure.insert_grant(grant_id=grant_id, lost=lost,
                                          transaction=transaction, now=now)
    issuance = procedure.record_issuance(grant, transaction=transaction)
    procedure.leave_vendor_state(read=device_state_read)
    return ManualIssuance(grant=grant, usage=usage, issuance=issuance)


# --- Excluded from anti-abuse, ordinary everywhere else ---------------------------------------

# A `manual` grant is remediation rather than a claim: no anti-abuse row, no gate-consumption row.
MANUAL_ANTI_ABUSE_ROWS: int = 0
MANUAL_GATE_CONSUMPTION_ROWS: int = 0


def assert_excluded_from_anti_abuse(*,
                                   anti_abuse_grant_source: AccessGrantSource | None = None,
                                   gate_consumption_rows: int = 0) -> None:
    """A `manual` grant has no `core.access_grants_anti_abuse` row and no
    `core.provider_account_gate_consumptions` row."""
    # [impl->req~grants-manual-excluded-from-anti-abuse~1]
    # The grant an issuance row names always has `source = 'manual'`, and therefore neither row.
    # [impl->req~schema-manual-grant-issuances-grant-id-unique~1]
    assert_anti_abuse_pairing(AccessGrantSource.manual, anti_abuse_grant_source)
    if gate_consumption_rows or MANUAL_ANTI_ABUSE_ROWS or MANUAL_GATE_CONSUMPTION_ROWS:
        raise ManualGrantError("a manual grant consumes no provider-account gate")


def free_grant_slots_after_manual(
        committed_free_sources: Sequence[AccessGrantSource]) -> tuple[AccessGrantSource, ...]:
    """Issuing a `manual` grant neither consumes nor reopens a free-grant slot: the user's
    committed free-grant history is exactly what it was before."""
    # [impl->req~grants-manual-excluded-from-anti-abuse~1]
    return tuple(source for source in committed_free_sources if source in FREE_CLAIM_SOURCES)


def manual_grant_is_ordinary_downstream(grant: GrantRow, now: datetime) -> PublicEntitlementType:
    """Once issued it is an ordinary grant everywhere downstream: access and quota enforcement
    honor it under the shared effective-grant predicate, `/auth/sync` reports it as
    `type = manual`, and restore treats it exactly as it treats any other active grant."""
    # [impl->req~grants-manual-excluded-from-anti-abuse~1]
    if grant.source is not AccessGrantSource.manual:
        raise ManualGrantError(f"{grant.source} is no manual grant")
    if not is_effective(grant, now):
        raise ManualGrantError("an ended or revoked manual grant authorizes nothing")
    return PublicEntitlementType.manual


# --- Open-ended, and revoked on the same surface ----------------------------------------------

# No client-reachable call ends, drops or replaces a grant a user holds.
CLIENT_REACHABLE_GRANT_ENDERS: frozenset[str] = frozenset()
MANUAL_GRANT_END_SURFACE: IssuanceSurface = IssuanceSurface.direct_database_procedure


def manual_grant_open_ended(grant: GrantRow) -> bool:
    """A `manual` grant needs no finite end date: like any grant it may run open-ended, with
    `ends_at` unset, until it is revoked."""
    # [impl->req~grants-manual-open-ended-and-revocation~1]
    if grant.source is not AccessGrantSource.manual:
        raise ManualGrantError(f"{grant.source} is no manual grant")
    return grant.ends_at is None


def revoke_manual_grant(grant: GrantRow, *,
                        at: datetime,
                        surface: IssuanceSurface = MANUAL_GRANT_END_SURFACE) -> GrantRow:
    """Ending one early is an operator action on the same procedure surface as issuance: the
    operator moves the grant to `status = 'revoked'` with `ends_at` at the revocation time, which
    frees the user's one active-grant slot. That is the remediation for a user who holds an
    open-ended `manual` grant and wants the registered free grant instead."""
    # [impl->req~grants-manual-open-ended-and-revocation~1]
    assert_operator_only_surface(surface)
    if grant.source is not AccessGrantSource.manual:
        raise ManualGrantError(f"{grant.source} is not revoked through this procedure")
    if CLIENT_REACHABLE_GRANT_ENDERS:
        raise ManualGrantError("no client-reachable call ends, drops or replaces a held grant")
    revoked = GrantRow(grant_id=grant.grant_id, user_id=grant.user_id, tier_id=grant.tier_id,
                       source=grant.source, status=AccessGrantStatus.revoked,
                       starts_at=grant.starts_at, ends_at=at,
                       subscription_id=grant.subscription_id,
                       tier_monthly_credits=grant.tier_monthly_credits)
    if is_effective(revoked, at):
        raise ManualGrantError("a revoked grant frees the user's one active-grant slot")
    return revoked


def blocked_registered_claim_options(*, revoked_by_operator: bool) -> tuple[str, ...]:
    """A `claim_registered_grant` blocked by an active `manual` grant either waits for that grant
    to end or asks support to revoke it. There is no endpoint that lets the user end it."""
    # [impl->req~grants-manual-open-ended-and-revocation~1]
    if CLIENT_REACHABLE_GRANT_ENDERS:
        raise ManualGrantError("no endpoint lets a user end, drop or replace a grant they hold")
    return ("operator_revocation_then_retry",) if revoked_by_operator \
        else ("wait_for_the_held_grant_to_end", "ask_support_to_revoke_it")


# --- Never promotional ------------------------------------------------------------------------

# The uses `manual` must never take on. A promotions feature, if it is ever wanted, arrives as its
# own complete design rather than through this source.
PROHIBITED_MANUAL_USES: frozenset[str] = frozenset({
    "goodwill", "promo", "promotion", "promotional", "marketing", "campaign", "giveaway",
    "discount", "referral", "loyalty"})
PROMOTIONAL_GRANT_SOURCES: frozenset[AccessGrantSource] = frozenset()


def assert_not_promotional(reason: str, *, purpose: str = MANUAL_PURPOSE) -> str:
    """`manual` repairs a documented lost claim only. It must never become a general-purpose
    goodwill, promotional or marketing source, and the absence of a promotional grant source must
    not be worked around through it."""
    # [impl->req~grants-manual-never-promotional~1]
    if purpose != MANUAL_PURPOSE or PROMOTIONAL_GRANT_SOURCES:
        raise ManualGrantError(f"{purpose} is not what the manual source is for")
    words = {word.strip(",.;:!?-_/()") for word in reason.lower().replace("-", " ").split()}
    offending = sorted(words & PROHIBITED_MANUAL_USES)
    if offending:
        raise ManualGrantError(
            f"manual is no {offending} source; a promotions feature arrives as its own design")
    return reason


def promotional_source_workaround(candidate: Callable[[], AccessGrantSource] | None = None) -> None:
    """There is no promotional grant source, and `manual` is not a stand-in for one."""
    # [impl->req~grants-manual-never-promotional~1]
    if candidate is not None and candidate() is AccessGrantSource.manual:
        raise ManualGrantError("the missing promotional source is never worked around through manual")
