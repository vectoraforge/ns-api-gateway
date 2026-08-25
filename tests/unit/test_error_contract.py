"""The contract under test is that every branch within an error class returns identical copy."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.app.main import app as real_app

# Written out rather than derived from REGISTRY: the mirror that catches an undecided code shipping.
CONTRACT_CODES = {"auth_required", "preauth_identity_not_allowed", "account_unavailable",
                  "challenge_required", "invalid_request", "verification_temporarily_unavailable",
                  "rate_limited", "validation_error", "not_found", "method_not_allowed",
                  "internal_error", "service_unavailable", "quota_exceeded", "out_of_scope",
                  "identity_already_linked", "operation_not_allowed"}
CONTRACT_STATUSES = {400, 401, 403, 404, 405, 409, 422, 429, 500, 503}


@pytest.fixture(scope="module")
def contract_client():
    """Minimal app with error handlers + a single route for method testing."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/only-get")
    async def _only_get():
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestStatusCodeRemapping:
    """Every framework status carries its own honest class rather than being folded onto one."""

    def test_wrong_method_returns_405(self, contract_client):
        """POST to a GET-only route returns 405 -- the deleted remap table folded it to 400."""
        response = contract_client.post("/only-get")
        assert response.status_code == 405
        assert response.json()["code"] == "method_not_allowed"

    def test_undefined_route_returns_404(self, contract_client):
        """Request to nonexistent path returns 404 with code not_found."""
        response = contract_client.get("/no-such-route")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    def test_response_body_has_only_code_field(self, contract_client):
        """Error responses contain exactly one field: code."""
        response = contract_client.get("/no-such-route")
        body = response.json()
        assert list(body.keys()) == ["code"]

    def test_error_code_is_from_contract_set(self, contract_client):
        """Error code value is one the registry declares."""
        response = contract_client.post("/only-get")
        assert response.json()["code"] in CONTRACT_CODES


class TestOpenAPISchema:
    """ERR-04: ErrorResponse in OpenAPI, no 422."""

    def test_openapi_schema_has_422(self):
        """Every route with a request body should have a 422 response."""
        schema = real_app.openapi()
        for path, methods in schema.get("paths", {}).items():
            for method, op in methods.items():
                if isinstance(op, dict) and "requestBody" in op:
                    responses = op.get("responses", {})
                    assert "422" in responses, (f"422 missing in {method.upper()} {path}")

    def test_openapi_schema_contains_error_response(self):
        """ErrorResponse model must appear in the schema components."""
        schema = real_app.openapi()
        schemas = schema.get("components", {}).get("schemas", {})
        assert "ErrorResponse" in schemas

    def test_openapi_error_response_has_code_field(self):
        """ErrorResponse schema must have a 'code' property."""
        schema = real_app.openapi()
        error_schema = schema["components"]["schemas"]["ErrorResponse"]
        assert "code" in error_schema.get("properties", {})

    def test_openapi_error_response_code_is_enum(self):
        """ErrorResponse.code must enumerate exactly the registered codes."""
        schema = real_app.openapi()
        error_schema = schema["components"]["schemas"]["ErrorResponse"]
        code_prop = error_schema["properties"]["code"]
        enum_values = set(code_prop.get("enum", []))
        assert enum_values == CONTRACT_CODES
