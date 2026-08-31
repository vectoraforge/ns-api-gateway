import subprocess
import sys
from typing import cast
from uuid import uuid7

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.jwt_verifier import BoundedReason
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import (
    BlockedUser,
    ChatHistoryLimitError,
    CircuitOpenError,
    DatabaseNotInitializedError,
    HistoricalIdentity,
    IdentityAlreadyLinked,
    InvalidChatError,
    InvalidCursorError,
    InvalidExternalJwt,
    NotLinked,
    OutOfScopeError,
    PageSizeLimitError,
    PermanentLLMError,
    QueueFullError,
    TransientLLMError,
    UnsupportedLanguageError,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.users import User

ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "subject-under-test"

CASES = [
    ("missing_token", InvalidExternalJwt(bounded_reason=None), 401),
    ("invalid_token", InvalidExternalJwt(bounded_reason=BoundedReason.bad_signature), 401),
    ("expired_token", InvalidExternalJwt(bounded_reason=BoundedReason.expired), 401),
    ("db_not_init", DatabaseNotInitializedError(), 500),
    ("unsupported_lang", UnsupportedLanguageError("fr", ["en"]), 400),
    ("invalid_chat", InvalidChatError("xyz"), 404),
    ("invalid_cursor", InvalidCursorError(), 400),
    ("page_size_limit", PageSizeLimitError(100), 400),
    ("queue_full", QueueFullError(30), 503),
    ("circuit_open", CircuitOpenError(60), 503),
    ("history_limit", ChatHistoryLimitError(max_messages=50), 400),
    ("out_of_scope", OutOfScopeError(), 400),
    ("generic_exception", Exception("boom"), 500),
    ("starlette_http", StarletteHTTPException(status_code=404, detail="not found"), 404),
    ("transient_llm", TransientLLMError("upstream timeout"), 503),
    ("permanent_llm", PermanentLLMError("bad response format"), 503),
]


# Each route name is the event name the handler must derive from the class, written out rather than
# re-derived with `camel_to_snake`.
REJECTION_CASES = [
    ("identity_already_linked", IdentityAlreadyLinked(), 409, "identity_already_linked"),
]

# The merged tree's arms, answered by `app_error_handler`. Each route name is the event name again.
APP_ERROR_CASES = [
    ("historical_identity", HistoricalIdentity(), 403, "account_unavailable"),
    ("blocked_user", BlockedUser(), 403, "account_unavailable"),
    ("not_linked", NotLinked(stage="provider_classification"), 403, "operation_not_allowed"),
]


class _Body(BaseModel):
    required_field: str


def _make_raise_route(exc: Exception):
    async def _route():
        raise exc

    return _route


class _WarningSpy:
    """A recording spy on the handler's own logger, so "which rejection, once" stays observable."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **kwargs) -> None:
        self.entries.append((event, kwargs))


@pytest.fixture
def warnings(monkeypatch) -> _WarningSpy:
    spy = _WarningSpy()
    monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger.warning", spy.record)
    return spy


@pytest.fixture(scope="module")
def handler_client():
    app = FastAPI()
    register_exception_handlers(app)

    for name, exc, _ in CASES:
        app.add_api_route(f"/raise/{name}", _make_raise_route(exc), methods=["GET"])

    for name, exc, _, _ in REJECTION_CASES:
        app.add_api_route(f"/reject/{name}", _make_raise_route(exc), methods=["GET"])

    for name, exc, _, _ in APP_ERROR_CASES:
        app.add_api_route(f"/fail/{name}", _make_raise_route(exc), methods=["GET"])

    @app.post("/validate-body")
    async def _validate_route(body: _Body):
        return body

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("name,exc,expected_status", CASES)
def test_handler(handler_client, name, exc, expected_status):
    response = handler_client.get(f"/raise/{name}")
    assert response.status_code == expected_status
    body = response.json()
    assert list(body.keys()) == ["code"], f"Expected only 'code' key, got {list(body.keys())}"
    assert body["code"] in {
        "invalid_request",
        "auth_required",
        "not_found",
        "service_unavailable",
        "internal_error",
        "out_of_scope",
    }


def test_validation_error_handler(handler_client):
    response = handler_client.post("/validate-body", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"


# The token-verification and missing-header cases live in test_jwt_security.py and test_auth_security.py.


class TestRetryAfterHeaders:
    """Verify Retry-After header on 503 errors."""

    def test_queue_full_has_retry_after(self, handler_client):
        """QueueFullError(30) response includes Retry-After: 30."""
        response = handler_client.get("/raise/queue_full")
        assert response.status_code == 503
        assert response.headers.get("retry-after") == "30"

    def test_circuit_open_has_retry_after(self, handler_client):
        """CircuitOpenError(60) response includes Retry-After: 60."""
        response = handler_client.get("/raise/circuit_open")
        assert response.status_code == 503
        assert response.headers.get("retry-after") == "60"

    def test_transient_llm_no_retry_after(self, handler_client):
        """TransientLLMError does NOT include Retry-After (no extra_headers on base)."""
        response = handler_client.get("/raise/transient_llm")
        assert response.status_code == 503
        assert "retry-after" not in response.headers


_REJECTION_IDS = [name for name, _, _, _ in REJECTION_CASES]


class TestARaisedRejectionBecomesItsClientResponse:
    """One `add_exception_handler` entry answers the whole family, because dispatch walks the MRO."""

    @pytest.mark.parametrize("name,exc,expected_status,expected_code", REJECTION_CASES,
                             ids=_REJECTION_IDS)
    def test_it_answers_the_class_the_exception_declared(self, handler_client, name, exc,
                                                         expected_status, expected_code):
        response = handler_client.get(f"/reject/{name}")
        assert response.status_code == expected_status
        body = response.json()
        assert list(body.keys()) == ["code"], f"Expected only 'code' key, got {list(body.keys())}"
        assert body["code"] == expected_code

    def test_the_two_forbidden_arms_answer_the_same_status_and_body(self, handler_client):
        """`operation_not_allowed` and `account_unavailable` are both 403 and must stay distinct codes."""
        forbidden = handler_client.get("/fail/not_linked")
        unavailable = handler_client.get("/fail/blocked_user")

        assert forbidden.status_code == unavailable.status_code == 403
        assert forbidden.json() != unavailable.json()

    def test_an_exception_outside_the_family_still_reaches_the_generic_handler(self, handler_client):
        """The negative control: the new registration must not swallow everything else."""
        response = handler_client.get("/raise/generic_exception")
        assert response.status_code == 500
        assert response.json() == {"code": "internal_error"}


class TestTheHandlerRecordsTheRejectionExactlyOnce:
    """The structured security log is the only record a rejection leaves, so its shape is a contract."""

    @pytest.mark.parametrize("name,exc,expected_status,expected_code", REJECTION_CASES,
                             ids=_REJECTION_IDS)
    def test_the_event_name_is_the_snake_cased_class_name(self, handler_client, warnings, name,
                                                          exc, expected_status, expected_code):
        handler_client.get(f"/reject/{name}")

        assert len(warnings.entries) == 1
        event, _fields = warnings.entries[0]
        assert event == name

    def test_a_rejection_carrying_no_extra_fields_logs_none(self, handler_client, warnings):
        """The base contributes `{}`, so nothing rides along that a subclass did not put there."""
        handler_client.get("/reject/identity_already_linked")

        assert warnings.entries[0][1] == {"exc_info": False}


@pytest.fixture
def dependency_client():
    """A router-level dependency that rejects, so the handler is reached before any route body runs."""
    app = FastAPI()
    register_exception_handlers(app)

    async def _rejecting_dependency():
        raise IdentityAlreadyLinked()

    router = APIRouter(dependencies=[Depends(_rejecting_dependency)])

    @router.get("/guarded/{item_id}")
    async def _guarded_route(item_id: str):
        raise AssertionError("the route body ran despite a rejecting dependency")

    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestARejectionFromADependencyReachesTheSameHandler:
    """Where the raise happens is not part of the contract; that it is answered identically is."""

    def test_it_answers_the_same_status_and_body(self, dependency_client):
        response = dependency_client.get("/guarded/abc")
        assert response.status_code == 409
        assert response.json() == {"code": "identity_already_linked"}

    def test_it_is_recorded_once_and_names_no_caller_supplied_text(self, dependency_client,
                                                                   warnings):
        """D-03 dropped `route`; what remains must still carry nothing the caller chose."""
        dependency_client.get("/guarded/abc")

        assert len(warnings.entries) == 1
        event, fields = warnings.entries[0]
        assert event == "identity_already_linked"
        assert "abc" not in str(fields)


class _RollbackRecordingSession:
    """Stands in for the session `get_db` yields: only the two boundaries this case observes."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture
def generator_session_client():
    """A route whose session comes from a real `get_db`-shaped generator, rollback arm included."""
    app = FastAPI()
    register_exception_handlers(app)
    session = _RollbackRecordingSession()

    async def _get_db():
        # Mirrors `app/dependencies.py::get_db`. A plain callable has no `except` arm and so would
        # not exercise the property this case exists for.
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    @app.get("/consuming")
    async def _consuming_route(db=Depends(_get_db)):
        raise HistoricalIdentity

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, session


class TestARejectionSurvivesTheSessionsRollbackOnTheWayOut:
    """The 409-became-500 failure mode: a handler that touches expired ORM state raises itself."""

    def test_it_still_answers_its_own_status_and_not_an_internal_error(self,
                                                                      generator_session_client):
        client, session = generator_session_client

        response = client.get("/consuming")

        assert response.status_code == 403
        assert response.json() == {"code": "account_unavailable"}

    def test_the_generators_rollback_arm_really_ran(self, generator_session_client):
        """The premise: without the rollback this case would prove nothing about the handler."""
        client, session = generator_session_client

        client.get("/consuming")

        assert (session.rollbacks, session.commits) == (1, 0)


class _StubResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _StubSession:
    """Stands in for the one short session the admission barrier opens."""

    def __init__(self, row):
        self._row = row

    async def exec(self, statement):
        return _StubResult(self._row)


def _identity_row(*, identity_state=IdentityState.active, user_active: bool = True):
    """An `(identity, user)` pair shaped exactly as the single joined statement returns one."""
    user_id = uuid7()
    identity = ExternalIdentity(id=uuid7(), user_id=user_id, issuer=ISSUER, subject=SUBJECT,
                                provider=IdentityProvider.google, provider_uid="google-account-1",
                                identity_state=identity_state)
    return identity, User(id=user_id, active=user_active)


ADMISSION_ARMS = {"historical_identity": _identity_row(identity_state=IdentityState.historical),
                  "blocked_user": _identity_row(user_active=False)}


@pytest.fixture(scope="module")
def admission_client():
    """Routes whose dependency runs the real resolution, so the raise travels the real stack."""
    app = FastAPI()
    register_exception_handlers(app)

    def _resolving(row):
        async def _dependency():
            session = cast(AsyncSession, _StubSession(row))
            return await IdentitiesDB(session).resolve(issuer=ISSUER, subject=SUBJECT,
                                                       allow_preauth=False)

        return _dependency

    async def _unreachable_route():
        raise AssertionError("the route body ran despite a rejecting dependency")

    for name, row in ADMISSION_ARMS.items():
        app.add_api_route(f"/admit/{name}", _unreachable_route, methods=["GET"],
                          dependencies=[Depends(_resolving(row))])

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _comparable(response) -> tuple[int, bytes, dict[str, str]]:
    """Status, body bytes and headers, with the one header that cannot repeat dropped."""
    headers = {key: value for key, value in response.headers.items() if key.lower() != "date"}
    return response.status_code, response.content, headers


class TestAnAccountUnavailableArmTravelsTheWholeErrorPath:
    """The tracer: a raise in resolution, the dependency stack, MRO dispatch, and one handler."""

    @pytest.mark.parametrize("arm", list(ADMISSION_ARMS), ids=list(ADMISSION_ARMS))
    def test_it_answers_403_with_a_one_field_body(self, admission_client, arm):
        response = admission_client.get(f"/admit/{arm}")

        assert response.status_code == 403
        assert response.json() == {"code": "account_unavailable"}

    @pytest.mark.parametrize("arm", list(ADMISSION_ARMS), ids=list(ADMISSION_ARMS))
    def test_it_produces_exactly_one_warning_named_for_its_class(self, admission_client, warnings,
                                                                 arm):
        admission_client.get(f"/admit/{arm}")

        assert len(warnings.entries) == 1
        event, fields = warnings.entries[0]
        assert event == arm
        assert fields == {"exc_info": False}

    def test_the_two_arms_are_indistinguishable_to_the_client(self, admission_client):
        """T-37.4-02: the 403 is declared once on the base, so drift takes editing the base."""
        historical = admission_client.get("/admit/historical_identity")
        blocked = admission_client.get("/admit/blocked_user")

        assert _comparable(historical) == _comparable(blocked)

    def test_neither_arm_carries_a_field_into_its_log_line(self, admission_client, warnings):
        """The `cause` field D-05 deleted was the only channel; the event name replaced it."""
        for arm in ADMISSION_ARMS:
            admission_client.get(f"/admit/{arm}")

        assert [event for event, _ in warnings.entries] == list(ADMISSION_ARMS)
        for _, fields in warnings.entries:
            assert set(fields) == {"exc_info"}


def _fresh_interpreter(snippet: str) -> subprocess.CompletedProcess:
    """Run the check in its own process, so a synthetic subclass cannot outlive it."""
    return subprocess.run([sys.executable, "-c", snippet], capture_output=True, text=True)


class TestStartupFailsClosedOnATreeDefect:
    """`assert_tree_total` is the gate; a walk that quietly found nothing would pass every case."""

    def test_a_duplicate_code_at_another_status_is_reported_and_names_both_classes(self):
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "from unit.error_tree import assert_tree_total\n"
            "class _Duplicate(AppError):\n"
            "    status = 409\n"
            "    code = 'account_unavailable'\n"
            "assert_tree_total()\n")

        assert result.returncode != 0
        assert "AccountUnavailable" in result.stderr
        assert "_Duplicate" in result.stderr

    def test_a_class_declaring_only_status_is_reported(self):
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "from unit.error_tree import assert_tree_total\n"
            "class _HalfDeclared(AppError):\n"
            "    status = 418\n"
            "assert_tree_total()\n")

        assert result.returncode != 0
        assert "_HalfDeclared declares only status" in result.stderr

    def test_the_same_check_reports_neither_when_neither_class_exists(self):
        """The control: without it the two cases above would pass on any raised message at all."""
        result = _fresh_interpreter(
            "from unit.error_tree import assert_tree_total\n"
            "try:\n"
            "    assert_tree_total()\n"
            "except RuntimeError as problem:\n"
            "    print(problem)\n")

        assert result.returncode == 0
        assert "_Duplicate" not in result.stdout
        assert "_HalfDeclared" not in result.stdout


