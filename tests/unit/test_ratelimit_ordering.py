"""Where admission checks sit: the ordering rules of 08."""

import pytest

from nativespeaker.api.auth.challenges import ChallengeState
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.ratelimit.config import RateLimitsConfig
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import RateLimiter
from nativespeaker.api.ratelimit.ordering import (
    ANONYMOUS_GRANT_ADMISSION,
    DEVICE_BIT_BUDGET,
    GETUSER_BUDGET_ORDER,
    PRIMARY_GETUSER_BUDGET,
    AdmissionLedger,
    AdmissionOrderError,
    DeviceBitCall,
    DeviceBitWriteError,
    ExpensiveStep,
    GetUserCallSite,
    anonymous_grant_admission,
    assert_budgets_gate_getuser,
    assert_grant_row_permitted,
    evaluate_getuser_budgets,
    gate_getuser_call,
)

CLAIM = ("POST", "/auth/claim-anonymous-grant")


def admitted(method: str = "POST", path: str = "/auth/claim-anonymous-grant") -> AdmissionLedger:
    ledger = AdmissionLedger(method, path)
    ledger.verify_jwt()
    ledger.admit_barrier()
    return ledger


# --- Rejection precedes expensive work ----------------------------------------------------------

# [utest->req~ratelimit-reject-before-expensive-steps~1]
@pytest.mark.parametrize("step", list(ExpensiveStep))
def test_an_expensive_step_runs_only_after_the_limits_that_guard_it(step):
    # The guarding set is the route's own: a caller that declares nothing still cannot take an
    # expensive step before the entries this operation configures have been evaluated.
    ledger = admitted()
    assert set(ledger.applicable_entries()) == {"claim_anonymous_grant",
                                                "claim_anonymous_grant_ip"}
    with pytest.raises(AdmissionOrderError, match="must be evaluated"):
        ledger.expensive_step(step)
    ledger.evaluate("claim_anonymous_grant_ip", (KeyComponent.ip,))
    with pytest.raises(AdmissionOrderError, match="must be evaluated"):
        ledger.expensive_step(step)
    ledger.evaluate("claim_anonymous_grant", (KeyComponent.user,))
    ledger.expensive_step(step)
    assert ledger.expensive_steps == [step]


# [utest->req~ratelimit-reject-before-expensive-steps~1]
def test_a_rejected_request_takes_no_expensive_step():
    ledger = admitted()
    ledger.evaluate("claim_anonymous_grant", (KeyComponent.user,), allowed=False)
    with pytest.raises(AdmissionOrderError, match="only for an admitted request"):
        ledger.expensive_step(ExpensiveStep.firebase_lookup)


# [utest->req~ratelimit-reject-before-expensive-steps~1]
def test_the_guarding_entries_come_from_the_route_and_the_phase():
    # A prepare is guarded by the prepare-phase counters, a completion by its own.
    prepare = AdmissionLedger(*CLAIM, mode=RequestMode.prepare)
    assert set(prepare.applicable_entries()) == {"claim_anonymous_grant_prepare",
                                                 "claim_anonymous_grant_prepare_ip"}
    # An operation with no challenge is guarded by every entry it configures.
    sync = AdmissionLedger("POST", "/auth/sync")
    assert sync.applicable_entries() == ("auth_sync",)
    # A route outside the inventory configures no named entry, so it derives none.
    assert AdmissionLedger("GET", "/chats").applicable_entries() == ()


# --- Identity- and user-keyed limits --------------------------------------------------------------

# [utest->req~ratelimit-identity-keyed-after-jwt-verification~1]
def test_an_identity_keyed_limit_waits_for_jwt_verification_but_an_ip_keyed_one_does_not():
    ledger = AdmissionLedger(*CLAIM)
    # IP-keyed limits require no verified identity and may run at any position.
    ledger.evaluate("claim_anonymous_grant_ip", (KeyComponent.ip,))
    with pytest.raises(AdmissionOrderError, match="only after JWT verification"):
        ledger.evaluate("auth_sync", (KeyComponent.issuer, KeyComponent.subject_hash))
    ledger.verify_jwt()
    ledger.evaluate("auth_sync", (KeyComponent.issuer, KeyComponent.subject_hash))
    assert ledger.evaluated == ["claim_anonymous_grant_ip", "auth_sync"]


