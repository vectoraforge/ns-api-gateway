"""Which endpoint requires which proof — and, mostly, which requires none.

No endpoint in this specification requires an attestation proof or accepts one as evidence of
identity, ownership, recovery or upgrade. What the free-grant claims require is anti-abuse device
state from a vendor, and what `POST /auth/restore-subscription` requires is a store artifact. The
requesting identity behind every one of them is the backend-verified token, resolved once per
request by the shared barrier.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import VerifiedIdentityContext
from nativespeaker.api.auth.derived_identifiers import (
    IDP_HMAC_OPERATIONS,
    DerivationError,
    IdpAccountAliasIndex,
    WebGateAccount,
    confirm_registered_binding,
    registered_grant_canonical_provider_account_id,
    web_gate_canonical_provider_account_id,
)
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    IdentityError,
    ProviderClassificationError,
    ProviderLookupFailedError,
    ProviderUidSource,
    assert_provider_data_read_point,
    assert_provider_uid_source,
    matches_identity,
)
from nativespeaker.api.auth.integration import FirebaseIntegrations
from nativespeaker.api.auth.invariants import (
    DevicePlatform,
    GateConsumptionKind,
    ProofUse,
    ProviderAccount,
    assert_device_check_proof_use,
)
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.taxonomy import ClientErrorClass, ProviderDataReadPoint, surface
from nativespeaker.api.auth.upgrade import UPGRADE_DEVICE_GRANT_BITS, UPGRADE_GRANT_WRITES
from nativespeaker.api.auth.users import ATTESTATION_FIELDS
from nativespeaker.api.exceptions import ServiceError


class ProofApplicabilityError(RuntimeError):
    """An endpoint was about to be given, or asked for, proof it does not use."""


# --- The requesting identity ------------------------------------------------------------------


class IdentityInput(StrEnum):
    """Everything a request carries that might be offered as the requesting identity."""
    verified_id_token_claims = "verified_id_token_claims"
    request_header = "request_header"
    body_field = "body_field"
    query_parameter = "query_parameter"
    cookie = "cookie"
    proof_artifact = "proof_artifact"


# The one input that establishes identity: the backend-verified `iss` and `sub` of the Firebase
# ID token the client presented as its `Authorization` bearer credential.
IDENTITY_INPUTS: frozenset[IdentityInput] = frozenset({IdentityInput.verified_id_token_claims})

# Who resolves it, and how often. The sessions file owns the mechanics.
IDENTITY_RESOLUTION_OWNER: str = "shared_authentication_and_identity_resolution_barrier"
IDENTITY_RESOLUTIONS_PER_REQUEST: int = 1


def requesting_identity(context: VerifiedIdentityContext,
                        *,
                        source: IdentityInput = IdentityInput.verified_id_token_claims,
                        resolutions: int = IDENTITY_RESOLUTIONS_PER_REQUEST) -> tuple[str, str]:
    """The requesting identity, the current issuer and the current subject all mean the same
    thing: the backend-verified `iss` and `sub` claims of the presented Firebase ID token,
    resolved once per request by the shared authentication-and-identity-resolution barrier. No
    header, body field, query parameter, cookie, or proof artifact may contribute to it."""
    # [impl->req~proof-requesting-identity-from-token~1]
    if source not in IDENTITY_INPUTS:
        raise ProofApplicabilityError(f"{source} never contributes to the requesting identity")
    if resolutions != IDENTITY_RESOLUTIONS_PER_REQUEST:
        raise ProofApplicabilityError("the identity is resolved once per request, by the barrier")
    if not context.issuer or not context.subject:
        raise ProofApplicabilityError("the barrier resolved no verified issuer and subject")
    return context.issuer, context.subject


# --- Attestation: required by nothing, accepted as evidence by nothing -------------------------


class ProofArtifact(StrEnum):
    """The proof-carrying artifacts this specification names."""
    attestation_key_proof = "attestation_key_proof"
    attestation_blob = "attestation_blob"
    integrity_proof = "integrity_proof"
    store_artifact = "store_artifact"
    devicecheck_query_token = "devicecheck_query_token"
    devicecheck_update_token = "devicecheck_update_token"
    play_integrity_verdict = "play_integrity_verdict"
    turnstile_token = "turnstile_token"


# Attestation and integrity proof, as distinct from anti-abuse vendor material and store proof.
ATTESTATION_ARTIFACTS: frozenset[ProofArtifact] = frozenset({
    ProofArtifact.attestation_key_proof,
    ProofArtifact.attestation_blob,
    ProofArtifact.integrity_proof,
})

# The endpoints that require an attestation proof: none of the seven.
ATTESTATION_REQUIRING_OPERATIONS: frozenset[AuthOperation] = frozenset()

# The roles an attestation artifact is never accepted in. It is not an identity token, an
# ownership credential, a recovery credential, an upgrade credential, or an account-resolution
# input, and no endpoint verifies an attestation-key proof to establish one.
ATTESTATION_FORBIDDEN_ROLES: frozenset[ProofUse] = frozenset(set(ProofUse))

# What is challenge-bound in this specification: the server-issued operation challenge, never a
# piece of vendor anti-abuse material.
CHALLENGE_BOUND_ARTIFACTS: frozenset[ProofArtifact] = frozenset()


def requires_attestation(operation: AuthOperation) -> bool:
    """No endpoint requires an attestation proof."""
    # [impl->req~proof-no-endpoint-requires-attestation~1]
    # [impl->req~proof-no-attestation-key-verification~1]
    if operation not in set(AuthOperation):
        raise ProofApplicabilityError(f"{operation} is no endpoint of this specification")
    return operation in ATTESTATION_REQUIRING_OPERATIONS


def assert_not_attestation_evidence(artifact: ProofArtifact, role: ProofUse) -> None:
    """No endpoint accepts an attestation or integrity proof as identity, ownership, recovery or
    upgrade evidence, and none verifies an attestation-key proof to establish any of them or to
    resolve an account."""
    # [impl->req~proof-no-endpoint-requires-attestation~1]
    # [impl->req~proof-no-attestation-key-verification~1]
    if artifact in ATTESTATION_ARTIFACTS and role in ATTESTATION_FORBIDDEN_ROLES:
        raise ProofApplicabilityError(f"an {artifact} is never {role} evidence")


def assert_anti_abuse_device_state_only(artifacts: Sequence[ProofArtifact]) -> None:
    """The vendor material the free-grant claims require is anti-abuse device state and nothing
    else: none of it is challenge-bound attestation proof, and none of it is identity."""
    # [impl->req~proof-no-endpoint-requires-attestation~1]
    for artifact in artifacts:
        if artifact in ATTESTATION_ARTIFACTS or artifact in CHALLENGE_BOUND_ARTIFACTS:
            raise ProofApplicabilityError(f"{artifact} is not anti-abuse device state")
        assert_device_check_proof_use(ProofUse.anti_abuse_gate)


# --- `POST /auth/restore-subscription` ---------------------------------------------------------


class RestoreRejected(ServiceError):
    """A restore call that presented no native store-artifact family. The store is fixed by the
    calling platform, so this is a structural refusal under the shared class."""
    status_code = 403
    error_code = "operation_not_allowed"


# Restore proof applies to exactly one operation.
RESTORE_PROOF_OPERATIONS: frozenset[AuthOperation] = frozenset({AuthOperation.restore_subscription})

# The store artifact family each native platform presents: the signed StoreKit transaction on
# iOS and the Google Play purchase token on Android. The web platform has none.
NATIVE_STORE_ARTIFACTS: dict[DevicePlatform, str] = {
    DevicePlatform.ios: "signed_storekit_transaction",
    DevicePlatform.android: "google_play_purchase_token",
}


def restore_proof_applies_to(operation: AuthOperation) -> bool:
    """Restore proof applies to `POST /auth/restore-subscription` only."""
    # [impl->req~proof-restore-proof-scope~2]
    return operation in RESTORE_PROOF_OPERATIONS


def restore_proof_set(platform: DevicePlatform,
                      *,
                      store_artifact: str | None,
                      other_artifacts: Sequence[ProofArtifact] = ()) -> str:
    """`POST /auth/restore-subscription` accepts the store artifact alone — the signed StoreKit
    transaction or the Google Play purchase token — and is native-only, with the store fixed by
    the calling platform. A web call, or any call presenting no native store-artifact family, is
    rejected with `operation_not_allowed`."""
    # [impl->req~proof-no-endpoint-requires-attestation~1]
    # [impl->req~proof-restore-proof-scope~2]
    if requires_attestation(AuthOperation.restore_subscription):
        raise ProofApplicabilityError("restore requires no attestation or integrity proof")
    for artifact in other_artifacts:
        assert_not_attestation_evidence(artifact, ProofUse.ownership)
        if artifact is not ProofArtifact.store_artifact:
            raise ProofApplicabilityError(f"restore accepts no {artifact}")
    family = NATIVE_STORE_ARTIFACTS.get(platform)
    if family is None or not store_artifact:
        raise RestoreRejected("restore is native-only and takes the platform's store artifact")
    return family


# --- `POST /auth/create-user` -------------------------------------------------------------------

# What the device-check signal gates, and what it never gates.
DEVICE_CHECK_GATES: frozenset[str] = frozenset({"free_credit_grant_eligibility"})
DEVICE_CHECK_NEVER_GATES: frozenset[str] = frozenset({"account_creation_volume"})


def create_user_takes_no_device_check(*,
                                      phase: RequestMode,
                                      variant: IdentityProvider,
                                      body: Mapping[str, Any] | None = None) -> frozenset[str]:
    """`POST /auth/create-user` requires no attestation proof, integrity proof, or device check in
    either phase or in either its anonymous or registered form. The device-check signal gates
    free-credit grant eligibility only and is never a control on account-creation volume."""
    # [impl->req~proof-create-user-no-device-check~1]
    if phase not in set(RequestMode) or variant not in set(IdentityProvider):
        raise ProofApplicabilityError("create-user has two phases and three variants")
    if requires_attestation(AuthOperation.create_user):
        raise ProofApplicabilityError("create-user requires no attestation proof")
    offered = sorted(set(body or {}) & ATTESTATION_FIELDS)
    if offered:
        raise ProofApplicabilityError(f"create-user takes no {offered} in {phase}")
    if DEVICE_CHECK_GATES & DEVICE_CHECK_NEVER_GATES:
        raise ProofApplicabilityError(
            "the device-check signal never controls account-creation volume")
    return frozenset()


# --- `POST /auth/claim-anonymous-grant` ----------------------------------------------------------


class ClaimBranch(StrEnum):
    """The anonymous free-credit grant's two paths, and the native one's two platforms."""
    native_ios = "native_ios"
    native_android = "native_android"
    web = "web"


# What gates each branch. The native branches are gated by per-device device-check state; the web
# branch by a server-side Firebase sign-in check, deduplicated per provider account.
BRANCH_GATE_MATERIAL: dict[ClaimBranch, frozenset[ProofArtifact]] = {
    ClaimBranch.native_ios: frozenset({ProofArtifact.devicecheck_query_token,
                                       ProofArtifact.devicecheck_update_token}),
    ClaimBranch.native_android: frozenset({ProofArtifact.play_integrity_verdict}),
    ClaimBranch.web: frozenset({ProofArtifact.turnstile_token}),
}

# What the claim enrolls on `core.external_identities`, and what it stores on the grant
# anti-abuse record: no attestation-key-derived identifier, on either.
CLAIM_TIME_IDENTITY_ENROLMENTS: frozenset[str] = frozenset()
ANTI_ABUSE_ATTESTATION_IDENTIFIERS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class AnonymousGrantGate:
    """How this branch of the anonymous grant is gated, and what the material is trusted for."""
    branch: ClaimBranch
    material: frozenset[ProofArtifact]
    dedup_key: str | None


def claim_anonymous_grant_gate(branch: ClaimBranch,
                               *,
                               client_material_role: ProofUse = ProofUse.anti_abuse_gate,
                               enrols_identity: Sequence[str] = (),
                               anti_abuse_identifiers: Sequence[str] = ()) -> AnonymousGrantGate:
    """The anonymous free-credit grant has a native and a web path. The native path is gated by
    per-device device-check state — Apple DeviceCheck on iOS, Google Play Integrity / Device
    Recall on Android where Device Recall is available. Client-supplied device-check or integrity
    material is untrusted request-body input used only for the required vendor read and write: it
    is never an identity token and never resolves which account a request belongs to. The web path
    is gated by a server-side Firebase sign-in check and deduplicated per provider account via
    `idp_account_hash`. The backend enrols no attestation-key-derived identifier on
    `core.external_identities` at claim time and stores none on the grant anti-abuse record."""
    # [impl->req~proof-claim-anonymous-grant-gating-paths~1]
    material = BRANCH_GATE_MATERIAL[branch]
    assert_anti_abuse_device_state_only(sorted(material))
    if client_material_role is not ProofUse.anti_abuse_gate:
        raise ProofApplicabilityError(
            f"client-supplied vendor material is never {client_material_role}")
    if set(enrols_identity) - CLAIM_TIME_IDENTITY_ENROLMENTS:
        raise ProofApplicabilityError(
            "no attestation-key-derived identifier is enrolled on core.external_identities")
    if set(anti_abuse_identifiers) - ANTI_ABUSE_ATTESTATION_IDENTIFIERS:
        raise ProofApplicabilityError(
            "no attestation-key-derived identifier is stored on the anti-abuse record")
    dedup = "idp_account_hash" if branch is ClaimBranch.web else None
    return AnonymousGrantGate(branch=branch, material=material, dedup_key=dedup)


# --- `POST /auth/upgrade-anonymous` --------------------------------------------------------------

# The flip's shape, as this split refers to it.
UPGRADE_IS_IN_PLACE: bool = True
UPGRADE_RETIRES_ATTESTATION_BINDING: bool = False
IDENTITY_ROWS_PER_USER: int = 1


def upgrade_in_place_flip(row: ExternalIdentityRow,
                          *,
                          provider: IdentityProvider,
                          provider_uid: str,
                          identity_rows_for_user: int = IDENTITY_ROWS_PER_USER,
                          device_state_touched: Sequence[str] = (),
                          grants_minted: Sequence[str] = (),
                          interrupted_registration: bool = False) -> ExternalIdentityRow:
    """Anonymous-to-registered upgrade is an in-place provider flip on the existing
    `core.external_identities` row that keeps the same `(issuer, subject)`. It is not an
    attestation-key-proven transition, not a retire-and-attach transition, and retires no enrolled
    attestation-key binding. It reads, sets and clears no vendor per-device device-check state and
    mints no grant — including when it completes a registration interrupted after the provider
    link succeeded. Each `core.users` row maps to a single `core.external_identities` row."""
    # [impl->req~proof-upgrade-in-place-provider-flip~1]
    if requires_attestation(AuthOperation.upgrade_anonymous_to_registered):
        raise ProofApplicabilityError("the flip is not an attestation-key-proven transition")
    if not UPGRADE_IS_IN_PLACE or UPGRADE_RETIRES_ATTESTATION_BINDING:
        raise ProofApplicabilityError("the flip retires and attaches nothing")
    if provider not in REGISTERED_PROVIDERS:
        raise ProofApplicabilityError(f"{provider} is not a registered provider")
    if identity_rows_for_user != IDENTITY_ROWS_PER_USER:
        raise ProofApplicabilityError("each core.users row maps to one external identity row")
    if set(device_state_touched) | UPGRADE_DEVICE_GRANT_BITS:
        raise ProofApplicabilityError(
            "the flip reads, sets and clears no vendor per-device device-check state")
    if set(grants_minted) | UPGRADE_GRANT_WRITES:
        raise ProofApplicabilityError(
            f"the flip mints no grant, interrupted_registration={interrupted_registration}")
    flipped = ExternalIdentityRow(id=row.id, user_id=row.user_id, issuer=row.issuer,
                                  subject=row.subject, provider=provider,
                                  provider_uid=provider_uid,
                                  identity_state=row.identity_state,
                                  native_claim_platform=row.native_claim_platform,
                                  free_grant_consumed_at=row.free_grant_consumed_at)
    if not matches_identity(flipped, row.issuer, row.subject) or flipped.id != row.id:
        raise ProofApplicabilityError("the flip keeps the same row and the same (issuer, subject)")
    return flipped


# --- Where IDP-account HMAC derivation applies ----------------------------------------------------


def idp_hmac_applies(operation: AuthOperation,
                     *, branch: ClaimBranch | None = None) -> bool:
    """IDP-account HMAC derivation applies to `POST /auth/claim-registered-grant` and to the web
    sign-in gate for `POST /auth/claim-anonymous-grant` — not to that endpoint's native paths, and
    to no other operation. The derived hash is a non-authoritative lookup and audit alias: gate
    uniqueness is enforced on the stable provider UID through the canonical
    `core.provider_accounts` registry and its per-gate consumption rows."""
    # [impl->req~proof-idp-hmac-applicability~1]
    if operation not in IDP_HMAC_OPERATIONS:
        return False
    if operation is AuthOperation.claim_anonymous_grant:
        return branch is ClaimBranch.web
    return True


def registered_grant_idp_account(row: ExternalIdentityRow,
                                 provider_data: Sequence[object],
                                 *,
                                 read_point: ProviderDataReadPoint =
                                 ProviderDataReadPoint.claim_registered_grant_completion) -> str:
    """For `claim_registered_grant`, the backend derives `canonical_provider_account_id` from the
    stored `provider_uid` on the current linked `core.external_identities` row. It never takes
    that identifier from client input, the operation rejects when the row has no stored
    `provider_uid`, and every call additionally performs a mandatory fail-closed Firebase Admin
    `providerData` confirmation of the stored binding. A divergent result is a conflict that
    denies only the free grant and never rewrites the stored binding. The closed enumeration of
    read points stays the identity files'."""
    # [impl->req~proof-idp-hmac-applicability~1]
    if not idp_hmac_applies(AuthOperation.claim_registered_grant):
        raise ProofApplicabilityError("claim_registered_grant derives an idp_account_hash")
    if assert_provider_data_read_point(read_point) is not \
            ProviderDataReadPoint.claim_registered_grant_completion:
        raise ProofApplicabilityError("the confirmation is the registered claim's own read point")
    # The identifier comes from the stored binding, never from a client-supplied field.
    assert_provider_uid_source(ProviderUidSource.firebase_provider_data)
    canonical = registered_grant_canonical_provider_account_id(row)
    confirm_registered_binding(row, provider_data)
    return canonical


