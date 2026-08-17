"""The required rules of `claim_registered_grant`, and its three destinations.

`claim_registered_grant` is the platform-independent free-credit backstop: it produces, or
converts to, one `core.access_grants` row with `source = 'registered_account_grant'`, gated by the
current user's own grant history, the stored current provider classification, and the
registered-account-grant gate-consumption domain over the stable provider UID.

This module holds that operation's rules in the one order they run in, and nothing else. The
mechanics belong to their owners and are not restated here: the barrier resolves the identity
(`barrier`), the shared completion requirements own the challenge claim and consumption
(`challenges`), the vendor sequence and the Android release policy are the proof adapters'
(`proof_adapters`), the closed `providerData` classifier and the `idp_account_hash` derivation are
the identity and derivation modules' (`external_identities`, `derived_identifiers`), the
grant-and-usage ownership model is `07-quota-and-access-enforcement.md`'s (`quota.grants`,
`quota.usage`), the row shapes are `06-schema-reference.md`'s (`schema_invariants`), and the
failure classes, retry policy and alternate path are `registered_grant_failures`'.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from nativespeaker.api.auth.audit import (
    AttemptPhase,
    AuthActor,
    AuthEvent,
    AuthEventResult,
    SubjectHasher,
    terminal_event,
)
from nativespeaker.api.auth.barrier import (
    VerifiedIdentityContext,
    barrier_result_for,
)
from nativespeaker.api.auth.challenges import ClaimOutcome
from nativespeaker.api.auth.derived_identifiers import (
    UNIQUENESS_ANCHOR,
    DerivationFamily,
    DerivedValue,
    IdpAccountAliasIndex,
    UniquenessAnchor,
    actor_subject_preimage,
    assert_persisted_key_version,
    assert_uniqueness_anchor,
    domain_label,
    registered_grant_canonical_provider_account_id,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    IdentityState,
    assert_conversion_same_lineage,
    assert_raw_provider_account_store,
    assert_stored_provider_not_a_mirror,
    free_grant_available,
    mark_free_grant_consumed,
)
from nativespeaker.api.auth.free_grants import (
    ANTI_ABUSE_UNIQUENESS_DOMAIN,
    FREE_GRANT_SOURCES,
    LIFETIME_FREE_GRANTS_PER_ACCOUNT,
    MAX_ACTIVE_GRANTS_PER_USER,
    ClaimEvidence,
    FreeGrantError,
    FreeGrantRejected,
    assert_database_bounds,
    assert_device_check_is_anti_abuse_only,
    consume_free_grant_gate,
    free_grant_anti_abuse_row,
    non_accusatory_copy,
    registered_eligibility_inputs,
    select_branch,
)
from nativespeaker.api.auth.grant_failures import assert_no_raw_provider_account_ids
from nativespeaker.api.auth.invariants import (
    GateAlreadyConsumedError,
    GateConsumptionKind,
    ProofUse,
    ProviderAccount,
    assert_grant_columns_entitlement_only,
    assert_same_transaction,
)
from nativespeaker.api.auth.locks import LockLedger, lock_grant_set
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider, route_for
from nativespeaker.api.auth.proof_adapters import (
    CLAIM_EXECUTION_CONTEXT,
    ClaimRejection,
    DeviceGrantExhausted,
    DeviceStateAdapter,
    ExecutionContext,
    NativeClaimLedger,
    NativeClaimStep,
    ReleaseKey,
    ReleasePolicyRegistry,
    TurnstileDenied,
    TurnstileUnavailable,
    assert_execution_context,
    claim_state_for,
    devicecheck_bit_for,
    recall_state_for,
    registered_claim_requires_recall,
)
from nativespeaker.api.auth.proof_endpoints import (
    BRANCH_GATE_MATERIAL,
    ClaimBranch,
    ProofApplicabilityError,
    ProofArtifact,
    assert_anti_abuse_device_state_only,
    assert_not_attestation_evidence,
    registered_grant_idp_account,
    requires_attestation,
)
from nativespeaker.api.auth.schema_invariants import (
    assert_grant_source_never_rewritten,
    assert_native_claim_written_before_grant,
    assert_registered_conversion,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass, remediation_for
from nativespeaker.api.quota.grants import GrantRow, assert_billing_separation, is_effective
from nativespeaker.api.quota.usage import NewUsageRow, new_usage_row
from nativespeaker.api.ratelimit.ordering import DeviceBitWrite, assert_grant_row_permitted

if TYPE_CHECKING:  # `registered_grant_failures` sits below this module in the import graph.
    from nativespeaker.api.auth.registered_grant_failures import RegClaimCondition

# --- The operation, as this section defines it ----------------------------------------------------

# The one source this operation creates, and the gate-consumption domain that bounds it.
REGISTERED_GRANT_SOURCE: AccessGrantSource = AccessGrantSource.registered_account_grant
REGISTERED_GRANT_GATE: GateConsumptionKind = GateConsumptionKind.registered_account_grant

# What gates the claim. All three are backend-stored state; none of them is a client assertion.
REGISTERED_GRANT_GATES: tuple[str, ...] = (
    "user_own_grant_history",
    "stored_provider_classification",
    "registered_account_grant_gate_consumption",
)

# The grant is kept small and uniform across platforms, and the backend ranks no grant against
# another: no value ordering, no queue of pending claims behind a held grant, and no call that
# drops or replaces a held grant so a claim can proceed.
GRANT_VALUE_RANKINGS: frozenset[str] = frozenset()
PENDING_CLAIM_QUEUES: frozenset[str] = frozenset()
GRANT_DROPPING_CALLS: frozenset[str] = frozenset()

# The one active grant this operation may move aside, as a transition of the same allowance.
CONVERTIBLE_ACTIVE_SOURCE: AccessGrantSource = AccessGrantSource.anonymous_device_grant


@dataclass(frozen=True, slots=True)
class RegisteredGrantDefinition:
    """What `claim_registered_grant` is: the source it writes, the gate domain that bounds it, and
    the gates it reads."""
    source: AccessGrantSource
    gate_kind: GateConsumptionKind
    gates: tuple[str, ...]
    platform_uniform: bool
    convertible_source: AccessGrantSource


def registered_grant_operation() -> RegisteredGrantDefinition:
    """`claim_registered_grant` produces or converts to a `core.access_grants` row with
    `source = 'registered_account_grant'`, gated by the current user's own grant history, the
    stored current provider classification, and the registered-account-grant gate-consumption
    domain. It is the platform-independent backstop, and it never outranks a grant the user
    already holds: no ranking, no queued pending claim, and no call that drops the held grant."""
    # [impl->req~grants-registered-operation-definition~1]
    # [impl->req~grants-reg-logic-purpose~1]
    if GRANT_VALUE_RANKINGS or PENDING_CLAIM_QUEUES or GRANT_DROPPING_CALLS:
        raise FreeGrantError("the backend ranks, queues and drops no grant for this claim")
    if ANTI_ABUSE_UNIQUENESS_DOMAIN[REGISTERED_GRANT_SOURCE] is not REGISTERED_GRANT_GATE:
        raise FreeGrantError("the registered grant is bounded by its own gate domain")
    return RegisteredGrantDefinition(source=REGISTERED_GRANT_SOURCE,
                                     gate_kind=REGISTERED_GRANT_GATE,
                                     gates=REGISTERED_GRANT_GATES,
                                     platform_uniform=True,
                                     convertible_source=CONVERTIBLE_ACTIVE_SOURCE)


def backstop_reachable(*, active_grant_source: AccessGrantSource | None) -> bool:
    """Whether the backstop is reachable right now. While an active grant other than a convertible
    anonymous device grant is held the claim is refused under the destination rules; the backstop
    becomes reachable again once that grant is no longer active, and the wait forfeits nothing."""
    # [impl->req~grants-registered-operation-definition~1]
    registered_grant_operation()
    return (active_grant_source is None
            or active_grant_source is CONVERTIBLE_ACTIVE_SOURCE
            or active_grant_source is REGISTERED_GRANT_SOURCE)


# The identity provider enum this file's rules read. It is `core.identity_provider` as
# `operations.IdentityProvider` defines it — `anonymous`, `google` and `apple`, and nothing else —
# and the registered classifier below reads it rather than keeping a second copy.
# [impl->req~grants-provider-enum~1]
GRANT_PROVIDERS: tuple[IdentityProvider, ...] = tuple(IdentityProvider)


def assert_registered_provider(row: ExternalIdentityRow) -> IdentityProvider:
    """The current linked external identity's stored `provider` must be `google` or `apple`. Any
    other provider, `anonymous` included, is audited as `idp_account_not_eligible` and rejected
    with `verification_required`."""
    # [impl->req~grants-reg-rule-provider-google-apple~1]
    # [impl->req~grants-reg-entry-provider~1]
    if row.provider not in GRANT_PROVIDERS:
        raise FreeGrantError(f"{row.provider} is no core.identity_provider value")
    if row.provider not in REGISTERED_PROVIDERS:
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                f"a {row.provider} identity claims no registered account grant")
    return row.provider


# --- Device proof is never identity here ---------------------------------------------------------

# Device proof this operation neither requires, accepts nor evaluates, in any role.
DEVICE_PROOF_INPUTS: frozenset[str] = frozenset({
    "app_attest_assertion", "app_attest_attestation", "android_keystore_proof",
    "attestation_key_proof", "attestation_blob", "integrity_proof",
})
# The roles it is never evaluated in.
IDENTITY_ROLES: frozenset[ProofUse] = frozenset({
    ProofUse.identity, ProofUse.ownership, ProofUse.account_resolution,
})


def assert_no_device_proof_as_identity(*,
                                       required: Sequence[str] = (),
                                       accepted: Sequence[str] = (),
                                       evaluated: Sequence[str] = ()) -> None:
    """The operation must not require, accept or evaluate App Attest, Android Keystore proof, or
    any device proof as identity, ownership, or account-resolution evidence."""
    # [impl->req~grants-reg-rule-no-device-proof-as-identity~1]
    # [impl->req~grants-reg-entry-no-device-identity-proof~1]
    if requires_attestation(AuthOperation.claim_registered_grant):
        raise FreeGrantError("the registered claim requires no attestation proof")
    offending = sorted(DEVICE_PROOF_INPUTS & (set(required) | set(accepted) | set(evaluated)))
    if offending:
        raise FreeGrantError(f"{offending} is never identity, ownership or resolution evidence")
    # No attestation or integrity artifact may stand in any of those roles: the proof module owns
    # that prohibition, and this reads it rather than restating it.
    for role in IDENTITY_ROLES:
        try:
            assert_not_attestation_evidence(ProofArtifact.attestation_key_proof, role)
        except ProofApplicabilityError:
            continue
        raise FreeGrantError(f"a device proof is never {role} evidence")
    # The vendor material this operation does carry is anti-abuse device state and nothing else.
    assert_device_check_is_anti_abuse_only(ProofUse.anti_abuse_gate)


# --- The claim kind is server-owned -------------------------------------------------------------

# The three claim kinds, and the complete evidence set each one requires. Every kind has one:
# there is no kind without a complete proof set, so omitting native material can never turn a
# native claim into an account-only claim.
REGISTERED_CLAIM_KINDS: tuple[ClaimBranch, ...] = tuple(ClaimBranch)
KIND_MATERIAL: dict[ClaimBranch, frozenset[ProofArtifact]] = dict(BRANCH_GATE_MATERIAL)

# Device-check participation is server-owned and mandatory per platform, never client-optional:
# iOS carries no availability gate at all, and the Android verdict is mandatory on every claim
# regardless of Device Recall.
DEVICE_CHECK_IS_CLIENT_OPTIONAL: bool = False
IOS_AVAILABILITY_GATES: frozenset[str] = frozenset()
OPTIONAL_KIND_MATERIAL: frozenset[str] = frozenset()

# The kinds whose gate is durable per-device state, and the kind that has none.
DEVICE_CHECKED_KINDS: frozenset[ClaimBranch] = frozenset({ClaimBranch.native_ios,
                                                          ClaimBranch.native_android})
ACCOUNT_ONLY_KINDS: frozenset[ClaimBranch] = frozenset({ClaimBranch.web})


def resolve_claim_kind(evidence: ClaimEvidence,
                       *,
                       platform_header: str | None = None,
                       optional_material: Sequence[str] = (),
                       consulted: Sequence[str] = ()) -> ClaimBranch:
    """Resolve the claim kind server-side, from which complete evidence set the request carries
    and from validated provider facts — never from a client-supplied platform header and never by
    treating material as optional. Exactly one complete kind must be present; zero, multiple or
    partial evidence sets are `proof_rejected`, rejected as a request-shape error before any
    eligibility check, vendor call or ledger write."""
    # [impl->req~grants-reg-rule-server-owned-claim-kind~1]
    if platform_header is not None:
        raise FreeGrantError("the claim kind never comes from a client-supplied platform header")
    if DEVICE_CHECK_IS_CLIENT_OPTIONAL or optional_material or OPTIONAL_KIND_MATERIAL:
        raise FreeGrantError("device-check participation is mandatory, never client-optional")
    if IOS_AVAILABILITY_GATES:
        raise FreeGrantError("iOS DeviceCheck carries no availability gate")
    missing = [str(kind) for kind in REGISTERED_CLAIM_KINDS if not KIND_MATERIAL.get(kind)]
    if missing:
        raise FreeGrantError(f"{missing} would be a claim kind with no complete proof set")
    # Zero, multiple and partial sets raise `BranchShapeError`: `proof_malformed` audited,
    # `proof_rejected` surfaced.
    kind = select_branch(evidence, consulted=consulted)
    # Whatever the kind, the material is anti-abuse device state and never account identity.
    assert_anti_abuse_device_state_only(
        sorted(KIND_MATERIAL[kind], key=lambda artifact: artifact.value))
    return kind


def registered_claim_bit(kind: ClaimBranch) -> str:
    """The registered-claimed state this kind reads and writes: DeviceCheck `bit1` on iOS, the
    registered Device Recall state on Android. The web kind has no such state, and there is no
    cross-platform bit sharing — the bit means the same thing on every participating platform."""
    # [impl->req~grants-reg-rule-device-checked-kinds-bit~1]
    if kind not in DEVICE_CHECKED_KINDS:
        raise FreeGrantError(f"{kind} carries no registered-claimed device state")
    operation = AuthOperation.claim_registered_grant
    state = claim_state_for(operation)
    if kind is ClaimBranch.native_ios:
        bit = str(devicecheck_bit_for(operation))
    else:
        bit = str(recall_state_for(operation))
    if str(claim_state_for(AuthOperation.claim_anonymous_grant)) == str(state):
        raise FreeGrantError("the anonymous and registered device states are distinct")
    return bit


# --- The Android release policy ------------------------------------------------------------------

# The three fields the checked-in server release policy enumerates a release by.
RELEASE_POLICY_KEY: tuple[str, str, str] = ("package_name", "signing_certificate_digest",
                                            "release")


def registered_recall_required(registry: ReleasePolicyRegistry,
                               key: ReleaseKey,
                               *,
                               client_omitted_material: bool = False) -> bool:
    """On Android, Device Recall is additionally mandatory only where the checked-in release
    policy — an enumeration by package name, signing-certificate digest and release — classes the
    release `device_recall_required`. An unrecognized, unenumerated release is rejected outright,
    and omission of Play Integrity or Device Recall material never selects the no-recall
    branch."""
    # [impl->req~grants-reg-rule-android-release-policy~1]
    if RELEASE_POLICY_KEY != tuple(ReleaseKey.__dataclass_fields__):
        raise FreeGrantError("the release policy enumerates package, digest and release")
    policy = registry.policy_for(key)
    return registered_claim_requires_recall(policy,
                                            client_omitted_material=client_omitted_material)


# --- The accepted platform-spoof bound ------------------------------------------------------------

# The server cannot verify a claimed platform, so nothing tries to.
SERVER_VERIFIABLE_PLATFORM_CLAIM: bool = False
# What the account-rules layer binds on instead, independently of the platform claim.
ACCOUNT_LAYER_BINDINGS: tuple[str, ...] = (
    "persisted_stable_provider_account_uid",
    "registered_gate_per_provider_account_uniqueness",
    "account_grant_history",
    "mandatory_turnstile_pass",
)
# The cost of evading the device bit that way: one brand-new Google or Apple account per repeat.
NEW_PROVIDER_ACCOUNTS_PER_REPEAT_CLAIM: int = 1


def platform_spoof_bound(*, account_bindings: Sequence[str]) -> int:
    """The accepted, documented bound: a native client may present itself as web and trade
    DeviceCheck or Play Integrity for the cheaper Turnstile gate. The account-rules layer binds
    independently of the platform claim, so the spoof still costs one brand-new provider account
    per repeat claim."""
    # [impl->req~grants-reg-rule-accepted-platform-spoof-bound~1]
    if SERVER_VERIFIABLE_PLATFORM_CLAIM:
        raise FreeGrantError("the server cannot verify a claimed platform")
    missing = sorted(set(ACCOUNT_LAYER_BINDINGS) - set(account_bindings))
    if missing:
        raise FreeGrantError(f"{missing} must bind independently of the platform claim")
    return NEW_PROVIDER_ACCOUNTS_PER_REPEAT_CLAIM


# --- The mandatory `providerData` confirmation -----------------------------------------------------

# Exactly one mandatory fail-closed lookup per call, on every branch.
MANDATORY_PROVIDER_DATA_LOOKUPS: int = 1
CONFIRMATION_SKIPPING_DESTINATIONS: frozenset[str] = frozenset()
# The divergence remedy: a manual operator fix, never an automatic rewrite.
DIVERGENCE_REMEDY: str = "manual_operator_fix"


def confirm_stored_binding_live(row: ExternalIdentityRow,
                               provider_data: Sequence[object],
                               *,
                               lookups: int = MANDATORY_PROVIDER_DATA_LOOKUPS,
                               issuer_selected_admin_client: bool = True,
                               destination: RegisteredDestination | None = None,
                               mutations: Sequence[str] = ()) -> str:
    """Every call performs exactly one mandatory, fail-closed Firebase Admin `providerData` lookup
    through the issuer-selected Admin client — the idempotent repeat included, with no branch
    skipping it. The complete live result must pass the closed classifier, and the classified
    provider and sole entry's non-empty `uid` must equal the stored provider and stored
    `provider_uid`. A divergent confirmation is a conflict that mutates nothing and never rewrites
    the stored binding. Provider eligibility itself is still read from the stored column."""
    # [impl->req~grants-reg-rule-mandatory-providerdata-confirmation~1]
    # [impl->req~grants-reg-entry-mandatory-confirmation~1]
    # [impl->req~grants-reg-gate-compute-hash-and-confirm~1]
    # [impl->req~grants-reg-id-mandatory-confirmation~1]
    if lookups != MANDATORY_PROVIDER_DATA_LOOKUPS:
        raise FreeGrantError("every call performs exactly one providerData confirmation")
    if not issuer_selected_admin_client:
        raise FreeGrantError("the confirmation runs through the issuer-selected Admin client")
    if CONFIRMATION_SKIPPING_DESTINATIONS or (
            destination is not None and str(destination) in CONFIRMATION_SKIPPING_DESTINATIONS):
        raise FreeGrantError("no branch skips the mandatory confirmation")
    before = (row.provider, row.provider_uid)
    # The classifier, the stored-provider equality and the stored-`provider_uid` equality, in the
    # derivation module's own implementation. A divergence raises and mutates nothing.
    canonical = registered_grant_idp_account(row, provider_data)
    if (row.provider, row.provider_uid) != before or mutations:
        raise FreeGrantError("a confirmation rewrites no stored binding and mutates nothing")
    # The stored classification stays the classifier: the live result never reclassifies.
    assert_stored_provider_not_a_mirror(live_provider=row.provider, row=row)
    return canonical


# --- The `idp_account_hash`, and what it is derived from -------------------------------------------

# The Firebase UID is not the uniqueness anchor, and no input derived from it may become one.
FIREBASE_UID_INPUTS: frozenset[str] = frozenset({"firebase_uid", "subject", "uid", "local_id",
                                                 "actor_subject_hash"})


def assert_firebase_uid_not_anchor(anchor_inputs: Iterable[str] = ()) -> UniquenessAnchor:
    """The Firebase UID itself must not be used as the uniqueness anchor: the stable provider UID
    is."""
    # [impl->req~grants-reg-rule-firebase-uid-not-anchor~1]
    offending = sorted(FIREBASE_UID_INPUTS & set(anchor_inputs))
    if offending:
        raise FreeGrantError(f"{offending} is never the per-provider-account uniqueness anchor")
    return assert_uniqueness_anchor(UNIQUENESS_ANCHOR)


def registered_provider_account(row: ExternalIdentityRow) -> ProviderAccount:
    """`idp_account_hash` uses the current linked identity row's stored `provider_uid` as its
    canonical provider account identifier. A row with none is audited as
    `idp_account_not_eligible` and rejected with `verification_required`."""
    # [impl->req~grants-reg-rule-hash-from-stored-provider-uid~1]
    # [impl->req~grants-reg-entry-provider-uid~1]
    # [impl->req~grants-reg-id-canonical-provider-uid~1]
    assert_registered_provider(row)
    if not row.provider_uid:
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                "the linked identity row stores no provider_uid")
    assert_firebase_uid_not_anchor()
    return ProviderAccount(provider=row.provider,
                           provider_uid=registered_grant_canonical_provider_account_id(row))


def registered_account_alias(index: IdpAccountAliasIndex,
                            account: ProviderAccount) -> DerivedValue:
    """The backend computes `idp_account_hash` over the stored provider and stored `provider_uid`
    using this document's HMAC derivation, with explicit domain separation and a persisted key
    version, as the non-authoritative lookup and audit alias.

    The derivation itself is not defined here. The entropy-match principle, the HMAC families and
    formulas, canonicalization, domain separation and its label format, key versioning and rotation,
    and the IDP-account-hash rules all belong to `05-proof-adapters-and-derived-identifiers.md` and
    live in `derived_identifiers`; this is the grant operation's consumption of them, which is all
    the grants file defines."""
    # [impl->req~grants-reg-rule-hash-derivation~1]
    # [impl->req~grants-reg-gate-compute-hash-and-confirm~1]
    # [impl->req~grants-derived-identifiers-owned-by-proof-file~1]
    label = domain_label(DerivationFamily.idp_account_hash)
    if not label.startswith("idp-account:") or not label.endswith(":"):
        raise FreeGrantError(f"{label} is no domain separation label for this derivation")
    return assert_persisted_key_version(index.alias(account))


def consume_registered_gate(index: IdpAccountAliasIndex,
                            account: ProviderAccount,
                            grant_id: UUID,
                            *,
                            transaction: object,
                            grant_transaction: object) -> DerivedValue:
    """The registered gate's per-provider-account bound, enforced on the stable UID: the
    completion transaction resolves-or-creates the canonical `core.provider_accounts` row and
    inserts the `registered_account_grant` gate-consumption row. A consumption conflict is audited
    as `idp_account_already_claimed` and rejected with `account_already_claimed`."""
    # [impl->req~grants-reg-rule-gate-consumption-uniqueness~1]
    # [impl->req~grants-reg-txn-step-05-gate-consumption~1]
    # [impl->req~grants-reg-id-gate-conflict-mapping~1]
    index.register(account)
    try:
        return consume_free_grant_gate(index, account, REGISTERED_GRANT_GATE, grant_id,
                                       transaction=transaction,
                                       grant_transaction=grant_transaction)
    except GateAlreadyConsumedError as conflict:
        raise FreeGrantRejected(
            conflict.result, "account_already_claimed",
            "this provider account already consumed the registered gate",
            status_code=remediation_for(ClientErrorClass.account_already_claimed).http_status
        ) from None


# --- What PostgreSQL may hold for this claim ------------------------------------------------------

# The only two anti-abuse columns that may carry provider-account material.
REGISTERED_ANTI_ABUSE_ALIAS_COLUMNS: tuple[str, str] = ("idp_account_hash",
                                                        "idp_account_hash_key_version")


def assert_no_raw_provider_ids(*,
                               columns: Iterable[str] = (),
                               tables: Iterable[str] = ()) -> None:
    """Raw provider account identifiers must not be persisted in PostgreSQL, audit rows, or grant
    anti-abuse records outside `core.external_identities` and the canonical
    `core.provider_accounts` registry. Only `idp_account_hash` and `idp_account_hash_key_version`
    may be persisted on anti-abuse rows."""
    # [impl->req~grants-reg-rule-no-raw-provider-ids~1]
    for table in tables:
        assert_raw_provider_account_store(table)
    assert_no_raw_provider_account_ids(columns)


# --- The account's own grant history ---------------------------------------------------------------

def assert_account_grant_history(committed_free_sources: Sequence[AccessGrantSource],
                                 *,
                                 converting_active_anonymous: bool = False,
                                 carried_anonymous_credits: bool = False) -> None:
    """A flipped or registered account claiming the registered grant is gated on that account's
    own grant history, not on device state alone: any committed free grant of either source
    refuses a new issuance, the conversion of the user's active anonymous grant being the one
    permitted transition. An upgraded account cannot receive carried anonymous credits plus a
    fresh registered grant."""
    # [impl->req~grants-reg-rule-account-grant-history~1]
    held = [source for source in committed_free_sources if source in FREE_GRANT_SOURCES]
    if converting_active_anonymous:
        if any(source is not CONVERTIBLE_ACTIVE_SOURCE for source in held):
            raise FreeGrantRejected(
                AuthEventResult.policy_rejected, "operation_not_allowed",
                "only an active anonymous device grant converts to the registered grant")
        return
    if carried_anonymous_credits:
        raise FreeGrantRejected(
            AuthEventResult.policy_rejected, "operation_not_allowed",
            "carried anonymous credits and a fresh registered grant are two allowances")
    if len(held) >= LIFETIME_FREE_GRANTS_PER_ACCOUNT:
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "operation_not_allowed",
                                f"a committed {held[0]} grant refuses a new free issuance")


# --- Eligibility keys on stored state alone -------------------------------------------------------

# There is no registered-to-anonymous downgrade, and no live-state path that reclassifies the
# account: a divergent live result can only refuse this one free grant.
REGISTERED_TO_ANONYMOUS_DOWNGRADES: frozenset[str] = frozenset()
LIVE_STATE_RECLASSIFIERS: frozenset[str] = frozenset()


def registered_eligibility(row: ExternalIdentityRow,
                           *,
                           provider_data_confirmed: bool,
                           consulted: Sequence[str] = (),
                           live_provider: IdentityProvider | None = None
                           ) -> tuple[IdentityProvider, str]:
    """Eligibility keys only on backend-stored registration state: the stored provider as the sole
    classifier, the stored `provider_uid`, and the account's own grant history. `registered_at` is
    reporting data and is never consulted. Live Firebase state never reclassifies the account, so
    unlinking at Google or Apple moves no previously registered user into an anonymous grant class
    and no registered-to-anonymous downgrade exists."""
    # [impl->req~grants-reg-rule-stored-state-only~1]
    if REGISTERED_TO_ANONYMOUS_DOWNGRADES or LIVE_STATE_RECLASSIFIERS:
        raise FreeGrantError("no registered-to-anonymous downgrade exists")
    provider, provider_uid = registered_eligibility_inputs(
        row, provider_data_confirmed=provider_data_confirmed, consulted=consulted)
    if live_provider is not None and live_provider is not row.provider:
        # A divergent live result refuses this free grant and reclassifies nothing.
        assert_stored_provider_not_a_mirror(live_provider=live_provider, row=row)
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                "the live provider diverges from the stored classification")
    return provider, provider_uid


# --- The one-active-grant bound --------------------------------------------------------------------


def assert_one_active_grant(*,
                            active_after: int,
                            committed_free_sources: Sequence[AccessGrantSource] = (),
                            second_allowance: bool = False) -> None:
    """The operation preserves the one-active-grant-per-user invariant and never creates a second
    free-credit allowance for the same user."""
    # [impl->req~grants-reg-rule-one-active-grant~1]
    # [impl->req~grants-reg-never-second-allowance~1]
    if second_allowance:
        raise FreeGrantError("the operation never creates a second free-credit allowance")
    if active_after > MAX_ACTIVE_GRANTS_PER_USER:
        raise FreeGrantError("at most one active grant per user survives this operation")
    assert_database_bounds(committed_free_sources=committed_free_sources,
                           active_grants=active_after)


# --- The destination rules ------------------------------------------------------------------------


class RegisteredDestination(StrEnum):
    """The three destinations a call may take, and exactly those three."""
    idempotent_repeat = "idempotent_repeat"
    supersession_conversion = "supersession_conversion"
    new_grant = "new_grant"


class RegisteredDestinationBlocked(FreeGrantRejected):
    """An active grant blocks the destination. The rejection is a wait: it mutates nothing, and it
    discloses only when the held grant ends."""

    def __init__(self, held_grant_ends_at: datetime | None):
        self.held_grant_ends_at = held_grant_ends_at
        super().__init__(AuthEventResult.registered_grant_destination_incompatible,
                         "operation_not_allowed",
                         "an active grant blocks the registered grant destination")


# An operator-managed `manual` grant may run open-ended, and no client-reachable call ends, drops
# or replaces it: the operator support path revokes it.
OPERATOR_MANAGED_SOURCES: frozenset[AccessGrantSource] = frozenset({AccessGrantSource.manual})
CLIENT_REACHABLE_GRANT_ENDERS: frozenset[str] = frozenset()
MANUAL_GRANT_END_PATH: str = "operator_support_revocation"


def manual_grant_end(grant: GrantRow) -> datetime | None:
    """An active `manual` grant may run open-ended: no grant is required to carry a finite
    `ends_at`, and an open-ended one ends only when an operator revokes it. A user who needs it
    ended early goes through the operator support path."""
    # [impl->req~grants-dest-manual-open-ended~1]
    if grant.source not in OPERATOR_MANAGED_SOURCES:
        raise FreeGrantError(f"a {grant.source} grant is not operator-managed state")
    if CLIENT_REACHABLE_GRANT_ENDERS:
        raise FreeGrantError("no client-reachable call ends, drops or replaces a manual grant")
    return grant.ends_at


@dataclass(frozen=True, slots=True)
class RegisteredDecision:
    """The one destination a call takes, the row it acts on, and how many of the user's grants
    were effective when the preflight looked."""
    destination: RegisteredDestination
    grant: GrantRow | None = None
    effective_grants: int = 0
    lapsed_grant_ids: tuple[UUID, ...] = ()


def committed_registered_grant(grants: Sequence[GrantRow]) -> GrantRow | None:
    """The user's own committed `registered_account_grant` row, if the history carries one."""
    for grant in grants:
        if grant.source is REGISTERED_GRANT_SOURCE:
            return grant
    return None


