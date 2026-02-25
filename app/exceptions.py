
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


class InvalidChatError(ServiceError):
    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")
