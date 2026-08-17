"""Backend-to-provider damping: the second layer.

Adapter limits protect the provider integrations and the backend's credentials. They are not a
substitute for an endpoint's own limits and never admit a call the endpoint's admission checks
did not already admit. Every damping value an adapter runs under — the connect timeout, the
fixed per-attempt timeout, the total budget, the attempt cap, the per-request retry budget and
the coalesced-result freshness bound — is read from the application configuration file, so a
provider outage, a retry storm or a replay attempt cannot fan out unbounded calls.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from nativespeaker.api.ratelimit.config import (
    TURNSTILE_ENTRY,
    FailureMode,
    RateLimitConfigError,
)
from nativespeaker.api.ratelimit.limiter import LimitDecision, RateLimiter
from nativespeaker.api.ratelimit.ordering import (
    DEVICE_BIT_BUDGET,
    WRITE_CALLS,
    DeviceBitCall,
    DeviceBitWrite,
    DeviceBitWriteError,
)
from nativespeaker.api.ratelimit.rejection import RateLimitMetrics


class ProviderCall(StrEnum):
    """Every outbound provider call these specifications budget and damp."""
    firebase_lookup = "firebase_lookup"
    devicecheck_read = "devicecheck_read"
    devicecheck_write = "devicecheck_write"
    play_integrity_verify = "play_integrity_verify"
    device_recall_read = "device_recall_read"
    device_recall_write = "device_recall_write"
    turnstile_siteverify = "turnstile_siteverify"
    apple_live_store_verification = "apple_live_store_verification"
    google_play_live_store_verification = "google_play_live_store_verification"


class ProviderDampingError(RuntimeError):
    """A provider call was about to be made outside the damping the configuration fixes."""


# The free-grant device-bit reads and writes. Which calls they are, and which budget entry each
# runs under, are `ratelimit/ordering.py`'s to state: this file names the outbound call and
# borrows the mapping rather than keeping a second copy of it.
DEVICE_BIT_PROVIDER_CALLS: dict[ProviderCall, DeviceBitCall] = {
    ProviderCall.devicecheck_read: DeviceBitCall.devicecheck_read,
    ProviderCall.devicecheck_write: DeviceBitCall.devicecheck_write,
    ProviderCall.device_recall_read: DeviceBitCall.device_recall_read,
    ProviderCall.device_recall_write: DeviceBitCall.device_recall_write,
}

DEVICE_BIT_CALLS: frozenset[ProviderCall] = frozenset(DEVICE_BIT_PROVIDER_CALLS)

DEVICE_BIT_WRITES: frozenset[ProviderCall] = frozenset(
    call for call, bit in DEVICE_BIT_PROVIDER_CALLS.items() if bit in WRITE_CALLS)

# Global provider-call budgets, configured separately from every endpoint request limit. Apple
# and Google Play live store-state verification carry separate budgets of their own.
# [impl->req~ratelimit-global-provider-call-budgets~1]
GLOBAL_PROVIDER_CALL_BUDGETS: dict[ProviderCall, str] = {
    ProviderCall.apple_live_store_verification: "provider_apple_store_live_verification_global",
    ProviderCall.google_play_live_store_verification:
        "provider_google_play_live_verification_global",
    ProviderCall.firebase_lookup: "adapter_firebase_lookup",
    ProviderCall.play_integrity_verify: "adapter_play_integrity_verify",
    ProviderCall.turnstile_siteverify: TURNSTILE_ENTRY,
    **{call: DEVICE_BIT_BUDGET[bit] for call, bit in DEVICE_BIT_PROVIDER_CALLS.items()},
}

# The calls that run on a completion path, after the operation challenge has been claimed.
# [impl->req~ratelimit-provider-attempt-timeouts~1]
COMPLETION_PATH_CALLS: frozenset[ProviderCall] = frozenset(ProviderCall)

# Live store-state verification. Its per-restore call count is owned normatively by
# `04-subscription-restore-and-entitlement-transfer.md`, so no retry budget is configured for it
# here and this file restates none.
# [impl->req~ratelimit-per-request-provider-retry-budget~1]
LIVE_STORE_VERIFICATION: frozenset[ProviderCall] = frozenset({
    ProviderCall.apple_live_store_verification,
    ProviderCall.google_play_live_store_verification})


# --- Configured damping ------------------------------------------------------------------------


class ProviderDampingEntry(BaseModel):
    """One adapter's configured damping limits."""
    # [impl->req~ratelimit-adapter-damping-limits-configured~1]

    connect_timeout_ms: int = Field(default=500, ge=1)
    # A fixed configured per-attempt timeout, so the worst-case duration of the steps after the
    # challenge's claim is bounded by these timeouts and the attempt caps alone.
    # [impl->req~ratelimit-provider-attempt-timeouts~1]
    attempt_timeout_seconds: float = Field(gt=0)
    total_budget_seconds: float = Field(gt=0)
    # The endpoint-specific maximum this call's attempts are capped by.
    max_attempts: int = Field(default=1, ge=1)
    # The per-request provider retry budget, in attempts. `null` means the call carries no retry
    # budget at all and its call count is fixed by the endpoint-specific file.
    # [impl->req~ratelimit-per-request-provider-retry-budget~1]
    retry_budget: int | None = Field(default=1)
    retry_on: tuple[str, ...] = ()
    # The freshness bound a coalesced result of this lookup may be reused under.
    # [impl->req~ratelimit-coalesce-concurrent-provider-lookups~1]
    freshness_seconds: float | None = Field(default=None)
    failure_mode: FailureMode = Field(default=FailureMode.fail_closed)

    @model_validator(mode="after")
    def _bounded(self):
        # A retry budget defaults to one provider attempt and is capped by the endpoint-specific
        # maximum; it never raises the cap.
        # [impl->req~ratelimit-per-request-provider-retry-budget~1]
        if self.retry_budget is not None:
            if self.retry_budget < 1:
                raise ValueError("a retry budget is at least one provider attempt")
            if self.retry_budget > self.max_attempts:
                raise ValueError("a retry budget is capped by the endpoint-specific maximum")
        # At least one full attempt fits inside the total budget.
        # [impl->req~ratelimit-adapter-damping-limits-configured~1]
        if self.total_budget_seconds < self.attempt_timeout_seconds:
            raise ValueError("the total budget must admit one full attempt")
        return self


