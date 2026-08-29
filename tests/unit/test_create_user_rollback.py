"""Control flow only: a failed insert stops inserting and rolls back; durability is a schema-test claim."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.auth.create_user import create_user
from nativespeaker.api.auth.exceptions import IdentityAlreadyLinked
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.purchases import StorePurchaseToken
from nativespeaker.api.tables.users import User

ISSUER = "https://securetoken.google.com/ns-rollback-test"
SUBJECT = "rollback-control-flow-subject"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# The user flushes alone, then the identity row and both tokens; every case below fails the second.
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
    """A session whose chosen `flush()` raises, snapshotting what had been added at the moment of failure."""

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


def _context() -> RequestContext:
    return RequestContext(identity=PreAuthIdentity(issuer=ISSUER, subject=SUBJECT),
                          route="/auth/create-user",
                          evaluated_at=NOW,
                          attempt_id=uuid4())


async def _create(session, store) -> UUID:
    context = _context()
    challenge = AuthChallenge(challenge_id="rollback-handle",
                              operation=AuthOperation.create_user,
                              preauth_issuer=ISSUER,
                              preauth_subject_hash=b"\x01" * 32,
                              expires_at=NOW,
                              created_at=NOW)
    return await create_user(session,
                             context=context,
                             identity=context.identity,
                             challenge=challenge,
                             provider=IdentityProvider.anonymous,
                             provider_uid=None,
                             email=None,
                             challenge_store=store)


def _harness(error: BaseException, **kwargs):
    return _FlushFailingSession(error=error, **kwargs), _ConsumingStore()


async def _rejected(session, store, expect=IdentityAlreadyLinked):
    """Drive the conflict arm to the rejection it raises, and hand the rejection back."""
    with pytest.raises(expect) as raised:
        await _create(session, store)
    return raised.value


class TestAllThreeInsertsShareOneSavepoint:
    """A user row with no identity row is the partial account this forbids."""

    async def test_the_savepoint_opens_before_the_first_insert(self):
        """Not around the last two, and not per-insert -- an insert outside it could not be undone."""
        session, store = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _rejected(session, store)

        assert session.savepoint.rolled_back is True
        assert session.savepoint.committed is False

    async def test_all_three_row_kinds_were_inside_the_savepoint_that_rolled_back(self):
        """One savepoint over all four rows: a narrower one would leave tokens for a user that no longer exists."""
        session, store = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _rejected(session, store)

        kinds = [type(instance) for instance in session.added_at_failure]
        assert kinds.count(User) == 1
        assert kinds.count(ExternalIdentity) == 1
        assert kinds.count(StorePurchaseToken) == 2


class TestAFailedInsertStopsInserting:
    """The function must not carry on after the conflict, and must not report success."""

    async def test_no_further_row_is_added_after_the_failure(self):
        session, store = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _rejected(session, store)

        assert session.added == session.added_at_failure

    async def test_no_second_attempt_at_the_business_inserts(self):
        """A retry loop here would be a second race entrant under the same claim."""
        session, store = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _rejected(session, store)

        assert session.flushes == SECOND_FLUSH

    async def test_the_failure_is_never_swallowed_into_the_success_path(self):
        """There is no success arm left to fall into: the conflict raises, so nothing can return an id."""
        session, store = _harness(integrity_error("external_identities_issuer_subject_key"))
        rejection = await _rejected(session, store)

        assert isinstance(rejection, IdentityAlreadyLinked)
        assert rejection.error_class.status == 409

    async def test_the_rejection_leaves_the_consume_to_the_route(self):
        """D-04 put the post-claim consume in `_complete`'s except arm; doing it here too spends the handle twice."""
        session, store = _harness(integrity_error("external_identities_issuer_subject_key"))
        await _rejected(session, store)

        assert store.consumed == []
        assert session.commits == 0


class TestAnUnclassifiableFailureIsNotAbsorbed:
    """Fail loudly rather than answering the client something plausible and wrong."""

    async def test_an_unmapped_constraint_propagates_after_the_savepoint_is_rolled_back(self):
        """The rollback still happens, but no business outcome is invented for a conflict nobody mapped."""
        error = integrity_error("store_purchase_tokens_provider_identity_value_key")
        session, store = _harness(error)

        with pytest.raises(IntegrityError) as raised:
            await _create(session, store)

        assert raised.value is error
        assert session.savepoint.rolled_back is True
        assert session.commits == 0

    async def test_a_non_integrity_failure_is_not_caught_at_all(self):
        """A connection drop must not be reshaped into a uniqueness conflict."""
        error = RuntimeError("the connection went away mid-flush")
        session, store = _harness(error)

        with pytest.raises(RuntimeError):
            await _create(session, store)

        assert session.commits == 0

    async def test_a_failure_on_the_very_first_insert_is_also_inside_the_savepoint(self):
        """The user row goes in on the first flush; a conflict there must undo just as cleanly."""
        session, store = _harness(integrity_error("external_identities_user_id_key"),
                                  fail_on_flush=1)
        rejection = await _rejected(session, store)

        assert isinstance(rejection, IdentityAlreadyLinked)
        assert session.savepoint.rolled_back is True
        assert [type(instance) for instance in session.added_at_failure] == [User]
