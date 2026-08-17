"""Backend restore admission control: the named limits, their order, the provider-call budgets and
the coalescing of live provider verification."""

import asyncio
from pathlib import Path

import pytest
import yaml

from nativespeaker.api.auth.audit import AttemptPhase, AuthAttempt, AuthEventResult
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.restore import RestoreAttemptAudit
from nativespeaker.api.auth.restore_admission import (
    DELETED_CHALLENGE_ENTRIES,
    LIVE_VERIFICATION_CALLS,
    PROVIDER_CALL_BUDGETS,
    RESTORE_ADMISSION_COUNTERS,
    RESTORE_ADMISSION_ENTRIES,
    RESTORE_ADMISSION_KEYS,
    ProofVerifiedParticipant,
    ProviderCallBudget,
    RestoreAdmissionError,
    RestoreCoalescer,
    assert_admission_order,
    assert_budget_exhaustion_is_admission,
    assert_follower_completes_own_work,
    assert_lock_wait_confers_no_result,
    assert_observation_only,
    assert_one_call_per_request,
    assert_operational_counters,
    assert_restore_admission_policy_configured,
    assert_restore_admission_required,
    assert_telemetry_only,
    assert_waiters_share_the_outcome,
    consume_provider_call_unit,
    destination_user_entries,
    dispatch_under_budget,
    may_reuse,
    participant,
    proof_fingerprint_entries,
    provider_call_budget,
    provider_call_budget_rejection,
    release_undispatched_unit,
    request_rate_entries,
    restore_admission_rejection,
    restore_keyed_limits_admission,
    restore_request_rate_admission,
    store_subscription_entries,
    verify_restore_proof,
)
from nativespeaker.api.auth.restore_flow import VerifiedTransaction
from nativespeaker.api.ratelimit.config import (
    RateLimitEntry,
    RateLimitsConfig,
    Strategy,
)
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import LimitDecision, RateLimiter
from nativespeaker.api.ratelimit.ordering import AdmissionLedger, ExpensiveStep
from nativespeaker.api.ratelimit.providers import (
    CoalescingError,
    ProviderDampingConfig,
)
from nativespeaker.api.ratelimit.rejection import (
    AdmissionPhaseError,
    RateLimitMetrics,
    SecurityTelemetry,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
EXTERNAL_ID = "2000000123456789"
APPLE = StoreProvider.apple
VERIFIED = VerifiedTransaction(provider=APPLE, external_id=EXTERNAL_ID)


def shipped() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def shipped_rate_limits() -> RateLimitsConfig:
    return RateLimitsConfig(**shipped()["rate_limits"])


def shipped_damping() -> ProviderDampingConfig:
    return ProviderDampingConfig(**shipped()["provider_damping"])


def budget_limiter(**entries: str) -> RateLimiter:
    config = RateLimitsConfig(enabled=True, storage_uri="memory://",
                              strategy=Strategy.moving_window,
                              default=RateLimitEntry(limit="120/minute", key="ip"),
                              entries={name: RateLimitEntry(limit=limit, key="deployment")
                                       for name, limit in entries.items()})
    return RateLimiter(config)


def admitted_ledger() -> AdmissionLedger:
    ledger = AdmissionLedger("POST", "/auth/restore-subscription")
    ledger.verify_jwt()
    ledger.admit_barrier()
    return ledger


def restore_attempt() -> AuthAttempt:
    return AuthAttempt("POST", "/auth/restore-subscription")


def refusal(limiter: str = "restore_subscription_user") -> LimitDecision:
    return LimitDecision(allowed=False, limiter=limiter, retry_after_seconds=30,
                         exhausted=(limiter,))


# --- What restore admission control is ----------------------------------------------------------


# [utest->req~restore-admission-control-required~1]
def test_restore_enforces_backend_admission_control_additional_to_the_gateway():
    config = shipped_rate_limits()
    entries = assert_restore_admission_required(config)
    assert entries == RESTORE_ADMISSION_ENTRIES
    # Every entry is keyed on restore data only the backend can derive, so none of them is a
    # restatement of a gateway ceiling on IP, subject or URL alone.
    backend_only = {KeyComponent.user, KeyComponent.restore_proof_fingerprint,
                    KeyComponent.provider, KeyComponent.external_id,
                    KeyComponent.issuer, KeyComponent.subject_hash}
    for name in entries:
        assert set(RESTORE_ADMISSION_KEYS[name]) <= backend_only


# [utest->req~restore-admission-control-required~1]
def test_the_deleted_challenge_limits_may_not_come_back():
    config = shipped_rate_limits()
    revived = config.model_copy(update={
        "entries": {**config.entries,
                    "restore_subscription_prepare": RateLimitEntry(limit="5/minute", key="user")}})
    with pytest.raises(RestoreAdmissionError, match="restore_subscription_prepare"):
        assert_restore_admission_required(revived)
    assert not DELETED_CHALLENGE_ENTRIES & set(config.entries)


# [utest->req~restore-admission-policy-config-required~1]
def test_the_shipped_config_defines_the_whole_restore_admission_policy():
    config = shipped_rate_limits()
    families = assert_restore_admission_policy_configured(config)
    assert set(families) == {"request_rate", "proof_fingerprints", "store_subscriptions",
                             "destination_users", "provider_call_budgets"}
    for names in families.values():
        for name in names:
            assert name in config.entries


# [utest->req~restore-admission-policy-config-required~1]
def test_a_missing_restore_policy_entry_is_a_startup_error():
    config = shipped_rate_limits()
    pruned = {name: entry for name, entry in config.entries.items()
              if name != "restore_subscription_proof_fingerprint_total"}
    stripped = config.model_copy(update={"entries": pruned})
    with pytest.raises(RestoreAdmissionError, match="proof_fingerprint_total"):
        assert_restore_admission_policy_configured(stripped)


# [utest->req~restore-admission-policy-config-required~1]
def test_a_restore_entry_configured_on_the_wrong_key_is_refused():
    config = shipped_rate_limits()
    rekeyed = {**config.entries,
               "restore_subscription_user": RateLimitEntry(limit="10/day", key="ip")}
    with pytest.raises(RestoreAdmissionError, match="restore_subscription_user"):
        assert_restore_admission_policy_configured(config.model_copy(update={"entries": rekeyed}))


# --- The five families ---------------------------------------------------------------------------


# [utest->req~restore-admission-limit-request-rate~1]
def test_request_rate_is_keyed_by_subject_and_by_destination_user():
    subject, user = request_rate_entries()
    assert RESTORE_ADMISSION_KEYS[subject] == (KeyComponent.issuer, KeyComponent.subject_hash)
    assert RESTORE_ADMISSION_KEYS[user] == (KeyComponent.user,)
    shipped_entries = shipped_rate_limits().entries
    assert shipped_entries[subject].policy == RESTORE_ADMISSION_KEYS[subject]
    assert shipped_entries[user].policy == RESTORE_ADMISSION_KEYS[user]


# [utest->req~restore-admission-limit-proof-fingerprints~1]
def test_proof_fingerprints_carry_a_failed_and_a_total_limit():
    failed, total = proof_fingerprint_entries()
    assert failed != total
    for name in (failed, total):
        assert RESTORE_ADMISSION_KEYS[name] == (KeyComponent.restore_proof_fingerprint,)
        assert shipped_rate_limits().entries[name].policy == (
            KeyComponent.restore_proof_fingerprint,)


# [utest->req~restore-admission-limit-store-subscriptions~1]
def test_store_subscriptions_carry_a_cross_account_and_a_live_verification_limit():
    cross_account, live_verification = store_subscription_entries()
    assert "cross_account" in cross_account and "live_verification" in live_verification
    for name in (cross_account, live_verification):
        assert RESTORE_ADMISSION_KEYS[name] == (KeyComponent.provider, KeyComponent.external_id)
        assert shipped_rate_limits().entries[name].policy == (KeyComponent.provider,
                                                              KeyComponent.external_id)


# [utest->req~restore-admission-limit-destination-users~1]
def test_destination_users_carry_a_rejected_cross_account_attempt_limit():
    entries = destination_user_entries()
    assert entries == ("restore_subscription_destination_rejected_cross_account",)
    assert RESTORE_ADMISSION_KEYS[entries[0]] == (KeyComponent.user,)
    assert shipped_rate_limits().entries[entries[0]].policy == (KeyComponent.user,)


# [utest->req~restore-admission-limit-provider-call-budgets~1]
def test_apple_and_google_carry_separate_global_provider_call_budgets():
    apple = provider_call_budget(StoreProvider.apple)
    google = provider_call_budget(StoreProvider.google_play)
    assert apple != google
    assert {apple, google} == set(PROVIDER_CALL_BUDGETS.values())
    entries = shipped_rate_limits().entries
    assert entries[apple].policy == (KeyComponent.deployment,)
    assert entries[google].policy == (KeyComponent.deployment,)


# --- Ordering ---------------------------------------------------------------------------------------


# [utest->req~restore-admission-order-request-rate-first~1]
def test_the_request_rate_limits_run_first_and_write_no_audit_row():
    ledger = admitted_ledger()
    audit = RestoreAttemptAudit()
    subject, user = restore_request_rate_admission(ledger, audit)
    assert ledger.evaluated == [subject, user]
    # An admission check writes nothing: the restore-attempt row this guards against is unwritten.
    assert audit.rows == ()


# [utest->req~restore-admission-order-request-rate-first~1]
def test_the_request_rate_limits_never_run_behind_another_restore_limit():
    ledger = admitted_ledger()
    failed, _total = proof_fingerprint_entries()
    ledger.evaluate(failed, RESTORE_ADMISSION_KEYS[failed])
    with pytest.raises(RestoreAdmissionError, match="run before"):
        restore_request_rate_admission(ledger, RestoreAttemptAudit())


# [utest->req~restore-admission-order-request-rate-first~1]
def test_the_request_rate_limits_never_run_behind_the_attempt_audit_row():
    audit = RestoreAttemptAudit()
    audit.record(phase=AttemptPhase.business,
                 result=AuthEventResult.invalid_restore_proof,
                 audit_transaction=object())
    with pytest.raises(RestoreAdmissionError, match="audit row"):
        restore_request_rate_admission(admitted_ledger(), audit)


# [utest->req~restore-admission-order-limits-before-proof-verification~1]
def test_the_keyed_limits_run_before_proof_verification_and_the_provider_call():
    ledger = admitted_ledger()
    audit = RestoreAttemptAudit()
    restore_request_rate_admission(ledger, audit)
    restore_keyed_limits_admission(ledger)
    assert set(ledger.evaluated) == set(RESTORE_ADMISSION_ENTRIES)
    verified = verify_restore_proof(ledger, lambda: VERIFIED)
    assert verified.key == (APPLE, EXTERNAL_ID)
    ledger.expensive_step(ExpensiveStep.live_store_verification)
    assert_admission_order(ledger.evaluated, ledger.expensive_steps)


# [utest->req~restore-admission-order-limits-before-proof-verification~1]
def test_the_keyed_limits_refuse_to_run_after_proof_verification():
    ledger = admitted_ledger()
    restore_request_rate_admission(ledger, RestoreAttemptAudit())
    with pytest.raises(RestoreAdmissionError, match="precede proof verification"):
        restore_keyed_limits_admission(ledger, proof_verified=True)


# [utest->req~restore-admission-order-limits-before-proof-verification~1]
def test_proof_verification_waits_for_every_named_restore_limit():
    ledger = admitted_ledger()
    restore_request_rate_admission(ledger, RestoreAttemptAudit())
    with pytest.raises(RestoreAdmissionError, match="before restore-proof verification"):
        verify_restore_proof(ledger, lambda: VERIFIED)


# [utest->req~restore-admission-order-limits-before-proof-verification~1]
def test_a_provider_call_before_proof_verification_is_out_of_order():
    with pytest.raises(RestoreAdmissionError, match="precedes coalescing"):
        assert_admission_order(RESTORE_ADMISSION_ENTRIES,
                               (ExpensiveStep.live_store_verification,
                                ExpensiveStep.proof_verification))


# --- The provider-call budget --------------------------------------------------------------------


# [utest->req~restore-admission-provider-call-budget-accounting~1]
def test_a_unit_is_consumed_immediately_before_each_dispatch_and_kept_however_it_resolves():
    entry = provider_call_budget(APPLE)
    backend = budget_limiter(**{entry: "2/minute"})
    budget = ProviderCallBudget(provider=APPLE)
    decision = consume_provider_call_unit(backend, budget, "deployment",
                                          endpoint_admission_passed=True)
    assert decision.allowed and budget.held == 1

    def failing_dispatch():
        raise RuntimeError("provider timed out")

    with pytest.raises(RuntimeError):
        dispatch_under_budget(budget, failing_dispatch)
    # The dispatched call keeps its unit: acquired and dispatched, nothing refunded.
    assert (budget.acquired, budget.dispatched, budget.released) == (1, 1, 0)


# [utest->req~restore-admission-provider-call-budget-accounting~1]
def test_units_are_acquired_one_at_a_time_and_never_reserved_up_front():
    entry = provider_call_budget(APPLE)
    backend = budget_limiter(**{entry: "5/minute"})
    budget = ProviderCallBudget(provider=APPLE)
    consume_provider_call_unit(backend, budget, "deployment", endpoint_admission_passed=True)
    with pytest.raises(RestoreAdmissionError, match="immediately before one dispatch"):
        consume_provider_call_unit(backend, budget, "deployment", endpoint_admission_passed=True)


# [utest->req~restore-admission-provider-call-budget-accounting~1]
def test_a_unit_reserved_but_unused_before_dispatch_is_released():
    entry = provider_call_budget(APPLE)
    backend = budget_limiter(**{entry: "5/minute"})
    budget = ProviderCallBudget(provider=APPLE)
    consume_provider_call_unit(backend, budget, "deployment", endpoint_admission_passed=True)
    release_undispatched_unit(budget)
    assert budget.held == 0 and budget.dispatched == 0
    with pytest.raises(RestoreAdmissionError, match="acquired, undispatched"):
        release_undispatched_unit(budget)


# [utest->req~restore-admission-provider-call-budget-accounting~1]
def test_an_exhausted_budget_makes_no_call_and_rejects_as_admission_control():
    entry = provider_call_budget(APPLE)
    backend = budget_limiter(**{entry: "1/minute"})
    metrics = RateLimitMetrics()
    first = ProviderCallBudget(provider=APPLE)
    consume_provider_call_unit(backend, first, "deployment", endpoint_admission_passed=True)
    dispatch_under_budget(first, lambda: "active")

    second = ProviderCallBudget(provider=APPLE)
    refused = consume_provider_call_unit(backend, second, "deployment",
                                         endpoint_admission_passed=True, metrics=metrics)
    assert refused.allowed is False and second.acquired == 0
    audit = RestoreAttemptAudit()
    rejection = provider_call_budget_rejection(restore_attempt(), SecurityTelemetry(), refused,
                                               metrics=metrics)
    assert rejection.error.status_code == 429
    assert rejection.audit_rows == 0 and audit.rows == ()
    assert metrics.counters()["provider_budget_rejections"] == 2
    with pytest.raises(RestoreAdmissionError, match="exactly one acquired unit"):
        dispatch_under_budget(second, lambda: "active")


# [utest->req~restore-admission-provider-call-budget-accounting~1]
def test_budget_exhaustion_is_never_a_verification_outcome():
    with pytest.raises(RestoreAdmissionError, match="restore_store_state_unverified"):
        assert_budget_exhaustion_is_admission(
            audited_result=AuthEventResult.restore_store_state_unverified)
    with pytest.raises(RestoreAdmissionError, match="restore_proof_rejected"):
        assert_budget_exhaustion_is_admission(client_class="restore_proof_rejected")
    assert_budget_exhaustion_is_admission(client_class="rate_limited")


# [utest->req~restore-admission-one-call-per-request~1]
def test_exactly_one_live_provider_call_per_restore_request():
    entry = provider_call_budget(APPLE)
    backend = budget_limiter(**{entry: "5/minute"})
    budget = ProviderCallBudget(provider=APPLE)
    consume_provider_call_unit(backend, budget, "deployment", endpoint_admission_passed=True)
    dispatch_under_budget(budget, lambda: "active")
    assert assert_one_call_per_request(budget) == 1
    consume_provider_call_unit(backend, budget, "deployment", endpoint_admission_passed=True)
    with pytest.raises(RestoreAdmissionError, match="exactly one live provider call"):
        dispatch_under_budget(budget, lambda: "active")


# [utest->req~restore-admission-one-call-per-request~1]
def test_admission_is_evaluated_once_per_incoming_request():
    budget = ProviderCallBudget(provider=APPLE, acquired=1, dispatched=1)
    with pytest.raises(RestoreAdmissionError, match="once per incoming request"):
        assert_one_call_per_request(budget, admission_evaluations=2)


# --- Rejection behaviour -----------------------------------------------------------------------------


# [utest->req~restore-admission-rejection-429~1]
def test_a_restore_admission_rejection_returns_429():
    rejection = restore_admission_rejection(restore_attempt(), SecurityTelemetry(), refusal())
    assert rejection.error.status_code == 429
    assert rejection.error.client.headers["Retry-After"] == "30"


# [utest->req~restore-admission-rejection-carve-out~1]
def test_a_restore_admission_rejection_never_joins_the_audited_attempt_path():
    attempt = restore_attempt()
    rejection = restore_admission_rejection(attempt, SecurityTelemetry(), refusal())
    assert rejection.audit_rows == 0 and rejection.database_rows == 0
    assert attempt.audited is False
    # Once the attempt has been audited, it is past the carve-out and no admission rejection
    # can be taken for it.
    attempt.audited = True
    with pytest.raises(AdmissionPhaseError, match="audit row"):
        restore_admission_rejection(attempt, SecurityTelemetry(), refusal())


# [utest->req~restore-admission-rejection-telemetry-only~1]
def test_an_admission_rejection_records_aggregate_telemetry_and_nothing_else():
    telemetry = SecurityTelemetry()
    audit = RestoreAttemptAudit()
    rejection = restore_admission_rejection(restore_attempt(), telemetry, refusal())
    assert telemetry.labels() == [("/auth/restore-subscription", "restore_subscription_user",
                                   "authenticated")]
    assert_telemetry_only(telemetry, audit, {"route": rejection.telemetry.route,
                                             "reason": rejection.telemetry.reason,
                                             "actor": str(rejection.telemetry.actor)})
    with pytest.raises(AdmissionPhaseError, match="restore_proof"):
        assert_telemetry_only(telemetry, audit, {"route": "r", "reason": "x", "actor": "a",
                                                 "restore_proof": "secret"})


# [utest->req~restore-admission-rejection-telemetry-only~1]
def test_an_admission_rejection_never_leaves_a_restore_audit_row():
    audit = RestoreAttemptAudit()
    audit.record(phase=AttemptPhase.business,
                 result=AuthEventResult.invalid_restore_proof,
                 audit_transaction=object())
    with pytest.raises(RestoreAdmissionError, match="no restore audit row"):
        assert_telemetry_only(SecurityTelemetry(), audit,
                              {"route": "r", "reason": "x", "actor": "a"})


# --- Coalescing -------------------------------------------------------------------------------------


# [utest->req~restore-coalescing-serialize-provider-verification~1]
async def test_concurrent_verifications_of_one_store_subscription_share_one_call():
    coalescer = RestoreCoalescer(shipped_damping())
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"provider": str(APPLE), "external_id": EXTERNAL_ID, "store_state": "active"}

    joining = participant(VERIFIED, APPLE, EXTERNAL_ID)
    leader = asyncio.create_task(coalescer.verify(joining, dispatch, budget=lambda: 1))
    await started.wait()
    follower = asyncio.create_task(coalescer.verify(joining, dispatch, budget=lambda: 1))
    await asyncio.sleep(0)
    release.set()
    lead, follow = await asyncio.gather(leader, follower)
    assert calls == 1
    assert lead.dispatched and not follow.dispatched
    assert lead.observation == follow.observation
    # One shared call, one budget unit.
    assert (lead.budget_units, follow.budget_units) == (1, 0)


