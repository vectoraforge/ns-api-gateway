"""The shared operation challenge: preparation, the wire contract, the challenge row, and the
common completion procedure with its claim-and-consume serialization."""

import base64
import hashlib
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import (
    AuthAuditWriter,
    AuthEventResult,
    AuthResultCounter,
)
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import (
    CHALLENGE_TTL_SECONDS,
    ChallengeError,
    ChallengeRow,
    ChallengeState,
    ChallengeStore,
    ClaimOutcome,
    ConsumeOutcome,
    IdentityBinding,
    NonceConvention,
    PrepareResponse,
    advance_state,
    assert_no_proof_material_bound,
    assert_nothing_serialized,
    challenge_expires_at,
    challenge_ids_equal,
    new_challenge_id,
    persisted_bindings,
    provider_nonce,
    variants_equal,
)
from nativespeaker.api.auth.flow import ChallengeScopeError, dispatch_state_changing
from nativespeaker.api.auth.modes import ModeSignalError, RequestMode, classify_mode
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    InvalidOperationVariantError,
    route_for,
)
from nativespeaker.api.auth.procedures import (
    ChallengeLookupUnavailableError,
    ChallengeRejection,
    SharedChallengeService,
    TransientTransactionError,
    UnsurfacedResultError,
    challenge_id_shape,
    prepare_mode_supported,
    reconciliation_options,
    register_client_class,
    surface,
)
from nativespeaker.api.auth.taxonomy import RESULT_TO_CLASS
from nativespeaker.api.database.challenges import (
    CLAIM_CHALLENGE,
    CONSUME_CHALLENGE,
    ChallengesDB,
)

TEST_ISSUER = "https://securetoken.google.com/test-project"
CHALLENGE_BEARING = (AuthOperation.create_user, AuthOperation.upgrade_anonymous_to_registered,
                     AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant)
VARIANT_FOR = {AuthOperation.create_user: IdentityProvider.anonymous,
               AuthOperation.upgrade_anonymous_to_registered: IdentityProvider.google,
               AuthOperation.claim_anonymous_grant: None,
               AuthOperation.claim_registered_grant: None}


def verifier(subject: str) -> bytes:
    return hashlib.sha256(b"test-key|" + subject.encode()).digest()


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeSession:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.committed = False

    async def commit(self) -> None:
        self.committed = True
        self.log.append("commit")


class FakeSessionFactory:
    """Counts open sessions, so a test can prove no session is held across provider work."""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.opened = 0
        self.open_now = 0
        self.sessions: list[FakeSession] = []

    def __call__(self):
        return self._session()

    @asynccontextmanager
    async def _session(self):
        self.opened += 1
        self.open_now += 1
        self.log.append("open")
        session = FakeSession(self.log)
        self.sessions.append(session)
        try:
            yield session
        finally:
            self.open_now -= 1
            self.log.append("close")


class _Calls(list):
    """A call log that also appends to a trace shared by the store and the endpoint, so a test
    can assert the order of steps across both."""

    def __init__(self, trace: list[str], owner: str) -> None:
        super().__init__()
        self._trace = trace
        self._owner = owner

    def append(self, item) -> None:
        super().append(item)
        self._trace.append(f"{self._owner}:{item}")


class FakeSink:
    def __init__(self) -> None:
        self.events: list = []

    async def insert(self, session, event) -> None:
        self.events.append(event)

    def results(self) -> list[AuthEventResult]:
        return [event.result for event in self.events]


class FakeStore(ChallengeStore):
    """The challenge row store: the same two conditional updates, in memory."""

    def __init__(self, clock: FakeClock, trace: list[str] | None = None) -> None:
        self.rows: dict[str, ChallengeRow] = {}
        self.clock = clock
        self.trace = trace if trace is not None else []
        self.calls = _Calls(self.trace, "store")
        self.case_insensitive = False

    async def insert(self, row: ChallengeRow) -> None:
        self.calls.append("insert")
        self.rows[row.challenge_id] = row

    async def get(self, challenge_id: str) -> ChallengeRow | None:
        self.calls.append("get")
        if self.case_insensitive:
            for stored, row in self.rows.items():
                if stored.lower() == challenge_id.lower():
                    return row
            return None
        return self.rows.get(challenge_id)

    async def claim(self, challenge_id: str, claim_attempt_id) -> ClaimOutcome:
        self.calls.append("claim")
        row = self.rows.get(challenge_id)
        if row is None:
            return ClaimOutcome.not_found
        if row.state is not ChallengeState.issued:
            return ClaimOutcome.already_used
        if row.expires_at <= self.clock():
            return ClaimOutcome.expired
        self.rows[challenge_id] = replace(row,
                                          state=advance_state(row.state, ChallengeState.claimed),
                                          claim_attempt_id=claim_attempt_id)
        return ClaimOutcome.claimed

    async def consume(self, session, challenge_id: str, claim_attempt_id) -> ConsumeOutcome:
        self.calls.append("consume")
        row = self.rows[challenge_id]
        if row.state is ChallengeState.claimed and row.claim_attempt_id == claim_attempt_id:
            cleared = replace(row.binding, preauth_subject_hash=None) \
                if row.binding.preauth_issuer is not None else row.binding
            self.rows[challenge_id] = replace(
                row, state=advance_state(row.state, ChallengeState.consumed), binding=cleared)
            return ConsumeOutcome.consumed
        if row.state is ChallengeState.consumed and row.claim_attempt_id == claim_attempt_id:
            return ConsumeOutcome.already_consumed_by_this_attempt
        return ConsumeOutcome.lost

    def only(self) -> ChallengeRow:
        assert len(self.rows) == 1
        return next(iter(self.rows.values()))


class FakeEndpoint:
    """The endpoint half. Every hook records itself, so a test can prove what ran and when."""

    def __init__(self, operation: AuthOperation, *,
                 eligibility: AuthEventResult | None = None,
                 proof: AuthEventResult | None = None,
                 live: AuthEventResult | None = None,
                 factory: FakeSessionFactory | None = None,
                 trace: list[str] | None = None) -> None:
        self.operation = operation
        self.trace = trace if trace is not None else []
        self.calls = _Calls(self.trace, "endpoint")
        self.bodies: list = []
        self.eligibility = eligibility
        self.proof = proof
        self.live = live
        self.factory = factory
        self.sessions_open_during_proof: list[int] = []
        self.challenge_states: list[tuple] = []
        self.transient_left = 0

    async def check_prepare_eligibility(self, identity, variant) -> None:
        self.calls.append("eligibility")
        if self.eligibility is not None:
            raise ChallengeRejection(self.eligibility)

    async def verify_proof(self, identity, challenge, body):
        self.calls.append("verify_proof")
        self.bodies.append(body)
        self.challenge_states.append((challenge.state, challenge.claim_attempt_id))
        if self.factory is not None:
            self.sessions_open_during_proof.append(self.factory.open_now)
        if self.proof is not None:
            raise ChallengeRejection(self.proof)
        return {"proof_for": challenge.challenge_id}

    async def confirm_live_state(self, session, identity, challenge):
        self.calls.append("confirm_live_state")
        if self.live is not None:
            raise ChallengeRejection(self.live)
        return {"live": True}

    async def mutate(self, session, identity, challenge, proof, live):
        self.calls.append("mutate")
        if self.transient_left:
            self.transient_left -= 1
            raise TransientTransactionError("commit acknowledgment lost")
        return {"mutated": str(self.operation), "proof": proof}

    async def run(self, identity, body):
        self.calls.append("run")
        return {"ran": str(self.operation)}


