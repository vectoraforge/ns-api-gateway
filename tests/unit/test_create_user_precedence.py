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
from nativespeaker.api.auth.adapters import ProviderDataEntry, ProviderDataOutcome
from nativespeaker.api.auth.challenges import ChallengeStore
from nativespeaker.api.auth.context import ClientIpBucketKind, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.auth.registry import lookup
from nativespeaker.api.auth.retry import FIREBASE_LOOKUP_ATTEMPTS
from nativespeaker.api.config import HmacConfig
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import IdentityProvider
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


class TestTheProviderStageRejections:
    """§02 completion steps 8 and 9 -- three outcomes, three client classes, all consuming.

    **Collapsing any pair here is a client-contract bug the client cannot detect.**
    `auth_required` (401) says the token no longer identifies a Firebase user;
    `verification_temporarily_unavailable` (503) says the lookup itself failed and the whole
    operation should be retried; `operation_not_allowed` (403) is a terminal statement about the
    account. Telling a client with a deleted Firebase user to retry forever is exactly what
    `user_not_found` mapping onto 503 would do, which is why those two are asserted at distinct
    statuses with distinct internal results (T-37-38).
    """

    def test_user_not_found_is_auth_required_and_persists_nothing(
            self, client, store, writer, context, keyring, creator, fake_firebase_adapter):
        """A valid token for a deleted Firebase user must not create an account (T-37-37)."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(ProviderDataOutcome.user_not_found)

        response = _complete(client)

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
        assert writer.results == [AuthEventResult.firebase_user_unresolved]
        # Definitive and non-retryable: it spends no further attempt.
        assert len(fake_firebase_adapter.calls) == 1
        assert creator.calls == []

    def test_an_exhausted_retry_budget_is_verification_temporarily_unavailable(
            self, client, store, writer, context, keyring, creator, fake_firebase_adapter):
        """Three attempts, then the §7.1 exhaustion mapping -- and no `tenacity.RetryError`.

        The call count is what proves the retry predicate is wired end to end rather than only in
        37-02's isolated unit: a `retry_if_exception_type` predicate would match nothing here and
        would silently turn the three-attempt budget into a one-attempt budget.
        """
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(ProviderDataOutcome.retryable_failure)

        response = _complete(client)

        assert response.status_code == 503
        assert response.json() == {"code": "verification_temporarily_unavailable"}
        assert writer.results == [AuthEventResult.firebase_lookup_unavailable]
        assert len(fake_firebase_adapter.calls) == FIREBASE_LOOKUP_ATTEMPTS == 3
        assert creator.calls == []

    def test_a_selection_failure_is_unavailable_on_its_first_attempt(
            self, client, store, writer, context, keyring, creator, fake_firebase_adapter):
        """An issuer mismatch fails closed and never falls back to another project -- so it is
        definitive, spends one attempt, and lands on the same internal result as exhaustion."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(ProviderDataOutcome.selection_failure)

        response = _complete(client)

        assert response.status_code == 503
        assert response.json() == {"code": "verification_temporarily_unavailable"}
        assert writer.results == [AuthEventResult.firebase_lookup_unavailable]
        assert len(fake_firebase_adapter.calls) == 1
        assert creator.calls == []

    @pytest.mark.parametrize("entries", [
        # Both providers at once. There is no first recognized entry to take.
        (ProviderDataEntry("google.com", "g-uid"), ProviderDataEntry("apple.com", "a-uid")),
        # One unrecognized entry -- the exact shape the e2e email/password credential produces.
        (ProviderDataEntry("password", "someone@example.test"),),
        # Recognized, but with no uid: §02 makes the entry's non-empty uid the SOLE source of
        # `provider_uid`, so a missing one is a malformed lookup, not an anonymous account.
        (ProviderDataEntry("google.com", ""),),
    ])
    def test_a_rejecting_provider_data_shape_is_operation_not_allowed(
            self, client, store, writer, context, keyring, creator, fake_firebase_adapter,
            entries):
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(ProviderDataOutcome.ok, entries=entries)

        response = _complete(client)

        assert response.status_code == 403
        assert response.json() == {"code": "operation_not_allowed"}
        assert writer.results == [AuthEventResult.provider_not_linked]
        # D-12 left the bounded cause with exactly two members; the third went with the declaration
        # it described. No flow is named anywhere in the response.
        assert writer.rows[0][1]["details"]["failure"]["cause"] == "invalid-shape"
        assert len(fake_firebase_adapter.calls) == 1
        assert creator.calls == []

    def test_one_recognized_entry_with_a_uid_reaches_the_consuming_transaction(
            self, client, store, context, keyring, creator, fake_firebase_adapter):
        """The classifier's verdict is carried through unchanged; the router re-derives nothing."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(ProviderDataOutcome.ok,
                                     entries=(ProviderDataEntry("google.com", "google-uid-1"),),
                                     email="someone@example.test", email_verified=True)

        response = _complete(client)

        assert response.status_code == 200
        assert response.json() == {"identity_provider": "google"}
        assert len(creator.calls) == 1
        assert creator.calls[0]["provider"] is IdentityProvider.google
        assert creator.calls[0]["provider_uid"] == "google-uid-1"
        assert creator.calls[0]["email"] == "someone@example.test"


class TestEveryProviderStageRejectionConsumes:
    """§02 step 13: every rejection at or after the Admin lookup consumes, so a retry needs a fresh
    prepare (T-37-39). The audit row rides in the SAME transaction as the consumption, which is why
    it is written in-transaction rather than standalone."""

    @pytest.mark.parametrize("outcome,entries", [
        (ProviderDataOutcome.user_not_found, ()),
        (ProviderDataOutcome.retryable_failure, ()),
        (ProviderDataOutcome.selection_failure, ()),
        (ProviderDataOutcome.ok, (ProviderDataEntry("password", "someone@example.test"),)),
    ])
    def test_the_challenge_is_consumed_and_its_binding_cleared(
            self, client, store, writer, context, keyring, fake_firebase_adapter,
            outcome, entries):
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(outcome, entries=entries)

        _complete(client)

        assert store.row.consumed_at is not None
        # Cleared in the same state transition -- which is why a later presentation of the same
        # handle takes the already-used rejection rather than a mismatch.
        assert store.row.preauth_subject_hash is None
        assert writer.rows[0][0] == "in_transaction"
        assert len(writer.rows) == 1

    def test_a_replay_after_a_rejection_is_challenge_required_and_mints_nothing(
            self, client, store, writer, context, keyring, creator, fake_firebase_adapter):
        """There is no idempotent replay and no `challenge_replayed` result (§02 DELETIONS)."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(ProviderDataOutcome.user_not_found)

        first = _complete(client)
        second = _complete(client)

        assert first.status_code == 401
        _assert_challenge_required(second)
        assert writer.results == [AuthEventResult.firebase_user_unresolved,
                                  AuthEventResult.challenge_consumed]
        assert creator.calls == []
        # The second attempt performs no work at all: the provider was not read a second time.
        assert len(fake_firebase_adapter.calls) == 1


