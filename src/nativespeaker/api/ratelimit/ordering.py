"""Where admission checks sit in a request.

One ledger records the order a request actually took — JWT verification, barrier admission,
each limiter evaluation, the challenge, each provider budget and each expensive step — and
fails closed the moment that order is wrong. The order is enforced where the steps are taken
rather than reviewed afterwards.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from nativespeaker.api.auth.challenges import ChallengeState, advance_state
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import (
    AuthOperation,
    is_challenge_bearing,
    is_on_audited_path,
    match_operation,
)
from nativespeaker.api.ratelimit.config import (
    DEVICE_BIT_BUDGET_ENTRIES,
    FIREBASE_LOOKUP_ENTRY_KEYS,
    complete_entries,
    is_blocking,
    prepare_entries,
)
from nativespeaker.api.ratelimit.keys import IDENTITY_COMPONENTS, KeyComponent

if TYPE_CHECKING:
    from nativespeaker.api.ratelimit.limiter import RateLimiter


class AdmissionOrderError(RuntimeError):
    """A step ran out of the order this specification fixes."""


class ExpensiveStep(StrEnum):
    """The steps a rejection must precede whenever the configured key is available."""
    # [impl->req~ratelimit-reject-before-expensive-steps~1]
    provider_call = "provider_call"
    proof_verification = "proof_verification"
    live_store_verification = "live_store_verification"
    firebase_lookup = "firebase_lookup"
    provider_state_write = "provider_state_write"
    database_lock = "database_lock"
    database_mutation = "database_mutation"


# A coarse first limit may key only on the client IP, the verified-token subject, or the user.
# [impl->req~ratelimit-coarse-then-endpoint-specific-limit~1]
COARSE_KEY_POLICIES: frozenset[tuple[KeyComponent, ...]] = frozenset({
    (KeyComponent.ip,),
    (KeyComponent.subject_hash,),
    (KeyComponent.issuer, KeyComponent.subject_hash),
    (KeyComponent.user,),
})


class DeviceBitCall(StrEnum):
    """The four load-bearing vendor device-bit calls on the free-grant claim path."""
    devicecheck_read = "devicecheck_read"
    devicecheck_write = "devicecheck_write"
    device_recall_read = "device_recall_read"
    device_recall_write = "device_recall_write"


# Each call's budget entry.
# [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
DEVICE_BIT_BUDGET: dict[DeviceBitCall, str] = {
    DeviceBitCall.devicecheck_read: "adapter_devicecheck_read",
    DeviceBitCall.devicecheck_write: "adapter_devicecheck_write",
    DeviceBitCall.device_recall_read: "adapter_play_integrity_device_recall_read",
    DeviceBitCall.device_recall_write: "adapter_play_integrity_device_recall_write",
}

READ_CALLS: frozenset[DeviceBitCall] = frozenset({
    DeviceBitCall.devicecheck_read, DeviceBitCall.device_recall_read})
WRITE_CALLS: frozenset[DeviceBitCall] = frozenset(set(DeviceBitCall) - READ_CALLS)


class DeviceBitWriteError(AdmissionOrderError):
    """The device-bit write was about to be treated as anything other than load-bearing."""


@dataclass(frozen=True, slots=True)
class DeviceBitWrite:
    """One vendor device-bit write and the vendor's confirmation of it."""
    call: DeviceBitCall
    confirmed: bool


def assert_grant_row_permitted(write: DeviceBitWrite | None) -> None:
    """A grant row is inserted only behind a vendor-confirmed device-bit write. This is the one
    guard for that rule: the adapter layer dispatches the write and reports the vendor's
    confirmation, and the decision is taken here. After a failed claim the client may retry only
    by submitting a whole new claim with fresh vendor material — never by having the backend
    finish this write later."""
    # [impl->req~ratelimit-device-bit-write-load-bearing~1]
    # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
    if write is None or write.call not in WRITE_CALLS or not write.confirmed:
        raise DeviceBitWriteError("the vendor confirms the bit write before the grant row")


