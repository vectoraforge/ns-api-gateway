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


async def insert_usage(
    conn: asyncpg.Connection,
    *,
    grant_id: uuid.UUID,
    monthly_period: str = "2026-08",
    monthly_used: int = 0,
) -> None:
    """Insert one core.user_monthly_usage row. Returns nothing -- grant_id is already the key.

    created_at and updated_at are named explicitly because this is the one table in the schema
    whose timestamps are NOT NULL with no DB DEFAULT; omitting them is a NOT NULL violation.
    """
    await conn.execute(
        "INSERT INTO core.user_monthly_usage "
        "(grant_id, monthly_period, monthly_used, created_at, updated_at) "
        "VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        grant_id,
        monthly_period,
        monthly_used,
    )
