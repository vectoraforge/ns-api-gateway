"""SCHEMA-02 .. SCHEMA-06 -- the 00-schema.md section 10 rejection cases, exercised with real rows."""
import contextlib
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

from schema.helpers import insert_grant, insert_user

pytestmark = pytest.mark.schema

# Names asserted below were read out of a live applied schema rather than copied from the DDL by
# eye, because PostgreSQL truncates generated identifiers at 63 characters. Only names that are
# explicit in the migration, or derived from an explicit column name, appear here. The
# auto-generated positional CHECK names are deliberately never asserted: they shift when two CHECK
# clauses are reordered even though the schema is semantically unchanged (RESEARCH P-8). Those
# cases assert the exception class only.
IX_ONE_ACTIVE_PER_USER = "ix_access_grants_one_active_per_user"
IX_ONE_FREE_GRANT_PER_USER_SOURCE = "ix_access_grants_one_free_grant_per_user_source"
IX_ONE_PER_SUBSCRIPTION = "ix_access_grants_one_per_subscription"
UQ_IDENTITY_ISSUER_SUBJECT = "external_identities_issuer_subject_key"
FK_IDENTITY_USER = "external_identities_user_id_fkey"
FK_ANTI_ABUSE_REQUIRED = "access_grants_anti_abuse_required_grant_id_fkey"
PK_USER_MONTHLY_USAGE = "user_monthly_usage_pkey"

ISSUER = "https://securetoken.google.com/native-speaker-test"

