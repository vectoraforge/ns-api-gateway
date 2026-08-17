"""The shared auth audit contract: `audit.auth_events` rows for the audited attempt path,
and the bounded counter metric that carries barrier results everywhere else."""

import hashlib
import hmac
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID, uuid7

import structlog

from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider, match_operation
from nativespeaker.api.auth.tokens import JwtRejectionReason

logger = structlog.get_logger()


class AuthEventResult(StrEnum):
    """`core.auth_event_result`. `succeeded` is the only success code."""
    succeeded = "succeeded"
    challenge_expired = "challenge_expired"
    challenge_consumed = "challenge_consumed"
    challenge_identity_mismatch = "challenge_identity_mismatch"
    challenge_operation_mismatch = "challenge_operation_mismatch"
    challenge_not_found = "challenge_not_found"
    invalid_external_jwt = "invalid_external_jwt"
    preauth_identity_not_allowed = "preauth_identity_not_allowed"
    identity_already_linked = "identity_already_linked"
    provider_not_linked = "provider_not_linked"
    provider_transition_not_allowed = "provider_transition_not_allowed"
    provider_account_already_linked = "provider_account_already_linked"
    blocked_user = "blocked_user"
    historical_identity = "historical_identity"
    invalid_restore_proof = "invalid_restore_proof"
    proof_malformed = "proof_malformed"
    store_transaction_already_linked = "store_transaction_already_linked"
    restore_subscription_unlinked = "restore_subscription_unlinked"
    restore_subscription_not_entitled = "restore_subscription_not_entitled"
    restore_purchase_uuid_unknown = "restore_purchase_uuid_unknown"
    restore_purchase_uuid_mismatch = "restore_purchase_uuid_mismatch"
    restore_subscription_grant_owner_mismatch = "restore_subscription_grant_owner_mismatch"
    restore_branch_inconsistent = "restore_branch_inconsistent"
    restore_store_state_unverified = "restore_store_state_unverified"
    restore_source_user_inactive = "restore_source_user_inactive"
    restore_destination_anonymous = "restore_destination_anonymous"
    restore_destination_already_entitled = "restore_destination_already_entitled"
    anti_abuse_already_claimed = "anti_abuse_already_claimed"
    native_claim_already_claimed = "native_claim_already_claimed"
    native_claim_unavailable = "native_claim_unavailable"
    native_claim_write_failed = "native_claim_write_failed"
    devicecheck_read_budget_exhausted = "devicecheck_read_budget_exhausted"
    devicecheck_write_budget_exhausted = "devicecheck_write_budget_exhausted"
    device_recall_read_budget_exhausted = "device_recall_read_budget_exhausted"
    device_recall_write_budget_exhausted = "device_recall_write_budget_exhausted"
    firebase_user_unresolved = "firebase_user_unresolved"
    idp_account_not_eligible = "idp_account_not_eligible"
    firebase_lookup_unavailable = "firebase_lookup_unavailable"
    verification_temporarily_unavailable = "verification_temporarily_unavailable"
    idp_account_already_claimed = "idp_account_already_claimed"
    registered_grant_destination_incompatible = "registered_grant_destination_incompatible"
    policy_rejected = "policy_rejected"
    revocation_unconfirmed = "revocation_unconfirmed"
    internal_error = "internal_error"


# The four results the shared pre-handler barrier can produce.
BARRIER_RESULTS: frozenset[AuthEventResult] = frozenset({
    AuthEventResult.invalid_external_jwt,
    AuthEventResult.preauth_identity_not_allowed,
    AuthEventResult.historical_identity,
    AuthEventResult.blocked_user,
})


class ResultEnumError(RuntimeError):
    """`core.auth_event_result` drifted from the operations that write it."""


_ALL_OPERATIONS: frozenset[AuthOperation] = frozenset(AuthOperation)
# The challenge-bearing subset, the two account-creating operations, the two free-credit claims,
# and restore. Each group is the set of operations whose own rules require the results below.
_CHALLENGE_BEARING: frozenset[AuthOperation] = frozenset({
    AuthOperation.create_user, AuthOperation.upgrade_anonymous_to_registered,
    AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant,
})
_ACCOUNT_CREATION: frozenset[AuthOperation] = frozenset({
    AuthOperation.create_user, AuthOperation.upgrade_anonymous_to_registered,
})
_CLAIMS: frozenset[AuthOperation] = frozenset({
    AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant,
})
_ANONYMOUS_CLAIM: frozenset[AuthOperation] = frozenset({AuthOperation.claim_anonymous_grant})
_REGISTERED_CLAIM: frozenset[AuthOperation] = frozenset({AuthOperation.claim_registered_grant})
_RESTORE: frozenset[AuthOperation] = frozenset({AuthOperation.restore_subscription})

