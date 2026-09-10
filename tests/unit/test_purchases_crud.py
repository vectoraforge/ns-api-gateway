"""The two `core.store_purchase_tokens` reads: the per-store token read, complete or raising
with no token in its message, and the attribution read, keyed on the store and the token."""
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
    """The two shapes these reads ask for: the token read's `(provider, identity_value)` rows, and
    the one owner the attribution read takes off its single column."""

    def __init__(self, rows, owner=None):
        self._rows = list(rows)
        self._owner = owner

    def all(self):
        return list(self._rows)

    def first(self):
        return self._owner


class _StubSession:
    """Stands in for the request session, keeping every statement it was asked to run."""

    def __init__(self, tokens, owner=None):
        self._tokens = dict(tokens)
        self._owner = owner
        self.statements = []

    @property
    def executed(self) -> int:
        return len(self.statements)

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._tokens.items(), self._owner)


def _compiled(statement) -> str:
    """The statement as PostgreSQL would receive it -- the dialect that actually runs it."""
    return str(statement.compile(dialect=postgresql.dialect()))


def _bound(statement) -> list:
    """The values the statement carries, which the compiled text renders only as placeholders."""
    return list(statement.compile(dialect=postgresql.dialect()).params.values())


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


class TestTheReadIsScopedToOneOwner:
    """WR-84: the token column is the secret this read returns, so an unscoped predicate hands every
    account's Apple and Play tokens to whichever caller asked. SHARED-INVARIANTS:5 is the whole rule."""

    async def test_the_statement_carries_an_owner_predicate(self):
        _, session = await _read(SEEDED)

        assert "core.store_purchase_tokens.user_id = " in _compiled(session.statements[0])

    async def test_the_owner_it_is_keyed_on_is_the_caller_the_handler_named(self):
        """The predicate is not enough on its own: the compiled text renders its value as a placeholder."""
        _, session = await _read(SEEDED)

        assert _bound(session.statements[0]) == [USER_ID]


async def _resolved(provider, identity_value):
    """The attribution read's answer, and the session that carries the statement it issued."""
    session = _StubSession(SEEDED, owner=USER_ID)
    return await PurchasesDB(session).resolve_user(provider, identity_value), session


class TestTheAttributionReadIsKeyedOnTheStoreAndTheToken:
    """`08-webhook-app-store.md`:37 keys attribution on the store provider and the lifetime token,
    with no identity-kind dimension, so one store's token never resolves the other store's binding."""

    async def test_the_statement_carries_both_halves_of_the_key(self):
        """The predicates are not enough on their own: the compiled text renders both as placeholders."""
        _, session = await _resolved(PurchaseProvider.apple, APPLE_TOKEN)

        assert _bound(session.statements[0]) == [PurchaseProvider.apple, APPLE_TOKEN]

    async def test_the_bound_owner_is_the_answer(self):
        owner, _ = await _resolved(PurchaseProvider.apple, APPLE_TOKEN)

        assert owner == USER_ID

    async def test_the_read_takes_one_unlocked_statement(self):
        """A lock here would serialise every ingestion behind the grant locks it is read before."""
        _, session = await _resolved(PurchaseProvider.google_play, GOOGLE_TOKEN)

        assert session.executed == 1
        assert LOCK_CLAUSE not in _compiled(session.statements[0])
