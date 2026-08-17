from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from nativespeaker.api.auth.entitlement import AccessGrantStatus
from nativespeaker.api.auth.integration import FirebaseIntegration, FirebaseIntegrations
from nativespeaker.api.models import Subscription, SubscriptionPlan, SubscriptionStatus
from nativespeaker.api.services import FirebaseService, SubscriptionService

TEST_ISSUER = "https://securetoken.google.com/test-project"


def _firebase_service() -> FirebaseService:
    """The service bound to the one configured integration: every Admin call selects its
    client by the matched issuer, and there is no default app to fall back to."""
    integrations = FirebaseIntegrations([FirebaseIntegration(issuer=TEST_ISSUER,
                                                            project_id="test-project",
                                                            verifier=MagicMock(),
                                                            admin_client=MagicMock())])
    return FirebaseService(integrations=integrations, issuer=TEST_ISSUER)

# --- Helpers for building mock Apple payloads ---

def _make_mock_transaction(*,
                           original_transaction_id: str = "txn_001",
                           product_id: str = "com.example.nativespeaker.gold",
                           app_account_token: str | None = None):
    txn = MagicMock()
    txn.originalTransactionId = original_transaction_id
    txn.productId = product_id
    txn.appAccountToken = app_account_token or str(uuid4())
    return txn


def _make_mock_payload(*,
                       notification_type: str,
                       subtype: str | None = None,
                       notification_uuid: str = "uuid-001",
                       signed_transaction: str | None = "signed.txn.info"):
    payload = MagicMock()
    payload.notificationType = notification_type
    payload.subtype = subtype
    payload.notificationUUID = notification_uuid
    payload.data = MagicMock()
    payload.data.signedTransactionInfo = signed_transaction
    return payload


PRODUCT_TO_PLAN = {
    "com.example.nativespeaker.silver": SubscriptionPlan.silver,
    "com.example.nativespeaker.gold": SubscriptionPlan.gold,
    "com.example.nativespeaker.platinum": SubscriptionPlan.platinum,
}


@pytest.fixture
def mock_verifier():
    return MagicMock()


@pytest.fixture
def mock_firebase():
    return AsyncMock(spec=FirebaseService)


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def mock_subscriptions_db():
    return AsyncMock()


@pytest.fixture
def subscription_service(mock_db_session, mock_verifier, mock_firebase, mock_subscriptions_db):
    svc = SubscriptionService(
        db=mock_db_session,
        verifier=mock_verifier,
        firebase_service=mock_firebase,
        product_id_to_plan=PRODUCT_TO_PLAN,
    )
    svc.subscriptions_db = mock_subscriptions_db
    return svc


