"""What restore does with a verified store artifact, and what it accepts about it.

`05-proof-adapters-and-derived-identifiers.md` owns the restore-proof rules themselves. This
module owns the part built on top of the verified result: that `restore_proof` is an accepted
bearer recovery credential for subscription entitlement, the four mitigations that make that
acceptable, the secrecy of the raw material, the store-side verification the backend performs, the
lifetime store-transaction-to-account binding that caps a proof at one account, and the manual
repair that is the only way to move an established binding.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult, redact, structured_details
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.invariants import DevicePlatform, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_restore import (
    RESTORE_ADDITIONAL_PROOF,
    RESTORE_CHALLENGES,
    InvalidRestoreProof,
    StoreVerifier,
    VerifiedStoreProof,
    verify_restore_proof,
)
from nativespeaker.api.auth.restore import (
    NON_STORE_PROOF_FIELDS,
    RestoreContractError,
    RestoreRejection,
    native_only_surface_gate,
)


class RestoreProofPolicyError(RuntimeError):
    """A property this file states about restore proof was about to be broken."""


# --- What this file owns, and what it does not ---------------------------------------------------

THIS_FILE: str = "04-subscription-restore-and-entitlement-transfer.md"
PROOF_RULES_OWNER: str = "05-proof-adapters-and-derived-identifiers.md"

# The restore-proof rules owned by the proof file's `## Restore Proof`. This file states none of
# them: it calls that file's verification and builds entitlement behaviour on the result.
PROOF_FILE_RULES: tuple[str, ...] = (
    "server_verifiability",
    "absence_of_challenge_binding",
    "server_side_verification_of_the_artifact",
    "sole_restoration_input",
    "not_ownership_proof",
    "moves_no_app_data",
)

# What this file defines instead.
THIS_FILE_RULES: tuple[str, ...] = (
    "bearer_credential_property",
    "bearer_credential_mitigations",
    "entitlement_behaviour_on_the_verified_result",
)


def proof_rule_owner(rule: str) -> str:
    """Which file owns a restore-proof rule."""
    if rule in PROOF_FILE_RULES:
        return PROOF_RULES_OWNER
    if rule in THIS_FILE_RULES:
        return THIS_FILE
    raise RestoreProofPolicyError(f"{rule} is no restore-proof rule")


# --- Server-side verification, against the store -------------------------------------------------

# Verification runs against the store, never against the device: there is no device-side
# verification step and no client-asserted verification result on this endpoint.
VERIFICATION_TARGET: str = "store"
DEVICE_SIDE_VERIFICATION: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class StoreVerificationCall:
    """The one call each store's verification makes, and the ordinary store checks it performs."""
    provider: StoreProvider
    api: str
    checks: tuple[str, ...]


# Apple: the signed StoreKit transaction (JWS) verified against Apple's certificate chain or
# through the App Store Server API's `Get Transaction Info`, checking bundle ID, product ID and
# environment. Google Play: the purchase token verified through the Play Developer API's
# `purchases.subscriptionsv2.get`, checking package name, product and subscription state.
STORE_SIDE_VERIFICATION: dict[StoreProvider, StoreVerificationCall] = {
    StoreProvider.apple: StoreVerificationCall(
        StoreProvider.apple, "app_store_server_api.get_transaction_info",
        ("jws_certificate_chain", "bundle_id", "product_id", "environment")),
    StoreProvider.google_play: StoreVerificationCall(
        StoreProvider.google_play, "play_developer_api.purchases.subscriptionsv2.get",
        ("package_name", "product", "subscription_state")),
}


def store_side_verification(provider: StoreProvider,
                            *,
                            performed_checks: Iterable[str],
                            target: str = VERIFICATION_TARGET) -> StoreVerificationCall:
    """Restore's proof set is the store artifact alone, and its verification runs server-side
    against the store rather than against the device. Each store's own application and environment
    field checks are ordinary store checks, unrelated to any device-integrity proof."""
    # [impl->req~restore-proof-set-store-side-verification~1]
    if target != VERIFICATION_TARGET or DEVICE_SIDE_VERIFICATION:
        raise RestoreProofPolicyError(f"restore verifies against the store, not {target}")
    if RESTORE_ADDITIONAL_PROOF:
        raise RestoreProofPolicyError("the store artifact is restore's entire proof set")
    call = STORE_SIDE_VERIFICATION[provider]
    missing = tuple(check for check in call.checks if check not in set(performed_checks))
    if missing:
        raise InvalidRestoreProof(f"{call.api} did not check {list(missing)}")
    return call


