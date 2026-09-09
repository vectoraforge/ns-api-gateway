"""The registration pairing, scanned over real rows: no row sits in the half-upgraded third state."""
import contextlib
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

from nativespeaker.api.tables.identities import IdentityProvider

# The production completion and its harness, so the pairing is scanned over rows the application
# wrote rather than over rows this file invented. The harness is aliased because pytest registers
# an imported fixture under the name it is bound to here.
from schema.test_create_atomicity import harness as creation_harness  # noqa: F401
from schema.test_create_atomicity import run_creation, scalar

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

# Both scans alias the identity table as `i`, so one suffix keys either of them to a single issuer.
# The scoped form is what a case owning its rows asks; the bare form is the whole-database probe.
_FOR_ONE_ISSUER = " AND i.issuer = :issuer"

_IDENTITIES_OF_ONE_ISSUER = (
    "SELECT count(*) FROM core.external_identities i WHERE i.issuer = :issuer"
)

# The same two, in asyncpg's positional form: the `conn` fixture is a raw connection and the
# `:issuer` spelling above is SQLAlchemy's, which `scalar` binds for the production-writer class.
_FOR_ONE_ISSUER_POSITIONAL = " AND i.issuer = $1"
_IDENTITIES_OF_ONE_ISSUER_POSITIONAL = (
    "SELECT count(*) FROM core.external_identities i WHERE i.issuer = $1"
)


def _an_issuer() -> str:
    """An issuer no other case and no other module writes under, so a scan keyed to it answers for
    the rows this case seeded and for nothing else."""
    return f"{ISSUER}/scan-{uuid.uuid4().hex[:8]}"


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


async def _insert_identity(conn: asyncpg.Connection, *, user_id: uuid.UUID, provider: str,
                           issuer: str = ISSUER) -> uuid.UUID:
    """Insert one core.external_identities row; subject and provider_uid are generated so neither collides."""
    identity_id = uuid.uuid4()
    # The table's CHECK ties the two together: provider_uid is NULL exactly for anonymous.
    provider_uid = None if provider == "anonymous" else f"uid_{uuid.uuid4().hex[:16]}"
    await conn.execute(_INSERT_IDENTITY, identity_id, user_id, issuer,
                       f"sub_{uuid.uuid4().hex[:16]}", provider, provider_uid)
    return identity_id


class TestTheRegistrationPairing:
    """Neither half of the pairing stands without the other. Each case seeds a conforming pair under
    an issuer of its own and scans that issuer alone: sibling modules COMMIT into this shared
    scratch database, so an unscoped scan answers for their rows and for collection order."""

    async def test_no_registered_user_carries_an_anonymous_identity(self, conn):
        """One half of the third state: a timestamp set while the identity row still says anonymous."""
        issuer = _an_issuer()
        user_id = await _insert_user(conn, registered_at=datetime.now(UTC))
        await _insert_identity(conn, user_id=user_id, provider="google", issuer=issuer)
        # The premise: a conforming pair of this issuer exists, so the zero below is conformance
        # and never an empty scope.
        assert await conn.fetchval(_IDENTITIES_OF_ONE_ISSUER_POSITIONAL, issuer) == 1

        assert await conn.fetchval(
            _REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY + _FOR_ONE_ISSUER_POSITIONAL, issuer) == 0

    async def test_the_first_scan_counts_a_deliberately_offending_row(self, conn):
        """The control: the database accepts the third state, so the scan above must be able to see it."""
        issuer = _an_issuer()
        scan = _REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY + _FOR_ONE_ISSUER_POSITIONAL
        async with _rolled_back(conn):
            user_id = await _insert_user(conn, registered_at=datetime.now(UTC))
            await _insert_identity(conn, user_id=user_id, provider="anonymous", issuer=issuer)
            assert await conn.fetchval(scan, issuer) == 1
        assert await conn.fetchval(scan, issuer) == 0

    async def test_no_registered_identity_belongs_to_a_user_without_a_timestamp(self, conn):
        """The other half: a google/apple identity row whose user was never marked registered."""
        issuer = _an_issuer()
        user_id = await _insert_user(conn, registered_at=datetime.now(UTC))
        await _insert_identity(conn, user_id=user_id, provider="google", issuer=issuer)
        # The same premise as the first half: this scan has a row of its own to answer for.
        assert await conn.fetchval(_IDENTITIES_OF_ONE_ISSUER_POSITIONAL, issuer) == 1

        assert await conn.fetchval(
            _REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER + _FOR_ONE_ISSUER_POSITIONAL, issuer) == 0

    async def test_the_second_scan_counts_a_deliberately_offending_row(self, conn):
        """The control for the other direction, inserted, counted, and rolled back to the savepoint."""
        issuer = _an_issuer()
        scan = _REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER + _FOR_ONE_ISSUER_POSITIONAL
        async with _rolled_back(conn):
            user_id = await _insert_user(conn, registered_at=None)
            await _insert_identity(conn, user_id=user_id, provider="google", issuer=issuer)
            assert await conn.fetchval(scan, issuer) == 1
        assert await conn.fetchval(scan, issuer) == 0


class TestTheProductionWriterLeavesNeitherHalf:
    """The pairing over rows `AuthService.complete` committed, which is the only writer that can
    reach the third state: it sets `registered_at` and the identity's provider in one transaction."""

    # noqa F811: the parameter is the imported fixture's request, not a second definition of it.
    async def test_a_created_registered_account_satisfies_both_halves(self, creation_harness):  # noqa: F811
        subject = f"pairing-{uuid.uuid4().hex[:8]}"

        result, _, _ = await run_creation(creation_harness, subject=subject,
                                          provider=IdentityProvider.google,
                                          provider_uid=f"uid_{uuid.uuid4().hex[:16]}")

        # The premise: the completion committed an account, so the two scans below have a row to
        # scan. Without it this case would pass as vacuously as an empty table does.
        assert result is IdentityProvider.google
        assert await scalar(creation_harness, _IDENTITIES_OF_ONE_ISSUER,
                            {"issuer": creation_harness.issuer}) == 1
        # Keyed to this case's own issuer: a whole-table count would answer for every other file's
        # leftovers as well, and could neither fail for this writer nor pass for it.
        assert await scalar(creation_harness, _REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY + _FOR_ONE_ISSUER,
                            {"issuer": creation_harness.issuer}) == 0
        assert await scalar(creation_harness,
                            _REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER + _FOR_ONE_ISSUER,
                            {"issuer": creation_harness.issuer}) == 0
