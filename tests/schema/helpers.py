"""Typed seed helpers for the schema-conformance suite -- each returns the id of the row it inserted."""
import uuid

import asyncpg

# Every row value binds through an asyncpg $N positional parameter (T-34-03-01). No helper in this
# module builds row data into SQL text, and no helper commits -- the per-test transaction in
# conftest.py owns the transaction boundary so each test rolls back cleanly (D-15).


async def insert_user(
    conn: asyncpg.Connection,
    *,
    email: str | None = None,
    display_name: str | None = None,
    active: bool = True,
) -> uuid.UUID:
    """Insert one core.users row and return its id."""
    user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO core.users (id, email, display_name, active) VALUES ($1, $2, $3, $4)",
        user_id,
        email,
        display_name,
        active,
    )
    return user_id


async def insert_tier(conn: asyncpg.Connection, *, monthly_credits: int = 100) -> str:
    """Insert one core.access_tiers row and return its id.

    The id is randomised rather than fixed so two tiers can coexist inside a single test
    without colliding on the TEXT primary key.
    """
    tier_id = f"tier_{uuid.uuid4().hex[:12]}"
    await conn.execute(
        "INSERT INTO core.access_tiers (id, monthly_credits) VALUES ($1, $2)",
        tier_id,
        monthly_credits,
    )
    return tier_id


async def insert_grant(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    tier_id: str,
    source: str = "anonymous_device_grant",
    status: str = "active",
    subscription_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one core.access_grants row and return its id.

    source and status bind as text against the core.access_grant_source and
    core.access_grant_status enum columns; asyncpg's enum codec accepts the label string.
    """
    grant_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO core.access_grants (id, user_id, tier_id, source, status, subscription_id) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        grant_id,
        user_id,
        tier_id,
        source,
        status,
        subscription_id,
    )
    return grant_id