# [utest->req~ratelimit-user-keyed-after-barrier-admission~1]
def test_a_user_keyed_limit_waits_for_barrier_admission():
    ledger = AdmissionLedger(*CLAIM)
    ledger.verify_jwt()
    # A request the barrier has not admitted — a pre-auth, historical or blocked identity —
    # never reaches a user-keyed limiter.
    with pytest.raises(AdmissionOrderError, match="only after the barrier admitted"):
        ledger.evaluate("claim_anonymous_grant", (KeyComponent.user,))
    # It is still bounded by IP-keyed limits and the generic default entry.
    ledger.evaluate("claim_anonymous_grant_ip", (KeyComponent.ip,))
    ledger.evaluate("default", (KeyComponent.ip,))
    ledger.admit_barrier()
    ledger.evaluate("claim_anonymous_grant", (KeyComponent.user,))
    assert ledger.evaluated[-1] == "claim_anonymous_grant"


# [utest->req~ratelimit-user-keyed-after-barrier-admission~1]
def test_the_barrier_admits_nothing_before_token_verification():
    with pytest.raises(AdmissionOrderError, match="before token verification"):
        AdmissionLedger(*CLAIM).admit_barrier()


# --- Coarse then endpoint-specific ------------------------------------------------------------------

# [utest->req~ratelimit-coarse-then-endpoint-specific-limit~1]
def test_a_coarse_limit_may_precede_the_endpoint_specific_one():
    ledger = admitted()
    ledger.coarse_then_endpoint_specific(
        ("claim_anonymous_grant_ip", (KeyComponent.ip,)),
        ("claim_registered_grant", (KeyComponent.user, KeyComponent.idp_account_hash)))
    assert ledger.evaluated == ["claim_anonymous_grant_ip", "claim_registered_grant"]
    ledger.evaluate("claim_anonymous_grant", (KeyComponent.user,))
    # `guarded_by` only adds to the set the route already requires.
    ledger.expensive_step(ExpensiveStep.proof_verification,
                          guarded_by=["claim_registered_grant"])
    # The coarse limit is an IP, verified-token-subject or user limit, never something stronger.
    with pytest.raises(AdmissionOrderError, match="no coarse"):
        admitted().coarse_then_endpoint_specific(
            ("weird", (KeyComponent.provider, KeyComponent.external_id)),
            ("claim_anonymous_grant", (KeyComponent.user,)))


# --- The anonymous-grant admission pair -----------------------------------------------------------

# [utest->req~ratelimit-grant-claim-admission-keys~1]
def test_the_ip_counter_runs_at_route_entry_and_the_user_counter_after_the_barrier():
    ledger = AdmissionLedger(*CLAIM)
    ledger.verify_jwt()
    with pytest.raises(AdmissionOrderError, match="once the barrier has admitted"):
        anonymous_grant_admission(ledger, "complete")
    assert ledger.evaluated == ["claim_anonymous_grant_ip"]
    ledger.admit_barrier()
    anonymous_grant_admission(ledger, "complete")
    assert ledger.evaluated[-2:] == ["claim_anonymous_grant_ip", "claim_anonymous_grant"]
    assert ANONYMOUS_GRANT_ADMISSION["prepare"] == ("claim_anonymous_grant_prepare_ip",
                                                    "claim_anonymous_grant_prepare")


# [utest->req~ratelimit-grant-claim-admission-keys~1]
def test_both_counters_of_the_pair_must_pass_and_the_user_counter_precedes_the_vendor_work():
    ledger = admitted()
    anonymous_grant_admission(ledger, "complete", ip_allowed=False)
    with pytest.raises(AdmissionOrderError, match="only for an admitted request"):
        ledger.expensive_step(ExpensiveStep.provider_call)
    other = admitted()
    anonymous_grant_admission(other, "complete", user_allowed=False)
    with pytest.raises(AdmissionOrderError, match="claims no operation challenge"):
        other.claim_challenge(["claim_anonymous_grant_ip", "claim_anonymous_grant"])