# [utest->req~restore-coalescing-serialize-provider-verification~1]
def test_the_serialization_lock_is_per_store_subscription():
    coalescer = RestoreCoalescer(shipped_damping())
    assert coalescer.lock(APPLE, EXTERNAL_ID) is coalescer.lock(APPLE, EXTERNAL_ID)
    assert coalescer.lock(APPLE, EXTERNAL_ID) is not coalescer.lock(APPLE, "other")
    assert coalescer.lock(APPLE, EXTERNAL_ID) is not coalescer.lock(StoreProvider.google_play,
                                                                    EXTERNAL_ID)


# [utest->req~restore-coalescing-join-requires-verified-proof~1]
def test_a_request_joins_only_on_its_own_proof_resolved_to_that_store_subscription():
    with pytest.raises(CoalescingError, match="never joins"):
        participant(VERIFIED, APPLE, EXTERNAL_ID, proof_verified=False)
    with pytest.raises(CoalescingError, match="resolved to"):
        participant(VERIFIED, APPLE, "a-different-subscription")
    with pytest.raises(RestoreAdmissionError, match="no provider call"):
        participant(VERIFIED, APPLE, EXTERNAL_ID, provider_calls_used_to_verify=1)


# [utest->req~restore-coalescing-join-requires-verified-proof~1]
async def test_a_request_whose_proof_failed_never_sees_the_result():
    coalescer = RestoreCoalescer(shipped_damping())
    unverified = ProofVerifiedParticipant(provider=APPLE, external_id=EXTERNAL_ID,
                                          proof_verified=False)

    async def dispatch():
        return {"provider": str(APPLE), "external_id": EXTERNAL_ID, "store_state": "active"}

    with pytest.raises(CoalescingError, match="its own restore_proof"):
        await coalescer.verify(unverified, dispatch)


