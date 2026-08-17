"""`GET /users/me`: the profile read, and the store purchase-attribution tokens beside it.

Two reads over already-committed state — the user's `core.users` profile fields and the user's
`core.store_purchase_tokens` rows — and one fixed response shape. Nothing is created, rotated,
mutated or verified here, and no client-supplied signal changes what is returned: the response
carries an entry for every store provider on every platform, always.

The tokens are minted once, in the create-user transaction. That is why a missing token row is an
internal invariant failure here rather than a `null` field or a reason to mint a replacement.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, NoReturn
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import VerifiedIdentityContext
from nativespeaker.api.auth.create_user import ATTRIBUTION_TOKEN_FIELDS
from nativespeaker.api.auth.endpoints import barrier_admitted, bearer_credential
from nativespeaker.api.auth.invariants import StoreProvider
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.profile import PROFILE_FIELDS
from nativespeaker.api.auth.sync import REGISTRATION_STATE_FIELD

USERS_ME_METHOD = "GET"
USERS_ME_PATH = "/users/me"


class UsersMeError(RuntimeError):
    """A `GET /users/me` rule was about to be broken."""


class UsersMeProhibitedError(UsersMeError):
    """`GET /users/me` was about to do something its must-not list forbids."""

    def __init__(self, effect: UsersMeEffect | str):
        self.effect = effect
        super().__init__(f"GET /users/me must not {effect}")


class MissingAttributionTokenError(UsersMeError):
    """A user has no attribution token row for a store. Both tokens are minted in the create-user
    transaction, so this is an internal invariant failure — never a `null` in the response, and
    never a reason to lazily mint a replacement."""

    result = AuthEventResult.internal_error

    def __init__(self, user_id: UUID, provider: StoreProvider):
        self.user_id = user_id
        self.provider = provider
        super().__init__(f"user {user_id} has no {provider} attribution token row")


# --- Authentication and admission ---------------------------------------------------------------


def users_me_credential(authorization_values: Iterable[str]) -> str:
    """The endpoint's authentication: the external IDP ID token as a single `Authorization: Bearer`
    credential, and nothing else."""
    # [impl->req~sessions-api-users-me-bearer-credential~1]
    return bearer_credential(USERS_ME_METHOD, USERS_ME_PATH, list(authorization_values))


def assert_admitted(context: VerifiedIdentityContext) -> VerifiedIdentityContext:
    """The endpoint's admission precondition: authentication and identity resolution happen in the
    shared pre-handler barrier before this handler runs, and the endpoint requires a linked, active
    identity — pre-auth, historical and blocked identities are rejected at the barrier."""
    # [impl->req~sessions-api-users-me-barrier-precondition~1]
    return barrier_admitted(context, USERS_ME_METHOD, USERS_ME_PATH)


# --- The must-not list ---------------------------------------------------------------------------


class UsersMeEffect(StrEnum):
    """Everything `GET /users/me` must not do. The list is the whole of the endpoint's must-not
    contract, and membership is what makes an effect forbidden."""
    # [impl->req~sessions-users-me-must-not-create-users~1]
    create_user = "create users"
    # [impl->req~sessions-users-me-must-not-mutate-identities~1]
    mutate_identities = "mutate core.external_identities"
    # [impl->req~sessions-users-me-must-not-mutate-grants~1]
    mutate_grants = "mutate core.access_grants"
    # [impl->req~sessions-users-me-must-not-mutate-subscriptions~1]
    mutate_subscriptions = "mutate core.subscriptions or core.store_purchases"
    # [impl->req~sessions-users-me-must-not-issue-challenges~1]
    issue_challenge = "issue operation challenges"
    # Restore proofs and device-check proofs alike — Apple DeviceCheck, Google Play Integrity and
    # Play Integrity Device Recall included.
    # [impl->req~sessions-users-me-must-not-verify-proofs~1]
    verify_proof = "verify restore proofs or device-check proofs"
    # [impl->req~sessions-users-me-must-not-touch-device-grant-state~1]
    touch_device_grant_state = "read or modify per-device grant state"
    # [impl->req~sessions-users-me-must-not-append-state-changing-audit~1]
    append_state_changing_audit = "append audit.auth_events rows that imply state-changing auth"
    # The endpoint performs no state mutation and mints no token or grant: it never creates,
    # rotates or replaces a store purchase-attribution token, and the binding it reads is not
    # created here.
    # [impl->req~sessions-api-users-me-no-token-rotation~1]
    rotate_attribution_token = "create, rotate or replace a store purchase-attribution token"
    mint_grant = "mint a grant"
    update_profile = "update user profile fields"


# The whole must-not list, and there is no permitted subset: `GET /users/me` must not do any of it.
# [impl->req~sessions-api-users-me-prohibitions~1]
FORBIDDEN_EFFECTS: frozenset[UsersMeEffect] = frozenset(UsersMeEffect)

# The calls a caller could make against the read-only session, and the forbidden effect each one
# is. A call not named here is refused too — the session fails closed on an unknown call — so this
# map is a diagnostic, never an allowlist.
PROHIBITED_CALLS: dict[str, UsersMeEffect] = {
    "create_user": UsersMeEffect.create_user,
    "insert_user": UsersMeEffect.create_user,
    "link_identity": UsersMeEffect.mutate_identities,
    "mark_identity_historical": UsersMeEffect.mutate_identities,
    "write_identity": UsersMeEffect.mutate_identities,
    "create_grant": UsersMeEffect.mutate_grants,
    "expire_grant": UsersMeEffect.mutate_grants,
    "write_grant": UsersMeEffect.mutate_grants,
    "modify_subscription": UsersMeEffect.mutate_subscriptions,
    "write_store_purchase": UsersMeEffect.mutate_subscriptions,
    "issue_challenge": UsersMeEffect.issue_challenge,
    "verify_restore_proof": UsersMeEffect.verify_proof,
    "verify_device_proof": UsersMeEffect.verify_proof,
    "verify_devicecheck": UsersMeEffect.verify_proof,
    "verify_play_integrity": UsersMeEffect.verify_proof,
    "verify_device_recall": UsersMeEffect.verify_proof,
    "read_device_grant_state": UsersMeEffect.touch_device_grant_state,
    "write_device_grant_state": UsersMeEffect.touch_device_grant_state,
    "append_state_changing_audit": UsersMeEffect.append_state_changing_audit,
    "mint_attribution_token": UsersMeEffect.rotate_attribution_token,
    "rotate_attribution_token": UsersMeEffect.rotate_attribution_token,
    "replace_attribution_token": UsersMeEffect.rotate_attribution_token,
    "mint_grant": UsersMeEffect.mint_grant,
    "update_profile": UsersMeEffect.update_profile,
}


def assert_permitted(effect: UsersMeEffect | str) -> NoReturn:
    """The single decision point for the must-not list: nothing on it is ever permitted, whichever
    caller asks and whatever the account state is."""
    # [impl->req~sessions-api-users-me-prohibitions~1]
    raise UsersMeProhibitedError(effect)


def is_forbidden(effect: UsersMeEffect | str) -> bool:
    """Whether an effect is on the must-not list. An unrecognized effect counts as forbidden: the
    contract is a closed permission set of two reads, so an unknown effect is not a licence."""
    # [impl->req~sessions-api-users-me-prohibitions~1]
    try:
        return UsersMeEffect(effect) in FORBIDDEN_EFFECTS
    except ValueError:
        return True


# --- The read-only session -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProfileRow:
    """The resolved user's `core.users` profile fields, as `GET /users/me` reads them."""
    user_id: UUID
    email: str | None = None
    display_name: str | None = None
    created_at: datetime | None = None


