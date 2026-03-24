from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from nativespeaker.api.exceptions import ErrorCode
from nativespeaker.api.models.subscriptions import SubscriptionPlan


class ErrorResponse(BaseModel):
    code: ErrorCode


class ChatRequest(BaseModel):
    """New chat request."""
    phrase: str = Field(..., max_length=4096)
    comment: str | None = Field(default=None, max_length=4096)
    lang: str | None = Field(default=None)


class ChatResponse(BaseModel):
    """API response for new chat."""
    chat_id: UUID
    title: str
    created_at: datetime
    lang: str | None = None


class MessageRequest(BaseModel):
    """Followup message in existing chat."""
    content: str = Field(..., max_length=4096)


class MessageResponse(BaseModel):
    """API response for both new chat and followup."""
    chat_id: UUID
    role: str
    content: str
    created_at: datetime


class ExamplesResponse(BaseModel):
    lang: str = Field(..., description="Language code")
    examples: list[str] = Field(..., description="List of example phrases")


class UserProfileResponse(BaseModel):
    email: str
    name: str | None = None
    subscription_plan: SubscriptionPlan
    created_at: datetime
    requests_used: int
    monthly_limit: int
    resets_at: datetime
