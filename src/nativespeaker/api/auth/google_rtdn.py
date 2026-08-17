"""`POST /webhooks/google-play/rtdn`: how a Pub/Sub push is authenticated, and what its body is
good for.

Google does not call this backend. Real-Time Developer Notifications arrive through a Cloud
Pub/Sub push subscription, which attaches a Google-signed OIDC JWT for a service account the
operator designates. That token is a Google service-account token, not a Firebase ID token, and
this backend is what verifies it — signature, issuer, expiry, audience, and the one dedicated
push service account. Once it verifies, the message body is a trigger and nothing more: the
authoritative subscription state comes from the Play Developer API, and every mutation is derived
from that response.
"""

import base64
import binascii
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import jwt

from nativespeaker.api.auth.callbacks import (
    CallbackRequest,
    ProviderCallbackError,
    pubsub_oidc_verifier,
)
from nativespeaker.api.auth.routes import PROVIDER_CALLBACK_ROUTES

# The route the Play RTDN push lands on, read from the registry that owns the route list.
RTDN_METHOD, RTDN_PATH = next(
    (route.method, route.path) for route in PROVIDER_CALLBACK_ROUTES
    if route.verifier == "pubsub_oidc")

# The status codes this route answers with. Pub/Sub is not an app client, so the route reports
# plain HTTP status codes rather than the shared client-visible error classes.
RTDN_ACCEPTED = 200
RTDN_UNAUTHENTICATED = 401
RTDN_INTERNAL_FAILURE = 500

# Google's OIDC issuer for service-account identity tokens, in both spellings Google mints.
GOOGLE_OIDC_ISSUERS: frozenset[str] = frozenset({
    "https://accounts.google.com", "accounts.google.com"})

# How the notification reaches the backend, and what credential kind it carries. Neither is a
# Firebase ID token, and no Firebase verifier runs on this route.
RTDN_DELIVERY: str = "cloud_pubsub_push_subscription"
RTDN_CREDENTIAL_KIND: str = "google_service_account_oidc_jwt"

# The authoritative lookup every mutation is derived from.
AUTHORITATIVE_LOOKUP: str = "play_developer_api.purchases.subscriptionsv2.get"

# Fields the pushed message carries that a mutation must never be derived from directly. The
# purchase token is a lookup input; nothing in the message is a mutation input.
UNTRUSTED_MESSAGE_FIELDS: frozenset[str] = frozenset({
    "purchaseToken", "subscriptionId", "productId", "notificationType", "priceChangeState",
    "subscriptionState", "expiryTime", "linkedPurchaseToken",
})


class RtdnContractError(RuntimeError):
    """A rule this route states was about to be broken. A server-side bug, not Google's input."""


class RtdnInternalError(RuntimeError):
    """The notification's effect could not be made durable. The route answers 5xx so Pub/Sub
    redelivers on its own schedule."""


class RtdnRejectionReason(StrEnum):
    """Why a push was not authenticated. Internal detail: the route answers a bare 401."""
    missing_token = "missing_token"
    malformed = "malformed"
    bad_signature = "bad_signature"
    issuer_mismatch = "issuer_mismatch"
    audience_mismatch = "audience_mismatch"
    expired = "expired"
    service_account_mismatch = "service_account_mismatch"
    email_unverified = "email_unverified"


class RtdnAuthenticationError(RuntimeError):
    """The push was not authenticated: HTTP 401, no ingestion, and no business logic run."""

    def __init__(self, reason: RtdnRejectionReason) -> None:
        self.reason = reason
        super().__init__(str(reason))


# --- Configuration --------------------------------------------------------------------------------

# The configuration keys the route registry already requires of a registered RTDN route, read from
# that entry so the two cannot drift.
RTDN_REQUIRED_CONFIG: tuple[str, ...] = next(
    route.required_config for route in PROVIDER_CALLBACK_ROUTES if route.verifier == "pubsub_oidc")

# The server-controlled product mapping the expected subscription is validated against. The
# message never nominates which products this deployment sells.
RTDN_PRODUCT_MAP_KEY: str = "google_play.product_id_to_tier"


@dataclass(frozen=True, slots=True)
class PlayRtdnConfig:
    """What the RTDN route is configured with: the expected Play package, the exact audience this
    push subscription mints tokens for, the one dedicated push service account, and the products
    this deployment expects a subscription notification about."""
    package_name: str
    pubsub_audience: str
    pubsub_service_account_email: str
    product_ids: frozenset[str] = frozenset()


