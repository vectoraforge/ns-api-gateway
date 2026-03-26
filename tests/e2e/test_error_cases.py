import pytest
from uuid import uuid4

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestErrorCases:
    async def test_get_nonexistent_chat_returns_404(self, async_client):
        """GET /chats/{id} for nonexistent chat returns 404."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_delete_nonexistent_chat_returns_404(self, async_client):
        """DELETE /chats/{id} for nonexistent chat returns 404."""
        response = await async_client.delete(f"/chats/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_followup_nonexistent_chat_returns_404(self, async_client):
        """POST /chats/{id} for nonexistent chat returns 404."""
        response = await async_client.post(f"/chats/{uuid4()}",
                                           json={"message": "hello"})
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_unsupported_language_returns_400(self, async_client):
        """POST /chats with lang=xx returns 400 invalid_request."""
        response = await async_client.post("/chats",
                                           json={"phrase": "test", "lang": "xx"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_request"

    async def test_missing_phrase_returns_422(self, async_client):
        """POST /chats without phrase returns 422 validation_error."""
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_error_body_has_only_code_field(self, async_client):
        """Error responses contain exactly {code: ...} -- no extra fields."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 404
        body = response.json()
        assert list(body.keys()) == ["code"]


@pytest.mark.asyncio(loop_scope="module")
class TestUnauthenticatedAccess:
    async def test_no_auth_header_returns_401(self, _app_lifespan):
        """Request without Authorization header returns 401 unauthorized."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "unauthorized"

    async def test_no_auth_on_users_me_returns_401(self, _app_lifespan):
        """GET /users/me without auth returns 401."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            response = await client.get("/users/me")
            assert response.status_code == 401
            assert response.json()["code"] == "unauthorized"

    async def test_invalid_bearer_token_returns_401(self, _app_lifespan):
        """Request with invalid Bearer token returns 401."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            client.headers["Authorization"] = "Bearer invalid.token.here"
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "unauthorized"
