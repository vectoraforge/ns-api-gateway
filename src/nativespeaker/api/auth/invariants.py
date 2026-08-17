"""The cross-cutting invariants of `00-overview-and-shared-contracts.md`.

These are the rules whose full statement spans more than one section, so no single section
captures the whole rule. Rules with a complete normative home elsewhere are referenced here by
the requirement that owns them and are enforced there — this module never restates them as a
second rule.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast
from uuid import UUID

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.taxonomy import (
    REMEDIATIONS,
    RESULT_TO_CLASS,
    ClientErrorClass,
    register_client_class,
    surface,
)


class InvariantError(RuntimeError):
    """A cross-cutting invariant was about to be broken."""


# --- Scope ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Invariant:
    """One numbered cross-cutting invariant. `owner` names the requirement whose file owns the
    rule outright; where it is set, this file only references that rule."""
    number: int
    summary: str
    owner: str | None = None


# The twelve invariants, and for the referencing ones the requirement that owns the rule.
# A rule with a complete normative home in one section is stated there, not duplicated here.
# [impl->req~shared-invariants-scope~1]
CROSS_CUTTING_INVARIANTS: tuple[Invariant, ...] = (
    Invariant(1, "the enumerated creators of a core.access_grants row"),
    # [impl->req~shared-invariant-02~2]
    Invariant(2, "enum typing of authorization-relevant categorical fields",
              owner="req~schema-invariant-03~1"),
    Invariant(3, "a historical identity is rejected at per-request resolution"),
    # [impl->req~shared-invariant-04~2]
    Invariant(4, "the entitlement-only grant row and its paired anti-abuse row",
              owner="req~schema-invariant-08~2"),
    Invariant(5, "per-device free-credit anti-abuse is a device-check state, never a credential"),
    Invariant(6, "the three distinct free-grant failure classes"),
    Invariant(7, "global per-provider-account uniqueness of registered free-credit claims"),
    # [impl->req~shared-invariant-08~2]
    Invariant(8, "owner agreement between active subscription-backed grants and subscriptions",
              owner="req~schema-invariant-11~1"),
    # [impl->req~shared-invariant-09~2]
    Invariant(9, "the same-transaction deferred-constraint obligation",
              owner="req~schema-invariant-14~1"),
    Invariant(10, "purchase attribution carries no identity-kind dimension"),
    Invariant(11, "one provider account binds to only one user"),
    Invariant(12, "the fixed grant-then-usage lock order"),
)

_BY_NUMBER: dict[int, Invariant] = {entry.number: entry for entry in CROSS_CUTTING_INVARIANTS}


def normative_home(number: int) -> str | None:
    """The requirement that owns invariant `number` outright, or `None` where this file states
    the whole rule itself."""
    # [impl->req~shared-invariants-scope~1]
    entry = _BY_NUMBER.get(number)
    if entry is None:
        raise InvariantError(f"there is no cross-cutting invariant {number}")
    return entry.owner


def assert_stated_here(number: int) -> None:
    """A referencing invariant must not grow a second implementation in the shared layer: its
    normative home enforces it, and this file only points at that home."""
    # [impl->req~shared-invariants-scope~1]
    owner = normative_home(number)
    if owner is not None:
        raise InvariantError(f"invariant {number} is owned by {owner}, not restated here")


# --- 1. The enumerated creators of an access grant --------------------------------------------


class GrantCreator(StrEnum):
    """Every operation this specification lets create a `core.access_grants` row."""
    claim_anonymous_grant = "claim_anonymous_grant"
    claim_registered_grant = "claim_registered_grant"
    manual_issuance = "manual_issuance"
    purchase_ingestion = "purchase_ingestion"
    renewal_term_insert = "renewal_term_insert"
    restore_adoption = "restore_adoption"


# The grant source each creator is allowed to produce. A grant with no creator among these does
# not exist, and no other path creates one.
# [impl->req~shared-invariant-01~2]
GRANT_CREATOR_SOURCES: dict[GrantCreator, AccessGrantSource] = {
    GrantCreator.claim_anonymous_grant: AccessGrantSource.anonymous_device_grant,
    GrantCreator.claim_registered_grant: AccessGrantSource.registered_account_grant,
    GrantCreator.manual_issuance: AccessGrantSource.manual,
    GrantCreator.purchase_ingestion: AccessGrantSource.subscription,
    GrantCreator.renewal_term_insert: AccessGrantSource.subscription,
    GrantCreator.restore_adoption: AccessGrantSource.subscription,
}


def assert_grant_creator(creator: GrantCreator | str, source: AccessGrantSource) -> None:
    """Fail closed on any path that is not one of the enumerated creators, and on a creator
    producing a source it does not own."""
    # [impl->req~shared-invariant-01~2]
    if creator not in set(GrantCreator):
        raise InvariantError(f"{creator} is not an enumerated access-grant creator")
    allowed = GRANT_CREATOR_SOURCES[GrantCreator(creator)]
    if source is not allowed:
        raise InvariantError(f"{creator} creates {allowed} grants, not {source}")


# --- 2. Enum typing of authorization-relevant categorical fields ------------------------------

# The categorical fields authorization depends on, and the schema-typed enum each is stored as:
# external-identity `provider`, grant `source`, grant `status`, and audit `actor_provider` when
# present are stored as schema-typed enums, never as free text.
# [impl->req~schema-invariant-03~1]
ENUM_TYPED_FIELDS: dict[str, type[StrEnum]] = {
    "core.external_identities.provider": IdentityProvider,
    "core.access_grants.source": AccessGrantSource,
    "core.access_grants.status": AccessGrantStatus,
    "audit.auth_events.operation": AuthOperation,
    "audit.auth_events.result": AuthEventResult,
    "audit.auth_events.actor_provider": IdentityProvider,
}


# --- 3. A historical identity is rejected at per-request resolution ---------------------------

# The resolution outcomes that reject the request where they are produced, before any handler
# runs. Once an external identity has transitioned to `historical`, every subsequent request for
# it resolves here and is rejected — there is no later window in which it is admitted.
# [impl->req~shared-invariant-03~1]
REJECTED_AT_RESOLUTION: dict[ResolutionOutcome, AuthEventResult] = {
    ResolutionOutcome.historical_identity: AuthEventResult.historical_identity,
    ResolutionOutcome.blocked_user: AuthEventResult.blocked_user,
}


def rejected_at_resolution(outcome: ResolutionOutcome) -> AuthEventResult | None:
    """The result a per-request resolution outcome rejects with, or `None` where it admits."""
    # [impl->req~shared-invariant-03~1]
    return REJECTED_AT_RESOLUTION.get(outcome)


# --- 4/5. The entitlement-only grant row -------------------------------------------------------

# The two free-credit sources whose grants pair with a `core.access_grants_anti_abuse` row. The
# pairing rule itself is `req~schema-invariant-08~2`.
ANTI_ABUSE_ELIGIBLE_SOURCES: frozenset[AccessGrantSource] = frozenset({
    AccessGrantSource.anonymous_device_grant,
    AccessGrantSource.registered_account_grant,
})


def requires_anti_abuse_row(source: AccessGrantSource) -> bool:
    """Whether a grant of this source pairs with an anti-abuse row."""
    return source in ANTI_ABUSE_ELIGIBLE_SOURCES


class DevicePlatform(StrEnum):
    ios = "ios"
    android = "android"
    web = "web"


# The per-device free-credit anti-abuse mechanism on each platform.
# [impl->req~shared-invariant-05~1]
DEVICE_CHECK_MECHANISM: dict[DevicePlatform, str] = {
    DevicePlatform.ios: "apple_devicecheck",
    DevicePlatform.android: "play_integrity_device_recall",
    DevicePlatform.web: "signin_plus_server_validated_bot_check",
}


class ProofUse(StrEnum):
    """What a caller proposes to do with a device-check proof token."""
    anti_abuse_gate = "anti_abuse_gate"
    identity = "identity"
    ownership = "ownership"
    recovery = "recovery"
    upgrade = "upgrade"
    account_resolution = "account_resolution"


# Column names that would put device-check state on the entitlement row.
FORBIDDEN_GRANT_COLUMNS: frozenset[str] = frozenset({
    "device_check_state", "devicecheck_token", "devicecheck_bits", "device_recall_token",
    "device_principal", "device_principal_hash", "device_id", "device_identifier",
    "play_integrity_token", "bot_check_token", "device_check_hash",
})


def assert_device_check_proof_use(use: ProofUse) -> None:
    """A device-check proof token gates free credit for a device and does nothing else: it is
    never an identity, ownership, recovery or upgrade credential, and it resolves no account.

    It is not an identity token: it is an untrusted request-body input used only to query the
    device-check vendor, must never be read as a source of verified identity, and does not relax
    the rule that verified `(issuer, subject)` comes from the backend-verified token claims alone
    and never from client-supplied input."""
    # [impl->req~shared-invariant-05~1]
    # [impl->req~sessions-device-check-token-not-identity~1]
    if use is not ProofUse.anti_abuse_gate:
        raise InvariantError(f"a device-check proof token is no {use} credential")


def assert_grant_columns_entitlement_only(columns: Iterable[str]) -> None:
    """`core.access_grants` carries entitlement state only: no device-check state is stored as an
    anti-abuse column on it."""
    # [impl->req~shared-invariant-05~1]
    # [impl->req~schema-invariant-08~2]
    offending = sorted(set(columns) & FORBIDDEN_GRANT_COLUMNS)
    if offending:
        raise InvariantError(f"{offending} are not entitlement state on core.access_grants")


# --- 6. The three distinct free-grant failure classes ------------------------------------------

# Durable exhaustion, a verification gate and a transient verification outage: three classes with
# three remediations, never conflated.
# [impl->req~shared-invariant-06~1]
DISTINCT_FAILURE_CLASSES: tuple[ClientErrorClass, ...] = (
    ClientErrorClass.device_grant_exhausted,
    ClientErrorClass.verification_required,
    ClientErrorClass.verification_temporarily_unavailable,
)


def _assert_failure_classes_distinct() -> None:
    # [impl->req~shared-invariant-06~1]
    actions = {REMEDIATIONS[klass].action for klass in DISTINCT_FAILURE_CLASSES}
    if len(actions) != len(DISTINCT_FAILURE_CLASSES):
        raise InvariantError("the three free-grant failure classes share a remediation")
    if not REMEDIATIONS[ClientErrorClass.verification_temporarily_unavailable].transient:
        raise InvariantError("a verification outage is the transient class")
    if REMEDIATIONS[ClientErrorClass.device_grant_exhausted].transient:
        raise InvariantError("durable exhaustion is not a transient class")


_assert_failure_classes_distinct()


# Which internal result surfaces as which of the three classes, and the rule that a transient
# failure is never surfaced as a durable class unless durable state was independently observed,
# both belong to the grant material in `03-free-credit-grants-and-anti-abuse.md`. This invariant
# owns only the distinctness above; there is no second decider here.


# --- 7. One free-credit claim per provider account ---------------------------------------------


class GateConsumptionKind(StrEnum):
    """`core.gate_consumption_kind`. The two kinds are distinct rows."""
    web_anonymous_gate = "web_anonymous_gate"
    registered_account_grant = "registered_account_grant"


@dataclass(frozen=True, slots=True)
class ProviderAccount:
    """One canonical `core.provider_accounts` row, keyed by the stable provider UID."""
    provider: IdentityProvider
    provider_uid: str


# The grants domain's own additions to the one shared internal-result-to-class mapping, made
# through the taxonomy's declared extension point. There is no second result-to-class registry:
# every class below is read back out of `taxonomy.surface`.
_GRANT_GATE_CLASSES: dict[AuthEventResult, ClientErrorClass] = {
    AuthEventResult.idp_account_already_claimed: ClientErrorClass.account_already_claimed,
    AuthEventResult.anti_abuse_already_claimed: ClientErrorClass.device_grant_exhausted,
    AuthEventResult.native_claim_already_claimed: ClientErrorClass.device_grant_exhausted,
}

for _result, _class in _GRANT_GATE_CLASSES.items():
    if _result not in RESULT_TO_CLASS:
        register_client_class(_result, _class.value, REMEDIATIONS[_class].http_status)


def _conflict(result: AuthEventResult) -> tuple[AuthEventResult, ClientErrorClass]:
    """The internal result together with the shared class it surfaces as, read from the one
    registry rather than restated here."""
    return result, ClientErrorClass(surface(result)[0])


# Each gate's conflict, with its internal result and its client-visible class. A duplicate
# registered gate is not the same thing as a per-device anonymous-grant block: the two are
# enforced by different mechanisms, audit differently, and surface as different classes.
# A registered-gate conflict surfaces as `idp_account_already_claimed` and the client-visible
# class `account_already_claimed`; a web-gate conflict surfaces as `device_grant_exhausted`.
# [impl->req~shared-invariant-07~1]
# [impl->req~schema-invariant-10~1]
GATE_CONFLICTS: dict[GateConsumptionKind, tuple[AuthEventResult, ClientErrorClass]] = {
    GateConsumptionKind.registered_account_grant: _conflict(
        AuthEventResult.idp_account_already_claimed),
    GateConsumptionKind.web_anonymous_gate: _conflict(
        AuthEventResult.anti_abuse_already_claimed),
}

# The durable per-device anonymous-grant block, enforced by the per-device device-check state
# rather than by a provider-account gate row.
# [impl->req~shared-invariant-07~1]
DEVICE_GRANT_BLOCK: tuple[AuthEventResult, ClientErrorClass] = _conflict(
    AuthEventResult.native_claim_already_claimed)


class GateAlreadyConsumedError(InvariantError):
    """The provider account has already consumed this free-grant gate."""

    def __init__(self, result: AuthEventResult, client_class: ClientErrorClass):
        self.result = result
        self.client_class = client_class
        super().__init__(f"{result} for this provider account")


class ProviderAccountGates:
    """The canonical registry's gate-consumption rows, unique on
    `(provider_account_id, consumption_kind)` over the stable provider UID."""

    def __init__(self) -> None:
        self._consumed: dict[tuple[IdentityProvider, str, GateConsumptionKind], UUID] = {}
        # `idp_account_hash` persists only as a non-authoritative lookup and audit alias: it is
        # recorded beside the consumption, never as part of the key that enforces it, so a hash
        # key rotation never reopens the gate.
        # [impl->req~shared-invariant-07~1]
        self._aliases: dict[tuple[IdentityProvider, str, GateConsumptionKind], tuple[bytes, int]] = {}

    def consume(self, account: ProviderAccount, kind: GateConsumptionKind, grant_id: UUID,
                *, idp_account_hash: bytes | None = None,
                hash_key_version: int | None = None) -> None:
        """Record that this provider account consumed this gate. The same Google or Apple
        provider account cannot back two successful registered free-credit claims, whatever
        Firebase account, external identity, internal user, reinstall or device asks. The two
        consumption kinds are distinct rows: the same account may hold one of each."""
        # [impl->req~shared-invariant-07~1]
        # [impl->req~schema-invariant-10~1]
        key = (account.provider, account.provider_uid, kind)
        if key in self._consumed:
            result, client_class = GATE_CONFLICTS[kind]
            raise GateAlreadyConsumedError(result, client_class)
        self._consumed[key] = grant_id
        if idp_account_hash is not None and hash_key_version is not None:
            self._aliases[key] = (idp_account_hash, hash_key_version)

    def consumed_grant(self, account: ProviderAccount, kind: GateConsumptionKind) -> UUID | None:
        return self._consumed.get((account.provider, account.provider_uid, kind))

    def alias(self, account: ProviderAccount,
              kind: GateConsumptionKind) -> tuple[bytes, int] | None:
        """The non-authoritative lookup and audit alias recorded for this consumption."""
        return self._aliases.get((account.provider, account.provider_uid, kind))


# --- 8/9. Rules with their normative home in the schema file -----------------------------------


def assert_owner_agreement(*, grant_user_id: UUID | None, subscription_user_id: UUID | None) -> None:
    """Active subscription-backed grants and canonical subscriptions share one current owner at
    commit. The rule is `req~schema-invariant-11~1`, enforced by the deferrable composite foreign
    key; this is the read-side check the locked paths make against the same condition. Neither
    row reaches that agreement by rewriting a grant's `user_id`."""
    # [impl->req~shared-invariant-08~2]
    # [impl->req~schema-invariant-11~1]
    if grant_user_id != subscription_user_id:
        raise InvariantError("a subscription-backed grant and its subscription share one owner")


