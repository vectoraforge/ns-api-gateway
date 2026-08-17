"""Quota and access enforcement: the effective grant, the entitlement it reports, quota
admission, and the lazy monthly rollover sequence that spends it.

The sequence is exercised against a recording store, so the statements it takes — and their
order, and the ones it must never take — are checked directly.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid7

import pytest
import yaml

from nativespeaker.api.app.dependencies import require_quota
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.locks import ExternalCallUnderLockError, LockingPath, LockLedger
from nativespeaker.api.database.usage import GrantsDB, QuotaStoreDB, current_period
from nativespeaker.api.exceptions import QuotaExceededError
from nativespeaker.api.models.subscriptions import SubscriptionStatus
from nativespeaker.api.quota.grants import (
    EntitlementError,
    MissingTierError,
    PublicEntitlementStatus,
    PublicEntitlementType,
    RaceOutcome,
    ReadPathRepairError,
    TooManyActiveGrantsError,
    assert_billing_separation,
    assert_status_writer_settled_grant,
    authorizes,
    effective_allowance,
    effective_tier,
    entitlement_report,
    has_monthly_allowance,
    honor_grant,
    is_effective,
    is_product_entitled,
    resolve_entitlement_race,
    select_effective_grant,
    settle_subscription_grant,
)
from nativespeaker.api.quota.rollover import (
    QUOTA_ADMISSION_ENTRY,
    QUOTA_ADMISSION_KEY_POLICY,
    QuotaSequenceError,
    assert_admission_key_policy,
    assert_no_background_job,
    consume_quota,
    quota_admission,
    remaining_credits,
    rollover_values,
)
from nativespeaker.api.quota.usage import MissingUsageRowError
from nativespeaker.api.ratelimit.config import RateLimitsConfig
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import AdmissionLedger, AdmissionOrderError
from nativespeaker.api.ratelimit.rejection import AdmissionRejected
from unit.conftest import FakeQuotaStore, admitted_ledger, grant_row, quota_request
from unit.test_user_monthly_usage import FakeResult, FakeSession, db, live_grant

NOW = datetime(2026, 3, 9, 12, 0, tzinfo=UTC)
PERIOD = "2026-03"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def postgres_sql(statement: object) -> str:
    """One recorded statement as PostgreSQL sees it, so the row-locking clause the sequence
    depends on is visible — the default dialect drops the `OF` list."""
    from sqlalchemy.dialects import postgresql  # noqa: PLC0415

    return str(statement.compile(dialect=postgresql.dialect()))  # ty: ignore[unresolved-attribute]


def ledger() -> AdmissionLedger:
    return admitted_ledger()


# --- Access grants own monthly usage state -----------------------------------------------------


# [utest->req~quota-allowance-from-active-grant-row~1]
def test_an_allowance_is_an_active_grant_row_and_nothing_else():
    """Not a usage row, and not a field on `core.users`."""
    assert has_monthly_allowance(grant_row()) is True
    # A counter with no effective grant behind it is not an allowance.
    assert has_monthly_allowance(None, usage_row_exists=True) is False
    # Nor is a column on the user row.
    for column in ("plan", "monthly_credits", "free_access", "has_access"):
        with pytest.raises(EntitlementError):
            has_monthly_allowance(grant_row(), user_columns=["id", column])
    # A grant that is present but not effective carries no allowance either.
    lapsed = grant_row(ends_at=NOW - timedelta(days=1))
    assert effective_tier([lapsed], NOW).allowance == 0


# [utest->req~quota-billing-vs-grant-separation~1]
def test_billing_records_and_grants_are_separate_tables():
    """Paid billing lives in `core.subscriptions`; access is granted through
    `core.access_grants`, and a free grant is never written as a fake subscription."""
    subscription_id = uuid7()
    assert_billing_separation(AccessGrantSource.subscription, subscription_id)
    for source in (AccessGrantSource.anonymous_device_grant,
                   AccessGrantSource.registered_account_grant,
                   AccessGrantSource.manual):
        assert_billing_separation(source, None)
        with pytest.raises(EntitlementError):
            assert_billing_separation(source, subscription_id)
    with pytest.raises(EntitlementError):
        assert_billing_separation(AccessGrantSource.subscription, None)


# [utest->req~quota-status-writer-owns-grant-deactivation~1]
def test_the_status_writer_settles_the_grant_in_its_own_transaction():
    """Whichever write path takes a subscription out of the product-entitled set deactivates or
    replaces the active grant in the same transaction; there is no sweep to do it later."""
    transaction = object()
    grant_id = uuid7()
    # A transition out of the entitled set that leaves the grant active cannot stand.
    with pytest.raises(EntitlementError):
        assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                           new_status=SubscriptionStatus.expired,
                                           active_grant_id=grant_id,
                                           subscription_transaction=transaction,
                                           grant_transaction=transaction)
    for settled in ({"grant_deactivated": True}, {"grant_replaced": True}):
        assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                           new_status=SubscriptionStatus.billing_retry,
                                           active_grant_id=grant_id,
                                           subscription_transaction=transaction,
                                           grant_transaction=transaction,
                                           **settled)
    # A transition that stays inside the entitled set settles nothing.
    assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                       new_status=SubscriptionStatus.grace_period,
                                       active_grant_id=grant_id,
                                       subscription_transaction=transaction,
                                       grant_transaction=transaction)
    # And the two writes are one transaction.
    with pytest.raises(EntitlementError):
        assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                           new_status=SubscriptionStatus.expired,
                                           active_grant_id=grant_id,
                                           grant_deactivated=True,
                                           subscription_transaction=transaction,
                                           grant_transaction=object())


# [utest->req~quota-restore-race-serialization~1]
def test_the_restore_race_is_resolved_by_serialization_alone():
    """One transaction commits and the other retries or fails cleanly; no repair protocol
    exists to be invoked."""
    assert resolve_entitlement_race(committed=True) is RaceOutcome.committed
    assert resolve_entitlement_race(committed=False) is RaceOutcome.retry
    assert resolve_entitlement_race(committed=False, retryable=False) is RaceOutcome.failed
    with pytest.raises(EntitlementError):
        resolve_entitlement_race(committed=False, repair_protocol="reconcile_grant_status")


# [utest->req~quota-restore-requires-entitled-subscription~1]
def test_restore_activates_no_grant_behind_a_non_entitled_subscription():
    user_id = uuid7()
    grant = grant_row(user_id=user_id, source=AccessGrantSource.subscription,
                      subscription_id=uuid7())
    for entitled in (SubscriptionStatus.active, SubscriptionStatus.grace_period):
        assert is_product_entitled(entitled) is True
        assert settle_subscription_grant(grant, subscription_status=entitled,
                                         destination_user_id=user_id,
                                         usage_row_grant_id=grant.grant_id) is grant
    for lapsed in (SubscriptionStatus.billing_retry, SubscriptionStatus.expired,
                   SubscriptionStatus.revoked):
        assert is_product_entitled(lapsed) is False
        with pytest.raises(EntitlementError):
            settle_subscription_grant(grant, subscription_status=lapsed,
                                      destination_user_id=user_id,
                                      usage_row_grant_id=grant.grant_id)
    # The grant does not move to another user, and no per-device state feeds the decision.
    with pytest.raises(EntitlementError):
        settle_subscription_grant(grant, subscription_status=SubscriptionStatus.active,
                                  destination_user_id=uuid7(),
                                  usage_row_grant_id=grant.grant_id)
    with pytest.raises(EntitlementError):
        settle_subscription_grant(grant, subscription_status=SubscriptionStatus.active,
                                  destination_user_id=user_id,
                                  usage_row_grant_id=grant.grant_id,
                                  per_device_inputs=["devicecheck_bit"])


# --- Entitlement reporting ---------------------------------------------------------------------


# [utest->req~quota-report-single-effective-grant~1]
def test_the_report_is_the_single_effective_grant_never_a_status_match():
    """A row that is `status = 'active'` but time-ended is not the reported entitlement."""
    lapsed = grant_row(status=AccessGrantStatus.active, ends_at=NOW - timedelta(hours=1))
    report = entitlement_report([lapsed], now=NOW)
    assert report.status is PublicEntitlementStatus.none
    live = grant_row(tier_id="gold", monthly_credits=200)
    assert entitlement_report([live], now=NOW).tier_id == "gold"
    # Two effective grants are an invariant violation, not a tie to break.
    with pytest.raises(TooManyActiveGrantsError):
        entitlement_report([live, grant_row()], now=NOW)


# [utest->req~quota-type-from-grant-source~1]
def test_type_comes_from_the_effective_grants_source():
    for source, expected in ((AccessGrantSource.subscription,
                              PublicEntitlementType.subscription),
                             (AccessGrantSource.anonymous_device_grant,
                              PublicEntitlementType.anonymous_device_grant),
                             (AccessGrantSource.registered_account_grant,
                              PublicEntitlementType.registered_account_grant),
                             (AccessGrantSource.manual, PublicEntitlementType.manual)):
        row = grant_row(source=source,
                        subscription_id=uuid7()
                        if source is AccessGrantSource.subscription else None)
        assert entitlement_report([row], now=NOW).type is expected
    assert entitlement_report([], now=NOW).type is PublicEntitlementType.none


# [utest->req~quota-public-status-none-or-active~1]
def test_the_public_status_enum_is_exactly_none_or_active():
    assert set(PublicEntitlementStatus) == {PublicEntitlementStatus.none,
                                            PublicEntitlementStatus.active}
    assert entitlement_report([grant_row()], now=NOW).status is PublicEntitlementStatus.active
    assert entitlement_report([], now=NOW).status is PublicEntitlementStatus.none
    # A revoked or expired row reads exactly as a user who never had a grant.
    for status in (AccessGrantStatus.revoked, AccessGrantStatus.expired):
        report = entitlement_report([grant_row(status=status)], now=NOW)
        assert report.status is PublicEntitlementStatus.none
        assert report.type is PublicEntitlementType.none
        assert str(report.status) not in {"expired", "revoked"}


# [utest->req~quota-auth-sync-no-grant-defaults~1]
def test_with_no_effective_grant_sync_still_reports_the_period_and_zero_usage():
    report = entitlement_report([], now=NOW, stored_period=PERIOD, stored_used=7)
    assert (report.type, report.status) == (PublicEntitlementType.none,
                                            PublicEntitlementStatus.none)
    assert report.current_period == PERIOD  # the clock-computed period, never null
    assert report.monthly_used == 0
    assert (report.tier_id, report.monthly_credits) == (None, None)
    # With a grant, the stored counter counts only when the row names the current period.
    row = grant_row()
    assert entitlement_report([row], now=NOW,
                              stored_period=PERIOD, stored_used=7).monthly_used == 7
    assert entitlement_report([row], now=NOW,
                              stored_period="2026-02", stored_used=7).monthly_used == 0
    assert entitlement_report([row], now=NOW).monthly_used == 0


# --- The effective access tier -----------------------------------------------------------------


# [utest->req~quota-shared-effective-grant-predicate~1]
# [utest->req~quota-effective-tier-step-01~1]
def test_the_shared_predicate_is_the_whole_conjunction():
    """`status = 'active'` and `starts_at <= now` and (`ends_at IS NULL OR ends_at > now`)."""
    assert is_effective(grant_row(), NOW) is True
    assert is_effective(grant_row(ends_at=NOW + timedelta(days=1)), NOW) is True
    # Status alone never selects a row.
    assert is_effective(grant_row(status=AccessGrantStatus.expired), NOW) is False
    assert is_effective(grant_row(status=AccessGrantStatus.revoked), NOW) is False
    # Nor does an active status with the clock outside the window.
    assert is_effective(grant_row(starts_at=NOW + timedelta(seconds=1)), NOW) is False
    assert is_effective(grant_row(ends_at=NOW), NOW) is False
    # And the selection uses exactly that predicate.
    row = grant_row()
    assert select_effective_grant([row, grant_row(status=AccessGrantStatus.expired)], NOW) is row
    assert select_effective_grant([grant_row(ends_at=NOW - timedelta(days=1))], NOW) is None


# [utest->req~quota-effective-tier-step-02~1]
def test_more_than_one_effective_grant_is_an_invariant_violation():
    user_id = uuid7()
    with pytest.raises(TooManyActiveGrantsError):
        select_effective_grant([grant_row(user_id=user_id), grant_row(user_id=user_id)], NOW)


# [utest->req~quota-effective-tier-step-03~1]
# [utest->req~quota-effective-tier-step-04~1]
def test_a_subscription_backed_grant_is_honored_without_re_reading_the_subscription():
    """The deferrable foreign key already guarantees it; evaluation branches on nothing, and a
    read path repairs nothing."""
    grant = grant_row(source=AccessGrantSource.subscription, subscription_id=uuid7())
    assert honor_grant(grant) is grant
    with pytest.raises(ReadPathRepairError):
        honor_grant(grant, subscription_status=SubscriptionStatus.expired)
    with pytest.raises(ReadPathRepairError):
        honor_grant(grant, subscription_status=SubscriptionStatus.active)
    # Entitlement is never evaluated from a deferred-constraint intermediate state.
    with pytest.raises(ReadPathRepairError):
        honor_grant(grant, deferred_constraints_pending=True)


# [utest->req~quota-effective-tier-step-05~1]
# [utest->req~quota-effective-tier-step-06~1]
def test_the_allowance_is_the_joined_tiers_monthly_credits():
    assert effective_allowance(grant_row(tier_id="gold", monthly_credits=200)) == 200
    assert effective_tier([grant_row(monthly_credits=10)], NOW).allowance == 10
    # A grant that joins no tier row has no allowance to read.
    with pytest.raises(MissingTierError):
        effective_allowance(grant_row(monthly_credits=None))


# [utest->req~quota-no-grant-zero-allowance~1]
def test_no_effective_grant_means_an_allowance_of_zero():
    assert effective_allowance(None) == 0
    tier = effective_tier([], NOW)
    assert (tier.grant, tier.allowance) == (None, 0)


# [utest->req~quota-only-effective-grants-authorize~1]
@pytest.mark.asyncio
async def test_only_effective_grants_authorize_consumption():
    assert authorizes(grant_row(), NOW) is True
    assert authorizes(None, NOW) is False
    assert authorizes(grant_row(status=AccessGrantStatus.expired), NOW) is False
    # A lapsed row plus a live counter authorizes nothing, and no counter is even read.
    store = FakeQuotaStore(rows=[grant_row(ends_at=NOW - timedelta(days=1))],
                           usage=(PERIOD, 0))
    with pytest.raises(QuotaExceededError):
        await consume_quota(store, user_id=uuid7(), ledger=ledger(), now=NOW)
    assert store.usage_reads == [] and store.increments == []


# [utest->req~quota-no-future-dating-lazy-expiry-flip~2]
@pytest.mark.asyncio
async def test_an_unflipped_ended_row_never_ranks_against_its_replacement():
    """The predicate is applied over the rows as they stand, and one captured evaluation time
    drives selection, the period computation and the usage read."""
    user_id = uuid7()
    unflipped = grant_row(user_id=user_id, status=AccessGrantStatus.active,
                          ends_at=NOW - timedelta(minutes=1), monthly_credits=200)
    replacement = grant_row(user_id=user_id, tier_id="free", monthly_credits=10)
    tier = effective_tier([unflipped, replacement], NOW)
    assert tier.grant is replacement and tier.allowance == 10

    # The same instant drives the report's grant selection, period and usage read.
    report = entitlement_report([unflipped, replacement], now=NOW,
                                stored_period=PERIOD, stored_used=3)
    assert (report.current_period, report.monthly_used) == (PERIOD, 3)

    # And a read path flips nothing: the ended row is untouched.
    store = FakeQuotaStore(rows=[unflipped, replacement], usage=(PERIOD, 0))
    await consume_quota(store, user_id=user_id, ledger=ledger(), now=NOW)
    assert store.rollovers == []
    assert store.increments == [(replacement.grant_id, PERIOD)]


# --- Lazy monthly rollover ---------------------------------------------------------------------


# [utest->req~quota-no-background-job~1]
@pytest.mark.asyncio
async def test_quota_enforcement_needs_no_background_job():
    """The month turns over on the request that noticed it, inside that request's transaction."""
    assert_no_background_job()
    for job in ("monthly_rollover_sweep", "grant_expiry_cron"):
        with pytest.raises(QuotaSequenceError):
            assert_no_background_job([job])
    row = grant_row(monthly_credits=10)
    store = FakeQuotaStore(rows=[row], usage=("2026-02", 9))
    outcome = await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
    assert outcome.rolled_over is True
    assert store.rollovers == [(row.grant_id, {"monthly_period": PERIOD, "monthly_used": 0,
                                               "updated_at": NOW})]