def lapsed_active_grants(grants: Sequence[GrantRow], now: datetime) -> tuple[UUID, ...]:
    """Rows still on `status = 'active'` whose time has passed. They are not effective, so they
    block nothing; this operation's own insert flips them under the lazy-flip rule in
    `07-quota-and-access-enforcement.md`."""
    # [impl->req~grants-dest-rejection-is-a-wait~1]
    return tuple(grant.grant_id for grant in grants
                 if grant.status is AccessGrantStatus.active and not is_effective(grant, now))


def destination_rejection(held: GrantRow,
                          *,
                          mutations: Sequence[str] = (),
                          registered_bit_written: bool = False) -> RegisteredDestinationBlocked:
    """The rejection an incompatible active grant produces. It is a wait, not a forfeit: it
    mutates nothing — no grant, no gate-consumption row, no free-grant-consumed marker — and it
    runs in the preflight ahead of the registered-claimed bit write, so it burns no device slot.
    It reports when the held grant ends, and nothing else about it."""
    # [impl->req~grants-dest-rejection-is-a-wait~1]
    if mutations:
        raise FreeGrantError(f"the destination rejection mutates nothing, not {sorted(mutations)}")
    if registered_bit_written:
        raise FreeGrantError("the destination check runs ahead of the registered-bit write")
    ends_at = manual_grant_end(held) if held.source in OPERATOR_MANAGED_SOURCES else held.ends_at
    return RegisteredDestinationBlocked(ends_at)