# --- The web anonymous-grant sign-in gate ---------------------------------------------------------


class GateDenied(ServiceError):
    """The classifier, the stored-provider equality or the stored-`provider_uid` equality failed.
    The free grant is denied and nothing else is."""
    status_code = 403
    error_code = "verification_required"


# What a failed web-gate lookup may deny: the free grant on this one endpoint, and nothing else.
GATE_DENIES: frozenset[AuthOperation] = frozenset({AuthOperation.claim_anonymous_grant})

# The paths a failed, indeterminate, invalid-shape or non-matching Admin lookup must never deny.
GATE_NEVER_DENIES: frozenset[AuthOperation] = frozenset(set(AuthOperation) - GATE_DENIES)
GATE_NEVER_DENIES_PAID_ENTITLEMENT: bool = True

# What an unavailable lookup audits as, as distinct from the classifier's own denial.
GATE_UNAVAILABLE_RESULT: AuthEventResult = AuthEventResult.firebase_lookup_unavailable


def web_gate_admin_client(integrations: FirebaseIntegrations, issuer: str) -> Any:
    """The Admin lookup runs through the Admin client of the single configured Firebase
    integration selected by the request's verified issuer match; the sessions file owns the
    selection mechanics."""
    # [impl->req~proof-web-gate-provider-data-classifier~1]
    return integrations.admin_client_for_issuer(issuer)


