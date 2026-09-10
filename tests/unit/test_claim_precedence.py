"""The claim completion: the order of its rejections, and what each branch spends.
D-06's accounting: no pre-claim rejection claims or consumes, and every post-claim outcome
consumes once -- the refusals, the Apple arms, the race loss and the success alike.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import InvalidRequestError

from nativespeaker.api.app.dependencies import (
    get_challenge_store,
    get_devicecheck_adapter,
    get_firebase_adapter,
    get_identity,
    get_sync_service,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.devicecheck import BitState, RetryableDeviceCheckError
from nativespeaker.api.crud.grants import ActivationOutcome, GrantsDB
from nativespeaker.api.errors import ProofRejected, Unavailable
from nativespeaker.api.routers import auth_router
from nativespeaker.api.schemas.auth import (
    Entitlement,
    EntitlementStatus,
    EntitlementType,
    Identity,
)
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.grants import AccessGrant, AccessGrantSource
from nativespeaker.api.tables.identities import (
    ExternalIdentity,
    IdentityProvider,
    NativeClaimProvider,
)
from nativespeaker.api.tables.users import User

# The challenge-store fake is imported rather than copied: two drifting fakes of one conditional
# update is the hazard, and that update is the system's only serialization point.
from .conftest import TEST_ISSUER
from .conftest import FakeChallengeStore as _FakeChallengeStore

SUBJECT = "claim-precedence-subject"
HANDLE = "a-scripted-claim-handle"

# One obviously synthetic token, naming the one device; it resembles no real device token.
DEVICE_TOKEN = "a-synthetic-device-token"

REFUSED = {"code": "operation_not_allowed"}
CHALLENGE_REQUIRED = {"code": "challenge_required"}


class _WarningSpy:
    """Stands in for the handler's whole `logger`; only the level a refusal is recorded at exists."""

    def __init__(self, records: list[dict]) -> None:
        self.records = records

    def warning(self, event, **fields) -> None:
        self.records.append({"event": event} | fields)


def _handler_warnings(monkeypatch) -> list[dict]:
    """The whole `logger` name, never its level attributes: structlog's lazy proxy builds those on
    demand, so monkeypatch's undo would freeze one onto the proxy for the rest of the session."""
    records: list[dict] = []
    monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger", _WarningSpy(records))
    return records


class _StubSession:
    """Records transaction boundaries and refuses queries: a statement here means a write ran unstubbed."""

    def __init__(self, timeline: list[str], detached: tuple = ()) -> None:
        self.timeline = timeline
        self.commits = 0
        self.rollbacks = 0
        # A real session holds one open from its first statement until the next boundary, so every
        # recorded read sets this as well as the writer: a preflight read checks a connection out too.
        self.in_transaction = False
        # The rows `get_identity` resolved on its own closed session, which this session never held.
        self.detached = detached

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def commit(self) -> None:
        self.commits += 1
        self.in_transaction = False
        self.timeline.append("commit")

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.in_transaction = False
        self.timeline.append("rollback")

    async def refresh(self, obj) -> None:
        if any(obj is row for row in self.detached):
            raise InvalidRequestError(f"Instance '{obj}' is not persistent within this Session")

    async def exec(self, statement):
        raise AssertionError(f"the completion path issued a query of its own: {statement!r}")


