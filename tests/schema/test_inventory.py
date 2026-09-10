"""Exact-set object inventory: enums, tables, columns, index names, index keys and predicates,
foreign-key delete actions, and the absence of the legacy structures."""
import pytest

pytestmark = pytest.mark.schema

# The introspection queries, read against pg_catalog.

ENUMS = """
SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
JOIN pg_enum e      ON e.enumtypid = t.oid
WHERE n.nspname = 'core' AND t.typtype = 'e'
GROUP BY t.typname
"""

TABLES = "SELECT tablename FROM pg_tables WHERE schemaname = $1"

INDEXES = """
SELECT n.nspname AS schema,
       i.relname AS index_name,
       ix.indisunique AS is_unique,
       pg_get_expr(ix.indpred, ix.indrelid) AS predicate
FROM pg_index ix
JOIN pg_class i     ON i.oid = ix.indexrelid
JOIN pg_class c     ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('core', 'audit')
"""

# NOT t.tgisinternal is required: PostgreSQL implements every foreign key as a pair of internal triggers.
USER_TRIGGERS = """
SELECT count(*) FROM pg_trigger t
JOIN pg_class c     ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('core','audit') AND NOT t.tgisinternal
"""

FK_DELETE_ACTIONS = """
SELECT n.nspname || '.' || c.relname AS table_name,
       con.confdeltype::text AS delete_action,
       (SELECT string_agg(a.attname, ',' ORDER BY k.ord)
        FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum) AS columns
FROM pg_constraint con
JOIN pg_class c     ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE con.contype = 'f' AND n.nspname IN ('core', 'audit')
"""

VIEWS = "SELECT count(*) FROM pg_views WHERE schemaname IN ('core','audit')"
MATVIEWS = "SELECT count(*) FROM pg_matviews WHERE schemaname IN ('core','audit')"

GONE = """
SELECT
  to_regtype('core.subscription_plan')  IS NULL AS no_plan_enum,
  to_regclass('core.usage_monthly')     IS NULL AS no_usage_monthly,
  to_regclass('core.subscription_events') IS NULL AS no_sub_events,
  NOT EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='core' AND table_name='users'
                AND column_name='jwt_sub')          AS no_jwt_sub
"""

USERS_COLUMNS = """
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'core' AND table_name = 'users'
ORDER BY ordinal_position
"""

COLUMNS = r"""
SELECT n.nspname || '.' || c.relname || '.' || a.attname AS name,
       format_type(a.atttypid, a.atttypmod)
         || CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END
         || COALESCE(CASE WHEN a.attgenerated <> '' THEN ' GENERATED ' ELSE ' DEFAULT ' END
                     || btrim(regexp_replace(pg_get_expr(d.adbin, d.adrelid), '\s+', ' ', 'g')), '')
         AS spec
FROM pg_attribute a
JOIN pg_class c     ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE n.nspname IN ('core', 'audit') AND c.relkind = 'r'
  AND a.attnum > 0 AND NOT a.attisdropped
"""

INDEX_KEYS = """
SELECT i.relname AS index_name,
       CASE WHEN ix.indisunique THEN 'UNIQUE ' ELSE '' END
         || '(' || (SELECT string_agg(pg_get_indexdef(ix.indexrelid, k.ord::int, true), ', '
                                      ORDER BY k.ord)
                    FROM generate_series(1, ix.indnkeyatts) WITH ORDINALITY AS k(pos, ord))
         || ')' AS key
FROM pg_index ix
JOIN pg_class i     ON i.oid = ix.indexrelid
JOIN pg_class c     ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('core', 'audit')
"""

# pg_get_expr renders enum casts relative to search_path, so it is pinned and the expected strings stay literal.
PINNED_SEARCH_PATH = '"$user", public'

# Every expected value below was read out of pg_catalog on a live apply, not transcribed from a document.

