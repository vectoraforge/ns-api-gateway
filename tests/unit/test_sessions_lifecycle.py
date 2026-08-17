"""Identity lifecycle from the sessions side: what the stored classification is and is not, where
live `providerData` may still be read, the device check that gates only free credit, the
administrative block and retirement that revoke refresh tokens, erasure's tombstone, and an
upstream Firebase deletion the backend deliberately does not chase."""

import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, barrier_result_for
from nativespeaker.api.auth.derived_identifiers import confirm_registered_binding
from nativespeaker.api.auth.external_identities import (
    BLOCK_EVASION_CONTROLS,
    BLOCK_NEVER_COVERS,
    BLOCK_SCOPE,
    DELETE_PERMITTED_ROLES,
    ERASED_PROFILE_COLUMNS,
    ERASURE_RETAINED_ROWS,
    FIREBASE_DELETION_SYNC_MECHANISMS,
    HOT_PATH_RECONCILIATION,
    IDENTITY_ROW_DELETERS,
    IDENTITY_STATE_CHANGING_FLOWS,
    IDENTITY_STATE_TRANSITIONS,
    PER_REQUEST_FIREBASE_CHECKS,
    PROVIDER_CONSUMERS,
    PROVIDER_READ_ONLY_READ_POINTS,
    REVOCATION_FAILURE_MACHINERY,
    REVOCATION_MECHANISM,
    SCRUB_EXEMPT_COLUMNS,
    STALE_ID_TOKEN_WINDOW,
    STORED_PROVIDER_MIRRORS,
    TOMBSTONE_REMOVERS,
    AdministrativeAction,
    BindingDivergenceError,
    ExternalIdentityRow,
    IdentityError,
    IdentityState,
    ProviderConsumer,
    UpstreamDeletionRemedy,
    administrative_revocation,
    administrative_revocation_result,
    administrative_write,
    assert_live_provider_data_scope,
    assert_no_firebase_deletion_sync,
    assert_no_identity_delete,
    assert_no_per_request_firebase_check,
    assert_stored_provider_not_a_mirror,
    assert_upstream_deletion_remedy,
    authoritative_provider,
    block_covers,
    block_user,
    deletion_sync_transition,
    erase_account,
    erasure_disclosure,
    may_delete_identity_rows,
    registered_grant_class_inputs,
    resolves_through_stale_row,
    retire,
    revokes_refresh_tokens,
    transition_identity_state,
)
from nativespeaker.api.auth.invariants import (
    InvariantError,
    ProofUse,
    assert_device_check_proof_use,
)
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_endpoints import (
    CREATE_USER_VOLUME_CONTROLS,
    DEVICE_CHECK_FREE_ROUTES,
    DEVICE_CHECK_GATES,
    DEVICE_CHECK_NEVER_GATES,
    REJECTED_CREATE_USER_CONTROLS,
    ProofApplicabilityError,
    create_user_takes_no_device_check,
    takes_no_device_check,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass, ProviderDataReadPoint, surface
from unit.conftest import TEST_ISSUER

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
GOOGLE_UID = "google-account-id"


def row(provider: IdentityProvider = IdentityProvider.anonymous,
        provider_uid: str | None = None,
        state: IdentityState = IdentityState.active,
        free_grant_consumed_at: datetime | None = None) -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=TEST_ISSUER,
                               subject="lifecycle-subject", provider=provider,
                               provider_uid=provider_uid, identity_state=state,
                               free_grant_consumed_at=free_grant_consumed_at)


REGISTERED = row(IdentityProvider.google, GOOGLE_UID)


# --- ProviderData divergence --------------------------------------------------------------------


