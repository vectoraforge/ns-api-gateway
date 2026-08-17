"""The rate-limit and admission-control configuration contract.

Every limit this application enforces is declared here and read from the application
configuration file. No endpoint carries its own limit string, storage URI, key function, cost,
strategy, enabled state or failure behaviour, so an operator retunes policy by editing
configuration and never by editing code.
"""

import os
import re
from enum import StrEnum
from typing import Any

from limits import RateLimitItem, parse_many
from pydantic import BaseModel, Field, field_validator, model_validator

from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.ratelimit.keys import (
    IDENTITY_COMPONENTS,
    AddressSource,
    KeyComponent,
    LimiterKeyError,
    TrustedProxyChain,
    parse_key_policy,
    trusted_proxy_chain,
)

_ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


class RateLimitConfigError(RuntimeError):
    """The shipped rate-limit configuration cannot be served: a required entry is missing, a
    forbidden one is present, or a named entry does not carry the key policy or failure
    behaviour this specification fixes for it. Raised at startup, before traffic."""


def expand_env(value: str, *, default: str) -> str:
    """Expand a `${VAR}` placeholder from the environment. An unset variable falls back to the
    development default, which the production storage check then rejects where it must."""
    match = _ENV_PATTERN.match(value.strip())
    if match is None:
        return value
    return os.environ.get(match.group(1)) or default


class FailureMode(StrEnum):
    """What an entry does when the `limits` backend cannot be evaluated."""
    # [impl->req~ratelimit-entry-failure-behavior~1]
    fail_closed = "fail_closed"
    fail_open = "fail_open"


class Strategy(StrEnum):
    """The `limits` strategies this application will select."""
    # [impl->req~ratelimit-config-key-strategy~1]
    fixed_window = "fixed-window"
    moving_window = "moving-window"
    sliding_window_counter = "sliding-window-counter"


class DeploymentEnvironment(StrEnum):
    local = "local"
    production = "production"


# Storage schemes that share counters across every backend replica.
SHARED_STORAGE_SCHEMES: frozenset[str] = frozenset({
    "redis", "rediss", "redis+unix", "redis+cluster", "redis+sentinel",
    "valkey", "valkeys", "valkey+unix", "valkey+cluster", "valkey+sentinel",
    "async+redis", "async+rediss", "async+redis+unix", "async+redis+cluster",
    "async+redis+sentinel", "async+valkey", "async+valkeys", "async+valkey+unix",
    "async+valkey+cluster", "async+valkey+sentinel"})

# In-memory storage is acceptable only for local development and tests.
LOCAL_ONLY_STORAGE_SCHEMES: frozenset[str] = frozenset({"memory", "async+memory"})
DEFAULT_LOCAL_STORAGE_URI = "memory://"

# Rate-limit counters are operational abuse controls, not business ownership state, so they
# never live in the auth refactor PostgreSQL schema.
# [impl->req~ratelimit-limits-library-and-storage-separation~1]
FORBIDDEN_STORAGE_SCHEMES: frozenset[str] = frozenset({
    "postgres", "postgresql", "postgresql+asyncpg", "async+postgresql"})


class RateLimitEntry(BaseModel):
    """One configured limit. Every entry defines all five facts an entry must define: the limit
    string, the key policy, the cost, whether it is enabled, and the failure behaviour when the
    `limits` backend is unavailable. `cost`, `enabled` and `failure_mode` are optional in the
    file and take these documented defaults when the file omits them."""
    # [impl->req~ratelimit-entry-must-define~1]
    # [impl->req~ratelimit-config-per-entry-fields~1]

    # [impl->req~ratelimit-entry-limit-string~1]
    limit: str = Field(description="The configured limit string, e.g. '2/minute; 6/hour; 20/day'")
    # [impl->req~ratelimit-entry-key-policy~1]
    key: str = Field(description="The configured key policy, a '+'-joined component list")
    # [impl->req~ratelimit-entry-cost~1]
    cost: int = Field(default=1, ge=1, description="The configured cost; the default cost is 1")
    # [impl->req~ratelimit-entry-enabled~1]
    enabled: bool = Field(default=True, description="Whether the limit is enabled")
    # The default production failure behaviour for security-sensitive admission controls is
    # fail-closed unless the config file explicitly chooses fail-open for a named entry.
    # [impl->req~ratelimit-default-fail-closed-unless-configured~1]
    failure_mode: FailureMode = Field(default=FailureMode.fail_closed)

    @field_validator("limit")
    @classmethod
    def _parseable(cls, value: str) -> str:
        # Multi-window strings are parsed with `limits.parse_many()` and enforced as a set.
        # [impl->req~ratelimit-parse-many-multi-window-strings~1]
        # [impl->req~ratelimit-entry-limit-string~1]
        if not parse_many(value):
            raise ValueError(f"{value!r} declares no rate limit")
        return value

    @field_validator("key")
    @classmethod
    def _key_policy(cls, value: str) -> str:
        try:
            components = parse_key_policy(value)
        except LimiterKeyError as exc:
            raise ValueError(str(exc)) from exc
        # The user counter and the client-IP counter are always independent buckets; a composite
        # `user+ip` counter fires only when both components repeat together and is never the
        # shape this specification asks for.
        # [impl->req~ratelimit-grant-claim-admission-keys~1]
        if KeyComponent.user in components and KeyComponent.ip in components:
            raise ValueError(f"{value!r} fuses the user and client-IP counters into one")
        return value

    @property
    def parsed(self) -> list[RateLimitItem]:
        """The configured windows, as a set."""
        # [impl->req~ratelimit-parse-many-multi-window-strings~1]
        return parse_many(self.limit)

    @property
    def policy(self) -> tuple[KeyComponent, ...]:
        # [impl->req~ratelimit-entry-key-policy~1]
        return parse_key_policy(self.key)

    def definition(self) -> dict[str, Any]:
        """The five facts this entry defines, all resolved."""
        # [impl->req~ratelimit-entry-must-define~1]
        return {"limit": self.limit, "key": self.key, "cost": self.cost,
                "enabled": self.enabled, "failure_mode": self.failure_mode}


