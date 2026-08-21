"""JWT verification against the one configured Firebase integration (spec 01-foundation.md §1.2).

`verify` **returns** `(claims, reason)` instead of raising. The barrier is a pure-ASGI middleware
installed with `add_middleware`, which places it outside Starlette's `ExceptionMiddleware`: an
exception raised at this seam would bypass every registered handler and surface as a 500 rather
than as `auth_required` (D-01).

Anti-oracle: every acceptance-failure branch yields the identical `auth_required` response. The
bounded reason lives only in the audit row's `details.failure` and in metric labels -- it is never
client-visible, and it never names the issuer, the integration, or the failed check.
"""
from dataclasses import dataclass
from typing import Protocol

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    MissingRequiredClaimError,
    PyJWTError,
)

from nativespeaker.api.auth.wire import BoundedReason


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub` -- §1.2.

    The v1.6 `UserIdentity` also carried `email` and `name` read off the token. §1.2 and
    SHARED-INVARIANTS both forbid deriving identity or classification from claims, so those fields
    do not survive the move. These two are never reconstructed from transport metadata.
    """
    issuer: str
    subject: str


VerificationResult = tuple[VerifiedClaims | None, BoundedReason | None]


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerificationResult:
        """Return `(claims, None)` on acceptance, `(None, reason)` on any failure. Never raises."""
        ...


def bounded_reason_for(exc: PyJWTError) -> BoundedReason:
    """Map one PyJWT failure to exactly one §1.2 bounded reason.

    Only PyJWT's own taxonomy is mapped. Anything outside it propagates, so a genuinely new
    failure mode surfaces loudly instead of being silently labelled a bad signature.
    """
    if isinstance(exc, InvalidIssuerError):
        return BoundedReason.issuer_mismatch
    if isinstance(exc, InvalidAudienceError):
        return BoundedReason.audience_mismatch
    if isinstance(exc, (ExpiredSignatureError, ImmatureSignatureError)):
        return BoundedReason.expired
    # An absent `sub` is caught by the `require` list before the payload is ever returned; a
    # present-but-empty one is caught after decode. Both are the same condition.
    if isinstance(exc, MissingRequiredClaimError) and exc.claim == "sub":
        return BoundedReason.empty_subject
    # Everything else PyJWT raises -- signature failure, algorithm confusion, malformed compact
    # form, unknown key id, any other missing required claim.
    return BoundedReason.bad_signature


def claims_from_payload(payload: dict) -> VerificationResult:
    """Turn an already-verified payload into claims, enforcing the non-empty-`sub` rule.

    Split out so the production verifier and the fixed-key test verifier share one implementation
    of the post-decode rules rather than drifting apart.
    """
    subject = payload.get("sub")
    if not subject:
        return None, BoundedReason.empty_subject
    return VerifiedClaims(issuer=str(payload["iss"]), subject=str(subject)), None


class JWTVerifier:
    """Verifies RS256-signed JWTs using JWKS-fetched signing keys.

    Exactly one Firebase integration, selected by issuer equality against the configured
    `JWTConfig.issuer`. No ambient, default, global, or fallback client exists or is constructible,
    and an issuer mismatch rejects here -- before any Admin client selection or Admin lookup.

    `checkRevoked` is deliberately absent: SHARED-INVARIANTS forbids a per-request revocation check
    in every phase, so an already-minted ID token stays valid until its own `exp`.
    """

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
        # Warm up JWKS cache — crashes startup if endpoint unreachable (fail-fast). The set is
        # cached for `cache_ttl_seconds`, so a request costs one local RSA verification and no
        # per-request network call.
        self._jwks_client.get_signing_keys()

    def verify(self, token: str) -> VerificationResult:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            # `algorithms` is passed explicitly and lists RS256 alone, so an `alg: none` token and
            # an HS256-over-the-public-key token both fail before any signature check runs.
            payload = jwt.decode(token,
                                 signing_key,
                                 algorithms=["RS256"],
                                 audience=self._audience,
                                 issuer=self._issuer,
                                 leeway=self._leeway,
                                 options={"require": ["exp", "iat", "aud", "iss", "sub"]})
        except PyJWTError as exc:
            return None, bounded_reason_for(exc)

        return claims_from_payload(payload)
