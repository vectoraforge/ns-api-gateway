"""The provider honoured `strict=True`, read from its own JSON before Pydantic filled any default.

The phrase is the defect case, and these cases skip without a real provider key.
"""
import json
import os

import pytest
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from nativespeaker.api.schemas.llm import ChatModelResponse
from nativespeaker.api.services.llm import LLMService

pytestmark = pytest.mark.e2e

DECLARED_KEYS = {"resolved_mode", "response", "issues", "suggestions"}

# Shaped like what ChatService sends: the human message content, serialised.
CORRECT_PHRASE = json.dumps({"mode": "analyze", "phrase": "I am going home."})


@pytest.fixture(scope="module")
def provider_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY is not set -- this gate needs a real provider, and a mocked "
                    "chain would prove nothing about whether the constraint was honoured")
    return key


@pytest.fixture(scope="module")
def llm_service(_app_config, provider_key) -> LLMService:
    """The shipped service on the configured model."""
    return LLMService(model_config=_app_config.model,
                      resilence_config=_app_config.resilience,
                      system_prompt=_app_config.prompt)


def provider_payload(raw) -> dict:
    """The provider's own JSON object, read from the tool call's arguments or the message content."""
    if getattr(raw, "tool_calls", None):
        return dict(raw.tool_calls[0]["args"])

    content = raw.content
    if isinstance(content, list):
        content = "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return json.loads(content)


@pytest.mark.asyncio(loop_scope="module")
class TestProviderHonoursStrictSchema:

    async def test_raw_output_carries_every_declared_key(self, llm_service, _app_config):
        """Asserted against the raw payload: the parsed model would have defaulted the missing lists."""
        bound = llm_service.llm.with_structured_output(ChatModelResponse,
                                                       method="json_schema",
                                                       strict=True,
                                                       include_raw=True)
        template = ChatPromptTemplate.from_messages([("system", _app_config.prompt),
                                                     MessagesPlaceholder("history"),
                                                     ("human", "{content}")])

        result = await (template | bound).ainvoke({"history": [],
                                                   "content": CORRECT_PHRASE,
                                                   "lang": "English"})

        assert not result["parsing_error"], result["parsing_error"]
        payload = provider_payload(result["raw"])
        assert DECLARED_KEYS <= set(payload), f"provider omitted {DECLARED_KEYS - set(payload)}: {payload}"

    async def test_real_chain_still_yields_a_dict(self, llm_service):
        """The contract ChatService depends on, exercised against the real provider."""
        async with llm_service.admission() as admitted:
            result = await llm_service.ainvoke(history=[], content=CORRECT_PHRASE, lang="English",
                                               admitted=admitted)

        assert isinstance(result, dict)
        assert result["resolved_mode"] in {"analyze", "follow_up", "reject"}
