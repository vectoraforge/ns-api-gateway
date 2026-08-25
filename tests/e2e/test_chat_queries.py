"""The three read/delete chat routes, each asserted for a linked caller and for an unlinked one."""
from uuid import uuid4

import pytest

from .conftest import create_chat

# linked_firebase_identity must be requested before create_chat, or a second anonymous identity is inserted.
pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestListChats:
    async def test_list_chats(self, async_client, linked_firebase_identity, _db_transaction):
        """Mine, and only mine: a stranger's chat is seeded so the assertion pins ownership, not count."""
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
        # Reading it back separates "the statement matched" from "the row is gone".
        gone = await async_client.get(f"/chats/{chat_id}")
        assert gone.status_code == 404
        assert gone.json()["code"] == "not_found"


@pytest.mark.asyncio(loop_scope="module")
class TestUnlinkedCallerIsRefused:
    """The same credential with no identity row, on the same three routes."""

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
