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
    client, and neither is the bounded rejection reason it carries for the audit row.

    The client and audit mappings are the ones already defined for these resolution outcomes,
    read out of the shared taxonomy: no per-endpoint error variant exists for the same
    condition."""

    # [impl->req~shared-error-classes-govern-all-routes~1]
    # [impl->req~shared-error-no-internal-results-exposed~1]
    # [impl->req~shared-invalid-external-jwt-reasons~1]
    # [impl->req~sessions-barrier-rejection-mappings-reused~1]
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
    """The four per-request identity-resolution outcomes, and exactly those four."""
    # [impl->req~sessions-exactly-four-resolution-outcomes~1]
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
    account-blocking rule can never drift between two copies.

    Route policy is fail-closed and admission is positive: the default policy requires a linked,
    active user, pre-auth admission is the explicit per-route declaration this predicate consults,
    and every other outcome — a route carrying no declaration included — takes the strictest
    treatment. The predicate admits no route-specific exception, `POST /auth/sign-out-all`
    included: a blocked user or a historical identity is rejected there exactly as everywhere
    else, and both surface as `account_unavailable`. Barrier rejections carry the client and audit
    mappings already defined for these outcomes; no per-endpoint variant is introduced.

    This predicate is the whole of the must-reject list an authenticated request is judged
    against once its token has been verified: a historical linked identity and a blocked user are
    rejected here, on every route, and no handler can admit either."""
    # [impl->req~shared-prehandler-barrier~1]
    # [impl->req~shared-invariant-03~1]
    # [impl->req~sessions-barrier-step-enforce-outcomes~1]
    # [impl->req~sessions-route-policy-fail-closed~1]
    # [impl->req~sessions-route-default-requires-linked-active~1]
    # [impl->req~sessions-preauth-admission-explicit-declaration~1]
    # [impl->req~sessions-undeclared-route-strictest~1]
    # [impl->req~sessions-barrier-no-route-exception~1]
    # [impl->req~sessions-barrier-rejection-mappings-reused~1]
    # [impl->req~sessions-backend-must-reject-list~1]
    # A historical identity and a blocked user are rejected on every endpoint, both phases of
    # `POST /auth/create-user` included, and always with the shared `account_unavailable` class.
    # [impl->req~sessions-historical-and-blocked-rejection-everywhere~1]
    if outcome is ResolutionOutcome.linked:
        # The one admitted outcome by default: a linked identity whose user is active.
        # [impl->req~sessions-resolution-outcome-04~1]
        return None
    if outcome is ResolutionOutcome.pre_auth:
        # A pre-auth identity is admitted only onto a route that declares itself pre-auth-callable;
        # every other route rejects it as `preauth_identity_not_allowed`.
        # [impl->req~sessions-resolution-outcome-01~1]
        # [impl->req~sessions-create-user-callable-from-preauth~1]
        return None if is_pre_auth_callable(method, path) \
            else AuthEventResult.preauth_identity_not_allowed
    if outcome is ResolutionOutcome.historical_identity:
        # Once an external identity has transitioned to `historical`, every subsequent request
        # for it is rejected here, at per-request resolution — on the pre-auth-declared
        # `POST /auth/create-user` phases too, so a retired identity never becomes eligible for a
        # pre-auth creation flow. It never receives `preauth_identity_not_allowed`, which would
        # send the client into create-user, and it never reaches a success path.
        # [impl->req~sessions-resolution-outcome-02~1]
        # [impl->req~sessions-reject-historical-identity~1]
        return AuthEventResult.historical_identity
    if outcome is ResolutionOutcome.blocked_user:
        # A blocked user is already linked and never legitimately reaches a pre-auth route; it is
        # rejected everywhere, under its own internal result.
        # [impl->req~sessions-resolution-outcome-03~1]
        # [impl->req~sessions-reject-blocked-user~1]
        return AuthEventResult.blocked_user
    # An outcome outside the four never authorizes: it takes the strictest rejection rather than
    # falling through to admission.
    # [impl->req~sessions-malformed-lifecycle-never-authorizes~1]
    return AuthEventResult.blocked_user


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
    # A request carrying no `Authorization` bearer credential conforming to that contract is
    # rejected here, before any resolution.
    # [impl->req~sessions-reject-no-bearer-credential~1]
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
        repeats or re-implements it, and nothing weaker than that verification satisfies it.

        The three steps run in this order on every authenticated request: verify the presented
        token under the external JWT acceptance policy, resolve the verified `(issuer, subject)`
        against `core.external_identities` and `core.users`, then enforce the four resolution
        outcomes. The barrier decides admission and leaves no result for a handler to check: it
        returns a context only for an admitted identity, so a historical identity and a blocked
        user are never represented as an authenticated principal."""
        # [impl->req~shared-prehandler-barrier~1]
        # [impl->req~sessions-jwt-acceptance-policy-scope~1]
        # [impl->req~sessions-backend-authoritative-verifier~1]
        # [impl->req~sessions-shared-barrier-mandatory~1]
        # [impl->req~sessions-barrier-ordered-steps~1]
        # [impl->req~sessions-barrier-positive-admission-test~1]
        # [impl->req~sessions-no-principal-for-historical-or-blocked~1]
        # Every authenticated endpoint is admitted only after this verification, this acceptance
        # policy over the verified claims, and these per-request identity-resolution rules have
        # all run, in this order.
        # [impl->req~sessions-endpoint-admission-after-verification~1]
        # [impl->req~sessions-backend-must-reject-list~1]
        # Backend network isolation is defence in depth, never a trust precondition: nothing here
        # reads the peer address, a gateway marker header or a mesh identity, so a request that
        # reached the pod off-gateway is judged by exactly the same token verification.
        # [impl->req~sessions-network-isolation-recommended~1]
        # [impl->req~sessions-off-gateway-access-accepted-risk~1]
        # Authenticated traffic, counted before any branch: the alert's fractional threshold is
        # a share of it, and every route that rejects here is inside that share.
        # [impl->req~sessions-invalid-external-jwt-metric-alert~1]
        self._audit.count_authenticated_request()
        try:
            # Step one: verify the presented external IDP ID token and apply the minimum external
            # JWT acceptance policy to its verified claims.
            # [impl->req~sessions-barrier-step-verify-token~1]
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
            # A verification failure — for any reason, a bad signature, an `iss` that is not the
            # configured integration's issuer, a wrong `aud`, expiry, or an empty `sub` — takes
            # the same `invalid_external_jwt` audit result and the same `auth_required` client
            # surfacing as every other acceptance failure.
            # [impl->req~sessions-reject-failed-verification~1]
            # [impl->req~sessions-verification-failure-mapping~1]
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
        # Step two: resolve the verified pair against `core.external_identities` and `core.users`.
        # All four outcomes come out of this one lookup: there is no outcome-dependent early
        # exit, no extra query for a particular state, no deliberate per-reason delay, and no
        # state-specific externally observable side effect. Constant-time resolution is not
        # required and is not attempted.
        # [impl->req~sessions-barrier-step-resolve-identity~1]
        # [impl->req~sessions-single-lookup-path-no-early-exit~1]
        resolved = await self._resolver.resolve(claims.issuer, claims.subject)
        actor = self._actor(claims.issuer, claims.subject, resolved)

        # Step three: enforce the four resolution outcomes. A rejection returns no context, so no
        # handler ever sees a historical identity or a blocked user as a principal.
        # [impl->req~shared-invariant-03~1]
        # [impl->req~sessions-barrier-step-enforce-outcomes~1]
        # [impl->req~sessions-no-principal-for-historical-or-blocked~1]
        result = barrier_result_for(resolved.outcome, attempt.method, attempt.route)
        if result is not None:
            raise await self._reject(attempt, result, actor=actor)

        # The admitted identity's resolved rows, including the stored `provider` and the user's
        # `registered_at`, become the typed context handler logic then runs with.
        # [impl->req~sessions-resolution-outcome-04~1]
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

    # It is a property of the request-processing layer rather than a per-endpoint obligation: the
    # middleware runs before any endpoint handler on every authenticated route, and it is the only
    # place the four resolution outcomes are evaluated. A provider-callback route is not an
    # authenticated route — it passes through here carrying no identity context, and its own named
    # verifier admits it instead.
    # [impl->req~sessions-shared-entry-point-three-way-partition~1]
    # [impl->req~sessions-authenticated-endpoint-families~1]
    # [impl->req~sessions-provider-callback-third-category~1]
    # [impl->req~sessions-gateway-forwards-pubsub-oidc-unchanged~1]
    # [impl->req~sessions-gateway-never-parses-apple-signedpayload~1]
    # [impl->req~sessions-shared-barrier-mandatory~1]
    # [impl->req~sessions-callback-route-not-authenticated-route~1]
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
    open, and a new route attaches here instead of reimplementing token extraction.

    This accessor is the whole of the handler-side contract: a handler performs no external JWT
    acceptance and no identity resolution of its own, never skips the barrier, and keeps only its
    own endpoint-specific authorization and business rules. Registering an authenticated route
    outside the barrier therefore cannot open it — the missing context rejects."""
    # [impl->req~shared-prehandler-barrier~1]
    # [impl->req~sessions-shared-entry-point-three-way-partition~1]
    # [impl->req~sessions-handlers-no-reimplementation~1]
    # [impl->req~sessions-no-authenticated-route-outside-barrier~1]
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise BarrierRejectionError(AuthEventResult.invalid_external_jwt)
    return identity


