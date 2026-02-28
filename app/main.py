import logging
import sys
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from langchain.chat_models import init_chat_model

from app.auth import UnsafeBase64Verifier
from app.chats import Chats
from app.config import MainConfig
from app.database import engine, init_engine
from app.errors import register_exception_handlers
from app.resilience import ResiliencePolicy
from app.routers import chats_router, health_router, prompts_router, root_router
from app.services import AnalysisService

logger = logging.getLogger(__name__)


def setup_logging(log_level: str):
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = MainConfig().app
    setup_logging(log_level=config.log_level)

    init_engine(config.db.url, config.db.pool_size)
    chats = Chats()

    llm = init_chat_model(
        model=config.model.name, temperature=config.model.temperature, max_tokens=config.model.max_tokens
    )
    policy = ResiliencePolicy(config.model.resilience)

    app.state.config = config
    app.state.verifier = UnsafeBase64Verifier()
    app.state.service = AnalysisService(
        prompt=config.prompt,
        examples=config.examples,
        llm=llm,
        policy=policy,
        history_max_human_messages=config.history_max_human_messages,
        history_max_assistant_messages=config.history_max_assistant_messages,
        message_max_chars=config.message_max_chars,
        chats=chats,
    )

    logger.info("Starting API Gateway")
    logger.info(f"Using LLM model: {config.model.name}")
    logger.info(f"Max LLM concurrency: {config.model.resilience.pool_size}")
    logger.info(f"Supported languages: {', '.join(config.examples.keys())}")
    yield
    await engine.dispose()
    logger.info("Shutting down API Gateway")


app = FastAPI(
    title="SpeakNative API Gateway",
    description="API Gateway for linguistic analysis of phrases",
    version=version("sn-api-gateway"),
    lifespan=lifespan,
)

app.include_router(root_router)
app.include_router(prompts_router)
app.include_router(chats_router)
app.include_router(health_router)
register_exception_handlers(app)
