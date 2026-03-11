from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ErrorCode = Literal["invalid_request",
                    "unauthorized",
                    "not_found",
                    "service_unavailable",
                    "internal_error"]


class ErrorResponse(BaseModel):
    code: ErrorCode


class Issue(BaseModel):
    text_part: str = Field(..., description="The problematic part of the phrase")
    explanation: str = Field(..., description="Explanation of why this is an issue")


class ChatResponseLLM(BaseModel):
    """LLM structured output schema."""
    issues: list[Issue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    response: str


class ChatRequest(BaseModel):
    """New chat request."""
    phrase: str = Field(..., max_length=4096)
    comment: str | None = Field(default=None, max_length=4096)
    lang: str | None = Field(default=None)


class FollowupRequest(BaseModel):
    """Followup message in existing chat."""
    content: str = Field(..., max_length=4096)


class ChatResponse(BaseModel):
    """API response for both new chat and followup."""
    chat_id: UUID
    issues: list[Issue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    response: str


class MessageResponse(BaseModel):
    """Single message in a chat history listing."""
    id: int
    role: str
    content: str
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    """Chat detail with paginated messages."""
    id: UUID
    phrase: str
    comment: str | None
    lang: str | None
    created_at: datetime
    messages: list[MessageResponse]
    next_cursor: str | None = None


class ChatListItem(BaseModel):
    """Item in the chat list."""
    id: UUID
    phrase: str
    created_at: datetime


class ExamplesResponse(BaseModel):
    lang: str = Field(..., description="Language code")
    examples: list[str] = Field(..., description="List of example phrases")
