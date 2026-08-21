"""The three read/delete chat routes, over the real app with a real Firebase credential.

Both halves live here, and each is the other's control. `TestListChats` / `TestGetChatMessages` /
`TestDeleteChat` are the three cases plan 35-04 removed, restored against seeded rows and a served
response; `TestUnlinkedCallerIsRefused` is the same client on the same routes with no
`core.external_identities` row, answering §1.3 outcome 1'.

The seeded caller is the genuine Firebase credential `async_client` carries.
`linked_firebase_identity` is what makes it resolvable -- it seeds the pair inside the per-test
transaction and hands back the `(user, identity)` it wrote, so `create_chat` can attach rows to the
very identity the barrier will resolve rather than to a second one that happens to share a subject.
Fixture ordering matters and is not incidental: `seed_identity` must run before `create_chat` for a
pair, or `create_chat` seeds its own `anonymous` identity and the unique index rejects the second.

Together with `test_chats.py` this covers all five chat routes: no route is left unasserted in
either direction.
"""
from uuid import uuid4

import pytest

from .conftest import create_chat

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestListChats:
    async def test_list_chats(self, async_client, linked_firebase_identity, _db_transaction):
        """Mine, and only mine.

        A second user's chat is seeded deliberately. Mutation M3 -- `list_chats` dropping its
        `user_id` filter -- passed this case when the transaction held one chat, because
        `== [seeded]` and `== [every row]` are the same list when there is only one row. The
        assertion looked like it pinned ownership and did not. With a stranger's row present it
        does, and M3 fails here.
        """
        _, identity = linked_firebase_identity
        chat_id = await create_chat(_db_transaction, identity.issuer, identity.subject)
        stranger_chat_id = await create_chat(_db_transaction, identity.issuer, "listing-stranger")

        response = await async_client.get("/chats")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        chat = data[0]
        assert "chat_id" in chat
        assert "title" in chat
        assert "created_at" in chat
        returned = [c["chat_id"] for c in data]
        assert returned == [str(chat_id)]
        assert str(stranger_chat_id) not in returned


@pytest.mark.asyncio(loop_scope="module")
class TestGetChatMessages:
    async def test_get_messages(self, async_client, linked_firebase_identity, _db_transaction):
        _, identity = linked_firebase_identity
        chat_id = await create_chat(_db_transaction, identity.issuer, identity.subject)

        response = await async_client.get(f"/chats/{chat_id}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # human + AI message
        msg = data[0]
        assert "chat_id" in msg
        assert "role" in msg
        assert "content" in msg
        assert "created_at" in msg
        assert {m["role"] for m in data} == {"human", "ai"}
        assert all(m["chat_id"] == str(chat_id) for m in data)


@pytest.mark.asyncio(loop_scope="module")
class TestDeleteChat:
    async def test_delete_chat(self, async_client, linked_firebase_identity, _db_transaction):
        _, identity = linked_firebase_identity
        chat_id = await create_chat(_db_transaction, identity.issuer, identity.subject)

        response = await async_client.delete(f"/chats/{chat_id}")

        assert response.status_code == 204
        # 204 already means a row matched -- `delete_chat` raises `InvalidChatError` on a rowcount
        # of zero, so a no-op delete would surface as 404. Reading it back afterwards is what
        # separates "the statement matched" from "the row is gone".
        gone = await async_client.get(f"/chats/{chat_id}")
        assert gone.status_code == 404
        assert gone.json()["code"] == "not_found"


@pytest.mark.asyncio(loop_scope="module")
class TestUnlinkedCallerIsRefused:
    """The same credential with no identity row, on the same three routes.

    Plan 06 sharpened this from `auth_required` to `preauth_identity_not_allowed`: the e2e Firebase
    subject is a *verified* subject with no `core.external_identities` row, which is exactly what
    outcome 1' names. See `test_chats.py`'s module docstring for why the class change is a
    strengthening rather than a regression.
    """

    async def test_list_chats_is_refused(self, async_client):
        response = await async_client.get("/chats")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_get_messages_is_refused(self, async_client):
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_delete_chat_is_refused(self, async_client):
        response = await async_client.delete(f"/chats/{uuid4()}")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}
