"""The six attribution outcomes of one store notification, driven through the service over a stub session.

Each case asserts the values the writer was asked to persist, never the statements it emitted.
"""
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.crud.subscriptions import SubscriptionsDB, WriteOutcome
from nativespeaker.api.crud.violations import UNIQUE_VIOLATION
from nativespeaker.api.errors import AttributionConflict, InternalError
from nativespeaker.api.services.subscriptions import SubscriptionsService
from nativespeaker.api.tables import (
    PurchaseProvider,
    StorePurchase,
    Subscription,
    SubscriptionStatus,
)

PAID_TIER_ID = "paid"

OTHER_TIER_ID = "registered"

# One obviously synthetic attribution token, and a second that disagrees with it.
TOKEN = "a-synthetic-attribution-token"
OTHER_TOKEN = "a-different-synthetic-attribution-token"

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

# The two accounts of the D-09 case: the one a restore made the owner, and the one that bought it.
RESTORER = uuid7()
ORIGINAL_BUYER = uuid7()

DEFERRED_KEY_VIOLATION = "23503"


def _notification(**overrides) -> VerifiedNotification:
    """One verified subscription notification; `overrides` replaces any field a case cares about."""
    fields = {"provider": PurchaseProvider.apple,
              "notification_uuid": f"uuid-{uuid4()}",
              "event_type": "SUBSCRIBED",
              "external_id": f"original-{uuid4()}",
              "transaction_id": f"txn-{uuid4()}",
              "product_id": "com.nativespeaker.subscription.monthly",
              # Resolved in the provider's class before this value type exists, never by the service.
              "tier_id": PAID_TIER_ID,
              "attribution_token": None,
              "status": SubscriptionStatus.active,
              "signed_at": NOW,
              "purchased_at": NOW,
              "expires_at": NOW + timedelta(days=30),
              "grace_period_expires_at": None}
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


class _Orig(Exception):
    """The DBAPI exception SQLAlchemy wraps, carrying the one attribute the writer reads."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


class _RefusingSession(_StubSession):
    """The stub session whose commit raises what the deferred entitlement keys raise at COMMIT."""

    def __init__(self, sqlstate: str | None = DEFERRED_KEY_VIOLATION) -> None:
        super().__init__()
        self._orig = None if sqlstate is None else _Orig(sqlstate)

    async def commit(self) -> None:
        self.commits += 1
        raise IntegrityError("COMMIT", {}, self._orig)


class _UpsertResult:
    """One row and one row count: what the writer's read and its conditional owner update ask for."""

    def __init__(self, row: Subscription | None, rowcount: int = 1) -> None:
        self._row = row
        self.rowcount = rowcount

    def first(self) -> Subscription | None:
        return self._row


class _UpsertSession:
    """The one-row session `SubscriptionsDB.upsert_subscription` runs over, so this file measures
    against the real writer rather than a restatement of it."""

    def __init__(self, stored: Subscription | None, claim_wins: bool = True) -> None:
        self._stored = stored
        self._claim_wins = claim_wins
        self.added: list = []

    async def exec(self, statement) -> _UpsertResult:  # noqa: ARG002
        return _UpsertResult(self._stored, 1 if self._claim_wins else 0)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        return None


