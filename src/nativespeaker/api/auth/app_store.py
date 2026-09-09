"""The App Store Server Notifications integration: one envelope and its two nested payloads, verified.
A signed payload carries an attribution token: this module holds no logger, so none is logged."""
from datetime import UTC, datetime
from typing import Protocol

from appstoreserverlibrary.models.JWSRenewalInfoDecodedPayload import JWSRenewalInfoDecodedPayload
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.models.Status import Status
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException

from nativespeaker.api.auth.store_notifications import RestoredSubscription, VerifiedNotification
from nativespeaker.api.errors import (
    NotificationRejected,
    ProofRejected,
    Unavailable,
    UnknownStoreSubscriptionStatus,
    UnmappedStoreProduct,
)
from nativespeaker.api.tables.purchases import PurchaseProvider, SubscriptionStatus

# Apple's five statuses, one to one onto `core.subscription_status`.
_APPLE_STATUSES = {Status.ACTIVE: SubscriptionStatus.active,
                   Status.EXPIRED: SubscriptionStatus.expired,
                   Status.BILLING_RETRY: SubscriptionStatus.billing_retry,
                   Status.BILLING_GRACE_PERIOD: SubscriptionStatus.grace_period,
                   Status.REVOKED: SubscriptionStatus.revoked}


class StoreNotificationVerifier(Protocol):
    """The store-callback seam: one verified notification, or a raise."""

    def verify(self, signed_payload: str) -> VerifiedNotification:
        """The verification call: this project's value type, or a raise."""
        ...


def _instant(milliseconds: int | None) -> datetime | None:
    """Convert one of Apple's UNIX-millisecond stamps, keeping an absent or unusable one absent."""
    if milliseconds is None:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000, UTC)
    except (ValueError, OverflowError, OSError):
        # Every Apple stamp is an unbounded int in the library, and a value past year 9999 raised
        # out of the dependency onto the generic 500 -- the answer that makes Apple resend this same
        # body on its whole retry schedule. Out of range is as unusable as absent, and every field
        # this feeds is optional; an entitled status left with no term is still refused by
        # `SubscriptionsService.ingest`, so dropping the stamp fails closed.
        return None


def _transaction_status(transaction: JWSTransactionDecodedPayload,
                        evaluated_at: datetime) -> SubscriptionStatus:
    """The status one signed transaction reports, with no renewal payload to consult."""
    if transaction.revocationDate is not None:
        return SubscriptionStatus.revoked
    expires_at = _instant(transaction.expiresDate)
    # Grace and billing retry need the renewal payload, so an Apple restore reports three words only.
    return (SubscriptionStatus.active if expires_at is not None and expires_at > evaluated_at
            else SubscriptionStatus.expired)


def _crossed(payload, transaction: JWSTransactionDecodedPayload | None,
             renewal: JWSRenewalInfoDecodedPayload | None, *,
             status: SubscriptionStatus, tier_id: str | None) -> VerifiedNotification:
    """Assemble the value type; the grace-period field comes from the renewal payload alone."""
    return VerifiedNotification(
        provider=PurchaseProvider.apple,
        notification_uuid=payload.notificationUUID,
        # The raw string, never `notificationType`: the typed attribute is None for an unknown type.
        event_type=payload.rawNotificationType,
        external_id=None if transaction is None else transaction.originalTransactionId,
        transaction_id=None if transaction is None else transaction.transactionId,
        product_id=None if transaction is None else transaction.productId,
        tier_id=tier_id,
        attribution_token=None if transaction is None else transaction.appAccountToken,
        status=status,
        # The envelope's own instant: neither nested payload carries a signing date.
        signed_at=_instant(payload.signedDate),
        purchased_at=None if transaction is None else _instant(transaction.purchaseDate),
        expires_at=None if transaction is None else _instant(transaction.expiresDate),
        grace_period_expires_at=None if renewal is None else _instant(renewal.gracePeriodExpiresDate),
    )