# The paths that must bring their rows into one transaction so the deferred constraints hold at
# commit. The obligation itself is `req~schema-invariant-14~1` (final paragraph).
DEFERRED_CONSTRAINT_PATHS: frozenset[str] = frozenset({
    "subscription_lifecycle_ingestion",
    "restore_subscription",
    "claim_anonymous_grant",
    "claim_registered_grant",
})


def assert_same_transaction(path: str, transaction_ids: Sequence[object]) -> None:
    """Every row a deferred-constraint path writes commits in one transaction, so the deferred
    foreign keys hold at commit."""
    # [impl->req~shared-invariant-09~2]
    if path not in DEFERRED_CONSTRAINT_PATHS:
        raise InvariantError(f"{path} carries no deferred-constraint obligation")
    if len(set(map(id, transaction_ids))) > 1:
        raise InvariantError(f"{path} must write its rows in one transaction")


# --- 10. Purchase attribution ------------------------------------------------------------------


class StoreProvider(StrEnum):
    """`core.subscription_provider`. Attribution is keyed by the store and the token."""
    apple = "apple"
    google_play = "google_play"


class AttributionSource(StrEnum):
    """Where an attribution decision may come from."""
    store_echoed_token = "store_echoed_token"
    restore_insert_once = "restore_insert_once"
    request_authenticated_identity = "request_authenticated_identity"
    client_asserted_identity = "client_asserted_identity"


