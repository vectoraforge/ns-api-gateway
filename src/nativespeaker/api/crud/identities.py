"""The identity store: the resolving query, the re-resolution, the account insert and the provider flip.
Lock order: the identity row and then its user row, taken together by the one joined statement below."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.errors import (
    BlockedUser,
    HistoricalIdentity,
    IdentityAlreadyLinked,
    IdentityUnresolvable,
    PreAuthIdentityNotAllowed,
    ProviderAccountAlreadyLinked,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.purchases import PurchaseProvider, StorePurchaseToken
from nativespeaker.api.tables.users import User


class IdentitiesDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve(self, *, issuer: str, subject: str, allow_preauth: bool) -> Identity:
        """Resolve a verified `(issuer, subject)` or raise the rejection it earned, using a single query."""
        # Outer join: an identity row whose user_id resolves to nothing must stay distinct from no row.
        statement = (select(ExternalIdentity, User)
                     .join(User, col(ExternalIdentity.user_id) == col(User.id), isouter=True)
                     .where(col(ExternalIdentity.issuer) == issuer,
                            col(ExternalIdentity.subject) == subject))
        row = (await self.session.exec(statement)).first()

        if row is None:
            # Identity rows are never deleted, so no row can only mean this pair was never linked.
            if allow_preauth:
                return Identity(issuer=issuer, subject=subject)
            raise PreAuthIdentityNotAllowed

        identity, user = row
        if user is None:
            # A broken link is unresolvable state: fail closed rather than read it as an unlinked pair.
            raise IdentityUnresolvable
        # Positive tests, so a NULL or any future enum member fails closed on these same two branches.
        if identity.identity_state != IdentityState.active:
            raise HistoricalIdentity
        if user.active is not True:
            raise BlockedUser
        return Identity(issuer=issuer, subject=subject, user=user, identity=identity)

    async def resolve_existing(self, *, issuer: str, subject: str) -> ExternalIdentity | None:
        """The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."""
        statement = select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                                   col(ExternalIdentity.subject) == subject)
        return (await self.session.exec(statement)).first()

    async def lock_identity_and_user(self, *, issuer: str,
                                     subject: str) -> tuple[ExternalIdentity, User] | None:
        """Lock and return the identity row and its user, or `None`. Revalidation, never a race arbiter."""
        # Inner join: Postgres refuses a row lock on the nullable side of the outer join `resolve` uses.
        statement = (select(ExternalIdentity, User)
                     .join(User, col(ExternalIdentity.user_id) == col(User.id))
                     .where(col(ExternalIdentity.issuer) == issuer,
                            col(ExternalIdentity.subject) == subject)
                     .with_for_update())
        row = (await self.session.exec(statement)).first()
        if row is None:
            return None
        identity, user = row
        return identity, user

    async def user_by_id(self, user_id: UUID | None) -> User | None:
        """The user an identity row points at, or `None`."""
        return (await self.session.exec(select(User).where(col(User.id) == user_id))).first()

    async def insert_account(self, *,
                             evaluated_at: datetime,
                             identity: Identity,
                             provider: IdentityProvider,
                             provider_uid: str | None,
                             email: str | None) -> UUID:
        """Insert the user, its identity row and its purchase tokens, and return the new user's id."""
        try:
            user = User(email=email,
                        registered_at=None if provider is IdentityProvider.anonymous else evaluated_at,
                        created_at=evaluated_at,
                        updated_at=evaluated_at)
            self.session.add(user)
            await self.session.flush()

            self.session.add(ExternalIdentity(user_id=user.id,
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
                self.session.add(StorePurchaseToken(user_id=user.id,
                                                    provider=store,
                                                    identity_value=str(uuid4()),
                                                    created_at=evaluated_at))

            await self.session.flush()
            return user.id
        except IntegrityError as conflict:
            raise IdentityAlreadyLinked() from conflict

    async def flip_provider(self, *,
                            evaluated_at: datetime,
                            identity_row: ExternalIdentity,
                            user: User,
                            provider: IdentityProvider,
                            provider_uid: str | None,
                            email: str | None) -> IdentityProvider:
        """Write both halves of the flip in the caller's transaction, and return the provider written."""
        stored_provider = identity_row.provider
        identity_row.provider = provider
        identity_row.provider_uid = provider_uid
        identity_row.updated_at = evaluated_at
        user.registered_at = evaluated_at
        user.updated_at = evaluated_at
        if user.email is None:
            # A stored address is never overwritten, and a divergent live one is simply not copied.
            user.email = email

        # Only the flush is inside: an ORM assignment sends nothing to the database.
        try:
            await self.session.flush()
        except IntegrityError as conflict:
            raise ProviderAccountAlreadyLinked(identity_row_id=identity_row.id,
                                               stored_provider=stored_provider,
                                               live_provider=provider) from conflict
        return provider
