"""The anonymous device-grant claim, end to end through the real router against a real database."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.tables.auth import AuthChallenge
from nativespeaker.api.tables.grants import (
    AccessGrant,
    AccessGrantAntiAbuse,
    AccessGrantSource,
    UserMonthlyUsage,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, NativeClaimProvider

from .conftest import seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-claim-anonymous-subject"

# Two distinct tokens, each used once: the query token is never reused for the update.
QUERY_TOKEN = "query-token-tracer"
UPDATE_TOKEN = "update-token-tracer"


@pytest_asyncio.fixture(loop_scope="module")
async def claim_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


@pytest.mark.asyncio(loop_scope="module")
class TestTheAnonymousDeviceGrantHappyPath:
    """One anonymous row, one handle, one claim, and the four rows one success must leave."""

    async def test_a_never_set_device_claims_the_grant_and_the_body_reports_it(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.anonymous)

        issued = await claim_client.post("/auth/challenge",
                                         json={"operation": "claim_anonymous_grant"},
                                         headers=_auth())

        assert issued.status_code == 200, issued.text
        handle = issued.json()["challenge_id"]
        # Issuance reaches no device gate, so a call here would mean the handler did more than issue.
        assert scripted_devicecheck_adapter.read_calls == []

        claim = await claim_client.post("/auth/claim-anonymous-grant",
                                        json={"challenge_id": handle,
                                              "query_token": QUERY_TOKEN,
                                              "update_token": UPDATE_TOKEN},
                                        headers=_auth())

        assert claim.status_code == 200, claim.text
        assert claim.headers["Cache-Control"] == "no-store"
        body = claim.json()
        assert body["identity_provider"] == "anonymous"
        assert body["entitlement"]["type"] == "anonymous_device_grant"
        assert body["entitlement"]["status"] == "active"
        assert body["entitlement"]["tier_id"] == "anonymous"
        assert body["entitlement"]["monthly_credits"] == 10
        assert body["entitlement"]["monthly_used"] == 0
        assert body["entitlement"]["current_period"]

        assert scripted_devicecheck_adapter.read_calls == [QUERY_TOKEN]
        # The update carried the query's bit1 forward, and set only bit0.
        assert scripted_devicecheck_adapter.write_calls == [(UPDATE_TOKEN, True, False)]

        async with _db_transaction() as session:
            grants = (await session.exec(
                select(AccessGrant).where(col(AccessGrant.user_id) == user.id))).all()
            assert len(grants) == 1
            grant = grants[0]
            assert grant.source is AccessGrantSource.anonymous_device_grant
            assert grant.tier_id == "anonymous"
            assert grant.subscription_id is None

            anti_abuse = (await session.exec(
                select(AccessGrantAntiAbuse)
                .where(col(AccessGrantAntiAbuse.grant_id) == grant.id))).all()
            assert len(anti_abuse) == 1
            assert anti_abuse[0].native_claim_provider is NativeClaimProvider.ios_devicecheck
            # Both hash columns NULL: the iOS arm of the table's exclusive-or CHECK.
            assert anti_abuse[0].idp_account_hash is None
            assert anti_abuse[0].idp_account_hash_key_version is None

            usage = (await session.exec(
                select(UserMonthlyUsage)
                .where(col(UserMonthlyUsage.grant_id) == grant.id))).all()
            assert len(usage) == 1
            assert usage[0].monthly_used == 0
            assert usage[0].monthly_period == body["entitlement"]["current_period"]

            identity = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == SUBJECT))).one()
            assert identity.free_grant_consumed_at is not None
            assert identity.native_claim_platform is NativeClaimProvider.ios_devicecheck
            # The one instant: the grant, the marker and the usage period all came from it.
            assert identity.free_grant_consumed_at == grant.starts_at

            challenge = (await session.exec(
                select(AuthChallenge)
                .where(col(AuthChallenge.challenge_id) == handle))).one()
            assert challenge.consumed_at is not None
