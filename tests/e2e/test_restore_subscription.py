"""The same-account Apple restore, end to end through the real router against a real database."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.tables.grants import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    UserMonthlyUsage,
)
from nativespeaker.api.tables.identities import IdentityProvider
from nativespeaker.api.tables.purchases import PurchaseProvider, SubscriptionStatus

from .conftest import seed_identity, seed_subscription

pytestmark = pytest.mark.e2e

SUBJECT = "tracer-restore-subscription-subject"

# The artifact the client presents; the seam is scripted, so its content is never parsed here.
RESTORE_PROOF = "a-signed-transaction-the-scripted-seam-accepts"

# The tier the migration seeds for a paid subscription, which the proof's product maps to.
PAID_TIER_ID = "paid"

# The same body as bytes, so the gate refusal is compared on the wire and not after parsing.
REFUSED_BODY = '{"code":"operation_not_allowed"}'

# A month out, so the written term is unambiguously open at the instant every case runs.
TERM_REMAINING = timedelta(days=30)

# An hour back, because `CHECK (ends_at IS NULL OR ends_at > starts_at)` is strict.
PURCHASED_AGO = timedelta(hours=1)


@pytest_asyncio.fixture(loop_scope="module")
async def restore_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


def _proof(external_id: str, *, status: SubscriptionStatus = SubscriptionStatus.active
           ) -> RestoredSubscription:
    """What the Apple check reports for this case, in the value type the seam returns."""
    now = datetime.now(UTC)
    return RestoredSubscription(provider=PurchaseProvider.apple,
                                external_id=external_id,
                                product_id="com.nativespeaker.subscription.monthly",
                                tier_id=PAID_TIER_ID,
                                attribution_token=None,
                                status=status,
                                purchased_at=now - PURCHASED_AGO,
                                expires_at=now + TERM_REMAINING,
                                grace_period_expires_at=None)


async def _restore(client, subject: str = SUBJECT, **body):
    """Present one restore proof; `body` replaces the default two fields wholesale."""
    payload = body or {"provider": "apple", "restore_proof": RESTORE_PROOF}
    return await client.post("/auth/restore-subscription", json=payload, headers=_auth(subject))


async def _grants_of(factory, user_id) -> list[AccessGrant]:
    """Every grant row of `user_id`, in the same ascending order the writer locks them."""
    async with factory() as session:
        return list((await session.exec(
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id)
            .order_by(col(AccessGrant.id).asc()))).all())


async def _usage_of(factory, grant_id) -> UserMonthlyUsage:
    async with factory() as session:
        return (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id))).one()


async def _spend(factory, grant_id, used: int) -> None:
    """Charge the grant's counter, so a reset by a repeat restore is visible rather than invisible."""
    async with factory() as session:
        usage = (await session.exec(
            select(UserMonthlyUsage)
            .where(col(UserMonthlyUsage.grant_id) == grant_id))).one()
        usage.monthly_used = used
        session.add(usage)
        await session.commit()


@pytest.mark.asyncio(loop_scope="module")
class TestTheSameAccountAppleRestore:
    """The one path this slice serves: the caller's account already owns the subscription named."""

    async def test_a_verified_proof_attaches_the_paid_grant_and_the_body_reports_it(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-restore-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        answered = await _restore(restore_client)

        assert answered.status_code == 200, answered.text
        body = answered.json()
        assert body["entitlement"]["type"] == "subscription"
        assert body["entitlement"]["status"] == "active"
        assert body["entitlement"]["tier_id"] == PAID_TIER_ID
        assert body["identity_provider"] == "google"
        assert answered.headers["Cache-Control"] == "no-store"

    async def test_the_one_grant_it_wrote_is_the_subscription_grant_and_its_usage_row(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-restore-{uuid4()}"
        subscription_id = await seed_subscription(_db_transaction, external_id=external_id,
                                                  user_id=user.id, tier_id=PAID_TIER_ID)
        scripted_app_store_notifications.script_restore(_proof(external_id))

        assert (await _restore(restore_client)).status_code == 200

        grants = await _grants_of(_db_transaction, user.id)
        assert len(grants) == 1
        assert grants[0].source is AccessGrantSource.subscription
        assert grants[0].status is AccessGrantStatus.active
        assert grants[0].subscription_id == subscription_id
        assert (await _usage_of(_db_transaction, grants[0].id)).monthly_used == 0

    async def test_a_repeat_restore_writes_no_new_row_and_resets_no_counter(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        """D-07: the same term and tier is a replay, so the paid month's counter survives it."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-restore-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        proof = _proof(external_id)
        scripted_app_store_notifications.script_restore(proof)
        assert (await _restore(restore_client)).status_code == 200
        first = (await _grants_of(_db_transaction, user.id))[0]
        await _spend(_db_transaction, first.id, 7)

        # The identical proof a second time: the same term, so the writer answers `replayed`.
        scripted_app_store_notifications.script_restore(proof)
        repeated = await _restore(restore_client)

        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["entitlement"]["monthly_used"] == 7
        grants = await _grants_of(_db_transaction, user.id)
        assert [grant.id for grant in grants] == [first.id]
        assert (await _usage_of(_db_transaction, first.id)).monthly_used == 7


@pytest.mark.asyncio(loop_scope="module")
class TestTheSurfaceGateIsTheStoreNameAndTheProof:
    """RESTORE-02, D-01, D-02: a caller naming no store this deployment serves is refused here."""

    async def test_a_store_the_server_does_not_serve_is_refused_before_any_proof_check(
            self, restore_client, _db_transaction, scripted_app_store_notifications):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)

        refused = await _restore(restore_client, provider="web", restore_proof=RESTORE_PROOF)

        assert refused.status_code == 403
        # Compared as bytes, so a more helpful field on this body fails here.
        assert refused.text == REFUSED_BODY
        assert scripted_app_store_notifications.restore_calls == []

    async def test_an_empty_store_name_is_the_frameworks_own_refusal(
            self, restore_client, _db_transaction):
        """D-01: both fields are required and non-empty, so an empty one never reaches the handler."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                            provider=IdentityProvider.google)

        refused = await _restore(restore_client, provider="", restore_proof=RESTORE_PROOF)

        assert refused.status_code == 422
