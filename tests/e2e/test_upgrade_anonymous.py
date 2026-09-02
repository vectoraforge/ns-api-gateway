"""The upgrade endpoint's e2e home, opening with the canary that proves the Google-linked credential."""
import firebase_admin
import pytest
from firebase_admin import auth

from nativespeaker.api.auth.firebase import FirebaseAdminLookup
from nativespeaker.api.tables.identities import IdentityProvider

pytestmark = pytest.mark.e2e


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
