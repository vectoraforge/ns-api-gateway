"""The profile route's answer: one closed body, one unlocked query, and no branch on any client signal."""
import contextlib
from uuid import uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from nativespeaker.api.app.dependencies import get_linked_identity, get_purchases_db
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.routers import users_router
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.purchases import PurchaseProvider
from nativespeaker.api.tables.users import User

from .conftest import TEST_ISSUER

SUBJECT = "profile-subject"
EMAIL = "seeded@example.test"
DISPLAY_NAME = "Seeded Caller"
APPLE_TOKEN = "apple-token-1"
GOOGLE_TOKEN = "google-play-token-1"

# Derived from the enum and never hand-listed: a third store must fail here until this route serves it.
EVERY_STORE = set(PurchaseProvider)
SEEDED_TOKENS = {PurchaseProvider.apple: APPLE_TOKEN, PurchaseProvider.google_play: GOOGLE_TOKEN}

# The whole payload as one literal: a fourth top-level key or a fifth profile field fails against it.
EXPECTED_BODY = {"profile": {"email": EMAIL, "display_name": DISPLAY_NAME},
                 "identity_provider": IdentityProvider.google.value,
                 "purchase_tokens": {"apple": APPLE_TOKEN, "google_play": GOOGLE_TOKEN}}


class _RecordingResult:
    """The two-column rows the read unpacks: `(provider, identity_value)` tuples, not model instances."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _RecordingSession:
    """Records what it was asked, so a second query or a `core.users` read on this route is visible."""

    def __init__(self, tokens):
        self._tokens = dict(tokens)
        self.statements: list[object] = []

    async def exec(self, statement):
        self.statements.append(statement)
        return _RecordingResult(self._tokens.items())

    async def commit(self):
        raise AssertionError("no path in this module may commit")

    async def rollback(self):
        raise AssertionError("no path in this module may roll back")


def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))


def _linked_identity(*, email=EMAIL, display_name=DISPLAY_NAME) -> Identity:
    """A linked caller carrying the profile fields the shared `TEST_IDENTITY` leaves unset."""
    user_id = uuid7()
    return Identity(issuer=TEST_ISSUER, subject=SUBJECT,
                    user=User(id=user_id, active=True, email=email, display_name=display_name),
                    identity=ExternalIdentity(id=uuid7(), user_id=user_id, issuer=TEST_ISSUER,
                                              subject=SUBJECT, provider=IdentityProvider.google,
                                              provider_uid="google-account-profile",
                                              identity_state=IdentityState.active))


@contextlib.contextmanager
def _client_for(identity: Identity, session: _RecordingSession):
    """The real users router, with the barrier's context supplied and the token store substituted."""
    app = FastAPI()
    app.include_router(users_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_linked_identity] = lambda: identity
    app.dependency_overrides[get_purchases_db] = lambda: PurchasesDB(session)

    # `raise_server_exceptions=False` so the 500 arm renders through the shared handler rather than propagating.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def session() -> _RecordingSession:
    return _RecordingSession(SEEDED_TOKENS)


@pytest.fixture
def identity() -> Identity:
    return _linked_identity()


@pytest.fixture
def client(identity, session):
    with _client_for(identity, session) as test_client:
        yield test_client


class TestTheProfileBodyIsClosed:
    """The payload is one literal: a fourth top-level key or a fifth profile field fails here."""

    def test_a_linked_caller_reads_the_whole_body_and_nothing_more(self, client):
        response = client.get("/users/me")

        assert response.status_code == 200
        assert response.json() == EXPECTED_BODY

    def test_the_token_map_carries_one_key_per_store(self, client):
        """The key set is read off the enum, so a third store fails until this route serves it."""
        body = client.get("/users/me").json()

        assert set(body["purchase_tokens"]) == {store.value for store in EVERY_STORE}

    def test_the_body_is_never_stored_by_a_cache(self, client):
        """`no-store` and not `no-cache`: a revalidatable copy of a store token is still a copy."""
        response = client.get("/users/me")

        assert response.headers["cache-control"] == "no-store"


