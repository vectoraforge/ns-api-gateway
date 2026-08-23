"""`POST /auth/create-user` (spec 02-create-user.md) -- the only pre-auth-callable route.

One registered path function, dispatching to two mode bodies. 37-CONTEXT.md left the one-route/
two-route question to implementation; one route is what the registry can express (`operation` maps
to exactly one `(method, path)`, condition 8), and two bodies behind it is what keeps each mode
readable on its own -- prepare mutates no business state and completion mutates all of it, and a
single body serving both would be an `if` around two unrelated procedures.

**The ordering below is §02's literal completion order, and the order IS the rejection precedence.**
Three properties of it are architectural rather than stylistic, and none may be "simplified":

1. **The claim commits in its own transaction, before the provider call.** A crash mid-lookup then
   leaves a permanently-claimed dead row, which is §6.2's stated design ("a claimed challenge is
   dead") and costs the client one fresh prepare. Holding the claim uncommitted across the lookup
   would instead let a second attempt win the same challenge, which is the property the claim
   exists to make impossible. It looks like a stray commit otherwise -- it is not.
2. **No transaction is open across the provider call** (§02 step 8, SHARED-INVARIANTS § Locks).
   Provider latency under an open transaction is a database-wide stall.
3. **The consuming transaction lives in `auth/creation.py`**, not inline here, so 37-09 can drive
   it directly from two real sessions.

**Nothing in this module re-derives what a seam already owns.** No token verification (the barrier
did it, and §02's hardenings forbid a handler repeating it), no keyed-hash comparison (only
`HmacKeyring.actor_subject_matches`, reached through `ChallengeStore.verify_binding`), no expiry
evaluation (only `ChallengeStore.claim`'s WHERE), no affected-row count read off a driver attribute
(the store's conditional updates use `returning`), and no second clock or attempt id (both are on
`RequestContext`, 35 D-02).

**The public `challenge_id` never leaves the body.** It is a secret capability handle: not in a URL,
not in a log line, not in an audit row, not in error text. Correlation is on the non-secret
`core.auth_challenges.id`, carried as the audit row's `challenge_row_id`.
"""
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse, Response

from nativespeaker.api.app.dependencies import (
    get_audit_writer,
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_raw_query_string,
    get_request_context,
    get_session_factory,
)
from nativespeaker.api.auth.adapters import ProviderDataOutcome
from nativespeaker.api.auth.audit import AuditWriter, build_details
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.classifier import classify_provider_data, email_to_persist
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import create_account, resolve_existing_identity
from nativespeaker.api.auth.modesignal import ModeSignal, classify_mode_signal
from nativespeaker.api.auth.retry import lookup_with_retry
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    CHALLENGE_REQUIRED,
    IDENTITY_ALREADY_LINKED,
    INVALID_REQUEST,
    OPERATION_NOT_ALLOWED,
    VERIFICATION_TEMPORARILY_UNAVAILABLE,
    error_response,
)
from nativespeaker.api.models.auth import AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState

logger = structlog.get_logger()

router = APIRouter(tags=["auth"])


class CreateUserRequest(BaseModel):
    """The completion body, typed permissively on purpose.

    `challenge_id` is `Any` and defaults to `None` so that **every** unusable handle -- an integer,
    a list, an object, an empty string -- reaches `classify_mode_signal` and rejects as
    `invalid_request` (400). A `str | None` annotation would hand the wrong-type case to Pydantic
    instead, and the client would receive `validation_error` (422): a status and a code §02 never
    names for this route (37-RESEARCH Pitfall 6).

    The whole body is optional at the parameter below, so a bodyless `?challenge=true` prepare
    request is a prepare request rather than a 422.
    """
    challenge_id: Any = None


class PrepareResponse(BaseModel):
    """§6.1 / §02 prepare step 5: exactly two fields. Do not add a third.

    Nothing else about the challenge is ever disclosed -- not the row id, not the binding, not the
    operation, not the lifecycle state. Building the body through this model rather than a dict
    literal is what makes the key set a declaration instead of a convention.
    """
    challenge_id: str
    expires_at: datetime


class CompletionResponse(BaseModel):
    """§02 step 14 / 37 D-10: the resulting registration state, which is one field.

    No backend token, no session, no cookie, no generation counter -- there is no backend session
    tier to mint one into, and the same Firebase ID token simply resolves as linked on the next
    request. The attribution tokens are minted but deliberately not returned (D-11); Phase 39's
    rewritten `GET /users/me` is the one place that surfaces them.
    """
    identity_provider: IdentityProvider


