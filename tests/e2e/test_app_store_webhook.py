"""The App Store notification callback, end to end through the real router against a real database."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from appstoreserverlibrary.signed_data_verifier import VerificationStatus
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func
from sqlmodel import col, select
from unit.conftest import make_token

from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.errors import NotificationRejected
from nativespeaker.api.tables import (
    PurchaseProvider,
    StorePurchase,
    StorePurchaseToken,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
    User,
)

pytestmark = pytest.mark.e2e

PATH = "/webhooks/app-store"

# The tier the migration seeds for a paid subscription, and the one the configured map targets.
PAID_TIER_ID = "paid"

# The one body every verification failure answers with, compared by equality so a richer field fails here.
REJECTED = {"code": "auth_required"}

# The same body as raw bytes, so the refusals are compared on the wire and not after parsing.
REJECTED_BODY = b'{"code":"auth_required"}'

# The 503 an incomplete configuration answers, and the 500 both refusal leaves share.
UNAVAILABLE = {"code": "verification_temporarily_unavailable"}
INTERNAL = {"code": "internal_error"}

# The seam is scripted, so the envelope is never parsed here; it only has to be a non-empty string.
ENVELOPE = "signed-payload-that-only-the-scripted-seam-reads"

# Every reachable arm: the library's whole status set less the one that is not a refusal.
REFUSAL_STAGES = tuple(status.name for status in VerificationStatus
                       if status is not VerificationStatus.OK)

# One obviously synthetic attribution token, and a second that disagrees with it.
TOKEN = "a-synthetic-attribution-token"
OTHER_TOKEN = "a-different-synthetic-attribution-token"

# The value a `core.store_purchase_tokens` row carries, which resolves a delivery to a real owner.
STORE_TOKEN = "a-synthetic-store-purchase-token"

# Every value a log record must never carry: the payload, both attribution tokens and the store token.
SENSITIVE_VALUES = (ENVELOPE, TOKEN, OTHER_TOKEN, STORE_TOKEN)


# The two modules that write a record on this route: the error handler, and the service's own INFO line.
_LOGGERS = ("nativespeaker.api.app.error_handlers.logger",
            "nativespeaker.api.services.subscriptions.logger")


class _LogSpy:
    """A recording spy on a module's own logger, so "which record, once" stays observable."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **fields) -> None:
        self.entries.append((event, fields))


def _spy_on(monkeypatch, targets: tuple[str, ...], levels: tuple[str, ...]) -> _LogSpy:
    """A spy, not `capture_logs`: the module-level logger caches its binding, so capture sees nothing."""
    spy = _LogSpy()
    for target in targets:
        for level in levels:
            monkeypatch.setattr(f"{target}.{level}", spy.record)
    return spy


@pytest.fixture
def error_records(monkeypatch) -> _LogSpy:
    """Every ERROR record the handler writes, and nothing else."""
    return _spy_on(monkeypatch, (_LOGGERS[0],), ("error",))


@pytest.fixture
def info_records(monkeypatch) -> _LogSpy:
    """Every INFO record the service writes, and nothing else."""
    return _spy_on(monkeypatch, (_LOGGERS[1],), ("info",))


@pytest.fixture
def captured_records(monkeypatch) -> _LogSpy:
    """One list holding every record either module writes at any level, for the hygiene walk."""
    return _spy_on(monkeypatch, _LOGGERS, ("info", "warning", "error"))


