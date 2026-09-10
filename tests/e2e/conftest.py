import logging
import os
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import firebase_admin
import httpx
import jwt as pyjwt
import pytest
import pytest_asyncio
from firebase_admin import auth
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from unit.conftest import FakeFirebaseAdapter, make_test_verifier
from unit.test_jwks_offload import install_counted_transport

from nativespeaker.api.app.main import app
from nativespeaker.api.auth.app_store import AppStoreNotifications
from nativespeaker.api.auth.devicecheck import BitState
from nativespeaker.api.auth.firebase import _application_default_credential
from nativespeaker.api.auth.google_play import (
    GOOGLE_ISSUER,
    GOOGLE_JWKS_URL,
    PlayDeveloperSubscriptions,
    PubSubPushTokens,
)
from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.auth.store_notifications import (
    RestoredSubscription,
    VerifiedNotification,
)
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.logs import _QUIETED_LIBRARIES
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    Chat,
    ChatRole,
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    Message,
    PurchaseProvider,
    StorePurchaseToken,
    User,
    UserMonthlyUsage,
)

# The tier the migration seeds as reference data at 50 monthly credits, well above any module's use.
REGISTERED_TIER_ID = "registered"


class LogSpy:
    """A recording spy on a module's own logger, so "which record, once" stays observable."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **fields) -> None:
        self.entries.append((event, fields))


class _SpyLogger:
    """Stands in for a module's whole `logger`; only the levels a route spies on are recorded."""

    def __init__(self, spy: LogSpy, levels: tuple[str, ...]) -> None:
        for level in levels:
            setattr(self, level, spy.record)


def spy_on(monkeypatch, targets: tuple[str, ...], levels: tuple[str, ...]) -> LogSpy:
    """A spy, not `capture_logs`: the module-level logger caches its binding, so capture sees nothing.
    The whole `logger` name is replaced, never its level attributes: structlog's lazy proxy builds
    those on demand, so monkeypatch's undo would freeze one onto the proxy for the whole session."""
    spy = LogSpy()
    for target in targets:
        monkeypatch.setattr(target, _SpyLogger(spy, levels))
    return spy


@pytest.fixture(scope="session")
def _app_config():
    """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
    return EnvironmentConfig().app_config


def _identity_toolkit_key(config) -> str:
    """The Identity Toolkit key, unwrapped once. Secret in the config, and read only here."""
    # The loud failure lives here rather than in the config: no request path reads this value,
    # so an absent key is a broken test environment and never a broken deployment.
    api_key = config.jwt.api_key
    assert api_key is not None, "JWT_API_KEY env var required for e2e tests"
    return api_key.get_secret_value()


@pytest.fixture(scope="session")
def firebase_token(_app_config):
    """Obtain a real Firebase ID token via REST API for the dedicated test user."""
    api_key = _identity_toolkit_key(_app_config)
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
    # Assigned, never `setdefault`: `test_user_id` must be the subject of the token this fixture
    # returned, and a stale value carried in by `.env` would silently decouple the two.
    os.environ["FIREBASE_TEST_USER_ID"] = data["localId"]
    return token


def _admin_credential_configured() -> bool:
    """Whether build_admin_apps would find a credential, asked with the one call it makes."""
    return _application_default_credential() is not None


_NO_ADMIN_CREDENTIAL = (
    "no Firebase Admin credential: set GOOGLE_APPLICATION_CREDENTIALS (Application Default "
    "Credentials) in .env"
)


# firebase_token signs in with a password, whose providerData the classifier rejects; only signUp is anonymous.
# Module-scoped, not session-scoped, so the minted user can be deleted through the Admin app the
# lifespan built: that app is torn down with the lifespan, and a session fixture outlives it.
@pytest.fixture(scope="module")
def anonymous_firebase_credential(_app_lifespan, _app_config):
    """A genuinely anonymous Firebase user, minted for real; yields (id_token, local_id), or skips.
    Deleted on the way out, as google_linked_firebase_credential does: the project is shared, so a
    user left behind is permanent, and one accumulates per run."""
    if not _admin_credential_configured():
        pytest.skip(_NO_ADMIN_CREDENTIAL)
    # The app the lifespan already built, reached by its documented name -- never a second one.
    # Resolved before the signUp, as google_linked_firebase_credential does: `get_app` raises
    # `ValueError` when no app carries that name, and the guard above answers a different question
    # (a findable credential, not a registered app). Between the user starting to exist and the try
    # that deletes it nothing may raise, or the minted user is permanent in this shared project.
    admin_app = firebase_admin.get_app(name=f"issuer:{_app_config.jwt.issuer}")
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={_identity_toolkit_key(_app_config)}",
        json={"returnSecureToken": True},
    )
    local_id = None
    # Opened where the user starts existing: signUp has already minted it by the time the body parses.
    try:
        resp.raise_for_status()
        data = resp.json()
        # Subscripting rather than .get(): if returnSecureToken were ever ignored, this fails loudly.
        local_id = data["localId"]
        yield data["idToken"], local_id
    finally:
        if local_id is not None:
            auth.delete_user(local_id, app=admin_app)


def _google_id_token() -> str:
    """Redeem the stored refresh token for a fresh Google ID token; a missing variable raises."""
    resp = httpx.post("https://oauth2.googleapis.com/token",
                      data={"client_id": os.environ["FIREBASE_TEST_GOOGLE_CLIENT_ID"],
                            "client_secret": os.environ["FIREBASE_TEST_GOOGLE_CLIENT_SECRET"],
                            "refresh_token": os.environ["FIREBASE_TEST_GOOGLE_REFRESH_TOKEN"],
                            "grant_type": "refresh_token"})
    resp.raise_for_status()
    # Absent when the one-off consent omitted the `openid` scope; .env.example says to include it.
    return resp.json()["id_token"]


def _release_google_account(admin_app, google_subject: str) -> None:
    """Delete any user a previous run left holding the Google account, or this run's link fails."""
    found = auth.get_users([auth.ProviderIdentifier("google.com", google_subject)], app=admin_app)
    for user in found.users:
        auth.delete_user(user.uid, app=admin_app)


