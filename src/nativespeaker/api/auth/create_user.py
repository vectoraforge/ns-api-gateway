"""`create_user`: the endpoint half of `POST /auth/create-user`.

The shared procedures own the barrier checks, the challenge lookup, the claim, the variant
comparison, the consuming transaction and the audit write. This module holds what `create_user`
itself decides: the one mandatory Firebase Admin lookup and its closed classification, the
account and identity state the completion transaction writes, the profile rules that commit
with it, and the endpoint's own rejection classes.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID, uuid4, uuid7

from nativespeaker.api.auth.audit import AuthEventResult, structured_details
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import ChallengeRow, variants_equal
from nativespeaker.api.auth.external_identities import (
    PAIRING_ENFORCEMENT_MECHANISMS,
    REGISTERED_PROVIDERS,
    AlreadyLinkedSite,
    ExternalIdentityRow,
    IdentityAlreadyLinkedError,
    IdentityState,
    LookupFailure,
    ProviderAccountAlreadyLinkedError,
    ProviderClassificationError,
    ProviderDataReadPoint,
    ProviderDeclarationMismatchError,
    ProviderLookupFailedError,
    ProviderSource,
    already_linked_result,
    assert_declared_provider,
    assert_may_write_provider_fields,
    assert_provider_source,
    classify_provider,
    create_account,
    provider_account_conflict,
    provider_from_lookup,
    provider_uid_for,
    uniqueness_race_loser,
)
from nativespeaker.api.auth.integration import FirebaseIntegrations
from nativespeaker.api.auth.onboarding import assert_pre_consumption_checks_first
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider, route_for
from nativespeaker.api.auth.procedures import ChallengeRejection, reconciliation_options
from nativespeaker.api.auth.profile import (
    AccountClass,
    AdminUserRecord,
    account_class,
    assert_registered_at_pairing,
    initial_email_on_create,
)
from nativespeaker.api.auth.taxonomy import (
    REMEDIATIONS,
    RESULT_TO_CLASS,
    ClientErrorClass,
    ClientRejection,
    Remediation,
    client_response,
    register_client_class,
    register_endpoint_class,
    surface,
)
from nativespeaker.api.auth.users import (
    CREATE_USER_ROUTE,
    assert_no_free_credits,
    complete_create_user,
    context_pair,
    create_user_prepare_constraints,
    firebase_identity_lookup,
    issuer_selected_admin_client,
    lookup_unavailable,
    unavailable_account,
)
from nativespeaker.api.exceptions import ErrorCode
from nativespeaker.api.ratelimit.ordering import AdmissionLedger, BudgetVerdict


class CreateUserError(RuntimeError):
    """A `create_user` rule was about to be broken."""


class CreateFlow(StrEnum):
    """The two create-user flows a client can be sent to. `required_flow` names one of these
    and nothing else."""
    anonymous = "anonymous"
    registered = "registered"


# What each classified provider means for the flow the client must use. This is also the whole
# of what `create_user` serves: anonymous first-time users and registered first-time users.
CREATE_USER_FLOWS: dict[IdentityProvider, CreateFlow] = {
    # [impl->req~users-create-user-serves-anonymous-first-time~1]
    IdentityProvider.anonymous: CreateFlow.anonymous,
    # [impl->req~users-create-user-serves-registered-first-time~1]
    IdentityProvider.google: CreateFlow.registered,
    IdentityProvider.apple: CreateFlow.registered,
}


class ProviderNotLinkedCause(StrEnum):
    """The bounded cause an internal `provider_not_linked` rejection carries in audit details.
    It distinguishes the empty, invalid-shape and supported-provider-mismatch cases."""
    empty_provider_data = "empty_provider_data"
    invalid_provider_data_shape = "invalid_provider_data_shape"
    supported_provider_mismatch = "supported_provider_mismatch"


# The two causes a successful, classifiable lookup produces. Both name the flow the client must
# switch to; the invalid-shape cause names none.
DETERMINATE_CAUSES: frozenset[ProviderNotLinkedCause] = frozenset({
    ProviderNotLinkedCause.empty_provider_data,
    ProviderNotLinkedCause.supported_provider_mismatch,
})


# --- The operation-specific client class -------------------------------------------------------

CREATE_FLOW_MISMATCH_CLASS: ErrorCode = "create_flow_mismatch"

# Its remediation is genuinely its own: switch to the flow `required_flow` names and retry there
# once with a freshly prepared challenge. It is not a durable block and not device-grant
# exhaustion, so it is neither terminal nor a reason to stop a grant path.
CREATE_FLOW_MISMATCH_REMEDIATION = Remediation(
    action="switch_to_the_flow_named_by_required_flow_and_retry_there_once",
    http_status=409, fresh_challenge=True, switch_flow=True)

register_endpoint_class(CREATE_FLOW_MISMATCH_CLASS, CREATE_FLOW_MISMATCH_REMEDIATION, 409)

# `provider_not_linked` surfaces through the shared `operation_not_allowed` class by default —
# the reading the anonymous upgrade and this endpoint's invalid-shape cause both take. Only the
# two determinate wrong-flow causes below are remapped, per rejection, onto `create_flow_mismatch`.
if AuthEventResult.provider_not_linked not in RESULT_TO_CLASS:
    register_client_class(AuthEventResult.provider_not_linked,
                          ClientErrorClass.operation_not_allowed.value,
                          REMEDIATIONS[ClientErrorClass.operation_not_allowed].http_status)


# Every internal result this endpoint's own rules can produce, and the barrier and challenge
# results it inherits. The client class of each is read from the shared taxonomy, so this
# endpoint holds no second copy of the shared mapping.
CREATE_USER_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.invalid_external_jwt,
    AuthEventResult.firebase_user_unresolved,
    AuthEventResult.historical_identity,
    AuthEventResult.blocked_user,
    AuthEventResult.identity_already_linked,
    AuthEventResult.challenge_not_found,
    AuthEventResult.challenge_expired,
    AuthEventResult.challenge_consumed,
    AuthEventResult.challenge_identity_mismatch,
    AuthEventResult.challenge_operation_mismatch,
    AuthEventResult.policy_rejected,
    AuthEventResult.provider_account_already_linked,
    AuthEventResult.provider_not_linked,
    AuthEventResult.firebase_lookup_unavailable,
})


def create_user_client_class(result: AuthEventResult, *,
                             cause: ProviderNotLinkedCause | None = None) -> ErrorCode:
    """The opaque client-visible class a rejection returns, mapped from the underlying internal
    `core.auth_event_result`. Every provider rejection is audited under an internal result more
    specific than the class it surfaces as: the two determinate wrong-flow causes take this
    endpoint's own `create_flow_mismatch`, and the invalid-shape cause — an unrecognized,
    otherwise-unresolvable provider state routed to support with no flow named — takes the
    shared `operation_not_allowed`."""
    # [impl->req~users-create-user-error-class-mapping~1]
    if result not in CREATE_USER_RESULTS:
        raise CreateUserError(f"{result} is no rejection of POST /auth/create-user")
    if result is AuthEventResult.provider_not_linked:
        if cause is None:
            raise CreateUserError("a provider_not_linked rejection names its bounded cause")
        return (CREATE_FLOW_MISMATCH_CLASS if cause in DETERMINATE_CAUSES
                else ClientErrorClass.operation_not_allowed.value)
    if cause is not None:
        raise CreateUserError(f"{result} carries no provider cause")
    client_class, _status = surface(result)
    return client_class


def audited_result_for(result: AuthEventResult, client_class: ErrorCode) -> AuthEventResult:
    """The audit row records the specific internal `core.auth_event_result` regardless of which
    client class is returned, and that audited value is never less specific than the class: two
    results that share a class stay distinct in the row."""
    # [impl->req~users-create-user-audit-specific-result~1]
    if result not in CREATE_USER_RESULTS:
        raise CreateUserError(f"{result} is no rejection of POST /auth/create-user")
    sharing = {other for other in CREATE_USER_RESULTS
               if other is not result and _class_of(other) == client_class}
    if str(result) == client_class and sharing:
        raise CreateUserError(f"{result} is less specific than {client_class}")
    return result


def _class_of(result: AuthEventResult) -> ErrorCode:
    if result is AuthEventResult.provider_not_linked:
        return ClientErrorClass.operation_not_allowed.value
    return surface(result)[0]


def required_flow_for(classified: IdentityProvider) -> CreateFlow:
    """The flow `create_flow_mismatch` names, set only from the successful Firebase Admin
    `providerData` classification: a recognized registered provider yields `registered`, none
    linked — empty `providerData` — yields `anonymous`. The client's own declaration is never
    authoritative, and an Admin/declaration conflict resolves in the Admin result's favour."""
    # [impl->req~users-create-flow-mismatch-class~1]
    assert_provider_source(ProviderSource.firebase_admin_provider_data)
    return CREATE_USER_FLOWS[classified]


