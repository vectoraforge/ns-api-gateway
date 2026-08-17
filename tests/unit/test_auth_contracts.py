"""Shared auth contracts: the operation inventory, the audited attempt path, the mode-signal
partition, operation variants, endpoint dispatch, introductory entitlement, and ownership keys."""

import pytest
from sqlalchemy import Column, ForeignKey, MetaData, String, Table
from sqlmodel import SQLModel

import nativespeaker.api.models  # noqa: F401  (registers the mapped tables)
from nativespeaker.api.auth.audit import AttemptPhase, AuthAttempt, AuthEventResult, terminal_event
from nativespeaker.api.auth.entitlement import (
    INTRODUCTORY_GRANT_SOURCES,
    AccessGrantSource,
    GrantMutation,
    IntroductoryEntitlementError,
    allocates_introductory_entitlement,
    guard_grant_mutation,
)
from nativespeaker.api.auth.flow import (
    ChallengeScopeError,
    OperationMismatchError,
    assert_challenge_bearing,
    dispatch_state_changing,
)
from nativespeaker.api.auth.modes import (
    ModeSignalDefect,
    ModeSignalError,
    RequestMode,
    classify_mode,
)
from nativespeaker.api.auth.operations import (
    CHALLENGE_BEARING_OPERATIONS,
    FREE_GRANT_DEVICE_BIT_BUDGETS,
    OPERATION_INVENTORY,
    AdmissionRejection,
    AuthOperation,
    IdentityProvider,
    InvalidOperationVariantError,
    is_admission_phase,
    is_on_audited_path,
    match_operation,
    normalize_variant,
    requires_attempt_audit,
    supports_prepare,
    variants_for,
)
from nativespeaker.api.auth.ownership import ownership_violations

EXPECTED_INVENTORY = {
    ("POST", "/auth/create-user", AuthOperation.create_user, True),
    ("POST", "/auth/upgrade-anonymous", AuthOperation.upgrade_anonymous_to_registered, True),
    ("POST", "/auth/claim-anonymous-grant", AuthOperation.claim_anonymous_grant, True),
    ("POST", "/auth/claim-registered-grant", AuthOperation.claim_registered_grant, True),
    ("POST", "/auth/restore-subscription", AuthOperation.restore_subscription, False),
    ("POST", "/auth/sign-out-all", AuthOperation.sign_out_all, False),
    ("POST", "/auth/sync", AuthOperation.sync, False),
}


class TestOperationInventory:
    # [utest->req~shared-operation-inventory-table~1]
    def test_inventory_is_the_seven_canonical_rows(self):
        assert {(e.method, e.path, e.operation, e.challenge_bearing)
                for e in OPERATION_INVENTORY} == EXPECTED_INVENTORY
        assert len(OPERATION_INVENTORY) == 7
        assert set(AuthOperation) == {row[2] for row in EXPECTED_INVENTORY}

    # [utest->req~shared-inventory-membership-authoritative~1]
    def test_membership_is_read_from_the_table_only(self):
        # In the table even though its handler mutates no business state, and even though it
        # only revokes refresh tokens.
        assert match_operation("POST", "/auth/sync") is AuthOperation.sync
        assert match_operation("POST", "/auth/sign-out-all") is AuthOperation.sign_out_all
        # Routine authenticated traffic: absent from the table.
        assert match_operation("GET", "/users/me") is None
        assert match_operation("POST", "/chats") is None
        # Never inferred from a path name, and never from the wrong method.
        assert match_operation("POST", "/auth/looks-official") is None
        assert match_operation("GET", "/auth/sync") is None

    # [utest->req~shared-challenge-bearing-subset~1]
    def test_only_the_four_marked_operations_are_challenge_bearing(self):
        assert CHALLENGE_BEARING_OPERATIONS == {AuthOperation.create_user,
                                                AuthOperation.upgrade_anonymous_to_registered,
                                                AuthOperation.claim_anonymous_grant,
                                                AuthOperation.claim_registered_grant}
        for operation in (AuthOperation.restore_subscription, AuthOperation.sign_out_all,
                          AuthOperation.sync):
            assert supports_prepare(operation) is False
            assert variants_for(operation) == ()
            with pytest.raises(ChallengeScopeError):
                assert_challenge_bearing(operation)

    # [utest->req~shared-inventory-obligations-bind-all-seven~1]
    def test_shared_obligations_bind_all_seven_operations(self):
        for entry in OPERATION_INVENTORY:
            assert is_on_audited_path(entry.method, entry.path) is True
            assert requires_attempt_audit(entry.operation) is True
        assert len(CHALLENGE_BEARING_OPERATIONS) == 4

    # [utest->req~shared-sync-canonical-operation~1]
    def test_sync_is_canonical_by_route_and_carries_no_challenge(self):
        assert is_on_audited_path("POST", "/auth/sync") is True
        assert requires_attempt_audit(AuthOperation.sync) is True
        assert supports_prepare(AuthOperation.sync) is False
        assert AuthOperation.sync not in CHALLENGE_BEARING_OPERATIONS
        # Its terminal outcome — a barrier rejection included — is one row for `sync`.
        event = terminal_event(AttemptPhase.barrier, AuthEventResult.blocked_user,
                               operation=AuthOperation.sync)
        assert event.operation is AuthOperation.sync
        # ... while `GET /users/me` is routine traffic, off the path.
        assert is_on_audited_path("GET", "/users/me") is False


