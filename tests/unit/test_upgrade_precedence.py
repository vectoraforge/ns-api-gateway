"""The upgrade completion: the case matrix over the stored row and the live read, and what each branch spends."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_devicecheck_adapter,
    get_firebase_adapter,
    get_identity,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import AppError, ProviderAccountAlreadyLinked, UserNotFound
from nativespeaker.api.routers import auth_router
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User

from .conftest import TEST_ISSUER

SUBJECT = "upgrade-precedence-subject"
HANDLE = "a-scripted-upgrade-handle"

# What the stored row carries once a case makes it registered, and what the live read reports.
STORED_UID = "google-uid-stored"
LIVE_UID = "google-uid-live"
VERIFIED_EMAIL = "upgraded@example.test"


class _FakeChallengeStore:
    """One in-memory row whose `claim` and `consume` mirror the real conditional updates clause for clause."""

    def __init__(self) -> None:
        self._binding = ChallengesDB()
        self.row: AuthChallenge | None = None
        self.consume_calls = 0

    async def locate(self, session, challenge_id: str) -> AuthChallenge | None:
        if self.row is not None and self.row.challenge_id == challenge_id:
            return self.row
        return None

    def verify_binding(self, row, identity):
        return self._binding.verify_binding(row, identity)

    async def claim(self, session, *, challenge_id, now) -> bool:
        row = self.row
        if row is None or row.challenge_id != challenge_id:
            return False
        if row.claimed_at is not None or row.expires_at <= now:
            return False
        row.claimed_at = now
        return True

    async def consume(self, session, *, challenge_id, now) -> bool:
        self.consume_calls += 1
        row = self.row
        if row is None or row.challenge_id != challenge_id:
            return False
        if row.claimed_at is None or row.consumed_at is not None:
            return False
        row.consumed_at = now
        row.preauth_subject = None
        return True


class _RejectionLog:
    """The rejections this request logged, in order, from a spy on each logger one can come from.

    Every logger feeds one list, so a rejection re-logged anywhere appears here as a second entry.
    """

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **kwargs) -> None:
        self.entries.append((event, kwargs))

    @property
    def results(self) -> list[str]:
        """One string per rejection. The class name, snake_cased, is the outcome vocabulary (D-05)."""
        return [event for event, _ in self.entries]


class _StubSession:
    """Records transaction boundaries and refuses queries: a statement here would mean the write ran unstubbed."""

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


class _RecordingUpgrade:
    """Stands in for the two crud calls the upgrade write makes, recording the lock and the flip."""

    def __init__(self, identity_row: ExternalIdentity, user: User) -> None:
        self.identity_row = identity_row
        self.user = user
        self.locks = 0
        self.flips: list[dict] = []
        # What the partial unique index's breach looks like from the service: raised by the flip, never before it.
        self.conflict: AppError | None = None

    async def lock(self, *, issuer: str, subject: str) -> tuple[ExternalIdentity, User]:
        self.locks += 1
        return self.identity_row, self.user

    async def flip(self, *, evaluated_at, identity_row, user, provider, provider_uid,
                   email) -> IdentityProvider:
        self.flips.append({"provider": provider, "provider_uid": provider_uid, "email": email})
        if self.conflict is not None:
            raise self.conflict
        identity_row.provider = provider
        identity_row.provider_uid = provider_uid
        user.registered_at = evaluated_at
        return provider


@pytest.fixture
def store() -> _FakeChallengeStore:
    return _FakeChallengeStore()


@pytest.fixture
def rejections(monkeypatch) -> _RejectionLog:
    """Spy on every logger a rejection can come from, so one logged at the wrong site is still seen."""
    log = _RejectionLog()
    monkeypatch.setattr("nativespeaker.api.routers.auth.logger.warning", log.record)
    monkeypatch.setattr("nativespeaker.api.services.auth.logger.warning", log.record)
    monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger.warning", log.record)
    return log


@pytest.fixture
def session() -> _StubSession:
    return _StubSession()


@pytest.fixture
def account() -> tuple[ExternalIdentity, User]:
    """The caller's stored rows, anonymous until a case registers them; the objects the lock returns."""
    user = User(id=uuid4())
    identity_row = ExternalIdentity(user_id=user.id,
                                    issuer=TEST_ISSUER,
                                    subject=SUBJECT,
                                    provider=IdentityProvider.anonymous,
                                    provider_uid=None)
    return identity_row, user


@pytest.fixture
def identity(account) -> Identity:
    """A linked caller: the upgrade route narrows to one, unlike create-user's pre-auth identity."""
    identity_row, user = account
    return Identity(issuer=TEST_ISSUER, subject=SUBJECT, user=user, identity=identity_row)


