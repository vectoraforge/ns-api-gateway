"""FOUND-01: the §1.4 typed identity context and the fail-loudly `Depends()` accessors (D-02).

Pure unit tests -- no database, no network. The three accessors *are* admission now (37.1 D-06):
`get_request_context` applies the wire contract, verifies the token and resolves the identity, and
the other two narrow the variant it produced. So these cases drive real requests through real
routers with a real verifier over an ephemeral keypair, and stub only the two things the lifespan
would otherwise supply -- `app.state.jwt_verifier` and `app.state.session_factory`.

Every case here is still the inverse of the usual one: what the seam **refuses**, and that it never
hands a handler something it could read as anonymous. `test_auth_security.py` asserts the same seam
from the wire side.
"""
import inspect
from datetime import UTC, datetime
from typing import get_type_hints
from uuid import uuid7

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_linked_identity,
    get_preauth_identity,
    get_request_context,
)
from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.context import (
    IdentityKind,
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.models.identities import (
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    NativeClaimProvider,
)
from nativespeaker.api.models.users import User
from unit.conftest import TEST_ISSUER, make_test_verifier, make_token

ACCESSORS = (get_request_context, get_linked_identity, get_preauth_identity)
ISSUER = TEST_ISSUER
SUBJECT = "firebase-uid-1"

# The context carries no client address in any form (A3). Any field name matching one of these
# would be an address sneaking back in.
_ADDRESS_MARKERS = ("addr", "remote", "host", "forwarded", "xff", "peer")


def _linked() -> LinkedIdentity:
    """A linked variant over the real model classes -- no mock stands in for the resolved rows."""
    user, identity = _rows()
    return LinkedIdentity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)


def _rows() -> tuple[User, ExternalIdentity]:
    """The `(user, identity)` pair the single joined statement returns for a linked caller."""
    user = User(id=uuid7(), active=True)
    identity = ExternalIdentity(id=uuid7(),
                                user_id=user.id,
                                issuer=ISSUER,
                                subject=SUBJECT,
                                provider=IdentityProvider.google,
                                provider_uid="google-account-1",
                                identity_state=IdentityState.active)
    return user, identity


def _preauth() -> PreAuthIdentity:
    return PreAuthIdentity(issuer=ISSUER, subject=SUBJECT)


def _context(identity: LinkedIdentity | PreAuthIdentity) -> RequestContext:
    return RequestContext(identity=identity,
                          route="/chats",
                          evaluated_at=datetime.now(UTC),
                          attempt_id=uuid7())


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _ProbeSession:
    """The one short session the auth dependency opens: exactly one read, and never a write.

    Every write verb raises rather than recording. §1.4's no-provisioning prohibition used to be
    structural -- the accessors were synchronous and could not reach a session at all -- and
    `get_request_context` now opens one, so the prohibition needs asserting instead of assuming.
    A `create`, `link`, `repair` or `merge` on this path would have to come through one of these.
    """

    instances: list[_ProbeSession] = []

    def __init__(self, row):
        self._row = row
        self.statements: list[object] = []
        self.closed = False
        _ProbeSession.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        self.closed = True
        return False

    async def exec(self, statement):
        self.statements.append(statement)
        return _Result(self._row)

    async def commit(self):
        raise AssertionError("the auth dependency may not commit")

    async def flush(self):
        raise AssertionError("the auth dependency may not flush")

    def add(self, _instance):
        raise AssertionError("the auth dependency may not add a row")

    async def delete(self, _instance):
        raise AssertionError("the auth dependency may not delete a row")


def _client(row=None) -> TestClient:
    """Three accessor-declaring routes over stubbed app state.

    `row` is what the identity query finds: `None` resolves as a pre-auth caller, an
    `(identity, user)` pair as a linked one. Each router declares its accessor **and** each
    endpoint declares the identical callable again, which is the D-07 shape the real routers use.
    """
    _ProbeSession.instances.clear()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_exception_handlers(app)

    ctx_router = APIRouter(dependencies=[Depends(get_request_context)])
    linked_router = APIRouter(dependencies=[Depends(get_linked_identity)])
    preauth_router = APIRouter(dependencies=[Depends(get_preauth_identity)])

    @ctx_router.get("/ctx")
    async def _ctx(context: RequestContext = Depends(get_request_context)):
        return {"kind": context.identity.kind, "route": context.route}

    @linked_router.get("/linked")
    async def _linked_route(identity: LinkedIdentity = Depends(get_linked_identity)):
        return {"user_id": str(identity.user.id)}

    @preauth_router.get("/preauth")
    async def _preauth_route(identity: PreAuthIdentity = Depends(get_preauth_identity)):
        return {"subject": identity.subject}

    app.include_router(ctx_router)
    app.include_router(linked_router)
    app.include_router(preauth_router)

    # Read per request by the dependency, exactly as the real lifespan supplies them.
    app.state.jwt_verifier = make_test_verifier()
    app.state.session_factory = lambda: _ProbeSession(row)
    return TestClient(app, raise_server_exceptions=False)