# --- Prepare and complete around the challenge ------------------------------------------------------

# [utest->req~ratelimit-prepare-limits-before-challenge-issue~1]
def test_prepare_limits_run_before_the_challenge_is_issued():
    ledger = admitted()
    with pytest.raises(AdmissionOrderError, match="before an operation challenge is issued"):
        ledger.issue_challenge(["claim_anonymous_grant_prepare_ip",
                                "claim_anonymous_grant_prepare"])
    anonymous_grant_admission(ledger, "prepare")
    ledger.issue_challenge(["claim_anonymous_grant_prepare_ip", "claim_anonymous_grant_prepare"])
    assert ledger.challenge_issued


# [utest->req~ratelimit-complete-limits-before-challenge-claim~1]
def test_complete_limits_run_before_the_claim_and_neither_claim_nor_consume_the_challenge():
    ledger = admitted()
    with pytest.raises(AdmissionOrderError, match="before the operation challenge is claimed"):
        ledger.claim_challenge(["claim_anonymous_grant_ip", "claim_anonymous_grant"])
    anonymous_grant_admission(ledger, "complete")
    # Evaluating the limits left the challenge untouched.
    assert not ledger.challenge_claimed
    ledger.claim_challenge(["claim_anonymous_grant_ip", "claim_anonymous_grant"])
    assert ledger.challenge_claimed
    # After the claim there is no further complete-phase limit.
    with pytest.raises(AdmissionOrderError, match="runs before the challenge is claimed"):
        ledger.evaluate("claim_anonymous_grant", (KeyComponent.user,))


# [utest->req~ratelimit-complete-limits-before-challenge-claim~1]
def test_the_completion_claims_the_challenge_before_any_provider_call():
    ledger = admitted()
    anonymous_grant_admission(ledger, "complete")
    ledger.expensive_step(ExpensiveStep.provider_call)
    with pytest.raises(AdmissionOrderError, match="before any provider call"):
        ledger.claim_challenge(["claim_anonymous_grant_ip", "claim_anonymous_grant"])


# --- The Firebase Admin getUser budgets --------------------------------------------------------------

def _recorder():
    charged: list[str] = []

    def charge(names):
        charged.extend(names)

    return charged, charge


# [utest->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
def test_both_create_user_lookup_counters_gate_getuser_on_both_paths():
    for site in (GetUserCallSite.create_user_anonymous_completion,
                 GetUserCallSite.create_user_registered_completion):
        assert GETUSER_BUDGET_ORDER[site] == ("adapter_firebase_lookup",
                                              "create_user_firebase_identity_lookup",
                                              "create_user_firebase_identity_lookup_ip")
        assert_budgets_gate_getuser(site, GETUSER_BUDGET_ORDER[site])
        with pytest.raises(AdmissionOrderError, match="gates getUser on"):
            assert_budgets_gate_getuser(site, ("adapter_firebase_lookup",))
    assert GETUSER_BUDGET_ORDER[GetUserCallSite.upgrade_anonymous_to_registered] == (
        "adapter_firebase_lookup",
        "upgrade_anonymous_to_registered_firebase_identity_lookup")


# [utest->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
def test_a_lookup_budget_that_cannot_be_evaluated_fails_closed():
    charged, charge = _recorder()

    def broken(name: str) -> bool:
        if name == "create_user_firebase_identity_lookup_ip":
            raise ConnectionError("the limits backend is unavailable")
        return True

    verdict = evaluate_getuser_budgets(GetUserCallSite.create_user_anonymous_completion,
                                       test=broken, charge=charge)
    assert not verdict.allowed
    assert verdict.exhausted == ("create_user_firebase_identity_lookup_ip",)
    assert charged == []


# [utest->req~ratelimit-getuser-budget-evaluation-order~1]
def test_budgets_are_tested_broadest_to_narrowest_then_charged_together():
    seen: list[str] = []
    charged, charge = _recorder()
    verdict = evaluate_getuser_budgets(GetUserCallSite.create_user_anonymous_completion,
                                       test=lambda name: (seen.append(name), True)[1],
                                       charge=charge)
    assert seen == ["adapter_firebase_lookup", "create_user_firebase_identity_lookup",
                    "create_user_firebase_identity_lookup_ip"]
    assert verdict.allowed and charged == seen
    assert verdict.charged == tuple(seen)


