from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from nativespeaker.api.exceptions import ErrorCode


class ErrorResponse(BaseModel):
    code: ErrorCode


class ChatRequest(BaseModel):
    """New chat request."""
    phrase: str = Field(..., max_length=4096)
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
    message: str = Field(..., max_length=4096)


class MessageResponse(BaseModel):
    """API response for both new chat and followup."""
    chat_id: UUID
    role: str
    content: dict
    created_at: datetime


class ExamplesResponse(BaseModel):
    lang: str = Field(..., description="Language code")
    examples: list[str] = Field(..., description="List of example phrases")


class UserProfileResponse(BaseModel):
    email: str | None = None
    name: str | None = None
    # The effective access grant's tier, or `none` where the user holds no effective grant.
    subscription_plan: str
    created_at: datetime
    requests_used: int
    monthly_limit: int
    resets_at: datetime
