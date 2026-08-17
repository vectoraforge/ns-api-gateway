"""What the user-creation and anonymous-continuity flows require as proof — and what they do not.

`POST /auth/create-user`, `POST /auth/upgrade-anonymous` and `/auth/sync` all rest on the
Firebase ID token the shared pre-handler barrier verifies, plus — for the upgrade alone — the
mandatory Firebase Admin `providerData` confirmation. None of them takes an attestation,
integrity or device-check proof, and a device-check token is never an identity.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.barrier import VerifiedIdentityContext
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    ProviderDataReadPoint,
    assert_provider_data_read_point,
    matches_identity,
)
from nativespeaker.api.auth.onboarding import AuthorizationHeaderSource
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.upgrade import (
    UPGRADE_DEVICE_GRANT_BITS,
    UPGRADE_GRANT_WRITES,
    entry_linked_identity,
)
from nativespeaker.api.auth.users import (
    ATTESTATION_FIELDS,
    assert_no_attestation,
    assert_no_restore_proof,
    context_pair,
)


class ProofRequirementError(RuntimeError):
    """A flow of this split was about to be given, or asked for, proof it does not use."""


# The flows this split defines. `sync` is the read-only reconciliation both of the others send
# clients to; the two state-changing ones are the onboarding operations.
SPLIT_FLOWS: tuple[AuthOperation, ...] = (
    AuthOperation.create_user,
    AuthOperation.upgrade_anonymous_to_registered,
    AuthOperation.sync,
)

# The flows requiring an attestation-key proof: none of them.
ATTESTATION_PROOF_FLOWS: frozenset[AuthOperation] = frozenset()


def requires_attestation_proof(operation: AuthOperation) -> bool:
    """No flow in this split requires an attestation-key proof."""
    # [impl->req~users-no-attestation-proof-required~1]
    if operation not in SPLIT_FLOWS:
        raise ProofRequirementError(f"{operation} is not a flow of this split")
    return operation in ATTESTATION_PROOF_FLOWS


# What plain `POST /auth/create-user` requires beyond the verified ID token and its challenge.
CREATE_USER_PROOF_MATERIAL: frozenset[str] = frozenset()


def create_user_proof_material(body: Mapping[str, Any] | None = None) -> frozenset[str]:
    """Plain `POST /auth/create-user` requires no attestation or integrity proof: a request that
    carries either is refused rather than verified, and the operation asks for none."""
    # [impl->req~users-create-user-no-integrity-proof~1]
    if requires_attestation_proof(AuthOperation.create_user) or CREATE_USER_PROOF_MATERIAL:
        raise ProofRequirementError("plain create-user takes no attestation or integrity proof")
    assert_no_attestation(body)
    assert_no_restore_proof(body)
    return CREATE_USER_PROOF_MATERIAL


@dataclass(frozen=True, slots=True)
class UpgradeProofBasis:
    """The three things `POST /auth/upgrade-anonymous` rests on, and nothing else."""
    verified_pair: tuple[str, str]
    linked_identity_id: UUID
    confirmed_provider: IdentityProvider


# The gateway's JWT filter serves edge admission and rate-limit keying alone; it establishes no
# backend identity context and rewrites no header.
GATEWAY_JWT_FILTER_ROLES: frozenset[str] = frozenset({"edge_admission", "rate_limit_keying"})
FORBIDDEN_GATEWAY_JWT_FILTER_ROLES: frozenset[str] = frozenset({
    "backend_identity_context", "authorization_header_rewrite"})


def upgrade_proof_basis(context: VerifiedIdentityContext, row: ExternalIdentityRow, *,
                        confirmed_provider: IdentityProvider,
                        read_point: ProviderDataReadPoint =
                        ProviderDataReadPoint.upgrade_anonymous_completion,
                        header: AuthorizationHeaderSource =
                        AuthorizationHeaderSource.unchanged_client_header) -> UpgradeProofBasis:
    """`POST /auth/upgrade-anonymous` relies on the Firebase ID token the backend's shared
    pre-handler barrier verified cryptographically to establish `(issuer, subject)`, on the
    existing linked identity row for that same pair, and on the mandatory issuer-selected
    Firebase Admin `providerData` confirmation of the client-declared provider. The gateway
    forwards the client's `Authorization` header unchanged; its JWT filter serves only edge
    admission and rate-limit keying."""
    # [impl->req~users-upgrade-proof-basis~1]
    if requires_attestation_proof(AuthOperation.upgrade_anonymous_to_registered):
        raise ProofRequirementError("the upgrade rests on no attestation-key proof")
    if header is not AuthorizationHeaderSource.unchanged_client_header:
        raise ProofRequirementError(f"{header} is not the upgrade's authentication")
    if GATEWAY_JWT_FILTER_ROLES & FORBIDDEN_GATEWAY_JWT_FILTER_ROLES:
        raise ProofRequirementError("the gateway JWT filter establishes no identity context")
    issuer, subject = context_pair(context)
    identity_id = entry_linked_identity(context, row=row)
    if not matches_identity(row, issuer, subject) or identity_id != row.id:
        raise ProofRequirementError("the linked identity row is the one for the verified pair")
    if assert_provider_data_read_point(read_point) is not \
            ProviderDataReadPoint.upgrade_anonymous_completion:
        raise ProofRequirementError("the confirmation is the upgrade completion's own read")
    if confirmed_provider not in REGISTERED_PROVIDERS:
        raise ProofRequirementError("the confirmation names the declared registered provider")
    return UpgradeProofBasis(verified_pair=(issuer, subject), linked_identity_id=identity_id,
                             confirmed_provider=confirmed_provider)


# What `/auth/sync` accepts, what it writes, and which device state it touches.
SYNC_ACCEPTED_CREDENTIALS: tuple[str, ...] = ("authorization_bearer_firebase_id_token",)
SYNC_WRITES: frozenset[str] = frozenset()
SYNC_DEVICE_STATE_ACCESS: frozenset[str] = frozenset()


def sync_request_credentials(context: VerifiedIdentityContext, *,
                             offered: Sequence[str] = (),
                             header: AuthorizationHeaderSource =
                             AuthorizationHeaderSource.unchanged_client_header
                             ) -> tuple[str, str]:
    """`/auth/sync` accepts only the Firebase ID token in the unchanged client `Authorization`
    header; the shared pre-handler barrier verifies it cryptographically and the read-only
    request is resolved from the verified `iss` and `sub`. It requires no attestation or
    device-check proof and neither reads nor modifies per-device grant state."""
    # [impl->req~users-auth-sync-token-only~1]
    if header is not AuthorizationHeaderSource.unchanged_client_header:
        raise ProofRequirementError(f"{header} is not /auth/sync's authentication")
    extra = sorted(set(offered) - set(SYNC_ACCEPTED_CREDENTIALS))
    if extra:
        raise ProofRequirementError(f"/auth/sync accepts no {extra}")
    if requires_attestation_proof(AuthOperation.sync) or SYNC_DEVICE_STATE_ACCESS or SYNC_WRITES:
        raise ProofRequirementError("/auth/sync stays read-only and reads no device state")
    return context_pair(context)


class DeviceCheckUse(StrEnum):
    """What a caller can ask a device-check proof token to be."""
    verified_identity = "verified_identity"
    account_resolution = "account_resolution"
    grant_anti_abuse = "grant_anti_abuse"


# The one thing a device-check proof token is: per-device free-grant anti-abuse state, defined
# in the grant files. It is never identity.
DEVICE_CHECK_USES: frozenset[DeviceCheckUse] = frozenset({DeviceCheckUse.grant_anti_abuse})


def assert_device_check_use(use: DeviceCheckUse) -> DeviceCheckUse:
    """A device-check proof token is not an identity token and must not be treated as verified
    identity: where this split refers to grant anti-abuse the mechanism is the per-device
    device-check state defined in other files, and `POST /auth/upgrade-anonymous` neither reads
    nor modifies that state."""
    # [impl->req~users-device-check-not-identity~1]
    if use not in DEVICE_CHECK_USES:
        raise ProofRequirementError(f"a device-check proof token is not {use}")
    if UPGRADE_DEVICE_GRANT_BITS or UPGRADE_GRANT_WRITES:
        raise ProofRequirementError("the upgrade reads and modifies no per-device grant state")
    return use


def assert_not_identity_material(fields: Sequence[str]) -> None:
    """Attestation and device-check material never establishes an identity context."""
    # [impl->req~users-device-check-not-identity~1]
    offending = sorted(set(fields) & ATTESTATION_FIELDS)
    if offending:
        raise ProofRequirementError(f"{offending} are not verified identity")