class _RecordingSubscriptions:
    """Stands in for the subscription crud calls, keyed as the two tables' unique indexes key them."""

    def __init__(self) -> None:
        self.timeline: list[str] = []
        self.events: dict[str, dict] = {}
        self.purchases: dict[tuple[PurchaseProvider, str], StorePurchase] = {}
        self.subscriptions: dict[tuple[PurchaseProvider, str], Subscription] = {}
        self.inserted: list[dict] = []
        self.upserts: list[dict] = []
        self.appended: list[dict] = []
        self.locked: list[UUID] = []
        self.granted: list[dict] = []
        self.settled_owner: UUID | None = None
        self.claim_wins = True
        self.rival: Callable[[], None] | None = None

    async def lock_grants(self, user_id: UUID) -> list:
        self.timeline.append("lock_grants")
        self.locked.append(user_id)
        return []

    async def read_owner(self, provider: PurchaseProvider, external_id: str) -> UUID | None:
        if self.settled_owner is not None:
            return self.settled_owner
        stored = self.subscriptions.get((provider, external_id))
        return None if stored is None else stored.user_id

    async def write_subscription_grant(self, **fields) -> WriteOutcome:
        self.timeline.append("write_subscription_grant")
        self.granted.append(fields)
        return WriteOutcome.applied

    async def read_event(self, notification_uuid: str) -> dict | None:
        return self.events.get(notification_uuid)

    async def read_purchase(self, provider: PurchaseProvider,
                            external_id: str) -> StorePurchase | None:
        return self.purchases.get((provider, external_id))

    async def read_subscription(self, provider: PurchaseProvider,
                                external_id: str) -> Subscription | None:
        stored = self.subscriptions.get((provider, external_id))
        if self.rival is not None:
            rival, self.rival = self.rival, None
            rival()
        return stored

    async def upsert_subscription(self, **fields) -> tuple[Subscription, WriteOutcome]:
        self.timeline.append("upsert_subscription")
        self.upserts.append(fields)
        key = (fields["provider"], fields["external_id"])
        session = _UpsertSession(self.subscriptions.get(key), self.claim_wins)
        stored, outcome = await SubscriptionsDB(session).upsert_subscription(**fields)
        self.subscriptions[key] = stored
        return stored, outcome

    async def insert_purchase(self, **fields) -> WriteOutcome:
        self.timeline.append("insert_purchase")
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
        self.timeline.append("append_event")
        self.appended.append(fields)
        self.events[fields["notification_uuid"]] = fields
        return WriteOutcome.applied


class _RecordingPurchases:
    """Stands in for the inverse token read, answering with one binding or with none."""

    def __init__(self, timeline: list[str], bound: UUID | None = None) -> None:
        self.timeline = timeline
        self.bound = bound
        self.calls: list[tuple[PurchaseProvider, str]] = []

    async def resolve_user(self, provider: PurchaseProvider, identity_value: str) -> UUID | None:
        self.timeline.append("resolve_user")
        self.calls.append((provider, identity_value))
        return self.bound


@pytest.fixture
def session() -> _StubSession:
    return _StubSession()


@pytest.fixture
def writer() -> _RecordingSubscriptions:
    return _RecordingSubscriptions()


def _seed_owned(writer, owner: UUID, *, external_id: str | None = None,
                store_signed_at: datetime | None = None,
                tier_id: str = PAID_TIER_ID,
                status: SubscriptionStatus = SubscriptionStatus.active) -> str:
    """Put one already-owned canonical row in the writer, as a restore leaves it; return its key."""
    external_id = external_id or f"original-{uuid4()}"
    writer.subscriptions[(PurchaseProvider.apple, external_id)] = Subscription(
        provider=PurchaseProvider.apple,
        external_id=external_id,
        user_id=owner,
        tier_id=tier_id,
        status=status,
        store_signed_at=store_signed_at,
        created_at=NOW,
        updated_at=NOW)
    return external_id


