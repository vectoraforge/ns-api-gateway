"""Comprehensive JWT security tests for JWTVerifier."""

import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from nativespeaker.api.exceptions import AuthenticationError
from unit.conftest import PRIVATE_KEY_PEM, TEST_ISSUER, TEST_PROJECT_ID, make_test_verifier, make_token


@pytest.fixture
def verifier():
    return make_test_verifier()


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
        with pytest.raises(AuthenticationError):
            verifier.verify(token)

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
        with pytest.raises(AuthenticationError):
            verifier.verify(token)


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
        with pytest.raises(AuthenticationError):
            verifier.verify(tampered_token)

    def test_rejects_token_signed_with_different_key(self, verifier):
        """Token signed with an unknown private key must be rejected."""
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(encoding=serialization.Encoding.PEM,
                                            format=serialization.PrivateFormat.PKCS8,
                                            encryption_algorithm=serialization.NoEncryption())
        token = make_token("user1", private_key=other_pem)
        with pytest.raises(AuthenticationError):
            verifier.verify(token)


class TestTokenExpiry:
    def test_rejects_expired_token(self, verifier):
        token = make_token("user1", exp=time.time() - 3600)
        with pytest.raises(AuthenticationError):
            verifier.verify(token)

    def test_accepts_token_within_leeway(self, verifier):
        """Token expired <30s ago should still be accepted (leeway=30)."""
        token = make_token("user1", exp=time.time() - 10)
        result = verifier.verify(token)
        assert result.sub == "user1"

    def test_rejects_token_past_leeway(self, verifier):
        """Token expired >30s ago must be rejected."""
        token = make_token("user1", exp=time.time() - 60)
        with pytest.raises(AuthenticationError):
            verifier.verify(token)


class TestClaimValidation:
    def test_rejects_wrong_audience(self, verifier):
        token = make_token("user1", aud="wrong-project")
        with pytest.raises(AuthenticationError):
            verifier.verify(token)

    def test_rejects_wrong_issuer(self, verifier):
        token = make_token("user1", iss="https://evil.example.com")
        with pytest.raises(AuthenticationError):
            verifier.verify(token)

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
        with pytest.raises(AuthenticationError):
            verifier.verify(token)

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
        with pytest.raises(AuthenticationError):
            verifier.verify(token)

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
        with pytest.raises(AuthenticationError):
            verifier.verify(token)

class TestMalformedTokens:
    def test_rejects_empty_string(self, verifier):
        with pytest.raises(AuthenticationError):
            verifier.verify("")

    def test_rejects_garbage(self, verifier):
        with pytest.raises(AuthenticationError):
            verifier.verify("not.a.jwt.at.all")

    def test_rejects_just_dots(self, verifier):
        with pytest.raises(AuthenticationError):
            verifier.verify("...")


class TestCrossUserIsolation:
    def test_different_sub_returns_different_user(self, verifier):
        token_a = make_token("user-a")
        token_b = make_token("user-b")
        assert verifier.verify(token_a).sub == "user-a"
        assert verifier.verify(token_b).sub == "user-b"

    def test_sub_is_returned_as_string(self, verifier):
        token = make_token("12345")
        assert verifier.verify(token).sub == "12345"


class TestValidToken:
    def test_accepts_valid_token(self, verifier):
        token = make_token("user1")
        assert verifier.verify(token).sub == "user1"

    def test_accepts_token_with_extra_claims(self, verifier):
        """Extra claims are ignored -- token is still valid."""
        token = make_token("user1", extra_claims={"custom": "value", "firebase": {"sign_in_provider": "google.com"}})
        assert verifier.verify(token).sub == "user1"
