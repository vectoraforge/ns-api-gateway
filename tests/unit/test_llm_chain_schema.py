"""What the provider is actually asked for, checked without calling a provider.

Every declared key required, no undeclared key accepted, and a plain dict handed back.
"""

from langchain_core.runnables import RunnableLambda
from langchain_core.utils.function_calling import convert_to_json_schema

from nativespeaker.api.schemas.llm import ChatModelResponse
from nativespeaker.api.services.llm import LLMService

DECLARED_KEYS = {"resolved_mode", "response", "issues", "suggestions"}


def strict_schema() -> dict:
    return convert_to_json_schema(ChatModelResponse, strict=True)


class TestEmittedSchemaIsStrict:

    def test_every_declared_key_is_required(self):
        assert set(strict_schema()["required"]) == DECLARED_KEYS

    def test_undeclared_keys_are_forbidden(self):
        assert strict_schema()["additionalProperties"] is False

    def test_nested_issue_is_equally_constrained(self):
        """The strict rewrite has to reach the nested object too, or `issues` entries stay loose."""
        issue = strict_schema()["properties"]["issues"]["items"]

        assert issue["additionalProperties"] is False
        assert set(issue["required"]) == {"text_part", "explanation"}

    def test_root_is_flat_rather_than_a_union(self):
        """A discriminated-union root is left un-rewritten by the strict conversion, so it would
        ship looking strict while every branch stayed unconstrained."""
        schema = strict_schema()

        assert schema["type"] == "object"
        assert "oneOf" not in schema
        assert "anyOf" not in schema


class RecordingModel:
    """A chat model stand-in that records how the schema was bound and returns a fixed model.

    Only the provider call is replaced, so the real `create_chain` wiring is exercised.
    """

    def __init__(self, produces: ChatModelResponse) -> None:
        self.produces = produces
        self.bindings: list[dict] = []

    def with_structured_output(self, schema, **kwargs):
        self.bindings.append({"schema": schema, **kwargs})
        return RunnableLambda(lambda _inputs: self.produces)


def chain_over(model: RecordingModel):
    """`create_chain` with the provider replaced -- `__init__` would build a real client."""
    service = LLMService.__new__(LLMService)
    service.llm = model
    return service.create_chain(prompt="You are a linguistic editor for {lang}.")


class TestChainContract:

    def test_chain_yields_a_plain_dict(self):
        """`ChatService.ask_llm` calls `.get("resolved_mode")` on this -- a model instance breaks it."""
        model = RecordingModel(ChatModelResponse(resolved_mode="analyze", response="Looks good"))

        result = chain_over(model).invoke({"history": [], "content": "hello", "lang": "English"})

        assert isinstance(result, dict)
        assert result["resolved_mode"] == "analyze"

    def test_schema_is_bound_strictly_at_the_call(self):
        model = RecordingModel(ChatModelResponse(resolved_mode="analyze", response="Looks good"))

        chain_over(model)

        assert len(model.bindings) == 1
        binding = model.bindings[0]
        assert binding["schema"] is ChatModelResponse
        assert binding["method"] == "json_schema"
        assert binding["strict"] is True
