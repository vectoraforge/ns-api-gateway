from collections.abc import Awaitable, Callable, Iterable

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
    body = await request.json()
    verifiers = {"apple_signed_payload":
                 apple_signed_payload_verifier(service.process_apple_notification)}
    try:
        await verify_provider_callback(
            CallbackRequest("POST", APPLE_WEBHOOK_PATH, body=body), verifiers)
    except ProviderCallbackError as exc:
        raise WebhookVerificationError(str(exc)) from None
    return Response(status_code=200)


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
