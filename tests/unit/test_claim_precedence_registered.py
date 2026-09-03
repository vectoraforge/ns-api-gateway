"""The registered claim completion: its rejection precedence, and what each branch spends.
Every post-claim outcome consumes the handle exactly once, and no pre-claim rejection consumes.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_db,
    get_devicecheck_adapter,
    get_firebase_adapter,
    get_identity,
    get_sync_service,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.devicecheck import BitState, RetryableDeviceCheckError
from nativespeaker.api.crud.grants import ActivationOutcome, GrantsDB
from nativespeaker.api.errors import ProofRejected
from nativespeaker.api.routers import auth_router
from nativespeaker.api.schemas.auth import (
    Entitlement,
    EntitlementStatus,
    EntitlementType,
    Identity,
)
from nativespeaker.api.tables.auth import AuthOperation
from nativespeaker.api.tables.grants import AccessGrantSource
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User

from .conftest import TEST_ISSUER

# The scaffolding is imported rather than copied: two drifting fakes of one conditional update is the hazard.
from .test_claim_precedence import (
    CHALLENGE_REQUIRED,
    HANDLE,
    REFUSED,
    _a_grant,
    _FakeChallengeStore,
    _issued_row,
    _RecordingGrants,
    _ScriptedDeviceCheck,
    _StubSession,
    _StubSync,
)

SUBJECT = "claim-precedence-registered-subject"

# One obviously synthetic token, naming the one device; it resembles no real device token.
DEVICE_TOKEN = "a-synthetic-registered-device-token"

DEVICE_EXHAUSTED = {"code": "device_grant_exhausted"}
PROOF_REJECTED = {"code": "proof_rejected"}
UNAVAILABLE = {"code": "verification_temporarily_unavailable"}


class _RecordingSession(_StubSession):
    """The stub session, additionally recording every instance the completion asked it to refresh."""

    def __init__(self, timeline: list[str], detached: tuple = ()) -> None:
        super().__init__(timeline, detached)
        self.refresh_calls: list[object] = []

    async def refresh(self, obj) -> None:
        self.refresh_calls.append(obj)
        await super().refresh(obj)


class _RegisteredStubSync(_StubSync):
    """The post-commit entitlement read on this route, answering with the registered grant."""

    async def read_entitlement(self, user_id) -> Entitlement:
        return Entitlement(type=EntitlementType.registered_account_grant,
                           status=EntitlementStatus.active,
                           tier_id="registered",
                           monthly_credits=50,
                           current_period="2026-09",
                           monthly_used=0)


@pytest.fixture
def timeline() -> list[str]:
    """One ordered record of every boundary, crud call and seam call this request made."""
    return []


@pytest.fixture
def store() -> _FakeChallengeStore:
    return _FakeChallengeStore()


@pytest.fixture
def account() -> tuple[ExternalIdentity, User]:
    """The caller's stored rows, registered through Google and eligible until a case says otherwise."""
    user = User(id=uuid4())
    identity_row = ExternalIdentity(user_id=user.id,
                                    issuer=TEST_ISSUER,
                                    subject=SUBJECT,
                                    provider=IdentityProvider.google,
                                    provider_uid="google-uid-stored")
    return identity_row, user


@pytest.fixture
def session(timeline, account) -> _RecordingSession:
    return _RecordingSession(timeline, detached=account)


@pytest.fixture
def identity(account) -> Identity:
    """A linked caller: this route sits behind the same barrier the anonymous claim does."""
    identity_row, user = account
    return Identity(issuer=TEST_ISSUER, subject=SUBJECT, user=user, identity=identity_row)


@pytest.fixture
def grants(session, timeline, monkeypatch) -> _RecordingGrants:
    """Every crud call replaced by a recorder, so the preflight's own matrix is what a case drives."""
    recorder = _RecordingGrants(session, timeline)
    monkeypatch.setattr(GrantsDB, "read_effective_grants", recorder.read_effective)
    monkeypatch.setattr(GrantsDB, "read_active_grants", recorder.read_active)
    monkeypatch.setattr(GrantsDB, "holds_grant_of_source", recorder.holds_grant_of_source)
    monkeypatch.setattr(GrantsDB, "has_prior_free_grant", recorder.has_prior_free_grant)
    monkeypatch.setattr(GrantsDB, "activate_registered_account_grant", recorder.activate)
    return recorder


