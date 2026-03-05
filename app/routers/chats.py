import base64
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppConfig
from app.dependencies import get_config, get_db, get_service, get_user_id
from app.exceptions import InvalidCursorError, PageSizeLimitError
from app.schema import ChatMessage, ChatMessagesResponse, ChatRequest, ChatResponse
from app.services import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chats", response_model=ChatResponse)
async def create_or_continue_chat(body: ChatRequest,
                                  db: AsyncSession = Depends(get_db),
                                  user_id: str = Depends(get_user_id),
                                  service: ChatService = Depends(get_service)) -> ChatResponse:
    return await service.chat(db, body.text, user_id, lang=body.lang, chat_id=body.chat_id)


@router.get("/chats/{chat_id}/messages", response_model=ChatMessagesResponse)
async def list_chat_messages(chat_id: UUID,
                             limit: int = Query(50, ge=1),
                             cursor: str | None = Query(None),
                             db: AsyncSession = Depends(get_db),
                             user_id: str = Depends(get_user_id),
                             service: ChatService = Depends(get_service),
                             config: AppConfig = Depends(get_config)) -> ChatMessagesResponse:
    if limit > config.messages_max_page_size:
        raise PageSizeLimitError(config.messages_max_page_size)

    if cursor is not None:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode()).decode()
            if "|" not in decoded:
                raise ValueError
        except Exception:
            raise InvalidCursorError()

    messages, next_cursor = await service.chats.list_messages(db, chat_id, user_id, limit=limit, cursor=cursor)

    items = [ChatMessage(id=message.id,
                         role=message.role,
                         content=message.content,
                         created_at=message.created_at)
             for message in messages]
    return ChatMessagesResponse(messages=items, next_cursor=next_cursor)


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(chat_id: UUID,
                      db: AsyncSession = Depends(get_db),
                      user_id: str = Depends(get_user_id),
                      service: ChatService = Depends(get_service)) -> Response:
    await service.chats.delete_chat(db, chat_id, user_id)
    return Response(status_code=204)
