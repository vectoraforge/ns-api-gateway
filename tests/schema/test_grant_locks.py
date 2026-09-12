"""The grant-then-usage lock order under real contention, the activation path's tiers, and the free-grant set."""
import asyncio
import contextlib
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.store_notifications import RestoredSubscription
from nativespeaker.api.crud.grants import (
    ActivationOutcome,
    GrantsDB,
    _effective_grants_statement,
    _usage_statement,
)
from nativespeaker.api.services.restore import RestoreService
from nativespeaker.api.services.subscriptions import SubscriptionsService
from nativespeaker.api.tables import PurchaseProvider, SubscriptionStatus
from nativespeaker.api.tables.grants import (
    FREE_GRANT_SOURCES,
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
)
from nativespeaker.api.tables.identities import NativeClaimProvider
from schema.helpers import (
    insert_grant,
    insert_subscription,
    insert_tier,
    insert_usage,
    insert_user,
)
from schema.test_restore_race import _ScriptedAppStore, identity_of
from schema.test_subscription_ingestion import _clean, _notification

pytestmark = pytest.mark.schema


def _issuable(statement) -> str:
    """One production statement as the literal SQL a raw asyncpg connection can issue."""
    return str(statement.compile(dialect=postgresql.asyncpg.dialect(),
                                 compile_kwargs={"literal_binds": True}))


def _lock_grants(user_id: uuid.UUID) -> str:
    """The SQL `GrantsDB.lock_effective_grants` compiles, so there is no mirror left to drift."""
    return _issuable(_effective_grants_statement(user_id).with_for_update())


def _lock_usage(grant_id: uuid.UUID) -> str:
    """The SQL `GrantsDB.lock_usage` compiles, so there is no mirror left to drift."""
    return _issuable(_usage_statement(grant_id).with_for_update())


class TestTheIssuedStatementsAreProductionsOwn:
    """The contention cases below issue exactly what production compiles, so a production drift
    reaches them. These pin the two properties the cases read but cannot see. No database."""

    def test_the_grant_lock_carries_the_lock_the_order_and_no_cap(self):
        issued = _lock_grants(uuid.uuid4())

        assert "FOR UPDATE" in issued
        assert "ORDER BY core.access_grants.id ASC" in issued
        assert "LIMIT" not in issued
        for term in ("core.access_grants.user_id = ",
                     "core.access_grants.status = ",
                     "core.access_grants.starts_at <= ",
                     "core.access_grants.ends_at IS NULL",
                     "core.access_grants.ends_at > "):
            assert term in issued, f"the effective predicate no longer carries {term!r}"

    def test_the_usage_lock_carries_the_lock_and_the_whole_key(self):
        issued = _lock_usage(uuid.uuid4())

        assert "FOR UPDATE" in issued
        assert "core.user_monthly_usage.grant_id = " in issued


# Longer than PostgreSQL's 1s deadlock_timeout, so a deadlock case fails on a missed detection, not a timeout.
_WAIT = "5s"

# Short on purpose: the blocking cases assert a lock is NOT available, so the timeout is their instrument.
_NO_WAIT = "500ms"