class ReadOnlyUsersMeSession:
    """The only database handle the `GET /users/me` path is given: two reads over already-committed
    state, and no way to reach anything else.

    Every other call — a write, a proof verification, a challenge issuance, a per-device grant
    read, an attribution-token mint — is refused here rather than in each caller, so the must-not
    list cannot be evaded by adding a method to whatever the handler was handed.
    """

    # The two reads the endpoint is allowed, and the only ones.
    READS: tuple[str, ...] = ("profile_row", "store_tokens")

    def __init__(self,
                 *,
                 profile_row: ProfileRow,
                 store_tokens: Mapping[StoreProvider, str] | None = None,
                 stored_provider: IdentityProvider = IdentityProvider.anonymous):
        self._profile_row = profile_row
        self._store_tokens = dict(store_tokens or {})
        self._stored_provider = stored_provider
        self.reads: list[str] = []

    def read_profile_row(self) -> ProfileRow:
        """Step one: the resolved user's profile fields, from `core.users`."""
        # [impl->req~sessions-users-me-step-01~1]
        self.reads.append("profile_row")
        return self._profile_row

    def read_store_tokens(self) -> dict[StoreProvider, str]:
        """Step two: the user's persisted purchase-attribution tokens from
        `core.store_purchase_tokens`, scoped per store provider. Reading them creates nothing."""
        # [impl->req~sessions-users-me-step-02~1]
        self.reads.append("store_tokens")
        return dict(self._store_tokens)

    def read_stored_provider(self) -> IdentityProvider:
        """The stored registration state of the linked identity, read from the same stored column
        `POST /auth/sync` reports."""
        self.reads.append("stored_provider")
        return self._stored_provider

    def __getattr__(self, name: str) -> NoReturn:
        """Anything beyond the reads above. A named call reports the effect it would have been; an
        unnamed one is refused all the same."""
        # [impl->req~sessions-api-users-me-prohibitions~1]
        # [impl->req~sessions-api-users-me-no-token-rotation~1]
        if name.startswith("_"):
            raise AttributeError(name)
        assert_permitted(PROHIBITED_CALLS.get(name, name))