# [utest->req~restore-coalescing-lock-wait-confers-no-result~1]
def test_waiting_on_the_lock_confers_no_result():
    with pytest.raises(CoalescingError, match="confers no result"):
        assert_lock_wait_confers_no_result(waited_on_lock=True, joined_as_participant=False,
                                           budget_units_consumed=0,
                                           observation={"store_state": "active"})
    with pytest.raises(CoalescingError, match="independently budgeted"):
        assert_lock_wait_confers_no_result(waited_on_lock=True, joined_as_participant=False,
                                           budget_units_consumed=0)
    # Its own budgeted call after waiting is what a non-participant needs.
    assert_lock_wait_confers_no_result(waited_on_lock=True, joined_as_participant=False,
                                       budget_units_consumed=1)


# [utest->req~restore-coalescing-shared-outcome-single-budget-unit~1]
async def test_waiters_share_a_failed_leaders_outcome_without_a_second_call():
    coalescer = RestoreCoalescer(shipped_damping())
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        raise RuntimeError("apple returned 503")

    joining = participant(VERIFIED, APPLE, EXTERNAL_ID)
    leader = asyncio.create_task(coalescer.verify(joining, dispatch, budget=lambda: 1))
    await started.wait()
    follower = asyncio.create_task(coalescer.verify(joining, dispatch, budget=lambda: 1))
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(leader, follower, return_exceptions=True)
    assert all(isinstance(one, RuntimeError) for one in results)
    assert calls == 1
    assert_waiters_share_the_outcome(leader_failed=True, waiter_dispatched=False,
                                     budget_units=calls, waiters=1)


