"""The four store-subscription tables of the schema reference.

`core.subscriptions`, `core.store_purchase_tokens`, `core.store_purchases` and
`audit.subscription_events`. Two kinds of check appear here: structural ones read the applied
migration and assert the declarative facts the specification's table semantics claim, and
behavioural ones drive the write-side contract in `nativespeaker.api.auth.subscription_schema`,
which refuses to hand a write path a row or a plan the schema would reject at commit.
"""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5, uuid7

import pytest

from nativespeaker.api.auth.audit import REDACTED, AuthEventResult
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.grant_schema import GrantSchemaError
from nativespeaker.api.auth.invariants import AttributionTokens, InvariantError, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.restore import RestoreContractError, RestoreRejection
from nativespeaker.api.auth.restore_flow import PurchaseRow, SubscriptionRow, VerifiedTransaction
from nativespeaker.api.auth.restore_phases import LOCK_ORDER, LockTier
from nativespeaker.api.auth.restore_proof_policy import BindingOutcome
from nativespeaker.api.auth.store_purchases import StorePurchaseError
from nativespeaker.api.auth.subscription_schema import (
    ENTITLED_STATUS_RUNTIME_MECHANISMS,
    IDENTITY_KIND_COLUMNS,
    INGESTION_REACTIVATION_PATHS,
    LOCKSTEP_CHANGES,
    REACTIVATION_OWNER,
    TOKEN_COLUMNS,
    PurchaseAttributionUse,
    StorePurchaseTokenRow,
    SubscriptionEventRow,
    SubscriptionSchemaError,
    adopt_unclaimed,
    append_subscription_event,
    apply_lifecycle_transition,
    assert_billing_fact_grants_nothing,
    assert_billing_fact_not_access,
    assert_binding_survives_upgrade,
    assert_entitled_status_set_change,
    assert_entitlement_holds_at_commit,
    assert_event_not_rewritten,
    assert_generated_column_is_the_authority,
    assert_grant_ended,
    assert_history_confers_no_entitlement,
    assert_id_user_id_is_fk_target_only,
    assert_identity_value_not_unique,
    assert_ingestion_settles_grant,
    assert_lifecycle_globally_unique,
    assert_names_canonical_subscription,
    assert_never_rotated,
    assert_no_active_grant_for_terminal,
    assert_no_attribution_conflict,
    assert_no_grant_while_unclaimed,
    assert_no_ingestion_reactivation,
    assert_one_row_per_lifecycle,
    assert_owner_agreement_at_commit,
    assert_purchase_row_immutable,
    assert_purchase_user_id_not_load_bearing,
    assert_purchase_user_id_use,
    assert_random_opaque_uuid,
    assert_resolved_token_value,
    assert_restore_purchase_write,
    assert_restore_serialized,
    assert_rows_per_user_provider,
    assert_stable_identity_field,
    assert_tier_is_current,
    assert_token_proves_nothing,
    assert_token_row_columns,
    assert_transfer_month_untouched,
    attribution_record,
    bind_restore_destination,
    bound_after_restore,
    canonical_state,
    current_tier,
    entitlement_input,
    event_tier_transition,
    ingest_lifecycle_event,
    is_entitled,
    lifecycle_external_id,
    mint_into,
    mint_token_row,
    persistence_failure_result,
    product_entitled_subscription_id,
    purchase_identity_value,
    purchase_store,
    purchase_table_semantics,
    record_event_type,
    record_purchase,
    redacted_token_payload,
    resolve_for_ingestion,
    resolve_owning_user,
    resolve_purchase_user,
    resolved_token_value,
    restore_branch_owner,
    restore_purchase_row,
    settle_grant_for_non_entitled,
    store_transaction_identifiers,
    token_binding,
    token_kind,
    unclaimed_subscription,
)
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.grants import EntitlementError
from unit.test_schema_ddl import MIGRATION, declarative_section, parse

APPLIED = parse(declarative_section(MIGRATION.read_text()))
SCHEMA_TEXT = declarative_section(MIGRATION.read_text())
SUBSCRIPTIONS = APPLIED.tables["core.subscriptions"]
TOKENS = APPLIED.tables["core.store_purchase_tokens"]
PURCHASES = APPLIED.tables["core.store_purchases"]
EVENTS = APPLIED.tables["audit.subscription_events"]
GRANTS = APPLIED.tables["core.access_grants"]

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
APPLE = StoreProvider.apple
PLAY = StoreProvider.google_play


def _row(external_id: str = "1000000123",
         *,
         status: SubscriptionStatus = SubscriptionStatus.active,
         tier: str = "silver",
         user_id: UUID | None = None,
         provider: StoreProvider = APPLE,
         bound: UUID | None = None) -> SubscriptionRow:
    return SubscriptionRow(subscription_id=uuid7(), provider=provider, external_id=external_id,
                           status=status, tier_id=tier, user_id=user_id,
                           restore_bound_user_id=bound)


def _event(subscription_id: UUID, event_type: str = "DID_RENEW") -> SubscriptionEventRow:
    return SubscriptionEventRow(event_id=uuid7(), subscription_id=subscription_id,
                                event_type=event_type, notification_uuid=str(uuid4()))


# ==============================================================================================
# `core.subscriptions`
# ==============================================================================================

# [utest->req~schema-subscriptions-row-per-lifecycle~1]
def test_each_row_is_exactly_one_paid_subscription_lifecycle():
    first, second = _row("A"), _row("B")
    assert_one_row_per_lifecycle([first, second])
    # A second row holding another state of the same lifecycle is not a second subscription.
    with pytest.raises(SubscriptionSchemaError):
        assert_one_row_per_lifecycle([first, _row("A", status=SubscriptionStatus.expired)])
    # Same identifier in the other store namespace is a different lifecycle.
    assert_one_row_per_lifecycle([first, _row("A", provider=PLAY)])
    assert canonical_state(first) == {"user_id": None, "tier_id": "silver",
                                      "status": SubscriptionStatus.active}


