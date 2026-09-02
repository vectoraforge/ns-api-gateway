"""The upgrade endpoint's e2e home, opening with the canary that proves the Google-linked credential."""
import firebase_admin
import pytest
import pytest_asyncio
from firebase_admin import auth
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.auth.firebase import FirebaseAdminLookup
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User

from .conftest import seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-anonymous-subject"

# What the scripted read reports back; neither value is derived from anything the caller sent.
GOOGLE_UID = "google-uid-tracer-anonymous-subject"
VERIFIED_EMAIL = "tracer-anonymous@example.test"


@pytest_asyncio.fixture(loop_scope="module")
async def upgrade_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


@pytest.fixture(scope="module", autouse=True)
def _google_user_deleted_after_teardown(_app_lifespan, _app_config):
    """Autouse, so it is set up before the credential fixture and therefore finalized after it."""
    holder: dict[str, str] = {}
    yield holder
    local_id = holder.get("local_id")
    if local_id is None:
        # The recording case never ran; its own failure is the report, so do not add a second one.
        return
    admin_app = firebase_admin.get_app(name=f"issuer:{_app_config.jwt.issuer}")
    with pytest.raises(auth.UserNotFoundError):
        auth.get_user(local_id, app=admin_app)


@pytest.mark.asyncio(loop_scope="module")
class TestTheGoogleLinkedCredential:
    """The standing proof that exchange-and-link still yields a genuinely Google-linked session."""

    async def test_the_linked_user_reports_exactly_one_google_provider_entry(
            self, google_linked_firebase_credential, _app_lifespan, _app_config):
        _, local_id = google_linked_firebase_credential
        admin_app = firebase_admin.get_app(name=f"issuer:{_app_config.jwt.issuer}")
        record = auth.get_user(local_id, app=admin_app)
        # An exact one-element comparison: the classifier this phase depends on refuses anything else.
        assert [entry.provider_id for entry in record.provider_data] == ["google.com"]
        identity = await _app_lifespan.state.firebase_adapter.get_user_provider_data(
            _app_config.jwt.issuer, local_id)
        assert identity.provider is IdentityProvider.google
        assert identity.provider_uid

    async def test_the_read_ran_through_the_production_lookup(self, _app_lifespan):
        # scripted_firebase_adapter is deliberately not requested, and this is what makes that visible.
        assert isinstance(_app_lifespan.state.firebase_adapter, FirebaseAdminLookup)

    async def test_the_firebase_user_is_deleted_when_the_module_tears_down(
            self, google_linked_firebase_credential, _google_user_deleted_after_teardown, _app_config):
        _, local_id = google_linked_firebase_credential
        admin_app = firebase_admin.get_app(name=f"issuer:{_app_config.jwt.issuer}")
        assert auth.get_user(local_id, app=admin_app).uid == local_id
        # The not-found read runs in the fixture's finalizer, after the credential has been torn down.
        _google_user_deleted_after_teardown["local_id"] = local_id


@pytest.mark.asyncio(loop_scope="module")
class TestTheAnonymousToRegisteredHappyPath:
    """One stored-anonymous row, one issued handle, one completion, and the row state that must result."""

    async def test_a_stored_anonymous_row_is_flipped_in_place_to_the_provider_the_read_reports(
            self, upgrade_client, _db_transaction, scripted_firebase_adapter):
        _, seeded = await seed_identity(_db_transaction,
                                        issuer=TEST_ISSUER,
                                        subject=SUBJECT,
                                        provider=IdentityProvider.anonymous)
        row_id_before = seeded.id
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid=GOOGLE_UID,
                                     email=VERIFIED_EMAIL))

        issued = await upgrade_client.post(
            "/auth/challenge",
            json={"operation": "upgrade_anonymous_to_registered"},
            headers=_auth())

        assert issued.status_code == 200
        handle = issued.json()["challenge_id"]
        # Issuance reads no provider, so a call here would mean the handler did more than issue.
        assert scripted_firebase_adapter.calls == []

        completion = await upgrade_client.post("/auth/upgrade-anonymous",
                                               json={"challenge_id": handle},
                                               headers=_auth())

        assert completion.status_code == 200
        assert completion.json() == {"identity_provider": "google"}
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)]

        async with _db_transaction() as session:
            identities = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == SUBJECT))).all()
            # Exactly one row, and the same one: a flip in place, never a second row or a merge.
            assert len(identities) == 1
            identity = identities[0]
            assert identity.id == row_id_before
            assert identity.provider is IdentityProvider.google
            assert identity.provider_uid == GOOGLE_UID

            user = (await session.exec(
                select(User).where(col(User.id) == identity.user_id))).one()
            assert user.registered_at is not None
            # Copied because the stored value was still NULL; nothing else on the user row moved.
            assert user.email == VERIFIED_EMAIL
            assert user.display_name is None
