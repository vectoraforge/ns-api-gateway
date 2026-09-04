"""The one client-visible error tree: one base, one response model, one totality check."""
import logging
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from nativespeaker.api.auth.jwt_verifier import BoundedReason
from nativespeaker.api.tables.identities import IdentityProvider
from nativespeaker.api.tables.purchases import PurchaseProvider

# The codes the body may carry. A typo is a ValidationError at construction, not a runtime 500.
ErrorCode = Literal["auth_required",
                    "preauth_identity_not_allowed",
                    "account_unavailable",
                    "challenge_required",
                    "invalid_request",
                    "verification_temporarily_unavailable",
                    "rate_limited",
                    "validation_error",
                    "not_found",
                    "method_not_allowed",
                    "internal_error",
                    "service_unavailable",
                    "quota_exceeded",
                    "out_of_scope",
                    "identity_already_linked",
                    "operation_not_allowed",
                    "proof_rejected",
                    "device_grant_exhausted"]


class ErrorResponse(BaseModel):
    """The single shared error body shape. Exactly one field -- do not add more."""
    code: ErrorCode


class AppError(Exception):
    """Base for every failure that has a client-visible answer."""

    # A class declaring neither answers 500 `internal_error`: the fail-closed default, not a shortcut.
    status: int = 500
    code: ErrorCode = "internal_error"
    log_level: int | None = logging.WARNING
    answers_framework_status: bool = False

    def __init__(self, *args, headers: dict[str, str] | None = None) -> None:
        self._headers = headers
        super().__init__(*args)

    def extra_headers(self) -> dict[str, str] | None:
        return self._headers

    def log_fields(self) -> dict[str, str | None]:
        """The extra fields this failure contributes to its one log line, and the only such channel."""
        return {}


def _family[T](root: type[T]) -> list[type[T]]:
    """Every class under `root`, at any depth -- an intermediate base is not a place to hide."""
    found: list[type[T]] = []
    for subclass in root.__subclasses__():
        found.append(subclass)
        found.extend(_family(subclass))
    return found


def class_answering_status(status: int) -> type[AppError] | None:
    """The class a bare framework status resolves to, found by the walk each time it is asked."""
    for cls in _family(AppError):
        if vars(cls).get("answers_framework_status") and cls.status == status:
            return cls
    return None


# --- The generic answer for each bare framework status: silent, and carrying that status's headers ---


class InvalidRequest(AppError):
    """The generic 400: the request itself is unusable."""
    status = 400
    code = "invalid_request"
    log_level = None
    answers_framework_status = True


class AuthRequired(AppError):
    """The generic 401: no usable credential accompanied the request."""
    status = 401
    code = "auth_required"
    log_level = None
    answers_framework_status = True


class NotFound(AppError):
    """The generic 404: the addressed thing does not exist."""
    status = 404
    code = "not_found"
    log_level = None
    answers_framework_status = True


class MethodNotAllowed(AppError):
    """The generic 405. It discloses only that the path exists."""
    status = 405
    code = "method_not_allowed"
    log_level = None
    answers_framework_status = True


class ChallengeRequired(AppError):
    """The generic 409: the operation needs a challenge it was not given."""
    status = 409
    code = "challenge_required"
    log_level = None
    answers_framework_status = True


class ValidationError(AppError):
    """The generic 422: the request body did not satisfy its schema."""
    status = 422
    code = "validation_error"
    log_level = None
    answers_framework_status = True


class RateLimited(AppError):
    """The generic 429 every unspecialized rate-limit rejection carries, including Envoy's."""
    status = 429
    code = "rate_limited"
    log_level = None
    answers_framework_status = True


class InternalError(AppError):
    """The generic 500: the service failed and the client is told nothing more."""
    status = 500
    code = "internal_error"
    log_level = None
    answers_framework_status = True


class ServiceUnavailable(AppError):
    """The generic 503: the service is temporarily unable to answer."""
    status = 503
    code = "service_unavailable"
    log_level = None
    answers_framework_status = True


