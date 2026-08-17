"""The rate-limit configuration contract and the shipped `config/config.yaml`."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.ratelimit.config import (
    DEVICE_BIT_BUDGET_ENTRIES,
    FIREBASE_LOOKUP_ENTRY_KEYS,
    TURNSTILE_ENTRY,
    DeploymentEnvironment,
    FailureMode,
    GatewayRateLimitsConfig,
    RateLimitConfigError,
    RateLimitEntry,
    RateLimitsConfig,
    Strategy,
    applies_default_entry,
    assert_rate_limit_config,
    is_blocking,
    required_entry_names,
)
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import RateLimiter, UnconfiguredLimitError

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def shipped() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def shipped_rate_limits() -> RateLimitsConfig:
    return RateLimitsConfig(**shipped()["rate_limits"])


def minimal(**overrides) -> dict:
    data = {"enabled": True, "storage_uri": "memory://", "strategy": "moving-window",
            "default": {"limit": "120/minute", "key": "ip"}}
    data.update(overrides)
    return data


# --- The shipped configuration: the umbrella conformance test --------------------------------

# The recommended initial configuration, transcribed from
# `08-rate-limits-and-admission-control.md`. The shipped file must carry each of these entries
# with exactly this limit string, key policy, and failure mode.
RECOMMENDED_ENTRIES: dict[str, dict[str, str]] = {
    "auth_sync": {"limit": "60/minute", "key": "issuer+subject_hash"},
    "users_me": {"limit": "30/minute", "key": "issuer+subject_hash"},
    "create_user_prepare": {"limit": "10/minute", "key": "ip"},
    "create_user": {"limit": "10/minute", "key": "ip"},
    "create_user_firebase_identity_lookup": {
        "limit": "60/minute", "key": "deployment", "failure_mode": "fail_closed"},
    "create_user_firebase_identity_lookup_ip": {
        "limit": "10/minute", "key": "ip", "failure_mode": "fail_closed"},
    "upgrade_anonymous_prepare": {"limit": "5/minute; 20/hour", "key": "ip+issuer+subject_hash"},
    "upgrade_anonymous_to_registered_firebase_identity_lookup": {
        "limit": "3/minute; 10/hour",
        "key": "deployment+firebase_project_id+issuer+subject_hash",
        "failure_mode": "fail_closed"},
    "claim_anonymous_grant_prepare": {"limit": "5/minute; 20/hour", "key": "user"},
    "claim_anonymous_grant_prepare_ip": {"limit": "10/minute; 60/hour", "key": "ip"},
    "claim_anonymous_grant": {"limit": "2/minute; 6/hour; 20/day", "key": "user"},
    "claim_anonymous_grant_ip": {"limit": "10/minute; 30/hour; 100/day", "key": "ip"},
    "claim_registered_grant_prepare": {"limit": "5/minute; 20/hour", "key": "user"},
    "claim_registered_grant": {"limit": "2/minute; 6/hour; 20/day", "key": "user+idp_account_hash"},
    "restore_subscription_user": {"limit": "10/day", "key": "user"},
    "restore_subscription_subject": {"limit": "20/day", "key": "issuer+subject_hash"},
    "restore_subscription_proof_fingerprint_failed": {
        "limit": "5/hour", "key": "restore_proof_fingerprint"},
    "restore_subscription_proof_fingerprint_total": {
        "limit": "20/day", "key": "restore_proof_fingerprint"},
    "restore_subscription_store_subscription_cross_account": {
        "limit": "3/hour", "key": "provider+external_id"},
    "restore_subscription_store_subscription_live_verification": {
        "limit": "1/minute", "key": "provider+external_id"},
    "restore_subscription_destination_rejected_cross_account": {"limit": "3/day", "key": "user"},
    "quota_checked_request": {"limit": "120/minute", "key": "user"},
    "adapter_play_integrity_verify": {"limit": "60/minute", "key": "deployment+package_name"},
    "adapter_devicecheck_read": {
        "limit": "30/minute", "key": "deployment+apple_team_id", "failure_mode": "fail_closed"},
    "adapter_devicecheck_write": {
        "limit": "20/minute", "key": "deployment+apple_team_id", "failure_mode": "fail_closed"},
    "adapter_play_integrity_device_recall_read": {
        "limit": "30/minute", "key": "deployment+package_name", "failure_mode": "fail_closed"},
    "adapter_play_integrity_device_recall_write": {
        "limit": "20/minute", "key": "deployment+package_name", "failure_mode": "fail_closed"},
    "adapter_cloudflare_turnstile_siteverify": {
        "limit": "60/minute", "key": "deployment", "failure_mode": "fail_closed"},
    "adapter_firebase_lookup": {"limit": "30/minute", "key": "deployment+firebase_project_id"},
    "adapter_apple_store_status": {"limit": "30/minute", "key": "deployment+bundle_id"},
    "adapter_google_play_subscription_status": {
        "limit": "30/minute", "key": "deployment+package_name"},
    "provider_apple_store_live_verification_global": {"limit": "300/minute", "key": "deployment"},
    "provider_google_play_live_verification_global": {"limit": "300/minute", "key": "deployment"},
}


# [utest->req~ratelimit-config-shape-and-defaults~1]
def test_shipped_config_matches_the_recommended_shape_and_defaults():
    raw = shipped()["rate_limits"]
    assert raw["enabled"] is True
    assert raw["storage_uri"] == "${RATE_LIMIT_STORAGE_URI}"
    assert raw["strategy"] == "moving-window"
    assert raw["default"] == {"limit": "120/minute", "key": "ip", "failure_mode": "fail_closed"}
    for name, expected in RECOMMENDED_ENTRIES.items():
        assert name in raw, f"{name} is missing from the shipped configuration"
        assert raw[name]["limit"] == expected["limit"], name
        assert raw[name]["key"] == expected["key"], name
        assert raw[name].get("failure_mode", "fail_closed") == \
            expected.get("failure_mode", "fail_closed"), name


# [utest->req~ratelimit-config-shape-and-defaults~1]
def test_shipped_config_loads_and_passes_the_startup_check():
    config = shipped_rate_limits()
    assert_rate_limit_config(config, raw=shipped()["rate_limits"])
    assert config.strategy is Strategy.moving_window
    assert config.default.limit == "120/minute"
    gateway = GatewayRateLimitsConfig(**shipped()["gateway_rate_limits"])
    assert gateway.upgrade_anonymous.limit == "3/hour"


# --- The four required configuration keys ----------------------------------------------------

# [utest->req~ratelimit-config-must-include-at-least~1]
# [utest->req~ratelimit-config-key-enabled~1]
# [utest->req~ratelimit-config-key-storage-uri~1]
# [utest->req~ratelimit-config-key-strategy~1]
# [utest->req~ratelimit-config-key-default~1]
@pytest.mark.parametrize("missing", ["enabled", "storage_uri", "strategy", "default"])
def test_configuration_must_include_the_four_required_keys(missing):
    data = minimal()
    del data[missing]
    with pytest.raises(ValidationError):
        RateLimitsConfig(**data)


# [utest->req~ratelimit-config-key-enabled~1]
def test_enabled_false_admits_every_request():
    limiter = RateLimiter(RateLimitsConfig(**minimal(enabled=False,
                                                     probe={"limit": "1/minute", "key": "ip"})))
    assert limiter.hit("probe", "k").allowed
    assert limiter.hit("probe", "k").allowed


# [utest->req~ratelimit-config-key-strategy~1]
def test_strategy_selects_the_limits_strategy():
    from limits.strategies import FixedWindowRateLimiter, MovingWindowRateLimiter
    assert isinstance(RateLimiter(RateLimitsConfig(**minimal())).strategy, MovingWindowRateLimiter)
    fixed = RateLimiter(RateLimitsConfig(**minimal(strategy="fixed-window")))
    assert isinstance(fixed.strategy, FixedWindowRateLimiter)


# [utest->req~ratelimit-config-key-default~1]
def test_the_default_entry_is_a_full_entry():
    config = RateLimitsConfig(**minimal())
    assert config.default.definition() == {"limit": "120/minute", "key": "ip", "cost": 1,
                                           "enabled": True,
                                           "failure_mode": FailureMode.fail_closed}


# --- Entry shape -----------------------------------------------------------------------------

# [utest->req~ratelimit-entry-must-define~1]
def test_every_entry_defines_all_five_facts():
    entry = RateLimitEntry(limit="2/minute", key="ip")
    definition = entry.definition()
    assert set(definition) == {"limit", "key", "cost", "enabled", "failure_mode"}
    assert all(value is not None for value in definition.values())


# [utest->req~ratelimit-config-per-entry-fields~1]
def test_entry_fields_are_limit_key_and_three_optionals():
    fields = RateLimitEntry.model_fields
    assert set(fields) == {"limit", "key", "cost", "enabled", "failure_mode"}
    assert fields["limit"].is_required() and fields["key"].is_required()
    assert not any(fields[name].is_required() for name in ("cost", "enabled", "failure_mode"))


# [utest->req~ratelimit-entry-limit-string~1]
def test_the_limit_string_must_parse():
    with pytest.raises(ValidationError):
        RateLimitEntry(limit="often", key="ip")
    assert RateLimitEntry(limit="2/minute", key="ip").limit == "2/minute"


# [utest->req~ratelimit-entry-key-policy~1]
def test_the_key_policy_must_name_declared_components():
    with pytest.raises(ValidationError):
        RateLimitEntry(limit="2/minute", key="raw_id_token")
    assert RateLimitEntry(limit="2/minute", key="deployment+package_name").policy == (
        KeyComponent.deployment, KeyComponent.package_name)


# [utest->req~ratelimit-entry-cost~1]
def test_cost_defaults_to_one_and_is_deducted_when_configured():
    assert RateLimitEntry(limit="2/minute", key="ip").cost == 1
    limiter = RateLimiter(RateLimitsConfig(**minimal(
        heavy={"limit": "4/minute", "key": "ip", "cost": 3})))
    assert limiter.hit("heavy", "k").allowed
    assert not limiter.hit("heavy", "k").allowed


# [utest->req~ratelimit-entry-enabled~1]
def test_a_disabled_entry_never_rejects():
    limiter = RateLimiter(RateLimitsConfig(**minimal(
        off={"limit": "1/minute", "key": "ip", "enabled": False})))
    assert limiter.hit("off", "k").allowed
    assert limiter.hit("off", "k").allowed


class _BrokenStorage:
    def __getattr__(self, name):
        raise ConnectionError("the limits backend is unavailable")


# [utest->req~ratelimit-entry-failure-behavior~1]
# [utest->req~ratelimit-default-fail-closed-unless-configured~1]
def test_failure_behaviour_when_the_limits_backend_is_unavailable():
    config = RateLimitsConfig(**minimal(
        closed={"limit": "5/minute", "key": "ip"},
        opened={"limit": "5/minute", "key": "ip", "failure_mode": "fail_open"}))
    limiter = RateLimiter(config)
    limiter._strategy = _BrokenStorage()  # type: ignore[assignment]
    closed = limiter.hit("closed", "k")
    opened = limiter.hit("opened", "k")
    assert closed.storage_failed and not closed.allowed
    assert opened.storage_failed and opened.allowed


# [utest->req~ratelimit-default-fail-closed-unless-configured~1]
def test_an_entry_that_names_no_failure_mode_fails_closed():
    assert RateLimitEntry(limit="5/minute", key="ip").failure_mode is FailureMode.fail_closed


# [utest->req~ratelimit-default-fail-closed-unless-configured~1]
def test_a_security_sensitive_entry_may_not_choose_fail_open():
    for name in (*FIREBASE_LOOKUP_ENTRY_KEYS, *DEVICE_BIT_BUDGET_ENTRIES, TURNSTILE_ENTRY):
        raw = shipped()["rate_limits"]
        raw[name] = {**raw[name], "failure_mode": "fail_open"}
        with pytest.raises(RateLimitConfigError, match="fails closed"):
            assert_rate_limit_config(RateLimitsConfig(**raw))


# --- Storage ---------------------------------------------------------------------------------

# [utest->req~ratelimit-limits-library-and-storage-separation~1]
def test_counters_never_live_in_the_postgresql_schema():
    with pytest.raises(ValidationError, match="never live in the PostgreSQL schema"):
        RateLimitsConfig(**minimal(storage_uri="postgresql+asyncpg://user:pw@db:5432/ns"))


# [utest->req~ratelimit-limits-library-and-storage-separation~1]
def test_the_backend_enforces_limits_through_the_limits_library():
    from limits import RateLimitItem
    from limits.storage import MemoryStorage
    from limits.strategies import RateLimiter as LimitsStrategy

    limiter = RateLimiter(RateLimitsConfig(**minimal(probe={"limit": "1/minute", "key": "ip"})))
    assert isinstance(limiter.strategy, LimitsStrategy)
    assert isinstance(limiter.strategy.storage, MemoryStorage)
    assert all(isinstance(window, RateLimitItem) for window in limiter.windows("probe"))
    assert limiter.hit("probe", "k").allowed
    assert not limiter.hit("probe", "k").allowed


# [utest->req~ratelimit-shared-storage-in-production~1]
def test_production_requires_shared_redis_or_valkey_storage():
    with pytest.raises(ValidationError, match="local development and tests only"):
        RateLimitsConfig(**minimal(environment="production", storage_uri="memory://"))
    with pytest.raises(ValidationError, match="no shared Redis or Valkey"):
        RateLimitsConfig(**minimal(environment="production", storage_uri="memcached://host:11211"))
    shared = RateLimitsConfig(**minimal(environment="production",
                                        storage_uri="redis://limits:6379/0"))
    assert shared.environment is DeploymentEnvironment.production
    # In-memory storage remains acceptable for local development and tests.
    assert RateLimitsConfig(**minimal()).storage_scheme == "memory"


# --- The canonical client address is configuration-tunable ------------------------------------

# [utest->req~ratelimit-canonical-client-ip-resolution~2]
def test_the_ipv6_prefix_and_the_unresolved_ceiling_come_from_configuration():
    from nativespeaker.api.ratelimit.keys import (
        UNRESOLVED_ADDRESS_KEY,
        AddressSource,
        gateway_resolved_address,
    )
    address = gateway_resolved_address("2001:db8:1:2::1",
                                       source=AddressSource.envoy_direct_downstream)
    sibling = gateway_resolved_address("2001:db8:1:3::1",
                                       source=AddressSource.envoy_direct_downstream)
    narrow = RateLimiter(RateLimitsConfig(**minimal()))
    assert narrow.client_ip_key(address) != narrow.client_ip_key(sibling)
    wide = RateLimiter(RateLimitsConfig(**minimal(
        client_address={"ipv6_prefix": 48, "unresolved_limit": "3/minute"})))
    assert wide.client_ip_key(address) == wide.client_ip_key(sibling)
    # The unresolved bucket runs at the configured single-address ceiling, never unlimited.
    assert wide.unresolved_address_ceiling().limit == "3/minute"
    assert narrow.unresolved_address_ceiling().limit == "10/minute"
    assert wide.client_ip_key(None) == UNRESOLVED_ADDRESS_KEY
    with pytest.raises(ValidationError):
        RateLimitsConfig(**minimal(client_address={"ipv6_prefix": 32}))


# --- No hard-coded limits --------------------------------------------------------------------

# [utest->req~ratelimit-all-limits-in-config-no-hardcoding~1]
def test_an_unconfigured_limit_is_an_error_and_never_a_built_in_fallback():
    limiter = RateLimiter(RateLimitsConfig(**minimal()))
    with pytest.raises(UnconfiguredLimitError):
        limiter.hit("create_user", "k")


# [utest->req~ratelimit-all-limits-in-config-no-hardcoding~1]
def test_every_facet_of_a_limit_comes_from_the_file():
    config = RateLimitsConfig(**minimal(probe={"limit": "7/minute", "key": "issuer+subject_hash",
                                               "cost": 2, "enabled": False,
                                               "failure_mode": "fail_open"}))
    entry = RateLimiter(config).entry("probe")
    assert entry.definition() == {"limit": "7/minute", "key": "issuer+subject_hash", "cost": 2,
                                  "enabled": False, "failure_mode": FailureMode.fail_open}
    assert config.storage_uri == "memory://" and config.strategy is Strategy.moving_window


# [utest->req~ratelimit-parse-many-multi-window-strings~1]
def test_multi_window_strings_are_enforced_as_a_set():
    limiter = RateLimiter(RateLimitsConfig(**minimal(
        multi={"limit": "2/minute; 6/hour; 20/day", "key": "user"})))
    assert [str(window) for window in limiter.windows("multi")] == [
        "2 per 1 minute", "6 per 1 hour", "20 per 1 day"]
    # The narrower hour window rejects while the minute window still has room.
    wide = RateLimiter(RateLimitsConfig(**minimal(pair={"limit": "10/minute; 2/hour", "key": "ip"})))
    assert wide.hit("pair", "k").allowed
    assert wide.hit("pair", "k").allowed
    denied = wide.hit("pair", "k")
    assert not denied.allowed and denied.retry_after_seconds is not None


# --- Named entries per operation -------------------------------------------------------------

# [utest->req~ratelimit-config-named-entry-per-operation~1]
def test_one_named_entry_per_operation_including_the_pre_auth_create_user_entries():
    config = shipped_rate_limits()
    for name in required_entry_names():
        assert name in config.entries, f"{name} is not configured"
    assert {"create_user", "create_user_prepare"} <= set(config.entries)
    for name in required_entry_names():
        raw = shipped()["rate_limits"]
        del raw[name]
        with pytest.raises(RateLimitConfigError, match=f"{name} is not configured"):
            assert_rate_limit_config(RateLimitsConfig(**raw))


# [utest->req~ratelimit-config-named-entry-per-operation~1]
# [utest->req~ratelimit-upgrade-anonymous-authoritative-gateway-bound~1]
def test_upgrade_anonymous_completion_has_no_backend_named_entry():
    config = shipped_rate_limits()
    assert "upgrade_anonymous" not in config.entries
    raw = shipped()["rate_limits"]
    raw["upgrade_anonymous"] = {"limit": "3/hour", "key": "issuer+subject_hash"}
    with pytest.raises(RateLimitConfigError, match="takes no backend named entry"):
        assert_rate_limit_config(RateLimitsConfig(**raw))


# [utest->req~ratelimit-config-named-entry-per-operation~1]
def test_sign_out_all_has_no_named_entry_and_is_exempt_from_the_default_entry():
    config = shipped_rate_limits()
    assert "sign_out_all" not in config.entries
    assert not applies_default_entry(AuthOperation.sign_out_all)
    for operation in AuthOperation:
        if operation is not AuthOperation.sign_out_all:
            assert applies_default_entry(operation)
    raw = shipped()["rate_limits"]
    raw["sign_out_all"] = {"limit": "5/hour", "key": "user"}
    with pytest.raises(RateLimitConfigError, match="takes no backend named entry"):
        assert_rate_limit_config(RateLimitsConfig(**raw))


# [utest->req~ratelimit-config-named-entry-per-operation~1]
@pytest.mark.parametrize("exemption", ["bypass_token", "priority_lane", "treat_as_anonymous",
                                       "skip_limits"])
def test_no_route_takes_an_exemption_from_limiting(exemption):
    raw = shipped()["rate_limits"]
    raw["claim_anonymous_grant"] = {**raw["claim_anonymous_grant"], exemption: "yes"}
    with pytest.raises(RateLimitConfigError, match="no route takes one"):
        assert_rate_limit_config(RateLimitsConfig(**raw), raw=raw)


# --- Firebase identity-lookup budgets --------------------------------------------------------

# [utest->req~ratelimit-config-firebase-identity-lookup-entries~1]
def test_the_three_firebase_lookup_budgets_are_distinct_and_fail_closed():
    config = shipped_rate_limits()
    names = ("create_user_firebase_identity_lookup", "create_user_firebase_identity_lookup_ip",
             "upgrade_anonymous_to_registered_firebase_identity_lookup")
    assert set(names) == set(FIREBASE_LOOKUP_ENTRY_KEYS)
    for name in names:
        entry = config.entries[name]
        assert entry.failure_mode is FailureMode.fail_closed
        assert entry.policy == FIREBASE_LOOKUP_ENTRY_KEYS[name]
    # Each is distinct from the global provider-call budget.
    assert "adapter_firebase_lookup" not in names
    keys = {name: config.entries[name].key for name in names}
    assert len(set(keys.values())) == 3


# [utest->req~ratelimit-config-firebase-identity-lookup-entries~1]
# [utest->req~ratelimit-create-user-key-policy~1]
@pytest.mark.parametrize("fused", ["deployment+ip", "deployment+issuer+subject_hash",
                                   "deployment+firebase_project_id"])
def test_the_create_user_lookup_budgets_are_never_fused(fused):
    raw = shipped()["rate_limits"]
    raw["create_user_firebase_identity_lookup"] = {"limit": "60/minute", "key": fused,
                                                   "failure_mode": "fail_closed"}
    with pytest.raises(RateLimitConfigError, match="keys on deployment"):
        assert_rate_limit_config(RateLimitsConfig(**raw))


# --- Device-bit provider budgets ---------------------------------------------------------------

# [utest->req~ratelimit-config-device-bit-provider-budgets~1]
def test_four_fail_closed_device_bit_budgets_distinct_from_the_verdict_budget():
    config = shipped_rate_limits()
    assert DEVICE_BIT_BUDGET_ENTRIES == (
        "adapter_devicecheck_read", "adapter_devicecheck_write",
        "adapter_play_integrity_device_recall_read", "adapter_play_integrity_device_recall_write")
    for name in DEVICE_BIT_BUDGET_ENTRIES:
        assert config.entries[name].failure_mode is FailureMode.fail_closed
    assert "adapter_play_integrity_verify" not in DEVICE_BIT_BUDGET_ENTRIES
    assert "adapter_play_integrity_verify" in config.entries


# --- The Turnstile siteverify budget ------------------------------------------------------------

# [utest->req~ratelimit-config-turnstile-siteverify-entry~1]
def test_the_turnstile_budget_is_named_and_fail_closed():
    entry = shipped_rate_limits().entries[TURNSTILE_ENTRY]
    assert entry.failure_mode is FailureMode.fail_closed
    assert entry.policy == (KeyComponent.deployment,)


# [utest->req~ratelimit-config-turnstile-siteverify-entry~1]
def test_a_missing_turnstile_entry_is_a_startup_error_while_the_web_grant_route_is_enabled():
    raw = shipped()["rate_limits"]
    del raw[TURNSTILE_ENTRY]
    with pytest.raises(RateLimitConfigError, match=f"{TURNSTILE_ENTRY} is not configured"):
        assert_rate_limit_config(RateLimitsConfig(**raw, web_grant_route_enabled=True))
    # With the web grant route disabled the entry is not required.
    assert_rate_limit_config(RateLimitsConfig(**raw, web_grant_route_enabled=False))


# --- create-user key policy ----------------------------------------------------------------------

# [utest->req~ratelimit-create-user-key-policy~1]
def test_create_user_keys_on_the_canonical_client_ip():
    config = shipped_rate_limits()
    assert config.entries["create_user"].policy == (KeyComponent.ip,)
    assert config.entries["create_user_prepare"].policy == (KeyComponent.ip,)
    assert config.entries["create_user_firebase_identity_lookup"].policy == (
        KeyComponent.deployment,)
    assert config.entries["create_user_firebase_identity_lookup_ip"].policy == (KeyComponent.ip,)
    raw = shipped()["rate_limits"]
    raw["create_user"] = {"limit": "10/minute", "key": "issuer+subject_hash"}
    with pytest.raises(RateLimitConfigError, match="canonical client IP alone"):
        assert_rate_limit_config(RateLimitsConfig(**raw))


# [utest->req~ratelimit-create-user-key-policy~1]
def test_the_optional_create_user_subject_counter_is_secondary_and_non_blocking():
    raw = shipped()["rate_limits"]
    raw["create_user_subject"] = {"limit": "20/hour", "key": "issuer+subject_hash",
                                  "failure_mode": "fail_open"}
    assert_rate_limit_config(RateLimitsConfig(**raw))
    assert not is_blocking("create_user_subject")
    assert is_blocking("create_user")
    # It is never fail-closed and never fused with the client-IP key.
    raw["create_user_subject"] = {"limit": "20/hour", "key": "issuer+subject_hash"}
    with pytest.raises(RateLimitConfigError, match="never fail-closed"):
        assert_rate_limit_config(RateLimitsConfig(**raw))
    with pytest.raises(ValidationError):
        RateLimitEntry(limit="20/hour", key="ip+user")


# [utest->req~ratelimit-create-user-key-policy~1]
def test_no_device_fingerprint_key_on_the_create_user_route():
    with pytest.raises(ValidationError):
        RateLimitEntry(limit="10/minute", key="ip+device_fingerprint")


# --- Grant-claim admission keys -----------------------------------------------------------------

# [utest->req~ratelimit-grant-claim-admission-keys~1]
def test_anonymous_grant_admission_pairs_are_user_and_ip_and_never_fused():
    config = shipped_rate_limits()
    for name in ("claim_anonymous_grant_prepare", "claim_anonymous_grant"):
        assert config.entries[name].policy == (KeyComponent.user,)
        assert config.entries[f"{name}_ip"].policy == (KeyComponent.ip,)
        assert config.entries[name].failure_mode is FailureMode.fail_closed
        assert config.entries[f"{name}_ip"].failure_mode is FailureMode.fail_closed
    with pytest.raises(ValidationError, match="fuses the user and client-IP counters"):
        RateLimitEntry(limit="2/minute", key="user+ip")
    raw = shipped()["rate_limits"]
    raw["claim_anonymous_grant"] = {"limit": "2/minute", "key": "idp_account_hash"}
    with pytest.raises(RateLimitConfigError, match="barrier-resolved user alone"):
        assert_rate_limit_config(RateLimitsConfig(**raw))


# --- The upgrade route's authoritative gateway bound ---------------------------------------------

# [utest->req~ratelimit-upgrade-anonymous-authoritative-gateway-bound~1]
def test_the_upgrade_route_keeps_only_its_firebase_lookup_budget():
    config = shipped_rate_limits()
    entry = config.entries["upgrade_anonymous_to_registered_firebase_identity_lookup"]
    assert entry.failure_mode is FailureMode.fail_closed
    assert not any(name.startswith("upgrade_anonymous")
                   and name.endswith(("_complete", "_completion"))
                   for name in config.entries)
    gateway = GatewayRateLimitsConfig(**shipped()["gateway_rate_limits"]).upgrade_anonymous
    assert gateway.route == "POST /auth/upgrade-anonymous"
    assert gateway.limit == "3/hour"
    assert gateway.key == "issuer+subject_hash"
    assert gateway.evaluate_after == "envoy_jwt_verification"
