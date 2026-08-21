"""The §1.2 / §8.2 bounded-cardinality rejection counter and the structured security log.

§8.2 puts every route this phase registers **off** the audited attempt path, so a barrier
rejection there writes no `audit.auth_events` row -- ever. What it writes instead is exactly this:
one counter increment and one structured security-log event carrying the stable internal result.
The counter, not the audit table, is §1.2's required alerting source for cross-route attack volume
and for a systemic verification break, so it increments **wherever the barrier rejects**, on and
off the audited path alike.

**Cardinality is bounded by construction**, because all three label values come from closed sets:
`AuthEventResult` members, `BoundedReason` members, and the registry's declared path templates.
The raw request path, the raw token, the subject, and the client address are never labels -- a
single unbounded label would make the counter unusable and would put caller-controlled text into
telemetry. The route label is the matched route's path *template* (`/chats/{chat_id}`), which is
why a hundred distinct chat ids collapse into one key.

Nothing exports this counter yet. `snapshot()` makes it readable, but this deployment ships no
Prometheus client and no scrape endpoint, so the operational alert §1.2 calls for cannot fire.
Recorded as an accepted v2.0 gap in 35-06-SUMMARY.md rather than left to be rediscovered.
"""
import structlog
from starlette.datastructures import State

from nativespeaker.api.auth.wire import BoundedReason
from nativespeaker.api.models.auth import AuthEventResult

logger = structlog.get_logger()


class RejectionCounter:
    """An in-process counter keyed by result x bounded reason x route.

    A plain dict is the whole implementation: this counts rejections in one process, and D-05
    removed the distributed-counter subsystem from the product. An exporter reads `snapshot()`.
    """

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str | None, str], int] = {}

    def increment(self, *, result: str, bounded_reason: str | None, route: str) -> None:
        key = (result, bounded_reason, route)
        self._counts[key] = self._counts.get(key, 0) + 1

    def snapshot(self) -> dict[tuple[str, str | None, str], int]:
        """A copy, so a reader cannot mutate live counts."""
        return dict(self._counts)


def record_rejection(app_state: State, *,
                     result: AuthEventResult,
                     bounded_reason: BoundedReason | None,
                     route: str) -> None:
    """Count one barrier rejection and emit its security-log event.

    The bounded reason travels here and, for on-path routes, into the audit row's
    `details.failure`. It is never client-visible, and it never names the issuer, the integration,
    or the failed check.
    """
    reason = None if bounded_reason is None else str(bounded_reason)
    counter = getattr(app_state, "rejection_counter", None)
    if counter is None:
        # A telemetry gap must never change what the client is told, so this does not raise --
        # but the counter is §1.2's required alerting source, so its absence is loud in the log.
        logger.error("rejection_counter_missing",
                     result=str(result), bounded_reason=reason, route=route)
    else:
        counter.increment(result=str(result), bounded_reason=reason, route=route)
    logger.warning("auth_rejected", result=str(result), bounded_reason=reason, route=route)
