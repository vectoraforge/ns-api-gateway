"""Live store-state verification: the one provider call the adoption branch makes.

Adoption attaches a subscription nobody owns, so the canonical row is not enough to authorize it:
the backend asks the store itself whether the subscription is entitled right now. That call is made
once, before the locked mutation transaction is entered, with backend-held provider credentials and
inputs derived only from server-verified restore material. Its outcome is recorded — never its raw
payload — and the locked phase consumes that record and nothing else.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.restore import (
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
)
from nativespeaker.api.auth.restore_flow import VerifiedTransaction
from nativespeaker.api.auth.restore_operation import RESTORE_MUTATIONS
from nativespeaker.api.auth.restore_phases import (
    LIVE_LOOKUP_INPUT_SOURCES,
    NON_ENTITLED_LIVE_STATES,
    LiveStoreVerification,
    LockedPhaseLedger,
    step_17_live_verification_freshness,
)
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.grants import is_product_entitled
from nativespeaker.api.ratelimit.providers import ProviderCall, ProviderDampingConfig


class LiveVerificationError(RestoreContractError):
    """The live store-state verification was about to run outside its own rules."""


class LiveDecision(StrEnum):
    """The high-level decision the outcome records."""
    entitled = "entitled"
    not_entitled = "not_entitled"
    unavailable = "unavailable"


# The provider damping entry each provider's live verification runs under.
LIVE_VERIFICATION_CALL: dict[StoreProvider, ProviderCall] = {
    StoreProvider.apple: ProviderCall.apple_live_store_verification,
    StoreProvider.google_play: ProviderCall.google_play_live_store_verification,
}


# --- Common rules ---------------------------------------------------------------------------------


def assert_adoption_only(branch: RestoreBranch, *, verification_performed: bool) -> bool:
    """The unclaimed-subscription adoption branch must live-verify current store state through the
    provider's server-side API before entering the locked mutation transaction.

    Same-account restore is not subject to this section: it is authorized by the current owner on
    the canonical row equaling the destination user, the resolution or insert-once creation of the
    `core.store_purchases` row, and a product-entitled current state, and gains no live provider
    verification requirement.
    """
    # [impl->req~restore-live-verification-adoption-only~1]
    if branch is RestoreBranch.adoption:
        if not verification_performed:
            raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                                   "adoption requires live store-state verification")
        return True
    if verification_performed:
        raise LiveVerificationError(
            "same-account restore gains no live provider verification requirement")
    return False


def assert_before_locked_transaction(call: str,
                                     *,
                                     locks_held: bool,
                                     locked_phase_consumes: str = "recorded_outcome") -> str:
    """Live store-state verification is performed before the locked mutation transaction is
    entered, not inside it. The locked mutation transaction makes no Apple or Google network call
    and retries no provider request while holding restore mutation locks; it consumes the recorded
    pre-transaction outcome only, via the freshness-and-correspondence recheck."""
    # [impl->req~restore-live-verification-before-locked-transaction~1]
    if locks_held:
        raise LiveVerificationError(f"{call} runs before the restore mutation locks are held")
    if locked_phase_consumes != "recorded_outcome":
        raise LiveVerificationError(
            f"the locked phase consumes the recorded outcome, not {locked_phase_consumes}")
    return call


def assert_after_barrier_and_proof(*,
                                   barrier_admitted: bool,
                                   proof_verified: bool,
                                   rejected: bool = False,
                                   rejection_result: AuthEventResult | None = None,
                                   rejection_transaction: object | None = None,
                                   mutations_performed: Iterable[str] = ()) -> None:
    """Live store-state verification runs only after the shared barrier has admitted the request and
    restore's own proof verification has passed.

    Any rejection it produces — non-entitled live state, or provider unavailability after the
    configured retry budget, both audited as `restore_store_state_unverified` — writes the
    `audit.auth_events` row in one pre-transaction rejection transaction while performing no restore
    mutation.
    """
    # [impl->req~restore-live-verification-after-barrier-and-proof~1]
    if not barrier_admitted:
        raise LiveVerificationError("the shared barrier admits the request before live verification")
    if not proof_verified:
        raise LiveVerificationError("restore's own proof verification passes before live verification")
    offending = sorted(set(mutations_performed) & RESTORE_MUTATIONS)
    if offending:
        raise LiveVerificationError(f"live verification performs no restore mutation: {offending}")
    if not rejected:
        return
    if rejection_result is not AuthEventResult.restore_store_state_unverified:
        raise LiveVerificationError(
            f"{rejection_result} is no live-verification rejection; it audits as "
            f"{AuthEventResult.restore_store_state_unverified}")
    if rejection_transaction is None:
        raise LiveVerificationError(
            "the rejection writes its audit row in one pre-transaction rejection transaction")


# Entitlement evidence the backend must not derive the adoption decision from.
CACHED_ENTITLEMENT_SOURCES: frozenset[str] = frozenset({
    "cached_subscription_state", "prior_webhook_delivery", "core_subscriptions_status_alone",
})


def assert_no_cached_state(sources: Iterable[str] = (),
                           *, live_verification_performed: bool = True) -> bool:
    """The backend must not derive entitlement from cached subscription state, prior webhook
    deliveries, or the current `core.subscriptions` state alone for the adoption branch: the current
    row's status is necessary but not sufficient, and live verification is mandatory."""
    # [impl->req~restore-live-verification-no-cached-state~1]
    borrowed = sorted(set(sources) & CACHED_ENTITLEMENT_SOURCES)
    if borrowed:
        raise LiveVerificationError(f"{borrowed} does not establish entitlement for adoption")
    if not live_verification_performed:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "live verification is mandatory for adoption")
    return True


