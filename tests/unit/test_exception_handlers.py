import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.exceptions import (
    AccountUnavailable,
    IdentityAlreadyLinked,
    ProviderAccountAlreadyLinked,
)
from nativespeaker.api.errors import (
    AuthenticationError,
    ChatHistoryLimitError,
    CircuitOpenError,
    DatabaseNotInitializedError,
    InvalidChatError,
    InvalidCursorError,
    OutOfScopeError,
    PageSizeLimitError,
    PermanentLLMError,
    QueueFullError,
    TransientLLMError,
    UnsupportedLanguageError,
)

CASES = [
    ("missing_token", AuthenticationError("Missing Bearer token"), 401),
    ("invalid_token", AuthenticationError("Invalid token"), 401),
    ("expired_token", AuthenticationError("Expired token"), 401),
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


# The rejection family answers through its own handler. Each route name is the event name the
# handler must derive from the class, written out rather than re-derived with `camel_to_snake`.
REJECTION_CASES = [
    ("identity_already_linked", IdentityAlreadyLinked(), 409, "identity_already_linked"),
    ("provider_account_already_linked", ProviderAccountAlreadyLinked(), 403,
     "operation_not_allowed"),
    ("account_unavailable", AccountUnavailable(cause="blocked_user"), 403, "account_unavailable"),
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
    monkeypatch.setattr("nativespeaker.api.app.errors.logger.warning", spy.record)
    return spy


@pytest.fixture(scope="module")
def handler_client():
    app = FastAPI()
    register_exception_handlers(app)

    for name, exc, _ in CASES:
        app.add_api_route(f"/raise/{name}", _make_raise_route(exc), methods=["GET"])

    for name, exc, _, _ in REJECTION_CASES:
        app.add_api_route(f"/reject/{name}", _make_raise_route(exc), methods=["GET"])

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
        forbidden = handler_client.get("/reject/provider_account_already_linked")
        unavailable = handler_client.get("/reject/account_unavailable")

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
        event, fields = warnings.entries[0]
        assert event == name
        assert fields["route"] == f"/reject/{name}"

    def test_the_account_unavailable_arms_are_distinguished_in_the_log_alone(self, handler_client,
                                                                            warnings):
        """One class, one body; `cause` is the only place the two arms are told apart."""
        handler_client.get("/reject/account_unavailable")

        assert warnings.entries[0][1]["cause"] == "blocked_user"

    def test_a_rejection_carrying_no_extra_fields_logs_none(self, handler_client, warnings):
        """The base contributes `{}`, so nothing rides along that a subclass did not put there."""
        handler_client.get("/reject/identity_already_linked")

        assert warnings.entries[0][1] == {"route": "/reject/identity_already_linked"}


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

    def test_it_logs_the_path_template_and_never_the_callers_raw_path(self, dependency_client,
                                                                     warnings):
        """A raw path would put caller-controlled text in the security log."""
        dependency_client.get("/guarded/abc")

        assert len(warnings.entries) == 1
        event, fields = warnings.entries[0]
        assert event == "identity_already_linked"
        assert fields["route"] == "/guarded/{item_id}"


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
        raise AccountUnavailable(cause="historical_identity")

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
