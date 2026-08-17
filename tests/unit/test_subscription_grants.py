"""Subscription-backed access grants and usage state: where paid billing lives, when a
subscription-backed grant may stand active, what verified purchase ingestion creates, and the fact
that a paid entitlement's monthly counter never leaves its grant."""

from uuid import uuid7

import pytest

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.restore import RestoreBranch, RestoreContractError
from nativespeaker.api.auth.restore_flow import (
    GRANT_REASSIGNMENT_PATHS,
    OWNER_CHANGING_BRANCHES,
    SubscriptionRow,
    assert_owner_change_only_by_adoption,
)
from nativespeaker.api.auth.store_purchases import (
    IngestionLedger,
    ingest_verified_purchase,
    upsert_canonical_subscription,
)
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.grants import (
    BILLING_TABLE,
    ENTITLEMENT_TABLE,
    PRODUCT_ENTITLED_GENERATED_COLUMN,
    PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES,
    USAGE_TABLE,
    EntitlementError,
    assert_status_writer_settled_grant,
    is_product_entitled,
    settle_subscription_grant,
)
from nativespeaker.api.quota.usage import UsageRowError, assert_stays_with_grant
from tests.unit.conftest import grant_row

APPLE = StoreProvider.apple
EXTERNAL_ID = "2000000123456789"


class TestPaidBillingLivesInSubscriptions:

    def test_the_canonical_row_is_one_per_provider_external_id(self):
        # [utest->req~restore-paid-billing-in-subscriptions~1]
        assert BILLING_TABLE == "core.subscriptions"
        owner = uuid7()
        first = upsert_canonical_subscription((), provider=APPLE, external_id=EXTERNAL_ID,
                                              status=SubscriptionStatus.active, tier_id="gold",
                                              user_id=owner)
        # A second observation updates that same row in place rather than adding a second one.
        again = upsert_canonical_subscription([first], provider=APPLE, external_id=EXTERNAL_ID,
                                              status=SubscriptionStatus.grace_period,
                                              tier_id="gold", user_id=owner)
        assert again.subscription_id == first.subscription_id
        assert again.status is SubscriptionStatus.grace_period

    def test_a_duplicate_canonical_row_is_refused(self):
        # [utest->req~restore-paid-billing-in-subscriptions~1]
        duplicate = [SubscriptionRow(subscription_id=uuid7(), provider=APPLE,
                                     external_id=EXTERNAL_ID, status=SubscriptionStatus.active,
                                     tier_id="gold") for _ in range(2)]
        with pytest.raises(Exception):
            upsert_canonical_subscription(duplicate, provider=APPLE, external_id=EXTERNAL_ID,
                                          status=SubscriptionStatus.active, tier_id="gold",
                                          user_id=None)


class TestOwnerChangesOnlyByAdoption:

    def test_adoption_is_the_only_owner_changing_branch(self):
        # [utest->req~restore-owner-changes-only-by-adoption~1]
        assert OWNER_CHANGING_BRANCHES == frozenset({RestoreBranch.adoption})
        destination = uuid7()
        transaction = object()
        assert assert_owner_change_only_by_adoption(
            branch=RestoreBranch.adoption,
            grant_created_for=destination,
            destination_user_id=destination,
            subscription_transaction=transaction,
            grant_transaction=transaction) == destination
        with pytest.raises(RestoreContractError):
            assert_owner_change_only_by_adoption(
                branch=RestoreBranch.same_account,
                grant_created_for=destination,
                destination_user_id=destination,
                subscription_transaction=transaction,
                grant_transaction=transaction)

    def test_the_adoption_grant_is_created_in_the_same_transaction(self):
        # [utest->req~restore-owner-changes-only-by-adoption~1]
        destination = uuid7()
        with pytest.raises(RestoreContractError):
            assert_owner_change_only_by_adoption(
                branch=RestoreBranch.adoption,
                grant_created_for=destination,
                destination_user_id=destination,
                subscription_transaction=object(),
                grant_transaction=object())

    def test_no_path_moves_an_existing_subscription_grant_to_another_user(self):
        # [utest->req~restore-owner-changes-only-by-adoption~1]
        assert GRANT_REASSIGNMENT_PATHS == frozenset()
        destination, other = uuid7(), uuid7()
        transaction = object()
        with pytest.raises(RestoreContractError):
            assert_owner_change_only_by_adoption(
                branch=RestoreBranch.adoption,
                grant_created_for=destination,
                destination_user_id=destination,
                subscription_transaction=transaction,
                grant_transaction=transaction,
                moved_grant_user_id=other)