@router.post("/auth/create-user",
             summary="Create the account for a verified but unlinked identity",
             description="Prepare mode (`?challenge=true`) issues a single-use challenge; "
                         "completion mode (`challenge_id` in the body) creates the account.")
async def create_user(body: CreateUserRequest | None = None,
                      raw_query: bytes = Depends(get_raw_query_string),
                      context: RequestContext = Depends(get_request_context),
                      session: AsyncSession = Depends(get_db),
                      session_factory=Depends(get_session_factory),
                      challenge_store: ChallengeStore = Depends(get_challenge_store),
                      audit_writer: AuditWriter = Depends(get_audit_writer),
                      adapter=Depends(get_firebase_adapter)) -> Response:
    """Classify the mode signal, then dispatch. The classification itself has no side effects.

    §6.5's partition is evaluated before anything is issued, looked up or consumed, so a corrected
    retry may reuse the same unexpired challenge. A `None` classification is `invalid_request`
    (400): it belongs to the admission phase, has no internal `core.auth_event_result`, and writes
    **no** `audit.auth_events` row -- it is recorded in the structured security log alone.

    **This route reads the identity variant off the context rather than demanding a pre-auth one,
    and it is the only route in the system that does.** `Depends(get_preauth_identity)` raises on a
    linked caller -- correctly, for every other handler, where a linked context arriving at a
    pre-auth-only handler is a wiring bug. Here it is a *client condition* §02 prepare step 1 names
    explicitly: a caller who already has an account gets `identity_already_linked` (409), not
    `auth_required` (401), and the two say incompatible things to a client. So the accessor's
    fail-loudly guarantee is preserved where it belongs -- `get_request_context` still raises when
    the barrier did not run -- while the variant itself becomes something this one route decides on.
    """
    body_challenge_id = None if body is None else body.challenge_id
    mode = classify_mode_signal(raw_query, body_challenge_id)
    if mode is None:
        logger.warning("auth_mode_signal_invalid",
                       route=context.route_metadata.path,
                       operation=str(AuthOperation.create_user),
                       # The raw value is never logged: an unusable handle is still a handle
                       # somebody typed, and the shape is the whole diagnostic.
                       body_present=body is not None)
        return error_response(INVALID_REQUEST)

    identity = context.identity
    if mode is ModeSignal.prepare:
        return await _prepare(session, session_factory, context=context, identity=identity,
                              challenge_store=challenge_store, audit_writer=audit_writer)

    # `classify_mode_signal` returns `completion` only for a non-empty `str`, so the annotation
    # below is the partition's guarantee rather than this handler's assumption -- and the value is
    # forwarded **untouched**. `locate` compares byte-for-byte, so a whitespace-padded handle is
    # `challenge_not_found`, not `invalid_request`: a deliberate asymmetry, not an oversight to
    # tidy up with a `.strip()` here.
    completion_handle: str = body_challenge_id  # ty: ignore[invalid-assignment]
    return await _complete(session, context=context, identity=identity,
                           challenge_id=completion_handle,
                           challenge_store=challenge_store, audit_writer=audit_writer,
                           adapter=adapter)


async def _prepare(session: AsyncSession, session_factory, *,
                   context: RequestContext,
                   identity: LinkedIdentity | PreAuthIdentity,
                   challenge_store: ChallengeStore,
                   audit_writer: AuditWriter) -> Response:
    """§02 prepare steps 1, 4 and 5: fail fast, then issue one challenge and disclose two fields.

    Prepare mutates **no** business state -- no user, no identity, no grant, no attribution token.
    The only row it writes is the challenge itself, inside the request's one transaction, which
    `get_db` commits when this handler returns.

    `expires_at` comes from the store, derived from the request's single captured evaluation time.
    Nothing here recomputes it, extends it, or renews it on retry.
    """
    linked = await _already_linked(session, identity=identity)
    if linked is not None:
        # Release the read transaction the racy check may have opened, so the standalone write
        # below is the only thing holding a session. It has nothing to be atomic with anyway --
        # that is what "standalone" means -- and prepare has written nothing to preserve.
        await session.rollback()
        await audit_writer.write_standalone(
            session_factory,
            operation=AuthOperation.create_user,
            result=AuthEventResult.identity_already_linked,
            actor_issuer=identity.issuer,
            actor_subject=identity.subject,
            # Permitted here precisely because it is the STORED column of a resolved identity row
            # (§4.2) -- never fabricated, never a token claim, never client input.
            actor_provider=linked.provider,
            # No challenge exists to correlate on: none was issued, and none was located.
            challenge_row_id=None,
            details=_prepare_details(context, linked=True),
            created_at=context.evaluated_at)
        return error_response(IDENTITY_ALREADY_LINKED)

    challenge_id, expires_at = await challenge_store.issue(session,
                                                           operation=AuthOperation.create_user,
                                                           identity=identity,
                                                           now=context.evaluated_at)
    body = PrepareResponse(challenge_id=challenge_id, expires_at=expires_at)
    # `no-store` rather than `no-cache`: the handle is a secret capability, and an intermediary
    # holding a revalidatable copy is a copy.
    return JSONResponse(content=body.model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})


