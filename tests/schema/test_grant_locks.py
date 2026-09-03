"""The grant-then-usage lock order under real contention, the activation path's tiers, and the free-grant set."""
import asyncio
import contextlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.crud.grants import UNIQUE_VIOLATION, ActivationOutcome, GrantsDB
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.tables.grants import FREE_GRANT_SOURCES, AccessGrant, AccessGrantSource
from schema.helpers import insert_grant, insert_tier, insert_usage, insert_user

pytestmark = pytest.mark.schema

# Mirrors GrantsDB.lock_effective_grants; the ORDER BY is the lock order itself, not presentation.
_LOCK_GRANTS = (
    "SELECT id FROM core.access_grants "
    "WHERE user_id = $1 AND status = 'active' "
    "  AND starts_at <= CURRENT_TIMESTAMP "
    "  AND (ends_at IS NULL OR ends_at > CURRENT_TIMESTAMP) "
    "ORDER BY id ASC "
    "FOR UPDATE"
)

# Mirrors GrantsDB.lock_usage: second in the order, keyed on the whole primary key, and never an INSERT.
_LOCK_USAGE = "SELECT grant_id FROM core.user_monthly_usage WHERE grant_id = $1 FOR UPDATE"

# Longer than PostgreSQL's 1s deadlock_timeout, so a deadlock case fails on a missed detection, not a timeout.
_WAIT = "5s"

# Short on purpose: the blocking cases assert a lock is NOT available, so the timeout is their instrument.
_NO_WAIT = "500ms"


@dataclass(frozen=True)
class _Seeded:
    user_id: uuid.UUID
    tier_id: str
    grant_id: uuid.UUID


@pytest_asyncio.fixture
async def committed_grant(_schema_db_uri):
    """Committed rows, because uncommitted ones are invisible to the second connection and every case would pass."""
    setup = await asyncpg.connect(_schema_db_uri)
    try:
        # No transaction block: asyncpg autocommits each statement, which is the commit these rows need.
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        grant_id = await insert_grant(setup, user_id=user_id, tier_id=tier_id, source="manual")
        await insert_usage(setup, grant_id=grant_id)
    finally:
        await setup.close()

    try:
        yield _Seeded(user_id=user_id, tier_id=tier_id, grant_id=grant_id)
    finally:
        cleanup = await asyncpg.connect(_schema_db_uri)
        try:
            await cleanup.execute("DELETE FROM core.access_grants WHERE user_id = $1", user_id)
            await cleanup.execute("DELETE FROM core.users WHERE id = $1", user_id)
            await cleanup.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)
        finally:
            await cleanup.close()


@pytest_asyncio.fixture
async def contenders(_schema_db_uri):
    """Two live connections, closed in nested finally blocks so a leaked lock cannot block the next case."""
    conn_a = await asyncpg.connect(_schema_db_uri)
    try:
        conn_b = await asyncpg.connect(_schema_db_uri)
        try:
            yield conn_a, conn_b
        finally:
            await conn_b.close()
    finally:
        await conn_a.close()


async def _begin(conn, *, lock_timeout: str):
    """Start a transaction with a bounded lock wait; SET LOCAL lock_timeout is how "not available" is detected."""
    tx = conn.transaction()
    await tx.start()
    await conn.execute(f"SET LOCAL lock_timeout = '{lock_timeout}'")
    return tx


async def _rollback(tx):
    """Roll a transaction back, tolerating one PostgreSQL already aborted (a deadlock victim)."""
    with contextlib.suppress(Exception):
        await tx.rollback()


@pytest.mark.asyncio
class TestTheGrantLockExcludes:
    """The lock is real: while one transaction holds the grant row, no other can take it."""

    async def test_a_second_transaction_cannot_take_the_grant_lock(self, committed_grant,
                                                                   contenders):
        conn_a, conn_b = contenders
        tx_a = await _begin(conn_a, lock_timeout=_WAIT)
        tx_b = await _begin(conn_b, lock_timeout=_NO_WAIT)
        try:
            held = await conn_a.fetch(_LOCK_GRANTS, committed_grant.user_id)
            assert [row["id"] for row in held] == [committed_grant.grant_id], \
                "control: A must actually hold the seeded grant row, or B has nothing to wait for"

            with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
                await conn_b.fetch(_LOCK_GRANTS, committed_grant.user_id)
        finally:
            await _rollback(tx_b)
            await _rollback(tx_a)

    async def test_the_lock_is_released_when_the_first_transaction_ends(self, committed_grant,
                                                                        contenders):
        """A lock that never released would be a hang, not a gate; the short timeout is what asserts that."""
        conn_a, conn_b = contenders
        tx_a = await _begin(conn_a, lock_timeout=_WAIT)
        await conn_a.fetch(_LOCK_GRANTS, committed_grant.user_id)
        await _rollback(tx_a)

        tx_b = await _begin(conn_b, lock_timeout=_NO_WAIT)
        try:
            rows = await conn_b.fetch(_LOCK_GRANTS, committed_grant.user_id)
            assert [row["id"] for row in rows] == [committed_grant.grant_id]
        finally:
            await _rollback(tx_b)


