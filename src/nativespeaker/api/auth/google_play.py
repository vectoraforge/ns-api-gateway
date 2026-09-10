"""The Google Play integration: the Pub/Sub push token, the RTDN body, and the live subscription read.
Log labels come from a closed set: the purchase token, the push token and every Play value are excluded."""
import asyncio
import base64
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote

import google.auth.exceptions
import google.auth.transport.requests
import httpx
import structlog
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.jwt_verifier import TokenVerifier
from nativespeaker.api.auth.store_notifications import RestoredSubscription, VerifiedNotification
from nativespeaker.api.errors import (
    InternalError,
    NotificationRejected,
    ProofRejected,
    Unavailable,
    UnmappedStoreProduct,
)
from nativespeaker.api.schemas.webhooks import PUBSUB_DATA_LIMIT
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

# The floor under the push verifier's rebuild rate. The rebuild runs before any credential is
# checked on a route outside the gateway's JWT policy, so this is what bounds its cost per burst.
PUSH_VERIFIER_REBUILD_INTERVAL_SECONDS = 30.0

# The two Play statuses that say this purchase token is gone, which no later attempt can change.
_GONE_STATUSES = frozenset({404, 410})

# Play's answer for a purchase token it cannot read, and for one that names another application.
# The credential and the scope answer 401 and 403, so this status is the caller's alone.
_UNUSABLE_TOKEN_STATUS = 400

# The stage labels the restore read answers with, and its whole log vocabulary. One label for each
# repair, because the client is told only 503 or 403 and the label is the whole diagnosis.
RESTORE_READ_STAGE = "play_restore_read"
RESTORE_TOKEN_GONE_STAGE = "play_token_gone"
RESTORE_TOKEN_UNUSABLE_STAGE = "play_restore_token_unusable"
RESTORE_UNCONFIGURED_STAGE = "play_restore_unconfigured"
RESTORE_PACKAGE_STAGE = "play_restore_package_unusable"
RESTORE_TRANSPORT_STAGE = "play_restore_transport"
RESTORE_UNPARSEABLE_STAGE = "play_restore_unparseable"

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
    # Optional as defensive typing only: Play gives every entitled term an end.
    # Aware, never a bare `datetime`: a naive value would detonate later, inside `_status_for`.
    expiryTime: AwareDatetime | None = None


class PlaySubscription(BaseModel):
    """The `purchases.subscriptionsv2.get` response, keeping Google's own field names."""
    subscriptionState: str
    # Aware for the same reason as `expiryTime` above: it is written to `core.subscriptions`.
    startTime: AwareDatetime | None = None
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
    """One decoded RTDN: the envelope, and at most one notification body.
    Every other body is kept as an extra rather than declared, so `model_fields_set` names the
    one that arrived even when this build has never seen it. No body's value is ever read."""
    model_config = ConfigDict(extra="allow")

    version: str | None = None
    packageName: str
    eventTimeMillis: int
    subscriptionNotification: SubscriptionNotification | None = None


class PlaySubscriptionSource(Protocol):
    """The Play read seam: one live subscription as this project's value type, or a raise."""

    async def read(self, *, package_name: str, purchase_token: str, event_type: str,
                   notification_uuid: str, signed_at: datetime | None,
                   evaluated_at: datetime) -> VerifiedNotification | None:
        """The `subscriptionsv2.get` call: the value type, `None` for a gone token, or a raise."""
        ...

    async def read_for_restore(self, *, package_name: str, purchase_token: str,
                               evaluated_at: datetime) -> RestoredSubscription:
        """The same call for a client-presented token: the value type, or the refusal it earned."""
        ...


def developer_notification_from(data: str) -> DeveloperNotification | None:
    """The decoded RTDN, or `None` when this verified message carries an unusable body."""
    if not data:
        # Pub/Sub permits an attributes-only message, so this is routine and not a breached bound.
        logger.info("google_play_message_without_data")
        return None
    if len(data) > PUBSUB_DATA_LIMIT:
        # Out of range is as unusable as undecodable; the length alone reaches the log.
        logger.error("google_play_message_out_of_range", length=len(data))
        return None
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


