"""Conformance of the shipped migration against the declarative database schema.

`tests/unit/data/schema_reference_ddl.sql` is the declarative schema fence of
`specs/auth-refactor/06-schema-reference.md`, copied verbatim. The migration under test must
apply exactly that DDL, and the structural expectations below — transcribed by hand from the
specification, not from either file — pin the facts `core.users` depends on.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION = MIGRATIONS / "20260816_01_auth-refactor-schema.sql"
REFERENCE = Path(__file__).resolve().parent / "data" / "schema_reference_ddl.sql"

DDL_TAG = "-- [impl->req~schema-ddl-as-written~1]"
ROLLBACK_MARKER = "-- migrate: rollback"
TAG_PREFIX = "-- [impl->"


# --- Reading the migration ---------------------------------------------------------------------

def declarative_section(migration: str) -> str:
    """The part of the apply section that is the declarative schema: everything after the
    umbrella coverage tag, with the coverage tag lines themselves removed."""
    body = migration.split(DDL_TAG, 1)[1].split(ROLLBACK_MARKER, 1)[0]
    kept = [line for line in body.splitlines(keepends=True)
            if not line.strip().startswith(TAG_PREFIX)]
    return "".join(kept).strip("\n") + "\n"


@dataclass(frozen=True)
class Table:
    columns: dict[str, str]
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class Schema:
    enums: dict[str, tuple[str, ...]]
    tables: dict[str, Table]
    indexes: dict[str, str]
    alters: tuple[str, ...]


def _statements(sql: str) -> list[str]:
    stripped = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [statement.strip() for statement in stripped.split(";") if statement.strip()]


def _split_top_level(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [" ".join(part.split()) for part in parts if part.strip()]


CONSTRAINT_STARTS = ("CHECK", "UNIQUE", "PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT")


def parse(sql: str) -> Schema:
    """The schema a DDL script declares: enum types, tables, indexes and table alterations."""
    enums: dict[str, tuple[str, ...]] = {}
    tables: dict[str, Table] = {}
    indexes: dict[str, str] = {}
    alters: list[str] = []
    for statement in _statements(sql):
        flat = " ".join(statement.split())
        if flat.startswith("CREATE TYPE"):
            enums[flat.split()[2]] = tuple(re.findall(r"'([^']*)'", flat))
        elif flat.startswith("CREATE TABLE"):
            body = statement[statement.index("(") + 1:statement.rindex(")")]
            columns: dict[str, str] = {}
            constraints: list[str] = []
            for part in _split_top_level(body):
                if part.upper().startswith(CONSTRAINT_STARTS):
                    constraints.append(part)
                else:
                    name, _, definition = part.partition(" ")
                    columns[name] = definition
            tables[flat.split()[2]] = Table(columns, tuple(constraints))
        elif flat.startswith("CREATE INDEX") or flat.startswith("CREATE UNIQUE INDEX"):
            match = re.match(r"CREATE (?:UNIQUE )?INDEX (\S+) ON ", flat)
            assert match is not None, flat
            indexes[match.group(1)] = flat
        elif flat.startswith("ALTER TABLE"):
            alters.append(flat)
    return Schema(enums, tables, indexes, tuple(alters))


@pytest.fixture(scope="module")
def applied() -> Schema:
    return parse(declarative_section(MIGRATION.read_text()))


# --- The umbrella: the migration applies the DDL as written ------------------------------------

# [utest->req~schema-ddl-as-written~1]
def test_the_migration_applies_the_declarative_schema_verbatim():
    assert declarative_section(MIGRATION.read_text()) == REFERENCE.read_text()


# [utest->req~schema-ddl-as-written~1]
def test_the_migration_is_a_pogo_migration_that_follows_the_initial_release():
    text = MIGRATION.read_text()
    assert "-- depends: 20260322_01_initial-release" in text
    assert "-- migrate: apply" in text
    assert ROLLBACK_MARKER in text
    assert MIGRATION.name == "20260816_01_auth-refactor-schema.sql"


# Transcribed from the specification's schema fence: every type and table it declares.
EXPECTED_TYPES = {
    "core.chat_role", "core.subscription_provider", "core.subscription_status",
    "core.identity_provider", "core.identity_state", "core.auth_operation",
    "core.access_grant_source", "core.access_grant_status", "core.auth_event_result",
    "core.native_claim_provider", "core.gate_consumption_kind",
}
EXPECTED_TABLES = {
    "core.users", "core.external_identities", "core.access_tiers", "core.chats",
    "core.messages", "core.subscriptions", "core.store_purchase_tokens", "core.store_purchases",
    "audit.subscription_events", "core.access_grants", "core.access_grants_anti_abuse",
    "core.manual_grant_issuances", "core.provider_accounts",
    "core.provider_account_gate_consumptions", "core.user_monthly_usage",
    "core.auth_challenges", "audit.auth_events",
}


# [utest->req~schema-ddl-as-written~1]
def test_the_applied_schema_declares_exactly_the_specified_types_and_tables(applied: Schema):
    assert set(applied.enums) == EXPECTED_TYPES
    assert set(applied.tables) == EXPECTED_TABLES
    assert applied.enums["core.identity_provider"] == ("anonymous", "google", "apple")
    assert applied.enums["core.identity_state"] == ("active", "historical")
    assert applied.enums["core.access_grant_status"] == ("active", "revoked", "expired")
    assert applied.enums["core.access_grant_source"] == (
        "subscription", "anonymous_device_grant", "registered_account_grant", "manual")


# --- `core.users` column facts ------------------------------------------------------------------

USERS_COLUMNS = {
    "id": "UUID PRIMARY KEY",
    "email": "TEXT",
    "display_name": "TEXT",
    "registered_at": "TIMESTAMPTZ",
    "active": "BOOLEAN NOT NULL DEFAULT TRUE",
    "created_at": "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
}


# Subscription plan, free access and custom access tiers are not fields on the user row.
# [utest->req~schema-users-no-plan-fields~1]
def test_the_user_row_carries_no_plan_free_access_or_tier_field(applied: Schema):
    assert applied.tables["core.users"].columns == USERS_COLUMNS
    forbidden = ("plan", "tier", "credit", "quota", "subscription", "free", "entitle")
    for column in applied.tables["core.users"].columns:
        assert not any(word in column for word in forbidden), column


# [utest->req~schema-users-timestamps-default-on-insert~1]
def test_user_timestamps_default_to_the_insert_timestamp(applied: Schema):
    users = applied.tables["core.users"].columns
    for column in ("created_at", "updated_at"):
        assert users[column] == "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"


# [utest->req~schema-users-shared-table-anon-registered~1]
def test_anonymous_and_registered_users_share_the_same_table_and_ownership_model(applied: Schema):
    # One user table, reached the same way for both kinds: there is no second owner table.
    assert [name for name in applied.tables if name.endswith("users")] == ["core.users"]
    # Nothing on the row itself separates the two kinds; the external identity carries the
    # provider, and `registered_at` is the only kind-related column on the user.
    assert "provider" not in applied.tables["core.users"].columns
    identities = applied.tables["core.external_identities"]
    assert identities.columns["provider"] == "core.identity_provider NOT NULL"
    assert identities.columns["user_id"].startswith("UUID NOT NULL REFERENCES core.users (id)")
    assert applied.enums["core.identity_provider"] == ("anonymous", "google", "apple")


# [utest->req~schema-users-chat-single-owner~1]
def test_every_chat_belongs_to_exactly_one_user(applied: Schema):
    chats = applied.tables["core.chats"]
    owning = [name for name, definition in chats.columns.items()
              if "REFERENCES core.users" in definition]
    assert owning == ["user_id"]
    assert chats.columns["user_id"] == "UUID NOT NULL REFERENCES core.users (id)"
    # No second owner may be attached through a table constraint either.
    assert not [c for c in chats.constraints if "core.users" in c]
    # Messages hang off the chat, so they inherit that one owner rather than naming their own.
    assert not [name for name, definition in applied.tables["core.messages"].columns.items()
                if "REFERENCES core.users" in definition]


# [utest->req~schema-users-access-via-access-grants~1]
def test_access_is_represented_by_access_grants(applied: Schema):
    grants = applied.tables["core.access_grants"]
    assert grants.columns["user_id"] == "UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE"
    assert grants.columns["tier_id"] == "TEXT NOT NULL REFERENCES core.access_tiers (id)"
    assert grants.columns["status"] == "core.access_grant_status NOT NULL DEFAULT 'active'"
    # The grant row, not the user row, is where access lives.
    assert not any("access" in column for column in applied.tables["core.users"].columns)


# [utest->req~schema-users-usage-via-user-monthly-usage~1]
def test_monthly_consumption_hangs_off_the_grant(applied: Schema):
    usage = applied.tables["core.user_monthly_usage"]
    assert usage.columns["grant_id"] == \
        "UUID PRIMARY KEY REFERENCES core.access_grants (id) ON DELETE CASCADE"
    assert set(usage.columns) == {"grant_id", "monthly_period", "monthly_used",
                                  "created_at", "updated_at"}
    # Usage is never owned by the user row directly.
    assert "user_id" not in usage.columns


# [utest->req~schema-users-never-hard-deleted~1]
def test_a_user_row_with_an_identity_row_cannot_be_hard_deleted(applied: Schema):
    identities = applied.tables["core.external_identities"]
    assert identities.columns["user_id"] == \
        "UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT"
    # A cascade anywhere on that reference would delete the row the specification retains.
    assert "ON DELETE CASCADE" not in identities.columns["user_id"]
