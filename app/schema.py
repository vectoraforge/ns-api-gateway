from uuid import UUID

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str = Field(..., max_length=4096, description="The phrase to analyze")
    lang: str | None = Field(default="en", description="Language code (e.g., 'en', 'es')")
    chat_id: UUID | None = Field(default=None, description="Existing chat ID for follow-up")


class Issue(BaseModel):
    text_part: str = Field(..., description="The problematic part of the phrase")
    explanation: str = Field(..., description="Explanation of why this is an issue")


class AnalyzeResponse(BaseModel):
    text: str = Field(..., description="The original phrase")
    lang: str = Field(..., description="Language code used")
    chat_id: UUID = Field(..., description="Chat session ID")
    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    alternatives: list[str] = Field(default_factory=list, description="Corrected alternatives")
    assessment: str = Field(..., description="Overall assessment of naturalness")


class ExamplesResponse(BaseModel):
    lang: str = Field(..., description="Language code")
    examples: list[str] = Field(..., description="List of example phrases")


class ChatMessageRequest(BaseModel):
    text: str = Field(..., max_length=4096, description="Follow-up message text")