@pytest.fixture
def upgrade(account, monkeypatch) -> _RecordingUpgrade:
    """Both crud calls replaced by recorders, so `_apply_upgrade`'s own matrix is what a case exercises."""
    recorder = _RecordingUpgrade(*account)
    monkeypatch.setattr(IdentitiesDB, "lock_identity_and_user", recorder.lock)
    monkeypatch.setattr(IdentitiesDB, "flip_provider", recorder.flip)
    return recorder


@pytest.fixture
def client(store, session, identity, upgrade, fake_firebase_adapter):
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_identity] = lambda: identity
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
    # Declared by `get_auth_service` for every auth route; this app has no lifespan to build one.
    app.dependency_overrides[get_devicecheck_adapter] = lambda: None

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _issued_row(*,
                bound_to: UUID | None,
                operation: AuthOperation = AuthOperation.upgrade_anonymous_to_registered,
                ttl_seconds: int = 300,
                claimed: bool = False,
                consumed: bool = False) -> AuthChallenge:
    """An identity-bound challenge row in whichever lifecycle state the case needs."""
    now = datetime.now(UTC)
    row = AuthChallenge(
        challenge_id=HANDLE,
        operation=operation,
        # A linked caller's handle binds to the identity row id, which is what the real issuance does.
        bound_external_identity_id=bound_to,
        expires_at=now + timedelta(seconds=ttl_seconds),
        created_at=now,
    )
    if claimed or consumed:
        row.claimed_at = now
    if consumed:
        row.consumed_at = now
    return row


def _complete(client, handle: str = HANDLE):
    return client.post("/auth/upgrade-anonymous", json={"challenge_id": handle})


def _register(identity_row: ExternalIdentity,
              provider: IdentityProvider = IdentityProvider.google,
              provider_uid: str = STORED_UID) -> None:
    """Make the stored row registered, which is the half of the matrix the flip may not touch."""
    identity_row.provider = provider
    identity_row.provider_uid = provider_uid


def _live(provider: IdentityProvider = IdentityProvider.google,
          provider_uid: str | None = LIVE_UID) -> VerifiedProviderIdentity:
    return VerifiedProviderIdentity(provider=provider, provider_uid=provider_uid,
                                    email=VERIFIED_EMAIL)


def _assert_operation_not_allowed(response) -> None:
    """Byte-identical across all three refusals, asserted by equality so a more helpful field fails here."""
    assert response.status_code == 403
    assert response.json() == {"code": "operation_not_allowed"}


def _assert_challenge_required(response) -> None:
    """Byte-identical across every rejection that spends nothing, and asserted the same way."""
    assert response.status_code == 409
    assert response.json() == {"code": "challenge_required"}


