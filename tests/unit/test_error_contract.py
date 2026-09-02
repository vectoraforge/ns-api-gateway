"""The contract under test is that every branch within an error class returns identical copy."""
from typing import cast
from uuid import uuid7

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from nativespeaker.api.app.error_handlers import app_error_handler, register_exception_handlers
from nativespeaker.api.app.main import app as real_app
from nativespeaker.api.errors import (
    MissingPurchaseTokenError,
    MissingUsageRowError,
    MultipleEffectiveGrantsError,
    UnknownTierError,
)
from nativespeaker.api.tables.purchases import PurchaseProvider

# Written out rather than derived from the tree: the mirror that catches an undecided code shipping.
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
        """POST to a GET-only route returns 405."""
        response = contract_client.post("/only-get")
        assert response.status_code == 405
        assert response.json()["code"] == "method_not_allowed"

    def test_undefined_route_returns_404(self, contract_client):
        """Request to nonexistent path returns 404 with code not_found."""
        response = contract_client.get("/no-such-route")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


# The merged handler reads nothing off the request, which is what lets these cases skip building one.
NO_REQUEST = cast(Request, None)


def _id_carrying_cases():
    """The four classes that format server-side identifiers into their own message."""
    grant_id, user_id, token_user_id = uuid7(), uuid7(), uuid7()
    return [
        (MissingUsageRowError(grant_id), [str(grant_id)]),
        (MultipleEffectiveGrantsError(3, user_id), [str(user_id), "3"]),
        (UnknownTierError("a-private-tier-id", grant_id), ["a-private-tier-id", str(grant_id)]),
        (MissingPurchaseTokenError(token_user_id, [PurchaseProvider.apple]),
         [str(token_user_id), PurchaseProvider.apple.value]),
    ]


class TestTheBodyStaysOneFieldAndCarriesNoIdentifier:
    """The message reaches the log and the traceback; the body is built from `code` alone."""

    @pytest.mark.parametrize("exc,secrets", _id_carrying_cases(),
                             ids=["missing_usage_row", "multiple_grants", "unknown_tier",
                                  "missing_purchase_token"])
    async def test_the_body_is_exactly_the_code_key(self, exc, secrets):
        response = await app_error_handler(NO_REQUEST, exc)
        assert response.status_code == 500
        assert response.body == b'{"code":"internal_error"}'

    @pytest.mark.parametrize("exc,secrets", _id_carrying_cases(),
                             ids=["missing_usage_row", "multiple_grants", "unknown_tier",
                                  "missing_purchase_token"])
    async def test_no_identifier_the_exception_stored_appears_in_the_bytes(self, exc, secrets):
        response = await app_error_handler(NO_REQUEST, exc)
        for secret in secrets:
            assert secret.encode() not in response.body
            assert secret.encode() not in str(response.headers).encode()

    @pytest.mark.parametrize("exc,secrets", _id_carrying_cases(),
                             ids=["missing_usage_row", "multiple_grants", "unknown_tier",
                                  "missing_purchase_token"])
    def test_the_premise_holds_and_each_message_really_names_its_identifiers(self, exc, secrets):
        """The control: without it the case above would pass on a class that stored nothing."""
        for secret in secrets:
            assert secret in str(exc)


class TestOpenAPISchema:
    """The emitted schema documents 422 and enumerates exactly the registered codes."""

    def test_openapi_schema_has_422(self):
        """Every route with a request body should have a 422 response."""
        schema = real_app.openapi()
        for path, methods in schema.get("paths", {}).items():
            for method, op in methods.items():
                if isinstance(op, dict) and "requestBody" in op:
                    responses = op.get("responses", {})
                    assert "422" in responses, (f"422 missing in {method.upper()} {path}")

    def test_openapi_error_response_code_is_enum(self):
        """ErrorResponse.code must enumerate exactly the registered codes."""
        schema = real_app.openapi()
        error_schema = schema["components"]["schemas"]["ErrorResponse"]
        code_prop = error_schema["properties"]["code"]
        enum_values = set(code_prop.get("enum", []))
        assert enum_values == CONTRACT_CODES