def _service(session, writer, bound: UUID | None) -> SubscriptionsService:
    """The real service over the two recording crud stands-in, so its own arms are what runs."""
    service = SubscriptionsService(db=session, evaluated_at=NOW)
    service.subscriptions_db = writer
    service.purchases_db = _RecordingPurchases(writer.timeline, bound)
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

    async def test_the_two_store_ids_are_passed_in_their_own_arguments(self, session, writer):
        """D-08 fixes `external_id` as Apple's `originalTransactionId`, so the per-term id is not
        the lifecycle key. The service's half alone: which column each lands in is the writer's,
        pinned by `test_app_store_webhook.py::test_the_two_store_ids_land_in_their_own_columns`."""
        service = _service(session, writer, uuid7())
        notification = _notification(attribution_token=TOKEN)

        await service.ingest(notification)

        purchase = writer.inserted[0]
        assert purchase["store_original_transaction_id"] == notification.external_id
        assert purchase["store_transaction_id"] == notification.transaction_id

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
        assert "lock_grants" in writer.timeline, "the lock this read must precede never ran"
        assert writer.timeline[0] == "resolve_user", writer.timeline
        assert writer.timeline.index("resolve_user") < writer.timeline.index("lock_grants")


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

    async def test_the_refusal_carries_the_rows_own_key_and_not_the_token(self, session, writer):
        """T-43-06, 44 T-44-26: the row's key finds the purchase, and no store value is in the record."""
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        with pytest.raises(AttributionConflict) as refusal:
            await service.ingest(_notification(attribution_token=OTHER_TOKEN,
                                               external_id=external_id))

        recorded = writer.purchases[(PurchaseProvider.apple, external_id)]
        assert refusal.value.log_fields() == {"provider": "apple",
                                              "purchase_id": str(recorded.id)}
        for secret in (external_id, TOKEN, OTHER_TOKEN):
            assert secret not in str(refusal.value)

    async def test_a_later_delivery_without_a_token_is_no_conflict(self, session, writer):
        """A notification presenting nothing disagrees with nothing, so an attributed row survives it."""
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        await service.ingest(_notification(attribution_token=None, external_id=external_id))

        assert len(writer.inserted) == 1
        assert writer.subscriptions[(PurchaseProvider.apple, external_id)].user_id is not None


    async def test_a_purchase_recorded_unattributed_accepts_a_later_real_token(self,
                                                                                session, writer):
        """CR-03: the store gave no token first, so the row carries a placeholder and no rival owner."""
        owner = uuid7()
        service = _service(session, writer, owner)
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=None, external_id=external_id))
        assert writer.purchases[(PurchaseProvider.apple, external_id)].resolved_token_value is None

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        assert writer.subscriptions[(PurchaseProvider.apple, external_id)].user_id == owner
        assert [grant["user_id"] for grant in writer.granted] == [owner]

    async def test_a_store_supplied_owner_that_disagrees_is_still_refused(self, session, writer):
        """The mirror the change must not lose: the recorded value came from the store, and they disagree."""
        service = _service(session, writer, uuid7())
        external_id = f"original-{uuid4()}"
        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))
        assert writer.purchases[(PurchaseProvider.apple, external_id)].resolved_token_value == TOKEN

        with pytest.raises(AttributionConflict):
            await service.ingest(_notification(attribution_token=OTHER_TOKEN,
                                               external_id=external_id))


@pytest.mark.asyncio
class TestTheOwnerIsChangedByRestoreAlone:
    """D-09: the token attributes an unowned row only, and a row that has an owner keeps it."""

    async def test_a_row_that_already_has_an_owner_keeps_it(self, session, writer):
        """T-45-07: a renewal carrying the original buyer's token must not take a restored row back."""
        external_id = _seed_owned(writer, RESTORER)
        # The token resolves to the account that bought the subscription before the restore moved it.
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id,
                                           event_type="DID_RENEW"))

        assert writer.subscriptions[(PurchaseProvider.apple, external_id)].user_id == RESTORER

    async def test_the_locks_and_the_grant_follow_the_row_and_not_the_token(self, session, writer):
        """The kept owner is the account whose grants are locked and whose grant the renewal writes."""
        external_id = _seed_owned(writer, RESTORER)
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id,
                                           event_type="DID_RENEW"))

        assert writer.locked == [RESTORER]
        assert [grant["user_id"] for grant in writer.granted] == [RESTORER]