# [utest->req~restore-coalescing-shared-outcome-single-budget-unit~1]
def test_a_shared_attempt_debits_the_budget_once_not_once_per_waiter():
    with pytest.raises(CoalescingError, match="launches no second call"):
        assert_waiters_share_the_outcome(leader_failed=True, waiter_dispatched=True,
                                         budget_units=1, waiters=1)
    with pytest.raises(CoalescingError, match="one shared attempt debits one unit"):
        assert_waiters_share_the_outcome(leader_failed=False, waiter_dispatched=False,
                                         budget_units=2, waiters=1)


# [utest->req~restore-coalescing-shares-only-provider-observation~1]
def test_only_the_raw_store_state_observation_is_shared():
    observation = {"provider": str(APPLE), "external_id": EXTERNAL_ID, "store_state": "active"}
    assert assert_observation_only(observation) is observation
    with pytest.raises(CoalescingError, match="user_id"):
        assert_observation_only({**observation, "user_id": "another-caller"})
    with pytest.raises(CoalescingError, match="entitled_token"):
        assert_observation_only({**observation, "entitled_token": "attach-me-anywhere"})
    with pytest.raises(CoalescingError, match="restore_proof"):
        assert_observation_only({**observation, "restore_proof": "secret"})


# [utest->req~restore-coalescing-shares-only-provider-observation~1]
def test_every_follower_completes_its_own_authorization_and_processing():
    joining = participant(VERIFIED, APPLE, EXTERNAL_ID)
    observation = {"provider": str(APPLE), "external_id": EXTERNAL_ID, "store_state": "active"}
    assert_follower_completes_own_work(
        follower=joining, calling_subject_user_id="user-1", observation=observation,
        completed=("user_and_account_authorization", "database_conflict_checks",
                   "transactional_grant_and_ownership_processing"))
    with pytest.raises(CoalescingError, match="own"):
        assert_follower_completes_own_work(
            follower=joining, calling_subject_user_id="user-1", observation=observation,
            completed=("user_and_account_authorization",))
    with pytest.raises(CoalescingError, match="proof-derived subscription"):
        assert_follower_completes_own_work(
            follower=participant(VERIFIED, APPLE, EXTERNAL_ID),
            calling_subject_user_id="user-1",
            observation={**observation, "external_id": "someone-elses"},
            completed=("user_and_account_authorization", "database_conflict_checks",
                       "transactional_grant_and_ownership_processing"))