# --- The fixed response shape --------------------------------------------------------------------

# Every store provider appears, always. The shape is fixed and carries no platform condition, so
# the entry set is this enumeration and not a function of the caller.
# [impl->req~sessions-api-users-me-fixed-response-shape~1]
STORE_PROVIDERS: tuple[StoreProvider, ...] = tuple(StoreProvider)

# The attribution identifier each store's entry carries, by the name that store's API uses. Read
# from the create-user minting map, so the names cannot drift from what was minted.
ATTRIBUTION_FIELD_BY_STORE: dict[StoreProvider, str] = {
    StoreProvider(store): field for store, field in ATTRIBUTION_TOKEN_FIELDS.items()
}

# The only identifiers this payload may carry: explicitly defined non-secret attribution
# identifiers such as the Apple `app_account_token`. No store credentials, signed transactions or
# purchase proofs belong in it.
# [impl->req~sessions-api-users-me-fixed-response-shape~1]
PERMITTED_TOKEN_FIELDS: frozenset[str] = frozenset(ATTRIBUTION_FIELD_BY_STORE.values())
FORBIDDEN_PAYLOAD_FRAGMENTS: frozenset[str] = frozenset({
    "credential", "password", "secret", "signed_transaction", "signed_payload", "receipt",
    "purchase_proof", "proof", "jws", "private_key", "purchase_token", "id_token", "authorization",
})

# Client-supplied signals and gateway claims a caller might hope would change which tokens are
# loaded or whether they appear. None of them is read: the response carries no platform condition.
# [impl->req~sessions-api-users-me-fixed-response-shape~1]
IGNORED_REQUEST_SIGNALS: frozenset[str] = frozenset({
    "user-agent", "x-platform", "x-client-platform", "x-device-platform", "platform",
    "store", "provider", "x-forwarded-user", "x-jwt-claim-platform", "x-gateway-claims",
})

# The reads that decide the response. The token load is keyed by the resolved user alone.
TOKEN_LOAD_INPUTS: tuple[str, ...] = ("resolved_user_id",)


def assert_no_client_signal_consulted(signals: Iterable[str] = ()) -> None:
    """No client-supplied signal — a `User-Agent` value, an `X-Platform`-style header, a query
    parameter, a request-body flag — and no gateway claim may change which tokens are loaded or
    whether they appear. The token load reads the resolved user id and nothing else."""
    # [impl->req~sessions-api-users-me-fixed-response-shape~1]
    consulted = sorted({name.lower() for name in signals})
    if consulted:
        raise UsersMeError(f"the response shape is fixed; {consulted} is not read")
    if tuple(TOKEN_LOAD_INPUTS) != ("resolved_user_id",):
        raise UsersMeError("the token load is keyed by the resolved user alone")


def attribution_tokens(session: ReadOnlyUsersMeSession,
                       user_id: UUID,
                       *,
                       request_signals: Iterable[str] = ()) -> dict[str, str]:
    """The purchase-attribution token entries, one per store provider, unconditionally.

    Both tokens are minted in the create-user transaction, so no `null` case exists: a missing row
    is an internal invariant failure, never a `null` response value and never a reason to mint a
    replacement here.
    """
    # [impl->req~sessions-users-me-step-02~1]
    # [impl->req~sessions-api-users-me-fixed-response-shape~1]
    assert_no_client_signal_consulted(request_signals)
    stored = session.read_store_tokens()
    entries: dict[str, str] = {}
    for provider in STORE_PROVIDERS:
        value = stored.get(provider)
        if not value:
            # Never a lazily minted replacement, and never a `null`.
            # [impl->req~sessions-api-users-me-no-token-rotation~1]
            raise MissingAttributionTokenError(user_id, provider)
        entries[str(provider)] = value
    if set(entries) != {str(provider) for provider in STORE_PROVIDERS}:
        raise UsersMeError("the response always includes an entry for every store provider")
    return entries