@pytest_asyncio.fixture(loop_scope="module")
async def webhook_client(_app_lifespan):
    """A client over the real started app that sends no Authorization header."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _notification(**overrides) -> VerifiedNotification:
    """One verified subscription notification; `overrides` replaces any field a case cares about."""
    now = datetime.now(UTC)
    fields = {"provider": PurchaseProvider.apple,
              "notification_uuid": f"uuid-{uuid4()}",
              "event_type": "SUBSCRIBED",
              "external_id": f"original-{uuid4()}",
              "transaction_id": f"txn-{uuid4()}",
              "product_id": "com.nativespeaker.subscription.monthly",
              "attribution_token": None,
              "signed_at": now,
              "purchased_at": now,
              "expires_at": now + timedelta(days=30),
              "revoked_at": None,
              "grace_period_expires_at": None,
              "in_billing_retry": False}
    return VerifiedNotification(**(fields | overrides))


def _empty_notification(**overrides) -> VerifiedNotification:
    """A TEST or summary notification: verified, and carrying no transaction part at all."""
    return _notification(event_type="TEST", external_id=None, transaction_id=None,
                         product_id=None, purchased_at=None, expires_at=None, **overrides)


async def _seed_store_token(factory, value: str) -> None:
    """One user holding one Apple store token, so a delivery carrying that token resolves an owner."""
    async with factory() as session:
        user = User()
        session.add(user)
        await session.flush()
        session.add(StorePurchaseToken(user_id=user.id, provider=PurchaseProvider.apple,
                                       identity_value=value, created_at=datetime.now(UTC)))
        await session.commit()


async def _subscriptions_of(factory, external_id: str) -> list[Subscription]:
    """Every canonical row for one lifecycle key; the unique index allows at most one."""
    async with factory() as session:
        return list((await session.exec(
            select(Subscription).where(col(Subscription.external_id) == external_id))).all())


async def _purchases_of(factory, external_id: str) -> list[StorePurchase]:
    """Every purchase row for one lifecycle key; the UNIQUE constraint allows at most one."""
    async with factory() as session:
        return list((await session.exec(
            select(StorePurchase).where(col(StorePurchase.external_id) == external_id))).all())


async def _counts(factory) -> tuple[int, ...]:
    """Row counts of the three tables one delivery writes, so a case naming no key can still say "nothing"."""
    counted = []
    async with factory() as session:
        for model in (Subscription, StorePurchase, SubscriptionEvent):
            counted.append((await session.exec(select(func.count()).select_from(model))).one())
    return tuple(counted)


async def _events_of(factory, notification_uuid: str) -> list[SubscriptionEvent]:
    """Every event row carrying one notification key; the UNIQUE column allows at most one."""
    async with factory() as session:
        return list((await session.exec(
            select(SubscriptionEvent)
            .where(col(SubscriptionEvent.notification_uuid) == notification_uuid))).all())


@pytest.mark.asyncio(loop_scope="module")
class TestTheVerifiedNotificationReachesCommittedRows:
    """The tracer: one verified envelope, one canonical row, one event row, and a 200 after the commit."""

    async def test_an_unattributed_subscription_writes_both_rows(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        notification = _notification()
        scripted_app_store_notifications.script(notification)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 200, response.text
        subscriptions = await _subscriptions_of(_db_transaction, notification.external_id)
        assert len(subscriptions) == 1
        assert subscriptions[0].provider is PurchaseProvider.apple
        assert subscriptions[0].tier_id == PAID_TIER_ID
        assert subscriptions[0].status is SubscriptionStatus.active
        # Unattributed by design: restore is the only path that ever links this row to a user.
        assert subscriptions[0].user_id is None

        events = await _events_of(_db_transaction, notification.notification_uuid)
        assert len(events) == 1
        assert events[0].subscription_id == subscriptions[0].id
        assert events[0].event_type == "SUBSCRIBED"
        assert events[0].new_tier_id == PAID_TIER_ID

    async def test_the_seam_received_the_posted_envelope_untouched(
            self, webhook_client, scripted_app_store_notifications):
        scripted_app_store_notifications.script(_notification())

        await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert scripted_app_store_notifications.calls == [ENVELOPE]

    async def test_an_unknown_notification_type_is_recorded_as_sent(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        """A type this build does not know costs nothing: it is text in a column, never a branch."""
        notification = _notification(event_type="SOME_FUTURE_TYPE")
        scripted_app_store_notifications.script(notification)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 200, response.text
        events = await _events_of(_db_transaction, notification.notification_uuid)
        assert [event.event_type for event in events] == ["SOME_FUTURE_TYPE"]


@pytest.mark.asyncio(loop_scope="module")
class TestEveryVerificationFailureAnswersTheOneBody:
    """T-43-05: one class, one body, so the route is no oracle about which check refused the payload."""

    @pytest.mark.parametrize("stage", REFUSAL_STAGES)
    async def test_each_refusal_answers_the_same_401_body(
            self, webhook_client, scripted_app_store_notifications, stage):
        """One parameter per reachable status, so an arm the library adds arrives here rather than silently."""
        scripted_app_store_notifications.script(NotificationRejected(stage=stage))

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 401
        assert response.json() == REJECTED
        # On the wire, not after parsing: a field added later fails here rather than becoming an oracle.
        assert response.content == REJECTED_BODY

    async def test_every_reachable_arm_is_covered_by_one_parameter(self):
        """The control: a narrowed tuple would leave an arm untested while every case above still passed."""
        assert set(REFUSAL_STAGES) == {status.name for status in VerificationStatus} - {"OK"}
        assert len(REFUSAL_STAGES) == len(VerificationStatus) - 1

    async def test_a_refused_payload_writes_nothing(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        notification = _notification()
        scripted_app_store_notifications.script(
            NotificationRejected(stage="VERIFICATION_FAILURE"))

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 401
        assert await _subscriptions_of(_db_transaction, notification.external_id) == []
        assert await _events_of(_db_transaction, notification.notification_uuid) == []

    async def test_a_valid_firebase_token_does_not_change_the_refusal(
            self, webhook_client, scripted_app_store_notifications, stub_verifier):
        """The route never reads an Authorization header, so a good token buys a bad payload nothing."""
        scripted_app_store_notifications.script(
            NotificationRejected(stage="VERIFICATION_FAILURE"))

        response = await webhook_client.post(
            PATH, json={"signedPayload": ENVELOPE},
            headers={"Authorization": f"Bearer {make_token(sub='store-callback-subject')}"})

        assert response.status_code == 401
        assert response.content == REJECTED_BODY

    async def test_an_unconfigured_deployment_answers_503(
            self, webhook_client, unconfigured_app_store_notifications):
        """D-02. A real seam holding no verifier, which is what an incomplete configuration leaves behind."""
        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 503
        assert response.json() == UNAVAILABLE

    async def test_the_route_is_still_registered_while_the_seam_is_unconfigured(
            self, _app_lifespan, webhook_client, unconfigured_app_store_notifications):
        """D-02. The route set is identical in every environment: present and answering 503, never absent."""
        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 503
        assert PATH in {route.path for route in _app_lifespan.routes}


@pytest.mark.asyncio(loop_scope="module")
class TestTheReplayAndTheEmptyNotificationWriteNothing:
    """The two 200s that record nothing: a second delivery of one key, and a notification with no transaction."""

    async def test_a_second_delivery_of_one_key_writes_no_second_event(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        notification = _notification()
        scripted_app_store_notifications.script(notification)

        first = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})
        second = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert (first.status_code, second.status_code) == (200, 200)
        assert len(await _events_of(_db_transaction, notification.notification_uuid)) == 1
        assert len(await _subscriptions_of(_db_transaction, notification.external_id)) == 1

    async def test_a_notification_with_no_transaction_part_writes_nothing(
            self, webhook_client, scripted_app_store_notifications, _db_transaction, info_records):
        """D-22. A TEST or summary notification: 200, no row of any of the three kinds, one INFO line."""
        notification = _empty_notification()
        scripted_app_store_notifications.script(notification)
        before = await _counts(_db_transaction)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 200, response.text
        assert await _events_of(_db_transaction, notification.notification_uuid) == []
        assert await _counts(_db_transaction) == before
        assert len(info_records.entries) == 1
        event, fields = info_records.entries[0]
        assert event == "store_notification_without_transaction"
        assert fields["event_type"] == notification.event_type

    async def test_an_unmapped_product_answers_500_and_writes_nothing(
            self, webhook_client, scripted_app_store_notifications, _db_transaction, error_records):
        """D-14, D-21. An operator adds the map line and Apple's next retry succeeds; nothing is written."""
        notification = _notification(product_id="com.nativespeaker.subscription.unmapped")
        scripted_app_store_notifications.script(notification)
        before = await _counts(_db_transaction)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 500
        assert response.json() == INTERNAL
        assert await _subscriptions_of(_db_transaction, notification.external_id) == []
        assert await _purchases_of(_db_transaction, notification.external_id) == []
        assert await _events_of(_db_transaction, notification.notification_uuid) == []
        assert await _counts(_db_transaction) == before
        assert len(error_records.entries) == 1
        event, fields = error_records.entries[0]
        assert event == "unmapped_store_product"
        assert fields["product_id"] == notification.product_id


