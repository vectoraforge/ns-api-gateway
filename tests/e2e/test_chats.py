"""The two mutating chat routes, over the real app with a real Firebase credential.

The module carries both halves of the same fact, and each is the other's control:

* `TestCreateChat` / `TestFollowup` — the five served cases plan 35-04 removed, restored. The
  caller is the genuine Firebase credential `async_client` carries, admitted because
  `linked_firebase_identity` seeded its `(issuer, subject)` pair inside the per-test transaction.
  A real token, verified by the production verifier, resolved through a real
  `core.external_identities` row, reaching a handler that reads `identity.user.id` off the
  barrier's context and nothing else.
* `TestUnlinkedCallerIsRefused` — the same client, the same routes, the same credential, with the
  one difference that no identity row exists. §1.3 outcome 1' answers
  `preauth_identity_not_allowed`.

That difference is exactly one seeded row, which is what makes each class load-bearing: the served
cases cannot be passing because the barrier was skipped (the refusals prove it runs on this client),
and the refusals cannot be a blanket deny (the served cases prove the routes serve).

No case here asserts a quota outcome. The chat quota path reads a grant model Phase 36 wires
(D-15), so there is no allowance to enforce and nothing honest to assert about one.
"""
from uuid import UUID, uuid4

import pytest

from nativespeaker.api.models import Chat

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestCreateChat:
    """`POST /chats` served end to end, LLM included."""

    async def test_create_chat_english(self, async_client, linked_firebase_identity):
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

    async def test_create_chat_spanish(self, async_client, linked_firebase_identity):
        response = await async_client.post("/chats",
                                           json={"phrase": "Yo soy va a casa.", "lang": "es"})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"
        assert "content" in data
        assert "response" in data["content"]
        assert data["content"] != {}

    async def test_create_chat_autodetect_lang(self, async_client, linked_firebase_identity):
        """A request omitting `lang` is served -- `ask_llm` sends the autodetect directive.

        **The phrase changed on restoration, and the reason is a live defect, recorded rather than
        worked around silently.** This case used to send `"I am going home."`, which is *correct*
        English. `config/prompt.txt` asks for `issues` and `suggestions` only when issues exist,
        but `AnalyzeResponse` declares both required -- so a correct phrase makes
        `AnalyzeResponse.model_validate` raise and `POST /chats` answers **500**, whatever `lang`
        says. Deferred item D-35-11-A; `models/llm.py` and `config/prompt.txt` are outside this
        phase, and §8.3 requires existing non-auth contracts unchanged.

        The assertions are the original ones, unweakened, and the property under test is unchanged:
        an omitted `lang` is served. Only the input moved to the incorrect phrase the four
        neighbouring cases already use, so the case exercises autodetect rather than the defect.
        No case here asserts the 500 -- pinning a bug as expected behaviour would make it look
        intended and would have to be deleted the moment it is fixed.
        """
        response = await async_client.post("/chats",
                                           json={"phrase": "I am going to home."})
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        assert data["role"] == "ai"

    async def test_create_chat_with_context(self, async_client, linked_firebase_identity):
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
                                                                 _db_transaction):
        """The row lands under the id the barrier resolved, not under anything off the token.

        The four cases above assert the response shape, which a handler ignoring the identity
        context entirely would also produce. This one reads `core.chats.user_id` straight back out
        and requires it to equal the seeded `core.users.id` -- the only assertion in the module that
        a `create_chat` writing some other user's id could fail.
        """
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
    async def test_followup_message(self, async_client, linked_firebase_identity):
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
    """The same credential with no identity row: §1.3 outcome 1', on every mutating chat route.

    Plan 06 sharpened this from `auth_required` to `preauth_identity_not_allowed`, and the change
    is the point. The old 401 was consistent with a barrier that never touched the database; this
    403 is not, because it is reachable only after acceptance succeeded and the identity query ran.
    Chat routes are not pre-auth-callable -- only the two `create-user` phases are -- so an unlinked
    caller can never reach a handler here whatever the token says.
    """

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
        """A malformed body still answers the barrier's rejection, never 422.

        §3.1's anti-oracle rule: the rejection an unadmitted caller sees must not vary with
        anything about the request it could steer. A 422 here would tell an unadmitted caller that
        its credential was fine and only its body was wrong. Its admitted counterpart --
        `test_error_cases.py::TestErrorCases::test_missing_phrase_returns_422` -- is what proves
        this is a suppressed 422 rather than a route that never validates bodies at all.
        """
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}
