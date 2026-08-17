from contextlib import asynccontextmanager
from dataclasses import fields

import firebase_admin
import structlog
from fastapi import FastAPI
from firebase_admin import credentials
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.audit import (
    AuthAuditWriter,
    AuthResultCounter,
    InvalidExternalJwtAlerting,
    KeyedSubjectHasher,
)
from nativespeaker.api.auth.barrier import AuthBarrier, VerifiedIdentityContext
from nativespeaker.api.auth.callbacks import assert_callback_configuration
from nativespeaker.api.auth.integration import build_firebase_integrations
from nativespeaker.api.auth.ownership import assert_ownership_keys
from nativespeaker.api.auth.routes import (
    assert_route_categories,
    backend_credential_violations,
    registered_routes,
)
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.database import AccessTiersDB, AuthEventsDB, IdentityResolverDB
from nativespeaker.api.logs import setup_logging
from nativespeaker.api.models import User  # noqa: F401  (registers the mapped tables)
from nativespeaker.api.ratelimit import (
    ProviderCoalescer,
    RateLimitConfigError,
    RateLimiter,
    RateLimitMetrics,
    SecurityTelemetry,
    assert_create_user_gateway_limits,
    assert_provider_damping,
    assert_rate_limit_config,
)
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

    # A registered provider-callback route must be able to verify its store's own credential,
    # and carries no supplementary control instead: a store's route is not registered at all
    # while that store's integration is unconfigured.
    # [impl->req~sessions-named-verifier-per-callback-route~1]
    # [impl->req~sessions-no-supplementary-callback-controls~1]
    assert_callback_configuration(registered_routes(app), environment.raw_config or {})

    # The backend mints no backend access token and keeps no server-side session tier.
    # [impl->req~sessions-no-backend-tokens-or-session-tier~1]
    credential_violations = backend_credential_violations(
        registered_routes(app), [f.name for f in fields(VerifiedIdentityContext)])
    if credential_violations:
        raise RuntimeError("; ".join(sorted(credential_violations)))

    # Fail closed on a rate-limit configuration this specification cannot serve: a missing
    # named entry, a forbidden one, or a security-sensitive control configured fail-open.
    # [impl->req~ratelimit-config-must-include-at-least~1]
    # [impl->req~ratelimit-config-turnstile-siteverify-entry~1]
    assert_rate_limit_config(config.rate_limits, raw=(environment.raw_config or {}).get("rate_limits"))
    # Gateway rate limiting on the pre-auth `POST /auth/create-user` route is required on every
    # deployment: startup refuses a configuration that leaves it unthrottled.
    # [impl->req~sessions-create-user-gateway-limit-required~1]
    assert_create_user_gateway_limits(config.gateway_rate_limits)
    app.state.rate_limiter = RateLimiter(config.rate_limits)

    # Fail closed on adapter damping the configuration file does not declare: every outbound
    # provider call carries its configured timeouts, attempt cap and retry budget before traffic
    # reaches an adapter.
    # [impl->req~ratelimit-adapter-damping-limits-configured~1]
    if config.provider_damping is None:
        raise RateLimitConfigError("provider_damping is not configured")
    assert_provider_damping(config.provider_damping)
    app.state.provider_damping = config.provider_damping

    # The operational counters, the bounded aggregate rate-limit telemetry, and the coalescer
    # that keeps concurrent identical provider lookups down to one outbound call.
    # [impl->req~ratelimit-operational-counters~1]
    app.state.rate_limit_metrics = RateLimitMetrics()
    app.state.security_telemetry = SecurityTelemetry()
    app.state.provider_coalescer = ProviderCoalescer(config.provider_damping,
                                                     metrics=app.state.rate_limit_metrics)

    # Initialize database
    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
    session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                         expire_on_commit=False)
    app.state.session_factory = session_factory

    # The access tiers are product configuration in PostgreSQL: startup writes the configured
    # catalogue into `core.access_tiers`, and refuses to serve a catalogue whose registered
    # tiers are sized below the anonymous tier.
    # [impl->req~schema-access-tiers-product-configuration~1]
    # [impl->req~schema-access-tiers-sizing-invariant-enforced~1]
    if config.access_tiers:
        async with session_factory() as session:
            await AccessTiersDB(session).sync(config.access_tiers)
            await session.commit()

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
    # The required counter, and the operational alert on a sustained rise in
    # `invalid_external_jwt` rejections that is the systemic-break detection path.
    # [impl->req~sessions-invalid-external-jwt-metric-alert~1]
    # [impl->req~sessions-systemic-break-detection-path~1]
    app.state.invalid_jwt_alerting = InvalidExternalJwtAlerting(
        config.auth.invalid_external_jwt_alert)
    app.state.auth_result_counter = AuthResultCounter(app.state.invalid_jwt_alerting)
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