class TestProductEntitledStatuses:

    def test_the_set_is_exactly_active_and_grace_period(self):
        # [utest->req~restore-product-entitled-statuses~1]
        assert PRODUCT_ENTITLED_SUBSCRIPTION_STATUSES == frozenset({
            SubscriptionStatus.active, SubscriptionStatus.grace_period})
        assert is_product_entitled(SubscriptionStatus.active)
        assert is_product_entitled(SubscriptionStatus.grace_period)

    def test_billing_retry_expired_and_revoked_are_not_entitled(self):
        # [utest->req~restore-product-entitled-statuses~1]
        for status in (SubscriptionStatus.billing_retry, SubscriptionStatus.expired,
                       SubscriptionStatus.revoked):
            assert not is_product_entitled(status)

    def test_the_generated_column_is_cited_as_the_authority(self):
        # [utest->req~restore-product-entitled-statuses~1]
        assert PRODUCT_ENTITLED_GENERATED_COLUMN == "product_entitled_subscription_id"


class TestSubscriptionGrantActiveOnlyWhenEntitled:

    def test_leaving_the_entitled_set_settles_the_grant(self):
        # [utest->req~restore-subscription-grant-active-only-when-entitled~1]
        transaction = object()
        with pytest.raises(EntitlementError):
            assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                               new_status=SubscriptionStatus.expired,
                                               active_grant_id=uuid7(),
                                               grant_deactivated=False,
                                               subscription_transaction=transaction,
                                               grant_transaction=transaction)
        assert assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                                  new_status=SubscriptionStatus.expired,
                                                  active_grant_id=uuid7(),
                                                  grant_deactivated=True,
                                                  subscription_transaction=transaction,
                                                  grant_transaction=transaction) is None

    def test_a_move_inside_the_entitled_set_leaves_the_grant_active(self):
        # [utest->req~restore-subscription-grant-active-only-when-entitled~1]
        transaction = object()
        assert assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                                  new_status=SubscriptionStatus.grace_period,
                                                  active_grant_id=uuid7(),
                                                  subscription_transaction=transaction,
                                                  grant_transaction=transaction) is None


class TestIngestionUpdatesSubscriptionAndGrantTogether:

    def test_the_two_writes_share_one_transaction(self):
        # [utest->req~restore-ingestion-updates-subscription-and-grant-same-transaction~1]
        with pytest.raises(EntitlementError):
            assert_status_writer_settled_grant(old_status=SubscriptionStatus.active,
                                               new_status=SubscriptionStatus.revoked,
                                               active_grant_id=uuid7(),
                                               grant_deactivated=True,
                                               subscription_transaction=object(),
                                               grant_transaction=object())