# [utest->req~schema-subscriptions-external-id-stable-identity~1]
def test_external_id_is_the_stable_lifecycle_identity_within_the_provider_namespace():
    apple = {"originalTransactionId": "1000000123", "transactionId": "2000000999"}
    assert lifecycle_external_id(APPLE, apple) == "1000000123"
    assert lifecycle_external_id(PLAY, {"purchaseToken": "play-token"}) == "play-token"
    # A per-term identifier renews with the billing period and would split one lifecycle.
    for name in ("transactionId", "webOrderLineItemId", "orderId", "notificationUUID"):
        with pytest.raises(SubscriptionSchemaError):
            assert_stable_identity_field(name)
    with pytest.raises(SubscriptionSchemaError):
        lifecycle_external_id(APPLE, {"transactionId": "2000000999"})


# [utest->req~schema-subscriptions-transitions-update-in-place~1]
def test_every_ordinary_lifecycle_transition_updates_the_same_row_in_place():
    rows = [_row("A", user_id=uuid7())]
    for transition, status in (("renewal", SubscriptionStatus.active),
                               ("grace_period", SubscriptionStatus.grace_period),
                               ("billing_retry", SubscriptionStatus.billing_retry),
                               ("expiration", SubscriptionStatus.expired),
                               ("revocation", SubscriptionStatus.revoked),
                               ("tier_change", SubscriptionStatus.active)):
        updated = apply_lifecycle_transition(rows, provider=APPLE, external_id="A",
                                             transition=transition, status=status,
                                             tier_id="silver")
        assert updated.subscription_id == rows[0].subscription_id
        assert updated.status is status
        assert updated.user_id == rows[0].user_id
    with pytest.raises(SubscriptionSchemaError):
        apply_lifecycle_transition(rows, provider=APPLE, external_id="A",
                                   transition="second_row", status=SubscriptionStatus.active,
                                   tier_id="silver")


# [utest->req~schema-subscriptions-ingestion-resolve-by-key~1]
def test_ingestion_resolves_by_provider_and_external_id_and_updates_what_it_finds():
    rows = [_row("A"), _row("B")]
    found = resolve_for_ingestion(rows, provider=APPLE, external_id="B")
    assert found is not None and found.subscription_id == rows[1].subscription_id
    assert resolve_for_ingestion(rows, provider=APPLE, external_id="C") is None
    # The key includes the provider: the same identifier in the other store resolves to nothing.
    assert resolve_for_ingestion(rows, provider=PLAY, external_id="A") is None
    updated = apply_lifecycle_transition(rows, provider=APPLE, external_id="A",
                                         transition="renewal", status=SubscriptionStatus.active,
                                         tier_id="gold")
    assert updated.subscription_id == rows[0].subscription_id


# [utest->req~schema-subscriptions-provider-external-id-unique~1]
def test_provider_and_external_id_are_globally_unique():
    index = APPLIED.indexes["ix_subscriptions_provider_external_id"]
    assert index.startswith("CREATE UNIQUE INDEX")
    assert "(provider, external_id)" in index
    assert "WHERE" not in index  # global, not partial
    rows = [_row("A", user_id=uuid7())]
    # A different owner buys no second canonical row for the same store subscription.
    with pytest.raises(SubscriptionSchemaError):
        assert_lifecycle_globally_unique(rows, provider=APPLE, external_id="A")
    assert_lifecycle_globally_unique(rows, provider=PLAY, external_id="A")


# [utest->req~schema-subscriptions-user-id-null-unclaimed~1]
def test_an_unclaimed_subscription_is_unowned_and_can_back_no_grant():
    row = unclaimed_subscription(provider=APPLE, external_id="A",
                                 status=SubscriptionStatus.active, tier_id="silver")
    assert row.user_id is None
    assert SUBSCRIPTIONS.columns["user_id"] == "UUID REFERENCES core.users (id)"
    assert_no_grant_while_unclaimed(subscription_user_id=None, grant_user_id=None)
    with pytest.raises(SubscriptionSchemaError):
        assert_no_grant_while_unclaimed(subscription_user_id=None, grant_user_id=uuid7())
    destination = uuid7()
    adopted = adopt_unclaimed(row, destination_user_id=destination)
    assert adopted.user_id == destination
    assert adopted.subscription_id == row.subscription_id
    assert_no_grant_while_unclaimed(subscription_user_id=destination, grant_user_id=destination)
    with pytest.raises(InvariantError):
        assert_no_grant_while_unclaimed(subscription_user_id=destination, grant_user_id=uuid7())
    with pytest.raises(SubscriptionSchemaError):
        adopt_unclaimed(adopted, destination_user_id=uuid7())


# [utest->req~schema-subscriptions-tier-id-current-tier~1]
def test_tier_id_records_the_tier_currently_associated_with_the_lifecycle():
    rows = [_row("A", tier="silver", user_id=uuid7())]
    moved = apply_lifecycle_transition(rows, provider=APPLE, external_id="A",
                                       transition="tier_change",
                                       status=SubscriptionStatus.active, tier_id="gold")
    assert current_tier(moved) == "gold"
    assert_tier_is_current(moved, tier_id="gold")
    with pytest.raises(SubscriptionSchemaError):
        assert_tier_is_current(rows[0], tier_id="gold")
    assert SUBSCRIPTIONS.columns["tier_id"] == "TEXT NOT NULL REFERENCES core.access_tiers (id)"


# [utest->req~schema-subscriptions-events-append-only-history~1]
def test_the_event_history_beside_the_canonical_row_is_append_only():
    subscription_id = uuid7()
    first, second = _event(subscription_id), _event(subscription_id, "EXPIRED")
    history = append_subscription_event((), first)
    history = append_subscription_event(history, second)
    assert history == (first, second)
    with pytest.raises(SubscriptionSchemaError):
        append_subscription_event(history, first)
    with pytest.raises(SubscriptionSchemaError):
        assert_event_not_rewritten(first, replace(first, event_type="REFUND"))
    assert EVENTS.columns["subscription_id"] == \
        "UUID NOT NULL REFERENCES core.subscriptions (id)"


# [utest->req~schema-subscriptions-multiple-rows-per-user-provider~1]
def test_one_user_may_hold_several_rows_per_store_only_for_different_lifecycles():
    owner = uuid7()
    assert_rows_per_user_provider([_row("A", user_id=owner), _row("B", user_id=owner)])
    with pytest.raises(SubscriptionSchemaError):
        assert_rows_per_user_provider([_row("A", user_id=owner), _row("A", user_id=owner)])


