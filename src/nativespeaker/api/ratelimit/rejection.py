"""What a rejection returns, what it records, and what it must not leave behind.

Two rejections live here and they are not the same thing. An admission-control rejection is a
`429` taken in the admission phase: it belongs to that phase wherever its check sits, so it
touches no challenge and writes no `audit.auth_events` row, and the whole record of it is one
bounded aggregate telemetry entry. Exhaustion of a verification-capacity budget is not that: it
is a server-side condition that surfaces as `verification_temporarily_unavailable`, and for the
four free-grant device-bit budgets it is durably audited, because those budgets are checked
after the operation challenge has been claimed.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from nativespeaker.api.auth.audit import (
    NO_ACTOR,
    AttemptPhase,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEvent,
    AuthEventResult,
    terminal_event,
)
from nativespeaker.api.auth.challenges import ChallengeState, advance_state
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.taxonomy import (
    RATE_LIMITED_CLASS,
    ClientErrorClass,
    ClientRejection,
    Remediation,
    client_response,
    remediation_for,
)
from nativespeaker.api.exceptions import ErrorCode, ServiceError
from nativespeaker.api.ratelimit.config import (
    CREATE_USER_GATEWAY_ENTRIES,
    DEVICE_BIT_BUDGET_ENTRIES,
    FIREBASE_LOOKUP_ENTRY_KEYS,
    TURNSTILE_ENTRY,
)
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import ExpensiveStep

# The one status an admission-control rejection carries.
ADMISSION_REJECTION_STATUS = 429


class AdmissionRejected(ServiceError):
    """A rate-limit or admission-control rejection: `429 Too Many Requests`, carrying
    `Retry-After` when the `limits` backend could compute a reset time and nothing else. The
    body and headers are built by the shared error contract in `auth/taxonomy.py`, so the body
    names a registered client class alone and never the limiter that fired."""

    # [impl->req~ratelimit-reject-429-with-retry-after~1]
    status_code = ADMISSION_REJECTION_STATUS
    error_code: ErrorCode = "rate_limited"

    def __init__(self,
                 limiter: str,
                 retry_after_seconds: int | None = None,
                 *,
                 client_class: str = RATE_LIMITED_CLASS,
                 waits: Sequence[int] = ()):
        self.limiter = limiter
        self.client_class = client_class
        waits = tuple(waits) or ((retry_after_seconds,) if retry_after_seconds is not None else ())
        # The header reflects the limiting bucket's true wait — the longest known wait when more
        # than one limit applies — which the shared contract computes.
        # [impl->req~ratelimit-reject-429-with-retry-after~1]
        self.client: ClientRejection = client_response(client_class, retry_after_seconds=waits)
        self.retry_after_seconds = max(waits) if waits else None
        self.status_code = self.client.status
        self.error_code = cast(ErrorCode, client_class)
        super().__init__("rate limited")

    def extra_headers(self) -> dict[str, str] | None:
        """`Retry-After` is included exactly when a reset time was computable; a limiter
        rejection the backend could not compute a reset for carries no header rather than a
        fabricated one."""
        # [impl->req~ratelimit-reject-429-with-retry-after~1]
        return dict(self.client.headers) or None


def admission_rejection(decision: LimitDecision,
                        *more: LimitDecision,
                        client_class: str = RATE_LIMITED_CLASS) -> AdmissionRejected:
    """Turn one or more refusing limiter verdicts into the rejection the client receives. Where
    several limiters are exhausted the longest known wait is the one reported."""
    # [impl->req~ratelimit-reject-429-with-retry-after~1]
    decisions = (decision, *more)
    admitted = [one.limiter for one in decisions if one.allowed]
    if admitted:
        raise ValueError(f"{', '.join(admitted)} admitted the request")
    waits = [one.retry_after_seconds for one in decisions if one.retry_after_seconds is not None]
    return AdmissionRejected(decision.limiter, client_class=client_class, waits=waits)


# --- Budget exhaustion: a verification-capacity condition, never a `429` -----------------------

# Every Firebase Admin lookup budget this file defines: the deployment-wide and client-IP
# endpoint-layer entries at `create_user` completion, the upgrade route's entry, and the global
# provider-call budget behind all of them.
# [impl->req~ratelimit-firebase-budget-exhaustion-class~1]
FIREBASE_LOOKUP_BUDGETS: tuple[str, ...] = (*FIREBASE_LOOKUP_ENTRY_KEYS, "adapter_firebase_lookup")

# The four free-grant device-bit provider budgets, each with the internal result that names it,
# one per budget entry in the order this file names them.
# [impl->req~ratelimit-device-bit-budget-exhaustion-class~1]
DEVICE_BIT_BUDGET_RESULTS: dict[str, AuthEventResult] = {
    "adapter_devicecheck_read": AuthEventResult.devicecheck_read_budget_exhausted,
    "adapter_devicecheck_write": AuthEventResult.devicecheck_write_budget_exhausted,
    "adapter_play_integrity_device_recall_read":
        AuthEventResult.device_recall_read_budget_exhausted,
    "adapter_play_integrity_device_recall_write":
        AuthEventResult.device_recall_write_budget_exhausted,
}

# Both families are server-side verification-capacity conditions and share one client class.
VERIFICATION_CAPACITY_CLASS = ClientErrorClass.verification_temporarily_unavailable


class BudgetExhaustionError(RuntimeError):
    """An entry was treated as a verification-capacity budget that is not one, or a rejection
    was about to leave the backend in the wrong class."""


def budget_exhaustion_class(entry: str) -> ClientErrorClass:
    """The client class an exhausted verification budget maps to."""
    # [impl->req~ratelimit-firebase-budget-exhaustion-class~1]
    # [impl->req~ratelimit-device-bit-budget-exhaustion-class~1]
    if entry not in FIREBASE_LOOKUP_BUDGETS and entry not in DEVICE_BIT_BUDGET_RESULTS:
        raise BudgetExhaustionError(f"{entry} is no verification-capacity budget")
    remediation = client_response(VERIFICATION_CAPACITY_CLASS)
    if remediation.status == ADMISSION_REJECTION_STATUS:
        # A `429` would misrepresent a verification-backend outage as client misbehaviour and
        # hide it from the audit taxonomy.
        # [impl->req~ratelimit-device-bit-budget-exhaustion-class~1]
        raise BudgetExhaustionError(f"{entry} exhaustion is never the generic admission 429")
    return VERIFICATION_CAPACITY_CLASS


# The free-credit grant claims. A fail-closed device-bit or web-gate lookup budget rejection
# denies one of these and nothing else.
# [impl->req~ratelimit-fail-closed-scoped-to-free-grant~1]
FREE_GRANT_OPERATIONS: frozenset[AuthOperation] = frozenset({
    AuthOperation.claim_anonymous_grant,
    AuthOperation.claim_registered_grant,
})

# The budgets whose fail-closed behaviour that scope covers: the four device-bit budgets and the
# web gate's Turnstile `siteverify` budget.
FAIL_CLOSED_FREE_GRANT_BUDGETS: frozenset[str] = frozenset({
    *DEVICE_BIT_BUDGET_ENTRIES, TURNSTILE_ENTRY})


class FailClosedScopeError(RuntimeError):
    """A free-grant fail-closed budget was about to deny something other than a free grant."""


def budget_denies(entry: str, operation: AuthOperation) -> bool:
    """Whether an exhausted fail-closed device-bit or web-gate lookup budget denies this
    operation. Only the free-credit grant claims: never login, account creation, upgrade, sync,
    subscription restore, or any paid entitlement path."""
    # [impl->req~ratelimit-fail-closed-scoped-to-free-grant~1]
    if entry not in FAIL_CLOSED_FREE_GRANT_BUDGETS:
        raise FailClosedScopeError(f"{entry} is no free-grant fail-closed budget")
    return operation in FREE_GRANT_OPERATIONS


def assert_fail_closed_scope(entry: str, operation: AuthOperation) -> None:
    """Fail closed against the free grant alone."""
    # [impl->req~ratelimit-fail-closed-scoped-to-free-grant~1]
    if not budget_denies(entry, operation):
        raise FailClosedScopeError(f"{entry} never blocks {operation}")


class DeviceBitBudgetExhausted(ServiceError):
    """The client-visible rejection an exhausted free-grant device-bit budget earns. It is a
    server-side verification-capacity condition, never the generic admission `429`."""

    error_code: ErrorCode = "verification_temporarily_unavailable"

    def __init__(self, rejection: DeviceBitBudgetRejection):
        self.rejection = rejection
        self.status_code = rejection.client.status
        super().__init__("verification capacity exhausted")


@dataclass(frozen=True, slots=True)
class DeviceBitBudgetRejection:
    """An exhausted free-grant device-bit budget. The attempt is already on the audited attempt
    path — the budget is checked after the operation challenge has been claimed — so it writes
    its single `audit.auth_events` row, the internal result names the exhausted budget, and the
    claimed challenge is consumed with the rejection rather than returned to the issued state.
    No grant is issued and the read or write whose budget was unavailable is not performed."""
    entry: str
    result: AuthEventResult
    client: ClientRejection
    challenge_state: ChallengeState
    event: AuthEvent
    grant_issued: bool = False
    vendor_call_performed: bool = False

    @property
    def audit_rows(self) -> int:
        """One row for the attempt, and the writer is what enforces that it is only one."""
        return 1


def device_bit_budget_rejection(entry: str,
                                operation: AuthOperation,
                                *,
                                challenge_state: ChallengeState,
                                actor: AuthActor = NO_ACTOR,
                                challenge_row_id: UUID | None = None
                                ) -> DeviceBitBudgetRejection:
    """Refuse a claim whose device-bit budget is exhausted."""
    # [impl->req~ratelimit-device-bit-budget-exhaustion-class~1]
    result = DEVICE_BIT_BUDGET_RESULTS.get(entry)
    if result is None:
        raise BudgetExhaustionError(f"{entry} is no free-grant device-bit budget")
    # The rejection is scoped to the free grant it denies.
    # [impl->req~ratelimit-fail-closed-scoped-to-free-grant~1]
    assert_fail_closed_scope(entry, operation)
    client_class = budget_exhaustion_class(entry)
    if challenge_state is not ChallengeState.claimed:
        raise BudgetExhaustionError(
            "a device-bit budget is checked only after the challenge has been claimed")
    # Consumed with the rejection: the claimed challenge is never returned to `issued`, and the
    # client retries the whole claim with a fresh challenge and fresh vendor material.
    consumed = advance_state(challenge_state, ChallengeState.consumed)
    # The durable record the attempt owes: one `audit.auth_events` row whose internal result
    # names the exhausted budget. It is built here and written by `AuthAuditWriter`, the one
    # write path every other on-path rejection uses.
    # [impl->req~ratelimit-device-bit-budget-exhaustion-class~1]
    event = terminal_event(AttemptPhase.business, result, operation=operation, actor=actor,
                           challenge_row_id=challenge_row_id,
                           details={"failure": {"budget": entry}})
    return DeviceBitBudgetRejection(entry=entry,
                                    result=result,
                                    client=client_response(client_class),
                                    challenge_state=consumed,
                                    event=event)


async def record_device_bit_budget_rejection(writer: AuthAuditWriter,
                                             attempt: AuthAttempt,
                                             rejection: DeviceBitBudgetRejection,
                                             *,
                                             session: Any) -> Exception:
    """Durably audit the rejection inside the transaction that consumes the claimed challenge,
    and hand back the client-visible error. The attempt is claimed by the writer, so no later
    path can write a second row for the same attempt."""
    # [impl->req~ratelimit-device-bit-budget-exhaustion-class~1]
    return await writer.record_rejection(attempt, rejection.event,
                                         DeviceBitBudgetExhausted(rejection), session=session)


def _assert_budget_results_ordered() -> None:
    """One internal result per budget entry, in the order this file names the budgets."""
    # [impl->req~ratelimit-device-bit-budget-exhaustion-class~1]
    if tuple(DEVICE_BIT_BUDGET_RESULTS) != DEVICE_BIT_BUDGET_ENTRIES:
        raise BudgetExhaustionError("one result per device-bit budget entry, in that order")
    if len(set(DEVICE_BIT_BUDGET_RESULTS.values())) != len(DEVICE_BIT_BUDGET_ENTRIES):
        raise BudgetExhaustionError("each device-bit budget names its own result")


_assert_budget_results_ordered()


# --- Pre-admission telemetry ------------------------------------------------------------------


class CoarseActor(StrEnum):
    """The coarse actor data a telemetry record may carry. Bounded by construction: no subject,
    no user id, no proof fingerprint, and no per-attempt detail of any kind."""
    # [impl->req~ratelimit-pre-admission-aggregate-telemetry~1]
    anonymous = "anonymous"
    authenticated = "authenticated"
    unresolved_address = "unresolved_address"


@dataclass(frozen=True, slots=True)
class RejectionTelemetry:
    """One bounded aggregate record: the route, the name of the limiter that fired, and coarse
    actor data. There is no field for raw proof material, a raw provider payload, or per-attempt
    restore audit-event data, so no call site can store one."""
    # [impl->req~ratelimit-pre-admission-aggregate-telemetry~1]
    route: str
    reason: str
    actor: CoarseActor


class SecurityTelemetry:
    """The ordinary access and rate-limit telemetry a suppressed rejection appears in. It counts
    records; it holds no database session and writes no row."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str, str], int] = {}

    def record(self, *, route: str, reason: str, actor: CoarseActor) -> RejectionTelemetry:
        """Record one rejection as an aggregate. That is the whole record of a suppressed
        attempt: no `audit.auth_events` row and no per-rejection database row of any kind."""
        # [impl->req~ratelimit-pre-admission-aggregate-telemetry~1]
        entry = RejectionTelemetry(route=route, reason=reason, actor=CoarseActor(actor))
        key = (entry.route, entry.reason, str(entry.actor))
        self._counts[key] = self._counts.get(key, 0) + 1
        return entry

    def value(self, *, route: str, reason: str, actor: CoarseActor) -> int:
        return self._counts.get((route, reason, str(CoarseActor(actor))), 0)

    def labels(self) -> list[tuple[str, str, str]]:
        """Every label triple recorded. The label set is the aggregate's whole content."""
        return sorted(self._counts)


