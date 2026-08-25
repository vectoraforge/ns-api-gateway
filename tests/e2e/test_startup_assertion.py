"""What the real application answers an unauthenticated caller, at real startup.

Every case here is about the *absence* of an Authorization header: which paths that still reaches,
what each one answers, and that no path answers with a redirect. This module deliberately does not
use the `async_client` fixture, which carries a real Firebase bearer token.

The two cases that used to head this file proved the §2.3 route-enumeration assertion ran during
the lifespan. 37.1 D-06 deleted that assertion along with the registry it checked -- the property
it protected is now asserted over the live router itself, in `tests/unit/test_app_wiring.py`. What
remains here is the observable half, which no unit test can reach: a real request, over a real
ASGI transport, through the real app.
"""
import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.e2e

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


@pytest.fixture
def unauthenticated_client(_app_lifespan):
    """A client over the real, started app that sends no Authorization header."""
    transport = ASGITransport(app=_app_lifespan)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio(loop_scope="module")
class TestUnauthenticatedAccess:
    async def test_unauthenticated_root_is_rejected(self, unauthenticated_client):
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
        """redirect_slashes=False: GET /chats/ is a 404, never an unauthenticated 307.

        The redirect is produced by the router before any route matches, so no route's auth
        dependency has run when it is written -- it would name a real path to a caller who has
        proven nothing.
        """
        async with unauthenticated_client as client:
            response = await client.get("/chats/")
        assert response.status_code == 404
