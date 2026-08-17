"""`core.external_identities` semantics: the verified external identity, its provider binding,
and its one-way lifecycle.

This module is the one place the rules that govern an external-identity row are decided — where
`issuer` and `subject` may come from, how `provider` is classified and how `provider_uid` is
sourced and reserved, what an `identity_state` transition may do, and what must never happen to
the row. The column facts themselves live in the declarative schema and are applied by the
migration that ships it; rules with a complete normative home elsewhere are delegated to that
home rather than restated here.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, NoReturn
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.integration import (
    AdminCallSite,
    FirebaseIntegrations,
    UnrecognizedProviderError,
)
from nativespeaker.api.auth.invariants import (
    InvariantError,
    ProviderAccountAlreadyLinkedError,
    assert_provider_uid_immutable,
    provider_data_id,
    provider_uid_from_provider_data,
    provider_uid_reserved,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.profile import read_orphan_user
from nativespeaker.api.auth.taxonomy import (
    REMEDIATIONS,
    RESULT_TO_CLASS,
    ClientErrorClass,
    ClientRejection,
    ProviderDataReadPoint,
    client_response,
    register_client_class,
    surface,
)


class IdentityError(RuntimeError):
    """A `core.external_identities` rule was about to be broken."""


class ProviderClassificationError(IdentityError):
    """The Firebase Admin `providerData` shape does not classify to a stored provider."""


class ProviderLookupFailedError(IdentityError):
    """A required Firebase Admin `getUser(subject)` lookup did not produce a usable record."""

    def __init__(self, result: AuthEventResult, client_class: ClientErrorClass, *,
                 retryable: bool):
        self.result = result
        self.client_class = client_class
        self.retryable = retryable
        super().__init__(f"the provider lookup failed as {result}")


class BindingDivergenceError(IdentityError):
    """The stored registered binding diverges from the Firebase Admin-confirmed live one."""

    result = AuthEventResult.provider_transition_not_allowed
    client_class = ClientErrorClass.operation_not_allowed


# A divergent stored binding surfaces through the shared `operation_not_allowed` class, added
# through the taxonomy's declared extension point rather than through a second registry.
if AuthEventResult.provider_transition_not_allowed not in RESULT_TO_CLASS:
    register_client_class(AuthEventResult.provider_transition_not_allowed,
                          ClientErrorClass.operation_not_allowed.value,
                          REMEDIATIONS[ClientErrorClass.operation_not_allowed].http_status)


# --- The row ------------------------------------------------------------------------------------


class IdentityState(StrEnum):
    """`core.identity_state`: an identity is `active` or `historical`."""
    # [impl->req~users-rule-identity-lifecycle-state~1]
    active = "active"
    historical = "historical"


class NativeClaimPlatform(StrEnum):
    """`core.native_claim_provider`: the native free-grant branch an anonymous identity pinned."""
    ios_devicecheck = "ios_devicecheck"
    android_play_integrity = "android_play_integrity"


REGISTERED_PROVIDERS: frozenset[IdentityProvider] = frozenset(
    {IdentityProvider.google, IdentityProvider.apple})


def assert_provider_uid_check(provider: IdentityProvider, provider_uid: str | None) -> None:
    """The table's `CHECK` tying `provider_uid` to the identity kind: `NULL` exactly when
    `provider = 'anonymous'`, non-empty for `google` and `apple`. It is what keeps every
    registered row inside the reservation index's scope, so a malformed registered row cannot
    store a `NULL` `provider_uid` and evade the reservation."""
    # `provider_uid IS NULL` is required when `provider = 'anonymous'`, and a non-empty
    # `provider_uid` when `provider IN ('google', 'apple')`.
    # [impl->req~schema-external-identities-reservation-not-null-semantics~1]
    # [impl->req~users-rule-provider-uid-nullability~1]
    if provider is IdentityProvider.anonymous:
        if provider_uid is not None:
            raise IdentityError("an anonymous identity carries no provider_uid")
        return
    if not provider_uid:
        raise IdentityError(f"a {provider} identity carries a non-empty provider_uid")


@dataclass(frozen=True, slots=True)
class ExternalIdentityRow:
    """One `core.external_identities` row: a verified external identity and the internal user it
    maps to. `user_id` is that mapping and the only one; nothing else resolves an owner."""
    # [impl->req~schema-external-identities-purpose~1]
    id: UUID
    user_id: UUID
    issuer: str
    subject: str
    provider: IdentityProvider
    provider_uid: str | None = None
    identity_state: IdentityState = IdentityState.active
    native_claim_platform: NativeClaimPlatform | None = None
    free_grant_consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        # `provider` is stored as `core.identity_provider`, not free text, so a string that
        # merely looks like a provider never reaches the column.
        # [impl->req~schema-external-identities-provider-enum-typed~1]
        if not isinstance(self.provider, IdentityProvider):
            raise IdentityError("provider is stored as core.identity_provider, not free text")
        if not isinstance(self.identity_state, IdentityState):
            raise IdentityError("identity_state is stored as core.identity_state, not free text")
        assert_provider_uid_check(self.provider, self.provider_uid)


# --- Where the raw identity may live --------------------------------------------------------------

# The one table that stores a raw, recoverable external identity subject.
RAW_SUBJECT_STORES: frozenset[str] = frozenset({"core.external_identities"})

# The two tables a raw provider-account identifier may live in: the identity row and the
# canonical registry that keeps the same stable identifier.
RAW_PROVIDER_ACCOUNT_STORES: frozenset[str] = frozenset(
    {"core.external_identities", "core.provider_accounts"})

# The tables that hold a keyed hash of a subject and never the subject itself.
KEYED_SUBJECT_ONLY_TABLES: frozenset[str] = frozenset(
    {"core.auth_challenges", "audit.auth_events"})


def assert_raw_subject_store(table: str) -> None:
    """`core.external_identities` is the only table that stores the plaintext `issuer` and
    `subject`. `core.auth_challenges` and `audit.auth_events` hold a keyed hash of a subject and
    never the subject itself."""
    # [impl->req~schema-external-identities-only-raw-subject-store~1]
    if table not in RAW_SUBJECT_STORES:
        raise IdentityError(f"{table} must not store a raw external identity subject")


def assert_raw_provider_account_store(table: str) -> None:
    """A registered `provider_uid` is stored in plaintext on the identity row, and the canonical
    `core.provider_accounts` registry keeps the same stable identifier. Those two tables are the
    only places a raw provider account identifier lives."""
    # [impl->req~schema-external-identities-only-raw-subject-store~1]
    if table not in RAW_PROVIDER_ACCOUNT_STORES:
        raise IdentityError(f"{table} must not store a raw provider account identifier")


class IdentityFieldSource(StrEnum):
    """Where a value offered for `issuer` or `subject` came from."""
    verified_id_token = "verified_id_token"
    transport_metadata = "transport_metadata"
    request_header = "request_header"
    cookie = "cookie"
    client_field = "client_field"


def identity_key(issuer: str, subject: str, *, source: IdentityFieldSource) -> tuple[str, str]:
    """`issuer` and `subject` are exactly the backend-verified Firebase ID token's `iss` and
    `sub` claims. They are never reconstructed from transport metadata, headers, cookies, or
    client-supplied fields."""
    # [impl->req~schema-external-identities-issuer-subject-from-verified-token~1]
    if source is not IdentityFieldSource.verified_id_token:
        raise IdentityError(f"{source} is not a source for issuer and subject")
    if not issuer or not subject:
        raise IdentityError("both verified claims are required")
    return issuer, subject


# Identity lookup is by exact `(issuer, subject)` and by nothing else.
IDENTITY_LOOKUP_KEY: tuple[str, str] = ("issuer", "subject")


def assert_lookup_fields(fields: Iterable[str]) -> None:
    """Identity lookup is done by exact `(issuer, subject)`: not by subject alone, not by a
    stored email, and not by any normalized or folded variant of either."""
    # [impl->req~schema-external-identities-lookup-by-issuer-subject~1]
    if sorted(fields) != sorted(IDENTITY_LOOKUP_KEY):
        raise IdentityError(f"identity lookup is by {IDENTITY_LOOKUP_KEY} exactly")


def matches_identity(row: ExternalIdentityRow, issuer: str, subject: str) -> bool:
    """Exact match of the stored pair against the verified pair. Nothing is trimmed, case-folded,
    decoded or defaulted on either side."""
    # [impl->req~schema-external-identities-lookup-by-issuer-subject~1]
    return row.issuer == issuer and row.subject == subject


# --- Administrative operations on an existing row --------------------------------------------------


class AdministrativeAction(StrEnum):
    """The two lifecycle writes an operator may make against an existing identity row."""
    block_user = "block_user"
    retire_identity = "retire_identity"


@dataclass(frozen=True, slots=True)
class AdministrativeOutcome:
    """What an administrative action left behind. The lifecycle database write is committed
    first and is immediately authoritative; the revocation that accompanies it is reported
    separately and never undoes it."""
    action: AdministrativeAction
    lifecycle_write: str
    committed: bool
    revocation_failed: bool
    operator_retry_available: bool


# The lifecycle write each administrative action commits before any Firebase Admin call.
LIFECYCLE_WRITES: dict[AdministrativeAction, str] = {
    AdministrativeAction.block_user: "core.users.active = FALSE",
    AdministrativeAction.retire_identity: "core.external_identities.identity_state = 'historical'",
}

# Nothing further is done about refresh tokens that survive a failed revocation: no automated
# retry, no compensation machinery, no revocation-pending marker or queue, and no user-visible
# partial-failure state.
REVOCATION_FAILURE_MACHINERY: frozenset[str] = frozenset()


ADMINISTRATIVE_ADMIN_CALL_SITES: dict[AdministrativeAction, AdminCallSite] = {
    AdministrativeAction.block_user: AdminCallSite.operator_block_revocation,
    AdministrativeAction.retire_identity: AdminCallSite.identity_retirement_revocation,
}


def admin_client_for_identity(integrations: FirebaseIntegrations,
                              row: ExternalIdentityRow,
                              *,
                              action: AdministrativeAction = AdministrativeAction.block_user
                              ) -> Any:
    """For an administrative operation acting on an existing identity row, the stored `issuer`
    selects the Firebase integration whose Admin client performs the operation — including the
    refresh-token revocation that accompanies an operator block or an identity retirement. A
    stored issuer that no longer matches the configured one is a hard error, never a revocation
    against another project."""
    # [impl->req~schema-external-identities-stored-issuer-selects-admin-client~1]
    # [impl->req~sessions-integration-select-administrative~1]
    # [impl->req~sessions-integration-selection-fails-closed~1]
    return integrations.admin_client_for_stored_issuer(
        stored_issuer=row.issuer, site=ADMINISTRATIVE_ADMIN_CALL_SITES[action])


# Both administrative actions revoke Firebase refresh tokens through the same Admin mechanism
# `POST /auth/sign-out-all` uses. The coupling is normative: it is what makes the barrier's closure
# of that route to a blocked or retired subject complete, because the revocation such a subject can
# no longer request has already been performed for it. Revocation is defense-in-depth — it stops
# that subject's refresh tokens from minting new ID tokens, while already-issued ID tokens run to
# their own `exp`.
REVOCATION_MECHANISM: str = "firebase_admin_refresh_token_revocation"
REVOKING_ACTIONS: frozenset[AdministrativeAction] = frozenset(AdministrativeAction)


def administrative_revocation(action: AdministrativeAction, row: ExternalIdentityRow, *,
                              stored_provider_consulted: bool = False) -> str:
    """Blocking a user and marking an identity `historical` must each also revoke Firebase refresh
    tokens for the affected subject as part of that same operation, through the same Firebase Admin
    refresh-token revocation mechanism `POST /auth/sign-out-all` uses and regardless of the
    identity's stored provider classification."""
    # [impl->req~sessions-block-and-retire-revoke-refresh-tokens~1]
    if action not in REVOKING_ACTIONS:
        raise IdentityError(f"{action} revokes no refresh tokens")
    if stored_provider_consulted:
        raise IdentityError("revocation is unconditional, never keyed on the stored provider")
    if not revokes_refresh_tokens(row):
        raise IdentityError("every account's refresh tokens are revoked")
    return REVOCATION_MECHANISM


