"""The `core.external_identities` semantics: the verified identity, the provider binding, the
reservation, and the one-way lifecycle."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.external_identities import (
    DELETE_PERMITTED_ROLES,
    FIREBASE_DELETION_SYNC_MECHANISMS,
    FORBIDDEN_RESERVATION_OPTIONS,
    IDENTITY_ROW_DELETERS,
    LOOKUP_FAILURE_PERSISTS,
    PAIRING_ENFORCEMENT_MECHANISMS,
    PERMITTED_PROVIDER_TRANSITIONS,
    PROVIDER_CONFLICT_MUTATIONS,
    PROVIDER_CONFLICT_REMEDY,
    PROVIDER_READ_ONLY_READ_POINTS,
    PROVIDER_RECONCILIATION_JOBS,
    PROVIDER_WRITING_READ_POINTS,
    RACE_LOSER_ROLLBACK,
    REVOCATION_FAILURE_MACHINERY,
    SCRUB_EXEMPT_COLUMNS,
    STALE_ID_TOKEN_WINDOW,
    TOMBSTONE_DISCLOSURE_REQUIRED,
    AdministrativeAction,
    AlreadyLinkedSite,
    BindingDivergenceError,
    ExternalIdentities,
    ExternalIdentityRow,
    IdentityAlreadyLinkedError,
    IdentityError,
    IdentityFieldSource,
    IdentityState,
    LookupFailure,
    NativeClaimPlatform,
    ProviderClassificationError,
    ProviderConsumer,
    ProviderLookupFailedError,
    ProviderSource,
    ProviderUidSource,
    UpstreamDeletionRemedy,
    admin_client_for_identity,
    administrative_write,
    already_linked_result,
    assert_conversion_same_lineage,
    assert_lookup_fields,
    assert_may_write_provider_fields,
    assert_no_firebase_deletion_sync,
    assert_no_identity_delete,
    assert_no_sentinel_provider_uid,
    assert_provider_data_read_point,
    assert_provider_source,
    assert_provider_transition,
    assert_provider_uid_check,
    assert_provider_uid_source,
    assert_raw_provider_account_store,
    assert_raw_subject_store,
    assert_reservation_index,
    assert_upstream_deletion_remedy,
    assign_provider_uid,
    authoritative_provider,
    authorizes,
    classify_provider,
    clear_free_grant_marker,
    confirm_stored_binding,
    create_account,
    deletion_sync_transition,
    erase_pii,
    free_grant_available,
    historical_identity_rejection,
    identity_key,
    in_reservation_scope,
    mark_free_grant_consumed,
    matches_identity,
    may_delete_identity_rows,
    never_linked,
    pin_native_claim_platform,
    provider_account_conflict,
    provider_from_lookup,
    provider_uid_for,
    resolve_owner,
    resolves_through_stale_row,
    retire,
    revokes_refresh_tokens,
    stale_row_retirement_deadline,
    transition_identity_state,
    uniqueness_race_loser,
    upgrade_to_registered,
    write_provider_uid,
)
from nativespeaker.api.auth.integration import FirebaseIntegration, FirebaseIntegrations
from nativespeaker.api.auth.invariants import (
    InvariantError,
    ProviderAccountAlreadyLinkedError,
    ProviderAccountReservations,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.profile import OrphanUserError
from nativespeaker.api.auth.taxonomy import ClientErrorClass, ProviderDataReadPoint
from nativespeaker.api.auth.tokens import InvalidExternalJwtError, VerifiedClaims

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
ISSUER = "https://securetoken.google.com/test-project"


def anon_row(**overrides) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"id": uuid4(), "user_id": uuid4(), "issuer": ISSUER, "subject": "sub-1",
              "provider": IdentityProvider.anonymous}
    fields.update(overrides)
    return ExternalIdentityRow(**fields)


def google_row(**overrides) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.google,
                              "provider_uid": "google-uid"}
    fields.update(overrides)
    return anon_row(**fields)


class _StubVerifier:
    def verify_id_token(self, token: str) -> VerifiedClaims:
        return VerifiedClaims(issuer=ISSUER, subject="sub-1")


def integrations(admin_client: object) -> FirebaseIntegrations:
    return FirebaseIntegrations([FirebaseIntegration(issuer=ISSUER, project_id="test-project",
                                                     verifier=_StubVerifier(),
                                                     admin_client=admin_client)])


# --- Where the raw identity may live ------------------------------------------------------------


class TestRawIdentityStorage:

    # [utest->req~schema-external-identities-only-raw-subject-store~1]
    def test_only_the_identity_table_stores_a_raw_subject(self):
        assert_raw_subject_store("core.external_identities")
        for table in ("core.auth_challenges", "audit.auth_events", "core.provider_accounts"):
            with pytest.raises(IdentityError):
                assert_raw_subject_store(table)

    # [utest->req~schema-external-identities-only-raw-subject-store~1]
    def test_two_tables_may_hold_a_raw_provider_account_identifier(self):
        assert_raw_provider_account_store("core.external_identities")
        assert_raw_provider_account_store("core.provider_accounts")
        for table in ("core.auth_challenges", "audit.auth_events"):
            with pytest.raises(IdentityError):
                assert_raw_provider_account_store(table)

    # [utest->req~schema-external-identities-issuer-subject-from-verified-token~1]
    def test_issuer_and_subject_come_from_the_verified_token_alone(self):
        assert identity_key(ISSUER, "sub-1",
                            source=IdentityFieldSource.verified_id_token) == (ISSUER, "sub-1")
        for source in (IdentityFieldSource.transport_metadata, IdentityFieldSource.request_header,
                       IdentityFieldSource.cookie, IdentityFieldSource.client_field):
            with pytest.raises(IdentityError):
                identity_key(ISSUER, "sub-1", source=source)

    # [utest->req~schema-external-identities-issuer-subject-from-verified-token~1]
    def test_a_missing_claim_is_never_defaulted(self):
        with pytest.raises(IdentityError):
            identity_key("", "sub-1", source=IdentityFieldSource.verified_id_token)


class TestIdentityLookup:

    # [utest->req~schema-external-identities-lookup-by-issuer-subject~1]
    def test_lookup_is_the_exact_issuer_subject_pair(self):
        assert_lookup_fields(("issuer", "subject"))
        for fields in (("subject",), ("issuer",), ("issuer", "subject", "email"), ("email",)):
            with pytest.raises(IdentityError):
                assert_lookup_fields(fields)

    # [utest->req~schema-external-identities-lookup-by-issuer-subject~1]
    def test_the_match_is_exact_on_both_halves(self):
        row = anon_row()
        assert matches_identity(row, ISSUER, "sub-1")
        assert not matches_identity(row, ISSUER, "SUB-1")
        assert not matches_identity(row, ISSUER.upper(), "sub-1")
        assert not matches_identity(row, ISSUER, " sub-1 ")


# --- Administrative operations -------------------------------------------------------------------


class TestAdministrativeOperations:

    # [utest->req~schema-external-identities-stored-issuer-selects-admin-client~1]
    def test_the_stored_issuer_selects_the_admin_client(self):
        client = object()
        assert admin_client_for_identity(integrations(client), anon_row()) is client
        with pytest.raises(InvalidExternalJwtError):
            admin_client_for_identity(integrations(client), anon_row(issuer="https://other"))

    # [utest->req~schema-external-identities-stored-issuer-selects-admin-client~1]
    def test_the_lifecycle_write_is_committed_first_and_survives_a_failed_revocation(self):
        blocked = administrative_write(AdministrativeAction.block_user, revocation_failed=True)
        assert blocked.committed is True
        assert blocked.lifecycle_write == "core.users.active = FALSE"
        retired = administrative_write(AdministrativeAction.retire_identity,
                                       revocation_failed=True)
        assert retired.committed is True
        assert retired.lifecycle_write.endswith("identity_state = 'historical'")

    # [utest->req~schema-external-identities-stored-issuer-selects-admin-client~1]
    def test_a_revocation_failure_never_rolls_the_database_state_back(self):
        with pytest.raises(IdentityError):
            administrative_write(AdministrativeAction.block_user, revocation_failed=True,
                                 rollback_requested=True)

    # [utest->req~schema-external-identities-stored-issuer-selects-admin-client~1]
    def test_no_retry_compensation_marker_or_queue_exists_only_a_manual_operator_retry(self):
        assert REVOCATION_FAILURE_MACHINERY == frozenset()
        outcome = administrative_write(AdministrativeAction.retire_identity,
                                       revocation_failed=True)
        assert outcome.operator_retry_available is True
        clean = administrative_write(AdministrativeAction.retire_identity, revocation_failed=False)
        assert clean.operator_retry_available is False


# --- Creation ---------------------------------------------------------------------------------------


class TestAccountCreation:

    # [utest->req~schema-external-identities-user-and-identity-one-transaction~1]
    def test_both_rows_are_written_in_one_transaction(self):
        transaction = object()
        user_id = uuid4()
        identity = anon_row(user_id=user_id)
        created = create_account(user_id=user_id, identity=identity,
                                 user_transaction=transaction, identity_transaction=transaction)
        assert created.transaction is transaction
        with pytest.raises(IdentityError):
            create_account(user_id=user_id, identity=identity, user_transaction=transaction,
                           identity_transaction=object())

    # [utest->req~schema-external-identities-user-and-identity-one-transaction~1]
    def test_unique_user_id_caps_a_user_at_one_identity_row(self):
        transaction = object()
        user_id = uuid4()
        with pytest.raises(IdentityError):
            create_account(user_id=user_id, identity=anon_row(user_id=user_id),
                           user_transaction=transaction, identity_transaction=transaction,
                           existing_identity_for_user=anon_row(user_id=user_id))

    # [utest->req~schema-external-identities-user-and-identity-one-transaction~1]
    def test_no_constraint_trigger_or_healer_enforces_the_pairing(self):
        assert PAIRING_ENFORCEMENT_MECHANISMS == frozenset()

    # [utest->req~schema-external-identities-orphan-user-internal-error~1]
    def test_an_orphan_user_row_is_an_internal_error_that_repairs_nothing(self):
        user_id = uuid4()
        row = anon_row(user_id=user_id)
        assert resolve_owner(row, user_id=user_id) == user_id
        with pytest.raises(OrphanUserError) as excinfo:
            resolve_owner(None, user_id=user_id)
        assert excinfo.value.result is AuthEventResult.internal_error
        assert excinfo.value.user_id == user_id


# --- Uniqueness ----------------------------------------------------------------------------------------


class TestUniqueness:

    # [utest->req~schema-external-identities-unique-issuer-subject~1]
    def test_one_issuer_subject_pair_belongs_to_one_user_anonymous_and_registered_alike(self):
        store = ExternalIdentities()
        store.link(anon_row(subject="a"))
        with pytest.raises(IdentityAlreadyLinkedError):
            store.link(anon_row(subject="a"))
        store.link(google_row(subject="b"))
        with pytest.raises(IdentityAlreadyLinkedError):
            store.link(google_row(subject="b", provider_uid="other-uid"))

    # [utest->req~schema-external-identities-unique-issuer-subject~1]
    def test_no_sentinel_provider_uid_is_invented_for_an_anonymous_row(self):
        assert_no_sentinel_provider_uid(anon_row())
        with pytest.raises(IdentityError):
            ExternalIdentityRow(id=uuid4(), user_id=uuid4(), issuer=ISSUER, subject="s",
                                provider=IdentityProvider.anonymous, provider_uid="placeholder")

    # [utest->req~schema-external-identities-identity-already-linked-result~1]
    def test_all_three_rejection_sites_audit_the_same_result(self):
        results = {already_linked_result(site) for site in AlreadyLinkedSite}
        assert results == {AuthEventResult.identity_already_linked}
        assert len(set(AlreadyLinkedSite)) == 3

    # [utest->req~schema-external-identities-uniqueness-race-arbiter~1]
    def test_the_race_loser_rolls_back_everything_and_audits_already_linked(self):
        outcome = uniqueness_race_loser()
        assert outcome.result is AuthEventResult.identity_already_linked
        assert outcome.result is not AuthEventResult.invalid_external_jwt
        assert outcome.client_class is ClientErrorClass.identity_already_linked
        assert outcome.rolled_back == RACE_LOSER_ROLLBACK
        assert "per_device_grant_state_read" in outcome.rolled_back
        assert "grant" in outcome.rolled_back


# --- The provider classification -------------------------------------------------------------------------


class TestProviderClassification:

    # [utest->req~schema-external-identities-provider-enum-typed~1]
    def test_provider_is_stored_as_the_schema_enum_not_free_text(self):
        assert google_row().provider is IdentityProvider.google
        with pytest.raises(IdentityError):
            ExternalIdentityRow(id=uuid4(), user_id=uuid4(), issuer=ISSUER, subject="s",
                                provider="google", provider_uid="u")  # type: ignore[arg-type]

    # [utest->req~schema-external-identities-provider-closed-classifier~1]
    def test_the_three_recognized_shapes(self):
        assert classify_provider([]) is IdentityProvider.anonymous
        assert classify_provider([{"provider_id": "google.com"}]) is IdentityProvider.google
        assert classify_provider([{"provider_id": "apple.com"}]) is IdentityProvider.apple

    # [utest->req~schema-external-identities-provider-closed-classifier~1]
    def test_every_other_shape_rejects(self):
        for shape in ([{"provider_id": "google.com"}, {"provider_id": "apple.com"}],
                      [{"provider_id": "google.com"}, {"provider_id": "google.com"}],
                      [{"provider_id": "facebook.com"}],
                      [{"provider_id": ""}]):
            with pytest.raises(ProviderClassificationError):
                classify_provider(shape)

    # [utest->req~schema-external-identities-provider-closed-classifier~1]
    def test_the_first_recognized_entry_is_never_selected(self):
        with pytest.raises(ProviderClassificationError):
            classify_provider([{"provider_id": "google.com"}, {"provider_id": "facebook.com"}])

    # [utest->req~schema-external-identities-provider-closed-classifier~1]
    def test_non_empty_provider_data_is_never_anonymous(self):
        with pytest.raises(ProviderClassificationError):
            classify_provider([{"provider_id": "unknown"}])

    # [utest->req~schema-external-identities-provider-closed-classifier~1]
    def test_token_claims_and_headers_are_never_a_provider_source(self):
        assert_provider_source(ProviderSource.firebase_admin_provider_data)
        for source in (ProviderSource.token_claim, ProviderSource.request_header,
                       ProviderSource.client_declaration, ProviderSource.stored_profile_data):
            with pytest.raises(ProviderClassificationError):
                assert_provider_source(source)


class TestProviderLookupFailsClosed:

    # [utest->req~schema-external-identities-provider-lookup-fail-closed~1]
    def test_a_successful_well_formed_record_derives_the_provider(self):
        assert provider_from_lookup([{"provider_id": "apple.com"}]) is IdentityProvider.apple

    # [utest->req~schema-external-identities-provider-lookup-fail-closed~1]
    def test_a_deleted_subject_is_non_retryable_and_surfaces_auth_required(self):
        with pytest.raises(ProviderLookupFailedError) as excinfo:
            provider_from_lookup(None, failure=LookupFailure.user_not_found)
        assert excinfo.value.result is AuthEventResult.firebase_user_unresolved
        assert excinfo.value.client_class is ClientErrorClass.auth_required
        assert excinfo.value.retryable is False

    # [utest->req~schema-external-identities-provider-lookup-fail-closed~1]
    def test_every_indeterminate_failure_is_the_distinct_transient_result(self):
        for failure in (LookupFailure.transient, LookupFailure.infrastructure,
                        LookupFailure.malformed_response, LookupFailure.indeterminate):
            with pytest.raises(ProviderLookupFailedError) as excinfo:
                provider_from_lookup(None, failure=failure)
            assert excinfo.value.result is AuthEventResult.firebase_lookup_unavailable
            assert excinfo.value.client_class is \
                ClientErrorClass.verification_temporarily_unavailable
            assert excinfo.value.retryable is True

    # [utest->req~schema-external-identities-provider-lookup-fail-closed~1]
    def test_a_failed_lookup_is_never_read_as_an_empty_provider_data_result(self):
        with pytest.raises(ProviderLookupFailedError):
            provider_from_lookup(None)
        assert LOOKUP_FAILURE_PERSISTS == frozenset()


class TestStoredProviderIsAuthoritative:

    # [utest->req~schema-external-identities-stored-provider-authoritative~1]
    def test_every_per_request_decision_reads_the_stored_provider(self):
        row = google_row()
        for consumer in (ProviderConsumer.registered_grant_gating, ProviderConsumer.claim_path,
                         ProviderConsumer.authorization_branch, ProviderConsumer.audit_branch,
                         ProviderConsumer.entitlement_handling):
            assert authoritative_provider(row, consumer) is IdentityProvider.google

    # [utest->req~schema-external-identities-stored-provider-authoritative~1]
    def test_revocation_is_unconditional_and_never_reads_the_stored_provider(self):
        with pytest.raises(IdentityError):
            authoritative_provider(google_row(), ProviderConsumer.refresh_token_revocation)
        assert revokes_refresh_tokens(anon_row()) is True
        assert revokes_refresh_tokens(google_row()) is True


# --- `provider_uid` ---------------------------------------------------------------------------------------


class TestProviderUid:

    # [utest->req~schema-external-identities-provider-uid-source~1]
    def test_the_uid_comes_from_the_matching_provider_data_entry(self):
        assert provider_uid_for(IdentityProvider.anonymous, []) is None
        assert provider_uid_for(IdentityProvider.google,
                                [{"provider_id": "google.com", "uid": "g-1"}]) == "g-1"
        assert provider_uid_for(IdentityProvider.apple,
                                [{"provider_id": "apple.com", "uid": "a-1"}]) == "a-1"

    # [utest->req~schema-external-identities-provider-uid-source~1]
    def test_a_missing_or_empty_uid_is_refused(self):
        with pytest.raises(InvariantError):
            provider_uid_for(IdentityProvider.google, [{"provider_id": "google.com", "uid": ""}])
        with pytest.raises(InvariantError):
            provider_uid_for(IdentityProvider.google, [{"provider_id": "apple.com", "uid": "a"}])

    # [utest->req~schema-external-identities-provider-uid-never-client-input~1]
    def test_no_other_source_may_supply_the_uid(self):
        assert_provider_uid_source(ProviderUidSource.firebase_provider_data)
        for source in (ProviderUidSource.client_input, ProviderUidSource.request_header,
                       ProviderUidSource.token_claim, ProviderUidSource.email,
                       ProviderUidSource.display_name):
            with pytest.raises(IdentityError):
                assert_provider_uid_source(source)

    # [utest->req~schema-external-identities-provider-uid-same-transaction~1]
    def test_the_uid_is_written_in_the_rows_own_transaction(self):
        transaction = object()
        row = anon_row()
        assert write_provider_uid(row, None, row_transaction=transaction,
                                  uid_transaction=transaction).provider_uid is None
        with pytest.raises(IdentityError):
            write_provider_uid(row, None, row_transaction=transaction, uid_transaction=object())

    # [utest->req~schema-external-identities-provider-uid-immutable~1]
    def test_the_sole_assignment_transition_is_the_upgrade(self):
        assert assign_provider_uid(
            None, "g-1", operation=AuthOperation.upgrade_anonymous_to_registered) == "g-1"
        with pytest.raises(IdentityError):
            assign_provider_uid(None, "g-1", operation=AuthOperation.create_user)

    # [utest->req~schema-external-identities-provider-uid-immutable~1]
    def test_an_assigned_uid_is_never_rewritten(self):
        with pytest.raises(InvariantError):
            assign_provider_uid("g-1", "g-2",
                                operation=AuthOperation.upgrade_anonymous_to_registered)
        assert assign_provider_uid(
            "g-1", "g-1", operation=AuthOperation.upgrade_anonymous_to_registered) == "g-1"


class TestProviderDataReadPoints:

    # [utest->req~schema-external-identities-provider-data-five-read-points~1]
    def test_the_five_read_points_are_the_complete_set(self):
        assert len(set(ProviderDataReadPoint)) == 5
        for point in ProviderDataReadPoint:
            assert assert_provider_data_read_point(point) is point
        for other in ("sync", "restore_subscription", "sign_out_all", "ordinary_request"):
            with pytest.raises(IdentityError):
                assert_provider_data_read_point(other)

    # [utest->req~schema-external-identities-provider-data-five-read-points~1]
    def test_only_creation_and_upgrade_write_the_stored_provider_fields(self):
        for point in PROVIDER_WRITING_READ_POINTS:
            assert_may_write_provider_fields(point)
        assert len(PROVIDER_WRITING_READ_POINTS) == 3

    # [utest->req~schema-external-identities-provider-data-five-read-points~1]
    def test_the_two_live_matches_persist_neither_field(self):
        assert PROVIDER_READ_ONLY_READ_POINTS == {
            ProviderDataReadPoint.web_anonymous_grant_gate,
            ProviderDataReadPoint.claim_registered_grant_completion}
        for point in PROVIDER_READ_ONLY_READ_POINTS:
            with pytest.raises(IdentityError):
                assert_may_write_provider_fields(point)

    # [utest->req~schema-external-identities-provider-data-five-read-points~1]
    def test_no_job_reconciles_the_stored_value_against_live_firebase(self):
        assert PROVIDER_RECONCILIATION_JOBS == frozenset()


# --- The reservation ---------------------------------------------------------------------------------------


class TestProviderAccountReservation:

    # [utest->req~schema-external-identities-provider-account-reservation-index~1]
    def test_the_reservation_is_a_partial_unique_index(self):
        assert_reservation_index(columns=("issuer", "provider", "provider_uid"),
                                 predicate="provider_uid IS NOT NULL")
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=("issuer", "provider", "provider_uid"),
                                     predicate="provider_uid IS NOT NULL",
                                     table_wide_unique=True)
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=("provider", "provider_uid"),
                                     predicate="provider_uid IS NOT NULL")
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=("issuer", "provider", "provider_uid"), predicate="")

    # [utest->req~schema-external-identities-provider-account-reservation-index~1]
    def test_a_provider_account_is_usable_by_at_most_one_user_ever(self):
        reservations = ProviderAccountReservations()
        owner = uuid4()
        reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                          provider=IdentityProvider.google, provider_uid="g-1", user_id=owner)
        with pytest.raises(ProviderAccountAlreadyLinkedError):
            reservations.bind(operation=AuthOperation.upgrade_anonymous_to_registered,
                              issuer=ISSUER, provider=IdentityProvider.google,
                              provider_uid="g-1", user_id=uuid4())

    # [utest->req~schema-external-identities-provider-account-reservation-index~1]
    def test_retirement_does_not_free_the_provider_account(self):
        reservations = ProviderAccountReservations()
        owner = uuid4()
        reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                          provider=IdentityProvider.google, provider_uid="g-1", user_id=owner)
        reservations.retire(issuer=ISSUER, provider=IdentityProvider.google, provider_uid="g-1")
        assert reservations.is_historical(ISSUER, IdentityProvider.google, "g-1")
        assert reservations.holder(ISSUER, IdentityProvider.google, "g-1") == owner
        with pytest.raises(ProviderAccountAlreadyLinkedError):
            reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                              provider=IdentityProvider.google, provider_uid="g-1",
                              user_id=uuid4())

    # [utest->req~schema-external-identities-provider-account-reservation-index~1]
    def test_the_index_covers_active_and_historical_rows_alike(self):
        assert in_reservation_scope(google_row()) is True
        assert in_reservation_scope(google_row(identity_state=IdentityState.historical)) is True


class TestReservationNotNullSemantics:

    # [utest->req~schema-external-identities-reservation-not-null-semantics~1]
    def test_anonymous_rows_fall_wholly_outside_the_index_and_coexist_without_limit(self):
        rows = [anon_row(subject=f"s-{index}") for index in range(5)]
        assert [in_reservation_scope(row) for row in rows] == [False] * 5

    # [utest->req~schema-external-identities-reservation-not-null-semantics~1]
    def test_nulls_not_distinct_must_not_be_used(self):
        assert "NULLS NOT DISTINCT" in FORBIDDEN_RESERVATION_OPTIONS
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=("issuer", "provider", "provider_uid"),
                                     predicate="provider_uid IS NOT NULL",
                                     options=("NULLS NOT DISTINCT",))

    # [utest->req~schema-external-identities-reservation-not-null-semantics~1]
    def test_the_check_keeps_every_registered_row_inside_the_index(self):
        assert_provider_uid_check(IdentityProvider.anonymous, None)
        assert_provider_uid_check(IdentityProvider.google, "g-1")
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.google, None)
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.apple, "")
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.anonymous, "placeholder")

    # [utest->req~schema-external-identities-provider-account-already-linked~1]
    def test_a_conflict_rejects_through_operation_not_allowed_and_changes_nothing(self):
        for operation in (AuthOperation.create_user,
                          AuthOperation.upgrade_anonymous_to_registered):
            error = provider_account_conflict(operation)
            assert error.result is AuthEventResult.provider_account_already_linked
            assert error.client_class is ClientErrorClass.operation_not_allowed
        assert PROVIDER_CONFLICT_MUTATIONS == frozenset()
        assert PROVIDER_CONFLICT_REMEDY == "manual_operator_fix"

    # [utest->req~schema-external-identities-provider-account-already-linked~1]
    def test_only_the_two_provider_binding_writes_take_the_conflict(self):
        for operation in (AuthOperation.sync, AuthOperation.claim_registered_grant,
                          AuthOperation.restore_subscription):
            with pytest.raises(IdentityError):
                provider_account_conflict(operation)


# --- Provider transitions -----------------------------------------------------------------------------------


class TestProviderTransitions:

    # [utest->req~schema-external-identities-provider-monotonic-transition-record~1]
    def test_the_stored_provider_never_moves_backwards_or_sideways(self):
        with pytest.raises(IdentityError):
            assert_provider_transition(IdentityProvider.google, IdentityProvider.apple)
        with pytest.raises(IdentityError):
            assert_provider_transition(IdentityProvider.apple, IdentityProvider.google)
        assert_provider_transition(IdentityProvider.google, IdentityProvider.google)

    # [utest->req~schema-external-identities-only-anonymous-to-registered~1]
    def test_the_only_permitted_transition_is_anonymous_to_registered(self):
        assert PERMITTED_PROVIDER_TRANSITIONS == {
            (IdentityProvider.anonymous, IdentityProvider.google),
            (IdentityProvider.anonymous, IdentityProvider.apple)}
        assert_provider_transition(IdentityProvider.anonymous, IdentityProvider.google)
        assert_provider_transition(IdentityProvider.anonymous, IdentityProvider.apple)

    # [utest->req~schema-external-identities-only-anonymous-to-registered~1]
    def test_there_is_no_registered_to_anonymous_transition(self):
        for registered in (IdentityProvider.google, IdentityProvider.apple):
            with pytest.raises(IdentityError):
                assert_provider_transition(registered, IdentityProvider.anonymous)

    # [utest->req~schema-external-identities-binding-divergence-refused~1]
    def test_a_matching_live_binding_confirms(self):
        confirm_stored_binding(google_row(), live_provider=IdentityProvider.google,
                               live_provider_uid="google-uid")

    # [utest->req~schema-external-identities-binding-divergence-refused~1]
    def test_a_divergent_provider_or_uid_is_refused_and_never_rewritten(self):
        row = google_row()
        with pytest.raises(BindingDivergenceError) as excinfo:
            confirm_stored_binding(row, live_provider=IdentityProvider.apple,
                                   live_provider_uid="google-uid")
        assert excinfo.value.result is AuthEventResult.provider_transition_not_allowed
        assert excinfo.value.client_class is ClientErrorClass.operation_not_allowed
        with pytest.raises(BindingDivergenceError):
            confirm_stored_binding(row, live_provider=IdentityProvider.google,
                                   live_provider_uid="other-uid")
        assert row.provider is IdentityProvider.google
        assert row.provider_uid == "google-uid"


# --- `identity_state` ------------------------------------------------------------------------------------------


class TestIdentityState:

    # [utest->req~schema-external-identities-state-active-authorizes~1]
    def test_an_active_identity_authorizes(self):
        assert authorizes(IdentityState.active) is True

    # [utest->req~schema-external-identities-state-historical-no-authorize~1]
    def test_a_historical_identity_does_not_authorize(self):
        assert authorizes(IdentityState.historical) is False

    # [utest->req~schema-external-identities-historical-identity-result~1]
    def test_the_two_states_keep_distinct_audit_results(self):
        result, _ = historical_identity_rejection()
        assert result is AuthEventResult.historical_identity
        assert result is not AuthEventResult.blocked_user

    # [utest->req~schema-external-identities-historical-identity-result~1]
    def test_the_client_cannot_distinguish_a_historical_identity_from_a_blocked_user(self):
        _, rejection = historical_identity_rejection()
        assert rejection.body == {"code": ClientErrorClass.account_unavailable}
        assert rejection.status == 403
        assert set(rejection.body) == {"code"}

    # [utest->req~schema-external-identities-state-transition-one-way~1]
    def test_the_transition_set_is_the_one_way_administrative_transition(self):
        assert transition_identity_state(IdentityState.active, IdentityState.historical,
                                         administrative=True) is IdentityState.historical
        with pytest.raises(IdentityError):
            transition_identity_state(IdentityState.historical, IdentityState.active,
                                      administrative=True)
        with pytest.raises(IdentityError):
            transition_identity_state(IdentityState.active, IdentityState.active,
                                      administrative=True)
        with pytest.raises(IdentityError):
            transition_identity_state(IdentityState.active, IdentityState.historical,
                                      administrative=False)


# --- Retention, retirement, erasure ---------------------------------------------------------------------------------


class TestRetentionAndErasure:

    # [utest->req~schema-external-identities-rows-never-deleted~1]
    def test_no_path_deletes_an_identity_row(self):
        assert IDENTITY_ROW_DELETERS == frozenset()
        with pytest.raises(IdentityError):
            assert_no_identity_delete("account_teardown")

    # [utest->req~schema-external-identities-rows-never-deleted~1]
    def test_no_matching_row_means_the_identity_was_never_linked(self):
        assert never_linked(None) is True
        assert never_linked(anon_row()) is False

    # [utest->req~schema-external-identities-no-delete-permission~1]
    def test_no_application_or_cleanup_role_may_delete_identity_rows(self):
        assert DELETE_PERMITTED_ROLES == frozenset()
        for role in ("application", "cleanup", "api", "migrator"):
            assert may_delete_identity_rows(role) is False

    # [utest->req~schema-external-identities-no-delete-permission~1]
    def test_no_statement_in_the_source_deletes_from_the_identity_table(self):
        source = Path(__file__).resolve().parents[2] / "src"
        offending = [path for path in source.rglob("*.py")
                     if "delete from core.external_identities" in path.read_text().lower()]
        assert offending == []

    # [utest->req~schema-external-identities-retirement-erasure-keep-pair~1]
    def test_retirement_keeps_both_sides_of_the_pair(self):
        row = google_row()
        retired = retire(row)
        assert retired.identity_state is IdentityState.historical
        assert (retired.id, retired.user_id) == (row.id, row.user_id)
        assert (retired.issuer, retired.subject) == (row.issuer, row.subject)

    # [utest->req~schema-external-identities-retirement-erasure-keep-pair~1]
    def test_erasure_scrubs_in_place_and_reassigns_nothing(self):
        row = google_row(identity_state=IdentityState.historical,
                         native_claim_platform=NativeClaimPlatform.ios_devicecheck)
        scrubbed = erase_pii(row)
        assert (scrubbed.id, scrubbed.user_id) == (row.id, row.user_id)
        assert scrubbed.identity_state is IdentityState.historical
        assert scrubbed.native_claim_platform is None

    # [utest->req~schema-external-identities-historical-tombstone-scrub-exception~1]
    def test_the_tombstone_retains_its_uniqueness_reservations(self):
        assert SCRUB_EXEMPT_COLUMNS == ("issuer", "subject", "provider", "provider_uid")
        row = google_row(identity_state=IdentityState.historical)
        scrubbed = erase_pii(row)
        assert scrubbed.issuer == row.issuer
        assert scrubbed.subject == row.subject
        assert scrubbed.provider is IdentityProvider.google
        assert scrubbed.provider_uid == "google-uid"

    # [utest->req~schema-external-identities-historical-tombstone-scrub-exception~1]
    def test_the_retention_exception_is_disclosed(self):
        assert TOMBSTONE_DISCLOSURE_REQUIRED is True


# --- Upstream deletion --------------------------------------------------------------------------------------------


class TestUpstreamDeletion:

    # [utest->req~schema-external-identities-no-firebase-deletion-sync~1]
    def test_a_provider_side_deletion_changes_nothing_in_the_database(self):
        assert FIREBASE_DELETION_SYNC_MECHANISMS == frozenset()
        assert deletion_sync_transition(google_row()) is None

    # [utest->req~schema-external-identities-no-firebase-deletion-sync~1]
    def test_no_detection_reconciliation_or_webhook_exists(self):
        for mechanism in ("deletion_detection", "periodic_reconciliation", "webhook_handler"):
            with pytest.raises(IdentityError):
                assert_no_firebase_deletion_sync(mechanism)

    # [utest->req~schema-external-identities-stale-token-window~1]
    def test_a_minted_token_keeps_resolving_through_the_stale_active_row_until_its_exp(self):
        assert STALE_ID_TOKEN_WINDOW == timedelta(hours=1)
        row = google_row()
        exp = NOW + timedelta(minutes=30)
        assert resolves_through_stale_row(row, token_exp=exp, now=NOW) is True
        assert resolves_through_stale_row(row, token_exp=exp,
                                          now=NOW + timedelta(hours=2)) is False

    # [utest->req~schema-external-identities-stale-token-window~1]
    def test_the_stale_row_may_remain_active_indefinitely(self):
        row = google_row()
        assert stale_row_retirement_deadline(row) is None
        retired = retire(row)
        assert resolves_through_stale_row(retired, token_exp=NOW + timedelta(minutes=30),
                                          now=NOW) is False

    # [utest->req~schema-external-identities-upstream-deletion-manual-remedy~1]
    def test_the_defined_remedies_are_the_two_manual_administrative_ones(self):
        assert assert_upstream_deletion_remedy(UpstreamDeletionRemedy.administrative_block) is \
            UpstreamDeletionRemedy.administrative_block
        assert assert_upstream_deletion_remedy("administrative_retirement") is \
            UpstreamDeletionRemedy.administrative_retirement
        for other in ("automatic_deletion_sync", "background_retire", "webhook_block"):
            with pytest.raises(IdentityError):
                assert_upstream_deletion_remedy(other)


# --- The upgrade and the per-account markers ---------------------------------------------------------------------


class TestUpgradeInPlace:

    # [utest->req~schema-external-identities-upgrade-in-place~1]
    def test_the_upgrade_flips_the_existing_row_and_creates_none(self):
        transaction = object()
        row = anon_row()
        upgraded = upgrade_to_registered(row, provider=IdentityProvider.google,
                                         provider_uid="g-1", transaction=transaction)
        assert upgraded.id == row.id
        assert (upgraded.issuer, upgraded.subject) == (row.issuer, row.subject)
        assert upgraded.provider is IdentityProvider.google
        assert upgraded.provider_uid == "g-1"

    # [utest->req~schema-external-identities-upgrade-in-place~1]
    def test_the_upgrade_marks_no_row_historical(self):
        upgraded = upgrade_to_registered(anon_row(), provider=IdentityProvider.apple,
                                         provider_uid="a-1", transaction=object())
        assert upgraded.identity_state is IdentityState.active

    # [utest->req~schema-external-identities-upgrade-in-place~1]
    def test_an_already_registered_row_is_not_upgraded_again(self):
        with pytest.raises(IdentityError):
            upgrade_to_registered(google_row(), provider=IdentityProvider.apple,
                                  provider_uid="a-1", transaction=object())


class TestNativeClaimPlatform:

    # [utest->req~schema-external-identities-native-claim-platform-pinned~1]
    def test_the_platform_is_pinned_on_the_first_verified_attestation(self):
        row = anon_row()
        pinned = pin_native_claim_platform(row, NativeClaimPlatform.ios_devicecheck,
                                           attestation_verified=True)
        assert pinned.native_claim_platform is NativeClaimPlatform.ios_devicecheck

    # [utest->req~schema-external-identities-native-claim-platform-pinned~1]
    def test_an_unverified_attestation_pins_nothing(self):
        with pytest.raises(IdentityError):
            pin_native_claim_platform(anon_row(), NativeClaimPlatform.ios_devicecheck,
                                      attestation_verified=False)

    # [utest->req~schema-external-identities-native-claim-platform-pinned~1]
    def test_the_identity_cannot_switch_native_branches(self):
        row = anon_row(native_claim_platform=NativeClaimPlatform.ios_devicecheck)
        assert pin_native_claim_platform(row, NativeClaimPlatform.ios_devicecheck,
                                         attestation_verified=True) is row
        with pytest.raises(IdentityError):
            pin_native_claim_platform(row, NativeClaimPlatform.android_play_integrity,
                                      attestation_verified=True)


class TestFreeGrantConsumedAt:

    # [utest->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    def test_the_marker_is_set_in_the_transaction_that_commits_the_grant(self):
        transaction = object()
        marked = mark_free_grant_consumed(anon_row(), now=NOW, grant_transaction=transaction,
                                          marker_transaction=transaction)
        assert marked.free_grant_consumed_at == NOW
        with pytest.raises(IdentityError):
            mark_free_grant_consumed(anon_row(), now=NOW, grant_transaction=transaction,
                                     marker_transaction=object())

    # [utest->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    def test_the_marker_is_never_cleared_and_a_retry_creates_no_second_lineage(self):
        transaction = object()
        row = anon_row(free_grant_consumed_at=NOW)
        again = mark_free_grant_consumed(row, now=NOW + timedelta(days=1),
                                         grant_transaction=transaction,
                                         marker_transaction=transaction)
        assert again.free_grant_consumed_at == NOW
        with pytest.raises(IdentityError):
            clear_free_grant_marker(row)

    # [utest->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    def test_the_marker_is_authoritative_for_the_cross_endpoint_refusal(self):
        fresh = anon_row()
        consumed = anon_row(free_grant_consumed_at=NOW)
        for endpoint in (AuthOperation.claim_anonymous_grant,
                         AuthOperation.claim_registered_grant):
            assert free_grant_available(fresh, endpoint) is True
            assert free_grant_available(consumed, endpoint) is False
        with pytest.raises(IdentityError):
            free_grant_available(fresh, AuthOperation.sync)

    # [utest->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    def test_the_marker_survives_retirement_erasure_and_the_upgrade(self):
        row = anon_row(free_grant_consumed_at=NOW)
        assert retire(row).free_grant_consumed_at == NOW
        assert erase_pii(retire(row)).free_grant_consumed_at == NOW
        upgraded = upgrade_to_registered(row, provider=IdentityProvider.google,
                                         provider_uid="g-1", transaction=object())
        assert upgraded.free_grant_consumed_at == NOW

    # [utest->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    def test_conversion_transitions_the_same_lineage_rather_than_issuing_a_second(self):
        row = anon_row(free_grant_consumed_at=NOW)
        assert_conversion_same_lineage(row, converted_at=NOW + timedelta(hours=1))
        with pytest.raises(IdentityError):
            assert_conversion_same_lineage(anon_row(), converted_at=NOW)
        with pytest.raises(IdentityError):
            assert_conversion_same_lineage(row, converted_at=NOW - timedelta(hours=1))
