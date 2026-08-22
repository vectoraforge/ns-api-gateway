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
    # D-12 (Phase 36): both lists default to empty. The LLM chain is unconstrained —
    # `services/llm.py` pipes through a plain `JsonOutputParser()` rather than a
    # schema-bound call — so for a phrase that needs no correction the model
    # legitimately returns only `resolved_mode` and `response`. `services/chats.py`'s
    # `AnalyzeResponse.model_validate` then raised, and the product's primary route
    # answered 500 for an already-correct sentence (D-35-11-A).
    #
    # This is a knowing, narrow exception to 01-foundation.md §8.3 ("existing non-auth
    # error contracts unchanged"): it changes a published response shape, which is cheap
    # only because the product is pre-launch with no clients. It is exactly two field
    # defaults — `resolved_mode` and `response` stay required so a truncated provider
    # payload still fails validation instead of reaching the client as an empty success.
    # The general fix (binding these models as a strict schema on the chat model call) is
    # filed as .planning/todos/pending/restore-strict-structured-output.md.
    issues: list[Issue] = []
    suggestions: list[str] = []


class FollowUpResponse(BaseModel):
    resolved_mode: Literal["follow_up"]
    response: str


class RejectResponse(BaseModel):
    resolved_mode: Literal["reject"]
    response: str