# [utest->req~ratelimit-getuser-budget-evaluation-order~1]
def test_a_rejection_charges_no_counter_at_either_layer():
    charged, charge = _recorder()
    # The global budget is exhausted: the endpoint-layer allowance is not depleted.
    verdict = evaluate_getuser_budgets(
        GetUserCallSite.create_user_anonymous_completion,
        test=lambda name: name != "adapter_firebase_lookup", charge=charge)
    assert not verdict.allowed and charged == []
    # An endpoint-layer bound is over: global capacity is not burned either.
    charged2, charge2 = _recorder()
    verdict2 = evaluate_getuser_budgets(
        GetUserCallSite.create_user_anonymous_completion,
        test=lambda name: name != "create_user_firebase_identity_lookup_ip", charge=charge2)
    assert not verdict2.allowed and charged2 == []


# [utest->req~ratelimit-getuser-budget-evaluation-order~1]
def test_the_global_budget_is_the_primary_result_and_every_exhausted_limiter_is_recorded():
    verdict = evaluate_getuser_budgets(GetUserCallSite.create_user_anonymous_completion,
                                       test=lambda name: False,
                                       charge=lambda names: None)
    assert verdict.primary == PRIMARY_GETUSER_BUDGET
    assert verdict.exhausted == ("adapter_firebase_lookup",
                                 "create_user_firebase_identity_lookup",
                                 "create_user_firebase_identity_lookup_ip")
    # With only an endpoint-layer entry exhausted, that entry is the reported result.
    only_ip = evaluate_getuser_budgets(
        GetUserCallSite.create_user_anonymous_completion,
        test=lambda name: name != "create_user_firebase_identity_lookup_ip",
        charge=lambda names: None)
    assert only_ip.primary == "create_user_firebase_identity_lookup_ip"


# [utest->req~ratelimit-getuser-budget-evaluation-order~1]
def test_each_permitted_retry_charges_the_budgets_again():
    charged, charge = _recorder()
    for _ in range(2):
        evaluate_getuser_budgets(GetUserCallSite.upgrade_anonymous_to_registered,
                                 test=lambda name: True, charge=charge)
    assert charged == ["adapter_firebase_lookup",
                       "upgrade_anonymous_to_registered_firebase_identity_lookup"] * 2


# [utest->req~ratelimit-getuser-budget-evaluation-order~1]
# [utest->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
def test_a_real_limiter_charges_nothing_when_one_budget_is_already_over():
    data: dict = {
        "enabled": True, "storage_uri": "memory://", "strategy": "moving-window",
        "default": {"limit": "120/minute", "key": "ip"},
        "adapter_firebase_lookup": {"limit": "30/minute", "key": "deployment"},
        "create_user_firebase_identity_lookup": {"limit": "60/minute", "key": "deployment"},
        "create_user_firebase_identity_lookup_ip": {"limit": "1/minute", "key": "ip"}}
    limiter = RateLimiter(RateLimitsConfig(**data))
    keys = {"adapter_firebase_lookup": "d", "create_user_firebase_identity_lookup": "d",
            "create_user_firebase_identity_lookup_ip": "1.2.3.4"}
    site = GetUserCallSite.create_user_registered_completion
    assert gate_getuser_call(limiter, site, keys).allowed
    # The narrow client-IP budget is now exhausted, so the whole gate refuses...
    refused = gate_getuser_call(limiter, site, keys)
    assert not refused.allowed
    assert refused.exhausted == ("create_user_firebase_identity_lookup_ip",)
    # ...and the global budget was not charged by the refused attempt.
    assert limiter.test("adapter_firebase_lookup", "d").allowed
    for _ in range(29):
        limiter.hit("adapter_firebase_lookup", "d")
    assert not limiter.test("adapter_firebase_lookup", "d").allowed


# --- The free-grant device-bit budgets -----------------------------------------------------------------

