"""Ownership keys: `core.users.id` owns business data, `core.access_grants.id` owns usage.

The check runs over the mapped table metadata at startup, so a business table that tries to
own rows by an external subject, or a monthly usage table that hangs off the user instead of
the grant that authorizes its credits, fails loudly.
"""

from typing import Any

USER_OWNERSHIP_KEY = "core.users.id"
GRANT_OWNERSHIP_KEY = "core.access_grants.id"

# Monthly usage rows are owned by the access grant, so usage stays with the entitlement grant
# that authorizes it for the life of that grant. The set is matched by role rather than by one
# future table name: whatever a monthly usage table is called, it owes the grant ownership key.
GRANT_OWNED_TABLES: frozenset[str] = frozenset({
    "user_monthly_usage", "usage_monthly", "monthly_usage", "user_usage_monthly",
})

# Columns that carry an external subject (`sub`, `uid`, ...). They may exist only on the
# identity tables, which map external identities onto internal users.
EXTERNAL_SUBJECT_COLUMNS: frozenset[str] = frozenset({
    "sub", "uid", "subject", "jwt_sub", "firebase_uid", "idp_sub", "external_subject",
})
IDENTITY_TABLES: frozenset[str] = frozenset({"external_identities", "users"})

_OWNER_COLUMN_SUFFIX = "user_id"


class OwnershipKeyError(RuntimeError):
    """A mapped table owns rows by something other than the permitted ownership key."""


def ownership_violations(metadata: Any) -> list[str]:
    """Return every ownership-key violation in the mapped schema."""
    violations: list[str] = []
    for table in metadata.tables.values():
        name = table.name
        for column in table.columns:
            targets = {fk.target_fullname for fk in column.foreign_keys}
            # Business ownership remains through `core.users.id`: no business table keys
            # ownership on an external subject (`sub`, `uid`, ...).
            # [impl->req~shared-no-external-subject-ownership~1]
            # [impl->req~sessions-no-external-subject-ownership~1]
            if name not in IDENTITY_TABLES and column.name in EXTERNAL_SUBJECT_COLUMNS:
                violations.append(
                    f"{name}.{column.name} uses an external subject as an ownership key")
            if any(target.rsplit(".", 1)[0].endswith("external_identities") for target in targets):
                violations.append(
                    f"{name}.{column.name} owns rows by an external identity, not {USER_OWNERSHIP_KEY}")
            # Chats, messages, subscription billing records, store purchases, access grants and
            # introductory allocation state always belong to internal `core.users.id`; monthly
            # usage counters belong to `core.access_grants.id`.
            # [impl->req~shared-ownership-key-users-id~1]
            # [impl->req~sessions-users-id-sole-ownership-key~1]
            # [impl->req~schema-invariant-01~1]
            # [impl->req~grants-invariant-01~2]
            # [impl->req~restore-invariant-01~2]
            if column.name.endswith(_OWNER_COLUMN_SUFFIX) and targets:
                if name in GRANT_OWNED_TABLES:
                    violations.append(f"{name}.{column.name} must be owned by {GRANT_OWNERSHIP_KEY}")
                elif targets != {USER_OWNERSHIP_KEY}:
                    violations.append(
                        f"{name}.{column.name} must reference {USER_OWNERSHIP_KEY}, got {sorted(targets)}")
        # Monthly usage counters belong to `core.access_grants.id`; the free-credit grant material
        # states no second ownership rule of its own.
        # [impl->req~schema-invariant-01~1]
        # [impl->req~grants-invariant-01~2]
        # [impl->req~restore-invariant-01~2]
        if name in GRANT_OWNED_TABLES:
            grant_owned = any(GRANT_OWNERSHIP_KEY in {fk.target_fullname for fk in column.foreign_keys}
                              for column in table.columns)
            if not grant_owned:
                violations.append(f"{name} must be owned by {GRANT_OWNERSHIP_KEY}")
    return violations


def assert_ownership_keys(metadata: Any) -> None:
    violations = ownership_violations(metadata)
    if violations:
        raise OwnershipKeyError("; ".join(sorted(set(violations))))