# [utest->req~schema-subscriptions-billing-facts-not-access~1]
def test_subscription_rows_are_billing_facts_and_access_comes_from_grants():
    subscription_id = uuid7()
    assert_billing_fact_not_access(source=AccessGrantSource.subscription,
                                   subscription_id=subscription_id)
    with pytest.raises(EntitlementError):
        assert_billing_fact_not_access(source=AccessGrantSource.subscription, subscription_id=None)
    with pytest.raises(EntitlementError):
        assert_billing_fact_not_access(source=AccessGrantSource.manual,
                                       subscription_id=subscription_id)


# [utest->req~schema-subscriptions-entitlement-from-grants~1]
def test_entitlement_is_derived_from_grants_never_from_subscription_rows():
    assert entitlement_input("core.access_grants") == "core.access_grants"
    for table in ("core.subscriptions", "core.store_purchases", "audit.subscription_events"):
        with pytest.raises(SubscriptionSchemaError):
            entitlement_input(table)
    # Duplicate same-lifecycle rows webhook ordering created decide nothing.
    assert_billing_fact_grants_nothing(subscription_rows=3, active_grants=1)
    with pytest.raises(SubscriptionSchemaError):
        assert_billing_fact_grants_nothing(subscription_rows=1, active_grants=2)


# [utest->req~schema-subscriptions-product-entitled-status-set~1]
def test_the_product_entitled_statuses_are_exactly_active_and_grace_period():
    entitled = {status for status in SubscriptionStatus if is_entitled(status)}
    assert entitled == {SubscriptionStatus.active, SubscriptionStatus.grace_period}
    row = _row(status=SubscriptionStatus.active)
    assert product_entitled_subscription_id(row) == row.subscription_id
    for status in (SubscriptionStatus.billing_retry, SubscriptionStatus.expired,
                   SubscriptionStatus.revoked):
        assert product_entitled_subscription_id(_row(status=status)) is None
    assert "CASE WHEN status IN ('active', 'grace_period') THEN id END" in \
        SUBSCRIPTIONS.columns["product_entitled_subscription_id"]


# [utest->req~schema-subscriptions-expired-revoked-no-active-grant~1]
def test_expired_and_revoked_rows_back_no_active_subscription_grant():
    for status in (SubscriptionStatus.expired, SubscriptionStatus.revoked):
        with pytest.raises(SubscriptionSchemaError):
            assert_no_active_grant_for_terminal(status=status, active_grant_id=uuid7())
        assert_no_active_grant_for_terminal(status=status, active_grant_id=None)
    assert_no_active_grant_for_terminal(status=SubscriptionStatus.active,
                                        active_grant_id=uuid7())
    # `billing_retry` is not product-entitled either, and the entitlement key catches it.
    with pytest.raises(GrantSchemaError):
        assert_no_active_grant_for_terminal(status=SubscriptionStatus.billing_retry,
                                            active_grant_id=uuid7())


# [utest->req~schema-subscriptions-ingestion-updates-grant-same-transaction~1]
def test_a_status_or_tier_change_settles_the_grant_in_the_same_transaction():
    transaction, other = object(), object()
    grant_id = uuid7()
    assert_ingestion_settles_grant(old_status=SubscriptionStatus.active,
                                   new_status=SubscriptionStatus.expired,
                                   old_tier_id="silver", new_tier_id="silver",
                                   active_grant_id=grant_id, grant_deactivated=True,
                                   subscription_transaction=transaction,
                                   grant_transaction=transaction)
    with pytest.raises(InvariantError):
        assert_ingestion_settles_grant(old_status=SubscriptionStatus.active,
                                       new_status=SubscriptionStatus.expired,
                                       old_tier_id="silver", new_tier_id="silver",
                                       active_grant_id=grant_id, grant_deactivated=True,
                                       subscription_transaction=transaction,
                                       grant_transaction=other)
    # A tier change moves the grant's tier in that same transaction.
    assert_ingestion_settles_grant(old_status=SubscriptionStatus.active,
                                   new_status=SubscriptionStatus.active,
                                   old_tier_id="silver", new_tier_id="gold",
                                   active_grant_id=grant_id, grant_tier_id="gold",
                                   subscription_transaction=transaction,
                                   grant_transaction=transaction)
    with pytest.raises(SubscriptionSchemaError):
        assert_ingestion_settles_grant(old_status=SubscriptionStatus.active,
                                       new_status=SubscriptionStatus.active,
                                       old_tier_id="silver", new_tier_id="gold",
                                       active_grant_id=grant_id, grant_tier_id="silver",
                                       subscription_transaction=transaction,
                                       grant_transaction=transaction)
    # An observation that changes neither status nor tier owes the grant nothing.
    assert_ingestion_settles_grant(old_status=SubscriptionStatus.active,
                                   new_status=SubscriptionStatus.active,
                                   old_tier_id="silver", new_tier_id="silver",
                                   active_grant_id=grant_id)


# [utest->req~schema-subscriptions-non-entitled-marks-grant-ended~1]
def test_a_non_entitled_transition_marks_the_grant_ended_with_an_ends_at():
    status, ends_at = settle_grant_for_non_entitled(SubscriptionStatus.revoked, now=NOW)
    assert status is AccessGrantStatus.revoked and ends_at == NOW
    assert settle_grant_for_non_entitled(SubscriptionStatus.expired, now=NOW)[0] is \
        AccessGrantStatus.expired
    assert settle_grant_for_non_entitled(SubscriptionStatus.billing_retry, now=NOW)[0] is \
        AccessGrantStatus.expired
    with pytest.raises(EntitlementError):
        settle_grant_for_non_entitled(SubscriptionStatus.active, now=NOW)
    assert_grant_ended(grant_status=status, ends_at=ends_at)
    with pytest.raises(SubscriptionSchemaError):
        assert_grant_ended(grant_status=AccessGrantStatus.active, ends_at=NOW)
    with pytest.raises(SubscriptionSchemaError):
        assert_grant_ended(grant_status=AccessGrantStatus.expired, ends_at=None)


