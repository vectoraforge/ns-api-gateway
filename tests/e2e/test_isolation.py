import pytest

from tests.e2e.conftest import cleanup_chat, create_chat

pytestmark = pytest.mark.e2e

OTHER_USER = "other-user-not-in-firebase"


class TestCrossUserIsolation:
    @pytest.mark.asyncio
    async def test_cannot_read_other_user_chat(self, real_client, db_session):
        chat_id = await create_chat(db_session, OTHER_USER)
        try:
            response = real_client.get(f"/chats/{chat_id}")
            assert response.status_code == 404
            assert response.json()["code"] == "not_found"
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_cannot_delete_other_user_chat(self, real_client, db_session):
        chat_id = await create_chat(db_session, OTHER_USER)
        try:
            response = real_client.delete(f"/chats/{chat_id}")
            assert response.status_code == 404
            assert response.json()["code"] == "not_found"
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_cannot_post_to_other_user_chat(self, real_client, db_session):
        chat_id = await create_chat(db_session, OTHER_USER)
        try:
            response = real_client.post(f"/chats/{chat_id}",
                                        json={"content": "Hello"})
            assert response.status_code == 404
            assert response.json()["code"] == "not_found"
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_can_read_own_chat(self, real_client, db_session, test_user_id):
        chat_id = await create_chat(db_session, test_user_id)
        try:
            response = real_client.get(f"/chats/{chat_id}")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_can_delete_own_chat(self, real_client, db_session, test_user_id):
        chat_id = await create_chat(db_session, test_user_id)
        response = real_client.delete(f"/chats/{chat_id}")
        assert response.status_code == 204
