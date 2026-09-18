"""App-construction invariants admission depends on, asserted over the real app because runtime hides them."""
import ast
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute

from nativespeaker.api.app import dependencies as dependencies_module
from nativespeaker.api.app import lifespan as lifespan_module
from nativespeaker.api.app.dependencies import (
    get_claims,
    get_db,
    get_identity,
    get_runtime,
    verify_app_store_notification,
    verify_google_play_notification,
)
from nativespeaker.api.app.main import app as real_app
from nativespeaker.api.app.runtime import Runtime
from unit.conftest import make_runtime

DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# Literals rather than derived from anything, so widening the exemption is a visible edit here.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}
PROVIDER_CALLBACK_VERIFIERS = {"/webhooks/app-store": verify_app_store_notification,
                               "/webhooks/google-play/rtdn": verify_google_play_notification}
PROVIDER_CALLBACK_PATHS = set(PROVIDER_CALLBACK_VERIFIERS)

DEPENDENCIES_MODULE = Path(dependencies_module.__file__)
LIFESPAN_MODULE = Path(lifespan_module.__file__)
TESTS_ROOT = Path(__file__).resolve().parents[1]

# Literals, as above: the one untyped read and the two functions allowed to take a `Request`.
APP_STATE_CHAIN = "request.app.state"
REQUEST_DECLARING_FUNCTIONS = {"get_runtime", "get_claims"}

# Literals again: a renamed builder, a reordered boot or a new warning is a visible edit here.
FIELD_BUILDERS = ("build_session_factory", "build_firebase_adapter", "build_devicecheck_adapter",
                  "build_app_store_notifications", "build_google_play_notifications")
BOOT_FATAL_BUILDERS = ("build_session_factory", "build_jwt_verifier")
DEGRADED_TOLERANT_BUILDERS = ("build_firebase_adapter", "build_devicecheck_adapter",
                              "build_app_store_notifications", "build_google_play_notifications")
ABSENT_WARNINGS = {"devicecheck_credential_absent", "app_store_configuration_absent",
                   "google_play_configuration_absent"}


def _dotted(node: ast.Attribute) -> str:
    """The attribute chain as text, or `""` when it is not rooted in a plain name."""
    parts = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return ""
    parts.append(current.id)
    return ".".join(reversed(parts))


