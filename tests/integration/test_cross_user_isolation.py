import pytest

from tests.integration.conftest import cleanup_chat, create_chat

# DI override in integration_client always returns "test-user" as user_id.
# Positive tests create chats for TEST_OWNER (matching DI override).
# Negative tests create chats for OTHER_USER (different from DI override).
TEST_OWNER = "test-user"
OTHER_USER = "other-user"


@pytest.mark.db
class TestCrossUserIsolation:
    @pytest.mark.asyncio
    async def test_cannot_read_other_user_chat(self, integration_client, db_session):
        """Negative: request user (test-user via DI) cannot read other-user's chat."""
        chat_id = await create_chat(db_session, OTHER_USER)
        try:
            response = integration_client.get(
                f"/chats/{chat_id}/messages",
            )
            assert response.status_code == 404
            body = response.json()
            assert body["code"] == "not_found"
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_cannot_delete_other_user_chat(self, integration_client, db_session):
        """Negative: request user (test-user via DI) cannot delete other-user's chat."""
        chat_id = await create_chat(db_session, OTHER_USER)
        try:
            response = integration_client.delete(
                f"/chats/{chat_id}",
            )
            assert response.status_code == 404
            body = response.json()
            assert body["code"] == "not_found"
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_cannot_post_to_other_user_chat(self, integration_client, db_session):
        """Negative: request user (test-user via DI) cannot post to other-user's chat."""
        chat_id = await create_chat(db_session, OTHER_USER)
        try:
            response = integration_client.post(
                "/chats",
                json={"text": "Hello", "chat_id": str(chat_id)},
            )
            assert response.status_code == 404
            body = response.json()
            assert body["code"] == "not_found"
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_can_read_own_chat(self, integration_client, db_session):
        """Positive: request user (test-user via DI) can read their own chat."""
        chat_id = await create_chat(db_session, TEST_OWNER)
        try:
            response = integration_client.get(
                f"/chats/{chat_id}/messages",
            )
            assert response.status_code == 200
            assert len(response.json()["messages"]) > 0
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_can_delete_own_chat(self, integration_client, db_session):
        """Positive: request user (test-user via DI) can delete their own chat."""
        chat_id = await create_chat(db_session, TEST_OWNER)
        # No cleanup needed -- delete succeeds
        response = integration_client.delete(
            f"/chats/{chat_id}",
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_malformed_cursor_returns_400(self, integration_client, db_session):
        """CURS-01 integration: malformed cursor returns 400 before decode attempt."""
        chat_id = await create_chat(db_session, TEST_OWNER)
        try:
            response = integration_client.get(
                f"/chats/{chat_id}/messages?cursor=not-valid-cursor!!!",
            )
            assert response.status_code == 400
            body = response.json()
            assert body["code"] == "invalid_request"
        finally:
            await cleanup_chat(db_session, chat_id)
