"""The three free-grant proof adapters, and the claim sequence they run inside.

Apple DeviceCheck gates the native iOS claims, Google Play Integrity / Play Integrity Device
Recall gates the native Android claims, and Cloudflare Turnstile is the web gate's bot check.
None of the three is identity: each one is per-device or per-request anti-abuse state held by a
vendor, read and written with the backend's own configured credentials, and every piece of it a
client hands us is untrusted request-body input that exists only to make those vendor calls.

The native claim sequence — verify material, read vendor state, pass the database eligibility
checks, write the vendor state, insert the grant — is mandatory and ordered on both platforms,
and the vendor's confirmed write is the gate the grant row sits behind.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.challenges import ClaimOutcome, claim_failure_result
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import NativeClaimPlatform
from nativespeaker.api.auth.invariants import DevicePlatform, ProofUse, assert_device_check_proof_use
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_endpoints import ClaimBranch, ProofArtifact
from nativespeaker.api.auth.proof_material import assert_anti_abuse_row_prohibitions
from nativespeaker.api.auth.schema_invariants import anti_abuse_evidence
from nativespeaker.api.auth.taxonomy import (
    REMEDIATIONS,
    RESULT_TO_CLASS,
    ClientErrorClass,
    register_client_class,
    remediation_for,
    surface,
)
from nativespeaker.api.exceptions import ErrorCode, ServiceError
from nativespeaker.api.ratelimit.config import TURNSTILE_ENTRY
from nativespeaker.api.ratelimit.keys import (
    AddressSource,
    GatewayResolvedAddress,
    canonical_client_ip_key,
)
from nativespeaker.api.ratelimit.limiter import LimitDecision, RateLimiter
from nativespeaker.api.ratelimit.ordering import (
    AdmissionLedger,
    DeviceBitCall,
    DeviceBitWrite,
    assert_grant_row_permitted,
)
from nativespeaker.api.ratelimit.providers import (
    DEVICE_BIT_PROVIDER_CALLS,
    AttemptPlan,
    ProviderCall,
    ProviderDampingConfig,
    attempt_plan,
    budget_entry_for,
    consume_budget_unit,
    device_bit_write,
)


class ProofAdapterError(RuntimeError):
    """An adapter was about to be used outside the contract this file fixes."""


# The device-bit write call each platform's confirmed write reports under. The budget entries
# themselves are `ratelimit/ordering.py`'s.
DEVICE_BIT_WRITE_CALL: dict[DevicePlatform, DeviceBitCall] = {
    DevicePlatform.ios: DeviceBitCall.devicecheck_write,
    DevicePlatform.android: DeviceBitCall.device_recall_write,
}


# --- Rejections ---------------------------------------------------------------------------------


# The native claim path's own post-barrier results, registered through the taxonomy's declared
# extension point. A vendor read that cannot be trusted and a vendor write that cannot be
# confirmed are verification-capacity failures, distinct from a client-supplied proof failure;
# the already-claimed device state is the grants domain's own registration in `invariants.py`.
# There is no second result-to-class registry here: every class is read back out of
# `taxonomy.surface`, so a renderer that goes through the shared registry sees the same mapping.
# [impl->req~proof-devicecheck-vendor-failure-audit-codes~1]
# [impl->req~proof-native-claim-vendor-read~1]
_CLAIM_PATH_CLASSES: dict[AuthEventResult, ClientErrorClass] = {
    AuthEventResult.native_claim_unavailable:
        ClientErrorClass.verification_temporarily_unavailable,
    AuthEventResult.native_claim_write_failed:
        ClientErrorClass.verification_temporarily_unavailable,
    # A device-bit budget guarding one of those vendor calls is exhausted: the same
    # verification-capacity class, and never a durable denial of the grant.
    # [impl->req~proof-native-claim-vendor-write-gate~1]
    AuthEventResult.devicecheck_read_budget_exhausted:
        ClientErrorClass.verification_temporarily_unavailable,
    AuthEventResult.devicecheck_write_budget_exhausted:
        ClientErrorClass.verification_temporarily_unavailable,
    AuthEventResult.device_recall_read_budget_exhausted:
        ClientErrorClass.verification_temporarily_unavailable,
    AuthEventResult.device_recall_write_budget_exhausted:
        ClientErrorClass.verification_temporarily_unavailable,
}

for _result, _class in _CLAIM_PATH_CLASSES.items():
    if _result not in RESULT_TO_CLASS:
        register_client_class(_result, _class.value, REMEDIATIONS[_class].http_status)


class ClaimRejection(ServiceError):
    """A free-grant claim rejection, carrying the audited internal result and the class that
    result surfaces as. The internal value never reaches the client."""

    def __init__(self, result: AuthEventResult, message: str = ""):
        client_class, status = surface(result)
        self.result = result
        self.error_code = client_class
        self.status_code = status
        super().__init__(message or str(result))


class ProofRejected(ClaimRejection):
    """Missing, withheld or malformed client-supplied vendor material."""

    def __init__(self, message: str = ""):
        # [impl->req~proof-devicecheck-client-material-proof-rejected~1]
        super().__init__(AuthEventResult.proof_malformed, message)


class NativeClaimUnavailable(ClaimRejection):
    """The vendor read failed, returned no bits, or returned a payload we cannot trust."""

    def __init__(self, message: str = ""):
        super().__init__(AuthEventResult.native_claim_unavailable, message)


class NativeClaimWriteFailed(ClaimRejection):
    """The vendor write failed, timed out, was cancelled, was ambiguous, or was never attempted."""

    def __init__(self, message: str = ""):
        super().__init__(AuthEventResult.native_claim_write_failed, message)


class DeviceGrantExhausted(ClaimRejection):
    """The vendor's per-device state says this device already consumed its grant slot."""

    def __init__(self, message: str = ""):
        super().__init__(AuthEventResult.native_claim_already_claimed, message)


# --- The anti-abuse layers of the anonymous device grant ----------------------------------------


class GateLayer(StrEnum):
    """What a successful anonymous free-credit grant must satisfy, per branch."""
    ios_devicecheck_state = "ios_devicecheck_state"
    android_device_recall_state = "android_device_recall_state"
    web_firebase_sign_in_gate = "web_firebase_sign_in_gate"


# The one gate each branch must satisfy. There is no second, weaker entry here, because there is
# no degraded verification mode to select.
# [impl->req~proof-anonymous-grant-no-degraded-mode~1]
BRANCH_GATE: dict[ClaimBranch, GateLayer] = {
    ClaimBranch.native_ios: GateLayer.ios_devicecheck_state,
    ClaimBranch.native_android: GateLayer.android_device_recall_state,
    ClaimBranch.web: GateLayer.web_firebase_sign_in_gate,
}

# The web branch's own three requirements, all of them mandatory together. The classifier and
# the stored-binding equality checks are `proof_endpoints.web_anonymous_grant_gate`'s; this
# names what the grant must satisfy, and per-provider-account uniqueness is enforced on the
# stable provider UID through the registry's gate-consumption rows.
WEB_GATE_REQUIREMENTS: tuple[str, ...] = (
    "stored_provider_is_google_or_apple",
    "complete_provider_data_passes_closed_classifier",
    "idp_account_hash_uniqueness_per_provider_account",
)

# No degraded, fallback or cached-positive mode exists for any branch, and the grant is gated by
# no attestation-key proof of possession and no per-attestation-key database uniqueness.
DEGRADED_VERIFICATION_MODES: frozenset[str] = frozenset()
ATTESTATION_KEY_UNIQUENESS_INDEXES: frozenset[str] = frozenset()


def anonymous_grant_gate_layer(branch: ClaimBranch, *,
                               degraded_mode: str | None = None,
                               attestation_key_proof: object = None) -> GateLayer:
    """Anonymous device grants have no degraded verification mode. A native grant must satisfy
    the platform's per-device device-check state; the web grant must satisfy the sign-in gate's
    stored-provider requirement, the closed classifier over the complete Firebase Admin
    `providerData` result with its stored-binding equality checks, and per-provider-account
    `idp_account_hash` uniqueness. The grant is not gated by attestation-key proof of possession
    and uses no per-attestation-key database uniqueness."""
    # [impl->req~proof-anonymous-grant-no-degraded-mode~1]
    if degraded_mode is not None or DEGRADED_VERIFICATION_MODES:
        raise ProofAdapterError(f"there is no degraded verification mode {degraded_mode}")
    if attestation_key_proof is not None or ATTESTATION_KEY_UNIQUENESS_INDEXES:
        raise ProofAdapterError("the grant is gated by no attestation-key proof of possession")
    layer = BRANCH_GATE.get(branch)
    if layer is None:
        raise ProofAdapterError(f"{branch} is no anonymous free-grant branch")
    return layer


def web_gate_requirements() -> tuple[str, ...]:
    """The web branch's three mandatory requirements. A failed, indeterminate, invalid-shape or
    non-matching Admin lookup denies the free grant and nothing else, and a failed or
    indeterminate lookup is never read as an empty, invalid-shape or non-matching result: that
    scoping and its `firebase_lookup_unavailable` audit result are
    `proof_endpoints.web_anonymous_grant_gate`'s, and this file adds no second rule."""
    # [impl->req~proof-anonymous-grant-no-degraded-mode~1]
    return WEB_GATE_REQUIREMENTS


