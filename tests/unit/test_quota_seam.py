"""D-07's two halves at the seam A-03 settled: nobody is billed for a request the service refuses,
and an exhausted allowance answers 429 with the provider untouched."""
import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, uuid7

import pytest

from nativespeaker.api.config import ResilienceConfig
from nativespeaker.api.errors import (
    ChatHistoryLimitError,
    CircuitOpenError,
    InvalidChatError,
    PermanentLLMError,
    QueueFullError,
    QuotaExceededError,
    ServiceUnavailable,
    TransientLLMError,
    UnsupportedLanguageError,
)
from nativespeaker.api.resilience import Admitted, ResiliencePolicy
from nativespeaker.api.services import ChatService, QuotaService
from nativespeaker.api.tables import (
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    AccessTier,
    Chat,
    ChatRole,
    Message,
    UserMonthlyUsage,
    monthly_period_for,
)
from unit.conftest import TEST_USER_ID

PHRASE = "I am going to home"
GRANT_STARTED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
TIER_ID = "registered"
ALLOWANCE = 50
CHATS_LIMIT = 50
MESSAGES_LIMIT = 50

# The answer a chain returns when the provider is actually reached; only its shape matters here.
LLM_ANSWER = {"resolved_mode": "analyze", "response": "ok", "issues": [], "suggestions": []}


def _resilience_config() -> ResilienceConfig:
    """A gate that never rejects and a breaker that never opens, so a count can only move for one reason."""
    return ResilienceConfig(pool_size=4,
                            queue_size=8,
                            queue_retry_after_seconds=2,
                            timeout_seconds=5.0,
                            retry_max_attempts=3,
                            retry_backoff_base_seconds=0.0,
                            retry_backoff_max_seconds=0.0,
                            circuit_breaker_failure_threshold=100,
                            circuit_breaker_reset_seconds=60)


class RecordingLLM:
    """Counts provider calls and runs them through the real `ResiliencePolicy`, so the breaker is production's."""

    def __init__(self, events: list[str] | None = None, *, transient_failures: int = 0):
        self.events = [] if events is None else events
        self.calls = 0
        self.transient_failures = transient_failures
        self.policy = ResiliencePolicy(_resilience_config())

    @property
    def breaker_failures(self) -> int:
        """The real breaker's own count, read rather than wrapped: `record_failure` is the only thing that moves it."""
        return self.policy._circuit_breaker._failure_count

    def admission(self):
        return self.policy.admission()

    async def ainvoke(self, history, content: str, lang: str, admitted) -> dict:
        return await self.policy.ainvoke(self._answer, admitted)

    async def _answer(self) -> dict:
        # Counted in the operation rather than on entry: a marker on entry fires before admission is held.
        self.calls += 1
        self.events.append("provider_called")
        if self.calls <= self.transient_failures:
            raise TimeoutError(f"scripted transient failure {self.calls}")
        return LLM_ANSWER


def _erased(value: object) -> Any:
    """Drop a declared type, so a deliberately tokenless call is a runtime fact and not a CI diagnostic."""
    return value


def _drain_the_gate(policy: ResiliencePolicy) -> None:
    """Take every in-flight slot, so the next admission is refused deterministically."""
    while True:
        try:
            policy._gate._slots.get_nowait()
        except asyncio.QueueEmpty:
            return


def _take_every_permit(policy: ResiliencePolicy) -> asyncio.Semaphore:
    """Hold the whole provider concurrency budget, so the next `ainvoke` has to wait for one."""
    semaphore = policy._gate._semaphore
    while not semaphore.locked():
        semaphore._value -= 1
    return semaphore


async def _settle() -> None:
    """Yield until a pending task has run as far as it can, without waiting on the clock."""
    for _ in range(10):
        await asyncio.sleep(0)