def linked_context(external_identity_id=None) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=TEST_ISSUER, subject="linked-subject",
                                   outcome=ResolutionOutcome.linked,
                                   user_id=uuid7(),
                                   external_identity_id=external_identity_id or uuid7(),
                                   provider=IdentityProvider.google)


def preauth_context(subject: str = "preauth-subject") -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=TEST_ISSUER, subject=subject,
                                   outcome=ResolutionOutcome.pre_auth)


class Harness:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.trace: list[str] = []
        self.store = FakeStore(self.clock, self.trace)
        self.factory = FakeSessionFactory()
        self.sink = FakeSink()
        self.audit = AuthAuditWriter(sink=self.sink, counter=AuthResultCounter(),
                                     session_factory=self.factory)
        self.service = SharedChallengeService(store=self.store, audit=self.audit,
                                              session_factory=self.factory,
                                              subject_verifier=verifier, clock=self.clock)

    def endpoint(self, operation: AuthOperation, **kwargs) -> FakeEndpoint:
        return FakeEndpoint(operation, factory=self.factory, trace=self.trace, **kwargs)

    async def prepared(self, operation: AuthOperation, context=None, **kwargs) -> ChallengeRow:
        endpoint = self.endpoint(operation, **kwargs)
        await self.service.prepare(operation, VARIANT_FOR[operation],
                                   context or linked_context(), endpoint)
        return self.store.only()


@pytest.fixture
def h() -> Harness:
    return Harness()


# --- Operation challenge preparation -------------------------------------------------------


