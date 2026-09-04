"""The six attribution outcomes of one store notification, driven through the service over a stub session.

Each case asserts the values the writer was asked to persist, never the statements it emitted.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid7

import pytest

from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.crud.subscriptions import WriteOutcome
from nativespeaker.api.errors import AttributionConflict
from nativespeaker.api.services.subscriptions import SubscriptionsService
from nativespeaker.api.tables import (
    PurchaseProvider,
    StorePurchase,
    Subscription,
    SubscriptionStatus,
)

# The map the deployment configures; only the mapped product reaches a write.
PRODUCTS = {"com.nativespeaker.subscription.monthly": "paid"}

PAID_TIER_ID = "paid"

# One obviously synthetic attribution token, and a second that disagrees with it.
TOKEN = "a-synthetic-attribution-token"
OTHER_TOKEN = "a-different-synthetic-attribution-token"

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _notification(**overrides) -> VerifiedNotification:
    """One verified subscription notification; `overrides` replaces any field a case cares about."""
    fields = {"provider": PurchaseProvider.apple,
              "notification_uuid": f"uuid-{uuid4()}",
              "event_type": "SUBSCRIBED",
              "external_id": f"original-{uuid4()}",
              "transaction_id": f"txn-{uuid4()}",
              "product_id": "com.nativespeaker.subscription.monthly",
              "attribution_token": None,
              "purchased_at": NOW,
              "expires_at": NOW + timedelta(days=30),
              "revoked_at": None,
              "grace_period_expires_at": None,
              "in_billing_retry": False}
    return VerifiedNotification(**(fields | overrides))


class _StubSession:
    """Records the transaction boundaries and refuses queries: a query here means a read ran unstubbed."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def exec(self, statement):
        raise AssertionError(f"the ingestion path issued a query of its own: {statement!r}")


class _RecordingSubscriptions:
    """Stands in for the subscription crud calls, keyed as the two tables' unique indexes key them."""

    def __init__(self) -> None:
        self.events: dict[str, dict] = {}
        self.purchases: dict[tuple[PurchaseProvider, str], StorePurchase] = {}
        self.subscriptions: dict[tuple[PurchaseProvider, str], Subscription] = {}
        self.inserted: list[dict] = []
        self.upserts: list[dict] = []
        self.appended: list[dict] = []

    async def read_event(self, notification_uuid: str) -> dict | None:
        return self.events.get(notification_uuid)

    async def read_purchase(self, provider: PurchaseProvider,
                            external_id: str) -> StorePurchase | None:
        return self.purchases.get((provider, external_id))

    async def read_subscription(self, provider: PurchaseProvider,
                                external_id: str) -> Subscription | None:
        return self.subscriptions.get((provider, external_id))

    async def upsert_subscription(self, **fields) -> tuple[Subscription, WriteOutcome]:
        self.upserts.append(fields)
        key = (fields["provider"], fields["external_id"])
        stored = self.subscriptions.get(key)
        if stored is None:
            stored = Subscription(provider=fields["provider"],
                                  external_id=fields["external_id"],
                                  user_id=fields["user_id"],
                                  tier_id=fields["tier_id"],
                                  status=fields["status"],
                                  created_at=fields["evaluated_at"],
                                  updated_at=fields["evaluated_at"])
            self.subscriptions[key] = stored
        else:
            # The same rule the crud holds: an owner is added, never cleared.
            stored.user_id = stored.user_id if fields["user_id"] is None else fields["user_id"]
            stored.tier_id = fields["tier_id"]
            stored.status = fields["status"]
        return stored, WriteOutcome.applied

    async def insert_purchase(self, **fields) -> WriteOutcome:
        self.inserted.append(fields)
        self.purchases[(fields["provider"], fields["external_id"])] = StorePurchase(
            provider=fields["provider"],
            identity_value=fields["identity_value"],
            external_id=fields["external_id"],
            store_transaction_id=fields["store_transaction_id"],
            store_original_transaction_id=fields["store_original_transaction_id"],
            purchase_user_id=fields["purchase_user_id"],
            resolved_token_value=fields["resolved_token_value"],
            created_at=fields["evaluated_at"])
        return WriteOutcome.applied

    async def append_event(self, **fields) -> WriteOutcome:
        self.appended.append(fields)
        self.events[fields["notification_uuid"]] = fields
        return WriteOutcome.applied


