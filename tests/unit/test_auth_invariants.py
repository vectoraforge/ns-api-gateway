"""The cross-cutting invariants of the shared contracts file, and the fixed grant/usage lock
order they all depend on."""

from uuid import uuid7

import pytest
from fastapi.testclient import TestClient

import nativespeaker.api.auth.invariants as invariants
from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.invariants import (
    CROSS_CUTTING_INVARIANTS,
    DEVICE_CHECK_MECHANISM,
    DISTINCT_FAILURE_CLASSES,
    ENUM_TYPED_FIELDS,
    AttributionSource,
    AttributionTokens,
    DevicePlatform,
    GateAlreadyConsumedError,
    GateConsumptionKind,
    GrantCreator,
    InvariantError,
    ProofUse,
    ProviderAccount,
    ProviderAccountAlreadyLinkedError,
    ProviderAccountGates,
    ProviderAccountReservations,
    StoreProvider,
    assert_attribution_source,
    assert_device_check_proof_use,
    assert_grant_columns_entitlement_only,
    assert_grant_creator,
    assert_owner_agreement,
    assert_provider_uid_immutable,
    assert_same_transaction,
    assert_stated_here,
    normative_home,
    provider_uid_from_provider_data,
    provider_uid_reserved,
    rejected_at_resolution,
    requires_anti_abuse_row,
)
from nativespeaker.api.auth.locks import (
    ExternalCallUnderLockError,
    LockingPath,
    LockLedger,
    LockOrderError,
    lock_grant_set,
    takes_user_row_lock,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.taxonomy import REMEDIATIONS, ClientErrorClass
from unit.conftest import make_token
from unit.test_auth_barrier import FakeResolver, RecordingSink, build_app, make_writer

ISSUER = "https://securetoken.google.com/test-project"


def ids(count: int) -> list:
    """Ascending row ids: uuid7 is time-ordered, so successive calls sort in creation order."""
    return sorted(uuid7() for _ in range(count))


class TestScope:
    # The scope statement is impl-only; this guards the partition it defines.
    def test_referenced_invariants_name_their_normative_home(self):
        assert len(CROSS_CUTTING_INVARIANTS) == 12
        assert normative_home(2) == "req~schema-invariant-03~1"
        assert normative_home(4) == "req~schema-invariant-08~1"
        assert normative_home(8) == "req~schema-invariant-11~1"
        assert normative_home(9) == "req~schema-invariant-14~1"
        assert normative_home(1) is None
        with pytest.raises(InvariantError):
            assert_stated_here(2)
        assert_stated_here(1)


class TestGrantCreators:
    # [utest->req~shared-invariant-01~2]
    @pytest.mark.parametrize(("creator", "source"), [
        (GrantCreator.claim_anonymous_grant, AccessGrantSource.anonymous_device_grant),
        (GrantCreator.claim_registered_grant, AccessGrantSource.registered_account_grant),
        (GrantCreator.manual_issuance, AccessGrantSource.manual),
        (GrantCreator.purchase_ingestion, AccessGrantSource.subscription),
        (GrantCreator.renewal_term_insert, AccessGrantSource.subscription),
        (GrantCreator.restore_adoption, AccessGrantSource.subscription),
    ])
    def test_each_enumerated_creator_owns_its_source(self, creator, source):
        assert_grant_creator(creator, source)

    # [utest->req~shared-invariant-01~2]
    def test_no_other_path_creates_a_grant(self):
        with pytest.raises(InvariantError):
            assert_grant_creator("sync", AccessGrantSource.manual)
        with pytest.raises(InvariantError):
            assert_grant_creator("subscription_webhook_side_effect",
                                 AccessGrantSource.subscription)

    # [utest->req~shared-invariant-01~2]
    def test_a_creator_cannot_produce_another_creators_source(self):
        with pytest.raises(InvariantError):
            assert_grant_creator(GrantCreator.claim_anonymous_grant,
                                 AccessGrantSource.registered_account_grant)
        with pytest.raises(InvariantError):
            assert_grant_creator(GrantCreator.restore_adoption,
                                 AccessGrantSource.anonymous_device_grant)


class TestHistoricalIdentity:
    # [utest->req~shared-invariant-03~1]
    def test_a_historical_identity_is_rejected_at_resolution(self):
        assert rejected_at_resolution(ResolutionOutcome.historical_identity) \
            is AuthEventResult.historical_identity
        assert rejected_at_resolution(ResolutionOutcome.linked) is None

    # [utest->req~shared-invariant-03~1]
    def test_every_subsequent_request_for_that_identity_is_rejected(self):
        sink = RecordingSink()
        resolver = FakeResolver(ResolutionOutcome.historical_identity)
        app = build_app([("GET", "/users/me"), ("POST", "/auth/sync")],
                        resolver=resolver, writer=make_writer(sink=sink))
        headers = {"Authorization": f"Bearer {make_token('retired-uid')}"}
        with TestClient(app, raise_server_exceptions=False) as client:
            first = client.get("/users/me", headers=headers)
            second = client.post("/auth/sync", headers=headers)
        assert [first.status_code, second.status_code] == [403, 403]
        assert first.json()["code"] == "account_unavailable"
        # Both requests reached per-request resolution; neither reached a handler.
        assert len(resolver.seen) == 2
        assert [row["result"] for row in sink.rows] == [AuthEventResult.historical_identity]


class TestEnumTypedFields:
    # Reference item: the rule is `req~schema-invariant-03~1`.
    def test_authorization_relevant_fields_name_their_enum(self):
        assert ENUM_TYPED_FIELDS["core.external_identities.provider"] is IdentityProvider
        assert ENUM_TYPED_FIELDS["audit.auth_events.actor_provider"] is IdentityProvider
        assert ENUM_TYPED_FIELDS["core.access_grants.source"] is AccessGrantSource


class TestEntitlementOnlyGrantRow:
    # [utest->req~shared-invariant-05~1]
    def test_every_platform_has_its_own_device_check_mechanism(self):
        assert DEVICE_CHECK_MECHANISM[DevicePlatform.ios] == "apple_devicecheck"
        assert DEVICE_CHECK_MECHANISM[DevicePlatform.android] == "play_integrity_device_recall"
        assert DEVICE_CHECK_MECHANISM[DevicePlatform.web] == \
            "signin_plus_server_validated_bot_check"
        assert len(set(DEVICE_CHECK_MECHANISM.values())) == 3

    # [utest->req~shared-invariant-05~1]
    @pytest.mark.parametrize("use", [ProofUse.identity, ProofUse.ownership, ProofUse.recovery,
                                     ProofUse.upgrade, ProofUse.account_resolution])
    def test_a_device_check_proof_is_no_credential_and_resolves_no_account(self, use):
        with pytest.raises(InvariantError):
            assert_device_check_proof_use(use)
        assert_device_check_proof_use(ProofUse.anti_abuse_gate)

    # [utest->req~shared-invariant-05~1]
    def test_device_check_state_is_not_stored_on_the_grant_row(self):
        assert_grant_columns_entitlement_only(["id", "user_id", "source", "status"])
        with pytest.raises(InvariantError):
            assert_grant_columns_entitlement_only(["id", "source", "device_check_state"])
        with pytest.raises(InvariantError):
            assert_grant_columns_entitlement_only(["id", "device_principal_hash"])

    # Reference item: the pairing rule is `req~schema-invariant-08~1`.
    def test_only_the_two_free_sources_pair_with_an_anti_abuse_row(self):
        assert requires_anti_abuse_row(AccessGrantSource.anonymous_device_grant)
        assert requires_anti_abuse_row(AccessGrantSource.registered_account_grant)
        assert not requires_anti_abuse_row(AccessGrantSource.subscription)
        assert not requires_anti_abuse_row(AccessGrantSource.manual)


class TestDistinctFailureClasses:
    # [utest->req~shared-invariant-06~1]
    def test_durable_exhaustion_a_gate_and_an_outage_are_three_classes(self):
        assert set(DISTINCT_FAILURE_CLASSES) == {
            ClientErrorClass.device_grant_exhausted,
            ClientErrorClass.verification_required,
            ClientErrorClass.verification_temporarily_unavailable,
        }
        # Three classes, three remediations: none of them can be collapsed into another, which
        # is the whole content of this invariant.
        actions = [REMEDIATIONS[klass].action for klass in DISTINCT_FAILURE_CLASSES]
        assert len(set(actions)) == len(actions)
        assert REMEDIATIONS[ClientErrorClass.verification_temporarily_unavailable].transient
        assert not REMEDIATIONS[ClientErrorClass.device_grant_exhausted].transient
        assert not REMEDIATIONS[ClientErrorClass.verification_required].transient

    # [utest->req~shared-invariant-06~1]
    def test_the_selection_rule_lives_with_the_grant_material_not_here(self):
        # Which internal result maps to which of the three classes, and the rule that a
        # transient failure is never surfaced as a durable class unless durable state was
        # independently observed, belong to the grant material. This module owns only the
        # distinctness above, so it exposes no second decider for anyone to drift from.
        assert not [name for name in dir(invariants)
                   if "failure_class" in name and not name.startswith("_assert")]


class TestProviderAccountGates:
    # [utest->req~shared-invariant-07~1]
    def test_one_registered_free_credit_claim_per_provider_account(self):
        gates = ProviderAccountGates()
        account = ProviderAccount(IdentityProvider.google, "google-uid-1")
        gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
        with pytest.raises(GateAlreadyConsumedError) as excinfo:
            gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
        assert excinfo.value.result is AuthEventResult.idp_account_already_claimed
        assert excinfo.value.client_class is ClientErrorClass.account_already_claimed

    # [utest->req~shared-invariant-07~1]
    def test_the_gate_is_keyed_on_the_stable_uid_so_a_hash_rotation_never_reopens_it(self):
        gates = ProviderAccountGates()
        account = ProviderAccount(IdentityProvider.apple, "apple-uid-1")
        gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7(),
                      idp_account_hash=b"\x01" * 32, hash_key_version=1)
        assert gates.alias(account, GateConsumptionKind.registered_account_grant) \
            == (b"\x01" * 32, 1)
        # A rotated hash key produces a different alias but the same stable UID: still closed.
        with pytest.raises(GateAlreadyConsumedError):
            gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7(),
                          idp_account_hash=b"\x02" * 32, hash_key_version=2)

    # [utest->req~shared-invariant-07~1]
    def test_the_two_consumption_kinds_are_distinct_rows(self):
        gates = ProviderAccountGates()
        account = ProviderAccount(IdentityProvider.google, "google-uid-2")
        grant = uuid7()
        gates.consume(account, GateConsumptionKind.registered_account_grant, grant)
        gates.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())
        assert gates.consumed_grant(account, GateConsumptionKind.registered_account_grant) == grant

    # [utest->req~shared-invariant-07~1]
    def test_a_different_provider_account_is_a_different_gate(self):
        gates = ProviderAccountGates()
        gates.consume(ProviderAccount(IdentityProvider.google, "uid"),
                      GateConsumptionKind.registered_account_grant, uuid7())
        gates.consume(ProviderAccount(IdentityProvider.apple, "uid"),
                      GateConsumptionKind.registered_account_grant, uuid7())

    # [utest->req~shared-invariant-07~1]
    def test_a_registered_gate_conflict_is_not_a_device_grant_block(self):
        registered = ClientErrorClass.account_already_claimed
        device = ClientErrorClass.device_grant_exhausted
        assert registered is not device
        assert AuthEventResult.idp_account_already_claimed \
            is not AuthEventResult.native_claim_already_claimed