# [utest->req~restore-coalescing-reuse-only-while-fresh~1]
def test_a_coalesced_result_is_reusable_only_inside_the_configured_freshness_bound():
    damping = shipped_damping()
    bound = damping.entry(LIVE_VERIFICATION_CALLS[APPLE]).freshness_seconds
    assert bound is not None
    assert may_reuse(damping, APPLE, age_seconds=bound - 1)
    assert not may_reuse(damping, APPLE, age_seconds=bound)
    assert not may_reuse(damping, APPLE, age_seconds=bound + 60)


# [utest->req~restore-coalescing-reuse-only-while-fresh~1]
async def test_a_stale_result_forces_a_fresh_provider_verification():
    now = [1000.0]
    metrics = RateLimitMetrics()
    coalescer = RestoreCoalescer(shipped_damping(), metrics=metrics, clock=lambda: now[0])
    calls = 0

    async def dispatch():
        nonlocal calls
        calls += 1
        return {"provider": str(APPLE), "external_id": EXTERNAL_ID, "store_state": "active"}

    joining = participant(VERIFIED, APPLE, EXTERNAL_ID)
    await coalescer.verify(joining, dispatch, budget=lambda: 1)
    reused = await coalescer.verify(joining, dispatch, budget=lambda: 1)
    assert calls == 1 and reused.dispatched is False
    assert metrics.counters()["coalesced_provider_reuse"] == 1

    now[0] += 10_000
    fresh = await coalescer.verify(joining, dispatch, budget=lambda: 1)
    assert calls == 2 and fresh.dispatched is True


