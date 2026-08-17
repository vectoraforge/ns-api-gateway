"""`audit.auth_events` as the schema file defines it: which attempts appear, what each column
means, what `details` may hold, and the rows the two challenge-free operations owe.

The structural expectations are transcribed from the specification's schema fence; the
behavioural ones exercise the one insertion path every durable row goes through.
"""

import re
from datetime import UTC, datetime
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import (
    BARRIER_RESULTS,
    DETAIL_SECTIONS,
    INVALID_EXTERNAL_JWT_REASONS,
    MOVEMENT_OPERATIONS,
    NO_ACTOR,
    RESULT_PRODUCERS,
    REVOCATION_FAILURE_FIELDS,
    AttemptPhase,
    AuditRowError,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEvent,
    AuthEventResult,
    AuthResultCounter,
    InvalidTerminalOutcomeError,
    OffPathAuditError,
    RevocationErrorCategory,
    auth_event_row,
    movement_details,
    required_by,
    resolved_actor,
    sign_out_all_event,
    sync_event,
    terminal_event,
)
from nativespeaker.api.auth.operations import (
    OPERATION_INVENTORY,
    AuthOperation,
    IdentityProvider,
)
from nativespeaker.api.auth.tokens import JwtRejectionReason
from nativespeaker.api.database.audit import (
    AUDIT_UPDATE_ENFORCEMENT_MECHANISMS,
    INSERT_AUTH_EVENT,
    NORMAL_FLOW_STATEMENTS,
)
from unit.test_schema_ddl import MIGRATION, Schema, declarative_section, parse

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
SUBJECT_HASH = bytes(range(32))
ISSUER = "https://securetoken.google.com/test-project"


@pytest.fixture(scope="module")
def applied() -> Schema:
    return parse(declarative_section(MIGRATION.read_text()))


def actor(provider: IdentityProvider | None = None) -> AuthActor:
    return resolved_actor(ISSUER, SUBJECT_HASH, 1, stored_provider=provider)


class RecordingSink:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def insert(self, session, row) -> None:
        self.rows.append(dict(row))


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None


def make_writer(sink: RecordingSink) -> AuthAuditWriter:
    return AuthAuditWriter(sink=sink, counter=AuthResultCounter(),
                           session_factory=FakeSession, clock=lambda: NOW)


# --- The table's purpose ------------------------------------------------------------------------

# [utest->req~schema-auth-events-purpose~1]
async def test_one_row_per_on_path_attempt_and_none_for_any_other_route():
    sink = RecordingSink()
    writer = make_writer(sink)
    for entry in OPERATION_INVENTORY:
        attempt = AuthAttempt(entry.method, entry.path)
        details = (movement_details(movement_classification="unclassified")
                   if entry.operation in MOVEMENT_OPERATIONS else None)
        await writer.write_standalone(
            attempt, terminal_event(AttemptPhase.business, AuthEventResult.policy_rejected,
                                    operation=entry.operation, actor=actor(), details=details))
    assert [row["operation"] for row in sink.rows] == \
        [entry.operation for entry in OPERATION_INVENTORY]
    # A rejection on any other authenticated route writes no row at all.
    off_path = AuthAttempt("POST", "/chats")
    with pytest.raises(OffPathAuditError):
        await writer.write_standalone(
            off_path, terminal_event(AttemptPhase.barrier, AuthEventResult.blocked_user,
                                     actor=actor()))
    assert len(sink.rows) == len(OPERATION_INVENTORY)


# [utest->req~schema-auth-events-purpose~1]
def test_normal_flows_only_append_and_no_mechanism_prevents_a_repair_update():
    statement = str(INSERT_AUTH_EVENT).upper()
    assert NORMAL_FLOW_STATEMENTS == ("INSERT",)
    assert statement.strip().startswith("INSERT INTO AUDIT.AUTH_EVENTS")
    for forbidden in ("UPDATE ", "DELETE ", "TRUNCATE"):
        assert forbidden not in statement
    # Controlled DBA or support repair may still update a row, so no trigger, permission
    # boundary or other enforcement mechanism exists to prevent every audit row update.
    assert AUDIT_UPDATE_ENFORCEMENT_MECHANISMS == frozenset()
    ddl = declarative_section(MIGRATION.read_text()).upper()
    assert "CREATE TRIGGER" not in ddl
    assert "CREATE RULE" not in ddl
    assert re.search(r"\bREVOKE\b", ddl) is None