class _StubResult:
    """Both accessor shapes the resolver uses, over one row list."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


_ENTITY_KEY = {AccessGrant: "grants", UserMonthlyUsage: "usage", AccessTier: "allowance"}


class _RecordingSession:
    """Appends open, commit and close to a shared list, which is what makes their order against the provider visible."""

    def __init__(self, events: list[str], rows: dict):
        self._events = events
        self._rows = rows

    async def __aenter__(self):
        self._events.append("session_opened")
        return self

    async def __aexit__(self, *exc_info) -> bool:
        self._events.append("session_closed")
        return False

    async def exec(self, statement):
        return _StubResult(self._rows[_ENTITY_KEY[statement.column_descriptions[0]["entity"]]])

    async def commit(self) -> None:
        self._events.append("session_committed")

    async def rollback(self) -> None:
        self._events.append("session_rolled_back")


def _effective_grant_rows(*, monthly_used: int = 0):
    """One active grant and its usage row for this calendar month -- the admitted case."""
    grant = AccessGrant(id=uuid7(), user_id=TEST_USER_ID, tier_id=TIER_ID,
                        source=AccessGrantSource.manual, status=AccessGrantStatus.active,
                        starts_at=GRANT_STARTED_AT, ends_at=None)
    usage = UserMonthlyUsage(grant_id=grant.id,
                             monthly_period=monthly_period_for(datetime.now(UTC)),
                             monthly_used=monthly_used)
    return grant, usage


class _RecordingRequestSession:
    """Records the request session's own commit, which is what returns its connection to the pool."""

    def __init__(self, events: list[str]):
        self._events = events

    async def commit(self) -> None:
        self._events.append("request_committed")


def _recording_factory(events: list[str], grant, usage):
    rows = {"grants": [grant], "usage": [usage], "allowance": [ALLOWANCE]}
    return lambda: _RecordingSession(events, rows)


def _llm_double(llm=None) -> Any:
    """`Any` because a stand-in for the provider seam is deliberately not an `LLMService`."""
    return RecordingLLM() if llm is None else llm


def _service(mock_chats_db, *, llm=None, session_factory=None, request_session=None) -> ChatService:
    """The real `ChatService`, so the order of its validations against the charge is the production order."""
    svc = ChatService(db=AsyncMock() if request_session is None else request_session,
                      llm_service=_llm_double(llm),
                      examples={"en": ["Example 1"], "es": ["Ejemplo 1"]},
                      messages_limit=MESSAGES_LIMIT,
                      chats_limit=CHATS_LIMIT,
                      quota_service=QuotaService(
                          session_factory if session_factory is not None else MagicMock()))
    svc.chats_db = mock_chats_db
    return svc


def _raising_charge(monkeypatch, error: BaseException) -> None:
    """Replace the charge with one that refuses, leaving every other line of the service untouched."""

    async def refusing_charge(self, *, user_id) -> None:
        raise error

    monkeypatch.setattr(QuotaService, "charge", refusing_charge)


def _chat_with_ai_messages(count: int) -> Chat:
    chat_id = uuid4()
    chat = Chat(id=chat_id, title="hello", user_id=TEST_USER_ID)
    chat.messages = [Message(chat_id=chat_id, role=ChatRole.ai,
                             content={"resolved_mode": "analyze", "response": "r",
                                      "issues": [], "suggestions": []})
                     for _ in range(count)]
    return chat


class TestAServiceRejectionPrecedesAnyCharge:
    """T-37.4-17: the four rejections the service makes on its own terms must each cost nothing."""

    async def test_an_unsupported_language_is_not_charged(self, service, charge_calls):
        with pytest.raises(UnsupportedLanguageError):
            await service.create_chat(phrase="Bonjour", user_id=TEST_USER_ID, lang="fr")

        assert charge_calls == []

    async def test_an_exceeded_chats_limit_is_not_charged(self, service, mock_chats_db, charge_calls):
        mock_chats_db.count_chats.return_value = CHATS_LIMIT

        with pytest.raises(ChatHistoryLimitError):
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert charge_calls == []

    async def test_a_chat_that_does_not_exist_is_not_charged(self, service, mock_chats_db, charge_calls):
        mock_chats_db.get_chat.return_value = None

        with pytest.raises(InvalidChatError):
            await service.send_message(uuid4(), user_id=TEST_USER_ID, message="why?")

        assert charge_calls == []

    async def test_an_exceeded_messages_limit_is_not_charged(self, service, mock_chats_db, charge_calls):
        mock_chats_db.get_chat.return_value = _chat_with_ai_messages(MESSAGES_LIMIT)

        with pytest.raises(ChatHistoryLimitError):
            await service.send_message(uuid4(), user_id=TEST_USER_ID, message="why?")

        assert charge_calls == []

    async def test_the_admitted_path_is_charged_exactly_once(self, service, charge_calls):
        """The positive control: without it the four zeros above could be a stand-in that never fires."""
        service.llm_service.ainvoke.return_value = LLM_ANSWER

        await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert charge_calls == [TEST_USER_ID]

    async def test_the_admitted_follow_up_is_charged_exactly_once(self, service, mock_chats_db, charge_calls):
        mock_chats_db.get_chat.return_value = _chat_with_ai_messages(1)
        service.llm_service.ainvoke.return_value = LLM_ANSWER

        await service.send_message(uuid4(), user_id=TEST_USER_ID, message="why?")

        assert charge_calls == [TEST_USER_ID]


