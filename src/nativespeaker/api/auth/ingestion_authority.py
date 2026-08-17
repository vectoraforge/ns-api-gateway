"""What a verified store notification is allowed to do.

A verified notification carries the store's authority over entitlement and nothing more. It may
move the canonical `core.subscriptions` row for its own `(provider, external_id)` store
subscription, append the observation to `audit.subscription_events`, and settle the corresponding
subscription-backed grant. It may act only on the account that store subscription is already
linked to, it creates no session, user or identity, and an attribution token matching no account
leaves the store subscription unclaimed for restore's adoption branch to pick up later.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.invariants import AttributionTokens, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation, match_operation, route_for
from nativespeaker.api.auth.routes import ID_TOKEN_REQUIRED_ROUTES, PROVIDER_CALLBACK_ROUTES


class IngestionAuthorityError(RuntimeError):
    """An ingestion handler was about to exceed the authority a store notification carries."""


class IngestionEffect(StrEnum):
    """The whole of what a verified notification may cause."""
    update_canonical_subscription = "update_canonical_subscription"
    append_subscription_event = "append_subscription_event"
    update_subscription_grant = "update_subscription_grant"


# The three tables those effects touch, and nothing else.
INGESTION_WRITES: Mapping[IngestionEffect, str] = {
    IngestionEffect.update_canonical_subscription: "core.subscriptions",
    IngestionEffect.append_subscription_event: "audit.subscription_events",
    IngestionEffect.update_subscription_grant: "core.access_grants",
}

# Effects that lie outside the store's authority over entitlement: a session, a token minted or
# issued for a user, a `core.users` or `core.external_identities` row, or any other privilege.
IDENTITY_AND_SESSION_EFFECTS: frozenset[str] = frozenset({
    "create_session", "create_refresh_session", "mint_token", "issue_token",
    "mint_custom_token", "issue_id_token", "create_user_row", "create_external_identity_row",
    "link_external_identity", "grant_privilege", "grant_admin_role", "issue_free_grant",
    "issue_manual_grant",
})


def assert_ingestion_authority(effects: Iterable[str]) -> tuple[IngestionEffect, ...]:
    """A verified notification carries the store's authority over entitlement and nothing more.

    Every effect an ingestion handler claims is checked against that authority here: the three
    entitlement effects are the whole of it, and anything else is refused before it is applied.
    """
    # [impl->req~restore-ingestion-authority-entitlement-only~1]
    claimed = list(effects)
    assert_no_identity_or_session_effect(claimed)
    permitted = {str(effect) for effect in IngestionEffect}
    beyond = sorted(name for name in set(claimed) if name not in permitted)
    if beyond:
        raise IngestionAuthorityError(
            f"a verified notification carries no authority over {beyond}")
    return tuple(IngestionEffect(name) for name in claimed)


def permitted_ingestion_write(effect: IngestionEffect) -> str:
    """It may update the canonical `core.subscriptions` row for its own `(provider, external_id)`
    store subscription, append that observation to `audit.subscription_events`, and update the
    corresponding subscription-backed `core.access_grants` row."""
    # [impl->req~restore-ingestion-may-update-subscription-and-grant~1]
    table = INGESTION_WRITES.get(effect)
    if table is None:
        raise IngestionAuthorityError(f"{effect} writes no table under ingestion authority")
    return table


def assert_ingestion_scope(effect: IngestionEffect,
                           *,
                           notification_key: tuple[StoreProvider, str],
                           row_key: tuple[StoreProvider, str]) -> str:
    """The canonical row a notification may move is the one for its own store subscription. A
    notification for one `(provider, external_id)` never writes another's row."""
    # [impl->req~restore-ingestion-may-update-subscription-and-grant~1]
    if notification_key != row_key:
        raise IngestionAuthorityError(
            f"a notification for {notification_key} does not write {row_key}")
    return permitted_ingestion_write(effect)


def assert_no_identity_or_session_effect(effects: Iterable[str]) -> None:
    """It never creates a session, mints or issues any token for a user, creates a `core.users` or
    `core.external_identities` row, or grants any privilege beyond the entitlement effect of the
    store event."""
    # [impl->req~restore-ingestion-never-creates-session-or-identity~1]
    offending = sorted(set(effects) & IDENTITY_AND_SESSION_EFFECTS)
    if offending:
        raise IngestionAuthorityError(f"store ingestion never performs {offending}")


# --- The account a notification may act on ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LinkedAccount:
    """The account the store subscription is already linked to, and how that link was found."""
    user_id: UUID | None
    resolved_by: str | None = None


# The two ways a store subscription is already linked to an account, and the only two.
LINK_SOURCES: tuple[str, ...] = ("store_purchase_tokens", "canonical_subscription_user_id")


def ingestion_target_user(*,
                          provider: StoreProvider,
                          echoed_token: str | None,
                          tokens: AttributionTokens,
                          canonical_user_id: UUID | None) -> LinkedAccount:
    """A notification may act only on the account the store subscription is already linked to.

    That is the account the echoed attribution token resolves to through
    `core.store_purchase_tokens` by `(provider, identity_value)`, or the current `user_id` on the
    canonical row. No other account is reachable: the notification never nominates a user, and a
    token that resolves to nobody does not fall back to any account.
    """
    # [impl->req~restore-ingestion-acts-only-on-linked-account~1]
    resolved = tokens.owner_of(provider, echoed_token) if echoed_token else None
    if resolved is not None:
        return LinkedAccount(user_id=resolved, resolved_by=LINK_SOURCES[0])
    if canonical_user_id is not None:
        return LinkedAccount(user_id=canonical_user_id, resolved_by=LINK_SOURCES[1])
    return LinkedAccount(user_id=None, resolved_by=None)


