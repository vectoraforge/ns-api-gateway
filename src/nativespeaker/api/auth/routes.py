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
# documentation routes FastAPI registers.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/health/ready"),
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
})


@dataclass(frozen=True, slots=True)
class ProviderCallbackRoute:
    """A store webhook. The calling store authenticates with its own credential, which the
    backend verifies with the named verifier this entry declares."""
    method: str
    path: str
    verifier: str


# Closed, enumerated by exact path. A wildcard or path-prefix exemption never confers
# membership. `01-sessions-and-identity-resolution.md` owns the membership list.
PROVIDER_CALLBACK_ROUTES: tuple[ProviderCallbackRoute, ...] = (
    ProviderCallbackRoute("POST", "/webhooks/app-store", "apple_signed_payload"),
    ProviderCallbackRoute("POST", "/webhooks/google-play/rtdn", "pubsub_oidc"),
)

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
# token, followed by the remaining routine authenticated traffic.
AUTHENTICATED_ROUTES: tuple[AuthenticatedRoute, ...] = (
    # [impl->req~shared-id-token-endpoint-auth-sync~1]
    AuthenticatedRoute("POST", "/auth/sync"),
    # Auth challenge prepare calls and auth completion calls are the same four challenge-bearing
    # endpoint URLs, selected by the mode-signal partition.
    # [impl->req~shared-id-token-endpoint-challenge-prepare~1]
    # [impl->req~shared-id-token-endpoint-completion~1]
    AuthenticatedRoute("POST", "/auth/create-user", pre_auth_callable=True),
    AuthenticatedRoute("POST", "/auth/upgrade-anonymous"),
    AuthenticatedRoute("POST", "/auth/claim-anonymous-grant"),
    AuthenticatedRoute("POST", "/auth/claim-registered-grant"),
    # [impl->req~shared-id-token-endpoint-restore-subscription~1]
    AuthenticatedRoute("POST", "/auth/restore-subscription"),
    # [impl->req~shared-id-token-endpoint-users-me~1]
    AuthenticatedRoute("GET", "/users/me"),
    # [impl->req~shared-id-token-endpoint-chat-quota~1]
    AuthenticatedRoute("GET", "/chats"),
    AuthenticatedRoute("POST", "/chats"),
    AuthenticatedRoute("GET", "/chats/{chat_id}"),
    AuthenticatedRoute("POST", "/chats/{chat_id}"),
    AuthenticatedRoute("DELETE", "/chats/{chat_id}"),
    AuthenticatedRoute("GET", "/users/me/quota"),
    # [impl->req~shared-id-token-endpoint-sign-out-everywhere~1]
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
    callback = _CALLBACK_BY_ROUTE.get((method.upper(), path))
    return callback.verifier if callback is not None else None


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
    route is admitted by a generic bypass instead of the named verifier it declares."""
    # [impl->req~shared-route-categories~1]
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
