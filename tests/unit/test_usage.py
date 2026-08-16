"""Tests for monthly quota enforcement via require_quota dependency and QuotaExceededError contract."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import nativespeaker.api.app.dependencies as dep_module
from nativespeaker.api.app.dependencies import require_quota
from nativespeaker.api.exceptions import QuotaExceededError
from nativespeaker.api.models import SubscriptionPlan
from unit.conftest import TEST_USER


class TestQuotaExceededError:
    """Error contract: QuotaExceededError returns 429 with quota_exceeded code."""

    def test_status_code(self):
        assert QuotaExceededError.status_code == 429

    def test_error_code(self):
        assert QuotaExceededError.error_code == "quota_exceeded"

    def test_message(self):
        err = QuotaExceededError("Monthly quota exceeded")
        assert str(err) == "Monthly quota exceeded"


class TestRequireQuota:
    """require_quota dependency raises QuotaExceededError when quota exhausted, passes silently otherwise."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.quotas = {SubscriptionPlan.free: 10,
                         SubscriptionPlan.silver: 50,
                         SubscriptionPlan.gold: 200,
                         SubscriptionPlan.platinum: 1000}
        return config

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_require_quota_raises_when_exhausted(self, mock_db, mock_config):
        """require_quota raises QuotaExceededError when try_increment returns False."""
        mock_usage = AsyncMock()
        mock_usage.try_increment = AsyncMock(return_value=False)
        with patch.object(dep_module, "UsageDB", return_value=mock_usage):
            with pytest.raises(QuotaExceededError):
                await require_quota(user=TEST_USER, db=mock_db, config=mock_config)

    @pytest.mark.asyncio
    async def test_require_quota_passes_when_under_limit(self, mock_db, mock_config):
        """require_quota completes silently when under quota."""
        mock_usage = AsyncMock()
        mock_usage.try_increment = AsyncMock(return_value=True)
        with patch.object(dep_module, "UsageDB", return_value=mock_usage):
            result = await require_quota(user=TEST_USER, db=mock_db, config=mock_config)
        assert result is None

    @pytest.mark.asyncio
    async def test_require_quota_calls_try_increment_with_correct_args(self, mock_db, mock_config):
        """require_quota passes user_id, current month, and monthly_quota to try_increment."""
        mock_usage = AsyncMock()
        mock_usage.try_increment = AsyncMock(return_value=True)
        with patch.object(dep_module, "UsageDB", return_value=mock_usage):
            await require_quota(user=TEST_USER, db=mock_db, config=mock_config)
        mock_usage.try_increment.assert_called_once()
        call_args = mock_usage.try_increment.call_args
        assert call_args.args[0] == TEST_USER.id  # user_id
        assert isinstance(call_args.args[1], str)  # month string like "2026-03"
        assert call_args.args[2] == 10  # free tier quota

    @pytest.mark.asyncio
    async def test_require_quota_creates_usage_db_with_session(self, mock_db, mock_config):
        """require_quota creates UsageDB with the injected db session."""
        mock_usage = AsyncMock()
        mock_usage.try_increment = AsyncMock(return_value=True)
        with patch.object(dep_module, "UsageDB", return_value=mock_usage) as MockUsageDB:
            await require_quota(user=TEST_USER, db=mock_db, config=mock_config)
        MockUsageDB.assert_called_once_with(mock_db)


class TestQuotaViaHTTP:
    """HTTP-level quota enforcement -- POST /chats returns 429 when require_quota raises."""

    def test_create_chat_returns_429_when_quota_exhausted(self, client):
        """POST /chats returns 429 when require_quota override raises QuotaExceededError."""
        client.app.dependency_overrides[require_quota] = _raise_quota_exceeded
        response = client.post("/chats", json={"phrase": "test phrase"})
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"

    def test_send_message_returns_429_when_quota_exhausted(self, client):
        """POST /chats/{id} returns 429 when require_quota override raises QuotaExceededError."""
        import uuid
        client.app.dependency_overrides[require_quota] = _raise_quota_exceeded
        response = client.post(f"/chats/{uuid.uuid4()}", json={"message": "test"})
        assert response.status_code == 429
        assert response.json()["code"] == "quota_exceeded"


def _raise_quota_exceeded():
    raise QuotaExceededError("Monthly quota exceeded")