class GatewayCounterScope(StrEnum):
    """Where a gateway counter lives. Only one value is permitted: a per-Envoy-pod counter would
    multiply every ceiling by the replica count."""
    # [impl->req~sessions-create-user-two-gateway-limits~1]
    global_rate_limit_service = "global_rate_limit_service"
    per_envoy_pod = "per_envoy_pod"


class GatewayPhase(StrEnum):
    """The two phases of a challenge-bearing route a gateway limit can cover."""
    prepare = "prepare"
    complete = "complete"


# Where an identity-keyed gateway limiter may be evaluated, and where an IP-keyed one may.
ENVOY_JWT_VERIFICATION = "envoy_jwt_verification"
GATEWAY_ROUTE_MATCH = "gateway_route_match"
GATEWAY_EVALUATION_POINTS: frozenset[str] = frozenset({ENVOY_JWT_VERIFICATION,
                                                       GATEWAY_ROUTE_MATCH})


class GatewayRateLimitEntry(BaseModel):
    """A limit the gateway enforces. It is declared here because the application configuration
    file is the source of truth for every limit; the backend evaluates none of them."""
    route: str
    limit: str
    key: str
    evaluate_after: str
    # Both gateway counters are enforced as counters in a global rate-limit service shared by
    # every Envoy replica, never as per-Envoy-pod counters.
    # [impl->req~sessions-create-user-two-gateway-limits~1]
    enforcement: GatewayCounterScope = Field(default=GatewayCounterScope.global_rate_limit_service)
    # Which phases of the route the limit covers. A challenge-bearing route's limits cover both.
    phases: tuple[GatewayPhase, ...] = Field(default=(GatewayPhase.prepare, GatewayPhase.complete))
    # A gateway limit fails closed: an unevaluable ceiling rejects rather than admitting.
    # [impl->req~sessions-create-user-limits-fail-closed~1]
    failure_mode: FailureMode = Field(default=FailureMode.fail_closed)
    # Sustained saturation of a deployment-wide ceiling raises an operational alert.
    # [impl->req~sessions-create-user-limit-tuning-and-alert~1]
    saturation_alert: bool = Field(default=False)

    @field_validator("limit")
    @classmethod
    def _parseable(cls, value: str) -> str:
        if not parse_many(value):
            raise ValueError(f"{value!r} declares no rate limit")
        return value

    @field_validator("key")
    @classmethod
    def _key_policy(cls, value: str) -> str:
        try:
            parse_key_policy(value)
        except LimiterKeyError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("enforcement")
    @classmethod
    def _global_counters_only(cls, value: GatewayCounterScope) -> GatewayCounterScope:
        # [impl->req~sessions-create-user-two-gateway-limits~1]
        if value is not GatewayCounterScope.global_rate_limit_service:
            raise ValueError("a gateway counter lives in the global rate-limit service")
        return value

    @model_validator(mode="after")
    def _identity_keys_evaluated_after_jwt_verification(self):
        """A gateway limiter keyed on verified identity derives its key from the JWT filter's own
        verified token metadata, so it is evaluated only after that filter has verified the
        request's token for the route. A client-IP-keyed limit needs no verified identity and may
        sit anywhere in the filter chain."""
        # [impl->req~sessions-identity-keyed-limiter-from-verified-metadata~1]
        if self.evaluate_after not in GATEWAY_EVALUATION_POINTS:
            raise ValueError(f"{self.evaluate_after!r} is no gateway evaluation point")
        identity_keyed = any(component in IDENTITY_COMPONENTS
                             for component in parse_key_policy(self.key))
        if identity_keyed and self.evaluate_after != ENVOY_JWT_VERIFICATION:
            raise ValueError("an identity-keyed gateway limit is evaluated after JWT verification")
        return self

    @property
    def windows(self) -> list[RateLimitItem]:
        """The entry's configured windows."""
        return parse_many(self.limit)

    def per_window(self) -> dict[str, float]:
        """The configured ceiling per window granularity, as `{'minute': 10}`."""
        return {window.GRANULARITY.name: window.amount / window.multiples
                for window in self.windows}


