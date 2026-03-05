import logging
from typing import Protocol

import jwt
from jwt import PyJWKClient

from app.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class TokenVerifier(Protocol):
    def verify(self, token: str) -> str:
        """Decode token and return user identity. Raise AuthenticationError on failure."""
        ...


class JWTVerifier:
    """Verifies RS256-signed JWTs using JWKS-fetched signing keys."""

    def __init__(self, *,
                 jwks_url: str,
                 audience: str,
                 issuer: str,
                 leeway: int = 30,
                 cache_ttl_seconds: float = 3600):
        self._jwks_client = PyJWKClient(jwks_url,
                                        cache_jwk_set=True,
                                        lifespan=cache_ttl_seconds)
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway
        # Warm up JWKS cache — crashes startup if endpoint unreachable (fail-fast)
        self._jwks_client.get_signing_keys()

    def verify(self, token: str) -> str:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(token,
                                 signing_key,
                                 algorithms=["RS256"],
                                 audience=self._audience,
                                 issuer=self._issuer,
                                 leeway=self._leeway,
                                 options={"require": ["exp", "iat", "aud", "iss", "sub"]})
        except Exception as exc:
            logger.warning("Authentication failure: %s", exc)
            raise AuthenticationError(f"Token verification failed: {exc}") from None

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Missing sub claim")
        return str(sub)
