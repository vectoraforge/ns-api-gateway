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
to *survive* a rolled-back business insert. Under this project's e2e
harness (`join_transaction_mode="create_savepoint"`) an `IntegrityError` marks the whole session
transaction as rolled back, so a consume issued after a conflict raises `PendingRollbackError` and
the attempt returns exactly the generic 500 step 12 forbids. `begin_nested()` around the business
inserts is what keeps the outer transaction live across a conflict. This was disproved-then-proved
empirically against PostgreSQL 17.11 under that harness (37-RESEARCH Pitfall 1 / Pattern 3) -- it is
settled, and not to be re-litigated into a consume-first conditional update.

**The database is the only race arbiter, and the constraint that fired is the only discriminator.**
Two completions can both observe an unlinked subject; nothing in this module tries to stop that,
and nothing may be added that does. The loser is whoever the `INSERT` rejects, and *which* rule
rejected it decides what the caller is told -- so the arm below reads the constraint name off the
driver exception rather than inspecting the message text, which is brittle and locale-fragile. See
`RACE_CONSTRAINT_NAMES` for the mapping and for what happens to a name nobody mapped.
"""
from datetime import datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity, RequestContext
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    IDENTITY_ALREADY_LINKED,
    OPERATION_NOT_ALLOWED,
    ErrorClass,
)
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.models.purchase_tokens import PurchaseProvider, StorePurchaseToken
from nativespeaker.api.models.users import User

logger = structlog.get_logger()

# §02 step 12's two arbiters over `core.external_identities`, by the names PostgreSQL reports for
# them. The migration names neither rule explicitly, so both names below are *generated* -- which
# means they are not a stable contract and must never be trusted on the strength of the pattern
# alone. `tests/schema/test_create_atomicity.py` reads the live names out of `pg_constraint` and
# `pg_class` and asserts they still equal these literals, so a migration that names a constraint
# explicitly breaks a test rather than silently misclassifying a conflict as an unmapped one.
#
#   external_identities_issuer_subject_key -> UNIQUE (issuer, subject)
#   external_identities_user_id_key        -> UNIQUE (user_id)
#
# Both mean the same thing to the caller: an account already exists for this identity, reconcile it
# through `/auth/sync` rather than creating a second one.
RACE_CONSTRAINT_NAMES = frozenset({
    "external_identities_issuer_subject_key",
    "external_identities_user_id_key",
})

# §02 step 11's conflict, and a standalone PARTIAL UNIQUE INDEX rather than a table constraint --
# `UNIQUE (issuer, provider, provider_uid) WHERE provider_uid IS NOT NULL`. asyncpg reports an index
# by name exactly as it reports a constraint, which is what makes one discriminator sufficient for
# both. This one is terminal for the caller and routes to support; keeping it apart from the two
# above is a client-contract requirement, not a nicety.
PROVIDER_ACCOUNT_INDEX_NAME = "ix_external_identities_provider_account"

# Every internal result this transaction can return that is not `succeeded`, and the client class it
# earns. Declared here, beside the code that produces the results, so the two cannot drift: the
# router maps the returned result onto a class and never re-derives it.
#
# `historical_identity` and `blocked_user` deliberately share one class -- §02 makes them mutually
# indistinguishable to a client, and only the internal result tells them apart.
CLIENT_CLASS_FOR_RESULT: dict[AuthEventResult, ErrorClass] = {
    AuthEventResult.identity_already_linked: IDENTITY_ALREADY_LINKED,
    AuthEventResult.provider_account_already_linked: OPERATION_NOT_ALLOWED,
    AuthEventResult.historical_identity: ACCOUNT_UNAVAILABLE,
    AuthEventResult.blocked_user: ACCOUNT_UNAVAILABLE,
}


async def create_account(session: AsyncSession, *,
                         context: RequestContext,
                         identity: LinkedIdentity | PreAuthIdentity,
                         challenge: AuthChallenge,
                         provider: IdentityProvider,
                         provider_uid: str | None,
                         email: str | None,
                         challenge_store: ChallengeStore) -> AuthEventResult:
    """Run §02 step 10's transaction and return the internal result it earned.

    One transaction: the in-transaction re-resolution, the savepoint-wrapped business inserts and
    the challenge consumption -- committed together, exactly once. The caller maps the returned
    `AuthEventResult` onto a client-visible class and never re-derives it.
    """
    existing = await resolve_existing_identity(session, issuer=identity.issuer, subject=identity.subject)

    if existing is None:
        _, result = await _insert_account(session,
                                          evaluated_at=context.evaluated_at,
                                          identity=identity,
                                          provider=provider,
                                          provider_uid=provider_uid,
                                          email=email)
    else:
        # §02 step 10's three no-mutation arms. The prepare-time pre-check is racy and never
        # authoritative, so this is the resolution that decides -- and it decides for a row that
        # may have appeared between prepare and now.
        result = await _result_for_existing(session, existing)

    # Runs on the outer transaction, on success and rejection alike (§02 step 13: every rejection
    # at or after the provider read consumes). It must precede the commit and does not commit on
    # its own.
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge.challenge_id,
                                             claim_attempt_id=context.attempt_id,
                                             now=context.evaluated_at)
    if not consumed:
        # Not a branch to recover from -- this attempt holds the claim, so a `False` here means
        # stored state diverged from the lifecycle. Correlate on the non-secret row id; the public
        # handle is never logged (§6.1).
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await session.commit()
    return result


async def resolve_existing_identity(session: AsyncSession, *,
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


def classify_insert_conflict(exc: IntegrityError) -> AuthEventResult:
    """Which business outcome a rejected `INSERT` earned -- or nothing, loudly.

    Exactly three constraint names are business outcomes here. Every other name, including the
    provider/provider_uid agreement CHECK (`external_identities_check`, which §02 step 10 derives
    `provider_uid` specifically so as not to reach), is a defect in this service rather than a
    statement about the caller's account -- so it re-raises. Swallowing an unmapped conflict as a
    business branch is the failure this function exists to prevent: it would convert a programming
    error into a plausible, permanent-looking answer that tells the client to do the wrong thing.

    Re-raising the original exception rather than a fresh one keeps the driver's own diagnostics --
    the constraint, the detail line, the statement -- attached to the traceback that surfaces.
    """
    name = _conflicting_constraint_name(exc)
    if name in RACE_CONSTRAINT_NAMES:
        return AuthEventResult.identity_already_linked
    if name == PROVIDER_ACCOUNT_INDEX_NAME:
        return AuthEventResult.provider_account_already_linked
    raise exc


def _conflicting_constraint_name(exc: IntegrityError) -> str | None:
    """The `constraint_name` the driver reported, walking down to the exception that carries it.

    SQLAlchemy's `IntegrityError.orig` is the dialect's own wrapper and the asyncpg exception is
    its `__cause__`, so the walk is normally one step; it is written as a loop rather than a fixed
    `orig.__cause__` because a driver or dialect that nests one level deeper would otherwise turn
    every conflict into an unmapped re-raise. `None` when nothing in the chain carries one, which
    the caller treats as unmapped.

    Reading a structured field off the driver exception is the whole point. The alternative --
    matching against the rendered message -- depends on PostgreSQL's message wording and on the
    server's `lc_messages`, and a substring match would silently accept the wrong one of two rules
    that name the same table.
    """
    cause: BaseException | None = exc.orig
    while cause is not None and not hasattr(cause, "constraint_name"):
        cause = cause.__cause__
    return getattr(cause, "constraint_name", None)


async def _result_for_existing(session: AsyncSession,
                               existing: ExternalIdentity) -> AuthEventResult:
    """Map an already-present identity row onto its internal result. No mutation on any arm.

    `!= active` rather than `== historical`, so a NULL or a future enum member fails closed on the
    same branch instead of falling through into a creation the row forbids -- the strict form
    `auth/identity.py` uses for the same comparison.

    An active row costs one further read, of its `core.users` row, because `blocked_user` and
    `identity_already_linked` are different internal results and the identity row alone cannot tell
    them apart. That read is issued only on this arm: a non-active row is already decisive, and a
    second query to reach the same answer would be work spent to learn nothing. `is not True` is
    the barrier's positive test, so an unexpected value rejects rather than being read as
    permission -- and an absent user row, which the FK's `ON DELETE RESTRICT` makes unreachable,
    fails closed on the same branch. §02's rule there is explicit: refuse, and never invent or
    reassign an identity to repair it.

    `blocked_user` and `historical_identity` surface identically to the client
    (`account_unavailable`, §02's mutually-indistinguishable pair). The delta is the internal
    result this function returns.
    """
    if existing.identity_state != IdentityState.active:
        return AuthEventResult.historical_identity

    user = (await session.exec(select(User).where(col(User.id) == existing.user_id))).first()
    if user is None or user.active is not True:
        return AuthEventResult.blocked_user
    return AuthEventResult.identity_already_linked


async def _insert_account(session: AsyncSession, *,
                          evaluated_at: datetime,
                          identity: LinkedIdentity | PreAuthIdentity,
                          provider: IdentityProvider,
                          provider_uid: str | None,
                          email: str | None) -> tuple[UUID | None, AuthEventResult]:
    """The three business inserts, inside one savepoint. Either all land or none does.

    `registered_at` is NULL for anonymous and the request's evaluation time otherwise -- §02 step
    10's invariant is `registered_at IS NOT NULL` iff the provider is google or apple, with no
    third state, so it is derived from `provider` here rather than passed in as a fourth thing a
    caller could set inconsistently.

    `display_name` is never populated. Not defaulted, not copied from the provider record, not
    derived from the address: §02's DELETIONS list forbids it outright, and the column's absence
    from every construction below is the enforcement.

    **Why the savepoint, and why it may not be simplified away.** §02 step 12 requires the challenge
    consumption to *survive* a rolled-back business insert. PostgreSQL aborts the entire transaction
    on a failed statement, and SQLAlchemy mirrors that by refusing every further statement until an
    explicit rollback -- so without a savepoint the consume that follows a conflict raises
    `PendingRollbackError`, the commit raises too, and the attempt returns exactly the generic 500
    step 12 forbids while leaving the challenge replayable. Rolling back *to* the savepoint discards
    the three inserts and leaves the **outer** transaction live, which is what lets the caller
    finish normally. Consuming earlier in the same transaction does not help: the abort would roll
    the consume back too. This was settled empirically against PostgreSQL 17.11 under this project's
    e2e harness configuration (37-RESEARCH Pitfall 1 / Pattern 3) -- it is a correctness
    requirement, not a tradeoff.

    All **three** inserts share the one savepoint, including the attribution tokens: a conflict on
    the third must undo the first two, or the account is the partial one §02 forbids.
    """
    savepoint = await session.begin_nested()
    try:
        return await _flush_account(session, savepoint,
                                    evaluated_at=evaluated_at, identity=identity,
                                    provider=provider, provider_uid=provider_uid, email=email)
    except IntegrityError as conflict:
        # Rollback FIRST, classify second. Until the savepoint is released the session refuses
        # every further statement, so a classifier that raised before this line would leave the
        # outer transaction poisoned and take the consume down with it.
        await savepoint.rollback()
        return None, classify_insert_conflict(conflict)


async def _flush_account(session: AsyncSession, savepoint, *,
                         evaluated_at: datetime,
                         identity: LinkedIdentity | PreAuthIdentity,
                         provider: IdentityProvider,
                         provider_uid: str | None,
                         email: str | None) -> tuple[UUID, AuthEventResult]:
    """The inserts themselves, so the arm above reads as one rollback around one body."""
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
