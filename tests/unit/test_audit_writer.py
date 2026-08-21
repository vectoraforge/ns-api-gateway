"""FOUND-05: the §4 audit writer -- the row it builds, and the two modes it builds it in.

Pure unit coverage against a recording stub session: no database, no application. What lives here
is everything about the *writer* -- the actor-field guard that keeps the table's all-or-nothing
CHECK from becoming an insert-time surprise, the derivation running through the one shared keyring,
redaction happening before the row reaches a session, and the rule that a failed audit write never
changes what the client is told.

`build_details` and `redact` are exercised in depth by `test_audit_details.py`; this module asserts
only that the writer *applies* them, which is a property of the writer rather than of either
function.

The live-database proof of the row shape -- the columns PostgreSQL actually accepts and the CHECKs
it actually enforces -- is `tests/e2e/test_audit_writer.py`. Neither module replaces the other: a
stub session proves the writer's logic and nothing about the schema, and the e2e module proves the
schema and cannot reach the branches a real database makes unconstructible.
"""

import ast
import base64
import inspect
from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest
from sqlalchemy import CheckConstraint

from nativespeaker.api.auth import audit
from nativespeaker.api.auth.audit import AuditWriter, build_details
from nativespeaker.api.auth.keys import HmacConfig, HmacKeyring
from nativespeaker.api.models.auth import AuthEvent, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import IdentityProvider

ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "Xy7Q1s0K2mNb3fV4"
CREATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)

# Every result but `invalid_external_jwt` requires all three actor fields non-NULL. These four are
# the ones foundation itself emits (§4.5), so they are the ones a Phase 35 caller can get wrong.
ACTOR_BEARING_RESULTS = (
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.historical_identity,
    AuthEventResult.blocked_user,
    AuthEventResult.internal_error,
)


def material(seed: int) -> str:
    """A distinct, valid 32-byte key as base64 text -- the on-disk encoding this phase pinned."""
    return base64.b64encode(bytes((seed * 37 + i) % 256 for i in range(32))).decode()


def keyring(active: int = 1, keys: dict[int, str] | None = None) -> HmacKeyring:
    return HmacKeyring(HmacConfig(active_version=active,
                                  keys=keys if keys is not None else {active: material(active)}))


class _RecordingLog:
    """A recording spy. `structlog.testing.capture_logs` is unusable in this suite (D-35-01-A), so
    the module logger is monkeypatched with this instead."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def exception(self, event: str, **kwargs) -> None:
        self.calls.append((event, kwargs))


class _StubSession:
    """Records what the writer hands it, and can be told to fail at a chosen step."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.flushes = 0
        self.exited = False
        self._fail_on = fail_on

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        self.exited = True
        return False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        if self._fail_on == "commit":
            raise RuntimeError("connection reset")
        self.commits += 1

    async def flush(self) -> None:
        if self._fail_on == "flush":
            raise RuntimeError("connection reset")
        self.flushes += 1


class _StubFactory:
    """Stands in for `app.state.session_factory` -- counts how many sessions the writer opened."""

    def __init__(self, session: _StubSession) -> None:
        self.session = session
        self.calls = 0

    def __call__(self) -> _StubSession:
        self.calls += 1
        return self.session


def rejection_details(reason: str = "missing_token") -> dict:
    return build_details(context={"route": "/auth/sync", "method": "POST"},
                         failure={"stage": "barrier", "reason": reason})


async def write_rejection(writer: AuditWriter, factory: _StubFactory, **overrides) -> None:
    """`write_standalone` for the shape a barrier rejection produces, with named overrides."""
    kwargs = dict(operation=AuthOperation.sync,
                  result=AuthEventResult.invalid_external_jwt,
                  actor_issuer=None,
                  actor_subject=None,
                  actor_provider=None,
                  challenge_row_id=None,
                  details=rejection_details(),
                  created_at=CREATED_AT)
    kwargs.update(overrides)
    await writer.write_standalone(factory, **kwargs)


