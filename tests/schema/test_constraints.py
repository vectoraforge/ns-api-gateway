"""SCHEMA-02 .. SCHEMA-06 -- the 00-schema.md section 10 rejection cases, exercised with real rows."""
import contextlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from schema.helpers import insert_grant, insert_usage, insert_user

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
CK_ANTI_ABUSE_GRANT_SOURCE = "access_grants_anti_abuse_grant_source_check"
FK_GRANT_SUBSCRIPTION_ENTITLED = "access_grants_active_subscription_grant_subscription_id_fkey"
# PostgreSQL truncates a generated identifier at 63 characters. This composite FK's full
# column-derived name does not fit, and "_ac" is all that survives of its second column. The name
# is still derived from explicit column names rather than from declaration order, so it is stable
# in the way P-8 cares about -- and asserting it is the only way to show that case OWN rejects on
# the ownership FK rather than on the entitlement FK above.
FK_GRANT_SUBSCRIPTION_OWNER = "access_grants_active_subscription_grant_subscription_id_ac_fkey"

ISSUER = "https://securetoken.google.com/native-speaker-test"
_ACTOR_SUBJECT_HASH = bytes(range(32))
_IDP_ACCOUNT_HASH = bytes(range(32, 64))
_DETAILS_KEYS = ("schema_version", "context", "verification", "resolved", "mutation", "failure")