def _claimed() -> AdmissionLedger:
    ledger = admitted()
    anonymous_grant_admission(ledger, "complete")
    ledger.claim_challenge(["claim_anonymous_grant_ip", "claim_anonymous_grant"])
    return ledger


# [utest->req~ratelimit-free-grant-device-bit-budget-ordering~1]
def test_endpoint_admission_passes_before_the_claim_and_budgets_are_checked_after_it():
    ledger = admitted()
    anonymous_grant_admission(ledger, "complete")
    with pytest.raises(AdmissionOrderError, match="after the challenge has been claimed"):
        ledger.check_device_bit_budget(DeviceBitCall.devicecheck_read)
    ledger.claim_challenge(["claim_anonymous_grant_ip", "claim_anonymous_grant"])
    ledger.check_device_bit_budget(DeviceBitCall.devicecheck_read)
    assert ledger.budgets_checked == ["adapter_devicecheck_read"]


# [utest->req~ratelimit-free-grant-device-bit-budget-ordering~1]
def test_each_budget_is_checked_immediately_before_the_vendor_call_it_budgets():
    ledger = _claimed()
    with pytest.raises(AdmissionOrderError, match="checked immediately before"):
        ledger.vendor_device_bit_call(DeviceBitCall.device_recall_read)
    ledger.check_device_bit_budget(DeviceBitCall.device_recall_read)
    ledger.vendor_device_bit_call(DeviceBitCall.device_recall_read)
    ledger.check_device_bit_budget(DeviceBitCall.device_recall_write)
    ledger.vendor_device_bit_call(DeviceBitCall.device_recall_write)
    ledger.insert_grant_row()
    assert DEVICE_BIT_BUDGET[DeviceBitCall.device_recall_write] == \
        "adapter_play_integrity_device_recall_write"


# [utest->req~ratelimit-free-grant-device-bit-budget-ordering~1]
def test_a_challenge_that_fails_validation_charges_no_device_bit_budget():
    ledger = admitted()
    anonymous_grant_admission(ledger, "complete")
    ledger.fail_challenge_validation()
    with pytest.raises(AdmissionOrderError, match="charges no device-bit budget"):
        ledger.check_device_bit_budget(DeviceBitCall.devicecheck_read)
    assert ledger.budgets_checked == []


# [utest->req~ratelimit-free-grant-device-bit-budget-ordering~1]
def test_an_exhausted_read_budget_prevents_the_read_and_every_later_step():
    ledger = _claimed()
    ledger.check_device_bit_budget(DeviceBitCall.devicecheck_read, allowed=False)
    with pytest.raises(AdmissionOrderError, match="prevents the call it budgets"):
        ledger.vendor_device_bit_call(DeviceBitCall.devicecheck_read)
    with pytest.raises(AdmissionOrderError, match="every later step"):
        ledger.check_device_bit_budget(DeviceBitCall.devicecheck_write)
    with pytest.raises(AdmissionOrderError, match="refused claim creates no grant row"):
        ledger.insert_grant_row()


# [utest->req~ratelimit-free-grant-device-bit-budget-ordering~1]
def test_an_exhausted_write_budget_prevents_the_write_and_the_grant_after_a_good_read():
    ledger = _claimed()
    ledger.check_device_bit_budget(DeviceBitCall.devicecheck_read)
    ledger.vendor_device_bit_call(DeviceBitCall.devicecheck_read)
    ledger.check_device_bit_budget(DeviceBitCall.devicecheck_write, allowed=False)
    with pytest.raises(AdmissionOrderError, match="prevents the call it budgets"):
        ledger.vendor_device_bit_call(DeviceBitCall.devicecheck_write)
    with pytest.raises(AdmissionOrderError, match="refused claim creates no grant row"):
        ledger.insert_grant_row()


# [utest->req~ratelimit-free-grant-device-bit-budget-ordering~1]
def test_the_grant_row_needs_its_own_read_and_a_confirmed_write():
    ledger = _claimed()
    with pytest.raises(AdmissionOrderError, match="performs its own vendor bit read"):
        ledger.insert_grant_row()
    ledger.check_device_bit_budget(DeviceBitCall.devicecheck_read)
    ledger.vendor_device_bit_call(DeviceBitCall.devicecheck_read)
    with pytest.raises(AdmissionOrderError, match="confirms the bit write"):
        ledger.insert_grant_row()
    # A write is never attempted before the claim performed its own read.
    fresh = _claimed()
    with pytest.raises(AdmissionOrderError, match="performs its own vendor bit read first"):
        fresh.check_device_bit_budget(DeviceBitCall.devicecheck_write)


