"""The chat routes' error contract, over the real app, from both sides of the barrier.

The module now carries the pair that makes either half meaningful:

* `TestErrorCases` -- the five per-branch cases plan 35-04 removed, restored. An **admitted**
  caller gets the honest status its request earned: 404 for a chat that is not its own or does not
  exist, 400 for an unsupported language, 422 for a body that fails validation. §8.3's "existing
  non-auth error contracts unchanged" is what these assert, and they are unchanged from v1.6.
* `TestUnadmittedCallerLearnsNothing` -- the identical requests from an **unadmitted** caller, all
  answering one indistinguishable 403. §3.1's anti-oracle rule.

Neither class means much alone. Without the restored half, "every branch answers 403" is equally
consistent with a service that has no branches -- the 422 case in particular would be satisfied by
a route that never validates a body. Without the anti-oracle half, the per-branch statuses say
nothing about what an unadmitted caller can learn. Read together they say the branches exist, are
distinguishable to a caller entitled to distinguish them, and collapse to one answer for a caller
that is not.

`test_no_auth_on_users_me_returns_401` is **not** restored here: `GET /users/me` was deleted with
its router under D-16 and Phase 39 owns the replacement route, its declaration, and this case.
"""
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestErrorCases:
    """An admitted caller, on the branches behind the handler."""

    async def test_get_nonexistent_chat_returns_404(self, async_client, linked_firebase_identity):
        """GET /chats/{id} for nonexistent chat returns 404."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_delete_nonexistent_chat_returns_404(self, async_client,
                                                       linked_firebase_identity):
        """DELETE /chats/{id} for nonexistent chat returns 404."""
        response = await async_client.delete(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_followup_nonexistent_chat_returns_404(self, async_client,
                                                         linked_firebase_identity):
        """POST /chats/{id} for nonexistent chat returns 404."""
        response = await async_client.post(f"/chats/{uuid4()}",
                                           json={"message": "hello"})
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_unsupported_language_returns_400(self, async_client, linked_firebase_identity):
        """POST /chats with lang=xx returns 400 invalid_request."""
        response = await async_client.post("/chats",
                                           json={"phrase": "test", "lang": "xx"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    async def test_missing_phrase_returns_422(self, async_client, linked_firebase_identity):
        """POST /chats without phrase returns 422 validation_error."""
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_the_404_body_has_only_code_field(self, async_client,
                                                    linked_firebase_identity):
        """The shared body shape holds on a handler-raised class too, not only a barrier one."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert list(response.json().keys()) == ["code"]


@pytest.mark.asyncio(loop_scope="module")
class TestUnadmittedCallerLearnsNothing:
    """The same requests, unadmitted: every branch carries one indistinguishable answer.

    Plan 06 moved the refusal from `auth_required` (an absent identity context) to
    `preauth_identity_not_allowed` (§1.3 outcome 1', reached only after the token verified and the
    single identity query ran). The anti-oracle property is unchanged.
    """

    async def test_nonexistent_chat_is_indistinguishable_from_an_existing_one(self, async_client):
        """A caller the barrier did not admit cannot probe which chat ids exist."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_unsupported_language_is_not_disclosed(self, async_client):
        """`lang=xx` is refused by the barrier, not by the handler -- no language enumeration."""
        response = await async_client.post("/chats",
                                           json={"phrase": "test", "lang": "xx"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_a_malformed_body_is_not_disclosed(self, async_client):
        """A missing required field is refused by the barrier, not 422 -- no schema enumeration."""
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_error_body_has_only_code_field(self, async_client):
        """Error responses contain exactly {code: ...} -- no extra fields."""
        response = await async_client.get(f"/chats/{uuid4()}")
        body = response.json()
        assert list(body.keys()) == ["code"]


@pytest.mark.asyncio(loop_scope="module")
class TestUnauthenticatedAccess:
    async def test_no_auth_header_returns_401(self, _app_lifespan):
        """Request without Authorization header returns 401 auth_required.

        The barrier owns this rejection, and D-11 retires the old `unauthorized` code.
        """
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "auth_required"

    async def test_invalid_bearer_token_returns_401(self, _app_lifespan):
        """A syntactically valid but unverifiable Bearer token returns the identical 401.

        The two cases in this class are refused at different steps -- the wire contract at §1.5
        step 2, and RS256 verification at step 3. They are required to be indistinguishable to a
        client, and asserting it here is what would catch a later change that let one of them say
        more than the other.
        """
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            client.headers["Authorization"] = "Bearer invalid.token.here"
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "auth_required"
