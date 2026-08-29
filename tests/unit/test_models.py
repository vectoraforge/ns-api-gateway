from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from nativespeaker.api.errors import AnalysisError, InvalidChatError, ServiceError, UnsupportedLanguageError
from nativespeaker.api.schemas.api import (
    ChatRequest,
    ChatResponse,
    ExamplesResponse,
    MessageRequest,
    MessageResponse,
)
from nativespeaker.api.schemas.llm import (
    AnalyzeInput,
    AnalyzeResponse,
    FollowUpInput,
    FollowUpResponse,
    Issue,
    RejectResponse,
)
from nativespeaker.api.tables import PurchaseProvider, StorePurchaseToken


class TestChatRequest:
    def test_valid_request(self):
        request = ChatRequest(phrase="Hello world", lang="en")
        assert request.phrase == "Hello world"
        assert request.lang == "en"

    def test_with_context(self):
        request = ChatRequest(phrase="Hello world", context="Is this natural?", lang="en")
        assert request.context == "Is this natural?"

    def test_lang_optional(self):
        request = ChatRequest(phrase="Hello world")
        assert request.lang is None

    def test_missing_phrase(self):
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(lang="en")
        assert "phrase" in str(exc_info.value)


class TestMessageRequest:
    def test_valid_request(self):
        request = MessageRequest(message="Why is that wrong?")
        assert request.message == "Why is that wrong?"

    def test_missing_question(self):
        with pytest.raises(ValidationError):
            MessageRequest()


class TestIssue:
    def test_valid_issue(self):
        issue = Issue(text_part="going to home", explanation="Should be 'going home'")
        assert issue.text_part == "going to home"
        assert issue.explanation == "Should be 'going home'"

    def test_issue_missing_fields(self):
        with pytest.raises(ValidationError):
            # Omitting the required field is the point of this test.
            Issue(text_part="going to home")  # ty: ignore[missing-argument]


