from contextlib import asynccontextmanager

import firebase_admin
import structlog
from fastapi import FastAPI
from firebase_admin import credentials
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.audit import AuthAuditWriter, AuthResultCounter, KeyedSubjectHasher
from nativespeaker.api.auth.barrier import AuthBarrier
from nativespeaker.api.auth.integration import build_firebase_integrations
from nativespeaker.api.auth.ownership import assert_ownership_keys
from nativespeaker.api.auth.routes import assert_route_categories
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.database import AuthEventsDB, IdentityResolverDB
from nativespeaker.api.logs import setup_logging
from nativespeaker.api.models import User  # noqa: F401  (registers the mapped tables)
from nativespeaker.api.ratelimit import RateLimiter, assert_rate_limit_config
from nativespeaker.api.services import FirebaseService, LLMService, create_apple_verifier

logger = structlog.get_logger()

# The one Firebase Admin app this process creates. It is named, never the default app, so no
# ambient or global client exists for an Admin call to fall back to.
# [impl->req~shared-single-firebase-integration~1]
FIREBASE_ADMIN_APP_NAME = "nativespeaker"


@asynccontextmanager
async def lifespan(app: FastAPI):
    environment = EnvironmentConfig()
    config = environment.app_config
    if config is None:
        raise RuntimeError("Configuration failed to load")
    app.state.config = config

    # Setup logging
    setup_logging(log_level=config.log_level)

    # Fail closed on route-category and ownership-key violations before serving traffic
    assert_route_categories(app)
    assert_ownership_keys(SQLModel.metadata)

    # Fail closed on a rate-limit configuration this specification cannot serve: a missing
    # named entry, a forbidden one, or a security-sensitive control configured fail-open.
    # [impl->req~ratelimit-config-must-include-at-least~1]
    # [impl->req~ratelimit-config-turnstile-siteverify-entry~1]
    assert_rate_limit_config(config.rate_limits, raw=(environment.raw_config or {}).get("rate_limits"))
    app.state.rate_limiter = RateLimiter(config.rate_limits)

    # Initialize database
    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
    session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                         expire_on_commit=False)
    app.state.session_factory = session_factory

    # Initialize token verifiers
    app.state.apple_verifier = create_apple_verifier(config.apple)

    # The single Firebase integration: one named Admin app, one JWKS-backed ID token verifier
    # over the cached Google signing keys, selected by matched issuer.
    # [impl->req~shared-single-firebase-integration~1]
    admin_app = firebase_admin.initialize_app(credentials.ApplicationDefault(),
                                              name=FIREBASE_ADMIN_APP_NAME)
    integrations = build_firebase_integrations(issuer=config.jwt.issuer,
                                               project_id=config.jwt.project_id,
                                               jwks_url=config.jwt.jwks_url,
                                               admin_client=admin_app,
                                               leeway=config.jwt.leeway_seconds,
                                               jwks_cache_ttl_seconds=config.jwt.jwks_cache_ttl_seconds)
    app.state.firebase_integrations = integrations

    # The shared, mandatory, default-on pre-handler barrier: the only place external JWT
    # acceptance and the four identity-resolution outcomes are evaluated.
    # [impl->req~shared-prehandler-barrier~1]
    app.state.auth_result_counter = AuthResultCounter()
    app.state.auth_barrier = AuthBarrier(
        integrations=integrations,
        resolver=IdentityResolverDB(session_factory),
        audit=AuthAuditWriter(sink=AuthEventsDB(),
                              counter=app.state.auth_result_counter,
                              session_factory=session_factory),
        subject_hasher=KeyedSubjectHasher(
            key=config.auth.subject_hash_key.get_secret_value().encode("utf-8"),
            key_version=config.auth.subject_hash_key_version))

    # Initialize LLM service
    app.state.llm_service = LLMService(model_config=config.model,
                                       resilence_config=config.resilience,
                                       system_prompt=config.prompt)

    # Initialize Firebase service, bound to the integration's Admin client
    app.state.firebase_service = FirebaseService(integrations=integrations,
                                                 issuer=config.jwt.issuer)

    # Start the app
    logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size,
                languages=list(config.examples.keys()))
    yield

    # Shutdown
    firebase_admin.delete_app(admin_app)
    await db_engine.dispose()

    logger.info("shutdown")