class ClientAddressConfig(BaseModel):
    """How the canonical client address becomes a limiter key, and the trusted-proxy chain it is
    resolved through."""
    # [impl->req~ratelimit-canonical-client-ip-resolution~2]
    ipv6_prefix: int = Field(default=64, description="64, operator-configurable to 56 or 48")
    unresolved_limit: str = Field(default="10/minute",
                                  description="The single-address ceiling for the one shared "
                                              "unresolved-address bucket")
    # The explicitly configured chain: how Envoy terminates, which proxies may connect to the
    # listener, and which component injects the true client address.
    # [impl->req~sessions-client-ip-trusted-proxy-chain~1]
    source: AddressSource = Field(default=AddressSource.envoy_direct_downstream)
    trusted_proxies: tuple[str, ...] = Field(default=())
    injector: str | None = Field(default=None)
    overwrite_inbound_forwarding_headers: bool = Field(default=True)

    @field_validator("ipv6_prefix")
    @classmethod
    def _permitted_prefix(cls, value: int) -> int:
        if value not in (64, 56, 48):
            raise ValueError("the IPv6 aggregation prefix is /64, /56 or /48")
        return value

    @model_validator(mode="after")
    def _trust_chain_is_pinned_to_the_deployment(self):
        """The configured chain is validated by the one module that owns the client-address
        definition, so a hop count that does not match the deployment's actual chain, an
        undocumented injector, or an appending outermost hop is a startup configuration error."""
        # [impl->req~sessions-client-ip-trusted-proxy-chain~1]
        # [impl->req~sessions-client-ip-deployment-documents-injector~1]
        try:
            trusted_proxy_chain(
                self.source,
                trusted_proxies=self.trusted_proxies,
                injector=self.injector,
                overwrite_inbound_forwarding_headers=self.overwrite_inbound_forwarding_headers)
        except LimiterKeyError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @property
    def chain(self) -> TrustedProxyChain:
        """The validated trusted-proxy chain, with `xff_num_trusted_hops` pinned to exactly the
        number of trusted proxies."""
        # [impl->req~sessions-client-ip-xff-trusted-hops~1]
        return trusted_proxy_chain(
            self.source,
            trusted_proxies=self.trusted_proxies,
            injector=self.injector,
            overwrite_inbound_forwarding_headers=self.overwrite_inbound_forwarding_headers)


class RateLimitsConfig(BaseModel):
    """`rate_limits`. The configuration file must include at least `enabled`, `storage_uri`,
    `strategy`, `default`, and the named entries the operation inventory requires."""
    # [impl->req~ratelimit-config-must-include-at-least~1]
    # [impl->req~ratelimit-all-limits-in-config-no-hardcoding~1]

    # [impl->req~ratelimit-config-key-enabled~1]
    enabled: bool = Field(description="Whether backend rate limiting is enforced")
    # [impl->req~ratelimit-config-key-storage-uri~1]
    storage_uri: str = Field(description="The `limits` storage backend URI")
    # [impl->req~ratelimit-config-key-strategy~1]
    strategy: Strategy = Field(description="The `limits` strategy every entry is evaluated with")
    # [impl->req~ratelimit-config-key-default~1]
    default: RateLimitEntry = Field(description="The generic default entry")

    environment: DeploymentEnvironment = Field(default=DeploymentEnvironment.local)
    client_address: ClientAddressConfig = Field(default_factory=ClientAddressConfig)
    web_grant_route_enabled: bool = Field(default=True)
    entries: dict[str, RateLimitEntry] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_entries(cls, data: Any) -> Any:
        """Named entries sit directly under `rate_limits` in the file, beside the four required
        keys. Collect them into `entries` so the settings model stays typed."""
        if not isinstance(data, dict):
            return data
        reserved = {"enabled", "storage_uri", "strategy", "default", "environment",
                    "client_address", "web_grant_route_enabled", "entries"}
        collected = dict(data.get("entries") or {})
        remainder = {key: value for key, value in data.items() if key not in reserved}
        collected.update(remainder)
        return {**{k: v for k, v in data.items() if k in reserved}, "entries": collected}

    @field_validator("storage_uri", mode="before")
    @classmethod
    def _expand_storage_uri(cls, value: Any) -> Any:
        if isinstance(value, str):
            return expand_env(value, default=DEFAULT_LOCAL_STORAGE_URI)
        return value

    @field_validator("environment", mode="before")
    @classmethod
    def _expand_environment(cls, value: Any) -> Any:
        if isinstance(value, str):
            return expand_env(value, default=DeploymentEnvironment.local)
        return value

    @property
    def storage_scheme(self) -> str:
        return self.storage_uri.split("://", 1)[0]

    @model_validator(mode="after")
    def _storage_backend_is_a_limits_backend(self):
        """Counters live in the configured `limits` storage backend, never in the auth refactor
        PostgreSQL schema."""
        # [impl->req~ratelimit-limits-library-and-storage-separation~1]
        if self.storage_scheme in FORBIDDEN_STORAGE_SCHEMES:
            raise ValueError("rate-limit counters never live in the PostgreSQL schema")
        # Production deployments back `limits` with shared Redis or Valkey storage so counters
        # apply across all backend replicas; in-memory storage is local development and tests
        # only.
        # [impl->req~ratelimit-shared-storage-in-production~1]
        if self.environment is DeploymentEnvironment.production:
            if self.storage_scheme in LOCAL_ONLY_STORAGE_SCHEMES:
                raise ValueError("in-memory rate-limit storage is local development and tests only")
            if self.storage_scheme not in SHARED_STORAGE_SCHEMES:
                raise ValueError(f"{self.storage_scheme!r} is no shared Redis or Valkey storage")
        return self

    def entry(self, name: str) -> RateLimitEntry:
        """The named entry. An unconfigured name is a configuration error, never a built-in
        fallback limit."""
        # [impl->req~ratelimit-all-limits-in-config-no-hardcoding~1]
        found = self.entries.get(name)
        if found is not None:
            return found
        raise RateLimitConfigError(f"{name!r} is not a configured rate-limit entry")


