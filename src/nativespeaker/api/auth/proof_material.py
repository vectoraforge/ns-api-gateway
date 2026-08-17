"""Raw proof material: what PostgreSQL stores, what it never stores, and what is redacted.

The database keeps identity material in exactly three places — the plaintext `(issuer, subject)`
on `core.external_identities` with its stored `provider_uid`, the keyed verifier on
`core.auth_challenges`, and the keyed actor hash on `audit.auth_events`. Everything else a proof
carries is anti-abuse state held by a vendor, a fingerprint, or nothing at all.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nativespeaker.api.auth.audit import REDACTED, auth_event_row, redact
from nativespeaker.api.auth.derived_identifiers import DerivationFamily
from nativespeaker.api.auth.external_identities import (
    IDENTITY_ROW_DELETERS,
    KEYED_SUBJECT_ONLY_TABLES,
    RAW_PROVIDER_ACCOUNT_STORES,
    RAW_SUBJECT_STORES,
    SCRUB_EXEMPT_COLUMNS,
)
from nativespeaker.api.auth.invariants import DevicePlatform, ProofUse, assert_device_check_proof_use
from nativespeaker.api.auth.schema_invariants import FORBIDDEN_ANTI_ABUSE_COLUMNS


class ProofMaterialError(RuntimeError):
    """Material was about to be stored that this specification keeps out of PostgreSQL."""


# --- What PostgreSQL does not store -----------------------------------------------------------


class ProhibitedMaterial(StrEnum):
    """The six things PostgreSQL does not store."""
    raw_device_ids = "raw_device_ids"
    installation_ids = "installation_ids"
    general_device_records = "general_device_records"
    raw_devicecheck_or_integrity_tokens = "raw_devicecheck_or_integrity_tokens"
    raw_provider_account_ids_outside_registry = "raw_provider_account_ids_outside_registry"
    claim_finalization_table = "claim_finalization_table"


# Column names that would put a raw device identifier on a row.
RAW_DEVICE_ID_COLUMNS: frozenset[str] = frozenset({
    "device_id", "device_identifier", "device_uuid", "identifier_for_vendor", "idfv", "idfa",
    "android_id", "hardware_id", "device_principal", "device_principal_hash",
    "stable_device_principal_hash", "provider_device_principal_hash",
})

# Column names that would put an installation identifier on a row.
INSTALLATION_ID_COLUMNS: frozenset[str] = frozenset({
    "installation_id", "install_id", "firebase_installation_id", "app_instance_id",
    "instance_id",
})

# Table names that would amount to a general device record.
DEVICE_RECORD_TABLES: frozenset[str] = frozenset({
    "core.devices", "core.user_devices", "core.device_records", "core.device_registrations",
    "core.installations",
})

# Column names that would put a raw vendor anti-abuse token on a row.
RAW_VENDOR_TOKEN_COLUMNS: frozenset[str] = frozenset({
    "devicecheck_token", "device_check_token", "devicecheck_query_token",
    "devicecheck_update_token", "play_integrity_token", "play_integrity_verdict",
    "integrity_token", "device_recall_token", "device_recall_state", "turnstile_token",
    "bot_check_token",
})

# Column names that hold a raw provider account identifier. A surrogate `provider_account_id`
# foreign key into the registry is not one: it carries no provider-account value of its own.
RAW_PROVIDER_ACCOUNT_COLUMNS: frozenset[str] = frozenset({
    "provider_uid", "raw_provider_account_id", "canonical_provider_account_id",
    "google_account_id", "apple_user_id",
})

# Table names that would amount to a separate anonymous free-grant claim-finalization table.
CLAIM_FINALIZATION_TABLES: frozenset[str] = frozenset({
    "core.claim_finalizations", "core.anonymous_claim_finalizations",
    "core.grant_claim_finalizations", "core.claim_finalization",
})


def assert_no_raw_device_ids(table: str, columns: Iterable[str]) -> None:
    """PostgreSQL does not store raw device IDs."""
    # [impl->req~proof-no-raw-device-ids~1]
    offending = sorted({name for name in columns if name.lower() in RAW_DEVICE_ID_COLUMNS})
    if offending:
        raise ProofMaterialError(f"{table}.{offending} would store a raw device ID")


def assert_no_installation_ids(table: str, columns: Iterable[str]) -> None:
    """PostgreSQL does not store installation IDs."""
    # [impl->req~proof-no-installation-ids~1]
    offending = sorted({name for name in columns if name.lower() in INSTALLATION_ID_COLUMNS})
    if offending:
        raise ProofMaterialError(f"{table}.{offending} would store an installation ID")


def assert_no_general_device_records(tables: Iterable[str]) -> None:
    """PostgreSQL does not store general device records: there is no device table at all."""
    # [impl->req~proof-no-general-device-records~1]
    offending = sorted({name for name in tables if name.lower() in DEVICE_RECORD_TABLES})
    if offending:
        raise ProofMaterialError(f"{offending} would be a general device record")


def assert_no_raw_vendor_tokens(table: str, columns: Iterable[str]) -> None:
    """PostgreSQL does not store raw DeviceCheck tokens or Play Integrity tokens."""
    # [impl->req~proof-no-raw-devicecheck-or-integrity-tokens~1]
    offending = sorted({name for name in columns if name.lower() in RAW_VENDOR_TOKEN_COLUMNS})
    if offending:
        raise ProofMaterialError(f"{table}.{offending} would store a raw vendor token")


def assert_no_raw_provider_account_ids(table: str, columns: Iterable[str]) -> None:
    """PostgreSQL does not store raw provider account identifiers outside
    `core.external_identities` and the canonical `core.provider_accounts` registry."""
    # [impl->req~proof-no-raw-provider-account-ids-outside-registry~1]
    if table in RAW_PROVIDER_ACCOUNT_STORES:
        return
    offending = sorted({name for name in columns
                        if name.lower() in RAW_PROVIDER_ACCOUNT_COLUMNS})
    if offending:
        raise ProofMaterialError(
            f"{table}.{offending} holds a raw provider account identifier outside the registry")


def assert_no_claim_finalization_table(tables: Iterable[str]) -> None:
    """PostgreSQL does not store a separate anonymous free-grant claim-finalization table."""
    # [impl->req~proof-no-claim-finalization-table~1]
    offending = sorted({name for name in tables if name.lower() in CLAIM_FINALIZATION_TABLES})
    if offending:
        raise ProofMaterialError(f"{offending} is a claim-finalization table")


def assert_postgresql_does_not_store(table: str, columns: Iterable[str] = ()) -> None:
    """The whole prohibition, as one gate a proposed table must pass. PostgreSQL does not store
    raw device IDs, installation IDs, general device records, raw DeviceCheck or Play Integrity
    tokens, raw provider account identifiers outside the identity row and the canonical registry,
    or a separate anonymous free-grant claim-finalization table."""
    # [impl->req~proof-postgresql-does-not-store~1]
    names = list(columns)
    assert_no_general_device_records([table])
    assert_no_claim_finalization_table([table])
    assert_no_raw_device_ids(table, names)
    assert_no_installation_ids(table, names)
    assert_no_raw_vendor_tokens(table, names)
    assert_no_raw_provider_account_ids(table, names)


# --- The table-by-table inventory of external identity material -------------------------------


@dataclass(frozen=True, slots=True)
class TableInventory:
    """What one table holds of the external identity, and how long it holds it."""
    raw_subject: bool
    raw_provider_account_id: bool
    keyed_subject_hash: DerivationFamily | None
    plaintext_issuer: bool
    rows_deleted: bool
    purge_job: bool


# External identity material, table by table.
EXTERNAL_IDENTITY_INVENTORY: dict[str, TableInventory] = {
    "core.external_identities": TableInventory(
        raw_subject=True, raw_provider_account_id=True, keyed_subject_hash=None,
        plaintext_issuer=True, rows_deleted=False, purge_job=False),
    "core.auth_challenges": TableInventory(
        raw_subject=False, raw_provider_account_id=False,
        keyed_subject_hash=DerivationFamily.preauth_subject_hash,
        plaintext_issuer=True, rows_deleted=False, purge_job=False),
    "audit.auth_events": TableInventory(
        raw_subject=False, raw_provider_account_id=False,
        keyed_subject_hash=DerivationFamily.actor_subject_hash,
        plaintext_issuer=True, rows_deleted=False, purge_job=False),
}


def inventory_for(table: str) -> TableInventory:
    """External identity material is inventoried table by table: exactly these three tables hold
    any of it, and each one's entry says what it holds."""
    # [impl->req~proof-external-identity-material-inventory~1]
    entry = EXTERNAL_IDENTITY_INVENTORY.get(table)
    if entry is None:
        raise ProofMaterialError(f"{table} holds no external identity material")
    if entry.raw_subject != (table in RAW_SUBJECT_STORES):
        raise ProofMaterialError(f"{table} disagrees with the raw-subject store list")
    if (entry.keyed_subject_hash is not None) != (table in KEYED_SUBJECT_ONLY_TABLES):
        raise ProofMaterialError(f"{table} disagrees with the keyed-subject-only table list")
    return entry


