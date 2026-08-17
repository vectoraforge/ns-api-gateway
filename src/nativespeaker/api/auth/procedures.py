"""The shared prepare and completion procedures every challenge-bearing auth endpoint uses.

Prepare issues one single-use challenge and mutates no business state. Completion runs the
numbered backend obligations in order — barrier, lookup, binding, the claim, the variant
comparison, proof and provider work, then one short database-only consuming transaction — and
the numbered order is the rejection precedence.
"""

import re
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid7

from nativespeaker.api.auth.audit import (
    BARRIER_RESULTS,
    NO_ACTOR,
    AttemptPhase,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEvent,
    AuthEventResult,
    terminal_event,
)
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import (
    ChallengeError,
    ChallengeRow,
    ChallengeState,
    ChallengeStore,
    ClaimOutcome,
    ConsumeOutcome,
    IdentityBinding,
    PrepareResponse,
    SubjectVerifier,
    advance_state,
    assert_no_proof_material_bound,
    assert_nothing_serialized,
    authoritative_binding,
    challenge_expires_at,
    challenge_ids_equal,
    new_challenge_id,
    variants_equal,
)
from nativespeaker.api.auth.flow import OperationMismatchError, assert_challenge_bearing
from nativespeaker.api.auth.modes import CHALLENGE_QUERY_PARAM, CHALLENGE_QUERY_VALUE
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    is_challenge_bearing,
    route_for,
    variants_for,
)
from nativespeaker.api.auth.routes import is_pre_auth_callable, requires_id_token
from nativespeaker.api.auth.taxonomy import (
    UnsurfacedResultError,
    register_client_class,
    surface,
)
from nativespeaker.api.exceptions import ErrorCode, ServiceError

__all__ = ["ChallengeLookupUnavailableError", "ChallengeRejection", "SharedChallengeService",
           "TransientTransactionError", "UnsurfacedResultError", "challenge_id_shape",
           "prepare_mode_supported", "reconciliation_options", "register_client_class",
           "surface"]

# --- Taxonomy surfacing -------------------------------------------------------------------


class ChallengeRejection(ServiceError):
    """A rejection on a challenge-bearing endpoint, carrying the specific internal result for
    the audit row and the shared class for the client. The shared client-error taxonomy lives
    in one module and governs every authenticated route, the shared pre-handler barrier
    included: rejections surface through those classes alone, and a `core.auth_event_result`
    value is never exposed."""

    # [impl->req~shared-completion-taxonomy-surfacing~1]
    # [impl->req~shared-error-classes-govern-all-routes~1]
    # [impl->req~shared-error-no-internal-results-exposed~1]
    def __init__(self, result: AuthEventResult, *, detail: str | None = None):
        self.result = result
        self.detail = detail
        error_code, status_code = surface(result)
        self.error_code = error_code
        self.status_code = status_code
        super().__init__("Auth operation rejected")


class TransientTransactionError(RuntimeError):
    """The consuming transaction failed transiently — a lost commit acknowledgment included."""


class ChallengeLookupUnavailableError(ServiceError):
    """The challenge lookup could not be completed. An infrastructure failure, never the
    definitive `challenge_not_found`."""
    status_code = 503
    error_code: ErrorCode = "service_unavailable"


_CHALLENGE_ID_SHAPE = re.compile(r"^[A-Za-z0-9_-]{22}$")


def challenge_id_shape(challenge_id: str) -> str:
    """The malformed-versus-unknown debugging detail, which belongs in `audit.auth_events`
    `details`. The raw identifier is never written to the audit row and never logged."""
    # [impl->req~shared-challenge-not-found-scope~1]
    return "unknown_challenge_id" if _CHALLENGE_ID_SHAPE.match(challenge_id) \
        else "malformed_challenge_id"


