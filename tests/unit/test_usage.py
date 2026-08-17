"""Tests for monthly quota enforcement via require_quota dependency and QuotaExceededError contract."""
from unittest.mock import MagicMock, patch

import pytest

import nativespeaker.api.app.dependencies as dep_module
from nativespeaker.api.app.dependencies import require_quota
from nativespeaker.api.database.usage import current_period
from nativespeaker.api.exceptions import QuotaExceededError
from unit.conftest import TEST_USER, FakeQuotaStore, grant_row, quota_request


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
    """The quota-checked request path: `quota_checked_request` admission first, then the lazy
    monthly rollover sequence against the user's single effective grant."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def store(self):
        return FakeQuotaStore(rows=[grant_row(user_id=TEST_USER.id, monthly_credits=10)],
                              usage=(current_period(), 0))

    @pytest.mark.asyncio
    async def test_require_quota_raises_when_exhausted(self, mock_db, store):
        """A grant whose counter has reached its tier's allowance is ordinary exhaustion."""
        store.rows = [grant_row(user_id=TEST_USER.id, monthly_credits=10)]
        store.usage = (current_period(), 10)
        with patch.object(dep_module, "QuotaStoreDB", return_value=store):
            with pytest.raises(QuotaExceededError):
                await require_quota(quota_request(), user=TEST_USER, db=mock_db)
        assert store.increments == []

    @pytest.mark.asyncio
    async def test_require_quota_raises_when_no_effective_grant_exists(self, mock_db, store):
        """No effective grant means an allowance of zero, and no counter is touched."""
        store.rows = []
        with patch.object(dep_module, "QuotaStoreDB", return_value=store):
            with pytest.raises(QuotaExceededError):
                await require_quota(quota_request(), user=TEST_USER, db=mock_db)
        assert store.usage_reads == []
        assert store.increments == []

    @pytest.mark.asyncio
    async def test_require_quota_passes_when_under_limit(self, mock_db, store):
        """require_quota completes silently when under quota."""
        with patch.object(dep_module, "QuotaStoreDB", return_value=store):
            result = await require_quota(quota_request(), user=TEST_USER, db=mock_db)
        assert result is None
        assert len(store.increments) == 1

    @pytest.mark.asyncio
    async def test_require_quota_meters_the_grant_not_the_user(self, mock_db, store):
        """The counter is keyed by the effective grant, and the allowance is its tier\'s."""
        with patch.object(dep_module, "QuotaStoreDB", return_value=store):
            await require_quota(quota_request(), user=TEST_USER, db=mock_db)
        grant_id, period = store.increments[0]
        assert grant_id == store.rows[0].grant_id
        assert grant_id != TEST_USER.id
        assert period == current_period()

    @pytest.mark.asyncio
    async def test_require_quota_creates_the_store_with_the_session(self, mock_db, store):
        """require_quota builds its store on the injected db session."""
        with patch.object(dep_module, "QuotaStoreDB", return_value=store) as MockStore:
            await require_quota(quota_request(), user=TEST_USER, db=mock_db)
        MockStore.assert_called_once_with(mock_db)


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
