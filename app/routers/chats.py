import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import get_chat_service, get_user_id
from app.api.schema import ChatListItem, ChatMessagesResponse, ChatRequest, MessageResponse, MessageRequest
from app.service import ChatService
from app.api.schema import ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chats", response_model=MessageResponse)
async def create_chat(body: ChatRequest,
                      user_id: str = Depends(get_user_id),
                      service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ai_message = await service.create_chat(user_id=user_id, phrase=body.phrase,
                                           comment=body.comment, lang=body.lang)
    return MessageResponse(chat_id=ai_message.chat_id, role=ai_message.role,
                           content=ai_message.content.model_dump_json(),
                           created_at=ai_message.created_at)


@router.post("/chats/{chat_id}", response_model=MessageResponse)
async def send_message(chat_id: UUID,
                       body: MessageRequest,
                       user_id: str = Depends(get_user_id),
                       service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ai_message = await service.send_message(chat_id=chat_id, user_id=user_id,
                                            content=body.content)

    return MessageResponse(chat_id=ai_message.chat_id, role=ai_message.role,
                           content=ai_message.content.model_dump_json(),
                           created_at=ai_message.created_at)


@router.get("/chats", response_model=list[ChatResponse])
async def list_chats(user_id: str = Depends(get_user_id),
                     service: ChatService = Depends(get_chat_service)):
    chats = await service.get_chat_list(user_id)
    return [ChatResponse(chat_id=chat.id, title=chat.title,
                         created_at=chat.created_at, lang=chat.lang)
            for chat in chats]


@router.get("/chats/{chat_id}", response_model=ChatMessagesResponse)
async def get_chat_messages(chat_id: UUID,
                            user_id: str = Depends(get_user_id),
                            service: ChatService = Depends(get_chat_service)) -> ChatMessagesResponse:
    messages = await service.get_messages(chat_id=chat_id, user_id=user_id)
    return [
        MessageResponse(chat_id=message.chat_id, role=message.role,
                        content=message.content.model_dump_json(),
                        created_at=message.created_at)
        for message in messages
    ]


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(chat_id: UUID,
                      user_id: str = Depends(get_user_id),
                      service: ChatService = Depends(get_chat_service)) -> Response:
    await service.delete_chat(chat_id, user_id)
    return Response(status_code=204)