# --- The columns --------------------------------------------------------------------------------

# [utest->req~schema-auth-events-result-single-outcome-code~1]
def test_result_is_the_single_outcome_code_with_no_failure_reason_column(applied: Schema):
    events = applied.tables["audit.auth_events"]
    assert events.columns["result"] == "core.auth_event_result NOT NULL"
    assert "failure_reason" not in events.columns
    success = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                            operation=AuthOperation.sync, actor=actor()),
                             created_at=NOW)
    assert success["result"] is AuthEventResult.succeeded
    assert "failure_reason" not in success
    # Every other value is a rejection reason and must say why the attempt was rejected.
    rejection = auth_event_row(terminal_event(AttemptPhase.business,
                                              AuthEventResult.policy_rejected,
                                              operation=AuthOperation.create_user, actor=actor()),
                               created_at=NOW)
    assert rejection["details"]["failure"]["result"] == "policy_rejected"
    # A free-text outcome is not a result code.
    with pytest.raises(AuditRowError):
        auth_event_row(AuthEvent(result="policy_rejected",  # type: ignore[invalid-argument-type]
                                 operation=AuthOperation.create_user, actor=actor()),
                       created_at=NOW)


# [utest->req~schema-auth-events-operation-nullable~1]
def test_operation_is_nullable_and_holds_the_attempted_operation_when_known(applied: Schema):
    events = applied.tables["audit.auth_events"]
    # The column is the operation enum and carries no NOT NULL.
    assert events.columns["operation"] == "core.auth_operation"
    early = auth_event_row(terminal_event(AttemptPhase.barrier,
                                          AuthEventResult.invalid_external_jwt,
                                          details={"reason": "missing_token"}),
                           created_at=NOW)
    assert early["operation"] is None
    known = auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.challenge_expired,
                                          operation=AuthOperation.claim_anonymous_grant,
                                          actor=actor()),
                           created_at=NOW)
    assert known["operation"] is AuthOperation.claim_anonymous_grant


# [utest->req~schema-auth-events-challenge-row-id-non-secret~1]
def test_challenge_row_id_is_the_internal_row_id_and_never_the_public_handle(applied: Schema):
    row_id = uuid7()
    row = auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.challenge_consumed,
                                        operation=AuthOperation.create_user, actor=actor(),
                                        challenge_row_id=row_id),
                         created_at=NOW)
    assert row["challenge_row_id"] == row_id
    assert applied.tables["audit.auth_events"].columns["challenge_row_id"] == "UUID"
    # The public capability handle is a string, and it is refused in the column...
    with pytest.raises(AuditRowError):
        auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.challenge_consumed,
                                      operation=AuthOperation.create_user, actor=actor(),
                                      challenge_row_id="public-handle"),  # type: ignore[invalid-argument-type]
                       created_at=NOW)
    # ...and never duplicated into details either.
    duplicated = auth_event_row(
        terminal_event(AttemptPhase.business, AuthEventResult.challenge_consumed,
                       operation=AuthOperation.create_user, actor=actor(),
                       challenge_row_id=row_id,
                       details={"context": {"challenge_id": "public-handle"}}),
        created_at=NOW)
    assert duplicated["details"]["context"]["challenge_id"] == "[redacted]"


# [utest->req~schema-auth-events-actor-fields-derivation~1]
def test_actor_fields_derive_only_from_verified_material_and_store_no_raw_subject():
    row = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                        operation=AuthOperation.sync,
                                        actor=actor(IdentityProvider.google),
                                        details={"context": {"subject": "raw-subject"}}),
                         created_at=NOW)
    assert row["actor_issuer"] == ISSUER
    # Stored only as the derived HMAC-SHA-256 hash, with the key version that produced it.
    assert row["actor_subject_hash"] == SUBJECT_HASH
    assert len(row["actor_subject_hash"]) == 32
    assert row["actor_subject_hash_key_version"] == 1
    assert "actor_subject" not in row and "subject" not in row
    assert row["details"]["context"]["subject"] == "[redacted]"
    # For `invalid_external_jwt` no permitted actor identity exists, so all three are NULL.
    rejected = auth_event_row(terminal_event(AttemptPhase.barrier,
                                             AuthEventResult.invalid_external_jwt,
                                             actor=actor(IdentityProvider.google),
                                             details={"reason": "bad_signature"}),
                              created_at=NOW)
    assert (rejected["actor_issuer"], rejected["actor_subject_hash"],
            rejected["actor_subject_hash_key_version"]) == (None, None, None)
    # For every other result all three are non-NULL.
    with pytest.raises(AuditRowError):
        auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.policy_rejected,
                                      operation=AuthOperation.create_user, actor=NO_ACTOR),
                       created_at=NOW)
    # Something that is not a keyed digest is not an actor subject hash.
    unhashed = AuthActor(issuer=ISSUER, subject_hash=b"raw-subject",
                         subject_hash_key_version=1)
    with pytest.raises(AuditRowError):
        auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.policy_rejected,
                                      operation=AuthOperation.create_user, actor=unhashed),
                       created_at=NOW)