class TestTheAuthEventTable:
    """The model mirrors the migration. It does not re-encode what the migration enforces."""

    def test_it_maps_the_audit_schema(self):
        """The first model in this codebase outside `core`."""
        assert AuthEvent.__tablename__ == "auth_events"
        assert AuthEvent.__table_args__ == {"schema": "audit"}

    def test_it_declares_every_column_the_migration_declares(self):
        expected = {"id", "challenge_row_id", "operation", "result", "actor_issuer",
                    "actor_subject_hash", "actor_subject_hash_key_version", "actor_provider",
                    "details", "created_at"}
        assert {c.name for c in AuthEvent.__table__.columns} == expected

    def test_the_enum_columns_name_their_postgresql_types(self):
        """The v1.6 native-enum idiom: the column carries the database's own type, not VARCHAR."""
        columns = AuthEvent.__table__.columns
        assert (columns["operation"].type.name, columns["operation"].type.schema) == \
               ("auth_operation", "core")
        assert (columns["result"].type.name, columns["result"].type.schema) == \
               ("auth_event_result", "core")
        assert (columns["actor_provider"].type.name, columns["actor_provider"].type.schema) == \
               ("identity_provider", "core")

    def test_the_subject_hash_is_bytea_and_the_key_version_is_a_smallint(self):
        """`actor_subject_hash_key_version` is SMALLINT, which is why `HmacConfig.active_version`
        is bounded to 32767 at configuration load rather than at the first insert."""
        columns = AuthEvent.__table__.columns
        assert type(columns["actor_subject_hash"].type).__name__ == "LargeBinary"
        assert type(columns["actor_subject_hash_key_version"].type).__name__ == "SmallInteger"

    def test_details_is_jsonb(self):
        assert type(AuthEvent.__table__.columns["details"].type).__name__ == "JSONB"

    def test_only_result_details_and_created_at_are_not_nullable(self):
        """`operation` is nullable: a rejection can precede operation determination. The actor
        columns are nullable because `invalid_external_jwt` carries no actor at all."""
        columns = AuthEvent.__table__.columns
        not_nullable = {c.name for c in columns if not c.nullable}
        assert not_nullable == {"id", "result", "details", "created_at"}

    def test_no_check_constraint_is_re_encoded_in_python(self):
        """The database owns the CHECKs. A Python copy is a second source of truth that can drift
        from the one that actually enforces -- the same rule `models/identities.py` states."""
        assert [c for c in AuthEvent.__table__.constraints
                if isinstance(c, CheckConstraint)] == []


class TestTheDerivationRunsThroughTheSharedKeyring:
    """§4.3 / D-21: one derivation, shared with the challenge store. Not a local reimplementation."""

    def test_the_stored_hash_is_the_keyrings_own_derivation(self):
        ring = keyring()
        row = AuditWriter(ring).build_row(operation=None,
                                          result=AuthEventResult.historical_identity,
                                          actor_issuer=ISSUER,
                                          actor_subject=SUBJECT,
                                          actor_provider=None,
                                          challenge_row_id=None,
                                          details=build_details(),
                                          created_at=CREATED_AT)
        assert row.actor_subject_hash == ring.actor_subject_hash(ISSUER, SUBJECT)
        assert len(row.actor_subject_hash) == 32

    def test_the_row_records_the_keyrings_active_version(self):
        ring = keyring(active=7, keys={3: material(3), 7: material(7)})
        row = AuditWriter(ring).build_row(operation=None,
                                          result=AuthEventResult.blocked_user,
                                          actor_issuer=ISSUER,
                                          actor_subject=SUBJECT,
                                          actor_provider=None,
                                          challenge_row_id=None,
                                          details=build_details(),
                                          created_at=CREATED_AT)
        assert row.actor_subject_hash_key_version == 7
        assert row.actor_subject_hash == ring.actor_subject_hash(ISSUER, SUBJECT, version=7)

    def test_the_module_imports_no_hashing_primitive_of_its_own(self):
        """A second derivation would drift silently: both forms produce a plausible 32-byte digest
        and only one matches the rows already written. `auth/keys.py` is the single site, so this
        module must not reach for `hmac`, `hashlib`, or `base64` at all."""
        roots: set[str] = set()
        for node in ast.walk(ast.parse(inspect.getsource(audit))):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        assert roots & {"hmac", "hashlib", "base64", "binascii"} == set()


