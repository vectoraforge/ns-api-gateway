"""Sign-out everywhere: `POST /auth/sign-out-all`, and nothing else.

The backend exposes exactly one sign-out endpoint, and what it does is one external call: Firebase
Admin refresh-token revocation for the subject the current request's token verified. It reads no
stored provider, writes no business state, keeps no revocation state of its own, and returns
success only when Firebase confirmed the revocation.

Per-device sign-out is not here because it does not exist as a backend operation: an ID token is
stateless and Firebase revocation acts on the whole subject, so signing out one device is a purely
local client action. The accepted residual risks the endpoint carries are written down here too,
because they are the contract the endpoint is judged against; the client-side sign-out
responsibilities are the client app's and are not modelled here.
"""

import asyncio
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, get_args

import structlog

from nativespeaker.api.auth.audit import (
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEvent,
    AuthEventResult,
    RevocationErrorCategory,
    sign_out_all_event,
)
from nativespeaker.api.auth.barrier import (
    ResolutionOutcome,
    VerifiedIdentityContext,
    barrier_result_for,
)
from nativespeaker.api.auth.endpoints import bearer_credential
from nativespeaker.api.auth.integration import AdminCallSite, FirebaseIntegrations
from nativespeaker.api.auth.operations import (
    AdmissionRejection,
    AuthOperation,
    IdentityProvider,
    is_admission_phase,
    is_challenge_bearing,
    route_for,
    supports_prepare,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.exceptions import ErrorCode, ServiceError
from nativespeaker.api.ratelimit.config import (
    DEFAULT_ENTRY_EXEMPT,
    REQUIRED_OPERATION_ENTRIES,
)

logger = structlog.get_logger()

SIGN_OUT_ALL_OPERATION: AuthOperation = AuthOperation.sign_out_all
SIGN_OUT_ALL_METHOD, SIGN_OUT_ALL_PATH = route_for(SIGN_OUT_ALL_OPERATION)


class SignOutError(RuntimeError):
    """A sign-out rule was about to be broken."""


# --- Exactly one sign-out endpoint ----------------------------------------------------------------

# The backend's whole sign-out surface. Membership is the operation inventory's, so a second
# sign-out route could not be added without appearing here.
# [impl->req~sessions-single-sign-out-endpoint~1]
SIGN_OUT_ENDPOINTS: tuple[tuple[str, str], ...] = ((SIGN_OUT_ALL_METHOD, SIGN_OUT_ALL_PATH),)

# There is no per-device backend sign-out: an ID token is stateless and cannot be revoked
# individually before its own `exp`, and Firebase refresh-token revocation acts on the whole
# Firebase subject, so no route could implement one. Signing out the current device only is a
# client action; a client that wants to sign out everywhere calls the one endpoint above.
# [impl->req~sessions-no-per-device-backend-sign-out~1]
PER_DEVICE_SIGN_OUT_ENDPOINTS: frozenset[tuple[str, str]] = frozenset()


def sign_out_endpoint() -> tuple[str, str]:
    """The one sign-out endpoint. A second one, or a per-device variant, fails closed here rather
    than quietly becoming a second way to end sessions."""
    # [impl->req~sessions-single-sign-out-endpoint~1]
    # [impl->req~sessions-no-per-device-backend-sign-out~1]
    if len(SIGN_OUT_ENDPOINTS) != 1 or PER_DEVICE_SIGN_OUT_ENDPOINTS:
        raise SignOutError("the backend exposes exactly one sign-out endpoint")
    return SIGN_OUT_ENDPOINTS[0]


# What a current-device sign-out calls on the backend: nothing. What the client clears locally
# when it does that is the client app's own contract, not this backend's — see the client
# responsibilities note below.
# [impl->req~sessions-no-per-device-backend-sign-out~1]
LOCAL_SIGN_OUT_BACKEND_CALLS: tuple[tuple[str, str], ...] = ()


# --- The endpoint's purpose and its preconditions -------------------------------------------------


def sign_out_all_credential(authorization_values: Sequence[str]) -> str:
    """The endpoint's authentication: the external IDP ID token as a single `Authorization: Bearer`
    credential, and nothing else."""
    # [impl->req~sessions-api-sign-out-all-bearer-credential~1]
    return bearer_credential(SIGN_OUT_ALL_METHOD, SIGN_OUT_ALL_PATH, authorization_values)


def sign_out_all_subject(context: VerifiedIdentityContext) -> tuple[str, str]:
    """The endpoint's admission precondition and, with it, the subject the revocation acts on.

    Authentication and identity resolution happened in the shared pre-handler barrier before this
    handler ran, and the endpoint requires a linked, active identity: a pre-auth, historical or
    blocked identity is rejected at the barrier, so nothing but a linked context reaches here.
    The revoked subject is the one the barrier's own token verification produced — the endpoint
    requests global sign-out through the external IDP for the current linked user, for that
    verified subject, whatever the account's stored provider classification says.
    """
    # [impl->req~sessions-api-sign-out-all-barrier-precondition~1]
    # [impl->req~sessions-api-sign-out-all-purpose~1]
    if context.outcome is not ResolutionOutcome.linked or context.user_id is None:
        raise SignOutError("sign-out everywhere acts only on a barrier-admitted linked identity")
    if not context.issuer or not context.subject:
        raise SignOutError("the barrier resolved no verified issuer and subject")
    return context.issuer, context.subject


def self_service_admitted(outcome: ResolutionOutcome) -> bool:
    """Sign-out everywhere is self-service for a subject that can still authenticate and is
    neither blocked nor retired. The shared barrier rejects a blocked user or a historical
    identity here as on every other authenticated route, with no exception for this endpoint —
    this reads that predicate rather than restating it, so the route cannot drift into an
    exception of its own.
    """
    # [impl->req~sessions-sign-out-self-service-scope~1]
    return barrier_result_for(outcome, SIGN_OUT_ALL_METHOD, SIGN_OUT_ALL_PATH) is None


# The operator paths that cover the blocked-or-retired case instead: each revokes the account's
# Firebase refresh tokens as part of the same operation, so such an account needs no second,
# self-service way to end its sessions.
# [impl->req~sessions-sign-out-self-service-scope~1]
OPERATOR_REVOCATION_SITES: frozenset[AdminCallSite] = frozenset({
    AdminCallSite.operator_block_revocation,
    AdminCallSite.identity_retirement_revocation,
})


def operator_revocation_is_authoritative_after(*, database_committed: bool,
                                              revocation_confirmed: bool) -> bool:
    """On the operator path the database flag or tombstone is committed first and stays
    authoritative whatever the revocation outcome: a failed or ambiguous revocation never undoes
    the block or the retirement."""
    # [impl->req~sessions-sign-out-self-service-scope~1]
    if not database_committed and revocation_confirmed:
        raise SignOutError("the database change is committed before the revocation is attempted")
    return database_committed


# --- No backend quota of its own ------------------------------------------------------------------

# Sign-out-all has no named backend rate-limit entry and is exempt from the backend generic
# default entry, so no backend counter can reject an authenticated request to it. Both facts are
# read from the rate-limit configuration module that owns them.
# [impl->req~sessions-api-sign-out-all-no-backend-quota~1]
SIGN_OUT_ALL_BACKEND_ENTRIES: tuple[str, ...] = REQUIRED_OPERATION_ENTRIES[SIGN_OUT_ALL_OPERATION]

# Its only bounds: the gateway's standard per-IP and per-user limits, which apply here exactly as
# on every other authenticated route. No route-specific deployment-wide counter is added, and the
# route takes no exemption from the generic gateway limiting either.
SIGN_OUT_ALL_GATEWAY_BOUNDS: tuple[str, ...] = ("gateway_per_ip", "gateway_per_user")
SIGN_OUT_ALL_ROUTE_SPECIFIC_COUNTERS: frozenset[str] = frozenset()
SIGN_OUT_ALL_GATEWAY_EXEMPTIONS: frozenset[str] = frozenset()


def assert_no_backend_quota(counters: Iterable[str] = ()) -> None:
    """No backend counter may reject an authenticated request to this endpoint, and the route
    introduces none: no named entry, no dedicated per-subject quota, no new counter, and no
    route-specific deployment-wide counter. It takes no exemption from the gateway's generic
    limiting either."""
    # [impl->req~sessions-api-sign-out-all-no-backend-quota~1]
    if SIGN_OUT_ALL_BACKEND_ENTRIES:
        raise SignOutError("sign-out-all carries no named backend rate-limit entry")
    if SIGN_OUT_ALL_OPERATION not in DEFAULT_ENTRY_EXEMPT:
        raise SignOutError("sign-out-all is exempt from the backend generic default entry")
    if SIGN_OUT_ALL_ROUTE_SPECIFIC_COUNTERS or SIGN_OUT_ALL_GATEWAY_EXEMPTIONS:
        raise SignOutError("no route-specific counter bounds sign-out-all, and it takes no "
                           "exemption from gateway limiting")
    offending = sorted(counters)
    if offending:
        raise SignOutError(f"no backend counter rejects sign-out-all: {offending}")


@dataclass(frozen=True, slots=True)
class CoalescedRevocation:
    """A revocation result shared by concurrent in-flight requests for one subject."""
    subject: str
    outcome: RevocationOutcome
    in_flight: bool


def may_share_revocation_result(result: CoalescedRevocation, *, sequential: bool) -> bool:
    """Concurrent in-flight revocations for the same subject may be coalesced to share a single
    result. A later sequential request never reuses it: the user may have re-authenticated with
    fresh refresh credentials in the meantime, so that request needs its own revocation."""
    # [impl->req~sessions-api-sign-out-all-no-backend-quota~1]
    return result.in_flight and not sequential


# --- The revocation ------------------------------------------------------------------------------


class RevocationOutcome(StrEnum):
    """What the one Firebase Admin refresh-token revocation call did. Only `confirmed` is a
    success; the other three are the shapes an unconfirmed outcome takes."""
    confirmed = "confirmed"
    # Firebase returned a definitive failure.
    definitive_failure = "definitive_failure"
    # A local dependency prevented the call from completing — a missing or misconfigured Admin
    # client among them.
    dependency_unavailable = "dependency_unavailable"
    # A timeout, a lost response or a disconnect left the outcome unknown.
    ambiguous = "ambiguous"


# The sanitized audit category each unconfirmed outcome records. Bounded and low-cardinality:
# nothing here can carry a raw Firebase message, a credential, a token, a stack trace,
# high-cardinality exception text or a vendor response payload.
REVOCATION_ERROR_CATEGORIES: dict[RevocationOutcome, RevocationErrorCategory] = {
    RevocationOutcome.definitive_failure: RevocationErrorCategory.definitive_failure,
    RevocationOutcome.dependency_unavailable: RevocationErrorCategory.dependency_unavailable,
    RevocationOutcome.ambiguous: RevocationErrorCategory.ambiguous_outcome,
}

# The bounded number of in-request attempts the backend may make before treating the outcome as
# unconfirmed. Small, and inside the request: there is no queue and no later attempt.
MAX_REVOCATION_ATTEMPTS = 3

# Outcomes worth another in-request attempt. A definitive failure and a missing local dependency
# are not: repeating either inside the same request cannot change it.
_RETRIABLE_IN_REQUEST: frozenset[RevocationOutcome] = frozenset({RevocationOutcome.ambiguous})


class RevocationTimeout(Exception):
    """The revocation call did not return in time, or its response was lost."""


class RevocationDependencyError(Exception):
    """A local dependency prevented the revocation call from being made at all."""


def classify_revocation_error(error: BaseException) -> RevocationOutcome:
    """Which unconfirmed shape a failed revocation attempt took. A timeout, a lost response or a
    disconnect is ambiguous; a local dependency failure is its own category; anything Firebase
    itself returned is a definitive failure."""
    # [impl->req~sessions-sign-out-all-step-01~1]
    if isinstance(error, RevocationTimeout | TimeoutError | asyncio.TimeoutError | ConnectionError):
        return RevocationOutcome.ambiguous
    if isinstance(error, RevocationDependencyError):
        return RevocationOutcome.dependency_unavailable
    return RevocationOutcome.definitive_failure


class RefreshTokenRevoker(Protocol):
    def __call__(self, subject: str, *, client: Any) -> None:
        """Revoke every refresh token Firebase holds for this subject, through this Admin
        client."""
        ...


def _firebase_revoke(subject: str, *, client: Any) -> None:
    """The Firebase Admin refresh-token revocation call itself."""
    from firebase_admin import auth  # noqa: PLC0415 - imported lazily so tests need no app

    auth.revoke_refresh_tokens(subject, app=client)


# Sign-out everywhere is not a consumer of the stored `provider` value: the reads it is allowed
# name no provider column, so the revocation cannot become conditional on one.
# [impl->req~sessions-sign-out-revokes-refresh-tokens~1]
SIGN_OUT_ALL_READS: frozenset[str] = frozenset()

# Nothing durable is kept about a revocation: no retry queue, no background reconciliation, and
# no stored revocation state. The client is the retry path.
# [impl->req~sessions-revocation-idempotent-client-retries~1]
REVOCATION_RETRY_QUEUES: frozenset[str] = frozenset()
REVOCATION_RECONCILIATION_JOBS: frozenset[str] = frozenset()
DURABLE_REVOCATION_STATE: frozenset[str] = frozenset()


def assert_provider_not_consulted(reads: Iterable[str] = ()) -> None:
    """Revocation is unconditional. It does not read the stored `provider` value, so no stored
    classification — anonymous, google or apple — can make it happen or not happen."""
    # [impl->req~sessions-sign-out-revokes-refresh-tokens~1]
    # [impl->req~sessions-risk-revocation-scope~1]
    provider_reads = sorted({name for name in (*SIGN_OUT_ALL_READS, *reads)
                             if "provider" in name.lower()})
    if provider_reads:
        raise SignOutError(f"sign-out everywhere does not read {provider_reads}")


def retry_is_safe(outcome: RevocationOutcome) -> bool:
    """Whether the client may retry the call after this outcome: always.

    Firebase revocation is whole-subject and idempotent — re-revoking only re-asserts the
    subject's valid-after timestamp — so retrying after any outcome, an ambiguous one included, is
    safe. The client is the retry path: the backend keeps no retry queue, runs no background
    reconciliation, and stores no durable revocation state to reconcile against.
    """
    # [impl->req~sessions-revocation-idempotent-client-retries~1]
    if REVOCATION_RETRY_QUEUES or REVOCATION_RECONCILIATION_JOBS or DURABLE_REVOCATION_STATE:
        raise SignOutError("the backend keeps no revocation retry state; the client retries")
    return outcome in set(RevocationOutcome)


@dataclass(frozen=True, slots=True)
class RevocationAttempt:
    """One request's revocation: the outcome, and how many in-request calls produced it."""
    outcome: RevocationOutcome
    calls: int

    @property
    def confirmed(self) -> bool:
        return self.outcome is RevocationOutcome.confirmed

    @property
    def error_category(self) -> RevocationErrorCategory | None:
        return REVOCATION_ERROR_CATEGORIES.get(self.outcome)


async def revoke_refresh_tokens(integrations: FirebaseIntegrations,
                                context: VerifiedIdentityContext,
                                *,
                                revoker: RefreshTokenRevoker = _firebase_revoke,
                                max_attempts: int = MAX_REVOCATION_ATTEMPTS) -> RevocationAttempt:
    """Step one: call Firebase Admin refresh-token revocation for the verified subject, through
    the Admin client the request-verified issuer selects, without loading or consulting the stored
    provider classification.

    The call may be retried a small bounded number of times inside the request before the outcome
    is treated as unconfirmed. Revocation stops new ID tokens from being minted for that subject;
    ID tokens already minted stay valid until their own `exp`, which is why this is the whole of
    what the endpoint does.
    """
    # [impl->req~sessions-sign-out-all-step-01~1]
    # [impl->req~sessions-sign-out-revokes-refresh-tokens~1]
    # [impl->req~sessions-risk-revocation-scope~1]
    issuer, subject = sign_out_all_subject(context)
    assert_provider_not_consulted()
    if max_attempts < 1:
        raise SignOutError("the revocation is attempted at least once")
    outcome = RevocationOutcome.dependency_unavailable
    calls = 0
    for _ in range(min(max_attempts, MAX_REVOCATION_ATTEMPTS)):
        calls += 1
        try:
            # The Admin client is selected by the issuer this request's token verified, at the
            # `sign_out_all_revocation` call site — never a default or ambient client.
            client = integrations.admin_client_for_request(
                verified_issuer=issuer, site=AdminCallSite.sign_out_all_revocation)
            await asyncio.to_thread(revoker, subject, client=client)
        except Exception as error:  # noqa: BLE001 - every failure becomes a bounded outcome
            outcome = classify_revocation_error(error)
            # Only an ambiguous outcome is worth another attempt inside the request.
            if outcome not in _RETRIABLE_IN_REQUEST:
                break
            continue
        outcome = RevocationOutcome.confirmed
        break
    return RevocationAttempt(outcome=outcome, calls=calls)


# --- What success means, and what every other outcome returns -------------------------------------


class SignOutAllUnconfirmedError(ServiceError):
    """The revocation was not confirmed, so the attempt returns a server-side failure rather than
    success. Retryable by default; a definitive configuration failure may be surfaced as
    non-retryable. Neither adds a new client-visible error class."""
    status_code = 503
    error_code: ErrorCode = "service_unavailable"

    def __init__(self, category: RevocationErrorCategory, *, retryable: bool = True):
        self.category = category
        self.retryable = retryable
        if not retryable:
            self.status_code = 500
            self.error_code = "internal_error"
        super().__init__("sign-out everywhere could not be confirmed")


# The classes an unconfirmed revocation may surface as. Both already exist in the shared error
# vocabulary, so this path adds no new client-visible error class — and neither is a success.
# [impl->req~sessions-sign-out-all-step-03~1]
UNCONFIRMED_SURFACES: frozenset[ErrorCode] = frozenset({"service_unavailable", "internal_error"})


def sign_out_all_failure(outcome: RevocationOutcome,
                        *,
                        definitive_configuration_failure: bool = False
                        ) -> SignOutAllUnconfirmedError:
    """Step three, negative half: every outcome other than a confirmed revocation — an error
    response, a timeout, a transport failure, a permission or configuration error, a quota
    failure, and a lost response that leaves the result ambiguous — returns a retryable
    server-side failure and never success. A definitive configuration failure may be surfaced as
    non-retryable; it is still never success."""
    # [impl->req~sessions-sign-out-all-step-03~1]
    category = REVOCATION_ERROR_CATEGORIES.get(outcome)
    if category is None:
        raise SignOutError(f"{outcome} is a confirmed revocation, not a failure")
    error = SignOutAllUnconfirmedError(category, retryable=not definitive_configuration_failure)
    if error.error_code not in UNCONFIRMED_SURFACES:
        raise SignOutError("the unconfirmed path adds no new client-visible error class")
    # The vocabulary is the shared one: no class is invented here, and none of the auth classes is
    # repurposed to mean "revocation unconfirmed".
    if error.error_code not in set(get_args(ErrorCode)) \
            or error.error_code in set(ClientErrorClass):
        raise SignOutError("the unconfirmed path adds no new client-visible error class")
    return error


def sign_out_all_succeeded(attempt: RevocationAttempt) -> bool:
    """Step three, positive half, and the whole meaning of success: the IDP confirmed
    refresh-token revocation for the subject.

    It does not mean every already-minted ID token is now invalid — those remain valid until their
    own `exp` — and there is no second success code for the difference.
    """
    # [impl->req~sessions-sign-out-all-step-03~1]
    # [impl->req~sessions-api-sign-out-all-success-meaning~1]
    return attempt.confirmed


# What success does *not* claim: already-minted ID tokens keep working until they expire, so the
# backend performs no per-request check of Firebase revocation state to notice them.
# [impl->req~sessions-api-sign-out-all-success-meaning~1]
# [impl->req~sessions-risk-no-per-request-revocation-check~1]
SUCCESS_INVALIDATES_MINTED_ID_TOKENS: bool = False
PER_REQUEST_REVOCATION_CHECKS: frozenset[str] = frozenset()


# --- The attempt's single audit row ---------------------------------------------------------------


def sign_out_all_attempt_event(*,
                               actor: AuthActor,
                               request_id: str,
                               attempt: RevocationAttempt,
                               details: Mapping[str, Any] | None = None) -> AuthEvent:
    """Step two: the attempt's single `audit.auth_events` row for the observed outcome, built
    before the response is returned, on confirmed revocation, failure and ambiguity alike.

    `result` alone carries the outcome — `succeeded`, or `revocation_unconfirmed` with a sanitized
    error category in `details.failure` and no second outcome field. The row carries the
    operation, the hashed actor subject, the request identifier and the event timestamp; raw
    Firebase messages, credentials, tokens, stack traces, high-cardinality exception text and
    vendor response payloads are not expressible in it.
    """
    # [impl->req~sessions-sign-out-all-step-02~1]
    # [impl->req~sessions-api-sign-out-all-audit-row~1]
    body = dict(details or {})
    if body.get("mutation"):
        raise SignOutError("sign-out everywhere records no business-state mutation")
    return sign_out_all_event(actor=actor,
                              request_id=request_id,
                              revoked=attempt.confirmed,
                              error_category=attempt.error_category,
                              details=body)


def barrier_rejection_event_result(outcome: ResolutionOutcome) -> AuthEventResult:
    """A request rejected before the authorized revocation phase never claims revocation was
    attempted. A barrier rejection is still on the audited attempt path, so it writes this
    attempt's single row carrying the barrier's own more specific result — one of
    `invalid_external_jwt`, `preauth_identity_not_allowed`, `historical_identity` or
    `blocked_user` — never `revocation_unconfirmed`."""
    # [impl->req~sessions-api-sign-out-all-audit-row~1]
    # [impl->req~sessions-api-sign-out-all-canonical-operation~1]
    result = barrier_result_for(outcome, SIGN_OUT_ALL_METHOD, SIGN_OUT_ALL_PATH)
    if result is None:
        raise SignOutError(f"{outcome} is admitted, so the barrier writes no rejection row")
    if result is AuthEventResult.revocation_unconfirmed:
        raise SignOutError("a barrier rejection never claims revocation was attempted")
    return result


def admission_rejection_writes_row(rejection: AdmissionRejection) -> bool:
    """An admission-control or gateway rate-limit rejection falls under the admission-control
    carve-out: it is off the audited attempt path and writes no `audit.auth_events` row at all."""
    # [impl->req~sessions-api-sign-out-all-audit-row~1]
    return not is_admission_phase(rejection)


def assert_one_row_per_attempt(attempt: AuthAttempt) -> AuthAttempt:
    """Sign-out-all is on the audited attempt path from the route match, and every attempt writes
    exactly one row — a barrier rejection, `revocation_unconfirmed`, or `succeeded`. Each retry is
    a new attempt with its own single row, which is why the claim is per attempt rather than per
    subject.

    It is challenge-free: it creates, reads and consumes no `core.auth_challenges` row, so the
    challenge-variant and prepare-phase rules written for the challenge-bearing subset do not
    apply to it. Belonging to the inventory adds no quota of its own.
    """
    # [impl->req~sessions-api-sign-out-all-canonical-operation~1]
    if attempt.operation is not SIGN_OUT_ALL_OPERATION or not attempt.on_audited_path:
        raise SignOutError("sign-out-all is on the audited attempt path from the route match")
    if is_challenge_bearing(SIGN_OUT_ALL_OPERATION) or supports_prepare(SIGN_OUT_ALL_OPERATION):
        raise SignOutError("sign-out-all is challenge-free and has no prepare phase")
    # Exactly one row per attempt: an attempt that already wrote its row owes no second one, and
    # the shared writer's own claim is what this reads, so there is no second counter of rows.
    if attempt.audited:
        raise SignOutError("this attempt already wrote its one audit.auth_events row")
    assert_no_backend_quota()
    return attempt


# --- No business-state mutation -------------------------------------------------------------------

# The PostgreSQL business-state tables sign-out everywhere writes: none of them.
# [impl->req~sessions-sign-out-no-business-mutation~1]
# [impl->req~sessions-api-sign-out-all-no-business-mutation~1]
SIGN_OUT_ALL_BUSINESS_WRITES: frozenset[str] = frozenset()

# The tables the endpoint is most often assumed to touch, named so a write to any of them is
# recognized rather than passed through as an unknown name.
PROTECTED_BUSINESS_TABLES: frozenset[str] = frozenset({
    "core.users", "core.external_identities", "core.access_grants", "core.access_tiers",
    "core.subscriptions", "core.store_purchases", "core.store_purchase_tokens",
    "core.user_monthly_usage", "core.chats", "core.messages", "core.auth_challenges",
})

# The one table the attempt does append to. It is operational logging rather than business state,
# so it is compatible with the no-mutation rule.
# [impl->req~sessions-api-sign-out-all-no-business-mutation~1]
OPERATIONAL_LOG_TABLE = "audit.auth_events"


def assert_no_business_mutation(writes: Iterable[str] = ()) -> None:
    """`POST /auth/sign-out-all` mutates no PostgreSQL business-state table. Appending the
    attempt's `audit.auth_events` row is the one permitted write, and it is operational logging,
    not business state."""
    # [impl->req~sessions-sign-out-no-business-mutation~1]
    # [impl->req~sessions-api-sign-out-all-no-business-mutation~1]
    offending = sorted({table for table in (*SIGN_OUT_ALL_BUSINESS_WRITES, *writes)
                        if table != OPERATIONAL_LOG_TABLE})
    if offending:
        raise SignOutError(f"sign-out everywhere mutates no business-state table: {offending}")


# --- The anonymous one-way door -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnonymousRevocationConsequence:
    """What revoking an anonymous subject costs, and what it leaves behind."""
    reachable_by_later_sign_in: bool
    refresh_token_holder_locked_out_at_once: bool
    id_token_holder_locked_out_at_exp: bool
    retained_rows: tuple[str, ...]
    recovery_path: str | None


# Anonymous re-sign-in mints a new Firebase uid, so no later sign-in resolves to the revoked
# account. The rows stay in PostgreSQL; nothing reaches them.
# [impl->req~sessions-anonymous-revocation-one-way-door~1]
ANONYMOUS_RETAINED_ROWS: tuple[str, ...] = ("core.users", "core.chats", "core.access_grants")
ANONYMOUS_RECOVERY_PATH: str | None = None


def anonymous_revocation_consequence(
        provider: IdentityProvider) -> AnonymousRevocationConsequence | None:
    """For an anonymous identity, revocation is a one-way door.

    Anonymous re-sign-in mints a new Firebase uid, so the revoked account becomes unreachable: at
    once for anyone holding only a refresh token, and for the legitimate user once the current ID
    token reaches its own `exp`, at most an hour later. The `core.users` row and its chats,
    credits and grants remain in PostgreSQL, but no later sign-in resolves to them — consistent
    with there being no anonymous-account recovery path. A registered identity has none of this,
    so the answer there is `None`.
    """
    # [impl->req~sessions-anonymous-revocation-one-way-door~1]
    if provider is not IdentityProvider.anonymous:
        return None
    if ANONYMOUS_RECOVERY_PATH is not None:
        raise SignOutError("there is no anonymous-account recovery path")
    return AnonymousRevocationConsequence(reachable_by_later_sign_in=False,
                                          refresh_token_holder_locked_out_at_once=True,
                                          id_token_holder_locked_out_at_exp=True,
                                          retained_rows=ANONYMOUS_RETAINED_ROWS,
                                          recovery_path=ANONYMOUS_RECOVERY_PATH)


# --- Client responsibilities ----------------------------------------------------------------------

# The sign-out client responsibilities in `01-sessions-and-identity-resolution.md` — the
# current-device local sign-out, the sign-out-everywhere ordering, the non-success and
# `account_unavailable` handling, and the anonymous warnings — are obligations of the client app.
# They are implemented in `ns-ios`, which is outside this repository's traced scope, and no
# backend behavior reads them, so they carry no coverage tag here: a Python model of them would
# only be somewhere to put a tag, and regressing the real client would not fail it. The six ids
# are recorded on the blocked list instead.

# --- Accepted risk --------------------------------------------------------------------------------

# A leaked external IDP ID token is usable on every authenticated route until its own `exp`. Any
# bearer already reads the user's profile, entitlement state and chats, so the store
# purchase-attribution tokens `GET /users/me` returns add no authority: exposing them to an
# authenticated session is no privilege escalation.
# [impl->req~sessions-risk-leaked-token-usable~1]
LEAKED_TOKEN_READS: frozenset[str] = frozenset({"profile", "entitlement_state", "chats"})
STORE_ATTRIBUTION_TOKEN_AUTHORITY: frozenset[str] = frozenset()


def leaked_token_escalates_privilege() -> bool:
    """Whether returning the store purchase-attribution tokens escalates a leaked bearer's
    privilege. It does not: the tokens carry no authority of their own, and everything they sit
    beside was already readable by that bearer."""
    # [impl->req~sessions-risk-leaked-token-usable~1]
    return bool(STORE_ATTRIBUTION_TOKEN_AUTHORITY - LEAKED_TOKEN_READS)


# Token lifetime is governed by the external IDP token `exp` and the IDP refresh token, not by any
# backend-controlled absolute session expiry — there is none to configure.
# [impl->req~sessions-risk-token-lifetime-idp-governed~1]
TOKEN_LIFETIME_GOVERNORS: tuple[str, ...] = ("external_idp_token_exp", "idp_refresh_token")
BACKEND_ABSOLUTE_SESSION_EXPIRY: None = None


def token_lifetime_source() -> tuple[str, ...]:
    """What bounds a session's lifetime. A backend-controlled absolute expiry would be a second
    answer; there is none."""
    # [impl->req~sessions-risk-token-lifetime-idp-governed~1]
    if BACKEND_ABSOLUTE_SESSION_EXPIRY is not None:
        raise SignOutError("no backend-controlled absolute session expiry exists")
    return TOKEN_LIFETIME_GOVERNORS


def assert_no_per_request_revocation_check(checks: Iterable[str] = ()) -> None:
    """The backend performs no per-request revocation check against Firebase refresh-token
    revocation state. Resolution reads the database, never the IDP's revocation state."""
    # [impl->req~sessions-risk-no-per-request-revocation-check~1]
    offending = sorted({*PER_REQUEST_REVOCATION_CHECKS, *checks})
    if offending:
        raise SignOutError(f"no per-request revocation check runs: {offending}")


# Protecting against an attacker that can keep minting fresh external IDP ID tokens from a
# compromised registered install is out of scope for this specification: it would need upstream
# session revocation semantics or additional client-side credential binding, and neither is built.
# [impl->req~sessions-risk-compromised-install-out-of-scope~1]
COMPROMISED_INSTALL_MITIGATIONS: frozenset[str] = frozenset()
COMPROMISED_INSTALL_WOULD_REQUIRE: tuple[str, ...] = ("upstream_session_revocation_semantics",
                                                      "client_side_credential_binding")


def compromised_install_in_scope() -> bool:
    """Whether this specification defends against a compromised registered install that can keep
    minting fresh ID tokens. It does not, and nothing here pretends to."""
    # [impl->req~sessions-risk-compromised-install-out-of-scope~1]
    return bool(COMPROMISED_INSTALL_MITIGATIONS)


# --- The whole endpoint, in order -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignOutAllResult:
    """One `POST /auth/sign-out-all` attempt: its revocation outcome, the single audit row it
    owes, and whether the client sees success."""
    attempt: RevocationAttempt
    event: AuthEvent
    succeeded: bool


async def sign_out_all(integrations: FirebaseIntegrations,
                       context: VerifiedIdentityContext,
                       *,
                       actor: AuthActor,
                       request_id: str,
                       audit_attempt: AuthAttempt,
                       audit: AuthAuditWriter,
                       revoker: RefreshTokenRevoker = _firebase_revoke,
                       max_attempts: int = MAX_REVOCATION_ATTEMPTS) -> SignOutAllResult:
    """The three steps, in order: revoke, audit the observed outcome, then return success only on
    a confirmed revocation.

    Sign-out everywhere maps onto the external IDP and onto nothing else, so no business state
    changes here and no revocation state is stored. The attempt's single row is appended through
    the shared audit writer before the response is returned, on every outcome; the writer's own
    per-attempt claim is what makes a second row for one attempt impossible.
    """
    # [impl->req~sessions-api-sign-out-all-canonical-operation~1]
    # [impl->req~sessions-api-sign-out-all-purpose~1]
    assert_one_row_per_attempt(audit_attempt)
    attempt = await revoke_refresh_tokens(integrations, context,
                                          revoker=revoker, max_attempts=max_attempts)
    # Step two, before the response, whatever the outcome was.
    # [impl->req~sessions-sign-out-all-step-02~1]
    event = sign_out_all_attempt_event(actor=actor, request_id=request_id, attempt=attempt)
    assert_no_business_mutation()
    # The endpoint opens no consuming or mutating transaction — it mutates no business state — so
    # the row is the standalone durable write of this attempt's own transaction, awaited here
    # rather than deferred, and it is claimed against the attempt so no second row can follow.
    # [impl->req~sessions-sign-out-all-step-02~1]
    # [impl->req~sessions-api-sign-out-all-audit-row~1]
    # [impl->req~sessions-api-sign-out-all-canonical-operation~1]
    if event.result is AuthEventResult.revocation_unconfirmed:
        logger.warning("sign_out_all_revocation_unconfirmed",
                       operation=str(SIGN_OUT_ALL_OPERATION),
                       error_category=str(attempt.error_category),
                       calls=attempt.calls)
        # A failing audit write is logged loudly and the client still receives the unconfirmed
        # outcome this attempt earned rather than a different one.
        await audit.record_rejection(audit_attempt, event,
                                     sign_out_all_failure(attempt.outcome))
    else:
        await audit.write_standalone(audit_attempt, event)
    # Step three: the client sees success exactly when the row says `succeeded`, which is exactly
    # when Firebase confirmed the revocation. The two can never disagree.
    # [impl->req~sessions-sign-out-all-step-03~1]
    succeeded = sign_out_all_succeeded(attempt)
    if succeeded is not (event.result is AuthEventResult.succeeded):
        raise SignOutError("success means only that Firebase confirmed the revocation")
    return SignOutAllResult(attempt=attempt, event=event, succeeded=succeeded)
