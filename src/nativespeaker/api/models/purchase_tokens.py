"""The `core.store_purchase_tokens` table and the Python mirror of the enum it binds.

**The Python names here deliberately diverge from the database's, and neither side may be
"fixed" to match the other.** The PostgreSQL type is and remains `core.subscription_provider`
(`migrations/20260818_01_initial-release.sql:54`), consumed today by three existing tables; this
phase migrates nothing, so it keeps that name. The Python class is `PurchaseProvider`, and this
module is `purchase_tokens.py` rather than `subscriptions.py`, because
`tests/unit/test_users.py::TestSubscriptionModelLayerIsGone` is a live D-16 guard over the
*removed subscription-plan layer*: it forbids the file `models/subscriptions.py`, every name in
its `REMOVED_SYMBOLS` frozenset, and any `models.__all__` entry containing `Subscription` or
`Usage`. Purchase attribution is a different feature that happens to reuse one old enum, so the
guard stays at full strength and this module routes around it by name instead.

The database owns every constraint. The table's two UNIQUE rules -- `UNIQUE (user_id, provider)`
and `UNIQUE (provider, identity_value)` -- are declared in the migration and are deliberately
not re-encoded here: a Python copy of a constraint is a second source of truth that can drift
from the one that actually enforces.
"""
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import DateTime, Enum
from sqlmodel import Field, SQLModel


class PurchaseProvider(StrEnum):
    """Mirrors `core.subscription_provider` -- exactly two values (migration:54)."""
    apple = "apple"
    google_play = "google_play"


# `name=` names the PRE-EXISTING PostgreSQL type `core.subscription_provider`. The Python class
# above is NOT it, and neither argument may be dropped or "tidied" to agree with the class name:
# without an explicit `name=`, SQLAlchemy derives the type name from the Python class and will
# happily emit a SECOND, differently-named enum type at DDL time. Nothing fails at import; the
# divergence first surfaces as a type error on a real INSERT.
PurchaseProviderType = cast(Any, Enum(PurchaseProvider, name='subscription_provider', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class StorePurchaseToken(SQLModel, table=True):
    """One purchase-attribution token per user per store, for the account's life.

    **The two `primary_key=True` markers below are ORM-level only.** The table has NO database
    primary key by design; SQLAlchemy's mapper needs a row identity, and the table's own
    `UNIQUE (user_id, provider)` already supplies one. Do NOT add a `PRIMARY KEY` to the
    migration to make the mapper happy -- SCHEMA-01 forbids incremental migrations, and the
    PK-less shape is a documented ruling
    (`migrations/20260818_01_initial-release.sql:327-338`: "Intentionally has NO primary key;
    its two UNIQUE constraints carry the rules").
    """

    __tablename__ = "store_purchase_tokens"
    __table_args__ = {"schema": "core"}

    # ON DELETE CASCADE in the migration: the token has no meaning without its user row.
    user_id: UUID = Field(foreign_key="core.users.id", primary_key=True)
    provider: PurchaseProvider = Field(sa_type=PurchaseProviderType, primary_key=True)
    # A random, opaque, server-generated UUID: no PII, not derivable from identity, never
    # rotated, one per user per store for the account's life, and it survives the
    # anonymous-to-registered upgrade.
    #
    # Deliberately NOT `unique=True`. The table's second uniqueness rule is the COMPOSITE
    # `UNIQUE (provider, identity_value)`; a single-column marker here would describe a stricter
    # rule than the database enforces, which is the second-source-of-truth drift this project
    # keeps out of its models.
    identity_value: str = Field()
    created_at: datetime = Field(sa_type=DateTimeType)

    # No default factory on either `identity_value` or `created_at`, on purpose. The creating
    # transaction supplies both: `created_at` from the request's single captured
    # `RequestContext.evaluated_at` (35 D-02: never recompute it), and `identity_value` from a
    # fresh `uuid4()` per row. A model-level default would put a second clock and a second RNG
    # on a path that must have exactly one of each.
