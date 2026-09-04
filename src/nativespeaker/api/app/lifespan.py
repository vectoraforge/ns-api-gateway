from contextlib import asynccontextmanager
from pathlib import Path

import firebase_admin
import httpx
import structlog
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.app_store import AppStoreNotifications
from nativespeaker.api.auth.devicecheck import (
    DEVICECHECK_HTTP_TIMEOUT_SECONDS,
    AppleDeviceCheck,
    read_private_key,
)
from nativespeaker.api.auth.firebase import FirebaseAdminLookup, build_admin_apps
from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.config import AppStoreConfig, EnvironmentConfig, StoreEnvironment
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.logs import setup_logging
from nativespeaker.api.services import LLMService

logger = structlog.get_logger()

# Two arms and no case transform, so the two library members that skip verification stay unreachable.
_STORE_ENVIRONMENTS = {StoreEnvironment.sandbox: Environment.SANDBOX,
                       StoreEnvironment.production: Environment.PRODUCTION}


def build_app_store_verifier(store: AppStoreConfig) -> SignedDataVerifier | None:
    """The one verifier, or `None` when this deployment cannot build one."""
    root = Path(store.root_certificate_path) if store.root_certificate_path else None
    # Production needs the app id too: the library raises ValueError without it, and that would stop boot.
    if not (store.bundle_id and store.environment and root and root.is_file()) or (
            store.environment is StoreEnvironment.production and store.app_apple_id is None):
        return None
    return SignedDataVerifier(root_certificates=[root.read_bytes()],
                              # No network call on the admission path, so `verify` performs no I/O.
                              enable_online_checks=False,
                              environment=_STORE_ENVIRONMENTS[store.environment],
                              bundle_id=store.bundle_id,
                              app_apple_id=store.app_apple_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = EnvironmentConfig().app_config
    if config is None:
        raise RuntimeError("Configuration failed to load")
    app.state.config = config

    setup_logging(log_level=config.log_level)

    app.state.challenge_store = ChallengesDB()

    # One named Firebase app per configured issuer; an absent credential returns {} and boot proceeds.
    firebase_apps = build_admin_apps(config)
    app.state.firebase_adapter = FirebaseAdminLookup(firebase_apps)

    devicecheck_key = read_private_key(config.devicecheck.private_key_path)
    if not (config.devicecheck.key_id and config.devicecheck.team_id and devicecheck_key):
        logger.warning("devicecheck_credential_absent",
                       consequence="the anonymous grant claim fails closed as "
                                   "verification_temporarily_unavailable until the DeviceCheck key id, "
                                   "team id and private key are available in this environment")
    devicecheck_client = httpx.AsyncClient(timeout=DEVICECHECK_HTTP_TIMEOUT_SECONDS)
    app.state.devicecheck_adapter = AppleDeviceCheck(key_id=config.devicecheck.key_id,
                                                     team_id=config.devicecheck.team_id,
                                                     private_key=devicecheck_key,
                                                     client=devicecheck_client)

    app_store_verifier = build_app_store_verifier(config.app_store)
    if app_store_verifier is None:
        logger.warning("app_store_configuration_absent",
                       consequence="POST /webhooks/app-store fails closed as "
                                   "verification_temporarily_unavailable until the App Store bundle "
                                   "id, environment, app id and root certificate are available in "
                                   "this environment")
    # Set unconditionally, so the route set is the same in every environment.
    app.state.app_store_notifications = AppStoreNotifications(verifier=app_store_verifier)

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
    await devicecheck_client.aclose()

    # firebase_admin registers named apps process-globally and raises on a repeat, so a second boot needs these gone.
    for firebase_app in firebase_apps.values():
        firebase_admin.delete_app(firebase_app)

    logger.info("shutdown")