def administrative_revocation_result(*, revoked: bool) -> AuthEventResult:
    """Where these administrative paths audit their revocation outcome, they reuse the same
    `revocation_unconfirmed` value for a failed or ambiguous revocation rather than minting a
    parallel one."""
    # [impl->req~sessions-block-and-retire-revoke-refresh-tokens~1]
    parallel = sorted(result for result in AuthEventResult
                      if "revocation" in str(result)
                      and result is not AuthEventResult.revocation_unconfirmed)
    if parallel:
        raise IdentityError(f"{parallel} would be parallel revocation-outcome values")
    return AuthEventResult.succeeded if revoked else AuthEventResult.revocation_unconfirmed


def administrative_write(action: AdministrativeAction, *, revocation_failed: bool,
                         rollback_requested: bool = False) -> AdministrativeOutcome:
    """Commit the lifecycle write, then report the accompanying revocation. A revocation failure
    never rolls back or otherwise undoes that database state: it surfaces to the operator as an
    operational failure while the account stays blocked or retired and rejects on every route,
    and an operator may retry the revocation by hand.

    The lifecycle write commits first and stays authoritative: a revocation failure, a selection
    failure included, never undoes it, and it surfaces to the operator as an operational failure
    rather than being swallowed.

    When the revocation fails or leaves the outcome ambiguous nothing further is done about the
    surviving refresh tokens: no automated retry, no compensation machinery, no revocation-pending
    marker, queue or scheduled job, and no user-visible partial-failure state. The account stays
    blocked or retired and rejecting on every route whatever the revocation outcome was."""
    # [impl->req~schema-external-identities-stored-issuer-selects-admin-client~1]
    # [impl->req~sessions-database-change-first-on-revocation~1]
    # [impl->req~sessions-block-and-retire-revoke-refresh-tokens~1]
    # [impl->req~sessions-revocation-failure-no-compensation~1]
    if rollback_requested:
        raise IdentityError("a revocation failure never undoes the committed lifecycle write")
    if REVOCATION_FAILURE_MACHINERY:
        raise IdentityError("no retry, compensation, marker or queue exists for a revocation")
    return AdministrativeOutcome(action=action,
                                 lifecycle_write=LIFECYCLE_WRITES[action],
                                 committed=True,
                                 revocation_failed=revocation_failed,
                                 operator_retry_available=revocation_failed)


# --- Creating the user and identity pair ------------------------------------------------------------

# Every path that creates an account. The list is open-ended by design: the rule binds any
# account-creating path, named here or not.
ACCOUNT_CREATING_PATHS: frozenset[str] = frozenset({
    "anonymous_creation", "registered_creation", "upgrade_completion_of_account_created_that_way",
})

# The transaction is the entire guarantee. No cross-table constraint, trigger, deferrable foreign
# key, or background healer enforces the pairing, and none is to be added.
PAIRING_ENFORCEMENT_MECHANISMS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class AccountCreation:
    """The two rows an account-creating path writes, and the transaction they share."""
    user_id: UUID
    identity: ExternalIdentityRow
    transaction: object


def create_account(*, user_id: UUID, identity: ExternalIdentityRow, user_transaction: object,
                   identity_transaction: object,
                   existing_identity_for_user: ExternalIdentityRow | None = None) -> AccountCreation:
    """A user row and its external identity row are created together in one transaction, so if
    either insert fails the whole transaction rolls back and no account exists. `UNIQUE (user_id)`
    caps a user at one identity row, and because identity rows are never removed, creation is the
    only point at which the pairing could break."""
    # The transaction is the whole of the enforcement: no cross-table constraint, trigger,
    # deferrable foreign key or scheduled healer backs it, and none is to be added.
    # [impl->req~schema-external-identities-user-and-identity-one-transaction~1]
    # [impl->req~schema-invariant-07~1]
    # Every creating path writes the two rows together, and `UNIQUE (user_id)` caps a user at
    # one identity row.
    # [impl->req~users-account-and-identity-row-atomic~1]
    # [impl->req~users-rule-unique-user-id~1]
    if user_transaction is not identity_transaction:
        raise IdentityError("the user row and its identity row are written in one transaction")
    if PAIRING_ENFORCEMENT_MECHANISMS:
        raise IdentityError("no constraint, trigger, deferrable key or healer enforces the pairing")
    if identity.user_id != user_id:
        raise IdentityError("the identity row belongs to the user created with it")
    if existing_identity_for_user is not None:
        raise IdentityError("UNIQUE (user_id) caps a user at one identity row")
    return AccountCreation(user_id=user_id, identity=identity, transaction=user_transaction)


def resolve_owner(row: ExternalIdentityRow | None, *, user_id: UUID) -> UUID:
    """Resolve the owner of a `core.users` row through its identity row. A user row found without
    one is an unresolvable owner and an internal error: the read path fails closed, and no path
    invents an identity row, reassigns the account, or repairs it in the background."""
    # An account with zero identity rows is unresolvable by design: the path that meets one
    # fails closed rather than inventing an identity row or reassigning the account. This is the
    # arrival point of every lookup that comes in by user id — a support query, a server-side
    # attribution lookup — and `core.users.id` never authenticates anyone here: it only names an
    # owner whose identity row must already exist.
    # [impl->req~schema-external-identities-orphan-user-internal-error~1]
    # [impl->req~sessions-users-id-not-auth-key~1]
    # [impl->req~schema-invariant-07~1]
    # [impl->req~users-account-and-identity-row-atomic~1]
    if row is None:
        return _orphan(user_id)
    return row.user_id


def _orphan(user_id: UUID) -> NoReturn:
    # The orphan read fails closed with `internal_error`; the row itself is left in place.
    # [impl->req~schema-external-identities-orphan-user-internal-error~1]
    read_orphan_user(user_id)


# --- Uniqueness ---------------------------------------------------------------------------------


class IdentityAlreadyLinkedError(IdentityError):
    """The verified `(issuer, subject)` already belongs to a user."""

    result = AuthEventResult.identity_already_linked
    client_class = ClientErrorClass.identity_already_linked


class AlreadyLinkedSite(StrEnum):
    """The three places the already-linked rejection is taken."""
    prepare_phase_check = "prepare_phase_check"
    completion_identity_reresolution = "completion_identity_reresolution"
    uniqueness_race_loser = "uniqueness_race_loser"


def already_linked_result(site: AlreadyLinkedSite) -> AuthEventResult:
    """`identity_already_linked` is the single audit result for the already-linked
    `POST /auth/create-user` rejection at all three sites; there is no per-site variant."""
    # [impl->req~schema-external-identities-identity-already-linked-result~1]
    if site not in set(AlreadyLinkedSite):
        raise IdentityError(f"{site} is not an already-linked rejection site")
    return AuthEventResult.identity_already_linked


@dataclass(frozen=True, slots=True)
class RaceLoserOutcome:
    """What the losing `create-user` completion transaction leaves behind: nothing."""
    result: AuthEventResult
    client_class: ClientErrorClass
    rolled_back: frozenset[str]