class ClaimState(StrEnum):
    """The per-device claim states the two native free-grant operations use. They are distinct:
    neither operation can read or write the other's state."""
    anonymous_device_grant_claimed = "anonymous_device_grant_claimed"
    registered_account_grant_claimed = "registered_account_grant_claimed"


# The per-device claim state each native free-grant operation uses.
# [impl->req~proof-distinct-per-device-claim-states~1]
OPERATION_CLAIM_STATE: dict[AuthOperation, ClaimState] = {
    AuthOperation.claim_anonymous_grant: ClaimState.anonymous_device_grant_claimed,
    AuthOperation.claim_registered_grant: ClaimState.registered_account_grant_claimed,
}

NATIVE_CLAIM_OPERATIONS: frozenset[AuthOperation] = frozenset(OPERATION_CLAIM_STATE)


def claim_state_for(operation: AuthOperation) -> ClaimState:
    """The two native free-grant operations use distinct per-device claim states."""
    # [impl->req~proof-distinct-per-device-claim-states~1]
    state = OPERATION_CLAIM_STATE.get(operation)
    if state is None:
        raise ProofAdapterError(f"{operation} is no native free-grant claim")
    if len(set(OPERATION_CLAIM_STATE.values())) != len(OPERATION_CLAIM_STATE):
        raise ProofAdapterError("the two native claims share a per-device claim state")
    return state


class DeviceCheckBit(StrEnum):
    """The two persistent per-device per-team bits DeviceCheck exposes, named as Apple's API
    names them."""
    # [impl->req~proof-devicecheck-two-bits~1]
    bit0 = "bit0"
    bit1 = "bit1"


# This specification's bit assignment: `bit0` is the anonymous device grant's claimed state and
# `bit1` is the registered account grant's.
# [impl->req~proof-devicecheck-bit-assignment~1]
# [impl->req~proof-ios-devicecheck-bit-split~1]
DEVICECHECK_BIT_MEANING: dict[DeviceCheckBit, ClaimState] = {
    DeviceCheckBit.bit0: ClaimState.anonymous_device_grant_claimed,
    DeviceCheckBit.bit1: ClaimState.registered_account_grant_claimed,
}

OPERATION_BIT: dict[AuthOperation, DeviceCheckBit] = {
    operation: bit
    for operation, state in OPERATION_CLAIM_STATE.items()
    for bit, meaning in DEVICECHECK_BIT_MEANING.items() if meaning is state
}


def devicecheck_bit_for(operation: AuthOperation) -> DeviceCheckBit:
    """`claim_anonymous_grant` reads and writes only `bit0`; `claim_registered_grant` reads and
    writes only `bit1`."""
    # [impl->req~proof-ios-devicecheck-bit-split~1]
    # [impl->req~proof-devicecheck-bit-assignment~1]
    bit = OPERATION_BIT.get(operation)
    if bit is None:
        raise ProofAdapterError(f"{operation} is assigned no DeviceCheck bit")
    if DEVICECHECK_BIT_MEANING[bit] is not claim_state_for(operation):
        raise ProofAdapterError(f"{bit} does not carry {operation}'s claim state")
    return bit


def other_devicecheck_bit(bit: DeviceCheckBit) -> DeviceCheckBit:
    """The bit this operation must leave alone."""
    # [impl->req~proof-ios-devicecheck-bit-split~1]
    return DeviceCheckBit.bit1 if bit is DeviceCheckBit.bit0 else DeviceCheckBit.bit0


class RecallState(StrEnum):
    """The distinct vendor-provided Device Recall states, one per native free-grant operation."""
    anonymous_device_grant_recall = "anonymous_device_grant_recall"
    registered_account_grant_recall = "registered_account_grant_recall"


# Android's distinct recall states, one per operation.
# [impl->req~proof-android-recall-state-split~1]
OPERATION_RECALL_STATE: dict[AuthOperation, RecallState] = {
    AuthOperation.claim_anonymous_grant: RecallState.anonymous_device_grant_recall,
    AuthOperation.claim_registered_grant: RecallState.registered_account_grant_recall,
}


def recall_state_for(operation: AuthOperation) -> RecallState:
    """The backend uses distinct vendor-provided recall states to determine whether the anonymous
    or the registered device grant has already been claimed."""
    # [impl->req~proof-android-recall-state-split~1]
    state = OPERATION_RECALL_STATE.get(operation)
    if state is None:
        raise ProofAdapterError(f"{operation} has no Device Recall state")
    if len(set(OPERATION_RECALL_STATE.values())) != len(OPERATION_RECALL_STATE):
        raise ProofAdapterError("the two native claims share a recall state")
    return state


@dataclass(frozen=True, slots=True)
class AppleCredentials:
    """The backend's own configured Apple credentials for the DeviceCheck server-to-server API."""
    team_id: str
    key_id: str
    private_key: SecretStr
    production: bool = True


@dataclass(frozen=True, slots=True)
class GoogleCredentials:
    """The backend's own configured Google credentials for Play Integrity and Device Recall."""
    package_name: str
    service_account_email: str
    private_key: SecretStr
    cloud_project_number: int = 0


def assert_configured_credentials(credentials: AppleCredentials | GoogleCredentials,
                                  *, client_supplied_state: object = None) -> None:
    """The backend queries and updates device-check state with configured Apple or Google
    credentials, and never accepts client-supplied device-check state as trusted fact."""
    # [impl->req~proof-vendor-state-via-configured-credentials~1]
    if client_supplied_state is not None:
        raise ProofAdapterError("client-supplied device-check state is not trusted fact")
    match credentials:
        case AppleCredentials(team_id=team, key_id=key, private_key=secret):
            missing = not team or not key or not secret.get_secret_value()
        case GoogleCredentials(package_name=package, service_account_email=account,
                               private_key=secret):
            missing = not package or not account or not secret.get_secret_value()
        case _:
            raise ProofAdapterError("device-check state is read with configured credentials")
    if missing:
        raise ProofAdapterError("the configured vendor credentials are incomplete")


def untrusted_vendor_material(material: Mapping[str, Any],
                              *,
                              use: ProofUse = ProofUse.anti_abuse_gate,
                              resolves_account: object = None) -> Mapping[str, Any]:
    """Client-supplied device-check or integrity material is untrusted request-body input used
    only for the vendor read and write. It is never an identity token and never resolves which
    account a request belongs to."""
    # [impl->req~proof-client-vendor-material-untrusted~1]
    # [impl->req~proof-ios-tokens-untrusted~1]
    assert_device_check_proof_use(use)
    if resolves_account is not None:
        raise ProofAdapterError("vendor material resolves no account")
    for name in ("issuer", "subject", "user_id", "uid", "account_id"):
        if name in material:
            raise ProofAdapterError(f"{name} is not carried by vendor anti-abuse material")
    return material


# --- The mandatory native claim sequence --------------------------------------------------------


class NativeClaimStep(StrEnum):
    """The five steps of the native claim, in the one order they may run in."""
    verify_vendor_material = "verify_vendor_material"
    vendor_read = "vendor_read"
    database_eligibility = "database_eligibility"
    vendor_write = "vendor_write"
    insert_grant = "insert_grant"


# The sequence itself. It is mandatory on both platforms and has no alternative ordering.
# [impl->req~proof-native-claim-sequence-mandatory~1]
NATIVE_CLAIM_SEQUENCE: tuple[NativeClaimStep, ...] = tuple(NativeClaimStep)


# The device-bit provider call each platform's read and write is metered by, and the internal
# result an exhausted budget takes. The budget entries themselves are `ratelimit/providers.py`'s.
DEVICE_BIT_BUDGET_EXHAUSTED: dict[ProviderCall, AuthEventResult] = {
    ProviderCall.devicecheck_read: AuthEventResult.devicecheck_read_budget_exhausted,
    ProviderCall.devicecheck_write: AuthEventResult.devicecheck_write_budget_exhausted,
    ProviderCall.device_recall_read: AuthEventResult.device_recall_read_budget_exhausted,
    ProviderCall.device_recall_write: AuthEventResult.device_recall_write_budget_exhausted,
}


@dataclass(frozen=True, slots=True)
class VendorBudget:
    """The second-layer damping a claim's outbound vendor calls run under: the shared counter
    storage the unit is taken from, the configured per-call attempt plan, and the admission
    ledger that records the read-write-insert order. All of it is `ratelimit/`'s; this is the
    handle the claim carries so every dispatch can charge it."""
    limiter: RateLimiter
    damping: ProviderDampingConfig
    key: str
    idempotency_key: str = "native-claim"
    endpoint_admission_passed: bool = True
    admission: AdmissionLedger | None = None