# --- The backend trust boundary ----------------------------------------------------------------

# Enforced backend network isolation — a Kubernetes NetworkPolicy restricting backend ingress to
# the gateway, or equivalent service-mesh mTLS restricting callers to the gateway's identity — is
# recommended defence-in-depth. It is not a required or load-bearing control for authenticated
# request trust, because the backend verifies every token itself; what it buys is a bound on the
# residual bypass of the gateway's rate limits, create-user spam included.
# [impl->req~sessions-network-isolation-recommended~1]
NETWORK_ISOLATION_IS_LOAD_BEARING = False

# This trust boundary introduces no new data artifacts: no table, column, stored marker or
# persisted flag records how a request reached the pod.
# [impl->req~sessions-network-isolation-no-data-artifacts~1]
NETWORK_ISOLATION_DATA_ARTIFACTS: frozenset[str] = frozenset()

# Fields a caller could send to claim it arrived through the gateway, or that a mesh would add.
# None of them is read by admission.
# [impl->req~sessions-off-gateway-access-accepted-risk~1]
GATEWAY_PRESENCE_MARKERS: frozenset[str] = frozenset({
    "x-envoy-external-address", "x-envoy-internal", "x-envoy-original-path",
    "x-envoy-peer-metadata", "x-forwarded-client-cert", "x-gateway-verified", "x-from-gateway"})