class GatewayRateLimitsConfig(BaseModel):
    """`gateway_rate_limits`. Declared here so the deployment renders Envoy's limits from the
    same source of truth; the backend enforces none of them.

    The two `POST /auth/create-user` entries are required fields rather than optional ones:
    gateway rate limiting on that pre-auth route is a load-bearing control on every deployment, so
    a configuration that omits either is rejected here at load time."""
    # [impl->req~sessions-create-user-gateway-limit-required~1]
    upgrade_anonymous: GatewayRateLimitEntry
    create_user_ip: GatewayRateLimitEntry
    create_user_deployment: GatewayRateLimitEntry


# The `POST /auth/create-user` gateway entries, and the route both of them cover. There are
# exactly two, and both cover the route's prepare and complete phases.
# [impl->req~sessions-create-user-two-gateway-limits~1]
CREATE_USER_GATEWAY_ENTRIES: tuple[str, ...] = ("create_user_ip", "create_user_deployment")
CREATE_USER_GATEWAY_ROUTE: str = "POST /auth/create-user"

# The per-client-IP entry keys on the canonical client address alone: the verified
# `issuer+subject_hash` may only ever be a secondary key here, because a fresh anonymous sign-in
# is free and mints a new subject on every call.
# [impl->req~sessions-client-ip-primary-key-on-create-user~1]
CREATE_USER_PRIMARY_KEY_POLICY: tuple[KeyComponent, ...] = (KeyComponent.ip,)
CREATE_USER_SECONDARY_KEY_POLICY: tuple[KeyComponent, ...] = (KeyComponent.issuer,
                                                              KeyComponent.subject_hash)

# The default ceilings. Both are configuration-tunable; these are the values the shipped file
# carries, not values any code path falls back to.
# [impl->req~sessions-create-user-per-ip-limit~1]
# [impl->req~sessions-create-user-deployment-wide-limit~1]
CREATE_USER_IP_DEFAULT_LIMIT = "10/minute"
CREATE_USER_DEPLOYMENT_DEFAULT_LIMIT = "100/minute; 2000/day"

# The deployment-wide ceiling is what bounds total account creation, so it must sit far above the
# single-address ceiling: the per-IP limit bounds per-source throughput only, and an attacker
# rotating source addresses is otherwise unbounded.
# [impl->req~sessions-create-user-limit-tuning-and-alert~1]
MINIMUM_DEPLOYMENT_TO_IP_RATIO = 10


