"""FOUND-05 / D-21 / D-22: the one keyring behind `actor_subject_hash` and `preauth_subject_hash`.

Every configuration here is built inline from locally-generated base64 material. The module reads
nothing from `config/` on purpose: these cases must stay true whatever key version the repository
happens to have active, and a case that derived its expectations from the committed development key
would go green again the moment someone rotated it.
"""

import ast
import base64
import hashlib
import hmac
import inspect
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from nativespeaker.api.auth.keys import (
    ACTOR_SUBJECT_PREFIX,
    IDP_ACCOUNT_PREFIX,
    HmacConfig,
    HmacKeyring,
)
from nativespeaker.api.config import AppConfig

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


def discloses(text: str, rendered: str, run: int = 8) -> bool:
    """True when any `run`-character stretch of the key text appears in `rendered`.

    Whole-string containment is too weak to assert against: pydantic truncates long values in its
    error output, so a leaked 44-character key shows up as its head and its tail with an ellipsis
    between them and `text not in rendered` passes while most of the key is on screen. Verified by
    mutation -- turning `hide_input_in_errors` off is invisible to the containment form.
    """
    return any(text[i:i + run] in rendered for i in range(len(text) - run + 1))


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

    def test_two_keyrings_from_the_same_configuration_agree(self):
        """Stability across instances, not merely across calls. A row written by one process must
        still match a hash recomputed by the next one, which is the property the audit table and
        the challenge binding both rest on."""
        cfg = config(1, keys={1: material(4)})
        assert (HmacKeyring(cfg).actor_subject_hash(ISSUER, SUBJECT)
                == HmacKeyring(cfg).actor_subject_hash(ISSUER, SUBJECT))

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
        """The matcher names the whole clause on purpose. `match="2"` also passes when the config
        is rejected for some *other* reason that happens to print a 2 -- verified by mutation."""
        with pytest.raises(ValidationError, match="no entry for active_version 2"):
            HmacConfig(active_version=2, keys={1: material(1)})

    def test_an_empty_active_key_is_rejected(self):
        """The message is pinned, not just the rejection. Without the emptiness branch an empty
        key still fails -- as "decodes to 0 bytes" -- and a blanked-out or not-yet-filled key is
        the case an operator most needs a readable answer for. Verified by mutation."""
        with pytest.raises(ValidationError, match="is empty"):
            HmacConfig(active_version=1, keys={1: ""})

    def test_a_whitespace_active_key_is_rejected(self):
        with pytest.raises(ValidationError, match="is empty"):
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


