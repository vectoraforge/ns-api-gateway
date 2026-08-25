"""§1.2 JWT verification rules: acceptance, bounded-reason rejection, and the anti-oracle shape.

Every rejection branch returns `(None, BoundedReason.<member>)` rather than raising. The bounded
reason is the only thing distinguishing one acceptance failure from another -- every one of them
answers the client with the identical `auth_required` -- so it has to reach the security log as a
*value*, which is what returning it buys and raising would not.
"""

import threading
import time
from unittest.mock import patch
from urllib.error import URLError

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from nativespeaker.api.auth.verification import _ABSENT_KID_SENTINEL, JWTVerifier, VerifiedClaims
from nativespeaker.api.auth.wire import BoundedReason
from unit.conftest import (
    PRIVATE_KEY_PEM,
    PUBLIC_KEY_PEM,
    TEST_ISSUER,
    TEST_PROJECT_ID,
    make_test_verifier,
    make_token,
)
from unit.test_jwks_offload import (
    JWKS_URL,
    KNOWN_KID,
    install_counted_transport,
    jwks_body,
)


@pytest.fixture
def verifier():
    return make_test_verifier()


def hs256_over(secret: bytes, payload: dict) -> str:
    """Hand-build an HS256 token keyed on `secret`.

    PyJWT refuses to *encode* HS256 with a PEM key, so the classic confusion attack cannot be
    expressed through `pyjwt.encode`. An attacker has no such guard -- they emit the compact form
    directly, which is what this reproduces.
    """
    import base64
    import hashlib
    import hmac
    import json

    def seg(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    signing_input = seg(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()) + b"." + \
        seg(json.dumps(payload).encode())
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + seg(signature)).decode()


def rejected(verifier, token) -> BoundedReason:
    """Assert the two-tuple rejection shape and return the single bounded reason."""
    claims, reason = verifier.verify(token)
    assert claims is None, "a rejected token must yield no claims"
    assert reason is not None, "a rejected token must yield exactly one bounded reason"
    return reason


def accepted(verifier, token) -> VerifiedClaims:
    """Assert the two-tuple acceptance shape and return the claims."""
    claims, reason = verifier.verify(token)
    assert reason is None, f"an accepted token must carry no bounded reason, got {reason}"
    assert claims is not None
    return claims


class TestAlgorithmSecurity:
    def test_rejects_alg_none(self, verifier):
        """AUTH-07: alg:none tokens must be rejected."""
        payload = {
            "sub": "user1",
            "aud": TEST_PROJECT_ID,
            "iss": TEST_ISSUER,
            "exp": time.time() + 3600,
            "iat": time.time(),
            "email_verified": True,
        }
        token = pyjwt.encode(payload, None, algorithm="none")  # type: ignore[invalid-argument-type]
        assert rejected(verifier, token) is BoundedReason.bad_signature

    def test_rejects_hs256_token(self, verifier):
        """HS256-signed tokens must be rejected (only RS256 accepted)."""
        payload = {
            "sub": "user1",
            "aud": TEST_PROJECT_ID,
            "iss": TEST_ISSUER,
            "exp": time.time() + 3600,
            "iat": time.time(),
            "email_verified": True,
        }
        token = pyjwt.encode(payload, "secret-key", algorithm="HS256")
        assert rejected(verifier, token) is BoundedReason.bad_signature

    def test_rejects_hs256_signed_with_the_public_key(self, verifier):
        """The classic confusion attack: HS256 keyed on the RSA public key."""
        payload = {
            "sub": "user1",
            "aud": TEST_PROJECT_ID,
            "iss": TEST_ISSUER,
            "exp": time.time() + 3600,
            "iat": time.time(),
        }
        token = hs256_over(PUBLIC_KEY_PEM, payload)
        assert rejected(verifier, token) is BoundedReason.bad_signature


class TestSignatureVerification:
    def test_rejects_tampered_payload(self, verifier):
        """Token with modified payload after signing must be rejected."""
        token = make_token("user1")
        parts = token.split(".")
        # Tamper with the payload
        import base64
        import json

        payload_bytes = base64.urlsafe_b64decode(parts[1] + "==")
        payload_data = json.loads(payload_bytes)
        payload_data["sub"] = "attacker"
        tampered_payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=").decode()
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
        assert rejected(verifier, tampered_token) is BoundedReason.bad_signature

    def test_rejects_token_signed_with_different_key(self, verifier):
        """Token signed with an unknown private key must be rejected."""
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(encoding=serialization.Encoding.PEM,
                                            format=serialization.PrivateFormat.PKCS8,
                                            encryption_algorithm=serialization.NoEncryption())
        token = make_token("user1", private_key=other_pem)
        assert rejected(verifier, token) is BoundedReason.bad_signature


