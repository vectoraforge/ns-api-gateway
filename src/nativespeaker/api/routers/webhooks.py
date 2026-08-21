from fastapi import APIRouter, Depends, Request, Response

from nativespeaker.api.app.dependencies import get_subscription_service
from nativespeaker.api.errors import WebhookVerificationError
from nativespeaker.api.services import SubscriptionService

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/apple",
             status_code=200,
             summary="Apple subscription webhook",
             description="Receives Apple App Store Server Notifications v2 for subscription lifecycle events.")
async def apple_webhook(request: Request,
                         service: SubscriptionService = Depends(get_subscription_service)) -> Response:
    body = await request.json()
    signed_payload = body.get("signedPayload")
    if not signed_payload:
        raise WebhookVerificationError("Missing signedPayload")
    await service.process_apple_notification(signed_payload)
    return Response(status_code=200)