@dataclass(frozen=True, slots=True)
class AppleCredentials:
    """The backend-held App Store Server API identity, read from the application configuration."""
    bundle_id: str
    team_id: str
    backend_held: bool = True


@dataclass(frozen=True, slots=True)
class GooglePlayCredentials:
    """The backend-held Google service account authorized for the Google Play Developer API."""
    package_name: str
    service_account_email: str
    service_account_private_key: str
    backend_held: bool = True


# The configuration keys each provider's live verification cannot run without.
APPLE_REQUIRED_CONFIG: tuple[str, ...] = ("apple.bundle_id", "apple.team_id")
GOOGLE_REQUIRED_CONFIG: tuple[str, ...] = ("google_play.package_name",
                                           "google_play.service_account_email",
                                           "google_play.service_account_private_key")


def _configured(raw: Mapping[str, Any], dotted: str) -> str:
    """One dotted configuration key, or a fail-closed error naming it."""
    node: Any = raw
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise LiveVerificationError(f"{dotted} is not configured")
        node = node[part]
    if not isinstance(node, str) or not node.strip():
        raise LiveVerificationError(f"{dotted} is not configured")
    return node


def apple_credentials(raw_config: Mapping[str, Any]) -> AppleCredentials:
    """The configured Apple bundle ID and team identifier, held by the backend."""
    # [impl->req~restore-live-verification-backend-credentials-and-inputs~1]
    bundle_id, team_id = (_configured(raw_config, key) for key in APPLE_REQUIRED_CONFIG)
    return AppleCredentials(bundle_id=bundle_id, team_id=team_id)


def google_credentials(raw_config: Mapping[str, Any]) -> GooglePlayCredentials:
    """The configured Google Play package name and the backend-held service account."""
    # [impl->req~restore-live-verification-backend-credentials-and-inputs~1]
    package, email, key = (_configured(raw_config, name) for name in GOOGLE_REQUIRED_CONFIG)
    return GooglePlayCredentials(package_name=package, service_account_email=email,
                                 service_account_private_key=key)