# The closed set of uses the retained plaintext identity fields may be put to, and the uses they
# may never be put to.
IDENTITY_FIELD_USES: frozenset[str] = frozenset({
    "uniqueness_enforcement", "reject_re_registration", "operator_investigation_of_rejection",
})
IDENTITY_FIELD_FORBIDDEN_USES: frozenset[str] = frozenset({
    "profiling", "analytics", "marketing", "contact", "export",
})

# The paths those fields are reachable from.
IDENTITY_FIELD_REACHABLE_FROM: frozenset[str] = frozenset({
    "authentication_and_identity_path", "operator_functions",
})


def assert_identity_field_use(use: str, *, reached_from: str) -> str:
    """`core.external_identities` is the only table holding a raw, recoverable external identity
    subject — the plaintext `issuer` and `subject` — and, for a registered identity, the stored
    provider kind and `provider_uid`, the same stable identifier the canonical
    `core.provider_accounts` registry keeps; those two tables are the only places it lives. The
    rows are never deleted and privacy erasure deliberately retains those fields in plaintext,
    because they are the uniqueness reservations that keep a retired identity retired and reject
    re-registration of the same Google or Apple account. They may be used only for that
    uniqueness enforcement, for rejecting such a re-registration, and for operator investigation
    of a rejected re-registration — never for profiling, analytics, marketing, contact or export
    — and are reachable only from the authentication and identity path and the operator functions
    those uses require."""
    # [impl->req~proof-external-identities-retains-raw-subject~1]
    if RAW_SUBJECT_STORES != {"core.external_identities"}:
        raise ProofMaterialError("one table holds a raw, recoverable external identity subject")
    if RAW_PROVIDER_ACCOUNT_STORES != {"core.external_identities", "core.provider_accounts"}:
        raise ProofMaterialError("the identity row and the registry are the only two places")
    if IDENTITY_ROW_DELETERS:
        raise ProofMaterialError("these rows are never deleted")
    for column in ("issuer", "subject", "provider", "provider_uid"):
        if column not in SCRUB_EXEMPT_COLUMNS:
            raise ProofMaterialError(f"privacy erasure retains {column} in plaintext")
    if use in IDENTITY_FIELD_FORBIDDEN_USES or use not in IDENTITY_FIELD_USES:
        raise ProofMaterialError(f"the retained identity fields are never used for {use}")
    if reached_from not in IDENTITY_FIELD_REACHABLE_FROM:
        raise ProofMaterialError(f"the retained identity fields are not reachable from {reached_from}")
    return use