class TestTokenExpiry:
    def test_rejects_expired_token(self, verifier):
        token = make_token("user1", exp=time.time() - 3600)
        assert rejected(verifier, token) is BoundedReason.expired

    def test_accepts_token_within_leeway(self, verifier):
        """Token expired <30s ago should still be accepted (leeway=30)."""
        token = make_token("user1", exp=time.time() - 10)
        assert accepted(verifier, token).subject == "user1"

    def test_rejects_token_past_leeway(self, verifier):
        """Token expired >30s ago must be rejected."""
        token = make_token("user1", exp=time.time() - 60)
        assert rejected(verifier, token) is BoundedReason.expired


class TestClaimValidation:
    def test_rejects_wrong_audience(self, verifier):
        token = make_token("user1", aud="wrong-project")
        assert rejected(verifier, token) is BoundedReason.audience_mismatch

    def test_rejects_wrong_issuer(self, verifier):
        token = make_token("user1", iss="https://evil.example.com")
        assert rejected(verifier, token) is BoundedReason.issuer_mismatch

    def test_rejects_missing_sub(self, verifier):
        """Token without sub claim must be rejected."""
        now = time.time()
        payload = {
            "aud": TEST_PROJECT_ID,
            "iss": TEST_ISSUER,
            "exp": now + 3600,
            "iat": now,
            "email_verified": True,
        }
        token = pyjwt.encode(payload, PRIVATE_KEY_PEM, algorithm="RS256")
        assert rejected(verifier, token) is BoundedReason.empty_subject

    def test_rejects_empty_sub(self, verifier):
        """A present but empty sub is the same condition as an absent one."""
        token = make_token("")
        assert rejected(verifier, token) is BoundedReason.empty_subject

    def test_rejects_missing_exp(self, verifier):
        """Token without exp claim must be rejected."""
        now = time.time()
        payload = {
            "sub": "user1",
            "aud": TEST_PROJECT_ID,
            "iss": TEST_ISSUER,
            "iat": now,
            "email_verified": True,
        }
        token = pyjwt.encode(payload, PRIVATE_KEY_PEM, algorithm="RS256", headers={"alg": "RS256"})
        assert rejected(verifier, token) is BoundedReason.bad_signature

    def test_rejects_missing_iat(self, verifier):
        """Token without iat claim must be rejected."""
        now = time.time()
        payload = {
            "sub": "user1",
            "aud": TEST_PROJECT_ID,
            "iss": TEST_ISSUER,
            "exp": now + 3600,
            "email_verified": True,
        }
        token = pyjwt.encode(payload, PRIVATE_KEY_PEM, algorithm="RS256")
        assert rejected(verifier, token) is BoundedReason.bad_signature


class TestMalformedTokens:
    def test_rejects_empty_string(self, verifier):
        assert rejected(verifier, "") is BoundedReason.bad_signature

    def test_rejects_garbage(self, verifier):
        assert rejected(verifier, "not.a.jwt.at.all") is BoundedReason.bad_signature

    def test_rejects_just_dots(self, verifier):
        assert rejected(verifier, "...") is BoundedReason.bad_signature


class TestCrossUserIsolation:
    def test_different_sub_returns_different_user(self, verifier):
        assert accepted(verifier, make_token("user-a")).subject == "user-a"
        assert accepted(verifier, make_token("user-b")).subject == "user-b"

    def test_sub_is_returned_as_string(self, verifier):
        assert accepted(verifier, make_token("12345")).subject == "12345"


class TestValidToken:
    def test_accepts_valid_token(self, verifier):
        assert accepted(verifier, make_token("user1")).subject == "user1"

    def test_accepts_token_with_extra_claims(self, verifier):
        """Extra claims are ignored -- token is still valid."""
        token = make_token("user1", extra_claims={"custom": "value", "firebase": {"sign_in_provider": "google.com"}})
        assert accepted(verifier, token).subject == "user1"

    def test_issuer_is_the_verified_iss(self, verifier):
        """`issuer` is exactly the verified `iss`, never reconstructed from transport metadata."""
        assert accepted(verifier, make_token("user1")).issuer == TEST_ISSUER