def select_destination(*,
                       grants: Sequence[GrantRow],
                       committed_free_sources: Sequence[AccessGrantSource],
                       now: datetime,
                       gate_consumption_grant_id: UUID | None = None,
                       registered_bit_written: bool = False) -> RegisteredDecision:
    """Select exactly one destination from the user's locked grant history.

    The idempotent repeat is determined first, so a repeat call whose own registered grant is
    still active reaches it rather than the destination-incompatible rejection. Any other active
    grant — anything that is neither an anonymous device grant nor this user's own committed
    registered grant — rejects as `registered_grant_destination_incompatible` under
    `operation_not_allowed`. An active anonymous device grant selects supersession conversion, and
    no free-grant history at all selects new-grant creation.
    """
    # [impl->req~grants-dest-idempotent-repeat~1]
    # [impl->req~grants-dest-incompatible-active-grant~1]
    # [impl->req~grants-dest-supersession-conversion~1]
    # [impl->req~grants-dest-new-grant-creation~1]
    # [impl->req~grants-reg-txn-step-02-select-destination~1]
    lapsed = lapsed_active_grants(grants, now)
    effective = sum(1 for grant in grants if is_effective(grant, now))
    repeat = committed_registered_grant(grants)
    if repeat is not None:
        # The idempotent repeat: the gate-consumption rows must identify this same grant.
        if gate_consumption_grant_id is not None and gate_consumption_grant_id != repeat.grant_id:
            raise FreeGrantRejected(
                AuthEventResult.idp_account_already_claimed, "account_already_claimed",
                "a registered gate consumption belongs to another grant",
                status_code=remediation_for(ClientErrorClass.account_already_claimed).http_status)
        return RegisteredDecision(destination=RegisteredDestination.idempotent_repeat,
                                  grant=repeat, effective_grants=effective,
                                  lapsed_grant_ids=lapsed)
    blocking = [grant for grant in grants
                if is_effective(grant, now) and grant.source is not CONVERTIBLE_ACTIVE_SOURCE]
    if blocking:
        # A wait, not a forfeit: nothing is mutated and no device slot is burned.
        raise destination_rejection(blocking[0], registered_bit_written=registered_bit_written)
    convertible = [grant for grant in grants
                   if is_effective(grant, now) and grant.source is CONVERTIBLE_ACTIVE_SOURCE]
    if convertible:
        assert_account_grant_history(committed_free_sources, converting_active_anonymous=True)
        return RegisteredDecision(destination=RegisteredDestination.supersession_conversion,
                                  grant=convertible[0], effective_grants=effective,
                                  lapsed_grant_ids=lapsed)
    assert_account_grant_history(committed_free_sources)
    return RegisteredDecision(destination=RegisteredDestination.new_grant,
                              effective_grants=effective, lapsed_grant_ids=lapsed)