def _lookup(config: Mapping[str, Any], dotted_key: str) -> Any:
    node: Any = config
    for part in dotted_key.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def play_rtdn_config(resolved: Mapping[str, Any]) -> PlayRtdnConfig:
    """Read the RTDN route's configuration, requiring every key the route registry declares plus
    the server-controlled product map the expected subscription is checked against."""
    values: dict[str, Any] = {}
    for key in RTDN_REQUIRED_CONFIG:
        value = _lookup(resolved, key)
        if value in (None, "", [], {}):
            raise RtdnContractError(f"{RTDN_PATH} is registered without {key}")
        values[key.split(".")[-1]] = str(value)
    products = _lookup(resolved, RTDN_PRODUCT_MAP_KEY) or {}
    if not products:
        raise RtdnContractError(f"{RTDN_PATH} is registered without {RTDN_PRODUCT_MAP_KEY}")
    return PlayRtdnConfig(package_name=values["package_name"],
                          pubsub_audience=values["pubsub_audience"],
                          pubsub_service_account_email=values["pubsub_service_account_email"],
                          product_ids=frozenset(str(product) for product in products))


# --- The Pub/Sub OIDC credential -------------------------------------------------------------------


def pubsub_push_credential(authorization: Sequence[str],
                           *, firebase_verifier: object | None = None) -> str:
    """Google does not call the backend directly.

    The notification arrives through a Cloud Pub/Sub push subscription, which attaches a
    Google-signed OIDC JWT as an ordinary `Authorization: Bearer` credential minted for the
    service account the operator designates. That token is a Google service-account token, not a
    Firebase ID token: no Firebase verifier is offered it, and the backend is what verifies it.
    """
    # [impl->req~restore-google-rtdn-pubsub-oidc-token~1]
    if firebase_verifier is not None:
        raise RtdnContractError(
            f"{RTDN_CREDENTIAL_KIND} is not a Firebase ID token and is not verified as one")
    if RTDN_DELIVERY != "cloud_pubsub_push_subscription":
        raise RtdnContractError("RTDN reaches the backend through a Pub/Sub push subscription")
    captured: list[str] = []
    extract = pubsub_oidc_verifier(captured.append)
    try:
        extract(CallbackRequest(RTDN_METHOD, RTDN_PATH, authorization=tuple(authorization)))
    except ProviderCallbackError:
        raise RtdnAuthenticationError(RtdnRejectionReason.missing_token) from None
    return captured[0]


@dataclass(frozen=True, slots=True)
class OidcClaims:
    """What the verifying decode returned. Claims are never read without verifying first."""
    issuer: str
    audience: str
    email: str
    email_verified: bool


class PubSubOidcVerifier:
    """The backend's own verification of the Pub/Sub push credential: RS256 signature against
    Google's published signing keys, `iss` one of Google's OIDC issuers, `exp` temporal validity,
    and `aud` exactly the audience configured for this push subscription — then the service-account
    email claim against the one dedicated push service account, with `email_verified` required.
    """

    def __init__(self, *,
                 audience: str,
                 service_account_email: str,
                 key_resolver: Callable[[str], Any],
                 leeway: int = 30,
                 issuers: frozenset[str] = GOOGLE_OIDC_ISSUERS) -> None:
        self._audience = audience
        self._service_account_email = service_account_email
        self._key_resolver = key_resolver
        self._leeway = leeway
        self._issuers = issuers

    def verify(self, token: str) -> OidcClaims:
        """Verify the push credential and return its claims, or raise `RtdnAuthenticationError`."""
        # The signing key comes from Google's published key set; the verifying decode then pins
        # the issuer, the expiry and the audience. `aud` is compared against the exact configured
        # audience for this push subscription, never a prefix or a set of acceptable values.
        # [impl->req~restore-google-verify-token-signature-audience~1]
        if not token:
            raise RtdnAuthenticationError(RtdnRejectionReason.missing_token)
        try:
            signing_key = self._key_resolver(token)
        except Exception:
            raise RtdnAuthenticationError(RtdnRejectionReason.bad_signature) from None
        try:
            claims = jwt.decode(token,
                                signing_key,
                                algorithms=["RS256"],
                                audience=self._audience,
                                issuer=sorted(self._issuers),
                                leeway=self._leeway,
                                options={"require": ["exp", "iat", "aud", "iss"],
                                         "verify_signature": True})
        except jwt.ExpiredSignatureError:
            raise RtdnAuthenticationError(RtdnRejectionReason.expired) from None
        except jwt.InvalidIssuerError:
            raise RtdnAuthenticationError(RtdnRejectionReason.issuer_mismatch) from None
        except jwt.InvalidAudienceError:
            raise RtdnAuthenticationError(RtdnRejectionReason.audience_mismatch) from None
        except jwt.InvalidSignatureError:
            raise RtdnAuthenticationError(RtdnRejectionReason.bad_signature) from None
        except Exception:
            raise RtdnAuthenticationError(RtdnRejectionReason.malformed) from None
        if str(claims.get("aud") or "") != self._audience:
            raise RtdnAuthenticationError(RtdnRejectionReason.audience_mismatch)
        return self._assert_push_service_account(claims)

    def _assert_push_service_account(self, claims: Mapping[str, Any]) -> OidcClaims:
        """The token's service-account email claim must be the one dedicated push service account
        provisioned for this subscription, and `email_verified` is required: a Google-signed token
        for any other service account opens nothing here."""
        # [impl->req~restore-google-verify-service-account-email~1]
        email = str(claims.get("email") or "")
        verified = claims.get("email_verified")
        if email != self._service_account_email:
            raise RtdnAuthenticationError(RtdnRejectionReason.service_account_mismatch)
        if verified is not True:
            raise RtdnAuthenticationError(RtdnRejectionReason.email_unverified)
        return OidcClaims(issuer=str(claims["iss"]), audience=str(claims["aud"]),
                          email=email, email_verified=True)