class _RecordingGrants:
    """Stands in for the crud calls the claim makes, recording each and scripting its answer."""

    def __init__(self, session: _StubSession, timeline: list[str]) -> None:
        self.session = session
        self.timeline = timeline
        self.held: list[AccessGrant] = []
        self.marked_active: list[AccessGrant] = []
        self.grant_of_source: set[AccessGrantSource] = set()
        self.prior_free_grant = False
        self.activates = 0
        # The platform each activation named, so the pin is asserted rather than assumed.
        self.claim_platforms: list = []
        self.outcome = ActivationOutcome.activated
        # The arm the writer says refused, which the refusal's one log line carries.
        self.cause: str | None = None
        # What the loser's re-read finds after its rollback, which is the winner's row and not its own.
        self.won_by: list[AccessGrant] | None = None
        self.reads = 0

    async def read_effective(self, user_id: UUID, evaluated_at: datetime) -> list[AccessGrant]:
        self.timeline.append("read_effective_grants")
        # A read opens the transaction as surely as a write does: SQLAlchemy autobegins on the
        # first statement, and the connection stays checked out until the next boundary.
        self.session.in_transaction = True
        # Every read after the first is the loser's re-read, taken in the transaction the rollback opened.
        answer = self.won_by if self.reads and self.won_by is not None else self.held
        self.reads += 1
        return list(answer)

    async def read_active(self, user_id: UUID) -> list[AccessGrant]:
        """The status-only read, which by default sees exactly the effective rows and no more."""
        self.timeline.append("read_active_grants")
        self.session.in_transaction = True
        return list(self.held) + list(self.marked_active)

    async def holds_grant_of_source(self, user_id: UUID, source: AccessGrantSource) -> bool:
        self.timeline.append("holds_grant_of_source")
        self.session.in_transaction = True
        return source in self.grant_of_source

    async def has_prior_free_grant(self, user_id: UUID) -> bool:
        self.timeline.append("has_prior_free_grant")
        self.session.in_transaction = True
        return self.prior_free_grant

    async def activate(self, *, user_id, issuer, subject, tier_id, evaluated_at,
                       claim_platform=None) -> tuple[ActivationOutcome, str | None]:
        # One double for both writers, and only the anonymous one pins a platform: the default is
        # what lets the registered writer, which has no attestation to name, share this recorder.
        self.activates += 1
        self.claim_platforms.append(claim_platform)
        self.timeline.append("activate")
        # The writer takes both lock tiers and flushes, so the transaction is open from here.
        self.session.in_transaction = True
        return self.outcome, self.cause


class _ScriptedDeviceCheck:
    """The device-gate seam, recording each call and the transaction state the session was in at the time."""

    def __init__(self, session: _StubSession, timeline: list[str]) -> None:
        self.session = session
        self.timeline = timeline
        self.answer: BaseException | BitState = BitState(bit0=False, bit1=False)
        self.write_answer: BaseException | None = None
        self.read_calls: list[str] = []
        self.write_calls: list[tuple[str, bool, bool]] = []
        self.transaction_open_during: list[bool] = []

    def script(self, answer: BaseException | BitState) -> None:
        self.answer = answer

    async def read_bits(self, device_token: str) -> BitState:
        self.read_calls.append(device_token)
        self.transaction_open_during.append(self.session.in_transaction)
        self.timeline.append("read_bits")
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    async def write_bits(self, device_token: str, *, bit0: bool, bit1: bool) -> None:
        self.write_calls.append((device_token, bit0, bit1))
        self.transaction_open_during.append(self.session.in_transaction)
        self.timeline.append("write_bits")
        if isinstance(self.write_answer, BaseException):
            raise self.write_answer


