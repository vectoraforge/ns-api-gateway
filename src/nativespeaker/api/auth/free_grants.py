"""Free-credit grants and anti-abuse: the two claim operations, and the anonymous claim's rules.

Free credits exist only as ordinary `core.access_grants` rows created by exactly two operations,
`claim_anonymous_grant` and `claim_registered_grant`. This module is where the grants domain's own
rules live: which operation may create which source, how `claim_anonymous_grant` selects among its
three server-verified evidence branches, what each platform gate is, what the database and the
vendor ledgers each decide, and what the schema deliberately does not store.

The mechanics it composes belong to their owners and are not restated here: the native
read-write-activate sequence and the two-ledger model are
`05-proof-adapters-and-derived-identifiers.md`'s (`proof_adapters`), the closed `providerData`
classifier and the derived `idp_account_hash` are the identity and derivation modules', the
grant-and-usage ownership model is `07-quota-and-access-enforcement.md`'s (`quota.grants`,
`quota.usage`), and the row shapes and their per-source CHECKs are `06-schema-reference.md`'s
(`schema_invariants`).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from nativespeaker.api.auth.audit import AttemptPhase, AuthEvent, AuthEventResult, terminal_event
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import ChallengeRow, ChallengeState, ClaimOutcome
from nativespeaker.api.auth.derived_identifiers import (
    UNIQUENESS_ANCHOR,
    DerivedValue,
    IdpAccountAliasIndex,
    WebGateAccount,
    assert_uniqueness_anchor,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import (
    REGISTERED_PROVIDERS,
    ExternalIdentityRow,
    IdentityError,
    IdentityState,
    NativeClaimPlatform,
    free_grant_available,
    mark_free_grant_consumed,
    pin_native_claim_platform,
)
from nativespeaker.api.auth.integration import FirebaseIntegrations
from nativespeaker.api.auth.invariants import (
    DEVICE_CHECK_MECHANISM,
    DevicePlatform,
    GateAlreadyConsumedError,
    GateConsumptionKind,
    ProofUse,
    ProviderAccount,
    ProviderAccountGates,
    assert_device_check_proof_use,
    assert_grant_columns_entitlement_only,
    assert_same_transaction,
)
from nativespeaker.api.auth.locks import LockLedger, lock_grant_set
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_adapters import (
    CLAIM_EXECUTION_CONTEXT,
    NATIVE_CLAIM_PROVIDER,
    ClaimRejection,
    DeviceGrantExhausted,
    DeviceStateAdapter,
    ExecutionContext,
    NativeClaimLedger,
    NativeClaimStep,
    ProofRejected,
    anonymous_device_grant_row,
    assert_execution_context,
    assert_same_device_race_bounded,
    claim_challenge_before_vendor,
    devicecheck_bit_for,
    untrusted_vendor_material,
)
from nativespeaker.api.auth.proof_endpoints import (
    ClaimBranch,
    GateDenied,
    ProofArtifact,
    web_anonymous_grant_gate,
    web_gate_admin_client,
)
from nativespeaker.api.auth.proof_material import assert_anti_abuse_row_prohibitions
from nativespeaker.api.auth.schema_invariants import (
    anti_abuse_evidence,
    assert_anti_abuse_pairing,
    assert_native_claim_written_before_grant,
    assert_no_raw_device_material,
)
from nativespeaker.api.auth.taxonomy import ProviderDataReadPoint
from nativespeaker.api.exceptions import ErrorCode, ServiceError
from nativespeaker.api.quota.grants import assert_billing_separation
from nativespeaker.api.quota.usage import NewUsageRow, new_usage_row
from nativespeaker.api.ratelimit.ordering import (
    ANONYMOUS_GRANT_ADMISSION,
    DeviceBitWrite,
    assert_grant_row_permitted,
)


class FreeGrantError(RuntimeError):
    """A free-credit grant rule was about to be broken."""


class FreeGrantRejected(ServiceError):
    """A free-credit claim rejected on a grants-domain rule. It carries the specific internal
    `core.auth_event_result` for the audit row and the shared client-visible class for the
    response; the taxonomy owns the mapping and this exception invents neither side."""

    audit: AuthEvent | None = None

    def __init__(self, result: AuthEventResult, error_code: ErrorCode, message: str,
                 *, status_code: int = 403, details: Mapping[str, Any] | None = None):
        self.result = result
        self.error_code: ErrorCode = error_code
        self.status_code = status_code
        # The audit details this rejection carries onto its single `audit.auth_events` row.
        self.audit_details: dict[str, Any] | None = dict(details) if details is not None else None
        super().__init__(message)


class BranchShapeError(FreeGrantRejected):
    """The request resolved to zero branches, to more than one, or to a partial evidence set. It
    is a request-shape validation error, not a vendor-material failure: it audits as
    `proof_malformed` with the shape cause in audit detail and surfaces as `proof_rejected`."""

    def __init__(self, cause: str):
        self.cause = cause
        super().__init__(AuthEventResult.proof_malformed, "proof_rejected",
                         f"the claim request resolved to no single evidence set: {cause}")

    def audit_detail(self) -> dict[str, dict[str, str]]:
        """The shape cause travels in `details`, never in the client-visible class."""
        return {"failure": {"stage": "branch_selection", "shape_cause": self.cause}}


# --- Access grants own monthly usage state -------------------------------------------------------

# The grant-and-usage ownership model this file consumes and never restates. Free-credit grants are
# ordinary `core.access_grants` rows under it: the same per-grant `core.user_monthly_usage` row and
# the same one-active-grant bound as every other source.
# [impl->req~grants-usage-state-owned-by-quota-spec~1]
USAGE_STATE_OWNER: str = "07-quota-and-access-enforcement.md"
USAGE_STATE_FACTS: tuple[str, ...] = (
    "core.access_grants is the single entitlement table",
    "core.user_monthly_usage is per-grant state, not per-user state",
    "core.access_tiers carries the configured monthly credit amount",
    "one effective grant per user, with no precedence ranking",
    "what restore may and may not move",
)


def free_grant_usage_row(grant_id: UUID,
                         *,
                         transaction: object,
                         now: datetime | None = None,
                         carried: tuple[str, int] | None = None) -> NewUsageRow:
    """The usage row a free-credit grant carries, created by the one creation point every grant
    source shares and keyed by the grant rather than by the user."""
    # [impl->req~grants-usage-state-owned-by-quota-spec~1]
    return new_usage_row(grant_id, now=now, carried=carried,
                         grant_transaction=transaction, usage_transaction=transaction)


# --- The two free-credit grant operations --------------------------------------------------------

# Free credits are granted only through these two operations, one per free-credit source.
# [impl->req~grants-only-two-grant-operations~1]
FREE_GRANT_OPERATIONS: dict[AccessGrantSource, AuthOperation] = {
    AccessGrantSource.anonymous_device_grant: AuthOperation.claim_anonymous_grant,
    AccessGrantSource.registered_account_grant: AuthOperation.claim_registered_grant,
}
FREE_GRANT_SOURCES: frozenset[AccessGrantSource] = frozenset(FREE_GRANT_OPERATIONS)

# Every other operation in the inventory: account creation, `/auth/sync`, restore, the in-place
# upgrade and sign-out-all allocate no free credit.
# [impl->req~grants-never-allocated-at-creation-or-sync~1]
NON_ALLOCATING_FLOWS: frozenset[AuthOperation] = frozenset(
    set(AuthOperation) - set(FREE_GRANT_OPERATIONS.values()))


def free_grant_operation(source: AccessGrantSource) -> AuthOperation:
    """The one operation allowed to create a grant of this free-credit source."""
    # [impl->req~grants-only-two-grant-operations~1]
    operation = FREE_GRANT_OPERATIONS.get(source)
    if operation is None:
        raise FreeGrantError(f"{source} is no free-credit grant source")
    return operation


def assert_free_credit_source_operation(operation: AuthOperation,
                                        source: AccessGrantSource) -> None:
    """Fail closed on any pairing outside the two: no third operation grants free credit, and
    neither claim creates the other's source."""
    # [impl->req~grants-only-two-grant-operations~1]
    if operation not in set(FREE_GRANT_OPERATIONS.values()):
        raise FreeGrantError(f"{operation} grants no free credit")
    if free_grant_operation(source) is not operation:
        raise FreeGrantError(f"{operation} does not create a {source} grant")


def assert_no_free_credit_allocation(operation: AuthOperation) -> None:
    """Free credits are never allocated during account creation, and never during `/auth/sync`,
    restore, upgrade, or any other completion flow."""
    # [impl->req~grants-never-allocated-at-creation-or-sync~1]
    if operation in NON_ALLOCATING_FLOWS:
        raise FreeGrantError(f"{operation} never allocates a free-credit grant")


# --- `claim_anonymous_grant`: branches, identities and the one source ------------------------------

NATIVE_BRANCHES: frozenset[ClaimBranch] = frozenset({ClaimBranch.native_ios,
                                                     ClaimBranch.native_android})

# The vendor gate each branch runs, and the platform each maps onto.
# [impl->req~grants-claim-anonymous-operation~1]
BRANCH_VENDOR_GATE: dict[ClaimBranch, str] = {
    ClaimBranch.native_ios: "apple_devicecheck",
    ClaimBranch.native_android: "play_integrity_with_device_recall",
    ClaimBranch.web: "firebase_provider_data_plus_cloudflare_bot_check",
}
BRANCH_PLATFORM: dict[ClaimBranch, DevicePlatform] = {
    ClaimBranch.native_ios: DevicePlatform.ios,
    ClaimBranch.native_android: DevicePlatform.android,
    ClaimBranch.web: DevicePlatform.web,
}


# What `claim_anonymous_grant` is for, per branch: an explicit free-credit claim of the one
# anonymous source, for a linked anonymous user on native gated by durable device state, or for a
# linked `google`/`apple` user on web gated by the complete closed-classifier-and-stored-binding
# `providerData` check plus the bot-check gate.
# [impl->req~grants-anon-logic-purpose~1]
ANONYMOUS_CLAIM_GATING: dict[ClaimBranch, tuple[str, ...]] = {
    ClaimBranch.native_ios: ("durable_device_state",),
    ClaimBranch.native_android: ("durable_device_state",),
    ClaimBranch.web: ("closed_classifier_and_stored_binding_provider_data", "bot_check_gate"),
}


def anonymous_claim_source(branch: ClaimBranch) -> AccessGrantSource:
    """Every branch of `claim_anonymous_grant` produces one `core.access_grants` row with
    `source = 'anonymous_device_grant'` — the shared free-tier bucket, counted as the account's
    one free entitlement whichever branch issued it.

    That is the whole purpose of the operation: an explicit free-credit grant claim of this one
    source, gated on native by the durable per-device state and on web by the complete
    closed-classifier-and-stored-binding `providerData` check plus the bot-check gate.
    """
    # [impl->req~grants-claim-anonymous-operation~1]
    # [impl->req~grants-anon-logic-purpose~1]
    if branch not in BRANCH_VENDOR_GATE:
        raise FreeGrantError(f"{branch} is no claim_anonymous_grant branch")
    if branch not in ANONYMOUS_CLAIM_GATING:
        raise FreeGrantError(f"{branch} names no anonymous-claim gate")
    return AccessGrantSource.anonymous_device_grant


def anonymous_claim_gating(branch: ClaimBranch) -> tuple[str, ...]:
    """What gates this branch's claim of the one anonymous source: durable device state on the
    native platforms, and the complete `providerData` stored-binding check plus the bot-check gate
    on web. `registered_at` gates nothing anywhere."""
    # [impl->req~grants-anon-logic-purpose~1]
    gating = ANONYMOUS_CLAIM_GATING.get(branch)
    if gating is None:
        raise FreeGrantError(f"{branch} names no anonymous-claim gate")
    return gating


def assert_claimant_eligible(branch: ClaimBranch, row: ExternalIdentityRow) -> IdentityProvider:
    """Who may claim on this branch: on the native device-checked paths an active anonymous
    identity, or an active registered identity whose stored provider is `google` or `apple`,
    burning the device-ledger bit exactly as an anonymous claimant would; on web an active
    registered identity whose stored provider is `google` or `apple`."""
    # [impl->req~grants-claim-anonymous-operation~1]
    # A non-`active` row is a historical identity, audited under its own barrier result and
    # surfaced through the shared `account_unavailable` class.
    # [impl->req~shared-audit-outcome-barrier-rejection~1]
    if row.identity_state is not IdentityState.active:
        raise FreeGrantRejected(AuthEventResult.historical_identity, "account_unavailable",
                                "a free-credit claim needs an active identity")
    if row.provider in REGISTERED_PROVIDERS:
        return row.provider
    if branch in NATIVE_BRANCHES and row.provider is IdentityProvider.anonymous:
        return row.provider
    raise FreeGrantRejected(AuthEventResult.policy_rejected, "verification_required",
                            f"{branch} requires a google or apple stored provider")


