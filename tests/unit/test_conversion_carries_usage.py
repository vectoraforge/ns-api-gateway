"""WR-09. What the anonymous-to-registered conversion does with the superseded grant's counters.

Driven at the writer, because every other unit suite replaces the whole writer with a recorder.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nativespeaker.api.crud.grants import ActivationOutcome, GrantsDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import MissingUsageRowError
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    UserMonthlyUsage,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider

SEEDED_AT = datetime(2026, 9, 9, 12, tzinfo=UTC)
ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "conversion-subject"
TIER_ID = "registered"

FRESH_PERIOD = datetime.now(UTC).strftime("%Y-%m")

SPENT_PERIOD = "2026-08"
SPENT_CREDITS = 7


class _AddingSession:
    """A session stand-in that records what the writer added and lets its one flush succeed."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


@pytest.fixture
def account() -> tuple[ExternalIdentity, AccessGrant]:
    """A google account holding one effective anonymous grant, which the conversion supersedes."""
    user_id = uuid4()
    identity_row = ExternalIdentity(user_id=user_id,
                                    issuer=ISSUER,
                                    subject=SUBJECT,
                                    provider=IdentityProvider.google,
                                    provider_uid="google-uid-stored")
    superseded = AccessGrant(user_id=user_id,
                             tier_id="anonymous",
                             source=AccessGrantSource.anonymous_device_grant,
                             starts_at=SEEDED_AT,
                             created_at=SEEDED_AT,
                             updated_at=SEEDED_AT)
    return identity_row, superseded


@pytest.fixture
def writer(account, monkeypatch) -> GrantsDB:
    """The writer with both lock tiers and the re-read scripted; only the usage row varies per case."""
    identity_row, superseded = account

    async def lock_active(self, user_id):
        return []

    async def lock_effective(self, user_id):
        return [superseded]

    async def resolve_existing(self, *, issuer, subject):
        return identity_row

    async def holds_grant_of_source(self, user_id, source):
        return False

    async def has_prior_free_grant(self, user_id):
        raise AssertionError("a superseded grant is present, so this question is not asked")

    monkeypatch.setattr(GrantsDB, "lock_active_grants", lock_active)
    monkeypatch.setattr(GrantsDB, "lock_effective_grants", lock_effective)
    monkeypatch.setattr(GrantsDB, "holds_grant_of_source", holds_grant_of_source)
    monkeypatch.setattr(GrantsDB, "has_prior_free_grant", has_prior_free_grant)
    monkeypatch.setattr(IdentitiesDB, "resolve_existing", resolve_existing)
    return GrantsDB(_AddingSession())  # ty: ignore[invalid-argument-type]


def _spent_usage(grant_id) -> UserMonthlyUsage:
    """The superseded grant's usage row: the month and the count a conversion must carry across."""
    return UserMonthlyUsage(grant_id=grant_id,
                            monthly_period=SPENT_PERIOD,
                            monthly_used=SPENT_CREDITS,
                            created_at=SEEDED_AT,
                            updated_at=SEEDED_AT)


def _with_usage(monkeypatch, usage: UserMonthlyUsage | None) -> None:
    async def lock_usage(self, grant_id):
        return usage

    monkeypatch.setattr(GrantsDB, "lock_usage", lock_usage)


async def _convert(writer: GrantsDB, identity_row: ExternalIdentity) -> ActivationOutcome:
    """The writer's outcome alone: no case here refuses, so the arm it would name is unread."""
    outcome, _ = await writer.activate_registered_account_grant(user_id=identity_row.user_id,
                                                                issuer=identity_row.issuer,
                                                                subject=identity_row.subject,
                                                                tier_id=TIER_ID)
    return outcome


class TestTheConversionCarriesTheCountersAcross:
    """The control: with a usage row present the period and the count survive the conversion."""

    async def test_the_new_usage_row_carries_the_superseded_period_and_count(self, writer, account,
                                                                             monkeypatch):
        identity_row, superseded = account
        _with_usage(monkeypatch, _spent_usage(superseded.id))

        assert await _convert(writer, identity_row) is ActivationOutcome.activated

        usage = [row for row in writer.session.added if isinstance(row, UserMonthlyUsage)]
        assert len(usage) == 1
        assert (usage[0].monthly_period, usage[0].monthly_used) == (SPENT_PERIOD, SPENT_CREDITS)


class TestOneConversionStampsEveryColumnWithOneValue:
    """A second clock read inside the writer would let the marker and the rows disagree, and a
    second free grant could then be claimed against a marker that matches no row. The start and
    the end of a term are the database clock, which the effective-grant predicate reads."""

    async def test_every_column_the_conversion_writes_carries_the_same_value(self, writer, account,
                                                                             monkeypatch):
        identity_row, superseded = account
        _with_usage(monkeypatch, _spent_usage(superseded.id))

        assert await _convert(writer, identity_row) is ActivationOutcome.activated

        activated = [row for row in writer.session.added if isinstance(row, AccessGrant)][0]
        usage = [row for row in writer.session.added if isinstance(row, UserMonthlyUsage)][0]
        assert {superseded.updated_at,
                activated.created_at, activated.updated_at,
                usage.created_at, usage.updated_at,
                identity_row.free_grant_consumed_at, identity_row.updated_at} == {
                    activated.created_at}

    async def test_the_term_start_and_the_superseded_end_are_the_database_clock(self, writer, account,
                                                                                monkeypatch):
        identity_row, superseded = account
        _with_usage(monkeypatch, _spent_usage(superseded.id))

        assert await _convert(writer, identity_row) is ActivationOutcome.activated

        activated = [row for row in writer.session.added if isinstance(row, AccessGrant)][0]
        assert {str(activated.starts_at), str(superseded.ends_at)} == {"statement_timestamp()"}

    async def test_the_value_is_read_inside_the_call_and_not_copied_from_the_old_grant(
            self, writer, account, monkeypatch):
        """The control: equality alone would also hold if the writer copied the superseded row."""
        identity_row, superseded = account
        _with_usage(monkeypatch, _spent_usage(superseded.id))
        before = datetime.now(UTC)

        await _convert(writer, identity_row)

        activated = [row for row in writer.session.added if isinstance(row, AccessGrant)][0]
        assert before <= activated.created_at <= datetime.now(UTC)


class TestASupersededGrantWithNoUsageRowFailsClosed:
    """SHARED-INVARIANTS: a missing usage row for an existing grant is never lazily minted."""

    async def test_it_raises_rather_than_minting_a_fresh_allowance(self, writer, account,
                                                                   monkeypatch):
        identity_row, superseded = account
        _with_usage(monkeypatch, None)

        with pytest.raises(MissingUsageRowError) as failure:
            await _convert(writer, identity_row)

        assert failure.value.grant_id == superseded.id

    async def test_it_writes_nothing_and_leaves_the_superseded_grant_active(self, writer, account,
                                                                            monkeypatch):
        """The refusal precedes the expiry write, so the rejected attempt mutates no row at all."""
        identity_row, superseded = account
        _with_usage(monkeypatch, None)

        with pytest.raises(MissingUsageRowError):
            await _convert(writer, identity_row)

        assert writer.session.added == []
        assert superseded.status is AccessGrantStatus.active
        assert superseded.ends_at is None


class TestTheFreshPeriodIsNotWhatACarriedRowWouldShow:
    """The control on the control: the two cases above differ, so neither passes vacuously."""

    def test_the_captured_month_is_not_the_spent_month(self):
        assert FRESH_PERIOD != SPENT_PERIOD
        assert SPENT_CREDITS != 0
