"""The global lock order for grant and usage rows.

Grant lock(s) first, usage-row lock(s) second, never the reverse; several grants in ascending
grant `id` order and their usage rows in that same order; and no store, provider, network or
other external call while any of those locks is held. The fixed order, not per-path exceptions,
is what keeps restore and the quota hot path from deadlocking against each other.
"""

from enum import StrEnum
from types import TracebackType
from uuid import UUID


class LockOrderError(RuntimeError):
    """A transaction asked for a lock out of the one fixed order."""


class ExternalCallUnderLockError(RuntimeError):
    """Remote work was attempted while a grant or usage row lock was held."""


class LockingPath(StrEnum):
    """Every path this specification lets reach the grant and usage rows. A path added later
    takes the same fixed order; there is no per-path exception."""
    restore_mutation = "restore_mutation"
    lazy_monthly_rollover = "lazy_monthly_rollover"
    claim_anonymous_grant_completion = "claim_anonymous_grant_completion"
    claim_registered_grant_completion = "claim_registered_grant_completion"
    manual_issuance = "manual_issuance"


# The grant procedures lock the target user first and then that user's whole live grant set in
# the fixed order. `restore_subscription` and the lazy rollover take no user-row lock at all, so
# no user-row lock tier ever runs ahead of their grant locks and that leading lock closes no
# cycle.
# [impl->req~shared-invariant-12~1]
USER_ROW_LOCK_PATHS: frozenset[LockingPath] = frozenset({
    LockingPath.claim_anonymous_grant_completion,
    LockingPath.claim_registered_grant_completion,
    LockingPath.manual_issuance,
})
NO_USER_ROW_LOCK_PATHS: frozenset[LockingPath] = frozenset(set(LockingPath) - USER_ROW_LOCK_PATHS)


def takes_user_row_lock(path: LockingPath) -> bool:
    """Whether the path locks the target user row ahead of its grant locks."""
    # [impl->req~shared-invariant-12~1]
    return path in USER_ROW_LOCK_PATHS


class LockLedger:
    """One transaction's lock acquisitions, in the order it made them.

    Every path that reaches `core.access_grants` and `core.user_monthly_usage` goes through this
    ledger, so the fixed order is enforced where the locks are taken rather than reviewed after
    the fact.
    """

    def __init__(self, path: LockingPath):
        self.path = path
        self._user_locks: list[UUID] = []
        self._grant_locks: list[UUID] = []
        self._usage_locks: list[UUID] = []
        self._open = True

    # --- acquisition ----------------------------------------------------------------------

    def lock_user(self, user_id: UUID) -> None:
        """Lock the target user row. Only the grant procedures do this, and only before any
        grant lock: `restore_subscription` and the lazy rollover take no user-row lock at all."""
        # [impl->req~shared-invariant-12~1]
        self._require_open()
        if not takes_user_row_lock(self.path):
            raise LockOrderError(f"{self.path} takes no user-row lock")
        if self._grant_locks or self._usage_locks:
            raise LockOrderError("the user row is locked before any grant or usage row")
        self._user_locks.append(user_id)

    def lock_grant(self, grant_id: UUID) -> None:
        """Lock a `core.access_grants` row `FOR UPDATE`. Grants come first, and where a
        transaction locks more than one they are locked in ascending grant `id` order — never in
        the order the transaction happened to discover them."""
        # [impl->req~shared-invariant-12~1]
        self._require_open()
        if self._usage_locks:
            # No path may hold a usage-row lock and then request a grant lock.
            raise LockOrderError("a usage-row lock is held; no grant lock may follow it")
        if self._grant_locks and grant_id <= self._grant_locks[-1]:
            raise LockOrderError(
                f"grant {grant_id} follows {self._grant_locks[-1]} out of ascending id order")
        self._grant_locks.append(grant_id)

    def lock_usage(self, grant_id: UUID) -> None:
        """Lock the `core.user_monthly_usage` row owned by `grant_id`. Its owning grant row must
        already be locked — no path may lock a usage row while reading its grant unlocked — and
        usage rows are locked in the same ascending grant-id order as their grants."""
        # [impl->req~shared-invariant-12~1]
        self._require_open()
        if grant_id not in self._grant_locks:
            raise LockOrderError(f"grant {grant_id} must be locked FOR UPDATE before its usage row")
        if self._usage_locks and grant_id <= self._usage_locks[-1]:
            raise LockOrderError(
                f"usage row for {grant_id} follows {self._usage_locks[-1]} out of order")
        self._usage_locks.append(grant_id)

    # --- external work --------------------------------------------------------------------

    def external_call(self, name: str) -> None:
        """A store, provider, network or other external call. Remote work runs before the
        locking transaction opens or after it commits, never while a lock is held."""
        # [impl->req~shared-invariant-12~1]
        if self.holds_locks:
            raise ExternalCallUnderLockError(
                f"{name} may not run while {self.path} holds grant or usage locks")

    @property
    def holds_locks(self) -> bool:
        return self._open and bool(self._user_locks or self._grant_locks or self._usage_locks)

    @property
    def grant_locks(self) -> tuple[UUID, ...]:
        return tuple(self._grant_locks)

    @property
    def usage_locks(self) -> tuple[UUID, ...]:
        return tuple(self._usage_locks)

    def commit(self) -> None:
        """The transaction commits and its locks are released; remote work may run again."""
        self._open = False

    def _require_open(self) -> None:
        if not self._open:
            raise LockOrderError("the locking transaction has already committed")

    def __enter__(self) -> LockLedger:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 traceback: TracebackType | None) -> None:
        self.commit()


def lock_grant_set(ledger: LockLedger, grant_ids: list[UUID], *, with_usage: bool = True) -> None:
    """Lock a whole live grant set: the grants in ascending `id` order, then their usage rows in
    that same order."""
    # [impl->req~shared-invariant-12~1]
    ordered = sorted(grant_ids)
    for grant_id in ordered:
        ledger.lock_grant(grant_id)
    if with_usage:
        for grant_id in ordered:
            ledger.lock_usage(grant_id)
