"""Rate-limit key policies, key safety, and canonical client-address resolution.

A limiter key is never a raw value. It is assembled from a closed set of named components, each
of which is supplied by the layer that already verified or derived it: the gateway's Envoy JWT
filter, the backend's shared authentication-and-identity-resolution barrier, or a server-side
derivation. There is no field on this module's material for raw token, proof, purchase-token,
attestation, verdict or provider-response bytes, so no assembly path can carry one into a key.
"""

import ipaddress
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

# The derived-identifier shape the audit contract already allows: an HMAC digest plus the
# version of the key that produced it.
DERIVED_DIGEST_BYTES = 32


class LimiterKeyError(RuntimeError):
    """A limiter key was about to be built from material the key-safety rules forbid, or from
    material the evaluating layer has not established."""


class DeviceCheckKeyComponentError(LimiterKeyError):
    """Device-check correlation material was offered as a limiter key component."""


class KeyComponent(StrEnum):
    """The closed set of limiter key components. A configured key policy is a `+`-joined list of
    these names and nothing else; anything outside this enumeration is rejected, so a raw JWT,
    restore proof, purchase token, provider account identifier, attestation blob, Play Integrity
    verdict, DeviceCheck payload or provider response can never name itself into a key."""
    # [impl->req~ratelimit-keys-from-verified-values-only~1]
    ip = "ip"
    user = "user"
    deployment = "deployment"
    issuer = "issuer"
    subject_hash = "subject_hash"
    firebase_project_id = "firebase_project_id"
    package_name = "package_name"
    apple_team_id = "apple_team_id"
    bundle_id = "bundle_id"
    idp_account_hash = "idp_account_hash"
    provider = "provider"
    external_id = "external_id"
    restore_proof_fingerprint = "restore_proof_fingerprint"


# Components whose value is identity material and may therefore be used only by the layer that
# established it.
IDENTITY_COMPONENTS: frozenset[KeyComponent] = frozenset({
    KeyComponent.issuer,
    KeyComponent.subject_hash,
    KeyComponent.user,
})

# Components that must arrive in the redacted or HMAC-derived form the audit contract allows,
# never as a raw provider or proof value.
DERIVED_COMPONENTS: frozenset[KeyComponent] = frozenset({
    KeyComponent.subject_hash,
    KeyComponent.idp_account_hash,
    KeyComponent.restore_proof_fingerprint,
    KeyComponent.external_id,
})

# Device-check correlation material, in every form it could be offered: the raw payload, the
# verdict, the provider response, and any redacted, hashed, transaction-scoped, install-scoped
# or otherwise server-derived value of one, including a synthetic stable device principal.
# [impl->req~ratelimit-no-device-check-key-component~1]
_DEVICE_CHECK_PATTERN = re.compile(
    r"device[_-]?check|app[_-]?attest|attest|play[_-]?integrity|integrity[_-]?verdict"
    r"|device[_-]?recall|recall|device[_-]?bit|device[_-]?fingerprint|device[_-]?principal"
    r"|device[_-]?id|device[_-]?token|bot[_-]?check|turnstile[_-]?token", re.IGNORECASE)


def _reject_device_check(name: str) -> None:
    """DeviceCheck, App Attest, Play Integrity, Device Recall and bot-check material is a
    pass/fail proof gate evaluated elsewhere in the flow, never a keying dimension. A device
    fingerprint is no key component on any route, `POST /auth/create-user` included."""
    # [impl->req~ratelimit-no-device-check-key-component~1]
    # [impl->req~sessions-client-ip-primary-key-on-create-user~1]
    if _DEVICE_CHECK_PATTERN.search(name):
        raise DeviceCheckKeyComponentError(
            f"{name!r} is device-check correlation material and is never a rate-limit key component")


def parse_key_policy(raw: str) -> tuple[KeyComponent, ...]:
    """Parse a configured key policy such as `ip` or `deployment+firebase_project_id`."""
    # [impl->req~ratelimit-entry-key-policy~1]
    # [impl->req~ratelimit-keys-from-verified-values-only~1]
    if not raw or not raw.strip():
        raise LimiterKeyError("a limit entry defines no key policy")
    components: list[KeyComponent] = []
    for part in raw.split("+"):
        name = part.strip()
        _reject_device_check(name)
        if name not in set(KeyComponent):
            raise LimiterKeyError(f"{name!r} is no declared rate-limit key component")
        component = KeyComponent(name)
        if component in components:
            raise LimiterKeyError(f"{name!r} appears twice in key policy {raw!r}")
        components.append(component)
    return tuple(components)