class ProviderDampingConfig(BaseModel):
    """`provider_damping`. One entry per outbound provider call the adapters make."""
    # [impl->req~ratelimit-adapter-damping-limits-configured~1]
    calls: dict[ProviderCall, ProviderDampingEntry] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect(cls, data: Any) -> Any:
        """Entries sit directly under `provider_damping` in the file."""
        if not isinstance(data, dict) or "calls" in data:
            return data
        return {"calls": data}

    def entry(self, call: ProviderCall) -> ProviderDampingEntry:
        """The configured damping for this call. No adapter carries a built-in fallback."""
        # [impl->req~ratelimit-adapter-damping-limits-configured~1]
        found = self.calls.get(call)
        if found is None:
            raise RateLimitConfigError(f"{call} has no configured provider damping")
        return found


# The Turnstile `siteverify` recommended shape: a 500 ms connect timeout, a 2-second per-attempt
# timeout, a 3.5-second total budget, and at most 2 attempts.
# [impl->req~ratelimit-turnstile-siteverify-fail-closed-budget~1]
TURNSTILE_CONNECT_TIMEOUT_MS = 500
TURNSTILE_ATTEMPT_TIMEOUT_SECONDS = 2.0
TURNSTILE_TOTAL_BUDGET_SECONDS = 3.5
TURNSTILE_MAX_ATTEMPTS = 2

# The only outcomes a `siteverify` attempt may be retried on, and only under the same
# idempotency key.
TURNSTILE_RETRYABLE: frozenset[str] = frozenset({
    "connection_failure", "http_429", "http_5xx", "cloudflare_internal_error"})


def assert_turnstile_budget(config: ProviderDampingConfig) -> None:
    """The web gate's `siteverify` call is budgeted fail-closed under its named entry, in the
    recommended shape and no looser."""
    # [impl->req~ratelimit-turnstile-siteverify-fail-closed-budget~1]
    entry = config.entry(ProviderCall.turnstile_siteverify)
    problems: list[str] = []
    if entry.connect_timeout_ms > TURNSTILE_CONNECT_TIMEOUT_MS:
        problems.append("a 500 ms connect timeout")
    if entry.attempt_timeout_seconds > TURNSTILE_ATTEMPT_TIMEOUT_SECONDS:
        problems.append("a 2-second per-attempt timeout")
    if entry.total_budget_seconds > TURNSTILE_TOTAL_BUDGET_SECONDS:
        problems.append("a 3.5-second total budget")
    if entry.max_attempts > TURNSTILE_MAX_ATTEMPTS:
        problems.append("at most 2 attempts")
    if not set(entry.retry_on) <= TURNSTILE_RETRYABLE:
        problems.append(f"retries only on {sorted(TURNSTILE_RETRYABLE)}")
    if entry.failure_mode is not FailureMode.fail_closed:
        problems.append("exhaustion fails closed")
    if problems:
        raise RateLimitConfigError(f"siteverify is budgeted with {'; '.join(problems)}")