class TestAuditedAttemptPath:
    # [utest->req~shared-audited-path-entry~1]
    def test_entry_is_the_matched_route_and_method_alone(self):
        attempt = AuthAttempt("POST", "/auth/claim-anonymous-grant")
        # Classified from route metadata, before the barrier has run anything.
        assert attempt.operation is AuthOperation.claim_anonymous_grant
        assert attempt.on_audited_path is True
        assert attempt.audited is False
        assert AuthAttempt("GET", "/auth/claim-anonymous-grant").on_audited_path is False
        assert AuthAttempt("GET", "/users/me").on_audited_path is False

    # [utest->req~shared-admission-phase-precedes-path~1]
    def test_admission_rejections_never_reach_the_path(self):
        for rejection in AdmissionRejection:
            if rejection is AdmissionRejection.provider_budget_exhausted:
                continue
            assert is_admission_phase(rejection) is True
        # The syntactic mode-signal check belongs to the admission phase.
        assert is_admission_phase(AdmissionRejection.mode_signal_invalid) is True

    # [utest->req~shared-admission-phase-precedes-path~1]
    def test_free_grant_device_bit_budgets_are_the_single_exception(self):
        assert len(FREE_GRANT_DEVICE_BIT_BUDGETS) == 4
        for budget in FREE_GRANT_DEVICE_BIT_BUDGETS:
            assert is_admission_phase(AdmissionRejection.provider_budget_exhausted,
                                      budget=budget) is False
        assert is_admission_phase(AdmissionRejection.provider_budget_exhausted,
                                  budget="adapter_firebase_lookup") is True