class TestOwnerAgreementReference:
    # Reference item: the rule is `req~schema-invariant-11~1`.
    def test_a_grant_and_its_subscription_share_one_owner(self):
        owner = uuid7()
        assert_owner_agreement(grant_user_id=owner, subscription_user_id=owner)
        with pytest.raises(InvariantError):
            assert_owner_agreement(grant_user_id=owner, subscription_user_id=uuid7())


class TestSameTransactionReference:
    # Reference item: the rule is `req~schema-invariant-14~1` (final paragraph).
    def test_a_deferred_constraint_path_writes_its_rows_in_one_transaction(self):
        session = object()
        assert_same_transaction("restore_subscription", [session, session])
        with pytest.raises(InvariantError):
            assert_same_transaction("restore_subscription", [session, object()])
        with pytest.raises(InvariantError):
            assert_same_transaction("sign_out_all", [session])


class TestPurchaseAttribution:
    # [utest->req~shared-invariant-10~1]
    def test_one_lifetime_token_per_user_per_store(self):
        tokens = AttributionTokens()
        user = uuid7()
        tokens.mint(user, StoreProvider.apple, "apple-token")
        tokens.mint(user, StoreProvider.google_play, "play-token")
        assert tokens.token_for(user, StoreProvider.apple) == "apple-token"
        with pytest.raises(InvariantError):
            tokens.mint(user, StoreProvider.apple, "apple-token-2")

    # [utest->req~shared-invariant-10~1]
    def test_attribution_is_keyed_by_store_and_token_alone(self):
        tokens = AttributionTokens()
        owner = uuid7()
        tokens.mint(owner, StoreProvider.apple, "shared-value")
        other = uuid7()
        tokens.mint(other, StoreProvider.google_play, "shared-value")
        assert tokens.owner_of(StoreProvider.apple, "shared-value") == owner
        assert tokens.owner_of(StoreProvider.google_play, "shared-value") == other
        assert tokens.owner_of(StoreProvider.apple, "unknown") is None

    # [utest->req~shared-invariant-10~1]
    def test_one_store_token_binds_to_one_user_only(self):
        # The binding is keyed by the store provider and that token, so a token already bound
        # to one user is never rebound: verified-purchase ingestion resolving through it must
        # never find a second owner.
        tokens = AttributionTokens()
        owner, thief = uuid7(), uuid7()
        tokens.mint(owner, StoreProvider.apple, "tok")
        with pytest.raises(InvariantError):
            tokens.mint(thief, StoreProvider.apple, "tok")
        assert tokens.owner_of(StoreProvider.apple, "tok") == owner
        assert tokens.token_for(thief, StoreProvider.apple) is None

    # [utest->req~shared-invariant-10~1]
    def test_attribution_never_comes_from_the_request_identity(self):
        assert_attribution_source(AttributionSource.store_echoed_token)
        assert_attribution_source(AttributionSource.restore_insert_once)
        with pytest.raises(InvariantError):
            assert_attribution_source(AttributionSource.request_authenticated_identity)
        with pytest.raises(InvariantError):
            assert_attribution_source(AttributionSource.client_asserted_identity)


