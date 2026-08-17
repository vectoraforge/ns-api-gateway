"""The two purchase tables, the purchase flow that fills them, and store notification ingestion."""

from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid7

import pytest

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import AttributionTokens, StoreProvider
from nativespeaker.api.auth.restore import RestoreContractError
from nativespeaker.api.auth.restore_flow import PurchaseRow, SubscriptionRow, VerifiedTransaction
from nativespeaker.api.auth.store_purchases import (
    INGESTION_AUDIT_ROWS,
    INGESTION_OPERATIONS,
    INGESTION_RESPONSE_KIND,
    INGESTION_ROUTES,
    STORE_PURCHASES,
    SUBSCRIPTIONS,
    IngestionLedger,
    StorePurchaseError,
    apple_notification_credential,
    assert_ingestion_route,
    assert_no_silent_success,
    assert_not_an_ownership_selector,
    assert_tokens_held_before_purchase,
    attribution_field,
    build_purchase_row,
    client_purchase_obligations,
    current_state,
    expire_before_insert,
    ingest_verified_purchase,
    purchase_initiation_slot,
    renew_per_term,
    resolve_or_create_purchase_row,
    settled_status,
    store_echoed_token,
    table_semantics,
    upsert_canonical_subscription,
)
from nativespeaker.api.models import SubscriptionStatus

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
BUYER = uuid7()
EXTERNAL_ID = "2000000123456789"
TOKEN = str(uuid4())
TIER_MAP = {"com.nativespeaker.gold.monthly": "gold"}
PRODUCT = "com.nativespeaker.gold.monthly"


def tokens_for(user_id=BUYER, *, provider=StoreProvider.apple, value=TOKEN) -> AttributionTokens:
    tokens = AttributionTokens()
    tokens.mint(user_id, provider, value)
    return tokens


def subscription_row(*, user_id=None, external_id=EXTERNAL_ID) -> SubscriptionRow:
    return SubscriptionRow(subscription_id=uuid7(), provider=StoreProvider.apple,
                           external_id=external_id, status=SubscriptionStatus.active,
                           tier_id="gold", user_id=user_id)


class TestTwoTablesDifferentSemantics:

    def test_each_table_answers_its_own_question(self):
        # [utest->req~restore-two-tables-different-semantics~1]
        assert table_semantics("core.subscriptions").answers \
            == "what is the current state of this store subscription?"
        assert "which attribution token" in table_semantics("core.store_purchases").answers

    def test_the_two_tables_differ_in_mutability(self):
        # [utest->req~restore-two-tables-different-semantics~1]
        assert SUBSCRIPTIONS.mutability.value == "updated_in_place"
        assert STORE_PURCHASES.mutability.value == "insert_once"

    def test_a_third_table_is_neither(self):
        # [utest->req~restore-two-tables-different-semantics~1]
        with pytest.raises(StorePurchaseError):
            table_semantics("core.access_grants")


class TestCanonicalSubscriptionState:

    def test_one_row_per_provider_and_external_id_updated_in_place(self):
        # [utest->req~restore-subscriptions-canonical-current-state~1]
        existing = subscription_row(user_id=BUYER)
        updated = upsert_canonical_subscription([existing], provider=StoreProvider.apple,
                                               external_id=EXTERNAL_ID,
                                               status=SubscriptionStatus.grace_period,
                                               tier_id="gold", user_id=BUYER,
                                               transition="grace_period")
        assert updated.subscription_id == existing.subscription_id
        assert updated.status is SubscriptionStatus.grace_period

    def test_a_new_key_inserts_its_own_row(self):
        # [utest->req~restore-subscriptions-canonical-current-state~1]
        created = upsert_canonical_subscription([], provider=StoreProvider.apple,
                                               external_id=EXTERNAL_ID,
                                               status=SubscriptionStatus.active,
                                               tier_id="gold", user_id=None)
        assert created.user_id is None
        assert created.external_id == EXTERNAL_ID

    def test_the_current_values_are_the_row_s_own(self):
        # [utest->req~restore-subscriptions-canonical-current-state~1]
        assert current_state(subscription_row(user_id=BUYER)) == {
            "user_id": BUYER, "status": SubscriptionStatus.active, "tier_id": "gold"}

    def test_history_lives_in_audit_subscription_events(self):
        # [utest->req~restore-subscriptions-canonical-current-state~1]
        assert SUBSCRIPTIONS.history_in == "audit.subscription_events"

    def test_a_second_row_for_the_same_store_subscription_is_refused(self):
        # [utest->req~restore-subscriptions-canonical-current-state~1]
        rows = [subscription_row(user_id=BUYER), subscription_row(user_id=BUYER)]
        with pytest.raises(StorePurchaseError):
            upsert_canonical_subscription(rows, provider=StoreProvider.apple,
                                          external_id=EXTERNAL_ID,
                                          status=SubscriptionStatus.active, tier_id="gold",
                                          user_id=BUYER)

    def test_an_unknown_transition_is_no_in_place_update(self):
        # [utest->req~restore-subscriptions-canonical-current-state~1]
        with pytest.raises(StorePurchaseError):
            upsert_canonical_subscription([], provider=StoreProvider.apple,
                                          external_id=EXTERNAL_ID,
                                          status=SubscriptionStatus.active, tier_id="gold",
                                          user_id=BUYER, transition="cross_account_transfer")


