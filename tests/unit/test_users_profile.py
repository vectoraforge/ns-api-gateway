"""The `core.users` semantics: classification, profile fields, and row lifecycle."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.profile import (
    ORPHAN_USER_SWEEPS,
    PROFILE_FIELDS,
    USER_RETENTION_DAYS,
    AccountClass,
    AdminUserRecord,
    EmailUse,
    OrphanUserError,
    ProfileError,
    ProfileWriter,
    account_class,
    assert_email_control_verified,
    assert_email_use,
    assert_hard_delete_allowed,
    assert_identity_match_fields,
    assert_no_implicit_reactivation,
    assert_registered_at_pairing,
    assert_user_created_with_identity,
    display_name_for_client,
    email_on_upgrade,
    initial_email_on_create,
    is_blocked,
    is_registered,
    profile_changes,
    read_orphan_user,
    retention_deadline,
    sync_mutations,
    user_mutation,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
VERIFIED = AdminUserRecord(email="user@example.com", email_verified=True)


# --- Classification -----------------------------------------------------------------------------

# [utest->req~schema-users-registered-at-null-unregistered~1]
def test_a_null_registered_at_means_registration_was_not_completed():
    assert is_registered(None) is False


# [utest->req~schema-users-registered-at-set-registered~1]
def test_a_set_registered_at_means_the_user_is_registered():
    assert is_registered(NOW) is True


# [utest->req~schema-users-registered-at-not-classifier~1]
def test_the_stored_provider_classifies_the_account_and_registered_at_never_competes():
    # A corrupt row whose timestamp says "registered" is still an anonymous account: the
    # timestamp is reporting data, and it never produces a competing classification.
    assert account_class(IdentityProvider.anonymous) is AccountClass.anonymous
    assert account_class(IdentityProvider.google) is AccountClass.registered
    assert account_class(IdentityProvider.apple) is AccountClass.registered
    with pytest.raises(ProfileError):
        assert_registered_at_pairing(IdentityProvider.anonymous, NOW)
    with pytest.raises(ProfileError):
        assert_registered_at_pairing(IdentityProvider.google, None)
    assert_registered_at_pairing(IdentityProvider.anonymous, None)
    assert_registered_at_pairing(IdentityProvider.google, NOW)


# [utest->req~schema-users-shared-table-anon-registered~1]
def test_both_kinds_of_user_are_classified_from_one_shared_ownership_model():
    # The same call classifies both kinds; nothing routes an anonymous user elsewhere.
    assert {account_class(provider) for provider in IdentityProvider} == set(AccountClass)


# --- What `email` and `display_name` are ---------------------------------------------------------

# [utest->req~schema-users-email-display-name-canonical~1]
def test_email_and_display_name_are_the_canonical_backend_profile_fields():
    assert PROFILE_FIELDS == ("email", "display_name")
    changes = profile_changes(ProfileWriter.user_profile_update,
                              {"email": "new@example.com", "display_name": "Ada"})
    assert changes == {"email": "new@example.com", "display_name": "Ada"}
    with pytest.raises(ProfileError):
        profile_changes(ProfileWriter.user_profile_update, {"registered_at": NOW})


# [utest->req~schema-users-email-not-identity-match~1]
def test_identity_is_matched_by_issuer_and_subject_and_never_by_email():
    assert_identity_match_fields(("issuer", "subject"))
    with pytest.raises(ProfileError):
        assert_identity_match_fields(("issuer", "subject", "email"))
    with pytest.raises(ProfileError):
        assert_identity_match_fields(("email",))


# [utest->req~schema-users-email-not-proof~1]
@pytest.mark.parametrize("use", [EmailUse.ownership_proof,
                                 EmailUse.authorization,
                                 EmailUse.account_recovery,
                                 EmailUse.identity_match])
def test_a_stored_address_is_never_by_itself_proof(use):
    with pytest.raises(ProfileError):
        assert_email_use(use)


# [utest->req~schema-users-email-not-proof~1]
def test_showing_the_stored_address_back_is_the_one_thing_it_is_good_for():
    assert_email_use(EmailUse.display)


# [utest->req~schema-users-email-control-verification~1]
@pytest.mark.parametrize("use", [EmailUse.account_recovery, EmailUse.address_change])
def test_security_sensitive_email_operations_verify_current_control_independently(use):
    with pytest.raises(ProfileError):
        assert_email_control_verified(use, control_verified=False)
    assert_email_control_verified(use, control_verified=True)


# --- Copying an address in -----------------------------------------------------------------------

# [utest->req~schema-users-email-copy-on-create~1]
@pytest.mark.parametrize("record,expected", [
    (VERIFIED, "user@example.com"),
    (AdminUserRecord(email="user@example.com", email_verified=False), None),
    (AdminUserRecord(email="", email_verified=True), None),
    (AdminUserRecord(email=None, email_verified=True), None),
    (None, None),
])
def test_the_initial_email_is_copied_only_from_a_verified_non_empty_address(record, expected):
    assert initial_email_on_create(record) == expected


# [utest->req~schema-users-email-copy-on-create~1]
def test_auth_completion_never_copies_a_display_name():
    assert profile_changes(ProfileWriter.auth_completion,
                           {"display_name": "From The IDP"}) == {}


# [utest->req~schema-users-email-copy-on-upgrade~1]
def test_the_upgrade_copies_an_email_only_into_a_still_null_column():
    assert email_on_upgrade(None, VERIFIED) == "user@example.com"
    assert email_on_upgrade("stored@example.com", VERIFIED) == "stored@example.com"
    assert email_on_upgrade(None, AdminUserRecord(email="u@e.com", email_verified=False)) is None
    assert email_on_upgrade(None, AdminUserRecord(email="", email_verified=True)) is None
    assert email_on_upgrade(None, None) is None
    assert email_on_upgrade("stored@example.com", None) == "stored@example.com"


# [utest->req~schema-users-email-may-be-stale~1]
def test_nothing_refreshes_a_copied_address_afterwards():
    # A later successful lookup reporting a different verified address changes nothing.
    assert sync_mutations({"email": "changed@example.com"}) == {}
    assert profile_changes(ProfileWriter.auth_sync, {"email": "changed@example.com"}) == {}


# --- Who may write ---------------------------------------------------------------------------------

# [utest->req~schema-users-profile-fields-explicit-update-only~1]
@pytest.mark.parametrize("writer", [ProfileWriter.auth_completion,
                                    ProfileWriter.auth_sync,
                                    ProfileWriter.client_presentation,
                                    ProfileWriter.operator_action])
def test_only_explicit_user_facing_profile_updates_change_the_profile_fields(writer):
    assert profile_changes(writer, {"email": "x@example.com", "display_name": "X"}) == {}


# [utest->req~schema-users-sync-no-overwrite~1]
def test_a_later_auth_sync_overwrites_neither_profile_fields_nor_access_grants():
    assert sync_mutations({"email": "x@example.com",
                           "display_name": "X",
                           "access_grants": [{"tier_id": "gold"}],
                           "active": True}) == {}


# [utest->req~schema-users-updated-at-on-mutation~1]
def test_every_mutation_stamps_updated_at_in_the_same_write():
    assert user_mutation({"email": "x@example.com"}, now=NOW) == {"email": "x@example.com",
                                                                  "updated_at": NOW}
    # A caller cannot smuggle a stale stamp past the mutation builder.
    stale = NOW - timedelta(days=30)
    assert user_mutation({"active": False, "updated_at": stale}, now=NOW)["updated_at"] == NOW
    with pytest.raises(ProfileError):
        user_mutation({}, now=NOW)


# --- Blocking, retention, and the identity row ------------------------------------------------------

# [utest->req~schema-users-active-false-blocked~1]
def test_an_inactive_user_is_blocked_and_is_never_reactivated_implicitly():
    assert is_blocked(False) is True
    assert is_blocked(True) is False
    for writer in (ProfileWriter.auth_sync, ProfileWriter.auth_completion):
        with pytest.raises(ProfileError):
            assert_no_implicit_reactivation(writer, stored_active=False, requested_active=True)
    # A deliberate operator action is the only way back.
    assert_no_implicit_reactivation(ProfileWriter.operator_action,
                                    stored_active=False, requested_active=True)
    # An active user is untouched by the rule.
    assert_no_implicit_reactivation(ProfileWriter.auth_sync,
                                    stored_active=True, requested_active=True)


# [utest->req~schema-users-never-hard-deleted~1]
def test_a_user_row_with_an_identity_row_is_never_hard_deleted():
    with pytest.raises(ProfileError):
        assert_hard_delete_allowed(has_external_identity=True)
    assert_hard_delete_allowed(has_external_identity=False)


# [utest->req~schema-users-anonymous-retained-indefinitely~1]
def test_anonymous_user_rows_have_no_scheduled_deletion():
    created = NOW - timedelta(days=4000)
    assert retention_deadline(AccountClass.anonymous, created_at=created) is None
    assert USER_RETENTION_DAYS[AccountClass.anonymous] is None
    assert set(USER_RETENTION_DAYS.values()) == {None}


# [utest->req~schema-users-created-with-identity-row~1]
def test_a_user_row_is_created_in_the_same_transaction_as_its_identity_row():
    assert_user_created_with_identity(identity_row_written=True)
    with pytest.raises(ProfileError):
        assert_user_created_with_identity(identity_row_written=False)


# [utest->req~schema-users-created-with-identity-row~1]
def test_no_sweep_repair_or_deletion_looks_for_a_user_row_without_an_identity_row():
    assert ORPHAN_USER_SWEEPS == frozenset()


# [utest->req~schema-users-created-with-identity-row~1]
def test_a_read_path_reaching_an_orphan_user_row_fails_closed_as_an_internal_error():
    user_id = uuid4()
    with pytest.raises(OrphanUserError) as raised:
        read_orphan_user(user_id)
    # It neither invents an identity row nor reassigns the account: it only reports.
    assert raised.value.result is AuthEventResult.internal_error
    assert raised.value.user_id == user_id
    # The row itself is left in place — the read path has no delete to offer.
    with pytest.raises(ProfileError):
        assert_hard_delete_allowed(has_external_identity=True)


# --- Client display ---------------------------------------------------------------------------------

# [utest->req~schema-users-client-display-name-fallback~1]
def test_the_client_falls_back_to_the_idp_name_only_when_the_backend_name_is_null():
    assert display_name_for_client(None, "Ada From Google") == "Ada From Google"
    assert display_name_for_client("Ada", "Ada From Google") == "Ada"
    assert display_name_for_client(None, None) is None


# [utest->req~schema-users-external-display-not-backend-data~1]
def test_the_external_display_value_does_not_become_backend_data():
    shown = display_name_for_client(None, "Ada From Google")
    assert profile_changes(ProfileWriter.client_presentation, {"display_name": shown}) == {}
    # Only an explicit update by the user writes it.
    assert profile_changes(ProfileWriter.user_profile_update,
                           {"display_name": shown}) == {"display_name": shown}
