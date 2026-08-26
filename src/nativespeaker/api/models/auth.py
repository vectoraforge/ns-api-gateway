"""The auth-domain enums, the challenge request and response bodies, and the `core.auth_challenges` table."""
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from pydantic import BaseModel
from sqlalchemy import DateTime, Enum, LargeBinary
from sqlmodel import Field, SQLModel


class AuthOperation(StrEnum):
    """Mirrors `core.auth_operation` -- the canonical state-changing auth operations."""
    create_user = "create_user"
    upgrade_anonymous_to_registered = "upgrade_anonymous_to_registered"
    claim_anonymous_grant = "claim_anonymous_grant"
    claim_registered_grant = "claim_registered_grant"
    restore_subscription = "restore_subscription"
    sign_out_all = "sign_out_all"
    sync = "sync"


class AuthEventResult(StrEnum):
    """The internal outcome vocabulary for an auth attempt. Never client-visible, and never persisted."""
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


class ChallengeRequest(BaseModel):
    """The issuance body. `operation` is a plain `str`, never a Literal: an unissuable value is the handler's 400."""
    operation: str


class PrepareResponse(BaseModel):
    """The prepare body: the handle and its expiry, and nothing else about the challenge is disclosed."""
    challenge_id: str
    expires_at: datetime


AuthOperationType = cast(Any, Enum(AuthOperation, name='auth_operation', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))
ByteaType = cast(Any, LargeBinary)


class AuthChallenge(SQLModel, table=True):
    """One challenge row. There is no state column: the lifecycle is discriminated by column nullability."""

    __tablename__ = "auth_challenges"
    __table_args__ = {"schema": "core"}

    # Logs correlate on this row id; the public `challenge_id` below is never logged.
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # A secret capability handle: body-only transport, never in a URL, a log, a trace, or error text.
    challenge_id: str = Field(unique=True)
    operation: AuthOperation = Field(sa_type=AuthOperationType)
    # Exactly one of this and the pre-auth pair below is populated.
    bound_external_identity_id: UUID | None = Field(default=None,
                                                    foreign_key="core.external_identities.id")
    # Plaintext on purpose: a deployment-known provider string shared by every user of that provider.
    preauth_issuer: str | None = Field(default=None)
    # Keyed hash of the verified subject, cleared by consumption. No key-version column: a rotation fails it.
    preauth_subject_hash: bytes | None = Field(sa_type=ByteaType, default=None)
    # Written by the application as now + 300s, and evaluated in exactly one place: the claim's WHERE.
    expires_at: datetime = Field(sa_type=DateTimeType)
    claimed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    claim_attempt_id: UUID | None = Field(default=None)
    consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType)
