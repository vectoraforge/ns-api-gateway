import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from unit.conftest import make_test_verifier

from nativespeaker.api.app.main import app
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.models import (
    Chat,
    ChatRole,
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    Message,
    User,
)


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