# No skip and no guard: the three variables are supplied before the run, so an absent one is a broken environment.
@pytest.fixture(scope="module")
def google_linked_firebase_credential(_app_lifespan, _app_config):
    """A fresh anonymous Firebase user with the test Google account linked onto it.
    Yields (id_token, local_id), the same pair shape anonymous_firebase_credential yields."""
    api_key = _identity_toolkit_key(_app_config)
    # The app the lifespan already built, reached by its documented name -- never a second one.
    admin_app = firebase_admin.get_app(name=f"issuer:{_app_config.jwt.issuer}")
    google_id_token = _google_id_token()
    # Unverified on purpose: the claim only finds a leftover user, and Firebase verifies the token itself.
    google_subject = pyjwt.decode(google_id_token, options={"verify_signature": False})["sub"]
    _release_google_account(admin_app, google_subject)

    signup = httpx.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp"
                        f"?key={api_key}",
                        json={"returnSecureToken": True})
    local_id = None
    # Opened where the user starts existing, parse included: an abandoned user here is permanent.
    try:
        signup.raise_for_status()
        anonymous = signup.json()
        local_id = anonymous["localId"]
        link = httpx.post(f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp"
                          f"?key={api_key}",
                          json={"postBody": f"id_token={google_id_token}&providerId=google.com",
                                "requestUri": "http://localhost",
                                "returnSecureToken": True,
                                "idToken": anonymous["idToken"]})
        link.raise_for_status()
        linked = link.json()
        # Linking rather than signing in is the whole point: no second Firebase user may appear.
        assert linked["localId"] == local_id
        yield linked["idToken"], local_id
    finally:
        if local_id is not None:
            auth.delete_user(local_id, app=admin_app)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan():
    """Start app lifespan (config, DB engine, verifier, LLM service), then put `logging` back."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    # The lifespan calls `setup_logging`, which clears the root handlers and pins these nine.
    original_levels = {name: logging.getLogger(name).level for name in _QUIETED_LIBRARIES}
    try:
        async with app.router.lifespan_context(app):
            yield app
    finally:
        for name, level in original_levels.items():
            logging.getLogger(name).setLevel(level)
        root.handlers = original_handlers
        root.setLevel(original_level)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def async_client(_app_lifespan, firebase_token):
    """Async HTTP client wired to the real app with Firebase auth."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {firebase_token}"
        yield client