# Every business mutation the losing transaction rolls back: no `core.users` row, no
# `core.external_identities` row and no grant survive it. A per-device grant-state read is rolled
# back with the rest — the loser neither reads nor modifies per-device grant state — so grant side
# effects belong to the winning insert path alone, keyed on the new `core.users.id`.
# [impl->req~sessions-grant-side-effects-winner-only~1]
RACE_LOSER_ROLLBACK: frozenset[str] = frozenset({
    "user_row", "identity_row", "grant", "per_device_grant_state_read",
    "per_device_grant_state_write",
})

# The only race controls a `create-user` completion needs: atomic challenge consumption and these
# unique constraints. Nothing else is added — no serializable isolation level, no distributed
# lock, no compare-and-swap generation on a pre-auth subject, and no cancellation of the loser's
# challenge beyond its single-use consumption.
# [impl->req~sessions-create-user-race-controls-bounded~1]
CREATE_USER_RACE_CONTROLS: frozenset[str] = frozenset({
    "atomic_challenge_consumption", "unique_issuer_subject", "unique_user_id"})
FORBIDDEN_RACE_CONTROLS: frozenset[str] = frozenset()


def uniqueness_race_loser() -> RaceLoserOutcome:
    """`UNIQUE (issuer, subject)` together with `UNIQUE (user_id)` is the final arbiter when two
    `create-user` completion transactions both observe an unlinked subject. The uniqueness
    violation never escapes as a generic server error and is never audited as
    `invalid_external_jwt`."""
    # [impl->req~schema-external-identities-uniqueness-race-arbiter~1]
    # [impl->req~sessions-create-user-unique-constraint-arbiter~1]
    # [impl->req~sessions-create-user-race-controls-bounded~1]
    if FORBIDDEN_RACE_CONTROLS or "unique_issuer_subject" not in CREATE_USER_RACE_CONTROLS:
        raise IdentityError("the unique constraints and single-use are the whole race control")
    result = already_linked_result(AlreadyLinkedSite.uniqueness_race_loser)
    if result in (AuthEventResult.internal_error, AuthEventResult.invalid_external_jwt):
        raise IdentityError("the uniqueness race loser audits as identity_already_linked")
    return RaceLoserOutcome(result=result,
                            client_class=ClientErrorClass(surface(result)[0]),
                            rolled_back=RACE_LOSER_ROLLBACK)


class ExternalIdentities:
    """The uniqueness constraints as the linking paths see them: `UNIQUE (issuer, subject)` over
    every row, anonymous and registered alike, and `UNIQUE (user_id)` over the owner."""

    def __init__(self) -> None:
        self._by_pair: dict[tuple[str, str], ExternalIdentityRow] = {}
        self._by_user: dict[UUID, ExternalIdentityRow] = {}

    def link(self, row: ExternalIdentityRow) -> ExternalIdentityRow:
        """Each external identity may belong to only one user. The uniqueness holds over every
        row, and `(issuer, subject)` is the lookup key auth-time resolution uses — a separate
        rule from the `(issuer, provider, provider_uid)` reservation, which reserves external
        provider accounts only."""
        # [impl->req~schema-external-identities-unique-issuer-subject~1]
        # [impl->req~users-rule-unique-issuer-subject~1]
        # [impl->req~users-rule-unique-user-id~1]
        assert_no_sentinel_provider_uid(row)
        if (row.issuer, row.subject) in self._by_pair:
            raise IdentityAlreadyLinkedError("this external identity already belongs to a user")
        if row.user_id in self._by_user:
            raise IdentityError("UNIQUE (user_id) caps a user at one identity row")
        self._by_pair[(row.issuer, row.subject)] = row
        self._by_user[row.user_id] = row
        return row

    def find(self, issuer: str, subject: str) -> ExternalIdentityRow | None:
        """Auth-time resolution by exact `(issuer, subject)`. `None` means no row matched, and
        because rows are never deleted, that means the identity was never linked."""
        # [impl->req~schema-external-identities-lookup-by-issuer-subject~1]
        # [impl->req~schema-external-identities-rows-never-deleted~1]
        assert_lookup_fields(IDENTITY_LOOKUP_KEY)
        return self._by_pair.get((issuer, subject))

    def replace_row(self, row: ExternalIdentityRow) -> ExternalIdentityRow:
        """Update a row in place. The pair and the owner never move."""
        stored = self._by_pair[(row.issuer, row.subject)]
        if stored.id != row.id or stored.user_id != row.user_id:
            raise IdentityError("an identity row is never reassigned")
        self._by_pair[(row.issuer, row.subject)] = row
        self._by_user[row.user_id] = row
        return row


def assert_no_sentinel_provider_uid(row: ExternalIdentityRow) -> None:
    """No sentinel or placeholder `provider_uid` is ever invented for an anonymous row: `NULL`
    there means no linked provider account, and no anonymous row is ever backfilled."""
    # [impl->req~schema-external-identities-unique-issuer-subject~1]
    # [impl->req~schema-external-identities-reservation-not-null-semantics~1]
    if row.provider is IdentityProvider.anonymous and row.provider_uid is not None:
        raise IdentityError("an anonymous row carries no placeholder provider_uid")


# --- The closed provider-derivation procedure -------------------------------------------------------

# Provider derivation is one closed procedure, and these five stages are the whole of it, in
# order. Nothing outside them derives a provider: there is no second classifier, no per-request
# rederivation, and no reconciliation job. Every Firebase Admin `getUser(subject)` `providerData`
# read a stage names runs on the integration selected under Firebase Integration Selection — the
# request-driven selector in `integration.py` — and never on an ambient or default Admin client.
# [impl->req~sessions-provider-derivation-closed-procedure~1]
PROVIDER_DERIVATION_STAGES: tuple[tuple[str, str], ...] = (
    ("call_sites", "assert_provider_data_read_point"),
    ("lookup_failure", "provider_from_lookup"),
    ("classifier", "classify_provider"),
    ("declaration_match", "assert_declared_provider"),
    ("persistence", "write_provider_uid"),
)


class ProviderDeclarationMismatchError(IdentityError):
    """The classified provider does not equal the client-declared one."""

    def __init__(self, classified: IdentityProvider, declared: IdentityProvider):
        self.classified = classified
        self.declared = declared
        super().__init__(f"the lookup classified {classified}, not the declared {declared}")


def provider_derivation_stage(name: str) -> str:
    """The named stage of the closed procedure. Anything else is not part of provider derivation,
    so no path can grow a sixth stage — or a private classifier — without failing here."""
    # [impl->req~sessions-provider-derivation-closed-procedure~1]
    for stage, entry_point in PROVIDER_DERIVATION_STAGES:
        if stage == name:
            return entry_point
    raise ProviderClassificationError(f"{name} is not a stage of provider derivation")


def assert_declared_provider(classified: IdentityProvider,
                             declared: IdentityProvider | None) -> IdentityProvider:
    """Declaration match, in the one place both declaring call sites read it: wherever the API
    carries a client-declared provider — registered `create-user` and `upgrade-anonymous` — the
    classified provider must equal the declaration, and a mismatch rejects the operation with no
    mutation. Each call site maps this mismatch onto its own client class; none of them resolves
    the disagreement in favour of the declaration."""
    # [impl->req~sessions-declaration-match~1]
    provider_derivation_stage("declaration_match")
    if declared is not None and classified is not declared:
        raise ProviderDeclarationMismatchError(classified, declared)
    return classified


# --- The provider classification -------------------------------------------------------------------


class ProviderSource(StrEnum):
    """Where a provider classification was offered from."""
    firebase_admin_provider_data = "firebase_admin_provider_data"
    client_declaration = "client_declaration"
    token_claim = "token_claim"
    request_header = "request_header"
    stored_profile_data = "stored_profile_data"


def assert_provider_source(source: ProviderSource) -> None:
    """`provider` is derived exclusively from the Firebase Admin `getUser(subject)` `providerData`
    lookup. Token claims and HTTP headers are never a provider source."""
    # [impl->req~schema-external-identities-provider-closed-classifier~1]
    if source is not ProviderSource.firebase_admin_provider_data:
        raise ProviderClassificationError(f"{source} is not a provider source")


class _ProviderDataEntry:
    """One normalized `providerData` entry, whatever shape the Admin SDK handed back."""
    __slots__ = ("provider_id",)

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id


# Entry normalization is the invariants module's, shared with `provider_uid_from_provider_data`
# so classification and uid derivation accept exactly the same `providerData` shapes.
_provider_id = provider_data_id


def classify_provider(provider_data: Sequence[object]) -> IdentityProvider:
    """The closed classifier: no entries means `anonymous`; exactly one entry whose `providerId`
    is `google.com` means `google`; exactly one entry whose `providerId` is `apple.com` means
    `apple`. Every other shape rejects the operation with no persistence — entries for both
    providers, multiple entries, or any entry whose `providerId` is neither recognized value.
    The first recognized entry is never selected, and non-empty `providerData` is never
    classified as `anonymous`."""
    # [impl->req~schema-external-identities-provider-closed-classifier~1]
    provider_derivation_stage("classifier")
    assert_provider_source(ProviderSource.firebase_admin_provider_data)
    entries = [_ProviderDataEntry(_provider_id(entry)) for entry in provider_data]
    try:
        classified = FirebaseIntegrations.classify_provider(entries)
    except UnrecognizedProviderError as exc:
        raise ProviderClassificationError(str(exc)) from None
    return IdentityProvider(classified)