# --- Quota admission control -------------------------------------------------------------------


# [utest->req~quota-admission-before-quota-mutation~1]
@pytest.mark.asyncio
async def test_admission_runs_before_any_database_quota_mutation():
    """The rollover write, the counter read and the increment all sit behind it."""
    row = grant_row(monthly_credits=10)
    store = FakeQuotaStore(rows=[row], usage=("2026-02", 4))
    unadmitted = AdmissionLedger("POST", "/chats")
    unadmitted.verify_jwt()
    unadmitted.admit_barrier()
    with pytest.raises(AdmissionOrderError):
        await consume_quota(store, user_id=row.user_id, ledger=unadmitted, now=NOW)
    assert (store.grant_reads, store.usage_reads, store.rollovers, store.increments) == (
        [], [], [], [])

    # A request over the limit is rejected at admission, before the sequence runs.
    over = AdmissionLedger("POST", "/chats")
    over.verify_jwt()
    over.admit_barrier()
    with pytest.raises(AdmissionRejected):
        quota_admission(over, user_id=row.user_id,
                        decision=LimitDecision(allowed=False, limiter=QUOTA_ADMISSION_ENTRY,
                                               retry_after_seconds=30))
    with pytest.raises(AdmissionOrderError):
        await consume_quota(store, user_id=row.user_id, ledger=over, now=NOW)
    assert store.increments == []