class TestVerifiedClaims:
    """§1.2: the accepted value object carries the verified (iss, sub) and nothing else."""

    def test_carries_exactly_issuer_and_subject(self):
        assert sorted(VerifiedClaims.__dataclass_fields__) == ["issuer", "subject"]

    def test_fields(self):
        claims = VerifiedClaims(issuer=TEST_ISSUER, subject="abc123")
        assert claims.issuer == TEST_ISSUER
        assert claims.subject == "abc123"

    def test_frozen(self):
        claims = VerifiedClaims(issuer=TEST_ISSUER, subject="abc123")
        with pytest.raises(AttributeError):
            claims.subject = "changed"  # type: ignore[invalid-assignment]

    def test_carries_no_email_or_name(self):
        """§1.2 and SHARED-INVARIANTS forbid deriving identity or classification from claims."""
        claims = VerifiedClaims(issuer=TEST_ISSUER, subject="abc123")
        assert not hasattr(claims, "email")
        assert not hasattr(claims, "name")


class TestAntiOracle:
    """§1.2: every acceptance-failure branch is shaped identically and none raises."""

    @pytest.mark.parametrize("name,builder", [
        ("wrong_issuer", lambda: make_token("u", iss="https://evil.example.com")),
        ("wrong_audience", lambda: make_token("u", aud="wrong-project")),
        ("expired", lambda: make_token("u", exp=time.time() - 3600)),
        ("empty_subject", lambda: make_token("")),
        ("bad_signature", lambda: "not.a.jwt.at.all"),
    ])
    def test_every_failure_returns_the_same_two_tuple_shape(self, verifier, name, builder):
        result = verifier.verify(builder())
        assert isinstance(result, tuple)
        assert len(result) == 2
        claims, reason = result
        assert claims is None
        assert isinstance(reason, BoundedReason)

    def test_reason_is_never_carried_alongside_claims(self, verifier):
        """Exactly one of the two slots is populated -- never both, never neither."""
        for token in (make_token("u"), "garbage", make_token("u", aud="nope")):
            claims, reason = verifier.verify(token)
            assert (claims is None) != (reason is None)


class TestProductionVerifier:
    """The §1.2 claim rules against the real `JWTVerifier`, with the JWKS client substituted.

    Substituting the client is legitimate isolation *here*: every case below is about issuer,
    audience, algorithm or subject, and where the key came from is irrelevant to all four. It is
    illegitimate for a case about fetch counts, which is why the one that used to live here was
    deleted rather than repaired -- `get_signing_keys.call_count == 0` held whatever the production
    code did, because `verify()` calls `get_signing_key_from_jwt` instead (WR-05). Fetch counts now
    live in `TestTheJwksTransportIsNotHitPerRequest`, measured at the transport under a real client.
    """

    @pytest.fixture
    def jwks_client(self):
        with patch("nativespeaker.api.auth.verification.PyJWKClient") as mock_cls:
            instance = mock_cls.return_value
            instance.get_signing_keys.return_value = []
            instance.get_signing_key_from_jwt.return_value = PUBLIC_KEY_PEM
            yield mock_cls, instance

    @pytest.fixture
    def real_verifier(self, jwks_client):
        _, instance = jwks_client
        verifier = JWTVerifier(jwks_url="https://jwks.invalid/keys",
                               audience=TEST_PROJECT_ID,
                               issuer=TEST_ISSUER)
        instance.get_signing_keys.reset_mock()
        return verifier

    def test_constructs_a_caching_client_and_warms_it_up(self, jwks_client):
        mock_cls, instance = jwks_client
        JWTVerifier(jwks_url="https://jwks.invalid/keys",
                    audience=TEST_PROJECT_ID,
                    issuer=TEST_ISSUER,
                    cache_ttl_seconds=1234,
                    fetch_timeout_seconds=2.5)
        mock_cls.assert_called_once_with("https://jwks.invalid/keys",
                                         cache_jwk_set=True,
                                         lifespan=1234,
                                         timeout=2.5)
        # Fail-fast warm-up: an unreachable JWKS endpoint crashes startup, not the first request.
        instance.get_signing_keys.assert_called_once_with()

    def test_the_default_fetch_timeout_is_bounded(self, jwks_client):
        """The bound has to hold for the call site that passes nothing -- which is the real one.

        `app/lifespan.py` constructs the verifier without the keyword, so pinning only the explicit
        value would leave production on PyJWT 2.12.1's 30-second default with a green test beside it.
        """
        mock_cls, _ = jwks_client
        JWTVerifier(jwks_url="https://jwks.invalid/keys",
                    audience=TEST_PROJECT_ID,
                    issuer=TEST_ISSUER)
        timeout = mock_cls.call_args.kwargs["timeout"]
        assert timeout is not None and timeout <= 5

    def test_rejects_hs256_over_the_public_key(self, real_verifier):
        """`algorithms=["RS256"]` is passed explicitly, so confusion lands on bad_signature."""
        payload = {"sub": "u", "aud": TEST_PROJECT_ID, "iss": TEST_ISSUER,
                   "exp": time.time() + 3600, "iat": time.time()}
        token = hs256_over(PUBLIC_KEY_PEM, payload)
        assert rejected(real_verifier, token) is BoundedReason.bad_signature

    def test_pins_the_issuer_to_the_one_configured_integration(self, real_verifier):
        token = make_token("u", iss="https://securetoken.google.com/other-project")
        assert rejected(real_verifier, token) is BoundedReason.issuer_mismatch

    def test_pins_the_audience_to_the_configured_project_id(self, real_verifier):
        token = make_token("u", aud="other-project")
        assert rejected(real_verifier, token) is BoundedReason.audience_mismatch

    def test_requires_a_non_empty_subject(self, real_verifier):
        assert rejected(real_verifier, make_token("")) is BoundedReason.empty_subject


