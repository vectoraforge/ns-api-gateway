"""§6.5 the shared mode-signal partition -- the one syntactic check every challenge-bearing
endpoint calls.

`challenge=true` in the query string and no body handle is **prepare**. A body handle and no
`challenge=true` is **completion**. Both together, or neither, is `invalid_request` -- the same
`invalid_request` that covers a `challenge` parameter whose value is anything other than exactly
`true`, a duplicated `challenge` parameter, and a body handle that is null, empty, or wrongly
typed.

Prepare is never *inferred* from a missing challenge, and one signal is never silently preferred
over the other. Guessing on the client's behalf is how an ambiguous request ends up consuming a
challenge the client meant to reuse.

**The check is purely syntactic and has no side effects.** It issues nothing, looks up nothing,
consumes nothing, and changes no state. It has no internal `AuthEventResult` and belongs to the
admission phase: a rejection here is recorded only in
the structured security log and the counter metric. That matters concretely -- a corrected retry
may reuse the same unexpired challenge, and it can only do so because this ran without touching the
row.

Foundation ships this check and nothing more. Mode-signal *dispatch*, provider normalization, proof
verification, and the consuming-transaction body belong to each endpoint's own phase.
"""
from enum import StrEnum
from urllib.parse import parse_qsl

_CHALLENGE = b"challenge"
_TRUE = b"true"


class ModeSignal(StrEnum):
    """The two modes a challenge-bearing endpoint can be in."""
    prepare = "prepare"
    completion = "completion"


def classify_mode_signal(raw_query: bytes, body_challenge_id: object) -> ModeSignal | None:
    """Classify one request's mode signals. `None` means `invalid_request`.

    `raw_query` is the ASGI `scope["query_string"]` bytes, parsed here rather than read through a
    first-value-wins accessor. A duplicated `challenge` parameter is its own `invalid_request`
    case, and an accessor that folds duplicates would silently satisfy it -- exactly the trap the
    `Authorization` wire contract (`auth/wire.py`) exists to avoid, one layer up.

    `body_challenge_id` is whatever the parsed request body carried under `challenge_id`, typed
    `object` on purpose: a client can put anything there, and a signature promising `str | None`
    would push the wrong-type case onto every caller. `None` is the **absent** case; a present but
    unusable handle is `invalid_request` in its own right and is never re-read as absent.
    """
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
        # `.strip()` decides emptiness only. The value itself is passed on untouched: `locate`
        # compares byte-for-byte (§6.1), and trimming here would widen that lookup from two
        # modules away. A handle with stray whitespace is `challenge_not_found`, not
        # `invalid_request`.
        completion_signalled = True
    else:
        return None                                   # empty, whitespace-only, or wrongly typed

    if prepare_signalled == completion_signalled:     # both signals, or neither
        return None
    return ModeSignal.prepare if prepare_signalled else ModeSignal.completion
