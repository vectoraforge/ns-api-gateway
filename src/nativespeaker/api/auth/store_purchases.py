"""Two tables, two different semantics, and the purchase flow that fills them.

`core.subscriptions` holds the canonical current state of each `(provider, external_id)` paid store
subscription as exactly one row, updated in place. `core.store_purchases` records the durable
attribution between a verified store subscription and the token it was purchased under, one row per
accepted store subscription, written once. The echoed UUID a store carries is evidence about that
attribution — never an active user identity that selects current subscription ownership.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.invariants import AttributionTokens, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation, match_operation
from nativespeaker.api.auth.restore import RestoreContractError
from nativespeaker.api.auth.restore_flow import (
    PurchaseRow,
    SubscriptionRow,
    VerifiedTransaction,
)
from nativespeaker.api.auth.routes import (
    ID_TOKEN_REQUIRED_ROUTES,
    PROVIDER_CALLBACK_ROUTES,
    named_verifier,
)
from nativespeaker.api.models import SubscriptionStatus
from nativespeaker.api.quota.usage import NewUsageRow, new_usage_row


class StorePurchaseError(RuntimeError):
    """A rule about the two purchase tables was about to be broken."""


# --- Two tables, different semantics ---------------------------------------------------------------


class TableMutability(StrEnum):
    updated_in_place = "updated_in_place"
    insert_once = "insert_once"


@dataclass(frozen=True, slots=True)
class TableSemantics:
    """What one of the two tables is for: the question it answers, the key it is one row per, and
    whether that row is rewritten or written once."""
    table: str
    answers: str
    keyed_by: tuple[str, str]
    mutability: TableMutability
    history_in: str


SUBSCRIPTIONS = TableSemantics(
    table="core.subscriptions",
    answers="what is the current state of this store subscription?",
    keyed_by=("provider", "external_id"),
    mutability=TableMutability.updated_in_place,
    history_in="audit.subscription_events")

STORE_PURCHASES = TableSemantics(
    table="core.store_purchases",
    answers=("which attribution token was this store subscription purchased under, "
             "and which user did that token bind to?"),
    keyed_by=("provider", "external_id"),
    mutability=TableMutability.insert_once,
    history_in="the store itself")

TABLE_SEMANTICS: dict[str, TableSemantics] = {
    SUBSCRIPTIONS.table: SUBSCRIPTIONS,
    STORE_PURCHASES.table: STORE_PURCHASES,
}


def table_semantics(table: str) -> TableSemantics:
    """The backend keeps subscription state and store purchase attribution in two separate tables
    with different semantics. Neither answers the other's question, and neither is rewritten the
    other's way."""
    # [impl->req~restore-two-tables-different-semantics~1]
    if SUBSCRIPTIONS.mutability is STORE_PURCHASES.mutability:
        raise StorePurchaseError("the two tables do not share one mutability")
    if SUBSCRIPTIONS.answers == STORE_PURCHASES.answers:
        raise StorePurchaseError("the two tables answer different questions")
    if table not in TABLE_SEMANTICS:
        raise StorePurchaseError(f"{table} is neither subscription state nor purchase attribution")
    return TABLE_SEMANTICS[table]


# --- `core.subscriptions`: the canonical current state ---------------------------------------------

# The transitions that update the same canonical row in place rather than inserting a second row for
# another state of the same store subscription.
IN_PLACE_TRANSITIONS: frozenset[str] = frozenset({
    "renewal", "grace_period", "billing_retry", "expiration", "revocation", "tier_change",
    "restore_owner_change",
})

# The current values of a store subscription are the ones on that row, and nowhere else.
CANONICAL_FIELDS: tuple[str, ...] = ("user_id", "status", "tier_id")


