"""The auth-domain PostgreSQL enums, the `core.auth_challenges` table, and `audit.auth_events`.

The two enums came first because route metadata (auth/registry.py) and the audit writer both key
off them.

`AuthEvent` is the first model in this codebase mapped outside the `core` schema. Every constraint
the table carries stays in `migrations/20260818_01_initial-release.sql` and is deliberately not
re-encoded here -- the all-or-nothing actor CHECK, the six-key `details` shape, and the
`succeeded`-needs-an-operation rule included. A Python copy of a CHECK is a second source of truth
that can drift from the one that actually enforces. What the writer *does* do is refuse to build a
row those CHECKs would reject, so the failure reads as a message rather than as a constraint
violation; that guard lives in `auth/audit.py`, next to the caller it protects.
"""
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID, uuid7

from sqlalchemy import DateTime, Enum, LargeBinary, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from nativespeaker.api.models.identities import IdentityProvider, IdentityProviderType


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
    """Mirrors `core.auth_event_result` -- the internal audit outcome codes.

    Closed and exact (44 values). Never client-visible: the shared error registry maps these onto
    the client-visible classes, and the audited internal result is never less specific than the
    class returned.
    """
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


AuthOperationType = cast(Any, Enum(AuthOperation, name='auth_operation', schema='core'))
AuthEventResultType = cast(Any, Enum(AuthEventResult, name='auth_event_result', schema='core'))
DateTimeType = cast(Any, DateTime(timezone=True))
# BYTEA and SMALLINT. The key version is a SMALLINT, which is why `HmacConfig.active_version` is
# bounded to 1..32767 at configuration load rather than discovered at the first insert.
ByteaType = cast(Any, LargeBinary)
SmallIntType = cast(Any, SmallInteger)
JSONBType = cast(Any, JSONB)


class AuthChallenge(SQLModel, table=True):
    """One challenge row (§6). Lifecycle is discriminated by column nullability, not by a state
    column: `issued` while `claimed_at IS NULL`, `claimed` once `claimed_at` and the attempt's
    server-generated `claim_attempt_id` are set, `consumed` once `consumed_at` is set.

    Do not add a state column, and do **not** add an HMAC key-version column. The migration comment
    forbids the second explicitly: verification uses the current active key alone, so a challenge
    outstanding across a key rotation simply fails (D-21's accepted consequence). `audit.auth_events`
    is the table that has one.

    The three CHECKs -- the lifecycle nullability rule, the operation-membership rule that admits
    exactly the four challenge-bearing operations, and the binding rule that admits a cleared
    `preauth_subject_hash` only once `consumed_at` is set -- live in the migration and are
    deliberately not re-encoded here.
    """

    __tablename__ = "auth_challenges"
    __table_args__ = {"schema": "core"}

    # The internal correlation identifier, never returned to a client. This is the id that goes in
    # `audit.auth_events.challenge_row_id`; the public `challenge_id` below never does.
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # The single opaque random value that both locates the row and serves as the nonce (§6.5). A
    # **secret capability handle**: body-only transport, and never in a URL, an audit row, a log, a
    # trace, analytics, or error text.
    challenge_id: str = Field(unique=True)
    operation: AuthOperation = Field(sa_type=AuthOperationType)
    # §6.4's linked arm. Exactly one of this and the pre-auth pair below is populated.
    bound_external_identity_id: UUID | None = Field(default=None,
                                                    foreign_key="core.external_identities.id")
    # Ruling 9.3: PLAINTEXT on purpose. A deployment-known provider string shared by every user of
    # that provider -- do not hash it, encrypt it, or drop it.
    preauth_issuer: str | None = Field(default=None)
    # Ruling 9.4: the keyed hash of the backend-verified subject, never the raw subject and never a
    # signed token the client carries. Cleared by consumption, in the same statement that sets
    # `consumed_at` -- the binding CHECK admits a cleared hash only then.
    preauth_subject_hash: bytes | None = Field(sa_type=ByteaType, default=None)
    # Written by the application as `now + 300s` (§6.3). No database default, no per-operation
    # override, and evaluated in exactly one place: the claim's WHERE.
    expires_at: datetime = Field(sa_type=DateTimeType)
    claimed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    claim_attempt_id: UUID | None = Field(default=None)
    consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType)


class AuthEvent(SQLModel, table=True):
    """One append-only row per on-path attempt, for its terminal outcome (§4.1).

    No raw subject, no raw token, and no other plaintext credential material lands here: the actor
    subject is a keyed BYTEA hash with the version of the key that produced it, and `details` is
    redacted before write.
    """

    __tablename__ = "auth_events"
    __table_args__ = {"schema": "audit"}

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # A bare UUID with NO foreign key to core.auth_challenges, deliberately, so audit rows survive
    # independently of the challenge they describe. This is the **non-secret** row id; the public
    # `challenge_id` capability handle is never written to a row, to `details`, to a log, or to
    # error text.
    challenge_row_id: UUID | None = Field(default=None)
    # Nullable: a rejection can precede operation determination. The table requires it non-NULL
    # when `result = 'succeeded'`.
    operation: AuthOperation | None = Field(sa_type=AuthOperationType, default=None)
    # The single machine-readable outcome. There is no failure_reason column and no free-text
    # fallback -- the bounded reason lives in `details.failure`.
    result: AuthEventResult = Field(sa_type=AuthEventResultType)
    actor_issuer: str | None = Field(default=None)
    actor_subject_hash: bytes | None = Field(sa_type=ByteaType, default=None)
    actor_subject_hash_key_version: int | None = Field(sa_type=SmallIntType, default=None)
    # Populated only from the **stored** core.external_identities.provider column of a resolved
    # linked identity. Never fabricated, and never taken from token claims, headers, or client
    # input.
    actor_provider: IdentityProvider | None = Field(sa_type=IdentityProviderType, default=None)
    details: dict = Field(sa_type=JSONBType)
    created_at: datetime = Field(sa_type=DateTimeType)
