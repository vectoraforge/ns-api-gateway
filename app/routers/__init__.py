__all__ = ["chats_router", "health_router", "prompts_router", "root_router"]

from app.routers.health import router as health_router
from app.routers.prompts import chats_router
from app.routers.prompts import router as prompts_router
from app.routers.root import router as root_router
