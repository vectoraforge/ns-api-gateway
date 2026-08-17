"""The authority a verified store notification carries: entitlement, and nothing more."""

from uuid import uuid7

import pytest

from nativespeaker.api.auth.ingestion_authority import (
    CLIENT_EVIDENCE_ROUTE,
    IngestionAuthorityError,
    IngestionEffect,
    UnclaimedIngestion,
    assert_acts_on_linked_account,
    assert_ingestion_authority,
    assert_ingestion_scope,
    assert_no_client_submitted_evidence,
    assert_no_identity_or_session_effect,
    assert_restore_route_keeps_both_checks,
    ingestion_routes_carry_no_id_token,
    ingestion_target_user,
    permitted_ingestion_write,
    unmatched_token_outcome,
)
from nativespeaker.api.auth.invariants import AttributionTokens, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation

APPLE = StoreProvider.apple
EXTERNAL_ID = "2000000123456789"


def tokens_for(user_id, token: str) -> AttributionTokens:
    tokens = AttributionTokens()
    tokens.mint(user_id, APPLE, token)
    return tokens


class TestEntitlementAuthorityOnly:

    def test_the_three_entitlement_effects_are_the_whole_authority(self):
        # [utest->req~restore-ingestion-authority-entitlement-only~1]
        allowed = [str(effect) for effect in IngestionEffect]
        assert assert_ingestion_authority(allowed) == tuple(IngestionEffect)

    def test_anything_beyond_entitlement_is_refused(self):
        # [utest->req~restore-ingestion-authority-entitlement-only~1]
        for beyond in ("delete_user", "rewrite_store_purchase", "issue_free_grant"):
            with pytest.raises(IngestionAuthorityError):
                assert_ingestion_authority(["update_canonical_subscription", beyond])


class TestPermittedWrites:

    def test_it_may_move_the_canonical_row_the_event_and_the_grant(self):
        # [utest->req~restore-ingestion-may-update-subscription-and-grant~1]
        assert permitted_ingestion_write(
            IngestionEffect.update_canonical_subscription) == "core.subscriptions"
        assert permitted_ingestion_write(
            IngestionEffect.append_subscription_event) == "audit.subscription_events"
        assert permitted_ingestion_write(
            IngestionEffect.update_subscription_grant) == "core.access_grants"

    def test_it_writes_only_its_own_store_subscriptions_row(self):
        # [utest->req~restore-ingestion-may-update-subscription-and-grant~1]
        assert assert_ingestion_scope(IngestionEffect.update_canonical_subscription,
                                      notification_key=(APPLE, EXTERNAL_ID),
                                      row_key=(APPLE, EXTERNAL_ID)) == "core.subscriptions"
        with pytest.raises(IngestionAuthorityError):
            assert_ingestion_scope(IngestionEffect.update_canonical_subscription,
                                   notification_key=(APPLE, EXTERNAL_ID),
                                   row_key=(APPLE, "2000000999999999"))


class TestActsOnlyOnLinkedAccount:

    def test_the_echoed_token_resolves_the_account(self):
        # [utest->req~restore-ingestion-acts-only-on-linked-account~1]
        owner = uuid7()
        target = ingestion_target_user(provider=APPLE, echoed_token="tok",
                                       tokens=tokens_for(owner, "tok"),
                                       canonical_user_id=None)
        assert target.user_id == owner
        assert target.resolved_by == "store_purchase_tokens"

    def test_the_canonical_rows_current_owner_is_the_other_link(self):
        # [utest->req~restore-ingestion-acts-only-on-linked-account~1]
        owner = uuid7()
        target = ingestion_target_user(provider=APPLE, echoed_token=None,
                                       tokens=AttributionTokens(), canonical_user_id=owner)
        assert target.user_id == owner
        assert target.resolved_by == "canonical_subscription_user_id"

    def test_the_current_owner_wins_over_a_token_minted_for_another_account(self):
        """After an adoption the token still names the account it was minted for at purchase; the
        account the store subscription is *already linked to* is the canonical row's owner, and
        ingestion acts on that one."""
        # [utest->req~restore-ingestion-acts-only-on-linked-account~1]
        original, current = uuid7(), uuid7()
        target = ingestion_target_user(provider=APPLE, echoed_token="tok",
                                       tokens=tokens_for(original, "tok"),
                                       canonical_user_id=current)
        assert target.user_id == current
        assert target.resolved_by == "canonical_subscription_user_id"
        with pytest.raises(IngestionAuthorityError):
            assert_acts_on_linked_account(target, original)

    def test_no_other_account_is_reachable(self):
        # [utest->req~restore-ingestion-acts-only-on-linked-account~1]
        owner, intruder = uuid7(), uuid7()
        target = ingestion_target_user(provider=APPLE, echoed_token="tok",
                                       tokens=tokens_for(owner, "tok"),
                                       canonical_user_id=None)
        assert assert_acts_on_linked_account(target, owner) == owner
        with pytest.raises(IngestionAuthorityError):
            assert_acts_on_linked_account(target, intruder)


