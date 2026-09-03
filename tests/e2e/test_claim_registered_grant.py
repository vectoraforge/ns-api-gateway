"""The registered account-grant claim, end to end through the real router against a real database."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.devicecheck import BitState
from nativespeaker.api.tables.auth import AuthChallenge
from nativespeaker.api.tables.grants import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    UserMonthlyUsage,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider

from .conftest import seed_grant, seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-claim-registered-subject"

# One token, naming the device the read and the write both act on.
DEVICE_TOKEN = "device-token-registered-tracer"

# The one body every refusal answers with, compared by equality so a more helpful field fails here.
REFUSED = {"code": "operation_not_allowed"}


@pytest_asyncio.fixture(loop_scope="module")
async def claim_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


async def _issue(client, subject: str) -> str:
    """Obtain a claim handle for `subject`, which every case below spends exactly once."""
    issued = await client.post("/auth/challenge",
                               json={"operation": "claim_registered_grant"},
                               headers=_auth(subject))
    assert issued.status_code == 200, issued.text
    return issued.json()["challenge_id"]


async def _claim(client, subject: str, handle: str, **body):
    """Spend `handle` on the registered claim; `body` replaces the default two fields wholesale."""
    payload = {"challenge_id": handle, "device_token": DEVICE_TOKEN} if not body else body
    return await client.post("/auth/claim-registered-grant", json=payload,
                             headers=_auth(subject))


async def _challenge_for(factory, handle: str) -> AuthChallenge:
    async with factory() as session:
        return (await session.exec(
            select(AuthChallenge).where(col(AuthChallenge.challenge_id) == handle))).one()


async def _grants_of(factory, user_id) -> list[AccessGrant]:
    """Every grant row of `user_id`, in the same ascending order the writer locks them."""
    async with factory() as session:
        return list((await session.exec(
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id)
            .order_by(col(AccessGrant.id).asc()))).all())


async def _row_counts(factory, user_id) -> tuple[int, int]:
    """The grant and usage row counts for `user_id`: the two kinds a claim writes."""
    grants = await _grants_of(factory, user_id)
    ids = [grant.id for grant in grants]
    async with factory() as session:
        usage = (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id).in_(ids or [uuid4()])))).all()
        return len(grants), len(usage)


async def _usage_of(factory, grant_id) -> UserMonthlyUsage:
    async with factory() as session:
        return (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id))).one()


@pytest.mark.asyncio(loop_scope="module")
class TestTheNewRegisteredGrantHappyPath:
    """D-11: a clean registered account, one handle, Apple's bit1, and the three rows one success leaves."""

    async def test_a_never_set_device_claims_the_grant_and_the_body_reports_it(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)

        handle = await _issue(claim_client, SUBJECT)
        # Issuance reaches no device gate, so a call here would mean the handler did more than issue.
        assert scripted_devicecheck_adapter.read_calls == []

        claim = await _claim(claim_client, SUBJECT, handle)

        assert claim.status_code == 200, claim.text
        assert claim.headers["Cache-Control"] == "no-store"
        body = claim.json()
        assert body["identity_provider"] == "google"
        assert body["entitlement"]["type"] == "registered_account_grant"
        assert body["entitlement"]["status"] == "active"
        assert body["entitlement"]["tier_id"] == "registered"
        assert body["entitlement"]["monthly_credits"] == 50
        assert body["entitlement"]["monthly_used"] == 0
        assert body["entitlement"]["current_period"]

        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN]
        # The update carried the query's bit0 forward, set only bit1, and named the device that was read.
        assert scripted_devicecheck_adapter.write_calls == [(DEVICE_TOKEN, False, True)]

        grants = await _grants_of(_db_transaction, user.id)
        assert len(grants) == 1
        assert grants[0].source is AccessGrantSource.registered_account_grant
        assert grants[0].status is AccessGrantStatus.active
        assert grants[0].tier_id == "registered"
        assert grants[0].ends_at is None

        usage = await _usage_of(_db_transaction, grants[0].id)
        assert usage.monthly_used == 0
        assert usage.monthly_period == body["entitlement"]["current_period"]

        async with _db_transaction() as session:
            identity = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == SUBJECT))).one()
        # The one instant: the grant, the marker and the usage period all came from it.
        assert identity.free_grant_consumed_at == grants[0].starts_at
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestTheConversionOfAnActiveAnonymousGrant:
    """D-10: one allowance changes tier inside one transaction, and Apple is never asked (D-02)."""

    async def test_the_anonymous_grant_is_expired_and_its_usage_moves_to_the_registered_row(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        subject = "e2e-claim-registered-conversion"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        period = datetime.now(UTC).strftime("%Y-%m")
        # Strictly earlier than the request instant: `CHECK (ends_at IS NULL OR ends_at > starts_at)` is strict.
        anonymous, _ = await seed_grant(_db_transaction, user_id=user.id, tier_id="anonymous",
                                        source=AccessGrantSource.anonymous_device_grant,
                                        status=AccessGrantStatus.active,
                                        monthly_period=period, monthly_used=7,
                                        starts_at=datetime.now(UTC) - timedelta(hours=1))

        handle = await _issue(claim_client, subject)
        claim = await _claim(claim_client, subject, handle)

        assert claim.status_code == 200, claim.text
        assert claim.headers["Cache-Control"] == "no-store"
        body = claim.json()
        assert body["entitlement"]["type"] == "registered_account_grant"
        assert body["entitlement"]["tier_id"] == "registered"
        assert body["entitlement"]["monthly_credits"] == 50
        assert body["entitlement"]["current_period"] == period
        assert body["entitlement"]["monthly_used"] == 7

        # D-02: the conversion issues no new allowance, so it spends no new device slot.
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []

        grants = await _grants_of(_db_transaction, user.id)
        assert len(grants) == 2
        expired = next(grant for grant in grants if grant.id == anonymous.id)
        registered = next(grant for grant in grants if grant.id != anonymous.id)
        assert expired.status is AccessGrantStatus.expired
        # The source is history and is never rewritten: only the status and the end instant move.
        assert expired.source is AccessGrantSource.anonymous_device_grant
        assert expired.ends_at == registered.starts_at
        assert registered.source is AccessGrantSource.registered_account_grant
        assert [grant.id for grant in grants
                if grant.status is AccessGrantStatus.active] == [registered.id]

        old_usage = await _usage_of(_db_transaction, anonymous.id)
        new_usage = await _usage_of(_db_transaction, registered.id)
        assert (new_usage.monthly_period, new_usage.monthly_used) == (old_usage.monthly_period,
                                                                      old_usage.monthly_used)
        assert (new_usage.monthly_period, new_usage.monthly_used) == (period, 7)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestTheGuardsThatWriteNothing:
    """The three refusals this route owes before any row is written, each costing at most one Apple read."""

    async def test_an_anonymous_caller_is_refused_through_the_fourth_claim_leaf(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """D-05: the stored provider column is the sole classifier, and it decides before Apple."""
        subject = "e2e-claim-registered-anonymous-caller"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        # Decided after the claim, because the claimant check is the first thing the post-claim work does.
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    @pytest.mark.parametrize("token", [None, ""], ids=["absent", "empty"])
    async def test_a_body_without_a_usable_device_token_is_the_frameworks_422(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter, token):
        """D-04: `min_length=1` on a required field is what makes an unusable token a 422 and not a 403."""
        subject = "e2e-claim-registered-no-token"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                            provider=IdentityProvider.google)

        handle = await _issue(claim_client, subject)
        payload = {"challenge_id": handle}
        if token is not None:
            payload["device_token"] = token
        refusal = await _claim(claim_client, subject, handle, **payload)

        assert refusal.status_code == 422, refusal.text
        assert scripted_devicecheck_adapter.read_calls == []
        # The handler is never entered, so the handle survives unclaimed and unspent.
        challenge = await _challenge_for(_db_transaction, handle)
        assert (challenge.claimed_at, challenge.consumed_at) == (None, None)

    async def test_a_device_whose_bit1_is_already_set_is_exhausted_and_is_never_written_to(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """D-01: bit1 is the registered slot, and a set bit refuses with no device state in the body."""
        subject = "e2e-claim-registered-device-spent"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        scripted_devicecheck_adapter.script(BitState(bit0=False, bit1=True))

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == {"code": "device_grant_exhausted"}
        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN]
        # The slot is spent, so the write that would spend it again is never attempted.
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None