# The operations each `core.auth_event_result` value is required by. The enum is closed and
# exact in both directions: every value some operation is required to write is a member, and
# every member is required by at least one operation, so a value no operation writes cannot
# survive here and an operation cannot write a value the enum does not carry.
# [impl->req~schema-auth-events-result-enum-closed-and-exact~1]
RESULT_PRODUCERS: dict[AuthEventResult, frozenset[AuthOperation]] = {
    # Ordinary success, and the four barrier rejections, bind all seven inventory operations.
    AuthEventResult.succeeded: _ALL_OPERATIONS,
    AuthEventResult.invalid_external_jwt: _ALL_OPERATIONS,
    AuthEventResult.preauth_identity_not_allowed: _ALL_OPERATIONS,
    AuthEventResult.historical_identity: _ALL_OPERATIONS,
    AuthEventResult.blocked_user: _ALL_OPERATIONS,
    # The five challenge rejections belong to the challenge-bearing subset alone.
    AuthEventResult.challenge_expired: _CHALLENGE_BEARING,
    AuthEventResult.challenge_consumed: _CHALLENGE_BEARING,
    AuthEventResult.challenge_identity_mismatch: _CHALLENGE_BEARING,
    AuthEventResult.challenge_operation_mismatch: _CHALLENGE_BEARING,
    AuthEventResult.challenge_not_found: _CHALLENGE_BEARING,
    # Identity binding and provider classification.
    AuthEventResult.identity_already_linked: frozenset({AuthOperation.create_user}),
    AuthEventResult.provider_not_linked: _ACCOUNT_CREATION,
    AuthEventResult.provider_transition_not_allowed: frozenset(
        {AuthOperation.upgrade_anonymous_to_registered}),
    AuthEventResult.provider_account_already_linked: _ACCOUNT_CREATION,
    AuthEventResult.firebase_user_unresolved: _ACCOUNT_CREATION | _CLAIMS,
    AuthEventResult.firebase_lookup_unavailable: _ACCOUNT_CREATION | _CLAIMS,
    AuthEventResult.verification_temporarily_unavailable: _ACCOUNT_CREATION | _CLAIMS,
    AuthEventResult.policy_rejected: _ACCOUNT_CREATION | _CLAIMS,
    # Restore proof, branch and live store-state outcomes.
    AuthEventResult.invalid_restore_proof: _RESTORE,
    AuthEventResult.store_transaction_already_linked: _RESTORE,
    AuthEventResult.restore_subscription_unlinked: _RESTORE,
    AuthEventResult.restore_subscription_not_entitled: _RESTORE,
    AuthEventResult.restore_purchase_uuid_unknown: _RESTORE,
    AuthEventResult.restore_purchase_uuid_mismatch: _RESTORE,
    AuthEventResult.restore_subscription_grant_owner_mismatch: _RESTORE,
    AuthEventResult.restore_branch_inconsistent: _RESTORE,
    AuthEventResult.restore_store_state_unverified: _RESTORE,
    AuthEventResult.restore_source_user_inactive: _RESTORE,
    AuthEventResult.restore_destination_anonymous: _RESTORE,
    AuthEventResult.restore_destination_already_entitled: _RESTORE,
    AuthEventResult.internal_error: _RESTORE,
    # Free-credit anti-abuse: the device gates belong to the anonymous claim, the provider
    # account gate to the registered claim.
    AuthEventResult.proof_malformed: _CLAIMS,
    AuthEventResult.anti_abuse_already_claimed: _ANONYMOUS_CLAIM,
    AuthEventResult.native_claim_already_claimed: _ANONYMOUS_CLAIM,
    AuthEventResult.native_claim_unavailable: _ANONYMOUS_CLAIM,
    AuthEventResult.native_claim_write_failed: _ANONYMOUS_CLAIM,
    AuthEventResult.devicecheck_read_budget_exhausted: _ANONYMOUS_CLAIM,
    AuthEventResult.devicecheck_write_budget_exhausted: _ANONYMOUS_CLAIM,
    AuthEventResult.device_recall_read_budget_exhausted: _ANONYMOUS_CLAIM,
    AuthEventResult.device_recall_write_budget_exhausted: _ANONYMOUS_CLAIM,
    AuthEventResult.idp_account_not_eligible: _REGISTERED_CLAIM,
    AuthEventResult.idp_account_already_claimed: _REGISTERED_CLAIM,
    AuthEventResult.registered_grant_destination_incompatible: _REGISTERED_CLAIM,
    # Sign-out everywhere.
    AuthEventResult.revocation_unconfirmed: frozenset({AuthOperation.sign_out_all}),
}


def _assert_result_enum_closed_and_exact() -> None:
    """`result` stays NOT NULL and machine-readable: every member is required by at least one
    operation, no member is a free-text or nullable fallback, and no generic `internal_error`
    stands in for a value an operation is required to write."""
    # [impl->req~schema-auth-events-result-enum-closed-and-exact~1]
    missing = set(AuthEventResult) - set(RESULT_PRODUCERS)
    if missing:
        raise ResultEnumError(f"no operation is required to write {sorted(missing)}")
    unknown = set(RESULT_PRODUCERS) - set(AuthEventResult)
    if unknown:
        raise ResultEnumError(f"{sorted(unknown)} is written but is no enum member")
    for result, producers in RESULT_PRODUCERS.items():
        if not producers:
            raise ResultEnumError(f"{result} is required by no operation")
        if not producers <= _ALL_OPERATIONS:
            raise ResultEnumError(f"{result} names an operation outside the inventory")


_assert_result_enum_closed_and_exact()


def required_by(operation: AuthOperation) -> frozenset[AuthEventResult]:
    """Every result this operation may be required to write."""
    # [impl->req~schema-auth-events-result-enum-closed-and-exact~1]
    return frozenset(result for result, producers in RESULT_PRODUCERS.items()
                     if operation in producers)


@dataclass(frozen=True, slots=True)
class AuthActor:
    """Actor columns. Populated only when a backend-verified token or resolved identity
    supplied that actor; nothing decoded from an unverified token may fill them."""
    # Actor subject material is stored only as its derived HMAC hash under the
    # derived-identifier rules, together with the key version used. There is no field for a
    # raw `subject` here, so no insertion path can carry one to the row.
    # [impl->req~shared-auth-events-actor-subject-hash~1]
    # [impl->req~schema-auth-events-actor-fields-derivation~1]
    issuer: str | None = None
    subject_hash: bytes | None = None
    subject_hash_key_version: int | None = None
    provider: IdentityProvider | None = None


