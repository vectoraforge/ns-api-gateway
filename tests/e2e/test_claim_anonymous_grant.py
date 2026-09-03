"""The anonymous device-grant claim, end to end through the real router against a real database."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, NativeClaimProvider

from .conftest import seed_grant, seed_identity

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-claim-anonymous-subject"

# One token, naming the device the read and the write both act on.
DEVICE_TOKEN = "device-token-tracer"


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
                                              "device_token": DEVICE_TOKEN},
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

        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN]
        # The update carried the query's bit1 forward, set only bit0, and named the device that was read.
        assert scripted_devicecheck_adapter.write_calls == [(DEVICE_TOKEN, True, False)]

        async with _db_transaction() as session:
            grants = (await session.exec(
                select(AccessGrant).where(col(AccessGrant.user_id) == user.id))).all()
            assert len(grants) == 1
            grant = grants[0]
            assert grant.source is AccessGrantSource.anonymous_device_grant
            assert grant.tier_id == "anonymous"
            assert grant.subscription_id is None

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


# The one body every refusal answers with, compared by equality so a more helpful field fails here.
REFUSED = {"code": "operation_not_allowed"}

# The same body as bytes, so a refusal is compared on the wire and not only after parsing.
REFUSED_BODY = '{"code":"operation_not_allowed"}'

# An hour back, because `CHECK (ends_at IS NULL OR ends_at > starts_at)` is strict.
SEEDED_AGO = timedelta(hours=1)

# A minute back, so a row seeded with it is marked active and its term is already over.
LAPSED_AGO = timedelta(minutes=1)


async def _issue(client, subject: str) -> str:
    """Obtain a claim handle for `subject`, which every case below spends exactly once."""
    issued = await client.post("/auth/challenge",
                               json={"operation": "claim_anonymous_grant"},
                               headers=_auth(subject))
    assert issued.status_code == 200, issued.text
    return issued.json()["challenge_id"]


async def _claim(client, subject: str, handle: str, *, device_token: str = DEVICE_TOKEN):
    return await client.post("/auth/claim-anonymous-grant",
                             json={"challenge_id": handle, "device_token": device_token},
                             headers=_auth(subject))


async def _challenge_for(factory, handle: str) -> AuthChallenge:
    async with factory() as session:
        return (await session.exec(
            select(AuthChallenge).where(col(AuthChallenge.challenge_id) == handle))).one()


async def _row_counts(factory, user_id) -> tuple[int, int]:
    """The grant and usage row counts for `user_id`: the two kinds a claim writes."""
    async with factory() as session:
        grants = (await session.exec(
            select(AccessGrant).where(col(AccessGrant.user_id) == user_id))).all()
        ids = [grant.id for grant in grants]
        usage = (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id).in_(ids or [uuid4()])))).all()
        return len(grants), len(usage)


async def _grants_of(factory, user_id) -> list[AccessGrant]:
    """Every grant row of `user_id`, in the same ascending order the writer locks them."""
    async with factory() as session:
        return list((await session.exec(
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id)
            .order_by(col(AccessGrant.id).asc()))).all())


async def _identity_of(factory, subject: str) -> ExternalIdentity:
    async with factory() as session:
        return (await session.exec(
            select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                           col(ExternalIdentity.subject) == subject))).one()


async def _mark_free_grant_consumed(factory, subject: str) -> None:
    """Set the lifetime marker on the seeded identity row, which only this phase's writer sets."""
    async with factory() as session:
        row = (await session.exec(
            select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                           col(ExternalIdentity.subject) == subject))).one()
        row.free_grant_consumed_at = datetime.now(UTC)
        session.add(row)
        await session.commit()


