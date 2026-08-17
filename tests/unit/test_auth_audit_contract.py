"""The rejection-audit requirements and the shared `audit.auth_events` contract: which
attempts get a row, when that row is written, and what the row may and may not hold."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import pytest
import structlog
from fastapi.testclient import TestClient

from nativespeaker.api.auth.audit import (
    NO_ACTOR,
    AttemptPhase,
    AuditRowError,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEventResult,
    AuthResultCounter,
    auth_event_row,
    movement_details,
    resolved_actor,
    terminal_event,
)
from nativespeaker.api.auth.derived_identifiers import DerivationError
from nativespeaker.api.auth.operations import OPERATION_INVENTORY, AuthOperation, IdentityProvider
from nativespeaker.api.auth.procedures import ChallengeRejection, SharedChallengeService
from unit.conftest import TEST_ISSUER, make_token
from unit.test_auth_barrier import (
    FakeResolver,
    RecordingSink,
    ResolutionOutcome,
    build_app,
    make_session_factory,
    make_writer,
)
from unit.test_auth_challenges import (
    Harness,
    actor_subject_preimage,
    hasher,
    linked_context,
    preauth_context,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
SUBJECT_HASH = bytes(range(32))


def actor(provider: IdentityProvider | None = None) -> AuthActor:
    return resolved_actor("https://securetoken.google.com/test-project", SUBJECT_HASH, 1,
                          stored_provider=provider)


class TracingSink:
    """A sink that records the session each row was written on and its place in the trace."""

    def __init__(self, trace: list[str]) -> None:
        self.trace = trace
        self.events: list[Any] = []
        self.sessions: list[Any] = []
        self.committed_at_insert: list[bool] = []
        self.attempts = 0
        self.fail = False

    async def insert(self, session: Any, row: Any) -> None:
        self.attempts += 1
        if self.fail:
            raise RuntimeError("audit insert failed")
        self.trace.append("audit_insert")
        self.sessions.append(session)
        self.committed_at_insert.append(session.committed)
        self.events.append(dict(row))


class AuditHarness(Harness):
    """The shared challenge harness with the tracing sink in place of the plain one."""

    def __init__(self) -> None:
        super().__init__()
        self.sink = TracingSink(self.trace)
        self.counter = AuthResultCounter()
        self.audit = AuthAuditWriter(sink=self.sink, counter=self.counter,
                                     session_factory=self.factory, clock=self.clock)
        self.service = SharedChallengeService(store=self.store, audit=self.audit,
                                              session_factory=self.factory,
                                              subject_hasher=hasher,
                                              resolver=self.resolver, clock=self.clock)


@pytest.fixture
def h() -> AuditHarness:
    return AuditHarness()


class TestRejectionAuditRequirements:
    # [utest->req~shared-rejection-audit-required~1]
    def test_every_canonical_operation_audits_a_rejected_attempt(self):
        # All seven, challenge-bearing or not: a barrier rejection is still the attempt's row.
        for entry in OPERATION_INVENTORY:
            sink = RecordingSink()
            app = build_app([(entry.method, entry.path)],
                            resolver=FakeResolver(ResolutionOutcome.blocked_user),
                            writer=make_writer(sink=sink))
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.request(entry.method, entry.path,
                                          headers={"Authorization": f"Bearer {make_token('u')}"})
            assert response.status_code == 403
            assert [row["operation"] for row in sink.rows] == [entry.operation]
            assert [row["result"] for row in sink.rows] == [AuthEventResult.blocked_user]

    # [utest->req~shared-rejection-audit-required~1]
    async def test_a_prepare_phase_rejection_is_audited_too(self, h):
        # Not only completions: an already-linked caller rejected at `create_user` prepare owes
        # the same row, though no mutation was even attempted.
        with pytest.raises(ChallengeRejection):
            await h.service.prepare(AuthOperation.create_user, IdentityProvider.anonymous,
                                    linked_context(), h.endpoint(AuthOperation.create_user))
        assert [event["result"] for event in h.sink.events] == \
            [AuthEventResult.identity_already_linked]
        assert h.store.rows == {}

    # [utest->req~shared-rejection-audit-scope~1]
    # [utest->req~shared-auth-events-scope~1]
    def test_only_requests_on_the_audited_path_are_in_scope(self):
        sink = RecordingSink()
        counter = AuthResultCounter()
        app = build_app([("GET", "/users/me")],
                        resolver=FakeResolver(ResolutionOutcome.blocked_user),
                        writer=make_writer(sink=sink, counter=counter))
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me", headers={"Authorization": f"Bearer {make_token()}"})
        assert response.status_code == 403
        # Off the path the rejection is telemetry, never an `audit.auth_events` row.
        assert sink.rows == []
        assert counter.value(result=AuthEventResult.blocked_user, route="/users/me") == 1

    # [utest->req~shared-rejection-audit-scope~1]
    async def test_an_admission_rejection_writes_no_row(self, h):
        from nativespeaker.api.auth.flow import dispatch_state_changing
        from nativespeaker.api.auth.modes import ModeSignalError
        # The mode-signal partition belongs to the admission phase: neither signal is an
        # `invalid_request` with no audit row and no challenge touched.
        with pytest.raises(ModeSignalError):
            await dispatch_state_changing(operation=AuthOperation.claim_anonymous_grant,
                                          endpoint=h.endpoint(AuthOperation.claim_anonymous_grant),
                                          identity=linked_context(), query_items=[], body={},
                                          shared=h.service)
        assert h.sink.events == []
        assert h.store.rows == {}


class TestFailClosedWriting:
    # [utest->req~shared-audit-fail-closed~1]
    # [utest->req~shared-audit-fail-closed-success~1]
    async def test_a_success_commits_its_row_with_the_consumption(self, h):
        row = await h.prepared(AuthOperation.claim_anonymous_grant)
        context = linked_context(row.binding.bound_external_identity_id)
        await h.service.complete(AuthOperation.claim_anonymous_grant, None, row.challenge_id,
                                 context, h.endpoint(AuthOperation.claim_anonymous_grant))
        # The row is written on the consuming transaction's own session, after the challenge
        # consumption and before that transaction commits: one commit carries both.
        assert h.trace[-2:] == ["store:consume", "audit_insert"]
        assert h.sink.sessions == [h.factory.sessions[-1]]
        assert h.sink.committed_at_insert == [False]
        assert h.factory.sessions[-1].committed is True
        # The mutation's savepoint releases into that same transaction: one commit, still.
        assert h.factory.log[-5:] == ["open", "savepoint", "release_savepoint", "commit", "close"]
        assert [event["result"] for event in h.sink.events] == [AuthEventResult.succeeded]

    # [utest->req~shared-audit-fail-closed~1]
    # [utest->req~shared-audit-fail-closed-rejection~1]
    async def test_a_rejection_durably_appends_before_the_error_is_returned(self, h):
        # A barrier-phase rejection has no later transaction to carry its row, so it opens and
        # commits its own.
        with pytest.raises(ChallengeRejection):
            await h.service.prepare(AuthOperation.claim_anonymous_grant, None,
                                    preauth_context(),
                                    h.endpoint(AuthOperation.claim_anonymous_grant))
        assert h.factory.log == ["open", "commit", "close"]
        assert h.trace == ["audit_insert"]
        # Appended and committed in that one transaction, before the error reaches the client.
        assert h.sink.committed_at_insert == [False]
        assert h.sink.sessions == [h.factory.sessions[-1]]
        assert h.factory.sessions[-1].committed is True
        assert [event["result"] for event in h.sink.events] == \
            [AuthEventResult.preauth_identity_not_allowed]

    # [utest->req~shared-audit-fail-closed-not-best-effort~1]
    async def test_the_write_is_awaited_inline_and_a_failure_is_never_swallowed(self):
        trace: list[str] = []
        sink = TracingSink(trace)
        sink.fail = True
        writer = AuthAuditWriter(sink=sink, counter=AuthResultCounter(),
                                 session_factory=make_session_factory([]))
        attempt = AuthAttempt("POST", "/auth/sync")
        event = terminal_event(AttemptPhase.barrier, AuthEventResult.blocked_user,
                               operation=AuthOperation.sync, actor=actor())
        earned = ChallengeRejection(AuthEventResult.blocked_user)
        with structlog.testing.capture_logs() as logs:
            returned = await writer.record_rejection(attempt, event, earned)
        # Attempted inline before the response, not queued or deferred to a background task.
        assert sink.attempts == 1
        # A failure is logged loudly rather than silently dropped, and the client still gets
        # the rejection the attempt earned rather than a different outcome.
        assert [(entry["event"], entry["log_level"]) for entry in logs] == \
            [("auth_audit_write_failed", "error")]
        assert returned is earned


class TestTheAuthEventsRow:
    def test_the_row_is_a_chronological_record_of_on_path_attempts(self):
        for result in (AuthEventResult.succeeded, AuthEventResult.policy_rejected):
            phase = (AttemptPhase.success if result is AuthEventResult.succeeded
                     else AttemptPhase.business)
            row = auth_event_row(terminal_event(phase, result, operation=AuthOperation.sync,
                                                actor=actor()),
                                 created_at=NOW)
            assert row["created_at"] == NOW
            assert row["result"] is result

    # [utest->req~shared-auth-events-result-column~1]
    # [utest->req~shared-audit-result-code~1]
    def test_result_is_the_single_outcome_code(self):
        row = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                            operation=AuthOperation.sync, actor=actor()),
                             created_at=NOW)
        # One machine-readable code, and no second column carrying a failure reason.
        assert row["result"] is AuthEventResult.succeeded
        assert "failure_reason" not in row
        # `succeeded` is the only success code: every other value is a rejection reason and
        # must say why the request was rejected.
        rejection = auth_event_row(terminal_event(AttemptPhase.business,
                                                  AuthEventResult.policy_rejected,
                                                  operation=AuthOperation.sync, actor=actor()),
                                   created_at=NOW)
        assert rejection["details"]["failure"]["result"] == "policy_rejected"
        assert row["details"]["failure"] == {}
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                          actor=actor()), created_at=NOW)

    # [utest->req~shared-auth-events-operation-column~1]
    def test_operation_is_null_when_the_rejection_precedes_it(self):
        # A rejection before the operation was determined leaves the column NULL.
        early = auth_event_row(terminal_event(AttemptPhase.barrier,
                                              AuthEventResult.invalid_external_jwt,
                                              details={"reason": "missing_token"}),
                               created_at=NOW)
        assert early["operation"] is None
        known = auth_event_row(terminal_event(AttemptPhase.business,
                                              AuthEventResult.challenge_expired,
                                              operation=AuthOperation.create_user, actor=actor()),
                               created_at=NOW)
        assert known["operation"] is AuthOperation.create_user

    # [utest->req~shared-auth-events-actor-subject-hash~1]
    def test_the_actor_subject_is_stored_only_as_its_derived_hash(self):
        row = auth_event_row(terminal_event(AttemptPhase.business,
                                            AuthEventResult.challenge_expired,
                                            operation=AuthOperation.sync, actor=actor(),
                                            details={"subject": "raw-firebase-subject",
                                                     "sub": "raw-firebase-subject"}),
                             created_at=NOW)
        assert row["actor_subject_hash"] == SUBJECT_HASH
        assert row["actor_subject_hash_key_version"] == 1
        # There is no raw-subject column, and a raw subject smuggled into details is redacted
        # under either claim name.
        assert "actor_subject" not in row
        assert row["details"]["context"]["subject"] == "[redacted]"
        assert row["details"]["context"]["sub"] == "[redacted]"
        # Anything that is not a keyed HMAC digest is refused outright.
        short = AuthActor(issuer="iss", subject_hash=b"short", subject_hash_key_version=1)
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.policy_rejected,
                                          operation=AuthOperation.sync, actor=short),
                           created_at=NOW)

    # [utest->req~shared-auth-events-actor-fields-null~1]
    def test_invalid_external_jwt_leaves_every_actor_field_null(self):
        row = auth_event_row(terminal_event(AttemptPhase.barrier,
                                            AuthEventResult.invalid_external_jwt,
                                            # Nothing decoded from an unverified token may fill
                                            # the actor fields, whatever the caller passed.
                                            actor=actor(IdentityProvider.google),
                                            details={"reason": "bad_signature",
                                                     "route": "/auth/sync"}),
                             created_at=NOW)
        assert row["actor_issuer"] is None
        assert row["actor_subject_hash"] is None
        assert row["actor_subject_hash_key_version"] is None
        assert row["actor_provider"] is None
        # The bounded failure reason and the route stay in details.
        assert row["details"]["failure"]["reason"] == "bad_signature"
        assert row["details"]["context"]["route"] == "/auth/sync"
        # Every other result carries all three fields.
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.policy_rejected,
                                          operation=AuthOperation.sync, actor=NO_ACTOR),
                           created_at=NOW)

    # [utest->req~shared-auth-events-actor-provider~1]
    def test_actor_provider_is_populated_only_from_a_resolved_linked_row(self):
        linked = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                               operation=AuthOperation.sync,
                                               actor=actor(IdentityProvider.google)),
                                created_at=NOW)
        assert linked["actor_provider"] is IdentityProvider.google
        # A pre-auth or unlinked event — an early challenge failure included — leaves it NULL
        # rather than fabricating a value.
        unlinked = auth_event_row(terminal_event(AttemptPhase.business,
                                                 AuthEventResult.challenge_not_found,
                                                 operation=AuthOperation.create_user,
                                                 actor=actor()),
                                  created_at=NOW)
        assert unlinked["actor_provider"] is None
        fabricated = AuthActor(issuer="iss", subject_hash=SUBJECT_HASH,
                               subject_hash_key_version=1, provider="google")  # type: ignore[invalid-argument-type]
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                          operation=AuthOperation.sync, actor=fabricated),
                           created_at=NOW)

    # [utest->req~shared-auth-events-provider-source~1]
    def test_a_recorded_provider_comes_from_the_stored_column(self):
        row = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                            operation=AuthOperation.sync,
                                            actor=actor(IdentityProvider.apple)),
                             created_at=NOW)
        # The success detail mirrors the stored `core.external_identities.provider` value.
        assert row["details"]["resolved"]["provider"] == "apple"
        # A provider that did not come from the resolved row is refused, so a token claim,
        # header or client field can never become the recorded provider.
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                          operation=AuthOperation.sync, actor=actor(),
                                          details={"resolved": {"provider": "google"}}),
                           created_at=NOW)

    # [utest->req~shared-auth-events-details-redaction~1]
    def test_details_hold_no_secret_material(self):
        secrets = {"verification": {"id_token": "aaa.bbb.ccc",
                                    "attestation_blob": "AAAA",
                                    "device_token": "dt",
                                    "proof_fingerprints": ["sha256:abc"]},
                   "context": {"restore_proof": {"signed_transaction": "x"},
                               "challenge_id": "public-handle",
                               "purchase_token": "pt",
                               "raw_bytes": b"secret",
                               "loose_jwt": "eee.fff.ggg",
                               "route": "/auth/restore-subscription"}}
        row = auth_event_row(terminal_event(AttemptPhase.business,
                                            AuthEventResult.invalid_restore_proof,
                                            operation=AuthOperation.sync, actor=actor(),
                                            details=secrets),
                             created_at=NOW)
        verification = row["details"]["verification"]
        context = row["details"]["context"]
        for redacted in (verification["id_token"], verification["attestation_blob"],
                         verification["device_token"], context["restore_proof"],
                         context["challenge_id"], context["purchase_token"],
                         context["raw_bytes"], context["loose_jwt"]):
            assert redacted == "[redacted]"
        # Non-secret server-derived metadata survives.
        assert verification["proof_fingerprints"] == ["sha256:abc"]
        assert context["route"] == "/auth/restore-subscription"

    # [utest->req~shared-auth-events-record-sufficiency~1]
    def test_the_record_reconstructs_the_attempt(self):
        challenge_row_id = uuid7()
        row = auth_event_row(terminal_event(AttemptPhase.business,
                                            AuthEventResult.challenge_expired,
                                            operation=AuthOperation.claim_anonymous_grant,
                                            actor=actor(IdentityProvider.google),
                                            challenge_row_id=challenge_row_id,
                                            details={"mutation": {"partial_state": "none"},
                                                     "reason": "expired_at_claim"}),
                             created_at=NOW)
        # The verified actor, the non-secret challenge row, the operation, the verification and
        # identity metadata, what changed, and why it was rejected.
        assert row["actor_issuer"] and row["actor_subject_hash"]
        assert row["challenge_row_id"] == challenge_row_id
        assert row["operation"] is AuthOperation.claim_anonymous_grant
        assert row["details"]["verification"]["actor"] == "verified"
        assert row["details"]["resolved"]["provider"] == "google"
        assert row["details"]["mutation"] == {"partial_state": "none"}
        assert row["details"]["failure"] == {"reason": "expired_at_claim",
                                             "result": "challenge_expired"}
        # Where no verified actor existed, the record says so.
        none = auth_event_row(terminal_event(AttemptPhase.barrier,
                                             AuthEventResult.invalid_external_jwt,
                                             details={"reason": "expired"}),
                              created_at=NOW)
        assert none["details"]["verification"]["actor"] == "none"
        # The public capability handle is never the correlation id.
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.policy_rejected,
                                          operation=AuthOperation.sync, actor=actor(),
                                          challenge_row_id="public-handle"),  # type: ignore[invalid-argument-type]
                           created_at=NOW)

    # [utest->req~shared-auth-events-movement-details~1]
    @pytest.mark.parametrize("operation", [AuthOperation.restore_subscription,
                                           AuthOperation.upgrade_anonymous_to_registered])
    def test_movement_context_is_folded_into_details(self, operation):
        source, destination = uuid7(), uuid7()
        subscription, grant, purchase = uuid7(), uuid7(), uuid7()
        details = movement_details(movement_classification="cross_account",
                                   source_user_id=source,
                                   source_external_identity_id=uuid7(),
                                   destination_user_id=destination,
                                   destination_external_identity_id=uuid7(),
                                   subscription_id=subscription,
                                   access_grant_id=grant,
                                   store_purchase_id=purchase,
                                   proof_fingerprints=["sha256:abc"],
                                   store_state_verification="active")
        row = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                            operation=operation, actor=actor(),
                                            details=details),
                             created_at=NOW)
        assert row["details"]["resolved"]["source_user_id"] == source
        assert row["details"]["resolved"]["destination_user_id"] == destination
        # The touched subscription, access grant and store-purchase rows survive redaction:
        # they are non-secret resolved identifiers, not proof material.
        assert row["details"]["mutation"]["subscription_id"] == subscription
        assert row["details"]["mutation"]["access_grant_id"] == grant
        assert row["details"]["mutation"]["store_purchase_id"] == purchase
        assert row["details"]["mutation"]["movement_classification"] == "cross_account"
        assert row["details"]["verification"]["store_state_verification"] == "active"
        assert row["details"]["verification"]["proof_fingerprints"] == ["sha256:abc"]
        # A movement row without that context is not a usable movement record.
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                          operation=operation, actor=actor()),
                           created_at=NOW)


class TestTheWritePathBuildsTheRow:
    """Every durable write goes through `auth_event_row`, so nothing a sink is handed can carry
    material the row contract forbids."""

    # [utest->req~shared-auth-events-details-redaction~1]
    async def test_a_secret_in_the_events_details_never_reaches_the_sink(self):
        trace: list[str] = []
        sink = TracingSink(trace)
        writer = AuthAuditWriter(sink=sink, counter=AuthResultCounter(),
                                 session_factory=make_session_factory([]))
        event = terminal_event(
            AttemptPhase.business, AuthEventResult.invalid_restore_proof,
            operation=AuthOperation.restore_subscription, actor=actor(),
            details={"id_token": "leaked.jwt.value",
                     "restore_proof": "raw-receipt-bytes",
                     "challenge_id": "public-capability-handle",
                     "reason": "proof_rejected",
                     **movement_details(movement_classification="unclassified")})
        await writer.write_standalone(AuthAttempt("POST", "/auth/restore-subscription"), event)
        written = str(sink.events[0])
        for secret in ("leaked.jwt.value", "raw-receipt-bytes", "public-capability-handle"):
            assert secret not in written
        assert sink.events[0]["details"]["context"]["id_token"] == "[redacted]"

    # [utest->req~shared-auth-events-actor-subject-hash~1]
    # [utest->req~shared-auth-events-actor-fields-null~1]
    async def test_a_challenge_service_rejection_carries_all_three_actor_columns(self, h):
        # The challenge service and the barrier build their actor from the same keyed hasher,
        # so a rejection this service writes carries the key version too and the row is
        # buildable at all.
        with pytest.raises(ChallengeRejection):
            await h.service.prepare(AuthOperation.create_user, IdentityProvider.anonymous,
                                    linked_context(), h.endpoint(AuthOperation.create_user))
        row = h.sink.events[-1]
        context = linked_context()
        # The persisted digest is the `actor_subject_hash` family's own: the keyed HMAC over the
        # domain-separated, canonicalized preimage, not over the bare subject.
        preimage = actor_subject_preimage(context.issuer, context.subject)
        assert row["actor_issuer"] == context.issuer
        assert row["actor_subject_hash"] == hasher(preimage)[0]
        assert row["actor_subject_hash_key_version"] == hasher(preimage)[1]
        assert row["actor_subject_hash"] != hasher(context.subject)[0]

    # [utest->req~shared-audit-outcome-barrier-rejection~1]
    def test_a_barrier_rejection_row_is_built_with_its_actor_columns(self):
        sink = RecordingSink()
        app = build_app([("POST", "/auth/sync")],
                        resolver=FakeResolver(ResolutionOutcome.blocked_user),
                        writer=make_writer(sink=sink))
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/auth/sync", headers={"Authorization": f"Bearer {make_token('u1')}"})
        # The row exists at all — building it would have raised without a keyed subject hasher,
        # and the writer would then have lost the attempt's mandatory single row.
        assert len(sink.rows) == 1
        row = sink.rows[0]
        assert row["actor_issuer"] is not None
        assert len(row["actor_subject_hash"]) == 32
        assert row["actor_subject_hash_key_version"] is not None

    # The persisted digest is domain-separated and canonicalized: the same `sub` under a
    # different issuer is a different digest, and NFC/whitespace variation of the subject is not.
    # [utest->req~proof-hmac-domain-separation~1]
    # [utest->req~proof-hmac-input-canonicalization~1]
    # [utest->req~proof-family-actor-subject-hash~1]
    def test_the_barrier_digest_separates_issuers_and_canonicalizes_the_subject(self):
        from unit.test_auth_barrier import subject_hasher
        barrier_digest = subject_hasher(actor_subject_preimage(TEST_ISSUER, "sub-1"))[0]
        other_issuer = subject_hasher(
            actor_subject_preimage("https://securetoken.google.com/other", "sub-1"))[0]
        assert barrier_digest != other_issuer
        for variant in (" sub-1 ", "sub-1\n"):
            assert subject_hasher(actor_subject_preimage(TEST_ISSUER, variant))[0] == \
                barrier_digest
        # A subject carrying the preimage's own separator cannot be canonicalized at all.
        with pytest.raises(DerivationError):
            actor_subject_preimage(TEST_ISSUER, "a:b")

    # [utest->req~shared-upgrade-movement-context-required~1]
    # [utest->req~shared-restore-movement-classification~1]
    # [utest->req~shared-movement-single-audit-row~1]
    @pytest.mark.parametrize("path, operation, classification", [
        ("/auth/restore-subscription", AuthOperation.restore_subscription, "unclassified"),
        ("/auth/upgrade-anonymous", AuthOperation.upgrade_anonymous_to_registered, "upgrade"),
    ])
    def test_a_barrier_rejected_movement_attempt_still_carries_its_movement_context(
            self, path, operation, classification):
        sink = RecordingSink()
        app = build_app([("POST", path)],
                        resolver=FakeResolver(ResolutionOutcome.blocked_user),
                        writer=make_writer(sink=sink))
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(path,
                                   headers={"Authorization": f"Bearer {make_token('u1')}"})
        assert response.status_code == 403
        assert len(sink.rows) == 1
        row = sink.rows[0]
        assert row["operation"] is operation
        # Nothing was resolved yet, so every movement field is NULL — but the context is there,
        # with the classification the route owes even before branch determination.
        assert row["details"]["mutation"]["movement_classification"] == classification
        assert row["details"]["resolved"]["destination_user_id"] is None
        assert row["details"]["resolved"]["source_user_id"] is None
        assert row["details"]["verification"]["store_state_verification"] is None
