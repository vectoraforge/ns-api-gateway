"""§02's completion rejection precedence: four client classes over nine internal results.

**The numbered completion flow IS the rejection precedence** ("reject for the earliest failed
step"), and the mapping it defines is a client contract the client cannot audit. `challenge_required`
says "prepare again", `auth_required` says "re-authenticate", `verification_temporarily_unavailable`
says "back off and retry the whole operation", and `operation_not_allowed` is terminal and routes to
support. Those are four incompatible instructions, so every arm here asserts three things that a
status-only test would let drift apart: the client class, the internal `core.auth_event_result`
audited beside it, and whether the challenge was consumed.

**Why the collaborators are fakes rather than a database.** The subject is the router's branch
structure, and a fake store that models the two conditional updates exactly (`claim` fails on a
claimed or expired row; `consume` fails under any other attempt id) reproduces every lifecycle
outcome the branches depend on at unit speed. The *binding* comparison is not faked -- it delegates
to the real `ChallengeStore.verify_binding`, through a keyring spy, because "the keyring was never
consulted" is one of the assertions and a fake could only assert against itself. The row-level
proofs over real PostgreSQL live in `tests/e2e/test_create_user.py`.

**Why `create_account` is substituted.** It is `auth/creation.py`'s consuming transaction and this
module is about what happens *before* it -- every case here either never reaches it or asserts
precisely that it was not reached. Recording the call is the honest way to assert "the classifier's
verdict reached the transaction unchanged" without this module growing an opinion about a function
another plan owns and proves end to end.
"""
import base64
from datetime import UTC, datetime, timedelta
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
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import ClientIpBucketKind, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.auth.registry import lookup
from nativespeaker.api.config import HmacConfig
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.routers import auth_router

from .conftest import TEST_ISSUER

SUBJECT = "precedence-unlinked-subject"
OTHER_SUBJECT = "precedence-somebody-else"
OTHER_ISSUER = "https://securetoken.google.com/some-other-project"
HANDLE = "a-scripted-handle"

CREATE_USER_META = lookup("POST", "/auth/create-user")


def _material(seed: int) -> str:
    return base64.b64encode(bytes((seed * 37 + i) % 256 for i in range(32))).decode()


class _SpyKeyring:
    """The real derivation, with the one comparison counted.

    §6.4 says a pre-auth row whose `preauth_subject_hash` was already cleared is **not compared at
    all** -- the keyring is never consulted and the row takes the already-used rejection. An
    assertion on the returned rejection alone cannot tell "compared against NULL and rejected" from
    "not compared", and only the second is the specified behaviour.
    """

    def __init__(self) -> None:
        self._ring = HmacKeyring(HmacConfig(active_version=1, keys={1: _material(1)}))
        self.comparisons = 0

    def actor_subject_hash(self, issuer: str, subject: str, *, version: int | None = None) -> bytes:
        return self._ring.actor_subject_hash(issuer, subject, version=version)

    def actor_subject_matches(self, stored: bytes, issuer: str, subject: str) -> bool:
        self.comparisons += 1
        return self._ring.actor_subject_matches(stored, issuer, subject)


class _FakeChallengeStore:
    """One in-memory row, with `claim` and `consume` modelling the real conditional updates.

    Both mirror their WHERE clauses exactly -- `claim` requires `claimed_at IS NULL` **and** an
    `expires_at` in the future, `consume` requires still-claimed under **this** attempt's id -- so
    the router's branches see the same answers a real row would give them. `verify_binding` is not
    modelled at all: it delegates to the real store, which is pure and is the thing whose
    cleared-hash arm this module asserts against.
    """

    def __init__(self, keyring: _SpyKeyring) -> None:
        self._binding = ChallengeStore(keyring)
        self.row: AuthChallenge | None = None
        self.consume_calls = 0

    async def locate(self, session, challenge_id: str) -> AuthChallenge | None:
        if self.row is not None and self.row.challenge_id == challenge_id:
            return self.row
        return None

    def verify_binding(self, row, identity):
        return self._binding.verify_binding(row, identity)

    async def claim(self, session, *, challenge_id, claim_attempt_id, now) -> bool:
        row = self.row
        if row is None or row.challenge_id != challenge_id:
            return False
        if row.claimed_at is not None or row.expires_at <= now:
            return False
        row.claimed_at = now
        row.claim_attempt_id = claim_attempt_id
        return True

    async def consume(self, session, *, challenge_id, claim_attempt_id, now) -> bool:
        self.consume_calls += 1
        row = self.row
        if row is None or row.challenge_id != challenge_id:
            return False
        if (row.claimed_at is None or row.consumed_at is not None
                or row.claim_attempt_id != claim_attempt_id):
            return False
        row.consumed_at = now
        row.preauth_subject_hash = None
        return True


