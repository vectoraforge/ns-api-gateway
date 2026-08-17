"""Key safety and canonical client-address resolution."""

from uuid import uuid4

import pytest

from nativespeaker.api.ratelimit.keys import (
    CLIENT_FORWARDING_HEADERS,
    UNRESOLVED_ADDRESS_KEY,
    AddressSource,
    DerivedIdentifier,
    DeviceCheckKeyComponentError,
    IdentitySource,
    KeyComponent,
    KeyMaterial,
    LimiterKeyError,
    LimiterLayer,
    build_key,
    canonical_client_ip_key,
    gateway_resolved_address,
    parse_key_policy,
)

DIGEST = bytes(range(32))
OTHER_DIGEST = bytes(range(32, 64))


def derived(digest: bytes = DIGEST, version: int = 1) -> DerivedIdentifier:
    return DerivedIdentifier(digest=digest, key_version=version)


def direct(address: str):
    return gateway_resolved_address(address, source=AddressSource.envoy_direct_downstream)


# --- Verified values only ---------------------------------------------------------------------

# [utest->req~ratelimit-keys-from-verified-values-only~1]
@pytest.mark.parametrize("raw", ["raw_id_token", "jwt", "purchase_token", "restore_proof",
                                 "provider_response", "email", "apple_receipt"])
def test_raw_material_can_never_name_itself_into_a_key(raw):
    with pytest.raises(LimiterKeyError, match="no declared rate-limit key component"):
        parse_key_policy(raw)


# [utest->req~ratelimit-keys-from-verified-values-only~1]
def test_key_material_carries_no_raw_field_at_all():
    fields = set(KeyMaterial.__dataclass_fields__)
    assert not any("raw" in name or "token" in name or "payload" in name or "proof_blob" in name
                   for name in fields)
    # Every key is assembled from verified or server-derived values.
    material = KeyMaterial(identity_source=IdentitySource.backend_barrier,
                           issuer="https://securetoken.google.com/p",
                           subject_hash=derived())
    key = build_key(parse_key_policy("issuer+subject_hash"), material)
    assert key == f"https://securetoken.google.com/p|{DIGEST.hex()}.v1"


# --- The canonical client address ----------------------------------------------------------------

# [utest->req~ratelimit-canonical-client-ip-resolution~2]
def test_ipv4_keys_on_the_full_address_in_binary_form():
    assert canonical_client_ip_key(direct("203.0.113.7")) == f"v4/32:{bytes([203,0,113,7]).hex()}"
    # The same address, written differently, is the same key.
    assert canonical_client_ip_key(direct("203.0.113.7")) != canonical_client_ip_key(
        direct("203.0.113.8"))


# [utest->req~ratelimit-canonical-client-ip-resolution~2]
def test_an_ipv4_mapped_ipv6_address_is_treated_as_ipv4():
    assert canonical_client_ip_key(direct("::ffff:203.0.113.7")) == canonical_client_ip_key(
        direct("203.0.113.7"))


# [utest->req~ratelimit-canonical-client-ip-resolution~2]
def test_ipv6_keys_on_the_configured_prefix():
    a = "2001:db8:1:2:3:4:5:6"
    b = "2001:db8:1:2:ffff:ffff:ffff:ffff"
    c = "2001:db8:1:3::1"
    assert canonical_client_ip_key(direct(a)) == canonical_client_ip_key(direct(b))
    assert canonical_client_ip_key(direct(a)) != canonical_client_ip_key(direct(c))
    # Operator-configurable to /56 or /48, where the two now share a bucket.
    assert canonical_client_ip_key(direct(a), ipv6_prefix=48) == canonical_client_ip_key(
        direct(c), ipv6_prefix=48)
    with pytest.raises(LimiterKeyError, match="no permitted IPv6 aggregation prefix"):
        canonical_client_ip_key(direct(a), ipv6_prefix=32)


# [utest->req~ratelimit-canonical-client-ip-resolution~2]
def test_an_unresolved_address_enters_one_shared_bucket_and_never_the_client_value():
    unresolved = gateway_resolved_address("198.51.100.9", source=AddressSource.unresolved)
    assert unresolved.address is None
    assert canonical_client_ip_key(unresolved) == UNRESOLVED_ADDRESS_KEY
    assert canonical_client_ip_key(None) == UNRESOLVED_ADDRESS_KEY


# [utest->req~ratelimit-canonical-client-ip-resolution~2]
def test_the_backend_never_recalculates_the_address_from_a_forwarding_header():
    # There is no address source naming a client- or proxy-supplied header, so no call can build
    # the key from one.
    sources = {str(source) for source in AddressSource}
    assert not (sources & CLIENT_FORWARDING_HEADERS)
    assert CLIENT_FORWARDING_HEADERS == {"x-forwarded-for", "forwarded", "x-real-ip",
                                         "true-client-ip", "cf-connecting-ip"}
    with pytest.raises(LimiterKeyError, match="supplied no address"):
        gateway_resolved_address(None, source=AddressSource.envoy_trusted_hop_chain)