class LookupFailure(StrEnum):
    """Why a required Firebase Admin `getUser(subject)` lookup produced no usable record."""
    user_not_found = "user_not_found"
    transient = "transient"
    infrastructure = "infrastructure"
    malformed_response = "malformed_response"
    indeterminate = "indeterminate"


# The subject deleted at Firebase is the one non-retryable failure; every other shape — transient,
# infrastructure, malformed, or otherwise indeterminate — is the retryable one, audited
# distinctly from a client-sent bad provider.
# The failure classes stay distinct: `user-not-found` — the subject deleted at Firebase between
# token mint and the call — is the non-retryable external-identity failure, audited as its own
# internal result and surfaced through the existing `auth_required` class, so a still-valid token
# for a deleted Firebase user creates and upgrades nothing. Transient and infrastructure failures
# — timeout, 5xx, quota, and permission errors, the last indicating misconfiguration — are
# retryable, audited as `firebase_lookup_unavailable`, and surfaced as
# `verification_temporarily_unavailable` once the in-request retry budget is exhausted.
# [impl->req~sessions-failure-classes-distinct~1]
# [impl->req~sessions-failure-user-not-found~1]
# [impl->req~sessions-failure-transient-unavailable~1]
_LOOKUP_FAILURE_RESULTS: dict[LookupFailure, AuthEventResult] = {
    LookupFailure.user_not_found: AuthEventResult.firebase_user_unresolved,
    LookupFailure.transient: AuthEventResult.firebase_lookup_unavailable,
    LookupFailure.infrastructure: AuthEventResult.firebase_lookup_unavailable,
    LookupFailure.malformed_response: AuthEventResult.firebase_lookup_unavailable,
    LookupFailure.indeterminate: AuthEventResult.firebase_lookup_unavailable,
}

# What a failed provider derivation persists: nothing, anywhere.
LOOKUP_FAILURE_PERSISTS: frozenset[str] = frozenset()


def provider_from_lookup(record: Sequence[object] | None, *,
                         failure: LookupFailure | None = None) -> IdentityProvider:
    """A provider-derivation write proceeds only from a successful, well-formed
    `getUser(subject)` record. A failed, malformed, or indeterminate lookup is never treated as
    an empty `providerData` result and never falls back to a client-declared provider, token
    claim, request header, or stored profile data. It persists nothing anywhere.

    An operation proceeds only after the lookup returns a successful, well-formed record: a
    timeout, a permission or configuration error, a malformed response, a missing `providerData`,
    a 5xx or a quota error each stop it here, and no cached earlier provider value stands in.
    Nothing is persisted on failure — no `provider`, no `registered_at`, no email, no grant."""
    # [impl->req~schema-external-identities-provider-lookup-fail-closed~1]
    # [impl->req~sessions-providerdata-lookup-failure~1]
    provider_derivation_stage("lookup_failure")
    if failure is not None or record is None:
        raise _lookup_failure(failure or LookupFailure.indeterminate)
    # A malformed record is detected here, not left to escape as a bare shape error: anything
    # that is not a sequence of readable entries is a malformed response.
    if isinstance(record, str | bytes) or not isinstance(record, Sequence):
        raise _lookup_failure(LookupFailure.malformed_response)
    return classify_provider(record)


def _lookup_failure(failure: LookupFailure) -> ProviderLookupFailedError:
    # [impl->req~schema-external-identities-provider-lookup-fail-closed~1]
    if LOOKUP_FAILURE_PERSISTS:
        raise IdentityError("a failed provider lookup persists nothing")
    result = _LOOKUP_FAILURE_RESULTS[failure]
    client_class = ClientErrorClass(surface(result)[0])
    return ProviderLookupFailedError(result, client_class,
                                     retryable=failure is not LookupFailure.user_not_found)


# --- What the stored provider decides ---------------------------------------------------------------


class ProviderConsumer(StrEnum):
    """Per-request decisions that read the stored classification."""
    registered_grant_gating = "registered_grant_gating"
    claim_path = "claim_path"
    authorization_branch = "authorization_branch"
    audit_branch = "audit_branch"
    entitlement_handling = "entitlement_handling"
    refresh_token_revocation = "refresh_token_revocation"


# Firebase refresh-token revocation is explicitly not a consumer.
PROVIDER_CONSUMERS: frozenset[ProviderConsumer] = frozenset(set(ProviderConsumer) -
                                                            {ProviderConsumer.refresh_token_revocation})


def authoritative_provider(row: ExternalIdentityRow,
                           consumer: ProviderConsumer) -> IdentityProvider:
    """Once an identity row exists, its stored `provider` is authoritative for every per-request
    decision that depends on the classification. Revocation is unconditional for every account
    and never reads or branches on the stored `provider`.

    The stored value is the sole classifier for every identity, authorization, entitlement,
    grant-class and audit decision made per request: the linked user's `registered_at` is a
    reporting and profile timestamp and never a competing classifier, and no general authenticated
    request rederives the provider or the anonymous-versus-registered classification."""
    # Every consumer of the classification reads the stored value: registered-grant gating and
    # claim paths, authorization and audit branches on anonymous versus registered, and every
    # other per-request decision.
    # [impl->req~schema-external-identities-stored-provider-authoritative~1]
    # [impl->req~sessions-stored-provider-sole-classifier~1]
    # [impl->req~sessions-consumers-read-stored-classification~1]
    if consumer not in PROVIDER_CONSUMERS:
        raise IdentityError(f"{consumer} never reads the stored provider")
    return row.provider


def revokes_refresh_tokens(row: ExternalIdentityRow) -> bool:
    """Revocation is unconditional: it applies to every account whatever the stored provider.

    `POST /auth/sign-out-all` is therefore explicitly not a consumer of the stored classification:
    its revocation is unconditional for every account and is never keyed on the stored provider."""
    # [impl->req~schema-external-identities-stored-provider-authoritative~1]
    # [impl->req~sessions-consumers-read-stored-classification~1]
    if ProviderConsumer.refresh_token_revocation in PROVIDER_CONSUMERS:
        raise IdentityError("refresh-token revocation never reads the stored classification")
    return True


# What the stored `provider` is: a record of a server-confirmed registration transition. Live
# `providerData` reports current links, which is why it is unsuitable as a permanent mirror, and
# why an unlink or a bad write may leave the two disagreeing indefinitely.
STORED_PROVIDER_SEMANTICS: str = "monotonic_server_confirmed_transition"
STORED_PROVIDER_MIRRORS: frozenset[str] = frozenset()
HOT_PATH_RECONCILIATION: frozenset[str] = frozenset()


def assert_stored_provider_not_a_mirror(*, live_provider: IdentityProvider,
                                        row: ExternalIdentityRow) -> ExternalIdentityRow:
    """The stored `provider` records a monotonic, server-confirmed registration transition rather
    than a mirror of the user's currently linked Firebase providers, so a Firebase-side unlink or a
    bad write may leave the stored `provider` and `registered_at` disagreeing with live
    `providerData` indefinitely. After write time the backend never reconciles the two on the hot
    path: the divergence is tolerated and the row is returned unchanged."""
    # [impl->req~sessions-stored-provider-not-a-mirror~1]
    if STORED_PROVIDER_MIRRORS or STORED_PROVIDER_SEMANTICS != "monotonic_server_confirmed_transition":
        raise IdentityError("the stored provider is no mirror of live providerData")
    if HOT_PATH_RECONCILIATION or PROVIDER_RECONCILIATION_JOBS:
        raise IdentityError("the backend never reconciles against providerData after write time")
    if live_provider not in set(IdentityProvider):
        raise IdentityError(f"{live_provider} is no classified live provider")
    return row


# --- `provider_uid` -------------------------------------------------------------------------------


class ProviderUidSource(StrEnum):
    """Where a `provider_uid` was offered from."""
    firebase_provider_data = "firebase_provider_data"
    client_input = "client_input"
    request_header = "request_header"
    token_claim = "token_claim"
    email = "email"
    display_name = "display_name"


def assert_provider_uid_source(source: ProviderUidSource) -> None:
    """`provider_uid` is never taken from client input, headers, token claims, email, or display
    name."""
    # [impl->req~schema-external-identities-provider-uid-never-client-input~1]
    if source is not ProviderUidSource.firebase_provider_data:
        raise IdentityError(f"provider_uid is never taken from {source}")


def provider_uid_for(provider: IdentityProvider,
                     provider_data: Sequence[object]) -> str | None:
    """`provider_uid` is `NULL` for `anonymous` identities and, for `google` or `apple`, the
    non-empty stable `uid` from the `providerData` entry whose `providerId` matches the confirmed
    provider: the Google account ID for Google and the per-app Apple user identifier for Apple."""
    # It comes out of the same `getUser(subject)` read that confirmed the provider — it costs no
    # further Firebase Admin call — and only from the entry whose `providerId` matches the
    # confirmed provider, never from client input, headers, token claims, email or display name.
    # [impl->req~schema-external-identities-provider-uid-source~1]
    # [impl->req~users-provider-uid-source-and-immutability~1]
    # [impl->req~sessions-provider-uid-from-same-read~1]
    assert_provider_uid_source(ProviderUidSource.firebase_provider_data)
    try:
        return provider_uid_from_provider_data(provider, provider_data)
    except InvariantError:
        # A record that classified but carries no readable uid for the confirmed provider is a
        # malformed lookup response, not a bare shape error: it is audited as
        # `firebase_lookup_unavailable` and surfaces `verification_temporarily_unavailable`.
        # [impl->req~schema-external-identities-provider-lookup-fail-closed~1]
        raise _lookup_failure(LookupFailure.malformed_response) from None