async def _already_linked(session: AsyncSession, *,
                          identity: LinkedIdentity | PreAuthIdentity) -> ExternalIdentity | None:
    """§02 prepare step 1's fail-fast. The row when this caller already has an account, else `None`.

    **Best-effort, racy, and never authoritative -- do not "strengthen" it.** The authoritative
    answer is the re-resolution inside the consuming transaction, and the arbiters between two
    completions that both observed an unlinked subject are `UNIQUE (issuer, subject)` and
    `UNIQUE (user_id)` alone (§02 step 12). Turning this into a lock, a `FOR UPDATE`, or a
    pre-SELECT-then-INSERT would *add* a window the constraints do not have, while looking like it
    closed one. It is here to save a challenge, a provider read and a transaction in the common
    case, and for nothing else.

    Two arms, because the question has already been answered once for most callers:

    * **A linked context needs no query at all.** The barrier resolved this exact pair through
      `auth/identity.py`'s single statement one layer ago and put the answer in the context. Asking
      again would be a second identity resolution -- which §1.4 forbids a handler outright -- and
      it would be *racier*, not less, because it would be strictly later.
    * **A pre-auth context gets one direct read**, through the same query the consuming transaction
      uses, to catch a row that appeared in the window between the barrier's resolution and now.

    Historical and blocked callers are **not** re-checked here: the barrier already rejected both
    with `account_unavailable`, so a context reaching this handler at all resolved to no active
    identity row. The `is` test below is why a historical row that somehow arrived falls through to
    issue a challenge rather than being reported as already-linked -- it is not linked, and the
    consuming transaction is where that gets the answer it deserves.
    """
    if isinstance(identity, LinkedIdentity):
        return identity.identity
    existing = await resolve_existing_identity(session,
                                               issuer=identity.issuer, subject=identity.subject)
    if existing is not None and existing.identity_state is IdentityState.active:
        return existing
    return None


def _prepare_details(context: RequestContext, *, linked: bool) -> dict:
    """§4.4's six-key object for a prepare-mode outcome.

    `context` carries the route, the method, the operation, this attempt's id, the mode signal as
    booleans, and the client-IP **bucket kind**. Never the address -- §4.4 admits the kind alone,
    so `audit.auth_events` cannot become a behavioural-tracking archive -- and never the public
    challenge handle, which prepare mode does not even have at the point this is built.
    """
    return build_details(
        context={"route": context.route_metadata.path,
                 "method": context.route_metadata.method,
                 "operation": AuthOperation.create_user,
                 "attempt_id": context.attempt_id,
                 "prepare_mode": True,
                 "completion_mode": False,
                 "client_ip_bucket_kind": context.client_ip_bucket_kind},
        verification={},
        resolved={"identity_already_linked": linked},
        # Prepare mutates no business state on either arm, so there is nothing to report -- and
        # `{}` is §4.4's own way of saying exactly that.
        mutation={},
        failure={"stage": "prepare_precheck"} if linked else {})


