"""The typed identity context and the accessors that are admission: what the seam refuses, over real routers."""
import inspect
from datetime import UTC, datetime
from typing import get_type_hints
from uuid import uuid7

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_linked_identity,
    get_request_context,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.context import (
    IdentityKind,
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.tables.identities import (
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    NativeClaimProvider,
)
from nativespeaker.api.tables.users import User
from unit.conftest import TEST_ISSUER, make_test_verifier, make_token

ACCESSORS = (get_request_context, get_linked_identity)
ISSUER = TEST_ISSUER
SUBJECT = "firebase-uid-1"

# A field name matching any of these would be a client address sneaking back into the context.
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
    """The one short session the dependency opens: exactly one read, and every write verb raises."""

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
    """Two accessor-declaring routes over stubbed app state, each declaring its accessor at both levels."""
    _ProbeSession.instances.clear()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_exception_handlers(app)

    ctx_router = APIRouter(dependencies=[Depends(get_request_context)])
    linked_router = APIRouter(dependencies=[Depends(get_linked_identity)])

    @ctx_router.get("/ctx")
    async def _ctx(context: RequestContext = Depends(get_request_context)):
        return {"kind": context.identity.kind, "route": context.route}

    @linked_router.get("/linked")
    async def _linked_route(identity: LinkedIdentity = Depends(get_linked_identity)):
        return {"user_id": str(identity.user.id)}

    app.include_router(ctx_router)
    app.include_router(linked_router)

    # Read per request by the dependency, exactly as the real lifespan supplies them.
    app.state.jwt_verifier = make_test_verifier()
    app.state.session_factory = lambda: _ProbeSession(row)
    return TestClient(app, raise_server_exceptions=False)


def _bearer(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


class TestNoCredentialIsRefused:
    """A route declaring either accessor refuses a caller who presented nothing."""

    @pytest.mark.parametrize("path", ["/ctx", "/linked"])
    def test_no_authorization_header_answers_auth_required(self, path):
        response = _client().get(path)
        assert response.status_code == 401
        body = response.json()
        assert list(body.keys()) == ["code"]
        assert body["code"] == "auth_required"

    @pytest.mark.parametrize("path", ["/ctx", "/linked"])
    def test_an_unverifiable_token_answers_auth_required(self, path):
        response = _client().get(path, headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    def test_a_refused_request_never_reaches_the_identity_query(self):
        """Step 3 refuses before step 4, so no session is opened for an unverifiable token."""
        _client().get("/linked", headers={"Authorization": "Bearer not.a.jwt"})
        assert _ProbeSession.instances == []


class TestVariantConfusionIsRefused:
    """An accessor refuses the wrong variant rather than handing it over."""

    def test_a_preauth_caller_on_a_linked_route_answers_403(self):
        """Resolution admits a pre-auth principal everywhere and this accessor rejects it, so create-user reads it."""
        response = _client(row=None).get("/linked", headers=_bearer())
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    def test_a_linked_caller_reaches_a_linked_route(self):
        """The negative cases mean nothing unless the positive hand-off actually works."""
        user, identity = _rows()
        response = _client(row=(identity, user)).get("/linked", headers=_bearer())
        assert response.status_code == 200
        assert response.json() == {"user_id": str(user.id)}

    def test_get_request_context_accepts_either_variant(self):
        user, identity = _rows()
        assert _client(row=None).get("/ctx", headers=_bearer()).json()["kind"] == "preauth"
        assert _client(row=(identity, user)).get(
            "/ctx", headers=_bearer()).json()["kind"] == "linked"

    def test_the_context_carries_the_matched_path_template(self):
        """`RequestContext.route` is the route's declared template, read from the ASGI scope."""
        assert _client(row=None).get("/ctx", headers=_bearer()).json()["route"] == "/ctx"


class TestTheWireArmsRaiseAndTheHandlerRecordsThemOnce:
    """D-06's single-logging-site rule, asserted where a re-logging catch would show up as a second record."""

    @pytest.fixture
    def warnings(self, monkeypatch) -> list[tuple[str, dict]]:
        """A recording spy on the handler's own logger -- see 35-02's caching note on capture_logs."""
        entries: list[tuple[str, dict]] = []
        monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger.warning",
                            lambda event, **kw: entries.append((event, kw)))
        return entries

    @pytest.mark.parametrize("headers,expected_reason", [
        ({}, "missing_token"),
        # Well-formed on the wire -- one Bearer credential -- so this is the verifier's own reason.
        ({"Authorization": "Bearer not.a.jwt"}, "bad_signature"),
    ], ids=["absent-token", "failed-verify"])
    def test_each_arm_logs_one_record_naming_its_class_and_its_bounded_reason(
            self, headers, expected_reason, warnings):
        response = _client().get("/linked", headers=headers)

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
        assert len(warnings) == 1, f"expected exactly one record, got {warnings}"
        event, fields = warnings[0]
        assert event == "invalid_external_jwt"
        # D-03 dropped `route`, so the reason is now the only field the record carries.
        assert fields["bounded_reason"] == expected_reason
        assert set(fields) == {"bounded_reason", "exc_info"}

    def test_the_bounded_reason_is_logged_as_a_plain_string(self, warnings):
        """`BoundedReason` is a StrEnum; the field's type in the log pipeline does not change."""
        _client().get("/linked")
        _event, fields = warnings[0]
        assert type(fields["bounded_reason"]) is str

    def test_a_resolution_rejection_is_recorded_once_and_only_by_the_handler(self, warnings):
        """A thin re-logging catch anywhere between the raise and the handler would make this two."""
        response = _client(row=None).get("/linked", headers=_bearer())

        assert response.status_code == 403
        assert [name for name, _ in warnings] == ["pre_auth_identity_not_allowed"]

    def test_an_admitted_request_leaves_no_record_at_all(self, warnings):
        """The control: a spy that recorded nothing either way would pass every case above."""
        user, identity = _rows()
        response = _client(row=(identity, user)).get("/linked", headers=_bearer())

        assert response.status_code == 200
        assert warnings == []


class TestNeverReturnsNone:
    """No accessor has a path that yields None, which is the failure mode worth naming."""

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_no_accessor_declares_an_optional_return(self, accessor):
        annotation = get_type_hints(accessor)["return"]
        assert "None" not in str(annotation), f"{accessor.__name__} may return None"

    @pytest.mark.parametrize("path", ["/ctx", "/linked"])
    @pytest.mark.parametrize("header", [None, "", "Bearer", "Basic dXNlcjpwYXNz", "Bearer  "],
                             ids=["absent", "empty", "scheme-only", "wrong-scheme", "blank-token"])
    def test_no_failing_credential_shape_reaches_a_handler(self, path, header):
        """Whatever the credential looks like, a failure is an error body -- never a 2xx."""
        headers = {} if header is None else {"Authorization": header}
        response = _client().get(path, headers=headers)
        assert response.status_code == 401
        assert set(response.json()) == {"code"}


class TestAccessorsCannotProvision:
    """Exactly one read and no reachable write verb, asserted now that the accessors do open a session."""

    def test_only_the_resolving_accessor_takes_the_request(self):
        """The narrowing accessors take the resolved context, which is also what puts them on the cache."""
        assert list(inspect.signature(get_request_context).parameters) == ["request"]
        params = list(inspect.signature(get_linked_identity).parameters)
        assert params == ["context"], f"get_linked_identity takes {params}, not the context"

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_accessor_is_asynchronous(self, accessor):
        """Both await resolution now, so FastAPI must not hand them to the threadpool."""
        assert inspect.iscoroutinefunction(accessor)

    @pytest.mark.parametrize("path", ["/ctx", "/linked"])
    def test_the_declaration_resolves_once(self, path):
        """One session across both declarations; an accessor calling rather than declaring ran everything twice."""
        user, identity = _rows()
        _client(row=(identity, user)).get(path, headers=_bearer())
        assert len(_ProbeSession.instances) == 1, "resolution ran more than once"
        session = _ProbeSession.instances[0]
        assert len(session.statements) == 1, "resolution issues exactly one statement per request"
        assert session.closed, "the session closes before the handler runs"


class TestContextShape:
    """The field sets later phases import verbatim, so they are the contract."""

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
    """No client address in any form, since deriving trust from one would assume rather than prove it."""

    @pytest.mark.parametrize("cls", [LinkedIdentity, PreAuthIdentity, RequestContext],
                             ids=lambda c: c.__name__)
    def test_no_field_name_reads_as_an_address(self, cls):
        for name in cls.__dataclass_fields__:
            offenders = [m for m in _ADDRESS_MARKERS if m in name]
            assert not offenders, f"{cls.__name__}.{name} looks like an address field ({offenders})"

    @pytest.mark.parametrize("cls", [LinkedIdentity, PreAuthIdentity, RequestContext],
                             ids=lambda c: c.__name__)
    def test_the_only_string_fields_are_the_verified_pair_and_the_route_template(self, cls):
        """An address would arrive as a str, and the route is a declared template no caller can steer."""
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
