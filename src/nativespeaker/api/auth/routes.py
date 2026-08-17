"""The three-way route partition: public allowlist, provider-callback routes, and everything
else, which is authenticated behind the shared pre-handler barrier.

Authentication is the default, not the exception: an undeclared route is treated as
authenticated at runtime, and the startup assertion below fails closed on it.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RouteCategory(StrEnum):
    public = "public"
    provider_callback = "provider_callback"
    authenticated = "authenticated"


# Zero-authentication routes. The health and readiness probes, plus the generated schema and
# documentation routes FastAPI registers. The allowlist is explicit and enumerated: neither
# provider-callback route is on it, because public means zero authentication and those routes
# require provider-specific verification.
# [impl->req~sessions-shared-entry-point-three-way-partition~1]
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/health/ready"),
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
})


@dataclass(frozen=True, slots=True)
class ProviderCallbackRoute:
    """A store webhook: a machine-to-machine call from the store's own servers, carrying no
    Firebase ID token and therefore never able to pass the barrier, and not public either,
    because it carries a provider credential the backend must verify.

    The calling store authenticates with that credential, which the backend verifies with the
    one named verifier this entry declares. `integration` names the store integration whose
    configuration the route needs, and `required_config` the configuration keys that verifier
    cannot run without."""
    # [impl->req~sessions-provider-callback-third-category~1]
    # [impl->req~sessions-named-verifier-per-callback-route~1]
    method: str
    path: str
    verifier: str
    integration: str = ""
    required_config: tuple[str, ...] = ()


# Closed, enumerated by exact path, and the category holds nothing else. A wildcard or
# path-prefix exemption such as `/webhooks/*` never confers membership, and a further route
# joins only by being named in `01-sessions-and-identity-resolution.md`, which owns this list.
# A client posting a receipt or a purchase token is a signed-in user on an ordinary barrier
# route: client-submitted purchase evidence never makes a route provider-callable.
# [impl->req~sessions-provider-callback-membership-closed~1]
# [impl->req~sessions-no-wildcard-callback-membership~1]
# [impl->req~sessions-gateway-behavior-callback-paths-only~1]
PROVIDER_CALLBACK_ROUTES: tuple[ProviderCallbackRoute, ...] = (
    # Apple App Store Server Notifications. Apple's request carries no `Authorization` field at
    # all: the credential is the JWS in its body, which this backend verifies itself.
    # [impl->req~sessions-webhook-app-store-path~1]
    # [impl->req~sessions-gateway-never-parses-apple-signedpayload~1]
    ProviderCallbackRoute("POST", "/webhooks/app-store", "apple_signed_payload",
                          integration="apple",
                          required_config=("apple.bundle_id", "apple.environment",
                                           "apple.certs_dir")),
    # The Cloud Pub/Sub push subscription that delivers Google Play real-time developer
    # notifications. Its credential is the Pub/Sub OIDC bearer token in `Authorization`, which
    # reaches the backend unchanged and which the backend verifies itself.
    # [impl->req~sessions-webhook-google-play-rtdn-path~1]
    # [impl->req~sessions-gateway-forwards-pubsub-oidc-unchanged~1]
    ProviderCallbackRoute("POST", "/webhooks/google-play/rtdn", "pubsub_oidc",
                          integration="google_play",
                          required_config=("google_play.package_name",
                                           "google_play.pubsub_audience",
                                           "google_play.pubsub_service_account_email")),
)

# Each callback route declares one of these. A generic external or unauthenticated bypass never
# stands in for one.
# [impl->req~sessions-named-verifier-per-callback-route~1]
NAMED_VERIFIERS: frozenset[str] = frozenset({"apple_signed_payload", "pubsub_oidc"})


@dataclass(frozen=True, slots=True)
class AuthenticatedRoute:
    """A route behind the barrier. `id_token_required` marks the endpoint families that must
    present the external IDP ID token for backend verification."""
    method: str
    path: str
    pre_auth_callable: bool = False
    id_token_required: bool = True


# The authenticated endpoint families that require the client to present the external IDP ID
# token, followed by the remaining routine authenticated traffic. Every one of them runs through
# the one shared entry point and presents its Firebase ID token as `Authorization: Bearer`.
# [impl->req~sessions-authenticated-endpoint-families~1]
# [impl->req~sessions-bearer-firebase-id-token~1]
AUTHENTICATED_ROUTES: tuple[AuthenticatedRoute, ...] = (
    # [impl->req~shared-id-token-endpoint-auth-sync~1]
    # [impl->req~sessions-authfamily-auth-sync~1]
    AuthenticatedRoute("POST", "/auth/sync"),
    # Auth challenge prepare calls and auth completion calls are the same four challenge-bearing
    # endpoint URLs, selected by the mode-signal partition.
    # [impl->req~shared-id-token-endpoint-challenge-prepare~1]
    # [impl->req~shared-id-token-endpoint-completion~1]
    # [impl->req~sessions-authfamily-challenge-prepare~1]
    # [impl->req~sessions-authfamily-completion-calls~1]
    AuthenticatedRoute("POST", "/auth/create-user", pre_auth_callable=True),
    AuthenticatedRoute("POST", "/auth/upgrade-anonymous"),
    AuthenticatedRoute("POST", "/auth/claim-anonymous-grant"),
    AuthenticatedRoute("POST", "/auth/claim-registered-grant"),
    # [impl->req~shared-id-token-endpoint-restore-subscription~1]
    # [impl->req~sessions-authfamily-restore-subscription~1]
    AuthenticatedRoute("POST", "/auth/restore-subscription"),
    # [impl->req~shared-id-token-endpoint-users-me~1]
    # [impl->req~sessions-authfamily-users-me~1]
    AuthenticatedRoute("GET", "/users/me"),
    # [impl->req~shared-id-token-endpoint-chat-quota~1]
    # [impl->req~sessions-authfamily-chat-and-quota~1]
    AuthenticatedRoute("GET", "/chats"),
    AuthenticatedRoute("POST", "/chats"),
    AuthenticatedRoute("GET", "/chats/{chat_id}"),
    AuthenticatedRoute("POST", "/chats/{chat_id}"),
    AuthenticatedRoute("DELETE", "/chats/{chat_id}"),
    AuthenticatedRoute("GET", "/users/me/quota"),
    # [impl->req~shared-id-token-endpoint-sign-out-everywhere~1]
    # [impl->req~sessions-authfamily-sign-out-all~1]
    AuthenticatedRoute("POST", "/auth/sign-out-all"),
    AuthenticatedRoute("GET", "/"),
    AuthenticatedRoute("GET", "/examples"),
)

# [impl->req~shared-id-token-required-endpoints~1]
ID_TOKEN_REQUIRED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    (route.method, route.path) for route in AUTHENTICATED_ROUTES if route.id_token_required)

_AUTHENTICATED_BY_ROUTE: dict[tuple[str, str], AuthenticatedRoute] = {
    (route.method, route.path): route for route in AUTHENTICATED_ROUTES}
_CALLBACK_BY_ROUTE: dict[tuple[str, str], ProviderCallbackRoute] = {
    (route.method, route.path): route for route in PROVIDER_CALLBACK_ROUTES}


class UndeclaredRouteError(RuntimeError):
    """A registered route is in none of the three categories."""


class RouteCategoryError(RuntimeError):
    """The registered routes do not form the required three-way partition."""


def _template_matches(template: str, path: str) -> bool:
    if template == path:
        return True
    template_parts = template.split("/")
    path_parts = path.split("/")
    if len(template_parts) != len(path_parts):
        return False
    for template_part, path_part in zip(template_parts, path_parts, strict=True):
        if template_part.startswith("{") and template_part.endswith("}"):
            if not path_part:
                return False
        elif template_part != path_part:
            return False
    return True


def resolve_route_template(method: str, path: str) -> str | None:
    """Map a concrete request path onto the declared route template, so telemetry labels stay
    bounded. Returns None for a route no registry declares."""
    method = method.upper()
    for candidate in (*PUBLIC_ROUTES, *((r.method, r.path) for r in PROVIDER_CALLBACK_ROUTES),
                      *((r.method, r.path) for r in AUTHENTICATED_ROUTES)):
        if candidate[0] == method and _template_matches(candidate[1], path):
            return candidate[1]
    return None


def categorize(method: str, path: str, *, strict: bool = False) -> RouteCategory:
    """Classify a route. Authentication is the default, so an undeclared route is
    authenticated at runtime; `strict` turns it into the startup failure instead."""
    # [impl->req~shared-route-categories~1]
    method = method.upper()
    for candidate in PUBLIC_ROUTES:
        if candidate[0] == method and _template_matches(candidate[1], path):
            return RouteCategory.public
    for callback in PROVIDER_CALLBACK_ROUTES:
        if callback.method == method and _template_matches(callback.path, path):
            return RouteCategory.provider_callback
    for route in AUTHENTICATED_ROUTES:
        if route.method == method and _template_matches(route.path, path):
            return RouteCategory.authenticated
    if strict:
        raise UndeclaredRouteError(f"{method} {path} is in none of the three route categories")
    return RouteCategory.authenticated


def requires_id_token(method: str, path: str) -> bool:
    """Every authenticated endpoint family presents the Firebase ID token for backend
    verification."""
    return categorize(method, path) is RouteCategory.authenticated


def is_pre_auth_callable(method: str, path: str) -> bool:
    """A pre-auth identity is admitted only where the route declares it. The only such route
    is `POST /auth/create-user`, in both its prepare and completion phases."""
    route = _AUTHENTICATED_BY_ROUTE.get((method.upper(), path))
    return route is not None and route.pre_auth_callable


def named_verifier(method: str, path: str) -> str | None:
    """The verifier a provider-callback route declares, matched on the exact enumerated path.
    A path-prefix or wildcard match never confers membership, so a path that merely starts with
    `/webhooks/` has no verifier and is not in the category."""
    # [impl->req~sessions-no-wildcard-callback-membership~1]
    callback = _CALLBACK_BY_ROUTE.get((method.upper(), path))
    return callback.verifier if callback is not None else None


# A route whose path looks like a credential-issuing or session endpoint. The backend mints no
# backend access token and keeps no server-side authentication session tier, so no such route
# exists and the verified identity context carries no credential of its own: a request's whole
# authentication state is the external ID token it presented.
# [impl->req~sessions-no-backend-tokens-or-session-tier~1]
CREDENTIAL_ROUTE_MARKERS: tuple[str, ...] = ("token", "refresh", "session", "login", "logout")

# The context handlers receive names an identity, never a credential or a session.
CREDENTIAL_CONTEXT_FIELDS: tuple[str, ...] = ("token", "session", "credential", "secret",
                                              "cookie", "expires")


def backend_credential_violations(registered: Iterable[tuple[str, str]],
                                  context_fields: Iterable[str]) -> list[str]:
    """Every place the backend would be minting a credential or keeping a session tier."""
    # [impl->req~sessions-no-backend-tokens-or-session-tier~1]
    violations: list[str] = []
    for method, path in registered:
        segments = {segment for part in path.lower().split("/") for segment in part.split("-")}
        for marker in CREDENTIAL_ROUTE_MARKERS:
            if marker in segments:
                violations.append(f"{method} {path} mints a backend credential or session")
    for field in context_fields:
        lowered = field.lower()
        for marker in CREDENTIAL_CONTEXT_FIELDS:
            if marker in lowered:
                violations.append(f"the verified identity context carries {field}")
    return violations


def registered_routes(app: Any) -> list[tuple[str, str]]:
    """Every method and path the router has registered, as the enumeration assertion reads
    them."""
    return _registered_routes(getattr(app, "routes", []))


def _registered_routes(routes: Iterable[Any]) -> list[tuple[str, str]]:
    registered: list[tuple[str, str]] = []
    for route in routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or not methods:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            registered.append((method, path))
    return registered


def assert_route_categories(app: Any) -> None:
    """Startup assertion: enumerate the router's registered routes and fail closed if a route
    is in none of the three categories, if it is in more than one, or if a provider-callback
    route is admitted by a generic external or path-prefix bypass instead of the named verifier
    it declares.

    This is the one route-coverage check required, and it covers the shared pre-handler barrier.
    No gateway conformance check belongs here: no Envoy route inventory, no assertion over
    gateway configuration, no continuous gateway probing."""
    # [impl->req~shared-route-categories~1]
    # [impl->req~sessions-route-enumeration-assertion~1]
    # [impl->req~sessions-shared-entry-point-three-way-partition~1]
    problems: list[str] = []
    for callback in PROVIDER_CALLBACK_ROUTES:
        key = (callback.method, callback.path)
        if key in PUBLIC_ROUTES or key in _AUTHENTICATED_BY_ROUTE:
            problems.append(f"{callback.method} {callback.path} is in more than one category")
        if callback.verifier not in NAMED_VERIFIERS:
            problems.append(f"{callback.method} {callback.path} declares no named verifier")
        if "*" in callback.path or "{" in callback.path:
            problems.append(f"{callback.method} {callback.path} is a wildcard callback entry")
    for key in PUBLIC_ROUTES & frozenset(_AUTHENTICATED_BY_ROUTE):
        problems.append(f"{key[0]} {key[1]} is in more than one category")

    for method, path in _registered_routes(getattr(app, "routes", [])):
        try:
            categorize(method, path, strict=True)
        except UndeclaredRouteError as exc:
            problems.append(str(exc))

    if problems:
        raise RouteCategoryError("; ".join(sorted(set(problems))))