# `core.auth_challenges` columns that carry identity material, and the one that is cleared on
# consumption. There is no other identity material on the row.
CHALLENGE_IDENTITY_COLUMNS: tuple[str, ...] = ("preauth_issuer", "preauth_subject_hash")
CHALLENGE_CLEARED_ON_CONSUMPTION: tuple[str, ...] = ("preauth_subject_hash",)
CHALLENGE_PURGE_JOBS: frozenset[str] = frozenset()


def assert_challenge_identity_material(columns: Iterable[str]) -> None:
    """`core.auth_challenges` holds no raw subject: `preauth_issuer` is the deployment-known
    plaintext issuer string, and the subject appears only as the keyed `preauth_subject_hash`
    verifier, which consumption clears. Its rows carry no other identity material and are
    retained indefinitely, with no purge or scheduled cleanup."""
    # [impl->req~proof-auth-challenges-no-raw-subject~1]
    entry = inventory_for("core.auth_challenges")
    if entry.raw_subject or entry.purge_job or CHALLENGE_PURGE_JOBS:
        raise ProofMaterialError("core.auth_challenges keeps no raw subject and is never purged")
    extra = sorted({name for name in columns
                    if name.startswith("preauth_") and name not in CHALLENGE_IDENTITY_COLUMNS})
    if extra:
        raise ProofMaterialError(f"{extra} is other identity material on core.auth_challenges")
    assert_postgresql_does_not_store("core.auth_challenges", columns)