class TestModeSignalPartition:
    # [utest->req~shared-mode-prepare~1]
    def test_challenge_true_without_challenge_id_is_prepare(self):
        signal = classify_mode([("challenge", "true")], {"provider": "google"})
        assert signal.mode is RequestMode.prepare
        assert signal.challenge_id is None

    # [utest->req~shared-mode-completion~1]
    def test_challenge_id_without_challenge_true_is_completion(self):
        signal = classify_mode([], {"challenge_id": "abc"})
        assert signal.mode is RequestMode.completion
        assert signal.challenge_id == "abc"

    # [utest->req~shared-mode-invalid~1]
    # [utest->req~shared-mode-invalid-request-class~1]
    def test_both_signals_or_neither_is_invalid_request(self):
        with pytest.raises(ModeSignalError) as both:
            classify_mode([("challenge", "true")], {"challenge_id": "abc"})
        assert both.value.defect is ModeSignalDefect.both_signals
        with pytest.raises(ModeSignalError) as neither:
            classify_mode([], {"provider": "google"})
        assert neither.value.defect is ModeSignalDefect.neither_signal
        # One consistent answer, with the shared class and HTTP 400 -- never a silent
        # preference for either interpretation.
        for error in (both.value, neither.value):
            assert error.error_code == "invalid_request"
            assert error.status_code == 400

    # [utest->req~shared-no-implicit-prepare-mode~1]
    def test_missing_challenge_is_never_inferred_as_prepare(self):
        with pytest.raises(ModeSignalError) as exc:
            classify_mode([("other", "true")], {})
        assert exc.value.defect is ModeSignalDefect.neither_signal

    # [utest->req~shared-mode-malformed-shapes~1]
    @pytest.mark.parametrize(("query", "body", "defect"), [
        ([("challenge", "1")], {}, ModeSignalDefect.challenge_param_not_true),
        ([("challenge", "True")], {}, ModeSignalDefect.challenge_param_not_true),
        ([("challenge", "")], {}, ModeSignalDefect.challenge_param_not_true),
        ([("challenge", "true"), ("challenge", "true")], {},
         ModeSignalDefect.duplicate_challenge_param),
        ([], {"challenge_id": None}, ModeSignalDefect.malformed_challenge_id),
        ([], {"challenge_id": ""}, ModeSignalDefect.malformed_challenge_id),
        ([], {"challenge_id": 17}, ModeSignalDefect.malformed_challenge_id),
    ])
    def test_malformed_mode_signal_shapes(self, query, body, defect):
        with pytest.raises(ModeSignalError) as exc:
            classify_mode(query, body)
        assert exc.value.defect is defect
        assert exc.value.error_code == "invalid_request"

    # [utest->req~shared-mode-check-no-side-effects~1]
    def test_rejection_has_no_side_effects_and_the_challenge_survives(self):
        with pytest.raises(ModeSignalError):
            classify_mode([("challenge", "true")], {"challenge_id": "live-challenge"})
        # The client corrects its URL and retries with that same challenge.
        retry = classify_mode([], {"challenge_id": "live-challenge"})
        assert retry.mode is RequestMode.completion
        assert retry.challenge_id == "live-challenge"

    # [utest->req~shared-mode-signal-partition~1]
    @pytest.mark.parametrize(("query", "body"), [
        ([("challenge", "true")], {}),
        ([], {"challenge_id": "abc"}),
        ([("challenge", "true")], {"challenge_id": "abc"}),
        ([], {}),
    ])
    def test_partition_is_exhaustive(self, query, body):
        """Every combination resolves to prepare, completion, or invalid_request."""
        try:
            mode = classify_mode(query, body).mode
        except ModeSignalError as exc:
            assert exc.defect in {ModeSignalDefect.both_signals, ModeSignalDefect.neither_signal}
        else:
            assert mode in {RequestMode.prepare, RequestMode.completion}


class TestOperationVariants:
    # [utest->req~shared-challenge-binds-variant~1]
    def test_variants_are_normalized_per_operation(self):
        assert normalize_variant(AuthOperation.create_user, None) is IdentityProvider.anonymous
        assert normalize_variant(AuthOperation.create_user, "google") is IdentityProvider.google
        assert normalize_variant(AuthOperation.upgrade_anonymous_to_registered,
                                 "apple") is IdentityProvider.apple
        # Exact, case-sensitive match against the identity-provider enumeration.
        with pytest.raises(InvalidOperationVariantError):
            normalize_variant(AuthOperation.create_user, "Google")
        # The upgrade target is google or apple; it has no anonymous variant and no default.
        with pytest.raises(InvalidOperationVariantError):
            normalize_variant(AuthOperation.upgrade_anonymous_to_registered, "anonymous")
        with pytest.raises(InvalidOperationVariantError):
            normalize_variant(AuthOperation.upgrade_anonymous_to_registered, None)
        # Neither claim has a client-selected variant, and neither do the operations outside
        # the challenge-bearing subset.
        for operation in (AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant,
                          AuthOperation.sync, AuthOperation.restore_subscription):
            assert normalize_variant(operation, None) is None
            with pytest.raises(InvalidOperationVariantError):
                normalize_variant(operation, "google")


class _RecordingEndpoint:
    def __init__(self, operation: AuthOperation):
        self.operation = operation
        self.calls: list[str] = []

    async def run(self, identity, body):
        self.calls.append("endpoint")
        return {"ran": str(self.operation)}


class _RecordingShared:
    def __init__(self):
        self.calls: list[tuple] = []

    async def prepare(self, operation, variant, identity, endpoint, **_):
        endpoint.calls.append("shared-prepare")
        self.calls.append(("prepare", operation, variant))
        return {"challenge_id": "issued"}

    async def complete(self, operation, declared_variant, challenge_id, identity, endpoint, **_):
        endpoint.calls.append("shared-complete")
        self.calls.append(("complete", operation, declared_variant, challenge_id))
        return {"completed": challenge_id}