# [utest->req~schema-auth-events-actor-fields-derivation~1]
def test_the_row_shape_the_actor_check_constraint_enforces(applied: Schema):
    constraints = " ".join(applied.tables["audit.auth_events"].constraints)
    assert "result = 'invalid_external_jwt' AND actor_issuer IS NULL" in constraints
    assert "actor_subject_hash IS NULL" in constraints
    assert "actor_subject_hash_key_version IS NULL" in constraints
    assert "result <> 'invalid_external_jwt' AND actor_issuer IS NOT NULL" in constraints


# [utest->req~schema-auth-events-actor-provider-population~1]
def test_actor_provider_comes_from_the_stored_column_or_stays_null():
    linked = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                           operation=AuthOperation.claim_registered_grant,
                                           actor=actor(IdentityProvider.apple)),
                            created_at=NOW)
    assert linked["actor_provider"] is IdentityProvider.apple
    # An early challenge failure or a Firebase-lookup outage has no linked identity: NULL, and
    # never a fabricated value.
    for result in (AuthEventResult.challenge_not_found,
                   AuthEventResult.firebase_lookup_unavailable):
        unlinked = auth_event_row(terminal_event(AttemptPhase.business, result,
                                                 operation=AuthOperation.create_user,
                                                 actor=actor()),
                                  created_at=NOW)
        assert unlinked["actor_provider"] is None
    fabricated = AuthActor(issuer=ISSUER, subject_hash=SUBJECT_HASH,
                           subject_hash_key_version=1, provider="google")  # type: ignore[invalid-argument-type]
    with pytest.raises(AuditRowError):
        auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                      operation=AuthOperation.sync, actor=fabricated),
                       created_at=NOW)


# [utest->req~schema-auth-events-detail-provider-from-stored-column~1]
def test_a_success_detail_provider_mirrors_the_stored_provider_column():
    row = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                        operation=AuthOperation.claim_registered_grant,
                                        actor=actor(IdentityProvider.google)),
                         created_at=NOW)
    assert row["details"]["resolved"]["provider"] == "google"
    # A provider supplied by anything but the resolved row — a token claim, a header, a client
    # field — never becomes the recorded provider.
    with pytest.raises(AuditRowError):
        auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                      operation=AuthOperation.claim_registered_grant,
                                      actor=actor(),
                                      details={"resolved": {"provider": "apple"}}),
                       created_at=NOW)


# --- `details` ----------------------------------------------------------------------------------

# [utest->req~schema-auth-events-details-shape~1]
def test_details_carry_the_five_subobjects_and_the_schema_version(applied: Schema):
    assert DETAIL_SECTIONS == ("context", "verification", "resolved", "mutation", "failure")
    row = auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                        operation=AuthOperation.sync, actor=actor()),
                         created_at=NOW)
    assert set(row["details"]) == {"schema_version", *DETAIL_SECTIONS}
    # A successful event leaves `failure` empty.
    assert row["details"]["failure"] == {}
    # And the schema enforces the same shape.
    constraints = " ".join(applied.tables["audit.auth_events"].constraints)
    assert "jsonb_typeof(details) = 'object'" in constraints
    for section in DETAIL_SECTIONS:
        assert f"details ? '{section}' AND jsonb_typeof(details -> '{section}') = 'object'" \
            in constraints
    assert "details ? 'schema_version'" in constraints