# --- `claim_registered_grant`, as this section states it -------------------------------------------

# Registered identity providers keep existing for these purposes. None of them is a free-credit
# path: a linked Google or Apple identity by itself creates no free credit.
# [impl->req~grants-registered-identity-not-a-free-path~1]
REGISTERED_IDENTITY_PURPOSES: tuple[str, ...] = ("account_login", "user_creation",
                                                 "anonymous_to_registered_upgrade",
                                                 "subscription_flows")


@dataclass(frozen=True, slots=True)
class RegisteredClaimPlan:
    """What a `claim_registered_grant` call would write."""
    source: AccessGrantSource
    gate_kind: GateConsumptionKind
    supersedes_anonymous_grant: bool


def registered_claim_plan(row: ExternalIdentityRow,
                          *,
                          active_grant_source: AccessGrantSource | None,
                          provider_data_confirmed: bool) -> RegisteredClaimPlan:
    """`claim_registered_grant` is for an active linked user whose current external identity row
    has stored provider `google` or `apple` and a stored `provider_uid`. It produces a
    `core.access_grants` row with `source = 'registered_account_grant'`, superseding the user's
    active anonymous grant where one exists, gated by that stored provider classification, the
    account's own grant history and the registered-account-grant gate-consumption domain. Every
    call performs the mandatory fail-closed Firebase Admin `providerData` confirmation of the
    stored binding, the idempotent repeat included."""
    # [impl->req~grants-claim-registered-operation~1]
    if row.identity_state is not IdentityState.active:
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "operation_not_allowed",
                                "the registered claim needs an active linked identity")
    if row.provider not in REGISTERED_PROVIDERS or not row.provider_uid:
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                "the registered claim needs a stored google or apple binding")
    if not provider_data_confirmed:
        raise FreeGrantError(
            "every claim_registered_grant call confirms the stored binding against Firebase "
            "Admin providerData, the idempotent repeat included")
    if (active_grant_source is not None
            and active_grant_source is not AccessGrantSource.anonymous_device_grant):
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "operation_not_allowed",
                                f"an active {active_grant_source} grant is not convertible")
    return RegisteredClaimPlan(
        source=AccessGrantSource.registered_account_grant,
        gate_kind=GateConsumptionKind.registered_account_grant,
        supersedes_anonymous_grant=(
            active_grant_source is AccessGrantSource.anonymous_device_grant))


def registered_identity_is_not_a_free_path(row: ExternalIdentityRow,
                                           *,
                                           anti_abuse_evidence_present: bool) -> None:
    """Registered identity alone does not create a free-credit path: the claim additionally
    requires the current linked row's stored provider to be `google` or `apple` and the
    registered-grant anti-abuse evidence the registered-account-grant rules require."""
    # [impl->req~grants-registered-identity-not-a-free-path~1]
    if "free_credit_grant" in REGISTERED_IDENTITY_PURPOSES:
        raise FreeGrantError("registered identity is not itself a free-credit path")
    if row.provider not in REGISTERED_PROVIDERS:
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                "the registered claim needs a google or apple stored provider")
    if not anti_abuse_evidence_present:
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                "the registered claim needs its own anti-abuse evidence")


# The inputs the account-level registered decision reads, and the fields it never reads.
# [impl->req~grants-registered-eligibility-inputs~1]
REGISTERED_ELIGIBILITY_INPUTS: tuple[str, ...] = ("stored_provider", "stored_provider_uid",
                                                  "user_grant_history",
                                                  "registered_account_grant_gate")
NEVER_CONSULTED_FOR_ELIGIBILITY: frozenset[str] = frozenset({
    "registered_at", "email", "display_name", "user_agent",
    "client_supplied_provider_account_id", "device_check_state",
})


def registered_eligibility_inputs(row: ExternalIdentityRow,
                                  *,
                                  provider_data_confirmed: bool,
                                  consulted: Sequence[str] = (),
                                  read_point: ProviderDataReadPoint =
                                  ProviderDataReadPoint.claim_registered_grant_completion
                                  ) -> tuple[IdentityProvider, str]:
    """The stored provider is the sole anonymous-versus-registered classifier; `registered_at` is
    reporting data and is never consulted for grant eligibility. The alias hash is computed from
    the stored `provider_uid`, the mandatory fail-closed Firebase Admin `providerData`
    confirmation runs on every call at this operation's own read point out of the closed set of
    five, a row with no `provider_uid` rejects as `idp_account_not_eligible`, and no
    client-supplied provider account identifier is ever trusted for the decision."""
    # [impl->req~grants-registered-eligibility-inputs~1]
    offending = sorted(set(consulted) & NEVER_CONSULTED_FOR_ELIGIBILITY)
    if offending:
        raise FreeGrantError(f"{offending} is never consulted for free-grant eligibility")
    if len(set(ProviderDataReadPoint)) != 5:
        raise FreeGrantError("the providerData read points are a closed set of five")
    if read_point is not ProviderDataReadPoint.claim_registered_grant_completion:
        raise FreeGrantError(f"{read_point} is not the registered claim's own read point")
    if row.provider not in REGISTERED_PROVIDERS or not row.provider_uid:
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                "the identity row stores no google or apple provider_uid")
    if not provider_data_confirmed:
        raise FreeGrantRejected(AuthEventResult.idp_account_not_eligible, "verification_required",
                                "the stored binding was not confirmed against providerData")
    return row.provider, row.provider_uid


# The durable registered-claim rejections. After one of them there is no further free-credit path
# for that user state, and the duplicate block is final for that provider account.
# [impl->req~grants-registered-rejection-final~1]
DURABLE_REGISTERED_REJECTIONS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.idp_account_not_eligible,
    AuthEventResult.idp_account_already_claimed,
    AuthEventResult.policy_rejected,
})


def further_free_credit_path(result: AuthEventResult) -> AuthOperation | None:
    """The next free-credit path available after a `claim_registered_grant` outcome: `None` once
    the rejection was durable."""
    # [impl->req~grants-registered-rejection-final~1]
    if result in DURABLE_REGISTERED_REJECTIONS:
        return None
    if result is AuthEventResult.succeeded:
        return None
    return AuthOperation.claim_registered_grant


def registered_account_blocked(gates: ProviderAccountGates,
                               account: ProviderAccount) -> bool:
    """Whether the registered-account-grant gate is already consumed for this Google or Apple
    provider account. The block is keyed by that provider account alone, so it holds across every
    Firebase user, external identity, internal user, reinstall and device."""
    # [impl->req~grants-registered-rejection-final~1]
    return gates.consumed_grant(account,
                                GateConsumptionKind.registered_account_grant) is not None


# --- The per-device grant states and their exhaustion ----------------------------------------------


class DeviceGrantState(StrEnum):
    """The two grant states the per-device device-check record carries."""
    anonymous_claimed = "anonymous_claimed"
    registered_claimed = "registered_claimed"


# Two states per device where the platform supports durable device state — the two Apple
# DeviceCheck bits on iOS, the two Play Integrity Device Recall states on Android. Web has none.
# [impl->req~grants-two-per-device-grant-states~1]
PER_DEVICE_GRANT_STATES: tuple[DeviceGrantState, ...] = tuple(DeviceGrantState)
DURABLE_DEVICE_STATE_PLATFORMS: frozenset[DevicePlatform] = frozenset({DevicePlatform.ios,
                                                                       DevicePlatform.android})
WEB_HAS_DURABLE_DEVICE_STATE: bool = False

# What the states survive, to the extent the vendor guarantees it.
# [impl->req~grants-per-device-states-persist~1]
PERSISTS_ACROSS: tuple[str, ...] = ("app_reinstall", "device_reset")
STATE_CLEARERS: frozenset[str] = frozenset()

# The client copy an exhausted device gets. It states the fact and accuses nobody.
# [impl->req~grants-two-per-device-grant-states~1]
DEVICE_GRANT_EXHAUSTED_COPY: str = ("The free credits for this device have already been used. "
                                   "You can continue with a Google or Apple account.")
ACCUSATORY_TERMS: frozenset[str] = frozenset({"abuse", "abusive", "cheat", "cheating", "fraud",
                                              "fraudulent", "banned", "violation", "suspicious"})


def device_states_for(platform: DevicePlatform) -> tuple[DeviceGrantState, ...]:
    """The per-device grant states this platform carries: both on iOS and Android, none on web,
    whose per-provider-account limit is enforced by the web anonymous-grant gate instead."""
    # [impl->req~grants-two-per-device-grant-states~1]
    if platform in DURABLE_DEVICE_STATE_PLATFORMS:
        return PER_DEVICE_GRANT_STATES
    if WEB_HAS_DURABLE_DEVICE_STATE:
        raise FreeGrantError("web has no durable device-check state")
    return ()


def non_accusatory_copy() -> str:
    """The `device_grant_exhausted` copy, checked against the words it must not use."""
    # [impl->req~grants-two-per-device-grant-states~1]
    words = set(DEVICE_GRANT_EXHAUSTED_COPY.lower().replace(".", " ").replace(",", " ").split())
    offending = sorted(words & ACCUSATORY_TERMS)
    if offending:
        raise FreeGrantError(f"{offending} is accusatory copy")
    return DEVICE_GRANT_EXHAUSTED_COPY


def device_grant_exhausted(*,
                           anonymous_claimed: bool = False,
                           registered_claimed: bool = False,
                           web_gate_consumed: bool = False) -> None:
    """Both per-device states set, the anonymous-claimed state set on its own, or a web provider
    account that already consumed the web gate: further free-grant attempts for that device or
    account return `device_grant_exhausted` with non-accusatory copy. The two causes keep their
    own internal results — the per-device block and the web gate conflict are different
    mechanisms — and surface as the one client-visible class."""
    # [impl->req~grants-two-per-device-grant-states~1]
    # [impl->req~grants-anonymous-exhausted-registered-backstop~1]
    # [impl->req~grants-anon-rule-already-consumed-rejects~1]
    if anonymous_claimed or (registered_claimed and anonymous_claimed):
        raise DeviceGrantExhausted(non_accusatory_copy())
    if web_gate_consumed:
        raise ClaimRejection(AuthEventResult.anti_abuse_already_claimed, non_accusatory_copy())


def registered_backstop(row: ExternalIdentityRow,
                        *,
                        active_grant_source: AccessGrantSource | None,
                        anonymous_gate_exhausted: bool = True) -> AuthOperation:
    """The registered account grant is the platform-independent backstop when the anonymous
    device state or the web provider-account gate is exhausted, and when the platform has no
    supported anonymous platform gate at all. It requires a Google or Apple linked identity and
    no active grant other than a convertible anonymous device grant, stays subject to the
    registered-grant gates, and is not guaranteed to succeed: it has its own gates, so naming it as
    the alternate path is not a promise that it will issue a grant."""
    # [impl->req~grants-anonymous-exhausted-registered-backstop~1]
    # [impl->req~grants-anon-alt-not-guaranteed~1]
    if not anonymous_gate_exhausted:
        raise FreeGrantError("the backstop applies once the anonymous gate is closed")
    if row.provider not in REGISTERED_PROVIDERS:
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "verification_required",
                                "the backstop requires a google or apple linked identity")
    if (active_grant_source is not None
            and active_grant_source is not AccessGrantSource.anonymous_device_grant):
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "operation_not_allowed",
                                f"an active {active_grant_source} grant blocks the backstop")
    return AuthOperation.claim_registered_grant