def turnstile_retry_allowed(outcome: str) -> bool:
    """Whether a `siteverify` attempt may be retried. Connection failures, `429` and `5xx`
    responses, and Cloudflare `internal-error` results only; every other outcome — a denial
    included — is final for the attempt."""
    # [impl->req~ratelimit-turnstile-siteverify-fail-closed-budget~1]
    return outcome in TURNSTILE_RETRYABLE


def assert_provider_damping(config: ProviderDampingConfig) -> None:
    """The startup check. Every outbound provider call on a completion path must carry its
    configured damping limits before traffic reaches the adapters."""
    # [impl->req~ratelimit-adapter-damping-limits-configured~1]
    # [impl->req~ratelimit-provider-attempt-timeouts~1]
    missing = sorted(str(call) for call in COMPLETION_PATH_CALLS if call not in config.calls)
    if missing:
        raise RateLimitConfigError(f"{', '.join(missing)} carry no configured provider damping")
    for call in LIVE_STORE_VERIFICATION:
        # The restore exception: no retry budget at all, and the call count that replaces it is
        # the restore file's to state.
        # [impl->req~ratelimit-per-request-provider-retry-budget~1]
        if config.entry(call).retry_budget is not None:
            raise RateLimitConfigError(f"{call} carries no retry budget")
    assert_turnstile_budget(config)


# --- Adapter limits are a second layer ----------------------------------------------------------


class EndpointLimitsBypassed(RuntimeError):
    """A provider budget was about to stand in for an endpoint's own admission checks."""


def assert_second_layer(*, endpoint_admission_passed: bool, budget_entry: str) -> None:
    """An adapter budget is a second layer behind the endpoint limits, never a replacement for
    them: it protects the provider integration and the backend's credentials, and it admits
    nothing the endpoint's own admission checks did not already admit."""
    # [impl->req~ratelimit-adapter-limits-second-layer~1]
    if not endpoint_admission_passed:
        raise EndpointLimitsBypassed(
            f"{budget_entry} is a second layer, not a substitute for the endpoint limits")


# --- Global provider-call budgets ----------------------------------------------------------------


# The Firebase Admin `getUser` budget is not charged here. `adapter_firebase_lookup` is one of
# several budgets guarding the same call, and they are reserved jointly and non-destructively by
# `ratelimit/ordering.gate_getuser_call`: a rejection at either layer must charge neither, which
# a lone destructive consume cannot honour. One counter, one charging path.
# [impl->req~ratelimit-getuser-budget-evaluation-order~1]
JOINTLY_RESERVED_CALLS: frozenset[ProviderCall] = frozenset({ProviderCall.firebase_lookup})


class JointlyReservedBudgetError(ProviderDampingError):
    """A budget reserved jointly with others was about to be charged on its own."""


def budget_entry_for(call: ProviderCall) -> str:
    """The global provider-call budget this call is metered by."""
    # [impl->req~ratelimit-global-provider-call-budgets~1]
    return GLOBAL_PROVIDER_CALL_BUDGETS[call]


def consume_budget_unit(limiter: RateLimiter,
                        call: ProviderCall,
                        key: str,
                        *,
                        endpoint_admission_passed: bool,
                        metrics: RateLimitMetrics | None = None) -> LimitDecision:
    """Take one unit immediately before an outbound dispatch.

    The accounting unit is the actual outbound provider attempt: the unit is checked and
    consumed in a single atomic operation against the configured shared counter storage, so the
    budget is enforced across every backend replica and no second replica can slip a dispatch in
    between. A dispatched call consumes its unit regardless of how it resolves.
    """
    # [impl->req~ratelimit-global-provider-call-budgets~1]
    entry = budget_entry_for(call)
    # [impl->req~ratelimit-getuser-budget-evaluation-order~1]
    if call in JOINTLY_RESERVED_CALLS:
        raise JointlyReservedBudgetError(
            f"{entry} is reserved jointly with its endpoint-layer budgets by gate_getuser_call")
    # [impl->req~ratelimit-adapter-limits-second-layer~1]
    assert_second_layer(endpoint_admission_passed=endpoint_admission_passed, budget_entry=entry)
    decision = limiter.consume(entry, key)
    if metrics is not None and not decision.allowed:
        metrics.provider_budget_rejected(entry)
    return decision


