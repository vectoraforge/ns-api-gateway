"""Identity resolution and the multiple-external-identities rules, as
`01-sessions-and-identity-resolution.md` states them: what `core.external_identities` stores, the
`(issuer, subject)` lookup key, the derived `provider` and `provider_uid` metadata, the two
uniqueness rules, and the identity lifecycle state.
"""

from uuid import UUID, uuid4

import pytest

import nativespeaker.api.auth.external_identities as ei_module
from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, barrier_result_for
from nativespeaker.api.auth.external_identities import (
    IDENTITY_LOOKUP_KEY,
    IDENTITY_STATE_CHANGING_FLOWS,
    PROVIDER_CONFLICT_MUTATIONS,
    RESERVATION_INDEX_COLUMNS,
    RESERVATION_INDEX_PREDICATE,
    ExternalIdentities,
    ExternalIdentityRow,
    IdentityAlreadyLinkedError,
    IdentityError,
    IdentityFieldSource,
    IdentityState,
    ProviderClassificationError,
    ProviderSource,
    ProviderUidSource,
    assert_lookup_fields,
    assert_provider_source,
    assert_provider_uid_check,
    assert_provider_uid_source,
    assert_reservation_index,
    authorizes,
    classify_provider,
    create_account,
    identity_key,
    in_reservation_scope,
    matches_identity,
    provider_account_conflict,
    provider_uid_for,
    retire,
    transition_identity_state,
    upgrade_to_registered,
    write_provider_uid,
)
from nativespeaker.api.auth.invariants import (
    ProviderAccountAlreadyLinkedError,
    ProviderAccountReservations,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider

ISSUER = "https://securetoken.google.com/test-project"


def identity_row(*,
                 user_id: UUID | None = None,
                 subject: str = "sub-1",
                 provider: IdentityProvider = IdentityProvider.anonymous,
                 provider_uid: str | None = None,
                 identity_state: IdentityState = IdentityState.active) -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid4(),
                               user_id=user_id or uuid4(),
                               issuer=ISSUER,
                               subject=subject,
                               provider=provider,
                               provider_uid=provider_uid,
                               identity_state=identity_state)


def provider_data(provider_id: str, uid: str) -> list[dict[str, str]]:
    """One Firebase Admin `providerData` entry, in the shape the Admin SDK hands back."""
    return [{"providerId": provider_id, "uid": uid}]


class TestIdentityLookup:
    # [utest->req~sessions-identity-lookup-fields~1]
    def test_lookup_is_by_issuer_and_subject_and_nothing_else(self):
        assert IDENTITY_LOOKUP_KEY == ("issuer", "subject")
        assert_lookup_fields(("subject", "issuer"))
        for wrong in (("subject",), ("issuer",), ("issuer", "email"),
                      ("issuer", "subject", "provider"), ()):
            with pytest.raises(IdentityError):
                assert_lookup_fields(wrong)

    # [utest->req~sessions-identity-lookup-fields~1]
    def test_the_stored_pair_matches_exactly(self):
        row = identity_row(subject="Sub-1")
        assert matches_identity(row, ISSUER, "Sub-1") is True
        # Neither half is trimmed, case-folded or defaulted.
        assert matches_identity(row, ISSUER, "sub-1") is False
        assert matches_identity(row, ISSUER.upper(), "Sub-1") is False

    # [utest->req~sessions-derivation-sources-for-identity-fields~1]
    def test_issuer_and_subject_come_only_from_the_verified_token(self):
        assert identity_key(ISSUER, "sub-1",
                            source=IdentityFieldSource.verified_id_token) == (ISSUER, "sub-1")
        for source in (IdentityFieldSource.request_header, IdentityFieldSource.cookie,
                       IdentityFieldSource.client_field, IdentityFieldSource.transport_metadata):
            with pytest.raises(IdentityError):
                identity_key(ISSUER, "sub-1", source=source)

    # [utest->req~sessions-derivation-sources-for-identity-fields~1]
    def test_provider_and_provider_uid_come_only_from_the_provider_data_read(self):
        assert_provider_source(ProviderSource.firebase_admin_provider_data)
        for source in (ProviderSource.client_declaration, ProviderSource.token_claim,
                       ProviderSource.request_header, ProviderSource.stored_profile_data):
            with pytest.raises(ProviderClassificationError):
                assert_provider_source(source)
        assert_provider_uid_source(ProviderUidSource.firebase_provider_data)
        for uid_source in (ProviderUidSource.client_input, ProviderUidSource.request_header,
                           ProviderUidSource.token_claim, ProviderUidSource.email,
                           ProviderUidSource.display_name):
            with pytest.raises(IdentityError):
                assert_provider_uid_source(uid_source)


