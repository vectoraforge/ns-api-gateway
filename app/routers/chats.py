import base64
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.config import AppConfig
from app.dependencies import get_chat_service, get_config, get_user_id
from app.exceptions import InvalidCursorError, PageSizeLimitError
from app.schema import ChatListItem, ChatMessagesResponse, ChatRequest, ChatResponse, FollowupRequest
from app.services.chats import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chats", response_model=ChatResponse)
async def create_chat(body: ChatRequest,
                      user_id: str = Depends(get_user_id),
                      service: ChatService = Depends(get_chat_service)) -> ChatResponse:
    return await service.create_chat(phrase=body.phrase,
                                     user_id=user_id,
                                     comment=body.comment,
                                     lang=body.lang)


@router.post("/chats/{chat_id}", response_model=ChatResponse)
async def followup_chat(chat_id: UUID,
                        body: FollowupRequest,
                        user_id: str = Depends(get_user_id),
                        service: ChatService = Depends(get_chat_service)) -> ChatResponse:
    return await service.followup(chat_id=chat_id,
                                  content=body.content,
                                  user_id=user_id)


@router.get("/chats")
async def list_chats(user_id: str = Depends(get_user_id),
                     service: ChatService = Depends(get_chat_service)):
    chats = await service.get_chat_list(user_id)
    return [ChatListItem(id=c.id, phrase=c.phrase, created_at=c.created_at) for c in chats]


@router.get("/chats/{chat_id}", response_model=ChatMessagesResponse)
async def get_chat_messages(chat_id: UUID,
                            limit: int = Query(50, ge=1),
                            cursor: str | None = Query(None),
                            user_id: str = Depends(get_user_id),
                            service: ChatService = Depends(get_chat_service),
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

    return await service.get_messages(chat_id=chat_id,
                                      user_id=user_id,
                                      limit=limit,
                                      cursor=cursor)


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(chat_id: UUID,
                      user_id: str = Depends(get_user_id),
                      service: ChatService = Depends(get_chat_service)) -> Response:
    await service.delete_chat(chat_id, user_id)
    return Response(status_code=204)
