class ServiceError(Exception):
    """Base exception for service layer errors"""

    pass


class UnsupportedLanguageError(ServiceError):
    """Raised when an unsupported language is requested"""

    def __init__(self, lang: str, supported: list[str]):
        self.lang = lang
        self.supported = supported
        super().__init__(f"Language '{lang}' not supported. Supported: {', '.join(supported)}")


class AnalysisError(ServiceError):
    """Raised when phrase analysis fails"""

    pass


class TransientLLMError(AnalysisError):
    """Raised when all retry attempts failed due to a transient LLM error.
    __cause__ holds the original exception from the last failed attempt."""

    pass


class PermanentLLMError(AnalysisError):
    """Raised when the LLM call failed with a non-transient error (no retry possible).
    __cause__ holds the original exception."""

    pass


class InvalidChatError(ServiceError):
    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")


class InvalidCursorError(ServiceError):
    def __init__(self):
        super().__init__("Invalid cursor")


class PageSizeLimitError(ServiceError):
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Limit exceeds maximum page size of {limit}")


class QueueFullError(ServiceError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM queue is full")


class CircuitOpenError(ServiceError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM circuit breaker is open")


class ChatHistoryLimitError(ServiceError):
    def __init__(self, max_human: int, max_assistant: int):
        self.max_human = max_human
        self.max_assistant = max_assistant
        super().__init__("Chat history limit reached")


class MessageTooLargeError(ServiceError):
    def __init__(self, role: str, limit: int):
        self.role = role
        self.limit = limit
        super().__init__(f"{role} message exceeds {limit} characters")


class AuthenticationError(ServiceError):
    """Base for authentication failures — maps to 401."""

    pass


class ChatOwnershipError(ServiceError):
    """Raised when a user accesses a chat they don't own — maps to 404."""

    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")


class DatabaseNotInitializedError(ServiceError):
    """Raised when DB session factory is not initialized — maps to 500."""

    def __init__(self):
        super().__init__("Database session factory is not initialized")