class TestTheUpgradeCaseMatrix:
    """Every combination of the stored row and the live read reaches a named outcome, and none falls through."""

    def test_a_live_anonymous_read_against_a_stored_anonymous_row_is_not_linked(
            self, client, store, rejections, upgrade, account, fake_firebase_adapter):
        """The client called before its own linking finished: recoverable, and told apart only in the log."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live(provider=IdentityProvider.anonymous, provider_uid=None))

        _assert_operation_not_allowed(_complete(client))

        assert rejections.results == ["not_linked"]
        # The first producer of this cause in the tree, at a stage naming the confirmation, not the classifier.
        assert rejections.entries[0][1]["stage"] == "upgrade_confirmation"
        assert rejections.entries[0][1]["cause"] == "empty"
        assert upgrade.flips == []
        assert identity_row.provider is IdentityProvider.anonymous
        assert identity_row.provider_uid is None

    def test_the_same_provider_and_the_same_uid_is_the_idempotent_repeat(
            self, client, store, upgrade, account, fake_firebase_adapter):
        """D-04: the repeat that changed nothing answers exactly as the call that performed the flip."""
        identity_row, _ = account
        _register(identity_row)
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live(provider_uid=STORED_UID))

        response = _complete(client)

        assert response.status_code == 200
        assert response.json() == {"identity_provider": "google"}
        # No write at all: the stored provider is returned, not the read's.
        assert upgrade.flips == []
        assert len(fake_firebase_adapter.calls) == 1

    def test_the_same_provider_with_a_different_uid_is_a_transition_refusal(
            self, client, store, rejections, upgrade, account, fake_firebase_adapter):
        """The binding diverged: the stored uid is refused, never rewritten to the live one."""
        identity_row, _ = account
        _register(identity_row)
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live(provider_uid=LIVE_UID))

        _assert_operation_not_allowed(_complete(client))

        assert rejections.results == ["provider_transition_not_allowed"]
        assert upgrade.flips == []
        assert identity_row.provider_uid == STORED_UID

    def test_a_different_live_provider_is_a_transition_refusal(
            self, client, store, rejections, upgrade, account, fake_firebase_adapter):
        identity_row, _ = account
        _register(identity_row)
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live(provider=IdentityProvider.apple, provider_uid="apple-uid-live"))

        _assert_operation_not_allowed(_complete(client))

        assert rejections.results == ["provider_transition_not_allowed"]
        assert rejections.entries[0][1]["stored_provider"] == "google"
        assert rejections.entries[0][1]["live_provider"] == "apple"
        assert upgrade.flips == []
        assert identity_row.provider is IdentityProvider.google

    def test_a_registered_row_does_not_un_register(
            self, client, store, rejections, upgrade, account, fake_firebase_adapter):
        """A live anonymous read against a registered row is drift, never a downgrade."""
        identity_row, _ = account
        _register(identity_row)
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live(provider=IdentityProvider.anonymous, provider_uid=None))

        _assert_operation_not_allowed(_complete(client))

        assert rejections.results == ["provider_transition_not_allowed"]
        assert upgrade.flips == []
        assert identity_row.provider is IdentityProvider.google
        assert identity_row.provider_uid == STORED_UID

    def test_a_target_triple_another_row_holds_is_raised_by_the_write(
            self, client, store, rejections, upgrade, account, fake_firebase_adapter):
        """Found by catching the database's refusal: the flip was attempted, so no pre-flight lookup decided it."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        upgrade.conflict = ProviderAccountAlreadyLinked(identity_row_id=identity_row.id,
                                                        stored_provider=IdentityProvider.anonymous,
                                                        live_provider=IdentityProvider.google)
        fake_firebase_adapter.script(_live())

        _assert_operation_not_allowed(_complete(client))

        assert rejections.results == ["provider_account_already_linked"]
        # One flip attempt is what proves the conflict came from the write arm rather than a pre-check.
        assert len(upgrade.flips) == 1

    def test_the_three_refusals_are_three_log_events_and_one_client_answer(
            self, client, store, rejections, upgrade, account, fake_firebase_adapter):
        """The control: distinguishable refusals would let a token holder probe which accounts are held."""
        identity_row, _ = account
        bodies = []
        for setup in (_not_linked_case, _drift_case, _already_linked_case):
            setup(store, upgrade, account, fake_firebase_adapter)
            response = _complete(client)
            assert response.status_code == 403
            bodies.append(response.json())

        assert bodies == [{"code": "operation_not_allowed"}] * 3
        assert rejections.results == ["not_linked",
                                      "provider_transition_not_allowed",
                                      "provider_account_already_linked"]
        assert identity_row.id is not None


def _not_linked_case(store, upgrade, account, adapter) -> None:
    identity_row, _ = account
    identity_row.provider = IdentityProvider.anonymous
    identity_row.provider_uid = None
    upgrade.conflict = None
    store.row = _issued_row(bound_to=identity_row.id)
    adapter.script(_live(provider=IdentityProvider.anonymous, provider_uid=None))


def _drift_case(store, upgrade, account, adapter) -> None:
    identity_row, _ = account
    _register(identity_row)
    upgrade.conflict = None
    store.row = _issued_row(bound_to=identity_row.id)
    adapter.script(_live(provider_uid=LIVE_UID))


def _already_linked_case(store, upgrade, account, adapter) -> None:
    identity_row, _ = account
    identity_row.provider = IdentityProvider.anonymous
    identity_row.provider_uid = None
    store.row = _issued_row(bound_to=identity_row.id)
    upgrade.conflict = ProviderAccountAlreadyLinked(identity_row_id=identity_row.id,
                                                    stored_provider=IdentityProvider.anonymous,
                                                    live_provider=IdentityProvider.google)
    adapter.script(_live())