class TestPrepareMode:
    # [utest->req~shared-prepare-mode-signal~1]
    async def test_prepare_mode_exists_only_on_the_challenge_bearing_subset(self, h):
        for operation in CHALLENGE_BEARING:
            assert prepare_mode_supported(operation) is True
        for operation in (AuthOperation.sync, AuthOperation.sign_out_all,
                          AuthOperation.restore_subscription):
            assert prepare_mode_supported(operation) is False
            # `challenge=true` on one of those endpoints is not a recognized signal: the
            # endpoint's own rules run and no challenge is issued.
            endpoint = h.endpoint(operation)
            await dispatch_state_changing(operation=operation, endpoint=endpoint,
                                          identity=linked_context(),
                                          query_items=[("challenge", "true")], body={},
                                          shared=h.service)
            assert endpoint.calls == ["run"]
        assert h.store.rows == {}

    # [utest->req~shared-prepare-mode-obligations~1]
    async def test_prepare_mode_runs_every_obligation_in_order(self, h):
        endpoint = h.endpoint(AuthOperation.create_user)
        context = preauth_context()
        response = await h.service.prepare(AuthOperation.create_user, IdentityProvider.anonymous,
                                           context, endpoint)
        row = h.store.only()
        assert endpoint.calls == ["eligibility"]
        assert h.store.calls == ["insert"]
        assert row.state is ChallengeState.issued
        assert row.binding.preauth_issuer == TEST_ISSUER
        assert response.challenge_id == row.challenge_id
        assert response.expires_at == row.expires_at

    # [utest->req~shared-prepare-step-01~1]
    async def test_prepare_consumes_the_barrier_context_and_nothing_else(self, h):
        endpoint = h.endpoint(AuthOperation.create_user)
        with pytest.raises(ChallengeRejection) as excinfo:
            # A handler wired outside the barrier has no typed context: prepare refuses to
            # reconstruct one from anything else.
            await h.service.prepare(AuthOperation.create_user, IdentityProvider.anonymous,
                                    {"sub": "spoofed"}, endpoint)
        assert excinfo.value.result is AuthEventResult.invalid_external_jwt
        assert excinfo.value.error_code == "auth_required"
        assert h.store.rows == {} and endpoint.calls == []

    # [utest->req~shared-prepare-step-02~1]
    async def test_binding_is_derived_from_the_verified_context(self, h):
        linked = linked_context()
        row = await h.prepared(AuthOperation.claim_anonymous_grant, linked)
        assert row.binding.bound_external_identity_id == linked.external_identity_id
        assert row.binding.preauth_issuer is None

        h.store.rows.clear()
        pre = preauth_context()
        row = await h.prepared(AuthOperation.create_user, pre)
        assert row.binding.preauth_issuer == TEST_ISSUER
        assert row.binding.preauth_subject_hash == verifier(pre.subject)
        # The raw subject is never bound.
        assert pre.subject.encode() not in row.binding.preauth_subject_hash

    # [utest->req~shared-prepare-step-03~1]
    async def test_pre_auth_is_admitted_only_for_create_user(self, h):
        for operation in (AuthOperation.upgrade_anonymous_to_registered,
                          AuthOperation.claim_anonymous_grant,
                          AuthOperation.claim_registered_grant):
            endpoint = h.endpoint(operation)
            with pytest.raises(ChallengeRejection) as excinfo:
                await h.service.prepare(operation, VARIANT_FOR[operation], preauth_context(),
                                        endpoint)
            assert excinfo.value.result is AuthEventResult.preauth_identity_not_allowed
            assert endpoint.calls == [] and h.store.rows == {}
        row = await h.prepared(AuthOperation.create_user, preauth_context())
        assert row.operation is AuthOperation.create_user

    # [utest->req~shared-prepare-step-04~1]
    async def test_historical_and_blocked_are_never_admitted(self, h):
        for outcome, result in ((ResolutionOutcome.historical_identity,
                                 AuthEventResult.historical_identity),
                                (ResolutionOutcome.blocked_user, AuthEventResult.blocked_user)):
            endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
            context = VerifiedIdentityContext(issuer=TEST_ISSUER, subject="s", outcome=outcome,
                                              external_identity_id=uuid7())
            with pytest.raises(ChallengeRejection) as excinfo:
                await h.service.prepare(AuthOperation.claim_anonymous_grant, None, context,
                                        endpoint)
            assert excinfo.value.result is result
            assert excinfo.value.error_code == "account_unavailable"
            assert endpoint.calls == [] and h.store.rows == {}

    # [utest->req~shared-prepare-step-05~1]
    async def test_prepare_validates_the_variant_and_runs_only_cheap_eligibility(self, h):
        # An already-linked identity at create_user prepare is rejected here.
        endpoint = h.endpoint(AuthOperation.create_user)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.prepare(AuthOperation.create_user, IdentityProvider.anonymous,
                                    linked_context(), endpoint)
        assert excinfo.value.result is AuthEventResult.identity_already_linked
        assert excinfo.value.error_code == "identity_already_linked"
        assert h.store.rows == {}

        # A variant the operation does not define never reaches the row.
        with pytest.raises(ChallengeError):
            await h.service.prepare(AuthOperation.claim_anonymous_grant, IdentityProvider.google,
                                    linked_context(), h.endpoint(AuthOperation.claim_anonymous_grant))
        with pytest.raises(ChallengeError):
            await h.service.prepare(AuthOperation.upgrade_anonymous_to_registered,
                                    IdentityProvider.anonymous, linked_context(),
                                    h.endpoint(AuthOperation.upgrade_anonymous_to_registered))
        assert h.store.rows == {}

        # An endpoint's own cheap eligibility rejection is audited and issues no challenge.
        endpoint = h.endpoint(AuthOperation.claim_registered_grant,
                              eligibility=AuthEventResult.policy_rejected)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.prepare(AuthOperation.claim_registered_grant, None, linked_context(),
                                    endpoint)
        assert excinfo.value.result is AuthEventResult.policy_rejected
        assert h.store.rows == {}
        assert h.sink.results() == [AuthEventResult.identity_already_linked,
                                    AuthEventResult.policy_rejected]

    # [utest->req~shared-prepare-step-06~1]
    async def test_a_single_use_challenge_is_issued_bound_and_expiring(self, h):
        context = linked_context()
        row = await h.prepared(AuthOperation.claim_anonymous_grant, context)
        assert row.state is ChallengeState.issued
        assert row.expires_at == h.clock() + timedelta(seconds=CHALLENGE_TTL_SECONDS)
        assert row.binding.bound_external_identity_id == context.external_identity_id
        assert row.claim_attempt_id is None
        first = row.challenge_id
        h.store.rows.clear()
        assert (await h.prepared(AuthOperation.claim_anonymous_grant, context)).challenge_id != first

    # [utest->req~shared-prepare-step-07~1]
    async def test_the_challenge_is_persisted_server_side_keyed_by_challenge_id(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        assert h.store.rows[row.challenge_id] is row
        assert await h.store.get(row.challenge_id) is row

    # [utest->req~shared-prepare-step-08~1]
    async def test_prepare_returns_the_handle_and_expiry(self, h):
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        response = await h.service.prepare(AuthOperation.claim_anonymous_grant, None,
                                           linked_context(), endpoint)
        row = h.store.only()
        assert response.model_dump() == {"challenge_id": row.challenge_id,
                                         "expires_at": row.expires_at}

    # [utest->req~shared-prepare-step-09~1]
    async def test_prepare_mutates_no_business_state(self, h):
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.prepare(AuthOperation.claim_anonymous_grant, None, linked_context(),
                                endpoint)
        # No live-state read, no provider call, no mutation, and no transaction at all.
        assert endpoint.calls == ["eligibility"]
        assert h.factory.opened == 0
        assert h.store.calls == ["insert"]


class TestChallengeTtl:
    # [utest->req~shared-challenge-ttl~1]
    async def test_one_ttl_from_the_server_clock_never_extended(self, h):
        assert CHALLENGE_TTL_SECONDS == 300
        # The same lifetime for every challenge-issuing operation; no operation overrides it.
        for operation in CHALLENGE_BEARING:
            h.store.rows.clear()
            context = (preauth_context() if operation is AuthOperation.create_user
                       else linked_context())
            row = await h.prepared(operation, context)
            assert row.expires_at - h.clock() == timedelta(seconds=CHALLENGE_TTL_SECONDS)

        # Never client-supplied: a body asking for a longer life changes nothing.
        h.store.rows.clear()
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.prepare(AuthOperation.claim_anonymous_grant, None, linked_context(),
                                endpoint, body={"expires_at": "2099-01-01T00:00:00Z",
                                                "ttl_seconds": 86400})
        first = h.store.only()
        assert first.expires_at == h.clock() + timedelta(seconds=CHALLENGE_TTL_SECONDS)

        # Never extended and never renewed on retry: a second prepare mints a second challenge
        # and leaves the first one's expiry exactly where it was.
        h.clock.advance(120)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.prepare(AuthOperation.claim_anonymous_grant, None, linked_context(),
                                endpoint)
        assert h.store.rows[first.challenge_id].expires_at == first.expires_at
        assert len(h.store.rows) == 2

    # [utest->req~shared-challenge-ttl~1]
    def test_expiry_is_computed_from_the_issuance_clock(self):
        now = datetime(2026, 8, 16, tzinfo=UTC)
        assert challenge_expires_at(now) == now + timedelta(seconds=300)


# --- The challenge wire contract -----------------------------------------------------------


class TestWireContract:
    # [utest->req~shared-challenge-wire-contract~1]
    async def test_the_wire_contract_is_identical_for_every_challenge_bearing_operation(self, h):
        for operation in CHALLENGE_BEARING:
            h.store.rows.clear()
            context = (preauth_context() if operation is AuthOperation.create_user
                       else linked_context())
            endpoint = h.endpoint(operation)
            response = await h.service.prepare(operation, VARIANT_FOR[operation], context,
                                               endpoint)
            assert isinstance(response, PrepareResponse)
            assert set(response.model_dump()) == {"challenge_id", "expires_at"}
            assert len(base64.urlsafe_b64decode(response.challenge_id + "==")) == 16
            row = h.store.only()
            assert row.operation is operation
            assert row.operation_variant == VARIANT_FOR[operation]

    # [utest->req~shared-wire-provider-normalization~1]
    async def test_the_declared_provider_is_normalized_once_at_prepare(self, h):
        # Exact case-sensitive match against the identity-provider enumeration.
        await dispatch_state_changing(operation=AuthOperation.create_user,
                                      endpoint=h.endpoint(AuthOperation.create_user),
                                      identity=preauth_context(),
                                      query_items=[("challenge", "true")],
                                      body={"provider": "google"}, shared=h.service)
        assert h.store.only().operation_variant is IdentityProvider.google

        with pytest.raises(InvalidOperationVariantError):
            await dispatch_state_changing(operation=AuthOperation.create_user,
                                          endpoint=h.endpoint(AuthOperation.create_user),
                                          identity=preauth_context(),
                                          query_items=[("challenge", "true")],
                                          body={"provider": "Google"}, shared=h.service)
        # The default is applied at prepare and persisted like any other declaration.
        h.store.rows.clear()
        await dispatch_state_changing(operation=AuthOperation.create_user,
                                      endpoint=h.endpoint(AuthOperation.create_user),
                                      identity=preauth_context(),
                                      query_items=[("challenge", "true")], body={},
                                      shared=h.service)
        assert h.store.only().operation_variant is IdentityProvider.anonymous

    # [utest->req~shared-wire-prepare-response-fields~1]
    def test_the_prepare_response_carries_exactly_two_fields(self):
        response = PrepareResponse(challenge_id="abc", expires_at=datetime.now(UTC))
        assert set(response.model_dump()) == {"challenge_id", "expires_at"}
        assert set(PrepareResponse.model_fields) == {"challenge_id", "expires_at"}

    # [utest->req~shared-wire-challenge-id-format~1]
    def test_challenge_id_is_16_random_bytes_base64url_unpadded(self):
        ids = {new_challenge_id() for _ in range(64)}
        assert len(ids) == 64
        for value in ids:
            assert "=" not in value and "+" not in value and "/" not in value
            assert len(base64.urlsafe_b64decode(value + "==")) == 16

    # [utest->req~shared-wire-completion-body~1]
    async def test_the_completion_body_carries_the_handle_and_the_declaration(self, h):
        row = await h.prepared(AuthOperation.create_user, preauth_context())
        endpoint = h.endpoint(AuthOperation.create_user)
        result = await dispatch_state_changing(
            operation=AuthOperation.create_user, endpoint=endpoint, identity=preauth_context(),
            query_items=[], shared=h.service,
            body={"challenge_id": row.challenge_id, "provider": "anonymous", "proof": "p"})
        assert result["mutated"] == str(AuthOperation.create_user)
        assert endpoint.bodies[0]["challenge_id"] == row.challenge_id

    # [utest->req~shared-wire-exact-comparison~1]
    async def test_both_comparisons_are_exact(self, h):
        assert challenge_ids_equal("abc", "abc") is True
        assert challenge_ids_equal(" abc", "abc") is False
        assert challenge_ids_equal("ABC", "abc") is False
        assert variants_equal("google", IdentityProvider.google) is True
        assert variants_equal("Google", IdentityProvider.google) is False
        assert variants_equal(None, IdentityProvider.anonymous) is False
        assert variants_equal(None, None) is True

        # A re-padded or case-folded handle finds no challenge, even against a store whose
        # lookup would happily match it.
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        h.store.case_insensitive = True
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                     row.challenge_id.upper(), linked_context(
                                         row.binding.bound_external_identity_id), endpoint)
        assert excinfo.value.result is AuthEventResult.challenge_not_found
        assert h.store.rows[row.challenge_id].state is ChallengeState.issued

    # [utest->req~shared-wire-server-held-state~1]
    async def test_only_the_row_is_authoritative(self, h):
        context = preauth_context()
        row = await h.prepared(AuthOperation.create_user, context)
        endpoint = h.endpoint(AuthOperation.create_user)
        # The completion body's copies of the authoritative fields are ignored outright.
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "google", row.challenge_id,
                                     context, endpoint,
                                     body={"operation": "claim_anonymous_grant",
                                           "operation_variant": "google",
                                           "expires_at": "2099-01-01T00:00:00Z"})
        assert excinfo.value.result is AuthEventResult.challenge_operation_mismatch
        assert h.store.rows[row.challenge_id].operation_variant is IdentityProvider.anonymous

    # [utest->req~shared-challenge-id-as-provider-nonce~1]
    async def test_the_stored_challenge_id_is_the_provider_nonce(self, h):
        row = await h.prepared(AuthOperation.create_user, preauth_context())
        assert provider_nonce(row, NonceConvention.raw) == row.challenge_id
        assert provider_nonce(row, NonceConvention.sha256_hex) == hashlib.sha256(
            row.challenge_id.encode()).hexdigest()
        # The comparand is the stored value, never a client-supplied copy.
        forged = replace(row, challenge_id="client-supplied")
        assert provider_nonce(forged, NonceConvention.sha256_hex) != provider_nonce(
            row, NonceConvention.sha256_hex)


