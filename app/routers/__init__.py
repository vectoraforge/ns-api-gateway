__all__ = ["chats_router", "examples_router", "health_router", "root_router"]

from app.routers.chats import router as chats_router
from app.routers.examples import router as examples_router
from app.routers.health import router as health_router
from app.routers.root import router as root_router
