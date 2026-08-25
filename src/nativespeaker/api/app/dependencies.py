from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import NoReturn
from uuid import uuid7

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import (
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.auth.identity import Reject, resolve_identity
from nativespeaker.api.auth.telemetry import record_rejection
from nativespeaker.api.auth.wire import BoundedReason, extract_bearer
from nativespeaker.api.config import AppConfig
from nativespeaker.api.errors import (
    AUTH_REQUIRED,
    PREAUTH_IDENTITY_NOT_ALLOWED,
    AuthenticationError,
    AuthRejectionError,
    ErrorClass,
)
from nativespeaker.api.models.auth import AuthEventResult
from nativespeaker.api.quota import QuotaGate
from nativespeaker.api.services import ChatService


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# The §1.5 admission barrier, as a dependency (37.1 D-06, D-07)
#
# `get_request_context` is the ONE place JWT acceptance and identity resolution happen. It used to
# read what a middleware had already resolved; it now does the resolving itself. The property that
# matters is unchanged and the mechanism is what moved: every non-public router declares this in
# `APIRouter(dependencies=[...])`, so authentication is default-on per router and an endpoint that
# forgets its own declaration is still authenticated.
#
# **Both declaration levels must name the identical function object.** FastAPI keys its
# per-request dependency cache on the callable, so the router-level `Depends(get_linked_identity)`
# and the endpoint's own `Depends(get_linked_identity)` resolve to ONE execution -- and the two
# accessors share the one cached `get_request_context` beneath them. Wrapping the callable at
# either level, or turning that per-request cache off anywhere on this path, would run the JWT
# verify twice and issue the identity query twice per request. Neither appears here, and neither
# may be added. The `Depends` keyword that disables the cache is deliberately not spelled anywhere
# in this file: a repository-wide grep for it is the mechanical check, and a comment naming it
# would be the one hit that teaches a reader to ignore the result.
#
# Each accessor RAISES rather than returning None -- that is §1.4's "fails loudly". A None a
# handler could treat as anonymous is exactly the silently-open route the rule exists to prevent.
#
# None of the three creates, links, repairs, reassigns, or merges a row on any path.
# ---------------------------------------------------------------------------


async def get_request_context(request: Request) -> RequestContext:
    """Accept the token, resolve the identity, and build the §1.4 context -- once per request.

    The six §1.5 steps, in order: read the matched route, apply the §1.1 wire contract, verify the
    token, resolve `(issuer, subject)` from one short session, enforce the §1.3 admission matrix,
    and return the context. Every rejection is recorded through `record_rejection` -- the only
    record a rejection leaves -- and answered with the identical body its class declares.

    Resolution passes `allow_preauth=True` and lets `get_linked_identity` do the narrowing. That
    keeps ONE cached inner dependency for both accessors, and it is what lets
    `POST /auth/create-user` read the variant off the context: §02 prepare step 1 owes an
    already-linked caller `identity_already_linked` (409), which is unreachable if resolution 403s
    on a linked caller first.
    """
    # One evaluation time and one attempt id per request. Every time-dependent value derives from
    # this capture, so two reads within one request can never straddle a period boundary.
    evaluated_at = datetime.now(UTC)
    attempt_id = uuid7()

    # FastAPI writes the matched route into the ASGI scope inside `APIRoute.matches`, which runs
    # before any dependency is resolved -- so the path template is simply readable here. The
    # middleware ran too early to see it and had to re-run the router's own matching to find out;
    # that is the whole of what `barrier.py::_match_full` existed for, and it is why the function
    # was deleted rather than moved.
    route = request.scope["route"].path

    # Step 2 -- the wire contract. `headers.raw` is the raw list of byte pairs, deliberately never
    # `headers.get`: that folds duplicate fields and cannot see the desync §1.1 exists to reject.
    token, reason = extract_bearer(request.headers.raw)
    if token is None:
        _reject(AUTH_REQUIRED, AuthEventResult.invalid_external_jwt, reason, route)

    # Step 3 -- verification, off the loop, always. `verify` is synchronous, and on a `kid` the
    # cached JWKS set does not match it performs a blocking `urlopen` inside PyJWT. Called directly
    # from here that stalls every other coroutine in the process -- `/health/ready` included -- for
    # one outbound round trip, at the choice of an unauthenticated caller who has not yet proven
    # anything. Envoy bounds how many such requests arrive; it cannot un-block an event loop.
    claims, reason = await run_in_threadpool(request.app.state.jwt_verifier.verify, token)
    if claims is None:
        _reject(AUTH_REQUIRED, AuthEventResult.invalid_external_jwt, reason, route)

    # Step 4 -- resolution. Its own short session, opened here and closed before the handler runs.
    # Deliberately NOT `Depends(get_db)`: that is a yield dependency holding its transaction open
    # until after the handler returns, which would hold a read transaction across the LLM provider
    # round trip on POST /chats -- the lock-across-a-provider-call shape SHARED-INVARIANTS forbids.
    async with request.app.state.session_factory() as session:
        decision = await resolve_identity(session, issuer=claims.issuer,
                                          subject=claims.subject, allow_preauth=True)

    # Step 5 -- the admission matrix.
    if isinstance(decision, Reject):
        _reject(decision.error_class, decision.result, None, route)

    # Step 6 -- the §1.4 context.
    return RequestContext(identity=decision.identity,
                          route=route,
                          evaluated_at=evaluated_at,
                          attempt_id=attempt_id)


def _reject(error_class: ErrorClass, result: AuthEventResult,
            bounded_reason: BoundedReason | None, route: str) -> NoReturn:
    """Record the rejection, then raise it. `NoReturn` is load-bearing, not decoration.

    It is what lets each call site above stand as a bare statement: the type checker knows control
    does not come back, so `token` and `claims` are non-`None` on the lines that follow.

    Telemetry fires for every rejection, on every route, before the raise: `record_rejection`
    carries the specific internal result and the bounded reason into the structured security log,
    and it is the only record a rejection leaves.
    """
    record_rejection(result=result, bounded_reason=bounded_reason, route=route)
    raise AuthRejectionError(error_class, f"admission rejected on {route}: {result}")


# Both narrowing accessors DECLARE the context rather than calling `get_request_context(request)`.
# That is not a style choice and it is the whole of what makes the caching contract hold: FastAPI's
# per-request cache lives in the dependency solver, so it only sees a dependency the solver
# resolved. A direct call inside the function body is invisible to it, and a route declaring
# `Depends(get_linked_identity)` *and* `Depends(get_request_context)` -- which is exactly what
# `get_chat_service` produces on every /chats route -- would then verify the token twice and issue
# the identity query twice. Measured, not assumed: it did, until these two took the parameter.
#
# Taking the context instead of the Request also removes their last route to application state, so
# neither can reach a session, a verifier or a provider client at all.


async def get_linked_identity(
        context: RequestContext = Depends(get_request_context)) -> LinkedIdentity:
    """The resolved user and identity row. Rejects an unlinked caller with 403.

    `get_request_context` admits a pre-auth principal on every route, so this is where every route
    but `POST /auth/create-user` narrows it back down -- and `preauth_identity_not_allowed` (403)
    is exactly what `resolve_identity`'s non-pre-auth-callable arm used to produce for the same
    caller. The rejection is recorded here for the same reason it was recorded there: after 37.1
    D-01 the structured log is the only record.
    """
    identity = context.identity
    if not isinstance(identity, LinkedIdentity):
        _reject(PREAUTH_IDENTITY_NOT_ALLOWED, AuthEventResult.preauth_identity_not_allowed,
                None, context.route)
    return identity


async def get_preauth_identity(
        context: RequestContext = Depends(get_request_context)) -> PreAuthIdentity:
    """The verified (issuer, subject) of an unlinked caller. Raises when the caller is linked.

    Nothing declares this today. `POST /auth/create-user` is the only route an unlinked caller may
    reach, and it deliberately reads the variant off the context instead (see `routers/auth.py`):
    a linked caller there is a *client condition* answered with 409, not a wiring bug. The accessor
    is kept because phases 40/41/42 register challenge-bearing routes that do want the narrowing.
    """
    identity = context.identity
    if not isinstance(identity, PreAuthIdentity):
        raise AuthenticationError("Identity context is linked on a route expecting a pre-auth identity")
    return identity


# Defined below the accessors, not above them, because its `Depends(get_request_context)` default
# is evaluated at definition time and the name has to exist by then.
def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config),
                     context: RequestContext = Depends(get_request_context)) -> ChatService:
    # The context is *declared* rather than fetched: `get_quota_gate` needs it, and resolving it
    # through `Depends` is what puts it on FastAPI's per-request cache alongside the router-level
    # declaration. Calling `get_request_context(request)` here instead would bypass that cache and
    # run a second JWT verify and a second identity query on every request (T-37.1-11).
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit,
                       quota_gate=get_quota_gate(request, context))


