"""Restore proof: the store artifact, server-verified, and nothing else.

`POST /auth/restore-subscription` carries one piece of proof — the signed StoreKit transaction
on iOS or the Google Play purchase token on Android — and the backend verifies it against the
store itself. What that verification yields is a `(provider, external_id)` pair and a purchase
UUID, and those are inputs to subscription-entitlement restoration and to nothing else: not
ownership of a prior app account, not recovery of an anonymous identity, not an attestation
linkage, and not authority to move any app-owned data.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.invariants import DevicePlatform, ProofUse, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_endpoints import (
    ProofArtifact,
    assert_not_attestation_evidence,
    requires_attestation,
    restore_proof_applies_to,
    restore_proof_set,
)
from nativespeaker.api.exceptions import ServiceError
from nativespeaker.api.quota.usage import UsageRowError, assert_stays_with_grant


class RestoreProofError(RuntimeError):
    """Restore proof was about to be asked to carry something it does not carry."""


class InvalidRestoreProof(ServiceError):
    """The store artifact did not verify server-side."""
    status_code = 403
    error_code = "proof_rejected"


# --- Server-verifiable store proof ----------------------------------------------------------


# The two stores whose artifacts restore accepts, one per native platform: exactly
# `core.subscription_provider`, taken from the invariants file that defines it rather than declared a
# second time here, so no two distinct enumerations of the same column can drift apart or compare
# unequal by identity across modules.

# The store each calling platform fixes. Restore is native-only, so the web platform has none.
PLATFORM_STORE: dict[DevicePlatform, StoreProvider] = {
    DevicePlatform.ios: StoreProvider.apple,
    DevicePlatform.android: StoreProvider.google_play,
}

# Where a restore proof may be verified: on the server, against the store. There is no
# client-asserted verification result and no trusted client claim about the artifact.
CLIENT_ASSERTED_VERIFICATION: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class VerifiedStoreProof:
    """What server-side verification of the store artifact yields."""
    provider: StoreProvider
    external_id: str
    purchase_uuid: UUID


StoreVerifier = Callable[[StoreProvider, str], VerifiedStoreProof]


def assert_server_verifiable(artifact: str | None,
                             *, verified_by: str = "backend_store_verification") -> str:
    """Restore proof must be server-verifiable store proof: a signed StoreKit transaction or a
    Google Play purchase token the backend can check against the store, never a client assertion
    that some check already passed."""
    # [impl->req~proof-restore-server-verifiable-store-proof~1]
    if verified_by != "backend_store_verification" or CLIENT_ASSERTED_VERIFICATION:
        raise RestoreProofError(f"{verified_by} is not server-verifiable store proof")
    if not artifact or not str(artifact).strip():
        raise InvalidRestoreProof("restore proof is the store artifact itself")
    return artifact


# `restore_subscription` is not challenge-bearing: there is no operation challenge for
# restore-proof material to be bound into, and the store artifact is the endpoint's only proof.
# [impl->req~proof-restore-not-challenge-bearing~1]
RESTORE_CHALLENGES: frozenset[AuthOperation] = frozenset()
RESTORE_PROOF_ARTIFACTS: frozenset[ProofArtifact] = frozenset({ProofArtifact.store_artifact})


def assert_not_challenge_bearing(operation: AuthOperation = AuthOperation.restore_subscription,
                                 *, challenge_id: str | None = None) -> None:
    """There is no operation challenge for restore-proof material to be bound into."""
    # [impl->req~proof-restore-not-challenge-bearing~1]
    if operation in RESTORE_CHALLENGES or challenge_id is not None:
        raise RestoreProofError("restore_subscription is not challenge-bearing")
    if RESTORE_PROOF_ARTIFACTS != {ProofArtifact.store_artifact}:
        raise RestoreProofError("the store artifact is the endpoint's only proof")


# What the server-verified values may be used for: restoring subscription entitlement, and
# nothing else.
ENTITLEMENT_RESTORATION: str = "subscription_entitlement_restoration"


def verify_restore_proof(platform: DevicePlatform,
                         artifact: str | None,
                         verifier: StoreVerifier,
                         *,
                         used_for: str = ENTITLEMENT_RESTORATION,
                         other_artifacts: Sequence[ProofArtifact] = ()) -> VerifiedStoreProof:
    """At `POST /auth/restore-subscription` the server verifies the supplied restore proof
    server-side and uses the server-verified store subscription identity and the server-verified
    purchase UUID only as input to subscription-entitlement restoration."""
    # [impl->req~proof-restore-server-side-verification~1]
    if not restore_proof_applies_to(AuthOperation.restore_subscription):
        raise RestoreProofError("restore proof applies to restore_subscription")
    if used_for != ENTITLEMENT_RESTORATION:
        raise RestoreProofError(f"the verified store identity is no input to {used_for}")
    # The native-only rule and the platform's store-artifact family are `proof_endpoints`'.
    restore_proof_set(platform, store_artifact=artifact, other_artifacts=other_artifacts)
    assert_not_challenge_bearing()
    assert_server_verifiable(artifact)
    provider = PLATFORM_STORE[platform]
    verified = verifier(provider, str(artifact))
    if verified.provider is not provider or not verified.external_id:
        raise InvalidRestoreProof("verification resolved no store subscription identity")
    return verified


# The whole proof set: the store artifact. No attestation or integrity proof is required, and no
# other platform proof material is accepted.
# [impl->req~proof-restore-store-artifact-entire-proof-set~1]
RESTORE_ADDITIONAL_PROOF: frozenset[ProofArtifact] = frozenset()


def restore_entire_proof_set(platform: DevicePlatform,
                             *, artifact: str | None,
                             offered: Sequence[ProofArtifact] = ()) -> frozenset[ProofArtifact]:
    """Restore requires no attestation or integrity proof: the store artifact is the entire proof
    set, restore is native-only with the store fixed by the calling platform, and no other
    platform proof material is required or accepted."""
    # [impl->req~proof-restore-store-artifact-entire-proof-set~1]
    if requires_attestation(AuthOperation.restore_subscription) or RESTORE_ADDITIONAL_PROOF:
        raise RestoreProofError("the store artifact is restore's entire proof set")
    restore_proof_set(platform, store_artifact=artifact, other_artifacts=offered)
    return RESTORE_PROOF_ARTIFACTS


# --- What restore proof is not ------------------------------------------------------------------


# Source-anonymous-identity recovery material, in every shape this specification names. Restore
# is not parameterized by any of it.
# [impl->req~proof-restore-not-parameterized-by-recovery-material~1]
RECOVERY_MATERIAL_FIELDS: frozenset[str] = frozenset({
    "source_subject", "source_issuer", "source_user_id", "source_identity_id",
    "anonymous_subject", "anonymous_uid", "recovery_token", "recovery_code",
    "previous_identity", "attestation_key_id", "attestation_key_proof",
})


def assert_not_parameterized_by_recovery_material(body: Mapping[str, Any] | None) -> None:
    """Restore must not be parameterized by source-anonymous-identity recovery material."""
    # [impl->req~proof-restore-not-parameterized-by-recovery-material~1]
    offending = sorted(set(body or {}) & RECOVERY_MATERIAL_FIELDS)
    if offending:
        raise RestoreProofError(f"restore is not parameterized by {offending}")


# The roles restore proof is never accepted in.
RESTORE_PROOF_FORBIDDEN_ROLES: frozenset[ProofUse] = frozenset({
    ProofUse.identity, ProofUse.ownership, ProofUse.recovery, ProofUse.upgrade,
    ProofUse.account_resolution,
})


def assert_not_ownership_proof(role: ProofUse) -> None:
    """Restore proof is not proof of prior app-account ownership."""
    # [impl->req~proof-restore-not-ownership-proof~1]
    if role in RESTORE_PROOF_FORBIDDEN_ROLES:
        raise RestoreProofError(f"restore proof is no {role} proof")


# The linkages restore implies: none of them.
# [impl->req~proof-restore-no-attestation-linkage~1]
RESTORE_ATTESTATION_LINKAGES: frozenset[str] = frozenset()


def assert_no_attestation_linkage(linkage: str | None = None) -> None:
    """No attestation-key recovery or upgrade linkage is implied by restore."""
    # [impl->req~proof-restore-no-attestation-linkage~1]
    if RESTORE_ATTESTATION_LINKAGES:
        raise RestoreProofError("restore implies no attestation-key linkage")
    if linkage is not None:
        assert_not_attestation_evidence(ProofArtifact.attestation_key_proof, ProofUse.recovery)
        raise RestoreProofError(f"restore implies no {linkage} linkage")


# What restore proof must never authorize the movement of.
# [impl->req~proof-restore-moves-no-app-data~1]
IMMOVABLE_APP_DATA: frozenset[str] = frozenset({
    "chats", "messages", "external_identity", "access_grants", "profile_fields",
    "display_name", "email", "settings",
})

# The one piece of usage state restore touches: the monthly usage row attached to the
# subscription-backed grant it settles or creates, which stays attached to that same `grant_id`.
RESTORE_TOUCHED_USAGE: str = "monthly_usage_row_of_the_settled_subscription_grant"


@dataclass(frozen=True, slots=True)
class RestoreDataMovement:
    """What one restore moved: nothing but the usage row's continued attachment."""
    usage_state: str
    grant_id: UUID


