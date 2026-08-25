"""§4.3 / §6.4 keyed subject hashing -- the one derivation its callers share.

`actor_subject_hash` and the challenge store's `preauth_subject_hash` are the **same family under
the same key** (D-21), separated only by a pinned domain-separation prefix. There is one helper
here rather than one per caller because two helpers would drift, and a drift here is silent: both
would produce a plausible 32-byte digest and only one would match the rows already written.

**On-disk encoding, pinned by this phase's checkpoint (assumption A5, reversibility one-way).**
Key material is base64 text in `config/config.yaml`, decoded to `bytes` exactly once at
configuration load and stored thereafter only as `bytes`. `hmac.new` is never called on a `str`:
it raises `TypeError`, and the obvious "fix" of calling `.encode()` silently derives the HMAC over
the base64 *text* instead of the 32 key bytes. Once one `core.auth_challenges` row exists there is
no migration back, because the raw subject was never stored.

**D-20's accepted consequence.** `config/config.yaml` is tracked in git, so the key material below
is committed and rotating a key leaves its predecessor readable in history for good. That was
raised and accepted; `.planning/todos/pending/secret-manager-integration.md` is the mitigation path
and exists for this reason. Note also that the YAML is authoritative for anything it declares --
`AppConfig(**yaml_data, ...)` ranks `init_settings` above `env_settings` -- so an environment
variable cannot shadow a committed key, and the Secret Manager follow-up must *remove* the YAML
entries rather than override them.

**D-22, the fail-closed policy.** A missing, empty, or short *active* key aborts configuration
load: nothing can be written without it, so the process must not start. A missing *older* version
only warns -- it means historical hashes cannot be recomputed, which no request path needs.
Requiring every version 1..active would mean keys could never be retired and losing one would
brick the app.
"""

import base64
import binascii
import hashlib
import hmac
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

# §4.3 / §6.4 -- pinned as `bytes` literals. Never parameterized, never built from a format
# string, never read from configuration. Pinning them is what stops them drifting.
ACTOR_SUBJECT_PREFIX = b"actor-subject:v1:"
IDP_ACCOUNT_PREFIX = b"idp-account:v1:"

# HMAC-SHA-256's block-aligned key length. Shorter material is a plausible-looking key that
# silently weakens every derived hash, so it is rejected at load rather than accepted quietly.
MIN_KEY_BYTES = 32


def _decode(material: SecretStr, label: str) -> bytes:
    """Decode base64 key material to raw bytes, or raise a message carrying none of it."""
    text = material.get_secret_value()
    if not text.strip():
        raise ValueError(f"hmac key material for {label} is empty")
    try:
        raw = base64.b64decode(text, validate=True)
    except binascii.Error:
        # Deliberately unchained: a `raise ... from exc` puts the original one frame away in a
        # traceback that may well be logged, and nothing in it helps an operator anyway.
        raise ValueError(f"hmac key material for {label} is not valid base64") from None
    if len(raw) < MIN_KEY_BYTES:
        raise ValueError(f"hmac key material for {label} decodes to {len(raw)} bytes, "
                         f"at least {MIN_KEY_BYTES} required")
    return raw


def _digest(key: bytes, prefix: bytes, issuer: str, subject: str) -> bytes:
    """`HMAC-SHA-256(key, prefix || issuer || ":" || subject)` -- 32 bytes for the BYTEA column."""
    return hmac.new(key, prefix + issuer.encode() + b":" + subject.encode(), hashlib.sha256).digest()