class TestTheActorGuard:
    """T-35-09-08 / RESEARCH Pitfall 10. The all-or-nothing CHECK is the database's; the writer's
    job is to fail with a message naming the problem instead of a constraint violation."""

    @pytest.mark.parametrize("result", ACTOR_BEARING_RESULTS)
    async def test_a_missing_subject_raises_before_the_database(self, result):
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        with pytest.raises(ValueError, match="actor"):
            await write_rejection(AuditWriter(ring), factory, result=result,
                                  actor_issuer=ISSUER, actor_subject=None)
        assert factory.calls == 0
        assert session.added == []

    @pytest.mark.parametrize("result", ACTOR_BEARING_RESULTS)
    async def test_a_missing_issuer_raises_before_the_database(self, result):
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        with pytest.raises(ValueError, match="actor"):
            await write_rejection(AuditWriter(ring), factory, result=result,
                                  actor_issuer=None, actor_subject=SUBJECT)
        assert factory.calls == 0
        assert session.added == []

    async def test_an_invalid_external_jwt_row_carrying_an_actor_also_raises(self):
        """The CHECK is all-or-nothing in both directions: verification supplied no permitted
        actor, so a value in any actor column means the caller invented one."""
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        with pytest.raises(ValueError, match="actor"):
            await write_rejection(AuditWriter(ring), factory,
                                  actor_issuer=ISSUER, actor_subject=SUBJECT)
        assert factory.calls == 0

    async def test_an_invalid_external_jwt_row_carrying_a_provider_also_raises(self):
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        with pytest.raises(ValueError, match="actor"):
            await write_rejection(AuditWriter(ring), factory,
                                  actor_provider=IdentityProvider.google)
        assert factory.calls == 0

    async def test_the_same_guard_applies_to_the_in_transaction_mode(self):
        session, ring = _StubSession(), keyring()
        with pytest.raises(ValueError, match="actor"):
            await AuditWriter(ring).write_in_transaction(
                session,
                operation=AuthOperation.sync,
                result=AuthEventResult.internal_error,
                actor_issuer=None,
                actor_subject=None,
                actor_provider=None,
                challenge_row_id=None,
                details=build_details(),
                created_at=CREATED_AT)
        assert session.added == []

    async def test_a_details_object_that_is_not_the_six_key_shape_raises(self):
        """Same rationale as the actor guard: the shape is CHECK-enforced, so a caller shipping
        five keys should read a message rather than a constraint violation."""
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        with pytest.raises(ValueError, match="details"):
            await write_rejection(AuditWriter(ring), factory,
                                  details={"schema_version": 1, "context": {}})
        assert factory.calls == 0


class TestTheStandaloneDurableMode:
    """§4.1: its own session, from the factory the caller hands in, committed before the response."""

    async def test_an_all_null_actor_row_is_written_and_committed(self):
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        await write_rejection(AuditWriter(ring), factory)

        assert factory.calls == 1
        assert session.commits == 1
        assert session.exited is True
        row = session.added[0]
        assert len(session.added) == 1
        assert row.result is AuthEventResult.invalid_external_jwt
        assert (row.actor_issuer, row.actor_subject_hash,
                row.actor_subject_hash_key_version, row.actor_provider) == (None, None, None, None)

    async def test_the_row_carries_the_operation_the_challenge_row_and_the_capture_time(self):
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        challenge_row_id = uuid7()
        await write_rejection(AuditWriter(ring), factory, challenge_row_id=challenge_row_id)

        row = session.added[0]
        assert row.operation is AuthOperation.sync
        assert row.challenge_row_id == challenge_row_id
        assert row.created_at == CREATED_AT
        assert isinstance(row.id, UUID)

    async def test_the_factory_is_the_one_handed_in_not_one_captured_at_construction(self):
        """Pitfall 5: the e2e rollback fixture swaps `app.state.session_factory` per test, so a
        writer that captured a factory once would write to the real database."""
        ring = keyring()
        writer = AuditWriter(ring)
        first, second = _StubFactory(_StubSession()), _StubFactory(_StubSession())
        await write_rejection(writer, first)
        await write_rejection(writer, second)
        assert (first.calls, second.calls) == (1, 1)

    async def test_redaction_runs_before_the_row_reaches_the_session(self):
        session, ring = _StubSession(), keyring()
        factory = _StubFactory(session)
        await write_rejection(
            AuditWriter(ring), factory,
            details=build_details(failure={"reason": "bad_signature", "raw_token": "eyJhbGciOi"}))

        row = session.added[0]
        assert "raw_token" not in str(row.details)
        assert "eyJhbGciOi" not in str(row.details)
        assert row.details["failure"]["reason"] == "bad_signature"


