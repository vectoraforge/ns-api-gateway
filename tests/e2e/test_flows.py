"""The six-step chat lifecycle end to end, over the real app with a real Firebase credential.

Plan 35-04 deleted this module: its one case is six served steps, and none of them was reachable
once the barrier resolved identity against a subject with no `core.external_identities` row.
35-04-SUMMARY.md names it in the table of cases for plan 11 to restore, so it is restored here
under its own name rather than folded into another module.

`linked_firebase_identity` seeds the pair inside the per-test transaction, which is the whole
difference between this and the twelve refusal cases in `test_chats.py` and `test_chat_queries.py`.
Nothing else about the request path changes: the same real token, the same production verifier, the
same single identity query, the same handlers.

This is the only case that drives all five chat routes in sequence against one chat, so it is the
one that would notice a route serving correctly in isolation but leaving state a later route
cannot read -- a create whose row never commits, a followup that writes under a fresh chat id, a
delete that reports 204 without matching.
"""
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestChatLifecycle:
    async def test_full_chat_lifecycle(self, async_client, linked_firebase_identity):
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