class TestProviderAccountBinding:
    # [utest->req~shared-invariant-11~1]
    def test_provider_uid_comes_only_from_the_matching_provider_data_entry(self):
        data = [{"provider_id": "google.com", "uid": "g-1", "email": "a@example.com"},
                {"provider_id": "password", "uid": "ignored"}]
        assert provider_uid_from_provider_data(IdentityProvider.google, data) == "g-1"
        assert provider_uid_from_provider_data(IdentityProvider.anonymous, data) is None
        with pytest.raises(InvariantError):
            provider_uid_from_provider_data(IdentityProvider.apple, data)
        with pytest.raises(InvariantError):
            provider_uid_from_provider_data(
                IdentityProvider.google, [{"provider_id": "google.com", "uid": ""}])

    # [utest->req~shared-invariant-11~1]
    def test_provider_uid_is_immutable_once_assigned(self):
        assert_provider_uid_immutable("g-1", "g-1")
        assert_provider_uid_immutable(None, "g-1")
        with pytest.raises(InvariantError):
            assert_provider_uid_immutable("g-1", "g-2")

    # [utest->req~shared-invariant-11~1]
    def test_the_reservation_covers_registered_rows_only(self):
        assert provider_uid_reserved(IdentityProvider.google, "g-1")
        assert provider_uid_reserved(IdentityProvider.apple, "a-1")
        assert not provider_uid_reserved(IdentityProvider.anonymous, None)

    # [utest->req~shared-invariant-11~1]
    def test_one_provider_account_binds_to_one_user_and_a_conflict_mutates_nothing(self):
        reservations = ProviderAccountReservations()
        owner = uuid7()
        reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                          provider=IdentityProvider.google, provider_uid="g-1", user_id=owner)
        with pytest.raises(ProviderAccountAlreadyLinkedError) as excinfo:
            reservations.bind(operation=AuthOperation.upgrade_anonymous_to_registered,
                              issuer=ISSUER, provider=IdentityProvider.google,
                              provider_uid="g-1", user_id=uuid7())
        assert excinfo.value.result is AuthEventResult.provider_account_already_linked
        assert excinfo.value.client_class is ClientErrorClass.operation_not_allowed
        assert reservations.holder(ISSUER, IdentityProvider.google, "g-1") == owner

    # [utest->req~shared-invariant-11~1]
    def test_retiring_an_identity_never_frees_its_provider_account(self):
        reservations = ProviderAccountReservations()
        owner = uuid7()
        reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                          provider=IdentityProvider.apple, provider_uid="a-1", user_id=owner)
        reservations.retire(issuer=ISSUER, provider=IdentityProvider.apple, provider_uid="a-1")
        assert reservations.is_historical(ISSUER, IdentityProvider.apple, "a-1")
        with pytest.raises(ProviderAccountAlreadyLinkedError):
            reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                              provider=IdentityProvider.apple, provider_uid="a-1",
                              user_id=uuid7())

    # [utest->req~shared-invariant-11~1]
    def test_an_anonymous_row_is_never_constrained_by_the_index(self):
        reservations = ProviderAccountReservations()
        for _ in range(2):
            reservations.bind(operation=AuthOperation.create_user, issuer=ISSUER,
                              provider=IdentityProvider.anonymous, provider_uid=None,
                              user_id=uuid7())

    # [utest->req~shared-invariant-11~1]
    def test_only_the_provider_binding_operations_reserve(self):
        reservations = ProviderAccountReservations()
        with pytest.raises(InvariantError):
            reservations.bind(operation=AuthOperation.restore_subscription, issuer=ISSUER,
                              provider=IdentityProvider.google, provider_uid="g-9",
                              user_id=uuid7())