class TestTheInTransactionMode:
    """§4.1: the caller's session, atomically with whatever else that transaction is doing."""

    async def test_it_writes_into_the_callers_session_and_does_not_commit(self):
        session, ring = _StubSession(), keyring()
        await AuditWriter(ring).write_in_transaction(
            session,
            operation=AuthOperation.sync,
            result=AuthEventResult.historical_identity,
            actor_issuer=ISSUER,
            actor_subject=SUBJECT,
            actor_provider=IdentityProvider.google,
            challenge_row_id=None,
            details=build_details(),
            created_at=CREATED_AT)

        assert len(session.added) == 1
        assert session.flushes == 1
        assert session.commits == 0
        assert session.exited is False

    async def test_both_modes_build_the_identical_row(self):
        """They differ only in the session they use and whether they commit."""
        ring = keyring()
        writer = AuditWriter(ring)
        standalone, in_transaction = _StubSession(), _StubSession()
        arguments = dict(operation=AuthOperation.sync,
                         result=AuthEventResult.blocked_user,
                         actor_issuer=ISSUER,
                         actor_subject=SUBJECT,
                         actor_provider=IdentityProvider.apple,
                         challenge_row_id=None,
                         details=rejection_details(),
                         created_at=CREATED_AT)
        await writer.write_standalone(_StubFactory(standalone), **arguments)
        await writer.write_in_transaction(in_transaction, **arguments)

        def shape(row):
            return (row.operation, row.result, row.actor_issuer, row.actor_subject_hash,
                    row.actor_subject_hash_key_version, row.actor_provider, row.challenge_row_id,
                    row.details, row.created_at)

        assert shape(standalone.added[0]) == shape(in_transaction.added[0])


class TestAFailedWriteNeverChangesTheOutcome:
    """T-35-09-07. Auditing is never best-effort, but it also never turns a business rejection
    into a 500 -- the failure is loud in the log and silent on the wire."""

    async def test_a_failing_commit_is_logged_and_not_re_raised(self, monkeypatch):
        log = _RecordingLog()
        monkeypatch.setattr(audit, "logger", log)
        factory = _StubFactory(_StubSession(fail_on="commit"))
        await write_rejection(AuditWriter(keyring()), factory)

        assert [event for event, _ in log.calls] == ["audit_write_failed"]
        assert log.calls[0][1]["result"] == str(AuthEventResult.invalid_external_jwt)

    async def test_a_failing_flush_is_logged_and_not_re_raised(self, monkeypatch):
        log = _RecordingLog()
        monkeypatch.setattr(audit, "logger", log)
        await AuditWriter(keyring()).write_in_transaction(
            _StubSession(fail_on="flush"),
            operation=AuthOperation.sync,
            result=AuthEventResult.invalid_external_jwt,
            actor_issuer=None,
            actor_subject=None,
            actor_provider=None,
            challenge_row_id=None,
            details=build_details(),
            created_at=CREATED_AT)

        assert [event for event, _ in log.calls] == ["audit_write_failed"]

    async def test_the_failure_log_carries_no_actor_subject_and_no_details(self, monkeypatch):
        """The log line is diagnostic context, not a second copy of the row. The raw subject is
        never logged (§4.3) and `details` is already on its way nowhere."""
        log = _RecordingLog()
        monkeypatch.setattr(audit, "logger", log)
        factory = _StubFactory(_StubSession(fail_on="commit"))
        await write_rejection(AuditWriter(keyring()), factory,
                              result=AuthEventResult.blocked_user,
                              actor_issuer=ISSUER, actor_subject=SUBJECT)

        rendered = str(log.calls[0][1])
        assert SUBJECT not in rendered
        assert "missing_token" not in rendered