# [utest->req~schema-auth-events-details-shape~1]
def test_each_subobject_receives_the_material_it_is_for():
    row = auth_event_row(
        terminal_event(AttemptPhase.business, AuthEventResult.native_claim_write_failed,
                       operation=AuthOperation.claim_anonymous_grant, actor=actor(),
                       details={"context": {"request_id": "req-1", "route": "/auth/claim"},
                                "verification": {"proof_families": ["ios_devicecheck"],
                                                 "verifier_error": "write_failed"},
                                "resolved": {"user_id": "u-1", "access_grant_id": None},
                                "mutation": {"partial_state": "native_claim_written"},
                                "failure": {"stage": "native_claim", "retryable": True}}),
        created_at=NOW)
    details = row["details"]
    assert details["context"] == {"request_id": "req-1", "route": "/auth/claim"}
    assert details["verification"]["proof_families"] == ["ios_devicecheck"]
    assert details["resolved"]["user_id"] == "u-1"
    assert details["mutation"]["partial_state"] == "native_claim_written"
    assert details["failure"]["retryable"] is True
    assert details["failure"]["stage"] == "native_claim"


# [utest->req~schema-auth-events-details-non-secret-only~1]
def test_secret_material_is_redacted_before_the_row_is_built():
    row = auth_event_row(
        terminal_event(AttemptPhase.business, AuthEventResult.proof_malformed,
                       operation=AuthOperation.claim_anonymous_grant, actor=actor(),
                       details={"verification": {"id_token": "aaa.bbb.ccc",
                                                 "attestation": "attestation-blob",
                                                 "attestation_private_key": b"private-key"},
                                "context": {"restore_proof": "raw-receipt",
                                            "purchase_token": "purchase-token-value",
                                            "signed_transaction": "signed-transaction-value",
                                            "device_identifier": "raw-idfv"},
                                "reason": "proof_rejected"}),
        created_at=NOW)
    written = str(row)
    for secret in ("aaa.bbb.ccc", "attestation-blob", "private-key", "raw-receipt",
                   "purchase-token-value", "signed-transaction-value", "raw-idfv"):
        assert secret not in written
    assert row["details"]["verification"]["id_token"] == "[redacted]"
    assert row["details"]["context"]["device_identifier"] == "[redacted]"


# [utest->req~schema-auth-events-invalid-external-jwt-detail~1]
def test_invalid_external_jwt_records_a_bounded_failed_branch_and_stays_first_class():
    assert INVALID_EXTERNAL_JWT_REASONS == {str(reason) for reason in JwtRejectionReason}
    for reason in (JwtRejectionReason.missing_token, JwtRejectionReason.malformed,
                   JwtRejectionReason.bad_signature, JwtRejectionReason.expired,
                   JwtRejectionReason.audience_mismatch, JwtRejectionReason.issuer_mismatch):
        row = auth_event_row(terminal_event(AttemptPhase.barrier,
                                            AuthEventResult.invalid_external_jwt,
                                            operation=AuthOperation.sync,
                                            details={"reason": str(reason)}),
                             created_at=NOW)
        # A first-class, queryable result value, not a generic log line.
        assert row["result"] is AuthEventResult.invalid_external_jwt
        assert row["details"]["failure"]["reason"] == str(reason)
    # An unbounded or missing branch is refused rather than written.
    for details in ({}, {"reason": "the RSA signature over segment two did not verify"}):
        with pytest.raises(AuditRowError):
            auth_event_row(terminal_event(AttemptPhase.barrier,
                                          AuthEventResult.invalid_external_jwt,
                                          operation=AuthOperation.sync, details=details),
                           created_at=NOW)


# [utest->req~schema-auth-events-invalid-external-jwt-detail~1]
def test_off_path_the_same_rejection_writes_no_row_but_keeps_its_named_result():
    sink = RecordingSink()
    writer = make_writer(sink)
    counter = AuthResultCounter()
    writer = AuthAuditWriter(sink=sink, counter=counter, session_factory=FakeSession,
                             clock=lambda: NOW)
    attempt = AuthAttempt("POST", "/chats")
    writer.record_off_path(attempt, AuthEventResult.invalid_external_jwt, reason="expired")
    assert sink.rows == []
    assert counter.value(result=AuthEventResult.invalid_external_jwt,
                         route="/chats", reason="expired") == 1


