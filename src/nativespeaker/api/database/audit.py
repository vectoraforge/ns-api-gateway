"""`audit.auth_events` insertion.

The sink is deliberately dumb: the row arrives already built, redacted and validated by
`auth.audit.auth_event_row`, so there is no second place where a `details` body could be
assembled and no path by which raw event details could reach the table.
"""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

INSERT_AUTH_EVENT = text("""
    INSERT INTO audit.auth_events (
        id, challenge_row_id, operation, result, actor_issuer, actor_subject_hash,
        actor_subject_hash_key_version, actor_provider, details, created_at)
    VALUES (:id, :challenge_row_id, :operation, :result, :actor_issuer, :actor_subject_hash,
            :actor_subject_hash_key_version, :actor_provider, CAST(:details AS jsonb),
            :created_at)
""")


class AuthEventsDB:
    """Appends one durable `audit.auth_events` row inside the caller's transaction."""

    # [impl->req~shared-audit-write-in-transaction~1]
    async def insert(self, session: Any, row: Mapping[str, Any]) -> None:
        parameters = dict(row)
        parameters["operation"] = None if row["operation"] is None else str(row["operation"])
        parameters["result"] = str(row["result"])
        parameters["actor_provider"] = (None if row["actor_provider"] is None
                                        else str(row["actor_provider"]))
        parameters["details"] = json.dumps(row["details"], default=str)
        await session.execute(INSERT_AUTH_EVENT, parameters)