class AdmissionLedger:
    """One request's admission order."""

    def __init__(self, method: str, path: str, *, mode: RequestMode | None = None):
        # The audited attempt path's boundary is the single route-scoped entry rule in
        # `00-overview-and-shared-contracts.md`. Nothing here defines an audit boundary of its
        # own: this ledger reads the shared rule and never restates it.
        # [impl->req~ratelimit-audit-boundary-owned-by-shared-contract~1]
        self.method = method.upper()
        self.path = path
        self.mode = mode
        self.operation: AuthOperation | None = match_operation(self.method, self.path)
        self.on_audited_path = is_on_audited_path(method, path)
        self.jwt_verified = False
        self.barrier_admitted = False
        # The challenge lifecycle is `auth.challenges.ChallengeState` and nothing else: this
        # ledger tracks the state the shared module defines instead of keeping its own flags.
        self.challenge_state: ChallengeState | None = None
        self.challenge_failed = False
        self.refused = False
        self.evaluated: list[str] = []
        self.budgets_checked: list[str] = []
        self.device_bit_calls: list[DeviceBitCall] = []
        self.device_bit_writes: list[DeviceBitWrite] = []
        self.expensive_steps: list[ExpensiveStep] = []

    @property
    def challenge_issued(self) -> bool:
        return self.challenge_state is not None

    @property
    def challenge_claimed(self) -> bool:
        return self.challenge_state is ChallengeState.claimed

    def applicable_entries(self) -> tuple[str, ...]:
        """Every blocking named entry this route's operation configures for the phase the
        request has reached, derived from the route itself. A caller declares nothing: the
        rejection must precede the expensive step whenever the configured key is available, so
        the applicable set is the ledger's to compute, not the caller's to remember."""
        # [impl->req~ratelimit-reject-before-expensive-steps~1]
        if self.operation is None:
            return ()
        if not is_challenge_bearing(self.operation):
            # No prepare phase and no challenge: every named entry the operation carries.
            return (*prepare_entries(self.operation), *complete_entries(self.operation))
        if self.mode is RequestMode.prepare:
            return prepare_entries(self.operation)
        # A completion, and the conservative default: expensive work lives in the completion,
        # so an undeclared mode is guarded by the completion's counters, not the weaker set.
        return complete_entries(self.operation)

    # --- what the layers establish ---------------------------------------------------------

    def verify_jwt(self) -> None:
        """This layer's JWT verification succeeded for the route."""
        # [impl->req~ratelimit-identity-keyed-after-jwt-verification~1]
        self.jwt_verified = True

    def admit_barrier(self) -> None:
        """The shared authentication-and-identity-resolution barrier resolved and admitted a
        linked active user."""
        # [impl->req~ratelimit-user-keyed-after-barrier-admission~1]
        if not self.jwt_verified:
            raise AdmissionOrderError("the barrier admits nothing before token verification")
        self.barrier_admitted = True

    # --- limiter evaluation ----------------------------------------------------------------

    def evaluate(self, name: str, policy: Sequence[KeyComponent], *, allowed: bool = True) -> None:
        """Record one limiter evaluation, in the position the request actually took it.

        An IP-keyed limit requires no verified identity and may run at any position. An
        identity-keyed limit may run only after this layer's JWT verification succeeded, and a
        `user`-keyed limit only after the barrier admitted a linked active user.
        """
        # [impl->req~ratelimit-identity-keyed-after-jwt-verification~1]
        # [impl->req~ratelimit-user-keyed-after-barrier-admission~1]
        if self.challenge_claimed:
            raise AdmissionOrderError(
                f"{name} is a complete-phase limit and runs before the challenge is claimed")
        components = tuple(policy)
        if any(component in IDENTITY_COMPONENTS for component in components):
            if not self.jwt_verified:
                raise AdmissionOrderError(
                    f"{name} is identity-keyed and runs only after JWT verification")
        if KeyComponent.user in components and not self.barrier_admitted:
            raise AdmissionOrderError(
                f"{name} is user-keyed and runs only after the barrier admitted the caller")
        self.evaluated.append(name)
        # Evaluating a limit consumes no challenge and reinterprets nothing: the ledger's
        # challenge state is untouched here, on prepare and on completion alike.
        # [impl->req~ratelimit-complete-limits-before-challenge-claim~1]
        if not allowed and is_blocking(name):
            self.refused = True

    def coarse_then_endpoint_specific(self,
                                      coarse: tuple[str, Sequence[KeyComponent]],
                                      specific: tuple[str, Sequence[KeyComponent]]) -> None:
        """Apply an initial coarse limit, then the stronger endpoint-specific limit, before the
        expensive step the endpoint-specific key only became available after."""
        # [impl->req~ratelimit-coarse-then-endpoint-specific-limit~1]
        coarse_name, coarse_policy = coarse
        if tuple(coarse_policy) not in COARSE_KEY_POLICIES:
            raise AdmissionOrderError(
                f"{coarse_name} is no coarse IP, verified-token subject, or user limit")
        self.evaluate(coarse_name, coarse_policy)
        self.evaluate(*specific)

    # --- the challenge ---------------------------------------------------------------------

    def issue_challenge(self, prepare_limits: Sequence[str]) -> None:
        """Issue an operation challenge. Prepare-phase limits run first."""
        # [impl->req~ratelimit-prepare-limits-before-challenge-issue~1]
        self._require_evaluated(prepare_limits, "before an operation challenge is issued")
        if self.refused:
            raise AdmissionOrderError("a refused request issues no operation challenge")
        self.challenge_state = ChallengeState.issued

    def fail_challenge_validation(self) -> None:
        """The presented challenge failed validation. It is handled and audited as that
        challenge error, and charges no device-bit budget."""
        # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
        self.challenge_failed = True

    def claim_challenge(self, complete_limits: Sequence[str]) -> None:
        """Claim the operation challenge. Complete-phase limits ran before this point and did
        not claim, consume, reinterpret or modify it; the claim happens here and before any
        provider call."""
        # [impl->req~ratelimit-complete-limits-before-challenge-claim~1]
        self._require_evaluated(complete_limits, "before the operation challenge is claimed")
        if self.refused:
            raise AdmissionOrderError("a refused request claims no operation challenge")
        if self.challenge_failed:
            raise AdmissionOrderError("a challenge that failed validation is never claimed")
        if self.expensive_steps:
            raise AdmissionOrderError(
                "the completion claims the challenge before any provider call")
        # The claim moves the row along the one-way lifecycle the shared challenge module owns.
        self.challenge_state = advance_state(self.challenge_state or ChallengeState.issued,
                                             ChallengeState.claimed)

    # --- expensive work --------------------------------------------------------------------

    def expensive_step(self, step: ExpensiveStep, *, guarded_by: Sequence[str] = ()) -> None:
        """Take an expensive step. Every limit whose configured key was available at this point
        has already been evaluated, and a rejected request never gets here. The guarding set is
        derived from the ledger's own route; `guarded_by` only adds to it."""
        # [impl->req~ratelimit-reject-before-expensive-steps~1]
        if self.refused:
            raise AdmissionOrderError(f"{step} runs only for an admitted request")
        self._require_evaluated((*self.applicable_entries(), *guarded_by), f"before {step}")
        self.expensive_steps.append(step)

    def _require_evaluated(self, names: Sequence[str], where: str) -> None:
        missing = [name for name in names if name not in self.evaluated]
        if missing:
            raise AdmissionOrderError(f"{', '.join(sorted(missing))} must be evaluated {where}")

    # --- the free-grant device-bit budgets --------------------------------------------------

    def check_device_bit_budget(self, call: DeviceBitCall, *, allowed: bool = True) -> None:
        """Check one device-bit provider budget, immediately before the vendor call it budgets
        and after the operation challenge has been claimed."""
        # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
        if self.challenge_failed:
            raise AdmissionOrderError("a failed challenge charges no device-bit budget")
        if not self.challenge_claimed:
            raise AdmissionOrderError(
                f"{DEVICE_BIT_BUDGET[call]} is checked after the challenge has been claimed")
        if self.refused:
            raise AdmissionOrderError("an exhausted budget prevents every later step of the claim")
        if call in WRITE_CALLS:
            read = next((done for done in self.device_bit_calls if done in READ_CALLS), None)
            if read is None:
                raise AdmissionOrderError("the claim performs its own vendor bit read first")
        self.budgets_checked.append(DEVICE_BIT_BUDGET[call])
        if not allowed:
            self.refused = True

    def vendor_device_bit_call(self,
                               call: DeviceBitCall,
                               *,
                               confirmed: bool = True) -> DeviceBitWrite | None:
        """Perform the vendor device-bit read or write. Its budget was checked immediately
        before it, and no cached or coalesced value substitutes for the call. A write also
        records whether the vendor confirmed it, because that confirmation is what the grant
        row hangs on."""
        # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
        # [impl->req~ratelimit-device-bit-write-load-bearing~1]
        if self.refused:
            raise AdmissionOrderError("an exhausted budget prevents the call it budgets")
        if not self.budgets_checked or self.budgets_checked[-1] != DEVICE_BIT_BUDGET[call]:
            raise AdmissionOrderError(
                f"{DEVICE_BIT_BUDGET[call]} is checked immediately before {call}")
        self.device_bit_calls.append(call)
        if call not in WRITE_CALLS:
            return None
        write = DeviceBitWrite(call=call, confirmed=confirmed)
        self.device_bit_writes.append(write)
        return write

    def confirmed_write(self) -> DeviceBitWrite | None:
        """The vendor-confirmed device-bit write this claim performed, if any."""
        return next((write for write in self.device_bit_writes if write.confirmed), None)

    def insert_grant_row(self) -> None:
        """Insert the grant row. The claim performed its own vendor bit read and obtained
        confirmation of its own vendor bit write first; any rejection or failure refuses the
        claim with no grant row created."""
        # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
        if self.refused:
            raise AdmissionOrderError("a refused claim creates no grant row")
        if not any(call in READ_CALLS for call in self.device_bit_calls):
            raise AdmissionOrderError("the claim performs its own vendor bit read")
        # The one guard for the vendor-confirmed write, shared with the adapter layer.
        # [impl->req~ratelimit-device-bit-write-load-bearing~1]
        assert_grant_row_permitted(self.confirmed_write())