def assert_acts_on_linked_account(target: LinkedAccount, acting_on: UUID | None) -> UUID | None:
    """The account an ingestion handler actually writes is the linked account it resolved, and no
    other."""
    # [impl->req~restore-ingestion-acts-only-on-linked-account~1]
    if acting_on is not None and acting_on != target.user_id:
        raise IngestionAuthorityError(
            f"ingestion acts on {target.user_id}, the linked account, not {acting_on}")
    return target.user_id


# --- An unmatched token leaves the subscription unclaimed ---------------------------------------


@dataclass(frozen=True, slots=True)
class UnclaimedIngestion:
    """The shape a verified but unattributed notification leaves behind: the canonical row unowned
    and no subscription-backed grant — exactly what an unattributed verified purchase records."""
    user_id: None = None
    subscription_grant_id: None = None
    claimed_by: AuthOperation = AuthOperation.restore_subscription


def unmatched_token_outcome(target: LinkedAccount) -> UnclaimedIngestion | UUID:
    """A verified notification whose echoed attribution token matches no account leaves the store
    subscription unclaimed — the canonical row unowned with `user_id` NULL and no
    subscription-backed grant.

    An account claims it later by presenting that transaction to
    `POST /auth/restore-subscription`, whose adoption of an unclaimed subscription is what links
    it. Ingestion itself links nothing here.
    """
    # [impl->req~restore-ingestion-unmatched-token-leaves-unclaimed~1]
    if target.user_id is not None:
        return target.user_id
    outcome = UnclaimedIngestion()
    if route_for(outcome.claimed_by) != CLIENT_EVIDENCE_ROUTE:
        raise IngestionAuthorityError("an unclaimed subscription is claimed through restore")
    return outcome


# --- Client-submitted evidence never arrives here -----------------------------------------------


# The two ingestion routes, read from the registry that owns the list.
INGESTION_ROUTES: frozenset[tuple[str, str]] = frozenset(
    (route.method, route.path) for route in PROVIDER_CALLBACK_ROUTES)

# Purchase evidence a signed-in client might submit. It has its own route, and it is not one of
# these.
CLIENT_SUBMITTED_EVIDENCE: frozenset[str] = frozenset({
    "restore_proof", "receipt", "receipt_data", "purchase_token", "signed_transaction",
    "transaction_receipt", "store_proof",
})

# Where a signed-in user submits it instead: an ordinary Firebase-barrier route.
CLIENT_EVIDENCE_ROUTE: tuple[str, str] = route_for(AuthOperation.restore_subscription)


def assert_no_client_submitted_evidence(method: str, path: str,
                                        body: Mapping[str, Any] | None = None) -> None:
    """Client-submitted purchase evidence never arrives on the ingestion routes.

    A signed-in user submitting a receipt or a purchase token uses
    `POST /auth/restore-subscription`, an ordinary Firebase-barrier route keyed to the verified
    subject: the store evidence in that request does not replace the Firebase ID token, and the
    Firebase ID token does not excuse verifying that evidence with the store before any mutation.
    """
    # [impl->req~restore-ingestion-no-client-submitted-evidence~1]
    key = (method.upper(), path)
    if key not in INGESTION_ROUTES:
        raise IngestionAuthorityError(f"{method} {path} is no store ingestion route")
    submitted = sorted(set(body or {}) & CLIENT_SUBMITTED_EVIDENCE)
    if submitted:
        raise IngestionAuthorityError(
            f"{submitted} is submitted to {CLIENT_EVIDENCE_ROUTE[0]} {CLIENT_EVIDENCE_ROUTE[1]}")


def assert_restore_route_keeps_both_checks(*,
                                           id_token_verified: bool,
                                           store_evidence_verified: bool) -> tuple[str, str]:
    """`POST /auth/restore-subscription` requires both: the Firebase ID token the barrier verifies
    and the store evidence the backend verifies with the store before any mutation. Neither
    excuses the other."""
    # [impl->req~restore-ingestion-no-client-submitted-evidence~1]
    if CLIENT_EVIDENCE_ROUTE not in ID_TOKEN_REQUIRED_ROUTES:
        raise IngestionAuthorityError(f"{CLIENT_EVIDENCE_ROUTE} is a Firebase-barrier route")
    if match_operation(*CLIENT_EVIDENCE_ROUTE) is not AuthOperation.restore_subscription:
        raise IngestionAuthorityError("client purchase evidence goes to restore_subscription")
    if not id_token_verified:
        raise IngestionAuthorityError("store evidence does not replace the Firebase ID token")
    if not store_evidence_verified:
        raise IngestionAuthorityError(
            "the Firebase ID token does not excuse verifying the evidence with the store")
    return CLIENT_EVIDENCE_ROUTE


def ingestion_routes_carry_no_id_token(routes: Sequence[tuple[str, str]] = ()) -> tuple[
        tuple[str, str], ...]:
    """The ingestion routes are not Firebase-barrier routes: no client ID token reaches them, so
    no signed-in user submits evidence through one."""
    # [impl->req~restore-ingestion-no-client-submitted-evidence~1]
    checked = tuple(routes) or tuple(sorted(INGESTION_ROUTES))
    for route in checked:
        if (route[0].upper(), route[1]) in ID_TOKEN_REQUIRED_ROUTES:
            raise IngestionAuthorityError(f"{route} carries no Firebase ID token")
    return checked
