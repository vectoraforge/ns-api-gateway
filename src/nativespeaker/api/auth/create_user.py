"""The consuming transaction for `create_user`: one function, one transaction, every input a parameter."""
from datetime import datetime
from typing import NoReturn
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity, RequestContext
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import (
    BlockedUser,
    HistoricalIdentity,
    IdentityAlreadyLinked,
    ProviderAccountAlreadyLinked,
)
from nativespeaker.api.tables.auth import AuthChallenge
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.purchases import PurchaseProvider, StorePurchaseToken
from nativespeaker.api.tables.users import User

logger = structlog.get_logger()


async def create_user(session: AsyncSession, *,
                      context: RequestContext,
                      identity: LinkedIdentity | PreAuthIdentity,
                      challenge: AuthChallenge,
                      provider: IdentityProvider,
                      provider_uid: str | None,
                      email: str | None,
                      challenge_store: ChallengesDB) -> UUID:
    """Return the new user's id, or raise the rejection the transaction earned.

    Total rather than narrowed: the existing-identity branch has no success arm -- all three of its
    outcomes are rejections -- and the insert branch either succeeds or conflicts.
    """
    existing = await resolve_existing_identity(session, issuer=identity.issuer, subject=identity.subject)

    if existing is not None:
        # The prepare-time pre-check is racy, so this resolution is the one that decides.
        await _reject_existing_identity(session, existing)

    user_id = await _insert_account(session,
                                    evaluated_at=context.evaluated_at,
                                    identity=identity,
                                    provider=provider,
                                    provider_uid=provider_uid,
                                    email=email)

    # The success path's consume, on the outer transaction, before the commit and never itself.
    # A raising arm never reaches this line: it leaves the consume to the route's except arm, so
    # the two paths spend the handle exactly once between them.
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge.challenge_id,
                                             claim_attempt_id=context.attempt_id,
                                             now=context.evaluated_at)
    if not consumed:
        # This attempt holds the claim, so `False` means state diverged; the handle is never logged.
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await session.commit()
    return user_id


async def resolve_existing_identity(session: AsyncSession, *,
                                    issuer: str, subject: str) -> ExternalIdentity | None:
    """The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."""
    statement = select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                               col(ExternalIdentity.subject) == subject)
    return (await session.exec(statement)).first()


async def _reject_existing_identity(session: AsyncSession,
                                    existing: ExternalIdentity) -> NoReturn:
    """Raise what an already-present identity row earned. No mutation, and every test fails closed."""
    if existing.identity_state != IdentityState.active:
        raise HistoricalIdentity

    user = (await session.exec(select(User).where(col(User.id) == existing.user_id))).first()
    if user is None or user.active is not True:
        raise BlockedUser
    raise IdentityAlreadyLinked()


async def _insert_account(session: AsyncSession, *,
                          evaluated_at: datetime,
                          identity: LinkedIdentity | PreAuthIdentity,
                          provider: IdentityProvider,
                          provider_uid: str | None,
                          email: str | None) -> UUID:
    """All three inserts in one savepoint: a conflict rolls them back but leaves the consume able to commit."""
    savepoint = await session.begin_nested()
    try:
        return await _flush_account(session, savepoint,
                                    evaluated_at=evaluated_at, identity=identity,
                                    provider=provider, provider_uid=provider_uid, email=email)
    except IntegrityError as conflict:
        # Rollback FIRST, classify second: until then the session refuses every further statement.
        await savepoint.rollback()
        # The driver's own `constraint_name`, walked down the cause chain -- never the rendered
        # message, whose text depends on the server's locale and names no rule unambiguously.
        cause: BaseException | None = conflict.orig
        while cause is not None and not hasattr(cause, "constraint_name"):
            cause = cause.__cause__
        name = getattr(cause, "constraint_name", None)

        if name in ("external_identities_issuer_subject_key", "external_identities_user_id_key"):
            raise IdentityAlreadyLinked() from conflict
        if name == "ix_external_identities_provider_account":
            raise ProviderAccountAlreadyLinked() from conflict
        # A name nobody mapped is a new constraint or a rename, which is a bug. Re-raising it
        # unchanged is a deliberate 500 tripwire: reported as a benign 409 it would never be found.
        raise conflict


async def _flush_account(session: AsyncSession, savepoint, *,
                         evaluated_at: datetime,
                         identity: LinkedIdentity | PreAuthIdentity,
                         provider: IdentityProvider,
                         provider_uid: str | None,
                         email: str | None) -> UUID:
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
                                 # NULL for anonymous, never a sentinel: the CHECK requires it.
                                 provider_uid=provider_uid,
                                 identity_state=IdentityState.active,
                                 created_at=evaluated_at,
                                 updated_at=evaluated_at))

    # One per store, minted eagerly. A fresh `uuid4()` derived from nothing, so it correlates nothing.
    for store in PurchaseProvider:
        session.add(StorePurchaseToken(user_id=user.id,
                                       provider=store,
                                       identity_value=str(uuid4()),
                                       created_at=evaluated_at))

    await session.flush()
    await savepoint.commit()
    return user.id