def restore_data_movement(*, grant_id: UUID,
                          usage_row_grant_id: UUID,
                          moved: Sequence[str] = ()) -> RestoreDataMovement:
    """Restore proof must not authorize movement of chats, the user's single external identity
    row, non-subscription access grants, profile fields, or any other app-owned data from the
    prior account. Restore moves no access grant at all: the only usage state it touches is the
    monthly usage row attached to the subscription-backed grant it settles or creates, which
    stays attached to that same `grant_id`."""
    # [impl->req~proof-restore-moves-no-app-data~1]
    offending = sorted(set(moved) & IMMOVABLE_APP_DATA)
    if offending:
        raise RestoreProofError(f"restore proof authorizes no movement of {offending}")
    if set(moved) - {RESTORE_TOUCHED_USAGE}:
        raise RestoreProofError(f"restore moves nothing but {RESTORE_TOUCHED_USAGE}")
    # The counter stays with its grant for the life of that grant, and restore mints no fresh
    # one for a paid entitlement that already has one.
    # [impl->req~schema-user-monthly-usage-stays-with-grant~1]
    try:
        assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=usage_row_grant_id)
    except UsageRowError as error:
        raise RestoreProofError(str(error)) from None
    return RestoreDataMovement(usage_state=RESTORE_TOUCHED_USAGE, grant_id=grant_id)


