"""What the real app answers a caller who sends no Authorization header."""
import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.e2e

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


# Never use async_client here: every assertion below is about the absence of an Authorization header.
@pytest.fixture
def unauthenticated_client(_app_lifespan):
    """A client over the real, started app that sends no Authorization header."""
    transport = ASGITransport(app=_app_lifespan)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio(loop_scope="module")
class TestUnauthenticatedAccess:
    async def test_unauthenticated_root_is_rejected(self, unauthenticated_client):
        """GET / with no Authorization header returns 401 auth_required."""
        async with unauthenticated_client as client:
            response = await client.get("/")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_readiness_probe_is_reachable_unauthenticated(self, unauthenticated_client):
        """GET /health/ready is the only public route and needs no token."""
        async with unauthenticated_client as client:
            response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "up"}

    @pytest.mark.parametrize("path", _DOC_PATHS)
    async def test_documentation_routes_are_not_registered(self, unauthenticated_client, path):
        """The four documentation routes are switched off, so none is reachable or enumerable."""
        async with unauthenticated_client as client:
            response = await client.get(path)
        assert response.status_code == 404

    async def test_trailing_slash_does_not_redirect(self, unauthenticated_client):
        """GET /chats/ is a 404, never a 307: a redirect would name a real path to a caller who has proven nothing."""
        async with unauthenticated_client as client:
            response = await client.get("/chats/")
        assert response.status_code == 404
