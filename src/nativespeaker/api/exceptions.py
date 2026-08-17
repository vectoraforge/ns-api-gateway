import logging
from typing import Literal

ErrorCode = Literal["invalid_request",
                    "validation_error",
                    "unauthorized",
                    "not_found",
                    "service_unavailable",
                    "internal_error",
                    "quota_exceeded",
                    "out_of_scope",
                    # Shared client-visible auth classes
                    "auth_required",
                    "preauth_identity_not_allowed",
                    "account_unavailable",
                    "identity_already_linked",
                    "challenge_required",
                    "proof_rejected",
                    "operation_not_allowed",
                    "verification_required",
                    "device_grant_exhausted",
                    "account_already_claimed",
                    "verification_temporarily_unavailable",
                    "registration_temporarily_unavailable"]


class ServiceError(Exception):
    """Base exception for service layer errors."""
    status_code: int = 500
    error_code: ErrorCode = "internal_error"
    log_level: int | None = None

    def extra_headers(self) -> dict[str, str] | None:
        return None


class UnsupportedLanguageError(ServiceError):
    """Raised when an unsupported language is requested"""
    status_code = 400
    error_code = "invalid_request"

    def __init__(self, lang: str, supported: list[str]):
        self.lang = lang
        self.supported = supported
        super().__init__(f"Language '{lang}' not supported. Supported: {', '.join(supported)}")


class AnalysisError(ServiceError):
    """Raised when phrase analysis fails"""
    status_code = 500
    error_code = "internal_error"
    log_level = logging.ERROR


class TransientLLMError(AnalysisError):
    """Raised when all retry attempts failed due to a transient LLM error.
    __cause__ holds the original exception from the last failed attempt."""
    status_code = 503
    error_code = "service_unavailable"
    log_level = None


class PermanentLLMError(AnalysisError):
    """Raised when the LLM call failed with a non-transient error (no retry possible).
    __cause__ holds the original exception."""
    status_code = 503
    error_code = "service_unavailable"
    log_level = None


class InvalidChatError(ServiceError):
    status_code = 404
    error_code = "not_found"

    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")


class InvalidCursorError(ServiceError):
    status_code = 400
    error_code = "invalid_request"

    def __init__(self):
        super().__init__("Invalid cursor")


class PageSizeLimitError(ServiceError):
    status_code = 400
    error_code = "invalid_request"

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Limit exceeds maximum page size of {limit}")


class QueueFullError(ServiceError):
    status_code = 503
    error_code = "service_unavailable"

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM queue is full")

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}


class CircuitOpenError(ServiceError):
    status_code = 503
    error_code = "service_unavailable"

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM circuit breaker is open")

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}


class QuotaExceededError(ServiceError):
    status_code = 429
    error_code = "quota_exceeded"


class ChatHistoryLimitError(ServiceError):
    status_code = 400
    error_code = "invalid_request"

    def __init__(self, max_messages: int):
        self.max_messages = max_messages
        super().__init__("Chat history limit reached")


class OutOfScopeError(ServiceError):
    status_code = 400
    error_code = "out_of_scope"

    def __init__(self):
        super().__init__("The request is outside the scope of linguistic analysis")


class AuthenticationError(ServiceError):
    """Base for authentication failures -- maps to 401."""
    status_code = 401
    error_code = "unauthorized"
    log_level = logging.WARNING

    def extra_headers(self) -> dict[str, str]:
        return {"WWW-Authenticate": "Bearer"}


class WebhookVerificationError(ServiceError):
    """JWS signature verification failed on incoming webhook."""
    status_code = 400
    error_code = "validation_error"


class DatabaseNotInitializedError(ServiceError):
    """Raised when DB session factory is not initialized -- maps to 500."""
    status_code = 500
    error_code = "internal_error"
    log_level = logging.ERROR

    def __init__(self):
        super().__init__("Database session factory is not initialized")
