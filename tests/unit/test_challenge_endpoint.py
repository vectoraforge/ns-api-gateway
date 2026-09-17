"""The challenge route's answer for every `operation` value, and for each of the two callers that may ask.

Everything outside the four-value vocabulary is one 400; an account-less caller is refused beyond create-user.
"""
import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_claims,
    get_db,
    get_firebase_adapter,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.jwt_verifier import VerifiedClaims
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.routers import auth as auth_module
from nativespeaker.api.routers import auth_router
from nativespeaker.api.schemas.auth import ChallengeRequest
from nativespeaker.api.tables.auth import AuthOperation
from nativespeaker.api.tables.identities import (
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
)
from nativespeaker.api.tables.users import User

from .conftest import TEST_IDENTITY, TEST_ISSUER, TEST_SUBJECT

UNLINKED_SUBJECT = "unlinked-challenge-subject"

UNLINKED_CLAIMS = VerifiedClaims(issuer=TEST_ISSUER, subject=UNLINKED_SUBJECT)
LINKED_CLAIMS = VerifiedClaims(issuer=TEST_ISSUER, subject=TEST_SUBJECT)


# What the fake store answers with; nothing under test parses either value.
ISSUED_HANDLE = "issued-handle"
ISSUED_EXPIRY = datetime(2026, 1, 1, tzinfo=UTC)


class _RecordingChallengeStore:
    """Records what the route asked of the store, and answers the minimum needed to observe issuance."""

    def __init__(self) -> None:
        self.issued: list[object] = []
        self.bound: list[object] = []

    async def issue(self, session, *, operation, claims, linked):
        self.issued.append(operation)
        self.bound.append(linked)
        return ISSUED_HANDLE, ISSUED_EXPIRY


class _StubResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _RecordingSession:
    """Records what it was asked, so a query on any arm of this route would be visible."""

    def __init__(self, row=None) -> None:
        self._row = row
        self.statements: list[object] = []
        self.commits = 0

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._row)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        raise AssertionError("no path in this module may roll back")


@pytest.fixture
def store(monkeypatch) -> _RecordingChallengeStore:
    recorder = _RecordingChallengeStore()

    async def issue(self, session, *, operation, claims, linked):
        return await recorder.issue(session, operation=operation, claims=claims, linked=linked)

    monkeypatch.setattr(ChallengesDB, "issue", issue)
    return recorder


@pytest.fixture
def session() -> _RecordingSession:
    return _RecordingSession()


@pytest.fixture
def linked_session() -> _RecordingSession:
    return _RecordingSession(row=(TEST_IDENTITY.identity, TEST_IDENTITY.user))


def _identity_row(*, identity_state=IdentityState.active, user_active: bool = True):
    """An `(identity, user)` pair shaped exactly as the single joined statement returns one."""
    user_id = uuid7()
    identity = ExternalIdentity(id=uuid7(), user_id=user_id, issuer=TEST_ISSUER,
                                subject=TEST_SUBJECT, provider=IdentityProvider.google,
                                provider_uid="google-account-test", identity_state=identity_state)
    return identity, User(id=user_id, active=user_active)


@pytest.fixture
def historical_session() -> _RecordingSession:
    return _RecordingSession(row=_identity_row(identity_state=IdentityState.historical))


@pytest.fixture
def blocked_session() -> _RecordingSession:
    return _RecordingSession(row=_identity_row(user_active=False))


def _client_for(claims, session, fake_firebase_adapter):
    """The real auth router, with the barrier's context supplied and app state substituted."""
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_claims] = lambda: claims
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def client(store, session, fake_firebase_adapter):
    """A verified caller whose pair matched no identity row."""
    yield from _client_for(UNLINKED_CLAIMS, session, fake_firebase_adapter)


@pytest.fixture
def linked_client(store, linked_session, fake_firebase_adapter):
    """A verified caller holding an identity row and the user it belongs to."""
    yield from _client_for(LINKED_CLAIMS, linked_session, fake_firebase_adapter)


@pytest.fixture
def historical_client(store, historical_session, fake_firebase_adapter):
    """A verified caller whose identity row is no longer active."""
    yield from _client_for(LINKED_CLAIMS, historical_session, fake_firebase_adapter)


@pytest.fixture
def blocked_client(store, blocked_session, fake_firebase_adapter):
    """A verified caller holding an active identity row whose user is not active."""
    yield from _client_for(LINKED_CLAIMS, blocked_session, fake_firebase_adapter)


def _assert_preauth_refused(response) -> None:
    """Both halves, every time: the 403 and the code the existing pre-auth refusal answers with."""
    assert response.status_code == 403
    assert response.json() == {"code": "preauth_identity_not_allowed"}


def _assert_account_unavailable(response) -> None:
    """Both halves, every time: the two row rejections answer as one class, and neither names a row."""
    assert response.status_code == 403
    assert response.json() == {"code": "account_unavailable"}


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
                                                                          linked_session, operation):
        response = linked_client.post("/auth/challenge", json={"operation": operation})

        assert response.status_code == 200
        # The key set, not two known keys: a third field would pass the weaker check.
        assert set(response.json()) == {"challenge_id", "expires_at"}
        assert response.json()["challenge_id"] == ISSUED_HANDLE
        assert store.issued == [AuthOperation(operation)]
        # The member and not the caller's string, so the store never stores what was typed.
        assert all(isinstance(issued, AuthOperation) for issued in store.issued)
        assert linked_session.commits == 1

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