def assert_device_states_persist(*, cleared_by: Sequence[str] = (),
                                 extra_grants_from_race: int = 0) -> None:
    """The two per-device states persist across app reinstall and device reset to the extent
    Apple DeviceCheck or Play Integrity Device Recall supports. Each state enforces its
    one-slot-per-physical-device bound subject to the accepted narrow concurrent same-device
    race, bounded to one extra grant and further bounded by per-user uniqueness and the
    create-user per-IP and deployment-wide limits."""
    # [impl->req~grants-per-device-states-persist~1]
    offending = sorted(set(cleared_by) & set(PERSISTS_ACROSS))
    if offending or STATE_CLEARERS:
        raise FreeGrantError(f"a claimed per-device state survives {offending or PERSISTS_ACROSS}")
    assert_same_device_race_bounded(extra_grants_from_race)


# The database-side bounds behind the same rule: at most one committed grant per user per
# free-grant source for the user's lifetime, and at most one active grant per user. Web's
# analogous product limit is at most one anonymous web gate per provider account.
# [impl->req~grants-per-device-states-persist~1]
MAX_COMMITTED_FREE_GRANTS_PER_USER_SOURCE: int = 1
MAX_ACTIVE_GRANTS_PER_USER: int = 1
MAX_WEB_GATES_PER_PROVIDER_ACCOUNT: int = 1


def assert_database_bounds(*,
                           committed_free_sources: Sequence[AccessGrantSource],
                           active_grants: int) -> None:
    """The two bounds the database enforces on committed data, independently of any device."""
    # [impl->req~grants-per-device-states-persist~1]
    for source in FREE_GRANT_SOURCES:
        if list(committed_free_sources).count(source) > MAX_COMMITTED_FREE_GRANTS_PER_USER_SOURCE:
            raise FreeGrantError(f"one committed {source} grant per user for the user's lifetime")
    if active_grants > MAX_ACTIVE_GRANTS_PER_USER:
        raise FreeGrantError("at most one active grant per user")


# --- The three platform gates ---------------------------------------------------------------------

# There is no degraded verification mode: a successful anonymous device grant satisfies the whole
# gate for the request it came from.
# [impl->req~grants-no-degraded-verification-mode~1]
DEGRADED_VERIFICATION_MODES: frozenset[str] = frozenset()

# Each branch's gate, step by step, in the one order it runs in.
# [impl->req~grants-platform-gate-ios~1]
IOS_GATE: tuple[str, ...] = ("verify_devicecheck_proof", "read_anonymous_claimed_bit",
                             "database_per_user_eligibility", "write_bit_and_await_apple_confirmation",
                             "activate_grant")
# [impl->req~grants-platform-gate-android~1]
ANDROID_GATE: tuple[str, ...] = ("verify_play_integrity", "read_device_recall_anonymous_claimed",
                                 "database_per_user_eligibility",
                                 "write_recall_state_and_await_google_confirmation",
                                 "activate_grant")
# [impl->req~grants-platform-gate-web~1]
WEB_GATE: tuple[str, ...] = ("stored_provider_is_google_or_apple",
                             "issuer_selected_firebase_admin_provider_data",
                             "closed_classifier_over_complete_result",
                             "stored_provider_and_provider_uid_equality",
                             "derive_idp_account_hash_with_stored_provider",
                             "server_validated_cloudflare_bot_check",
                             "activate_grant")
PLATFORM_GATE: dict[ClaimBranch, tuple[str, ...]] = {
    ClaimBranch.native_ios: IOS_GATE,
    ClaimBranch.native_android: ANDROID_GATE,
    ClaimBranch.web: WEB_GATE,
}


def platform_gate(branch: ClaimBranch) -> tuple[str, ...]:
    """The gate the request's branch must satisfy. There is no relaxed variant of any of them."""
    # [impl->req~grants-no-degraded-verification-mode~1]
    if DEGRADED_VERIFICATION_MODES:
        raise FreeGrantError("anonymous device grants have no degraded verification mode")
    gate = PLATFORM_GATE.get(branch)
    if gate is None:
        raise FreeGrantError(f"{branch} has no platform gate")
    return gate


def ios_gate_bits() -> tuple[str, str]:
    """The two Apple DeviceCheck bits for the same physical device: the anonymous-claimed bit the
    anonymous claim reads and writes, and the bit that records the registered-claimed state."""
    # [impl->req~grants-platform-gate-ios~1]
    anonymous = devicecheck_bit_for(AuthOperation.claim_anonymous_grant)
    registered = devicecheck_bit_for(AuthOperation.claim_registered_grant)
    if anonymous is registered:
        raise FreeGrantError("the two claim states are two distinct DeviceCheck bits")
    return str(anonymous), str(registered)


def android_gate(*, device_recall_available: bool) -> tuple[str, ...] | AuthOperation:
    """Android has the anonymous gate wherever Play Integrity Device Recall is available. Without
    Device Recall there is no anonymous device-check path at all and the claim falls back to
    forced registration — the registered account grant, gated by the registered-account rules and
    by account cost rather than by any Android device state."""
    # [impl->req~grants-platform-gate-android~1]
    # [impl->req~grants-android-device-recall-availability~1]
    if not device_recall_available:
        return AuthOperation.claim_registered_grant
    return ANDROID_GATE


def android_anonymous_path_available(*, device_recall_available: bool) -> bool:
    """Whether this Android client has an anonymous device-check path at all. Where Device Recall
    is available there is no Android-platform pre-rejection: the claim runs its gate like any
    other."""
    # [impl->req~grants-android-device-recall-availability~1]
    # [impl->req~grants-anon-entry-no-app-attest~1]
    return device_recall_available


def web_hash_provider_component(row: ExternalIdentityRow,
                                account: WebGateAccount) -> IdentityProvider:
    """The HMAC provider component of the web gate's `idp_account_hash` is the stored provider,
    and the classified provider must equal it."""
    # [impl->req~grants-platform-gate-web~1]
    if account.provider is not row.provider:
        raise GateDenied("the classified provider must equal the stored provider")
    return row.provider


def assert_no_gate_bypass(branch: ClaimBranch,
                          *,
                          completed: Sequence[str],
                          write: DeviceBitWrite | None = None) -> None:
    """The backend must not issue or activate an anonymous device grant by omitting,
    substituting, relaxing or bypassing the applicable platform gate — including by activating a
    native grant before the vendor confirms the bit write."""
    # [impl->req~grants-no-gate-bypass~1]
    required = platform_gate(branch)
    done = list(completed)
    missing = [step for step in required if step not in done]
    substituted = [step for step in done if step not in required]
    if missing or substituted:
        raise FreeGrantError(
            f"{branch} gate not satisfied: missing {missing}, substituted {substituted}")
    if branch in NATIVE_BRANCHES:
        # Only the vendor's confirmation of this attempt's own write permits activation.
        assert_grant_row_permitted(write)


# --- What the two ledgers each decide -------------------------------------------------------------


def native_eligible(*, vendor_bit_set: bool, database_eligible: bool) -> bool:
    """Native anonymous eligibility requires both ledgers to be eligible: the relevant per-device
    vendor bit unset, and the database showing the user eligible under per-user grant history.
    The applicable bit is vendor-confirmed written before activation."""
    # [impl->req~grants-native-eligibility-both-ledgers~1]
    return (not vendor_bit_set) and database_eligible


def web_eligible(*,
                 stored_provider: IdentityProvider,
                 classifier_passed: bool,
                 provider_uid_matched: bool,
                 bot_check_passed: bool,
                 persisted_device_state: Sequence[str] = ()) -> bool:
    """On web the stored provider must be `google` or `apple`, the complete live `providerData`
    result must pass the closed classifier and match the stored provider and stored
    `provider_uid`, and the server-validated Cloudflare bot check must pass. Web persists no
    device-check state; its per-provider-account uniqueness comes from the web anonymous-grant
    gate instead."""
    # [impl->req~grants-native-eligibility-both-ledgers~1]
    if persisted_device_state:
        raise FreeGrantError("web persists no device-check state")
    return (stored_provider in REGISTERED_PROVIDERS
            and classifier_passed and provider_uid_matched and bot_check_passed)


# --- The device-check signal is anti-abuse state only ----------------------------------------------

# The three device-check signals, and what none of them ever recovers.
# [impl->req~grants-device-check-not-identity~1]
DEVICE_CHECK_SIGNALS: tuple[str, ...] = (DEVICE_CHECK_MECHANISM[DevicePlatform.ios],
                                         DEVICE_CHECK_MECHANISM[DevicePlatform.android],
                                         DEVICE_CHECK_MECHANISM[DevicePlatform.web])
DEVICE_CHECK_RECOVERS: frozenset[str] = frozenset()
RECOVERABLE_BY_DEVICE_CHECK: frozenset[str] = frozenset({"chats", "identities", "subscriptions",
                                                         "access_grants", "account_data"})


def assert_device_check_is_anti_abuse_only(use: ProofUse,
                                           *,
                                           recovers: Sequence[str] = (),
                                           resolves_account: object = None) -> ProofUse:
    """The device-check signal is anti-abuse state and nothing else: not an identity, ownership,
    recovery or upgrade credential, never the thing that resolves which account a request belongs
    to, and never used to recover chats, identities, subscriptions, access grants or any other
    account data. DeviceCheck, Play Integrity Device Recall and Cloudflare bot checks are alike
    in this."""
    # [impl->req~grants-device-check-not-identity~1]
    assert_device_check_proof_use(use)
    if resolves_account is not None:
        raise FreeGrantError("a device-check signal resolves no account")
    offending = sorted(set(recovers) & RECOVERABLE_BY_DEVICE_CHECK)
    if offending or DEVICE_CHECK_RECOVERS:
        raise FreeGrantError(f"a device-check signal never recovers {offending}")
    return use


# --- Vendor state is never client-supplied ---------------------------------------------------------

# Facts a client might offer as already-verified vendor state. None of them is trusted.
# [impl->req~grants-vendor-state-never-client-supplied~1]
CLIENT_SUPPLIED_VENDOR_FACTS: frozenset[str] = frozenset({
    "device_check_state", "devicecheck_bits", "bit0", "bit1", "recall_state", "device_labels",
    "verdict_summary", "already_verified", "bot_check_passed", "provider_data",
    "signed_in_with_google", "signed_in_with_apple", "turnstile_verified",
})

# What each branch must carry up front for the writes and validations it will make.
# [impl->req~grants-vendor-state-never-client-supplied~1]
REQUIRED_BRANCH_MATERIAL: dict[ClaimBranch, tuple[ProofArtifact, ...]] = {
    ClaimBranch.native_ios: (ProofArtifact.devicecheck_query_token,
                             ProofArtifact.devicecheck_update_token),
    ClaimBranch.native_android: (ProofArtifact.play_integrity_verdict,),
    ClaimBranch.web: (ProofArtifact.turnstile_token,),
}


def assert_vendor_state_not_client_supplied(body: Mapping[str, Any]) -> Mapping[str, Any]:
    """Client-supplied device-check proof tokens and Cloudflare bot-check evidence are untrusted
    request-body inputs used only to query or validate with the provider. No client-asserted
    vendor state is accepted as already-verified state, and the web Google or Apple sign-in half
    is never established from request-body evidence: it is read from Firebase Admin
    `providerData` with backend-held credentials."""
    # [impl->req~grants-vendor-state-never-client-supplied~1]
    untrusted_vendor_material(body)
    offending = sorted(set(body) & CLIENT_SUPPLIED_VENDOR_FACTS)
    if offending:
        raise ProofRejected(f"{offending} is never accepted as verified vendor state")
    return body


def assert_write_material_present(branch: ClaimBranch, carried: Sequence[ProofArtifact]) -> None:
    """A claim that must write a bit carries all its required vendor material up front: iOS two
    separate per-transaction DeviceCheck tokens, Android one Play Integrity token whose
    transaction covers the recall read and write. Withheld or invalid write material refuses the
    claim before a grant exists."""
    # [impl->req~grants-vendor-state-never-client-supplied~1]
    required = REQUIRED_BRANCH_MATERIAL.get(branch)
    if required is None:
        raise FreeGrantError(f"{branch} is no claim branch")
    missing = [artifact for artifact in required if artifact not in set(carried)]
    if missing:
        raise ProofRejected(f"{branch} withheld {[str(name) for name in missing]}")


def assert_no_raw_vendor_material_stored(columns: Iterable[str]) -> None:
    """No raw DeviceCheck token, raw Play Integrity token, Cloudflare bot-check token, synthetic
    stable provider device principal hash or device-check-state hash is stored in PostgreSQL."""
    # [impl->req~grants-vendor-state-never-client-supplied~1]
    assert_no_raw_device_material(columns)
    assert_no_raw_attestation_tokens(columns)
    assert_no_raw_cloudflare_tokens(columns)


