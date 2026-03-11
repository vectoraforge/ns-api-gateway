import logging
import sys
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from langchain.chat_models import init_chat_model
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import JWTVerifier
from app.config import MainConfig
from app.errors import register_exception_handlers
from app.resilience import ResiliencePolicy
from app.routers import chats_router, examples_router, health_router, root_router
from app.schema import ErrorResponse
from app.services.chats import create_chain

logger = logging.getLogger(__name__)


def setup_logging(log_level: str):
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO),
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = MainConfig().app
    setup_logging(log_level=config.log_level)

    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)

    app.state.config = config
    app.state.session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    app.state.verifier = JWTVerifier(jwks_url=config.jwt.jwks_url,
                                     audience=config.jwt.audience,
                                     issuer=config.jwt.issuer,
                                     leeway=config.jwt.leeway_seconds,
                                     cache_ttl_seconds=config.jwt.jwks_cache_ttl_seconds)
    logger.info(f"Firebase project ID: {config.jwt.project_id}")
    app.state.policy = ResiliencePolicy(config.model.resilience)

    llm = init_chat_model(model=config.model.name,
                          temperature=config.model.temperature,
                          max_tokens=config.model.max_tokens)
    app.state.chain = create_chain(llm, config.prompt)

    logger.info("Starting API Gateway")
    logger.info(f"Using LLM model: {config.model.name}")
    logger.info(f"Max LLM concurrency: {config.model.resilience.pool_size}")
    logger.info(f"Supported languages: {', '.join(config.examples.keys())}")
    yield
    await db_engine.dispose()
    logger.info("Shutting down API Gateway")


app = FastAPI(title="SpeakNative API Gateway",
              description="API Gateway for linguistic analysis of phrases",
              version=version("sn-api-gateway"),
              lifespan=lifespan,
              responses={
                  400: {"model": ErrorResponse, "description": "Invalid request"},
                  401: {"model": ErrorResponse, "description": "Unauthorized"},
                  404: {"model": ErrorResponse, "description": "Not found"},
                  500: {"model": ErrorResponse, "description": "Internal error"},
                  503: {"model": ErrorResponse, "description": "Service unavailable"},
              })

app.include_router(root_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
register_exception_handlers(app)