# --- Identity keys come from the evaluating layer -------------------------------------------------

# [utest->req~ratelimit-identity-keys-from-evaluating-layer~1]
def test_a_backend_identity_key_needs_barrier_established_material():
    from_envoy = KeyMaterial(identity_source=IdentitySource.envoy_jwt_filter,
                             issuer="iss", subject_hash=derived())
    with pytest.raises(LimiterKeyError, match="backend may key on"):
        build_key((KeyComponent.issuer,), from_envoy, layer=LimiterLayer.backend)
    from_barrier = KeyMaterial(identity_source=IdentitySource.backend_barrier,
                               issuer="iss", subject_hash=derived())
    assert build_key((KeyComponent.issuer,), from_barrier, layer=LimiterLayer.backend) == "iss"
    # And a gateway limiter takes only Envoy's own JWT-filter-verified metadata.
    with pytest.raises(LimiterKeyError, match="gateway may key on"):
        build_key((KeyComponent.issuer,), from_barrier, layer=LimiterLayer.gateway)


# [utest->req~ratelimit-identity-keys-from-evaluating-layer~1]
def test_unverified_identity_material_never_builds_a_key():
    unverified = KeyMaterial(issuer="iss", subject_hash=derived(), user_id=uuid4(),
                             barrier_admitted=True)
    for policy in ("issuer", "subject_hash", "user"):
        with pytest.raises(LimiterKeyError):
            build_key(parse_key_policy(policy), unverified)


# [utest->req~ratelimit-identity-keys-from-evaluating-layer~1]
def test_a_pre_auth_route_exposes_the_verified_subject_but_has_no_user_key():
    pre_auth = KeyMaterial(identity_source=IdentitySource.backend_barrier,
                           issuer="iss", subject_hash=derived())
    assert build_key((KeyComponent.subject_hash,), pre_auth) == f"{DIGEST.hex()}.v1"
    with pytest.raises(LimiterKeyError, match="linked active user"):
        build_key((KeyComponent.user,), pre_auth)


# --- Derived identifiers --------------------------------------------------------------------------

# [utest->req~ratelimit-proof-correlation-key-fingerprints~1]
def test_a_proof_correlation_key_is_a_server_derived_fingerprint():
    material = KeyMaterial(restore_proof_fingerprint=derived(version=3))
    assert build_key((KeyComponent.restore_proof_fingerprint,), material) == f"{DIGEST.hex()}.v3"
    # A raw proof string is not a derived identifier and cannot be supplied.
    with pytest.raises(LimiterKeyError, match="32-byte HMAC digest"):
        DerivedIdentifier(digest=b"raw-restore-proof", key_version=1)
    with pytest.raises(LimiterKeyError, match="names the key version"):
        DerivedIdentifier(digest=DIGEST, key_version=0)


# [utest->req~ratelimit-provider-account-key-component~1]
def test_the_idp_account_component_is_the_stored_redacted_identifier():
    material = KeyMaterial(identity_source=IdentitySource.backend_barrier,
                           user_id=uuid4(), barrier_admitted=True,
                           idp_account_hash=derived(OTHER_DIGEST, 2))
    key = build_key(parse_key_policy("user+idp_account_hash"), material)
    assert key.endswith(f"{OTHER_DIGEST.hex()}.v2")
    # A raw provider identifier, an email address or a display name has no representation here.
    for bad in ("google-oauth2|1234", "user@example.com", "Ada Lovelace"):
        with pytest.raises(LimiterKeyError, match="32-byte HMAC digest"):
            DerivedIdentifier(digest=bad, key_version=1)  # type: ignore[arg-type]
    missing = KeyMaterial(identity_source=IdentitySource.backend_barrier,
                          user_id=uuid4(), barrier_admitted=True)
    with pytest.raises(LimiterKeyError, match="no verified value available"):
        build_key(parse_key_policy("user+idp_account_hash"), missing)


# --- No device-check key component ------------------------------------------------------------------

# [utest->req~ratelimit-no-device-check-key-component~1]
@pytest.mark.parametrize("component", [
    "device_check", "devicecheck", "device_check_hash", "app_attest", "attest_key",
    "play_integrity", "play_integrity_verdict", "device_recall", "device_recall_write_token",
    "device_bit", "device_fingerprint", "device_principal", "device_id", "bot_check",
    "turnstile_token"])
def test_device_check_material_is_never_a_key_component(component):
    with pytest.raises(DeviceCheckKeyComponentError):
        parse_key_policy(component)
    with pytest.raises(DeviceCheckKeyComponentError):
        parse_key_policy(f"user+{component}")


# [utest->req~ratelimit-no-device-check-key-component~1]
def test_no_declared_component_is_device_check_material():
    for component in KeyComponent:
        parse_key_policy(str(component))
