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
not in a log line, not in error text. Correlation is on the non-secret `core.auth_challenges.id`.
"""
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import JSONResponse, Response

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_raw_query_string,
    get_request_context,
)
from nativespeaker.api.auth.adapters import ProviderDataEntry, ProviderDataOutcome
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.classifier import classify_provider_data, email_to_persist
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import (
    CLIENT_CLASS_FOR_RESULT,
    create_account,
    resolve_existing_identity,
)
from nativespeaker.api.auth.modesignal import ModeSignal, classify_mode_signal
from nativespeaker.api.auth.retry import (
    LOOKUP_UNAVAILABLE_ERROR_CLASS,
    LOOKUP_UNAVAILABLE_RESULT,
    lookup_with_retry,
)
from nativespeaker.api.errors import (
    AUTH_REQUIRED,
    CHALLENGE_REQUIRED,
    IDENTITY_ALREADY_LINKED,
    INVALID_REQUEST,
    OPERATION_NOT_ALLOWED,
    ErrorClass,
    error_response,
)
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState

logger = structlog.get_logger()

# Authentication is default-on for this router (D-07), but the declaration is
# `get_request_context` rather than one of the two narrowing accessors -- the one departure from
# D-08's table, and the same reason `create_user` reads the variant off the context instead of
# demanding a pre-auth one: `get_preauth_identity` raises on a *linked* caller, and here that
# caller is a client condition §02 prepare step 1 answers with `identity_already_linked` (409), not
# a wiring bug to answer with a 401. The property D-07 is buying is unaffected -- the token is
# still verified and the identity still resolved before any handler in this router runs.
router = APIRouter(tags=["auth"], dependencies=[Depends(get_request_context)])


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
                      challenge_store: ChallengeStore = Depends(get_challenge_store),
                      adapter=Depends(get_firebase_adapter)) -> Response:
    """Classify the mode signal, then dispatch. The classification itself has no side effects.

    §6.5's partition is evaluated before anything is issued, looked up or consumed, so a corrected
    retry may reuse the same unexpired challenge. A `None` classification is `invalid_request`
    (400): it belongs to the admission phase and has no internal `AuthEventResult` -- it is
    recorded in the structured security log alone.

    **This route reads the identity variant off the context rather than demanding a pre-auth one,
    and it is the only route in the system that does.** `Depends(get_preauth_identity)` raises on a
    linked caller -- correctly, for every other handler, where a linked context arriving at a
    pre-auth-only handler is a wiring bug. Here it is a *client condition* §02 prepare step 1 names
    explicitly: a caller who already has an account gets `identity_already_linked` (409), not
    `auth_required` (401), and the two say incompatible things to a client. Nothing is given up by
    reading the variant here: `get_request_context` is declared on this router as well as in the
    signature below, so the token is verified and the identity resolved before this body runs --
    the only thing this route decides for itself is what to do with the variant that came back.
    """
    body_challenge_id = None if body is None else body.challenge_id
    mode = classify_mode_signal(raw_query, body_challenge_id)
    if mode is None:
        logger.warning("auth_mode_signal_invalid",
                       route=context.route,
                       operation=str(AuthOperation.create_user),
                       # The raw value is never logged: an unusable handle is still a handle
                       # somebody typed, and the shape is the whole diagnostic.
                       body_present=body is not None)
        return error_response(INVALID_REQUEST)

    identity = context.identity
    if mode is ModeSignal.prepare:
        return await _prepare(session, context=context, identity=identity,
                              challenge_store=challenge_store)

    # `classify_mode_signal` returns `completion` only for a non-empty `str`, so the annotation
    # below is the partition's guarantee rather than this handler's assumption -- and the value is
    # forwarded **untouched**. `locate` compares byte-for-byte, so a whitespace-padded handle is
    # `challenge_not_found`, not `invalid_request`: a deliberate asymmetry, not an oversight to
    # tidy up with a `.strip()` here.
    completion_handle: str = body_challenge_id  # ty: ignore[invalid-assignment]
    return await _complete(session, context=context, identity=identity,
                           challenge_id=completion_handle,
                           challenge_store=challenge_store,
                           adapter=adapter)


async def _prepare(session: AsyncSession, *,
                   context: RequestContext,
                   identity: LinkedIdentity | PreAuthIdentity,
                   challenge_store: ChallengeStore) -> Response:
    """§02 prepare steps 1, 4 and 5: fail fast, then issue one challenge and disclose two fields.

    Prepare mutates **no** business state -- no user, no identity, no grant, no attribution token.
    The only row it writes is the challenge itself, inside the request's one transaction, which
    `get_db` commits when this handler returns.

    `expires_at` comes from the store, derived from the request's single captured evaluation time.
    Nothing here recomputes it, extends it, or renews it on retry.
    """
    linked = await _already_linked(session, identity=identity)
    if linked is not None:
        # Nothing is read off the row, and the read transaction is left alone: the rollback that
        # used to stand here existed solely to free the session for a standalone write, and reading
        # `linked.provider` after it was 37-REVIEW CR-02 -- an attribute expired by that very
        # rollback, whose lazy load off the event loop turned this 409 into a 500.
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


async def _complete(session: AsyncSession, *,
                    context: RequestContext,
                    identity: LinkedIdentity | PreAuthIdentity,
                    challenge_id: str,
                    challenge_store: ChallengeStore,
                    adapter) -> Response:
    """§02 completion steps 3-14, in the specification's own order.

    The numbering is normative rejection precedence: reject for the earliest failed step. Every
    rejection below therefore has to stay where it is relative to its neighbours, even when a later
    check would be cheaper to run first.
    """
    # --- Steps 3-5, in one transaction that COMMITS before the provider call. ---
    #
    # **None of the five rejections below consumes anything**, and that is the part easiest to get
    # backwards, so it is stated once here rather than repeated at each arm:
    #
    # * `challenge_not_found` has no row at all;
    # * the identity and operation mismatches are rejected BEFORE the claim, on purpose, so a wrong
    #   presenter can never burn the rightful user's in-flight challenge (§6.4, T-37-35);
    # * the two claim losers never held a claim, so there is nothing for them to consume.
    #
    # Consumption begins at the Admin lookup and covers every rejection from there on.
    challenge = await challenge_store.locate(session, challenge_id)
    if challenge is None:
        # A definitive no-row. A database outage during the lookup is NOT this -- it raises out of
        # `locate` and stays the ordinary infrastructure failure, because answering "no such
        # challenge" to an unreachable database tells a legitimate client to throw away a challenge
        # that exists. The raw malformed identifier is never logged.
        return await _challenge_rejected(session, result=AuthEventResult.challenge_not_found)

    # Every `ChallengeRejection` member's value is also an `AuthEventResult` member, precisely so a
    # caller needs no private mapping table -- so this maps straight through by name. No keyed
    # comparison is written here either: `verify_binding` already routes it through
    # `HmacKeyring.actor_subject_matches`, and a second comparison is a second answer. The
    # constant-time primitive's name stays absent from this module so a grep for it remains a live
    # detector of exactly that mistake.
    rejection = challenge_store.verify_binding(challenge, identity)
    if rejection is not None:
        return await _challenge_rejected(session, result=AuthEventResult(rejection.value))
    if challenge.operation is not AuthOperation.create_user:
        # D-12 removed step 6's provider-*variant* check, not this one. A challenge issued for a
        # different operation and presented here is still step 4's rejection, and still pre-claim.
        return await _challenge_rejected(
            session, result=AuthEventResult.challenge_operation_mismatch)

    if not await challenge_store.claim(session,
                                       challenge_id=challenge_id,
                                       claim_attempt_id=context.attempt_id,
                                       now=context.evaluated_at):
        # The claim is the single serialization point and the only expiry evaluation anywhere. A
        # loser matched zero rows, mutated nothing, and performs no work at all from here.
        #
        # The two reasons are distinguished by **re-reading the located row**, not by issuing a
        # second conditional update -- `challenges.py:168-172` says so explicitly, and a second
        # conditional update would be a second serialization point that can disagree with the
        # first. `claimed_at` alone answers it: still NULL means the row is issued and the claim
        # can only have failed its deadline; non-NULL means somebody else already holds it.
        # Reading the row's expiry deadline here instead would be a second expiry evaluation,
        # which is exactly what the store's WHERE exists to prevent -- and the deadline column is
        # deliberately not named anywhere in this handler, so a grep for it stays a live detector.
        await session.refresh(challenge)
        lost = (AuthEventResult.challenge_expired if challenge.claimed_at is None
                else AuthEventResult.challenge_consumed)
        return await _challenge_rejected(session, result=lost)

    # **This commit is load-bearing; see module docstring point 1.** The claim must be durable
    # before the provider call, or a crash during the lookup leaves the challenge unclaimed and a
    # second attempt could win it -- contradicting §6.2's "a claimed challenge is dead".
    await session.commit()

    # --- Step 7: almost entirely gone, and recorded here rather than silently skipped. ---
    #
    # §02 step 7 gates the read on three budgets checked non-destructively broadest-to-narrowest.
    # D-02 drops `create_user_firebase_identity_lookup` (60/min, key `deployment`) and
    # `create_user_firebase_identity_lookup_ip` (10/min, key client IP): both are per-minute IP- and
    # deployment-keyed *traffic* limits written in budget vocabulary, and building anything that
    # could carry them is what D-01 rules out for this route. Only the retry budget survives, and
    # D-04 expresses it as `tenacity` in `auth/retry.py`.
    #
    # **This is a flagged SHARED-INVARIANTS conflict, recorded and not silently resolved** (T-37-40,
    # accepted). A reader comparing this handler to §02 finds the answer here instead of assuming an
    # omission. One request still costs at most three provider calls, each timeout-bounded.

    # --- Step 8: the provider read, with NO transaction open. ---
    # Exactly one mandatory fail-closed read per completion, on EVERY completion -- anonymous and
    # registered alike, with no branch skipping it. `lookup_with_retry` returns under every outcome
    # including exhaustion, so no `tenacity.RetryError` can reach a client from here.
    provider_data = await lookup_with_retry(adapter, identity.issuer, identity.subject)

    if provider_data.outcome is not ProviderDataOutcome.ok:
        return await _consuming_rejection(session, context=context,
                                          challenge=challenge,
                                          stage="provider_lookup",
                                          challenge_store=challenge_store,
                                          **_LOOKUP_REJECTIONS[provider_data.outcome])

    # --- Steps 9-10: classify the account and resolve the address, both from THIS one response. ---
    classified = classify_provider_data(provider_data.entries)
    if classified is None:
        return await _consuming_rejection(session, context=context,
                                          challenge=challenge,
                                          result=AuthEventResult.provider_not_linked,
                                          error_class=OPERATION_NOT_ALLOWED,
                                          stage="provider_classification",
                                          cause=_classification_cause(provider_data.entries),
                                          challenge_store=challenge_store)
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
                                  challenge_store=challenge_store)

    # --- Step 14: return the resulting backend state, and nothing more. ---
    return _completion_response(result, provider)


async def _challenge_rejected(session: AsyncSession, *, result: AuthEventResult) -> Response:
    """The five §6 challenge rejections collapse into one client class (§02's error table).

    `challenge_required` for all of them -- byte-identical body and status -- so completion is not
    a challenge-enumeration oracle: a client cannot learn whether a handle was unknown, expired,
    already used, bound to somebody else, or bound to another operation. **Only the structured log
    differs**, and it carries the specific internal result, which is never less specific than the
    class returned (T-37-34).

    None of the five consumes; see the disposition note at the call sites. None of them has written
    anything either -- the pre-claim arms mutate nothing and a claim loser matched zero rows -- so
    the rollback releases the read transaction `locate` opened rather than undoing work.
    """
    # The specific internal result, in the structured log only. The client sees one collapsed class
    # and the public handle is never logged (§6.1).
    logger.warning("create_user_challenge_rejected", stage=str(result))
    await session.rollback()
    return error_response(CHALLENGE_REQUIRED)


# §02 step 8's three non-`ok` outcomes, onto their internal result and their client class.
#
# **Three outcomes, and collapsing any pair is a client-contract bug.** `user_not_found` is
# definitive, spends no retry budget, and persists nothing -- a valid token for a *deleted* Firebase
# user must not create an account. It is explicitly **not** `verification_temporarily_unavailable`:
# the two are one letter apart in intent, and the wrong one tells the client to retry forever
# against a fact Firebase has already stated permanently (T-37-37, T-37-38).
#
# The unavailable pair comes from `auth/retry.py`'s named constants rather than repeated literals,
# so the mapping `BudgetExhausted` used to carry as class data stays one named fact across §7.1's
# five providerData read points.
_LOOKUP_REJECTIONS: dict[ProviderDataOutcome, dict[str, object]] = {
    ProviderDataOutcome.user_not_found: {
        "result": AuthEventResult.firebase_user_unresolved,
        "error_class": AUTH_REQUIRED,
    },
    ProviderDataOutcome.retryable_failure: {
        "result": LOOKUP_UNAVAILABLE_RESULT,
        "error_class": LOOKUP_UNAVAILABLE_ERROR_CLASS,
    },
    ProviderDataOutcome.selection_failure: {
        "result": LOOKUP_UNAVAILABLE_RESULT,
        "error_class": LOOKUP_UNAVAILABLE_ERROR_CLASS,
    },
}


def _classification_cause(entries: tuple[ProviderDataEntry, ...]) -> str:
    """§02 step 9's bounded `provider_not_linked` cause. D-12 left it exactly two members.

    `empty` is the answer where an account carries no providerData in a context that *required* one.
    This route is not such a context -- the closed classifier answers `anonymous` to an empty read
    and never rejects it -- so `empty` is unreachable from here and is kept because phases 40/41/42
    do require a linked provider and reach the same bounded vocabulary. Writing the branch is what
    keeps the vocabulary one fact rather than one per caller.
    """
    return "empty" if not entries else "invalid-shape"


async def _consuming_rejection(session: AsyncSession, *,
                               context: RequestContext,
                               challenge: AuthChallenge,
                               result: AuthEventResult,
                               error_class: ErrorClass,
                               stage: str,
                               challenge_store: ChallengeStore,
                               cause: str | None = None) -> Response:
    """A rejection at or after the Admin lookup: it **consumes**, and it persists nothing else.

    §02 step 13 makes consumption unconditional from the provider read onwards -- a retry requires a
    fresh prepare, and a handle that survived a rejection would be a handle an attacker could
    re-present (T-37-39). There is no business mutation on any arm this serves, so the transaction
    it opens holds exactly one thing: the conditional consume, committed on its own.

    Consumption clears `preauth_subject_hash` in the same statement, which is why a later
    presentation of the same handle takes the already-used rejection rather than a mismatch.

    `cause` is the bounded `provider_not_linked` reason and is present for that result alone. It is
    omitted rather than `None`-valued everywhere else, so a reader of the log cannot mistake "not
    applicable" for "applicable and unknown". Like every bounded reason it is never client-visible.
    """
    bounded = {} if cause is None else {"cause": cause}
    logger.warning("create_user_lookup_rejected", stage=stage, result=str(result), **bounded)
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge.challenge_id,
                                             claim_attempt_id=context.attempt_id,
                                             now=context.evaluated_at)
    if not consumed:
        # Not a branch to recover from -- this attempt holds the claim, so a `False` here means
        # stored state diverged from the lifecycle. Correlated on the non-secret row id; the public
        # handle is never logged (§6.1).
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await session.commit()
    return error_response(error_class)


def _completion_response(result: AuthEventResult, provider: IdentityProvider) -> Response:
    """Map the transaction's internal result onto the client's answer.

    The internal result is never client-visible and is never less specific than the class returned
    -- that asymmetry is the point of having both.

    The rejection arms key on `CLIENT_CLASS_FOR_RESULT`, exported by the transaction that produces
    these results, so the mapping has exactly one definition. The local two-arm form this replaced
    collapsed `provider_account_already_linked` onto `ACCOUNT_UNAVAILABLE`; §02 step 11 gives it
    `operation_not_allowed` -- the same 403, but a different code and a different remediation.
    The success arm is complete: one field, the classified provider, and nothing else.
    """
    if result is not AuthEventResult.succeeded:
        logger.warning("create_user_transaction_rejected", result=str(result))
        return error_response(CLIENT_CLASS_FOR_RESULT[result])
    return JSONResponse(content=CompletionResponse(identity_provider=provider)
                        .model_dump(mode="json"))
