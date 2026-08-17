"""Handler-side admission control and damping for the two free-credit grant claims.

Envoy Gateway bounds these routes by IP, subject and URL, but it cannot key the conditional work
inside them: whether this request is about to issue an operation challenge, query a device-check
vendor, write a fail-closed vendor bit, validate a Cloudflare bot check, read `providerData` for
the web gate, or activate a grant. So `claim_anonymous_grant` and `claim_registered_grant` enforce
their own named admission entries on top of the gateway's, and on top of the shared adapter and
provider budgets.

Where those checks sit is the whole point of this module: the named handler-side limits run before
the operation challenge is claimed, and the four device-bit provider budgets sit on the other side
of that boundary — after the claim, immediately before the vendor call each one budgets. The
positions themselves are enforced by `ratelimit.ordering.AdmissionLedger`; this file says which
entries apply to which phase of which claim, and what each side of the boundary does on rejection.
"""

from collections.abc import Sequence

from nativespeaker.api.auth.audit import AuthAttempt
from nativespeaker.api.auth.challenges import ChallengeState
from nativespeaker.api.auth.derived_identifiers import DerivedValue
from nativespeaker.api.auth.external_identities import REGISTERED_PROVIDERS, ExternalIdentityRow
from nativespeaker.api.auth.free_grants import claim_admission_pair
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_endpoints import ClaimBranch
from nativespeaker.api.ratelimit.config import (
    DEVICE_BIT_BUDGET_ENTRIES,
    FIREBASE_LOOKUP_ENTRY_KEYS,
    REQUIRED_ADAPTER_ENTRIES,
    REQUIRED_OPERATION_ENTRIES,
    TURNSTILE_ENTRY,
    RateLimitsConfig,
    complete_entries,
    prepare_entries,
)
from nativespeaker.api.ratelimit.keys import KeyComponent
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import (
    READ_CALLS,
    WRITE_CALLS,
    AdmissionLedger,
    AdmissionOrderError,
    DeviceBitCall,
    DeviceBitWrite,
    ExpensiveStep,
    anonymous_grant_admission,
)
from nativespeaker.api.ratelimit.rejection import (
    DEVICE_BIT_BUDGET_RESULTS,
    VERIFICATION_CAPACITY_CLASS,
    AdmissionPhase,
    AdmissionRejection,
    DeviceBitBudgetExhausted,
    SecurityTelemetry,
    device_bit_budget_rejection,
)


class GrantAdmissionError(RuntimeError):
    """A handler-side admission rule of the grant claims was about to be broken."""


# --- Which handler work is abuse-sensitive ----------------------------------------------------

# The conditional work Envoy Gateway cannot key precisely, and which the handler-side entries
# therefore exist to damp.
# [impl->req~grants-handler-admission-required~1]
ABUSE_SENSITIVE_HANDLER_WORK: tuple[str, ...] = (
    "operation_challenge_issuance",
    "device_check_vendor_query",
    "fail_closed_vendor_bit_write",
    "cloudflare_bot_check_validation",
    "web_anonymous_grant_firebase_lookup",
    "grant_activation",
)

# App Attest verification is no longer abuse-sensitive handler work for the anonymous grant: the
# device-check vendor query, the fail-closed bit write and grant activation are.
# [impl->req~grants-app-attest-not-abuse-sensitive~1]
NOT_ABUSE_SENSITIVE_HANDLER_WORK: frozenset[str] = frozenset({"app_attest_verification"})

# Which phase's admission entries damp each piece of that work. Challenge issuance is damped by
# the prepare-phase entries; everything else by the completion entries, which is why they run
# before the challenge is claimed and before any of it starts.
WORK_PHASE: dict[str, str] = {
    "operation_challenge_issuance": "prepare",
    "device_check_vendor_query": "complete",
    "fail_closed_vendor_bit_write": "complete",
    "cloudflare_bot_check_validation": "complete",
    "web_anonymous_grant_firebase_lookup": "complete",
    "grant_activation": "complete",
}


def is_abuse_sensitive_handler_work(step: str) -> bool:
    """Whether a step is abuse-sensitive handler work the named admission entries damp."""
    # [impl->req~grants-handler-admission-required~1]
    # [impl->req~grants-app-attest-not-abuse-sensitive~1]
    if step in NOT_ABUSE_SENSITIVE_HANDLER_WORK:
        return False
    return step in ABUSE_SENSITIVE_HANDLER_WORK