# The two read points that may write the stored `provider` or `provider_uid`.
PROVIDER_WRITING_READ_POINTS: frozenset[ProviderDataReadPoint] = frozenset({
    ProviderDataReadPoint.anonymous_create_user_completion,
    ProviderDataReadPoint.registered_create_user_completion,
    ProviderDataReadPoint.upgrade_anonymous_completion,
})

# The two read-only live matches against both stored values; they persist neither field.
PROVIDER_READ_ONLY_READ_POINTS: frozenset[ProviderDataReadPoint] = frozenset({
    ProviderDataReadPoint.web_anonymous_grant_gate,
    ProviderDataReadPoint.claim_registered_grant_completion,
})

# No background, scheduled, or periodic job reconciles the stored value against live Firebase.
PROVIDER_RECONCILIATION_JOBS: frozenset[str] = frozenset()


def assert_provider_data_read_point(point: ProviderDataReadPoint | str) -> ProviderDataReadPoint:
    """The five `providerData` read points are the complete set. No other operation reads
    `providerData`, and the backend does not rederive the classification on ordinary
    authenticated requests.

    The enumeration is closed and it is the procedure's own call-site stage: every
    `getUser(subject)` `providerData` read happens at one of these points, each of which persists
    or gates provider-dependent state. `POST /auth/sync`, `GET /users/me` and every other ordinary
    authenticated request perform no such read, and no background or periodic reconciliation job
    and no admin reconciliation surface exists to perform one either."""
    # [impl->req~schema-external-identities-provider-data-five-read-points~1]
    # [impl->req~sessions-providerdata-read-call-sites~1]
    provider_derivation_stage("call_sites")
    if point not in set(ProviderDataReadPoint):
        raise IdentityError(f"{point} is not one of the five providerData read points")
    if PROVIDER_RECONCILIATION_JOBS:
        raise IdentityError("no job reconciles the stored provider against live Firebase state")
    return ProviderDataReadPoint(point)


def assert_may_write_provider_fields(point: ProviderDataReadPoint) -> None:
    """Only identity creation and `upgrade-anonymous` write stored `provider` or `provider_uid`;
    the web anonymous-grant gate and the mandatory fail-closed `claim_registered_grant`
    confirmation are read-only and persist neither field."""
    # [impl->req~schema-external-identities-provider-data-five-read-points~1]
    assert_provider_data_read_point(point)
    if point not in PROVIDER_WRITING_READ_POINTS:
        raise IdentityError(f"{point} persists neither provider nor provider_uid")


def assert_live_provider_data_scope(point: ProviderDataReadPoint) -> ProviderDataReadPoint:
    """Deciding on the stored classification has exactly two exceptions, and both are free-grant
    gates that read live `providerData`: the web anonymous-grant sign-in gate and the mandatory
    `claim_registered_grant` confirmation. Each requires the live data to match both the stored
    `provider` and the stored `provider_uid`, and a mismatch denies only the free grant — it
    rewrites neither stored value and blocks neither login nor paid subscription access. The
    upgrade endpoint is not among them: a divergent upgrade call is refused, never reconciled."""
    # [impl->req~sessions-live-providerdata-only-at-grant-gates~1]
    if point not in PROVIDER_READ_ONLY_READ_POINTS:
        raise IdentityError(f"{point} is no live-providerData free-grant gate")
    if PROVIDER_READ_ONLY_READ_POINTS & PROVIDER_WRITING_READ_POINTS:
        raise IdentityError("a read-only gate never persists provider or provider_uid")
    return assert_provider_data_read_point(point)


def registered_grant_class_inputs(row: ExternalIdentityRow, *,
                                  registered_at: datetime | None,
                                  grant_history_exhausted: bool) -> bool:
    """Registered-grant eligibility keys on backend-stored registration state — the stored
    classification and `registered_at`, together with the account's own grant history — and never
    on live Firebase state. A user who unlinks in Firebase stays in the registered grant class,
    because the account did register and `registered_at` is set, and at most one registered grant
    is ever claimable per account.

    The other half of that rule — `claim_registered_grant`'s mandatory fail-closed `providerData`
    confirmation of the stored binding on every call — is `confirm_registered_binding`, and lives
    there rather than being restated here: eligibility takes no live input, so a live result
    cannot make an ineligible account eligible or an eligible one ineligible.
    """
    # [impl->req~sessions-registered-grant-keys-on-stored-state~1]
    stored = authoritative_provider(row, ProviderConsumer.registered_grant_gating)
    if stored not in REGISTERED_PROVIDERS or registered_at is None:
        return False
    return not grant_history_exhausted


def write_provider_uid(row: ExternalIdentityRow, provider_uid: str | None, *,
                       provider: IdentityProvider | None = None,
                       row_transaction: object, uid_transaction: object) -> ExternalIdentityRow:
    """Identity creation writes `provider_uid` in the same transaction as the identity row; the
    anonymous-to-registered upgrade assigns it in the same transaction as the in-place
    transition, so the provider flip and its UID land together or not at all.

    This is the procedure's persistence stage: the classified provider, `provider_uid`,
    `registered_at` and any verified-email copy are written together in the single completion
    transaction, so stored `provider` and `registered_at` are aligned by construction."""
    # [impl->req~schema-external-identities-provider-uid-same-transaction~1]
    # [impl->req~sessions-provider-persistence-single-transaction~1]
    provider_derivation_stage("persistence")
    if row_transaction is not uid_transaction:
        raise IdentityError("provider_uid is written in the identity row's own transaction")
    return replace(row, provider=provider or row.provider, provider_uid=provider_uid)


# The one operation that may move `provider_uid` off `NULL`.
PROVIDER_UID_ASSIGNING_OPERATION: AuthOperation = AuthOperation.upgrade_anonymous_to_registered


def assign_provider_uid(stored: str | None, incoming: str | None, *,
                        operation: AuthOperation) -> str | None:
    """Once assigned, `provider_uid` is immutable. Its sole assignment transition is from `NULL`
    to the confirmed registered provider's UID during the in-place anonymous-to-registered
    upgrade."""
    # Its sole assignment transition on an existing row is the in-place anonymous-to-registered
    # upgrade; registered-to-registered rebinding is unsupported.
    # [impl->req~schema-external-identities-provider-uid-immutable~1]
    # [impl->req~users-provider-uid-source-and-immutability~1]
    assert_provider_uid_immutable(stored, incoming)
    if stored is None and incoming is not None and operation is not PROVIDER_UID_ASSIGNING_OPERATION:
        raise IdentityError(f"{operation} does not assign provider_uid")
    return incoming if stored is None else stored


# --- The provider-account reservation -----------------------------------------------------------------

# The reservation is a partial unique index restricted to rows where `provider_uid IS NOT NULL`,
# never a table-wide `UNIQUE` constraint.
RESERVATION_INDEX_COLUMNS: tuple[str, str, str] = ("issuer", "provider", "provider_uid")
RESERVATION_INDEX_PREDICATE: str = "provider_uid IS NOT NULL"

# `UNIQUE NULLS NOT DISTINCT` must not be used here: on the plain constraint it would admit only
# one `NULL` `provider_uid` per `(issuer, provider)` and break anonymous account creation.
FORBIDDEN_RESERVATION_OPTIONS: frozenset[str] = frozenset({"NULLS NOT DISTINCT"})

# The reservation applies to both `active` and `historical` rows.
RESERVED_IDENTITY_STATES: frozenset[IdentityState] = frozenset(IdentityState)


def assert_reservation_index(*, columns: Sequence[str], predicate: str,
                             table_wide_unique: bool = False,
                             options: Iterable[str] = ()) -> None:
    """The provider-account reservation is the partial unique index on
    `(issuer, provider, provider_uid)` restricted to rows where `provider_uid IS NOT NULL`. The
    restriction states the business rule directly — the reservation covers registered provider
    accounts only — rather than leaning on the SQL rule that `NULL`s compare as distinct."""
    # The reservation is a partial unique index, never a table-wide `UNIQUE`, and it leaves
    # anonymous rows — whose `provider_uid` is `NULL` — outside it entirely.
    # [impl->req~schema-external-identities-provider-account-reservation-index~1]
    # [impl->req~schema-external-identities-reservation-not-null-semantics~1]
    # [impl->req~users-rule-partial-unique-provider-account~1]
    if table_wide_unique:
        raise IdentityError("the reservation is a partial unique index, not a table-wide UNIQUE")
    if tuple(columns) != RESERVATION_INDEX_COLUMNS:
        raise IdentityError(f"the reservation is keyed on {RESERVATION_INDEX_COLUMNS}")
    if predicate != RESERVATION_INDEX_PREDICATE:
        raise IdentityError(f"the reservation is restricted to {RESERVATION_INDEX_PREDICATE}")
    offending = sorted(set(options) & FORBIDDEN_RESERVATION_OPTIONS)
    if offending:
        raise IdentityError(f"{offending} must not be used on the reservation")


def in_reservation_scope(row: ExternalIdentityRow) -> bool:
    """Whether a row falls inside the reservation. Anonymous rows carry `provider_uid IS NULL`,
    fall wholly outside the index, and coexist without limit, so a later `NULLS NOT DISTINCT`
    change, a port to another dialect, or a well-meant tightening cannot break anonymous account
    creation."""
    # `historical` rows stay inside the reservation, so administrative retirement never frees
    # a provider account for reuse.
    # [impl->req~schema-external-identities-reservation-not-null-semantics~1]
    # [impl->req~users-rule-partial-unique-provider-account~1]
    if row.identity_state not in RESERVED_IDENTITY_STATES:
        raise IdentityError("the reservation applies to active and historical rows alike")
    return provider_uid_reserved(row.provider, row.provider_uid)