class TestSubscriptionLifecycle:
    """SUBS-03: Full subscription lifecycle event processing."""

    def test_map_subscribed_initial_buy(self, subscription_service):
        """SUBSCRIBED + INITIAL_BUY -> active, tier from product."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
        from appstoreserverlibrary.models.Subtype import Subtype

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.SUBSCRIBED, Subtype.INITIAL_BUY,
            "com.example.nativespeaker.gold",
        )
        assert status == SubscriptionStatus.active
        assert tier == SubscriptionPlan.gold

    def test_map_did_renew(self, subscription_service):
        """DID_RENEW -> active, same tier."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.DID_RENEW, None,
            "com.example.nativespeaker.gold",
        )
        assert status == SubscriptionStatus.active
        assert tier == SubscriptionPlan.gold

    def test_map_grace_period(self, subscription_service):
        """DID_FAIL_TO_RENEW + GRACE_PERIOD -> grace_period, keeps tier."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
        from appstoreserverlibrary.models.Subtype import Subtype

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.DID_FAIL_TO_RENEW, Subtype.GRACE_PERIOD,
            "com.example.nativespeaker.silver",
        )
        assert status == SubscriptionStatus.grace_period
        assert tier == SubscriptionPlan.silver

    def test_map_billing_retry(self, subscription_service):
        """DID_FAIL_TO_RENEW (no grace) -> billing_retry, keeps tier."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.DID_FAIL_TO_RENEW, None,
            "com.example.nativespeaker.gold",
        )
        assert status == SubscriptionStatus.billing_retry
        assert tier == SubscriptionPlan.gold

    def test_map_expired(self, subscription_service):
        """EXPIRED -> expired, falls to free."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
        from appstoreserverlibrary.models.Subtype import Subtype

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.EXPIRED, Subtype.VOLUNTARY,
            "com.example.nativespeaker.gold",
        )
        assert status == SubscriptionStatus.expired
        assert tier == SubscriptionPlan.free

    def test_map_revoked(self, subscription_service):
        """REVOKE -> revoked, falls to free."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.REVOKE, None,
            "com.example.nativespeaker.gold",
        )
        assert status == SubscriptionStatus.revoked
        assert tier == SubscriptionPlan.free

    def test_map_upgrade(self, subscription_service):
        """DID_CHANGE_RENEWAL_PREF + UPGRADE -> active, new tier."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
        from appstoreserverlibrary.models.Subtype import Subtype

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.DID_CHANGE_RENEWAL_PREF, Subtype.UPGRADE,
            "com.example.nativespeaker.platinum",
        )
        assert status == SubscriptionStatus.active
        assert tier == SubscriptionPlan.platinum

    def test_map_downgrade_deferred(self, subscription_service):
        """DID_CHANGE_RENEWAL_PREF + DOWNGRADE -> None (deferred, no immediate change)."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
        from appstoreserverlibrary.models.Subtype import Subtype

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.DID_CHANGE_RENEWAL_PREF, Subtype.DOWNGRADE,
            "com.example.nativespeaker.silver",
        )
        assert status is None

    def test_map_unknown_product_defaults_to_free(self, subscription_service):
        """Unknown product ID maps to free tier."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        status, tier = subscription_service._map_lifecycle_event(
            NotificationTypeV2.SUBSCRIBED, None,
            "com.unknown.product",
        )
        assert tier == SubscriptionPlan.free

    @pytest.mark.asyncio
    async def test_ignored_notification_types(self, subscription_service,
                                                mock_verifier, mock_subscriptions_db):
        """TEST, CONSUMPTION_REQUEST, etc. are ignored -- no DB calls."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(notification_type=NotificationTypeV2.TEST)
        mock_verifier.verify_and_decode_notification.return_value = payload

        await subscription_service.process_apple_notification("signed.payload")

        # Verify no DB operations were called
        mock_subscriptions_db.get_subscription_by_external_id.assert_not_called()