class NativeClaimLedger:
    """One claim's step order, and the point every outbound vendor call goes through. Every
    adapter call records its step here and the ledger refuses the moment a step runs out of
    order, is skipped, or runs twice."""

    def __init__(self, budget: VendorBudget | None = None) -> None:
        self.steps: list[NativeClaimStep] = []
        self.budget = budget
        self.provider_calls: list[ProviderCall] = []

    def dispatch(self, call: ProviderCall, run: Callable[[AttemptPlan | None], Any]) -> Any:
        """Dispatch one outbound vendor call under its own budget. The unit is checked and
        consumed immediately before the dispatch, the admission ledger records the call in the
        read-then-write order it enforces, and the per-attempt and connect timeouts, the attempt
        cap and the idempotency key come from the configured plan. An exhausted budget refuses
        the call with that budget's own internal result rather than letting a vendor outage fan
        out unbounded."""
        # [impl->req~proof-native-claim-vendor-write-gate~1]
        # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
        plan = self._charge(call)
        outcome = run(plan)
        self._record_call(call)
        return outcome

    def dispatch_write(self, call: ProviderCall,
                       confirm: Callable[[AttemptPlan | None], bool]) -> DeviceBitWrite:
        """The device-bit write, charged and then performed inline, returned as the vendor's
        confirmation. `ratelimit/providers.device_bit_write` is what builds it, so the
        load-bearing-write rule keeps one implementation."""
        # [impl->req~proof-native-claim-vendor-write-gate~1]
        plan = self._charge(call)
        if self.budget is None:
            write = DeviceBitWrite(call=DEVICE_BIT_PROVIDER_CALLS[call],
                                   confirmed=bool(confirm(plan)))
        else:
            write = device_bit_write(self.budget.damping, call, dispatch=confirm,
                                     idempotency_key=self.budget.idempotency_key,
                                     endpoint_admission_passed=True, budget_unit_consumed=True)
        self._record_call(call)
        return write

    def _charge(self, call: ProviderCall) -> AttemptPlan | None:
        """One unit of this call's global provider budget, taken immediately before dispatch."""
        # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
        self.provider_calls.append(call)
        if self.budget is None:
            return None
        bit = DEVICE_BIT_PROVIDER_CALLS.get(call)
        decision = consume_budget_unit(
            self.budget.limiter, call, self.budget.key,
            endpoint_admission_passed=self.budget.endpoint_admission_passed)
        if self.budget.admission is not None and bit is not None:
            self.budget.admission.check_device_bit_budget(bit, allowed=decision.allowed)
        if not decision.allowed:
            result = DEVICE_BIT_BUDGET_EXHAUSTED.get(call)
            if result is None:
                raise NativeClaimUnavailable(f"{budget_entry_for(call)} is exhausted")
            raise ClaimRejection(result, f"{budget_entry_for(call)} is exhausted")
        return attempt_plan(self.budget.damping, call,
                            idempotency_key=self.budget.idempotency_key,
                            endpoint_admission_passed=True, budget_unit_consumed=True)

    def _record_call(self, call: ProviderCall) -> None:
        bit = DEVICE_BIT_PROVIDER_CALLS.get(call)
        if self.budget is not None and self.budget.admission is not None and bit is not None:
            self.budget.admission.vendor_device_bit_call(bit)

    # [impl->req~proof-native-claim-sequence-mandatory~1]
    def record(self, step: NativeClaimStep) -> None:
        position = len(self.steps)
        if position >= len(NATIVE_CLAIM_SEQUENCE) or NATIVE_CLAIM_SEQUENCE[position] is not step:
            raise ProofAdapterError(
                f"{step} cannot run after {self.steps}: the native claim sequence is mandatory")
        self.steps.append(step)

    def completed(self, step: NativeClaimStep) -> bool:
        return step in self.steps

    def require(self, step: NativeClaimStep) -> None:
        if not self.completed(step):
            raise ProofAdapterError(f"{step} has not run yet")


@dataclass(frozen=True, slots=True)
class IosClaimMaterial:
    """What an iOS claim request carries up front: two separate per-transaction DeviceCheck
    tokens, one for the server-to-server query and one for the update."""
    query_token: str | None
    update_token: str | None


@dataclass(frozen=True, slots=True)
class AndroidClaimMaterial:
    """What an Android claim request carries: one Play Integrity token covering both the recall
    read and the recall write."""
    integrity_token: str | None
    package_name: str | None = None
    signing_certificate_digest: str | None = None
    release: str | None = None


ClaimMaterial = IosClaimMaterial | AndroidClaimMaterial


class DeviceStateAdapter(Protocol):
    """What the native claim sequence needs from a platform adapter."""

    platform: DevicePlatform

    def verify_material(self, operation: AuthOperation, material: Any,
                        ledger: NativeClaimLedger) -> None: ...

    def read_claimed(self, operation: AuthOperation, material: Any,
                     ledger: NativeClaimLedger) -> bool: ...

    def write_claimed(self, operation: AuthOperation, material: Any,
                      ledger: NativeClaimLedger) -> DeviceBitWrite: ...


# The operations allowed to touch vendor per-device state at all. The upgrade flip, subscription
# restore and the read-only account and profile reads are not among them.
# [impl->req~proof-two-authoritative-ledgers~1]
VENDOR_STATE_TOUCHING_OPERATIONS: frozenset[AuthOperation] = NATIVE_CLAIM_OPERATIONS


def assert_vendor_state_access(operation: AuthOperation) -> None:
    """The native claim sequence is the only place vendor per-device state is read or written."""
    # [impl->req~proof-two-authoritative-ledgers~1]
    if operation not in VENDOR_STATE_TOUCHING_OPERATIONS:
        raise ProofAdapterError(f"{operation} never reads or writes vendor per-device state")


@dataclass(frozen=True, slots=True)
class NativeClaimOutcome:
    """What one completed native claim produced."""
    operation: AuthOperation
    platform: DevicePlatform
    state: ClaimState
    write: DeviceBitWrite
    grant_id: UUID


def native_claim(adapter: DeviceStateAdapter,
                 operation: AuthOperation,
                 material: Any,
                 *,
                 database_eligibility: Callable[[], bool],
                 insert_grant: Callable[[], UUID],
                 challenge_claimed: bool = True,
                 ledger: NativeClaimLedger | None = None) -> NativeClaimOutcome:
    """The mandatory native claim sequence, on both platforms.

    First verify the device-check or integrity proof and all client-supplied vendor material the
    claim requires; missing, withheld or malformed write material fails before any vendor write
    and before any grant exists. Next read the vendor's per-device state: a read failure fails
    closed and an already-claimed state returns `device_grant_exhausted` with no grant created.
    Only after the read reports an unclaimed device do the per-user database eligibility checks
    run, and only after they pass is the vendor claimed bit or recall state written as a
    mandatory pre-grant gate. Only once the vendor confirms that write is the grant row inserted,
    idempotently.
    """
    # [impl->req~proof-native-claim-sequence-mandatory~1]
    ledger = ledger if ledger is not None else NativeClaimLedger()
    assert_vendor_state_access(operation)
    state = claim_state_for(operation)
    if not challenge_claimed:
        # Both the challenge's validation and its claim run before any vendor call.
        # [impl->req~proof-claim-challenge-mechanics~1]
        raise ProofAdapterError("the operation challenge is claimed before any vendor call")

    adapter.verify_material(operation, material, ledger)

    # [impl->req~proof-native-claim-vendor-read~1]
    if adapter.read_claimed(operation, material, ledger):
        raise DeviceGrantExhausted(f"{state} is already set for this device")

    # [impl->req~proof-native-claim-database-eligibility~1]
    ledger.record(NativeClaimStep.database_eligibility)
    if not database_eligibility():
        # An ineligible caller is an ordinary per-user denial owned by the grants domain, not a
        # contract violation: it audits under its own internal result and surfaces through the
        # shared taxonomy, never as the `internal_error` a bare `RuntimeError` would produce.
        # An eligibility check with a more specific result of its own raises that itself and
        # this path propagates it untouched.
        raise ClaimRejection(AuthEventResult.policy_rejected,
                             "the per-user database eligibility checks failed")

    # [impl->req~proof-native-claim-vendor-write-gate~1]
    write = adapter.write_claimed(operation, material, ledger)
    # The one guard for "a grant row sits behind a vendor-confirmed write" lives in
    # `ratelimit/ordering.py`; this path calls it rather than restating the rule.
    assert_grant_row_permitted(write)

    # [impl->req~proof-native-claim-insert-grant~1]
    ledger.record(NativeClaimStep.insert_grant)
    grant_id = insert_grant()
    return NativeClaimOutcome(operation=operation, platform=adapter.platform, state=state,
                              write=write, grant_id=grant_id)


# --- The two authoritative ledgers ---------------------------------------------------------------


class LedgerAuthority(StrEnum):
    """What each of the two authoritative ledgers is authoritative for."""
    user_received_a_grant = "user_received_a_grant"
    device_consumed_its_slot = "device_consumed_its_slot"


# [impl->req~proof-two-authoritative-ledgers~1]
LEDGER_AUTHORITY: dict[str, LedgerAuthority] = {
    "database": LedgerAuthority.user_received_a_grant,
    "vendor_per_device_state": LedgerAuthority.device_consumed_its_slot,
}

# The vendor's per-device state is load-bearing authority, never a cache, so nothing may treat
# it as one and nothing clears a claimed bit automatically.
VENDOR_STATE_IS_A_CACHE: bool = False
AUTOMATIC_BIT_CLEARERS: frozenset[str] = frozenset()

# The narrow concurrent same-device race this enforcement accepts, and its bound.
MAX_EXTRA_GRANTS_PER_SAME_DEVICE_RACE: int = 1

# A stranded device slot — a crash after a confirmed vendor write but before the grant insert,
# or a lost write acknowledgment — is remediated with a `manual`-source grant, never by granting
# around the gate.
STRANDED_SLOT_REMEDIATION: AccessGrantSource = AccessGrantSource.manual


