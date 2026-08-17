"""The shared account-movement audit contract.

`POST /auth/restore-subscription` and `POST /auth/upgrade-anonymous` are the two account-movement
operations. Every attempt on either of them is one `audit.auth_events` row carrying the movement
context in `details`, whatever the outcome, and that row is the durable record and the query
surface for support, fraud review and historical account-movement analysis.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import (
    MOVEMENT_OPERATIONS,
    NO_ACTOR,
    AttemptPhase,
    AuthActor,
    AuthAttempt,
    AuthAuditWriter,
    AuthEvent,
    AuthEventResult,
    movement_details,
    terminal_event,
)
from nativespeaker.api.auth.operations import AuthOperation


class MovementError(RuntimeError):
    """A movement attempt was about to be recorded outside the shared movement contract."""


class MovementKind(StrEnum):
    """The kind of account movement the attempted operation performs."""
    subscription_restore = "subscription_restore"
    identity_upgrade = "identity_upgrade"


# The two account-movement operations and the movement kind each one performs.
MOVEMENT_KIND: dict[AuthOperation, MovementKind] = {
    AuthOperation.restore_subscription: MovementKind.subscription_restore,
    AuthOperation.upgrade_anonymous_to_registered: MovementKind.identity_upgrade,
}


class MovementClassification(StrEnum):
    """The movement classification recorded in `details`."""
    same_account = "same_account"
    adoption = "adoption"
    unclassified = "unclassified"
    upgrade = "upgrade"


CLASSIFICATIONS_BY_KIND: dict[MovementKind, frozenset[MovementClassification]] = {
    MovementKind.subscription_restore: frozenset({MovementClassification.same_account,
                                                  MovementClassification.adoption,
                                                  MovementClassification.unclassified}),
    MovementKind.identity_upgrade: frozenset({MovementClassification.upgrade}),
}

# What `details` must record at minimum for a movement attempt, whatever its outcome.
MOVEMENT_MINIMUM_DETAIL_KEYS: tuple[str, ...] = (
    "operation", "movement_kind", "result", "movement_classification",
    "source_user_id", "source_external_identity_id",
    "destination_user_id", "destination_external_identity_id",
    "challenge_row_id", "subscription_id", "store_purchase_id", "access_grant_id",
    "proof_fingerprints", "occurred_at",
)


def movement_kind_of(operation: AuthOperation) -> MovementKind:
    """The movement kind of an account-movement operation. Everything else is not a movement."""
    kind = MOVEMENT_KIND.get(operation)
    if kind is None:
        raise MovementError(f"{operation} is not an account-movement operation")
    return kind


@dataclass(frozen=True, slots=True)
class MovementContext:
    """The movement context one attempt folds into its single `audit.auth_events` row."""
    operation: AuthOperation
    result: AuthEventResult
    classification: MovementClassification
    occurred_at: datetime
    source_user_id: UUID | None = None
    source_external_identity_id: UUID | None = None
    destination_user_id: UUID | None = None
    destination_external_identity_id: UUID | None = None
    challenge_row_id: UUID | None = None
    subscription_id: UUID | None = None
    store_purchase_id: UUID | None = None
    access_grant_id: UUID | None = None
    proof_fingerprints: tuple[str, ...] = ()
    store_state_verification: str | None = None

    @property
    def kind(self) -> MovementKind:
        return movement_kind_of(self.operation)


def movement_audit_details(context: MovementContext) -> dict[str, Any]:
    """Build the `details` body for one movement attempt. It records, at minimum, the operation
    attempted and the movement kind, the result code, the source and destination user and identity
    context, the non-secret server-side challenge row ID, the subscription, store-purchase and
    access-grant rows touched, non-secret proof fingerprints, and the timestamp of the attempt."""
    # [impl->req~shared-movement-details-minimum~1]
    kind = movement_kind_of(context.operation)
    if context.classification not in CLASSIFICATIONS_BY_KIND[kind]:
        raise MovementError(f"{context.classification} is not a {kind} classification")
    if isinstance(context.challenge_row_id, str):
        # The public capability handle is a string; the internal row id is a UUID.
        # [impl->req~shared-movement-detail-challenge-row-id~1]
        raise MovementError("challenge_row_id is the internal row id, never the public handle")
    details = movement_details(
        movement_classification=str(context.classification),
        # The resolved source user and source identity context, where the attempt has one.
        # [impl->req~shared-movement-detail-source-context~1]
        source_user_id=context.source_user_id,
        source_external_identity_id=context.source_external_identity_id,
        # The destination user and destination identity context.
        # [impl->req~shared-movement-detail-destination-context~1]
        destination_user_id=context.destination_user_id,
        destination_external_identity_id=context.destination_external_identity_id,
        subscription_id=context.subscription_id,
        # The subscription, store purchase and access grant rows the attempt touched.
        # [impl->req~shared-movement-detail-touched-rows~1]
        store_purchase_id=context.store_purchase_id,
        access_grant_id=context.access_grant_id,
        # Fingerprints only: raw proof material is never part of the record.
        # [impl->req~shared-movement-detail-proof-fingerprints~1]
        proof_fingerprints=list(context.proof_fingerprints),
        store_state_verification=context.store_state_verification)
    # The operation attempted and the movement kind it performs.
    # [impl->req~shared-movement-detail-operation-kind~1]
    details["context"] = {"operation": str(context.operation),
                          "movement_kind": str(kind),
                          # The result code, in the same vocabulary as the `result` column.
                          # [impl->req~shared-movement-detail-result-code~1]
                          "result": str(context.result),
                          # The timestamp of the attempt.
                          # [impl->req~shared-movement-detail-timestamp~1]
                          "occurred_at": context.occurred_at.isoformat()}
    # The non-secret server-side challenge row ID, never the public `challenge_id` handle.
    # [impl->req~shared-movement-detail-challenge-row-id~1]
    details["resolved"]["challenge_row_id"] = context.challenge_row_id
    assert_movement_details_minimum(details)
    return details


def assert_movement_details_minimum(details: dict[str, Any]) -> None:
    """Fail closed on a movement row that does not carry the whole minimum record."""
    # [impl->req~shared-movement-details-minimum~1]
    present = {key for section in details.values() if isinstance(section, dict) for key in section}
    missing = [key for key in MOVEMENT_MINIMUM_DETAIL_KEYS if key not in present]
    if missing:
        raise MovementError(f"movement details are missing {missing}")
    if "challenge_id" in present:
        raise MovementError("the public challenge_id handle is never recorded")


def assert_destination_anchored(context: MovementContext) -> None:
    """Destination or issuing context is anchored by resolved destination identity fields for
    linked flows. Both movement operations are linked flows: a restore's destination is a
    registered user's resolved identity, and `POST /auth/upgrade-anonymous` operates on an
    existing linked identity rather than a pre-auth actor, so its destination context is
    anchored by the resolved destination identity fields on the same identity row before and
    after the in-place provider flip."""
    # [impl->req~shared-movement-destination-anchoring~1]
    # [impl->req~shared-movement-detail-destination-context~1]
    if context.destination_user_id is None:
        raise MovementError("a movement anchors its destination on the resolved user")
    if context.destination_external_identity_id is None:
        raise MovementError(
            "a movement anchors its destination on the resolved destination identity")
    if context.kind is not MovementKind.identity_upgrade:
        return
    if context.source_external_identity_id is None:
        raise MovementError("an upgrade anchors its destination on a resolved linked identity")
    if context.destination_external_identity_id != context.source_external_identity_id:
        raise MovementError("an upgrade's destination identity is the same row before and after")


def unresolved_movement_context(operation: AuthOperation,
                                result: AuthEventResult,
                                occurred_at: datetime,
                                *,
                                challenge_row_id: UUID | None = None) -> MovementContext:
    """The movement context of an attempt rejected before anything was resolved — a barrier
    rejection, or any other pre-resolution rejection. Every field the attempt could not resolve
    is `NULL`, and the classification is the kind's own unresolved value: `unclassified` for a
    restore that never reached branch determination, `upgrade` for the upgrade, whose kind
    admits no other classification. The row is still written: the movement context is owed for
    every attempt, successful or rejected."""
    # [impl->req~shared-upgrade-movement-context-required~1]
    # [impl->req~shared-restore-movement-classification~1]
    kind = movement_kind_of(operation)
    classification = (MovementClassification.upgrade if kind is MovementKind.identity_upgrade
                      else MovementClassification.unclassified)
    if result is AuthEventResult.succeeded:
        raise MovementError("a succeeded movement resolves its own context")
    return MovementContext(operation=operation,
                           result=result,
                           classification=classification,
                           occurred_at=occurred_at,
                           challenge_row_id=challenge_row_id)


def upgrade_movement_context(*,
                             result: AuthEventResult,
                             occurred_at: datetime,
                             user_id: UUID | None,
                             external_identity_id: UUID | None,
                             challenge_row_id: UUID | None = None,
                             issuer_before: str | None = None,
                             issuer_after: str | None = None,
                             subject_before: str | None = None,
                             subject_after: str | None = None,
                             retired_identity_ids: Sequence[UUID] = (),
                             created_identity_ids: Sequence[UUID] = (),
                             proof_fingerprints: Sequence[str] = ()) -> MovementContext:
    """The movement context of one `POST /auth/upgrade-anonymous` attempt. The upgrade preserves
    the same logical user: one identity row's provider is flipped in place for the same
    `(issuer, subject)`, no source identity is retired, and no new identity row is created — so
    the source and destination user and identity are one and the same."""
    # [impl->req~shared-upgrade-preserves-user~1]
    if retired_identity_ids:
        raise MovementError("an upgrade retires no source identity")
    if created_identity_ids:
        raise MovementError("an upgrade creates no new identity row")
    if issuer_before is not None and issuer_after is not None and issuer_before != issuer_after:
        raise MovementError("an upgrade flips the provider for the same issuer")
    if subject_before is not None and subject_after is not None and subject_before != subject_after:
        raise MovementError("an upgrade flips the provider for the same subject")
    context = MovementContext(operation=AuthOperation.upgrade_anonymous_to_registered,
                              result=result,
                              classification=MovementClassification.upgrade,
                              occurred_at=occurred_at,
                              source_user_id=user_id,
                              source_external_identity_id=external_identity_id,
                              destination_user_id=user_id,
                              destination_external_identity_id=external_identity_id,
                              challenge_row_id=challenge_row_id,
                              proof_fingerprints=tuple(proof_fingerprints))
    if result is AuthEventResult.succeeded:
        # A completed upgrade has resolved both ends of the movement, so the anchoring holds.
        assert_destination_anchored(context)
    return context


def restore_branch(current_owner_id: UUID | None,
                   destination_user_id: UUID) -> tuple[MovementClassification, AuthEventResult | None]:
    """Classify a restore whose branch is knowable from the locked owner of the canonical
    subscription: unclaimed is an adoption, the destination itself is a same-account restore, and
    a store transaction linked to a different account is rejected with
    `store_transaction_already_linked` — cross-account transfer is never performed, and that
    rejection is not a classified movement."""
    # [impl->req~shared-restore-movement-classification~1]
    # [impl->req~shared-restore-ownership-immutable~1]
    if current_owner_id is None:
        return MovementClassification.adoption, None
    if current_owner_id == destination_user_id:
        return MovementClassification.same_account, None
    return (MovementClassification.unclassified,
            AuthEventResult.store_transaction_already_linked)


def restore_movement_context(*,
                             result: AuthEventResult,
                             occurred_at: datetime,
                             destination_user_id: UUID | None,
                             destination_external_identity_id: UUID | None,
                             classification: MovementClassification | None = None,
                             source_user_id: UUID | None = None,
                             subscription_id: UUID | None = None,
                             store_purchase_id: UUID | None = None,
                             access_grant_id: UUID | None = None,
                             proof_fingerprints: Sequence[str] = (),
                             store_state_verification: str | None = None) -> MovementContext:
    """The movement context of one `POST /auth/restore-subscription` attempt. Every attempt
    records a movement classification, whether or not it reached branch determination: an attempt
    that failed before the branch was knowable records `unclassified` rather than falsely
    classifying itself."""
    # [impl->req~shared-restore-movement-classification~1]
    if classification is None:
        classification = MovementClassification.unclassified
    if classification not in CLASSIFICATIONS_BY_KIND[MovementKind.subscription_restore]:
        raise MovementError(f"{classification} is not a restore classification")
    if (result is AuthEventResult.store_transaction_already_linked
            and classification is not MovementClassification.unclassified):
        raise MovementError("a store transaction linked elsewhere is never a classified movement")
    if classification is MovementClassification.adoption and source_user_id is not None:
        raise MovementError("an adoption has no source user")
    return MovementContext(operation=AuthOperation.restore_subscription,
                           result=result,
                           classification=classification,
                           occurred_at=occurred_at,
                           source_user_id=source_user_id,
                           destination_user_id=destination_user_id,
                           destination_external_identity_id=destination_external_identity_id,
                           subscription_id=subscription_id,
                           store_purchase_id=store_purchase_id,
                           access_grant_id=access_grant_id,
                           proof_fingerprints=tuple(proof_fingerprints),
                           store_state_verification=store_state_verification)


def settled_subscription_owner(context: MovementContext,
                               *,
                               current_owner_id: UUID | None) -> UUID | None:
    """The owner the canonical `core.subscriptions` row carries once this attempt settles.

    Restore never changes the owner of an already-linked store subscription. Only the adoption of
    an unclaimed subscription establishes ownership, once, for the life of the transaction; a
    failed, rejected, same-account or unclassified attempt leaves the current owner exactly as it
    found it."""
    # [impl->req~shared-restore-ownership-immutable~1]
    if context.operation is not AuthOperation.restore_subscription:
        raise MovementError("only restore settles subscription ownership")
    if (context.classification is MovementClassification.adoption
            and context.result is AuthEventResult.succeeded):
        if current_owner_id is not None:
            raise MovementError("an already-linked subscription is never adopted")
        if context.destination_user_id is None:
            raise MovementError("an adoption links the subscription to its destination user")
        return context.destination_user_id
    return current_owner_id


def movement_event(phase: AttemptPhase,
                   context: MovementContext,
                   *,
                   actor: AuthActor = NO_ACTOR,
                   details: dict[str, Any] | None = None) -> AuthEvent:
    """The single `audit.auth_events` row a movement attempt owes, whatever its outcome. The
    movement context is written for every attempt — successful or rejected — even for
    `upgrade_anonymous_to_registered`, which preserves the same logical user."""
    # [impl->req~shared-upgrade-movement-context-required~1]
    # [impl->req~shared-movement-single-audit-row~1]
    if context.result is AuthEventResult.succeeded:
        assert_destination_anchored(context)
    body = movement_audit_details(context)
    for key, value in (details or {}).items():
        if key in body and isinstance(body[key], dict) and isinstance(value, dict):
            body[key].update(value)
        else:
            body[key] = value
    return terminal_event(phase, context.result, operation=context.operation, actor=actor,
                          challenge_row_id=context.challenge_row_id, details=body)


async def record_movement_attempt(writer: AuthAuditWriter,
                                  attempt: AuthAttempt,
                                  event: AuthEvent,
                                  *,
                                  error: Exception | None = None,
                                  session: Any = None) -> Exception | None:
    """Record one movement attempt as its single `audit.auth_events` row. A second row for the
    same attempt is refused by the writer, so the one row stays the durable record for the
    attempt whatever its outcome."""
    # [impl->req~shared-movement-single-audit-row~1]
    # [impl->req~shared-upgrade-movement-context-required~1]
    if attempt.operation not in MOVEMENT_OPERATIONS:
        raise MovementError(f"{attempt.operation} is not an account-movement operation")
    if event.operation is not attempt.operation:
        raise MovementError("the movement row names the operation the attempt matched")
    if error is not None:
        return await writer.record_rejection(attempt, event, error, session=session)
    if session is None:
        raise MovementError("a successful movement writes its row in the mutating transaction")
    await writer.write_in_transaction(session, attempt, event)
    return None