def instant_from_millis(milliseconds: int) -> datetime | None:
    """Convert one of Google's UNIX-millisecond stamps, or `None` when it names no instant."""
    try:
        return datetime.fromtimestamp(milliseconds / 1000, UTC)
    except (ValueError, OverflowError, OSError):
        # Out of range is as unusable as undecodable, and `signed_at` is optional on every path
        # that reads it; the value itself never reaches the log.
        logger.error("google_play_event_time_out_of_range")
        return None


def notification_key_for(purchase_token: str, event_time_millis: int, event_type: str) -> str:
    """The replay key for one delivery, derived from the RTDN so a redelivery repeats it."""
    # The provider prefix keeps a Google key from colliding with an Apple UUID in the shared index.
    return f"google_play:{purchase_token}:{event_time_millis}:{event_type}"


def _names_one_path_segment(value: str) -> bool:
    """`quote` leaves a dot unescaped and httpx deletes a dot segment, so dots alone name nothing."""
    return bool(value.strip("."))


def _play_answer_is_usable(response: httpx.Response) -> bool:
    """Classify one Play answer in the one order that lets nothing fall through to a default."""
    if response.status_code // 100 == 2:
        return True
    if response.status_code in _GONE_STATUSES:
        # Definitive: a token Google says is gone can never resolve, so a retry loops until retention.
        logger.error("google_play_purchase_token_gone", status_code=response.status_code)
        return False
    # Named before the raise: `InternalError` logs nothing of its own, and the access line says only 500.
    logger.error("google_play_read_refused", status_code=response.status_code)
    # Pub/Sub acknowledges five statuses only, so a failed read is redelivered rather than lost.
    raise InternalError


def _status_for(state: str, expiry: datetime | None,
                evaluated_at: datetime) -> SubscriptionStatus:
    """The subscription's status from Play's own state word, which is the only source here."""
    if state == _CANCELED_STATE:
        # Canceled but not expired is still a paid term: Google says so in the field's own text.
        return (SubscriptionStatus.active if expiry is not None and expiry > evaluated_at
                else SubscriptionStatus.expired)
    # Every unlisted value is unentitled, so a state this build has never seen never grants.
    return _STATES.get(state, SubscriptionStatus.expired)


class PubSubPushTokens:
    """The Cloud Pub/Sub push token, verified against Google's keys and pinned to one push identity."""

    # The declared seam, never the concrete class: this class reads nothing of the verifier but
    # `verify`, and a Protocol nothing is typed against catches no wrong-shaped double at all.
    def __init__(self, *, verifier: TokenVerifier | None,
                 build: Callable[[], TokenVerifier | None] | None = None,
                 rebuild_interval_seconds: float = PUSH_VERIFIER_REBUILD_INTERVAL_SECONDS) -> None:
        self._verifier = verifier
        self._build = build
        self._rebuild_lock = asyncio.Lock()
        self._rebuild_interval = rebuild_interval_seconds
        # Zero and not the clock: the first delivery after a failed warm-up rebuilds at once.
        self._next_rebuild = 0.0

    async def verify(self, bearer: str) -> None:
        """Accept one Google-signed push token, or raise."""
        build = self._build
        if self._verifier is None and build is not None:
            # Off the loop, because the builder fetches Google's key set: an unreachable endpoint
            # at boot is transient, and an unconfigured deployment answers None again for free.
            # Serialized and rate-floored, because this runs before the bearer is examined at all:
            # unguarded, one burst of junk tokens spends the whole threadpool `get_identity` shares
            # on its own concurrent fetches, and re-pays that cost for as long as Google is away.
            async with self._rebuild_lock:
                # Re-read under the lock: a rival that just built one leaves nothing to do here.
                if self._verifier is None and time.monotonic() >= self._next_rebuild:
                    # Stamped before the fetch, so the callers held up behind it do not each
                    # inherit the right to make one of their own the moment it fails.
                    self._next_rebuild = time.monotonic() + self._rebuild_interval
                    self._verifier = await run_in_threadpool(build)
        if self._verifier is None:
            raise Unavailable(stage="google_push_verify")

        # `verify` is synchronous and can block on a JWKS fetch, so it never runs on the event loop.
        claims, reason = await run_in_threadpool(self._verifier.verify, bearer)
        if claims is None:
            raise NotificationRejected(stage=str(reason))


