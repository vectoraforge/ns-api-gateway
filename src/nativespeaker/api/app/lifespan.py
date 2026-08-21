from contextlib import asynccontextmanager

import firebase_admin
import structlog
from fastapi import FastAPI
from firebase_admin import credentials
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth import JWTVerifier
from nativespeaker.api.auth.registry import assert_route_enumeration
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.logs import setup_logging
from nativespeaker.api.services import FirebaseService, LLMService, create_apple_verifier

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = EnvironmentConfig().app_config
    if config is None:
        raise RuntimeError("Configuration failed to load")
    app.state.config = config

    # Setup logging
    setup_logging(log_level=config.log_level)

    # Validate the route registry against the live router -- fails closed before serving traffic
    assert_route_enumeration(app)

    # Initialize database
    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
    app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)

    # Initialize token verifiers
    app.state.apple_verifier = create_apple_verifier(config.apple)
    app.state.jwt_verifier = JWTVerifier(jwks_url=config.jwt.jwks_url,
                                         audience=config.jwt.project_id,
                                         issuer=config.jwt.issuer,
                                         leeway=config.jwt.leeway_seconds,
                                         cache_ttl_seconds=config.jwt.jwks_cache_ttl_seconds)

    # Initialize LLM service
    app.state.llm_service = LLMService(model_config=config.model,
                                       resilence_config=config.resilience,
                                       system_prompt=config.prompt)

    # Initialize Firebase service
    firebase_admin.initialize_app(credentials.ApplicationDefault())
    app.state.firebase_service = FirebaseService()

    # Start the app
    logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size,
                languages=list(config.examples.keys()))
    yield

    # Shutdown
    firebase_admin.delete_app(firebase_admin.get_app())
    await db_engine.dispose()

    logger.info("shutdown")