@pytest.fixture(scope="module")
def test_user_id(firebase_token):
    """The Firebase test user's UID, matching the token's sub claim; firebase_token is what sets it."""
    _ = firebase_token
    return os.environ["FIREBASE_TEST_USER_ID"]


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _db_transaction(_app_lifespan):
    """Wrap each test in a transaction that rolls back: the app's session factory is swapped so its writes join it."""
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
    """Swap app.state.jwt_verifier for an ephemeral-RSA one; the app reads it per request, so the real path runs."""
    original = _app_lifespan.state.jwt_verifier
    _app_lifespan.state.jwt_verifier = make_test_verifier()
    try:
        yield _app_lifespan.state.jwt_verifier
    finally:
        _app_lifespan.state.jwt_verifier = original


@pytest.fixture
def scripted_firebase_adapter(_app_lifespan):
    """Swap app.state.firebase_adapter for a scripted fake, defaulting to ok with empty providerData."""
    original = _app_lifespan.state.firebase_adapter
    adapter = FakeFirebaseAdapter()
    _app_lifespan.state.firebase_adapter = adapter
    try:
        yield adapter
    finally:
        _app_lifespan.state.firebase_adapter = original


class FakeDeviceCheckAdapter:
    """A scriptable stand-in for the device-gate seam, recording each method's calls separately."""

    def __init__(self) -> None:
        # A never-set device: the eligible first-ever claim, and what most cases want.
        self.answer: BaseException | BitState = BitState(bit0=False, bit1=False)
        self.write_answer: BaseException | None = None
        self.read_calls: list[str] = []
        self.write_calls: list[tuple[str, bool, bool]] = []

    def script(self, answer: BaseException | BitState) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted state is returned."""
        self.answer = answer

    def script_write(self, answer: BaseException | None) -> None:
        """Raise-or-confirm: a scripted exception is raised, `None` confirms the write."""
        self.write_answer = answer

    async def read_bits(self, device_token: str) -> BitState:
        self.read_calls.append(device_token)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    async def write_bits(self, device_token: str, *, bit0: bool, bit1: bool) -> None:
        self.write_calls.append((device_token, bit0, bit1))
        if isinstance(self.write_answer, BaseException):
            raise self.write_answer


@pytest.fixture
def scripted_devicecheck_adapter(_app_lifespan):
    """Swap app.state.devicecheck_adapter for a scripted fake, defaulting to a never-set device."""
    original = _app_lifespan.state.devicecheck_adapter
    adapter = FakeDeviceCheckAdapter()
    _app_lifespan.state.devicecheck_adapter = adapter
    try:
        yield adapter
    finally:
        _app_lifespan.state.devicecheck_adapter = original


class FakeAppStoreNotifications:
    """A scriptable stand-in for the store-callback seam, recording every payload it was given."""

    def __init__(self) -> None:
        # No default answer: every case scripts the notification it wants verified or refused.
        self.answer: BaseException | VerifiedNotification | None = None
        # The restore proof is a second entry point, so it carries a second scripted answer.
        self.restore_answer: BaseException | RestoredSubscription | None = None
        self.calls: list[str] = []
        # The pair, never the artifact alone: SHARED-INVARIANTS binds this seam to the request's
        # one captured instant, so a case can only see a second clock read if the instant is here.
        self.restore_calls: list[tuple[str, datetime]] = []

    def script(self, answer: BaseException | VerifiedNotification) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted notification is returned."""
        self.answer = answer

    def script_restore(self, answer: BaseException | RestoredSubscription) -> None:
        """Raise-or-return on the restore entry point, on the same terms as `script` above."""
        self.restore_answer = answer

    def verify(self, signed_payload: str) -> VerifiedNotification:
        self.calls.append(signed_payload)
        if isinstance(self.answer, BaseException):
            raise self.answer
        assert self.answer is not None, "the seam was called before a case scripted it"
        return self.answer

    def verify_transaction(self, signed_transaction: str,
                           evaluated_at: datetime) -> RestoredSubscription:
        self.restore_calls.append((signed_transaction, evaluated_at))
        if isinstance(self.restore_answer, BaseException):
            raise self.restore_answer
        assert self.restore_answer is not None, "the seam was called before a case scripted it"
        return self.restore_answer


