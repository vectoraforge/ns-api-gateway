"""The server-held operation challenge: its wire contract, its bound state, and its one-way
lifecycle.

"The challenge" is the `core.auth_challenges` row that `challenge_id` references. Nothing about
it is serialized to the client, so the row is the only authority for the operation, the
operation variant, the identity binding and expiry; the client holds one opaque handle and
nothing else.
"""

import base64
import hashlib
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider, variants_for

# The one challenge lifetime. Every challenge-issuing operation uses it and none overrides it.
CHALLENGE_TTL_SECONDS = 300
CHALLENGE_ID_BYTES = 16


class ChallengeError(RuntimeError):
    """A challenge was built, bound or moved in a way the contract forbids."""


# --- The wire contract -------------------------------------------------------------------


def new_challenge_id() -> str:
    """A single opaque value: 16 bytes from a CSPRNG, base64url-encoded without padding. It is
    both the lookup key for the server-side row and the nonce the completion echoes back, so no
    second nonce is ever issued, returned or compared."""
    # [impl->req~shared-wire-challenge-id-format~1]
    return base64.urlsafe_b64encode(secrets.token_bytes(CHALLENGE_ID_BYTES)).decode().rstrip("=")


def challenge_expires_at(now: datetime) -> datetime:
    """`expires_at` from the server's own clock at issuance. Never client-supplied, never
    extended, never renewed: there is no grace period and no sliding renewal on retry, so an
    expired challenge leaves the client only one remedy, a fresh prepare."""
    # [impl->req~shared-challenge-ttl~1]
    return now + timedelta(seconds=CHALLENGE_TTL_SECONDS)


class PrepareResponse(BaseModel):
    """The prepare response body: exactly two fields, disclosing nothing else about the
    challenge."""
    # [impl->req~shared-wire-prepare-response-fields~1]
    challenge_id: str
    expires_at: datetime


def challenge_ids_equal(presented: str, stored: str) -> bool:
    """Byte-for-byte against the stored value. Not trimmed, decoded and re-encoded, case-folded,
    defaulted, or otherwise reinterpreted."""
    # [impl->req~shared-wire-exact-comparison~1]
    return secrets.compare_digest(presented.encode("utf-8"), stored.encode("utf-8"))


def variants_equal(declared: str | None, stored: IdentityProvider | None) -> bool:
    """The completion's `provider` against the stored operation variant, by exact match.
    Completion applies the declaration it received; normalization happens only at prepare, so
    nothing here trims, case-folds or defaults."""
    # [impl->req~shared-wire-exact-comparison~1]
    # [impl->req~shared-challenge-variant-immutable~1]
    if stored is None:
        return declared is None
    return declared is not None and declared == stored.value


class NonceConvention(StrEnum):
    """How a provider flow embeds the nonce inside its external token."""
    raw = "raw"
    sha256_hex = "sha256_hex"


# --- The challenge row -------------------------------------------------------------------


class ChallengeState(StrEnum):
    """The lifecycle state the row carries: `issued` at prepare, then `claimed`, then
    `consumed`."""
    # [impl->req~shared-challenge-row-lifecycle-state~1]
    issued = "issued"
    claimed = "claimed"
    consumed = "consumed"


_ALLOWED_TRANSITIONS: dict[ChallengeState, frozenset[ChallengeState]] = {
    ChallengeState.issued: frozenset({ChallengeState.claimed}),
    ChallengeState.claimed: frozenset({ChallengeState.consumed}),
    ChallengeState.consumed: frozenset(),
}


def advance_state(current: ChallengeState, target: ChallengeState) -> ChallengeState:
    """The lifecycle runs in one direction only. A row is never moved back to `issued`, never
    reissued, and never reclaimed once it has left `issued`."""
    # [impl->req~shared-challenge-lifecycle-one-way~1]
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ChallengeError(f"a {current} challenge cannot become {target}")
    return target


