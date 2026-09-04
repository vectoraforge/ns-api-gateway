"""The App Store notification callback, end to end through the real router against a real database."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import make_token

from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.errors import NotificationRejected, Unavailable
from nativespeaker.api.tables import (
    PurchaseProvider,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)

pytestmark = pytest.mark.e2e

PATH = "/webhooks/app-store"

# The tier the migration seeds for a paid subscription, and the one the configured map targets.
PAID_TIER_ID = "paid"

# The one body every verification failure answers with, compared by equality so a richer field fails here.
REJECTED = {"code": "auth_required"}

# The same body as bytes, so the refusals are compared on the wire and not after parsing.
REJECTED_BODY = '{"code":"auth_required"}'

# The seam is scripted, so the envelope is never parsed here; it only has to be a non-empty string.
ENVELOPE = "signed-payload-that-only-the-scripted-seam-reads"

# The four `VerificationStatus` names a misconfigured deployment and a forged payload produce.
REFUSAL_STAGES = ("VERIFICATION_FAILURE", "INVALID_CERTIFICATE",
                  "INVALID_APP_IDENTIFIER", "INVALID_ENVIRONMENT")


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


async def _subscriptions_of(factory, external_id: str) -> list[Subscription]:
    """Every canonical row for one lifecycle key; the unique index allows at most one."""
    async with factory() as session:
        return list((await session.exec(
            select(Subscription).where(col(Subscription.external_id) == external_id))).all())


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
        scripted_app_store_notifications.script(NotificationRejected(stage=stage))

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 401
        assert response.json() == REJECTED
        assert response.text == REJECTED_BODY

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
        assert response.text == REJECTED_BODY

    async def test_an_unconfigured_deployment_answers_503(
            self, webhook_client, scripted_app_store_notifications):
        """The route is registered in every environment; an incomplete config fails it closed here."""
        scripted_app_store_notifications.script(Unavailable(stage="app_store_verify"))

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 503
        assert response.json() == {"code": "verification_temporarily_unavailable"}


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
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        notification = _empty_notification()
        scripted_app_store_notifications.script(notification)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 200, response.text
        assert await _events_of(_db_transaction, notification.notification_uuid) == []

    async def test_an_unmapped_product_answers_500_and_writes_nothing(
            self, webhook_client, scripted_app_store_notifications, _db_transaction):
        """An operator adds the map line and Apple's next retry succeeds; nothing is written meanwhile."""
        notification = _notification(product_id="com.nativespeaker.subscription.unmapped")
        scripted_app_store_notifications.script(notification)

        response = await webhook_client.post(PATH, json={"signedPayload": ENVELOPE})

        assert response.status_code == 500
        assert response.json() == {"code": "internal_error"}
        assert await _subscriptions_of(_db_transaction, notification.external_id) == []
        assert await _events_of(_db_transaction, notification.notification_uuid) == []


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
