from importlib.metadata import version

from fastapi import APIRouter, Depends

from app.api.dependencies import get_chat_service
from app.services import ChatService

router = APIRouter()


@router.get("/")
async def root(service: ChatService = Depends(get_chat_service)):
    return {
        "name": "NativeSpeaker API Gateway",
        "version": version("ns-api-gateway"),
        "supported_languages": service.supported_languages,
    }
