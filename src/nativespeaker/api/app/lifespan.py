from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.audit import AuditWriter
from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.auth.registry import REGISTRY, assert_route_enumeration
from nativespeaker.api.auth.telemetry import RejectionCounter
from nativespeaker.api.auth.verification import JWTVerifier
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

    # Setup logging
    setup_logging(log_level=config.log_level)

    # Validate the error registry and the route registry -- both fail closed before serving traffic.
    # The route registry goes onto app.state first and the assertion runs against *that* object, so
    # the table the barrier reads per request is provably the table boot checked.
    assert_registry_total()
    app.state.route_registry = REGISTRY
    assert_route_enumeration(app, app.state.route_registry)

    # The §1.2 / §8.2 bounded-cardinality rejection counter. Every route this phase registers is
    # off the audited attempt path, so this counter plus the structured security log is the whole
    # record of a barrier rejection there -- and §1.2 makes it the required alerting source for
    # cross-route attack volume and for a systemic verification break. Nothing exports it yet;
    # see 35-06-SUMMARY.md for the recorded gap.
    app.state.rejection_counter = RejectionCounter()

    # The §4.3 / §6.4 keyed-hashing seam: one keyring, read per request, never cached by a caller.
    # D-22's fail-closed half already happened -- a missing, empty, or unusable active key raises
    # out of EnvironmentConfig() above, before this line and long before the app serves. All that
    # is left here is the tolerated half: a gap below the active version is named in the log and
    # the process keeps going, because no request path recomputes a historical hash.
    app.state.hmac_keyring = HmacKeyring(config.hmac)
    app.state.hmac_keyring.warn_missing_older(logger)

    # The §4 audit writer. One instance, read per request, never cached by a caller -- it takes the
    # session factory as a parameter rather than reading app state itself, so the e2e rollback
    # fixture's per-test factory swap still governs every row it writes. Nothing calls it in
    # production this phase: all eight registered routes declare `operation = None`, and §8.2 puts
    # them off the audited attempt path permanently. Phases 37-45 supply the real call sites.
    app.state.audit_writer = AuditWriter(app.state.hmac_keyring)

    # Initialize database
    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
    app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)

    # Initialize token verifiers. D-16 removed the Apple receipt verifier with the subscription
    # layer, and the Firebase Admin app with the plan-claim sync: neither Google Application
    # Default Credentials nor the Apple signing certificates are read at boot any more. Phases 37+
    # reintroduce Firebase behind the §7.1 adapter seam, never as an ambient startup client.
    app.state.jwt_verifier = JWTVerifier(jwks_url=config.jwt.jwks_url,
                                         audience=config.jwt.project_id,
                                         issuer=config.jwt.issuer,
                                         leeway=config.jwt.leeway_seconds,
                                         cache_ttl_seconds=config.jwt.jwks_cache_ttl_seconds)

    # Initialize LLM service
    app.state.llm_service = LLMService(model_config=config.model,
                                       resilence_config=config.resilience,
                                       system_prompt=config.prompt)

    # Start the app
    logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size,
                languages=list(config.examples.keys()))
    yield

    # Shutdown
    await db_engine.dispose()

    logger.info("shutdown")
