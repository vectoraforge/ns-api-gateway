from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnableSerializable

from nativespeaker.api.config import ModelConfig, ResilienceConfig
from nativespeaker.api.resilience import Admitted, ResiliencePolicy
from nativespeaker.api.schemas.llm import ChatModelResponse


class LLMService:
    def __init__(self,
                 model_config: ModelConfig,
                 resilence_config: ResilienceConfig,
                 system_prompt: str):
        self.llm = init_chat_model(model=model_config.name,
                                   temperature=model_config.temperature,
                                   max_tokens=model_config.max_tokens)
        self.policy = ResiliencePolicy(resilence_config)
        self.chain = self.create_chain(prompt=system_prompt)

    def create_chain(self, prompt: str) -> RunnableSerializable[dict, dict[str, Any]]:
        prompt_template = ChatPromptTemplate.from_messages([("system", prompt),
                                                            MessagesPlaceholder("history"),
                                                            ("human", "{content}")])
        # The schema rides on the call, so the provider cannot omit a declared key.
        constrained = self.llm.with_structured_output(ChatModelResponse, method="json_schema", strict=True)
        return prompt_template | constrained | RunnableLambda(lambda answer: answer.model_dump())

    def admission(self):
        """Admit one request through the resilience policy."""
        return self.policy.admission()

    async def ainvoke(self, history: list[HumanMessage | AIMessage], content: str, lang: str,
                      admitted: Admitted) -> dict:
        """Invoke the chain under the resilience policy."""
        return await self.policy.ainvoke(
            lambda: self.chain.ainvoke({"history": history, "content": content, "lang": lang}), admitted)
