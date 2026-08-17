from collections.abc import Awaitable, Callable, Iterable, Mapping

from fastapi import APIRouter, Depends, Request, Response

from nativespeaker.api.app.dependencies import get_subscription_service
from nativespeaker.api.auth.callbacks import (
    CallbackRequest,
    ProviderCallbackError,
    apple_signed_payload_verifier,
    registered_callback_routes,
    verify_provider_callback,
)
from nativespeaker.api.exceptions import WebhookVerificationError
from nativespeaker.api.services import SubscriptionService

APPLE_WEBHOOK_PATH = "/webhooks/app-store"

# The status codes this route answers with. A store server is not an app client, so the route
# reports plain HTTP status codes rather than the shared client-visible error classes.
INGESTION_ACCEPTED = 200
INGESTION_UNAUTHENTICATED = 401


async def apple_webhook(request: Request,
                        service: SubscriptionService = Depends(get_subscription_service)
                        ) -> Response:
    """Receives Apple App Store Server Notifications v2 for subscription lifecycle events."""
    # A provider-callback route: Apple calls it from its own servers with no Firebase ID token,
    # so it never passes the barrier, and it is not public either. What admits the call is the
    # one named verifier the route registry declares for this exact path — Apple's signed
    # payload, verified by this backend. The request carries no `Authorization` field, and a
    # Firebase user token would not stand in for that verification.
    # [impl->req~sessions-webhook-app-store-path~1]
    # [impl->req~sessions-provider-callback-third-category~1]
    # [impl->req~sessions-gateway-never-parses-apple-signedpayload~1]
    # Apple sends no `Authorization` header and no shared secret: the body is a single
    # `signedPayload` field, a JWS Apple signed, so verifying that payload is how the notification
    # is both authenticated and read. This route reads no `Authorization` field at all.
    # [impl->req~restore-apple-webhook-signed-payload-auth~1]
    # This route is the store subscription ingestion path, not a canonical state-changing auth
    # operation: it writes no `audit.auth_events` row and answers in plain HTTP status codes.
    # [impl->req~restore-ingestion-provider-callback-routes~1]
    try:
        body = await request.json()
    except ValueError:
        # A malformed envelope, rejected before any business logic runs.
        # [impl->req~restore-apple-invalid-payload-401~1]
        return Response(status_code=INGESTION_UNAUTHENTICATED)
    if not isinstance(body, Mapping):
        # [impl->req~restore-apple-invalid-payload-401~1]
        return Response(status_code=INGESTION_UNAUTHENTICATED)
    verifiers = {"apple_signed_payload":
                 apple_signed_payload_verifier(service.process_apple_notification)}
    try:
        await verify_provider_callback(
            CallbackRequest("POST", APPLE_WEBHOOK_PATH, body=body), verifiers)
    except (ProviderCallbackError, WebhookVerificationError):
        # A missing, malformed or invalid payload — at the envelope or at any nested payload — is
        # rejected with HTTP 401, with no ingestion and no entitlement effect.
        # [impl->req~restore-apple-invalid-payload-401~1]
        return Response(status_code=INGESTION_UNAUTHENTICATED)
    # HTTP 200 only once the notification is durably persisted or applied. An internal failure
    # raises out of this commit and surfaces as 5xx, so Apple's own retry schedule covers it.
    # [impl->req~restore-apple-200-only-after-durable~1]
    await service.commit()
    return Response(status_code=INGESTION_ACCEPTED)


# The handler each registered callback route is served by, keyed by the registry's exact path.
_HANDLERS: dict[str, Callable[..., Awaitable[Response]]] = {
    APPLE_WEBHOOK_PATH: apple_webhook,
}


def build_webhooks_router(configured_integrations: Iterable[str]) -> APIRouter:
    """The store-webhook routes this deployment registers, built from the callback registry
    filtered by the store integrations the configuration actually carries.

    A store whose integration is unconfigured gets no route at all: its path is simply absent
    from `app.routes`, rather than registered and then refused at request time or at startup.
    """
    # [impl->req~sessions-named-verifier-per-callback-route~1]
    router = APIRouter(tags=["webhooks"])
    for route in registered_callback_routes(configured_integrations):
        endpoint = _HANDLERS.get(route.path)
        if endpoint is None:
            continue
        router.add_api_route(route.path, endpoint, methods=[route.method], status_code=200)
    return router