# The two provider-binding writes. A conflict on either leaves all database state unmodified.
PROVIDER_BINDING_WRITES: frozenset[AuthOperation] = frozenset({
    AuthOperation.create_user,
    AuthOperation.upgrade_anonymous_to_registered,
})

# What a `provider_account_already_linked` rejection may change: nothing. The stored row is never
# auto-rewritten and the reserved provider UID is never reassigned to the requesting identity; a
# manual operator fix is the only remedy.
PROVIDER_CONFLICT_MUTATIONS: frozenset[str] = frozenset()
PROVIDER_CONFLICT_REMEDY: str = "manual_operator_fix"


def provider_account_conflict(operation: AuthOperation) -> ProviderAccountAlreadyLinkedError:
    """The rejection either provider-binding write takes on a conflict on
    `(issuer, provider, provider_uid)`: `provider_account_already_linked`, surfaced through the
    shared `operation_not_allowed` client class, leaving identity, user, grant and profile state
    exactly as they were."""
    # [impl->req~schema-external-identities-provider-account-already-linked~1]
    if operation not in PROVIDER_BINDING_WRITES:
        raise IdentityError(f"{operation} performs no provider binding")
    if PROVIDER_CONFLICT_MUTATIONS:
        raise IdentityError("a provider-account conflict modifies no database state")
    error = ProviderAccountAlreadyLinkedError("this provider account is already bound to a user")
    if ClientErrorClass(surface(error.result)[0]) is not ClientErrorClass.operation_not_allowed:
        raise IdentityError("the conflict surfaces through operation_not_allowed")
    return error


# --- Provider transitions ---------------------------------------------------------------------------

# The only permitted provider transition is the in-place anonymous-to-registered one. There is no
# registered-to-anonymous transition, and no registered-to-registered one either.
PERMITTED_PROVIDER_TRANSITIONS: frozenset[tuple[IdentityProvider, IdentityProvider]] = frozenset(
    (IdentityProvider.anonymous, registered) for registered in REGISTERED_PROVIDERS)


def assert_provider_transition(stored: IdentityProvider, incoming: IdentityProvider) -> None:
    """The stored `provider` records a monotonic, server-confirmed registration transition; it is
    not a mirror of the providers currently linked in Firebase, so a live change never rewrites
    it backwards or sideways."""
    # [impl->req~schema-external-identities-provider-monotonic-transition-record~1]
    # [impl->req~schema-external-identities-only-anonymous-to-registered~1]
    if stored is incoming:
        return
    if (stored, incoming) not in PERMITTED_PROVIDER_TRANSITIONS:
        raise IdentityError(f"{stored} to {incoming} is not a permitted provider transition")


def confirm_stored_binding(row: ExternalIdentityRow, *, live_provider: IdentityProvider,
                           live_provider_uid: str | None) -> None:
    """If a stored registered binding diverges from the Firebase Admin-confirmed live one, the
    operation is refused as `provider_transition_not_allowed` and the stored values are never
    automatically rewritten. An incorrect registered value requires a manual operator correction
    that no retry of the operation can substitute for."""
    # [impl->req~schema-external-identities-binding-divergence-refused~1]
    if row.provider is live_provider and row.provider_uid == live_provider_uid:
        return
    error = BindingDivergenceError(
        f"the stored binding for {row.issuer} diverges from the confirmed live one")
    if ClientErrorClass(surface(error.result)[0]) is not ClientErrorClass.operation_not_allowed:
        raise IdentityError("a divergent binding surfaces through operation_not_allowed")
    raise error


# --- `identity_state` ----------------------------------------------------------------------------------


def authorizes(identity_state: IdentityState) -> bool:
    """`active` means the identity may authorize normal authenticated API access; `historical`
    means the identity is retained for audit but must not."""
    # [impl->req~schema-external-identities-state-active-authorizes~1]
    # [impl->req~schema-external-identities-state-historical-no-authorize~1]
    return identity_state is IdentityState.active


def historical_identity_rejection() -> tuple[AuthEventResult, ClientRejection]:
    """Resolving a matching `historical` identity rejects as `historical_identity`, distinct in
    internal audit from `blocked_user`. Both surface the single shared `account_unavailable`
    client class with the same status, the same machine-readable code, the same generic copy, and
    no state-specific field, so clients cannot distinguish the two states."""
    # [impl->req~schema-external-identities-historical-identity-result~1]
    result = AuthEventResult.historical_identity
    if result is AuthEventResult.blocked_user:
        raise IdentityError("the two states keep distinct audit results")
    if surface(result) != surface(AuthEventResult.blocked_user):
        raise IdentityError("both states surface as the same class with the same status")
    rejection = client_response(ClientErrorClass.account_unavailable.value)
    if set(rejection.body) != {"code"}:
        raise IdentityError("the rejection carries no state-specific field")
    return result, rejection


# The complete `identity_state` transition set: one-way, administrative-only, permanent.
IDENTITY_STATE_TRANSITIONS: frozenset[tuple[IdentityState, IdentityState]] = frozenset(
    {(IdentityState.active, IdentityState.historical)})


# Flows that change `identity_state` on their own: none. `/auth/sync` and every auth-completion
# path leave it exactly as it was.
IDENTITY_STATE_CHANGING_FLOWS: frozenset[str] = frozenset()


def transition_identity_state(current: IdentityState, target: IdentityState, *,
                              administrative: bool) -> IdentityState:
    """The one-way `active` to `historical` transition. It is permanent and cannot be reversed,
    and only an administrative action makes it.

    That pair is the complete `identity_state` transition set. Retirement is permanent: no
    `historical` to `active` reversal exists, and no user-driven flow, `/auth/sync` or
    auth-completion path changes `identity_state` at all."""
    # [impl->req~schema-external-identities-state-transition-one-way~1]
    # [impl->req~sessions-identity-state-transition-set~1]
    # [impl->req~sessions-historical-administrative-only~1]
    if IDENTITY_STATE_CHANGING_FLOWS:
        raise IdentityError("no user-driven flow changes identity_state")
    if (current, target) not in IDENTITY_STATE_TRANSITIONS:
        raise IdentityError(f"{current} to {target} is not an identity_state transition")
    if not administrative:
        raise IdentityError("the transition is administrative-only")
    return target


# --- Retention, retirement and erasure ------------------------------------------------------------------

# Retirement, blocking and account teardown are state transitions rather than row removal.
IDENTITY_ROW_DELETERS: frozenset[str] = frozenset()

# Normal application and cleanup database roles have no permission to delete identity rows.
DELETE_PERMITTED_ROLES: frozenset[str] = frozenset()


def assert_no_identity_delete(actor: str) -> NoReturn:
    """External-identity rows are never physically deleted, and no normal application or cleanup
    database role has permission to delete one."""
    # Identity rows are never physically deleted; retirement and blocking are in-place state
    # transitions, and every `historical` row stays as a permanent tombstone.
    # [impl->req~schema-external-identities-rows-never-deleted~1]
    # [impl->req~schema-external-identities-no-delete-permission~1]
    # [impl->req~users-identity-rows-never-deleted~1]
    # [impl->req~users-rule-no-physical-delete~1]
    raise IdentityError(f"{actor} may not delete a core.external_identities row")


def may_delete_identity_rows(role: str) -> bool:
    """Whether a database role may delete external-identity rows. No normal application or
    cleanup role may."""
    # [impl->req~schema-external-identities-no-delete-permission~1]
    # [impl->req~users-rule-no-physical-delete~1]
    return role in DELETE_PERMITTED_ROLES


def never_linked(found: ExternalIdentityRow | None) -> bool:
    """Because rows are never deleted, no matching `(issuer, subject)` row means that identity
    was never linked — never that a linked identity was removed."""
    # [impl->req~schema-external-identities-rows-never-deleted~1]
    if IDENTITY_ROW_DELETERS:
        raise IdentityError("no path deletes an external-identity row")
    return found is None


def retire(row: ExternalIdentityRow, *, administrative: bool = True) -> ExternalIdentityRow:
    """Administrative retirement transitions `identity_state` and deletes or reassigns neither
    side of the user/identity pair.

    No user-driven flow marks an identity `historical` automatically: the state is retained only as
    an administrative or abuse-retirement state, and per-request resolution still rejects a
    `historical` identity wherever it is encountered. Retirement is expressed exclusively by
    setting the existing row's `identity_state` in place — never by removing a row."""
    # No flow in this split marks an identity `historical`: the transition stays administrative,
    # and the tombstone's retained `(issuer, subject)` reservation keeps a retired subject out of
    # pre-auth creation.
    # [impl->req~schema-external-identities-retirement-erasure-keep-pair~1]
    # [impl->req~users-identity-rows-never-deleted~1]
    # [impl->req~sessions-historical-administrative-only~1]
    # [impl->req~sessions-identity-rows-never-deleted~1]
    state = transition_identity_state(row.identity_state, IdentityState.historical,
                                      administrative=administrative)
    retired = replace(row, identity_state=state)
    if retired.id != row.id or retired.user_id != row.user_id:
        raise IdentityError("retirement is a state transition on the existing row")
    return retired


def block_user(row: ExternalIdentityRow, *, active: bool = False) -> tuple[str, IdentityState]:
    """Blocking is expressed exclusively by setting `core.users.active = FALSE`, which leaves the
    identity row `active` and linked so per-request resolution rejects it on the blocked-user path.
    Blocking a user does not mark that user's identity `historical`, and neither the `core.users`
    row nor the identity row is ever hard-deleted: a blocked or retired user keeps both."""
    # [impl->req~sessions-identity-rows-never-deleted~1]
    # [impl->req~sessions-block-immediate-for-backend~1]
    if active:
        raise IdentityError("a block is core.users.active = FALSE")
    if IDENTITY_ROW_DELETERS or row.identity_state is not IdentityState.active:
        raise IdentityError("blocking leaves the identity row active, linked and present")
    return LIFECYCLE_WRITES[AdministrativeAction.block_user], row.identity_state


