"""The shared auth audit contract: `audit.auth_events` rows for the audited attempt path,
and the bounded counter metric that carries barrier results everywhere else."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

import structlog

from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider, match_operation

logger = structlog.get_logger()


class AuthEventResult(StrEnum):
    """`core.auth_event_result`. `succeeded` is the only success code."""
    succeeded = "succeeded"
    challenge_expired = "challenge_expired"
    challenge_consumed = "challenge_consumed"
    challenge_identity_mismatch = "challenge_identity_mismatch"
    challenge_operation_mismatch = "challenge_operation_mismatch"
    challenge_not_found = "challenge_not_found"
    invalid_external_jwt = "invalid_external_jwt"
    preauth_identity_not_allowed = "preauth_identity_not_allowed"
    identity_already_linked = "identity_already_linked"
    provider_not_linked = "provider_not_linked"
    provider_transition_not_allowed = "provider_transition_not_allowed"
    provider_account_already_linked = "provider_account_already_linked"
    blocked_user = "blocked_user"
    historical_identity = "historical_identity"
    invalid_restore_proof = "invalid_restore_proof"
    proof_malformed = "proof_malformed"
    store_transaction_already_linked = "store_transaction_already_linked"
    restore_subscription_unlinked = "restore_subscription_unlinked"
    restore_subscription_not_entitled = "restore_subscription_not_entitled"
    restore_purchase_uuid_unknown = "restore_purchase_uuid_unknown"
    restore_purchase_uuid_mismatch = "restore_purchase_uuid_mismatch"
    restore_subscription_grant_owner_mismatch = "restore_subscription_grant_owner_mismatch"
    restore_branch_inconsistent = "restore_branch_inconsistent"
    restore_store_state_unverified = "restore_store_state_unverified"
    restore_source_user_inactive = "restore_source_user_inactive"
    restore_destination_anonymous = "restore_destination_anonymous"
    restore_destination_already_entitled = "restore_destination_already_entitled"
    anti_abuse_already_claimed = "anti_abuse_already_claimed"
    native_claim_already_claimed = "native_claim_already_claimed"
    native_claim_unavailable = "native_claim_unavailable"
    native_claim_write_failed = "native_claim_write_failed"
    devicecheck_read_budget_exhausted = "devicecheck_read_budget_exhausted"
    devicecheck_write_budget_exhausted = "devicecheck_write_budget_exhausted"
    device_recall_read_budget_exhausted = "device_recall_read_budget_exhausted"
    device_recall_write_budget_exhausted = "device_recall_write_budget_exhausted"
    firebase_user_unresolved = "firebase_user_unresolved"
    idp_account_not_eligible = "idp_account_not_eligible"
    firebase_lookup_unavailable = "firebase_lookup_unavailable"
    verification_temporarily_unavailable = "verification_temporarily_unavailable"
    idp_account_already_claimed = "idp_account_already_claimed"
    registered_grant_destination_incompatible = "registered_grant_destination_incompatible"
    policy_rejected = "policy_rejected"
    revocation_unconfirmed = "revocation_unconfirmed"
    internal_error = "internal_error"


# The four results the shared pre-handler barrier can produce.
BARRIER_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.invalid_external_jwt,
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.historical_identity,
    AuthEventResult.blocked_user,
})


@dataclass(frozen=True, slots=True)
class AuthActor:
    """Actor columns. Populated only when a backend-verified token or resolved identity
    supplied that actor; nothing decoded from an unverified token may fill them."""
    issuer: str | None = None
    subject_hash: bytes | None = None
    subject_hash_key_version: int | None = None
    provider: IdentityProvider | None = None


NO_ACTOR = AuthActor()


@dataclass(frozen=True, slots=True)
class AuthEvent:
    result: AuthEventResult
    operation: AuthOperation | None = None
    actor: AuthActor = NO_ACTOR
    challenge_row_id: UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)


class AttemptPhase(StrEnum):
    """Where the attempt reached its terminal outcome. Every phase writes the one row."""
    barrier = "barrier"
    prepare = "prepare"
    business = "business"
    later = "later"
    success = "success"


class InvalidTerminalOutcomeError(ValueError):
    """The result does not belong to the phase that produced it."""


def terminal_event(phase: AttemptPhase,
                   result: AuthEventResult,
                   *,
                   operation: AuthOperation | None = None,
                   actor: AuthActor = NO_ACTOR,
                   challenge_row_id: UUID | None = None,
                   details: dict[str, Any] | None = None) -> AuthEvent:
    """Build the single row an on-path attempt owes for its terminal outcome, whatever that
    outcome is."""
    details = dict(details or {})
    match phase:
        case AttemptPhase.barrier:
            # A barrier rejection. `invalid_external_jwt` supplied no permitted actor, so the
            # row takes the actor-`NULL` shape whatever the caller passed.
            # [impl->req~shared-audit-outcome-barrier-rejection~1]
            if result not in BARRIER_RESULTS:
                raise InvalidTerminalOutcomeError(f"{result} is not a barrier result")
            if result is AuthEventResult.invalid_external_jwt:
                actor = NO_ACTOR
        case AttemptPhase.prepare:
            # A prepare-phase rejection, such as `identity_already_linked` at create_user prepare.
            # [impl->req~shared-audit-outcome-prepare-rejection~1]
            _reject_success(phase, result)
        case AttemptPhase.business:
            # An ordinary business-validation, proof, or live-state rejection.
            # [impl->req~shared-audit-outcome-business-rejection~1]
            _reject_success(phase, result)
            if result in BARRIER_RESULTS:
                raise InvalidTerminalOutcomeError(f"{result} is a barrier result")
        case AttemptPhase.later:
            # A later operation failure, such as `revocation_unconfirmed`.
            # [impl->req~shared-audit-outcome-later-failure~1]
            _reject_success(phase, result)
        case AttemptPhase.success:
            # `succeeded` is the only success code.
            # [impl->req~shared-audit-outcome-succeeded~1]
            if result is not AuthEventResult.succeeded:
                raise InvalidTerminalOutcomeError(f"{result} is not a success")
    return AuthEvent(result=result, operation=operation, actor=actor,
                     challenge_row_id=challenge_row_id, details=details)


def _reject_success(phase: AttemptPhase, result: AuthEventResult) -> None:
    if result is AuthEventResult.succeeded:
        raise InvalidTerminalOutcomeError(f"{phase} cannot produce {result}")


class AuthEventSink(Protocol):
    async def insert(self, session: Any, event: AuthEvent) -> None:
        """Append one durable `audit.auth_events` row using the given session."""
        ...


class AuditAlreadyWrittenError(RuntimeError):
    """A second `audit.auth_events` row was attempted for one attempt."""


class OffPathAuditError(RuntimeError):
    """An `audit.auth_events` row was attempted for a request off the audited attempt path."""


class AuthAttempt:
    """One request, classified against the operation inventory from its matched route and
    method. Classification happens on route metadata, so it is available before the shared
    pre-handler barrier runs and does not depend on how far the handler got."""

    # [impl->req~shared-audited-path-entry~1]
    def __init__(self, method: str, path: str, *, route_template: str | None = None):
        self.method = method.upper()
        self.path = path
        self.route = route_template or path
        self.operation = match_operation(self.method, path)
        self.on_audited_path = self.operation is not None
        self.audited = False


class AuthResultCounter:
    """The bounded-cardinality counter metric labeled by result, bounded reason and route.
    It is mandatory wherever the barrier rejects, on and off the audited path alike."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str, str], int] = {}

    def increment(self, *, result: AuthEventResult, route: str, reason: str | None = None) -> None:
        key = (str(result), reason or "none", route)
        self._counts[key] = self._counts.get(key, 0) + 1

    def value(self, *, result: AuthEventResult, route: str, reason: str | None = None) -> int:
        return self._counts.get((str(result), reason or "none", route), 0)

    def labels(self) -> list[tuple[str, str, str]]:
        return sorted(self._counts)


