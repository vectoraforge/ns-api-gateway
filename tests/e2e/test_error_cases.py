"""The shared error body, over the real app.

The six `TestErrorCases` cases asserted the handler-level statuses a *served* chat request
produces -- 404 for a nonexistent chat, 400 for an unsupported language, 422 for a missing field.
None of those branches is reachable in Phase 35: nothing attaches a §1.4 identity context yet, so
every chat route answers `auth_required` before a handler runs. Rather than assert a status the
code cannot produce, they are retargeted onto what that state actually guarantees, which is the
stronger property anyway -- §3.1's anti-oracle rule. Their served-response forms are named in
35-04-SUMMARY.md for plan 11 to restore.
"""
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestUnadmittedCallerLearnsNothing:
    """Every branch that used to carry its own status now carries one indistinguishable answer."""

    async def test_nonexistent_chat_is_indistinguishable_from_an_existing_one(self, async_client):
        """A caller the barrier did not admit cannot probe which chat ids exist."""
        response = await async_client.get(f"/chats/{uuid4()}")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_unsupported_language_is_not_disclosed(self, async_client):
        """`lang=xx` answers auth_required, not the handler's 400 -- no language enumeration."""
        response = await async_client.post("/chats",
                                           json={"phrase": "test", "lang": "xx"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_a_malformed_body_is_not_disclosed(self, async_client):
        """A missing required field answers auth_required, not 422 -- no schema enumeration."""
        response = await async_client.post("/chats", json={"lang": "en"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

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

        The barrier does not verify the token until plan 06, so today this and the case above are
        refused at different steps -- the wire contract and the absent identity context. They are
        required to be indistinguishable to a client, and asserting that now is what keeps plan
        06's move of the rejection point from silently changing the client contract.
        """
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=_app_lifespan)
        async with AsyncClient(transport=transport,
                               base_url="http://test") as client:
            client.headers["Authorization"] = "Bearer invalid.token.here"
            response = await client.get("/chats")
            assert response.status_code == 401
            assert response.json()["code"] == "auth_required"