class TestTheJwksTransportIsNotHitPerRequest:
    """Fetch counts, measured at the transport under a **real** `PyJWKClient`.

    This class replaces the deleted `TestProductionVerifier` fetch-count case, which counted calls
    to a method the code under test never invoked, on a client class that had been substituted
    wholesale -- an assertion that held whatever the production code did (WR-05). The seam here is
    `urllib.request.urlopen`, the one blocking call `PyJWKClient.fetch_data` makes, so every fetch
    the real path performs is counted and none can hide.

    Two cases exist to keep the rest honest.
    `test_with_the_negative_cache_disabled_each_repeat_costs_a_fetch` shows the harness registering
    real fetches, so a zero is evidence rather than an artefact; and
    `test_distinct_unknown_kids_still_cost_one_fetch_each` states the residual this fix deliberately
    accepts (T-35-12-03) somewhere a later phase will find it.
    """

    @pytest.fixture
    def counted_transport(self, monkeypatch):
        return install_counted_transport(monkeypatch)

    def build(self, **kwargs) -> JWTVerifier:
        return JWTVerifier(jwks_url=JWKS_URL, audience=TEST_PROJECT_ID, issuer=TEST_ISSUER,
                           **kwargs)

    def test_the_constructor_fetch_carries_a_bounded_timeout(self, counted_transport):
        """T-35-12-02: the bound is observed on the wire, not read off the constructor."""
        self.build()
        assert len(counted_transport) == 1, "the warm-up is exactly one fetch"
        assert all(t is not None and t <= 5 for t in counted_transport.timeouts), \
            f"PyJWT's 30s default is the operative bound: {counted_transport.timeouts}"

    def test_a_repeated_unknown_kid_costs_one_fetch_not_one_per_request(self, counted_transport):
        """The gap statement's item (c): *repeated*, not distinct."""
        verifier = self.build()
        counted_transport.timeouts.clear()
        for _ in range(5):
            assert rejected(verifier, make_token("u", headers={"kid": "unknown-1"})) \
                is BoundedReason.bad_signature
        assert len(counted_transport) == 1

    def test_with_the_negative_cache_disabled_each_repeat_costs_a_fetch(self, counted_transport):
        """The control. Without it, the case above is a zero nobody has shown can be non-zero."""
        verifier = self.build(unknown_kid_ttl_seconds=0)
        counted_transport.timeouts.clear()
        for _ in range(5):
            rejected(verifier, make_token("u", headers={"kid": "unknown-1"}))
        assert len(counted_transport) == 5

    def test_distinct_unknown_kids_still_cost_one_fetch_each(self, counted_transport):
        """T-35-12-03, pinned rather than assumed away: the per-`kid` cache caps repeats, not spread.

        Accepted because Envoy rate-limits by IP, user and URL, and because T-35-12-01 removes the
        reason rate limiting could not help -- the fetch no longer blocks the loop. A global refresh
        cooldown would cap this too, at the price of delaying a legitimate key rotation.
        """
        verifier = self.build()
        counted_transport.timeouts.clear()
        for i in range(5):
            rejected(verifier, make_token("u", headers={"kid": f"unknown-{i}"}))
        assert len(counted_transport) == 5

    def test_a_cached_rejection_is_indistinguishable_from_a_fetched_one(self, counted_transport):
        """T-35-12-06: the cache-hit path yields the same bounded reason as the fetched path."""
        verifier = self.build()
        token = make_token("u", headers={"kid": "unknown-1"})
        counted_transport.timeouts.clear()

        fetched = verifier.verify(token)
        assert len(counted_transport) == 1, "the first verification really did fetch"
        cached = verifier.verify(token)
        assert len(counted_transport) == 1, "the second really did not"

        assert fetched == cached == (None, BoundedReason.bad_signature)

    def test_a_jwks_connection_failure_does_not_mark_the_kid_unknown(self, counted_transport):
        """T-35-12-04: an outage must not become a longer self-inflicted authentication outage.

        `PyJWKClientConnectionError` says the *endpoint* was unreachable, not that the key id is
        bogus. Recording it would reject legitimate tokens for the whole TTL after recovery -- the
        difference between a cache and an outage amplifier.
        """
        verifier = self.build()
        rotated_kid = "rotated-key-2"
        token = make_token("u", headers={"kid": rotated_kid})

        counted_transport.error = URLError("jwks endpoint unreachable")
        assert rejected(verifier, token) is BoundedReason.bad_signature

        # The endpoint recovers, now publishing the rotated key.
        counted_transport.error = None
        counted_transport.body = jwks_body(rotated_kid)
        assert accepted(verifier, token).subject == "u", \
            "the outage poisoned the negative cache: the recovered kid is still rejected"

    def test_repeated_absent_kids_share_one_sentinel_entry_and_one_fetch(self, counted_transport):
        """FOUND-02/empty: omitting one header field must not buy an unbounded per-request fetch.

        `get_signing_keys` keeps only keys with a truthy `key_id`, so a `None` `kid` can never match
        a candidate and `get_signing_key` always falls through to `get_signing_keys(refresh=True)`,
        which bypasses the JWK-set TTL cache. Uncached, that is one real fetch per request forever,
        reachable by leaving `kid` out.
        """
        verifier = self.build()
        counted_transport.timeouts.clear()
        for _ in range(5):
            assert rejected(verifier, make_token("u")) is BoundedReason.bad_signature
        assert len(counted_transport) == 1

        cache = verifier._unknown_kids
        assert len(cache) == 1
        assert list(cache) == [_ABSENT_KID_SENTINEL]
        assert None not in cache, "an absent kid keys on the sentinel, never on None"

    def test_repeated_absent_kids_cost_a_fetch_each_with_the_cache_disabled(self, counted_transport):
        """The sentinel's own control, at the same seam as the repeated-`kid` one."""
        verifier = self.build(unknown_kid_ttl_seconds=0)
        counted_transport.timeouts.clear()
        for _ in range(5):
            rejected(verifier, make_token("u"))
        assert len(counted_transport) == 5

    def test_an_empty_kid_keys_on_the_same_sentinel(self, counted_transport):
        """An empty-string `kid` is the same condition as an absent one, and shares its entry."""
        verifier = self.build()
        counted_transport.timeouts.clear()
        assert rejected(verifier, make_token("u")) is BoundedReason.bad_signature
        assert len(counted_transport) == 1

        assert rejected(verifier, make_token("u", headers={"kid": ""})) \
            is BoundedReason.bad_signature
        assert len(counted_transport) == 1, "the empty kid did not fall through to a second fetch"
        assert list(verifier._unknown_kids) == [_ABSENT_KID_SENTINEL]

    def test_two_equal_unknown_kids_merge_into_one_cache_entry(self, counted_transport):
        """FOUND-02/adjacency: two equal keys neither collide onto a wrong answer nor accumulate."""
        verifier = self.build()
        token = make_token("u", headers={"kid": "unknown-1"})
        rejected(verifier, token)
        rejected(verifier, token)
        assert list(verifier._unknown_kids) == ["unknown-1"]

    def test_the_unknown_kid_cache_is_bounded(self, counted_transport):
        """The cache is a bounded memory, not a growth surface an attacker chooses the size of."""
        verifier = self.build(unknown_kid_cache_size=256)
        for i in range(300):
            rejected(verifier, make_token("u", headers={"kid": f"unknown-{i}"}))
        assert len(verifier._unknown_kids) <= 256

    def test_a_known_kid_still_verifies_and_costs_no_fetch(self, counted_transport):
        """The cache changes nothing for a recognized key, which is still matched per request."""
        verifier = self.build()
        counted_transport.timeouts.clear()
        token = make_token("user-a", headers={"kid": KNOWN_KID})
        assert accepted(verifier, token).subject == "user-a"
        assert accepted(verifier, token).subject == "user-a"
        assert len(counted_transport) == 0

    def test_no_signing_key_or_decision_is_memoized(self, counted_transport):
        """T-35-12-05: the cache is negative only -- nothing an acceptance could be replayed from.

        A positive cache here would keep a rotated or withdrawn key working past its own lifetime,
        which is why the stored value is a deadline and the stored key is a key id.
        """
        verifier = self.build()
        rejected(verifier, make_token("u", headers={"kid": "unknown-1"}))
        assert all(isinstance(k, str) and isinstance(v, float)
                   for k, v in verifier._unknown_kids.items())

        # The endpoint withdraws the key it was serving; the next request stops being accepted, so
        # no acceptance survived in memory.
        counted_transport.body = jwks_body("some-other-key")
        verifier._jwks_client.jwk_set_cache = None
        assert rejected(verifier, make_token("u", headers={"kid": KNOWN_KID})) \
            is BoundedReason.bad_signature


