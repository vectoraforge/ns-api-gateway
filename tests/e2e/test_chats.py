import pytest

pytestmark = pytest.mark.e2e


class TestCreateChat:
    def test_create_chat_english(self, real_client):
        response = real_client.post("/chats",
                                     json={"phrase": "I am going to home.", "lang": "en"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"
        assert "content" in data
        assert "created_at" in data

    def test_create_chat_spanish(self, real_client):
        response = real_client.post("/chats",
                                     json={"phrase": "Yo soy va a casa.", "lang": "es"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"
        assert "content" in data

    def test_create_chat_autodetect_lang(self, real_client):
        response = real_client.post("/chats",
                                     json={"phrase": "I am going home."})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"

    def test_create_chat_with_comment(self, real_client):
        response = real_client.post("/chats",
                                     json={"phrase": "I am going to home.",
                                            "comment": "Is this too informal?",
                                            "lang": "en"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert "content" in data


class TestFollowup:
    def test_followup_message(self, real_client):
        # First create a chat to get chat_id
        create_resp = real_client.post("/chats",
                                       json={"phrase": "I am going to home.", "lang": "en"})
        assert create_resp.status_code == 200
        chat_id = create_resp.json()["chat_id"]

        # Send followup
        followup_resp = real_client.post(f"/chats/{chat_id}",
                                          json={"content": "Can you explain more?"})
        assert followup_resp.status_code == 200
        data = followup_resp.json()
        assert data["chat_id"] == chat_id
        assert data["role"] == "ai"
        assert "content" in data
        assert "created_at" in data