# --- the anonymous-grant admission pair -------------------------------------------------------

# The IP counter is evaluated at route entry; the user counter once the shared barrier has
# admitted the caller. Both counters of a pair must pass, and neither is ever fused with the
# other.
# [impl->req~ratelimit-grant-claim-admission-keys~1]
ANONYMOUS_GRANT_ADMISSION: dict[str, tuple[str, str]] = {
    "prepare": ("claim_anonymous_grant_prepare_ip", "claim_anonymous_grant_prepare"),
    "complete": ("claim_anonymous_grant_ip", "claim_anonymous_grant"),
}


def anonymous_grant_admission(ledger: AdmissionLedger,
                              phase: str,
                              *,
                              ip_allowed: bool = True,
                              user_allowed: bool = True) -> None:
    """Evaluate an anonymous-grant admission pair in its fixed positions."""
    # [impl->req~ratelimit-grant-claim-admission-keys~1]
    ip_entry, user_entry = ANONYMOUS_GRANT_ADMISSION[phase]
    ledger.evaluate(ip_entry, (KeyComponent.ip,), allowed=ip_allowed)
    if not ledger.barrier_admitted:
        raise AdmissionOrderError(
            f"{user_entry} runs once the barrier has admitted the caller")
    ledger.evaluate(user_entry, (KeyComponent.user,), allowed=user_allowed)


