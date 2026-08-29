"""Completion rejection precedence: each arm asserts the client class, the internal result logged, and consumption."""
import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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
from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.auth.firebase import FIREBASE_LOOKUP_ATTEMPTS, RetryableLookupError
from nativespeaker.api.auth.hmac_keyring import HmacKeyring
from nativespeaker.api.config import HmacConfig
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import (
    AppError,
    IdentityAlreadyLinked,
    NotLinked,
    Unavailable,
    UserNotFound,
)
from nativespeaker.api.routers import auth_router
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.identities import IdentityProvider

from .conftest import TEST_ISSUER

SUBJECT = "precedence-unlinked-subject"
OTHER_SUBJECT = "precedence-somebody-else"
OTHER_ISSUER = "https://securetoken.google.com/some-other-project"
HANDLE = "a-scripted-handle"

CREATE_USER_ROUTE = "/auth/create-user"


def _material(seed: int) -> str:
    return base64.b64encode(bytes((seed * 37 + i) % 256 for i in range(32))).decode()


class _SpyKeyring:
    """The real derivation with the one comparison counted, since not-compared is what the cleared-hash arm asserts."""

    def __init__(self) -> None:
        self._ring = HmacKeyring(HmacConfig(active_version=1, keys={1: _material(1)}))
        self.comparisons = 0

    def actor_subject_hash(self, issuer: str, subject: str, *, version: int | None = None) -> bytes:
        return self._ring.actor_subject_hash(issuer, subject, version=version)

    def actor_subject_matches(self, stored: bytes, issuer: str, subject: str) -> bool:
        self.comparisons += 1
        return self._ring.actor_subject_matches(stored, issuer, subject)


class _FakeChallengeStore:
    """One in-memory row whose `claim` and `consume` mirror the real conditional updates clause for clause."""

    def __init__(self, keyring: _SpyKeyring) -> None:
        self._binding = ChallengesDB(keyring)
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


class _RejectionLog:
    """The rejections this request logged, in order, from a spy on each logger one can come from.

    The migration this recorder was built to span is finished: every rejection below is now recorded
    by the exception handler, and the router records none. Both loggers stay spied anyway, and both
    feed one list -- that is what makes "only the handler records a rejection" a tested property
    rather than an assumption, since a rejection re-logged at the router would appear here as a
    second entry and fail the exactly-once cases.
    """

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **kwargs) -> None:
        self.entries.append((event, kwargs))

    @property
    def results(self) -> list[str]:
        """One string per rejection. The class name, snake_cased, is the outcome vocabulary (D-02)."""
        return [event for event, _ in self.entries]