_A_HOLDS_FOR_SECONDS = 0.2


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
            held = await conn_a.fetch(_lock_grants(committed_grant.user_id))
            assert [row["id"] for row in held] == [committed_grant.grant_id], \
                "control: A must actually hold the seeded grant row, or B has nothing to wait for"

            with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
                await conn_b.fetch(_lock_grants(committed_grant.user_id))
        finally:
            await _rollback(tx_b)
            await _rollback(tx_a)

    async def test_the_lock_is_released_when_the_first_transaction_ends(self, committed_grant,
                                                                        contenders):
        """A lock that never released would be a hang, not a gate; the short timeout is what asserts that."""
        conn_a, conn_b = contenders
        tx_a = await _begin(conn_a, lock_timeout=_WAIT)
        await conn_a.fetch(_lock_grants(committed_grant.user_id))
        await _rollback(tx_a)

        tx_b = await _begin(conn_b, lock_timeout=_NO_WAIT)
        try:
            rows = await conn_b.fetch(_lock_grants(committed_grant.user_id))
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
            await conn_a.fetch(_lock_grants(committed_grant.user_id))   # fixed order, step 1
            await conn_b.fetch(_lock_usage(committed_grant.grant_id))   # reverse order, step 1

            outcomes = await asyncio.gather(
                conn_a.fetch(_lock_usage(committed_grant.grant_id)),    # fixed order, step 2
                conn_b.fetch(_lock_grants(committed_grant.user_id)),    # reverse order, step 2
                return_exceptions=True,
            )

            deadlocked = [outcome for outcome in outcomes
                          if isinstance(outcome, asyncpg.exceptions.DeadlockDetectedError)]
            assert len(deadlocked) == 1, f"expected exactly one deadlock victim, got {outcomes}"
        finally:
            await _rollback(tx_b)
            await _rollback(tx_a)

    @pytest.mark.timing
    async def test_the_fixed_order_does_not_deadlock(self, committed_grant, contenders):
        """The control: both transactions take the fixed order, the second waits, and nothing is aborted."""
        conn_a, conn_b = contenders
        tx_a = await _begin(conn_a, lock_timeout=_WAIT)
        tx_b = await _begin(conn_b, lock_timeout=_WAIT)
        released_at = None
        try:
            await conn_a.fetch(_lock_grants(committed_grant.user_id))
            await conn_a.fetch(_lock_usage(committed_grant.grant_id))

            async def b_takes_the_same_order_and_waits():
                asked_at = time.monotonic()
                await conn_b.fetch(_lock_grants(committed_grant.user_id))
                acquired_at = time.monotonic()
                usage = await conn_b.fetch(_lock_usage(committed_grant.grant_id))
                return asked_at, acquired_at, usage

            async def a_finishes_shortly():
                nonlocal released_at
                await asyncio.sleep(_A_HOLDS_FOR_SECONDS)
                released_at = time.monotonic()
                await tx_a.rollback()

            outcomes = await asyncio.gather(b_takes_the_same_order_and_waits(),
                                            a_finishes_shortly(),
                                            return_exceptions=True)

            assert not [outcome for outcome in outcomes if isinstance(outcome, BaseException)], \
                f"the fixed order must not deadlock or time out, got {outcomes}"
            asked_at, acquired_at, rows = outcomes[0]
            assert released_at is not None, "A never reached its release, so B waited on nothing"
            assert asked_at < released_at < acquired_at, \
                (f"B did not block on A's grant lock: asked at {asked_at:.3f}, "
                 f"A released at {released_at:.3f}, B acquired at {acquired_at:.3f}")
            assert [row["grant_id"] for row in rows] == [committed_grant.grant_id]
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

_LOCK_CLAUSE = re.compile(r"FOR (?:NO KEY )?UPDATE|FOR (?:KEY )?SHARE")

_RELATIONS = re.compile(r"\b(?:FROM|JOIN|,)\s+((?:core|audit)\.[a-z_]+)")


def locking(statements: list[str]) -> list[str]:
    """Only the statements that take a row lock, in the order the writer issued them."""
    return [statement for statement in statements if _LOCK_CLAUSE.search(statement)]


def relations_of(statement: str) -> list[str]:
    """Every core or audit relation a statement draws rows from, which for a lock is the tiers it takes."""
    # An unreadable statement returns itself, so the assertion fails and no empty list passes.
    return sorted(set(_RELATIONS.findall(statement))) or [statement]


