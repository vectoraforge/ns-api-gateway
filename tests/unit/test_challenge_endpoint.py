"""The challenge route's answer for every `operation` value, and for each of the two callers that may ask.

Everything outside the four-value vocabulary is one 400; an account-less caller is refused beyond create-user.
"""
import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_identity,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.routers import auth as auth_module
from nativespeaker.api.routers import auth_router
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.auth import AuthOperation

from .conftest import TEST_IDENTITY, TEST_ISSUER

UNLINKED_SUBJECT = "unlinked-challenge-subject"


# What the fake store answers with; nothing under test parses either value.
ISSUED_HANDLE = "issued-handle"
ISSUED_EXPIRY = datetime(2026, 1, 1, tzinfo=UTC)


class _RecordingChallengeStore:
    """Records what the route asked of the store, and answers the minimum needed to observe issuance."""

    def __init__(self) -> None:
        self.issued: list[object] = []

    async def issue(self, session, *, operation, identity, now):
        self.issued.append(operation)
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


def _client_for(identity, store, session, fake_firebase_adapter):
    """The real auth router, with the barrier's context supplied and app state substituted."""
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_identity] = lambda: identity
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def client(store, session, fake_firebase_adapter):
    """A verified caller whose pair matched no identity row."""
    yield from _client_for(Identity(issuer=TEST_ISSUER, subject=UNLINKED_SUBJECT),
                           store, session, fake_firebase_adapter)


@pytest.fixture
def linked_client(store, session, fake_firebase_adapter):
    """A verified caller holding an identity row and the user it belongs to."""
    yield from _client_for(TEST_IDENTITY, store, session, fake_firebase_adapter)


def _assert_preauth_refused(response) -> None:
    """Both halves, every time: the 403 and the code the existing pre-auth refusal answers with."""
    assert response.status_code == 403
    assert response.json() == {"code": "preauth_identity_not_allowed"}


def _assert_invalid_request(response) -> None:
    """Both halves, every time: a status alone would also pass for a body carrying some other code."""
    assert response.status_code == 400
    assert response.json() == {"code": "invalid_request"}


def _assert_validation_error(response) -> None:
    """The framework's refusal, rendered by the shared handler rather than by FastAPI's default body."""
    assert response.status_code == 422
    assert response.json() == {"code": "validation_error"}


# Read off the enum, never restated: a list written here could disagree with the type.
_EVERY_OPERATION = [member.value for member in AuthOperation]
_BEYOND_CREATE_USER = [member.value for member in AuthOperation
                       if member is not AuthOperation.create_user]


class TestTheIssuableOperations:
    """The values this route issues for, read off the enum rather than restated here."""

    @pytest.mark.parametrize("operation", _EVERY_OPERATION)
    def test_a_member_of_the_vocabulary_is_issued_with_the_two_field_body(self, linked_client, store,
                                                                          operation):
        response = linked_client.post("/auth/challenge", json={"operation": operation})

        assert response.status_code == 200
        # The key set, not two known keys: a third field would pass the weaker check.
        assert set(response.json()) == {"challenge_id", "expires_at"}
        assert response.json()["challenge_id"] == ISSUED_HANDLE
        assert store.issued == [AuthOperation(operation)]
        # The member and not the caller's string, so the store never stores what was typed.
        assert all(isinstance(issued, AuthOperation) for issued in store.issued)

    def test_the_issued_handle_is_not_cacheable(self, client):
        """`no-store` and not `no-cache`: a revalidatable copy of a secret handle is still a copy."""
        response = client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.headers["cache-control"] == "no-store"


# Former operation names, a plausible invention, a case variation and the empty string.
_OUTSIDE_THE_VOCABULARY = ["sync", "sign_out_all", "restore_subscription",
                           "nope", "", "create-user", "CREATE_USER"]


class TestTheStringsOutsideTheVocabulary:
    """One 400 for every one of them, so no string outside the four is distinguishable from another."""

    @pytest.mark.parametrize("operation", _OUTSIDE_THE_VOCABULARY)
    def test_every_string_outside_the_vocabulary_is_the_same_refusal(self, client, operation):
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
        ({"operation": _BEYOND_CREATE_USER[0]}, {"code": "preauth_identity_not_allowed"}),
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
        assert store.issued == [AuthOperation.create_user]


class TestTheAccountLessCallerPreparesCreateUserAndNothingElse:
    """D-10: create-user is the only operation a caller matching no identity row may prepare."""

    def test_create_user_is_issued_to_a_caller_with_no_account(self, client, store):
        response = client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.status_code == 200
        assert response.json()["challenge_id"] == ISSUED_HANDLE
        assert store.issued == [AuthOperation.create_user]

    @pytest.mark.parametrize("operation", _BEYOND_CREATE_USER)
    def test_every_other_operation_is_the_preauth_refusal(self, client, store, operation):
        _assert_preauth_refused(client.post("/auth/challenge", json={"operation": operation}))

        assert store.issued == []

    @pytest.mark.parametrize("operation", _BEYOND_CREATE_USER)
    def test_the_same_operation_is_issued_once_the_caller_holds_an_account(self, linked_client,
                                                                          store, operation):
        response = linked_client.post("/auth/challenge", json={"operation": operation})

        assert response.status_code == 200
        assert store.issued == [AuthOperation(operation)]


class TestTheRefusalOrderDisclosesNothing:
    """A string outside the vocabulary earns the same 400 whether or not the caller holds an account."""

    @pytest.mark.parametrize("operation", _OUTSIDE_THE_VOCABULARY)
    def test_an_unknown_string_is_the_same_refusal_for_both_callers(self, client, linked_client,
                                                                    store, operation):
        _assert_invalid_request(client.post("/auth/challenge", json={"operation": operation}))
        _assert_invalid_request(linked_client.post("/auth/challenge", json={"operation": operation}))

        assert store.issued == []


class TestTheIssuableSetIsTheEnumAndNothingElse:
    """The handler's module holds no collection of operation names for the enum to disagree with."""

    def test_the_router_module_declares_no_module_level_collection(self):
        module = ast.parse(Path(auth_module.__file__).read_text())
        collections = [node for node in module.body if isinstance(node, ast.Assign)
                       and isinstance(node.value, ast.List | ast.Set | ast.Dict | ast.Tuple)]

        assert collections == []
