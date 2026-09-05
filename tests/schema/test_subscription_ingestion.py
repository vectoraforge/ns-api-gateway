"""What one ingested notification leaves behind on real PostgreSQL: the term, the renewal, the free
grant, the non-entitled transition, the unattributed path and the replay."""
import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.services.subscriptions import SubscriptionsService
from nativespeaker.api.tables import PurchaseProvider
from schema.helpers import (
    insert_store_purchase,
    insert_subscription,
    insert_tier,
    insert_usage,
    insert_user,
)

pytestmark = pytest.mark.schema

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

# The one product this deployment maps; an unmapped id never reaches a write.
PRODUCT_ID = "com.nativespeaker.subscription.monthly"

_A_MONTH = timedelta(days=30)


def _notification(*, external_id: str, token: str | None, purchased_at: datetime,
                  expires_at: datetime | None, revoked_at: datetime | None = None,
                  signed_at: datetime | None = None,
                  notification_uuid: str | None = None) -> VerifiedNotification:
    """One verified notification carrying the transaction part every write needs."""
    return VerifiedNotification(
        provider=PurchaseProvider.apple,
        notification_uuid=notification_uuid or f"notification-{uuid.uuid4()}",
        event_type="DID_RENEW",
        external_id=external_id,
        transaction_id=f"transaction-{uuid.uuid4().hex[:12]}",
        product_id=PRODUCT_ID,
        attribution_token=token,
        # The purchase instant unless a case places it: two deliveries otherwise share one signing date.
        signed_at=purchased_at if signed_at is None else signed_at,
        purchased_at=purchased_at,
        expires_at=expires_at,
        revoked_at=revoked_at,
        grace_period_expires_at=None,
        in_billing_retry=False)


async def _seed_grant(conn: asyncpg.Connection, *, user_id: uuid.UUID, tier_id: str, source: str,
                      starts_at: datetime, subscription_id: uuid.UUID | None = None) -> uuid.UUID:
    """Seed one active grant with its usage row, placing its term where the case needs it."""
    grant_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO core.access_grants (id, user_id, tier_id, source, status, subscription_id, starts_at) "
        "VALUES ($1, $2, $3, $4, 'active', $5, $6)",
        grant_id, user_id, tier_id, source, subscription_id, starts_at)
    await insert_usage(conn, grant_id=grant_id)
    return grant_id


@dataclass(frozen=True)
class _Buyer:
    """A seeded account with its store token, a session factory, and a probe for committed reads."""

    factory: async_sessionmaker
    probe: asyncpg.Connection
    user_id: uuid.UUID | None
    tier_id: str
    token: str | None
    external_id: str
    evaluated_at: datetime

    async def ingest(self, notification: VerifiedNotification) -> None:
        """Drive one delivery through the real service on its own session, as one request would."""
        async with self.factory() as session:
            await SubscriptionsService(db=session, evaluated_at=self.evaluated_at,
                                       products={PRODUCT_ID: self.tier_id}).ingest(notification)

    async def deliver(self, *, external_id: str | None = None, expires_in: timedelta | None = _A_MONTH,
                      purchased_before: timedelta = _A_MONTH, revoked: bool = False,
                      signed_at: datetime | None = None,
                      notification_uuid: str | None = None) -> None:
        """Ingest one notification for this buyer, with its term placed around the captured instant."""
        await self.ingest(_notification(
            external_id=external_id or self.external_id,
            token=self.token,
            purchased_at=self.evaluated_at - purchased_before,
            expires_at=None if expires_in is None else self.evaluated_at + expires_in,
            revoked_at=self.evaluated_at - timedelta(hours=1) if revoked else None,
            signed_at=signed_at,
            notification_uuid=notification_uuid))

    async def grants(self) -> list[asyncpg.Record]:
        """Every committed grant on this case's tier, oldest first."""
        return await self.probe.fetch(
            "SELECT id, source::text AS source, status::text AS status, subscription_id, tier_id, "
            "starts_at, ends_at, updated_at FROM core.access_grants WHERE tier_id = $1 "
            "ORDER BY created_at ASC, id ASC", self.tier_id)

    async def usage(self, grant_id: uuid.UUID) -> asyncpg.Record | None:
        """The committed usage row of one grant, or None."""
        return await self.probe.fetchrow(
            "SELECT monthly_period, monthly_used FROM core.user_monthly_usage WHERE grant_id = $1",
            grant_id)

    async def counts(self) -> tuple[int, ...]:
        """Committed row counts of the four tables one delivery writes, keyed on this case's tier."""
        return tuple(await self.probe.fetchrow(
            "SELECT (SELECT count(*) FROM core.subscriptions WHERE tier_id = $1), "
            "(SELECT count(*) FROM core.access_grants WHERE tier_id = $1), "
            "(SELECT count(*) FROM core.user_monthly_usage u JOIN core.access_grants g "
            "  ON g.id = u.grant_id WHERE g.tier_id = $1), "
            "(SELECT count(*) FROM audit.subscription_events e JOIN core.subscriptions s "
            "  ON s.id = e.subscription_id WHERE s.tier_id = $1)", self.tier_id))

    async def signed_at(self, external_id: str | None = None) -> datetime | None:
        """The committed store clock on one lifecycle key's subscription row."""
        return await self.probe.fetchval(
            "SELECT store_signed_at FROM core.subscriptions WHERE provider = 'apple' "
            "AND external_id = $1", external_id or self.external_id)

    async def subscription_id(self, external_id: str | None = None) -> uuid.UUID:
        """The committed subscription id for one lifecycle key."""
        return await self.probe.fetchval(
            "SELECT id FROM core.subscriptions WHERE provider = 'apple' AND external_id = $1",
            external_id or self.external_id)


