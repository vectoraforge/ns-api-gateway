"""The two store-callback routes: Apple's signed notifications, and Google's Pub/Sub pushes."""
from fastapi import APIRouter, Depends
from starlette.responses import Response

from nativespeaker.api.app.dependencies import (
    get_subscriptions_service,
    verify_app_store_notification,
    verify_google_play_notification,
)
from nativespeaker.api.auth.store_notifications import VerifiedNotification
from nativespeaker.api.services import SubscriptionsService

# Membership of this router is the provider-callback partition; each route declares its own verifier.
router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/app-store",
             status_code=200,
             summary="Ingest one App Store Server Notification",
             description="Verifies Apple's signed envelope and both nested payloads against the "
                         "pinned Apple root, then records the subscription and its event. It reads "
                         "no Authorization header.")
async def app_store_notification(
        notification: VerifiedNotification = Depends(verify_app_store_notification),
        service: SubscriptionsService = Depends(get_subscriptions_service)) -> Response:
    """Record one verified notification, or answer 200 having written nothing."""
    await service.ingest(notification)
    # An empty body: Apple reads the status code and nothing else.
    return Response(status_code=200)


@router.post("/webhooks/google-play/rtdn",
             status_code=200,
             summary="Ingest one Google Play real-time developer notification",
             description="Verifies the Cloud Pub/Sub push token against Google's own keys, reads "
                         "the subscription's live state from the Play Developer API, then records "
                         "the subscription and its event.")
async def google_play_notification(
        notification: VerifiedNotification | None = Depends(verify_google_play_notification),
        service: SubscriptionsService = Depends(get_subscriptions_service)) -> Response:
    """Record one verified notification, or answer 200 having written nothing."""
    if notification is not None:
        await service.ingest(notification)
    # An empty body: Pub/Sub reads the status code and nothing else.
    return Response(status_code=200)