NO_ACTOR = AuthActor()

# The keyed subject hasher every actor-populating event producer shares: the derived HMAC hash
# of the backend-verified subject together with the version of the key that produced it.
# [impl->req~shared-auth-events-actor-subject-hash~1]
SubjectHasher = Callable[[str], tuple[bytes, int]]


class KeyedSubjectHasher:
    """HMAC-SHA-256 over the backend-verified subject under a versioned server-side key. The raw
    subject is never stored, and every hash carries the version of the key that produced it so a
    key rotation stays reconstructible."""

    # `actor_subject_hash` is HMAC-SHA-256 of the backend-verified actor subject, and
    # `actor_subject_hash_key_version` the version of the key that produced it.
    # [impl->req~shared-auth-events-actor-subject-hash~1]
    # [impl->req~schema-auth-events-actor-fields-derivation~1]
    def __init__(self, *, key: bytes, key_version: int = 1):
        if not key:
            raise ValueError("the subject hash key must not be empty")
        self._key = key
        self._key_version = key_version

    def __call__(self, subject: str) -> tuple[bytes, int]:
        digest = hmac.new(self._key, subject.encode("utf-8"), hashlib.sha256).digest()
        return digest, self._key_version


def resolved_actor(issuer: str,
                   subject_hash: bytes,
                   subject_hash_key_version: int,
                   *,
                   stored_provider: IdentityProvider | None = None) -> AuthActor:
    """The actor for a backend-verified request. `stored_provider` is the value read from the
    `core.external_identities.provider` column of the resolved linked row and is `None` for a
    pre-auth or unlinked event: nothing here may come from token claims, request headers or
    client input, and no provider value is ever fabricated."""
    # `actor_issuer` and `actor_subject_hash` derive only from the backend-verified token's
    # `iss` and `sub`, or from the resolved external-identity row: this constructor takes no
    # header, cookie, client field or unverified claim.
    # [impl->req~shared-auth-events-actor-provider~1]
    # [impl->req~shared-auth-events-provider-source~1]
    # [impl->req~schema-auth-events-actor-fields-derivation~1]
    # [impl->req~schema-auth-events-actor-provider-population~1]
    return AuthActor(issuer=issuer,
                     subject_hash=subject_hash,
                     subject_hash_key_version=subject_hash_key_version,
                     provider=stored_provider)


@dataclass(frozen=True, slots=True)
class AuthEvent:
    result: AuthEventResult
    operation: AuthOperation | None = None
    actor: AuthActor = NO_ACTOR
    challenge_row_id: UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)


class AttemptPhase(StrEnum):
    """Where the attempt reached its terminal outcome. Every phase writes the one row."""
    barrier = "barrier"
    prepare = "prepare"
    business = "business"
    later = "later"
    success = "success"


class InvalidTerminalOutcomeError(ValueError):
    """The result does not belong to the phase that produced it."""


def terminal_event(phase: AttemptPhase,
                   result: AuthEventResult,
                   *,
                   operation: AuthOperation | None = None,
                   actor: AuthActor = NO_ACTOR,
                   challenge_row_id: UUID | None = None,
                   details: dict[str, Any] | None = None) -> AuthEvent:
    """Build the single row an on-path attempt owes for its terminal outcome, whatever that
    outcome is."""
    details = dict(details or {})
    match phase:
        case AttemptPhase.barrier:
            # A barrier rejection. `invalid_external_jwt` supplied no permitted actor, so the
            # row takes the actor-`NULL` shape whatever the caller passed.
            # [impl->req~shared-audit-outcome-barrier-rejection~1]
            if result not in BARRIER_RESULTS:
                raise InvalidTerminalOutcomeError(f"{result} is not a barrier result")
            if result is AuthEventResult.invalid_external_jwt:
                actor = NO_ACTOR
        case AttemptPhase.prepare:
            # A prepare-phase rejection, such as `identity_already_linked` at create_user prepare.
            # [impl->req~shared-audit-outcome-prepare-rejection~1]
            _reject_success(phase, result)
        case AttemptPhase.business:
            # An ordinary business-validation, proof, or live-state rejection.
            # [impl->req~shared-audit-outcome-business-rejection~1]
            _reject_success(phase, result)
            if result in BARRIER_RESULTS:
                raise InvalidTerminalOutcomeError(f"{result} is a barrier result")
        case AttemptPhase.later:
            # A later operation failure, such as `revocation_unconfirmed`.
            # [impl->req~shared-audit-outcome-later-failure~1]
            _reject_success(phase, result)
        case AttemptPhase.success:
            # `succeeded` is the only success code.
            # [impl->req~shared-audit-outcome-succeeded~1]
            if result is not AuthEventResult.succeeded:
                raise InvalidTerminalOutcomeError(f"{result} is not a success")
    return AuthEvent(result=result, operation=operation, actor=actor,
                     challenge_row_id=challenge_row_id, details=details)


def _reject_success(phase: AttemptPhase, result: AuthEventResult) -> None:
    if result is AuthEventResult.succeeded:
        raise InvalidTerminalOutcomeError(f"{phase} cannot produce {result}")


# --- The `audit.auth_events` row -----------------------------------------------------------

DETAILS_SCHEMA_VERSION = 1

# The structured `details` sections. `context` holds non-secret request and routing context,
# `verification` non-secret verification metadata, `resolved` resolved internal ids and
# redacted server-derived identifiers, `mutation` the committed state change including partial
# state on fail-closed paths, and `failure` the rejection stage and reason context. Which
# specific fields appear inside each subobject is the implementer's choice per operation,
# bounded only by the redaction and reconstruction rules below.
# [impl->req~schema-auth-events-details-shape~1]
# [impl->req~schema-auth-events-implementer-chooses-fields~1]
DETAIL_SECTIONS: tuple[str, ...] = ("context", "verification", "resolved", "mutation", "failure")

