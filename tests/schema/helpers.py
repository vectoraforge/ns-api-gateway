"""Typed seed helpers for the schema-conformance suite -- each returns the id of the row it inserted."""
import uuid

import asyncpg

# Every row value binds through an asyncpg $N parameter, and no helper commits or owns a transaction.


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
    """Insert one core.access_tiers row with a randomised id, so two tiers can coexist in one test."""
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
    """Insert one core.access_grants row; source and status bind as text against the enum columns."""
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


async def insert_subscription(
    conn: asyncpg.Connection,
    *,
    external_id: str,
    tier_id: str,
    provider: str = "apple",
    status: str = "active",
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one core.subscriptions row; provider and status bind as text against the enum columns."""
    subscription_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO core.subscriptions "
        "(id, user_id, provider, external_id, tier_id, status, created_at, updated_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        subscription_id,
        user_id,
        provider,
        external_id,
        tier_id,
        status,
    )
    return subscription_id


async def insert_store_purchase(
    conn: asyncpg.Connection,
    *,
    identity_value: str,
    external_id: str,
    provider: str = "apple",
    purchase_user_id: uuid.UUID | None = None,
    resolved_token_value: str | None = None,
) -> uuid.UUID:
    """Insert one core.store_purchases row; its created_at is NOT NULL with no default, so it is named."""
    purchase_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO core.store_purchases "
        "(id, provider, identity_value, external_id, purchase_user_id, resolved_token_value, created_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)",
        purchase_id,
        provider,
        identity_value,
        external_id,
        purchase_user_id,
        resolved_token_value,
    )
    return purchase_id


async def insert_usage(
    conn: asyncpg.Connection,
    *,
    grant_id: uuid.UUID,
    monthly_period: str = "2026-08",
    monthly_used: int = 0,
) -> None:
    """Insert one core.user_monthly_usage row; its timestamps are NOT NULL with no default, so both are named."""
    await conn.execute(
        "INSERT INTO core.user_monthly_usage "
        "(grant_id, monthly_period, monthly_used, created_at, updated_at) "
        "VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        grant_id,
        monthly_period,
        monthly_used,
    )