def verify_store_artifact(platform: DevicePlatform,
                          body: Mapping[str, Any] | None,
                          verifier: StoreVerifier,
                          *,
                          performed_checks: Iterable[str]) -> VerifiedStoreProof:
    """Verify the request's store artifact and return what the store confirmed.

    Server-verifiability, the absence of challenge binding, the server-side verification of the
    artifact and its use as the sole restoration input, not-ownership-proof and moves-no-app-data
    are the proof file's rules; this call is where restore satisfies them rather than restating
    them, and it adds only the store-side checks above.
    """
    # [impl->req~restore-proof-rules-owned-by-proof-file~1]
    # [impl->req~restore-proof-set-store-side-verification~1]
    fields = dict(body or {})
    store = native_only_surface_gate(
        platform,
        artifact_family=fields.get("store_artifact_family"),
        store_artifact=(fields.get("restore_proof")
                        if isinstance(fields.get("restore_proof"), str) else None))
    offered = sorted(set(fields) & NON_STORE_PROOF_FIELDS)
    if offered:
        raise RestoreRejection(AuthEventResult.invalid_restore_proof,
                               f"restore accepts no {offered}")
    store_side_verification(store, performed_checks=performed_checks)
    return verify_restore_proof(platform, str(fields.get("restore_proof")), verifier)


# --- The accepted bearer-credential property ------------------------------------------------------

# What the proof set proves, and what it does not. No part of it shows that the requester ever
# owned the subscription.
PROOF_SET_PROVES: tuple[str, ...] = ("store_subscription_entitlement",)
PROOF_SET_DOES_NOT_PROVE: tuple[str, ...] = (
    "original_subscriber", "current_source_account_owner", "prior_app_account_ownership",
)

# Replay protection comes from these two, not from an operation challenge.
REPLAY_PROTECTION: tuple[str, ...] = (
    "lifetime_store_transaction_to_account_binding",
    "per_provider_external_id_store_subscription_serialization",
)

# Every precondition that still applies to a bearer proof, so a proof reaches only a store
# subscription no account has claimed.
BEARER_PRECONDITIONS: tuple[str, ...] = (
    "server_side_restore_proof_verification",
    "purchase_uuid_resolution_through_store_purchases",
    "product_entitled_subscription_state",
    "adoption_live_store_state_verification",
    "registered_active_destination",
)

# The mitigations for the bearer property, and the whole of them.
BEARER_MITIGATIONS: tuple[str, ...] = (
    "store_side_proof_verification",
    "lifetime_store_transaction_to_account_binding",
    "one_active_grant_per_user",
    "gateway_and_backend_admission_limits",
)

# Device attestation is not among them: it would constrain which app install presents the proof,
# never who holds it.
ATTESTATION_CONSTRAINS: str = "which_app_install_presents_the_proof"
ATTESTATION_NEVER_CONSTRAINS: str = "who_holds_the_proof"
NON_MITIGATIONS: frozenset[str] = frozenset({
    "device_attestation", "app_attest", "play_integrity", "devicecheck",
})


def assert_bearer_mitigations(claimed: Iterable[str] = BEARER_MITIGATIONS) -> tuple[str, ...]:
    """The mitigations for the accepted bearer property are store-side verification of the proof,
    the lifetime store-transaction-to-account binding, the one-active-grant-per-user invariant, and
    the gateway and backend admission limits. Device attestation is not among them and is not used
    here."""
    # [impl->req~restore-proof-bearer-mitigations~1]
    offered = set(claimed)
    attestation = sorted(offered & NON_MITIGATIONS)
    if attestation:
        raise RestoreProofPolicyError(
            f"{attestation} constrains {ATTESTATION_CONSTRAINS}, never {ATTESTATION_NEVER_CONSTRAINS}")
    if offered != set(BEARER_MITIGATIONS):
        raise RestoreProofPolicyError(f"the mitigations are exactly {list(BEARER_MITIGATIONS)}")
    return BEARER_MITIGATIONS