def upsert_canonical_subscription(rows: Sequence[SubscriptionRow],
                                  *,
                                  provider: StoreProvider,
                                  external_id: str,
                                  status: SubscriptionStatus,
                                  tier_id: str,
                                  user_id: UUID | None,
                                  transition: str | None = None,
                                  now: datetime | None = None) -> SubscriptionRow:
    """`core.subscriptions` holds the canonical current state of each `(provider, external_id)` paid
    store subscription as exactly one row, updated in place across renewals, grace-period and
    billing-retry transitions, expirations, revocations, tier changes and restore-driven owner
    changes. The append-only history of accepted provider state observations is recorded separately
    in `audit.subscription_events`."""
    # [impl->req~restore-subscriptions-canonical-current-state~1]
    del now
    if transition is not None and transition not in IN_PLACE_TRANSITIONS:
        raise StorePurchaseError(f"{transition} is no in-place canonical-row transition")
    matches = [row for row in rows if row.key == (provider, external_id)]
    if len(matches) > 1:
        raise StorePurchaseError(
            f"{(provider, external_id)} is exactly one row, never a second state")
    if matches:
        existing = matches[0]
        # Updated in place: the same row keeps its identity across every transition above.
        return SubscriptionRow(subscription_id=existing.subscription_id,
                               provider=provider,
                               external_id=external_id,
                               status=status,
                               tier_id=tier_id,
                               user_id=user_id,
                               restore_bound_user_id=existing.restore_bound_user_id)
    return SubscriptionRow(subscription_id=uuid4(), provider=provider, external_id=external_id,
                           status=status, tier_id=tier_id, user_id=user_id)


def current_state(row: SubscriptionRow) -> dict[str, Any]:
    """The current `user_id`, `status` and `tier_id` for a store subscription are the values on the
    canonical row."""
    # [impl->req~restore-subscriptions-canonical-current-state~1]
    return {name: getattr(row, name) for name in CANONICAL_FIELDS}


# --- `core.store_purchases`: the attribution table --------------------------------------------------

# The purchase-attribution field each store determines. There is no separate identity-kind
# dimension anywhere in this table.
ATTRIBUTION_FIELD: dict[StoreProvider, str] = {
    StoreProvider.apple: "appAccountToken",
    StoreProvider.google_play: "obfuscatedExternalAccountId",
}
IDENTITY_KIND_DIMENSION: frozenset[str] = frozenset()


def attribution_field(provider: StoreProvider) -> str:
    """Store provider determines which purchase-attribution field is expected: Apple uses
    `appAccountToken`, Google Play the obfuscated external account ID."""
    # [impl->req~restore-store-purchases-attribution-table~1]
    if IDENTITY_KIND_DIMENSION:
        raise StorePurchaseError("there is no separate identity-kind dimension")
    return ATTRIBUTION_FIELD[provider]


def build_purchase_row(*,
                       provider: StoreProvider,
                       external_id: str,
                       identity_value: str,
                       purchase_user_id: UUID | None,
                       store_transaction_id: str | None = None,
                       store_original_transaction_id: str | None = None,
                       existing: Sequence[PurchaseRow] = ()) -> PurchaseRow:
    """One row per accepted `(provider, external_id)` store subscription: the store provider, the
    attribution token value the client passed into that store's SDK — or the server-generated
    internal purchase UUID recorded in its place — the store transaction identifiers when available,
    the `core.users.id` the attribution resolved to where one did, and the store subscription the
    purchase produced.

    This is a purchase-attribution table, not a separate audit row per lifecycle event: the store
    itself remains the source of lifecycle history.
    """
    # [impl->req~restore-store-purchases-attribution-table~1]
    if any(row.key == (provider, external_id) for row in existing):
        raise StorePurchaseError(
            f"{(provider, external_id)} already holds its one purchase-attribution row")
    del store_transaction_id, store_original_transaction_id
    attribution_field(provider)
    return PurchaseRow(purchase_id=uuid4(), provider=provider, external_id=external_id,
                       identity_value=identity_value, purchase_user_id=purchase_user_id)


# --- The echoed UUID is evidence, not identity ------------------------------------------------------

# What may select current subscription ownership: the canonical row's own `user_id`. The echoed
# UUID and the purchase row's `purchase_user_id` are not among them.
OWNERSHIP_SELECTORS: tuple[str, ...] = ("core.subscriptions.user_id",)
NON_SELECTORS: frozenset[str] = frozenset({
    "echoed_uuid", "identity_value", "purchase_user_id", "app_account_token",
    "obfuscated_external_account_id",
})

# What restore does to a purchase row: resolve it, verify a carried UUID against it, or create the
# missing one once. Never reassign it.
PURCHASE_ROW_REASSIGNMENTS: frozenset[str] = frozenset()