# --- The admission phase ----------------------------------------------------------------------


class AdmissionPhaseError(RuntimeError):
    """An admission-control rejection was about to behave like an on-path attempt."""


@dataclass(frozen=True, slots=True)
class AdmissionRejection:
    """Everything an admission-control rejection leaves behind: the `429` the client receives
    and one aggregate telemetry record. No audit row, no consumed challenge, no database row."""
    error: AdmissionRejected
    telemetry: RejectionTelemetry
    challenge_state: ChallengeState | None
    audit_rows: int = 0
    database_rows: int = 0


class AdmissionPhase:
    """One request's admission phase, over the attempt the route already classified."""

    def __init__(self,
                 attempt: AuthAttempt,
                 telemetry: SecurityTelemetry,
                 *,
                 challenge_state: ChallengeState | None = None):
        self.attempt = attempt
        self._telemetry = telemetry
        self._challenge_state = challenge_state

    def reject(self,
               decision: LimitDecision,
               *more: LimitDecision,
               actor: CoarseActor = CoarseActor.anonymous,
               client_class: str = RATE_LIMITED_CLASS) -> AdmissionRejection:
        """Reject in the admission phase. The rejection belongs to that phase wherever in the
        request path its check sits — on a canonical state-changing route as much as anywhere
        else — so it consumes no operation challenge and creates no `audit.auth_events` row."""
        # [impl->req~ratelimit-admission-rejections-off-audited-path~1]
        if self.attempt.audited:
            raise AdmissionPhaseError(
                f"{self.attempt.route} already wrote an audit row for this attempt")
        # It appears in the ordinary access and rate-limit telemetry carrying the name of the
        # limiter that fired, and leaves nothing else behind.
        # [impl->req~ratelimit-pre-admission-aggregate-telemetry~1]
        record = self._telemetry.record(route=self.attempt.route,
                                        reason=decision.limiter,
                                        actor=actor)
        rejection = AdmissionRejection(error=admission_rejection(decision, *more,
                                                                client_class=client_class),
                                       telemetry=record,
                                       # Untouched: the challenge stays in whatever state it was
                                       # already in, and is neither claimed nor consumed here.
                                       challenge_state=self._challenge_state)
        assert_off_audited_path(rejection, self.attempt)
        return rejection