@pytest.mark.asyncio(loop_scope="module")
class TestTheRepeatIsIdempotent:
    """D-09: an account already holding an active anonymous grant claims again and gets the same body."""

    async def test_a_repeat_answers_the_fresh_claim_body_writes_nothing_and_never_reaches_apple(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        subject = "e2e-claim-repeat"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)

        first = await _claim(claim_client, subject, await _issue(claim_client, subject))
        assert first.status_code == 200, first.text
        after_first = await _row_counts(_db_transaction, user.id)
        assert after_first == (1, 1)

        # Cleared rather than re-created: the repeat's own call count is what the next assertion reads.
        scripted_devicecheck_adapter.read_calls.clear()
        scripted_devicecheck_adapter.write_calls.clear()

        handle = await _issue(claim_client, subject)
        repeat = await _claim(claim_client, subject, handle)

        assert repeat.status_code == 200, repeat.text
        assert repeat.headers["Cache-Control"] == "no-store"
        # The same body a fresh claim returns, by equality: the repeat is not a differently-shaped answer.
        assert repeat.json() == first.json()
        # The preflight ran before Apple rather than after, which is what these two empty lists prove.
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == after_first
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestTheFourRefusals:
    """One body, four classes, and not one of them costs an Apple round trip (D-03, D-09, D-08)."""

    async def test_a_consumed_marker_with_no_active_grant_is_refused(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """The lifetime rule read off the marker alone: no grant row survives to be found."""
        subject = "e2e-claim-marker-set"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)
        await _mark_free_grant_consumed(_db_transaction, subject)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_a_revoked_free_grant_is_refused_because_the_read_carries_no_status_predicate(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """Revocation never reopens the slot: the preflight and the lifetime index agree by construction."""
        subject = "e2e-claim-revoked-free-grant"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)
        await seed_grant(_db_transaction, user_id=user.id, tier_id="anonymous",
                         source=AccessGrantSource.anonymous_device_grant,
                         status=AccessGrantStatus.revoked)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        # The revoked row and its anti-abuse row are still the only ones: nothing was written.
        assert await _row_counts(_db_transaction, user.id) == (1, 1)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_an_active_grant_of_another_source_is_refused(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """One user holds at most one active grant, so a manual grant refuses the claim."""
        subject = "e2e-claim-other-source-held"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)
        await seed_grant(_db_transaction, user_id=user.id,
                         source=AccessGrantSource.manual, status=AccessGrantStatus.active)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (1, 1)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_a_registered_caller_is_refused_and_waits_for_phase_42(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """D-08: the stored provider column is the sole classifier, and it decides before Apple."""
        subject = "e2e-claim-registered-caller"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == REFUSED
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        # Decided after the claim, because the claimant check is the first thing the post-claim work does.
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestARowMarkedActiveOutsideItsTermIsRefusedBeforeApple:
    """CR-01. `ix_access_grants_one_active_per_user` carries no time window, so a row whose term has
    passed still holds the one active slot and still refuses the insert this claim would make."""

    async def test_a_term_lapsed_active_grant_is_refused_and_no_bit_is_read_or_written(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        subject = "e2e-claim-anonymous-lapsed-active"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)
        now = datetime.now(UTC)
        await seed_grant(_db_transaction, user_id=user.id, source=AccessGrantSource.manual,
                         status=AccessGrantStatus.active,
                         starts_at=now - SEEDED_AGO, ends_at=now - LAPSED_AGO)
        before = (await _grants_of(_db_transaction, user.id))[0]

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.text == REFUSED_BODY
        assert refusal.json() == REFUSED
        # The one-way bit is the thing protected here: a fix that still spends it fails on these two.
        assert scripted_devicecheck_adapter.read_calls == []
        assert scripted_devicecheck_adapter.write_calls == []
        after = await _grants_of(_db_transaction, user.id)
        assert [grant.id for grant in after] == [before.id]
        assert (after[0].status, after[0].ends_at, after[0].updated_at) == (before.status,
                                                                            before.ends_at,
                                                                            before.updated_at)
        assert (await _identity_of(_db_transaction, subject)).free_grant_consumed_at is None
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None


@pytest.mark.asyncio(loop_scope="module")
class TestTheThreeAppleFailureArms:
    """An eligible account reaches Apple, and each of its three refusing answers writes nothing (D-06)."""

    async def test_a_device_whose_bit0_is_already_set_is_exhausted_and_is_never_written_to(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        subject = "e2e-claim-device-spent"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)
        scripted_devicecheck_adapter.script(BitState(bit0=True, bit1=False))

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        # No device state in the body: the copy directs to the registered path and discloses nothing.
        assert refusal.json() == {"code": "device_grant_exhausted"}
        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN]
        # The slot is spent, so the write that would spend it again is never attempted.
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_a_token_apple_refuses_is_a_proof_rejection(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        subject = "e2e-claim-token-refused"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)
        scripted_devicecheck_adapter.script(ProofRejected(stage="devicecheck_read", cause="rejected"))

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 403, refusal.text
        assert refusal.json() == {"code": "proof_rejected"}
        # Definitive, so it spends one attempt of the budget rather than all three.
        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN]
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None

    async def test_an_exhausted_apple_budget_is_temporarily_unavailable_and_writes_nothing(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter):
        """Fail-closed: only Apple's explicit confirmation permits activation, so the budget's end is a 503."""
        subject = "e2e-claim-apple-unavailable"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.anonymous)
        scripted_devicecheck_adapter.script(RetryableDeviceCheckError("scripted transport failure"))

        handle = await _issue(claim_client, subject)
        refusal = await _claim(claim_client, subject, handle)

        assert refusal.status_code == 503, refusal.text
        assert refusal.json() == {"code": "verification_temporarily_unavailable"}
        assert scripted_devicecheck_adapter.read_calls == [DEVICE_TOKEN] * DEVICECHECK_ATTEMPTS
        assert scripted_devicecheck_adapter.write_calls == []
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None
