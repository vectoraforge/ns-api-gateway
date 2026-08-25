from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import DateTime, Enum
from sqlmodel import Field, SQLModel


class PurchaseProvider(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_provider` -- exactly two values."""
    apple = "apple"
    google_play = "google_play"


# `name=` pins the pre-existing type; without it SQLAlchemy derives a second, differently-named enum.
PurchaseProviderType = cast(Any, Enum(PurchaseProvider, name='subscription_provider', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))


class StorePurchaseToken(SQLModel, table=True):
    """One purchase-attribution token per user per store, for the account's life."""

    __tablename__ = "store_purchase_tokens"
    __table_args__ = {"schema": "core"}

    # The table has no database primary key; these two markers are ORM-level, met by UNIQUE (user_id, provider).
    user_id: UUID = Field(foreign_key="core.users.id", primary_key=True)
    provider: PurchaseProvider = Field(sa_type=PurchaseProviderType, primary_key=True)
    # Deliberately not `unique=True`: the table's rule is the composite UNIQUE (provider, identity_value).
    identity_value: str = Field()
    created_at: datetime = Field(sa_type=DateTimeType)
