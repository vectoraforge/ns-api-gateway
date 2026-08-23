"""CREATE-02: the route's mode-signal **dispatch**, exhaustively, at unit speed.

`tests/unit/test_mode_signal.py` already proves the classifier. This module proves the thing one
layer up -- that `POST /auth/create-user` actually routes each classification to the right place,
and that a rejected classification touches nothing.

**Status and body code are both asserted on every rejection, always.** 37-RESEARCH Pitfall 6 is
precisely the failure where the permissive body typing is quietly lost and every wrong-typed handle
becomes FastAPI's 422 `validation_error` instead of §02's 400 `invalid_request`. Those are
different classes saying different things, and a status-only assertion would not notice: both are
4xx, both carry a JSON body, and the route would look fine in review.

The app here mirrors `conftest.py`'s `client` fixture -- the identity context is supplied instead of
installing the barrier, because what a handler does *once admitted* is this module's subject.
`get_raw_query_string` is deliberately **not** overridden: the duplicated-`challenge` case is only
visible in the raw ASGI bytes, so overriding that accessor would stub out the very thing under test.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_audit_writer,
    get_challenge_store,
    get_db,
    get_firebase_adapter,
    get_request_context,
    get_session_factory,
)
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.context import ClientIpBucketKind, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.registry import lookup
from nativespeaker.api.routers import auth_router

from .conftest import TEST_ISSUER

UNLINKED_SUBJECT = "unlinked-mode-signal-subject"

# The **production** metadata for this route, looked up rather than hand-built: a fixture-only
# RouteMetadata would let this module keep passing after the real declaration changed.
CREATE_USER_META = lookup("POST", "/auth/create-user")


class _RecordingChallengeStore:
    """Records what the route asked of the store, and answers the minimum to observe dispatch.

    `issue` returns a fixed pair, so prepare answers 200. `locate` returns `None`, so completion
    answers `challenge_required` -- a 409 that could not have been produced by prepare or by a
    mode-signal rejection, which makes it a positive signal of *which* branch ran.
    """

    def __init__(self) -> None:
        self.issued: list[str] = []
        self.located: list[str] = []

    async def issue(self, session, *, operation, identity, now):
        self.issued.append(str(operation))
        return "issued-handle", datetime(2026, 1, 1, tzinfo=UTC)

    async def locate(self, session, challenge_id):
        self.located.append(challenge_id)
        return None


class _RecordingAuditWriter:
    """Fails the assertion by *recording*, not by raising -- the count is the subject.

    A mode-signal rejection must write zero `audit.auth_events` rows: it belongs to the admission
    phase, has no internal `core.auth_event_result`, and is recorded in the structured security log
    alone (§4.1, §02). Asserting on a recorder rather than on database rows is what keeps this a
    unit test; the row-count version over a real database is 37-08's.
    """

    def __init__(self) -> None:
        self.writes: list[str] = []

    async def write_standalone(self, session_factory, **kwargs):
        self.writes.append(str(kwargs.get("result")))

    async def write_in_transaction(self, session, **kwargs):
        self.writes.append(str(kwargs.get("result")))


class _EmptyResult:
    def first(self):
        return None


class _UnlinkedSession:
    """A session that answers "no such identity row" and records what it was asked.

    Prepare mode really does read the database once, and that is not an accident to stub away: it
    is §02 prepare step 1's racy already-linked pre-check, which for a pre-auth caller is a single
    direct read. `statements` is recorded so a case can assert *one* -- a second read appearing
    here would mean the handler had grown a second identity resolution, which §1.4 forbids.

    `commit` still raises, because no path this module drives may reach one: a mode-signal
    rejection precedes everything, and prepare's own transaction is committed by `get_db`'s
    teardown, which this app overrides away.

    **`rollback` records rather than raising** (37-08). The two completion cases here reach
    `challenge_not_found`, and that rejection now writes a standalone-durable audit row -- which
    means releasing the read transaction `locate` opened first, exactly as prepare's already-linked
    arm already did. The count is kept so the release stays observable rather than merely tolerated.
    """

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
def writer() -> _RecordingAuditWriter:
    return _RecordingAuditWriter()


@pytest.fixture
def session() -> _UnlinkedSession:
    return _UnlinkedSession()


@pytest.fixture
def client(store, writer, session, fake_firebase_adapter):
    """The real auth router, with the barrier's context supplied and app state substituted."""
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    context = RequestContext(
        identity=PreAuthIdentity(issuer=TEST_ISSUER, subject=UNLINKED_SUBJECT),
        route_metadata=CREATE_USER_META,
        client_ip_bucket_kind=ClientIpBucketKind.ipv4,
        evaluated_at=datetime.now(UTC),
        attempt_id=uuid4(),
    )
    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_session_factory] = lambda: None
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_audit_writer] = lambda: writer
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
        # Exactly one read: §02 prepare step 1's racy pre-check, and nothing else. A second would
        # mean the handler had grown an identity resolution of its own.
        assert len(session.statements) == 1

    def test_a_body_handle_with_no_challenge_parameter_is_completion(self, client, store, session):
        response = client.post("/auth/create-user", json={"challenge_id": "a-handle"})

        # `challenge_required`, which only the completion branch can produce here.
        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert store.located == ["a-handle"]
        assert store.issued == []
        # The standalone-durable audit row requires releasing `locate`'s read transaction, so this
        # arm rolls back exactly once. Asserted, not merely tolerated: the fake counts instead of
        # raising, so without this a spurious rollback anywhere in the module would pass silently.
        assert session.rollbacks == 1


