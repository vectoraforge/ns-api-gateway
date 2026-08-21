"""§1.2 JWT verification rules: acceptance, bounded-reason rejection, and the anti-oracle shape.

Every rejection branch returns `(None, BoundedReason.<member>)` rather than raising. Raising is
wrong at this seam: the barrier is a pure-ASGI middleware outside Starlette's ExceptionMiddleware,
so an exception raised here would surface as a 500 instead of `auth_required` (D-01).
"""

import time
from unittest.mock import patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from nativespeaker.api.auth.verification import JWTVerifier, VerifiedClaims
from nativespeaker.api.auth.wire import BoundedReason
from unit.conftest import (
    PRIVATE_KEY_PEM,
    PUBLIC_KEY_PEM,
    TEST_ISSUER,
    TEST_PROJECT_ID,
    make_test_verifier,
    make_token,
)


@pytest.fixture
def verifier():
    return make_test_verifier()


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
        token = pyjwt.encode(payload, PUBLIC_KEY_PEM.decode(), algorithm="HS256")
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
    """The same rules against the real `JWTVerifier`, with only the JWKS transport stubbed."""

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
                    cache_ttl_seconds=1234)
        mock_cls.assert_called_once_with("https://jwks.invalid/keys",
                                         cache_jwk_set=True,
                                         lifespan=1234)
        # Fail-fast warm-up: an unreachable JWKS endpoint crashes startup, not the first request.
        instance.get_signing_keys.assert_called_once_with()

    def test_two_verifications_issue_no_additional_jwks_fetch(self, real_verifier, jwks_client):
        """§1.2: a request costs one local RSA verification and no per-request network call."""
        _, instance = jwks_client
        assert accepted(real_verifier, make_token("user-a")).subject == "user-a"
        assert accepted(real_verifier, make_token("user-b")).subject == "user-b"
        assert instance.get_signing_keys.call_count == 0

    def test_rejects_hs256_over_the_public_key(self, real_verifier):
        """`algorithms=["RS256"]` is passed explicitly, so confusion lands on bad_signature."""
        payload = {"sub": "u", "aud": TEST_PROJECT_ID, "iss": TEST_ISSUER,
                   "exp": time.time() + 3600, "iat": time.time()}
        token = pyjwt.encode(payload, PUBLIC_KEY_PEM.decode(), algorithm="HS256")
        assert rejected(real_verifier, token) is BoundedReason.bad_signature

    def test_pins_the_issuer_to_the_one_configured_integration(self, real_verifier):
        token = make_token("u", iss="https://securetoken.google.com/other-project")
        assert rejected(real_verifier, token) is BoundedReason.issuer_mismatch

    def test_pins_the_audience_to_the_configured_project_id(self, real_verifier):
        token = make_token("u", aud="other-project")
        assert rejected(real_verifier, token) is BoundedReason.audience_mismatch

    def test_requires_a_non_empty_subject(self, real_verifier):
        assert rejected(real_verifier, make_token("")) is BoundedReason.empty_subject
