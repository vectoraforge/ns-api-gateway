"""The wire contract driven directly: every hand-built key is lowercase, and no value is normalized."""
import pytest

from nativespeaker.api.auth.wire import BoundedReason, extract_bearer

TOKEN = "header.payload.signature"


def _headers(*values: bytes) -> list[tuple[bytes, bytes]]:
    """A raw ASGI header list carrying one `authorization` field per value, plus noise."""
    return [(b"host", b"test"),
            *[(b"authorization", value) for value in values],
            (b"accept", b"*/*")]


class TestTheSixWireCases:
    """Every one of these is `invalid_external_jwt` internally and `auth_required` to a client."""

    def test_zero_authorization_values_is_missing_token(self):
        assert extract_bearer(_headers()) == (None, BoundedReason.missing_token)

    def test_two_instances_are_duplicates(self):
        token, reason = extract_bearer(_headers(f"Bearer {TOKEN}".encode(),
                                                f"Bearer {TOKEN}".encode()))
        assert (token, reason) == (None, BoundedReason.duplicate_authorization)

    def test_two_differently_cased_instances_are_duplicates(self):
        """The server folds both onto one lowercase key, so what arrives is two entries of one field."""
        raw = [(b"authorization", b"Bearer one"), (b"authorization", b"Bearer two")]
        assert extract_bearer(raw) == (None, BoundedReason.duplicate_authorization)

    def test_a_comma_joined_value_is_a_duplicate_not_a_first_wins_pick(self):
        value = f"Bearer {TOKEN}, Bearer {TOKEN}".encode()
        assert extract_bearer(_headers(value)) == (None, BoundedReason.duplicate_authorization)

    def test_an_empty_token_after_the_scheme_is_malformed(self):
        assert extract_bearer(_headers(b"Bearer ")) == (None, BoundedReason.malformed)

    def test_trailing_content_after_the_token_is_malformed(self):
        value = f"Bearer {TOKEN} extra".encode()
        assert extract_bearer(_headers(value)) == (None, BoundedReason.malformed)


class TestNoValueIsEverSelected:
    """Duplicates are counted before any value is inspected, so there is nothing to steer."""

    def test_a_valid_and_an_invalid_instance_still_reject(self):
        raw = [(b"authorization", f"Bearer {TOKEN}".encode()), (b"authorization", b"garbage")]
        assert extract_bearer(raw) == (None, BoundedReason.duplicate_authorization)

    def test_the_reverse_order_rejects_identically(self):
        raw = [(b"authorization", b"garbage"), (b"authorization", f"Bearer {TOKEN}".encode())]
        assert extract_bearer(raw) == (None, BoundedReason.duplicate_authorization)

    def test_three_instances_reject_too(self):
        assert extract_bearer(_headers(b"Bearer a", b"Bearer b", b"Bearer c")) == (
            None, BoundedReason.duplicate_authorization)


class TestSchemeAndTokenCasing:
    """The scheme matches case-insensitively; the token bytes are never touched."""

    @pytest.mark.parametrize("scheme", [b"Bearer", b"bearer", b"BEARER", b"BeArEr"])
    def test_the_scheme_matches_case_insensitively(self, scheme):
        token, reason = extract_bearer(_headers(scheme + b" " + TOKEN.encode()))
        assert (token, reason) == (TOKEN, None)

    def test_the_token_bytes_are_not_case_folded(self):
        mixed = "AbC.dEf.GhI"
        assert extract_bearer(_headers(f"Bearer {mixed}".encode()))[0] == mixed

    def test_the_token_bytes_are_not_trimmed_of_internal_content(self):
        """A `+`, a `/`, and a `=` are all legal in a JWT's base64url-ish payload text."""
        odd = "a+b/c=d_e-f"
        assert extract_bearer(_headers(f"Bearer {odd}".encode()))[0] == odd

    @pytest.mark.parametrize("scheme", [b"Basic", b"Digest", b"Token", b"Bearertoken"])
    def test_any_other_scheme_is_malformed(self, scheme):
        value = scheme + b" " + TOKEN.encode() if scheme != b"Bearertoken" else scheme
        assert extract_bearer(_headers(value))[1] is BoundedReason.malformed


class TestShapesNoClientCanSend:
    """The reason this module exists alongside the e2e one."""

    @pytest.mark.parametrize("fold", [b"\n", b"\r", b"\r\n"])
    def test_a_line_folded_value_is_a_duplicate(self, fold):
        value = b"Bearer one" + fold + b" Bearer two"
        assert extract_bearer(_headers(value)) == (None, BoundedReason.duplicate_authorization)

    def test_a_non_ascii_token_byte_is_malformed(self):
        """The token is decoded strictly as ASCII -- never re-encoded into something acceptable."""
        assert extract_bearer(_headers(b"Bearer caf\xc3\xa9"))[1] is BoundedReason.malformed

    def test_internal_padding_between_scheme_and_token_is_malformed(self):
        """`Bearer  token` splits into three parts, the middle one empty."""
        assert extract_bearer(_headers(b"Bearer  token"))[1] is BoundedReason.malformed


class TestTheHarnessMatchesTheWire:
    """Guards this module's own premise -- see the module docstring."""

    def test_exactly_one_well_formed_field_is_accepted(self):
        """The positive control: the rejections above are the contract, not a blanket refusal."""
        assert extract_bearer(_headers(f"Bearer {TOKEN}".encode())) == (TOKEN, None)

    def test_a_capitalised_key_would_be_invisible_and_must_never_be_written(self):
        """A capitalised hand-built key is invisible to the production path, so it would pass for the wrong reason."""
        raw = [(b"Authorization", f"Bearer {TOKEN}".encode())]
        assert extract_bearer(raw) == (None, BoundedReason.missing_token)
