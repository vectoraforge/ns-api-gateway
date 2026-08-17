"""Pre-auth route rate limiting and the canonical client-IP key, as
`01-sessions-and-identity-resolution.md` defines them: the two required `POST /auth/create-user`
gateway ceilings, what their rejection looks like, and how the one canonical client address
becomes a limiter key.
"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.ratelimit.config import (
    CREATE_USER_DEPLOYMENT_DEFAULT_LIMIT,
    CREATE_USER_GATEWAY_ENTRIES,
    CREATE_USER_GATEWAY_ROUTE,
    CREATE_USER_IP_DEFAULT_LIMIT,
    ClientAddressConfig,
    FailureMode,
    GatewayCounterScope,
    GatewayPhase,
    GatewayRateLimitEntry,
    GatewayRateLimitsConfig,
    RateLimitConfigError,
    RateLimitsConfig,
    assert_create_user_gateway_limits,
)
from nativespeaker.api.ratelimit.keys import (
    CLIENT_FORWARDING_HEADERS,
    ENVOY_AS_INJECTOR,
    UNRESOLVED_ADDRESS_KEY,
    AddressSource,
    ClientAddressTrustError,
    DeviceCheckKeyComponentError,
    IdentitySource,
    KeyComponent,
    KeyMaterial,
    LimiterKeyError,
    LimiterLayer,
    assert_hops_match_chain,
    build_key,
    canonical_client_ip_key,
    client_address_from_forwarding_header,
    gateway_resolved_address,
    parse_key_policy,
    trusted_proxy_chain,
)
from nativespeaker.api.ratelimit.limiter import RateLimiter
from nativespeaker.api.ratelimit.rejection import (
    CREATE_USER_BACKEND_ARTIFACTS,
    GATEWAY_REGISTRATION_CLASS,
    GatewayRejectionError,
    assert_no_automatic_deletion,
    assert_saturation_tradeoff_accepted,
    backend_artifacts_after_gateway,
    gateway_registration_rejection,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def shipped() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def shipped_gateway() -> GatewayRateLimitsConfig:
    return GatewayRateLimitsConfig(**shipped()["gateway_rate_limits"])


def gateway_entry(**overrides) -> dict:
    data = {"route": CREATE_USER_GATEWAY_ROUTE, "limit": "10/minute", "key": "ip",
            "evaluate_after": "gateway_route_match"}
    data.update(overrides)
    return data


def gateway_config(**overrides) -> GatewayRateLimitsConfig:
    """The shipped gateway section with named entries replaced."""
    raw = dict(shipped()["gateway_rate_limits"])
    for name, changes in overrides.items():
        raw[name] = {**raw[name], **changes}
    return GatewayRateLimitsConfig(**raw)


def address(value: str, *,
            source: AddressSource = AddressSource.envoy_direct_downstream):
    return gateway_resolved_address(value, source=source)


def minimal(**overrides) -> dict:
    """The four required `rate_limits` keys, as the configuration file carries them."""
    data = {"enabled": True, "storage_uri": "memory://", "strategy": "moving-window",
            "default": {"limit": "120/minute", "key": "ip"}}
    data.update(overrides)
    return data


# --- The two required gateway ceilings ---------------------------------------------------------


# [utest->req~sessions-create-user-two-gateway-limits~1]
def test_two_gateway_limits_cover_both_phases_as_global_counters():
    gateway = shipped_gateway()
    assert CREATE_USER_GATEWAY_ENTRIES == ("create_user_ip", "create_user_deployment")
    for name in CREATE_USER_GATEWAY_ENTRIES:
        entry = getattr(gateway, name)
        assert entry.route == CREATE_USER_GATEWAY_ROUTE
        assert set(entry.phases) == set(GatewayPhase)
        assert entry.enforcement is GatewayCounterScope.global_rate_limit_service
    assert_create_user_gateway_limits(gateway)


# [utest->req~sessions-create-user-two-gateway-limits~1]
def test_a_per_envoy_pod_counter_and_a_single_phase_limit_are_both_refused():
    # A per-pod counter would multiply the ceiling by the replica count.
    with pytest.raises(ValidationError):
        GatewayRateLimitEntry(**gateway_entry(enforcement="per_envoy_pod"))
    # A limit covering only the prepare phase leaves completion unthrottled.
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(gateway_config(create_user_ip={"phases": ["prepare"]}))


# [utest->req~sessions-create-user-per-ip-limit~1]
def test_the_per_ip_ceiling_defaults_to_ten_a_minute_on_the_client_ip_key():
    entry = shipped_gateway().create_user_ip
    assert entry.limit == CREATE_USER_IP_DEFAULT_LIMIT == "10/minute"
    assert entry.per_window() == {"minute": 10}
    assert parse_key_policy(entry.key) == (KeyComponent.ip,)
    # The client IP is the address defined under Client-IP Rate-Limit Key, so the key policy
    # resolves through the canonical definition.
    material = KeyMaterial(client_address=address("198.51.100.7"))
    assert build_key(parse_key_policy(entry.key), material, layer=LimiterLayer.gateway) == \
        canonical_client_ip_key(material.client_address)
    # A per-IP entry that stops keying on the client address is refused.
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(gateway_config(create_user_ip={"key": "deployment"}))


# [utest->req~sessions-create-user-deployment-wide-limit~1]
def test_the_deployment_wide_ceiling_spans_every_source_address():
    entry = shipped_gateway().create_user_deployment
    assert entry.limit == CREATE_USER_DEPLOYMENT_DEFAULT_LIMIT == "100/minute; 2000/day"
    assert entry.per_window() == {"minute": 100, "day": 2000}
    assert parse_key_policy(entry.key) == (KeyComponent.deployment,)
    # A deployment-wide entry keyed on anything narrower than the deployment, or missing the
    # daily window, does not bound total creation.
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(gateway_config(create_user_deployment={"key": "ip"}))
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(
            gateway_config(create_user_deployment={"limit": "100/minute"}))


# [utest->req~sessions-create-user-limit-tuning-and-alert~1]
def test_both_ceilings_are_tunable_and_the_deployment_wide_one_alerts():
    # Tunable: a retuned pair validates, and nothing in code substitutes the shipped values.
    tuned = gateway_config(create_user_ip={"limit": "30/minute"},
                           create_user_deployment={"limit": "5000/minute; 100000/day"})
    assert_create_user_gateway_limits(tuned)
    assert tuned.create_user_ip.per_window() == {"minute": 30}
    # The deployment-wide ceiling must sit far above the single-address one: it, and not the
    # per-IP limit, is what bounds total account creation.
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(
            gateway_config(create_user_deployment={"limit": "20/minute; 2000/day"}))
    # Sustained saturation of that ceiling must raise an operational alert.
    assert shipped_gateway().create_user_deployment.saturation_alert is True
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(
            gateway_config(create_user_deployment={"saturation_alert": False}))


# [utest->req~sessions-create-user-limits-fail-closed~1]
def test_both_ceilings_fail_closed_with_one_identical_registration_rejection():
    for name in CREATE_USER_GATEWAY_ENTRIES:
        assert getattr(shipped_gateway(), name).failure_mode is FailureMode.fail_closed
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(
            gateway_config(create_user_ip={"failure_mode": "fail_open"}))
    per_ip = gateway_registration_rejection(retry_after_seconds=(42,), ceiling="create_user_ip")
    deployment = gateway_registration_rejection(retry_after_seconds=(42,),
                                                ceiling="create_user_deployment")
    # Identical and non-accusatory for both ceilings: same status, same body, same headers.
    assert per_ip == deployment
    assert per_ip.status == 429
    assert per_ip.body == {"code": ClientErrorClass.registration_temporarily_unavailable}
    assert per_ip.headers["Retry-After"] == "42"
    assert GATEWAY_REGISTRATION_CLASS is ClientErrorClass.registration_temporarily_unavailable
    # The response never identifies the exhausted bucket.
    disclosed = f"{per_ip.body}{per_ip.headers}"
    assert not [name for name in CREATE_USER_GATEWAY_ENTRIES if name in disclosed]
    with pytest.raises(GatewayRejectionError):
        gateway_registration_rejection(ceiling="some_other_bucket")


# [utest->req~sessions-rejected-request-never-reaches-backend~1]
def test_a_rejected_request_creates_no_row_and_triggers_no_firebase_lookup():
    assert backend_artifacts_after_gateway(admitted=False) == frozenset()
    for artifact in sorted(CREATE_USER_BACKEND_ARTIFACTS):
        with pytest.raises(GatewayRejectionError):
            backend_artifacts_after_gateway(admitted=False, artifacts=(artifact,))
    # Every insert and every Firebase Admin read is allowed only once the limits admitted it.
    assert backend_artifacts_after_gateway(
        admitted=True, artifacts=("core.users", "firebase_admin_lookup")) == frozenset(
            {"core.users", "firebase_admin_lookup"})
    assert {"core.auth_challenges", "core.users", "core.external_identities",
            "audit.auth_events", "firebase_admin_lookup"} == set(CREATE_USER_BACKEND_ARTIFACTS)


# [utest->req~sessions-create-user-saturation-tradeoff~1]
def test_a_saturated_ceiling_is_a_transient_wait_with_no_bypass():
    remediation = assert_saturation_tradeoff_accepted()
    assert remediation.transient and remediation.sends_retry_after
    assert not remediation.terminal
    # Registration is unavailable for the duration of the window, and the client is told to wait
    # rather than offered another route around the ceiling.
    assert remediation.next_route is None
    assert gateway_registration_rejection(retry_after_seconds=(60,)).headers == {"Retry-After": "60"}


# [utest->req~sessions-no-automatic-deletion-on-create-user-route~1]
def test_nothing_this_route_creates_is_deleted_on_a_schedule():
    assert_no_automatic_deletion()
    with pytest.raises(GatewayRejectionError):
        assert_no_automatic_deletion(("purge_expired_challenges",))
    with pytest.raises(GatewayRejectionError):
        assert_no_automatic_deletion(("delete_empty_anonymous_users",))


# [utest->req~sessions-client-ip-primary-key-on-create-user~1]
def test_the_client_ip_key_is_primary_and_no_fingerprint_keys_this_route():
    gateway = shipped_gateway()
    assert parse_key_policy(gateway.create_user_ip.key)[0] is KeyComponent.ip
    # The verified subject may only ever be a secondary key, never the sole one.
    with pytest.raises(RateLimitConfigError):
        assert_create_user_gateway_limits(
            gateway_config(create_user_ip={"key": "issuer+subject_hash",
                                           "evaluate_after": "envoy_jwt_verification"}))
    # No device fingerprint is a key component at all.
    for offered in ("device_fingerprint", "device_id", "devicecheck"):
        with pytest.raises(DeviceCheckKeyComponentError):
            parse_key_policy(offered)


# [utest->req~sessions-identity-keyed-limiter-from-verified-metadata~1]
def test_an_identity_keyed_gateway_limit_runs_only_after_jwt_verification():
    # An identity-keyed gateway entry evaluated at route match would key on unverified data.
    with pytest.raises(ValidationError):
        GatewayRateLimitEntry(**gateway_entry(key="issuer+subject_hash",
                                              evaluate_after="gateway_route_match"))
    verified = GatewayRateLimitEntry(**gateway_entry(key="issuer+subject_hash",
                                                     evaluate_after="envoy_jwt_verification"))
    assert verified.evaluate_after == "envoy_jwt_verification"
    # A client-IP-keyed limit needs no verified identity and may sit anywhere in the chain.
    assert GatewayRateLimitEntry(**gateway_entry()).evaluate_after == "gateway_route_match"
    # At the gateway, the identity material may come only from the JWT filter's own metadata.
    from_barrier = KeyMaterial(identity_source=IdentitySource.backend_barrier,
                               issuer="https://securetoken.google.com/p")
    with pytest.raises(LimiterKeyError):
        build_key((KeyComponent.issuer,), from_barrier, layer=LimiterLayer.gateway)
    from_filter = KeyMaterial(identity_source=IdentitySource.envoy_jwt_filter,
                              issuer="https://securetoken.google.com/p")
    assert build_key((KeyComponent.issuer,), from_filter, layer=LimiterLayer.gateway) == \
        "https://securetoken.google.com/p"


# --- The canonical client-IP key ---------------------------------------------------------------


# [utest->req~sessions-client-ip-trusted-proxy-chain~1]
def test_the_key_comes_from_an_explicitly_configured_trusted_proxy_chain():
    direct = trusted_proxy_chain(AddressSource.envoy_direct_downstream)
    behind_lb = trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                                    trusted_proxies=("203.0.113.10",),
                                    injector="cloud_load_balancer")
    assert direct.source is AddressSource.envoy_direct_downstream
    assert behind_lb.trusted_proxies == ("203.0.113.10",)
    # The unresolved bucket is an outcome, never a trust configuration to key from.
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.unresolved)
    # The shipped deployment's chain is validated at configuration load.
    assert ClientAddressConfig(**shipped()["rate_limits"]["client_address"]).chain == direct


# [utest->req~sessions-client-ip-direct-downstream~1]
def test_a_direct_terminating_listener_keys_on_the_downstream_socket_only():
    direct = trusted_proxy_chain(AddressSource.envoy_direct_downstream)
    assert direct.xff_num_trusted_hops == 0
    assert direct.trusted_proxies == ()
    # No forwarded address is trusted there: naming trusted proxies contradicts the source, and a
    # forwarding header cannot supply the key.
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.envoy_direct_downstream,
                            trusted_proxies=("203.0.113.10",), injector="cloud_load_balancer")
    with pytest.raises(ClientAddressTrustError):
        client_address_from_forwarding_header(
            "X-Forwarded-For", "198.51.100.9",
            source=AddressSource.envoy_direct_downstream)
    resolved = gateway_resolved_address("198.51.100.9",
                                        source=AddressSource.envoy_direct_downstream)
    assert canonical_client_ip_key(resolved) == canonical_client_ip_key(address("198.51.100.9"))


# [utest->req~sessions-client-ip-xff-trusted-hops~1]
def test_xff_num_trusted_hops_is_pinned_to_the_actual_chain():
    single = trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                                 trusted_proxies=("203.0.113.10",),
                                 injector="cloud_load_balancer")
    assert single.xff_num_trusted_hops == 1
    assert_hops_match_chain(single, xff_num_trusted_hops=1)
    # A count that does not match the chain trusts a hop the client can add, or keys on the
    # load balancer instead of the client.
    for wrong in (0, 2):
        with pytest.raises(ClientAddressTrustError):
            assert_hops_match_chain(single, xff_num_trusted_hops=wrong)
    two = trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                              trusted_proxies=("203.0.113.10", "203.0.113.11"),
                              injector="cdn_then_cloud_load_balancer")
    assert two.xff_num_trusted_hops == 2
    # Only the configured load-balancer addresses or proxy identities may connect: a proxied
    # listener that names none is refused.
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                            injector="cloud_load_balancer")


# [utest->req~sessions-client-ip-outermost-hop-overwrites~1]
def test_the_outermost_trusted_hop_overwrites_inbound_forwarding_headers():
    assert trusted_proxy_chain(
        AddressSource.envoy_direct_downstream).overwrite_inbound_forwarding_headers is True
    # An appending outermost hop would let a client's own inbound header survive, on either
    # kind of listener.
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.envoy_direct_downstream,
                            overwrite_inbound_forwarding_headers=False)
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                            trusted_proxies=("203.0.113.10",),
                            injector="cloud_load_balancer",
                            overwrite_inbound_forwarding_headers=False)
    with pytest.raises(ValidationError):
        ClientAddressConfig(overwrite_inbound_forwarding_headers=False)


# [utest->req~sessions-client-ip-forwarding-headers-untrusted~1]
def test_no_client_forwarding_header_supplies_the_key_unless_envoy_validated_it():
    assert CLIENT_FORWARDING_HEADERS == {"x-forwarded-for", "forwarded", "x-real-ip",
                                         "true-client-ip", "cf-connecting-ip"}
    for header in sorted(CLIENT_FORWARDING_HEADERS):
        for source in (AddressSource.envoy_direct_downstream, AddressSource.unresolved):
            with pytest.raises(ClientAddressTrustError):
                client_address_from_forwarding_header(header.title(), "198.51.100.9",
                                                      source=source)
        # Only Envoy's own trusted-hop calculation makes the value usable.
        resolved = client_address_from_forwarding_header(
            header, "198.51.100.9", source=AddressSource.envoy_trusted_hop_chain)
        assert resolved.address == "198.51.100.9"


# [utest->req~sessions-client-ip-normalized-binary~1]
def test_the_resolved_address_is_normalized_to_binary_before_descriptors_are_built():
    # The descriptor carries the packed binary form, not the text the gateway resolved.
    assert canonical_client_ip_key(address("198.51.100.7")) == "v4/32:c6336407"
    assert canonical_client_ip_key(address("2001:db8::1")) == \
        "v6/64:20010db8000000000000000000000000"
    # An IPv4-mapped IPv6 address is treated as IPv4, so both spellings key identically.
    assert canonical_client_ip_key(address("::ffff:198.51.100.7")) == \
        canonical_client_ip_key(address("198.51.100.7"))
    with pytest.raises(LimiterKeyError):
        canonical_client_ip_key(address("not-an-address"))


# [utest->req~sessions-client-ip-deployment-documents-injector~1]
def test_the_deployment_documents_the_injector_and_the_hops_match_it():
    behind_lb = trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                                    trusted_proxies=("203.0.113.10",),
                                    injector="cloud_load_balancer")
    assert behind_lb.injector == "cloud_load_balancer"
    # A proxied deployment that documents no injector, or claims Envoy itself injects while a
    # proxy sits in front, is a configuration error.
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                            trusted_proxies=("203.0.113.10",))
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.envoy_trusted_hop_chain,
                            trusted_proxies=("203.0.113.10",), injector=ENVOY_AS_INJECTOR)
    # A direct-terminating listener's injector is Envoy itself and nothing else.
    assert trusted_proxy_chain(AddressSource.envoy_direct_downstream).injector == ENVOY_AS_INJECTOR
    with pytest.raises(ClientAddressTrustError):
        trusted_proxy_chain(AddressSource.envoy_direct_downstream, injector="cloud_load_balancer")
    with pytest.raises(ValidationError):
        ClientAddressConfig(injector="cloud_load_balancer")


# [utest->req~sessions-client-ip-canonical-definition~1]
def test_one_canonical_definition_serves_every_ip_keyed_limiter():
    material = KeyMaterial(client_address=address("198.51.100.7"))
    canonical = canonical_client_ip_key(material.client_address)
    # Gateway-layer and backend-layer IP keys are the same value from the same definition.
    assert build_key((KeyComponent.ip,), material, layer=LimiterLayer.gateway) == canonical
    assert build_key((KeyComponent.ip,), material, layer=LimiterLayer.backend) == canonical
    assert RateLimiter(RateLimitsConfig(**minimal())).client_ip_key(
        material.client_address) == canonical
    # A backend service cannot recalculate the address out of a raw forwarded header.
    with pytest.raises(ClientAddressTrustError):
        client_address_from_forwarding_header("x-real-ip", "198.51.100.7",
                                              source=AddressSource.envoy_direct_downstream)


# [utest->req~sessions-client-ip-unresolved-bucket~1]
def test_an_unresolvable_address_enters_one_shared_bucket_at_the_single_address_ceiling():
    unresolved = gateway_resolved_address("198.51.100.7", source=AddressSource.unresolved)
    # A client-supplied address is never the fallback: the offered value is discarded.
    assert unresolved.address is None
    assert canonical_client_ip_key(unresolved) == UNRESOLVED_ADDRESS_KEY
    assert canonical_client_ip_key(None) == UNRESOLVED_ADDRESS_KEY
    limiter = RateLimiter(RateLimitsConfig(**minimal()))
    # One bucket, at the same default ceiling as a single address, and never unlimited.
    assert limiter.unresolved_address_ceiling().limit == "10/minute"
    assert limiter.client_ip_key(unresolved) == limiter.client_ip_key(None)


# [utest->req~sessions-client-ip-ipv4-full-address~1]
def test_ipv4_keys_on_the_full_address():
    neighbour = canonical_client_ip_key(address("198.51.100.8"))
    assert canonical_client_ip_key(address("198.51.100.7")) != neighbour
    assert canonical_client_ip_key(address("198.51.100.7")).startswith("v4/32:")
    # The same address always lands in the same bucket, NAT sharing included.
    assert canonical_client_ip_key(address("198.51.100.7")) == \
        canonical_client_ip_key(address("198.51.100.7"))


# [utest->req~sessions-client-ip-ipv6-prefix-bucket~1]
def test_ipv6_buckets_by_the_configured_prefix():
    inside = address("2001:db8:1:2::5")
    sibling = address("2001:db8:1:2:ffff::9")
    other = address("2001:db8:1:3::5")
    # Rotation inside one /64 lands in one bucket; a different /64 does not.
    assert canonical_client_ip_key(inside) == canonical_client_ip_key(sibling)
    assert canonical_client_ip_key(inside) != canonical_client_ip_key(other)
    # Operator-configurable, and only to /56 or /48.
    assert canonical_client_ip_key(inside, ipv6_prefix=48) == \
        canonical_client_ip_key(other, ipv6_prefix=48)
    assert canonical_client_ip_key(inside, ipv6_prefix=56) == \
        canonical_client_ip_key(other, ipv6_prefix=56)
    with pytest.raises(LimiterKeyError):
        canonical_client_ip_key(inside, ipv6_prefix=32)
    with pytest.raises(ValidationError):
        ClientAddressConfig(ipv6_prefix=32)
    assert ClientAddressConfig().ipv6_prefix == 64
