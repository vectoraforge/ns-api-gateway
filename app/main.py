import logging
import sys
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from langchain.chat_models import init_chat_model

from app.routers import prompts_router, chats_router, root_router
from app.config import MainConfig
from app.errors import register_exception_handlers
from app.chats import Chats
from app.database import init_engine, engine
from app.services import AnalysisService, LLMExecutionGate, CircuitBreaker

logger = logging.getLogger(__name__)


def setup_logging(log_level: str):
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = MainConfig().app
    setup_logging(log_level=config.log_level)

    init_engine(config.db.url, config.pool_size)
    chats = Chats()

    llm = init_chat_model(
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    gate = LLMExecutionGate(
        max_concurrency=config.model.pool_size,
        max_queue=config.model.queue_size,
        retry_after_seconds=config.model.queue_retry_after_seconds,
    )
    circuit_breaker = CircuitBreaker(
        failure_threshold=config.model.circuit_breaker_failure_threshold,
        reset_seconds=config.model.circuit_breaker_reset_seconds,
    )

    app.state.config = config
    app.state.service = AnalysisService(
        prompt=config.prompt,
        examples=config.examples,
        llm=llm,
        gate=gate,
        circuit_breaker=circuit_breaker,
        timeout_seconds=config.model.timeout_seconds,
        retry_max_attempts=config.model.retry_max_attempts,
        retry_backoff_base_seconds=config.model.retry_backoff_base_seconds,
        retry_backoff_max_seconds=config.model.retry_backoff_max_seconds,
        chats=chats,
    )

    logger.info("Starting API Gateway")
    logger.info(f"Using LLM model: {config.model.name}")
    logger.info(f"Max LLM concurrency: {config.model.pool_size}")
    logger.info(f"Supported languages: {', '.join(config.examples.keys())}")
    yield
    await engine.dispose()
    logger.info("Shutting down API Gateway")


app = FastAPI(
    title="SpeakNative API Gateway",
    description="API Gateway for linguistic analysis of phrases",
    version=version("sn-api-gateway"),
    lifespan=lifespan
)

app.include_router(root_router)
app.include_router(prompts_router)
app.include_router(chats_router)
register_exception_handlers(app)