# --- The challenge row ---------------------------------------------------------------------


class TestChallengeRow:
    # [utest->req~shared-challenge-row-bindings~1]
    async def test_the_row_binds_at_least_the_required_fields(self, h):
        row = await h.prepared(AuthOperation.create_user, preauth_context())
        bound = persisted_bindings(row)
        assert set(bound) >= {"challenge_id", "operation", "operation_variant", "preauth_issuer",
                              "preauth_subject_hash", "expires_at"}
        assert all(bound[field] is not None for field in
                   ("challenge_id", "operation", "operation_variant", "expires_at"))

    # [utest->req~shared-challenge-row-challenge-id~1]
    async def test_the_row_binds_its_challenge_id(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        assert row.challenge_id and h.store.rows[row.challenge_id].challenge_id == row.challenge_id

    # [utest->req~shared-challenge-row-operation~1]
    async def test_the_row_binds_the_concrete_operation(self, h):
        for operation in CHALLENGE_BEARING:
            h.store.rows.clear()
            context = (preauth_context() if operation is AuthOperation.create_user
                       else linked_context())
            assert (await h.prepared(operation, context)).operation is operation

    # [utest->req~shared-challenge-row-variant~1]
    async def test_the_row_binds_the_variant_only_where_the_operation_defines_one(self, h):
        assert (await h.prepared(AuthOperation.create_user,
                                 preauth_context())).operation_variant is IdentityProvider.anonymous
        h.store.rows.clear()
        assert (await h.prepared(AuthOperation.claim_anonymous_grant)).operation_variant is None
        base = h.store.only()
        with pytest.raises(ChallengeError):
            replace(base, operation_variant=IdentityProvider.google)
        with pytest.raises(ChallengeError):
            replace(base, operation=AuthOperation.create_user)

    # [utest->req~shared-challenge-row-identity-context~1]
    async def test_the_row_binds_exactly_one_identity_context(self, h):
        linked = await h.prepared(AuthOperation.claim_anonymous_grant)
        assert linked.binding.preauth_subject_hash is None
        h.store.rows.clear()
        pre = await h.prepared(AuthOperation.create_user, preauth_context())
        assert pre.binding.bound_external_identity_id is None
        assert pre.binding.preauth_issuer == TEST_ISSUER
        with pytest.raises(ChallengeError):
            IdentityBinding()
        with pytest.raises(ChallengeError):
            IdentityBinding(bound_external_identity_id=uuid7(), preauth_issuer=TEST_ISSUER)
        # An unconsumed pre-auth row always carries the verifier.
        with pytest.raises(ChallengeError):
            replace(pre, binding=replace(pre.binding, preauth_subject_hash=None))

    # [utest->req~shared-challenge-row-expires-at~1]
    async def test_the_row_binds_its_expiry(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        assert row.expires_at == h.clock() + timedelta(seconds=CHALLENGE_TTL_SECONDS)
        assert persisted_bindings(row)["expires_at"] == row.expires_at

    # [utest->req~shared-challenge-row-lifecycle-state~1]
    async def test_the_row_binds_its_lifecycle_state_and_the_claim_attempt(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        assert row.state is ChallengeState.issued and row.claim_attempt_id is None
        claim_attempt_id = uuid7()
        assert await h.store.claim(row.challenge_id, claim_attempt_id) is ClaimOutcome.claimed
        claimed = h.store.rows[row.challenge_id]
        assert claimed.state is ChallengeState.claimed
        assert claimed.claim_attempt_id == claim_attempt_id
        assert await h.store.consume(None, row.challenge_id, claim_attempt_id) is \
            ConsumeOutcome.consumed
        assert h.store.rows[row.challenge_id].state is ChallengeState.consumed
        # An issued row never carries a claim, and a claimed row always does.
        with pytest.raises(ChallengeError):
            replace(row, claim_attempt_id=uuid7())
        with pytest.raises(ChallengeError):
            replace(row, state=ChallengeState.claimed)

    # [utest->req~shared-challenge-lifecycle-one-way~1]
    async def test_the_lifecycle_runs_one_way_only(self, h):
        assert advance_state(ChallengeState.issued, ChallengeState.claimed) is ChallengeState.claimed
        assert advance_state(ChallengeState.claimed,
                             ChallengeState.consumed) is ChallengeState.consumed
        for current, target in ((ChallengeState.claimed, ChallengeState.issued),
                                (ChallengeState.consumed, ChallengeState.issued),
                                (ChallengeState.consumed, ChallengeState.claimed),
                                (ChallengeState.issued, ChallengeState.consumed),
                                (ChallengeState.claimed, ChallengeState.claimed)):
            with pytest.raises(ChallengeError):
                advance_state(current, target)
        # And the store never reissues or reclaims a row that has left `issued`.
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        await h.store.claim(row.challenge_id, uuid7())
        assert await h.store.claim(row.challenge_id, uuid7()) is ClaimOutcome.already_used

    # [utest->req~shared-challenge-variant-immutable~1]
    async def test_a_completion_cannot_change_the_declared_variant(self, h):
        context = preauth_context()
        row = await h.prepared(AuthOperation.create_user, context)
        assert row.operation_variant is IdentityProvider.anonymous
        endpoint = h.endpoint(AuthOperation.create_user)
        # An anonymous creation challenge cannot complete registered creation.
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "google", row.challenge_id,
                                     context, endpoint)
        assert excinfo.value.result is AuthEventResult.challenge_operation_mismatch
        assert h.store.rows[row.challenge_id].operation_variant is IdentityProvider.anonymous
        assert "mutate" not in endpoint.calls

    # [utest->req~shared-challenge-not-serialized~1]
    async def test_nothing_about_the_challenge_is_serialized_to_the_client(self, h):
        endpoint = h.endpoint(AuthOperation.create_user)
        context = preauth_context()
        response = await h.service.prepare(AuthOperation.create_user, IdentityProvider.google,
                                           context, endpoint)
        row = h.store.only()
        body = response.model_dump()
        assert set(body) == {"challenge_id", "expires_at"}
        for claim in (str(row.operation), "google", TEST_ISSUER):
            assert claim not in response.challenge_id
        # A handle that did carry a claim about the challenge would be caught.
        with pytest.raises(ChallengeError):
            assert_nothing_serialized(
                PrepareResponse(challenge_id=f"v1.{row.operation}.google",
                                expires_at=row.expires_at), row)

    # [utest->req~shared-challenge-binds-no-proof-material~1]
    async def test_the_challenge_binds_no_proof_or_integrity_material(self, h):
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.prepare(AuthOperation.claim_anonymous_grant, None, linked_context(),
                                endpoint,
                                body={"device_token": "dc-token", "integrity_token": "pi-token",
                                      "restore_proof": "receipt", "target_user_id": str(uuid7())})
        row = h.store.only()
        bound = {str(value) for value in persisted_bindings(row).values()}
        assert not ({"dc-token", "pi-token", "receipt"} & bound)
        # And smuggling a proof value into a bound field fails closed.
        with pytest.raises(ChallengeError):
            assert_no_proof_material_bound(row, {"integrity_token": row.challenge_id})


# --- Common completion requirements --------------------------------------------------------


class TestCompletionRequest:
    # [utest->req~shared-completion-scope~1]
    async def test_the_completion_procedure_binds_the_challenge_bearing_subset_only(self, h):
        for operation in (AuthOperation.sync, AuthOperation.sign_out_all,
                          AuthOperation.restore_subscription):
            with pytest.raises(ChallengeScopeError):
                await h.service.complete(operation, None, "abc", linked_context(),
                                         h.endpoint(operation))
        assert h.store.calls == []

    # [utest->req~shared-completion-request-id-token~1]
    async def test_completion_requires_the_verified_id_token_context(self, h):
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, "abc",
                                     None, endpoint)
        assert excinfo.value.result is AuthEventResult.invalid_external_jwt
        assert excinfo.value.error_code == "auth_required"
        # Rejected before any challenge lookup.
        assert h.store.calls == [] and endpoint.calls == []

    # [utest->req~shared-completion-request-challenge-id~1]
    async def test_completion_echoes_the_prepared_challenge_id_verbatim(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        result = await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                          row.challenge_id, context, endpoint)
        assert result["mutated"] == str(AuthOperation.claim_anonymous_grant)
        # An empty handle is no handle at all.
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, "",
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.result is AuthEventResult.challenge_not_found

    # [utest->req~shared-completion-request-provider~1]
    async def test_completion_carries_the_same_normalized_declaration(self, h):
        context = preauth_context()
        row = await h.prepared(AuthOperation.create_user, context)
        # Omitting the declaration is a mismatch, not a defaulted re-normalization.
        endpoint = h.endpoint(AuthOperation.create_user)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, None, row.challenge_id,
                                     context, endpoint)
        assert excinfo.value.result is AuthEventResult.challenge_operation_mismatch
        h.store.rows.clear()
        row = await h.prepared(AuthOperation.create_user, context)
        endpoint = h.endpoint(AuthOperation.create_user)
        assert await h.service.complete(AuthOperation.create_user, "anonymous", row.challenge_id,
                                        context, endpoint)

    # [utest->req~shared-completion-request-proof-material~1]
    async def test_endpoint_proof_material_reaches_the_endpoint(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        body = {"challenge_id": row.challenge_id, "device_token": "dc-token"}
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, endpoint, body=body)
        assert endpoint.bodies == [body]


