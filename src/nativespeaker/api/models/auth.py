"""Python mirrors of the auth-domain PostgreSQL enums (`migrations/20260818_01_initial-release.sql`).

No SQLModel table lives here yet -- `core.auth_challenges` and `audit.auth_events` are added by
later Phase 35 plans. These two enums are needed now because route metadata (auth/registry.py)
and the audit writer both key off them.
"""
from enum import StrEnum


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
