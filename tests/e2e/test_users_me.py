"""What `/users/me` answers over the real stack: the caller's profile, its provider, and both store tokens."""
import pytest
import pytest_asyncio
from sqlalchemy import text

from nativespeaker.api.tables import IdentityProvider, PurchaseProvider

from .conftest import seed_identity, seed_purchase_tokens
from .test_sync import _stored_provider

pytestmark = pytest.mark.e2e

# The stored column read back by name, rather than through the ORM mapping the route itself reads through.
_TOKEN_VALUES = text("SELECT provider, identity_value FROM core.store_purchase_tokens"
                     " WHERE user_id = :user_id")


async def _stored_tokens(factory, user_id) -> dict[str, str]:
    """The token values actually on the rows, read back rather than taken from the seed's arguments."""
    async with factory() as session:
        rows = (await session.execute(_TOKEN_VALUES, {"user_id": user_id})).all()
        return {provider: value for provider, value in rows}


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

    async def test_every_token_value_is_the_one_stored_for_that_store(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_purchase_tokens(_db_transaction, user_id=user.id)
        stored = await _stored_tokens(_db_transaction, user.id)

        response = await async_client.get("/users/me")

        assert response.status_code == 200, response.text
        # The mapping as a whole: a handler echoing a constant or the wrong column fails the readback.
        assert response.json()["purchase_tokens"] == stored


@pytest_asyncio.fixture(loop_scope="module")
async def apple_linked_identity(_db_transaction, _app_config, test_user_id):
    """The real credential's identity pair, stored with a provider the happy-path fixture never seeds."""
    return await seed_identity(_db_transaction,
                               issuer=_app_config.jwt.issuer,
                               subject=test_user_id,
                               provider=IdentityProvider.apple)


@pytest.mark.asyncio(loop_scope="module")
class TestTheProviderComesFromTheStoredColumn:
    """`identity_provider` is the value in `core.external_identities.provider`, not a default or a token claim."""

    async def test_a_non_google_caller_reports_its_stored_provider(
            self, async_client, _db_transaction, _app_config, test_user_id, apple_linked_identity):
        user, _ = apple_linked_identity
        await seed_purchase_tokens(_db_transaction, user_id=user.id)
        stored = await _stored_provider(_db_transaction, _app_config.jwt.issuer, test_user_id)
        # The happy-path fixture seeds google; a row equal to it would leave the case proving nothing.
        assert stored != IdentityProvider.google

        response = await async_client.get("/users/me")

        assert response.status_code == 200, response.text
        assert response.json()["identity_provider"] == stored

    async def test_both_routes_report_the_same_provider_for_the_same_caller(
            self, async_client, _db_transaction, _app_config, test_user_id, apple_linked_identity):
        user, _ = apple_linked_identity
        # /users/me is a 500 without a complete token set; /auth/sync answers `none` with no grant seeded.
        await seed_purchase_tokens(_db_transaction, user_id=user.id)
        stored = await _stored_provider(_db_transaction, _app_config.jwt.issuer, test_user_id)
        assert stored != IdentityProvider.google

        me = await async_client.get("/users/me")
        sync = await async_client.post("/auth/sync")

        assert (me.status_code, sync.status_code) == (200, 200), sync.text
        # Both against each other and both against the row: agreeing on a wrong value would pass a weaker check.
        assert me.json()["identity_provider"] == sync.json()["identity_provider"] == stored
