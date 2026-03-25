from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from nativespeaker.api.models import AIContent, HumanContent
from nativespeaker.api.schema import ChatRequest, ChatResponse, ExamplesResponse, MessageRequest, MessageResponse
from nativespeaker.api.models.content import Issue
from nativespeaker.api.exceptions import AnalysisError, InvalidChatError, ServiceError, UnsupportedLanguageError


class TestChatRequest:
    def test_valid_request(self):
        request = ChatRequest(phrase="Hello world", lang="en")
        assert request.phrase == "Hello world"
        assert request.lang == "en"

    def test_with_comment(self):
        request = ChatRequest(phrase="Hello world", comment="Is this natural?", lang="en")
        assert request.comment == "Is this natural?"

    def test_lang_optional(self):
        request = ChatRequest(phrase="Hello world")
        assert request.lang is None

    def test_missing_phrase(self):
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(lang="en")
        assert "phrase" in str(exc_info.value)


class TestMessageRequest:
    def test_valid_request(self):
        request = MessageRequest(content="Why is that wrong?")
        assert request.content == "Why is that wrong?"

    def test_missing_content(self):
        with pytest.raises(ValidationError):
            MessageRequest()


class TestIssue:
    def test_valid_issue(self):
        issue = Issue(text_part="going to home", explanation="Should be 'going home'")
        assert issue.text_part == "going to home"
        assert issue.explanation == "Should be 'going home'"

    def test_issue_missing_fields(self):
        with pytest.raises(ValidationError):
            Issue(text_part="going to home")


class TestMessageResponse:
    def test_valid_response(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = MessageResponse(chat_id=cid, role="ai",
                                   content=AIContent(response="Good"),
                                   created_at=now)
        assert response.chat_id == cid
        assert response.role == "ai"
        assert response.content == AIContent(response="Good")
        assert response.created_at == now

    def test_ai_content_serialization(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = MessageResponse(
            chat_id=cid, role="ai",
            content=AIContent(
                response="Looks good",
                issues=[Issue(text_part="going to home", explanation="Drop 'to'")],
                suggestions=["going home"]),
            created_at=now)
        dumped = response.model_dump()
        assert dumped["content"]["response"] == "Looks good"
        assert len(dumped["content"]["issues"]) == 1
        assert dumped["content"]["issues"][0]["text_part"] == "going to home"
        assert dumped["content"]["suggestions"] == ["going home"]

    def test_human_content_serialization(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = MessageResponse(
            chat_id=cid, role="human",
            content=HumanContent(phrase="Hello", comment="Test"),
            created_at=now)
        dumped = response.model_dump()
        assert dumped["content"]["phrase"] == "Hello"
        assert dumped["content"]["comment"] == "Test"

    def test_content_never_empty(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = MessageResponse(
            chat_id=cid, role="ai",
            content=AIContent(response="Ok"),
            created_at=now)
        dumped = response.model_dump()
        assert dumped["content"] != {}
        assert "response" in dumped["content"]


class TestChatResponse:
    def test_valid_response(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = ChatResponse(chat_id=cid, title="Test phrase",
                                created_at=now, lang="en")
        assert response.chat_id == cid
        assert response.title == "Test phrase"
        assert response.lang == "en"

    def test_lang_optional(self):
        cid = uuid4()
        response = ChatResponse(chat_id=cid, title="Test",
                                created_at=datetime.now(UTC))
        assert response.lang is None


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
