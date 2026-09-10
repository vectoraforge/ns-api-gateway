import asyncio
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
    DatabaseConfig,
    EnvironmentConfig,
    GooglePlayConfig,
    JWTConfig,
    StoreEnvironment,
)
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.logs import setup_logging
from nativespeaker.api.services import LLMService

logger = structlog.get_logger()

#: Well inside every managed-Postgres and NAT idle timeout this service could sit behind, so a
#: connection is retired before the far end drops it rather than after.
_DB_POOL_RECYCLE_SECONDS = 1800

#: The cap on the one boot connection below. asyncpg's own default is 60 seconds and the chart
#: ships no `startupProbe`, so an unbounded connect to a blackholed host would let the liveness
#: probe kill the pod before boot named the reason it was failing.
_DB_CONNECT_TIMEOUT_SECONDS = 8.0

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
        # Parsed and discarded: `SignedDataVerifier` parses its root lazily, so a PEM or a
        # truncated value would surface only as a 401 on a genuine notification.
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


def google_push_pins(play: GooglePlayConfig) -> tuple[str, str] | None:
    """The audience and push identity the token is pinned to, or `None` when either is absent."""
    if not (play.push_audience and play.push_service_account_email):
        return None
    return play.push_audience, play.push_service_account_email


def build_google_push_verifier(play: GooglePlayConfig) -> JWTVerifier | None:
    """The Pub/Sub push-token verifier, or `None` when this deployment cannot build one."""
    pins = google_push_pins(play)
    if pins is None:
        return None
    audience, service_account = pins
    try:
        return JWTVerifier(jwks_url=GOOGLE_JWKS_URL,
                           audience=audience,
                           issuer=GOOGLE_ISSUER,
                           # The audience alone is a value the deployer chose, so the push identity is pinned too.
                           required_claims={"email": service_account,
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
        # Fatal, where the two builders above answer `None`: a pod without this verifier has
        # nothing to be Ready for. The URL is named because `PyJWKClientError` names none.
        raise RuntimeError(f"JWKS unusable at {jwt.jwks_url}: {failure}") from failure


def build_db_engine(db: DatabaseConfig) -> AsyncEngine:
    """The one engine. Named like its three sibling builders so its pool settings are assertable."""
    # `pool_pre_ping` and `pool_recycle` are not the library's defaults. A pod is long-lived and
    # this service is almost idle, so a pooled connection sits for hours -- exactly what a managed
    # Postgres idle timeout, a failover or a NAT expiry kills server-side. Without the ping, the
    # next request to draw that connection raises out of the CRUD layer as an opaque 500, and on a
    # chat route it does so after `QuotaService.charge` has already committed a spent credit. With
    # `max_overflow=0`, up to `pool_size` requests in a row can hit it, and nothing retries.
    # `hide_parameters`, because almost every write here binds a secret: the single-use challenge
    # handle, the DeviceCheck token, the user email, and the Play purchase token inside
    # `notification_uuid`. A `StatementError` renders its bound parameters in `__str__`, and any one
    # that escapes the CRUD layer reaches `generic_error_handler`, which logs the whole chain. The
    # SQL text is kept: it names columns, never values.
    return create_async_engine(db.url,
                               pool_size=db.pool_size,
                               max_overflow=0,
                               pool_pre_ping=True,
                               pool_recycle=_DB_POOL_RECYCLE_SECONDS,
                               hide_parameters=True)


async def _prove_database_reachable(engine: AsyncEngine, db: DatabaseConfig) -> None:
    """One connection, opened and dropped, so the pod is not Ready before anything reached Postgres."""
    # Fatal, like `build_jwt_verifier` and unlike the two store builders: a pod that cannot reach
    # Postgres has nothing to be Ready for, and `/health/ready` answers a static 200 that will never
    # say so. `create_async_engine` connects lazily, so without this a rollout carrying a wrong
    # DB_HOST or a rotated DB_PASSWORD passes both probes, completes its rolling update, and
    # terminates the last working pod. Boot-time only: a blip afterwards never reaches this line, so
    # a running pod is never restarted by it and the rollout simply halts on the previous ReplicaSet.
    try:
        async with asyncio.timeout(_DB_CONNECT_TIMEOUT_SECONDS):
            async with engine.connect():
                pass
    except Exception as failure:
        # Host and port, never the URL: `DatabaseConfig.url` renders the password. Measured: none of
        # the three real failures (refused, wrong password, unreachable) carries it in its own text.
        raise RuntimeError(f"database unreachable at {db.host}:{db.port}/{db.name}: "
                           f"{type(failure).__name__}: {failure}") from failure


def _play_credential():
    """ADC scoped for the Play Developer API, or `None` if the environment supplies none."""
    try:
        credential, _project = google.auth.default(scopes=[PLAY_SCOPE])
    except google.auth.exceptions.GoogleAuthError:
        # The whole family, not just an absent credential: `google.auth.default()` also raises
        # `RefreshError` and `TransportError` when the metadata server answers badly at pod start.
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
                                       "verification_temporarily_unavailable until this pod is restarted "
                                       "with the DeviceCheck key id, team id and private key available "
                                       "in this environment")
        devicecheck_client = httpx.AsyncClient(timeout=DEVICECHECK_HTTP_TIMEOUT_SECONDS)
        app.state.devicecheck_adapter = AppleDeviceCheck(key_id=config.devicecheck.key_id,
                                                         team_id=config.devicecheck.team_id,
                                                         private_key=devicecheck_key,
                                                         client=devicecheck_client)

        app_store_verifier = build_app_store_verifier(config.app_store)
        # The product map too, as the Play arm below tests it: a map serving nothing has no other signal.
        if app_store_verifier is None or not config.app_store.products:
            logger.warning("app_store_configuration_absent",
                           consequence="POST /webhooks/app-store refuses every notification and "
                                       "POST /auth/restore-subscription refuses every apple "
                                       "restore until this pod is restarted with the App Store "
                                       "bundle id, environment, product map, app id (production "
                                       "only) and root certificate available in this environment")
        # Set unconditionally, so the route set is the same in every environment.
        app.state.app_store_notifications = AppStoreNotifications(verifier=app_store_verifier,
                                                                  products=config.app_store.products)

        google_push_verifier = build_google_push_verifier(config.google_play)
        play_credential = _play_credential()
        if (google_push_pins(config.google_play) is None or play_credential is None
                or not config.google_play.package_name or not config.google_play.products):
            logger.warning("google_play_configuration_absent",
                           consequence="POST /webhooks/google-play/rtdn refuses every delivery and "
                                       "POST /auth/restore-subscription refuses every google_play "
                                       "restore until this pod is restarted with the Play package "
                                       "name, product map, push audience, push service account and "
                                       "Application Default Credentials available in this environment")
        elif google_push_verifier is None:
            # Told apart from the absence above, which this configuration is not: the values are here.
            logger.warning("google_push_verifier_warm_up_failed",
                           consequence="POST /webhooks/google-play/rtdn refuses every delivery until "
                                       "Google's key set is reachable again, which the next delivery "
                                       "retries without a restart")
        play_client = httpx.AsyncClient(timeout=PLAY_HTTP_TIMEOUT_SECONDS)
        # Set unconditionally, so the route set is the same in every environment.
        app.state.google_push_tokens = PubSubPushTokens(
            verifier=google_push_verifier,
            # A JWKS blip at boot is transient, so the verifier is rebuilt rather than cached as absent.
            build=lambda: build_google_push_verifier(config.google_play))
        app.state.play_subscriptions = PlayDeveloperSubscriptions(
            credential=play_credential,
            client=play_client,
            products=config.google_play.products)

        db_engine = build_db_engine(config.db)
        await _prove_database_reachable(db_engine, config.db)
        app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)

        app.state.jwt_verifier = build_jwt_verifier(config.jwt)

        app.state.llm_service = LLMService(model_config=config.model,
                                           api_key=config.openai.api_key,
                                           resilence_config=config.resilience,
                                           system_prompt=config.prompt)

        logger.info("started", model=config.model.name, concurrency=config.resilience.pool_size,
                    languages=list(config.examples.keys()))

        yield
    finally:
        # Guarded per step: `dispose()` and `aclose()` both raise on a handle in a bad state, and a
        # raise here would skip every step below it.
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

        # `firebase_admin` registers named apps process-globally and raises on a repeat, so a
        # second boot needs these gone.
        for firebase_app in firebase_apps.values():
            try:
                firebase_admin.delete_app(firebase_app)
            except Exception:
                logger.error("shutdown_step_failed", step="firebase_delete_app", exc_info=True)

        logger.info("shutdown")