class TestCompletionSteps:
    # [utest->req~shared-completion-backend-obligations~1]
    async def test_the_backend_obligations_run_in_the_numbered_order(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        result = await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                          row.challenge_id, context, endpoint)
        assert h.store.calls == ["insert", "get", "claim", "consume"]
        assert endpoint.calls == ["verify_proof", "confirm_live_state", "mutate"]
        # The endpoint works on the row this attempt holds the claim on.
        state, claim_attempt_id = endpoint.challenge_states[0]
        assert state is ChallengeState.claimed
        assert h.store.rows[row.challenge_id].claim_attempt_id == claim_attempt_id
        assert result["mutated"] == str(AuthOperation.claim_anonymous_grant)

    # [utest->req~shared-completion-step-01~1]
    async def test_token_verification_failure_precedes_every_challenge_check(self, h):
        await h.prepared(AuthOperation.claim_anonymous_grant)
        h.store.calls.clear()
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, "anything",
                                     "not-a-context", h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.result is AuthEventResult.invalid_external_jwt
        assert h.store.calls == []

    # [utest->req~shared-completion-step-02~1]
    async def test_route_admission_precedes_every_challenge_check(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        h.store.calls.clear()
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     preauth_context(),
                                     h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.result is AuthEventResult.preauth_identity_not_allowed
        assert h.store.calls == []

    # [utest->req~shared-completion-step-03~1]
    async def test_a_historical_identity_is_rejected_before_every_challenge_check(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        h.store.calls.clear()
        context = VerifiedIdentityContext(issuer=TEST_ISSUER, subject="s",
                                          outcome=ResolutionOutcome.historical_identity,
                                          external_identity_id=row.binding.bound_external_identity_id)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.result is AuthEventResult.historical_identity
        assert h.store.calls == []

    # [utest->req~shared-completion-step-04~1]
    async def test_a_blocked_user_is_rejected_before_every_challenge_check(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        h.store.calls.clear()
        context = VerifiedIdentityContext(issuer=TEST_ISSUER, subject="s",
                                          outcome=ResolutionOutcome.blocked_user,
                                          external_identity_id=row.binding.bound_external_identity_id)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.result is AuthEventResult.blocked_user
        assert h.store.calls == []

    # [utest->req~shared-completion-step-05~1]
    async def test_the_row_is_located_by_the_completions_challenge_id(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, "unknown-handle",
                                     context, endpoint)
        assert excinfo.value.result is AuthEventResult.challenge_not_found
        assert endpoint.calls == []
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, h.endpoint(AuthOperation.claim_anonymous_grant))

    # [utest->req~shared-completion-step-06~1]
    async def test_operation_and_identity_bindings_are_verified(self, h):
        # A linked binding matches only the same external identity row.
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     linked_context(), h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.result is AuthEventResult.challenge_identity_mismatch

        # A pre-auth binding matches on issuer plus the recomputed verifier, even once the
        # subject has become linked.
        h.store.rows.clear()
        pre = preauth_context("subject-a")
        row = await h.prepared(AuthOperation.create_user, pre)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "anonymous", row.challenge_id,
                                     preauth_context("subject-b"),
                                     h.endpoint(AuthOperation.create_user))
        assert excinfo.value.result is AuthEventResult.challenge_identity_mismatch
        now_linked = VerifiedIdentityContext(issuer=TEST_ISSUER, subject="subject-a",
                                             outcome=ResolutionOutcome.linked,
                                             external_identity_id=uuid7())
        assert await h.service.complete(AuthOperation.create_user, "anonymous", row.challenge_id,
                                        now_linked, h.endpoint(AuthOperation.create_user))

        # A row whose verifier consumption already cleared is not compared at all.
        consumed = h.store.rows[row.challenge_id]
        assert consumed.verifier_cleared
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "anonymous", row.challenge_id,
                                     pre, h.endpoint(AuthOperation.create_user))
        assert excinfo.value.result is AuthEventResult.challenge_consumed

    # [utest->req~shared-completion-step-07~1]
    async def test_pre_claim_rejections_leave_the_challenge_unconsumed(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        # Wrong identity.
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     linked_context(), h.endpoint(AuthOperation.claim_anonymous_grant))
        # Wrong operation for this row.
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_registered_grant, None, row.challenge_id,
                                     linked_context(row.binding.bound_external_identity_id),
                                     h.endpoint(AuthOperation.claim_registered_grant))
        assert excinfo.value.result is AuthEventResult.challenge_operation_mismatch
        assert h.store.rows[row.challenge_id].state is ChallengeState.issued
        # The rightful user's in-flight challenge survives both.
        assert await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                        row.challenge_id,
                                        linked_context(row.binding.bound_external_identity_id),
                                        h.endpoint(AuthOperation.claim_anonymous_grant))

    # [utest->req~shared-completion-step-08~1]
    async def test_the_claim_is_the_serialization_point_and_the_only_expiry_check(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)

        # Expiry is evaluated at the claim and nowhere else.
        h.clock.advance(CHALLENGE_TTL_SECONDS + 1)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, endpoint)
        assert excinfo.value.result is AuthEventResult.challenge_expired
        assert excinfo.value.error_code == "challenge_required"
        # Nothing ran and nothing changed.
        assert endpoint.calls == []
        assert h.store.rows[row.challenge_id].state is ChallengeState.issued

        # An already-claimed row is a generic already-used conflict, carrying no outcome of the
        # attempt holding the claim.
        h.store.rows.clear()
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        await h.store.claim(row.challenge_id, uuid7())
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.result is AuthEventResult.challenge_consumed
        assert excinfo.value.error_code == "challenge_required"

    # [utest->req~shared-completion-step-09~1]
    async def test_the_variant_comparison_runs_on_the_claimed_row_and_consumes_it(self, h):
        context = preauth_context()
        row = await h.prepared(AuthOperation.create_user, context)
        endpoint = h.endpoint(AuthOperation.create_user)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "apple", row.challenge_id,
                                     context, endpoint)
        assert excinfo.value.result is AuthEventResult.challenge_operation_mismatch
        # Unlike the step 7 rejections, this one consumed the row.
        assert h.store.rows[row.challenge_id].state is ChallengeState.consumed
        assert endpoint.calls == []

    # [utest->req~shared-completion-step-10~1]
    async def test_proof_and_provider_work_run_after_the_claim_with_no_session_open(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, endpoint)
        assert h.trace.index("store:claim") < h.trace.index("endpoint:verify_proof")
        # No transaction, row lock or open database session is held across the provider work.
        assert endpoint.sessions_open_during_proof == [0]

    # [utest->req~shared-completion-step-11~1]
    async def test_live_state_is_reconfirmed_inside_the_consuming_transaction(self, h):
        row = await h.prepared(AuthOperation.create_user, preauth_context())
        context = preauth_context()
        endpoint = h.endpoint(AuthOperation.create_user,
                              live=AuthEventResult.identity_already_linked)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "anonymous", row.challenge_id,
                                     context, endpoint)
        assert excinfo.value.result is AuthEventResult.identity_already_linked
        assert endpoint.calls == ["verify_proof", "confirm_live_state"]
        assert h.factory.opened == 1
        assert h.store.rows[row.challenge_id].state is ChallengeState.consumed

        # Historical and blocked state is re-verified there too, to close the race, and that
        # rejection is audited and consumes the claimed row like any other.
        h.store.rows.clear()
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant,
                              live=AuthEventResult.blocked_user)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, endpoint)
        assert excinfo.value.error_code == "account_unavailable"
        assert h.sink.results()[-1] is AuthEventResult.blocked_user
        assert h.store.rows[row.challenge_id].state is ChallengeState.consumed

    # [utest->req~shared-completion-step-12~1]
    async def test_consumption_is_atomic_with_the_audit_row_and_retried_under_one_claim(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        endpoint.transient_left = 1
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, endpoint)
        consumed = h.store.rows[row.challenge_id]
        assert consumed.state is ChallengeState.consumed
        # The retry ran the same local transaction under the same claim, and never repeated the
        # provider call that already ran.
        assert endpoint.calls.count("verify_proof") == 1
        assert endpoint.calls.count("mutate") == 2
        assert h.factory.opened == 2
        # One audit row, written inside the transaction that consumed the challenge.
        assert h.sink.results() == [AuthEventResult.succeeded]
        assert h.factory.sessions[-1].committed is True

    # [utest->req~shared-completion-step-13~1]
    async def test_the_mutation_runs_only_when_the_live_state_still_allows_it(self, h):
        row = await h.prepared(AuthOperation.claim_registered_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_registered_grant,
                              live=AuthEventResult.policy_rejected)
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_registered_grant, None, row.challenge_id,
                                     context, endpoint)
        assert "mutate" not in endpoint.calls

        h.store.rows.clear()
        row = await h.prepared(AuthOperation.claim_registered_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_registered_grant)
        await h.service.complete(AuthOperation.claim_registered_grant, None, row.challenge_id,
                                 context, endpoint)
        assert "mutate" in endpoint.calls

    # [utest->req~shared-completion-step-14~1]
    async def test_completion_returns_the_backend_state_and_reissues_no_token(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        result = await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                          row.challenge_id, context,
                                          h.endpoint(AuthOperation.claim_anonymous_grant))
        assert result == {"mutated": str(AuthOperation.claim_anonymous_grant),
                          "proof": {"proof_for": row.challenge_id}}
        assert "token" not in result

    # [utest->req~shared-completion-rejection-precedence~1]
    async def test_the_earliest_failed_step_is_the_one_that_rejects(self, h):
        row = await h.prepared(AuthOperation.create_user, preauth_context())
        h.clock.advance(CHALLENGE_TTL_SECONDS + 1)
        # This request fails the barrier's route rule (step 2), the identity binding (step 6),
        # expiry (step 8) and the variant comparison (step 9) all at once, on an endpoint whose
        # proof would also fail. It is rejected for the earliest of them.
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, "apple",
                                     row.challenge_id, preauth_context("other"),
                                     h.endpoint(AuthOperation.claim_anonymous_grant,
                                                proof=AuthEventResult.proof_malformed))
        assert excinfo.value.result is AuthEventResult.preauth_identity_not_allowed
        # Drop the route rule and the identity mismatch is next, still ahead of expiry.
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "apple", row.challenge_id,
                                     preauth_context("other"),
                                     h.endpoint(AuthOperation.create_user,
                                                proof=AuthEventResult.proof_malformed))
        assert excinfo.value.result is AuthEventResult.challenge_identity_mismatch
        # Drop that too and expiry rejects ahead of the variant comparison.
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "apple", row.challenge_id,
                                     preauth_context(),
                                     h.endpoint(AuthOperation.create_user,
                                                proof=AuthEventResult.proof_malformed))
        assert excinfo.value.result is AuthEventResult.challenge_expired

    # [utest->req~shared-completion-proof-after-claim~1]
    async def test_proof_verification_runs_after_the_claim_and_never_before(self, h):
        row = await h.prepared(AuthOperation.create_user, preauth_context())
        # A wrong-identity presentation neither claims nor consumes, and runs no proof.
        endpoint = h.endpoint(AuthOperation.create_user, proof=AuthEventResult.proof_malformed)
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.create_user, "anonymous", row.challenge_id,
                                     preauth_context("someone-else"), endpoint)
        assert endpoint.calls == []
        assert h.store.rows[row.challenge_id].state is ChallengeState.issued

        # The rightful caller claims first, then verifies proof; a rejected proof consumes.
        endpoint = h.endpoint(AuthOperation.create_user, proof=AuthEventResult.proof_malformed)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.create_user, "anonymous", row.challenge_id,
                                     preauth_context(), endpoint)
        assert excinfo.value.result is AuthEventResult.proof_malformed
        assert h.store.calls == ["insert", "get", "get", "claim", "consume"]
        assert h.store.rows[row.challenge_id].state is ChallengeState.consumed

    # [utest->req~shared-completion-loser-no-work~1]
    async def test_the_attempt_that_loses_the_claim_performs_no_endpoint_work(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        winner = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, winner)
        loser = h.endpoint(AuthOperation.claim_anonymous_grant)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, loser)
        assert excinfo.value.result is AuthEventResult.challenge_consumed
        # No proof verification, no provider call, no live-state read, no mutation, and never an
        # idempotent repeat of the winner's result.
        assert loser.calls == []

    # [utest->req~shared-claimed-challenge-is-dead~1]
    async def test_a_claimed_challenge_is_dead(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        # A failure after the claim consumes the row.
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant,
                                                         proof=AuthEventResult.proof_malformed))
        assert h.store.rows[row.challenge_id].state is ChallengeState.consumed

        # An attempt abandoned after claiming leaves the row `claimed` forever: no later attempt
        # reclaims it, and nothing returns it to `issued`.
        h.store.rows.clear()
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        await h.store.claim(row.challenge_id, uuid7())
        for _ in range(2):
            with pytest.raises(ChallengeRejection) as excinfo:
                await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                         row.challenge_id, context,
                                         h.endpoint(AuthOperation.claim_anonymous_grant))
            assert excinfo.value.result is AuthEventResult.challenge_consumed
        assert h.store.rows[row.challenge_id].state is ChallengeState.claimed

    # [utest->req~shared-serialization-mechanism-scope~1]
    async def test_the_mechanism_is_one_claim_state_and_two_conditional_updates(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, endpoint)
        # Exactly two mutating store calls, and no database work at all around the provider call.
        assert h.store.calls == ["insert", "get", "claim", "consume"]
        assert endpoint.sessions_open_during_proof == [0]
        # No lease, no recovery scan, no cleanup job, no reclaim path.
        surface_names = {name for name in dir(ChallengeStore) if not name.startswith("_")}
        assert surface_names == {"insert", "get", "claim", "consume"}
        # The claim is one conditional UPDATE gated on the state and the expiry; the consume is
        # one conditional UPDATE gated on this attempt's claim, and re-checks no expiry.
        claim_sql = str(CLAIM_CHALLENGE).lower()
        consume_sql = str(CONSUME_CHALLENGE).lower()
        assert claim_sql.count("update") == 1 and "claimed_at is null" in claim_sql
        assert "expires_at > now()" in claim_sql
        assert consume_sql.count("update") == 1 and "claim_attempt_id = :claim_attempt_id" in consume_sql
        assert "expires_at" not in consume_sql
        assert "for update" not in claim_sql and "for update" not in consume_sql

    # [utest->req~shared-completion-mode-signal-invalid~1]
    async def test_both_signals_or_neither_is_invalid_request_before_any_challenge_work(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        h.store.calls.clear()
        context = linked_context(row.binding.bound_external_identity_id)
        for query, body in (([("challenge", "true")], {"challenge_id": row.challenge_id}),
                            ([], {})):
            endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
            with pytest.raises(ModeSignalError) as excinfo:
                await dispatch_state_changing(operation=AuthOperation.claim_anonymous_grant,
                                              endpoint=endpoint, identity=context,
                                              query_items=query, body=body, shared=h.service)
            assert excinfo.value.error_code == "invalid_request"
            assert endpoint.calls == []
        # Neither issued nor consumed a challenge.
        assert h.store.calls == []
        assert h.store.rows[row.challenge_id].state is ChallengeState.issued

    # [utest->req~shared-completion-no-fallthrough~1]
    async def test_completion_never_falls_through_to_another_operation(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_registered_grant)
        with pytest.raises(Exception) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, endpoint)
        assert "cannot complete" in str(excinfo.value)
        assert endpoint.calls == []

    # [utest->req~shared-completion-audit-obligation~1]
    async def test_every_rejection_inside_the_endpoint_is_audited_before_the_response(self, h):
        # A prepare-phase rejection.
        with pytest.raises(ChallengeRejection):
            await h.service.prepare(AuthOperation.create_user, IdentityProvider.anonymous,
                                    linked_context(), h.endpoint(AuthOperation.create_user))
        # A barrier rejection on a completion.
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, "x",
                                     preauth_context(),
                                     h.endpoint(AuthOperation.claim_anonymous_grant))
        # A pre-claim challenge rejection.
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, "x",
                                     linked_context(),
                                     h.endpoint(AuthOperation.claim_anonymous_grant))
        # A rejection inside the consuming transaction, and a success.
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant,
                                                         live=AuthEventResult.policy_rejected))
        h.store.rows.clear()
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, h.endpoint(AuthOperation.claim_anonymous_grant))
        assert h.sink.results() == [AuthEventResult.identity_already_linked,
                                    AuthEventResult.preauth_identity_not_allowed,
                                    AuthEventResult.challenge_not_found,
                                    AuthEventResult.policy_rejected,
                                    AuthEventResult.succeeded]
        # The row never carries the public capability handle.
        assert all(getattr(event, "challenge_row_id", None) != row.challenge_id
                   for event in h.sink.events)

    # [utest->req~shared-completion-taxonomy-surfacing~1]
    async def test_internal_results_surface_through_the_shared_taxonomy_only(self, h):
        assert surface(AuthEventResult.challenge_expired) == ("challenge_required", 403)
        assert surface(AuthEventResult.historical_identity) == ("account_unavailable", 403)
        assert surface(AuthEventResult.firebase_lookup_unavailable)[0] == \
            "verification_temporarily_unavailable"
        # The audited internal value is never less specific than the class returned: it equals
        # the class only for the three results this specification names identically.
        for result in (AuthEventResult.identity_already_linked,
                       AuthEventResult.preauth_identity_not_allowed,
                       AuthEventResult.verification_temporarily_unavailable):
            assert surface(result)[0] == str(result)
        # An internal result with no mapped class never reaches the client.
        with pytest.raises(UnsurfacedResultError):
            surface(AuthEventResult.native_claim_write_failed)

        # An endpoint may add its own post-barrier case, but never redefine a shared one.
        try:
            register_client_class(AuthEventResult.provider_transition_not_allowed,
                                  "operation_not_allowed", 403)
            assert surface(AuthEventResult.provider_transition_not_allowed) == \
                ("operation_not_allowed", 403)
            with pytest.raises(UnsurfacedResultError):
                register_client_class(AuthEventResult.challenge_expired, "invalid_request", 400)
        finally:
            RESULT_TO_CLASS.pop(AuthEventResult.provider_transition_not_allowed, None)

        # And a real rejection carries the specific internal result to the audit row while the
        # client sees only the shared class.
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        h.clock.advance(CHALLENGE_TTL_SECONDS + 1)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.error_code == "challenge_required"
        assert h.sink.results() == [AuthEventResult.challenge_expired]