class TestStorePurchasesAttributionTable:

    def test_the_store_determines_the_attribution_field(self):
        # [utest->req~restore-store-purchases-attribution-table~1]
        assert attribution_field(StoreProvider.apple) == "appAccountToken"
        assert attribution_field(StoreProvider.google_play) == "obfuscatedExternalAccountId"

    def test_one_row_per_accepted_store_subscription(self):
        # [utest->req~restore-store-purchases-attribution-table~1]
        row = build_purchase_row(provider=StoreProvider.apple, external_id=EXTERNAL_ID,
                                identity_value=TOKEN, purchase_user_id=BUYER)
        assert row.identity_value == TOKEN
        assert row.purchase_user_id == BUYER
        with pytest.raises(StorePurchaseError):
            build_purchase_row(provider=StoreProvider.apple, external_id=EXTERNAL_ID,
                               identity_value=TOKEN, purchase_user_id=BUYER, existing=[row])

    def test_an_unattributed_row_records_no_user(self):
        # [utest->req~restore-store-purchases-attribution-table~1]
        row = build_purchase_row(provider=StoreProvider.apple, external_id=EXTERNAL_ID,
                                identity_value=str(uuid4()), purchase_user_id=None)
        assert row.purchase_user_id is None

    def test_the_table_carries_no_lifecycle_history(self):
        # [utest->req~restore-store-purchases-attribution-table~1]
        assert STORE_PURCHASES.history_in == "the store itself"
        assert STORE_PURCHASES.keyed_by == ("provider", "external_id")


class TestEchoedUuidIsEvidence:

    def test_only_the_canonical_row_selects_ownership(self):
        # [utest->req~restore-echoed-uuid-is-evidence-not-identity~1]
        assert assert_not_an_ownership_selector("core.subscriptions.user_id") is None

    @pytest.mark.parametrize("name", ["echoed_uuid", "identity_value", "purchase_user_id",
                                      "app_account_token",
                                      "obfuscated_external_account_id"])
    def test_purchase_evidence_never_selects_the_current_owner(self, name):
        # [utest->req~restore-echoed-uuid-is-evidence-not-identity~1]
        with pytest.raises(StorePurchaseError):
            assert_not_an_ownership_selector(name)

    def test_restore_resolves_the_row_by_provider_and_external_id(self):
        # [utest->req~restore-echoed-uuid-is-evidence-not-identity~1]
        existing = PurchaseRow(purchase_id=uuid7(), provider=StoreProvider.apple,
                               external_id=EXTERNAL_ID, identity_value=TOKEN,
                               purchase_user_id=BUYER)
        verified = VerifiedTransaction(StoreProvider.apple, EXTERNAL_ID, TOKEN)
        assert resolve_or_create_purchase_row([existing], verified) is existing

    def test_a_missing_row_is_created_once_from_store_verified_data(self):
        # [utest->req~restore-echoed-uuid-is-evidence-not-identity~1]
        verified = VerifiedTransaction(StoreProvider.apple, EXTERNAL_ID, TOKEN)
        destination = uuid7()
        created = resolve_or_create_purchase_row([], verified,
                                                destination_user_id=destination)
        assert created.identity_value == TOKEN
        assert created.purchase_user_id == destination

    def test_a_carried_uuid_that_is_not_the_row_s_attribution_is_refused(self):
        # [utest->req~restore-echoed-uuid-is-evidence-not-identity~1]
        existing = PurchaseRow(purchase_id=uuid7(), provider=StoreProvider.apple,
                               external_id=EXTERNAL_ID, identity_value=TOKEN)
        verified = VerifiedTransaction(StoreProvider.apple, EXTERNAL_ID, "another")
        with pytest.raises(StorePurchaseError):
            resolve_or_create_purchase_row([existing], verified)


