from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

DateTimeType = cast(Any, DateTime(timezone=True))


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # Nullable on purpose: copied only from a provider record whose email is verified, left NULL otherwise.
    email: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    # Reporting-only, never a classifier: `core.external_identities.provider` is the sole classifier.
    registered_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    # Tested positively (`is not True` rejects), so an unexpected value fails closed.
    active: bool = Field(default=True)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