# No 415: `python-multipart` is absent, so a Form or File parameter cannot be declared at all.
# No generic 403: neither class at that status is the generic answer.


# --- Service arms ---


class UnsupportedLanguageError(InvalidRequest):
    """Raised when an unsupported language is requested."""

    def __init__(self, lang: str, supported: list[str]):
        self.lang = lang
        self.supported = supported
        super().__init__(f"Language '{lang}' not supported. Supported: {', '.join(supported)}")


class ChatHistoryLimitError(InvalidRequest):
    """Raised when a chat already holds as many messages as it may."""

    def __init__(self, max_messages: int):
        self.max_messages = max_messages
        super().__init__("Chat history limit reached")


class OutOfScopeError(InvalidRequest):
    """The request is outside the scope of linguistic analysis."""
    status = 400
    code = "out_of_scope"

    def __init__(self):
        super().__init__("The request is outside the scope of linguistic analysis")


class InvalidChatError(NotFound):
    """Raised when a chat id addresses no chat."""

    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")


class QuotaExceededError(RateLimited):
    """The user's monthly allowance is spent."""
    status = 429
    code = "quota_exceeded"


class AnalysisError(InternalError):
    """Raised when phrase analysis fails."""
    log_level = logging.ERROR


class TransientLLMError(AnalysisError):
    """All retries failed on a transient LLM error; `__cause__` holds the last one."""
    status = 503
    code = "service_unavailable"
    log_level = None


class PermanentLLMError(AnalysisError):
    """The LLM call failed with a non-transient error; `__cause__` holds it."""
    status = 503
    code = "service_unavailable"
    log_level = None


class MissingUsageRowError(InternalError):
    """An effective grant with no `core.user_monthly_usage` row."""
    # Never minted here: that would turn a detectable broken invariant into a silent free allowance.
    log_level = logging.ERROR

    def __init__(self, grant_id: UUID):
        self.grant_id = grant_id
        super().__init__(f"Grant {grant_id} has no core.user_monthly_usage row")


class MultipleEffectiveGrantsError(InternalError):
    """More than one effective grant for one user."""
    # A unique index makes this unreachable; asserted so dropping it fails loudly, never tie-breaks.
    log_level = logging.ERROR

    def __init__(self, count: int, user_id: UUID):
        self.count = count
        self.user_id = user_id
        super().__init__(f"{count} effective grants for user {user_id}; refusing to tie-break")


class UnknownTierError(InternalError):
    """A grant whose `tier_id` has no `core.access_tiers` row."""
    # A foreign key makes this unreachable; the silent readings are a wrong 429 or a free service.
    log_level = logging.ERROR

    def __init__(self, tier_id: str, grant_id: UUID):
        self.tier_id = tier_id
        self.grant_id = grant_id
        super().__init__(f"Grant {grant_id} references tier {tier_id!r}, which has no row")


class MissingPurchaseTokenError(InternalError):
    """A user with no `core.store_purchase_tokens` row for one or more stores."""
    # Never minted here: that would turn a detectable broken invariant into a silently repaired one.
    log_level = logging.ERROR

    def __init__(self, user_id: UUID, missing: Sequence[PurchaseProvider]):
        self.user_id = user_id
        self.missing = missing
        super().__init__(f"User {user_id} has no core.store_purchase_tokens row for "
                         f"{', '.join(store.value for store in missing)}")


class UnmappedStoreProduct(InternalError):
    """A verified store product id with no entry in the configured product map."""
    # An operator edits the map and the store's next retry succeeds; nothing is written meanwhile.
    log_level = logging.ERROR

    def __init__(self, provider: PurchaseProvider, product_id: str):
        self.provider = provider
        self.product_id = product_id
        super().__init__(f"Store product {product_id!r} of {provider.value} maps to no tier")

    def log_fields(self) -> dict[str, str | None]:
        # The store product id is a server-side catalogue value, so it is admissible; a token is not.
        return {"provider": str(self.provider), "product_id": self.product_id}


