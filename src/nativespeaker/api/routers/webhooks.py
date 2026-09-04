"""The one store-callback route: `/webhooks/app-store` ingests Apple's signed notifications."""
from fastapi import APIRouter, Depends
from starlette.responses import Response

from nativespeaker.api.app.dependencies import (
    get_subscriptions_service,
    verify_app_store_notification,
)
from nativespeaker.api.auth.app_store import VerifiedNotification
from nativespeaker.api.services import SubscriptionsService

# Membership of this router is the provider-callback partition; no other router declares the verifier.
router = APIRouter(tags=["webhooks"],
                   dependencies=[Depends(verify_app_store_notification)])


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