def assert_off_audited_path(rejection: AdmissionRejection, attempt: AuthAttempt) -> None:
    """An admission-control rejection is never on the audited attempt path."""
    # [impl->req~ratelimit-admission-rejections-off-audited-path~1]
    if attempt.audited or rejection.audit_rows or rejection.database_rows:
        raise AdmissionPhaseError("an admission-control rejection writes no audit row")
    if rejection.challenge_state is ChallengeState.consumed:
        raise AdmissionPhaseError("an admission-control rejection consumes no challenge")


def assert_aggregate_only(payload: Mapping[str, object]) -> None:
    """Aggregate telemetry stores route, reason and coarse actor data alone: never raw proof
    material, raw provider payloads, or per-attempt restore audit-event data."""
    # [impl->req~ratelimit-pre-admission-aggregate-telemetry~1]
    permitted = {"route", "reason", "actor"}
    extra = sorted(set(payload) - permitted)
    if extra:
        raise AdmissionPhaseError(f"aggregate telemetry stores no {extra}")


# --- The pre-auth create-user gateway rejection ------------------------------------------------

# The one client-visible class both `POST /auth/create-user` gateway ceilings reject with.
# [impl->req~sessions-create-user-limits-fail-closed~1]
GATEWAY_REGISTRATION_CLASS = ClientErrorClass.registration_temporarily_unavailable

