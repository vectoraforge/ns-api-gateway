from contextlib import asynccontextmanager
from importlib.metadata import version

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

import firebase_admin
from firebase_admin import credentials

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.schema import ErrorResponse
from nativespeaker.api.auth import JWTVerifier
from nativespeaker.api.config import MainConfig
from nativespeaker.api.logs import RequestLoggingMiddleware, setup_logging
from nativespeaker.api.routers import chats_router, examples_router, health_router, root_router, users_router, webhooks_router
from nativespeaker.api.services import FirebaseService, LLMService, create_apple_verifier

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = MainConfig().app_config
    setup_logging(log_level=config.log_level, json_log_path=config.json_log_path)

    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0,
                                        connect_args=config.db.connect_args)

    app.state.config = config
    app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)
    app.state.verifier = JWTVerifier(jwks_url=config.jwt.jwks_url,
                                     audience=config.jwt.project_id,
                                     issuer=config.jwt.issuer,
                                     leeway=config.jwt.leeway_seconds,
                                     cache_ttl_seconds=config.jwt.jwks_cache_ttl_seconds)
    app.state.llm_service = LLMService(model_config=config.model,
                                       resilence_config=config.resilience,
                                       system_prompt=config.prompt)

    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
    app.state.firebase_service = FirebaseService()

    app.state.apple_verifier = create_apple_verifier(config.apple)

    logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size,
                languages=list(config.examples.keys()))
    yield
    firebase_admin.delete_app(firebase_admin.get_app())
    await db_engine.dispose()
    logger.info("shutdown")


app = FastAPI(title="NativeSpeaker API Gateway",
              description="API Gateway for linguistic analysis of phrases",
              version=version("ns-api-gateway"),
              lifespan=lifespan,
              responses={
                  400: {"model": ErrorResponse, "description": "Invalid request"},
                  401: {"model": ErrorResponse, "description": "Unauthorized"},
                  404: {"model": ErrorResponse, "description": "Not found"},
                  422: {"model": ErrorResponse, "description": "Validation error"},
                  429: {"model": ErrorResponse, "description": "Rate limited"},
                  500: {"model": ErrorResponse, "description": "Internal error"},
                  503: {"model": ErrorResponse, "description": "Service unavailable"},
              })

app.include_router(root_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
app.include_router(users_router)
app.include_router(webhooks_router)
register_exception_handlers(app)
app.add_middleware(RequestLoggingMiddleware)