# --- The pushed message ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PubSubPushMessage:
    """One Pub/Sub push: the message ID redelivery is keyed on, and the RTDN payload it wraps."""
    message_id: str
    payload: Mapping[str, Any]

    @property
    def package_name(self) -> str:
        return str(self.payload.get("packageName") or "")

    @property
    def subscription_product_id(self) -> str:
        notification = self.payload.get("subscriptionNotification")
        if not isinstance(notification, Mapping):
            return ""
        return str(notification.get("subscriptionId") or "")

    @property
    def purchase_token(self) -> str:
        notification = self.payload.get("subscriptionNotification")
        if not isinstance(notification, Mapping):
            return ""
        return str(notification.get("purchaseToken") or "")


def decode_push_body(body: Mapping[str, Any]) -> PubSubPushMessage:
    """Decode the Pub/Sub push envelope into its message ID and RTDN payload.

    An envelope that does not decode is not a notification this backend can act on, and is
    refused on the authentication path rather than half-ingested.
    """
    message = body.get("message")
    if not isinstance(message, Mapping):
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed)
    message_id = str(message.get("messageId") or message.get("message_id") or "")
    raw = message.get("data")
    if not message_id or not isinstance(raw, str):
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed)
    try:
        payload = json.loads(base64.b64decode(raw, validate=True))
    except (ValueError, binascii.Error):
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed) from None
    if not isinstance(payload, Mapping):
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed)
    return PubSubPushMessage(message_id=message_id, payload=payload)


# --- The ingestion ledger --------------------------------------------------------------------------


@dataclass(slots=True)
class RtdnLedger:
    """What this delivery actually did, in order. Authentication runs against an empty ledger, so
    "no ingestion and no business logic run first" is checked where it is claimed."""
    steps: list[str] = field(default_factory=list)
    committed: bool = False

    def record(self, step: str) -> None:
        if self.committed:
            raise RtdnContractError(f"{step} runs before the delivery is acknowledged")
        self.steps.append(step)

    def commit(self) -> None:
        self.committed = True

    @property
    def ingested(self) -> bool:
        return bool(self.steps)


def authenticate_rtdn_push(authorization: Sequence[str],
                           *,
                           verifier: PubSubOidcVerifier,
                           ledger: RtdnLedger) -> OidcClaims:
    """Authenticate the push before anything else happens: no business logic runs first."""
    # [impl->req~restore-google-auth-failure-401~1]
    if ledger.ingested:
        raise RtdnContractError(f"authentication runs before {ledger.steps}")
    token = pubsub_push_credential(authorization)
    return verifier.verify(token)


# --- Package, expected subscription, and redelivery -------------------------------------------------


def validate_and_dedupe(message: PubSubPushMessage,
                        *,
                        config: PlayRtdnConfig,
                        already_applied: bool,
                        ledger: RtdnLedger) -> str | None:
    """Validate the expected Play package name and the expected subscription, and deduplicate on
    the Pub/Sub message ID.

    That message ID is the observation's `audit.subscription_events.notification_uuid`, so a
    redelivery is recognized against the same column Apple's notification UUID uses and repeats no
    side effect: the caller acknowledges it again without applying anything.
    """
    # [impl->req~restore-google-validate-package-and-dedupe~1]
    if message.package_name != config.package_name:
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed)
    product = message.subscription_product_id
    if not product or product not in config.product_ids:
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed)
    if not message.purchase_token:
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed)
    if already_applied:
        return None
    ledger.record("dedupe:notification_uuid")
    return message.message_id