# --- Audit details ---------------------------------------------------------------------------------


def registered_audit_details(row: ExternalIdentityRow,
                             *,
                             alias: DerivedValue,
                             destination: RegisteredDestination | None = None,
                             grant_id: UUID | None = None,
                             account_context: Mapping[str, str] | None = None
                             ) -> dict[str, dict[str, Any]]:
    """The audit details a successful or rejected attempt carries: the current identity provider
    sourced from the stored `core.external_identities.provider` column, the
    `idp_account_hash_key_version`, and non-secret account context for support correlation. The
    canonical account identifier stays the stored `provider_uid`, and no raw provider account
    identifier appears in details."""
    # [impl->req~grants-reg-audit-details~1]
    context = dict(account_context or {})
    details: dict[str, dict[str, Any]] = {
        "identity": {"provider": str(row.provider), **context},
        "anti_abuse": {"idp_account_hash_key_version": alias.key_version},
    }
    if destination is not None:
        details["mutation"] = {"destination": str(destination)}
        if grant_id is not None:
            details["mutation"]["grant_id"] = str(grant_id)
    for section in details.values():
        assert_no_raw_provider_ids(columns=section)
        raw = [name for name, value in section.items()
               if row.provider_uid and str(value) == row.provider_uid]
        if raw:
            raise FreeGrantError(f"{raw} would carry a raw provider account identifier")
    return details