class TestAnExhaustedAllowanceAnswers429AndNeverReachesTheProvider:
    """T-37.4-14 and T-37.4-16, asserted directly rather than inferred from the deleted wrapper."""

    async def test_the_quota_error_surfaces_unchanged(self, monkeypatch, mock_chats_db):
        rejection = QuotaExceededError("The allowance for the current period is used up")
        _raising_charge(monkeypatch, rejection)
        service = _service(mock_chats_db)

        with pytest.raises(QuotaExceededError) as caught:
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert caught.value is rejection
        assert (caught.value.status, caught.value.code) == (429, "quota_exceeded")

    async def test_the_429_never_degrades_into_a_503(self, monkeypatch, mock_chats_db):
        """Structural: the charge is raised inside admission and outside `ainvoke`'s classifier."""
        _raising_charge(monkeypatch, QuotaExceededError("used up"))
        service = _service(mock_chats_db)

        with pytest.raises(QuotaExceededError) as caught:
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert not isinstance(caught.value, (ServiceUnavailable, TransientLLMError, PermanentLLMError))
        # Unwrapped, so it carries no provider error underneath it either.
        assert caught.value.__cause__ is None

    async def test_the_llm_service_records_zero_calls(self, monkeypatch, mock_chats_db):
        _raising_charge(monkeypatch, QuotaExceededError("used up"))
        llm = RecordingLLM()
        service = _service(mock_chats_db, llm=llm)

        with pytest.raises(QuotaExceededError):
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert llm.calls == 0

    async def test_the_circuit_breaker_records_no_failure(self, monkeypatch, mock_chats_db):
        """One exhausted allowance must not count towards opening the breaker for every other caller."""
        _raising_charge(monkeypatch, QuotaExceededError("used up"))
        llm = RecordingLLM()
        service = _service(mock_chats_db, llm=llm)

        with pytest.raises(QuotaExceededError):
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert llm.breaker_failures == 0
        assert llm.policy._circuit_breaker._opened_at is None

    async def test_the_follow_up_route_refuses_the_same_way(self, monkeypatch, mock_chats_db):
        rejection = QuotaExceededError("used up")
        _raising_charge(monkeypatch, rejection)
        mock_chats_db.get_chat.return_value = _chat_with_ai_messages(1)
        llm = RecordingLLM()
        service = _service(mock_chats_db, llm=llm)

        with pytest.raises(QuotaExceededError) as caught:
            await service.send_message(uuid4(), user_id=TEST_USER_ID, message="why?")

        assert caught.value is rejection
        assert llm.calls == 0


