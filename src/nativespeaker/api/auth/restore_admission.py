"""Backend restore admission control: the named limits, their order, the provider-call budgets,
and the coalescing of live provider verification.

Envoy Gateway already bounds `POST /auth/restore-subscription` by IP, subject and URL, and it stays
in place. What it cannot key is restore data only the backend can derive: the proof fingerprint, the
`(provider, external_id)` store subscription behind a verified artifact, and the destination user
the shared barrier resolved. Those are the limits this module places, and it places them for two
reasons — so a junk request cannot force a full `audit.auth_events` restore-attempt row, and so an
adoption attempt cannot spend an Apple or Google provider call before the restore mutation locks
apply.

Nothing here defines its own rejection shape, telemetry rule or counter: the `429`, the
admission-phase carve-out, the aggregate telemetry and the operational counters are
`08-rate-limits-and-admission-control.md`'s, read from `ratelimit/` rather than restated. What is
restore's own is which entries exist, where each one sits, and what may join a coalesced provider
call.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nativespeaker.api.auth.audit import AuthAttempt, AuthEventResult
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.restore import RestoreAttemptAudit, RestoreContractError
from nativespeaker.api.auth.restore_flow import VerifiedTransaction
from nativespeaker.api.ratelimit.config import (
    REQUIRED_ADAPTER_ENTRIES,
    REQUIRED_OPERATION_ENTRIES,
    RateLimitsConfig,
)
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import LimitDecision, RateLimiter
from nativespeaker.api.ratelimit.ordering import AdmissionLedger, ExpensiveStep
from nativespeaker.api.ratelimit.providers import (
    CoalescingError,
    ProviderCall,
    ProviderCoalescer,
    ProviderDampingConfig,
    budget_entry_for,
    consume_budget_unit,
)
from nativespeaker.api.ratelimit.rejection import (
    ADMISSION_REJECTION_STATUS,
    AdmissionPhase,
    AdmissionRejection,
    CoarseActor,
    RateLimitMetrics,
    SecurityTelemetry,
    assert_aggregate_only,
    assert_off_audited_path,
)

RESTORE_OPERATION = AuthOperation.restore_subscription


class RestoreAdmissionError(RestoreContractError):
    """A restore admission rule was about to be broken: a missing entry, a check out of position,
    a budget unit spent the wrong way, or a coalesced result about to be shared too widely."""


# --- What restore admission control is, and what it is additional to --------------------------

# The two reasons the backend keeps its own restore-aware limits on top of Envoy Gateway's.
# [impl->req~restore-admission-control-required~1]
RESTORE_ADMISSION_PURPOSE: tuple[str, ...] = (
    "stop_junk_requests_forcing_restore_attempt_audit_writes",
    "stop_adoption_attempts_spending_provider_calls_before_the_mutation_locks",
)

# Envoy Gateway rate limiting remains in place; the backend limits are additional to it, never a
# restatement of it.
# [impl->req~restore-admission-control-required~1]
GATEWAY_LIMITING_REMAINS = True

# Deleted with the challenge itself: restore has no challenge, so it has no challenge-issuance and
# no challenge-validation-failure limit. The request-rate limits below took over their throttling.
# [impl->req~restore-admission-control-required~1]
DELETED_CHALLENGE_ENTRIES: frozenset[str] = frozenset({
    "restore_subscription_prepare",
    "restore_subscription_challenge_issuance",
    "restore_subscription_challenge_validation_failed",
})


# --- The configured restore admission policy --------------------------------------------------

# Restore request rate, keyed by verified-token subject and by destination user.
# [impl->req~restore-admission-limit-request-rate~1]
REQUEST_RATE_ENTRIES: tuple[str, ...] = ("restore_subscription_subject", "restore_subscription_user")

# Restore proof fingerprints: a failed-attempt limit and a total-attempt limit.
# [impl->req~restore-admission-limit-proof-fingerprints~1]
PROOF_FINGERPRINT_ENTRIES: tuple[str, ...] = ("restore_subscription_proof_fingerprint_failed",
                                              "restore_subscription_proof_fingerprint_total")

# Store subscriptions keyed by `(provider, external_id)`: a cross-account attempt limit and a live
# provider verification limit.
# [impl->req~restore-admission-limit-store-subscriptions~1]
STORE_SUBSCRIPTION_ENTRIES: tuple[str, ...] = (
    "restore_subscription_store_subscription_cross_account",
    "restore_subscription_store_subscription_live_verification")

# Destination users: a rejected cross-account restore attempt limit.
# [impl->req~restore-admission-limit-destination-users~1]
DESTINATION_USER_ENTRIES: tuple[str, ...] = ("restore_subscription_destination_rejected_cross_account",)

# A global live provider-call budget for Apple and a separate one for Google Play. Two counters,
# never one shared budget and never a per-provider sub-budget of a larger one.
# [impl->req~restore-admission-limit-provider-call-budgets~1]
PROVIDER_CALL_BUDGETS: dict[StoreProvider, str] = {
    StoreProvider.apple: "provider_apple_store_live_verification_global",
    StoreProvider.google_play: "provider_google_play_live_verification_global",
}

# The five families the configuration file must define the restore admission policy for.
# [impl->req~restore-admission-policy-config-required~1]
RESTORE_ADMISSION_POLICY: dict[str, tuple[str, ...]] = {
    "request_rate": REQUEST_RATE_ENTRIES,
    "proof_fingerprints": PROOF_FINGERPRINT_ENTRIES,
    "store_subscriptions": STORE_SUBSCRIPTION_ENTRIES,
    "destination_users": DESTINATION_USER_ENTRIES,
    "provider_call_budgets": tuple(PROVIDER_CALL_BUDGETS.values()),
}

# The key policy each restore admission entry is configured with.
# [impl->req~restore-admission-limit-request-rate~1]
# [impl->req~restore-admission-limit-proof-fingerprints~1]
# [impl->req~restore-admission-limit-store-subscriptions~1]
# [impl->req~restore-admission-limit-destination-users~1]
RESTORE_ADMISSION_KEYS: dict[str, tuple[KeyComponent, ...]] = {
    "restore_subscription_subject": (KeyComponent.issuer, KeyComponent.subject_hash),
    "restore_subscription_user": (KeyComponent.user,),
    "restore_subscription_proof_fingerprint_failed": (KeyComponent.restore_proof_fingerprint,),
    "restore_subscription_proof_fingerprint_total": (KeyComponent.restore_proof_fingerprint,),
    "restore_subscription_store_subscription_cross_account": (KeyComponent.provider,
                                                              KeyComponent.external_id),
    "restore_subscription_store_subscription_live_verification": (KeyComponent.provider,
                                                                  KeyComponent.external_id),
    "restore_subscription_destination_rejected_cross_account": (KeyComponent.user,),
}

# Every named entry restore's admission control evaluates, in the order it evaluates them.
RESTORE_ADMISSION_ENTRIES: tuple[str, ...] = (*REQUEST_RATE_ENTRIES,
                                              *PROOF_FINGERPRINT_ENTRIES,
                                              *STORE_SUBSCRIPTION_ENTRIES,
                                              *DESTINATION_USER_ENTRIES)


def assert_restore_admission_required(config: RateLimitsConfig | None = None) -> tuple[str, ...]:
    """`POST /auth/restore-subscription` enforces backend restore admission control under the shared
    contract in `08-rate-limits-and-admission-control.md`.

    The backend limits are additional to Envoy Gateway's, which remains in place: they are keyed by
    restore data only the backend can derive, so no gateway limit already rejects what they reject.
    Restore's challenge-issuance and challenge-validation-failure limits are gone with the challenge
    itself, and the request-rate limits took over the throttling they provided.
    """
    # [impl->req~restore-admission-control-required~1]
    if not GATEWAY_LIMITING_REMAINS:
        raise RestoreAdmissionError("Envoy Gateway rate limiting remains in place")
    configured = REQUIRED_OPERATION_ENTRIES[RESTORE_OPERATION]
    if set(configured) != set(RESTORE_ADMISSION_ENTRIES):
        raise RestoreAdmissionError(
            f"restore_subscription enforces {sorted(RESTORE_ADMISSION_ENTRIES)}")
    if not RESTORE_ADMISSION_PURPOSE:
        raise RestoreAdmissionError("restore admission control exists for a stated purpose")
    entries = set(config.entries) if config is not None else set(configured)
    present = sorted(DELETED_CHALLENGE_ENTRIES & entries)
    if present:
        raise RestoreAdmissionError(f"{present} was deleted with restore's challenge")
    return RESTORE_ADMISSION_ENTRIES


def assert_restore_admission_policy_configured(config: RateLimitsConfig) -> dict[str, tuple[str, ...]]:
    """The configuration file defines the restore admission policy for all five families: request
    rate, proof fingerprints, store subscriptions, destination users, and the two global provider-call
    budgets. A missing entry is a startup configuration error, never a built-in default."""
    # [impl->req~restore-admission-policy-config-required~1]
    missing: list[str] = []
    for family, names in RESTORE_ADMISSION_POLICY.items():
        if not names:
            raise RestoreAdmissionError(f"the restore admission policy defines {family}")
        missing.extend(f"{family}.{name}" for name in names if name not in config.entries)
    if missing:
        raise RestoreAdmissionError(f"{sorted(missing)} is not configured")
    for name, expected in RESTORE_ADMISSION_KEYS.items():
        entry = config.entries[name]
        if entry.policy != expected:
            raise RestoreAdmissionError(f"{name} keys on {'+'.join(expected)}")
    return dict(RESTORE_ADMISSION_POLICY)


def request_rate_entries() -> tuple[str, str]:
    """The restore request-rate limits: one keyed by the verified-token subject, one by the
    destination user the barrier resolved."""
    # [impl->req~restore-admission-limit-request-rate~1]
    subject, user = REQUEST_RATE_ENTRIES
    if RESTORE_ADMISSION_KEYS[subject] != (KeyComponent.issuer, KeyComponent.subject_hash):
        raise RestoreAdmissionError(f"{subject} keys on the verified-token subject")
    if RESTORE_ADMISSION_KEYS[user] != (KeyComponent.user,):
        raise RestoreAdmissionError(f"{user} keys on the destination user")
    return subject, user


def proof_fingerprint_entries() -> tuple[str, str]:
    """The two restore proof-fingerprint limits: a failed-attempt limit and a total-attempt limit,
    both keyed by the server-derived fingerprint of the presented proof."""
    # [impl->req~restore-admission-limit-proof-fingerprints~1]
    failed, total = PROOF_FINGERPRINT_ENTRIES
    if not failed.endswith("_failed") or not total.endswith("_total"):
        raise RestoreAdmissionError("restore fingerprints carry a failed and a total limit")
    for name in (failed, total):
        if RESTORE_ADMISSION_KEYS[name] != (KeyComponent.restore_proof_fingerprint,):
            raise RestoreAdmissionError(f"{name} keys on the restore proof fingerprint")
    return failed, total


def store_subscription_entries() -> tuple[str, str]:
    """The two store-subscription limits, keyed by `(provider, external_id)`: a cross-account
    attempt limit and a live provider verification limit."""
    # [impl->req~restore-admission-limit-store-subscriptions~1]
    cross_account, live_verification = STORE_SUBSCRIPTION_ENTRIES
    for name in STORE_SUBSCRIPTION_ENTRIES:
        if RESTORE_ADMISSION_KEYS[name] != (KeyComponent.provider, KeyComponent.external_id):
            raise RestoreAdmissionError(f"{name} keys on (provider, external_id)")
    if cross_account == live_verification:
        raise RestoreAdmissionError("the cross-account and live-verification limits are separate")
    return cross_account, live_verification


def destination_user_entries() -> tuple[str, ...]:
    """The destination-user limit: rejected cross-account restore attempts, keyed by the
    destination user."""
    # [impl->req~restore-admission-limit-destination-users~1]
    for name in DESTINATION_USER_ENTRIES:
        if RESTORE_ADMISSION_KEYS[name] != (KeyComponent.user,):
            raise RestoreAdmissionError(f"{name} keys on the destination user")
        if "rejected" not in name:
            raise RestoreAdmissionError(f"{name} counts rejected cross-account attempts")
    return DESTINATION_USER_ENTRIES


def provider_call_budget(provider: StoreProvider) -> str:
    """The global live provider-call budget for one store. Apple and Google Play each have their
    own; neither is a sub-budget or a share of the other."""
    # [impl->req~restore-admission-limit-provider-call-budgets~1]
    # [impl->req~restore-coalescing-global-provider-budgets~1]
    budgets = set(PROVIDER_CALL_BUDGETS.values())
    if len(budgets) != len(PROVIDER_CALL_BUDGETS):
        raise RestoreAdmissionError("Apple and Google Play carry separate global budgets")
    missing = sorted(budgets - set(REQUIRED_ADAPTER_ENTRIES))
    if missing:
        raise RestoreAdmissionError(f"{missing} is not a configured global provider-call budget")
    entry = PROVIDER_CALL_BUDGETS.get(provider)
    if entry is None:
        raise RestoreAdmissionError(f"{provider} makes no live restore verification call")
    return entry


# --- The order the checks run in --------------------------------------------------------------


def restore_request_rate_admission(ledger: AdmissionLedger,
                                   audit: RestoreAttemptAudit,
                                   *,
                                   subject_allowed: bool = True,
                                   user_allowed: bool = True) -> tuple[str, str]:
    """The restore request-rate limits run first, before a junk request can force a full
    `audit.auth_events` restore-attempt row.

    Like every admission-control check they stay in the admission phase wherever they sit, so they
    write no audit row of their own — the row this guards against is the attempt's, and it is not
    written here either way.
    """
    # [impl->req~restore-admission-order-request-rate-first~1]
    subject, user = request_rate_entries()
    if ledger.evaluated:
        raise RestoreAdmissionError(
            f"the restore request-rate limits run before {ledger.evaluated}")
    if audit.rows:
        raise RestoreAdmissionError(
            "the request-rate limits run before the restore-attempt audit row")
    ledger.evaluate(subject, RESTORE_ADMISSION_KEYS[subject], allowed=subject_allowed)
    ledger.evaluate(user, RESTORE_ADMISSION_KEYS[user], allowed=user_allowed)
    if audit.rows:
        raise RestoreAdmissionError("an admission check writes no audit row of its own")
    return subject, user


def restore_keyed_limits_admission(ledger: AdmissionLedger,
                                   *,
                                   proof_verified: bool = False,
                                   allowed: Mapping[str, bool] | None = None) -> tuple[str, ...]:
    """The proof-fingerprint, store-subscription and destination-user limits, all of which run
    before restore-proof verification."""
    # [impl->req~restore-admission-order-limits-before-proof-verification~1]
    if proof_verified:
        raise RestoreAdmissionError(
            "the fingerprint, store-subscription and destination limits precede proof verification")
    for name in (*request_rate_entries(),):
        if name not in ledger.evaluated:
            raise RestoreAdmissionError(f"{name} runs before the keyed restore limits")
    verdicts = dict(allowed or {})
    names = (*proof_fingerprint_entries(), *store_subscription_entries(), *destination_user_entries())
    for name in names:
        ledger.evaluate(name, RESTORE_ADMISSION_KEYS[name], allowed=verdicts.get(name, True))
    return names


def verify_restore_proof(ledger: AdmissionLedger,
                         verify: Callable[[], VerifiedTransaction]) -> VerifiedTransaction:
    """Verify the request's own `restore_proof` and resolve it to its `(provider, external_id)`.

    Every named restore admission entry has been evaluated by now: the order is admission and
    limits, then proof verification, then coalescing and the provider call.
    """
    # [impl->req~restore-admission-order-limits-before-proof-verification~1]
    missing = [name for name in RESTORE_ADMISSION_ENTRIES if name not in ledger.evaluated]
    if missing:
        raise RestoreAdmissionError(f"{missing} runs before restore-proof verification")
    ledger.expensive_step(ExpensiveStep.proof_verification)
    return verify()


def assert_admission_order(evaluated: Sequence[str], steps: Sequence[ExpensiveStep]) -> None:
    """The whole order one restore request took: admission and limits, then proof verification,
    then coalescing and the provider call."""
    # [impl->req~restore-admission-order-request-rate-first~1]
    # [impl->req~restore-admission-order-limits-before-proof-verification~1]
    if tuple(evaluated) != RESTORE_ADMISSION_ENTRIES:
        raise RestoreAdmissionError(
            f"restore evaluates {list(RESTORE_ADMISSION_ENTRIES)}, in that order")
    expensive = [step for step in steps
                 if step in (ExpensiveStep.proof_verification,
                             ExpensiveStep.live_store_verification,
                             ExpensiveStep.provider_call)]
    if expensive and expensive[0] is not ExpensiveStep.proof_verification:
        raise RestoreAdmissionError("proof verification precedes coalescing and the provider call")


# --- The provider-call budget ------------------------------------------------------------------

# The accounting unit, stated so it cannot drift: one unit per actual outbound provider attempt,
# acquired one at a time immediately before dispatch. No unit is reserved up front for a maximum
# attempt count, and no per-provider sub-budget or burst allowance exists.
# [impl->req~restore-admission-provider-call-budget-accounting~1]
BUDGET_ACCOUNTING_UNIT: str = "outbound_provider_attempt"
UNITS_PER_ACQUISITION: int = 1
UNITS_RESERVED_UP_FRONT: int = 0
PROVIDER_SUB_BUDGETS: frozenset[str] = frozenset()
PROVIDER_BURST_ALLOWANCES: frozenset[str] = frozenset()

# Budget exhaustion is an admission outcome, never a verification outcome: these are the two
# results it must never be dressed up as.
# [impl->req~restore-admission-provider-call-budget-accounting~1]
BUDGET_IS_NEVER_AUDITED_AS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.restore_store_state_unverified,
})
BUDGET_IS_NEVER_SURFACED_AS: str = "restore_proof_rejected"

# The live verification call each provider's budget meters.
LIVE_VERIFICATION_CALLS: dict[StoreProvider, ProviderCall] = {
    StoreProvider.apple: ProviderCall.apple_live_store_verification,
    StoreProvider.google_play: ProviderCall.google_play_live_store_verification,
}

# Exactly one live provider call per restore request, with no in-request retries.
# [impl->req~restore-admission-one-call-per-request~1]
LIVE_CALLS_PER_REQUEST: int = 1
IN_REQUEST_RETRIES: int = 0


@dataclass(slots=True)
class ProviderCallBudget:
    """One request's use of a global provider-call budget.

    Units are acquired one at a time, immediately before each outbound dispatch, and a dispatched
    call keeps its unit however it resolves — success, error, timeout, or uncertain result. A unit
    acquired but not dispatched because the backend failed first is released; nothing is borrowed,
    queued, or partially refunded.
    """
    provider: StoreProvider
    acquired: int = 0
    dispatched: int = 0
    released: int = 0

    @property
    def entry(self) -> str:
        return provider_call_budget(self.provider)

    @property
    def held(self) -> int:
        return self.acquired - self.dispatched - self.released


def consume_provider_call_unit(limiter: RateLimiter,
                               budget: ProviderCallBudget,
                               key: str,
                               *,
                               endpoint_admission_passed: bool,
                               metrics: RateLimitMetrics | None = None) -> LimitDecision:
    """Atomically check and consume one unit immediately before one outbound provider dispatch.

    The unit is taken through the one shared counter storage, so the budget is enforced atomically
    across every backend replica. If no unit is available the call is not made.
    """
    # [impl->req~restore-admission-provider-call-budget-accounting~1]
    # [impl->req~restore-coalescing-global-provider-budgets~1]
    if PROVIDER_SUB_BUDGETS or PROVIDER_BURST_ALLOWANCES:
        raise RestoreAdmissionError("no per-provider sub-budget or burst allowance exists")
    if UNITS_RESERVED_UP_FRONT or UNITS_PER_ACQUISITION != 1:
        raise RestoreAdmissionError("units are acquired one at a time, never reserved up front")
    if budget.held:
        raise RestoreAdmissionError("a unit is acquired immediately before one dispatch")
    call = LIVE_VERIFICATION_CALLS[budget.provider]
    if budget_entry_for(call) != budget.entry:
        raise RestoreAdmissionError(f"{call} is metered by {budget.entry}")
    decision = consume_budget_unit(limiter, call, key,
                                   endpoint_admission_passed=endpoint_admission_passed,
                                   metrics=metrics)
    if decision.allowed:
        budget.acquired += UNITS_PER_ACQUISITION
    return decision


def dispatch_under_budget(budget: ProviderCallBudget,
                          dispatch: Callable[[], Any]) -> Any:
    """Make the outbound call the acquired unit paid for. The unit stays spent however the call
    resolves; a failure before dispatch releases it instead."""
    # [impl->req~restore-admission-provider-call-budget-accounting~1]
    if budget.held != 1:
        raise RestoreAdmissionError("a dispatch is made under exactly one acquired unit")
    if budget.dispatched >= LIVE_CALLS_PER_REQUEST:
        raise RestoreAdmissionError("exactly one live provider call per restore request")
    budget.dispatched += 1
    return dispatch()


def release_undispatched_unit(budget: ProviderCallBudget) -> None:
    """Release a unit reserved but unused because the backend failed before dispatch."""
    # [impl->req~restore-admission-provider-call-budget-accounting~1]
    if budget.held != 1:
        raise RestoreAdmissionError("only an acquired, undispatched unit is released")
    budget.released += 1


def assert_one_call_per_request(budget: ProviderCallBudget,
                                *,
                                admission_evaluations: int = 1) -> int:
    """Exactly one live provider call per restore request, with no in-request retries. Restore
    admission stays evaluated once per incoming request, so the once-per-request admission check
    and the before-dispatch budget check never diverge."""
    # [impl->req~restore-admission-one-call-per-request~1]
    if IN_REQUEST_RETRIES:
        raise RestoreAdmissionError("the live provider call is never retried in-request")
    if budget.dispatched > LIVE_CALLS_PER_REQUEST:
        raise RestoreAdmissionError(
            f"{budget.dispatched} live provider calls; the rule is {LIVE_CALLS_PER_REQUEST}")
    if admission_evaluations != 1:
        raise RestoreAdmissionError("restore admission is evaluated once per incoming request")
    if budget.dispatched != budget.acquired - budget.released:
        raise RestoreAdmissionError("the admission check and the budget check never diverge")
    return budget.dispatched


def assert_budget_exhaustion_is_admission(*,
                                          audited_result: AuthEventResult | None = None,
                                          client_class: str | None = None) -> None:
    """Budget exhaustion is an admission outcome, not a verification outcome: it is never audited
    as `restore_store_state_unverified` and never surfaces as `restore_proof_rejected`."""
    # [impl->req~restore-admission-provider-call-budget-accounting~1]
    if audited_result is not None and audited_result in BUDGET_IS_NEVER_AUDITED_AS:
        raise RestoreAdmissionError(f"a budget rejection is never audited as {audited_result}")
    if client_class is not None and client_class == BUDGET_IS_NEVER_SURFACED_AS:
        raise RestoreAdmissionError(
            f"a budget rejection never surfaces as {BUDGET_IS_NEVER_SURFACED_AS}")


# --- What a rejection does ----------------------------------------------------------------------


def restore_admission_rejection(attempt: AuthAttempt,
                                telemetry: SecurityTelemetry,
                                decision: LimitDecision,
                                *more: LimitDecision,
                                actor: CoarseActor = CoarseActor.authenticated,
                                metrics: RateLimitMetrics | None = None) -> AdmissionRejection:
    """Reject a restore request under restore admission control.

    The `429`, the admission-phase carve-out and the aggregate-telemetry rule are the shared
    contract's; this is restore taking them rather than restating them, so the rejection writes no
    per-attempt restore audit row and records no secret proof material.
    """
    # [impl->req~restore-admission-rejection-429~1]
    # [impl->req~restore-admission-rejection-carve-out~1]
    # [impl->req~restore-admission-rejection-telemetry-only~1]
    if attempt.operation is not RESTORE_OPERATION:
        raise RestoreAdmissionError(f"{attempt.route} is not the restore route")
    rejection = AdmissionPhase(attempt, telemetry).reject(decision, *more, actor=actor)
    if rejection.error.status_code != ADMISSION_REJECTION_STATUS:
        raise RestoreAdmissionError("restore admission control rejects with 429")
    # The carve-out: admission control rejects before the attempt is admitted to the audited
    # restore path, so there is no restore-attempt row to write.
    # [impl->req~restore-admission-rejection-carve-out~1]
    assert_off_audited_path(rejection, attempt)
    # Bounded aggregate security telemetry, and nothing else.
    # [impl->req~restore-admission-rejection-telemetry-only~1]
    assert_aggregate_only({"route": rejection.telemetry.route,
                           "reason": rejection.telemetry.reason,
                           "actor": str(rejection.telemetry.actor)})
    if metrics is not None:
        metrics.observe(decision)
    return rejection


def provider_call_budget_rejection(attempt: AuthAttempt,
                                   telemetry: SecurityTelemetry,
                                   decision: LimitDecision,
                                   *,
                                   metrics: RateLimitMetrics,
                                   mutations_performed: Iterable[str] = ()) -> AdmissionRejection:
    """Reject a restore request whose provider-call budget had no unit: `429`, no mutation, no
    `audit.auth_events` row, counted on the provider-call budget rejection counter."""
    # [impl->req~restore-admission-provider-call-budget-accounting~1]
    # [impl->req~restore-coalescing-global-provider-budgets~1]
    if decision.allowed:
        raise RestoreAdmissionError(f"{decision.limiter} had a unit available")
    performed = sorted(mutations_performed)
    if performed:
        raise RestoreAdmissionError(f"a budget rejection performs no mutation, but did {performed}")
    assert_budget_exhaustion_is_admission()
    metrics.provider_budget_rejected(decision.limiter)
    rejection = restore_admission_rejection(attempt, telemetry, decision, metrics=metrics)
    if rejection.audit_rows:
        raise RestoreAdmissionError("a provider-call budget rejection writes no audit row")
    return rejection


def assert_telemetry_only(telemetry: SecurityTelemetry,
                          audit: RestoreAttemptAudit,
                          payload: Mapping[str, object]) -> None:
    """For an admission rejection the backend records bounded aggregate security telemetry and
    nothing else: never a per-attempt restore audit row, never secret proof material."""
    # [impl->req~restore-admission-rejection-telemetry-only~1]
    if audit.rows:
        raise RestoreAdmissionError("an admission rejection writes no restore audit row")
    assert_aggregate_only(payload)
    if not telemetry.labels():
        raise RestoreAdmissionError("a suppressed rejection still appears in aggregate telemetry")


# --- Coalescing the live provider call -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProofVerifiedParticipant:
    """A request that may join a coalesced verification: its own `restore_proof` verified —
    cryptographically and structurally, with no provider call — and resolved to this exact
    `(provider, external_id)`."""
    provider: StoreProvider
    external_id: str
    proof_verified: bool = True
    provider_calls_used_to_verify: int = 0

    @property
    def key(self) -> str:
        """The store subscription this participant's own proof resolved to."""
        return f"{self.provider}|{self.external_id}"


