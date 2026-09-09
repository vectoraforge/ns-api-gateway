"""JWT verification. `verify` returns `(claims, reason)` rather than raising, and callers rely on that."""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import jwt
import structlog
from jwt import PyJWKClient
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    MissingRequiredClaimError,
    PyJWKClientError,
    PyJWTError,
)
from jwt.types import Options

logger = structlog.get_logger()


# Exactly the closed set spec 11 names, and never a null. The first three separate the three
# populations the invalid_external_jwt spike alert is labelled by -- clients that send nothing,
# clients that send garbage, and an actor forging signatures -- so collapsing them blinds it.
class BoundedReason(StrEnum):
    """Rejection reasons for logs and metric labels; all of them surface the same copy to the client."""
    missing_token = "missing_token"
    malformed = "malformed"
    bad_signature = "bad_signature"
    duplicate_authorization = "duplicate_authorization"
    issuer_mismatch = "issuer_mismatch"
    audience_mismatch = "audience_mismatch"
    expired = "expired"
    empty_subject = "empty_subject"
    # The ninth, and the one no barrier rejection can carry: only a caller that pinned
    # `required_claims` runs the comparison that returns it. The specs close
    # `invalid_external_jwt` over the eight above, and name them as a minimum rather than a
    # total (`00-overview-and-shared-contracts.md`: "including at least").
    required_claim_mismatch = "required_claim_mismatch"


#: The decode rules, module-level so a test double substituting only the key lookup imports them
#: rather than restating them: a copy is what lets production widen while the suite stays green.
#: RS256 alone, so `alg: none` and HS256-over-the-public-key fail before any check runs.
DECODE_ALGORITHMS = ["RS256"]
DEFAULT_LEEWAY = 30
DECODE_OPTIONS: Options = {"require": ["exp", "iat", "aud", "iss", "sub"]}

#: One entry per claim in `require` above. The signature has already verified by the time any of
#: these is raised, so an absent claim carries the label of its present-but-wrong twin.
_MISSING_CLAIM_REASONS = {"sub": BoundedReason.empty_subject,
                          "iss": BoundedReason.issuer_mismatch,
                          "aud": BoundedReason.audience_mismatch,
                          "exp": BoundedReason.expired,
                          "iat": BoundedReason.expired}

#: The negative-cache key an absent, empty, or non-string `kid` is recorded under.
_ABSENT_KID_SENTINEL = ""

