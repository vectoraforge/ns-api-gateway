"""The message read's ordering, as the statement PostgreSQL receives rather than as prose."""
from uuid import uuid7

import pytest
from sqlalchemy.dialects import postgresql

from nativespeaker.api.crud.chats import ChatsDB
from nativespeaker.api.routers.chats import router

CHAT_ID = uuid7()
USER_ID = uuid7()

# The route's own promise, which the ORDER BY below is the implementation of.
DOCUMENTED_CONTRACT = "ordered chronologically"


class _StubResult:

    def all(self):
        return []


class _StubSession:
    """Stands in for the request session, keeping every statement it was asked to run."""

    def __init__(self):
        self.statements = []

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult()


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def _description() -> str:
    for route in router.routes:
        if route.path == "/chats/{chat_id}" and "GET" in route.methods:
            return route.description
    raise AssertionError("the message route is not registered at all")


class TestTheMessageReadIsChronological:

    @pytest.mark.asyncio
    async def test_the_statement_orders_by_ascending_id(self):
        """uuid7 makes ascending id chronological, so this is the whole ordering guarantee."""
        session = _StubSession()

        await ChatsDB(session).get_messages(chat_id=CHAT_ID, user_id=USER_ID)

        assert "ORDER BY core.messages.id ASC" in _sql(session.statements[0])

    @pytest.mark.asyncio
    async def test_the_statement_does_not_order_descending(self):
        """The control: the defect this replaces rendered the conversation backwards."""
        session = _StubSession()

        await ChatsDB(session).get_messages(chat_id=CHAT_ID, user_id=USER_ID)

        assert "DESC" not in _sql(session.statements[0])

    def test_the_route_still_documents_the_order_the_statement_takes(self):
        """Both halves in one case: a change to either side alone fails here."""
        assert DOCUMENTED_CONTRACT in _description()