@pytest.mark.asyncio
class TestTheLockOrderIsLoadBearing:
    """Why SHARED-INVARIANTS:33 fixes an order at all, demonstrated from both sides."""

    async def test_the_reverse_order_deadlocks(self, committed_grant, contenders):
        """Grant-then-usage against usage-then-grant: PostgreSQL aborts one, which is what fixes the order."""
        conn_a, conn_b = contenders
        tx_a = await _begin(conn_a, lock_timeout=_WAIT)
        tx_b = await _begin(conn_b, lock_timeout=_WAIT)
        try:
            await conn_a.fetch(_LOCK_GRANTS, committed_grant.user_id)   # fixed order, step 1
            await conn_b.fetch(_LOCK_USAGE, committed_grant.grant_id)   # reverse order, step 1

            outcomes = await asyncio.gather(
                conn_a.fetch(_LOCK_USAGE, committed_grant.grant_id),    # fixed order, step 2
                conn_b.fetch(_LOCK_GRANTS, committed_grant.user_id),    # reverse order, step 2
                return_exceptions=True,
            )

            deadlocked = [outcome for outcome in outcomes
                          if isinstance(outcome, asyncpg.exceptions.DeadlockDetectedError)]
            assert len(deadlocked) == 1, f"expected exactly one deadlock victim, got {outcomes}"
        finally:
            await _rollback(tx_b)
            await _rollback(tx_a)

    async def test_the_fixed_order_does_not_deadlock(self, committed_grant, contenders):
        """The control: both transactions take the fixed order, the second waits, and nothing is aborted."""
        conn_a, conn_b = contenders
        tx_a = await _begin(conn_a, lock_timeout=_WAIT)
        tx_b = await _begin(conn_b, lock_timeout=_WAIT)
        try:
            await conn_a.fetch(_LOCK_GRANTS, committed_grant.user_id)
            await conn_a.fetch(_LOCK_USAGE, committed_grant.grant_id)

            async def b_takes_the_same_order_and_waits():
                await conn_b.fetch(_LOCK_GRANTS, committed_grant.user_id)
                return await conn_b.fetch(_LOCK_USAGE, committed_grant.grant_id)

            async def a_finishes_shortly():
                # Long enough that B is provably blocked before A releases; without it the two could serialise.
                await asyncio.sleep(0.2)
                await tx_a.rollback()

            outcomes = await asyncio.gather(b_takes_the_same_order_and_waits(),
                                            a_finishes_shortly(),
                                            return_exceptions=True)

            assert not [outcome for outcome in outcomes if isinstance(outcome, BaseException)], \
                f"the fixed order must not deadlock or time out, got {outcomes}"
            assert [row["grant_id"] for row in outcomes[0]] == [committed_grant.grant_id]
        finally:
            await _rollback(tx_b)
            await _rollback(tx_a)


# The activation path, and the two claims that keep a future writer inside the fixed order.

_ASYNCPG_PREFIX = "postgres://"
_SQLALCHEMY_PREFIX = "postgresql+asyncpg://"

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# The lifetime index's membership, read from the live catalogue rather than transcribed from the migration.
_LIFETIME_INDEX = "ix_access_grants_one_free_grant_per_user_source"
_INDEX_PREDICATE = (
    "SELECT pg_get_expr(ix.indpred, ix.indrelid) AS predicate "
    "FROM pg_index ix JOIN pg_class i ON i.oid = ix.indexrelid WHERE i.relname = $1"
)

# pg_get_expr renders enum casts relative to search_path, so it is pinned and the expected strings stay literal.
PINNED_SEARCH_PATH = '"$user", public'

