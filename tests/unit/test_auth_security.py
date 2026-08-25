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
from unit.conftest import make_test_verifier, make_token


class _EmptyResult:
    def first(self):
        return None


class _NoIdentitySession:
    """A session whose single identity query matches no row -- /probe has no seeded pair.

    The barrier resolves identity from plan 06 onward, so this fixture has to answer step 4. It is
    a stand-in for the one short session the barrier opens, not for the database: what these cases
    assert is which *step* refused the request, and every case below is refused at or before the
    admission matrix.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def exec(self, _statement):
        return _EmptyResult()


@pytest.fixture(scope="module")
def barrier_client():
    """The real barrier in front of one route that returns 200 whenever it is reached."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/probe")
    async def _probe():
        return {"reached": True}

    app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]
    # Read per request by the barrier, exactly as the real lifespan supplies them.
    app.state.jwt_verifier = make_test_verifier()
    app.state.session_factory = _NoIdentitySession
    # An empty registry, which is what makes /probe undeclared *to this app* rather than merely
    # absent from the production table. It also keeps every case here off the on-path attempt
    # route: a route with no declaration has no operation.
    app.state.route_registry = ()

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_the_probe_route_is_undeclared(barrier_client):
    """Guards this module's premise: /probe carries no registry declaration.

    Asserted against both tables the barrier could consult -- the production one and the empty one
    this app puts on its own state -- so the premise cannot survive a change to either.
    """
    assert lookup("GET", "/probe") is None
    assert lookup("GET", "/probe", ()) is None


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


class TestWellFormedCredentialPassesTheWireContract:
    """The positive control: the 401s above are the wire contract, not a blanket deny.

    Plan 06 moved verification and resolution onto this seam, so a well-formed credential no
    longer reaches the handler -- `/probe` has no `core.external_identities` row and is not
    pre-auth-callable, so §1.3 outcome 1' refuses it. The control still does its job, and does it
    better: the answer *changes class* when the wire contract passes, which is the proof that the
    401s above are §1.1 refusals rather than a deny-everything middleware. A 200 here would now
    prove less, because it could equally come from a barrier that skipped steps 3 to 5.
    """

    def test_one_well_formed_bearer_advances_past_the_wire_contract(self, barrier_client):
        """It clears §1.1 and §1.2 and is refused by the admission matrix, not by the wire."""
        response = barrier_client.get("/probe",
                                      headers={"Authorization": f"Bearer {make_token()}"})
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    def test_the_scheme_is_matched_case_insensitively(self, barrier_client):
        """RFC 7235 makes the auth scheme case-insensitive, and §1.1 follows it.

        The deleted `get_current_user` required a literal 'Bearer ' prefix and refused lowercase.
        That was a stricter-than-the-RFC rule, and losing it is a deliberate behaviour change, not
        a regression: the token bytes after the scheme are still never case-folded or trimmed.
        """
        response = barrier_client.get("/probe",
                                      headers={"Authorization": f"bearer {make_token()}"})
        assert response.status_code == 403

    def test_an_unverifiable_token_is_refused_at_step_3(self, barrier_client):
        """§1.2: a well-formed but unverifiable credential is the identical 401, never a 403."""
        response = barrier_client.get("/probe",
                                      headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
