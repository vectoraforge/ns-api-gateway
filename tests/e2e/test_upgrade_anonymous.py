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
from nativespeaker.api.tables.auth import AuthChallenge
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User

from .conftest import seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-anonymous-subject"

# What the scripted read reports back; neither value is derived from anything the caller sent.
GOOGLE_UID = "google-uid-tracer-anonymous-subject"
VERIFIED_EMAIL = "tracer-anonymous@example.test"

# The one body all three refusals answer with, compared by equality so a more helpful field fails.
REFUSED = {"code": "operation_not_allowed"}


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


async def _issue(client, subject: str) -> str:
    """Obtain an upgrade handle for `subject`, which every case below spends exactly once."""
    issued = await client.post("/auth/challenge",
                               json={"operation": "upgrade_anonymous_to_registered"},
                               headers=_auth(subject))
    assert issued.status_code == 200, issued.text
    return issued.json()["challenge_id"]


async def _upgrade(client, subject: str, handle: str):
    return await client.post("/auth/upgrade-anonymous",
                             json={"challenge_id": handle},
                             headers=_auth(subject))


async def _binding(factory, subject: str) -> tuple[IdentityProvider, str | None]:
    """The stored provider and provider_uid, read back through the test transaction."""
    async with factory() as session:
        row = (await session.exec(
            select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                           col(ExternalIdentity.subject) == subject))).one()
        return row.provider, row.provider_uid


async def _challenge_for(factory, handle: str) -> AuthChallenge:
    async with factory() as session:
        return (await session.exec(
            select(AuthChallenge).where(col(AuthChallenge.challenge_id) == handle))).one()


@pytest.mark.asyncio(loop_scope="module")
class TestTheRefusalsAndTheRepeat:
    """The four cases the real Google account cannot produce on demand, each through the real router."""

    async def test_a_live_anonymous_read_refuses_and_leaves_the_row_untouched(
            self, upgrade_client, _db_transaction, scripted_firebase_adapter):
        """The client called before its own linking finished: refused, and nothing is recorded."""
        subject = "e2e-upgrade-not-yet-linked"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                            provider=IdentityProvider.anonymous)
        before = await _binding(_db_transaction, subject)
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.anonymous, provider_uid=None))

        handle = await _issue(upgrade_client, subject)
        completion = await _upgrade(upgrade_client, subject, handle)

        assert completion.status_code == 403, completion.text
        assert completion.json() == REFUSED
        assert await _binding(_db_transaction, subject) == before

    async def test_a_diverged_binding_is_refused_rather_than_rewritten(
            self, upgrade_client, _db_transaction, scripted_firebase_adapter):
        """The stored row is registered and the live read disagrees: no column moves."""
        subject = "e2e-upgrade-drifted"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                            provider=IdentityProvider.google)
        before = await _binding(_db_transaction, subject)
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid="google-uid-somebody-else-entirely"))

        handle = await _issue(upgrade_client, subject)
        completion = await _upgrade(upgrade_client, subject, handle)

        assert completion.status_code == 403, completion.text
        assert completion.json() == REFUSED
        assert await _binding(_db_transaction, subject) == before

    async def test_a_provider_account_another_row_holds_is_refused_and_spends_the_handle(
            self, upgrade_client, _db_transaction, scripted_firebase_adapter):
        """Refused by the write's conflict arm, so the handle is spent: this failure is after the read."""
        subject = "e2e-upgrade-claimant"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                            provider=IdentityProvider.anonymous)
        _, owner = await seed_identity(_db_transaction, issuer=TEST_ISSUER,
                                       subject="e2e-upgrade-account-owner",
                                       provider=IdentityProvider.google)
        # Read back rather than rederived: a second derivation stops colliding the day the helper changes.
        assert owner.provider_uid is not None
        claimant_before = await _binding(_db_transaction, subject)
        owner_before = await _binding(_db_transaction, owner.subject)
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid=owner.provider_uid))

        handle = await _issue(upgrade_client, subject)
        completion = await _upgrade(upgrade_client, subject, handle)

        assert completion.status_code == 403, completion.text
        assert completion.json() == REFUSED
        assert await _binding(_db_transaction, subject) == claimant_before
        assert await _binding(_db_transaction, owner.subject) == owner_before
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_the_repeat_that_changes_nothing_answers_as_the_flip_did(
            self, upgrade_client, _db_transaction, scripted_firebase_adapter):
        """D-04: same status, same one-field body, no write, and one provider read per completion."""
        subject = "e2e-upgrade-repeated"
        _, seeded = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                        provider=IdentityProvider.anonymous)
        row_id = seeded.id
        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid=f"google-uid-{subject}",
                                     email=VERIFIED_EMAIL))

        first = await _upgrade(upgrade_client, subject, await _issue(upgrade_client, subject))
        after_flip = await _binding(_db_transaction, subject)
        second = await _upgrade(upgrade_client, subject, await _issue(upgrade_client, subject))

        assert (first.status_code, second.status_code) == (200, 200), second.text
        assert first.json() == second.json() == {"identity_provider": "google"}
        assert await _binding(_db_transaction, subject) == after_flip
        # One read per completion, not one in total: an already-registered row is never read past.
        assert scripted_firebase_adapter.calls == [(TEST_ISSUER, subject)] * 2

        async with _db_transaction() as session:
            identity = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == subject))).one()
            assert identity.id == row_id


@pytest_asyncio.fixture(loop_scope="module")
async def google_linked_client(_app_lifespan, google_linked_firebase_credential):
    """A client bearing the real linked ID token, so it must not take stub_verifier, which would reject it."""
    id_token, _ = google_linked_firebase_credential
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {id_token}"
        yield client


@pytest.mark.asyncio(loop_scope="module")
class TestTheRealGoogleLinkedUpgrade:
    """Nothing substituted, end to end against the live project: the flip runs on Google's own answer."""

    async def test_a_genuinely_google_linked_user_completes_through_the_real_admin_sdk(
            self, google_linked_client, _db_transaction, _app_lifespan, _app_config,
            google_linked_firebase_credential):
        _, local_id = google_linked_firebase_credential
        adapter = _app_lifespan.state.firebase_adapter
        # scripted_firebase_adapter is deliberately not requested, and this is what makes that visible.
        assert isinstance(adapter, FirebaseAdminLookup)
        issuer = _app_config.jwt.issuer
        _, seeded = await seed_identity(_db_transaction, issuer=issuer, subject=local_id,
                                        provider=IdentityProvider.anonymous)
        row_id_before = seeded.id
        # Read through the same seam the endpoint uses, so the uid asserted below is Google's, not the test's.
        reported = await adapter.get_user_provider_data(issuer, local_id)

        issued = await google_linked_client.post(
            "/auth/challenge", json={"operation": "upgrade_anonymous_to_registered"})

        assert issued.status_code == 200, issued.text
        completion = await google_linked_client.post(
            "/auth/upgrade-anonymous", json={"challenge_id": issued.json()["challenge_id"]})

        assert completion.status_code == 200, completion.text
        assert completion.json() == {"identity_provider": "google"}

        async with _db_transaction() as session:
            identities = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == issuer,
                                               col(ExternalIdentity.subject) == local_id))).all()
        # Exactly one row, and the same one: a flip in place, never a second row or a merge.
        assert len(identities) == 1
        assert identities[0].id == row_id_before
        assert identities[0].provider is IdentityProvider.google
        assert identities[0].provider_uid == reported.provider_uid