def assert_not_an_ownership_selector(name: str) -> None:
    """The echoed UUID value is store-carried purchase evidence, not an active user identity that
    selects current subscription ownership."""
    # [impl->req~restore-echoed-uuid-is-evidence-not-identity~1]
    if PURCHASE_ROW_REASSIGNMENTS:
        raise StorePurchaseError("core.store_purchases rows are never reassigned during restore")
    if name in NON_SELECTORS:
        raise StorePurchaseError(f"{name} is purchase evidence, not the current owner")
    if name not in OWNERSHIP_SELECTORS:
        raise StorePurchaseError(f"{name} selects no subscription ownership")


def resolve_or_create_purchase_row(rows: Sequence[PurchaseRow],
                                  verified: VerifiedTransaction,
                                  *,
                                  destination_user_id: UUID | None = None) -> PurchaseRow:
    """Restore resolves the row for the verified store subscription by `(provider, external_id)`,
    verifies any carried purchase UUID against its recorded `identity_value`, and creates the missing
    row once, from store-verified data, where none exists."""
    # [impl->req~restore-echoed-uuid-is-evidence-not-identity~1]
    matches = [row for row in rows if row.key == verified.key]
    if matches:
        row = matches[0]
        carried = verified.carried_purchase_uuid
        if carried is not None and carried != row.identity_value:
            raise StorePurchaseError("the carried purchase UUID is not this row's attribution")
        return row
    identity_value = verified.carried_purchase_uuid or str(uuid4())
    return build_purchase_row(provider=verified.provider,
                              external_id=verified.external_id,
                              identity_value=identity_value,
                              purchase_user_id=destination_user_id,
                              existing=rows)


# --- The purchase flow -----------------------------------------------------------------------------

# Step 2: the client slot each store's attribution value is passed into at purchase initiation.
PURCHASE_INITIATION_SLOT: dict[StoreProvider, str] = {
    StoreProvider.apple: "StoreKit.Product.PurchaseOption.appAccountToken",
    StoreProvider.google_play: "BillingFlowParams.Builder.setObfuscatedAccountId",
}


def purchase_initiation_slot(provider: StoreProvider) -> str:
    """Step 2: the iOS client passes the returned `appAccountToken` value into the StoreKit purchase
    API; the Android client passes the returned `obfuscated_external_account_id` value into Google
    Play Billing's obfuscated account ID slot."""
    # [impl->req~restore-purchase-flow-02-client-passes-token-to-store~1]
    return PURCHASE_INITIATION_SLOT[provider]


# Step 3: where each store reports the value back on the verified purchase.
STORE_ECHO_FIELD: dict[StoreProvider, str] = {
    StoreProvider.apple: "appAccountToken",
    StoreProvider.google_play: "obfuscatedExternalAccountId",
}


def store_echoed_token(provider: StoreProvider,
                       verified_purchase: Mapping[str, Any]) -> str | None:
    """Step 3: Apple records that `appAccountToken` value inside the signed transaction it later
    returns for the purchase; Google Play records it as the purchase's obfuscated external account
    ID, returned with the verified Google Play purchase. A store-initiated transaction carries
    none."""
    # [impl->req~restore-purchase-flow-03-store-records-token~1]
    if STORE_ECHO_FIELD[provider] != attribution_field(provider):
        raise StorePurchaseError("the echoed field is the store's own attribution field")
    value = verified_purchase.get(STORE_ECHO_FIELD[provider])
    return str(value) if value else None


@dataclass(frozen=True, slots=True)
class IngestedPurchase:
    """What one ingestion transaction produced."""
    subscription: SubscriptionRow
    purchase: PurchaseRow
    grant_id: UUID | None
    grant_source: AccessGrantSource | None
    usage_row: NewUsageRow | None
    expired_grant_ids: tuple[UUID, ...] = ()
    resolved_token_value: str | None = None


@dataclass(slots=True)
class IngestionLedger:
    """The statements one ingestion transaction took, in order."""
    statements: list[str] = field(default_factory=list)

    def record(self, statement: str) -> None:
        self.statements.append(statement)