class TestNoSessionIsHeldAcrossTheProviderCall:
    """T-37.4-15 and SHARED-INVARIANTS.md § Locks and transactions: the charge's session closes first."""

    async def test_the_charges_session_is_closed_before_the_provider_is_entered(self, mock_chats_db):
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        llm = RecordingLLM(events)
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        # The real `QuotaService.charge` runs here: opened, committed and closed, all before the provider.
        assert events == ["session_opened", "session_committed", "session_closed", "provider_called"]

    async def test_the_charge_really_spent_a_unit_in_that_session(self, mock_chats_db):
        """Otherwise the ordering above could be satisfied by a session that resolved nothing."""
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        service = _service(mock_chats_db, llm=RecordingLLM(events),
                           session_factory=_recording_factory(events, grant, usage))

        before = datetime.now(UTC)
        await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert usage.monthly_used == 1
        assert before <= usage.updated_at <= datetime.now(UTC)

    async def test_a_refused_charge_rolls_its_session_back_and_closes_it(self, mock_chats_db):
        """The failing path closes too: an exhausted row must not leak an open transaction into the request."""
        events: list[str] = []
        grant, usage = _effective_grant_rows(monthly_used=ALLOWANCE)
        llm = RecordingLLM(events)
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        with pytest.raises(QuotaExceededError):
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert events == ["session_opened", "session_rolled_back", "session_closed"]
        assert llm.calls == 0
        assert usage.monthly_used == ALLOWANCE


class TestTheChatServiceHoldsNoClockReading:
    """A datetime held here would be a request-scoped instant the charge no longer takes."""

    def test_no_attribute_of_the_service_is_a_datetime(self, mock_chats_db):
        assert [value for value in vars(_service(mock_chats_db)).values()
                if isinstance(value, datetime)] == []


class TestNoConnectionIsHeldAcrossTheProviderCall:
    """CR-01: the request session and the charge session must never want a connection at the same instant."""

    async def test_the_request_session_commits_before_the_charge_opens_its_own(self, mock_chats_db):
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        service = _service(mock_chats_db, llm=RecordingLLM(events),
                           session_factory=_recording_factory(events, grant, usage),
                           request_session=_RecordingRequestSession(events))

        await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert events == ["request_committed", "session_opened", "session_committed",
                          "session_closed", "provider_called", "request_committed"]

    async def test_the_follow_up_commits_its_request_session_the_same_way(self, mock_chats_db):
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        mock_chats_db.get_chat.return_value = _chat_with_ai_messages(1)
        service = _service(mock_chats_db, llm=RecordingLLM(events),
                           session_factory=_recording_factory(events, grant, usage),
                           request_session=_RecordingRequestSession(events))

        await service.send_message(uuid4(), user_id=TEST_USER_ID, message="why?")

        assert events == ["request_committed", "session_opened", "session_committed",
                          "session_closed", "provider_called", "request_committed"]

    async def test_a_service_rejection_commits_nothing(self, mock_chats_db):
        """The commit sits after the two limit checks, so a refused request never opens a transaction to end."""
        events: list[str] = []
        mock_chats_db.count_chats.return_value = CHATS_LIMIT
        service = _service(mock_chats_db, llm=RecordingLLM(events),
                           request_session=_RecordingRequestSession(events))

        with pytest.raises(ChatHistoryLimitError):
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert events == []


class TestAdmissionCannotBeBypassed:
    """The token is a required parameter, so reaching the provider without holding admission is not spellable."""

    async def test_invoking_the_policy_without_a_token_raises(self):
        async def operation() -> dict:
            return LLM_ANSWER

        # Erased, because spelled directly this call is a `ty` error -- which is the other half of the guarantee.
        invoke = _erased(ResiliencePolicy(_resilience_config()).ainvoke)

        with pytest.raises(TypeError, match="admitted"):
            await invoke(operation)

    async def test_a_token_the_policy_never_minted_reaches_no_provider(self):
        """WR-01: the parameter alone was a name, not a guarantee -- a caller could build its own
        token, hold no in-flight slot, and never meet the `queue_size` bound at all."""
        policy = ResiliencePolicy(_resilience_config())
        free_slots = policy._gate._slots.qsize()
        calls = 0

        async def operation() -> dict:
            nonlocal calls
            calls += 1
            return LLM_ANSWER

        with pytest.raises(RuntimeError, match="did not mint"):
            await policy.ainvoke(operation, Admitted(object()))

        assert calls == 0
        assert policy._gate._slots.qsize() == free_slots

    async def test_admission_mints_the_only_token_the_gate_accounts_for(self):
        """A minted token means a slot was actually taken, which is what a bypass would skip."""
        policy = ResiliencePolicy(_resilience_config())
        free_slots = policy._gate._slots.qsize()

        async with policy.admission() as admitted:
            assert isinstance(admitted, Admitted)
            assert policy._gate._slots.qsize() == free_slots - 1

        assert policy._gate._slots.qsize() == free_slots