class TestTheRejectionsThatSpendNothing:
    """One client class, five internal results, and not one of them claims, consumes or reads the provider."""

    def test_an_unknown_handle_is_challenge_not_found(self, client, store, rejections,
                                                      fake_firebase_adapter):
        store.row = None

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_not_found"]
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_a_handle_bound_to_another_identity_row_is_an_identity_mismatch(
            self, client, store, rejections, fake_firebase_adapter):
        """A linked caller's handle binds to a row id, so a mismatch is a comparison against that id."""
        store.row = _issued_row(bound_to=uuid4())

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_identity_mismatch"]
        # Rejected BEFORE the claim: the rightful owner's row is untouched.
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_a_handle_issued_for_another_operation_is_an_operation_mismatch(
            self, client, store, rejections, account, fake_firebase_adapter):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id, operation=AuthOperation.create_user)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_operation_mismatch"]
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_an_expired_handle_is_challenge_expired(self, client, store, rejections, account,
                                                    fake_firebase_adapter):
        """Reached by losing the claim and re-reading the row, never by comparing `expires_at` in the router."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id, ttl_seconds=-1)

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_expired"]
        assert store.row.claimed_at is None
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_an_already_consumed_handle_is_challenge_consumed(self, client, store, rejections,
                                                              account, fake_firebase_adapter):
        """The claim loser does no work: there is no idempotent replay of a spent handle."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id, claimed=True, consumed=True)
        holder = store.row.claimed_at

        _assert_challenge_required(_complete(client))

        assert rejections.results == ["challenge_consumed"]
        assert store.row.claimed_at == holder
        assert store.consume_calls == 0
        assert fake_firebase_adapter.calls == []

    def test_all_five_answer_one_body_and_never_name_the_handle(self, client, store, rejections,
                                                                account):
        """The control: a more helpful field on any one of them fails here, and the handle is never logged."""
        identity_row, _ = account
        bodies = []
        for row in (None,
                    _issued_row(bound_to=uuid4()),
                    _issued_row(bound_to=identity_row.id, operation=AuthOperation.create_user),
                    _issued_row(bound_to=identity_row.id, ttl_seconds=-1),
                    _issued_row(bound_to=identity_row.id, claimed=True, consumed=True)):
            store.row = row
            bodies.append(_complete(client).json())

        assert bodies == [{"code": "challenge_required"}] * 5
        assert len(rejections.results) == 5
        assert HANDLE not in repr(rejections.entries)


class TestEveryOutcomeAtOrAfterTheProviderCallSpends:
    """D-14: once the provider was called the handle is spent, with no branch on which outcome fired."""

    def test_a_deleted_provider_user_is_auth_required_and_still_consumes(
            self, client, store, rejections, upgrade, account, fake_firebase_adapter):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(UserNotFound(stage="provider_lookup"))

        response = _complete(client)

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
        assert rejections.results == ["user_not_found"]
        assert store.row.consumed_at is not None
        assert store.consume_calls == 1
        assert upgrade.flips == []

    def test_the_not_linked_refusal_still_consumes(self, client, store, rejections, upgrade,
                                                   account, fake_firebase_adapter):
        """The case D-14 names explicitly: recoverable, and still spent, so it cannot probe provider state."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live(provider=IdentityProvider.anonymous, provider_uid=None))

        _assert_operation_not_allowed(_complete(client))

        assert rejections.results == ["not_linked"]
        assert store.row.consumed_at is not None
        assert store.consume_calls == 1
        assert upgrade.flips == []

    def test_the_successful_flip_consumes_exactly_once(self, client, store, rejections, upgrade,
                                                       account, fake_firebase_adapter):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live())

        response = _complete(client)

        assert response.status_code == 200
        assert response.json() == {"identity_provider": "google"}
        assert rejections.results == []
        assert store.row.consumed_at is not None
        assert store.consume_calls == 1
        assert len(upgrade.flips) == 1


class TestOneProviderReadPerCompletion:
    """D-22: the read is never skipped as an optimisation, because it is what detects a diverged binding."""

    def test_the_repeat_that_changes_nothing_still_reads(self, client, store, upgrade, account,
                                                         fake_firebase_adapter):
        identity_row, _ = account
        _register(identity_row)
        store.row = _issued_row(bound_to=identity_row.id)
        fake_firebase_adapter.script(_live(provider_uid=STORED_UID))

        response = _complete(client)

        assert response.status_code == 200
        # One entry for a completion that wrote nothing: the already-registered row was read anyway.
        assert fake_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)]
        assert upgrade.flips == []

    def test_two_completions_read_twice(self, client, store, upgrade, account,
                                        fake_firebase_adapter):
        """The flip then its repeat: one read per completion rather than one read in total."""
        identity_row, _ = account
        fake_firebase_adapter.script(_live())

        store.row = _issued_row(bound_to=identity_row.id)
        first = _complete(client)
        store.row = _issued_row(bound_to=identity_row.id)
        second = _complete(client)

        assert (first.status_code, second.status_code) == (200, 200)
        assert first.json() == second.json() == {"identity_provider": "google"}
        assert fake_firebase_adapter.calls == [(TEST_ISSUER, SUBJECT)] * 2
        # The second completion wrote nothing: the first flip is what left the row registered.
        assert len(upgrade.flips) == 1
