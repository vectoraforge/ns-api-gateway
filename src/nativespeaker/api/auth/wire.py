"""The wire contract: a request carries exactly one well-formed Authorization header, or it is rejected."""
from enum import StrEnum

_AUTHORIZATION = b"authorization"
_BEARER = b"bearer"


class BoundedReason(StrEnum):
    """Rejection reasons for logs and metric labels; all of them surface the same copy to the client."""
    missing_token = "missing_token"
    malformed = "malformed"
    duplicate_authorization = "duplicate_authorization"
    bad_signature = "bad_signature"
    issuer_mismatch = "issuer_mismatch"
    audience_mismatch = "audience_mismatch"
    expired = "expired"
    empty_subject = "empty_subject"


def extract_bearer(raw_headers: list[tuple[bytes, bytes]]) -> tuple[str | None, BoundedReason | None]:
    """Return `(token, None)` for exactly one well-formed Bearer credential, else `(None, reason)`."""
    # ASGI lowercases header names, so differently-cased duplicates fold into this one key.
    values = [v for (k, v) in raw_headers if k == _AUTHORIZATION]
    if not values:
        return None, BoundedReason.missing_token
    # Counted before any value is read: `Headers.get` returns the first and hides the rest.
    if len(values) > 1:
        return None, BoundedReason.duplicate_authorization

    value = values[0]
    if b"," in value or b"\n" in value or b"\r" in value:  # comma-joined or line-folded
        return None, BoundedReason.duplicate_authorization

    parts = value.split(b" ")  # exactly two parts: no trailing content, no internal padding
    if len(parts) != 2 or parts[0].lower() != _BEARER or not parts[1]:
        return None, BoundedReason.malformed

    try:
        # The scheme matched case-insensitively; the token bytes are never trimmed or normalized.
        token = parts[1].decode("ascii", "strict")
    except UnicodeDecodeError:
        return None, BoundedReason.malformed
    return token, None