class TestAdmissionHoldsNoProviderPermit:
    """D-15: admission takes the in-flight slot alone, so the charge's round trip occupies no permit."""

    async def test_entering_admission_leaves_the_semaphore_untouched(self):
        policy = ResiliencePolicy(_resilience_config())
        permits = policy._gate._semaphore._value

        async with policy.admission():
            # The breaker check and the slot are instantaneous; the permit is `ainvoke`'s to take.
            assert policy._gate._semaphore._value == permits

    async def test_a_charge_commits_while_every_permit_is_taken(self, mock_chats_db):
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        llm = RecordingLLM(events)
        semaphore = _take_every_permit(llm.policy)
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        request = asyncio.create_task(
            service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en"))
        await _settle()

        # Charged, committed and closed with no permit available: a slow database occupies none.
        assert events == ["session_opened", "session_committed", "session_closed"]
        assert llm.calls == 0

        semaphore.release()
        await request

        assert llm.calls == 1
        assert usage.monthly_used == 1


class TestARetriedRequestIsChargedExactlyOnce:
    """The charge sits outside the retry loop, so tenacity's three attempts cannot become three credits."""

    async def test_two_transient_failures_then_success_spends_one_unit(self, mock_chats_db):
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        llm = RecordingLLM(events, transient_failures=2)
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        # Three provider attempts against one credit: a charge inside the retried body would read three.
        assert llm.calls == 3
        assert usage.monthly_used == 1
        assert events.count("session_committed") == 1


class TestNoRequestThatNeverReachedTheProviderIsBilled:
    """D-07: both admission rejections answer 503 and cost nothing, because the charge sits inside admission."""

    async def test_a_full_queue_answers_503_and_spends_nothing(self, mock_chats_db):
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        llm = RecordingLLM(events)
        _drain_the_gate(llm.policy)
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        with pytest.raises(QueueFullError) as caught:
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert (caught.value.status, caught.value.code) == (503, "service_unavailable")
        # No session was ever opened, so the refusal happened before the charge rather than after it.
        assert events == []
        assert usage.monthly_used == 0
        assert llm.calls == 0

    async def test_an_open_circuit_answers_503_and_spends_nothing(self, mock_chats_db):
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        llm = RecordingLLM(events)
        llm.policy._circuit_breaker._opened_at = time.monotonic()
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        with pytest.raises(CircuitOpenError) as caught:
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        assert (caught.value.status, caught.value.code) == (503, "service_unavailable")
        assert events == []
        assert usage.monthly_used == 0
        assert llm.calls == 0

    async def test_a_breaker_opening_while_a_charged_request_waits_still_reaches_the_provider(
            self, mock_chats_db):
        """CR-01: the charge commits on admission's verdict, and the wait for a provider permit is
        unbounded, so a second verdict taken after it must not refuse a request that has already
        spent a credit and called nothing -- the one case D-14 and D-15 opened between them."""
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        llm = RecordingLLM(events)
        semaphore = _take_every_permit(llm.policy)
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        request = asyncio.create_task(
            service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en"))
        await _settle()

        assert (usage.monthly_used, llm.calls) == (1, 0)
        llm.policy._circuit_breaker._opened_at = time.monotonic()

        semaphore.release()
        await request

        assert llm.calls == 1
        assert usage.monthly_used == 1

    async def test_the_charge_is_not_refunded_when_the_provider_call_fails(self, mock_chats_db):
        """`services/quota.py`'s docstring states it: the charge commits in its own session and nothing reverses it."""
        events: list[str] = []
        grant, usage = _effective_grant_rows()
        llm = RecordingLLM(events, transient_failures=99)
        service = _service(mock_chats_db, llm=llm,
                           session_factory=_recording_factory(events, grant, usage))

        with pytest.raises(TransientLLMError):
            await service.create_chat(phrase=PHRASE, user_id=TEST_USER_ID, lang="en")

        # The provider was reached and failed, which is the case that is deliberately still charged.
        assert llm.calls == 3
        assert "session_rolled_back" not in events
        assert usage.monthly_used == 1
