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
# `GET /users/me` and `POST /webhooks/apple` were deleted here in the same commit as their routers
# (D-16); Phase 39 and Phase 43 write the replacements and re-declare them alongside.
REGISTRY: tuple[RouteMetadata, ...] = (
    RouteMetadata(method="GET", path="/health/ready", category=Category.public),
    RouteMetadata(method="GET", path="/", category=Category.authenticated),
    RouteMetadata(method="GET", path="/examples", category=Category.authenticated),
    RouteMetadata(method="GET", path="/chats", category=Category.authenticated),
    # quota_checked is enforcement, not documentation: condition 10 requires this route to be
    # served by a handler that consumes the allowance, and a flag that moves without its handler
    # -- in either direction -- fails boot rather than serving requests free.
    #
    # Exactly these two of the eight entries carry it (D-07). The four reads and the delete do not:
    # charging a user for listing or deleting what they already paid for is not what the allowance
    # counts.
    RouteMetadata(method="POST", path="/chats", category=Category.authenticated,
                  quota_checked=True),
    RouteMetadata(method="GET", path="/chats/{chat_id}", category=Category.authenticated),
    RouteMetadata(method="POST", path="/chats/{chat_id}", category=Category.authenticated,
                  quota_checked=True),
    RouteMetadata(method="DELETE", path="/chats/{chat_id}", category=Category.authenticated),
    # Phase 37 / spec 02-create-user.md. The one route in the whole table that may carry
    # `preauth_callable` -- condition 6 above fails boot on any other entry declaring it, and
    # `_PREAUTH_CALLABLE_ROUTE` is the pin.
    #
    # `category` is `authenticated`, not a fourth category and not `public`: condition 8 rejects a
    # non-`None` `operation` on any other category, and the flag -- not the category -- is what
    # admits the unlinked caller (`auth/identity.py:87-88`). The barrier still verifies the token
    # on this route like every other one; what `preauth_callable` changes is only what happens when
    # that verified pair resolves to no identity row.
    RouteMetadata(method="POST", path="/auth/create-user", category=Category.authenticated,
                  operation=AuthOperation.create_user, preauth_callable=True,
                  challenge_bearing=True),
)

_INDEX: dict[tuple[str, str], RouteMetadata] = {(e.method, e.path): e for e in REGISTRY}


def lookup(method: str, path: str,
           registry: tuple[RouteMetadata, ...] = REGISTRY) -> RouteMetadata | None:
    """Resolve declared metadata for a matched route. `None` means undeclared -- treat as strictest.

    The barrier passes the registry it read from `scope["app"].state.route_registry` per request,
    so a test app can declare a route carrying an `operation` -- every route this phase registers
    declares `operation = None`, which would otherwise leave the audited-path branch unreachable
    from anything. The default keeps the production lookup on the prebuilt index and keeps this one
    function the only place a `(method, path)` resolves, so the two cannot drift.
    """
    if registry is REGISTRY:
        return _INDEX.get((method, path))
    return next((e for e in registry if e.method == method and e.path == path), None)


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
    """Fail closed on any of ten conditions -- the nine §2.3 ones plus D-05's quota cross-check.

    Raises `RuntimeError` listing every problem found, never only the first.
    """
    # Local imports, both breaking an import cycle rather than deferring work:
    #   - barrier.py imports this module for its own route lookup, and condition 9 needs the
    #     barrier class by identity;
    #   - app.dependencies imports auth.context, which imports this module, and condition 10 needs
    #     the quota-consuming handlers by identity.
    # The handler tuple is therefore built here rather than at module scope: there is no
    # import-time moment at which those callables are available to this module.
    from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
    from nativespeaker.api.routers.chats import create_chat, send_message

    # Every handler that consumes the allowance, by identity.
    #
    # This set used to be the `require_quota_*` decorator dependencies. It is the handlers now
    # because REBIND-06 moved the charge off the decorator and into the handler's own call stack --
    # a decorator dependency runs before the handler can reject anything, so five rejections
    # charged a caller for work the service never did. What condition 10 asserts is unchanged in
    # both strength and direction: it pairs the declared flag with the thing that does the
    # charging, and a handler missing from here reads as "consumes nothing" and fails boot on the
    # route that declares the flag.
    quota_consuming_handlers = (create_chat, send_message)

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

    # Condition 10 (D-05) -- the `quota_checked` flag and the charging handler must agree, in both
    # directions, or the flag is documentation rather than enforcement: a route declaring it while
    # served by a handler that charges nothing serves every request free, invisibly.
    #
    # `route.endpoint` is the handler the router will actually call. Matching is by callable
    # IDENTITY -- a name string would silently pass a renamed function, which is the failure this
    # condition exists to catch. `functools.wraps`-style decoration would defeat identity here; no
    # handler carries any, and one added later must be registered by its wrapper rather than its
    # wrapped function.
    attached: set[tuple[str, str]] = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and any(route.endpoint is handler
                                               for handler in quota_consuming_handlers):
            for method in route.methods:
                attached.add((method, route.path))

    # Two set differences, so empty input is a no-op rather than an error, and `sorted()` on both
    # so the same disagreement produces byte-identical text on every run.
    declared_quota = {(e.method, e.path) for e in registry if e.quota_checked}
    if undeclared := attached - declared_quota:
        problems.append(f"quota-consuming handler serves a route where quota_checked is not "
                        f"declared: {sorted(undeclared)}")
    if unattached := declared_quota - attached:
        problems.append(f"quota_checked declared but no quota-consuming handler serves it: "
                        f"{sorted(unattached)}")

    # Condition 9, asserted structurally: one middleware wraps the whole router (D-01), so no
    # registered route can be outside it -- provided the barrier is actually installed.
    if not any(m.cls is AuthBarrierMiddleware for m in app.user_middleware):
        problems.append("AuthBarrierMiddleware is absent from app.user_middleware: every "
                        "authenticated route would be registered outside the barrier")

    if problems:
        raise RuntimeError("route enumeration assertion failed:\n  " + "\n  ".join(problems))