class TestStoredProviderIsNotAMirror:
    # [utest->req~sessions-stored-provider-not-a-mirror~1]
    def test_a_firebase_unlink_may_diverge_from_the_stored_value_indefinitely(self):
        # Live `providerData` now reports no registered link at all; the stored row is untouched.
        unchanged = assert_stored_provider_not_a_mirror(
            live_provider=IdentityProvider.anonymous, row=REGISTERED)
        assert unchanged is REGISTERED
        assert unchanged.provider is IdentityProvider.google
        assert unchanged.provider_uid == GOOGLE_UID
        assert STORED_PROVIDER_MIRRORS == frozenset()
        assert HOT_PATH_RECONCILIATION == frozenset()

    # [utest->req~sessions-consumers-read-stored-classification~1]
    def test_every_per_request_consumer_reads_the_stored_classification(self):
        for consumer in (ProviderConsumer.registered_grant_gating,
                         ProviderConsumer.claim_path,
                         ProviderConsumer.authorization_branch,
                         ProviderConsumer.audit_branch,
                         ProviderConsumer.entitlement_handling):
            assert authoritative_provider(REGISTERED, consumer) is IdentityProvider.google

    # [utest->req~sessions-consumers-read-stored-classification~1]
    def test_sign_out_all_revocation_is_not_one_of_them(self):
        assert ProviderConsumer.refresh_token_revocation not in PROVIDER_CONSUMERS
        with pytest.raises(IdentityError):
            authoritative_provider(REGISTERED, ProviderConsumer.refresh_token_revocation)
        # Revocation is unconditional for every account whatever the stored provider.
        for stored in (row(), REGISTERED, row(IdentityProvider.apple, "apple-user-id")):
            assert revokes_refresh_tokens(stored) is True

    # [utest->req~sessions-registered-grant-keys-on-stored-state~1]
    def test_registered_grant_eligibility_keys_on_stored_state_not_live_firebase(self):
        # The account registered and has not used its one registered grant: eligible. Eligibility
        # takes no live input at all, so a Firebase-side unlink cannot reach it.
        assert registered_grant_class_inputs(REGISTERED, registered_at=NOW,
                                             grant_history_exhausted=False) is True
        assert "live" not in inspect.signature(registered_grant_class_inputs).parameters
        # The account's own grant history is what closes it, and at most one is ever claimable.
        assert registered_grant_class_inputs(REGISTERED, registered_at=NOW,
                                             grant_history_exhausted=True) is False
        # An anonymous stored classification is not in the registered grant class.
        assert registered_grant_class_inputs(row(), registered_at=None,
                                            grant_history_exhausted=False) is False
        # No downgrade happened: the stored row is exactly as it was.
        assert REGISTERED.provider is IdentityProvider.google

    # [utest->req~sessions-registered-grant-keys-on-stored-state~1]
    def test_the_claims_mandatory_confirmation_denies_only_the_grant_on_divergence(self):
        """`claim_registered_grant` confirms the stored binding against live `providerData` on
        every call. A result diverging on the provider or on the `provider_uid` is a conflict that
        denies this free grant; the stored classification is left exactly as it was."""
        confirming = [{"provider_id": "google.com", "uid": GOOGLE_UID}]
        assert confirm_registered_binding(REGISTERED, confirming) is IdentityProvider.google

        diverging = ([{"provider_id": "google.com", "uid": "some-other-google-account"}],
                     [{"provider_id": "apple.com", "uid": GOOGLE_UID}],
                     [])  # unlinked entirely: no live entry confirms the stored binding
        for provider_data in diverging:
            with pytest.raises(BindingDivergenceError) as conflict:
                confirm_registered_binding(REGISTERED, provider_data)
            assert conflict.value.result is AuthEventResult.provider_transition_not_allowed
            # The row is untouched: the denial is of the grant, never a rewrite or a downgrade.
            assert (REGISTERED.provider, REGISTERED.provider_uid) == (IdentityProvider.google,
                                                                      GOOGLE_UID)
            # And eligibility, which reads stored state only, is unchanged by the divergence.
            assert registered_grant_class_inputs(REGISTERED, registered_at=NOW,
                                                 grant_history_exhausted=False) is True

    # [utest->req~sessions-live-providerdata-only-at-grant-gates~1]
    def test_only_the_two_free_grant_gates_read_live_provider_data(self):
        for point in (ProviderDataReadPoint.web_anonymous_grant_gate,
                      ProviderDataReadPoint.claim_registered_grant_completion):
            assert assert_live_provider_data_scope(point) is point
        assert PROVIDER_READ_ONLY_READ_POINTS == {
            ProviderDataReadPoint.web_anonymous_grant_gate,
            ProviderDataReadPoint.claim_registered_grant_completion}
        for point in (ProviderDataReadPoint.upgrade_anonymous_completion,
                      ProviderDataReadPoint.anonymous_create_user_completion,
                      ProviderDataReadPoint.registered_create_user_completion):
            with pytest.raises(IdentityError):
                assert_live_provider_data_scope(point)


# --- The device check gates free credit and nothing else ----------------------------------------


