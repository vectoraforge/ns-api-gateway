"""Provider budgets, coalescing and adapter damping: the second layer of 08."""

import asyncio
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nativespeaker.api.ratelimit.config import RateLimitEntry, RateLimitsConfig, Strategy
from nativespeaker.api.ratelimit.limiter import RateLimiter
from nativespeaker.api.ratelimit.providers import (
    COMPLETION_PATH_CALLS,
    DEVICE_BIT_CALLS,
    GLOBAL_PROVIDER_CALL_BUDGETS,
    LIVE_STORE_VERIFICATION,
    TURNSTILE_RETRYABLE,
    CoalescingError,
    DeviceBitWriteError,
    EndpointLimitsBypassed,
    NoRetryBudgetError,
    ProviderCall,
    ProviderCoalescer,
    ProviderDampingConfig,
    ProviderDampingEntry,
    ProviderDampingError,
    assert_grant_row_permitted,
    assert_provider_damping,
    assert_turnstile_budget,
    attempt_plan,
    consume_budget_unit,
    device_bit_write,
    turnstile_retry_allowed,
)
from nativespeaker.api.ratelimit.rejection import RateLimitMetrics

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def shipped_damping() -> ProviderDampingConfig:
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    return ProviderDampingConfig(**raw["provider_damping"])


def limiter(**entries: str) -> RateLimiter:
    config = RateLimitsConfig(enabled=True, storage_uri="memory://",
                              strategy=Strategy.moving_window,
                              default=RateLimitEntry(limit="120/minute", key="ip"),
                              entries={name: RateLimitEntry(limit=limit, key="deployment")
                                       for name, limit in entries.items()})
    return RateLimiter(config)


# --- Configured damping ---------------------------------------------------------------------

# [utest->req~ratelimit-adapter-damping-limits-configured~1]
def test_the_shipped_file_configures_damping_for_every_provider_call():
    damping = shipped_damping()
    assert set(damping.calls) == set(ProviderCall)
    assert_provider_damping(damping)
    for call in ProviderCall:
        entry = damping.entry(call)
        assert entry.connect_timeout_ms > 0
        assert entry.attempt_timeout_seconds > 0
        assert entry.total_budget_seconds >= entry.attempt_timeout_seconds
        assert entry.max_attempts >= 1


# [utest->req~ratelimit-adapter-damping-limits-configured~1]
def test_an_adapter_with_no_configured_damping_fails_at_startup():
    damping = shipped_damping()
    del damping.calls[ProviderCall.devicecheck_write]
    with pytest.raises(Exception, match="devicecheck_write"):
        assert_provider_damping(damping)
    with pytest.raises(Exception, match="devicecheck_write"):
        damping.entry(ProviderCall.devicecheck_write)


# [utest->req~ratelimit-adapter-damping-limits-configured~1]
def test_a_total_budget_must_admit_one_full_attempt():
    with pytest.raises(ValidationError):
        ProviderDampingEntry(attempt_timeout_seconds=5, total_budget_seconds=2)


# --- Adapter limits are a second layer -------------------------------------------------------

# [utest->req~ratelimit-adapter-limits-second-layer~1]
def test_a_provider_budget_never_stands_in_for_the_endpoint_limits():
    backend = limiter(adapter_firebase_lookup="10/minute")
    with pytest.raises(EndpointLimitsBypassed):
        consume_budget_unit(backend, ProviderCall.firebase_lookup, "deployment",
                            endpoint_admission_passed=False)
    # Nothing was spent: the budget was never even consulted.
    assert backend.test("adapter_firebase_lookup", "deployment").allowed
    assert consume_budget_unit(backend, ProviderCall.firebase_lookup, "deployment",
                               endpoint_admission_passed=True).allowed


# [utest->req~ratelimit-adapter-limits-second-layer~1]
def test_the_retry_budget_is_behind_the_endpoint_limits_too():
    damping = shipped_damping()
    with pytest.raises(ProviderDampingError, match="endpoint admission"):
        attempt_plan(damping, ProviderCall.firebase_lookup, idempotency_key="k",
                     endpoint_admission_passed=False, budget_unit_consumed=True)


# --- Global provider-call budgets ------------------------------------------------------------

# [utest->req~ratelimit-global-provider-call-budgets~1]
def test_apple_and_google_play_live_verification_carry_separate_global_budgets():
    apple = GLOBAL_PROVIDER_CALL_BUDGETS[ProviderCall.apple_live_store_verification]
    google = GLOBAL_PROVIDER_CALL_BUDGETS[ProviderCall.google_play_live_store_verification]
    assert apple != google
    # Configured separately from every endpoint request limit.
    shipped = yaml.safe_load(CONFIG_PATH.read_text())["rate_limits"]
    assert apple in shipped and google in shipped
    assert apple not in shipped["restore_subscription_user"]


