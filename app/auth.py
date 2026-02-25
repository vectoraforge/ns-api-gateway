import base64
import json

from fastapi import Header, HTTPException


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid token")
    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    raw = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


async def get_user_id(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    try:
        payload = _decode_jwt_payload(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token") from None

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user_id claim")
    return str(user_id)
