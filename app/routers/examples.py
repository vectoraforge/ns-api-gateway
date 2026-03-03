from fastapi import APIRouter, Depends, Query

from app.dependencies import get_service
from app.schema import ExamplesResponse
from app.services import ChatService

router = APIRouter()


@router.get("/examples", response_model=ExamplesResponse)
async def get_examples(
    lang: str = Query(..., description="Language code (e.g., 'en', 'es')"),
    service: ChatService = Depends(get_service),
) -> ExamplesResponse:
    return service.get_examples(lang)