class _StubSync:
    """The post-commit entitlement read, stubbed: the real one would query the refusing session."""

    async def read_entitlement(self, user_id: UUID) -> Entitlement:
        return Entitlement(type=EntitlementType.anonymous_device_grant,
                           status=EntitlementStatus.active,
                           tier_id="anonymous",
                           monthly_credits=10,
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
def session(timeline, account) -> _StubSession:
    return _StubSession(timeline, detached=account)


@pytest.fixture
def account() -> tuple[ExternalIdentity, User]:
    """The caller's stored rows, anonymous and eligible until a case makes them otherwise."""
    user = User(id=uuid4())
    identity_row = ExternalIdentity(user_id=user.id,
                                    issuer=TEST_ISSUER,
                                    subject=SUBJECT,
                                    provider=IdentityProvider.anonymous,
                                    provider_uid=None)
    return identity_row, user


@pytest.fixture
def identity(account) -> Identity:
    """A linked caller: the claim route narrows to one, as the upgrade route does."""
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
    monkeypatch.setattr(GrantsDB, "activate_anonymous_device_grant", recorder.activate)
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

    # `get_db` is left un-overridden and reads only this: a mirror of it drifted from the real one.
    app.state.session_factory = lambda: session
    app.dependency_overrides[get_challenge_store] = lambda: store
    app.dependency_overrides[get_firebase_adapter] = lambda: None
    app.dependency_overrides[get_devicecheck_adapter] = lambda: devicecheck
    app.dependency_overrides[get_sync_service] = lambda: _StubSync()

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _issued_row(*,
                bound_to: UUID | None,
                operation: AuthOperation = AuthOperation.claim_anonymous_grant,
                ttl_seconds: int = 300,
                claimed: bool = False,
                consumed: bool = False) -> AuthChallenge:
    """An identity-bound challenge row in whichever lifecycle state the case needs."""
    now = datetime.now(UTC)
    row = AuthChallenge(challenge_id=HANDLE,
                        operation=operation,
                        bound_external_identity_id=bound_to,
                        expires_at=now + timedelta(seconds=ttl_seconds),
                        created_at=now)
    if claimed or consumed:
        row.claimed_at = now
    if consumed:
        row.consumed_at = now
    return row


def _claim(client, handle: str = HANDLE):
    return client.post("/auth/claim-anonymous-grant",
                       json={"challenge_id": handle, "device_token": DEVICE_TOKEN})


def _a_grant(source: AccessGrantSource) -> AccessGrant:
    """One effective grant of `source`, which is all the preflight reads off it."""
    return AccessGrant(user_id=uuid4(), tier_id="registered", source=source)


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
        store.row = _issued_row(bound_to=uuid4())

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
                                operation=AuthOperation.upgrade_anonymous_to_registered)

        response = _claim(client)

        assert response.status_code == 409
        assert response.json() == CHALLENGE_REQUIRED
        assert store.row.claimed_at is None
        assert store.row.consumed_at is None
        assert store.consume_calls == 0
        assert devicecheck.read_calls == []


class TestTheClaimsConditionalUpdateIsTheOnlyExpiryEvaluation:
    """Both losses come from losing the conditional update; `claimed_at` is what tells them apart."""

    def test_an_expired_handle_loses_the_claim_and_consumes_nothing(self, client, store, account,
                                                                     devicecheck):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id, ttl_seconds=-1)

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
        store.row = _issued_row(bound_to=identity_row.id, claimed=True, consumed=True)
        holder = store.row.claimed_at

        response = _claim(client)

        assert response.status_code == 409
        assert response.json() == CHALLENGE_REQUIRED
        assert store.row.claimed_at == holder
        assert store.consume_calls == 0
        assert devicecheck.read_calls == []


class TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce:
    """D-06: once the claim is won the handle is spent, with no branch on which outcome fired."""

    def test_a_registered_claimant_is_refused_and_still_consumes(self, client, store, account,
                                                                  devicecheck):
        identity_row, _ = account
        identity_row.provider = IdentityProvider.google
        identity_row.provider_uid = "google-uid-stored"
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        # Decided after the claim, because the claimant check is the first thing the post-claim work does.
        assert store.row.consumed_at is not None
        assert devicecheck.read_calls == []

    def test_a_spent_lifetime_slot_is_refused_and_still_consumes(self, client, store, account,
                                                                  grants, devicecheck):
        identity_row, _ = account
        identity_row.free_grant_consumed_at = datetime.now(UTC)
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []

    def test_a_prior_free_grant_at_any_status_is_refused_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        """The marker is unset, so this arm is the lifetime read alone -- and it carries no status predicate."""
        identity_row, _ = account
        grants.prior_free_grant = True
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert devicecheck.read_calls == []

    def test_an_active_grant_of_another_source_is_refused_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.manual)]
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert devicecheck.read_calls == []

    def test_the_repeat_answers_two_hundred_and_still_consumes(self, client, store, account,
                                                               grants, devicecheck):
        """D-09: the held anonymous grant returns before Apple, writes nothing, and spends the handle."""
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant)]
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []

    def test_a_spent_device_slot_is_refused_and_still_consumes(self, client, store, account,
                                                               grants, devicecheck):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        devicecheck.script(BitState(bit0=True, bit1=False))

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == {"code": "device_grant_exhausted"}
        assert store.consume_calls == 1
        assert devicecheck.write_calls == []
        assert grants.activates == 0

    def test_a_token_apple_refuses_is_a_proof_rejection_that_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        devicecheck.script(ProofRejected(stage="devicecheck_read", cause="rejected"))

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == {"code": "proof_rejected"}
        assert store.consume_calls == 1
        assert grants.activates == 0

    def test_an_exhausted_apple_budget_is_unavailable_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        devicecheck.script(RetryableDeviceCheckError("scripted transport failure"))

        response = _claim(client)

        assert response.status_code == 503
        assert response.json() == {"code": "verification_temporarily_unavailable"}
        assert store.consume_calls == 1
        assert grants.activates == 0

    def test_the_race_loser_answers_two_hundred_and_still_consumes(self, client, store, account,
                                                                    grants, devicecheck):
        """The unique indexes are the arbiter, and the loser answers exactly as the repeat does.
        The caller's rows came from a closed session, so touching either one here is the 500 this pins."""
        identity_row, _ = account
        grants.outcome = ActivationOutcome.lost_race
        grants.won_by = [_a_grant(AccessGrantSource.anonymous_device_grant)]
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert store.consume_calls == 1
        assert grants.activates == 1

    def test_a_refused_write_answers_four_hundred_and_three_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        """WR-03: the write was impossible, so there is no row to read back and no 200 to give."""
        identity_row, _ = account
        grants.outcome = ActivationOutcome.refused
        # A readable grant after the rollback, so only the outcome itself can produce the 403 below.
        grants.won_by = [_a_grant(AccessGrantSource.anonymous_device_grant)]
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert grants.activates == 1

    def test_the_refusal_names_the_writer_s_arm_in_its_one_log_line(self, client, store, account,
                                                                     grants, devicecheck,
                                                                     monkeypatch):
        """WR-62: nine refusals left the same field-less `claim_refused_under_lock`, so a platform
        pin and a lost race read identically. One line still, and now it says which."""
        records = _handler_warnings(monkeypatch)
        identity_row, _ = account
        grants.outcome = ActivationOutcome.refused
        grants.cause = "platform_pinned_to_another"
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert [(line["event"], line.get("cause")) for line in records] == [
            ("claim_refused_under_lock", "platform_pinned_to_another")]

    def test_a_race_the_re_read_cannot_answer_is_named_apart_from_those_refusals(
            self, client, store, account, grants, devicecheck, monkeypatch):
        """The one arm the writer does not name: the service supplies it, and it is the only
        `claim_refused_under_lock` that really was a race."""
        records = _handler_warnings(monkeypatch)
        identity_row, _ = account
        grants.outcome = ActivationOutcome.lost_race
        grants.won_by = []
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert [line.get("cause") for line in records] == ["lost_race_without_a_readable_grant"]

    def test_a_lost_race_whose_re_read_finds_nothing_is_refused_rather_than_reported_as_a_grant(
            self, client, store, account, grants, devicecheck):
        """The backstop: a 200 that reports a grant the caller does not hold is structurally impossible."""
        identity_row, _ = account
        grants.outcome = ActivationOutcome.lost_race
        grants.won_by = []
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1

    def test_the_successful_claim_consumes_exactly_once(self, client, store, account, grants,
                                                        devicecheck):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert response.json()["entitlement"]["type"] == "anonymous_device_grant"
        assert store.consume_calls == 1
        assert grants.activates == 1
        assert devicecheck.read_calls == [DEVICE_TOKEN]
        # bit1 carried forward from the query, never fabricated.
        assert devicecheck.write_calls == [(DEVICE_TOKEN, True, False)]

    def test_the_other_bit_is_carried_forward_rather_than_fabricated(self, client, store, account,
                                                                     grants, devicecheck):
        """WR-69: bit1 is this device's registered slot, and Apple writes both bits in one call,
        so a fabricated `False` here hands back a slot nothing in this product ever clears."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        devicecheck.script(BitState(bit0=False, bit1=True))

        response = _claim(client)

        assert response.status_code == 200
        assert grants.activates == 1
        assert devicecheck.write_calls == [(DEVICE_TOKEN, True, True)]

    def test_a_failed_bit_write_after_the_commit_is_logged_rather_than_answered(
            self, client, store, account, grants, devicecheck):
        """CR-60: the grant committed before Apple was told, so the vendor failure is not the answer."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        devicecheck.write_answer = Unavailable(stage="devicecheck_write")

        response = _claim(client)

        assert response.status_code == 200
        assert response.json()["entitlement"]["type"] == "anonymous_device_grant"
        assert store.consume_calls == 1
        assert grants.activates == 1
        assert devicecheck.write_calls == [(DEVICE_TOKEN, True, False)]

    def test_the_writer_is_told_which_attestation_this_route_ran(self, client, store, account,
                                                                 grants, devicecheck):
        """WR-41. The platform pinned on the identity is the one this arm verified, supplied by the
        caller: a constant inside the writer records an Android claim as an Apple one."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)

        assert _claim(client).status_code == 200
        assert grants.claim_platforms == [NativeClaimProvider.ios_devicecheck]

    def test_a_second_effective_grant_trips_the_wire_rather_than_choosing_between_them(
            self, client, store, account, grants, devicecheck):
        """The tripwire the registered sibling raises: two effective grants fail closed here too,
        rather than letting the repeat arm below rank `anonymous_device_grant` above the other."""
        identity_row, _ = account
        grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant),
                       _a_grant(AccessGrantSource.manual)]
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 500
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []


class TestTheDeviceReadAndTheDeviceWriteNameOneDevice:
    """ANONGRANT-03: two tokens would let bit0 be read off a device that is never written to."""

    def test_the_token_the_gate_reads_is_the_token_it_then_writes(self, client, store, account,
                                                                   grants, devicecheck):
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        assert devicecheck.read_calls == [DEVICE_TOKEN]
        assert [token for token, _, _ in devicecheck.write_calls] == devicecheck.read_calls

    def test_a_body_naming_no_device_is_rejected_before_the_gate(self, client, store,
                                                                 account, devicecheck):
        """The one token is required, so a body without it is the framework's 422 and spends nothing."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)

        response = client.post("/auth/claim-anonymous-grant",
                               json={"challenge_id": HANDLE,
                                     "query_token": "device-a-never-written-to",
                                     "update_token": "device-b-already-set"})

        assert response.status_code == 422
        assert devicecheck.read_calls == []
        assert store.consume_calls == 0

    def test_a_body_offering_a_second_token_never_reaches_the_gate_with_it(self, client, store,
                                                                           account, devicecheck):
        """WR-70: the split body is gone from the wire, so the extra keys are dropped rather than
        substituted, and one device is named on both calls."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)

        response = client.post("/auth/claim-anonymous-grant",
                               json={"challenge_id": HANDLE,
                                     "device_token": DEVICE_TOKEN,
                                     "query_token": "device-a-never-written-to",
                                     "update_token": "device-b-already-set"})

        assert response.status_code == 200
        assert devicecheck.read_calls == [DEVICE_TOKEN]
        assert [token for token, _, _ in devicecheck.write_calls] == [DEVICE_TOKEN]


def _registered(identity_row, grants, devicecheck) -> None:
    identity_row.provider = IdentityProvider.google
    identity_row.provider_uid = "google-uid-stored"


def _slot_spent(identity_row, grants, devicecheck) -> None:
    identity_row.free_grant_consumed_at = datetime.now(UTC)


def _prior_free_grant(identity_row, grants, devicecheck) -> None:
    grants.prior_free_grant = True


def _other_source_held(identity_row, grants, devicecheck) -> None:
    grants.held = [_a_grant(AccessGrantSource.manual)]


def _repeat(identity_row, grants, devicecheck) -> None:
    grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant)]


def _marked_outside_its_term(identity_row, grants, devicecheck) -> None:
    # A row the one-active index sees and the effective read does not, so only the status read finds it.
    grants.marked_active = [_a_grant(AccessGrantSource.anonymous_device_grant)]


def _device_spent(identity_row, grants, devicecheck) -> None:
    devicecheck.script(BitState(bit0=True, bit1=False))


def _proof_refused(identity_row, grants, devicecheck) -> None:
    devicecheck.script(ProofRejected(stage="devicecheck_read", cause="rejected"))


def _apple_unavailable(identity_row, grants, devicecheck) -> None:
    devicecheck.script(RetryableDeviceCheckError("scripted transport failure"))


def _race_lost(identity_row, grants, devicecheck) -> None:
    grants.outcome = ActivationOutcome.lost_race
    grants.won_by = [_a_grant(AccessGrantSource.anonymous_device_grant)]


def _write_refused(identity_row, grants, devicecheck) -> None:
    grants.outcome = ActivationOutcome.refused
    grants.won_by = [_a_grant(AccessGrantSource.anonymous_device_grant)]


def _race_lost_with_nothing_to_read(identity_row, grants, devicecheck) -> None:
    grants.outcome = ActivationOutcome.lost_race
    grants.won_by = []


def _success(identity_row, grants, devicecheck) -> None:
    return None


POST_CLAIM_OUTCOMES = (_registered, _slot_spent, _prior_free_grant, _other_source_held, _repeat,
                       _marked_outside_its_term, _device_spent, _proof_refused, _apple_unavailable,
                       _race_lost, _write_refused, _race_lost_with_nothing_to_read, _success)


class TestTheConsumptionCounterIsOneForEveryPostClaimOutcome:
    """The control: one assertion over every branch, so a new branch that forgets to spend fails here."""

    @pytest.mark.parametrize("setup", POST_CLAIM_OUTCOMES, ids=lambda f: f.__name__.strip("_"))
    def test_each_outcome_consumes_exactly_once(self, setup, client, store, account, grants,
                                                devicecheck):
        identity_row, _ = account
        setup(identity_row, grants, devicecheck)
        store.row = _issued_row(bound_to=identity_row.id)

        _claim(client)

        assert store.consume_calls == 1
        assert store.row.consumed_at is not None


class TestNoVendorCallHappensUnderALockOrInsideTheTransaction:
    """ANONGRANT-02 as a sequence check: a future edit that reorders these fails a named case."""

    def test_the_claims_commit_precedes_the_seam_and_no_transaction_is_open_during_it(
            self, client, store, account, session, devicecheck, timeline):
        """A post-claim refusal, chosen because it reaches the seam and then refuses."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)
        devicecheck.script(BitState(bit0=True, bit1=False))

        response = _claim(client)

        assert response.status_code == 403
        assert timeline.index("commit") < timeline.index("read_bits")
        assert devicecheck.transaction_open_during == [False]

    def test_the_activation_sits_between_the_two_seam_calls_and_commits_before_the_write(
            self, client, store, account, grants, devicecheck, timeline):
        """The read runs before the transaction opens; the write runs after it commits."""
        identity_row, _ = account
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 200
        activated = timeline.index("activate")
        written = timeline.index("write_bits")
        assert timeline.index("read_bits") < activated < written
        # The grant is durable before Apple is told, so no crash can burn the bit with nothing
        # granted. `index` alone would find the challenge claim's own commit, which precedes both.
        assert "commit" in timeline[activated:written]
        # Neither seam call saw an open transaction, which is the claim in prose stated as a check.
        assert devicecheck.transaction_open_during == [False, False]