class TestPurchaseFlowClientSteps:

    def test_step_02_each_client_slot_is_the_store_s_own(self):
        # [utest->req~restore-purchase-flow-02-client-passes-token-to-store~1]
        assert purchase_initiation_slot(StoreProvider.apple) \
            == "StoreKit.Product.PurchaseOption.appAccountToken"
        assert purchase_initiation_slot(StoreProvider.google_play) \
            == "BillingFlowParams.Builder.setObfuscatedAccountId"

    def test_step_03_the_store_echoes_the_value_back(self):
        # [utest->req~restore-purchase-flow-03-store-records-token~1]
        assert store_echoed_token(StoreProvider.apple, {"appAccountToken": TOKEN}) == TOKEN
        assert store_echoed_token(StoreProvider.google_play,
                                  {"obfuscatedExternalAccountId": TOKEN}) == TOKEN

    def test_step_03_a_store_initiated_transaction_echoes_nothing(self):
        # [utest->req~restore-purchase-flow-03-store-records-token~1]
        assert store_echoed_token(StoreProvider.apple, {}) is None
        assert store_echoed_token(StoreProvider.apple, {"appAccountToken": ""}) is None


class TestPurchaseFlowIngestion:

    def test_step_04_resolves_the_owner_and_creates_the_paid_entitlement(self):
        # [utest->req~restore-purchase-flow-04-ingestion-resolves-and-creates~1]
        transaction = object()
        ledger = IngestionLedger()
        ingested = ingest_verified_purchase(provider=StoreProvider.apple,
                                          external_id=EXTERNAL_ID,
                                          verified_purchase={"appAccountToken": TOKEN},
                                          tokens=tokens_for(), product_id=PRODUCT,
                                          product_tier_map=TIER_MAP,
                                          status=SubscriptionStatus.active,
                                          transaction=transaction, ledger=ledger, now=NOW)
        assert ingested.subscription.user_id == BUYER
        assert ingested.purchase.purchase_user_id == BUYER
        assert ingested.resolved_token_value == TOKEN
        assert ingested.grant_source is AccessGrantSource.subscription
        assert ingested.usage_row is not None
        assert ingested.usage_row.monthly_used == 0
        assert ledger.statements == ["upsert_subscription", "insert_store_purchase",
                                     "insert_subscription_grant", "insert_usage_row"]

    def test_step_04_resolves_the_tier_from_the_server_controlled_mapping(self):
        # [utest->req~restore-purchase-flow-04-ingestion-resolves-and-creates~1]
        with pytest.raises(StorePurchaseError):
            ingest_verified_purchase(provider=StoreProvider.apple, external_id=EXTERNAL_ID,
                                    verified_purchase={"appAccountToken": TOKEN},
                                    tokens=tokens_for(), product_id=PRODUCT,
                                    product_tier_map=TIER_MAP,
                                    status=SubscriptionStatus.active, transaction=object(),
                                    client_supplied_tier="platinum")

    def test_step_04_an_unmapped_product_is_refused(self):
        # [utest->req~restore-purchase-flow-04-ingestion-resolves-and-creates~1]
        with pytest.raises(StorePurchaseError):
            ingest_verified_purchase(provider=StoreProvider.apple, external_id=EXTERNAL_ID,
                                    verified_purchase={"appAccountToken": TOKEN},
                                    tokens=tokens_for(), product_id="unknown.product",
                                    product_tier_map=TIER_MAP,
                                    status=SubscriptionStatus.active, transaction=object())

    def test_step_04_an_unresolved_token_leaves_the_subscription_unclaimed(self):
        # [utest->req~restore-purchase-flow-04-ingestion-resolves-and-creates~1]
        ingested = ingest_verified_purchase(provider=StoreProvider.apple,
                                          external_id=EXTERNAL_ID,
                                          verified_purchase={"appAccountToken": str(uuid4())},
                                          tokens=tokens_for(), product_id=PRODUCT,
                                          product_tier_map=TIER_MAP,
                                          status=SubscriptionStatus.active,
                                          transaction=object())
        assert ingested.subscription.user_id is None
        assert ingested.purchase.purchase_user_id is None
        assert ingested.resolved_token_value is None
        assert ingested.grant_id is None
        assert ingested.usage_row is None

    def test_step_04_a_store_initiated_purchase_records_an_internal_uuid(self):
        """Offer-code redemption and store-managed resubscription carry no echoed token."""
        # [utest->req~restore-purchase-flow-04-ingestion-resolves-and-creates~1]
        ingested = ingest_verified_purchase(provider=StoreProvider.apple,
                                          external_id=EXTERNAL_ID,
                                          verified_purchase={}, tokens=tokens_for(),
                                          product_id=PRODUCT, product_tier_map=TIER_MAP,
                                          status=SubscriptionStatus.active,
                                          transaction=object())
        assert UUID(ingested.purchase.identity_value)
        assert ingested.purchase.purchase_user_id is None
        assert ingested.grant_id is None

    def test_step_05_every_blocking_grant_is_expired_before_the_insert(self):
        # [utest->req~restore-purchase-flow-05-expire-then-insert-order~1]
        transaction = object()
        ledger = IngestionLedger()
        blocking = sorted([uuid7(), uuid7()])
        ingested = ingest_verified_purchase(provider=StoreProvider.apple,
                                          external_id=EXTERNAL_ID,
                                          verified_purchase={"appAccountToken": TOKEN},
                                          tokens=tokens_for(), product_id=PRODUCT,
                                          product_tier_map=TIER_MAP,
                                          status=SubscriptionStatus.active,
                                          blocking_grant_ids=blocking,
                                          transaction=transaction, ledger=ledger, now=NOW)
        assert ingested.expired_grant_ids == tuple(blocking)
        expiries = [index for index, name in enumerate(ledger.statements)
                    if name.startswith("expire_grant")]
        insert = ledger.statements.index("insert_subscription_grant")
        assert expiries and max(expiries) < insert

    def test_step_05_each_expiry_records_a_reason(self):
        # [utest->req~restore-purchase-flow-05-expire-then-insert-order~1]
        ledger = IngestionLedger()
        expire_before_insert([uuid7()], ledger=ledger)
        assert ledger.statements == ["expire_grant:superseded_by_verified_purchase"]
        with pytest.raises(StorePurchaseError):
            expire_before_insert([uuid7()], ledger=IngestionLedger(), reason="")

    def test_step_05_no_expiry_may_follow_the_insert(self):
        # [utest->req~restore-purchase-flow-05-expire-then-insert-order~1]
        ledger = IngestionLedger()
        ledger.record("insert_subscription_grant")
        with pytest.raises(StorePurchaseError):
            expire_before_insert([uuid7()], ledger=ledger)

    def test_step_06_renewal_inserts_a_new_grant_per_term(self):
        # [utest->req~restore-purchase-flow-06-renewal-per-term-grant~1]
        prior = uuid7()
        outcome = renew_per_term(active_grant_id=prior, time_ended=True, already_applied=False)
        assert outcome.flipped_grant_id == prior
        assert outcome.new_grant_id is not None
        assert outcome.new_grant_id != prior
        assert settled_status(time_ended=True) is AccessGrantStatus.expired

    def test_step_06_ends_at_is_never_extended_in_place(self):
        # [utest->req~restore-purchase-flow-06-renewal-per-term-grant~1]
        with pytest.raises(StorePurchaseError):
            renew_per_term(active_grant_id=uuid7(), time_ended=True, already_applied=False,
                           extend_ends_at=True)

    def test_step_06_a_redelivered_event_is_an_idempotent_no_op(self):
        # [utest->req~restore-purchase-flow-06-renewal-per-term-grant~1]
        outcome = renew_per_term(active_grant_id=uuid7(), time_ended=True, already_applied=True)
        assert outcome.idempotent_no_op is True
        assert outcome.new_grant_id is None
        assert outcome.flipped_grant_id is None

    def test_step_06_a_superseded_subscription_is_never_silently_reactivated(self):
        # [utest->req~restore-purchase-flow-06-renewal-per-term-grant~1]
        quiet = renew_per_term(active_grant_id=None, time_ended=False, already_applied=False,
                               superseded=True)
        assert quiet.new_grant_id is None
        explicit = renew_per_term(active_grant_id=None, time_ended=False, already_applied=False,
                                  superseded=True,
                                  selecting_operation="restore_subscription")
        assert explicit.new_grant_id is not None