@pytest.fixture
def devicecheck(session, timeline) -> _ScriptedDeviceCheck:
    return _ScriptedDeviceCheck(session, timeline)


@pytest.fixture
def client(store, session, identity, grants, devicecheck):
    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_identity] = lambda: identity

    # An async generator, not a plain callable: `get_db` releases the read transaction itself.
    async def _db():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_firebase_adapter] = lambda: None
    app.dependency_overrides[get_devicecheck_adapter] = lambda: devicecheck
    app.dependency_overrides[get_sync_service] = lambda: _RegisteredStubSync()

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _issued(bound_to, **state):
    """A challenge row issued for this route's operation, in whichever lifecycle state the case needs."""
    return _issued_row(bound_to=bound_to,
                       operation=AuthOperation.claim_registered_grant,
                       **state)


def _claim(client, handle: str = HANDLE):
    return client.post("/auth/claim-registered-grant",
                       json={"challenge_id": handle, "device_token": DEVICE_TOKEN})


class TestTheRejectionsBeforeTheClaimSpendNothing:
    """A wrong presenter must not be able to burn a live handle belonging to someone else."""

    def test_an_unknown_handle_neither_claims_nor_consumes(self, client, store, devicecheck):
        store.row = None

        response = _claim(client)

        assert response.status_code == 409
        assert response.json() == CHALLENGE_REQUIRED
        assert store.consume_calls == 0
        assert devicecheck.read_calls == []

    def test_a_handle_bound_to_another_identity_neither_claims_nor_consumes(
            self, client, store, devicecheck):
        store.row = _issued(bound_to=uuid4())

        response = _claim(client)

        assert response.status_code == 409
        assert response.json() == CHALLENGE_REQUIRED
        # The rightful owner's row is untouched: this is the property that stops the burn.
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert devicecheck.read_calls == []

    def test_a_handle_issued_for_another_operation_neither_claims_nor_consumes(
            self, client, store, account, devicecheck):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id,
                                operation=AuthOperation.claim_anonymous_grant)

        response = _claim(client)

        assert response.status_code == 409
        assert response.json() == CHALLENGE_REQUIRED
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert devicecheck.read_calls == []

    def test_an_expired_handle_loses_the_claim_and_consumes_nothing(self, client, store, account,
                                                                     devicecheck):
        identity_row, _ = account
        store.row = _issued(bound_to=identity_row.id, ttl_seconds=-1)

        response = _claim(client)

        assert response.status_code == 409
        assert response.json() == CHALLENGE_REQUIRED
        assert store.row.claimed_at is None
        assert store.consume_calls == 0
        assert devicecheck.read_calls == []

    def test_an_already_consumed_handle_loses_the_claim_and_consumes_nothing(
            self, client, store, account, devicecheck):
        """There is no idempotent replay of a spent handle: the claim loser does no work at all."""
        identity_row, _ = account
        store.row = _issued(bound_to=identity_row.id, claimed=True, consumed=True)
        holder = store.row.claimed_at

        response = _claim(client)

        assert response.status_code == 409
        assert response.json() == CHALLENGE_REQUIRED
        assert store.row.claimed_at == holder
        assert store.consume_calls == 0
        assert devicecheck.read_calls == []


class TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce:
    """Once the claim is won the handle is spent, with no branch on which of the ten outcomes fired."""

    def test_an_anonymous_claimant_is_refused_before_any_grant_is_read(self, client, store,
                                                                        account, devicecheck,
                                                                        timeline):
        identity_row, _ = account
        identity_row.provider = IdentityProvider.anonymous
        identity_row.provider_uid = None
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        # The first decision of the post-claim work, so no grant read was ever issued.
        assert "read_effective_grants" not in timeline
        assert devicecheck.read_calls == []

    def test_an_active_grant_of_another_source_is_refused_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.manual)]
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []

    def test_a_spent_free_grant_in_history_is_refused_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        grants.prior_free_grant = True
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []

    def test_the_repeat_answers_two_hundred_writes_nothing_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.registered_account_grant)]
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []
        assert devicecheck.write_calls == []

    def test_the_conversion_reaches_the_writer_without_reaching_apple_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant)]
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert store.consume_calls == 1
        assert grants.activates == 1
        assert devicecheck.read_calls == []
        assert devicecheck.write_calls == []

    def test_the_new_grant_reaches_the_writer_after_one_read_and_one_write(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert response.json()["entitlement"]["type"] == "registered_account_grant"
        assert store.consume_calls == 1
        assert grants.activates == 1
        assert devicecheck.read_calls == [DEVICE_TOKEN]
        # bit0 carried forward from the query, never fabricated.
        assert devicecheck.write_calls == [(DEVICE_TOKEN, False, True)]

    def test_a_spent_device_slot_is_exhausted_and_still_consumes(self, client, store, account,
                                                                  grants, devicecheck):
        identity_row, _ = account
        store.row = _issued(bound_to=identity_row.id)
        devicecheck.script(BitState(bit0=False, bit1=True))

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == DEVICE_EXHAUSTED
        assert store.consume_calls == 1
        assert devicecheck.write_calls == []
        assert grants.activates == 0

    def test_a_token_apple_refuses_is_a_proof_rejection_that_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        store.row = _issued(bound_to=identity_row.id)
        devicecheck.script(ProofRejected(stage="devicecheck_read", cause="rejected"))

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == PROOF_REJECTED
        assert store.consume_calls == 1
        assert grants.activates == 0

    def test_an_exhausted_apple_budget_is_unavailable_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        store.row = _issued(bound_to=identity_row.id)
        devicecheck.script(RetryableDeviceCheckError("scripted transport failure"))

        response = _claim(client)

        assert response.status_code == 503
        assert response.json() == UNAVAILABLE
        assert store.consume_calls == 1
        assert grants.activates == 0

    def test_the_race_loser_rolls_back_answers_two_hundred_and_refreshes_nothing(
            self, client, store, account, grants, devicecheck, session):
        """The unique indexes are the arbiter, and the loser answers exactly as the repeat does."""
        identity_row, _ = account
        grants.outcome = ActivationOutcome.lost_race
        grants.won_by = [_a_grant(AccessGrantSource.registered_account_grant)]
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert store.consume_calls == 1
        assert grants.activates == 1
        assert session.rollbacks >= 1
        # The caller's rows came from a closed session, so a refresh on this arm is the 500 this pins.
        assert session.refresh_calls == []

    def test_a_refused_write_rolls_back_answers_four_hundred_and_three_and_refreshes_nothing(
            self, client, store, account, grants, devicecheck, session):
        """WR-03: the write was impossible, so there is no row to read back and no 200 to give."""
        identity_row, _ = account
        grants.outcome = ActivationOutcome.refused
        # A readable grant after the rollback, so only the outcome itself can produce the 403 below.
        grants.won_by = [_a_grant(AccessGrantSource.anonymous_device_grant)]
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert grants.activates == 1
        assert session.rollbacks >= 1
        assert session.refresh_calls == []

    def test_a_lost_race_whose_re_read_finds_nothing_is_refused_rather_than_reported_as_a_grant(
            self, client, store, account, grants, devicecheck, session):
        """The backstop: a 200 that reports a grant the caller does not hold is structurally impossible."""
        identity_row, _ = account
        grants.outcome = ActivationOutcome.lost_race
        grants.won_by = []
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert session.refresh_calls == []

    def test_a_second_effective_grant_trips_the_wire_rather_than_choosing_between_them(
            self, client, store, account, grants, devicecheck):
        """WR-04: the tripwire the two reading services already raise, on the writer's own caller."""
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant),
                       _a_grant(AccessGrantSource.anonymous_device_grant)]
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 500
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []


