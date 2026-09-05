"""The App Store Server Notifications integration: one envelope and its two nested payloads, verified.
A signed payload carries an attribution token: this module holds no logger, so none is logged."""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from appstoreserverlibrary.models.JWSRenewalInfoDecodedPayload import JWSRenewalInfoDecodedPayload
from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException

from nativespeaker.api.errors import NotificationRejected, Unavailable
from nativespeaker.api.tables.purchases import PurchaseProvider


@dataclass(frozen=True, slots=True)
class VerifiedNotification:
    """One store notification after verification, in this project's own field names."""

    provider: PurchaseProvider
    notification_uuid: str
    event_type: str
    external_id: str | None
    transaction_id: str | None
    product_id: str | None
    attribution_token: str | None
    signed_at: datetime | None
    purchased_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    grace_period_expires_at: datetime | None
    in_billing_retry: bool


class StoreNotificationVerifier(Protocol):
    """The store-callback seam: one verified notification, or a raise."""

    def verify(self, signed_payload: str) -> VerifiedNotification:
        """The verification call: this project's value type, or a raise."""
        ...


def _instant(milliseconds: int | None) -> datetime | None:
    """Convert one of Apple's UNIX-millisecond stamps, keeping an absent one absent."""
    return None if milliseconds is None else datetime.fromtimestamp(milliseconds / 1000, UTC)


def _crossed(payload, transaction: JWSTransactionDecodedPayload | None,
             renewal: JWSRenewalInfoDecodedPayload | None) -> VerifiedNotification:
    """Assemble the value type; the two renewal-only fields come from the renewal payload alone."""
    return VerifiedNotification(
        provider=PurchaseProvider.apple,
        notification_uuid=payload.notificationUUID,
        # The raw string, never `notificationType`: the typed attribute is None for an unknown type.
        event_type=payload.rawNotificationType,
        external_id=None if transaction is None else transaction.originalTransactionId,
        transaction_id=None if transaction is None else transaction.transactionId,
        product_id=None if transaction is None else transaction.productId,
        attribution_token=None if transaction is None else transaction.appAccountToken,
        # The envelope's own instant: neither nested payload carries a signing date.
        signed_at=_instant(payload.signedDate),
        purchased_at=None if transaction is None else _instant(transaction.purchaseDate),
        expires_at=None if transaction is None else _instant(transaction.expiresDate),
        revoked_at=None if transaction is None else _instant(transaction.revocationDate),
        grace_period_expires_at=None if renewal is None else _instant(renewal.gracePeriodExpiresDate),
        in_billing_retry=False if renewal is None else bool(renewal.isInBillingRetryPeriod),
    )


class AppStoreNotifications:
    """Apple's signed notification envelope and its two nested payloads, verified against a pinned root."""

    def __init__(self, *, verifier: SignedDataVerifier | None) -> None:
        self._verifier = verifier

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
            return _crossed(payload, None, None)

        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure

        if data.signedRenewalInfo is None:
            return _crossed(payload, transaction, None)

        try:
            renewal = self._verifier.verify_and_decode_renewal_info(data.signedRenewalInfo)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure

        return _crossed(payload, transaction, renewal)