def assert_create_user_gateway_limits(gateway: GatewayRateLimitsConfig | None) -> None:
    """Gateway rate limiting on `POST /auth/create-user` is a required, load-bearing control on
    every deployment: leaving this pre-auth route unthrottled is not a permitted configuration.
    A missing `gateway_rate_limits` section, or an entry that names another route, is a startup
    configuration error rather than a route that quietly runs unthrottled.

    Two limits apply, both covering the route's prepare and complete phases and both enforced as
    counters in a global rate-limit service: a per-client-IP limit keyed on the canonical client
    address, and a deployment-wide limit across all source addresses. Both fail closed, the
    deployment-wide ceiling carries the operational saturation alert, and it is sized well above
    the single-address ceiling because it, and not the per-IP limit, bounds total creation.
    """
    # [impl->req~sessions-create-user-gateway-limit-required~1]
    # [impl->req~sessions-create-user-two-gateway-limits~1]
    if gateway is None:
        raise RateLimitConfigError(
            f"gateway rate limiting on {CREATE_USER_GATEWAY_ROUTE} is required on every deployment")
    problems = [f"{name} must limit {CREATE_USER_GATEWAY_ROUTE}"
                for name in CREATE_USER_GATEWAY_ENTRIES
                if getattr(gateway, name).route != CREATE_USER_GATEWAY_ROUTE]
    for name in CREATE_USER_GATEWAY_ENTRIES:
        entry = getattr(gateway, name)
        # Both limits cover the prepare and the complete phase, and both are global counters.
        # [impl->req~sessions-create-user-two-gateway-limits~1]
        if set(entry.phases) != set(GatewayPhase):
            problems.append(f"{name} must cover the prepare and complete phases")
        if entry.enforcement is not GatewayCounterScope.global_rate_limit_service:
            problems.append(f"{name} must be a counter in the global rate-limit service")
        # Both limits fail closed: a ceiling that cannot be evaluated rejects.
        # [impl->req~sessions-create-user-limits-fail-closed~1]
        if entry.failure_mode is not FailureMode.fail_closed:
            problems.append(f"{name} must fail closed")
    # The client-IP key is the primary key for this pre-auth route, and never the verified
    # subject alone; no device fingerprint is a key component anywhere.
    # [impl->req~sessions-client-ip-primary-key-on-create-user~1]
    # [impl->req~sessions-create-user-per-ip-limit~1]
    ip_policy = parse_key_policy(gateway.create_user_ip.key)
    if ip_policy[:1] != CREATE_USER_PRIMARY_KEY_POLICY:
        problems.append("create_user_ip keys on the canonical client IP first")
    if set(ip_policy) & set(CREATE_USER_SECONDARY_KEY_POLICY) and len(ip_policy) < 2:
        problems.append("the verified subject is never the sole create-user key")
    # The deployment-wide limit spans all source addresses, so it keys on the deployment.
    # [impl->req~sessions-create-user-deployment-wide-limit~1]
    if parse_key_policy(gateway.create_user_deployment.key) != (KeyComponent.deployment,):
        problems.append("create_user_deployment applies across all source addresses")
    problems.extend(_create_user_ceiling_problems(gateway))
    if problems:
        raise RateLimitConfigError("; ".join(sorted(problems)))


def _create_user_ceiling_problems(gateway: GatewayRateLimitsConfig) -> list[str]:
    """The relationship between the two configured ceilings, and the alert the deployment-wide
    one carries. Both values are tunable; what is fixed is that the deployment-wide ceiling is
    the one that bounds total creation and that its sustained saturation alerts."""
    # [impl->req~sessions-create-user-limit-tuning-and-alert~1]
    problems: list[str] = []
    per_ip = gateway.create_user_ip.per_window()
    deployment = gateway.create_user_deployment.per_window()
    # The deployment-wide entry declares the windows that bound total creation.
    # [impl->req~sessions-create-user-deployment-wide-limit~1]
    missing = [window for window in ("minute", "day") if window not in deployment]
    if missing:
        problems.append("create_user_deployment declares a per-minute and a per-day ceiling")
    for window, ceiling in deployment.items():
        loosest = per_ip.get(window)
        if loosest is not None and ceiling < loosest * MINIMUM_DEPLOYMENT_TO_IP_RATIO:
            # A deployment-wide ceiling near the single-address one would bind on ordinary
            # traffic behind one NAT, and the per-IP limit must stay loose for those users.
            problems.append(f"the deployment-wide {window} ceiling must sit far above "
                            "the single-address ceiling")
    # Sustained saturation of the deployment-wide ceiling must raise an operational alert: at
    # launch scale, that ceiling binding at all is the anomaly signal.
    # [impl->req~sessions-create-user-limit-tuning-and-alert~1]
    if not gateway.create_user_deployment.saturation_alert:
        problems.append("sustained saturation of the deployment-wide ceiling must alert")
    return problems


# --- What the configuration must contain -----------------------------------------------------