class TestThePrecedenceOrderAndNotOnlyTheOutcome:
    """The three facts a copy of the anonymous module would get wrong, each stated as an order."""

    def test_an_active_subscription_refuses_before_the_history_read_is_issued(
            self, client, store, account, grants, devicecheck, timeline):
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.subscription)]
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        # `OtherActiveGrantHeld`, not `FreeGrantAlreadyConsumed`: the history read is never reached.
        assert "has_prior_free_grant" not in timeline
        assert devicecheck.read_calls == []

    def test_a_spent_anonymous_grant_with_no_active_grant_is_refused_by_the_history_read(
            self, client, store, account, grants, devicecheck, timeline):
        identity_row, _ = account
        grants.held = []
        grants.prior_free_grant = True
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert "has_prior_free_grant" in timeline
        assert devicecheck.read_calls == []
        assert devicecheck.write_calls == []

    def test_an_active_anonymous_grant_converts_even_though_both_spent_signals_are_true(
            self, client, store, account, grants, devicecheck):
        """A blanket `free_grant_consumed_at` or `has_prior_free_grant` guard turns this into a 403."""
        identity_row, _ = account
        identity_row.free_grant_consumed_at = datetime.now(UTC)
        grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant)]
        grants.prior_free_grant = True
        store.row = _issued(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert grants.activates == 1
        assert devicecheck.read_calls == []


def _anonymous_claimant(identity_row, grants, devicecheck) -> None:
    identity_row.provider = IdentityProvider.anonymous
    identity_row.provider_uid = None


def _other_source_held(identity_row, grants, devicecheck) -> None:
    grants.held = [_a_grant(AccessGrantSource.manual)]


def _free_grant_already_consumed(identity_row, grants, devicecheck) -> None:
    grants.prior_free_grant = True


def _repeat(identity_row, grants, devicecheck) -> None:
    grants.held = [_a_grant(AccessGrantSource.registered_account_grant)]


def _conversion(identity_row, grants, devicecheck) -> None:
    grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant)]


def _device_spent(identity_row, grants, devicecheck) -> None:
    devicecheck.script(BitState(bit0=False, bit1=True))


def _proof_refused(identity_row, grants, devicecheck) -> None:
    devicecheck.script(ProofRejected(stage="devicecheck_read", cause="rejected"))


def _apple_unavailable(identity_row, grants, devicecheck) -> None:
    devicecheck.script(RetryableDeviceCheckError("scripted transport failure"))


def _race_lost(identity_row, grants, devicecheck) -> None:
    grants.outcome = ActivationOutcome.lost_race
    grants.won_by = [_a_grant(AccessGrantSource.registered_account_grant)]


def _write_refused(identity_row, grants, devicecheck) -> None:
    grants.outcome = ActivationOutcome.refused
    grants.won_by = [_a_grant(AccessGrantSource.anonymous_device_grant)]


def _race_lost_with_nothing_to_read(identity_row, grants, devicecheck) -> None:
    grants.outcome = ActivationOutcome.lost_race
    grants.won_by = []


def _new_grant(identity_row, grants, devicecheck) -> None:
    return None


POST_CLAIM_OUTCOMES = (_anonymous_claimant, _other_source_held, _free_grant_already_consumed,
                       _repeat, _conversion, _device_spent, _proof_refused, _apple_unavailable,
                       _race_lost, _write_refused, _race_lost_with_nothing_to_read, _new_grant)


class TestTheConsumptionCounterIsOneForEveryPostClaimOutcome:
    """The control: one assertion over every branch, so a new branch that forgets to spend fails here."""

    @pytest.mark.parametrize("setup", POST_CLAIM_OUTCOMES, ids=lambda f: f.__name__.strip("_"))
    def test_each_outcome_consumes_exactly_once(self, setup, client, store, account, grants,
                                                devicecheck):
        identity_row, _ = account
        setup(identity_row, grants, devicecheck)
        store.row = _issued(bound_to=identity_row.id)

        _claim(client)

        assert store.consume_calls == 1
        assert store.row.consumed_at is not None