class TestStatusWriterSettlesTheGrant:
    """The notification handler is a subscription status writer, so it owns the obligation the
    subscription-backed grant invariant places on one: a transition out of the product-entitled
    set deactivates or replaces the active grant in the same transaction as the status change.
    There is no reconciliation sweep to do it afterwards."""

    @staticmethod
    def _lapsing(mock_verifier, mock_subscriptions_db, *, notification_type,
                 old_status=SubscriptionStatus.active, grant_id=None):
        payload = _make_mock_payload(notification_type=notification_type,
                                     notification_uuid=f"settle-{notification_type}")
        mock_verifier.verify_and_decode_notification.return_value = payload
        mock_verifier.verify_and_decode_signed_transaction.return_value = _make_mock_transaction()
        existing = MagicMock(spec=Subscription)
        existing.id = uuid4()
        existing.user_id = uuid4()
        existing.plan = SubscriptionPlan.gold
        existing.status = old_status
        mock_subscriptions_db.get_subscription_by_external_id.return_value = existing
        mock_subscriptions_db.insert_event_idempotent.return_value = True
        mock_subscriptions_db.active_subscription_grant_id.return_value = grant_id
        return existing

    # [utest->req~quota-status-writer-owns-grant-deactivation~1]
    @pytest.mark.asyncio
    async def test_an_expiry_notification_deactivates_the_active_grant(
            self, subscription_service, mock_verifier, mock_subscriptions_db):
        """`active` -> `expired` with an active subscription-backed grant: without this the
        deferrable foreign key would fail the commit and the status would never persist."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        grant_id = uuid4()
        subscription = self._lapsing(mock_verifier, mock_subscriptions_db,
                                     notification_type=NotificationTypeV2.EXPIRED,
                                     grant_id=grant_id)

        await subscription_service.process_apple_notification("signed.payload")

        assert mock_subscriptions_db.update_subscription.await_args.kwargs["status"] is (
            SubscriptionStatus.expired)
        mock_subscriptions_db.active_subscription_grant_id.assert_awaited_once_with(
            subscription.id)
        mock_subscriptions_db.deactivate_grant.assert_awaited_once_with(
            grant_id, AccessGrantStatus.expired)

    # [utest->req~quota-status-writer-owns-grant-deactivation~1]
    @pytest.mark.asyncio
    async def test_a_revocation_revokes_the_grant_and_a_failed_renewal_expires_it(
            self, subscription_service, mock_verifier, mock_subscriptions_db):
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        grant_id = uuid4()
        self._lapsing(mock_verifier, mock_subscriptions_db,
                      notification_type=NotificationTypeV2.REVOKE, grant_id=grant_id)
        await subscription_service.process_apple_notification("signed.payload")
        mock_subscriptions_db.deactivate_grant.assert_awaited_once_with(
            grant_id, AccessGrantStatus.revoked)

        # `billing_retry` is not product-entitled either, so it settles the grant the same way.
        mock_subscriptions_db.deactivate_grant.reset_mock()
        self._lapsing(mock_verifier, mock_subscriptions_db,
                      notification_type=NotificationTypeV2.DID_FAIL_TO_RENEW, grant_id=grant_id)
        await subscription_service.process_apple_notification("signed.payload")
        mock_subscriptions_db.deactivate_grant.assert_awaited_once_with(
            grant_id, AccessGrantStatus.expired)

    # [utest->req~quota-status-writer-owns-grant-deactivation~1]
    @pytest.mark.asyncio
    async def test_a_transition_inside_the_entitled_set_settles_nothing(
            self, subscription_service, mock_verifier, mock_subscriptions_db):
        """`active` -> `grace_period` keeps the subscription product-entitled, so the grant
        stays exactly as it is."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
        from appstoreserverlibrary.models.Subtype import Subtype

        self._lapsing(mock_verifier, mock_subscriptions_db,
                      notification_type=NotificationTypeV2.DID_FAIL_TO_RENEW,
                      grant_id=uuid4())
        payload = mock_verifier.verify_and_decode_notification.return_value
        payload.subtype = Subtype.GRACE_PERIOD

        await subscription_service.process_apple_notification("signed.payload")

        assert mock_subscriptions_db.update_subscription.await_args.kwargs["status"] is (
            SubscriptionStatus.grace_period)
        mock_subscriptions_db.deactivate_grant.assert_not_called()

    # [utest->req~quota-status-writer-owns-grant-deactivation~1]
    @pytest.mark.asyncio
    async def test_a_lapse_with_no_active_grant_has_nothing_to_settle(
            self, subscription_service, mock_verifier, mock_subscriptions_db):
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        self._lapsing(mock_verifier, mock_subscriptions_db,
                      notification_type=NotificationTypeV2.EXPIRED, grant_id=None)

        await subscription_service.process_apple_notification("signed.payload")

        mock_subscriptions_db.deactivate_grant.assert_not_called()


class TestIdempotency:
    """SUBS-04: Duplicate notifications safely ignored."""

    @pytest.mark.asyncio
    async def test_duplicate_notification_ignored(self, subscription_service,
                                                    mock_verifier, mock_subscriptions_db):
        """Second notification with same UUID is silently skipped."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.DID_RENEW,
            notification_uuid="dup-uuid-001",
        )
        mock_verifier.verify_and_decode_notification.return_value = payload
        mock_verifier.verify_and_decode_signed_transaction.return_value = _make_mock_transaction()

        existing_sub = MagicMock(spec=Subscription)
        existing_sub.id = uuid4()
        existing_sub.user_id = uuid4()
        existing_sub.plan = SubscriptionPlan.gold
        mock_subscriptions_db.get_subscription_by_external_id.return_value = existing_sub
        # insert_event_idempotent returns False -> duplicate
        mock_subscriptions_db.insert_event_idempotent.return_value = False

        await subscription_service.process_apple_notification("signed.payload")

        # Verify update_subscription was NOT called (duplicate skipped)
        mock_subscriptions_db.update_subscription.assert_not_called()


class TestPlanTierUpdate:
    """SUBS-05: User plan tier stored in local DB."""

    @pytest.mark.asyncio
    async def test_plan_updated_on_subscription_change(self, subscription_service,
                                                        mock_verifier, mock_db_session,
                                                        mock_subscriptions_db):
        """Existing subscription update triggers user plan update in DB."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.DID_RENEW,
            notification_uuid="plan-update-uuid",
        )
        mock_verifier.verify_and_decode_notification.return_value = payload
        mock_verifier.verify_and_decode_signed_transaction.return_value = _make_mock_transaction(
            product_id="com.example.nativespeaker.gold"
        )

        user_id = uuid4()
        existing_sub = MagicMock(spec=Subscription)
        existing_sub.id = uuid4()
        existing_sub.user_id = user_id
        existing_sub.plan = SubscriptionPlan.gold
        mock_subscriptions_db.get_subscription_by_external_id.return_value = existing_sub
        mock_subscriptions_db.insert_event_idempotent.return_value = True

        # Tier unchanged (gold -> gold), so no Firebase call but update_user_plan still called
        await subscription_service.process_apple_notification("signed.payload")

        mock_subscriptions_db.update_user_plan.assert_called_once_with(
            user_id=user_id, plan=SubscriptionPlan.gold
        )