# [utest->req~quota-admission-keyed-by-user-id~1]
def test_the_admission_limit_is_keyed_by_the_internal_user_id():
    assert QUOTA_ADMISSION_KEY_POLICY == (KeyComponent.user,)
    shipped = RateLimitsConfig(**yaml.safe_load(CONFIG_PATH.read_text())["rate_limits"])
    assert_admission_key_policy(shipped)
    assert shipped.entry(QUOTA_ADMISSION_ENTRY).policy == (KeyComponent.user,)
    rekeyed = shipped.model_copy(deep=True)
    rekeyed.entries[QUOTA_ADMISSION_ENTRY] = rekeyed.entry(
        QUOTA_ADMISSION_ENTRY).model_copy(update={"key": "ip"})
    with pytest.raises(QuotaSequenceError):
        assert_admission_key_policy(rekeyed)
    # A ledger only lets the user-keyed limit run once the barrier has admitted the caller.
    unadmitted = AdmissionLedger("POST", "/chats")
    unadmitted.verify_jwt()
    with pytest.raises(AdmissionOrderError):
        quota_admission(unadmitted, user_id=uuid7(),
                        decision=LimitDecision(allowed=True, limiter=QUOTA_ADMISSION_ENTRY))


# [utest->req~quota-admission-independent-of-entitlement~1]
@pytest.mark.asyncio
async def test_admission_and_entitlement_neither_replaces_nor_exempts_the_other():
    """Passing admission grants no entitlement, and holding entitlement exempts no request."""
    # Admission passed, but the user holds no effective grant: still refused.
    store = FakeQuotaStore(rows=[], usage=(PERIOD, 0))
    with pytest.raises(QuotaExceededError):
        await consume_quota(store, user_id=uuid7(), ledger=ledger(), now=NOW)

    # Entitled, but admission was never evaluated: still refused, and nothing is read.
    row = grant_row(monthly_credits=10)
    entitled = FakeQuotaStore(rows=[row], usage=(PERIOD, 0))
    exempt = AdmissionLedger("POST", "/chats")
    exempt.verify_jwt()
    exempt.admit_barrier()
    with pytest.raises(AdmissionOrderError):
        await consume_quota(entitled, user_id=row.user_id, ledger=exempt, now=NOW)
    assert entitled.grant_reads == []

    # The allowance is the tier's either way: admission never contributes to it.
    admitted = await consume_quota(entitled, user_id=row.user_id, ledger=ledger(), now=NOW)
    assert admitted.allowance == 10