class _StubSession:
    """Records transaction boundaries and refuses queries: a statement here would mean the router resolves identity."""

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
    """Stands in for `auth/create_user.py::create_account` and records the facts handed to it."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        # The new user's id on success; a scripted rejection is raised instead, as the real one does.
        self.result = uuid4()
        self.rejection: AppError | None = None

    async def __call__(self, session, **kwargs) -> UUID:
        self.calls.append(kwargs)
        if self.rejection is not None:
            raise self.rejection
        return self.result


@pytest.fixture
def keyring() -> _SpyKeyring:
    return _SpyKeyring()


@pytest.fixture
def store(keyring) -> _FakeChallengeStore:
    return _FakeChallengeStore(keyring)


@pytest.fixture
def rejections(monkeypatch) -> _RejectionLog:
    """Spy on both loggers a rejection can come from, so one logged at the wrong site is still seen."""
    log = _RejectionLog()
    monkeypatch.setattr("nativespeaker.api.routers.auth.logger.warning", log.record)
    monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger.warning", log.record)
    return log


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
        route=CREATE_USER_ROUTE,
        evaluated_at=datetime.now(UTC),
        attempt_id=uuid4(),
    )


@pytest.fixture
def client(store, session, context, creator, fake_firebase_adapter):
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

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
    """Byte-identical across all five rejections, asserted by equality so a more helpful field fails here."""
    assert response.status_code == 409
    assert response.json() == {"code": "challenge_required"}


class TestTheFiveChallengeRejections:
    """One client class, five internal results, and none of the five consumes."""

    def test_an_unknown_handle_is_challenge_not_found(self, client, store, rejections,
                                                      fake_firebase_adapter):
        store.row = None

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_not_found"]
        assert fake_firebase_adapter.calls == []

    def test_a_challenge_bound_to_another_subject_is_an_identity_mismatch(
            self, client, store, rejections, context, keyring, fake_firebase_adapter):
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_identity_mismatch"]
        # Rejected BEFORE the claim: the rightful owner's row is untouched.
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_a_challenge_bound_to_another_issuer_is_an_identity_mismatch(
            self, client, store, rejections, context, keyring, fake_firebase_adapter):
        store.row = _issued_row(context, keyring, issuer=OTHER_ISSUER)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_identity_mismatch"]
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert fake_firebase_adapter.calls == []

    def test_a_challenge_for_another_operation_is_an_operation_mismatch(
            self, client, store, rejections, context, keyring, fake_firebase_adapter):
        """A challenge issued for another operation is still rejected, and still before the claim."""
        store.row = _issued_row(context, keyring,
                                operation=AuthOperation.claim_anonymous_grant)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_operation_mismatch"]
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_a_cleared_binding_hash_is_already_used_and_is_never_compared(
            self, client, store, rejections, context, keyring, fake_firebase_adapter):
        store.row = _issued_row(context, keyring, claimed=True, consumed=True, cleared_hash=True)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_consumed"]
        # The whole point of the cleared-hash arm: the comparison is skipped entirely.
        assert keyring.comparisons == 0
        assert fake_firebase_adapter.calls == []

    def test_a_still_issued_but_expired_challenge_is_challenge_expired(
            self, client, store, rejections, context, keyring, fake_firebase_adapter):
        """Reached by losing the claim and re-reading the row, never by comparing `expires_at` in the router."""
        store.row = _issued_row(context, keyring, ttl_seconds=-1)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_expired"]
        assert store.row.claimed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_an_already_claimed_challenge_is_challenge_consumed(
            self, client, store, rejections, context, keyring, fake_firebase_adapter):
        """The claim loser does no work and never receives the claim-holder's outcome; there is no idempotent replay."""
        store.row = _issued_row(context, keyring, claimed=True)
        holder = store.row.claim_attempt_id

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_consumed"]
        # The holder's claim is untouched, and the loser consumed nothing.
        assert store.row.claim_attempt_id == holder
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_every_rejection_is_recorded_exactly_once_and_never_names_the_handle(
            self, client, store, rejections, context, keyring):
        """One record per rejection is as much the contract as which one, and the handle is never in it."""
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT)

        _complete(client)

        assert len(rejections.results) == 1
        assert HANDLE not in repr(rejections.entries)