def _dependency_functions() -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function `dependencies.py` defines, at any nesting depth."""
    tree = ast.parse(DEPENDENCIES_MODULE.read_text())
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _app_state_chains() -> list[ast.Attribute]:
    """Every `request.app.state` chain in the module, counted wherever it sits."""
    tree = ast.parse(DEPENDENCIES_MODULE.read_text())
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and _dotted(node) == APP_STATE_CHAIN]


def _assignment_targets(node: ast.Assign) -> list[ast.expr]:
    """Every name this statement assigns, unpacked targets included."""
    targets: list[ast.expr] = []
    for target in node.targets:
        if isinstance(target, (ast.Tuple, ast.List)):
            targets.extend(target.elts)
        else:
            targets.append(target)
    return targets


def _state_assignments(names: set[str]) -> list[str]:
    """Every `<...>.state.<name>` assignment under `tests/`, as file and line."""
    found = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Assign):
                continue
            for target in _assignment_targets(node):
                if (isinstance(target, ast.Attribute) and target.attr in names
                        and isinstance(target.value, ast.Attribute)
                        and target.value.attr == "state"):
                    found.append(f"{path.relative_to(TESTS_ROOT)}:{node.lineno} "
                                 f"sets .state.{target.attr}")
    return found


def _lifespan_tree() -> ast.Module:
    """The `lifespan.py` source, parsed."""
    return ast.parse(LIFESPAN_MODULE.read_text())


def _function_named(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """The one function of that name, found at any nesting depth."""
    found = [node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    assert len(found) == 1, f"{name} is defined {len(found)} times"
    return found[0]


def _first_call_lines(node: ast.AST) -> dict[str, int]:
    """The first line each callable is called at under this node, dotted calls keyed on the attribute."""
    lines: dict[str, int] = {}
    for inner in sorted((node for node in ast.walk(node) if isinstance(node, ast.Call)),
                        key=lambda call: call.lineno):
        if isinstance(inner.func, ast.Name):
            lines.setdefault(inner.func.id, inner.lineno)
        elif isinstance(inner.func, ast.Attribute):
            lines.setdefault(inner.func.attr, inner.lineno)
    return lines


def _lifespan_with_body() -> list[ast.stmt]:
    """The body of the one `async with` in `lifespan`."""
    opened = [node for node in ast.walk(_function_named(_lifespan_tree(), "lifespan"))
              if isinstance(node, ast.AsyncWith)]
    assert len(opened) == 1, f"lifespan opens {len(opened)} async with blocks"
    return opened[0].body


def _warning_events() -> set[str]:
    """Every event name `lifespan.py` passes to `logger.warning`."""
    events = set()
    for node in ast.walk(_lifespan_tree()):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "warning" and node.args):
            continue
        event = node.args[0]
        if isinstance(event, ast.Constant):
            events.add(event.value)
    return events


def _api_routes() -> list[APIRoute]:
    return [route for route in real_app.routes if isinstance(route, APIRoute)]


def _declared(route: APIRoute) -> list:
    """The callables FastAPI resolved for this route, router-level declarations included."""
    return [dependency.call for dependency in route.dependant.dependencies]


def _flattened(route: APIRoute) -> list:
    """Every dependency callable in resolution order, sub-dependencies depth-first under their parent."""
    order = []

    def walk(dependencies):
        for dependency in dependencies:
            order.append(dependency.call)
            walk(dependency.dependencies)

    walk(route.dependant.dependencies)
    return order


def _route_at(path: str) -> APIRoute:
    """The one registered route at this exact path."""
    routes = [route for route in _api_routes() if route.path == path]
    assert len(routes) == 1, f"{path} is registered {len(routes)} times"
    return routes[0]


class TestEveryRouteIsAuthenticated:
    """The structural replacement for the deleted startup assertion: the declaration is what serves traffic."""

    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   | PROVIDER_CALLBACK_PATHS
                   and get_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"

    @pytest.mark.parametrize("path", sorted(PREAUTH_CALLABLE_PATHS))
    def test_the_preauth_callable_route_still_verifies_the_token(self, path):
        """Create-user is exempt from the narrowing, not from authentication: a linked caller is owed a 409."""
        declared = [_declared(route) for route in _api_routes() if route.path == path]
        assert declared, f"{path} is not a registered route"
        assert all(get_claims in calls for calls in declared)

    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant",
                                      "/auth/restore-subscription", "/auth/sign-out-all",
                                      "/users/me"))
    def test_a_narrowed_route_declares_the_linked_identity_narrowing(self, path):
        """Named rather than left to the generic case, which would also pass if the route were exempted."""
        declared = [_declared(route) for route in _api_routes() if route.path == path]
        assert declared, f"{path} is not a registered route"
        assert all(get_identity in calls for calls in declared)

    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant",
                                      "/auth/restore-subscription", "/auth/sign-out-all",
                                      "/users/me"))
    def test_a_narrowed_route_is_in_neither_exemption_set(self, path):
        """The route is authenticated and narrowed, so widening either literal above would fail here."""
        assert path in {route.path for route in _api_routes()}
        assert path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS

    def test_the_public_allowlist_is_exactly_the_readiness_probe(self):
        """Read off the live router, not off the literal: a second open route fails here, not only below."""
        open_paths = {route.path for route in _api_routes()
                      if route.path not in PROVIDER_CALLBACK_PATHS
                      and get_identity not in _declared(route)
                      and get_claims not in _declared(route)}
        assert open_paths == {"/health/ready"}

    def test_no_route_serves_without_an_identity_or_a_callback_declaration(self):
        """A second such route would have to be added to one of the two literals above to pass."""
        unauthenticated = {route.path for route in _api_routes()
                           if get_identity not in _declared(route)
                           and get_claims not in _declared(route)}
        assert unauthenticated == PUBLIC_PATHS | PROVIDER_CALLBACK_PATHS

    def test_no_route_declares_a_wrapper_around_an_accessor(self):
        """The cache keys on the callable, so a `wraps` wrapper would key differently and verify twice."""
        for route in _api_routes():
            for call in _declared(route):
                wrapped = getattr(call, "__wrapped__", None)
                assert wrapped not in (get_identity, get_claims), \
                    f"{route.path} declares a wrapper around {getattr(wrapped, '__name__', wrapped)}"


class TestTheRuntimeContainerIsFrozenAndSlotted:
    """Criterion 4. The field list is a literal here, so a reordering is a visible edit in this file."""

    FIELD_NAMES = ("config", "session_factory", "jwt_verifier", "firebase_adapter",
                   "devicecheck_adapter", "app_store_notifications",
                   "google_play_notifications", "llm_service")

    def test_the_container_is_a_frozen_slotted_dataclass(self):
        assert is_dataclass(Runtime)
        assert Runtime.__dataclass_params__.frozen is True
        assert hasattr(Runtime, "__slots__")

    def test_the_eight_fields_are_declared_in_build_order(self):
        assert tuple(field.name for field in fields(Runtime)) == self.FIELD_NAMES

    def test_a_built_container_carries_no_instance_dict(self):
        """Slotted, so a field the lifespan never built cannot be smuggled onto the container."""
        assert not hasattr(make_runtime(), "__dict__")

    def test_a_field_cannot_be_reassigned(self):
        # Frozen `__setattr__` runs before the slots check, so this is not an `AttributeError`.
        with pytest.raises(FrozenInstanceError):
            make_runtime().llm_service = None  # ty: ignore[invalid-assignment]

    def test_the_container_lives_in_its_own_module_under_app(self):
        assert Runtime.__module__ == "nativespeaker.api.app.runtime"


class TestTheStackOwnsEveryTeardown:
    """Criteria 1 and 2, read off the `lifespan.py` source. Every expectation is a literal above,
    so a reordered boot or a renamed builder has to be written down here to pass."""

    def test_the_module_builds_exactly_one_exit_stack(self):
        made = [node for node in ast.walk(_lifespan_tree())
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "AsyncExitStack"]
        assert len(made) == 1, f"AsyncExitStack is built {len(made)} times"

    def test_the_lifespan_holds_no_try_finally(self):
        """The stack owns the teardown, so a `finally` here would be a second owner of it."""
        blocks = [node.lineno for node in ast.walk(_function_named(_lifespan_tree(), "lifespan"))
                  if isinstance(node, ast.Try) and node.finalbody]
        assert blocks == [], f"lifespan holds a try/finally at line(s) {blocks}"

    def test_dispose_is_registered_before_the_reachability_probe(self):
        """A probe that raises must still dispose the pool the engine already opened."""
        lines = _first_call_lines(_function_named(_lifespan_tree(), "build_session_factory"))
        assert lines["push_async_callback"] < lines["_prove_database_reachable"]

    def test_the_shutdown_log_is_the_first_statement_of_the_stack(self):
        """Registered first, so it runs last."""
        first = _lifespan_with_body()[0]
        assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
        call = first.value
        assert isinstance(call.func, ast.Attribute) and call.func.attr == "callback"
        logged, event = call.args
        assert isinstance(logged, ast.Attribute) and _dotted(logged) == "logger.info"
        assert isinstance(event, ast.Constant) and event.value == "shutdown"

    def test_each_runtime_field_has_a_builder_of_its_own_name(self):
        defined = {node.name for node in ast.walk(_lifespan_tree())
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert set(FIELD_BUILDERS) <= defined, f"missing builders: {set(FIELD_BUILDERS) - defined}"
        assert {name.removeprefix("build_") for name in FIELD_BUILDERS} <= \
            {field.name for field in fields(Runtime)}

    def test_the_two_boot_fatal_builders_run_before_the_degraded_tolerant_ones(self):
        """A pod that cannot verify an identity token never reaches the point of building a store reader."""
        lines = _first_call_lines(_function_named(_lifespan_tree(), "lifespan"))
        missing = [name for name in BOOT_FATAL_BUILDERS + DEGRADED_TOLERANT_BUILDERS
                   if name not in lines]
        assert missing == [], f"not called in lifespan: {missing}"
        assert max(lines[name] for name in BOOT_FATAL_BUILDERS) < \
            min(lines[name] for name in DEGRADED_TOLERANT_BUILDERS)

    def test_the_only_warnings_are_the_three_absent_ones(self):
        """The two warm-up warnings went with the retry, and no builder gained a new one."""
        assert _warning_events() == ABSENT_WARNINGS


def _recording_lifespan(monkeypatch, order: list[str]) -> None:
    """Point every builder at a stand-in that records its own teardown, one of which raises."""
    config = MagicMock()
    config.examples = {"en": "example"}
    monkeypatch.setattr(lifespan_module, "EnvironmentConfig",
                        lambda: SimpleNamespace(app_config=config))
    monkeypatch.setattr(lifespan_module, "setup_logging", lambda **_fields: None)
    monkeypatch.setattr(lifespan_module, "logger",
                        SimpleNamespace(info=lambda event, **_fields: order.append(event)))
    monkeypatch.setattr(lifespan_module, "LLMService", lambda **_fields: MagicMock())

    def note(name):
        async def _note():
            order.append(name)
        return _note

    async def boom():
        order.append("devicecheck_boom")
        raise RuntimeError("teardown failed")

    @asynccontextmanager
    async def closing(name):
        yield MagicMock()
        order.append(name)

    async def session_factory(_db, stack):
        stack.push_async_callback(note("dispose"))
        return MagicMock()

    def firebase_adapter(_jwt, stack):
        stack.callback(order.append, "firebase_delete")
        return MagicMock()

    async def devicecheck_adapter(_devicecheck, stack):
        stack.push_async_callback(boom)
        return MagicMock()

    async def play_notifications(_play, stack):
        return await stack.enter_async_context(closing("play_close"))

    monkeypatch.setattr(lifespan_module, "build_session_factory", session_factory)
    monkeypatch.setattr(lifespan_module, "build_jwt_verifier", lambda _jwt: MagicMock())
    monkeypatch.setattr(lifespan_module, "build_firebase_adapter", firebase_adapter)
    monkeypatch.setattr(lifespan_module, "build_devicecheck_adapter", devicecheck_adapter)
    monkeypatch.setattr(lifespan_module, "build_app_store_notifications", lambda _store: MagicMock())
    monkeypatch.setattr(lifespan_module, "build_google_play_notifications", play_notifications)


class TestATeardownThatRaisesStopsNoOtherTeardown:
    """Criterion 3, measured rather than inferred from the deleted logging. The stand-ins register
    the same three ways the builders do: a callback, an async callback and an entered context."""

    async def test_every_remaining_callback_runs_and_the_failure_propagates(self, monkeypatch):
        order: list[str] = []
        app = FastAPI()
        _recording_lifespan(monkeypatch, order)

        with pytest.raises(RuntimeError, match="teardown failed"):
            async with lifespan_module.lifespan(app):
                assert isinstance(app.state.runtime, Runtime)
                order.append("serving")

        assert order == ["started", "serving", "play_close", "devicecheck_boom",
                         "firebase_delete", "dispose", "shutdown"]


class TestTheSignOutRouteOpensNoSession:
    """D-04. The revocation writes no row and reads no table, so the handler declares no session."""

    def test_sign_out_all_declares_no_database_session(self):
        # `_flattened` walks sub-dependencies, so a session taken through a service is visible here.
        assert get_db not in _flattened(_route_at("/auth/sign-out-all"))


class TestOnlyTheSignOutRouteReachesTheContainer:
    """Criterion 5, D-05. `_declared`, never `_flattened`: after this phase every route reaches
    `get_runtime` under `get_db` or `get_claims`, so a flattened walk would pass for all of them."""

    def test_sign_out_all_declares_the_container(self):
        assert get_runtime in _declared(_route_at("/auth/sign-out-all"))

    def test_no_other_route_declares_the_container(self):
        reaching = [route.path for route in _api_routes()
                    if route.path != "/auth/sign-out-all"
                    and get_runtime in _declared(route)]
        assert reaching == [], f"routes declaring the whole container: {reaching}"


class TestTheContainerIsTheOneUntypedRead:
    """Criterion 5, counted over the source. `get_claims` keeps its `Request` for the
    authorization header alone, which is why the literal above names two functions, not one."""

    def test_the_module_holds_exactly_one_app_state_chain(self):
        chains = _app_state_chains()
        assert len(chains) == 1, f"{APP_STATE_CHAIN} is read {len(chains)} times"

    def test_the_one_chain_sits_inside_get_runtime(self):
        reading = [function.name for function in _dependency_functions()
                   for node in ast.walk(function)
                   if isinstance(node, ast.Attribute) and _dotted(node) == APP_STATE_CHAIN]
        assert reading == ["get_runtime"], f"functions reading {APP_STATE_CHAIN}: {reading}"

    def test_only_those_two_functions_declare_a_request(self):
        """A dependency that takes a `Request` can reach `app.state` without declaring the container."""
        declaring = {function.name for function in _dependency_functions()
                     for argument in (function.args.posonlyargs + function.args.args
                                      + function.args.kwonlyargs)
                     if isinstance(argument.annotation, ast.Name)
                     and argument.annotation.id == "Request"}
        assert declaring == REQUEST_DECLARING_FUNCTIONS, \
            f"functions declaring a Request: {sorted(declaring)}"


class TestNoTestSetsALifespanAttributeOnAppState:
    """Criterion 6, walked over every file under `tests/`. The field names are read off the
    container, so renaming a field cannot carry an assignment past this case."""

    def test_no_container_field_is_assigned_through_state(self):
        offenders = _state_assignments({field.name for field in fields(Runtime)})
        assert offenders == [], f"tests setting a lifespan-built attribute: {offenders}"

    def test_opened_sessions_is_still_assigned_that_way_control(self):
        """The control: without it, a walk that matched nothing anywhere would also pass above."""
        assert _state_assignments({"opened_sessions"}) != [], \
            "opened_sessions is set on app.state by no test, so the case above measures nothing"


class TestTheProviderCallbackPartition:
    """Membership is the set of routes on the webhooks router, counted here against one literal."""

    def test_the_partition_is_exactly_the_routes_on_the_webhooks_router(self):
        from nativespeaker.api.routers import webhooks_router

        assert {route.path for route in webhooks_router.routes} == PROVIDER_CALLBACK_PATHS

    @pytest.mark.parametrize("path,verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.items()))
    def test_each_callback_route_declares_its_own_verifier_and_neither_identity(self, path, verifier):
        """Its own, not any: one route declaring the other's verifier would pass a shared-name case."""
        calls = _declared(_route_at(path))
        assert verifier in calls
        assert get_claims not in calls
        assert get_identity not in calls

    @pytest.mark.parametrize("verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.values(),
                                                key=lambda call: call.__name__))
    def test_no_route_outside_the_partition_declares_any_callback_verifier(self, verifier):
        leaked = [route.path for route in _api_routes()
                  if route.path not in PROVIDER_CALLBACK_PATHS
                  and verifier in _declared(route)]
        assert leaked == [], f"routes declaring a callback verifier off the partition: {leaked}"

    @pytest.mark.parametrize("path,verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.items()))
    def test_the_verifier_is_the_routes_first_declared_dependency(self, path, verifier):
        """D-02. A reordered parameter list is what this catches, and it costs a connection per junk request."""
        assert _route_at(path).dependant.dependencies[0].call is verifier

    @pytest.mark.parametrize("path,verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.items()))
    def test_the_verifier_resolves_before_any_session_is_taken(self, path, verifier):
        """D-02. `get_db` is a sub-dependency, so the order is read off the flattened resolution walk."""
        order = _flattened(_route_at(path))
        assert order.index(verifier) < order.index(get_db)

    def test_the_partition_is_disjoint_from_both_other_literals(self):
        """A callback path in either exemption set would make the three literals disagree silently."""
        assert PROVIDER_CALLBACK_PATHS & (PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS) == set()


class TestDocumentationRoutes:
    """No unauthenticated schema dump; these are registered on `app.router`, so they carry no router dependency."""

    def test_no_documentation_route_is_registered(self):
        registered_paths = {r.path for r in real_app.routes}
        assert registered_paths & DOC_PATHS == set()

    def test_openapi_is_still_generatable_as_a_method_call(self):
        """openapi_url=None removes the route, not the schema -- tests still introspect it."""
        assert "ErrorResponse" in real_app.openapi()["components"]["schemas"]


class TestRedirectSlashes:
    """The trailing-slash 307 is produced before any route's dependencies run."""

    def test_redirect_slashes_is_disabled(self):
        assert real_app.router.redirect_slashes is False


class TestTheAuthDependencyIsResolvedOncePerRequest:
    """One verify and one identity query, counted across both declaration levels and the context beneath."""

    def test_one_verify_and_one_query_for_a_doubly_declared_route(self):
        from uuid import uuid7

        from fastapi import APIRouter, FastAPI
        from fastapi.testclient import TestClient

        from nativespeaker.api.app.error_handlers import register_exception_handlers
        from nativespeaker.api.auth.jwt_verifier import VerifiedClaims
        from nativespeaker.api.schemas.auth import LinkedIdentity
        from nativespeaker.api.tables.identities import (
            ExternalIdentity,
            IdentityProvider,
            IdentityState,
        )
        from nativespeaker.api.tables.users import User
        from unit.conftest import TEST_ISSUER, make_test_verifier, make_token

        subject = "cache-contract-subject"
        counts = {"verify": 0, "query": 0}

        user = User(id=uuid7(), active=True)
        identity = ExternalIdentity(id=uuid7(), user_id=user.id, issuer=TEST_ISSUER,
                                    subject=subject, provider=IdentityProvider.google,
                                    provider_uid="g-1", identity_state=IdentityState.active)

        class _Result:
            def first(self):
                return identity, user

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def exec(self, _statement):
                counts["query"] += 1
                return _Result()

        class _CountingVerifier:
            def __init__(self):
                self._inner = make_test_verifier()

            def verify(self, token):
                counts["verify"] += 1
                return self._inner.verify(token)

        app = FastAPI()
        register_exception_handlers(app)
        router = APIRouter(dependencies=[Depends(get_identity)])

        @router.get("/chats/{chat_id}")
        async def _handler(chat_id: str,
                           linked: LinkedIdentity = Depends(get_identity),
                           admitted: VerifiedClaims = Depends(get_claims)):
            return {"resolved_user": str(linked.user.id), "subject": admitted.subject}

        app.include_router(router)
        app.state.runtime = make_runtime(jwt_verifier=_CountingVerifier(), session_factory=_Session)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/chats/0199a0d0-0000-7000-8000-000000000000",
                              headers={"Authorization": f"Bearer {make_token(sub=subject)}"})

        assert response.status_code == 200, response.json()
        assert counts["verify"] == 1, f"the JWT was verified {counts['verify']} times"
        assert counts["query"] == 1, f"identity was resolved {counts['query']} times"
        # Each declaration's own output, so a resolution of anything but the token's subject fails here.
        assert response.json() == {"resolved_user": str(user.id), "subject": subject}
