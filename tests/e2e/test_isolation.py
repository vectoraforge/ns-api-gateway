"""Cross-user isolation on the chat routes: every refusal carries the owner's own 200 as its control."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unit.conftest import TEST_ISSUER, make_token

from .conftest import create_chat, seed_grant, seed_identity

pytestmark = pytest.mark.e2e

OWNER = "isolation-owner"
STRANGER = "isolation-stranger"


@pytest_asyncio.fixture(loop_scope="module")
async def isolation_client(_app_lifespan, stub_verifier):
    """A client whose tokens the stub verifier accepts; the credential is per request, not on the client."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(loop_scope="module")
async def owned_chat(_db_transaction):
    """Two linked identities, a grant for STRANGER, and one chat owned by OWNER; returns the chat id."""
    await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=OWNER)
    stranger, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=STRANGER)
    # The stranger's grant keeps the POST case about ownership rather than about the quota gate.
    await seed_grant(_db_transaction, user_id=stranger.id)
    return await create_chat(_db_transaction, TEST_ISSUER, OWNER)


def _auth(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


@pytest.mark.asyncio(loop_scope="module")
class TestCrossUserIsolation:

    async def test_cannot_read_other_user_chat(self, isolation_client, owned_chat):
        owner_sees_it = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert owner_sees_it.status_code == 200, "control: the chat must exist and be readable"

        response = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(STRANGER))

        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_cannot_delete_other_user_chat(self, isolation_client, owned_chat):
        owner_sees_it = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert owner_sees_it.status_code == 200, "control: the chat must exist and be readable"

        response = await isolation_client.delete(f"/chats/{owned_chat}", headers=_auth(STRANGER))

        assert response.status_code == 404
        assert response.json()["code"] == "not_found"
        # A refused delete must also be a delete that did not happen.
        still_there = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert still_there.status_code == 200

    async def test_cannot_post_to_other_user_chat(self, isolation_client, owned_chat):
        owner_sees_it = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert owner_sees_it.status_code == 200, "control: the chat must exist and be readable"

        response = await isolation_client.post(f"/chats/{owned_chat}",
                                               json={"message": "Hello"},
                                               headers=_auth(STRANGER))

        # 404 rather than 403: the caller is admitted and the body is well-formed, so only ownership refuses.
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_can_read_own_chat(self, isolation_client, owned_chat):
        response = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert all(m["chat_id"] == str(owned_chat) for m in data)

    async def test_can_delete_own_chat(self, isolation_client, owned_chat):
        response = await isolation_client.delete(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert response.status_code == 204

        gone = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert gone.status_code == 404

    async def test_the_stranger_is_admitted_not_refused(self, isolation_client, owned_chat):
        """The three 404s above come from ownership, not from admission: the stranger is admitted."""
        response = await isolation_client.get("/chats", headers=_auth(STRANGER))
        assert response.status_code == 200
        assert response.json() == []
