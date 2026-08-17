"""The request contracts of the two free-credit grant endpoints.

`POST /auth/claim-anonymous-grant` and `POST /auth/claim-registered-grant` each perform exactly one
operation, and this file is what each one accepts: the `Authorization` credential the shared barrier
verifies, the identity shape it requires, the operation challenge it was prepared with, the vendor
material of its platform, and — as loudly as the rest — the material it refuses to be given.

The operation logic is elsewhere: `free_grants` owns the anonymous claim's rules, `registered_grants`
the registered claim's, `grant_admission` the handler-side limits both sit behind, and
`grant_failures` / `registered_grant_failures` the internal-result-to-class mapping. What this file
adds is the endpoint boundary itself — one operation per endpoint, one set of accepted inputs, and
the closed set of client-visible classes each endpoint can emit.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.derived_identifiers import IdpAccountAliasIndex, WebGateAccount
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    IdentityState,
    matches_identity,
)
from nativespeaker.api.auth.free_grants import (
    BRANCH_PLATFORM,
    NATIVE_BRANCHES,
    WebGateRead,
    assert_claimant_eligible,
    claim_identity,
    read_web_gate,
)
from nativespeaker.api.auth.grant_failures import ANON_CLIENT_CLASSES, anonymous_emitted_classes
from nativespeaker.api.auth.modes import (
    CHALLENGE_QUERY_PARAM,
    CHALLENGE_QUERY_VALUE,
    RequestMode,
    classify_mode,
)
from nativespeaker.api.auth.onboarding import AuthorizationHeaderSource
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider, route_for
from nativespeaker.api.auth.proof_endpoints import BRANCH_GATE_MATERIAL, ClaimBranch, ProofArtifact
from nativespeaker.api.auth.registered_grant_failures import (
    REG_CLIENT_CLASSES,
    RegClaimCondition,
    proof_rejected_conditions,
    registered_emitted_classes,
)
from nativespeaker.api.auth.registered_grants import (
    DEVICE_CHECKED_KINDS,
    assert_no_device_proof_as_identity,
    assert_registered_provider,
    registered_account_alias,
    registered_provider_account,
)
from nativespeaker.api.auth.sync import is_forbidden as sync_forbids
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.auth.users_me import is_forbidden as users_me_forbids


class ClaimEndpointError(RuntimeError):
    """A grant endpoint was about to accept, or ask for, something its contract excludes."""


# --- One operation per endpoint ---------------------------------------------------------------

ANONYMOUS_GRANT_ROUTE: tuple[str, str] = route_for(AuthOperation.claim_anonymous_grant)
REGISTERED_GRANT_ROUTE: tuple[str, str] = route_for(AuthOperation.claim_registered_grant)

CLAIM_ENDPOINTS: dict[AuthOperation, tuple[str, str]] = {
    AuthOperation.claim_anonymous_grant: ANONYMOUS_GRANT_ROUTE,
    AuthOperation.claim_registered_grant: REGISTERED_GRANT_ROUTE,
}


def _single_operation(method: str, path: str, expected: AuthOperation) -> AuthOperation:
    route = CLAIM_ENDPOINTS[expected]
    if (method.upper(), path) != route:
        raise ClaimEndpointError(f"{method} {path} does not perform {expected}")
    for operation, other in CLAIM_ENDPOINTS.items():
        if operation is not expected and other == route:
            raise ClaimEndpointError(f"{route} would also perform {operation}")
    return expected


def anonymous_grant_operation(method: str, path: str) -> AuthOperation:
    """`POST /auth/claim-anonymous-grant` performs only `claim_anonymous_grant`."""
    # [impl->req~grants-anon-endpoint-single-operation~1]
    return _single_operation(method, path, AuthOperation.claim_anonymous_grant)


def registered_grant_operation_for(method: str, path: str) -> AuthOperation:
    """`POST /auth/claim-registered-grant` performs only `claim_registered_grant`."""
    # [impl->req~grants-reg-endpoint-single-operation~1]
    return _single_operation(method, path, AuthOperation.claim_registered_grant)


# --- The `Authorization` credential both endpoints authenticate with --------------------------


def _barrier_supplied_pair(context: VerifiedIdentityContext,
                           row: ExternalIdentityRow | None,
                           header: AuthorizationHeaderSource) -> tuple[str, str]:
    """The `(issuer, subject)` and the current identity come from the shared mandatory pre-handler
    authentication-and-identity-resolution barrier, out of the backend-verified Firebase ID token in
    the unchanged client `Authorization` header. The handler resolves nothing itself."""
    if header is not AuthorizationHeaderSource.unchanged_client_header:
        raise ClaimEndpointError(f"{header} does not authenticate a free-credit claim")
    if not context.issuer or not context.subject:
        raise ClaimEndpointError("the barrier supplies the verified issuer and subject")
    if row is not None and not matches_identity(row, context.issuer, context.subject):
        raise ClaimEndpointError("the current identity is the barrier's own resolution")
    return context.issuer, context.subject


def anonymous_grant_authentication(context: VerifiedIdentityContext,
                                   *,
                                   row: ExternalIdentityRow | None = None,
                                   header: AuthorizationHeaderSource =
                                   AuthorizationHeaderSource.unchanged_client_header
                                   ) -> tuple[str, str]:
    """The anonymous claim authenticates with the backend-verified Firebase ID token from the
    `Authorization` header; `(issuer, subject)` and the current identity are supplied by the shared
    mandatory pre-handler authentication-and-identity-resolution barrier."""
    # [impl->req~grants-anon-req-authorization-token~1]
    return _barrier_supplied_pair(context, row, header)


def registered_grant_authentication(context: VerifiedIdentityContext,
                                    *,
                                    row: ExternalIdentityRow | None = None,
                                    header: AuthorizationHeaderSource =
                                    AuthorizationHeaderSource.unchanged_client_header
                                    ) -> tuple[str, str]:
    """The registered claim authenticates the same way: the backend-verified Firebase ID token from
    the `Authorization` header, with `(issuer, subject)` and the current identity supplied by the
    shared barrier."""
    # [impl->req~grants-reg-req-authorization-token~1]
    return _barrier_supplied_pair(context, row, header)


# --- The identity shape each endpoint requires ------------------------------------------------

# `registered_at` is not an eligibility input on either endpoint: the stored provider is the
# classifier, and nothing reads the timestamp.
REGISTRATION_TIMESTAMP_INPUTS: frozenset[str] = frozenset()


def anonymous_identity_shape(row: ExternalIdentityRow,
                             branch: ClaimBranch,
                             *,
                             consulted: Sequence[str] = ()) -> IdentityProvider:
    """On native paths the resolved identity must be an active linked identity that is either
    anonymous or registered with stored provider `google` or `apple`. On web it must be an active
    linked identity whose stored provider is `google` or `apple` and whose stored `provider_uid` is
    present. The stored provider is the classifier; `registered_at` is not consulted."""
    # [impl->req~grants-anon-req-identity-shape~1]
    # [impl->req~grants-anon-entry-identity-classification~1]
    offending = sorted({name for name in consulted if "registered_at" in name})
    if offending or REGISTRATION_TIMESTAMP_INPUTS:
        raise ClaimEndpointError(f"{offending} is not an eligibility input here")
    if row.identity_state is not IdentityState.active:
        raise ClaimEndpointError("the claim needs an active linked identity")
    # The branch's own provider rule, read from the stored column and from nothing else.
    provider = assert_claimant_eligible(branch, row)
    if branch is ClaimBranch.web:
        if provider not in REGISTERED_PROVIDERS:
            raise ClaimEndpointError("the web claimant's stored provider is google or apple")
        if not row.provider_uid:
            raise ClaimEndpointError("the web claimant's stored provider_uid must be present")
    return provider


def registered_identity_linked_active(context: VerifiedIdentityContext,
                                      row: ExternalIdentityRow,
                                      *,
                                      user_active: bool) -> ExternalIdentityRow:
    """The resolved identity must be linked and active, and its linked user must be active."""
    # [impl->req~grants-reg-req-linked-active~1]
    # [impl->req~grants-reg-entry-barrier~1]
    if context.outcome is not ResolutionOutcome.linked:
        raise ClaimEndpointError("the registered claim needs a linked identity")
    if row.identity_state is not IdentityState.active:
        raise ClaimEndpointError("the registered claim needs an active identity")
    if not user_active:
        raise ClaimEndpointError("the registered claim needs an active linked user")
    if row.user_id is None:
        raise ClaimEndpointError("a linked identity names its user")
    return row


def registered_provider_requirement(row: ExternalIdentityRow) -> IdentityProvider:
    """The current linked external identity must have `provider = 'google'` or
    `provider = 'apple'`."""
    # [impl->req~grants-reg-req-provider-google-apple~1]
    # [impl->req~grants-reg-entry-provider~1]
    return assert_registered_provider(row)


# --- The operation challenge each endpoint was prepared with ----------------------------------


def _challenge_source(operation: AuthOperation) -> str:
    method, path = CLAIM_ENDPOINTS[operation]
    signal = classify_mode([(CHALLENGE_QUERY_PARAM, CHALLENGE_QUERY_VALUE)], None)
    if signal.mode is not RequestMode.prepare:
        raise ClaimEndpointError("challenge=true on the endpoint's own URL prepares the challenge")
    return f"{method} {path}?{CHALLENGE_QUERY_PARAM}={CHALLENGE_QUERY_VALUE}"


def anonymous_challenge_source() -> str:
    """The completion carries the operation challenge returned by
    `POST /auth/claim-anonymous-grant?challenge=true`."""
    # [impl->req~grants-anon-req-operation-challenge~1]
    return _challenge_source(AuthOperation.claim_anonymous_grant)


def registered_challenge_source() -> str:
    """The completion carries the operation challenge returned by
    `POST /auth/claim-registered-grant?challenge=true`."""
    # [impl->req~grants-reg-req-operation-challenge~1]
    return _challenge_source(AuthOperation.claim_registered_grant)


# --- The vendor material the anonymous claim carries -------------------------------------------

# iOS carries two separate per-transaction DeviceCheck tokens — one sufficient for the query and one
# for the update; Android carries one Play Integrity token covering both the Device Recall read and
# the write. Both sets are untrusted provider-query input.
ANON_NATIVE_MATERIAL: dict[ClaimBranch, frozenset[ProofArtifact]] = {
    ClaimBranch.native_ios: BRANCH_GATE_MATERIAL[ClaimBranch.native_ios],
    ClaimBranch.native_android: BRANCH_GATE_MATERIAL[ClaimBranch.native_android],
}
IOS_TRANSACTION_TOKENS: int = 2
ANDROID_TRANSACTION_TOKENS: int = 1


def anonymous_native_vendor_tokens(branch: ClaimBranch,
                                   *,
                                   device_recall_available: bool = True
                                   ) -> frozenset[ProofArtifact]:
    """On iOS, separate untrusted per-transaction DeviceCheck tokens sufficient for the vendor query
    and update. On Android where Device Recall is available, one untrusted Play Integrity token
    covering both the Device Recall read and write."""
    # [impl->req~grants-anon-req-native-vendor-tokens~1]
    # [impl->req~grants-anon-entry-vendor-material~1]
    if branch not in NATIVE_BRANCHES:
        raise ClaimEndpointError(f"{branch} carries no native vendor material")
    material = ANON_NATIVE_MATERIAL[branch]
    if branch is ClaimBranch.native_ios:
        if len(material) != IOS_TRANSACTION_TOKENS:
            raise ClaimEndpointError("iOS carries separate query and update DeviceCheck tokens")
        return material
    if not device_recall_available:
        raise ClaimEndpointError(
            "the Android anonymous path exists only where Device Recall is available")
    if len(material) != ANDROID_TRANSACTION_TOKENS:
        raise ClaimEndpointError("Android carries one Play Integrity token for read and write")
    return material


# The only web-gate evidence the request body carries. The sign-in half is not client-supplied.
ANON_WEB_BODY_EVIDENCE: frozenset[ProofArtifact] = frozenset({ProofArtifact.turnstile_token})
CLIENT_SUPPLIED_WEB_SIGN_IN_EVIDENCE: frozenset[str] = frozenset()


def anonymous_web_evidence(read: WebGateRead,
                           *,
                           body_evidence: Sequence[ProofArtifact] = (),
                           index: IdpAccountAliasIndex | None = None) -> WebGateAccount:
    """On web the request body carries Cloudflare bot-check evidence and nothing else. Through the
    Admin client of the single configured Firebase integration selected by the request's verified
    issuer, the backend applies the closed classifier to the complete live `providerData` result and
    requires the classified provider and sole entry's non-empty `uid` to equal the identity's stored
    provider and stored `provider_uid`."""
    # [impl->req~grants-anon-req-web-evidence~1]
    # [impl->req~grants-anon-entry-vendor-material~1]
    if CLIENT_SUPPLIED_WEB_SIGN_IN_EVIDENCE:
        raise ClaimEndpointError("the web sign-in half is never client-supplied")
    offered = frozenset(body_evidence) if body_evidence else ANON_WEB_BODY_EVIDENCE
    if offered != ANON_WEB_BODY_EVIDENCE:
        raise ClaimEndpointError(
            f"{sorted(offered)} is not the web gate's only request-body evidence")
    account, _ = read_web_gate(read, index=index)
    return account


# Attestation and recovery material the anonymous claim never carries, in every name it could
# arrive under: App Attest proof, Android Keystore proof, enrolled-key proof, and `restore_proof`.
ANON_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "app_attest_assertion", "app_attest_attestation", "app_attest_key_id", "attestation",
    "attestation_blob", "attestation_key", "attestation_key_id", "attestation_key_proof",
    "android_keystore_proof", "enrolled_key", "enrolled_key_proof", "integrity_proof",
    "restore_proof"})


def assert_no_attestation_material(body: Mapping[str, Any] | None) -> None:
    """The anonymous claim request carries no App Attest proof, Android Keystore proof,
    enrolled-key proof, or `restore_proof`."""
    # [impl->req~grants-anon-req-no-attestation-material~1]
    # [impl->req~grants-anon-entry-no-restore-proof~1]
    # [impl->req~grants-anon-entry-no-app-attest~1]
    offending = sorted(set(body or {}) & ANON_FORBIDDEN_FIELDS)
    if offending:
        raise ClaimEndpointError(
            f"POST /auth/claim-anonymous-grant takes no {offending}")


# --- The proof is not an identity token -------------------------------------------------------

# The gateway JWT filter is edge admission and defense-in-depth; it establishes no identity.
GATEWAY_JWT_FILTER_ROLE: str = "edge_admission_and_defense_in_depth"
# Admin-client selection failure fails closed for this grant and for nothing else.
ADMIN_SELECTION_FAILURE_SCOPE: frozenset[AuthOperation] = frozenset({
    AuthOperation.claim_anonymous_grant})


def anonymous_proof_is_not_identity(context: VerifiedIdentityContext,
                                    *,
                                    offered: Sequence[str] = (),
                                    resolved_by: str = "") -> tuple[str, str]:
    """The device-check proof material and the Cloudflare bot-check evidence are not identity tokens
    and never resolve which account the request belongs to. Verified identity is only the barrier's
    backend-verified `(issuer, subject)` from the Firebase ID token in the `Authorization` header.

    On web, the issuer-selected Admin client reads `providerData` with backend-held credentials and
    enforces the complete closed-classifier-and-stored-binding check; a failure to select that
    client fails closed for this grant alone.
    """
    # [impl->req~grants-anon-proof-not-identity-token~1]
    if resolved_by and resolved_by != "shared_pre_handler_barrier":
        raise ClaimEndpointError(f"{resolved_by} never resolves the request's account")
    if GATEWAY_JWT_FILTER_ROLE != "edge_admission_and_defense_in_depth":
        raise ClaimEndpointError("the gateway JWT filter is edge admission, not identity")
    if ADMIN_SELECTION_FAILURE_SCOPE != frozenset({AuthOperation.claim_anonymous_grant}):
        raise ClaimEndpointError("Admin-client selection failure fails closed for this grant only")
    return claim_identity(context, offered=offered)


# --- Where per-device and web sign-in state may be touched ------------------------------------

# The endpoint verifies and updates native per-device grant state only through the platform gate,
# and verifies the web sign-in half only through server-side Firebase Admin `providerData`.
DEVICE_STATE_ACCESS_PATHS: frozenset[str] = frozenset({"platform_gate"})
WEB_SIGN_IN_VERIFICATION_PATHS: frozenset[str] = frozenset({"firebase_admin_provider_data"})

# What the two read-only endpoints must not do with any of it.
SYNC_PROHIBITED: tuple[str, ...] = ("read_device_grant_state", "write_device_grant_state",
                                    "verify_devicecheck", "read_provider_data")
USERS_ME_PROHIBITED: tuple[str, ...] = ("verify_devicecheck", "read_device_grant_state",
                                        "write_device_grant_state", "read_provider_data",
                                        "mint_grant")


def assert_device_state_scope(*,
                              device_state_paths: Sequence[str] = (),
                              web_sign_in_paths: Sequence[str] = ()) -> None:
    """Native per-device grant state is verified and updated only through the platform gate, and the
    web sign-in half only through server-side Firebase Admin `providerData`. `POST /auth/sync` must
    not query the device check or perform the web grant `providerData` lookup, and `GET /users/me`
    must not verify device-check proofs, read or modify per-device grant state, perform that lookup,
    or mint any grant."""
    # [impl->req~grants-anon-endpoint-device-state-scope~1]
    stray = sorted(set(device_state_paths) - DEVICE_STATE_ACCESS_PATHS)
    if stray:
        raise ClaimEndpointError(f"{stray} is no platform gate")
    stray_web = sorted(set(web_sign_in_paths) - WEB_SIGN_IN_VERIFICATION_PATHS)
    if stray_web:
        raise ClaimEndpointError(f"{stray_web} does not verify the web sign-in half")
    permitted = [call for call in SYNC_PROHIBITED if not sync_forbids(call)]
    if permitted:
        raise ClaimEndpointError(f"POST /auth/sync must not {permitted}")
    permitted = [call for call in USERS_ME_PROHIBITED if not users_me_forbids(call)]
    if permitted:
        raise ClaimEndpointError(f"GET /users/me must not {permitted}")


# --- The registered claim's proof set and prohibitions ----------------------------------------


def assert_no_registered_device_identity_proof(*,
                                               required: Sequence[str] = (),
                                               accepted: Sequence[str] = (),
                                               evaluated: Sequence[str] = ()) -> None:
    """No App Attest, Android Keystore proof, or device material as identity or ownership proof is
    required, accepted, or evaluated by the registered claim."""
    # [impl->req~grants-reg-req-no-device-identity-proof~1]
    # [impl->req~grants-reg-entry-no-device-identity-proof~1]
    assert_no_device_proof_as_identity(required=required, accepted=accepted, evaluated=evaluated)


def registered_platform_proof_set(kind: ClaimBranch,
                                  *,
                                  recall_required: bool | None = None
                                  ) -> frozenset[ProofArtifact]:
    """The platform proof set is mandatory per claim kind: every iOS claim requires separate
    untrusted per-transaction DeviceCheck tokens sufficient for the query and update; every Android
    claim requires one untrusted Play Integrity token, covering the Device Recall read and write
    where the checked-in release policy requires Device Recall; every web claim requires Cloudflare
    Turnstile evidence.

    `recall_required` is the checked-in release policy's answer for an Android release, which
    `registered_grants.registered_recall_required` resolves; it changes what the one token has to
    cover, never whether the token is required.
    """
    # [impl->req~grants-reg-req-platform-proof-set~1]
    # [impl->req~grants-reg-entry-claim-kind-proof-set~1]
    material = BRANCH_GATE_MATERIAL[kind]
    if not material:
        raise ClaimEndpointError(f"{kind} would be a claim kind with no mandatory proof set")
    if kind is ClaimBranch.native_ios and len(material) != IOS_TRANSACTION_TOKENS:
        raise ClaimEndpointError("every iOS claim requires separate DeviceCheck tokens")
    if kind is ClaimBranch.native_android:
        if len(material) != ANDROID_TRANSACTION_TOKENS:
            raise ClaimEndpointError("every Android claim requires one Play Integrity token")
        if ProofArtifact.play_integrity_verdict not in material:
            raise ClaimEndpointError("the Android proof set is the Play Integrity verdict")
        # Whether that one token also has to cover a Device Recall read and write is the release
        # policy's answer; it never makes the token itself optional.
        del recall_required
    if kind is ClaimBranch.web and material != frozenset({ProofArtifact.turnstile_token}):
        raise ClaimEndpointError("every web claim requires Cloudflare Turnstile evidence")
    if kind in DEVICE_CHECKED_KINDS and kind not in BRANCH_PLATFORM:
        raise ClaimEndpointError(f"{kind} names no native platform")
    return material


REGISTERED_RESTORE_PROOF_FIELDS: frozenset[str] = frozenset({"restore_proof"})
# The provider account identifier is derived from the stored `provider_uid`, never accepted.
CLIENT_PROVIDER_ID_FIELDS: frozenset[str] = frozenset({
    "provider_uid", "provider_account_id", "idp_account_id", "idp_account_hash", "google_uid",
    "apple_uid", "sub", "email", "account_id"})


def assert_no_registered_restore_proof(body: Mapping[str, Any] | None) -> None:
    """The registered claim request carries no `restore_proof`."""
    # [impl->req~grants-reg-req-no-restore-proof~1]
    # [impl->req~grants-reg-entry-no-restore-proof~1]
    offending = sorted(set(body or {}) & REGISTERED_RESTORE_PROOF_FIELDS)
    if offending:
        raise ClaimEndpointError(f"POST /auth/claim-registered-grant takes no {offending}")


def assert_no_client_provider_identifier(body: Mapping[str, Any] | None) -> None:
    """The registered claim request carries no client-supplied provider account identifier."""
    # [impl->req~grants-reg-req-no-client-provider-id~1]
    # [impl->req~grants-reg-entry-no-client-provider-id~1]
    offending = sorted(set(body or {}) & CLIENT_PROVIDER_ID_FIELDS)
    if offending:
        raise ClaimEndpointError(
            f"POST /auth/claim-registered-grant takes no client-supplied {offending}")


# --- What the registered endpoint reads and enforces ------------------------------------------

REGISTERED_ENFORCEMENTS: tuple[str, ...] = (
    "one_free_grant_per_account",
    "registered_gate_consumption_uniqueness_on_stable_uid",
)
MANDATORY_PROVIDER_DATA_CONFIRMATIONS_PER_CALL: int = 1


def registered_endpoint_reads_and_enforces(row: ExternalIdentityRow,
                                           index: IdpAccountAliasIndex,
                                           *,
                                           provider_data_confirmations: int =
                                           MANDATORY_PROVIDER_DATA_CONFIRMATIONS_PER_CALL
                                           ) -> tuple[str, ...]:
    """The endpoint reads the current linked external identity's stored provider and stored
    `provider_uid`, computes the alias `idp_account_hash` from those stored values, enforces account
    grant history under the one-free-grant-per-account rule, and enforces the registered gate's
    per-provider-account consumption uniqueness on the stable UID. Every call performs the mandatory
    fail-closed Firebase Admin `providerData` confirmation of the stored binding; `POST /auth/sync`
    still performs no Firebase account lookups."""
    # [impl->req~grants-reg-endpoint-reads-and-enforces~1]
    # [impl->req~grants-reg-entry-provider-uid~1]
    # [impl->req~grants-reg-entry-mandatory-confirmation~1]
    assert_registered_provider(row)
    if not row.provider_uid:
        raise ClaimEndpointError("the alias is computed from the stored provider_uid")
    account = registered_provider_account(row)
    alias = registered_account_alias(index, account)
    if not alias.digest:
        raise ClaimEndpointError("the endpoint computes the idp_account_hash alias")
    if provider_data_confirmations != MANDATORY_PROVIDER_DATA_CONFIRMATIONS_PER_CALL:
        raise ClaimEndpointError("every call performs the mandatory providerData confirmation")
    if not sync_forbids("read_provider_data"):
        raise ClaimEndpointError("POST /auth/sync performs no Firebase account lookup")
    return REGISTERED_ENFORCEMENTS


# --- The client-visible classes each endpoint returns -----------------------------------------

# `claim_anonymous_grant`'s nine opaque classes, per the taxonomy in the grants document.
ANON_ENDPOINT_ERROR_CLASSES: tuple[ClientErrorClass, ...] = (
    ClientErrorClass.auth_required,
    ClientErrorClass.preauth_identity_not_allowed,
    ClientErrorClass.account_unavailable,
    ClientErrorClass.challenge_required,
    ClientErrorClass.proof_rejected,
    ClientErrorClass.operation_not_allowed,
    ClientErrorClass.device_grant_exhausted,
    ClientErrorClass.verification_required,
    ClientErrorClass.verification_temporarily_unavailable,
)

# `claim_registered_grant` returns the same set plus `account_already_claimed`. The shared
# challenge rejections belong to the endpoint but not to the claim's own failure-condition table,
# which is why the operation's emitted set is the rest of this one.
REG_ENDPOINT_ERROR_CLASSES: tuple[ClientErrorClass, ...] = (
    ClientErrorClass.auth_required,
    ClientErrorClass.preauth_identity_not_allowed,
    ClientErrorClass.account_unavailable,
    ClientErrorClass.challenge_required,
    ClientErrorClass.proof_rejected,
    ClientErrorClass.operation_not_allowed,
    ClientErrorClass.device_grant_exhausted,
    ClientErrorClass.verification_required,
    ClientErrorClass.account_already_claimed,
    ClientErrorClass.verification_temporarily_unavailable,
)


def anonymous_endpoint_error_classes() -> frozenset[ClientErrorClass]:
    """The opaque client-visible classes `POST /auth/claim-anonymous-grant` returns, cross-checked
    against the classes the operation's own failure conditions can actually produce."""
    # [impl->req~grants-anon-endpoint-error-classes~1]
    declared = frozenset(ANON_ENDPOINT_ERROR_CLASSES)
    undeclared = sorted(str(name) for name in declared if name not in set(ClientErrorClass))
    if undeclared:
        raise ClaimEndpointError(f"{undeclared} is no shared client-visible class")
    if declared != ANON_CLIENT_CLASSES or declared != anonymous_emitted_classes():
        raise ClaimEndpointError(
            f"the endpoint returns {sorted(str(name) for name in declared)}")
    return declared


