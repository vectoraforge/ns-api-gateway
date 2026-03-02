import base64
import json
import time
from typing import Protocol

from fastapi import Header, Request

from app.exceptions import AuthenticationError


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid token")
    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    raw = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


class TokenVerifier(Protocol):
    def verify(self, token: str) -> str:
        """Decode token and return user_id. Raise AuthenticationError on failure."""
        ...


class JWTVerifier:
    """Base class for JWT verification — Plan 02 provides the full implementation."""

    def verify(self, token: str) -> str:
        raise NotImplementedError


class UnsafeBase64Verifier:
    def verify(self, token: str) -> str:
        try:
            payload = _decode_jwt_payload(token)
        except Exception:
            raise AuthenticationError("Invalid token") from None
        exp = payload.get("exp")
        if exp is not None and exp < time.time():
            raise AuthenticationError("Expired token")
        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationError("Invalid token")
        return str(user_id)


async def get_user_id(request: Request, authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Missing Bearer token")
    verifier: TokenVerifier = request.app.state.verifier
    return verifier.verify(token)