# The ledger owns the vendor-confirmation rule, so an unconfirmed write is refused at the one
# guard the adapter layer shares with it.
# [utest->req~ratelimit-device-bit-write-load-bearing~1]
def test_an_unconfirmed_vendor_write_permits_no_grant_row():
    ledger = _claimed()
    ledger.check_device_bit_budget(DeviceBitCall.devicecheck_read)
    ledger.vendor_device_bit_call(DeviceBitCall.devicecheck_read)
    ledger.check_device_bit_budget(DeviceBitCall.devicecheck_write)
    write = ledger.vendor_device_bit_call(DeviceBitCall.devicecheck_write, confirmed=False)
    assert write is not None and write.confirmed is False
    assert ledger.confirmed_write() is None
    with pytest.raises(DeviceBitWriteError, match="confirms the bit write"):
        ledger.insert_grant_row()
    with pytest.raises(DeviceBitWriteError):
        assert_grant_row_permitted(write)


# --- The challenge decision points -----------------------------------------------------------

class _Endpoint:
    """A minimal challenge endpoint whose hooks all succeed."""

    def __init__(self, operation):
        self.operation = operation

    async def check_prepare_eligibility(self, identity, variant):
        return None

    async def verify_proof(self, identity, challenge, body):
        return {}

    async def confirm_live_state(self, session, identity, challenge):
        return {}

    async def mutate(self, session, identity, challenge, proof, live):
        return {"ok": True}


# [utest->req~ratelimit-prepare-limits-before-challenge-issue~1]
async def test_the_shared_prepare_cannot_issue_a_challenge_before_its_prepare_limits():
    from unit.test_auth_challenges import Harness, linked_context

    harness = Harness()
    operation = AuthOperation.claim_anonymous_grant
    endpoint = _Endpoint(operation)
    ledger = AdmissionLedger(*CLAIM, mode=RequestMode.prepare)
    ledger.verify_jwt()
    ledger.admit_barrier()
    # No prepare-phase limit has been evaluated, so no challenge row may be created.
    with pytest.raises(AdmissionOrderError, match="before an operation challenge is issued"):
        await harness.service.prepare(operation, None, linked_context(), endpoint,
                                      admission=ledger)
    assert harness.store.rows == {}

    anonymous_grant_admission(ledger, "prepare")
    await harness.service.prepare(operation, None, linked_context(), endpoint, admission=ledger)
    assert len(harness.store.rows) == 1
    assert ledger.challenge_issued


# [utest->req~ratelimit-complete-limits-before-challenge-claim~1]
async def test_the_shared_completion_cannot_claim_a_challenge_before_its_complete_limits():
    from unit.test_auth_challenges import Harness, linked_context

    harness = Harness()
    operation = AuthOperation.claim_anonymous_grant
    endpoint = _Endpoint(operation)
    await harness.service.prepare(operation, None, linked_context(), endpoint)
    row = next(iter(harness.store.rows.values()))
    context = linked_context(row.binding.bound_external_identity_id)

    ledger = AdmissionLedger(*CLAIM, mode=RequestMode.completion)
    ledger.verify_jwt()
    ledger.admit_barrier()
    with pytest.raises(AdmissionOrderError, match="before the operation challenge is claimed"):
        await harness.service.complete(operation, None, row.challenge_id, context, endpoint,
                                       admission=ledger)
    # Nothing claimed it, so the row is still issued and a properly admitted retry works.
    assert harness.store.rows[row.challenge_id].state is ChallengeState.issued
    anonymous_grant_admission(ledger, "complete")
    await harness.service.complete(operation, None, row.challenge_id, context, endpoint,
                                   admission=ledger)
    assert ledger.challenge_claimed
    assert harness.store.rows[row.challenge_id].state is ChallengeState.consumed