class BindingOutcome(StrEnum):
    """What the lifetime binding says about one attempt."""
    bound = "bound"
    idempotent = "idempotent"


def bind_store_transaction(*,
                           restore_bound_user_id: UUID | None,
                           destination_user_id: UUID,
                           relink: bool = False) -> BindingOutcome:
    """The verified store transaction's stable identity is bound to one account for its life,
    persisted as `core.subscriptions.restore_bound_user_id` on the canonical row.

    The first successful restore sets the binding to its destination user; re-restoring into the
    same account is idempotent success; a restore whose destination differs from a non-NULL binding
    rejects with `store_transaction_already_linked` and is never silently re-linked. Moving the
    binding is a manual operator repair only.
    """
    # [impl->req~restore-lifetime-transaction-account-binding~1]
    # [impl->req~restore-proof-set-not-subscriber-identity~1]
    if relink:
        raise RestoreContractError("moving an established binding is a manual repair only")
    if restore_bound_user_id is None:
        return BindingOutcome.bound
    if restore_bound_user_id == destination_user_id:
        return BindingOutcome.idempotent
    raise RestoreRejection(AuthEventResult.store_transaction_already_linked,
                           "this store transaction is already linked to another account")


def bearer_credential_authorizes(*,
                                 satisfied: Iterable[str],
                                 restore_bound_user_id: UUID | None,
                                 destination_user_id: UUID,
                                 destination_registered: bool = True) -> BindingOutcome:
    """Whoever holds a valid `restore_proof` and can call this endpoint as an active, registered
    account can attach the entitlement it proves to that account, once.

    Every precondition in this document still applies, so a proof reaches only a store subscription
    no account has claimed; a proof for an already-linked transaction is rejected with
    `store_transaction_already_linked` and moves nothing.
    """
    # [impl->req~restore-proof-bearer-credential-accepted~1]
    if not destination_registered:
        raise RestoreContractError("the caller must be an active, registered account")
    missing = tuple(name for name in BEARER_PRECONDITIONS if name not in set(satisfied))
    if missing:
        raise RestoreProofPolicyError(f"the bearer property still requires {list(missing)}")
    return bind_store_transaction(restore_bound_user_id=restore_bound_user_id,
                                  destination_user_id=destination_user_id)


def assert_proof_set_is_not_subscriber_identity(*, claimed_proof_of: Iterable[str] = ()) -> None:
    """The proof set does not prove that the requester is the original subscriber or the current
    source account owner, and replay protection is not an operation challenge."""
    # [impl->req~restore-proof-set-not-subscriber-identity~1]
    overclaimed = sorted(set(claimed_proof_of) & set(PROOF_SET_DOES_NOT_PROVE))
    if overclaimed:
        raise RestoreProofPolicyError(f"the proof set is no proof of {overclaimed}")
    if RESTORE_CHALLENGES:
        raise RestoreProofPolicyError("replay protection is not an operation challenge")


# --- Secret bearer material -----------------------------------------------------------------------

# Where raw proof material must never be written.
FORBIDDEN_PROOF_SINKS: frozenset[str] = frozenset({
    "application_logs", "analytics_events", "crash_reports", "support_bundles", "audit_rows",
    "durable_application_storage",
})

# The one place it may be: the minimum path needed to complete verification.
PERMITTED_PROOF_SINKS: frozenset[str] = frozenset({"store_verification_call"})

# What may be persisted about the proof instead.
PERSISTABLE_PROOF_FACTS: tuple[str, ...] = ("proof_fingerprints", "restore_outcome")