def participant(verified: VerifiedTransaction,
                provider: StoreProvider,
                external_id: str,
                *,
                proof_verified: bool = True,
                provider_calls_used_to_verify: int = 0) -> ProofVerifiedParticipant:
    """Build the participant a verified restore proof earns, refusing any proof that resolved to a
    different store subscription than the group's."""
    # [impl->req~restore-coalescing-join-requires-verified-proof~1]
    if not proof_verified:
        raise CoalescingError("a request whose proof fails never joins the group")
    if provider_calls_used_to_verify:
        raise RestoreAdmissionError("restore-proof verification makes no provider call")
    if str(verified.provider) != str(provider) or verified.external_id != external_id:
        raise CoalescingError(
            f"the proof resolved to {verified.provider}|{verified.external_id}, not "
            f"{provider}|{external_id}")
    return ProofVerifiedParticipant(provider=provider, external_id=external_id,
                                    proof_verified=proof_verified,
                                    provider_calls_used_to_verify=provider_calls_used_to_verify)


# What a coalesced call shares, and what it never shares. The payload is the raw provider
# observation of live store state; nothing on it stands in for a follower's own authorization.
# [impl->req~restore-coalescing-shares-only-provider-observation~1]
SHARED_OBSERVATION_FIELDS: frozenset[str] = frozenset({
    "provider", "external_id", "store_state", "observed_at",
})
NEVER_SHARED_FIELDS: frozenset[str] = frozenset({
    "user_id", "destination_user_id", "source_user_id", "account", "restore_proof",
    "proof_fingerprint", "request_context", "subject_hash", "entitled_token", "authorization",
    "grant_id", "access_grant", "purchase_user_id",
})