# Labels are in enumsortorder, asserted as an ordered sequence and never as an unordered set.
EXPECTED_ENUM_LABELS = {
    "access_grant_source": [
        "subscription", "anonymous_device_grant", "registered_account_grant", "manual"
    ],
    "access_grant_status": [
        "active", "revoked", "expired"
    ],
    "auth_operation": [
        "create_user", "upgrade_anonymous_to_registered", "claim_anonymous_grant", "claim_registered_grant"
    ],
    "chat_role": [
        "human", "ai"
    ],
    "identity_provider": [
        "anonymous", "google", "apple"
    ],
    "identity_state": [
        "active", "historical"
    ],
    "native_claim_provider": [
        "ios_devicecheck", "android_play_integrity"
    ],
    "subscription_provider": [
        "apple", "google_play"
    ],
    "subscription_status": [
        "active", "grace_period", "billing_retry", "expired", "revoked"
    ],
}

EXPECTED_CORE_TABLES = {
    "access_grants", "access_tiers", "auth_challenges", "chats", "external_identities",
    "manual_grant_issuances", "messages",
    "store_purchase_tokens", "store_purchases", "subscriptions", "user_monthly_usage", "users"
}

EXPECTED_AUDIT_TABLES = {
    "subscription_events"
}

EXPECTED_CORE_INDEXES = {
    "access_grants_pkey", "access_tiers_pkey", "auth_challenges_challenge_id_key",
    "auth_challenges_pkey", "chats_pkey", "external_identities_issuer_subject_key", "external_identities_pkey",
    "external_identities_user_id_key",
    "ix_access_grants_one_active_per_user", "ix_access_grants_one_free_grant_per_user_source",
    "ix_access_grants_one_per_subscription", "ix_access_grants_subscription", "ix_access_grants_user_active",
    "ix_auth_challenges_expires_at", "ix_chats_user_id", "ix_external_identities_provider",
    "ix_external_identities_provider_account", "ix_external_identities_user_active",
    "ix_external_identities_user_id", "ix_messages_chat_id",
    "ix_store_purchase_tokens_user_id", "ix_store_purchases_provider_identity_value",
    "ix_store_purchases_purchase_user_id", "ix_subscriptions_provider_external_id", "ix_subscriptions_user_id",
    "ix_users_registered_at", "manual_grant_issuances_grant_id_key", "manual_grant_issuances_pkey", "messages_pkey",
    "store_purchase_tokens_provider_identity_value_key",
    "store_purchase_tokens_user_id_provider_key", "store_purchases_pkey",
    "store_purchases_provider_external_id_key", "subscriptions_id_user_id_key", "subscriptions_pkey",
    "subscriptions_product_entitled_subscription_id_key", "user_monthly_usage_pkey", "users_pkey"
}

EXPECTED_AUDIT_INDEXES = {
    "ix_subscription_events_subscription_id", "subscription_events_notification_uuid_key",
    "subscription_events_pkey"
}

# pg_get_expr output as rendered under PINNED_SEARCH_PATH; without the pin none of these strings match.
EXPECTED_INDEX_PREDICATES = {
    "ix_access_grants_one_active_per_user": "(status = 'active'::core.access_grant_status)",
    "ix_access_grants_one_free_grant_per_user_source": (
        "(source = ANY (ARRAY['anonymous_device_grant'::core.access_grant_source, "
        "'registered_account_grant'::core.access_grant_source]))"
    ),
    "ix_access_grants_one_per_subscription": (
        "((source = 'subscription'::core.access_grant_source) AND (subscription_id IS NOT NULL) AND "
        "(status = 'active'::core.access_grant_status))"
    ),
    "ix_access_grants_subscription": "(subscription_id IS NOT NULL)",
    "ix_external_identities_provider_account": "(provider_uid IS NOT NULL)",
    # Unique with no predicate; asserting the absence stops a later predicate silently narrowing it.
    "ix_subscriptions_provider_external_id": None,
}

