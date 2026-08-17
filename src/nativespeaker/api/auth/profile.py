"""`core.users` semantics: the internal owner row, its profile fields, and its lifecycle.

`core.users` is the internal owner of app data. This module is the one place the rules that
govern that row are decided — who classifies an account, what a stored `email` may be used for,
who may write the canonical profile fields, and what may never happen to the row. The column
facts themselves (nullability, defaults, the foreign keys that carry ownership) live in the
declarative schema and are applied by the migration that ships it.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, NoReturn
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.operations import IdentityProvider


class ProfileError(RuntimeError):
    """A `core.users` rule was about to be broken."""


class OrphanUserError(RuntimeError):
    """A read path reached a `core.users` row with no `core.external_identities` row."""

    def __init__(self, user_id: UUID | None = None):
        self.user_id = user_id
        self.result = AuthEventResult.internal_error
        super().__init__("user row has no external identity row")


# --- Account class ----------------------------------------------------------------------------

class AccountClass(StrEnum):
    """Anonymous and registered users share one table and one ownership model; the class is a
    reading of the stored external identity, not a separate table or a column on the user."""
    anonymous = "anonymous"
    registered = "registered"


REGISTERED_PROVIDERS: frozenset[IdentityProvider] = frozenset(
    {IdentityProvider.google, IdentityProvider.apple})


def account_class(provider: IdentityProvider) -> AccountClass:
    """The classifier, and the only one: the stored external-identity `provider`. `registered_at`
    never competes with it — a row whose timestamp disagrees is corruption, not a third class."""
    # [impl->req~schema-users-registered-at-not-classifier~1]
    # [impl->req~schema-users-shared-table-anon-registered~1]
    return AccountClass.registered if provider in REGISTERED_PROVIDERS else AccountClass.anonymous


def is_registered(registered_at: datetime | None) -> bool:
    """The reporting and profile reading of `registered_at`."""
    # `registered_at IS NULL` means registration was not completed.
    # [impl->req~schema-users-registered-at-null-unregistered~1]
    # `registered_at IS NOT NULL` means the user is registered.
    # [impl->req~schema-users-registered-at-set-registered~1]
    return registered_at is not None


def assert_registered_at_pairing(provider: IdentityProvider,
                                 registered_at: datetime | None) -> None:
    """`registered_at` is set exactly when the stored provider is registered. Disagreement is a
    corrupt row and fails closed; it never re-classifies the account.

    The two fields are paired: `registered_at IS NOT NULL` if and only if the stored provider is
    `google` or `apple`, equivalently `provider = 'anonymous'` if and only if
    `registered_at IS NULL`. Authorization, grant class and audit never invent a third state, and
    because each user has exactly one external identity the pairing is enforced here — in the code
    of the single completion transaction that writes both fields — rather than by a cross-table
    constraint trigger."""
    # [impl->req~schema-users-registered-at-not-classifier~1]
    # [impl->req~sessions-provider-registered-at-pairing~1]
    if is_registered(registered_at) != (account_class(provider) is AccountClass.registered):
        raise ProfileError(
            f"registered_at disagrees with the stored provider {provider}; the provider classifies")


# --- What a stored email address is, and is not -----------------------------------------------

class EmailUse(StrEnum):
    """The uses a caller can ask of the address stored in `core.users.email`."""
    display = "display"
    identity_match = "identity_match"
    ownership_proof = "ownership_proof"
    authorization = "authorization"
    account_recovery = "account_recovery"
    address_change = "address_change"


# A canonical backend profile field is data to show back to its owner. It is not a credential,
# so displaying it is the only use it carries on its own.
PERMITTED_EMAIL_USES: frozenset[EmailUse] = frozenset({EmailUse.display})

# The security-sensitive operations on an address. Each must independently verify current
# control of that address before it runs.
CONTROL_VERIFYING_USES: frozenset[EmailUse] = frozenset(
    {EmailUse.account_recovery, EmailUse.address_change})

# Identity is matched on the backend-verified token claims, and on nothing else.
IDENTITY_MATCH_KEY: tuple[str, str] = ("issuer", "subject")

# The canonical backend profile fields.
PROFILE_FIELDS: tuple[str, str] = ("email", "display_name")


def assert_identity_match_fields(fields: Iterable[str]) -> None:
    """Identity lookup is by exact `(issuer, subject)`. A stored profile email never selects,
    matches, or merges an account."""
    # [impl->req~schema-users-email-not-identity-match~1]
    extra = sorted(set(fields) - set(IDENTITY_MATCH_KEY))
    if extra:
        raise ProfileError(
            f"identity is matched by {IDENTITY_MATCH_KEY} alone, not by {extra}")


def assert_email_use(use: EmailUse) -> None:
    """A stored address is never by itself proof of identity, ownership, authorization, or
    account recovery."""
    # [impl->req~schema-users-email-not-proof~1]
    if use not in PERMITTED_EMAIL_USES:
        raise ProfileError(f"core.users.email is not proof for {use}")


def assert_email_control_verified(use: EmailUse, *, control_verified: bool) -> None:
    """Every security-sensitive email operation independently verifies current control of the
    address first; the presence of the address in `core.users.email` proves nothing about it."""
    # [impl->req~schema-users-email-control-verification~1]
    if use in CONTROL_VERIFYING_USES and not control_verified:
        raise ProfileError(f"{use} requires independently verified current control of the address")


# --- Copying an address in from the Firebase Admin user record --------------------------------

@dataclass(frozen=True, slots=True)
class AdminUserRecord:
    """The fields of one successful `getUser(subject)` response that auth completion may read.
    A lookup that did not succeed has no record at all."""
    email: str | None
    email_verified: bool


def initial_email_on_create(record: AdminUserRecord | None) -> str | None:
    """First creation of a registered user: the initial `email`, or `None` to leave it `NULL`.
    `display_name` is never copied by auth completion, so it has no counterpart here."""
    # [impl->req~schema-users-email-copy-on-create~1]
    # [impl->req~schema-users-email-display-name-canonical~1]
    if record is None or not record.email or not record.email_verified:
        return None
    return record.email


def email_on_upgrade(stored_email: str | None, record: AdminUserRecord | None) -> str | None:
    """The first completion of `upgrade_anonymous_to_registered` for an existing anonymous user:
    the resulting `email`. A stored address is never overwritten, and `display_name` is never
    copied by auth completion."""
    # [impl->req~schema-users-email-copy-on-upgrade~1]
    if stored_email is not None:
        return stored_email
    return initial_email_on_create(record)


# --- Who may write the canonical profile fields ------------------------------------------------

class ProfileWriter(StrEnum):
    """Who is asking to write `core.users`."""
    user_profile_update = "user_profile_update"
    auth_completion = "auth_completion"
    auth_sync = "auth_sync"
    client_presentation = "client_presentation"
    operator_action = "operator_action"


def sync_mutations(requested: Mapping[str, Any]) -> dict[str, Any]:
    """A later auth sync automatically overwrites nothing it finds — not the canonical profile
    fields, not the user's access grants. A copied address may therefore go stale: there is no
    continuing Firebase email synchronization and no provenance to reconcile it against."""
    # [impl->req~schema-users-sync-no-overwrite~1]
    # [impl->req~schema-users-email-may-be-stale~1]
    return {}


def profile_changes(writer: ProfileWriter,
                    requested: Mapping[str, Any],
                    *,
                    control_verified: bool = False) -> dict[str, Any]:
    """The single decision point for writes to `email` and `display_name`. Only user-facing
    profile update logic changes them; every other writer leaves them exactly as they are.

    A change to `email` is an address change, which is security-sensitive: the caller must have
    independently verified current control of the new address, and the address already stored on
    the row proves nothing about that.
    """
    # [impl->req~schema-users-profile-fields-explicit-update-only~1]
    if writer is not ProfileWriter.user_profile_update:
        # A name the client showed from the current verified IDP account is presentation only:
        # it does not become backend data on any path but an explicit profile update.
        # [impl->req~schema-users-external-display-not-backend-data~1]
        return sync_mutations(requested) if writer is ProfileWriter.auth_sync else {}
    unknown = sorted(set(requested) - set(PROFILE_FIELDS))
    if unknown:
        raise ProfileError(f"{unknown} are not canonical backend profile fields")
    if "email" in requested:
        # [impl->req~schema-users-email-control-verification~1]
        assert_email_control_verified(EmailUse.address_change,
                                      control_verified=control_verified)
    # [impl->req~schema-users-email-display-name-canonical~1]
    return dict(requested)


def user_mutation(changes: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    """Every mutation of a `core.users` row carries its own `updated_at` stamp, written by the
    same statement that carries the change."""
    # [impl->req~schema-users-updated-at-on-mutation~1]
    if not changes:
        raise ProfileError("a mutation with no changes is not a mutation")
    return {**changes, "updated_at": now}


# --- Blocking, retention and the identity row --------------------------------------------------

def is_blocked(active: bool) -> bool:
    """`active = FALSE` means the user is blocked."""
    # [impl->req~schema-users-active-false-blocked~1]
    return not active


def assert_no_implicit_reactivation(writer: ProfileWriter,
                                    *,
                                    stored_active: bool,
                                    requested_active: bool) -> None:
    """A blocked user is never reactivated implicitly by auth sync or auth completion; only a
    deliberate operator action lifts the block."""
    # [impl->req~schema-users-active-false-blocked~1]
    if is_blocked(stored_active) and requested_active and writer is not ProfileWriter.operator_action:
        raise ProfileError(f"{writer} may not reactivate a blocked user")


# No user row has a scheduled deletion: not a blocked or retired one, and not an anonymous one.
USER_RETENTION_DAYS: dict[AccountClass, int | None] = {
    AccountClass.anonymous: None,
    AccountClass.registered: None,
}


def retention_deadline(account: AccountClass, *, created_at: datetime) -> datetime | None:
    """The deletion deadline for a user row, or `None` where the row is retained indefinitely."""
    # [impl->req~schema-users-anonymous-retained-indefinitely~1]
    days = USER_RETENTION_DAYS[account]
    return None if days is None else created_at + timedelta(days=days)


def assert_hard_delete_allowed(*, has_external_identity: bool) -> None:
    """A `core.users` row that has a `core.external_identities` row is never hard-deleted:
    blocked and retired users retain a minimal user row."""
    # [impl->req~schema-users-never-hard-deleted~1]
    if has_external_identity:
        raise ProfileError("a user row with an external identity row is never hard-deleted")


# No scheduled sweep, repair or deletion looks for a user row without an identity row.
ORPHAN_USER_SWEEPS: frozenset[str] = frozenset()


def assert_user_created_with_identity(*,
                                      identity_row_written: bool,
                                      user_transaction: object = None,
                                      identity_transaction: object = None) -> None:
    """Enforcement is creation-time only: a `core.users` row is written in the same transaction
    as its `core.external_identities` row. Two rows written in two transactions do not satisfy
    the rule, so the two transactions must be the same object — the same test
    `external_identities.create_account` applies."""
    # [impl->req~schema-users-created-with-identity-row~1]
    if not identity_row_written:
        raise ProfileError("a core.users row is created with its external identity row")
    if user_transaction is not identity_transaction:
        raise ProfileError(
            "a core.users row is created in the same transaction as its identity row")


def read_orphan_user(user_id: UUID | None = None) -> NoReturn:
    """A user row that somehow exists without an identity row is left in place; the read path
    that reached it fails closed as an internal error rather than inventing an identity row or
    reassigning the account."""
    # [impl->req~schema-users-created-with-identity-row~1]
    raise OrphanUserError(user_id)


def display_name_for_client(backend_display_name: str | None,
                            idp_display_name: str | None) -> str | None:
    """What the client shows. Where the backend `display_name` is `NULL`, a name from the
    current verified IDP account may stand in, for presentation only."""
    # [impl->req~schema-users-client-display-name-fallback~1]
    if backend_display_name is not None:
        return backend_display_name
    return idp_display_name