# What a block disables, and what it deliberately does not. Operator-facing wording must say so
# rather than imply a durable ban on a person or a device.
BLOCK_SCOPE: tuple[str, str] = ("one core.users row", "one core.external_identities row")
BLOCK_NEVER_COVERS: frozenset[str] = frozenset({"person", "device", "fresh_anonymous_sign_in",
                                                "another_registered_account"})
# Evasion by minting a fresh anonymous subject is handled by the gateway limits on
# `POST /auth/create-user` and by the device-gated free-credit grants, not by the `active` flag.
BLOCK_EVASION_CONTROLS: tuple[str, ...] = ("create_user_gateway_limits",
                                           "device_gated_free_credit_grants")


def block_covers(target: str) -> bool:
    """A block disables one `core.users` row and one external identity: it does not disable a
    person and does not disable a device. A fresh anonymous sign-in, or another registered account,
    is a new identity the block does not cover."""
    # [impl->req~sessions-block-scope-one-account~1]
    if target in BLOCK_NEVER_COVERS:
        return False
    if "active_flag" in BLOCK_EVASION_CONTROLS:
        raise IdentityError("the active flag is not the anonymous-evasion control")
    return target in BLOCK_SCOPE


# The retained plaintext columns privacy erasure does not scrub: they are the uniqueness
# reservations that keep retirement permanent and re-registration of the same Google or Apple
# account rejectable, and they are retained for that purpose alone.
SCRUB_EXEMPT_COLUMNS: tuple[str, ...] = ("issuer", "subject", "provider", "provider_uid")

# Everything the tombstone keeps. Beyond the uniqueness reservations that is the non-PII
# `free_grant_consumed_at` marker and the `native_claim_platform` pin, which is immutable once
# set: clearing it would re-open the native-branch switch the pin exists to prevent on a row
# that is never deleted.
# [impl->req~schema-external-identities-native-claim-platform-pinned~1]
TOMBSTONE_RETAINED_COLUMNS: tuple[str, ...] = (
    *SCRUB_EXEMPT_COLUMNS, "identity_state", "native_claim_platform", "free_grant_consumed_at")

# The PII columns erasure clears on this row: none. The user's personal data — `email` and
# `display_name` — are `core.users` columns and are scrubbed there; every column on the identity
# row is either a uniqueness reservation or non-PII lifecycle state.
IDENTITY_PII_COLUMNS: tuple[str, ...] = ()

# The exception is deliberate and disclosed: the erasure rules in
# `01-sessions-and-identity-resolution.md` require the same disclosure to the user.
TOMBSTONE_DISCLOSURE_REQUIRED: bool = True


# The `core.users` profile columns a privacy or data-erasure request scrubs, and the rows erasure
# retains beside the identity tombstone: the canonical provider-account registry row and its
# per-gate consumption rows, so free-grant finality survives erasure for the account and for the
# Google or Apple provider account behind it.
ERASED_PROFILE_COLUMNS: tuple[str, str] = ("email", "display_name")
ERASURE_RETAINED_ROWS: tuple[str, ...] = ("core.external_identities",
                                          "core.provider_accounts",
                                          "core.provider_account_gate_consumptions")
# No cleanup, cascade or erasure path may remove a tombstoned identity row.
TOMBSTONE_REMOVERS: frozenset[str] = frozenset()


def erase_account(row: ExternalIdentityRow, *,
                  profile: dict[str, Any] | None = None) -> tuple[ExternalIdentityRow,
                                                                  dict[str, Any]]:
    """A privacy or data-erasure request scrubs PII — profile fields such as `email` and
    `display_name` — and business data, but retains the `(issuer, subject)` row as a `historical`
    tombstone. The retained `UNIQUE (issuer, subject)` constraint on that row is what keeps denying
    the erased subject a fresh pre-auth `POST /auth/create-user`, and no cleanup, cascade or
    erasure path may remove it. Erasure likewise retains the canonical `core.provider_accounts` row
    and its gate-consumption rows, and the tombstone keeps its non-PII `free_grant_consumed_at`
    marker, so neither the erased account nor its Google or Apple provider account may claim a free
    grant again: free-grant finality survives erasure."""
    # [impl->req~sessions-erasure-retains-tombstone~1]
    if TOMBSTONE_REMOVERS or IDENTITY_ROW_DELETERS:
        raise IdentityError("no cleanup, cascade or erasure path removes a tombstoned row")
    tombstone = erase_pii(row if row.identity_state is IdentityState.historical else retire(row))
    if tombstone.identity_state is not IdentityState.historical:
        raise IdentityError("erasure retains the row as a historical tombstone")
    if sorted(IDENTITY_LOOKUP_KEY) != sorted(("issuer", "subject")):
        raise IdentityError("the retained uniqueness reservation is (issuer, subject)")
    if tombstone.free_grant_consumed_at != row.free_grant_consumed_at:
        raise IdentityError("the non-PII free-grant marker survives erasure")
    if row.free_grant_consumed_at is not None and free_grant_available(
            tombstone, AuthOperation.claim_registered_grant):
        raise IdentityError("an erased account never claims a free grant again")
    scrubbed = dict(profile or {})
    for column in ERASED_PROFILE_COLUMNS:
        scrubbed[column] = None
    return tombstone, scrubbed


@dataclass(frozen=True, slots=True)
class ErasureDisclosure:
    """What the user-facing erasure confirmation must say, and how it says it."""
    retained_identifiers: tuple[str, ...]
    retained_in: tuple[str, ...]
    retained_purpose: tuple[str, ...]
    no_raw_subject_elsewhere: tuple[str, ...]
    display_only: bool


# The tables that hold only keyed hashes of the subject, which is why no raw subject is kept
# anywhere beyond the identity row and the provider-account registry.
HASHED_SUBJECT_TABLES: tuple[str, str] = ("core.auth_challenges", "audit.auth_events")
# The whole of why the retained identifiers are kept.
RETENTION_PURPOSES: tuple[str, str] = ("keep_the_account_retired",
                                       "reject_re_registration_of_the_same_provider_account")


def erasure_disclosure() -> ErasureDisclosure:
    """Erasure is deliberately not the removal of every personal identifier, and no erasure-facing
    wording may claim that it is. What is kept, in plaintext and indefinitely, is named plainly: the
    identity row's `issuer` and `subject`, and for a registered account the stored provider kind and
    its `provider_uid` — the stable Google account ID or the per-app Apple user identifier — held on
    the identity row and in the canonical `core.provider_accounts` registry. They are the uniqueness
    reservations that make retirement permanent and re-registration of the same Google or Apple
    account rejectable, and are retained for that purpose alone. The user-facing confirmation states
    the same thing, including that no raw subject is kept anywhere else because
    `core.auth_challenges` and `audit.auth_events` hold only keyed hashes of it; that copy is
    display-only and adds no acknowledgment step."""
    # [impl->req~sessions-erasure-retained-identifiers-disclosure~1]
    if tuple(SCRUB_EXEMPT_COLUMNS) != ("issuer", "subject", "provider", "provider_uid"):
        raise IdentityError("the disclosure names exactly the retained plaintext columns")
    if RAW_PROVIDER_ACCOUNT_STORES != {"core.external_identities", "core.provider_accounts"}:
        raise IdentityError("the retained identifiers live on the row and in the registry")
    if not TOMBSTONE_DISCLOSURE_REQUIRED:
        raise IdentityError("the retained identifiers are a disclosed exception")
    return ErasureDisclosure(retained_identifiers=tuple(SCRUB_EXEMPT_COLUMNS),
                             retained_in=tuple(sorted(RAW_PROVIDER_ACCOUNT_STORES)),
                             retained_purpose=RETENTION_PURPOSES,
                             no_raw_subject_elsewhere=HASHED_SUBJECT_TABLES,
                             display_only=True)


def erase_pii(row: ExternalIdentityRow) -> ExternalIdentityRow:
    """Privacy erasure scrubs PII around the `historical` identity tombstone while retaining the
    row and all of its uniqueness constraints. Neither retirement nor erasure deletes or
    reassigns either side of the user/identity pair, and the free-grant marker is non-PII and
    survives."""
    # [impl->req~schema-external-identities-historical-tombstone-scrub-exception~1]
    # [impl->req~schema-external-identities-retirement-erasure-keep-pair~1]
    # [impl->req~sessions-erasure-retains-tombstone~1]
    if not TOMBSTONE_DISCLOSURE_REQUIRED:
        raise IdentityError("the retained tombstone columns are a disclosed exception")
    # A retained column is never also a scrubbed one. This is what keeps the pin and the
    # uniqueness reservations out of the erasure set rather than trusting the call below.
    overlap = sorted(set(IDENTITY_PII_COLUMNS) & set(TOMBSTONE_RETAINED_COLUMNS))
    if overlap:
        raise IdentityError(f"{', '.join(overlap)} are retained by the tombstone, never scrubbed")
    scrubbed = replace(row, **dict.fromkeys(IDENTITY_PII_COLUMNS))
    for column in TOMBSTONE_RETAINED_COLUMNS:
        if getattr(scrubbed, column) != getattr(row, column):
            raise IdentityError(f"{column} is retained by the identity tombstone")
    if scrubbed.id != row.id or scrubbed.user_id != row.user_id:
        raise IdentityError("erasure retains the row and its owner")
    return scrubbed