def web_anonymous_grant_gate(row: ExternalIdentityRow,
                             provider_data: Sequence[object] | None,
                             *,
                             lookup_failure: ProviderLookupFailedError | None = None,
                             read_point: ProviderDataReadPoint =
                             ProviderDataReadPoint.web_anonymous_grant_gate) -> WebGateAccount:
    """The web gate's closed classifier over the complete server-side Firebase Admin
    `providerData` result. The claiming identity's stored provider must be `google` or `apple`;
    no entries classifies as `anonymous`; exactly one `google.com` entry is `google` and exactly
    one `apple.com` entry is `apple`; every other shape — both providers, multiple entries, or
    any unrecognized entry — rejects the grant. Merely finding one matching entry is never
    sufficient. The classified provider must equal the stored provider and the sole entry's
    non-empty stable provider subject must equal the stored `provider_uid`."""
    # [impl->req~proof-web-gate-provider-data-classifier~1]
    if assert_provider_data_read_point(read_point) is not \
            ProviderDataReadPoint.web_anonymous_grant_gate:
        raise ProofApplicabilityError("this is the web anonymous-grant gate's own read point")
    if lookup_failure is not None or provider_data is None:
        # A failed or indeterminate lookup is never read as an empty, invalid-shape or
        # non-matching `providerData` result: it keeps its own audit result, distinct from a
        # client-supplied proof failure, and surfaces as `verification_temporarily_unavailable`.
        raise gate_lookup_unavailable(lookup_failure)
    try:
        return web_gate_canonical_provider_account_id(row, provider_data)
    except ProviderLookupFailedError:
        # A malformed Admin record keeps the identity file's own fail-closed classification: it
        # is an unavailable lookup, not a client-supplied proof failure.
        raise
    except (ProviderClassificationError, DerivationError, IdentityError) as exc:
        raise GateDenied(str(exc)) from None


