"""The structured security log for barrier rejections.

**This is the whole record a rejection leaves.** Nothing persists an auth attempt to a table, so
this one structured event carrying the stable internal result is the rejection signal -- the cheap,
no-schema version of the durable trail, and the only one there is (37.1 D-01/D-03).

The bounded reason is a closed-set value (`BoundedReason`) and the route is the matched route's
path *template* (`/chats/{chat_id}`), never the raw path -- caller-controlled text never reaches
the log fields, and a hundred distinct chat ids collapse into one route value.

There is deliberately no in-process metric object here. Rejection rate is derived from these log
events by whatever log pipeline the deployment runs; the service does not hand-roll its own
counter subsystem to be scraped.
"""
import structlog

from nativespeaker.api.auth.wire import BoundedReason
from nativespeaker.api.models.auth import AuthEventResult

logger = structlog.get_logger()


def record_rejection(*,
                     result: AuthEventResult,
                     bounded_reason: BoundedReason | None,
                     route: str) -> None:
    """Emit the security-log event for one barrier rejection.

    The bounded reason travels here and nowhere else. It is never client-visible, and it never
    names the issuer, the integration, or the failed check.
    """
    reason = None if bounded_reason is None else str(bounded_reason)
    logger.warning("auth_rejected", result=str(result), bounded_reason=reason, route=route)