class TestTheInvalidRequestPartition:
    """Every shape §02 pins to `invalid_request`, and each asserts the code as well as the status."""

    def test_both_signals_together(self, client):
        _assert_invalid_request(
            client.post("/auth/create-user?challenge=true", json={"challenge_id": "a-handle"}))

    def test_neither_signal(self, client):
        _assert_invalid_request(client.post("/auth/create-user"))

    def test_neither_signal_with_an_empty_body_object(self, client):
        _assert_invalid_request(client.post("/auth/create-user", json={}))

    def test_a_duplicated_challenge_parameter(self, client):
        """The case a first-value-wins query accessor cannot see.

        `request.query_params.get("challenge")` folds duplicates and answers `"true"`, so this
        would dispatch to prepare -- which is exactly why the route parses the raw ASGI bytes.
        """
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
        """Pitfall 6, parametrized.

        `123` and `{"value": ...}` are the load-bearing members: a `challenge_id: str | None`
        annotation would make both a Pydantic `validation_error` (422), a class §02 never names for
        this route. The `True` case is subtler still -- `bool` is a subclass of `int`, so a
        permissive annotation admits it and only the classifier's `isinstance(..., str)` rejects it.
        """
        response = client.post("/auth/create-user", json={"challenge_id": handle})

        _assert_invalid_request(response)
        assert response.status_code != 422


class TestTheWhitespaceAsymmetry:
    def test_a_padded_handle_reaches_completion_untouched(self, client, store, session):
        """Deliberately **not** `invalid_request` -- and it must arrive byte-for-byte.

        `.strip()` in the classifier decides emptiness only; `locate` compares byte-for-byte, so a
        padded handle is a handle that does not exist (`challenge_not_found`), not a malformed
        request. Trimming it anywhere on the way down would widen a secret capability handle into a
        family of handles, from two modules away.
        """
        response = client.post("/auth/create-user", json={"challenge_id": "  a-handle  "})

        assert response.status_code == 409
        assert response.json() == {"code": "challenge_required"}
        assert store.located == ["  a-handle  "]
        assert session.rollbacks == 1


class TestTheRejectionHasNoSideEffects:
    """§02: the rejection issues nothing, consumes nothing, and writes no audit row."""

    @pytest.mark.parametrize("kwargs", [
        {"params": {"challenge": "true"}, "json": {"challenge_id": "a-handle"}},
        {},
        {"params": [("challenge", "true"), ("challenge", "true")]},
        {"params": {"challenge": "1"}},
        {"json": {"challenge_id": 123}},
    ])
    def test_no_audit_row_is_written(self, client, store, writer, session,
                                     fake_firebase_adapter, kwargs):
        response = client.post("/auth/create-user", **kwargs)

        _assert_invalid_request(response)
        assert writer.writes == []
        assert store.issued == []
        assert store.located == []
        # The rejection is syntactic and precedes the pre-check too: it reads nothing at all.
        assert session.statements == []
        # And no provider read: the rejection is syntactic and precedes everything.
        assert fake_firebase_adapter.calls == []

    def test_a_prepare_after_a_rejection_still_succeeds(self, client, store):
        """The proof that the rejection left no residue.

        A corrected retry may reuse the same unexpired challenge precisely because nothing was
        touched, so the second request has to behave as though the first never happened.
        """
        _assert_invalid_request(client.post("/auth/create-user"))

        response = client.post("/auth/create-user?challenge=true")

        assert response.status_code == 200
        assert store.issued == ["create_user"]
