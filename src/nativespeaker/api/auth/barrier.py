"""The shared, mandatory, default-on pre-handler barrier.

It is the only place external JWT acceptance and the four identity-resolution outcomes are
evaluated. Handlers consume its typed output and never verify tokens or resolve identity
themselves.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from nativespeaker.api.auth.audit import (
    NO_ACTOR,
    AttemptPhase,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEventResult,
    terminal_event,
)
from nativespeaker.api.auth.integration import FirebaseIntegrations
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.routes import (
    RouteCategory,
    categorize,
    is_pre_auth_callable,
    resolve_route_template,
)
from nativespeaker.api.auth.tokens import InvalidExternalJwtError, JwtRejectionReason
from nativespeaker.api.exceptions import ServiceError
from nativespeaker.api.models.api import ErrorResponse

BEARER_PREFIX = "Bearer "

_RESULT_TO_CLIENT_CLASS: dict[AuthEventResult, tuple[str, int]] = {
    AuthEventResult.invalid_external_jwt: ("auth_required", 401),
    AuthEventResult.preauth_identity_not_allowed: ("preauth_identity_not_allowed", 403),
    AuthEventResult.historical_identity: ("account_unavailable", 403),
    AuthEventResult.blocked_user: ("account_unavailable", 403),
}


class BarrierRejectionError(ServiceError):
    """A barrier rejection, surfaced through the shared client-error taxonomy. The internal
    `core.auth_event_result` is never exposed to the client."""

    def __init__(self, result: AuthEventResult, reason: str | None = None):
        self.result = result
        self.reason = reason
        error_code, status_code = _RESULT_TO_CLIENT_CLASS[result]
        self.error_code = error_code  # type: ignore[invalid-assignment]
        self.status_code = status_code
        super().__init__("Authentication failed")


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


def extract_bearer_token(authorization_values: Sequence[str]) -> str:
    """The `Authorization` header is the sole identity carrier: exactly one field, `Bearer`
    scheme, non-empty token."""
    # [impl->req~shared-bearer-single-identity-carrier~1]
    # [impl->req~shared-wire-contract-owner~1]
    if len(authorization_values) > 1:
        raise InvalidExternalJwtError(JwtRejectionReason.duplicate_authorization)
    if not authorization_values:
        raise InvalidExternalJwtError(JwtRejectionReason.missing_token)
    value = authorization_values[0]
    if not value.startswith(BEARER_PREFIX):
        raise InvalidExternalJwtError(JwtRejectionReason.malformed)
    token = value[len(BEARER_PREFIX):].strip()
    if not token:
        raise InvalidExternalJwtError(JwtRejectionReason.missing_token)
    return token


class AuthBarrier:
    """Token verification plus identity resolution, in one place, for every authenticated
    route."""

    def __init__(self,
                 *,
                 integrations: FirebaseIntegrations,
                 resolver: IdentityResolver,
                 audit: AuthAuditWriter,
                 subject_hasher: Callable[[str], tuple[bytes, int]] | None = None):
        self._integrations = integrations
        self._resolver = resolver
        self._audit = audit
        self._subject_hasher = subject_hasher

    async def admit(self,
                    attempt: AuthAttempt,
                    authorization_values: Sequence[str]) -> VerifiedIdentityContext:
        """Verify, resolve, enforce the route's identity policy, and return the typed context.
        Every rejection is audited on the path and counted everywhere."""
        # [impl->req~shared-prehandler-barrier~1]
        try:
            token = extract_bearer_token(authorization_values)
            claims = self._integrations.verify_id_token(token)
        except InvalidExternalJwtError as exc:
            # Verification supplied no permitted actor, so the row takes the actor-`NULL` shape.
            raise await self._reject(attempt, AuthEventResult.invalid_external_jwt,
                                     reason=str(exc.reason)) from None

        # Identity comes only from the verified claims. No header, cookie, query parameter or
        # body field contributes any part of it.
        # [impl->req~shared-identity-from-verified-claims-only~1]
        resolved = await self._resolver.resolve(claims.issuer, claims.subject)
        actor = self._actor(claims.issuer, claims.subject, resolved)

        match resolved.outcome:
            case ResolutionOutcome.historical_identity:
                raise await self._reject(attempt, AuthEventResult.historical_identity, actor=actor)
            case ResolutionOutcome.blocked_user:
                raise await self._reject(attempt, AuthEventResult.blocked_user, actor=actor)
            case ResolutionOutcome.pre_auth:
                if not is_pre_auth_callable(attempt.method, attempt.route):
                    raise await self._reject(attempt,
                                             AuthEventResult.preauth_identity_not_allowed,
                                             actor=actor)

        return VerifiedIdentityContext(issuer=claims.issuer,
                                       subject=claims.subject,
                                       outcome=resolved.outcome,
                                       user_id=resolved.user_id,
                                       external_identity_id=resolved.external_identity_id,
                                       provider=resolved.provider,
                                       registered_at=resolved.registered_at)

    def _actor(self, issuer: str, subject: str, resolved: ResolvedIdentity) -> AuthActor:
        subject_hash: bytes | None = None
        key_version: int | None = None
        if self._subject_hasher is not None:
            subject_hash, key_version = self._subject_hasher(subject)
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
        the named result code in the security log and counter metric off it."""
        # [impl->req~shared-barrier-result-first-class~1]
        # [impl->req~shared-challenge-scope-narrower-subset~1]
        error = BarrierRejectionError(result, reason)
        if not attempt.on_audited_path:
            self._audit.record_off_path(attempt, result, reason=reason)
            return error
        details = {"reason": reason, "route": attempt.route} if reason else {"route": attempt.route}
        event = terminal_event(AttemptPhase.barrier, result,
                               operation=attempt.operation, actor=actor, details=details)
        return await self._audit.record_rejection(attempt, event, error)


class AuthBarrierMiddleware(BaseHTTPMiddleware):
    """Runs the barrier ahead of every handler. Public and provider-callback routes pass
    through; every other route, declared or not, is authenticated."""

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        method = request.method
        path = request.url.path
        attempt = AuthAttempt(method, path,
                              route_template=resolve_route_template(method, path) or "other")
        request.state.auth_attempt = attempt
        if categorize(method, path) is RouteCategory.authenticated:
            barrier: AuthBarrier = request.app.state.auth_barrier
            try:
                request.state.identity = await barrier.admit(
                    attempt, request.headers.getlist("authorization"))
            except ServiceError as exc:
                return JSONResponse(status_code=exc.status_code,
                                    content=ErrorResponse(code=exc.error_code).model_dump(),
                                    headers=exc.extra_headers())
        return await call_next(request)


def verified_identity(request: Request) -> VerifiedIdentityContext:
    """The handler-side accessor for the barrier's typed output. A route wired outside the
    barrier has no identity context and fails loudly rather than running open."""
    # [impl->req~shared-prehandler-barrier~1]
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise BarrierRejectionError(AuthEventResult.invalid_external_jwt)
    return identity
