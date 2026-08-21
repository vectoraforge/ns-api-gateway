"""The two mutating chat routes, over the real app with a real Firebase credential.

Every served-chat case this module carried was removed by plan 35-04 and is named in
35-04-SUMMARY.md for plan 11 to restore. What survives is the inverse, and it is not a
placeholder: a caller presenting a genuinely-issued, well-formed credential is still refused by a
chat route, with the shared error body.

**Plan 06 changed which class that refusal carries, and the change is the point.** Until the
barrier resolved identity, these cases collected `auth_required` -- the §1.4 accessors raising on
an absent context. Now the barrier verifies the token, resolves the e2e Firebase subject against
`core.external_identities`, finds no row, and answers §1.3 outcome 1' directly:
`preauth_identity_not_allowed`. That is a stronger claim than the old one. The old 401 was
consistent with a barrier that never looked at the database; this 403 is not, because it is
reachable only after acceptance succeeded and resolution ran.

Chat routes are not pre-auth-callable -- only the two `create-user` phases are -- so an unlinked
caller can never reach a handler here whatever the token says.
"""
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestUnlinkedCallerIsRefused:
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
        its credential was fine and only its body was wrong.
        """
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}
