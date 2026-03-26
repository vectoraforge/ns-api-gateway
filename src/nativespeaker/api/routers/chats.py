from uuid import UUID

from fastapi import APIRouter, Depends, Response

from nativespeaker.api.app.dependencies import get_chat_service, get_current_user, require_quota
from nativespeaker.api.models.api import ChatRequest, ChatResponse, MessageRequest, MessageResponse
from nativespeaker.api.models import User
from nativespeaker.api.services import ChatService

router = APIRouter(tags=["chats"])


@router.get("/chats",
            response_model=list[ChatResponse],
            summary="List chats",
            description="Returns all chat sessions belonging to the authenticated user.")
async def list_chats(user: User = Depends(get_current_user),
                     service: ChatService = Depends(get_chat_service)):
    chats = await service.list_chats(user.id)
    return [ChatResponse(chat_id=chat.id, title=chat.title,
                         created_at=chat.created_at, lang=chat.lang)
            for chat in chats]


@router.get("/chats/{chat_id}",
            response_model=list[MessageResponse],
            summary="Get chat messages",
            description="Returns all messages in a chat session, ordered chronologically.")
async def get_chat_messages(chat_id: UUID,
                            user: User = Depends(get_current_user),
                            service: ChatService = Depends(get_chat_service)) -> list[MessageResponse]:
    messages = await service.get_messages(chat_id=chat_id, user_id=user.id)
    return [
        MessageResponse(chat_id=message.chat_id, role=message.role,
                        content=message.content,
                        created_at=message.created_at)
        for message in messages
    ]


@router.post("/chats",
             response_model=MessageResponse,
             dependencies=[Depends(require_quota)],
             summary="Start new analysis",
             description="Analyzes a phrase and creates a new chat session with the AI response. Consumes one request from the user's monthly quota.",
             response_description="AI analysis message")
async def create_chat(body: ChatRequest,
                      user: User = Depends(get_current_user),
                      service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ai_message = await service.create_chat(user=user, phrase=body.phrase,
                                           context=body.context, lang=body.lang)
    return MessageResponse(chat_id=ai_message.chat_id, role=ai_message.role,
                           content=ai_message.content,
                           created_at=ai_message.created_at)


@router.post("/chats/{chat_id}",
             response_model=MessageResponse,
             dependencies=[Depends(require_quota)],
             summary="Send follow-up message",
             description="Sends a follow-up message in an existing chat session. Consumes one request from the user's monthly quota.",
             response_description="AI follow-up message")
async def send_message(chat_id: UUID,
                       body: MessageRequest,
                       user: User = Depends(get_current_user),
                       service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ai_message = await service.send_message(chat_id=chat_id, user=user,
                                            message=body.message)
    return MessageResponse(chat_id=ai_message.chat_id, role=ai_message.role,
                           content=ai_message.content,
                           created_at=ai_message.created_at)


@router.delete("/chats/{chat_id}",
               status_code=204,
               summary="Delete chat",
               description="Permanently deletes a chat session and all its messages.")
async def delete_chat(chat_id: UUID,
                      user: User = Depends(get_current_user),
                      service: ChatService = Depends(get_chat_service)) -> Response:
    await service.delete_chat(chat_id, user.id)
    return Response(status_code=204)