def create_flow_mismatch_response(required_flow: CreateFlow) -> ClientRejection:
    """`create_flow_mismatch` is returned with HTTP 409 in the shared response shape, carrying
    the mandatory machine-readable `required_flow` field. A rejection without a successful,
    classifiable lookup names no flow and never reaches this builder."""
    # [impl->req~users-create-flow-mismatch-class~1]
    if required_flow not in set(CreateFlow):
        raise CreateUserError(f"{required_flow} is no create-user flow")
    rejection = client_response(CREATE_FLOW_MISMATCH_CLASS)
    if rejection.status != 409:
        raise CreateUserError("create_flow_mismatch is returned with HTTP 409")
    return ClientRejection(status=rejection.status,
                           body={**rejection.body, "required_flow": required_flow.value},
                           headers=rejection.headers)


def provider_not_linked_details(cause: ProviderNotLinkedCause) -> dict[str, Any]:
    """Any declaration the closed classifier does not confirm is audited as
    `provider_not_linked`, with the bounded cause in the audit row's details."""
    # [impl->req~users-create-user-provider-not-linked-audit~1]
    if cause not in set(ProviderNotLinkedCause):
        raise CreateUserError(f"{cause} is no bounded provider_not_linked cause")
    return {"failure": {"reason": cause.value}}