#: The one PyJWK failure meaning the key id is bogus. Every other one is an endpoint condition.
_DEFINITIVE_KID_MISS = "Unable to find a signing key that matches"


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub`, never reconstructed from transport metadata."""
    issuer: str
    subject: str
    # Carried only for a caller that pinned required claims; every other caller reads `None`.
    payload: dict | None = None


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
    if isinstance(exc, MissingRequiredClaimError):
        return _MISSING_CLAIM_REASONS.get(exc.claim, BoundedReason.malformed)
    # A token that is not a token: too few segments, an unreadable header or body, bad padding.
    # `InvalidSignatureError` is excluded because it subclasses `DecodeError` and is a real forgery,
    # and `PyJWKClientError` because an unknown key id is not a `DecodeError` at all.
    if isinstance(exc, DecodeError) and not isinstance(exc, InvalidSignatureError):
        return BoundedReason.malformed
    # Everything else: signature failure, algorithm confusion, unknown key id.
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
                 leeway: int = DEFAULT_LEEWAY,
                 cache_ttl_seconds: float = 3600,
                 fetch_timeout_seconds: float = 3.0,
                 unknown_kid_ttl_seconds: float = 60.0,
                 unknown_kid_cache_size: int = 256,
                 required_claims: dict[str, object] | None = None):
        # Explicit `timeout=`: PyJWT defaults to 30 seconds, which would pin a worker on a hang.
        self._jwks_client = PyJWKClient(jwks_url,
                                        cache_jwk_set=True,
                                        lifespan=cache_ttl_seconds,
                                        timeout=fetch_timeout_seconds)
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway
        # Exact expected values, checked after decode: a claim in `require` would refuse a shape change.
        self._required_claims = required_claims
        self._unknown_kid_ttl = unknown_kid_ttl_seconds
        self._unknown_kid_cache_size = unknown_kid_cache_size
        # Key id -> monotonic deadline. Negative only: a positive cache would outlive a pulled key.
        self._unknown_kids: OrderedDict[str, float] = OrderedDict()
        # `verify` runs on the worker threadpool, so an unsynchronized dict would escape as a 500.
        self._cache_lock = threading.Lock()
        # Warm the JWKS cache, and fail fast at startup if the endpoint is unusable.
        # Wrapped so that both callers can guard this constructor on one exception class, each with
        # its own policy: `build_google_push_verifier` answers `None` and costs one route a 503,
        # `build_jwt_verifier` re-raises naming the endpoint and stops the pod.
        # `PyJWKClient.fetch_data` converts `URLError` and `TimeoutError` alone: a 2xx whose body is
        # not JSON leaves a `json.JSONDecodeError`, and one that parses to a non-object leaves an
        # `AttributeError`, neither of which is a `PyJWTError`. Only the class name travels: the
        # message of either embeds the JWKS URL or the body the endpoint answered with.
        try:
            self._jwks_client.get_signing_keys()
        except PyJWTError:
            raise
        except Exception as failure:
            raise PyJWKClientError(f"JWKS warm-up failed: {type(failure).__name__}") from failure

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
            payload = jwt.decode(token,
                                 signing_key,
                                 algorithms=DECODE_ALGORITHMS,
                                 audience=self._audience,
                                 issuer=self._issuer,
                                 leeway=self._leeway,
                                 options=DECODE_OPTIONS)
        except PyJWKClientError as exc:
            # Named here because nothing else can: the bounded reason set is closed at eight values
            # and carries no `jwks_unavailable`, so an outage rejects the whole fleet labelled
            # `bad_signature` and the spike alert reads it as mass forgery. Every `PyJWKClientError`
            # but the key-id miss earns the line, not the connection subclass alone: PyJWT raises
            # the plain class for a reachable endpoint that answered a non-object ("did not return a
            # JSON object") and for one whose set holds no signing key ("did not contain any signing
            # keys") -- a botched rotation and a proxy in the way, and both are the same fleet-wide
            # outage. Only the class name, never the exception text: it embeds the JWKS URL.
            if _DEFINITIVE_KID_MISS not in str(exc):
                logger.error("jwks_endpoint_unusable", failure=type(exc).__name__)
            # A key id this endpoint does not serve is the token's fault, not the endpoint's, so it
            # is the one arm that caches. An outage records no `kid`: caching it would prolong it.
            elif cache_key is not None:
                self._record_unknown(cache_key)
            return None, bounded_reason_for(exc)
        except PyJWTError as exc:
            return None, bounded_reason_for(exc)
        except Exception as failure:
            # What makes "never raises" structural -- an escape would 500 a caller owed a 401.
            # Logged as the same outage, because that is what reaches here: `fetch_data` converts
            # `URLError` and `TimeoutError` alone, so an HTML error page served at 200 arrives as a
            # bare `json.JSONDecodeError` -- the constructor's warm-up wrapper already names it.
            logger.error("jwks_endpoint_unusable", failure=type(failure).__name__)
            return None, BoundedReason.bad_signature

        if self._required_claims is None:
            return claims_from_payload(payload)

        for claim, expected in self._required_claims.items():
            if payload.get(claim) != expected:
                # Its own reason, not `bad_signature`. The answer is `auth_required` either way and
                # the reason is never client-visible, so naming the class of failure discloses
                # nothing -- while collapsing it leaves a mistyped push identity in this
                # deployment's own configuration indistinguishable from a forged token, which is
                # the one distinction `.env.example` promises the operator this field carries.
                return None, BoundedReason.required_claim_mismatch

        claims, reason = claims_from_payload(payload)
        if claims is None:
            return None, reason
        return VerifiedClaims(issuer=claims.issuer, subject=claims.subject, payload=payload), None
