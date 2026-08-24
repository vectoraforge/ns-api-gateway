import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from unit.conftest import FakeFirebaseAdapter, make_test_verifier

from nativespeaker.api.app.main import app
from nativespeaker.api.auth.firebase import _application_default_credential
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.models import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    Chat,
    ChatRole,
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    Message,
    User,
    UserMonthlyUsage,
)

# The `registered` tier, seeded as reference data by
# `migrations/20260818_01_initial-release.sql:280-283` at 50 monthly credits. Not a randomised
# `tests/schema/helpers.py::insert_tier` id: that helper lives in the asyncpg-based `tests/schema/`
# package and is not importable here. 50 is comfortably above any single e2e module's consumption.
REGISTERED_TIER_ID = "registered"


@pytest.fixture(scope="session")
def _app_config():
    """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
    return EnvironmentConfig().app_config


@pytest.fixture(scope="session")
def firebase_token(_app_config):
    """Obtain a real Firebase ID token via REST API for the dedicated test user."""
    api_key = _app_config.jwt.api_key
    assert api_key, "JWT_API_KEY env var required for e2e tests"
    email = os.environ["FIREBASE_TEST_EMAIL"]
    password = os.environ["FIREBASE_TEST_PASSWORD"]
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={api_key}",
        json={"email": email,
              "password": password,
              "returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["idToken"]
    # Store the test user's UID (from Firebase 'localId') for seeding assertions
    os.environ.setdefault("FIREBASE_TEST_USER_ID", data["localId"])
    return token


def _admin_credential_configured(app_config) -> bool:
    """Whether `build_admin_apps` would find a credential -- asked the way it asks.

    Both source probes below are the **same two calls** `auth/firebase.py::build_admin_apps` makes,
    in the same order, rather than a re-reading of the environment: a local
    `os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"]` test would have gone on reporting "absent" on a
    machine whose credential arrives through ADC, and skipped the one case in this package that
    can only run when a credential is present. A predicate that can disagree with the thing it
    predicts is worse than no predicate.
    """
    if app_config.firebase.credential_dict() is not None:
        return True
    return _application_default_credential() is not None


# Names both routes, because either one satisfies the requirement and a message naming only the
# first sends a reader to provision a key that this project's org policy
# (`iam.disableServiceAccountKeyCreation`) forbids minting at all.
_NO_ADMIN_CREDENTIAL = (
    "no Firebase Admin credential: set FIREBASE_SERVICE_ACCOUNT_JSON (a service-account key) or "
    "GOOGLE_APPLICATION_CREDENTIALS (Application Default Credentials) in .env"
)


@pytest.fixture(scope="session")
def anonymous_firebase_credential(_app_config):
    """A **genuinely anonymous** Firebase user, minted for real. Returns `(id_token, local_id)`.

    `accounts:signUp` with `returnSecureToken` and **no** `email` and **no** `password` is the one
    credential shape that can be minted reproducibly from a test and still produce empty
    providerData from the real Admin SDK. Google's Identity Platform reference says of the `email`
    field: "An anonymous user will be created if not provided."

    It mirrors the `firebase_token` fixture's REST idiom above deliberately -- same host, same v1
    `identitytoolkit.googleapis.com` form (not the legacy v3 `relyingparty/signupNewUser`), same
    key -- because the two fixtures are the same operation on the same project and a second idiom
    would be a second thing to keep true.

    **Why this exists at all.** `firebase_token` signs in with `accounts:signInWithPassword`, so
    its providerData is `[{providerId: "password"}]` -- a single unrecognized entry that §02 step
    9's closed classifier rejects. A completion test written against it "passes" while testing the
    rejection arm (Pitfall 8). This fixture is D-09's answer for the one flow that can be minted
    for real.

    **Each call creates a permanent user in the shared project, and nothing deletes it** (T-37-50,
    accepted). SHARED-INVARIANTS deletes purge jobs and an `auth.delete_user` teardown would itself
    be an Admin call; a handful of empty anonymous users in a test project is the accepted cost.

    Skips -- never fails -- when no Admin credential is configured, so a contributor without one
    still gets a green `-m e2e` run and a skip reason that names what to set.
    """
    if not _admin_credential_configured(_app_config):
        pytest.skip(_NO_ADMIN_CREDENTIAL)
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={_app_config.jwt.api_key}",
        json={"returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    # RESEARCH A1: `returnSecureToken` is absent from the Identity Platform field list but present
    # in the Firebase Auth REST reference. If it were ignored the response would simply lack
    # `idToken`, and this subscript is what makes that fail loudly on the first run rather than
    # degrade into a case that silently stopped proving anything.
    return data["idToken"], data["localId"]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan():
    """Start app lifespan (config, DB engine, verifier, LLM service)."""
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def async_client(_app_lifespan, firebase_token):
    """Async HTTP client wired to the real app with Firebase auth."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {firebase_token}"
        yield client


