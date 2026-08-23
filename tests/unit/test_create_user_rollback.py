"""ROADMAP criterion 3, control-flow half: a failed business insert never becomes a partial account.

This is the fast feedback loop and it proves exactly one thing -- that when an insert fails, the
creation function stops inserting, rolls back to its savepoint, and never falls through into the
success path. It proves nothing about **durability**, because a stub session cannot: whether the
challenge consumption and the rejected audit row actually survive a rolled-back business insert is
a claim about what PostgreSQL committed, and `tests/schema/test_create_atomicity.py` settles it
against a real database with real commits.

The split is deliberate rather than duplicative. Control flow is cheap to check and breaks often;
durability is expensive to check and breaks rarely but silently. Running only the cheap half would
leave §02 step 12's actual requirement unproven, and running only the expensive half would make
every refactor wait on a database.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.auth.context import ClientIpBucketKind, PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import create_account
from nativespeaker.api.auth.registry import lookup
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.models.purchase_tokens import StorePurchaseToken
from nativespeaker.api.models.users import User

ISSUER = "https://securetoken.google.com/ns-rollback-test"
SUBJECT = "rollback-control-flow-subject"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# The insert order inside the savepoint: the user alone on the first flush, then the identity row
# and both attribution tokens on the second. A conflict on the second is the shape §02 step 12
# describes, and it is the second flush every case below fails.
SECOND_FLUSH = 2


class _DriverViolation(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__("synthetic uniqueness violation")
        self.constraint_name = constraint_name


def integrity_error(constraint_name: str) -> IntegrityError:
    wrapper = Exception("dialect-level wrapper")
    wrapper.__cause__ = _DriverViolation(constraint_name)
    return IntegrityError("INSERT INTO core.external_identities ...", {}, wrapper)


class _EmptyResult:
    def first(self):
        return None


class _RecordingSavepoint:
    """A savepoint that records which way it was closed, and refuses to be closed both ways."""

    def __init__(self) -> None:
        self.rolled_back = False
        self.committed = False

    async def rollback(self) -> None:
        assert not self.committed, "a released savepoint cannot then be rolled back"
        self.rolled_back = True

    async def commit(self) -> None:
        assert not self.rolled_back, "a rolled-back savepoint cannot then be released"
        self.committed = True


class _FlushFailingSession:
    """A session whose chosen `flush()` raises, recording everything the function did around it.

    `added_at_failure` is the snapshot that makes "attempted no further inserts" checkable: the
    list is frozen at the moment the failure was raised, and a later `add` would make the final
    list differ from it.
    """

    def __init__(self, *, error: BaseException, fail_on_flush: int = SECOND_FLUSH) -> None:
        self._error = error
        self._fail_on_flush = fail_on_flush
        self.added: list[object] = []
        self.added_at_failure: list[object] | None = None
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0
        self.savepoint = _RecordingSavepoint()

    async def exec(self, statement):
        # The in-transaction re-resolution: no row, so the creation arm runs.
        return _EmptyResult()

    async def begin_nested(self):
        return self.savepoint

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1
        if self.flushes == self._fail_on_flush:
            self.added_at_failure = list(self.added)
            raise self._error

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _ConsumingStore:
    def __init__(self) -> None:
        self.consumed: list[str] = []

    async def consume(self, session, *, challenge_id, claim_attempt_id, now) -> bool:
        self.consumed.append(challenge_id)
        return True


class _RecordingAuditWriter:
    """Records rather than writes, so the business `flush` counter stays the business one."""

    def __init__(self) -> None:
        self.results: list[AuthEventResult] = []

    async def write_in_transaction(self, session, **kwargs) -> None:
        self.results.append(kwargs["result"])


def _context() -> RequestContext:
    return RequestContext(identity=PreAuthIdentity(issuer=ISSUER, subject=SUBJECT),
                          route_metadata=lookup("POST", "/auth/create-user"),
                          client_ip_bucket_kind=ClientIpBucketKind.ipv4,
                          evaluated_at=NOW,
                          attempt_id=uuid4())


async def _create(session, store, writer) -> AuthEventResult:
    context = _context()
    challenge = AuthChallenge(challenge_id="rollback-handle",
                              operation=AuthOperation.create_user,
                              preauth_issuer=ISSUER,
                              preauth_subject_hash=b"\x01" * 32,
                              expires_at=NOW,
                              created_at=NOW)
    return await create_account(session,
                                context=context,
                                identity=context.identity,
                                challenge=challenge,
                                provider=IdentityProvider.anonymous,
                                provider_uid=None,
                                email=None,
                                challenge_store=store,
                                audit_writer=writer)


def _harness(error: BaseException, **kwargs):
    return _FlushFailingSession(error=error, **kwargs), _ConsumingStore(), _RecordingAuditWriter()


class TestAllThreeInsertsShareOneSavepoint:
    """T-37-45: a user row with no identity row is the partial account §02 forbids."""

    async def test_the_savepoint_opens_before_the_first_insert(self):
        """Not around the last two, and not per-insert -- an insert outside it could not be undone."""
        session, store, writer = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _create(session, store, writer)

        assert session.savepoint.rolled_back is True
        assert session.savepoint.committed is False

    async def test_all_three_row_kinds_were_inside_the_savepoint_that_rolled_back(self):
        """The user, the identity and both attribution tokens -- one savepoint over all four rows.

        A savepoint scoped around only the first two inserts would leave the attribution tokens
        committed for a user that no longer exists.
        """
        session, store, writer = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _create(session, store, writer)

        kinds = [type(instance) for instance in session.added_at_failure]
        assert kinds.count(User) == 1
        assert kinds.count(ExternalIdentity) == 1
        assert kinds.count(StorePurchaseToken) == 2


class TestAFailedInsertStopsInserting:
    """The function must not carry on after the conflict, and must not report success."""

    async def test_no_further_row_is_added_after_the_failure(self):
        session, store, writer = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _create(session, store, writer)

        assert session.added == session.added_at_failure

    async def test_no_second_attempt_at_the_business_inserts(self):
        """A retry loop here would be a second race entrant under the same claim."""
        session, store, writer = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _create(session, store, writer)

        assert session.flushes == SECOND_FLUSH

    async def test_the_failure_is_never_swallowed_into_the_success_path(self):
        session, store, writer = _harness(integrity_error("external_identities_issuer_subject_key"))
        result = await _create(session, store, writer)

        assert result is not AuthEventResult.succeeded
        assert result is AuthEventResult.identity_already_linked
        assert writer.results == [AuthEventResult.identity_already_linked]

    async def test_the_rejection_still_consumes_audits_and_commits(self):
        """§02 step 12's durability requirement, in control-flow form: the consume and the audit
        write are *reached* after the rollback. That they actually commit is the schema test's."""
        session, store, writer = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _create(session, store, writer)

        assert store.consumed == ["rollback-handle"]
        assert writer.results == [AuthEventResult.identity_already_linked]
        assert session.commits == 1