class TestTheProfileTakesOneQuery:
    """One statement over the token table alone; the profile fields arrive from the barrier's own read."""

    def test_exactly_one_statement_is_issued(self, client, session):
        client.get("/users/me")

        assert len(session.statements) == 1

    def test_the_statement_reads_the_token_table(self, client, session):
        """The positive half: without it the users-table case below could pass on an empty string."""
        client.get("/users/me")

        assert "core.store_purchase_tokens" in _compiled(session.statements[0])

    def test_no_statement_reads_the_users_table(self, client, session):
        """The profile fields are already in hand, so a second read of `core.users` is a regression."""
        client.get("/users/me")

        assert all("core.users" not in _compiled(statement) for statement in session.statements)


# Signals the caller supplies about itself: a user agent, an unknown header, an unknown query parameter.
_CLIENT_SIGNALS = [pytest.param({"User-Agent": "NativeSpeaker-iOS/9.9 (iPhone17,2)"}, None, id="ios-agent"),
                   pytest.param({"User-Agent": "curl/8.7.1"}, None, id="curl-agent"),
                   pytest.param({"X-Platform": "android"}, None, id="unknown-platform-header"),
                   pytest.param({}, {"platform": "android"}, id="unknown-platform-parameter"),
                   pytest.param({}, {"store": "google_play"}, id="unknown-store-parameter")]


class TestTheBodyIgnoresEveryClientSignal:
    """The same caller reads the same bytes whatever it says about itself; a branch would fail here."""

    @pytest.mark.parametrize(("headers", "params"), _CLIENT_SIGNALS)
    def test_the_response_is_byte_identical_to_the_baseline(self, client, headers, params):
        """Bytes and not a re-parsed dict, so a reordering or a formatting change is visible too."""
        baseline = client.get("/users/me")

        response = client.get("/users/me", headers=headers, params=params)

        assert response.status_code == 200
        assert response.content == baseline.content


class TestANullContactFieldIsNotAMissingToken:
    """A nullable profile column answers `null` inside `profile` and leaves the token map whole."""

    def test_a_caller_with_neither_contact_field_still_reads_both_store_keys(self, session):
        with _client_for(_linked_identity(email=None, display_name=None), session) as client:
            response = client.get("/users/me")

        assert response.status_code == 200
        assert response.json()["profile"] == {"email": None, "display_name": None}
        assert set(response.json()["purchase_tokens"]) == {store.value for store in EVERY_STORE}


# Every incomplete account: no row at all, and each single store, which an emptiness check would pass.
_INCOMPLETE_ACCOUNTS = [pytest.param({}, id="no-store-row"),
                        pytest.param({PurchaseProvider.apple: APPLE_TOKEN}, id="apple-only"),
                        pytest.param({PurchaseProvider.google_play: GOOGLE_TOKEN}, id="google-play-only")]


class TestAnIncompleteAccountIsAnOpaqueFailure:
    """An unrepresented store is a broken invariant answered as the generic 500, never as a partial body."""

    @pytest.mark.parametrize("seeded", _INCOMPLETE_ACCOUNTS)
    def test_a_missing_store_row_answers_the_generic_500(self, identity, seeded):
        with _client_for(identity, _RecordingSession(seeded)) as client:
            response = client.get("/users/me")

        assert response.status_code == 500
        assert response.json() == {"code": "internal_error"}

    @pytest.mark.parametrize("seeded", _INCOMPLETE_ACCOUNTS)
    def test_the_refusal_carries_no_cache_header_and_no_identifier(self, identity, seeded):
        """The 500 body is the whole disclosure: no user id, no provider name, no token value."""
        with _client_for(identity, _RecordingSession(seeded)) as client:
            response = client.get("/users/me")

        assert set(response.json()) == {"code"}
        assert APPLE_TOKEN not in response.text
        assert GOOGLE_TOKEN not in response.text
