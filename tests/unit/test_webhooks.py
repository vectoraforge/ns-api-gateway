"""`POST /webhooks/app-store`: Apple's signed payload is the credential, and the route answers in
plain HTTP status codes."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.signed_data_verifier import (
    VerificationException,
    VerificationStatus,
)

from nativespeaker.api.config import AppleConfig
from nativespeaker.api.exceptions import WebhookVerificationError
from nativespeaker.api.models import SubscriptionPlan
from nativespeaker.api.services import FirebaseService, SubscriptionService
from nativespeaker.api.services.subscriptions import create_apple_verifier

PRODUCT_TO_PLAN = {"com.example.nativespeaker.gold": SubscriptionPlan.gold}


@pytest.fixture
def mock_verifier():
    return MagicMock()


@pytest.fixture
def mock_subscriptions_db():
    return AsyncMock()


@pytest.fixture
def subscription_service(mock_verifier, mock_subscriptions_db):
    """The real service, with the store verifier and the two tables mocked out."""
    service = SubscriptionService(db=AsyncMock(),
                                 verifier=mock_verifier,
                                 firebase_service=AsyncMock(spec=FirebaseService),
                                 product_id_to_plan=PRODUCT_TO_PLAN)
    service.subscriptions_db = mock_subscriptions_db
    return service


class TestAppleWebhook:
    """Tests for POST /webhooks/app-store endpoint (SUBS-01, SUBS-02)."""

    def test_receives_notification(self, webhook_client, mock_subscription_service):
        """SUBS-01: Endpoint receives and acknowledges Apple notification."""
        response = webhook_client.post(
            "/webhooks/app-store",
            json={"signedPayload": "valid.jws.token"},
        )
        assert response.status_code == 200
        assert response.content == b""
        mock_subscription_service.process_apple_notification.assert_called_once_with(
            "valid.jws.token"
        )

    def test_missing_signed_payload(self, webhook_client):
        """A missing payload is rejected with HTTP 401 and no ingestion."""
        # [utest->req~restore-apple-invalid-payload-401~1]
        response = webhook_client.post("/webhooks/app-store", json={})
        assert response.status_code == 401
        assert response.content == b""

    def test_empty_signed_payload(self, webhook_client):
        """An empty payload is rejected the same way."""
        # [utest->req~restore-apple-invalid-payload-401~1]
        response = webhook_client.post(
            "/webhooks/app-store",
            json={"signedPayload": ""},
        )
        assert response.status_code == 401

    def test_malformed_body_is_rejected_before_any_business_logic(self, webhook_client,
                                                                 mock_subscription_service):
        """A malformed envelope never reaches ingestion."""
        # [utest->req~restore-apple-invalid-payload-401~1]
        response = webhook_client.post("/webhooks/app-store", content=b"{not json",
                                       headers={"content-type": "application/json"})
        assert response.status_code == 401
        mock_subscription_service.process_apple_notification.assert_not_called()
        mock_subscription_service.commit.assert_not_called()

    def test_invalid_jws_rejected(self, webhook_client, mock_subscription_service):
        """SUBS-02: an invalid JWS signature is rejected with HTTP 401, no entitlement effect."""
        # [utest->req~restore-apple-invalid-payload-401~1]
        mock_subscription_service.process_apple_notification.side_effect = (
            WebhookVerificationError("Invalid signature")
        )
        response = webhook_client.post(
            "/webhooks/app-store",
            json={"signedPayload": "invalid.jws.token"},
        )
        assert response.status_code == 401
        assert response.content == b""
        mock_subscription_service.commit.assert_not_called()

    def test_the_route_answers_in_plain_status_codes(self, webhook_client,
                                                    mock_subscription_service):
        """A store server is not an app client: no shared client-visible error class appears."""
        # [utest->req~restore-ingestion-provider-callback-routes~1]
        mock_subscription_service.process_apple_notification.side_effect = (
            WebhookVerificationError("Invalid signature")
        )
        response = webhook_client.post("/webhooks/app-store",
                                       json={"signedPayload": "invalid.jws.token"})
        assert response.status_code == 401
        assert response.content == b""

    def test_no_jwt_auth_required(self, webhook_client, mock_subscription_service):
        """SUBS-01: Webhook does not require JWT Bearer token."""
        # No Authorization header provided -- should still succeed
        # [utest->req~restore-apple-webhook-signed-payload-auth~1]
        # [utest->req~restore-ingestion-provider-callback-routes~1]
        response = webhook_client.post(
            "/webhooks/app-store",
            json={"signedPayload": "valid.jws.token"},
        )
        assert response.status_code == 200

    def test_a_firebase_token_does_not_stand_in_for_the_signed_payload(self, webhook_client):
        """The credential is the JWS in the body; an `Authorization` header admits nothing."""
        # [utest->req~restore-apple-webhook-signed-payload-auth~1]
        response = webhook_client.post("/webhooks/app-store", json={},
                                       headers={"Authorization": "Bearer firebase-id-token"})
        assert response.status_code == 401

    def test_200_only_after_the_notification_is_durable(self, webhook_client,
                                                       mock_subscription_service):
        """HTTP 200 is returned only once the notification is durably persisted or applied."""
        # [utest->req~restore-apple-200-only-after-durable~1]
        response = webhook_client.post("/webhooks/app-store",
                                       json={"signedPayload": "valid.jws.token"})
        assert response.status_code == 200
        mock_subscription_service.commit.assert_awaited_once()

    def test_a_persistence_failure_answers_5xx_not_200(self, webhook_client,
                                                      mock_subscription_service):
        """An internal failure returns 5xx, so Apple's own retry schedule covers it."""
        # [utest->req~restore-apple-200-only-after-durable~1]
        mock_subscription_service.commit.side_effect = RuntimeError("connection lost")
        response = webhook_client.post("/webhooks/app-store",
                                       json={"signedPayload": "valid.jws.token"})
        assert response.status_code >= 500


