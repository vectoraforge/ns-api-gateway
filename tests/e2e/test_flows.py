"""The multi-route flows, each driving one sequence of real routes over the real app."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.tables.identities import IdentityProvider
from nativespeaker.api.tables.purchases import PurchaseProvider

from .conftest import seed_identity, seed_purchase_tokens

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestChatLifecycle:
    async def test_full_chat_lifecycle(self, async_client, linked_firebase_identity,
                                       quota_grant):
        """Full lifecycle: create -> followup -> read messages -> list chats -> delete."""
        create_resp = await async_client.post("/chats",
                                              json={"phrase": "I am going to home.", "lang": "en"})
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        chat_id = create_data["chat_id"]
        assert create_data["role"] == "ai"
        assert "content" in create_data

        followup_resp = await async_client.post(f"/chats/{chat_id}",
                                                json={"message": "Why is that incorrect?"})
        assert followup_resp.status_code == 200
        followup_data = followup_resp.json()
        assert followup_data["chat_id"] == chat_id
        assert followup_data["role"] == "ai"

        messages_resp = await async_client.get(f"/chats/{chat_id}")
        assert messages_resp.status_code == 200
        messages = messages_resp.json()
        assert isinstance(messages, list)
        assert len(messages) >= 4
        roles = [m["role"] for m in messages]
        assert "human" in roles
        assert "ai" in roles

        list_resp = await async_client.get("/chats")
        assert list_resp.status_code == 200
        chat_ids = [c["chat_id"] for c in list_resp.json()]
        assert chat_id in chat_ids

        delete_resp = await async_client.delete(f"/chats/{chat_id}")
        assert delete_resp.status_code == 204

        verify_resp = await async_client.get(f"/chats/{chat_id}")
        assert verify_resp.status_code == 404


UPGRADE_SUBJECT = "e2e-flow-upgrade-subject"


@pytest_asyncio.fixture(loop_scope="module")
async def upgrade_flow_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio(loop_scope="module")
class TestTheUpgradeAsAClientSeesIt:
    """Upgrade, then read both endpoints a client reads: the provider moves and the purchase tokens do not."""

    async def test_both_reads_report_the_new_provider_and_no_purchase_token_moves(
            self, upgrade_flow_client, _db_transaction, scripted_firebase_adapter):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=UPGRADE_SUBJECT,
                                      provider=IdentityProvider.anonymous)
        await seed_purchase_tokens(_db_transaction, user_id=user.id)
        headers = {"Authorization": f"Bearer {make_token(sub=UPGRADE_SUBJECT)}"}

        me_before = await upgrade_flow_client.get("/users/me", headers=headers)
        sync_before = await upgrade_flow_client.post("/auth/sync", headers=headers)

        assert (me_before.status_code, sync_before.status_code) == (200, 200), me_before.text
        assert me_before.json()["identity_provider"] == "anonymous"
        assert sync_before.json()["identity_provider"] == "anonymous"
        # Captured from the endpoint, never re-derived: a regenerated token would still match a re-derivation.
        tokens_before = me_before.json()["purchase_tokens"]

        scripted_firebase_adapter.script(
            VerifiedProviderIdentity(provider=IdentityProvider.google,
                                     provider_uid=f"google-uid-{UPGRADE_SUBJECT}"))
        issued = await upgrade_flow_client.post("/auth/challenge",
                                                json={"operation": "upgrade_anonymous_to_registered"},
                                                headers=headers)
        assert issued.status_code == 200, issued.text
        completion = await upgrade_flow_client.post("/auth/upgrade-anonymous",
                                                    json={"challenge_id": issued.json()["challenge_id"]},
                                                    headers=headers)
        assert completion.status_code == 200, completion.text
        assert completion.json() == {"identity_provider": "google"}

        me_after = await upgrade_flow_client.get("/users/me", headers=headers)
        sync_after = await upgrade_flow_client.post("/auth/sync", headers=headers)

        assert (me_after.status_code, sync_after.status_code) == (200, 200), me_after.text
        assert me_after.json()["identity_provider"] == "google"
        # Asserted as agreement too, because criterion 3 names two endpoints rather than one row.
        assert sync_after.json()["identity_provider"] == me_after.json()["identity_provider"]

        tokens_after = me_after.json()["purchase_tokens"]
        # PurchaseProvider, never IdentityProvider: both carry the value apple and mean different things.
        assert set(tokens_after) == {provider.value for provider in PurchaseProvider}
        assert tokens_after == tokens_before
