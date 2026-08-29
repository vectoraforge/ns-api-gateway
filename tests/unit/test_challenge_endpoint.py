"""The challenge route's answer for every `operation` value: one refusal bucket, and the framework's own arm.

Every operation string the route will not issue for gets the same 400, so the route cannot be asked which
operations exist. A value that is not a string at all never reaches the handler -- the framework refuses it
first -- and that arm is pinned here rather than worked around.
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
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.identity import Identity, RequestContext
from nativespeaker.api.routers import auth_router

from .conftest import TEST_ISSUER

UNLINKED_SUBJECT = "unlinked-challenge-subject"

CHALLENGE_ROUTE = "/auth/challenge"

# What the fake store answers with; nothing under test parses either value.
ISSUED_HANDLE = "issued-handle"
ISSUED_EXPIRY = datetime(2026, 1, 1, tzinfo=UTC)


class _RecordingChallengeStore:
    """Records what the route asked of the store, and answers the minimum needed to observe issuance."""

    def __init__(self) -> None:
        self.issued: list[str] = []

    async def issue(self, session, *, operation, identity, now):
        self.issued.append(str(operation))
        return ISSUED_HANDLE, ISSUED_EXPIRY


class _EmptyResult:
    def first(self):
        return None


class _RecordingSession:
    """Records what it was asked, so a query on any arm of this route would be visible."""

    def __init__(self) -> None:
        self.statements: list[object] = []

    async def exec(self, statement):
        self.statements.append(statement)
        return _EmptyResult()

    async def commit(self):
        raise AssertionError("no path in this module may commit")

    async def rollback(self):
        raise AssertionError("no path in this module may roll back")


@pytest.fixture
def store() -> _RecordingChallengeStore:
    return _RecordingChallengeStore()


@pytest.fixture
def session() -> _RecordingSession:
    return _RecordingSession()


@pytest.fixture
def client(store, session, fake_firebase_adapter):
    """The real auth router, with the barrier's context supplied and app state substituted."""
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    context = RequestContext(
        identity=Identity(issuer=TEST_ISSUER, subject=UNLINKED_SUBJECT),
        route=CHALLENGE_ROUTE,
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
    """Both halves, every time: a status alone would also pass for a body carrying some other code."""
    assert response.status_code == 400
    assert response.json() == {"code": "invalid_request"}


def _assert_validation_error(response) -> None:
    """The framework's refusal, rendered by the shared handler rather than by FastAPI's default body."""
    assert response.status_code == 422
    assert response.json() == {"code": "validation_error"}


class TestTheIssuableOperation:
    """The one value this route issues for today."""

    def test_create_user_is_issued_with_the_two_field_body(self, client, store):
        response = client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.status_code == 200
        # The key set, not two known keys: a third field would pass the weaker check.
        assert set(response.json()) == {"challenge_id", "expires_at"}
        assert response.json()["challenge_id"] == ISSUED_HANDLE
        # Asked for exactly once, and for the operation the caller named.
        assert store.issued == ["create_user"]

    def test_the_issued_handle_is_not_cacheable(self, client):
        """`no-store` and not `no-cache`: a revalidatable copy of a secret handle is still a copy."""
        response = client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.headers["cache-control"] == "no-store"


# Members of the operation vocabulary whose phases are unbuilt, and strings outside it entirely.
_NOT_ISSUABLE = ["sync", "sign_out_all", "restore_subscription", "claim_anonymous_grant",
                 "nope", "", "create-user", "CREATE_USER"]


class TestTheOperationsThisRouteWillNotIssueFor:
    """One bucket for all of them, so an unbuilt operation and an invented one are indistinguishable."""

    @pytest.mark.parametrize("operation", _NOT_ISSUABLE)
    def test_every_unissuable_string_is_the_same_refusal(self, client, operation):
        _assert_invalid_request(client.post("/auth/challenge", json={"operation": operation}))


# Values the field's `str` annotation refuses outright, so the handler never runs for any of them.
_NOT_A_STRING = [123, None, 1.5, True, ["create_user"], {"operation": "create_user"}]


class TestTheFrameworksOwnArm:
    """A non-string, a missing field, and an absent body all render through the shared handler."""

    @pytest.mark.parametrize("operation", _NOT_A_STRING)
    def test_a_non_string_operation_is_a_validation_error(self, client, operation):
        _assert_validation_error(client.post("/auth/challenge", json={"operation": operation}))

    def test_an_empty_body_object_is_a_validation_error(self, client):
        _assert_validation_error(client.post("/auth/challenge", json={}))

    def test_no_body_at_all_is_a_validation_error(self, client):
        _assert_validation_error(client.post("/auth/challenge"))


class TestEveryRefusalLeavesNothingBehind:
    """The refusals are syntactic: nothing is issued, nothing is read, and the provider is never called."""

    @pytest.mark.parametrize(("body", "expected"), [
        ({"operation": "sync"}, {"code": "invalid_request"}),
        ({"operation": "nope"}, {"code": "invalid_request"}),
        ({"operation": 123}, {"code": "validation_error"}),
        ({"operation": None}, {"code": "validation_error"}),
        ({}, {"code": "validation_error"}),
    ])
    def test_nothing_is_issued_read_or_looked_up(self, client, store, session,
                                                 fake_firebase_adapter, body, expected):
        response = client.post("/auth/challenge", json=body)

        assert response.json() == expected
        assert store.issued == []
        # Issuance resolves no identity of its own, so a statement here would be a new read.
        assert session.statements == []
        assert fake_firebase_adapter.calls == []

    def test_an_issue_after_a_refusal_still_succeeds(self, client, store):
        """A corrected retry must behave exactly as a first attempt would."""
        _assert_invalid_request(client.post("/auth/challenge", json={"operation": "sync"}))

        response = client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.status_code == 200
        assert store.issued == ["create_user"]