# --- The rollover sequence ---------------------------------------------------------------------


# [utest->req~quota-rollover-after-admission~1]
# [utest->req~quota-rollover-step-01~1]
# [utest->req~quota-rollover-step-02~1]
# [utest->req~quota-rollover-step-03~1]
@pytest.mark.asyncio
async def test_the_sequence_locks_the_grant_then_the_usage_row():
    row = grant_row(monthly_credits=10)
    store = FakeQuotaStore(rows=[row], usage=(PERIOD, 0))
    outcome = await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
    # 1. the grant, resolved for this user at the captured evaluation time.
    assert store.grant_reads == [(row.user_id, NOW)]
    # 2. then its usage row, by grant id.
    assert store.usage_reads == [row.grant_id]
    # 3. the period is computed from that same instant.
    assert outcome.monthly_period == PERIOD

    # The lock order itself: grant first, usage second, never the reverse.
    locks = LockLedger(LockingPath.lazy_monthly_rollover)
    locks.lock_grant(row.grant_id)
    locks.lock_usage(row.grant_id)
    assert (locks.grant_locks, locks.usage_locks) == ((row.grant_id,), (row.grant_id,))


# [utest->req~quota-rollover-step-01~1]
# [utest->req~quota-rollover-step-02~1]
@pytest.mark.asyncio
async def test_the_two_statements_really_take_row_locks_in_that_order():
    """`FOR UPDATE` is the whole content of steps 1 and 2, so the statements the store issues are
    checked as compiled SQL: the grant select locks the grant row and precedes the usage select,
    which locks the usage row."""
    user_id = uuid7()
    grant = live_grant(user_id)
    session = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult((PERIOD, 0)))
    store = QuotaStoreDB(db(session))
    await store.locked_grant_rows(user_id, NOW)
    await store.locked_usage_row(grant.id)

    grant_select, usage_select = (postgres_sql(statement) for statement in session.statements)
    # 1. the grant row itself is locked; the tier row it joins is configuration and is not.
    assert "core.access_grants" in grant_select
    assert grant_select.rstrip().endswith("FOR UPDATE OF access_grants")
    # 2. the usage row is locked second, after its grant.
    assert "core.user_monthly_usage" in usage_select
    assert usage_select.rstrip().endswith("FOR UPDATE")