class AuthAuditWriter:
    """Writes the single durable audit row an on-path attempt owes, and keeps every barrier
    result first-class off the path through the security log and the counter metric."""

    def __init__(self,
                 *,
                 sink: AuthEventSink,
                 counter: AuthResultCounter,
                 session_factory: Callable[[], AbstractAsyncContextManager[Any]] | None = None):
        self._sink = sink
        self._counter = counter
        self._session_factory = session_factory

    def _claim(self, attempt: AuthAttempt) -> None:
        # [impl->req~shared-path-single-audit-row~1]
        # [impl->req~shared-off-path-no-audit-row~1]
        if not attempt.on_audited_path:
            raise OffPathAuditError(f"{attempt.method} {attempt.path} is not on the audited path")
        if attempt.audited:
            raise AuditAlreadyWrittenError(f"{attempt.operation} already audited this attempt")
        attempt.audited = True

    async def write_in_transaction(self,
                                   session: Any,
                                   attempt: AuthAttempt,
                                   event: AuthEvent) -> None:
        """An attempt that reaches a consuming or mutating transaction writes its row inside
        that transaction, atomically with any challenge consumption and any state change."""
        # [impl->req~shared-audit-write-in-transaction~1]
        # [impl->req~shared-audit-obligation-of-path~1]
        self._claim(attempt)
        await self._sink.insert(session, event)
        self._count(attempt, event)

    async def write_standalone(self, attempt: AuthAttempt, event: AuthEvent) -> None:
        """An attempt rejected before such a transaction exists writes its row as a standalone
        durable write in its own transaction."""
        # [impl->req~shared-audit-write-standalone~1]
        if self._session_factory is None:
            raise RuntimeError("no session factory configured for standalone audit writes")
        self._claim(attempt)
        async with self._session_factory() as session:
            await self._sink.insert(session, event)
            await session.commit()
        self._count(attempt, event)

    async def record_rejection(self,
                               attempt: AuthAttempt,
                               event: AuthEvent,
                               error: Exception,
                               *,
                               session: Any | None = None) -> Exception:
        """Write the attempt's row before the response is returned, then hand back the
        rejection the attempt earned. Never best-effort: a failed write is logged, and the
        client still receives that same rejection rather than a different outcome."""
        # [impl->req~shared-audit-write-before-response~1]
        try:
            if session is None:
                await self.write_standalone(attempt, event)
            else:
                await self.write_in_transaction(session, attempt, event)
        except (AuditAlreadyWrittenError, OffPathAuditError):
            raise
        except Exception:
            logger.error("auth_audit_write_failed",
                         operation=str(attempt.operation), result=str(event.result),
                         route=attempt.route, exc_info=True)
            self._count(attempt, event)
        return error

    def record_off_path(self,
                        attempt: AuthAttempt,
                        result: AuthEventResult,
                        *,
                        reason: str | None = None) -> None:
        """Off the path no `audit.auth_events` row is ever written: the stable internal result
        code goes to the structured security log and the counter metric instead."""
        # [impl->req~shared-off-path-no-audit-row~1]
        # [impl->req~shared-barrier-result-first-class~1]
        if attempt.on_audited_path:
            raise OffPathAuditError(f"{attempt.method} {attempt.path} is on the audited path")
        logger.warning("auth_rejected", result=str(result), reason=reason, route=attempt.route)
        self._counter.increment(result=result, route=attempt.route, reason=reason)

    def _count(self, attempt: AuthAttempt, event: AuthEvent) -> None:
        if event.result in BARRIER_RESULTS:
            reason = event.details.get("reason")
            self._counter.increment(result=event.result, route=attempt.route,
                                    reason=str(reason) if reason is not None else None)
