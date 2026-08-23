"""§02 step 10's consuming transaction for `create_user` -- one function, one transaction.

It lives here rather than inline in `routers/auth.py` for one reason, and the reason is testability
of the thing hardest to test: 37-09 has to drive this transaction from two real sessions
concurrently to prove that `UNIQUE (issuer, subject)` is the only race arbiter, and a body reachable
only through FastAPI cannot be driven that way. Everything it needs is a parameter.

**What the caller must have already done, and this function must never redo.**

* The provider read has happened, outside any transaction (§02 step 8, SHARED-INVARIANTS § Locks).
  This function opens the first transaction that outlives the provider call, and it performs no
  outbound call of its own -- not a lookup, not a retry, not a re-read.
* The account type is already classified. `provider` and `provider_uid` arrive resolved; the closed
  classifier is `auth/classifier.py`'s and runs once, in the router.
* The address to persist is already resolved. `email` arrives as the value to write, and §02 step
  10's two-condition copy rule has already been evaluated by `classifier.email_to_persist` at the
  one site that owns it. **There is deliberately no second email-related parameter of any kind**:
  a flag here would be a second place the rule could be re-evaluated, and two evaluation sites are
  two answers that can disagree (T-37-34). Write the argument through, unconditionally.
* `evaluated_at` and `attempt_id` are the request's, captured once by the barrier (35 D-02). This
  module reads no clock and generates no attempt id.

**The savepoint is the shape, not an optimisation.** §02 step 12 requires the challenge consumption
and the rejected audit row to *survive* a rolled-back business insert. Under this project's e2e
harness (`join_transaction_mode="create_savepoint"`) an `IntegrityError` marks the whole session
transaction as rolled back, so a consume issued after a conflict raises `PendingRollbackError` and
the attempt returns exactly the generic 500 step 12 forbids. `begin_nested()` around the business
inserts is what keeps the outer transaction live across a conflict. This was disproved-then-proved
empirically against PostgreSQL 17.11 under that harness (37-RESEARCH Pitfall 1 / Pattern 3) -- it is
settled, and not to be re-litigated into a consume-first conditional update.

**What is not here yet.** The `except IntegrityError` arm that classifies a conflict by constraint
name and rolls back *to* the savepoint belongs to 37-09, which owns conflict discrimination and both
race proofs. The savepoint is built here regardless, because the transaction's shape is the
architectural fact the tracer exists to prove and retrofitting it later would move every line in
this function.
"""
from datetime import datetime
from uuid import UUID, uuid4

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.audit import AuditWriter, build_details
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.models.purchase_tokens import PurchaseProvider, StorePurchaseToken
from nativespeaker.api.models.users import User

logger = structlog.get_logger()


async def create_account(session: AsyncSession, *,
                         context: RequestContext,
                         identity: PreAuthIdentity,
                         challenge: AuthChallenge,
                         provider: IdentityProvider,
                         provider_uid: str | None,
                         email: str | None,
                         challenge_store: ChallengeStore,
                         audit_writer: AuditWriter) -> AuthEventResult:
    """Run §02 step 10's transaction and return the internal result it earned.

    One transaction: the in-transaction re-resolution, the savepoint-wrapped business inserts, the
    challenge consumption, and the audit row -- committed together, exactly once. The caller maps
    the returned `AuthEventResult` onto a client-visible class and never re-derives it.
    """
    existing = await _resolve_existing(session, issuer=identity.issuer, subject=identity.subject)

    user_id: UUID | None = None
    if existing is None:
        user_id, result = await _insert_account(session,
                                                evaluated_at=context.evaluated_at,
                                                identity=identity,
                                                provider=provider,
                                                provider_uid=provider_uid,
                                                email=email)
    else:
        # §02 step 10's three no-mutation arms. The prepare-time pre-check is racy and never
        # authoritative, so this is the resolution that decides -- and it decides for a row that
        # may have appeared between prepare and now.
        result = _result_for_existing(existing)

    # Both of the following run on the outer transaction, on success and rejection alike (§02 step
    # 13: every rejection at or after the provider read consumes). Ordering matters only in that
    # both must precede the commit; neither commits on its own.
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge.challenge_id,
                                             claim_attempt_id=context.attempt_id,
                                             now=context.evaluated_at)
    if not consumed:
        # Not a branch to recover from -- this attempt holds the claim, so a `False` here means
        # stored state diverged from the lifecycle. Correlate on the non-secret row id; the public
        # handle is never logged (§6.1).
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await audit_writer.write_in_transaction(
        session,
        operation=AuthOperation.create_user,
        result=result,
        actor_issuer=identity.issuer,
        actor_subject=identity.subject,
        # NULL on purpose: §4.2 admits `actor_provider` only from the stored provider column of a
        # *resolved linked* identity, and this request's identity context is pre-auth. The provider
        # this attempt classified is recorded under `details.resolved` instead, where it reads as
        # what it is -- an outcome of the attempt, not the actor's established classification.
        actor_provider=None,
        challenge_row_id=challenge.id,
        details=_details(context, result=result, provider=provider, user_id=user_id),
        created_at=context.evaluated_at)

    await session.commit()
    return result