@dataclass(frozen=True, slots=True)
class IdentityBinding:
    """The verified identity context the challenge binds: `bound_external_identity_id` for a
    linked identity, or `(preauth_issuer, preauth_subject_hash)` for a pre-auth identity, where
    the issuer is stored plaintext and the subject only as its keyed verifier, never raw."""
    # [impl->req~shared-challenge-row-identity-context~1]
    bound_external_identity_id: UUID | None = None
    preauth_issuer: str | None = None
    preauth_subject_hash: bytes | None = None

    def __post_init__(self) -> None:
        # Exactly one of the two identity contexts, mirroring whether the verified identity was
        # linked or unlinked at prepare time.
        linked = self.bound_external_identity_id is not None
        preauth = self.preauth_issuer is not None
        if linked == preauth:
            raise ChallengeError("a challenge binds exactly one identity context")
        if linked and self.preauth_subject_hash is not None:
            raise ChallengeError("a linked binding stores no pre-auth verifier")


@dataclass(frozen=True, slots=True)
class ChallengeRow:
    """One `core.auth_challenges` row. Every field the completion trusts is read from here."""
    # The row binds at least the challenge id, the operation, its normalized variant where the
    # operation defines one, the verified identity context, expiry, and its lifecycle state.
    # [impl->req~shared-challenge-row-bindings~1]
    challenge_id: str                                # [impl->req~shared-challenge-row-challenge-id~1]
    operation: AuthOperation                         # [impl->req~shared-challenge-row-operation~1]
    operation_variant: IdentityProvider | None       # [impl->req~shared-challenge-row-variant~1]
    binding: IdentityBinding                         # [impl->req~shared-challenge-row-identity-context~1]
    expires_at: datetime                             # [impl->req~shared-challenge-row-expires-at~1]
    state: ChallengeState = ChallengeState.issued
    claim_attempt_id: UUID | None = None
    id: UUID | None = None

    def __post_init__(self) -> None:
        # `operation_variant` is the normalized declaration for the operations that define one
        # and is absent for the two variant-free challenge-bearing operations.
        # [impl->req~shared-challenge-row-variant~1]
        allowed = variants_for(self.operation)
        if allowed and self.operation_variant not in allowed:
            raise ChallengeError(f"{self.operation} requires one of {allowed} as its variant")
        if not allowed and self.operation_variant is not None:
            raise ChallengeError(f"{self.operation} defines no operation variant")
        # Once claimed the row also carries the server-generated `claim_attempt_id` of the
        # completion attempt holding the claim.
        # [impl->req~shared-challenge-row-lifecycle-state~1]
        if (self.state is ChallengeState.issued) != (self.claim_attempt_id is None):
            raise ChallengeError("a claim_attempt_id exists exactly while the row is not issued")
        # A pre-auth binding carries the subject's keyed verifier until consumption clears it.
        # [impl->req~shared-challenge-row-identity-context~1]
        if (self.binding.preauth_issuer is not None and not self.binding.preauth_subject_hash
                and self.state is not ChallengeState.consumed):
            raise ChallengeError("an unconsumed pre-auth challenge stores the subject verifier")

    @property
    def is_preauth_bound(self) -> bool:
        return self.binding.preauth_issuer is not None

    @property
    def verifier_cleared(self) -> bool:
        """Consumption clears a pre-auth row's subject verifier as part of the transition."""
        return self.is_preauth_bound and not self.binding.preauth_subject_hash


# Material a challenge must never bind. Proof, restore proof, a reassignment target, a source
# anonymous identity and integrity material all arrive with the completion, never at prepare.
# [impl->req~shared-challenge-binds-no-proof-material~1]
FORBIDDEN_BINDINGS: frozenset[str] = frozenset({
    "proof", "proof_material", "restore_proof", "store_receipt", "transaction_id",
    "subscription_id", "reassignment_target", "target_user_id", "source_anonymous_identity",
    "source_user_id", "integrity_token", "attestation", "device_token", "devicecheck_token",
    "play_integrity_token", "bot_check_token", "id_token", "authorization_code",
})


def persisted_bindings(row: ChallengeRow) -> dict[str, Any]:
    """Everything the challenge row binds, by persisted field name."""
    return {"challenge_id": row.challenge_id,
            "operation": row.operation,
            "operation_variant": row.operation_variant,
            "bound_external_identity_id": row.binding.bound_external_identity_id,
            "preauth_issuer": row.binding.preauth_issuer,
            "preauth_subject_hash": row.binding.preauth_subject_hash,
            "expires_at": row.expires_at}