@pytest.mark.asyncio
class TestARestoreThatCommitsInTheWindowIsRefused:
    """The unlocked read of the canonical row can be stale: nothing serialises it against a restore,
    which takes no lock on `core.subscriptions` either. Writing against the owner this path locked
    when the row has since moved supersedes nothing at all."""

    async def test_an_expiry_whose_owner_moved_refuses_rather_than_writing_against_the_old_one(
            self, session, writer):
        """The sharp case: `expired` supersedes no grant, so a silent write would commit the event
        and leave the new owner holding an active grant with a future `ends_at`."""
        external_id = _seed_owned(writer, ORIGINAL_BUYER)
        writer.settled_owner = RESTORER
        service = _service(session, writer, None)

        with pytest.raises(InternalError):
            await service.ingest(_notification(external_id=external_id, event_type="EXPIRED",
                                               status=SubscriptionStatus.expired))

        assert writer.locked == [ORIGINAL_BUYER]
        assert writer.granted == []
        assert writer.upserts == []
        assert session.commits == 0

    async def test_an_adoption_of_a_row_this_path_read_unowned_is_refused_too(self, session,
                                                                             writer):
        """The unowned row locks nothing, so a restore adopting it in the window leaves the new
        owner's grants unlocked and unread."""
        writer.settled_owner = RESTORER
        service = _service(session, writer, None)

        with pytest.raises(InternalError):
            await service.ingest(_notification(event_type="EXPIRED",
                                               status=SubscriptionStatus.expired))

        assert writer.locked == []
        assert writer.granted == []
        assert session.commits == 0

    async def test_a_replay_takes_no_lock_and_gives_its_read_transaction_back(self, session,
                                                                              writer):
        """WR-61: `get_db` runs its teardown only after the response is on the wire, so a lock or a
        transaction still held on return survives the 200 the store is answered with."""
        notification = _notification()
        writer.events[notification.notification_uuid] = {"already": "recorded"}
        _seed_owned(writer, ORIGINAL_BUYER, external_id=notification.external_id)
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(notification)

        assert writer.locked == []
        assert writer.timeline == []
        assert (session.commits, session.rollbacks) == (0, 1)

    async def test_an_owner_that_did_not_move_writes_exactly_as_before(self, session, writer):
        """The control: the guard reads the same owner the locks were taken on and changes nothing."""
        external_id = _seed_owned(writer, RESTORER)
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id,
                                           event_type="DID_RENEW"))

        assert writer.locked == [RESTORER]
        assert [grant["user_id"] for grant in writer.granted] == [RESTORER]
        assert session.commits == 1


@pytest.mark.asyncio
class TestTheAppendedEventNamesTheTierTheLocksSettledOn:
    """WR-61: `old_tier_id` was copied out of the pre-lock read, which the under-lock read replaced."""

    async def test_a_tier_a_rival_moved_in_the_window_is_the_transition_recorded(self, session,
                                                                                 writer):
        """The audit trail is what an operator reconstructs a disputed subscription from, so a
        transition out of a tier the row no longer carried is worse there than no value at all."""
        external_id = _seed_owned(writer, RESTORER)
        writer.rival = lambda: _seed_owned(writer, RESTORER, external_id=external_id,
                                           tier_id=OTHER_TIER_ID)
        service = _service(session, writer, None)

        await service.ingest(_notification(external_id=external_id, event_type="DID_RENEW"))

        assert [event["old_tier_id"] for event in writer.appended] == [OTHER_TIER_ID]
        assert session.commits == 1

    async def test_a_row_the_unlocked_read_missed_entirely_still_names_its_tier(self, session,
                                                                               writer):
        """The rival's insert is what that read missed, so the pre-lock snapshot recorded NULL."""
        external_id = f"original-{uuid4()}"
        writer.rival = lambda: _seed_owned(writer, RESTORER, external_id=external_id,
                                           tier_id=OTHER_TIER_ID)
        service = _service(session, writer, RESTORER)

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id,
                                           event_type="DID_RENEW"))

        assert [event["old_tier_id"] for event in writer.appended] == [OTHER_TIER_ID]
        assert session.commits == 1

    async def test_a_tier_no_rival_touched_is_still_the_one_recorded_control(self, session, writer):
        """The control: the re-read must not turn every ordinary delivery's transition into a no-op."""
        external_id = _seed_owned(writer, RESTORER)
        service = _service(session, writer, None)

        await service.ingest(_notification(external_id=external_id, event_type="DID_RENEW"))

        assert [event["old_tier_id"] for event in writer.appended] == [PAID_TIER_ID]
        assert session.commits == 1