def _bearer(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


class TestNoCredentialIsRefused:
    """§1.4: a route declaring any of the three refuses a caller who presented nothing."""

    @pytest.mark.parametrize("path", ["/ctx", "/linked", "/preauth"])
    def test_no_authorization_header_answers_auth_required(self, path):
        response = _client().get(path)
        assert response.status_code == 401
        body = response.json()
        assert list(body.keys()) == ["code"]
        assert body["code"] == "auth_required"

    @pytest.mark.parametrize("path", ["/ctx", "/linked", "/preauth"])
    def test_an_unverifiable_token_answers_auth_required(self, path):
        response = _client().get(path, headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    def test_a_refused_request_never_reaches_the_identity_query(self):
        """Step 3 refuses before step 4, so no session is opened for an unverifiable token."""
        _client().get("/linked", headers={"Authorization": "Bearer not.a.jwt"})
        assert _ProbeSession.instances == []


class TestVariantConfusionIsRefused:
    """T-35-03-02: an accessor refuses the wrong variant rather than handing it over."""

    def test_a_preauth_caller_on_a_linked_route_answers_403(self):
        """`preauth_identity_not_allowed`, not `auth_required` -- CREATE-01's client contract.

        This is the same answer, with the same status and the same body, that the deleted barrier
        produced for the same caller through `resolve_identity`'s non-pre-auth-callable arm. What
        moved is *where* the narrowing happens: resolution now admits a pre-auth principal on every
        route and this accessor rejects it, which is what lets `POST /auth/create-user` read the
        variant off the context.
        """
        response = _client(row=None).get("/linked", headers=_bearer())
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    def test_a_linked_caller_on_a_preauth_route_answers_401(self):
        user, identity = _rows()
        response = _client(row=(identity, user)).get("/preauth", headers=_bearer())
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    def test_a_linked_caller_reaches_a_linked_route(self):
        """The negative cases mean nothing unless the positive hand-off actually works."""
        user, identity = _rows()
        response = _client(row=(identity, user)).get("/linked", headers=_bearer())
        assert response.status_code == 200
        assert response.json() == {"user_id": str(user.id)}

    def test_a_preauth_caller_reaches_a_preauth_route(self):
        response = _client(row=None).get("/preauth", headers=_bearer())
        assert response.status_code == 200
        assert response.json() == {"subject": SUBJECT}

    def test_get_request_context_accepts_either_variant(self):
        user, identity = _rows()
        assert _client(row=None).get("/ctx", headers=_bearer()).json()["kind"] == "preauth"
        assert _client(row=(identity, user)).get(
            "/ctx", headers=_bearer()).json()["kind"] == "linked"

    def test_the_context_carries_the_matched_path_template(self):
        """`RequestContext.route` is the route's declared template, read from the ASGI scope."""
        assert _client(row=None).get("/ctx", headers=_bearer()).json()["route"] == "/ctx"


class TestNeverReturnsNone:
    """No accessor has a path that yields None -- the failure mode §1.4 names explicitly."""

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_no_accessor_declares_an_optional_return(self, accessor):
        annotation = get_type_hints(accessor)["return"]
        assert "None" not in str(annotation), f"{accessor.__name__} may return None"

    @pytest.mark.parametrize("path", ["/ctx", "/linked", "/preauth"])
    @pytest.mark.parametrize("header", [None, "", "Bearer", "Basic dXNlcjpwYXNz", "Bearer  "],
                             ids=["absent", "empty", "scheme-only", "wrong-scheme", "blank-token"])
    def test_no_failing_credential_shape_reaches_a_handler(self, path, header):
        """Whatever the credential looks like, a failure is an error body -- never a 2xx."""
        headers = {} if header is None else {"Authorization": header}
        response = _client().get(path, headers=headers)
        assert response.status_code == 401
        assert set(response.json()) == {"code"}


class TestAccessorsCannotProvision:
    """The no-provisioning prohibition: exactly one read, and no write verb is reachable.

    It used to be structural -- the accessors were synchronous and could not await a session at
    all. `get_request_context` opens one now, for §1.3's single statement, so the prohibition is
    asserted directly instead: `_ProbeSession` raises on `commit`, `flush`, `add` and `delete`, so
    a create, link, repair, reassign or merge appearing on this path fails these cases loudly.
    """

    def test_only_the_resolving_accessor_takes_the_request(self):
        """`get_request_context` needs app state; the two narrowing accessors must not have it.

        They take the resolved context instead, which is also what puts them on FastAPI's
        per-request cache -- see `test_the_declaration_resolves_once` below.
        """
        assert list(inspect.signature(get_request_context).parameters) == ["request"]
        for accessor in (get_linked_identity, get_preauth_identity):
            params = list(inspect.signature(accessor).parameters)
            assert params == ["context"], f"{accessor.__name__} takes {params}, not the context"

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_accessor_is_asynchronous(self, accessor):
        """All three await resolution now, so FastAPI must not hand them to the threadpool."""
        assert inspect.iscoroutinefunction(accessor)

    @pytest.mark.parametrize("path", ["/ctx", "/linked", "/preauth"])
    def test_the_declaration_resolves_once(self, path):
        """One session, one statement, closed before the handler -- across BOTH declarations.

        Each route here declares its accessor at the router level and again in the endpoint
        signature, and `/linked` and `/preauth` add a third resolution of `get_request_context`
        beneath them. A second `_ProbeSession` would mean the JWT verify and the identity query
        had run twice, which is what T-37.1-11 is about: an accessor that *called*
        `get_request_context(request)` instead of declaring it did exactly that, because the
        per-request cache lives in FastAPI's solver and cannot see a direct call.
        """
        user, identity = _rows()
        _client(row=(identity, user)).get(path, headers=_bearer())
        assert len(_ProbeSession.instances) == 1, "resolution ran more than once"
        session = _ProbeSession.instances[0]
        assert len(session.statements) == 1, "resolution issues exactly one statement per request"
        assert session.closed, "the session closes before the handler runs"


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