class TestTheIssuedChallengeIsBoundToWhatTheRouteResolved:
    """The route resolves its own caller, and hands the store the row it found or `None`."""

    def test_a_caller_with_a_row_is_bound_to_that_row(self, linked_client, store, linked_session):
        response = linked_client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.status_code == 200
        assert [bound.identity.id for bound in store.bound] == [TEST_IDENTITY.identity.id]
        assert len(linked_session.statements) == 1

    def test_a_caller_with_no_row_is_bound_to_nothing(self, client, store, session):
        response = client.post("/auth/challenge", json={"operation": "create_user"})

        assert response.status_code == 200
        assert store.bound == [None]
        assert len(session.statements) == 1


class TestEveryRefusalLeavesNothingBehind:
    """The body refusals are syntactic: nothing is issued, nothing is read, and the provider is never called."""

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
        # The route resolves after the operation check, so a refused body issues no statement.
        assert session.statements == []
        assert session.commits == 0
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
    def test_every_other_operation_is_the_preauth_refusal(self, client, store, session,
                                                          fake_firebase_adapter, operation):
        _assert_preauth_refused(client.post("/auth/challenge", json={"operation": operation}))

        assert store.issued == []
        assert session.commits == 0
        assert fake_firebase_adapter.calls == []
        # The row refusal is earned by a read, where every body refusal is not.
        assert len(session.statements) == 1

    @pytest.mark.parametrize("operation", _BEYOND_CREATE_USER)
    def test_the_same_operation_is_issued_once_the_caller_holds_an_account(self, linked_client,
                                                                          store, operation):
        response = linked_client.post("/auth/challenge", json={"operation": operation})

        assert response.status_code == 200
        assert store.issued == [AuthOperation(operation)]


class TestTheRowRejectionsAreThisRoutesOwn:
    """The route resolves its own caller, so the two rejections the router-level declaration used to
    raise are raised here now, for every operation and before anything is issued."""

    @pytest.mark.parametrize("operation", _EVERY_OPERATION)
    def test_a_historical_identity_row_is_refused_before_a_handle_is_issued(
            self, historical_client, store, historical_session, operation):
        _assert_account_unavailable(historical_client.post("/auth/challenge",
                                                           json={"operation": operation}))

        assert store.issued == []
        assert historical_session.commits == 0

    @pytest.mark.parametrize("operation", _EVERY_OPERATION)
    def test_a_blocked_user_is_refused_before_a_handle_is_issued(
            self, blocked_client, store, blocked_session, operation):
        _assert_account_unavailable(blocked_client.post("/auth/challenge",
                                                        json={"operation": operation}))

        assert store.issued == []
        assert blocked_session.commits == 0


class TestTheRefusalOrderDisclosesNothing:
    """A string outside the vocabulary earns the same 400 whether or not the caller holds an account."""

    @pytest.mark.parametrize("operation", _OUTSIDE_THE_VOCABULARY)
    def test_an_unknown_string_is_the_same_refusal_for_both_callers(self, client, linked_client,
                                                                    store, operation):
        _assert_invalid_request(client.post("/auth/challenge", json={"operation": operation}))
        _assert_invalid_request(linked_client.post("/auth/challenge", json={"operation": operation}))

        assert store.issued == []


_OPERATION_LIMIT = ChallengeRequest.model_fields["operation"].metadata[0].max_length

_LONGEST_OPERATION = max(len(value) for value in _EVERY_OPERATION)


class TestTheOperationFieldIsBounded:
    """WR-01. The refusal log carries this value verbatim, so an unbounded string is a log-flooding hole."""

    def test_the_bound_stands_well_above_every_member_of_the_vocabulary(self):
        assert _OPERATION_LIMIT >= 2 * _LONGEST_OPERATION

    def test_an_oversized_operation_is_the_frameworks_refusal_and_never_reaches_the_log(self, client,
                                                                                        store):
        _assert_validation_error(client.post("/auth/challenge",
                                             json={"operation": "a" * (_OPERATION_LIMIT + 1)}))
        assert store.issued == []

    def test_an_operation_at_the_bound_is_still_the_handlers_refusal(self, client):
        """The control: a value the bound admits is classified by the handler, as every string is."""
        _assert_invalid_request(client.post("/auth/challenge",
                                            json={"operation": "a" * _OPERATION_LIMIT}))


_COLLECTION_BUILDERS = {"frozenset", "set", "list", "tuple", "dict"}


def _module_level_collections(source: str) -> list[str]:
    """The names bound at module level to a collection, whether written as a display or built by a call."""
    found = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        builds_a_collection = (isinstance(node.value, ast.List | ast.Set | ast.Dict | ast.Tuple)
                               or (isinstance(node.value, ast.Call)
                                   and getattr(node.value.func, "id", None) in _COLLECTION_BUILDERS))
        if builds_a_collection:
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            found.extend(getattr(target, "id", "<unnamed>") for target in targets)
    return found


class TestTheIssuableSetIsTheEnumAndNothingElse:
    """The handler's module holds no collection of operation names for the enum to disagree with."""

    def test_the_router_module_declares_no_module_level_collection(self):
        assert _module_level_collections(Path(auth_module.__file__).read_text()) == []

    def test_the_walk_sees_an_annotated_binding_and_a_constructor_call(self):
        """WR-65. The control: matching only an unannotated display let the two spellings a
        re-introduced list would actually use through."""
        source = ('_ANNOTATED: frozenset[str] = frozenset({"create_user"})\n'
                  '_CALLED = frozenset({"create_user"})\n'
                  '_DISPLAY = ["create_user"]\n')

        assert _module_level_collections(source) == ["_ANNOTATED", "_CALLED", "_DISPLAY"]
