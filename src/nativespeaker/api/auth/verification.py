"""JWT verification. `verify` returns `(claims, reason)` rather than raising, and callers rely on that."""
import threading
import time
from collections import OrderedDict
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
    PyJWKClientError,
    PyJWTError,
)

from nativespeaker.api.auth.wire import BoundedReason

#: The negative-cache key an absent, empty, or non-string `kid` is recorded under.
_ABSENT_KID_SENTINEL = ""

#: The one PyJWK failure meaning the key id is bogus. Every other one is an endpoint condition.
_DEFINITIVE_KID_MISS = "Unable to find a signing key that matches"


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub`, never reconstructed from transport metadata."""
    issuer: str
    subject: str


# A bounded reason is never client-visible: it reaches the security log and nowhere else.
VerificationResult = tuple[VerifiedClaims | None, BoundedReason | None]


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerificationResult:
        """Return `(claims, None)` on acceptance, `(None, reason)` on any failure. Never raises."""
        ...


def bounded_reason_for(exc: PyJWTError) -> BoundedReason:
    """Map one PyJWT failure to one bounded reason. Anything outside PyJWT's taxonomy propagates."""
    if isinstance(exc, InvalidIssuerError):
        return BoundedReason.issuer_mismatch
    if isinstance(exc, InvalidAudienceError):
        return BoundedReason.audience_mismatch
    if isinstance(exc, (ExpiredSignatureError, ImmatureSignatureError)):
        return BoundedReason.expired
    # An absent `sub` is caught by `require`; a present-but-empty one after decode. Same condition.
    if isinstance(exc, MissingRequiredClaimError) and exc.claim == "sub":
        return BoundedReason.empty_subject
    # Everything else: signature failure, algorithm confusion, malformed form, unknown key id.
    return BoundedReason.bad_signature


def claims_from_payload(payload: dict) -> VerificationResult:
    """Turn an already-verified payload into claims, enforcing the non-empty-`sub` rule."""
    subject = payload.get("sub")
    if not subject:
        return None, BoundedReason.empty_subject
    return VerifiedClaims(issuer=str(payload["iss"]), subject=str(subject)), None


class JWTVerifier:
    """Verifies RS256 JWTs with JWKS-fetched keys. It can block, so callers run it off the loop."""

    def __init__(self, *,
                 jwks_url: str,
                 audience: str,
                 issuer: str,
                 leeway: int = 30,
                 cache_ttl_seconds: float = 3600,
                 fetch_timeout_seconds: float = 3.0,
                 unknown_kid_ttl_seconds: float = 60.0,
                 unknown_kid_cache_size: int = 256):
        # Explicit `timeout=`: PyJWT defaults to 30 seconds, which would pin a worker on a hang.
        self._jwks_client = PyJWKClient(jwks_url,
                                        cache_jwk_set=True,
                                        lifespan=cache_ttl_seconds,
                                        timeout=fetch_timeout_seconds)
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway
        self._unknown_kid_ttl = unknown_kid_ttl_seconds
        self._unknown_kid_cache_size = unknown_kid_cache_size
        # Key id -> monotonic deadline. Negative only: a positive cache would outlive a pulled key.
        self._unknown_kids: OrderedDict[str, float] = OrderedDict()
        # `verify` runs on the worker threadpool, so an unsynchronized dict would escape as a 500.
        self._cache_lock = threading.Lock()
        # Warm the JWKS cache, and fail fast at startup if the endpoint is unreachable.
        self._jwks_client.get_signing_keys()

    def _cache_key_for(self, token: str) -> str | None:
        """The negative-cache key for this token's unverified `kid`, or `None` if it is unreadable."""
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except PyJWTError:
            return None
        return kid if isinstance(kid, str) and kid else _ABSENT_KID_SENTINEL

    def _is_known_unknown(self, key: str) -> bool:
        """Whether this key id is a live entry, expiring it in passing if it is not."""
        with self._cache_lock:
            deadline = self._unknown_kids.get(key)
            if deadline is None:
                return False
            if deadline <= time.monotonic():
                del self._unknown_kids[key]
                return False
            return True

    def _record_unknown(self, key: str) -> None:
        """Remember this key id until its deadline, within the cache bound. A TTL of 0 disables it."""
        if self._unknown_kid_ttl <= 0:
            return
        with self._cache_lock:
            now = time.monotonic()
            for expired in [k for k, deadline in self._unknown_kids.items() if deadline <= now]:
                del self._unknown_kids[expired]
            self._unknown_kids[key] = now + self._unknown_kid_ttl
            self._unknown_kids.move_to_end(key)
            while len(self._unknown_kids) > self._unknown_kid_cache_size:
                self._unknown_kids.popitem(last=False)

    def verify(self, token: str) -> VerificationResult:
        # An absent or non-string `kid` shares one sentinel; PyJWT would otherwise refetch for each.
        cache_key = self._cache_key_for(token)
        if cache_key is not None and self._is_known_unknown(cache_key):
            # Exactly what the fetched path yields, so the two are indistinguishable to the client.
            return None, BoundedReason.bad_signature

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            # RS256 alone, so `alg: none` and HS256-over-the-public-key fail before any check runs.
            payload = jwt.decode(token,
                                 signing_key,
                                 algorithms=["RS256"],
                                 audience=self._audience,
                                 issuer=self._issuer,
                                 leeway=self._leeway,
                                 options={"require": ["exp", "iat", "aud", "iss", "sub"]})
        except PyJWKClientError as exc:
            # A connection error records no `kid`: caching an outage would prolong it fleet-wide.
            if cache_key is not None and _DEFINITIVE_KID_MISS in str(exc):
                self._record_unknown(cache_key)
            return None, bounded_reason_for(exc)
        except PyJWTError as exc:
            return None, bounded_reason_for(exc)
        except Exception:
            # What makes "never raises" structural -- an escape would 500 a caller owed a 401.
            return None, BoundedReason.bad_signature

        return claims_from_payload(payload)