@pytest.fixture
def scripted_app_store_notifications(_app_lifespan):
    """Swap app.state.app_store_notifications for a scripted fake, scripted per case."""
    original = _app_lifespan.state.app_store_notifications
    notifications = FakeAppStoreNotifications()
    _app_lifespan.state.app_store_notifications = notifications
    try:
        yield notifications
    finally:
        _app_lifespan.state.app_store_notifications = original


@pytest.fixture
def unconfigured_app_store_notifications(_app_lifespan):
    """Swap app.state.app_store_notifications for one holding no verifier, as an incomplete config leaves it."""
    original = _app_lifespan.state.app_store_notifications
    _app_lifespan.state.app_store_notifications = AppStoreNotifications(verifier=None, products={})
    try:
        yield _app_lifespan.state.app_store_notifications
    finally:
        _app_lifespan.state.app_store_notifications = original


# The three values a deployment configures for the Pub/Sub push, in obviously synthetic form.
GOOGLE_PUSH_AUDIENCE = "https://nativespeaker.test/webhooks/google-play/rtdn"
GOOGLE_PUSH_SERVICE_ACCOUNT = "rtdn-push@nativespeaker-test.iam.gserviceaccount.com"
GOOGLE_PACKAGE_NAME = "com.nativespeaker.app"

# Google's own issuer, read from the module under test so a changed constant fails the cases.
GOOGLE_PUSH_ISSUER = GOOGLE_ISSUER

# The Play product the scripted map resolves, and the tier the migration seeds for a paid one.
GOOGLE_PRODUCT_ID = "nativespeaker.subscription.monthly"
GOOGLE_PAID_TIER_ID = "paid"


def play_subscription_body(**overrides) -> dict:
    """One `purchases.subscriptionsv2.get` response body, active on one line item."""
    now = datetime.now(UTC)
    body = {"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
            "startTime": now.isoformat(),
            "latestOrderId": f"order-{uuid4()}",
            "lineItems": [{"productId": GOOGLE_PRODUCT_ID,
                           "expiryTime": (now + timedelta(days=30)).isoformat()}]}
    return body | overrides


class ScriptedPlayApi:
    """The Play read scripted at the transport, recording every request the real class sent."""

    def __init__(self) -> None:
        self.body = play_subscription_body()
        self.status_code = 200
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.body)


class StubPlayCredential:
    """A credential that is already valid, so no case ever reaches a token refresh."""

    valid = True
    token = "a-synthetic-play-access-token"

    def refresh(self, request) -> None:
        raise AssertionError("a valid credential was refreshed")


@pytest.fixture
def real_google_play_seam(_app_lifespan, monkeypatch):
    """Install the real Google classes: a real verifier over a fake JWKS, and a scripted Play transport."""
    install_counted_transport(monkeypatch)
    play = _app_lifespan.state.config.google_play
    original = (_app_lifespan.state.google_push_tokens, _app_lifespan.state.play_subscriptions,
                play.package_name, play.push_audience, play.push_service_account_email)
    play.package_name = GOOGLE_PACKAGE_NAME
    play.push_audience = GOOGLE_PUSH_AUDIENCE
    play.push_service_account_email = GOOGLE_PUSH_SERVICE_ACCOUNT

    scripted = ScriptedPlayApi()
    verifier = JWTVerifier(jwks_url=GOOGLE_JWKS_URL,
                           audience=GOOGLE_PUSH_AUDIENCE,
                           issuer=GOOGLE_ISSUER,
                           required_claims={"email": GOOGLE_PUSH_SERVICE_ACCOUNT,
                                            "email_verified": True})
    _app_lifespan.state.google_push_tokens = PubSubPushTokens(verifier=verifier)
    _app_lifespan.state.play_subscriptions = PlayDeveloperSubscriptions(
        credential=StubPlayCredential(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(scripted.handle)),
        products={GOOGLE_PRODUCT_ID: GOOGLE_PAID_TIER_ID})
    try:
        yield scripted
    finally:
        (_app_lifespan.state.google_push_tokens, _app_lifespan.state.play_subscriptions,
         play.package_name, play.push_audience, play.push_service_account_email) = original


