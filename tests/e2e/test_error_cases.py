"""The chat routes' error contract, asserted for an admitted caller and for an unadmitted one."""
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
                                                         linked_firebase_identity, quota_grant):
        """POST /chats/{id} for a nonexistent chat returns 404; quota_grant keeps it about the missing chat."""
        response = await async_client.post(f"/chats/{uuid4()}",
                                           json={"message": "hello"})
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_unsupported_language_returns_400(self, async_client, linked_firebase_identity,
                                                    quota_grant):
        """POST /chats with lang=xx returns 400; quota_grant keeps the case about the language, not the gate."""
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
        """The shared body shape holds on a handler-raised class too, not only a refusal."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert list(response.json().keys()) == ["code"]


@pytest.mark.asyncio(loop_scope="module")
class TestUnadmittedCallerLearnsNothing:
    """The same requests, unadmitted: every branch carries one indistinguishable answer."""

    async def test_nonexistent_chat_is_indistinguishable_from_an_existing_one(self, async_client):
        """A caller that was not admitted cannot probe which chat ids exist."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_unsupported_language_is_not_disclosed(self, async_client):
        """lang=xx is refused before the handler runs, so there is no language enumeration."""
        response = await async_client.post("/chats",
                                           json={"phrase": "test", "lang": "xx"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_a_malformed_body_is_not_disclosed(self, async_client):
        """A missing required field is refused before validation, so there is no schema enumeration."""
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    async def test_error_body_has_only_code_field(self, async_client):
        """Error responses contain exactly {code: ...} and no extra fields."""
        response = await async_client.get(f"/chats/{uuid4()}")
        body = response.json()
        assert list(body.keys()) == ["code"]


@pytest.mark.asyncio(loop_scope="module")
class TestUnauthenticatedAccess:
    async def test_no_auth_header_returns_401(self, _app_lifespan):
        """A request with no Authorization header returns 401 auth_required."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "auth_required"

    async def test_invalid_bearer_token_returns_401(self, _app_lifespan):
        """An unverifiable Bearer token returns the identical 401, so the two refusal steps stay indistinct."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            client.headers["Authorization"] = "Bearer invalid.token.here"
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "auth_required"
