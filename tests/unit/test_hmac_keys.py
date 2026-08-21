"""FOUND-05 / D-21 / D-22: the one keyring behind `actor_subject_hash` and `preauth_subject_hash`.

Every configuration here is built inline from locally-generated base64 material. The module reads
nothing from `config/` on purpose: these cases must stay true whatever key version the repository
happens to have active, and a case that derived its expectations from the committed development key
would go green again the moment someone rotated it.
"""

import base64
import hashlib
import hmac

import pytest
from pydantic import ValidationError

from nativespeaker.api.auth.keys import (
    ACTOR_SUBJECT_PREFIX,
    IDP_ACCOUNT_PREFIX,
    HmacConfig,
    HmacKeyring,
)

ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "Xy7Q1s0K2mNb3fV4"


def material(seed: int) -> str:
    """A distinct, valid 32-byte key as base64 text -- the on-disk encoding this phase pinned."""
    return base64.b64encode(bytes((seed * 37 + i) % 256 for i in range(32))).decode()


def config(active: int = 1, *, keys: dict[int, str] | None = None,
           idp: dict[int, str] | None = None) -> HmacConfig:
    return HmacConfig(active_version=active,
                      keys=keys if keys is not None else {active: material(active)},
                      idp_account_keys=idp if idp is not None else {active: material(active + 100)})


def keyring(active: int = 1, **kwargs) -> HmacKeyring:
    return HmacKeyring(config(active, **kwargs))


class _RecordingLog:
    """A recording spy. `warn_missing_older` takes its logger as a parameter, so nothing needs
    patching -- and `structlog.testing.capture_logs` is unusable in this suite (D-35-01-A)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def warning(self, event: str, **kwargs) -> None:
        self.calls.append((event, kwargs))


class TestTheDerivation:
    """§4.3: HMAC-SHA-256 over a pinned domain-separated message, 32 bytes for the BYTEA column."""

    def test_actor_subject_hash_is_exactly_32_bytes(self):
        assert len(keyring().actor_subject_hash(ISSUER, SUBJECT)) == 32

    def test_the_same_inputs_yield_the_identical_digest(self):
        ring = keyring()
        assert ring.actor_subject_hash(ISSUER, SUBJECT) == ring.actor_subject_hash(ISSUER, SUBJECT)

    def test_a_different_key_version_yields_a_different_digest(self):
        """D-21's rotation consequence, stated as an assertion: the same subject hashes
        differently under a different key, which is why an outstanding challenge dies."""
        ring = keyring(2, keys={1: material(1), 2: material(2)})
        assert (ring.actor_subject_hash(ISSUER, SUBJECT, version=1)
                != ring.actor_subject_hash(ISSUER, SUBJECT, version=2))

    def test_the_prefixes_separate_the_two_families(self):
        ring = keyring()
        assert ring.actor_subject_hash(ISSUER, SUBJECT) != ring.idp_account_hash(ISSUER, SUBJECT)

    def test_the_prefixes_are_pinned_bytes_literals(self):
        """RESEARCH Pitfall 8: `bytes`, never `str`, and never built from a format string."""
        assert isinstance(ACTOR_SUBJECT_PREFIX, bytes)
        assert isinstance(IDP_ACCOUNT_PREFIX, bytes)
        assert ACTOR_SUBJECT_PREFIX == b"actor-subject:v1:"
        assert IDP_ACCOUNT_PREFIX == b"idp-account:v1:"

    def test_the_derivation_runs_over_the_decoded_key_bytes_not_the_base64_text(self):
        """T-35-08-04, the one-way failure the checkpoint exists to prevent.

        Both derivations produce a plausible 32-byte digest and neither raises. Only one matches
        whatever wrote the existing rows, and no migration can recompute the other -- the raw
        subject was never stored. This case is what makes the wrong one fail loudly.
        """
        text = material(9)
        message = ACTOR_SUBJECT_PREFIX + ISSUER.encode() + b":" + SUBJECT.encode()
        over_key_bytes = hmac.new(base64.b64decode(text), message, hashlib.sha256).digest()
        over_base64_text = hmac.new(text.encode(), message, hashlib.sha256).digest()

        got = HmacKeyring(config(1, keys={1: text})).actor_subject_hash(ISSUER, SUBJECT)
        assert got == over_key_bytes
        assert got != over_base64_text


class TestTheActiveKeyPolicy:
    """D-22: nothing can be written without the active key, so a bad one aborts configuration load."""

    def test_an_absent_active_key_is_rejected(self):
        with pytest.raises(ValidationError, match="2"):
            HmacConfig(active_version=2, keys={1: material(1)})

    def test_an_empty_active_key_is_rejected(self):
        with pytest.raises(ValidationError):
            HmacConfig(active_version=1, keys={1: ""})

    def test_a_whitespace_active_key_is_rejected(self):
        with pytest.raises(ValidationError):
            HmacConfig(active_version=1, keys={1: "   "})

    def test_short_key_material_is_rejected(self):
        """31 bytes is a plausible-looking key that silently weakens every derived hash."""
        short = base64.b64encode(b"x" * 31).decode()
        with pytest.raises(ValidationError):
            HmacConfig(active_version=1, keys={1: short})

    @pytest.mark.parametrize("version", [0, -1, 32768])
    def test_an_out_of_range_active_version_is_rejected(self, version):
        """`audit.auth_events.actor_subject_hash_key_version` is SMALLINT: fail at load, not at
        the first audit insert."""
        with pytest.raises(ValidationError):
            HmacConfig(active_version=version, keys={version: material(1)})

    @pytest.mark.parametrize("version", [1, 32767])
    def test_the_range_bounds_themselves_are_accepted(self, version):
        assert HmacConfig(active_version=version,
                          keys={version: material(version)}).active_version == version


class TestTheHistoricalGapIsTolerated:
    """D-22's other half: a missing *older* key only warns. Requiring 1..active would mean keys
    could never be retired, and losing one would brick the app."""

    def test_a_gap_below_the_active_version_loads(self):
        cfg = HmacConfig(active_version=3, keys={1: material(1), 3: material(3)})
        assert cfg.active_version == 3
        assert sorted(cfg.keys) == [1, 3]

    def test_warn_missing_older_names_the_gap_and_does_not_raise(self):
        log = _RecordingLog()
        HmacKeyring(config(3, keys={1: material(1), 3: material(3)})).warn_missing_older(log)
        assert [kwargs["key_version"] for _, kwargs in log.calls] == [2]

    def test_a_complete_history_warns_about_nothing(self):
        log = _RecordingLog()
        keyring(2, keys={1: material(1), 2: material(2)}).warn_missing_older(log)
        assert log.calls == []


class TestNoLeakage:
    """T-35-08-02: key material reaches no repr, no traceback, and no log line."""

    def test_repr_of_the_configuration_discloses_no_key_material(self):
        text = material(5)
        cfg = HmacConfig(active_version=1, keys={1: text})
        assert text not in repr(cfg)
