"""The grant-then-usage lock order under real contention: the only module where two transactions contend."""
import asyncio
import contextlib
import uuid
from dataclasses import dataclass

import asyncpg
import pytest
import pytest_asyncio

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