EXPECTED_FK_DELETE_ACTIONS = {
    "core.chats(user_id)": "a",
    "core.messages(chat_id)": "c",
    "core.external_identities(user_id)": "r",
    "core.subscriptions(user_id)": "a",
    "core.subscriptions(tier_id)": "a",
    "core.subscriptions(restore_bound_user_id)": "a",
    "core.store_purchase_tokens(user_id)": "c",
    "core.store_purchases(purchase_user_id)": "a",
    "core.store_purchases(provider,external_id)": "a",
    "core.store_purchases(provider,resolved_token_value)": "a",
    "audit.subscription_events(subscription_id)": "a",
    "audit.subscription_events(old_tier_id)": "a",
    "audit.subscription_events(new_tier_id)": "a",
    "core.access_grants(user_id)": "c",
    "core.access_grants(tier_id)": "a",
    "core.access_grants(active_subscription_grant_subscription_id,"
    "active_subscription_grant_user_id)": "a",
    "core.access_grants(active_subscription_grant_subscription_id)": "a",
    "core.manual_grant_issuances(grant_id)": "a",
    "core.manual_grant_issuances(user_id)": "a",
    "core.user_monthly_usage(grant_id)": "c",
    "core.auth_challenges(bound_external_identity_id)": "a",
}

EXPECTED_USER_TRIGGERS = 0
EXPECTED_VIEWS = 0
EXPECTED_MATVIEWS = 0

# The target shape for core.users, in ordinal_position: seven columns, no jwt_sub and no subscription_plan.
EXPECTED_USERS_COLUMNS = [
    "id", "email", "display_name", "registered_at", "active", "created_at", "updated_at"
]

