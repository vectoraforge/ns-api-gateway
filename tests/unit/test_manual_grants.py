"""Operator-issued `manual` grants: the remediation procedure for a burned device slot."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import IdentityState
from nativespeaker.api.auth.invariants import InvariantError
from nativespeaker.api.auth.locks import LockingPath, LockOrderError
from nativespeaker.api.auth.manual_grants import (
    CLIENT_REACHABLE_GRANT_ENDERS,
    MANUAL_ANTI_ABUSE_ROWS,
    MANUAL_GATE_CONSUMPTION_ROWS,
    MANUAL_GRANT_RATE_CAPS,
    MANUAL_ISSUANCE_AUDIT_ROWS,
    MANUAL_ISSUANCE_OPERATIONS,
    MANUAL_PROCEDURE_STEPS,
    RBAC_REQUIRED,
    IssuanceSurface,
    LostClaim,
    ManualGrantError,
    ManualGrantIssuance,
    ManualIssuance,
    ManualIssuanceRefused,
    ManualIssuanceRequest,
    ManualStep,
    OperatorAuth,
    assert_excluded_from_anti_abuse,
    assert_no_issuance_route,
    assert_no_manual_rate_cap,
    assert_not_promotional,
    assert_operator_authenticated,
    assert_operator_only_surface,
    blocked_registered_claim_options,
    derived_terms,
    free_grant_slots_after_manual,
    issuance_inputs,
    issue_manual_grant,
    manual_grant_is_ordinary_downstream,
    manual_grant_open_ended,
    manual_remedy_for_burned_slot,
    revoke_manual_grant,
    slot_burned,
)
from nativespeaker.api.quota.grants import GrantRow, PublicEntitlementType

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
USER = uuid7()
LOST_ANONYMOUS = LostClaim(source=AccessGrantSource.anonymous_device_grant,
                           tier_id="anonymous", monthly_credits=10, starts_at=NOW)


def request_for(**overrides: Any) -> ManualIssuanceRequest:
    fields: dict[str, Any] = {"user_id": USER, "case_id": "CASE-1",
                              "operator": "ops@example.com", "reason": "ticket NS-42 lost claim"}
    fields.update(overrides)
    return ManualIssuanceRequest(**fields)


def grant_row(*,
              source: AccessGrantSource = AccessGrantSource.manual,
              status: AccessGrantStatus = AccessGrantStatus.active,
              ends_at: datetime | None = None,
              grant_id: UUID | None = None) -> GrantRow:
    return GrantRow(grant_id=grant_id or uuid7(), user_id=USER, tier_id="anonymous",
                    source=source, status=status, starts_at=NOW - timedelta(days=1),
                    ends_at=ends_at, tier_monthly_credits=10)


def run(**overrides: Any) -> ManualIssuance:
    transaction = object()
    fields: dict[str, Any] = {"grant_id": uuid7(), "lost": LOST_ANONYMOUS,
                              "live_grant_ids": (), "grants": (), "now": NOW,
                              "transaction": transaction,
                              "claim_would_have_succeeded": True}
    fields.update(overrides)
    return issue_manual_grant(request_for(), **fields)


# --- What a `manual` grant is for --------------------------------------------------------------


# [utest->req~grants-manual-remediation-purpose~1]
def test_a_set_vendor_bit_burns_the_slot_even_with_no_grant_on_record() -> None:
    assert slot_burned(vendor_bit_set=True, grant_activated=False) is True
    assert slot_burned(vendor_bit_set=True, grant_activated=True) is True
    assert slot_burned(vendor_bit_set=False, grant_activated=False) is False


# [utest->req~grants-manual-remediation-purpose~1]
def test_a_manual_grant_is_the_only_remedy_for_a_burned_slot() -> None:
    assert manual_remedy_for_burned_slot(vendor_bit_set=True) == ("manual_grant",)
    with pytest.raises(ManualGrantError):
        manual_remedy_for_burned_slot(vendor_bit_set=False)


# --- The issuance surface ---------------------------------------------------------------------


# [utest->req~grants-manual-operator-only-surface~1]
def test_only_the_two_operator_surfaces_issue_a_manual_grant() -> None:
    for surface in (IssuanceSurface.direct_database_procedure,
                    IssuanceSurface.operator_authenticated_internal_action):
        assert assert_operator_only_surface(surface) is surface
    for forbidden in (IssuanceSurface.client_endpoint, IssuanceSurface.support_facing_api,
                      IssuanceSurface.admin_ui, IssuanceSurface.other_web_surface):
        with pytest.raises(ManualGrantError):
            assert_operator_only_surface(forbidden)


# [utest->req~grants-manual-operator-only-surface~1]
def test_issuance_is_no_canonical_operation_and_writes_no_audit_row() -> None:
    assert MANUAL_ISSUANCE_OPERATIONS == frozenset()
    assert MANUAL_ISSUANCE_AUDIT_ROWS == 0
    assert_no_issuance_route()


# [utest->req~grants-manual-operator-auth-required~1]
def test_operator_authentication_must_be_distinct_from_ordinary_users() -> None:
    assert RBAC_REQUIRED is False
    for sufficient in (OperatorAuth.shared_administrative_secret,
                       OperatorAuth.iam_bound_internal_route):
        assert assert_operator_authenticated(sufficient) is sufficient
    for insufficient in (OperatorAuth.ordinary_user_credentials, OperatorAuth.none):
        with pytest.raises(ManualGrantError):
            assert_operator_authenticated(insufficient)


def test_no_manual_grant_rate_cap_is_enforced_in_the_backend() -> None:
    assert MANUAL_GRANT_RATE_CAPS == frozenset()
    assert_no_manual_rate_cap(("claim_anonymous_grant", "users_me"))
    with pytest.raises(ManualGrantError):
        assert_no_manual_rate_cap(("manual_grant_per_operator",))


# --- The inputs -------------------------------------------------------------------------------


# [utest->req~grants-manual-issuance-inputs~1]
def test_the_issuance_takes_four_inputs_and_no_derived_term() -> None:
    request = issuance_inputs({"user_id": USER, "case_id": "CASE-9",
                               "operator": "ops@example.com", "reason": "NS-9"})
    assert (request.user_id, request.case_id) == (USER, "CASE-9")
    for derived in ("tier_id", "monthly_credits", "duration", "expires_at", "ends_at"):
        with pytest.raises(ManualGrantError):
            issuance_inputs({"user_id": USER, "case_id": "C", "operator": "o", "reason": "r",
                             derived: 10})


# [utest->req~grants-manual-issuance-inputs~1]
def test_every_one_of_the_four_inputs_is_required() -> None:
    for missing in ("case_id", "operator", "reason"):
        payload: dict[str, Any] = {"user_id": USER, "case_id": "C", "operator": "o", "reason": "r"}
        payload[missing] = "  "
        with pytest.raises(ManualGrantError):
            issuance_inputs(payload)
    with pytest.raises(ManualGrantError):
        issuance_inputs({"case_id": "C", "operator": "o", "reason": "r"})


# --- The procedure ----------------------------------------------------------------------------


# [utest->req~grants-manual-step-01-resolve-case~1]
def test_a_repeated_case_returns_the_original_result_and_issues_nothing() -> None:
    first = run()
    again = run(recorded={"CASE-1": first}, grant_id=uuid7())
    assert again.repeated is True
    assert again.grant["id"] == first.grant["id"]
    assert again.issuance["case_id"] == "CASE-1"


# [utest->req~grants-manual-step-01-resolve-case~1]
def test_the_case_identifier_is_resolved_before_anything_else() -> None:
    procedure = ManualGrantIssuance(request_for())
    with pytest.raises(ManualGrantError):
        procedure.lock(live_grant_ids=())
    assert procedure.resolve_case() is None
    assert procedure.steps == [ManualStep.resolve_case]


# [utest->req~grants-manual-step-02-lock-order~1]
def test_the_user_is_locked_first_then_grants_then_usage_in_ascending_id_order() -> None:
    procedure = ManualGrantIssuance(request_for())
    procedure.resolve_case()
    grants = sorted((uuid7(), uuid7(), uuid7()))
    ledger = procedure.lock(live_grant_ids=list(reversed(grants)))
    assert ledger.path is LockingPath.manual_issuance
    assert list(ledger.grant_locks) == grants
    assert list(ledger.usage_locks) == grants


# [utest->req~grants-manual-step-02-lock-order~1]
def test_a_usage_row_is_never_locked_before_its_grant() -> None:
    procedure = ManualGrantIssuance(request_for())
    procedure.resolve_case()
    ledger = procedure.lock(live_grant_ids=())
    with pytest.raises(LockOrderError):
        ledger.lock_usage(uuid7())


# [utest->req~grants-manual-step-03-refuse-blocked~1]
def test_a_blocked_user_or_retired_identity_is_refused_and_nothing_is_created() -> None:
    with pytest.raises(ManualIssuanceRefused):
        run(user_blocked=True)
    with pytest.raises(ManualIssuanceRefused):
        run(identity_state=IdentityState.historical)


# [utest->req~grants-manual-step-04-establish-eligibility~1]
def test_issuance_never_overrides_an_anti_abuse_decision() -> None:
    procedure = ManualGrantIssuance(request_for())
    procedure.resolve_case()
    procedure.lock(live_grant_ids=())
    procedure.refuse_blocked(user_blocked=False)
    with pytest.raises(ManualIssuanceRefused):
        procedure.establish_eligibility(anti_abuse_denial="a reused-account restriction")


# [utest->req~grants-manual-step-04-establish-eligibility~1]
def test_recorded_operator_judgment_stands_in_for_unavailable_evidence() -> None:
    def eligibility(**kwargs: Any) -> str:
        procedure = ManualGrantIssuance(request_for())
        procedure.resolve_case()
        procedure.lock(live_grant_ids=())
        procedure.refuse_blocked(user_blocked=False)
        return procedure.establish_eligibility(**kwargs)

    assert eligibility(claim_would_have_succeeded=True) == "machine_verifiable_evidence"
    assert eligibility(operator_judgment="support confirmed the lost claim") \
        == "operator_recorded_judgment"
    with pytest.raises(ManualIssuanceRefused):
        eligibility()
    with pytest.raises(ManualIssuanceRefused):
        eligibility(claim_would_have_succeeded=False)


# [utest->req~grants-manual-step-05-one-active-grant~1]
def test_an_existing_active_grant_of_any_source_refuses_the_issuance() -> None:
    for source in AccessGrantSource:
        held = grant_row(source=source)
        with pytest.raises(ManualIssuanceRefused):
            run(grants=(held,), live_grant_ids=(held.grant_id,))


# [utest->req~grants-manual-step-05-one-active-grant~1]
def test_the_one_active_grant_check_reads_the_locked_grant_set() -> None:
    procedure = ManualGrantIssuance(request_for())
    procedure.resolve_case()
    procedure.lock(live_grant_ids=())
    procedure.refuse_blocked(user_blocked=False)
    procedure.establish_eligibility(claim_would_have_succeeded=True)
    with pytest.raises(ManualGrantError):
        procedure.check_one_active_grant((grant_row(),), NOW)


# [utest->req~grants-manual-step-05-one-active-grant~1]
def test_a_revoked_or_ended_grant_does_not_block_issuance() -> None:
    ended = grant_row(status=AccessGrantStatus.revoked)
    issued = run(grants=(ended,), live_grant_ids=(ended.grant_id,))
    assert issued.grant["status"] is AccessGrantStatus.active


# [utest->req~grants-manual-step-06-insert-grant~1]
def test_the_inserted_grant_reproduces_the_lost_claim_terms() -> None:
    issued = run(lost=LOST_ANONYMOUS)
    assert issued.grant["source"] is AccessGrantSource.manual
    assert issued.grant["tier_id"] == LOST_ANONYMOUS.tier_id
    assert issued.grant["user_id"] == USER
    assert issued.grant["ends_at"] is None
    assert issued.usage.grant_id == issued.grant["id"]
    assert issued.usage.monthly_used == 0


# [utest->req~grants-manual-step-06-insert-grant~1]
def test_the_terms_come_from_a_free_credit_claim_and_carry_no_discretion() -> None:
    assert derived_terms(LOST_ANONYMOUS) is LOST_ANONYMOUS
    with pytest.raises(ManualGrantError):
        derived_terms(LostClaim(source=AccessGrantSource.subscription, tier_id="gold",
                                monthly_credits=200, starts_at=NOW))
    with pytest.raises(ManualGrantError):
        derived_terms(LostClaim(source=AccessGrantSource.registered_account_grant,
                                tier_id="", monthly_credits=10, starts_at=NOW))


# [utest->req~grants-manual-step-07-record-issuance~1]
def test_the_issuance_row_carries_the_case_operator_reason_and_grant() -> None:
    issued = run()
    assert issued.issuance == {"case_id": "CASE-1", "grant_id": issued.grant["id"],
                               "user_id": USER, "operator": "ops@example.com",
                               "reason": "ticket NS-42 lost claim"}


# [utest->req~grants-manual-step-07-record-issuance~1]
def test_the_issuance_row_is_written_in_the_grants_own_transaction() -> None:
    procedure = ManualGrantIssuance(request_for())
    procedure.resolve_case()
    procedure.lock(live_grant_ids=())
    procedure.refuse_blocked(user_blocked=False)
    procedure.establish_eligibility(claim_would_have_succeeded=True)
    procedure.check_one_active_grant((), NOW)
    transaction = object()
    grant, _ = procedure.insert_grant(grant_id=uuid7(), lost=LOST_ANONYMOUS,
                                     transaction=transaction, now=NOW)
    with pytest.raises(ManualGrantError):
        procedure.record_issuance(grant, transaction=transaction,
                                  usage_transaction=object())


# [utest->req~grants-manual-step-08-leave-vendor-state~1]
def test_vendor_and_per_device_state_may_be_read_but_never_cleared_or_rewritten() -> None:
    issued = run(device_state_read=("devicecheck_bit0",))
    assert issued.grant["source"] is AccessGrantSource.manual

    def leave(**kwargs: Any) -> tuple[str, ...]:
        procedure = ManualGrantIssuance(request_for())
        procedure.resolve_case()
        procedure.lock(live_grant_ids=())
        procedure.refuse_blocked(user_blocked=False)
        procedure.establish_eligibility(claim_would_have_succeeded=True)
        procedure.check_one_active_grant((), NOW)
        transaction = object()
        grant, _ = procedure.insert_grant(grant_id=uuid7(), lost=LOST_ANONYMOUS,
                                         transaction=transaction, now=NOW)
        procedure.record_issuance(grant, transaction=transaction)
        return procedure.leave_vendor_state(**kwargs)

    assert leave(read=("device_recall",)) == ("device_recall",)
    with pytest.raises(ManualGrantError):
        leave(cleared=("devicecheck_bit0",))
    with pytest.raises(ManualGrantError):
        leave(rewritten=("device_recall",))


def test_the_procedure_runs_its_eight_steps_in_one_order() -> None:
    assert MANUAL_PROCEDURE_STEPS == tuple(ManualStep)
    procedure = ManualGrantIssuance(request_for())
    procedure.resolve_case()
    with pytest.raises(ManualGrantError):
        procedure.resolve_case()


# --- Excluded from anti-abuse, ordinary everywhere else ---------------------------------------


# [utest->req~grants-manual-excluded-from-anti-abuse~1]
def test_a_manual_grant_carries_no_anti_abuse_or_gate_consumption_row() -> None:
    assert (MANUAL_ANTI_ABUSE_ROWS, MANUAL_GATE_CONSUMPTION_ROWS) == (0, 0)
    assert_excluded_from_anti_abuse()
    with pytest.raises(InvariantError):
        assert_excluded_from_anti_abuse(
            anti_abuse_grant_source=AccessGrantSource.anonymous_device_grant)
    with pytest.raises(ManualGrantError):
        assert_excluded_from_anti_abuse(gate_consumption_rows=1)


# [utest->req~grants-manual-excluded-from-anti-abuse~1]
def test_issuing_neither_consumes_nor_reopens_a_free_grant_slot() -> None:
    history = (AccessGrantSource.anonymous_device_grant,)
    assert free_grant_slots_after_manual(history) == history
    assert free_grant_slots_after_manual(()) == ()
    assert free_grant_slots_after_manual((AccessGrantSource.manual,)) == ()


# [utest->req~grants-manual-excluded-from-anti-abuse~1]
def test_downstream_it_is_an_ordinary_grant_reported_as_type_manual() -> None:
    assert manual_grant_is_ordinary_downstream(grant_row(), NOW) is PublicEntitlementType.manual
    with pytest.raises(ManualGrantError):
        manual_grant_is_ordinary_downstream(
            grant_row(source=AccessGrantSource.subscription), NOW)
    with pytest.raises(ManualGrantError):
        manual_grant_is_ordinary_downstream(
            grant_row(status=AccessGrantStatus.revoked), NOW)


# --- Open-ended, and revoked on the same surface ----------------------------------------------


# [utest->req~grants-manual-open-ended-and-revocation~1]
def test_a_manual_grant_may_run_open_ended() -> None:
    assert manual_grant_open_ended(grant_row()) is True
    assert manual_grant_open_ended(grant_row(ends_at=NOW + timedelta(days=30))) is False


# [utest->req~grants-manual-open-ended-and-revocation~1]
def test_revocation_sets_revoked_with_ends_at_and_frees_the_slot() -> None:
    revoked = revoke_manual_grant(grant_row(), at=NOW)
    assert revoked.status is AccessGrantStatus.revoked
    assert revoked.ends_at == NOW
    # Freeing the slot is exactly this: the revoked row is no longer an effective grant.
    with pytest.raises(ManualGrantError):
        manual_grant_is_ordinary_downstream(revoked, NOW)


# [utest->req~grants-manual-open-ended-and-revocation~1]
def test_revocation_is_never_client_reachable() -> None:
    assert CLIENT_REACHABLE_GRANT_ENDERS == frozenset()
    with pytest.raises(ManualGrantError):
        revoke_manual_grant(grant_row(), at=NOW, surface=IssuanceSurface.client_endpoint)
    assert blocked_registered_claim_options(revoked_by_operator=False) == (
        "wait_for_the_held_grant_to_end", "ask_support_to_revoke_it")
    assert blocked_registered_claim_options(revoked_by_operator=True) == (
        "operator_revocation_then_retry",)


# --- Never promotional ------------------------------------------------------------------------


# [utest->req~grants-manual-never-promotional~1]
def test_manual_never_becomes_a_promotional_or_goodwill_source() -> None:
    assert assert_not_promotional("ticket NS-42: lost claim after a crash")
    for pitch in ("goodwill credit for a loyal user", "summer promo giveaway",
                  "marketing campaign credits", "referral bonus"):
        with pytest.raises(ManualGrantError):
            assert_not_promotional(pitch)


# [utest->req~grants-manual-never-promotional~1]
def test_a_promotional_reason_is_refused_before_the_procedure_starts() -> None:
    with pytest.raises(ManualGrantError):
        ManualGrantIssuance(request_for(reason="promotional credits for launch week"))