class TestFirebaseSync:
    """SUBS-06, SUBS-07: Firebase claim sync."""

    @pytest.mark.asyncio
    async def test_firebase_sync_on_tier_change(self, subscription_service,
                                                 mock_verifier, mock_firebase,
                                                 mock_db_session, mock_subscriptions_db):
        """SUBS-06: Plan change triggers Firebase custom claim sync."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.SUBSCRIBED,
            notification_uuid="firebase-sync-uuid",
        )
        mock_verifier.verify_and_decode_notification.return_value = payload
        mock_verifier.verify_and_decode_signed_transaction.return_value = _make_mock_transaction(
            product_id="com.example.nativespeaker.gold"
        )

        user_id = uuid4()
        existing_sub = MagicMock(spec=Subscription)
        existing_sub.id = uuid4()
        existing_sub.user_id = user_id
        existing_sub.plan = SubscriptionPlan.free  # Was free, now gold -> tier changed
        mock_subscriptions_db.get_subscription_by_external_id.return_value = existing_sub
        mock_subscriptions_db.insert_event_idempotent.return_value = True

        # The external subject comes from `core.external_identities`, not from a column on
        # `core.users`.
        mock_subscriptions_db.external_subject.return_value = "firebase-uid-456"

        await subscription_service.process_apple_notification("signed.payload")

        mock_subscriptions_db.external_subject.assert_awaited_once_with(user_id)
        mock_firebase.set_plan_claim.assert_called_once_with(
            "firebase-uid-456", SubscriptionPlan.gold
        )
        # A tier move changes the grant's tier and nothing else: `monthly_used` still means
        # the amount already consumed for its period, so no counter is rewritten mid-period.
        # [utest->req~schema-user-monthly-usage-monthly-used-field~1]
        written = " ".join(str(call) for call in mock_db_session.exec.call_args_list)
        assert "user_monthly_usage" not in written

    @pytest.mark.asyncio
    async def test_uses_to_thread(self):
        """SUBS-07: FirebaseService.set_plan_claim uses asyncio.to_thread."""
        firebase_service = _firebase_service()

        with patch("nativespeaker.api.services.firebase.asyncio.to_thread",
                    new_callable=AsyncMock) as mock_to_thread:
            await firebase_service.set_plan_claim("uid-123", SubscriptionPlan.gold)
            mock_to_thread.assert_called_once()
            # The Admin call runs on the client the integration selects by matched issuer.
            # [utest->req~shared-single-firebase-integration~1]
            expected = firebase_service._integrations.sole.admin_client   # noqa: SLF001
            assert mock_to_thread.call_args.kwargs["app"] is expected

    @pytest.mark.asyncio
    async def test_firebase_failure_does_not_raise(self):
        """SUBS-07: Firebase sync failure is swallowed (best-effort)."""
        firebase_service = _firebase_service()

        with patch("nativespeaker.api.services.firebase.asyncio.to_thread",
                    side_effect=Exception("Firebase down")):
            # Should NOT raise -- just log warning
            await firebase_service.set_plan_claim("uid-123", SubscriptionPlan.gold)

    @pytest.mark.asyncio
    async def test_no_firebase_sync_when_tier_unchanged(self, subscription_service,
                                                         mock_verifier, mock_firebase,
                                                         mock_db_session,
                                                         mock_subscriptions_db):
        """No Firebase call when plan tier doesn't change (e.g., DID_RENEW with same product)."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.DID_RENEW,
            notification_uuid="no-change-uuid",
        )
        mock_verifier.verify_and_decode_notification.return_value = payload
        mock_verifier.verify_and_decode_signed_transaction.return_value = _make_mock_transaction(
            product_id="com.example.nativespeaker.gold"
        )

        existing_sub = MagicMock(spec=Subscription)
        existing_sub.id = uuid4()
        existing_sub.user_id = uuid4()
        existing_sub.plan = SubscriptionPlan.gold  # Same tier -> no change
        mock_subscriptions_db.get_subscription_by_external_id.return_value = existing_sub
        mock_subscriptions_db.insert_event_idempotent.return_value = True

        await subscription_service.process_apple_notification("signed.payload")

        # Firebase should NOT be called because tier did not change
        mock_firebase.set_plan_claim.assert_not_called()


