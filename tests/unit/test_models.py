import json
from base64 import b64encode
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from nativespeaker.api.auth.google_play import developer_notification_from
from nativespeaker.api.errors import AnalysisError, AppError, InvalidChatError, UnsupportedLanguageError
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
)
from nativespeaker.api.schemas.webhooks import (
    APP_STORE_ENVELOPE_LIMIT,
    PUBSUB_DATA_LIMIT,
    AppStoreNotificationRequest,
    PubSubPushMessage,
    PubSubPushRequest,
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

    def test_an_empty_phrase_is_refused(self):
        """WR-22: `create_chat` charges the monthly credit before the provider sees the phrase,
        so an empty one has to be the framework's 422 rather than a spent, unrefundable credit."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(phrase="", lang="en")
        assert "phrase" in str(exc_info.value)

    def test_an_empty_language_is_refused(self):
        """WR-63: the empty string is not a language code. Falsy, it slipped past the service's
        supported-language check, was persisted, and was then reported back as the chat's language."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(phrase="Hello world", lang="")
        assert "lang" in str(exc_info.value)


class TestMessageRequest:
    def test_valid_request(self):
        request = MessageRequest(message="Why is that wrong?")
        assert request.message == "Why is that wrong?"

    def test_missing_question(self):
        with pytest.raises(ValidationError):
            MessageRequest()

    def test_an_empty_message_is_refused(self):
        """WR-22, for the reason the empty phrase is: `send_message` charges before it asks."""
        with pytest.raises(ValidationError):
            MessageRequest(message="")


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
        assert isinstance(error, AppError)

    def test_invalid_chat_error(self):
        cid = uuid4()
        error = InvalidChatError(cid)
        assert error.chat_id == cid
        assert str(cid) in str(error)
        assert isinstance(error, AppError)

    def test_service_error_base(self):
        error = AppError("Base error")
        assert isinstance(error, Exception)


class TestPurchaseProviderEnum:
    """The Python mirror of the pre-existing database enum type, whose names deliberately differ."""

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
        """ORM-level only. The table has no database primary key by design (migration:327-338)."""
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


# Apple's body alone. WR-25 moved Google's bound into `developer_notification_from`, because
# Pub/Sub redelivers every non-2xx and a 422 here is a message the subscription never clears.
_BOUNDED_WEBHOOK_FIELDS = [
    (AppStoreNotificationRequest, "signedPayload", {}, APP_STORE_ENVELOPE_LIMIT),
]

# The upper end of the range a real V2 notification occupies, certificate chain included.
REALISTIC_APP_STORE_ENVELOPE = 24 * 1024


class TestTheUnauthenticatedWebhookBodiesAreBounded:
    """WR-03. These are the only two routes outside the gateway JWT policy, so the body is the credential."""

    @pytest.mark.parametrize("model,field,other,limit", _BOUNDED_WEBHOOK_FIELDS)
    def test_an_oversized_body_is_refused(self, model, field, other, limit):
        with pytest.raises(ValidationError) as refusal:
            model(**other, **{field: "a" * (limit + 1)})

        assert f"at most {limit}" in str(refusal.value)

    @pytest.mark.parametrize("model,field,other,limit", _BOUNDED_WEBHOOK_FIELDS)
    def test_a_body_at_the_bound_is_accepted(self, model, field, other, limit):
        """The control: a bound set below a real envelope would refuse live deliveries."""
        body = model(**other, **{field: "a" * limit})

        assert len(getattr(body, field)) == limit

    @pytest.mark.parametrize("model,field,other,limit", _BOUNDED_WEBHOOK_FIELDS)
    def test_an_empty_body_is_still_refused(self, model, field, other, limit):
        with pytest.raises(ValidationError):
            model(**other, **{field: ""})

    def test_the_pubsub_body_carries_no_bound_of_its_own_any_more(self):
        """WR-25: the bound is the decoder's, so an out-of-range body is acknowledged, not retried."""
        oversized = PubSubPushMessage(data="a" * (PUBSUB_DATA_LIMIT + 1))

        assert len(oversized.data) == PUBSUB_DATA_LIMIT + 1
        assert PubSubPushMessage(data="").data == ""

    def test_the_body_needs_nothing_but_the_data_field(self):
        """WR-25: `messageId` was required and unread, so an envelope shape change that dropped or
        renamed it was a 422 Pub/Sub retries forever -- in exchange for validating nothing."""
        assert PubSubPushMessage(data="ZQ==").data == "ZQ=="

    def test_an_attributes_only_message_validates_and_reaches_the_decoder(self):
        """WR-63: Pub/Sub permits a message with attributes and no data, and a 422 for one is a
        delivery this subscription retries until retention expires."""
        body = PubSubPushRequest(message={"attributes": {"k": "v"}})

        assert body.message.data == ""
        assert developer_notification_from(body.message.data) is None

    def test_a_delivery_still_carrying_the_message_id_validates_unchanged(self):
        """The control: real Pub/Sub sends `messageId` on every push, so dropping the declaration
        must leave those bodies accepted rather than merely stop requiring the field."""
        body = PubSubPushRequest(message={"messageId": "2280000000000001", "data": "ZQ=="})

        assert body.message.data == "ZQ=="

    def test_the_decoder_drops_an_out_of_range_body_rather_than_refusing_it(self):
        """The bound still fires; it just answers the way the undecodable case already answered."""
        assert developer_notification_from("a" * (PUBSUB_DATA_LIMIT + 1)) is None

    def test_the_decoder_drops_an_attributes_only_body_the_same_way(self):
        """WR-01: the same answer, but not the same event -- an empty body breached no bound.
        The two records are told apart in
        `test_google_play_notifications.py::TestTheEmptyBodyAndTheBreachedBoundAreRecordedApart`."""
        assert developer_notification_from("") is None

    def test_a_body_at_the_bound_still_reaches_the_decoder(self):
        """The control: a bound off by one here would drop every genuine RTDN at the ceiling."""
        payload = b64encode(json.dumps({"packageName": "com.example",
                                        "eventTimeMillis": 1}).encode()).decode()
        assert len(payload) <= PUBSUB_DATA_LIMIT
        assert developer_notification_from(payload) is not None

    def test_an_envelope_the_size_apple_really_sends_is_accepted(self):
        """CR-01. Apple carries the certificate chain three times, so a 16 KB bound refused every genuine delivery."""
        body = AppStoreNotificationRequest(signedPayload="a" * REALISTIC_APP_STORE_ENVELOPE)

        assert len(body.signedPayload) == REALISTIC_APP_STORE_ENVELOPE
