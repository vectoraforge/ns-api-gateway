import pytest

from e2e.conftest import create_chat

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestListChats:
    async def test_list_chats(self, async_client, test_user_id, _db_transaction):
        chat_id = await create_chat(_db_transaction, test_user_id)
        response = await async_client.get("/chats")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        chat = data[0]
        assert "chat_id" in chat
        assert "title" in chat
        assert "created_at" in chat


@pytest.mark.asyncio(loop_scope="module")
class TestGetChatMessages:
    async def test_get_messages(self, async_client, test_user_id, _db_transaction):
        chat_id = await create_chat(_db_transaction, test_user_id)
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


@pytest.mark.asyncio(loop_scope="module")
class TestDeleteChat:
    async def test_delete_chat(self, async_client, test_user_id, _db_transaction):
        chat_id = await create_chat(_db_transaction, test_user_id)
        response = await async_client.delete(f"/chats/{chat_id}")
        assert response.status_code == 204