# Everything the route creates when it runs, and therefore everything a request rejected at the
# gateway never creates: it reaches no backend code at all. Each artifact is named with the
# backend step that would create it, so the admission ledger — not a caller's recollection — is
# what refuses it behind a gateway rejection.
# [impl->req~sessions-rejected-request-never-reaches-backend~1]
CREATE_USER_ARTIFACT_STEPS: dict[str, ExpensiveStep] = {
    "core.auth_challenges": ExpensiveStep.database_mutation,
    "core.users": ExpensiveStep.database_mutation,
    "core.external_identities": ExpensiveStep.database_mutation,
    "audit.auth_events": ExpensiveStep.database_mutation,
    "firebase_admin_lookup": ExpensiveStep.firebase_lookup,
}
CREATE_USER_BACKEND_ARTIFACTS: frozenset[str] = frozenset(CREATE_USER_ARTIFACT_STEPS)

# What a gateway-rejected request leaves behind in the backend: nothing.
# [impl->req~sessions-rejected-request-never-reaches-backend~1]
GATEWAY_REJECTED_BACKEND_ARTIFACTS: frozenset[str] = frozenset()

# Nothing this route creates is deleted automatically: no scheduled purge of expired or consumed
# challenge rows, and no scheduled deletion of empty anonymous users. Both retention rules are
# read from the modules that own them rather than restated here.
# [impl->req~sessions-no-automatic-deletion-on-create-user-route~1]
CREATE_USER_ROUTE_DELETION_JOBS: frozenset[str] = frozenset()