PERMITTED_ATTRIBUTION_SOURCES: frozenset[AttributionSource] = frozenset({
    AttributionSource.store_echoed_token,
    AttributionSource.restore_insert_once,
})


def assert_attribution_source(source: AttributionSource) -> None:
    """Attribution is never taken from the request-authenticated or client-asserted identity."""
    # [impl->req~shared-invariant-10~1]
    if source not in PERMITTED_ATTRIBUTION_SOURCES:
        raise InvariantError(f"{source} is not a purchase-attribution source")


class AttributionTokens:
    """`core.store_purchase_tokens`: one lifetime token per user per store, keyed by the store
    provider and that token. There is no identity-kind dimension anywhere in the key."""

    def __init__(self) -> None:
        self._by_user: dict[tuple[UUID, StoreProvider], str] = {}
        self._by_token: dict[tuple[StoreProvider, str], UUID] = {}

    def mint(self, user_id: UUID, provider: StoreProvider, identity_value: str) -> None:
        """Minted once at `create_user`, for the life of the user. The binding is keyed by the
        store provider and that token, so a token already bound to one user is never rebound to
        another: verified-purchase ingestion resolving through it must find one owner or none."""
        # [impl->req~shared-invariant-10~1]
        # [impl->req~schema-invariant-16~1]
        if (user_id, provider) in self._by_user:
            raise InvariantError("a user mints one lifetime attribution token per store")
        owner = self._by_token.get((provider, identity_value))
        if owner is not None and owner != user_id:
            raise InvariantError(
                f"{provider} attribution token is already bound to another user")
        self._by_user[(user_id, provider)] = identity_value
        self._by_token[(provider, identity_value)] = user_id

    def token_for(self, user_id: UUID, provider: StoreProvider) -> str | None:
        """The `GET /users/me` read: the user's own minted token, by store."""
        # [impl->req~shared-invariant-10~1]
        return self._by_user.get((user_id, provider))

    def owner_of(self, provider: StoreProvider, identity_value: str) -> UUID | None:
        """Verified-purchase ingestion: the owning user is resolved by matching the store-echoed
        token through this binding alone. An unresolved token attributes to nobody."""
        # [impl->req~shared-invariant-10~1]
        # [impl->req~schema-invariant-15~1]
        assert_attribution_source(AttributionSource.store_echoed_token)
        return self._by_token.get((provider, identity_value))


