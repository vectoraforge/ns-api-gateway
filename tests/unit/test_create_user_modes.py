"""The route's mode-signal dispatch: every rejection asserts the body code as well as the status."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_request_context,
)
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.routers import auth_router

from .conftest import TEST_ISSUER

UNLINKED_SUBJECT = "unlinked-mode-signal-subject"

# Supplied only because `RequestContext` requires it; nothing below reads the value.
CREATE_USER_ROUTE = "/auth/create-user"


class _RecordingChallengeStore:
    """Records what the route asked of the store, and answers the minimum needed to observe dispatch."""

    def __init__(self) -> None:
        self.issued: list[str] = []
        self.located: list[str] = []

    async def issue(self, session, *, operation, identity, now):
        self.issued.append(str(operation))
        return "issued-handle", datetime(2026, 1, 1, tzinfo=UTC)

    async def locate(self, session, challenge_id):
        self.located.append(challenge_id)
        return None


class _EmptyResult:
    def first(self):
        return None


class _UnlinkedSession:
    """Answers no-such-identity-row and records what it was asked, so a second read would be visible."""

    def __init__(self) -> None:
        self.statements: list[object] = []
        self.rollbacks = 0

    async def exec(self, statement):
        self.statements.append(statement)
        return _EmptyResult()

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        raise AssertionError("no path in this module may commit")


@pytest.fixture
def store() -> _RecordingChallengeStore:
    return _RecordingChallengeStore()


@pytest.fixture
def session() -> _UnlinkedSession:
    return _UnlinkedSession()


@pytest.fixture
def client(store, session, fake_firebase_adapter):
    """The real auth router, with the barrier's context supplied and app state substituted."""
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    context = RequestContext(
        identity=PreAuthIdentity(issuer=TEST_ISSUER, subject=UNLINKED_SUBJECT),
        route=CREATE_USER_ROUTE,
        evaluated_at=datetime.now(UTC),
        attempt_id=uuid4(),
    )
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _assert_invalid_request(response) -> None:
    """Both halves, every time. See the module docstring for why the status alone is not enough."""
    assert response.status_code == 400
    assert response.json() == {"code": "invalid_request"}


class TestTheTwoModesDispatch:
    def test_challenge_true_with_no_body_handle_is_prepare(self, client, store, session):
        response = client.post("/auth/create-user?challenge=true")

        assert response.status_code == 200
        assert set(response.json()) == {"challenge_id", "expires_at"}
        assert store.issued == ["create_user"]
        assert store.located == []
        # A second read would mean the handler had grown an identity resolution of its own.
        assert len(session.statements) == 1

    def test_a_body_handle_with_no_challenge_parameter_is_completion(self, client, store, session):
        response = client.post("/auth/create-user", json={"challenge_id": "a-handle"})

        # `challenge_required`, which only the completion branch can produce here.
        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert store.located == ["a-handle"]
        assert store.issued == []
        # This arm releases `locate`'s read transaction, so a spurious rollback elsewhere fails here.
        assert session.rollbacks == 1


class TestTheInvalidRequestPartition:
    """Every shape pinned to `invalid_request`, each asserting the code as well as the status."""

    def test_both_signals_together(self, client):
        _assert_invalid_request(
            client.post("/auth/create-user?challenge=true", json={"challenge_id": "a-handle"}))

    def test_neither_signal(self, client):
        _assert_invalid_request(client.post("/auth/create-user"))

    def test_neither_signal_with_an_empty_body_object(self, client):
        _assert_invalid_request(client.post("/auth/create-user", json={}))

    def test_a_duplicated_challenge_parameter(self, client):
        """A first-value-wins accessor folds duplicates, which is why the route parses the raw ASGI bytes."""
        _assert_invalid_request(client.post("/auth/create-user?challenge=true&challenge=true"))

    @pytest.mark.parametrize("query", ["challenge=1",
                                       "challenge=TRUE",
                                       "challenge=True",
                                       "challenge=yes",
                                       "challenge=",
                                       "challenge"])
    def test_any_challenge_value_other_than_exactly_true(self, client, query):
        """`true` is the only prepare signal. Not truthy, not case-insensitive, not bare."""
        _assert_invalid_request(client.post(f"/auth/create-user?{query}"))

    @pytest.mark.parametrize("handle", [None, "", "   ", "\t\n", 123, 0, 1.5, True,
                                        ["a-handle"], {"value": "a-handle"}])
    def test_an_unusable_body_handle_is_400_and_never_422(self, client, handle):
        """A typed annotation would make these a Pydantic 422, a class this route never answers with."""
        response = client.post("/auth/create-user", json={"challenge_id": handle})

        _assert_invalid_request(response)
        assert response.status_code != 422


class TestTheWhitespaceAsymmetry:
    def test_a_padded_handle_reaches_completion_untouched(self, client, store, session):
        """Trimming anywhere on the way down would widen a secret capability handle into a family of handles."""
        response = client.post("/auth/create-user", json={"challenge_id": "  a-handle  "})

        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert store.located == ["  a-handle  "]
        assert session.rollbacks == 1


class TestTheRejectionHasNoSideEffects:
    """The rejection issues nothing, consumes nothing, and reads nothing."""

    @pytest.mark.parametrize("kwargs", [
        {"params": {"challenge": "true"}, "json": {"challenge_id": "a-handle"}},
        {},
        {"params": [("challenge", "true"), ("challenge", "true")]},
        {"params": {"challenge": "1"}},
        {"json": {"challenge_id": 123}},
    ])
    def test_nothing_is_issued_read_or_resolved(self, client, store, session,
                                                fake_firebase_adapter, kwargs):
        response = client.post("/auth/create-user", **kwargs)

        _assert_invalid_request(response)
        assert store.issued == []
        assert store.located == []
        # The rejection is syntactic and precedes the pre-check too: it reads nothing at all.
        assert session.statements == []
        # And no provider read: the rejection is syntactic and precedes everything.
        assert fake_firebase_adapter.calls == []

    def test_a_prepare_after_a_rejection_still_succeeds(self, client, store):
        """A corrected retry may reuse the same unexpired challenge, so the second request must behave as the first."""
        _assert_invalid_request(client.post("/auth/create-user"))

        response = client.post("/auth/create-user?challenge=true")

        assert response.status_code == 200
        assert store.issued == ["create_user"]