class TestAnUnclassifiableFailureIsNotAbsorbed:
    """Fail loudly rather than answering the client something plausible and wrong."""

    async def test_an_unmapped_constraint_propagates_after_the_savepoint_is_rolled_back(self):
        """The rollback still happens -- the outer transaction must be usable by whoever handles
        this -- but no business outcome is invented for a conflict nobody mapped."""
        error = integrity_error("store_purchase_tokens_provider_identity_value_key")
        session, store, writer = _harness(error)

        with pytest.raises(IntegrityError) as raised:
            await _create(session, store, writer)

        assert raised.value is error
        assert session.savepoint.rolled_back is True
        assert session.commits == 0
        assert writer.results == []

    async def test_a_non_integrity_failure_is_not_caught_at_all(self):
        """Only `IntegrityError` is a candidate for classification. A connection drop or a
        programming error must not be reshaped into a uniqueness conflict."""
        error = RuntimeError("the connection went away mid-flush")
        session, store, writer = _harness(error)

        with pytest.raises(RuntimeError):
            await _create(session, store, writer)

        assert session.commits == 0
        assert writer.results == []

    async def test_a_failure_on_the_very_first_insert_is_also_inside_the_savepoint(self):
        """The user row goes in on the first flush; a conflict there must undo just as cleanly."""
        session, store, writer = _harness(integrity_error("external_identities_user_id_key"),
                                          fail_on_flush=1)
        result = await _create(session, store, writer)

        assert result is AuthEventResult.identity_already_linked
        assert session.savepoint.rolled_back is True
        assert [type(instance) for instance in session.added_at_failure] == [User]