# --- 11. One provider account binds to only one user -------------------------------------------

# The Firebase Admin `providerData` provider ids, and the stored provider each one confirms.
_PROVIDER_DATA_IDS: dict[str, IdentityProvider] = {
    "google.com": IdentityProvider.google,
    "apple.com": IdentityProvider.apple,
}


def provider_data_field(entry: object, *names: str) -> str:
    """One field of a `providerData` entry, whatever shape the Admin SDK handed back: a mapping
    or an object, `snake_case` or `camelCase`. Classification and `provider_uid` derivation read
    entries through this one normalizer, so they can never disagree about which shapes are
    valid."""
    # [impl->req~schema-external-identities-provider-uid-source~1]
    if isinstance(entry, Mapping):
        values = cast(Mapping[str, object], entry)
        found = next((values[name] for name in names if values.get(name)), None)
    else:
        found = next((getattr(entry, name) for name in names if getattr(entry, name, None)), None)
    return str(found) if found is not None else ""


def provider_data_id(entry: object) -> str:
    """The entry's `providerId`."""
    # [impl->req~schema-external-identities-provider-uid-source~1]
    return provider_data_field(entry, "provider_id", "providerId")


def provider_uid_from_provider_data(provider: IdentityProvider,
                                    provider_data: Sequence[object]) -> str | None:
    """`core.external_identities.provider_uid` comes only from the Firebase Admin `providerData`
    entry matching the confirmed provider — never from client input, headers, token claims, email
    or display name. It is `NULL` for `anonymous` and non-empty for `google` and `apple`."""
    # [impl->req~shared-invariant-11~1]
    # [impl->req~schema-external-identities-provider-uid-source~1]
    # [impl->req~schema-external-identities-provider-uid-never-client-input~1]
    if provider is IdentityProvider.anonymous:
        return None
    matching = [entry for entry in provider_data
                if _PROVIDER_DATA_IDS.get(provider_data_id(entry)) is provider]
    if len(matching) != 1:
        raise InvariantError(f"no single providerData entry confirms {provider}")
    uid = provider_data_field(matching[0], "uid")
    if not uid:
        raise InvariantError(f"{provider} carries a non-empty provider_uid")
    return uid