# --- the Firebase Admin `getUser` budgets ------------------------------------------------------


class GetUserCallSite(StrEnum):
    """Every place this specification makes a Firebase Admin identity lookup."""
    create_user_anonymous_completion = "create_user_anonymous_completion"
    create_user_registered_completion = "create_user_registered_completion"
    upgrade_anonymous_to_registered = "upgrade_anonymous_to_registered"


_CREATE_USER_GETUSER_BUDGETS: tuple[str, ...] = (
    "adapter_firebase_lookup",
    "create_user_firebase_identity_lookup",
    "create_user_firebase_identity_lookup_ip")

# One deterministic order, broadest scope to narrowest: the global provider-call budget first,
# then the endpoint-layer entries. `create_user` completion is identical on the anonymous and
# the declared-registered path.
# [impl->req~ratelimit-getuser-budget-evaluation-order~1]
# [impl->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
GETUSER_BUDGET_ORDER: dict[GetUserCallSite, tuple[str, ...]] = {
    GetUserCallSite.create_user_anonymous_completion: _CREATE_USER_GETUSER_BUDGETS,
    GetUserCallSite.create_user_registered_completion: _CREATE_USER_GETUSER_BUDGETS,
    GetUserCallSite.upgrade_anonymous_to_registered: (
        "adapter_firebase_lookup",
        "upgrade_anonymous_to_registered_firebase_identity_lookup"),
}

