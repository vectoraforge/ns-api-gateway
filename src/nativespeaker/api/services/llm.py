from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel

from nativespeaker.api.config import ModelConfig, ResilienceConfig
from nativespeaker.api.resilience import ResiliencePolicy


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

    def create_chain(self, prompt: str) -> RunnableSerializable[dict, dict[str, Any] | BaseModel]:
        prompt_template = ChatPromptTemplate.from_messages([("system", prompt),
                                                            MessagesPlaceholder("history"),
                                                            ("human", "{content}")])
        return prompt_template | self.llm | JsonOutputParser()

    async def ainvoke(self, history: list[HumanMessage | AIMessage], content: str, lang: str) -> dict:
        return await self.policy.ainvoke(
            lambda: self.chain.ainvoke({"history": history, "content": content, "lang": lang})
        )