class GatewayRejectionError(RuntimeError):
    """A gateway rejection was about to leave the shared client contract: a status other than
    `429`, a body naming the exhausted bucket, or backend work behind a rejected request."""


def gateway_registration_rejection(retry_after_seconds: Sequence[int],
                                   *,
                                   ceiling: str | None = None) -> ClientRejection:
    """The rejection either `POST /auth/create-user` gateway ceiling returns.

    Both limits fail closed with the shared `registration_temporarily_unavailable` class: HTTP
    429, a `Retry-After` header reflecting the limiting bucket's true wait, and the shared
    response shape naming the class. The response is identical and non-accusatory for the per-IP
    and the deployment-wide ceiling alike, and it never identifies which bucket was exhausted.

    The wait is a required argument, and an empty one is refused. Unlike a backend limiter, whose
    reset time may not be computable, these are fixed-window gateway ceilings: the wait until the
    applicable window admits requests again always exists, so the header is unconditional and a
    header-less rejection is not a shape this function can produce.
    """
    # [impl->req~sessions-create-user-limits-fail-closed~1]
    if ceiling is not None and ceiling not in CREATE_USER_GATEWAY_ENTRIES:
        raise GatewayRejectionError(f"{ceiling} is no create-user gateway ceiling")
    waits = tuple(retry_after_seconds)
    if not waits:
        raise GatewayRejectionError(
            "a gateway ceiling's rejection carries the limiting bucket's true wait")
    rejection = client_response(GATEWAY_REGISTRATION_CLASS, retry_after_seconds=waits)
    if rejection.status != ADMISSION_REJECTION_STATUS:
        raise GatewayRejectionError("a gateway ceiling rejects with HTTP 429")
    if "Retry-After" not in rejection.headers:
        raise GatewayRejectionError("the rejection carries the limiting bucket's true wait")
    disclosed = f"{sorted(rejection.body.items())}{sorted(rejection.headers.items())}"
    # Neither the bucket that fired nor the key it fired on appears anywhere in the response.
    # [impl->req~sessions-create-user-limits-fail-closed~1]
    for name in (*CREATE_USER_GATEWAY_ENTRIES, *([ceiling] if ceiling else [])):
        if name in disclosed:
            raise GatewayRejectionError("the rejection never identifies the exhausted bucket")
    return rejection


