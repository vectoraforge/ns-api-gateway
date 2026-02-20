import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from langchain.chat_models import init_chat_model

from app.routers import prompts_router, root_router
from app.config import load_app_config, load_content_config, AppConfig
from app.errors import register_exception_handlers
from app.services import AnalysisService

logger = logging.getLogger(__name__)

MAX_LLM_CONCURRENCY = 8


def setup_logging(config: AppConfig):
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_app_config()
    content = load_content_config()
    setup_logging(config)

    llm = init_chat_model(
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    semaphore = asyncio.Semaphore(MAX_LLM_CONCURRENCY)

    app.state.config = config
    app.state.content = content
    app.state.service = AnalysisService(
        prompt=content.prompt,
        examples=content.examples,
        llm=llm,
        semaphore=semaphore,
    )

    logger.info("Starting API Gateway")
    logger.info(f"Using LLM model: {config.model.name}")
    logger.info(f"Max LLM concurrency: {MAX_LLM_CONCURRENCY}")
    logger.info(f"Supported languages: {', '.join(content.examples.keys())}")
    yield
    logger.info("Shutting down API Gateway")


app = FastAPI(
    title="SpeakNative API Gateway",
    description="API Gateway for linguistic analysis of phrases",
    version=version("sn-api-gateway"),
    lifespan=lifespan
)

app.include_router(root_router)
app.include_router(prompts_router)
register_exception_handlers(app)
