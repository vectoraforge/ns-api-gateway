"""The error tree is total, and the handlers read it rather than a remap table."""
import re
import subprocess
import sys
from pathlib import Path
from typing import get_args

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

import nativespeaker.api.errors
from nativespeaker.api.app.error_handlers import app_error_handler, http_exception_handler
from nativespeaker.api.app.main import app as real_app
from nativespeaker.api.errors import (
    AppError,
    ErrorCode,
    ErrorResponse,
    InvalidCursorError,
    PageSizeLimitError,
    QueueFullError,
    _family,
    class_answering_status,
)
from unit.error_tree import assert_tree_total, tree_problems

# The 401 code an earlier contract used alongside auth_required, since retired.
RETIRED_401_CODE = "unauthorized"

# The statuses a bare framework rejection can arrive with, each answered by exactly one class.
FRAMEWORK_STATUSES = (400, 401, 404, 405, 409, 422, 429, 500, 503)


def _declaring(code: str) -> list[type[AppError]]:
    """Every class that declares `code` itself, rather than inheriting it from a base."""
    return [cls for cls in _family(AppError) if vars(cls).get("code") == code]


def _fresh_interpreter(snippet: str) -> subprocess.CompletedProcess:
    """Run a check in its own process, so a synthetic subclass cannot outlive it."""
    return subprocess.run([sys.executable, "-c", snippet], capture_output=True, text=True)