class FakePlaySubscriptions:
    """A scriptable stand-in for the Play read seam, recording every read it was asked for."""

    def __init__(self) -> None:
        # No default answer: every case scripts the notification it wants read or the failure it wants.
        self.answer: BaseException | VerifiedNotification | None = None
        # The restore read is a second entry point, so it carries a second scripted answer.
        self.restore_answer: BaseException | RestoredSubscription | None = None
        self.calls: list[dict] = []
        self.restore_calls: list[dict] = []

    def script(self, answer: BaseException | VerifiedNotification) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted notification is returned."""
        self.answer = answer

    def script_restore(self, answer: BaseException | RestoredSubscription) -> None:
        """Raise-or-return on the restore entry point, on the same terms as `script` above."""
        self.restore_answer = answer

    async def read_for_restore(self, *, package_name: str, purchase_token: str,
                               evaluated_at: datetime) -> RestoredSubscription:
        self.restore_calls.append({"package_name": package_name,
                                   "purchase_token": purchase_token,
                                   "evaluated_at": evaluated_at})
        if isinstance(self.restore_answer, BaseException):
            raise self.restore_answer
        assert self.restore_answer is not None, "the seam was called before a case scripted it"
        return self.restore_answer

    # `async` because the live read does I/O; FakeDeviceCheckAdapter above is the same precedent.
    async def read(self, *, package_name: str, purchase_token: str, event_type: str,
                   notification_uuid: str, signed_at: datetime | None,
                   evaluated_at: datetime) -> VerifiedNotification:
        self.calls.append({"package_name": package_name, "purchase_token": purchase_token,
                           "event_type": event_type, "notification_uuid": notification_uuid,
                           "signed_at": signed_at, "evaluated_at": evaluated_at})
        if isinstance(self.answer, BaseException):
            raise self.answer
        assert self.answer is not None, "the seam was called before a case scripted it"
        return self.answer


class AcceptingPushTokens:
    """A push-token seam that admits any bearer, for the cases that are not about the token."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def verify(self, bearer: str) -> None:
        self.calls.append(bearer)


@pytest.fixture
def scripted_play_subscriptions(_app_lifespan):
    """Swap app.state.play_subscriptions for a scripted fake, scripted per case."""
    original = _app_lifespan.state.play_subscriptions
    subscriptions = FakePlaySubscriptions()
    _app_lifespan.state.play_subscriptions = subscriptions
    try:
        yield subscriptions
    finally:
        _app_lifespan.state.play_subscriptions = original


@pytest.fixture
def scripted_google_play(_app_lifespan, scripted_play_subscriptions):
    """The scripted Play read with the push check neutralised, so a case scripts an outcome
    without minting a token; it yields the same fake."""
    play = _app_lifespan.state.config.google_play
    original = (_app_lifespan.state.google_push_tokens, play.package_name)
    _app_lifespan.state.google_push_tokens = AcceptingPushTokens()
    play.package_name = GOOGLE_PACKAGE_NAME
    try:
        yield scripted_play_subscriptions
    finally:
        (_app_lifespan.state.google_push_tokens, play.package_name) = original


def _play_is_never_reached(request: httpx.Request) -> httpx.Response:
    """The transport an unconfigured deployment holds: reaching Play at all is the failure."""
    raise AssertionError(f"an unconfigured deployment reached {request.url}")


@pytest.fixture
def unconfigured_google_play(_app_lifespan):
    """Swap both Google classes for ones holding no verifier and no credential, which is the
    state an incomplete configuration leaves them in."""
    original = (_app_lifespan.state.google_push_tokens, _app_lifespan.state.play_subscriptions)
    _app_lifespan.state.google_push_tokens = PubSubPushTokens(verifier=None)
    # Constructed with None, never deleted: lifespan always builds both, configured or not.
    _app_lifespan.state.play_subscriptions = PlayDeveloperSubscriptions(
        credential=None,
        client=httpx.AsyncClient(transport=httpx.MockTransport(_play_is_never_reached)),
        products={})
    try:
        yield _app_lifespan.state.google_push_tokens
    finally:
        (_app_lifespan.state.google_push_tokens,
         _app_lifespan.state.play_subscriptions) = original


