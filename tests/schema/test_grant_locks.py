"""SHARED-INVARIANTS:33 / REBIND-05 -- the grant-then-usage lock order, under real contention.

Every other proof of this invariant in the repo is statement-level: `tests/unit/test_quota_resolver.py`
asserts the *sequence of statements* the resolver issues, and `tests/e2e/test_quota.py` asserts that
the effective-grant select carries `FOR UPDATE`. Neither can show that the locks actually exclude
anybody, because neither has a second transaction to be excluded. The e2e package cannot grow one:
its `_db_transaction` fixture pins every session to a single connection inside one uncommitted
transaction, which is exactly what makes its rollback isolation work. This suite is the only place
in the repo where two transactions can genuinely contend, so this is where the invariant gets
tested rather than argued.

The load-bearing case is `test_the_reverse_order_deadlocks`. A fixed lock order is the kind of rule
no CHECK constraint can express and no code review reliably enforces, and Phases 41, 42 and 45 are
each required to copy `GrantsDB`'s statement order rather than invent their own. This module is what
makes "grant first, then usage" a fact about the database rather than a convention about the source:
take the two locks the other way round against a holder of the fixed order and PostgreSQL aborts
one of the transactions.

**The locking statements here are written directly against the two tables, not through `GrantsDB`.**
This suite is asyncpg-based and has no SQLModel session to hand the class. `_LOCK_GRANTS` mirrors
`GrantsDB.lock_effective_grants` and `_LOCK_USAGE` mirrors `GrantsDB.lock_usage`; a change to either
method has a matching test here to update, and a divergence between the two is the thing this
comment exists to make noticeable.

**This is the only module in the repo that commits rows outside a rolled-back transaction.** It has
to: the `conn` fixture never commits, so its rows are invisible to any other connection, and a
second connection contending for them would match zero rows and return instantly -- the test would
pass while proving nothing. The `committed_grant` fixture below therefore commits its seed and
removes it in a `finally`. `test_apply_rollback.py::TestSeededTiers::test_seeded_tiers_and_credits`
is the independent detector if it ever fails to: a leaked `core.access_tiers` row fails that case on
the next run.
"""
import asyncio
import contextlib
import uuid
from dataclasses import dataclass

import asyncpg
import pytest
import pytest_asyncio

from schema.helpers import insert_grant, insert_tier, insert_usage, insert_user

pytestmark = pytest.mark.schema

# Mirrors GrantsDB.lock_effective_grants: the shared effective-grant predicate, FOR UPDATE,
# ascending by grant id, with no row-count cap. The ORDER BY is the lock order itself, not
# presentation -- it is what makes two concurrent transactions take the same rows in the same
# sequence.
_LOCK_GRANTS = (
    "SELECT id FROM core.access_grants "
    "WHERE user_id = $1 AND status = 'active' "
    "  AND starts_at <= CURRENT_TIMESTAMP "
    "  AND (ends_at IS NULL OR ends_at > CURRENT_TIMESTAMP) "
    "ORDER BY id ASC "
    "FOR UPDATE"
)

# Mirrors GrantsDB.lock_usage: second in the order, keyed on the table's whole primary key, and
# never an INSERT.
_LOCK_USAGE = "SELECT grant_id FROM core.user_monthly_usage WHERE grant_id = $1 FOR UPDATE"

# Long enough that the deadlock detector (PostgreSQL's `deadlock_timeout`, 1s by default) always
# wins the race, so the deadlock cases fail on a missed detection instead of on the timeout that
# was meant to be a backstop. `deadlock_timeout` itself is deliberately left alone: it is a
# superuser-only setting, and a test that silently needs superuser is a test that breaks on the
# first CI runner that is not one.
_WAIT = "5s"

# Short on purpose: the blocking cases assert that a lock is NOT available, so their timeout is the
# assertion's instrument rather than a safety net, and every second of it is a second of test time.
_NO_WAIT = "500ms"