class _Result:
    def __init__(self, row) -> None:
        self._row = row

    def first(self):
        return self._row


class _DbSession:
    """A session that replays a scripted result per `execute`."""

    def __init__(self, script: list) -> None:
        self.script = script
        self.executed: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, statement, params):
        self.executed.append((str(statement), params))
        return _Result(self.script.pop(0))

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


def _db(script: list) -> tuple[ChallengesDB, _DbSession]:
    session = _DbSession(script)

    @asynccontextmanager
    async def factory():
        yield session

    return ChallengesDB(factory), session


def _record(**overrides):
    fields = {"id": uuid7(), "challenge_id": "cid", "operation": "claim_anonymous_grant",
              "operation_variant": None, "bound_external_identity_id": uuid7(),
              "preauth_issuer": None, "preauth_subject_hash": None,
              "expires_at": datetime(2099, 1, 1, tzinfo=UTC), "claimed_at": None,
              "claim_attempt_id": None, "consumed_at": None}
    fields.update(overrides)
    return type("Record", (), fields)()


class TestChallengesDbStatements:
    """The store's SQL: the two conditional updates and the row mapping."""

    def test_the_conditional_updates_carry_their_conditions(self):
        claim = str(CLAIM_CHALLENGE).lower()
        consume = str(CONSUME_CHALLENGE).lower()
        assert "returning id" in claim and "returning id" in consume
        assert "consumed_at = now()" in consume and "preauth_subject_hash = null" in consume
        assert "consumed_at is null" in consume

    # [utest->req~shared-completion-step-08~1]
    async def test_a_missed_claim_is_classified_without_mutating_anything(self):
        # The conditional update matched no row; the follow-up read only says why.
        expired = _record(expires_at=datetime(2020, 1, 1, tzinfo=UTC))
        db, session = _db([None, expired])
        assert await db.claim("cid", uuid7()) is ClaimOutcome.expired

        claim_attempt_id = uuid7()
        claimed = _record(claimed_at=datetime.now(UTC), claim_attempt_id=claim_attempt_id)
        db, session = _db([None, claimed])
        assert await db.claim("cid", uuid7()) is ClaimOutcome.already_used

        db, session = _db([None, None])
        assert await db.claim("cid", uuid7()) is ClaimOutcome.not_found
        assert session.committed is False

        db, session = _db([object()])
        assert await db.claim("cid", uuid7()) is ClaimOutcome.claimed
        assert session.committed is True

    # [utest->req~shared-completion-step-12~1]
    async def test_consume_recognizes_this_attempts_own_claim(self):
        claim_attempt_id = uuid7()
        db, session = _db([object()])
        assert await db.consume(session, "cid", claim_attempt_id) is ConsumeOutcome.consumed

        # A retry after a lost commit acknowledgment finds its own consumption, not a conflict.
        mine = _record(claimed_at=datetime.now(UTC), consumed_at=datetime.now(UTC),
                       claim_attempt_id=claim_attempt_id, preauth_subject_hash=None)
        db, session = _db([None, mine])
        assert await db.consume(session, "cid", claim_attempt_id) is \
            ConsumeOutcome.already_consumed_by_this_attempt

        theirs = _record(claimed_at=datetime.now(UTC), consumed_at=datetime.now(UTC),
                         claim_attempt_id=uuid7(), preauth_subject_hash=None)
        db, session = _db([None, theirs])
        assert await db.consume(session, "cid", claim_attempt_id) is ConsumeOutcome.lost


