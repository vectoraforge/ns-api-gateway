"""JWT verification against the one configured Firebase integration (spec 01-foundation.md §1.2).

`verify` **returns** `(claims, reason)` instead of raising. The barrier is a pure-ASGI middleware
installed with `add_middleware`, which places it outside Starlette's `ExceptionMiddleware`: an
exception raised at this seam would bypass every registered handler and surface as a 500 rather
than as `auth_required` (D-01).

Anti-oracle: every acceptance-failure branch yields the identical `auth_required` response. The
bounded reason lives only in the audit row's `details.failure` and in metric labels -- it is never
client-visible, and it never names the issuer, the integration, or the failed check.
"""
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
#:
#: It cannot collide with a real key id by construction rather than by convention: the only other
#: branch that writes a key requires a non-empty `str`, so the empty-string key is unreachable from
#: it. PyJWT reads `kid` off the *unverified* header, so this key is attacker-influenced -- which is
#: why nothing but a deadline is ever stored against it.
_ABSENT_KID_SENTINEL = ""

#: The one PyJWK failure that actually means "this key id is bogus".
#:
#: PyJWT raises it only after a *successful* refresh still failed to match. Every other
#: `PyJWKClientError` -- connection failure, an empty `keys` list, a non-JSON document -- is an
#: *endpoint* condition. Caching those against a key id that every legitimate token shares would
#: reject the whole fleet for the TTL, and keep rejecting it after the endpoint recovered.
_DEFINITIVE_KID_MISS = "Unable to find a signing key that matches"


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

    Synchronous by design, and called through a threadpool at the barrier. `verify` must *return*
    rather than raise (D-01), which an `async def` would not change -- but it can block on a JWKS
    fetch, so `AuthBarrierMiddleware` awaits it through `starlette.concurrency.run_in_threadpool`
    rather than calling it inline. Do not re-introduce the direct call: it puts a blocking outbound
    round trip, chosen by an unauthenticated caller, on the loop that also serves `/health/ready`.
    """

    def __init__(self, *,
                 jwks_url: str,
                 audience: str,
                 issuer: str,
                 leeway: int = 30,
                 cache_ttl_seconds: float = 3600,
                 fetch_timeout_seconds: float = 3.0,
                 unknown_kid_ttl_seconds: float = 60.0,
                 unknown_kid_cache_size: int = 256):
        # `timeout=` is explicit because PyJWT 2.12.1 defaults it to 30 seconds. That default is the
        # operative bound on a blocking `urlopen`, so a hung endpoint would pin a worker for half a
        # minute per request; three seconds frees it while leaving ample room for a healthy fetch.
        self._jwks_client = PyJWKClient(jwks_url,
                                        cache_jwk_set=True,
                                        lifespan=cache_ttl_seconds,
                                        timeout=fetch_timeout_seconds)
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway
        self._unknown_kid_ttl = unknown_kid_ttl_seconds
        self._unknown_kid_cache_size = unknown_kid_cache_size
        # Key id -> monotonic deadline. Negative only: no signing key, no claim set, no admission
        # decision. A positive cache here would keep a rotated or withdrawn key working past its own
        # lifetime, so the value is a deadline and nothing else is ever stored.
        self._unknown_kids: OrderedDict[str, float] = OrderedDict()
        # `verify` runs on the anyio worker threadpool, so every reader and writer of
        # `_unknown_kids` is a different OS thread. An unsynchronized `OrderedDict` raises
        # `RuntimeError: OrderedDict mutated during iteration` under that concurrency, and neither
        # that nor the check-then-`del` `KeyError` is a `PyJWTError` -- so both would escape
        # `verify`, escape `run_in_threadpool`, and reach a barrier that catches nothing, turning an
        # unauthenticated caller's 401 into a 500. The lock is held only for dict bookkeeping;
        # nothing under it blocks, so no fetch ever serializes behind it.
        self._cache_lock = threading.Lock()
        # Warm up JWKS cache — crashes startup if endpoint unreachable (fail-fast), and under the
        # same bound, which is the intent. The set is cached for `cache_ttl_seconds`, so a
        # *recognized* key id costs one local RSA verification and no outbound request. An
        # unrecognized one costs at most one bounded, off-loop fetch for the life of its
        # negative-cache entry, and none at all while that entry is live.
        self._jwks_client.get_signing_keys()

    def _cache_key_for(self, token: str) -> str | None:
        """The negative-cache key for this token's unverified `kid`, or `None` if unreadable.

        A malformed compact form is left to the normal path: `verify` never raises, for the same
        D-01 reason the barrier never raises, and a token whose header cannot be parsed has no key
        id to remember.
        """
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except PyJWTError:
            return None
        return kid if isinstance(kid, str) and kid else _ABSENT_KID_SENTINEL

    def _is_known_unknown(self, key: str) -> bool:
        """Whether this key id is a live entry -- expiring it in passing if it is not.

        Under `_cache_lock`: the expiring `del` is a check-then-act that two threads would otherwise
        race into a `KeyError`.
        """
        with self._cache_lock:
            deadline = self._unknown_kids.get(key)
            if deadline is None:
                return False
            if deadline <= time.monotonic():
                del self._unknown_kids[key]
                return False
            return True

    def _record_unknown(self, key: str) -> None:
        """Remember this key id until its deadline, keeping the cache within its bound.

        A TTL of 0 disables the cache outright, honestly rather than as a special case: nothing is
        recorded, so every repeat takes the fetch path exactly as it did before this cache existed.

        Under `_cache_lock`: the sweep iterates the dict while the writes below mutate it.
        """
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
        # The unverified `kid` is attacker-chosen and reaches an outbound network decision before
        # any identity work happens, so it is read here only to answer "have I already failed to
        # match this one?". PyJWT keeps only candidates with a truthy `key_id`, so an absent or
        # empty `kid` can never match and `get_signing_key` always falls through to
        # `get_signing_keys(refresh=True)` -- which bypasses the JWK-set TTL cache and fetches for
        # real, every time. Uncached, omitting one header field is an unbounded per-request fetch on
        # the authentication hot path; hence the shared sentinel rather than skipping the cache.
        # Caching that rejection is sound as well as necessary: a keyless token can never verify.
        cache_key = self._cache_key_for(token)
        if cache_key is not None and self._is_known_unknown(cache_key):
            # Exactly what the fetched path yields for an unmatched key id, so the two are
            # indistinguishable to the client, to telemetry, and to the audit `details.failure`.
            return None, BoundedReason.bad_signature

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
        except PyJWKClientError as exc:
            # Record only the definitive "refreshed, and still no match" case. Testing for that one
            # message is narrower than excluding `PyJWKClientConnectionError`: an empty `keys` list
            # and a non-JSON document are plain `PyJWKClientError`s too, and both are *endpoint*
            # conditions. Caching either against the one or two key ids the whole fleet shares would
            # reject every legitimate token for the TTL -- the outage amplifier this branch exists to
            # avoid. The rule covers the sentinel path unchanged: when the endpoint is degraded, the
            # very refresh an absent `kid` forces is what raises the endpoint variant.
            if cache_key is not None and _DEFINITIVE_KID_MISS in str(exc):
                self._record_unknown(cache_key)
            return None, bounded_reason_for(exc)
        except PyJWTError as exc:
            return None, bounded_reason_for(exc)
        except Exception:
            # `verify` never raises (D-01), and the two clauses above do not make that structural:
            # PyJWT wraps neither `json.JSONDecodeError` from a non-JSON JWKS body nor anything a
            # future dependency invents. An escape here bypasses every registered handler and lands
            # a 500 on a caller owed `auth_required`, so the contract is closed here rather than
            # asserted in the docstring. Indistinguishable from any other rejection to the client;
            # the audit row's `details.failure` carries the bounded reason as always.
            return None, BoundedReason.bad_signature

        return claims_from_payload(payload)
