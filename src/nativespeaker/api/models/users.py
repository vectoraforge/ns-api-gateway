"""The `core.users` table at the section 2 target shape.

Seven columns, taken from `migrations/20260818_01_initial-release.sql` lines 150-158. Three
columns the v1.6 model carried are deliberately absent, each for its own reason:

- `jwt_sub` -- the external subject is never an ownership or lookup key in v2.0. `(issuer,
  subject)` lives only on `core.external_identities`, behind the barrier's single identity query,
  so there is no model-level path by which a token subject can become an ownership key.
- `name` -- renamed `display_name` by the schema.
- `subscription_plan` -- allowance moved to `core.access_tiers.monthly_credits`, resolved through
  the grant Phase 36 wires.

`core.usage_monthly` was dropped by the same migration, so `UsageMonthly` went with it. Phase 36
introduces `core.user_monthly_usage`, keyed on `grant_id`; that is a different table it owns.
"""
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
    # NULLABLE on purpose (00-schema.md:80): copied only from a Firebase Admin record whose
    # `emailVerified` is TRUE, and left NULL otherwise. Do not add NOT NULL or a non-None default.
    email: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    # Reporting-only. Never a classifier: `core.external_identities.provider` is the sole
    # per-request classifier for every identity, entitlement, and audit decision.
    registered_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    # A plain NOT NULL boolean the barrier tests positively (`is not True` rejects), so an
    # unexpected value fails closed.
    active: bool = Field(default=True)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