class TestStateChangingDispatch:
    # [utest->req~shared-endpoint-operation-specific~1]
    async def test_endpoint_attempts_only_its_own_operation(self):
        endpoint = _RecordingEndpoint(AuthOperation.claim_anonymous_grant)
        with pytest.raises(OperationMismatchError):
            await dispatch_state_changing(operation=AuthOperation.claim_registered_grant,
                                          endpoint=endpoint, identity=object(),
                                          query_items=[], body={"challenge_id": "abc"},
                                          shared=_RecordingShared())
        assert endpoint.calls == []

    # [utest->req~shared-endpoints-use-shared-procedures~1]
    async def test_challenge_bearing_endpoints_go_through_the_shared_procedures(self):
        shared = _RecordingShared()
        endpoint = _RecordingEndpoint(AuthOperation.create_user)
        await dispatch_state_changing(operation=AuthOperation.create_user, endpoint=endpoint,
                                      identity=object(), query_items=[("challenge", "true")],
                                      body={}, shared=shared)
        await dispatch_state_changing(operation=AuthOperation.create_user, endpoint=endpoint,
                                      identity=object(), query_items=[],
                                      body={"challenge_id": "abc", "provider": "google"},
                                      shared=shared)
        assert shared.calls == [("prepare", AuthOperation.create_user, IdentityProvider.anonymous),
                                ("complete", AuthOperation.create_user, "google", "abc")]

    # [utest->req~shared-flow-order-shared-then-specific~1]
    async def test_shared_procedures_run_before_endpoint_specific_rules(self):
        shared = _RecordingShared()
        endpoint = _RecordingEndpoint(AuthOperation.claim_anonymous_grant)
        await dispatch_state_changing(operation=AuthOperation.claim_anonymous_grant,
                                      endpoint=endpoint, identity=object(), query_items=[],
                                      body={"challenge_id": "abc"}, shared=shared)
        assert endpoint.calls == ["shared-complete"]
        # An operation outside the subset applies its own endpoint rules directly.
        sync_endpoint = _RecordingEndpoint(AuthOperation.sync)
        await dispatch_state_changing(operation=AuthOperation.sync, endpoint=sync_endpoint,
                                      identity=object(), query_items=[], body={}, shared=shared)
        assert sync_endpoint.calls == ["endpoint"]

    # [utest->req~shared-challenge-scope-narrower-subset~1]
    async def test_operations_outside_the_subset_touch_no_challenge(self):
        shared = _RecordingShared()
        for operation in (AuthOperation.sync, AuthOperation.sign_out_all,
                          AuthOperation.restore_subscription):
            endpoint = _RecordingEndpoint(operation)
            # Even with a prepare-looking query string and a challenge_id in the body.
            result = await dispatch_state_changing(
                operation=operation, endpoint=endpoint, identity=object(),
                query_items=[("challenge", "true")], body={"challenge_id": "abc"}, shared=shared)
            assert result == {"ran": str(operation)}
        assert shared.calls == []

    # [utest->req~shared-internal-reuse-allowed~1]
    async def test_shared_code_is_reused_while_the_contract_stays_operation_specific(self):
        shared = _RecordingShared()
        for operation in (AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant):
            endpoint = _RecordingEndpoint(operation)
            await dispatch_state_changing(operation=operation, endpoint=endpoint,
                                          identity=object(), query_items=[],
                                          body={"challenge_id": "abc"}, shared=shared)
        assert [call[1] for call in shared.calls] == [AuthOperation.claim_anonymous_grant,
                                                      AuthOperation.claim_registered_grant]

    # [utest->req~shared-admission-phase-precedes-path~1]
    async def test_mode_signal_rejection_reaches_no_operation_work(self):
        shared = _RecordingShared()
        endpoint = _RecordingEndpoint(AuthOperation.create_user)
        with pytest.raises(ModeSignalError):
            await dispatch_state_changing(operation=AuthOperation.create_user, endpoint=endpoint,
                                          identity=object(), query_items=[("challenge", "true")],
                                          body={"challenge_id": "abc"}, shared=shared)
        assert shared.calls == []
        assert endpoint.calls == []