class TestTheProviderStageRejections:
    """Three outcomes, three client classes, all consuming; collapsing any pair is a bug clients cannot detect."""

    def test_user_not_found_is_auth_required_and_persists_nothing(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """A valid token for a deleted provider user must not create an account."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(UserNotFound(stage="provider_lookup"))

        response = _complete(client)

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
        assert rejections.results == ["user_not_found"]
        assert rejections.entries[0][1]["stage"] == "provider_lookup"
        # Definitive and non-retryable: it spends no further attempt.
        assert len(fake_firebase_adapter.calls) == 1
        assert creator.calls == []

    def test_an_exhausted_retry_budget_is_verification_temporarily_unavailable(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """The call count proves the retry predicate is wired: a mismatched one would allow a single attempt."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(RetryableLookupError("the provider is unreachable"))

        response = _complete(client)

        assert response.status_code == 503
        assert response.json() == {"code": "verification_temporarily_unavailable"}
        assert rejections.results == ["unavailable"]
        assert rejections.entries[0][1]["stage"] == "provider_lookup"
        assert len(fake_firebase_adapter.calls) == FIREBASE_LOOKUP_ATTEMPTS == 3
        assert creator.calls == []

    def test_a_selection_failure_is_unavailable_on_its_first_attempt(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """An issuer mismatch fails closed rather than falling back, so it is definitive and spends one attempt."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(Unavailable(stage="issuer_selection"))

        response = _complete(client)

        assert response.status_code == 503
        assert response.json() == {"code": "verification_temporarily_unavailable"}
        assert rejections.results == ["unavailable"]
        # The same class as an exhausted budget, told apart in the log by its stage and nowhere else.
        assert rejections.entries[0][1]["stage"] == "issuer_selection"
        assert len(fake_firebase_adapter.calls) == 1
        assert creator.calls == []

    def test_a_rejecting_provider_data_shape_is_operation_not_allowed(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """Which shapes reject is now decided behind the seam, so the shape table lives at adapter
        level in `test_firebase_adapter.py`. What this layer still owns is the answer the rejection
        earns: a terminal class whose body names no shape, and no attempt at the transaction."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(NotLinked(stage="provider_classification",
                                               cause="invalid-shape"))

        response = _complete(client)

        assert response.status_code == 403
        assert response.json() == {"code": "operation_not_allowed"}
        assert rejections.results == ["not_linked"]
        assert rejections.entries[0][1]["stage"] == "provider_classification"
        # The bounded cause reaches the security log and never the response.
        assert rejections.entries[0][1]["cause"] == "invalid-shape"
        assert len(fake_firebase_adapter.calls) == 1
        assert creator.calls == []

    def test_one_recognized_entry_with_a_uid_reaches_the_consuming_transaction(
            self, client, store, context, keyring, creator, fake_firebase_adapter):
        """The classifier's verdict is carried through unchanged; the router re-derives nothing."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(VerifiedProviderIdentity(provider=IdentityProvider.google,
                                                              provider_uid="google-uid-1",
                                                              email="someone@example.test"))

        response = _complete(client)

        assert response.status_code == 200
        assert response.json() == {"identity_provider": "google"}
        assert len(creator.calls) == 1
        assert creator.calls[0]["provider"] is IdentityProvider.google
        assert creator.calls[0]["provider_uid"] == "google-uid-1"
        assert creator.calls[0]["email"] == "someone@example.test"


class TestEveryProviderStageRejectionConsumes:
    """Every rejection at or after the provider lookup consumes, so a retry needs a fresh prepare."""

    @pytest.mark.parametrize("rejection", [
        UserNotFound(stage="provider_lookup"),
        RetryableLookupError("the provider is unreachable"),
        Unavailable(stage="issuer_selection"),
        NotLinked(stage="provider_classification", cause="invalid-shape"),
    ], ids=["user_not_found", "exhausted_budget", "issuer_selection", "not_linked"])
    def test_the_challenge_is_consumed_and_its_binding_cleared(
            self, client, store, context, keyring, fake_firebase_adapter, rejection):
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(rejection)

        _complete(client)

        assert store.row.consumed_at is not None
        # Cleared in the same transition, which is why a later presentation takes the already-used rejection.
        assert store.row.preauth_subject_hash is None

    def test_a_replay_after_a_rejection_is_challenge_required_and_mints_nothing(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """There is no idempotent replay and no `challenge_replayed` result."""
        store.row = _issued_row(context, keyring)
        fake_firebase_adapter.script(UserNotFound(stage="provider_lookup"))

        first = _complete(client)
        second = _complete(client)

        assert first.status_code == 401
        _assert_challenge_required(second)
        assert rejections.results == ["user_not_found",
                                      "challenge_consumed"]
        assert creator.calls == []
        # The second attempt performs no work at all: the provider was not read a second time.
        assert len(fake_firebase_adapter.calls) == 1


class TestThePrecedenceItself:
    """Precedence is a property of the ordering, so every case makes two things wrong and asserts which is reported."""

    def test_an_unknown_handle_beats_a_failing_provider(
            self, client, store, rejections, creator, fake_firebase_adapter):
        """3 beats 8. The adapter is scripted to fail and is never asked."""
        store.row = None
        fake_firebase_adapter.script(RetryableLookupError("the provider is unreachable"))

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_not_found"]
        assert fake_firebase_adapter.calls == []
        assert creator.calls == []

    def test_an_identity_mismatch_beats_an_expired_row(
            self, client, store, rejections, context, keyring, fake_firebase_adapter):
        """Were the claim first, a live row bound to somebody else would be claimed by the wrong presenter."""
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT, ttl_seconds=-1)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_identity_mismatch"]
        assert store.row.claimed_at is None
        assert fake_firebase_adapter.calls == []

    def test_the_identity_binding_is_checked_before_the_operation(
            self, client, store, rejections, context, keyring):
        """Both are pre-claim rejections collapsing to one client class, so the order shows only in the log."""
        store.row = _issued_row(context, keyring, subject=OTHER_SUBJECT,
                                operation=AuthOperation.claim_anonymous_grant)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_identity_mismatch"]

    def test_an_expired_row_beats_a_failing_provider(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """5 beats 8. The claim loser performs no work at all."""
        store.row = _issued_row(context, keyring, ttl_seconds=-1)
        fake_firebase_adapter.script(UserNotFound(stage="provider_lookup"))

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_expired"]
        assert fake_firebase_adapter.calls == []
        assert creator.calls == []

    # `a failed lookup beats a rejecting shape` is no longer expressible here: the seam admits one
    # answer per call, because the read now decides the lookup before it ever classifies. The case
    # moved to `test_firebase_adapter.py`, where both facts can still be set up at once -- a
    # not-found `get_user` on a record whose providerData would reject.


class TestTheTransactionRejectionIsObservedAtTheHandler:
    """The arm this plan migrated: `create_account` raises, and the record is written at the handler."""

    @staticmethod
    def _reaching_the_transaction(store, context, keyring, creator, adapter) -> None:
        """Get past every earlier rejection, then have the transaction reject the way the real one does."""
        store.row = _issued_row(context, keyring)
        adapter.script(VerifiedProviderIdentity(provider=IdentityProvider.google,
                                                provider_uid="google-uid-1"))
        creator.rejection = IdentityAlreadyLinked()

    def test_it_is_recorded_once_under_its_class_derived_event_name(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """Sourced from the handler's logger rather than the router's -- the migration this fixture spans."""
        self._reaching_the_transaction(store, context, keyring, creator, fake_firebase_adapter)

        _complete(client)

        assert rejections.results == ["identity_already_linked"]
        assert len(creator.calls) == 1

    def test_it_consumes_the_challenge_exactly_once_before_the_client_is_answered(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """D-04: the route's except arm spends the handle, and `create_account` no longer also does."""
        self._reaching_the_transaction(store, context, keyring, creator, fake_firebase_adapter)

        _complete(client)

        assert store.consume_calls == 1
        assert store.row.consumed_at is not None
        # Cleared in the same transition, which is why a replay takes the already-used rejection.
        assert store.row.preauth_subject_hash is None

    def test_a_replay_after_it_is_rejected_and_never_reaches_the_transaction_again(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """There is no idempotent replay: the second presentation is a spent handle, not a repeat answer."""
        self._reaching_the_transaction(store, context, keyring, creator, fake_firebase_adapter)

        _complete(client)
        _complete(client)

        assert rejections.results == ["identity_already_linked",
                                      "challenge_consumed"]
        assert len(creator.calls) == 1

    def test_the_handle_never_reaches_either_log(
            self, client, store, rejections, context, keyring, creator, fake_firebase_adapter):
        """The handle is a secret, and moving the record to a new logging site does not relax that."""
        self._reaching_the_transaction(store, context, keyring, creator, fake_firebase_adapter)

        _complete(client)

        assert HANDLE not in repr(rejections.entries)