def consume_challenge_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    """Consumption clears the keyed verifier and leaves the plaintext issuer behind."""
    # [impl->req~proof-auth-challenges-no-raw-subject~1]
    consumed = dict(row)
    for column in CHALLENGE_CLEARED_ON_CONSUMPTION:
        consumed[column] = None
    return consumed


# `audit.auth_events` actor columns, and what a log line, metric label or audit row may copy.
AUTH_EVENT_ACTOR_COLUMNS: tuple[str, ...] = (
    "actor_issuer", "actor_subject_hash", "actor_subject_hash_key_version")
NEVER_COPIED_TO_LOGS: frozenset[str] = frozenset({"subject", "raw_subject", "sub", "provider_uid"})
AUTH_EVENT_PURGE_JOBS: frozenset[str] = frozenset()
AUTH_EVENT_ERASURE = "scrub_around_the_row"
# The retention rule and the tombstone disclosure it carries are owned elsewhere.
AUTH_EVENT_RETENTION_OWNER = "00-overview-and-shared-contracts.md"


def assert_auth_event_actor_only(fields: Iterable[str]) -> None:
    """`audit.auth_events` holds `actor_issuer` and the keyed `actor_subject_hash` only. Logs,
    metrics and audit rows keep that hashed representation and never copy the raw `subject` or
    `provider_uid` retained on an identity row. Its rows are retained indefinitely, with no purge
    or scheduled cleanup, and privacy erasure scrubs around them rather than deleting them."""
    # [impl->req~proof-auth-events-hashed-actor-only~1]
    entry = inventory_for("audit.auth_events")
    if entry.raw_subject or entry.raw_provider_account_id or entry.purge_job:
        raise ProofMaterialError("audit.auth_events keeps the hashed actor and nothing raw")
    if AUTH_EVENT_PURGE_JOBS or entry.rows_deleted or AUTH_EVENT_ERASURE != "scrub_around_the_row":
        raise ProofMaterialError("audit rows are retained indefinitely and scrubbed around")
    offending = sorted({name for name in fields if name.lower() in NEVER_COPIED_TO_LOGS})
    if offending:
        raise ProofMaterialError(f"{offending} is never copied into logs, metrics or audit rows")


# --- What decides free-credit eligibility -------------------------------------------------------

# The per-device device-check state, by platform. No per-device identifier in PostgreSQL decides
# anything, and no stable provider device principal is ever derived or hashed.
DEVICE_ELIGIBILITY_SIGNAL: dict[DevicePlatform, str] = {
    DevicePlatform.ios: "apple_devicecheck",
    DevicePlatform.android: "play_integrity_device_recall",
}
DERIVED_DEVICE_PRINCIPALS: frozenset[str] = frozenset()


def device_eligibility_signal(platform: DevicePlatform,
                              *, stored_device_identifier: str | None = None) -> str:
    """Device-level free-credit eligibility for `anonymous_device_grant` is decided from the
    per-device device-check state, not from any per-device identifier stored in PostgreSQL: Apple
    DeviceCheck on iOS and Google Play Integrity / Play Integrity Device Recall on Android where
    Device Recall is available. The backend never derives or hashes a stable provider device
    principal."""
    # [impl->req~proof-device-eligibility-from-vendor-state~1]
    if stored_device_identifier is not None or DERIVED_DEVICE_PRINCIPALS:
        raise ProofMaterialError("no stored per-device identifier decides device eligibility")
    signal = DEVICE_ELIGIBILITY_SIGNAL.get(platform)
    if signal is None:
        raise ProofMaterialError(f"{platform} has no per-device device-check state")
    return signal


