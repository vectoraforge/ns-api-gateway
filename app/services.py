import asyncio
import logging

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.schema import AnalyzeResponse, ExamplesResponse
from app.exceptions import UnsupportedLanguageError, AnalysisError

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(
        self,
        prompt: str,
        examples: dict[str, list[str]],
        llm: ChatOpenAI,
        semaphore: asyncio.Semaphore,
    ):
        self.prompt = prompt
        self.examples = examples
        self.llm = llm
        self.semaphore = semaphore

    @property
    def supported_languages(self) -> list[str]:
        return list(self.examples.keys())

    async def analyze(self, phrase: str, lang: str) -> AnalyzeResponse:
        if lang not in self.examples:
            raise UnsupportedLanguageError(lang=lang, supported=self.supported_languages)

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.prompt),
            ("human", "{phrase}")
        ])
        chain = prompt_template | self.llm | JsonOutputParser()

        logger.info(f"Analyzing phrase in language '{lang}': {phrase}")

        try:
            async with self.semaphore:
                response = await chain.ainvoke({"lang": lang, "phrase": phrase})
        except Exception as e:
            logger.error(f"Error during phrase analysis: {e}", exc_info=True)
            raise AnalysisError(f"Error analyzing phrase: {str(e)}")

        response['phrase'] = phrase
        response['lang'] = lang

        logger.debug(f"LLM response: {response}")
        return AnalyzeResponse.model_validate(response)

    def get_examples(self, lang: str) -> ExamplesResponse:
        examples = self.examples.get(lang, [])
        if not examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)

        logger.info(f"Returning {len(examples)} examples for language '{lang}'")
        return ExamplesResponse(lang=lang, examples=examples)
