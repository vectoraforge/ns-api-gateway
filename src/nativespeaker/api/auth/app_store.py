"""The App Store Server Notifications integration: one envelope and its two nested payloads, verified.
A signed payload carries an attribution token: this module holds no logger, so none is logged."""
from datetime import UTC, datetime

from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload
from appstoreserverlibrary.models.Status import Status as AppleStatus
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException

from nativespeaker.api.auth.store_notifications import RestoredSubscription, VerifiedNotification
from nativespeaker.api.errors import (
    NotificationRejected,
    PurchaseProofRejected,
    Unavailable,
    UnknownStoreSubscriptionStatus,
    UnmappedStoreProduct,
)
from nativespeaker.api.tables.purchases import PurchaseProvider, SubscriptionStatus

_APPLE_STATUSES = {AppleStatus.ACTIVE: SubscriptionStatus.active,
                   AppleStatus.EXPIRED: SubscriptionStatus.expired,
                   AppleStatus.BILLING_RETRY: SubscriptionStatus.billing_retry,
                   AppleStatus.BILLING_GRACE_PERIOD: SubscriptionStatus.grace_period,
                   AppleStatus.REVOKED: SubscriptionStatus.revoked}


def _ms_to_datetime(milliseconds: int | None) -> datetime | None:
    """Convert one of Apple's UNIX-millisecond stamps, keeping an absent or unusable one absent."""
    if milliseconds is None:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000, UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _transaction_status(transaction: JWSTransactionDecodedPayload,
                        evaluated_at: datetime) -> SubscriptionStatus:
    """The status one signed transaction reports, with no renewal payload to consult."""
    if transaction.revocationDate is not None:
        return SubscriptionStatus.revoked
    expires_at = _ms_to_datetime(transaction.expiresDate)
    # Grace and billing retry need the renewal payload, so an Apple restore reports three words only.
    return (SubscriptionStatus.active if expires_at is not None and expires_at > evaluated_at
            else SubscriptionStatus.expired)


class AppStoreNotifications:
    """Apple's signed notification envelope and its two nested payloads, verified against a pinned root."""

    def __init__(self, *, verifier: SignedDataVerifier | None,
                 products: dict[str, str]) -> None:
        self._verifier = verifier
        # Server-controlled reference data, never a value the store supplied.
        self._products = products

    def verify(self, signed_payload: str) -> VerifiedNotification | None:
        """Verify the envelope and both nested payloads, then return this project's value type."""
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")

        try:
            payload = self._verifier.verify_and_decode_notification(signed_payload)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure
        except Exception as failure:
            raise NotificationRejected(stage="payload_unstructurable") from failure

        if not payload.notificationUUID or not payload.rawNotificationType:
            raise NotificationRejected(stage="notification_without_identity")

        if payload.data is None or payload.data.signedTransactionInfo is None:
            return None

        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(payload.data.signedTransactionInfo)
        except VerificationException as failure:
            raise NotificationRejected(stage=failure.status.name) from failure
        except Exception as failure:
            raise NotificationRejected(stage="payload_unstructurable") from failure

        if payload.data.rawStatus is None:
            return None

        if transaction.originalTransactionId is None:
            raise NotificationRejected(stage="transaction_without_original_id")

        renewal = None
        if payload.data.signedRenewalInfo is not None:
            try:
                renewal = self._verifier.verify_and_decode_renewal_info(payload.data.signedRenewalInfo)
            except VerificationException as failure:
                raise NotificationRejected(stage=failure.status.name) from failure
            except Exception as failure:
                raise NotificationRejected(stage="payload_unstructurable") from failure

        # Keep this check below the last verification arm. A 500 above it makes Apple retry a bad payload.
        status = _APPLE_STATUSES.get(payload.data.status) if payload.data.status else None
        if status is None:
            raise UnknownStoreSubscriptionStatus(PurchaseProvider.apple)

        return VerifiedNotification(
            provider=PurchaseProvider.apple,
            notification_uuid=payload.notificationUUID,
            event_type=payload.rawNotificationType,
            status=status,
            external_id=transaction.originalTransactionId,
            transaction_id=transaction.transactionId,
            product_id=transaction.productId,
            tier_id=self._tier_for(transaction.productId),
            attribution_token=transaction.appAccountToken,
            signed_at=_ms_to_datetime(payload.signedDate),
            purchased_at=_ms_to_datetime(transaction.purchaseDate),
            expires_at=_ms_to_datetime(transaction.expiresDate),
            # The grace-period field comes from the renewal payload, absent on most notifications.
            grace_period_expires_at=(None if renewal is None
                                     else _ms_to_datetime(renewal.gracePeriodExpiresDate)),
        )

    def verify_transaction(self, signed_transaction: str) -> RestoredSubscription:
        """Verify one client-presented signed transaction and report the subscription it names."""
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")

        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(signed_transaction)
        except VerificationException as failure:
            # `PurchaseProofRejected`, never `NotificationRejected`: this caller's own bearer token was valid.
            raise PurchaseProofRejected(stage=failure.status.name) from failure
        except Exception as failure:
            raise PurchaseProofRejected(stage="payload_unstructurable") from failure

        if transaction.originalTransactionId is None:
            # Refused before any read: the lifecycle key this proof is looked up by is absent.
            raise PurchaseProofRejected(stage="transaction_without_original_id")

        instant = datetime.now(UTC)
        return RestoredSubscription(
            provider=PurchaseProvider.apple,
            external_id=transaction.originalTransactionId,
            product_id=transaction.productId,
            tier_id=self._tier_for(transaction.productId),
            attribution_token=transaction.appAccountToken,
            status=_transaction_status(transaction, instant),
            purchased_at=_ms_to_datetime(transaction.purchaseDate),
            expires_at=_ms_to_datetime(transaction.expiresDate),
            # Apple's grace window lives in the renewal payload, which this proof does not carry.
            grace_period_expires_at=None)

    def _tier_for(self, product_id: str | None) -> str:
        """The tier this store product maps to, or a refusal that leaves nothing written."""
        tier_id = None if product_id is None else self._products.get(product_id)
        if tier_id is None:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.apple, str(product_id))
        return tier_id
