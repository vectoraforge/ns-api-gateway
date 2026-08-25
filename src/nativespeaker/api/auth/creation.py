"""The consuming transaction for `create_user`: one function, one transaction, every input a parameter."""
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

# PostgreSQL's generated names for the two UNIQUE rules on external_identities; a schema test pins them.
RACE_CONSTRAINT_NAMES = frozenset({
    "external_identities_issuer_subject_key",
    "external_identities_user_id_key",
})

# A partial UNIQUE index, which asyncpg reports by name exactly as it reports a constraint.
PROVIDER_ACCOUNT_INDEX_NAME = "ix_external_identities_provider_account"

# The client class each non-succeeded result earns; the router maps it and never re-derives it.
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
    """Run the consuming transaction and return the internal result it earned."""
    existing = await resolve_existing_identity(session, issuer=identity.issuer, subject=identity.subject)

    if existing is None:
        _, result = await _insert_account(session,
                                          evaluated_at=context.evaluated_at,
                                          identity=identity,
                                          provider=provider,
                                          provider_uid=provider_uid,
                                          email=email)
    else:
        # The prepare-time pre-check is racy, so this resolution is the one that decides.
        result = await _result_for_existing(session, existing)

    # On the outer transaction, on success and rejection alike, before the commit and never itself.
    consumed = await challenge_store.consume(session,
                                             challenge_id=challenge.challenge_id,
                                             claim_attempt_id=context.attempt_id,
                                             now=context.evaluated_at)
    if not consumed:
        # This attempt holds the claim, so `False` means state diverged; the handle is never logged.
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await session.commit()
    return result


async def resolve_existing_identity(session: AsyncSession, *,
                                    issuer: str, subject: str) -> ExternalIdentity | None:
    """The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."""
    statement = select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                               col(ExternalIdentity.subject) == subject)
    return (await session.exec(statement)).first()


def classify_insert_conflict(exc: IntegrityError) -> AuthEventResult:
    """Which business outcome a rejected `INSERT` earned. An unmapped constraint re-raises, loudly."""
    name = _conflicting_constraint_name(exc)
    if name in RACE_CONSTRAINT_NAMES:
        return AuthEventResult.identity_already_linked
    if name == PROVIDER_ACCOUNT_INDEX_NAME:
        return AuthEventResult.provider_account_already_linked
    raise exc


def _conflicting_constraint_name(exc: IntegrityError) -> str | None:
    """The driver's `constraint_name`, walked down the cause chain -- never the rendered message."""
    cause: BaseException | None = exc.orig
    while cause is not None and not hasattr(cause, "constraint_name"):
        cause = cause.__cause__
    return getattr(cause, "constraint_name", None)


async def _result_for_existing(session: AsyncSession,
                               existing: ExternalIdentity) -> AuthEventResult:
    """Map an already-present identity row onto its result. No mutation, and every test fails closed."""
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
    """All three inserts in one savepoint: a conflict rolls them back but leaves the consume able to commit."""
    savepoint = await session.begin_nested()
    try:
        return await _flush_account(session, savepoint,
                                    evaluated_at=evaluated_at, identity=identity,
                                    provider=provider, provider_uid=provider_uid, email=email)
    except IntegrityError as conflict:
        # Rollback FIRST, classify second: until then the session refuses every further statement.
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
    return user.id, AuthEventResult.succeeded
