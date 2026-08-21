"""The single-Authorization wire contract (spec 01-foundation.md §1.1).

Reads the raw ASGI header list directly. Never `Headers.get`, never `Headers[...]`, never
FastAPI's `Header()` alias: `Headers.get` returns only the *first* matching value and discards the
rest, which silently satisfies the duplicate-field attack this contract exists to reject.
"""
from enum import StrEnum

_AUTHORIZATION = b"authorization"
_BEARER = b"bearer"


class BoundedReason(StrEnum):
    """§1.1 / §4.5 rejection reasons -- audit `details.failure` and metric labels only.

    Never client-visible: every one of these surfaces the identical `auth_required` status, body,
    and copy.
    """
    missing_token = "missing_token"
    malformed = "malformed"
    duplicate_authorization = "duplicate_authorization"
    bad_signature = "bad_signature"
    issuer_mismatch = "issuer_mismatch"
    audience_mismatch = "audience_mismatch"
    expired = "expired"
    empty_subject = "empty_subject"


def extract_bearer(raw_headers: list[tuple[bytes, bytes]]) -> tuple[str | None, BoundedReason | None]:
    """Return `(token, None)` for exactly one well-formed Bearer credential, else `(None, reason)`.

    Field instances are counted before any value is inspected, so a request carrying two
    Authorization values is rejected without either being selected -- there is no first-value or
    last-value path for an attacker to steer. HTTP field names are case-insensitive and ASGI
    guarantees lowercase keys, so `Authorization`, `authorization`, and `AUTHORIZATION` all arrive
    folded into the same key and differently-cased occurrences count as duplicates.
    """
    values = [v for (k, v) in raw_headers if k == _AUTHORIZATION]
    if not values:
        return None, BoundedReason.missing_token
    if len(values) > 1:
        return None, BoundedReason.duplicate_authorization

    value = values[0]
    if b"," in value or b"\n" in value or b"\r" in value:  # comma-joined or line-folded
        return None, BoundedReason.duplicate_authorization

    parts = value.split(b" ")  # exactly two parts: no trailing content, no internal padding
    if len(parts) != 2 or parts[0].lower() != _BEARER or not parts[1]:
        return None, BoundedReason.malformed

    try:
        # The scheme matched case-insensitively; the token bytes are case-sensitive and are never
        # trimmed, case-folded, decoded and re-encoded, or otherwise normalized.
        token = parts[1].decode("ascii", "strict")
    except UnicodeDecodeError:
        return None, BoundedReason.malformed
    return token, None