# The work every follower completes for itself, whatever the shared call observed.
# [impl->req~restore-coalescing-shares-only-provider-observation~1]
FOLLOWER_OWN_WORK: tuple[str, ...] = (
    "user_and_account_authorization",
    "database_conflict_checks",
    "transactional_grant_and_ownership_processing",
)


def assert_observation_only(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """What is shared is the raw provider observation of live store state and nothing else: no
    field derives from another caller's account, proof, or request context, and the payload is
    never a global entitled token attachable to arbitrary callers."""
    # [impl->req~restore-coalescing-shares-only-provider-observation~1]
    borrowed = sorted(set(payload) & NEVER_SHARED_FIELDS)
    if borrowed:
        raise CoalescingError(f"a coalesced observation carries no {borrowed}")
    extra = sorted(set(payload) - SHARED_OBSERVATION_FIELDS)
    if extra:
        raise CoalescingError(f"{extra} is not a raw provider observation of store state")
    return payload


def assert_follower_completes_own_work(*,
                                       follower: ProofVerifiedParticipant,
                                       calling_subject_user_id: Any,
                                       observation: Mapping[str, Any],
                                       completed: Iterable[str]) -> None:
    """A follower's shared observation authorizes nothing by itself: it applies only to the calling
    subject's own restore for its own proof-derived subscription, and the follower still completes
    its own authorization, conflict checks and transactional processing."""
    # [impl->req~restore-coalescing-shares-only-provider-observation~1]
    assert_observation_only(observation)
    if str(observation.get("provider")) != str(follower.provider) or (
            observation.get("external_id") != follower.external_id):
        raise CoalescingError("the outcome applies to the caller's own proof-derived subscription")
    if calling_subject_user_id is None:
        raise CoalescingError("a coalesced outcome is never a global entitled token")
    outstanding = [step for step in FOLLOWER_OWN_WORK if step not in set(completed)]
    if outstanding:
        raise CoalescingError(f"every follower completes its own {outstanding}")


@dataclass(frozen=True, slots=True)
class RestoreVerification:
    """One caller's live verification: the shared store-state observation, and whether this caller
    spent a provider call — and so a budget unit — of its own."""
    observation: Any
    dispatched: bool
    budget_units: int


class RestoreCoalescer:
    """Serializes live provider verification per `(provider, external_id)`.

    Concurrent adoption attempts at the same store subscription share one outbound call instead of
    each spending an Apple or Google call, and a result may be reused afterwards only while it is
    fresh under the configured restore verification freshness bound. Joining is not a consequence of
    arriving: only a request whose own proof verified to this exact store subscription is a
    participant.
    """

    def __init__(self,
                 config: ProviderDampingConfig,
                 *,
                 metrics: RateLimitMetrics | None = None,
                 clock: Callable[[], float] | None = None):
        self._coalescer = ProviderCoalescer(config, metrics=metrics, clock=clock)
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, provider: StoreProvider, external_id: str) -> asyncio.Lock:
        """The `(provider, external_id)` serialization lock. It exists only to avoid simultaneous
        provider calls, and holding or waiting on it confers no result."""
        # [impl->req~restore-coalescing-serialize-provider-verification~1]
        # [impl->req~restore-coalescing-lock-wait-confers-no-result~1]
        return self._locks.setdefault(f"{provider}|{external_id}", asyncio.Lock())

    async def verify(self,
                     joining: ProofVerifiedParticipant,
                     dispatch: Callable[[], Awaitable[Any]],
                     *,
                     budget: Callable[[], int] | None = None) -> RestoreVerification:
        """Verify live store state for this participant, joining an in-flight call or reusing a
        fresh result where that is allowed, and otherwise leading the one shared call.

        Only the request that actually dispatches consumes a budget unit; every waiter shares the
        leader's terminal outcome and launches nothing of its own.
        """
        # [impl->req~restore-coalescing-serialize-provider-verification~1]
        # [impl->req~restore-coalescing-join-requires-verified-proof~1]
        # [impl->req~restore-coalescing-shared-outcome-single-budget-unit~1]
        # [impl->req~restore-coalescing-reuse-only-while-fresh~1]
        if not joining.proof_verified:
            raise CoalescingError("a request joins only after its own restore_proof verified")
        call = LIVE_VERIFICATION_CALLS[joining.provider]
        units = 0

        async def leader() -> Any:
            nonlocal units
            # The budget unit is charged by the request that dispatches, and by nobody else: a
            # single shared attempt debits the budget once, not once per waiter.
            # [impl->req~restore-coalescing-shared-outcome-single-budget-unit~1]
            units = budget() if budget is not None else 1
            return await dispatch()

        outcome = await self._coalescer.lookup(call, joining.key, leader,
                                               verified_key=joining.key)
        if not outcome.dispatched and units:
            raise RestoreAdmissionError("a waiter consumes no budget unit of its own")
        return RestoreVerification(observation=outcome.observation,
                                   dispatched=outcome.dispatched,
                                   budget_units=units)


