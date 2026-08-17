"""Rate limits and backend admission control."""

from nativespeaker.api.ratelimit.config import (
    FailureMode,
    GatewayRateLimitsConfig,
    RateLimitConfigError,
    RateLimitEntry,
    RateLimitsConfig,
    Strategy,
    assert_rate_limit_config,
)
from nativespeaker.api.ratelimit.keys import (
    AddressSource,
    DerivedIdentifier,
    GatewayResolvedAddress,
    KeyComponent,
    KeyMaterial,
    LimiterKeyError,
    LimiterLayer,
    build_key,
    canonical_client_ip_key,
    gateway_resolved_address,
    parse_key_policy,
)
from nativespeaker.api.ratelimit.limiter import (
    LimitDecision,
    RateLimiter,
    UnconfiguredLimitError,
)
from nativespeaker.api.ratelimit.ordering import (
    AdmissionLedger,
    AdmissionOrderError,
    DeviceBitCall,
    ExpensiveStep,
    GetUserCallSite,
    evaluate_getuser_budgets,
)

__all__ = [
    "AddressSource",
    "AdmissionLedger",
    "AdmissionOrderError",
    "DerivedIdentifier",
    "DeviceBitCall",
    "ExpensiveStep",
    "FailureMode",
    "GatewayResolvedAddress",
    "GatewayRateLimitsConfig",
    "GetUserCallSite",
    "KeyComponent",
    "KeyMaterial",
    "LimitDecision",
    "LimiterKeyError",
    "LimiterLayer",
    "RateLimitConfigError",
    "RateLimitEntry",
    "RateLimiter",
    "RateLimitsConfig",
    "Strategy",
    "UnconfiguredLimitError",
    "assert_rate_limit_config",
    "build_key",
    "canonical_client_ip_key",
    "evaluate_getuser_budgets",
    "gateway_resolved_address",
    "parse_key_policy",
]
