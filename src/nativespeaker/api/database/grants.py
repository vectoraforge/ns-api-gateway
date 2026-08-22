"""Entitlement reads over `core.access_grants`, and the first implementation of the lock order.

SHARED-INVARIANTS:33 fixes one global lock order for every path that touches grants, now and
later: the grant row(s) `FOR UPDATE` first, ascending by grant id, and only then their
`core.user_monthly_usage` rows in the same order. Never the reverse, and never a user-row lock
tier ahead of the grants. This module is the first place that order is written down in code, so
Phases 41, 42 and 45 copy the shape here rather than re-deriving it -- which is why the locking is
two separate statements and not one locking join. A join gives no guarantee about which row the
executor locks first *within* the statement, so it cannot be shown to satisfy the invariant;
two statements make the order auditable by reading them in order.

Nothing here reads the system clock. `evaluated_at` is a required parameter on every method that
needs one, always supplied by the caller from `RequestContext.evaluated_at` (D-06), so two reads
inside one request cannot straddle a period or grant boundary.
"""
from datetime import datetime
from uuid import UUID

from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.models import AccessGrant, AccessGrantStatus


class GrantsDB:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_effective_grants(self, user_id: UUID,
                                    evaluated_at: datetime) -> list[AccessGrant]:
        """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id.

        "Effective" is the shared predicate SHARED-INVARIANTS names, never `status` alone.
        """
        statement = (
            select(AccessGrant)
            .where(col(AccessGrant.user_id) == user_id,
                   # `== active`, not `!= revoked`: a NULL and any future enum member must fail
                   # closed on this comparison rather than be admitted as "not terminal".
                   col(AccessGrant.status) == AccessGrantStatus.active,
                   col(AccessGrant.starts_at) <= evaluated_at,
                   # Ruling 9.11 makes open-ended grants legal, so a NULL `ends_at` is effective
                   # forever; a finite end is exclusive, so a grant ending exactly at
                   # `evaluated_at` is already over.
                   or_(col(AccessGrant.ends_at).is_(None),
                       col(AccessGrant.ends_at) > evaluated_at))
            # Ascending grant id is the lock order itself, not presentation: it is what makes two
            # concurrent requests for the same user take the same rows in the same sequence.
            .order_by(col(AccessGrant.id).asc())
            # No eager-loading option is applied here, and none may be added. PostgreSQL rejects
            # FOR UPDATE combined with the outer join that `selectinload`/`joinedload` emit, so
            # copying `ChatsDB.get_chat`'s option (database/chats.py:21) would turn this statement
            # into a runtime error rather than a slower query.
            .with_for_update()
        )
        # Every matching row, with no `.limit(...)`. D-10 requires the caller to *see* a second
        # effective grant and fail closed on it: more than one active grant is an integrity
        # failure, and a cap here would let the database silently pick one and hide it. The
        # partial unique index `ix_access_grants_one_active_per_user` is what makes that state
        # unreachable in practice; the missing cap is what makes it detectable if it ever is not.
        return list((await self.session.exec(statement)).all())