class TestThePrecedenceItself:
    """§02 line 52: "numbered order is normative rejection precedence -- reject for the earliest
    failed step".

    **Precedence is a property of the ordering, not of any single branch**, so reading the handler
    top to bottom proves nothing: every case below makes *two* things wrong at once and asserts
    which one is reported. A reordering that a per-branch suite would wave through fails here.
    """

    def test_an_unknown_handle_beats_a_failing_provider(
            self, client, store, writer, creator, fake_firebase_adapter):
        """3 beats 8. The adapter is scripted to fail and is never asked."""
        store.row = None
        fake_firebase_adapter.script(ProviderDataOutcome.retryable_failure)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_not_found]
        assert fake_firebase_adapter.calls == []
        assert creator.calls == []

    def test_an_identity_mismatch_beats_an_expired_row(
            self, client, store, writer, context, keyring, fake_firebase_adapter):
        """4 beats 5 -- and this ordering is load-bearing rather than cosmetic.

        If the claim ran first, an expired row bound to somebody else would audit
        `challenge_expired` and, worse, a *live* row bound to somebody else would be claimed by the
        wrong presenter. The pre-claim placement is what makes T-37-35 structural.
        """
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT, ttl_seconds=-1)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_identity_mismatch]
        assert store.row.claimed_at is None
        assert fake_firebase_adapter.calls == []

    def test_the_identity_binding_is_checked_before_the_operation(
            self, client, store, writer, context, keyring):
        """§02 step 4 names both checks and orders neither, so this pins the choice.

        The binding runs first, matching the order the sentence itself uses ("verify binding ...;
        operation must be `create_user`") and matching `ChallengeStore.verify_binding` owning the
        comparison the step is named for. Both are pre-claim rejections collapsing to the same
        client class, so the choice is observable only in the audit row -- which is exactly why it
        needs to be a decision on the record rather than an accident of line order.
        """
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT,
                                operation=AuthOperation.claim_anonymous_grant)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_identity_mismatch]

    def test_an_expired_row_beats_a_failing_provider(
            self, client, store, writer, context, keyring, creator, fake_firebase_adapter):
        """5 beats 8. The claim loser performs no work at all."""
        store.row = _issued_row(context, keyring, ttl_seconds=-1)
        fake_firebase_adapter.script(ProviderDataOutcome.user_not_found)

        _assert_challenge_required(_complete(client))

        assert writer.results == [AuthEventResult.challenge_expired]
        assert fake_firebase_adapter.calls == []
        assert creator.calls == []

    def test_a_failed_lookup_beats_a_rejecting_shape(
            self, client, store, writer, context, keyring, creator, fake_firebase_adapter):
        """8 beats 9: the classifier is never reached.

        The scripted result carries entries the classifier would reject, so a handler that
        classified before checking the outcome would answer 403 `operation_not_allowed` -- terminal,
        routed to support -- to a caller whose token simply no longer identifies a Firebase user.
        """
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(
            ProviderDataOutcome.user_not_found,
            entries=(ProviderDataEntry("password", "someone@example.test"),))

        response = _complete(client)

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
        assert writer.results == [AuthEventResult.firebase_user_unresolved]
        assert creator.calls == []
