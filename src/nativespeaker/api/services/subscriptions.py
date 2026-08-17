from pathlib import Path
from uuid import UUID

import structlog
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.Subtype import Subtype
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.config import AppleConfig
from nativespeaker.api.database import SubscriptionDB
from nativespeaker.api.exceptions import WebhookVerificationError
from nativespeaker.api.models import SubscriptionPlan, SubscriptionProvider, SubscriptionStatus
from nativespeaker.api.services.firebase import FirebaseService

logger = structlog.get_logger()

_IGNORED_TYPES = {
    NotificationTypeV2.TEST,
    NotificationTypeV2.CONSUMPTION_REQUEST,
    NotificationTypeV2.REFUND_DECLINED,
    NotificationTypeV2.PRICE_INCREASE,
    NotificationTypeV2.RENEWAL_EXTENDED,
    NotificationTypeV2.EXTERNAL_PURCHASE_TOKEN,
    NotificationTypeV2.ONE_TIME_CHARGE,
}


def _load_apple_root_certificates(cert_dir: str) -> list[bytes]:
    """Load Apple root CA certificates from directory as DER bytes."""
    cert_files = [
        "AppleIncRootCertificate.cer",
        "AppleRootCA-G2.cer",
        "AppleRootCA-G3.cer",
    ]
    cert_path = Path(cert_dir)
    return [(cert_path / f).read_bytes() for f in cert_files]


def create_apple_verifier(config: AppleConfig) -> SignedDataVerifier:
    """Create and return a SignedDataVerifier from AppleConfig."""
    environment = (Environment.PRODUCTION
                   if config.environment == "production"
                   else Environment.SANDBOX)
    return SignedDataVerifier(
        root_certificates=_load_apple_root_certificates(config.certs_dir),
        enable_online_checks=config.enable_online_checks,
        environment=environment,
        bundle_id=config.bundle_id,
        app_apple_id=config.app_apple_id,
    )


class SubscriptionService:

    def __init__(self, *,
                 db: AsyncSession,
                 verifier: SignedDataVerifier,
                 firebase_service: FirebaseService,
                 product_id_to_plan: dict[str, SubscriptionPlan]):
        self.db = db
        self.subscriptions_db = SubscriptionDB(db)
        self.verifier = verifier
        self.firebase_service = firebase_service
        self.product_id_to_plan = product_id_to_plan

    async def process_apple_notification(self, signed_payload: str) -> None:
        """Verify, decode, and process an Apple Store Server Notification V2."""
        try:
            payload = self.verifier.verify_and_decode_notification(signed_payload)
        except VerificationException:
            raise WebhookVerificationError("Invalid notification signature")

        notification_type = payload.notificationType
        subtype = payload.subtype
        notification_uuid = payload.notificationUUID

        if notification_type is None or notification_uuid is None:
            logger.warning("apple_notification_incomplete",
                           type=notification_type, uuid=notification_uuid)
            return

        if notification_type in _IGNORED_TYPES:
            logger.info("apple_notification_ignored",
                        type=notification_type, uuid=notification_uuid)
            return

        # `data` is absent on notifications that carry `summary` or
        # `externalPurchaseToken` instead -- the three fields are mutually exclusive.
        data = payload.data
        signed_transaction = data.signedTransactionInfo if data else None
        if not signed_transaction:
            logger.warning("apple_notification_no_transaction",
                           type=notification_type, uuid=notification_uuid)
            return

        transaction = self.verifier.verify_and_decode_signed_transaction(
            signed_transaction
        )
        original_transaction_id = transaction.originalTransactionId
        product_id = transaction.productId

        if original_transaction_id is None or product_id is None:
            logger.warning("apple_notification_incomplete_transaction",
                           type=notification_type, uuid=notification_uuid)
            return

        status, plan = self._map_lifecycle_event(
            notification_type, subtype, product_id
        )
        if status is None:
            logger.info("apple_notification_deferred",
                        type=notification_type, subtype=subtype,
                        uuid=notification_uuid)
            return

        subscription = await self.subscriptions_db.get_subscription_by_external_id(
            external_id=original_transaction_id,
            provider=SubscriptionProvider.apple,
        )

        old_plan = subscription.plan if subscription else None

        if subscription is None:
            app_account_token = transaction.appAccountToken
            if not app_account_token:
                logger.error("apple_notification_no_user",
                             transaction_id=original_transaction_id,
                             uuid=notification_uuid)
                return

            subscription = await self.subscriptions_db.create_subscription(
                user_id=UUID(app_account_token),
                provider=SubscriptionProvider.apple,
                external_id=original_transaction_id,
                plan=plan,
                status=status,
            )
            await self.subscriptions_db.insert_event_idempotent(
                subscription_id=subscription.id,
                event_type=notification_type,
                notification_uuid=notification_uuid,
                old_plan=None,
                new_plan=plan,
            )
            await self.subscriptions_db.update_user_plan(
                user_id=subscription.user_id, plan=plan
            )
        else:
            inserted = await self.subscriptions_db.insert_event_idempotent(
                subscription_id=subscription.id,
                event_type=notification_type,
                notification_uuid=notification_uuid,
                old_plan=old_plan,
                new_plan=plan,
            )
            if not inserted:
                logger.info("apple_notification_duplicate",
                            uuid=notification_uuid)
                return

            await self.subscriptions_db.update_subscription(
                subscription=subscription, plan=plan, status=status
            )
            await self.subscriptions_db.update_user_plan(
                user_id=subscription.user_id, plan=plan
            )

        # Firebase sync -- only if the plan changed. The monthly counter is not touched: a tier
        # move changes the grant's tier and nothing else, so `monthly_used` keeps meaning the
        # amount already consumed for `monthly_period`. Remaining is recomputed from the new
        # tier's allowance and floors at zero, and the counter resets only at the lazy monthly
        # rollover.
        if old_plan != plan:
            subject = await self.subscriptions_db.external_subject(subscription.user_id)
            if subject:
                await self.firebase_service.set_plan_claim(subject, plan)

    def _map_lifecycle_event(self,
                             notification_type: str,
                             subtype: str | None,
                             product_id: str) -> tuple[SubscriptionStatus | None, SubscriptionPlan]:
        """Map Apple notification type/subtype to subscription status and plan."""
        plan = self.product_id_to_plan.get(product_id, SubscriptionPlan.free)

        match notification_type:
            case NotificationTypeV2.SUBSCRIBED:
                return SubscriptionStatus.active, plan
            case NotificationTypeV2.DID_RENEW:
                return SubscriptionStatus.active, plan
            case NotificationTypeV2.DID_FAIL_TO_RENEW:
                if subtype == Subtype.GRACE_PERIOD:
                    return SubscriptionStatus.grace_period, plan
                return SubscriptionStatus.billing_retry, plan
            case NotificationTypeV2.EXPIRED:
                return SubscriptionStatus.expired, SubscriptionPlan.free
            case NotificationTypeV2.REVOKE:
                return SubscriptionStatus.revoked, SubscriptionPlan.free
            case NotificationTypeV2.DID_CHANGE_RENEWAL_PREF:
                if subtype == Subtype.UPGRADE:
                    return SubscriptionStatus.active, plan
                # DOWNGRADE -- deferred to next renewal
                return None, plan
            case _:
                return SubscriptionStatus.active, plan
