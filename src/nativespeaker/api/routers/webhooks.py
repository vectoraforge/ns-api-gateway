from fastapi import APIRouter, Depends, Request, Response

from nativespeaker.api.app.dependencies import get_subscription_service
from nativespeaker.api.auth.callbacks import (
    CallbackRequest,
    ProviderCallbackError,
    apple_signed_payload_verifier,
    verify_provider_callback,
)
from nativespeaker.api.exceptions import WebhookVerificationError
from nativespeaker.api.services import SubscriptionService

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/app-store",
             status_code=200,
             summary="Apple subscription webhook",
             description="Receives Apple App Store Server Notifications v2 for subscription lifecycle events.")
async def apple_webhook(request: Request,
                         service: SubscriptionService = Depends(get_subscription_service)) -> Response:
    # A provider-callback route: Apple calls it from its own servers with no Firebase ID token,
    # so it never passes the barrier, and it is not public either. What admits the call is the
    # one named verifier the route registry declares for this exact path — Apple's signed
    # payload, verified by this backend. The request carries no `Authorization` field, and a
    # Firebase user token would not stand in for that verification.
    # [impl->req~sessions-webhook-app-store-path~1]
    # [impl->req~sessions-provider-callback-third-category~1]
    # [impl->req~sessions-gateway-never-parses-apple-signedpayload~1]
    body = await request.json()
    verifiers = {"apple_signed_payload":
                 apple_signed_payload_verifier(service.process_apple_notification)}
    try:
        await verify_provider_callback(
            CallbackRequest("POST", "/webhooks/app-store", body=body), verifiers)
    except ProviderCallbackError as exc:
        raise WebhookVerificationError(str(exc)) from None
    return Response(status_code=200)