class TestTheTwoFamiliesAreSeparate:
    """§4.3 / D-21: `idp_account_hash` is a parallel prefix under **its own key**, never one
    derived from the actor-subject key."""

    def test_identical_key_material_still_yields_different_digests(self):
        """Isolates the prefix. Both families are handed byte-identical material here, so the only
        thing left that can separate them is the domain-separation prefix."""
        same = material(6)
        ring = HmacKeyring(HmacConfig(active_version=1, keys={1: same},
                                      idp_account_keys={1: same}))
        assert ring.actor_subject_hash(ISSUER, SUBJECT) != ring.idp_account_hash(ISSUER, SUBJECT)

    def test_the_idp_derivation_moves_with_its_own_key_and_not_the_actor_key(self):
        shared = material(11)
        first = HmacKeyring(HmacConfig(active_version=1, keys={1: shared},
                                       idp_account_keys={1: material(12)}))
        second = HmacKeyring(HmacConfig(active_version=1, keys={1: shared},
                                        idp_account_keys={1: material(13)}))
        assert first.idp_account_hash(ISSUER, SUBJECT) != second.idp_account_hash(ISSUER, SUBJECT)
        assert first.actor_subject_hash(ISSUER, SUBJECT) == second.actor_subject_hash(ISSUER, SUBJECT)

    def test_the_idp_digest_is_not_the_actor_key_under_the_idp_prefix(self):
        """The failure this guards against is subtle: swapping only the prefix while keeping one
        key would satisfy every other case in this class and still put both families under one
        secret, which is exactly what §4.3 separates them to avoid."""
        actor, idp = material(14), material(15)
        ring = HmacKeyring(HmacConfig(active_version=1, keys={1: actor},
                                      idp_account_keys={1: idp}))
        message = IDP_ACCOUNT_PREFIX + ISSUER.encode() + b":" + SUBJECT.encode()
        under_actor_key = hmac.new(base64.b64decode(actor), message, hashlib.sha256).digest()
        under_idp_key = hmac.new(base64.b64decode(idp), message, hashlib.sha256).digest()

        assert ring.idp_account_hash(ISSUER, SUBJECT) == under_idp_key
        assert ring.idp_account_hash(ISSUER, SUBJECT) != under_actor_key

    def test_an_idp_family_configured_without_the_active_version_is_rejected(self):
        with pytest.raises(ValidationError, match="idp_account_keys"):
            HmacConfig(active_version=2, keys={2: material(2)}, idp_account_keys={1: material(1)})

    def test_idp_account_hash_raises_when_no_idp_key_is_configured(self):
        """Foundation writes no idp-account hash, so an unconfigured family is not a boot failure --
        but it must not silently fall back to the actor-subject key either."""
        ring = HmacKeyring(HmacConfig(active_version=1, keys={1: material(1)}))
        with pytest.raises(KeyError):
            ring.idp_account_hash(ISSUER, SUBJECT)


class TestComparison:
    """T-35-08-03: every stored-hash comparison goes through `hmac.compare_digest`, never `==`."""

    def test_a_recomputed_hash_matches_the_stored_one(self):
        ring = keyring()
        assert ring.actor_subject_matches(ring.actor_subject_hash(ISSUER, SUBJECT), ISSUER, SUBJECT)

    def test_a_different_subject_does_not_match(self):
        ring = keyring()
        stored = ring.actor_subject_hash(ISSUER, SUBJECT)
        assert not ring.actor_subject_matches(stored, ISSUER, "someone-else")
        assert not ring.actor_subject_matches(stored, "https://other.example", SUBJECT)

    def test_the_comparison_is_compare_digest_and_not_an_equality_operator(self):
        """Pinned on the source, because no input can distinguish the two: an equality operator
        returns the same answers and differs only in what it leaks through timing. Plans 09 and 10
        call this method rather than writing their own comparison, which is what keeps the operator
        out of the seam."""
        tree = ast.parse(textwrap.dedent(inspect.getsource(HmacKeyring.actor_subject_matches)))
        called = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        compared = [node for node in ast.walk(tree) if isinstance(node, ast.Compare)
                    and any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops)]
        assert "hmac.compare_digest" in called
        assert compared == []


class TestTheKeyringHoldsBytes:
    """RESEARCH Pitfall 8 / T-35-08-04: decode once at construction, then bytes only."""

    def test_every_stored_key_is_bytes(self):
        ring = keyring(2, keys={1: material(1), 2: material(2)})
        stored = [value for mapping in vars(ring).values() if isinstance(mapping, dict)
                  for value in mapping.values()]
        assert stored, "expected the keyring to hold decoded key material"
        assert all(isinstance(value, bytes) for value in stored)

    def test_the_keyring_decodes_each_key_exactly_once(self, monkeypatch):
        cfg = config(2, keys={1: material(1), 2: material(2)}, idp={2: material(102)})

        calls = 0
        real = base64.b64decode

        def counting(*args, **kwargs):
            nonlocal calls
            calls += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(base64, "b64decode", counting)
        ring = HmacKeyring(cfg)
        after_construction = calls
        for _ in range(5):
            ring.actor_subject_hash(ISSUER, SUBJECT)
            ring.idp_account_hash(ISSUER, SUBJECT)

        assert after_construction == 3, "one decode per configured key, no more"
        assert calls == after_construction, "derivation must not decode anything"