def assert_backend_credentials_and_inputs(
        *,
        credentials: AppleCredentials | GooglePlayCredentials,
        input_sources: Iterable[str] = ("server_verified_restore_material",),
        client_supplied_parameters: Iterable[str] = ()) -> tuple[str, ...]:
    """Live verification must use backend-held provider credentials and must derive its lookup
    inputs only from server-verified restore material and the locally resolved subscription state
    read non-locking from `core.subscriptions`; client input must not parameterize the provider call
    beyond the verified identifiers extracted from the server-verified `restore_proof`."""
    # [impl->req~restore-live-verification-backend-credentials-and-inputs~1]
    if not credentials.backend_held:
        raise LiveVerificationError("the provider call uses backend-held provider credentials")
    supplied = sorted(set(client_supplied_parameters))
    if supplied:
        raise LiveVerificationError(f"client input does not parameterize the call with {supplied}")
    borrowed = sorted(set(input_sources) - LIVE_LOOKUP_INPUT_SOURCES)
    if borrowed:
        raise LiveVerificationError(f"{borrowed} is no permitted live-lookup input source")
    return tuple(sorted(set(input_sources)))


def confirm_currently_entitled(observed: SubscriptionStatus | str | None) -> SubscriptionStatus:
    """Live verification must confirm that the subscription is currently entitled at the store: not
    expired, not revoked, not refunded in a way that voids entitlement, and otherwise satisfying the
    configured product-entitlement policy."""
    # [impl->req~restore-live-verification-confirm-currently-entitled~1]
    if observed is None or str(observed) in NON_ENTITLED_LIVE_STATES:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               f"live store state {observed} is not entitlement")
    try:
        status = SubscriptionStatus(str(observed))
    except ValueError:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               f"live store state {observed} is not a known state") from None
    if not is_product_entitled(status):
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               f"live store state {status} is not product-entitled")
    return status


def assert_non_entitled_rejects(observed: SubscriptionStatus | str | None,
                                *, mutations_performed: Iterable[str] = ()) -> SubscriptionStatus:
    """If the provider call returns a state that is missing, unknown, expired, revoked, refunded so
    as to void entitlement, or otherwise non-entitled, the adoption branch must reject with
    `restore_store_state_unverified` and perform no mutation."""
    # [impl->req~restore-live-verification-non-entitled-rejects~1]
    offending = sorted(set(mutations_performed) & RESTORE_MUTATIONS)
    if offending:
        raise LiveVerificationError(f"a non-entitled live state performs no {offending}")
    return confirm_currently_entitled(observed)


# The normative one-call rule: exactly one live provider call per restore request, no in-request
# retries, and no retry configuration knob. The two files that reference this rule do not restate
# it.
LIVE_VERIFICATION_CALLS_PER_REQUEST: int = 1
IN_REQUEST_RETRIES: int = 0
RETRY_CONFIGURATION_KNOBS: frozenset[str] = frozenset()
REFERENCING_FILES: tuple[str, ...] = ("05-proof-adapters-and-derived-identifiers.md",
                                      "08-rate-limits-and-admission-control.md")


def assert_one_call_rule(*,
                         calls_made: int,
                         admission_checks_passed: bool,
                         proof_verified: bool,
                         locks_held: bool = False,
                         retries: int = 0,
                         retry_knobs: Iterable[str] = ()) -> int:
    """Exactly one live provider call per restore request, with no in-request retries and no retry
    configuration knob.

    The call is dispatched during the pre-transaction phase, after all backend restore admission
    checks have passed and after the request's own `restore_proof` has been verified; the locked
    phase never makes or retries provider requests.
    """
    # [impl->req~restore-live-verification-one-call-rule~1]
    if sorted(set(retry_knobs) | RETRY_CONFIGURATION_KNOBS):
        raise LiveVerificationError("restore live verification has no retry configuration knob")
    if retries != IN_REQUEST_RETRIES:
        raise LiveVerificationError("the single live verification call is never retried in-request")
    if calls_made > LIVE_VERIFICATION_CALLS_PER_REQUEST:
        raise LiveVerificationError(
            f"one restore request makes {LIVE_VERIFICATION_CALLS_PER_REQUEST} live provider call")
    if locks_held:
        raise LiveVerificationError("the locked phase never makes or retries provider requests")
    if calls_made and not (admission_checks_passed and proof_verified):
        raise LiveVerificationError(
            "the call is dispatched after admission control and after proof verification")
    return calls_made


