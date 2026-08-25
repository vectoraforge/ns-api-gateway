"""The structured security log for auth rejections -- the only record a rejection leaves."""
import structlog

from nativespeaker.api.auth.wire import BoundedReason
from nativespeaker.api.models.auth import AuthEventResult

logger = structlog.get_logger()


def record_rejection(*,
                     result: AuthEventResult,
                     bounded_reason: BoundedReason | None,
                     route: str) -> None:
    """Emit the event for one rejection. `route` is the path template, never the caller's raw path."""
    reason = None if bounded_reason is None else str(bounded_reason)
    logger.warning("auth_rejected", result=str(result), bounded_reason=reason, route=route)