class CreateUserRejection(ChallengeRejection):
    """A `create_user` rejection: the specific internal result for the audit row, this
    endpoint's client class for the response, and — for the two determinate wrong-flow causes —
    the flow the client must switch to."""

    def __init__(self, result: AuthEventResult, *,
                 cause: ProviderNotLinkedCause | None = None,
                 required_flow: CreateFlow | None = None,
                 detail: str | None = None):
        super().__init__(result, detail=detail or (cause.value if cause else None))
        self.cause = cause
        self.required_flow = required_flow
        # [impl->req~users-create-user-error-class-mapping~1]
        self.error_code = create_user_client_class(result, cause=cause)
        self.status_code = client_response(self.error_code).status
        audited_result_for(result, self.error_code)
        if (self.error_code == CREATE_FLOW_MISMATCH_CLASS) != (required_flow is not None):
            raise CreateUserError("create_flow_mismatch names a flow; no other class does")

    def response(self) -> ClientRejection:
        """The shared response shape this rejection returns."""
        # [impl->req~users-create-user-provider-not-linked-audit~1]
        if self.required_flow is not None:
            return create_flow_mismatch_response(self.required_flow)
        return client_response(self.error_code)


# --- The mandatory Firebase Admin lookup and the closed classifier -------------------------------


@dataclass(frozen=True, slots=True)
class AdminLookupResult:
    """The fields of one successful `getUser(subject)` response `create_user` reads."""
    provider_data: tuple[Any, ...] = ()
    email: str | None = None
    email_verified: bool = False

    @property
    def record(self) -> AdminUserRecord:
        return AdminUserRecord(email=self.email, email_verified=self.email_verified)


@dataclass(frozen=True, slots=True)
class ConfirmedCreation:
    """What the live lookup confirmed: the classified provider, its `provider_uid`, and the
    same response's email fields. Nothing here comes from the client."""
    provider: IdentityProvider
    provider_uid: str | None
    lookup: AdminLookupResult
    lookups: int = 1


# The token claim this operation never reads. The provider is derived from the Admin
# `providerData` response alone.
TOKEN_SIGN_IN_PROVIDER_CLAIM = "firebase.sign_in_provider"

# Provider header names a client might send. None of them is read, and none of them missing is
# ever a rejection reason.
PROVIDER_HEADER_NAMES: frozenset[str] = frozenset({
    "x-provider", "x-auth-provider", "x-identity-provider", "x-firebase-provider"})


def classify_admin_provider_data(provider_data: Sequence[Any], *,
                                 token_claims: Mapping[str, Any] | None = None
                                 ) -> IdentityProvider:
    """The closed classifier over a successful `providerData` response: no entries is
    `anonymous`, exactly one `google.com` entry is `google`, exactly one `apple.com` entry is
    `apple`, and every other shape — entries for both supported providers, multiple entries, or
    any unrecognized entry — is invalid and rejects with no persistence. The backend never takes
    the first recognized entry, never classifies non-empty `providerData` as `anonymous`, and
    never reads the token's `firebase.sign_in_provider` claim."""
    # [impl->req~users-create-user-step-03~1]
    # [impl->req~users-create-user-step-04~1]
    if token_claims is not None:
        raise CreateUserError(f"{TOKEN_SIGN_IN_PROVIDER_CLAIM} is never a provider source")
    try:
        return classify_provider(provider_data)
    except ProviderClassificationError:
        raise CreateUserRejection(
            AuthEventResult.provider_not_linked,
            cause=ProviderNotLinkedCause.invalid_provider_data_shape) from None


def assert_no_provider_header_requirement(headers: Mapping[str, Any] | None = None,
                                          token_claims: Mapping[str, Any] | None = None) -> None:
    """A missing provider header or claim is not a rejection reason, and token-presented
    provider values are not read by this operation."""
    # [impl->req~users-create-user-no-provider-header-requirement~1]
    for source in (ProviderSource.request_header, ProviderSource.token_claim):
        try:
            assert_provider_source(source)
        except ProviderClassificationError:
            continue
        raise CreateUserError(f"{source} is not a provider source for create_user")
    # Whatever a client sent under those names is ignored rather than validated or rejected.
    _ = (headers, token_claims)


def confirm_declaration(declared: IdentityProvider, lookup: AdminLookupResult) -> ConfirmedCreation:
    """The classified provider must equal the client declaration. A declared-anonymous
    completion therefore requires empty `providerData`, and a subject with Google or Apple
    attached is refused toward the registered flow rather than silently recorded as anonymous;
    a declared registered provider requires the matching single-entry classification. For
    `google` or `apple` the matching entry's non-empty `uid` is the only source of
    `provider_uid`, and a missing or empty `uid` is a malformed lookup result that rejects with
    no persistence under the shared lookup-failure handling."""
    # [impl->req~users-create-user-step-04~1]
    # Declaration match is the shared procedure's own stage: an anonymous completion therefore
    # requires an empty `providerData`, and a registered one requires the classifier to return the
    # declared `google` or `apple`. Neither branch persists anything on a mismatch, and neither
    # silently records the account as the other kind.
    # [impl->req~sessions-declaration-match~1]
    # [impl->req~sessions-declaration-anonymous-create-user~1]
    # [impl->req~sessions-declaration-registered-create-user~1]
    classified = classify_admin_provider_data(lookup.provider_data)
    try:
        assert_declared_provider(classified, declared)
    except ProviderDeclarationMismatchError:
        # A successful lookup the classifier classified: the flow is named from that
        # classification, never from the declaration. A declared-anonymous completion that finds
        # a Google or Apple login attached is refused toward `required_flow = registered`; a
        # declared-registered completion that finds an empty result is refused toward
        # `required_flow = anonymous` and never persists `anonymous` on that path.
        # [impl->req~users-create-user-provider-not-linked-audit~1]
        cause = (ProviderNotLinkedCause.empty_provider_data
                 if classified is IdentityProvider.anonymous
                 else ProviderNotLinkedCause.supported_provider_mismatch)
        raise CreateUserRejection(AuthEventResult.provider_not_linked, cause=cause,
                                  required_flow=required_flow_for(classified)) from None
    # A missing or empty `uid` on the matching entry is a malformed lookup result. Taken on the
    # claimed row, it rejects with no persistence through the shared lookup-failure handling and
    # consumes the challenge like every other rejection at or after the mandatory lookup.
    try:
        provider_uid = provider_uid_for(classified, lookup.provider_data)
    except ProviderLookupFailedError as failure:
        raise lookup_rejection(failure) from None
    if classified in REGISTERED_PROVIDERS and not provider_uid:
        raise lookup_rejection(lookup_unavailable())
    return ConfirmedCreation(provider=classified, provider_uid=provider_uid, lookup=lookup)


