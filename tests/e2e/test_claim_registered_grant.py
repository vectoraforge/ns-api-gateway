"""The registered account-grant claim, end to end through the real router against a real database."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.devicecheck import (
    DEVICECHECK_ATTEMPTS,
    BitState,
    RetryableDeviceCheckError,
)
from nativespeaker.api.errors import ProofRejected
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

# The same body as bytes, so the four refusals are compared on the wire and not after parsing.
REFUSED_BODY = '{"code":"operation_not_allowed"}'

# An hour back, because `CHECK (ends_at IS NULL OR ends_at > starts_at)` is strict.
SEEDED_AGO = timedelta(hours=1)


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


async def _identity_of(factory, subject: str) -> ExternalIdentity:
    async with factory() as session:
        return (await session.exec(
            select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                           col(ExternalIdentity.subject) == subject))).one()


async def _seed_subscription_grant(factory, *, user_id) -> AccessGrant:
    """Insert an active subscription and the grant it entitles; `seed_grant` cannot carry the id."""
    now = datetime.now(UTC)
    subscription_id = uuid4()
    async with factory() as session:
        await session.exec(text(
            "INSERT INTO core.subscriptions"
            " (id, user_id, provider, external_id, tier_id, status, created_at, updated_at)"
            " VALUES (:id, :user_id, 'apple', :external_id, 'registered', 'active', :now, :now)")
            .bindparams(id=subscription_id, user_id=user_id,
                        external_id=f"e2e-subscription-{subscription_id}", now=now))
        grant = AccessGrant(user_id=user_id,
                            tier_id="registered",
                            source=AccessGrantSource.subscription,
                            status=AccessGrantStatus.active,
                            subscription_id=subscription_id,
                            starts_at=now - SEEDED_AGO)
        session.add(grant)
        await session.flush()
        session.add(UserMonthlyUsage(grant_id=grant.id, monthly_period=now.strftime("%Y-%m"),
                                     monthly_used=0))
        await session.commit()
    return grant


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
        # REGGRANT-03: free entitlement from exactly one source at this instant, never from two.
        assert [grant.source for grant in grants
                if grant.status is AccessGrantStatus.active] == [
                    AccessGrantSource.registered_account_grant]

        old_usage = await _usage_of(_db_transaction, anonymous.id)
        new_usage = await _usage_of(_db_transaction, registered.id)
        assert (new_usage.monthly_period, new_usage.monthly_used) == (old_usage.monthly_period,
                                                                      old_usage.monthly_used)
        assert (new_usage.monthly_period, new_usage.monthly_used) == (period, 7)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestTheGuardsThatWriteNothing:
    """The body the handler never sees: an unusable device token is refused before the route runs."""

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


@pytest.mark.asyncio(loop_scope="module")
class TestTheRepeatIsIdempotent:
    """D-09: an account already holding an active registered grant claims again and gets the same body."""

    async def test_a_repeat_answers_the_fresh_claim_body_writes_nothing_and_never_reaches_apple(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        subject = "e2e-claim-registered-repeat"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)

        first = await _claim(claim_client, subject, await _issue(claim_client, subject))
        assert first.status_code == 200, first.text
        after_first = await _row_counts(_db_transaction, user.id)
        assert after_first == (1, 1)
        granted = (await _grants_of(_db_transaction, user.id))[0]
        usage_before = await _usage_of(_db_transaction, granted.id)

        # Cleared rather than re-created: the repeat's own call count is what the next assertion reads.
        scripted_devicecheck_adapter.read_calls.clear()
        scripted_devicecheck_adapter.write_calls.clear()

        handle = await _issue(claim_client, subject)
        repeat = await _claim(claim_client, subject, handle)

        assert repeat.status_code == 200, repeat.text
        assert repeat.headers["Cache-Control"] == "no-store"
        # The same body a fresh claim returns, by equality: the repeat is not a differently-shaped answer.
        assert repeat.json() == first.json()
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == after_first

        unchanged = (await _grants_of(_db_transaction, user.id))[0]
        assert (unchanged.id, unchanged.updated_at) == (granted.id, granted.updated_at)
        usage_after = await _usage_of(_db_transaction, granted.id)
        assert (usage_after.monthly_period, usage_after.monthly_used, usage_after.updated_at) == (
            usage_before.monthly_period, usage_before.monthly_used, usage_before.updated_at)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestTheFourRefusals:
    """One status and one body for four causes, so the route is no account-state oracle (D-05, D-09)."""

    async def test_an_anonymous_caller_is_refused_through_the_fourth_claim_leaf(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """D-05: the stored provider column is the sole classifier, and it decides before Apple."""
        subject = "e2e-claim-registered-anonymous-caller"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.text == REFUSED_BODY
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        # Decided after the claim, because the claimant check is the first thing the post-claim work does.
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_an_active_manual_grant_is_refused(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """One user holds at most one active grant, so a manual grant refuses the claim."""
        subject = "e2e-claim-registered-manual-held"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        await seed_grant(_db_transaction, user_id=user.id, source=AccessGrantSource.manual,
                         status=AccessGrantStatus.active,
                         starts_at=datetime.now(UTC) - SEEDED_AGO)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.text == REFUSED_BODY
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (1, 1)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_an_active_subscription_grant_is_refused_and_is_never_converted(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """A paid source is not a free one: only an anonymous device grant is convertible."""
        subject = "e2e-claim-registered-subscription-held"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        held = await _seed_subscription_grant(_db_transaction, user_id=user.id)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.text == REFUSED_BODY
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert [grant.id for grant in await _grants_of(_db_transaction, user.id)] == [held.id]
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_a_revoked_anonymous_grant_is_refused_by_the_history_read(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """REGGRANT-03: revocation never reopens the slot, and the read is by source and status."""
        subject = "e2e-claim-registered-revoked-anonymous"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        spent, _ = await seed_grant(_db_transaction, user_id=user.id, tier_id="anonymous",
                                    source=AccessGrantSource.anonymous_device_grant,
                                    status=AccessGrantStatus.revoked,
                                    starts_at=datetime.now(UTC) - SEEDED_AGO)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.text == REFUSED_BODY
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        # The revoked row is still the only one: no registered grant was written beside it.
        assert [grant.id for grant in await _grants_of(_db_transaction, user.id)] == [spent.id]
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestTheThreeAppleFailureArms:
    """An eligible account reaches Apple, and each of its three refusing answers writes nothing (D-01)."""

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
        assert (await _identity_of(_db_transaction, subject)).free_grant_consumed_at is None
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_a_token_apple_refuses_is_a_proof_rejection(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        subject = "e2e-claim-registered-token-refused"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        scripted_devicecheck_adapter.script(ProofRejected(stage="devicecheck_read",
                                                          cause="rejected"))

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == {"code": "proof_rejected"}
        # Definitive, so it spends one attempt of the budget rather than all three.
        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN]
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        assert (await _identity_of(_db_transaction, subject)).free_grant_consumed_at is None
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_an_exhausted_apple_budget_is_temporarily_unavailable_and_writes_nothing(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """Fail-closed: only Apple's explicit confirmation permits activation, so the budget's end is a 503."""
        subject = "e2e-claim-registered-apple-unavailable"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        scripted_devicecheck_adapter.script(
            RetryableDeviceCheckError("scripted transport failure"))

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 503, refusal.text
        assert refusal.json() == {"code": "verification_temporarily_unavailable"}
        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN] * DEVICECHECK_ATTEMPTS
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        assert (await _identity_of(_db_transaction, subject)).free_grant_consumed_at is None
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None
