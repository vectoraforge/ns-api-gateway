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


class ChatModelResponse(BaseModel):
    """The one shape the provider is asked for: every field any of the three modes can produce.

    Flat on purpose, and that is load-bearing. The strict-schema conversion rewrites an object by
    forcing every property into `required` and refusing undeclared ones, but it does not descend
    into a root-level union -- so a discriminated-union root would ship looking strict while leaving
    every branch, and the nested `Issue`, unconstrained.

    `AnalyzeResponse`, `FollowUpResponse` and `RejectResponse` are unchanged. They remain the
    client-facing contract and the post-hoc validation `ChatService.ask_llm` performs; this model
    describes only what is asked of the provider.
    """
    resolved_mode: Literal["analyze", "follow_up", "reject"]
    response: str
    issues: list[Issue] = []
    suggestions: list[str] = []