class TestProviderMetadata:
    # [utest->req~sessions-provider-allowed-values~1]
    def test_the_allowed_provider_values_are_exactly_three(self):
        assert {member.value for member in IdentityProvider} == {"anonymous", "google", "apple"}

    # [utest->req~sessions-provider-and-provider-uid-metadata~1]
    def test_provider_uid_is_the_provider_side_identifier_and_null_for_anonymous(self):
        assert provider_uid_for(IdentityProvider.anonymous, []) is None
        assert provider_uid_for(IdentityProvider.google,
                                provider_data("google.com", "g-1")) == "g-1"
        assert provider_uid_for(IdentityProvider.apple,
                                provider_data("apple.com", "a-1")) == "a-1"
        # The row's own check keeps the two fields consistent with the identity kind.
        assert_provider_uid_check(IdentityProvider.anonymous, None)
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.anonymous, "g-1")
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.google, None)
        with pytest.raises(IdentityError):
            assert_provider_uid_check(IdentityProvider.google, "")

    # [utest->req~sessions-provider-stored-as-enum~1]
    def test_provider_is_stored_as_the_schema_enum_never_free_text(self):
        with pytest.raises(IdentityError):
            ExternalIdentityRow(id=uuid4(), user_id=uuid4(), issuer=ISSUER, subject="sub-1",
                                provider="google", provider_uid="g-1")  # ty: ignore[invalid-argument-type]
        stored = classify_provider(provider_data("google.com", "g-1"))
        assert isinstance(stored, IdentityProvider)
        assert identity_row(provider=stored, provider_uid="g-1").provider \
            is IdentityProvider.google


class TestUniqueness:
    # [utest->req~sessions-issuer-subject-unique~1]
    # [utest->req~sessions-unique-issuer-subject-kept~1]
    def test_the_pair_is_unique_across_anonymous_and_registered_rows_alike(self):
        store = ExternalIdentities()
        store.link(identity_row(subject="sub-1"))
        with pytest.raises(IdentityAlreadyLinkedError):
            store.link(identity_row(subject="sub-1"))
        with pytest.raises(IdentityAlreadyLinkedError):
            store.link(identity_row(subject="sub-1", provider=IdentityProvider.google,
                                    provider_uid="g-1"))
        # A different subject under the same issuer is a different identity.
        assert store.link(identity_row(subject="sub-2")).subject == "sub-2"

    # [utest->req~sessions-unique-user-id~1]
    # [utest->req~sessions-one-user-one-identity-row~1]
    def test_unique_user_id_caps_a_user_at_one_identity_row(self):
        store = ExternalIdentities()
        owner = uuid4()
        store.link(identity_row(user_id=owner, subject="sub-1"))
        with pytest.raises(IdentityError):
            store.link(identity_row(user_id=owner, subject="sub-2"))
        assert store.find(ISSUER, "sub-2") is None

    # [utest->req~sessions-one-user-one-identity-row~1]
    # [utest->req~sessions-account-creation-single-transaction~1]
    def test_the_user_row_and_its_identity_row_are_created_in_one_transaction(self):
        transaction = object()
        owner = uuid4()
        created = create_account(user_id=owner, identity=identity_row(user_id=owner),
                                 user_transaction=transaction,
                                 identity_transaction=transaction)
        assert created.transaction is transaction
        # Two transactions do not satisfy the rule: a failure of either insert must leave no
        # account at all.
        with pytest.raises(IdentityError):
            create_account(user_id=owner, identity=identity_row(user_id=owner),
                           user_transaction=transaction, identity_transaction=object())
        # And a user that already has an identity row never gets a second one.
        with pytest.raises(IdentityError):
            create_account(user_id=owner, identity=identity_row(user_id=owner),
                           user_transaction=transaction, identity_transaction=transaction,
                           existing_identity_for_user=identity_row(user_id=owner))

    # [utest->req~sessions-provider-account-reservation-unique~1]
    def test_one_provider_account_maps_to_at_most_one_user(self):
        reservations = ProviderAccountReservations()
        owner = uuid4()
        reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                          provider=IdentityProvider.google, provider_uid="g-1", user_id=owner)
        with pytest.raises(ProviderAccountAlreadyLinkedError):
            reservations.bind(operation=AuthOperation.upgrade_anonymous_to_registered,
                              issuer=ISSUER, provider=IdentityProvider.google,
                              provider_uid="g-1", user_id=uuid4())
        assert reservations.holder(ISSUER, IdentityProvider.google, "g-1") == owner

    # [utest->req~sessions-provider-account-reservation-unique~1]
    def test_the_reservation_is_the_partial_index_and_spans_historical_rows(self):
        assert_reservation_index(columns=RESERVATION_INDEX_COLUMNS,
                                 predicate=RESERVATION_INDEX_PREDICATE)
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=RESERVATION_INDEX_COLUMNS,
                                     predicate=RESERVATION_INDEX_PREDICATE,
                                     table_wide_unique=True)
        with pytest.raises(IdentityError):
            assert_reservation_index(columns=("provider", "provider_uid"),
                                     predicate=RESERVATION_INDEX_PREDICATE)
        # Retirement does not free the provider account, and an anonymous row is outside the
        # index entirely — no sentinel `provider_uid` is invented for it.
        registered = identity_row(provider=IdentityProvider.google, provider_uid="g-1")
        assert in_reservation_scope(registered) is True
        assert in_reservation_scope(retire(registered)) is True
        assert in_reservation_scope(identity_row()) is False

    # [utest->req~sessions-provider-account-reservation-unique~1]
    def test_provider_uid_is_persisted_in_the_transition_transaction(self):
        transaction = object()
        row = identity_row()
        bound = write_provider_uid(row, "g-1", provider=IdentityProvider.google,
                                   row_transaction=transaction, uid_transaction=transaction)
        assert (bound.provider, bound.provider_uid) == (IdentityProvider.google, "g-1")
        with pytest.raises(IdentityError):
            write_provider_uid(row, "g-1", provider=IdentityProvider.google,
                               row_transaction=transaction, uid_transaction=object())

    # [utest->req~sessions-provider-account-reservation-unique~1]
    def test_a_conflict_rejects_the_operation_and_mutates_nothing(self):
        error = provider_account_conflict(AuthOperation.create_user)
        assert error.result is AuthEventResult.provider_account_already_linked
        assert PROVIDER_CONFLICT_MUTATIONS == frozenset()
        with pytest.raises(IdentityError):
            provider_account_conflict(AuthOperation.sync)