# --- What the schema does and does not store ------------------------------------------------------

# The seven families PostgreSQL does not store.
# [impl->req~grants-postgres-does-not-store~1]
POSTGRES_NEVER_STORES: tuple[str, ...] = ("raw_device_ids", "installation_ids",
                                          "general_device_records",
                                          "raw_devicecheck_or_play_integrity_tokens",
                                          "raw_cloudflare_bot_check_tokens",
                                          "raw_provider_account_identifiers_outside_the_registry",
                                          "anonymous_free_grant_claim_finalization_table")

# [impl->req~grants-no-raw-device-ids~1]
RAW_DEVICE_ID_COLUMNS: frozenset[str] = frozenset({
    "device_id", "device_identifier", "device_uuid", "vendor_identifier", "idfv", "idfa",
    "android_id", "hardware_id", "gsf_id",
})
# [impl->req~grants-no-installation-ids~1]
INSTALLATION_ID_COLUMNS: frozenset[str] = frozenset({
    "installation_id", "install_id", "firebase_installation_id", "app_instance_id", "fid",
})
# There is no device table and no device-record table of any shape.
# [impl->req~grants-no-general-device-records~1]
DEVICE_RECORD_TABLES: frozenset[str] = frozenset()
FORBIDDEN_DEVICE_TABLE_NAMES: frozenset[str] = frozenset({
    "core.devices", "core.device_records", "core.user_devices", "core.installations",
    "core.device_check_states",
})
# [impl->req~grants-no-raw-attestation-tokens~1]
RAW_ATTESTATION_TOKEN_COLUMNS: frozenset[str] = frozenset({
    "devicecheck_token", "device_check_token", "devicecheck_query_token",
    "devicecheck_update_token", "play_integrity_token", "integrity_token", "attestation_token",
    "attestation_blob",
})
# [impl->req~grants-no-raw-cloudflare-tokens~1]
RAW_CLOUDFLARE_TOKEN_COLUMNS: frozenset[str] = frozenset({
    "turnstile_token", "bot_check_token", "cf_turnstile_response", "cloudflare_token",
    "turnstile_response",
})
# The only two places a raw Google or Apple provider account identifier lives.
# [impl->req~grants-no-raw-provider-ids-outside-registry~1]
RAW_PROVIDER_ACCOUNT_TABLES: frozenset[str] = frozenset({"core.external_identities",
                                                         "core.provider_accounts"})
# Device principals and device-check-state hashes: a synthetic stand-in for a device record, and
# forbidden everywhere the same way a raw device ID is.
# [impl->req~grants-no-general-device-records~1]
DEVICE_PRINCIPAL_COLUMNS: frozenset[str] = frozenset({
    "device_principal", "device_principal_hash", "stable_device_principal_hash",
    "provider_device_principal_hash", "device_check_state", "device_check_hash",
    "device_check_state_hash", "device_recall_token",
})
# There is no separate anonymous free-grant claim-finalization table.
# [impl->req~grants-no-claim-finalization-table~1]
CLAIM_FINALIZATION_TABLES: frozenset[str] = frozenset()
FORBIDDEN_CLAIM_FINALIZATION_NAMES: frozenset[str] = frozenset({
    "core.anonymous_grant_claims", "core.free_grant_claims", "core.grant_claim_finalizations",
    "core.claim_finalizations",
})


def assert_no_raw_device_ids(columns: Iterable[str]) -> None:
    """PostgreSQL stores no raw device IDs."""
    # [impl->req~grants-no-raw-device-ids~1]
    offending = sorted({name for name in columns if name.lower() in RAW_DEVICE_ID_COLUMNS})
    if offending:
        raise FreeGrantError(f"{offending} would store a raw device ID")


def assert_no_installation_ids(columns: Iterable[str]) -> None:
    """PostgreSQL stores no installation IDs."""
    # [impl->req~grants-no-installation-ids~1]
    offending = sorted({name for name in columns if name.lower() in INSTALLATION_ID_COLUMNS})
    if offending:
        raise FreeGrantError(f"{offending} would store an installation ID")


def assert_no_general_device_records(tables: Iterable[str] = (),
                                     columns: Iterable[str] = ()) -> None:
    """PostgreSQL keeps no general device records: there is no device table to hold them, and no
    device principal or device-check-state hash standing in for one."""
    # [impl->req~grants-no-general-device-records~1]
    if DEVICE_RECORD_TABLES:
        raise FreeGrantError("there is no general device record table")
    offending = sorted({name for name in tables
                        if name.lower() in FORBIDDEN_DEVICE_TABLE_NAMES})
    if offending:
        raise FreeGrantError(f"{offending} would be a general device record table")
    principals = sorted({name for name in columns if name.lower() in DEVICE_PRINCIPAL_COLUMNS})
    if principals:
        raise FreeGrantError(f"{principals} would be a device record in a column")


def assert_no_raw_attestation_tokens(columns: Iterable[str]) -> None:
    """PostgreSQL stores no raw DeviceCheck tokens and no raw Play Integrity tokens."""
    # [impl->req~grants-no-raw-attestation-tokens~1]
    offending = sorted({name for name in columns
                        if name.lower() in RAW_ATTESTATION_TOKEN_COLUMNS})
    if offending:
        raise FreeGrantError(f"{offending} would store a raw vendor attestation token")


def assert_no_raw_cloudflare_tokens(columns: Iterable[str]) -> None:
    """PostgreSQL stores no raw Cloudflare bot-check tokens."""
    # [impl->req~grants-no-raw-cloudflare-tokens~1]
    offending = sorted({name for name in columns
                        if name.lower() in RAW_CLOUDFLARE_TOKEN_COLUMNS})
    if offending:
        raise FreeGrantError(f"{offending} would store a raw Cloudflare bot-check token")


def assert_provider_account_id_store(table: str) -> str:
    """A raw Google or Apple provider account identifier lives in `core.external_identities` and
    in the canonical `core.provider_accounts` registry, and nowhere else."""
    # [impl->req~grants-no-raw-provider-ids-outside-registry~1]
    if table not in RAW_PROVIDER_ACCOUNT_TABLES:
        raise FreeGrantError(f"{table} stores no raw provider account identifier")
    return table


def assert_no_claim_finalization_table(tables: Iterable[str]) -> None:
    """There is no separate anonymous free-grant claim-finalization table: the grant row and its
    anti-abuse row are the whole record of a finalized claim."""
    # [impl->req~grants-no-claim-finalization-table~1]
    if CLAIM_FINALIZATION_TABLES:
        raise FreeGrantError("no claim-finalization table exists")
    offending = sorted({name for name in tables
                        if name.lower() in FORBIDDEN_CLAIM_FINALIZATION_NAMES})
    if offending:
        raise FreeGrantError(f"{offending} would be a claim-finalization table")


def assert_postgres_does_not_store(*,
                                   tables: Iterable[str] = (),
                                   columns: Iterable[str] = ()) -> None:
    """The whole list, in one call: every family above, checked together."""
    # [impl->req~grants-postgres-does-not-store~1]
    if len(POSTGRES_NEVER_STORES) != 7:
        raise FreeGrantError("the list has seven entries")
    columns = list(columns)
    tables = list(tables)
    assert_no_raw_device_ids(columns)
    assert_no_installation_ids(columns)
    assert_no_general_device_records(tables, columns)
    assert_no_raw_attestation_tokens(columns)
    assert_no_raw_cloudflare_tokens(columns)
    assert_no_claim_finalization_table(tables)
    # The raw provider account identifier is the one family whose rule is table-scoped: it lives
    # in the two registry tables and nowhere else, so `assert_provider_account_id_store` is what
    # a writer of that column asks, rather than a global column check here.


# --- The anti-abuse table and its rows ------------------------------------------------------------

# Anti-abuse fields live on their own table, keyed one-to-one by `grant_id`, so the entitlement
# table carries entitlement state only and does not vary its column shape per source.
# [impl->req~grants-anti-abuse-table-separate~1]
ANTI_ABUSE_TABLE: str = "core.access_grants_anti_abuse"
ANTI_ABUSE_KEY: str = "grant_id"
ANTI_ABUSE_UNIQUENESS_DOMAIN: dict[AccessGrantSource, GateConsumptionKind] = {
    AccessGrantSource.anonymous_device_grant: GateConsumptionKind.web_anonymous_gate,
    AccessGrantSource.registered_account_grant: GateConsumptionKind.registered_account_grant,
}


def free_grant_anti_abuse_row(*,
                              grant_id: UUID,
                              source: AccessGrantSource,
                              platform: DevicePlatform | None = None,
                              idp_account_hash: bytes | None = None,
                              idp_account_hash_key_version: int | None = None,
                              created_at: datetime | None = None,
                              grant_columns: Iterable[str] = ()) -> dict[str, Any]:
    """One anti-abuse row beside its entitlement-only grant row. Native anonymous rows record the
    platform device-check gate through `native_claim_provider` and persist no principal; web
    anonymous rows carry the derived provider-account `idp_account_hash` and its key version;
    registered account grant rows carry the same alias under their own uniqueness domain."""
    # [impl->req~grants-anti-abuse-table-separate~1]
    # [impl->req~grants-anti-abuse-row-records-gate~1]
    if source not in FREE_GRANT_SOURCES:
        raise FreeGrantError(f"a {source} grant has no anti-abuse row")
    assert_grant_columns_entitlement_only(grant_columns)
    assert_anti_abuse_pairing(source, source)
    if source is AccessGrantSource.anonymous_device_grant:
        row = anonymous_device_grant_row(grant_id=grant_id, platform=platform,
                                         idp_account_hash=idp_account_hash,
                                         idp_account_hash_key_version=idp_account_hash_key_version,
                                         created_at=created_at)
    elif source is AccessGrantSource.registered_account_grant:
        anti_abuse_evidence(grant_source=source,
                            idp_account_hash=idp_account_hash,
                            idp_account_hash_key_version=idp_account_hash_key_version)
        row = {
            "grant_id": grant_id,
            "grant_source": source,
            "native_claim_provider": None,
            "idp_account_hash": idp_account_hash,
            "idp_account_hash_key_version": idp_account_hash_key_version,
            "created_at": created_at if created_at is not None else datetime.now(UTC),
        }
        assert_anti_abuse_row_prohibitions(row)
    else:
        raise FreeGrantError(f"a {source} grant has no anti-abuse row")
    assert_postgres_does_not_store(columns=row)
    return row


def gate_recorded_by(row: Mapping[str, Any]) -> str:
    """Which platform gate an `anonymous_device_grant` anti-abuse row records. For native rows
    the per-device state itself stays with the vendor and PostgreSQL records no device principal;
    for web rows PostgreSQL persists the derived `idp_account_hash` and key version only."""
    # [impl->req~grants-anti-abuse-row-records-gate~1]
    if row.get("grant_source") is not AccessGrantSource.anonymous_device_grant:
        raise FreeGrantError("only an anonymous_device_grant row records a platform gate")
    assert_postgres_does_not_store(columns=row)
    native = row.get("native_claim_provider")
    if native is not None:
        return str(native)
    if row.get("idp_account_hash") is None or row.get("idp_account_hash_key_version") is None:
        raise FreeGrantError("an anonymous_device_grant row records one gate's evidence")
    return BRANCH_VENDOR_GATE[ClaimBranch.web]


# --- Gate uniqueness on the stable provider UID ---------------------------------------------------

# Uniqueness is enforced on the stable provider-account UID, never on hash bytes: the canonical
# registry is unique on `(provider, provider_uid)` and each consumed gate is one row unique on
# `(provider_account_id, consumption_kind)`, inserted in the same transaction as the grant.
# `idp_account_hash` and its key version persist only as a non-authoritative lookup and audit
# alias, so wherever this file names an `idp_account_hash` uniqueness domain the enforced rule is
# this one and the conflict arises on the gate-consumption insert.
# [impl->req~grants-gate-uniqueness-on-stable-uid~1]
PROVIDER_ACCOUNTS_TABLE: str = "core.provider_accounts"
GATE_CONSUMPTIONS_TABLE: str = "core.provider_account_gate_consumptions"
PROVIDER_ACCOUNTS_UNIQUE_ON: tuple[str, ...] = ("provider", "provider_uid")
GATE_CONSUMPTIONS_UNIQUE_ON: tuple[str, ...] = ("provider_account_id", "consumption_kind")
IDP_ACCOUNT_HASH_IS_AUTHORITATIVE: bool = False
# The per-gate rows are per-key abuse brakes, not independent allowances: one free grant per
# account across both claim endpoints, with conversion of the user's active anonymous grant
# allowed as a transition rather than a second issuance.
FREE_GRANTS_PER_PROVIDER_ACCOUNT: int = 1