# --- The named handler-side entries -----------------------------------------------------------

FREE_GRANT_CLAIMS: tuple[AuthOperation, ...] = (AuthOperation.claim_anonymous_grant,
                                                AuthOperation.claim_registered_grant)

# The key policy each grant admission entry is configured with. The anonymous pair is keyed on the
# barrier-resolved user with an independent client-IP counter beside it; the registered completion
# adds the redacted IdP-account alias. No entry carries a device-check component in any form.
# [impl->req~grants-anon-challenge-issuance-admission~1]
# [impl->req~grants-anon-completion-admission~1]
# [impl->req~grants-reg-challenge-issuance-admission~1]
# [impl->req~grants-reg-completion-admission~1]
GRANT_ADMISSION_KEYS: dict[str, tuple[KeyComponent, ...]] = {
    "claim_anonymous_grant_prepare": (KeyComponent.user,),
    "claim_anonymous_grant_prepare_ip": (KeyComponent.ip,),
    "claim_anonymous_grant": (KeyComponent.user,),
    "claim_anonymous_grant_ip": (KeyComponent.ip,),
    "claim_registered_grant_prepare": (KeyComponent.user,),
    "claim_registered_grant": (KeyComponent.user, KeyComponent.idp_account_hash),
}

# The vendor-derived material that never becomes part of an admission key, so no admission check
# ever waits on a vendor query for its key.
VENDOR_KEY_MATERIAL: frozenset[str] = frozenset({
    "devicecheck", "devicecheck_bit", "device_check", "device_recall", "play_integrity",
    "bot_check", "turnstile", "vendor_bit"})

# The budgets the handler-side entries are additional to: the shared adapter and provider budgets,
# the four device-bit budgets among them, and the Firebase lookup budgets.
SHARED_BUDGET_ENTRIES: frozenset[str] = frozenset({
    *REQUIRED_ADAPTER_ENTRIES, *DEVICE_BIT_BUDGET_ENTRIES, *FIREBASE_LOOKUP_ENTRY_KEYS,
    TURNSTILE_ENTRY})


def handler_admission_entries(operation: AuthOperation, phase: str) -> tuple[str, ...]:
    """The named handler-side admission entries one claim enforces in one phase."""
    # [impl->req~grants-handler-admission-required~1]
    if operation not in FREE_GRANT_CLAIMS:
        raise GrantAdmissionError(f"{operation} is no free-credit grant claim")
    if phase == "prepare":
        return prepare_entries(operation)
    if phase == "complete":
        return complete_entries(operation)
    raise GrantAdmissionError(f"{phase} is no admission phase of a grant claim")


def assert_handler_admission_required(operation: AuthOperation) -> tuple[str, ...]:
    """Both claims must enforce named endpoint-specific handler-side admission limits, in both
    phases, and those limits are additional to the Envoy Gateway endpoint limits and to the shared
    adapter and provider budgets rather than a restatement of either. Every piece of the
    abuse-sensitive handler work above is damped by one of them."""
    # [impl->req~grants-handler-admission-required~1]
    entries = (*handler_admission_entries(operation, "prepare"),
               *handler_admission_entries(operation, "complete"))
    if not entries:
        raise GrantAdmissionError(f"{operation} enforces no handler-side admission limit")
    for phase in ("prepare", "complete"):
        if not handler_admission_entries(operation, phase):
            raise GrantAdmissionError(f"{operation} enforces no {phase}-phase admission limit")
    # Additional to, never the same counter as, the shared adapter and provider budgets.
    overlap = sorted(set(entries) & SHARED_BUDGET_ENTRIES)
    if overlap:
        raise GrantAdmissionError(
            f"{overlap} is a shared adapter or provider budget, not a handler-side limit")
    for name in entries:
        assert_no_vendor_key_component(name)
    missing = sorted(work for work in ABUSE_SENSITIVE_HANDLER_WORK
                     if not handler_admission_entries(operation, WORK_PHASE[work]))
    if missing:
        raise GrantAdmissionError(f"{missing} is abuse-sensitive work with no admission limit")
    return entries