# --- The per-request attempt plan ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AttemptPlan:
    """What one request may spend on one provider call: a fixed per-attempt timeout, a connect
    timeout, a total budget, and a bounded number of attempts sharing one idempotency key."""
    call: ProviderCall
    attempts: int
    connect_timeout_ms: int
    attempt_timeout_seconds: float
    total_budget_seconds: float
    idempotency_key: str

    @property
    def worst_case_seconds(self) -> float:
        """The worst case this plan can take, from its timeouts and attempt cap alone."""
        # [impl->req~ratelimit-provider-attempt-timeouts~1]
        return min(self.attempts * self.attempt_timeout_seconds, self.total_budget_seconds)


class NoRetryBudgetError(ProviderDampingError):
    """A call whose per-request call count another file owns was asked for a retry budget."""


def attempt_plan(config: ProviderDampingConfig,
                 call: ProviderCall,
                 *,
                 idempotency_key: str,
                 endpoint_admission_passed: bool,
                 budget_unit_consumed: bool,
                 endpoint_max_attempts: int | None = None) -> AttemptPlan:
    """The per-request provider retry budget for one call.

    Retry budgets apply only after the endpoint admission checks and the provider-call budget
    check have passed. The budget is configured, defaults to one provider attempt, and is capped
    by the endpoint-specific maximum.
    """
    # [impl->req~ratelimit-per-request-provider-retry-budget~1]
    if not endpoint_admission_passed:
        raise ProviderDampingError("a retry budget applies only after endpoint admission passes")
    if not budget_unit_consumed:
        raise ProviderDampingError(
            "a retry budget applies only after the provider-call budget check has passed")
    entry = config.entry(call)
    if entry.retry_budget is None:
        raise NoRetryBudgetError(f"{call} carries no retry budget")
    attempts = min(entry.retry_budget, entry.max_attempts)
    if endpoint_max_attempts is not None:
        attempts = min(attempts, endpoint_max_attempts)
    # Every outbound call on a completion path carries its fixed configured per-attempt timeout.
    # [impl->req~ratelimit-provider-attempt-timeouts~1]
    return AttemptPlan(call=call,
                       attempts=attempts,
                       connect_timeout_ms=entry.connect_timeout_ms,
                       attempt_timeout_seconds=entry.attempt_timeout_seconds,
                       total_budget_seconds=entry.total_budget_seconds,
                       idempotency_key=idempotency_key)


# --- The load-bearing device-bit write ---------------------------------------------------------


def device_bit_write(config: ProviderDampingConfig,
                     call: ProviderCall,
                     *,
                     dispatch: Callable[[AttemptPlan], bool],
                     idempotency_key: str,
                     endpoint_admission_passed: bool,
                     budget_unit_consumed: bool,
                     time_remaining_seconds: float | None = None) -> DeviceBitWrite:
    """Perform the free-grant device-bit write inline and return the vendor's confirmation.

    The write is a load-bearing admission step: it is never best-effort, deferred, queued, or
    retried out of band, and the vendor must confirm it before a grant row is inserted. It is
    also not gated on any remaining execution budget — `time_remaining_seconds` is observability
    only and never a reason to refuse to begin the write, because the challenge's expiry was
    evaluated once at the claim and governs nothing downstream of it.
    """
    # [impl->req~ratelimit-device-bit-write-load-bearing~1]
    # [impl->req~ratelimit-provider-attempt-timeouts~1]
    if call not in DEVICE_BIT_WRITES:
        raise DeviceBitWriteError(f"{call} is no free-grant device-bit write")
    plan = attempt_plan(config, call,
                        idempotency_key=idempotency_key,
                        endpoint_admission_passed=endpoint_admission_passed,
                        budget_unit_consumed=budget_unit_consumed)
    # Dispatched here and awaited here: nothing is queued and nothing is handed to a background
    # worker to finish later.
    confirmed = bool(dispatch(plan))
    # Whether that confirmation permits a grant row is `ratelimit/ordering.py`'s single guard,
    # `assert_grant_row_permitted`, re-exported here rather than restated.
    return DeviceBitWrite(call=DEVICE_BIT_PROVIDER_CALLS[call], confirmed=confirmed)


# --- Coalescing --------------------------------------------------------------------------------


class CoalescingError(RuntimeError):
    """A coalesced result was about to be shared with a request that may not have it."""


@dataclass(frozen=True, slots=True)
class CoalescedObservation:
    """What a coalesced lookup shares: the raw provider observation of live store state, and
    nothing that stands in for a follower's own authorization."""
    # [impl->req~ratelimit-coalesce-concurrent-provider-lookups~1]
    key: str
    observation: Any
    obtained_at: float


@dataclass(frozen=True, slots=True)
class LookupOutcome:
    """One caller's result: the shared observation, and whether this caller spent a provider
    call of its own."""
    observation: Any
    dispatched: bool