def assert_no_retry_budget(config: ProviderDampingConfig, provider: StoreProvider) -> None:
    """The configured damping for this call carries no retry budget at all: the one-call rule is
    what fixes its call count."""
    # [impl->req~restore-live-verification-one-call-rule~1]
    entry = config.entry(LIVE_VERIFICATION_CALL[provider])
    if entry.retry_budget is not None or entry.max_attempts != LIVE_VERIFICATION_CALLS_PER_REQUEST:
        raise LiveVerificationError(
            f"{provider} live verification is budgeted for exactly one attempt, with no retry")


# A later attempt is a new request, not a continuation of this one.
REINITIATION_IS_A_NEW_REQUEST: bool = True


def fail_closed_on_failure(failure: str, *, retried: bool = False) -> RestoreRejection:
    """On failure or timeout of the single call — including a transient failure that a retry might
    once have papered over — the request fails closed with `restore_store_state_unverified`.

    The user may re-initiate the restore later; that is a new request and passes normal admission and
    provider-budget checks again.
    """
    # [impl->req~restore-live-verification-fail-closed-on-failure~1]
    if retried:
        raise LiveVerificationError("a failed live verification is not retried inside the request")
    if not REINITIATION_IS_A_NEW_REQUEST:
        raise LiveVerificationError("a later restore is a new request")
    return RestoreRejection(AuthEventResult.restore_store_state_unverified,
                            f"the live store-state verification failed: {failure}")


# Failures that are not retryable at all, and are not transient conditions to wait out.
NON_RETRYABLE_FAILURES: frozenset[str] = frozenset({
    "declared_outage", "persistent_malformed_response",
    "persistent_integration_authentication_failure",
})


def assert_non_retryable_failure_rejects(failure: str) -> RestoreRejection:
    """If the provider call fails for non-retryable reasons — a declared outage, a persistent
    malformed response, a persistent integration authentication failure — the adoption branch must
    reject with `restore_store_state_unverified`."""
    # [impl->req~restore-live-verification-non-retryable-failure-rejects~1]
    if failure not in NON_RETRYABLE_FAILURES:
        raise LiveVerificationError(f"{failure} is no declared non-retryable live-verification failure")
    return fail_closed_on_failure(failure)


def record_outcome(verified: VerifiedTransaction,
                   *,
                   status: SubscriptionStatus,
                   subscription_id: UUID | None,
                   canonical_row_absent: bool,
                   verified_at: datetime) -> LiveStoreVerification:
    """The pre-transaction verification outcome is recorded together with the store subscription it
    covers — the resolved `(provider, external_id)`, and the specific current `core.subscriptions.id`
    whose state it covered where a canonical row existed, or a note of that row's absence on the
    adoption-with-creation path — and a server-issued verification timestamp."""
    # [impl->req~restore-live-verification-record-outcome-and-recheck~1]
    if canonical_row_absent != (subscription_id is None):
        raise LiveVerificationError(
            "the record names the canonical row it covered, or notes that row's absence")
    return LiveStoreVerification(provider=verified.provider,
                                 external_id=verified.external_id,
                                 subscription_id=subscription_id,
                                 canonical_row_absent=canonical_row_absent,
                                 verified_at=verified_at,
                                 status=status)