def classify_lookup_error(error: BaseException) -> LookupFailure:
    """Which shared lookup failure a raised Admin error is. The subject deleted at Firebase
    after token mint is the one non-retryable cause; every other shape — transient,
    infrastructure, malformed or otherwise indeterminate — is retryable."""
    # [impl->req~users-create-user-firebase-user-not-found~1]
    # [impl->req~users-create-user-lookup-unavailable~1]
    if type(error).__name__ in ("UserNotFoundError", "UserNotFound"):
        return LookupFailure.user_not_found
    if isinstance(error, ValueError | TypeError | KeyError | AttributeError):
        return LookupFailure.malformed_response
    return LookupFailure.transient


def lookup_failure(failure: LookupFailure) -> ProviderLookupFailedError:
    """The shared fail-closed lookup failure for a raised Admin error, built by the one place
    that decides which internal result and client class each failure carries."""
    # [impl->req~users-create-user-lookup-unavailable~1]
    try:
        provider_from_lookup(None, failure=failure)
    except ProviderLookupFailedError as error:
        return error
    raise CreateUserError("a failed lookup never yields a provider")


def lookup_rejection(failure: ProviderLookupFailedError) -> CreateUserRejection:
    """A failed mandatory lookup, taken on the claimed row: the distinct internal result the
    shared lookup-failure handling assigned — `firebase_user_unresolved` for the subject deleted
    at Firebase, `firebase_lookup_unavailable` for every indeterminate cause — audited as itself
    and surfaced through the class that result maps to. It is a `ChallengeRejection`, so the
    shared completion machinery consumes the challenge and writes the rejection's audit row
    rather than letting an `IdentityError` escape the completion path."""
    # The challenge is consumed whether the attempt succeeds or is rejected, so a rejected
    # provider lookup leaves the client to prepare a fresh challenge and retry: raising a
    # `ChallengeRejection` here is what puts this rejection on the shared consuming path, and no
    # challenge-recycling path exists.
    # [impl->req~users-create-user-firebase-user-not-found~1]
    # [impl->req~users-create-user-lookup-unavailable~1]
    # [impl->req~users-create-user-rejection-consumes-challenge~1]
    # [impl->req~sessions-failure-challenge-consumed~1]
    rejection = CreateUserRejection(failure.result)
    if rejection.error_code != failure.client_class:
        raise CreateUserError(f"{failure.result} surfaces as {failure.client_class}")
    return rejection


async def firebase_admin_get_user(client: Any, subject: str) -> AdminLookupResult:
    """One `getUser(subject)` read through the issuer-selected Admin client. Every failure is
    converted into the shared fail-closed lookup failure; nothing is persisted on any of them."""
    # [impl->req~users-create-user-lookup-unavailable~1]
    from firebase_admin import auth  # noqa: PLC0415 - imported lazily so tests need no app

    try:
        record = await asyncio.to_thread(auth.get_user, subject, app=client)
    except Exception as cause:
        raise lookup_failure(classify_lookup_error(cause)) from cause
    # An absent or null `providerData` attribute is a malformed response, not an empty result.
    # Defaulting it to `()` here would classify the account `anonymous` off a malformed Admin
    # response and persist that classification, which is exactly what a failed or indeterminate
    # lookup must never be read as.
    # [impl->req~sessions-providerdata-lookup-failure~1]
    entries = getattr(record, "provider_data", None)
    if entries is None:
        raise lookup_failure(LookupFailure.malformed_response)
    # The record's shape is judged in one place, the procedure's own lookup-failure stage: a
    # `providerData` that is not a sequence of readable entries stops the operation there.
    provider_from_lookup(entries)
    return AdminLookupResult(provider_data=tuple(entries),
                             email=getattr(record, "email", None),
                             email_verified=bool(getattr(record, "email_verified", False)))


# --- What the completion transaction writes -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NewUser:
    """The `core.users` row this completion creates. Custom access tiers are `core.access_tiers`
    rows and `core.access_grants` rows, never fields here, and neither is any plan or free-access
    column."""
    # [impl->req~users-custom-tiers-not-user-fields~1]
    id: UUID
    email: str | None = None
    registered_at: datetime | None = None
    display_name: None = None