@pytest.fixture(scope="module")
def framework_client():
    """Routes that raise the framework's own exception, which no class in the tree inherits from."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/only-get")
    async def _only_get():
        return {"ok": True}

    app.add_api_route("/raise/framework/418",
                      _make_raise_route(StarletteHTTPException(status_code=418)), methods=["GET"])

    @app.post("/needs-a-body")
    async def _needs_a_body(body: _Body):
        return body

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestAFrameworkStatusStillReachesTheOneResponseBuilder:
    """The two framework adapters construct the tree's own exception and delegate to the handler."""

    def test_an_unrouted_path_answers_the_404_class(self, framework_client):
        response = framework_client.get("/no-such-route")
        assert response.status_code == 404
        assert response.json() == {"code": "not_found"}

    def test_a_wrong_method_answers_the_405_class_and_keeps_the_routers_allow_header(
            self, framework_client):
        """`Allow` is the router's, not the class's, so only forwarding `headers` preserves it."""
        response = framework_client.post("/only-get")
        assert response.status_code == 405
        assert response.json() == {"code": "method_not_allowed"}
        assert "GET" in response.headers["allow"]

    def test_a_schema_violation_answers_the_422_class(self, framework_client):
        response = framework_client.post("/needs-a-body", json={})
        assert response.status_code == 422
        assert response.json() == {"code": "validation_error"}

    @pytest.mark.parametrize("path,expected_code", [("/no-such-route", "not_found"),
                                                    ("/needs-a-body", "validation_error")])
    def test_every_framework_answer_body_is_still_exactly_one_field(self, framework_client, path,
                                                                    expected_code):
        response = (framework_client.post(path, json={}) if path == "/needs-a-body"
                    else framework_client.get(path))
        assert list(response.json().keys()) == ["code"]
        assert response.json()["code"] == expected_code

    def test_a_status_no_class_answers_logs_loudly_and_answers_500(self, framework_client,
                                                                   monkeypatch):
        """The fail-loudly branch is a control: an unmapped status must never default silently."""
        recorder = []
        monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger.error",
                            lambda event, **kwargs: recorder.append((event, kwargs)))

        response = framework_client.get("/raise/framework/418")

        assert response.status_code == 500
        assert response.json() == {"code": "internal_error"}
        assert recorder == [("error_registry_unmapped_status", {"unmapped_status": 418})]


class TestTheHeadersEachClassComputesStillReachTheClient:
    """`extra_headers()` is the one channel, and three classes use it for two different reasons."""

    def test_the_401_class_carries_www_authenticate(self, handler_client):
        response = handler_client.get("/raise/missing_token")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.parametrize("name,seconds", [("queue_full", "30"), ("circuit_open", "60")])
    def test_the_two_503_classes_carry_the_retry_after_they_computed(self, handler_client, name,
                                                                    seconds):
        response = handler_client.get(f"/raise/{name}")
        assert response.status_code == 503
        assert response.headers["retry-after"] == seconds

    def test_a_class_that_computes_no_header_sends_none(self, handler_client):
        """The control: without it the two cases above would pass on a header added to every answer."""
        response = handler_client.get("/raise/transient_llm")
        assert response.status_code == 503
        assert "retry-after" not in response.headers
        assert "www-authenticate" not in response.headers
