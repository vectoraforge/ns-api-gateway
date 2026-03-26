import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestChatLifecycle:
    async def test_full_chat_lifecycle(self, async_client):
        """Full lifecycle: create -> followup -> read messages -> list chats -> delete."""
        # Step 1: Create a new chat via LLM
        create_resp = await async_client.post("/chats",
                                              json={"phrase": "I am going to home.", "lang": "en"})
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        chat_id = create_data["chat_id"]
        assert create_data["role"] == "ai"
        assert "content" in create_data

        # Step 2: Send a followup message via LLM
        followup_resp = await async_client.post(f"/chats/{chat_id}",
                                                json={"message": "Why is that incorrect?"})
        assert followup_resp.status_code == 200
        followup_data = followup_resp.json()
        assert followup_data["chat_id"] == chat_id
        assert followup_data["role"] == "ai"

        # Step 3: Get chat messages (should have 4: human, AI, human, AI)
        messages_resp = await async_client.get(f"/chats/{chat_id}")
        assert messages_resp.status_code == 200
        messages = messages_resp.json()
        assert isinstance(messages, list)
        assert len(messages) >= 4
        roles = [m["role"] for m in messages]
        assert "human" in roles
        assert "ai" in roles

        # Step 4: Verify chat appears in list
        list_resp = await async_client.get("/chats")
        assert list_resp.status_code == 200
        chat_ids = [c["chat_id"] for c in list_resp.json()]
        assert chat_id in chat_ids

        # Step 5: Delete the chat
        delete_resp = await async_client.delete(f"/chats/{chat_id}")
        assert delete_resp.status_code == 204

        # Step 6: Verify chat is gone
        verify_resp = await async_client.get(f"/chats/{chat_id}")
        assert verify_resp.status_code == 404
