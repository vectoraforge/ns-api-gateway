"""The third route category: the two store webhooks Apple and Google call from their own
servers.

These routes are neither public nor behind the Firebase user-token barrier. Each one declares
one named verifier, and that verifier — the backend's own cryptographic verification of the
store's credential — is the only thing that admits a request. Nothing else does: not a generic
external bypass, not a path prefix, not edge rate limiting, and not a valid Firebase user token.
What each route then verifies in detail, how it handles redelivery, and the narrow authority its
handler holds are defined under Store Notification Ingestion in
`04-subscription-restore-and-entitlement-transfer.md`.
"""

# [impl->req~sessions-store-notification-ingestion-crossref~1]

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any

from nativespeaker.api.auth.routes import (
    NAMED_VERIFIERS,
    PROVIDER_CALLBACK_ROUTES,
    ProviderCallbackRoute,
    named_verifier,
)


class ProviderCallbackError(RuntimeError):
    """A provider-callback request was not admitted by the route's named verifier."""


class ProviderCallbackConfigError(RuntimeError):
    """Startup configuration error on a registered provider-callback route."""


# Controls these routes never carry, as a primary or a supplementary control: no secret URL
# token, no IP allowlist, no certificate pinning beyond Apple's own root, and no mTLS. Each
# vendor's own documented mechanism, together with the authoritative Play lookup the Google
# route performs, is the whole control set, so a configuration that adds one of these is a
# startup error rather than extra safety.
# [impl->req~sessions-no-supplementary-callback-controls~1]
SUPPLEMENTARY_CONTROLS: frozenset[str] = frozenset({
    "secret_url_token", "url_token", "shared_secret", "webhook_secret",
    "ip_allowlist", "allowed_ips", "source_ip_ranges",
    "mtls", "client_certificate", "certificate_pinning", "pinned_certificates",
    "basic_auth",
})


@dataclass(frozen=True, slots=True)
class CallbackRequest:
    """What a store's call carries. `authorization` holds the `Authorization` field values as
    they arrived — the gateway mints and trusts no identity header on these paths and forwards
    Google's Pub/Sub OIDC bearer token unchanged — and `body_credential` the JWS Apple signs
    into its body, which the backend verifies itself."""
    method: str
    path: str
    authorization: tuple[str, ...] = ()
    body_credential: str | None = None
    body: Mapping[str, Any] = field(default_factory=dict)


CallbackVerifier = Callable[[CallbackRequest], Any]


async def verify_provider_callback(request: CallbackRequest,
                                   verifiers: Mapping[str, CallbackVerifier]) -> str:
    """Admit a provider-callback request through the one named verifier its registry entry
    declares, and return that verifier's name.

    Membership is by exact enumerated path, so a path-prefix or wildcard match admits nothing,
    and a missing verifier fails closed rather than falling back to a generic external or
    unauthenticated bypass. Edge rate limiting on these paths is ordinary hygiene and never
    stands in for this verification."""
    # [impl->req~sessions-named-verifier-per-callback-route~1]
    # [impl->req~sessions-no-wildcard-callback-membership~1]
    # [impl->req~sessions-gateway-edge-role-only-on-callbacks~1]
    name = named_verifier(request.method, request.path)
    if name is None:
        raise ProviderCallbackError(
            f"{request.method} {request.path} is not a provider-callback route")
    if name not in NAMED_VERIFIERS:
        raise ProviderCallbackError(f"{name} is not a named provider-callback verifier")
    verifier = verifiers.get(name)
    if verifier is None:
        raise ProviderCallbackError(f"{name} is not configured for {request.path}")
    outcome = verifier(request)
    if isawaitable(outcome):
        await outcome
    return name


def apple_signed_payload_verifier(verify_jws: Callable[[str], Any]) -> CallbackVerifier:
    """Apple's named verifier. Apple's request carries no `Authorization` field at all and
    reaches the backend as sent; the credential is the JWS in the body, and this backend — not
    the gateway — verifies it."""
    # [impl->req~sessions-gateway-never-parses-apple-signedpayload~1]
    async def verify(request: CallbackRequest) -> None:
        payload = request.body_credential or request.body.get("signedPayload")
        if not payload:
            raise ProviderCallbackError("no signedPayload to verify")
        outcome = verify_jws(str(payload))
        if isawaitable(outcome):
            await outcome

    return verify


def pubsub_oidc_verifier(verify_oidc: Callable[[str], Any]) -> CallbackVerifier:
    """The Play RTDN route's named verifier. Google's Pub/Sub push carries an OIDC bearer token
    in `Authorization`, which the gateway forwards unchanged and which the backend verifies
    itself. That token is not a Firebase ID token and is never verified as one, and it opens
    only this route."""
    # [impl->req~sessions-gateway-forwards-pubsub-oidc-unchanged~1]
    def verify(request: CallbackRequest) -> None:
        if len(request.authorization) != 1:
            raise ProviderCallbackError("exactly one Authorization field carries the OIDC token")
        scheme, separator, token = request.authorization[0].partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            raise ProviderCallbackError("the Pub/Sub OIDC credential is a Bearer token")
        verify_oidc(token)

    return verify


def registered_callback_routes(configured_integrations: Iterable[str]
                               ) -> tuple[ProviderCallbackRoute, ...]:
    """The callback routes a deployment registers: a store's route is not registered at all
    while that store's integration is unconfigured."""
    # [impl->req~sessions-named-verifier-per-callback-route~1]
    configured = set(configured_integrations)
    return tuple(route for route in PROVIDER_CALLBACK_ROUTES if route.integration in configured)


def _configured(raw_config: Mapping[str, Any], dotted_key: str) -> bool:
    node: Any = raw_config
    for part in dotted_key.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False
        node = node[part]
    return node not in (None, "", [], {})


def callback_configuration_problems(registered_paths: Sequence[tuple[str, str]],
                                    raw_config: Mapping[str, Any]) -> list[str]:
    """Every reason a registered provider-callback route must not serve traffic."""
    # A registered route whose named verifier lacks configuration it requires is a startup
    # failure, never a route that runs with a weaker check.
    # [impl->req~sessions-named-verifier-per-callback-route~1]
    problems: list[str] = []
    registered = {(method.upper(), path) for method, path in registered_paths}
    for route in PROVIDER_CALLBACK_ROUTES:
        if (route.method, route.path) not in registered:
            continue
        if route.verifier not in NAMED_VERIFIERS:
            problems.append(f"{route.path} declares no named verifier")
        for key in route.required_config:
            if not _configured(raw_config, key):
                problems.append(f"{route.path} is registered without {key}")
        # [impl->req~sessions-no-supplementary-callback-controls~1]
        section = raw_config.get(route.integration)
        if isinstance(section, Mapping):
            for control in sorted(SUPPLEMENTARY_CONTROLS & set(section)):
                problems.append(f"{route.path} carries the supplementary control {control}")
    return problems


def assert_callback_configuration(registered_paths: Sequence[tuple[str, str]],
                                  raw_config: Mapping[str, Any]) -> None:
    """Startup fails closed on a registered provider-callback route that cannot verify its
    store's credential, or that carries a supplementary control instead of relying on the
    vendor's own mechanism."""
    problems = callback_configuration_problems(registered_paths, raw_config)
    if problems:
        raise ProviderCallbackConfigError("; ".join(sorted(set(problems))))
