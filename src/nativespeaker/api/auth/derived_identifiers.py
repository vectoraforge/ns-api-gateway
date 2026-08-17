"""Server-side derived identifiers: the HMAC families, their keys, and their rotation rules.

Where this specification stores a derived identifier for lookup, uniqueness or audit, it stores
a keyed `HMAC-SHA-256` digest and never the value it was derived from. Three derived identifiers
exist — `actor_subject_hash`, its `preauth_subject_hash` twin, and `idp_account_hash` — under two
versioned keys, each family domain-separated from the other and each input canonicalized by the
adapter that produced it before a byte of it is hashed.
"""

import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    classify_provider,
    confirm_stored_binding,
    provider_uid_for,
)
from nativespeaker.api.auth.invariants import (
    GateAlreadyConsumedError,
    GateConsumptionKind,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.taxonomy import ClientErrorClass, surface


class DerivationError(RuntimeError):
    """A derived identifier was about to be computed, stored or rotated the wrong way."""


# --- The families and their domain separation -------------------------------------------------


class DerivationFamily(StrEnum):
    """The three derived identifiers this specification stores."""
    actor_subject_hash = "actor_subject_hash"
    preauth_subject_hash = "preauth_subject_hash"
    idp_account_hash = "idp_account_hash"


class KeyFamily(StrEnum):
    """The two versioned server-side HMAC keys. `preauth_subject_hash` is the
    `actor_subject_hash` family under the same key, not a third one."""
    k_actor_subject = "k_actor_subject"
    k_idp_account = "k_idp_account"


FAMILY_KEY: dict[DerivationFamily, KeyFamily] = {
    DerivationFamily.actor_subject_hash: KeyFamily.k_actor_subject,
    DerivationFamily.preauth_subject_hash: KeyFamily.k_actor_subject,
    DerivationFamily.idp_account_hash: KeyFamily.k_idp_account,
}

# The domain-separation label each key family's preimage opens with.
DOMAIN_LABELS: dict[KeyFamily, str] = {
    KeyFamily.k_actor_subject: "actor-subject:v1:",
    KeyFamily.k_idp_account: "idp-account:v1:",
}

_LABEL_SHAPE = re.compile(r"^[a-z][a-z0-9-]*:v[0-9]+:$")


def assert_label_format(labels: Mapping[KeyFamily, str] = DOMAIN_LABELS) -> None:
    """The literal label strings are normative in spirit rather than byte for byte: a deployment
    may replace them, but only with labels that stay fixed, explicit, versioned, and disjoint
    across derivation families. Disjointness is prefix-freeness — a label that prefixed another
    would let one family's preimage be read as another's."""
    # [impl->req~proof-domain-separation-label-format~1]
    if set(labels) != set(KeyFamily):
        raise DerivationError("every derivation family carries its own explicit label")
    for label in labels.values():
        if not _LABEL_SHAPE.match(label):
            raise DerivationError(f"{label!r} is not a fixed, explicit, versioned label")
    for family, label in labels.items():
        for other, other_label in labels.items():
            if other is not family and (label == other_label or other_label.startswith(label)):
                raise DerivationError(f"{family} and {other} are not disjoint")


assert_label_format()


def domain_label(family: DerivationFamily) -> str:
    """Every HMAC derivation opens its preimage with its family's explicit label, so no two
    families can ever produce the same digest from the same underlying value."""
    # [impl->req~proof-hmac-domain-separation~1]
    key_family = FAMILY_KEY[family]
    label = DOMAIN_LABELS[key_family]
    if not label:
        raise DerivationError(f"{family} has no domain-separation label")
    return label


# --- Canonicalization -------------------------------------------------------------------------

# A canonical HMAC input carries no Unicode ambiguity, no surrounding whitespace, no control
# characters, and no `:` — the separator the preimages use between their components.
_FORBIDDEN_INPUT = re.compile(r"[\x00-\x20:\x7f]")


def _canonical_text(value: str, what: str) -> str:
    if not isinstance(value, str):
        raise DerivationError(f"{what} is canonicalized as text")
    canonical = unicodedata.normalize("NFC", value).strip()
    if not canonical:
        raise DerivationError(f"{what} must be non-empty")
    if _FORBIDDEN_INPUT.search(canonical):
        raise DerivationError(f"{what} carries a character the preimage cannot separate")
    return canonical


def canonical_issuer(issuer: str) -> str:
    """The issuer component: a deployment-known plaintext issuer string, NFC-normalized. It is
    the one component allowed to carry the `:` of its `https://` scheme."""
    # [impl->req~proof-hmac-input-canonicalization~1]
    canonical = unicodedata.normalize("NFC", issuer).strip()
    if not canonical:
        raise DerivationError("the issuer must be non-empty")
    return canonical


def canonical_actor_subject(subject: str) -> str:
    """The actor-subject family's own canonicalization of a backend-verified `sub` claim."""
    # [impl->req~proof-hmac-input-canonicalization~1]
    return _canonical_text(subject, "an actor subject")


def _canonical_google_account_id(value: str) -> str:
    """Google's stable account identifier as `providerData` reports it."""
    return _canonical_text(value, "a Google provider account id")


def _canonical_apple_user_id(value: str) -> str:
    """Apple's per-app stable user identifier as `providerData` reports it."""
    return _canonical_text(value, "an Apple provider account id")


# The provider-specific adapters. There is no adapter for `anonymous`: an anonymous identity has
# no provider account, so no `idp_account_hash` input can be produced from one.
PROVIDER_ACCOUNT_ADAPTERS: dict[IdentityProvider, Callable[[str], str]] = {
    IdentityProvider.google: _canonical_google_account_id,
    IdentityProvider.apple: _canonical_apple_user_id,
}


def canonical_provider_account_id(provider: IdentityProvider, value: str) -> str:
    """The provider-specific adapter that produced the identifier canonicalizes it before it is
    hashed. An unrecognized provider has no adapter and derives nothing."""
    # [impl->req~proof-hmac-input-canonicalization~1]
    adapter = PROVIDER_ACCOUNT_ADAPTERS.get(provider)
    if adapter is None:
        raise DerivationError(f"{provider} has no provider-account canonicalization adapter")
    return adapter(value)


# --- The keys ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HmacKey:
    """One version of one server-side HMAC key."""
    version: int
    secret: bytes

    def __post_init__(self) -> None:
        if self.version < 1:
            raise DerivationError("an HMAC key version starts at 1")
        if len(self.secret) < 32:
            raise DerivationError("an HMAC-SHA-256 key carries at least 256 bits of entropy")


# Where HMAC key material may come from. PostgreSQL application tables are not on the list, and
# neither is a platform private key: nothing here is ever written to a row.
KEY_SOURCES: frozenset[str] = frozenset({"server_configuration", "deployment_secret_store"})

# Column names that would put key material into an application table. None of them exists.
KEY_MATERIAL_COLUMNS: frozenset[str] = frozenset({
    "hmac_key", "hmac_secret", "k_actor_subject", "k_idp_account", "signing_key",
    "attestation_private_key", "private_key", "platform_private_key", "secret_key",
})


def assert_key_source(source: str) -> str:
    """Raw platform private keys and backend HMAC keys are never persisted in PostgreSQL
    application tables: the key ring is loaded from server configuration alone."""
    # [impl->req~proof-no-raw-keys-in-postgresql~1]
    if source not in KEY_SOURCES:
        raise DerivationError(f"{source} is not a source of HMAC key material")
    return source


def assert_no_key_material_column(table: str, columns: Iterable[str]) -> None:
    """No application table carries a column that could hold a raw platform private key or a
    backend HMAC key."""
    # [impl->req~proof-no-raw-keys-in-postgresql~1]
    offending = sorted({column for column in columns if column.lower() in KEY_MATERIAL_COLUMNS})
    if offending:
        raise DerivationError(f"{table}.{offending} would persist raw key material")


class KeyRing:
    """One key family's current active version, plus the versions retained for lookup during a
    rotation window. New values are always written under the current version."""

    def __init__(self, family: KeyFamily, *, current: HmacKey,
                 retired: Sequence[HmacKey] = (),
                 source: str = "server_configuration") -> None:
        assert_key_source(source)
        self.family = family
        self._current = current
        versions = {key.version: key for key in retired}
        if current.version in versions:
            raise DerivationError("a retired version is not also the current one")
        if any(key.version > current.version for key in retired):
            raise DerivationError("a retired version precedes the current one")
        self._retired = versions

    @property
    def write_key(self) -> HmacKey:
        """Newly written HMAC-derived values use the current active key version."""
        # [impl->req~proof-hmac-key-rotation-window~1]
        # [impl->req~proof-idp-account-key-rotation-window~2]
        return self._current

    def lookup_keys(self) -> tuple[HmacKey, ...]:
        """Old key versions may remain valid for lookup during a rotation window: the current
        version first, then every version still retained."""
        # [impl->req~proof-hmac-key-rotation-window~1]
        # [impl->req~proof-idp-account-key-rotation-window~2]
        return (self._current, *sorted(self._retired.values(), key=lambda key: -key.version))

    def key(self, version: int) -> HmacKey:
        if version == self._current.version:
            return self._current
        key = self._retired.get(version)
        if key is None:
            raise DerivationError(f"key version {version} is not retained for lookup")
        return key


# `preauth_subject_hash` is written and verified under the current active key alone: no retired
# version is kept for verifying it.
PREAUTH_RETAINS_RETIRED_KEYS: bool = False


def preauth_lookup_keys(ring: KeyRing) -> tuple[HmacKey, ...]:
    """The keys a `preauth_subject_hash` comparison may use: the current active one and no
    other, whatever the actor-subject ring still retains for `actor_subject_hash` lookup."""
    # [impl->req~proof-preauth-hash-current-key-only~1]
    if PREAUTH_RETAINS_RETIRED_KEYS:
        raise DerivationError("no retired key version verifies a preauth_subject_hash")
    return (ring.write_key,)


# --- The derivations --------------------------------------------------------------------------

# `HMAC-SHA-256`, for every family. Nothing here is a bare digest, a truncation, or an encoding.
HMAC_ALGORITHM: str = "sha256"
DIGEST_SIZE: int = hashlib.sha256().digest_size


@dataclass(frozen=True, slots=True)
class DerivedValue:
    """A derived identifier as it is persisted: the digest and the version of the key that
    produced it. `preauth_subject_hash` is the one family that records no version."""
    family: DerivationFamily
    digest: bytes
    key_version: int | None

    def __post_init__(self) -> None:
        if len(self.digest) != DIGEST_SIZE:
            raise DerivationError("a derived identifier is a full HMAC-SHA-256 digest")


def _digest(key: HmacKey, preimage: str) -> bytes:
    return hmac.new(key.secret, preimage.encode("utf-8"), hashlib.sha256).digest()


def actor_subject_preimage(issuer: str, subject: str) -> str:
    """`"actor-subject:v1:" || actor_issuer || ":" || canonical_actor_subject`."""
    # [impl->req~proof-family-actor-subject-hash~1]
    # [impl->req~proof-hmac-domain-separation~1]
    # [impl->req~proof-hmac-input-canonicalization~1]
    label = domain_label(DerivationFamily.actor_subject_hash)
    return f"{label}{canonical_issuer(issuer)}:{canonical_actor_subject(subject)}"


def actor_subject_hash(issuer: str, subject: str, ring: KeyRing) -> DerivedValue:
    """`actor_subject_hash = HMAC-SHA-256(k_actor_subject_vN, "actor-subject:v1:" ||
    actor_issuer || ":" || canonical_actor_subject)`, written under the current key version."""
    # [impl->req~proof-actor-subject-hash-hmac-sha256~1]
    # [impl->req~proof-family-actor-subject-hash~1]
    if ring.family is not KeyFamily.k_actor_subject:
        raise DerivationError("actor_subject_hash derives under k_actor_subject")
    key = ring.write_key
    return DerivedValue(family=DerivationFamily.actor_subject_hash,
                        digest=_digest(key, actor_subject_preimage(issuer, subject)),
                        key_version=key.version)


def preauth_subject_hash(issuer: str, subject: str, ring: KeyRing) -> DerivedValue:
    """`core.auth_challenges.preauth_subject_hash` is the `actor_subject_hash` derivation applied
    to a challenge's pre-auth identity — the same `HMAC-SHA-256` construction under the same key,
    over the same domain-separated preimage — so the challenge row holds a keyed verifier of the
    subject and never the subject itself. It is the one derived value that records no key
    version."""
    # [impl->req~proof-preauth-subject-hash-derivation~1]
    # [impl->req~proof-family-preauth-subject-hash~1]
    actor = actor_subject_hash(issuer, subject, ring)
    return DerivedValue(family=DerivationFamily.preauth_subject_hash,
                        digest=actor.digest,
                        key_version=None)


# A challenge whose stored verifier no longer matches is an identity mismatch: the completion is
# rejected, the client prepares a fresh challenge, and the short challenge lifetime — the shared
# 300-second TTL — makes that cheap.
PREAUTH_MISMATCH_RESULT: AuthEventResult = AuthEventResult.challenge_identity_mismatch


def preauth_subject_matches(stored: bytes | None, issuer: str, subject: str,
                            ring: KeyRing) -> bool:
    """Completion recomputes the verifier from this request's backend-verified subject and
    compares it against the stored value under the current active key alone. A challenge prepared
    before a key rotation therefore stops verifying after it."""
    # [impl->req~proof-preauth-hash-current-key-only~1]
    if stored is None:
        return False
    for key in preauth_lookup_keys(ring):
        candidate = _digest(key, actor_subject_preimage(issuer, subject))
        if secrets.compare_digest(stored, candidate):
            return True
    return False


def preauth_mismatch() -> tuple[AuthEventResult, ClientErrorClass]:
    """What a failed comparison is: `challenge_identity_mismatch`, surfacing through the shared
    registry as the class whose remediation is to prepare a fresh challenge."""
    # [impl->req~proof-preauth-hash-current-key-only~1]
    client_class = ClientErrorClass(surface(PREAUTH_MISMATCH_RESULT)[0])
    if client_class is not ClientErrorClass.challenge_required:
        raise DerivationError("a preauth mismatch tells the client to prepare a fresh challenge")
    return PREAUTH_MISMATCH_RESULT, client_class


def idp_account_preimage(provider: IdentityProvider, provider_account_id: str) -> str:
    """`"idp-account:v1:" || provider || ":" || canonical_provider_account_id`."""
    # [impl->req~proof-family-idp-account-hash~1]
    # [impl->req~proof-hmac-domain-separation~1]
    if provider not in REGISTERED_PROVIDERS:
        raise DerivationError(f"{provider} is never the provider component of an idp-account hash")
    label = domain_label(DerivationFamily.idp_account_hash)
    return f"{label}{provider}:{canonical_provider_account_id(provider, provider_account_id)}"


def idp_account_hash(provider: IdentityProvider, provider_account_id: str,
                     ring: KeyRing) -> DerivedValue:
    """`idp_account_hash = HMAC-SHA-256(k_idp_account_vN, "idp-account:v1:" || provider || ":" ||
    canonical_provider_account_id)`, where `provider` is the current linked identity's stored
    registered provider for `registered_account_grant` and the closed-classifier result — equal
    to that stored provider, `google` or `apple` and never `anonymous` — for the web
    anonymous-grant sign-in gate."""
    # [impl->req~proof-idp-account-hash-hmac-sha256~1]
    # [impl->req~proof-family-idp-account-hash~1]
    if ring.family is not KeyFamily.k_idp_account:
        raise DerivationError("idp_account_hash derives under k_idp_account")
    key = ring.write_key
    return DerivedValue(family=DerivationFamily.idp_account_hash,
                        digest=_digest(key, idp_account_preimage(provider, provider_account_id)),
                        key_version=key.version)


def idp_account_hash_under(version: int, provider: IdentityProvider, provider_account_id: str,
                           ring: KeyRing) -> bytes:
    """The same digest under a retained key version, for lookup during a rotation window."""
    # [impl->req~proof-idp-account-key-rotation-window~2]
    return _digest(ring.key(version), idp_account_preimage(provider, provider_account_id))


# --- What a persisted derived value must carry ------------------------------------------------

# Every persisted HMAC-derived value used for equality lookup or audit correlation carries the
# version of the key that produced it, so the backend can support rotation.
KEY_VERSIONED_FAMILIES: frozenset[DerivationFamily] = frozenset({
    DerivationFamily.actor_subject_hash,
    DerivationFamily.idp_account_hash,
})

# The one exception, which carries none.
UNVERSIONED_FAMILIES: frozenset[DerivationFamily] = frozenset({
    DerivationFamily.preauth_subject_hash,
})


def assert_persisted_key_version(value: DerivedValue) -> DerivedValue:
    """`actor_subject_hash` and `idp_account_hash` are persisted with their key version;
    `preauth_subject_hash` is persisted with none."""
    # [impl->req~proof-hmac-key-version-recorded~1]
    if value.family in KEY_VERSIONED_FAMILIES and value.key_version is None:
        raise DerivationError(f"{value.family} is persisted with the key version that produced it")
    if value.family in UNVERSIONED_FAMILIES and value.key_version is not None:
        raise DerivationError(f"{value.family} records no key version")
    return value


# --- Derivation strength ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DerivationSpec:
    """How a stored derived identifier is produced, as the registry records it."""
    construction: str
    keyed: bool
    digest_bits: int
    reversible: bool


# The three stored derived identifiers and their derivations. Each is a keyed, full-width
# `HMAC-SHA-256` digest: matching the entropy and the privacy of the value underneath it means a
# server-keyed construction, never a bare digest of a low-entropy value, a truncation that
# collides, or a reversible encoding.
DERIVED_IDENTIFIERS: dict[DerivationFamily, DerivationSpec] = {
    family: DerivationSpec(construction="HMAC-SHA-256", keyed=True,
                           digest_bits=DIGEST_SIZE * 8, reversible=False)
    for family in DerivationFamily
}


def assert_derivation_matches(family: DerivationFamily,
                              spec: DerivationSpec | None = None) -> DerivationSpec:
    """A server-side derived identifier stored for lookup, uniqueness or audit must match the
    entropy and privacy properties of the underlying value: a keyed construction an attacker
    cannot precompute, at full digest width, that no one can reverse."""
    # [impl->req~proof-derivation-matches-entropy-privacy~1]
    spec = spec if spec is not None else DERIVED_IDENTIFIERS[family]
    if not spec.keyed:
        raise DerivationError(f"{family} must be keyed, not a bare digest of the value")
    if spec.construction != "HMAC-SHA-256" or spec.digest_bits != DIGEST_SIZE * 8:
        raise DerivationError(f"{family} is a full-width HMAC-SHA-256 digest")
    if spec.reversible:
        raise DerivationError(f"{family} must not be reversible to the value it derives from")
    return spec


# --- Rotation persists no preimages -----------------------------------------------------------

# What a key rotation persists in PostgreSQL: key versions beside the derived values, and
# nothing else. Raw actor subjects and raw provider account identifiers are never persisted
# merely so a future rotation could recompute their hashes.
ROTATION_PERSISTED_COLUMNS: frozenset[str] = frozenset({
    "actor_subject_hash_key_version", "idp_account_hash_key_version",
})
ROTATION_FORBIDDEN_COLUMNS: frozenset[str] = frozenset({
    "actor_subject", "raw_subject", "subject", "preauth_subject",
    "provider_account_id", "raw_provider_account_id", "canonical_provider_account_id",
})


def assert_rotation_persists_no_preimages(columns: Iterable[str]) -> None:
    """Rotation support persists key versions, never the preimages. Raw actor subjects and raw
    provider account identifiers must not be persisted in PostgreSQL merely to support it — the
    identity row and the canonical registry keep what they keep for uniqueness reasons of their
    own, and a rotation adds nothing to them."""
    # [impl->req~proof-no-raw-subjects-for-rotation~1]
    # [impl->req~proof-no-raw-provider-account-ids-for-rotation~1]
    offending = sorted({column for column in columns
                        if column.lower() in ROTATION_FORBIDDEN_COLUMNS})
    if offending:
        raise DerivationError(f"{offending} must not be persisted merely to support rotation")


# --- Where the IDP-account inputs may come from -----------------------------------------------


class IdpInputSource(StrEnum):
    """Where a `provider` component or a `canonical_provider_account_id` was offered from."""
    stored_identity_binding = "stored_identity_binding"
    web_gate_validated_provider_data_entry = "web_gate_validated_provider_data_entry"
    client_input = "client_input"
    request_header = "request_header"
    token_claim = "token_claim"
    sign_in_provider_claim = "sign_in_provider_claim"
    email = "email"
    display_name = "display_name"


# The two permitted sources: the stored identity binding, and — for the web anonymous-grant
# sign-in gate alone — the sole server-side Firebase Admin entry that survived the closed
# classifier and the stored-binding equality checks. Both are backend-verified, which is also what
# makes them the only two sources the canonical registry's stable UID may be obtained from.
# [impl->req~schema-provider-accounts-uid-source-backend-verified~1]
IDP_INPUT_SOURCES: frozenset[IdpInputSource] = frozenset({
    IdpInputSource.stored_identity_binding,
    IdpInputSource.web_gate_validated_provider_data_entry,
})


def assert_idp_input_source(source: IdpInputSource) -> IdpInputSource:
    """Neither the `provider` component nor `canonical_provider_account_id` may come from client
    input, request headers, token claims including any sign-in-provider claim, email, or display
    name."""
    # [impl->req~proof-idp-hmac-inputs-not-from-client~1]
    # The stable UID the canonical registry is keyed on comes from the backend-verified stored
    # identity binding or the mandatory Firebase Admin `providerData` read, and from nowhere else.
    # [impl->req~schema-provider-accounts-uid-source-backend-verified~1]
    if source not in IDP_INPUT_SOURCES:
        raise DerivationError(f"an idp-account HMAC input never comes from {source}")
    return source


def registered_grant_canonical_provider_account_id(row: ExternalIdentityRow) -> str:
    """For `registered_account_grant`, `canonical_provider_account_id` is the stored
    `provider_uid` on the current linked `core.external_identities` row. It is never taken from
    client input, and the operation rejects when that stored value is absent."""
    # [impl->req~proof-registered-grant-canonical-provider-account-id~1]
    # [impl->req~proof-idp-hmac-inputs-not-from-client~1]
    assert_idp_input_source(IdpInputSource.stored_identity_binding)
    if row.provider not in REGISTERED_PROVIDERS or not row.provider_uid:
        raise DerivationError(
            "claim_registered_grant rejects when the linked row stores no provider_uid")
    return canonical_provider_account_id(row.provider, row.provider_uid)


def confirm_registered_binding(row: ExternalIdentityRow,
                               provider_data: Sequence[object]) -> IdentityProvider:
    """The registered claim's mandatory fail-closed Firebase Admin `providerData` confirmation of
    the stored binding, performed on every call. A live result that does not confirm both the
    stored `provider` and the stored `provider_uid` is a conflict that denies this free grant
    alone; it never rewrites the stored classification, whose columns this read leaves exactly as
    it found them, and no automatic registered-to-anonymous downgrade follows from it.

    Eligibility itself is `registered_grant_class_inputs`, which keys on stored state only."""
    # [impl->req~proof-registered-grant-canonical-provider-account-id~1]
    # [impl->req~sessions-registered-grant-keys-on-stored-state~1]
    before = (row.provider, row.provider_uid)
    live_provider = classify_provider(provider_data)
    confirm_stored_binding(row, live_provider=live_provider,
                           live_provider_uid=provider_uid_for(live_provider, provider_data))
    if (row.provider, row.provider_uid) != before:
        raise DerivationError("the confirmation never rewrites the stored binding")
    return live_provider


@dataclass(frozen=True, slots=True)
class WebGateAccount:
    """What the web anonymous-grant sign-in gate resolved: the classified registered provider
    that supplies the HMAC's `provider` component, and the sole validated entry's stable provider
    subject that is its `canonical_provider_account_id`."""
    provider: IdentityProvider
    canonical_provider_account_id: str


def web_gate_canonical_provider_account_id(row: ExternalIdentityRow,
                                           provider_data: Sequence[object]) -> WebGateAccount:
    """The claiming identity's stored provider must be `google` or `apple`; the complete
    server-side Firebase Admin `providerData` result must pass the closed classifier; and the
    classified provider and the sole entry's non-empty stable provider subject must equal the
    stored provider and the stored `provider_uid`. Only then is
    `canonical_provider_account_id` that sole validated entry's stable provider subject, with
    the classified registered provider supplying the `provider` component."""
    # [impl->req~proof-web-gate-canonical-provider-account-id~1]
    # [impl->req~proof-idp-hmac-inputs-not-from-client~1]
    assert_idp_input_source(IdpInputSource.web_gate_validated_provider_data_entry)
    if row.provider not in REGISTERED_PROVIDERS or not row.provider_uid:
        raise DerivationError("the claiming identity's stored provider must be google or apple")
    classified = classify_provider(provider_data)
    if classified is not row.provider:
        raise DerivationError("the classified provider must equal the stored provider")
    live_uid = provider_uid_for(classified, provider_data)
    if not live_uid or live_uid != row.provider_uid:
        raise DerivationError(
            "the sole entry's stable provider subject must equal the stored provider_uid")
    return WebGateAccount(provider=classified,
                          canonical_provider_account_id=canonical_provider_account_id(
                              classified, live_uid))


# --- The uniqueness anchor --------------------------------------------------------------------


class UniquenessAnchor(StrEnum):
    """What per-provider-account uniqueness may be enforced on."""
    stable_provider_uid = "stable_provider_uid"
    firebase_uid = "firebase_uid"
    idp_account_hash = "idp_account_hash"


# The stable provider UID, through the canonical `core.provider_accounts` registry.
UNIQUENESS_ANCHOR: UniquenessAnchor = UniquenessAnchor.stable_provider_uid


def assert_uniqueness_anchor(anchor: UniquenessAnchor) -> UniquenessAnchor:
    """The Firebase UID is not the uniqueness anchor: deleting and recreating a Firebase user for
    the same Google or Apple account can produce a new UID while the underlying provider subject
    stays the same. Nor is the `idp_account_hash`, which is only an alias of that subject."""
    # [impl->req~proof-firebase-uid-not-uniqueness-anchor~1]
    if anchor is not UNIQUENESS_ANCHOR:
        raise DerivationError(f"{anchor} is not the per-provider-account uniqueness anchor")
    return anchor


# `idp_account_hash` and its key version are recorded on `core.access_grants_anti_abuse` rows
# whose `grant_source` is `registered_account_grant`, and on web rows whose `grant_source` is
# `anonymous_device_grant`. On both they are a non-authoritative lookup and audit alias.
IDP_ACCOUNT_HASH_ALIAS_SOURCES: frozenset[str] = frozenset({
    "registered_account_grant", "anonymous_device_grant",
})
IDP_ACCOUNT_HASH_AUTHORITATIVE: bool = False


class IdpAccountAliasIndex:
    """The canonical registry as the two account-deduped gates see it: uniqueness enforced on the
    stable provider UID through `core.provider_accounts` and its per-gate consumption rows, with
    `idp_account_hash` kept beside them as a lookup and audit alias only."""

    def __init__(self, gates: ProviderAccountGates, ring: KeyRing) -> None:
        if ring.family is not KeyFamily.k_idp_account:
            raise DerivationError("the alias index derives under k_idp_account")
        self._gates = gates
        self._ring = ring
        self._known: tuple[ProviderAccount, ...] = ()

    def alias(self, account: ProviderAccount) -> DerivedValue:
        """The alias a consumption records, always under the current active key version."""
        # [impl->req~proof-idp-account-key-rotation-window~2]
        return idp_account_hash(account.provider, account.provider_uid, self._ring)

    def resolve(self, digest: bytes) -> ProviderAccount | None:
        """Resolve a digest produced under any retained key version back to the one canonical
        provider-account row. Every retained version resolves to the same row."""
        # [impl->req~proof-idp-account-key-rotation-window~2]
        for account in self._accounts():
            for key in self._ring.lookup_keys():
                candidate = idp_account_hash_under(key.version, account.provider,
                                                   account.provider_uid, self._ring)
                if secrets.compare_digest(digest, candidate):
                    return account
        return None

    def _accounts(self) -> tuple[ProviderAccount, ...]:
        return self._known

    @property
    def accounts(self) -> tuple[ProviderAccount, ...]:
        """The canonical `core.provider_accounts` rows the registry holds."""
        return self._accounts()

    def register(self, account: ProviderAccount) -> ProviderAccount:
        """Reserve the canonical `core.provider_accounts` row for a stable provider UID."""
        # [impl->req~proof-provider-accounts-registry-uniqueness~1]
        assert_uniqueness_anchor(UNIQUENESS_ANCHOR)
        existing = {(known.provider, known.provider_uid): known for known in self._known}
        found = existing.get((account.provider, account.provider_uid))
        if found is not None:
            return found
        self._known = (*self._known, account)
        return account

    def consume(self, account: ProviderAccount, kind: GateConsumptionKind,
                grant_id: UUID) -> DerivedValue:
        """Consume this account's gate. The consumption row is keyed by the canonical registry's
        provider account, not by the alias, so the alias never decides whether the gate is open —
        and rotating the alias key can never mint a new free grant or reopen a gate."""
        # [impl->req~proof-provider-accounts-registry-uniqueness~1]
        # [impl->req~proof-idp-rotation-never-mints-grant~1]
        if IDP_ACCOUNT_HASH_AUTHORITATIVE:
            raise DerivationError("idp_account_hash is never the authority for a gate")
        canonical = self.register(account)
        alias = assert_persisted_key_version(self.alias(canonical))
        self._gates.consume(canonical, kind, grant_id,
                            idp_account_hash=alias.digest,
                            hash_key_version=alias.key_version)
        return alias

    def consumed(self, account: ProviderAccount, kind: GateConsumptionKind) -> UUID | None:
        return self._gates.consumed_grant(self.register(account), kind)


def rotation_mints_no_grant(index: IdpAccountAliasIndex, account: ProviderAccount,
                            kind: GateConsumptionKind, grant_id: UUID) -> AuthEventResult:
    """A claim made after a key rotation, for an account whose gate was consumed under the old
    version, is still rejected: the gate is enforced on the canonical provider account. An
    implementation that could not guarantee this would not be allowed to rotate the key."""
    # [impl->req~proof-idp-rotation-never-mints-grant~1]
    try:
        index.consume(account, kind, grant_id)
    except GateAlreadyConsumedError as conflict:
        return conflict.result
    raise DerivationError("rotating a lookup-hash key must never reopen a consumed gate")


# The two operations whose derivation this module serves, named here so the endpoint layer can
# assert applicability without a second copy of the list.
IDP_HMAC_OPERATIONS: frozenset[AuthOperation] = frozenset({
    AuthOperation.claim_registered_grant,
    AuthOperation.claim_anonymous_grant,
})
