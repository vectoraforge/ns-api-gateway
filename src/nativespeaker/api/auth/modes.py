"""The mode-signal partition for challenge-bearing auth endpoints.

A syntactic request-shape check that runs before any challenge processing: it assigns the
request no operation-specific meaning, has no internal `core.auth_event_result`, and belongs
to the admission phase, so its rejection writes no `audit.auth_events` row.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nativespeaker.api.exceptions import ServiceError

CHALLENGE_QUERY_PARAM = "challenge"
CHALLENGE_QUERY_VALUE = "true"
CHALLENGE_ID_FIELD = "challenge_id"


class RequestMode(StrEnum):
    prepare = "prepare"
    completion = "completion"


class ModeSignalDefect(StrEnum):
    """Bounded telemetry reason for an `invalid_request` mode-signal rejection."""
    both_signals = "both_signals"
    neither_signal = "neither_signal"
    challenge_param_not_true = "challenge_param_not_true"
    duplicate_challenge_param = "duplicate_challenge_param"
    malformed_challenge_id = "malformed_challenge_id"


class ModeSignalError(ServiceError):
    """The shared `invalid_request` class: the request's shape is wrong before any
    operation-specific meaning can be assigned to it."""
    status_code = 400
    error_code = "invalid_request"

    def __init__(self, defect: ModeSignalDefect):
        self.defect = defect
        super().__init__("Invalid request")


@dataclass(frozen=True, slots=True)
class ModeSignal:
    mode: RequestMode
    challenge_id: str | None = None


def classify_mode(query_items: Sequence[tuple[str, str]],
                  body: Mapping[str, Any] | None) -> ModeSignal:
    """Partition every request to a challenge-bearing auth endpoint into prepare, completion,
    or `invalid_request`. Pure and side-effect free: it issues no challenge, looks up and
    consumes none, and changes no operation state."""
    # [impl->req~shared-mode-signal-partition~1]
    # [impl->req~shared-mode-check-no-side-effects~1]
    # [impl->req~shared-no-implicit-prepare-mode~1]
    values = [value for name, value in query_items if name == CHALLENGE_QUERY_PARAM]
    if len(values) > 1:
        # [impl->req~shared-mode-malformed-shapes~1]
        raise ModeSignalError(ModeSignalDefect.duplicate_challenge_param)
    if values and values[0] != CHALLENGE_QUERY_VALUE:
        raise ModeSignalError(ModeSignalDefect.challenge_param_not_true)
    prepare_signalled = bool(values)

    challenge_id: str | None = None
    completion_signalled = body is not None and CHALLENGE_ID_FIELD in body
    if completion_signalled:
        assert body is not None
        raw = body[CHALLENGE_ID_FIELD]
        if not isinstance(raw, str) or not raw:
            raise ModeSignalError(ModeSignalDefect.malformed_challenge_id)
        challenge_id = raw

    # [impl->req~shared-mode-invalid~1]
    # [impl->req~shared-mode-invalid-request-class~1]
    if prepare_signalled and completion_signalled:
        raise ModeSignalError(ModeSignalDefect.both_signals)
    if not prepare_signalled and not completion_signalled:
        raise ModeSignalError(ModeSignalDefect.neither_signal)

    if prepare_signalled:
        # [impl->req~shared-mode-prepare~1]
        return ModeSignal(RequestMode.prepare)
    # [impl->req~shared-mode-completion~1]
    return ModeSignal(RequestMode.completion, challenge_id)