# [utest->req~schema-subscriptions-reentitlement-no-auto-reactivate~1]
def test_re_entitlement_never_reactivates_the_grant_on_the_ingestion_path():
    # The entitled-subscription/expired-grant state is allowed to stand until restore.
    assert_no_ingestion_reactivation(new_status=SubscriptionStatus.active,
                                     grant_status=AccessGrantStatus.expired)
    with pytest.raises(SubscriptionSchemaError):
        assert_no_ingestion_reactivation(new_status=SubscriptionStatus.active,
                                         grant_status=AccessGrantStatus.expired,
                                         reactivated=True)
    assert INGESTION_REACTIVATION_PATHS == frozenset()
    assert REACTIVATION_OWNER == "restore_subscription"


# [utest->req~schema-subscriptions-unique-id-user-id-fk-target~1]
def test_unique_id_user_id_is_a_foreign_key_target_and_not_a_second_uniqueness_rule():
    assert "UNIQUE (id, user_id)" in SUBSCRIPTIONS.constraints
    assert "id UUID PRIMARY KEY" in SCHEMA_TEXT
    assert any("REFERENCES core.subscriptions (id, user_id)" in constraint
               for constraint in GRANTS.constraints)
    assert_id_user_id_is_fk_target_only()
    with pytest.raises(SubscriptionSchemaError):
        assert_id_user_id_is_fk_target_only(additional_uniqueness_claimed=True)
    # No trigger logic is involved in the binding.
    assert "CREATE TRIGGER" not in SCHEMA_TEXT


# [utest->req~schema-subscriptions-owner-drift-prevented-by-fk~1]
def test_owner_drift_is_prevented_declaratively_and_never_by_rewriting_a_grant():
    transaction = object()
    owner = uuid7()
    assert_owner_agreement_at_commit(grant_user_id=owner, subscription_user_id=owner,
                                     subscription_transaction=transaction,
                                     grant_transaction=transaction)
    with pytest.raises(InvariantError):
        assert_owner_agreement_at_commit(grant_user_id=owner, subscription_user_id=uuid7(),
                                         subscription_transaction=transaction,
                                         grant_transaction=transaction)
    with pytest.raises(SubscriptionSchemaError):
        assert_owner_agreement_at_commit(grant_user_id=owner, subscription_user_id=owner,
                                         subscription_transaction=transaction,
                                         grant_transaction=transaction,
                                         grant_user_id_rewritten=True)
    with pytest.raises(InvariantError):
        assert_owner_agreement_at_commit(grant_user_id=owner, subscription_user_id=owner,
                                         subscription_transaction=transaction,
                                         grant_transaction=object())
    # Deferrable, so the two rows may be written in either order inside that transaction.
    joined = " ".join(GRANTS.constraints)
    assert "REFERENCES core.subscriptions (id, user_id) DEFERRABLE INITIALLY DEFERRED" in joined


# [utest->req~schema-subscriptions-product-entitled-generated-column-authority~1]
def test_the_generated_column_expression_is_the_single_authority_for_entitlement():
    assert_generated_column_is_the_authority()
    with pytest.raises(SubscriptionSchemaError):
        assert_generated_column_is_the_authority(
            competing_sources=["config.entitled_subscription_statuses"])


# [utest->req~schema-subscriptions-product-entitled-generated-column-authority~1]
def test_the_entitled_status_set_changes_only_by_a_deliberate_schema_migration():
    assert_entitled_status_set_change("schema_migration", expression_altered=True,
                                      lockstep=LOCKSTEP_CHANGES,
                                      grants_adjusted_in_migration=True)
    for mechanism in ENTITLED_STATUS_RUNTIME_MECHANISMS:
        with pytest.raises(SubscriptionSchemaError):
            assert_entitled_status_set_change(mechanism, expression_altered=True,
                                              lockstep=LOCKSTEP_CHANGES,
                                              grants_adjusted_in_migration=True)
    with pytest.raises(SubscriptionSchemaError):
        assert_entitled_status_set_change("schema_migration", expression_altered=False,
                                          lockstep=LOCKSTEP_CHANGES,
                                          grants_adjusted_in_migration=True)
    with pytest.raises(SubscriptionSchemaError):
        assert_entitled_status_set_change("schema_migration", expression_altered=True,
                                          lockstep=("application_logic",),
                                          grants_adjusted_in_migration=True)
    with pytest.raises(SubscriptionSchemaError):
        assert_entitled_status_set_change("schema_migration", expression_altered=True,
                                          lockstep=LOCKSTEP_CHANGES,
                                          grants_adjusted_in_migration=False)


# [utest->req~schema-subscriptions-product-entitled-generated-column-authority~1]
def test_the_partner_generated_column_and_the_deferred_key_are_checked_at_commit():
    transaction = object()
    # Intermediate states inside the transaction are allowed; the commit is what is checked.
    assert_entitlement_holds_at_commit(subscription_status=SubscriptionStatus.grace_period,
                                       grant_status=AccessGrantStatus.active,
                                       subscription_transaction=transaction,
                                       grant_transaction=transaction,
                                       intermediate_states=[SubscriptionStatus.expired])
    with pytest.raises(GrantSchemaError):
        assert_entitlement_holds_at_commit(subscription_status=SubscriptionStatus.expired,
                                           grant_status=AccessGrantStatus.active,
                                           subscription_transaction=transaction,
                                           grant_transaction=transaction)
    with pytest.raises(InvariantError):
        assert_entitlement_holds_at_commit(subscription_status=SubscriptionStatus.active,
                                           grant_status=AccessGrantStatus.active,
                                           subscription_transaction=transaction,
                                           grant_transaction=object())
    assert "CASE WHEN source = 'subscription' AND status = 'active' THEN subscription_id END" in \
        GRANTS.columns["active_subscription_grant_subscription_id"]
    assert "UNIQUE (product_entitled_subscription_id)" in SUBSCRIPTIONS.constraints


# [utest->req~schema-subscriptions-last-cross-account-transfer-month-null~1]
def test_the_cross_account_transfer_month_is_retained_but_never_written():
    assert SUBSCRIPTIONS.columns["last_cross_account_transfer_month"] == "DATE"
    assert_transfer_month_untouched(["status", "tier_id", "user_id"])
    with pytest.raises(InvariantError):
        assert_transfer_month_untouched(["status", "last_cross_account_transfer_month"])


