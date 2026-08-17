"""The schema-specific invariants of `06-schema-reference.md`.

The declarative schema enforces most of these by construction — generated columns, partial
indexes, per-source CHECKs and deferrable composite foreign keys. What is left is the write-side
half: the guards that stop a code path from proposing a row the schema forbids, or from writing
a column the specification retains but never updates. Rules whose whole statement already lives
in another module are enforced there and referenced here rather than restated.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import (
    PAIRING_ENFORCEMENT_MECHANISMS,
    NativeClaimPlatform,
)
from nativespeaker.api.auth.invariants import (
    ENUM_TYPED_FIELDS,
    GRANT_CREATOR_SOURCES,
    GrantCreator,
    InvariantError,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.profile import (
    AccountClass,
    account_class,
    assert_registered_at_pairing,
)
from nativespeaker.api.auth.upgrade import IDENTITY_LOCK_ORDER

# --- Invariant 02: who may create a free-credit grant, and what its source may become ---------

# The two free-credit grant sources, and the one operation each may be created by.
# `subscription` and `manual` grants are not free credit and are created by neither claim.
# [impl->req~schema-invariant-02~1]
# [impl->req~grants-invariant-02~2]
FREE_CREDIT_GRANT_SOURCES: dict[AccessGrantSource, GrantCreator] = {
    AccessGrantSource.anonymous_device_grant: GrantCreator.claim_anonymous_grant,
    AccessGrantSource.registered_account_grant: GrantCreator.claim_registered_grant,
}


def is_free_credit_source(source: AccessGrantSource) -> bool:
    """`anonymous_device_grant` and `registered_account_grant` are the only free-credit grant
    sources; `subscription` and `manual` are not."""
    # [impl->req~schema-invariant-02~1]
    # [impl->req~grants-invariant-02~2]
    return source in FREE_CREDIT_GRANT_SOURCES


def assert_free_credit_creator(creator: GrantCreator | AuthOperation | str,
                               source: AccessGrantSource) -> None:
    """`claim_anonymous_grant` is the only operation that may create an
    `anonymous_device_grant` row and `claim_registered_grant` the only one that may create a
    `registered_account_grant` row. The creator-to-source table lives in `invariants`; this
    reads it rather than keeping a second copy."""
    # [impl->req~schema-invariant-02~1]
    # [impl->req~grants-invariant-02~2]
    if not is_free_credit_source(source):
        raise InvariantError(f"{source} is not a free-credit grant source")
    allowed = FREE_CREDIT_GRANT_SOURCES[source]
    if str(creator) != str(allowed) or GRANT_CREATOR_SOURCES[allowed] is not source:
        raise InvariantError(f"only {allowed} may create a {source} grant")


def assert_grant_source_never_rewritten(stored: AccessGrantSource,
                                        incoming: AccessGrantSource) -> None:
    """A grant's `source` is fixed at creation. The conversion path supersedes the active
    anonymous grant and inserts a new registered row instead of rewriting either one."""
    # [impl->req~schema-invariant-02~1]
    if stored is not incoming:
        raise InvariantError(f"a grant's source is never rewritten from {stored} to {incoming}")


def assert_registered_conversion(*,
                                 superseded_source: AccessGrantSource,
                                 created_source: AccessGrantSource,
                                 superseded_transaction: object,
                                 created_transaction: object) -> None:
    """`claim_registered_grant`'s conversion path supersedes the user's active anonymous grant
    and creates the registered row in the same transaction."""
    # [impl->req~schema-invariant-02~1]
    if superseded_source is not AccessGrantSource.anonymous_device_grant:
        raise InvariantError("the conversion path supersedes the active anonymous grant")
    if created_source is not AccessGrantSource.registered_account_grant:
        raise InvariantError("the conversion path creates a registered_account_grant row")
    if superseded_transaction is not created_transaction:
        raise InvariantError("supersession and creation commit in one transaction")


# --- Invariant 04: the provider / `registered_at` pairing, and the transaction that keeps it --

# The columns the classification commits as one unit. They are written by the single completion
# transaction, so no partially classified account can be observed between them.
CLASSIFICATION_COMMIT_SET: tuple[str, str, str] = (
    "core.external_identities.provider",
    "core.users.registered_at",
    "core.users.email",
)


class LookupOutcome(StrEnum):
    """What the Firebase Admin lookup that supplies the classification returned."""
    classified = "classified"
    failed = "failed"
    indeterminate = "indeterminate"


def assert_classification_pairing(provider: IdentityProvider,
                                  registered_at: datetime | None) -> None:
    """`registered_at IS NOT NULL` if and only if the stored `provider` is `google` or `apple`,
    and there is no third classification state for authorization, grant class, or audit. The
    pairing is enforced in code, by the transaction: no cross-table constraint trigger exists
    and none is to be added."""
    # [impl->req~schema-invariant-04~1]
    if PAIRING_ENFORCEMENT_MECHANISMS:
        raise InvariantError("no cross-table constraint trigger enforces this pairing")
    assert_registered_at_pairing(provider, registered_at)
    if account_class(provider) not in set(AccountClass):
        raise InvariantError("there is no third classification state")


def classification_write_set(outcome: LookupOutcome,
                             *,
                             provider: IdentityProvider | None = None,
                             registered_at: datetime | None = None,
                             email: str | None = None,
                             transaction: object = None,
                             identity_transaction: object = None,
                             user_transaction: object = None) -> frozenset[str]:
    """What the completion transaction commits, given the outcome of the Admin lookup that would
    supply the classification.

    A lookup that failed or came back indeterminate commits nothing across tables: no
    `core.users` row, no `core.external_identities` row, no classification, no eligible email
    copy, and no grant. A lookup that classified commits the provider, `registered_at` and any
    eligible email copy together, in that one transaction.
    """
    # [impl->req~schema-invariant-04~1]
    if outcome is not LookupOutcome.classified:
        return frozenset()
    if provider is None:
        raise InvariantError("a classified outcome carries the classified provider")
    assert_classification_pairing(provider, registered_at)
    if identity_transaction is not transaction or user_transaction is not transaction:
        raise InvariantError(
            "the provider, registered_at and any email copy commit in one transaction")
    written = set(CLASSIFICATION_COMMIT_SET)
    if email is None:
        written.discard("core.users.email")
    return frozenset(written)


def assert_upgrade_revalidates_under_lock(*,
                                          locked: Sequence[str],
                                          revalidated: bool) -> None:
    """For an upgrade, that one transaction first locks the identity row and revalidates it,
    before any classification is written."""
    # [impl->req~schema-invariant-04~1]
    if tuple(locked) != IDENTITY_LOCK_ORDER:
        raise InvariantError(f"the upgrade transaction locks {IDENTITY_LOCK_ORDER} first")
    if not revalidated:
        raise InvariantError("the upgrade transaction revalidates the locked identity row")


# --- Invariant 03: authorization-relevant categorical fields are schema-typed enums -----------


def assert_enum_typed(field: str, value: object) -> None:
    """An authorization-relevant categorical field — external-identity `provider`, grant
    `source`, grant `status`, and audit `actor_provider` when present — is stored as its
    schema-typed enum. A free-text value for one of them never reaches the row."""
    # [impl->req~schema-invariant-03~1]
    declared = ENUM_TYPED_FIELDS.get(field)
    if declared is None:
        raise InvariantError(f"{field} is not an authorization-relevant categorical field")
    if value is None:
        return
    if not isinstance(value, declared):
        raise InvariantError(f"{field} is stored as {declared.__name__}, not free text")


# --- Invariants 08 and 09: the anti-abuse row beside an entitlement-only grant ----------------

# Column names whose material may never be stored on the anti-abuse row — or anywhere else in
# PostgreSQL: raw DeviceCheck tokens, raw Play Integrity tokens, raw Cloudflare bot-check
# tokens, any device-check-state hash, any device principal, and any synthetic stable provider
# device principal hash. Raw provider account identifiers live only in
# `core.external_identities` and the canonical `core.provider_accounts` registry.
# [impl->req~schema-invariant-08~2]
# [impl->req~schema-invariant-09~1]
# [impl->req~grants-invariant-03~2]
FORBIDDEN_ANTI_ABUSE_COLUMNS: frozenset[str] = frozenset({
    "devicecheck_token", "device_check_token", "device_check_state", "device_check_hash",
    "device_check_state_hash", "play_integrity_token", "device_recall_token",
    "bot_check_token", "turnstile_token", "device_principal", "device_principal_hash",
    "stable_device_principal_hash", "provider_device_principal_hash", "device_id",
    "device_identifier", "provider_uid",
})


class AntiAbuseEvidence(StrEnum):
    """The two evidence shapes an anti-abuse row may carry."""
    native_device_check = "native_device_check"
    idp_account = "idp_account"


def assert_no_raw_device_material(columns: Iterable[str]) -> None:
    """No table stores raw device-check tokens, a device-check-state hash, a device principal,
    or a synthetic stable provider device principal hash."""
    # [impl->req~schema-invariant-08~2]
    # [impl->req~schema-invariant-09~1]
    # [impl->req~grants-invariant-03~2]
    # [impl->req~schema-access-grants-anti-abuse-no-raw-material-stored~1]
    offending = sorted({column for column in columns
                        if column in FORBIDDEN_ANTI_ABUSE_COLUMNS})
    if offending:
        raise InvariantError(f"{offending} must not be stored in PostgreSQL")


def requires_anti_abuse_row(source: AccessGrantSource) -> bool:
    """Every grant with a free-credit source has exactly one `core.access_grants_anti_abuse`
    row; a `subscription` or `manual` grant must not have one."""
    # The declarative lower bound of `req~schema-invariant-14~1` (second sub-bullet) reads the same
    # predicate: an anti-abuse-eligible grant is exactly a free-credit-source grant.
    # [impl->req~schema-invariant-08~2]
    # [impl->req~grants-invariant-03~2]
    # [impl->req~grants-invariant-07~2]
    # [impl->req~schema-access-grants-requires-anti-abuse-row~1]
    # [impl->req~schema-access-grants-anti-abuse-purpose~1]
    return is_free_credit_source(source)


def anti_abuse_evidence(*,
                        grant_source: AccessGrantSource,
                        native_claim_provider: NativeClaimPlatform | None = None,
                        idp_account_hash: bytes | None = None,
                        idp_account_hash_key_version: int | None = None) -> AntiAbuseEvidence:
    """The evidence shape this anti-abuse row carries, refusing every shape the per-source CHECK
    rejects. Anonymous device grant rows carry either native device-check state recorded through
    `native_claim_provider` or web IDP-account evidence recorded through `idp_account_hash` and
    its key version; registered account grant rows carry IDP-account evidence and no
    `native_claim_provider`. `core.access_grants` itself stays entitlement state only, so none
    of this material sits on the grant row."""
    # The per-source CHECK's evidence-shape half, which `req~schema-invariant-14~1`'s first
    # continuation paragraph combines with the primary-key upper bound.
    # [impl->req~schema-invariant-08~2]
    # [impl->req~schema-invariant-09~1]
    # [impl->req~grants-invariant-03~2]
    # [impl->req~grants-invariant-09~2]
    # The per-source CHECK's two anonymous forms, and the registered shape's required
    # `idp_account_hash` and key version with no `native_claim_provider`.
    # [impl->req~schema-access-grants-anti-abuse-anonymous-shape-forms~1]
    # [impl->req~schema-access-grants-anti-abuse-registered-shape-required~1]
    # [impl->req~schema-access-grants-registered-grant-hash-required~1]
    if not requires_anti_abuse_row(grant_source):
        raise InvariantError(f"a {grant_source} grant has no anti-abuse row")
    idp = idp_account_hash is not None and idp_account_hash_key_version is not None
    partial_idp = (idp_account_hash is None) != (idp_account_hash_key_version is None)
    if partial_idp:
        raise InvariantError("an IDP account hash is stored with its key version")
    if grant_source is AccessGrantSource.registered_account_grant:
        if native_claim_provider is not None:
            raise InvariantError("a registered_account_grant row carries no native_claim_provider")
        if not idp:
            raise InvariantError("a registered_account_grant row carries IDP-account evidence")
        return AntiAbuseEvidence.idp_account
    if (native_claim_provider is not None) == idp:
        raise InvariantError(
            "an anonymous_device_grant row carries native device-check state or IDP-account "
            "evidence, never both and never neither")
    if native_claim_provider is not None:
        return AntiAbuseEvidence.native_device_check
    return AntiAbuseEvidence.idp_account


def assert_anti_abuse_pairing(grant_source: AccessGrantSource,
                              anti_abuse_grant_source: AccessGrantSource | None) -> None:
    """The composite foreign key binds the anti-abuse row to its grant's source: a free-credit
    grant has a row whose `grant_source` equals the grant's `source`, and a grant of any other
    source has none.

    This is the write-side half of the composite foreign key on `(grant_id, grant_source)` plus the
    per-source CHECK — the same pair that, with `grant_id` being the anti-abuse table's primary key,
    yields "exactly one anti-abuse row per eligible grant, none for any other source". Because the
    foreign key is deferrable, the grant row and its anti-abuse row may be inserted in either order
    inside the one transaction and are checked together at commit, and a deleted grant cascades to
    its anti-abuse row rather than leaving it orphaned.
    """
    # [impl->req~schema-invariant-08~2]
    # [impl->req~grants-invariant-03~2]
    # [impl->req~grants-invariant-06~2]
    # [impl->req~grants-invariant-07~2]
    # [impl->req~grants-invariant-09~2]
    # [impl->req~schema-access-grants-requires-anti-abuse-row~1]
    # [impl->req~schema-access-grants-anti-abuse-no-row-for-other-sources~1]
    if requires_anti_abuse_row(grant_source):
        if anti_abuse_grant_source is None:
            raise InvariantError(f"a {grant_source} grant requires an anti-abuse row")
        if anti_abuse_grant_source is not grant_source:
            raise InvariantError("the anti-abuse row records its grant's own source")
    elif anti_abuse_grant_source is not None:
        raise InvariantError(f"a {grant_source} grant must not have an anti-abuse row")


def assert_native_claim_written_before_grant(*,
                                             native_claim_written: bool,
                                             same_attempt: bool) -> None:
    """For the native shape, `claim_anonymous_grant` writes native claimed state successfully in
    the same attempt before creating the active anonymous grant. The ordering is an operation
    rule, not a schema constraint, so it is enforced here on the claim path."""
    # [impl->req~schema-invariant-09~1]
    # [impl->req~schema-access-grants-native-write-before-activation~1]
    if not native_claim_written:
        raise InvariantError("native claimed state is written before the grant is created")
    if not same_attempt:
        raise InvariantError("native claimed state is written in the same attempt")


# --- Invariant 13: a retained column no write path ever updates ------------------------------

# Retained as schema and never updated: cross-account restore transfer is never performed, so no
# restore outcome writes this column.
# [impl->req~schema-invariant-13~1]
NEVER_WRITTEN_COLUMNS: frozenset[str] = frozenset({
    "core.subscriptions.last_cross_account_transfer_month",
})


def assert_no_never_written_column(table: str, columns: Iterable[str]) -> None:
    """Fail closed on any write path that names a retained-but-never-written column."""
    # [impl->req~schema-invariant-13~1]
    # [impl->req~restore-invariant-11~2]
    offending = sorted({column for column in columns
                        if f"{table}.{column}" in NEVER_WRITTEN_COLUMNS})
    if offending:
        raise InvariantError(f"{table}.{offending} is retained as schema and never updated")


# --- Invariant 15: purchase attribution carries no identity-kind dimension --------------------


class AttributionOutcome(StrEnum):
    """How a store-verified purchase was attributed."""
    token_binding = "token_binding"
    restore_insert_once = "restore_insert_once"
    unclaimed = "unclaimed"


def attribute_purchase(*,
                       token_owner_id: UUID | None,
                       restoring_destination_user_id: UUID | None = None) -> tuple[
                           AttributionOutcome, dict[str, Any]]:
    """The owning user of a verified purchase, resolved at ingestion only by matching the
    store-echoed token through `core.store_purchase_tokens` by `(provider, identity_value)`.
    `restore_subscription`'s insert-once creation is the one carve-out: where no row covers a
    store-verified subscription, restore attributes it to the restoring destination user on the
    strength of the store's own verification. A token that resolves to no binding creates the
    canonical subscription unclaimed and the store purchase unattributed, with no grant and no
    usage row."""
    # [impl->req~schema-invariant-15~1]
    if token_owner_id is not None:
        return AttributionOutcome.token_binding, {
            "subscription_user_id": token_owner_id,
            "purchase_user_id": token_owner_id,
        }
    if restoring_destination_user_id is not None:
        return AttributionOutcome.restore_insert_once, {
            "subscription_user_id": restoring_destination_user_id,
            "purchase_user_id": restoring_destination_user_id,
        }
    return AttributionOutcome.unclaimed, {
        "subscription_user_id": None,
        "purchase_user_id": None,
        "access_grant_id": None,
        "user_monthly_usage_grant_id": None,
    }


def assert_no_client_asserted_attribution(fields: Mapping[str, Any]) -> None:
    """Attribution is server-authoritative: it never comes from the request-authenticated or any
    client-asserted identity, and it carries no identity-kind dimension."""
    # [impl->req~schema-invariant-15~1]
    forbidden = {"authenticated_user_id", "client_user_id", "asserted_user_id",
                 "identity_kind", "is_anonymous", "account_kind"}
    offending = sorted(forbidden & {str(name) for name in fields})
    if offending:
        raise InvariantError(f"{offending} may not decide purchase attribution")


# --- Invariant 16: the attribution tokens minted once at user creation ------------------------

# The one point at which a user's purchase-attribution tokens are minted.
# [impl->req~schema-invariant-16~1]
TOKEN_MINTING_OPERATION: AuthOperation = AuthOperation.create_user


def assert_tokens_minted_at_creation(operation: AuthOperation) -> None:
    """Each user's purchase-attribution tokens are minted once, at user creation."""
    # [impl->req~schema-invariant-16~1]
    if operation is not TOKEN_MINTING_OPERATION:
        raise InvariantError(f"{operation} does not mint purchase-attribution tokens")


def assert_tokens_survive_upgrade(before: Mapping[str, str], after: Mapping[str, str]) -> None:
    """The binding persists across the in-place `upgrade_anonymous_to_registered` flow without
    being regenerated, moved, or retired."""
    # [impl->req~schema-invariant-16~1]
    if dict(after) != dict(before):
        raise InvariantError(
            "the in-place upgrade regenerates, moves or retires no attribution token")