_SOURCE_LITERAL = re.compile(r"'([a-z_]+)'::core\.access_grant_source")

# The relation a locking statement takes its rows from; the two tiers are the only two this path may name.
_LOCKED_RELATION = re.compile(r"FROM (core\.[a-z_]+)")


def locking(statements: list[str]) -> list[str]:
    """Only the statements that take a row lock, in the order the writer issued them."""
    return [statement for statement in statements if "FOR UPDATE" in statement]


def relation_of(statement: str) -> str:
    """The core relation a statement reads, which for a locking statement is the tier it takes."""
    found = _LOCKED_RELATION.search(statement)
    return found.group(1) if found else statement


@pytest_asyncio.fixture
async def activation_statements(_schema_db_uri):
    """Every statement GrantsDB.activate_anonymous_device_grant issued, in order, against a real database."""
    subject = f"lock-order-{uuid.uuid4().hex[:10]}"
    issuer = f"ns-lock-order-{uuid.uuid4().hex[:10]}"

    setup = await asyncpg.connect(_schema_db_uri)
    try:
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        # A held `manual` grant with its usage row, so both tiers have a real row to lock and to order.
        grant_id = await insert_grant(setup, user_id=user_id, tier_id=tier_id, source="manual")
        await insert_usage(setup, grant_id=grant_id)
        await setup.execute(
            "INSERT INTO core.external_identities "
            "(id, user_id, issuer, subject, provider, identity_state, created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, 'anonymous', 'active', $5, $5)",
            uuid.uuid4(), user_id, issuer, subject, NOW)
    finally:
        await setup.close()

    engine = create_async_engine(_schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    recorded: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        recorded.append(" ".join(statement.split()))

    # After the seed, never the module's fixed instant: the held grant's starts_at is CURRENT_TIMESTAMP,
    # and an earlier instant makes it ineffective, so the writer would take one tier instead of two.
    evaluated_at = datetime.now(UTC)

    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            identity_row = await IdentitiesDB(session).resolve_existing(issuer=issuer,
                                                                       subject=subject)
            # Everything above is setup; only what the writer itself issues is the subject of this fixture.
            recorded.clear()
            outcome = await GrantsDB(session).activate_anonymous_device_grant(
                user_id=user_id, identity_row=identity_row,
                tier_id=tier_id, evaluated_at=evaluated_at)
            await session.rollback()
        yield {"statements": list(recorded), "outcome": outcome}
    finally:
        await engine.dispose()
        cleanup = await asyncpg.connect(_schema_db_uri)
        try:
            await cleanup.execute("DELETE FROM core.user_monthly_usage WHERE grant_id = $1", grant_id)
            await cleanup.execute("DELETE FROM core.access_grants WHERE user_id = $1", user_id)
            await cleanup.execute("DELETE FROM core.external_identities WHERE issuer = $1", issuer)
            await cleanup.execute("DELETE FROM core.users WHERE id = $1", user_id)
            await cleanup.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)
        finally:
            await cleanup.close()


@pytest.mark.asyncio
class TestTheActivationAddsNoThirdLockTier:
    """ANONGRANT-02. An identity or user row may never be locked ahead of the grant rows: SHARED-INVARIANTS:33.
    The brief this phase implements says the opposite, and the invariants win by precedence (D-13)."""

    async def test_the_writer_locks_the_grant_rows_then_their_usage_rows(self, activation_statements):
        """The ORDER BY is the lock order itself, not presentation, so it is asserted with the tier."""
        taken = locking(activation_statements["statements"])
        assert [relation_of(statement) for statement in taken] == ["core.access_grants",
                                                                   "core.user_monthly_usage"]
        assert "ORDER BY core.access_grants.id ASC" in taken[0]

    async def test_exactly_two_distinct_lock_tiers_are_taken_on_the_claim_path(self,
                                                                               activation_statements):
        """Two, and never a third: a writer that locks the identity or user row first fails here, not in production."""
        taken = [relation_of(statement) for statement in locking(activation_statements["statements"])]
        assert len(set(taken)) == 2
        assert "core.external_identities" not in taken
        assert "core.users" not in taken

    async def test_the_identity_row_is_revalidated_by_a_plain_re_read(self, activation_statements):
        """The control: the writer issues more statements than it locks, so the count above is not vacuously small."""
        statements = activation_statements["statements"]
        re_reads = [statement for statement in statements
                    if "core.external_identities" in statement and "FOR UPDATE" not in statement]
        assert len(re_reads) == 1, f"expected one plain identity re-read, got {statements}"
        assert activation_statements["outcome"] is ActivationOutcome.refused
        # The control that matters: `False` must come from the held-grant check, not from a rejected insert,
        # or the two tiers above would be one lock and one write and the count would read as two by accident.
        assert not [statement for statement in statements if statement.startswith("INSERT")], \
            f"the writer must stop at the held grant and write nothing, got {statements}"