# --- The canonical client address ------------------------------------------------------------


class AddressSource(StrEnum):
    """How Envoy arrived at the address the backend consumes. There is no source naming a raw
    forwarding header, because the backend never recalculates the address from one."""
    # The client-IP key is the source address Envoy resolves through an explicitly configured
    # trusted-proxy chain — one of these two sources — and never a client-supplied forwarding
    # header, for which this enumeration has no member at all.
    # [impl->req~sessions-client-ip-trusted-proxy-chain~1]
    envoy_direct_downstream = "envoy_direct_downstream"
    envoy_trusted_hop_chain = "envoy_trusted_hop_chain"
    unresolved = "unresolved"


# The headers a client or an untrusted proxy can set. None of them ever supplies a limiter key
# unless Envoy itself set or validated the value through its own trusted-hop calculation, which
# this module models as `AddressSource.envoy_trusted_hop_chain`.
# [impl->req~sessions-client-ip-forwarding-headers-untrusted~1]
CLIENT_FORWARDING_HEADERS: frozenset[str] = frozenset({
    "x-forwarded-for", "forwarded", "x-real-ip", "true-client-ip", "cf-connecting-ip"})


# The single shared bucket every request with no trusted address enters, at the single-address
# ceiling. Its limit is configuration-tunable; the route is never left unlimited.
UNRESOLVED_ADDRESS_KEY = "unresolved-client-address"
DEFAULT_UNRESOLVED_ADDRESS_LIMIT = "10/minute"

# The operator-configurable IPv6 aggregation prefixes.
ALLOWED_IPV6_PREFIXES: frozenset[int] = frozenset({64, 56, 48})
DEFAULT_IPV6_PREFIX = 64


@dataclass(frozen=True, slots=True)
class GatewayResolvedAddress:
    """The one canonical client address, as resolved by Envoy. Backend services consume this and
    only this."""
    source: AddressSource
    address: str | None = None


def gateway_resolved_address(address: str | None, *,
                             source: AddressSource) -> GatewayResolvedAddress:
    """Accept the gateway's resolved address. When Envoy could not determine a trusted address
    the value is discarded outright: a client-supplied address is never the fallback.

    Where Envoy terminates client connections directly the address is the direct downstream
    socket address, and no forwarded address is trusted alongside it."""
    # [impl->req~ratelimit-canonical-client-ip-resolution~2]
    # [impl->req~sessions-client-ip-direct-downstream~1]
    if source is AddressSource.unresolved:
        # Missing, malformed or unexpectedly structured proxy metadata leaves no trusted
        # address, and whatever the client offered is dropped with it.
        # [impl->req~sessions-client-ip-unresolved-bucket~1]
        return GatewayResolvedAddress(source=source, address=None)
    if not address:
        raise LimiterKeyError(f"{source} supplied no address")
    return GatewayResolvedAddress(source=source, address=address)