def consume_free_grant_gate(index: IdpAccountAliasIndex,
                            account: ProviderAccount,
                            kind: GateConsumptionKind,
                            grant_id: UUID,
                            *,
                            transaction: object,
                            grant_transaction: object) -> DerivedValue:
    """Record this provider account's consumption of one free-grant gate, in the same transaction
    that inserts the grant. The conflict a repeat raises is the gate-consumption insert's, keyed
    by the canonical provider account; the alias recorded beside it decides nothing."""
    # [impl->req~grants-gate-uniqueness-on-stable-uid~1]
    if IDP_ACCOUNT_HASH_IS_AUTHORITATIVE:
        raise FreeGrantError("idp_account_hash is a lookup and audit alias, never the authority")
    if transaction is not grant_transaction:
        raise FreeGrantError("the gate consumption is inserted with its grant, in one transaction")
    assert_uniqueness_anchor(UNIQUENESS_ANCHOR)
    return index.consume(account, kind, grant_id)


# --- The closed grant source enumeration ----------------------------------------------------------

# Exactly four sources, with a creator and a lifecycle for each. There is no `promo` source and no
# value reserved for a future one.
# [impl->req~grants-source-enumeration-closed~1]
GRANT_SOURCE_CREATORS: dict[AccessGrantSource, str] = {
    AccessGrantSource.anonymous_device_grant: "claim_anonymous_grant",
    AccessGrantSource.registered_account_grant: "claim_registered_grant",
    AccessGrantSource.subscription: "purchase_ingestion_renewal_and_restore_adoption",
    AccessGrantSource.manual: "manual_issuance",
}
REMOVED_GRANT_SOURCES: frozenset[str] = frozenset({"promo"})
RESERVED_FUTURE_GRANT_SOURCES: frozenset[str] = frozenset()
GENERIC_GRANT_WRITERS: frozenset[str] = frozenset()

# The platform detail audit and support handling need for anonymous grants, which never changes
# the canonical `source` value the database uniqueness rules use.
# [impl->req~grants-source-enumeration-closed~1]
ANONYMOUS_PLATFORM_AUDIT_DETAIL: dict[ClaimBranch, str] = {
    ClaimBranch.native_ios: "ios_devicecheck",
    ClaimBranch.native_android: "android_play_integrity_device_recall",
    ClaimBranch.web: "web_signin_plus_cloudflare_bot_check",
}


def validate_grant_source(value: str | AccessGrantSource) -> AccessGrantSource:
    """Source validation is exhaustive and fails closed: a write carrying an unknown or removed
    source value — `promo` included — is rejected rather than accepted as a generic grant, and no
    fallback or generic grant-writing path exists to accept one."""
    # [impl->req~grants-source-enumeration-closed~1]
    if GENERIC_GRANT_WRITERS or RESERVED_FUTURE_GRANT_SOURCES:
        raise FreeGrantError("no generic grant-writing path and no reserved source value exists")
    text = str(value)
    if text in REMOVED_GRANT_SOURCES or text not in set(AccessGrantSource):
        raise FreeGrantError(f"{text!r} is not a core.access_grant_source value")
    source = AccessGrantSource(text)
    if source not in GRANT_SOURCE_CREATORS:
        raise FreeGrantError(f"{source} names no creator or lifecycle")
    return source


def anonymous_platform_detail(branch: ClaimBranch) -> tuple[AccessGrantSource, str]:
    """The canonical `grant_source` value stays `anonymous_device_grant` for native and web rows
    alike and never encodes platform; the platform distinction travels in audit detail."""
    # [impl->req~grants-source-enumeration-closed~1]
    detail = ANONYMOUS_PLATFORM_AUDIT_DETAIL.get(branch)
    if detail is None:
        raise FreeGrantError(f"{branch} has no audited platform detail")
    source = anonymous_claim_source(branch)
    if str(source) != AccessGrantSource.anonymous_device_grant.value:
        raise FreeGrantError("the canonical source never encodes platform")
    return source, detail


# --- Branch selection for `claim_anonymous_grant` --------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClaimEvidence:
    """The evidence a claim request carries, and the whole of what branch selection reads."""
    devicecheck_query_token: str | None = None
    devicecheck_update_token: str | None = None
    play_integrity_token: str | None = None
    turnstile_token: str | None = None

    def present(self) -> frozenset[str]:
        return frozenset(name for name in BRANCH_SELECTION_INPUTS if getattr(self, name))


# The four request fields branch selection reads, and the branch each belongs to. Nothing else
# participates: no client-declared claim-channel field exists or is consulted, no gateway-supplied
# identity or platform header takes part, and neither identity, stored provider nor `User-Agent`
# is an input — they apply only as the selected branch's own identity and ledger rules.
# [impl->req~grants-branch-selection-deterministic~1]
BRANCH_EVIDENCE: dict[ClaimBranch, tuple[str, ...]] = {
    ClaimBranch.native_ios: ("devicecheck_query_token", "devicecheck_update_token"),
    ClaimBranch.native_android: ("play_integrity_token",),
    ClaimBranch.web: ("turnstile_token",),
}
BRANCH_SELECTION_INPUTS: tuple[str, ...] = tuple(
    name for artifacts in BRANCH_EVIDENCE.values() for name in artifacts)
NON_SELECTION_INPUTS: frozenset[str] = frozenset({
    "claim_channel", "branch", "platform", "x-platform", "x-client-platform", "user_agent",
    "user-agent", "authorization", "x-user-id", "identity", "stored_provider",
    "gateway_resolved_user",
})
BRANCH_RANKING: tuple[ClaimBranch, ...] = ()

# What the selected evidence set is verified against server-side, before that branch's
# eligibility is evaluated. Evidence cannot be cross-played: DeviceCheck tokens come only from
# Apple hardware and Play Integrity tokens only from GMS Android.
# [impl->req~grants-branch-selection-deterministic~1]
BRANCH_SERVER_VERIFICATION: dict[ClaimBranch, tuple[str, ...]] = {
    ClaimBranch.native_ios: ("apple_team_id", "devicecheck_environment"),
    ClaimBranch.native_android: ("package_name", "signing_certificate_digest"),
    ClaimBranch.web: ("hostname", "action"),
}


def select_branch(evidence: ClaimEvidence,
                  *,
                  declared_channel: str | None = None,
                  consulted: Sequence[str] = ()) -> ClaimBranch:
    """Branch selection is a deterministic, server-verified function of which evidence set the
    request carries. A request must resolve to exactly one branch's set: zero sets, more than one
    set, or a partial set is a request-shape validation error rejected before any eligibility
    check, vendor call or ledger write, never ranked, preferred or fallen through."""
    # [impl->req~grants-branch-selection-deterministic~1]
    if BRANCH_RANKING:
        raise FreeGrantError("the branches are never ranked, preferred or fallen through")
    if declared_channel is not None:
        raise FreeGrantError("no client-declared claim-channel field exists or is consulted")
    offending = sorted(set(consulted) - set(BRANCH_SELECTION_INPUTS))
    if offending:
        raise FreeGrantError(f"{offending} never participates in branch selection")
    present = evidence.present()
    touched = {branch for branch, artifacts in BRANCH_EVIDENCE.items()
               if present & set(artifacts)}
    if not touched:
        raise BranchShapeError("no branch evidence set is present")
    if len(touched) > 1:
        raise BranchShapeError(
            f"evidence for {sorted(str(branch) for branch in touched)} is present")
    branch = touched.pop()
    missing = [name for name in BRANCH_EVIDENCE[branch] if name not in present]
    if missing:
        raise BranchShapeError(f"{branch} evidence set is partial: {missing} missing")
    return branch


def assert_branch_verified(branch: ClaimBranch, verified: Sequence[str]) -> None:
    """The selected evidence set is fully verified server-side against the vendor — nonce,
    request hash, hostname, action, package name or signing-certificate digest against the
    expected deployment — before that branch's eligibility is evaluated. Client-supplied material
    is never trusted directly."""
    # [impl->req~grants-branch-selection-deterministic~1]
    missing = [name for name in BRANCH_SERVER_VERIFICATION[branch] if name not in set(verified)]
    if missing:
        raise ProofRejected(f"{branch} evidence is unverified against {missing}")


# --- Branch pinning and shared admission ----------------------------------------------------------

# An anonymous identity may use only the device-attestation branches; a registered claimant
# presenting Cloudflare evidence on any surface, native app included, is a legitimate use of the
# web/registered gate rather than a bypass — under the lifetime one-free-grant-per-account cap,
# which ledger slot the grant burns is economically inconsequential.
# [impl->req~grants-branch-pinning-and-shared-admission~1]
ANONYMOUS_IDENTITY_BRANCHES: frozenset[ClaimBranch] = NATIVE_BRANCHES
LIFETIME_FREE_GRANTS_PER_ACCOUNT: int = 1


def assert_pinned_platform_matches(row: ExternalIdentityRow,
                                   branch: ClaimBranch) -> NativeClaimPlatform | None:
    """The half of the pinning rule that runs at branch selection: an anonymous identity may use
    only the device-attestation branches, and material from the other platform than the one this
    identity is already pinned to is rejected — so the same anonymous identity cannot switch
    branches. Nothing is written here; the pin itself is set once the attestation verifies.

    A registered claimant is not pinned: it may use the web/registered gate on any surface.
    """
    # [impl->req~grants-branch-pinning-and-shared-admission~1]
    if row.provider is not IdentityProvider.anonymous:
        return row.native_claim_platform
    if branch not in ANONYMOUS_IDENTITY_BRANCHES:
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "verification_required",
                                "an anonymous identity may use only the attestation branches")
    platform = NATIVE_CLAIM_PROVIDER[BRANCH_PLATFORM[branch]]
    stored = row.native_claim_platform
    if stored is not None and stored is not platform:
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "operation_not_allowed",
                                f"this identity is pinned to {stored}")
    return stored


def pin_native_platform(row: ExternalIdentityRow,
                        branch: ClaimBranch,
                        *,
                        attestation_verified: bool) -> ExternalIdentityRow:
    """An anonymous identity's native claim platform is pinned to the identity record when its
    first device attestation verifies, and is never re-declared per request. The set-once,
    immutable-once-set decision belongs to the `native_claim_platform` column's owner, so this
    delegates to it and only translates its refusal into this operation's rejection class; the
    returned row is the one the activation transaction writes.
    """
    # [impl->req~grants-branch-pinning-and-shared-admission~1]
    if row.provider is not IdentityProvider.anonymous:
        # A registered claimant is not pinned: it may use the web/registered gate on any surface.
        return row
    stored = assert_pinned_platform_matches(row, branch)
    platform = NATIVE_CLAIM_PROVIDER[BRANCH_PLATFORM[branch]]
    if stored is None and not attestation_verified:
        raise ProofRejected("the platform is pinned once the device attestation verifies")
    try:
        return pin_native_claim_platform(row, platform,
                                         attestation_verified=attestation_verified)
    except IdentityError as exc:
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "operation_not_allowed",
                                str(exc)) from None


def claim_admission_pair(branch: ClaimBranch, phase: str = "complete") -> tuple[str, str]:
    """All claim attempts, whatever branch, share the same endpoint-level per-user and per-IP
    admission accounting, so switching branches cannot reset an attempt budget and the per-IP and
    per-user gateway caps bound abuse across branches."""
    # [impl->req~grants-branch-pinning-and-shared-admission~1]
    if branch not in BRANCH_EVIDENCE:
        raise FreeGrantError(f"{branch} is no claim branch")
    return ANONYMOUS_GRANT_ADMISSION[phase]


# --- Development and simulator bypass boundary ------------------------------------------------------


class DeploymentEnvironment(StrEnum):
    """The server-side deployment environments a build or configuration can name."""
    development = "development"
    staging = "staging"
    production = "production"