# --- Upstream deletion at Firebase --------------------------------------------------------------------------

# The backend performs no deletion detection, synchronization, background or periodic
# reconciliation, or webhook handling for a provider-side account deletion.
FIREBASE_DELETION_SYNC_MECHANISMS: frozenset[str] = frozenset()


def assert_no_firebase_deletion_sync(mechanism: str) -> NoReturn:
    """Deletion of a Firebase account at the provider causes no automatic database transition:
    no automatic change to `identity_state` or `core.users.active`."""
    # [impl->req~schema-external-identities-no-firebase-deletion-sync~1]
    # [impl->req~sessions-upstream-deletion-no-backend-action~1]
    raise IdentityError(f"{mechanism} is not a provider-deletion synchronization mechanism")


def deletion_sync_transition(row: ExternalIdentityRow) -> None:
    """What an upstream Firebase deletion changes in the database: nothing. There is no detection,
    no synchronization, no background job, no webhook handling and no automatic flip to
    `historical`."""
    # [impl->req~schema-external-identities-no-firebase-deletion-sync~1]
    # [impl->req~sessions-upstream-deletion-no-backend-action~1]
    if FIREBASE_DELETION_SYNC_MECHANISMS:
        raise IdentityError("no deletion detection or reconciliation exists")
    return None


# Firebase Admin reads stay confined to the enumerated `providerData` read points: no
# user-existence or account-status check is added to the per-request path, because a per-request or
# polling check would couple availability to Firebase Admin on every request.
PER_REQUEST_FIREBASE_CHECKS: frozenset[str] = frozenset()


def assert_no_per_request_firebase_check(check: str | None = None) -> None:
    """No Firebase user-existence or account-status check runs on the per-request path, and every
    Firebase Admin read the backend makes is one of the enumerated `providerData` read points."""
    # [impl->req~sessions-no-per-request-firebase-existence-check~1]
    if PER_REQUEST_FIREBASE_CHECKS:
        raise IdentityError("no Firebase check is added to the per-request path")
    if check is not None:
        raise IdentityError(f"{check} is no enumerated providerData read point")
    if PROVIDER_WRITING_READ_POINTS | PROVIDER_READ_ONLY_READ_POINTS != frozenset(
            ProviderDataReadPoint):
        raise IdentityError("Firebase Admin reads stay confined to the enumerated read points")


# An already-minted ID token stays cryptographically valid until its own `exp`, for at most about
# one hour. Firebase stops refresh-token minting and does not reuse the UID.
STALE_ID_TOKEN_WINDOW: timedelta = timedelta(hours=1)


def resolves_through_stale_row(row: ExternalIdentityRow, *, token_exp: datetime,
                               now: datetime) -> bool:
    """After an upstream deletion, an already-minted ID token continues to resolve through the
    stale `active` identity row until its own `exp`. After those tokens expire the stale row may
    remain `active` indefinitely as an inert leftover.

    That is the accepted risk: verification checks signature, issuer, audience and temporal
    validity only, so such a token keeps resolving as a linked identity for up to about an hour.
    After that the subject can never present a valid token again, because deletion stops refresh
    and Firebase does not reuse subjects within a project — the same residual token window the
    specification already accepts for sign-out-everywhere refresh-token revocation."""
    # [impl->req~schema-external-identities-stale-token-window~1]
    # [impl->req~sessions-upstream-deletion-token-window-risk~1]
    if row.identity_state is not IdentityState.active:
        return False
    return now < token_exp


def stale_row_retirement_deadline(row: ExternalIdentityRow) -> datetime | None:
    """A stale `active` row has no scheduled retirement: it is retained indefinitely."""
    # [impl->req~schema-external-identities-stale-token-window~1]
    return None


class UpstreamDeletionRemedy(StrEnum):
    """The defined manual remedies when access must be terminated inside the remaining ID-token
    window, or the stale row should be retired for hygiene."""
    administrative_block = "administrative_block"
    administrative_retirement = "administrative_retirement"


def assert_upstream_deletion_remedy(remedy: UpstreamDeletionRemedy | str) -> UpstreamDeletionRemedy:
    """Upstream deletion is an accepted lifecycle risk: the remedy is a manual administrative
    block (`core.users.active = FALSE`) or the permanent administrative `active` to `historical`
    transition. No automatic provider-deletion machinery is added.

    That remedy is administrative and by hand, both to terminate access inside the remaining
    ID-token window and for hygiene afterwards; nothing relies on the upstream deletion itself."""
    # [impl->req~schema-external-identities-upstream-deletion-manual-remedy~1]
    # [impl->req~sessions-upstream-deletion-manual-remedy~1]
    if remedy not in set(UpstreamDeletionRemedy):
        raise IdentityError(f"{remedy} is not a defined upstream-deletion remedy")
    if FIREBASE_DELETION_SYNC_MECHANISMS:
        raise IdentityError("no automatic provider-deletion machinery is added")
    return UpstreamDeletionRemedy(remedy)


# --- The anonymous-to-registered upgrade ----------------------------------------------------------------


def upgrade_to_registered(row: ExternalIdentityRow, *, provider: IdentityProvider,
                          provider_uid: str, transaction: object) -> ExternalIdentityRow:
    """The upgrade updates the existing identity row's `provider` and `provider_uid` in place. It
    produces no new identity row and marks no row `historical`."""
    # The existing active row for the verified pair stays attached to the same user, flips its
    # stored `provider` in place and takes its `provider_uid` from the matching `providerData`
    # entry; no additional identity row is created and no source identity is marked `historical`.
    # [impl->req~schema-external-identities-upgrade-in-place~1]
    # [impl->req~users-upgrade-flips-provider-in-place~1]
    assert_provider_transition(row.provider, provider)
    if provider not in REGISTERED_PROVIDERS:
        raise IdentityError("the upgrade binds a registered provider")
    uid = assign_provider_uid(row.provider_uid, provider_uid,
                              operation=AuthOperation.upgrade_anonymous_to_registered)
    upgraded = write_provider_uid(row, uid, provider=provider,
                                  row_transaction=transaction, uid_transaction=transaction)
    if upgraded.id != row.id or upgraded.identity_state is not row.identity_state:
        raise IdentityError("the upgrade is in place and marks no row historical")
    return upgraded


# --- `native_claim_platform` -------------------------------------------------------------------------------


def pin_native_claim_platform(row: ExternalIdentityRow, platform: NativeClaimPlatform, *,
                              attestation_verified: bool) -> ExternalIdentityRow:
    """`native_claim_platform` pins an anonymous identity's native free-grant claim platform: set
    once, when the identity's first device attestation verifies on a `claim_anonymous_grant`
    attempt, immutable once set, and never re-declared per request — so the same anonymous
    identity cannot switch native branches by presenting different vendor material."""
    # [impl->req~schema-external-identities-native-claim-platform-pinned~1]
    if not attestation_verified:
        raise IdentityError("the pin is set only when a device attestation verifies")
    if row.native_claim_platform is None:
        return replace(row, native_claim_platform=platform)
    if row.native_claim_platform is not platform:
        raise IdentityError("native_claim_platform is immutable once set")
    return row


# --- `free_grant_consumed_at` --------------------------------------------------------------------------------

# The two claim endpoints the marker arbitrates between.
FREE_GRANT_CLAIM_ENDPOINTS: frozenset[AuthOperation] = frozenset({
    AuthOperation.claim_anonymous_grant,
    AuthOperation.claim_registered_grant,
})


def mark_free_grant_consumed(row: ExternalIdentityRow, *, now: datetime,
                             grant_transaction: object,
                             marker_transaction: object) -> ExternalIdentityRow:
    """`free_grant_consumed_at` is the permanent, non-PII per-account marker that the account has
    consumed its one lifetime free grant. It is set atomically in the transaction that commits the
    grant and is never cleared; a retry never creates a second lineage."""
    # [impl->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    if grant_transaction is not marker_transaction:
        raise IdentityError("the marker is set in the transaction that commits the grant")
    if row.free_grant_consumed_at is not None:
        # Never cleared and never re-stamped: a retry finds the same lineage already marked.
        return row
    return replace(row, free_grant_consumed_at=now)


def clear_free_grant_marker(row: ExternalIdentityRow) -> NoReturn:
    """The marker is never cleared, and it survives grant expiration, consumption, conversion,
    sign-out, identity retirement and PII erasure alike."""
    # [impl->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    raise IdentityError("free_grant_consumed_at is never cleared")


def free_grant_available(row: ExternalIdentityRow, endpoint: AuthOperation) -> bool:
    """After a success on either claim endpoint, the other endpoint refuses for that user. This
    marker is authoritative for the cross-endpoint refusal while ledger rows remain per-key abuse
    brakes; a tombstoned grant still counts as consumed, because identity rows are never
    deleted."""
    # [impl->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    if endpoint not in FREE_GRANT_CLAIM_ENDPOINTS:
        raise IdentityError(f"{endpoint} is not a free-grant claim endpoint")
    return row.free_grant_consumed_at is None


def assert_conversion_same_lineage(row: ExternalIdentityRow, *, converted_at: datetime) -> None:
    """Conversion through `claim_registered_grant` is a transition of the same lineage, never a
    second issuance."""
    # [impl->req~schema-external-identities-free-grant-consumed-at-permanent~1]
    if row.free_grant_consumed_at is None:
        raise IdentityError("conversion transitions an already-consumed lineage")
    if converted_at < row.free_grant_consumed_at:
        raise IdentityError("conversion never precedes the lineage it transitions")
