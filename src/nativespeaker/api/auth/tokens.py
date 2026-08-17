from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from nativespeaker.api.exceptions import AuthenticationError


class JwtRejectionReason(StrEnum):
    """Bounded, never client-visible reason carried by an `invalid_external_jwt` rejection.

    The finer detail behind an acceptance failure lives here and nowhere else: this
    classification reaches audit detail fields and metric labels only, never the client."""
    # [impl->req~sessions-acceptance-failure-internal-reason~1]
    missing_token = "missing_token"
    malformed = "malformed"
    duplicate_authorization = "duplicate_authorization"
    bad_signature = "bad_signature"
    issuer_mismatch = "issuer_mismatch"
    audience_mismatch = "audience_mismatch"
    expired = "expired"
    empty_subject = "empty_subject"
    # A Google signing key could not be resolved at all. The enumeration is open-ended ("at
    # least" the eight above), and a key-fetch outage is a systemic backend-verification break
    # rather than a client-side malformed token, so it carries its own bounded reason.
    signing_key_unavailable = "signing_key_unavailable"


class InvalidExternalJwtError(AuthenticationError):
    """Backend rejection of the Bearer Firebase ID token. Surfaces as `auth_required`."""

    def __init__(self, reason: JwtRejectionReason):
        self.reason = reason
        super().__init__("Authentication failed")


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """The only identity material a request may contribute: backend-verified `(iss, sub)`.

    Both values come out of the verifying decode below and are never reconstructed from
    transport metadata."""
    # [impl->req~sessions-wire-claims-from-verifying-decode~1]
    issuer: str
    subject: str


class IdTokenVerifier(Protocol):
    def verify_id_token(self, token: str) -> VerifiedClaims:
        """Cryptographically verify a Firebase ID token. Raise InvalidExternalJwtError otherwise."""
        ...


class CachedGoogleSigningKeys:
    """The cached Google signing keys an RS256 Firebase ID token is verified against. One JWKS
    client per integration, caching the key set for the configured TTL, so the hot path resolves
    a key without an outbound fetch."""

    # [impl->req~shared-verify-id-token~1]
    def __init__(self, *, jwks_url: str, cache_ttl_seconds: float = 3600.0):
        self._client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=cache_ttl_seconds)

    def warm(self) -> None:
        """Fetch the key set once at startup, so a misconfigured JWKS endpoint fails fast."""
        self._client.get_signing_keys()

    def __call__(self, token: str) -> Any:
        return self._client.get_signing_key_from_jwt(token)


class FirebaseIdTokenVerifier:
    """JWKS-backed Firebase ID token verifier: RS256 signature against Google's securetoken
    signing keys, `iss` exactly the configured integration's issuer, `aud` exactly the
    configured Firebase project ID, `exp`/`iat` temporal validity, and a non-empty `sub`.
    Claims are never read without verifying the signature first.

    This is the backend's own verification and the whole of it. It runs in the normal mode,
    without Firebase Admin's optional `checkRevoked`: no per-request revocation check and no
    Admin round-trip happens here, so an already-minted ID token stays valid until its own
    `exp`. Firebase ID tokens carry no `azp` and no `nbf` claim, so no rule is written on
    either: a check on them would test values the accepted token class never carries."""

    # [impl->req~sessions-backend-sole-jwt-verifier~1]
    # [impl->req~sessions-no-check-revoked~1]
    # [impl->req~sessions-no-azp-nbf-rules~1]

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
        # The signing key is resolved from the cached Google key set outside the decode below:
        # a key-fetch outage is a systemic backend-verification break and must not be recorded
        # and counted as a client-side `malformed` token.
        # [impl->req~shared-verify-id-token~1]
        try:
            signing_key = self._key_resolver(token)
        except InvalidExternalJwtError:
            raise
        except Exception:
            raise InvalidExternalJwtError(JwtRejectionReason.signing_key_unavailable) from None
        # One verifying decode does the whole acceptance policy, and any branch of it failing —
        # bad signature, wrong `iss`, wrong `aud`, expired, unparseable — rejects the request.
        # [impl->req~shared-verify-id-token~1]
        # [impl->req~sessions-iss-must-equal-configured-issuer~1]
        # [impl->req~sessions-any-verification-failure-rejects~1]
        # [impl->req~sessions-wire-claims-from-verifying-decode~1]
        try:
            claims = jwt.decode(token,
                                signing_key,
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