# [utest->req~quota-effective-tier-step-03~1]
# [utest->req~quota-effective-tier-step-04~1]
@pytest.mark.asyncio
async def test_the_read_paths_lock_nothing_read_no_subscription_and_write_nothing():
    """Evaluation never re-reads or branches on the linked subscription's status, and no read
    path repairs grant state: the reporting statements name no subscription table, take no lock
    and issue no write."""
    user_id = uuid7()
    grant = live_grant(user_id)

    effective = FakeSession(FakeResult(rows=[(grant, 10)]))
    await GrantsDB(db(effective)).effective_grant(user_id, NOW)
    reported = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult((PERIOD, 3)))
    await GrantsDB(db(reported)).entitlement(user_id, NOW)

    for session in (effective, reported):
        assert session.statements, "the read path issues its statements"
        assert session.commits == 0
        for statement in session.statements:
            sql = postgres_sql(statement)
            # `core.subscriptions` is never consulted: the deferrable foreign key already
            # guarantees an active subscription-backed grant is product-entitled.
            assert "core.subscriptions" not in sql
            assert "FOR UPDATE" not in sql
            assert sql.lstrip().split(" ", 1)[0] == "SELECT"


# [utest->req~quota-rollover-step-02~1]
@pytest.mark.asyncio
async def test_a_missing_usage_row_fails_closed_instead_of_minting_a_counter():
    row = grant_row(monthly_credits=10)
    store = FakeQuotaStore(rows=[row], usage=None)
    with pytest.raises(MissingUsageRowError):
        await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
    assert store.increments == [] and store.rollovers == []