def assert_lock_wait_confers_no_result(*,
                                       waited_on_lock: bool,
                                       joined_as_participant: bool,
                                       budget_units_consumed: int,
                                       observation: Any = None) -> None:
    """Merely waiting on the `(provider, external_id)` lock confers no result. A request that has
    not joined as a proof-verified participant still requires its own independently budgeted
    verification call after waiting."""
    # [impl->req~restore-coalescing-lock-wait-confers-no-result~1]
    if not waited_on_lock:
        raise RestoreAdmissionError("this request never waited on the serialization lock")
    if joined_as_participant:
        return
    if observation is not None:
        raise CoalescingError("waiting on the lock is not joining: it confers no result")
    if budget_units_consumed < 1:
        raise CoalescingError(
            "a request that did not join makes its own independently budgeted call")


def assert_waiters_share_the_outcome(*,
                                     leader_failed: bool,
                                     waiter_dispatched: bool,
                                     budget_units: int,
                                     waiters: int) -> None:
    """All requests waiting on a coalesced call share its terminal outcome, and a waiting request
    does not launch another provider call when the leader's attempt fails. One shared attempt
    debits the budget once, not once per waiter."""
    # [impl->req~restore-coalescing-shared-outcome-single-budget-unit~1]
    if leader_failed and waiter_dispatched:
        raise CoalescingError("a waiter shares the leader's failure and launches no second call")
    if budget_units != 1:
        raise CoalescingError(f"one shared attempt debits one unit, not {budget_units}")
    if waiters < 0:
        raise CoalescingError("a coalesced group has a non-negative number of waiters")


