from fastapi import APIRouter, Depends, Query

from nativespeaker.api.app.dependencies import get_chat_service
from nativespeaker.api.models.api import ExamplesResponse
from nativespeaker.api.services import ChatService

router = APIRouter(tags=["examples"])


@router.get("/examples",
            response_model=ExamplesResponse,
            summary="Get example phrases",
            description="Returns example phrases for a given language to help users get started.")
async def get_examples(lang: str = Query(..., description="Language code (e.g., 'en', 'es')"),
                       service: ChatService = Depends(get_chat_service)) -> ExamplesResponse:
    return service.get_examples(lang)