# [utest->req~quota-rollover-step-04~1]
# [utest->req~quota-introductory-entitlement-is-a-grant~1]
@pytest.mark.asyncio
async def test_a_stale_period_is_advanced_and_the_counter_zeroed():
    row = grant_row(monthly_credits=10)
    store = FakeQuotaStore(rows=[row], usage=("2026-02", 10))
    outcome = await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
    assert store.rollovers == [(row.grant_id, {"monthly_period": PERIOD, "monthly_used": 0,
                                               "updated_at": NOW})]
    # The reset frees the whole allowance again, and consumes one of it.
    assert (outcome.allowance, outcome.monthly_used) == (10, 1)

    # A row already on the current period is not rewritten.
    fresh = FakeQuotaStore(rows=[row], usage=(PERIOD, 1))
    assert (await consume_quota(fresh, user_id=row.user_id,
                                ledger=ledger(), now=NOW)).rolled_over is False
    assert fresh.rollovers == []

    # And the reset writes usage state only: entitlement is a grant, not a counter value.
    assert rollover_values(PERIOD, now=NOW) == {"monthly_period": PERIOD, "monthly_used": 0,
                                                "updated_at": NOW}
    for entitlement in ({"tier_id": "gold"}, {"monthly_credits": 200}, {"source": "manual"}):
        with pytest.raises(QuotaSequenceError):
            rollover_values(PERIOD, now=NOW, extra=entitlement)


