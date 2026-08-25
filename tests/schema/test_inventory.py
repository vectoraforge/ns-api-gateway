"""SCHEMA-07 and SCHEMA-08 -- exact-set object inventory, index predicates, and legacy absence."""
import pytest

pytestmark = pytest.mark.schema

# --- Introspection queries (34-RESEARCH.md Code Example 3, unmodified) -------------------------

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

# NOT t.tgisinternal is not an optimisation. A correct schema has 104 rows in pg_trigger for these
# two schemas, because PostgreSQL implements every foreign key as a pair of internal trigger rows.
# Without the filter this assertion fails on a correct schema (RESEARCH P-7).
USER_TRIGGERS = """
SELECT count(*) FROM pg_trigger t
JOIN pg_class c     ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('core','audit') AND NOT t.tgisinternal
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

# pg_get_expr renders an enum cast schema-qualified or bare depending on the reader's search_path,
# so the same index has two correct-looking predicate strings (RESEARCH P-5). 34-INVENTORY-PG17.md
# section 4 records both renderings and pins this one -- the default an ordinary asyncpg connection
# already has. Pinning keeps EXPECTED_INDEX_PREDICATES literal instead of normalised after the fact.
PINNED_SEARCH_PATH = '"$user", public'

# --- Expected inventory, captured from the live PostgreSQL 17.11 apply -------------------------
# Every value below is recorded in .planning/phases/34-schema/34-INVENTORY-PG17.md and was read out
# of pg_catalog, not transcribed from 00-schema.md. Section 10 of the spec names 7 indexes while the
# applied database has 54 (25 of them auto-named constraint indexes), so an exact-set assertion
# built from the spec prose fails on its first run.

# Labels are in enumsortorder -- the order 00-schema.md section 3 declares ("every value listed, in
# this order"), asserted as an ordered sequence and never as an unordered set.
EXPECTED_ENUM_LABELS = {
    "access_grant_source": [
        "subscription", "anonymous_device_grant", "registered_account_grant", "manual"
    ],
    "access_grant_status": [
        "active", "revoked", "expired"
    ],
    "auth_operation": [
        "create_user", "upgrade_anonymous_to_registered", "claim_anonymous_grant", "claim_registered_grant",
        "restore_subscription", "sign_out_all", "sync"
    ],
    "chat_role": [
        "human", "ai"
    ],
    "gate_consumption_kind": [
        "web_anonymous_gate", "registered_account_grant"
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
    "access_grants", "access_grants_anti_abuse", "access_tiers", "auth_challenges", "chats", "external_identities",
    "manual_grant_issuances", "messages", "provider_account_gate_consumptions", "provider_accounts",
    "store_purchase_tokens", "store_purchases", "subscriptions", "user_monthly_usage", "users"
}

EXPECTED_AUDIT_TABLES = {
    "subscription_events"
}

EXPECTED_CORE_INDEXES = {
    "access_grants_anti_abuse_pkey", "access_grants_anti_abuse_registered_account_grant_id_key",
    "access_grants_id_source_key", "access_grants_pkey", "access_tiers_pkey", "auth_challenges_challenge_id_key",
    "auth_challenges_pkey", "chats_pkey", "external_identities_issuer_subject_key", "external_identities_pkey",
    "external_identities_user_id_key", "ix_access_grants_anti_abuse_idp_account_hash",
    "ix_access_grants_one_active_per_user", "ix_access_grants_one_free_grant_per_user_source",
    "ix_access_grants_one_per_subscription", "ix_access_grants_subscription", "ix_access_grants_user_active",
    "ix_auth_challenges_expires_at", "ix_chats_user_id", "ix_external_identities_provider",
    "ix_external_identities_provider_account", "ix_external_identities_user_active",
    "ix_external_identities_user_id", "ix_gate_consumptions_grant_id", "ix_messages_chat_id",
    "ix_store_purchase_tokens_user_id", "ix_store_purchases_provider_identity_value",
    "ix_store_purchases_purchase_user_id", "ix_subscriptions_provider_external_id", "ix_subscriptions_user_id",
    "ix_users_registered_at", "manual_grant_issuances_grant_id_key", "manual_grant_issuances_pkey", "messages_pkey",
    "provider_account_gate_consumptions_pkey", "provider_accounts_pkey",
    "provider_accounts_provider_provider_uid_key", "store_purchase_tokens_provider_identity_value_key",
    "store_purchase_tokens_user_id_provider_key", "store_purchases_pkey",
    "store_purchases_provider_external_id_key", "subscriptions_id_user_id_key", "subscriptions_pkey",
    "subscriptions_product_entitled_subscription_id_key", "user_monthly_usage_pkey", "users_pkey"
}

EXPECTED_AUDIT_INDEXES = {
    "ix_subscription_events_subscription_id", "subscription_events_notification_uuid_key",
    "subscription_events_pkey"
}

# pg_get_expr output as rendered under PINNED_SEARCH_PATH. Under `core, public` the enum casts lose
# their `core.` prefix and none of these strings match -- which is the whole reason for the pin.
EXPECTED_INDEX_PREDICATES = {
    "ix_access_grants_anti_abuse_idp_account_hash": "(idp_account_hash IS NOT NULL)",
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
    # Unique with no predicate. Asserting the absence is load-bearing: a predicate added
    # here later would silently narrow the uniqueness guarantee.
    "ix_subscriptions_provider_external_id": None,
}

EXPECTED_USER_TRIGGERS = 0
EXPECTED_VIEWS = 0
EXPECTED_MATVIEWS = 0

# The section 2 target shape for core.users, in ordinal_position. Seven columns: no jwt_sub and no
# subscription_plan.
EXPECTED_USERS_COLUMNS = [
    "id", "email", "display_name", "registered_at", "active", "created_at", "updated_at"
]

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
    """SCHEMA-08: exactly the 11 declared core enum types, each with its exact labels in order."""

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
    """SCHEMA-08: exactly 15 tables in core and 1 in audit -- add nothing not listed in the spec."""

    async def test_core_table_set_is_exact(self, conn):
        actual = {row["tablename"] for row in await conn.fetch(TABLES, "core")}
        assert_exact_set(actual, EXPECTED_CORE_TABLES, "the core table set")

    async def test_audit_table_set_is_exact(self, conn):
        actual = {row["tablename"] for row in await conn.fetch(TABLES, "audit")}
        assert_exact_set(actual, EXPECTED_AUDIT_TABLES, "the audit table set")


class TestIndexes:
    """SCHEMA-08: exactly the 54 captured indexes -- a renamed or stray index fails this suite."""

    async def test_core_index_set_is_exact(self, conn):
        rows = await conn.fetch(INDEXES)
        actual = {r["index_name"] for r in rows if r["schema"] == "core"}
        assert_exact_set(actual, EXPECTED_CORE_INDEXES, "the core index set")

    async def test_audit_index_set_is_exact(self, conn):
        rows = await conn.fetch(INDEXES)
        actual = {r["index_name"] for r in rows if r["schema"] == "audit"}
        assert_exact_set(actual, EXPECTED_AUDIT_INDEXES, "the audit index set")


class TestIndexPredicates:
    """D-19: the seven spec-named indexes carry exactly their captured pg_get_expr predicates.

    search_path is pinned to PINNED_SEARCH_PATH before reading, because pg_get_expr renders enum
    casts relative to it -- an unpinned assertion passes on one machine and fails on another.
    """

    @pytest.mark.parametrize("index_name,expected_predicate", PREDICATE_CASES)
    async def test_predicate_matches_capture(self, conn, index_name, expected_predicate):
        await conn.execute(f"SET search_path TO {PINNED_SEARCH_PATH}")
        rows = await conn.fetch(INDEXES)
        predicates = {r["index_name"]: r["predicate"] for r in rows}
        assert predicates[index_name] == expected_predicate, (
            f"{index_name} predicate differs -- expected {expected_predicate!r}, "
            f"got {predicates[index_name]!r}"
        )


class TestNoProceduralObjects:
    """D-09 and D-18: the schema carries no user trigger, no view, and no materialized view."""

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
    """SCHEMA-07: the v1.6 structures are absent from the schema, not merely unused by the code."""

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
        """Ruling 9.1 -- a positive consequence of the exact label list, not a separate grep."""
        labels = await fetch_enum_labels(conn, "access_grant_source")
        assert labels == EXPECTED_ENUM_LABELS["access_grant_source"], f"labels drifted: {labels}"
        assert len(labels) == 4, f"expected exactly four access_grant_source labels, got {len(labels)}"
