"""FOUND-01: the §1.4 typed identity context and the fail-loudly `Depends()` accessors (D-02).

Pure unit tests -- no database, no network, no real barrier. Every case here is the inverse of the
usual one: a route registered outside the barrier has no identity context, and each accessor must
RAISE rather than hand a handler something it could read as anonymous. `test_auth_security.py`
wires the real dependency chain and asserts what it accepts; this file asserts what the seam
refuses.
"""
import inspect
from datetime import UTC, datetime
from typing import get_type_hints
from uuid import uuid7

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from nativespeaker.api.app.dependencies import (
    get_linked_identity,
    get_preauth_identity,
    get_request_context,
)
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.context import (
    REQUEST_CONTEXT_SCOPE_KEY,
    IdentityKind,
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.errors import AUTH_REQUIRED, AuthenticationError
from nativespeaker.api.models.identities import (
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    NativeClaimProvider,
)
from nativespeaker.api.models.users import User

ACCESSORS = (get_request_context, get_linked_identity, get_preauth_identity)
ISSUER = "https://securetoken.google.com/native-speaker"
SUBJECT = "firebase-uid-1"

# The context carries no client address in any form (A3). Any field name matching one of these
# would be an address sneaking back in.
_ADDRESS_MARKERS = ("addr", "remote", "host", "forwarded", "xff", "peer")


def _linked() -> LinkedIdentity:
    """A linked variant over the real model classes -- no mock stands in for the resolved rows."""
    user = User(id=uuid7(), active=True)
    identity = ExternalIdentity(id=uuid7(),
                                user_id=user.id,
                                issuer=ISSUER,
                                subject=SUBJECT,
                                provider=IdentityProvider.google,
                                provider_uid="google-account-1",
                                identity_state=IdentityState.active)
    return LinkedIdentity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)


def _preauth() -> PreAuthIdentity:
    return PreAuthIdentity(issuer=ISSUER, subject=SUBJECT)


def _context(identity: LinkedIdentity | PreAuthIdentity) -> RequestContext:
    return RequestContext(identity=identity,
                          route="/chats",
                          evaluated_at=datetime.now(UTC),
                          attempt_id=uuid7())


def _request(stash: object = None) -> Request:
    """A bare Request whose `state` carries `stash` under the context key, or nothing at all."""
    scope: dict = {"type": "http", "method": "GET", "path": "/chats", "headers": [], "state": {}}
    if stash is not None:
        scope["state"][REQUEST_CONTEXT_SCOPE_KEY] = stash
    return Request(scope)


def _stash_middleware(stash: object):
    """A stand-in for the barrier: writes one object to `scope["state"]` and dispatches.

    Deliberately pure-ASGI and deliberately writing the same key the barrier will (plan 06), so
    these tests exercise the real hand-off rather than a `dependency_overrides` shortcut that
    would prove nothing about where the context actually lives.
    """
    class _Stash:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})[REQUEST_CONTEXT_SCOPE_KEY] = stash
            await self.app(scope, receive, send)

    return _Stash