EXPECTED_COLUMNS = {
    "audit.subscription_events.created_at": "timestamp with time zone NOT NULL",
    "audit.subscription_events.event_type": "text NOT NULL",
    "audit.subscription_events.id": "uuid NOT NULL",
    "audit.subscription_events.new_tier_id": "text",
    "audit.subscription_events.notification_uuid": "text NOT NULL",
    "audit.subscription_events.old_tier_id": "text",
    "audit.subscription_events.subscription_id": "uuid NOT NULL",
    "core.access_grants.active_subscription_grant_subscription_id": (
        "uuid GENERATED CASE WHEN ((source = 'subscription'::core.access_grant_source) AND (status = "
        "'active'::core.access_grant_status)) THEN subscription_id ELSE NULL::uuid END"
    ),
    "core.access_grants.active_subscription_grant_user_id": (
        "uuid GENERATED CASE WHEN ((source = 'subscription'::core.access_grant_source) AND (status = "
        "'active'::core.access_grant_status)) THEN user_id ELSE NULL::uuid END"
    ),
    "core.access_grants.created_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.access_grants.ends_at": "timestamp with time zone",
    "core.access_grants.id": "uuid NOT NULL",
    "core.access_grants.source": "core.access_grant_source NOT NULL",
    "core.access_grants.starts_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.access_grants.status": "core.access_grant_status NOT NULL DEFAULT 'active'::core.access_grant_status",
    "core.access_grants.subscription_id": "uuid",
    "core.access_grants.tier_id": "text NOT NULL",
    "core.access_grants.updated_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.access_grants.user_id": "uuid NOT NULL",
    "core.access_tiers.created_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.access_tiers.id": "text NOT NULL",
    "core.access_tiers.monthly_credits": "integer NOT NULL",
    "core.access_tiers.updated_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.auth_challenges.bound_external_identity_id": "uuid",
    "core.auth_challenges.challenge_id": "text NOT NULL",
    "core.auth_challenges.claimed_at": "timestamp with time zone",
    "core.auth_challenges.consumed_at": "timestamp with time zone",
    "core.auth_challenges.created_at": "timestamp with time zone NOT NULL",
    "core.auth_challenges.expires_at": "timestamp with time zone NOT NULL",
    "core.auth_challenges.id": "uuid NOT NULL",
    "core.auth_challenges.operation": "core.auth_operation NOT NULL",
    "core.auth_challenges.preauth_issuer": "text",
    "core.auth_challenges.preauth_subject": "text",
    "core.chats.created_at": "timestamp with time zone NOT NULL",
    "core.chats.id": "uuid NOT NULL",
    "core.chats.lang": "text",
    "core.chats.title": "text NOT NULL",
    "core.chats.user_id": "uuid NOT NULL",
    "core.external_identities.created_at": "timestamp with time zone NOT NULL",
    "core.external_identities.free_grant_consumed_at": "timestamp with time zone",
    "core.external_identities.historical_at": "timestamp with time zone",
    "core.external_identities.id": "uuid NOT NULL",
    "core.external_identities.identity_state": "core.identity_state NOT NULL DEFAULT 'active'::core.identity_state",
    "core.external_identities.issuer": "text NOT NULL",
    "core.external_identities.native_claim_platform": "core.native_claim_provider",
    "core.external_identities.provider": "core.identity_provider NOT NULL",
    "core.external_identities.provider_uid": "text",
    "core.external_identities.subject": "text NOT NULL",
    "core.external_identities.updated_at": "timestamp with time zone NOT NULL",
    "core.external_identities.user_id": "uuid NOT NULL",
    "core.manual_grant_issuances.case_id": "text NOT NULL",
    "core.manual_grant_issuances.created_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.manual_grant_issuances.grant_id": "uuid NOT NULL",
    "core.manual_grant_issuances.operator": "text NOT NULL",
    "core.manual_grant_issuances.reason": "text NOT NULL",
    "core.manual_grant_issuances.user_id": "uuid NOT NULL",
    "core.messages.chat_id": "uuid NOT NULL",
    "core.messages.content": "jsonb NOT NULL",
    "core.messages.created_at": "timestamp with time zone NOT NULL",
    "core.messages.id": "uuid NOT NULL",
    "core.messages.role": "core.chat_role NOT NULL",
    "core.store_purchase_tokens.created_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.store_purchase_tokens.identity_value": "text NOT NULL",
    "core.store_purchase_tokens.provider": "core.subscription_provider NOT NULL",
    "core.store_purchase_tokens.user_id": "uuid NOT NULL",
    "core.store_purchases.created_at": "timestamp with time zone NOT NULL",
    "core.store_purchases.external_id": "text NOT NULL",
    "core.store_purchases.id": "uuid NOT NULL",
    "core.store_purchases.identity_value": "text NOT NULL",
    "core.store_purchases.provider": "core.subscription_provider NOT NULL",
    "core.store_purchases.purchase_user_id": "uuid",
    "core.store_purchases.resolved_token_value": "text",
    "core.store_purchases.store_original_transaction_id": "text",
    "core.store_purchases.store_transaction_id": "text",
    "core.subscriptions.created_at": "timestamp with time zone NOT NULL",
    "core.subscriptions.external_id": "text NOT NULL",
    "core.subscriptions.id": "uuid NOT NULL",
    "core.subscriptions.last_cross_account_transfer_month": "date",
    "core.subscriptions.product_entitled_subscription_id": (
        "uuid GENERATED CASE WHEN (status = ANY (ARRAY['active'::core.subscription_status, "
        "'grace_period'::core.subscription_status])) THEN id ELSE NULL::uuid END"
    ),
    "core.subscriptions.provider": "core.subscription_provider NOT NULL",
    "core.subscriptions.restore_bound_user_id": "uuid",
    "core.subscriptions.status": "core.subscription_status NOT NULL",
    "core.subscriptions.store_signed_at": "timestamp with time zone",
    "core.subscriptions.tier_id": "text NOT NULL",
    "core.subscriptions.updated_at": "timestamp with time zone NOT NULL",
    "core.subscriptions.user_id": "uuid",
    "core.user_monthly_usage.created_at": "timestamp with time zone NOT NULL",
    "core.user_monthly_usage.grant_id": "uuid NOT NULL",
    "core.user_monthly_usage.monthly_period": "text NOT NULL",
    "core.user_monthly_usage.monthly_used": "integer NOT NULL DEFAULT 0",
    "core.user_monthly_usage.updated_at": "timestamp with time zone NOT NULL",
    "core.users.active": "boolean NOT NULL DEFAULT true",
    "core.users.created_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "core.users.display_name": "text",
    "core.users.email": "text",
    "core.users.id": "uuid NOT NULL",
    "core.users.registered_at": "timestamp with time zone",
    "core.users.updated_at": "timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP",
}