# [utest->req~schema-auth-events-record-reconstruction-sufficiency~1]
def test_a_record_reconstructs_the_actor_the_challenge_row_the_change_and_the_reason():
    challenge_row_id = uuid7()
    row = auth_event_row(
        terminal_event(AttemptPhase.business, AuthEventResult.challenge_expired,
                       operation=AuthOperation.claim_anonymous_grant,
                       actor=actor(IdentityProvider.google),
                       challenge_row_id=challenge_row_id,
                       details={"verification": {"proof_families": ["ios_devicecheck"]},
                                "mutation": {"partial_state": "none"},
                                "reason": "expired_at_claim"}),
        created_at=NOW)
    assert row["details"]["verification"]["actor"] == "verified"
    assert row["actor_issuer"] and row["actor_subject_hash"]
    assert row["challenge_row_id"] == challenge_row_id
    assert row["operation"] is AuthOperation.claim_anonymous_grant
    assert row["details"]["mutation"] == {"partial_state": "none"}
    assert row["details"]["failure"] == {"reason": "expired_at_claim",
                                         "result": "challenge_expired"}
    assert row["created_at"] == NOW
    # Where no verified actor existed the record says so explicitly.
    none = auth_event_row(terminal_event(AttemptPhase.barrier,
                                         AuthEventResult.invalid_external_jwt,
                                         details={"reason": "expired"}),
                          created_at=NOW)
    assert none["details"]["verification"]["actor"] == "none"
    # A record that carries no verified actor for a result that has one is not sufficient
    # either: the row is refused rather than written half-reconstructible.
    with pytest.raises(AuditRowError):
        auth_event_row(terminal_event(AttemptPhase.business, AuthEventResult.challenge_expired,
                                      operation=AuthOperation.claim_anonymous_grant,
                                      actor=NO_ACTOR),
                       created_at=NOW)


# [utest->req~schema-auth-events-movement-context-details~1]
@pytest.mark.parametrize("operation", [AuthOperation.restore_subscription,
                                       AuthOperation.upgrade_anonymous_to_registered])
def test_movement_context_is_the_durable_record_for_the_two_movement_operations(operation):
    source, destination, subscription = uuid7(), uuid7(), uuid7()
    grant, purchase = uuid7(), uuid7()
    row = auth_event_row(
        terminal_event(AttemptPhase.success, AuthEventResult.succeeded, operation=operation,
                       actor=actor(IdentityProvider.apple),
                       details=movement_details(movement_classification="same_account",
                                                source_user_id=source,
                                                source_external_identity_id=uuid7(),
                                                destination_user_id=destination,
                                                destination_external_identity_id=uuid7(),
                                                subscription_id=subscription,
                                                access_grant_id=grant,
                                                store_purchase_id=purchase,
                                                proof_fingerprints=["sha256:abc"],
                                                store_state_verification="verified_active")),
        created_at=NOW)
    assert row["details"]["resolved"]["source_user_id"] == source
    assert row["details"]["resolved"]["destination_user_id"] == destination
    assert row["details"]["mutation"]["subscription_id"] == subscription
    assert row["details"]["mutation"]["access_grant_id"] == grant
    assert row["details"]["mutation"]["store_purchase_id"] == purchase
    assert row["details"]["mutation"]["movement_classification"] == "same_account"
    assert row["details"]["verification"]["proof_fingerprints"] == ["sha256:abc"]
    assert row["details"]["verification"]["store_state_verification"] == "verified_active"
    # Without that context the row is not the durable movement record support can query.
    with pytest.raises(AuditRowError):
        auth_event_row(terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                                      operation=operation, actor=actor()),
                       created_at=NOW)


# --- The rows the challenge-free operations owe -------------------------------------------------

# [utest->req~schema-auth-events-sign-out-all-row~1]
def test_sign_out_all_records_the_outcome_in_result_alone():
    ok = auth_event_row(sign_out_all_event(actor=actor(IdentityProvider.google),
                                           request_id="req-7", revoked=True),
                        created_at=NOW)
    assert ok["operation"] is AuthOperation.sign_out_all
    assert ok["result"] is AuthEventResult.succeeded
    # At minimum: the operation, the hashed actor identity, the request id, the timestamp.
    assert ok["actor_subject_hash"] == SUBJECT_HASH
    assert ok["details"]["context"]["request_id"] == "req-7"
    assert ok["created_at"] == NOW
    assert ok["details"]["failure"] == {}
    # There is no second success code, so a completed revocation is ordinary success.
    assert AuthEventResult.succeeded in required_by(AuthOperation.sign_out_all)


