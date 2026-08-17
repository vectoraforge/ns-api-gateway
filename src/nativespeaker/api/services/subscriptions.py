from pathlib import Path
from uuid import UUID

import structlog
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.Subtype import Subtype
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.config import AppleConfig
from nativespeaker.api.database import StorePurchaseTokensDB, SubscriptionDB
from nativespeaker.api.exceptions import WebhookVerificationError
from nativespeaker.api.models import SubscriptionPlan, SubscriptionProvider, SubscriptionStatus
from nativespeaker.api.quota.grants import (
    assert_status_writer_settled_grant,
    is_product_entitled,
    settled_grant_status,
)
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
    """Create and return a SignedDataVerifier from AppleConfig.

    Apple's own App Store Server Library performs the chain verification, given Apple's root
    certificates; there is no hand-written certificate-chain logic here. The same object carries the
    configured bundle ID, environment and App Apple ID, so every decode it performs validates the
    decoded payload against those configured values.
    """
    # [impl->req~restore-apple-verify-jws-chain~1]
    # [impl->req~restore-apple-validate-bundle-environment~1]
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
        self.purchase_tokens_db = StorePurchaseTokensDB(db)
        self.verifier = verifier
        self.firebase_service = firebase_service
        self.product_id_to_plan = product_id_to_plan

    async def commit(self) -> None:
        """Make everything this notification applied durable.

        The webhook route awaits this before answering 200, so a persistence failure raises here and
        surfaces as 5xx instead: Apple then retries on its own schedule.
        """
        # [impl->req~restore-apple-200-only-after-durable~1]
        await self.db.commit()

    async def process_apple_notification(self, signed_payload: str) -> None:
        """Verify, decode, and process an Apple Store Server Notification V2."""
        # The `signedPayload` JWS signature and its `x5c` certificate chain are verified up to
        # Apple's Root CA before the notification is treated as authentic, by Apple's own App Store
        # Server Library. The same call validates the decoded bundle ID and environment against the
        # configured values, and the App Apple ID where the notification carries one.
        # [impl->req~restore-apple-verify-jws-chain~1]
        # [impl->req~restore-apple-validate-bundle-environment~1]
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

        # Each nested signed payload is verified on its own before it is used as purchase evidence:
        # verifying the outer envelope is not sufficient. The signed renewal information is verified
        # the same way wherever the notification carries it.
        # [impl->req~restore-apple-verify-nested-payloads~1]
        try:
            transaction = self.verifier.verify_and_decode_signed_transaction(
                signed_transaction
            )
            signed_renewal = data.signedRenewalInfo if data else None
            if signed_renewal:
                self.verifier.verify_and_decode_renewal_info(signed_renewal)
        except VerificationException:
            # A nested payload that does not verify is an invalid payload, exactly like a bad
            # envelope: no ingestion and no entitlement effect.
            # [impl->req~restore-apple-invalid-payload-401~1]
            raise WebhookVerificationError("Invalid nested signed payload") from None
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
        old_status = subscription.status if subscription else None

        if subscription is None:
            # The owning user is resolved by matching the store-echoed token through
            # `core.store_purchase_tokens` by `(provider, identity_value)`. The echoed value is
            # purchase evidence about an attribution, never an active user identity, so it is never
            # read as a user id: a token that is absent or resolves to no binding leaves the
            # subscription unclaimed for restore's adoption path rather than attributing it.
            # [impl->req~restore-purchase-flow-04-ingestion-resolves-and-creates~1]
            # [impl->req~restore-echoed-uuid-is-evidence-not-identity~1]
            echoed = transaction.appAccountToken
            owner = (await self.purchase_tokens_db.owner_of(StoreProvider.apple, str(echoed))
                     if echoed else None)
            if owner is None:
                logger.error("apple_notification_unattributed",
                             transaction_id=original_transaction_id,
                             uuid=notification_uuid)
                return

            subscription = await self.subscriptions_db.create_subscription(
                user_id=owner,
                provider=SubscriptionProvider.apple,
                external_id=original_transaction_id,
                plan=plan,
                status=status,
            )
            # Redelivery is idempotent, keyed on Apple's notification UUID recorded as
            # `audit.subscription_events.notification_uuid`: a valid replay is acknowledged again and
            # repeats no side effect. That holds on this branch too, so a replay that races the first
            # delivery cannot apply the entitlement effect twice.
            # [impl->req~restore-apple-redelivery-idempotent~1]
            first_delivery = await self.subscriptions_db.insert_event_idempotent(
                subscription_id=subscription.id,
                event_type=notification_type,
                notification_uuid=notification_uuid,
                old_plan=None,
                new_plan=plan,
            )
            if not first_delivery:
                logger.info("apple_notification_duplicate", uuid=notification_uuid)
                return
            await self.subscriptions_db.update_user_plan(
                user_id=subscription.user_id, plan=plan
            )
        else:
            # [impl->req~restore-apple-redelivery-idempotent~1]
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
            await self._settle_grant_for_status_change(subscription.id,
                                                       old_status=old_status,
                                                       new_status=status)
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

    async def _settle_grant_for_status_change(self,
                                              subscription_id: UUID,
                                              *,
                                              old_status: SubscriptionStatus | None,
                                              new_status: SubscriptionStatus) -> None:
        """This notification handler is a subscription status writer, so it owns the obligation
        the entitlement invariant places on one: a transition out of the product-entitled set
        deactivates or replaces the active grant in the same transaction as the status change.

        No reconciliation sweep does it later. Skipping it would not leave a stale grant behind
        either — the deferrable foreign key from the grant's generated
        `active_subscription_grant_subscription_id` column to `product_entitled_subscription_id`
        fails the commit, so the notification would 500 and never persist the status at all.
        """
        # [impl->req~quota-status-writer-owns-grant-deactivation~1]
        # [impl->req~quota-lifecycle-ingestion-single-transaction~2]
        if old_status is None:
            return
        active_grant_id = await self.subscriptions_db.active_subscription_grant_id(subscription_id)
        deactivated = False
        if (active_grant_id is not None
                and is_product_entitled(old_status)
                and not is_product_entitled(new_status)):
            await self.subscriptions_db.deactivate_grant(active_grant_id,
                                                         settled_grant_status(new_status))
            deactivated = True
            logger.info("subscription_grant_settled", subscription_id=str(subscription_id),
                        grant_id=str(active_grant_id), old_status=old_status,
                        new_status=new_status)
        # The writer's own check, taken on the one transaction that carries both writes.
        assert_status_writer_settled_grant(old_status=old_status,
                                           new_status=new_status,
                                           active_grant_id=active_grant_id,
                                           grant_deactivated=deactivated,
                                           subscription_transaction=self.db,
                                           grant_transaction=self.db)

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