@pytest.mark.asyncio(loop_scope="module")
class TestAChangedAttributionIsRefusedAndNothingIsWritten:
    """T-43-07: a recorded owner is never reassigned, because a wrongly granted entitlement cannot be undone."""

    async def _record_then_conflict(self, client, seam, external_id: str):
        """Deliver one purchase under `TOKEN`, then a second delivery of the same key under another."""
        seam.script(_notification(attribution_token=TOKEN, external_id=external_id))
        first = await client.post(PATH, json={"signedPayload": ENVELOPE})
        assert first.status_code == 200, first.text

        conflicting = _notification(attribution_token=OTHER_TOKEN, external_id=external_id)
        seam.script(conflicting)
        return conflicting, await client.post(PATH, json={"signedPayload": ENVELOPE})

    async def test_the_conflicting_delivery_answers_the_shared_500_body(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        external_id = f"original-{uuid4()}"

        _, response = await self._record_then_conflict(
            webhook_client, scripted_app_store_notifications, external_id)

        assert response.status_code == 500
        assert response.json() == INTERNAL

    async def test_the_conflicting_delivery_adds_no_row_of_any_of_the_three_kinds(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        external_id = f"original-{uuid4()}"

        conflicting, response = await self._record_then_conflict(
            webhook_client, scripted_app_store_notifications, external_id)

        assert response.status_code == 500
        assert len(await _subscriptions_of(_db_transaction, external_id)) == 1
        assert len(await _purchases_of(_db_transaction, external_id)) == 1
        assert await _events_of(_db_transaction, conflicting.notification_uuid) == []

    async def test_the_recorded_attribution_is_left_as_the_first_delivery_wrote_it(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        external_id = f"original-{uuid4()}"

        await self._record_then_conflict(
            webhook_client, scripted_app_store_notifications, external_id)

        purchases = await _purchases_of(_db_transaction, external_id)
        assert purchases[0].identity_value == TOKEN
        # No binding row exists for this token, so the purchase is recorded unowned and stays so.
        assert purchases[0].resolved_token_value is None
        assert purchases[0].purchase_user_id is None

    async def test_the_refusal_logs_once_and_never_carries_the_attribution_token(
            self, webhook_client, scripted_app_store_notifications, error_records):
        external_id = f"original-{uuid4()}"

        await self._record_then_conflict(
            webhook_client, scripted_app_store_notifications, external_id)

        assert len(error_records.entries) == 1
        event, fields = error_records.entries[0]
        assert event == "attribution_conflict"
        assert fields["provider"] == "apple"
        assert fields["external_id"] == external_id
        # T-43-06: the token is a lifetime attribution value, so it reaches no record at all.
        assert TOKEN not in repr(error_records.entries)
        assert OTHER_TOKEN not in repr(error_records.entries)


@pytest.mark.asyncio(loop_scope="module")
class TestTheRowCountHelpersSeeARow:
    """The control: a helper quietly returning an empty list would pass every "nothing added" assertion."""

    async def test_a_successful_delivery_is_counted_by_all_three_helpers(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        notification = _notification(attribution_token=TOKEN)
        scripted_app_store_notifications.script(notification)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 200, response.text
        assert len(await _subscriptions_of(_db_transaction, notification.external_id)) == 1
        assert len(await _purchases_of(_db_transaction, notification.external_id)) == 1
        assert len(await _events_of(_db_transaction, notification.notification_uuid)) == 1

    async def test_an_unattributed_delivery_records_a_generated_identity_value(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        """P-10: `identity_value` is TEXT NOT NULL, so a store that gives no token still writes a row."""
        notification = _notification(attribution_token=None)
        scripted_app_store_notifications.script(notification)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 200, response.text
        purchases = await _purchases_of(_db_transaction, notification.external_id)
        assert UUID(purchases[0].identity_value)
        assert purchases[0].resolved_token_value is None


@pytest.mark.asyncio(loop_scope="module")
class TestTheRouteIsReachableWithoutACredential:
    """APPLEHOOK-01: the signature is the whole credential, so the framework must let the body through."""

    async def test_an_empty_signed_payload_is_the_frameworks_validation_error(
            self, webhook_client, scripted_app_store_notifications):
        response = await webhook_client.post(PATH, json={"signedPayload": ""})

        assert response.status_code == 422
        assert response.json() == {"code": "validation_error"}
        # The gate never ran: FastAPI collects the body's validation errors before resolving it.
        assert scripted_app_store_notifications.calls == []

    async def test_the_route_is_not_reachable_by_a_trailing_slash(self, webhook_client):
        """`redirect_slashes` is off, so no unauthenticated 307 exists ahead of the exact path."""
        response = await webhook_client.post(f"{PATH}/", json={"signedPayload": ENVELOPE})

        assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="module")
class TestNoRecordCarriesASensitiveValue:
    """T-43-06: the signed payload, both attribution tokens and a store token reach no log record at all."""

    async def _drive_every_recording_arm(self, client, seam, factory, records):
        """One delivery per arm that writes a record, plus the attributed one that writes rows and none."""
        await _seed_store_token(factory, STORE_TOKEN)
        external_id = f"original-{uuid4()}"

        for scripted in (_empty_notification(),
                         NotificationRejected(stage="VERIFICATION_FAILURE"),
                         _notification(product_id="com.nativespeaker.subscription.unmapped",
                                       attribution_token=TOKEN),
                         _notification(attribution_token=STORE_TOKEN, external_id=external_id),
                         _notification(attribution_token=OTHER_TOKEN, external_id=external_id)):
            seam.script(scripted)
            await client.post(PATH, json={"signedPayload": ENVELOPE})
        return records.entries

    async def test_the_walk_sees_the_records_the_deliveries_produced(
            self, webhook_client, scripted_app_store_notifications, _db_transaction,
            captured_records):
        """The control: a capture returning nothing would pass the hygiene case below without reading a record."""
        entries = await self._drive_every_recording_arm(
            webhook_client, scripted_app_store_notifications, _db_transaction, captured_records)

        assert {event for event, _ in entries} == {"store_notification_without_transaction",
                                                   "notification_rejected",
                                                   "unmapped_store_product",
                                                   "attribution_conflict"}

    async def test_no_record_carries_the_payload_an_attribution_token_or_the_store_token(
            self, webhook_client, scripted_app_store_notifications, _db_transaction,
            captured_records):
        entries = await self._drive_every_recording_arm(
            webhook_client, scripted_app_store_notifications, _db_transaction, captured_records)

        rendered = repr(entries)
        for secret in SENSITIVE_VALUES:
            assert secret not in rendered, f"a log record carries {secret!r}"
