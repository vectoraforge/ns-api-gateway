"""`core.access_grants`: the single entitlement table, and the constraints that police it.

Two kinds of check appear here. The structural ones read the applied migration and assert the
declarative facts the specification's table semantics claim — the CHECKs, the partial unique
indexes, the generated columns and the deferrable foreign keys. The behavioural ones drive the
write-side contract in `nativespeaker.api.auth.grant_schema`, which refuses to hand a write path
a row or a transaction plan the schema would reject at commit.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.grant_schema import (
    ACCESS_GRANTS_TABLE,
    ACTIVE_GRANT_INDEX,
    ACTIVE_INDEX_REJECTION_PATHS,
    ACTIVE_INDEX_REPLACEMENTS,
    ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN,
    ACTIVE_SUBSCRIPTION_GRANT_USER_COLUMN,
    ANTI_ABUSE_COMPOSITE_FK,
    ANTI_ABUSE_ONLY_COLUMNS,
    ANTI_ABUSE_REQUIRED_COLUMN,
    ANTI_ABUSE_REQUIRED_FK,
    ANTI_ABUSE_TABLE,
    ENDS_AT_CHECK,
    ENTITLED_SUBSCRIPTION_FK,
    ENTITLED_SUBSCRIPTION_READ_PATH_REPAIRS,
    EXPIRY_SWEEPERS,
    FREE_GRANT_LIFETIME_INDEX,
    GRANT_ENTITLEMENT_COLUMNS,
    GRANT_OWNER_FK,
    GRANT_SOURCE_VALUES,
    GRANT_TIER_FK,
    ID_SOURCE_FK_TARGET,
    MONTHLY_USAGE_OWNER_COLUMN,
    MONTHLY_USAGE_TABLE,
    ONE_ACTIVE_GRANT_PER_SUBSCRIPTION_INDEX,
    PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN,
    SOURCE_PROVENANCE_MECHANISMS,
    SUBSCRIPTION_GRANT_CREATORS,
    SUBSCRIPTION_ID_CHECK,
    SUBSCRIPTION_OWNER_FK,
    AccessRepresentation,
    AntiAbuseBound,
    DuplicateDetection,
    FreeClaimOutcome,
    GrantRowProposal,
    GrantSchemaError,
    RestoreGrantAction,
    access_grant_row,
    access_representation,
    active_index_violation_outcome,
    anti_abuse_row_bounds,
    assert_active_subscription_entitled,
    assert_active_subscription_owner,
    assert_anti_abuse_lower_bound,
    assert_anti_abuse_row_presence,
    assert_ends_after_starts,
    assert_entitlement_state_only,
    assert_free_grant_eligibility_is_the_unique_violation,
    assert_free_slot_available,
    assert_grant_identity_immutable,
    assert_lifecycle_updates_share_transaction,
    assert_native_write_precedes_activation,
    assert_not_future_dated,
    assert_one_active_grant_per_subscription,
    assert_one_active_per_user,
    assert_registered_grant_hash_recorded,
    duplicate_claim_rejection,
    free_claim_outcome,
    generated_column_value,
    ingest_subscription_term,
    lazy_expiry_flip,
    monthly_usage_owner,
    paid_access_rows,
    participates_in_access_calculation,
    reconciles_with_device_check_state,
    resolve_subscription_tier,
    restore_grant_action,
)
from nativespeaker.api.auth.invariants import GrantCreator, InvariantError
from nativespeaker.api.auth.taxonomy import REMEDIATIONS, ClientErrorClass
from nativespeaker.api.models.subscriptions import SubscriptionStatus
from nativespeaker.api.quota.grants import (
    EntitlementError,
    GrantRow,
    RaceOutcome,
    ReadPathRepairError,
    honor_grant,
)
from nativespeaker.api.quota.usage import UsageRowError
from unit.test_schema_ddl import MIGRATION, declarative_section, parse

APPLIED = parse(declarative_section(MIGRATION.read_text()))
GRANTS = APPLIED.tables[ACCESS_GRANTS_TABLE]

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
FREE = (AccessGrantSource.anonymous_device_grant, AccessGrantSource.registered_account_grant)


def free_grant(*,
               source: AccessGrantSource = AccessGrantSource.anonymous_device_grant,
               tier_id: str = "anonymous",
               starts_at: datetime = NOW,
               ends_at: datetime | None = None,
               subscription_id=None,
               now: datetime = NOW,
               columns=()) -> GrantRowProposal:
    """One anonymous device grant row proposal, with any one field varied."""
    return access_grant_row(grant_id=uuid7(), user_id=uuid7(), tier_id=tier_id, source=source,
                            starts_at=starts_at, ends_at=ends_at,
                            subscription_id=subscription_id, now=now, columns=columns)


# --- What the table is for ---------------------------------------------------------------------

# [utest->req~schema-access-grants-purpose~1]
def test_the_table_stores_entitlement_state_and_no_anti_abuse_evidence():
    """One row is one entitlement, free or paid; source-specific anti-abuse evidence is a column
    of the other table, never of this one."""
    assert tuple(GRANTS.columns) == GRANT_ENTITLEMENT_COLUMNS
    for column in ANTI_ABUSE_ONLY_COLUMNS:
        assert column not in GRANTS.columns
        assert column in APPLIED.tables[ANTI_ABUSE_TABLE].columns
    assert_entitlement_state_only(GRANT_ENTITLEMENT_COLUMNS)
    grant = free_grant()
    assert grant.status is AccessGrantStatus.active


# [utest->req~schema-access-grants-purpose~1]
# [utest->req~schema-access-grants-no-anti-abuse-columns~1]
def test_an_anti_abuse_column_on_the_entitlement_row_is_refused():
    for column in sorted(ANTI_ABUSE_ONLY_COLUMNS):
        with pytest.raises(GrantSchemaError):
            assert_entitlement_state_only(["id", column])
    # Device-check state on the entitlement row is refused by the shared invariant's guard.
    with pytest.raises(InvariantError):
        assert_entitlement_state_only(["id", "device_check_state"])
    with pytest.raises(GrantSchemaError):
        free_grant(columns=["id", "idp_account_hash"])


# [utest->req~schema-access-grants-one-user-per-grant~1]
def test_every_grant_belongs_to_exactly_one_user():
    assert GRANTS.columns["user_id"] == (
        f"UUID NOT NULL REFERENCES {GRANT_OWNER_FK.target_table} (id) ON DELETE CASCADE")
    owning = [name for name, definition in GRANTS.columns.items()
              if "REFERENCES core.users" in definition]
    assert owning == ["user_id"]
    # No second owner may be attached through a table constraint either.
    assert [c for c in GRANTS.constraints if "core.users" in c] == []


# [utest->req~schema-access-grants-one-tier-per-grant~1]
def test_every_grant_points_at_exactly_one_tier():
    assert GRANTS.columns["tier_id"] == (
        f"TEXT NOT NULL REFERENCES {GRANT_TIER_FK.target_table} (id)")
    assert [name for name, definition in GRANTS.columns.items()
            if "REFERENCES core.access_tiers" in definition] == ["tier_id"]
    with pytest.raises(GrantSchemaError):
        free_grant(tier_id="")


# --- The `(source, subscription_id)` CHECK -----------------------------------------------------

# [utest->req~schema-access-grants-subscription-source-requires-subscription-id~1]
def test_a_subscription_grant_must_name_its_subscription():
    normalized = " ".join(SUBSCRIPTION_ID_CHECK.split())
    assert normalized in " ".join(" ".join(GRANTS.constraints).split())
    with pytest.raises(EntitlementError):
        free_grant(source=AccessGrantSource.subscription, tier_id="gold")
    paid = free_grant(source=AccessGrantSource.subscription, tier_id="gold",
                      subscription_id=uuid7())
    assert paid.subscription_id is not None


# [utest->req~schema-access-grants-non-subscription-no-subscription-id~1]
@pytest.mark.parametrize("source", [AccessGrantSource.anonymous_device_grant,
                                    AccessGrantSource.registered_account_grant,
                                    AccessGrantSource.manual])
def test_a_non_subscription_grant_must_not_name_a_subscription(source):
    with pytest.raises(EntitlementError):
        free_grant(source=source, subscription_id=uuid7())
    assert free_grant(source=source).subscription_id is None


# --- How free, manual and paid access are written down -----------------------------------------

# [utest->req~schema-access-grants-free-and-manual-not-fake-subscriptions~1]
@pytest.mark.parametrize("source", [AccessGrantSource.anonymous_device_grant,
                                    AccessGrantSource.registered_account_grant,
                                    AccessGrantSource.manual])
def test_free_and_manual_access_is_a_grant_row_with_no_billing_row(source):
    assert access_representation(source) is AccessRepresentation.grant_row_only
    # A fake subscription would mean a billing row for access that was never bought.
    with pytest.raises(EntitlementError):
        free_grant(source=source, subscription_id=uuid7())


# [utest->req~schema-access-grants-paid-access-shape~1]
def test_paid_access_is_a_subscription_row_plus_a_subscription_backed_grant():
    assert (access_representation(AccessGrantSource.subscription)
            is AccessRepresentation.subscription_row_plus_grant_row)
    assert paid_access_rows(subscription_id=uuid7(), grant_id=uuid7()) == (
        "core.subscriptions", ACCESS_GRANTS_TABLE)


# --- The source enumeration --------------------------------------------------------------------

# [utest->req~schema-access-grants-source-enumeration~1]
def test_source_records_the_whole_enumeration_and_what_it_reconciles_against():
    assert APPLIED.enums["core.access_grant_source"] == tuple(
        source.value for source in (AccessGrantSource.subscription,
                                    AccessGrantSource.anonymous_device_grant,
                                    AccessGrantSource.registered_account_grant,
                                    AccessGrantSource.manual))
    assert set(GRANT_SOURCE_VALUES) == set(AccessGrantSource)
    # Only the anonymous device grant has per-device device-check state to reconcile against.
    assert reconciles_with_device_check_state(
        AccessGrantSource.anonymous_device_grant) is True
    for source in (AccessGrantSource.registered_account_grant, AccessGrantSource.subscription,
                   AccessGrantSource.manual):
        assert reconciles_with_device_check_state(source) is False
    with pytest.raises(GrantSchemaError):
        reconciles_with_device_check_state("promo")  # ty: ignore[invalid-argument-type]


# --- The active-grant axis ---------------------------------------------------------------------

# [utest->req~schema-access-grants-one-active-per-user~1]
def test_at_most_one_active_grant_may_exist_for_a_user():
    index = APPLIED.indexes[ACTIVE_GRANT_INDEX.name]
    assert index.startswith("CREATE UNIQUE INDEX")
    assert f"ON {ACCESS_GRANTS_TABLE} (user_id) WHERE status = 'active'" in index
    assert_one_active_per_user([AccessGrantStatus.active, AccessGrantStatus.expired,
                                AccessGrantStatus.revoked])
    with pytest.raises(GrantSchemaError):
        assert_one_active_per_user([AccessGrantStatus.active, AccessGrantStatus.active])


# [utest->req~schema-access-grants-active-index-non-deferrable~1]
def test_the_active_index_is_a_plain_non_deferrable_unique_index():
    index = APPLIED.indexes[ACTIVE_GRANT_INDEX.name]
    assert "DEFERRABLE" not in index
    assert ACTIVE_GRANT_INDEX.deferrable is False
    # No exclusion constraint replaces it anywhere in the schema.
    assert "EXCLUDE" not in declarative_section(MIGRATION.read_text())
    assert not ACTIVE_INDEX_REPLACEMENTS


# [utest->req~schema-access-grants-active-index-non-deferrable~1]
def test_a_violation_of_the_active_index_fails_the_transaction_rather_than_being_rejected():
    """There is no application rejection path for it: the transaction fails and the caller sees a
    conflict or retry-class error."""
    assert not ACTIVE_INDEX_REJECTION_PATHS
    assert active_index_violation_outcome() is RaceOutcome.retry
    assert active_index_violation_outcome(retryable=False) is RaceOutcome.failed


# [utest->req~schema-access-grants-only-active-participates~1]
def test_only_the_active_non_expired_grant_participates_in_access_calculation():
    def row(status: AccessGrantStatus, ends_at=None) -> GrantRow:
        return GrantRow(grant_id=uuid7(), user_id=uuid7(), tier_id="free", source=FREE[0],
                        status=status, starts_at=NOW - timedelta(days=1), ends_at=ends_at)

    assert participates_in_access_calculation(row(AccessGrantStatus.active), NOW) is True
    for status in (AccessGrantStatus.expired, AccessGrantStatus.revoked):
        assert participates_in_access_calculation(row(status), NOW) is False
    # A time-ended row still sitting on `active` does not participate either.
    ended = row(AccessGrantStatus.active, ends_at=NOW - timedelta(hours=1))
    assert participates_in_access_calculation(ended, NOW) is False


# --- Dates ------------------------------------------------------------------------------------

# [utest->req~schema-access-grants-no-future-dating~1]
def test_no_grant_is_future_dated():
    assert_not_future_dated(NOW - timedelta(seconds=1), now=NOW)
    assert_not_future_dated(NOW, now=NOW)  # at the creation time is allowed
    with pytest.raises(GrantSchemaError):
        assert_not_future_dated(NOW + timedelta(seconds=1), now=NOW)
    with pytest.raises(GrantSchemaError):
        free_grant(starts_at=NOW + timedelta(days=1), now=NOW)


# [utest->req~schema-access-grants-ends-at-after-starts-at~1]
def test_a_non_null_ends_at_must_be_later_than_starts_at():
    assert " ".join(ENDS_AT_CHECK.split()) in " ".join(" ".join(GRANTS.constraints).split())
    assert_ends_after_starts(NOW, None)
    assert_ends_after_starts(NOW, NOW + timedelta(days=30))
    for bad in (NOW, NOW - timedelta(seconds=1)):
        with pytest.raises(GrantSchemaError):
            assert_ends_after_starts(NOW, bad)
    with pytest.raises(GrantSchemaError):
        free_grant(ends_at=NOW)


# --- The lazy expiry flip ----------------------------------------------------------------------

# [utest->req~schema-access-grants-lazy-expiry-flip~1]
def test_only_the_issuance_or_replacement_transaction_flips_a_time_ended_grant():
    ended = [uuid7()]
    assert lazy_expiry_flip(path="grant_issuance_or_replacement",
                            ended_grant_ids=ended) == tuple(ended)
    for path in ("auth_sync", "quota_enforcement", "scheduled_sweeper", "restore_read"):
        with pytest.raises(GrantSchemaError):
            lazy_expiry_flip(path=path, ended_grant_ids=ended)
    assert not EXPIRY_SWEEPERS


# [utest->req~schema-access-grants-lazy-expiry-flip~1]
def test_the_flip_happens_immediately_before_the_new_grant_is_inserted():
    with pytest.raises(GrantSchemaError):
        lazy_expiry_flip(path="grant_issuance_or_replacement",
                         ended_grant_ids=[uuid7()], before_insert=False)


# --- The lifetime free-grant slots -------------------------------------------------------------

# [utest->req~schema-access-grants-lifetime-free-grant-per-source~1]
def test_the_lifetime_index_covers_the_two_free_sources_with_no_status_predicate():
    index = APPLIED.indexes[FREE_GRANT_LIFETIME_INDEX.name]
    assert index.startswith("CREATE UNIQUE INDEX")
    assert f"ON {ACCESS_GRANTS_TABLE} (user_id, source)" in index
    assert ("WHERE source IN ('anonymous_device_grant', 'registered_account_grant')") in index
    # A status term would let expiry or revocation reopen the slot.
    assert "status" not in index.split("WHERE", 1)[1]


# [utest->req~schema-access-grants-lifetime-free-grant-per-source~1]
@pytest.mark.parametrize("source", FREE)
def test_a_committed_free_grant_occupies_its_slot_whatever_its_status_became(source):
    assert_free_slot_available(source, [])
    with pytest.raises(GrantSchemaError):
        assert_free_slot_available(source, [source])
    # The other free source is a separate slot, and the paid sources are unbounded.
    other = FREE[0] if source is FREE[1] else FREE[1]
    assert_free_slot_available(other, [source])
    for unbounded in (AccessGrantSource.subscription, AccessGrantSource.manual):
        assert_free_slot_available(unbounded, [unbounded, unbounded])


# [utest->req~schema-access-grants-lifetime-free-grant-per-source~1]
def test_the_active_grant_axis_stays_independently_responsible():
    """The lifetime index bounds the per-source axis; the active index bounds the active one."""
    assert ACTIVE_GRANT_INDEX.columns == ("user_id",)
    assert ACTIVE_GRANT_INDEX.predicate == "status = 'active'"
    assert FREE_GRANT_LIFETIME_INDEX.columns == ("user_id", "source")
    assert ACTIVE_GRANT_INDEX.name != FREE_GRANT_LIFETIME_INDEX.name
    # A user may hold an expired free grant and an active paid one at once.
    assert_free_slot_available(AccessGrantSource.subscription, [FREE[0]])
    assert_one_active_per_user([AccessGrantStatus.expired, AccessGrantStatus.active])


# [utest->req~schema-access-grants-user-id-source-immutable~1]
def test_user_id_and_source_are_immutable_and_free_rows_are_never_deleted():
    user_id, source = uuid7(), FREE[0]
    assert_grant_identity_immutable(stored_user_id=user_id, stored_source=source,
                                    incoming_user_id=user_id, incoming_source=source)
    with pytest.raises(GrantSchemaError):
        assert_grant_identity_immutable(stored_user_id=user_id, stored_source=source,
                                        incoming_user_id=uuid7(), incoming_source=source)
    with pytest.raises(GrantSchemaError):
        assert_grant_identity_immutable(stored_user_id=user_id, stored_source=source,
                                        incoming_user_id=user_id,
                                        incoming_source=AccessGrantSource.manual)
    with pytest.raises(GrantSchemaError):
        assert_grant_identity_immutable(stored_user_id=user_id, stored_source=source,
                                        incoming_user_id=user_id, incoming_source=source,
                                        deleted=True)


# [utest->req~schema-access-grants-user-id-source-immutable~1]
def test_the_unique_violation_is_the_final_eligibility_check():
    assert_free_grant_eligibility_is_the_unique_violation(history_query_decided=False)
    with pytest.raises(GrantSchemaError):
        assert_free_grant_eligibility_is_the_unique_violation(history_query_decided=True)


# [utest->req~schema-access-grants-one-free-grant-across-endpoints~1]
def test_one_free_grant_per_account_across_both_claim_endpoints():
    assert free_claim_outcome("claim_anonymous_grant",
                              committed_sources=[]) is FreeClaimOutcome.issued
    # After a successful claim on either endpoint, the other refuses for that user.
    assert free_claim_outcome("claim_registered_grant",
                              committed_sources=[FREE[0]]) is FreeClaimOutcome.refused
    assert free_claim_outcome("claim_anonymous_grant",
                              committed_sources=[FREE[1]]) is FreeClaimOutcome.refused
    with pytest.raises(GrantSchemaError):
        free_claim_outcome("upgrade_anonymous_to_registered", committed_sources=[])


# [utest->req~schema-access-grants-one-free-grant-across-endpoints~1]
def test_the_conversion_is_a_transition_of_the_same_allowance_not_a_second_issuance():
    assert free_claim_outcome("claim_registered_grant",
                              committed_sources=[FREE[0]],
                              converting_active_anonymous_grant=True) is FreeClaimOutcome.converted
    # Only the registered endpoint converts, and only when the anonymous grant is actually there.
    with pytest.raises(GrantSchemaError):
        free_claim_outcome("claim_anonymous_grant", committed_sources=[FREE[0]],
                           converting_active_anonymous_grant=True)
    with pytest.raises(GrantSchemaError):
        free_claim_outcome("claim_registered_grant", committed_sources=[],
                           converting_active_anonymous_grant=True)


# --- Subscription-backed grants ----------------------------------------------------------------

PRODUCT_MAP = {"com.example.app.gold": "gold"}


# [utest->req~schema-access-grants-ingestion-creates-subscription-grant~1]
def test_ingestion_creates_the_grant_and_its_zeroed_usage_row_in_one_transaction():
    transaction = object()
    subscription_id = uuid7()
    term = ingest_subscription_term(creator=GrantCreator.purchase_ingestion,
                                    grant_id=uuid7(), user_id=uuid7(),
                                    subscription_id=subscription_id,
                                    store_product_id="com.example.app.gold",
                                    product_id_to_tier=PRODUCT_MAP,
                                    subscription_status=SubscriptionStatus.active,
                                    starts_at=NOW, transaction=transaction)
    assert term.grant.source is AccessGrantSource.subscription
    assert term.grant.subscription_id == subscription_id
    assert term.grant.tier_id == "gold"
    assert term.usage.grant_id == term.grant.id
    assert term.usage.monthly_used == 0
    assert term.usage.monthly_period == "2026-08"
    assert term.idempotent_no_op is False
    # The usage row belongs to the transaction that creates the grant, not to a second one.
    with pytest.raises(UsageRowError):
        ingest_subscription_term(creator=GrantCreator.purchase_ingestion, grant_id=uuid7(),
                                 user_id=uuid7(), subscription_id=subscription_id,
                                 store_product_id="com.example.app.gold",
                                 product_id_to_tier=PRODUCT_MAP,
                                 subscription_status=SubscriptionStatus.active,
                                 starts_at=NOW, transaction=transaction,
                                 usage_transaction=object())
    with pytest.raises(GrantSchemaError):
        ingest_subscription_term(creator=GrantCreator.purchase_ingestion, grant_id=uuid7(),
                                 user_id=uuid7(), subscription_id=subscription_id,
                                 store_product_id="com.example.app.gold",
                                 product_id_to_tier=PRODUCT_MAP,
                                 subscription_status=SubscriptionStatus.active,
                                 starts_at=NOW, transaction=None)


# [utest->req~schema-access-grants-ingestion-creates-subscription-grant~1]
def test_free_tier_usage_is_never_copied_into_the_paid_counter():
    transaction = object()
    with pytest.raises(GrantSchemaError):
        ingest_subscription_term(creator=GrantCreator.purchase_ingestion, grant_id=uuid7(),
                                 user_id=uuid7(), subscription_id=uuid7(),
                                 store_product_id="com.example.app.gold",
                                 product_id_to_tier=PRODUCT_MAP,
                                 subscription_status=SubscriptionStatus.active,
                                 starts_at=NOW, transaction=transaction,
                                 free_tier_monthly_used=7)


# [utest->req~schema-access-grants-ingestion-creates-subscription-grant~1]
def test_renewal_expires_the_index_blocking_grant_and_never_deletes_it():
    blocking = uuid7()
    term = ingest_subscription_term(creator=GrantCreator.renewal_term_insert, grant_id=uuid7(),
                                    user_id=uuid7(), subscription_id=uuid7(),
                                    store_product_id="com.example.app.gold",
                                    product_id_to_tier=PRODUCT_MAP,
                                    subscription_status=SubscriptionStatus.active,
                                    starts_at=NOW, blocking_grant_ids=[blocking],
                                    transaction=object())
    assert term.expired_grant_ids == (blocking,)
    assert term.deleted_grant_ids == ()


# [utest->req~schema-access-grants-ingestion-creates-subscription-grant~1]
def test_the_tier_comes_from_the_server_mapping_and_never_from_client_input():
    assert resolve_subscription_tier("com.example.app.gold", PRODUCT_MAP) == "gold"
    with pytest.raises(GrantSchemaError):
        resolve_subscription_tier("com.example.app.unknown", PRODUCT_MAP)
    with pytest.raises(GrantSchemaError):
        resolve_subscription_tier("com.example.app.gold", PRODUCT_MAP,
                                  client_supplied_tier_id="platinum")


# [utest->req~schema-access-grants-ingestion-creates-subscription-grant~1]
def test_a_redelivered_same_term_event_is_an_idempotent_no_op():
    existing = uuid7()
    term = ingest_subscription_term(creator=GrantCreator.purchase_ingestion, grant_id=uuid7(),
                                    user_id=uuid7(), subscription_id=uuid7(),
                                    store_product_id="com.example.app.gold",
                                    product_id_to_tier=PRODUCT_MAP,
                                    subscription_status=SubscriptionStatus.active,
                                    starts_at=NOW, transaction=object(),
                                    existing_term_grant_id=existing)
    assert term.idempotent_no_op is True
    assert term.grant.id == existing  # no second grant for the term
    assert term.expired_grant_ids == ()
    assert term.usage.monthly_used == 0  # and no reset of the live counter


# [utest->req~schema-access-grants-ingestion-creates-subscription-grant~1]
def test_only_ingestion_renewal_and_restore_adoption_create_a_subscription_backed_grant():
    assert set(SUBSCRIPTION_GRANT_CREATORS) == {GrantCreator.purchase_ingestion,
                                                GrantCreator.renewal_term_insert,
                                                GrantCreator.restore_adoption}
    for creator in (GrantCreator.claim_anonymous_grant, GrantCreator.claim_registered_grant,
                    GrantCreator.manual_issuance):
        with pytest.raises(GrantSchemaError):
            ingest_subscription_term(creator=creator, grant_id=uuid7(), user_id=uuid7(),
                                     subscription_id=uuid7(),
                                     store_product_id="com.example.app.gold",
                                     product_id_to_tier=PRODUCT_MAP,
                                     subscription_status=SubscriptionStatus.active,
                                     starts_at=NOW, transaction=object())


# [utest->req~schema-access-grants-subscription-id-unique-among-active~1]
def test_subscription_id_is_unique_among_active_subscription_backed_grants():
    index = APPLIED.indexes[ONE_ACTIVE_GRANT_PER_SUBSCRIPTION_INDEX.name]
    assert index.startswith("CREATE UNIQUE INDEX")
    assert "(subscription_id) WHERE source = 'subscription'" in index
    assert "status = 'active'" in index  # superseded term rows stay in history
    first, second = uuid7(), uuid7()
    assert_one_active_grant_per_subscription([first, second])
    with pytest.raises(GrantSchemaError):
        assert_one_active_grant_per_subscription([first, second, first])


# [utest->req~schema-access-grants-restore-no-second-active-subscription-grant~1]
def test_restore_settles_adopts_or_rejects_but_never_creates_a_second_active_grant():
    user_id = uuid7()
    grant_id = uuid7()
    assert restore_grant_action(same_account=True, existing_grant_id=grant_id,
                                subscription_owner_id=user_id,
                                destination_user_id=user_id) is RestoreGrantAction.settle_in_place
    assert restore_grant_action(same_account=False, existing_grant_id=None,
                                subscription_owner_id=None,
                                destination_user_id=user_id) is RestoreGrantAction.adopt_unclaimed
    assert restore_grant_action(
        same_account=False, existing_grant_id=None, subscription_owner_id=uuid7(),
        destination_user_id=user_id) is RestoreGrantAction.reject_owner_mismatch
    # Adoption is for an unclaimed subscription only; a later term is ingestion's renewal.
    with pytest.raises(GrantSchemaError):
        restore_grant_action(same_account=False, existing_grant_id=grant_id,
                             subscription_owner_id=None, destination_user_id=user_id)


# [utest->req~schema-access-grants-active-requires-entitled-subscription~1]
def test_an_active_subscription_grant_needs_a_product_entitled_subscription():
    for status in (SubscriptionStatus.active, SubscriptionStatus.grace_period):
        assert_active_subscription_entitled(status=AccessGrantStatus.active,
                                            subscription_status=status)
    for status in (SubscriptionStatus.billing_retry, SubscriptionStatus.expired,
                   SubscriptionStatus.revoked):
        with pytest.raises(GrantSchemaError):
            assert_active_subscription_entitled(status=AccessGrantStatus.active,
                                                subscription_status=status)
        # A terminal grant row generates NULL and is not subject to the check.
        assert_active_subscription_entitled(status=AccessGrantStatus.expired,
                                           subscription_status=status)


# [utest->req~schema-access-grants-active-requires-entitled-subscription~1]
def test_no_read_path_detects_or_repairs_a_non_entitled_active_subscription_grant():
    assert not ENTITLED_SUBSCRIPTION_READ_PATH_REPAIRS
    grant = GrantRow(grant_id=uuid7(), user_id=uuid7(), tier_id="gold",
                     source=AccessGrantSource.subscription, status=AccessGrantStatus.active,
                     starts_at=NOW, subscription_id=uuid7())
    assert honor_grant(grant) is grant
    with pytest.raises(ReadPathRepairError):
        honor_grant(grant, subscription_status=SubscriptionStatus.expired)


# [utest->req~schema-access-grants-lifecycle-same-transaction~1]
def test_a_lifecycle_update_settles_the_linked_grant_in_the_same_transaction():
    transaction = object()
    assert_lifecycle_updates_share_transaction(subscription_transaction=transaction,
                                               grant_transaction=transaction)
    with pytest.raises(InvariantError):
        assert_lifecycle_updates_share_transaction(subscription_transaction=transaction,
                                                   grant_transaction=object())


# --- Monthly usage ------------------------------------------------------------------------------

# [utest->req~schema-access-grants-owns-monthly-usage~1]
def test_the_grant_owns_its_monthly_usage_state():
    grant = free_grant()
    assert monthly_usage_owner(grant) == (MONTHLY_USAGE_TABLE, grant.id)
    usage = APPLIED.tables[MONTHLY_USAGE_TABLE]
    assert usage.columns[MONTHLY_USAGE_OWNER_COLUMN] == (
        f"UUID PRIMARY KEY REFERENCES {ACCESS_GRANTS_TABLE} (id) ON DELETE CASCADE")
    # Usage is keyed by the grant, never by the user, so it cannot outlive or move off it.
    assert "user_id" not in usage.columns


# --- The anti-abuse row's existence -------------------------------------------------------------

# [utest->req~schema-access-grants-requires-anti-abuse-row~1]
def test_a_free_credit_grant_requires_an_anti_abuse_row_of_its_own_source():
    for source in FREE:
        assert_anti_abuse_row_presence(source, source)
        with pytest.raises(InvariantError):
            assert_anti_abuse_row_presence(source, None)
        other = FREE[0] if source is FREE[1] else FREE[1]
        with pytest.raises(InvariantError):
            assert_anti_abuse_row_presence(source, other)


# [utest->req~schema-access-grants-requires-anti-abuse-row~1]
@pytest.mark.parametrize("source", [AccessGrantSource.subscription, AccessGrantSource.manual])
def test_a_subscription_or_manual_grant_must_not_have_an_anti_abuse_row(source):
    assert_anti_abuse_row_presence(source, None)
    with pytest.raises(InvariantError):
        assert_anti_abuse_row_presence(source, AccessGrantSource.anonymous_device_grant)


# [utest->req~schema-access-grants-registered-grant-hash-required~1]
def test_a_registered_grant_carries_its_hash_and_key_version():
    assert_registered_grant_hash_recorded(idp_account_hash=b"alias",
                                          idp_account_hash_key_version=1)
    for hash_bytes, version in ((None, 1), (b"alias", None), (None, None)):
        with pytest.raises(InvariantError):
            assert_registered_grant_hash_recorded(idp_account_hash=hash_bytes,
                                                  idp_account_hash_key_version=version)


# [utest->req~schema-access-grants-native-write-before-activation~1]
def test_the_native_claimed_state_write_precedes_activation_in_the_same_attempt():
    assert_native_write_precedes_activation(source=AccessGrantSource.anonymous_device_grant,
                                            native_claim_written=True, same_attempt=True)
    with pytest.raises(InvariantError):
        assert_native_write_precedes_activation(source=AccessGrantSource.anonymous_device_grant,
                                                native_claim_written=False, same_attempt=True)
    with pytest.raises(InvariantError):
        assert_native_write_precedes_activation(source=AccessGrantSource.anonymous_device_grant,
                                                native_claim_written=True, same_attempt=False)
    # Registered grants are governed by their own activation rules, not by this ordering.
    with pytest.raises(GrantSchemaError):
        assert_native_write_precedes_activation(source=FREE[1], native_claim_written=True,
                                                same_attempt=True)


# --- The generated columns and their deferrable foreign keys ------------------------------------

# [utest->req~schema-access-grants-required-anti-abuse-fk~1]
def test_the_lower_bound_foreign_key_hangs_off_the_generated_eligibility_column():
    definition = GRANTS.columns[ANTI_ABUSE_REQUIRED_COLUMN.name]
    assert definition.startswith("UUID GENERATED ALWAYS AS")
    assert ANTI_ABUSE_REQUIRED_COLUMN.expression in definition
    assert definition.endswith("STORED")
    alter = next(a for a in APPLIED.alters if ANTI_ABUSE_REQUIRED_COLUMN.name in a)
    assert (f"ADD FOREIGN KEY ({ANTI_ABUSE_REQUIRED_COLUMN.name}) REFERENCES "
            f"{ANTI_ABUSE_TABLE} (grant_id) DEFERRABLE INITIALLY DEFERRED") in alter
    assert ANTI_ABUSE_REQUIRED_FK.deferrable is True


# [utest->req~schema-access-grants-required-anti-abuse-fk~1]
def test_the_generated_column_is_the_id_for_free_sources_and_null_otherwise():
    grant_id = uuid7()
    for source in FREE:
        assert generated_column_value(ANTI_ABUSE_REQUIRED_COLUMN, grant_id=grant_id,
                                      source=source,
                                      status=AccessGrantStatus.active) == grant_id
    for source in (AccessGrantSource.subscription, AccessGrantSource.manual):
        assert generated_column_value(ANTI_ABUSE_REQUIRED_COLUMN, grant_id=grant_id,
                                      source=source,
                                      status=AccessGrantStatus.active) is None


# [utest->req~schema-access-grants-required-anti-abuse-fk~1]
def test_the_two_rows_may_be_inserted_in_either_order_inside_one_transaction():
    transaction = object()
    grant_id = uuid7()
    assert_anti_abuse_lower_bound(source=FREE[0], grant_id=grant_id,
                                  anti_abuse_grant_ids=[grant_id],
                                  grant_transaction=transaction,
                                  anti_abuse_transaction=transaction)
    # An eligible grant with no anti-abuse row is rejected at commit.
    with pytest.raises(GrantSchemaError):
        assert_anti_abuse_lower_bound(source=FREE[0], grant_id=grant_id,
                                      anti_abuse_grant_ids=[],
                                      grant_transaction=transaction,
                                      anti_abuse_transaction=transaction)
    # A non-eligible source is unconstrained.
    assert_anti_abuse_lower_bound(source=AccessGrantSource.subscription, grant_id=grant_id,
                                  anti_abuse_grant_ids=[],
                                  grant_transaction=transaction,
                                  anti_abuse_transaction=transaction)
    # Two transactions cannot satisfy a deferred constraint at one commit.
    with pytest.raises(GrantSchemaError):
        assert_anti_abuse_lower_bound(source=FREE[0], grant_id=grant_id,
                                      anti_abuse_grant_ids=[grant_id],
                                      grant_transaction=transaction,
                                      anti_abuse_transaction=object())


# [utest->req~schema-access-grants-unique-id-source-fk-target~1]
def test_unique_id_source_exists_only_as_the_composite_foreign_key_target():
    assert "UNIQUE (" + ", ".join(ID_SOURCE_FK_TARGET) + ")" in GRANTS.constraints
    assert GRANTS.columns["id"] == "UUID PRIMARY KEY"  # `id` is already unique on its own
    anti_abuse = APPLIED.tables[ANTI_ABUSE_TABLE]
    assert any(f"REFERENCES {ACCESS_GRANTS_TABLE} (id, source)" in constraint
               for constraint in anti_abuse.constraints)
    assert ANTI_ABUSE_COMPOSITE_FK.target_columns == ID_SOURCE_FK_TARGET


# [utest->req~schema-access-grants-unique-id-source-fk-target~1]
def test_source_is_not_protected_by_triggers_or_any_other_provenance_mechanism():
    assert not SOURCE_PROVENANCE_MECHANISMS
    schema = declarative_section(MIGRATION.read_text())
    for mechanism in ("CREATE TRIGGER", "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", "GRANT "):
        assert mechanism not in schema


# [utest->req~schema-access-grants-subscription-owner-composite-fk~1]
def test_owner_agreement_is_a_deferrable_composite_foreign_key_on_the_generated_pair():
    constraint = next(c for c in GRANTS.constraints
                      if "REFERENCES core.subscriptions (id, user_id)" in c)
    assert (f"FOREIGN KEY ({ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN.name}, "
            f"{ACTIVE_SUBSCRIPTION_GRANT_USER_COLUMN.name})") in constraint
    assert "REFERENCES core.subscriptions (id, user_id)" in constraint
    assert "DEFERRABLE INITIALLY DEFERRED" in constraint
    # No MATCH clause is written, so the composite key keeps Postgres' MATCH SIMPLE default.
    assert "MATCH" not in constraint
    assert SUBSCRIPTION_OWNER_FK.match == "SIMPLE"


# [utest->req~schema-access-grants-subscription-owner-composite-fk~1]
def test_only_active_subscription_backed_rows_are_subject_to_owner_agreement():
    user_id = uuid7()
    assert_active_subscription_owner(source=AccessGrantSource.subscription,
                                     status=AccessGrantStatus.active,
                                     grant_user_id=user_id, subscription_user_id=user_id)
    with pytest.raises(InvariantError):
        assert_active_subscription_owner(source=AccessGrantSource.subscription,
                                         status=AccessGrantStatus.active,
                                         grant_user_id=user_id, subscription_user_id=uuid7())
    # A terminal subscription-backed row and a non-subscription grant generate NULLs.
    assert_active_subscription_owner(source=AccessGrantSource.subscription,
                                     status=AccessGrantStatus.expired,
                                     grant_user_id=user_id, subscription_user_id=uuid7())
    assert_active_subscription_owner(source=FREE[0], status=AccessGrantStatus.active,
                                     grant_user_id=user_id, subscription_user_id=None)


# [utest->req~schema-access-grants-subscription-owner-composite-fk~1]
def test_the_generated_owner_pair_is_populated_only_while_active_and_subscription_backed():
    user_id, subscription_id, grant_id = uuid7(), uuid7(), uuid7()
    for column, expected in ((ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN, subscription_id),
                             (ACTIVE_SUBSCRIPTION_GRANT_USER_COLUMN, user_id)):
        assert column.expression in GRANTS.columns[column.name]
        assert generated_column_value(column, grant_id=grant_id,
                                      source=AccessGrantSource.subscription,
                                      status=AccessGrantStatus.active, user_id=user_id,
                                      subscription_id=subscription_id) == expected
        for source, status in ((AccessGrantSource.subscription, AccessGrantStatus.expired),
                               (AccessGrantSource.subscription, AccessGrantStatus.revoked),
                               (FREE[0], AccessGrantStatus.active)):
            assert generated_column_value(column, grant_id=grant_id, source=source,
                                          status=status, user_id=user_id,
                                          subscription_id=subscription_id) is None


# [utest->req~schema-access-grants-entitled-subscription-generated-fk~1]
def test_the_entitled_subscription_rule_is_a_generated_column_foreign_key_pair():
    constraint = next(c for c in GRANTS.constraints
                      if PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN.name in c)
    assert (f"FOREIGN KEY ({ACTIVE_SUBSCRIPTION_GRANT_SUBSCRIPTION_COLUMN.name}) REFERENCES "
            f"core.subscriptions ({PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN.name})") in constraint
    assert "DEFERRABLE INITIALLY DEFERRED" in constraint
    assert ENTITLED_SUBSCRIPTION_FK.deferrable is True
    # And the target column selects exactly the fixed product-entitled status set.
    subscriptions = APPLIED.tables["core.subscriptions"]
    assert (PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN.expression
            in subscriptions.columns[PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN.name])
    assert f"UNIQUE ({PRODUCT_ENTITLED_SUBSCRIPTION_COLUMN.name})" in subscriptions.constraints


# [utest->req~schema-access-grants-exactly-one-anti-abuse-row~1]
def test_exactly_one_anti_abuse_row_per_eligible_grant_is_fully_declarative():
    bounds = anti_abuse_row_bounds()
    assert set(bounds) == set(AntiAbuseBound)
    assert "primary key" in bounds[AntiAbuseBound.at_most_one]
    assert "per-source CHECK" in bounds[AntiAbuseBound.none_for_other_sources]
    assert ANTI_ABUSE_REQUIRED_COLUMN.name in bounds[AntiAbuseBound.at_least_one]
    # Each named mechanism is really in the applied schema.
    anti_abuse = APPLIED.tables[ANTI_ABUSE_TABLE]
    assert anti_abuse.columns["grant_id"] == "UUID PRIMARY KEY"
    assert any("grant_source IN" in constraint for constraint in anti_abuse.constraints)
    assert any(ANTI_ABUSE_REQUIRED_COLUMN.name in alter for alter in APPLIED.alters)


# --- Duplicate free-credit claims ---------------------------------------------------------------

# [utest->req~schema-access-grants-duplicate-claim-rejection-results~1]
def test_an_anonymous_duplicate_surfaces_as_device_grant_exhausted_and_rolls_back():
    native = duplicate_claim_rejection(DuplicateDetection.native_device_check_state)
    web = duplicate_claim_rejection(DuplicateDetection.web_gate)
    assert native.client_class is ClientErrorClass.device_grant_exhausted
    assert web.client_class is ClientErrorClass.device_grant_exhausted
    # The audited internal results differ by where the duplicate was detected.
    assert str(native.result) == "native_claim_already_claimed"
    assert str(web.result) == "anti_abuse_already_claimed"
    assert native.rolls_back_grant_insert and web.rolls_back_grant_insert
    # Detected outside activation there is no grant insert to roll back.
    outside = duplicate_claim_rejection(DuplicateDetection.web_gate, inside_activation=False)
    assert outside.rolls_back_grant_insert is False


# [utest->req~schema-access-grants-duplicate-claim-rejection-results~1]
def test_the_registered_duplicate_path_is_distinct_in_audit_class_and_remediation():
    registered = duplicate_claim_rejection(DuplicateDetection.registered_gate)
    anonymous = duplicate_claim_rejection(DuplicateDetection.native_device_check_state)
    assert str(registered.result) == "idp_account_already_claimed"
    assert registered.client_class is ClientErrorClass.account_already_claimed
    assert registered.rolls_back_grant_insert is True
    assert registered.result != anonymous.result
    assert registered.client_class != anonymous.client_class
    assert (REMEDIATIONS[registered.client_class].action
            != REMEDIATIONS[anonymous.client_class].action)
    with pytest.raises(GrantSchemaError):
        duplicate_claim_rejection("subscription_conflict")  # ty: ignore[invalid-argument-type]