class TestAppleVerifierConstruction:
    """The verifier the route's named verification runs through."""

    @staticmethod
    def _config(**overrides: Any) -> AppleConfig:
        fields: dict[str, Any] = {"bundle_id": "com.example.nativespeaker",
                  "environment": "production",
                  "certs_dir": "/certs",
                  "app_apple_id": 123456789,
                  "product_id_to_plan": PRODUCT_TO_PLAN}
        fields.update(overrides)
        return AppleConfig(**fields)

    def test_apple_s_own_library_does_the_chain_verification(self):
        """The `x5c` chain is verified up to Apple's Root CA by the App Store Server Library, given
        Apple's root certificates -- never by hand-written certificate-chain logic."""
        # [utest->req~restore-apple-verify-jws-chain~1]
        with (patch("nativespeaker.api.services.subscriptions._load_apple_root_certificates",
                    return_value=[b"root-1", b"root-2", b"root-3"]) as roots,
              patch("nativespeaker.api.services.subscriptions.SignedDataVerifier") as verifier):
            create_apple_verifier(self._config())
        roots.assert_called_once_with("/certs")
        assert verifier.call_args.kwargs["root_certificates"] == [b"root-1", b"root-2", b"root-3"]

    def test_the_configured_bundle_environment_and_app_apple_id_are_validated(self):
        """The decoded bundle ID, environment, and App Apple ID are checked against configuration."""
        # [utest->req~restore-apple-validate-bundle-environment~1]
        with (patch("nativespeaker.api.services.subscriptions._load_apple_root_certificates",
                    return_value=[b"root"]),
              patch("nativespeaker.api.services.subscriptions.SignedDataVerifier") as verifier):
            create_apple_verifier(self._config())
        kwargs = verifier.call_args.kwargs
        assert kwargs["bundle_id"] == "com.example.nativespeaker"
        assert kwargs["environment"] is Environment.PRODUCTION
        assert kwargs["app_apple_id"] == 123456789

    def test_a_sandbox_deployment_validates_against_the_sandbox_environment(self):
        # [utest->req~restore-apple-validate-bundle-environment~1]
        with (patch("nativespeaker.api.services.subscriptions._load_apple_root_certificates",
                    return_value=[b"root"]),
              patch("nativespeaker.api.services.subscriptions.SignedDataVerifier") as verifier):
            create_apple_verifier(self._config(environment="sandbox", app_apple_id=None))
        assert verifier.call_args.kwargs["environment"] is Environment.SANDBOX