class TestDeviceCheckGating:
    # [utest->req~sessions-device-check-token-not-identity~1]
    def test_a_device_check_token_is_never_identity_ownership_recovery_or_upgrade(self):
        assert assert_device_check_proof_use(ProofUse.anti_abuse_gate) is None
        for use in (ProofUse.identity, ProofUse.ownership, ProofUse.recovery, ProofUse.upgrade,
                    ProofUse.account_resolution):
            with pytest.raises(InvariantError):
                assert_device_check_proof_use(use)

    # [utest->req~sessions-read-only-endpoints-no-device-check~1]
    def test_sync_users_me_the_flip_and_restore_verify_no_device_check(self):
        for operation in (AuthOperation.sync, AuthOperation.upgrade_anonymous_to_registered,
                          AuthOperation.restore_subscription):
            assert takes_no_device_check(operation) == frozenset()
            with pytest.raises(ProofApplicabilityError):
                takes_no_device_check(operation, device_state_touched=["devicecheck_bit"])
        assert DEVICE_CHECK_FREE_ROUTES == (("POST", "/auth/sync"), ("GET", "/users/me"))
        # A free-grant claim is not on that list: it is the endpoint the device check gates.
        with pytest.raises(ProofApplicabilityError):
            takes_no_device_check(AuthOperation.claim_anonymous_grant)

    # [utest->req~sessions-create-user-no-device-check~1]
    def test_create_user_needs_no_device_check_in_either_phase_or_form(self):
        for phase in RequestMode:
            for variant in IdentityProvider:
                assert create_user_takes_no_device_check(phase=phase,
                                                        variant=variant) == frozenset()
        # The device check gates the value of a free grant, never creation volume; the gateway
        # limits on the route are what contain that.
        assert DEVICE_CHECK_GATES == frozenset({"free_credit_grant_eligibility"})
        assert DEVICE_CHECK_NEVER_GATES == frozenset({"account_creation_volume"})
        assert CREATE_USER_VOLUME_CONTROLS == ("create_user_ip", "create_user_deployment")
        assert not REJECTED_CREATE_USER_CONTROLS & set(CREATE_USER_VOLUME_CONTROLS)
        with pytest.raises(ProofApplicabilityError):
            create_user_takes_no_device_check(phase=RequestMode.completion,
                                              variant=IdentityProvider.anonymous,
                                              body={"devicecheck_token": "AAA"})


# --- Lifecycle enforcement at per-request resolution --------------------------------------------


class TestLifecycleAtResolution:
    # [utest->req~sessions-lifecycle-enforced-at-resolution~1]
    # [utest->req~sessions-historical-and-blocked-rejected-at-resolution~1]
    def test_a_historical_identity_and_a_blocked_user_are_rejected_at_resolution(self):
        for route in (("POST", "/auth/sync"), ("POST", "/auth/create-user"),
                      ("GET", "/users/me"), ("POST", "/auth/sign-out-all")):
            method, path = route
            assert barrier_result_for(ResolutionOutcome.historical_identity, method,
                                      path) is AuthEventResult.historical_identity
            assert barrier_result_for(ResolutionOutcome.blocked_user, method,
                                      path) is AuthEventResult.blocked_user
        # A linked identity whose user is active is the one admitted outcome.
        assert barrier_result_for(ResolutionOutcome.linked, "POST", "/auth/sync") is None

    # [utest->req~sessions-block-immediate-for-backend~1]
    def test_a_block_denies_the_next_request_and_leaves_the_identity_row_active(self):
        blocked = row()
        write, state = block_user(blocked)
        assert write == "core.users.active = FALSE"
        assert state is IdentityState.active
        # The rejection comes from resolution, not from the token: both surface the same class.
        assert barrier_result_for(ResolutionOutcome.blocked_user, "POST",
                                  "/chats") is AuthEventResult.blocked_user
        assert surface(AuthEventResult.blocked_user)[0] == ClientErrorClass.account_unavailable
        with pytest.raises(IdentityError):
            block_user(blocked, active=True)
        # Blocking never marks the identity `historical`.
        with pytest.raises(IdentityError):
            block_user(row(state=IdentityState.historical))

    # [utest->req~sessions-block-scope-one-account~1]
    def test_a_block_covers_one_user_row_and_one_identity_and_no_person_or_device(self):
        for target in BLOCK_SCOPE:
            assert block_covers(target) is True
        for target in ("person", "device", "fresh_anonymous_sign_in",
                       "another_registered_account"):
            assert block_covers(target) is False
        assert BLOCK_NEVER_COVERS >= {"person", "device"}
        assert "active_flag" not in BLOCK_EVASION_CONTROLS
        assert BLOCK_EVASION_CONTROLS == ("create_user_gateway_limits",
                                          "device_gated_free_credit_grants")

    # [utest->req~sessions-historical-administrative-only~1]
    def test_historical_is_administrative_only_and_still_rejected_everywhere(self):
        retired = retire(row())
        assert retired.identity_state is IdentityState.historical
        assert IDENTITY_STATE_CHANGING_FLOWS == frozenset()
        with pytest.raises(IdentityError):
            retire(row(), administrative=False)
        assert barrier_result_for(ResolutionOutcome.historical_identity, "POST",
                                  "/auth/sync") is AuthEventResult.historical_identity

    # [utest->req~sessions-identity-state-transition-set~1]
    def test_the_transition_set_is_active_to_historical_and_nothing_else(self):
        assert IDENTITY_STATE_TRANSITIONS == {(IdentityState.active, IdentityState.historical)}
        assert transition_identity_state(IdentityState.active, IdentityState.historical,
                                        administrative=True) is IdentityState.historical
        # No reversal, and no self-transition.
        with pytest.raises(IdentityError):
            transition_identity_state(IdentityState.historical, IdentityState.active,
                                      administrative=True)
        with pytest.raises(IdentityError):
            transition_identity_state(IdentityState.active, IdentityState.active,
                                      administrative=True)