class TestNoSessionOrIdentityEffect:

    def test_it_creates_no_session_token_user_or_identity(self):
        # [utest->req~restore-ingestion-never-creates-session-or-identity~1]
        for forbidden in ("create_session", "mint_token", "issue_token", "create_user_row",
                          "create_external_identity_row", "grant_privilege"):
            with pytest.raises(IngestionAuthorityError):
                assert_no_identity_or_session_effect(["update_canonical_subscription", forbidden])

    def test_the_entitlement_effects_pass(self):
        # [utest->req~restore-ingestion-never-creates-session-or-identity~1]
        assert assert_no_identity_or_session_effect(
            [str(effect) for effect in IngestionEffect]) is None


class TestUnmatchedTokenLeavesUnclaimed:

    def test_an_unresolved_token_leaves_the_subscription_unclaimed(self):
        # [utest->req~restore-ingestion-unmatched-token-leaves-unclaimed~1]
        target = ingestion_target_user(provider=APPLE, echoed_token="unknown-token",
                                       tokens=AttributionTokens(), canonical_user_id=None)
        outcome = unmatched_token_outcome(target)
        assert isinstance(outcome, UnclaimedIngestion)
        assert outcome.user_id is None
        assert outcome.subscription_grant_id is None
        assert outcome.claimed_by is AuthOperation.restore_subscription

    def test_a_resolved_token_is_not_left_unclaimed(self):
        # [utest->req~restore-ingestion-unmatched-token-leaves-unclaimed~1]
        owner = uuid7()
        target = ingestion_target_user(provider=APPLE, echoed_token="tok",
                                       tokens=tokens_for(owner, "tok"), canonical_user_id=None)
        assert unmatched_token_outcome(target) == owner


class TestNoClientSubmittedEvidence:

    def test_purchase_evidence_on_an_ingestion_route_is_refused(self):
        # [utest->req~restore-ingestion-no-client-submitted-evidence~1]
        assert assert_no_client_submitted_evidence("POST", "/webhooks/app-store",
                                                   {"signedPayload": "jws"}) is None
        with pytest.raises(IngestionAuthorityError):
            assert_no_client_submitted_evidence("POST", "/webhooks/app-store",
                                                {"restore_proof": "signed.storekit.tx"})
        with pytest.raises(IngestionAuthorityError):
            assert_no_client_submitted_evidence("POST", "/webhooks/google-play/rtdn",
                                                {"purchase_token": "play-token"})

    def test_the_ingestion_routes_carry_no_firebase_id_token(self):
        # [utest->req~restore-ingestion-no-client-submitted-evidence~1]
        assert ("POST", "/webhooks/app-store") in ingestion_routes_carry_no_id_token()

    def test_restore_needs_both_the_id_token_and_the_store_verification(self):
        # [utest->req~restore-ingestion-no-client-submitted-evidence~1]
        assert assert_restore_route_keeps_both_checks(
            id_token_verified=True, store_evidence_verified=True) == CLIENT_EVIDENCE_ROUTE
        with pytest.raises(IngestionAuthorityError):
            assert_restore_route_keeps_both_checks(id_token_verified=False,
                                                   store_evidence_verified=True)
        with pytest.raises(IngestionAuthorityError):
            assert_restore_route_keeps_both_checks(id_token_verified=True,
                                                   store_evidence_verified=False)
