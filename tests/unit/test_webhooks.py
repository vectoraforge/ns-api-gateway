from unittest.mock import AsyncMock

import pytest

from app.exceptions import WebhookVerificationError


class TestAppleWebhook:
    """Tests for POST /webhooks/apple endpoint (SUBS-01, SUBS-02)."""

    def test_receives_notification(self, webhook_client, mock_subscription_service):
        """SUBS-01: Endpoint receives and acknowledges Apple notification."""
        response = webhook_client.post(
            "/webhooks/apple",
            json={"signedPayload": "valid.jws.token"},
        )
        assert response.status_code == 200
        assert response.content == b""
        mock_subscription_service.process_apple_notification.assert_called_once_with(
            "valid.jws.token"
        )

    def test_missing_signed_payload(self, webhook_client):
        """SUBS-01: Missing signedPayload returns 400."""
        response = webhook_client.post("/webhooks/apple", json={})
        assert response.status_code == 400
        assert response.json()["code"] == "validation_error"

    def test_empty_signed_payload(self, webhook_client):
        """SUBS-01: Empty signedPayload returns 400."""
        response = webhook_client.post(
            "/webhooks/apple",
            json={"signedPayload": ""},
        )
        assert response.status_code == 400

    def test_invalid_jws_rejected(self, webhook_client, mock_subscription_service):
        """SUBS-02: Invalid JWS signatures rejected with 400."""
        mock_subscription_service.process_apple_notification.side_effect = (
            WebhookVerificationError("Invalid signature")
        )
        response = webhook_client.post(
            "/webhooks/apple",
            json={"signedPayload": "invalid.jws.token"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "validation_error"

    def test_no_jwt_auth_required(self, webhook_client, mock_subscription_service):
        """SUBS-01: Webhook does not require JWT Bearer token."""
        # No Authorization header provided -- should still succeed
        response = webhook_client.post(
            "/webhooks/apple",
            json={"signedPayload": "valid.jws.token"},
        )
        assert response.status_code == 200