# One named entry per public auth, identity, grant, restore, quota and adapter operation the
# split specs define, including the pre-auth completion entries `create_user` and
# `create_user_prepare`.
# [impl->req~ratelimit-config-named-entry-per-operation~1]
REQUIRED_OPERATION_ENTRIES: dict[AuthOperation, tuple[str, ...]] = {
    AuthOperation.create_user: ("create_user_prepare", "create_user"),
    # `upgrade_anonymous` completion has no backend named entry.
    AuthOperation.upgrade_anonymous_to_registered: ("upgrade_anonymous_prepare",),
    AuthOperation.claim_anonymous_grant: ("claim_anonymous_grant_prepare",
                                          "claim_anonymous_grant_prepare_ip",
                                          "claim_anonymous_grant",
                                          "claim_anonymous_grant_ip"),
    AuthOperation.claim_registered_grant: ("claim_registered_grant_prepare",
                                           "claim_registered_grant"),
    AuthOperation.restore_subscription: (
        "restore_subscription_user",
        "restore_subscription_subject",
        "restore_subscription_proof_fingerprint_failed",
        "restore_subscription_proof_fingerprint_total",
        "restore_subscription_store_subscription_cross_account",
        "restore_subscription_store_subscription_live_verification",
        "restore_subscription_destination_rejected_cross_account"),
    AuthOperation.sync: ("auth_sync",),
    # Sign-out-all has no named entry at all.
    AuthOperation.sign_out_all: (),
}

REQUIRED_IDENTITY_ENTRIES: tuple[str, ...] = ("users_me",)
REQUIRED_QUOTA_ENTRIES: tuple[str, ...] = ("quota_checked_request",)

# The three Firebase Admin identity-lookup admission budgets, each keyed exactly as the
# `create-user` key policy and the upgrade route require.
# [impl->req~ratelimit-config-firebase-identity-lookup-entries~1]
FIREBASE_LOOKUP_ENTRY_KEYS: dict[str, tuple[KeyComponent, ...]] = {
    "create_user_firebase_identity_lookup": (KeyComponent.deployment,),
    "create_user_firebase_identity_lookup_ip": (KeyComponent.ip,),
    "upgrade_anonymous_to_registered_firebase_identity_lookup": (
        KeyComponent.deployment, KeyComponent.firebase_project_id,
        KeyComponent.issuer, KeyComponent.subject_hash),
}

# The four load-bearing vendor device-bit calls on the free-grant claim path. The Device Recall
# read and write budgets are distinct from the Play Integrity verdict-verification budget.
# [impl->req~ratelimit-config-device-bit-provider-budgets~1]
DEVICE_BIT_BUDGET_ENTRIES: tuple[str, ...] = (
    "adapter_devicecheck_read",
    "adapter_devicecheck_write",
    "adapter_play_integrity_device_recall_read",
    "adapter_play_integrity_device_recall_write")

# The web gate's Cloudflare Turnstile `siteverify` budget.
# [impl->req~ratelimit-config-turnstile-siteverify-entry~1]
TURNSTILE_ENTRY = "adapter_cloudflare_turnstile_siteverify"

REQUIRED_ADAPTER_ENTRIES: tuple[str, ...] = (
    "adapter_play_integrity_verify",
    *DEVICE_BIT_BUDGET_ENTRIES,
    "adapter_firebase_lookup",
    "adapter_apple_store_status",
    "adapter_google_play_subscription_status",
    "provider_apple_store_live_verification_global",
    "provider_google_play_live_verification_global")

# Entries whose exhaustion is a server-side verification-capacity condition. Each must be
# fail-closed; the file may not choose fail-open for one.
FAIL_CLOSED_ENTRIES: frozenset[str] = frozenset({
    *FIREBASE_LOOKUP_ENTRY_KEYS,
    *DEVICE_BIT_BUDGET_ENTRIES,
    TURNSTILE_ENTRY,
    # Both counters of every anonymous-grant admission pair fail closed under this file's
    # default failure behaviour for security-sensitive admission controls.
    # [impl->req~ratelimit-grant-claim-admission-keys~1]
    "claim_anonymous_grant_prepare", "claim_anonymous_grant_prepare_ip",
    "claim_anonymous_grant", "claim_anonymous_grant_ip"})

# Backend entries that must not exist. `upgrade_anonymous` completion is bounded by the
# standalone Envoy per-linked-subject limit alone, and sign-out-all takes no backend counter.
# [impl->req~ratelimit-upgrade-anonymous-authoritative-gateway-bound~1]
# [impl->req~ratelimit-config-named-entry-per-operation~1]
FORBIDDEN_ENTRIES: frozenset[str] = frozenset({
    "upgrade_anonymous", "upgrade_anonymous_complete", "upgrade_anonymous_to_registered",
    "sign_out_all", "auth_sign_out_all"})

# Sign-out-all is exempt from the backend generic default entry: no backend counter rejects an
# authenticated request to it. Every other operation the default covers.
# [impl->req~ratelimit-config-named-entry-per-operation~1]
DEFAULT_ENTRY_EXEMPT: frozenset[AuthOperation] = frozenset({AuthOperation.sign_out_all})