# [utest->req~schema-auth-events-sign-out-all-row~1]
@pytest.mark.parametrize("category", list(RevocationErrorCategory))
def test_an_unconfirmed_revocation_carries_one_sanitized_category_and_no_second_outcome(category):
    row = auth_event_row(sign_out_all_event(actor=actor(), request_id="req-8", revoked=False,
                                            error_category=category),
                         created_at=NOW)
    assert row["result"] is AuthEventResult.revocation_unconfirmed
    assert row["details"]["failure"]["error_category"] == str(category)
    # `result` alone carries the outcome: no second outcome field beside it.
    assert "outcome" not in row["details"]["failure"]
    assert "revoked" not in row["details"]["failure"]
    with pytest.raises(InvalidTerminalOutcomeError):
        sign_out_all_event(actor=actor(), request_id="req-8", revoked=False,
                           error_category=category, details={"failure": {"outcome": "failed"}})
    # A definitive failure, a local dependency and an ambiguous outcome are the whole
    # vocabulary; a raw Firebase message is not expressible.
    assert {str(entry) for entry in RevocationErrorCategory} == {
        "definitive_failure", "dependency_unavailable", "ambiguous_outcome"}
    # And nothing else reaches the row: raw Firebase messages, stack traces and vendor response
    # payloads are refused rather than merged through, whatever the caller calls them.
    for forbidden in ({"firebase_message": "PERMISSION_DENIED: caller lacks permission"},
                      {"stack_trace": "Traceback (most recent call last)..."},
                      {"vendor_payload": {"code": 7}},
                      {"exception": "GoogleAuthError(...)"}):
        with pytest.raises(InvalidTerminalOutcomeError):
            sign_out_all_event(actor=actor(), request_id="req-8", revoked=False,
                               error_category=category, details={"failure": forbidden})
    # The caller's own `details.failure` keys are exactly the sanitized category; the shared row
    # builder mirrors the row's `result` in the same machine-readable vocabulary beside it, which
    # is the same outcome rather than a second one — and it can never disagree with the column.
    assert set(row["details"]["failure"]) <= REVOCATION_FAILURE_FIELDS | {"result"}
    assert row["details"]["failure"]["result"] == str(row["result"])
    # A caller-supplied `result` in `details.failure` would be a second outcome field, so it is
    # refused rather than merged: only the builder's own mirror of the column exists.
    assert "result" not in REVOCATION_FAILURE_FIELDS
    with pytest.raises(InvalidTerminalOutcomeError):
        sign_out_all_event(actor=actor(), request_id="req-8", revoked=False,
                           error_category=category, details={"failure": {"result": "revoked"}})


# [utest->req~schema-auth-events-sign-out-all-row~1]
def test_sign_out_all_needs_a_request_id_and_an_outcome_that_matches_its_category():
    with pytest.raises(InvalidTerminalOutcomeError):
        sign_out_all_event(actor=actor(), request_id="", revoked=True)
    # `revocation_unconfirmed` without a category, or success carrying one, is not a row.
    with pytest.raises(InvalidTerminalOutcomeError):
        sign_out_all_event(actor=actor(), request_id="req-9", revoked=False)
    with pytest.raises(InvalidTerminalOutcomeError):
        sign_out_all_event(actor=actor(), request_id="req-9", revoked=True,
                           error_category=RevocationErrorCategory.ambiguous_outcome)


# [utest->req~schema-auth-events-sync-row~1]
def test_the_sync_row_records_an_attempt_and_never_a_state_change():
    row = auth_event_row(sync_event(AuthEventResult.succeeded,
                                    actor=actor(IdentityProvider.google),
                                    details={"context": {"request_id": "req-1"}}),
                         created_at=NOW)
    assert row["operation"] is AuthOperation.sync
    assert row["result"] is AuthEventResult.succeeded
    # No mutation, and no challenge row: the operation is challenge-free.
    assert row["details"]["mutation"] == {}
    assert row["challenge_row_id"] is None
    with pytest.raises(InvalidTerminalOutcomeError):
        sync_event(AuthEventResult.succeeded, actor=actor(),
                   details={"mutation": {"user_id": "u-1"}})


