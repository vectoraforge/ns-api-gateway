"""What admission refuses at the wire; a route is authenticated because its router declares the dependency."""
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import get_linked_identity
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.identity import Identity
from unit.conftest import make_test_verifier, make_token


class _EmptyResult:
    def first(self):
        return None


class _NoIdentitySession:
    """One identity query matching no row: every case here is refused at or before the admission matrix."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def exec(self, _statement):
        return _EmptyResult()


@pytest.fixture(scope="module")
def probe_client():
    """One route behind the real auth dependency, returning 200 whenever it is reached."""
    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter(dependencies=[Depends(get_linked_identity)])

    @router.get("/probe")
    async def _probe(identity: Identity = Depends(get_linked_identity)):
        return {"reached": True}

    app.include_router(router)
    # Read per request by the dependency, exactly as the real lifespan supplies them.
    app.state.jwt_verifier = make_test_verifier()
    app.state.session_factory = _NoIdentitySession

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_the_probe_route_declares_the_dependency(probe_client):
    """The premise: /probe is authenticated structurally, declared at router level and again on the endpoint."""
    from fastapi.routing import APIRoute

    app = probe_client.app
    route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/probe")
    declared = [d.call for d in route.dependant.dependencies]
    assert declared.count(get_linked_identity) == 2, declared


class TestBearerTokenEdgeCases:
    """A credential that is not exactly one well-formed Bearer field is refused."""

    def test_missing_authorization_header(self, probe_client):
        """No Authorization field at all returns 401 auth_required."""
        response = probe_client.get("/probe")
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_bearer_with_only_whitespace(self, probe_client):
        """Header 'Bearer    ' (only spaces) carries no token and is refused."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": "Bearer    "})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_non_bearer_auth_scheme(self, probe_client):
        """Basic auth scheme is rejected -- only Bearer accepted."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_bearer_prefix_no_space(self, probe_client):
        """'Bearertoken123' without space after Bearer is rejected."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": "Bearertoken123"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_empty_authorization_header(self, probe_client):
        """Empty Authorization header returns 401."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": ""})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    def test_comma_joined_authorization_is_rejected(self, probe_client):
        """Two credentials folded into one field is the duplicate case, not a first-wins pick."""
        token = make_token()
        response = probe_client.get(
            "/probe",
            headers={"Authorization": f"Bearer {token}, Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"


class TestWellFormedCredentialPassesTheWireContract:
    """The positive control: the answer changes class when the wire contract passes, so the 401s are refusals."""

    def test_one_well_formed_bearer_advances_past_the_wire_contract(self, probe_client):
        """It clears the wire contract and verification, and is refused by the admission matrix instead."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": f"Bearer {make_token()}"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    def test_the_scheme_is_matched_case_insensitively(self, probe_client):
        """RFC 7235 makes the scheme case-insensitive; the token bytes after it are still never folded."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": f"bearer {make_token()}"})
        assert response.status_code == 403

    def test_an_unverifiable_token_is_refused_at_step_3(self, probe_client):
        """A well-formed but unverifiable credential is the identical 401, never a 403."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