class TestVerifyIsTotalUnderConcurrency:
    """`verify` never raises -- including out of its own cache, on the threadpool it runs on.

    The offload that took the JWKS fetch off the event loop also made `_unknown_kids` shared
    mutable state reachable from every anyio worker thread at once. Unsynchronized, the sweep in
    `_record_unknown` raises `RuntimeError: OrderedDict mutated during iteration` and the expiring
    `del` in `_is_known_unknown` races into a `KeyError`. Neither is a `PyJWTError`, so neither is
    caught by `verify`'s clauses, by `run_in_threadpool`, or by the barrier -- an unauthenticated
    caller would turn a 401 into a 500 (CR-01). These cases fail loudly if the lock is removed.
    """

    @pytest.fixture
    def counted_transport(self, monkeypatch):
        return install_counted_transport(monkeypatch)

    def build(self, **kwargs) -> JWTVerifier:
        return JWTVerifier(jwks_url=JWKS_URL, audience=TEST_PROJECT_ID, issuer=TEST_ISSUER,
                           **kwargs)

    @staticmethod
    def _run_on_threads(work, *, threads: int = 24) -> list[BaseException]:
        """Run `work` on `threads` OS threads at once, returning everything that escaped it."""
        escaped: list[BaseException] = []
        start = threading.Barrier(threads)

        def run() -> None:
            start.wait()
            try:
                work()
            except BaseException as exc:  # noqa: BLE001 - recording precisely what escaped
                escaped.append(exc)

        workers = [threading.Thread(target=run) for _ in range(threads)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        return escaped

    def test_the_cache_bookkeeping_survives_concurrent_readers_and_writers(self, counted_transport):
        """The race at its own seam.

        The parameters are load-bearing, not decorative. `_record_unknown`'s expiry sweep is what
        races, so the cache has to be *full* for the iteration to span enough bytecodes to be
        preempted: at 8 entries the sweep finishes inside a single scheduler slice and this case
        passes with the lock removed -- vacuous, the exact failure WR-05 was raised for. At the
        production 256 with a TTL short enough to keep entries turning over and a key space wider
        than the cache, removing `_cache_lock` yields 23 `RuntimeError`s out of 24 threads, six runs
        out of six.
        """
        verifier = self.build(unknown_kid_ttl_seconds=0.05, unknown_kid_cache_size=256)

        def churn() -> None:
            for i in range(3000):
                key = f"unknown-{i % 512}"
                verifier._is_known_unknown(key)
                verifier._record_unknown(key)

        escaped = self._run_on_threads(churn)
        assert not escaped, f"cache bookkeeping is not thread-safe: {escaped[:3]}"

    def test_concurrent_verification_of_unknown_kids_never_raises(self, counted_transport):
        """The same race reached the way production reaches it -- through `verify` itself.

        The `kid`s vary because that is what drives the sweep: a single repeated one short-circuits
        on its cache hit and never reaches `_record_unknown`, which makes the case unable to fail.
        Varying them is the reachable shape anyway -- the `kid` is attacker-chosen, and WR-03 records
        that churning it is exactly what walks past the cache.
        """
        verifier = self.build(unknown_kid_ttl_seconds=0.05, unknown_kid_cache_size=128)
        # 256 tokens, not more: each is a real RS256 signature, and the pool dominates this case's
        # runtime. 128/256 still reproduces the race 8-11 times per run with the lock removed.
        tokens = [make_token("u", headers={"kid": f"unknown-{i}"}) for i in range(256)]

        def verify_repeatedly() -> None:
            for i in range(400):
                assert verifier.verify(tokens[i % len(tokens)]) \
                    == (None, BoundedReason.bad_signature)

        escaped = self._run_on_threads(verify_repeatedly, threads=12)
        assert not escaped, f"verify raised instead of returning a bounded reason: {escaped[:3]}"

    def test_a_non_json_jwks_body_rejects_rather_than_raising(self, counted_transport):
        """WR-01: PyJWT wraps neither `json.JSONDecodeError` nor whatever a dependency invents next.

        The last-resort clause makes "never raises" structural rather than a docstring promise, so
        this returns the same bounded reason every other rejection does.
        """
        verifier = self.build()
        counted_transport.body = b"<html>502 Bad Gateway</html>"
        verifier._jwks_client.jwk_set_cache = None

        assert verifier.verify(make_token("u", headers={"kid": KNOWN_KID})) \
            == (None, BoundedReason.bad_signature)

    def test_a_non_json_jwks_body_does_not_mark_the_kid_unknown(self, counted_transport):
        """WR-02: a broken document is an *endpoint* condition, not a bogus key id."""
        verifier = self.build()
        counted_transport.body = b"<html>502 Bad Gateway</html>"
        verifier._jwks_client.jwk_set_cache = None
        rejected(verifier, make_token("u", headers={"kid": KNOWN_KID}))

        counted_transport.body = jwks_body(KNOWN_KID)
        verifier._jwks_client.jwk_set_cache = None
        assert accepted(verifier, make_token("u", headers={"kid": KNOWN_KID})).subject == "u", \
            "a broken JWKS document poisoned the cache for a kid the whole fleet shares"

    def test_a_jwks_document_with_no_usable_keys_does_not_mark_the_kid_unknown(
            self, counted_transport):
        """WR-02, the other endpoint shape: `{"keys": []}` is a degraded endpoint, not a miss.

        `PyJWKClient` raises a plain `PyJWKClientError` for it, which the previous carve-out --
        excluding only `PyJWKClientConnectionError` -- recorded as if the key id were bogus.
        """
        verifier = self.build()
        counted_transport.body = b'{"keys": []}'
        verifier._jwks_client.jwk_set_cache = None
        rejected(verifier, make_token("u", headers={"kid": KNOWN_KID}))

        counted_transport.body = jwks_body(KNOWN_KID)
        verifier._jwks_client.jwk_set_cache = None
        assert accepted(verifier, make_token("u", headers={"kid": KNOWN_KID})).subject == "u", \
            "an empty signing-key list poisoned the cache for the whole fleet's kid"

    def test_a_definitive_miss_is_still_recorded(self, counted_transport):
        """The narrowing must not disable the cache: a real refreshed-and-still-no-match still caches."""
        verifier = self.build()
        counted_transport.timeouts.clear()
        for _ in range(5):
            rejected(verifier, make_token("u", headers={"kid": "genuinely-unknown"}))
        assert len(counted_transport) == 1, "the definitive miss stopped being cached"