def ledger_authority(ledger: str) -> LedgerAuthority:
    """The database is authoritative for whether a user received a grant; the vendor's per-device
    state is the load-bearing authority for whether the physical device consumed its grant slot,
    and is not a cache."""
    # [impl->req~proof-two-authoritative-ledgers~1]
    if VENDOR_STATE_IS_A_CACHE or AUTOMATIC_BIT_CLEARERS:
        raise ProofAdapterError("vendor claimed bits are never cleared automatically")
    authority = LEDGER_AUTHORITY.get(ledger)
    if authority is None:
        raise ProofAdapterError(f"{ledger} is no authoritative free-grant ledger")
    return authority


def assert_same_device_race_bounded(extra_grants: int) -> None:
    """Per-device enforcement accepts the narrow concurrent same-device race in which both
    attempts read the unclaimed state, bounded to at most one extra grant."""
    # [impl->req~proof-two-authoritative-ledgers~1]
    if extra_grants > MAX_EXTRA_GRANTS_PER_SAME_DEVICE_RACE:
        raise ProofAdapterError("the same-device race is bounded to at most one extra grant")


def stranded_slot_remediation(source: AccessGrantSource = STRANDED_SLOT_REMEDIATION
                              ) -> AccessGrantSource:
    """A device slot stranded by a confirmed write whose grant insert never happened is
    remediated through a grant whose source is `manual`."""
    # [impl->req~proof-two-authoritative-ledgers~1]
    if source is not AccessGrantSource.manual:
        raise ProofAdapterError("the accepted over-enforcement is remediated with a manual grant")
    return source


class ExecutionContext(StrEnum):
    """Where the vendor read-write-grant-insert sequence runs."""
    disconnect_shielded_task = "disconnect_shielded_task"
    request_cancellation_scope = "request_cancellation_scope"


# The one context the sequence may run in: a client disconnect must not abort it mid-flight.
# [impl->req~proof-native-claim-retry-and-execution-context~1]
CLAIM_EXECUTION_CONTEXT: ExecutionContext = ExecutionContext.disconnect_shielded_task

# The context is a legitimate-user protection, not a security control, and the fail-closed
# vendor behavior gates the free grant alone.
FAIL_CLOSED_GATES: frozenset[AuthOperation] = NATIVE_CLAIM_OPERATIONS


def assert_execution_context(context: ExecutionContext) -> None:
    """The vendor read-write-grant-insert sequence runs in an execution context a client
    disconnect cannot abort mid-flight."""
    # [impl->req~proof-native-claim-retry-and-execution-context~1]
    if context is not CLAIM_EXECUTION_CONTEXT:
        raise ProofAdapterError(f"{context} lets a client disconnect abort the claim mid-flight")


def retry_after_failed_claim(material: Any, *, previous_material: Any = None) -> Any:
    """A failed native claim is retried only as a whole new claim with fresh vendor material."""
    # [impl->req~proof-native-claim-retry-and-execution-context~1]
    if previous_material is not None and material == previous_material:
        raise ProofAdapterError("a retry is a whole new claim with fresh vendor material")
    return material


def assert_fail_closed_scope(operation: AuthOperation) -> None:
    """All fail-closed vendor behavior gates only the free grant: it never gates login or paid
    subscription access."""
    # [impl->req~proof-native-claim-retry-and-execution-context~1]
    if operation not in FAIL_CLOSED_GATES:
        raise ProofAdapterError(f"fail-closed vendor behavior never gates {operation}")


# --- The anonymous device grant's anti-abuse row -------------------------------------------------


# The native branch each platform records on the row.
NATIVE_CLAIM_PROVIDER: dict[DevicePlatform, NativeClaimPlatform] = {
    DevicePlatform.ios: NativeClaimPlatform.ios_devicecheck,
    DevicePlatform.android: NativeClaimPlatform.android_play_integrity,
}


