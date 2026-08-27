"""The completion body's validation partition: an unusable handle is the framework's 422, and nothing else.

The route reads its body and nothing else. There is no mode to dispatch on, so the only question a handle
can raise is whether it is a usable string -- and the framework, not the handler, answers it. Every rejection
asserts the body code as well as the status, since a status alone would also pass for some other code.
"""
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
from nativespeaker.api.models.auth import CreateUserRequest
from nativespeaker.api.routers import auth_router

from .conftest import TEST_ISSUER

UNLINKED_SUBJECT = "unlinked-body-subject"

# Supplied only because `RequestContext` requires it; nothing below reads the value.
CREATE_USER_ROUTE = "/auth/create-user"


class _RecordingChallengeStore:
    """Records what the route asked of the store, and answers the minimum needed to observe the read."""

    def __init__(self) -> None:
        self.issued: list[str] = []
        self.located: list[str] = []

    async def issue(self, session, *, operation, identity, now):
        """Kept though completion never issues, so "nothing was issued" stays an assertion with teeth."""
        self.issued.append(str(operation))
        return "issued-handle", datetime(2026, 1, 1, tzinfo=UTC)

    async def locate(self, session, challenge_id):
        self.located.append(challenge_id)
        return None


class _EmptyResult:
    def first(self):
        return None


class _UnlinkedSession:
    """Answers no-such-identity-row and records what it was asked, so any read at all would be visible."""

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
    # An async generator, not a plain callable: `get_db` releases the read transaction itself, and a
    # callable has no `try`/`except` to do it with. Mirrors `app/dependencies.py::get_db` exactly.
    async def _db():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _assert_validation_error(response) -> None:
    """The framework's refusal, rendered by the shared handler. Both halves, every time."""
    assert response.status_code == 422
    assert response.json() == {"code": "validation_error"}


class TestTheHandleReachesTheStore:
    def test_a_body_handle_is_located_byte_for_byte(self, client, store, session):
        response = client.post("/auth/create-user", json={"challenge_id": "a-handle"})

        # `challenge_required`, which only the completion path can produce here.
        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert store.located == ["a-handle"]
        assert store.issued == []
        # This arm releases `locate`'s read transaction, so a spurious rollback elsewhere fails here.
        assert session.rollbacks == 1
        # The handler resolves no identity of its own: the racy pre-check is gone, not relocated.
        assert session.statements == []


# Absent, null, empty, four wrong scalar types and two containers. None of them is a usable handle.
_UNUSABLE_BODIES = [
    pytest.param({}, id="field-absent"),
    pytest.param({"challenge_id": None}, id="null"),
    pytest.param({"challenge_id": ""}, id="empty-string"),
    pytest.param({"challenge_id": 123}, id="int"),
    pytest.param({"challenge_id": 0}, id="zero"),
    pytest.param({"challenge_id": 1.5}, id="float"),
    pytest.param({"challenge_id": True}, id="bool"),
    pytest.param({"challenge_id": ["a-handle"]}, id="list"),
    pytest.param({"challenge_id": {"value": "a-handle"}}, id="object"),
]


class TestTheValidationPartition:
    """Every unusable handle is one 422 bucket, carrying no field name and no offending value."""

    @pytest.mark.parametrize("body", _UNUSABLE_BODIES)
    def test_an_unusable_handle_is_a_validation_error(self, client, body):
        """These were a hand-rolled 400 while the field was loosely typed; the annotation now earns them."""
        _assert_validation_error(client.post("/auth/create-user", json=body))

    def test_no_body_at_all_is_a_validation_error(self, client):
        """The body is required, so an absent one is refused exactly as an unusable one is."""
        _assert_validation_error(client.post("/auth/create-user"))

    def test_an_old_style_query_parameter_call_is_a_validation_error(self, client, store):
        """The query string is simply ignored now: `?challenge=true` with no body is a missing body, nothing more."""
        _assert_validation_error(client.post("/auth/create-user?challenge=true"))

        # The mode ambiguity this parameter used to express can no longer be expressed at all.
        assert store.issued == []


class TestTheModelArmsDirectly:
    """The three arms pinned on the model itself, so a route change cannot quietly relax the field."""

    @pytest.mark.parametrize("kwargs", [{}, {"challenge_id": ""}])
    def test_an_absent_or_empty_handle_raises(self, kwargs):
        with pytest.raises(ValueError):
            CreateUserRequest(**kwargs)

    def test_a_whitespace_only_handle_is_accepted_verbatim(self):
        """The constraint counts characters, not non-whitespace ones -- deliberately, see the asymmetry below."""
        assert CreateUserRequest(challenge_id="   ").challenge_id == "   "


class TestTheWhitespaceAsymmetry:
    def test_a_padded_handle_reaches_completion_untouched(self, client, store, session):
        """Trimming anywhere on the way down would widen a secret capability handle into a family of handles."""
        response = client.post("/auth/create-user", json={"challenge_id": "  a-handle  "})

        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert store.located == ["  a-handle  "]
        assert session.rollbacks == 1


class TestTheRejectionHasNoSideEffects:
    """The rejection issues nothing, locates nothing, and reads nothing."""

    @pytest.mark.parametrize("body", _UNUSABLE_BODIES)
    def test_nothing_is_issued_read_or_resolved(self, client, store, session,
                                                fake_firebase_adapter, body):
        response = client.post("/auth/create-user", json=body)

        _assert_validation_error(response)
        assert store.issued == []
        assert store.located == []
        # The rejection is the framework's: the handler never ran, so it read nothing at all.
        assert session.statements == []
        # And no provider read, for the same reason.
        assert fake_firebase_adapter.calls == []

    def test_a_corrected_retry_after_a_rejection_still_reaches_the_store(self, client, store):
        """A corrected retry must behave exactly as a first attempt would."""
        _assert_validation_error(client.post("/auth/create-user", json={}))

        response = client.post("/auth/create-user", json={"challenge_id": "a-handle"})

        assert response.status_code == 409
        assert store.located == ["a-handle"]