class _RecordingPurchases:
    """Stands in for the inverse token read, answering with one binding or with none."""

    def __init__(self, bound: UUID | None = None) -> None:
        self.bound = bound
        self.calls: list[tuple[PurchaseProvider, str]] = []

    async def resolve_user(self, provider: PurchaseProvider, identity_value: str) -> UUID | None:
        self.calls.append((provider, identity_value))
        return self.bound


@pytest.fixture
def session() -> _StubSession:
    return _StubSession()


@pytest.fixture
def writer() -> _RecordingSubscriptions:
    return _RecordingSubscriptions()


def _service(session, writer, bound: UUID | None) -> SubscriptionsService:
    """The real service over the two recording crud stands-in, so its own arms are what runs."""
    service = SubscriptionsService(db=session, evaluated_at=NOW, products=PRODUCTS)
    service.subscriptions_db = writer
    service.purchases_db = _RecordingPurchases(bound)
    return service


@pytest.mark.asyncio
class TestTheSinglePurchaseArms:
    """The three shapes one delivery can take: attributed, token bound to nobody, and no token at all."""

    @pytest.mark.parametrize("token,bound", [
        (TOKEN, uuid7()),
        (TOKEN, None),
        (None, None),
    ], ids=["attributed", "token_resolves_to_nothing", "no_token_at_all"])
    async def test_each_shape_writes_exactly_one_purchase_row(self, session, writer, token, bound):
        service = _service(session, writer, bound)

        await service.ingest(_notification(attribution_token=token))

        assert len(writer.inserted) == 1
        assert len(writer.upserts) == 1
        assert len(writer.appended) == 1
        assert session.commits == 1

    async def test_the_attributed_shape_carries_the_owner_and_the_resolved_token(self,
                                                                                session, writer):
        """The attributed half of the table's CHECK: the resolved value is exactly the identity value."""
        owner = uuid7()
        service = _service(session, writer, owner)

        await service.ingest(_notification(attribution_token=TOKEN))

        purchase = writer.inserted[0]
        assert purchase["identity_value"] == TOKEN
        assert purchase["resolved_token_value"] == TOKEN
        assert purchase["purchase_user_id"] == owner
        assert writer.upserts[0]["user_id"] == owner

    async def test_a_token_bound_to_nobody_records_the_purchase_unowned(self, session, writer):
        """An unattributed purchase is recorded honestly; restore is the only path that links it later."""
        service = _service(session, writer, None)

        await service.ingest(_notification(attribution_token=TOKEN))

        purchase = writer.inserted[0]
        assert purchase["identity_value"] == TOKEN
        assert purchase["resolved_token_value"] is None
        assert purchase["purchase_user_id"] is None
        assert writer.upserts[0]["user_id"] is None

    async def test_no_token_at_all_generates_the_identity_value(self, session, writer):
        """The other half of the CHECK: `identity_value` is NOT NULL, so the server mints one."""
        service = _service(session, writer, None)

        await service.ingest(_notification(attribution_token=None))

        purchase = writer.inserted[0]
        assert purchase["resolved_token_value"] is None
        assert purchase["purchase_user_id"] is None
        # A valid UUID string, never an empty one: `UUID()` raises on anything else.
        assert UUID(purchase["identity_value"])

    async def test_no_token_at_all_reads_no_binding(self, session, writer):
        """The read is skipped entirely: an absent token has nothing to resolve."""
        service = _service(session, writer, None)

        await service.ingest(_notification(attribution_token=None))

        assert service.purchases_db.calls == []

    async def test_the_owner_is_resolved_before_the_first_write(self, session, writer):
        """D-16: the token read happens before the transaction writes, so it never runs under a lock."""
        service = _service(session, writer, uuid7())

        await service.ingest(_notification(attribution_token=TOKEN))

        assert service.purchases_db.calls == [(PurchaseProvider.apple, TOKEN)]