def assert_proof_not_persisted(sink: str) -> str:
    """Raw `restore_proof`, signed StoreKit transactions, Google purchase tokens and equivalent
    payloads are secret bearer material: they go nowhere but the minimum verification path."""
    # [impl->req~restore-proof-secret-bearer-material~1]
    if sink in FORBIDDEN_PROOF_SINKS or sink not in PERMITTED_PROOF_SINKS:
        raise RestoreProofPolicyError(f"raw restore proof is never written to {sink}")
    return sink


def audit_safe_proof_details(*,
                             fingerprints: Sequence[str],
                             outcome: str,
                             raw_proof: str | None = None) -> dict[str, Any]:
    """Only non-secret, server-derived proof fingerprints and structured restore outcomes may be
    persisted in `audit.auth_events.details`."""
    # [impl->req~restore-proof-secret-bearer-material~1]
    if raw_proof is not None:
        raise RestoreProofPolicyError("raw restore proof never reaches an audit row")
    supplied = {"proof_fingerprints": list(fingerprints), "restore_outcome": outcome}
    for key, value in supplied.items():
        if key not in PERSISTABLE_PROOF_FACTS:
            raise RestoreProofPolicyError(f"{key} is no persistable proof fact")
        if redact(value) != value:
            raise RestoreProofPolicyError(f"{key} carries secret bearer material")
    return structured_details({"verification": {"proof_fingerprints": supplied["proof_fingerprints"]},
                               "mutation": {"restore_outcome": supplied["restore_outcome"]}})


# --- The store is the ground truth ----------------------------------------------------------------

# What restore creates, inside the locked mutation transaction, when the store confirms a
# subscription the database does not know about.
CREATABLE_ROWS: tuple[str, ...] = ("core.subscriptions", "core.store_purchases")


def reconcile_to_store(*,
                       store_verified: bool,
                       subscription_row_exists: bool,
                       purchase_row_exists: bool,
                       inside_locked_transaction: bool,
                       carried_purchase_uuid: str | None = None,
                       recorded_identity_value: str | None = None) -> tuple[str, ...]:
    """The store's own verification is the ground truth the database reconciles itself to.

    A verified proof showing a genuine subscription that no `core.subscriptions` or
    `core.store_purchases` row covers does not fail for the missing row: the backend creates the
    missing row(s) from the store-verified data inside the locked mutation transaction. Rejection
    for missing store rows is reserved for a proof that fails store verification itself. A carried
    purchase UUID that differs from the resolved row's recorded attribution still rejects.

    Neither of those two rules is decided here. The missing-row-versus-failed-verification split is
    `restore_flow.missing_purchase_row_path`'s and the carried-UUID comparison is its step 4, so
    each condition has exactly one outcome wherever it is reached from.
    """
    # [impl->req~restore-store-verification-is-ground-truth~1]
    from nativespeaker.api.auth.restore_flow import (  # noqa: PLC0415
        assert_carried_uuid_matches_recorded,
        missing_purchase_row_path,
    )

    if not store_verified:
        missing_purchase_row_path(None, store_verified=False)
    if purchase_row_exists:
        assert_carried_uuid_matches_recorded(carried=carried_purchase_uuid,
                                             recorded=recorded_identity_value)
    missing = tuple(table for table, exists in
                    (("core.subscriptions", subscription_row_exists),
                     ("core.store_purchases", purchase_row_exists)) if not exists)
    if missing and not inside_locked_transaction:
        raise RestoreContractError(
            f"{list(missing)} is created inside the locked mutation transaction")
    return missing


# --- An already-linked subscription needs no second restore ---------------------------------------

# Entitlement is account-level and travels with ordinary sign-in and sync; `POST /auth/sync` is
# what reports it.
ENTITLEMENT_REPORTED_BY: AuthOperation = AuthOperation.sync


def restore_calls_needed(*,
                         subscription_user_id: UUID | None,
                         signed_in_user_id: UUID) -> int:
    """How many restore calls another surface owes for an already-linked purchase: none.

    A subscription already linked to the signed-in account needs no additional restore call from
    another device — entitlement is account-level and `/auth/sync` already reports it — which
    settles the device-switch case for every already-linked purchase.
    """
    # [impl->req~restore-linked-subscription-needs-no-second-restore~1]
    if ENTITLEMENT_REPORTED_BY is not AuthOperation.sync:
        raise RestoreProofPolicyError("/auth/sync reports account-level entitlement")
    if subscription_user_id is not None and subscription_user_id == signed_in_user_id:
        return 0
    return 1