# [utest->req~ratelimit-global-provider-call-budgets~1]
def test_each_outbound_attempt_consumes_one_unit_whatever_it_returns():
    backend = limiter(provider_apple_store_live_verification_global="2/minute")
    call = ProviderCall.apple_live_store_verification

    def dispatch(fail: bool) -> None:
        decision = consume_budget_unit(backend, call, "deployment",
                                       endpoint_admission_passed=True)
        assert decision.allowed
        if fail:
            raise RuntimeError("provider returned 500")

    dispatch(fail=False)
    with pytest.raises(RuntimeError):
        # A dispatched call consumes its unit regardless of outcome.
        dispatch(fail=True)
    metrics = RateLimitMetrics()
    third = consume_budget_unit(backend, call, "deployment", endpoint_admission_passed=True,
                                metrics=metrics)
    assert third.allowed is False
    assert metrics.counters()["provider_budget_rejections"] == 1


# [utest->req~ratelimit-global-provider-call-budgets~1]
async def test_a_coalesced_follower_consumes_no_separate_unit():
    backend = limiter(provider_apple_store_live_verification_global="2/minute")
    call = ProviderCall.apple_live_store_verification
    coalescer = ProviderCoalescer(shipped_damping())
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch():
        consume_budget_unit(backend, call, "deployment", endpoint_admission_passed=True)
        started.set()
        await release.wait()
        return "active"

    async def caller():
        return await coalescer.lookup(call, "apple:sub-1", dispatch, verified_key="apple:sub-1")

    leader = asyncio.create_task(caller())
    await started.wait()
    follower = asyncio.create_task(caller())
    await asyncio.sleep(0)
    release.set()
    outcomes = [await leader, await follower]
    assert [outcome.dispatched for outcome in outcomes] == [True, False]
    assert all(outcome.observation == "active" for outcome in outcomes)
    # One unit for one outbound attempt out of the two the budget allowed: the follower spent
    # none of its own, so a unit is still there.
    assert backend.consume("provider_apple_store_live_verification_global", "deployment").allowed
    assert not backend.test("provider_apple_store_live_verification_global", "deployment").allowed


# --- Coalescing --------------------------------------------------------------------------------

# [utest->req~ratelimit-coalesce-concurrent-provider-lookups~1]
async def test_concurrent_lookups_for_one_resource_key_spend_one_provider_call():
    coalescer = ProviderCoalescer(shipped_damping())
    calls = 0
    release = asyncio.Event()

    async def dispatch():
        nonlocal calls
        calls += 1
        await release.wait()
        return "active"

    async def caller():
        return await coalescer.lookup(ProviderCall.google_play_live_store_verification,
                                      "google:sub-9", dispatch, verified_key="google:sub-9")

    tasks = [asyncio.create_task(caller()) for _ in range(4)]
    await asyncio.sleep(0)
    release.set()
    outcomes = [await task for task in tasks]
    assert calls == 1
    assert sum(outcome.dispatched for outcome in outcomes) == 1


# [utest->req~ratelimit-coalesce-concurrent-provider-lookups~1]
async def test_a_result_is_reused_only_while_fresh():
    now = [1000.0]
    damping = shipped_damping()
    freshness = damping.entry(ProviderCall.apple_live_store_verification).freshness_seconds
    assert freshness
    metrics = RateLimitMetrics()
    coalescer = ProviderCoalescer(damping, metrics=metrics, clock=lambda: now[0])
    calls = 0

    async def dispatch():
        nonlocal calls
        calls += 1
        return "active"

    async def lookup():
        return await coalescer.lookup(ProviderCall.apple_live_store_verification, "apple:1",
                                      dispatch, verified_key="apple:1")

    assert (await lookup()).dispatched is True
    now[0] += freshness / 2
    assert (await lookup()).dispatched is False
    assert metrics.counters()["coalesced_provider_reuse"] == 1
    # Once stale, a new attempt must obtain a fresh provider verification.
    now[0] += freshness
    assert (await lookup()).dispatched is True
    assert calls == 2


# [utest->req~ratelimit-coalesce-concurrent-provider-lookups~1]
async def test_a_request_joins_only_on_its_own_verified_proof_for_that_resource():
    coalescer = ProviderCoalescer(shipped_damping())

    async def dispatch():
        return "active"

    with pytest.raises(CoalescingError, match="apple:1"):
        await coalescer.lookup(ProviderCall.apple_live_store_verification, "apple:1", dispatch,
                               verified_key="apple:2")
    with pytest.raises(CoalescingError):
        await coalescer.lookup(ProviderCall.apple_live_store_verification, "apple:1", dispatch)


