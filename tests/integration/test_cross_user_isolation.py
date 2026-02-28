import pytest

from tests.integration.conftest import _make_token, cleanup_chat, create_chat

USER_A = "user-a"
USER_B = "user-b"


def auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


@pytest.mark.db
class TestCrossUserIsolation:
    @pytest.mark.asyncio
    async def test_user_a_cannot_read_user_b_chat(self, integration_client, db_session):
        chat_id = await create_chat(db_session, USER_B)
        try:
            response = integration_client.get(
                f"/chats/{chat_id}/messages",
                headers=auth(USER_A),
            )
            assert response.status_code == 404
            body = response.json()
            assert body["status"] == 404
            # Ownership-opaque: same message as not-found
            assert "not found" in body["error"].lower()
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_user_a_cannot_delete_user_b_chat(self, integration_client, db_session):
        chat_id = await create_chat(db_session, USER_B)
        try:
            response = integration_client.delete(
                f"/chats/{chat_id}",
                headers=auth(USER_A),
            )
            assert response.status_code == 404
            body = response.json()
            assert body["status"] == 404
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_user_a_cannot_post_to_user_b_chat(self, integration_client, db_session):
        chat_id = await create_chat(db_session, USER_B)
        try:
            response = integration_client.post(
                f"/chats/{chat_id}/messages",
                json={"text": "Hello"},
                headers=auth(USER_A),
            )
            assert response.status_code == 404
            body = response.json()
            assert body["status"] == 404
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_user_a_can_read_own_chat(self, integration_client, db_session):
        """Positive case: user can access their own chat."""
        chat_id = await create_chat(db_session, USER_A)
        try:
            response = integration_client.get(
                f"/chats/{chat_id}/messages",
                headers=auth(USER_A),
            )
            assert response.status_code == 200
            assert response.json()["messages"] == []
        finally:
            await cleanup_chat(db_session, chat_id)

    @pytest.mark.asyncio
    async def test_user_a_can_delete_own_chat(self, integration_client, db_session):
        """Positive case: user can delete their own chat."""
        chat_id = await create_chat(db_session, USER_A)
        # No cleanup needed — delete succeeds
        response = integration_client.delete(
            f"/chats/{chat_id}",
            headers=auth(USER_A),
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_malformed_cursor_returns_400(self, integration_client, db_session):
        """CURS-01 integration: malformed cursor returns 400 before decode attempt."""
        chat_id = await create_chat(db_session, USER_A)
        try:
            response = integration_client.get(
                f"/chats/{chat_id}/messages?cursor=not-valid-cursor!!!",
                headers=auth(USER_A),
            )
            assert response.status_code == 400
            body = response.json()
            assert body["status"] == 400
            assert "cursor" in body["error"].lower()
        finally:
            await cleanup_chat(db_session, chat_id)
