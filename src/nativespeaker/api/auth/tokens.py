from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from nativespeaker.api.exceptions import AuthenticationError


class JwtRejectionReason(StrEnum):
    """Bounded, never client-visible reason carried by an `invalid_external_jwt` rejection."""
    missing_token = "missing_token"
    malformed = "malformed"
    duplicate_authorization = "duplicate_authorization"
    bad_signature = "bad_signature"
    issuer_mismatch = "issuer_mismatch"
    audience_mismatch = "audience_mismatch"
    expired = "expired"
    empty_subject = "empty_subject"


class InvalidExternalJwtError(AuthenticationError):
    """Backend rejection of the Bearer Firebase ID token. Surfaces as `auth_required`."""

    def __init__(self, reason: JwtRejectionReason):
        self.reason = reason
        super().__init__("Authentication failed")


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """The only identity material a request may contribute: backend-verified `(iss, sub)`."""
    issuer: str
    subject: str


class IdTokenVerifier(Protocol):
    def verify_id_token(self, token: str) -> VerifiedClaims:
        """Cryptographically verify a Firebase ID token. Raise InvalidExternalJwtError otherwise."""
        ...


class FirebaseIdTokenVerifier:
    """JWKS-backed Firebase ID token verifier: RS256 signature, exact issuer and audience,
    temporal validity, non-empty subject. Claims are never read without verification."""

    def __init__(self, *,
                 issuer: str,
                 audience: str,
                 key_resolver: Callable[[str], Any],
                 leeway: int = 30):
        self._issuer = issuer
        self._audience = audience
        self._key_resolver = key_resolver
        self._leeway = leeway

    def verify_id_token(self, token: str) -> VerifiedClaims:
        if not token:
            raise InvalidExternalJwtError(JwtRejectionReason.missing_token)
        # [impl->req~shared-verify-id-token~1]
        try:
            claims = jwt.decode(token,
                                self._key_resolver(token),
                                algorithms=["RS256"],
                                audience=self._audience,
                                issuer=self._issuer,
                                leeway=self._leeway,
                                options={"require": ["exp", "iat", "aud", "iss", "sub"],
                                         "verify_signature": True})
        except jwt.ExpiredSignatureError:
            raise InvalidExternalJwtError(JwtRejectionReason.expired) from None
        except jwt.InvalidIssuerError:
            raise InvalidExternalJwtError(JwtRejectionReason.issuer_mismatch) from None
        except jwt.InvalidAudienceError:
            raise InvalidExternalJwtError(JwtRejectionReason.audience_mismatch) from None
        except jwt.InvalidSignatureError:
            raise InvalidExternalJwtError(JwtRejectionReason.bad_signature) from None
        except Exception:
            raise InvalidExternalJwtError(JwtRejectionReason.malformed) from None

        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise InvalidExternalJwtError(JwtRejectionReason.empty_subject)
        # Issuer is taken from the verified claims, which `jwt.decode` already pinned to
        # the configured integration's issuer by exact equality.
        return VerifiedClaims(issuer=str(claims["iss"]), subject=subject)


@dataclass(frozen=True, slots=True)
class UserIdentity:
    sub: str
    email: str
    name: str | None = None


class TokenVerifier(Protocol):
    def verify(self, token: str) -> UserIdentity:
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

    def verify(self, token: str) -> UserIdentity:
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
            raise AuthenticationError(f"Token verification failed: {exc}") from None

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Missing sub claim")
        return UserIdentity(
            sub=str(sub),
            email=payload.get("email", ""),
            name=payload.get("name"),
        )