def ingest_verified_purchase(*,
                             provider: StoreProvider,
                             external_id: str,
                             verified_purchase: Mapping[str, Any],
                             tokens: AttributionTokens,
                             product_id: str,
                             product_tier_map: Mapping[str, str],
                             status: SubscriptionStatus,
                             subscriptions: Sequence[SubscriptionRow] = (),
                             purchases: Sequence[PurchaseRow] = (),
                             blocking_grant_ids: Sequence[UUID] = (),
                             transaction: object,
                             ledger: IngestionLedger | None = None,
                             now: datetime | None = None,
                             client_supplied_tier: str | None = None) -> IngestedPurchase:
    """Step 4: resolve the owning user by matching the store-echoed token through
    `core.store_purchase_tokens` by `(provider, identity_value)`, then, in one ingestion
    transaction, upsert the canonical `core.subscriptions` row, write the one immutable
    `core.store_purchases` row, and create the paid entitlement — a `source = 'subscription'`,
    `status = 'active'` grant linked to that canonical row, its tier resolved from the
    server-controlled product-ID-to-tier mapping, together with its `core.user_monthly_usage` row
    seeded `monthly_used = 0`.

    An echoed token resolving to no binding — or a verified purchase carrying no echoed token at
    all, as store-initiated transactions legitimately do — is attributed to no user: the canonical
    row is created unclaimed and the purchase row unattributed, recording a server-generated
    internal purchase UUID where the store supplies no usable echoed value, with no grant and no
    usage row.
    """
    # [impl->req~restore-purchase-flow-04-ingestion-resolves-and-creates~1]
    if client_supplied_tier is not None:
        raise StorePurchaseError("the tier is resolved from the server-controlled mapping")
    steps = ledger or IngestionLedger()
    echoed = store_echoed_token(provider, verified_purchase)
    owner = tokens.owner_of(provider, echoed) if echoed else None
    resolved_token = echoed if owner is not None else None
    tier_id = product_tier_map.get(product_id)
    if tier_id is None:
        raise StorePurchaseError(f"{product_id} maps to no tier")

    steps.record("upsert_subscription")
    subscription = upsert_canonical_subscription(subscriptions, provider=provider,
                                                 external_id=external_id, status=status,
                                                 tier_id=tier_id, user_id=owner, now=now)
    steps.record("insert_store_purchase")
    purchase = build_purchase_row(provider=provider, external_id=external_id,
                                  identity_value=echoed or str(uuid4()),
                                  purchase_user_id=owner, existing=purchases)
    if owner is None:
        # Unclaimed and unattributed: no grant, no usage row. Restore's adoption links it later.
        return IngestedPurchase(subscription=subscription, purchase=purchase, grant_id=None,
                                grant_source=None, usage_row=None, resolved_token_value=None)

    expired = expire_before_insert(blocking_grant_ids, ledger=steps)
    steps.record("insert_subscription_grant")
    grant_id = uuid4()
    usage = new_usage_row(grant_id, now=now, grant_transaction=transaction,
                          usage_transaction=transaction)
    if usage.monthly_used != 0:
        raise StorePurchaseError("a genuinely new paid entitlement starts at zero")
    steps.record("insert_usage_row")
    return IngestedPurchase(subscription=subscription, purchase=purchase, grant_id=grant_id,
                           grant_source=AccessGrantSource.subscription, usage_row=usage,
                           expired_grant_ids=expired, resolved_token_value=resolved_token)


# The reason an expiry is recorded with, so no expiry is a silent side effect.
EXPIRY_REASON: str = "superseded_by_verified_purchase"
GRANT_DELETIONS: frozenset[str] = frozenset()


def expire_before_insert(blocking_grant_ids: Sequence[UUID],
                        *,
                        ledger: IngestionLedger,
                        reason: str = EXPIRY_REASON) -> tuple[UUID, ...]:
    """Step 5: because `ix_access_grants_one_active_per_user` is non-deferrable, expire-then-insert
    order is mandatory. Before the new active grant is inserted, any grant currently blocking the
    index — the buyer's active free grant, or the previously active subscription grant — is expired
    first in its own earlier statement, never deleted, and recorded with a reason.

    When a verified purchase completes for a second, genuinely different subscription while a
    subscription-backed grant is active, the newest verified purchase wins.
    """
    # [impl->req~restore-purchase-flow-05-expire-then-insert-order~1]
    if GRANT_DELETIONS:
        raise StorePurchaseError("a blocking grant is expired, never deleted")
    if not reason:
        raise StorePurchaseError("each expiry is recorded with a reason")
    if "insert_subscription_grant" in ledger.statements:
        raise StorePurchaseError("every blocking grant is expired before the insert")
    expired: list[UUID] = []
    for grant_id in sorted(blocking_grant_ids):
        ledger.record(f"expire_grant:{reason}")
        expired.append(grant_id)
    return tuple(expired)


