from datetime import UTC, datetime
from uuid import UUID, uuid7

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth import UserIdentity
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.profile import assert_user_created_with_identity
from nativespeaker.api.models import User
from nativespeaker.api.models.users import ExternalIdentity


class UsersDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self,
                            identity: UserIdentity,
                            *,
                            issuer: str,
                            provider: IdentityProvider = IdentityProvider.anonymous) -> User:
        """Resolve the internal user behind a verified `(issuer, subject)`, creating the user row
        and its external identity row together when none exists.

        Identity lookup is by exact `(issuer, subject)` on `core.external_identities`; the stored
        profile email never selects or merges an account.
        """
        existing = await self.session.exec(
            select(User)
            .join(ExternalIdentity, ExternalIdentity.user_id == User.id)  # type: ignore[arg-type]
            .where(ExternalIdentity.issuer == issuer,
                   ExternalIdentity.subject == identity.sub)
        )
        found = existing.first()
        if found is not None:
            return found
        # The two rows are written in one transaction: if either insert fails the whole
        # transaction rolls back and no account exists.
        # [impl->req~schema-users-created-with-identity-row~1]
        now = datetime.now(UTC)
        user = User(id=uuid7(), email=identity.email, display_name=identity.name,
                    registered_at=now if provider is not IdentityProvider.anonymous else None,
                    created_at=now, updated_at=now)
        self.session.add(user)
        self.session.add(ExternalIdentity(user_id=user.id, issuer=issuer,
                                          subject=identity.sub, provider=provider,
                                          created_at=now, updated_at=now))
        assert_user_created_with_identity(identity_row_written=True,
                                          user_transaction=self.session,
                                          identity_transaction=self.session)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id) -> User | None:
        result = await self.session.exec(
            select(User).where(User.id == user_id)
        )
        return result.first()


# The user's persisted purchase-attribution tokens, one row per store provider. `GET /users/me`
# reads them and creates nothing: the rows are minted once, in the create-user transaction.
SELECT_STORE_PURCHASE_TOKENS = text("""
    SELECT provider, identity_value
      FROM core.store_purchase_tokens
     WHERE user_id = :user_id
""")


class StorePurchaseTokensDB:
    """The `core.store_purchase_tokens` read behind `GET /users/me`."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def tokens_for(self, user_id: UUID) -> dict[StoreProvider, str]:
        """The user's stored attribution token per store provider. A store with no row is simply
        absent here; whether that is an invariant failure is the endpoint's decision, not this
        read's."""
        # [impl->req~sessions-users-me-step-02~1]
        result = await self.session.execute(SELECT_STORE_PURCHASE_TOKENS, {"user_id": user_id})
        return {StoreProvider(row.provider): row.identity_value for row in result.all()}
