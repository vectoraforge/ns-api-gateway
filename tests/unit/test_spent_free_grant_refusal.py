"""WR-36. What the registered claim's writer answers when the account's free slot is already spent.
Driven at the writer, because every other unit suite replaces the whole writer with a recorder.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nativespeaker.api.crud.grants import ActivationOutcome, GrantsDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.tables import AccessGrantSource
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider

EVALUATED_AT = datetime(2026, 9, 9, 12, tzinfo=UTC)
ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "spent-slot-subject"
TIER_ID = "registered"


class _AddingSession:
    """A session stand-in that records what the writer added and lets its one flush succeed."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


@pytest.fixture
def identity_row() -> ExternalIdentity:
    """A google account holding no active grant at all: nothing to lock and nothing to convert."""
    return ExternalIdentity(user_id=uuid4(),
                            issuer=ISSUER,
                            subject=SUBJECT,
                            provider=IdentityProvider.google,
                            provider_uid="google-uid-stored")


@pytest.fixture
def writer(identity_row, monkeypatch) -> GrantsDB:
    """Both lock tiers empty and the re-read scripted; only the history reads vary per case."""

    async def lock_active(self, user_id):
        return []

    async def lock_effective(self, user_id, evaluated_at):
        return []

    async def resolve_existing(self, *, issuer, subject):
        return identity_row

    async def has_prior_free_grant(self, user_id):
        # The account spent its lifetime free grant: the statement behind this carries no status.
        return True

    monkeypatch.setattr(GrantsDB, "lock_active_grants", lock_active)
    monkeypatch.setattr(GrantsDB, "lock_effective_grants", lock_effective)
    monkeypatch.setattr(GrantsDB, "has_prior_free_grant", has_prior_free_grant)
    monkeypatch.setattr(IdentitiesDB, "resolve_existing", resolve_existing)
    return GrantsDB(_AddingSession())  # ty: ignore[invalid-argument-type]


def _with_registered_row(monkeypatch, present: bool, asked: list) -> None:
    async def holds_grant_of_source(self, user_id, source):
        asked.append(source)
        return present and source is AccessGrantSource.registered_account_grant

    monkeypatch.setattr(GrantsDB, "holds_grant_of_source", holds_grant_of_source)


async def _claim(writer: GrantsDB, identity_row: ExternalIdentity) -> ActivationOutcome:
    return await writer.activate_registered_account_grant(user_id=identity_row.user_id,
                                                          identity_row=identity_row,
                                                          tier_id=TIER_ID,
                                                          evaluated_at=EVALUATED_AT)


class TestASpentSlotWithNoRegisteredRowIsARefusal:
    """A grant this window never locked cannot have been taken away by a concurrent commit, and a
    caller told it lost a race pays a rollback and a re-read that can only find nothing."""

    async def test_it_is_refused_rather_than_reported_as_a_lost_race(self, writer, identity_row,
                                                                     monkeypatch):
        _with_registered_row(monkeypatch, present=False, asked=[])

        assert await _claim(writer, identity_row) is ActivationOutcome.refused

    async def test_it_writes_nothing(self, writer, identity_row, monkeypatch):
        """The control: the refusal precedes every write, so no row is added on the way out."""
        _with_registered_row(monkeypatch, present=False, asked=[])

        await _claim(writer, identity_row)

        assert writer.session.added == []


class TestARegisteredRowThisWindowDidNotSeeIsStillARace:
    """The state the branch was written for: a concurrent conversion committed the row, and the
    caller's re-read is the one thing that can answer with it."""

    async def test_it_is_reported_as_a_lost_race(self, writer, identity_row, monkeypatch):
        _with_registered_row(monkeypatch, present=True, asked=[])

        assert await _claim(writer, identity_row) is ActivationOutcome.lost_race

    async def test_the_question_asked_is_the_registered_source(self, writer, identity_row,
                                                              monkeypatch):
        """The control: a question over both free sources would answer the same for either state."""
        asked: list = []
        _with_registered_row(monkeypatch, present=True, asked=asked)

        await _claim(writer, identity_row)

        assert asked == [AccessGrantSource.registered_account_grant]