# [utest->req~ratelimit-coalesce-concurrent-provider-lookups~1]
async def test_waiters_share_the_leaders_failure_without_launching_another_call():
    coalescer = ProviderCoalescer(shipped_damping())
    calls = 0
    release = asyncio.Event()

    async def dispatch():
        nonlocal calls
        calls += 1
        await release.wait()
        raise RuntimeError("store unavailable")

    async def caller():
        return await coalescer.lookup(ProviderCall.apple_live_store_verification, "apple:7",
                                      dispatch, verified_key="apple:7")

    tasks = [asyncio.create_task(caller()) for _ in range(3)]
    await asyncio.sleep(0)
    release.set()
    for task in tasks:
        with pytest.raises(RuntimeError, match="store unavailable"):
            await task
    assert calls == 1


# --- The Turnstile budget -----------------------------------------------------------------------

# [utest->req~ratelimit-turnstile-siteverify-fail-closed-budget~1]
def test_the_shipped_siteverify_budget_carries_the_recommended_shape():
    entry = shipped_damping().entry(ProviderCall.turnstile_siteverify)
    assert entry.connect_timeout_ms <= 500
    assert entry.attempt_timeout_seconds <= 2
    assert entry.total_budget_seconds <= 3.5
    assert entry.max_attempts <= 2
    assert entry.failure_mode == "fail_closed"
    assert_turnstile_budget(shipped_damping())


# [utest->req~ratelimit-turnstile-siteverify-fail-closed-budget~1]
@pytest.mark.parametrize("looser", [
    {"connect_timeout_ms": 3000},
    {"attempt_timeout_seconds": 3.0},
    {"total_budget_seconds": 30.0},
    {"max_attempts": 5, "retry_budget": 5},
    {"retry_on": ("token_denied",)},
    {"failure_mode": "fail_open"},
])
def test_a_looser_siteverify_budget_is_a_startup_error(looser):
    damping = shipped_damping()
    shape = damping.entry(ProviderCall.turnstile_siteverify).model_dump()
    shape.update(looser)
    damping.calls[ProviderCall.turnstile_siteverify] = ProviderDampingEntry(**shape)
    with pytest.raises(Exception, match="siteverify"):
        assert_turnstile_budget(damping)


# [utest->req~ratelimit-turnstile-siteverify-fail-closed-budget~1]
def test_siteverify_retries_only_connection_failures_429s_5xxs_and_internal_errors():
    assert TURNSTILE_RETRYABLE == {"connection_failure", "http_429", "http_5xx",
                                   "cloudflare_internal_error"}
    assert all(turnstile_retry_allowed(outcome) for outcome in TURNSTILE_RETRYABLE)
    for final in ("invalid_input_response", "timeout_or_duplicate", "hostname_mismatch"):
        assert turnstile_retry_allowed(final) is False


# --- Per-request retry budgets --------------------------------------------------------------

# [utest->req~ratelimit-per-request-provider-retry-budget~1]
def test_a_retry_budget_defaults_to_one_provider_attempt():
    assert ProviderDampingEntry(attempt_timeout_seconds=5,
                                total_budget_seconds=5).retry_budget == 1
    plan = attempt_plan(shipped_damping(), ProviderCall.firebase_lookup, idempotency_key="k",
                        endpoint_admission_passed=True, budget_unit_consumed=True)
    assert plan.attempts == 1


# [utest->req~ratelimit-per-request-provider-retry-budget~1]
def test_a_retry_budget_is_capped_by_the_endpoint_specific_maximum():
    with pytest.raises(ValidationError):
        ProviderDampingEntry(attempt_timeout_seconds=5, total_budget_seconds=5,
                             max_attempts=2, retry_budget=3)
    damping = shipped_damping()
    damping.calls[ProviderCall.turnstile_siteverify] = ProviderDampingEntry(
        attempt_timeout_seconds=2, total_budget_seconds=3.5, max_attempts=2, retry_budget=2)
    plan = attempt_plan(damping, ProviderCall.turnstile_siteverify, idempotency_key="k",
                        endpoint_admission_passed=True, budget_unit_consumed=True,
                        endpoint_max_attempts=1)
    assert plan.attempts == 1


# [utest->req~ratelimit-per-request-provider-retry-budget~1]
def test_a_retry_budget_applies_only_after_the_provider_call_budget_check():
    with pytest.raises(ProviderDampingError, match="provider-call budget"):
        attempt_plan(shipped_damping(), ProviderCall.firebase_lookup, idempotency_key="k",
                     endpoint_admission_passed=True, budget_unit_consumed=False)


