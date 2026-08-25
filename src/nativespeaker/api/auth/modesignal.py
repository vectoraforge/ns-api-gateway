"""The shared mode-signal check: `challenge=true` is prepare, a body handle is completion."""
from enum import StrEnum
from urllib.parse import parse_qsl

_CHALLENGE = b"challenge"
_TRUE = b"true"


class ModeSignal(StrEnum):
    """The two modes a challenge-bearing endpoint can be in."""
    prepare = "prepare"
    completion = "completion"


def classify_mode_signal(raw_query: bytes, body_challenge_id: object) -> ModeSignal | None:
    """Classify one request's mode signals. `None` is `invalid_request`; both signals or neither is one."""
    # Parsed here, not through a first-value-wins accessor: a duplicate is its own rejection.
    values = [value for key, value in parse_qsl(raw_query, keep_blank_values=True)
              if key == _CHALLENGE]
    if len(values) > 1:
        return None                                   # duplicated parameter
    if values and values[0] != _TRUE:
        return None                                   # any value other than exactly `true`
    prepare_signalled = bool(values)

    if body_challenge_id is None:
        completion_signalled = False
    elif isinstance(body_challenge_id, str) and body_challenge_id.strip():
        # `.strip()` decides emptiness only; the value passes through untrimmed for `locate`.
        completion_signalled = True
    else:
        return None                                   # empty, whitespace-only, or wrongly typed

    if prepare_signalled == completion_signalled:     # both signals, or neither
        return None
    return ModeSignal.prepare if prepare_signalled else ModeSignal.completion
