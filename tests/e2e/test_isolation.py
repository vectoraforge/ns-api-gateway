import pytest

from e2e.conftest import create_chat

pytestmark = pytest.mark.e2e

OTHER_USER = "other-user-not-in-firebase"


@pytest.mark.asyncio(loop_scope="module")
class TestCrossUserIsolation:
    async def test_cannot_read_other_user_chat(self, async_client, _db_transaction):
        chat_id = await create_chat(_db_transaction, OTHER_USER)
        response = await async_client.get(f"/chats/{chat_id}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_cannot_delete_other_user_chat(self, async_client, _db_transaction):
        chat_id = await create_chat(_db_transaction, OTHER_USER)
        response = await async_client.delete(f"/chats/{chat_id}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_cannot_post_to_other_user_chat(self, async_client, _db_transaction):
        chat_id = await create_chat(_db_transaction, OTHER_USER)
        response = await async_client.post(f"/chats/{chat_id}",
                                           json={"content": "Hello"})
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_can_read_own_chat(self, async_client, test_user_id, _db_transaction):
        chat_id = await create_chat(_db_transaction, test_user_id)
        response = await async_client.get(f"/chats/{chat_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_can_delete_own_chat(self, async_client, test_user_id, _db_transaction):
        chat_id = await create_chat(_db_transaction, test_user_id)
        response = await async_client.delete(f"/chats/{chat_id}")
        assert response.status_code == 204