# [utest->req~schema-auth-events-sync-row~1]
def test_a_sync_attempt_carries_the_barriers_own_result_where_the_barrier_rejected_it():
    for result in sorted(BARRIER_RESULTS):
        event = sync_event(result,
                           actor=NO_ACTOR if result is AuthEventResult.invalid_external_jwt
                           else actor(),
                           details={"reason": "missing_token"}
                           if result is AuthEventResult.invalid_external_jwt else None)
        row = auth_event_row(event, created_at=NOW)
        assert row["operation"] is AuthOperation.sync
        assert row["result"] is result
        assert row["details"]["mutation"] == {}
    # `/auth/sync` has no terminal outcome of its own beyond those and `succeeded`.
    with pytest.raises(InvalidTerminalOutcomeError):
        sync_event(AuthEventResult.challenge_expired, actor=actor())


# [utest->req~schema-auth-events-barrier-rejection-row~1]
def test_a_barrier_rejection_names_the_matched_operation_and_the_barriers_result():
    for entry in OPERATION_INVENTORY:
        attempt = AuthAttempt(entry.method, entry.path)
        # Route metadata determines the operation before the barrier runs.
        assert attempt.operation is entry.operation
        for result in sorted(BARRIER_RESULTS):
            details = ({"reason": "missing_token"}
                       if result is AuthEventResult.invalid_external_jwt
                       else {"route": entry.path})
            if entry.operation in MOVEMENT_OPERATIONS:
                details = {**details,
                           **movement_details(movement_classification="unclassified")}
            event = terminal_event(
                AttemptPhase.barrier, result, operation=attempt.operation,
                actor=actor(IdentityProvider.google), details=details)
            row = auth_event_row(event, created_at=NOW)
            assert row["operation"] is entry.operation
            assert row["result"] is result
            if result is AuthEventResult.invalid_external_jwt:
                # The actor-NULL row shape the CHECK enforces.
                assert row["actor_issuer"] is None and row["actor_provider"] is None
            else:
                # The actor the verified token or resolved identity supplied.
                assert row["actor_issuer"] == ISSUER
                assert row["actor_subject_hash"] == SUBJECT_HASH


# --- The result enum ----------------------------------------------------------------------------

# [utest->req~schema-auth-events-result-enum-closed-and-exact~1]
def test_the_result_enum_is_exactly_the_schemas_and_every_member_has_a_producer(applied: Schema):
    declared = applied.enums["core.auth_event_result"]
    assert tuple(str(result) for result in AuthEventResult) == declared
    # Every member is required by at least one operation...
    assert set(RESULT_PRODUCERS) == set(AuthEventResult)
    for result, producers in RESULT_PRODUCERS.items():
        assert producers, result
        assert producers <= set(AuthOperation)
    # ...and every operation's own results are members of the enum.
    for entry in OPERATION_INVENTORY:
        assert required_by(entry.operation) <= set(AuthEventResult)
    assert required_by(AuthOperation.sign_out_all) >= {AuthEventResult.revocation_unconfirmed,
                                                       AuthEventResult.succeeded}
    assert AuthEventResult.revocation_unconfirmed not in required_by(AuthOperation.sync)


# [utest->req~schema-auth-events-result-enum-closed-and-exact~1]
def test_result_stays_not_null_with_no_free_text_or_generic_fallback(applied: Schema):
    assert applied.tables["audit.auth_events"].columns["result"] == \
        "core.auth_event_result NOT NULL"
    # No member is a nullable or free-text fallback: each is required somewhere.
    assert all(RESULT_PRODUCERS.values())
    # `internal_error` is required by an operation of its own and stands in for nothing: an
    # operation that has no use for it never carries it.
    assert RESULT_PRODUCERS[AuthEventResult.internal_error] == \
        frozenset({AuthOperation.restore_subscription})
    assert AuthEventResult.internal_error not in required_by(AuthOperation.sync)
    # `details` supplements the code but never substitutes for it: a row with no result code
    # is refused rather than reconstructed from its details.
    with pytest.raises(AuditRowError):
        auth_event_row(AuthEvent(result=None,  # type: ignore[invalid-argument-type]
                                 operation=AuthOperation.sync, actor=actor()),
                       created_at=NOW)