def assert_payload_carries_no_store_secrets(payload: Mapping[str, Any]) -> None:
    """Only explicitly defined non-secret attribution identifiers belong in this payload: no store
    credentials, signed transactions or purchase proofs."""
    # [impl->req~sessions-api-users-me-fixed-response-shape~1]
    for provider, entry in payload.items():
        if not isinstance(entry, Mapping):
            raise UsersMeError(f"{provider}'s entry carries its attribution identifier")
        offending = sorted(name for name in entry
                           if name not in PERMITTED_TOKEN_FIELDS
                           or any(fragment in str(name).lower()
                                  for fragment in FORBIDDEN_PAYLOAD_FRAGMENTS))
        if offending:
            raise UsersMeError(f"{provider}'s entry carries {offending}")


@dataclass(frozen=True, slots=True)
class UsersMeState:
    """What one `GET /users/me` call reports: the profile fields, the stored registration state,
    and the persisted attribution tokens."""
    profile: ProfileRow
    identity_provider: IdentityProvider
    store_tokens: dict[str, str]


# The profile fields the response carries, taken from the canonical `core.users` profile fields.
RESPONSE_PROFILE_FIELDS: tuple[str, ...] = PROFILE_FIELDS


def users_me_response(state: UsersMeState) -> dict[str, Any]:
    """Step three, and the wire shape: the profile fields, the account's stored registration state
    under the same `identity_provider` name `POST /auth/sync` reports it under, and the read
    purchase tokens scoped per store provider.

    The shape is fixed: an entry for every store provider, each carrying that store's persisted
    attribution token by the field name that store's API uses, with no `null` anywhere and no
    platform condition. A client ignores the entries for stores it does not use — which is why
    every entry is present even where the caller cannot use it.
    """
    # [impl->req~sessions-users-me-step-03~1]
    # [impl->req~sessions-api-users-me-fixed-response-shape~1]
    profile = {field: getattr(state.profile, field) for field in RESPONSE_PROFILE_FIELDS}
    tokens = {
        str(provider): {ATTRIBUTION_FIELD_BY_STORE[provider]: state.store_tokens[str(provider)]}
        for provider in STORE_PROVIDERS
    }
    if any(next(iter(entry.values())) is None for entry in tokens.values()):
        raise UsersMeError("no null attribution token case exists")
    assert_payload_carries_no_store_secrets(tokens)
    return {
        "profile": profile,
        # The stored registration state, reported under the same name and from the same stored
        # column `POST /auth/sync` reads.
        # [impl->req~sessions-users-me-step-03~1]
        REGISTRATION_STATE_FIELD: state.identity_provider.value,
        "store_purchase_tokens": tokens,
    }


# What the iOS client does with the Apple entry: it reads `app_account_token` from the response and
# passes that exact stored value into the StoreKit purchase API at purchase time. It neither
# generates one nor transforms the value it read.
# [impl->req~sessions-api-users-me-purpose~1]
IOS_PURCHASE_TOKEN_FIELD: str = ATTRIBUTION_FIELD_BY_STORE[StoreProvider.apple]


def storekit_app_account_token(response: Mapping[str, Any]) -> str:
    """The exact stored Apple `app_account_token` the iOS client passes into the StoreKit purchase
    API. Read straight out of the response, never regenerated or reformatted."""
    # [impl->req~sessions-api-users-me-purpose~1]
    entry = response["store_purchase_tokens"][str(StoreProvider.apple)]
    return entry[IOS_PURCHASE_TOKEN_FIELD]


def users_me_state(context: VerifiedIdentityContext,
                   session: ReadOnlyUsersMeSession,
                   *,
                   request_signals: Iterable[str] = ()) -> UsersMeState:
    """The whole of what `GET /users/me` does: two reads and a fixed report.

    It returns the current user's backend profile and the user's already-persisted store
    purchase-attribution tokens, scoped per store provider. The tokens are returned unconditionally,
    for every store provider and on every platform. The endpoint performs no state mutation and
    mints no token or grant.
    """
    # [impl->req~sessions-api-users-me-purpose~1]
    # [impl->req~sessions-api-users-me-no-token-rotation~1]
    admitted = assert_admitted(context)
    assert admitted.user_id is not None  # noqa: S101 - narrowed by `assert_admitted`
    profile = session.read_profile_row()
    if profile.user_id != admitted.user_id:
        raise UsersMeError("the profile read is the barrier-resolved user's own row")
    tokens = attribution_tokens(session, admitted.user_id, request_signals=request_signals)
    return UsersMeState(profile=profile,
                        identity_provider=session.read_stored_provider(),
                        store_tokens=tokens)
