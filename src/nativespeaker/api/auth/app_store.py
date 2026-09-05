"""The App Store Server Notifications integration: one envelope and its two nested payloads, verified.
A signed payload carries an attribution token: this module holds no logger, so none is logged."""
from datetime import UTC, datetime
from typing import Protocol

from appstoreserverlibrary.models.JWSRenewalInfoDecodedPayload import JWSRenewalInfoDecodedPayload
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.models.Status import Status
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException

from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.errors import (
    InternalError,
    NotificationRejected,
    Unavailable,
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
    """Convert one of Apple's UNIX-millisecond stamps, keeping an absent one absent."""
    return None if milliseconds is None else datetime.fromtimestamp(milliseconds / 1000, UTC)


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

        data = payload.data
        if data is None or data.signedTransactionInfo is None:
            # A test or summary notification: verified, and carrying nothing a subscription row needs.
            return _crossed(payload, None, None, status=SubscriptionStatus.expired, tier_id=None)

        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure

        status = _APPLE_STATUSES.get(data.status)
        if status is None:
            # A subscription payload with no status Apple's own enum names: Apple retries and it is visible.
            raise InternalError
        tier_id = self._tier_for(transaction.productId)

        if data.signedRenewalInfo is None:
            return _crossed(payload, transaction, None, status=status, tier_id=tier_id)

        try:
            renewal = self._verifier.verify_and_decode_renewal_info(data.signedRenewalInfo)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure

        return _crossed(payload, transaction, renewal, status=status, tier_id=tier_id)

    def _tier_for(self, product_id: str | None) -> str:
        """The tier this store product maps to, or a refusal that leaves nothing written."""
        tier_id = None if product_id is None else self._products.get(product_id)
        if tier_id is None:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.apple, str(product_id))
        return tier_id
