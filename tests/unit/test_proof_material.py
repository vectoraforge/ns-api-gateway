"""Raw proof material: what PostgreSQL stores, what it never stores, and what is redacted.

The prohibitions are checked twice over: as guards a proposed write must pass, and against the
shipped declarative schema, so a column that would break one of them cannot be added quietly.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nativespeaker.api.auth.audit import (
    REDACTED,
    AttemptPhase,
    AuthEventResult,
    resolved_actor,
    terminal_event,
)
from nativespeaker.api.auth.derived_identifiers import DerivationFamily
from nativespeaker.api.auth.invariants import DevicePlatform, InvariantError, ProofUse
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_material import (
    ANTI_ABUSE_ROW_SHAPE_OWNER,
    AUTH_EVENT_RETENTION_OWNER,
    EXTERNAL_IDENTITY_INVENTORY,
    LIVE_STORE_REDACTION_OWNER,
    LIVE_STORE_RULES_RESTATED_HERE,
    AccountEligibilityPath,
    ProofMaterialError,
    account_eligibility_inputs,
    assert_anti_abuse_row_prohibitions,
    assert_auth_event_actor_only,
    assert_challenge_identity_material,
    assert_device_check_not_ownership,
    assert_identity_field_use,
    assert_no_claim_finalization_table,
    assert_no_general_device_records,
    assert_no_installation_ids,
    assert_no_raw_device_ids,
    assert_no_raw_proof_material,
    assert_no_raw_provider_account_ids,
    assert_no_raw_vendor_tokens,
    assert_postgresql_does_not_store,
    consume_challenge_identity,
    device_eligibility_signal,
    inventory_for,
    live_store_verification_details,
    redacted_audit_row,
)

REFERENCE = Path(__file__).resolve().parent / "data" / "schema_reference_ddl.sql"
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def shipped_tables() -> dict[str, tuple[str, ...]]:
    """Every table the declarative schema creates, with its column names."""
    sql = REFERENCE.read_text()
    found: dict[str, tuple[str, ...]] = {}
    for match in re.finditer(r"CREATE TABLE (\S+) \(([^;]*?)\n\);", sql, re.DOTALL):
        columns = []
        for line in match.group(2).splitlines():
            stripped = line.strip()
            if not stripped or stripped.upper().startswith(
                    ("CHECK", "UNIQUE", "PRIMARY", "FOREIGN", "CONSTRAINT", ")", "OR", "AND")):
                continue
            name = stripped.split()[0]
            if name.isidentifier():
                columns.append(name)
        found[match.group(1)] = tuple(columns)
    return found


SHIPPED = shipped_tables()


def actor():
    return resolved_actor("https://securetoken.google.com/test-project", bytes(range(32)), 1,
                          stored_provider=IdentityProvider.google)


# --- What PostgreSQL does not store -------------------------------------------------------------


class TestPostgresqlDoesNotStore:

    # The whole prohibition, as one gate: the shipped schema passes it, table by table.
    # [utest->req~proof-postgresql-does-not-store~1]
    def test_the_shipped_schema_stores_none_of_it(self):
        assert SHIPPED, "the declarative schema parsed to no tables"
        for table, columns in SHIPPED.items():
            assert_postgresql_does_not_store(table, columns)

    # [utest->req~proof-postgresql-does-not-store~1]
    def test_a_proposed_table_carrying_any_of_it_is_refused(self):
        for column in ("device_id", "installation_id", "devicecheck_token",
                       "canonical_provider_account_id"):
            with pytest.raises(ProofMaterialError):
                assert_postgresql_does_not_store("core.something", [column])
        for table in ("core.devices", "core.claim_finalizations"):
            with pytest.raises(ProofMaterialError):
                assert_postgresql_does_not_store(table, ["id"])

    # [utest->req~proof-no-raw-device-ids~1]
    def test_no_raw_device_ids(self):
        for table, columns in SHIPPED.items():
            assert_no_raw_device_ids(table, columns)
        for column in ("device_id", "device_identifier", "identifier_for_vendor",
                       "stable_device_principal_hash"):
            with pytest.raises(ProofMaterialError):
                assert_no_raw_device_ids("core.access_grants_anti_abuse", [column])

    # [utest->req~proof-no-installation-ids~1]
    def test_no_installation_ids(self):
        for table, columns in SHIPPED.items():
            assert_no_installation_ids(table, columns)
        for column in ("installation_id", "firebase_installation_id", "app_instance_id"):
            with pytest.raises(ProofMaterialError):
                assert_no_installation_ids("core.users", [column])

    # [utest->req~proof-no-general-device-records~1]
    def test_no_general_device_records(self):
        assert_no_general_device_records(SHIPPED)
        for table in ("core.devices", "core.user_devices", "core.installations"):
            with pytest.raises(ProofMaterialError):
                assert_no_general_device_records([table])

    # [utest->req~proof-no-raw-devicecheck-or-integrity-tokens~1]
    def test_no_raw_devicecheck_or_play_integrity_tokens(self):
        for table, columns in SHIPPED.items():
            assert_no_raw_vendor_tokens(table, columns)
        for column in ("devicecheck_token", "devicecheck_query_token", "play_integrity_token",
                       "play_integrity_verdict", "device_recall_token"):
            with pytest.raises(ProofMaterialError):
                assert_no_raw_vendor_tokens("core.access_grants_anti_abuse", [column])

    # A raw provider account identifier lives on the identity row and in the canonical registry,
    # and nowhere else.
    # [utest->req~proof-no-raw-provider-account-ids-outside-registry~1]
    def test_raw_provider_account_ids_live_only_in_the_two_permitted_tables(self):
        holders = {table for table, columns in SHIPPED.items() if "provider_uid" in columns}
        assert holders == {"core.external_identities", "core.provider_accounts"}
        for table, columns in SHIPPED.items():
            assert_no_raw_provider_account_ids(table, columns)
        with pytest.raises(ProofMaterialError):
            assert_no_raw_provider_account_ids("core.access_grants_anti_abuse", ["provider_uid"])
        with pytest.raises(ProofMaterialError):
            assert_no_raw_provider_account_ids("audit.auth_events",
                                               ["canonical_provider_account_id"])

    # [utest->req~proof-no-claim-finalization-table~1]
    def test_there_is_no_claim_finalization_table(self):
        assert_no_claim_finalization_table(SHIPPED)
        for table in ("core.claim_finalizations", "core.anonymous_claim_finalizations"):
            with pytest.raises(ProofMaterialError):
                assert_no_claim_finalization_table([table])


# --- The table-by-table inventory ----------------------------------------------------------------


class TestInventory:

    # Exactly three tables hold external identity material, and each entry says what it holds.
    # [utest->req~proof-external-identity-material-inventory~1]
    def test_external_identity_material_is_inventoried_table_by_table(self):
        assert set(EXTERNAL_IDENTITY_INVENTORY) == {
            "core.external_identities", "core.auth_challenges", "audit.auth_events"}
        assert inventory_for("core.external_identities").raw_subject is True
        assert inventory_for("core.auth_challenges").keyed_subject_hash is \
            DerivationFamily.preauth_subject_hash
        assert inventory_for("audit.auth_events").keyed_subject_hash is \
            DerivationFamily.actor_subject_hash
        for table in ("core.users", "core.access_grants", "core.provider_accounts"):
            with pytest.raises(ProofMaterialError):
                inventory_for(table)

    # The identity row is the only raw-subject store, and it also keeps the provider kind and
    # `provider_uid`; erasure retains all four in plaintext and the rows are never deleted.
    # [utest->req~proof-external-identities-retains-raw-subject~1]
    def test_the_identity_row_retains_the_raw_subject_and_provider_uid(self):
        columns = SHIPPED["core.external_identities"]
        assert {"issuer", "subject", "provider", "provider_uid"} <= set(columns)
        for use in ("uniqueness_enforcement", "reject_re_registration",
                    "operator_investigation_of_rejection"):
            assert assert_identity_field_use(
                use, reached_from="authentication_and_identity_path") == use

    # Never for profiling, analytics, marketing, contact or export, and not reachable from
    # anywhere but the authentication path and the operator functions those uses require.
    # [utest->req~proof-external-identities-retains-raw-subject~1]
    def test_the_retained_fields_have_a_closed_set_of_uses_and_callers(self):
        for use in ("profiling", "analytics", "marketing", "contact", "export"):
            with pytest.raises(ProofMaterialError):
                assert_identity_field_use(use, reached_from="authentication_and_identity_path")
        with pytest.raises(ProofMaterialError):
            assert_identity_field_use("uniqueness_enforcement", reached_from="analytics_pipeline")

    # `core.auth_challenges` holds a plaintext issuer and the keyed verifier, no other identity
    # material, and no purge job; consumption clears the verifier.
    # [utest->req~proof-auth-challenges-no-raw-subject~1]
    def test_the_challenge_row_holds_only_the_keyed_verifier(self):
        columns = SHIPPED["core.auth_challenges"]
        assert "preauth_issuer" in columns and "preauth_subject_hash" in columns
        assert "preauth_subject" not in columns and "subject" not in columns
        assert_challenge_identity_material(columns)
        consumed = consume_challenge_identity(
            {"preauth_issuer": "iss", "preauth_subject_hash": b"x", "consumed_at": NOW})
        assert consumed["preauth_subject_hash"] is None
        assert consumed["preauth_issuer"] == "iss"

    # [utest->req~proof-auth-challenges-no-raw-subject~1]
    def test_other_identity_material_on_the_challenge_row_is_refused(self):
        with pytest.raises(ProofMaterialError):
            assert_challenge_identity_material(["preauth_issuer", "preauth_subject_hash",
                                                "preauth_email"])

    # `audit.auth_events` holds the issuer and the keyed actor hash only, is never purged, and
    # nothing copies the raw subject or `provider_uid` into a log, metric or audit row.
    # [utest->req~proof-auth-events-hashed-actor-only~1]
    def test_the_audit_row_keeps_the_hashed_actor_only(self):
        columns = SHIPPED["audit.auth_events"]
        assert {"actor_issuer", "actor_subject_hash", "actor_subject_hash_key_version"} <= \
            set(columns)
        assert "actor_subject" not in columns and "provider_uid" not in columns
        assert_auth_event_actor_only(columns)
        assert AUTH_EVENT_RETENTION_OWNER == "00-overview-and-shared-contracts.md"
        for field in ("subject", "raw_subject", "sub", "provider_uid"):
            with pytest.raises(ProofMaterialError):
                assert_auth_event_actor_only([field])


# --- What decides free-credit eligibility ---------------------------------------------------------


class TestEligibility:

    # Decided from the per-device device-check state, not from a stored per-device identifier.
    # [utest->req~proof-device-eligibility-from-vendor-state~1]
    def test_device_eligibility_comes_from_the_vendor_state(self):
        assert device_eligibility_signal(DevicePlatform.ios) == "apple_devicecheck"
        assert device_eligibility_signal(DevicePlatform.android) == \
            "play_integrity_device_recall"
        with pytest.raises(ProofMaterialError):
            device_eligibility_signal(DevicePlatform.ios, stored_device_identifier="dev-1")

    # The backend never derives or hashes a stable provider device principal.
    # [utest->req~proof-device-eligibility-from-vendor-state~1]
    def test_no_stable_device_principal_is_derived(self):
        from nativespeaker.api.auth.proof_material import DERIVED_DEVICE_PRINCIPALS
        assert DERIVED_DEVICE_PRINCIPALS == frozenset()
        for table, columns in SHIPPED.items():
            assert_no_raw_device_ids(table, columns)

    # Two account-deduped paths, both on the stable provider UID; neither trusts client input.
    # [utest->req~proof-account-eligibility-two-paths~1]
    def test_account_eligibility_has_two_paths_and_trusts_no_client_input(self):
        registered = account_eligibility_inputs(AccountEligibilityPath.registered_account_grant)
        assert "stored_provider_uid" in registered
        assert "mandatory_fail_closed_provider_data_read" in registered
        web = account_eligibility_inputs(AccountEligibilityPath.web_anonymous_gate)
        assert web[0] == "closed_classifier_over_complete_provider_data"
        assert "stored_provider_uid" in web
        for path in AccountEligibilityPath:
            with pytest.raises(ProofMaterialError):
                account_eligibility_inputs(path, client_supplied=["provider_account_id"])

    # The device-check signal is not an ownership or ownership-recovery credential.
    # [utest->req~proof-device-check-not-ownership-credential~1]
    def test_the_device_check_signal_is_no_ownership_credential(self):
        assert_device_check_not_ownership(ProofUse.anti_abuse_gate)
        for use in (ProofUse.ownership, ProofUse.recovery, ProofUse.identity,
                    ProofUse.account_resolution, ProofUse.upgrade):
            with pytest.raises(InvariantError):
                assert_device_check_not_ownership(use)
        with pytest.raises(ProofMaterialError):
            assert_device_check_not_ownership(ProofUse.anti_abuse_gate,
                                              recovers=["chats", "subscriptions"])


# --- The anti-abuse row, and the general prohibition ----------------------------------------------


class TestAntiAbuseRow:

    # The shape belongs to the schema file; what this file states is the prohibition.
    # [utest->req~proof-anti-abuse-row-prohibitions~1]
    def test_the_row_carries_none_of_the_prohibited_material(self):
        assert ANTI_ABUSE_ROW_SHAPE_OWNER == "06-schema-reference.md"
        assert_anti_abuse_row_prohibitions(SHIPPED["core.access_grants_anti_abuse"])
        for column in ("attestation_key_id", "attestation_key_hash", "attestation_provider",
                       "devicecheck_token", "device_id", "stable_device_principal_hash"):
            with pytest.raises(ProofMaterialError):
                assert_anti_abuse_row_prohibitions([column])


class TestRawProofMaterial:

    # Live store-state verification's redaction rules belong to the restore file; the general
    # prohibition still binds that material.
    # [utest->req~proof-live-store-redaction-owned-by-restore-file~1]
    def test_the_restore_file_owns_the_live_store_rules(self):
        assert LIVE_STORE_REDACTION_OWNER == \
            "04-subscription-restore-and-entitlement-transfer.md"
        assert LIVE_STORE_RULES_RESTATED_HERE == frozenset()
        assert live_store_verification_details("entitled") == \
            {"store_state_verification": "entitled"}
        with pytest.raises(ProofMaterialError):
            live_store_verification_details("entitled", raw_provider_response={"signedPayload": 1})

    # No table stores raw proof material, and the shipped schema has none.
    # [utest->req~proof-no-raw-proof-material-stored~1]
    def test_no_table_stores_raw_proof_material(self):
        for table, columns in SHIPPED.items():
            assert_no_raw_proof_material(table, columns)
        for column in ("id_token", "restore_proof", "purchase_token", "signed_transaction",
                       "attestation_blob", "play_integrity_verdict", "devicecheck_payload",
                       "attestation_private_key", "device_identifier"):
            with pytest.raises(ProofMaterialError):
                assert_no_raw_proof_material("audit.auth_events", [column])

    # Audit insertion redacts before write: `details` keeps canonical proof fingerprints and
    # structured non-secret context, and the secret carriers are replaced.
    # [utest->req~proof-no-raw-proof-material-stored~1]
    def test_audit_insertion_redacts_before_write(self):
        event = terminal_event(
            AttemptPhase.business, AuthEventResult.policy_rejected,
            operation=AuthOperation.claim_anonymous_grant, actor=actor(),
            details={"verification": {"restore_proof": "eyJhbGciOi.payload.sig",
                                      "play_integrity_verdict": {"deviceRecall": "x"},
                                      "devicecheck_token": "abc",
                                      "purchase_token": "tok-1",
                                      "proof_fingerprints": ["fp-1"]},
                     "mutation": {"access_grant_id": None}})
        row = redacted_audit_row(event, created_at=NOW)
        verification = row["details"]["verification"]
        for secret in ("restore_proof", "play_integrity_verdict", "devicecheck_token",
                       "purchase_token"):
            assert verification[secret] == REDACTED
        # Canonical proof fingerprints and structured non-secret context survive.
        assert verification["proof_fingerprints"] == ["fp-1"]
        assert row["details"]["mutation"]["access_grant_id"] is None
        assert row["actor_subject_hash"] == bytes(range(32))
