"""Every rejection returns a bounded reason rather than raising, so the reason reaches the security log as a value."""

import threading
import time
from unittest.mock import patch
from urllib.error import URLError

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from nativespeaker.api.auth.jwt_verifier import _ABSENT_KID_SENTINEL, BoundedReason, JWTVerifier, VerifiedClaims
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
    """Hand-build an HS256 token keyed on `secret`, because PyJWT refuses to encode one with a PEM key."""
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
    """The accepted value object carries the verified (iss, sub) and nothing else."""

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
        """Identity and classification are never derived from claims."""
        claims = VerifiedClaims(issuer=TEST_ISSUER, subject="abc123")
        assert not hasattr(claims, "email")
        assert not hasattr(claims, "name")


class TestAntiOracle:
    """Every acceptance-failure branch is shaped identically and none raises."""

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
    """The claim rules against the real verifier; substituting the JWKS client isolates them, not fetch counts."""

    @pytest.fixture
    def jwks_client(self):
        with patch("nativespeaker.api.auth.jwt_verifier.PyJWKClient") as mock_cls:
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
        """The bound must hold for the call site that passes nothing, which is the one production uses."""
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
    """Fetch counts measured at `urlopen` under a real client, with a control case so a zero is evidence."""

    @pytest.fixture
    def counted_transport(self, monkeypatch):
        return install_counted_transport(monkeypatch)

    def build(self, **kwargs) -> JWTVerifier:
        return JWTVerifier(jwks_url=JWKS_URL, audience=TEST_PROJECT_ID, issuer=TEST_ISSUER,
                           **kwargs)

    def test_the_constructor_fetch_carries_a_bounded_timeout(self, counted_transport):
        """The bound is observed on the wire, not read off the constructor."""
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
        """The per-`kid` cache caps repeats, not spread; that residual is accepted because Envoy rate-limits."""
        verifier = self.build()
        counted_transport.timeouts.clear()
        for i in range(5):
            rejected(verifier, make_token("u", headers={"kid": f"unknown-{i}"}))
        assert len(counted_transport) == 5

    def test_a_cached_rejection_is_indistinguishable_from_a_fetched_one(self, counted_transport):
        """The cache-hit path yields the same bounded reason as the fetched path."""
        verifier = self.build()
        token = make_token("u", headers={"kid": "unknown-1"})
        counted_transport.timeouts.clear()

        fetched = verifier.verify(token)
        assert len(counted_transport) == 1, "the first verification really did fetch"
        cached = verifier.verify(token)
        assert len(counted_transport) == 1, "the second really did not"

        assert fetched == cached == (None, BoundedReason.bad_signature)

    def test_a_jwks_connection_failure_does_not_mark_the_kid_unknown(self, counted_transport):
        """An unreachable endpoint is not a bogus key id; recording it would extend the outage past recovery."""
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
        """A missing `kid` never matches a candidate, so without the sentinel it is one real fetch per request."""
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
        """Two equal key ids neither collide onto a wrong answer nor accumulate entries."""
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
        """The cache is negative only: it stores a deadline and a key id, never anything an acceptance could replay."""
        verifier = self.build()
        rejected(verifier, make_token("u", headers={"kid": "unknown-1"}))
        assert all(isinstance(k, str) and isinstance(v, float)
                   for k, v in verifier._unknown_kids.items())

        # The endpoint withdraws the key it was serving, so no acceptance can have survived in memory.
        counted_transport.body = jwks_body("some-other-key")
        verifier._jwks_client.jwk_set_cache = None
        assert rejected(verifier, make_token("u", headers={"kid": KNOWN_KID})) \
            is BoundedReason.bad_signature


class TestVerifyIsTotalUnderConcurrency:
    """`verify` never raises, including out of its own cache; every case here fails if `_cache_lock` is removed."""

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
        """The parameters are load-bearing: with a small cache the sweep finishes in one slice and passes unlocked."""
        verifier = self.build(unknown_kid_ttl_seconds=0.05, unknown_kid_cache_size=256)

        def churn() -> None:
            for i in range(3000):
                key = f"unknown-{i % 512}"
                verifier._is_known_unknown(key)
                verifier._record_unknown(key)

        escaped = self._run_on_threads(churn)
        assert not escaped, f"cache bookkeeping is not thread-safe: {escaped[:3]}"

    def test_concurrent_verification_of_unknown_kids_never_raises(self, counted_transport):
        """The `kid`s must vary; a repeated one short-circuits on its cache hit and the case can never fail."""
        verifier = self.build(unknown_kid_ttl_seconds=0.05, unknown_kid_cache_size=128)
        # 256 tokens, not more: each is a real RS256 signature and the pool dominates the runtime.
        tokens = [make_token("u", headers={"kid": f"unknown-{i}"}) for i in range(256)]

        def verify_repeatedly() -> None:
            for i in range(400):
                assert verifier.verify(tokens[i % len(tokens)]) \
                    == (None, BoundedReason.bad_signature)

        escaped = self._run_on_threads(verify_repeatedly, threads=12)
        assert not escaped, f"verify raised instead of returning a bounded reason: {escaped[:3]}"

    def test_a_non_json_jwks_body_rejects_rather_than_raising(self, counted_transport):
        """The last-resort clause makes never-raising structural, so this returns the usual bounded reason."""
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
        """An empty key set is a degraded endpoint, not a miss, so the key id must not be recorded as bogus."""
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