class _RecordingAuditWriter:
    """Records mode and kwargs. The count is an assertion in every case: §4.1 owes exactly one row
    per on-path attempt, and "one" is as much the contract as "which"."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, dict]] = []

    async def write_standalone(self, session_factory, **kwargs) -> None:
        self.rows.append(("standalone", kwargs))

    async def write_in_transaction(self, session, **kwargs) -> None:
        self.rows.append(("in_transaction", kwargs))

    @property
    def results(self) -> list[AuthEventResult]:
        return [kwargs["result"] for _, kwargs in self.rows]


class _StubSession:
    """Records the transaction boundaries and refuses to answer a query.

    Nothing on the completion path may issue a statement through this session: the one read
    completion owes is `auth/creation.py`'s in-transaction re-resolution, and that function is
    substituted here. A statement arriving would mean the router had grown an identity resolution
    of its own, which §1.4 forbids.
    """

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshed: list[object] = []

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, obj) -> None:
        self.refreshed.append(obj)

    async def exec(self, statement):
        raise AssertionError("the completion path issued a query of its own: "
                             f"{statement!r}")


class _RecordingCreator:
    """Stands in for `auth/creation.py::create_account` and records the facts handed to it."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.result = AuthEventResult.succeeded

    async def __call__(self, session, **kwargs) -> AuthEventResult:
        self.calls.append(kwargs)
        return self.result


@pytest.fixture
def keyring() -> _SpyKeyring:
    return _SpyKeyring()


@pytest.fixture
def store(keyring) -> _FakeChallengeStore:
    return _FakeChallengeStore(keyring)


@pytest.fixture
def writer() -> _RecordingAuditWriter:
    return _RecordingAuditWriter()


@pytest.fixture
def session() -> _StubSession:
    return _StubSession()


@pytest.fixture
def creator(monkeypatch) -> _RecordingCreator:
    recorder = _RecordingCreator()
    monkeypatch.setattr("nativespeaker.api.routers.auth.create_account", recorder)
    return recorder


@pytest.fixture
def context() -> RequestContext:
    return RequestContext(
        identity=PreAuthIdentity(issuer=TEST_ISSUER, subject=SUBJECT),
        route_metadata=CREATE_USER_META,
        client_ip_bucket_kind=ClientIpBucketKind.ipv4,
        evaluated_at=datetime.now(UTC),
        attempt_id=uuid4(),
    )


@pytest.fixture
def client(store, writer, session, context, creator, fake_firebase_adapter):
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_request_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_session_factory] = lambda: None
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_audit_writer] = lambda: writer
    app.dependency_overrides[get_firebase_adapter] = lambda: fake_firebase_adapter

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _issued_row(context: RequestContext, keyring: _SpyKeyring, *,
                operation: AuthOperation = AuthOperation.create_user,
                issuer: str = TEST_ISSUER,
                subject: str = SUBJECT,
                ttl_seconds: int = 300,
                claimed: bool = False,
                consumed: bool = False,
                cleared_hash: bool = False) -> AuthChallenge:
    """A pre-auth-bound challenge row in whichever lifecycle state the case needs."""
    now = context.evaluated_at
    row = AuthChallenge(
        challenge_id=HANDLE,
        operation=operation,
        preauth_issuer=issuer,
        preauth_subject_hash=(None if cleared_hash
                              else keyring.actor_subject_hash(issuer, subject)),
        expires_at=now + timedelta(seconds=ttl_seconds),
        created_at=now,
    )
    if claimed or consumed:
        row.claimed_at = now
        row.claim_attempt_id = uuid4()
    if consumed:
        row.consumed_at = now
    return row


def _complete(client, handle: str = HANDLE):
    return client.post("/auth/create-user", json={"challenge_id": handle})


def _assert_challenge_required(response) -> None:
    """Byte-identical across all five rejections -- completion is not an enumeration oracle.

    Asserting the body by equality rather than by a key lookup is what makes a future "more
    helpful" second field fail here instead of shipping (T-37-34).
    """
    assert response.status_code == 409
    assert response.json() == {"code": "challenge_required"}


