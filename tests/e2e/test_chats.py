"""The two mutating chat routes, over the real app with a real Firebase credential.

Every served-chat case this module carried was removed by plan 35-04 and is named in
35-04-SUMMARY.md for plan 11 to restore. They cannot run today: the e2e Firebase subject has no
`core.external_identities` row, so nothing attaches a §1.4 identity context and
`get_linked_identity` raises before a handler is entered. Plan 06 adds the `seed_identity` and
`stub_verifier` harness that makes a served response possible again.

What survives is the inverse, and it is not a placeholder. A caller presenting a genuinely-issued,
well-formed credential -- one that passes the §1.1 wire contract the barrier enforces -- is still
refused by a chat route, with the shared error body. That is §1.4's fail-loudly rule proven end to
end over the real transport (T-35-04-03): the chat routes cannot serve a request the barrier did
not admit, and they fail closed rather than reading an absent identity as anonymous.
"""
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestUnadmittedCallerIsRefused:
    async def test_create_chat_is_refused(self, async_client):
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going to home.", "lang": "en"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_followup_is_refused(self, async_client):
        response = await async_client.post(f"/chats/{uuid4()}",
                                           json={"message": "Can you explain more?"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_the_refusal_precedes_body_validation(self, async_client):
        """A malformed body still answers auth_required, never 422.

        §3.1's anti-oracle rule: the rejection an unadmitted caller sees must not vary with
        anything about the request it could steer. A 422 here would tell an unadmitted caller that
        its credential was fine and only its body was wrong.
        """
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