def assert_no_vendor_key_component(entry: str,
                                   *,
                                   policy: Sequence[KeyComponent] | None = None) -> None:
    """No grant admission entry keys on a device-check, Device Recall or bot-check value, in any
    form, so the admission check never waits on a vendor query for its key."""
    # [impl->req~grants-anon-challenge-issuance-admission~1]
    # [impl->req~grants-anon-completion-admission~1]
    components = tuple(policy) if policy is not None else GRANT_ADMISSION_KEYS.get(entry, ())
    for component in components:
        if any(marker in str(component).lower() for marker in VENDOR_KEY_MATERIAL):
            raise GrantAdmissionError(f"{entry} keys on vendor material through {component}")


def assert_configured_admission_keys(config: RateLimitsConfig) -> None:
    """The configured key policies are the ones this file names, entry for entry."""
    # [impl->req~grants-anon-challenge-issuance-admission~1]
    # [impl->req~grants-anon-completion-admission~1]
    # [impl->req~grants-reg-challenge-issuance-admission~1]
    # [impl->req~grants-reg-completion-admission~1]
    for name, expected in GRANT_ADMISSION_KEYS.items():
        entry = config.entries.get(name)
        if entry is None:
            raise GrantAdmissionError(f"{name} is not configured")
        if entry.policy != expected:
            raise GrantAdmissionError(f"{name} keys on {'+'.join(expected)}")
        assert_no_vendor_key_component(name, policy=entry.policy)


# --- `claim_anonymous_grant` admission --------------------------------------------------------


def anonymous_challenge_issuance_admission(ledger: AdmissionLedger,
                                           *,
                                           ip_allowed: bool = True,
                                           user_allowed: bool = True) -> tuple[str, str]:
    """`POST /auth/claim-anonymous-grant?challenge=true` enforces challenge-issuance admission
    before issuing an operation challenge, keyed by the current user, and enforces the entry's
    independent client-IP counter separately, at route entry. Neither key carries a device-check
    component."""
    # [impl->req~grants-anon-challenge-issuance-admission~1]
    ip_entry, user_entry = claim_admission_pair(ClaimBranch.web, "prepare")
    for name in (ip_entry, user_entry):
        assert_no_vendor_key_component(name)
    if GRANT_ADMISSION_KEYS[user_entry] != (KeyComponent.user,):
        raise GrantAdmissionError(f"{user_entry} is keyed by the current user")
    if GRANT_ADMISSION_KEYS[ip_entry] != (KeyComponent.ip,):
        raise GrantAdmissionError(f"{ip_entry} is the entry's independent client-IP counter")
    if ledger.challenge_issued:
        raise GrantAdmissionError("challenge-issuance admission runs before the challenge issues")
    anonymous_grant_admission(ledger, "prepare", ip_allowed=ip_allowed, user_allowed=user_allowed)
    if not ledger.refused:
        ledger.issue_challenge(handler_admission_entries(AuthOperation.claim_anonymous_grant,
                                                         "prepare"))
    return ip_entry, user_entry


def anonymous_completion_admission(ledger: AdmissionLedger,
                                   *,
                                   identity_resolved: bool,
                                   ip_allowed: bool = True,
                                   user_allowed: bool = True,
                                   branch: ClaimBranch | None = None) -> tuple[str, str]:
    """`POST /auth/claim-anonymous-grant` enforces completion admission after the current identity
    is resolved and before any device-check vendor query or write, the web Firebase Admin
    `providerData` lookup, Cloudflare bot-check validation, grant activation, or any other
    expensive provider work. It is keyed by the current user; the entry's independent client-IP
    counter is enforced separately, at route entry.

    The key policy is identical on every branch, native and web alike, and never carries a
    device-check, Device Recall or bot-check component in any form, so this admission never waits
    on a vendor query for its key.
    """
    # [impl->req~grants-anon-completion-admission~1]
    # [impl->req~grants-anon-logic-admission-applies~1]
    if not identity_resolved:
        raise GrantAdmissionError("completion admission runs after the identity is resolved")
    pair = claim_admission_pair(ClaimBranch.web, "complete")
    for candidate in ClaimBranch:
        if claim_admission_pair(candidate, "complete") != pair:
            raise GrantAdmissionError(
                "the completion key policy is identical on every branch, native and web alike")
    if branch is not None and claim_admission_pair(branch, "complete") != pair:
        raise GrantAdmissionError(f"{branch} takes the same completion admission pair")
    ip_entry, user_entry = pair
    if GRANT_ADMISSION_KEYS[user_entry] != (KeyComponent.user,):
        raise GrantAdmissionError(f"{user_entry} is keyed by the current user")
    for name in pair:
        assert_no_vendor_key_component(name)
    if ledger.expensive_steps:
        raise GrantAdmissionError(
            "completion admission precedes every vendor query, lookup and activation")
    anonymous_grant_admission(ledger, "complete", ip_allowed=ip_allowed, user_allowed=user_allowed)
    return pair


