"""End-to-end proof of the Phase 35 slice against the real application at real startup.

The lifespan runs the §2.3 enumeration assertion for real, and an unauthenticated request to an
authenticated route is rejected by the barrier with a response the shared error registry produced.

This module deliberately does not use the `async_client` fixture: that fixture carries a real
Firebase bearer token, and every assertion here is about the *absence* of an Authorization header.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from nativespeaker.api.auth.registry import assert_route_enumeration

pytestmark = pytest.mark.e2e

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


@pytest.fixture
def unauthenticated_client(_app_lifespan):
    """A client over the real, started app that sends no Authorization header."""
    transport = ASGITransport(app=_app_lifespan)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio(loop_scope="module")
class TestStartupAssertion:
    async def test_lifespan_completed(self, _app_lifespan):
        """The fixture yielded, so assert_route_enumeration ran inside the lifespan and passed."""
        assert _app_lifespan.state.config is not None
        assert _app_lifespan.state.session_factory is not None

    async def test_assertion_passes_against_the_live_app(self, _app_lifespan):
        """Calling the assertion directly against the started app raises nothing."""
        assert_route_enumeration(_app_lifespan)

    async def test_unauthenticated_root_is_rejected_by_the_barrier(self, unauthenticated_client):
        """GET / with no Authorization header returns the registry's auth_required response."""
        async with unauthenticated_client as client:
            response = await client.get("/")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_readiness_probe_is_reachable_unauthenticated(self, unauthenticated_client):
        """GET /health/ready is the whole §2.1 public allowlist and needs no token."""
        async with unauthenticated_client as client:
            response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "up"}

    @pytest.mark.parametrize("path", _DOC_PATHS)
    async def test_documentation_routes_are_not_registered(self, unauthenticated_client, path):
        """D-04 removes all four documentation routes, so none is reachable or enumerable."""
        async with unauthenticated_client as client:
            response = await client.get(path)
        assert response.status_code == 404

    async def test_trailing_slash_does_not_redirect(self, unauthenticated_client):
        """redirect_slashes=False: GET /chats/ is a 404, never an unauthenticated 307."""
        async with unauthenticated_client as client:
            response = await client.get("/chats/")
        assert response.status_code == 404
