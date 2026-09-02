"""The per-store token read: complete or raising, one statement, no lock, and no token in the message."""
from uuid import uuid7

import pytest
from sqlalchemy.dialects import postgresql

from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.errors import MissingPurchaseTokenError
from nativespeaker.api.tables.purchases import PurchaseProvider

USER_ID = uuid7()
APPLE_TOKEN = "apple-token-under-test"
GOOGLE_TOKEN = "google-play-token-under-test"

# The whole difference between the locking and the non-locking read, as PostgreSQL receives it.
LOCK_CLAUSE = " FOR UPDATE"

# Derived from the enum, never hand-listed: the completeness rule is written against exactly this set.
EVERY_STORE = set(PurchaseProvider)
SEEDED = {PurchaseProvider.apple: APPLE_TOKEN, PurchaseProvider.google_play: GOOGLE_TOKEN}


class _StubResult:
    """The rows a two-column select returns: `(provider, identity_value)` tuples, not model instances."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _StubSession:
    """Stands in for the request session, keeping every statement it was asked to run."""

    def __init__(self, tokens):
        self._tokens = dict(tokens)
        self.statements = []

    @property
    def executed(self) -> int:
        return len(self.statements)

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._tokens.items())


def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))


async def _read(tokens):
    """The admitting half: the mapping the read returns, and the session it used."""
    session = _StubSession(tokens)
    return await PurchasesDB(session).read_tokens(USER_ID), session


async def _refused(tokens):
    """The refusing half: the read raises, and the raised instance is what the cases read."""
    session = _StubSession(tokens)
    with pytest.raises(MissingPurchaseTokenError) as caught:
        await PurchasesDB(session).read_tokens(USER_ID)
    return caught.value, session


class TestACompleteAccountReadsBackItsTokens:
    """Every store represented is the only shape this read returns; there is no partial answer."""

    async def test_the_mapping_carries_one_entry_per_store(self):
        tokens, _ = await _read(SEEDED)

        assert set(tokens) == EVERY_STORE

    async def test_each_entry_carries_the_stored_token(self):
        tokens, _ = await _read(SEEDED)

        assert tokens == SEEDED


# Every incomplete seed: no row at all, and each single store, which an emptiness check would pass.
_INCOMPLETE_SEEDS = [
    pytest.param({}, [PurchaseProvider.apple, PurchaseProvider.google_play], id="no-store-row"),
    pytest.param({PurchaseProvider.apple: APPLE_TOKEN}, [PurchaseProvider.google_play], id="apple-only"),
    pytest.param({PurchaseProvider.google_play: GOOGLE_TOKEN}, [PurchaseProvider.apple], id="google-play-only"),
]


class TestAnIncompleteAccountIsRefused:
    """Completeness against the enum and never emptiness: one row present is as broken as no row."""

    @pytest.mark.parametrize(("seeded", "missing"), _INCOMPLETE_SEEDS)
    async def test_an_unrepresented_store_raises(self, seeded, missing):
        error, _ = await _refused(seeded)

        assert list(error.missing) == sorted(missing)

    @pytest.mark.parametrize(("seeded", "missing"), _INCOMPLETE_SEEDS)
    async def test_the_message_names_the_user_and_every_missing_store(self, seeded, missing):
        error, _ = await _refused(seeded)

        assert str(USER_ID) in str(error)
        assert all(store.value in str(error) for store in missing)

    @pytest.mark.parametrize(("seeded", "missing"), _INCOMPLETE_SEEDS)
    async def test_no_token_value_reaches_the_message(self, seeded, missing):
        """The token column is the secret, so it may never reach a message, a traceback or a log field."""
        error, _ = await _refused(seeded)

        assert APPLE_TOKEN not in str(error)
        assert GOOGLE_TOKEN not in str(error)


class TestTheReadTakesOneUnlockedStatement:
    """A read that locked or queried twice would serialise a profile call behind the writing paths."""

    async def test_exactly_one_statement_is_issued(self):
        _, session = await _read(SEEDED)

        assert session.executed == 1

    async def test_the_statement_reads_the_token_table(self):
        """The positive half: without it the two cases below could pass on an empty compiled string."""
        _, session = await _read(SEEDED)

        assert "core.store_purchase_tokens" in _compiled(session.statements[0])

    async def test_the_statement_takes_no_lock(self):
        _, session = await _read(SEEDED)

        assert LOCK_CLAUSE not in _compiled(session.statements[0])

    async def test_no_statement_reads_the_users_table(self):
        _, session = await _read(SEEDED)

        assert all("core.users" not in _compiled(statement) for statement in session.statements)