# The registered writer, whose two destinations are captured on the same terms as the anonymous one above.


def writes(statements: list[str]) -> list[str]:
    """Only the statements that change a row, which is the control on every lock-tier count below."""
    return [statement for statement in statements if statement.startswith(("INSERT", "UPDATE"))]


def first_index(statements: list[str], prefix: str) -> int:
    """Where `prefix` first appears among the recorded statements, or -1 if it never does."""
    for position, statement in enumerate(statements):
        if statement.startswith(prefix):
            return position
    return -1


def assert_one_plain_identity_re_read(captured: dict) -> None:
    """One non-locking re-read of the identity row, on an arm that provably wrote something."""
    statements = captured["statements"]
    # A SELECT, because the writer also marks the identity row and that UPDATE names the same relation.
    re_reads = [statement for statement in statements
                if statement.startswith("SELECT") and "core.external_identities" in statement
                and "FOR UPDATE" not in statement]
    assert len(re_reads) == 1, f"expected one plain identity re-read, got {statements}"
    assert captured["outcome"] is ActivationOutcome.activated
    assert writes(statements), f"the writer must have written on this arm, got {statements}"


@contextlib.asynccontextmanager
async def _registered_writer_run(schema_db_uri: str, *, holding_anonymous_grant: bool):
    """Drive GrantsDB.activate_registered_account_grant once, recording every statement it issues."""
    subject = f"registered-lock-{uuid.uuid4().hex[:10]}"
    issuer = f"ns-registered-{uuid.uuid4().hex[:10]}"

    setup = await asyncpg.connect(schema_db_uri)
    try:
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        # A `google` row must carry a non-empty provider_uid, which is the table's CHECK for this arm.
        await setup.execute(
            "INSERT INTO core.external_identities "
            "(id, user_id, issuer, subject, provider, provider_uid, identity_state, created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, 'google', $5, 'active', $6, $6)",
            uuid.uuid4(), user_id, issuer, subject, f"google-uid-{subject}", NOW)
        if holding_anonymous_grant:
            grant_id = await insert_grant(setup, user_id=user_id, tier_id=tier_id,
                                          source="anonymous_device_grant")
            await insert_usage(setup, grant_id=grant_id)
            # Strictly earlier than the writer's instant: the table's `ends_at > starts_at` CHECK is strict,
            # and a same-instant expiry would roll the conversion back and read as a race loss.
            await setup.execute("UPDATE core.access_grants SET starts_at = $2 WHERE id = $1",
                                grant_id, datetime.now(UTC) - timedelta(hours=1))
    finally:
        await setup.close()

    engine = create_async_engine(schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    recorded: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        recorded.append(" ".join(statement.split()))

    evaluated_at = datetime.now(UTC)
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            identity_row = await IdentitiesDB(session).resolve_existing(issuer=issuer,
                                                                       subject=subject)
            # Everything above is setup; only what the writer itself issues is the subject of this fixture.
            recorded.clear()
            outcome = await GrantsDB(session).activate_registered_account_grant(
                user_id=user_id, identity_row=identity_row,
                tier_id=tier_id, evaluated_at=evaluated_at)
            await session.rollback()
        yield {"statements": list(recorded), "outcome": outcome}
    finally:
        await engine.dispose()
        cleanup = await asyncpg.connect(schema_db_uri)
        try:
            await cleanup.execute("DELETE FROM core.user_monthly_usage WHERE grant_id IN "
                                  "(SELECT id FROM core.access_grants WHERE user_id = $1)", user_id)
            await cleanup.execute("DELETE FROM core.access_grants WHERE user_id = $1", user_id)
            await cleanup.execute("DELETE FROM core.external_identities WHERE issuer = $1", issuer)
            await cleanup.execute("DELETE FROM core.users WHERE id = $1", user_id)
            await cleanup.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)
        finally:
            await cleanup.close()


