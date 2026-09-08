"""What `POST /auth/sign-out-all` answers over the real router: the confirmed revocation, and its one record."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.tables.identities import IdentityProvider

from .conftest import seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-sign-out-all-subject"

# The one module that writes a record on the confirmed path: the router's own INFO line.
_ROUTER_LOGGER = "nativespeaker.api.routers.auth.logger"


class _LogSpy:
    """A recording spy on a module's own logger, so "which record, once" stays observable."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **fields) -> None:
        self.entries.append((event, fields))


def _spy_on(monkeypatch, targets: tuple[str, ...], levels: tuple[str, ...]) -> _LogSpy:
    """A spy, not `capture_logs`: the module-level logger caches its binding, so capture sees nothing."""
    spy = _LogSpy()
    for target in targets:
        for level in levels:
            monkeypatch.setattr(f"{target}.{level}", spy.record)
    return spy


@pytest.fixture
def info_records(monkeypatch) -> _LogSpy:
    """Every INFO record the router writes, and nothing else."""
    return _spy_on(monkeypatch, (_ROUTER_LOGGER,), ("info",))


@pytest_asyncio.fixture(loop_scope="module")
async def sign_out_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


@pytest.mark.asyncio(loop_scope="module")
class TestTheConfirmedRevocation:
    """The one path this slice serves: Firebase returned, so the caller is signed out everywhere."""

    async def test_a_confirmed_revocation_answers_204_with_an_empty_body(
            self, sign_out_client, _db_transaction, scripted_firebase_adapter):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        scripted_firebase_adapter.script_revocation(None)

        answered = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert answered.status_code == 204, answered.text
        assert answered.content == b""

    async def test_it_makes_exactly_one_revocation_call_for_the_verified_pair(
            self, sign_out_client, _db_transaction, scripted_firebase_adapter):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        scripted_firebase_adapter.script_revocation(None)

        answered = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert answered.status_code == 204, answered.text
        # The whole call list, not its length: a second call or a wrong pair would pass the weaker check.
        assert scripted_firebase_adapter.revoke_calls == [(TEST_ISSUER, SUBJECT)]

    async def test_it_writes_one_info_record_carrying_the_row_id_alone(
            self, sign_out_client, _db_transaction, scripted_firebase_adapter, info_records):
        _, identity = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                          provider=IdentityProvider.google)
        scripted_firebase_adapter.script_revocation(None)

        answered = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert answered.status_code == 204, answered.text
        # The whole entry list, so a second record and an extra field are both visible here.
        assert info_records.entries == [("sign_out_all_confirmed",
                                         {"identity_row_id": str(identity.id)})]