# ---------------------------------------------------------------------------
# The §6.5 / §7.1 challenge-bearing-endpoint accessors (Phase 37, reused by phases 40/41/42)
#
# Every one exists so a challenge-bearing route can stay Depends()-only. `POST /auth/create-user`
# needs five things the §1.4 context deliberately does not carry, and the alternative to an
# accessor apiece is a handler taking `Request` -- which is the v1.3 convention's one prohibition
# and would hand that handler the raw headers the barrier exists to be the only reader of.
# ---------------------------------------------------------------------------


def get_raw_query_string(request: Request) -> bytes:
    """The ASGI `scope["query_string"]` bytes, unparsed.

    `auth/modesignal.py`'s `classify_mode_signal` parses these itself with `parse_qsl`, because a
    duplicated `challenge` parameter is its own `invalid_request` case and **any** first-value-wins
    accessor -- `request.query_params.get(...)` included -- folds duplicates and cannot see it.
    Handing the raw bytes over is what keeps that decision in the one module that owns it.

    `RequestContext` deliberately carries no query string, so this is a seam rather than a field:
    the mode signal is a per-route syntactic concern, not part of the identity context.
    """
    return request.scope["query_string"]


def get_challenge_store(request: Request) -> ChallengeStore:
    """The one `ChallengeStore` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.challenge_store


def get_firebase_adapter(request: Request):
    """The §7.1 provider seam the lifespan built.

    Deliberately unannotated, following `auth/retry.py`'s precedent for the same object: the
    concrete class satisfies the Protocol's one reachable method asynchronously while the Protocol
    declares it synchronously, so an annotation here would be a claim the class does not make.
    Nothing on this path may reach a provider client any other way.
    """
    return request.app.state.firebase_adapter


# ---------------------------------------------------------------------------
# The §8.4 quota seam (D-04, REBIND-06)
#
# Which routes consume the allowance used to be declared twice -- a `quota_checked=True` flag on a
# registry entry, cross-checked at boot against a named set of charging handlers. 37.1 D-06 deleted
# the registry and both halves with it. What consumes the allowance is now simply what calls
# `QuotaGate.charge`: `ChatService`, at the resilience layer's admission callback, and nothing else.
#
# **The charge is no longer a decorator dependency, and that is REBIND-06's fix.** It used to be:
# `require_quota_*` wrappers in `dependencies=[...]`, committing in their own session before the
# handler body was entered. That ordering is what made five distinct rejections -- an unsupported
# language, either history limit, an unknown chat id, and the resilience layer's local backpressure
# -- each charge a caller for a request the service refused without ever calling the provider. A
# decorator dependency cannot see any of them, because none of them has happened when it runs.
#
# Consumption now travels as `QuotaGate`, which `ChatService` calls at the resilience layer's
# admission callback -- after every one of its own rejections, and after the circuit breaker and
# execution gate have admitted the call. D-04 is untouched: `QuotaGate.charge` still opens, commits
# and closes a session of its own, so no lock spans the provider round trip. Only the moment moved.
#
# **What the D-14 wrappers bought is now structural.** They existed so FastAPI would validate a
# route's body and path parameters before the own-session commit ran. With the commit moved inside
# the handler's call stack, request validation necessarily precedes it -- a 422 means the handler
# was never entered. The wrappers are deleted rather than kept as no-ops; `tests/e2e/test_quota.py`
# keeps their cases, which now pass for a structural reason instead of a declared one.
# ---------------------------------------------------------------------------


def get_quota_gate(request: Request, context: RequestContext) -> QuotaGate:
    """Build this request's charge seam from the context the auth dependency captured.

    Takes the app's real `session_factory` rather than `Depends(get_db)`: that is a
    yield-dependency committing after the handler returns, which is precisely the lock-across-the-
    provider-call shape D-04 forbids. `QuotaGate` opens its own short session instead.

    A plain function rather than a dependency: it is called by `get_chat_service`, which declares
    the context and hands it over, so a service that consumes the allowance cannot be constructed
    without one -- and the context it charges against is provably the one cached for this request.
    """
    identity = context.identity
    if not isinstance(identity, LinkedIdentity):
        # The quota-checked routes carry `Depends(get_linked_identity)` at router level, which
        # rejects a pre-auth caller before this runs, so this is unreachable. Asserted anyway, and
        # failing closed: a pre-auth caller reaching a charging service is a wiring bug, and the
        # alternative to raising is billing a principal with no user row.
        raise AuthenticationError("Identity context is pre-auth on a quota-checked route")
    return QuotaGate(request.app.state.session_factory,
                     # Both from the instant the barrier captured for this request (D-06). Nothing
                     # on this path reads the system clock.
                     evaluated_at=context.evaluated_at,
                     route=context.route)


# ---------------------------------------------------------------------------
# Deleted here (D-16), together with the chat-route rewiring that was their last caller:
#
#   get_current_user       -- read the credential through FastAPI's `Header(None)` alias, which
#                             returns a single folded value and cannot see a duplicate
#                             `Authorization` field. That is the exact desync §1.1 exists to
#                             reject, so this was a second acceptance path beside the barrier's.
#                             It also provisioned `core.users` rows just in time; in v2.0 only
#                             `POST /auth/create-user` (Phase 37) creates an account.
#   get_subscription_service -- read `app.state.apple_verifier`, which the lifespan no longer sets.
# ---------------------------------------------------------------------------
