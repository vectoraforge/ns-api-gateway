import pytest

from tests.e2e.conftest import cleanup_chat, create_chat

pytestmark = pytest.mark.e2e


class TestListChats:
    @pytest.mark.asyncio
    async def test_list_chats(self, real_client, db_session, test_user_id):
        chat_id = await create_chat(db_session, test_user_id)
        try:
            response = real_client.get("/chats")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1
            chat = data[0]
            assert "chat_id" in chat
            assert "title" in chat
            assert "created_at" in chat
        finally:
            await cleanup_chat(db_session, chat_id)


class TestGetChatMessages:
    @pytest.mark.asyncio
    async def test_get_messages(self, real_client, db_session, test_user_id):
        chat_id = await create_chat(db_session, test_user_id)
        try:
            response = real_client.get(f"/chats/{chat_id}")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 2  # human + AI message
            msg = data[0]
            assert "chat_id" in msg
            assert "role" in msg
            assert "content" in msg
            assert "created_at" in msg
        finally:
            await cleanup_chat(db_session, chat_id)


class TestDeleteChat:
    @pytest.mark.asyncio
    async def test_delete_chat(self, real_client, db_session, test_user_id):
        chat_id = await create_chat(db_session, test_user_id)
        response = real_client.delete(f"/chats/{chat_id}")
        assert response.status_code == 204
