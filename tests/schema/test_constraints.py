"""The schema's rejection cases, exercised with real rows against a real PostgreSQL."""
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from schema.helpers import insert_grant, insert_usage, insert_user

pytestmark = pytest.mark.schema

# Only explicit or column-derived names are asserted; positional CHECK names shift when clauses are reordered.
IX_ONE_ACTIVE_PER_USER = "ix_access_grants_one_active_per_user"
IX_ONE_FREE_GRANT_PER_USER_SOURCE = "ix_access_grants_one_free_grant_per_user_source"
IX_ONE_PER_SUBSCRIPTION = "ix_access_grants_one_per_subscription"
UQ_IDENTITY_ISSUER_SUBJECT = "external_identities_issuer_subject_key"
FK_IDENTITY_USER = "external_identities_user_id_fkey"
FK_ANTI_ABUSE_REQUIRED = "access_grants_anti_abuse_required_grant_id_fkey"
PK_USER_MONTHLY_USAGE = "user_monthly_usage_pkey"
CK_ANTI_ABUSE_GRANT_SOURCE = "access_grants_anti_abuse_grant_source_check"
FK_GRANT_SUBSCRIPTION_ENTITLED = "access_grants_active_subscription_grant_subscription_id_fkey"
# Truncated at 63 characters, so "_ac" is all that survives of the second column; still column-derived.
FK_GRANT_SUBSCRIPTION_OWNER = "access_grants_active_subscription_grant_subscription_id_ac_fkey"

ISSUER = "https://securetoken.google.com/native-speaker-test"
_PREAUTH_SUBJECT = "Xy7Q1s0K2mNb3fV4"
_IDP_ACCOUNT_HASH = bytes(range(32, 64))

# Two literal statements rather than one assembled string: the identity_state default is proven by omission.
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
    "preauth_subject, expires_at, claimed_at, consumed_at, created_at) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)"
)


@contextlib.asynccontextmanager
async def _rejects(conn: asyncpg.Connection, exc_type: type[Exception]):
    """A rejected statement aborts the whole transaction, so the savepoint is what keeps a follow-up query possible."""
    # Not usable for the COMMIT-time cases: a deferred failure leaves no savepoint to return to.
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
    """Insert one core.external_identities row; provider_uid is generated so it never collides by accident."""
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
    preauth_subject: str | None = _PREAUTH_SUBJECT,
    claimed_at: datetime | None = None,
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
        preauth_subject,
        datetime.now(UTC) + timedelta(seconds=300),
        claimed_at,
        consumed_at,
    )
    return challenge_row_id


class TestExternalIdentityConstraints:
    """The (issuer, subject) reservation, the provider/provider_uid agreement, and the identity FK."""

    async def test_identity_duplicate_issuer_subject_rejected(self, conn):
        """A second identity row carrying an existing active row's (issuer, subject) is rejected."""
        first_user = await insert_user(conn)
        second_user = await insert_user(conn)
        subject = f"sub_{uuid.uuid4().hex[:16]}"
        await _insert_identity(conn, user_id=first_user, subject=subject)
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
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
        # A state predicate on the index would free the reservation; there is none, and this would catch one.
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
            await _insert_identity(conn, user_id=user_id, provider="anonymous", provider_uid="uid_not_allowed")
        assert await conn.fetchval("SELECT count(*) FROM core.external_identities") == 0

    async def test_identity_registered_with_empty_provider_uid_rejected(self, conn):
        """A google/apple identity with an empty provider_uid violates the provider agreement CHECK."""
        user_id = await insert_user(conn)
        async with _rejects(conn, asyncpg.CheckViolationError):
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
        """ON DELETE RESTRICT stops a core.users row being deleted out from under an identity."""
        user_id = await insert_user(conn)
        await _insert_identity(conn, user_id=user_id)
        async with _rejects(conn, asyncpg.ForeignKeyViolationError) as exc_info:
            await conn.execute("DELETE FROM core.users WHERE id = $1", user_id)
        assert FK_IDENTITY_USER in str(exc_info.value)
        assert await conn.fetchval("SELECT count(*) FROM core.users WHERE id = $1", user_id) == 1


class TestAccessGrantConstraints:
    """One active grant per user, the lifetime free-grant slot, and the anti-abuse lower bound."""

    async def test_grant_second_active_grant_for_user_rejected(self, conn, tier):
        """Case R7 -- a user may hold at most one status='active' grant."""
        user_id = await insert_user(conn)
        await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        async with _rejects(conn, asyncpg.UniqueViolationError) as exc_info:
            # source='manual' keeps the free-grant index out of the way, leaving only one index to violate.
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
        # The one-active-per-user slot is now free, so only the lifetime free-grant index can reject.
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
            # A second user, because a second grant for the same owner would trip the per-user index first.
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
            # A composite key would accept a different monthly_period; rejecting it proves the key is grant_id.
            await insert_usage(conn, grant_id=grant_id, monthly_period="2026-09")
        assert PK_USER_MONTHLY_USAGE in str(exc_info.value)
        assert await conn.fetchval(
            "SELECT count(*) FROM core.user_monthly_usage WHERE grant_id = $1", grant_id
        ) == 1

    async def test_grant_free_source_without_anti_abuse_row_rejected_at_commit(self, conn, tier):
        """Case LB -- the deferred FK rejects a free grant that never got its anti-abuse row."""
        user_id = await insert_user(conn)
        await conn.execute("BEGIN")
        await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        with pytest.raises(asyncpg.ForeignKeyViolationError) as exc_info:
            await conn.execute("COMMIT")  # the deferred FK fires HERE, not on the INSERT above
        assert FK_ANTI_ABUSE_REQUIRED in str(exc_info.value)
        # No ROLLBACK: the server aborted this transaction already, so rolling back would mask the exception.

    async def test_grant_free_source_with_anti_abuse_row_passes_the_deferred_check(self, conn, tier):
        """The lower bound accepts the valid pair -- so case LB above rejects for absence, not always."""
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier, source="anonymous_device_grant")
        await _insert_anti_abuse(
            conn, grant_id=grant_id, grant_source="anonymous_device_grant", native_claim_provider="ios_devicecheck"
        )
        # Checks every deferred constraint now, so the valid pair is proven without committing it.
        await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