# --- The manual binding repair --------------------------------------------------------------------

# The repair's ordered steps, all in one transaction.
MANUAL_REPAIR_STEPS: tuple[str, ...] = (
    "end_prior_owner_active_subscription_grant",
    "clear_subscriptions_user_id",
    "clear_restore_bound_user_id",
)

# What the repair never touches.
REPAIR_NEVER_TOUCHES: frozenset[str] = frozenset({
    "grant_user_id", "store_purchases_row", "purchase_user_id", "terminal_grant_rows",
    "source_identity_row", "source_block_or_retirement", "firebase_refresh_token_revocation",
})

# Operator actions the repair needs, beyond its own three steps: none. There is no operator-only
# reattachment or rebind action, and no path un-retires a source account.
REPAIR_OPERATOR_ACTIONS: frozenset[str] = frozenset()
SOURCE_UNRETIRE_PATHS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class UnclaimedSubscription:
    """The shape a repaired canonical row is left in — exactly what ingestion produces for an
    unattributed purchase."""
    user_id: None = None
    restore_bound_user_id: None = None


def manual_binding_repair(*,
                          prior_grant_active: bool,
                          transaction: object,
                          grant_transaction: object | None = None,
                          touched: Iterable[str] = ()) -> UnclaimedSubscription:
    """Return the store subscription to the unclaimed state and let the ordinary adoption path
    finish the job.

    In one transaction the operator ends the prior owner's still-active subscription-backed grant,
    if one stands, then clears the canonical row's `user_id` and its `restore_bound_user_id` to
    `NULL`. The repair rewrites no grant's `user_id`, defines no new grant creator, and needs no
    operator-only reattachment or rebind action.
    """
    # [impl->req~restore-manual-binding-repair~1]
    if REPAIR_OPERATOR_ACTIONS or SOURCE_UNRETIRE_PATHS:
        raise RestoreProofPolicyError("the repair needs no reattachment action and revives nothing")
    offending = sorted(set(touched) & REPAIR_NEVER_TOUCHES)
    if offending:
        raise RestoreProofPolicyError(f"the repair leaves {offending} exactly as they are")
    if prior_grant_active and grant_transaction is not None and grant_transaction is not transaction:
        raise RestoreProofPolicyError("the repair's steps run in one transaction")
    return UnclaimedSubscription()


def manual_grant_source_produces(source: AccessGrantSource) -> str:
    """The `manual` grant source stays what it is: it produces a grant, never subscription
    state."""
    # [impl->req~restore-manual-binding-repair~1]
    if source is not AccessGrantSource.manual:
        raise RestoreProofPolicyError(f"{source} is not the manual grant source")
    return "core.access_grants"


# --- Abuse throttling -----------------------------------------------------------------------------

# The controls restore's abuse throttling stays with. No new mechanism is added.
RESTORE_ABUSE_CONTROLS: tuple[str, ...] = (
    "gateway_admission_limits", "backend_restore_admission_control",
)

# No web attestation surface is added: no WebAuthn, no browser integrity signal, and no
# restore-from-web-with-receipt-alone lane.
WEB_ATTESTATION_SURFACES: frozenset[str] = frozenset()


def restore_abuse_controls(*, added: Iterable[str] = ()) -> tuple[str, ...]:
    """Abuse throttling for restore stays with the existing gateway and backend admission limits."""
    # [impl->req~restore-abuse-throttling-existing-limits~1]
    if WEB_ATTESTATION_SURFACES:
        raise RestoreProofPolicyError("no web attestation surface is added for restore")
    extra = sorted(set(added) - set(RESTORE_ABUSE_CONTROLS))
    if extra:
        raise RestoreProofPolicyError(f"{extra} is a new abuse mechanism restore does not add")
    return RESTORE_ABUSE_CONTROLS
