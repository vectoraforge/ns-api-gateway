from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.Subtype import Subtype
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import AppleConfig
from app.database import SubscriptionDB, UsageDB
from app.exceptions import WebhookVerificationError
from app.models import PlanTier, SubscriptionProvider, SubscriptionStatus, User
from app.services.firebase_service import FirebaseService

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
        "AppleComputerRootCertificate.cer",
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
        root_certificates=_load_apple_root_certificates(config.cert_dir),
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
                 product_id_to_tier: dict[str, str]):
        self.db = db
        self.subscriptions_db = SubscriptionDB(db)
        self.usage_db = UsageDB(db)
        self.verifier = verifier
        self.firebase_service = firebase_service
        self.product_id_to_tier = product_id_to_tier

    async def process_apple_notification(self, signed_payload: str) -> None:
        """Verify, decode, and process an Apple Store Server Notification V2."""
        try:
            payload = self.verifier.verify_and_decode_notification(signed_payload)
        except VerificationException:
            raise WebhookVerificationError("Invalid notification signature")

        notification_type = payload.notificationType
        subtype = payload.subtype
        notification_uuid = payload.notificationUUID

        if notification_type in _IGNORED_TYPES:
            logger.info("apple_notification_ignored",
                        type=notification_type, uuid=notification_uuid)
            return

        signed_transaction = payload.data.signedTransactionInfo
        if not signed_transaction:
            logger.warning("apple_notification_no_transaction",
                           type=notification_type, uuid=notification_uuid)
            return

        transaction = self.verifier.verify_and_decode_signed_transaction(
            signed_transaction
        )
        original_transaction_id = transaction.originalTransactionId
        product_id = transaction.productId

        status, plan_tier = self._map_lifecycle_event(
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

        old_tier = subscription.plan if subscription else None

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
                plan=plan_tier,
                status=status,
            )
            await self.subscriptions_db.insert_event_idempotent(
                subscription_id=subscription.id,
                event_type=notification_type,
                notification_uuid=notification_uuid,
                old_tier=None,
                new_tier=plan_tier,
            )
            await self.subscriptions_db.update_user_plan(
                user_id=subscription.user_id, plan=plan_tier
            )
        else:
            inserted = await self.subscriptions_db.insert_event_idempotent(
                subscription_id=subscription.id,
                event_type=notification_type,
                notification_uuid=notification_uuid,
                old_tier=old_tier,
                new_tier=plan_tier,
            )
            if not inserted:
                logger.info("apple_notification_duplicate",
                            uuid=notification_uuid)
                return

            await self.subscriptions_db.update_subscription(
                subscription=subscription, plan=plan_tier, status=status
            )
            await self.subscriptions_db.update_user_plan(
                user_id=subscription.user_id, plan=plan_tier
            )

        # Usage reset + Firebase sync -- only if tier changed
        if old_tier != plan_tier:
            month = datetime.now(UTC).strftime("%Y-%m")
            await self.usage_db.reset_usage(subscription.user_id, month)

            result = await self.db.exec(
                select(User).where(User.id == subscription.user_id)
            )
            user = result.first()
            if user:
                await self.firebase_service.set_plan_claim(
                    user.jwt_sub, plan_tier
                )

    def _map_lifecycle_event(self,
                             notification_type: str,
                             subtype: str | None,
                             product_id: str) -> tuple[SubscriptionStatus | None, PlanTier]:
        """Map Apple notification type/subtype to subscription status and plan tier."""
        tier_str = self.product_id_to_tier.get(product_id, PlanTier.free)
        tier = PlanTier(tier_str) if tier_str in PlanTier.__members__ else PlanTier.free

        match notification_type:
            case NotificationTypeV2.SUBSCRIBED:
                return SubscriptionStatus.active, tier
            case NotificationTypeV2.DID_RENEW:
                return SubscriptionStatus.active, tier
            case NotificationTypeV2.DID_FAIL_TO_RENEW:
                if subtype == Subtype.GRACE_PERIOD:
                    return SubscriptionStatus.grace_period, tier
                return SubscriptionStatus.billing_retry, tier
            case NotificationTypeV2.EXPIRED:
                return SubscriptionStatus.expired, PlanTier.free
            case NotificationTypeV2.REVOKE:
                return SubscriptionStatus.revoked, PlanTier.free
            case NotificationTypeV2.DID_CHANGE_RENEWAL_PREF:
                if subtype == Subtype.UPGRADE:
                    return SubscriptionStatus.active, tier
                # DOWNGRADE -- deferred to next renewal
                return None, tier
            case _:
                return SubscriptionStatus.active, tier
