import base64
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schema import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatMessageRequest,
    ChatMessage,
    ChatMessagesResponse,
    ExamplesResponse,
)
from app.exceptions import ChatOwnershipError, InvalidCursorError
from app.auth import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompts")


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_prompt(
    request: Request,
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> AnalyzeResponse:
    service = request.app.state.service
    return await service.analyze(db, body.text, body.lang, user_id, body.chat_id)


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
    request: Request,
    chat_id: UUID,
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> AnalyzeResponse:
    service = request.app.state.service
    return await service.chat(db, chat_id, body.text, user_id)


@chats_router.get("/chats/{chat_id}/messages", response_model=ChatMessagesResponse)
async def list_chat_messages(
    request: Request,
    chat_id: UUID,
    limit: int = Query(50, ge=1),
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> ChatMessagesResponse:
    config = request.app.state.config
    if limit > config.messages_max_page_size:
        raise HTTPException(status_code=400, detail="Limit exceeds maximum page size")

    if cursor is not None:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode()).decode()
            if "|" not in decoded:
                raise ValueError
        except Exception:
            raise InvalidCursorError()

    service = request.app.state.service
    chat = await service.chats.get_chat_owned(db, chat_id, user_id)

    messages, next_cursor = await service.chats.list_messages(
        db, chat_id, limit=limit, cursor=cursor
    )

    items = [
        ChatMessage(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )
        for message in messages
    ]
    return ChatMessagesResponse(messages=items, next_cursor=next_cursor)


@chats_router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(
    request: Request,
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> Response:
    service = request.app.state.service
    await service.chats.delete_chat_owned(db, chat_id, user_id)
    return Response(status_code=204)