class TestSingleUseSemantics:
    """One `challenge_id`, two possible outcomes, and no replay of either."""

    # [utest->req~shared-single-use-completion-outcomes~1]
    # [utest->req~shared-single-use-claim-branch~1]
    async def test_the_first_attempt_claims_and_that_attempt_consumes_the_challenge(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant)
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, endpoint)
        # It claimed the row exactly once and proceeded through one completion attempt for the
        # challenge-bound identity context and operation.
        assert h.store.calls.count("claim") == 1
        assert h.store.only().state is ChallengeState.consumed
        assert endpoint.calls == ["verify_proof", "confirm_live_state", "mutate"]

    # [utest->req~shared-single-use-claim-branch~1]
    @pytest.mark.parametrize("failure", ["proof", "live"])
    async def test_the_claiming_attempt_consumes_the_challenge_even_when_it_then_fails(
            self, h, failure):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        endpoint = h.endpoint(AuthOperation.claim_anonymous_grant,
                              **{failure: AuthEventResult.policy_rejected})
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                     row.challenge_id, context, endpoint)
        # Whether the proof or the live-state check failed, the claimed row is consumed and
        # never returns to `issued`.
        assert h.store.rows[row.challenge_id].state is ChallengeState.consumed

    # [utest->req~shared-single-use-already-used-branch~1]
    # [utest->req~shared-single-use-no-stored-result~1]
    async def test_a_second_attempt_fails_at_the_claim_with_no_provider_work(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        first = await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                         row.challenge_id, context,
                                         h.endpoint(AuthOperation.claim_anonymous_grant))
        duplicate = h.endpoint(AuthOperation.claim_anonymous_grant)
        with pytest.raises(ChallengeRejection) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                     row.challenge_id, context, duplicate)
        # It failed as already used at the claim: no proof verification, no provider call, no
        # duplicate mutation, and no stored success result handed back.
        assert duplicate.calls == []
        assert excinfo.value.result is AuthEventResult.challenge_consumed
        assert excinfo.value.error_code == "challenge_required"
        assert first["mutated"] == str(AuthOperation.claim_anonymous_grant)
        assert not hasattr(excinfo.value, "result_body")

    # [utest->req~shared-single-use-client-reconciliation~1]
    async def test_a_lost_response_is_reconciled_by_sync_or_a_fresh_attempt(self, h):
        sync_route, fresh_attempt_signal = reconciliation_options()
        # `/auth/sync` is the canonical operation that re-reads the resolved backend state.
        assert sync_route == route_for(AuthOperation.sync)
        # And the concrete endpoint's own prepare signal starts a whole fresh attempt.
        name, _, value = fresh_attempt_signal.partition("=")
        assert classify_mode([(name, value)], None).mode is RequestMode.prepare
        # The lost attempt itself is not replayable: the same challenge is refused.
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, h.endpoint(AuthOperation.claim_anonymous_grant))
        with pytest.raises(ChallengeRejection):
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                     context, h.endpoint(AuthOperation.claim_anonymous_grant))
        # A fresh prepare, by contrast, issues a whole new challenge.
        fresh = await h.service.prepare(AuthOperation.claim_anonymous_grant, None, context,
                                        h.endpoint(AuthOperation.claim_anonymous_grant))
        assert fresh.challenge_id != row.challenge_id
        assert h.store.rows[fresh.challenge_id].state is ChallengeState.issued


