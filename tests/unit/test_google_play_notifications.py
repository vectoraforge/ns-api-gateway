"""The Google state map, the arms that answer without writing, and the push-token claim pins.
A throwaway keypair mints the push tokens and an `httpx.MockTransport` answers the Play read.
Untested by construction: only whether Google's live tokens and answers match Google's own shapes."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from nativespeaker.api.auth.google_play import PlayDeveloperSubscriptions
from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus

PACKAGE_NAME = "com.example.nativespeaker"
PRODUCT_ID = "com.example.nativespeaker.subscription.monthly"
TIER_ID = "paid"
PURCHASE_TOKEN = "opaque-play-purchase-token"
ORDER_ID = "GPA.0000-0000-0000-00000"
ATTRIBUTION_TOKEN = "8f4d1a2e-0000-4000-8000-000000000002"
EVENT_TYPE = "4"
NOTIFICATION_KEY = f"google_play:{PURCHASE_TOKEN}:1780000000000:{EVENT_TYPE}"

# One captured instant for every case below, so no assertion here depends on the wall clock.
EVALUATED_AT = datetime(2026, 6, 1, tzinfo=UTC)
PURCHASED_AT = EVALUATED_AT - timedelta(days=30)
SIGNED_AT = EVALUATED_AT - timedelta(minutes=1)
UNEXPIRED = EVALUATED_AT + timedelta(days=10)
LAPSED = EVALUATED_AT - timedelta(days=1)

# Google's `SubscriptionState` enum, all nine values verbatim.
PUBLISHED_STATES = (
    "SUBSCRIPTION_STATE_UNSPECIFIED",
    "SUBSCRIPTION_STATE_PENDING",
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_PAUSED",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
    "SUBSCRIPTION_STATE_ON_HOLD",
    "SUBSCRIPTION_STATE_CANCELED",
    "SUBSCRIPTION_STATE_EXPIRED",
    "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED",
)

# A tenth value this build has never seen, which is the arm that must not be entitled.
UNKNOWN_STATE = "SUBSCRIPTION_STATE_SOMETHING_GOOGLE_SHIPS_LATER"


class _FakeCredential:
    """ADC as the Play read uses it: already valid, so a refresh here is a failure, not a fixture."""

    valid = True
    token = "play-access-token"

    def refresh(self, request):
        raise AssertionError("a valid credential must not be refreshed")


def _subscription_body(state: str, *, expiry: datetime | None = None,
                       product_id: str | None = PRODUCT_ID) -> dict:
    """One `subscriptionsv2.get` answer in Google's own field names."""
    line_item: dict = {"productId": product_id}
    if expiry is not None:
        line_item["expiryTime"] = expiry.isoformat()
    return {"subscriptionState": state,
            "startTime": PURCHASED_AT.isoformat(),
            "latestOrderId": ORDER_ID,
            "lineItems": [line_item],
            "externalAccountIdentifiers": {"obfuscatedExternalAccountId": ATTRIBUTION_TOKEN}}


def _answering(body: dict, status_code: int = 200):
    """A Play transport that answers every read with this one status and body."""
    return lambda _request: httpx.Response(status_code, json=body)


def _play_reader(handler, *, products: dict[str, str] | None = None) -> PlayDeveloperSubscriptions:
    """The real Play read class over a stubbed transport and a captured instant."""
    return PlayDeveloperSubscriptions(
        credential=_FakeCredential(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        products={PRODUCT_ID: TIER_ID} if products is None else products,
        evaluated_at_source=lambda: EVALUATED_AT)


async def _read(state: str, *, expiry: datetime | None = None) -> VerifiedNotification:
    """Read one subscription in this state through the real class, and return the value type."""
    reader = _play_reader(_answering(_subscription_body(state, expiry=expiry)))
    return await reader.read(package_name=PACKAGE_NAME, purchase_token=PURCHASE_TOKEN,
                             event_type=EVENT_TYPE, notification_uuid=NOTIFICATION_KEY,
                             signed_at=SIGNED_AT)


class TestTheStateMap:
    """Nine published states and one unknown state, each with the status it must produce."""

    @pytest.mark.parametrize(("state", "expiry", "expected"), [
        ("SUBSCRIPTION_STATE_ACTIVE", UNEXPIRED, SubscriptionStatus.active),
        ("SUBSCRIPTION_STATE_IN_GRACE_PERIOD", UNEXPIRED, SubscriptionStatus.grace_period),
        # On hold is Play's billing retry: the paid term ended and Google is still charging.
        ("SUBSCRIPTION_STATE_ON_HOLD", LAPSED, SubscriptionStatus.billing_retry),
        # This project's enum carries no paused word, and the auto-resume arrives as a fresh active.
        ("SUBSCRIPTION_STATE_PAUSED", UNEXPIRED, SubscriptionStatus.expired),
        # Canceled but not expired is still a paid term: Google says so in the field's own text.
        ("SUBSCRIPTION_STATE_CANCELED", UNEXPIRED, SubscriptionStatus.active),
        ("SUBSCRIPTION_STATE_CANCELED", LAPSED, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_CANCELED", EVALUATED_AT, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_CANCELED", None, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_EXPIRED", LAPSED, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_PENDING", None, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED", None, SubscriptionStatus.expired),
        ("SUBSCRIPTION_STATE_UNSPECIFIED", UNEXPIRED, SubscriptionStatus.expired),
        (UNKNOWN_STATE, UNEXPIRED, SubscriptionStatus.expired),
    ])
    async def test_each_state_produces_its_status(self, state, expiry, expected):
        assert (await _read(state, expiry=expiry)).status is expected

    async def test_a_state_this_build_has_never_seen_is_not_entitled(self):
        """The fall-through, stated on its own: an unlisted value never grants."""
        notification = await _read(UNKNOWN_STATE, expiry=UNEXPIRED)

        assert notification.status is SubscriptionStatus.expired
        assert notification.provider is PurchaseProvider.google_play

    @pytest.mark.parametrize("state", [*PUBLISHED_STATES, UNKNOWN_STATE])
    async def test_no_state_produces_revoked(self, state):
        """`revoked` is unreachable here: `subscriptionsv2` exposes no citable revocation signal."""
        assert (await _read(state, expiry=UNEXPIRED)).status is not SubscriptionStatus.revoked


class TestTheGraceWindowGoogleDoesNotName:
    """Google carries no grace field, so in grace the line item's own expiry ends the window."""

    async def test_a_grace_period_subscription_carries_the_end_of_its_window(self):
        notification = await _read("SUBSCRIPTION_STATE_IN_GRACE_PERIOD", expiry=UNEXPIRED)

        assert notification.status is SubscriptionStatus.grace_period
        assert notification.grace_period_expires_at == UNEXPIRED
        assert notification.grace_period_expires_at == notification.expires_at
        assert notification.expires_at is not None

    @pytest.mark.parametrize("state", [state for state in PUBLISHED_STATES
                                       if state != "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"])
    async def test_every_other_state_carries_no_grace_window(self, state):
        assert (await _read(state, expiry=UNEXPIRED)).grace_period_expires_at is None