def consume_recorded_outcome(verification: LiveStoreVerification | None,
                             *,
                             ledger: LockedPhaseLedger,
                             locked_key: tuple[StoreProvider, str],
                             locked_subscription_id: UUID | None,
                             now: datetime,
                             freshness_seconds: float) -> LiveStoreVerification | None:
    """The locked phase consumes the record via the freshness-and-correspondence recheck, which
    rejects with `restore_store_state_unverified` when the record is stale under the configured
    bound, or no longer corresponds to the store subscription resolved inside the lock — a mismatch
    on the recorded `(provider, external_id)`, or, where the record carries one, on the recorded
    `core.subscriptions.id`."""
    # [impl->req~restore-live-verification-record-outcome-and-recheck~1]
    return step_17_live_verification_freshness(verification,
                                               ledger=ledger,
                                               branch=RestoreBranch.adoption,
                                               locked_key=locked_key,
                                               locked_subscription_id=locked_subscription_id,
                                               now=now,
                                               freshness_seconds=freshness_seconds)


def freshness_bound(config: ProviderDampingConfig, provider: StoreProvider) -> float:
    """The pre-transaction verification freshness bound is deployment policy, read from the
    configured damping entry for this provider's live verification call."""
    # [impl->req~restore-live-verification-freshness-bound~1]
    entry = config.entry(LIVE_VERIFICATION_CALL[provider])
    if entry.freshness_seconds is None or entry.freshness_seconds <= 0:
        raise LiveVerificationError(
            f"{provider} live verification has no configured freshness bound")
    return entry.freshness_seconds


def assert_within_freshness_bound(verification: LiveStoreVerification,
                                  *,
                                  now: datetime,
                                  freshness_seconds: float,
                                  extended: bool = False,
                                  re_run: bool = False) -> float:
    """The implementation must reject a recorded verification whose age at the locked-phase recheck
    exceeds the configured bound, even if the verification originally succeeded. The locked phase
    must not extend, refresh or re-run live verification under any circumstance."""
    # [impl->req~restore-live-verification-freshness-bound~1]
    if extended or re_run:
        raise LiveVerificationError(
            "the locked phase never extends, refreshes or re-runs live verification")
    age = (now - verification.verified_at).total_seconds()
    if age < 0 or age > freshness_seconds:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "the recorded live verification is stale")
    return age


# Raw provider material that never reaches a stored row.
RAW_RESPONSE_FIELDS: frozenset[str] = frozenset({
    "raw_response", "response_body", "signed_payload", "signed_transaction_info",
    "signed_renewal_info", "jws", "payload", "provider_payload",
})
NO_RAW_PERSISTENCE_TABLES: tuple[str, ...] = ("audit.auth_events", "core.subscriptions")


def assert_no_raw_response_persistence(recorded: Mapping[str, Any],
                                       *, table: str) -> Mapping[str, Any]:
    """Live verification responses must not be persisted in raw form on `audit.auth_events` or
    `core.subscriptions`; only redacted, server-derived fingerprints and structured non-secret
    outcome context may be recorded."""
    # [impl->req~restore-live-verification-no-raw-response-persistence~1]
    if table not in NO_RAW_PERSISTENCE_TABLES:
        raise LiveVerificationError(f"{table} stores no live-verification outcome")
    raw = sorted(set(recorded) & RAW_RESPONSE_FIELDS)
    if raw:
        raise LiveVerificationError(f"{raw} is raw provider material and is never persisted")
    return recorded


# Who may update the canonical row's state. Live verification is neither of them.
CANONICAL_STATE_UPDATERS: frozenset[str] = frozenset({
    "webhook_ingestion_pipeline", "restore_adoption_mutation",
})