def reconciliation_options() -> tuple[tuple[str, str], str]:
    """After losing the response to a state-changing attempt the client does not replay it: it
    calls `/auth/sync` again and uses the current resolved backend state, or calls the concrete
    endpoint again with `challenge=true` to start a whole fresh attempt. The server offers no
    third option, because it stores no completion result to hand back."""
    # [impl->req~shared-single-use-client-reconciliation~1]
    return route_for(AuthOperation.sync), f"{CHALLENGE_QUERY_PARAM}={CHALLENGE_QUERY_VALUE}"


# --- The endpoint-specific half ------------------------------------------------------------


class ChallengeEndpoint(Protocol):
    """The endpoint half of a challenge-bearing operation. The shared procedures call these
    hooks and nothing else, so prepare has no way to reach a mutation."""

    operation: AuthOperation

    async def check_prepare_eligibility(self, identity: VerifiedIdentityContext,
                                        variant: IdentityProvider | None) -> None:
        """Cheap basic eligibility for the named operation and variant. Reads only."""
        ...

    async def verify_proof(self, identity: VerifiedIdentityContext, challenge: ChallengeRow,
                           body: Mapping[str, Any] | None) -> Any:
        """Verify the endpoint's proof set against the exact challenge contents and perform any
        required live provider interaction. Runs with no open database session."""
        ...

    async def confirm_live_state(self, session: Any, identity: VerifiedIdentityContext,
                                 challenge: ChallengeRow) -> Any:
        """Re-resolve all endpoint-required state inside the consuming transaction."""
        ...

    async def mutate(self, session: Any, identity: VerifiedIdentityContext,
                     challenge: ChallengeRow, proof: Any, live: Any) -> Any:
        """Perform the mutation and return the resulting backend state."""
        ...


def prepare_mode_supported(operation: AuthOperation) -> bool:
    """Prepare mode exists for the challenge-bearing subset alone. On any other endpoint in the
    inventory `challenge=true` is not a recognized signal."""
    # [impl->req~shared-prepare-mode-signal~1]
    return is_challenge_bearing(operation)