# The store-scoped purchase-attribution tokens a new account mints, one per store, each a random
# UUID and each for the life of the account. "Provider" here means the store, not the identity
# provider, and there is no identity-kind dimension.
ATTRIBUTION_TOKEN_FIELDS: dict[str, str] = {
    "apple": "app_account_token",
    "google_play": "obfuscated_external_account_id",
}

# What `create_user` writes towards grants and monthly usage: nothing at all.
CREATE_USER_GRANT_ROWS: frozenset[str] = frozenset()
CREATE_USER_USAGE_ROWS: frozenset[str] = frozenset()


def new_user_row(provider: IdentityProvider, record: AdminUserRecord | None, *,
                 now: datetime) -> NewUser:
    """The profile rules, applied in the completion transaction and committing with it."""
    # If the classified provider is `anonymous`, `registered_at` remains `NULL`; if it is
    # `google` or `apple`, `registered_at` is set.
    # [impl->req~users-profile-anonymous-registered-at-null~1]
    # [impl->req~users-profile-registered-at-set~1]
    registered = provider in REGISTERED_PROVIDERS
    registered_at = now if registered else None
    # For registered creation the initial `email` is copied only when the same successful
    # `getUser` response carries a non-empty address reported as `emailVerified = true`.
    # [impl->req~users-profile-email-copy-conditions~1]
    email = initial_email_on_create(record) if registered else None
    # `registered_at IS NOT NULL` exactly when the stored provider is registered, and the
    # provider, the timestamp and any email copy commit together in this one transaction.
    # [impl->req~users-profile-registered-at-pairing~1]
    assert_pairing_enforced_in_code(provider, registered_at)
    # `display_name` is not populated from auth context or the Admin user record.
    # [impl->req~users-profile-display-name-not-populated~1]
    return NewUser(id=uuid7(), email=email, registered_at=registered_at, display_name=None)


def assert_pairing_enforced_in_code(provider: IdentityProvider,
                                    registered_at: datetime | None) -> None:
    """Code in the completion transaction enforces the provider/`registered_at` pairing: there
    is no cross-table constraint trigger, and authorization, grant classification and audit
    interpretation must not invent a third state beyond anonymous and registered."""
    # [impl->req~users-profile-pairing-enforced-in-code~1]
    if PAIRING_ENFORCEMENT_MECHANISMS:
        raise CreateUserError("no cross-table constraint trigger enforces this pairing")
    assert_registered_at_pairing(provider, registered_at)
    if account_class(provider) not in set(AccountClass):
        raise CreateUserError("there is no third account state to invent")


def assert_valid_without_grant(user: NewUser, *, grants: Iterable[str] = ()) -> NewUser:
    """A newly created user may exist with no active access grant until a separate explicit
    grant path creates one, and `create_user` is not that path."""
    # [impl->req~users-profile-no-grant-required~1]
    # [impl->req~users-create-user-step-10~1]
    offending = sorted(grants)
    if offending or CREATE_USER_GRANT_ROWS:
        raise CreateUserError(f"create_user creates no access grant: {offending}")
    return user


def assert_no_monthly_usage_row(rows: Iterable[str] = ()) -> None:
    """`create_user` creates no `core.user_monthly_usage` row; consumption state is owned by
    the grant that authorizes it, and no grant exists yet."""
    # [impl->req~users-create-user-step-11~1]
    offending = sorted(rows)
    if offending or CREATE_USER_USAGE_ROWS:
        raise CreateUserError(f"create_user creates no user_monthly_usage row: {offending}")


def mint_attribution_tokens() -> dict[str, str]:
    """This user's store-scoped purchase-attribution tokens, generated once: one Apple
    `app_account_token` and one Google `obfuscated_external_account_id`, each a random UUID.
    A user has at most one token per store for the life of the account, and this applies to
    anonymous and registered first-time users alike."""
    # [impl->req~users-create-user-step-09~1]
    tokens = {store: str(uuid4()) for store in ATTRIBUTION_TOKEN_FIELDS}
    if len(set(tokens.values())) != len(ATTRIBUTION_TOKEN_FIELDS):
        raise CreateUserError("each store gets its own random attribution token")
    return tokens


def onboarding_audit_details(*, user: NewUser, identity: ExternalIdentityRow,
                             tokens: Mapping[str, str]) -> dict[str, Any]:
    """The success audit record captures the committed onboarding mutation: the created user and
    identity rows, the stored provider, whether the account committed as registered, and which
    stores minted an attribution token. The token values themselves are not part of the record."""
    # [impl->req~users-create-user-step-12~1]
    details = structured_details({
        "resolved": {"user_id": str(user.id), "external_identity_id": str(identity.id)},
        "mutation": {"created_user": True,
                     "identity_provider": str(identity.provider),
                     "registered": user.registered_at is not None,
                     "attribution_stores": sorted(tokens)},
    })
    mutation = details["mutation"]
    if not mutation.get("created_user") or not details["resolved"].get("external_identity_id"):
        raise CreateUserError("the success audit record captures the committed mutation")
    if any(value in str(details) for value in tokens.values()):
        raise CreateUserError("the audit record carries no attribution token value")
    return details


def assert_one_transaction(session: Any, *used: Any) -> Any:
    """Steps 6 to 12 all run in the shared consuming transaction, and that transaction's single
    commit is what makes the account exist. The endpoint opens no session and commits none of
    its own, so a partial account cannot be committed ahead of the challenge consumption."""
    # [impl->req~users-create-user-step-13~1]
    for transaction in used:
        if transaction is not session:
            raise CreateUserError("every create_user write shares the consuming transaction")
    return session