def canonical_client_ip_key(resolved: GatewayResolvedAddress | None,
                            *,
                            ipv6_prefix: int = DEFAULT_IPV6_PREFIX) -> str:
    """The canonical client-IP limiter key.

    This is the one canonical client-address definition: every IP-keyed limiter, at the gateway
    and at the backend, resolves its key here, and no backend service recalculates the address
    from raw forwarded headers.

    The resolved address is normalized to its binary form, with an IPv4-mapped IPv6 address
    treated as IPv4. IPv4 keys on the full address; IPv6 keys on the configured prefix. A
    request Envoy could not resolve enters the one shared unresolved-address bucket.
    """
    # [impl->req~ratelimit-canonical-client-ip-resolution~2]
    # [impl->req~sessions-client-ip-canonical-definition~1]
    if resolved is None or resolved.source is AddressSource.unresolved or not resolved.address:
        # One shared bucket for every unresolved request, at the single-address ceiling: the
        # route is never left unlimited and no client-supplied address stands in.
        # [impl->req~sessions-client-ip-unresolved-bucket~1]
        return UNRESOLVED_ADDRESS_KEY
    # The prefix length is operator-configurable, defaulting to /64 and tightened to /56 or /48
    # only if abuse appears.
    # [impl->req~sessions-client-ip-ipv6-prefix-bucket~1]
    if ipv6_prefix not in ALLOWED_IPV6_PREFIXES:
        raise LimiterKeyError(f"/{ipv6_prefix} is no permitted IPv6 aggregation prefix")
    # The address is normalized to a binary IPv4 or IPv6 address before any descriptor is
    # constructed, with IPv4-mapped IPv6 treated as IPv4.
    # [impl->req~sessions-client-ip-normalized-binary~1]
    try:
        address = ipaddress.ip_address(resolved.address)
    except ValueError as exc:
        raise LimiterKeyError(f"{resolved.address!r} is no IP address") from exc
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if isinstance(address, ipaddress.IPv4Address):
        # IPv4 keys on the full address; shared fate behind NAT or CGNAT is accepted, which is
        # why the per-IP ceiling is required to be loose.
        # [impl->req~sessions-client-ip-ipv4-full-address~1]
        return f"v4/32:{address.packed.hex()}"
    # IPv6 buckets by the configured prefix of the resolved trusted address rather than by the
    # full address, so rotation inside one allocation lands in one bucket.
    # [impl->req~sessions-client-ip-ipv6-prefix-bucket~1]
    network = ipaddress.IPv6Network(f"{address}/{ipv6_prefix}", strict=False)
    return f"v6/{ipv6_prefix}:{network.network_address.packed.hex()}"


class ClientAddressTrustError(LimiterKeyError):
    """The configured client-address trust chain does not describe a deployment that can resolve
    a trustworthy client address: the hop count does not match the actual chain, the component
    that injects the true client address is undocumented, the listener accepts connections from
    something other than the configured proxies, or an inbound forwarding header would be
    appended to rather than overwritten."""


@dataclass(frozen=True, slots=True)
class TrustedProxyChain:
    """The explicitly configured trusted-proxy chain the client-IP key is resolved through.

    `trusted_proxies` are the load-balancer addresses or authenticated proxy identities that may
    connect to the gateway listener, and they are the whole of the trusted chain:
    `xff_num_trusted_hops` equals their number.
    """
    source: AddressSource
    xff_num_trusted_hops: int
    injector: str
    trusted_proxies: tuple[str, ...] = ()
    overwrite_inbound_forwarding_headers: bool = True


# Where Envoy terminates client connections directly, Envoy itself is the component that
# establishes the true client address.
ENVOY_AS_INJECTOR = "envoy_direct_downstream_socket"


def trusted_proxy_chain(source: AddressSource,
                        *,
                        trusted_proxies: Sequence[str] = (),
                        injector: str | None = None,
                        overwrite_inbound_forwarding_headers: bool = True) -> TrustedProxyChain:
    """Validate one deployment's client-address trust configuration and return it.

    A direct-terminating listener trusts no forwarded address at all: zero trusted hops, and the
    downstream socket address is the key. A listener behind proxies pins `xff_num_trusted_hops`
    to exactly the number of trusted proxies — typically 1 for a single cloud load balancer —
    and only those configured addresses or authenticated proxy identities may connect to it.
    Either way the outermost trusted hop overwrites inbound forwarding headers rather than
    appending to them, and the deployment names the component that injects the true client
    address so the hop configuration can be checked against it.
    """
    # [impl->req~sessions-client-ip-trusted-proxy-chain~1]
    if source is AddressSource.unresolved:
        raise ClientAddressTrustError("the unresolved bucket is no trust configuration")
    proxies = tuple(trusted_proxies)
    # An appending outermost hop would let a client's own inbound header survive into the
    # calculation, so the configuration is refused rather than trusted.
    # [impl->req~sessions-client-ip-outermost-hop-overwrites~1]
    if not overwrite_inbound_forwarding_headers:
        raise ClientAddressTrustError(
            "the outermost trusted hop overwrites inbound forwarding headers")
    if source is AddressSource.envoy_direct_downstream:
        # No forwarded address is trusted where Envoy terminates the client connection itself.
        # [impl->req~sessions-client-ip-direct-downstream~1]
        if proxies:
            raise ClientAddressTrustError(
                "a direct-terminating listener trusts no forwarded address")
        documented = injector or ENVOY_AS_INJECTOR
        # [impl->req~sessions-client-ip-deployment-documents-injector~1]
        if documented != ENVOY_AS_INJECTOR:
            raise ClientAddressTrustError(
                f"{documented} injects no address on a direct-terminating listener")
        return TrustedProxyChain(source=source, xff_num_trusted_hops=0, injector=documented)
    # The trust configuration is pinned to the actual chain, and the listener accepts nobody
    # else: an unlisted caller could otherwise present its own hop.
    # [impl->req~sessions-client-ip-xff-trusted-hops~1]
    if not proxies:
        raise ClientAddressTrustError(
            "a proxied listener names the load-balancer addresses or proxy identities it accepts")
    # The deployment must document which component injects the true client address, and the hop
    # configuration must match that component.
    # [impl->req~sessions-client-ip-deployment-documents-injector~1]
    if not injector or injector == ENVOY_AS_INJECTOR:
        raise ClientAddressTrustError(
            "a proxied deployment documents the component that injects the client address")
    return TrustedProxyChain(source=source,
                             xff_num_trusted_hops=len(proxies),
                             injector=injector,
                             trusted_proxies=proxies)