class AccountEligibilityPath(StrEnum):
    """The two account-deduped free-credit paths."""
    registered_account_grant = "registered_account_grant"
    web_anonymous_gate = "web_anonymous_gate"


# Both paths are enforced on the stable provider UID through the canonical registry and its
# per-gate consumption rows; `idp_account_hash` is retained only as an alias.
ACCOUNT_ELIGIBILITY_ENFORCED_ON: str = "core.provider_accounts.provider_uid"
ACCOUNT_ELIGIBILITY_ALIAS: str = "idp_account_hash"


def account_eligibility_inputs(path: AccountEligibilityPath,
                               *, client_supplied: Sequence[str] = ()) -> tuple[str, ...]:
    """Account-level free-credit eligibility has two account-deduped paths, both enforced on the
    stable provider UID through the canonical registry. `registered_account_grant` is decided from
    the current linked identity's stored provider and stored `provider_uid`, confirmed by the
    operation's mandatory fail-closed Firebase Admin `providerData` read. The web
    anonymous-grant sign-in gate first requires the complete server-side Firebase lookup result
    to pass the closed classifier, then requires the resulting registered provider and sole
    entry's stable provider subject to equal the claiming identity's stored provider and stored
    `provider_uid`. Neither path trusts client-supplied provider account identifiers."""
    # [impl->req~proof-account-eligibility-two-paths~1]
    if client_supplied:
        raise ProofMaterialError(
            f"neither path trusts client-supplied {sorted(client_supplied)}")
    match path:
        case AccountEligibilityPath.registered_account_grant:
            return ("stored_provider", "stored_provider_uid",
                    "mandatory_fail_closed_provider_data_read")
        case AccountEligibilityPath.web_anonymous_gate:
            return ("closed_classifier_over_complete_provider_data", "stored_provider",
                    "stored_provider_uid")
        case _:
            raise ProofMaterialError(f"{path} is not an account-deduped eligibility path")


# What the device-check signal is not.
DEVICE_CHECK_RECOVERS: frozenset[str] = frozenset()


def assert_device_check_not_ownership(use: ProofUse,
                                      *, recovers: Sequence[str] = ()) -> None:
    """The device-check signal is not an account-ownership or ownership-recovery credential. It
    is not used to recover chats, identities, subscriptions, or any other account data, and the
    backend must not use it as an account-ownership signal."""
    # [impl->req~proof-device-check-not-ownership-credential~1]
    assert_device_check_proof_use(use)
    if set(recovers) | DEVICE_CHECK_RECOVERS:
        raise ProofMaterialError("the device-check signal recovers no account data")


# --- The anti-abuse row's prohibition ------------------------------------------------------------

# The row shape and per-source evidence contract belong to `06-schema-reference.md`; this file
# states no competing shape, only the prohibition.
ANTI_ABUSE_ROW_SHAPE_OWNER: str = "06-schema-reference.md"
COMPETING_ANTI_ABUSE_SHAPE: frozenset[str] = frozenset()

# What no anti-abuse row carries.
ANTI_ABUSE_PROHIBITED_COLUMNS: frozenset[str] = frozenset({
    "attestation_key_id", "attestation_key_hash", "attestation_key_identifier",
    "attestation_provider",
}) | FORBIDDEN_ANTI_ABUSE_COLUMNS


def assert_anti_abuse_row_prohibitions(columns: Iterable[str]) -> None:
    """No anti-abuse row carries an attestation-key-derived identifier, an attestation provider, a
    raw device-check token, a raw device identifier, or a synthetic stable provider device
    principal."""
    # [impl->req~proof-anti-abuse-row-prohibitions~1]
    if COMPETING_ANTI_ABUSE_SHAPE:
        raise ProofMaterialError(f"{ANTI_ABUSE_ROW_SHAPE_OWNER} owns the row shape")
    names = list(columns)
    offending = sorted({name for name in names
                        if name.lower() in ANTI_ABUSE_PROHIBITED_COLUMNS})
    if offending:
        raise ProofMaterialError(f"{offending} is not carried on an anti-abuse row")
    assert_no_raw_device_ids("core.access_grants_anti_abuse", names)
    assert_no_raw_vendor_tokens("core.access_grants_anti_abuse", names)