# The global budget is the primary reported result whenever more than one applicable budget is
# exhausted.
PRIMARY_GETUSER_BUDGET = "adapter_firebase_lookup"


@dataclass(frozen=True, slots=True)
class BudgetVerdict:
    """The outcome of one `getUser` budget evaluation."""
    allowed: bool
    primary: str | None = None
    exhausted: tuple[str, ...] = field(default_factory=tuple)
    charged: tuple[str, ...] = field(default_factory=tuple)


def evaluate_getuser_budgets(site: GetUserCallSite,
                             *,
                             test: Callable[[str], bool],
                             charge: Callable[[Sequence[str]], None]) -> BudgetVerdict:
    """Gate one Firebase Admin `getUser` call.

    Every applicable budget is evaluated non-destructively first, in the fixed broadest-to-
    narrowest order, and no counter is incremented unless every one of them has capacity: a
    rejection at either layer charges neither. Only when every check clears are all applicable
    counters incremented together, immediately before the outbound call — including before each
    permitted retry of one — and once charged they remain charged however the call resolves.
    """
    # [impl->req~ratelimit-getuser-budget-evaluation-order~1]
    # [impl->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
    names = GETUSER_BUDGET_ORDER[site]
    exhausted: list[str] = []
    for name in names:
        try:
            has_capacity = test(name)
        except Exception:
            # Each endpoint-layer entry fails closed whenever it cannot be evaluated.
            # [impl->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
            has_capacity = False
        if not has_capacity:
            exhausted.append(name)
    if exhausted:
        primary = (PRIMARY_GETUSER_BUDGET if PRIMARY_GETUSER_BUDGET in exhausted
                   else exhausted[0])
        return BudgetVerdict(allowed=False, primary=primary, exhausted=tuple(exhausted))
    charge(names)
    return BudgetVerdict(allowed=True, charged=names)


def gate_getuser_call(limiter: RateLimiter,
                      site: GetUserCallSite,
                      keys: dict[str, str]) -> BudgetVerdict:
    """Gate a `getUser` call against the configured entries: sequential non-destructive checks
    followed by the joint increment, which is all this scale requires."""
    # [impl->req~ratelimit-getuser-budget-evaluation-order~1]
    # [impl->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
    def probe(name: str) -> bool:
        decision = limiter.test(name, keys[name])
        if decision.storage_failed:
            # Each budget fails closed whenever it cannot be evaluated.
            return False
        return decision.allowed

    def charge(names: Sequence[str]) -> None:
        for name in names:
            limiter.hit(name, keys[name])

    return evaluate_getuser_budgets(site, test=probe, charge=charge)


def assert_budgets_gate_getuser(site: GetUserCallSite, checked: Sequence[str]) -> None:
    """The endpoint-layer lookup budgets, and the global provider-call budget behind them, gate
    the `getUser` call and run before it."""
    # [impl->req~ratelimit-firebase-lookup-budgets-gate-getuser~1]
    expected = GETUSER_BUDGET_ORDER[site]
    if tuple(checked) != expected:
        raise AdmissionOrderError(
            f"{site} gates getUser on {' then '.join(expected)}")
    endpoint_layer = [name for name in expected if name in FIREBASE_LOOKUP_ENTRY_KEYS]
    if not endpoint_layer:
        raise AdmissionOrderError(f"{site} carries no endpoint-layer lookup budget")


def device_bit_budget_entries() -> tuple[str, ...]:
    """The four device-bit budget entry names, in the order this file names them."""
    # [impl->req~ratelimit-free-grant-device-bit-budget-ordering~1]
    return DEVICE_BIT_BUDGET_ENTRIES