class TestPurchaseIngestionCreatesGrantAndUsage:

    def test_one_transaction_upserts_the_row_writes_the_purchase_and_creates_the_grant(self):
        # [utest->req~restore-purchase-ingestion-creates-grant-and-usage~1]
        owner = uuid7()
        tokens = _tokens(owner, "echoed-token")
        ledger = IngestionLedger()
        transaction = object()
        ingested = ingest_verified_purchase(
            provider=APPLE, external_id=EXTERNAL_ID, status=SubscriptionStatus.active,
            product_id="com.example.nativespeaker.gold",
            product_tier_map={"com.example.nativespeaker.gold": "gold"},
            verified_purchase={"appAccountToken": "echoed-token",
                               "transactionId": "3000", "originalTransactionId": EXTERNAL_ID},
            tokens=tokens, transaction=transaction, ledger=ledger)
        assert ingested.subscription.user_id == owner
        assert ingested.grant_source is AccessGrantSource.subscription
        assert ingested.usage_row is not None
        assert ingested.usage_row.grant_id == ingested.grant_id
        assert ingested.usage_row.monthly_used == 0
        assert ingested.subscription.tier_id == "gold"
        assert ledger.statements[:2] == ["upsert_subscription", "insert_store_purchase"]
        assert "insert_subscription_grant" in ledger.statements
        assert "insert_usage_row" in ledger.statements

    def test_a_blocking_grant_is_expired_before_the_insert_never_deleted(self):
        # [utest->req~restore-purchase-ingestion-creates-grant-and-usage~1]
        owner = uuid7()
        blocking = uuid7()
        ledger = IngestionLedger()
        ingested = ingest_verified_purchase(
            provider=APPLE, external_id=EXTERNAL_ID, status=SubscriptionStatus.active,
            product_id="com.example.nativespeaker.gold",
            product_tier_map={"com.example.nativespeaker.gold": "gold"},
            verified_purchase={"appAccountToken": "echoed-token"},
            tokens=_tokens(owner, "echoed-token"), blocking_grant_ids=[blocking],
            transaction=object(), ledger=ledger)
        assert ingested.expired_grant_ids == (blocking,)
        expiry = ledger.statements.index("expire_grant:superseded_by_verified_purchase")
        assert expiry < ledger.statements.index("insert_subscription_grant")

    def test_a_client_supplied_tier_is_refused(self):
        # [utest->req~restore-purchase-ingestion-creates-grant-and-usage~1]
        with pytest.raises(Exception):
            ingest_verified_purchase(
                provider=APPLE, external_id=EXTERNAL_ID, status=SubscriptionStatus.active,
                product_id="com.example.nativespeaker.gold",
                product_tier_map={"com.example.nativespeaker.gold": "gold"},
                verified_purchase={"appAccountToken": "echoed-token"},
                tokens=_tokens(uuid7(), "echoed-token"), transaction=object(),
                client_supplied_tier="platinum")


class TestRestoreNeverActivatesANonEntitledGrant:

    def test_a_non_entitled_subscription_blocks_the_grant(self):
        # [utest->req~restore-must-not-activate-non-entitled-grant~1]
        destination = uuid7()
        grant = grant_row(user_id=destination, tier_id="gold",
                          source=AccessGrantSource.subscription,
                          status=AccessGrantStatus.active)
        for status in (SubscriptionStatus.expired, SubscriptionStatus.revoked,
                       SubscriptionStatus.billing_retry):
            with pytest.raises(EntitlementError):
                settle_subscription_grant(grant, subscription_status=status,
                                          destination_user_id=destination,
                                          usage_row_grant_id=grant.grant_id)

    def test_an_entitled_subscription_lets_it_stand(self):
        # [utest->req~restore-must-not-activate-non-entitled-grant~1]
        destination = uuid7()
        grant = grant_row(user_id=destination, tier_id="gold",
                          source=AccessGrantSource.subscription)
        assert settle_subscription_grant(grant, subscription_status=SubscriptionStatus.active,
                                         destination_user_id=destination,
                                         usage_row_grant_id=grant.grant_id) is grant


class TestUsageRowStaysWithItsGrant:

    def test_the_counter_never_repoints_and_is_never_minted_fresh(self):
        # [utest->req~restore-usage-row-stays-with-grant~1]
        grant_id, other = uuid7(), uuid7()
        assert assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=grant_id) is None
        with pytest.raises(UsageRowError):
            assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=other)
        with pytest.raises(UsageRowError):
            assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=grant_id,
                                    minted_fresh=True)

    def test_usage_is_per_grant_state(self):
        # [utest->req~restore-usage-row-stays-with-grant~1]
        assert USAGE_TABLE == "core.user_monthly_usage"
        assert ENTITLEMENT_TABLE == "core.access_grants"


def _tokens(owner, value: str):
    from nativespeaker.api.auth.invariants import AttributionTokens

    tokens = AttributionTokens()
    tokens.mint(owner, APPLE, value)
    return tokens
