from typing import Annotated

from pydantic import BaseModel, Field, Tag, Discriminator, TypeAdapter
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB


class Issue(BaseModel):
    text_part: str = Field(..., description="The problematic part of the phrase")
    explanation: str = Field(..., description="Explanation of why this is an issue")


class HumanContent(BaseModel):
    phrase: str
    comment: str | None = None


class AIContent(BaseModel):
    response: str
    issues: list[Issue] | None = None
    suggestions: list[str] | None = None


def content_discriminator(v):
    if isinstance(v, dict):
        return "human" if "phrase" in v else "ai"
    return "human" if isinstance(v, HumanContent) else "ai"


ContentUnion = Annotated[
    Annotated[HumanContent, Tag("human")] | Annotated[AIContent, Tag("ai")],
    Discriminator(content_discriminator),
]


class PydanticJSONB(TypeDecorator):
    impl = JSONB
    cache_ok = True

    def __init__(self, pydantic_type):
        super().__init__()
        self._adapter = TypeAdapter(pydantic_type)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._adapter.validate_python(value)