# The one residual capability an off-gateway caller gains: using its own valid token against the
# backend directly and thereby bypassing the gateway's rate limits. Holding such a token makes
# that caller the subject, exactly as it would through the gateway, so no identity is minted.
# [impl->req~sessions-off-gateway-access-accepted-risk~1]
OFF_GATEWAY_RESIDUAL_CAPABILITIES: frozenset[str] = frozenset({"bypasses_gateway_rate_limits"})


class OffGatewayTrustError(RuntimeError):
    """Backend admission was about to depend on the caller's network position."""


def admission_inputs(field_names: Sequence[str],
                     *,
                     consulted: Sequence[str] = (IDENTITY_HEADER,)) -> tuple[str, ...]:
    """The request fields backend admission reads, out of everything a caller sent: the one
    identity carrier and nothing else. A gateway-presence marker, a mesh peer identity or a
    proxy-added client certificate header contributes nothing, so a caller that reaches a pod
    off-gateway is judged by the same token verification as one that came through the gateway —
    and a caller that fakes a marker gains nothing. `consulted` is what an admission path
    declares it reads: anything beyond the identity carrier fails closed here."""
    # [impl->req~sessions-network-isolation-recommended~1]
    # [impl->req~sessions-off-gateway-access-accepted-risk~1]
    if NETWORK_ISOLATION_IS_LOAD_BEARING or NETWORK_ISOLATION_DATA_ARTIFACTS:
        raise OffGatewayTrustError("isolation is defence-in-depth and stores nothing")
    reads = {name.lower() for name in consulted}
    beyond = sorted(reads - {IDENTITY_HEADER})
    if beyond:
        raise OffGatewayTrustError(
            f"admission reads {IDENTITY_HEADER} alone, never {beyond}")
    return tuple(name.lower() for name in field_names if name.lower() in reads)


class RevocationWindowState(StrEnum):
    """The two states a subject is in after an operator block or an identity retirement revoked
    its Firebase refresh tokens."""
    # The client can mint no fresh ID token, so once its current one expires its requests fail
    # acceptance.
    no_mintable_token = "no_mintable_token"
    # An ID token already minted reaches resolution until its own `exp`.
    unexpired_id_token = "unexpired_id_token"


def revocation_window_class(state: RevocationWindowState) -> str:
    """The client-visible class each side of the revocation window surfaces as. That window needs
    no distinct class: both sides are classes the shared contract already defines, read from it
    here rather than restated — acceptance failure surfaces as `auth_required`, and a still-valid
    token that reaches resolution surfaces as `account_unavailable`."""
    # [impl->req~sessions-revocation-window-no-distinct-class~1]
    if state is RevocationWindowState.no_mintable_token:
        client_class, _status = surface(AuthEventResult.invalid_external_jwt)
    else:
        client_class, _status = surface(AuthEventResult.blocked_user)
    return client_class
