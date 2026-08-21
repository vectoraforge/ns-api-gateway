"""FOUND-01 / §1.1: what the barrier accepts and refuses at the wire, over a real ASGI stack.

These cases used to run against `app.dependencies.get_current_user`, which read the credential
through FastAPI's `Header(None)` alias. D-16 deletes that dependency -- the alias returns a single
folded value and cannot see a duplicate `Authorization` field, so it was a second acceptance path
beside the barrier's and exactly the desync §1.1 exists to reject. The behaviour they described is
still live; it just belongs to `AuthBarrierMiddleware` now, so they are retargeted rather than
dropped.

The route here is deliberately **undeclared** in the registry. `lookup` returns `None`, and the
barrier treats an undeclared route as authenticated -- the strictest disposition -- so this fixture
also pins that a route carrying no declaration can never fall through as public. (In a started
process an undeclared route aborts boot via the §2.3 assertion; this is the belt to that braces.)
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.auth.registry import lookup
from unit.conftest import make_token


@pytest.fixture(scope="module")
def barrier_client():
    """The real barrier in front of one route that returns 200 whenever it is reached."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/probe")
    async def _probe():
        return {"reached": True}

    app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_the_probe_route_is_undeclared(barrier_client):
    """Guards this module's premise: /probe carries no registry declaration."""
    assert lookup("GET", "/probe") is None


class TestBearerTokenEdgeCases:
    """§1.1: a credential that is not exactly one well-formed Bearer field is refused."""

    def test_missing_authorization_header(self, barrier_client):
        """No Authorization field at all returns 401 auth_required."""
        response = barrier_client.get("/probe")
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_bearer_with_only_whitespace(self, barrier_client):
        """Header 'Bearer    ' (only spaces) carries no token and is refused."""
        response = barrier_client.get("/probe",
                                      headers={"Authorization": "Bearer    "})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_non_bearer_auth_scheme(self, barrier_client):
        """Basic auth scheme is rejected -- only Bearer accepted."""
        response = barrier_client.get("/probe",
                                      headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_bearer_prefix_no_space(self, barrier_client):
        """'Bearertoken123' without space after Bearer is rejected."""
        response = barrier_client.get("/probe",
                                      headers={"Authorization": "Bearertoken123"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_empty_authorization_header(self, barrier_client):
        """Empty Authorization header returns 401."""
        response = barrier_client.get("/probe",
                                      headers={"Authorization": ""})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_comma_joined_authorization_is_rejected(self, barrier_client):
        """Two credentials folded into one field is the §1.1 duplicate case, not a first-wins pick."""
        token = make_token()
        response = barrier_client.get(
            "/probe",
            headers={"Authorization": f"Bearer {token}, Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"


class TestWellFormedCredentialPassesThrough:
    """The positive control: the 401s above are the wire contract, not a blanket deny."""

    def test_one_well_formed_bearer_reaches_the_handler(self, barrier_client):
        """The barrier does not verify the token here (plan 06 adds that) -- it checks the wire."""
        response = barrier_client.get("/probe",
                                      headers={"Authorization": f"Bearer {make_token()}"})
        assert response.status_code == 200
        assert response.json() == {"reached": True}

    def test_the_scheme_is_matched_case_insensitively(self, barrier_client):
        """RFC 7235 makes the auth scheme case-insensitive, and §1.1 follows it.

        The deleted `get_current_user` required a literal 'Bearer ' prefix and refused lowercase.
        That was a stricter-than-the-RFC rule, and losing it is a deliberate behaviour change, not
        a regression: the token bytes after the scheme are still never case-folded or trimmed.
        """
        response = barrier_client.get("/probe",
                                      headers={"Authorization": f"bearer {make_token()}"})
        assert response.status_code == 200