# The one gate that has a development and simulator bypass, and the environments that bypass may
# exist in. Production is not one of them, so a bypass cannot reach production.
# [impl->req~grants-devcheck-bypass-non-production-only~1]
BYPASSABLE_GATES: frozenset[str] = frozenset({"device_check"})
BYPASS_ENVIRONMENTS: frozenset[DeploymentEnvironment] = frozenset({
    DeploymentEnvironment.development, DeploymentEnvironment.staging})
# No client-supplied signal of any kind can enable the bypass — not a header, body field, token
# claim, or anything else — and no generalized development-flag framework exists.
CLIENT_SELECTABLE_BYPASS_SIGNALS: frozenset[str] = frozenset()
DEVELOPMENT_FLAG_FRAMEWORKS: frozenset[str] = frozenset()
BYPASS_ENABLED_BY: str = "server_side_build_or_configuration_state"


def device_check_bypass_enabled(*,
                                environment: DeploymentEnvironment,
                                server_configured: bool,
                                client_signals: Mapping[str, Any] | Sequence[str] = (),
                                production_credentials: bool = False,
                                gate: str = "device_check") -> bool:
    """Whether the device-check gate's development or simulator bypass is in effect.

    It may be in effect only in a non-production configuration that cannot reach production, and
    only from server-side build or configuration state. Any client-supplied signal offered as an
    enabler is a hard failure rather than an ignored input, as is a bypass configured in production
    or alongside production service credentials. This governs the device-check gate alone: no other
    gate — the Cloudflare gate included — gains a symmetric bypass.
    """
    # [impl->req~grants-devcheck-bypass-non-production-only~1]
    if gate not in BYPASSABLE_GATES:
        raise FreeGrantError(f"{gate} has no development or simulator bypass")
    if DEVELOPMENT_FLAG_FRAMEWORKS or CLIENT_SELECTABLE_BYPASS_SIGNALS:
        raise FreeGrantError("no generalized development-flag framework exists")
    offered = sorted(client_signals)
    if offered:
        raise FreeGrantError(f"{offered} is client input and never enables the bypass")
    if production_credentials:
        raise FreeGrantError("production service credentials never enable the bypass")
    if environment is DeploymentEnvironment.production:
        if server_configured:
            raise FreeGrantError("a device-check bypass cannot be enabled in production")
        return False
    if environment not in BYPASS_ENVIRONMENTS:
        raise FreeGrantError(f"{environment} is no bypass environment")
    return server_configured


# --- The proof is not identity ---------------------------------------------------------------------

# What establishes verified identity, and what never does. The gateway JWT filter is edge
# admission and defense-in-depth only, and handlers do not re-implement identity resolution.
# [impl->req~grants-anon-proof-not-identity~1]
IDENTITY_SOURCE: str = "backend_verified_firebase_id_token_issuer_and_subject"
NEVER_IDENTITY: frozenset[str] = frozenset({"devicecheck_query_token", "devicecheck_update_token",
                                            "play_integrity_token", "turnstile_token"})
GATEWAY_JWT_FILTER_ROLE: str = "edge_admission_and_defense_in_depth"
HANDLER_IDENTITY_RESOLUTIONS: int = 0


def claim_identity(context: VerifiedIdentityContext,
                   *,
                   offered: Sequence[str] = ()) -> tuple[str, str]:
    """The device-check proof token and the Cloudflare bot-check evidence are not identity and
    never select the user: verified identity is the backend-verified Firebase ID token's
    `(issuer, subject)` produced by the shared mandatory pre-handler barrier, and the web
    stored-binding check is derived server-side from the registered identity and its live
    Firebase Admin `providerData`."""
    # [impl->req~grants-anon-proof-not-identity~1]
    if HANDLER_IDENTITY_RESOLUTIONS:
        raise FreeGrantError("handlers do not re-implement identity resolution")
    offending = sorted(set(offered) & NEVER_IDENTITY)
    if offending:
        raise FreeGrantError(f"{offending} never selects the user")
    if not context.issuer or not context.subject:
        raise FreeGrantError("the barrier resolved no verified issuer and subject")
    return context.issuer, context.subject


# --- The required rules, in the order they run in --------------------------------------------------


class ClaimStep(StrEnum):
    """The steps of one `claim_anonymous_grant` attempt, in the one order they may run in.

    The shared pre-consumption checks — the barrier's four checks in
    `00-overview-and-shared-contracts.md`, each of them rejected before every challenge check —
    and the handler-side admission checks come first, and the challenge claim is step 8, after
    them: a claimant whose identity the barrier refuses is rejected before the claim and leaves
    the challenge unclaimed, having learnt nothing about whether it existed or was already used.
    """
    admission = "admission"
    identity_barrier = "identity_barrier"
    challenge_claim = "challenge_claim"
    branch_selection = "branch_selection"
    platform_gate = "platform_gate"
    database_eligibility = "database_eligibility"
    native_bit_write = "native_bit_write"
    activation = "activation"


ANONYMOUS_CLAIM_STEPS: tuple[ClaimStep, ...] = tuple(ClaimStep)

# The mutation rules and every vendor interaction run after the challenge claim; the native
# read-write-activate sequence runs in a context a client disconnect cannot cancel.
# [impl->req~grants-anon-rule-pre-consumption-then-challenge~1]
PRE_CHALLENGE_VENDOR_CALLS: int = 0
# [impl->req~grants-anon-rule-no-enrolled-key~1]
ENROLLED_KEY_PARTICIPANTS: frozenset[str] = frozenset()
PER_KEY_UNIQUENESS_ROWS: frozenset[str] = frozenset()