def registered_claim_rejected(result: AuthEventResult, message: str = "") -> FreeGrantRejected:
    """One rejection of this claim, by audited internal result. The result-to-class mapping and
    the condition table belong to `registered_grant_failures`, which sits below this module in
    the import graph, so it is read at call time rather than at module import — there is still
    only one mapping."""
    # [impl->req~grants-reg-failure-classes~1]
    from nativespeaker.api.auth.registered_grant_failures import (  # noqa: PLC0415
        registered_claim_rejected as classify,
    )

    return classify(result, message)


def registered_condition_rejected(condition: RegClaimCondition,
                                  message: str = "") -> FreeGrantRejected:
    """One rejection of this claim, by the failure-table condition it is. Same owner, same
    deferred read: the audited result and the client class both come from that table."""
    # [impl->req~grants-reg-failure-classes~1]
    from nativespeaker.api.auth.registered_grant_failures import (  # noqa: PLC0415
        registered_condition_rejected as classify,
    )

    return classify(condition, message)


# --- The rules, in the one order they run in --------------------------------------------------------


class RegisteredClaimStep(StrEnum):
    """The steps of one `claim_registered_grant` attempt, in the one order they may run in.

    The shared pre-consumption checks — the barrier's four checks, each rejected before every
    challenge check — and handler-side completion admission come first, and the challenge claim
    follows them: an identity the barrier refuses is rejected before the claim and leaves the
    challenge unclaimed.
    """
    admission = "admission"
    identity_barrier = "identity_barrier"
    challenge_claim = "challenge_claim"
    claim_kind = "claim_kind"
    provider_data_confirmation = "provider_data_confirmation"
    device_state_read = "device_state_read"
    database_eligibility = "database_eligibility"
    registered_bit_write = "registered_bit_write"
    activation = "activation"


REGISTERED_CLAIM_STEPS: tuple[RegisteredClaimStep, ...] = tuple(RegisteredClaimStep)


@dataclass(frozen=True, slots=True)
class RegisteredActivation:
    """The rows one completion transaction wrote, and the audit record it appended. `identity` is
    the claimant's identity row as the transaction leaves it, carrying the permanent
    free-grant-consumed marker."""
    destination: RegisteredDestination
    grant: dict[str, Any]
    anti_abuse: dict[str, Any]
    usage: NewUsageRow
    alias: DerivedValue
    audit: AuthEvent
    superseded: dict[str, Any] | None = None
    lapsed_grant_ids: tuple[UUID, ...] = ()
    identity: ExternalIdentityRow | None = None


@dataclass(frozen=True, slots=True)
class RegisteredGrantState:
    """What the completion returns: the active registered grant, its tier, and the current usage
    state of that grant."""
    grant_id: UUID
    status: AccessGrantStatus
    tier_id: str
    monthly_period: str
    monthly_used: int


def returned_grant_state(activation: RegisteredActivation) -> RegisteredGrantState:
    """Step 7: return the active registered grant, tier, and current usage state. A mutating
    destination returns the row it just wrote and that row's own usage state — for the conversion
    path, the allowance carried across from the superseded grant."""
    # [impl->req~grants-reg-txn-step-07-return-grant~1]
    grant = activation.grant
    if grant["status"] is not AccessGrantStatus.active:
        raise FreeGrantError("the completion returns the active registered grant")
    if grant["source"] is not REGISTERED_GRANT_SOURCE:
        raise FreeGrantError("the completion returns this operation's own grant")
    usage = activation.usage
    if usage.grant_id != grant["id"]:
        raise FreeGrantError("the usage state returned is the returned grant's own")
    return RegisteredGrantState(grant_id=grant["id"], status=grant["status"],
                                tier_id=grant["tier_id"], monthly_period=usage.monthly_period,
                                monthly_used=usage.monthly_used)


def repeated_grant_state(grant: GrantRow, usage: tuple[str, int]) -> RegisteredGrantState:
    """The same three things for the idempotent repeat, which writes nothing and returns the held
    registered grant's live state."""
    # [impl->req~grants-reg-txn-step-07-return-grant~1]
    if grant.source is not REGISTERED_GRANT_SOURCE:
        raise FreeGrantError("the repeat returns the user's own registered grant")
    period, used = usage
    return RegisteredGrantState(grant_id=grant.grant_id, status=grant.status,
                                tier_id=grant.tier_id, monthly_period=period, monthly_used=used)


# Deferred foreign keys are checked once, at commit, and never relaxed per statement.
DEFERRED_KEY_CHECK_POINT: str = "commit"


def assert_deferred_keys_checked_at_commit(transaction: object,
                                          *, check_point: str = DEFERRED_KEY_CHECK_POINT) -> None:
    """All deferred foreign keys are checked at commit of this one transaction, so the composite and
    generated-column foreign keys, the one-active-grant-per-user index and the lifetime free-grant
    index keep the declarative behavior table semantics describes."""
    # [impl->req~grants-reg-txn-step-05-gate-consumption~1]
    if transaction is None:
        raise FreeGrantError("the deferred keys are checked at this transaction's commit")
    if check_point != DEFERRED_KEY_CHECK_POINT:
        raise FreeGrantError(f"deferred keys are checked at {DEFERRED_KEY_CHECK_POINT}")


def reconfirm_registered_claimant(row: ExternalIdentityRow,
                                  account: ProviderAccount,
                                  moment: datetime,
                                  *,
                                  destination: RegisteredDestination) -> ExternalIdentityRow:
    """Step 1's reconfirmation, under the lock the completion transaction just took.

    The user must be active and unblocked, the identity active rather than historical, and the exact
    stored provider, `provider_uid` and registered state the hash used must still apply. Any
    inactive or blocked user or historical identity keeps its own distinct internal result under the
    shared `account_unavailable` class, and no grant mutation happens.

    Step 2's free-grant-consumed reconfirmation runs with it: a new issuance needs the marker unset,
    while the conversion transitions the same already-marked lineage rather than issuing a second
    allowance.
    """
    # [impl->req~grants-reg-txn-step-01-lock-and-reconfirm~1]
    # [impl->req~grants-reg-txn-step-02-select-destination~1]
    if row.identity_state is not IdentityState.active:
        raise registered_claim_rejected(AuthEventResult.historical_identity,
                                        "the claimant identity is no longer active")
    assert_registered_provider(row)
    if not row.provider_uid or row.provider_uid != account.provider_uid \
            or row.provider is not account.provider:
        raise FreeGrantError("the stored binding the hash used no longer applies")
    if destination is RegisteredDestination.supersession_conversion:
        # The conversion transitions the lineage the anonymous grant opened rather than issuing a
        # second allowance, so a marker that is already set is exactly what it expects — and it must
        # not post-date the conversion. A lineage carrying no marker yet takes one below.
        if row.free_grant_consumed_at is not None:
            assert_conversion_same_lineage(row, converted_at=moment)
    elif not free_grant_available(row, AuthOperation.claim_registered_grant):
        from nativespeaker.api.auth.registered_grant_failures import (  # noqa: PLC0415
            RegClaimCondition,
        )

        raise registered_condition_rejected(
            RegClaimCondition.structural_policy_block,
            "this account already consumed its one lifetime free grant")
    return row


