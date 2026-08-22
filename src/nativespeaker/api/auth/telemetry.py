"""The structured security log for barrier rejections.

§8.2 puts every route this phase registers **off** the audited attempt path, so a barrier
rejection there writes no `audit.auth_events` row -- ever. What it writes instead is this one
structured security-log event carrying the stable internal result.

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

    The bounded reason travels here and, for on-path routes, into the audit row's
    `details.failure`. It is never client-visible, and it never names the issuer, the integration,
    or the failed check.
    """
    reason = None if bounded_reason is None else str(bounded_reason)
    logger.warning("auth_rejected", result=str(result), bounded_reason=reason, route=route)