# --- Blocking and retirement revoke refresh tokens ----------------------------------------------


class TestAdministrativeRevocation:
    # [utest->req~sessions-block-and-retire-revoke-refresh-tokens~1]
    def test_both_actions_revoke_through_the_sign_out_all_mechanism_for_any_provider(self):
        for action in (AdministrativeAction.block_user, AdministrativeAction.retire_identity):
            for stored in (row(), REGISTERED):
                assert administrative_revocation(action, stored) == REVOCATION_MECHANISM
            with pytest.raises(IdentityError):
                administrative_revocation(action, REGISTERED, stored_provider_consulted=True)

    # [utest->req~sessions-block-and-retire-revoke-refresh-tokens~1]
    def test_the_database_change_is_authoritative_and_the_audit_value_is_reused(self):
        outcome = administrative_write(AdministrativeAction.block_user, revocation_failed=True)
        assert outcome.committed is True
        assert outcome.lifecycle_write == "core.users.active = FALSE"
        assert outcome.operator_retry_available is True
        with pytest.raises(IdentityError):
            administrative_write(AdministrativeAction.retire_identity, revocation_failed=True,
                                 rollback_requested=True)
        assert administrative_revocation_result(
            revoked=False) is AuthEventResult.revocation_unconfirmed
        assert administrative_revocation_result(revoked=True) is AuthEventResult.succeeded

    # [utest->req~sessions-revocation-failure-no-compensation~1]
    def test_a_failed_revocation_gets_no_retry_queue_marker_or_compensation(self):
        assert REVOCATION_FAILURE_MACHINERY == frozenset()
        for action in AdministrativeAction:
            outcome = administrative_write(action, revocation_failed=True)
            # The account stays blocked or retired, and the only recourse is an operator's own.
            assert (outcome.committed, outcome.revocation_failed) == (True, True)
            assert outcome.operator_retry_available is True


# --- Rows are never deleted, and erasure keeps the tombstone ------------------------------------