@pytest.mark.asyncio
class TestADeliveryThatCommitsInTheWindowSupersedesThisOne:
    """The unlocked read is stale on the store clock for the reason it is stale on the owner: the
    two deliveries of one subscription serialise on the buyer's grant locks, not before them."""

    async def test_a_payload_older_than_the_clock_the_winner_committed_is_superseded(self, session,
                                                                                     writer):
        """CR-17: the renewal commits `T2` between the unlocked read and the locks, so comparing
        against the clock that read saw would apply this expiry and end the paying buyer's grant."""
        external_id = _seed_owned(writer, RESTORER)
        writer.rival = lambda: _seed_owned(writer, RESTORER, external_id=external_id,
                                           store_signed_at=NOW + timedelta(hours=2))
        service = _service(session, writer, None)

        await service.ingest(_notification(external_id=external_id, event_type="EXPIRED",
                                           status=SubscriptionStatus.expired,
                                           signed_at=NOW + timedelta(hours=1)))

        assert [event["notification_uuid"] for event in writer.appended] != []
        assert writer.upserts == []
        assert writer.granted == []
        assert session.commits == 1

    async def test_a_payload_newer_than_that_clock_applies(self, session, writer):
        """The control: the same guard reading the same fresh clock lets the newer payload through."""
        external_id = _seed_owned(writer, RESTORER)
        writer.rival = lambda: _seed_owned(writer, RESTORER, external_id=external_id,
                                           store_signed_at=NOW + timedelta(hours=1))
        service = _service(session, writer, None)

        await service.ingest(_notification(external_id=external_id, event_type="EXPIRED",
                                           status=SubscriptionStatus.expired,
                                           signed_at=NOW + timedelta(hours=2)))

        assert [upsert["status"] for upsert in writer.upserts] == [SubscriptionStatus.expired]
        assert [grant["status"] for grant in writer.granted] == [SubscriptionStatus.expired]
        assert session.commits == 1

    async def test_a_row_the_unlocked_read_missed_entirely_still_supersedes_this_one(self, session,
                                                                                    writer):
        """WR-40: the guard was gated on the pre-lock read, so a rival that *inserted* the row in
        the window skipped it. One buyer leaves the owner guard nothing to say and the two
        `notification_uuid`s leave the replay arm nothing, so the older payload re-granted."""
        external_id = f"original-{uuid4()}"
        writer.rival = lambda: _seed_owned(writer, RESTORER, external_id=external_id,
                                           status=SubscriptionStatus.revoked,
                                           store_signed_at=NOW + timedelta(hours=2))
        service = _service(session, writer, RESTORER)

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id,
                                           event_type="DID_RENEW",
                                           status=SubscriptionStatus.active,
                                           signed_at=NOW + timedelta(hours=1)))

        assert [event["notification_uuid"] for event in writer.appended] != []
        assert writer.upserts == []
        assert writer.granted == []
        assert session.commits == 1

    async def test_the_same_delivery_writes_when_no_rival_committed_control(self, session, writer):
        """The control: the case above must pass because the rival's row superseded it, not because
        a delivery whose unlocked read saw nothing stopped writing at all."""
        external_id = f"original-{uuid4()}"
        service = _service(session, writer, RESTORER)

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id,
                                           event_type="DID_RENEW",
                                           status=SubscriptionStatus.active,
                                           signed_at=NOW + timedelta(hours=1)))

        assert [upsert["status"] for upsert in writer.upserts] == [SubscriptionStatus.active]
        assert [grant["status"] for grant in writer.granted] == [SubscriptionStatus.active]
        assert session.commits == 1


async def _upsert(writer, external_id: str, *, signed_at=NOW,
                  status=SubscriptionStatus.active) -> tuple[Subscription, WriteOutcome]:
    """One canonical write through the recorder, with the fields every case here holds fixed."""
    stored = writer.subscriptions.get((PurchaseProvider.apple, external_id))
    return await writer.upsert_subscription(provider=PurchaseProvider.apple,
                                            external_id=external_id,
                                            user_id=RESTORER,
                                            tier_id=PAID_TIER_ID,
                                            status=status,
                                            signed_at=signed_at,
                                            clock_read=(None if stored is None
                                                        else stored.store_signed_at),
                                            evaluated_at=NOW)


