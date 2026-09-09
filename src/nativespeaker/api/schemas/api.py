from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """New chat request."""
    # Non-empty, so an unusable body is the framework's 422 and never a charged credit: `create_chat`
    # spends the monthly allowance at `services/chats.py:96` before the provider sees the phrase, and
    # `services/quota.py` never refunds one. The same rule the challenge handle is bounded under.
    phrase: str = Field(..., min_length=1, max_length=4096)
    context: str | None = Field(default=None, max_length=4096)
    lang: str | None = Field(default=None)


class ChatResponse(BaseModel):
    """API response for new chat."""
    chat_id: UUID
    title: str
    created_at: datetime
    lang: str | None = None


class MessageRequest(BaseModel):
    """Followup message in existing chat."""
    # Non-empty, for the reason `ChatRequest.phrase` is: `send_message` charges before it asks.
    message: str = Field(..., min_length=1, max_length=4096)


class MessageResponse(BaseModel):
    """API response for both new chat and followup."""
    chat_id: UUID
    role: str
    content: dict
    created_at: datetime


class ExamplesResponse(BaseModel):
    lang: str = Field(..., description="Language code")
    examples: list[str] = Field(..., description="List of example phrases")