# --- Live store-state verification, and the general prohibition ----------------------------------

# Live store-state verification's redaction and audit rules belong to the restore file. This file
# restates none of them and adds none of its own.
LIVE_STORE_REDACTION_OWNER: str = "04-subscription-restore-and-entitlement-transfer.md"
LIVE_STORE_RULES_RESTATED_HERE: frozenset[str] = frozenset()


def live_store_verification_details(outcome: str, raw_provider_response: Any = None) -> Any:
    """The redaction and audit rules for live store-state verification — no raw provider response
    persisted, the outcome recorded only as non-secret context on the `audit.auth_events` row —
    belong to the restore file's definition and are not restated here. The general prohibition
    below binds that material as it binds every other proof payload."""
    # [impl->req~proof-live-store-redaction-owned-by-restore-file~1]
    if LIVE_STORE_RULES_RESTATED_HERE:
        raise ProofMaterialError(f"{LIVE_STORE_REDACTION_OWNER} owns these rules")
    if raw_provider_response is not None:
        raise ProofMaterialError("no raw provider response is persisted")
    return redact({"store_state_verification": outcome})


# Raw proof material, in every shape this specification names. None of it reaches a row.
RAW_PROOF_MATERIAL_FIELDS: frozenset[str] = frozenset({
    "id_token", "jwt", "authorization", "bearer", "restore_proof", "purchase_token",
    "signed_transaction", "signed_payload", "attestation", "attestation_blob",
    "attestation_private_key", "private_key", "play_integrity_verdict", "integrity_token",
    "devicecheck_payload", "devicecheck_token", "device_id", "device_identifier",
})

# What `audit.auth_events.details` may hold instead.
PERMITTED_DETAIL_CONTENT: frozenset[str] = frozenset({
    "canonical_proof_fingerprints", "structured_non_secret_context",
})
AUTH_EVENTS_IS_A_PROOF_ARCHIVE: bool = False


def assert_no_raw_proof_material(table: str, columns: Iterable[str]) -> None:
    """Audit rows and database tables must not store raw JWTs, raw `restore_proof`, raw purchase
    tokens, raw signed transaction payloads, raw attestation blobs, raw Play Integrity verdicts,
    raw DeviceCheck payloads, raw attestation private keys, raw device identifiers, or any other
    secret proof material."""
    # [impl->req~proof-no-raw-proof-material-stored~1]
    offending = sorted({name for name in columns if name.lower() in RAW_PROOF_MATERIAL_FIELDS})
    if offending:
        raise ProofMaterialError(f"{table}.{offending} would store raw proof material")
    assert_postgresql_does_not_store(table, columns)


def redacted_audit_row(event: Any, **kwargs: Any) -> dict[str, Any]:
    """Audit insertion redacts before write: `audit.auth_events` is not a proof archive, and its
    `details` may store only canonical proof fingerprints and structured non-secret context."""
    # [impl->req~proof-no-raw-proof-material-stored~1]
    if AUTH_EVENTS_IS_A_PROOF_ARCHIVE:
        raise ProofMaterialError("audit.auth_events is not a proof archive")
    row = auth_event_row(event, **kwargs)
    assert_no_raw_proof_material("audit.auth_events", row)
    _assert_details_redacted(row["details"])
    return row


def _assert_details_redacted(value: Any) -> None:
    # [impl->req~proof-no-raw-proof-material-stored~1]
    if isinstance(value, Mapping):
        for name, item in value.items():
            if str(name).lower() in RAW_PROOF_MATERIAL_FIELDS and item != REDACTED:
                raise ProofMaterialError(f"details.{name} reached the row unredacted")
            _assert_details_redacted(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _assert_details_redacted(item)