def assert_no_canonical_state_update(updates: Iterable[str] = (),
                                     *,
                                     live_status: SubscriptionStatus | None = None,
                                     current_status: SubscriptionStatus | None = None) -> bool:
    """Live verification must not trigger a webhook-equivalent canonical-state update on
    `core.subscriptions` from this code path; canonical-state updates remain the webhook ingestion
    pipeline's responsibility, or — for restore-driven owner changes — the adoption mutation step's.

    The adoption branch may, however, reject when live state contradicts the current row's
    product-entitlement status: the live state is authoritative for its authorization decision.
    """
    # [impl->req~restore-live-verification-no-canonical-state-update~1]
    attempted = sorted(set(updates))
    if attempted:
        raise LiveVerificationError(
            f"live verification updates no canonical state; {sorted(CANONICAL_STATE_UPDATERS)} do")
    if (live_status is not None and current_status is not None
            and is_product_entitled(current_status) and not is_product_entitled(live_status)):
        raise RestoreRejection(
            AuthEventResult.restore_store_state_unverified,
            "live state contradicts the current row's product-entitlement status")
    return True


# --- Apple-provider rules -------------------------------------------------------------------------

# A current App Store Server API endpoint, or its successor.
APPLE_API_SURFACE: str = "Get All Subscription Statuses"
APPLE_API_SURFACES: frozenset[str] = frozenset({APPLE_API_SURFACE, "Get Transaction Info"})


@dataclass(frozen=True, slots=True)
class ProviderCallDescriptor:
    """The one outbound call: the surface, the configured identity it runs under, and the
    server-verified identifiers it looks up."""
    provider: StoreProvider
    api_surface: str
    configured: tuple[tuple[str, str], ...]
    lookup: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class AppleSubscriptionStatusResponse:
    """Apple's response, as the backend receives it: a signature to verify and JWS-signed
    transaction and renewal information to decode."""
    signature_verified: bool
    signed_transaction_info: str | None
    signed_renewal_info: str | None
    status: SubscriptionStatus | str | None
    result_codes: tuple[str, ...] = ()


def apple_live_verification_call(verified: VerifiedTransaction,
                                 *,
                                 credentials: AppleCredentials,
                                 api_surface: str = APPLE_API_SURFACE,
                                 client_supplied_parameters: Iterable[str] = ()
                                 ) -> ProviderCallDescriptor:
    """For an Apple-provider attempt the backend calls Apple's App Store Server API to fetch the
    current subscription state for the verified `originalTransactionId`, using a current endpoint
    such as `Get All Subscription Statuses` or its successor, for the configured Apple bundle ID and
    team identifier."""
    # [impl->req~restore-apple-live-verification-api-call~1]
    if verified.provider is not StoreProvider.apple:
        raise LiveVerificationError(f"{verified.provider} is no Apple-provider attempt")
    if api_surface not in APPLE_API_SURFACES:
        raise LiveVerificationError(f"{api_surface} is no current App Store Server API endpoint")
    assert_backend_credentials_and_inputs(
        credentials=credentials, client_supplied_parameters=client_supplied_parameters)
    return ProviderCallDescriptor(
        provider=StoreProvider.apple,
        api_surface=api_surface,
        configured=(("apple.bundle_id", credentials.bundle_id),
                    ("apple.team_id", credentials.team_id)),
        lookup=(("originalTransactionId", verified.external_id),))


def apple_verify_and_decode(response: AppleSubscriptionStatusResponse,
                            *,
                            client_supplied_state: object | None = None) -> tuple[str, str]:
    """The backend must verify Apple's response signature and decode the JWS-signed transaction and
    renewal information; it must not accept client-supplied subscription state in place of Apple's
    response."""
    # [impl->req~restore-apple-live-verification-signature-and-decode~1]
    if client_supplied_state is not None:
        raise LiveVerificationError(
            "client-supplied subscription state never stands in for Apple's response")
    if not response.signature_verified:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "Apple's response signature did not verify")
    if not response.signed_transaction_info or not response.signed_renewal_info:
        raise RestoreRejection(
            AuthEventResult.restore_store_state_unverified,
            "Apple's response carries the JWS-signed transaction and renewal information")
    return response.signed_transaction_info, response.signed_renewal_info