def assert_provider_uid_immutable(stored: str | None, incoming: str | None) -> None:
    """`provider_uid` is immutable once assigned."""
    # [impl->req~shared-invariant-11~1]
    if stored is not None and incoming != stored:
        raise InvariantError("provider_uid is immutable once assigned")


def provider_uid_reserved(provider: IdentityProvider, provider_uid: str | None) -> bool:
    """Whether a row falls under the partial unique index on
    `(issuer, provider, provider_uid)`. It covers registered rows only: an anonymous row's
    `provider_uid` is `NULL`, so the index constrains it not at all."""
    # [impl->req~shared-invariant-11~1]
    return provider is not IdentityProvider.anonymous and provider_uid is not None


class ProviderAccountAlreadyLinkedError(InvariantError):
    """The provider account is already bound to a user. The internal result is
    `provider_account_already_linked`, under the client-visible `operation_not_allowed` class,
    and the rejected attempt mutates no user, identity, grant or profile."""

    result = AuthEventResult.provider_account_already_linked
    client_class = ClientErrorClass.operation_not_allowed


# The operations that enforce the reservation inside their provider-binding transactions.
PROVIDER_BINDING_OPERATIONS: frozenset[AuthOperation] = frozenset({
    AuthOperation.create_user,
    AuthOperation.upgrade_anonymous_to_registered,
})