class AppStoreNotifications:
    """Apple's signed notification envelope and its two nested payloads, verified against a pinned root."""

    def __init__(self, *, verifier: SignedDataVerifier | None,
                 products: dict[str, str]) -> None:
        self._verifier = verifier
        # Server-controlled reference data, never a value the store supplied.
        self._products = products

    def verify(self, signed_payload: str) -> VerifiedNotification:
        """Verify the envelope and both nested payloads, then return this project's value type."""
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")

        try:
            payload = self._verifier.verify_and_decode_notification(signed_payload)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure

        if not payload.notificationUUID or not payload.rawNotificationType:
            # Both are Optional in the library and neither is required by the verification, which
            # checks the chain, the bundle id, the app id and the environment and nothing else.
            # Refused before any write: both reach a NOT NULL column in `audit.subscription_events`,
            # and a null uuid also silently disarms the replay guard `SubscriptionsService.ingest`
            # runs on it -- `WHERE notification_uuid = NULL` matches nothing, so it never fires.
            raise NotificationRejected(stage="notification_without_identity")

        data = payload.data
        if data is None or data.signedTransactionInfo is None:
            # A test or summary notification: verified, and carrying nothing a subscription row needs.
            return _crossed(payload, None, None, status=SubscriptionStatus.expired, tier_id=None)

        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure

        if data.rawStatus is None:
            # `status` is the state of an *auto-renewable subscription*, and Apple omits it for the
            # types that carry a transaction but name no subscription: CONSUMPTION_REQUEST,
            # ONE_TIME_CHARGE, EXTERNAL_PURCHASE_TOKEN, RESCIND_CONSENT. The transaction is dropped
            # with it: `core.subscriptions.status` is NOT NULL, and inventing `expired` here would
            # end a live subscriber's grant. Verified and unwritable, exactly as line 98 above.
            # The raw int, never `status`: the typed attribute is also None for an unknown value.
            return _crossed(payload, None, None, status=SubscriptionStatus.expired, tier_id=None)

        status = _APPLE_STATUSES.get(data.status)
        if status is None:
            # A status value present but outside Apple's own enum. The named class carries the log
            # line this module cannot write itself, so Apple's retries are visible.
            raise UnknownStoreSubscriptionStatus(PurchaseProvider.apple)
        tier_id = self._tier_for(transaction.productId)

        if data.signedRenewalInfo is None:
            return _crossed(payload, transaction, None, status=status, tier_id=tier_id)

        try:
            renewal = self._verifier.verify_and_decode_renewal_info(data.signedRenewalInfo)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure

        return _crossed(payload, transaction, renewal, status=status, tier_id=tier_id)

    def verify_transaction(self, signed_transaction: str,
                           evaluated_at: datetime) -> RestoredSubscription:
        """Verify one client-presented signed transaction and report the subscription it names."""
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")

        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(signed_transaction)
        except VerificationException as failure:
            # `ProofRejected`, never `NotificationRejected`: this caller's own bearer token was valid.
            raise ProofRejected(stage=failure.status.name) from failure

        if transaction.originalTransactionId is None:
            # Refused before any read: the lifecycle key this proof is looked up by is absent.
            raise ProofRejected(stage="transaction_without_original_id")

        return RestoredSubscription(
            provider=PurchaseProvider.apple,
            external_id=transaction.originalTransactionId,
            product_id=transaction.productId,
            tier_id=self._tier_for(transaction.productId),
            attribution_token=transaction.appAccountToken,
            status=_transaction_status(transaction, evaluated_at),
            purchased_at=_instant(transaction.purchaseDate),
            expires_at=_instant(transaction.expiresDate),
            # Apple's grace window lives in the renewal payload, which this proof does not carry.
            grace_period_expires_at=None)

    def _tier_for(self, product_id: str | None) -> str:
        """The tier this store product maps to, or a refusal that leaves nothing written."""
        tier_id = None if product_id is None else self._products.get(product_id)
        if tier_id is None:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.apple, str(product_id))
        return tier_id