@dataclass(frozen=True)
class _Seeded:
    user_id: uuid.UUID
    tier_id: str
    grant_id: uuid.UUID


@pytest_asyncio.fixture
async def committed_grant(_schema_db_uri):
    """A committed user, tier, grant and usage row, visible to every connection. Removed after.

    Committed rather than seeded through the `conn` fixture, for the reason in the module
    docstring: uncommitted rows are invisible to the second connection and every contention case
    would pass vacuously.

    `source='manual'`, not the helper's `anonymous_device_grant` default. Both free sources
    populate the generated `anti_abuse_required_grant_id` column, whose `DEFERRABLE INITIALLY
    DEFERRED` FK (migrations/20260818_01_initial-release.sql:520-523) demands a matching
    `core.access_grants_anti_abuse` row **at commit time** -- which the rest of this suite never
    reaches, because it never commits. `manual` is the source the schema reserves for a
    hand-issued grant and requires no companion row.

    Teardown deletes the grant and then the user and the tier. `core.user_monthly_usage` has
    `ON DELETE CASCADE` on its grant FK, so removing the grant removes its usage row. The `finally`
    is what makes the cleanup unconditional: a case that deadlocks, times out, or fails an
    assertion must still leave the database as it found it.
    """
    setup = await asyncpg.connect(_schema_db_uri)
    try:
        # No transaction block: asyncpg autocommits each statement, which is the commit these rows
        # need in order to be visible to connections A and B below.
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
    """Two live connections, A and B, each closed however the case ends.

    Nested `finally` blocks rather than one flat close, following `test_apply_rollback.py:44-58`:
    a failure closing A must not leave B open, because an open connection holding a lock would
    block the *next* test in the module rather than fail this one.
    """
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
    """Start a transaction with a bounded lock wait, and return it.

    `SET LOCAL lock_timeout` is the whole detection mechanism for "this lock was not available".
    It beats the two alternatives: `FOR UPDATE NOWAIT` would put a lock modifier in the test that
    SHARED-INVARIANTS keeps out of the production statements it is mirroring, and a bare
    `asyncio.wait_for` would abandon a still-running query on a connection this module goes on to
    use. The timeout aborts server-side, deterministically, leaving the connection usable.
    """
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
        """The other half of the case above: a lock that never released would be a hang, not a gate.

        Same short `lock_timeout` on B, so "acquires immediately" is asserted rather than assumed --
        if the row were still held, this would raise instead of returning the row.
        """
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
        """Grant-then-usage against usage-then-grant: PostgreSQL aborts one of them.

        This is the rule no CHECK can express. `GrantsDB` locks the effective grants ascending by
        id and only then their usage rows, and Phases 41, 42 and 45 are each required to copy that
        order rather than derive their own -- because a path that reaches for the usage row first
        can interleave with a path that does not, and one of the two users gets a 500 for a request
        that was perfectly valid. The interleaving below is that scenario, executed:

            A holds the grant row, and reaches for the usage row.
            B holds the usage row, and reaches for the grant row.

        Neither can proceed, and neither will yield. Both reaches are issued concurrently rather
        than in sequence, because a sequential second reach would simply block forever on a
        connection that is not going anywhere. Both carry the long `lock_timeout`, so a *missed*
        deadlock detection fails this case instead of hanging the suite.

        The assertion names `DeadlockDetectedError` specifically, not a bare `Exception`: a lock
        timeout, a broken connection, and a syntax error would all satisfy "something raised", and
        exactly one of the three possibilities is the property this case exists to prove.
        """
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
        """The control, and the reason the case above is about the *order* and not about locking.

        Both transactions take grant-then-usage. The second simply waits for the first and then
        proceeds; nothing is aborted. Without this case, `test_the_reverse_order_deadlocks` is
        equally consistent with "two transactions touching these tables always deadlock", which
        would make the fixed order useless rather than load-bearing.
        """
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
                # Long enough that B is provably blocked on A's grant lock before A releases it:
                # without the pause the two could serialise by luck and the case would stop
                # exercising a wait at all.
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