@pytest_asyncio.fixture
async def conversion_statements(_schema_db_uri):
    """The registered writer driven on a caller holding one active anonymous device grant."""
    async with _registered_writer_run(_schema_db_uri, holding_anonymous_grant=True) as run:
        yield run


@pytest_asyncio.fixture
async def new_grant_statements(_schema_db_uri):
    """The registered writer driven on a clean account, which has no grant row to lock."""
    async with _registered_writer_run(_schema_db_uri, holding_anonymous_grant=False) as run:
        yield run


@pytest.mark.asyncio
class TestTheRegisteredWriterAddsNoThirdLockTier:
    """REGGRANT-02. The conversion runs under the same fixed order the anonymous claim does:
    SHARED-INVARIANTS:33, proven from the statements the writer emits rather than from its Python."""

    async def test_the_conversion_locks_the_grant_rows_then_their_usage_rows(self,
                                                                             conversion_statements):
        """The ORDER BY is the lock order itself, not presentation, so it is asserted with the tier."""
        taken = locking(conversion_statements["statements"])
        # Two grant-tier reads, the status-only one first: it contains the effective one, so one order holds.
        assert [relation_of(statement) for statement in taken] == ["core.access_grants",
                                                                   "core.access_grants",
                                                                   "core.user_monthly_usage"]
        assert "ORDER BY core.access_grants.id ASC" in taken[0]

    async def test_exactly_two_distinct_lock_tiers_are_taken_on_the_conversion(self,
                                                                               conversion_statements):
        """Two, and never a third: a writer that locks the identity or user row fails here, not in production."""
        taken = [relation_of(statement) for statement in locking(conversion_statements["statements"])]
        assert len(set(taken)) == 2
        assert "core.external_identities" not in taken
        assert "core.users" not in taken

    async def test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row(
            self, new_grant_statements):
        """A clean account has nothing in either tier, so `FOR UPDATE` locks nothing and the indexes arbitrate."""
        taken = [relation_of(statement) for statement in locking(new_grant_statements["statements"])]
        assert taken == ["core.access_grants", "core.access_grants"]
        assert "core.external_identities" not in taken
        assert "core.users" not in taken

    async def test_the_conversion_revalidates_the_identity_row_by_a_plain_re_read(
            self, conversion_statements):
        """The control: the writer wrote on this arm, so the tier count above is not vacuously small."""
        assert_one_plain_identity_re_read(conversion_statements)

    async def test_the_new_grant_revalidates_the_identity_row_by_a_plain_re_read(
            self, new_grant_statements):
        """The same control on the arm that locks one tier: a writer issuing nothing cannot satisfy it."""
        assert_one_plain_identity_re_read(new_grant_statements)


@pytest.mark.asyncio
class TestTheConversionExpiresBeforeItInserts:
    """REGGRANT-02. `ix_access_grants_one_active_per_user` is non-deferrable and per-statement, so the
    order the ORM emits -- not the order of the Python statements -- is what decides the conversion."""

    async def test_the_update_of_the_anonymous_row_precedes_the_insert_of_the_registered_one(
            self, conversion_statements):
        """If this inverts, the index refuses the insert, the writer returns false, and every conversion
        answers a stale 200 as though it had lost a race it never ran."""
        statements = conversion_statements["statements"]
        expiry = first_index(statements, "UPDATE core.access_grants")
        insert = first_index(statements, "INSERT INTO core.access_grants")
        assert expiry >= 0, f"no expiry statement was emitted at all, got {statements}"
        assert insert >= 0, f"no grant insert was emitted at all, got {statements}"
        assert expiry < insert, f"the insert was emitted first, got {statements}"

    async def test_the_usage_row_is_inserted_after_the_grant_it_belongs_to(self,
                                                                           conversion_statements):
        """The control on the case above: the recorded order is a real sequence, not one repeated prefix."""
        statements = conversion_statements["statements"]
        assert first_index(statements, "INSERT INTO core.access_grants") < \
            first_index(statements, "INSERT INTO core.user_monthly_usage")


# The registered writer's three outcomes, measured from the writer itself and not from the route.


@dataclass(frozen=True)
class _Row:
    """One grant to seed: its source, its status, and where its term sits around the writer's instant."""
    source: str
    status: str = "active"
    starts_before: timedelta = timedelta(hours=1)
    ends_before: timedelta | None = None