@pytest_asyncio.fixture(loop_scope="module")
async def linked_firebase_identity(_db_transaction, _app_config, test_user_id):
    """Seed the real Firebase credential's identity pair, so async_client is admitted."""
    return await seed_identity(_db_transaction,
                               issuer=_app_config.jwt.issuer,
                               subject=test_user_id)


async def seed_identity(factory, *,
                        issuer: str,
                        subject: str,
                        identity_state: IdentityState = IdentityState.active,
                        user_active: bool = True,
                        provider: IdentityProvider = IdentityProvider.google):
    """Insert a core.users row and its matching core.external_identities row; return both."""
    # The table's CHECK ties the two together: provider_uid is NULL exactly for anonymous.
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
    """One effective grant plus its usage row for the seeded caller; without it a quota route answers 429."""
    user, _ = linked_firebase_identity
    return await seed_grant(_db_transaction, user_id=user.id)


@pytest_asyncio.fixture(loop_scope="module")
async def own_chat(_db_transaction, linked_firebase_identity) -> UUID:
    """A chat owned by the seeded caller, written directly because POST /chats is itself quota-checked."""
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
    """Insert a core.access_grants row and its core.user_monthly_usage row; return both."""
    # A grant with no usage row is a 500 rather than a 429, so with_usage=False is only for that case.
    now = datetime.now(UTC)
    async with factory() as session:
        grant = AccessGrant(user_id=user_id,
                            tier_id=tier_id,
                            source=source,
                            status=status,
                            starts_at=now if starts_at is None else starts_at,
                            ends_at=ends_at,
                            created_at=now,
                            updated_at=now)
        session.add(grant)
        await session.flush()
        usage = None
        if with_usage:
            usage = UserMonthlyUsage(grant_id=grant.id,
                                     monthly_period=monthly_period or now.strftime("%Y-%m"),
                                     monthly_used=monthly_used,
                                     created_at=now,
                                     updated_at=now)
            session.add(usage)
        await session.commit()
    return grant, usage


async def seed_subscription(factory, *,
                            external_id: str,
                            provider: PurchaseProvider = PurchaseProvider.apple,
                            user_id: UUID | None = None,
                            tier_id: str = REGISTERED_TIER_ID,
                            status: str = "active",
                            last_cross_account_transfer_month: date | None = None) -> UUID:
    """Insert a core.subscriptions row and return its id; `user_id` is NULL on an unowned row."""
    # The column list of `_seed_subscription_grant`, plus the one column a restore move writes.
    now = datetime.now(UTC)
    subscription_id = uuid4()
    async with factory() as session:
        await session.exec(text(
            "INSERT INTO core.subscriptions"
            " (id, user_id, provider, external_id, tier_id, status,"
            " last_cross_account_transfer_month, created_at, updated_at)"
            # The two enum columns are cast in the statement: a bound parameter arrives as text.
            " VALUES (:id, :user_id, CAST(:provider AS core.subscription_provider),"
            " :external_id, :tier_id, CAST(:status AS core.subscription_status),"
            " CAST(:transfer_month AS DATE), :now, :now)")
            .bindparams(id=subscription_id, user_id=user_id, provider=str(provider),
                        external_id=external_id, tier_id=tier_id, status=status,
                        transfer_month=last_cross_account_transfer_month, now=now))
        await session.commit()
    return subscription_id


async def seed_purchase_tokens(factory, *,
                               user_id: UUID,
                               providers=PurchaseProvider):
    """Insert one core.store_purchase_tokens row per member of `providers`; return them."""
    # A narrowed `providers` is only for the missing-row case: a partial set is a 500, never a partial body.
    now = datetime.now(UTC)
    async with factory() as session:
        tokens = [StorePurchaseToken(user_id=user_id,
                                     provider=provider,
                                     identity_value=str(uuid4()),
                                     created_at=now)
                  for provider in providers]
        for token in tokens:
            session.add(token)
        await session.commit()
    return tokens


async def create_chat(factory, issuer: str, subject: str):
    """Insert a chat with a human+AI message pair for (issuer, subject), seeding the pair if absent."""
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