# The statuses a flipped time-ended grant may take. `ends_at` is never extended in place.
ENDS_AT_EXTENSIONS: frozenset[str] = frozenset()
REACTIVATION_OPERATIONS: tuple[str, ...] = ("verified_purchase_completion", "restore_subscription")


@dataclass(frozen=True, slots=True)
class RenewalOutcome:
    """What a renewal notification produced: the flipped prior term, the new term's grant, or
    neither where the event was a redelivery."""
    flipped_grant_id: UUID | None
    new_grant_id: UUID | None
    idempotent_no_op: bool = False


def renew_per_term(*,
                   active_grant_id: UUID | None,
                   time_ended: bool,
                   already_applied: bool,
                   superseded: bool = False,
                   selecting_operation: str | None = None,
                   extend_ends_at: bool = False) -> RenewalOutcome:
    """Step 6: renewal inserts a new grant row per term through the same flip-then-insert flow used
    for a fresh grant — flip any time-ended active row, then insert the new term's row; the existing
    row's `ends_at` is never extended in place.

    A re-reported or re-verified event for the same term stops as an idempotent no-op before
    touching grant or usage state. After a subscription's grant has been superseded under
    newest-wins, a later notification may update its canonical row but must not silently reactivate
    its grant: that requires an operation which explicitly selects it.
    """
    # [impl->req~restore-purchase-flow-06-renewal-per-term-grant~1]
    if extend_ends_at or ENDS_AT_EXTENSIONS:
        raise StorePurchaseError("a grant's ends_at is never extended in place")
    if already_applied:
        return RenewalOutcome(flipped_grant_id=None, new_grant_id=None, idempotent_no_op=True)
    if superseded and selecting_operation not in REACTIVATION_OPERATIONS:
        return RenewalOutcome(flipped_grant_id=None, new_grant_id=None)
    flipped = active_grant_id if (active_grant_id is not None and time_ended) else None
    return RenewalOutcome(flipped_grant_id=flipped, new_grant_id=uuid4())


def settled_status(*, time_ended: bool) -> AccessGrantStatus:
    """The status a flipped time-ended row takes: `expired`, never deleted."""
    # [impl->req~restore-purchase-flow-06-renewal-per-term-grant~1]
    if not time_ended:
        raise StorePurchaseError("only a time-ended active row is flipped")
    return AccessGrantStatus.expired


# --- Client purchase obligations --------------------------------------------------------------------

# What the client does while the backend has not acknowledged the binding. A missing acknowledgment
# is a hard failure to retry; no new error taxonomy is added for it.
UNACKNOWLEDGED_ACTIONS: tuple[str, ...] = (
    "retry_attribution", "submit_store_proof", "show_activating_state", "offer_restore",
)
SILENT_SUCCESS_ACTIONS: frozenset[str] = frozenset({"treat_as_success", "dead_end"})
NEW_ERROR_TAXONOMY: frozenset[str] = frozenset()


def client_purchase_obligations(*,
                               token_attached_at_initiation: bool,
                               binding_acknowledged: bool) -> tuple[str, ...]:
    """The client attaches the user's purchase-attribution token to the purchase at initiation —
    which it always holds, because `GET /users/me` returns the tokens unconditionally — and never
    treats a purchase whose binding the backend has not acknowledged as a silent success: it retries
    the attribution or submits the store proof, shows an activating state until the backend confirms
    the entitlement, and surfaces restore as the recovery path rather than a dead end."""
    # [impl->req~restore-client-purchase-obligations~1]
    if NEW_ERROR_TAXONOMY:
        raise StorePurchaseError("no new error taxonomy is added for a missing acknowledgment")
    if not token_attached_at_initiation:
        raise StorePurchaseError("the attribution token is attached at purchase initiation")
    if binding_acknowledged:
        return ()
    return UNACKNOWLEDGED_ACTIONS