# The COMMIT-time cases (LB, E1, E2, OWN) below drive the boundary with explicit SQL. The conn
# fixture has already opened a transaction, so the "BEGIN" is a documented no-op the server warns
# about; what matters is the explicit "COMMIT", because a DEFERRABLE INITIALLY DEFERRED constraint
# is only checked there. The failure aborts the transaction server-side while asyncpg still
# believes it is open, so none of those tests issues a ROLLBACK afterwards and none of them queries
# the connection again (RESEARCH P-6).

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
_INSERT_SUBSCRIPTION_WITH_GENERATED_COLUMN = (
    "INSERT INTO core.subscriptions "
    "(id, user_id, provider, external_id, tier_id, status, product_entitled_subscription_id, "
    "created_at, updated_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)
_INSERT_STORE_PURCHASE = (
    "INSERT INTO core.store_purchases "
    "(id, provider, identity_value, external_id, resolved_token_value, created_at) "
    "VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)"
)
_INSERT_CHALLENGE = (
    "INSERT INTO core.auth_challenges "
    "(id, challenge_id, operation, bound_external_identity_id, preauth_issuer, "
    "preauth_subject_hash, expires_at, claimed_at, claim_attempt_id, consumed_at, created_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP)"
)
# Two literal statements again: case A6 has to prove the DDL's details DEFAULT is what a minimal
# valid row gets, which means omitting the column rather than passing the skeleton by hand.
_INSERT_AUTH_EVENT = (
    "INSERT INTO audit.auth_events "
    "(id, challenge_row_id, operation, result, actor_issuer, actor_subject_hash, "
    "actor_subject_hash_key_version, actor_provider, details, created_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, CURRENT_TIMESTAMP)"
)
_INSERT_AUTH_EVENT_DETAILS_OMITTED = (
    "INSERT INTO audit.auth_events "
    "(id, challenge_row_id, operation, result, actor_issuer, actor_subject_hash, "
    "actor_subject_hash_key_version, actor_provider, created_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)"
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


async def _insert_challenge(
    conn: asyncpg.Connection,
    *,
    operation: str = "create_user",
    bound_external_identity_id: uuid.UUID | None = None,
    preauth_issuer: str | None = ISSUER,
    preauth_subject_hash: bytes | None = _ACTOR_SUBJECT_HASH,
    claimed_at: datetime | None = None,
    claim_attempt_id: uuid.UUID | None = None,
    consumed_at: datetime | None = None,
) -> uuid.UUID:
    """Insert one core.auth_challenges row and return its id."""
    challenge_row_id = uuid.uuid4()
    await conn.execute(
        _INSERT_CHALLENGE,
        challenge_row_id,
        f"chal_{uuid.uuid4().hex}",
        operation,
        bound_external_identity_id,
        preauth_issuer,
        preauth_subject_hash,
        datetime.now(UTC) + timedelta(seconds=300),
        claimed_at,
        claim_attempt_id,
        consumed_at,
    )
    return challenge_row_id


async def _insert_auth_event(
    conn: asyncpg.Connection,
    *,
    result: str,
    operation: str | None = None,
    actor_issuer: str | None = ISSUER,
    actor_subject_hash: bytes | None = _ACTOR_SUBJECT_HASH,
    actor_subject_hash_key_version: int | None = 1,
    actor_provider: str | None = None,
    details: dict | None = None,
) -> uuid.UUID:
    """Insert one audit.auth_events row and return its id.

    details=None omits the column entirely so the DDL's six-key DEFAULT applies; pass a dict to
    write an explicit one.
    """
    event_id = uuid.uuid4()
    common = (
        event_id,
        None,  # challenge_row_id -- deliberately bare, the schema has no FK to core.auth_challenges
        operation,
        result,
        actor_issuer,
        actor_subject_hash,
        actor_subject_hash_key_version,
        actor_provider,
    )
    if details is None:
        await conn.execute(_INSERT_AUTH_EVENT_DETAILS_OMITTED, *common)
    else:
        await conn.execute(_INSERT_AUTH_EVENT, *common, json.dumps(details))
    return event_id


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
        await insert_usage(conn, grant_id=grant_id, monthly_period="2026-08")
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            # A different monthly_period would be accepted under a composite key; it is rejected
            # here, which is what proves the key is grant_id alone.
            await insert_usage(conn, grant_id=grant_id, monthly_period="2026-09")
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


class TestAntiAbuseEvidenceConstraints:
    """SCHEMA-03 -- the four-arm anti-abuse CHECK and the "free sources only" partition."""

    async def _free_grant(self, conn, tier, source="anonymous_device_grant") -> uuid.UUID:
        user_id = await insert_user(conn)
        return await insert_grant(conn, user_id=user_id, tier_id=tier, source=source)

    async def test_grant_anti_abuse_native_ios_tuple_accepted(self, conn, tier):
        """Case V1 -- native iOS: a native_claim_provider and no hash fields at all."""
        grant_id = await self._free_grant(conn, tier)
        await _insert_anti_abuse(
            conn, grant_id=grant_id, grant_source="anonymous_device_grant", native_claim_provider="ios_devicecheck"
        )
        assert await conn.fetchval(
            "SELECT native_claim_provider::text FROM core.access_grants_anti_abuse WHERE grant_id = $1", grant_id
        ) == "ios_devicecheck"

    async def test_grant_anti_abuse_native_android_tuple_accepted(self, conn, tier):
        """Case V2 -- native Android. Ruling 9.6 keeps that arm shape-only, so no value list is asserted."""
        grant_id = await self._free_grant(conn, tier)
        await _insert_anti_abuse(
            conn,
            grant_id=grant_id,
            grant_source="anonymous_device_grant",
            native_claim_provider="android_play_integrity",
        )
        assert await conn.fetchval(
            "SELECT count(*) FROM core.access_grants_anti_abuse WHERE grant_id = $1", grant_id
        ) == 1

    async def test_grant_anti_abuse_web_anonymous_tuple_accepted(self, conn, tier):
        """Case V3 -- web anonymous: no native_claim_provider, both hash fields populated."""
        grant_id = await self._free_grant(conn, tier)
        await _insert_anti_abuse(
            conn,
            grant_id=grant_id,
            grant_source="anonymous_device_grant",
            idp_account_hash=_IDP_ACCOUNT_HASH,
            idp_account_hash_key_version=1,
        )
        assert await conn.fetchval(
            "SELECT idp_account_hash FROM core.access_grants_anti_abuse WHERE grant_id = $1", grant_id
        ) == _IDP_ACCOUNT_HASH

    async def test_grant_anti_abuse_registered_tuple_accepted(self, conn, tier):
        """Case V4 -- registered: same shape as web anonymous, on a registered_account_grant."""
        grant_id = await self._free_grant(conn, tier, source="registered_account_grant")
        await _insert_anti_abuse(
            conn,
            grant_id=grant_id,
            grant_source="registered_account_grant",
            idp_account_hash=_IDP_ACCOUNT_HASH,
            idp_account_hash_key_version=1,
        )
        assert await conn.fetchval(
            "SELECT count(*) FROM core.access_grants_anti_abuse WHERE grant_id = $1", grant_id
        ) == 1

    async def test_grant_anti_abuse_anonymous_row_without_any_evidence_rejected(self, conn, tier):
        """Case R1 -- an anonymous row with neither a native claim nor an account hash carries no evidence."""
        grant_id = await self._free_grant(conn, tier)
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Leaving every evidence column NULL is the point of this test.
            await _insert_anti_abuse(conn, grant_id=grant_id, grant_source="anonymous_device_grant")
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants_anti_abuse") == 0

    async def test_grant_anti_abuse_native_row_carrying_idp_hash_rejected(self, conn, tier):
        """Case R2 -- the native arm requires both hash fields NULL; a native row may not also carry one."""
        grant_id = await self._free_grant(conn, tier)
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Mixing the native and web arms is the point of this test.
            await _insert_anti_abuse(
                conn,
                grant_id=grant_id,
                grant_source="anonymous_device_grant",
                native_claim_provider="ios_devicecheck",
                idp_account_hash=_IDP_ACCOUNT_HASH,
                idp_account_hash_key_version=1,
            )

    async def test_grant_anti_abuse_web_anonymous_row_carrying_native_provider_rejected(self, conn, tier):
        """Case R3 -- a web-anonymous row may not also claim a native provider."""
        grant_id = await self._free_grant(conn, tier)
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Same mix as R2 read from the other side; the CHECK admits neither.
            await _insert_anti_abuse(
                conn,
                grant_id=grant_id,
                grant_source="anonymous_device_grant",
                native_claim_provider="android_play_integrity",
                idp_account_hash=_IDP_ACCOUNT_HASH,
                idp_account_hash_key_version=1,
            )

    async def test_grant_anti_abuse_registered_row_carrying_native_provider_rejected(self, conn, tier):
        """Case R4 -- the registered arm forbids a native_claim_provider outright."""
        grant_id = await self._free_grant(conn, tier, source="registered_account_grant")
        async with _rejects(conn, asyncpg.CheckViolationError):
            # A registered account never carries a native device claim; asserting one is the point.
            await _insert_anti_abuse(
                conn,
                grant_id=grant_id,
                grant_source="registered_account_grant",
                native_claim_provider="ios_devicecheck",
                idp_account_hash=_IDP_ACCOUNT_HASH,
                idp_account_hash_key_version=1,
            )

    async def test_grant_anti_abuse_row_for_subscription_backed_grant_rejected(self, conn, tier):
        """Case R5 -- a real subscription-backed grant cannot get an anti-abuse row at all."""
        user_id = await insert_user(conn)
        subscription_id = await _insert_subscription(conn, user_id=user_id, tier_id=tier, status="active")
        grant_id = await insert_grant(
            conn, user_id=user_id, tier_id=tier, source="subscription", subscription_id=subscription_id
        )
        # The real subscription and the real subscription-backed grant above are what make this test
        # mean anything: source='subscription' with a NULL subscription_id is rejected by the grant's
        # own subscription_id CHECK and would never reach the anti-abuse table at all (RESEARCH P-11).
        async with _rejects(conn, asyncpg.CheckViolationError):
            await _insert_anti_abuse(
                conn,
                grant_id=grant_id,
                grant_source="subscription",
                idp_account_hash=_IDP_ACCOUNT_HASH,
                idp_account_hash_key_version=1,
            )
        # The class only, not the name. RESEARCH Code Example 5 recorded this case as reporting
        # access_grants_anti_abuse_grant_source_check on PostgreSQL 16.2; on the PostgreSQL 17.11
        # target it reports access_grants_anti_abuse_check instead. That is not a schema defect and
        # not a weaker test -- the row is still rejected, by a constraint that subsumes the named
        # one. test_grant_anti_abuse_grant_source_check_is_subsumed below pins the reason.
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants_anti_abuse") == 0

    async def test_grant_anti_abuse_row_for_manual_grant_rejected(self, conn, tier):
        """Case R6 -- a manual grant cannot get an anti-abuse row either."""
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier, source="manual")
        async with _rejects(conn, asyncpg.CheckViolationError):
            # A manual grant is a real grant with no anti-abuse evidence; attaching one is the point.
            await _insert_anti_abuse(
                conn,
                grant_id=grant_id,
                grant_source="manual",
                idp_account_hash=_IDP_ACCOUNT_HASH,
                idp_account_hash_key_version=1,
            )
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants_anti_abuse") == 0

    async def test_grant_anti_abuse_grant_source_check_is_subsumed(self, conn):
        """Why cases R5 and R6 assert no constraint name: the named CHECK cannot be the reported one.

        Both arms of the four-arm shape CHECK already pin grant_source to the two free sources, so
        no row can satisfy that CHECK and still violate the grant_source CHECK. PostgreSQL evaluates
        a table's CHECKs in constraint-name order, and access_grants_anti_abuse_check sorts before
        access_grants_anti_abuse_grant_source_check, so the subsuming one always reports first. The
        named CHECK is redundant belt-and-braces, exactly as the migration comment says. This test
        asserts it is present and says what it says, which is what R5 and R6 can no longer assert.
        """
        definition = await conn.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'core.access_grants_anti_abuse'::regclass AND conname = $1",
            CK_ANTI_ABUSE_GRANT_SOURCE,
        )
        assert definition is not None
        assert "anonymous_device_grant" in definition
        assert "registered_account_grant" in definition
        assert "subscription" not in definition
        assert "manual" not in definition