@pytest.fixture(scope="module")
def test_user_id(firebase_token):
    """The Firebase test user's UID -- matches the 'sub' claim in the token.

    Depends on `firebase_token` because that fixture is what sets `FIREBASE_TEST_USER_ID`; without
    the edge this only works when something else happened to request the token first.
    """
    _ = firebase_token
    return os.environ["FIREBASE_TEST_USER_ID"]


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _db_transaction(_app_lifespan):
    """Wrap each test in a transaction that rolls back on completion."""
    original_factory = _app_lifespan.state.session_factory

    # async_sessionmaker stores bind in its kw dict
    engine = original_factory.kw["bind"]

    async with engine.connect() as connection:
        transaction = await connection.begin()

        test_factory = async_sessionmaker(
            bind=connection,
            class_=SQLModelAsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        _app_lifespan.state.session_factory = test_factory
        try:
            yield test_factory
        finally:
            _app_lifespan.state.session_factory = original_factory
            await transaction.rollback()


@pytest.fixture
def stub_verifier(_app_lifespan):
    """Swap `app.state.jwt_verifier` for the ephemeral-RSA verifier, and restore it afterwards.

    This is what makes four distinct subjects testable without four Firebase accounts: the barrier
    reads the verifier from the application per request, so replacing it here changes which tokens
    the *real* barrier accepts without touching the barrier at all.

    The verifier comes from `tests/unit/conftest.py` rather than being rebuilt here --
    `pythonpath = ["."]` makes both test packages importable, and duplicating the keypair machinery
    would let the two copies drift. `_FixedKeyVerifier` differs from `JWTVerifier` in exactly one
    respect, where the signing key comes from; the algorithm pin, the `require` list and the
    non-empty-`sub` rule are the production ones, imported rather than reimplemented.

    The real `firebase_token` fixture is untouched and stays for the modules that want a genuine
    credential.
    """
    original = _app_lifespan.state.jwt_verifier
    _app_lifespan.state.jwt_verifier = make_test_verifier()
    try:
        yield _app_lifespan.state.jwt_verifier
    finally:
        _app_lifespan.state.jwt_verifier = original


@pytest.fixture
def scripted_firebase_adapter(_app_lifespan):
    """Swap `app.state.firebase_adapter` for a scripted one, and restore it afterwards.

    The same shape as `stub_verifier` above, and it works for the same structural reason: the
    handler reads the adapter off the application per request rather than holding one, so replacing
    it here changes what the *real* route sees without touching the route at all.

    The fake itself is `tests/unit/conftest.py`'s, imported rather than redefined -- the same
    rule `stub_verifier` above follows, and for the same reason: two copies drift. Only the
    app-state swap is this package's business.

    Defaults to `ok` with empty providerData -- the anonymous account §02 step 9's classifier
    answers `anonymous` for -- so a case that does not care about the provider shape need not say
    so. `tests/e2e/test_create_user.py` documents why a substituted adapter is the right instrument
    here: the package's real Firebase credential signs in with email/password, whose providerData
    is `[{providerId: "password"}]` and which the closed classifier rejects by design.
    """
    original = _app_lifespan.state.firebase_adapter
    adapter = FakeFirebaseAdapter()
    _app_lifespan.state.firebase_adapter = adapter
    try:
        yield adapter
    finally:
        _app_lifespan.state.firebase_adapter = original


@pytest_asyncio.fixture(loop_scope="module")
async def linked_firebase_identity(_db_transaction, _app_config, test_user_id):
    """Seed the *real* Firebase credential's pair, so `async_client` is admitted by the barrier.

    `GET /` and `GET /examples` are authenticated routes (§8.1). Before plan 06 they were reachable
    with any well-formed credential, because the barrier stopped at the wire contract; now the
    barrier resolves identity, and the e2e Firebase subject needs a `core.external_identities` row
    like any other caller. Seeded inside the per-test transaction, so it rolls back.
    """
    return await seed_identity(_db_transaction,
                               issuer=_app_config.jwt.issuer,
                               subject=test_user_id)


async def seed_identity(factory, *,
                        issuer: str,
                        subject: str,
                        identity_state: IdentityState = IdentityState.active,
                        user_active: bool = True,
                        provider: IdentityProvider = IdentityProvider.google):
    """Insert a `core.users` row and its matching `core.external_identities` row; return both.

    The one helper that makes the §1.3 admission matrix testable: each of the four outcomes is a
    different `(identity_state, user_active)` pair, or the absence of a call to this function.

    `provider_uid` is derived rather than passed, because the table's CHECK ties the two together:
    NULL exactly for `anonymous`, non-empty otherwise. Deriving it from the subject also keeps the
    partial `ix_external_identities_provider_account` index satisfied across seeds in one test.

    Test seeding only, and deliberately not a provisioning path -- no route reaches it, and `src/`
    still contains no code that writes either table. `core.users` rows originate from
    `POST /auth/create-user` in Phase 37.
    """
    provider_uid = None if provider is IdentityProvider.anonymous else f"{provider}-uid-{subject}"
    async with factory() as session:
        user = User(active=user_active)
        session.add(user)
        await session.flush()
        identity = ExternalIdentity(user_id=user.id,
                                    issuer=issuer,
                                    subject=subject,
                                    provider=provider,
                                    provider_uid=provider_uid,
                                    identity_state=identity_state)
        session.add(identity)
        await session.commit()
    return user, identity


@pytest_asyncio.fixture(loop_scope="module")
async def quota_grant(_db_transaction, linked_firebase_identity):
    """One effective grant plus its usage row for the seeded Firebase caller. Returns both rows.

    Every case that drives a quota-checked route as an *admitted* caller needs this: without a
    grant, `require_quota` answers 429 before the handler is entered, and the case's real subject
    -- the chat behaviour, the language check, the ownership filter -- is never reached.

    Seeded through `_db_transaction`, inside the per-test transaction, so it rolls back like every
    other row this package writes.
    """
    user, _ = linked_firebase_identity
    return await seed_grant(_db_transaction, user_id=user.id)


@pytest_asyncio.fixture(loop_scope="module")
async def own_chat(_db_transaction, linked_firebase_identity) -> UUID:
    """A chat owned by the seeded Firebase caller, written directly rather than through the API.

    `POST /chats` is itself quota-checked, so a case whose subject is "a caller with NO grant is
    refused" cannot create its chat through the API -- it would need the grant it is asserting the
    absence of. Seeding the row is what breaks that circle.

    It exists because the charge moved off the decorator (REBIND-06). While quota was a decorator
    dependency, `POST /chats/{anything}` answered 429 before the handler looked the chat up, so the
    refusal cases could name a chat id that had never existed. The handler now runs first, so a
    made-up id answers 404 -- a true answer, but not the one those cases are about. Pointing them
    at a real chat keeps their subject the gate rather than the ownership filter.
    """
    user, _ = linked_firebase_identity
    chat_id = uuid4()
    async with _db_transaction() as session:
        chat = Chat(id=chat_id, user_id=user.id, title="seeded for a quota refusal case")
        chat.messages.append(Message(chat_id=chat_id, role=ChatRole.human,
                                     content={"mode": "analyze", "phrase": "seeded"}))
        chat.messages.append(Message(chat_id=chat_id, role=ChatRole.ai,
                                     content={"resolved_mode": "analyze", "response": "seeded",
                                              "issues": [], "suggestions": []}))
        session.add(chat)
        await session.commit()
    return chat_id


async def seed_grant(factory, *,
                     user_id: UUID,
                     tier_id: str = REGISTERED_TIER_ID,
                     source: AccessGrantSource = AccessGrantSource.manual,
                     status: AccessGrantStatus = AccessGrantStatus.active,
                     monthly_period: str | None = None,
                     monthly_used: int = 0,
                     starts_at: datetime | None = None,
                     ends_at: datetime | None = None,
                     with_usage: bool = True):
    """Insert a `core.access_grants` row **and its `core.user_monthly_usage` row**; return both.

    The two rows are written in one call, and that is not a convenience. A grant with no usage row
    is the state D-09 turns into a 500 rather than a 429, so a helper that seeded only the grant
    would convert every admitted chat case from an honest business answer into an internal error --
    a worse failure than the one this helper exists to prevent.

    `with_usage=False` writes the grant alone and returns `(grant, None)`. It exists for exactly one
    case -- proving D-09's fail-closed branch over the real transport -- and is a keyword here
    rather than a second seeder so there stays one definition of the grant insert: a parallel
    "seed_grant_without_usage" would drift from this one the first time a grant column changed.
    Nothing in `src/` can produce this state; only a failed write can.

    `source` defaults to `manual`, not to a free source. `anonymous_device_grant` and
    `registered_account_grant` both populate the `anti_abuse_required_grant_id` generated column,
    whose deferrable FK requires a matching `core.access_grants_anti_abuse` row at commit -- a table
    with no SQLModel class and no seeding path in this phase. `manual` is the source the schema
    reserves for a hand-issued grant, which is exactly what a fixture writes, and the effective-grant
    predicate reads `status`/`starts_at`/`ends_at` only, never the source.

    `monthly_period` defaults to the current UTC calendar month in `YYYY-MM` form -- the same string
    the request path derives from `RequestContext.evaluated_at`.

    Test seeding only, and deliberately not a provisioning path -- no route reaches it, and `src/`
    still contains no code that writes either table. Real grants originate from Phases 41, 42 and
    45; this helper must never be promoted into `src/`.
    """
    now = datetime.now(UTC)
    async with factory() as session:
        grant = AccessGrant(user_id=user_id,
                            tier_id=tier_id,
                            source=source,
                            status=status,
                            starts_at=now if starts_at is None else starts_at,
                            ends_at=ends_at)
        session.add(grant)
        await session.flush()
        usage = None
        if with_usage:
            usage = UserMonthlyUsage(grant_id=grant.id,
                                     monthly_period=monthly_period or now.strftime("%Y-%m"),
                                     monthly_used=monthly_used)
            session.add(usage)
        await session.commit()
    return grant, usage


async def create_chat(factory, issuer: str, subject: str):
    """Insert a chat with a human+AI message pair for `(issuer, subject)`; return chat_id.

    Seeds `core.users` and its matching `core.external_identities` row when the pair has none.
    The v1.6 version looked a user up by `jwt_sub` and inserted `User(jwt_sub=...)`; v2.0 dropped
    that column, and `(issuer, subject)` -- the table's auth-time lookup key -- is where an
    external subject lives now, so the pair is what identifies a seeded caller here too.

    This is **test seeding only**, and deliberately not a JIT-provisioning path: no route can
    reach it, and `src/` has no code that writes either table. `core.users` rows originate from
    `POST /auth/create-user` in Phase 37.

    The identity is seeded `anonymous` with a NULL `provider_uid` -- the left arm of the table's
    provider/provider_uid agreement CHECK, and the only shape available without inventing the
    sentinel `provider_uid` ruling 9.2 forbids. Plan 06's `seed_identity` owns provider variation
    and the barrier-resolvable case.
    """
    async with factory() as session:
        result = await session.exec(select(ExternalIdentity)
                                    .where(ExternalIdentity.issuer == issuer,
                                           ExternalIdentity.subject == subject))
        identity = result.first()
        if identity is None:
            user = User()
            session.add(user)
            await session.flush()
            identity = ExternalIdentity(user_id=user.id,
                                        issuer=issuer,
                                        subject=subject,
                                        provider=IdentityProvider.anonymous)
            session.add(identity)
            await session.flush()

        chat_id = uuid4()
        chat = Chat(id=chat_id, user_id=identity.user_id, title="test phrase")
        human = Message(chat_id=chat_id, role=ChatRole.human,
                        content={"mode": "analyze", "phrase": "test phrase"})
        ai = Message(chat_id=chat_id, role=ChatRole.ai,
                     content={"resolved_mode": "analyze",
                              "response": "test answer",
                              "issues": [], "suggestions": []})
        chat.messages.append(human)
        chat.messages.append(ai)
        session.add(chat)
        await session.commit()
    return chat_id