def assert_hops_match_chain(chain: TrustedProxyChain, *, xff_num_trusted_hops: int) -> None:
    """`xff_num_trusted_hops` is pinned to exactly the number of trusted proxies. A larger value
    would trust a hop the client can add; a smaller one would key on the load balancer."""
    # [impl->req~sessions-client-ip-xff-trusted-hops~1]
    if xff_num_trusted_hops != chain.xff_num_trusted_hops:
        raise ClientAddressTrustError(
            f"xff_num_trusted_hops is {chain.xff_num_trusted_hops} for this chain, "
            f"not {xff_num_trusted_hops}")


def client_address_from_forwarding_header(name: str, value: str, *,
                                          source: AddressSource) -> GatewayResolvedAddress:
    """A forwarding header's value becomes the client-IP key only where Envoy itself set or
    validated it through the trusted-hop calculation. `X-Forwarded-For`, `Forwarded`,
    `X-Real-IP`, `True-Client-IP` and `CF-Connecting-IP` are otherwise refused outright — the
    request keys into the unresolved bucket instead, because a client-supplied address is never
    the fallback."""
    # [impl->req~sessions-client-ip-forwarding-headers-untrusted~1]
    if (name.strip().lower() in CLIENT_FORWARDING_HEADERS
            and source is not AddressSource.envoy_trusted_hop_chain):
        raise ClientAddressTrustError(
            f"{name} is client-supplied here and never supplies the client-IP key")
    return gateway_resolved_address(value, source=source)

# --- Verified key material ---------------------------------------------------------------


class LimiterLayer(StrEnum):
    """The layer evaluating a limiter."""
    gateway = "gateway"
    backend = "backend"


class IdentitySource(StrEnum):
    """Where identity material for a limiter key was established."""
    envoy_jwt_filter = "envoy_jwt_filter"
    backend_barrier = "backend_barrier"


# Each layer accepts identity material established by itself and by nothing else.
# [impl->req~ratelimit-identity-keys-from-evaluating-layer~1]
LAYER_IDENTITY_SOURCE: dict[LimiterLayer, IdentitySource] = {
    LimiterLayer.gateway: IdentitySource.envoy_jwt_filter,
    LimiterLayer.backend: IdentitySource.backend_barrier,
}


@dataclass(frozen=True, slots=True)
class DerivedIdentifier:
    """A redacted server-derived fingerprint or HMAC-derived identifier — the same form the
    audit contract allows — carrying the version of the key that produced it."""
    # [impl->req~ratelimit-proof-correlation-key-fingerprints~1]
    # [impl->req~ratelimit-provider-account-key-component~1]
    digest: bytes
    key_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.digest, bytes) or len(self.digest) != DERIVED_DIGEST_BYTES:
            raise LimiterKeyError("a derived key component is a 32-byte HMAC digest")
        if self.key_version < 1:
            raise LimiterKeyError("a derived key component names the key version that made it")

    @property
    def key(self) -> str:
        return f"{self.digest.hex()}.v{self.key_version}"