class TestSubscriptionConstraints:
    """SCHEMA-04 -- the STORED generated column and the two deferred entitlement foreign keys."""

    async def test_subscription_explicit_write_to_generated_column_rejected(self, conn, tier):
        """Case GEN -- product_entitled_subscription_id is GENERATED ALWAYS and refuses a direct write."""
        user_id = await insert_user(conn)
        subscription_id = uuid.uuid4()
        async with _rejects(conn, asyncpg.exceptions.GeneratedAlwaysError):
            # Naming the generated column in the INSERT is the point of this test: forging
            # entitlement would mean writing this column directly.
            await conn.execute(
                _INSERT_SUBSCRIPTION_WITH_GENERATED_COLUMN,
                subscription_id,
                user_id,
                "apple",
                f"ext_{uuid.uuid4().hex[:16]}",
                tier,
                "expired",
                subscription_id,
            )
        assert await conn.fetchval("SELECT count(*) FROM core.subscriptions") == 0

    async def test_subscription_expired_rejects_active_grant_at_commit(self, conn, tier):
        """Case E1 -- an active subscription grant on an expired subscription fails the deferred FK."""
        user_id = await insert_user(conn)
        subscription_id = await _insert_subscription(conn, user_id=user_id, tier_id=tier, status="expired")
        assert await conn.fetchval(
            "SELECT product_entitled_subscription_id FROM core.subscriptions WHERE id = $1", subscription_id
        ) is None
        await conn.execute("BEGIN")
        # An entitlement-bearing grant on a subscription nobody is paying for is the point of this test.
        await insert_grant(
            conn, user_id=user_id, tier_id=tier, source="subscription", subscription_id=subscription_id
        )
        with pytest.raises(asyncpg.ForeignKeyViolationError) as exc_info:
            await conn.execute("COMMIT")  # the deferred FK fires HERE, not on the INSERT above
        assert FK_GRANT_SUBSCRIPTION_ENTITLED in str(exc_info.value)

    async def test_subscription_billing_retry_rejects_active_grant_at_commit(self, conn, tier):
        """Case E2 -- ruling 9.14 fixes the entitled set at ('active','grace_period'); billing_retry is out."""
        user_id = await insert_user(conn)
        subscription_id = await _insert_subscription(conn, user_id=user_id, tier_id=tier, status="billing_retry")
        assert await conn.fetchval(
            "SELECT product_entitled_subscription_id FROM core.subscriptions WHERE id = $1", subscription_id
        ) is None
        await conn.execute("BEGIN")
        # Not a duplicate of E1: this is the ruling most likely to be widened by a later reader who
        # reasons that a card retry should keep the subscriber served.
        await insert_grant(
            conn, user_id=user_id, tier_id=tier, source="subscription", subscription_id=subscription_id
        )
        with pytest.raises(asyncpg.ForeignKeyViolationError) as exc_info:
            await conn.execute("COMMIT")
        assert FK_GRANT_SUBSCRIPTION_ENTITLED in str(exc_info.value)

    async def test_subscription_grant_owner_mismatch_rejected_at_commit(self, conn, tier):
        """Case OWN -- a grant may not point at another user's subscription."""
        owner = await insert_user(conn)
        thief = await insert_user(conn)
        # The subscription stays entitled on purpose, so the entitlement FK is satisfied and the only
        # constraint left to reject this grant is the composite ownership FK.
        subscription_id = await _insert_subscription(conn, user_id=owner, tier_id=tier, status="active")
        await conn.execute("BEGIN")
        await insert_grant(
            conn, user_id=thief, tier_id=tier, source="subscription", subscription_id=subscription_id
        )
        with pytest.raises(asyncpg.ForeignKeyViolationError) as exc_info:
            await conn.execute("COMMIT")
        assert FK_GRANT_SUBSCRIPTION_OWNER in str(exc_info.value)

    async def test_subscription_with_null_user_id_accepted(self, conn, tier):
        """Case UNO -- an unclaimed store subscription is ingested unowned and adopted later."""
        subscription_id = await _insert_subscription(conn, user_id=None, tier_id=tier, status="active")
        assert await conn.fetchval(
            "SELECT user_id FROM core.subscriptions WHERE id = $1", subscription_id
        ) is None

    async def test_subscription_store_purchase_with_null_resolved_token_accepted(self, conn, tier):
        """Case MS -- MATCH SIMPLE lets an unattributed purchase record without a resolved token."""
        external_id = f"ext_{uuid.uuid4().hex[:16]}"
        await _insert_subscription(conn, tier_id=tier, status="active", external_id=external_id)
        purchase_id = uuid.uuid4()
        await conn.execute(
            _INSERT_STORE_PURCHASE, purchase_id, "apple", f"tok_{uuid.uuid4().hex[:16]}", external_id, None
        )
        assert await conn.fetchval(
            "SELECT resolved_token_value FROM core.store_purchases WHERE id = $1", purchase_id
        ) is None