class TestTheLockReaderSeesEveryTierAndEverySpelling:
    """The control on every tier count below: a reader blind to a join or to `FOR SHARE` passes them all."""

    @pytest.mark.parametrize("clause",
                             ["FOR UPDATE", "FOR NO KEY UPDATE", "FOR SHARE", "FOR KEY SHARE"])
    def test_every_row_lock_spelling_is_read_as_a_lock(self, clause):
        """A third tier taken with any of the four is a third tier; only the first was ever counted."""
        statement = f"SELECT core.users.id FROM core.users {clause}"
        assert locking([statement]) == [statement]

    def test_a_statement_that_takes_no_lock_is_not_read_as_one(self):
        """The boundary: a reader answering "locking" to everything would pass the case above."""
        assert locking(["SELECT core.users.id FROM core.users"]) == []

    def test_a_relation_reached_by_a_join_is_reported_beside_the_first(self):
        """The identity row locked through a join is the tier the counts below exist to refuse."""
        joined = ("SELECT core.access_grants.id FROM core.access_grants "
                  "JOIN core.external_identities ON true FOR UPDATE")
        assert relations_of(joined) == ["core.access_grants", "core.external_identities"]

    def test_a_statement_naming_no_relation_is_returned_whole(self):
        """Loudly, not as an empty list: every membership assertion below passes an empty one."""
        assert relations_of("COMMIT") == ["COMMIT"]


def writes(statements: list[str]) -> list[str]:
    """Only the statements that change a row, which is the control on every lock-tier count below."""
    return [statement for statement in statements if statement.startswith(("INSERT", "UPDATE"))]


def plain_identity_re_reads(statements: list[str]) -> list[str]:
    """Every non-locking SELECT of the identity row, which is the revalidation each writer owes."""
    return [statement for statement in statements
            if statement.startswith("SELECT") and "core.external_identities" in statement
            and "FOR UPDATE" not in statement]


def assert_one_plain_identity_re_read(captured: dict) -> None:
    """One non-locking re-read of the identity row, on an arm that provably wrote something."""
    statements = captured["statements"]
    re_reads = plain_identity_re_reads(statements)
    assert len(re_reads) == 1, f"expected one plain identity re-read, got {statements}"
    assert captured["outcome"] is ActivationOutcome.activated
    assert writes(statements), f"the writer must have written on this arm, got {statements}"