def assert_no_silent_success(actions: Iterable[str]) -> None:
    """A missing binding acknowledgment is a hard failure to retry, never a silent success."""
    # [impl->req~restore-client-purchase-obligations~1]
    offending = sorted(set(actions) & SILENT_SUCCESS_ACTIONS)
    if offending:
        raise StorePurchaseError(f"{offending} is not how an unacknowledged purchase is handled")


def assert_tokens_held_before_purchase(store_tokens: Mapping[str, Any]) -> None:
    """The client always holds both tokens before purchase, because `GET /users/me` returns them
    unconditionally."""
    # [impl->req~restore-client-purchase-obligations~1]
    missing = sorted(str(provider) for provider in StoreProvider
                     if not store_tokens.get(str(provider)))
    if missing:
        raise RestoreContractError(f"GET /users/me returns every store token; {missing} is absent")


# --- Store notification ingestion --------------------------------------------------------------------

# The two provider-callback routes Apple and Google deliver lifecycle events to, read from the route
# registry that owns the list rather than restated here.
INGESTION_ROUTES: tuple[tuple[str, str], ...] = tuple(
    (route.method, route.path) for route in PROVIDER_CALLBACK_ROUTES)

# They are not canonical state-changing auth operations, so they write no `audit.auth_events` row,
# and they answer with plain HTTP status codes rather than the shared client-visible error classes.
INGESTION_OPERATIONS: frozenset[AuthOperation] = frozenset()
INGESTION_AUDIT_ROWS: int = 0
INGESTION_RESPONSE_KIND: str = "plain_http_status"


def assert_ingestion_route(method: str, path: str) -> str:
    """Apple and Google deliver subscription lifecycle events to the two provider-callback routes.

    Neither carries a Firebase ID token, so each verifies its caller through the store's own
    mechanism, in the backend, before any business logic runs. Their caller is a store server rather
    than an app client: they are not canonical state-changing auth operations, they write no
    `audit.auth_events` row, and they answer with plain HTTP status codes.
    """
    # [impl->req~restore-ingestion-provider-callback-routes~1]
    if INGESTION_OPERATIONS or INGESTION_AUDIT_ROWS:
        raise StorePurchaseError("an ingestion route is no canonical auth operation")
    if INGESTION_RESPONSE_KIND != "plain_http_status":
        raise StorePurchaseError("ingestion answers in plain HTTP status codes")
    key = (method.upper(), path)
    if key not in INGESTION_ROUTES:
        raise StorePurchaseError(f"{method} {path} is no store ingestion route")
    if key in ID_TOKEN_REQUIRED_ROUTES:
        raise StorePurchaseError(f"{path} carries no Firebase ID token")
    if match_operation(*key) is not None:
        raise StorePurchaseError(f"{path} is not a canonical state-changing auth operation")
    verifier = named_verifier(*key)
    if verifier is None:
        raise StorePurchaseError(f"{path} verifies its caller through the store's own mechanism")
    return verifier


# Apple's credential is the JWS in the body. There is no `Authorization` header and no shared secret.
APPLE_BODY_CREDENTIAL_FIELD: str = "signedPayload"
APPLE_HEADER_CREDENTIALS: frozenset[str] = frozenset()
APPLE_SHARED_SECRETS: frozenset[str] = frozenset()


def apple_notification_credential(body: Mapping[str, Any],
                                  *, authorization: Iterable[str] = ()) -> str:
    """Apple sends no `Authorization` header and no shared secret. The request body is a single
    `signedPayload` field, a JWS Apple signed, so verifying that payload is how the notification is
    both authenticated and read."""
    # [impl->req~restore-apple-webhook-signed-payload-auth~1]
    if APPLE_HEADER_CREDENTIALS or APPLE_SHARED_SECRETS:
        raise StorePurchaseError("Apple sends no Authorization header and no shared secret")
    if tuple(authorization):
        raise StorePurchaseError("no Authorization field authenticates this notification")
    payload = body.get(APPLE_BODY_CREDENTIAL_FIELD)
    if not payload or not isinstance(payload, str):
        raise StorePurchaseError("the body is a single signedPayload field")
    return payload