EXPECTED_INDEX_KEYS = {
    "access_grants_pkey": "UNIQUE (id)",
    "access_tiers_pkey": "UNIQUE (id)",
    "auth_challenges_challenge_id_key": "UNIQUE (challenge_id)",
    "auth_challenges_pkey": "UNIQUE (id)",
    "chats_pkey": "UNIQUE (id)",
    "external_identities_issuer_subject_key": "UNIQUE (issuer, subject)",
    "external_identities_pkey": "UNIQUE (id)",
    "external_identities_user_id_key": "UNIQUE (user_id)",
    "ix_access_grants_one_active_per_user": "UNIQUE (user_id)",
    "ix_access_grants_one_free_grant_per_user_source": "UNIQUE (user_id, source)",
    "ix_access_grants_one_per_subscription": "UNIQUE (subscription_id)",
    "ix_access_grants_subscription": "(subscription_id)",
    "ix_access_grants_user_active": "(user_id, status, starts_at, ends_at)",
    "ix_auth_challenges_expires_at": "(expires_at)",
    "ix_chats_user_id": "(user_id)",
    "ix_external_identities_provider": "(provider)",
    "ix_external_identities_provider_account": "UNIQUE (issuer, provider, provider_uid)",
    "ix_external_identities_user_active": "(user_id, identity_state)",
    "ix_external_identities_user_id": "(user_id)",
    "ix_messages_chat_id": "(chat_id)",
    "ix_store_purchase_tokens_user_id": "(user_id)",
    "ix_store_purchases_provider_identity_value": "(provider, identity_value)",
    "ix_store_purchases_purchase_user_id": "(purchase_user_id)",
    "ix_subscription_events_subscription_id": "(subscription_id)",
    "ix_subscriptions_provider_external_id": "UNIQUE (provider, external_id)",
    "ix_subscriptions_user_id": "(user_id)",
    "ix_users_registered_at": "(registered_at)",
    "manual_grant_issuances_grant_id_key": "UNIQUE (grant_id)",
    "manual_grant_issuances_pkey": "UNIQUE (case_id)",
    "messages_pkey": "UNIQUE (id)",
    "store_purchase_tokens_provider_identity_value_key": "UNIQUE (provider, identity_value)",
    "store_purchase_tokens_user_id_provider_key": "UNIQUE (user_id, provider)",
    "store_purchases_pkey": "UNIQUE (id)",
    "store_purchases_provider_external_id_key": "UNIQUE (provider, external_id)",
    "subscription_events_notification_uuid_key": "UNIQUE (notification_uuid)",
    "subscription_events_pkey": "UNIQUE (id)",
    "subscriptions_id_user_id_key": "UNIQUE (id, user_id)",
    "subscriptions_pkey": "UNIQUE (id)",
    "subscriptions_product_entitled_subscription_id_key": "UNIQUE (product_entitled_subscription_id)",
    "user_monthly_usage_pkey": "UNIQUE (grant_id)",
    "users_pkey": "UNIQUE (id)",
}

ENUM_CASES = sorted(EXPECTED_ENUM_LABELS.items())
PREDICATE_CASES = sorted(EXPECTED_INDEX_PREDICATES.items())


def assert_exact_set(actual: set, expected: set, what: str) -> None:
    """Assert set equality, reporting the symmetric difference so a failure names the object."""
    unexpected = sorted(actual - expected)
    absent = sorted(expected - actual)
    assert not unexpected and not absent, (
        f"{what} is not an exact match -- "
        f"unexpected: {unexpected or 'none'}; absent: {absent or 'none'}"
    )


async def fetch_enum_labels(conn, type_name: str) -> list[str]:
    """Return one core enum type's labels in enumsortorder."""
    rows = await conn.fetch(ENUMS)
    labels = {row["typname"]: list(row["labels"]) for row in rows}
    return labels[type_name]