class TestChallengeNotFoundScope:
    # [utest->req~shared-challenge-not-found-scope~1]
    async def test_only_a_definitive_missing_row_is_challenge_not_found(self, h):
        context = linked_context()
        with pytest.raises(ChallengeRejection) as unknown:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None,
                                     "AAAAAAAAAAAAAAAAAAAAAA", context,
                                     h.endpoint(AuthOperation.claim_anonymous_grant))
        assert unknown.value.result is AuthEventResult.challenge_not_found
        # The malformed-versus-unknown detail belongs in `details`, and the raw identifier the
        # client sent is never part of the record.
        assert unknown.value.detail == "unknown_challenge_id"
        assert h.sink.events[-1].details["reason"] == "unknown_challenge_id"
        assert challenge_id_shape("not a challenge id!") == "malformed_challenge_id"
        assert all("AAAAAAAAAAAAAAAAAAAAAA" not in str(event.details)
                   for event in h.sink.events)

    # [utest->req~shared-challenge-not-found-scope~1]
    async def test_a_lookup_outage_is_not_challenge_not_found(self, h):
        async def outage(_challenge_id):
            raise RuntimeError("connection reset by peer")

        h.store.get = outage
        with pytest.raises(ChallengeLookupUnavailableError) as excinfo:
            await h.service.complete(AuthOperation.claim_anonymous_grant, None, "some-handle",
                                     linked_context(),
                                     h.endpoint(AuthOperation.claim_anonymous_grant))
        assert excinfo.value.status_code == 503
        # It stays the ordinary infrastructure failure in the audit trail too.
        assert h.sink.results() == [AuthEventResult.internal_error]
