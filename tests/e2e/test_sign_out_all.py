"""What `POST /auth/sign-out-all` answers over the real router: the confirmed revocation,
every refusal, and the record each one writes."""
import pytest
import pytest_asyncio
from firebase_admin import auth, exceptions
from httpx import ASGITransport, AsyncClient
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.firebase import FirebaseAdminLookup
from nativespeaker.api.tables.identities import IdentityProvider

from .conftest import seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-sign-out-all-subject"

# The provider's own text, which every refusal keeps out of the body and out of the record.
_PROVIDER_TEXT = "the identity toolkit answered no usable result for that request"

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
class _NamedApp:
    """Stands in for a `firebase_admin.App`; identity is all the seam needs from it."""

    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def real_seam(_app_lifespan):
    """Install the real seam over a given apps mapping: only it turns an SDK error into a refusal."""
    original = _app_lifespan.state.firebase_adapter

    def install(apps: dict) -> None:
        _app_lifespan.state.firebase_adapter = FirebaseAdminLookup(apps)

    try:
        yield install
    finally:
        _app_lifespan.state.firebase_adapter = original


@pytest.fixture
def sdk_revocations(monkeypatch):
    """Monkeypatch the SDK call and record it; the test scripts the answer it raises or returns."""
    calls: list[dict] = []

    def script(answer: BaseException | None):
        def fake_revoke(uid, app=None):
            calls.append({"uid": uid, "app": app})
            if isinstance(answer, BaseException):
                raise answer
        monkeypatch.setattr(auth, "revoke_refresh_tokens", fake_revoke)
        return calls

    return script


def _configured(real_seam) -> _NamedApp:
    """One named app for the test issuer, so selection succeeds and the SDK call is reached."""
    app = _NamedApp(f"issuer:{TEST_ISSUER}")
    real_seam({TEST_ISSUER: app})
    return app


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


@pytest.mark.asyncio(loop_scope="module")
class TestTheThreeRefusals:
    """Every outcome that is not a confirmation: an outage, an account the provider lacks, and no app."""

    async def test_a_firebase_outage_answers_503_and_never_204(
            self, sign_out_client, _db_transaction, real_seam, sdk_revocations):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        _configured(real_seam)
        sdk_revocations(exceptions.UnavailableError(_PROVIDER_TEXT))

        answered = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert answered.status_code == 503, answered.text
        # Named on its own: a swallowed raise answers 204, which is the one answer SIGNOUT-02 forbids.
        assert answered.status_code != 204
        assert answered.json() == {"code": "verification_temporarily_unavailable"}

    async def test_an_account_the_provider_does_not_have_answers_401(
            self, sign_out_client, _db_transaction, real_seam, sdk_revocations):
        """D-06: the token verified but names no live principal, so the credential is invalid in substance."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        _configured(real_seam)
        calls = sdk_revocations(auth.UserNotFoundError(_PROVIDER_TEXT))

        answered = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert answered.status_code == 401, answered.text
        assert answered.json() == {"code": "auth_required"}
        assert answered.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'
        # Definitive, so it spends one attempt and no more; a retryable classification would show three.
        assert len(calls) == 1

    async def test_an_issuer_with_no_configured_app_answers_503_with_no_call_made(
            self, sign_out_client, _db_transaction, real_seam, sdk_revocations):
        """D-01: there is no ambient app to fall back to, so selection fails above the SDK."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        real_seam({})
        calls = sdk_revocations(None)

        answered = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert answered.status_code == 503, answered.text
        assert answered.json() == {"code": "verification_temporarily_unavailable"}
        # The whole call list: nothing below the seam boundary may run for an unconfigured issuer.
        assert calls == []

    async def test_the_outage_and_the_no_app_bodies_are_equal_to_each_other(
            self, sign_out_client, _db_transaction, real_seam, sdk_revocations):
        """One body for two causes, compared to each other rather than each to a literal."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        _configured(real_seam)
        sdk_revocations(exceptions.UnavailableError(_PROVIDER_TEXT))
        outage = await sign_out_client.post("/auth/sign-out-all", headers=_auth())
        real_seam({})

        no_app = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert (outage.status_code, no_app.status_code) == (503, 503), no_app.text
        # Raw bytes: a body naming which check refused would differ here and nowhere else.
        assert outage.content == no_app.content


@pytest.mark.asyncio(loop_scope="module")
class TestARepeatedSignOut:
    """The provider operation only re-asserts a later timestamp, and the route holds no state of its own."""

    async def test_a_second_call_after_a_confirmed_one_answers_204_again(
            self, sign_out_client, _db_transaction, scripted_firebase_adapter):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)
        scripted_firebase_adapter.script_revocation(None)

        first = await sign_out_client.post("/auth/sign-out-all", headers=_auth())
        second = await sign_out_client.post("/auth/sign-out-all", headers=_auth())

        assert (first.status_code, second.status_code) == (204, 204), second.text
        assert second.content == b""
        # Both calls, so a route that cached the first answer would be visible as a missing second call.
        assert scripted_firebase_adapter.revoke_calls == [(TEST_ISSUER, SUBJECT)] * 2
