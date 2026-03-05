from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ErrorCode = Literal["invalid_request",
                    "unauthorized",
                    "not_found",
                    "service_unavailable",
                    "internal_error"]


class ErrorResponse(BaseModel):
    code: ErrorCode


class ChatRequest(BaseModel):
    text: str = Field(..., max_length=4096, description="The phrase to analyze")
    lang: str | None = Field(default=None, description="Language code (e.g., 'en', 'es')")
    chat_id: UUID | None = Field(default=None, description="Existing chat ID for continuation")

    @model_validator(mode="after")
    def require_lang_for_new_chat(self) -> "ChatRequest":
        if self.chat_id is None and self.lang is None:
            raise ValueError("'lang' is required when starting a new chat (no chat_id)")
        return self


class Issue(BaseModel):
    text_part: str = Field(..., description="The problematic part of the phrase")
    explanation: str = Field(..., description="Explanation of why this is an issue")


class ChatResponseLLM(BaseModel):
    """Schema for LLM structured output."""

    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    suggestions: list[str] = Field(default_factory=list, description="Suggested corrections")
    response: str = Field(..., description="Overall assessment of naturalness")


class ChatResponse(BaseModel):
    text: str = Field(..., description="The original phrase")
    chat_id: UUID = Field(..., description="Chat session ID")
    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    suggestions: list[str] = Field(default_factory=list, description="Suggested corrections")
    response: str = Field(..., description="Overall assessment of naturalness")


class ExamplesResponse(BaseModel):
    lang: str = Field(..., description="Language code")
    examples: list[str] = Field(..., description="List of example phrases")


class ChatMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    messages: list[ChatMessage]
    next_cursor: str | None = None
