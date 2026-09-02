"""What `/users/me` answers over the real stack: the caller's profile, its provider, and both store tokens."""
import pytest
from sqlmodel import col, select

from nativespeaker.api.tables import PurchaseProvider, StorePurchaseToken

from .conftest import seed_purchase_tokens

pytestmark = pytest.mark.e2e


async def _stored_tokens(factory, user_id) -> dict[str, str]:
    """The token values actually on the rows, read back rather than taken from the seed's arguments."""
    async with factory() as session:
        statement = (select(StorePurchaseToken.provider, StorePurchaseToken.identity_value)
                     .where(col(StorePurchaseToken.user_id) == user_id))
        return {provider.value: value for provider, value in (await session.exec(statement)).all()}


@pytest.mark.asyncio(loop_scope="module")
class TestTheProfileHappyPath:
    """One linked caller holding a token per store, and the whole body the route answers with."""

    async def test_a_linked_caller_reads_its_profile_and_both_store_tokens(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, identity = linked_firebase_identity
        await seed_purchase_tokens(_db_transaction, user_id=user.id)
        stored = await _stored_tokens(_db_transaction, user.id)

        response = await async_client.get("/users/me")

        assert response.status_code == 200, response.text
        # The whole body, not three known keys: a fourth field would pass the weaker check.
        assert response.json() == {"profile": {"email": user.email,
                                               "display_name": user.display_name},
                                   "identity_provider": identity.provider.value,
                                   "purchase_tokens": stored}

    async def test_the_token_map_carries_one_key_per_store(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_purchase_tokens(_db_transaction, user_id=user.id)

        response = await async_client.get("/users/me")

        assert response.status_code == 200, response.text
        assert set(response.json()["purchase_tokens"]) == {store.value for store in PurchaseProvider}

    async def test_the_body_is_never_stored_by_a_cache(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_purchase_tokens(_db_transaction, user_id=user.id)

        response = await async_client.get("/users/me")

        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