# Two literal statements rather than one assembled string: the identity_state default has to be
# proven by omitting the column, and no f-string is allowed to build SQL text in this module.
_INSERT_IDENTITY = (
    "INSERT INTO core.external_identities "
    "(id, user_id, issuer, subject, provider, provider_uid, identity_state, historical_at, "
    "created_at, updated_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)
_INSERT_IDENTITY_STATE_OMITTED = (
    "INSERT INTO core.external_identities "
    "(id, user_id, issuer, subject, provider, provider_uid, created_at, updated_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)
_INSERT_SUBSCRIPTION = (
    "INSERT INTO core.subscriptions "
    "(id, user_id, provider, external_id, tier_id, status, created_at, updated_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)
_INSERT_ANTI_ABUSE = (
    "INSERT INTO core.access_grants_anti_abuse "
    "(grant_id, grant_source, native_claim_provider, idp_account_hash, "
    "idp_account_hash_key_version, created_at) "
    "VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)"
)
_INSERT_USAGE = (
    "INSERT INTO core.user_monthly_usage "
    "(grant_id, monthly_period, monthly_used, created_at, updated_at) "
    "VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)


@contextlib.asynccontextmanager
async def _rejects(conn: asyncpg.Connection, exc_type: type[Exception]):
    """Assert the wrapped statement is rejected with exc_type, leaving the transaction usable.

    A rejected statement aborts the entire PostgreSQL transaction, so a bare pytest.raises leaves
    the connection unable to answer the follow-up queries these tests use to show what did and did
    not land. The savepoint confines the failure to the one statement. It is emphatically NOT what
    proves the rejection: the exception class, and the constraint or index name where that name is
    stable, are. Not usable for the COMMIT-time cases -- a deferred failure ends the transaction
    outright and there is no savepoint left to return to (RESEARCH P-6).
    """
    await conn.execute("SAVEPOINT rejected_statement")
    with pytest.raises(exc_type) as exc_info:
        yield exc_info
    await conn.execute("ROLLBACK TO SAVEPOINT rejected_statement")


async def _insert_identity(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    issuer: str = ISSUER,
    subject: str | None = None,
    provider: str = "google",
    provider_uid: str | None = None,
    identity_state: str | None = None,
) -> uuid.UUID:
    """Insert one core.external_identities row and return its id.

    provider_uid is generated for a non-anonymous provider when the caller leaves it unset, so the
    partial unique index on (issuer, provider, provider_uid) never collides by accident and a
    duplicate-(issuer, subject) test can only be rejected by the reservation it names.
    """
    identity_id = uuid.uuid4()
    if provider != "anonymous" and provider_uid is None:
        provider_uid = f"uid_{uuid.uuid4().hex[:16]}"
    if subject is None:
        subject = f"sub_{uuid.uuid4().hex[:16]}"
    if identity_state is None:
        await conn.execute(
            _INSERT_IDENTITY_STATE_OMITTED, identity_id, user_id, issuer, subject, provider, provider_uid
        )
        return identity_id
    historical_at = datetime.now(UTC) if identity_state == "historical" else None
    await conn.execute(
        _INSERT_IDENTITY,
        identity_id,
        user_id,
        issuer,
        subject,
        provider,
        provider_uid,
        identity_state,
        historical_at,
    )
    return identity_id


async def _insert_subscription(
    conn: asyncpg.Connection,
    *,
    tier_id: str,
    user_id: uuid.UUID | None = None,
    status: str = "active",
    provider: str = "apple",
    external_id: str | None = None,
) -> uuid.UUID:
    """Insert one core.subscriptions row and return its id."""
    subscription_id = uuid.uuid4()
    if external_id is None:
        external_id = f"ext_{uuid.uuid4().hex[:16]}"
    await conn.execute(
        _INSERT_SUBSCRIPTION, subscription_id, user_id, provider, external_id, tier_id, status
    )
    return subscription_id


async def _insert_anti_abuse(
    conn: asyncpg.Connection,
    *,
    grant_id: uuid.UUID,
    grant_source: str,
    native_claim_provider: str | None = None,
    idp_account_hash: bytes | None = None,
    idp_account_hash_key_version: int | None = None,
) -> None:
    """Insert one core.access_grants_anti_abuse row."""
    await conn.execute(
        _INSERT_ANTI_ABUSE,
        grant_id,
        grant_source,
        native_claim_provider,
        idp_account_hash,
        idp_account_hash_key_version,
    )


class TestExternalIdentityConstraints:
    """SCHEMA-02 -- the (issuer, subject) reservation, the provider/provider_uid agreement, and D-16."""

    async def test_identity_duplicate_issuer_subject_rejected(self, conn):
        """A second identity row carrying an existing active row's (issuer, subject) is rejected."""
        first_user = await insert_user(conn)
        second_user = await insert_user(conn)
        subject = f"sub_{uuid.uuid4().hex[:16]}"
        await _insert_identity(conn, user_id=first_user, subject=subject)
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            # Reusing the existing row's (issuer, subject) is the point of this test.
            await _insert_identity(conn, user_id=second_user, subject=subject)
        assert UQ_IDENTITY_ISSUER_SUBJECT in str(exc_info.value)
        assert await conn.fetchval(
            "SELECT count(*) FROM core.external_identities WHERE issuer = $1 AND subject = $2",
            ISSUER,
            subject,
        ) == 1

    async def test_identity_duplicate_issuer_subject_rejected_when_existing_is_historical(self, conn):
        """The (issuer, subject) reservation survives retirement -- section 8's re-registration rule."""
        first_user = await insert_user(conn)
        second_user = await insert_user(conn)
        subject = f"sub_{uuid.uuid4().hex[:16]}"
        await _insert_identity(conn, user_id=first_user, subject=subject, identity_state="historical")
        # The reservation would be freed by a state predicate on the index; there is none, and this
        # test is what would catch one being added.
        assert await conn.fetchval(
            "SELECT identity_state::text FROM core.external_identities WHERE subject = $1", subject
        ) == "historical"
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            await _insert_identity(conn, user_id=second_user, subject=subject)
        assert UQ_IDENTITY_ISSUER_SUBJECT in str(exc_info.value)

    async def test_identity_anonymous_with_provider_uid_rejected(self, conn):
        """An anonymous identity carrying a provider_uid violates the provider agreement CHECK."""
        user_id = await insert_user(conn)
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Giving an anonymous row a provider_uid is the point of this test; ruling 9.2 forbids
            # inventing any sentinel provider_uid for an anonymous identity.
            await _insert_identity(conn, user_id=user_id, provider="anonymous", provider_uid="uid_not_allowed")
        assert await conn.fetchval("SELECT count(*) FROM core.external_identities") == 0

    async def test_identity_registered_with_empty_provider_uid_rejected(self, conn):
        """A google/apple identity with an empty provider_uid violates the provider agreement CHECK."""
        user_id = await insert_user(conn)
        async with _rejects(conn, asyncpg.CheckViolationError):
            # The empty string, not NULL, is the point of this test: the CHECK spells out both.
            await _insert_identity(conn, user_id=user_id, provider="google", provider_uid="")
        assert await conn.fetchval("SELECT count(*) FROM core.external_identities") == 0

    async def test_identity_state_defaults_to_active(self, conn):
        """identity_state defaults to 'active' when the INSERT omits the column."""
        user_id = await insert_user(conn)
        identity_id = await _insert_identity(conn, user_id=user_id)
        assert await conn.fetchval(
            "SELECT identity_state::text FROM core.external_identities WHERE id = $1", identity_id
        ) == "active"

    async def test_identity_row_blocks_deleting_its_user(self, conn):
        """D-16 -- ON DELETE RESTRICT stops a core.users row being deleted out from under an identity."""
        user_id = await insert_user(conn)
        await _insert_identity(conn, user_id=user_id)
        async with _rejects(conn, asyncpg.ForeignKeyViolationError) as exc_info:
            # Deleting a user that still has an identity row is the point of this test.
            await conn.execute("DELETE FROM core.users WHERE id = $1", user_id)
        assert FK_IDENTITY_USER in str(exc_info.value)
        assert await conn.fetchval("SELECT count(*) FROM core.users WHERE id = $1", user_id) == 1


class TestAccessGrantConstraints:
    """SCHEMA-03 -- one active grant per user, the lifetime free-grant slot, and the anti-abuse lower bound."""

    async def test_grant_second_active_grant_for_user_rejected(self, conn, tier):
        """Case R7 -- a user may hold at most one status='active' grant."""
        user_id = await insert_user(conn)
        await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            # source='manual' keeps the lifetime free-grant index out of the way, so the only index
            # this second active grant can violate is the one-active-per-user index.
            await insert_grant(conn, user_id=user_id, tier_id=tier, source="manual")
        assert IX_ONE_ACTIVE_PER_USER in str(exc_info.value)
        assert await conn.fetchval(
            "SELECT count(*) FROM core.access_grants WHERE user_id = $1", user_id
        ) == 1

    async def test_grant_second_free_grant_same_source_rejected_after_first_expired(self, conn, tier):
        """Case R8 -- the lifetime free-grant slot carries no status predicate, so expiry never reopens it."""
        user_id = await insert_user(conn)
        first = await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        await conn.execute("UPDATE core.access_grants SET status = 'expired' WHERE id = $1", first)
        # Without this the test would only re-prove R7. The one-active-per-user slot is now free;
        # the only index left that can reject the second grant is the lifetime free-grant index.
        assert await conn.fetchval(
            "SELECT status::text FROM core.access_grants WHERE id = $1", first
        ) == "expired"
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        assert IX_ONE_FREE_GRANT_PER_USER_SOURCE in str(exc_info.value)

    async def test_grant_two_active_grants_on_one_subscription_rejected(self, conn, tier):
        """Case SUB -- at most one active grant may point at a given subscription."""
        owner = await insert_user(conn)
        other = await insert_user(conn)
        subscription_id = await _insert_subscription(conn, user_id=owner, tier_id=tier, status="active")
        await insert_grant(
            conn, user_id=owner, tier_id=tier, source="subscription", subscription_id=subscription_id
        )
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            # A second user is used deliberately: a second grant for the same owner would trip the
            # one-active-per-user index first and never reach the per-subscription index.
            await insert_grant(
                conn, user_id=other, tier_id=tier, source="subscription", subscription_id=subscription_id
            )
        assert IX_ONE_PER_SUBSCRIPTION in str(exc_info.value)

    async def test_grant_monthly_usage_is_keyed_by_grant_alone(self, conn, tier):
        """core.user_monthly_usage's primary key is grant_id alone -- not (grant_id, monthly_period)."""
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier, source="manual")
        await conn.execute(_INSERT_USAGE, grant_id, "2026-08", 0)
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            # A different monthly_period would be accepted under a composite key; it is rejected
            # here, which is what proves the key is grant_id alone.
            await conn.execute(_INSERT_USAGE, grant_id, "2026-09", 0)
        assert PK_USER_MONTHLY_USAGE in str(exc_info.value)
        assert await conn.fetchval(
            "SELECT count(*) FROM core.user_monthly_usage WHERE grant_id = $1", grant_id
        ) == 1

    async def test_grant_free_source_without_anti_abuse_row_rejected_at_commit(self, conn, tier):
        """Case LB -- the deferred FK rejects a free grant that never got its anti-abuse row."""
        user_id = await insert_user(conn)
        await conn.execute("BEGIN")
        # Omitting the core.access_grants_anti_abuse row is the point of this test.
        await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        with pytest.raises(asyncpg.ForeignKeyViolationError) as exc_info:
            await conn.execute("COMMIT")  # the deferred FK fires HERE, not on the INSERT above
        assert FK_ANTI_ABUSE_REQUIRED in str(exc_info.value)
        # No ROLLBACK: the server already aborted this transaction, and asyncpg's Transaction object
        # does not know it, so rolling back would raise a second exception masking this one (P-6).

    async def test_grant_free_source_with_anti_abuse_row_passes_the_deferred_check(self, conn, tier):
        """The lower bound accepts the valid pair -- so case LB above rejects for absence, not always."""
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        await _insert_anti_abuse(
            conn, grant_id=grant_id, grant_source="anonymous_device_grant", native_claim_provider="ios_devicecheck"
        )
        # Forces every deferred constraint to be checked now, inside the per-test transaction, so the
        # valid pair is proven without committing it and without breaking per-test rollback.
        await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
