"""Control flow only: a failed insert stops inserting and raises; durability is a schema-test claim."""
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.auth.create_user import create_user
from nativespeaker.api.auth.identity import Identity
from nativespeaker.api.errors import IdentityAlreadyLinked
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.purchases import StorePurchaseToken
from nativespeaker.api.tables.users import User

ISSUER = "https://securetoken.google.com/ns-rollback-test"
SUBJECT = "rollback-control-flow-subject"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# The user flushes alone, then the identity row and both tokens; every case below fails the second.
SECOND_FLUSH = 2


def integrity_error() -> IntegrityError:
    return IntegrityError("INSERT INTO core.external_identities ...", {},
                          Exception("synthetic uniqueness violation"))


class _EmptyResult:
    def first(self):
        return None


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

    async def exec(self, statement):
        # The in-transaction re-resolution: no row, so the creation arm runs.
        return _EmptyResult()

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


def _identity() -> Identity:
    return Identity(issuer=ISSUER, subject=SUBJECT)


async def _create(session) -> UUID:
    return await create_user(session,
                             identity=_identity(),
                             evaluated_at=NOW,
                             provider=IdentityProvider.anonymous,
                             provider_uid=None,
                             email=None)


def _harness(error: BaseException, **kwargs):
    return _FlushFailingSession(error=error, **kwargs)


async def _rejected(session, expect=IdentityAlreadyLinked):
    """Drive the conflict arm to the rejection it raises, and hand the rejection back."""
    with pytest.raises(expect) as raised:
        await _create(session)
    return raised.value


class TestAllFourRowsAreAddedInOneTransaction:
    """A user row with no identity row is the partial account this forbids."""

    async def test_all_three_row_kinds_were_pending_when_the_conflict_arrived(self):
        """One transaction over all four rows: a narrower one would leave tokens for a user that no longer exists."""
        session = _harness(integrity_error())
        await _rejected(session)

        kinds = [type(instance) for instance in session.added_at_failure]
        assert kinds.count(User) == 1
        assert kinds.count(ExternalIdentity) == 1
        assert kinds.count(StorePurchaseToken) == 2

    async def test_the_conflicting_transaction_is_neither_committed_nor_rolled_back_here(self):
        """Both boundaries belong to the route, which spends the handle in the same transaction."""
        session = _harness(integrity_error())
        await _rejected(session)

        assert (session.commits, session.rollbacks) == (0, 0)


class TestAFailedInsertStopsInserting:
    """The function must not carry on after the conflict, and must not report success."""

    async def test_no_further_row_is_added_after_the_failure(self):
        session = _harness(integrity_error())
        await _rejected(session)

        assert session.added == session.added_at_failure

    async def test_no_second_attempt_at_the_business_inserts(self):
        """A retry loop here would be a second race entrant under the same claim."""
        session = _harness(integrity_error())
        await _rejected(session)

        assert session.flushes == SECOND_FLUSH

    async def test_the_failure_is_never_swallowed_into_the_success_path(self):
        """There is no success arm left to fall into: the conflict raises, so nothing can return an id."""
        session = _harness(integrity_error())
        rejection = await _rejected(session)

        assert isinstance(rejection, IdentityAlreadyLinked)
        assert rejection.status == 409

    async def test_a_failure_on_the_very_first_insert_raises_the_same_rejection(self):
        """The user row goes in on the first flush; a conflict there earns the same answer as any other."""
        session = _harness(integrity_error(), fail_on_flush=1)
        rejection = await _rejected(session)

        assert isinstance(rejection, IdentityAlreadyLinked)
        assert [type(instance) for instance in session.added_at_failure] == [User]


class TestANonIntegrityFailureIsNotAbsorbed:
    """Fail loudly rather than answering the client something plausible and wrong."""

    async def test_a_non_integrity_failure_is_not_caught_at_all(self):
        """A connection drop must not be reshaped into a uniqueness conflict."""
        error = RuntimeError("the connection went away mid-flush")
        session = _harness(error)

        with pytest.raises(RuntimeError):
            await _create(session)

        assert session.commits == 0