class TestAntiAbuseEvidenceConstraints:
    """The four-arm anti-abuse CHECK and the "free sources only" partition."""

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
        """Case V2, native Android: that arm is shape-only, so no value list is asserted."""
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
            await _insert_anti_abuse(conn, grant_id=grant_id, grant_source="anonymous_device_grant")
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants_anti_abuse") == 0

    async def test_grant_anti_abuse_native_row_carrying_idp_hash_rejected(self, conn, tier):
        """Case R2 -- the native arm requires both hash fields NULL; a native row may not also carry one."""
        grant_id = await self._free_grant(conn, tier)
        async with _rejects(conn, asyncpg.CheckViolationError):
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
        # A real subscription-backed grant is needed: a NULL subscription_id never reaches the anti-abuse table.
        async with _rejects(conn, asyncpg.CheckViolationError):
            await _insert_anti_abuse(
                conn,
                grant_id=grant_id,
                grant_source="subscription",
                idp_account_hash=_IDP_ACCOUNT_HASH,
                idp_account_hash_key_version=1,
            )
        # The class only, not the name: which of the two CHECKs reports first varies by server version.
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants_anti_abuse") == 0

    async def test_grant_anti_abuse_row_for_manual_grant_rejected(self, conn, tier):
        """Case R6 -- a manual grant cannot get an anti-abuse row either."""
        user_id = await insert_user(conn)
        grant_id = await insert_grant(conn, user_id=user_id, tier_id=tier, source="manual")
        async with _rejects(conn, asyncpg.CheckViolationError):
            await _insert_anti_abuse(
                conn,
                grant_id=grant_id,
                grant_source="manual",
                idp_account_hash=_IDP_ACCOUNT_HASH,
                idp_account_hash_key_version=1,
            )
        assert await conn.fetchval("SELECT count(*) FROM core.access_grants_anti_abuse") == 0

    async def test_grant_anti_abuse_grant_source_check_is_subsumed(self, conn):
        """The grant_source CHECK is subsumed by the shape CHECK, so it can never be the reported one."""
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
    """The STORED generated column and the two deferred entitlement foreign keys."""

    async def test_subscription_explicit_write_to_generated_column_rejected(self, conn, tier):
        """Case GEN -- product_entitled_subscription_id is GENERATED ALWAYS and refuses a direct write."""
        user_id = await insert_user(conn)
        subscription_id = uuid.uuid4()
        async with _rejects(conn, asyncpg.exceptions.GeneratedAlwaysError):
            # Forging entitlement means writing this column directly.
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
        # Not a duplicate of E1: a later reader is most likely to widen this one for a card retry.
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
        # The subscription stays entitled, so the only constraint left to reject is the ownership FK.
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
    """The challenge operation partition, and the lifecycle and binding CHECKs."""

    @pytest.mark.parametrize("operation", ["restore_subscription", "sign_out_all", "sync"])
    async def test_challenge_for_a_string_outside_the_operation_type_rejected(self, conn, operation):
        """All three are asserted individually: none is a member of core.auth_operation, so none can be written."""
        # The exact class the driver raises, read off a live insert rather than guessed; a base class
        # or Exception would also pass for a connection failure and prove nothing about the type.
        async with _rejects(conn, asyncpg.exceptions.InvalidTextRepresentationError):
            await _insert_challenge(conn, operation=operation)
        assert await conn.fetchval("SELECT count(*) FROM core.auth_challenges") == 0

    @pytest.mark.parametrize("operation", [
        "create_user", "upgrade_anonymous_to_registered",
        "claim_anonymous_grant", "claim_registered_grant",
    ])
    async def test_challenge_for_every_challenge_bearing_operation_accepted(self, conn, operation):
        """The other half of the partition: all four challenge-bearing operations insert."""
        challenge_row_id = await _insert_challenge(conn, operation=operation)
        assert await conn.fetchval(
            "SELECT count(*) FROM core.auth_challenges WHERE id = $1", challenge_row_id
        ) == 1

    async def test_challenge_consumed_without_a_claim_rejected(self, conn):
        """The lifecycle CHECK -- a consumed row must have been claimed first."""
        async with _rejects(conn, asyncpg.CheckViolationError):
            await _insert_challenge(conn, claimed_at=None, consumed_at=datetime.now(UTC))

    async def test_challenge_claimed_but_not_yet_consumed_accepted(self, conn):
        """The other half of the lifecycle CHECK: the claimed-and-unconsumed state is the normal one."""
        challenge_row_id = await _insert_challenge(conn, claimed_at=datetime.now(UTC),
                                                   consumed_at=None)
        assert await conn.fetchval(
            "SELECT count(*) FROM core.auth_challenges WHERE id = $1", challenge_row_id
        ) == 1

    async def test_challenge_with_both_binding_forms_rejected(self, conn):
        """The binding CHECK -- exactly one of the identity binding or the preauth pair, never both."""
        user_id = await insert_user(conn)
        identity_id = await _insert_identity(conn, user_id=user_id)
        async with _rejects(conn, asyncpg.CheckViolationError):
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
            consumed_at=now,
        )
        assert await conn.fetchval(
            "SELECT count(*) FROM core.auth_challenges WHERE id = $1", challenge_row_id
        ) == 1