def apple_entitled_state_required(response: AppleSubscriptionStatusResponse,
                                  *,
                                  client_supplied_state: object | None = None
                                  ) -> SubscriptionStatus:
    """The backend must confirm from Apple's response that the subscription is in a state
    product-entitled by configured policy at the time of the adoption attempt; expired, revoked,
    refunded-voiding or otherwise non-entitled responses reject as defined above."""
    # [impl->req~restore-apple-live-verification-entitled-state-required~1]
    apple_verify_and_decode(response, client_supplied_state=client_supplied_state)
    return confirm_currently_entitled(response.status)


# --- Google Play-provider rules ---------------------------------------------------------------------

GOOGLE_API_SURFACE: str = "purchases.subscriptionsv2.get"
GOOGLE_API_SURFACES: frozenset[str] = frozenset({GOOGLE_API_SURFACE, "purchases.subscriptions.get"})

# Google states that carry no entitlement, beyond the shared non-entitled set.
GOOGLE_NON_ENTITLED_STATES: frozenset[str] = NON_ENTITLED_LIVE_STATES | {
    "on_hold_without_entitlement", "paused", "canceled_without_entitlement",
}


@dataclass(frozen=True, slots=True)
class GoogleLookupInputs:
    """The verified purchase token and subscription product identifier, extracted from the
    server-verified restore proof."""
    purchase_token: str
    subscription_product_id: str
    source: str = "server_verified_restore_material"


@dataclass(frozen=True, slots=True)
class GoogleSubscriptionStateResponse:
    """Google's response: the subscription state the Play Developer API reports."""
    state: SubscriptionStatus | str | None
    result_codes: tuple[str, ...] = ()


def google_live_verification_call(inputs: GoogleLookupInputs,
                                  *,
                                  credentials: GooglePlayCredentials,
                                  api_surface: str = GOOGLE_API_SURFACE,
                                  client_supplied_parameters: Iterable[str] = ()
                                  ) -> ProviderCallDescriptor:
    """For a Google Play-provider attempt the backend calls the Google Play Developer API to fetch
    the current subscription state for the verified purchase token and subscription product
    identifier extracted from the server-verified restore proof, using a current endpoint such as
    `purchases.subscriptionsv2.get` or its successor, for the configured Google Play package
    name."""
    # [impl->req~restore-google-live-verification-api-call~1]
    if api_surface not in GOOGLE_API_SURFACES:
        raise LiveVerificationError(f"{api_surface} is no current Google Play Developer API endpoint")
    assert_backend_credentials_and_inputs(
        credentials=credentials, input_sources=(inputs.source,),
        client_supplied_parameters=client_supplied_parameters)
    if not inputs.purchase_token or not inputs.subscription_product_id:
        raise LiveVerificationError(
            "the lookup uses the verified purchase token and subscription product identifier")
    return ProviderCallDescriptor(
        provider=StoreProvider.google_play,
        api_surface=api_surface,
        configured=(("google_play.package_name", credentials.package_name),),
        lookup=(("purchaseToken", inputs.purchase_token),
                ("subscriptionId", inputs.subscription_product_id)))


def google_service_account_credentials(credentials: GooglePlayCredentials,
                                       *,
                                       client_supplied_state: object | None = None
                                       ) -> GooglePlayCredentials:
    """The backend must use backend-held Google service account credentials authorized for the
    Google Play Developer API, and must not accept client-supplied subscription state in place of
    Google's response."""
    # [impl->req~restore-google-live-verification-service-account-credentials~1]
    if client_supplied_state is not None:
        raise LiveVerificationError(
            "client-supplied subscription state never stands in for Google's response")
    if not credentials.backend_held:
        raise LiveVerificationError("the Google Play Developer API call uses backend-held credentials")
    if not credentials.service_account_email or not credentials.service_account_private_key:
        raise LiveVerificationError(
            "the call runs under a service account authorized for the Google Play Developer API")
    return credentials