# The column the Pub/Sub message ID is recorded as, so redelivery detection has one home.
NOTIFICATION_UUID_COLUMN: str = "audit.subscription_events.notification_uuid"


# --- The message is a trigger only -------------------------------------------------------------------


async def authoritative_subscription_state(
        message: PubSubPushMessage,
        *,
        fetch: Callable[[str, str], Awaitable[Mapping[str, Any]]],
        config: PlayRtdnConfig,
        ledger: RtdnLedger) -> Mapping[str, Any]:
    """The message body is a trigger only.

    Once the token verifies, the authoritative subscription state is fetched from the Google Play
    Developer API (`purchases.subscriptionsv2.get`) and every mutation is derived from that
    response. The purchase token in the message is a lookup input and the package name comes from
    configuration, so a forged message that somehow passed authentication could only trigger a
    truthful lookup.
    """
    # [impl->req~restore-google-message-is-trigger-only~1]
    token = message.purchase_token
    if not token:
        raise RtdnAuthenticationError(RtdnRejectionReason.malformed)
    ledger.record(f"lookup:{AUTHORITATIVE_LOOKUP}")
    state = await fetch(config.package_name, token)
    if not isinstance(state, Mapping) or not state:
        raise RtdnInternalError(f"{AUTHORITATIVE_LOOKUP} returned no authoritative state")
    return state


def mutation_inputs(state: Mapping[str, Any],
                    *, taken_from_message: Iterable[str] = ()) -> Mapping[str, Any]:
    """Every mutation input comes out of the authoritative lookup's response. A value taken
    directly from the pushed message is never one, however well-formed the message looked."""
    # [impl->req~restore-google-message-is-trigger-only~1]
    borrowed = sorted(set(taken_from_message))
    if borrowed:
        raise RtdnContractError(
            f"{borrowed} is derived from the message rather than {AUTHORITATIVE_LOOKUP}")
    return dict(state)


# --- Acknowledgement -------------------------------------------------------------------------------


async def ingest_rtdn_push(body: Mapping[str, Any],
                           authorization: Sequence[str],
                           *,
                           config: PlayRtdnConfig,
                           verifier: PubSubOidcVerifier,
                           already_applied: Callable[[str], Awaitable[bool]],
                           fetch: Callable[[str, str], Awaitable[Mapping[str, Any]]],
                           apply: Callable[[str, Mapping[str, Any]], Awaitable[None]],
                           commit: Callable[[], Awaitable[None]],
                           ledger: RtdnLedger | None = None) -> int:
    """Handle one Pub/Sub push and return the HTTP status the route answers with.

    Authentication first, with no ingestion and no business logic ahead of it; then the package,
    expected-subscription and redelivery checks; then the authoritative Play lookup the mutations
    are derived from; and only once the resulting state is durably persisted is the message
    acknowledged.
    """
    steps = ledger if ledger is not None else RtdnLedger()
    try:
        authenticate_rtdn_push(authorization, verifier=verifier, ledger=steps)
        message = decode_push_body(body)
        notification_uuid = validate_and_dedupe(
            message, config=config,
            already_applied=await already_applied(message.message_id),
            ledger=steps)
    except RtdnAuthenticationError:
        # Any authentication failure is rejected with HTTP 401, with no ingestion and no business
        # logic run first.
        # [impl->req~restore-google-auth-failure-401~1]
        if steps.ingested:
            raise RtdnContractError(f"a rejected push ingested {steps.steps}") from None
        return RTDN_UNAUTHENTICATED
    if notification_uuid is None:
        # A redelivery: acknowledged again, repeating no side effect.
        # [impl->req~restore-google-validate-package-and-dedupe~1]
        return RTDN_ACCEPTED
    # HTTP 200 acknowledges the message only once the resulting state is durably persisted or
    # applied; an internal failure answers 5xx instead, so Pub/Sub redelivers.
    # [impl->req~restore-google-200-only-after-durable~1]
    try:
        state = await authoritative_subscription_state(message, fetch=fetch, config=config,
                                                       ledger=steps)
        steps.record("apply")
        await apply(notification_uuid, mutation_inputs(state))
        await commit()
    except Exception:
        return RTDN_INTERNAL_FAILURE
    steps.commit()
    return RTDN_ACCEPTED