# [utest->req~restore-coalescing-global-provider-budgets~1]
def test_a_provider_call_budget_rejection_is_a_429_on_its_own_counter():
    entry = provider_call_budget(StoreProvider.google_play)
    backend = budget_limiter(**{entry: "1/minute"})
    metrics = RateLimitMetrics()
    first = ProviderCallBudget(provider=StoreProvider.google_play)
    consume_provider_call_unit(backend, first, "deployment", endpoint_admission_passed=True)
    dispatch_under_budget(first, lambda: "active")
    second = ProviderCallBudget(provider=StoreProvider.google_play)
    refused = consume_provider_call_unit(backend, second, "deployment",
                                         endpoint_admission_passed=True)
    rejection = provider_call_budget_rejection(restore_attempt(), SecurityTelemetry(), refused,
                                               metrics=metrics)
    assert rejection.error.status_code == 429
    assert metrics.counters()["provider_budget_rejections"] == 1
    assert metrics.exhausted(entry) == 1
    # Apple's budget is untouched by Google's exhaustion.
    apple = budget_limiter(**{provider_call_budget(APPLE): "1/minute"})
    assert apple.test(provider_call_budget(APPLE), "deployment").allowed


# [utest->req~restore-coalescing-global-provider-budgets~1]
def test_a_mutation_behind_a_budget_rejection_is_refused():
    refused = LimitDecision(allowed=False, limiter=provider_call_budget(APPLE))
    with pytest.raises(RestoreAdmissionError, match="performs no mutation"):
        provider_call_budget_rejection(restore_attempt(), SecurityTelemetry(), refused,
                                       metrics=RateLimitMetrics(),
                                       mutations_performed=("access_grants_write",))


# --- Operational counters ------------------------------------------------------------------------------


# [utest->req~restore-admission-operational-counters~1]
def test_the_four_restore_admission_counters_are_exposed_and_move():
    metrics = RateLimitMetrics()
    assert assert_operational_counters(metrics) == RESTORE_ADMISSION_COUNTERS
    metrics.observe(LimitDecision(allowed=True, limiter="restore_subscription_user"))
    metrics.observe(refusal())
    metrics.provider_budget_rejected(provider_call_budget(APPLE))
    metrics.coalesced_reuse()
    counters = metrics.counters()
    assert counters["allowed_requests"] == 1
    assert counters["rejections_429"] == 1
    assert counters["provider_budget_rejections"] == 1
    assert counters["coalesced_provider_reuse"] == 1
