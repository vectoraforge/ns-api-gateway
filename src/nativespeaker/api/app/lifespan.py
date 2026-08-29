from contextlib import asynccontextmanager

import firebase_admin
import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.auth.firebase import FirebaseAdminLookup, build_admin_apps
from nativespeaker.api.auth.hmac_keyring import HmacKeyring
from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.errors import assert_registry_total
from nativespeaker.api.logs import setup_logging
from nativespeaker.api.services import LLMService

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = EnvironmentConfig().app_config
    if config is None:
        raise RuntimeError("Configuration failed to load")
    app.state.config = config

    setup_logging(log_level=config.log_level)

    # The error registry fails closed here, before any traffic is served.
    assert_registry_total()

    # One keyring for the process; a missing active key already raised out of EnvironmentConfig().
    app.state.hmac_keyring = HmacKeyring(config.hmac)
    app.state.hmac_keyring.warn_missing_older(logger)

    # The challenge store shares that keyring rather than deriving a key of its own.
    app.state.challenge_store = ChallengesDB(app.state.hmac_keyring)

    # One named Firebase app per configured issuer; an absent credential returns {} and boot proceeds.
    firebase_apps = build_admin_apps(config)
    app.state.firebase_adapter = FirebaseAdminLookup(firebase_apps)

    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
    app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)

    app.state.jwt_verifier = JWTVerifier(jwks_url=config.jwt.jwks_url,
                                         audience=config.jwt.project_id,
                                         issuer=config.jwt.issuer,
                                         leeway=config.jwt.leeway_seconds,
                                         cache_ttl_seconds=config.jwt.jwks_cache_ttl_seconds)

    app.state.llm_service = LLMService(model_config=config.model,
                                       resilence_config=config.resilience,
                                       system_prompt=config.prompt)

    logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size,
                languages=list(config.examples.keys()))
    yield

    await db_engine.dispose()

    # firebase_admin registers named apps process-globally and raises on a repeat, so a second boot needs these gone.
    for firebase_app in firebase_apps.values():
        firebase_admin.delete_app(firebase_app)

    logger.info("shutdown")