def backend_artifacts_after_gateway(*,
                                    admitted: bool,
                                    artifacts: Sequence[str] = ()) -> frozenset[str]:
    """The artifacts a `POST /auth/create-user` request is allowed to have created, given whether
    the gateway limits admitted it. Every database insert and every Firebase Admin read on this
    route happens only after those limits admit the request, so a rejected one creates no
    challenge row, no user or identity row, no `audit.auth_events` row, and triggers no Firebase
    Admin lookup."""
    # [impl->req~sessions-rejected-request-never-reaches-backend~1]
    offered = frozenset(artifacts)
    unknown = sorted(offered - CREATE_USER_BACKEND_ARTIFACTS)
    if unknown:
        raise GatewayRejectionError(f"{unknown} is not a create-user backend artifact")
    if not admitted:
        if offered:
            raise GatewayRejectionError(
                f"a gateway-rejected request creates no {sorted(offered)}")
        return GATEWAY_REJECTED_BACKEND_ARTIFACTS
    return offered


def assert_saturation_tradeoff_accepted() -> Remediation:
    """The accepted availability trade-off: while a distributed attack keeps the deployment-wide
    ceiling saturated, account creation is unavailable to legitimate users for the duration.

    That is the intended trade, so the rejection stays a transient wait-and-retry rather than
    something a caller can route around: the class is transient and carries `Retry-After`, and no
    bypass token, priority lane or limiting exemption exists to reopen the path while the ceiling
    binds."""
    # [impl->req~sessions-create-user-saturation-tradeoff~1]
    remediation = remediation_for(GATEWAY_REGISTRATION_CLASS)
    if not remediation.transient or not remediation.sends_retry_after:
        raise GatewayRejectionError("a saturated ceiling is a transient wait, not a terminal stop")
    if remediation.terminal:
        raise GatewayRejectionError("a saturated ceiling never terminally closes registration")
    return remediation


def assert_no_automatic_deletion(jobs: Sequence[str] = ()) -> None:
    """Nothing created on this route is deleted automatically: retention is indefinite, and total
    volume is bounded by the gateway ceilings instead. The challenge table's purge rule and the
    anonymous user row's retention rule are read from their owning modules."""
    # [impl->req~sessions-no-automatic-deletion-on-create-user-route~1]
    from nativespeaker.api.auth.challenges import CHALLENGE_PURGE_JOBS  # noqa: PLC0415
    from nativespeaker.api.auth.profile import AccountClass, retention_deadline  # noqa: PLC0415

    scheduled = sorted({*jobs, *CHALLENGE_PURGE_JOBS, *CREATE_USER_ROUTE_DELETION_JOBS})
    if scheduled:
        raise GatewayRejectionError(f"nothing on this route is purged on a schedule: {scheduled}")
    if retention_deadline(AccountClass.anonymous,
                          created_at=datetime(2026, 1, 1, tzinfo=UTC)) is not None:
        raise GatewayRejectionError("an empty anonymous user row is never deleted on a schedule")


# --- Operational counters ---------------------------------------------------------------------


class RateLimitMetrics:
    """The operational counters the backend exposes."""

    # [impl->req~ratelimit-operational-counters~1]
    COUNTERS: tuple[str, ...] = (
        "allowed_requests",
        "rejections_429",
        "storage_failures",
        "provider_budget_rejections",
        "coalesced_provider_reuse",
    )

    def __init__(self) -> None:
        self._counts: dict[str, int] = dict.fromkeys(self.COUNTERS, 0)
        self._exhausted: dict[str, int] = {}

    def _bump(self, name: str) -> None:
        if name not in self._counts:
            raise KeyError(f"{name} is no operational counter")
        self._counts[name] += 1

    def observe(self, decision: LimitDecision) -> None:
        """Count one limiter verdict: an allowed request, a `429` rejection, and a backend
        rate-limit storage failure independently of how that failure resolved."""
        # [impl->req~ratelimit-operational-counters~1]
        if decision.storage_failed:
            self._bump("storage_failures")
        self._bump("allowed_requests" if decision.allowed else "rejections_429")

    def provider_budget_rejected(self, entry: str) -> None:
        """Count one provider-call budget rejection. Where more than one applicable budget was
        exhausted, every exhausted limiter is recorded, not only the primary reported one."""
        # [impl->req~ratelimit-operational-counters~1]
        self._bump("provider_budget_rejections")
        self._exhausted[entry] = self._exhausted.get(entry, 0) + 1

    def coalesced_reuse(self) -> None:
        """Count one coalesced provider verification reuse: a follower or a fresh cached result
        that spent no provider call of its own."""
        # [impl->req~ratelimit-operational-counters~1]
        self._bump("coalesced_provider_reuse")

    def exhausted(self, entry: str) -> int:
        return self._exhausted.get(entry, 0)

    def counters(self) -> dict[str, int]:
        return dict(self._counts)
