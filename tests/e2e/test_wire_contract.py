"""FOUND-02 / §1.1: the same six wire cases, over a real ASGI transport.

`tests/unit/test_wire_contract.py` drives `extract_bearer` with hand-built header lists.
This module is worth having beside it for one reason: it proves the awkward shapes **survive the
transport**. A duplicate `Authorization` field, a differently-cased pair of them, and a
comma-joined value all reach `scope["headers"]` byte-for-byte instead of being folded, deduplicated,
or first-value-selected between the client and `extract_bearer`. If they were folded, the unit
module would still pass while the deployed service quietly authenticated one of two credentials --
which is the desync §1.1 exists to make impossible.

The bodies are compared byte-for-byte across all six. §3.1's anti-oracle rule is not "the same
status": it is the same status, the same body, and the same copy, so a caller cannot tell which of
the six conditions it tripped.

No stub verifier is used and none is needed: every case here is refused at step 2, before the token
is ever handed to a verifier.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.e2e

TOKEN = "header.payload.signature"

# The six §1.1 cases, as the header list each sends. `None` means "send no Authorization field".
WIRE_CASES: list[tuple[str, list[tuple[str, str]]]] = [
    ("zero values", []),
    ("two instances", [("authorization", f"Bearer {TOKEN}"),
                       ("authorization", f"Bearer {TOKEN}")]),
    ("two differently cased instances", [("Authorization", f"Bearer {TOKEN}"),
                                         ("AUTHORIZATION", f"Bearer {TOKEN}")]),
    ("comma joined", [("authorization", f"Bearer {TOKEN}, Bearer {TOKEN}")]),
    ("empty token", [("authorization", "Bearer ")]),
    ("trailing content", [("authorization", f"Bearer {TOKEN} extra")]),
]

CASE_IDS = [name for name, _ in WIRE_CASES]


@pytest_asyncio.fixture(loop_scope="module")
async def wire_client(_app_lifespan):
    """A client over the real started app carrying no default Authorization field."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio(loop_scope="module")
class TestTheSixCasesOverTheWire:

    @pytest.mark.parametrize("headers", [headers for _, headers in WIRE_CASES], ids=CASE_IDS)
    async def test_each_case_is_refused_with_the_shared_body(self, wire_client, headers):
        response = await wire_client.get("/chats", headers=headers)
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_all_six_bodies_are_byte_identical(self, wire_client):
        """§3.1: one class, one body -- not merely one status."""
        bodies = [(await wire_client.get("/chats", headers=headers)).content
                  for _, headers in WIRE_CASES]
        assert len(set(bodies)) == 1

    async def test_all_six_statuses_are_identical(self, wire_client):
        statuses = {(await wire_client.get("/chats", headers=headers)).status_code
                    for _, headers in WIRE_CASES}
        assert statuses == {401}


async def _record(sent: list[tuple[bytes, bytes]], scope, _receive, send) -> None:
    """A bare ASGI app that records what the transport actually delivered, then answers 204."""
    sent.extend(scope["headers"])
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _delivered(headers: list[tuple[str, str]]) -> list[tuple[bytes, bytes]]:
    """Send `headers` through the same transport the cases above use; return `scope["headers"]`."""
    sent: list[tuple[bytes, bytes]] = []
    transport = ASGITransport(app=lambda s, r, x: _record(sent, s, r, x))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/probe", headers=headers)
    return [(key, value) for key, value in sent if key.lower() == b"authorization"]


@pytest.mark.asyncio(loop_scope="module")
class TestTheTransportPreservesTheAwkwardShapes:
    """This module's whole reason for existing: the shapes are not folded before the server reads them.

    Asserted against a bare recording app rather than the real one, because what is under test
    here is the transport, not admission. If httpx folded a duplicate into one comma-joined
    value the cases above would still return 401 -- but for the wrong reason, and the deployed
    service's behaviour would no longer be what they claim to prove.
    """

    async def test_a_duplicate_survives_as_two_fields_not_one(self):
        delivered = await _delivered([("authorization", "Bearer a"),
                                      ("authorization", "Bearer b")])
        assert [value for _, value in delivered] == [b"Bearer a", b"Bearer b"]

    async def test_differently_cased_fields_arrive_folded_onto_one_lowercase_key(self):
        """Which is what makes them count as duplicates rather than as two different fields."""
        delivered = await _delivered([("Authorization", "Bearer a"),
                                      ("AUTHORIZATION", "Bearer b")])
        assert [key for key, _ in delivered] == [b"authorization", b"authorization"]

    async def test_a_comma_joined_value_arrives_unsplit(self):
        delivered = await _delivered([("authorization", "Bearer a, Bearer b")])
        assert [value for _, value in delivered] == [b"Bearer a, Bearer b"]


@pytest.mark.asyncio(loop_scope="module")
class TestTheContractRunsOnEveryAuthenticatedRoute:
    """§1.1 belongs to admission, so it does not vary by route -- and does not apply to the allowlist."""

    @pytest.mark.parametrize("path", ["/", "/examples", "/chats"])
    async def test_a_duplicate_is_refused_identically_on_every_authenticated_route(
            self, wire_client, path):
        response = await wire_client.get(path, headers=[("authorization", "Bearer a"),
                                                        ("authorization", "Bearer b")])
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_the_public_readiness_probe_is_not_subject_to_it(self, wire_client):
        """§2.1's allowlist declares no auth dependency at all: wire contract included."""
        response = await wire_client.get("/health/ready",
                                         headers=[("authorization", "Bearer a"),
                                                  ("authorization", "Bearer b")])
        assert response.status_code == 200