class TestTheFiveChallengeRejections:
    """§02 completion steps 3, 4 and 5 -- one client class, five internal results, no consumption.

    **None of the five consumes**, and that is the part easiest to get backwards: an identity or
    operation mismatch is rejected before the claim precisely so a wrong presenter cannot burn the
    rightful user's in-flight challenge (T-37-35), and a claim loser never held a claim, so it has
    nothing to consume. Consumption begins at the Admin lookup.
    """

    def test_an_unknown_handle_is_challenge_not_found(self, client, store, writer,
                                                      fake_firebase_adapter):
        store.row = None

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_not_found]
        assert writer.rows[0][0] == "standalone"
        # No row was located, so there is nothing non-secret to correlate on -- and the public
        # handle is never what goes there.
        assert writer.rows[0][1]["challenge_row_id"] is None
        assert fake_firebase_adapter.calls == []

    def test_a_challenge_bound_to_another_subject_is_an_identity_mismatch(
            self, client, store, writer, context, keyring, fake_firebase_adapter):
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_identity_mismatch]
        # Rejected BEFORE the claim: the rightful owner's row is untouched.
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_a_challenge_bound_to_another_issuer_is_an_identity_mismatch(
            self, client, store, writer, context, keyring, fake_firebase_adapter):
        store.row = _issued_row(context, keyring, issuer=OTHER_ISSUER)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_identity_mismatch]
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert fake_firebase_adapter.calls == []

    def test_a_challenge_for_another_operation_is_an_operation_mismatch(
            self, client, store, writer, context, keyring, fake_firebase_adapter):
        """D-12 removed the *variant* check, not this one. A challenge issued for a different
        operation and presented here is still step 4's rejection, and still a pre-claim one."""
        store.row = _issued_row(context, keyring,
                                operation=AuthOperation.claim_anonymous_grant)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_operation_mismatch]
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_a_cleared_binding_hash_is_already_used_and_is_never_compared(
            self, client, store, writer, context, keyring, fake_firebase_adapter):
        store.row = _issued_row(context, keyring, claimed=True, consumed=True, cleared_hash=True)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_consumed]
        # The whole point of the cleared-hash arm: the comparison is skipped entirely.
        assert keyring.comparisons == 0
        assert fake_firebase_adapter.calls == []

    def test_a_still_issued_but_expired_challenge_is_challenge_expired(
            self, client, store, writer, context, keyring, fake_firebase_adapter):
        """The claim's WHERE is the only expiry evaluation anywhere, so this rejection is reached
        by losing the claim and re-reading the row, never by comparing `expires_at` in the router."""
        store.row = _issued_row(context, keyring, ttl_seconds=-1)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_expired]
        assert store.row.claimed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_an_already_claimed_challenge_is_challenge_consumed(
            self, client, store, writer, context, keyring, fake_firebase_adapter):
        """The claim loser performs no work at all -- no provider read, no mutation -- and never
        receives the claim-holder's stored outcome. There is no idempotent replay (§02 DELETIONS);
        the client reconciles through `/auth/sync`."""
        store.row = _issued_row(context, keyring, claimed=True)
        holder = store.row.claim_attempt_id

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_consumed]
        # The holder's claim is untouched, and the loser consumed nothing.
        assert store.row.claim_attempt_id == holder
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_every_rejection_writes_exactly_one_audit_row_correlated_on_the_row_id(
            self, client, store, writer, context, keyring):
        """The located row's NON-SECRET id, never the public handle (§6.1, T-37-26)."""
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT)

        _complete(client)

        assert len(writer.rows) == 1
        mode, kwargs = writer.rows[0]
        assert mode == "standalone"
        assert kwargs["challenge_row_id"] == store.row.id
        assert kwargs["operation"] is AuthOperation.create_user
        # The token was verified, so the all-or-nothing actor CHECK requires both actor fields.
        assert kwargs["actor_issuer"] == TEST_ISSUER
        assert kwargs["actor_subject"] == SUBJECT
        # NULL for a pre-auth attempt: §4.2 admits `actor_provider` only from the stored provider
        # column of a resolved linked identity.
        assert kwargs["actor_provider"] is None
        assert HANDLE not in repr(kwargs["details"])
