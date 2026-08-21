"""Cross-user isolation on the chat routes, restored against two seeded identities.

Plan 35-04 deleted this module outright: every case seeded rows through `conftest.create_chat`,
which still inserted the v1.6 `User(jwt_sub=...)` shape, and then asserted a served response, and
neither half was available. Both are now, so all five cases are back.

**What changed on restoration, and why it is a strengthening.** The v1.6 form authenticated as the
real Firebase user and let `create_chat` invent an identity for `"other-user-not-in-firebase"`,
so only one side of the boundary ever made a request. Both sides are real callers here:
`stub_verifier` swaps `app.state.jwt_verifier` for the ephemeral-RSA verifier, so tokens for two
distinct subjects are mintable without two Firebase accounts, and both subjects get a seeded,
linked, active identity. That matters because a 404 has two possible causes -- the row belongs to
someone else, or the row does not exist -- and only the owner's own 200 against the same id
separates them. Every negative case here carries that positive control inline; without it the whole
module would pass unchanged against a service that had lost the chat rows entirely.

Isolation is enforced by the handler, not the barrier: all three refusals here are `not_found` from
`InvalidChatError`, raised because `ChatsDB` filters on the `user_id` the barrier resolved. A 403
would mean admission failed and the case never reached the property it names.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unit.conftest import TEST_ISSUER, make_token

from .conftest import create_chat, seed_identity

pytestmark = pytest.mark.e2e

OWNER = "isolation-owner"
STRANGER = "isolation-stranger"


@pytest_asyncio.fixture(loop_scope="module")
async def isolation_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts.

    Mirrors `test_barrier_admission.py::barrier_client`. The credential is per-request here rather
    than set on the client, because both subjects drive the same client.
    """
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(loop_scope="module")
async def owned_chat(_db_transaction):
    """Two linked, active identities and one chat owned by `OWNER`. Returns its chat id.

    `seed_identity` runs before `create_chat` for the owner's pair, so the chat attaches to the
    identity the barrier will resolve rather than to a second `anonymous` one `create_chat` would
    otherwise seed itself.
    """
    await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=OWNER)
    await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=STRANGER)
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
        # A refused delete must also be a delete that did not happen. Without this, a handler that
        # deleted the row and *then* reported 404 would pass the two assertions above.
        still_there = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert still_there.status_code == 200

    async def test_cannot_post_to_other_user_chat(self, isolation_client, owned_chat):
        owner_sees_it = await isolation_client.get(f"/chats/{owned_chat}", headers=_auth(OWNER))
        assert owner_sees_it.status_code == 200, "control: the chat must exist and be readable"

        response = await isolation_client.post(f"/chats/{owned_chat}",
                                               json={"message": "Hello"},
                                               headers=_auth(STRANGER))

        # 404 rather than 422 or 403: the body is well-formed and the caller is admitted, so the
        # only thing left to refuse the request is ownership. `send_message` raises before it
        # reaches the model, so no LLM call is spent proving a stranger cannot write here.
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
        """The three 404s above are the handler's, never the barrier's.

        If `STRANGER` were unseeded, every negative case would still show a non-200 -- a 403 -- and
        would still be read as "isolation holds" by anyone checking only that access failed. This
        pins that the stranger passes admission and is stopped by ownership alone.
        """
        response = await isolation_client.get("/chats", headers=_auth(STRANGER))
        assert response.status_code == 200
        assert response.json() == []