class TestAuthChallengeConstraints:
    """SCHEMA-05 -- ruling 9.8's operation partition and the lifecycle and binding CHECKs."""

    @pytest.mark.parametrize("operation", ["restore_subscription", "sign_out_all", "sync"])
    async def test_challenge_for_a_challenge_free_operation_rejected(self, conn, operation):
        """Case R9 -- the three challenge-free operations, none of which may have a challenge row.

        Widened from restore_subscription alone when D-12/D-13 collapsed the four-arm CHECK to a
        membership test. The membership form is the one that could plausibly be written too
        loosely -- an enum-wide CHECK, or none at all, would admit all three of these -- so all
        three are asserted rather than the one the original ruling named.
        """
        async with _rejects(conn, asyncpg.CheckViolationError):
            # These operations have no challenge row, no claim step and no consumption step;
            # writing one is the point of this test.
            await _insert_challenge(conn, operation=operation)
        assert await conn.fetchval("SELECT count(*) FROM core.auth_challenges") == 0

    @pytest.mark.parametrize("operation", [
        "create_user", "upgrade_anonymous_to_registered",
        "claim_anonymous_grant", "claim_registered_grant",
    ])
    async def test_challenge_for_every_challenge_bearing_operation_accepted(self, conn, operation):
        """The other half of the partition -- all four challenge-bearing operations insert.

        `upgrade_anonymous_to_registered` is the load-bearing case: it was pinned to a
        provider-variant arm (`IN ('google','apple')`) until D-13 removed that column, so this is
        the assertion that Phase 40's rows survived the rewrite. Phase 40 must supply its own provider
        binding; that it has none *here* is the recorded handoff, not a regression.
        """
        challenge_row_id = await _insert_challenge(conn, operation=operation)
        assert await conn.fetchval(
            "SELECT count(*) FROM core.auth_challenges WHERE id = $1", challenge_row_id
        ) == 1

    async def test_challenge_claimed_without_attempt_id_rejected(self, conn):
        """The lifecycle CHECK -- a claimed row must carry its server-generated claim_attempt_id."""
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Setting claimed_at while leaving claim_attempt_id NULL is the point of this test.
            await _insert_challenge(conn, claimed_at=datetime.now(UTC), claim_attempt_id=None)

    async def test_challenge_with_both_binding_forms_rejected(self, conn):
        """The binding CHECK -- exactly one of the identity binding or the preauth pair, never both."""
        user_id = await insert_user(conn)
        identity_id = await _insert_identity(conn, user_id=user_id)
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Carrying both binding forms at once is the point of this test.
            await _insert_challenge(
                conn,
                operation="claim_anonymous_grant",
                bound_external_identity_id=identity_id,
                preauth_issuer=ISSUER,
            )

    async def test_challenge_wellformed_claimed_and_consumed_row_accepted(self, conn):
        """All three CHECKs accept a well-formed claimed-and-consumed preauth row."""
        now = datetime.now(UTC)
        challenge_row_id = await _insert_challenge(
            conn,
            operation="upgrade_anonymous_to_registered",
            claimed_at=now,
            claim_attempt_id=uuid.uuid4(),
            consumed_at=now,
        )
        assert await conn.fetchval(
            "SELECT count(*) FROM core.auth_challenges WHERE id = $1", challenge_row_id
        ) == 1