class TestEnumTypes:
    """Exactly the 9 declared core enum types, each with its exact labels in order."""

    async def test_enum_type_name_set_is_exact(self, conn):
        actual = {row["typname"] for row in await conn.fetch(ENUMS)}
        assert_exact_set(actual, set(EXPECTED_ENUM_LABELS), "the core enum type set")

    @pytest.mark.parametrize("type_name,expected_labels", ENUM_CASES)
    async def test_labels_match_in_declared_order(self, conn, type_name, expected_labels):
        rows = await conn.fetch(ENUMS)
        actual = {row["typname"]: list(row["labels"]) for row in rows}
        assert actual[type_name] == expected_labels, (
            f"core.{type_name} labels differ from the declared order -- "
            f"expected {expected_labels}, got {actual[type_name]}"
        )


class TestTables:
    """Exactly 12 tables in core and 1 in audit, with nothing beyond the declared set."""

    async def test_core_table_set_is_exact(self, conn):
        actual = {row["tablename"] for row in await conn.fetch(TABLES, "core")}
        assert_exact_set(actual, EXPECTED_CORE_TABLES, "the core table set")

    async def test_audit_table_set_is_exact(self, conn):
        actual = {row["tablename"] for row in await conn.fetch(TABLES, "audit")}
        assert_exact_set(actual, EXPECTED_AUDIT_TABLES, "the audit table set")


class TestIndexes:
    """Exactly the 41 captured indexes: a renamed or stray index fails this suite."""

    async def test_core_index_set_is_exact(self, conn):
        rows = await conn.fetch(INDEXES)
        actual = {r["index_name"] for r in rows if r["schema"] == "core"}
        assert_exact_set(actual, EXPECTED_CORE_INDEXES, "the core index set")

    async def test_audit_index_set_is_exact(self, conn):
        rows = await conn.fetch(INDEXES)
        actual = {r["index_name"] for r in rows if r["schema"] == "audit"}
        assert_exact_set(actual, EXPECTED_AUDIT_INDEXES, "the audit index set")


class TestIndexPredicates:
    """The six named indexes carry exactly their captured predicates, read under a pinned search_path."""

    @pytest.mark.parametrize("index_name,expected_predicate", PREDICATE_CASES)
    async def test_predicate_matches_capture(self, conn, index_name, expected_predicate):
        await conn.execute(f"SET search_path TO {PINNED_SEARCH_PATH}")
        rows = await conn.fetch(INDEXES)
        predicates = {r["index_name"]: r["predicate"] for r in rows}
        assert predicates[index_name] == expected_predicate, (
            f"{index_name} predicate differs -- expected {expected_predicate!r}, "
            f"got {predicates[index_name]!r}"
        )


async def fetch_delete_actions(conn) -> dict[str, str]:
    """Every foreign key in core and audit, keyed by its referencing table and columns."""
    rows = await conn.fetch(FK_DELETE_ACTIONS)
    return {f"{row['table_name']}({row['columns']})": row["delete_action"] for row in rows}


class TestColumns:
    """Every column of every table, with its type, its NOT NULL and its default or generation."""

    async def test_the_column_set_is_exact(self, conn):
        actual = {row["name"] for row in await conn.fetch(COLUMNS)}
        assert_exact_set(actual, set(EXPECTED_COLUMNS), "the core and audit column set")

    async def test_every_column_spec_matches_capture(self, conn):
        """The type, the nullability and the default together: a widened column keeps its name."""
        await conn.execute(f"SET search_path TO {PINNED_SEARCH_PATH}")
        actual = {row["name"]: row["spec"] for row in await conn.fetch(COLUMNS)}
        differing = {name: (spec, EXPECTED_COLUMNS.get(name))
                     for name, spec in actual.items()
                     if EXPECTED_COLUMNS.get(name) != spec}
        assert not differing, f"column specs differ (found, expected): {differing}"


