import pytest
from pydantic import ValidationError

from app.schema import (
    AnalyzeRequest,
    Issue,
    AnalyzeResponse,
    ExamplesResponse,
)
from app.exceptions import (
    UnsupportedLanguageError,
    AnalysisError,
    ServiceError,
)


class TestAnalyzeRequest:
    def test_valid_request(self):
        request = AnalyzeRequest(phrase="Hello world", lang="en")
        assert request.phrase == "Hello world"
        assert request.lang == "en"

    def test_default_language(self):
        request = AnalyzeRequest(phrase="Hello world")
        assert request.lang == "en"

    def test_missing_phrase(self):
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeRequest(lang="en")
        assert "phrase" in str(exc_info.value)


class TestIssue:
    def test_valid_issue(self):
        issue = Issue(
            phrase_part="going to home",
            explanation="Should be 'going home'"
        )
        assert issue.phrase_part == "going to home"
        assert issue.explanation == "Should be 'going home'"

    def test_issue_missing_fields(self):
        with pytest.raises(ValidationError):
            Issue(phrase_part="going to home")


class TestAnalyzeResponse:
    def test_valid_response(self):
        response = AnalyzeResponse(
            phrase="Test phrase",
            lang="en",
            issues=[],
            alternatives=[],
            assessment="Good"
        )
        assert response.phrase == "Test phrase"
        assert response.lang == "en"
        assert response.assessment == "Good"

    def test_response_with_issues_and_alternatives(self):
        issue = Issue(phrase_part="going to home", explanation="Remove 'to'")
        response = AnalyzeResponse(
            phrase="Test",
            lang="en",
            issues=[issue],
            alternatives=["I am going home."],
            assessment="Needs work"
        )
        assert len(response.issues) == 1
        assert len(response.alternatives) == 1
        assert response.alternatives[0] == "I am going home."


class TestExamplesResponse:
    def test_valid_response(self):
        response = ExamplesResponse(
            lang="en",
            examples=["Example 1", "Example 2"]
        )
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

    def test_service_error_base(self):
        error = ServiceError("Base error")
        assert isinstance(error, Exception)