class TestNestedPayloadVerification:
    """Each nested signed payload is verified on its own before it is used as evidence."""

    @staticmethod
    def _payload(*, renewal: str | None = "signed.renewal.info"):
        payload = MagicMock()
        payload.notificationType = NotificationTypeV2.SUBSCRIBED
        payload.subtype = None
        payload.notificationUUID = "uuid-nested"
        payload.data = MagicMock()
        payload.data.signedTransactionInfo = "signed.txn.info"
        payload.data.signedRenewalInfo = renewal
        return payload

    async def test_both_nested_payloads_are_verified(self, subscription_service, mock_verifier,
                                                     mock_subscriptions_db):
        # [utest->req~restore-apple-verify-nested-payloads~1]
        mock_verifier.verify_and_decode_notification.return_value = self._payload()
        transaction = MagicMock()
        transaction.originalTransactionId = "txn-nested"
        transaction.productId = "com.example.nativespeaker.gold"
        transaction.appAccountToken = str(uuid4())
        mock_verifier.verify_and_decode_signed_transaction.return_value = transaction
        mock_subscriptions_db.get_subscription_by_external_id.return_value = None

        await subscription_service.process_apple_notification("outer.jws.payload")

        mock_verifier.verify_and_decode_signed_transaction.assert_called_once_with(
            "signed.txn.info")
        mock_verifier.verify_and_decode_renewal_info.assert_called_once_with(
            "signed.renewal.info")

    async def test_an_invalid_nested_transaction_is_an_invalid_payload(self, subscription_service,
                                                                      mock_verifier):
        """Verifying the outer envelope is not sufficient."""
        # [utest->req~restore-apple-verify-nested-payloads~1]
        mock_verifier.verify_and_decode_notification.return_value = self._payload()
        mock_verifier.verify_and_decode_signed_transaction.side_effect = VerificationException(
            VerificationStatus.INVALID_CHAIN)
        with pytest.raises(WebhookVerificationError):
            await subscription_service.process_apple_notification("outer.jws.payload")

    async def test_an_invalid_nested_renewal_info_is_an_invalid_payload(self,
                                                                       subscription_service,
                                                                       mock_verifier):
        # [utest->req~restore-apple-verify-nested-payloads~1]
        mock_verifier.verify_and_decode_notification.return_value = self._payload()
        transaction = MagicMock()
        transaction.originalTransactionId = "txn-nested"
        transaction.productId = "com.example.nativespeaker.gold"
        mock_verifier.verify_and_decode_signed_transaction.return_value = transaction
        mock_verifier.verify_and_decode_renewal_info.side_effect = VerificationException(
            VerificationStatus.VERIFICATION_FAILURE)
        with pytest.raises(WebhookVerificationError):
            await subscription_service.process_apple_notification("outer.jws.payload")

    async def test_a_notification_without_renewal_info_verifies_the_transaction_alone(
            self, subscription_service, mock_verifier, mock_subscriptions_db):
        # [utest->req~restore-apple-verify-nested-payloads~1]
        mock_verifier.verify_and_decode_notification.return_value = self._payload(renewal=None)
        transaction = MagicMock()
        transaction.originalTransactionId = "txn-nested"
        transaction.productId = "com.example.nativespeaker.gold"
        transaction.appAccountToken = str(uuid4())
        mock_verifier.verify_and_decode_signed_transaction.return_value = transaction
        mock_subscriptions_db.get_subscription_by_external_id.return_value = None

        await subscription_service.process_apple_notification("outer.jws.payload")
        mock_verifier.verify_and_decode_renewal_info.assert_not_called()


class TestRedeliveryIdempotence:
    """Redelivery is keyed on Apple's notification UUID."""

    @staticmethod
    def _payload():
        payload = MagicMock()
        payload.notificationType = NotificationTypeV2.SUBSCRIBED
        payload.subtype = None
        payload.notificationUUID = "uuid-replay"
        payload.data = MagicMock()
        payload.data.signedTransactionInfo = "signed.txn.info"
        payload.data.signedRenewalInfo = None
        return payload

    async def test_a_replay_on_an_existing_subscription_repeats_no_side_effect(
            self, subscription_service, mock_verifier, mock_subscriptions_db):
        # [utest->req~restore-apple-redelivery-idempotent~1]
        from nativespeaker.api.models import (
            Subscription,
            SubscriptionPlan,
            SubscriptionProvider,
            SubscriptionStatus,
        )

        mock_verifier.verify_and_decode_notification.return_value = self._payload()
        transaction = MagicMock()
        transaction.originalTransactionId = "txn-replay"
        transaction.productId = "com.example.nativespeaker.gold"
        mock_verifier.verify_and_decode_signed_transaction.return_value = transaction
        mock_subscriptions_db.get_subscription_by_external_id.return_value = Subscription(
            user_id=uuid4(), provider=SubscriptionProvider.apple,
            external_id="txn-replay",
            plan=SubscriptionPlan.gold, status=SubscriptionStatus.active)
        mock_subscriptions_db.insert_event_idempotent.return_value = False

        await subscription_service.process_apple_notification("outer.jws.payload")

        mock_subscriptions_db.insert_event_idempotent.assert_awaited_once()
        assert mock_subscriptions_db.insert_event_idempotent.await_args.kwargs[
            "notification_uuid"] == "uuid-replay"
        mock_subscriptions_db.update_subscription.assert_not_called()
        mock_subscriptions_db.update_user_plan.assert_not_called()

    async def test_a_replay_that_races_the_first_delivery_applies_nothing_twice(
            self, subscription_service, mock_verifier, mock_subscriptions_db):
        # [utest->req~restore-apple-redelivery-idempotent~1]
        mock_verifier.verify_and_decode_notification.return_value = self._payload()
        transaction = MagicMock()
        transaction.originalTransactionId = "txn-race"
        transaction.productId = "com.example.nativespeaker.gold"
        transaction.appAccountToken = str(uuid4())
        mock_verifier.verify_and_decode_signed_transaction.return_value = transaction
        mock_subscriptions_db.get_subscription_by_external_id.return_value = None
        mock_subscriptions_db.insert_event_idempotent.return_value = False

        await subscription_service.process_apple_notification("outer.jws.payload")

        mock_subscriptions_db.update_user_plan.assert_not_called()