class TestLockOrder:
    # [utest->req~shared-invariant-12~1]
    def test_the_owning_grant_is_locked_before_its_usage_row(self):
        grant = uuid7()
        ledger = LockLedger(LockingPath.lazy_monthly_rollover)
        with pytest.raises(LockOrderError):
            ledger.lock_usage(grant)
        ledger.lock_grant(grant)
        ledger.lock_usage(grant)
        assert ledger.grant_locks == (grant,) and ledger.usage_locks == (grant,)

    # [utest->req~shared-invariant-12~1]
    def test_a_usage_lock_is_never_followed_by_a_grant_lock(self):
        first, second = ids(2)
        ledger = LockLedger(LockingPath.restore_mutation)
        ledger.lock_grant(first)
        ledger.lock_usage(first)
        with pytest.raises(LockOrderError):
            ledger.lock_grant(second)

    # [utest->req~shared-invariant-12~1]
    def test_several_grants_are_locked_in_ascending_id_order(self):
        first, second, third = ids(3)
        ledger = LockLedger(LockingPath.manual_issuance)
        lock_grant_set(ledger, [third, first, second])
        assert ledger.grant_locks == (first, second, third)
        assert ledger.usage_locks == (first, second, third)

        out_of_order = LockLedger(LockingPath.manual_issuance)
        out_of_order.lock_grant(second)
        with pytest.raises(LockOrderError):
            out_of_order.lock_grant(first)

    # [utest->req~shared-invariant-12~1]
    def test_usage_rows_follow_the_same_ascending_order_as_their_grants(self):
        first, second = ids(2)
        ledger = LockLedger(LockingPath.claim_anonymous_grant_completion)
        ledger.lock_grant(first)
        ledger.lock_grant(second)
        ledger.lock_usage(second)
        with pytest.raises(LockOrderError):
            ledger.lock_usage(first)

    # [utest->req~shared-invariant-12~1]
    def test_no_external_call_runs_while_the_locks_are_held(self):
        grant = uuid7()
        ledger = LockLedger(LockingPath.restore_mutation)
        ledger.external_call("apple_verify_transaction")
        ledger.lock_grant(grant)
        ledger.lock_usage(grant)
        with pytest.raises(ExternalCallUnderLockError):
            ledger.external_call("apple_verify_transaction")
        ledger.commit()
        ledger.external_call("apple_verify_transaction")

    # [utest->req~shared-invariant-12~1]
    def test_restore_and_the_rollover_take_no_user_row_lock(self):
        for path in (LockingPath.restore_mutation, LockingPath.lazy_monthly_rollover):
            assert not takes_user_row_lock(path)
            with pytest.raises(LockOrderError):
                LockLedger(path).lock_user(uuid7())

    # [utest->req~shared-invariant-12~1]
    def test_the_grant_procedures_lock_the_user_first_then_the_grant_set(self):
        first, second = ids(2)
        for path in (LockingPath.claim_anonymous_grant_completion,
                     LockingPath.claim_registered_grant_completion,
                     LockingPath.manual_issuance):
            assert takes_user_row_lock(path)
            ledger = LockLedger(path)
            ledger.lock_user(uuid7())
            lock_grant_set(ledger, [second, first])
            assert ledger.grant_locks == (first, second)
            # The user row is never locked after a grant row.
            with pytest.raises(LockOrderError):
                ledger.lock_user(uuid7())

    # [utest->req~shared-invariant-12~1]
    def test_a_path_added_later_takes_the_same_fixed_order(self):
        # Every declared path is bound: none of them can take a usage lock first.
        for path in LockingPath:
            with pytest.raises(LockOrderError):
                LockLedger(path).lock_usage(uuid7())