class CappedRefreshRequest(google.auth.transport.requests.Request):
    """The credential refresh transport, capped at this module's own timeout.
    `Request.__call__` defaults to 120 s and `jwt_grant` passes no timeout of its own, so an
    uncapped refresh holds one thread of the pool `get_identity` shares for minutes, retried."""

    def __call__(self, url, method="GET", body=None, headers=None,
                 timeout=PLAY_HTTP_TIMEOUT_SECONDS, **kwargs):
        """One capped refresh call; an explicit `timeout` from the library still wins."""
        return super().__call__(url, method, body, headers, timeout, **kwargs)


class PlayDeveloperSubscriptions:
    """The `purchases.subscriptionsv2.get` read, signed per call with this deployment's credential."""

    def __init__(self, *, credential, client: httpx.AsyncClient,
                 products: dict[str, str]) -> None:
        self._credential = credential
        self._client = client
        # Server-controlled reference data, never a value the store supplied.
        self._products = products

    # `evaluated_at` is passed, never read from a clock here: a second reading would let a term
    # cross between `_status_for` and the grant writer's `ends_at`.
    async def read(self, *, package_name: str, purchase_token: str, event_type: str,
                   notification_uuid: str, signed_at: datetime | None,
                   evaluated_at: datetime) -> VerifiedNotification | None:
        """Read this subscription's live state from Play, or answer `None` for a gone token."""
        if self._credential is None:
            raise Unavailable(stage="play_subscriptions_read")
        if not package_name or not _names_one_path_segment(package_name):
            # An absent or dot-only name addresses a URL naming no application, whose 404 would
            # read here as a gone token; refused loudly, because acknowledging drops the delivery.
            logger.error("google_play_unusable_package_name")
            raise InternalError
        if not _names_one_path_segment(purchase_token):
            # `quote` leaves a dot unescaped and httpx removes a dot segment, so `..` addresses a
            # different Play URL; `None`, never a raise, because there is nothing here to read.
            logger.error("google_play_unusable_purchase_token")
            return None

        try:
            response = await self._get(package_name, purchase_token)
        except (httpx.HTTPError, google.auth.exceptions.GoogleAuthError) as failure:
            # A refused credential refresh is no more the caller's fault than a reset connection.
            # The exception's class name, never its text: a URL carrying the purchase token is in there.
            logger.error("google_play_read_transport_failed", failure=type(failure).__name__)
            # A transport failure is the 500 that makes Pub/Sub redeliver this notification.
            raise InternalError from failure
        if not _play_answer_is_usable(response):
            return None
        try:
            subscription = PlaySubscription.model_validate(response.json())
        except ValueError as failure:
            # Both a non-JSON 2xx and a body this build cannot read arrive as `ValueError`; the
            # class name alone, because the body and pydantic's echo of it carry Play's own values.
            logger.error("google_play_read_unparseable", failure=type(failure).__name__)
            raise InternalError from None

        product_id, tier_id, expiry = self._product_of(subscription)
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
            tier_id=tier_id,
            attribution_token=(None if identifiers is None
                               else identifiers.obfuscatedExternalAccountId),
            status=_status_for(subscription.subscriptionState, expiry, evaluated_at),
            signed_at=signed_at,
            purchased_at=subscription.startTime,
            expires_at=expiry,
            grace_period_expires_at=expiry if in_grace else None,
        )

    async def read_for_restore(self, *, package_name: str, purchase_token: str,
                               evaluated_at: datetime) -> RestoredSubscription:
        """Read the state of one client-presented purchase token, or raise the refusal it earned."""
        # Each refusal is classified here, so this path answers 503 where the webhook answers 500.
        # `UnmappedStoreProduct` is the one exception, and it is re-raised by name below.
        if self._credential is None:
            raise Unavailable(stage=RESTORE_UNCONFIGURED_STAGE)
        if not package_name or not _names_one_path_segment(package_name):
            # An absent or dot-only application name is an unusable deployment, never a refusal.
            raise Unavailable(stage=RESTORE_PACKAGE_STAGE)
        if not _names_one_path_segment(purchase_token):
            # No live purchase token is dots alone, so this is a rejected proof and never a read.
            raise ProofRejected(stage=RESTORE_TOKEN_GONE_STAGE)

        try:
            response = await self._get(package_name, purchase_token)
        except (httpx.HTTPError, google.auth.exceptions.GoogleAuthError) as failure:
            # The app retries later, so a transport failure is a 503 and never the webhook's 500.
            # A refused credential refresh is the same outcome, reached without any httpx error.
            raise Unavailable(stage=RESTORE_TRANSPORT_STAGE) from failure

        if response.status_code in _GONE_STATUSES:
            # A gone token is a rejected proof, not a server failure. The package name travels in
            # the URL path, so a token of another application answers 404 and arrives here too.
            raise ProofRejected(stage=RESTORE_TOKEN_GONE_STAGE)
        if response.status_code == _UNUSABLE_TOKEN_STATUS:
            # Play's answer for a token that does not parse, or that names another application:
            # the caller's proof, never this deployment's credential, and no retry changes it.
            raise ProofRejected(stage=RESTORE_TOKEN_UNUSABLE_STAGE)
        if response.status_code // 100 != 2:
            # Our own two words, never Play's status: the 401 and 403 left here are a credential or
            # scope an operator repairs, and a 5xx is Play's own outage, which is waited out.
            raise Unavailable(stage=RESTORE_READ_STAGE,
                              cause="refused" if response.status_code // 100 == 4 else "failed")

        try:
            subscription = PlaySubscription.model_validate(response.json())
        except ValueError:
            # A 2xx this build cannot read is as unusable as no answer at all. The cause is
            # dropped rather than chained: its text carries the Play values this module excludes.
            raise Unavailable(stage=RESTORE_UNPARSEABLE_STAGE) from None
        try:
            product_id, tier_id, expiry = self._product_of(subscription)
        except UnmappedStoreProduct:
            # D-11: an unmapped product is an operator error and stays a 500 on both paths.
            raise
        except InternalError:
            # A line item count this build cannot read is as unusable as a body it cannot parse,
            # and the webhook's 500 is not an answer this route gives the app.
            raise Unavailable(stage=RESTORE_UNPARSEABLE_STAGE) from None
        # Google carries no separate grace field, so in grace this expiry is the end of the window.
        in_grace = subscription.subscriptionState == GRACE_STATE
        identifiers = subscription.externalAccountIdentifiers
        return RestoredSubscription(
            provider=PurchaseProvider.google_play,
            # The purchase token: `subscriptionsv2.get` accepts no other handle for this subscription.
            external_id=purchase_token,
            product_id=product_id,
            tier_id=tier_id,
            attribution_token=(None if identifiers is None
                               else identifiers.obfuscatedExternalAccountId),
            status=_status_for(subscription.subscriptionState, expiry, evaluated_at),
            purchased_at=subscription.startTime,
            expires_at=expiry,
            grace_period_expires_at=expiry if in_grace else None,
        )

    def _product_of(self, subscription: PlaySubscription) -> tuple[str, str, datetime | None]:
        """The line item's product, the tier it maps to, and the end of its term."""
        if len(subscription.lineItems) != 1:
            # Refused before any write: the tier and the term are read off this one element, and
            # Google documents no ordering, so element zero of a longer list is a guess.
            logger.error("google_play_unexpected_line_item_count",
                         count=len(subscription.lineItems))
            raise InternalError
        line_item = subscription.lineItems[0]
        product_id = line_item.productId
        if product_id is None or product_id not in self._products:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.google_play, str(product_id))
        return product_id, self._products[product_id], line_item.expiryTime

    async def _get(self, package_name: str, purchase_token: str) -> httpx.Response:
        """Send one signed read; each entry point classifies a failed read its own way.
        A refused refresh leaves as `GoogleAuthError`, which both entry points catch."""
        if not self._credential.valid:
            # `refresh` is synchronous and can block on a token fetch, so it never runs on the loop.
            # Capped like the httpx client and the JWKS client: this is the one call that holds a
            # real OS thread, and google-auth's own default would hold it for 120 s per attempt.
            await run_in_threadpool(self._credential.refresh, CappedRefreshRequest())
        # Escaping confines each value to one segment, except dots, which both entry points refuse.
        return await self._client.get(
            PLAY_URL.format(package_name=quote(package_name, safe=""),
                            purchase_token=quote(purchase_token, safe="")),
            headers={"Authorization": f"Bearer {self._credential.token}"})
