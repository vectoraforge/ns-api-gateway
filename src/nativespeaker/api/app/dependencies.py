from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.audit import AuditWriter
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import (
    REQUEST_CONTEXT_SCOPE_KEY,
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.config import AppConfig
from nativespeaker.api.errors import AuthenticationError
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


def get_chat_service(request: Request,
                     db: AsyncSession = Depends(get_db),
                     config: AppConfig = Depends(get_config)) -> ChatService:
    return ChatService(db=db,
                       llm_service=request.app.state.llm_service,
                       examples=config.examples,
                       chats_limit=config.chats_limit,
                       messages_limit=config.messages_limit,
                       quota_gate=get_quota_gate(request))


# ---------------------------------------------------------------------------
# The §1.4 identity accessors (D-02)
#
# Routes stay Depends()-only: a handler reads the one object the barrier attached and never
# re-verifies a token or re-resolves identity.
#
# Each accessor RAISES rather than returning None -- that is §1.4's "fails loudly". A route
# registered outside the barrier has no identity context, and `auth_required` is the only safe
# reading of that: a None a handler could treat as anonymous is exactly the silently-open route
# the rule exists to prevent. Putting the check here, once, stops each of the seven later phases
# re-implementing it.
#
# None of the three creates, links, repairs, reassigns, or merges a row on any path. They are
# synchronous and take nothing but the Request -- there is no session to write through.
# ---------------------------------------------------------------------------


def get_request_context(request: Request) -> RequestContext:
    """The §1.4 context the barrier attached. Raises when the barrier did not run."""
    context = getattr(request.state, REQUEST_CONTEXT_SCOPE_KEY, None)
    if not isinstance(context, RequestContext):
        # isinstance, not `is None`: a wrong-typed value under the key is as unusable as an absent
        # one and must fail closed too, rather than reach a handler as a duck-typed stand-in.
        raise AuthenticationError("No identity context on this request: it ran outside the barrier")
    return context


def get_linked_identity(request: Request) -> LinkedIdentity:
    """The resolved user and identity row. Raises when absent, and when the variant is pre-auth."""
    identity = get_request_context(request).identity
    if not isinstance(identity, LinkedIdentity):
        # Reaching here means a route's registry declaration and its handler disagree: the barrier
        # admits a pre-auth principal only where `preauth_callable` is declared, so a pre-auth
        # variant arriving at a linked-only handler is a wiring bug, not a caller condition. The
        # caller-facing `preauth_identity_not_allowed` rejection is the barrier's to emit
        # (§1.5 step 5); this seam's only job is refusing to hand over the wrong variant.
        raise AuthenticationError("Identity context is pre-auth on a route requiring a linked identity")
    return identity


def get_preauth_identity(request: Request) -> PreAuthIdentity:
    """The verified (issuer, subject) of an unlinked caller. Raises when absent, and when linked."""
    identity = get_request_context(request).identity
    if not isinstance(identity, PreAuthIdentity):
        raise AuthenticationError("Identity context is linked on a route expecting a pre-auth identity")
    return identity


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


def get_audit_writer(request: Request) -> AuditWriter:
    """The one `AuditWriter` the lifespan built. Read per request, never cached by a caller."""
    return request.app.state.audit_writer


def get_session_factory(request: Request):
    """The app's real session factory, for `AuditWriter.write_standalone` alone.

    Not `Depends(get_db)`: a standalone-durable audit row exists precisely because there is no
    consuming transaction to be atomic with, so it must open and commit a session of its own. The
    factory is read off the app per request rather than captured, so the e2e rollback fixture's
    per-test swap still governs every row written through it.
    """
    return request.app.state.session_factory


def get_firebase_adapter(request: Request):
    """The §7.1 provider seam the lifespan built.

    Deliberately unannotated, following `auth/retry.py`'s precedent for the same object: the
    concrete class satisfies the Protocol's one reachable method asynchronously while the Protocol
    declares it synchronously, so an annotation here would be a claim the class does not make.
    Nothing on this path may reach a provider client any other way.
    """
    return request.app.state.firebase_adapter


# ---------------------------------------------------------------------------
# The §8.4 quota seam (D-04, D-05, REBIND-06)
#
# A quota-checked route declares `quota_checked=True` on its registry entry, and its handler is
# named in `auth/registry.py`'s quota-consuming handler set. Neither alone is enforcement: the
# §2.3 condition-10 cross-check fails boot when the two disagree in either direction, which is what
# stops a route from declaring the flag while serving requests free (D-05).
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


def get_quota_gate(request: Request) -> QuotaGate:
    """Build this request's charge seam from the context the barrier captured.

    Takes the app's real `session_factory` rather than `Depends(get_db)`: that is a
    yield-dependency committing after the handler returns, which is precisely the lock-across-the-
    provider-call shape D-04 forbids. `QuotaGate` opens its own short session instead.

    Not itself declared in any route's `dependencies=[...]`. It is resolved by `get_chat_service`,
    so a service that consumes the allowance cannot be constructed without one.
    """
    context = get_request_context(request)
    identity = context.identity
    if not isinstance(identity, LinkedIdentity):
        # The quota-checked routes are `Category.authenticated`, so the barrier admits no pre-auth
        # principal to them and this is unreachable through the registry. Asserted anyway, and
        # failing closed: a pre-auth caller reaching a charging service is a wiring bug, and the
        # alternative to raising is billing a principal with no user row.
        raise AuthenticationError("Identity context is pre-auth on a quota-checked route")
    return QuotaGate(request.app.state.session_factory,
                     # Both from the instant the barrier captured for this request (D-06). Nothing
                     # on this path reads the system clock.
                     evaluated_at=context.evaluated_at,
                     route=context.route_metadata.path)


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