async def _complete(session: AsyncSession, *,
                    context: RequestContext,
                    identity: LinkedIdentity | PreAuthIdentity,
                    challenge_id: str,
                    challenge_store: ChallengeStore,
                    audit_writer: AuditWriter,
                    adapter) -> Response:
    """§02 completion steps 3-14, in the specification's own order.

    The numbering is normative rejection precedence: reject for the earliest failed step. Every
    rejection below therefore has to stay where it is relative to its neighbours, even when a later
    check would be cheaper to run first.
    """
    # --- Steps 3-5, in one transaction that COMMITS before the provider call. ---
    challenge = await challenge_store.locate(session, challenge_id)
    if challenge is None:
        return _challenge_rejected("challenge_not_found")

    if challenge_store.verify_binding(challenge, identity) is not None:
        # Rejected BEFORE the claim, leaving the row unconsumed, so a wrong presenter can never
        # burn the rightful user's in-flight challenge (§6.4, T-37-25).
        return _challenge_rejected("challenge_binding_rejected")
    if challenge.operation is not AuthOperation.create_user:
        return _challenge_rejected("challenge_operation_mismatch")

    if not await challenge_store.claim(session,
                                       challenge_id=challenge_id,
                                       claim_attempt_id=context.attempt_id,
                                       now=context.evaluated_at):
        # The claim is the single serialization point and the only expiry evaluation anywhere. A
        # loser matched zero rows, mutated nothing, and performs no work at all from here.
        return _challenge_rejected("challenge_claim_lost")

    # **This commit is load-bearing; see module docstring point 1.** The claim must be durable
    # before the provider call, or a crash during the lookup leaves the challenge unclaimed and a
    # second attempt could win it -- contradicting §6.2's "a claimed challenge is dead".
    await session.commit()

    # --- Step 8: the provider read, with NO transaction open. ---
    provider_data = await lookup_with_retry(adapter, identity.issuer, identity.subject)

    # --- Steps 9-10: classify the account and resolve the address, both from THIS one response. ---
    classified = classify_provider_data(provider_data.entries)
    if classified is None:
        return _lookup_rejected(provider_data.outcome)
    provider, provider_uid = classified
    # The single evaluation site for §02 step 10's copy rule. `auth/creation.py` receives the
    # result as a plain `email` argument and re-derives nothing, so the rule cannot be answered
    # twice and cannot be answered differently (T-37-34).
    email = email_to_persist(provider_data)

    # --- Steps 10-13: the consuming transaction, opened only now. ---
    result = await create_account(session,
                                  context=context,
                                  identity=identity,
                                  challenge=challenge,
                                  provider=provider,
                                  provider_uid=provider_uid,
                                  email=email,
                                  challenge_store=challenge_store,
                                  audit_writer=audit_writer)

    # --- Step 14: return the resulting backend state, and nothing more. ---
    return _completion_response(result, provider)


def _challenge_rejected(stage: str) -> Response:
    """The five §6 challenge rejections collapse into one client class (§02's error table).

    `challenge_required` for all of them, so completion is not a challenge-enumeration oracle: a
    client cannot learn whether a handle was unknown, expired, already used, bound to somebody
    else, or bound to another operation.

    **37-08 Task 1 owns the rest of this branch** -- the per-rejection internal
    `core.auth_event_result`, its audit row, and its consumption disposition (an identity or
    operation mismatch neither claims nor consumes; a claim loser has nothing to consume). What is
    already correct here and must not regress: the class returned, and the fact that every check
    above the claim runs before it.
    """
    logger.warning("create_user_challenge_rejected", stage=stage)
    return error_response(CHALLENGE_REQUIRED)


def _lookup_rejected(outcome: ProviderDataOutcome) -> Response:
    """A provider read that produced no classifiable account.

    Two client classes, and they are not interchangeable: a failed or indeterminate *lookup* is
    transient and earns `verification_temporarily_unavailable` ("back off and retry the whole
    operation"), while a successful lookup whose providerData the closed classifier rejects is a
    terminal statement about the account and earns `operation_not_allowed` ("contact support").

    **37-08 Task 2 owns the rest of this branch** -- the `user_not_found` arm (which is
    `auth_required`, not either class below), the internal results, the audit rows, and the
    consumption every rejection at or after this point owes.
    """
    logger.warning("create_user_lookup_rejected", outcome=str(outcome))
    if outcome is not ProviderDataOutcome.ok:
        return error_response(VERIFICATION_TEMPORARILY_UNAVAILABLE)
    return error_response(OPERATION_NOT_ALLOWED)


def _completion_response(result: AuthEventResult, provider: IdentityProvider) -> Response:
    """Map the transaction's internal result onto the client's answer.

    The internal result is never client-visible and is never less specific than the class returned
    -- that asymmetry is the point of having both.

    **37-09 owns the rejection arms** (the in-transaction re-resolution outcomes and the race
    loser). The success arm is complete: one field, the classified provider, and nothing else.
    """
    if result is not AuthEventResult.succeeded:
        logger.warning("create_user_transaction_rejected", result=str(result))
        return error_response(IDENTITY_ALREADY_LINKED
                              if result is AuthEventResult.identity_already_linked
                              else ACCOUNT_UNAVAILABLE)
    return JSONResponse(content=CompletionResponse(identity_provider=provider)
                        .model_dump(mode="json"))