def assert_no_proof_material_bound(row: ChallengeRow,
                                   request_body: Mapping[str, Any] | None = None) -> None:
    """Fail closed on anything the challenge must not bind: proof material, restore-proof
    material, a subscription reassignment target, a source anonymous identity, or integrity
    material. Neither by field name nor by smuggling a request value into a bound field."""
    # [impl->req~shared-challenge-binds-no-proof-material~1]
    bound = persisted_bindings(row)
    for field in bound:
        if field in FORBIDDEN_BINDINGS:
            raise ChallengeError(f"a challenge must not bind {field}")
    values = {str(value) for value in bound.values() if value is not None}
    for field, supplied in (request_body or {}).items():
        if field in FORBIDDEN_BINDINGS and str(supplied) in values:
            raise ChallengeError(f"a challenge must not bind {field}")


def assert_nothing_serialized(response: PrepareResponse, row: ChallengeRow) -> None:
    """The challenge would have to be signed or MACed if it were serialized to the client. It is
    not: the response is the opaque handle plus expiry, and the handle carries no embedded
    operation, identity, provider or expiry claim, so no client-held payload exists for a
    signature to protect."""
    # [impl->req~shared-challenge-not-serialized~1]
    if set(response.model_dump()) != {"challenge_id", "expires_at"}:
        raise ChallengeError("the prepare response discloses more than the handle and expiry")
    claims = [str(row.operation), str(row.binding.preauth_issuer or ""),
              str(row.operation_variant or ""), str(row.binding.bound_external_identity_id or "")]
    for claim in claims:
        if claim and claim in response.challenge_id:
            raise ChallengeError("challenge_id must carry no claim about the challenge")


def provider_nonce(row: ChallengeRow, convention: NonceConvention) -> str:
    """Where a provider flow embeds a nonce inside an external token — Sign in with Apple and
    Firebase nonce binding — the same `challenge_id` is that nonce, hashed where the provider's
    convention requires it. The stored value is the comparand; a client-supplied copy is never
    trusted."""
    # [impl->req~shared-challenge-id-as-provider-nonce~1]
    if convention is NonceConvention.sha256_hex:
        return hashlib.sha256(row.challenge_id.encode("utf-8")).hexdigest()
    return row.challenge_id


def authoritative_binding(row: ChallengeRow) -> tuple[AuthOperation, IdentityProvider | None,
                                                      IdentityBinding, datetime]:
    """The operation, the operation variant, the identity binding and `expires_at`, taken from
    the server-held row alone. No completion-supplied copy of any of them is authoritative."""
    # [impl->req~shared-wire-server-held-state~1]
    return row.operation, row.operation_variant, row.binding, row.expires_at


# --- The store ---------------------------------------------------------------------------


class ClaimOutcome(StrEnum):
    """What the one atomic conditional update that claims a row did."""
    claimed = "claimed"
    expired = "expired"
    already_used = "already_used"
    not_found = "not_found"


class ConsumeOutcome(StrEnum):
    """What the one atomic conditional update that consumes a claimed row did."""
    consumed = "consumed"
    already_consumed_by_this_attempt = "already_consumed_by_this_attempt"
    lost = "lost"


class ChallengeStore(Protocol):
    """The whole serialization mechanism: one claim state on the challenge row and two atomic
    conditional updates. No distributed lock, no lease, no multi-phase commit with a provider,
    no cleanup job and no path that reclaims an in-flight challenge."""
    # [impl->req~shared-serialization-mechanism-scope~1]

    async def insert(self, row: ChallengeRow) -> None:
        """Persist one issued challenge, keyed by its `challenge_id`."""
        ...

    async def get(self, challenge_id: str) -> ChallengeRow | None:
        """Locate the row by `challenge_id`. `None` means the lookup definitively found no row."""
        ...

    async def claim(self, challenge_id: str, claim_attempt_id: UUID) -> ClaimOutcome:
        """The conditional update that moves `issued` to `claimed` for this attempt, and the
        only place expiry is ever evaluated."""
        ...

    async def consume(self, session: Any, challenge_id: str,
                      claim_attempt_id: UUID) -> ConsumeOutcome:
        """The conditional update that marks the row `consumed` for the claim-holding attempt,
        inside the caller's transaction."""
        ...


SubjectVerifier = Callable[[str], bytes]
