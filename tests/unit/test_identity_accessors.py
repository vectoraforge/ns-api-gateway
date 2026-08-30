"""The two identity accessors, driven over real routers: what each one admits and what each one refuses."""
import inspect
from typing import get_type_hints
from uuid import uuid7

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.dependencies import (
    get_identity,
    get_linked_identity,
)
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.identity import Identity
from nativespeaker.api.tables.identities import (
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    NativeClaimProvider,
)
from nativespeaker.api.tables.users import User
from unit.conftest import TEST_ISSUER, make_test_verifier, make_token

ACCESSORS = (get_identity, get_linked_identity)
ISSUER = TEST_ISSUER
SUBJECT = "firebase-uid-1"

# A field name matching any of these would be a client address sneaking onto the identity.
_ADDRESS_MARKERS = ("addr", "remote", "host", "forwarded", "xff", "peer")


def _linked() -> Identity:
    """A linked identity over the real model classes -- no mock stands in for the resolved rows."""
    user, identity = _rows()
    return Identity(issuer=ISSUER, subject=SUBJECT, user=user, identity=identity)


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


def _unlinked() -> Identity:
    return Identity(issuer=ISSUER, subject=SUBJECT)


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

    admit_router = APIRouter(dependencies=[Depends(get_identity)])
    linked_router = APIRouter(dependencies=[Depends(get_linked_identity)])

    @admit_router.get("/admitted")
    async def _admitted(identity: Identity = Depends(get_identity)):
        return {"linked": identity.user is not None}

    @linked_router.get("/linked")
    async def _linked_route(identity: Identity = Depends(get_linked_identity)):
        return {"user_id": str(identity.user.id)}

    app.include_router(admit_router)
    app.include_router(linked_router)

    # Read per request by the dependency, exactly as the real lifespan supplies them.
    app.state.jwt_verifier = make_test_verifier()
    app.state.session_factory = lambda: _ProbeSession(row)
    return TestClient(app, raise_server_exceptions=False)


def _bearer(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


class TestNoCredentialIsRefused:
    """A route declaring either accessor refuses a caller who presented nothing."""

    @pytest.mark.parametrize("path", ["/admitted", "/linked"])
    def test_no_authorization_header_answers_auth_required(self, path):
        response = _client().get(path)
        assert response.status_code == 401
        body = response.json()
        assert list(body.keys()) == ["code"]
        assert body["code"] == "auth_required"

    @pytest.mark.parametrize("path", ["/admitted", "/linked"])
    def test_an_unverifiable_token_answers_auth_required(self, path):
        response = _client().get(path, headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    def test_a_refused_request_never_reaches_the_identity_query(self):
        """Step 3 refuses before step 4, so no session is opened for an unverifiable token."""
        _client().get("/linked", headers={"Authorization": "Bearer not.a.jwt"})
        assert _ProbeSession.instances == []


class TestTheNarrowingHoldsInBothDirections:
    """With the type split gone, this is where D-02's narrowing is asserted at the accessor level."""

    def test_an_unlinked_caller_on_a_linked_route_answers_403(self):
        """The replacement for the deleted type guarantee: the declaration is what refuses the read."""
        response = _client(row=None).get("/linked", headers=_bearer())
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    def test_a_linked_caller_reaches_a_linked_route(self):
        """The negative cases mean nothing unless the positive hand-off actually works."""
        user, identity = _rows()
        response = _client(row=(identity, user)).get("/linked", headers=_bearer())
        assert response.status_code == 200
        assert response.json() == {"user_id": str(user.id)}

    def test_an_unlinked_caller_on_an_admitting_route_is_admitted(self):
        """The other direction of D-02's narrowing: get_identity is what create-user declares."""
        response = _client(row=None).get("/admitted", headers=_bearer())
        assert response.status_code == 200
        assert response.json() == {"linked": False}

    def test_a_linked_caller_on_an_admitting_route_is_admitted_too(self):
        user, identity = _rows()
        response = _client(row=(identity, user)).get("/admitted", headers=_bearer())
        assert response.status_code == 200
        assert response.json() == {"linked": True}


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
        # No member describes this any more: the extractor owned the three the framework replaced.
        ({}, None),
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
        _client().get("/linked", headers={"Authorization": "Bearer not.a.jwt"})
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

    @pytest.mark.parametrize("path", ["/admitted", "/linked"])
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
        """The narrowing accessor takes the resolved identity, which is what puts it on the cache."""
        assert list(inspect.signature(get_identity).parameters) == ["request", "credential"]
        params = list(inspect.signature(get_linked_identity).parameters)
        assert params == ["identity"], f"get_linked_identity takes {params}, not the identity"

    @pytest.mark.parametrize("accessor", ACCESSORS, ids=lambda f: f.__name__)
    def test_accessor_is_asynchronous(self, accessor):
        """Both await resolution now, so FastAPI must not hand them to the threadpool."""
        assert inspect.iscoroutinefunction(accessor)

    @pytest.mark.parametrize("path", ["/admitted", "/linked"])
    def test_the_declaration_resolves_once(self, path):
        """One session across both declarations; an accessor calling rather than declaring ran everything twice."""
        user, identity = _rows()
        _client(row=(identity, user)).get(path, headers=_bearer())
        assert len(_ProbeSession.instances) == 1, "resolution ran more than once"
        session = _ProbeSession.instances[0]
        assert len(session.statements) == 1, "resolution issues exactly one statement per request"
        assert session.closed, "the session closes before the handler runs"


class TestTheIdentityShape:
    """The one class's field set, which later phases import verbatim."""

    def test_the_identity_carries_the_verified_pair_and_the_two_nullable_rows(self):
        assert sorted(Identity.__dataclass_fields__) == ["identity", "issuer", "subject", "user"]

    def test_unlinked_is_both_row_fields_none_together(self):
        """There is no tag to misread: nullability is the whole distinction the store branches on."""
        identity = _unlinked()
        assert identity.user is None
        assert identity.identity is None
        for absent in ("kind", "provider", "provider_uid", "user_id"):
            assert not hasattr(identity, absent)

    def test_linked_carries_both_rows(self):
        identity = _linked()
        assert identity.user is not None
        assert identity.identity is not None

    def test_the_identity_is_frozen_and_slotted(self):
        assert Identity.__dataclass_params__.frozen
        assert "__slots__" in Identity.__dict__

    def test_a_frozen_identity_cannot_be_relinked(self):
        with pytest.raises(Exception):
            _unlinked().user = _rows()[0]  # ty: ignore[invalid-assignment]

    def test_the_linked_classifier_is_the_stored_provider_column(self):
        """The sole per-request classifier is read off the resolved row, not off a claim."""
        identity = _linked()
        assert identity.identity.provider is IdentityProvider.google
        assert not hasattr(identity, "provider"), "an identity-level provider would compete with the column"


class TestNoClientAddressIsCarried:
    """No client address in any form, since deriving trust from one would assume rather than prove it."""

    def test_no_field_name_reads_as_an_address(self):
        cls = Identity
        for name in cls.__dataclass_fields__:
            offenders = [m for m in _ADDRESS_MARKERS if m in name]
            assert not offenders, f"{cls.__name__}.{name} looks like an address field ({offenders})"

    def test_the_only_string_fields_are_the_verified_pair(self):
        """An address would arrive as a str, so the two verified values are the whole allowance."""
        strings = {name for name, hint in get_type_hints(Identity).items() if hint is str}
        assert strings == {"issuer", "subject"}, f"unexpected str field(s) on Identity: {strings}"


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