class ChallengeGate(Protocol):
    """The two atomic conditional updates the shared completion requirements own, as this claim
    sees them: the claim that serializes the attempt, and the consumption in its transaction."""

    def claim(self) -> ClaimOutcome: ...

    def consume(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class GateReading:
    """What reading the branch's platform gate found."""
    branch: ClaimBranch
    already_claimed: bool
    web_account: WebGateAccount | None = None


@dataclass(frozen=True, slots=True)
class ActivatedGrant:
    """The rows one activation transaction wrote, and the audit record it appended. `identity` is
    the claimant's identity row as the transaction leaves it — for an anonymous native claimant,
    carrying the `native_claim_platform` pin this attempt's verified attestation set."""
    grant: dict[str, Any]
    anti_abuse: dict[str, Any]
    usage: NewUsageRow
    audit: AuthEvent
    alias: DerivedValue | None = None
    identity: ExternalIdentityRow | None = None


def assert_no_enrolled_key(*,
                           participants: Sequence[str] = (),
                           uniqueness_rows: Sequence[str] = ()) -> None:
    """No App Attest proof, Android Keystore proof, enrolled-key binding or per-key uniqueness row
    participates in `claim_anonymous_grant`: there is no App Attest proof requirement and no
    enrolled-key binding requirement at its entry condition."""
    # [impl->req~grants-anon-rule-no-enrolled-key~1]
    # [impl->req~grants-anon-entry-no-app-attest~1]
    if participants or uniqueness_rows or ENROLLED_KEY_PARTICIPANTS or PER_KEY_UNIQUENESS_ROWS:
        raise FreeGrantError(
            f"no enrolled key or per-key uniqueness row participates: "
            f"{sorted(set(participants) | set(uniqueness_rows))}")


@dataclass(frozen=True, slots=True)
class WebGateRead:
    """What the web branch needs to read its gate: the identity row, the server-side Cloudflare
    bot check, the configured Firebase integrations, the request's backend-verified issuer, and
    the `providerData` read itself — which runs through the Admin client this issuer selects and
    never through a caller-supplied result."""
    row: ExternalIdentityRow
    bot_check: Callable[[], bool]
    integrations: FirebaseIntegrations
    issuer: str
    read_provider_data: Callable[[Any], Sequence[object] | None]


def read_web_gate(read: WebGateRead,
                  *,
                  index: IdpAccountAliasIndex | None = None) -> tuple[WebGateAccount,
                                                                      DerivedValue | None]:
    """The web branch's gate, in its own order: the server-validated Cloudflare bot check, then
    the Admin client of the single configured Firebase integration selected by the request's
    backend-verified issuer classifying the complete live `providerData` result under the closed
    classifier, then equality against the stored provider and stored `provider_uid`, then the
    per-provider-account `idp_account_hash` derived with the stored provider as the HMAC provider
    component — the hash and key version the anonymous-grant anti-abuse row persists.

    The `providerData` result is never client-supplied: it is what the issuer-selected Admin
    client returned for this identity, and an issuer that matches no configured integration fails
    here, before the classifier runs.
    """
    # [impl->req~grants-platform-gate-web~1]
    # [impl->req~grants-anon-rule-read-platform-gate~1]
    # [impl->req~grants-anon-rule-web-classifier-and-hash~1]
    # [impl->req~grants-anon-step-02-read-platform-gate~1]
    # [impl->req~grants-vendor-state-never-client-supplied~1]
    row = read.row
    if not read.bot_check():
        raise GateDenied("the server-validated Cloudflare bot check did not pass")
    client = web_gate_admin_client(read.integrations, read.issuer)
    provider_data = read.read_provider_data(client)
    account = web_anonymous_grant_gate(row, provider_data)
    web_hash_provider_component(row, account)
    if index is None:
        return account, None
    alias = index.alias(ProviderAccount(provider=account.provider,
                                        provider_uid=account.canonical_provider_account_id))
    return account, alias


def read_native_gate(adapter: DeviceStateAdapter,
                     material: Any,
                     *,
                     ledger: NativeClaimLedger) -> bool:
    """The native branch's gate read: verify the vendor material, then read the per-device
    anonymous-claimed state through DeviceCheck on iOS or Play Integrity plus Device Recall on
    Android. The step order inside it is the proof adapters' mandatory sequence: all the vendor
    material this branch needs is required and verified up front, before the state is queried."""
    # [impl->req~grants-anon-rule-read-platform-gate~1]
    # [impl->req~grants-anon-step-02-read-platform-gate~1]
    # [impl->req~grants-platform-gate-ios~1]
    # [impl->req~grants-platform-gate-android~1]
    operation = AuthOperation.claim_anonymous_grant
    adapter.verify_material(operation, material, ledger)
    return adapter.read_claimed(operation, material, ledger)


def recall_absence_alternate() -> AuthOperation:
    """Android Device Recall state that the decoded verdict does not carry rejects the claim with
    no grant; the registered account grant path remains the specified alternate.

    The same alternate is what the client is directed to whenever it cannot present qualifying
    native evidence at all: withheld, missing or malformed native material and a verified verdict
    that lacks Device Recall are one `proof_rejected` outcome with one alternate, and the backend
    never distinguishes absent capability from withheld material.
    """
    # [impl->req~grants-anon-rule-device-recall-fails-closed~1]
    # [impl->req~grants-anon-alt-proof-rejected-to-registered~1]
    return AuthOperation.claim_registered_grant


# --- The operation challenge this attempt claims ---------------------------------------------------


def assert_challenge_valid_for_claim(row: ChallengeRow,
                                    context: VerifiedIdentityContext,
                                    *,
                                    now: datetime,
                                    operation: AuthOperation =
                                    AuthOperation.claim_anonymous_grant) -> ChallengeRow:
    """The operation challenge the completion presents must be valid for this operation: issued
    for it, bound to the barrier-verified identity, unexpired, and not already claimed or
    consumed.

    Every one of these is checked before the atomic claim, so a challenge that fails them is left
    unclaimed — the identity- and operation-mismatch cases included, which reject here having made
    no vendor call, no Cloudflare validation and no Firebase lookup. Each keeps its own specific
    internal result under the shared `challenge_required` class.
    """
    # [impl->req~grants-anon-entry-challenge-valid~1]
    if row.operation is not operation:
        raise FreeGrantRejected(AuthEventResult.challenge_operation_mismatch, "challenge_required",
                                f"the challenge was issued for {row.operation}")
    bound = row.binding.bound_external_identity_id
    if bound is None or (context.external_identity_id is not None
                         and bound != context.external_identity_id):
        raise FreeGrantRejected(AuthEventResult.challenge_identity_mismatch, "challenge_required",
                                "the challenge binds another identity")
    if row.state is not ChallengeState.issued:
        raise FreeGrantRejected(AuthEventResult.challenge_consumed, "challenge_required",
                                f"a {row.state} challenge cannot be claimed again")
    if row.expires_at <= now:
        raise FreeGrantRejected(AuthEventResult.challenge_expired, "challenge_required",
                                "the operation challenge expired")
    return row


# --- The database eligibility preflight, and the invariant paths it takes --------------------------


def active_grant_invariant_rejection(source: AccessGrantSource) -> FreeGrantRejected:
    """An existing active grant fails the database eligibility check under the specific
    active-grant invariant path. An active `anonymous_device_grant` is no exception and returns no
    idempotent success: it is a structural completion-time invariant violation, audited as
    `policy_rejected` and surfaced as `operation_not_allowed`, and no database grant may substitute
    for or suppress the platform-gate read that ran before it."""
    # [impl->req~grants-anon-step-04-db-eligibility~1]
    from nativespeaker.api.auth.grant_failures import (  # noqa: PLC0415
        StructuralBlock,
        operation_not_allowed_block,
    )

    rejection = operation_not_allowed_block(StructuralBlock.anon_completion_invariant)
    return FreeGrantRejected(rejection.audit_result, rejection.client_class.value,
                             f"an active {source} grant violates the one-active-grant invariant",
                             status_code=rejection.status)


def reconfirm_claimant(row: ExternalIdentityRow,
                       branch: ClaimBranch,
                       *,
                       web_account: WebGateAccount | None = None,
                       consulted: Sequence[str] = ()) -> ExternalIdentityRow:
    """The activation transaction's own reconfirmation of the claimant, under the lock.

    The identity must still be active, and it must still be the same identity the gate ran
    against: an anonymous native claimant still matching its pinned native claim platform, or a
    registered claimant still carrying the stored Google or Apple provider and `provider_uid` the
    native or web gate used. The permanent free-grant-consumed marker must still be unset.
    `registered_at` is not consulted.
    """
    # [impl->req~grants-anon-step-06-activation-transaction~1]
    offending = sorted(set(consulted) & NEVER_CONSULTED_FOR_ELIGIBILITY)
    if offending:
        raise FreeGrantError(f"{offending} is not consulted by the activation reconfirmation")
    if row.identity_state is not IdentityState.active:
        raise ClaimRejection(AuthEventResult.historical_identity,
                             "the claimant identity is no longer active")
    if not free_grant_available(row, AuthOperation.claim_anonymous_grant):
        # The marker is authoritative for the cross-endpoint refusal, and it is permanent.
        raise ClaimRejection(AuthEventResult.anti_abuse_already_claimed,
                             "this account already consumed its one lifetime free grant")
    if row.provider is IdentityProvider.anonymous:
        # Still the same identity: an anonymous native claimant still matches its pin.
        assert_pinned_platform_matches(row, branch)
        return row
    if row.provider not in REGISTERED_PROVIDERS or not row.provider_uid:
        raise FreeGrantRejected(AuthEventResult.policy_rejected, "verification_required",
                                "the registered claimant no longer carries its stored binding")
    if branch is ClaimBranch.web:
        if web_account is None:
            raise FreeGrantError("a web activation reconfirms the account its gate resolved")
        if (web_account.provider is not row.provider
                or web_account.canonical_provider_account_id != row.provider_uid):
            raise FreeGrantRejected(AuthEventResult.policy_rejected, "verification_required",
                                    "the stored binding the web gate used no longer applies")
    return row


class AnonymousGrantClaim:
    """One `claim_anonymous_grant` attempt's required rules, in the one order they run in.

    Each step records itself, and a step that runs out of order, twice, or without its
    predecessors refuses. The steps themselves delegate: the shared barrier resolves the
    identity, the shared completion requirements own the challenge claim and consumption, the
    proof adapters own the vendor sequence, and the schema module owns the row shapes.
    """

    def __init__(self) -> None:
        self.steps: list[ClaimStep] = []
        self.branch: ClaimBranch | None = None
        self.vendor_calls = 0

    # --- ordering -------------------------------------------------------------------------

    def _record(self, step: ClaimStep) -> None:
        position = ANONYMOUS_CLAIM_STEPS.index(step)
        if self.steps and position <= ANONYMOUS_CLAIM_STEPS.index(self.steps[-1]):
            raise FreeGrantError(f"{step} cannot run after {self.steps[-1]}")
        self.steps.append(step)

    def _require(self, *steps: ClaimStep) -> None:
        missing = [step for step in steps if step not in self.steps]
        if missing:
            raise FreeGrantError(f"{missing} must run first")

    # --- the rules ------------------------------------------------------------------------

    def admit(self, *,
              pre_consumption_passed: bool,
              handler_admission_passed: bool,
              vendor_calls_made: int = 0) -> None:
        """The shared pre-consumption checks and the handler-side admission checks must pass
        before anything else: before the operation challenge is claimed, before any device-check
        vendor call, Cloudflare validation or Firebase Admin lookup, and before the
        anonymous-grant mutation rules run."""
        # [impl->req~grants-anon-rule-pre-consumption-then-challenge~1]
        self._record(ClaimStep.admission)
        if vendor_calls_made != PRE_CHALLENGE_VENDOR_CALLS:
            raise FreeGrantError("no vendor call precedes admission and the challenge claim")
        if not pre_consumption_passed or not handler_admission_passed:
            raise FreeGrantError("the shared and handler-side admission checks must pass first")

    def claim_challenge(self, gate: ChallengeGate,
                        *,
                        row: ChallengeRow | None = None,
                        context: VerifiedIdentityContext | None = None,
                        now: datetime | None = None) -> ClaimOutcome:
        """The operation challenge is then claimed under the shared completion requirements —
        after the barrier's checks and handler-side admission, and still before any vendor call.

        Where the presented row is available, it is checked for validity for
        `claim_anonymous_grant` first: a challenge issued for another operation, bound to another
        identity, expired, or already claimed or consumed is rejected here and left unclaimed.
        """
        # [impl->req~grants-anon-rule-pre-consumption-then-challenge~1]
        # [impl->req~grants-anon-mutation-challenge-claim-order~1]
        # [impl->req~grants-anon-entry-challenge-valid~1]
        self._require(ClaimStep.admission, ClaimStep.identity_barrier)
        if row is not None:
            if context is None:
                raise FreeGrantError("the challenge is checked against the barrier's own identity")
            assert_challenge_valid_for_claim(
                row, context, now=now if now is not None else datetime.now(UTC))
        self._record(ClaimStep.challenge_claim)
        claim = claim_challenge_before_vendor(gate.claim, vendor_calls_made=self.vendor_calls)
        if not claim.vendor_calls_allowed:
            raise FreeGrantError(f"the attempt did not claim the challenge: {claim.outcome}")
        return claim.outcome

    def resolve_identity(self,
                         context: VerifiedIdentityContext,
                         row: ExternalIdentityRow,
                         *,
                         offered_identity_inputs: Sequence[str] = ()) -> ExternalIdentityRow:
        """The current identity comes from the shared mandatory authentication-and-identity-
        resolution barrier and from nothing else: the barrier has backend-verified the Firebase ID
        token from the `Authorization` header, produced `(issuer, subject)` and resolved the current
        identity, and this handler neither re-verifies the token nor re-implements identity
        resolution. It is resolved before the challenge is claimed, so an identity the barrier
        refuses leaves the challenge unclaimed."""
        # [impl->req~grants-anon-rule-identity-barrier~1]
        # [impl->req~grants-anon-proof-not-identity~1]
        # [impl->req~grants-anon-mutation-challenge-claim-order~1]
        # [impl->req~grants-anon-entry-barrier~1]
        # [impl->req~grants-anon-step-01-resolve-identity~1]
        self._require(ClaimStep.admission)
        self._record(ClaimStep.identity_barrier)
        claim_identity(context, offered=offered_identity_inputs)
        if context.outcome is not ResolutionOutcome.linked:
            raise FreeGrantRejected(AuthEventResult.policy_rejected, "preauth_identity_not_allowed",
                                    "the claim needs the barrier's linked active identity")
        # A row that is not `active` is `historical`: the barrier's own result for it, under the
        # shared `account_unavailable` class, never the free-credit policy block.
        # [impl->req~shared-audit-outcome-barrier-rejection~1]
        if row.identity_state is not IdentityState.active:
            raise FreeGrantRejected(AuthEventResult.historical_identity, "account_unavailable",
                                    "the claim needs an active identity")
        if context.external_identity_id is not None and context.external_identity_id != row.id:
            raise FreeGrantError("the resolved context and the identity row must be the same row")
        return row

    def select_branch(self,
                      evidence: ClaimEvidence,
                      row: ExternalIdentityRow,
                      *,
                      declared_channel: str | None = None,
                      consulted: Sequence[str] = (),
                      verified: Sequence[str] = ()) -> ClaimBranch:
        """Select the one branch the request's evidence resolves to, verify that evidence set
        against the vendor, and only then apply the branch's identity and pinning rules: an active
        anonymous identity or an active `google`/`apple` registered identity on native, an active
        registered identity on web, and — for an anonymous claimant — the identity's pinned native
        claim platform, which rejects material from the other platform where it is already
        pinned."""
        # [impl->req~grants-branch-selection-deterministic~1]
        # [impl->req~grants-branch-pinning-and-shared-admission~1]
        # [impl->req~grants-anon-rule-identity-barrier~1]
        # [impl->req~grants-anon-step-01-resolve-identity~1]
        self._require(ClaimStep.identity_barrier)
        self._record(ClaimStep.branch_selection)
        branch = select_branch(evidence, declared_channel=declared_channel, consulted=consulted)
        assert_write_material_present(branch, _carried_artifacts(evidence))
        assert_branch_verified(branch, verified)
        assert_claimant_eligible(branch, row)
        # The pinning rule's refusal half runs here, before any vendor call; the pin itself is
        # written in the activation transaction, once the device attestation has verified.
        assert_pinned_platform_matches(row, branch)
        self.branch = branch
        return branch

    def read_platform_gate(self,
                           *,
                           native: tuple[DeviceStateAdapter, Any, NativeClaimLedger] | None = None,
                           web: WebGateRead | None = None,
                           index: IdpAccountAliasIndex | None = None) -> GateReading:
        """Read the branch's platform gate, after completion admission and the challenge claim.

        On iOS the separate DeviceCheck query and update tokens are required up front, the query
        material is verified, and the anonymous-claimed bit is queried; on Android the one Play
        Integrity token covering the Device Recall read and write is required and verified before
        the anonymous-claimed state is queried; on web the Cloudflare bot check is validated, the
        Admin client of the single configured Firebase integration is selected by matching the
        request's backend-verified issuer, the closed classifier is applied to the complete
        `providerData` result, the classified provider and sole entry's non-empty `uid` must equal
        the row's stored provider and stored `provider_uid`, and the web `idp_account_hash` is
        derived from that entry with the stored provider as the HMAC provider component. There is
        no provider preference order, and an extra or unrecognized entry rejects rather than being
        ignored.

        An already-set native state or an already-consumed web gate audits its own specific result
        and rejects with `device_grant_exhausted`, creating no grant.
        """
        # [impl->req~grants-anon-rule-read-platform-gate~1]
        # [impl->req~grants-anon-rule-already-consumed-rejects~1]
        # [impl->req~grants-anon-step-02-read-platform-gate~1]
        # [impl->req~grants-anon-step-03-gate-state-and-dependencies~1]
        self._require(ClaimStep.branch_selection)
        self._record(ClaimStep.platform_gate)
        branch = self._branch()
        if branch in NATIVE_BRANCHES:
            if native is None:
                raise FreeGrantError(f"{branch} reads the per-device state through its adapter")
            adapter, material, ledger = native
            self.vendor_calls += 1
            already = read_native_gate(adapter, material, ledger=ledger)
            device_grant_exhausted(anonymous_claimed=already)
            return GateReading(branch=branch, already_claimed=already)
        if web is None:
            raise FreeGrantError("the web branch reads the bot check and providerData")
        self.vendor_calls += 1
        account, _ = read_web_gate(web, index=index)
        consumed = (index is not None
                    and index.consumed(ProviderAccount(
                        provider=account.provider,
                        provider_uid=account.canonical_provider_account_id),
                        GateConsumptionKind.web_anonymous_gate) is not None)
        device_grant_exhausted(web_gate_consumed=consumed)
        return GateReading(branch=branch, already_claimed=consumed, web_account=account)

    def check_database_eligibility(self,
                                   *,
                                   committed_free_sources: Sequence[AccessGrantSource],
                                   active_grants: int = 0,
                                   active_sources: Sequence[AccessGrantSource] = (),
                                   identity: ExternalIdentityRow | None = None,
                                   reconcile_vendor_state: bool = False,
                                   ledger: NativeClaimLedger | None = None) -> None:
        """After an unset native bit or a satisfied web gate, check database per-user eligibility
        in one lookup against the identity record's permanent free-grant-consumed marker and the
        user's grant history, and confirm that activation would not stack a second free allowance
        or violate the lifetime `(user, source)`, one-free-grant-per-account, or one-active-grant
        rules.

        A set marker or any committed free grant of either source refuses the claim. An existing
        active `anonymous_device_grant` fails under the specific active-grant invariant path — it
        is never an idempotent-success shortcut — and no database grant may substitute for or
        suppress the platform-gate read, which is why this step cannot run before it. The check
        runs before any vendor bit or account-gate slot is burned, so a rejection consumes neither,
        and the backend must not infer, repair or reconcile vendor state from a grant. This is a
        preflight: the activation transaction repeats the live checks under lock, where the lifetime
        index's unique violation is the concurrency-safe final eligibility check.
        """
        # [impl->req~grants-anon-rule-db-eligibility-lifetime-slot~1]
        # [impl->req~grants-anon-step-04-db-eligibility~1]
        self._require(ClaimStep.platform_gate)
        self._record(ClaimStep.database_eligibility)
        if ledger is not None:
            # The native sequence's own eligibility step, recorded where the claim takes it.
            ledger.record(NativeClaimStep.database_eligibility)
        if reconcile_vendor_state:
            raise FreeGrantError("no vendor state is inferred, repaired or reconciled from a grant")
        # No bit has been written and no gate slot consumed at this point, so every rejection below
        # burns neither.
        if ClaimStep.native_bit_write in self.steps:
            raise FreeGrantError("eligibility is checked before the device bit is burned")
        assert_database_bounds(committed_free_sources=committed_free_sources,
                               active_grants=active_grants)
        if identity is not None and not free_grant_available(
                identity, AuthOperation.claim_anonymous_grant):
            raise ClaimRejection(AuthEventResult.anti_abuse_already_claimed,
                                 "the permanent free-grant-consumed marker is already set")
        held = [source for source in committed_free_sources if source in FREE_GRANT_SOURCES]
        if len(held) >= LIFETIME_FREE_GRANTS_PER_ACCOUNT:
            raise ClaimRejection(AuthEventResult.anti_abuse_already_claimed,
                                 f"a committed {held[0]} grant refuses this claim")
        active = [source for source in active_sources]
        if active:
            # The specific active-grant invariant path, an active anonymous grant included.
            raise active_grant_invariant_rejection(active[0])

    def write_native_bit(self,
                         adapter: DeviceStateAdapter,
                         material: Any,
                         *,
                         ledger: NativeClaimLedger) -> DeviceBitWrite:
        """On a native path, write the per-device anonymous-claimed bit before activation, with the
        in-request retry budget, and refuse with `verification_temporarily_unavailable` and no grant
        on any exhausted failure, timeout, cancellation, ambiguous result or inability to attempt
        the write: the server never grants around the write. Only explicit vendor confirmation
        permits the activation transaction, and the whole read-write-activate sequence runs in a
        server execution context a client disconnect cannot cancel."""
        # [impl->req~grants-anon-rule-native-bit-write~1]
        # [impl->req~grants-anon-step-05-write-bit~1]
        self._require(ClaimStep.database_eligibility)
        if self._branch() not in NATIVE_BRANCHES:
            raise FreeGrantError("only a native branch writes a per-device bit")
        self._record(ClaimStep.native_bit_write)
        self.vendor_calls += 1
        write = adapter.write_claimed(AuthOperation.claim_anonymous_grant, material, ledger)
        assert_grant_row_permitted(write)
        return write

    def activate(self,
                 *,
                 user_id: UUID,
                 grant_id: UUID,
                 tier_id: str,
                 transaction: object,
                 locks: LockLedger,
                 reconfirm: Callable[[], bool],
                 challenge: ChallengeGate,
                 write: DeviceBitWrite | None = None,
                 web_account: WebGateAccount | None = None,
                 index: IdpAccountAliasIndex | None = None,
                 identity_row: ExternalIdentityRow | None = None,
                 context: ExecutionContext = CLAIM_EXECUTION_CONTEXT,
                 now: datetime | None = None) -> ActivatedGrant:
        """One activation transaction: the `core.access_grants` row with
        `source = 'anonymous_device_grant'`, the configured free tier and `status = 'active'`; the
        `core.access_grants_anti_abuse` row for the anonymous source, carrying
        `native_claim_provider` only for native rows and `idp_account_hash` with its key version
        only for web rows; the platform in audit detail and never in `source`; an anonymous native
        claimant's now-verified `native_claim_platform` pin; the `core.user_monthly_usage` row; the
        consumption of the challenge this attempt claimed; and the success audit.

        It is entered only after the confirmed native write, or after the web gates pass, and it
        re-resolves and locks the current user, identity and live grant set before reconfirming
        them.

        A rejection taken inside this transaction consumes the claimed challenge too, atomically
        with its own rejection audit: a claimed challenge is dead whatever later check failed.
        """
        # [impl->req~grants-anon-rule-activation-transaction~1]
        # [impl->req~grants-anon-rule-reconfirm-in-transaction~1]
        # [impl->req~grants-anon-rule-uncancellable-context~1]
        # [impl->req~grants-anon-step-06-activation-transaction~1]
        # [impl->req~grants-grant-ordering-two-ledgers~2]
        branch = self._branch()
        self._require(ClaimStep.database_eligibility)
        if branch in NATIVE_BRANCHES:
            self._require(ClaimStep.native_bit_write)
        self._record(ClaimStep.activation)
        # The native read-write-activate sequence runs where a client disconnect cannot cancel it.
        assert_execution_context(context)
        try:
            return self._activate(user_id=user_id, grant_id=grant_id, tier_id=tier_id,
                                  transaction=transaction, locks=locks, reconfirm=reconfirm,
                                  challenge=challenge, write=write, web_account=web_account,
                                  index=index, identity_row=identity_row, branch=branch, now=now)
        except (ClaimRejection, FreeGrantRejected) as rejection:
            # This attempt holds the claim, so its challenge is consumed exactly once here —
            # atomically with the rejection audit — however late the check that failed was.
            # [impl->req~grants-anon-rule-activation-transaction~1]
            # [impl->req~shared-claimed-challenge-is-dead~1]
            challenge.consume()
            rejection.audit = terminal_event(
                AttemptPhase.business, rejection.result,
                operation=AuthOperation.claim_anonymous_grant,
                details={"verification": {"claim_branch": str(branch)},
                         "failure": {"stage": str(ClaimStep.activation)}})
            raise

    def _activate(self, *,
                  user_id: UUID,
                  grant_id: UUID,
                  tier_id: str,
                  transaction: object,
                  locks: LockLedger,
                  reconfirm: Callable[[], bool],
                  challenge: ChallengeGate,
                  write: DeviceBitWrite | None,
                  web_account: WebGateAccount | None,
                  index: IdpAccountAliasIndex | None,
                  identity_row: ExternalIdentityRow | None,
                  branch: ClaimBranch,
                  now: datetime | None) -> ActivatedGrant:
        """The transaction's own body. Every rejection it raises leaves through `activate`, which
        consumes the claimed challenge on the way out."""
        assert_no_enrolled_key()
        if not tier_id:
            raise FreeGrantError("the grant names the configured free tier")
        if branch in NATIVE_BRANCHES:
            assert_native_claim_written_before_grant(
                native_claim_written=bool(write is not None and write.confirmed),
                same_attempt=True)
            assert_grant_row_permitted(write)
        # Inside the transaction, re-resolve and re-confirm the live state before committing.
        if not reconfirm():
            raise ClaimRejection(AuthEventResult.policy_rejected,
                                 "the live state no longer satisfies the claim's rules")
        source, platform_detail = anonymous_platform_detail(branch)
        locks.lock_user(user_id)
        lock_grant_set(locks, [grant_id])
        # Under the lock: the user and identity are still active, the identity is still the same
        # identity the gate ran against, and the free-grant-consumed marker is still unset.
        # [impl->req~grants-anon-step-06-activation-transaction~1]
        if identity_row is not None:
            reconfirm_claimant(identity_row, branch, web_account=web_account)
        grant: dict[str, Any] = {
            "id": grant_id,
            "user_id": user_id,
            "tier_id": tier_id,
            "source": source,
            "status": AccessGrantStatus.active,
            "subscription_id": None,
        }
        assert_billing_separation(source, None)
        assert_grant_columns_entitlement_only(grant)
        platform = BRANCH_PLATFORM[branch] if branch in NATIVE_BRANCHES else None
        # An anonymous native claimant's `native_claim_platform` is pinned here: the device
        # attestation has verified and the vendor has confirmed the write, so this is the point
        # the identity record takes the pin, in the transaction that commits the grant.
        # [impl->req~grants-branch-pinning-and-shared-admission~1]
        pinned: ExternalIdentityRow | None = identity_row
        if identity_row is not None and branch in NATIVE_BRANCHES:
            pinned = pin_native_platform(identity_row, branch, attestation_verified=True)
        alias: DerivedValue | None = None
        if branch is ClaimBranch.web:
            if web_account is None or index is None:
                raise FreeGrantError("a web row carries its derived idp_account_hash")
            account = ProviderAccount(provider=web_account.provider,
                                      provider_uid=web_account.canonical_provider_account_id)
            # Resolve-or-create the canonical `core.provider_accounts` row, then insert the
            # `web_anonymous_gate` consumption row. A conflict on the stable provider UID rolls the
            # transaction back, audits `anti_abuse_already_claimed` and surfaces
            # `device_grant_exhausted` — never `account_already_claimed`, which belongs to the
            # registered gate.
            # [impl->req~grants-anon-step-07-insert-rows~1]
            index.register(account)
            try:
                alias = consume_free_grant_gate(index, account,
                                                GateConsumptionKind.web_anonymous_gate, grant_id,
                                                transaction=transaction,
                                                grant_transaction=transaction)
            except GateAlreadyConsumedError as conflict:
                raise ClaimRejection(
                    conflict.result,
                    "this provider account already consumed the web anonymous gate") from None
        anti_abuse = free_grant_anti_abuse_row(
            grant_id=grant_id, source=source, platform=platform,
            idp_account_hash=alias.digest if alias is not None else None,
            idp_account_hash_key_version=alias.key_version if alias is not None else None,
            created_at=now, grant_columns=grant)
        # The claimant identity's permanent free-grant-consumed marker, set in the transaction that
        # commits the grant and never cleared.
        # [impl->req~grants-anon-step-07-insert-rows~1]
        if pinned is not None:
            pinned = mark_free_grant_consumed(pinned, now=now if now is not None
                                              else datetime.now(UTC),
                                              grant_transaction=transaction,
                                              marker_transaction=transaction)
        usage = free_grant_usage_row(grant_id, transaction=transaction, now=now)
        assert_same_transaction("claim_anonymous_grant",
                                [transaction, transaction, transaction, transaction])
        if not challenge.consume():
            raise FreeGrantError("the challenge this attempt claimed is consumed exactly once")
        audit = terminal_event(AttemptPhase.success, AuthEventResult.succeeded,
                               operation=AuthOperation.claim_anonymous_grant,
                               details={"verification": {"claim_branch": str(branch),
                                                         "platform": platform_detail},
                                        "mutation": {"grant_source": str(source),
                                                     "tier_id": tier_id}})
        return ActivatedGrant(grant=grant, anti_abuse=anti_abuse, usage=usage, audit=audit,
                              alias=alias, identity=pinned)

    def _branch(self) -> ClaimBranch:
        if self.branch is None:
            raise FreeGrantError("the branch is selected before the gate is read")
        return self.branch


def _carried_artifacts(evidence: ClaimEvidence) -> tuple[ProofArtifact, ...]:
    """The proof artifacts a request's evidence actually carries."""
    names = {
        "devicecheck_query_token": ProofArtifact.devicecheck_query_token,
        "devicecheck_update_token": ProofArtifact.devicecheck_update_token,
        "play_integrity_token": ProofArtifact.play_integrity_verdict,
        "turnstile_token": ProofArtifact.turnstile_token,
    }
    return tuple(artifact for name, artifact in names.items() if name in evidence.present())
