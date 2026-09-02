"""The registration pairing, scanned over real rows: no row sits in the half-upgraded third state."""
import contextlib
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

pytestmark = pytest.mark.schema

ISSUER = "https://securetoken.google.com/native-speaker-test"

_INSERT_USER = "INSERT INTO core.users (id, registered_at) VALUES ($1, $2)"
_INSERT_IDENTITY = (
    "INSERT INTO core.external_identities "
    "(id, user_id, issuer, subject, provider, provider_uid, created_at, updated_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)

# The pairing spans two tables, so no CHECK can state it; these two queries are how it is observed instead.
_REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY = (
    "SELECT count(*) FROM core.users u "
    "JOIN core.external_identities i ON i.user_id = u.id "
    "WHERE u.registered_at IS NOT NULL AND i.provider = 'anonymous'"
)
_REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER = (
    "SELECT count(*) FROM core.external_identities i "
    "JOIN core.users u ON u.id = i.user_id "
    "WHERE i.provider <> 'anonymous' AND u.registered_at IS NULL"
)


@contextlib.asynccontextmanager
async def _rolled_back(conn: asyncpg.Connection):
    """The offending row is accepted by the database, so a control has to undo it explicitly."""
    await conn.execute("SAVEPOINT offending_row")
    try:
        yield
    finally:
        await conn.execute("ROLLBACK TO SAVEPOINT offending_row")


async def _insert_user(conn: asyncpg.Connection, *, registered_at: datetime | None) -> uuid.UUID:
    """Insert one core.users row, carrying a registration timestamp or not; return its id."""
    user_id = uuid.uuid4()
    await conn.execute(_INSERT_USER, user_id, registered_at)
    return user_id


async def _insert_identity(conn: asyncpg.Connection, *, user_id: uuid.UUID, provider: str) -> uuid.UUID:
    """Insert one core.external_identities row; subject and provider_uid are generated so neither collides."""
    identity_id = uuid.uuid4()
    # The table's CHECK ties the two together: provider_uid is NULL exactly for anonymous.
    provider_uid = None if provider == "anonymous" else f"uid_{uuid.uuid4().hex[:16]}"
    await conn.execute(_INSERT_IDENTITY, identity_id, user_id, ISSUER,
                       f"sub_{uuid.uuid4().hex[:16]}", provider, provider_uid)
    return identity_id


class TestTheRegistrationPairing:
    """Neither half of the pairing stands without the other, and neither scan may pass vacuously."""

    async def test_no_registered_user_carries_an_anonymous_identity(self, conn):
        """One half of the third state: a timestamp set while the identity row still says anonymous."""
        assert await conn.fetchval(_REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY) == 0

    async def test_the_first_scan_counts_a_deliberately_offending_row(self, conn):
        """The control: the database accepts the third state, so the scan above must be able to see it."""
        async with _rolled_back(conn):
            user_id = await _insert_user(conn, registered_at=datetime.now(UTC))
            await _insert_identity(conn, user_id=user_id, provider="anonymous")
            assert await conn.fetchval(_REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY) == 1
        assert await conn.fetchval(_REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY) == 0

    async def test_no_registered_identity_belongs_to_a_user_without_a_timestamp(self, conn):
        """The other half: a google/apple identity row whose user was never marked registered."""
        assert await conn.fetchval(_REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER) == 0

    async def test_the_second_scan_counts_a_deliberately_offending_row(self, conn):
        """The control for the other direction, inserted, counted, and rolled back to the savepoint."""
        async with _rolled_back(conn):
            user_id = await _insert_user(conn, registered_at=None)
            await _insert_identity(conn, user_id=user_id, provider="google")
            assert await conn.fetchval(_REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER) == 1
        assert await conn.fetchval(_REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER) == 0