async def _clean(conn: asyncpg.Connection, *, user_id: uuid.UUID | None, tier_id: str) -> None:
    """Remove every row a case wrote, child-first, because core.users is referenced with RESTRICT."""
    await conn.execute("DELETE FROM audit.subscription_events WHERE subscription_id IN "
                       "(SELECT id FROM core.subscriptions WHERE tier_id = $1)", tier_id)
    await conn.execute("DELETE FROM core.store_purchases WHERE external_id IN "
                       "(SELECT external_id FROM core.subscriptions WHERE tier_id = $1)", tier_id)
    await conn.execute("DELETE FROM core.user_monthly_usage WHERE grant_id IN "
                       "(SELECT id FROM core.access_grants WHERE tier_id = $1)", tier_id)
    await conn.execute("DELETE FROM core.access_grants WHERE tier_id = $1", tier_id)
    await conn.execute("DELETE FROM core.subscriptions WHERE tier_id = $1", tier_id)
    if user_id is not None:
        await conn.execute("DELETE FROM core.store_purchase_tokens WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM core.users WHERE id = $1", user_id)
    await conn.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)


@contextlib.asynccontextmanager
async def _buyer(schema_db_uri: str, *, attributed: bool = True):
    """Seed one account and its throwaway tier, and yield the handle every case drives."""
    token = f"token-{uuid.uuid4()}" if attributed else None
    user_id = None

    setup = await asyncpg.connect(schema_db_uri)
    try:
        tier_id = await insert_tier(setup)
        if attributed:
            user_id = await insert_user(setup)
            await setup.execute(
                "INSERT INTO core.store_purchase_tokens (user_id, provider, identity_value) "
                "VALUES ($1, 'apple', $2)", user_id, token)
    finally:
        await setup.close()

    engine = create_async_engine(schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    probe = await asyncpg.connect(schema_db_uri)
    try:
        yield _Buyer(factory=async_sessionmaker(engine, class_=SQLModelAsyncSession,
                                                expire_on_commit=False),
                     probe=probe, user_id=user_id, tier_id=tier_id, token=token,
                     external_id=f"original-{uuid.uuid4().hex[:12]}",
                     evaluated_at=datetime.now(UTC))
    finally:
        await probe.close()
        await engine.dispose()
        cleanup = await asyncpg.connect(schema_db_uri)
        try:
            await _clean(cleanup, user_id=user_id, tier_id=tier_id)
        finally:
            await cleanup.close()


@pytest.mark.asyncio
class TestTheFirstTermIsWritten:
    """APPLEHOOK-01, D-15. The term the notification carries becomes the grant's own term."""

    async def test_the_paid_grant_carries_the_term_and_the_mapped_tier(self, _schema_db_uri):
        async with _buyer(_schema_db_uri) as buyer:
            await buyer.deliver()

            held = await buyer.grants()
            assert [(row["source"], row["status"]) for row in held] == [("subscription", "active")]
            assert held[0]["tier_id"] == buyer.tier_id
            assert held[0]["subscription_id"] == await buyer.subscription_id()
            assert held[0]["starts_at"] == buyer.evaluated_at - _A_MONTH
            assert held[0]["ends_at"] == buyer.evaluated_at + _A_MONTH

    async def test_the_fresh_usage_row_is_written_with_the_grant(self, _schema_db_uri):
        """The period is the captured instant's month, spelled as services/quota.py spells it."""
        async with _buyer(_schema_db_uri) as buyer:
            await buyer.deliver()

            usage = await buyer.usage((await buyer.grants())[0]["id"])
            assert usage is not None
            assert usage["monthly_used"] == 0
            assert usage["monthly_period"] == buyer.evaluated_at.strftime("%Y-%m")

    async def test_the_store_signing_instant_is_kept_on_the_subscription_row(self, _schema_db_uri):
        """The store's own clock, which is the value the out-of-order guard compares."""
        async with _buyer(_schema_db_uri) as buyer:
            signed = buyer.evaluated_at - timedelta(minutes=5)

            await buyer.deliver(signed_at=signed)

            assert await buyer.signed_at() == signed

    async def test_the_buyers_free_grant_is_expired_and_not_deleted(self, _schema_db_uri):
        """D-18. The lifetime slot is spent, so a later lapse leaves the buyer holding nothing."""
        async with _buyer(_schema_db_uri) as buyer:
            free = await _seed_grant(buyer.probe, user_id=buyer.user_id, tier_id=buyer.tier_id,
                                     source="anonymous_device_grant",
                                     starts_at=buyer.evaluated_at - timedelta(hours=1))
            await buyer.deliver()

            held = {row["id"]: row for row in await buyer.grants()}
            assert len(held) == 2
            assert held[free]["status"] == "expired"
            assert held[free]["ends_at"] == buyer.evaluated_at
            assert await buyer.usage(free) is not None


@pytest.mark.asyncio
class TestTheTermDecidesWhatIsWritten:
    """D-15. Same term is a no-op reached before any write; a later term is a renewal."""

    async def test_the_same_term_writes_nothing_to_either_table(self, _schema_db_uri):
        async with _buyer(_schema_db_uri) as buyer:
            await buyer.deliver()
            before = (await buyer.grants())[0]
            usage_before = await buyer.usage(before["id"])

            await buyer.deliver()

            held = await buyer.grants()
            assert [row["id"] for row in held] == [before["id"]]
            assert held[0]["status"] == "active"
            assert held[0]["updated_at"] == before["updated_at"]
            assert await buyer.usage(before["id"]) == usage_before

    async def test_a_renewal_expires_the_old_term_and_inserts_the_next(self, _schema_db_uri):
        """Both halves in one case: the superseded row is expired and the next term is active."""
        async with _buyer(_schema_db_uri) as buyer:
            await buyer.deliver()
            first = (await buyer.grants())[0]["id"]

            await buyer.deliver(expires_in=2 * _A_MONTH, purchased_before=timedelta(hours=2))

            held = {row["id"]: row for row in await buyer.grants()}
            assert len(held) == 2
            assert held[first]["status"] == "expired"
            assert held[first]["ends_at"] == buyer.evaluated_at
            next_term = next(row for key, row in held.items() if key != first)
            assert next_term["status"] == "active"
            assert next_term["ends_at"] == buyer.evaluated_at + 2 * _A_MONTH
            assert (await buyer.usage(next_term["id"]))["monthly_used"] == 0


@pytest.mark.asyncio
class TestLeavingTheEntitledSet:
    """D-18, D-19. Outside `active` and `grace_period` the buyer holds no grant at all."""

    async def test_an_ended_term_leaves_the_buyer_holding_no_grant(self, _schema_db_uri):
        async with _buyer(_schema_db_uri) as buyer:
            await buyer.deliver()

            await buyer.deliver(expires_in=-timedelta(minutes=1))

            held = await buyer.grants()
            assert [row["status"] for row in held] == ["expired"]
            assert held[0]["ends_at"] == buyer.evaluated_at

    async def test_a_withdrawn_purchase_marks_the_grant_revoked(self, _schema_db_uri):
        async with _buyer(_schema_db_uri) as buyer:
            await buyer.deliver()

            await buyer.deliver(revoked=True)

            assert [row["status"] for row in await buyer.grants()] == ["revoked"]


@pytest.mark.asyncio
class TestTheNewestPurchaseWins:
    """D-19. A second subscription for one buyer takes the same expire-then-insert path."""

    async def test_a_second_subscription_supersedes_the_first(self, _schema_db_uri):
        async with _buyer(_schema_db_uri) as buyer:
            await buyer.deliver()
            first = (await buyer.grants())[0]["id"]
            second_key = f"original-{uuid.uuid4().hex[:12]}"

            await buyer.deliver(external_id=second_key, purchased_before=timedelta(hours=2))

            held = {row["id"]: row for row in await buyer.grants()}
            assert held[first]["status"] == "expired"
            newest = next(row for key, row in held.items() if key != first)
            assert newest["status"] == "active"
            assert newest["subscription_id"] == await buyer.subscription_id(second_key)

    async def test_a_repeat_delivery_grants_the_term_and_writes_no_second_purchase_row(
            self, _schema_db_uri):
        """D-19 over a seeded prior delivery, so the purchase row predates the grant this writes."""
        async with _buyer(_schema_db_uri) as buyer:
            await insert_subscription(buyer.probe, external_id=buyer.external_id,
                                      tier_id=buyer.tier_id, user_id=buyer.user_id)
            await insert_store_purchase(buyer.probe, identity_value=buyer.token,
                                        external_id=buyer.external_id,
                                        purchase_user_id=buyer.user_id,
                                        resolved_token_value=buyer.token)

            await buyer.deliver()

            assert [row["status"] for row in await buyer.grants()] == ["active"]
            assert await buyer.probe.fetchval(
                "SELECT count(*) FROM core.store_purchases WHERE external_id = $1",
                buyer.external_id) == 1


@pytest.mark.asyncio
class TestNothingIsWrittenWithoutABuyerOrOnAReplay:
    """D-17, D-20. No user means no grant to hold; a recorded key means nothing to write."""

    async def test_an_unattributed_notification_writes_no_grant_and_no_usage_row(self,
                                                                                 _schema_db_uri):
        async with _buyer(_schema_db_uri, attributed=False) as buyer:
            await buyer.deliver()

            # The control: the subscription row proves the delivery ran rather than failing early.
            assert await buyer.counts() == (1, 0, 0, 1)

    async def test_a_replayed_notification_uuid_leaves_every_count_unchanged(self, _schema_db_uri):
        async with _buyer(_schema_db_uri) as buyer:
            replayed = f"notification-{uuid.uuid4()}"
            await buyer.deliver(notification_uuid=replayed)
            before = await buyer.counts()

            await buyer.deliver(expires_in=2 * _A_MONTH, notification_uuid=replayed)

            assert await buyer.counts() == before
            assert [row["ends_at"] for row in await buyer.grants()] == \
                [buyer.evaluated_at + _A_MONTH]


@pytest.mark.asyncio
class TestTheDeferrableForeignKeyIsTheBackstop:
    """The control on the transition above: without it, that case could pass with no constraint."""

    async def test_a_grant_left_active_fails_the_commit(self, _schema_db_uri):
        conn = await asyncpg.connect(_schema_db_uri)
        tier_id = await insert_tier(conn)
        user_id = await insert_user(conn)
        try:
            subscription_id = await insert_subscription(
                conn, external_id=f"original-{uuid.uuid4().hex[:12]}", tier_id=tier_id,
                user_id=user_id)
            await _seed_grant(conn, user_id=user_id, tier_id=tier_id, source="subscription",
                              starts_at=datetime.now(UTC) - timedelta(hours=1),
                              subscription_id=subscription_id)

            transaction = conn.transaction()
            await transaction.start()
            await conn.execute("UPDATE core.subscriptions SET status = 'expired' WHERE id = $1",
                               subscription_id)
            with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
                await transaction.commit()
        finally:
            await _clean(conn, user_id=user_id, tier_id=tier_id)
            await conn.close()
