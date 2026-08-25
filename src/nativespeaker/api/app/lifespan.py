from contextlib import asynccontextmanager

import firebase_admin
import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.firebase import FirebaseAdminLookup, build_admin_apps
from nativespeaker.api.auth.keys import HmacKeyring
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

    # Validate the error registry -- it fails closed before serving traffic.
    #
    # The route-enumeration assertion that used to stand beside this is gone with the route
    # registry it checked (37.1 D-06). It existed to catch a route drifting from a parallel table
    # of auth declarations; there is no parallel table now, because each router declares its own
    # auth dependency and that declaration IS what serves traffic. `tests/unit/test_app_wiring.py`
    # asserts the resulting property over the live router directly.
    assert_registry_total()

    # The §4.3 / §6.4 keyed-hashing seam: one keyring, read per request, never cached by a caller.
    # D-22's fail-closed half already happened -- a missing, empty, or unusable active key raises
    # out of EnvironmentConfig() above, before this line and long before the app serves. All that
    # is left here is the tolerated half: a gap below the active version is named in the log and
    # the process keeps going, because no request path recomputes a historical hash.
    app.state.hmac_keyring = HmacKeyring(config.hmac)
    app.state.hmac_keyring.warn_missing_older(logger)

    # The §6 challenge store. It shares the keyring above rather than deriving anything of its own:
    # `preauth_subject_hash` is derived through that one keyed family under one key (D-21), and the
    # store calls it with no version because `core.auth_challenges` records none. It takes its
    # session as a method parameter, so the e2e rollback fixture's per-test factory swap governs
    # everything it writes. Nothing calls it in production this phase: the four challenge-bearing
    # operations are phases 37, 40, 41 and 42.
    app.state.challenge_store = ChallengeStore(app.state.hmac_keyring)

    # The §7.1 provider seam, built once at boot and read per request. `build_admin_apps` returns
    # one named app per configured issuer; an absent credential returns `{}`, the adapter is still
    # constructed, and boot proceeds -- 37-03 split absent from malformed deliberately, and a
    # malformed credential already failed at configuration load above, so the only state reachable
    # here is "no credential", under which a real completion fails closed at the adapter's own
    # selection arm as `verification_temporarily_unavailable` rather than at startup.
    #
    # No `[DEFAULT]` app is created and none is expressible: selection is an exact dict lookup on
    # the request-verified issuer, and every outbound call passes its app explicitly.
    firebase_apps = build_admin_apps(config)
    app.state.firebase_adapter = FirebaseAdminLookup(firebase_apps)

    # Initialize database
    db_engine = create_async_engine(config.db.url, pool_size=config.db.pool_size, max_overflow=0)
    app.state.session_factory = async_sessionmaker(db_engine, class_=SQLModelAsyncSession,
                                                       expire_on_commit=False)

    # Initialize token verifiers. D-16 removed the Apple receipt verifier with the subscription
    # layer, and the Firebase Admin app with the plan-claim sync.
    #
    # **Amended by Phase 37**, which reverses half of what this note used to say: a Firebase client
    # *is* read at boot again, in the `app.state.firebase_adapter` block above. What has not
    # changed is the part that mattered -- it is built behind the §7.1 adapter seam, as a named
    # per-issuer app with an explicit `projectId`, and never as an ambient `[DEFAULT]` app that a
    # call site could reach by forgetting `app=`. The credential itself may now come from
    # Application Default Credentials as well as from an explicit key: this project's org policy
    # sets `iam.disableServiceAccountKeyCreation`, so no key can be minted, and ADC is the only
    # route to a real Admin call. That is a change of credential *source*, not of the wire
    # contract D-08 is about. The Apple signing certificates are still not read at boot.
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

    # Give back every named Firebase app this lifespan created. `firebase_admin` keeps its apps in
    # a **process-global** registry that no lifespan owns and nothing else clears, and
    # `initialize_app` raises `ValueError: ... already exists` on a repeated name -- so a second
    # boot in one process dies at startup unless the first one cleaned up. One process, several
    # boots is not hypothetical: the e2e suite starts this lifespan once per test module.
    #
    # It stayed invisible while no credential was configured, because `build_admin_apps` then
    # returned `{}` without registering anything. The moment a real credential existed -- ADC, in
    # this project's case -- every e2e module after the first errored in fixture setup. Symmetry is
    # the fix: whoever creates a globally-registered handle destroys it.
    for firebase_app in firebase_apps.values():
        firebase_admin.delete_app(firebase_app)

    logger.info("shutdown")
