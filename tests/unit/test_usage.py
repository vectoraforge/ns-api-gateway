"""Tests for monthly quota enforcement via UsageDB and ChatService integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.exceptions import QuotaExceededError
from app.models import Chat, HumanContent, Message, Role
from tests.unit.conftest import TEST_USER


class TestQuotaExceededError:
    """Error contract: QuotaExceededError returns 429 with rate_limited code."""

    def test_status_code(self):
        assert QuotaExceededError.status_code == 429

    def test_error_code(self):
        assert QuotaExceededError.error_code == "rate_limited"

    def test_message(self):
        err = QuotaExceededError("Monthly quota exceeded")
        assert str(err) == "Monthly quota exceeded"


class TestChatServiceQuota:
    """ChatService raises QuotaExceededError when monthly quota is exhausted."""

    @pytest.mark.asyncio
    async def test_create_chat_quota_exceeded(self, service):
        """create_chat raises QuotaExceededError when try_increment returns False."""
        service.usage_db.try_increment = AsyncMock(return_value=False)
        with pytest.raises(QuotaExceededError):
            await service.create_chat(user_id=TEST_USER.id, phrase="test phrase")

    @pytest.mark.asyncio
    async def test_create_chat_llm_not_called_when_quota_exceeded(self, service):
        """LLM is not invoked when quota is exceeded."""
        service.usage_db.try_increment = AsyncMock(return_value=False)
        with pytest.raises(QuotaExceededError):
            await service.create_chat(user_id=TEST_USER.id, phrase="test phrase")
        service.llm_service.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_message_quota_exceeded(self, service, mock_chats_db):
        """send_message raises QuotaExceededError when try_increment returns False."""
        mock_chat = Chat(id=TEST_USER.id, user_id=TEST_USER.id, title="test", lang="en")
        mock_chat.messages = []
        mock_chats_db.get_chat = AsyncMock(return_value=mock_chat)
        service.usage_db.try_increment = AsyncMock(return_value=False)
        with pytest.raises(QuotaExceededError):
            await service.send_message(chat_id=mock_chat.id,
                                       user_id=TEST_USER.id,
                                       content="test")

    @pytest.mark.asyncio
    async def test_create_chat_allowed_when_under_quota(self, service):
        """create_chat proceeds when try_increment returns True."""
        service.usage_db.try_increment = AsyncMock(return_value=True)
        service.llm_service.ainvoke = AsyncMock(
            return_value={"response": "ok", "issues": [], "suggestions": []}
        )
        result = await service.create_chat(user_id=TEST_USER.id, phrase="test phrase")
        assert result is not None
        service.usage_db.try_increment.assert_called_once()
