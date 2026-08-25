"""FOUND-01 / §1.1: what admission accepts and refuses at the wire, over a real ASGI stack.

These cases used to run against `app.dependencies.get_current_user`, which read the credential
through FastAPI's `Header(None)` alias. D-16 deletes that dependency -- the alias returns a single
folded value and cannot see a duplicate `Authorization` field, so it was a second acceptance path
and exactly the desync §1.1 exists to reject. The behaviour they described is still live; it
belongs to `app/dependencies.py::get_request_context` now, so they are retargeted rather than
dropped.

**The route here carries the declaration, and that is now the whole premise.** Under the deleted
registry, `/probe` was deliberately *undeclared* and the barrier fell back to its strictest
disposition -- the belt to the startup assertion's braces, guarding a parallel table that could
drift from the router. 37.1 D-06 deletes the table and the drift with it: a route is authenticated
because its router declares the dependency, and there is nothing else for that declaration to
disagree with. So the fixture declares it the way the real routers do, at both levels, and what
these cases pin is the wire contract itself rather than a fallback that no longer exists.
"""
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import get_linked_identity
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.context import LinkedIdentity
from unit.conftest import make_test_verifier, make_token


class _EmptyResult:
    def first(self):
        return None


class _NoIdentitySession:
    """A session whose single identity query matches no row -- /probe has no seeded pair.

    A stand-in for the one short session the dependency opens, not for the database: what these
    cases assert is which *step* refused the request, and every case below is refused at or before
    the admission matrix.
    """

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
    async def _probe(identity: LinkedIdentity = Depends(get_linked_identity)):
        return {"reached": True}

    app.include_router(router)
    # Read per request by the dependency, exactly as the real lifespan supplies them.
    app.state.jwt_verifier = make_test_verifier()
    app.state.session_factory = _NoIdentitySession

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_the_probe_route_declares_the_dependency(probe_client):
    """Guards this module's premise: /probe is authenticated, and structurally so.

    Asserted at both levels. The router-level entry is what makes authentication default-on, and
    the endpoint-level one is what a handler reads its identity from; a rewrite that dropped either
    would change what every case below is measuring.
    """
    from fastapi.routing import APIRoute

    app = probe_client.app
    route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/probe")
    declared = [d.call for d in route.dependant.dependencies]
    assert declared.count(get_linked_identity) == 2, declared


class TestBearerTokenEdgeCases:
    """§1.1: a credential that is not exactly one well-formed Bearer field is refused."""

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
        """Two credentials folded into one field is the §1.1 duplicate case, not a first-wins pick."""
        token = make_token()
        response = probe_client.get(
            "/probe",
            headers={"Authorization": f"Bearer {token}, Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"


class TestWellFormedCredentialPassesTheWireContract:
    """The positive control: the 401s above are the wire contract, not a blanket deny.

    Verification and resolution live on this seam, so a well-formed credential does not reach the
    handler -- `/probe` has no `core.external_identities` row, and `get_linked_identity` refuses an
    unlinked caller. The control still does its job, and does it better: the answer *changes class*
    when the wire contract passes, which is the proof that the 401s above are §1.1 refusals rather
    than a blanket deny. A 200 here would prove less, because it could equally come from a seam
    that skipped steps 3 to 5.
    """

    def test_one_well_formed_bearer_advances_past_the_wire_contract(self, probe_client):
        """It clears §1.1 and §1.2 and is refused by the admission matrix, not by the wire."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": f"Bearer {make_token()}"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    def test_the_scheme_is_matched_case_insensitively(self, probe_client):
        """RFC 7235 makes the auth scheme case-insensitive, and §1.1 follows it.

        The deleted `get_current_user` required a literal 'Bearer ' prefix and refused lowercase.
        That was a stricter-than-the-RFC rule, and losing it is a deliberate behaviour change, not
        a regression: the token bytes after the scheme are still never case-folded or trimmed.
        """
        response = probe_client.get("/probe",
                                 headers={"Authorization": f"bearer {make_token()}"})
        assert response.status_code == 403

    def test_an_unverifiable_token_is_refused_at_step_3(self, probe_client):
        """§1.2: a well-formed but unverifiable credential is the identical 401, never a 403."""
        response = probe_client.get("/probe",
                                 headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