def gate_lookup_unavailable(
        failure: ProviderLookupFailedError | None) -> ProviderLookupFailedError:
    """A failed or indeterminate Admin lookup keeps the internal result and client class the
    identity file's own lookup-failure family assigned it, together with its retryability: the
    indeterminate causes audit as `firebase_lookup_unavailable` and surface as
    `verification_temporarily_unavailable`, and the non-retryable `user-not-found` at this
    required web read audits as `firebase_user_unresolved` and surfaces as `auth_required`.
    Neither is ever read as a client-supplied proof failure. A lookup that produced no failure
    object at all — no `providerData` and no reason — is the default unavailable case."""
    # [impl->req~proof-web-gate-provider-data-classifier~1]
    # [impl->req~grants-anon-failure-class-mapping~1]
    if failure is not None:
        if failure.client_class == GateDenied.error_code:
            raise ProofApplicabilityError(
                "a failed lookup is never a client-supplied proof failure")
        return failure
    client_class = ClientErrorClass(surface(GATE_UNAVAILABLE_RESULT)[0])
    if client_class is not ClientErrorClass.verification_temporarily_unavailable:
        raise ProofApplicabilityError(
            "an unavailable lookup surfaces as verification_temporarily_unavailable")
    return ProviderLookupFailedError(GATE_UNAVAILABLE_RESULT, client_class, retryable=True)