class AttributionConflict(InternalError):
    """A recorded store purchase whose attribution value differs from the one presented."""
    # Refused, never repaired: an owner this route cannot verify is a wrong entitlement waiting to happen.
    log_level = logging.ERROR

    def __init__(self, provider: PurchaseProvider, external_id: str):
        self.provider = provider
        self.external_id = external_id
        super().__init__(f"Store purchase {external_id!r} of {provider.value} presents "
                         f"another attribution value")

    def log_fields(self) -> dict[str, str | None]:
        # The lifecycle key finds the row and the provider names the store; the token is not admissible.
        return {"provider": str(self.provider), "external_id": self.external_id}


class QueueFullError(ServiceUnavailable):
    """The LLM queue is full."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM queue is full")

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}


class CircuitOpenError(ServiceUnavailable):
    """The LLM circuit breaker is open."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("LLM circuit breaker is open")

    def extra_headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_seconds)}


# --- Admission arms ---


class InvalidExternalJwt(AppError):
    """No usable bearer credential: none was presented, or the one presented did not verify."""
    status = 401
    code = "auth_required"

    def __init__(self, *, bounded_reason: BoundedReason | None) -> None:
        self.bounded_reason = bounded_reason
        super().__init__(f"invalid external jwt: {bounded_reason}")

    def extra_headers(self) -> dict[str, str]:
        # RFC 6750 §3.1: a request carrying no credential gets the bare challenge, no error code.
        if self.bounded_reason is None:
            return {"WWW-Authenticate": "Bearer"}
        return {"WWW-Authenticate": 'Bearer error="invalid_token"'}

    def log_fields(self) -> dict[str, str | None]:
        # A `StrEnum` member, stringified so the field's type in the log pipeline stays a plain str.
        return {"bounded_reason": None if self.bounded_reason is None else str(self.bounded_reason)}


class PreAuthIdentityNotAllowed(AppError):
    """A verified pair that matched no identity row, on a route that admits only linked callers."""
    status = 403
    code = "preauth_identity_not_allowed"


class IdentityUnresolvable(AppError):
    """An identity row whose `user_id` resolves to nothing, read fail-closed."""
    # Declared rather than inherited, so the walk can tell a deliberate 500 from a leaf that forgot.
    status = 500
    code = "internal_error"


class AccountUnavailable(AppError):
    """A historical identity row, or an active row whose user is not active."""

    # Declared once here: making one leaf answer differently takes an override a reviewer sees.
    status = 403
    code = "account_unavailable"


class HistoricalIdentity(AccountUnavailable):
    """The identity row's state is anything other than active."""


class BlockedUser(AccountUnavailable):
    """The identity row is active, but the user it resolves to is not."""


# --- Creation arms ---


class IdentityAlreadyLinked(AppError):
    """The pair already has an active identity backed by an active user: reconcile, do not create."""
    status = 409
    code = "identity_already_linked"


# --- Lookup arms ---


class ProviderLookupError(AppError):
    """The provider lookup's rejections share this shape; only its leaves are raised."""

    def __init__(self, *, stage: str, cause: str | None = None) -> None:
        # Plain strings, both of them ours: no provider text is ever admissible in either field.
        self.stage = stage
        self.cause = cause
        super().__init__(f"{type(self).__name__.lower()} at {stage}")

    def log_fields(self) -> dict[str, str | None]:
        fields: dict[str, str | None] = {"stage": self.stage}
        if self.cause is not None:
            fields["cause"] = self.cause
        return fields


class UserNotFound(ProviderLookupError):
    """The provider stated the account does not exist: definitive, and it spends no retry budget."""
    status = 401
    code = "auth_required"

    def extra_headers(self) -> dict[str, str]:
        # The signature verified but names no live principal, so the credential is invalid in substance.
        return {"WWW-Authenticate": 'Bearer error="invalid_token"'}


class Unavailable(ProviderLookupError):
    """The read could not be completed: an exhausted retry budget, or no app configured."""
    status = 503
    code = "verification_temporarily_unavailable"