@pytest.mark.asyncio
class TestTheRecorderAnswersWithTheRealWriter:
    """WR-49: the stand-in restated the writer's rules instead of running them, and had drifted on
    both -- it moved the store clock backwards where production only advances it, and answered
    `applied` for a delivery that changed nothing where production answers `replayed`."""

    async def test_a_delivery_carrying_no_change_is_a_replay_and_not_an_application(self,
                                                                                    writer):
        external_id = _seed_owned(writer, RESTORER)

        _, outcome = await _upsert(writer, external_id)

        assert outcome is WriteOutcome.replayed

    async def test_a_delivery_carrying_a_change_is_applied_control(self, writer):
        """The control: the outcome tracks the delivery, so the case above is not `replayed` always."""
        external_id = _seed_owned(writer, RESTORER)

        _, outcome = await _upsert(writer, external_id, status=SubscriptionStatus.expired)

        assert outcome is WriteOutcome.applied

    async def test_an_older_signing_date_never_moves_the_clock_backwards(self, writer):
        """The column the service's own out-of-order guard reads: moved back, a stale redelivery
        passes that guard and downgrades a paying subscriber."""
        external_id = _seed_owned(writer, RESTORER)
        await _upsert(writer, external_id, signed_at=NOW + timedelta(hours=2))

        stored, _ = await _upsert(writer, external_id, signed_at=NOW + timedelta(hours=1))

        assert stored.store_signed_at == NOW + timedelta(hours=2)


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

        await service.ingest(_notification(external_id=None, product_id=None, tier_id=None,
                                           event_type="TEST"))

        assert [len(writer.inserted), len(writer.upserts), len(writer.appended)] == [0, 0, 0]
        assert session.commits == 0

    async def test_the_status_written_is_the_one_the_notification_carries(self, session, writer):
        """The store's own word reaches the upsert unchanged, so no date is read on the way."""
        service = _service(session, writer, uuid7())

        await service.ingest(_notification(attribution_token=TOKEN,
                                           status=SubscriptionStatus.revoked))

        assert writer.upserts[0]["status"] is SubscriptionStatus.revoked
        assert writer.upserts[0]["tier_id"] == PAID_TIER_ID


@pytest.mark.asyncio
class TestATierlessNotificationIsRefusedBeforeAnyWrite:
    """WR-06: `tier_id` reaches three NOT NULL columns, guarded only by a comment about `product_id`."""

    async def test_it_raises_the_generic_500_the_store_then_retries(self, session, writer):
        service = _service(session, writer, None)

        with pytest.raises(InternalError):
            await service.ingest(_notification(tier_id=None))

    async def test_it_writes_nothing_and_commits_nothing(self, session, writer):
        service = _service(session, writer, None)

        with pytest.raises(InternalError):
            await service.ingest(_notification(tier_id=None))

        assert (writer.upserts, writer.inserted, writer.appended, writer.granted) == ([], [], [], [])
        assert session.commits == 0

    async def test_a_notification_naming_no_product_still_returns_quietly(self, session, writer):
        """The neighbouring branch is unchanged: no product means nothing to write, not a failure."""
        service = _service(session, writer, None)

        await service.ingest(_notification(product_id=None, tier_id=None))

        assert writer.upserts == []
        assert session.commits == 0


@pytest.fixture
def race_warnings(monkeypatch) -> list[tuple[str, dict]]:
    """A spy, not `capture_logs`: the module-level logger caches its binding at import."""
    entries: list[tuple[str, dict]] = []
    monkeypatch.setattr("nativespeaker.api.services.subscriptions.logger.warning",
                        lambda event, **kwargs: entries.append((event, kwargs)))
    return entries


@pytest.fixture
def commit_errors(monkeypatch) -> list[tuple[str, dict]]:
    """A spy on the same logger's error level, for the refusals that are not races at all."""
    entries: list[tuple[str, dict]] = []
    monkeypatch.setattr("nativespeaker.api.services.subscriptions.logger.error",
                        lambda event, **kwargs: entries.append((event, kwargs)))
    return entries