@contextlib.asynccontextmanager
async def _anonymous_writer_run(schema_db_uri: str, *, holding_grant: bool):
    """Drive GrantsDB.activate_anonymous_device_grant once, recording every statement it issues."""
    subject = f"lock-order-{uuid.uuid4().hex[:10]}"
    issuer = f"ns-lock-order-{uuid.uuid4().hex[:10]}"

    setup = await asyncpg.connect(schema_db_uri)
    try:
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        if holding_grant:
            grant_id = await insert_grant(setup, user_id=user_id, tier_id=tier_id, source="manual")
            await insert_usage(setup, grant_id=grant_id)
        await setup.execute(
            "INSERT INTO core.external_identities "
            "(id, user_id, issuer, subject, provider, identity_state, created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, 'anonymous', 'active', $5, $5)",
            uuid.uuid4(), user_id, issuer, subject, NOW)
    finally:
        await setup.close()

    engine = create_async_engine(schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    recorded: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        recorded.append(" ".join(statement.split()))

    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            # Everything above is setup; only what the writer itself issues is the subject of this fixture.
            recorded.clear()
            outcome, _ = await GrantsDB(session).activate_anonymous_device_grant(
                user_id=user_id, issuer=issuer, subject=subject,
                claim_platform=NativeClaimProvider.ios_devicecheck,
                tier_id=tier_id)
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
async def activation_statements(_schema_db_uri):
    """The anonymous writer driven on a caller already holding a grant, so it refuses and writes nothing."""
    async with _anonymous_writer_run(_schema_db_uri, holding_grant=True) as run:
        yield run


@pytest_asyncio.fixture
async def anonymous_activated_statements(_schema_db_uri):
    """The anonymous writer on a clean account: it activates, so the writing arm is the subject."""
    async with _anonymous_writer_run(_schema_db_uri, holding_grant=False) as run:
        yield run


@pytest.mark.asyncio
class TestTheActivationAddsNoThirdLockTier:
    """ANONGRANT-02. An identity or user row may never be locked ahead of the grant rows: SHARED-INVARIANTS:33.
    The brief this phase implements says the opposite, and the invariants win by precedence (D-13)."""

    async def test_the_writer_locks_the_grant_rows_then_their_usage_rows(self, activation_statements):
        """The ORDER BY is the lock order itself, not presentation, so it is asserted with the tier."""
        taken = locking(activation_statements["statements"])
        assert [relations_of(statement) for statement in taken] == [["core.access_grants"],
                                                                    ["core.access_grants"],
                                                                    ["core.user_monthly_usage"]]
        for statement in taken[:2]:
            assert "ORDER BY core.access_grants.id ASC" in statement

    async def test_exactly_two_distinct_lock_tiers_are_taken_on_the_claim_path(self,
                                                                               activation_statements):
        """Two, and never a third: a writer that locks the identity or user row first fails here, not in production."""
        taken = [relation for statement in locking(activation_statements["statements"])
                 for relation in relations_of(statement)]
        assert len(set(taken)) == 2
        assert "core.external_identities" not in taken
        assert "core.users" not in taken

    async def test_the_identity_row_is_revalidated_by_a_plain_re_read(self, activation_statements):
        """The control: the writer issues more statements than it locks, so the count above is not vacuously small."""
        statements = activation_statements["statements"]
        re_reads = plain_identity_re_reads(statements)
        assert len(re_reads) == 1, f"expected one plain identity re-read, got {statements}"
        assert activation_statements["outcome"] is ActivationOutcome.refused
        # The control that matters: `False` must come from the held-grant check, not from a rejected insert,
        # or the two tiers above would be one lock and one write and the count would read as two by accident.
        assert not [statement for statement in statements if statement.startswith("INSERT")], \
            f"the writer must stop at the held grant and write nothing, got {statements}"

    async def test_the_activating_arm_locks_the_grant_tier_alone(self,
                                                                 anonymous_activated_statements):
        """The arm the held-grant fixture never reaches: it inserts the grant, its usage row and the
        identity marker, and a third tier taken on that path is the SHARED-INVARIANTS:33 breach."""
        locked = locking(anonymous_activated_statements["statements"])
        assert [relations_of(statement) for statement in locked] == [["core.access_grants"],
                                                                     ["core.access_grants"]]
        taken = [relation for statement in locked for relation in relations_of(statement)]
        assert "core.external_identities" not in taken
        assert "core.users" not in taken
        for statement in locked[:2]:
            assert "ORDER BY core.access_grants.id ASC" in statement

    async def test_the_activating_arm_revalidates_the_identity_row_by_a_plain_re_read(
            self, anonymous_activated_statements):
        """The control the refused arm cannot give: this arm provably wrote, so the count is not vacuous."""
        assert_one_plain_identity_re_read(anonymous_activated_statements)


def first_index(statements: list[str], prefix: str) -> int:
    """Where `prefix` first appears among the recorded statements, or -1 if it never does."""
    for position, statement in enumerate(statements):
        if statement.startswith(prefix):
            return position
    return -1


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

    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            # Everything above is setup; only what the writer itself issues is the subject of this fixture.
            recorded.clear()
            outcome, _ = await GrantsDB(session).activate_registered_account_grant(
                user_id=user_id, issuer=issuer, subject=subject,
                tier_id=tier_id)
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
        assert [relations_of(statement) for statement in taken] == [["core.access_grants"],
                                                                    ["core.access_grants"],
                                                                    ["core.user_monthly_usage"]]
        for statement in taken[:2]:
            assert "ORDER BY core.access_grants.id ASC" in statement

    async def test_exactly_two_distinct_lock_tiers_are_taken_on_the_conversion(self,
                                                                               conversion_statements):
        """Two, and never a third: a writer that locks the identity or user row fails here, not in production."""
        taken = [relation for statement in locking(conversion_statements["statements"])
                 for relation in relations_of(statement)]
        assert len(set(taken)) == 2
        assert "core.external_identities" not in taken
        assert "core.users" not in taken

    async def test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row(
            self, new_grant_statements):
        """A clean account has nothing in either tier, so `FOR UPDATE` locks nothing and the indexes arbitrate."""
        locked = locking(new_grant_statements["statements"])
        assert [relations_of(statement) for statement in locked] == [["core.access_grants"],
                                                                     ["core.access_grants"]]
        taken = [relation for statement in locked for relation in relations_of(statement)]
        assert "core.external_identities" not in taken
        assert "core.users" not in taken
        for statement in locked[:2]:
            assert "ORDER BY core.access_grants.id ASC" in statement

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
    """A seeded account, an open session, and the instant the seeded rows are dated from."""
    session: SQLModelAsyncSession
    user_id: uuid.UUID
    issuer: str
    subject: str
    tier_id: str
    evaluated_at: datetime

    async def activate(self):
        """The outcome alone: the arm the writer names is asserted in the unit suites."""
        outcome, _ = await GrantsDB(self.session).activate_registered_account_grant(
            user_id=self.user_id, issuer=self.issuer, subject=self.subject,
            tier_id=self.tier_id)
        return outcome

    async def activate_anonymous(
            self, claim_platform: NativeClaimProvider = NativeClaimProvider.ios_devicecheck):
        """The other free-grant writer, on the same seed and the same session.
        The platform is a parameter because 06 step 7 refuses material from the other one."""
        outcome, _ = await GrantsDB(self.session).activate_anonymous_device_grant(
            user_id=self.user_id, issuer=self.issuer, subject=self.subject,
            claim_platform=claim_platform,
            tier_id=self.tier_id)
        return outcome

    async def claim_platform(self) -> str | None:
        """The pin the identity row carries, read back as the column's own text."""
        pinned = await self.session.exec(text(
            "SELECT native_claim_platform::text FROM core.external_identities "
            "WHERE user_id = :user_id").bindparams(user_id=self.user_id))
        return pinned.one()[0]

    async def grants(self) -> list[tuple[str, str]]:
        """Every grant row of this account as a sorted (source, status) pair list."""
        # Sorted, not in insertion order: the ids are uuid4 and their ascending order is not seeded order.
        rows = await self.session.exec(text(
            "SELECT source::text, status::text FROM core.access_grants "
            "WHERE user_id = :user_id").bindparams(user_id=self.user_id))
        return sorted(tuple(row) for row in rows.all())


@contextlib.asynccontextmanager
async def _account_holding(schema_db_uri: str, rows: tuple[_Row, ...],
                           *, provider: str = "google"):
    """Seed an account of `provider` holding `rows`, and yield an open session the writer runs on."""
    subject = f"outcome-{uuid.uuid4().hex[:10]}"
    issuer = f"ns-outcome-{uuid.uuid4().hex[:10]}"
    instant = datetime.now(UTC)

    setup = await asyncpg.connect(schema_db_uri)
    try:
        user_id = await insert_user(setup)
        tier_id = await insert_tier(setup)
        provider_uid = None if provider == "anonymous" else f"{provider}-uid-{subject}"
        await setup.execute(
            "INSERT INTO core.external_identities "
            "(id, user_id, issuer, subject, provider, provider_uid, identity_state, created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $7)",
            uuid.uuid4(), user_id, issuer, subject, provider, provider_uid, NOW)
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
            yield _Account(session=session, user_id=user_id, issuer=issuer, subject=subject,
                           tier_id=tier_id, evaluated_at=instant)
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
                              user_id=account.user_id, issuer=account.issuer,
                              subject=account.subject,
                              tier_id=account.tier_id, evaluated_at=account.evaluated_at)
            try:
                assert await racing.activate() is ActivationOutcome.lost_race
            finally:
                await winner.close()

    async def test_a_check_violation_is_raised_and_never_read_as_a_lost_race(self, _schema_db_uri):
        """WR-01 made executable: a row breaking `ends_at > starts_at` goes in with the writer's own
        inserts, and the real driver's code for it is no race for the narrowed catch to swallow."""
        async with _account_holding(_schema_db_uri, ()) as account:

            async def break_the_term_check() -> None:
                account.session.add(AccessGrant(user_id=account.user_id,
                                                tier_id=account.tier_id,
                                                source=AccessGrantSource.manual,
                                                status=AccessGrantStatus.expired,
                                                starts_at=account.evaluated_at,
                                                ends_at=account.evaluated_at,
                                                created_at=account.evaluated_at,
                                                updated_at=account.evaluated_at))

            breaking = _Account(session=_CommitsBeforeTheFlush(account.session,
                                                                break_the_term_check),
                                user_id=account.user_id, issuer=account.issuer,
                                subject=account.subject,
                                tier_id=account.tier_id, evaluated_at=account.evaluated_at)
            with pytest.raises(IntegrityError) as refused:
                await breaking.activate()
            # 23514 and not 23505: the narrowed catch swallows the unique violation and no other.
            assert refused.value.orig.sqlstate == "23514"


