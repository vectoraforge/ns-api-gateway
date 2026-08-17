"""The unclaimed-subscription adoption branch: entry condition, the two precondition sets, the
nine mutation rules, and the postconditions.

Adoption is the successor of the former cross-account entitlement-transfer branch. It attaches a
store subscription that belongs to nobody to the destination user, and it is the one restore path
that creates a grant and a monthly usage row. There is no source user, nothing is transferred, and
an owned store subscription never enters this branch.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult, movement_details
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import InvariantError, StoreProvider, assert_owner_agreement
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.restore import (
    MovementClassification,
    RestoreBranch,
    RestoreContractError,
    RestoreRejection,
)
from nativespeaker.api.auth.restore_flow import (
    PURCHASE_ROW_INSERT_ONCE,
    CurrentSubscriptionState,
    PurchaseRow,
    VerifiedTransaction,
    assert_product_entitled,
    assert_purchase_row_immutable,
    internal_purchase_uuid,
)
from nativespeaker.api.auth.restore_live_verification import live_verification_surface
from nativespeaker.api.auth.restore_operation import (
    RestoreGrantMutations,
    RestorePhase,
    audit_placement,
)
from nativespeaker.api.auth.restore_phases import (
    LiveStoreVerification,
    LockedPhaseLedger,
    LockedState,
    PreTransactionLedger,
    assert_no_provider_calls,
    step_08_live_store_state_verification,
    step_16_resolve_outcome_and_divergence,
    step_17_live_verification_freshness,
)
from nativespeaker.api.auth.restore_proof_policy import bind_store_transaction
from nativespeaker.api.auth.restore_same_account import PurchaseRowInsert
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.usage import assert_stays_with_grant


class AdoptionError(RestoreContractError):
    """The adoption branch was about to break one of its own rules."""


# --- The branch that succeeds the cross-account branch -------------------------------------------

# Configuration entries, admission-limit names and API surfaces whose names still say
# `cross_account`. They continue to govern this adoption path unchanged, so the rename of the
# branch is not a rename of the deployed configuration.
CROSS_ACCOUNT_NAMES: tuple[str, ...] = (
    "restore_subscription_store_subscription_cross_account",
    "restore_subscription_destination_rejected_cross_account",
)

# What the adoption branch may do to a store subscription that already belongs to an account:
# nothing. Cross-account transfer of an owned subscription is never performed.
OWNED_SUBSCRIPTION_TRANSFERS: frozenset[str] = frozenset()


def governs_adoption(name: str) -> bool:
    """A configuration entry, admission-limit name or API surface whose name says `cross_account`
    governs this adoption path unchanged."""
    # [impl->req~restore-adoption-succeeds-cross-account-branch~1]
    return name in CROSS_ACCOUNT_NAMES


def assert_owned_subscription_never_transferred(subscription: CurrentSubscriptionState,
                                                *,
                                                destination_user_id: UUID) -> None:
    """Cross-account transfer of an owned subscription is never performed: it rejects with
    `store_transaction_already_linked`."""
    # [impl->req~restore-adoption-succeeds-cross-account-branch~1]
    if OWNED_SUBSCRIPTION_TRANSFERS:
        raise AdoptionError("no adoption path transfers an owned store subscription")
    owner = subscription.user_id
    bound = subscription.restore_bound_user_id
    if ((owner is not None and owner != destination_user_id)
            or (bound is not None and bound != destination_user_id)):
        raise RestoreRejection(AuthEventResult.store_transaction_already_linked,
                               "this store transaction is already linked to another account")


# --- Entry condition ------------------------------------------------------------------------------

# Adoption has no source user at all, on either path.
ADOPTION_SOURCE_USER_ID: None = None


def entry_unclaimed_or_no_row(subscription: CurrentSubscriptionState,
                              *,
                              destination_user_id: UUID) -> bool:
    """The canonical `core.subscriptions` row for the resolved store subscription is unclaimed —
    linked to no account, with the lifetime store-transaction binding unset — or no canonical row
    exists yet, the adoption-with-creation case where restore creates the canonical row and the
    missing `core.store_purchases` row inside the locked mutation transaction.

    There is no source user. A store subscription linked to a different account never enters this
    branch. Returns whether this attempt is adoption-with-creation.
    """
    # [impl->req~restore-adoption-entry-unclaimed-or-no-row~1]
    row = subscription.row
    if row is None:
        return True
    assert_owned_subscription_never_transferred(subscription,
                                                destination_user_id=destination_user_id)
    if row.user_id is not None or subscription.restore_bound_user_id is not None:
        raise AdoptionError("a store subscription already owned by the destination is same-account")
    return False


def entry_destination_active_and_grant_free(*,
                                            destination_user_id: UUID,
                                            destination_active: bool,
                                            active_grant_sources: Iterable[AccessGrantSource] = (),
                                            expired_to_make_room: Iterable[UUID] = ()) -> UUID:
    """The destination user is `active` and holds no different active grant of any source — no
    source is exempt and none outranks another; otherwise the attempt rejects with
    `restore_destination_already_entitled`, and restore never expires a different active grant to
    make room."""
    # [impl->req~restore-adoption-entry-destination-active-no-other-grant~1]
    if sorted(set(expired_to_make_room)):
        raise AdoptionError("restore never expires a different active grant to make room")
    if not destination_active:
        raise RestoreRejection(AuthEventResult.blocked_user,
                               "the destination user is not active")
    standing = sorted(str(source) for source in active_grant_sources)
    if standing:
        raise RestoreRejection(AuthEventResult.restore_destination_already_entitled,
                               f"the destination already holds an active {standing} grant")
    return destination_user_id


def entry_product_entitled_and_live_verified(*,
                                             pre_transaction: CurrentSubscriptionState,
                                             locked: CurrentSubscriptionState,
                                             verification: LiveStoreVerification | None,
                                             recheck_passed: bool,
                                             adoption_with_creation: bool) -> SubscriptionStatus:
    """The canonical row is currently product-entitled at both the pre-transaction read and inside
    the locked mutation transaction — on the adoption-with-creation path, where no row exists
    pre-transaction, entitlement is established by the live verification and the row is created at
    the live-verified state — and live store-state verification was run pre-transaction and remains
    fresh and corresponding at the locked-phase recheck."""
    # [impl->req~restore-adoption-entry-product-entitled-and-live-verified~1]
    if verification is None:
        raise RestoreRejection(AuthEventResult.restore_store_state_unverified,
                               "adoption requires a pre-transaction live store-state verification")
    if not recheck_passed:
        raise RestoreRejection(
            AuthEventResult.restore_store_state_unverified,
            "the recorded verification is stale or covers a different store subscription")
    if adoption_with_creation:
        if pre_transaction.row is not None:
            raise AdoptionError("adoption-with-creation resolves to no pre-transaction row")
        # No canonical row existed pre-transaction, so the live-verified state is what has to be
        # product-entitled: it is the state the row is created at.
        assert_product_entitled(None, live_verified_status=verification.status)
        return verification.status
    assert_product_entitled(pre_transaction.status)
    assert_product_entitled(locked.status)
    status = locked.status
    if status is None:
        raise AdoptionError("no locked state stands behind the entitlement check")
    return status


# A successful adoption sends nothing to the user; the entitlement is observed through the
# existing reporting endpoint.
USER_FACING_NOTIFICATIONS: frozenset[str] = frozenset()
ADOPTION_REPORTING_ROUTE: tuple[str, str] = ("POST", "/auth/sync")


def adoption_notifications(sent: Iterable[str] = ()) -> tuple[str, str]:
    """A successful adoption sends no user-facing notification. The destination user observes the
    entitlement through the existing `/auth/sync` reporting."""
    # [impl->req~restore-adoption-no-user-facing-notification~1]
    offending = sorted(set(sent) | USER_FACING_NOTIFICATIONS)
    if offending:
        raise AdoptionError(f"a successful adoption sends no {offending}")
    return ADOPTION_REPORTING_ROUTE


# --- The two precondition sets --------------------------------------------------------------------

PRE_TRANSACTION_PRECONDITIONS: tuple[int, ...] = (1,)
LOCKED_PRECONDITIONS: tuple[int, ...] = (2, 3, 4)

SHARED_BARRIER_STEP: str = "shared_barrier"
ADOPTION_PRECONDITION_STEPS: tuple[str, ...] = (
    "01_live_store_state_verification",
    "02_still_unclaimed",
    "03_different_active_grant",
    "04_live_verification_freshness_recheck",
)


def precondition_numbering() -> tuple[int, ...]:
    """The locked-phase preconditions continue the pre-transaction numbering above as one
    sequence."""
    # [impl->req~restore-adoption-locked-precondition-numbering~1]
    numbers = (*PRE_TRANSACTION_PRECONDITIONS, *LOCKED_PRECONDITIONS)
    if numbers != tuple(range(1, len(numbers) + 1)):
        raise AdoptionError(f"{list(numbers)} is not one continuous precondition sequence")
    return numbers


def assert_precondition_split_and_audit(*,
                                        number: int,
                                        result: AuthEventResult,
                                        classification: MovementClassification,
                                        mutation_performed: Iterable[str] = ()):
    """Adoption preconditions split into a pre-transaction set evaluated before the locked mutation
    transaction is entered and a locked-phase set evaluated inside it from re-resolved local state.

    All preconditions in both sets must hold; failure of any of them rejects without mutation,
    audits with its listed `core.auth_event_result`, and records a movement classification in
    `details`. The pre-transaction rejection writes its row in the pre-transaction rejection
    transaction; the locked-phase rejection writes it in the locked mutation transaction.
    """
    # [impl->req~restore-adoption-precondition-split-and-audit~1]
    if number in PRE_TRANSACTION_PRECONDITIONS:
        phase = RestorePhase.pre_transaction
    elif number in LOCKED_PRECONDITIONS:
        phase = RestorePhase.locked_mutation
    else:
        raise AdoptionError(f"precondition {number} is in neither adoption precondition set")
    if result is AuthEventResult.succeeded:
        raise AdoptionError("a failed precondition rejects; it never audits as succeeded")
    if classification not in set(MovementClassification):
        raise AdoptionError(f"{classification} is no movement classification")
    return audit_placement(phase=phase, result=result, mutation_performed=mutation_performed)


def assert_shared_barrier_runs_first(order: Sequence[str] = (SHARED_BARRIER_STEP,
                                                             *ADOPTION_PRECONDITION_STEPS),
                                     *,
                                     barrier_admitted: bool = True) -> tuple[str, ...]:
    """The shared barrier checks in `00-overview-and-shared-contracts.md` run before these
    restore-specific preconditions."""
    # [impl->req~restore-adoption-shared-barrier-runs-first~1]
    if not barrier_admitted:
        raise AdoptionError("the shared barrier admits the request before any restore precondition")
    steps = tuple(order)
    if SHARED_BARRIER_STEP not in steps:
        raise AdoptionError("the shared barrier checks run before the restore-specific ones")
    barrier_at = steps.index(SHARED_BARRIER_STEP)
    early = [step for position, step in enumerate(steps)
             if step in ADOPTION_PRECONDITION_STEPS and position < barrier_at]
    if early:
        raise AdoptionError(f"{early} runs after the shared barrier checks, never before")
    return steps


def pre_transaction_precondition_01_live_store_state_verification(
        verified: VerifiedTransaction,
        subscription: CurrentSubscriptionState,
        *,
        ledger: PreTransactionLedger,
        lookup: Callable[[StoreProvider, str], SubscriptionStatus | str | None],
        now: datetime,
        branch: RestoreBranch = RestoreBranch.adoption,
        backend_held_credentials: bool = True,
        input_sources: Iterable[str] = ("server_verified_restore_material",)
        ) -> LiveStoreVerification:
    """1. Live store-state verification must succeed before the locked mutation transaction is
    entered.

    It confirms through the provider's own server-side API that the subscription the verified
    material identifies is currently entitled at the store, using backend-held credentials and
    lookup inputs derived only from server-verified restore material and the non-locking read of
    `core.subscriptions`. A missing, unknown, revoked, expired or otherwise non-entitled live state
    rejects with `restore_store_state_unverified`, and so does failure or timeout of the single
    provider call. The outcome is recorded together with the store subscription it covers — the
    resolved `(provider, external_id)`, and the `core.subscriptions.id` it covered where a canonical
    row existed, or a note of that row's absence — and a server-issued verification timestamp, for
    locked-phase precondition 4 to consume.
    """
    # [impl->req~restore-pre-transaction-precondition-01-live-store-state-verification~1]
    if branch is not RestoreBranch.adoption:
        raise AdoptionError("this precondition belongs to the adoption branch")
    # The confirmation is made through the provider's own server-side API — Apple's App Store
    # Server API for an Apple attempt, the Google Play Developer API for a `google_play` one — so
    # the surface is selected from the attempt's provider before the call, and a provider with no
    # such API never reaches one.
    surface = live_verification_surface(verified.provider)
    ledger.record(f"01_live_verification_api:{surface.api}")

    def through_the_providers_own_api(
            provider: StoreProvider, external_id: str) -> SubscriptionStatus | str | None:
        if provider is not surface.provider:
            raise AdoptionError(
                f"{provider} is not verified through {surface.api}")
        return lookup(provider, external_id)

    recorded = step_08_live_store_state_verification(
        verified, subscription, branch=branch, ledger=ledger,
        lookup=through_the_providers_own_api, now=now,
        backend_held_credentials=backend_held_credentials, input_sources=input_sources)
    if recorded is None:
        raise AdoptionError("adoption records a live store-state verification outcome")
    if recorded.key != verified.key:
        raise AdoptionError("the record covers the resolved (provider, external_id)")
    row = subscription.row
    if recorded.canonical_row_absent != (row is None):
        raise AdoptionError("the record notes the canonical row it covered, or its absence")
    if row is not None and recorded.subscription_id != row.subscription_id:
        raise AdoptionError("the record names the canonical row whose state it covered")
    return recorded


def locked_precondition_02_still_unclaimed(state: LockedState,
                                           *,
                                           ledger: LockedPhaseLedger,
                                           destination_user_id: UUID,
                                           pre_transaction_branch: RestoreBranch =
                                           RestoreBranch.adoption,
                                           purchase_user_active: bool | None = None) -> bool:
    """2. The subscription must still be unclaimed under locked state — linked to no account, with
    the lifetime store-transaction binding unset.

    A locked state showing a linked account is rejected at the step 16 confirmation as
    `store_transaction_already_linked` for a different account or as `restore_branch_inconsistent`
    for a divergence, never transferred. There is no source user; the `purchase_user_id` on the
    resolved `core.store_purchases` row is purchase context only and is subject to no active-user
    check.
    """
    # [impl->req~restore-locked-precondition-02-still-unclaimed~1]
    if purchase_user_active is not None:
        raise AdoptionError("the purchase row's purchase_user_id gets no active-user check")
    outcome = step_16_resolve_outcome_and_divergence(
        state, ledger=ledger, destination_user_id=destination_user_id,
        pre_transaction_branch=pre_transaction_branch)
    if outcome is not RestoreBranch.adoption:
        raise AdoptionError(f"{outcome} is no adoption outcome under locked state")
    bound = state.subscription.restore_bound_user_id
    if bound is not None:
        # The different-account decision belongs to the lifetime binding rule, which is where a
        # binding naming another account rejects as `store_transaction_already_linked`; this
        # precondition does not fork a second comparison.
        bind_store_transaction(restore_bound_user_id=bound,
                               destination_user_id=destination_user_id)
        # A binding that names the destination while the canonical row is still unclaimed is a
        # locked state that cannot be reconciled with a single outcome, not a different-account
        # conflict.
        raise RestoreRejection(
            AuthEventResult.restore_branch_inconsistent,
            "an unclaimed row bound to the destination reconciles with no single outcome")
    return True


# What the adoption branch may do to an existing active grant on the destination: nothing.
EXISTING_ACTIVE_GRANT_MUTATIONS: frozenset[str] = frozenset()
GRANT_MUTATION_VERBS: frozenset[str] = frozenset({"expire", "replace", "revoke", "mutate"})


def locked_precondition_03_different_active_grant(
        *,
        destination_user_id: UUID,
        active_grant_sources: Iterable[AccessGrantSource] = (),
        attempted: Iterable[str] = ()) -> UUID:
    """3. The destination user must not already hold any different active grant, of any source.

    Otherwise, reject with `restore_destination_already_entitled`. No source is exempt and none
    outranks another, and the adoption branch must not expire, replace, revoke or otherwise mutate
    any existing active grant on the destination to make room: an existing different active grant is
    a hard reject.
    """
    # [impl->req~restore-locked-precondition-03-different-active-grant~1]
    offending = sorted((set(attempted) | EXISTING_ACTIVE_GRANT_MUTATIONS) & GRANT_MUTATION_VERBS)
    if offending:
        raise AdoptionError(f"adoption does not {offending} an existing active grant to make room")
    standing = sorted(str(source) for source in active_grant_sources)
    if standing:
        raise RestoreRejection(AuthEventResult.restore_destination_already_entitled,
                               f"the destination already holds an active {standing} grant")
    return destination_user_id


def locked_precondition_04_live_verification_freshness_recheck(
        verification: LiveStoreVerification | None,
        *,
        ledger: LockedPhaseLedger,
        locked_key: tuple[StoreProvider, str],
        locked_subscription_id: UUID | None,
        now: datetime,
        freshness_seconds: float,
        branch: RestoreBranch = RestoreBranch.adoption,
        provider_call: str | None = None) -> LiveStoreVerification:
    """4. The pre-transaction live store-state verification must still be fresh under the configured
    freshness bound and must still correspond to the store subscription now resolved inside the
    lock.

    The recorded `(provider, external_id)` must match the store subscription resolved at lock
    acquisition, and the recorded `core.subscriptions.id`, where it recorded one, must match the
    current row; on the adoption-with-creation path the `(provider, external_id)` match is the whole
    correspondence. Stale or non-corresponding rejects with `restore_store_state_unverified` and
    performs no mutation. The locked phase never calls Apple or Google to re-run live verification.
    """
    # [impl->req~restore-locked-precondition-04-live-verification-freshness-recheck~1]
    rechecked = step_17_live_verification_freshness(
        verification, ledger=ledger, branch=branch, locked_key=locked_key,
        locked_subscription_id=locked_subscription_id, now=now,
        freshness_seconds=freshness_seconds, provider_call=provider_call)
    if rechecked is None:
        raise AdoptionError("the adoption branch consumes a recorded live verification")
    return rechecked


# --- Mutation rules -------------------------------------------------------------------------------

ADOPTION_PRECONDITION_NUMBERS: tuple[int, ...] = (*PRE_TRANSACTION_PRECONDITIONS,
                                                  *LOCKED_PRECONDITIONS)


def assert_mutations_inside_locked_transaction(*,
                                               ledger: LockedPhaseLedger,
                                               preconditions_passed: Iterable[int],
                                               provider_call: str | None = None) -> tuple[int, ...]:
    """All mutation operations execute inside the locked mutation transaction, after the
    pre-transaction and locked-phase preconditions have all passed; the locked mutation transaction
    makes no Apple or Google network call and retries no provider request while holding restore
    mutation locks."""
    # [impl->req~restore-adoption-mutation-inside-locked-transaction~1]
    if not ledger.holds_locks:
        raise AdoptionError("adoption mutates inside the locked mutation transaction")
    assert_no_provider_calls(ledger, provider_call)
    missing = sorted(set(ADOPTION_PRECONDITION_NUMBERS) - set(preconditions_passed))
    if missing:
        raise AdoptionError(f"adoption preconditions {missing} have not passed")
    return ADOPTION_PRECONDITION_NUMBERS


@dataclass(frozen=True, slots=True)
class CanonicalRowWrite:
    """What rule 1 wrote to `core.subscriptions`: an in-place attach, or a creation."""
    operation: str
    subscription_id: UUID | None
    provider: StoreProvider
    external_id: str
    user_id: UUID
    status: SubscriptionStatus
    tier_id: str


ATTACH: str = "attach_in_place"
CREATE: str = "create_from_store_verified_data"


def mutation_01_attach_or_create_canonical_row(state: LockedState,
                                               verified: VerifiedTransaction,
                                               *,
                                               destination_user_id: UUID,
                                               adoption_with_creation: bool,
                                               live_verified_status: SubscriptionStatus | None = None,
                                               store_product_id: str | None = None,
                                               product_tier_mapping: Mapping[str, str] | None = None,
                                               source_user_id: UUID | None = None
                                               ) -> CanonicalRowWrite:
    """1. Attach the unclaimed store subscription to the destination user by updating the canonical
    row in place — `user_id` set to the destination, `status` and `tier_id` left at the current
    product-entitled state — or, on the adoption-with-creation path, by creating that row in this
    transaction from the store-verified data under the `(provider, external_id)` uniqueness, linked
    to the destination user, with `status` at the live-verified store state and `tier_id` resolved
    from the server-controlled store-product-ID-to-tier mapping.

    This first linkage is the adoption; it is not a transfer, and no source user exists.
    """
    # [impl->req~restore-adoption-mutation-01-attach-or-create-canonical-row~1]
    if source_user_id is not ADOPTION_SOURCE_USER_ID:
        raise AdoptionError("the first linkage is no transfer: adoption has no source user")
    row = state.subscription.row
    if adoption_with_creation:
        if row is not None:
            raise AdoptionError("a row that appeared under the serialization is attached, not created")
        if live_verified_status is None:
            raise AdoptionError("the created row carries the live-verified store state")
        if not store_product_id or not product_tier_mapping:
            raise AdoptionError("the created row's tier comes from the server-controlled mapping")
        tier_id = product_tier_mapping.get(store_product_id)
        if tier_id is None:
            raise AdoptionError(f"{store_product_id} maps to no tier in the server-controlled map")
        return CanonicalRowWrite(operation=CREATE, subscription_id=None,
                                 provider=verified.provider, external_id=verified.external_id,
                                 user_id=destination_user_id, status=live_verified_status,
                                 tier_id=tier_id)
    if row is None:
        raise AdoptionError("an in-place attach needs the canonical row it attaches")
    if row.user_id is not None:
        raise AdoptionError("only an unclaimed canonical row is attached")
    return CanonicalRowWrite(operation=ATTACH, subscription_id=row.subscription_id,
                             provider=row.provider, external_id=row.external_id,
                             user_id=destination_user_id, status=row.status, tier_id=row.tier_id)


@dataclass(frozen=True, slots=True)
class GrantAndUsage:
    """The subscription-backed grant adoption created, and its monthly usage row."""
    grant_id: UUID
    user_id: UUID
    tier_id: str
    subscription_id: UUID
    usage_grant_id: UUID


def mutation_02_create_grant_and_usage(*,
                                       destination_user_id: UUID,
                                       subscription_id: UUID,
                                       tier_id: str,
                                       grant_id: UUID,
                                       subscription_transaction: object,
                                       grant_transaction: object,
                                       usage_transaction: object,
                                       mutations: RestoreGrantMutations,
                                       destination_active_grant_ids: Sequence[UUID] = ()
                                       ) -> GrantAndUsage:
    """2. Create the subscription-backed `core.access_grants` row for the destination user at the
    subscription's current `tier_id`, linked to the canonical subscription, together with its
    `core.user_monthly_usage` row, in this same transaction — so the invariant that the canonical
    `core.subscriptions.user_id` equals the subscription-backed `core.access_grants.user_id` holds
    at commit.

    The destination held no different active grant under locked-phase precondition 3, so the
    grant-activating statement runs against a grant-free destination under the restore
    grant-mutation ordering.
    """
    # [impl->req~restore-adoption-mutation-02-create-grant-and-usage~1]
    if (subscription_transaction is not grant_transaction
            or grant_transaction is not usage_transaction):
        raise AdoptionError("the canonical row, the grant and the usage row commit together")
    if sorted(set(destination_active_grant_ids)):
        raise AdoptionError("the grant-activating statement runs against a grant-free destination")
    try:
        assert_owner_agreement(grant_user_id=destination_user_id,
                               subscription_user_id=destination_user_id)
    except InvariantError:  # pragma: no cover - the destination is one user
        raise AdoptionError("the created grant and its subscription share one owner") from None
    mutations.activate(grant_id)
    assert_stays_with_grant(stored_grant_id=grant_id, row_grant_id=grant_id)
    return GrantAndUsage(grant_id=grant_id, user_id=destination_user_id, tier_id=tier_id,
                         subscription_id=subscription_id, usage_grant_id=grant_id)


def mutation_03_grant_active_only_if_verified(*,
                                              locked_status: SubscriptionStatus,
                                              verification: LiveStoreVerification | None,
                                              recheck_passed: bool,
                                              starts_at: datetime,
                                              now: datetime,
                                              ends_at: datetime | None = None
                                              ) -> AccessGrantStatus:
    """3. The created subscription-backed grant has `status = 'active'`, `starts_at <= now` and
    `ends_at IS NULL` only because the current subscription state was confirmed product-entitled
    inside the locked mutation transaction and the recorded pre-transaction live verification was
    confirmed fresh and store-subscription-corresponding."""
    # [impl->req~restore-adoption-mutation-03-grant-active-only-if-verified~1]
    assert_product_entitled(locked_status)
    if verification is None or not recheck_passed:
        raise RestoreRejection(
            AuthEventResult.restore_store_state_unverified,
            "no confirmed live verification stands behind an active subscription-backed grant")
    if starts_at > now:
        raise AdoptionError("the created grant starts at or before now")
    if ends_at is not None:
        raise AdoptionError("the created grant carries no end")
    return AccessGrantStatus.active


def mutation_04_never_mutate_existing_active_grant(*,
                                                   existing_active_grant_id: UUID | None = None,
                                                   attempted: Iterable[str] = ()) -> None:
    """4. Never expire, replace, revoke or otherwise mutate any existing active grant on the
    destination; that condition is rejected above by locked-phase precondition 3 and never reaches
    mutation."""
    # [impl->req~restore-adoption-mutation-04-never-mutate-existing-active-grant~1]
    offending = sorted((set(attempted) | EXISTING_ACTIVE_GRANT_MUTATIONS) & GRANT_MUTATION_VERBS)
    if offending:
        raise AdoptionError(f"adoption mutation does not {offending} an existing active grant")
    if existing_active_grant_id is not None:
        raise AdoptionError(
            "an existing active grant is rejected by precondition 3 and never reaches mutation")


# Everything adoption leaves alone. It attaches only paid subscription entitlement.
NON_SUBSCRIPTION_DATA: frozenset[str] = frozenset({
    "chats", "messages", "external_identities", "profile_fields", "anonymous_device_grants",
    "manual_grants", "non_subscription_user_monthly_usage",
})


def mutation_05_no_non_subscription_data_moved(touched: Iterable[str] = ()) -> frozenset[str]:
    """5. Do not move, mutate or rebind chats, messages, external identities, profile fields,
    anonymous device grants, manual grants, or any non-subscription `core.user_monthly_usage` rows
    belonging to any user. Adoption attaches only paid subscription entitlement."""
    # [impl->req~restore-adoption-mutation-05-no-non-subscription-data-moved~1]
    offending = sorted(set(touched) & NON_SUBSCRIPTION_DATA)
    if offending:
        raise AdoptionError(f"adoption moves, mutates or rebinds no {offending}")
    return NON_SUBSCRIPTION_DATA


def mutation_06_purchase_row_insert_once_only(*,
                                              purchase_row: PurchaseRow | None,
                                              verified: VerifiedTransaction,
                                              destination_user_id: UUID,
                                              adoption_with_creation: bool,
                                              operation: str = PURCHASE_ROW_INSERT_ONCE,
                                              store_transaction_id: str | None = None,
                                              store_original_transaction_id: str | None = None
                                              ) -> PurchaseRowInsert | None:
    """6. Beyond the adoption-with-creation path's insert-once creation of a missing
    `core.store_purchases` row — written from the store-verified data with the store transaction
    identifiers, the echoed purchase UUID or a server-generated internal purchase UUID where the
    verified transaction carries none, and the destination user as `purchase_user_id` — do not
    insert, update or revoke any `core.store_purchases` row.

    Every row remains immutable once written: the rows preserve purchase-event history, and current
    ownership lives only in the canonical `core.subscriptions` row.
    """
    # [impl->req~restore-adoption-mutation-06-purchase-row-insert-once-only~1]
    if operation != PURCHASE_ROW_INSERT_ONCE:
        raise AdoptionError(f"{operation} is no permitted adoption purchase-row write")
    if purchase_row is not None:
        return None
    if not adoption_with_creation:
        raise AdoptionError("only the adoption-with-creation path creates the missing row")
    assert_purchase_row_immutable(purchase_row=None, operation=operation,
                                  branch=RestoreBranch.adoption)
    return PurchaseRowInsert(provider=verified.provider,
                             external_id=verified.external_id,
                             identity_value=internal_purchase_uuid(verified),
                             purchase_user_id=destination_user_id,
                             store_transaction_id=store_transaction_id,
                             store_original_transaction_id=store_original_transaction_id)


# The one grant source adoption writes, and the sources it never allocates.
ADOPTION_GRANT_SOURCE: AccessGrantSource = AccessGrantSource.subscription
FREE_OR_MANUAL_SOURCES: frozenset[AccessGrantSource] = frozenset({
    AccessGrantSource.anonymous_device_grant,
    AccessGrantSource.registered_account_grant,
    AccessGrantSource.manual,
})


def mutation_07_no_free_or_manual_grant(allocated: Iterable[AccessGrantSource] = ()
                                        ) -> AccessGrantSource:
    """7. Do not allocate any anonymous device-based free-credit grant or manual grant."""
    # [impl->req~restore-adoption-mutation-07-no-free-or-manual-grant~1]
    offending = sorted(str(source) for source in set(allocated) & FREE_OR_MANUAL_SOURCES)
    if offending:
        raise AdoptionError(f"adoption allocates no {offending} grant")
    return ADOPTION_GRANT_SOURCE


# Writes adoption never makes to `core.external_identities`.
EXTERNAL_IDENTITY_WRITES: frozenset[str] = frozenset({
    "retire", "mark_historical", "update", "delete", "rebind",
})


def mutation_08_no_external_identity_mutation(attempted: Iterable[str] = ()) -> None:
    """8. Do not retire, mark `historical`, or otherwise mutate any `core.external_identities`
    row."""
    # [impl->req~restore-adoption-mutation-08-no-external-identity-mutation~1]
    offending = sorted(set(attempted) & EXTERNAL_IDENTITY_WRITES)
    if offending:
        raise AdoptionError(f"adoption performs no core.external_identities {offending}")


# Restore holds no challenge, so no challenge material may appear on the row.
CHALLENGE_DETAIL_KEYS: frozenset[str] = frozenset({
    "challenge_id", "challenge_row_id", "challenge_nonce", "challenge_material",
})


def mutation_09_audit_row_details(*,
                                  result: AuthEventResult,
                                  operation: AuthOperation,
                                  destination_user_id: UUID,
                                  destination_external_identity_id: UUID,
                                  subscription_id: UUID,
                                  grant_id: UUID,
                                  provider: StoreProvider,
                                  external_id: str,
                                  purchase_row_id: UUID,
                                  verification: Mapping[str, Any],
                                  proof_fingerprints: Iterable[str] = (),
                                  source_user_id: UUID | None = None,
                                  challenge_row_id: UUID | None = None) -> dict[str, Any]:
    """9. Append the single `audit.auth_events` row with `result = 'succeeded'`,
    `operation = 'restore_subscription'`, and `details` carrying
    `movement_classification = 'adoption'`, a `NULL` source user, the resolved purchase row,
    destination user and external identity, the resolved `(provider, external_id)` store
    subscription identifiers, the canonical `core.subscriptions.id`, `grant_id`, non-secret proof
    fingerprints, and the live-verification outcome.

    Restore holds no challenge, so the row's `challenge_row_id` is `NULL` and no challenge material
    appears in `details`, audit or logs.
    """
    # [impl->req~restore-adoption-mutation-09-audit-row-details~1]
    if result is not AuthEventResult.succeeded:
        raise AdoptionError("a successful adoption audits as succeeded")
    if operation is not AuthOperation.restore_subscription:
        raise AdoptionError(f"{operation} is not restore_subscription")
    if source_user_id is not ADOPTION_SOURCE_USER_ID:
        raise AdoptionError("adoption records a NULL source user")
    if challenge_row_id is not None:
        raise AdoptionError("restore holds no challenge, so challenge_row_id is NULL")
    leaked = sorted(set(verification) & CHALLENGE_DETAIL_KEYS)
    if leaked:
        raise AdoptionError(f"no challenge material appears in details: {leaked}")
    details = movement_details(
        movement_classification=str(MovementClassification.adoption),
        source_user_id=ADOPTION_SOURCE_USER_ID,
        destination_user_id=destination_user_id,
        destination_external_identity_id=destination_external_identity_id,
        subscription_id=subscription_id,
        access_grant_id=grant_id,
        store_purchase_id=purchase_row_id,
        proof_fingerprints=list(proof_fingerprints),
        store_state_verification=dict(verification))
    details["mutation"]["provider"] = str(provider)
    details["mutation"]["external_id"] = external_id
    return details


# --- Postconditions -------------------------------------------------------------------------------


def postcondition_owner_binding_grant(*,
                                      canonical_user_id: UUID | None,
                                      restore_bound_user_id: UUID | None,
                                      grant_user_id: UUID | None,
                                      destination_user_id: UUID) -> UUID:
    """The canonical `core.subscriptions` row for the store subscription now has the destination
    user as `user_id`, the lifetime store-transaction binding set, and the subscription-backed
    `core.access_grants.user_id` equal to that destination user."""
    # [impl->req~restore-adoption-postcondition-owner-binding-grant~1]
    if canonical_user_id != destination_user_id:
        raise AdoptionError("the canonical row now names the destination user as its owner")
    if restore_bound_user_id != destination_user_id:
        raise AdoptionError("the lifetime store-transaction binding is set to the destination")
    assert_owner_agreement(grant_user_id=grant_user_id,
                           subscription_user_id=canonical_user_id)
    return destination_user_id


def postcondition_entitlement_follows_destination(*,
                                                  destination_user_id: UUID,
                                                  requester_user_id: UUID,
                                                  requester_holds_grant: bool = False
                                                  ) -> RestoreBranch:
    """Paid subscription entitlement now follows the destination user and only the destination
    user: a later restore of this transaction is same-account for the destination and
    `store_transaction_already_linked` for anyone else."""
    # [impl->req~restore-adoption-postcondition-entitlement-follows-destination~1]
    if requester_user_id == destination_user_id:
        return RestoreBranch.same_account
    if requester_holds_grant:
        raise AdoptionError("the entitlement follows the destination user and only that user")
    raise RestoreRejection(AuthEventResult.store_transaction_already_linked,
                           "this store transaction is already linked to another account")


def postcondition_purchase_row_immutable(*,
                                         before: PurchaseRow,
                                         after: PurchaseRow) -> UUID | None:
    """The resolved `core.store_purchases` row remains immutable and continues to identify the
    token-bound purchase user via `purchase_user_id` where one was recorded."""
    # [impl->req~restore-adoption-postcondition-purchase-row-immutable~1]
    if after != before:
        raise AdoptionError("the resolved core.store_purchases row remains immutable")
    return after.purchase_user_id
