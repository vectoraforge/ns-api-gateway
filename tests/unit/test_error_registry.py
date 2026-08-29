"""The error registry is total, and the handlers read it rather than a remap table."""
import re
from contextlib import contextmanager
from pathlib import Path
from typing import get_args

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

import nativespeaker.api.errors
from nativespeaker.api.app.error_handlers import http_exception_handler, service_error_handler
from nativespeaker.api.app.main import app as real_app
from nativespeaker.api.errors import (
    CHALLENGE_REQUIRED,
    IDENTITY_ALREADY_LINKED,
    OPERATION_NOT_ALLOWED,
    REGISTRY,
    STATUS_TO_CLASS,
    ErrorClass,
    ErrorCode,
    ErrorResponse,
    InvalidCursorError,
    PageSizeLimitError,
    QueueFullError,
    assert_registry_total,
    register_class,
)

# The 401 code an earlier contract used alongside auth_required, since retired.
RETIRED_401_CODE = "unauthorized"


@contextmanager
def registry_mutation():
    """Restore both tables afterwards, since they are module-level dicts shared process-wide."""
    saved_registry = dict(REGISTRY)
    saved_status = dict(STATUS_TO_CLASS)
    try:
        yield
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved_registry)
        STATUS_TO_CLASS.clear()
        STATUS_TO_CLASS.update(saved_status)