# [utest->req~quota-rollover-step-05~1]
@pytest.mark.asyncio
async def test_the_allowance_comes_from_the_grants_tier():
    row = grant_row(tier_id="gold", monthly_credits=200)
    store = FakeQuotaStore(rows=[row], usage=(PERIOD, 0))
    outcome = await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
    assert outcome.allowance == 200


# [utest->req~quota-rollover-step-06~1]
def test_remaining_is_floored_at_zero():
    assert remaining_credits(10, 3) == 7
    assert remaining_credits(10, 10) == 0
    # A tier edit, downgrade or manual adjustment that left `monthly_used > monthly_credits`
    # degrades to zero remaining, never to negative arithmetic leaking onward.
    assert remaining_credits(10, 25) == 0
    assert remaining_credits(0, 0) == 0


# [utest->req~quota-rollover-step-07~1]
@pytest.mark.asyncio
async def test_zero_remaining_is_ordinary_quota_exhaustion():
    row = grant_row(monthly_credits=10)
    for used in (10, 25):
        store = FakeQuotaStore(rows=[row], usage=(PERIOD, used))
        with pytest.raises(QuotaExceededError):
            await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
        assert store.increments == []
    # A zero-credit tier is the same ordinary exhaustion.
    zero = FakeQuotaStore(rows=[grant_row(monthly_credits=0)], usage=(PERIOD, 0))
    with pytest.raises(QuotaExceededError):
        await consume_quota(zero, user_id=uuid7(), ledger=ledger(), now=NOW)


# [utest->req~quota-rollover-step-08~1]
@pytest.mark.asyncio
async def test_a_request_with_remaining_credit_consumes_one():
    row = grant_row(monthly_credits=10)
    store = FakeQuotaStore(rows=[row], usage=(PERIOD, 4))
    outcome = await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
    assert store.increments == [(row.grant_id, PERIOD)]
    assert (outcome.monthly_used, outcome.remaining) == (5, 5)


# [utest->req~quota-rollover-lock-scope~1]
@pytest.mark.asyncio
async def test_the_locks_are_held_for_these_statements_only_and_nothing_retries():
    """No external call under the locks, and a database abort is not retried here."""
    locks = LockLedger(LockingPath.lazy_monthly_rollover)
    locks.lock_grant(uuid7())
    with pytest.raises(ExternalCallUnderLockError):
        locks.external_call("app_store_status")
    locks.commit()
    locks.external_call("app_store_status")  # after commit, remote work is fine again

    row = grant_row(monthly_credits=10)
    aborted = FakeQuotaStore(rows=[row], usage=(PERIOD, 0),
                             increment_error=RuntimeError("deadlock detected"))
    with pytest.raises(RuntimeError, match="deadlock detected"):
        await consume_quota(aborted, user_id=row.user_id, ledger=ledger(), now=NOW)
    # The client's next request is the natural retry: this transaction tried exactly once.
    assert len(aborted.increments) == 1
    assert len(aborted.grant_reads) == 1
    assert aborted.commits == 0  # an aborted sequence commits nothing


# [utest->req~quota-rollover-lock-scope~1]
@pytest.mark.asyncio
async def test_the_sequence_commits_before_the_handler_calls_a_provider():
    """The locks are released at the sequence's own commit, which happens before it returns — so
    the handler's outbound model call is never made while the grant and usage rows are locked."""
    row = grant_row(monthly_credits=10)
    store = FakeQuotaStore(rows=[row], usage=("2026-02", 4))
    await consume_quota(store, user_id=row.user_id, ledger=ledger(), now=NOW)
    # Four statements, then the commit that ends the transaction. Nothing follows it.
    assert store.calls == ["locked_grant_rows", "locked_usage_row", "write_rollover",
                           "increment_usage", "commit"]

    # And on the real store the commit is the request-scoped session's own, taken inside the
    # dependency rather than left to the session finalizer that runs after the handler.
    user_id = uuid7()
    grant = live_grant(user_id)
    session = FakeSession(FakeResult(rows=[(grant, 10)]), FakeResult((current_period(), 0)))
    user = MagicMock()
    user.id = user_id
    await require_quota(quota_request(), user=user, db=db(session))
    assert session.commits == 1
    assert session.sql()[-1] == "COMMIT"