@pytest.mark.asyncio
class TestTheAnonymousWriterNamesWhyItRefused:
    """WR-40. The twin of the class above: the anonymous writer read the same state as a lost race,
    because it took the effective tier alone and never asked the one-active index's own question."""

    async def test_a_clean_account_is_activated(self, _schema_db_uri):
        """The control: without it a writer that refused everything would satisfy the case below."""
        async with _account_holding(_schema_db_uri, (), provider="anonymous") as account:
            assert await account.activate_anonymous() is ActivationOutcome.activated
            assert await account.grants() == [("anonymous_device_grant", "active")]

    async def test_a_term_lapsed_active_row_is_refused_and_not_lost(self, _schema_db_uri):
        """The row sits inside the one-active index and outside the effective read, so the insert
        this writer used to issue was doomed and its unique violation was never a race."""
        held = (_Row("manual", ends_before=timedelta(minutes=1)),)
        async with _account_holding(_schema_db_uri, held, provider="anonymous") as account:
            assert await account.activate_anonymous() is ActivationOutcome.refused
            assert await account.grants() == [("manual", "active")]

    async def test_the_repeat_is_a_lost_race_and_not_a_refusal(self, _schema_db_uri):
        """The one in-lock branch that stays a 200: the winner's row is there to be read back."""
        async with _account_holding(_schema_db_uri, (_Row("anonymous_device_grant"),),
                                    provider="anonymous") as account:
            assert await account.activate_anonymous() is ActivationOutcome.lost_race

    async def test_material_from_the_other_platform_is_refused_once_the_pin_is_set(
            self, _schema_db_uri):
        """06 step 7: the pin is immutable, so the other platform's material is refused and
        restamps nothing. The refusal, not a lost race: with the guard gone this same state
        answers `lost_race`, because the first claim's row is an active `anonymous_device_grant`."""
        async with _account_holding(_schema_db_uri, (), provider="anonymous") as account:
            assert await account.activate_anonymous() is ActivationOutcome.activated

            refused = await account.activate_anonymous(NativeClaimProvider.android_play_integrity)

            assert refused is ActivationOutcome.refused
            assert await account.grants() == [("anonymous_device_grant", "active")]
            assert await account.claim_platform() == "ios_devicecheck"


