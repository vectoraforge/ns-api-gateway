"""Purchase-attribution reads over `core.store_purchase_tokens`. Takes no lock and mints nothing."""
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.errors import MissingPurchaseTokenError
from nativespeaker.api.tables import PurchaseProvider, StorePurchaseToken


class PurchasesDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def read_tokens(self, user_id: UUID) -> dict[PurchaseProvider, str]:
        """Return `user_id`'s token per store, taking no lock, or raise if any store is unrepresented."""
        statement = (select(StorePurchaseToken.provider, StorePurchaseToken.identity_value)
                     .where(col(StorePurchaseToken.user_id) == user_id))
        rows = (await self.session.exec(statement)).all()
        # The key is named as the enum the column stores: a two-column select over a `StrEnum`
        # column types its first element as a plain string, and the mapping this returns is keyed
        # by members. Idempotent on a member, so the row's own value is what every key is.
        tokens = {PurchaseProvider(provider): value for provider, value in rows}

        missing = set(PurchaseProvider) - set(tokens)
        if missing:
            # Completeness, never emptiness: one row present and one absent is the same broken invariant.
            raise MissingPurchaseTokenError(user_id, sorted(missing))
        return tokens

    async def resolve_user(self, provider: PurchaseProvider, identity_value: str) -> UUID | None:
        """Return the user bound to one store's attribution token, taking no lock, or `None`."""
        statement = (select(StorePurchaseToken.user_id)
                     .where(col(StorePurchaseToken.provider) == provider,
                            col(StorePurchaseToken.identity_value) == identity_value))
        # Unlike `read_tokens` above, an absent binding is an ordinary outcome and never a raise.
        return (await self.session.exec(statement)).first()
