"""Control flow only: a failed insert stops inserting and raises; durability is a schema-test claim."""
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.crud.violations import UNIQUE_VIOLATION
from nativespeaker.api.errors import IdentityAlreadyLinked
from nativespeaker.api.schemas.auth import AuthIdentity
from nativespeaker.api.services.auth import AuthService
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.purchases import StorePurchaseToken
from nativespeaker.api.tables.users import User

ISSUER = "https://securetoken.google.com/ns-rollback-test"
SUBJECT = "rollback-control-flow-subject"

# The user flushes alone, then the identity row and both tokens; every case below fails the second.
SECOND_FLUSH = 2


class _Orig(Exception):
    """The DBAPI exception SQLAlchemy wraps, carrying the one attribute the writer reads."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


def integrity_error(sqlstate: str = UNIQUE_VIOLATION) -> IntegrityError:
    return IntegrityError("INSERT INTO core.external_identities ...", {}, _Orig(sqlstate))


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


def _identity() -> AuthIdentity:
    return AuthIdentity(issuer=ISSUER, subject=SUBJECT)


async def _create(session) -> UUID:
    service = AuthService(db=session, challenge_store=ChallengesDB(), adapter=None,
                          devicecheck=None)
    return await service.create_user(identity=_identity(),
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


class TestAFailedInsertStopsInserting:
    """The function must not carry on after the conflict, and must not report success."""

    async def test_no_further_row_is_added_after_the_failure(self):
        session = _harness(integrity_error())
        await _rejected(session)

        assert session.added == session.added_at_failure

    async def test_a_failure_on_the_very_first_insert_is_not_read_as_a_lost_race(self):
        """`core.users` carries no uniqueness this insert can lose, so a violation there is a broken
        invariant: it propagates to the internal-error path rather than answering `already linked`."""
        session = _harness(integrity_error(), fail_on_flush=1)
        rejection = await _rejected(session, expect=IntegrityError)

        assert not isinstance(rejection, IdentityAlreadyLinked)
        assert [type(instance) for instance in session.added_at_failure] == [User]

    async def test_an_integrity_failure_that_is_not_a_unique_violation_propagates(self):
        """A CHECK or a foreign key is a broken invariant, and answering 409 would hide it."""
        rejection = await _rejected(_harness(integrity_error("23514")), expect=IntegrityError)

        assert not isinstance(rejection, IdentityAlreadyLinked)
