"""`POST /auth/sync`'s read-only contract, as `01-sessions-and-identity-resolution.md` states it:
the barrier precondition, the reported entitlement and registration state, the response shape, and
the complete must-not list.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nativespeaker.api.auth.audit import (
    AuditAlreadyWrittenError,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEventResult,
    AuthResultCounter,
    InvalidTerminalOutcomeError,
    sync_event,
)
from nativespeaker.api.auth.barrier import (
    BarrierRejectionError,
    ResolutionOutcome,
    VerifiedIdentityContext,
    barrier_result_for,
)
from nativespeaker.api.auth.endpoints import EndpointContractError, bearer_credential
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.operations import (
    AdmissionRejection,
    AuthOperation,
    IdentityProvider,
)
from nativespeaker.api.auth.routes import is_pre_auth_callable
from nativespeaker.api.auth.sync import (
    ENTITLEMENT_FIELDS,
    ENTITLEMENT_SOURCE_TABLES,
    FORBIDDEN_EFFECTS,
    GRANT_SOURCE_PRECEDENCE,
    PROHIBITED_CALLS,
    SYNC_BUSINESS_WRITES,
    SYNC_CHALLENGE_ROWS_TOUCHED,
    SYNC_RESPONSE_IS_ADVISORY,
    ReadOnlySyncSession,
    SyncEffect,
    SyncError,
    SyncIntegrityError,
    SyncProhibitedError,
    assert_admitted,
    assert_barrier_precondition,
    assert_permitted,
    is_forbidden,
    preauth_rejection,
    sync_admission_rejection_writes_row,
    sync_attempt_event,
    sync_credential,
    sync_handler,
    sync_response,
    sync_state,
    sync_terminal_result,
)
from nativespeaker.api.auth.tokens import InvalidExternalJwtError
from nativespeaker.api.quota.grants import PublicEntitlementStatus, PublicEntitlementType
from unit.conftest import grant_row

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
ISSUER = "https://securetoken.google.com/test-project"
USER_ID = uuid4()


def linked(provider: IdentityProvider = IdentityProvider.anonymous) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=ISSUER,
                                   subject="sub-1",
                                   outcome=ResolutionOutcome.linked,
                                   user_id=USER_ID,
                                   external_identity_id=uuid4(),
                                   provider=provider)


def session(*,
            rows=(),
            usage: tuple[str, int] | None = ("2026-03", 4),
            provider: IdentityProvider = IdentityProvider.anonymous) -> ReadOnlySyncSession:
    return ReadOnlySyncSession(grant_rows=rows, usage_row=usage, stored_provider=provider)


def active_grant(**overrides):
    return grant_row(user_id=USER_ID,
                     starts_at=datetime(2026, 1, 1, tzinfo=UTC),
                     **overrides)


def _actor() -> AuthActor:
    """An actor the shared audit contract accepts: a verified issuer and a 32-byte subject hash."""
    return AuthActor(issuer=ISSUER, subject_hash=b"\x11" * 32, subject_hash_key_version=1)


class TestAdmission:
    # [utest->req~sessions-sync-runs-after-barrier~1]
    def test_sync_reports_only_on_a_barrier_admitted_linked_identity(self):
        assert assert_admitted(linked()).user_id == USER_ID
        for outcome in (ResolutionOutcome.pre_auth, ResolutionOutcome.historical_identity,
                        ResolutionOutcome.blocked_user):
            with pytest.raises(SyncError):
                assert_admitted(VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                                        outcome=outcome))
        # A linked outcome carrying no resolved user is not a reportable state either.
        with pytest.raises(SyncError):
            assert_admitted(VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                                    outcome=ResolutionOutcome.linked))

    # [utest->req~sessions-sync-runs-after-barrier~1]
    def test_the_handler_resolves_no_identity_of_its_own(self):
        # There is no path into the reported state that does not start from the barrier's context.
        with pytest.raises(SyncError):
            sync_state(VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                               outcome=ResolutionOutcome.pre_auth),
                       session(), now=NOW)

    # [utest->req~sessions-sync-not-preauth-callable~1]
    def test_a_preauth_identity_is_rejected_on_the_sync_route(self):
        assert is_pre_auth_callable("POST", "/auth/sync") is False
        assert preauth_rejection() is AuthEventResult.preauth_identity_not_allowed
        assert barrier_result_for(ResolutionOutcome.pre_auth, "POST", "/auth/sync") \
            is AuthEventResult.preauth_identity_not_allowed
        # The declaration is what makes the difference: create-user is the one pre-auth route.
        assert barrier_result_for(ResolutionOutcome.pre_auth, "POST", "/auth/create-user") is None


class TestReportedState:
    # [utest->req~sessions-sync-returns-state-no-mutation~1]
    # [utest->req~sessions-sync-returns-entitlement-state~1]
    def test_a_linked_user_gets_the_current_entitlement_state(self):
        rows = (active_grant(source=AccessGrantSource.subscription, subscription_id=uuid4(),
                             tier_id="silver", monthly_credits=50),)
        state = sync_state(linked(), session(rows=rows, usage=("2026-03", 4)), now=NOW)
        assert state.entitlement.type is PublicEntitlementType.subscription
        assert state.entitlement.status is PublicEntitlementStatus.active
        assert (state.entitlement.tier_id, state.entitlement.monthly_credits) == ("silver", 50)
        assert (state.entitlement.current_period, state.entitlement.monthly_used) == ("2026-03", 4)

    # [utest->req~sessions-sync-returns-state-no-mutation~1]
    def test_reporting_leaves_the_rows_it_read_untouched(self):
        rows = (active_grant(tier_id="free", monthly_credits=10),)
        handle = session(rows=rows, usage=("2026-03", 4))
        sync_state(linked(), handle, now=NOW)
        assert handle.read_grant_rows() == rows
        assert rows[0].status is AccessGrantStatus.active
        # And the handle offers no way to change any of it.
        with pytest.raises(SyncProhibitedError):
            handle.update_profile(display_name="x")

    # [utest->req~sessions-sync-single-effective-grant~2]
    def test_the_reported_entitlement_is_the_single_effective_grant(self):
        lapsed = active_grant(status=AccessGrantStatus.expired, tier_id="silver",
                              monthly_credits=50)
        current = active_grant(source=AccessGrantSource.manual, tier_id="gold",
                               monthly_credits=200)
        state = sync_state(linked(), session(rows=(lapsed, current)), now=NOW)
        # Content comes only from the effective grant and its tier row.
        assert state.entitlement.type is PublicEntitlementType.manual
        assert (state.entitlement.tier_id, state.entitlement.monthly_credits) == ("gold", 200)

    # [utest->req~sessions-sync-status-none-or-active~2]
    def test_a_lapsed_or_revoked_grant_reads_as_none(self):
        ended_but_not_flipped = active_grant(status=AccessGrantStatus.active,
                                             ends_at=datetime(2026, 2, 1, tzinfo=UTC))
        revoked = active_grant(status=AccessGrantStatus.revoked)
        for rows in ((), (revoked,), (ended_but_not_flipped,), (revoked, ended_but_not_flipped)):
            state = sync_state(linked(), session(rows=rows), now=NOW)
            assert state.entitlement.type is PublicEntitlementType.none
            assert state.entitlement.status is PublicEntitlementStatus.none
            assert state.entitlement.tier_id is None
            assert state.entitlement.monthly_credits is None
        # The public enum has exactly the two members, so `expired` and `revoked` cannot be
        # reported at all.
        assert {member.value for member in PublicEntitlementStatus} == {"none", "active"}

    # [utest->req~sessions-sync-monthly-used-source~2]
    def test_current_period_and_monthly_used_are_always_present(self):
        rows = (active_grant(),)
        # No usage row yet, a row naming an earlier period, and this month's row.
        assert sync_state(linked(), session(rows=rows, usage=None),
                          now=NOW).entitlement.monthly_used == 0
        assert sync_state(linked(), session(rows=rows, usage=("2026-01", 7)),
                          now=NOW).entitlement.monthly_used == 0
        assert sync_state(linked(), session(rows=rows, usage=("2026-03", 7)),
                          now=NOW).entitlement.monthly_used == 7
        # Present with no grant at all, too, and derived from the same clock.
        no_grant = sync_state(linked(), session(rows=(), usage=None), now=NOW).entitlement
        assert (no_grant.current_period, no_grant.monthly_used) == ("2026-03", 0)

    # [utest->req~sessions-sync-read-only-for-usage~1]
    def test_sync_never_rolls_a_usage_row_over_or_flips_a_grant(self):
        ended = active_grant(status=AccessGrantStatus.active,
                             ends_at=datetime(2026, 2, 1, tzinfo=UTC))
        handle = session(rows=(ended,), usage=("2026-01", 7))
        state = sync_state(linked(), handle, now=NOW)
        # The stale counter is reported as zero for the computed period and left unwritten.
        assert (state.entitlement.current_period, state.entitlement.monthly_used) == ("2026-03", 0)
        assert handle.read_usage_row() == ("2026-01", 7)
        # The time-ended row is still `active`: the lazy flip belongs to grant issuance.
        assert handle.read_grant_rows()[0].status is AccessGrantStatus.active
        for call in ("write_rollover", "increment_usage", "initialize_usage", "expire_grant"):
            with pytest.raises(SyncProhibitedError):
                getattr(handle, call)()

    # [utest->req~sessions-sync-multiple-active-grants-fail-closed~1]
    def test_two_effective_grants_fail_closed_with_no_precedence(self):
        rows = (active_grant(source=AccessGrantSource.subscription, subscription_id=uuid4()),
                active_grant(source=AccessGrantSource.manual))
        with pytest.raises(SyncIntegrityError) as raised:
            sync_state(linked(), session(rows=rows), now=NOW)
        assert raised.value.result is AuthEventResult.internal_error
        assert GRANT_SOURCE_PRECEDENCE == ()

    # [utest->req~sessions-sync-reports-registration-state~1]
    def test_the_stored_registration_state_is_reported_and_never_flipped(self):
        for provider in IdentityProvider:
            handle = session(rows=(active_grant(),), provider=provider)
            state = sync_state(linked(), handle, now=NOW)
            assert state.identity_provider is provider
            assert sync_response(state)["identity_provider"] == provider.value
        # Reporting it performs no `providerData` read and flips nothing.
        handle = session(rows=(active_grant(),), provider=IdentityProvider.google)
        sync_state(linked(), handle, now=NOW)
        assert handle.reads.count("stored_provider") == 1
        for call in ("read_provider_data", "flip_stored_provider"):
            with pytest.raises(SyncProhibitedError):
                getattr(handle, call)()

    # [utest->req~sessions-sync-no-device-check-or-grant-state~1]
    def test_sync_verifies_no_device_proof_and_touches_no_device_grant_state(self):
        handle = session(rows=(active_grant(),))
        sync_state(linked(), handle, now=NOW)
        # Database state only: the reads are the three the contract allows.
        assert set(handle.reads) <= set(ReadOnlySyncSession.READS)
        for call in ("verify_devicecheck", "verify_play_integrity", "verify_device_recall",
                     "verify_device_proof", "read_device_grant_state",
                     "write_device_grant_state"):
            with pytest.raises(SyncProhibitedError):
                getattr(handle, call)()


class TestResponseShape:
    # [utest->req~sessions-sync-entitlement-response-shape~1]
    def test_the_entitlement_object_is_exactly_the_documented_shape(self):
        state = sync_state(linked(IdentityProvider.apple),
                           session(rows=(active_grant(tier_id="free", monthly_credits=10),),
                                   usage=("2026-03", 4),
                                   provider=IdentityProvider.apple),
                           now=NOW)
        body = sync_response(state)
        assert tuple(body["entitlement"]) == ENTITLEMENT_FIELDS
        assert body["entitlement"] == {"type": "anonymous_device_grant",
                                       "status": "active",
                                       "tier_id": "free",
                                       "monthly_credits": 10,
                                       "current_period": "2026-03",
                                       "monthly_used": 4}
        # The `type` domain is the documented one.
        assert {member.value for member in PublicEntitlementType} == {
            "none", "subscription", "anonymous_device_grant", "registered_account_grant",
            "manual"}

    # [utest->req~sessions-sync-entitlement-response-shape~1]
    # [utest->req~sessions-sync-monthly-used-source~2]
    def test_no_grant_still_fills_the_whole_shape_with_no_nulls_where_none_are_allowed(self):
        body = sync_response(sync_state(linked(), session(rows=(), usage=None), now=NOW))
        assert tuple(body["entitlement"]) == ENTITLEMENT_FIELDS
        assert body["entitlement"]["current_period"] == "2026-03"
        assert body["entitlement"]["monthly_used"] == 0
        assert body["entitlement"]["tier_id"] is None
        assert body["entitlement"]["monthly_credits"] is None


class TestProhibitions:
    # [utest->req~sessions-sync-prohibitions~1]
    def test_nothing_on_the_must_not_list_is_ever_permitted(self):
        assert FORBIDDEN_EFFECTS == frozenset(SyncEffect)
        for effect in SyncEffect:
            assert is_forbidden(effect) is True
            with pytest.raises(SyncProhibitedError):
                assert_permitted(effect)
        # An effect nobody enumerated is forbidden too: the session is a closed permission set.
        assert is_forbidden("mint a backend token") is True
        handle = session()
        with pytest.raises(SyncProhibitedError):
            handle.something_nobody_thought_of()

    # Each entry of the must-not list, refused by name at the one decision point.
    # [utest->req~sessions-sync-must-not-create-users~1]
    # [utest->req~sessions-sync-must-not-init-usage~1]
    # [utest->req~sessions-sync-must-not-allocate-intro~1]
    # [utest->req~sessions-sync-must-not-verify-restore-proofs~1]
    # [utest->req~sessions-sync-must-not-verify-device-proofs~1]
    # [utest->req~sessions-sync-must-not-touch-device-grant-state~1]
    # [utest->req~sessions-sync-must-not-create-grants~1]
    # [utest->req~sessions-sync-must-not-issue-challenges~1]
    # [utest->req~sessions-sync-must-not-select-completion-operation~1]
    # [utest->req~sessions-sync-must-not-derive-restore-target~1]
    # [utest->req~sessions-sync-must-not-link-identities~1]
    # [utest->req~sessions-sync-must-not-mark-historical~1]
    # [utest->req~sessions-sync-must-not-merge-users~1]
    # [utest->req~sessions-sync-must-not-modify-subscriptions~1]
    # [utest->req~sessions-sync-must-not-update-profile~1]
    # [utest->req~sessions-sync-must-not-append-mutation-audit~1]
    @pytest.mark.parametrize(("call", "effect"), [
        ("create_user", SyncEffect.create_user),
        ("initialize_usage", SyncEffect.initialize_usage),
        ("allocate_introductory_entitlement", SyncEffect.allocate_introductory_entitlement),
        ("verify_restore_proof", SyncEffect.verify_restore_proof),
        ("verify_device_proof", SyncEffect.verify_device_proof),
        ("read_device_grant_state", SyncEffect.touch_device_grant_state),
        ("write_device_grant_state", SyncEffect.touch_device_grant_state),
        ("create_grant", SyncEffect.create_grant),
        ("finalize_grant", SyncEffect.create_grant),
        ("issue_challenge", SyncEffect.issue_challenge),
        ("select_completion_operation", SyncEffect.select_completion_operation),
        ("derive_restore_target", SyncEffect.derive_restore_target),
        ("link_identity", SyncEffect.link_identity),
        ("mark_identity_historical", SyncEffect.mark_identity_historical),
        ("merge_users", SyncEffect.merge_users),
        ("modify_subscription", SyncEffect.modify_subscription),
        ("update_profile", SyncEffect.update_profile),
        ("append_mutation_audit", SyncEffect.append_mutation_audit),
    ])
    def test_each_prohibited_call_is_refused_as_its_own_effect(self, call, effect):
        assert PROHIBITED_CALLS[call] is effect
        handle = session()
        with pytest.raises(SyncProhibitedError) as raised:
            getattr(handle, call)()
        assert raised.value.effect is effect

    # [utest->req~sessions-sync-must-not-append-mutation-audit~1]
    def test_the_sync_audit_row_records_no_mutation(self):
        event = sync_event(AuthEventResult.succeeded)
        assert event.details["mutation"] == {}
        assert event.challenge_row_id is None
        with pytest.raises(InvalidTerminalOutcomeError):
            sync_event(AuthEventResult.succeeded,
                       details={"mutation": {"core.users": {"email": "x@example.com"}}})


class TestEndpointContract:
    """The `## API: POST /auth/sync` section: the credential, the admission precondition, what the
    handler returns, and what it refuses to trust."""

    # [utest->req~sessions-api-sync-bearer-credential~1]
    def test_the_credential_is_exactly_one_authorization_bearer_value(self):
        assert sync_credential(["Bearer id-token"]) == "id-token"
        # Zero, duplicated, comma-folded, non-`Bearer` and multi-credential values all reject.
        for values in ([], ["Bearer a", "Bearer b"], ["Bearer a, Bearer b"], ["Basic a"],
                       ["Bearer "], ["Bearer a b"]):
            with pytest.raises(InvalidExternalJwtError):
                sync_credential(values)

    # [utest->req~sessions-api-sync-bearer-credential~1]
    def test_a_route_declaring_no_id_token_requirement_carries_no_credential(self):
        with pytest.raises(EndpointContractError):
            bearer_credential("GET", "/health/ready", ["Bearer id-token"])

    # [utest->req~sessions-api-sync-barrier-precondition~1]
    def test_the_endpoint_requires_a_linked_active_identity(self):
        assert assert_barrier_precondition(linked()).user_id == USER_ID
        # Pre-auth, historical and blocked are all rejected, each with the barrier's own result.
        for outcome, result in ((ResolutionOutcome.pre_auth,
                                 AuthEventResult.preauth_identity_not_allowed),
                                (ResolutionOutcome.historical_identity,
                                 AuthEventResult.historical_identity),
                                (ResolutionOutcome.blocked_user, AuthEventResult.blocked_user)):
            with pytest.raises(BarrierRejectionError) as raised:
                assert_barrier_precondition(
                    VerifiedIdentityContext(issuer=ISSUER, subject="sub-1", outcome=outcome))
            assert raised.value.result is result

    # [utest->req~sessions-api-sync-handler-returns-state~1]
    async def test_the_handler_returns_entitlement_state_from_the_three_tables(self):
        rows = (active_grant(status=AccessGrantStatus.active, tier_id="silver",
                             monthly_credits=50, source=AccessGrantSource.subscription),)
        body = await sync_handler(linked(IdentityProvider.google),
                                  session(rows=rows, usage=("2026-03", 7),
                                          provider=IdentityProvider.google),
                                  audit_attempt=sync_attempt(), audit=make_writer(RecordingSink()),
                                  actor=_actor(), now=NOW)
        assert body["entitlement"]["tier_id"] == "silver"
        assert body["entitlement"]["monthly_credits"] == 50
        assert body["entitlement"]["monthly_used"] == 7
        assert body["identity_provider"] == "google"
        # The three named tables are the whole derivation, and the handler writes nothing.
        assert set(ENTITLEMENT_SOURCE_TABLES) == {"core.access_grants", "core.access_tiers",
                                                 "core.user_monthly_usage"}
        assert SYNC_BUSINESS_WRITES == frozenset()

    # [utest->req~sessions-api-sync-handler-returns-state~1]
    async def test_the_handler_runs_the_admission_precondition_before_reading(self):
        handle = session()
        sink = RecordingSink()
        with pytest.raises(BarrierRejectionError):
            await sync_handler(VerifiedIdentityContext(issuer=ISSUER, subject="sub-1",
                                                       outcome=ResolutionOutcome.blocked_user),
                               handle, audit_attempt=sync_attempt(), audit=make_writer(sink),
                               actor=_actor(), now=NOW)
        assert handle.reads == []
        # The barrier owns that rejection's row; the handler wrote none of its own.
        assert sink.rows == []

    # [utest->req~sessions-api-sync-no-client-snapshot-trust~1]
    async def test_an_offered_client_snapshot_is_refused_rather_than_merged(self):
        for field in ("client_snapshot", "cached_entitlement", "last_known_tier",
                      "cached_identity_provider"):
            with pytest.raises(SyncError):
                await sync_handler(linked(), session(), audit_attempt=sync_attempt(),
                                   audit=make_writer(RecordingSink()), actor=_actor(), now=NOW,
                                   request_body={field: "anything"})
        # A body carrying nothing the snapshot list names is simply not read.
        body = await sync_handler(linked(), session(), audit_attempt=sync_attempt(),
                                  audit=make_writer(RecordingSink()), actor=_actor(), now=NOW,
                                  request_body={"unrelated": 1})
        assert body["identity_provider"] == "anonymous"
        assert SYNC_RESPONSE_IS_ADVISORY is True

    # The endpoint's purpose and the completeness of its must-not list are reference statements
    # rather than behaviour of their own — the individual `must not` items carry the tests — so
    # this keeps the derived sets honest without claiming a coverage tag for either.
    def test_the_prohibitions_are_exactly_the_read_only_contract_must_not_list(self):
        assert FORBIDDEN_EFFECTS == frozenset(SyncEffect)
        assert set(PROHIBITED_CALLS.values()) <= FORBIDDEN_EFFECTS


class RecordingSink:
    """The `audit.auth_events` sink, recording the rows the shared writer appends."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def insert(self, session, row) -> None:
        self.rows.append(dict(row))