@dataclass(frozen=True)
class _Account:
    """A seeded google account, an open session, and the instant the writer is driven at."""
    session: SQLModelAsyncSession
    user_id: uuid.UUID
    identity_row: object
    tier_id: str
    evaluated_at: datetime

    async def activate(self):
        return await GrantsDB(self.session).activate_registered_account_grant(
            user_id=self.user_id, identity_row=self.identity_row,
            tier_id=self.tier_id, evaluated_at=self.evaluated_at)

    async def grants(self) -> list[tuple[str, str]]:
        """Every grant row of this account as a sorted (source, status) pair list."""
        # Sorted, not in insertion order: the ids are uuid4 and their ascending order is not seeded order.
        rows = await self.session.exec(text(
            "SELECT source::text, status::text FROM core.access_grants "
            "WHERE user_id = :user_id").bindparams(user_id=self.user_id))
        return sorted(tuple(row) for row in rows.all())


@contextlib.asynccontextmanager
async def _account_holding(schema_db_uri: str, rows: tuple[_Row, ...],
                           *, evaluated_before: timedelta = timedelta(0)):
    """Seed a google account holding `rows`, and yield an open session the writer runs on."""
    subject = f"outcome-{uuid.uuid4().hex[:10]}"
    issuer = f"ns-outcome-{uuid.uuid4().hex[:10]}"
    instant = datetime.now(UTC)

    setup = await asyncpg.connect(schema_db_uri)
    try:
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        await setup.execute(
            "INSERT INTO core.external_identities "
            "(id, user_id, issuer, subject, provider, provider_uid, identity_state, created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, 'google', $5, 'active', $6, $6)",
            uuid.uuid4(), user_id, issuer, subject, f"google-uid-{subject}", NOW)
        for row in rows:
            grant_id = uuid.uuid4()
            await setup.execute(
                "INSERT INTO core.access_grants "
                "(id, user_id, tier_id, source, status, starts_at, ends_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                grant_id, user_id, tier_id, row.source, row.status,
                instant - row.starts_before,
                None if row.ends_before is None else instant - row.ends_before)
            await insert_usage(setup, grant_id=grant_id)
    finally:
        await setup.close()

    engine = create_async_engine(schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            identity_row = await IdentitiesDB(session).resolve_existing(issuer=issuer,
                                                                       subject=subject)
            yield _Account(session=session, user_id=user_id, identity_row=identity_row,
                           tier_id=tier_id, evaluated_at=instant - evaluated_before)
            await session.rollback()
    finally:
        await engine.dispose()
        cleanup = await asyncpg.connect(schema_db_uri)
        try:
            await cleanup.execute("DELETE FROM core.user_monthly_usage WHERE grant_id IN "
                                  "(SELECT id FROM core.access_grants WHERE user_id = $1)", user_id)
            await cleanup.execute("DELETE FROM core.access_grants WHERE user_id = $1", user_id)
            await cleanup.execute("DELETE FROM core.external_identities WHERE issuer = $1", issuer)
            await cleanup.execute("DELETE FROM core.users WHERE id = $1", user_id)
            await cleanup.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)
        finally:
            await cleanup.close()


class _CommitsBeforeTheFlush:
    """A session that lets a second connection commit a winning row just before the writer flushes."""

    def __init__(self, session, interfere) -> None:
        self.session = session
        self.interfere = interfere
        self.interfered = False

    async def flush(self, *args, **kwargs):
        if not self.interfered:
            self.interfered = True
            await self.interfere()
        return await self.session.flush(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.session, name)