class TestRetentionAndErasure:
    # [utest->req~sessions-identity-rows-never-deleted~1]
    def test_identity_rows_are_append_and_state_only(self):
        assert IDENTITY_ROW_DELETERS == frozenset()
        assert DELETE_PERMITTED_ROLES == frozenset()
        assert may_delete_identity_rows("app") is False
        assert may_delete_identity_rows("cleanup_job") is False
        with pytest.raises(IdentityError):
            assert_no_identity_delete("cleanup_job")
        # Retirement and blocking are transitions on the existing row, keeping both rows.
        original = row()
        retired = retire(original)
        assert (retired.id, retired.user_id) == (original.id, original.user_id)
        assert block_user(original)[1] is IdentityState.active

    # [utest->req~sessions-erasure-retains-tombstone~1]
    def test_erasure_scrubs_pii_and_keeps_the_historical_tombstone(self):
        consumed = row(IdentityProvider.google, GOOGLE_UID, free_grant_consumed_at=NOW)
        tombstone, profile = erase_account(consumed, profile={"email": "user@example.com",
                                                             "display_name": "User"})
        assert tombstone.identity_state is IdentityState.historical
        assert (tombstone.issuer, tombstone.subject) == (consumed.issuer, consumed.subject)
        assert (tombstone.provider, tombstone.provider_uid) == (IdentityProvider.google,
                                                                GOOGLE_UID)
        # The PII lives on `core.users` and is scrubbed there.
        assert profile == {"email": None, "display_name": None}
        assert ERASED_PROFILE_COLUMNS == ("email", "display_name")
        # Free-grant finality survives erasure, for the account and its provider account.
        assert tombstone.free_grant_consumed_at == NOW
        assert "core.provider_accounts" in ERASURE_RETAINED_ROWS
        assert TOMBSTONE_REMOVERS == frozenset()

    # [utest->req~sessions-erasure-retained-identifiers-disclosure~1]
    def test_the_disclosure_names_the_retained_identifiers_and_stays_display_only(self):
        disclosure = erasure_disclosure()
        assert disclosure.retained_identifiers == ("issuer", "subject", "provider", "provider_uid")
        assert disclosure.retained_identifiers == tuple(SCRUB_EXEMPT_COLUMNS)
        assert disclosure.retained_in == ("core.external_identities", "core.provider_accounts")
        assert disclosure.retained_purpose == ("keep_the_account_retired",
                                               "reject_re_registration_of_the_same_provider_account")
        # No raw subject is kept anywhere else: those two tables hold keyed hashes only.
        assert disclosure.no_raw_subject_elsewhere == ("core.auth_challenges",
                                                       "audit.auth_events")
        assert disclosure.display_only is True


# --- Upstream Firebase deletion -----------------------------------------------------------------


class TestUpstreamDeletion:
    # [utest->req~sessions-upstream-deletion-no-backend-action~1]
    def test_the_backend_changes_nothing_and_detects_nothing(self):
        stale = row()
        assert deletion_sync_transition(stale) is None
        assert stale.identity_state is IdentityState.active
        assert FIREBASE_DELETION_SYNC_MECHANISMS == frozenset()
        for mechanism in ("webhook", "background_job", "polling", "automatic_historical_flip"):
            with pytest.raises(IdentityError):
                assert_no_firebase_deletion_sync(mechanism)

    # [utest->req~sessions-upstream-deletion-token-window-risk~1]
    def test_an_already_minted_token_resolves_until_its_own_exp(self):
        stale = row()
        exp = NOW + timedelta(minutes=30)
        assert resolves_through_stale_row(stale, token_exp=exp, now=NOW) is True
        assert resolves_through_stale_row(stale, token_exp=NOW - timedelta(seconds=1),
                                          now=NOW) is False
        assert STALE_ID_TOKEN_WINDOW == timedelta(hours=1)
        # A retired row stops resolving even inside that window.
        assert resolves_through_stale_row(row(state=IdentityState.historical), token_exp=exp,
                                          now=NOW) is False

    # [utest->req~sessions-upstream-deletion-manual-remedy~1]
    def test_the_remedy_is_a_manual_block_or_retirement(self):
        assert assert_upstream_deletion_remedy(
            "administrative_block") is UpstreamDeletionRemedy.administrative_block
        assert assert_upstream_deletion_remedy(
            UpstreamDeletionRemedy.administrative_retirement
        ) is UpstreamDeletionRemedy.administrative_retirement
        for remedy in ("automatic_retirement", "scheduled_cleanup", "webhook_sync"):
            with pytest.raises(IdentityError):
                assert_upstream_deletion_remedy(remedy)

    # [utest->req~sessions-no-per-request-firebase-existence-check~1]
    def test_no_firebase_existence_check_is_added_to_the_per_request_path(self):
        assert assert_no_per_request_firebase_check() is None
        assert PER_REQUEST_FIREBASE_CHECKS == frozenset()
        for check in ("get_user_existence_probe", "account_status_poll", "disabled_flag_read"):
            with pytest.raises(IdentityError):
                assert_no_per_request_firebase_check(check)


def test_a_retired_row_keeps_its_uniqueness_reservation():
    """The tombstone is what keeps the retired pair out of a fresh pre-auth creation."""
    # [utest->req~sessions-erasure-retains-tombstone~1]
    consumed = row(IdentityProvider.google, GOOGLE_UID, free_grant_consumed_at=NOW)
    tombstone, _profile = erase_account(consumed)
    assert (tombstone.issuer, tombstone.subject) == (consumed.issuer, consumed.subject)
    assert tombstone.id == consumed.id
    # And erasure is idempotent on an already-retired row.
    again, _ = erase_account(replace(tombstone))
    assert again.identity_state is IdentityState.historical
