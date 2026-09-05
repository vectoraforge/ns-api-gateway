"""The Google Play callback, end to end through the real seam classes against a real database.
The push token is signed for real against the fake JWKS key, and the Play read is scripted at the transport."""
import base64
import json
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from unit.conftest import make_token
from unit.test_jwks_offload import KNOWN_KID

from e2e.conftest import (
    GOOGLE_PACKAGE_NAME,
    GOOGLE_PRODUCT_ID,
    GOOGLE_PUSH_AUDIENCE,
    GOOGLE_PUSH_ISSUER,
    GOOGLE_PUSH_SERVICE_ACCOUNT,
)
from nativespeaker.api.tables import (
    PurchaseProvider,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)

pytestmark = pytest.mark.e2e

PATH = "/webhooks/google-play/rtdn"

# The tier the migration seeds for a paid subscription, and the one the scripted product maps to.
PAID_TIER_ID = "paid"

# The 503 an incomplete configuration answers.
UNAVAILABLE = {"code": "verification_temporarily_unavailable"}

# One RTDN instant and one notification type, so the composite replay key is known to the case.
EVENT_TIME_MILLIS = 1789000000000
SUBSCRIPTION_PURCHASED = 4


@pytest_asyncio.fixture(loop_scope="module")
async def webhook_client(_app_lifespan):
    """A client over the real started app that sends the push token as its own Authorization header."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _push_token(**overrides) -> str:
    """One RS256 OIDC token in the shape Cloud Pub/Sub sends, signed by the fake JWKS key."""
    fields = {"sub": "111111111111111111111",
              "aud": GOOGLE_PUSH_AUDIENCE,
              "iss": GOOGLE_PUSH_ISSUER,
              "extra_claims": {"email": GOOGLE_PUSH_SERVICE_ACCOUNT},
              "headers": {"kid": KNOWN_KID}}
    return make_token(**(fields | overrides))


def _push_body(purchase_token: str, *, package_name: str = GOOGLE_PACKAGE_NAME) -> dict:
    """One Pub/Sub push body whose `data` is the base64 `DeveloperNotification` Google publishes."""
    notification = {"version": "1.0",
                    "packageName": package_name,
                    "eventTimeMillis": str(EVENT_TIME_MILLIS),
                    "subscriptionNotification": {"version": "1.0",
                                                 "notificationType": SUBSCRIPTION_PURCHASED,
                                                 "purchaseToken": purchase_token}}
    return {"message": {"messageId": f"message-{uuid4()}",
                        "data": base64.b64encode(json.dumps(notification).encode()).decode()},
            "subscription": "projects/nativespeaker-test/subscriptions/rtdn-push"}


def _replay_key(purchase_token: str) -> str:
    """The composite key the Google path derives from the RTDN itself, spelled out here."""
    return f"google_play:{purchase_token}:{EVENT_TIME_MILLIS}:{SUBSCRIPTION_PURCHASED}"


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
class TestOneVerifiedPushReachesACommittedRow:
    """The tracer: one signed push, one live Play read, one canonical row, and a 200 after the commit."""

    async def test_a_verified_push_writes_the_subscription_row(
            self, webhook_client, real_google_play_seam, _db_transaction):
        purchase_token = f"purchase-token-{uuid4()}"

        response = await webhook_client.post(PATH, json=_push_body(purchase_token),
                                             headers={"Authorization": f"Bearer {_push_token()}"})

        assert response.status_code == 200, response.text
        subscriptions = await _subscriptions_of(_db_transaction, purchase_token)
        assert len(subscriptions) == 1
        assert subscriptions[0].provider is PurchaseProvider.google_play
        # D-10: the purchase token is the only handle `subscriptionsv2.get` accepts.
        assert subscriptions[0].external_id == purchase_token
        assert subscriptions[0].status is SubscriptionStatus.active
        assert subscriptions[0].tier_id == PAID_TIER_ID

    async def test_the_delivery_records_exactly_one_event_under_the_composite_key(
            self, webhook_client, real_google_play_seam, _db_transaction):
        """OQ-4: the key is derived from the RTDN, so a redelivery of it repeats the same key."""
        purchase_token = f"purchase-token-{uuid4()}"

        response = await webhook_client.post(PATH, json=_push_body(purchase_token),
                                             headers={"Authorization": f"Bearer {_push_token()}"})

        assert response.status_code == 200, response.text
        events = await _events_of(_db_transaction, _replay_key(purchase_token))
        assert len(events) == 1
        assert events[0].event_type == str(SUBSCRIPTION_PURCHASED)
        assert events[0].new_tier_id == PAID_TIER_ID

    async def test_the_play_read_asked_for_the_configured_package_and_this_token(
            self, webhook_client, real_google_play_seam, _db_transaction):
        """The control: a scripted transport that was never called would pass every row assertion above."""
        purchase_token = f"purchase-token-{uuid4()}"

        await webhook_client.post(PATH, json=_push_body(purchase_token),
                                  headers={"Authorization": f"Bearer {_push_token()}"})

        assert len(real_google_play_seam.requests) == 1
        asked = str(real_google_play_seam.requests[0].url)
        assert GOOGLE_PACKAGE_NAME in asked and purchase_token in asked
        assert GOOGLE_PRODUCT_ID in json.dumps(real_google_play_seam.body)


@pytest.mark.asyncio(loop_scope="module")
class TestAnIncompleteDeploymentStillRegistersTheRoute:
    """D-14, D-18. The route set is identical in every environment: present and answering 503, never absent."""

    async def test_an_unconfigured_deployment_answers_503(
            self, webhook_client, unconfigured_google_play_seam):
        response = await webhook_client.post(PATH, json=_push_body("a-purchase-token"),
                                             headers={"Authorization": "Bearer a-token"})

        assert response.status_code == 503
        assert response.json() == UNAVAILABLE

    async def test_both_callback_routes_are_registered_while_the_seam_is_unconfigured(
            self, _app_lifespan, webhook_client, unconfigured_google_play_seam):
        response = await webhook_client.post(PATH, json=_push_body("a-purchase-token"),
                                             headers={"Authorization": "Bearer a-token"})

        assert response.status_code == 503
        registered = {route.path for route in _app_lifespan.routes}
        assert {"/webhooks/app-store", PATH} <= registered