@pytest.mark.asyncio
class TestTheDriverCarriesTheSqlstateTheNarrowingReads:
    """The narrowing fails closed on an absent attribute, so its presence on this driver is measured."""

    async def test_a_duplicate_active_grant_carries_sqlstate_23505(self, _schema_db_uri):
        async with _account_holding(_schema_db_uri,
                                    (_Row("manual"),)) as account:
            account.session.add(AccessGrant(user_id=account.user_id, tier_id=account.tier_id,
                                            source=AccessGrantSource.manual,
                                            starts_at=account.evaluated_at,
                                            created_at=account.evaluated_at,
                                            updated_at=account.evaluated_at))
            with pytest.raises(IntegrityError) as violation:
                await account.session.flush()

        assert violation.value.orig.sqlstate == "23505"
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


# The subscription writer, captured on the same terms as the two above and never from a mirrored literal.


@contextlib.asynccontextmanager
async def _ingestion_run(schema_db_uri: str, *, attributed: bool):
    """Drive SubscriptionsService.ingest once, recording every statement the writer issues."""
    token = f"token-{uuid.uuid4()}" if attributed else None
    user_id = None

    setup = await asyncpg.connect(schema_db_uri)
    try:
        tier_id = await insert_tier(setup)
        if attributed:
            user_id = await insert_user(setup)
            await setup.execute(
                "INSERT INTO core.store_purchase_tokens (user_id, provider, identity_value) "
                "VALUES ($1, 'apple', $2)", user_id, token)
            # A held `manual` grant with its usage row, so both tiers have a real row to lock and to order.
            grant_id = await insert_grant(setup, user_id=user_id, tier_id=tier_id, source="manual")
            await insert_usage(setup, grant_id=grant_id)
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
    external_id = f"original-{uuid.uuid4().hex[:12]}"
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            # Everything above is setup; only what the writer itself issues is the subject of this fixture.
            recorded.clear()
            await SubscriptionsService(db=session,
                                       evaluated_at=evaluated_at).ingest(_notification(
                                           external_id=external_id,
                                           token=token,
                                           tier_id=tier_id,
                                           purchased_at=evaluated_at - timedelta(days=30),
                                           expires_at=evaluated_at + timedelta(days=30)))
        yield {"statements": list(recorded)}
    finally:
        await engine.dispose()
        cleanup = await asyncpg.connect(schema_db_uri)
        try:
            await _clean(cleanup, user_id=user_id, tier_id=tier_id)
        finally:
            await cleanup.close()