# [utest->req~schema-subscriptions-restore-bound-user-id~1]
def test_the_lifetime_restore_binding_is_set_once_and_never_moved():
    destination = uuid7()
    assert bind_restore_destination(restore_bound_user_id=None,
                                    destination_user_id=destination) is BindingOutcome.bound
    assert bind_restore_destination(restore_bound_user_id=destination,
                                    destination_user_id=destination) is BindingOutcome.idempotent
    with pytest.raises(RestoreRejection) as refused:
        bind_restore_destination(restore_bound_user_id=uuid7(), destination_user_id=destination)
    assert refused.value.result is AuthEventResult.store_transaction_already_linked
    with pytest.raises(RestoreContractError):
        bind_restore_destination(restore_bound_user_id=destination,
                                 destination_user_id=destination, relink=True)
    assert bound_after_restore(_row(), destination_user_id=destination) == destination
    first_owner = uuid7()
    assert bound_after_restore(_row(bound=first_owner),
                               destination_user_id=first_owner) == first_owner
    assert SUBSCRIPTIONS.columns["restore_bound_user_id"] == "UUID REFERENCES core.users (id)"


# [utest->req~schema-subscriptions-restore-serialization~1]
def test_restore_is_serialized_per_store_subscription():
    assert_restore_serialized(list(LOCK_ORDER))
    assert_restore_serialized([LockTier.store_subscription_serialization,
                               LockTier.canonical_subscription_row])
    # The canonical row lock alone, or the serialization alone, is not the pair.
    with pytest.raises(SubscriptionSchemaError):
        assert_restore_serialized([LockTier.store_subscription_serialization,
                                   LockTier.grant_rows])
    with pytest.raises(SubscriptionSchemaError):
        assert_restore_serialized([LockTier.canonical_subscription_row])
    # And they are taken in the locked phase's fixed order.
    with pytest.raises(SubscriptionSchemaError):
        assert_restore_serialized([LockTier.canonical_subscription_row,
                                   LockTier.store_subscription_serialization])


# ==============================================================================================
# `core.store_purchase_tokens`
# ==============================================================================================

# [utest->req~schema-store-purchase-tokens-binding-definition~1]
def test_each_row_binds_one_token_value_to_one_user_scoped_only_by_store():
    row = StorePurchaseTokenRow(user_id=uuid7(), provider=APPLE, identity_value=str(uuid4()))
    assert token_binding(row) == (row.user_id, APPLE, row.identity_value)
    # Store provider implies the store-specific use; there is no identity-kind dimension.
    assert token_kind(APPLE) == "app_account_token"
    assert token_kind(PLAY) == "obfuscated_external_account_id"
    assert IDENTITY_KIND_COLUMNS == frozenset()
    with pytest.raises(SubscriptionSchemaError):
        token_binding(StorePurchaseTokenRow(user_id=uuid7(), provider=APPLE,
                                            identity_value="apple-token-for-user-7"))


# [utest->req~schema-store-purchase-tokens-created-at-user-creation~1]
def test_the_binding_row_is_created_once_at_user_creation():
    row = mint_token_row(user_id=uuid7(), provider=APPLE, operation=AuthOperation.create_user)
    assert UUID(row.identity_value).version == 4
    for operation in (AuthOperation.upgrade_anonymous_to_registered,
                      AuthOperation.restore_subscription,
                      AuthOperation.claim_registered_grant):
        with pytest.raises(InvariantError):
            mint_token_row(user_id=uuid7(), provider=APPLE, operation=operation)


# [utest->req~schema-store-purchase-tokens-row-columns~1]
def test_the_row_carries_the_owning_user_the_store_and_the_token_value():
    assert set(TOKENS.columns) == set(TOKEN_COLUMNS)
    assert_token_row_columns(TOKENS.columns)
    with pytest.raises(SubscriptionSchemaError):
        assert_token_row_columns([*TOKEN_COLUMNS, "identity_kind"])
    with pytest.raises(SubscriptionSchemaError):
        assert_token_row_columns(["user_id", "provider"])


# [utest->req~schema-store-purchase-tokens-provider-token-kinds~1]
def test_the_two_providers_tokens_are_apple_and_google_uuids():
    apple = mint_token_row(user_id=uuid7(), provider=APPLE, operation=AuthOperation.create_user)
    play = mint_token_row(user_id=uuid7(), provider=PLAY, operation=AuthOperation.create_user)
    assert token_kind(apple.provider) == "app_account_token"
    assert token_kind(play.provider) == "obfuscated_external_account_id"
    assert apple.identity_value != play.identity_value
    for row in (apple, play):
        assert UUID(row.identity_value).version == 4
    assert TOKENS.columns["provider"] == "core.subscription_provider NOT NULL"


# [utest->req~schema-store-purchase-tokens-one-per-user-per-provider~1]
def test_at_most_one_token_per_user_per_store_for_the_life_of_the_account():
    assert "UNIQUE (user_id, provider)" in TOKENS.constraints
    tokens = AttributionTokens()
    user_id = uuid7()
    mint_into(tokens, StorePurchaseTokenRow(user_id, APPLE, str(uuid4())))
    mint_into(tokens, StorePurchaseTokenRow(user_id, PLAY, str(uuid4())))
    with pytest.raises(InvariantError):
        mint_into(tokens, StorePurchaseTokenRow(user_id, APPLE, str(uuid4())))
    # Another user's token for the same store is a different row, not a replacement.
    mint_into(tokens, StorePurchaseTokenRow(uuid7(), APPLE, str(uuid4())))


# [utest->req~schema-store-purchase-tokens-random-opaque-uuid~1]
def test_a_token_is_a_random_opaque_server_generated_uuid():
    assert assert_random_opaque_uuid(str(uuid4())).version == 4
    # Derived from account material, guessable, or not a random UUID at all: all refused.
    with pytest.raises(SubscriptionSchemaError):
        assert_random_opaque_uuid(str(uuid5(NAMESPACE_URL, "user@example.com")))
    with pytest.raises(SubscriptionSchemaError):
        assert_random_opaque_uuid(str(uuid7()))
    with pytest.raises(SubscriptionSchemaError):
        assert_random_opaque_uuid(str(uuid4()), derived_from=["email"])
    with pytest.raises(SubscriptionSchemaError):
        assert_random_opaque_uuid(str(uuid4()), derived_from=["issuer", "subject"])
    with pytest.raises(SubscriptionSchemaError):
        assert_random_opaque_uuid("user-7-apple")