class TestIntroductoryEntitlement:
    # [utest->req~shared-introductory-entitlement-definition~1]
    def test_introductory_entitlement_is_exactly_the_two_claims(self):
        assert set(INTRODUCTORY_GRANT_SOURCES.values()) == {AuthOperation.claim_anonymous_grant,
                                                            AuthOperation.claim_registered_grant}
        assert allocates_introductory_entitlement(AuthOperation.claim_anonymous_grant) is True
        assert allocates_introductory_entitlement(AuthOperation.claim_registered_grant) is True
        for operation in (AuthOperation.create_user, AuthOperation.sync,
                          AuthOperation.upgrade_anonymous_to_registered,
                          AuthOperation.restore_subscription, AuthOperation.sign_out_all):
            assert allocates_introductory_entitlement(operation) is False
        # It has no entitlement type, counter, flag, or grant source of its own.
        assert "introductory" not in {source.value for source in AccessGrantSource}

    # [utest->req~shared-introductory-entitlement-prohibition~1]
    def test_prohibited_operations_allocate_nothing(self):
        for operation in (AuthOperation.create_user, AuthOperation.sync, AuthOperation.sign_out_all,
                          AuthOperation.upgrade_anonymous_to_registered):
            for mutation in (GrantMutation.access_grant_write, GrantMutation.claim_path_invocation):
                with pytest.raises(IntroductoryEntitlementError):
                    guard_grant_mutation(operation, mutation)
        # No operation may treat a monthly usage counter as an entitlement.
        with pytest.raises(IntroductoryEntitlementError):
            guard_grant_mutation(AuthOperation.claim_anonymous_grant,
                                 GrantMutation.usage_counter_as_entitlement)
        # Each claim creates only its own free-credit source.
        guard_grant_mutation(AuthOperation.claim_anonymous_grant, GrantMutation.access_grant_write,
                             source=AccessGrantSource.anonymous_device_grant)
        with pytest.raises(IntroductoryEntitlementError):
            guard_grant_mutation(AuthOperation.claim_registered_grant,
                                 GrantMutation.access_grant_write,
                                 source=AccessGrantSource.anonymous_device_grant)


def _schema_with(*tables) -> MetaData:
    metadata = MetaData()
    Table("users", metadata, Column("id", String, primary_key=True), schema="core")
    Table("access_grants", metadata, Column("id", String, primary_key=True),
          Column("user_id", String, ForeignKey("core.users.id")), schema="core")
    Table("external_identities", metadata, Column("id", String, primary_key=True),
          Column("subject", String), Column("user_id", String, ForeignKey("core.users.id")),
          schema="core")
    for build in tables:
        build(metadata)
    return metadata


class TestOwnershipKeys:
    # [utest->req~shared-ownership-key-users-id~1]
    # [utest->req~sessions-users-id-sole-ownership-key~1]
    def test_business_data_is_owned_by_users_id_and_usage_by_the_grant(self):
        good = _schema_with(
            lambda md: Table("chats", md, Column("id", String, primary_key=True),
                             Column("user_id", String, ForeignKey("core.users.id")), schema="core"),
            lambda md: Table("user_monthly_usage", md, Column("id", String, primary_key=True),
                             Column("access_grant_id", String,
                                    ForeignKey("core.access_grants.id")), schema="core"))
        assert ownership_violations(good) == []

        # Usage owned by the user instead of the grant that authorizes the credits.
        bad = _schema_with(
            lambda md: Table("user_monthly_usage", md, Column("id", String, primary_key=True),
                             Column("user_id", String, ForeignKey("core.users.id")), schema="core"))
        assert any("user_monthly_usage" in violation for violation in ownership_violations(bad))

        # Business data owned by something other than core.users.id.
        misowned = _schema_with(
            lambda md: Table("chats", md, Column("id", String, primary_key=True),
                             Column("user_id", String,
                                    ForeignKey("core.external_identities.id")), schema="core"))
        assert ownership_violations(misowned) != []

    # [utest->req~shared-no-external-subject-ownership~1]
    # [utest->req~sessions-no-external-subject-ownership~1]
    def test_no_business_table_owns_rows_by_an_external_subject(self):
        for column_name in ("sub", "uid", "jwt_sub", "firebase_uid"):
            metadata = _schema_with(
                lambda md, name=column_name: Table("chats", md,
                                                   Column("id", String, primary_key=True),
                                                   Column(name, String), schema="core"))
            violations = ownership_violations(metadata)
            assert any("external subject" in violation for violation in violations), column_name

    # [utest->req~shared-ownership-key-users-id~1]
    # [utest->req~sessions-users-id-sole-ownership-key~1]
    # [utest->req~sessions-no-external-subject-ownership~1]
    def test_the_guard_reads_the_shipped_schema_and_reports_its_real_state(self):
        # Every business table owns its rows by `core.users.id`, no business table owns rows by
        # an external subject or an external identity, and the monthly-usage table hangs off the
        # access grant that authorizes its credits rather than off the user.
        assert ownership_violations(SQLModel.metadata) == []
        assert "user_monthly_usage" in {t.name for t in SQLModel.metadata.tables.values()}
