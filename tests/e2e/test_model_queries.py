"""D-14's real claim: the model layer *queries* the applied v2.0 schema, not merely imports.

`import nativespeaker.api.app.main` succeeded and the lifespan ran throughout Phase 35 while
`select(User)` still raised `UndefinedColumnError: column users.jwt_sub does not exist`. SQLModel
classes import fine when their columns are gone -- the failure appears only when a query runs,
which is precisely the gap D-15 draws its line through. Every assertion in this module therefore
issues a real statement against the real database.

Reads and writes go through the `_db_transaction` fixture's swapped `test_factory`, never a fresh
engine: the whole e2e strategy rests on that factory's `join_transaction_mode="create_savepoint"`,
and a second engine would both miss the savepoint and leave rows behind.
"""
from uuid import uuid7

import pytest
from sqlalchemy import select as sa_select
from sqlmodel import SQLModel, select

from nativespeaker.api.models import (
    Chat,
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    Message,
    User,
)

from .conftest import create_chat

pytestmark = pytest.mark.e2e

# Rolled back with its transaction; the second case asserts exactly that.
LEAKED_USER_ID = uuid7()

# Every table the ORM maps, so a model that drifts from the schema is caught whichever model it is.
MAPPED_TABLES = sorted(SQLModel.metadata.tables)


@pytest.mark.asyncio(loop_scope="module")
class TestModelsMatchTheAppliedSchema:
    """Each case here failed before this plan, with the error named in its docstring."""

    async def test_select_user_executes(self, _db_transaction):
        """`UndefinedColumnError: column users.jwt_sub does not exist` before the repair."""
        async with _db_transaction() as session:
            result = await session.exec(select(User))
            assert result.all() is not None

    async def test_select_external_identity_executes(self, _db_transaction):
        async with _db_transaction() as session:
            result = await session.exec(select(ExternalIdentity))
            assert result.all() is not None

    @pytest.mark.parametrize("table_name", MAPPED_TABLES)
    async def test_every_mapped_table_selects_all_of_its_columns(self, _db_transaction, table_name):
        """The generalised form, and the one that catches the next drift rather than this one.

        `SELECT <every declared column> FROM <table>` fails with `UndefinedColumnError` for a
        column the database does not have and `UndefinedTableError` for a table it does not have.
        A surviving `UsageMonthly` mapping `core.usage_monthly` -- a relation the v2.0 migration
        dropped -- is caught here as the latter.
        """
        table = SQLModel.metadata.tables[table_name]
        async with _db_transaction() as session:
            await session.exec(sa_select(table).limit(1))  # ty: ignore[invalid-argument-type]


@pytest.mark.asyncio(loop_scope="module")
class TestRowsRoundTrip:
    """Writing is the other half: a shape that reads can still be rejected on insert."""

    async def test_user_and_identity_round_trip(self, _db_transaction):
        """A NULL email survives the round trip, and an anonymous identity satisfies the CHECK.

        `email` nullability cannot be proven in a unit test: SQLModel skips pydantic validation on
        `table=True` classes, so `User(email=None)` constructs whatever the annotation says. Only
        the database's own NOT NULL -- or its absence -- settles it.

        `provider='anonymous'` with `provider_uid=None` is the left arm of the table's
        provider/provider_uid agreement CHECK. Ruling 9.2 forbids inventing a sentinel
        `provider_uid` for an anonymous row, so this is the only shape an anonymous seed can take.
        """
        async with _db_transaction() as session:
            session.add(User(id=LEAKED_USER_ID, email=None, display_name="round trip"))
            await session.flush()
            session.add(ExternalIdentity(user_id=LEAKED_USER_ID,
                                         issuer="https://securetoken.google.com/test-project",
                                         subject=f"subject-{LEAKED_USER_ID}",
                                         provider=IdentityProvider.anonymous,
                                         provider_uid=None))
            await session.commit()

        async with _db_transaction() as session:
            user = (await session.exec(select(User).where(User.id == LEAKED_USER_ID))).one()
            assert user.email is None
            assert user.display_name == "round trip"
            assert user.active is True
            assert user.registered_at is None
            assert user.created_at is not None and user.updated_at is not None

            identity = (await session.exec(
                select(ExternalIdentity).where(ExternalIdentity.user_id == LEAKED_USER_ID))).one()
            assert identity.provider is IdentityProvider.anonymous
            assert identity.provider_uid is None
            assert identity.identity_state is IdentityState.active

    async def test_the_previous_rows_were_rolled_back(self, _db_transaction):
        """Runs after the case above, on a fresh transaction over a fresh connection.

        This is the isolation guarantee itself: without it every case above would be seeding the
        developer's database. Ordering is source order, which pytest preserves.
        """
        async with _db_transaction() as session:
            assert (await session.exec(
                select(User).where(User.id == LEAKED_USER_ID))).first() is None
            assert (await session.exec(
                select(ExternalIdentity).where(
                    ExternalIdentity.user_id == LEAKED_USER_ID))).first() is None


@pytest.mark.asyncio(loop_scope="module")
class TestCreateChatSeedsAgainstV2:
    """`create_chat` is the seeding helper the cases plan 11 restores all go through."""

    async def test_seeds_a_user_an_identity_and_a_chat(self, _db_transaction):
        issuer = "https://securetoken.google.com/test-project"
        subject = f"seeded-{uuid7()}"

        chat_id = await create_chat(_db_transaction, issuer, subject)

        async with _db_transaction() as session:
            identity = (await session.exec(
                select(ExternalIdentity).where(ExternalIdentity.issuer == issuer,
                                               ExternalIdentity.subject == subject))).one()
            user = (await session.exec(
                select(User).where(User.id == identity.user_id))).one()
            assert user.id == identity.user_id

            chat = (await session.exec(select(Chat).where(Chat.id == chat_id))).one()
            assert chat.user_id == user.id
            messages = (await session.exec(
                select(Message).where(Message.chat_id == chat_id))).all()
            assert len(messages) == 2

    async def test_reuses_the_identity_for_a_repeated_pair(self, _db_transaction):
        """A second chat for the same (issuer, subject) must not violate UNIQUE (issuer, subject)."""
        issuer = "https://securetoken.google.com/test-project"
        subject = f"repeated-{uuid7()}"

        first = await create_chat(_db_transaction, issuer, subject)
        second = await create_chat(_db_transaction, issuer, subject)
        assert first != second

        async with _db_transaction() as session:
            identities = (await session.exec(
                select(ExternalIdentity).where(ExternalIdentity.issuer == issuer,
                                               ExternalIdentity.subject == subject))).all()
            assert len(identities) == 1