# [utest->req~schema-store-purchase-tokens-non-secret-never-rotated~1]
def test_a_token_is_never_rotated_or_replaced():
    value = str(uuid4())
    assert assert_never_rotated(stored=value, incoming=value) == value
    with pytest.raises(SubscriptionSchemaError):
        assert_never_rotated(stored=value, incoming=str(uuid4()))


# [utest->req~schema-store-purchase-tokens-knowledge-not-proof~1]
def test_knowing_a_token_is_proof_of_nothing():
    assert_token_proves_nothing([])
    for claim in ("purchase", "identity_ownership", "restore_authority", "entitlement"):
        with pytest.raises(SubscriptionSchemaError):
            assert_token_proves_nothing([claim])


# [utest->req~schema-store-purchase-tokens-redacted-from-logs~1]
def test_token_values_are_redacted_from_routine_logs():
    payload = {"request_id": "r-1", "identity_value": str(uuid4()),
               "app_account_token": str(uuid4()), "resolved_token_value": str(uuid4()),
               "obfuscated_external_account_id": str(uuid4())}
    redacted = redacted_token_payload(payload)
    assert redacted["request_id"] == "r-1"
    for name in ("identity_value", "app_account_token", "resolved_token_value",
                 "obfuscated_external_account_id"):
        assert redacted[name] == REDACTED


# [utest->req~schema-store-purchase-tokens-resolution-key~1]
def test_ingestion_resolves_the_owning_user_by_provider_and_token_value():
    tokens = AttributionTokens()
    owner = uuid7()
    value = str(uuid4())
    mint_into(tokens, StorePurchaseTokenRow(owner, APPLE, value))
    assert resolve_owning_user(tokens, provider=APPLE, identity_value=value) == owner
    # The key includes the store, and an unknown value resolves to nobody.
    assert resolve_owning_user(tokens, provider=PLAY, identity_value=value) is None
    assert resolve_owning_user(tokens, provider=APPLE, identity_value=str(uuid4())) is None


# [utest->req~schema-store-purchase-tokens-survives-upgrade~1]
def test_the_binding_survives_the_in_place_upgrade():
    before = {"apple": str(uuid4()), "google_play": str(uuid4())}
    assert_binding_survives_upgrade(before, dict(before))
    with pytest.raises(InvariantError):
        assert_binding_survives_upgrade(before, {**before, "apple": str(uuid4())})
    with pytest.raises(InvariantError):
        assert_binding_survives_upgrade(before, {"google_play": before["google_play"]})


# ==============================================================================================
# `core.store_purchases`
# ==============================================================================================

# [utest->req~schema-store-purchases-purpose~1]
def test_the_purchase_table_is_keyed_one_row_per_accepted_store_subscription():
    semantics = purchase_table_semantics()
    assert semantics.keyed_by == ("provider", "external_id")
    assert semantics.mutability == "insert_once"
    # Lifecycle history stays with the store, not as an audit row per event on this table.
    assert semantics.history_in == "the store itself"
    assert "UNIQUE (provider, external_id)" in PURCHASES.constraints
    rows = [record_purchase((), provider=APPLE, external_id="A", identity_value=str(uuid4()),
                            purchase_user_id=None, token_resolved=False)]
    with pytest.raises(SubscriptionSchemaError):
        record_purchase(rows, provider=APPLE, external_id="A", identity_value=str(uuid4()),
                        purchase_user_id=None, token_resolved=False)


# [utest->req~schema-store-purchases-row-records-attribution~1]
def test_each_row_records_one_accepted_subscription_and_the_token_it_was_bought_under():
    buyer = uuid7()
    token = str(uuid4())
    row = record_purchase((), provider=APPLE, external_id="A", identity_value=token,
                          purchase_user_id=buyer, token_resolved=True,
                          verified_purchase={"transactionId": "2000000999",
                                             "originalTransactionId": "A"})
    assert row.external_id == "A"
    assert row.identity_value == token
    assert row.purchase_user_id == buyer
    assert row.resolved_token_value == token
    with pytest.raises(SubscriptionSchemaError):
        record_purchase((), provider=APPLE, external_id="B", identity_value="not-a-uuid",
                        purchase_user_id=buyer, token_resolved=True)


# [utest->req~schema-store-purchases-provider-column~1]
def test_provider_records_which_store_the_purchase_was_made_through():
    for provider in (APPLE, PLAY):
        row = record_purchase((), provider=provider, external_id="A",
                              identity_value=str(uuid4()), purchase_user_id=None,
                              token_resolved=False)
        assert purchase_store(row) is provider
    assert PURCHASES.columns["provider"] == "core.subscription_provider NOT NULL"


# [utest->req~schema-store-purchases-identity-value-uuid~1]
def test_identity_value_is_a_random_uuid_echoed_or_server_generated():
    echoed = str(uuid4())
    assert purchase_identity_value(echoed) == echoed
    generated = purchase_identity_value(None)
    assert UUID(generated).version == 4
    assert purchase_identity_value(None) != generated
    with pytest.raises(SubscriptionSchemaError):
        purchase_identity_value("com.example.account.7")


# [utest->req~schema-store-purchases-subscription-fk~1]
def test_every_purchase_row_names_a_real_canonical_subscription_row():
    subscriptions = [_row("A", user_id=uuid7())]
    assert_names_canonical_subscription(subscriptions, provider=APPLE, external_id="A")
    with pytest.raises(SubscriptionSchemaError):
        assert_names_canonical_subscription(subscriptions, provider=APPLE, external_id="B")
    with pytest.raises(SubscriptionSchemaError):
        assert_names_canonical_subscription(subscriptions, provider=APPLE, external_id="A",
                                            subscription_written_first=False)
    joined = " ".join(PURCHASES.constraints)
    assert "FOREIGN KEY (provider, external_id) REFERENCES core.subscriptions " \
           "(provider, external_id)" in joined
    assert "ON DELETE CASCADE" not in joined
    # A persistence failure is an internal-consistency error, never an attribution mismatch.
    assert persistence_failure_result() is AuthEventResult.internal_error