def web_provider_data_lookup(ledger: AdmissionLedger) -> ExpensiveStep:
    """The web gate's `providerData` lookup runs after the existing completion-admission boundary
    and before activation. No new named admission-budget entry is introduced for the web gate: the
    anonymous completion entries are the ones it runs behind."""
    # [impl->req~grants-anon-completion-admission~1]
    assert_no_new_web_gate_entry()
    if ExpensiveStep.database_mutation in ledger.expensive_steps:
        raise GrantAdmissionError("the providerData lookup runs before activation")
    ledger.expensive_step(ExpensiveStep.firebase_lookup)
    return ExpensiveStep.firebase_lookup


def assert_no_new_web_gate_entry() -> None:
    """The web gate introduces no named admission-budget entry of its own."""
    # [impl->req~grants-anon-completion-admission~1]
    configured = set(REQUIRED_OPERATION_ENTRIES[AuthOperation.claim_anonymous_grant])
    expected = {"claim_anonymous_grant_prepare", "claim_anonymous_grant_prepare_ip",
                "claim_anonymous_grant", "claim_anonymous_grant_ip"}
    if configured != expected:
        raise GrantAdmissionError(
            f"the anonymous claim carries {sorted(configured)}, not a new web-gate entry")


# --- `claim_registered_grant` admission -------------------------------------------------------

REGISTERED_PREPARE_ENTRY: str = "claim_registered_grant_prepare"
REGISTERED_COMPLETE_ENTRY: str = "claim_registered_grant"


def registered_challenge_issuance_admission(ledger: AdmissionLedger,
                                            *,
                                            allowed: bool = True) -> str:
    """`POST /auth/claim-registered-grant?challenge=true` enforces challenge-issuance admission
    before issuing an operation challenge, keyed by the current user."""
    # [impl->req~grants-reg-challenge-issuance-admission~1]
    policy = GRANT_ADMISSION_KEYS[REGISTERED_PREPARE_ENTRY]
    if policy != (KeyComponent.user,):
        raise GrantAdmissionError(f"{REGISTERED_PREPARE_ENTRY} is keyed by the current user")
    if ledger.challenge_issued:
        raise GrantAdmissionError("challenge-issuance admission runs before the challenge issues")
    ledger.evaluate(REGISTERED_PREPARE_ENTRY, policy, allowed=allowed)
    if not ledger.refused:
        ledger.issue_challenge(handler_admission_entries(AuthOperation.claim_registered_grant,
                                                         "prepare"))
    return REGISTERED_PREPARE_ENTRY


def registered_completion_admission(ledger: AdmissionLedger,
                                    row: ExternalIdentityRow,
                                    alias: DerivedValue,
                                    *,
                                    allowed: bool = True,
                                    provider_data_lookups: int = 0,
                                    firebase_calls_for_alias: int = 0) -> str:
    """The `claim_registered_grant` named entry is keyed by `user + idp_account_hash`, so it
    applies only once that alias has been derived from the current linked identity row's stored
    provider and stored `provider_uid`. The derivation needs no Firebase call, and the completion
    admission is enforced once the key exists and before the operation's mandatory Firebase Admin
    `providerData` confirmation.

    A row with no stored `provider_uid` never reaches this check: it follows the registered-grant
    policy rejection path instead.
    """
    # [impl->req~grants-reg-completion-admission~1]
    from nativespeaker.api.auth.registered_grant_failures import (  # noqa: PLC0415
        RegClaimCondition,
        registered_condition_rejected,
    )

    if row.provider not in REGISTERED_PROVIDERS:
        raise registered_condition_rejected(
            RegClaimCondition.stored_provider_not_google_or_apple,
            "the registered claim needs a stored google or apple provider")
    if not row.provider_uid:
        # The registered-grant policy rejection path, not an admission decision.
        raise registered_condition_rejected(
            RegClaimCondition.stored_provider_uid_absent,
            "a row without provider_uid derives no idp_account_hash")
    if firebase_calls_for_alias:
        raise GrantAdmissionError("the alias derivation needs no Firebase call")
    if provider_data_lookups:
        raise GrantAdmissionError(
            "completion admission runs before the mandatory providerData confirmation")
    if not alias.digest:
        raise GrantAdmissionError("the completion key carries the derived idp_account_hash")
    policy = GRANT_ADMISSION_KEYS[REGISTERED_COMPLETE_ENTRY]
    if policy != (KeyComponent.user, KeyComponent.idp_account_hash):
        raise GrantAdmissionError(
            f"{REGISTERED_COMPLETE_ENTRY} keys on user+idp_account_hash")
    ledger.evaluate(REGISTERED_COMPLETE_ENTRY, policy, allowed=allowed)
    return REGISTERED_COMPLETE_ENTRY