class _RecordingLogger:
    """Records calls per level, with no dependency on structlog's configuration state."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def __getattr__(self, level: str):
        def _record(event: str, **kwargs):
            self.calls.append((level, event, kwargs))
        return _record

    def events(self, level: str) -> list[tuple[str, dict]]:
        return [(event, kwargs) for lvl, event, kwargs in self.calls if lvl == level]


class TestRegistryTotality:
    """One class per condition, and the declared code set is exactly the registered one."""

    def test_no_two_classes_share_a_code(self):
        codes = [cls.code for cls in REGISTRY.values()]
        assert len(codes) == len(set(codes)), "a code is claimed by two classes"

    def test_every_class_carries_exactly_one_status(self):
        """Status is a single scalar field on a frozen class -- it cannot vary per branch."""
        for cls in REGISTRY.values():
            assert isinstance(cls.status, int)
            with pytest.raises(AttributeError):
                cls.status = 500  # type: ignore[invalid-assignment]

    def test_class_is_registered_under_its_own_name(self):
        for name, cls in REGISTRY.items():
            assert cls.name == name

    def test_error_code_literal_equals_the_registered_code_set(self):
        assert set(get_args(ErrorCode)) == {cls.code for cls in REGISTRY.values()}

    def test_assert_registry_total_passes_as_shipped(self):
        assert_registry_total() is None


class TestRegistryTotalityCatchesDefects:
    """Each of the four invariants fails loudly when a later phase appends a class carelessly."""

    def test_duplicate_code_is_rejected_at_registration(self):
        """`register_class` refuses a near-duplicate before boot even starts."""
        with registry_mutation():
            with pytest.raises(ValueError, match="already registered"):
                register_class(ErrorClass(name="second_not_found", status=404,
                                          code="not_found"))
        assert "second_not_found" not in REGISTRY

    def test_duplicate_code_smuggled_past_registration_fails_the_self_check(self):
        """Belt and braces: a class written straight into the table is still caught at boot."""
        with registry_mutation():
            REGISTRY["smuggled"] = ErrorClass(name="smuggled", status=404,
                                              code="not_found")
            with pytest.raises(RuntimeError, match="shared by"):
                assert_registry_total()

    def test_status_mapping_to_an_unregistered_class_fails_the_self_check(self):
        with registry_mutation():
            STATUS_TO_CLASS[418] = ErrorClass(name="ghost", status=418,
                                              code="not_found")
            with pytest.raises(RuntimeError, match="unregistered class"):
                assert_registry_total()

    def test_status_mapping_to_a_class_with_another_status_fails_the_self_check(self):
        """The exact shape of the deleted `_STATUS_REMAP`: one status folded onto another."""
        with registry_mutation():
            STATUS_TO_CLASS[409] = REGISTRY["invalid_request"]
            with pytest.raises(RuntimeError, match="carries status 400"):
                assert_registry_total()

    def test_code_absent_from_the_error_code_literal_fails_the_self_check(self):
        with registry_mutation():
            del REGISTRY["out_of_scope"]
            with pytest.raises(RuntimeError, match="ErrorCode declares unregistered codes"):
                assert_registry_total()


class TestRetired401Code:
    """`auth_required` is the only 401 the service emits."""

    def test_absent_from_the_registry(self):
        assert RETIRED_401_CODE not in {cls.code for cls in REGISTRY.values()}
        assert RETIRED_401_CODE not in REGISTRY

    def test_absent_from_the_error_code_literal(self):
        assert RETIRED_401_CODE not in get_args(ErrorCode)

    def test_absent_from_the_error_response_model(self):
        code_field = ErrorResponse.model_fields["code"]
        assert RETIRED_401_CODE not in get_args(code_field.annotation)

    def test_absent_from_the_apps_openapi_responses_block(self):
        """Introspects the mapping the app was constructed with -- no schema generation needed."""
        responses = real_app.router.responses
        assert RETIRED_401_CODE not in str(responses).lower()

    def test_the_one_401_the_responses_block_documents_is_the_registered_class(self):
        assert real_app.router.responses[401]["model"] is ErrorResponse
        assert STATUS_TO_CLASS[401].code == "auth_required"

    def test_exactly_one_class_carries_status_401(self):
        assert [cls.name for cls in REGISTRY.values() if cls.status == 401] == ["auth_required"]


class TestStatusToClass:
    """The closed framework-exception mapping that replaced the folding table."""

    @pytest.mark.parametrize("status,expected_code", [
        (404, "not_found"),
        (405, "method_not_allowed"),
        (422, "validation_error"),
        (500, "internal_error"),
    ])
    def test_framework_status_maps_to_exactly_one_registered_class(self, status, expected_code):
        error_class = STATUS_TO_CLASS[status]
        assert error_class.code == expected_code
        assert REGISTRY[error_class.name] is error_class

    def test_409_is_challenge_required_not_invalid_request(self):
        """The live collision the deleted remap table caused: its 409 -> 400 entry."""
        assert STATUS_TO_CLASS[409].code == "challenge_required"
        assert STATUS_TO_CLASS[409].status == 409

    def test_no_status_is_folded_onto_another(self):
        for status, error_class in STATUS_TO_CLASS.items():
            assert error_class.status == status, f"{status} folded onto {error_class.status}"

    def test_every_mapped_class_is_registered(self):
        for error_class in STATUS_TO_CLASS.values():
            assert REGISTRY.get(error_class.name) is error_class


class TestNo415Class:
    """A2: 415 is unreachable without python-multipart, so declaring a class would be a lie."""

    def test_no_registered_class_carries_status_415(self):
        assert [cls.name for cls in REGISTRY.values() if cls.status == 415] == []

    def test_415_is_not_in_the_status_mapping(self):
        assert 415 not in STATUS_TO_CLASS

    def test_python_multipart_is_not_installed(self):
        """The fact the omission rests on. If this ever fails, 415 needs a declared class."""
        import importlib.util

        installed = [name for name in ("multipart", "python_multipart")
                     if importlib.util.find_spec(name) is not None]
        assert installed == [], (
            f"python-multipart is installed as {installed}: a Form or File parameter can now be "
            "declared, so 415 became reachable and needs a declared class")


class TestHttpExceptionHandler:
    """The handler reads the registry; a miss is loud, not a silent fallback."""

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
        monkeypatch.setattr("nativespeaker.api.app.errors.logger", _RecordingLogger())
        response = await http_exception_handler(None, StarletteHTTPException(status_code=418))
        assert response.status_code == 500
        assert response.body == b'{"code":"internal_error"}'

    async def test_unmapped_status_logs_at_error_with_the_status_as_a_field(self, monkeypatch):
        recorder = _RecordingLogger()
        monkeypatch.setattr("nativespeaker.api.app.errors.logger", recorder)
        await http_exception_handler(None, StarletteHTTPException(status_code=418))
        assert recorder.events("error") == [("error_registry_unmapped_status",
                                             {"unmapped_status": 418})]

    async def test_a_mapped_status_logs_nothing(self, monkeypatch):
        """The loud path must fire only on a registry hole, not on every framework rejection."""
        recorder = _RecordingLogger()
        monkeypatch.setattr("nativespeaker.api.app.errors.logger", recorder)
        await http_exception_handler(None, StarletteHTTPException(status_code=404))
        assert recorder.calls == []


class TestServiceErrorHandler:
    """Within a class, status and body are identical across every branch."""

    async def test_two_subclasses_sharing_a_class_produce_byte_identical_bodies(self):
        first = await service_error_handler(None, InvalidCursorError())
        second = await service_error_handler(None, PageSizeLimitError(100))
        assert first.status_code == second.status_code == 400
        assert first.body == second.body == b'{"code":"invalid_request"}'

    async def test_the_exception_message_never_reaches_the_body(self):
        """`str(exc)` names the limit; the client body must not distinguish the branch."""
        response = await service_error_handler(None, PageSizeLimitError(100))
        assert b"100" not in response.body
        assert response.body == b'{"code":"invalid_request"}'

    async def test_extra_headers_survive(self):
        response = await service_error_handler(None, QueueFullError(30))
        assert response.status_code == 503
        assert response.headers["retry-after"] == "30"


class TestPhase37Classes:
    """The two appended classes, at statuses the registry chooses rather than inherits from the spec."""

    def test_identity_already_linked_is_registered_at_409(self):
        assert IDENTITY_ALREADY_LINKED.status == 409
        assert IDENTITY_ALREADY_LINKED.code == "identity_already_linked"
        assert REGISTRY["identity_already_linked"] is IDENTITY_ALREADY_LINKED

    def test_operation_not_allowed_is_registered_at_403(self):
        assert OPERATION_NOT_ALLOWED.status == 403
        assert OPERATION_NOT_ALLOWED.code == "operation_not_allowed"
        assert REGISTRY["operation_not_allowed"] is OPERATION_NOT_ALLOWED

    def test_both_codes_are_declared_in_the_error_code_literal(self):
        """`assert_registry_total` fails boot when the Literal and the table diverge."""
        declared = get_args(ErrorCode)
        assert "identity_already_linked" in declared
        assert "operation_not_allowed" in declared

    def test_the_registry_is_still_total(self):
        assert assert_registry_total() is None

    def test_sharing_409_with_challenge_required_is_legal_and_intended(self):
        """`register_class` forbids duplicate codes, not duplicate statuses."""
        at_409 = sorted(cls.name for cls in REGISTRY.values() if cls.status == 409)
        assert at_409 == ["challenge_required", "identity_already_linked"]

    def test_the_new_409_does_not_claim_the_framework_exception_slot(self):
        """The mapping is for framework-raised statuses, and rebinding it would recast every framework 409."""
        assert STATUS_TO_CLASS[409] is CHALLENGE_REQUIRED

    def test_403_remains_absent_from_the_status_mapping(self):
        """Three classes now sit at 403 and none of them is the generic answer."""
        assert 403 not in STATUS_TO_CLASS

    def test_operation_not_allowed_joins_the_existing_403_classes(self):
        at_403 = sorted(cls.name for cls in REGISTRY.values() if cls.status == 403)
        assert at_403 == ["account_unavailable", "operation_not_allowed",
                          "preauth_identity_not_allowed"]


class TestDeliberatelyUnregisteredClasses:
    """Two classes are absent by decision, asserted so the absences do not read as omissions to fix."""

    ABSENT = ("create_flow_mismatch", "registration_temporarily_unavailable")

    @pytest.mark.parametrize("code", ABSENT)
    def test_absent_from_the_registry(self, code):
        assert code not in {cls.code for cls in REGISTRY.values()}
        assert code not in REGISTRY

    @pytest.mark.parametrize("code", ABSENT)
    def test_absent_from_the_error_code_literal(self, code):
        assert code not in get_args(ErrorCode)

    def test_no_registered_class_carries_a_gateway_specialisation_of_429(self):
        """`rate_limited` stays the only registered 429 beside `quota_exceeded`."""
        at_429 = sorted(cls.name for cls in REGISTRY.values() if cls.status == 429)
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

    def test_the_registry_module_declares_no_per_class_payload_slot(self):
        """The field the 409 body once wanted no longer has a reason to exist."""
        source = Path(nativespeaker.api.errors.__file__).read_text()
        assert "required" + "_flow" not in source