@pytest.mark.asyncio
class TestTheDeferredKeysAreClassifiedWhereTheyAreEvaluated:
    """WR-11: COMMIT is the deferred pair's only evaluation, and both of them are FOREIGN KEYs --
    23503, which is the one class `is_unique_violation` exists to re-raise. Read as a lost race,
    a deterministic writer bug was redelivered until retention with nothing naming it anywhere."""

    async def test_a_deferred_foreign_key_at_commit_is_not_read_as_a_race(
            self, writer, race_warnings, commit_errors):
        """The cause survives: only the `IntegrityError` names the constraint that refused."""
        session = _RefusingSession()
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(IntegrityError) as refused:
            await service.ingest(_notification(attribution_token=TOKEN))

        assert refused.value.orig.sqlstate == DEFERRED_KEY_VIOLATION
        assert (session.commits, session.rollbacks) == (1, 0)
        assert race_warnings == []

    async def test_the_refusal_names_the_code_the_constraint_carried(
            self, writer, race_warnings, commit_errors):
        """`InternalError.log_level` is None, so before this line the failure was wholly silent."""
        session = _RefusingSession()
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(IntegrityError):
            await service.ingest(_notification(attribution_token=TOKEN))

        assert commit_errors == [("store_notification_commit_refused",
                                  {"sqlstate": DEFERRED_KEY_VIOLATION})]

    async def test_a_violation_carrying_no_readable_code_is_refused_too(
            self, writer, race_warnings, commit_errors):
        """Fail-closed, exactly as `is_unique_violation` reads it: no code is not a race."""
        session = _RefusingSession(sqlstate=None)
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(IntegrityError):
            await service.ingest(_notification(attribution_token=TOKEN))

        assert commit_errors == [("store_notification_commit_refused", {"sqlstate": None})]
        assert race_warnings == []

    async def test_a_unique_violation_at_commit_is_still_the_lost_race(
            self, writer, race_warnings, commit_errors):
        """The control on the classification: COMMIT flushes too, so a unique index can refuse a
        write the arms above never reached, and that one code is the race the resend recovers from."""
        session = _RefusingSession(sqlstate=UNIQUE_VIOLATION)
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN))

        assert (session.commits, session.rollbacks) == (1, 1)
        assert race_warnings == [("store_notification_race_lost", {"provider": "apple"})]
        assert commit_errors == []

    async def test_an_ingest_that_wins_reports_neither_control(self, session, writer,
                                                               race_warnings, commit_errors):
        """The control: a line written unconditionally would pass the cases above and page on
        every ordinary notification."""
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN))

        assert session.commits == 1
        assert (race_warnings, commit_errors) == ([], [])


@pytest.mark.asyncio
class TestTheUpsertsOwnLostClaimIsAnsweredByTheService:
    """WR-49: the writer answers `lost_race` when a restore adopted the row first, and `ingest`
    settles that outcome exactly as it settles every other writer's."""

    async def test_a_restore_that_took_the_unowned_row_first_refuses_this_delivery(
            self, session, writer, race_warnings):
        writer.claim_wins = False
        external_id = _seed_owned(writer, None)
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        assert session.rollbacks == 1
        assert (writer.inserted, writer.granted, session.commits) == ([], [], 0)
        assert race_warnings == [("store_notification_race_lost", {"provider": "apple"})]

    async def test_a_claim_this_delivery_wins_records_the_owner_control(self, session, writer,
                                                                        race_warnings):
        """The control: the row count is the whole answer, so the winning claim must still write."""
        external_id = _seed_owned(writer, None)
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        assert writer.granted[0]["user_id"] == ORIGINAL_BUYER
        assert (session.commits, session.rollbacks) == (1, 0)
        assert race_warnings == []


