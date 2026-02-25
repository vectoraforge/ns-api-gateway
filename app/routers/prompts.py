import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schema import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatMessageRequest,
    ExamplesResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompts")


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(request: Request, body: AnalyzeRequest, db: AsyncSession = Depends(get_db)) -> AnalyzeResponse:
    service = request.app.state.service
    return await service.analyze(db, body.text, body.lang, body.chat_id)


@router.get("/examples", response_model=ExamplesResponse)
async def get_examples(
    request: Request,
    lang: str = Query(..., description="Language code (e.g., 'en', 'es')"),
) -> ExamplesResponse:
    service = request.app.state.service
    return service.get_examples(lang)


chats_router = APIRouter()


@chats_router.post("/chats/{chat_id}/messages", response_model=AnalyzeResponse)
async def chat_message(
    request: Request, chat_id: UUID, body: ChatMessageRequest, db: AsyncSession = Depends(get_db)
) -> AnalyzeResponse:
    service = request.app.state.service
    return await service.chat(db, chat_id, body.text)