def freshness_seconds(config: ProviderDampingConfig, provider: StoreProvider) -> float:
    """The configured restore verification freshness bound a coalesced result may be reused
    under. Once the result is stale, a new attempt must obtain a fresh provider verification."""
    # [impl->req~restore-coalescing-reuse-only-while-fresh~1]
    entry = config.entry(LIVE_VERIFICATION_CALLS[provider])
    if entry.freshness_seconds is None or entry.freshness_seconds <= 0:
        raise RestoreAdmissionError(
            f"{provider} live verification carries no configured freshness bound")
    return entry.freshness_seconds


def may_reuse(config: ProviderDampingConfig,
              provider: StoreProvider,
              *,
              age_seconds: float) -> bool:
    """Whether a coalesced live verification result is still reusable."""
    # [impl->req~restore-coalescing-reuse-only-while-fresh~1]
    if age_seconds < 0:
        raise RestoreAdmissionError("a coalesced result is never reused from the future")
    return age_seconds < freshness_seconds(config, provider)


# --- Operational counters -------------------------------------------------------------------------

# The four operational counters restore admission control exposes. They are the shared counters
# `08-rate-limits-and-admission-control.md` defines, read from `RateLimitMetrics` rather than kept
# a second time here.
# [impl->req~restore-admission-operational-counters~1]
RESTORE_ADMISSION_COUNTERS: tuple[str, ...] = (
    "allowed_requests",
    "rejections_429",
    "provider_budget_rejections",
    "coalesced_provider_reuse",
)


def assert_operational_counters(metrics: RateLimitMetrics) -> tuple[str, ...]:
    """The backend exposes counters for allowed restore admissions, restore admission `429`
    rejections, provider-call budget rejections, and coalesced provider verification reuse."""
    # [impl->req~restore-admission-operational-counters~1]
    exposed = metrics.counters()
    missing = [name for name in RESTORE_ADMISSION_COUNTERS if name not in exposed]
    if missing:
        raise RestoreAdmissionError(f"{missing} is not exposed as an operational counter")
    return RESTORE_ADMISSION_COUNTERS