def google_entitled_state_required(response: GoogleSubscriptionStateResponse,
                                   *,
                                   client_supplied_state: object | None = None
                                   ) -> SubscriptionStatus:
    """The backend must confirm from Google's response that the subscription is in a state
    product-entitled by configured policy at the time of the adoption attempt; expired, revoked,
    refunded-voiding, on-hold-without-entitlement or otherwise non-entitled responses reject as
    defined above."""
    # [impl->req~restore-google-live-verification-entitled-state-required~1]
    if client_supplied_state is not None:
        raise LiveVerificationError(
            "client-supplied subscription state never stands in for Google's response")
    if response.state is None or str(response.state) in GOOGLE_NON_ENTITLED_STATES:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               f"Google reports {response.state}, which is not entitlement")
    return confirm_currently_entitled(response.state)


# --- Provider dispatch for the one live verification call ---------------------------------------

# The two store APIs live verification is made through, named as the provider's own server-side
# API rather than as a generic outbound call.
APP_STORE_SERVER_API: str = "app_store_server_api"
PLAY_DEVELOPER_API: str = "play_developer_api"


@dataclass(frozen=True, slots=True)
class LiveVerificationSurface:
    """Which of the two store APIs a provider's live verification runs through: the API itself,
    the current endpoint on it, the call that builds the one outbound request, and the check that
    reads an entitled state out of the response."""
    provider: StoreProvider
    api: str
    api_surface: str
    call: Callable[..., ProviderCallDescriptor]
    entitled_state_required: Callable[..., SubscriptionStatus]


# Apple-provider attempts verify through Apple's App Store Server API; `google_play`-provider
# attempts through the Google Play Developer API. There is no third way to verify live state, and
# no attempt verifies through the other store's API.
LIVE_VERIFICATION_BY_PROVIDER: dict[StoreProvider, LiveVerificationSurface] = {
    StoreProvider.apple: LiveVerificationSurface(
        provider=StoreProvider.apple,
        api=APP_STORE_SERVER_API,
        api_surface=APPLE_API_SURFACE,
        call=apple_live_verification_call,
        entitled_state_required=apple_entitled_state_required),
    StoreProvider.google_play: LiveVerificationSurface(
        provider=StoreProvider.google_play,
        api=PLAY_DEVELOPER_API,
        api_surface=GOOGLE_API_SURFACE,
        call=google_live_verification_call,
        entitled_state_required=google_entitled_state_required),
}


def live_verification_surface(provider: StoreProvider) -> LiveVerificationSurface:
    """The provider's own server-side API this attempt's live store-state verification is made
    through: Apple's App Store Server API for Apple-provider attempts, the Google Play Developer
    API for `google_play`-provider attempts."""
    # [impl->req~restore-pre-transaction-precondition-01-live-store-state-verification~1]
    surface = LIVE_VERIFICATION_BY_PROVIDER.get(provider)
    if surface is None:
        raise LiveVerificationError(f"{provider} has no live store-state verification API")
    return surface


# --- Audit rules ------------------------------------------------------------------------------------


def verification_audit_context(*,
                               provider: StoreProvider,
                               api_surface: str,
                               decision: LiveDecision,
                               result_codes: Iterable[str] = (),
                               raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The live verification outcome is recorded only as non-secret context on the
    `audit.auth_events` row (`details.verification`): the provider, the API surface called, the
    high-level decision, and any provider-specific machine-readable result codes the implementation
    chooses to retain. Raw signed responses and raw provider payloads are not stored on the row."""
    # [impl->req~restore-live-verification-audit-non-secret-context~1]
    if raw:
        raise LiveVerificationError(
            "raw signed responses and raw provider payloads are not stored on the row")
    context = {"provider": str(provider),
               "api_surface": api_surface,
               "decision": str(decision),
               "result_codes": sorted(set(result_codes))}
    assert_no_raw_response_persistence(context, table="audit.auth_events")
    return context