@pytest_asyncio.fixture
async def ingestion_statements(_schema_db_uri):
    """The ingestion driven for a buyer who holds one grant, so both tiers have a row to take."""
    async with _ingestion_run(_schema_db_uri, attributed=True) as run:
        yield run


@pytest_asyncio.fixture
async def unattributed_statements(_schema_db_uri):
    """The ingestion driven for a notification with no attribution token, which has no buyer."""
    async with _ingestion_run(_schema_db_uri, attributed=False) as run:
        yield run


@pytest.mark.asyncio
class TestTheSubscriptionWriterAddsNoThirdLockTier:
    """APPLEHOOK-01, D-16. The store callback runs under the same fixed order the two claims do:
    SHARED-INVARIANTS:33, proven from the statements the writer emits rather than from its Python."""

    async def test_the_ingestion_locks_the_grant_rows_then_their_usage_rows(self,
                                                                            ingestion_statements):
        """The ORDER BY is the lock order itself, not presentation, so it is asserted with the tier."""
        taken = locking(ingestion_statements["statements"])
        assert [relations_of(statement) for statement in taken] == [["core.access_grants"],
                                                                    ["core.user_monthly_usage"]]
        assert "ORDER BY core.access_grants.id ASC" in taken[0]

    async def test_exactly_two_distinct_lock_tiers_are_taken_on_the_ingestion(self,
                                                                              ingestion_statements):
        """Two, and never a third: a writer that locks the subscription or the purchase row fails here."""
        taken = [relation for statement in locking(ingestion_statements["statements"])
                 for relation in relations_of(statement)]
        assert len(set(taken)) == 2
        assert "core.subscriptions" not in taken
        assert "core.store_purchases" not in taken
        assert "core.users" not in taken

    async def test_the_unattributed_path_takes_no_lock_at_all(self, unattributed_statements):
        """With no buyer there is no row to lock, and the unique indexes are what serialise the case."""
        assert locking(unattributed_statements["statements"]) == []

    async def test_each_arm_wrote_something(self, ingestion_statements, unattributed_statements):
        """The control: a writer that issued nothing would satisfy both counts above vacuously."""
        assert writes(ingestion_statements["statements"])
        assert writes(unattributed_statements["statements"])