class TestAuthEventAuditConstraints:
    """SCHEMA-06 -- the all-or-nothing actor CHECK, the succeeded/operation CHECK, and the details shape."""

    async def test_audit_row_without_any_actor_fields_rejected(self, conn):
        """Case A1 -- every result other than invalid_external_jwt must be attributable."""
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Dropping the whole actor triple on an attributable result is the point of this test.
            await _insert_auth_event(
                conn,
                result="challenge_expired",
                actor_issuer=None,
                actor_subject_hash=None,
                actor_subject_hash_key_version=None,
            )
        assert await conn.fetchval("SELECT count(*) FROM audit.auth_events") == 0

    async def test_audit_invalid_external_jwt_row_carrying_actor_fields_rejected(self, conn):
        """Case A2 -- an unverifiable token yields no actor, so the row may not claim one."""
        async with _rejects(conn, asyncpg.CheckViolationError):
            # An invalid_external_jwt row was never able to identify an actor; asserting one is the point.
            await _insert_auth_event(conn, result="invalid_external_jwt")

    async def test_audit_row_with_partial_actor_triple_rejected(self, conn):
        """Case A3 -- issuer and subject hash without the key version is an unverifiable actor."""
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Omitting only the key version is the point of this test: the hash cannot be
            # re-derived later without knowing which key produced it.
            await _insert_auth_event(
                conn, result="challenge_expired", actor_subject_hash_key_version=None
            )

    async def test_audit_succeeded_row_without_operation_rejected(self, conn):
        """Case A4 -- operation is nullable for rejections, but a succeeded row must name one."""
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Leaving operation NULL on a success is the point of this test.
            await _insert_auth_event(conn, result="succeeded", operation=None)

    async def test_audit_row_with_details_missing_failure_key_rejected(self, conn):
        """Case A5 -- the details skeleton is enforced key by key."""
        partial = {key: {} for key in _DETAILS_KEYS if key != "failure"}
        partial["schema_version"] = 1
        async with _rejects(conn, asyncpg.CheckViolationError):
            # Only the failure key is dropped, so this isolates one shape CHECK instead of
            # tripping several at once.
            await _insert_auth_event(conn, result="challenge_expired", details=partial)

    async def test_audit_row_with_minimal_actor_triple_accepted(self, conn):
        """Case A6 -- the CHECKs are not simply rejecting everything: a valid minimal row is accepted."""
        event_id = await _insert_auth_event(conn, result="challenge_expired")
        row = await conn.fetchrow(
            "SELECT operation, actor_provider, details FROM audit.auth_events WHERE id = $1", event_id
        )
        assert row["operation"] is None  # nullable for a rejection result
        assert row["actor_provider"] is None  # not part of the required triple
        assert set(json.loads(row["details"])) == set(_DETAILS_KEYS)
