"""The shared, mandatory, default-on pre-handler barrier.

It is the only place external JWT acceptance and the four identity-resolution outcomes are
evaluated. Handlers consume its typed output and never verify tokens or resolve identity
themselves.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from nativespeaker.api.auth.audit import (
    MOVEMENT_OPERATIONS,
    NO_ACTOR,
    AttemptPhase,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEvent,
    AuthEventResult,
    SubjectHasher,
    terminal_event,
)
from nativespeaker.api.auth.integration import FirebaseIntegrations
from nativespeaker.api.auth.movement import movement_event, unresolved_movement_context
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.routes import (
    RouteCategory,
    categorize,
    is_pre_auth_callable,
    resolve_route_template,
)
from nativespeaker.api.auth.taxonomy import client_response, surface
from nativespeaker.api.auth.tokens import InvalidExternalJwtError, JwtRejectionReason
from nativespeaker.api.exceptions import ServiceError

BEARER_SCHEME = "bearer"

# The one request field the backend reads for authentication. There is no second backend check:
# no formal header registry, no header-canonicalization matrix, and no dual read of a header and
# the token with an equality check between them, because the one check is cryptographic.
# [impl->req~sessions-no-second-backend-header-check~1]
# [impl->req~sessions-backend-ignores-identity-headers~1]
# [impl->req~sessions-wire-no-alternate-token-location~1]
IDENTITY_HEADER = "authorization"


class BarrierRejectionError(ServiceError):
    """A barrier rejection, surfaced through the shared client-error taxonomy that governs
    every authenticated route. The internal `core.auth_event_result` is never exposed to the
    client, and neither is the bounded rejection reason it carries for the audit row."""

    # [impl->req~shared-error-classes-govern-all-routes~1]
    # [impl->req~shared-error-no-internal-results-exposed~1]
    # [impl->req~shared-invalid-external-jwt-reasons~1]
    def __init__(self, result: AuthEventResult, reason: str | None = None):
        self.result = result
        self.reason = reason
        error_code, status_code = surface(result)
        self.error_code = error_code
        self.status_code = status_code
        self.rejection = client_response(error_code)
        super().__init__("Authentication failed")

    def body(self) -> dict[str, str]:
        """The shared response shape: it names the class and nothing else."""
        return self.rejection.body


class ResolutionOutcome(StrEnum):
    """The four per-request identity-resolution outcomes."""
    pre_auth = "pre_auth"
    historical_identity = "historical_identity"
    blocked_user = "blocked_user"
    linked = "linked"


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    outcome: ResolutionOutcome
    user_id: UUID | None = None
    external_identity_id: UUID | None = None
    provider: IdentityProvider | None = None
    registered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VerifiedIdentityContext:
    """The typed verified identity context handlers consume. `issuer` and `subject` come from
    the backend-verified token claims and from nowhere else; `provider` is never sourced from
    headers or claims."""
    issuer: str
    subject: str
    outcome: ResolutionOutcome
    user_id: UUID | None = None
    external_identity_id: UUID | None = None
    provider: IdentityProvider | None = None
    registered_at: datetime | None = None


class IdentityResolver(Protocol):
    async def resolve(self, issuer: str, subject: str) -> ResolvedIdentity:
        """Resolve a backend-verified `(issuer, subject)` through `core.external_identities`
        and `core.users`."""
        ...


def barrier_result_for(outcome: ResolutionOutcome,
                       method: str,
                       path: str) -> AuthEventResult | None:
    """The barrier's three identity-policy rules, in one place: the historical-identity rule,
    the blocked-user rule, and the route-admission rule for a pre-auth identity. `None` means
    the outcome is admitted. Every enforcement point — the barrier itself and the completion
    procedure's re-checks — reads this predicate rather than restating the rules, so an
    account-blocking rule can never drift between two copies."""
    # [impl->req~shared-prehandler-barrier~1]
    # [impl->req~shared-invariant-03~1]
    match outcome:
        case ResolutionOutcome.historical_identity:
            # Once an external identity has transitioned to `historical`, every subsequent
            # request for it is rejected here, at per-request resolution.
            return AuthEventResult.historical_identity
        case ResolutionOutcome.blocked_user:
            return AuthEventResult.blocked_user
        case ResolutionOutcome.pre_auth:
            if not is_pre_auth_callable(method, path):
                return AuthEventResult.preauth_identity_not_allowed
    return None


def extract_bearer_token(authorization_values: Sequence[str]) -> str:
    """The `Authorization` field is the sole identity carrier, per RFC 6750: exactly one field
    value carrying exactly one well-formed `Bearer` credential.

    Zero field instances, several of them, a comma-joined or folded value, several credentials,
    an empty token, and trailing content after the token are all rejected here. None of them is
    ever resolved by taking the first or the last value, and none by concatenation. HTTP field
    names are case-insensitive, so differently-cased occurrences of the field arrive in this one
    list and count as duplicates; the rejection therefore happens before any value is picked.
    The scheme name matches case-insensitively, while the token bytes stay case-sensitive."""
    # [impl->req~shared-bearer-single-identity-carrier~1]
    # [impl->req~shared-wire-contract-owner~1]
    # [impl->req~sessions-bearer-firebase-id-token~1]
    # [impl->req~sessions-wire-authorization-bearer-sole-carrier~1]
    # [impl->req~sessions-wire-exactly-one-credential~1]
    # [impl->req~sessions-wire-case-insensitive-duplicate-fields~1]
    if len(authorization_values) > 1:
        raise InvalidExternalJwtError(JwtRejectionReason.duplicate_authorization)
    if not authorization_values:
        raise InvalidExternalJwtError(JwtRejectionReason.missing_token)
    value = authorization_values[0]
    # A comma-joined or folded value carries more than one field value. It is a duplicate, never
    # a list to pick a credential out of.
    if "," in value or "\n" in value or "\r" in value:
        raise InvalidExternalJwtError(JwtRejectionReason.duplicate_authorization)
    # [impl->req~sessions-wire-bearer-scheme-case~1]
    scheme, separator, credential = value.partition(" ")
    if not separator or scheme.lower() != BEARER_SCHEME:
        raise InvalidExternalJwtError(JwtRejectionReason.malformed)
    if not credential:
        raise InvalidExternalJwtError(JwtRejectionReason.missing_token)
    # Exactly one credential and nothing after it: any further whitespace-separated content is a
    # second credential or trailing junk, and the token bytes themselves carry no whitespace.
    if any(character.isspace() for character in credential):
        raise InvalidExternalJwtError(JwtRejectionReason.malformed)
    return credential


class AuthBarrier:
    """Token verification plus identity resolution, in one place, for every authenticated
    route."""

    def __init__(self,
                 *,
                 integrations: FirebaseIntegrations,
                 resolver: IdentityResolver,
                 audit: AuthAuditWriter,
                 subject_hasher: SubjectHasher,
                 clock: Callable[[], datetime] | None = None):
        # The keyed subject hasher is a hard dependency, not an option: without it every
        # non-`invalid_external_jwt` rejection would build a row the audit contract refuses,
        # and the attempt's mandatory single audit row would be lost.
        # [impl->req~shared-audit-outcome-barrier-rejection~1]
        # [impl->req~shared-auth-events-actor-fields-null~1]
        if subject_hasher is None:
            raise ValueError("the barrier requires a keyed subject hasher for its audit actor")
        self._integrations = integrations
        self._resolver = resolver
        self._audit = audit
        self._subject_hasher = subject_hasher
        self._clock = clock or (lambda: datetime.now(UTC))

    async def admit(self,
                    attempt: AuthAttempt,
                    authorization_values: Sequence[str]) -> VerifiedIdentityContext:
        """Verify, resolve, enforce the route's identity policy, and return the typed context.
        Every rejection is audited on the path and counted everywhere.

        The backend's own cryptographic verification of the raw external IDP JWT runs here,
        ahead of identity resolution, on every authenticated request; no endpoint handler
        repeats or re-implements it, and nothing weaker than that verification satisfies it."""
        # [impl->req~shared-prehandler-barrier~1]
        # [impl->req~sessions-jwt-acceptance-policy-scope~1]
        # [impl->req~sessions-backend-authoritative-verifier~1]
        # Authenticated traffic, counted before any branch: the alert's fractional threshold is
        # a share of it, and every route that rejects here is inside that share.
        # [impl->req~sessions-invalid-external-jwt-metric-alert~1]
        self._audit.count_authenticated_request()
        try:
            token = extract_bearer_token(authorization_values)
            claims = self._integrations.verify_id_token(token)
        except InvalidExternalJwtError as exc:
            # Every acceptance failure folds into one contract whatever check produced it — a
            # missing, duplicated or malformed credential, a bad signature, a wrong `iss` or
            # `aud`, an expired token, an empty `sub` — auditing as `invalid_external_jwt` and
            # surfacing through `auth_required`. The bounded reason stays internal.
            # [impl->req~sessions-any-verification-failure-rejects~1]
            # [impl->req~sessions-acceptance-failures-single-contract~1]
            # [impl->req~sessions-acceptance-failure-internal-reason~1]
            # Verification supplied no permitted actor, so the row takes the actor-`NULL` shape.
            raise await self._reject(attempt, AuthEventResult.invalid_external_jwt,
                                     reason=str(exc.reason)) from None

        # Identity comes only from the verified claims: the lookup key is exactly the verified
        # `(iss, sub)`. No header, cookie, query parameter or body field contributes any part of
        # it, and the provider is never read from either.
        # [impl->req~shared-identity-from-verified-claims-only~1]
        # [impl->req~sessions-identity-from-verified-iss-sub~1]
        # [impl->req~sessions-lookup-keyed-on-issuer-subject~1]
        # [impl->req~sessions-users-id-not-auth-key~1]
        # [impl->req~sessions-wire-no-provider-derivation~1]
        resolved = await self._resolver.resolve(claims.issuer, claims.subject)
        actor = self._actor(claims.issuer, claims.subject, resolved)

        # [impl->req~shared-invariant-03~1]
        result = barrier_result_for(resolved.outcome, attempt.method, attempt.route)
        if result is not None:
            raise await self._reject(attempt, result, actor=actor)

        return VerifiedIdentityContext(issuer=claims.issuer,
                                       subject=claims.subject,
                                       outcome=resolved.outcome,
                                       user_id=resolved.user_id,
                                       external_identity_id=resolved.external_identity_id,
                                       provider=resolved.provider,
                                       registered_at=resolved.registered_at)

    def _actor(self, issuer: str, subject: str, resolved: ResolvedIdentity) -> AuthActor:
        """The actor columns. `actor_subject_hash` is the `actor_subject_hash` derivation
        family's value — the keyed HMAC over that family's domain-separated, canonicalized
        preimage, never over the bare subject — so the digest this row persists is the one the
        family defines and the same construction the pre-auth challenge binding uses.
        """
        # [impl->req~proof-family-actor-subject-hash~1]
        # [impl->req~proof-hmac-domain-separation~1]
        # [impl->req~proof-hmac-input-canonicalization~1]
        # [impl->req~shared-auth-events-actor-subject-hash~1]
        # Imported here rather than at module scope: the derived-identifier module sits above
        # this one in the import graph.
        from nativespeaker.api.auth.derived_identifiers import (  # noqa: PLC0415
            actor_subject_preimage,
        )
        subject_hash, key_version = self._subject_hasher(actor_subject_preimage(issuer, subject))
        return AuthActor(issuer=issuer,
                         subject_hash=subject_hash,
                         subject_hash_key_version=key_version,
                         provider=resolved.provider)

    async def _reject(self,
                      attempt: AuthAttempt,
                      result: AuthEventResult,
                      *,
                      actor: AuthActor = NO_ACTOR,
                      reason: str | None = None) -> Exception:
        """A barrier result is first-class either way: an `audit.auth_events` row on the path,
        the named result code in the security log and counter metric off it.

        Where the rejection is durably recorded depends on the route alone. On a route matched
        to a canonical state-changing auth operation it writes its own `audit.auth_events` row —
        `invalid_external_jwt` with `NULL` actor fields — never collapsed into a generic 401 log
        line. On every other authenticated route, `GET /users/me` and the chat and quota
        endpoints among them, it writes no row and stays first-class as the named result code in
        the structured security log and in the counter."""
        # [impl->req~sessions-acceptance-failure-durable-record-by-route~1]
        # [impl->req~shared-barrier-result-first-class~1]
        # [impl->req~shared-challenge-scope-narrower-subset~1]
        error = BarrierRejectionError(result, reason)
        if not attempt.on_audited_path:
            self._audit.record_off_path(attempt, result, reason=reason)
            return error
        details = {"reason": reason, "route": attempt.route} if reason else {"route": attempt.route}
        return await self._audit.record_rejection(
            attempt, self._event(attempt, result, actor, details), error)

    def _event(self, attempt: AuthAttempt, result: AuthEventResult, actor: AuthActor,
               details: dict[str, Any]) -> AuthEvent:
        """The single row the attempt owes. On the two account-movement routes that row carries
        the movement context for every attempt, rejected ones included: nothing is resolved yet
        at the barrier, so the context is the all-`NULL` one with the route's own unresolved
        classification rather than an omitted section."""
        # The row carries the result the barrier produced — `invalid_external_jwt` under the
        # actor-`NULL` shape, or `preauth_identity_not_allowed`, `historical_identity` or
        # `blocked_user` with the actor the verified token or resolved identity supplied — and
        # `operation` set to the operation route metadata matched before the barrier ran.
        # [impl->req~shared-upgrade-movement-context-required~1]
        # [impl->req~shared-restore-movement-classification~1]
        # [impl->req~shared-movement-single-audit-row~1]
        # [impl->req~schema-auth-events-barrier-rejection-row~1]
        if attempt.operation in MOVEMENT_OPERATIONS:
            context = unresolved_movement_context(attempt.operation, result, self._clock())
            return movement_event(AttemptPhase.barrier, context, actor=actor, details=details)
        return terminal_event(AttemptPhase.barrier, result,
                              operation=attempt.operation, actor=actor, details=details)


class AuthBarrierMiddleware(BaseHTTPMiddleware):
    """The one shared entry point: it reads the bearer token, verifies it, derives
    `(issuer, subject)`, resolves the identity and only then dispatches to the handler.

    It is applied to every route by default, so authentication is the default rather than the
    exception. Public routes — the health and readiness probes — pass through on an explicit
    enumerated allowlist, and the two provider-callback routes pass through as the third
    category, carrying the calling store's own credential and no Firebase ID token; the
    `Authorization` field of a callback request is forwarded to its handler untouched, because
    the backend, not this barrier, verifies that provider credential.
    """

    # [impl->req~sessions-shared-entry-point-three-way-partition~1]
    # [impl->req~sessions-authenticated-endpoint-families~1]
    # [impl->req~sessions-provider-callback-third-category~1]
    # [impl->req~sessions-gateway-forwards-pubsub-oidc-unchanged~1]
    # [impl->req~sessions-gateway-never-parses-apple-signedpayload~1]
    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        method = request.method
        path = request.url.path
        attempt = AuthAttempt(method, path,
                              route_template=resolve_route_template(method, path) or "other")
        request.state.auth_attempt = attempt
        if categorize(method, path) is RouteCategory.authenticated:
            barrier: AuthBarrier = request.app.state.auth_barrier
            try:
                # The sole identity carrier, read here and nowhere else: not from a query
                # parameter, a cookie, the body, an `X-*` header, a framework header alias or a
                # gateway-projected claim header.
                # [impl->req~sessions-wire-no-alternate-token-location~1]
                # [impl->req~sessions-backend-ignores-identity-headers~1]
                request.state.identity = await barrier.admit(
                    attempt, request.headers.getlist(IDENTITY_HEADER))
            except BarrierRejectionError as exc:
                # The shared response shape, naming the class and disclosing nothing else: not
                # the internal result, not the bounded reason, not the failed check. Status,
                # body and headers are identical across every acceptance-failure branch, so an
                # issuer mismatch is indistinguishable from an expired token.
                # [impl->req~shared-error-no-internal-results-exposed~1]
                # [impl->req~shared-invalid-external-jwt-reasons~1]
                # [impl->req~sessions-acceptance-failure-response-indistinguishable~1]
                return JSONResponse(status_code=exc.rejection.status, content=exc.body(),
                                    headers=exc.rejection.headers or None)
            except ServiceError as exc:
                # Imported here: the mapped models pull in this module's own package, so a
                # module-level import would close an import cycle.
                from nativespeaker.api.models.api import ErrorResponse
                return JSONResponse(status_code=exc.status_code,
                                    content=ErrorResponse(code=exc.error_code).model_dump(),
                                    headers=exc.extra_headers())
        return await call_next(request)


def verified_identity(request: Request) -> VerifiedIdentityContext:
    """The handler-side accessor for the barrier's typed output. A route wired outside the
    barrier has no identity context and fails loudly as `auth_required` rather than running
    open, and a new route attaches here instead of reimplementing token extraction."""
    # [impl->req~shared-prehandler-barrier~1]
    # [impl->req~sessions-shared-entry-point-three-way-partition~1]
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise BarrierRejectionError(AuthEventResult.invalid_external_jwt)
    return identity