# --- The boundary: admission first, then the challenge claim ----------------------------------


def assert_admission_precedes_challenge_claim(ledger: AdmissionLedger,
                                              operation: AuthOperation) -> tuple[str, ...]:
    """The named handler-side admission limits are placed before the operation challenge is
    claimed, and so before it is consumed and before the request enters the normal audited
    completion path."""
    # [impl->req~grants-admission-before-challenge-claim~1]
    entries = handler_admission_entries(operation, "complete")
    if ledger.challenge_claimed:
        raise GrantAdmissionError(
            f"{operation} evaluates {list(entries)} before claiming the challenge")
    missing = [name for name in entries if name not in ledger.evaluated]
    if missing:
        raise GrantAdmissionError(f"{missing} must be evaluated before the challenge claim")
    return entries


def admission_rejection_leaves_challenge_unclaimed(attempt: AuthAttempt,
                                                   telemetry: SecurityTelemetry,
                                                   decision: LimitDecision,
                                                   *,
                                                   challenge_state: ChallengeState =
                                                   ChallengeState.issued) -> AdmissionRejection:
    """An admission rejection at that boundary leaves the challenge unclaimed. What such a
    rejection does — the `429`, the aggregate telemetry, no audit row and no consumed challenge —
    is governed by `08-rate-limits-and-admission-control.md` and taken from there rather than
    restated here."""
    # [impl->req~grants-admission-before-challenge-claim~1]
    # [impl->req~grants-anon-logic-admission-applies~1]
    if challenge_state is ChallengeState.claimed:
        raise GrantAdmissionError("the admission limits run before the challenge is claimed")
    rejection = AdmissionPhase(attempt, telemetry,
                               challenge_state=challenge_state).reject(decision)
    if rejection.challenge_state is not challenge_state:
        raise GrantAdmissionError("an admission rejection leaves the challenge unclaimed")
    return rejection


# --- The device-bit budgets, on the other side of the boundary --------------------------------

# The four device-bit provider budgets. They are provider budgets, not handler-side admission
# limits: each is checked after the operation challenge has been claimed, immediately before the
# vendor call it budgets.
# [impl->req~grants-device-bit-budgets-post-claim~1]
DEVICE_BIT_BUDGETS: tuple[str, ...] = DEVICE_BIT_BUDGET_ENTRIES


def assert_budgets_are_not_handler_admission() -> None:
    """The four device-bit budgets are on the other side of the admission boundary: none of them
    is one of the claims' handler-side admission entries."""
    # [impl->req~grants-device-bit-budgets-post-claim~1]
    handler = {name for operation in FREE_GRANT_CLAIMS
               for phase in ("prepare", "complete")
               for name in handler_admission_entries(operation, phase)}
    overlap = sorted(handler & set(DEVICE_BIT_BUDGETS))
    if overlap:
        raise GrantAdmissionError(f"{overlap} is a provider budget, not an admission limit")
    if tuple(DEVICE_BIT_BUDGET_RESULTS) != DEVICE_BIT_BUDGETS:
        raise GrantAdmissionError("one internal result per budget entry, in that order")


