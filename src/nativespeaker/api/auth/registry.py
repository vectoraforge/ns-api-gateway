"""The declarative route registry (§2.2) and the startup enumeration assertion (§2.3).

The registry is the single source of truth for which category a route sits in. The assertion is
set-equality against the live router in *both* directions and runs inside the application lifespan
(D-14), so a route the router registers without a declaration -- or a declaration with no route --
aborts boot rather than inheriting an implicit disposition.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi.routing import APIRoute, APIWebSocketRoute

from nativespeaker.api.models.auth import AuthOperation


class Category(StrEnum):
    """The three-way partition (§2.1). Every registered route sits in exactly one."""
    public = "public"
    provider_callback = "provider_callback"
    authenticated = "authenticated"


@dataclass(frozen=True, slots=True)
class RouteMetadata:
    """§2.2 per-route metadata. Readable *before* the barrier runs."""
    method: str
    path: str
    category: Category
    operation: AuthOperation | None = None
    preauth_callable: bool = False
    challenge_bearing: bool = False
    named_verifier: str | None = None
    quota_checked: bool = False


@dataclass(frozen=True, slots=True)
class NamedVerifier:
    """A provider-callback verifier seam (§2.1).

    Foundation registers none: phases 08 and 09 register the Apple signed-payload verifier and the
    Pub/Sub OIDC verifier along with their routes. The seam exists now so §2.3 conditions 4 and 5
    have something to resolve a `named_verifier` against.
    """
    name: str
    configured: bool


VERIFIERS: dict[str, NamedVerifier] = {}

# Only these two operations are challenge-bearing plus the two create-user phases (§2.2).
_CHALLENGE_BEARING_OPERATIONS = frozenset({
    AuthOperation.create_user,
    AuthOperation.upgrade_anonymous_to_registered,
    AuthOperation.claim_anonymous_grant,
    AuthOperation.claim_registered_grant,
})

# The only route that may ever declare `preauth_callable = True` (§2.2, §2.3 condition 6).
_PREAUTH_CALLABLE_ROUTE = ("POST", "/auth/create-user")

# Every route the router registers today, with the §8.1 metadata. Declaring the pre-existing routes
# here is REBIND-01 landing in Phase 35: §2.3 is set equality against the live router and D-14 makes
# it run at real startup, so whoever changes the router must change this table in the same commit.
# Plan 04 deletes `GET /users/me` and `POST /webhooks/apple` from both the router and this table.
REGISTRY: tuple[RouteMetadata, ...] = (
    RouteMetadata(method="GET", path="/health/ready", category=Category.public),
    RouteMetadata(method="GET", path="/", category=Category.authenticated),
    RouteMetadata(method="GET", path="/examples", category=Category.authenticated),
    RouteMetadata(method="GET", path="/users/me", category=Category.authenticated),
    RouteMetadata(method="GET", path="/chats", category=Category.authenticated),
    RouteMetadata(method="POST", path="/chats", category=Category.authenticated),
    RouteMetadata(method="GET", path="/chats/{chat_id}", category=Category.authenticated),
    RouteMetadata(method="POST", path="/chats/{chat_id}", category=Category.authenticated),
    RouteMetadata(method="DELETE", path="/chats/{chat_id}", category=Category.authenticated),
    RouteMetadata(method="POST", path="/webhooks/apple", category=Category.authenticated),
)

_INDEX: dict[tuple[str, str], RouteMetadata] = {(e.method, e.path): e for e in REGISTRY}


def lookup(method: str, path: str) -> RouteMetadata | None:
    """Resolve declared metadata for a matched route. `None` means undeclared -- treat as strictest."""
    return _INDEX.get((method, path))


def enumerate_registered(app: Any) -> tuple[set[tuple[str, str]], list[str]]:
    """Enumerate the router's actually registered `(method, path)` pairs.

    `route.methods` is used exactly as FastAPI built it -- `HEAD` is never synthesized, because
    `APIRoute.__init__` does not add it and a synthesized entry becomes a phantom declaration.
    """
    registered: set[tuple[str, str]] = set()
    problems: list[str] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                registered.add((method, route.path))
        elif isinstance(route, APIWebSocketRoute):
            registered.add(("WEBSOCKET", route.path))
        else:
            problems.append(f"unsupported route object registered: "
                            f"{type(route).__name__} {getattr(route, 'path', '?')!r}")
    return registered, problems


def assert_route_enumeration(app: Any,
                             registry: tuple[RouteMetadata, ...] = REGISTRY,
                             *,
                             verifiers: Mapping[str, NamedVerifier] | None = None) -> None:
    """Fail closed on any of the nine §2.3 conditions. Raises `RuntimeError` listing every problem."""
    # Local import: barrier.py imports this module for its own route lookup, and condition 9 needs
    # the barrier class by identity. Importing at function scope keeps the cycle from forming.
    from nativespeaker.api.auth.barrier import AuthBarrierMiddleware

    known_verifiers = VERIFIERS if verifiers is None else verifiers

    registered, problems = enumerate_registered(app)
    declared = {(e.method, e.path) for e in registry}

    # Conditions 1 and 2 -- set equality, reported as two separately labelled differences. Direction
    # 2 is the one a previous implementation omitted, leaving seven phantom declarations undetected.
    if extra := registered - declared:
        problems.append(f"registered but undeclared: {sorted(extra)}")
    if missing := declared - registered:
        problems.append(f"declared but unregistered: {sorted(missing)}")

    seen: set[tuple[str, str]] = set()
    operations: dict[AuthOperation, tuple[str, str]] = {}
    for entry in registry:
        key = (entry.method, entry.path)

        if key in seen:  # condition 3 -- one route resolving into more than one entry/category
            problems.append(f"duplicate registry entry for {key}")
        seen.add(key)

        if entry.preauth_callable and key != _PREAUTH_CALLABLE_ROUTE:  # condition 6
            problems.append(f"illegal preauth_callable declaration on {key}: only "
                            f"{_PREAUTH_CALLABLE_ROUTE} may be pre-auth callable")

        if entry.operation is not None:
            if not isinstance(entry.operation, AuthOperation):  # condition 8 -- unknown operation
                problems.append(f"operation {entry.operation!r} on {key} is not a "
                                f"core.auth_operation value")
            else:
                if entry.category is not Category.authenticated:  # condition 8 -- wrong category
                    problems.append(f"operation {entry.operation} declared on {key}, whose "
                                    f"category is {entry.category}, not authenticated")
                if (other := operations.get(entry.operation)) is not None:  # condition 8 -- two routes
                    problems.append(f"operation {entry.operation} is mapped by two routes: "
                                    f"{other} and {key}")
                else:
                    operations[entry.operation] = key

        if entry.challenge_bearing and entry.operation not in _CHALLENGE_BEARING_OPERATIONS:
            problems.append(f"illegal challenge_bearing declaration on {key}: operation "  # condition 7
                            f"{entry.operation!r} is not challenge-bearing")

        if entry.category is Category.provider_callback:
            if entry.named_verifier is None:  # condition 4 -- generic bypass instead of a verifier
                problems.append(f"provider_callback route {key} declares named_verifier=None")
            elif (verifier := known_verifiers.get(entry.named_verifier)) is None:  # condition 4
                problems.append(f"provider_callback route {key} names verifier "
                                f"{entry.named_verifier!r}, which is not registered")
            elif not verifier.configured:  # condition 5 -- verifier lacks required configuration
                problems.append(f"verifier {entry.named_verifier!r} for {key} lacks required "
                                f"configuration")
        elif entry.named_verifier is not None:
            problems.append(f"named_verifier {entry.named_verifier!r} declared on {key}, whose "
                            f"category is {entry.category}, not provider_callback")

    # Condition 9, asserted structurally: one middleware wraps the whole router (D-01), so no
    # registered route can be outside it -- provided the barrier is actually installed.
    if not any(m.cls is AuthBarrierMiddleware for m in app.user_middleware):
        problems.append("AuthBarrierMiddleware is absent from app.user_middleware: every "
                        "authenticated route would be registered outside the barrier")

    if problems:
        raise RuntimeError("route enumeration assertion failed:\n  " + "\n  ".join(problems))
