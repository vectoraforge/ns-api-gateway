__all__ = ["auth_router", "chats_router", "examples_router", "health_router", "root_router",
           "users_router", "webhooks_router"]

from nativespeaker.api.routers.auth import router as auth_router
from nativespeaker.api.routers.chats import router as chats_router
from nativespeaker.api.routers.examples import router as examples_router
from nativespeaker.api.routers.health import router as health_router
from nativespeaker.api.routers.root import router as root_router
from nativespeaker.api.routers.users import router as users_router
from nativespeaker.api.routers.webhooks import router as webhooks_router