class RegisteredGrantClaim:
    """One `claim_registered_grant` attempt's required rules, in the one order they run in.

    Each step records itself, and a step that runs out of order, twice, or without its
    predecessors refuses. The steps delegate: the barrier resolves the identity, the shared
    completion requirements own the challenge claim and consumption, the proof adapters own the
    vendor sequence, and the schema module owns the row shapes.
    """

    def __init__(self) -> None:
        self.steps: list[RegisteredClaimStep] = []
        self.kind: ClaimBranch | None = None
        self.account: ProviderAccount | None = None
        self.decision: RegisteredDecision | None = None
        self.registered_claimed: bool | None = None
        self.provider_data_lookups = 0
        self.vendor_calls = 0
        # What this attempt resolved, for the audit details every outcome of it owes, and whether
        # the claim kind carries a registered-claimed bit at all.
        self.row: ExternalIdentityRow | None = None
        self.alias: DerivedValue | None = None
        self.durable_bit: bool = True

    # --- ordering ---------------------------------------------------------------------------

    def _record(self, step: RegisteredClaimStep) -> None:
        position = REGISTERED_CLAIM_STEPS.index(step)
        if self.steps and position <= REGISTERED_CLAIM_STEPS.index(self.steps[-1]):
            raise FreeGrantError(f"{step} cannot run after {self.steps[-1]}")
        self.steps.append(step)

    def _require(self, *steps: RegisteredClaimStep) -> None:
        missing = [step for step in steps if step not in self.steps]
        if missing:
            raise FreeGrantError(f"{missing} must run first")

    def _kind(self) -> ClaimBranch:
        if self.kind is None:
            raise FreeGrantError("the claim kind is resolved before the gate is read")
        return self.kind

    def _rejected[E: (FreeGrantRejected, ClaimRejection)](self, exc: E) -> E:
        """One rejection of this claim, carrying the audit details a rejected attempt owes: the
        stored-column provider, the `idp_account_hash_key_version`, and the non-secret account
        context support correlates on. They are available from the confirmation step onwards; a
        rejection taken before the alias exists carries what the row alone can say."""
        # [impl->req~grants-reg-audit-details~1]
        if self.row is not None:
            exc.audit_details = (registered_audit_details(self.row, alias=self.alias)
                                 if self.alias is not None
                                 else {"identity": {"provider": str(self.row.provider)}})
        return exc

    # --- the rules --------------------------------------------------------------------------

    def admit(self, *, pre_consumption_passed: bool, handler_admission_passed: bool) -> None:
        """The shared pre-consumption checks and the handler-side completion admission run before
        the operation challenge is claimed and before any vendor or Firebase call."""
        self._record(RegisteredClaimStep.admission)
        if not (pre_consumption_passed and handler_admission_passed):
            raise FreeGrantError("the shared and handler-side admission checks must pass first")

    def claim_challenge(self, claim: Callable[[], ClaimOutcome]) -> ClaimOutcome:
        """The operation challenge is claimed under the shared completion requirements — after the
        barrier's checks and completion admission, and still before any vendor call.

        The mandatory `providerData` confirmation, the device-checked kinds' bit read and write, and
        the Turnstile validation all run after this claim. IDP-account derivation is the exception:
        completion admission is keyed on `user + idp_account_hash`, so the alias is derived from the
        stored provider and stored `provider_uid` before that admission check and therefore before
        the claim — it needs no Firebase and no vendor call, so deriving it early spends nothing. A
        duplicate that loses the claim is rejected here, having spent neither.
        """
        # [impl->req~grants-reg-mutation-challenge-claim-order~1]
        self._require(RegisteredClaimStep.admission, RegisteredClaimStep.identity_barrier)
        self._record(RegisteredClaimStep.challenge_claim)
        if self.vendor_calls or self.provider_data_lookups:
            raise FreeGrantError("no vendor or Firebase call precedes the challenge claim")
        outcome = claim()
        if outcome is not ClaimOutcome.claimed:
            raise FreeGrantError(f"the attempt did not claim the challenge: {outcome}")
        return outcome

    def resolve_identity(self,
                         context: VerifiedIdentityContext,
                         row: ExternalIdentityRow,
                         *,
                         offered_identity_inputs: Sequence[str] = ()) -> ExternalIdentityRow:
        """The shared mandatory pre-handler authentication-and-identity-resolution barrier must
        produce the backend-verified Firebase ID token's `(issuer, subject)` from the
        `Authorization` header and resolve it to a linked identity for an active user and active
        external identity.

        Which outcomes are admitted, and what each refused one audits as, is the barrier's own
        predicate: a blocked user or a historical identity keeps its distinct internal result
        under the shared `account_unavailable` class and never receives
        `preauth_identity_not_allowed`, which would send the client into create-user.
        """
        # [impl->req~grants-reg-rule-identity-barrier~1]
        # [impl->req~grants-reg-class-account-unavailable~1]
        # [impl->req~grants-reg-entry-barrier~1]
        # [impl->req~grants-reg-gate-resolve-identity~1]
        self._require(RegisteredClaimStep.admission)
        self._record(RegisteredClaimStep.identity_barrier)
        if not context.issuer or not context.subject:
            raise FreeGrantError("the barrier resolved no verified issuer and subject")
        assert_no_device_proof_as_identity(evaluated=offered_identity_inputs)
        self.row = row
        result = barrier_result_for(context.outcome,
                                   *route_for(AuthOperation.claim_registered_grant))
        if result is not None:
            raise self._rejected(
                registered_claim_rejected(result, f"the barrier refused {context.outcome}"))
        if row.identity_state is not IdentityState.active:
            raise self._rejected(registered_claim_rejected(
                AuthEventResult.historical_identity,
                "the claim needs an active external identity"))
        if context.external_identity_id is not None and context.external_identity_id != row.id:
            raise FreeGrantError("the resolved context and the identity row must be the same row")
        # The stored provider is the classifier, read from the row and from nothing else.
        assert_registered_provider(row)
        return row

    def resolve_kind(self,
                     evidence: ClaimEvidence,
                     *,
                     platform_header: str | None = None,
                     optional_material: Sequence[str] = (),
                     consulted: Sequence[str] = ()) -> ClaimBranch:
        """Resolve the one complete claim kind server-side, before any eligibility check, vendor
        call or ledger write."""
        # [impl->req~grants-reg-rule-server-owned-claim-kind~1]
        # [impl->req~grants-reg-entry-claim-kind-proof-set~1]
        # [impl->req~grants-reg-gate-resolve-claim-kind~1]
        self._require(RegisteredClaimStep.identity_barrier)
        self._record(RegisteredClaimStep.claim_kind)
        if self.vendor_calls or self.provider_data_lookups:
            raise FreeGrantError("the request shape is validated before any vendor call")
        self.kind = resolve_claim_kind(evidence, platform_header=platform_header,
                                       optional_material=optional_material, consulted=consulted)
        return self.kind

    def confirm_binding(self,
                        row: ExternalIdentityRow,
                        provider_data: Sequence[object],
                        index: IdpAccountAliasIndex,
                        *,
                        destination: RegisteredDestination | None = None
                        ) -> tuple[ProviderAccount, DerivedValue]:
        """The mandatory fail-closed `providerData` confirmation, and the alias derived from the
        stored provider and stored `provider_uid`."""
        # [impl->req~grants-reg-rule-mandatory-providerdata-confirmation~1]
        # [impl->req~grants-reg-rule-hash-from-stored-provider-uid~1]
        # [impl->req~grants-reg-gate-compute-hash-and-confirm~1]
        # [impl->req~grants-reg-entry-mandatory-confirmation~1]
        self._require(RegisteredClaimStep.claim_kind)
        self._record(RegisteredClaimStep.provider_data_confirmation)
        account = registered_provider_account(row)
        self.provider_data_lookups += 1
        canonical = confirm_stored_binding_live(row, provider_data,
                                                lookups=self.provider_data_lookups,
                                                destination=destination)
        if canonical != account.provider_uid:
            raise FreeGrantError("the confirmed account is the stored binding's own account")
        self.account = account
        self.row = row
        self.alias = registered_account_alias(index, account)
        return account, self.alias

    def read_registered_state(self,
                              *,
                              native: tuple[DeviceStateAdapter, Any, NativeClaimLedger]
                              | None = None,
                              turnstile: Callable[[], bool] | None = None) -> bool:
        """On the iOS and Android device-checked kinds, verify the proof and read the
        registered-claimed bit; an already-set bit returns `device_grant_exhausted`. On Android
        the read-check-write-confirm sequence runs where the checked-in release policy classes the
        release `device_recall_required`; a Play Integrity verdict is still required on every
        Android claim, but a `no_device_recall` release carries no registered-claimed bit at all,
        so nothing is read or written for it and the claim rests on the account-level rules alone.
        The web kind has no such bit and relies on the account-level rules plus the mandatory
        Turnstile pass, whose denial and dependency failure are the adapter's own outcomes."""
        # [impl->req~grants-reg-rule-device-checked-kinds-bit~1]
        # [impl->req~grants-reg-gate-resolve-claim-kind~1]
        self._require(RegisteredClaimStep.provider_data_confirmation)
        self._record(RegisteredClaimStep.device_state_read)
        kind = self._kind()
        if kind in DEVICE_CHECKED_KINDS:
            if native is None:
                raise FreeGrantError(f"{kind} reads its registered-claimed state")
            adapter, material, ledger = native
            operation = AuthOperation.claim_registered_grant
            self.vendor_calls += 1
            adapter.verify_material(operation, material, ledger)
            already = adapter.read_claimed(operation, material, ledger)
            # Whether this platform carries a registered-claimed bit is the checked-in release
            # policy's answer, which the vendor read consulted; the claim reads it from the
            # attempt's own ledger rather than keeping a second copy of that policy.
            self.durable_bit = ledger.durable_bit_participates
            if self.durable_bit:
                registered_claim_bit(kind)
                # The same durable-state meaning on every participating platform: this durable
                # device state already claimed a registered account grant.
                if already:
                    raise self._rejected(DeviceGrantExhausted(non_accusatory_copy()))
            self.registered_claimed = already
            return already
        self.durable_bit = False
        self.vendor_calls += 1
        self._validate_turnstile(turnstile)
        self.registered_claimed = False
        return False

    def _validate_turnstile(self, turnstile: Callable[[], bool] | None) -> None:
        """The web kind's mandatory Turnstile pass. `siteverify`'s own outcomes decide: a denial
        — invalid, expired, duplicate or replayed token, or a hostname mismatch — is the
        durable `verification_required` sign-in-gate rejection, and a dependency failure or
        misconfiguration is the transient one. Neither class is invented here."""
        # [impl->req~grants-reg-gate-resolve-claim-kind~1]
        # [impl->req~grants-reg-rule-device-checked-kinds-bit~1]
        from nativespeaker.api.auth.registered_grant_failures import (  # noqa: PLC0415
            RegClaimCondition,
        )

        if turnstile is None:
            raise FreeGrantError("the web kind needs its Turnstile validation")
        try:
            passed = turnstile()
        except TurnstileDenied as denied:
            raise self._rejected(
                registered_condition_rejected(RegClaimCondition.turnstile_denied,
                                              str(denied))) from None
        except TurnstileUnavailable as unavailable:
            raise self._rejected(
                registered_condition_rejected(RegClaimCondition.turnstile_dependency_failed,
                                              str(unavailable))) from None
        if not passed:
            raise self._rejected(
                registered_condition_rejected(RegClaimCondition.turnstile_denied,
                                              "the web kind needs a passing Turnstile validation"))

    def check_database_eligibility(self,
                                   *,
                                   grants: Sequence[GrantRow],
                                   committed_free_sources: Sequence[AccessGrantSource],
                                   now: datetime,
                                   gate_consumption_grant_id: UUID | None = None,
                                   ledger: NativeClaimLedger | None = None
                                   ) -> RegisteredDecision:
        """After an unset bit, or immediately where durable device state does not participate,
        check the account's own grant history and select the one destination."""
        # [impl->req~grants-reg-rule-account-grant-history~1]
        # [impl->req~grants-dest-incompatible-active-grant~1]
        # [impl->req~grants-reg-gate-db-history-destination~1]
        self._require(RegisteredClaimStep.device_state_read)
        self._record(RegisteredClaimStep.database_eligibility)
        if ledger is not None:
            ledger.record(NativeClaimStep.database_eligibility)
        try:
            decision = select_destination(grants=grants,
                                         committed_free_sources=committed_free_sources, now=now,
                                         gate_consumption_grant_id=gate_consumption_grant_id,
                                         registered_bit_written=(
                                             RegisteredClaimStep.registered_bit_write in self.steps))
        except FreeGrantRejected as blocked:
            # A rejected attempt owes the same audit details a successful one does.
            # [impl->req~grants-reg-audit-details~1]
            raise self._rejected(blocked) from None
        self.decision = decision
        return decision

    def write_registered_bit(self,
                             adapter: DeviceStateAdapter,
                             material: Any,
                             *,
                             ledger: NativeClaimLedger) -> DeviceBitWrite:
        """On the device-checked kinds, write the registered-claimed bit and receive vendor
        confirmation before activation. Any failed, timed-out, cancelled, ambiguous or
        unattemptable write rejects before activation with no grant."""
        # [impl->req~grants-reg-rule-device-checked-kinds-bit~1]
        # [impl->req~grants-reg-gate-write-registered-bit~1]
        self._require(RegisteredClaimStep.database_eligibility)
        if self._kind() not in DEVICE_CHECKED_KINDS:
            raise FreeGrantError("only a device-checked kind writes a registered-claimed bit")
        if not self.durable_bit:
            raise FreeGrantError("a no_device_recall release carries no registered-claimed bit")
        self._record(RegisteredClaimStep.registered_bit_write)
        self.vendor_calls += 1
        write = adapter.write_claimed(AuthOperation.claim_registered_grant, material, ledger)
        assert_grant_row_permitted(write)
        return write

    def activate(self,
                 *,
                 row: ExternalIdentityRow,
                 grant_id: UUID,
                 tier_id: str,
                 alias_index: IdpAccountAliasIndex,
                 transaction: object,
                 locks: LockLedger,
                 consume_challenge: Callable[[], bool],
                 subject_hasher: SubjectHasher,
                 carried_usage: tuple[str, int] | None = None,
                 write: DeviceBitWrite | None = None,
                 context: ExecutionContext = CLAIM_EXECUTION_CONTEXT,
                 now: datetime | None = None) -> RegisteredActivation:
        """One completion transaction, for the destination the preflight selected.

        Supersession conversion moves the active anonymous grant to `expired` with `ends_at` set
        to the conversion time, leaves its `source` and its anti-abuse row untouched, and inserts
        the new active registered grant with its own anti-abuse and gate-consumption rows and a
        usage row carrying the superseded grant's `monthly_period` and `monthly_used`. New-grant
        creation inserts the same rows with a fresh usage row for the current period and
        `monthly_used = 0`. Either way exactly one destination executes, and the whole transaction
        rolls back on any insertion failure or uniqueness conflict.

        It is entered only after the confirmed write on a device-checked kind, or after the database
        preflight and the mandatory Turnstile validation on the web kind.
        """
        # [impl->req~grants-dest-supersession-conversion~1]
        # [impl->req~grants-dest-new-grant-creation~1]
        # [impl->req~grants-reg-rule-one-active-grant~1]
        # [impl->req~grants-reg-completion-transaction-entry~1]
        # [impl->req~grants-reg-never-second-allowance~1]
        self._require(RegisteredClaimStep.database_eligibility)
        decision = self.decision
        account = self.account
        if decision is None or account is None:
            raise FreeGrantError("the destination and the confirmed account precede activation")
        kind = self._kind()
        # A kind that carries durable device state activates only behind this attempt's own
        # vendor-confirmed write. An Android release classed `no_device_recall` carries none, so
        # it has no write to confirm and rests on the account-level rules alone.
        if kind in DEVICE_CHECKED_KINDS and self.durable_bit:
            self._require(RegisteredClaimStep.registered_bit_write)
            assert_native_claim_written_before_grant(
                native_claim_written=bool(write is not None and write.confirmed),
                same_attempt=True)
            assert_grant_row_permitted(write)
        elif write is not None:
            raise FreeGrantError(f"{kind} carries no registered-claimed bit to confirm")
        self._record(RegisteredClaimStep.activation)
        assert_execution_context(context)
        if decision.destination is RegisteredDestination.idempotent_repeat:
            raise FreeGrantError("the idempotent repeat returns the held grant and writes nothing")
        if not tier_id:
            raise FreeGrantError("the grant names the configured free tier")
        moment = now if now is not None else datetime.now(UTC)
        superseded_row: dict[str, Any] | None = None
        carried: tuple[str, int] | None = None
        if (carried_usage is not None
                and decision.destination is not RegisteredDestination.supersession_conversion):
            raise FreeGrantError("only the conversion path carries an existing usage row across")
        locks.lock_user(row.user_id)
        superseded = decision.grant
        if decision.destination is RegisteredDestination.supersession_conversion:
            if superseded is None:
                raise FreeGrantError("the conversion path supersedes one anonymous grant")
            lock_grant_set(locks, sorted({superseded.grant_id, grant_id}))
            reconfirm_registered_claimant(row, account, moment,
                                          destination=decision.destination)
            assert_grant_source_never_rewritten(superseded.source, superseded.source)
            assert_registered_conversion(superseded_source=superseded.source,
                                         created_source=REGISTERED_GRANT_SOURCE,
                                         superseded_transaction=transaction,
                                         created_transaction=transaction)
            # The old row is deactivated before the new one is inserted, in this transaction.
            superseded_row = {
                "id": superseded.grant_id,
                "source": superseded.source,
                "status": AccessGrantStatus.expired,
                "ends_at": moment,
            }
            if carried_usage is None:
                raise FreeGrantError(
                    "the conversion carries the superseded grant's monthly_period and "
                    "monthly_used across unchanged")
            carried = carried_usage
        else:
            lock_grant_set(locks, [grant_id])
            reconfirm_registered_claimant(row, account, moment,
                                          destination=decision.destination)
        grant: dict[str, Any] = {
            "id": grant_id,
            "user_id": row.user_id,
            "tier_id": tier_id,
            "source": REGISTERED_GRANT_SOURCE,
            "status": AccessGrantStatus.active,
            "subscription_id": None,
        }
        assert_billing_separation(REGISTERED_GRANT_SOURCE, None)
        assert_grant_columns_entitlement_only(grant)
        # The new row is the user's one active grant: the conversion deactivated the only other
        # effective one, and every other effective grant already blocked the destination.
        superseded_count = (1 if decision.destination
                            is RegisteredDestination.supersession_conversion else 0)
        assert_one_active_grant(active_after=1 + decision.effective_grants - superseded_count,
                                second_allowance=False)
        try:
            alias = consume_registered_gate(alias_index, account, grant_id,
                                            transaction=transaction,
                                            grant_transaction=transaction)
        except FreeGrantRejected as conflict:
            # `idp_account_already_claimed` is exactly the rejection support correlates back to a
            # provider account and a key version, so it carries this attempt's audit details.
            # [impl->req~grants-reg-audit-details~1]
            raise self._rejected(conflict) from None
        anti_abuse = free_grant_anti_abuse_row(
            grant_id=grant_id, source=REGISTERED_GRANT_SOURCE,
            idp_account_hash=alias.digest,
            idp_account_hash_key_version=alias.key_version,
            created_at=moment, grant_columns=grant)
        assert_no_raw_provider_ids(columns=anti_abuse)
        # The conversion path carries the superseded grant's `monthly_period` and `monthly_used`
        # across unchanged; the new-grant path opens the current period at `monthly_used = 0`.
        # [impl->req~grants-reg-txn-step-03-supersession-conversion~1]
        # [impl->req~grants-reg-txn-step-04-new-grant-creation~1]
        # [impl->req~grants-inherit-conversion-carryover~1]
        # [impl->req~grants-inherit-new-grant-zero-used~1]
        usage = new_usage_row(grant_id, now=moment, carried=carried,
                              grant_transaction=transaction, usage_transaction=transaction)
        # The identity record's permanent free-grant-consumed marker, set where not already set, in
        # this same transaction — then the deferred foreign keys are checked at commit.
        # [impl->req~grants-reg-txn-step-05-gate-consumption~1]
        marked = mark_free_grant_consumed(row, now=moment, grant_transaction=transaction,
                                          marker_transaction=transaction)
        assert_deferred_keys_checked_at_commit(transaction)
        assert_same_transaction("claim_registered_grant", [transaction] * 4)
        # [impl->req~grants-reg-txn-step-06-consume-challenge-audit~1]
        if not consume_challenge():
            raise FreeGrantError("the challenge this attempt claimed is consumed exactly once")
        audit = terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                               operation=AuthOperation.claim_registered_grant,
                               actor=_actor_for(row, alias, subject_hasher),
                               details=registered_audit_details(
                                   row, alias=alias, destination=decision.destination,
                                   grant_id=grant_id))
        return RegisteredActivation(destination=decision.destination, grant=grant,
                                    anti_abuse=anti_abuse, usage=usage, alias=alias, audit=audit,
                                    superseded=superseded_row,
                                    lapsed_grant_ids=decision.lapsed_grant_ids,
                                    identity=marked)

    def repeat(self,
               row: ExternalIdentityRow,
               *,
               alias: DerivedValue,
               grant: GrantRow,
               subject_hasher: SubjectHasher) -> AuthEvent:
        """The idempotent repeat's outcome: the held registered grant is returned unchanged, after
        the same mandatory live confirmation every other branch performs."""
        # [impl->req~grants-dest-idempotent-repeat~1]
        self._require(RegisteredClaimStep.provider_data_confirmation,
                      RegisteredClaimStep.database_eligibility)
        if self.provider_data_lookups != MANDATORY_PROVIDER_DATA_LOOKUPS:
            raise FreeGrantError("the idempotent repeat confirms the binding too")
        if grant.source is not REGISTERED_GRANT_SOURCE:
            raise FreeGrantError("the repeat returns the user's own registered grant")
        return terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                              operation=AuthOperation.claim_registered_grant,
                              actor=_actor_for(row, alias, subject_hasher),
                              details=registered_audit_details(
                                  row, alias=alias,
                                  destination=RegisteredDestination.idempotent_repeat,
                                  grant_id=grant.grant_id))