# [utest->req~ratelimit-per-request-provider-retry-budget~1]
@pytest.mark.parametrize("call", sorted(LIVE_STORE_VERIFICATION))
def test_live_store_verification_carries_no_retry_budget_at_all(call):
    damping = shipped_damping()
    assert damping.entry(call).retry_budget is None
    with pytest.raises(NoRetryBudgetError):
        attempt_plan(damping, call, idempotency_key="k", endpoint_admission_passed=True,
                     budget_unit_consumed=True)


# --- Attempt timeouts ---------------------------------------------------------------------------

# [utest->req~ratelimit-provider-attempt-timeouts~1]
def test_every_completion_path_call_carries_a_fixed_configured_per_attempt_timeout():
    damping = shipped_damping()
    for call in COMPLETION_PATH_CALLS:
        assert damping.entry(call).attempt_timeout_seconds > 0
    damping.calls[ProviderCall.firebase_lookup] = ProviderDampingEntry(
        attempt_timeout_seconds=6, total_budget_seconds=12, max_attempts=2, retry_budget=2)
    plan = attempt_plan(damping, ProviderCall.firebase_lookup, idempotency_key="k",
                        endpoint_admission_passed=True, budget_unit_consumed=True)
    # The worst case comes from the timeouts and the attempt cap alone.
    assert plan.attempt_timeout_seconds == 6
    assert plan.worst_case_seconds == 12


# [utest->req~ratelimit-provider-attempt-timeouts~1]
def test_the_device_bit_write_is_not_gated_on_any_remaining_execution_budget():
    damping = shipped_damping()
    write = device_bit_write(damping, ProviderCall.devicecheck_write,
                             dispatch=lambda plan: True, idempotency_key="k",
                             endpoint_admission_passed=True, budget_unit_consumed=True,
                             # No time left at all: the write still begins.
                             time_remaining_seconds=0.0)
    assert write.confirmed is True


# --- The load-bearing device-bit write ----------------------------------------------------------

# [utest->req~ratelimit-device-bit-write-load-bearing~1]
def test_the_write_is_dispatched_inline_and_confirmed_before_the_grant_row():
    damping = shipped_damping()
    dispatched: list[str] = []

    def dispatch(plan):
        dispatched.append(plan.idempotency_key)
        return True

    write = device_bit_write(damping, ProviderCall.device_recall_write, dispatch=dispatch,
                             idempotency_key="claim-1", endpoint_admission_passed=True,
                             budget_unit_consumed=True)
    assert dispatched == ["claim-1"]
    assert_grant_row_permitted(write)


# [utest->req~ratelimit-device-bit-write-load-bearing~1]
def test_no_grant_row_behind_an_unconfirmed_or_deferred_write():
    damping = shipped_damping()
    unconfirmed = device_bit_write(damping, ProviderCall.devicecheck_write,
                                   dispatch=lambda plan: False, idempotency_key="k",
                                   endpoint_admission_passed=True, budget_unit_consumed=True)
    with pytest.raises(DeviceBitWriteError):
        assert_grant_row_permitted(unconfirmed)
    # A write that was never performed — deferred or queued for later — is no confirmation.
    with pytest.raises(DeviceBitWriteError):
        assert_grant_row_permitted(None)


# [utest->req~ratelimit-device-bit-write-load-bearing~1]
def test_only_a_device_bit_write_goes_through_that_path():
    with pytest.raises(DeviceBitWriteError):
        device_bit_write(shipped_damping(), ProviderCall.devicecheck_read,
                         dispatch=lambda plan: True, idempotency_key="k",
                         endpoint_admission_passed=True, budget_unit_consumed=True)


# --- No coalesced reuse for the device bit ------------------------------------------------------

# [utest->req~ratelimit-device-bit-no-coalesced-reuse~1]
@pytest.mark.parametrize("call", sorted(DEVICE_BIT_CALLS))
async def test_a_device_bit_read_or_write_is_never_coalesced(call):
    coalescer = ProviderCoalescer(shipped_damping())

    async def dispatch():
        return "set"

    with pytest.raises(CoalescingError, match="own call"):
        await coalescer.lookup(call, "device-1", dispatch)


# [utest->req~ratelimit-device-bit-no-coalesced-reuse~1]
async def test_concurrent_attempts_for_one_device_may_be_serialized_without_sharing_a_result():
    coalescer = ProviderCoalescer(shipped_damping())
    lock = coalescer.device_bit_lock(ProviderCall.devicecheck_read, "device-1")
    assert coalescer.device_bit_lock(ProviderCall.devicecheck_read, "device-1") is lock
    assert coalescer.device_bit_lock(ProviderCall.devicecheck_read, "device-2") is not lock
    with pytest.raises(CoalescingError):
        coalescer.device_bit_lock(ProviderCall.firebase_lookup, "device-1")