# No route takes an exemption from gateway limiting: no bypass token, no priority lane, and no
# rule making the gateway treat a route as unauthenticated or anonymous for limiting purposes.
# [impl->req~ratelimit-config-named-entry-per-operation~1]
FORBIDDEN_EXEMPTION_KEYS: frozenset[str] = frozenset({
    "bypass_token", "bypass", "priority_lane", "priority", "exempt", "exemptions",
    "treat_as_anonymous", "treat_as_unauthenticated", "skip_limits"})

# The optional secondary `create-user` subject counter. It is never the route's sole key, never
# fused with the client-IP key, never fail-closed, and never required for admission.
# [impl->req~ratelimit-create-user-key-policy~1]
CREATE_USER_SECONDARY_ENTRY = "create_user_subject"
ADVISORY_ENTRIES: frozenset[str] = frozenset({CREATE_USER_SECONDARY_ENTRY})


def applies_default_entry(operation: AuthOperation) -> bool:
    """Whether the backend generic default entry covers this operation."""
    # [impl->req~ratelimit-config-named-entry-per-operation~1]
    return operation not in DEFAULT_ENTRY_EXEMPT


# Prepare-phase entries name themselves: every prepare-phase counter carries this marker, so
# the phase split is read off the configured names rather than declared a second time.
_PREPARE_ENTRY_MARKER = "_prepare"


def prepare_entries(operation: AuthOperation) -> tuple[str, ...]:
    """The blocking prepare-phase entries this operation configures."""
    # [impl->req~ratelimit-config-named-entry-per-operation~1]
    return tuple(name for name in REQUIRED_OPERATION_ENTRIES[operation]
                 if _PREPARE_ENTRY_MARKER in name and is_blocking(name))


def complete_entries(operation: AuthOperation) -> tuple[str, ...]:
    """The blocking entries this operation configures outside its prepare phase."""
    # [impl->req~ratelimit-config-named-entry-per-operation~1]
    return tuple(name for name in REQUIRED_OPERATION_ENTRIES[operation]
                 if _PREPARE_ENTRY_MARKER not in name and is_blocking(name))


def is_blocking(name: str) -> bool:
    """Whether a configured entry can reject a request. The advisory secondary counters are
    abuse telemetry and soft dampeners, never required for admission."""
    # [impl->req~ratelimit-create-user-key-policy~1]
    return name not in ADVISORY_ENTRIES


def required_entry_names(*, web_grant_route_enabled: bool = True) -> tuple[str, ...]:
    """Every named entry the configuration must carry."""
    # [impl->req~ratelimit-config-named-entry-per-operation~1]
    names: list[str] = []
    for operation in AuthOperation:
        names.extend(REQUIRED_OPERATION_ENTRIES[operation])
    names.extend(REQUIRED_IDENTITY_ENTRIES)
    names.extend(REQUIRED_QUOTA_ENTRIES)
    names.extend(FIREBASE_LOOKUP_ENTRY_KEYS)
    names.extend(REQUIRED_ADAPTER_ENTRIES)
    if web_grant_route_enabled and TURNSTILE_ENTRY not in names:
        names.append(TURNSTILE_ENTRY)
    return tuple(dict.fromkeys(names))


def _check_named_keys(config: RateLimitsConfig, problems: list[str]) -> None:
    """The key policies this specification fixes by name."""
    # For `create-user`, the canonical client-IP key is the primary request-rate key, and
    # Firebase Admin lookup admission on the route must not rely on the subject at all.
    # [impl->req~ratelimit-create-user-key-policy~1]
    for name in ("create_user", "create_user_prepare"):
        entry = config.entries.get(name)
        if entry is not None and entry.policy != (KeyComponent.ip,):
            problems.append(f"{name} keys on the canonical client IP alone")

    # The two `create_user` lookup entries are standalone counters keyed on the deployment alone
    # and the client IP alone. Neither may be fused with the other, with an issuer or subject
    # component, or with a `firebase_project_id` component.
    # [impl->req~ratelimit-config-firebase-identity-lookup-entries~1]
    # [impl->req~ratelimit-create-user-key-policy~1]
    for name, expected in FIREBASE_LOOKUP_ENTRY_KEYS.items():
        entry = config.entries.get(name)
        if entry is None:
            continue
        if entry.policy != expected:
            problems.append(f"{name} keys on {'+'.join(expected)}")

    # The optional secondary subject counter is a separate entry: never fused with the IP key,
    # never the route's sole key, never fail-closed, never required for admission.
    # [impl->req~ratelimit-create-user-key-policy~1]
    secondary = config.entries.get(CREATE_USER_SECONDARY_ENTRY)
    if secondary is not None:
        if secondary.policy != (KeyComponent.issuer, KeyComponent.subject_hash):
            problems.append(f"{CREATE_USER_SECONDARY_ENTRY} keys on issuer+subject_hash")
        if secondary.failure_mode is not FailureMode.fail_open:
            problems.append(f"{CREATE_USER_SECONDARY_ENTRY} is never fail-closed")
        if "create_user" not in config.entries:
            problems.append(f"{CREATE_USER_SECONDARY_ENTRY} is never the route's sole key")

    # Anonymous-grant admission is keyed on the barrier-resolved user alone, under one identical
    # key policy on every platform including web, and each entry is paired with an independent
    # client-IP counter. No device-check value participates in either.
    # [impl->req~ratelimit-grant-claim-admission-keys~1]
    for name in ("claim_anonymous_grant_prepare", "claim_anonymous_grant"):
        entry = config.entries.get(name)
        if entry is not None and entry.policy != (KeyComponent.user,):
            problems.append(f"{name} keys on the barrier-resolved user alone")
        paired = config.entries.get(f"{name}_ip")
        if paired is not None and paired.policy != (KeyComponent.ip,):
            problems.append(f"{name}_ip keys on the canonical client IP alone")

    # The registered-grant claim's IdP-account component is the stored, redacted account hash.
    # [impl->req~ratelimit-provider-account-key-component~1]
    registered = config.entries.get("claim_registered_grant")
    if registered is not None and registered.policy != (KeyComponent.user,
                                                        KeyComponent.idp_account_hash):
        problems.append("claim_registered_grant keys on user+idp_account_hash")