class TestNewSubscription:
    """New subscription flow -- no existing subscription in DB."""

    @pytest.mark.asyncio
    async def test_creates_subscription_for_new_user(self,
                                                     subscription_service,
                                                     mock_verifier,
                                                     mock_db_session,
                                                     mock_subscriptions_db):
        """SUBSCRIBED with no existing sub creates new subscription."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        user_id = uuid4()
        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.SUBSCRIBED,
            notification_uuid="new-sub-uuid",
        )
        mock_verifier.verify_and_decode_notification.return_value = payload
        mock_verifier.verify_and_decode_signed_transaction.return_value = (
            _make_mock_transaction(
                product_id="com.example.nativespeaker.gold",
                app_account_token=str(user_id),
            )
        )

        mock_subscriptions_db.get_subscription_by_external_id.return_value = None
        new_sub = MagicMock()
        new_sub.id = uuid4()
        new_sub.user_id = user_id
        mock_subscriptions_db.create_subscription.return_value = new_sub

        # Mock the db.exec chain for Firebase sync (old_plan=None != plan=gold)
        mock_user = MagicMock()
        mock_user.jwt_sub = "firebase-uid-new"
        mock_result = MagicMock()
        mock_result.first.return_value = mock_user
        mock_db_session.exec = AsyncMock(return_value=mock_result)

        await subscription_service.process_apple_notification("signed.payload")

        mock_subscriptions_db.create_subscription.assert_called_once()
        mock_subscriptions_db.update_user_plan.assert_called_once_with(
            user_id=user_id, plan=SubscriptionPlan.gold
        )


class TestMissingAppAccountToken:
    """Missing appAccountToken in new subscription -- cannot identify user."""

    @pytest.mark.asyncio
    async def test_missing_app_account_token_returns_early(self,
                                                           subscription_service,
                                                           mock_verifier,
                                                           mock_subscriptions_db):
        """No appAccountToken means we can't associate with a user -- early return."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.SUBSCRIBED,
            notification_uuid="no-token-uuid",
        )
        mock_verifier.verify_and_decode_notification.return_value = payload
        txn = _make_mock_transaction(
            product_id="com.example.nativespeaker.gold",
            app_account_token=None,
        )
        txn.appAccountToken = None
        mock_verifier.verify_and_decode_signed_transaction.return_value = txn

        mock_subscriptions_db.get_subscription_by_external_id.return_value = None

        await subscription_service.process_apple_notification("signed.payload")

        mock_subscriptions_db.create_subscription.assert_not_called()
        mock_subscriptions_db.update_user_plan.assert_not_called()


class TestMissingTransactionData:
    """Notification without transaction data -- early return."""

    @pytest.mark.asyncio
    async def test_no_transaction_data_returns_early(self,
                                                     subscription_service,
                                                     mock_verifier,
                                                     mock_subscriptions_db):
        """Notification with empty signedTransactionInfo returns early."""
        from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2

        payload = _make_mock_payload(
            notification_type=NotificationTypeV2.DID_RENEW,
            notification_uuid="no-txn-uuid",
            signed_transaction=None,
        )
        payload.data.signedTransactionInfo = None
        mock_verifier.verify_and_decode_notification.return_value = payload

        await subscription_service.process_apple_notification("signed.payload")

        mock_verifier.verify_and_decode_signed_transaction.assert_not_called()
        mock_subscriptions_db.get_subscription_by_external_id.assert_not_called()