def race_loser_rejection() -> CreateUserRejection:
    """`UNIQUE (issuer, subject)` is the final arbiter between concurrent completions: the
    winner creates the account, and the loser rolls every business mutation back, returns the
    `identity_already_linked` conflict and records its own `identity_already_linked` audit
    result. Its challenge consumption and rejected audit row survive that rollback, because
    single-use applies to rejected attempts. The violation never escapes as a generic `500` and
    is never audited as `invalid_external_jwt`; the loser recovers through `/auth/sync` and
    proceeds on the winner's account, and no path merges, overwrites, creates a second user or
    treats the retry as idempotent success."""
    # [impl->req~users-create-user-race-arbitration~1]
    # `UNIQUE (issuer, subject)` with `UNIQUE (user_id)` is the final arbiter between two
    # completions that both observed an unlinked subject, and the loser rolls back every business
    # mutation — reading and writing no per-device grant state on the way.
    # [impl->req~sessions-create-user-unique-constraint-arbiter~1]
    # The loser needs no recovery API: the same token now resolves as linked, so the client calls
    # `POST /auth/sync` and proceeds on the winning account.
    # [impl->req~sessions-loser-no-recovery-api~1]
    outcome = uniqueness_race_loser()
    if outcome.result is not already_linked_result(AlreadyLinkedSite.uniqueness_race_loser):
        raise CreateUserError("the race loser audits as identity_already_linked")
    rejection = CreateUserRejection(outcome.result)
    if rejection.status_code == 500 or rejection.result is AuthEventResult.invalid_external_jwt:
        raise CreateUserError("the uniqueness violation is neither a 500 nor an invalid JWT")
    # A losing attempt is never reported as idempotent success, so its remediation is the sync
    # route rather than a success body, and it names no second account of its own.
    # [impl->req~sessions-loser-no-recovery-api~1]
    if rejection.error_code != ClientErrorClass.identity_already_linked:
        raise CreateUserError("the loser returns the identity_already_linked conflict")
    if REMEDIATIONS[ClientErrorClass.identity_already_linked].next_route != route_for(
            AuthOperation.sync)[1]:
        raise CreateUserError("the loser's remediation is POST /auth/sync")
    return rejection


def provider_conflict_rejection() -> CreateUserRejection:
    """A registered-provider uniqueness conflict is `provider_account_already_linked`: the whole
    business mutation rolls back, so no user, identity, grant, profile mutation or
    purchase-attribution token is created."""
    # [impl->req~users-create-user-step-08~1]
    conflict = provider_account_conflict(AuthOperation.create_user)
    return CreateUserRejection(conflict.result)


def rejects_before_commit(result: AuthEventResult, *, committed: bool) -> bool:
    """Rejection covers at minimum any endpoint-specific failure before the onboarding
    transaction commits. Once that transaction has committed there is no rejection left to
    return: the account exists and the client reconciles instead."""
    # [impl->req~users-create-user-failure-scope~1]
    if committed:
        if result is not AuthEventResult.succeeded:
            raise CreateUserError("a failure after the commit is not a create_user rejection")
        return False
    if result is AuthEventResult.succeeded:
        return False
    if result not in CREATE_USER_RESULTS:
        raise CreateUserError(f"{result} is no failure of this endpoint")
    return True


# Replaying the consumed challenge is not one of the client's options; the server stores no
# completion result to hand back.
CONSUMED_CHALLENGE_REPLAY_OPTIONS: frozenset[str] = frozenset()


def lost_response_recovery() -> tuple[str, str]:
    """A user whose response is lost after the onboarding transaction commits uses a later
    `/auth/sync`; the consumed challenge is never replayed, because the server stores no
    completion result to hand back."""
    # [impl->req~users-create-user-lost-response-uses-sync~1]
    sync_route, fresh_challenge = reconciliation_options()
    if sync_route != route_for(AuthOperation.sync):
        raise CreateUserError("the lost-response recovery is a later /auth/sync")
    if CONSUMED_CHALLENGE_REPLAY_OPTIONS or "challenge=true" not in fresh_challenge:
        raise CreateUserError("a consumed challenge is never replayed")
    return sync_route


# --- The endpoint --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateUserLiveState:
    """What the transactional re-resolution found. `create_user` proceeds only from pre-auth."""
    outcome: ResolutionOutcome


@dataclass(frozen=True, slots=True)
class CreatedAccount:
    """The resulting backend state, with no backend token in it."""
    user: NewUser
    identity: ExternalIdentityRow
    attribution_tokens: Mapping[str, str]
    audit_details: Mapping[str, Any] = field(default_factory=dict)
    backend_token: None = None


class AccountStore(Protocol):
    """The database half of the onboarding transaction, as this endpoint calls it."""

    async def resolve(self, session: Any, issuer: str,
                      subject: str) -> ResolutionOutcome:
        """Authoritatively re-resolve `(issuer, subject)` inside the consuming transaction."""
        ...

    async def insert_account(self, session: Any, *, user: NewUser,
                             identity: ExternalIdentityRow,
                             tokens: Mapping[str, str]) -> None:
        """Insert the user row, its identity row and its attribution tokens together. Raises
        `IdentityAlreadyLinkedError` on `UNIQUE (issuer, subject)` and
        `ProviderAccountAlreadyLinkedError` on the provider-account reservation."""
        ...


