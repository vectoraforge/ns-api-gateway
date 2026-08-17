"""The record tables beside the grant tables: `core.manual_grant_issuances`, `core.provider_accounts`
and `core.provider_account_gate_consumptions`.

Two different kinds of record live here. One is the operator issuance trail: a row per support case
that says which `manual` grant repaired it, who issued it and why, written in the grant's own
transaction and never touched again. The other is the canonical provider-account registry the
free-grant gates are enforced on: one row per stable Google or Apple provider account, plus one
consumption row per gate that account has spent.

Both are historical records rather than mutable state, so almost everything here is a refusal: the
issuance row is never updated or deleted, the registry row is never deleted or reassigned, and
`idp_account_hash` never decides anything. Rules whose whole statement already lives in another
module — the gate conflict results in `invariants`, the derivation input sources in
`derived_identifiers`, the lifetime free-grant slot in `grant_schema` — are enforced there and
delegated to from here rather than restated.
"""

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.derived_identifiers import (
    IdpAccountAliasIndex,
    IdpInputSource,
    assert_idp_input_source,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.grant_schema import (
    FREE_GRANTS_PER_ACCOUNT,
    GATE_CONSUMPTIONS_KEY,
    GATE_CONSUMPTIONS_TABLE,
    IDP_ACCOUNT_HASH_IS_AUTHORITATIVE,
)
from nativespeaker.api.auth.invariants import (
    GateConsumptionKind,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider


class RegistryError(RuntimeError):
    """A proposed row breaks the contract of one of the record tables."""


# --- `core.manual_grant_issuances` -------------------------------------------------------------

MANUAL_ISSUANCES_TABLE: str = "core.manual_grant_issuances"

# The one row per support case that records an operator-issued `manual` grant. `case_id` is the
# primary key, `grant_id` is unique, and the row is written in the same transaction as the grant it
# produced. The issuance procedure itself lives in `manual_grants`, which calls this to build the
# row; `03-free-credit-grants-and-anti-abuse.md` owns that procedure's steps.
# [impl->req~schema-manual-grant-issuances-purpose~1]
MANUAL_ISSUANCE_PRIMARY_KEY: str = "case_id"
MANUAL_ISSUANCE_UNIQUE_COLUMNS: tuple[str, ...] = ("grant_id",)
MANUAL_ISSUANCE_REQUIRED_TEXT: tuple[str, ...] = ("case_id", "operator", "reason")
MANUAL_ISSUANCE_GRANT_SOURCE: AccessGrantSource = AccessGrantSource.manual

# Rows are never updated or deleted: this table is the durable record of a manual issuance, so no
# write path revises one and no cleanup path removes one.
# [impl->req~schema-manual-grant-issuances-rows-immutable~1]
MANUAL_ISSUANCE_ROW_UPDATERS: frozenset[str] = frozenset()
MANUAL_ISSUANCE_ROW_DELETERS: frozenset[str] = frozenset()

# `audit.auth_events` covers requests on the audited attempt path only, and an operator issuance is
# not a request on that path, so it holds no row for one.
# [impl->req~schema-manual-grant-issuances-rows-immutable~1]
MANUAL_ISSUANCE_AUDIT_EVENT_ROWS: int = 0


def manual_issuance_row(*,
                        case_id: str,
                        grant: Mapping[str, Any],
                        operator: str,
                        reason: str,
                        target_user_id: UUID,
                        transaction: object,
                        grant_transaction: object) -> dict[str, Any]:
    """The one `core.manual_grant_issuances` row an issuance writes, in the same transaction as the
    grant it produced.

    `case_id` is the support or remediation case identifier supplied at issuance and the primary
    key, so the same case can never insert a second row. `grant_id` is the grant this issuance
    created and is unique, so one grant is never claimed by two cases; that grant always has
    `source = 'manual'`, which is why it carries neither an anti-abuse row nor a gate-consumption
    row. `user_id` is the target owner and is the same `core.users.id` the grant belongs to, and
    `operator` and `reason` are the issuance audit trail: both required, both non-empty.
    """
    # One row per support case, written in the grant's own transaction.
    # [impl->req~schema-manual-grant-issuances-purpose~1]
    # `case_id` is the primary key.
    # [impl->req~schema-manual-grant-issuances-case-id-primary-key~1]
    # `grant_id` is unique and always names a `manual` grant, so no anti-abuse or gate-consumption
    # row pairs with it.
    # [impl->req~schema-manual-grant-issuances-grant-id-unique~1]
    # `user_id` is the target owner, and it is the grant's own owner.
    # [impl->req~schema-manual-grant-issuances-user-id-target-owner~1]
    # `operator` and `reason` are both required and non-empty.
    # [impl->req~schema-manual-grant-issuances-operator-reason-required~1]
    if transaction is not grant_transaction:
        raise RegistryError("the issuance row is written in the grant's own transaction")
    values = {"case_id": case_id, "operator": operator, "reason": reason}
    missing = sorted(name for name in MANUAL_ISSUANCE_REQUIRED_TEXT
                     if not str(values[name]).strip())
    if missing:
        raise RegistryError(f"{missing} is required and non-empty on an issuance row")
    if grant.get("source") is not MANUAL_ISSUANCE_GRANT_SOURCE:
        raise RegistryError(f"an issuance row records a {MANUAL_ISSUANCE_GRANT_SOURCE} grant")
    grant_id = grant.get("id")
    if not isinstance(grant_id, UUID):
        raise RegistryError("the issuance row names the grant it created")
    if grant.get("user_id") != target_user_id:
        raise RegistryError("the issuance row's user_id is the grant's own owner")
    return {
        "case_id": case_id,
        "grant_id": grant_id,
        "user_id": target_user_id,
        "operator": operator,
        "reason": reason,
    }


def assert_case_issues_once(case_id: str, recorded: Iterable[str]) -> None:
    """A repeat issuance for an already-recorded case inserts no second row: `case_id` is the
    primary key, so the procedure returns the recorded grant instead of issuing another."""
    # [impl->req~schema-manual-grant-issuances-case-id-primary-key~1]
    if case_id in set(recorded):
        raise RegistryError(f"{case_id} already produced a grant; return that one")


def assert_grant_claimed_by_one_case(grant_id: UUID,
                                     recorded: Mapping[str, UUID]) -> None:
    """`grant_id` is unique on this table, so one grant is never claimed by two cases."""
    # [impl->req~schema-manual-grant-issuances-grant-id-unique~1]
    holder = next((case for case, held in recorded.items() if held == grant_id), None)
    if holder is not None:
        raise RegistryError(f"grant {grant_id} is already recorded by case {holder}")


def assert_issuance_row_immutable(*,
                                  updated: Iterable[str] = (),
                                  deleted: bool = False,
                                  audit_rows: int = 0) -> None:
    """Rows are never updated or deleted, and this table — not `audit.auth_events` — is the durable
    record of a manual issuance."""
    # [impl->req~schema-manual-grant-issuances-rows-immutable~1]
    if MANUAL_ISSUANCE_ROW_UPDATERS or MANUAL_ISSUANCE_ROW_DELETERS:
        raise RegistryError("no write path updates or deletes an issuance row")
    touched = sorted({str(column) for column in updated})
    if touched:
        raise RegistryError(f"an issuance row is never updated: {touched}")
    if deleted:
        raise RegistryError("an issuance row is never deleted")
    if audit_rows or MANUAL_ISSUANCE_AUDIT_EVENT_ROWS:
        raise RegistryError("audit.auth_events holds no row for an operator issuance")


# --- `core.provider_accounts`: the canonical registry -------------------------------------------

PROVIDER_ACCOUNTS_TABLE: str = "core.provider_accounts"

# The canonical registry of the Google and Apple provider accounts free-grant anti-abuse is
# enforced on. One row per stable provider-side account identifier — the same value the identity
# row stores as `provider_uid` — unique on `(provider, provider_uid)`, so the two provider
# namespaces are separate components of one key rather than one shared identifier space.
# [impl->req~schema-provider-accounts-registry-definition~1]
PROVIDER_ACCOUNTS_UNIQUE_ON: tuple[str, ...] = ("provider", "provider_uid")
REGISTRY_PROVIDERS: frozenset[IdentityProvider] = frozenset({IdentityProvider.google,
                                                             IdentityProvider.apple})
STABLE_UID_SOURCE_COLUMN: str = "core.external_identities.provider_uid"

# One consumption row per `(provider_account_id, consumption_kind)`, and the claim each kind
# belongs to. The row records the `grant_id` it produced, so a repeat claim is matched to its
# grant. The key and the table name are `grant_schema`'s; this only names the endpoints.
# [impl->req~schema-provider-accounts-registry-definition~1]
GATE_CLAIM_OPERATIONS: dict[GateConsumptionKind, AuthOperation] = {
    GateConsumptionKind.web_anonymous_gate: AuthOperation.claim_anonymous_grant,
    GateConsumptionKind.registered_account_grant: AuthOperation.claim_registered_grant,
}

# Rows are historical records: the stable UID and its provider binding are immutable, and no path
# deletes a registry row or reassigns one to another provider account.
# [impl->req~schema-provider-accounts-uid-immutable-historical~1]
PROVIDER_ACCOUNT_ROW_DELETERS: frozenset[str] = frozenset()
PROVIDER_ACCOUNT_REASSIGNERS: frozenset[str] = frozenset()


def canonical_account(provider: IdentityProvider, provider_uid: str) -> ProviderAccount:
    """One canonical registry row's key: a Google or Apple provider with the stable provider-side
    account identifier the identity row stores as `provider_uid`. Anonymous is no provider account,
    and an empty UID is no identifier."""
    # [impl->req~schema-provider-accounts-registry-definition~1]
    if provider not in REGISTRY_PROVIDERS:
        raise RegistryError(f"{provider} is no Google or Apple provider account")
    if not provider_uid.strip():
        raise RegistryError("a registry row carries a non-empty stable provider UID")
    return ProviderAccount(provider=provider, provider_uid=provider_uid)


def gate_consumption_row(account: ProviderAccount,
                         kind: GateConsumptionKind,
                         grant_id: UUID) -> dict[str, Any]:
    """One `core.provider_account_gate_consumptions` row: the canonical provider account, the gate
    kind it consumed, and the grant that consumption produced. `web_anonymous_gate` is the web
    anonymous claim's gate and `registered_account_grant` the registered claim's."""
    # [impl->req~schema-provider-accounts-registry-definition~1]
    if kind not in GATE_CLAIM_OPERATIONS:
        raise RegistryError(f"{kind} is no free-grant gate")
    canonical = canonical_account(account.provider, account.provider_uid)
    return {"provider_account_id": canonical, "consumption_kind": kind, "grant_id": grant_id}


def consumed_grant(gates: ProviderAccountGates,
                   account: ProviderAccount,
                   kind: GateConsumptionKind) -> UUID | None:
    """The grant a consumed gate produced, so a repeat claim can be matched to its grant rather
    than answered with a bare refusal."""
    # [impl->req~schema-provider-accounts-registry-definition~1]
    return gates.consumed_grant(canonical_account(account.provider, account.provider_uid), kind)


def assert_stable_binding_immutable(stored: ProviderAccount, incoming: ProviderAccount) -> None:
    """The stable UID and its provider binding are immutable once the canonical row exists."""
    # [impl->req~schema-provider-accounts-uid-immutable-historical~1]
    if stored.provider is not incoming.provider or stored.provider_uid != incoming.provider_uid:
        raise RegistryError("a registry row's provider and stable UID are immutable")


def resolve_or_create_provider_account(index: IdpAccountAliasIndex,
                                       account: ProviderAccount,
                                       *,
                                       source: IdpInputSource,
                                       transaction: object,
                                       grant_transaction: object,
                                       consumption_transaction: object) -> ProviderAccount:
    """Resolve the canonical registry row for this stable provider account, creating it only when
    the stable uniqueness constraint has no row for it, in the same transaction as the grant and
    the gate-consumption insert.

    The row is a historical record: it is never deleted, never reassigned, and its provider and
    stable UID are immutable, so a resolve that finds a row returns exactly that row. Resolution is
    keyed on the stable UID alone, and no `idp_account_hash` is consulted to reach it.
    """
    # Immutable, never deleted, never reassigned, resolved-or-created under the stable uniqueness
    # constraint in the grant's own transaction.
    # [impl->req~schema-provider-accounts-uid-immutable-historical~1]
    # The stable UID comes from a backend-verified source, never from a client field or a gateway
    # header; `derived_identifiers` owns which sources those are.
    # [impl->req~schema-provider-accounts-uid-source-backend-verified~1]
    if PROVIDER_ACCOUNT_ROW_DELETERS or PROVIDER_ACCOUNT_REASSIGNERS:
        raise RegistryError("a registry row is never deleted or reassigned")
    if transaction is not grant_transaction or transaction is not consumption_transaction:
        raise RegistryError(
            "the canonical row is resolved-or-created with the grant and consumption inserts")
    assert_idp_input_source(source)
    requested = canonical_account(account.provider, account.provider_uid)
    known = {(row.provider, row.provider_uid) for row in index.accounts}
    canonical = index.register(requested)
    assert_stable_binding_immutable(canonical, requested)
    if (requested.provider, requested.provider_uid) in known \
            and len(index.accounts) > len(known):
        raise RegistryError(
            "the stable UID already has a canonical row; no second row is created for it")
    return canonical


# --- `idp_account_hash` as a lookup and audit alias ---------------------------------------------


def resolve_through_retained_version(index: IdpAccountAliasIndex,
                                     digest: bytes) -> ProviderAccount | None:
    """A lookup through any retained key version resolves to the same canonical row: several key
    versions may map to one stable account, and none of them is authoritative for anything."""
    # [impl->req~schema-provider-accounts-hash-non-authoritative-alias~1]
    if IDP_ACCOUNT_HASH_IS_AUTHORITATIVE:
        raise RegistryError("idp_account_hash is a lookup and audit alias, never the authority")
    return index.resolve(digest)


def assert_alias_never_mints_a_row(index: IdpAccountAliasIndex,
                                   account: ProviderAccount,
                                   *,
                                   current_version_hash: bytes | None) -> ProviderAccount:
    """A missing current-version `idp_account_hash` must never cause creation of a second canonical
    row when the stable UID already exists: resolution is keyed on the UID, so an absent, stale or
    freshly rotated alias changes nothing about which row a claim resolves to. Where a hash is
    presented, every retained version it could have been derived under resolves to that same row.
    """
    # [impl->req~schema-provider-accounts-hash-non-authoritative-alias~1]
    requested = canonical_account(account.provider, account.provider_uid)
    known = {(row.provider, row.provider_uid) for row in index.accounts}
    canonical = index.register(requested)
    if (requested.provider, requested.provider_uid) in known \
            and len(index.accounts) > len(known):
        raise RegistryError("a missing current-version hash creates no second canonical row")
    if current_version_hash is not None:
        resolved = resolve_through_retained_version(index, current_version_hash)
        if resolved is not None and resolved != canonical:
            raise RegistryError("every retained alias version resolves to the one canonical row")
    return canonical


# --- The gates are abuse brakes, not allowances -------------------------------------------------

# What a gate-consumption row is, and what it is not. Two open gates are not two user-level
# allowances: the user-level rule is `grant_schema`'s one free grant per account across both claim
# endpoints, and the per-gate rows only stop one provider account from spending a gate twice.
# [impl->req~schema-provider-accounts-gates-are-abuse-brakes~1]
GATE_ROLE: str = "per_key_abuse_brake"
GATE_ROLES_REFUSED: frozenset[str] = frozenset({"independent_user_allowance"})


def assert_gate_is_no_second_allowance(*,
                                       open_gates: Iterable[GateConsumptionKind],
                                       committed_free_sources: Sequence[AccessGrantSource]) -> None:
    """An open gate never adds a user-level allowance. A user who already holds a committed
    free-credit grant is refused a second one even where the other endpoint's gate is untouched,
    because the per-gate rows are abuse brakes on one provider account's keys, not per-endpoint
    entitlements."""
    # [impl->req~schema-provider-accounts-gates-are-abuse-brakes~1]
    if GATE_ROLE in GATE_ROLES_REFUSED:
        raise RegistryError("a gate-consumption row is no independent user allowance")
    committed = {source for source in committed_free_sources
                 if source in {AccessGrantSource.anonymous_device_grant,
                               AccessGrantSource.registered_account_grant}}
    if len(committed) >= FREE_GRANTS_PER_ACCOUNT and set(open_gates):
        raise RegistryError(
            "one free grant per account across both claim endpoints; an open gate adds none")


# --- Pre-launch migration onto the stable UID ---------------------------------------------------


class PrelaunchDisposition(StrEnum):
    """What pre-launch migration does with one legacy anti-abuse row."""
    backfilled = "backfilled"
    discarded = "discarded"
    failed_closed = "failed_closed"


# An unresolved hash-only row is never treated as a fresh account: that would hand a provider
# account a second free grant. Pre-launch there are no users to protect, so discarding the row or
# failing the migration closed are both acceptable and cheap.
# [impl->req~schema-provider-accounts-prelaunch-migration~1]
UNRESOLVED_ROW_IS_FRESH_ACCOUNT: bool = False


def prelaunch_disposition(*,
                          stable_uid: str | None,
                          discard_unresolved: bool = True) -> PrelaunchDisposition:
    """Pre-launch migration is cheap: backfill the stable UID wherever it is available, and either
    discard the unresolved hash-only rows or fail the migration closed. What it never does is treat
    an unresolved row as a fresh account, which would reopen a consumed gate."""
    # [impl->req~schema-provider-accounts-prelaunch-migration~1]
    if UNRESOLVED_ROW_IS_FRESH_ACCOUNT:
        raise RegistryError("an unresolved hash-only row is never a fresh provider account")
    if stable_uid is not None and stable_uid.strip():
        return PrelaunchDisposition.backfilled
    return PrelaunchDisposition.discarded if discard_unresolved \
        else PrelaunchDisposition.failed_closed


# --- The link reservation and the gate uniqueness are separate rules ---------------------------

# The one-provider-account-one-user link uniqueness lives on `core.external_identities`, keyed by
# `(issuer, provider, provider_uid)`. The per-gate consumption uniqueness lives on
# `core.provider_account_gate_consumptions`, keyed by `(provider_account_id, consumption_kind)`.
# Different tables, different keys, different rejections: neither stands in for the other.
# [impl->req~schema-provider-accounts-link-uniqueness-separate~1]
LINK_UNIQUENESS_TABLE: str = "core.external_identities"
LINK_UNIQUENESS_KEY: tuple[str, ...] = ("issuer", "provider", "provider_uid")


def assert_uniqueness_rules_separate() -> None:
    """The link reservation and the per-gate consumption uniqueness are two rules on two tables.
    A consumed gate never frees or fills a link reservation, and an already-attached provider
    account is still rejected on attachment rather than silently moved to the second user."""
    # [impl->req~schema-provider-accounts-link-uniqueness-separate~1]
    if LINK_UNIQUENESS_TABLE == GATE_CONSUMPTIONS_TABLE:
        raise RegistryError("the two uniqueness rules live on two tables")
    if LINK_UNIQUENESS_KEY == GATE_CONSUMPTIONS_KEY:
        raise RegistryError("the two uniqueness rules are keyed differently")