# HMAC-SHA-256, per the derived-identifier rules.
SUBJECT_HASH_BYTES = 32

REDACTED = "[redacted]"

# Detail keys that would carry secret material or the public challenge capability handle.
# Anything whose name contains one of these fragments is redacted before the row is written.
# [impl->req~shared-auth-events-details-redaction~1]
# [impl->req~schema-auth-events-details-non-secret-only~1]
# [impl->req~schema-auth-events-challenge-row-id-non-secret~1]
SECRET_DETAIL_FRAGMENTS: frozenset[str] = frozenset({
    "subject", "authorization", "bearer", "jwt", "id_token", "token", "secret",
    "password", "private_key", "restore_proof", "proof_payload", "receipt",
    "signed_transaction", "signed_payload", "signed_renewal", "attestation", "assertion",
    "device_id", "device_identifier", "identifier_for_vendor", "challenge_id", "nonce",
    "credential", "api_key",
})

# Short names too ambiguous to match as a fragment: `sub` is the raw token subject, while
# `subscription_id` is an ordinary non-secret resolved identifier.
SECRET_DETAIL_KEYS: frozenset[str] = frozenset({"sub", "iss_sub", "raw_subject", "handle"})

# Detail keys that are explicitly non-secret server-derived identifiers even though their name
# contains a redacted fragment.
_ALLOWED_DETAIL_KEYS: frozenset[str] = frozenset({
    "subject_hash", "subject_hash_key_version", "challenge_row_id", "proof_fingerprints",
    "token_reason",
})


class AuditRowError(RuntimeError):
    """A row was about to be written that the shared audit contract forbids."""


def _looks_like_a_token(value: str) -> bool:
    """Three base64url segments separated by dots: a JWT or a signed provider payload."""
    parts = value.split(".")
    return len(parts) == 3 and all(part and part.replace("-", "").replace("_", "").isalnum()
                                   for part in parts)


def redact(value: Any) -> Any:
    """Redact before write: `audit.auth_events` is not a proof archive, so raw JWTs, raw
    restore proofs, purchase tokens, signed transaction payloads, attestation blobs, raw
    attestation private keys, raw device identifiers, the public `challenge_id` handle, and
    every other secret carrier are replaced rather than stored."""
    # [impl->req~shared-auth-events-details-redaction~1]
    # [impl->req~schema-auth-events-details-non-secret-only~1]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if name not in _ALLOWED_DETAIL_KEYS and (
                    name.lower() in SECRET_DETAIL_KEYS
                    or any(fragment in name.lower()
                           for fragment in SECRET_DETAIL_FRAGMENTS)):
                redacted[name] = REDACTED
            else:
                redacted[name] = redact(item)
        return redacted
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    if isinstance(value, bytes):
        return REDACTED
    if isinstance(value, str) and _looks_like_a_token(value):
        return REDACTED
    return value


