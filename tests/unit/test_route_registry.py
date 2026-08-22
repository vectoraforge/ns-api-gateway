"""FOUND-03: the §2.3 startup route-enumeration assertion, one test per failure condition.

Pure unit tests -- no database, no network, no e2e marker. The negative cases are built against
throwaway FastAPI instances with routes added inline and hand-built RouteMetadata tuples, so each
condition is exercised in isolation rather than by mutating the real REGISTRY.
"""
import pytest
from fastapi import FastAPI
from starlette.applications import Starlette

from nativespeaker.api.app.main import app as real_app
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.auth.registry import (
    REGISTRY,
    Category,
    NamedVerifier,
    RouteMetadata,
    assert_route_enumeration,
    enumerate_registered,
    lookup,
)
from nativespeaker.api.models.auth import AuthOperation
from nativespeaker.api.routers.chats import create_chat

CONFIGURED = {"apple_jws": NamedVerifier(name="apple_jws", configured=True)}
UNCONFIGURED = {"apple_jws": NamedVerifier(name="apple_jws", configured=False)}


async def _endpoint():
    return {"ok": True}


def _app(*routes: tuple[str, str], barrier: bool = True, endpoint=None,
         dependencies: list | None = None) -> FastAPI:
    """A throwaway app carrying exactly the given (method, path) routes.

    `dependencies` is forwarded to every route this call adds, which is what lets condition 10's
    cases build a route that carries a quota wrapper. It defaults to `None`, the same default
    `add_api_route` already has, so every existing call site is unchanged. A case needing routes
    that differ in their dependencies adds the second one with `app.add_api_route` directly, the
    way `TestEnumerateRegistered` already does.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    for method, path in routes:
        app.add_api_route(path, endpoint or _endpoint, methods=[method], dependencies=dependencies)
    if barrier:
        app.add_middleware(AuthBarrierMiddleware)
    return app


def _fails_with(substring: str, app: FastAPI, registry: tuple[RouteMetadata, ...], **kwargs) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        assert_route_enumeration(app, registry, **kwargs)
    assert substring in str(excinfo.value)


class TestAssertionPasses:
    def test_real_app_registry_matches_the_real_router(self):
        """The shipped REGISTRY is set-equal to what the real app registers."""
        assert_route_enumeration(real_app)

    def test_result_is_order_independent(self):
        """§2.3 compares (method, path) sets, so declaration order cannot change the outcome."""
        assert_route_enumeration(real_app, tuple(reversed(REGISTRY)))

    def test_zero_routes_and_zero_entries_pass(self):
        """Set equality holds vacuously: an app with no routes and an empty registry passes."""
        assert_route_enumeration(_app(), ())

    def test_lookup_returns_declared_metadata_or_none(self):
        assert lookup("GET", "/health/ready") is not None
        assert lookup("GET", "/health/ready").category is Category.public
        assert lookup("GET", "/") is not None
        assert lookup("GET", "/").category is Category.authenticated
        assert lookup("GET", "/no-such-route") is None


class TestCondition1UndeclaredRegisteredRoute:
    def test_registered_route_absent_from_the_registry_raises(self):
        _fails_with("registered but undeclared", _app(("GET", "/orphan")), ())

    def test_message_names_the_undeclared_pair(self):
        with pytest.raises(RuntimeError) as excinfo:
            assert_route_enumeration(_app(("GET", "/orphan")), ())
        assert "'GET'" in str(excinfo.value)
        assert "'/orphan'" in str(excinfo.value)


class TestCondition2DeclaredButUnregisteredRoute:
    def test_declared_entry_with_no_registered_route_raises(self):
        registry = (RouteMetadata(method="GET", path="/phantom", category=Category.authenticated),)
        _fails_with("declared but unregistered", _app(), registry)

    def test_both_directions_are_reported_as_separately_labelled_lines(self):
        """The reverted implementation checked only direction 1; both must be named, separately."""
        registry = (RouteMetadata(method="GET", path="/declared-only", category=Category.authenticated),)
        with pytest.raises(RuntimeError) as excinfo:
            assert_route_enumeration(_app(("GET", "/registered-only")), registry)
        message = str(excinfo.value)
        undeclared = [line for line in message.splitlines() if "registered but undeclared" in line]
        unregistered = [line for line in message.splitlines() if "declared but unregistered" in line]
        assert len(undeclared) == 1
        assert len(unregistered) == 1
        assert undeclared[0] is not unregistered[0]


class TestCondition3MultipleCategories:
    def test_same_method_and_path_declared_twice_raises(self):
        registry = (
            RouteMetadata(method="GET", path="/dup", category=Category.authenticated),
            RouteMetadata(method="GET", path="/dup", category=Category.public),
        )
        _fails_with("duplicate registry entry", _app(("GET", "/dup")), registry)

    def test_byte_identical_duplicate_entries_raise(self):
        """Two entries that agree on every field are still two entries for one (method, path)."""
        entry = RouteMetadata(method="GET", path="/dup", category=Category.authenticated)
        _fails_with("duplicate registry entry", _app(("GET", "/dup")), (entry, entry))


class TestCondition4ProviderCallbackVerifier:
    def test_named_verifier_none_raises(self):
        registry = (RouteMetadata(method="POST", path="/cb", category=Category.provider_callback),)
        _fails_with("declares named_verifier=None", _app(("POST", "/cb")), registry,
                    verifiers=CONFIGURED)

    def test_unregistered_verifier_raises(self):
        registry = (RouteMetadata(method="POST", path="/cb", category=Category.provider_callback,
                                  named_verifier="nope"),)
        _fails_with("is not registered", _app(("POST", "/cb")), registry, verifiers=CONFIGURED)

    def test_named_verifier_on_a_non_callback_route_raises(self):
        registry = (RouteMetadata(method="GET", path="/a", category=Category.authenticated,
                                  named_verifier="apple_jws"),)
        _fails_with("not provider_callback", _app(("GET", "/a")), registry, verifiers=CONFIGURED)


class TestCondition5MissingVerifierConfiguration:
    def test_registered_but_unconfigured_verifier_raises(self):
        registry = (RouteMetadata(method="POST", path="/cb", category=Category.provider_callback,
                                  named_verifier="apple_jws"),)
        _fails_with("lacks required configuration", _app(("POST", "/cb")), registry,
                    verifiers=UNCONFIGURED)

    def test_configured_verifier_passes(self):
        registry = (RouteMetadata(method="POST", path="/cb", category=Category.provider_callback,
                                  named_verifier="apple_jws"),)
        assert_route_enumeration(_app(("POST", "/cb")), registry, verifiers=CONFIGURED)


class TestCondition6IllegalPreAuthDeclaration:
    def test_preauth_callable_outside_create_user_raises(self):
        registry = (RouteMetadata(method="GET", path="/", category=Category.authenticated,
                                  preauth_callable=True),)
        _fails_with("illegal preauth_callable declaration", _app(("GET", "/")), registry)

    def test_preauth_callable_on_create_user_passes(self):
        registry = (RouteMetadata(method="POST", path="/auth/create-user",
                                  category=Category.authenticated,
                                  operation=AuthOperation.create_user,
                                  preauth_callable=True),)
        assert_route_enumeration(_app(("POST", "/auth/create-user")), registry)


class TestCondition7IllegalChallengeDeclaration:
    def test_challenge_bearing_without_an_operation_raises(self):
        registry = (RouteMetadata(method="GET", path="/a", category=Category.authenticated,
                                  challenge_bearing=True),)
        _fails_with("illegal challenge_bearing declaration", _app(("GET", "/a")), registry)

    def test_challenge_bearing_on_a_non_challenge_operation_raises(self):
        registry = (RouteMetadata(method="POST", path="/a", category=Category.authenticated,
                                  operation=AuthOperation.sync, challenge_bearing=True),)
        _fails_with("illegal challenge_bearing declaration", _app(("POST", "/a")), registry)

    def test_challenge_bearing_on_a_challenge_operation_passes(self):
        registry = (RouteMetadata(method="POST", path="/a", category=Category.authenticated,
                                  operation=AuthOperation.claim_anonymous_grant,
                                  challenge_bearing=True),)
        assert_route_enumeration(_app(("POST", "/a")), registry)


class TestCondition8OperationMappingErrors:
    def test_operation_outside_the_enum_raises(self):
        registry = (RouteMetadata(method="POST", path="/a", category=Category.authenticated,
                                  operation="not_an_operation"),)  # type: ignore[invalid-argument-type]
        _fails_with("is not a core.auth_operation value", _app(("POST", "/a")), registry)

    def test_one_operation_mapped_by_two_routes_raises(self):
        registry = (
            RouteMetadata(method="POST", path="/a", category=Category.authenticated,
                          operation=AuthOperation.sync),
            RouteMetadata(method="POST", path="/b", category=Category.authenticated,
                          operation=AuthOperation.sync),
        )
        _fails_with("is mapped by two routes", _app(("POST", "/a"), ("POST", "/b")), registry)

    def test_operation_on_a_public_route_raises(self):
        registry = (RouteMetadata(method="POST", path="/a", category=Category.public,
                                  operation=AuthOperation.sync),)
        _fails_with("not authenticated", _app(("POST", "/a")), registry)

    def test_operation_on_a_provider_callback_route_raises(self):
        registry = (RouteMetadata(method="POST", path="/cb", category=Category.provider_callback,
                                  named_verifier="apple_jws", operation=AuthOperation.sync),)
        _fails_with("not authenticated", _app(("POST", "/cb")), registry, verifiers=CONFIGURED)


class TestCondition9AuthenticatedRouteOutsideTheBarrier:
    def test_app_without_the_barrier_raises(self):
        registry = (RouteMetadata(method="GET", path="/a", category=Category.authenticated),)
        _fails_with("AuthBarrierMiddleware is absent",
                    _app(("GET", "/a"), barrier=False), registry)


# Condition 10 keys on the handler that consumes the allowance, so a route "carries quota" by
# being served by `create_chat` -- not by carrying a decorator dependency (REBIND-06).
QUOTA_ENDPOINT = {"endpoint": create_chat}


class TestCondition10QuotaFlagAndConsumingHandlerDisagree:
    """D-05: `quota_checked` is enforcement, not documentation.

    A route that declares the flag but is served by a handler that charges nothing serves every
    request free, and nothing about the served response says so. The cross-check is what turns
    that from an invisible defect into a boot failure, so it is checked in both directions.
    """

    def test_the_consuming_handler_and_quota_checked_together_pass(self):
        registry = (RouteMetadata(method="POST", path="/chats", category=Category.authenticated,
                                  quota_checked=True),)
        assert_route_enumeration(_app(("POST", "/chats"), **QUOTA_ENDPOINT), registry)

    def test_quota_checked_declared_with_no_consuming_handler_raises(self):
        registry = (RouteMetadata(method="POST", path="/chats", category=Category.authenticated,
                                  quota_checked=True),)
        _fails_with("quota_checked declared but no quota-consuming handler serves it",
                    _app(("POST", "/chats")), registry)

    def test_the_undeclared_handler_message_names_the_route(self):
        registry = (RouteMetadata(method="POST", path="/chats", category=Category.authenticated,
                                  quota_checked=True),)
        with pytest.raises(RuntimeError) as excinfo:
            assert_route_enumeration(_app(("POST", "/chats")), registry)
        assert "'POST'" in str(excinfo.value)
        assert "'/chats'" in str(excinfo.value)

    def test_a_consuming_handler_without_quota_checked_raises(self):
        """The other direction: the route charges, the registry does not say so."""
        registry = (RouteMetadata(method="POST", path="/chats", category=Category.authenticated),)
        _fails_with("quota-consuming handler serves a route where quota_checked is not declared",
                    _app(("POST", "/chats"), **QUOTA_ENDPOINT), registry)

    def test_the_unattached_quota_checked_message_names_the_route(self):
        registry = (RouteMetadata(method="POST", path="/chats", category=Category.authenticated),)
        with pytest.raises(RuntimeError) as excinfo:
            assert_route_enumeration(_app(("POST", "/chats"), **QUOTA_ENDPOINT),
                                     registry)
        assert "'POST'" in str(excinfo.value)
        assert "'/chats'" in str(excinfo.value)

    def test_both_quota_checked_disagreements_are_reported_in_one_error(self):
        """One raise lists everything, the way conditions 1 and 2 do -- never only the first."""
        app = _app(("POST", "/attached"), **QUOTA_ENDPOINT)
        app.add_api_route("/declared", _endpoint, methods=["POST"])
        registry = (
            RouteMetadata(method="POST", path="/attached", category=Category.authenticated),
            RouteMetadata(method="POST", path="/declared", category=Category.authenticated,
                          quota_checked=True),
        )
        with pytest.raises(RuntimeError) as excinfo:
            assert_route_enumeration(app, registry)
        message = str(excinfo.value)
        undeclared = [line for line in message.splitlines()
                      if "quota-consuming handler serves a route where quota_checked is not declared" in line]
        unattached = [line for line in message.splitlines()
                      if "quota_checked declared but no quota-consuming handler serves it" in line]
        assert len(undeclared) == 1
        assert len(unattached) == 1
        assert undeclared[0] is not unattached[0]

    def test_empty_input_adds_no_quota_checked_problem(self):
        """Backstop, not a derived requirement: REBIND-01 says nothing about empty input.

        Both directions are set differences, so empty-versus-empty must be a no-op rather than an
        error. Asserted here so a later rewrite that reaches for "at least one gated route" fails
        loudly instead of turning a fresh app's boot into a false alarm.
        """
        assert_route_enumeration(_app(), ())
        registry = (RouteMetadata(method="GET", path="/a", category=Category.authenticated),)
        assert_route_enumeration(_app(("GET", "/a")), registry)

    def test_the_quota_checked_message_is_byte_identical_across_runs(self):
        """`sorted()` on both differences, so the same disagreement never reads differently.

        Three routes rather than one: a single-element set cannot show the difference between an
        ordered emission and an accidental set iteration.
        """
        app = _app(("POST", "/a"), ("POST", "/b"), ("POST", "/c"))
        registry = tuple(RouteMetadata(method="POST", path=path,
                                       category=Category.authenticated, quota_checked=True)
                         for path in ("/a", "/b", "/c"))
        with pytest.raises(RuntimeError) as first:
            assert_route_enumeration(app, registry)
        with pytest.raises(RuntimeError) as second:
            assert_route_enumeration(app, registry)
        assert str(first.value) == str(second.value)


class TestEnumerateRegistered:
    def test_no_synthetic_head_for_a_get_only_route(self):
        """APIRoute.__init__ does not add HEAD; a synthesized entry becomes a phantom declaration."""
        registered, problems = enumerate_registered(_app(("GET", "/g")))
        assert registered == {("GET", "/g")}
        assert problems == []

    def test_mount_is_reported_as_a_problem(self):
        """Foundation registers no Mount, so one appearing is an unsupported registration."""
        app = _app()
        app.mount("/static", Starlette())
        registered, problems = enumerate_registered(app)
        assert registered == set()
        assert len(problems) == 1
        assert "unsupported route object registered" in problems[0]
        assert "Mount" in problems[0]

    def test_mount_fails_the_assertion(self):
        app = _app()
        app.mount("/static", Starlette())
        _fails_with("unsupported route object registered", app, ())

    def test_every_method_of_a_multi_method_route_is_enumerated(self):
        app = _app()
        app.add_api_route("/m", _endpoint, methods=["GET", "POST"])
        app.add_middleware(AuthBarrierMiddleware)
        registered, problems = enumerate_registered(app)
        assert registered == {("GET", "/m"), ("POST", "/m")}
        assert problems == []