class HmacConfig(BaseModel):
    """The `hmac:` block. A `dict` keyed by version validates uniqueness for free and reads
    directly as `keys[active_version]`; a list of objects would do neither."""

    # T-35-08-02. `SecretStr` covers `repr` and `str`, but not a validation error: pydantic
    # renders the *pre-coercion* input in `input_value=...`, so a rejected configuration would
    # otherwise print the raw base64 into whatever caught it -- and this model's whole job is to
    # reject configurations. `AppConfig` sets the same flag, because a nested error is rendered
    # under the outer model's config rather than this one's.
    model_config = ConfigDict(hide_input_in_errors=True)

    active_version: int = Field(ge=1, le=32767,
                                description="Key version used for new writes. Bounded to the "
                                            "SMALLINT range a stored key version occupies, so a "
                                            "bad value fails at load rather than at the first "
                                            "write.")
    keys: dict[int, SecretStr] = Field(description="Base64 actor-subject key material by version. "
                                                   "Shared by §4.3 and §6.4 per D-21.")
    idp_account_keys: dict[int, SecretStr] = Field(
        default_factory=dict,
        description="Base64 idp-account key material by version. A separate family: §4.3 gives "
                    "idp_account_hash its own key, never one derived from the actor-subject key.")

    @model_validator(mode="after")
    def _validate_key_material(self):
        active = self.keys.get(self.active_version)
        if active is None:
            raise ValueError(f"hmac.keys has no entry for active_version {self.active_version}")
        _decode(active, f"version {self.active_version}")

        # A *declared* key that does not decode is a configuration error whatever its version, and
        # failing here keeps `HmacKeyring.__init__` total over validated configuration. This is not
        # in tension with D-22, which tolerates a version that is **absent**, not one that is
        # present and unusable.
        for version, secret in self.keys.items():
            if version != self.active_version:
                _decode(secret, f"version {version}")

        if self.idp_account_keys:
            if self.active_version not in self.idp_account_keys:
                raise ValueError("hmac.idp_account_keys is configured but has no entry for "
                                 f"active_version {self.active_version}")
            for version, secret in self.idp_account_keys.items():
                _decode(secret, f"idp-account version {version}")
        return self


class HmacKeyring:
    """Decodes every configured key exactly once and keeps only the bytes."""

    def __init__(self, cfg: HmacConfig) -> None:
        self.active_version = cfg.active_version
        self._keys = {v: _decode(s, f"version {v}") for v, s in cfg.keys.items()}
        self._idp_keys = {v: _decode(s, f"idp-account version {v}")
                          for v, s in cfg.idp_account_keys.items()}

    def __repr__(self) -> str:
        """Explicit, so no future refactor to a dataclass turns this into a key dump."""
        return (f"HmacKeyring(active_version={self.active_version}, "
                f"versions={sorted(self._keys)}, idp_versions={sorted(self._idp_keys)})")

    def warn_missing_older(self, log: Any) -> None:
        """D-22: a gap below the active version warns, never aborts."""
        for version in range(1, self.active_version):
            if version not in self._keys:
                log.warning("hmac_key_version_missing", key_version=version)

    def actor_subject_hash(self, issuer: str, subject: str, *, version: int | None = None) -> bytes:
        """§4.3. The challenge store calls this same method for `preauth_subject_hash` (D-21) and
        stores **no** key version: `core.auth_challenges` has no such column and verification uses
        the active key alone. A rotation therefore invalidates outstanding challenges -- completion
        fails the binding comparison, rejects `challenge_identity_mismatch`, and the client prepares
        a fresh one inside the 300-second TTL. Do not add a key-version column to that table.
        """
        resolved = self.active_version if version is None else version
        key = self._keys.get(resolved)
        if key is None:
            raise KeyError(f"no hmac key configured for version {resolved}")
        return _digest(key, ACTOR_SUBJECT_PREFIX, issuer, subject)

    def idp_account_hash(self, issuer: str, account: str) -> bytes:
        """The parallel §4.3 derivation for phase 41, under its own prefix and its own key."""
        key = self._idp_keys.get(self.active_version)
        if key is None:
            raise KeyError(f"no idp-account hmac key configured for version {self.active_version}")
        return _digest(key, IDP_ACCOUNT_PREFIX, issuer, account)

    def actor_subject_matches(self, stored: bytes, issuer: str, subject: str) -> bool:
        """Compare a stored hash against a recomputed one. Use this rather than `==` -- it is the
        only comparison in the codebase that touches keyed material, and `hmac.compare_digest`
        is what keeps it from leaking position information through timing."""
        return hmac.compare_digest(stored, self.actor_subject_hash(issuer, subject))
