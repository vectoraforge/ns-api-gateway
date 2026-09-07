"""The Google Play integration: the Pub/Sub push token, the RTDN body, and the live subscription read.
Log labels come from a closed set: the purchase token, the push token and every Play value are excluded."""
import base64
from datetime import UTC, datetime
from typing import Protocol

import google.auth.transport.requests
import httpx
import structlog
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.errors import (
    InternalError,
    NotificationRejected,
    Unavailable,
    UnmappedStoreProduct,
)
from nativespeaker.api.tables.purchases import PurchaseProvider, SubscriptionStatus

logger = structlog.get_logger()

# The push token is a Google OpenID Connect ID token, so it carries Google's own issuer and keys.
GOOGLE_ISSUER = "https://accounts.google.com"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

# The one scope `purchases.subscriptionsv2.get` accepts.
PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

# The purchase token is the only handle the read accepts, so it travels in the path.
PLAY_URL = ("https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            "{package_name}/purchases/subscriptionsv2/tokens/{purchase_token}")

# A per-request option because every call sends one bearer and reads one subscription.
PLAY_HTTP_TIMEOUT_SECONDS = 8

# The two Play statuses that say this purchase token is gone, which no later attempt can change.
_GONE_STATUSES = frozenset({404, 410})

# The envelope fields every RTDN carries, so the rest of the set names the bodies it carries.
_ENVELOPE_FIELDS = frozenset({"version", "packageName", "eventTimeMillis"})

# The state Google is in during grace, whose line item expiry is also the end of the grace window.
GRACE_STATE = "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"

# Canceled is the one value whose answer depends on a date, so it is decided before this lookup.
_CANCELED_STATE = "SUBSCRIPTION_STATE_CANCELED"

# The four states that answer from Google's word alone. Every literal carries Google's own prefix.
_STATES = {
    "SUBSCRIPTION_STATE_ACTIVE": SubscriptionStatus.active,
    GRACE_STATE: SubscriptionStatus.grace_period,
    # On hold is Play's billing retry: the paid term ended and Google is still charging for it.
    "SUBSCRIPTION_STATE_ON_HOLD": SubscriptionStatus.billing_retry,
    # This enum carries no paused word, and the auto-resume arrives as a fresh active state.
    "SUBSCRIPTION_STATE_PAUSED": SubscriptionStatus.expired,
}


class PlayExternalAccountIdentifiers(BaseModel):
    """The buyer identifiers Play carries, which this project resolves against its own token."""
    obfuscatedExternalAccountId: str | None = None


class PlaySubscriptionLineItem(BaseModel):
    """One line item of a Play subscription: the product bought, and when its term ends."""
    productId: str | None = None
    # Optional as defensive typing only: Play gives every entitled term an end, so no producer sends None here.
    expiryTime: datetime | None = None


class PlaySubscription(BaseModel):
    """The `purchases.subscriptionsv2.get` response, keeping Google's own field names."""
    subscriptionState: str
    startTime: datetime | None = None
    latestOrderId: str | None = None
    # Parsed and not acted on: an upgrade's old token is the restore route's to read.
    linkedPurchaseToken: str | None = None
    lineItems: list[PlaySubscriptionLineItem] = Field(default_factory=list)
    externalAccountIdentifiers: PlayExternalAccountIdentifiers | None = None


class SubscriptionNotification(BaseModel):
    """The subscription body of one RTDN: the type, and the purchase token it happened to."""
    version: str | None = None
    notificationType: int
    purchaseToken: str


class DeveloperNotification(BaseModel):
    """One decoded RTDN: the envelope, and at most one notification body."""
    version: str | None = None
    packageName: str
    eventTimeMillis: int
    subscriptionNotification: SubscriptionNotification | None = None
    oneTimeProductNotification: dict | None = None
    voidedPurchaseNotification: dict | None = None
    pendingRefundReviewNotification: dict | None = None
    testNotification: dict | None = None


class PlaySubscriptionSource(Protocol):
    """The Play read seam: one live subscription as this project's value type, or a raise."""

    async def read(self, *, package_name: str, purchase_token: str, event_type: str,
                   notification_uuid: str, signed_at: datetime | None) -> VerifiedNotification | None:
        """The `subscriptionsv2.get` call: the value type, `None` for a gone token, or a raise."""
        ...


def developer_notification_from(data: str) -> DeveloperNotification | None:
    """The decoded RTDN, or `None` when this verified message carries an unusable body."""
    try:
        return DeveloperNotification.model_validate_json(base64.b64decode(data, validate=True))
    except ValueError:
        # A body that does not parse never will, so answering 200 is what stops the redelivery.
        logger.error("google_play_message_undecodable")
        return None


def subscription_notification_from(notification: DeveloperNotification) -> SubscriptionNotification | None:
    """The subscription body of one RTDN, or `None` when this delivery carries another body."""
    if notification.subscriptionNotification is None:
        # Presence, never a list of names: a body Google adds later must not fall through here.
        logger.info("google_play_notification_ignored",
                    bodies=sorted(set(notification.model_fields_set) - _ENVELOPE_FIELDS))
    return notification.subscriptionNotification


def instant_from_millis(milliseconds: int) -> datetime:
    """Convert one of Google's UNIX-millisecond stamps into an aware instant."""
    return datetime.fromtimestamp(milliseconds / 1000, UTC)


def notification_key_for(purchase_token: str, event_time_millis: int, event_type: str) -> str:
    """The replay key for one delivery, derived from the RTDN so a redelivery repeats it."""
    # The provider prefix keeps a Google key from colliding with an Apple UUID in the shared index.
    return f"google_play:{purchase_token}:{event_time_millis}:{event_type}"


def _play_answer_is_usable(response: httpx.Response) -> bool:
    """Classify one Play answer in the one order that lets nothing fall through to a default."""
    if response.status_code // 100 == 2:
        return True
    if response.status_code in _GONE_STATUSES:
        # Definitive: a token Google says is gone can never resolve, so a retry loops until retention.
        logger.error("google_play_purchase_token_gone", status_code=response.status_code)
        return False
    # Pub/Sub acknowledges five statuses only, so a failed read is redelivered rather than lost.
    raise InternalError


def _status_for(state: str, expiry: datetime | None,
                evaluated_at: datetime) -> SubscriptionStatus:
    """The subscription's status from Play's own state word, which is the only source here."""
    if state == _CANCELED_STATE:
        # Canceled but not expired is still a paid term: Google says so in the field's own text.
        return (SubscriptionStatus.active if expiry is not None and expiry > evaluated_at
                else SubscriptionStatus.expired)
    # `revoked` is unreachable on this path: `subscriptionsv2` publishes no revocation signal, and
    # a revoked subscription reports SUBSCRIPTION_STATE_EXPIRED with the reason in its event type.
    # Every unlisted value is unentitled, so a state this build has never seen never grants.
    return _STATES.get(state, SubscriptionStatus.expired)


class PubSubPushTokens:
    """The Cloud Pub/Sub push token, verified against Google's keys and pinned to one push identity."""

    def __init__(self, *, verifier: JWTVerifier | None) -> None:
        self._verifier = verifier

    async def verify(self, bearer: str) -> None:
        """Accept one Google-signed push token, or raise."""
        if self._verifier is None:
            raise Unavailable(stage="google_push_verify")

        # `verify` is synchronous and can block on a JWKS fetch, so it never runs on the event loop.
        claims, reason = await run_in_threadpool(self._verifier.verify, bearer)
        if claims is None:
            raise NotificationRejected(stage=str(reason))


class PlayDeveloperSubscriptions:
    """The `purchases.subscriptionsv2.get` read, signed per call with this deployment's credential."""

    def __init__(self, *, credential, client: httpx.AsyncClient, products: dict[str, str],
                 evaluated_at_source) -> None:
        self._credential = credential
        self._client = client
        # Server-controlled reference data, never a value the store supplied.
        self._products = products
        self._evaluated_at_source = evaluated_at_source

    async def read(self, *, package_name: str, purchase_token: str, event_type: str,
                   notification_uuid: str, signed_at: datetime | None) -> VerifiedNotification | None:
        """Read this subscription's live state from Play, or answer `None` for a gone token."""
        if self._credential is None:
            raise Unavailable(stage="play_subscriptions_read")

        response = await self._get(package_name, purchase_token)
        if not _play_answer_is_usable(response):
            return None
        subscription = PlaySubscription.model_validate(response.json())

        line_item = subscription.lineItems[0] if subscription.lineItems else None
        product_id = None if line_item is None else line_item.productId
        if product_id is None or product_id not in self._products:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.google_play, str(product_id))

        expiry = None if line_item is None else line_item.expiryTime
        # Google carries no separate grace field, so in grace this expiry is the end of the window.
        # Left as None, every grace-period subscriber's grant would be written with no end date.
        in_grace = subscription.subscriptionState == GRACE_STATE
        identifiers = subscription.externalAccountIdentifiers
        return VerifiedNotification(
            provider=PurchaseProvider.google_play,
            notification_uuid=notification_uuid,
            event_type=event_type,
            # The purchase token: `subscriptionsv2.get` accepts no other handle for this subscription.
            external_id=purchase_token,
            transaction_id=subscription.latestOrderId,
            product_id=product_id,
            tier_id=self._products[product_id],
            attribution_token=(None if identifiers is None
                               else identifiers.obfuscatedExternalAccountId),
            status=_status_for(subscription.subscriptionState, expiry,
                               self._evaluated_at_source()),
            signed_at=signed_at,
            purchased_at=subscription.startTime,
            expires_at=expiry,
            grace_period_expires_at=expiry if in_grace else None,
        )

    async def _get(self, package_name: str, purchase_token: str) -> httpx.Response:
        """Send one signed read; a transport failure is the 500 that makes Pub/Sub redeliver."""
        if not self._credential.valid:
            # `refresh` is synchronous and can block on a token fetch, so it never runs on the loop.
            await run_in_threadpool(self._credential.refresh,
                                    google.auth.transport.requests.Request())
        try:
            return await self._client.get(
                PLAY_URL.format(package_name=package_name, purchase_token=purchase_token),
                headers={"Authorization": f"Bearer {self._credential.token}"})
        except httpx.HTTPError as failure:
            raise InternalError from failure