@pytest.mark.asyncio
class TestAnEntitledNotificationWithNoOpenTermIsRefusedBeforeAnyWrite:
    """CR-20: an entitled status with no term end would insert a grant read as unbounded."""

    async def test_an_active_notification_with_no_expiry_raises_the_generic_500(self, session,
                                                                                writer):
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN, expires_at=None))

    async def test_a_grace_notification_with_no_grace_end_raises_the_generic_500(self, session,
                                                                                writer):
        """The grace arm reads its own field, so a paid expiry standing beside it is not the term."""
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN,
                                               status=SubscriptionStatus.grace_period,
                                               grace_period_expires_at=None))

    async def test_a_term_that_closed_before_the_captured_instant_raises_the_generic_500(
            self, session, writer):
        """CR-20: `starts_at` is a store purchase date, so it lies before the term end and guards
        nothing. An Apple redelivery, or a Play read answering `ACTIVE` past its expiry, arrives
        with a term already run out; writing it costs every grant held for one no read returns."""
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN,
                                               purchased_at=NOW - timedelta(days=40),
                                               expires_at=NOW - timedelta(minutes=1)))

    async def test_a_grace_window_that_closed_before_the_captured_instant_raises_the_generic_500(
            self, session, writer):
        """The grace arm reads its own field, so the closed window is the one guarded there."""
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN,
                                               status=SubscriptionStatus.grace_period,
                                               purchased_at=NOW - timedelta(days=40),
                                               expires_at=NOW - timedelta(days=10),
                                               grace_period_expires_at=NOW - timedelta(minutes=1)))

    async def test_a_closed_term_supersedes_no_grant_and_commits_nothing(self, session, writer):
        """The half that matters: the crud expires every grant the destination holds before it
        inserts an entitled one, so reaching the write would cost the buyer their free grant."""
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN,
                                               purchased_at=NOW - timedelta(days=40),
                                               expires_at=NOW - timedelta(minutes=1)))

        assert (writer.upserts, writer.inserted, writer.appended, writer.granted) == ([], [], [], [])
        assert session.commits == 0

    async def test_a_term_still_open_at_the_captured_instant_is_written_control(self, session,
                                                                                writer):
        """The control: the captured instant is what the guard compares against, so a term open at
        it is written whatever the purchase date says."""
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN,
                                           purchased_at=NOW - timedelta(days=40),
                                           expires_at=NOW + timedelta(minutes=1)))

        assert writer.granted[0]["ends_at"] == NOW + timedelta(minutes=1)

    async def test_a_purchase_date_ahead_of_the_captured_instant_is_capped_at_it(self, session,
                                                                                writer):
        """WR-60: unclamped it wrote a grant the shared effective predicate never reads, while that
        row still held the buyer's one-active slot and refused every free claim behind it."""
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN,
                                           purchased_at=NOW + timedelta(days=2),
                                           expires_at=NOW + timedelta(days=30)))

        assert writer.granted[0]["starts_at"] == NOW

    async def test_a_purchase_date_before_it_is_carried_through_control(self, session, writer):
        """The control: the cap binds one direction only, so a real purchase date is still the start."""
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN,
                                           purchased_at=NOW - timedelta(days=1),
                                           expires_at=NOW + timedelta(days=30)))

        assert writer.granted[0]["starts_at"] == NOW - timedelta(days=1)

    async def test_a_term_ending_no_later_than_it_starts_raises_the_generic_500(self, session,
                                                                               writer):
        """The row's own CHECK would fire as a non-unique violation the writer re-raises as a bare 500."""
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN, expires_at=NOW))

    async def test_it_writes_nothing_and_commits_nothing(self, session, writer):
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN, expires_at=None))

        assert (writer.upserts, writer.inserted, writer.appended, writer.granted) == ([], [], [], [])
        assert session.commits == 0

    async def test_the_same_shape_carrying_a_term_writes_that_term_control(self, session, writer):
        """The control: the guard refuses the missing term alone, never the entitled status."""
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN))

        assert writer.granted[0]["ends_at"] == NOW + timedelta(days=30)

    async def test_a_status_outside_the_entitled_set_still_writes_its_termless_end(self, session,
                                                                                  writer):
        """The second control: only an entitled term becomes an entitlement, so only it is guarded."""
        service = _service(session, writer, ORIGINAL_BUYER)

        await service.ingest(_notification(attribution_token=TOKEN,
                                           status=SubscriptionStatus.expired, expires_at=None))

        assert writer.granted[0]["ends_at"] is None


class TestTheStatusOneFieldCarriesIsAlwaysTheEnumMember:
    """WR-44. `write_subscription_grant` asks this field by value on one line and by identity three
    lines later, so the two answer differently for anything but a real member."""

    def test_a_raw_store_string_becomes_the_member_both_comparisons_agree_on(self):
        """Coerced in `__post_init__`, so a withdrawal is never recorded as an ordinary expiry."""
        notification = _notification(status="revoked")

        assert notification.status is SubscriptionStatus.revoked

    def test_a_value_outside_the_five_is_refused_rather_than_carried_control(self):
        """The control: the coercion is a check as well, so an unknown state never reaches a grant."""
        with pytest.raises(ValueError):
            _notification(status="cancelled")
