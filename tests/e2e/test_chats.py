import pytest


@pytest.mark.asyncio(loop_scope="module")
class TestCreateChat:
    async def test_create_chat_english(self, async_client):
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

    async def test_create_chat_spanish(self, async_client):
        response = await async_client.post("/chats",
                                           json={"phrase": "Yo soy va a casa.", "lang": "es"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"
        assert "content" in data
        assert "response" in data["content"]
        assert data["content"] != {}

    async def test_create_chat_autodetect_lang(self, async_client):
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going home."})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"

    async def test_create_chat_with_comment(self, async_client):
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going to home.",
                                                  "comment": "Is this too informal?",
                                                  "lang": "en"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert "content" in data
        assert "response" in data["content"]
        assert data["content"] != {}


@pytest.mark.asyncio(loop_scope="module")
class TestFollowup:
    async def test_followup_message(self, async_client):
        # First create a chat to get chat_id
        create_resp = await async_client.post("/chats",
                                              json={"phrase": "I am going to home.", "lang": "en"})
        assert create_resp.status_code == 200
        chat_id = create_resp.json()["chat_id"]

        # Send followup
        followup_resp = await async_client.post(f"/chats/{chat_id}",
                                                json={"content": "Can you explain more?"})
        assert followup_resp.status_code == 200
        data = followup_resp.json()
        assert data["chat_id"] == chat_id
        assert data["role"] == "ai"
        assert "content" in data
        assert "response" in data["content"]
        assert data["content"] != {}
        assert "created_at" in data
