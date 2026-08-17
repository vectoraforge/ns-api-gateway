"""`POST /auth/upgrade-anonymous` from the sessions side: the same-UID linking flip, the branch
matrix each call resolves against its own live `providerData` read, the interrupted-upgrade repair
path, and the identity transition a success records."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid7

import pytest
import yaml

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome
from nativespeaker.api.auth.create_user import AdminLookupResult, ProviderNotLinkedCause
from nativespeaker.api.auth.external_identities import IdentityState
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider, is_challenge_bearing
from nativespeaker.api.auth.profile import AdminUserRecord
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.auth.upgrade import (
    ABANDONED_ACCOUNT_MECHANISMS,
    ABANDONED_ACCOUNT_MUTATIONS,
    IDENTITY_LOCK_ORDER,
    NON_TRANSFER_COPY_IS_DISPLAY_ONLY,
    REPAIR_MECHANISMS,
    REPAIR_READ_SURFACES,
    REPAIR_ROLE_OPTIMIZATIONS,
    STRANDED_ACCOUNT_GRANTS,
    STRANDING_RESIDUAL_EXPOSURE,
    STRANDING_SIDE_EFFECTS,
    TRANSITION_REJECTION_MUTATIONS,
    TRANSITION_REJECTION_REMEDY,
    UPGRADE_CREATED_IDENTITY_ROWS,
    UPGRADE_DEVICE_GRANT_BITS,
    UPGRADE_DISPLAY_NAME_SOURCES,
    UPGRADE_GRANT_WRITES,
    UPGRADE_RETIRED_IDENTITY_ROWS,
    RepairRetry,
    TransitionDivergence,
    UpgradeBranch,
    UpgradeDecision,
    UpgradeError,
    UpgradePurpose,
    UpgradeRejection,
    UpgradeUser,
    abandoned_anonymous_account,
    assert_confirmation_source,
    assert_identity_metadata_only,
    assert_in_place,
    assert_state_preserved,
    assert_upgrade_transaction,
    credential_already_in_use_route,
    entry_target_provider,
    linking_flip,
    repair_disposition,
    repair_needed,
    stranded_exposure,
    stranded_upgrade,
    transition_rejection,
    upgrade_branch,
    upgrade_purpose,
    upgraded_user,
)
from nativespeaker.api.auth.users import (
    UPGRADE_GATEWAY_DEFAULT_LIMIT,
    UsersError,
    assert_no_secondary_auth_state,
    assert_upgrade_gateway_limit,
    upgrade_gateway_admission,
)
from nativespeaker.api.exceptions import ServiceError
from nativespeaker.api.ratelimit.config import GatewayRateLimitsConfig
from nativespeaker.api.ratelimit.ordering import AdmissionLedger, ExpensiveStep
from unit.test_create_user import ADMIN_CLIENT, ANONYMOUS, APPLE, GOOGLE, FakeLookup, entries
from unit.test_upgrade_anonymous import (
    APPLE_UID,
    GOOGLE_UID,
    LATER,
    NOW,
    PRESERVED,
    Flow,
    identity_row,
    upgrade_context,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
UPGRADE = AuthOperation.upgrade_anonymous_to_registered


def registered_flow(*, provider: IdentityProvider = IdentityProvider.google,
                    provider_uid: str = GOOGLE_UID, lookup: FakeLookup | None = None) -> Flow:
    """A row that already stores a registered binding — the idempotent-repeat starting point."""
    return Flow(stored=provider, provider_uid=provider_uid,
                user=UpgradeUser(id=uuid7(), registered_at=LATER),
                lookup=lookup or FakeLookup(GOOGLE))


# --- The same-UID linking upgrade -----------------------------------------------------------


class TestSameUidUpgrade:
    # [utest->req~sessions-upgrade-same-uid-only~1]
    async def test_the_anonymous_and_registered_identity_are_one_row_for_one_verified_pair(self):
        flow = Flow()
        before = flow.identity
        account = await flow.complete("google")
        assert (account.identity.id, account.identity.user_id) == (before.id, before.user_id)
        assert (account.identity.issuer, account.identity.subject) == (before.issuer,
                                                                       before.subject)
        assert account.identity.provider is IdentityProvider.google
        # One flip, on the one row: no second identity row is written anywhere.
        assert len(flow.identities.flips) == 1
        assert UPGRADE_CREATED_IDENTITY_ROWS == frozenset()

    # [utest->req~sessions-upgrade-same-uid-only~1]
    def test_the_flip_never_moves_the_row_to_another_user_or_pair(self):
        row = identity_row()
        decision = UpgradeDecision(UpgradeBranch.mutable, IdentityProvider.google, GOOGLE_UID)
        moved = replace(row, subject="another-subject")
        with pytest.raises((UpgradeError, UsersError)):
            linking_flip(row, decision, context=upgrade_context(moved), transaction=object())

    # [utest->req~sessions-upgrade-linked-identity-flip~1]
    async def test_the_declared_provider_is_confirmed_against_the_live_admin_read(self):
        flow = Flow()
        account = await flow.complete("google")
        # Exactly one `getUser(subject)` read, on the issuer-selected Admin client.
        assert flow.lookup.calls == 1
        assert flow.lookup.clients == [ADMIN_CLIENT]
        assert account.identity.provider_uid == GOOGLE_UID

    # [utest->req~sessions-upgrade-linked-identity-flip~1]
    def test_only_google_and_apple_may_be_declared(self):
        for declared in ("google", "apple"):
            assert entry_target_provider(declared,
                                        phase=RequestMode.prepare) is IdentityProvider(declared)
        for declared in ("anonymous", "facebook", None):
            with pytest.raises((UpgradeError, ServiceError)):
                entry_target_provider(declared, phase=RequestMode.prepare)

    # [utest->req~sessions-upgrade-linked-identity-flip~1]
    async def test_a_classification_that_differs_from_the_declaration_mutates_nothing(self):
        flow = Flow(lookup=FakeLookup(APPLE))
        with pytest.raises(UpgradeRejection):
            await flow.complete("google")
        assert flow.identities.flips == []
        assert flow.identities.identity.provider is IdentityProvider.anonymous
        assert flow.identities.user.registered_at is None

    # [utest->req~sessions-upgrade-linked-identity-flip~1]
    async def test_the_confirmation_runs_even_when_the_row_already_stores_the_declaration(self):
        flow = registered_flow()
        account = await flow.complete("google")
        assert account.branch is UpgradeBranch.idempotent
        assert flow.lookup.calls == 1

    # [utest->req~sessions-upgrade-linked-identity-flip~1]
    def test_the_flip_sets_registered_at_and_copies_only_a_verified_missing_email(self):
        user = UpgradeUser(id=uuid7())
        verified = AdminUserRecord(email="user@example.com", email_verified=True)
        upgraded = upgraded_user(user, verified, provider=IdentityProvider.google, now=NOW)
        assert (upgraded.registered_at, upgraded.email) == (NOW, "user@example.com")
        assert upgraded.display_name is None
        assert UPGRADE_DISPLAY_NAME_SOURCES == frozenset()
        # Unverified and empty addresses are not copied.
        for record in (AdminUserRecord(email="user@example.com", email_verified=False),
                       AdminUserRecord(email="", email_verified=True),
                       None):
            assert upgraded_user(user, record, provider=IdentityProvider.google,
                                 now=NOW).email is None
        # A stored email and a stored `registered_at` are never overwritten.
        stored = UpgradeUser(id=user.id, email="kept@example.com", registered_at=LATER,
                            display_name="Kept")
        kept = upgraded_user(stored, verified, provider=IdentityProvider.google, now=NOW)
        assert (kept.email, kept.registered_at, kept.display_name) == ("kept@example.com", LATER,
                                                                       "Kept")

    # [utest->req~sessions-upgrade-linked-identity-flip~1]
    # [utest->req~sessions-upgrade-token-freshness-irrelevant~1]
    def test_no_token_claim_or_request_header_confirms_the_provider(self):
        assert assert_confirmation_source() == "firebase_admin_provider_data"
        for source in ("token_claim", "request_header", "client_declaration", "stored_provider",
                       "firebase_sign_in_provider"):
            with pytest.raises(UpgradeError):
                assert_confirmation_source(source)

    # [utest->req~sessions-upgrade-token-freshness-irrelevant~1]
    async def test_an_anonymous_era_token_of_any_freshness_completes_the_upgrade(self):
        flow = Flow()
        # The context carries the pre-flip stored `anonymous` provider, as a stale token's
        # resolution would: the flip's content still comes from the live Admin read.
        assert flow.context.provider is IdentityProvider.anonymous
        account = await flow.complete("google")
        assert account.identity.provider is IdentityProvider.google
        assert account.identity.provider_uid == GOOGLE_UID


# --- The one transaction -----------------------------------------------------------------------


class TestSingleTransaction:
    # [utest->req~sessions-upgrade-single-transaction~1]
    async def test_the_flip_the_registered_at_write_and_the_email_copy_share_one_transaction(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        account = await flow.complete("google")
        assert account.user.registered_at == NOW
        assert account.user.email == "user@example.com"
        # Every database call of the completion ran on the one session the shared procedures
        # opened, and it is the transaction the locked rows were read in.
        assert len(set(map(id, flow.identities.sessions))) == 1
        session = flow.identities.sessions[0]
        assert assert_upgrade_transaction(session, session) is session
        with pytest.raises(UpgradeError):
            assert_upgrade_transaction(session, object())

    # [utest->req~sessions-upgrade-single-transaction~1]
    async def test_the_transaction_locks_and_revalidates_the_identity_row_first(self):
        flow = Flow(locked=("core.users", "core.external_identities"))
        with pytest.raises(UpgradeError):
            await flow.complete("google")
        assert IDENTITY_LOCK_ORDER == ("core.external_identities", "core.users")
        assert flow.identities.flips == []

    # [utest->req~sessions-upgrade-single-transaction~1]
    async def test_a_classifier_rejection_mid_completion_leaves_no_half_upgraded_account(self):
        flow = Flow(lookup=FakeLookup(ANONYMOUS))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert flow.identities.flips == []
        assert flow.identities.identity.provider is IdentityProvider.anonymous
        assert flow.identities.identity.provider_uid is None
        assert flow.identities.user.registered_at is None
        assert flow.identities.user.email is None


# --- The branch matrix -------------------------------------------------------------------------


class TestBranchSelection:
    # [utest->req~sessions-upgrade-branch-selection~1]
    def test_exactly_one_branch_is_selected_and_only_after_this_call_s_live_read(self):
        assert upgrade_branch(identity_row(), lookups=1) is UpgradeBranch.mutable
        assert upgrade_branch(identity_row(IdentityProvider.google, GOOGLE_UID),
                              lookups=1) is UpgradeBranch.idempotent
        for lookups in (0, 2):
            with pytest.raises(UpgradeError):
                upgrade_branch(identity_row(), lookups=lookups)

    # [utest->req~sessions-upgrade-branch-selection~1]
    async def test_a_stored_provider_equal_to_the_declaration_never_skips_the_read(self):
        flow = registered_flow()
        await flow.complete("google")
        assert flow.lookup.calls == 1

    # [utest->req~sessions-upgrade-branch-anonymous-flip~1]
    async def test_a_stored_anonymous_row_with_the_provider_confirmed_flips_in_place(self):
        flow = Flow()
        account = await flow.complete("google")
        assert account.branch is UpgradeBranch.mutable
        assert (account.identity.provider, account.identity.provider_uid) == (
            IdentityProvider.google, GOOGLE_UID)
        assert flow.identities.identity.provider is IdentityProvider.google

    # [utest->req~sessions-upgrade-branch-idempotent-success~1]
    async def test_a_matching_stored_binding_succeeds_without_mutation(self):
        flow = registered_flow()
        account = await flow.complete("google")
        assert account.branch is UpgradeBranch.idempotent
        assert flow.identities.flips == []
        assert flow.audited() == [AuthEventResult.succeeded]
        assert flow.identities.preserved == PRESERVED

    # [utest->req~sessions-upgrade-branch-idempotent-success~1]
    async def test_a_row_created_registered_and_never_anonymous_also_succeeds(self):
        # No history of an anonymous stage, and no stranded state to repair: still success.
        flow = registered_flow(provider=IdentityProvider.apple, provider_uid=APPLE_UID,
                               lookup=FakeLookup(APPLE))
        account = await flow.complete("apple", variant=IdentityProvider.apple)
        assert account.branch is UpgradeBranch.idempotent
        assert account.purpose is UpgradePurpose.link_completion
        assert flow.identities.flips == []

    # [utest->req~sessions-upgrade-branch-transition-conflict~1]
    async def test_a_stored_provider_other_than_the_confirmed_one_is_a_transition_conflict(self):
        flow = registered_flow(provider=IdentityProvider.apple, provider_uid=APPLE_UID,
                               lookup=FakeLookup(GOOGLE))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_transition_not_allowed
        assert raised.value.error_code == ClientErrorClass.operation_not_allowed
        assert raised.value.result is not AuthEventResult.provider_not_linked
        assert (flow.identities.identity.provider,
                flow.identities.identity.provider_uid) == (IdentityProvider.apple, APPLE_UID)

    # [utest->req~sessions-upgrade-branch-transition-conflict~1]
    async def test_a_diverging_live_uid_conflicts_and_never_converges_on_retry(self):
        diverged = FakeLookup(AdminLookupResult(
            provider_data=entries("google.com", "another-google-uid")))
        for _attempt in range(2):
            flow = registered_flow(provider_uid="stored-google-uid", lookup=diverged)
            with pytest.raises(UpgradeRejection) as raised:
                await flow.complete("google")
            assert raised.value.result is AuthEventResult.provider_transition_not_allowed
            # The stored binding is left exactly as it was on every repeat.
            assert flow.identities.identity.provider_uid == "stored-google-uid"
            assert flow.identities.flips == []
        assert TRANSITION_REJECTION_MUTATIONS == frozenset()
        assert TRANSITION_REJECTION_REMEDY == "manual_operator_repair"

    # [utest->req~sessions-upgrade-provider-account-already-linked~1]
    async def test_a_provider_account_bound_elsewhere_refuses_and_mutates_nothing(self):
        flow = Flow(conflict=True)
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_account_already_linked
        assert raised.value.error_code == ClientErrorClass.operation_not_allowed
        assert flow.identities.identity.provider is IdentityProvider.anonymous
        assert flow.identities.identity.provider_uid is None
        assert flow.identities.user.registered_at is None
        assert flow.identities.preserved == PRESERVED


# --- What the upgrade preserves ----------------------------------------------------------------


class TestPreservedState:
    # [utest->req~sessions-upgrade-preserves-account-state~1]
    async def test_chats_credits_and_grants_stay_on_the_same_rows_and_no_grant_is_minted(self):
        flow = Flow()
        account = await flow.complete("google")
        assert flow.identities.preserved == PRESERVED
        assert account.identity.user_id == flow.identity.user_id
        assert UPGRADE_GRANT_WRITES == frozenset()
        assert UPGRADE_DEVICE_GRANT_BITS == frozenset()
        assert UPGRADE_RETIRED_IDENTITY_ROWS == frozenset()

    # [utest->req~sessions-upgrade-preserves-account-state~1]
    # [utest->req~sessions-repair-updates-metadata-only~1]
    def test_no_completion_writes_a_grant_touches_device_bits_or_counts_as_a_claim(self):
        assert assert_identity_metadata_only() is None
        with pytest.raises(Exception):
            assert_identity_metadata_only(grants=["registered_account_grant"])
        with pytest.raises(UpgradeError):
            assert_identity_metadata_only(device_bits=["devicecheck_bit"])
        with pytest.raises(UpgradeError):
            assert_identity_metadata_only(registered_grant_claimed=True)

    # [utest->req~sessions-upgrade-no-reverse-transition~1]
    def test_no_path_flips_a_registered_row_back_to_anonymous(self):
        registered = identity_row(IdentityProvider.google, GOOGLE_UID)
        with pytest.raises(UpgradeError):
            assert_in_place(registered, replace(registered, provider=IdentityProvider.anonymous,
                                                provider_uid=None))
        # Registered-to-registered rebinding is refused the same way.
        with pytest.raises(UpgradeError):
            assert_in_place(registered, replace(registered, provider=IdentityProvider.apple,
                                                provider_uid=APPLE_UID))
        # And the mutable flip is the only assignment transition for `provider_uid`.
        decision = UpgradeDecision(UpgradeBranch.mutable, IdentityProvider.google, GOOGLE_UID)
        with pytest.raises(UpgradeError):
            linking_flip(registered, decision, context=upgrade_context(registered),
                         transaction=object())


# --- The gateway limit on the route ------------------------------------------------------------


class TestGatewayLimit:
    # [utest->req~sessions-upgrade-gateway-rate-limit~1]
    def test_the_shipped_gateway_entry_is_the_standalone_per_linked_subject_limit(self):
        raw = yaml.safe_load(CONFIG_PATH.read_text())["gateway_rate_limits"]
        entry = GatewayRateLimitsConfig(**raw).upgrade_anonymous
        assert_upgrade_gateway_limit(entry)
        assert entry.limit == UPGRADE_GATEWAY_DEFAULT_LIMIT == "3/hour"
        assert entry.key == "issuer+subject_hash"
        assert entry.route == "POST /auth/upgrade-anonymous"

    # [utest->req~sessions-upgrade-gateway-rate-limit~1]
    def test_a_missing_route_key_or_position_is_refused_but_the_ceiling_is_tunable(self):
        raw = yaml.safe_load(CONFIG_PATH.read_text())["gateway_rate_limits"]
        entry = GatewayRateLimitsConfig(**raw).upgrade_anonymous
        for override in ({"route": "POST /auth/create-user"},
                         {"key": "ip"},
                         {"evaluate_after": "gateway_route_match"}):
            # Another route, another key, or an earlier evaluation position is not this limit.
            with pytest.raises(Exception):
                assert_upgrade_gateway_limit(entry.model_copy(update=override))
        # 3/hour is the shipped default, not a mandate: a retuned ceiling validates, and nothing
        # in code substitutes the shipped value. An operator raising it raises this route's real
        # request-rate bound, because no backend request-rate counter sits behind it.
        for tuned in ("1/hour", "10/hour", "300/hour", "3/hour; 20/day"):
            assert_upgrade_gateway_limit(entry.model_copy(update={"limit": tuned}))

    # [utest->req~sessions-upgrade-limit-before-admin-call~1]
    def test_the_limit_is_applied_before_the_firebase_admin_call(self):
        ledger = AdmissionLedger("POST", "/auth/upgrade-anonymous")
        upgrade_gateway_admission(ledger, jwt_filter_verified=True)
        assert ledger.refused is False
        # An exceeded limit refuses the request; nothing beyond it is reached.
        refused = AdmissionLedger("POST", "/auth/upgrade-anonymous")
        upgrade_gateway_admission(refused, jwt_filter_verified=True, allowed=False)
        assert refused.refused is True
        assert ExpensiveStep.firebase_lookup not in refused.expensive_steps

    # [utest->req~sessions-upgrade-limit-before-admin-call~1]
    def test_the_limit_never_runs_after_the_lookup_or_before_jwt_verification(self):
        late = AdmissionLedger("POST", "/auth/upgrade-anonymous")
        late.expensive_step(ExpensiveStep.firebase_lookup)
        with pytest.raises(Exception):
            upgrade_gateway_admission(late, jwt_filter_verified=True)
        with pytest.raises(Exception):
            upgrade_gateway_admission(AdmissionLedger("POST", "/auth/upgrade-anonymous"),
                                      jwt_filter_verified=False)


# --- credential-already-in-use, and the account left behind ------------------------------------


class TestCredentialAlreadyInUse:
    # [utest->req~sessions-upgrade-credential-already-in-use~1]
    async def test_a_call_after_a_failed_link_is_rejected_without_touching_the_source_account(self):
        # The anonymous subject's `providerData` carries no registered provider, because the
        # client-side `linkWithCredential` never happened.
        flow = Flow(lookup=FakeLookup(ANONYMOUS))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert raised.value.cause is ProviderNotLinkedCause.empty_provider_data
        assert flow.identities.identity.provider is IdentityProvider.anonymous
        assert flow.identities.user.registered_at is None
        assert flow.identities.preserved == PRESERVED
        # No merge: the endpoint is not involved in that failure at all.
        assert credential_already_in_use_route(ResolutionOutcome.linked) is None

    # [utest->req~sessions-upgrade-fallback-sign-in-resolution~1]
    def test_the_provider_sign_in_flows_through_ordinary_resolution(self):
        assert credential_already_in_use_route(ResolutionOutcome.linked) is None
        assert credential_already_in_use_route(ResolutionOutcome.pre_auth) == (
            "POST", "/auth/create-user")
        for outcome, result in ((ResolutionOutcome.historical_identity,
                                 AuthEventResult.historical_identity),
                                (ResolutionOutcome.blocked_user, AuthEventResult.blocked_user)):
            with pytest.raises(UpgradeRejection) as raised:
                credential_already_in_use_route(outcome)
            assert raised.value.result is result

    # [utest->req~sessions-abandoned-anonymous-account-untouched~1]
    def test_the_abandoned_anonymous_account_keeps_everything_and_stays_active(self):
        row = identity_row()
        user = UpgradeUser(id=row.user_id)
        assert abandoned_anonymous_account(row, user, grants=("anonymous_device_grant",)) == (row,
                                                                                              user)
        assert ABANDONED_ACCOUNT_MUTATIONS == frozenset()
        assert ABANDONED_ACCOUNT_MECHANISMS == frozenset()
        assert NON_TRANSFER_COPY_IS_DISPLAY_ONLY is True
        # Retired, blocked, or no longer the anonymous account: none of those is this account.
        with pytest.raises(UpgradeError):
            abandoned_anonymous_account(replace(row, identity_state=IdentityState.historical), user)
        with pytest.raises(UpgradeError):
            abandoned_anonymous_account(row, replace(user, active=False))
        with pytest.raises(UpgradeError):
            abandoned_anonymous_account(identity_row(IdentityProvider.google, GOOGLE_UID), user)


# --- Interrupted upgrade repair -----------------------------------------------------------------


class TestInterruptedUpgradeRepair:
    # [utest->req~sessions-upgrade-repair-path~1]
    async def test_the_same_endpoint_repairs_an_upgrade_whose_backend_call_never_landed(self):
        flow = Flow()
        stranded = stranded_upgrade(flow.identity, flow.user,
                                    live_provider=IdentityProvider.google)
        assert stranded is not None and upgrade_purpose(stranded) is UpgradePurpose.stranded_repair
        account = await flow.complete("google")
        assert account.purpose is UpgradePurpose.stranded_repair
        # The idempotence that carries the repair is not optimized away.
        assert REPAIR_ROLE_OPTIMIZATIONS == frozenset()
        repeat = registered_flow()
        assert (await repeat.complete("google")).branch is UpgradeBranch.idempotent

    # [utest->req~sessions-stranded-account-state~1]
    def test_a_live_registered_provider_over_a_stored_anonymous_row_is_a_valid_state(self):
        row = identity_row()
        user = UpgradeUser(id=row.user_id)
        stranded = stranded_upgrade(row, user, live_provider=IdentityProvider.google)
        assert stranded is not None
        assert stranded.identity.identity_state is IdentityState.active
        assert stranded.user.active is True
        assert stranded.identity.provider is IdentityProvider.anonymous
        assert stranded.user.registered_at is None
        # Not stranded once the backend recorded the transition.
        assert stranded_upgrade(row, replace(user, registered_at=NOW),
                                live_provider=IdentityProvider.google) is None
        # Stranding itself marks nothing historical and signs nobody out.
        assert STRANDING_SIDE_EFFECTS == frozenset()
        with pytest.raises(UpgradeError):
            stranded_upgrade(replace(row, identity_state=IdentityState.historical), user,
                             live_provider=IdentityProvider.google)

    # [utest->req~sessions-stranded-account-no-registered-grant~1]
    def test_a_stranded_account_gets_no_registered_grant_and_can_still_sign_out_everywhere(self):
        row = identity_row()
        stranded = stranded_upgrade(row, UpgradeUser(id=row.user_id),
                                    live_provider=IdentityProvider.google)
        assert stranded is not None
        exposure = stranded_exposure(stranded)
        assert exposure.registered_grant_available is False
        assert exposure.sign_out_all_effective is True
        assert exposure.residual_exposure == STRANDING_RESIDUAL_EXPOSURE
        assert STRANDED_ACCOUNT_GRANTS == frozenset()
        # A row that already stores a registered provider is not stranded at all.
        registered = identity_row(IdentityProvider.google, GOOGLE_UID)
        with pytest.raises(UpgradeError):
            stranded_exposure(replace(stranded, identity=registered))

    # [utest->req~sessions-client-driven-repair-loop~1]
    def test_the_client_repairs_whenever_firebase_is_ahead_of_the_backend(self):
        for provider in (IdentityProvider.google, IdentityProvider.apple):
            assert repair_needed(backend_provider=IdentityProvider.anonymous,
                                 firebase_provider=provider) is True
        assert repair_needed(backend_provider=IdentityProvider.google,
                             firebase_provider=IdentityProvider.google) is False
        assert repair_needed(backend_provider=IdentityProvider.anonymous,
                             firebase_provider=IdentityProvider.anonymous) is False
        assert REPAIR_READ_SURFACES == (("POST", "/auth/sync"), ("GET", "/users/me"))

    # [utest->req~sessions-client-driven-repair-loop~1]
    def test_a_conflict_is_terminal_while_other_failures_retry_or_re_prepare(self):
        assert repair_disposition(ClientErrorClass.operation_not_allowed) is RepairRetry.terminal
        assert repair_disposition(
            ClientErrorClass.challenge_required) is RepairRetry.fresh_challenge
        assert repair_disposition(
            ClientErrorClass.verification_temporarily_unavailable) is RepairRetry.retry

    # [utest->req~sessions-repair-providerdata-source-of-truth~1]
    async def test_the_flip_content_comes_from_providerdata_and_reuses_the_challenge_model(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        account = await flow.complete("google")
        # The stored binding is exactly what the live read reported, not what the client declared.
        assert account.identity.provider_uid == GOOGLE_UID
        assert is_challenge_bearing(UPGRADE) is True
        assert REPAIR_MECHANISMS == frozenset()
        with pytest.raises(UpgradeError):
            assert_confirmation_source("client_declaration")


# --- The recorded identity transition -----------------------------------------------------------


class TestIdentityTransition:
    # [utest->req~sessions-upgrade-transition-effects~1]
    async def test_a_successful_upgrade_has_exactly_the_defined_effects(self):
        flow = Flow()
        before = flow.identity
        account = await flow.complete("google")
        after = account.identity
        assert (after.id, after.user_id) == (before.id, before.user_id)
        assert after.provider is IdentityProvider.google and after.provider_uid == GOOGLE_UID
        assert after.identity_state is IdentityState.active
        assert account.user.registered_at == NOW
        assert flow.identities.preserved == PRESERVED
        assert flow.audited() == [AuthEventResult.succeeded]

    # [utest->req~sessions-transition-in-place-provider-flip~1]
    async def test_the_flip_is_in_place_and_assigns_provider_uid_in_the_same_transaction(self):
        flow = Flow()
        account = await flow.complete("google")
        flipped, _user = flow.identities.flips[0]
        assert flipped.provider is IdentityProvider.google
        assert flipped.provider_uid == GOOGLE_UID
        assert flipped.id == flow.identity.id
        # One transaction carried the row and its uid together.
        assert len(set(map(id, flow.identities.sessions))) == 1
        assert account.identity.provider_uid == GOOGLE_UID

    # [utest->req~sessions-transition-idempotent-no-mutation~1]
    async def test_a_confirmed_matching_binding_succeeds_and_mutates_nothing(self):
        flow = registered_flow()
        account = await flow.complete("google")
        assert account.branch is UpgradeBranch.idempotent
        assert account.identity is flow.identity
        assert account.user.registered_at == LATER
        assert flow.identities.flips == []

    # [utest->req~sessions-transition-users-row-remains-owner~1]
    async def test_the_existing_users_row_remains_the_owner(self):
        flow = Flow()
        account = await flow.complete("google")
        assert account.user.id == flow.identity.user_id
        assert account.identity.user_id == flow.identity.user_id
        # Attribution never moves to another user row.
        with pytest.raises(UpgradeError):
            assert_state_preserved(PRESERVED, PRESERVED, user_id=account.user.id,
                                   attribution_owners=(uuid7(),))

    # [utest->req~sessions-transition-no-retirement-or-new-row~1]
    async def test_no_identity_is_retired_and_no_new_row_is_created(self):
        flow = Flow()
        account = await flow.complete("google")
        assert account.identity.identity_state is IdentityState.active
        assert UPGRADE_CREATED_IDENTITY_ROWS == frozenset()
        assert UPGRADE_RETIRED_IDENTITY_ROWS == frozenset()
        row = identity_row()
        with pytest.raises(UpgradeError):
            assert_in_place(row, replace(row, identity_state=IdentityState.historical))
        with pytest.raises(UpgradeError):
            assert_in_place(row, replace(row, id=uuid7()))

    # [utest->req~sessions-divergent-binding-not-a-transition~1]
    def test_a_divergent_stored_binding_is_refused_rather_than_recorded(self):
        for divergence in (TransitionDivergence.stored_provider_differs,
                           TransitionDivergence.live_provider_uid_differs):
            rejection = transition_rejection(divergence)
            assert rejection.result is AuthEventResult.provider_transition_not_allowed
            assert rejection.error_code == ClientErrorClass.operation_not_allowed
            assert rejection.divergence is divergence
        assert TRANSITION_REJECTION_MUTATIONS == frozenset()

    # [utest->req~sessions-no-secondary-auth-state-revocation~1]
    async def test_a_transition_issues_no_token_and_advances_no_auth_state(self):
        flow = Flow()
        account = await flow.complete("google")
        assert account.backend_token is None
        assert assert_no_secondary_auth_state() is None
        with pytest.raises(Exception):
            assert_no_secondary_auth_state({"session_generation": 2})
        with pytest.raises(Exception):
            assert_no_secondary_auth_state(generation=1)