@contextlib.asynccontextmanager
async def _restore_move_run(schema_db_uri: str):
    """Drive RestoreService.restore once for a move, recording every statement the writer issues.
    A move is the one restore that names two accounts, so it is the one that can order two ways."""
    setup = await asyncpg.connect(schema_db_uri)
    try:
        tier_id = await insert_tier(setup)
        old_owner = await insert_user(setup)
        destination = await insert_user(setup)
        external_id = f"restore-locks-{uuid.uuid4().hex[:12]}"
        subscription_id = await insert_subscription(setup, external_id=external_id,
                                                    tier_id=tier_id, user_id=old_owner)
        for user_id, source, names in ((old_owner, "subscription", subscription_id),
                                       (destination, "manual", None)):
            grant_id = await insert_grant(setup, user_id=user_id, tier_id=tier_id, source=source,
                                          subscription_id=names)
            await insert_usage(setup, grant_id=grant_id)
            await setup.execute("UPDATE core.access_grants SET starts_at = $2, ends_at = $3"
                                " WHERE id = $1", grant_id,
                                datetime.now(UTC) - timedelta(hours=1),
                                datetime.now(UTC) + timedelta(days=30))
    finally:
        await setup.close()

    engine = create_async_engine(schema_db_uri.replace(_ASYNCPG_PREFIX, _SQLALCHEMY_PREFIX, 1))
    recorded: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        recorded.append(" ".join(statement.split()))

    evaluated_at = datetime.now(UTC)
    proof = RestoredSubscription(provider=PurchaseProvider.apple, external_id=external_id,
                                 product_id="com.nativespeaker.subscription.monthly",
                                 tier_id=tier_id, attribution_token=None,
                                 status=SubscriptionStatus.active,
                                 purchased_at=evaluated_at - timedelta(days=30),
                                 expires_at=evaluated_at + timedelta(days=30),
                                 grace_period_expires_at=None)
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            recorded.clear()
            await RestoreService(db=session, evaluated_at=evaluated_at,
                                 app_store=_ScriptedAppStore(proof),
                                 play=None,
                                 package_name="com.nativespeaker.app").restore(
                                     identity_of(destination), PurchaseProvider.apple,
                                     "a-signed-transaction-the-scripted-seam-accepts")
            await session.commit()
        yield {"statements": list(recorded)}
    finally:
        await engine.dispose()
        cleanup = await asyncpg.connect(schema_db_uri)
        try:
            await _clean(cleanup, user_id=None, tier_id=tier_id)
            for user_id in (old_owner, destination):
                await cleanup.execute("DELETE FROM core.users WHERE id = $1", user_id)
            await cleanup.execute("DELETE FROM core.access_tiers WHERE id = $1", tier_id)
        finally:
            await cleanup.close()


@pytest_asyncio.fixture
async def move_statements(_schema_db_uri):
    """The restore driven as a move, which is the only writer D-08 gives two accounts to lock."""
    async with _restore_move_run(_schema_db_uri) as run:
        yield run


@pytest.mark.asyncio
class TestTheRestoreLocksBothAccountsInOneAscendingStatement:
    """WR-80, D-08. The move is the one writer that names two accounts, so it is the one that can
    take the grant tier in two orders. Two orders between two movers is the deadlock, and the
    single ascending statement is what prevents it -- proven from the statements it emits."""

    async def test_the_move_takes_the_grant_tier_first_then_the_usage_rows(self, move_statements):
        taken = locking(move_statements["statements"])
        assert [relations_of(statement) for statement in taken] == [["core.access_grants"],
                                                                    ["core.user_monthly_usage"],
                                                                    ["core.user_monthly_usage"]]
        assert "ORDER BY core.access_grants.id ASC" in taken[0]

    async def test_both_accounts_grant_rows_are_taken_in_one_statement(self, move_statements):
        """Two grant-tier statements are two orders, whatever each one of them orders by."""
        taken = locking(move_statements["statements"])
        grant_tier = [statement for statement in taken if "core.access_grants" in statement]
        assert len(grant_tier) == 1
        assert "core.access_grants.user_id IN (" in grant_tier[0]

    async def test_the_move_adds_no_third_lock_tier(self, move_statements):
        """Two, and never a third: a restore that locks the subscription row fails here."""
        taken = [relation for statement in locking(move_statements["statements"])
                 for relation in relations_of(statement)]
        assert set(taken) == {"core.access_grants", "core.user_monthly_usage"}

    async def test_the_move_wrote_something(self, move_statements):
        """The control: a restore that issued nothing would satisfy every count above vacuously."""
        assert writes(move_statements["statements"])