class SharedChallengeService:
    """The shared prepare and completion procedures."""

    def __init__(self,
                 *,
                 store: ChallengeStore,
                 audit: AuthAuditWriter,
                 session_factory: Callable[[], AbstractAsyncContextManager[Any]],
                 subject_verifier: SubjectVerifier,
                 clock: Callable[[], datetime] | None = None,
                 transaction_attempts: int = 3):
        self._store = store
        self._audit = audit
        self._session_factory = session_factory
        self._subject_verifier = subject_verifier
        self._clock = clock or (lambda: datetime.now(UTC))
        self._transaction_attempts = transaction_attempts
        self._open_sessions = 0

    # --- prepare --------------------------------------------------------------------------

    async def prepare(self,
                      operation: AuthOperation,
                      variant: IdentityProvider | None,
                      identity: Any,
                      endpoint: ChallengeEndpoint,
                      *,
                      attempt: AuthAttempt | None = None,
                      body: Mapping[str, Any] | None = None) -> PrepareResponse:
        """Prepare mode, in the order the obligations are numbered."""
        # [impl->req~shared-prepare-mode-obligations~1]
        # [impl->req~shared-challenge-wire-contract~1]
        if not prepare_mode_supported(operation):
            # [impl->req~shared-prepare-mode-signal~1]
            raise ChallengeError(f"{operation} has no prepare mode")
        assert_challenge_bearing(operation)
        if endpoint.operation is not operation:
            raise OperationMismatchError(f"{endpoint.operation} cannot prepare {operation}")
        attempt = attempt or self._attempt(operation)

        # 1. consume the typed identity context the shared barrier produced.
        # [impl->req~shared-prepare-step-01~1]
        context = await self._require_identity_context(attempt, identity)

        # 3. a pre-auth identity is admitted only for create_user; 4. neither a historical
        # identity nor a blocked user is admitted. Both are barrier rejections, enforced before
        # any prepare logic runs.
        # [impl->req~shared-prepare-step-03~1]
        # [impl->req~shared-prepare-step-04~1]
        await self._require_barrier_outcome(attempt, operation, context)

        # 2. derive the challenge binding from that verified context.
        # [impl->req~shared-prepare-step-02~1]
        binding = self.derive_binding(context)

        # 5. normalize and validate the client-selected variant, then only cheap eligibility.
        # [impl->req~shared-prepare-step-05~1]
        # [impl->req~shared-wire-provider-normalization~1]
        variant = self._validated_variant(operation, variant)
        await self._check_prepare_eligibility(attempt, operation, variant, context, endpoint)

        # 6. issue a single-use challenge bound to that context, expiring on the server's own
        # clock, in lifecycle state `issued`.
        # [impl->req~shared-prepare-step-06~1]
        row = ChallengeRow(challenge_id=new_challenge_id(),
                           operation=operation,
                           operation_variant=variant,
                           binding=binding,
                           expires_at=challenge_expires_at(self._clock()),
                           state=ChallengeState.issued,
                           id=uuid7())
        assert_no_proof_material_bound(row, body)

        # 7. persist it server-side as one `core.auth_challenges` row keyed by `challenge_id`.
        # [impl->req~shared-prepare-step-07~1]
        await self._store.insert(row)

        # 8. return `challenge_id` and `expires_at`, and nothing else.
        # [impl->req~shared-prepare-step-08~1]
        response = PrepareResponse(challenge_id=row.challenge_id, expires_at=row.expires_at)
        assert_nothing_serialized(response, row)

        # 9. no business-state mutation: prepare never opens the consuming transaction and never
        # reaches the endpoint's live-state or mutation hooks.
        # [impl->req~shared-prepare-step-09~1]
        return response

    def derive_binding(self, context: VerifiedIdentityContext) -> IdentityBinding:
        """`external_identity_id` for a linked identity, or the backend-verified issuer with the
        keyed verifier computed from the backend-verified subject for a pre-auth identity."""
        # [impl->req~shared-prepare-step-02~1]
        # [impl->req~shared-challenge-row-identity-context~1]
        if context.outcome is ResolutionOutcome.linked:
            if context.external_identity_id is None:
                raise ChallengeError("a linked identity context carries an external identity id")
            return IdentityBinding(bound_external_identity_id=context.external_identity_id)
        return IdentityBinding(preauth_issuer=context.issuer,
                               preauth_subject_hash=self._subject_verifier(context.subject))

    def _validated_variant(self, operation: AuthOperation,
                           variant: IdentityProvider | None) -> IdentityProvider | None:
        """The variant persisted on the row is the normalized declaration prepare produced, by
        exact case-sensitive match against the identity-provider enumeration."""
        # [impl->req~shared-wire-provider-normalization~1]
        allowed = variants_for(operation)
        if allowed and variant not in allowed:
            raise ChallengeError(f"{variant} is not a normalized variant of {operation}")
        if not allowed and variant is not None:
            raise ChallengeError(f"{operation} defines no operation variant")
        return variant

    async def _check_prepare_eligibility(self, attempt: AuthAttempt, operation: AuthOperation,
                                         variant: IdentityProvider | None,
                                         context: VerifiedIdentityContext,
                                         endpoint: ChallengeEndpoint) -> None:
        # An already-linked identity at `create_user` prepare is rejected here, not later.
        # [impl->req~shared-prepare-step-05~1]
        if operation is AuthOperation.create_user and context.outcome is ResolutionOutcome.linked:
            raise await self._reject(attempt, AttemptPhase.prepare,
                                     AuthEventResult.identity_already_linked, context)
        try:
            await endpoint.check_prepare_eligibility(context, variant)
        except ChallengeRejection as exc:
            raise await self._reject(attempt, AttemptPhase.prepare, exc.result, context,
                                     detail=exc.detail) from None

    # --- completion -----------------------------------------------------------------------

    async def complete(self,
                       operation: AuthOperation,
                       declared_variant: str | None,
                       challenge_id: str,
                       identity: Any,
                       endpoint: ChallengeEndpoint,
                       *,
                       attempt: AuthAttempt | None = None,
                       body: Mapping[str, Any] | None = None) -> Any:
        """The completion procedure. The numbered order below is the rejection precedence: when
        several conditions hold, the earliest failed step is the one that rejects."""
        # [impl->req~shared-completion-backend-obligations~1]
        # [impl->req~shared-completion-rejection-precedence~1]
        # This section binds the challenge-bearing endpoints and only them.
        # [impl->req~shared-completion-scope~1]
        assert_challenge_bearing(operation)
        # Each endpoint attempts exactly the operation it names and never falls through.
        # [impl->req~shared-completion-no-fallthrough~1]
        if endpoint.operation is not operation:
            raise OperationMismatchError(f"{endpoint.operation} cannot complete {operation}")
        attempt = attempt or self._attempt(operation)

        # The external IDP ID token in `Authorization` is the completion's authentication.
        # [impl->req~shared-completion-request-id-token~1]
        if not requires_id_token(*route_for(operation)):
            raise ChallengeError(f"{operation} must require the external IDP ID token")

        # 1-4. the barrier's checks, all of them ahead of every challenge check.
        context = await self._require_identity_context(attempt, identity)   # step 1
        await self._require_barrier_outcome(attempt, operation, context)    # steps 2-4

        # 5. locate the challenge row by the completion's `challenge_id`, compared byte-for-byte
        # against the stored value.
        # [impl->req~shared-completion-step-05~1]
        # [impl->req~shared-completion-request-challenge-id~1]
        # [impl->req~shared-wire-completion-body~1]
        try:
            row = await self._store.get(challenge_id) if challenge_id else None
        except Exception as cause:
            # `challenge_not_found` covers only a lookup that definitively finds no row: a
            # database outage while looking up the challenge remains the ordinary
            # infrastructure-failure result.
            # [impl->req~shared-challenge-not-found-scope~1]
            raise await self._lookup_unavailable(attempt, context, cause) from None
        if row is None or not challenge_ids_equal(challenge_id, row.challenge_id):
            # 7. an unknown `challenge_id` rejects before any consumption. Whether the handle
            # was malformed or merely unknown is a `details` field, never the raw identifier.
            # [impl->req~shared-completion-step-07~1]
            # [impl->req~shared-challenge-not-found-scope~1]
            raise await self._reject(attempt, AttemptPhase.business,
                                     AuthEventResult.challenge_not_found, context,
                                     detail=challenge_id_shape(challenge_id))

        # 6. verify the operation binding and the bound identity context. The operation, the
        # variant, the binding and the expiry are read from the server-held row and from no
        # copy the completion supplied.
        # [impl->req~shared-completion-step-06~1]
        # [impl->req~shared-wire-server-held-state~1]
        bound_operation, bound_variant, _, _ = authoritative_binding(row)
        if bound_operation is not operation:
            raise await self._reject(attempt, AttemptPhase.business,
                                     AuthEventResult.challenge_operation_mismatch, context, row=row)
        if row.verifier_cleared:
            # A pre-auth-bound row whose verifier consumption already cleared is not compared at
            # all: it takes the step 8 already-used rejection.
            raise await self._reject(attempt, AttemptPhase.business,
                                     AuthEventResult.challenge_consumed, context, row=row)
        if not self.binding_matches(row, context):
            # 7. a bound-context mismatch leaves the located challenge unconsumed.
            # [impl->req~shared-completion-step-07~1]
            raise await self._reject(attempt, AttemptPhase.business,
                                     AuthEventResult.challenge_identity_mismatch, context, row=row)

        # 8. claim the row for this attempt before any endpoint-specific work runs. Completion
        # attempts for one `challenge_id` therefore have exactly two outcomes: this attempt
        # claims the row, or it fails as already used right here.
        # [impl->req~shared-completion-step-08~1]
        # [impl->req~shared-single-use-completion-outcomes~1]
        claim_attempt_id = uuid7()
        outcome = await self._store.claim(row.challenge_id, claim_attempt_id)
        if outcome is not ClaimOutcome.claimed:
            # The already-used branch: it fails at the claim, before any proof verification or
            # provider call, so it performs no provider work and causes no duplicate mutation.
            # No stored success result is ever handed back for a claimed or consumed
            # challenge — same-challenge replay is not allowed, and the duplicate receives the
            # generic already-used conflict rather than the outcome of the attempt holding the
            # claim. The claiming update is also the only place expiry is evaluated.
            # [impl->req~shared-single-use-already-used-branch~1]
            # [impl->req~shared-single-use-no-stored-result~1]
            # [impl->req~shared-challenge-required-remediation~1]
            # [impl->req~shared-completion-loser-no-work~1]
            # [impl->req~shared-claimed-challenge-is-dead~1]
            result = (AuthEventResult.challenge_expired if outcome is ClaimOutcome.expired
                      else AuthEventResult.challenge_not_found
                      if outcome is ClaimOutcome.not_found
                      else AuthEventResult.challenge_consumed)
            raise await self._reject(attempt, AttemptPhase.business, result, context, row=row)

        # The claim branch: this attempt claimed the challenge exactly once and now proceeds
        # through one completion attempt for the exact challenge-bound identity context and
        # operation. From here the row is dead — every exit consumes it, whether the
        # operation-variant, proof and live-state checks then succeed or fail — and it never
        # returns to `issued`.
        # [impl->req~shared-single-use-claim-branch~1]
        # [impl->req~shared-claimed-challenge-is-dead~1]
        # [impl->req~shared-challenge-lifecycle-one-way~1]
        row = replace(row, state=advance_state(row.state, ChallengeState.claimed),
                      claim_attempt_id=claim_attempt_id)
        try:
            # 9. compare the completion's `provider` against the stored operation variant.
            # [impl->req~shared-completion-step-09~1]
            # [impl->req~shared-completion-request-provider~1]
            if not variants_equal(declared_variant, bound_variant):
                raise ChallengeRejection(AuthEventResult.challenge_operation_mismatch)

            # 10. proof verification and live provider interaction, only now that this attempt
            # holds the claim, and with no transaction, row lock or open session held across it.
            # [impl->req~shared-completion-step-10~1]
            # [impl->req~shared-completion-proof-after-claim~1]
            # [impl->req~shared-completion-request-proof-material~1]
            if self._open_sessions:
                raise ChallengeError("no database session may be held across provider work")
            proof = await endpoint.verify_proof(context, row, body)
        except ChallengeRejection as exc:
            await self._consume_after_rejection(attempt, context, row, claim_attempt_id, exc)
            raise

        # 11-13. the short, database-only consuming transaction.
        return await self._consuming_transaction(attempt, endpoint, context, row,
                                                 claim_attempt_id, proof)

    def binding_matches(self, row: ChallengeRow, context: VerifiedIdentityContext) -> bool:
        """A linked identity's `external_identity_id` must equal `bound_external_identity_id`; a
        pre-auth binding matches only where the issuer equals `preauth_issuer` and the verifier
        recomputed from this request's backend-verified subject equals `preauth_subject_hash`,
        even if that subject has since become linked."""
        # [impl->req~shared-completion-step-06~1]
        if row.binding.bound_external_identity_id is not None:
            return (context.outcome is ResolutionOutcome.linked
                    and context.external_identity_id == row.binding.bound_external_identity_id)
        return (row.binding.preauth_issuer == context.issuer
                and row.binding.preauth_subject_hash == self._subject_verifier(context.subject))

    async def _consuming_transaction(self, attempt: AuthAttempt, endpoint: ChallengeEndpoint,
                                     context: VerifiedIdentityContext, row: ChallengeRow,
                                     claim_attempt_id: UUID, proof: Any) -> Any:
        """One short database-only transaction: re-resolve, mutate, consume the challenge and
        write the attempt's audit row, atomically. It makes no provider call and never re-checks
        `expires_at`. A transient failure is retried as the same local transaction under the same
        `claim_attempt_id`, and the retry never repeats a provider call that already ran."""
        # [impl->req~shared-completion-step-12~1]
        remaining = self._transaction_attempts
        while True:
            remaining -= 1
            try:
                return await self._run_consuming_transaction(attempt, endpoint, context, row,
                                                             claim_attempt_id, proof)
            except TransientTransactionError:
                if remaining <= 0:
                    raise
                # The attempt recognizes its own claim on retry instead of reading it as a
                # conflicting duplicate; nothing above this line runs again.
                attempt.audited = False

    async def _run_consuming_transaction(self, attempt: AuthAttempt, endpoint: ChallengeEndpoint,
                                         context: VerifiedIdentityContext, row: ChallengeRow,
                                         claim_attempt_id: UUID, proof: Any) -> Any:
        rejection: ChallengeRejection | None = None
        result: Any = None
        async with self._open_session() as session:
            try:
                # 11. re-resolve all endpoint-required state and confirm the live state still
                # satisfies the endpoint's rules.
                # [impl->req~shared-completion-step-11~1]
                live = await endpoint.confirm_live_state(session, context, row)
                # 13. mutate only if the live state still satisfies those rules.
                # [impl->req~shared-completion-step-13~1]
                result = await endpoint.mutate(session, context, row, proof, live)
            except ChallengeRejection as exc:
                rejection = exc

            # 12. consume the challenge exactly once for the claim-holding attempt, atomically
            # with the audit record and any successful mutation, on success and rejection alike.
            # [impl->req~shared-completion-step-12~1]
            consumed = await self._store.consume(session, row.challenge_id, claim_attempt_id)
            if consumed is ConsumeOutcome.already_consumed_by_this_attempt:
                # A retry after a lost commit acknowledgment: the earlier transaction committed
                # this attempt's consumption and its one audit row.
                return result
            if consumed is ConsumeOutcome.lost and rejection is None:
                rejection = ChallengeRejection(AuthEventResult.challenge_consumed)

            if rejection is not None:
                event = self._event(AttemptPhase.business, rejection.result, attempt, context,
                                    row=row, detail=rejection.detail)
                await self._audit.record_rejection(attempt, event, rejection, session=session)
            else:
                event = self._event(AttemptPhase.success, AuthEventResult.succeeded, attempt,
                                    context, row=row)
                await self._audit.write_in_transaction(session, attempt, event)
            await session.commit()

        if rejection is not None:
            raise rejection
        # 14. return the resulting backend state. No backend token is reissued.
        # [impl->req~shared-completion-step-14~1]
        return result

    async def _consume_after_rejection(self, attempt: AuthAttempt, context: VerifiedIdentityContext,
                                       row: ChallengeRow, claim_attempt_id: UUID,
                                       rejection: ChallengeRejection) -> None:
        """A claimed challenge is dead: a variant mismatch, a rejected proof or an exhausted
        vendor budget consumes it, atomically with the attempt's audit record."""
        # [impl->req~shared-claimed-challenge-is-dead~1]
        # [impl->req~shared-completion-step-12~1]
        async with self._open_session() as session:
            await self._store.consume(session, row.challenge_id, claim_attempt_id)
            event = self._event(AttemptPhase.business, rejection.result, attempt, context,
                                row=row, detail=rejection.detail)
            await self._audit.record_rejection(attempt, event, rejection, session=session)
            await session.commit()

    @asynccontextmanager
    async def _open_session(self) -> AsyncIterator[Any]:
        """Sessions are opened only around the short consuming transaction, so the count is the
        proof that no session is held across proof verification or a provider call."""
        self._open_sessions += 1
        try:
            async with self._session_factory() as session:
                yield session
        finally:
            self._open_sessions -= 1

    # --- shared helpers -------------------------------------------------------------------

    def _attempt(self, operation: AuthOperation) -> AuthAttempt:
        method, path = route_for(operation)
        return AuthAttempt(method, path, route_template=path)

    async def _require_identity_context(self, attempt: AuthAttempt,
                                        identity: Any) -> VerifiedIdentityContext:
        """The typed verified identity context the barrier produced. Its absence means the
        Bearer token was never verified, and that rejection precedes every challenge check."""
        # [impl->req~shared-completion-step-01~1]
        # [impl->req~shared-prepare-step-01~1]
        if not isinstance(identity, VerifiedIdentityContext):
            raise await self._reject(attempt, AttemptPhase.barrier,
                                     AuthEventResult.invalid_external_jwt, None)
        return identity

    async def _require_barrier_outcome(self, attempt: AuthAttempt, operation: AuthOperation,
                                       context: VerifiedIdentityContext) -> None:
        """The barrier's route-admission, historical-identity and blocked-user rules, in that
        order, all of them before any challenge check."""
        # [impl->req~shared-completion-step-02~1]
        # [impl->req~shared-prepare-step-03~1]
        if (context.outcome is ResolutionOutcome.pre_auth
                and not is_pre_auth_callable(*route_for(operation))):
            raise await self._reject(attempt, AttemptPhase.barrier,
                                     AuthEventResult.preauth_identity_not_allowed, context)
        # [impl->req~shared-completion-step-03~1]
        # [impl->req~shared-prepare-step-04~1]
        if context.outcome is ResolutionOutcome.historical_identity:
            raise await self._reject(attempt, AttemptPhase.barrier,
                                     AuthEventResult.historical_identity, context)
        # [impl->req~shared-completion-step-04~1]
        if context.outcome is ResolutionOutcome.blocked_user:
            raise await self._reject(attempt, AttemptPhase.barrier,
                                     AuthEventResult.blocked_user, context)

    def _actor(self, context: VerifiedIdentityContext | None) -> AuthActor:
        if context is None:
            return NO_ACTOR
        return AuthActor(issuer=context.issuer,
                         subject_hash=self._subject_verifier(context.subject),
                         provider=context.provider)

    def _event(self, phase: AttemptPhase, result: AuthEventResult, attempt: AuthAttempt,
               context: VerifiedIdentityContext | None, *, row: ChallengeRow | None = None,
               detail: str | None = None) -> AuthEvent:
        # A race the consuming transaction closes can still land on a barrier state; the row
        # records it as the barrier result it is.
        if result in BARRIER_RESULTS:
            phase = AttemptPhase.barrier
        # `challenge_row_id` is the internal row id; the public handle is never recorded.
        details = {"route": attempt.route}
        if detail:
            details["reason"] = detail
        return terminal_event(phase, result, operation=attempt.operation,
                              actor=self._actor(context),
                              challenge_row_id=row.id if row is not None else None,
                              details=details)

    async def _reject(self, attempt: AuthAttempt, phase: AttemptPhase, result: AuthEventResult,
                      context: VerifiedIdentityContext | None, *,
                      row: ChallengeRow | None = None,
                      detail: str | None = None) -> Exception:
        """Audit the rejection before the response is returned, then hand back the error. Every
        rejection inside the endpoint — barrier, prepare phase, request validation, or the
        consuming transaction — owes that row, whether or not a mutation completed."""
        # [impl->req~shared-completion-audit-obligation~1]
        # [impl->req~shared-rejection-audit-required~1]
        # [impl->req~shared-rejection-audit-scope~1]
        error = ChallengeRejection(result, detail=detail)
        event = self._event(phase, result, attempt, context, row=row, detail=detail)
        return await self._audit.record_rejection(attempt, event, error)

    async def _lookup_unavailable(self, attempt: AuthAttempt,
                                  context: VerifiedIdentityContext | None,
                                  cause: Exception) -> Exception:
        """An infrastructure failure looking the challenge up: audited as the ordinary internal
        failure, never as the definitive `challenge_not_found`, and the raw identifier the
        client sent is not part of the record."""
        # [impl->req~shared-challenge-not-found-scope~1]
        error = ChallengeLookupUnavailableError(str(type(cause).__name__))
        event = self._event(AttemptPhase.business, AuthEventResult.internal_error, attempt,
                            context, detail="challenge_lookup_unavailable")
        return await self._audit.record_rejection(attempt, event, error)