# Lookups whose followers may join only after their own proof has verified to the exact
# resource key.
# [impl->req~ratelimit-coalesce-concurrent-provider-lookups~1]
JOIN_REQUIRES_VERIFIED_PROOF: frozenset[ProviderCall] = LIVE_STORE_VERIFICATION


class ProviderCoalescer:
    """Serializes concurrent identical live provider lookups behind one outbound call.

    Concurrent attempts at the same server-derived resource key share one call rather than each
    spending a separate provider call, and a result may be reused afterwards only while it is
    fresh under the configured freshness bound for that lookup.
    """

    def __init__(self,
                 config: ProviderDampingConfig,
                 *,
                 metrics: RateLimitMetrics | None = None,
                 clock: Callable[[], float] | None = None):
        self._config = config
        self._metrics = metrics
        self._clock = clock or time.monotonic
        self._inflight: dict[tuple[ProviderCall, str], asyncio.Future[Any]] = {}
        self._fresh: dict[tuple[ProviderCall, str], CoalescedObservation] = {}
        self._device_locks: dict[tuple[ProviderCall, str], asyncio.Lock] = {}

    async def lookup(self,
                     call: ProviderCall,
                     key: str,
                     dispatch: Callable[[], Awaitable[Any]],
                     *,
                     verified_key: str | None = None) -> LookupOutcome:
        """Run the lookup, joining an in-flight call or reusing a fresh result where allowed."""
        # [impl->req~ratelimit-coalesce-concurrent-provider-lookups~1]
        if call in DEVICE_BIT_CALLS:
            # The free-grant device-bit read and write are excluded from coalesced-result reuse.
            # [impl->req~ratelimit-device-bit-no-coalesced-reuse~1]
            raise CoalescingError(f"{call} performs its own call and reuses no coalesced result")
        if call in JOIN_REQUIRES_VERIFIED_PROOF and verified_key != key:
            # A request may join or reuse only after its own proof has verified to the exact
            # resource key; a request whose proof fails never joins and never sees the result.
            raise CoalescingError(f"{call} joins only on a proof verified to {key}")
        entry = self._config.entry(call)
        cached = self._fresh.get((call, key))
        if cached is not None and self._is_fresh(cached, entry.freshness_seconds):
            self._reused()
            return LookupOutcome(observation=cached.observation, dispatched=False)
        inflight = self._inflight.get((call, key))
        if inflight is not None:
            # A follower waits on the leader's call and shares its terminal outcome, success or
            # failure, without launching a further call of its own.
            observation = await asyncio.shield(inflight)
            self._reused()
            return LookupOutcome(observation=observation, dispatched=False)
        return await self._lead(call, key, dispatch, entry.freshness_seconds)

    async def _lead(self,
                    call: ProviderCall,
                    key: str,
                    dispatch: Callable[[], Awaitable[Any]],
                    freshness_seconds: float | None) -> LookupOutcome:
        """Dispatch the one shared outbound call. Only the leader spends a budget unit."""
        # [impl->req~ratelimit-global-provider-call-budgets~1]
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._inflight[(call, key)] = future
        try:
            observation = await dispatch()
        except Exception as exc:
            future.set_exception(exc)
            # Consume the exception so a future nobody awaited does not warn.
            future.exception()
            raise
        else:
            future.set_result(observation)
            if freshness_seconds:
                self._fresh[(call, key)] = CoalescedObservation(key=key,
                                                                observation=observation,
                                                                obtained_at=self._clock())
            return LookupOutcome(observation=observation, dispatched=True)
        finally:
            self._inflight.pop((call, key), None)

    def device_bit_lock(self, call: ProviderCall, device_key: str) -> asyncio.Lock:
        """Serialize concurrent attempts for the same device. Serializing is permitted; sharing
        a result is not — each claim performs its own read and its own confirmed write, and no
        cached or coalesced value substitutes for either call."""
        # [impl->req~ratelimit-device-bit-no-coalesced-reuse~1]
        if call not in DEVICE_BIT_CALLS:
            raise CoalescingError(f"{call} is no device-bit call")
        return self._device_locks.setdefault((call, device_key), asyncio.Lock())

    def _is_fresh(self, cached: CoalescedObservation, freshness_seconds: float | None) -> bool:
        """A coalesced result may be reused only while fresh under the configured bound; once it
        is stale a new attempt must obtain a fresh provider verification."""
        # [impl->req~ratelimit-coalesce-concurrent-provider-lookups~1]
        if not freshness_seconds:
            return False
        return (self._clock() - cached.obtained_at) < freshness_seconds

    def _reused(self) -> None:
        if self._metrics is not None:
            self._metrics.coalesced_reuse()