@dataclass(frozen=True, slots=True)
class KeyMaterial:
    """Everything a limiter key may be built from. Every field is already verified by the
    evaluating layer or derived server-side; there is no field for raw material of any kind.

    `barrier_admitted` records that the backend barrier resolved and admitted a linked active
    user, which is what makes `user_id` usable as a key.
    """
    # [impl->req~ratelimit-keys-from-verified-values-only~1]
    client_address: GatewayResolvedAddress | None = None
    ipv6_prefix: int = DEFAULT_IPV6_PREFIX
    identity_source: IdentitySource | None = None
    issuer: str | None = None
    subject_hash: DerivedIdentifier | None = None
    user_id: UUID | None = None
    barrier_admitted: bool = False
    deployment: str | None = None
    firebase_project_id: str | None = None
    package_name: str | None = None
    apple_team_id: str | None = None
    bundle_id: str | None = None
    provider: str | None = None
    external_id: DerivedIdentifier | None = None
    idp_account_hash: DerivedIdentifier | None = None
    restore_proof_fingerprint: DerivedIdentifier | None = None


def _component_value(component: KeyComponent,
                     material: KeyMaterial,
                     layer: LimiterLayer) -> str:
    if component in IDENTITY_COMPONENTS:
        expected = LAYER_IDENTITY_SOURCE[layer]
        if material.identity_source is not expected:
            # At the gateway, identity comes from Envoy's own JWT-filter-verified token
            # metadata; at the backend, from the shared barrier. Never from a client- or
            # proxy-supplied header, an unverified decoded claim, a cookie, or a body field.
            # A gateway limiter keyed on `issuer+subject_hash` therefore cannot be evaluated
            # before the JWT filter has verified the request's token for that route.
            # [impl->req~ratelimit-identity-keys-from-evaluating-layer~1]
            # [impl->req~sessions-identity-keyed-limiter-from-verified-metadata~1]
            raise LimiterKeyError(
                f"{layer} may key on {component} only from {expected}")
    match component:
        case KeyComponent.ip:
            # Every IP-keyed limiter takes its key from the one canonical definition, and an
            # IP-keyed limit needs no verified identity to do it.
            # [impl->req~sessions-client-ip-canonical-definition~1]
            # [impl->req~sessions-identity-keyed-limiter-from-verified-metadata~1]
            return canonical_client_ip_key(material.client_address,
                                           ipv6_prefix=material.ipv6_prefix)
        case KeyComponent.user:
            # A route callable while the identity is pre-auth exposes only the verified subject
            # and has no `user` key.
            # [impl->req~ratelimit-identity-keys-from-evaluating-layer~1]
            # [impl->req~ratelimit-user-keyed-after-barrier-admission~1]
            if material.user_id is None or not material.barrier_admitted:
                raise LimiterKeyError(
                    "a user key needs a linked active user the barrier resolved and admitted")
            return str(material.user_id)
        case KeyComponent.subject_hash:
            value = material.subject_hash
        case KeyComponent.idp_account_hash:
            value = material.idp_account_hash
        case KeyComponent.restore_proof_fingerprint:
            value = material.restore_proof_fingerprint
        case KeyComponent.external_id:
            value = material.external_id
        case _:
            plain = getattr(material, str(component))
            if plain is None:
                raise LimiterKeyError(f"no verified value available for key component {component}")
            return str(plain)
    if value is None:
        raise LimiterKeyError(f"no verified value available for key component {component}")
    # A proof-correlation or provider-account component is only ever its redacted, HMAC-derived
    # form; the raw provider identifier, client input, email address, display name and token
    # claim are all unrepresentable here.
    # [impl->req~ratelimit-proof-correlation-key-fingerprints~1]
    # [impl->req~ratelimit-provider-account-key-component~1]
    if not isinstance(value, DerivedIdentifier):
        raise LimiterKeyError(f"{component} must be a redacted server-derived identifier")
    return value.key


def build_key(policy: Sequence[KeyComponent],
              material: KeyMaterial,
              *,
              layer: LimiterLayer = LimiterLayer.backend) -> str:
    """Assemble one limiter key from verified and server-derived values only."""
    # [impl->req~ratelimit-keys-from-verified-values-only~1]
    if not policy:
        raise LimiterKeyError("a limiter needs a key policy")
    return "|".join(_component_value(component, material, layer) for component in policy)