async def _resolve_existing(session: AsyncSession, *,
                            issuer: str, subject: str) -> ExternalIdentity | None:
    """§02 step 10's re-resolution, issued INSIDE the transaction.

    Prepare-time pre-auth status never suffices: the barrier resolved this pair minutes ago at
    prepare and again microseconds ago at completion, but neither read is inside this transaction,
    and the row this attempt is about to create is exactly the kind of row another attempt may have
    created in between.

    This is **not** the race arbiter and must never be strengthened into one. A check-then-insert
    has a window; `UNIQUE (issuer, subject)` and `UNIQUE (user_id)` do not, and §02 step 12 makes
    them the only arbiters. No `FOR UPDATE`, no advisory lock, no serializable isolation.
    """
    statement = select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                               col(ExternalIdentity.subject) == subject)
    return (await session.exec(statement)).first()


def _result_for_existing(existing: ExternalIdentity) -> AuthEventResult:
    """Map an already-present identity row onto its internal result. No mutation on any arm.

    `!= active` rather than `== historical`, so a NULL or a future enum member fails closed on the
    same branch instead of falling through into a creation the row forbids -- the strict form
    `auth/identity.py` uses for the same comparison.

    The blocked-user arm is 37-09's: distinguishing it needs the joined `core.users` row, and this
    read deliberately fetches one table. Both arms surface identically to the client anyway
    (`account_unavailable`, §02's mutually-indistinguishable pair), so the delta is which internal
    result is audited, not what the caller is told.
    """
    if existing.identity_state != IdentityState.active:
        return AuthEventResult.historical_identity
    return AuthEventResult.identity_already_linked


async def _insert_account(session: AsyncSession, *,
                          evaluated_at: datetime,
                          identity: PreAuthIdentity,
                          provider: IdentityProvider,
                          provider_uid: str | None,
                          email: str | None) -> tuple[UUID, AuthEventResult]:
    """The three business inserts, inside one savepoint. Either all land or none does.

    `registered_at` is NULL for anonymous and the request's evaluation time otherwise -- §02 step
    10's invariant is `registered_at IS NOT NULL` iff the provider is google or apple, with no
    third state, so it is derived from `provider` here rather than passed in as a fourth thing a
    caller could set inconsistently.

    `display_name` is never populated. Not defaulted, not copied from the provider record, not
    derived from the address: §02's DELETIONS list forbids it outright, and the column's absence
    from every construction below is the enforcement.
    """
    savepoint = await session.begin_nested()

    user = User(email=email,
                registered_at=None if provider is IdentityProvider.anonymous else evaluated_at,
                created_at=evaluated_at,
                updated_at=evaluated_at)
    session.add(user)
    await session.flush()

    session.add(ExternalIdentity(user_id=user.id,
                                 issuer=identity.issuer,
                                 subject=identity.subject,
                                 provider=provider,
                                 # NULL for anonymous, and never a sentinel: the CHECK requires it,
                                 # and a placeholder would drag the row into the partial
                                 # provider-account reservation it must stay outside of.
                                 provider_uid=provider_uid,
                                 identity_state=IdentityState.active,
                                 created_at=evaluated_at,
                                 updated_at=evaluated_at))

    # Minted EAGERLY on every branch, one row per store, for the account's life (§02 step 10).
    # Each value is a fresh `uuid4()` and nothing else: not derived from the user id, the subject,
    # the issuer, the address, or any other stable input, so neither value can become a cross-store
    # or cross-service correlation key. Iterating the enum rather than listing two literals is what
    # keeps "one per store" true if the enum ever grows.
    for store in PurchaseProvider:
        session.add(StorePurchaseToken(user_id=user.id,
                                       provider=store,
                                       identity_value=str(uuid4()),
                                       created_at=evaluated_at))

    await session.flush()
    await savepoint.commit()
    return user.id, AuthEventResult.succeeded


def _details(context: RequestContext, *,
             result: AuthEventResult,
             provider: IdentityProvider,
             user_id: UUID | None) -> dict:
    """§4.4's six-key object for this attempt.

    Built through `build_details` rather than as a literal: the builder is keyword-only, so a
    seventh top-level key is a `TypeError` at this call site instead of a CHECK violation at insert.

    Two things are absent by rule rather than by oversight -- the public challenge handle (§4.4; the
    row is correlated on `challenge_row_id`, and the redactor would drop it anyway) and the client
    address (only the bucket kind the barrier derived). The minted attribution values are absent for
    the same reason a token never appears in an audit row: they are the account's durable store
    identifiers, and this table is not where a second copy of them belongs.
    """
    succeeded = result is AuthEventResult.succeeded
    return build_details(
        context={"route": context.route_metadata.path,
                 "method": context.route_metadata.method,
                 "operation": AuthOperation.create_user,
                 "attempt_id": context.attempt_id,
                 "prepare_mode": False,
                 "completion_mode": True,
                 "client_ip_bucket_kind": context.client_ip_bucket_kind},
        verification={"provider_data_read": True},
        resolved={"identity_provider": provider,
                  "user_id": user_id},
        mutation={"user_created": succeeded,
                  "identity_created": succeeded,
                  "store_attribution_rows_minted": len(PurchaseProvider) if succeeded else 0,
                  "access_grant_created": False,
                  "monthly_usage_row_created": False},
        failure={} if succeeded else {"stage": "consuming_transaction"})