# --- Live store-state verification ------------------------------------------------------------

# `04-subscription-restore-and-entitlement-transfer.md` owns live store-state verification in
# full: which branch requires it, the one-call rule with no in-request retries and no retry
# budget, its pre-transaction placement and the locked-phase freshness-and-correspondence
# recheck, the Apple App Store Server API and Google Play Developer API rules, the coalescing
# join condition, and the redaction and audit rules for the verification outcome. This file
# restates none of it.
# [impl->req~proof-live-store-verification-owned-by-restore-file~1]
LIVE_STORE_VERIFICATION_OWNER: str = "04-subscription-restore-and-entitlement-transfer.md"
LIVE_STORE_RULES_RESTATED_HERE: frozenset[str] = frozenset()


def live_store_verification_owner() -> str:
    """The owning file for live store-state verification. This file states none of its rules."""
    # [impl->req~proof-live-store-verification-owned-by-restore-file~1]
    if LIVE_STORE_RULES_RESTATED_HERE:
        raise RestoreProofError(f"{LIVE_STORE_VERIFICATION_OWNER} owns these rules")
    return LIVE_STORE_VERIFICATION_OWNER


def store_artifact_resolution_key(verified: VerifiedStoreProof) -> tuple[StoreProvider, str]:
    """This file's part is the proof itself: the store artifact is verified server-side under
    Restore Proof above, and the `(provider, external_id)` that verification resolves is the key
    the owning file's live verification and coalescing use."""
    # [impl->req~proof-store-artifact-resolves-provider-external-id~1]
    if not verified.external_id:
        raise RestoreProofError("verification resolves the (provider, external_id) key")
    return verified.provider, verified.external_id