# [utest->req~schema-store-purchases-store-transaction-ids~1]
def test_the_row_records_the_store_transaction_identifiers_when_available():
    assert store_transaction_identifiers(
        {"transactionId": "2000000999", "originalTransactionId": "A"}) == ("2000000999", "A")
    assert store_transaction_identifiers({}) == (None, None)
    row = record_purchase((), provider=APPLE, external_id="A", identity_value=str(uuid4()),
                          purchase_user_id=None, token_resolved=False,
                          verified_purchase={"transactionId": "2000000999"})
    assert row.store_transaction_id == "2000000999"
    assert row.store_original_transaction_id is None
    for column in ("store_transaction_id", "store_original_transaction_id"):
        assert PURCHASES.columns[column] == "TEXT"


# [utest->req~schema-store-purchases-purchase-user-id-resolution~1]
def test_purchase_user_id_is_resolved_only_through_the_token_binding():
    tokens = AttributionTokens()
    owner = uuid7()
    value = str(uuid4())
    mint_into(tokens, StorePurchaseTokenRow(owner, APPLE, value))
    assert resolve_purchase_user(tokens, provider=APPLE, echoed_token=value) == owner
    # An echoed token that resolves to no binding, and a purchase carrying none at all.
    assert resolve_purchase_user(tokens, provider=APPLE, echoed_token=str(uuid4())) is None
    assert resolve_purchase_user(tokens, provider=APPLE, echoed_token=None) is None
    # The one exception: restore's insert-once creation records the destination user.
    destination = uuid7()
    assert resolve_purchase_user(tokens, provider=APPLE, echoed_token=None,
                                 restoring_destination_user_id=destination) == destination
    # Request-authenticated and client-asserted identities are not attribution sources.
    with pytest.raises(InvariantError):
        resolve_purchase_user(tokens, provider=APPLE, echoed_token=value,
                              asserted={"authenticated_user_id": uuid7()})


# [utest->req~schema-store-purchases-resolved-token-value-fk~1]
def test_resolved_token_value_is_set_exactly_where_a_token_binding_resolved():
    token = str(uuid4())
    assert resolved_token_value(identity_value=token, token_resolved=True) == token
    assert resolved_token_value(identity_value=token, token_resolved=False) is None
    resolved = record_purchase((), provider=APPLE, external_id="A", identity_value=token,
                               purchase_user_id=uuid7(), token_resolved=True)
    assert resolved.resolved_token_value == resolved.identity_value
    # An echoed token that resolved to no binding, and a purchase carrying no token at all.
    for identity_value in (token, str(uuid4())):
        unresolved = record_purchase((), provider=APPLE, external_id="B",
                                     identity_value=identity_value, purchase_user_id=None,
                                     token_resolved=False)
        assert unresolved.resolved_token_value is None
    # And the row restore creates from store-verified proof, which resolved no binding either.
    created = restore_purchase_row([], VerifiedTransaction(APPLE, "C", token),
                                   destination_user_id=uuid7())
    assert created.purchase_user_id is not None
    assert created.resolved_token_value is None
    # The CHECK holds the two together, and the foreign key is MATCH SIMPLE without a cascade.
    with pytest.raises(SubscriptionSchemaError):
        assert_resolved_token_value(replace(resolved, resolved_token_value=str(uuid4())))
    joined = " ".join(PURCHASES.constraints)
    assert "CHECK (resolved_token_value IS NULL OR resolved_token_value = identity_value)" in \
        joined
    assert "FOREIGN KEY (provider, resolved_token_value) REFERENCES core.store_purchase_tokens " \
           "(provider, identity_value)" in joined


# [utest->req~schema-store-purchases-provider-external-id-unique~1]
def test_the_key_is_unique_while_the_token_column_is_not():
    token = str(uuid4())
    first = record_purchase((), provider=APPLE, external_id="A", identity_value=token,
                            purchase_user_id=uuid7(), token_resolved=True)
    # One token spans an account's whole purchase history: a second subscription reuses it.
    second = record_purchase([first], provider=APPLE, external_id="B", identity_value=token,
                             purchase_user_id=first.purchase_user_id, token_resolved=True)
    assert_identity_value_not_unique([first, second])
    with pytest.raises(SubscriptionSchemaError):
        assert_identity_value_not_unique([first, replace(second, external_id="A")])
    assert "UNIQUE (provider, external_id)" in PURCHASES.constraints
    assert APPLIED.indexes["ix_store_purchases_provider_identity_value"].startswith(
        "CREATE INDEX")


# [utest->req~schema-store-purchases-idempotent-lifecycle-events~1]
def test_a_repeat_lifecycle_event_updates_state_in_place_and_inserts_no_second_row():
    owner = uuid7()
    token = str(uuid4())
    first = ingest_lifecycle_event([], [], provider=APPLE, external_id="A",
                                   identity_value=token, status=SubscriptionStatus.active,
                                   tier_id="silver", user_id=owner)
    assert first.purchase_inserted is True
    repeat = ingest_lifecycle_event([first.subscription], list(first.purchases), provider=APPLE,
                                    external_id="A", identity_value=token,
                                    status=SubscriptionStatus.grace_period, tier_id="silver",
                                    user_id=owner)
    assert repeat.purchase_inserted is False
    assert repeat.purchases == first.purchases
    assert repeat.subscription.subscription_id == first.subscription.subscription_id
    assert repeat.subscription.status is SubscriptionStatus.grace_period
    # A new `external_id` under the same token inserts a new row.
    another = ingest_lifecycle_event([first.subscription], list(first.purchases), provider=APPLE,
                                     external_id="B", identity_value=token,
                                     status=SubscriptionStatus.active, tier_id="silver",
                                     user_id=owner)
    assert another.purchase_inserted is True
    assert len(another.purchases) == 2


# [utest->req~schema-store-purchases-attribution-conflict-refused~1]
def test_a_newly_presented_token_for_an_existing_row_is_an_attribution_conflict():
    owner = uuid7()
    token = str(uuid4())
    ingested = ingest_lifecycle_event([], [], provider=APPLE, external_id="A",
                                      identity_value=token, status=SubscriptionStatus.active,
                                      tier_id="silver", user_id=owner)
    existing = ingested.purchases[0]
    assert_no_attribution_conflict(existing, token)
    assert_no_attribution_conflict(None, str(uuid4()))
    with pytest.raises(SubscriptionSchemaError):
        assert_no_attribution_conflict(existing, str(uuid4()))
    with pytest.raises(SubscriptionSchemaError):
        ingest_lifecycle_event([ingested.subscription], list(ingested.purchases), provider=APPLE,
                               external_id="A", identity_value=str(uuid4()),
                               status=SubscriptionStatus.active, tier_id="silver",
                               user_id=owner)
    # The row is not reassigned by the refusal.
    assert existing.identity_value == token