class _RecordingLogger:
    """Records calls per level, with no dependency on structlog's configuration state."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def __getattr__(self, level: str):
        def _record(event: str, *args, **kwargs):
            self.calls.append((level, event, kwargs))
        return _record

    def events(self, level: str) -> list[tuple[str, dict]]:
        return [(event, kwargs) for lvl, event, kwargs in self.calls if lvl == level]


class TestTreeTotality:
    """One class per condition, and the declared code set is exactly the carried one."""

    def test_assert_tree_total_passes_as_shipped(self):
        assert assert_tree_total() is None

    def test_the_error_code_literal_equals_the_set_the_tree_carries(self):
        assert set(get_args(ErrorCode)) == {cls.code for cls in _family(AppError)}

    def test_no_code_is_declared_at_two_different_statuses(self):
        for code in get_args(ErrorCode):
            statuses = {cls.status for cls in _declaring(code)}
            assert len(statuses) <= 1, f"{code!r} is declared at {sorted(statuses)}"

    def test_every_class_declares_status_and_code_together_or_neither(self):
        for cls in _family(AppError):
            own = vars(cls)
            assert ("status" in own) == ("code" in own), cls.__name__

    def test_a_class_declaring_nothing_answers_the_fail_closed_default(self):
        """The base's 500 is the control that keeps a forgotten declaration from meaning 200.

        In a fresh interpreter, because a synthetic subclass joins the real tree while it is alive.
        """
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "class _Bare(AppError):\n"
            "    pass\n"
            "print(_Bare.status, _Bare.code)\n")

        assert result.stdout.strip() == "500 internal_error"


class TestTreeTotalityCatchesDefects:
    """Each invariant fails loudly when a later phase appends a class carelessly.

    The defect cases run in a fresh interpreter rather than in-process: a synthetic subclass of
    `AppError` joins the real tree for as long as it is alive, and one that outlived its case would
    fail every later call to `assert_tree_total`.
    """

    def test_a_code_claimed_at_a_second_status_is_reported_and_names_both_classes(self):
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "from unit.error_tree import assert_tree_total\n"
            "class _Duplicate(AppError):\n"
            "    status = 451\n"
            "    code = 'not_found'\n"
            "assert_tree_total()\n")

        assert result.returncode != 0
        assert "_Duplicate" in result.stderr
        assert "NotFound" in result.stderr

    def test_a_class_declaring_only_a_status_is_reported(self):
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "from unit.error_tree import assert_tree_total\n"
            "class _HalfDeclared(AppError):\n"
            "    status = 418\n"
            "assert_tree_total()\n")

        assert result.returncode != 0
        assert "_HalfDeclared declares only status" in result.stderr

    def test_a_class_declaring_only_a_code_is_reported(self):
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "from unit.error_tree import assert_tree_total\n"
            "class _HalfDeclared(AppError):\n"
            "    code = 'not_found'\n"
            "assert_tree_total()\n")

        assert result.returncode != 0
        assert "_HalfDeclared declares only code" in result.stderr

    def test_a_leaf_declaring_nothing_is_reported(self):
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "from unit.error_tree import assert_tree_total\n"
            "class _SilentLeaf(AppError):\n"
            "    pass\n"
            "assert_tree_total()\n")

        assert result.returncode != 0
        assert "_SilentLeaf declares no status or code" in result.stderr

    def test_a_second_class_claiming_one_framework_status_is_reported(self):
        result = _fresh_interpreter(
            "from nativespeaker.api.errors import AppError\n"
            "from unit.error_tree import assert_tree_total\n"
            "class _SecondNotFound(AppError):\n"
            "    status = 404\n"
            "    code = 'not_found'\n"
            "    answers_framework_status = True\n"
            "assert_tree_total()\n")

        assert result.returncode != 0
        assert "status 404 is answered by both" in result.stderr

    def test_a_code_absent_from_the_tree_is_reported(self):
        """The other direction of the vocabulary equality, reported as its own problem."""
        problems = tree_problems(AppError,
                                 declared_codes=frozenset(get_args(ErrorCode)) | {"invented"})
        assert problems == ["ErrorCode declares codes the tree never carries: ['invented']"]

    def test_the_same_checks_report_nothing_when_no_synthetic_class_exists(self):
        """The control: without it, every case above would pass on any raised message at all."""
        result = _fresh_interpreter(
            "from unit.error_tree import assert_tree_total\n"
            "assert_tree_total()\n")

        assert result.returncode == 0
        assert result.stderr == ""


class TestRetired401Code:
    """`auth_required` is the only 401 the service emits."""

    def test_absent_from_the_tree(self):
        assert RETIRED_401_CODE not in {cls.code for cls in _family(AppError)}

    def test_absent_from_the_error_code_literal(self):
        assert RETIRED_401_CODE not in get_args(ErrorCode)

    def test_absent_from_the_error_response_model(self):
        code_field = ErrorResponse.model_fields["code"]
        assert RETIRED_401_CODE not in get_args(code_field.annotation)

    def test_absent_from_the_apps_openapi_responses_block(self):
        """Introspects the mapping the app was constructed with -- no schema generation needed."""
        responses = real_app.router.responses
        assert RETIRED_401_CODE not in str(responses).lower()

    def test_the_one_401_the_responses_block_documents_is_the_answering_class(self):
        assert real_app.router.responses[401]["model"] is ErrorResponse
        answering = class_answering_status(401)
        assert answering is not None and answering.code == "auth_required"


class TestTheFrameworkStatusMap:
    """The walk-built mapping that replaced the folding table, and then `STATUS_TO_CLASS`."""

    @pytest.mark.parametrize("status,expected_code", [
        (404, "not_found"),
        (405, "method_not_allowed"),
        (422, "validation_error"),
        (500, "internal_error"),
    ])
    def test_framework_status_maps_to_exactly_one_class(self, status, expected_code):
        answering = class_answering_status(status)
        assert answering is not None
        assert answering.code == expected_code

    def test_409_is_challenge_required_not_identity_already_linked(self):
        """The live collision the deleted remap table caused: its 409 -> 400 entry."""
        answering = class_answering_status(409)
        assert answering is not None
        assert (answering.status, answering.code) == (409, "challenge_required")

    def test_no_status_is_folded_onto_another(self):
        for status in FRAMEWORK_STATUSES:
            answering = class_answering_status(status)
            assert answering is not None, f"{status} has no answering class"
            assert answering.status == status, f"{status} folded onto {answering.status}"

    def test_403_has_no_answering_class(self):
        """Three classes now sit at 403 and none of them is the generic answer."""
        assert class_answering_status(403) is None

    def test_the_new_409_does_not_claim_the_framework_slot(self):
        """The mapping is for framework-raised statuses, and rebinding it would recast every 409."""
        assert nativespeaker.api.errors.IdentityAlreadyLinked.status == 409
        assert not vars(nativespeaker.api.errors.IdentityAlreadyLinked).get(
            "answers_framework_status")

    def test_no_module_level_table_keyed_by_status_exists(self):
        """A mapping built by the walk is permitted; a module-level literal is the registry renamed."""
        source = Path(nativespeaker.api.errors.__file__).read_text()
        assert re.search(r"^[A-Z_]+: dict\[int", source, re.MULTILINE) is None


class TestNo415Class:
    """A2: 415 is unreachable without python-multipart, so declaring a class would be a lie."""

    def test_no_class_carries_status_415(self):
        assert [cls.__name__ for cls in _family(AppError) if cls.status == 415] == []

    def test_415_has_no_answering_class(self):
        assert class_answering_status(415) is None

    def test_python_multipart_is_not_installed(self):
        """The fact the omission rests on. If this ever fails, 415 needs a declared class."""
        import importlib.util

        installed = [name for name in ("multipart", "python_multipart")
                     if importlib.util.find_spec(name) is not None]
        assert installed == [], (
            f"python-multipart is installed as {installed}: a Form or File parameter can now be "
            "declared, so 415 became reachable and needs a declared class")


class TestHttpExceptionHandler:
    """The handler reads the tree; a miss is loud, not a silent fallback."""

    async def test_maps_a_known_status_to_its_class(self):
        response = await http_exception_handler(None, StarletteHTTPException(status_code=404))
        assert response.status_code == 404
        assert response.body == b'{"code":"not_found"}'

    async def test_405_preserves_the_routers_allow_header(self):
        exc = StarletteHTTPException(status_code=405, headers={"Allow": "GET, HEAD"})
        response = await http_exception_handler(None, exc)
        assert response.status_code == 405
        assert response.headers["allow"] == "GET, HEAD"
        assert response.body == b'{"code":"method_not_allowed"}'

    async def test_409_surfaces_as_challenge_required(self):
        response = await http_exception_handler(None, StarletteHTTPException(status_code=409))
        assert response.status_code == 409
        assert response.body == b'{"code":"challenge_required"}'

    async def test_unmapped_status_returns_500_internal_error(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger", _RecordingLogger())
        response = await http_exception_handler(None, StarletteHTTPException(status_code=418))
        assert response.status_code == 500
        assert response.body == b'{"code":"internal_error"}'

    async def test_unmapped_status_logs_at_error_with_the_status_as_a_field(self, monkeypatch):
        recorder = _RecordingLogger()
        monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger", recorder)
        await http_exception_handler(None, StarletteHTTPException(status_code=418))
        assert recorder.events("error") == [("error_registry_unmapped_status",
                                             {"unmapped_status": 418})]

    async def test_a_mapped_status_logs_nothing(self, monkeypatch):
        """The loud path must fire only on a hole in the tree, not on every framework rejection."""
        recorder = _RecordingLogger()
        monkeypatch.setattr("nativespeaker.api.app.error_handlers.logger", recorder)
        await http_exception_handler(None, StarletteHTTPException(status_code=404))
        assert recorder.calls == []


class TestAppErrorHandler:
    """Within a code, status and body are identical across every branch that carries it."""

    async def test_two_subclasses_sharing_a_code_produce_byte_identical_bodies(self):
        first = await app_error_handler(None, InvalidCursorError())
        second = await app_error_handler(None, PageSizeLimitError(100))
        assert first.status_code == second.status_code == 400
        assert first.body == second.body == b'{"code":"invalid_request"}'

    async def test_the_exception_message_never_reaches_the_body(self):
        """`str(exc)` names the limit; the client body must not distinguish the branch."""
        response = await app_error_handler(None, PageSizeLimitError(100))
        assert b"100" not in response.body
        assert response.body == b'{"code":"invalid_request"}'

    async def test_extra_headers_survive(self):
        response = await app_error_handler(None, QueueFullError(30))
        assert response.status_code == 503
        assert response.headers["retry-after"] == "30"


class TestPhase37Classes:
    """The two appended classes, at statuses the tree chooses rather than inherits from the spec."""

    def test_identity_already_linked_is_declared_at_409(self):
        cls = nativespeaker.api.errors.IdentityAlreadyLinked
        assert (cls.status, cls.code) == (409, "identity_already_linked")

    def test_operation_not_allowed_is_declared_at_403(self):
        cls = nativespeaker.api.errors.NotLinked
        assert (cls.status, cls.code) == (403, "operation_not_allowed")

    def test_both_codes_are_declared_in_the_error_code_literal(self):
        declared = get_args(ErrorCode)
        assert "identity_already_linked" in declared
        assert "operation_not_allowed" in declared

    def test_sharing_409_with_challenge_required_is_legal_and_intended(self):
        """Codes must be unique to one status; statuses may be shared by several codes."""
        at_409 = sorted({cls.code for cls in _family(AppError) if cls.status == 409})
        assert at_409 == ["challenge_required", "identity_already_linked"]

    def test_operation_not_allowed_joins_the_existing_403_codes(self):
        at_403 = sorted({cls.code for cls in _family(AppError) if cls.status == 403})
        assert at_403 == ["account_unavailable", "operation_not_allowed",
                          "preauth_identity_not_allowed"]


class TestDeliberatelyAbsentCodes:
    """Two codes are absent by decision, asserted so the absences do not read as omissions to fix."""

    ABSENT = ("create_flow_mismatch", "registration_temporarily_unavailable")

    @pytest.mark.parametrize("code", ABSENT)
    def test_absent_from_the_tree(self, code):
        assert code not in {cls.code for cls in _family(AppError)}

    @pytest.mark.parametrize("code", ABSENT)
    def test_absent_from_the_error_code_literal(self, code):
        assert code not in get_args(ErrorCode)

    def test_no_class_carries_a_gateway_specialisation_of_429(self):
        """`rate_limited` stays the only 429 beside `quota_exceeded`."""
        at_429 = sorted({cls.code for cls in _family(AppError) if cls.status == 429})
        assert at_429 == ["quota_exceeded", "rate_limited"]


class TestErrorResponseStaysOneField:
    """The one place a wider body was once demanded is gone, and the contract is not reopened."""

    def test_exactly_one_model_field(self):
        assert list(ErrorResponse.model_fields) == ["code"]

    def test_no_subclass_is_defined_anywhere_under_src(self):
        """Source-level, not runtime: a subclass nothing imports still widens the contract once a handler reaches it."""
        src = Path(__file__).resolve().parents[2] / "src"
        offenders = [str(path) for path in src.rglob("*.py")
                     if re.search(r"^class\s+\w+\(.*\bErrorResponse\b.*\):", path.read_text(),
                                  re.MULTILINE)]
        assert offenders == []

    def test_no_subclass_exists_at_runtime(self):
        """`test_error_registry` imports the real app, so every production module is loaded."""
        assert ErrorResponse.__subclasses__() == []

    def test_the_errors_module_declares_no_per_class_payload_slot(self):
        """The field the 409 body once wanted no longer has a reason to exist."""
        source = Path(nativespeaker.api.errors.__file__).read_text()
        assert "required" + "_flow" not in source
