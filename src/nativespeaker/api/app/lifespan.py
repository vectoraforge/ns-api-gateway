from contextlib import asynccontextmanager
from pathlib import Path

import firebase_admin
import google.auth
import google.auth.exceptions
import httpx
import structlog
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
from cryptography import x509
from fastapi import FastAPI
from jwt.exceptions import PyJWTError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.app_store import AppStoreNotifications
from nativespeaker.api.auth.devicecheck import (
    DEVICECHECK_HTTP_TIMEOUT_SECONDS,
    AppleDeviceCheck,
    read_private_key,
)
from nativespeaker.api.auth.firebase import FirebaseAdminLookup, build_admin_apps
from nativespeaker.api.auth.google_play import (
    GOOGLE_ISSUER,
    GOOGLE_JWKS_URL,
    PLAY_HTTP_TIMEOUT_SECONDS,
    PLAY_SCOPE,
    PlayDeveloperSubscriptions,
    PubSubPushTokens,
)
from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.config import (
    AppStoreConfig,
    EnvironmentConfig,
    GooglePlayConfig,
    JWTConfig,
    StoreEnvironment,
)
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
    try:
        root_bytes = root.read_bytes()
        # Parsed here because `SignedDataVerifier` parses its root lazily: a PEM mounted where the
        # DER form belongs, or a truncated ConfigMap value, would otherwise build a verifier that
        # answers 401 to every genuine Apple notification and reads in the log as a forgery. The
        # read is inside the guard too -- a present-but-unreadable projected secret raises
        # `PermissionError`, which is the boot this function exists to prevent.
        x509.load_der_x509_certificate(root_bytes)
    except (OSError, ValueError):
        # An unreadable or non-DER root is an unconfigured deployment, not a forged notification.
        return None
    return SignedDataVerifier(root_certificates=[root_bytes],
                              # No network call on the admission path, so `verify` performs no I/O.
                              enable_online_checks=False,
                              environment=_STORE_ENVIRONMENTS[store.environment],
                              bundle_id=store.bundle_id,
                              app_apple_id=store.app_apple_id)


def build_google_push_verifier(play: GooglePlayConfig) -> JWTVerifier | None:
    """The Pub/Sub push-token verifier, or `None` when this deployment cannot build one."""
    if not (play.push_audience and play.push_service_account_email):
        return None
    try:
        return JWTVerifier(jwks_url=GOOGLE_JWKS_URL,
                           audience=play.push_audience,
                           issuer=GOOGLE_ISSUER,
                           # The audience alone is a value the deployer chose, so the push identity is pinned too.
                           required_claims={"email": play.push_service_account_email,
                                            "email_verified": True})
    except PyJWTError:
        # The warm-up fetch raises on an unreachable JWKS, and one route's 503 beats a dead pod.
        return None


def build_jwt_verifier(jwt: JWTConfig) -> JWTVerifier:
    """The identity-barrier verifier. Unlike the two builders above, this one has no degraded form."""
    try:
        return JWTVerifier(jwks_url=jwt.jwks_url,
                           audience=jwt.project_id,
                           issuer=jwt.issuer,
                           leeway=jwt.leeway_seconds,
                           cache_ttl_seconds=jwt.jwks_cache_ttl_seconds)
    except PyJWTError as failure:
        # Deliberately fatal, where `build_google_push_verifier` answers `None`: every route past
        # the identity barrier needs this verifier, so a pod without it has nothing to be Ready for.
        # Re-raised naming the endpoint, because a crashlooping pod's first log line is all an
        # operator gets and `PyJWKClientError`'s own message names no URL.
        raise RuntimeError(f"JWKS unusable at {jwt.jwks_url}: {failure}") from failure


def _play_credential():
    """ADC scoped for the Play Developer API, or `None` if the environment supplies none."""
    try:
        credential, _project = google.auth.default(scopes=[PLAY_SCOPE])
    except google.auth.exceptions.GoogleAuthError:
        # The whole family, not just an absent credential: `google.auth.default()` also raises
        # `RefreshError` and `TransportError` when the GCE metadata server answers badly, which is
        # a routine transient at pod start. Every ADC failure is the same outcome here -- one route
        # answers 503 and the pod still serves -- and it is the policy the push verifier above and
        # `firebase._application_default_credential` already carry.
        return None
    return credential


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = EnvironmentConfig().app_config
    if config is None:
        raise RuntimeError("Configuration failed to load")
    app.state.config = config

    setup_logging(log_level=config.log_level)

    app.state.challenge_store = ChallengesDB()

    # Nothing built yet: the `finally` below reaches every one of these on a startup that
    # failed part-way, where the later names do not exist at all.
    db_engine: AsyncEngine | None = None
    devicecheck_client: httpx.AsyncClient | None = None
    play_client: httpx.AsyncClient | None = None
    firebase_apps: dict[str, firebase_admin.App] = {}

    try:
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
        app.state.app_store_notifications = AppStoreNotifications(verifier=app_store_verifier,
                                                                  products=config.app_store.products)

        google_push_verifier = build_google_push_verifier(config.google_play)
        play_credential = _play_credential()
        if (google_push_verifier is None or play_credential is None
                or not config.google_play.package_name or not config.google_play.products):
            logger.warning("google_play_configuration_absent",
                           consequence="POST /webhooks/google-play/rtdn refuses every delivery "
                                       "until the Play package name, product map, push audience, "
                                       "push service account and Application Default Credentials "
                                       "are available in this environment")
        play_client = httpx.AsyncClient(timeout=PLAY_HTTP_TIMEOUT_SECONDS)
        # Set unconditionally, so the route set is the same in every environment.
        app.state.google_push_tokens = PubSubPushTokens(verifier=google_push_verifier)
        app.state.play_subscriptions = PlayDeveloperSubscriptions(
            credential=play_credential,
            client=play_client,
            products=config.google_play.products)

        db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
        app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)

        app.state.jwt_verifier = build_jwt_verifier(config.jwt)

        app.state.llm_service = LLMService(model_config=config.model,
                                           resilence_config=config.resilience,
                                           system_prompt=config.prompt)

        logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size,
                    languages=list(config.examples.keys()))

        yield
    finally:
        # Every step is guarded on its own, because a step that raises must not skip the ones after
        # it: `dispose()` on a pool in a bad state and `aclose()` on a client mid-flight both raise,
        # and the step they would strand is the one whose failure outlives the process.
        if db_engine is not None:
            try:
                await db_engine.dispose()
            except Exception:
                logger.error("shutdown_step_failed", step="db_engine_dispose", exc_info=True)
        for client in (devicecheck_client, play_client):
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    logger.error("shutdown_step_failed", step="http_client_close", exc_info=True)

        # firebase_admin registers named apps process-globally and raises on a repeat, so a
        # second boot needs these gone -- a failed startup that kept them poisons every later one.
        # Guarded per app as well: one app that refuses to go must not strand the rest.
        for firebase_app in firebase_apps.values():
            try:
                firebase_admin.delete_app(firebase_app)
            except Exception:
                logger.error("shutdown_step_failed", step="firebase_delete_app", exc_info=True)

        logger.info("shutdown")