class CreateUserEndpoint:
    """The endpoint half `SharedChallengeService` drives for `POST /auth/create-user`."""

    operation = AuthOperation.create_user

    def __init__(self, *,
                 integrations: FirebaseIntegrations,
                 accounts: AccountStore,
                 lookup: Callable[[Any, str], Awaitable[AdminLookupResult]] | None = None,
                 clock: Callable[[], datetime] | None = None,
                 ledger: AdmissionLedger | None = None,
                 admit: Callable[[], BudgetVerdict] | None = None):
        self._integrations = integrations
        self._accounts = accounts
        self._lookup = lookup or firebase_admin_get_user
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ledger = ledger
        self._admit = admit
        self.lookups = 0

    # --- prepare ---------------------------------------------------------------------------

    async def check_prepare_eligibility(self, identity: VerifiedIdentityContext,
                                        variant: IdentityProvider | None) -> None:
        """`create_user` is first-time account creation, used when the current identity is
        unlinked and no upgrade, anonymous grant claim or paid restore is being attempted; the
        other three operations have their own endpoints and never fall through to this one."""
        # [impl->req~users-create-user-purpose~1]
        create_user_prepare_constraints(identity, variant.value if variant else None)

    # --- completion ------------------------------------------------------------------------

    async def verify_proof(self, identity: VerifiedIdentityContext, challenge: ChallengeRow,
                           body: Mapping[str, Any] | None) -> ConfirmedCreation:
        """Mutation rules 1 to 4: the declared provider against the bound variant, the one
        mandatory Admin lookup, and the closed classification of its response."""
        # No endpoint work runs unless this attempt already holds the claim, so every rejection
        # from here on — the ones at and after the mandatory Admin lookup included — is taken on
        # a claimed row and consumes the challenge under the shared completion requirements. A
        # retry therefore needs a freshly prepared challenge.
        # [impl->req~users-create-user-rejection-consumes-challenge~1]
        assert_pre_consumption_checks_first(challenge)
        declared = self.declared_provider(challenge, body)
        lookup = await self.mandatory_lookup(identity)
        # The provider fields this completion may write come from this read point alone.
        assert_may_write_provider_fields(
            ProviderDataReadPoint.registered_create_user_completion
            if declared in REGISTERED_PROVIDERS
            else ProviderDataReadPoint.anonymous_create_user_completion)
        return confirm_declaration(declared, lookup)

    def declared_provider(self, challenge: ChallengeRow,
                          body: Mapping[str, Any] | None) -> IdentityProvider:
        """1. Read the `provider` field from the completion request and require it to equal the
        exact normalized variant prepare persisted, compared byte-for-byte. Completion applies
        no default and no re-normalization, so a missing or differing value is a mismatch rather
        than something to resolve, and the shared completion check rejects it as
        `challenge_operation_mismatch` — a consuming rejection — before any Admin lookup."""
        # [impl->req~users-create-user-step-01~1]
        declared = (body or {}).get("provider")
        if not isinstance(declared, str) or not variants_equal(declared,
                                                               challenge.operation_variant):
            raise CreateUserRejection(AuthEventResult.challenge_operation_mismatch)
        if self.lookups:
            raise CreateUserError("the variant is compared before the Firebase Admin lookup")
        variant = challenge.operation_variant
        if variant is None:
            raise CreateUserError("a create_user challenge binds a normalized provider variant")
        return variant

    async def mandatory_lookup(self, identity: VerifiedIdentityContext) -> AdminLookupResult:
        """2. After the completion and Firebase-lookup admission checks pass, perform exactly
        one mandatory, fail-closed Firebase Admin `getUser(subject)` read immediately before the
        write transaction. It applies to every completion, declared-anonymous creation included,
        it uses only the issuer-selected Admin client, and no branch may skip it."""
        # [impl->req~users-create-user-step-02~1]
        if self.lookups:
            raise CreateUserError("exactly one getUser read is performed per completion")
        # Firebase user-not-found is non-retryable and consumes no retry budget; a transient,
        # infrastructure, matched-integration selection, malformed or otherwise indeterminate
        # failure is retried inside this one logical read and then surfaces as
        # `firebase_lookup_unavailable`. Neither persists anything, here or anywhere else, and
        # both are taken on the claimed row: the rejection consumes the challenge and is audited
        # under its own distinct internal result.
        # [impl->req~users-create-user-firebase-user-not-found~1]
        # [impl->req~users-create-user-lookup-unavailable~1]
        # [impl->req~users-create-user-rejection-consumes-challenge~1]
        try:
            client = issuer_selected_admin_client(self._integrations, identity.issuer)
            self.lookups += 1
            return await firebase_identity_lookup(lambda: self._lookup(client, identity.subject),
                                                  ledger=self._ledger, admit=self._admit)
        except ProviderLookupFailedError as failure:
            raise lookup_rejection(failure) from None

    async def confirm_live_state(self, session: Any, identity: VerifiedIdentityContext,
                                 challenge: ChallengeRow) -> CreateUserLiveState:
        """5. Inside the shared completion/consumption transaction, authoritatively re-resolve
        `(issuer, subject)`: prepare-time pre-auth status never suffices. An active row whose
        user is active rejects with `identity_already_linked`; a `historical` row, or one whose
        linked user is blocked, rejects with `account_unavailable` while retaining its distinct
        internal audit result. Neither performs any business mutation.

        The completion phase is the second of the two phases a linked identity is ineligible for,
        and it takes the same `identity_already_linked` rejection the prepare phase does.

        Nothing observed at prepare time is evidence here: this re-resolution inside the
        consuming transaction is the authoritative one, and an active row found at this point
        mutates no user, identity, profile or grant state."""
        # [impl->req~users-create-user-step-05~1]
        # [impl->req~sessions-linked-identity-ineligible-for-create-user~1]
        # [impl->req~sessions-create-user-completion-re-resolves~1]
        # [impl->req~sessions-create-user-preauth-only~1]
        issuer, subject = context_pair(identity)
        outcome = await self._accounts.resolve(session, issuer, subject)
        if outcome is ResolutionOutcome.linked:
            raise CreateUserRejection(
                already_linked_result(AlreadyLinkedSite.completion_identity_reresolution))
        if outcome in (ResolutionOutcome.historical_identity, ResolutionOutcome.blocked_user):
            result, _client_class = unavailable_account(outcome, *CREATE_USER_ROUTE)
            raise CreateUserRejection(result)
        if outcome is not ResolutionOutcome.pre_auth:
            raise CreateUserError(f"{outcome} is no outcome create_user admits")
        return CreateUserLiveState(outcome=outcome)

    async def mutate(self, session: Any, identity: VerifiedIdentityContext,
                     challenge: ChallengeRow, proof: ConfirmedCreation,
                     live: CreateUserLiveState) -> CreatedAccount:
        """Mutation rules 6 to 14, all inside the one consuming transaction."""
        assert_pre_consumption_checks_first(challenge)
        if live.outcome is not ResolutionOutcome.pre_auth or proof.lookups != 1:
            raise CreateUserError("the mutation runs once, from a re-resolved pre-auth identity")
        issuer, subject = context_pair(identity)

        # 6. create `core.users` inside that same transaction, with the profile rules applied.
        # [impl->req~users-create-user-step-06~1]
        user = new_user_row(proof.provider, proof.lookup.record, now=self._clock())

        # 7. create exactly one active `core.external_identities` row for the backend-verified
        # pair and the new user, in the same transaction. The classified provider is persisted;
        # `provider_uid` is `NULL` for `anonymous` — never a sentinel — and for `google` or
        # `apple` it is the matching `providerData.uid`, under the partial unique reservation
        # over `(issuer, provider, provider_uid)`.
        # [impl->req~users-create-user-step-07~1]
        row = ExternalIdentityRow(id=uuid7(), user_id=user.id, issuer=issuer, subject=subject,
                                  provider=proof.provider, provider_uid=proof.provider_uid,
                                  identity_state=IdentityState.active)
        creation = create_account(user_id=user.id, identity=row, user_transaction=session,
                                  identity_transaction=session)

        # 9. the store-scoped purchase-attribution tokens, generated once and persisted as
        # `core.store_purchase_tokens` rows in this same transaction.
        # [impl->req~users-create-user-step-09~1]
        tokens = mint_attribution_tokens()
        try:
            await self._accounts.insert_account(session, user=user, identity=creation.identity,
                                                tokens=tokens)
        except ProviderAccountAlreadyLinkedError:
            # 8. a registered-provider uniqueness conflict rolls the whole mutation back, so no
            # user, identity, grant, profile mutation or attribution token is created.
            # [impl->req~users-create-user-step-08~1]
            raise provider_conflict_rejection() from None
        except IdentityAlreadyLinkedError:
            # The concurrent race loser: `UNIQUE (issuer, subject)` arbitrates.
            # [impl->req~users-create-user-race-arbitration~1]
            raise race_loser_rejection() from None

        # 10 and 11: no access grant and no `core.user_monthly_usage` row. `create_user` creates
        # account and identity state only, and allocates no anonymous free credits.
        # [impl->req~users-create-user-state-only-no-credits~1]
        assert_valid_without_grant(user)
        assert_no_monthly_usage_row()
        assert_no_free_credits()

        # 12. the success audit record capturing the committed onboarding mutation, written by
        # the shared writer inside this same transaction.
        # [impl->req~users-create-user-step-12~1]
        details = onboarding_audit_details(user=user, identity=creation.identity, tokens=tokens)

        # 13. this transaction — and only this one — commits.
        # [impl->req~users-create-user-step-13~1]
        assert_one_transaction(session, creation.transaction)

        # 14. return the resulting backend state, with no backend token issued. Promotion of the
        # pre-auth identity is complete here: the identity row carrying the classified provider,
        # the user row and its `registered_at`, and any verified-email copy all commit with this
        # one transaction, and nothing is handed back but that state.
        # [impl->req~users-create-user-step-14~1]
        # [impl->req~sessions-preauth-promotion-obligations~1]
        # [impl->req~sessions-promotion-create-identity-row~1]
        # [impl->req~sessions-promotion-single-transaction~1]
        # [impl->req~sessions-promotion-no-backend-token~1]
        complete_create_user(user_id=user.id, identity=creation.identity,
                             completion_transaction=session, identity_transaction=session,
                             classified=proof.provider)
        return CreatedAccount(user=user, identity=creation.identity,
                              attribution_tokens=tokens, audit_details=details)
