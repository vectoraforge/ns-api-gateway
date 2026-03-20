from importlib.metadata import version

from fastapi import APIRouter, Depends

from app.api.dependencies import get_chat_service
from app.services import ChatService

router = APIRouter()


@router.get("/")
async def root(service: ChatService = Depends(get_chat_service)):
    return {
        "name": "SpeakNative API Gateway",
        "version": version("sn-api-gateway"),
        "supported_languages": service.supported_languages,
    }