def registered_endpoint_error_classes() -> frozenset[ClientErrorClass]:
    """The opaque client-visible classes `POST /auth/claim-registered-grant` returns: the ones its
    own failure conditions produce, plus the shared `challenge_required` every challenge-bearing
    completion can return."""
    # [impl->req~grants-reg-endpoint-error-classes~1]
    declared = frozenset(REG_ENDPOINT_ERROR_CLASSES)
    undeclared = sorted(str(name) for name in declared if name not in set(ClientErrorClass))
    if undeclared:
        raise ClaimEndpointError(f"{undeclared} is no shared client-visible class")
    expected = registered_emitted_classes() | {ClientErrorClass.challenge_required}
    if declared != frozenset(REG_CLIENT_CLASSES) | {ClientErrorClass.challenge_required} \
            or declared != expected:
        raise ClaimEndpointError(
            f"the endpoint returns {sorted(str(name) for name in declared)}")
    return declared


def registered_proof_rejected_scope() -> tuple[RegClaimCondition, ...]:
    """On the registered claim, `proof_rejected` applies only to missing or malformed
    client-supplied DeviceCheck or Play Integrity transaction material on a path that uses the
    registered-claimed device state; such material never establishes identity or ownership."""
    # [impl->req~grants-reg-endpoint-error-classes~1]
    conditions = proof_rejected_conditions()
    if not conditions:
        raise ClaimEndpointError("proof_rejected has no conditions on the registered claim")
    if not DEVICE_CHECKED_KINDS:
        raise ClaimEndpointError("proof_rejected needs a registered-claimed device-state path")
    # The material is anti-abuse device state and never identity or ownership evidence.
    assert_no_device_proof_as_identity(
        evaluated=["devicecheck_query_token", "play_integrity_token"])
    return conditions