def _actor_for(row: ExternalIdentityRow, alias: DerivedValue,
               subject_hasher: SubjectHasher) -> AuthActor:
    """The barrier actor context the audit row carries: the issuer, the stored provider, and the
    backend-verified subject as the shared keyed hash with the version of the key that produced
    it — the one derivation every actor-populating event producer shares. No raw subject exists to
    carry: `AuthActor` has no field for one, and no raw provider account identifier appears
    either."""
    # [impl->req~grants-reg-audit-details~1]
    # [impl->req~shared-auth-events-actor-subject-hash~1]
    assert_persisted_key_version(alias)
    subject_hash, key_version = subject_hasher(actor_subject_preimage(row.issuer, row.subject))
    actor = AuthActor(issuer=row.issuer, subject_hash=subject_hash,
                      subject_hash_key_version=key_version, provider=row.provider)
    if actor.subject_hash is None or actor.provider is not row.provider:
        raise FreeGrantError("the actor carries the stored provider and the hashed subject")
    return actor


def supersession_write_order(activation: RegisteredActivation) -> tuple[str, ...]:
    """The order the conversion transaction writes in: the anonymous row is deactivated before
    the registered row is inserted, so one-active-grant-per-user holds throughout. Its
    `source` stays `anonymous_device_grant` forever and its anti-abuse row is left untouched."""
    # [impl->req~grants-dest-supersession-conversion~1]
    # [impl->req~grants-reg-txn-step-03-supersession-conversion~1]
    if activation.destination is not RegisteredDestination.supersession_conversion:
        raise FreeGrantError("only the conversion path supersedes a grant")
    superseded = activation.superseded
    if superseded is None:
        raise FreeGrantError("the conversion path records the superseded row")
    if superseded["source"] is not CONVERTIBLE_ACTIVE_SOURCE:
        raise FreeGrantError("the superseded row keeps its anonymous_device_grant source")
    if superseded["status"] is not AccessGrantStatus.expired or superseded["ends_at"] is None:
        raise FreeGrantError("the superseded row expires at the conversion time")
    if "anti_abuse" in superseded:
        raise FreeGrantError("the superseded grant's anti-abuse row is left untouched")
    return ("expire_anonymous_grant", "insert_registered_grant", "insert_anti_abuse_row",
            "insert_gate_consumption_row", "insert_usage_row")