def structured_details(details: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize an event's `details` into the structured, redacted shape the row stores."""
    sections: dict[str, dict[str, Any]] = {name: {} for name in DETAIL_SECTIONS}
    for key, value in details.items():
        if key in DETAIL_SECTIONS and isinstance(value, Mapping):
            sections[key].update(value)
        elif key == "reason":
            sections["failure"]["reason"] = value
        else:
            sections["context"][key] = value
    # The stored object always carries the whole top-level shape the schema's CHECK constraints
    # require: `{schema_version, context, verification, resolved, mutation, failure}`.
    # [impl->req~shared-auth-events-details-redaction~1]
    # [impl->req~schema-auth-events-details-shape~1]
    body: dict[str, Any] = {"schema_version": DETAILS_SCHEMA_VERSION}
    body.update({name: redact(section) for name, section in sections.items()})
    return body


# Movement context these two operations fold into `details`. For these two operations the one
# row is the durable record and the query surface for support, fraud review and historical
# account-movement analysis, so the context is carried as non-secret data on the row itself.
# [impl->req~shared-auth-events-movement-details~1]
# [impl->req~schema-auth-events-movement-context-details~1]
# [impl->req~schema-invariant-12~1]
MOVEMENT_OPERATIONS: frozenset[AuthOperation] = frozenset({
    AuthOperation.restore_subscription,
    AuthOperation.upgrade_anonymous_to_registered,
})

MOVEMENT_DETAIL_KEYS: tuple[str, ...] = (
    "source_user_id", "source_external_identity_id",
    "destination_user_id", "destination_external_identity_id",
    "subscription_id", "access_grant_id", "store_purchase_id",
    "movement_classification", "proof_fingerprints", "store_state_verification",
)


def movement_details(*,
                     movement_classification: str,
                     source_user_id: Any = None,
                     source_external_identity_id: Any = None,
                     destination_user_id: Any = None,
                     destination_external_identity_id: Any = None,
                     subscription_id: Any = None,
                     access_grant_id: Any = None,
                     store_purchase_id: Any = None,
                     proof_fingerprints: Any = None,
                     store_state_verification: Any = None) -> dict[str, Any]:
    """The movement context `restore_subscription` and `upgrade_anonymous_to_registered` fold
    into `details`: source and destination users and identities where known, the touched
    subscription, access grant and store-purchase rows where applicable, the movement
    classification, non-secret proof fingerprints, and the live store-state verification
    outcome for a cross-account restore."""
    # [impl->req~shared-auth-events-movement-details~1]
    # [impl->req~schema-auth-events-movement-context-details~1]
    return {"resolved": {"source_user_id": source_user_id,
                         "source_external_identity_id": source_external_identity_id,
                         "destination_user_id": destination_user_id,
                         "destination_external_identity_id": destination_external_identity_id},
            "mutation": {"subscription_id": subscription_id,
                         "access_grant_id": access_grant_id,
                         "store_purchase_id": store_purchase_id,
                         "movement_classification": movement_classification},
            "verification": {"proof_fingerprints": proof_fingerprints,
                             "store_state_verification": store_state_verification}}


def auth_event_row(event: AuthEvent,
                   *,
                   created_at: datetime,
                   row_id: UUID | None = None) -> dict[str, Any]:
    """Build the one `audit.auth_events` row an attempt owes, redacted and validated. This is
    the single insertion path: everything the contract forbids fails here rather than reaching
    the table."""
    details = structured_details(event.details)
    # The record says which verification and identity metadata were available, and says
    # explicitly that no verified actor existed where none did.
    # [impl->req~shared-auth-events-record-sufficiency~1]
    # [impl->req~shared-auth-events-actor-fields-null~1]
    details["verification"].setdefault(
        "actor", "verified" if event.actor.issuer is not None else "none")
    if event.result is not AuthEventResult.succeeded:
        # Why the request was rejected, in the same machine-readable vocabulary as `result`.
        details["failure"].setdefault("result", str(event.result))
    if event.actor.provider is not None:
        # A recorded current identity provider is the stored column's value and no other.
        # [impl->req~shared-auth-events-provider-source~1]
        # [impl->req~schema-auth-events-detail-provider-from-stored-column~1]
        details["resolved"]["provider"] = str(event.actor.provider)
    elif "provider" in details["resolved"]:
        raise AuditRowError("a recorded provider comes from the stored provider column")
    row: dict[str, Any] = {
        "id": row_id or uuid7(),
        # The non-secret internal `core.auth_challenges.id`, never the public handle.
        # [impl->req~schema-auth-events-challenge-row-id-non-secret~1]
        "challenge_row_id": event.challenge_row_id,
        # `operation` is the attempted endpoint operation when known, and stays `NULL` when the
        # rejection happened before the operation was determined.
        # [impl->req~shared-auth-events-operation-column~1]
        # [impl->req~schema-auth-events-operation-nullable~1]
        "operation": event.operation,
        # `result` is the single machine-readable outcome code; there is no `failure_reason`
        # column, and `succeeded` is the only success code.
        # [impl->req~shared-audit-result-code~1]
        # [impl->req~shared-auth-events-result-column~1]
        # [impl->req~schema-auth-events-result-single-outcome-code~1]
        "result": event.result,
        "actor_issuer": event.actor.issuer,
        "actor_subject_hash": event.actor.subject_hash,
        "actor_subject_hash_key_version": event.actor.subject_hash_key_version,
        "actor_provider": event.actor.provider,
        "details": details,
        # The trail is chronological, so every row carries the time it happened.
        # [impl->req~shared-auth-events-scope~1]
        "created_at": created_at,
    }
    _assert_result_column(row)
    _assert_actor_columns(row)
    _assert_movement_details(row)
    _assert_record_sufficient(row)
    _assert_invalid_external_jwt_detail(row)
    return row


def _assert_result_column(row: dict[str, Any]) -> None:
    # [impl->req~shared-audit-result-code~1]
    # [impl->req~shared-auth-events-result-column~1]
    # [impl->req~schema-auth-events-result-single-outcome-code~1]
    if not isinstance(row["result"], AuthEventResult):
        raise AuditRowError("result must be a stable machine-readable outcome code")
    if "failure_reason" in row:
        raise AuditRowError("there is no separate failure_reason column")
    if row["result"] is AuthEventResult.succeeded and row["operation"] is None:
        raise AuditRowError("a success names the operation it completed")


def _assert_actor_columns(row: dict[str, Any]) -> None:
    """`invalid_external_jwt` supplied no permitted actor identity, so all three actor identity
    fields are `NULL`; for every other result all three are populated from the backend-verified
    token or the resolved identity. `actor_provider` is populated only where a resolved linked
    row supplied a stored provider."""
    # [impl->req~shared-auth-events-actor-fields-null~1]
    # [impl->req~shared-auth-events-actor-subject-hash~1]
    # [impl->req~shared-auth-events-actor-provider~1]
    # [impl->req~schema-auth-events-actor-fields-derivation~1]
    # [impl->req~schema-auth-events-actor-provider-population~1]
    identity_fields = (row["actor_issuer"], row["actor_subject_hash"],
                       row["actor_subject_hash_key_version"])
    if row["result"] is AuthEventResult.invalid_external_jwt:
        if any(field is not None for field in identity_fields):
            raise AuditRowError("invalid_external_jwt supplies no permitted actor identity")
        if row["actor_provider"] is not None:
            raise AuditRowError("invalid_external_jwt fabricates no provider")
        return
    if any(field is None for field in identity_fields):
        raise AuditRowError(f"{row['result']} carries a verified actor")
    subject_hash = row["actor_subject_hash"]
    if not isinstance(subject_hash, bytes) or len(subject_hash) != SUBJECT_HASH_BYTES:
        raise AuditRowError("actor subject material is stored only as its derived HMAC hash")
    provider = row["actor_provider"]
    # An authorization-relevant categorical field is schema-typed, never free text.
    # [impl->req~shared-invariant-02~2]
    # [impl->req~schema-invariant-03~1]
    # [impl->req~schema-auth-events-actor-provider-population~1]
    if provider is not None and not isinstance(provider, IdentityProvider):
        raise AuditRowError("actor_provider comes from the stored provider column")


def _assert_movement_details(row: dict[str, Any]) -> None:
    """The two account-movement operations fold their movement context into `details`."""
    # [impl->req~shared-auth-events-movement-details~1]
    # [impl->req~schema-auth-events-movement-context-details~1]
    if row["operation"] not in MOVEMENT_OPERATIONS:
        return
    if row["result"] is AuthEventResult.invalid_external_jwt:
        # Nothing was resolved, so there is no movement to describe.
        return
    present = {key for section in DETAIL_SECTIONS
               for key in row["details"][section]}
    missing = [key for key in MOVEMENT_DETAIL_KEYS if key not in present]
    if missing:
        raise AuditRowError(f"{row['operation']} owes movement details {missing}")


def _assert_record_sufficient(row: dict[str, Any]) -> None:
    """Each record must be enough to reconstruct the verified actor when one exists, or that
    none was available for `invalid_external_jwt`; which non-secret challenge row was involved;
    which operation was attempted; which non-secret verification and identity metadata were
    available; what state changed, partial state included; and why a rejection happened. The
    public `challenge_id` capability handle appears nowhere in the row."""
    # [impl->req~shared-auth-events-record-sufficiency~1]
    # [impl->req~schema-auth-events-record-reconstruction-sufficiency~1]
    # [impl->req~schema-auth-events-details-shape~1]
    details = row["details"]
    if details.get("schema_version") != DETAILS_SCHEMA_VERSION:
        raise AuditRowError("details carries its schema version")
    for section in DETAIL_SECTIONS:
        if not isinstance(details.get(section), dict):
            raise AuditRowError(f"details.{section} must be an object")
    if row["result"] is not AuthEventResult.succeeded and not details["failure"]:
        raise AuditRowError(f"{row['result']} must record why the request was rejected")
    if row["result"] is AuthEventResult.succeeded and details["failure"]:
        raise AuditRowError("a successful event leaves failure empty")
    # `challenge_row_id` is the non-secret internal `core.auth_challenges.id`. The public
    # capability handle is a string, so anything but a UUID is refused outright, and the same
    # handle may not be duplicated into `details` either — `challenge_id` is a redacted key.
    # [impl->req~schema-auth-events-challenge-row-id-non-secret~1]
    if row["challenge_row_id"] is not None and not isinstance(row["challenge_row_id"], UUID):
        raise AuditRowError("challenge_row_id is the internal row id, never the public handle")
    for section in DETAIL_SECTIONS:
        if any(str(key).lower() in {"challenge_id", "challenge_handle"}
               and details[section][key] != REDACTED
               for key in details[section]):
            raise AuditRowError("details never duplicates the public challenge handle")


# The bounded, machine-readable branches an external-JWT acceptance failure may record. The
# vocabulary is the verifier's own: a missing, malformed, badly signed, expired, wrong-audience
# or wrong-issuer token, and the key-fetch outage that is none of those.
# [impl->req~schema-auth-events-invalid-external-jwt-detail~1]
INVALID_EXTERNAL_JWT_REASONS: frozenset[str] = frozenset(
    str(reason) for reason in JwtRejectionReason)


def _assert_invalid_external_jwt_detail(row: dict[str, Any]) -> None:
    """An `invalid_external_jwt` row is first-class and queryable here: the result names the
    rejection and `details.failure` names the failed acceptance branch from a bounded
    vocabulary. The same detail never reaches the client, which sees only the shared class."""
    # [impl->req~schema-auth-events-invalid-external-jwt-detail~1]
    if row["result"] is not AuthEventResult.invalid_external_jwt:
        return
    reason = row["details"]["failure"].get("reason")
    if reason not in INVALID_EXTERNAL_JWT_REASONS:
        raise AuditRowError(
            f"invalid_external_jwt records a bounded acceptance-failure reason, not {reason!r}")


# --- The rows two challenge-free operations owe -----------------------------------------------

class RevocationErrorCategory(StrEnum):
    """The sanitized categories a `revocation_unconfirmed` row may record. Bounded and
    low-cardinality by construction: no raw Firebase message, credential, token, stack trace,
    high-cardinality exception text or vendor response payload can be expressed here."""
    definitive_failure = "definitive_failure"
    dependency_unavailable = "dependency_unavailable"
    ambiguous_outcome = "ambiguous_outcome"


# A second outcome field beside `result` would split the outcome across two places.
_SECOND_OUTCOME_FIELDS: frozenset[str] = frozenset({
    "outcome", "revoked", "revocation_result", "revocation_status", "status", "succeeded",
})

# The whole of `details.failure` on a `revocation_unconfirmed` row. The set is an allowlist, not
# a denylist, so raw Firebase messages, credentials, tokens, stack traces, high-cardinality
# exception text and vendor response payloads are not expressible here whatever they are named.
# [impl->req~schema-auth-events-sign-out-all-row~1]
REVOCATION_FAILURE_FIELDS: frozenset[str] = frozenset({"error_category", "result"})


def sign_out_all_event(*,
                       actor: AuthActor,
                       request_id: str,
                       revoked: bool,
                       error_category: RevocationErrorCategory | None = None,
                       details: dict[str, Any] | None = None) -> AuthEvent:
    """The single row a `POST /auth/sign-out-all` attempt appends once it reached the authorized
    revocation phase. `result` alone carries the outcome: `succeeded` when Firebase Admin
    refresh-token revocation completed for the account's Firebase uid — ordinary operation
    success, no second success code — or `revocation_unconfirmed` for a definitive Firebase
    failure, a local dependency that prevented the call, or a timeout, lost response or
    disconnect that left the outcome ambiguous."""
    # [impl->req~schema-auth-events-sign-out-all-row~1]
    body = dict(details or {})
    context = dict(body.pop("context", {}))
    failure = dict(body.pop("failure", {}))
    if not request_id:
        raise InvalidTerminalOutcomeError("the row records the request id in details.context")
    context["request_id"] = request_id
    if revoked:
        if error_category is not None:
            raise InvalidTerminalOutcomeError("a completed revocation records no error category")
        phase, result = AttemptPhase.success, AuthEventResult.succeeded
    else:
        if error_category is None:
            raise InvalidTerminalOutcomeError(
                "revocation_unconfirmed records a sanitized error category")
        failure["error_category"] = str(error_category)
        phase, result = AttemptPhase.later, AuthEventResult.revocation_unconfirmed
    offending = sorted(_SECOND_OUTCOME_FIELDS & {str(key) for key in failure})
    if offending:
        raise InvalidTerminalOutcomeError(f"{offending} would be a second outcome field")
    # Raw Firebase messages, credentials, tokens, stack traces, high-cardinality exception text
    # and vendor response payloads are never stored, so the caller's failure keys are checked
    # against the bounded set rather than merged through.
    unbounded = sorted({str(key) for key in failure} - REVOCATION_FAILURE_FIELDS)
    if unbounded:
        raise InvalidTerminalOutcomeError(
            f"{unbounded} are not among the bounded revocation failure fields")
    body.update({"context": context, "failure": failure})
    # The operation mutates no business-state table, so the row carries no mutation.
    body["mutation"] = {}
    return terminal_event(phase, result, operation=AuthOperation.sign_out_all,
                          actor=actor, details=body)


def sync_event(result: AuthEventResult,
               *,
               actor: AuthActor = NO_ACTOR,
               details: dict[str, Any] | None = None) -> AuthEvent:
    """The single row a `POST /auth/sync` attempt appends: `succeeded`, or the barrier's own
    result where the barrier rejected it. The operation is challenge-free and read-only, so the
    row records no mutation and carries no `challenge_row_id`; it exists as the attempt record
    the audited attempt path requires, not as evidence of a state change."""
    # [impl->req~schema-auth-events-sync-row~1]
    if result is not AuthEventResult.succeeded and result not in BARRIER_RESULTS:
        raise InvalidTerminalOutcomeError(f"/auth/sync has no terminal outcome {result}")
    body = dict(details or {})
    if body.get("mutation"):
        raise InvalidTerminalOutcomeError("/auth/sync records no mutation")
    body["mutation"] = {}
    phase = (AttemptPhase.success if result is AuthEventResult.succeeded
             else AttemptPhase.barrier)
    event = terminal_event(phase, result, operation=AuthOperation.sync,
                           actor=actor, details=body)
    if event.challenge_row_id is not None:
        raise InvalidTerminalOutcomeError("/auth/sync is challenge-free")
    return event


class AuthEventSink(Protocol):
    async def insert(self, session: Any, row: Mapping[str, Any]) -> None:
        """Append one durable `audit.auth_events` row using the given session. The row arrives
        already built, redacted and validated by `auth_event_row`, so a sink has nothing left to
        decide and no way to write an event's raw `details`."""
        ...


class AuditAlreadyWrittenError(RuntimeError):
    """A second `audit.auth_events` row was attempted for one attempt."""


class OffPathAuditError(RuntimeError):
    """An `audit.auth_events` row was attempted for a request off the audited attempt path."""


class AuthAttempt:
    """One request, classified against the operation inventory from its matched route and
    method. Classification happens on route metadata, so it is available before the shared
    pre-handler barrier runs and does not depend on how far the handler got."""

    # [impl->req~shared-audited-path-entry~1]
    def __init__(self, method: str, path: str, *, route_template: str | None = None):
        self.method = method.upper()
        self.path = path
        self.route = route_template or path
        self.operation = match_operation(self.method, path)
        self.on_audited_path = self.operation is not None
        self.audited = False


class AuthResultCounter:
    """The bounded-cardinality counter metric labeled by result, bounded reason and route.
    It is mandatory wherever the barrier rejects, on and off the audited path alike."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str, str], int] = {}

    def increment(self, *, result: AuthEventResult, route: str, reason: str | None = None) -> None:
        key = (str(result), reason or "none", route)
        self._counts[key] = self._counts.get(key, 0) + 1

    def value(self, *, result: AuthEventResult, route: str, reason: str | None = None) -> int:
        return self._counts.get((str(result), reason or "none", route), 0)

    def labels(self) -> list[tuple[str, str, str]]:
        return sorted(self._counts)


class AuthAuditWriter:
    """Writes the single durable audit row an on-path attempt owes, and keeps every barrier
    result first-class off the path through the security log and the counter metric."""

    def __init__(self,
                 *,
                 sink: AuthEventSink,
                 counter: AuthResultCounter,
                 session_factory: Callable[[], AbstractAsyncContextManager[Any]] | None = None,
                 clock: Callable[[], datetime] | None = None):
        self._sink = sink
        self._counter = counter
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def row_for(self, event: AuthEvent) -> dict[str, Any]:
        """Build the durable row this event becomes. Every write goes through `auth_event_row`,
        so redaction and the whole row contract are enforced on the write path itself rather
        than in a builder a sink might not call."""
        # [impl->req~shared-auth-events-details-redaction~1]
        return auth_event_row(event, created_at=self._clock())

    def _claim(self, attempt: AuthAttempt) -> None:
        """Only requests routed to a canonical state-changing auth operation reach the table.
        A rejection anywhere else is not an `audit.auth_events` row and cannot become one."""
        # One row for every request routed to a canonical state-changing auth operation, and
        # no row for a rejection on any other authenticated route. A movement attempt that
        # reaches the audited path is likewise represented by this single row: there is no
        # second durable attempt record anywhere.
        # [impl->req~shared-path-single-audit-row~1]
        # [impl->req~shared-off-path-no-audit-row~1]
        # [impl->req~shared-auth-events-scope~1]
        # [impl->req~shared-rejection-audit-scope~1]
        # [impl->req~schema-auth-events-purpose~1]
        # [impl->req~schema-invariant-12~1]
        if not attempt.on_audited_path:
            raise OffPathAuditError(f"{attempt.method} {attempt.path} is not on the audited path")
        if attempt.audited:
            raise AuditAlreadyWrittenError(f"{attempt.operation} already audited this attempt")
        attempt.audited = True

    async def write_in_transaction(self,
                                   session: Any,
                                   attempt: AuthAttempt,
                                   event: AuthEvent) -> None:
        """An attempt that reaches a consuming or mutating transaction writes its row inside
        that transaction, atomically with any challenge consumption and any state change. Audit
        writing is fail-closed: on success the row commits with the state change or neither
        does."""
        # When each row is written is defined by the auth completion audit requirements in
        # `00-overview-and-shared-contracts.md`; this is the write path they govern.
        # [impl->req~shared-audit-write-in-transaction~1]
        # [impl->req~shared-audit-obligation-of-path~1]
        # [impl->req~shared-audit-fail-closed~1]
        # [impl->req~shared-audit-fail-closed-success~1]
        # [impl->req~schema-auth-events-write-timing-cross-reference~1]
        self._claim(attempt)
        await self._sink.insert(session, self.row_for(event))
        self._count(attempt, event)

    async def write_standalone(self, attempt: AuthAttempt, event: AuthEvent) -> None:
        """An attempt rejected before such a transaction exists writes its row as a standalone
        durable write in its own transaction — the attempt's own, because no later transaction
        exists to carry it — and that write is committed here, not deferred."""
        # [impl->req~shared-audit-write-standalone~1]
        # [impl->req~shared-audit-fail-closed~1]
        # [impl->req~shared-audit-fail-closed-rejection~1]
        # [impl->req~schema-auth-events-write-timing-cross-reference~1]
        if self._session_factory is None:
            raise RuntimeError("no session factory configured for standalone audit writes")
        self._claim(attempt)
        row = self.row_for(event)
        async with self._session_factory() as session:
            await self._sink.insert(session, row)
            await session.commit()
        self._count(attempt, event)

    async def record_rejection(self,
                               attempt: AuthAttempt,
                               event: AuthEvent,
                               error: Exception,
                               *,
                               session: Any | None = None) -> Exception:
        """Write the attempt's row before the response is returned, then hand back the
        rejection the attempt earned. Every canonical state-changing auth operation audits its
        rejected attempts, not only its successful completions, and that obligation covers
        barrier and prepare-phase rejections as well as later ones.

        The write is never best-effort: it is awaited inline here, never queued, deferred to a
        background task, or dropped silently. If it nevertheless fails, the failure is logged
        loudly and the client still receives that same rejection rather than a different
        outcome."""
        # [impl->req~shared-audit-write-before-response~1]
        # [impl->req~shared-rejection-audit-required~1]
        # [impl->req~shared-audit-fail-closed~1]
        # [impl->req~shared-audit-fail-closed-rejection~1]
        # [impl->req~shared-audit-fail-closed-not-best-effort~1]
        try:
            if session is None:
                await self.write_standalone(attempt, event)
            else:
                await self.write_in_transaction(session, attempt, event)
        except (AuditAlreadyWrittenError, OffPathAuditError):
            raise
        except Exception:
            logger.error("auth_audit_write_failed",
                         operation=str(attempt.operation), result=str(event.result),
                         route=attempt.route, exc_info=True)
            self._count(attempt, event)
        return error

    def record_off_path(self,
                        attempt: AuthAttempt,
                        result: AuthEventResult,
                        *,
                        reason: str | None = None) -> None:
        """An authentication or identity-resolution rejection on any route outside the
        canonical operation inventory writes no `audit.auth_events` row: its stable internal
        result code goes to the structured security log and the required counter metric."""
        # Off the audited path the same rejection stays first-class as its named result code in
        # the structured security log and the required counter metric, and writes no row here.
        # [impl->req~shared-off-path-no-audit-row~1]
        # [impl->req~shared-barrier-result-first-class~1]
        # [impl->req~shared-auth-events-scope~1]
        # [impl->req~shared-rejection-audit-scope~1]
        # [impl->req~schema-auth-events-purpose~1]
        # [impl->req~schema-auth-events-invalid-external-jwt-detail~1]
        if attempt.on_audited_path:
            raise OffPathAuditError(f"{attempt.method} {attempt.path} is on the audited path")
        logger.warning("auth_rejected", result=str(result), reason=reason, route=attempt.route)
        # The required counter: `invalid_external_jwt` rejections by bounded reason and route,
        # the sole systemic-break detector, since a systemic backend-verification failure is
        # deliberately indistinguishable from ordinary session expiry to a client.
        # [impl->req~shared-invalid-external-jwt-metric~1]
        self._counter.increment(result=result, route=attempt.route, reason=reason)

    def _count(self, attempt: AuthAttempt, event: AuthEvent) -> None:
        # The same counter fires on the audited path, so no route loses coverage.
        # [impl->req~shared-invalid-external-jwt-metric~1]
        if event.result in BARRIER_RESULTS:
            reason = event.details.get("reason")
            self._counter.increment(result=event.result, route=attempt.route,
                                    reason=str(reason) if reason is not None else None)