def assert_gate_denial_scope(operation: AuthOperation) -> None:
    """A failed, indeterminate, invalid-shape or non-matching Admin lookup denies that free grant
    and nothing else: never login, account creation, the anonymous-to-registered upgrade, session
    sync, subscription restore, or any paid entitlement path."""
    # [impl->req~proof-web-gate-provider-data-classifier~1]
    if operation in GATE_NEVER_DENIES:
        raise ProofApplicabilityError(f"a web-gate lookup failure never denies {operation}")
    if operation not in GATE_DENIES:
        raise ProofApplicabilityError(f"{operation} has no web anonymous-grant gate")


def web_gate_consumption(index: IdpAccountAliasIndex, account: WebGateAccount,
                         grant_id: UUID) -> GateConsumptionKind:
    """Gate uniqueness is enforced on the stable provider UID through the canonical
    `core.provider_accounts` registry and its per-gate consumption rows; the `idp_account_hash`
    the consumption records beside them is the non-authoritative lookup and audit alias."""
    # [impl->req~proof-idp-hmac-applicability~1]
    kind = GateConsumptionKind.web_anonymous_gate
    index.consume(ProviderAccount(provider=account.provider,
                                  provider_uid=account.canonical_provider_account_id),
                  kind, grant_id)
    return kind
