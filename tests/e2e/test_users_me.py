"""What `/users/me` answers over the real stack: the caller's profile, its provider, and both store tokens."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from unit.conftest import make_token

from nativespeaker.api.errors import PreAuthIdentityNotAllowed
from nativespeaker.api.tables import IdentityProvider, PurchaseProvider

from .conftest import seed_identity, seed_purchase_tokens
from .test_sync import _stored_provider

pytestmark = pytest.mark.e2e

# Never seeded anywhere, so a token naming it verifies and still resolves to no identity row.
_UNLINKED_SUBJECT = "users-me-unlinked-subject"

# The stored column read back by name, rather than through the ORM mapping the route itself reads through.
_TOKEN_VALUES = text("SELECT provider, identity_value FROM core.store_purchase_tokens"
                     " WHERE user_id = :user_id")


async def _stored_tokens(factory, user_id) -> dict[str, str]:
    """The token values actually on the rows, read back rather than taken from the seed's arguments."""
    async with factory() as session:
        rows = (await session.execute(_TOKEN_VALUES, {"user_id": user_id})).all()
        return {provider: value for provider, value in rows}


# `SELECT *`, not the mapped columns: a change to a column the ORM leaves unmapped would go unseen.
_TOKEN_ROWS = text("SELECT * FROM core.store_purchase_tokens WHERE user_id = :user_id ORDER BY provider")
_USER_ROW = text("SELECT * FROM core.users WHERE id = :user_id")
_IDENTITY_ROWS = text("SELECT * FROM core.external_identities WHERE user_id = :user_id ORDER BY id")
# The whole-table counts, so an insert against some other user is visible too.
_TABLE_COUNTS = text("SELECT (SELECT count(*) FROM core.store_purchase_tokens),"
                     " (SELECT count(*) FROM core.external_identities),"
                     " (SELECT count(*) FROM core.users)")


async def _account_snapshot(factory, user_id) -> dict:
    """Every column of the caller's token, user and identity rows, plus the three whole-table counts."""
    async with factory() as session:
        params = {"user_id": user_id}
        return {"tokens": [tuple(r) for r in (await session.execute(_TOKEN_ROWS, params)).all()],
                "user": [tuple(r) for r in (await session.execute(_USER_ROW, params)).all()],
                "identities": [tuple(r) for r in (await session.execute(_IDENTITY_ROWS, params)).all()],
                "counts": tuple((await session.execute(_TABLE_COUNTS)).one())}


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


@pytest.mark.asyncio(loop_scope="module")
class TestTheFailClosedFiveHundred:
    """An incomplete token set is an opaque 500, whether no row is stored or only one of the two is."""

    async def test_a_caller_with_no_token_rows_is_an_opaque_500(
            self, async_client, linked_firebase_identity):
        # seed_identity mints no token rows, so the linked fixture on its own is already the broken account.
        _ = linked_firebase_identity

        response = await async_client.get("/users/me")

        assert response.status_code == 500
        # The whole body as a literal: an added detail field would name which condition tripped.
        assert response.json() == {"code": "internal_error"}

    async def test_a_caller_holding_one_of_the_two_rows_is_the_same_500(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        # The partial account: the case an emptiness check passes and the completeness rule refuses.
        await seed_purchase_tokens(_db_transaction, user_id=user.id,
                                   providers=[PurchaseProvider.apple])

        response = await async_client.get("/users/me")

        assert response.status_code == 500
        assert response.json() == {"code": "internal_error"}


@pytest.mark.asyncio(loop_scope="module")
class TestTheRouteInheritsTheBarriersRejections:
    """Both rejections come from the existing dependencies; the route adds no handling and no exemption."""

    async def test_a_caller_with_no_credential_is_rejected(self, _app_lifespan):
        # Never async_client here: it carries an Authorization header, which would make this a silent pass.
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/users/me")

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_a_verified_but_unlinked_caller_is_rejected(self, _app_lifespan, stub_verifier):
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/users/me", headers={"Authorization": f"Bearer {make_token(sub=_UNLINKED_SUBJECT)}"})

        # Status and code read off the error class rather than guessed, so a renamed code fails here first.
        assert response.status_code == PreAuthIdentityNotAllowed.status
        assert response.json() == {"code": PreAuthIdentityNotAllowed.code}


@pytest.mark.asyncio(loop_scope="module")
class TestTheRequestChangesNothing:
    """PROF-02: the caller's rows and the three table counts are identical before and after a read."""

    async def test_a_successful_read_leaves_every_row_untouched(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_purchase_tokens(_db_transaction, user_id=user.id)
        before = await _account_snapshot(_db_transaction, user.id)

        response = await async_client.get("/users/me")

        assert response.status_code == 200, response.text
        # Table state, never the absence of a COMMIT: get_db commits every request, and a read's commit writes nothing.
        assert await _account_snapshot(_db_transaction, user.id) == before

    async def test_a_repeated_request_answers_the_same_bytes_over_the_same_rows(
            self, async_client, _db_transaction, linked_firebase_identity):
        user, _ = linked_firebase_identity
        await seed_purchase_tokens(_db_transaction, user_id=user.id)
        before = await _account_snapshot(_db_transaction, user.id)

        # What a client reconciling after a lost response actually does, twice over the same rows.
        first = await async_client.get("/users/me")
        second = await async_client.get("/users/me")

        assert (first.status_code, second.status_code) == (200, 200), second.text
        assert first.content == second.content
        assert await _account_snapshot(_db_transaction, user.id) == before