class TestIndexKeys:
    """The key columns behind the index names, which the name set and the predicates never reach."""

    async def test_the_indexed_name_set_is_exact(self, conn):
        actual = {row["index_name"] for row in await conn.fetch(INDEX_KEYS)}
        assert_exact_set(actual, set(EXPECTED_INDEX_KEYS), "the indexed name set")

    async def test_every_index_key_matches_capture(self, conn):
        """`ix_access_grants_one_active_per_user` widened to (user_id, tier_id) fails here alone."""
        actual = {row["index_name"]: row["key"] for row in await conn.fetch(INDEX_KEYS)}
        differing = {name: (key, EXPECTED_INDEX_KEYS.get(name))
                     for name, key in actual.items()
                     if EXPECTED_INDEX_KEYS.get(name) != key}
        assert not differing, f"index keys differ (found, expected): {differing}"


class TestForeignKeyDeleteActions:
    """`00-schema.md` names the cascades that exist "and only these", and every fixture teardown in
    this suite deletes children before parents -- so a cascade dropped from the migration is
    invisible to every other case here."""

    async def test_the_foreign_key_set_is_exact(self, conn):
        actual = await fetch_delete_actions(conn)
        assert_exact_set(set(actual), set(EXPECTED_FK_DELETE_ACTIONS), "the foreign key set")

    async def test_every_delete_action_matches_capture(self, conn):
        actual = await fetch_delete_actions(conn)
        differing = {key: (action, EXPECTED_FK_DELETE_ACTIONS.get(key))
                     for key, action in actual.items()
                     if EXPECTED_FK_DELETE_ACTIONS.get(key) != action}
        assert not differing, f"delete actions differ (found, expected): {differing}"


class TestNoProceduralObjects:
    """The schema carries no user trigger, no view, and no materialized view."""

    async def test_no_user_triggers(self, conn):
        actual = await conn.fetchval(USER_TRIGGERS)
        assert actual == EXPECTED_USER_TRIGGERS, (
            f"expected {EXPECTED_USER_TRIGGERS} user triggers, found {actual} -- "
            "updated_at is maintained by application writes, never by a trigger (D-09)"
        )

    async def test_no_views(self, conn):
        assert await conn.fetchval(VIEWS) == EXPECTED_VIEWS

    async def test_no_materialized_views(self, conn):
        assert await conn.fetchval(MATVIEWS) == EXPECTED_MATVIEWS


class TestLegacyStructuresAreGone:
    """The v1.6 structures are absent from the schema, not merely unused by the code."""

    async def test_gone_query_negatives_all_hold(self, conn):
        row = await conn.fetchrow(GONE)
        still_present = [name for name, gone in row.items() if not gone]
        assert not still_present, f"legacy structures still present: {still_present}"

    async def test_audit_subscription_events_still_exists(self, conn):
        """The table moved to audit; it was not deleted, so its absence from core is not enough."""
        present = await conn.fetchval("SELECT to_regclass('audit.subscription_events') IS NOT NULL")
        assert present, "audit.subscription_events is missing -- the table was lost, not relocated"

    async def test_users_has_no_subscription_plan_column(self, conn):
        found = await conn.fetchval(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'core' AND table_name = 'users' AND column_name = $1",
            "subscription_plan",
        )
        assert found == 0, "core.users still carries a subscription_plan column"

    async def test_users_has_exactly_the_target_columns(self, conn):
        actual = [row["column_name"] for row in await conn.fetch(USERS_COLUMNS)]
        assert actual == EXPECTED_USERS_COLUMNS, (
            f"core.users is not the section 2 target shape -- expected {EXPECTED_USERS_COLUMNS}, got {actual}"
        )

    async def test_access_grant_source_dropped_promo(self, conn):
        """A positive consequence of the exact label list, not a separate grep."""
        labels = await fetch_enum_labels(conn, "access_grant_source")
        assert labels == EXPECTED_ENUM_LABELS["access_grant_source"], f"labels drifted: {labels}"
        assert len(labels) == 4, f"expected exactly four access_grant_source labels, got {len(labels)}"