# [utest->req~schema-store-purchases-history-confers-no-entitlement~1]
def test_historical_purchase_rows_confer_no_entitlement():
    owner = uuid7()
    token = str(uuid4())
    rows: list[PurchaseRow] = []
    for external_id in ("A", "B", "C"):
        rows.append(record_purchase(rows, provider=APPLE, external_id=external_id,
                                    identity_value=token, purchase_user_id=owner,
                                    token_resolved=True))
    assert_history_confers_no_entitlement(rows, active_grant_ids=[uuid7()])
    assert_history_confers_no_entitlement(rows, active_grant_ids=[])
    with pytest.raises(SubscriptionSchemaError):
        assert_history_confers_no_entitlement(rows, active_grant_ids=[uuid7(), uuid7()])


# [utest->req~schema-store-purchases-rows-immutable~1]
def test_purchase_rows_are_written_once_and_never_rewritten():
    stored = record_purchase((), provider=APPLE, external_id="A", identity_value=str(uuid4()),
                             purchase_user_id=uuid7(), token_resolved=True,
                             verified_purchase={"transactionId": "2000000999"})
    assert_purchase_row_immutable(stored, stored)
    for name, value in (("purchase_user_id", uuid7()), ("identity_value", str(uuid4())),
                        ("external_id", "B"), ("store_transaction_id", "2000001000"),
                        ("provider", PLAY)):
        with pytest.raises(SubscriptionSchemaError):
            assert_purchase_row_immutable(stored, replace(stored, **{name: value}))
    assert_restore_purchase_write("insert_once")
    for action in ("insert", "update", "revoke"):
        with pytest.raises(SubscriptionSchemaError):
            assert_restore_purchase_write(action)


# [utest->req~schema-store-purchases-authoritative-attribution-record~1]
def test_the_purchase_table_is_the_authoritative_attribution_record():
    assert attribution_record("core.store_purchases") == "core.store_purchases"
    for table in ("core.subscriptions", "core.store_purchase_tokens", "client_request"):
        with pytest.raises(SubscriptionSchemaError):
            attribution_record(table)


# [utest->req~schema-store-purchases-restore-uuid-verification~1]
def test_restore_verifies_a_carried_purchase_uuid_against_the_recorded_attribution():
    token = str(uuid4())
    existing = record_purchase((), provider=APPLE, external_id="A", identity_value=token,
                               purchase_user_id=uuid7(), token_resolved=True)
    assert restore_purchase_row([existing], VerifiedTransaction(APPLE, "A", token)) is existing
    with pytest.raises(RestoreRejection) as refused:
        restore_purchase_row([existing], VerifiedTransaction(APPLE, "A", str(uuid4())))
    assert refused.value.result is AuthEventResult.restore_purchase_uuid_mismatch
    # A missing row is created once from store-verified data rather than rejected.
    destination = uuid7()
    created = restore_purchase_row([], VerifiedTransaction(APPLE, "B", token),
                                   destination_user_id=destination)
    assert created.external_id == "B"
    assert created.purchase_user_id == destination


# [utest->req~schema-store-purchases-not-branch-selector~1]
def test_the_branch_is_selected_by_the_canonical_owner_not_by_the_purchase_row():
    owner = uuid7()
    subscription = _row("A", user_id=owner)
    purchase = record_purchase((), provider=APPLE, external_id="A",
                               identity_value=str(uuid4()), purchase_user_id=uuid7(),
                               token_resolved=True)
    # The purchase row records another user; branch selection still reads the canonical owner.
    assert restore_branch_owner(subscription, purchase) == owner
    assert restore_branch_owner(_row("A"), purchase) is None


# [utest->req~schema-store-purchases-purchase-user-id-not-load-bearing~1]
def test_purchase_user_id_is_not_load_bearing():
    assert_purchase_user_id_not_load_bearing(["core.subscriptions.user_id"])
    for name in ("purchase_user_id", "identity_value", "echoed_uuid"):
        with pytest.raises(StorePurchaseError):
            assert_purchase_user_id_not_load_bearing([name])
    assert_purchase_user_id_use(PurchaseAttributionUse.attribution_record)
    for use in (PurchaseAttributionUse.branch_selection,
                PurchaseAttributionUse.active_user_check,
                PurchaseAttributionUse.restore_source_attribution):
        with pytest.raises(SubscriptionSchemaError):
            assert_purchase_user_id_use(use)


# ==============================================================================================
# `audit.subscription_events`
# ==============================================================================================

# [utest->req~schema-subscription-events-event-type~1]
def test_event_type_records_the_provider_notification_type_as_received():
    for notification_type in ("DID_RENEW", "GRACE_PERIOD_EXPIRED",
                              "SUBSCRIPTION_PURCHASED", "SUBSCRIPTION_IN_GRACE_PERIOD"):
        assert record_event_type(notification_type) == notification_type
    with pytest.raises(SubscriptionSchemaError):
        record_event_type("")
    # An observation, not an internal enum: the column is free text referencing no enum type.
    assert EVENTS.columns["event_type"] == "TEXT NOT NULL"


# [utest->req~schema-subscription-events-tier-transition~1]
def test_the_tier_transition_columns_are_null_when_no_tier_moved():
    assert event_tier_transition(old_tier_id="silver", new_tier_id="gold") == ("silver", "gold")
    assert event_tier_transition(old_tier_id="silver", new_tier_id="silver") == (None, None)
    assert event_tier_transition(old_tier_id=None, new_tier_id=None) == (None, None)
    with pytest.raises(SubscriptionSchemaError):
        event_tier_transition(old_tier_id="silver", new_tier_id=None)
    for column in ("old_tier_id", "new_tier_id"):
        assert EVENTS.columns[column] == "TEXT REFERENCES core.access_tiers (id)"