def _check_exemptions(raw: Any, problems: list[str], path: str = "rate_limits") -> None:
    """No configured shape may grant a route an exemption from limiting."""
    # [impl->req~ratelimit-config-named-entry-per-operation~1]
    if isinstance(raw, dict):
        for key, value in raw.items():
            if str(key).lower() in FORBIDDEN_EXEMPTION_KEYS:
                problems.append(f"{path}.{key} is a limiting exemption; no route takes one")
            _check_exemptions(value, problems, f"{path}.{key}")
    elif isinstance(raw, list):
        for item in raw:
            _check_exemptions(item, problems, path)


def assert_rate_limit_config(config: RateLimitsConfig,
                             *,
                             raw: Any = None) -> None:
    """The startup check. Fails closed, before traffic, on a configuration this specification
    cannot serve."""
    # [impl->req~ratelimit-config-must-include-at-least~1]
    # [impl->req~ratelimit-all-limits-in-config-no-hardcoding~1]
    # The recommended values in the specification are initial deployment policy only: this
    # check reads the shipped application configuration file and never substitutes a built-in
    # limit for a missing one.
    # [impl->req~ratelimit-recommended-values-are-initial-policy~1]
    problems: list[str] = []

    for name in required_entry_names(web_grant_route_enabled=config.web_grant_route_enabled):
        if name not in config.entries:
            # The Turnstile entry's absence while the web grant route is enabled is itself a
            # startup configuration error.
            # [impl->req~ratelimit-config-turnstile-siteverify-entry~1]
            problems.append(f"{name} is not configured")

    for name in sorted(FORBIDDEN_ENTRIES & set(config.entries)):
        # `upgrade_anonymous` completion is bounded by the standalone Envoy per-linked-subject
        # limit alone; a backend request-rate counter on the same identity material could never
        # reject a request that limit had not already rejected. Sign-out-all gains no backend
        # rejecting quota and no dedicated per-subject quota.
        # [impl->req~ratelimit-upgrade-anonymous-authoritative-gateway-bound~1]
        # [impl->req~ratelimit-config-named-entry-per-operation~1]
        problems.append(f"{name} takes no backend named entry")

    for name in sorted(FAIL_CLOSED_ENTRIES):
        entry = config.entries.get(name)
        if entry is not None and entry.failure_mode is not FailureMode.fail_closed:
            # [impl->req~ratelimit-default-fail-closed-unless-configured~1]
            # [impl->req~ratelimit-config-device-bit-provider-budgets~1]
            # [impl->req~ratelimit-config-turnstile-siteverify-entry~1]
            problems.append(f"{name} is a security-sensitive admission control and fails closed")

    # Each Firebase lookup budget is distinct from its endpoint request-rate entry and from the
    # global `adapter_firebase_lookup` provider-call budget: four separate counters.
    # [impl->req~ratelimit-config-firebase-identity-lookup-entries~1]
    lookup_names = (*FIREBASE_LOOKUP_ENTRY_KEYS, "adapter_firebase_lookup")
    if len(set(lookup_names)) != len(lookup_names):
        problems.append("the Firebase lookup budgets are four distinct counters")

    # The Device Recall read and write budgets are distinct from the Play Integrity
    # verdict-verification budget.
    # [impl->req~ratelimit-config-device-bit-provider-budgets~1]
    if "adapter_play_integrity_verify" in DEVICE_BIT_BUDGET_ENTRIES:
        problems.append("Device Recall budgets are distinct from the verdict-verification budget")

    _check_named_keys(config, problems)
    if raw is not None:
        _check_exemptions(raw, problems)

    if problems:
        raise RateLimitConfigError("; ".join(sorted(set(problems))))
