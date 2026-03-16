from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_chat_service
from app.api.schema import ExamplesResponse
from app.service import ChatService

router = APIRouter()


@router.get("/examples", response_model=ExamplesResponse)
async def get_examples(lang: str = Query(..., description="Language code (e.g., 'en', 'es')"),
                       service: ChatService = Depends(get_chat_service)) -> ExamplesResponse:
    return service.get_examples(lang)