class NotLinked(ProviderLookupError):
    """A providerData shape outside the accept set, so no provider account may be claimed for it."""
    status = 403
    code = "operation_not_allowed"


# --- Upgrade arms ---


class UpgradeRefused(AppError):
    """The upgrade's two drift rejections share this shape; only its leaves are raised."""

    # The 403 is declared here and nowhere below, so the refusal cannot become an enumeration oracle.
    status = 403
    code = "operation_not_allowed"

    def __init__(self, *, identity_row_id: UUID, stored_provider: IdentityProvider,
                 live_provider: IdentityProvider) -> None:
        self.identity_row_id = identity_row_id
        self.stored_provider = stored_provider
        self.live_provider = live_provider
        super().__init__(type(self).__name__.lower())

    def log_fields(self) -> dict[str, str | None]:
        # Enough to find the row and name the disagreement; the provider account uid is not admissible.
        return {"identity_row_id": str(self.identity_row_id),
                "stored_provider": str(self.stored_provider),
                "live_provider": str(self.live_provider)}


class ProviderTransitionNotAllowed(UpgradeRefused):
    """The stored row is registered and the live read disagrees: the two have drifted apart."""


class ProviderAccountAlreadyLinked(UpgradeRefused):
    """The target provider account is already held by another identity row."""


# --- Device-gate arms ---


class ProofRejected(ProviderLookupError):
    """Apple refused the device token, or accepted it and refused the bit write."""
    status = 403
    code = "proof_rejected"


class NotificationRejected(ProviderLookupError):
    """The store notification did not verify: the signature, the chain, the app or the environment."""
    # One class for every arm, so the answer tells a caller nothing about which check refused it.
    status = 401
    code = "auth_required"


class DeviceGrantExhausted(ProviderLookupError):
    """The device's anonymous grant bit is already set, so its one slot is spent."""
    status = 403
    code = "device_grant_exhausted"


# --- Claim arms ---


class ClaimRefused(AppError):
    """The claim's refusals share this shape, and its leaves add only their own name."""

    # The 403 is declared here and nowhere below, so the refusal cannot become an enumeration oracle.
    status = 403
    code = "operation_not_allowed"


class ClaimantNotAnonymous(ClaimRefused):
    """The stored identity row is registered, so the anonymous claim is not the route that serves it."""


class ClaimantNotRegistered(ClaimRefused):
    """The stored identity row is anonymous, so the registered claim is not the route that serves it."""


class FreeGrantAlreadyConsumed(ClaimRefused):
    """The account's one lifetime free grant is spent; revocation and expiry never reopen the slot."""


class OtherActiveGrantHeld(ClaimRefused):
    """The account already holds an active grant of another source, and one user holds at most one."""


class ActiveGrantOutsideItsTerm(ClaimRefused):
    """The account holds a row marked active whose term has passed, so the index refuses every grant."""


class ClaimRefusedUnderLock(ClaimRefused):
    """The state the preflight read changed before the locks were taken, so the write was refused."""


# --- Challenge arms ---


class ChallengeRejected(AppError):
    """The five challenge rejections share this shape; only its leaves are raised."""

    # The 409 is declared here and nowhere below, so completion cannot become an enumeration oracle.
    status = 409
    code = "challenge_required"


class ChallengeNotFound(ChallengeRejected):
    """No row carries the handle presented, compared byte for byte and never trimmed."""


class ChallengeExpired(ChallengeRejected):
    """The claim found the row still unclaimed but past its expiry -- the one expiry evaluation."""


class ChallengeConsumed(ChallengeRejected):
    """The handle was already spent, or another attempt holds the claim; there is no replay."""


class ChallengeIdentityMismatch(ChallengeRejected):
    """The row is bound to an identity that is not the caller's, linked or pre-auth."""


class ChallengeOperationMismatch(ChallengeRejected):
    """The row was issued for another operation, so this route may not spend it."""