def anonymous_device_grant_row(*,
                               grant_id: UUID,
                               platform: DevicePlatform | None = None,
                               idp_account_hash: bytes | None = None,
                               idp_account_hash_key_version: int | None = None,
                               created_at: datetime | None = None,
                               extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One `core.access_grants_anti_abuse` row with `grant_source = 'anonymous_device_grant'`.
    It records the non-secret grant metadata whose row shape `06-schema-reference.md` defines —
    the native branch, or the web gate's IDP-account evidence — and never an attestation-key-
    derived identifier or attestation provider."""
    # [impl->req~proof-anonymous-device-grant-row-contents~1]
    native_claim_provider = NATIVE_CLAIM_PROVIDER.get(platform) if platform is not None else None
    if platform is not None and native_claim_provider is None:
        raise ProofAdapterError(f"{platform} is no native anonymous-grant branch")
    row: dict[str, Any] = {
        "grant_id": grant_id,
        "grant_source": AccessGrantSource.anonymous_device_grant,
        "native_claim_provider": native_claim_provider,
        "idp_account_hash": idp_account_hash,
        "idp_account_hash_key_version": idp_account_hash_key_version,
        "created_at": created_at if created_at is not None else datetime.now(UTC),
    }
    row.update(extra or {})
    # The row shape and its per-source evidence contract stay the schema file's; this asks that
    # owner whether the shape is one it allows.
    anti_abuse_evidence(grant_source=AccessGrantSource.anonymous_device_grant,
                        native_claim_provider=native_claim_provider,
                        idp_account_hash=idp_account_hash,
                        idp_account_hash_key_version=idp_account_hash_key_version)
    # No attestation-key-derived identifier, no attestation provider, no raw device material.
    assert_anti_abuse_row_prohibitions(row)
    return row


# --- The iOS proof adapter ------------------------------------------------------------------------


# What Apple DeviceCheck is on iOS, and what it is not. No iOS endpoint requires App Attest.
# [impl->req~proof-ios-devicecheck-role~1]
IOS_DEVICE_STATE: str = "apple_devicecheck"
APP_ATTEST_REQUIRING_OPERATIONS: frozenset[AuthOperation] = frozenset()


def devicecheck_role(use: ProofUse = ProofUse.anti_abuse_gate) -> str:
    """For iOS, Apple DeviceCheck is the per-device state used for anonymous and registered
    free-grant anti-abuse. It is not an identity token, ownership credential, recovery
    credential, upgrade credential, or account-resolution input, and no iOS endpoint requires
    App Attest."""
    # [impl->req~proof-ios-devicecheck-role~1]
    assert_device_check_proof_use(use)
    if APP_ATTEST_REQUIRING_OPERATIONS:
        raise ProofAdapterError("no iOS endpoint requires App Attest")
    return IOS_DEVICE_STATE


class DeviceCheckEnvironment(StrEnum):
    """Apple's two DeviceCheck environments."""
    development = "development"
    production = "production"


# In production the backend accepts the production environment alone: a development token is
# never accepted there.
# [impl->req~proof-ios-devicecheck-mandatory~1]
PRODUCTION_ACCEPTED_ENVIRONMENTS: frozenset[DeviceCheckEnvironment] = frozenset(
    {DeviceCheckEnvironment.production})

# DeviceCheck participation on iOS is unconditional and mandatory on both claims: there is no
# availability gate and no operation that opts out.
DEVICECHECK_EXEMPT_OPERATIONS: frozenset[AuthOperation] = frozenset()


class DeviceCheckTransport(Protocol):
    """The DeviceCheck server-to-server API, as this adapter uses it."""

    def query_two_bits(self, *, query_token: str, team_id: str,
                       environment: DeviceCheckEnvironment) -> Mapping[str, Any]: ...

    def update_two_bits(self, *, update_token: str, team_id: str,
                        environment: DeviceCheckEnvironment,
                        bits: Mapping[str, bool]) -> Mapping[str, Any]: ...


class DeviceCheckAdapter:
    """Apple DeviceCheck: two persistent per-device per-team bits, read and written by the
    backend with its own configured Apple credentials."""

    platform: DevicePlatform = DevicePlatform.ios

    def __init__(self, credentials: AppleCredentials, transport: DeviceCheckTransport,
                 *, environment: DeviceCheckEnvironment = DeviceCheckEnvironment.production):
        assert_configured_credentials(credentials)
        # Production accepts only the production DeviceCheck environment.
        # [impl->req~proof-ios-devicecheck-mandatory~1]
        if credentials.production and environment not in PRODUCTION_ACCEPTED_ENVIRONMENTS:
            raise ProofAdapterError(f"production never accepts {environment} DeviceCheck tokens")
        self._credentials = credentials
        self._transport = transport
        self._environment = environment

    @property
    def team_id(self) -> str:
        """The DeviceCheck transaction uses the configured Apple team identifier."""
        # [impl->req~proof-devicecheck-configured-team-id~1]
        return self._credentials.team_id

    def _assert_mandatory(self, operation: AuthOperation) -> None:
        """DeviceCheck participation is unconditional and mandatory on every iOS claim."""
        # [impl->req~proof-ios-devicecheck-mandatory~1]
        if operation not in NATIVE_CLAIM_OPERATIONS or operation in DEVICECHECK_EXEMPT_OPERATIONS:
            raise ProofAdapterError(f"{operation} has no DeviceCheck bit to read or update")
        assert_vendor_state_access(operation)

    def verify_material(self, operation: AuthOperation, material: IosClaimMaterial,
                        ledger: NativeClaimLedger) -> None:
        """Each claim request carries up front separate per-transaction DeviceCheck tokens for
        the server-to-server query and the update; the query token is never assumed reusable for
        the update. Withheld, missing or malformed update-token material fails here — before any
        vendor write and before any grant exists — as a client-supplied proof failure."""
        # [impl->req~proof-native-claim-verify-vendor-material~1]
        # [impl->req~proof-ios-separate-query-update-tokens~1]
        # [impl->req~proof-ios-missing-update-material-fails-early~1]
        # [impl->req~proof-devicecheck-client-material-proof-rejected~1]
        self._assert_mandatory(operation)
        ledger.record(NativeClaimStep.verify_vendor_material)
        if not isinstance(material, IosClaimMaterial):
            raise ProofRejected("an iOS claim carries DeviceCheck query and update tokens")
        query, update = material.query_token, material.update_token
        if not query or not str(query).strip():
            raise ProofRejected("the DeviceCheck query token is missing or malformed")
        if not update or not str(update).strip():
            raise ProofRejected("the DeviceCheck update token is missing or malformed")
        if query == update:
            raise ProofRejected("the query token is not reusable for the update")
        untrusted_vendor_material({"devicecheck_query_token": query,
                                   "devicecheck_update_token": update})

    def read_claimed(self, operation: AuthOperation, material: IosClaimMaterial,
                     ledger: NativeClaimLedger) -> bool:
        """Read the operation's assigned bit through the DeviceCheck server-to-server API.
        `bit0 = true` means already claimed and `bit0 = false`, including the never-set initial
        state, means unclaimed. A response that omits the bit values, is malformed, or fails
        backend integration authentication is `native_claim_unavailable`."""
        # [impl->req~proof-native-claim-vendor-read~1]
        # [impl->req~proof-devicecheck-bit0-read-semantics~1]
        # [impl->req~proof-devicecheck-vendor-failure-audit-codes~1]
        self._assert_mandatory(operation)
        ledger.require(NativeClaimStep.verify_vendor_material)
        ledger.record(NativeClaimStep.vendor_read)
        bit = devicecheck_bit_for(operation)
        assert_configured_credentials(self._credentials)

        def query(_plan: AttemptPlan | None) -> Any:
            try:
                return self._transport.query_two_bits(query_token=str(material.query_token),
                                                      team_id=self.team_id,
                                                      environment=self._environment)
            except Exception as exc:
                raise NativeClaimUnavailable(f"the DeviceCheck query failed: {exc}") from None

        # The read runs under its own budget unit, taken immediately before the dispatch.
        # [impl->req~proof-native-claim-vendor-write-gate~1]
        payload = ledger.dispatch(ProviderCall.devicecheck_read, query)
        if not isinstance(payload, Mapping):
            raise NativeClaimUnavailable("the DeviceCheck query returned a malformed payload")
        for name in (DeviceCheckBit.bit0, DeviceCheckBit.bit1):
            if str(name) not in payload:
                raise NativeClaimUnavailable(f"the DeviceCheck query omitted {name}")
        value = payload[str(bit)]
        if value is None:
            # The never-set initial state is unclaimed.
            # [impl->req~proof-devicecheck-bit0-read-semantics~1]
            return False
        if not isinstance(value, bool):
            raise NativeClaimUnavailable(f"{bit} came back as {type(value).__name__}")
        return value

    def write_claimed(self, operation: AuthOperation, material: IosClaimMaterial,
                      ledger: NativeClaimLedger) -> DeviceBitWrite:
        """Set the operation's assigned bit to `true` before any grant is created. The same
        DeviceCheck transaction must not modify the other bit, and only Apple's confirmed
        acknowledgment permits grant creation; a failed or ambiguous update is
        `native_claim_write_failed`."""
        # [impl->req~proof-native-claim-vendor-write-gate~1]
        # [impl->req~proof-devicecheck-bit0-write-before-grant~1]
        # [impl->req~proof-devicecheck-bit1-registered-claim~1]
        # [impl->req~proof-devicecheck-vendor-failure-audit-codes~1]
        self._assert_mandatory(operation)
        ledger.require(NativeClaimStep.database_eligibility)
        ledger.record(NativeClaimStep.vendor_write)
        bit = devicecheck_bit_for(operation)
        if not material.update_token:
            raise ProofRejected("the update token is required before any vendor write")
        assert_configured_credentials(self._credentials)
        bits = {str(bit): True}
        if str(other_devicecheck_bit(bit)) in bits:
            raise ProofAdapterError("the same transaction must not modify the other bit")

        def update(_plan: AttemptPlan | None) -> bool:
            try:
                acknowledgment = self._transport.update_two_bits(
                    update_token=str(material.update_token), team_id=self.team_id,
                    environment=self._environment, bits=bits)
            except Exception as exc:
                raise NativeClaimWriteFailed(f"the DeviceCheck update failed: {exc}") from None
            if not isinstance(acknowledgment, Mapping) or "acknowledged" not in acknowledgment:
                raise NativeClaimWriteFailed("the DeviceCheck update result is ambiguous")
            if acknowledgment["acknowledged"] is not True:
                raise NativeClaimWriteFailed("Apple did not acknowledge the DeviceCheck update")
            return True

        # Charged, dispatched inline and confirmed before any grant row exists.
        # [impl->req~proof-native-claim-vendor-write-gate~1]
        write = ledger.dispatch_write(ProviderCall.devicecheck_write, update)
        if write.call is not DEVICE_BIT_WRITE_CALL[DevicePlatform.ios]:
            raise ProofAdapterError("an iOS claim reports its write as the DeviceCheck write")
        return write


# --- The Android proof adapter ---------------------------------------------------------------------


# What Play Integrity / Device Recall is on Android, and what it is not. No Android endpoint
# requires a challenge-bound integrity proof.
# [impl->req~proof-android-play-integrity-role~1]
ANDROID_DEVICE_STATE: str = "play_integrity_device_recall"
CHALLENGE_BOUND_INTEGRITY_OPERATIONS: frozenset[AuthOperation] = frozenset()


def play_integrity_role(use: ProofUse = ProofUse.anti_abuse_gate) -> str:
    """For Android, Google Play Integrity / Play Integrity Device Recall is the per-device state
    used for anonymous and registered free-grant anti-abuse where Device Recall is available. It
    is not an identity token, ownership credential, recovery credential, upgrade credential, or
    account-resolution input, and no Android endpoint requires a challenge-bound integrity
    proof."""
    # [impl->req~proof-android-play-integrity-role~1]
    assert_device_check_proof_use(use)
    if CHALLENGE_BOUND_INTEGRITY_OPERATIONS:
        raise ProofAdapterError("no Android endpoint requires a challenge-bound integrity proof")
    return ANDROID_DEVICE_STATE


class ReleaseRecallPolicy(StrEnum):
    """How the checked-in server release policy classes one enumerated release."""
    device_recall_required = "device_recall_required"
    no_device_recall = "no_device_recall"


@dataclass(frozen=True, slots=True)
class ReleaseKey:
    """One enumerated release: package name, signing-certificate digest, and release."""
    package_name: str
    signing_certificate_digest: str
    release: str


class ReleasePolicyRegistry:
    """The checked-in server release policy: an enumeration by package name,
    signing-certificate digest and release, classing each release as `device_recall_required` or
    `no_device_recall`."""

    def __init__(self, entries: Mapping[ReleaseKey, ReleaseRecallPolicy] | None = None):
        self._entries: dict[ReleaseKey, ReleaseRecallPolicy] = dict(entries or {})

    def policy_for(self, key: ReleaseKey) -> ReleaseRecallPolicy:
        """An unrecognized, unenumerated release is rejected outright."""
        # [impl->req~proof-android-release-policy-enumeration~1]
        policy = self._entries.get(key)
        if policy is None:
            raise ProofRejected(f"{key.release} is not an enumerated release")
        return policy


def registered_claim_requires_recall(policy: ReleaseRecallPolicy,
                                     *, client_omitted_material: bool = False
                                     ) -> bool:
    """Device Recall is additionally mandatory on the registered claim only where the checked-in
    release policy requires it. Client omission of Play Integrity or Device Recall material never
    causes the server to select the no-recall branch."""
    # [impl->req~proof-android-release-policy-enumeration~1]
    if client_omitted_material:
        raise ProofRejected("omitted client material never selects the no-recall branch")
    return policy is ReleaseRecallPolicy.device_recall_required


class PlayIntegrityTransport(Protocol):
    """The Play Integrity and Device Recall surfaces this adapter uses."""

    def decode_verdict(self, *, integrity_token: str,
                       credentials: GoogleCredentials) -> Mapping[str, Any]: ...

    def write_recall(self, *, integrity_token: str, credentials: GoogleCredentials,
                     state: RecallState, value: bool) -> Mapping[str, Any]: ...


# What the backend never takes from the client as trusted fact.
UNTRUSTED_CLIENT_ASSERTIONS: tuple[str, ...] = (
    "device_check_state", "device_labels", "package_name", "signing_certificate_digest",
    "verdict_summary", "recall_state",
)


class PlayIntegrityAdapter:
    """Google Play Integrity / Play Integrity Device Recall, read and written by the backend with
    its own configured Google credentials."""

    platform: DevicePlatform = DevicePlatform.android

    def __init__(self, credentials: GoogleCredentials, transport: PlayIntegrityTransport,
                 *, release_policy: ReleasePolicyRegistry | None = None):
        assert_configured_credentials(credentials)
        self._credentials = credentials
        self._transport = transport
        self._release_policy = release_policy or ReleasePolicyRegistry()

    def _assert_mandatory(self, operation: AuthOperation) -> None:
        """A Play Integrity verdict is mandatory on every Android claim, registered claims
        included, regardless of Device Recall."""
        # [impl->req~proof-android-verdict-mandatory~1]
        if operation not in NATIVE_CLAIM_OPERATIONS:
            raise ProofAdapterError(f"{operation} has no Play Integrity state")
        assert_vendor_state_access(operation)
        assert_configured_credentials(self._credentials)

    def verify_material(self, operation: AuthOperation, material: AndroidClaimMaterial,
                        ledger: NativeClaimLedger) -> None:
        """One Android integrity token covers both the recall read and the recall write, and it
        must be present up front. It stays untrusted request-body input, and no client-supplied
        device label, package name, signing digest, verdict summary or recall state is a fact."""
        # [impl->req~proof-native-claim-verify-vendor-material~1]
        # [impl->req~proof-android-single-token-untrusted~1]
        # [impl->req~proof-android-verdict-mandatory~1]
        self._assert_mandatory(operation)
        ledger.record(NativeClaimStep.verify_vendor_material)
        if not isinstance(material, AndroidClaimMaterial):
            raise ProofRejected("an Android claim carries one Play Integrity token")
        if not material.integrity_token or not str(material.integrity_token).strip():
            raise ProofRejected("the Play Integrity token is missing or malformed")
        untrusted_vendor_material({"play_integrity_token": material.integrity_token})

    def _decoded_verdict(self, material: AndroidClaimMaterial,
                         ledger: NativeClaimLedger) -> Mapping[str, Any]:
        """The server-side decoded Play Integrity verdict, read under the Device Recall read
        budget: it is the recall read."""
        # [impl->req~proof-android-recall-from-decoded-verdict~1]
        # [impl->req~proof-native-claim-vendor-write-gate~1]
        def decode(_plan: AttemptPlan | None) -> Any:
            try:
                return self._transport.decode_verdict(
                    integrity_token=str(material.integrity_token), credentials=self._credentials)
            except Exception as exc:
                raise NativeClaimUnavailable(
                    f"the Play Integrity verdict failed: {exc}") from None

        verdict = ledger.dispatch(ProviderCall.device_recall_read, decode)
        if not isinstance(verdict, Mapping):
            raise NativeClaimUnavailable("the Play Integrity verdict is malformed")
        return verdict

    def release_key(self, verdict: Mapping[str, Any]) -> ReleaseKey:
        """The release this claim came from, taken from the server-side decoded verdict's own
        `appIntegrity` block — package name, signing-certificate digest and release — and never
        from the client-supplied fields of `AndroidClaimMaterial`. A verdict that does not carry
        all three names no enumerated release and is rejected outright."""
        # [impl->req~proof-android-release-policy-enumeration~1]
        # [impl->req~proof-android-single-token-untrusted~1]
        integrity = verdict.get("appIntegrity")
        if not isinstance(integrity, Mapping):
            raise ProofRejected("the decoded verdict carries no appIntegrity block")
        digest = integrity.get("certificateSha256Digest")
        if isinstance(digest, Sequence) and not isinstance(digest, str | bytes):
            digest = next(iter(digest), None)
        package, release = integrity.get("packageName"), integrity.get("release")
        if not all(isinstance(value, str) and value for value in (package, digest, release)):
            raise ProofRejected("the decoded verdict names no enumerated release")
        return ReleaseKey(package_name=str(package), signing_certificate_digest=str(digest),
                          release=str(release))

    def recall_required(self, operation: AuthOperation, verdict: Mapping[str, Any]) -> bool:
        """Whether this claim must satisfy Device Recall. An unrecognized, unenumerated release
        is rejected outright — before any vendor write — and the registered claim's requirement
        is the checked-in policy's to state; the anonymous claim always requires it."""
        # [impl->req~proof-android-release-policy-enumeration~1]
        policy = self._release_policy.policy_for(self.release_key(verdict))
        if operation is AuthOperation.claim_registered_grant:
            return registered_claim_requires_recall(policy)
        return True

    def read_claimed(self, operation: AuthOperation, material: AndroidClaimMaterial,
                     ledger: NativeClaimLedger) -> bool:
        """Device Recall state is read only from the server-side decoded verdict. A token that
        verifies but whose decoded verdict lacks Device Recall is a vendor-material failure
        surfaced as `proof_rejected`: no attempt is made to distinguish a device that genuinely
        lacks Device Recall from a client that withheld material, and no client assertion
        explaining the absence is trusted. The decoded verdict is also what the checked-in
        release policy is consulted with, so an unenumerated release fails here — before the
        eligibility checks and before any vendor write."""
        # [impl->req~proof-native-claim-vendor-read~1]
        # [impl->req~proof-android-recall-from-decoded-verdict~1]
        # [impl->req~proof-android-release-policy-enumeration~1]
        self._assert_mandatory(operation)
        ledger.require(NativeClaimStep.verify_vendor_material)
        ledger.record(NativeClaimStep.vendor_read)
        state = recall_state_for(operation)
        verdict = self._decoded_verdict(material, ledger)
        if not self.recall_required(operation, verdict):
            # This release is classed `no_device_recall`: the registered claim carries no recall
            # state to consult, and the device has consumed no recall slot.
            return False
        recall = verdict.get("deviceRecall")
        if not isinstance(recall, Mapping) or str(state) not in recall:
            raise ProofRejected("the decoded Play Integrity verdict carries no Device Recall")
        value = recall[str(state)]
        return bool(value)

    def write_claimed(self, operation: AuthOperation, material: AndroidClaimMaterial,
                      ledger: NativeClaimLedger) -> DeviceBitWrite:
        """The recall-state write is a mandatory fail-closed pre-grant gate: Google must confirm
        it before any grant is created, and any write failure, timeout or ambiguous result fails
        the claim with no grant created."""
        # [impl->req~proof-native-claim-vendor-write-gate~1]
        # [impl->req~proof-android-recall-write-gate~1]
        self._assert_mandatory(operation)
        ledger.require(NativeClaimStep.database_eligibility)
        ledger.record(NativeClaimStep.vendor_write)
        state = recall_state_for(operation)

        def write_recall(_plan: AttemptPlan | None) -> bool:
            try:
                acknowledgment = self._transport.write_recall(
                    integrity_token=str(material.integrity_token), credentials=self._credentials,
                    state=state, value=True)
            except Exception as exc:
                raise NativeClaimWriteFailed(f"the Device Recall write failed: {exc}") from None
            if not isinstance(acknowledgment, Mapping) or "confirmed" not in acknowledgment:
                raise NativeClaimWriteFailed("the Device Recall write result is ambiguous")
            if acknowledgment["confirmed"] is not True:
                raise NativeClaimWriteFailed("Google did not confirm the Device Recall write")
            return True

        # [impl->req~proof-native-claim-vendor-write-gate~1]
        write = ledger.dispatch_write(ProviderCall.device_recall_write, write_recall)
        if write.call is not DEVICE_BIT_WRITE_CALL[DevicePlatform.android]:
            raise ProofAdapterError("an Android claim reports its write as the recall write")
        return write


# Platforms whose device-state gates are supported. Android's anonymous and registered gates are
# supported wherever their Device Recall states are available, so no iOS-only rejection applies
# merely because a request is Android.
# [impl->req~proof-android-gates-no-ios-only-rejection~1]
SUPPORTED_NATIVE_PLATFORMS: frozenset[DevicePlatform] = frozenset(
    {DevicePlatform.ios, DevicePlatform.android})
IOS_ONLY_REJECTIONS: frozenset[str] = frozenset()


def assert_platform_supported(platform: DevicePlatform, operation: AuthOperation) -> None:
    """Android anonymous and registered device-state gates are supported where their Device
    Recall states are available; no iOS-only platform rejection applies merely because the
    request is Android."""
    # [impl->req~proof-android-gates-no-ios-only-rejection~1]
    if IOS_ONLY_REJECTIONS:
        raise ProofAdapterError("no iOS-only rejection applies to an Android request")
    if operation not in NATIVE_CLAIM_OPERATIONS:
        raise ProofAdapterError(f"{operation} is no native free-grant claim")
    if platform not in SUPPORTED_NATIVE_PLATFORMS:
        raise ProofAdapterError(f"{platform} has no native device-state gate")


# --- The web bot-check adapter: Cloudflare Turnstile -------------------------------------------------


class TurnstileEnvironment(StrEnum):
    """Each environment holds its own Turnstile key pair."""
    development = "development"
    production = "production"


class TurnstileDenied(ServiceError):
    """`siteverify` denied the token: invalid, expired, duplicate or replayed, or the hostname
    did not match. Never treated as a pass. Its status is the shared class's own."""
    error_code: ErrorCode = ClientErrorClass.verification_required.value
    status_code = remediation_for(ClientErrorClass.verification_required.value).http_status


class TurnstileUnavailable(ServiceError):
    """A dependency failure or a service misconfiguration. Fails closed and is recorded directly
    as the audit row's result."""
    error_code: ErrorCode = ClientErrorClass.verification_temporarily_unavailable.value
    status_code = remediation_for(
        ClientErrorClass.verification_temporarily_unavailable.value).http_status
    result: AuthEventResult = AuthEventResult.verification_temporarily_unavailable


class TurnstileMisconfigured(TurnstileUnavailable):
    """The third failure class: invalid or missing server-side Cloudflare secrets. Fails closed,
    reports temporary unavailability, and raises an alert — never a client-caused denial."""


# Cloudflare's documented test keys, which production startup validation rejects.
# [impl->req~proof-turnstile-per-environment-keys~1]
TURNSTILE_TEST_SITEKEYS: frozenset[str] = frozenset({
    "1x00000000000000000000AA", "2x00000000000000000000AB", "3x00000000000000000000FF",
    "1x00000000000000000000BB", "2x00000000000000000000BB",
})
TURNSTILE_TEST_SECRETS: frozenset[str] = frozenset({
    "1x0000000000000000000000000000000AA", "2x0000000000000000000000000000000AA",
    "3x0000000000000000000000000000000AA",
})
DEVELOPMENT_HOSTNAMES: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})
DEVELOPMENT_HOSTNAME_SUFFIXES: tuple[str, ...] = (".local", ".localhost", ".test", ".invalid",
                                                  ".example")