def device_bit_budget_step(ledger: AdmissionLedger,
                           call: DeviceBitCall,
                           *,
                           operation: AuthOperation,
                           allowed: bool = True,
                           confirmed: bool = True) -> DeviceBitWrite | None:
    """Check one device-bit budget and, if it has capacity, make the vendor call it budgets.

    Exhaustion rejects the claim with `verification_temporarily_unavailable`, never with the
    admission `429`; it creates no grant and does not attempt the read or write whose budget was
    unavailable. Because the budget is checked after the challenge has been claimed, the attempt is
    already on the audited attempt path: the rejection is durably audited as a normal completion
    attempt whose single `audit.auth_events` row names the exhausted budget, and the claimed
    challenge is consumed with it rather than returned to the issued state.
    """
    # [impl->req~grants-device-bit-budgets-post-claim~1]
    assert_budgets_are_not_handler_admission()
    if operation not in FREE_GRANT_CLAIMS:
        raise GrantAdmissionError(f"{operation} charges no device-bit budget")
    entry = DEVICE_BIT_BUDGETS[_budget_index(call)]
    # The ledger enforces the position: after the claim, immediately before the call, and a
    # challenge that failed validation charges nothing.
    ledger.check_device_bit_budget(call, allowed=allowed)
    if not allowed:
        raise device_bit_budget_exhausted(entry, operation)
    return ledger.vendor_device_bit_call(call, confirmed=confirmed)


def _budget_index(call: DeviceBitCall) -> int:
    from nativespeaker.api.ratelimit.ordering import DEVICE_BIT_BUDGET  # noqa: PLC0415

    return DEVICE_BIT_BUDGETS.index(DEVICE_BIT_BUDGET[call])


def device_bit_budget_exhausted(entry: str,
                                operation: AuthOperation) -> DeviceBitBudgetExhausted:
    """The rejection an exhausted device-bit budget earns, built through the one rejection path
    `08-rate-limits-and-admission-control.md` owns."""
    # [impl->req~grants-device-bit-budgets-post-claim~1]
    rejection = device_bit_budget_rejection(entry, operation,
                                           challenge_state=ChallengeState.claimed)
    if rejection.client.status == 429:
        raise GrantAdmissionError("an exhausted device-bit budget is never the admission 429")
    if str(rejection.client.body.get("code")) != str(VERIFICATION_CAPACITY_CLASS):
        raise GrantAdmissionError(f"{entry} exhaustion surfaces as {VERIFICATION_CAPACITY_CLASS}")
    if rejection.grant_issued or rejection.vendor_call_performed:
        raise GrantAdmissionError("an exhausted budget creates no grant and makes no vendor call")
    if rejection.challenge_state is not ChallengeState.consumed:
        raise GrantAdmissionError("the claimed challenge is consumed with the rejection")
    if rejection.audit_rows != 1:
        raise GrantAdmissionError("the attempt writes its single audit.auth_events row")
    if rejection.result is not DEVICE_BIT_BUDGET_RESULTS[entry]:
        raise GrantAdmissionError(f"{entry} audits as {DEVICE_BIT_BUDGET_RESULTS[entry]}")
    return DeviceBitBudgetExhausted(rejection)


def assert_exhausted_budget_stops_the_grant(ledger: AdmissionLedger) -> None:
    """A read-budget rejection stops every later step of the claim; a write-budget rejection stops
    the write and the grant even where the read already succeeded."""
    # [impl->req~grants-device-bit-budgets-post-claim~1]
    if not ledger.refused:
        raise GrantAdmissionError("no budget was exhausted on this claim")
    try:
        ledger.insert_grant_row()
    except AdmissionOrderError:
        return
    raise GrantAdmissionError("a claim whose budget was exhausted creates no grant row")


def budget_call_kinds() -> tuple[frozenset[DeviceBitCall], frozenset[DeviceBitCall]]:
    """The read calls and the write calls, each with its own budget checked immediately before
    it: the read budget before the device-bit read, the write budget before the device-bit
    write."""
    # [impl->req~grants-device-bit-budgets-post-claim~1]
    if READ_CALLS & WRITE_CALLS:
        raise GrantAdmissionError("a device-bit call is either a read or a write")
    return READ_CALLS, WRITE_CALLS


def assert_failed_challenge_charges_nothing(ledger: AdmissionLedger) -> None:
    """A challenge that fails validation is rejected and audited as that challenge error before
    the claim, and charges no device-bit budget."""
    # [impl->req~grants-device-bit-budgets-post-claim~1]
    if not ledger.challenge_failed:
        raise GrantAdmissionError("this attempt's challenge did not fail validation")
    if ledger.budgets_checked:
        raise GrantAdmissionError("a failed challenge charges no device-bit budget")