def _client(stash: object = None) -> TestClient:
    """An app with three accessor-consuming routes and NO barrier."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_exception_handlers(app)

    @app.get("/ctx")
    async def _ctx(context: RequestContext = Depends(get_request_context)):
        return {"kind": context.identity.kind}

    @app.get("/linked")
    async def _linked_route(identity: LinkedIdentity = Depends(get_linked_identity)):
        return {"user_id": str(identity.user.id)}

    @app.get("/preauth")
    async def _preauth_route(identity: PreAuthIdentity = Depends(get_preauth_identity)):
        return {"subject": identity.subject}

    if stash is not None:
        app.add_middleware(_stash_middleware(stash))
    return TestClient(app, raise_server_exceptions=False)


class TestAbsentContextRaises:
    """§1.4: reading the context where the barrier did not run raises -- never returns None."""

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_accessor_raises_when_state_is_empty(self, accessor):
        with pytest.raises(AuthenticationError):
            accessor(_request())

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_raised_class_is_auth_required(self, accessor):
        with pytest.raises(AuthenticationError) as exc:
            accessor(_request())
        assert exc.value.error_class is AUTH_REQUIRED
        assert exc.value.error_class.status == 401
        assert exc.value.error_class.code == "auth_required"

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_a_wrong_typed_stash_fails_closed_too(self, accessor):
        """A non-RequestContext under the key is as unusable as an absent one."""
        with pytest.raises(AuthenticationError):
            accessor(_request({"identity": "not-a-context"}))

    @pytest.mark.parametrize("path", ["/ctx", "/linked", "/preauth"])
    def test_route_outside_the_barrier_answers_auth_required(self, path):
        """The raised class resolves to the one 401 body -- the route is not silently open."""
        response = _client().get(path)
        assert response.status_code == 401
        body = response.json()
        assert list(body.keys()) == ["code"]
        assert body["code"] == "auth_required"


class TestVariantConfusionRaises:
    """T-35-03-02: an accessor raises on the wrong variant rather than returning it."""

    def test_get_linked_identity_raises_on_preauth(self):
        with pytest.raises(AuthenticationError) as exc:
            get_linked_identity(_request(_context(_preauth())))
        assert exc.value.error_class is AUTH_REQUIRED

    def test_get_preauth_identity_raises_on_linked(self):
        with pytest.raises(AuthenticationError) as exc:
            get_preauth_identity(_request(_context(_linked())))
        assert exc.value.error_class is AUTH_REQUIRED

    def test_get_linked_identity_returns_the_linked_variant(self):
        identity = _linked()
        assert get_linked_identity(_request(_context(identity))) is identity

    def test_get_preauth_identity_returns_the_preauth_variant(self):
        identity = _preauth()
        assert get_preauth_identity(_request(_context(identity))) is identity

    def test_get_request_context_accepts_either_variant(self):
        for identity in (_linked(), _preauth()):
            context = _context(identity)
            assert get_request_context(_request(context)) is context

    def test_preauth_caller_on_a_linked_route_answers_401_over_http(self):
        response = _client(_context(_preauth())).get("/linked")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    def test_linked_caller_on_a_preauth_route_answers_401_over_http(self):
        response = _client(_context(_linked())).get("/preauth")
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    def test_a_stashed_context_reaches_the_handler_over_http(self):
        """The negative cases above mean nothing unless the positive hand-off actually works."""
        identity = _linked()
        response = _client(_context(identity)).get("/linked")
        assert response.status_code == 200
        assert response.json() == {"user_id": str(identity.user.id)}


class TestNeverReturnsNone:
    """No accessor has a path that yields None -- the failure mode §1.4 names explicitly."""

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    @pytest.mark.parametrize("stash", [None, "garbage", 0], ids=["absent", "wrong-type", "falsy"])
    def test_no_accessor_returns_none_on_any_failing_stash(self, accessor, stash):
        try:
            result = accessor(_request(stash))
        except AuthenticationError:
            return
        assert result is not None

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_no_accessor_declares_an_optional_return(self, accessor):
        annotation = get_type_hints(accessor)["return"]
        assert "None" not in str(annotation), f"{accessor.__name__} may return None"


class TestAccessorsCannotWrite:
    """The no-provisioning prohibition, structurally: none of the three can reach a session."""

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_accessor_takes_only_the_request(self, accessor):
        params = list(inspect.signature(accessor).parameters)
        assert params == ["request"], f"{accessor.__name__} takes {params}, not just the Request"

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_accessor_is_synchronous(self, accessor):
        """A sync function cannot await a session: creating, linking, or repairing a row is
        unreachable from here, not merely absent."""
        assert not inspect.iscoroutinefunction(accessor)


class TestContextShape:
    """The §1.4 field sets. Phases 36-46 import these verbatim, so they are the contract."""

    def test_request_context_carries_exactly_the_four_request_scoped_values(self):
        assert sorted(RequestContext.__dataclass_fields__) == [
            "attempt_id", "evaluated_at", "identity", "route",
        ]

    def test_preauth_carries_the_verified_pair_and_nothing_else(self):
        """No user row, no identity row, no provider -- there is nothing to misread as linked."""
        assert sorted(PreAuthIdentity.__dataclass_fields__) == ["issuer", "kind", "subject"]
        identity = _preauth()
        for absent in ("user", "identity", "provider", "provider_uid", "user_id"):
            assert not hasattr(identity, absent)

    def test_linked_carries_both_rows_and_the_verified_pair(self):
        assert sorted(LinkedIdentity.__dataclass_fields__) == [
            "identity", "issuer", "kind", "subject", "user",
        ]

    @pytest.mark.parametrize("cls", [LinkedIdentity, PreAuthIdentity, RequestContext],
                             ids=lambda c: c.__name__)
    def test_every_context_dataclass_is_frozen_and_slotted(self, cls):
        assert cls.__dataclass_params__.frozen
        assert "__slots__" in cls.__dict__

    def test_the_kind_tags_discriminate_the_two_variants(self):
        assert _linked().kind is IdentityKind.linked
        assert _preauth().kind is IdentityKind.preauth
        assert sorted(m.value for m in IdentityKind) == ["linked", "preauth"]

    def test_a_frozen_variant_cannot_be_retagged(self):
        with pytest.raises(Exception):
            _preauth().kind = IdentityKind.linked  # ty: ignore[invalid-assignment]

    def test_the_linked_classifier_is_the_stored_provider_column(self):
        """The sole per-request classifier is read off the resolved row, not off a claim."""
        identity = _linked()
        assert identity.identity.provider is IdentityProvider.google
        assert not hasattr(identity, "provider"), "a context-level provider would compete with the column"


class TestNoClientAddressIsCarried:
    """A3 / T-35-03-04: no address at all. §9 is deferred, so one would be trusted, not proven."""

    @pytest.mark.parametrize("cls", [LinkedIdentity, PreAuthIdentity, RequestContext],
                             ids=lambda c: c.__name__)
    def test_no_field_name_reads_as_an_address(self, cls):
        for name in cls.__dataclass_fields__:
            offenders = [m for m in _ADDRESS_MARKERS if m in name]
            assert not offenders, f"{cls.__name__}.{name} looks like an address field ({offenders})"

    @pytest.mark.parametrize("cls", [LinkedIdentity, PreAuthIdentity, RequestContext],
                             ids=lambda c: c.__name__)
    def test_the_only_string_fields_are_the_verified_pair_and_the_route_template(self, cls):
        """An address would have to arrive as a str, so the str fields are an enumerated set.

        `route` is the third and last one. It is a **path template** the router declared, drawn
        from a closed set fixed at import time -- not a client-supplied value, and nothing a caller
        can steer. The verified pair is the other two.
        """
        strings = {name for name, hint in get_type_hints(cls).items() if hint is str}
        assert strings <= {"issuer", "subject", "route"}, \
            f"unexpected str field(s) on {cls.__name__}: {strings}"


class TestExternalIdentityModel:
    """`core.external_identities` as the migration declares it."""

    def test_columns_match_the_migration(self):
        assert sorted(ExternalIdentity.model_fields) == [
            "created_at", "free_grant_consumed_at", "historical_at", "id", "identity_state",
            "issuer", "native_claim_platform", "provider", "provider_uid", "subject",
            "updated_at", "user_id",
        ]

    def test_table_is_in_the_core_schema(self):
        assert ExternalIdentity.__table__.schema == "core"
        assert ExternalIdentity.__table__.name == "external_identities"

    def test_identity_state_has_exactly_two_values(self):
        """A third value would be a state the admission matrix has no ruling for."""
        assert [m.value for m in IdentityState] == ["active", "historical"]

    def test_identity_provider_mirrors_the_native_enum(self):
        assert [m.value for m in IdentityProvider] == ["anonymous", "google", "apple"]

    def test_native_claim_provider_mirrors_the_native_enum(self):
        assert [m.value for m in NativeClaimProvider] == ["ios_devicecheck", "android_play_integrity"]

    def test_identity_state_defaults_to_active(self):
        assert ExternalIdentity.model_fields["identity_state"].default is IdentityState.active

    def test_the_enums_bind_the_native_postgresql_types(self):
        """v1.6 convention: domain enums are native `core.*` types, never TEXT with a CHECK."""
        columns = ExternalIdentity.__table__.columns
        for column, name in (("provider", "identity_provider"),
                             ("identity_state", "identity_state"),
                             ("native_claim_platform", "native_claim_provider")):
            sa_type = columns[column].type
            assert sa_type.name == name
            assert sa_type.schema == "core"
