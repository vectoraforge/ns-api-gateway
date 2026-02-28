from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.exceptions import (
    AnalysisError,
    InvalidChatError,
    ServiceError,
    UnsupportedLanguageError,
)
from app.schema import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatMessageRequest,
    ExamplesResponse,
    Issue,
)


class TestAnalyzeRequest:
    def test_valid_request(self):
        request = AnalyzeRequest(text="Hello world", lang="en")
        assert request.text == "Hello world"
        assert request.lang == "en"

    def test_default_language(self):
        request = AnalyzeRequest(text="Hello world")
        assert request.lang == "en"

    def test_missing_text(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeRequest(lang="en")
        assert "text" in str(exc_info.value)

    def test_with_chat_id(self):
        cid = uuid4()
        request = AnalyzeRequest(text="Hello", chat_id=cid)
        assert request.chat_id == cid

    def test_chat_id_defaults_to_none(self):
        request = AnalyzeRequest(text="Hello")
        assert request.chat_id is None


class TestIssue:
    def test_valid_issue(self):
        issue = Issue(text_part="going to home", explanation="Should be 'going home'")
        assert issue.text_part == "going to home"
        assert issue.explanation == "Should be 'going home'"

    def test_issue_missing_fields(self):
        with pytest.raises(ValidationError):
            Issue(text_part="going to home")


class TestAnalyzeResponse:
    def test_valid_response(self):
        cid = uuid4()
        response = AnalyzeResponse(
            text="Test phrase", lang="en", chat_id=cid, issues=[], alternatives=[], assessment="Good"
        )
        assert response.text == "Test phrase"
        assert response.lang == "en"
        assert response.chat_id == cid
        assert response.assessment == "Good"

    def test_response_with_issues_and_alternatives(self):
        issue = Issue(text_part="going to home", explanation="Remove 'to'")
        response = AnalyzeResponse(
            text="Test",
            lang="en",
            chat_id=uuid4(),
            issues=[issue],
            alternatives=["I am going home."],
            assessment="Needs work",
        )
        assert len(response.issues) == 1
        assert len(response.alternatives) == 1
        assert response.alternatives[0] == "I am going home."


class TestChatModels:
    def test_chat_message_request(self):
        req = ChatMessageRequest(text="Why is that wrong?")
        assert req.text == "Why is that wrong?"


class TestExamplesResponse:
    def test_valid_response(self):
        response = ExamplesResponse(lang="en", examples=["Example 1", "Example 2"])
        assert response.lang == "en"
        assert len(response.examples) == 2


class TestExceptions:
    def test_unsupported_language_error(self):
        error = UnsupportedLanguageError("fr", ["en", "es"])
        assert error.lang == "fr"
        assert error.supported == ["en", "es"]
        assert "fr" in str(error)
        assert "en" in str(error)

    def test_analysis_error(self):
        error = AnalysisError("Something went wrong")
        assert "Something went wrong" in str(error)
        assert isinstance(error, ServiceError)

    def test_invalid_chat_error(self):
        cid = uuid4()
        error = InvalidChatError(cid)
        assert error.chat_id == cid
        assert str(cid) in str(error)
        assert isinstance(error, ServiceError)

    def test_service_error_base(self):
        error = ServiceError("Base error")
        assert isinstance(error, Exception)