class TurnstileConfig(BaseModel):
    """One environment's Turnstile keys, held in server configuration only. The sitekey is the
    public half; the secret never leaves the server."""
    # [impl->req~proof-turnstile-per-environment-keys~1]
    environment: TurnstileEnvironment
    sitekey: str = Field(min_length=1)
    secret: SecretStr
    hostname_allow_list: tuple[str, ...] = ()

    def assert_startup_valid(self) -> None:
        """Production startup validation rejects Cloudflare's documented test keys, development
        secrets and development hostnames, so a non-production key cannot validate a production
        token."""
        # [impl->req~proof-turnstile-per-environment-keys~1]
        # [impl->req~proof-turnstile-misconfiguration-class~1]
        secret = self.secret.get_secret_value()
        if not secret:
            raise TurnstileMisconfigured("the Cloudflare secret key is missing")
        if self.environment is not TurnstileEnvironment.production:
            return
        if self.sitekey in TURNSTILE_TEST_SITEKEYS or secret in TURNSTILE_TEST_SECRETS:
            raise TurnstileMisconfigured("production rejects Cloudflare's documented test keys")
        if not self.hostname_allow_list:
            raise TurnstileMisconfigured("production configures its own hostname allow-list")
        for hostname in self.hostname_allow_list:
            if is_development_hostname(hostname):
                raise TurnstileMisconfigured(f"{hostname} is a development hostname")

    def hostname_allowed(self, hostname: str | None) -> bool:
        """The returned hostname must match the deployment's configured production hostname
        allow-list strictly — exact equality, never a suffix or wildcard match."""
        # [impl->req~proof-turnstile-success-and-hostname~1]
        # [impl->req~proof-turnstile-per-environment-keys~1]
        return bool(hostname) and hostname in self.hostname_allow_list


