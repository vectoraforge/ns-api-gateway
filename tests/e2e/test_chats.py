"""The two mutating chat routes, each asserted for a linked caller and for an unlinked one."""
from uuid import UUID, uuid4

import pytest

from nativespeaker.api.tables import Chat

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestCreateChat:
    """POST /chats served end to end, LLM included."""

    async def test_create_chat_english(self, async_client, linked_firebase_identity,
                                       quota_grant):
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going to home.", "lang": "en"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert "content" in data
        assert isinstance(data["content"], dict)
        assert "response" in data["content"]
        assert data["content"] != {}
        assert "created_at" in data

    async def test_create_chat_spanish(self, async_client, linked_firebase_identity,
                                       quota_grant):
        response = await async_client.post("/chats",
                                           json={"phrase": "Yo soy va a casa.", "lang": "es"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"
        assert "content" in data
        assert "response" in data["content"]
        assert data["content"] != {}

    async def test_create_chat_autodetect_lang(self, async_client, linked_firebase_identity,
                                               quota_grant):
        """An omitted lang is served; the phrase must be incorrect English, as a correct one trips a known 500."""
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going to home."})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"

    async def test_create_chat_with_context(self, async_client, linked_firebase_identity,
                                            quota_grant):
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going to home.",
                                                 "context": "Is this too informal?",
                                                 "lang": "en"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert "content" in data
        assert "response" in data["content"]
        assert data["content"] != {}

    async def test_the_created_chat_belongs_to_the_resolved_user(self, async_client,
                                                                 linked_firebase_identity,
                                                                 quota_grant,
                                                                 _db_transaction):
        """The row lands under the resolved user's id, read straight back out of core.chats."""
        user, _ = linked_firebase_identity
        created = await async_client.post("/chats",
                                          json={"phrase": "I am going to home.", "lang": "en"})
        assert created.status_code == 200
        chat_id = UUID(created.json()["chat_id"])

        async with _db_transaction() as session:
            chat = await session.get(Chat, chat_id)
        assert chat is not None
        assert chat.user_id == user.id


@pytest.mark.asyncio(loop_scope="module")
class TestFollowup:
    async def test_followup_message(self, async_client, linked_firebase_identity, quota_grant):
        # First create a chat to get chat_id
        create_resp = await async_client.post("/chats",
                                              json={"phrase": "I am going to home.", "lang": "en"})
        assert create_resp.status_code == 200
        chat_id = create_resp.json()["chat_id"]

        # Send followup
        followup_resp = await async_client.post(f"/chats/{chat_id}",
                                                json={"message": "Can you explain more?"})
        assert followup_resp.status_code == 200
        data = followup_resp.json()
        assert data["chat_id"] == chat_id
        assert data["role"] == "ai"
        assert "content" in data
        assert "response" in data["content"]
        assert data["content"] != {}
        assert "created_at" in data


@pytest.mark.asyncio(loop_scope="module")
class TestUnlinkedCallerIsRefused:
    """The same credential with no identity row, on every mutating chat route."""

    async def test_create_chat_is_refused(self, async_client):
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going to home.", "lang": "en"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_followup_is_refused(self, async_client):
        response = await async_client.post(f"/chats/{uuid4()}",
                                           json={"message": "Can you explain more?"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_the_refusal_precedes_body_validation(self, async_client):
        """A malformed body still answers the refusal, never 422, so an unadmitted caller learns nothing."""
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}