class FakeSession:
    async def commit(self) -> None:
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None


def make_writer(sink: RecordingSink) -> AuthAuditWriter:
    return AuthAuditWriter(sink=sink, counter=AuthResultCounter(), session_factory=FakeSession)


def sync_attempt() -> AuthAttempt:
    return AuthAttempt("POST", "/auth/sync")


class TestAuditedAttemptPath:
    """Every attempt owes exactly one row, and an admission rejection owes none."""

    # [utest->req~sessions-api-sync-audited-attempt-path~1]
    def test_the_terminal_result_is_succeeded_or_the_barriers_own_result(self):
        assert sync_terminal_result(None) is AuthEventResult.succeeded
        for result in (AuthEventResult.invalid_external_jwt,
                       AuthEventResult.preauth_identity_not_allowed,
                       AuthEventResult.historical_identity,
                       AuthEventResult.blocked_user):
            assert sync_terminal_result(result) is result

    # [utest->req~sessions-api-sync-audited-attempt-path~1]
    def test_the_attempt_row_names_sync_records_no_mutation_and_is_challenge_free(self):
        attempt = AuthAttempt("POST", "/auth/sync")
        assert attempt.on_audited_path is True
        event = sync_attempt_event(AuthEventResult.succeeded, actor=_actor())
        assert event.operation is AuthOperation.sync
        assert event.details["mutation"] == {}
        assert event.challenge_row_id is None
        # A caller offering a mutation is refused rather than trimmed: the row is an attempt
        # record, never evidence of a state change.
        with pytest.raises(InvalidTerminalOutcomeError):
            sync_attempt_event(AuthEventResult.succeeded, actor=_actor(),
                               details={"mutation": {"core.users": {"email": "x@example.com"}}})
        # And no result outside the endpoint's terminal outcomes can be recorded for it.
        with pytest.raises(InvalidTerminalOutcomeError):
            sync_attempt_event(AuthEventResult.revocation_unconfirmed, actor=_actor())

    # [utest->req~sessions-api-sync-audited-attempt-path~1]
    async def test_the_response_is_not_produced_without_the_attempts_one_row(self):
        sink = RecordingSink()
        writer = make_writer(sink)
        attempt = sync_attempt()
        body = await sync_handler(linked(IdentityProvider.google),
                                  session(provider=IdentityProvider.google),
                                  audit_attempt=attempt, audit=writer, actor=_actor(), now=NOW)
        assert body["identity_provider"] == "google"
        # Exactly one row, with `operation = 'sync'`, appended before the response was returned.
        assert [(row["operation"], row["result"]) for row in sink.rows] == \
            [(AuthOperation.sync, AuthEventResult.succeeded)]
        assert sink.rows[0]["challenge_row_id"] is None
        assert sink.rows[0]["details"]["mutation"] == {}
        # A second row for the same attempt is refused rather than appended.
        with pytest.raises(AuditAlreadyWrittenError):
            await sync_handler(linked(), session(), audit_attempt=attempt, audit=writer,
                               actor=_actor(), now=NOW)
        assert len(sink.rows) == 1

    # [utest->req~sessions-api-sync-audited-attempt-path~1]
    def test_an_admission_rejection_ahead_of_the_route_match_writes_no_row(self):
        for rejection in (AdmissionRejection.gateway_rate_limited,
                          AdmissionRejection.backend_rate_limited,
                          AdmissionRejection.overload_shed,
                          AdmissionRejection.route_or_method_mismatch):
            assert sync_admission_rejection_writes_row(rejection) is False
        assert SYNC_CHALLENGE_ROWS_TOUCHED == frozenset()