def is_development_hostname(hostname: str) -> bool:
    """Whether a configured hostname is a development one."""
    # [impl->req~proof-turnstile-per-environment-keys~1]
    lowered = hostname.strip().lower()
    return (lowered in DEVELOPMENT_HOSTNAMES
            or lowered.endswith(DEVELOPMENT_HOSTNAME_SUFFIXES))


# A Turnstile token expires 300 seconds after issuance if unvalidated, and is single-use: a
# second `siteverify` call against a consumed token fails as `timeout-or-duplicate`.
# [impl->req~proof-turnstile-token-ttl-single-use~1]
TURNSTILE_TOKEN_TTL_SECONDS: int = 300
TURNSTILE_DUPLICATE_ERROR: str = "timeout-or-duplicate"

# The vendor's one-time-use behavior is the whole web-gate replay bound: no backend per-request
# web-gate challenge or binding record exists, and no scheduled cleanup job is introduced.
WEB_GATE_REPLAY_RECORDS: frozenset[str] = frozenset()
WEB_GATE_CLEANUP_JOBS: frozenset[str] = frozenset()

# Fields the gate never matches against a pinned per-gate value, and never denies a request on.
UNMATCHED_SITEVERIFY_FIELDS: tuple[str, ...] = ("action", "cdata")

# Denial reasons Cloudflare returns. Every one of them maps to `verification_required`.
TURNSTILE_DENIAL_CODES: frozenset[str] = frozenset({
    "invalid-input-response", "timeout-or-duplicate", "invalid-widget-id",
    "invalid-parsed-secret", "bad-request",
})

# Misconfiguration codes: the server's own secret is missing or invalid.
TURNSTILE_MISCONFIGURATION_CODES: frozenset[str] = frozenset({
    "missing-input-secret", "invalid-input-secret",
})

# Dependency-failure outcomes. None of them may fail open, and none downgrades to a
# cached-positive or account-only fallback.
TURNSTILE_FALLBACKS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class TurnstileOutcome:
    """One accepted `siteverify` result."""
    hostname: str
    remoteip: str | None
    unresolved_address_key: str | None = None
    unmatched: tuple[str, ...] = field(default=UNMATCHED_SITEVERIFY_FIELDS)


class SiteverifyTransport(Protocol):
    """The POST to Cloudflare's `siteverify` endpoint."""

    def post(self, *, secret: str, response: str,
             remoteip: str | None) -> Mapping[str, Any]: ...


def turnstile_remoteip(address: GatewayResolvedAddress | None) -> tuple[str | None, str | None]:
    """The `remoteip` the backend passes: the trusted-proxy-chain-resolved client address, never
    a client-supplied header. An unresolvable address follows the existing unresolved-address
    handling — the one shared bucket at the single-address ceiling — rather than being omitted
    silently."""
    # [impl->req~proof-turnstile-siteverify-validation~1]
    if address is None or address.source is AddressSource.unresolved or not address.address:
        return None, canonical_client_ip_key(address)
    return address.address, None


def turnstile_siteverify(config: TurnstileConfig,
                         token: str | None,
                         transport: SiteverifyTransport,
                         *,
                         address: GatewayResolvedAddress | None,
                         limiter: RateLimiter | None = None,
                         budget_key: str = "global",
                         endpoint_admission_passed: bool = True,
                         alert: Callable[[str], None] | None = None) -> TurnstileOutcome:
    """The web free-grant gate's bot check. The client-supplied Turnstile token is untrusted
    request-body input; the backend validates it with a POST to Cloudflare's `siteverify`
    endpoint using the deployment's server-held secret key, passing the resolved client address
    as `remoteip`. It accepts only `success: true` with a hostname on the configured allow-list;
    every denial reason maps to `verification_required`, every dependency failure fails closed as
    `verification_temporarily_unavailable`, and invalid or missing server-side secrets are the
    third, misconfiguration failure class."""
    # [impl->req~proof-turnstile-siteverify-validation~1]
    config.assert_startup_valid()
    if not token or not str(token).strip():
        raise TurnstileDenied("no Turnstile token was presented")
    remoteip, unresolved_key = turnstile_remoteip(address)

    # The call runs under its named fail-closed budget.
    # [impl->req~proof-turnstile-siteverify-budget~1]
    decision = consume_siteverify_budget(limiter, budget_key,
                                         endpoint_admission_passed=endpoint_admission_passed)
    if decision is not None and not decision.allowed:
        raise TurnstileUnavailable(f"{TURNSTILE_ENTRY} is exhausted")

    try:
        payload = transport.post(secret=config.secret.get_secret_value(),
                                 response=str(token), remoteip=remoteip)
    except Exception as exc:
        # [impl->req~proof-turnstile-dependency-failure-fails-closed~1]
        raise TurnstileUnavailable(f"siteverify was unreachable: {exc}") from None
    return _classify_siteverify(config, payload, remoteip=remoteip,
                                unresolved_key=unresolved_key, alert=alert)


def consume_siteverify_budget(limiter: RateLimiter | None, key: str, *,
                              endpoint_admission_passed: bool) -> LimitDecision | None:
    """The `siteverify` call runs under the named fail-closed
    `adapter_cloudflare_turnstile_siteverify` budget defined in
    `08-rate-limits-and-admission-control.md`. That budget's shape is the rate-limit file's; this
    is the adapter charging it."""
    # [impl->req~proof-turnstile-siteverify-budget~1]
    entry = budget_entry_for(ProviderCall.turnstile_siteverify)
    if entry != TURNSTILE_ENTRY:
        raise ProofAdapterError(f"siteverify is budgeted under {TURNSTILE_ENTRY}")
    if limiter is None:
        return None
    # The unit is taken by the one charging path, which also enforces the second-layer rule:
    # this adapter keeps no copy of the endpoint-admission guard.
    # [impl->req~ratelimit-adapter-limits-second-layer~1]
    return consume_budget_unit(limiter, ProviderCall.turnstile_siteverify, key,
                               endpoint_admission_passed=endpoint_admission_passed)


