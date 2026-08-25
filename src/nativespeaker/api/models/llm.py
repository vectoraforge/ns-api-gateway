from typing import Literal

from pydantic import BaseModel


class Issue(BaseModel):
    text_part: str
    explanation: str


class AnalyzeInput(BaseModel):
    mode: Literal["analyze"] = "analyze"
    phrase: str
    context: str | None = None


class FollowUpInput(BaseModel):
    mode: Literal["follow_up"] = "follow_up"
    message: str


class AnalyzeResponse(BaseModel):
    resolved_mode: Literal["analyze"]
    response: str
    # Both lists default to empty -- Pydantic copies the default per instance -- so a correct phrase validates.
    issues: list[Issue] = []
    suggestions: list[str] = []


class FollowUpResponse(BaseModel):
    resolved_mode: Literal["follow_up"]
    response: str


class RejectResponse(BaseModel):
    resolved_mode: Literal["reject"]
    response: str
