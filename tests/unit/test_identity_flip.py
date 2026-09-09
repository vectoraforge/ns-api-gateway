"""What the mutable provider flip writes, and how it classifies the flush that refuses it.

The crud method is driven directly over a stub session, so its own arms are what each case runs.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.crud.violations import UNIQUE_VIOLATION
from nativespeaker.api.errors import ProviderAccountAlreadyLinked
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User

TEST_ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "firebase-subject-under-test"
PROVIDER_UID = "google-provider-uid-under-test"
EMAIL = "buyer@example.test"

REGISTERED_AT = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
NOW = REGISTERED_AT + timedelta(days=30)


class _Orig(Exception):
    """The DBAPI exception SQLAlchemy wraps, carrying the one attribute the writer reads."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


def _violation(sqlstate: str) -> IntegrityError:
    return IntegrityError("UPDATE core.external_identities ...", {}, _Orig(sqlstate))


class _StubSession:
    """A session whose `flush()` raises whatever the case handed it, or returns."""

    def __init__(self, error: BaseException | None = None) -> None:
        self._error = error
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1
        if self._error is not None:
            raise self._error


def _account(*, registered_at: datetime | None = None,
             email: str | None = None) -> tuple[ExternalIdentity, User]:
    """The stored anonymous rows the flip mutates, in whichever state the case needs."""
    user = User(id=uuid4(), registered_at=registered_at, email=email,
                created_at=REGISTERED_AT, updated_at=REGISTERED_AT)
    identity_row = ExternalIdentity(user_id=user.id,
                                    issuer=TEST_ISSUER,
                                    subject=SUBJECT,
                                    provider=IdentityProvider.anonymous,
                                    provider_uid=None)
    return identity_row, user


async def _flip(session: _StubSession, identity_row: ExternalIdentity, user: User):
    return await IdentitiesDB(session).flip_provider(evaluated_at=NOW,
                                                     identity_row=identity_row,
                                                     user=user,
                                                     provider=IdentityProvider.google,
                                                     provider_uid=PROVIDER_UID,
                                                     email=EMAIL)


@pytest.mark.asyncio
class TestTheRefusedFlipIsClassified:
    """WR-41: only the reservation index answers `provider_account_already_linked`."""

    async def test_a_unique_violation_is_the_reserved_provider_account(self):
        identity_row, user = _account()

        with pytest.raises(ProviderAccountAlreadyLinked):
            await _flip(_StubSession(_violation(UNIQUE_VIOLATION)), identity_row, user)

    @pytest.mark.parametrize("sqlstate", ["23502", "23503", "23514"])
    async def test_every_other_integrity_failure_propagates(self, sqlstate):
        """A CHECK or a foreign key is divergent stored state, never a reservation this write lost."""
        identity_row, user = _account()

        with pytest.raises(IntegrityError):
            await _flip(_StubSession(_violation(sqlstate)), identity_row, user)

    async def test_an_integrity_error_carrying_no_dbapi_exception_propagates(self):
        """Fail closed: an unreadable code is not a race, exactly as every sibling writer reads it."""
        identity_row, user = _account()

        with pytest.raises(IntegrityError):
            await _flip(_StubSession(IntegrityError("UPDATE ...", {}, None)), identity_row, user)

    async def test_a_flush_that_returns_writes_the_confirmed_provider_control(self):
        """The control: the classification above is reached by a raise, never by the ordinary path."""
        identity_row, user = _account()

        written = await _flip(_StubSession(), identity_row, user)

        assert (written, identity_row.provider_uid) == (IdentityProvider.google, PROVIDER_UID)


@pytest.mark.asyncio
class TestTheFlipSetsWhereUnsetAndNeverOverwrites:
    """WR-42: `req~users-upgrade-step-07~1` sets `registered_at` if it is NULL, as `email` already is."""

    async def test_an_unset_registration_instant_is_stamped(self):
        identity_row, user = _account()

        await _flip(_StubSession(), identity_row, user)

        assert user.registered_at == NOW

    async def test_a_stored_registration_instant_survives_the_repair(self):
        """The flip doubles as the idempotent repair for a crash-stranded upgrade; it re-registers nobody."""
        identity_row, user = _account(registered_at=REGISTERED_AT)

        await _flip(_StubSession(), identity_row, user)

        assert user.registered_at == REGISTERED_AT

    async def test_the_repair_still_records_that_it_ran(self):
        """The control: `updated_at` moves either way, so the case above is not measuring a no-op."""
        identity_row, user = _account(registered_at=REGISTERED_AT)

        await _flip(_StubSession(), identity_row, user)

        assert user.updated_at == NOW

    async def test_a_stored_email_survives_beside_it_control(self):
        """The half that was already correct, kept beside the half this case fixed."""
        identity_row, user = _account(registered_at=REGISTERED_AT, email="stored@example.test")

        await _flip(_StubSession(), identity_row, user)

        assert (user.email, user.registered_at) == ("stored@example.test", REGISTERED_AT)