class TestIdentityLifecycleState:
    # [utest->req~sessions-identity-lifecycle-state-added~1]
    def test_an_identity_is_active_or_historical(self):
        assert {member.value for member in IdentityState} == {"active", "historical"}
        assert identity_row().identity_state is IdentityState.active
        assert retire(identity_row()).identity_state is IdentityState.historical
        with pytest.raises(IdentityError):
            ExternalIdentityRow(id=uuid4(), user_id=uuid4(), issuer=ISSUER, subject="sub-1",
                                provider=IdentityProvider.anonymous,
                                identity_state="retired")  # ty: ignore[invalid-argument-type]

    # [utest->req~sessions-historical-retention-administrative~1]
    def test_historical_is_reached_only_by_an_administrative_action(self):
        assert transition_identity_state(IdentityState.active, IdentityState.historical,
                                         administrative=True) is IdentityState.historical
        with pytest.raises(IdentityError):
            transition_identity_state(IdentityState.active, IdentityState.historical,
                                      administrative=False)
        with pytest.raises(IdentityError):
            retire(identity_row(), administrative=False)

    # [utest->req~sessions-no-user-driven-historical~1]
    def test_no_user_driven_flow_marks_an_identity_historical(self):
        assert IDENTITY_STATE_CHANGING_FLOWS == frozenset()
        # The retirement transition refuses to run at all while any flow claims to change the
        # state on its own.
        original = ei_module.IDENTITY_STATE_CHANGING_FLOWS
        ei_module.IDENTITY_STATE_CHANGING_FLOWS = frozenset({"auth_sync"})
        try:
            with pytest.raises(IdentityError):
                transition_identity_state(IdentityState.active, IdentityState.historical,
                                          administrative=True)
        finally:
            ei_module.IDENTITY_STATE_CHANGING_FLOWS = original

    # [utest->req~sessions-historical-no-api-access~1]
    def test_a_historical_identity_authorizes_no_authenticated_api_access(self):
        assert authorizes(IdentityState.active) is True
        assert authorizes(IdentityState.historical) is False
        # Per-request resolution is where that answer is enforced, on every route including the
        # pre-auth-callable one.
        for method, path in (("POST", "/auth/sync"), ("GET", "/users/me"),
                             ("POST", "/auth/create-user")):
            assert barrier_result_for(ResolutionOutcome.historical_identity, method, path) \
                is AuthEventResult.historical_identity

    # [utest->req~sessions-in-place-flip-no-historical-rows~1]
    def test_the_in_place_upgrade_produces_no_historical_row(self):
        transaction = object()
        anonymous = identity_row()
        upgraded = upgrade_to_registered(anonymous, provider=IdentityProvider.google,
                                         provider_uid="g-1", transaction=transaction)
        assert (upgraded.id, upgraded.user_id) == (anonymous.id, anonymous.user_id)
        assert upgraded.identity_state is IdentityState.active
        assert (upgraded.provider, upgraded.provider_uid) == (IdentityProvider.google, "g-1")
        # The store still holds exactly one row for the pair, and it is the same row.
        store = ExternalIdentities()
        store.link(anonymous)
        store.replace_row(upgraded)
        found = store.find(ISSUER, anonymous.subject)
        assert found is not None
        assert found.id == anonymous.id
        assert found.identity_state is IdentityState.active