class TestMessageResponse:
    def test_valid_response(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = MessageResponse(chat_id=cid, role="ai",
                                   content={"response": "Good"},
                                   created_at=now)
        assert response.chat_id == cid
        assert response.role == "ai"
        assert response.content == {"response": "Good"}
        assert response.created_at == now

    def test_ai_content_serialization(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = MessageResponse(
            chat_id=cid, role="ai",
            content={"response": "Looks good",
                     "issues": [{"text_part": "going to home", "explanation": "Drop 'to'"}],
                     "suggestions": ["going home"]},
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
            content={"phrase": "Hello", "context": "Test"},
            created_at=now)
        dumped = response.model_dump()
        assert dumped["content"]["phrase"] == "Hello"
        assert dumped["content"]["context"] == "Test"

    def test_content_never_empty(self):
        cid = uuid4()
        now = datetime.now(UTC)
        response = MessageResponse(
            chat_id=cid, role="ai",
            content={"response": "Ok"},
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


class TestAnalyzeInput:
    def test_with_context(self):
        ai = AnalyzeInput(phrase="hello", context="greeting")
        dumped = ai.model_dump(exclude_none=True)
        assert dumped == {"mode": "analyze", "phrase": "hello", "context": "greeting"}

    def test_without_context(self):
        ai = AnalyzeInput(phrase="hello")
        dumped = ai.model_dump(exclude_none=True)
        assert dumped == {"mode": "analyze", "phrase": "hello"}
        assert "context" not in dumped


class TestFollowUpInput:
    def test_valid(self):
        fi = FollowUpInput(message="why?")
        dumped = fi.model_dump(exclude_none=True)
        assert dumped == {"mode": "follow_up", "message": "why?"}


class TestAnalyzeResponse:
    def test_valid(self):
        ar = AnalyzeResponse(resolved_mode="analyze", response="ok",
                             issues=[Issue(text_part="x", explanation="y")],
                             suggestions=["fix"])
        assert ar.response == "ok"
        assert len(ar.issues) == 1
        assert ar.suggestions == ["fix"]

    def test_empty_issues_and_suggestions(self):
        ar = AnalyzeResponse(resolved_mode="analyze", response="ok",
                             issues=[], suggestions=[])
        assert ar.issues == []
        assert ar.suggestions == []

    # Both list fields default to empty rather than raising on omission.
    def test_both_lists_default_to_empty(self):
        ar = AnalyzeResponse(resolved_mode="analyze", response="Looks good.")
        assert ar.issues == []
        assert ar.suggestions == []

    def test_validates_payload_omitting_both_lists(self):
        ar = AnalyzeResponse.model_validate({"resolved_mode": "analyze", "response": "ok"})
        assert ar.issues == []
        assert ar.suggestions == []

    def test_defaults_are_not_shared_between_instances(self):
        first = AnalyzeResponse(resolved_mode="analyze", response="ok")
        second = AnalyzeResponse(resolved_mode="analyze", response="ok")
        first.issues.append(Issue(text_part="x", explanation="y"))
        first.suggestions.append("fix")
        assert second.issues == []
        assert second.suggestions == []

    def test_explicit_values_still_win_over_defaults(self):
        issue = Issue(text_part="x", explanation="y")
        ar = AnalyzeResponse(resolved_mode="analyze", response="ok",
                             issues=[issue], suggestions=["fix"])
        assert ar.issues == [issue]
        assert ar.suggestions == ["fix"]

    def test_resolved_mode_and_response_stay_required(self):
        with pytest.raises(ValidationError):
            # A truncated provider payload must still fail validation.
            AnalyzeResponse.model_validate({"response": "ok"})
        with pytest.raises(ValidationError):
            AnalyzeResponse.model_validate({"resolved_mode": "analyze"})


class TestFollowUpResponse:
    def test_valid(self):
        fr = FollowUpResponse(resolved_mode="follow_up", response="because...")
        assert fr.response == "because..."


class TestRejectResponse:
    def test_valid(self):
        rr = RejectResponse(resolved_mode="reject", response="out of scope")
        assert rr.response == "out of scope"


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


class TestPurchaseProviderEnum:
    """The Python mirror of the pre-existing crud enum type, whose names deliberately differ."""

    def test_exactly_two_members_in_migration_order(self):
        assert list(PurchaseProvider) == [PurchaseProvider.apple, PurchaseProvider.google_play]

    def test_values_are_the_migration_labels(self):
        assert [member.value for member in PurchaseProvider] == ["apple", "google_play"]


class TestStorePurchaseTokenMapping:
    """Read off the SQLAlchemy Table rather than the annotations, so it describes what was actually built."""

    def test_the_models_package_imports(self):
        """The mapper configures without raising 'could not assemble any primary key columns'."""
        from nativespeaker.api import tables as models_package

        assert models_package.StorePurchaseToken is StorePurchaseToken

    def test_maps_core_store_purchase_tokens(self):
        assert StorePurchaseToken.__tablename__ == "store_purchase_tokens"
        assert StorePurchaseToken.__table_args__ == {"schema": "core"}

    def test_orm_primary_key_is_the_composite_user_id_provider(self):
        """ORM-level only. The table has no crud primary key by design (migration:327-338)."""
        columns = StorePurchaseToken.__table__.primary_key.columns
        assert {column.name for column in columns} == {"user_id", "provider"}

    def test_column_set_is_exactly_the_four_table_columns(self):
        """No `id`, no surrogate key -- the mapper adds nothing the migration did not declare."""
        columns = StorePurchaseToken.__table__.columns
        assert {column.name for column in columns} == {
            "user_id", "provider", "identity_value", "created_at",
        }

    def test_provider_column_binds_the_pre_existing_database_enum_type(self):
        """The explicit name and schema hold the two together; without them SQLAlchemy emits a second enum type."""
        provider_type = StorePurchaseToken.__table__.c.provider.type
        assert provider_type.name == "subscription_provider"
        assert provider_type.schema == "core"
        assert sorted(provider_type.enums) == ["apple", "google_play"]