class TestNoLeakage:
    """T-35-08-02: key material reaches no repr, no str, and no validation-error message."""

    def test_repr_of_the_configuration_discloses_no_key_material(self):
        text = material(5)
        cfg = HmacConfig(active_version=1, keys={1: text})
        assert not discloses(text, repr(cfg))

    def test_str_of_the_configuration_discloses_no_key_material(self):
        text = material(5)
        cfg = HmacConfig(active_version=1, keys={1: text})
        assert not discloses(text, str(cfg))

    def test_repr_of_the_keyring_discloses_no_key_material(self):
        """The keyring holds raw bytes, so this is the one object that could print the key
        itself rather than its base64 text."""
        text = material(5)
        ring = HmacKeyring(HmacConfig(active_version=1, keys={1: text}))
        assert not discloses(text, repr(ring))
        assert not discloses(repr(base64.b64decode(text)), repr(ring))

    @pytest.mark.parametrize("bad", [{1: material(1)}, {2: "!!!not base64!!!"},
                                     {2: base64.b64encode(b"x" * 31).decode()}])
    def test_a_validation_error_discloses_no_key_material(self, bad):
        """`SecretStr` covers repr and str but not this: pydantic renders the *pre-coercion* input
        in `input_value=...`, so the one model whose job is to reject configurations was also the
        one most likely to print them. `hide_input_in_errors` is what closes it."""
        with pytest.raises(ValidationError) as caught:
            HmacConfig(active_version=2, keys=bad)
        for text in bad.values():
            assert not discloses(text, str(caught.value))

    def test_a_validation_error_raised_through_app_config_discloses_no_key_material(self):
        """The nested path, which is the one a real deployment takes. A nested model's error is
        rendered under the *outer* model's config, so `HmacConfig` setting the flag on itself is
        not enough -- `AppConfig` has to set it too. Mutation-verified: removing the flag from the
        settings tree fails here and nowhere else."""
        text = material(8)
        with pytest.raises(ValidationError) as caught:
            AppConfig(db={"host": "h", "port": 1, "user": "u", "password": "p", "name": "n"},
                      jwt={"project_id": "x", "api_key": "y"},
                      hmac={"active_version": 2, "keys": {1: text}},
                      prompt="p",
                      examples={"en": ["Example 1"]})
        assert "hmac" in str(caught.value)
        assert not discloses(text, str(caught.value))


class TestThisModuleStandsAloneFromTheCommittedConfiguration:
    """Pinned so it survives an edit: every case above builds its own key material.

    A case that asserted against the tracked configuration file would go green again the moment
    someone rotated the committed development key -- or, worse, would encode that key into an
    expectation and quietly become the thing preventing rotation. `tests/unit/test_config.py` owns
    the one case that does assert against the committed key, which is where it belongs.
    """

    def _tree(self) -> ast.Module:
        return ast.parse(Path(__file__).read_text())

    def test_the_only_file_this_module_opens_is_its_own_source(self):
        opens = [node for node in ast.walk(self._tree()) if isinstance(node, ast.Call)
                 and (getattr(node.func, "id", None) == "open"
                      or getattr(node.func, "attr", None) in {"open", "read_text", "read_bytes"})]
        assert opens, "expected to find the __file__ reads in this class, or this case is vacuous"
        for node in opens:
            names = {inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)}
            assert "__file__" in names, f"opens something other than its own source: {ast.unparse(node)}"

    def test_this_module_imports_nothing_that_reads_configuration(self):
        """`AppConfig` is a model and reads nothing; `EnvironmentConfig` is the loader that opens
        `config/`. Importing the first is fine, importing the second is the drift this forbids."""
        imported = {alias.name for node in ast.walk(self._tree())
                    if isinstance(node, ast.ImportFrom) for alias in node.names}
        assert "EnvironmentConfig" not in imported
