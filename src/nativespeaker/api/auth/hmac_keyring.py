"""Keyed subject hashing: one helper for every caller, because two would drift and the drift is silent."""

import base64
import binascii
import hashlib
import hmac
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

# Pinned as bytes literals: never parameterized, never built from a format string, never configured.
ACTOR_SUBJECT_PREFIX = b"actor-subject:v1:"
IDP_ACCOUNT_PREFIX = b"idp-account:v1:"

# HMAC-SHA-256's block-aligned key length. Shorter material silently weakens every derived hash.
MIN_KEY_BYTES = 32


# Key material is base64 in config/config.yaml, which is tracked in git: a rotated key stays readable.
def _decode(material: SecretStr, label: str) -> bytes:
    """Decode base64 key material to raw bytes, or raise a message carrying none of it."""
    text = material.get_secret_value()
    if not text.strip():
        raise ValueError(f"hmac key material for {label} is empty")
    try:
        raw = base64.b64decode(text, validate=True)
    except binascii.Error:
        # Unchained on purpose: `raise ... from exc` puts the base64 one frame away in a traceback.
        raise ValueError(f"hmac key material for {label} is not valid base64") from None
    if len(raw) < MIN_KEY_BYTES:
        raise ValueError(f"hmac key material for {label} decodes to {len(raw)} bytes, "
                         f"at least {MIN_KEY_BYTES} required")
    return raw


def _digest(key: bytes, prefix: bytes, issuer: str, subject: str) -> bytes:
    """`HMAC-SHA-256(key, prefix || issuer || ":" || subject)` -- 32 bytes for the BYTEA column."""
    return hmac.new(key, prefix + issuer.encode() + b":" + subject.encode(), hashlib.sha256).digest()


class HmacConfig(BaseModel):
    """The `hmac:` block, keyed by version so uniqueness validates for free and reads as `keys[v]`."""

    # SecretStr hides repr and str but not a validation error, which renders the pre-coercion input.
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

        # A declared key that does not decode is a configuration error whatever its version.
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
        """Explicit, so a later refactor to a dataclass cannot turn this into a key dump."""
        return (f"HmacKeyring(active_version={self.active_version}, "
                f"versions={sorted(self._keys)}, idp_versions={sorted(self._idp_keys)})")

    def warn_missing_older(self, log: Any) -> None:
        """Warn, never abort: requiring every version would mean a key could never be retired."""
        for version in range(1, self.active_version):
            if version not in self._keys:
                log.warning("hmac_key_version_missing", key_version=version)

    def actor_subject_hash(self, issuer: str, subject: str, *, version: int | None = None) -> bytes:
        """Hash `(issuer, subject)`; the challenge store calls this for its own binding hash too."""
        # No key version is stored, so a rotation invalidates outstanding challenges within the TTL.
        resolved = self.active_version if version is None else version
        key = self._keys.get(resolved)
        if key is None:
            raise KeyError(f"no hmac key configured for version {resolved}")
        return _digest(key, ACTOR_SUBJECT_PREFIX, issuer, subject)

    def idp_account_hash(self, issuer: str, account: str) -> bytes:
        """The parallel derivation for idp accounts, under its own prefix and its own key."""
        key = self._idp_keys.get(self.active_version)
        if key is None:
            raise KeyError(f"no idp-account hmac key configured for version {self.active_version}")
        return _digest(key, IDP_ACCOUNT_PREFIX, issuer, account)

    def actor_subject_matches(self, stored: bytes, issuer: str, subject: str) -> bool:
        """Compare a stored hash against a recomputed one; `compare_digest` keeps that timing-safe."""
        return hmac.compare_digest(stored, self.actor_subject_hash(issuer, subject))