class TestClientPurchaseObligations:

    def test_an_unacknowledged_binding_is_retried_not_swallowed(self):
        # [utest->req~restore-client-purchase-obligations~1]
        assert client_purchase_obligations(token_attached_at_initiation=True,
                                          binding_acknowledged=False) == (
            "retry_attribution", "submit_store_proof", "show_activating_state", "offer_restore")

    def test_an_acknowledged_binding_owes_nothing(self):
        # [utest->req~restore-client-purchase-obligations~1]
        assert client_purchase_obligations(token_attached_at_initiation=True,
                                          binding_acknowledged=True) == ()

    def test_the_token_is_attached_at_purchase_initiation(self):
        # [utest->req~restore-client-purchase-obligations~1]
        with pytest.raises(StorePurchaseError):
            client_purchase_obligations(token_attached_at_initiation=False,
                                        binding_acknowledged=False)

    @pytest.mark.parametrize("action", ["treat_as_success", "dead_end"])
    def test_a_missing_acknowledgment_is_never_a_silent_success(self, action):
        # [utest->req~restore-client-purchase-obligations~1]
        with pytest.raises(StorePurchaseError):
            assert_no_silent_success([action])

    def test_the_client_always_holds_both_tokens_before_purchase(self):
        # [utest->req~restore-client-purchase-obligations~1]
        assert assert_tokens_held_before_purchase({"apple": TOKEN,
                                                   "google_play": str(uuid4())}) is None
        with pytest.raises(RestoreContractError):
            assert_tokens_held_before_purchase({"apple": TOKEN})