def _classify_siteverify(config: TurnstileConfig,
                         payload: Mapping[str, Any] | Any,
                         *,
                         remoteip: str | None,
                         unresolved_key: str | None,
                         alert: Callable[[str], None] | None) -> TurnstileOutcome:
    """The three failure classes, and the one acceptance."""
    if not isinstance(payload, Mapping) or "success" not in payload:
        # [impl->req~proof-turnstile-dependency-failure-fails-closed~1]
        raise TurnstileUnavailable("siteverify returned a malformed or unparseable response")
    codes = tuple(str(code) for code in payload.get("error-codes", ()))
    misconfigured = set(codes) & TURNSTILE_MISCONFIGURATION_CODES
    if misconfigured:
        # [impl->req~proof-turnstile-misconfiguration-class~1]
        if alert is not None:
            alert(f"turnstile_misconfiguration:{sorted(misconfigured)}")
        raise TurnstileMisconfigured(
            f"the server-side Cloudflare secret is {sorted(misconfigured)}")
    if payload["success"] is not True:
        # Invalid, expired, duplicate or replayed tokens all land here, and none is ever a pass.
        # [impl->req~proof-turnstile-success-and-hostname~1]
        # [impl->req~proof-turnstile-token-ttl-single-use~1]
        raise TurnstileDenied(f"siteverify denied the token: {codes or ('unspecified',)}")
    hostname = payload.get("hostname")
    if not config.hostname_allowed(hostname if isinstance(hostname, str) else None):
        # [impl->req~proof-turnstile-success-and-hostname~1]
        raise TurnstileDenied(f"{hostname} is not on the configured hostname allow-list")
    if TURNSTILE_FALLBACKS:
        # [impl->req~proof-turnstile-dependency-failure-fails-closed~1]
        raise ProofAdapterError("the gate never downgrades to a cached-positive fallback")
    # `action` and `cdata` are not matched against a pinned per-gate value, and no request is
    # denied on that basis.
    # [impl->req~proof-turnstile-action-cdata-not-matched~1]
    return TurnstileOutcome(hostname=str(hostname), remoteip=remoteip,
                            unresolved_address_key=unresolved_key)


def turnstile_replay_bound() -> tuple[int, str]:
    """The vendor's 300-second TTL and one-time use is the whole web-gate replay bound: no
    backend per-request web-gate challenge or binding record exists, and no scheduled cleanup job
    is introduced for the web gate."""
    # [impl->req~proof-turnstile-token-ttl-single-use~1]
    if WEB_GATE_REPLAY_RECORDS or WEB_GATE_CLEANUP_JOBS:
        raise ProofAdapterError("the web gate keeps no replay record and no cleanup job")
    return TURNSTILE_TOKEN_TTL_SECONDS, TURNSTILE_DUPLICATE_ERROR


def assert_action_cdata_not_matched(pinned: Mapping[str, Any] | None = None) -> None:
    """Matching the returned `action` or `cdata` to a pinned per-gate value is not required, and
    no request is denied on that basis."""
    # [impl->req~proof-turnstile-action-cdata-not-matched~1]
    pinned_fields = sorted(set(pinned or {}) & set(UNMATCHED_SITEVERIFY_FIELDS))
    if pinned_fields:
        raise ProofAdapterError(f"{pinned_fields} is not matched to a pinned per-gate value")


# --- Claim challenge lifetime -----------------------------------------------------------------------


# `claim_anonymous_grant` enforces no age limit on the proof material a caller presents: no bound
# on the Play Integrity verdict's `timestampMillis`, and no vendor-evidence age measurement of
# any kind.
# [impl->req~proof-claim-no-vendor-evidence-age-limit~1]
VENDOR_EVIDENCE_AGE_LIMITS: frozenset[str] = frozenset()
DEVICECHECK_HAS_GENERATION_TIMESTAMP: bool = False

# The challenge's own lifetime, which bounds only the interval between issuance and the claim.
CLAIM_CHALLENGE_TTL_SECONDS: int = 300
CLAIM_CHALLENGE_TTL_OVERRIDES: frozenset[AuthOperation] = frozenset()

# What the rest of the completion is bounded by instead: the fixed per-call provider timeouts and
# the three-attempt caps alone.
COMPLETION_ATTEMPT_CAP: int = 3
COMPLETION_WALL_CLOCK_BOUNDS: frozenset[str] = frozenset()


def assert_no_vendor_evidence_age(evidence: Mapping[str, Any] | None = None) -> None:
    """No vendor-evidence age measurement of any kind: no bound on the Play Integrity verdict's
    `timestampMillis`, and no server-readable DeviceCheck generation timestamp for the backend to
    claim to extract. A token's validity is solely the vendor's determination at submission."""
    # [impl->req~proof-claim-no-vendor-evidence-age-limit~1]
    if VENDOR_EVIDENCE_AGE_LIMITS or DEVICECHECK_HAS_GENERATION_TIMESTAMP:
        raise ProofAdapterError("no vendor-evidence age is measured")
    for name in ("timestampMillis", "devicecheck_generated_at", "evidence_age_seconds"):
        if evidence is not None and name in evidence:
            raise ProofAdapterError(f"{name} is not an age limit this endpoint enforces")


def claim_challenge_ttl(operation: AuthOperation = AuthOperation.claim_anonymous_grant) -> int:
    """The endpoint's server-issued challenge carries the shared 300-second default TTL with
    single-use state and no per-operation override, and that lifetime bounds only the interval
    between issuance and the claim."""
    # [impl->req~proof-claim-no-vendor-evidence-age-limit~1]
    if operation in CLAIM_CHALLENGE_TTL_OVERRIDES:
        raise ProofAdapterError(f"{operation} has no per-operation TTL override")
    return CLAIM_CHALLENGE_TTL_SECONDS


def assert_completion_unbounded_by_clock(elapsed_seconds: float,
                                         *, attempts: int = 1) -> None:
    """Once the challenge is claimed, the rest of the completion — proof verification, the vendor
    read, the database eligibility preflight, the vendor write and the activation transaction —
    runs regardless of wall-clock time, bounded by the fixed per-call provider timeouts and the
    three-attempt caps alone."""
    # [impl->req~proof-claim-no-vendor-evidence-age-limit~1]
    if COMPLETION_WALL_CLOCK_BOUNDS:
        raise ProofAdapterError(f"{elapsed_seconds}s of wall clock bounds nothing after the claim")
    if attempts > COMPLETION_ATTEMPT_CAP:
        raise ProofAdapterError("the completion is capped at three attempts per call")


@dataclass(frozen=True, slots=True)
class ChallengeClaim:
    """One claim attempt's result, and whether a vendor call may follow it."""
    outcome: ClaimOutcome
    vendor_calls_allowed: bool
    result: AuthEventResult | None = None


def claim_challenge_before_vendor(claim: Callable[[], ClaimOutcome],
                                  *, vendor_calls_made: int = 0) -> ChallengeClaim:
    """The thin guard this endpoint adds over the shared challenge mechanics: no vendor call may
    precede the claim.

    The mechanics themselves are `procedures.SharedChallengeService.complete`'s — the exists,
    operation-binding and caller-context checks, the one atomic conditional update that also
    enforces expiry from the row's own server timestamps, the outcome-to-result mapping, and the
    consumption in the attempt's final transaction. This function neither repeats nor reinterprets
    them: it takes that conditional update's own `ClaimOutcome` and reads the shared mapping, so a
    bad challenge is recorded as what it actually was — an unknown row is `challenge_not_found`,
    never `challenge_expired` — the vendor adapter is never invoked, and a duplicate that loses
    the claim spends no vendor call at all. The lifecycle facts the requirement also states — a
    claimed row never returns to `issued`, a consumed row is marked consumed rather than deleted,
    and no cleanup job or recovery scan exists — are `challenges.advance_state`,
    `challenges.CHALLENGE_PURGE_JOBS` and `challenges.challenge_retention_deadline`'s.
    """
    # [impl->req~proof-claim-challenge-mechanics~1]
    if vendor_calls_made:
        raise ProofAdapterError("the challenge is validated and claimed before any vendor call")
    outcome = claim()
    if outcome is ClaimOutcome.claimed:
        return ChallengeClaim(outcome, True)
    return ChallengeClaim(outcome, False, claim_failure_result(outcome))


def vendor_failure_is_a_dependency_failure(error: Exception) -> AuthEventResult:
    """Vendor outages and timeouts stay dependency failures and are never misreported as invalid
    proof."""
    # [impl->req~proof-claim-challenge-mechanics~1]
    if isinstance(error, ProofRejected):
        raise ProofAdapterError("a client-proof failure is not a dependency failure")
    if isinstance(error, ClaimRejection):
        return error.result
    return AuthEventResult.native_claim_unavailable


# --- What the free-grant claims ask a client for -------------------------------------------------


# The client-supplied artifacts each branch's request carries. iOS carries two separate
# per-transaction tokens; Android carries one; the web gate carries the Turnstile token.
# [impl->req~proof-ios-separate-query-update-tokens~1]
BRANCH_CLIENT_ARTIFACTS: dict[ClaimBranch, tuple[ProofArtifact, ...]] = {
    ClaimBranch.native_ios: (ProofArtifact.devicecheck_query_token,
                             ProofArtifact.devicecheck_update_token),
    ClaimBranch.native_android: (ProofArtifact.play_integrity_verdict,),
    ClaimBranch.web: (ProofArtifact.turnstile_token,),
}


def branch_client_artifacts(branch: ClaimBranch) -> tuple[ProofArtifact, ...]:
    """What the request must carry up front for this branch."""
    # [impl->req~proof-native-claim-verify-vendor-material~1]
    artifacts = BRANCH_CLIENT_ARTIFACTS.get(branch)
    if artifacts is None:
        raise ProofAdapterError(f"{branch} is no free-grant claim branch")
    return artifacts


def assert_untrusted_client_assertions(claimed: Sequence[str]) -> None:
    """No client-supplied device-check state, device label, package name, signing digest, verdict
    summary or recall state is trusted as fact."""
    # [impl->req~proof-android-single-token-untrusted~1]
    offending = sorted(set(claimed) & set(UNTRUSTED_CLIENT_ASSERTIONS))
    if offending:
        raise ProofAdapterError(f"{offending} are never trusted as client-supplied facts")