@pytest.mark.asyncio
class TestTheRepeatArms:
    """One purchase row per lifecycle key: a repeat adds none, and a new key adds one."""

    async def test_a_repeat_under_the_same_token_writes_no_second_purchase_row(self,
                                                                              session, writer):
        """D-19: the canonical subscription row still updates in place, and the purchase row does not repeat."""
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id,
                                           event_type="DID_RENEW"))

        assert len(writer.inserted) == 1
        assert len(writer.upserts) == 2
        assert len(writer.appended) == 2

    async def test_a_new_external_id_under_the_same_token_writes_a_new_purchase_row(self,
                                                                                   session, writer):
        """A second subscription bought by one account is a second lifecycle key, so it is a second row."""
        service = _service(session, writer, uuid7())

        await service.ingest(_notification(attribution_token=TOKEN))
        await service.ingest(_notification(attribution_token=TOKEN))

        assert len(writer.inserted) == 2
        assert {purchase["identity_value"] for purchase in writer.inserted} == {TOKEN}
        assert len({purchase["external_id"] for purchase in writer.inserted}) == 2


@pytest.mark.asyncio
class TestTheConflictArm:
    """T-43-07: a purchase whose attribution changed is refused, because a wrong owner cannot be undone."""

    async def test_a_changed_attribution_raises_and_writes_nothing_further(self, session, writer):
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        with pytest.raises(AttributionConflict):
            await service.ingest(_notification(attribution_token=OTHER_TOKEN,
                                               external_id=external_id))

        assert len(writer.inserted) == 1
        assert len(writer.upserts) == 1
        assert len(writer.appended) == 1
        assert session.commits == 1

    async def test_the_recorded_identity_value_is_left_alone(self, session, writer):
        """Refused, never repaired: the stored attribution is what the first delivery wrote."""
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        with pytest.raises(AttributionConflict):
            await service.ingest(_notification(attribution_token=OTHER_TOKEN,
                                               external_id=external_id))

        stored = writer.purchases[(PurchaseProvider.apple, external_id)]
        assert stored.identity_value == TOKEN

    async def test_the_refusal_carries_the_lifecycle_key_and_not_the_token(self, session, writer):
        """T-43-06: the two fields an operator needs, and the attribution token is not one of them."""
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        with pytest.raises(AttributionConflict) as refusal:
            await service.ingest(_notification(attribution_token=OTHER_TOKEN,
                                               external_id=external_id))

        assert refusal.value.log_fields() == {"provider": "apple", "external_id": external_id}
        assert TOKEN not in repr(refusal.value.log_fields())
        assert OTHER_TOKEN not in repr(refusal.value.log_fields())

    async def test_a_later_delivery_without_a_token_is_no_conflict(self, session, writer):
        """A notification presenting nothing disagrees with nothing, so an attributed row survives it."""
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        await service.ingest(_notification(attribution_token=None, external_id=external_id))

        assert len(writer.inserted) == 1
        assert writer.subscriptions[(PurchaseProvider.apple, external_id)].user_id is not None


@pytest.mark.asyncio
class TestTheMeasurementFires:
    """The controls: a recording stand-in that quietly recorded nothing would pass every count above."""

    async def test_the_recorder_counts_the_rows_a_successful_ingest_writes(self, session, writer):
        service = _service(session, writer, uuid7())

        await service.ingest(_notification(attribution_token=TOKEN))

        assert [len(writer.inserted), len(writer.upserts), len(writer.appended)] == [1, 1, 1]

    async def test_a_notification_with_no_transaction_part_reaches_no_arm_at_all(self,
                                                                                session, writer):
        """The control's mirror: the counts really do fall to zero when nothing is written."""
        service = _service(session, writer, uuid7())

        await service.ingest(_notification(external_id=None, product_id=None, event_type="TEST"))

        assert [len(writer.inserted), len(writer.upserts), len(writer.appended)] == [0, 0, 0]
        assert session.commits == 0

    async def test_the_status_written_is_the_one_the_dates_earn(self, session, writer):
        """A revoked term is recorded revoked, so the upsert really carries a derived value."""
        service = _service(session, writer, uuid7())

        await service.ingest(_notification(attribution_token=TOKEN, revoked_at=NOW))

        assert writer.upserts[0]["status"] is SubscriptionStatus.revoked
        assert writer.upserts[0]["tier_id"] == PAID_TIER_ID
