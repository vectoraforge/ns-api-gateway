from uuid import UUID

from fastapi import APIRouter, Depends, Response

from nativespeaker.api.app.dependencies import (
    get_chat_service,
    get_linked_identity,
)
from nativespeaker.api.auth.context import LinkedIdentity
from nativespeaker.api.models.api import ChatRequest, ChatResponse, MessageRequest, MessageResponse
from nativespeaker.api.services import ChatService

# Authentication is default-on for this router (D-07); see `root.py` for why both levels declare it.
router = APIRouter(tags=["chats"], dependencies=[Depends(get_linked_identity)])

# Every handler below reads the one identity context the auth dependency resolved, through the §1.4
# accessor and nothing else (D-02). `get_linked_identity` raises rather than returning `None`, so a
# handler cannot serve a request admission refused. Handlers take `identity.user.id` -- the
# resolved primary key -- and never a `User` row they could read a second classifier off.
#
# The two quota-consuming POSTs carry no decorator dependency: the charge used to be one, and
# running before the handler body is exactly what made five of this router's own rejections -- an
# unsupported language, either history limit, an unknown chat id, and the resilience layer's
# backpressure -- charge a caller for a request that never reached the provider (REBIND-06). It now
# travels inside `ChatService`, which spends at the provider-admission seam and nowhere else.


@router.get("/chats",
            response_model=list[ChatResponse],
            summary="List chats",
            description="Returns all chat sessions belonging to the authenticated user.")
async def list_chats(identity: LinkedIdentity = Depends(get_linked_identity),
                     service: ChatService = Depends(get_chat_service)):
    chats = await service.list_chats(identity.user.id)
    return [ChatResponse(chat_id=chat.id, title=chat.title,
                         created_at=chat.created_at, lang=chat.lang)
            for chat in chats]


@router.get("/chats/{chat_id}",
            response_model=list[MessageResponse],
            summary="Get chat messages",
            description="Returns all messages in a chat session, ordered chronologically.")
async def get_chat_messages(chat_id: UUID,
                            identity: LinkedIdentity = Depends(get_linked_identity),
                            service: ChatService = Depends(get_chat_service)) -> list[MessageResponse]:
    messages = await service.get_messages(chat_id=chat_id, user_id=identity.user.id)
    return [
        MessageResponse(chat_id=message.chat_id, role=message.role,
                        content=message.content,
                        created_at=message.created_at)
        for message in messages
    ]


@router.post("/chats",
             response_model=MessageResponse,
             summary="Start new analysis",
             description="Analyzes a phrase and creates a new chat session with the AI response. "
                         "Consumes one request from the user's monthly quota.",
             response_description="AI analysis message")
async def create_chat(body: ChatRequest,
                      identity: LinkedIdentity = Depends(get_linked_identity),
                      service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ai_message = await service.create_chat(user_id=identity.user.id, phrase=body.phrase,
                                           context=body.context, lang=body.lang)
    return MessageResponse(chat_id=ai_message.chat_id, role=ai_message.role,
                           content=ai_message.content,
                           created_at=ai_message.created_at)


@router.post("/chats/{chat_id}",
             response_model=MessageResponse,
             summary="Send follow-up message",
             description="Sends a follow-up message in an existing chat session. "
                         "Consumes one request from the user's monthly quota.",
             response_description="AI follow-up message")
async def send_message(chat_id: UUID,
                       body: MessageRequest,
                       identity: LinkedIdentity = Depends(get_linked_identity),
                       service: ChatService = Depends(get_chat_service)) -> MessageResponse:
    ai_message = await service.send_message(chat_id=chat_id, user_id=identity.user.id,
                                            message=body.message)
    return MessageResponse(chat_id=ai_message.chat_id, role=ai_message.role,
                           content=ai_message.content,
                           created_at=ai_message.created_at)


@router.delete("/chats/{chat_id}",
               status_code=204,
               summary="Delete chat",
               description="Permanently deletes a chat session and all its messages.")
async def delete_chat(chat_id: UUID,
                      identity: LinkedIdentity = Depends(get_linked_identity),
                      service: ChatService = Depends(get_chat_service)) -> Response:
    await service.delete_chat(chat_id, identity.user.id)
    return Response(status_code=204)