@pytest.mark.asyncio
class TestTheRegisteredWriterNamesWhyItRefused:
    """CR-01, WR-02 and WR-03 at the writer: a refusal and a lost race are two answers, not one."""

    async def test_a_clean_account_is_activated(self, _schema_db_uri):
        """The control: without it a writer that refused everything would satisfy every case below."""
        async with _account_holding(_schema_db_uri, ()) as account:
            assert await account.activate() is ActivationOutcome.activated
            assert await account.grants() == [("registered_account_grant", "active")]

    async def test_a_term_lapsed_active_row_is_refused_and_not_lost(self, _schema_db_uri):
        """CR-01 at the writer: the row sits inside the one-active index and outside the effective read."""
        held = (_Row("manual", ends_before=timedelta(minutes=1)),)
        async with _account_holding(_schema_db_uri, held) as account:
            assert await account.activate() is ActivationOutcome.refused
            assert await account.grants() == [("manual", "active")]

    async def test_a_spent_registered_slot_is_refused_and_not_lost(self, _schema_db_uri):
        """WR-02 at the writer: the lifetime index carries no status, so one revoked row is the slot."""
        held = (_Row("registered_account_grant", status="revoked"),
                _Row("anonymous_device_grant"))
        async with _account_holding(_schema_db_uri, held) as account:
            assert await account.activate() is ActivationOutcome.refused
            assert await account.grants() == sorted([("registered_account_grant", "revoked"),
                                                      ("anonymous_device_grant", "active")])

    async def test_the_repeat_is_a_lost_race_and_not_a_refusal(self, _schema_db_uri):
        """The one in-lock branch WR-03 agrees is a 200: the winner's row is there to be read back."""
        async with _account_holding(_schema_db_uri,
                                    (_Row("registered_account_grant"),)) as account:
            assert await account.activate() is ActivationOutcome.lost_race

    async def test_a_unique_violation_at_the_flush_is_a_lost_race(self, _schema_db_uri):
        """A second connection commits the winning row after the writer's reads and before its flush."""
        async with _account_holding(_schema_db_uri, ()) as account:
            winner = await asyncpg.connect(_schema_db_uri)

            async def commit_the_winner() -> None:
                await winner.execute(
                    "INSERT INTO core.access_grants (id, user_id, tier_id, source, status) "
                    "VALUES ($1, $2, $3, 'registered_account_grant', 'active')",
                    uuid.uuid4(), account.user_id, account.tier_id)

            racing = _Account(session=_CommitsBeforeTheFlush(account.session, commit_the_winner),
                              user_id=account.user_id, identity_row=account.identity_row,
                              tier_id=account.tier_id, evaluated_at=account.evaluated_at)
            try:
                assert await racing.activate() is ActivationOutcome.lost_race
            finally:
                await winner.close()

    async def test_a_check_violation_is_raised_and_never_read_as_a_lost_race(self, _schema_db_uri):
        """WR-01 made executable: the expiry UPDATE breaks `ends_at > starts_at`, which is no race."""
        held = (_Row("anonymous_device_grant", starts_before=timedelta(0)),)
        async with _account_holding(_schema_db_uri, held) as account:
            with pytest.raises(IntegrityError) as refused:
                await account.activate()
            # Not 23505, which is the whole reason the narrowed catch re-raises this one.
            assert getattr(refused.value.orig.__cause__, "sqlstate", None) != UNIQUE_VIOLATION


@pytest.mark.asyncio
class TestTheDriverCarriesTheSqlstateTheNarrowingReads:
    """The narrowing fails closed on an absent attribute, so its presence on this driver is measured."""

    async def test_a_duplicate_active_grant_carries_sqlstate_23505(self, _schema_db_uri):
        async with _account_holding(_schema_db_uri,
                                    (_Row("manual"),)) as account:
            account.session.add(AccessGrant(user_id=account.user_id, tier_id=account.tier_id,
                                            source=AccessGrantSource.manual,
                                            starts_at=account.evaluated_at))
            with pytest.raises(IntegrityError) as violation:
                await account.session.flush()

        assert getattr(violation.value.orig.__cause__, "sqlstate", None) == UNIQUE_VIOLATION
        assert type(violation.value.orig.__cause__).__name__ == "UniqueViolationError"


@pytest.mark.asyncio
class TestTheFreeGrantSourceSetMatchesTheIndex:
    """ANONGRANT-03. Narrowing FREE_GRANT_SOURCES back to one member reopens a spent lifetime slot for every
    account that already used one, so it goes red here rather than silently."""

    async def test_the_named_set_equals_the_live_index_predicate(self, conn):
        """Pinned to the asyncpg default search path, which is how this suite keeps expected strings literal."""
        await conn.execute(f"SET search_path TO {PINNED_SEARCH_PATH}")
        predicate = await conn.fetchval(_INDEX_PREDICATE, _LIFETIME_INDEX)

        carried = set(_SOURCE_LITERAL.findall(predicate or ""))
        assert carried, f"no source literal parsed out of {predicate!r}"
        assert carried == {source.value for source in FREE_GRANT_SOURCES}
