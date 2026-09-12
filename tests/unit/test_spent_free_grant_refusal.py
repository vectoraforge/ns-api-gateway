"""WR-36. What the registered claim's writer answers when the account's free slot is already spent.
Driven at the writer, because every other unit suite replaces the whole writer with a recorder.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nativespeaker.api.crud.grants import ActivationOutcome, GrantsDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    UserMonthlyUsage,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider

SEEDED_AT = datetime(2026, 9, 9, 12, tzinfo=UTC)
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

    async def lock_effective(self, user_id):
        return []

    async def resolve_existing(self, *, issuer, subject):
        return identity_row

    async def has_prior_free_grant(self, user_id):
        return True

    monkeypatch.setattr(GrantsDB, "lock_active_grants", lock_active)
    monkeypatch.setattr(GrantsDB, "lock_effective_grants", lock_effective)
    monkeypatch.setattr(GrantsDB, "has_prior_free_grant", has_prior_free_grant)
    monkeypatch.setattr(IdentitiesDB, "resolve_existing", resolve_existing)
    return GrantsDB(_AddingSession())  # ty: ignore[invalid-argument-type]


def _a_grant(source: AccessGrantSource) -> AccessGrant:
    """One active grant row, shaped as a lock tier hands one back."""
    return AccessGrant(user_id=uuid4(),
                       tier_id=TIER_ID,
                       source=source,
                       status=AccessGrantStatus.active,
                       starts_at=SEEDED_AT,
                       created_at=SEEDED_AT,
                       updated_at=SEEDED_AT)


def _locks_returning(monkeypatch, *, effective=(), marked_active=()) -> None:
    """Rescript the two lock tiers the `writer` fixture leaves empty, plus the usage lock a
    non-empty effective set makes the writer take before it decides anything."""

    async def lock_effective(self, user_id):
        return list(effective)

    async def lock_active(self, user_id):
        return list(marked_active)

    async def lock_usage(self, grant_id):
        return UserMonthlyUsage(grant_id=grant_id,
                                monthly_period="2026-09",
                                monthly_used=0,
                                created_at=SEEDED_AT,
                                updated_at=SEEDED_AT)

    monkeypatch.setattr(GrantsDB, "lock_effective_grants", lock_effective)
    monkeypatch.setattr(GrantsDB, "lock_active_grants", lock_active)
    monkeypatch.setattr(GrantsDB, "lock_usage", lock_usage)


def _with_registered_row(monkeypatch, present: bool, asked: list) -> None:
    async def holds_grant_of_source(self, user_id, source):
        asked.append(source)
        return present and source is AccessGrantSource.registered_account_grant

    monkeypatch.setattr(GrantsDB, "holds_grant_of_source", holds_grant_of_source)


async def _activate(writer: GrantsDB,
                    identity_row: ExternalIdentity) -> tuple[ActivationOutcome, str | None]:
    """The writer's own pair: what it did, and the arm it names when what it did was refuse."""
    return await writer.activate_registered_account_grant(user_id=identity_row.user_id,
                                                          issuer=identity_row.issuer,
                                                          subject=identity_row.subject,
                                                          tier_id=TIER_ID)


async def _claim(writer: GrantsDB, identity_row: ExternalIdentity) -> ActivationOutcome:
    outcome, _ = await _activate(writer, identity_row)
    return outcome


async def _cause(writer: GrantsDB, identity_row: ExternalIdentity) -> str | None:
    _, cause = await _activate(writer, identity_row)
    return cause


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


class TestEachRefusalNamesTheArmThatFiredIt:
    """WR-62: `refused` carried no label, so nine conditions left one identical, field-less line."""

    async def test_the_spent_slot_names_itself(self, writer, identity_row, monkeypatch):
        _with_registered_row(monkeypatch, present=False, asked=[])

        assert await _cause(writer, identity_row) == "spent_slot_without_a_registered_grant"

    async def test_a_claimant_this_route_does_not_serve_names_a_different_arm(self, writer,
                                                                             identity_row,
                                                                             monkeypatch):
        """Two refusals, two labels: without them an operator reads the same line for both."""
        identity_row.provider = IdentityProvider.anonymous
        _with_registered_row(monkeypatch, present=False, asked=[])

        assert await _cause(writer, identity_row) == "identity_not_registered"

    async def test_a_held_grant_of_another_source_names_its_own_arm(self, writer, identity_row,
                                                                    monkeypatch):
        """D-09(b): a `subscription` or `manual` grant is waited out, and it is not a spent slot."""
        _locks_returning(monkeypatch, effective=[_a_grant(AccessGrantSource.subscription)])
        _with_registered_row(monkeypatch, present=False, asked=[])

        assert await _cause(writer, identity_row) == "other_grant_held"

    async def test_a_row_this_window_never_locked_names_its_own_arm(self, writer, identity_row,
                                                                    monkeypatch):
        """A row `ix_access_grants_one_active_per_user` sees and the effective read does not: the
        insert would be refused by that index, so the writer fails closed rather than racing it."""
        _locks_returning(monkeypatch,
                         marked_active=[_a_grant(AccessGrantSource.anonymous_device_grant)])
        _with_registered_row(monkeypatch, present=False, asked=[])

        assert await _cause(writer, identity_row) == "unseen_active_grant"

    async def test_a_lifetime_registered_row_on_the_conversion_arm_names_its_own_arm(
            self, writer, identity_row, monkeypatch):
        """D-09(e) on the conversion arm, where it is the only guard: `has_prior_free_grant` is
        true of every conversion, so the lifetime `(user_id, source)` question -- which one revoked
        registered row is enough to answer -- is what refuses a second registered slot here."""
        _locks_returning(monkeypatch,
                         effective=[_a_grant(AccessGrantSource.anonymous_device_grant)])
        _with_registered_row(monkeypatch, present=True, asked=[])

        assert await _cause(writer, identity_row) == "registered_grant_held"

    async def test_a_lost_race_names_no_arm_control(self, writer, identity_row, monkeypatch):
        """The control: the label belongs to the refusals, and a race is not one of them."""
        _with_registered_row(monkeypatch, present=True, asked=[])

        assert await _cause(writer, identity_row) is None