class ProviderAccountReservations:
    """The partial unique index, as the binding paths see it. It spans `active` and `historical`
    rows alike, so retiring an identity never frees its provider account."""

    def __init__(self) -> None:
        self._reserved: dict[tuple[str, IdentityProvider, str], UUID] = {}
        self._historical: set[tuple[str, IdentityProvider, str]] = set()

    def bind(self, *, operation: AuthOperation, issuer: str, provider: IdentityProvider,
             provider_uid: str | None, user_id: UUID) -> None:
        """Reserve the provider account for this user inside the provider-binding transaction.
        The partial index makes each registered Google or Apple provider account usable by at
        most one internal user ever."""
        # [impl->req~shared-invariant-11~1]
        # [impl->req~schema-external-identities-provider-account-reservation-index~1]
        # [impl->req~schema-external-identities-provider-account-already-linked~1]
        if operation not in PROVIDER_BINDING_OPERATIONS:
            raise InvariantError(f"{operation} performs no provider binding")
        if not provider_uid_reserved(provider, provider_uid):
            return
        assert provider_uid is not None
        key = (issuer, provider, provider_uid)
        holder = self._reserved.get(key)
        if holder is not None and holder != user_id:
            raise ProviderAccountAlreadyLinkedError(
                "this provider account is already bound to a user")
        self._reserved[key] = user_id

    def retire(self, *, issuer: str, provider: IdentityProvider, provider_uid: str) -> None:
        """Retire the identity row to `historical`. The index spans `active` and `historical`
        rows alike, so the reservation stays exactly where it was: administrative retirement does
        not free that provider account for reuse."""
        # [impl->req~shared-invariant-11~1]
        # [impl->req~schema-external-identities-provider-account-reservation-index~1]
        if (issuer, provider, provider_uid) not in self._reserved:
            raise InvariantError("no reservation to retire")
        self._historical.add((issuer, provider, provider_uid))

    def is_historical(self, issuer: str, provider: IdentityProvider, provider_uid: str) -> bool:
        return (issuer, provider, provider_uid) in self._historical

    def holder(self, issuer: str, provider: IdentityProvider, provider_uid: str) -> UUID | None:
        return self._reserved.get((issuer, provider, provider_uid))