class TestStoreNotificationIngestionRoutes:

    def test_both_provider_callback_routes_are_the_ingestion_path(self):
        # [utest->req~restore-ingestion-provider-callback-routes~1]
        assert INGESTION_ROUTES == (("POST", "/webhooks/app-store"),
                                    ("POST", "/webhooks/google-play/rtdn"))
        assert assert_ingestion_route("POST", "/webhooks/app-store") == "apple_signed_payload"
        assert assert_ingestion_route("POST", "/webhooks/google-play/rtdn") == "pubsub_oidc"

    def test_they_are_no_canonical_auth_operation_and_write_no_audit_row(self):
        # [utest->req~restore-ingestion-provider-callback-routes~1]
        assert INGESTION_OPERATIONS == frozenset()
        assert INGESTION_AUDIT_ROWS == 0
        assert INGESTION_RESPONSE_KIND == "plain_http_status"

    def test_a_barrier_route_is_no_ingestion_route(self):
        """A signed-in user submitting purchase evidence uses the restore endpoint instead."""
        # [utest->req~restore-ingestion-provider-callback-routes~1]
        with pytest.raises(StorePurchaseError):
            assert_ingestion_route("POST", "/auth/restore-subscription")


class TestAppleSignedPayloadAuth:

    def test_the_body_s_signed_payload_is_the_whole_credential(self):
        # [utest->req~restore-apple-webhook-signed-payload-auth~1]
        assert apple_notification_credential({"signedPayload": "a.b.c"}) == "a.b.c"

    def test_no_authorization_field_authenticates_the_notification(self):
        # [utest->req~restore-apple-webhook-signed-payload-auth~1]
        with pytest.raises(StorePurchaseError):
            apple_notification_credential({"signedPayload": "a.b.c"},
                                          authorization=("Bearer firebase-id-token",))

    def test_a_body_without_a_signed_payload_carries_no_credential(self):
        # [utest->req~restore-apple-webhook-signed-payload-auth~1]
        with pytest.raises(StorePurchaseError):
            apple_notification_credential({})
        with pytest.raises(StorePurchaseError):
            apple_notification_credential({"signedPayload": ""})
