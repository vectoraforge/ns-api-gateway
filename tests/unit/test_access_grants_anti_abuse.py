"""`core.access_grants_anti_abuse`: the free-credit grant's evidence row.

The row shape — the column set, the `core.native_claim_provider` enum, and the per-source CHECK —
is owned by the schema reference, so the structural assertions here read the applied migration and
compare it against that contract. The behavioural ones drive the write-side guards: which evidence
tuples the per-source CHECK admits, which gate a claim consumes, and what a duplicate does.
"""

from uuid import uuid7

import pytest

from nativespeaker.api.auth.entitlement import AccessGrantSource
from nativespeaker.api.auth.external_identities import NativeClaimPlatform
from nativespeaker.api.auth.grant_schema import (
    ACCESS_GRANTS_TABLE,
    ANDROID_ENUM_VALUE,
    ANDROID_ROLLOUT_BACKFILLS,
    ANDROID_ROLLOUT_ORDER,
    ANTI_ABUSE_COLUMNS,
    ANTI_ABUSE_COMPOSITE_FK,
    ANTI_ABUSE_KEY,
    ANTI_ABUSE_SOURCE_CHECK,
    ANTI_ABUSE_TABLE,
    ATTESTATION_ARTIFACTS,
    COMPETING_ROW_SHAPE_ENUMERATIONS,
    GATE_CONSUMPTIONS_KEY,
    GATE_CONSUMPTIONS_TABLE,
    GRANT_SOURCE_PROVENANCE_MECHANISMS,
    IDP_ACCOUNT_HASH_IS_AUTHORITATIVE,
    MALFORMED_EVIDENCE_TUPLES,
    NATIVE_CLAIM_PROVIDERS,
    REGISTERED_ACTIVATION_RULES_OWNER,
    VALID_EVIDENCE_TUPLES,
    VENDOR_BIT_COMPENSATIONS,
    VENDOR_BIT_FALLBACK,
    AntiAbuseForm,
    DuplicateDetection,
    GrantSchemaError,
    anti_abuse_form,
    anti_abuse_row_bounds,
    assert_android_enum_rollout_additive,
    assert_hash_not_derived_from_attestation,
    assert_no_raw_anti_abuse_material,
    assert_registered_activation_not_native_state,
    duplicate_claim_rejection,
    evidence_tuple_form,
    gate_for,
    native_claim_provider_for,
    native_claim_write_order,
)
from nativespeaker.api.auth.invariants import (
    DevicePlatform,
    GateAlreadyConsumedError,
    GateConsumptionKind,
    IdentityProvider,
    InvariantError,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.proof_adapters import anonymous_device_grant_row
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from unit.test_schema_ddl import MIGRATION, declarative_section, parse

APPLIED = parse(declarative_section(MIGRATION.read_text()))
ANTI_ABUSE = APPLIED.tables[ANTI_ABUSE_TABLE]
PER_SOURCE_CHECK = next(c for c in ANTI_ABUSE.constraints if "native_claim_provider" in c)

ANONYMOUS = AccessGrantSource.anonymous_device_grant
REGISTERED = AccessGrantSource.registered_account_grant


# --- What the table is for ----------------------------------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-purpose~1]
def test_the_table_holds_evidence_for_the_two_free_credit_sources_only():
    """It is keyed one-to-one to the grant, and only the two free-credit sources have rows."""
    assert ANTI_ABUSE.columns[ANTI_ABUSE_KEY] == "UUID PRIMARY KEY"
    assert ANTI_ABUSE_SOURCE_CHECK in " ".join(ANTI_ABUSE.constraints)
    for source in (ANONYMOUS, REGISTERED):
        assert gate_for(source) in set(GateConsumptionKind)
    for source in (AccessGrantSource.subscription, AccessGrantSource.manual):
        with pytest.raises(GrantSchemaError):
            gate_for(source)


# --- The column set and what each column means --------------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-grant-id-field~1]
def test_grant_id_is_the_primary_key_and_cascades_from_its_grant():
    assert ANTI_ABUSE_COLUMNS[0].name == ANTI_ABUSE_KEY
    assert ANTI_ABUSE_COLUMNS[0].nullable is False
    assert ANTI_ABUSE.columns[ANTI_ABUSE_KEY] == "UUID PRIMARY KEY"
    fk = next(c for c in ANTI_ABUSE.constraints if c.startswith("FOREIGN KEY"))
    assert f"REFERENCES {ACCESS_GRANTS_TABLE} (id, source)" in fk
    assert "ON DELETE CASCADE" in fk
    assert ANTI_ABUSE_COMPOSITE_FK.on_delete == "CASCADE"


# [utest->req~schema-access-grants-anti-abuse-grant-source-field~1]
def test_grant_source_is_pinned_to_the_linked_grant_by_the_composite_foreign_key():
    assert ANTI_ABUSE.columns["grant_source"] == "core.access_grant_source NOT NULL"
    fk = next(c for c in ANTI_ABUSE.constraints if c.startswith("FOREIGN KEY"))
    assert "FOREIGN KEY (grant_id, grant_source)" in fk
    # It also drives the partial-index predicates and the per-source CHECKs.
    assert "grant_source" in ANTI_ABUSE_SOURCE_CHECK
    assert "grant_source = 'anonymous_device_grant'" in PER_SOURCE_CHECK
    assert "grant_source = 'registered_account_grant'" in PER_SOURCE_CHECK


# [utest->req~schema-access-grants-anti-abuse-native-claim-provider-field~1]
def test_native_claim_provider_names_the_platform_claim_state_provider():
    assert ANTI_ABUSE.columns["native_claim_provider"] == "core.native_claim_provider"
    assert APPLIED.enums["core.native_claim_provider"] == ("ios_devicecheck",
                                                           "android_play_integrity")
    assert (native_claim_provider_for(DevicePlatform.ios)
            is NativeClaimPlatform.ios_devicecheck)
    assert (native_claim_provider_for(DevicePlatform.android)
            is NativeClaimPlatform.android_play_integrity)
    # The web branch has no native form at all.
    with pytest.raises(GrantSchemaError):
        native_claim_provider_for(DevicePlatform.web)


# [utest->req~schema-access-grants-anti-abuse-native-claim-provider-field~1]
def test_native_claim_provider_must_be_null_for_web_and_registered_rows():
    assert anti_abuse_form(grant_source=ANONYMOUS, idp_account_hash=b"a",
                           idp_account_hash_key_version=1) is AntiAbuseForm.web
    with pytest.raises(InvariantError):
        anti_abuse_form(grant_source=REGISTERED,
                        native_claim_provider=NativeClaimPlatform.ios_devicecheck,
                        idp_account_hash=b"a", idp_account_hash_key_version=1)


# [utest->req~schema-access-grants-anti-abuse-idp-account-hash-field~1]
def test_idp_account_hash_is_the_hmac_alias_and_never_the_authority():
    assert ANTI_ABUSE.columns["idp_account_hash"] == "BYTEA"
    assert IDP_ACCOUNT_HASH_IS_AUTHORITATIVE is False
    # Required for the registered and web anonymous shapes, NULL for the native shape.
    assert anti_abuse_form(grant_source=REGISTERED, idp_account_hash=b"a",
                           idp_account_hash_key_version=1) is AntiAbuseForm.registered
    assert anti_abuse_form(grant_source=ANONYMOUS,
                           native_claim_provider=NativeClaimPlatform.ios_devicecheck
                           ) is AntiAbuseForm.native
    with pytest.raises(InvariantError):
        anti_abuse_form(grant_source=ANONYMOUS,
                        native_claim_provider=NativeClaimPlatform.ios_devicecheck,
                        idp_account_hash=b"a", idp_account_hash_key_version=1)


# [utest->req~schema-access-grants-anti-abuse-idp-hash-key-version-field~1]
def test_the_key_version_travels_with_the_hash_it_derived():
    assert ANTI_ABUSE.columns["idp_account_hash_key_version"] == "SMALLINT"
    # Neither half is ever stored without the other, so a rotation window stays resolvable.
    for hash_bytes, version in ((b"a", None), (None, 2)):
        with pytest.raises(InvariantError):
            anti_abuse_form(grant_source=REGISTERED, idp_account_hash=hash_bytes,
                            idp_account_hash_key_version=version)
    # An older key version stays valid for lookup: the version is recorded, not validated away.
    assert anti_abuse_form(grant_source=REGISTERED, idp_account_hash=b"a",
                           idp_account_hash_key_version=1) is AntiAbuseForm.registered


# [utest->req~schema-access-grants-anti-abuse-created-at-field~1]
def test_created_at_is_the_insert_timestamp():
    assert ANTI_ABUSE.columns["created_at"] == "TIMESTAMPTZ NOT NULL"
    assert [column.name for column in ANTI_ABUSE_COLUMNS][-1] == "created_at"
    row = anonymous_device_grant_row(grant_id=uuid7(), platform=DevicePlatform.ios)
    assert row["created_at"] is not None


# [utest->req~schema-access-grants-anti-abuse-purpose~1]
def test_the_declared_column_set_is_the_applied_column_set():
    declared = {column.name for column in ANTI_ABUSE_COLUMNS}
    applied = set(ANTI_ABUSE.columns)
    # The one extra applied column is the generated key the registered gate's uniqueness uses.
    assert applied - declared == {"registered_account_grant_id"}
    assert declared - applied == set()


# --- The evidence shapes the per-source CHECK admits ---------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-anonymous-shape-forms~1]
def test_the_anonymous_shape_admits_the_native_form_and_the_web_form_and_nothing_else():
    assert anti_abuse_form(grant_source=ANONYMOUS,
                           native_claim_provider=NativeClaimPlatform.android_play_integrity
                           ) is AntiAbuseForm.native
    assert anti_abuse_form(grant_source=ANONYMOUS, idp_account_hash=b"a",
                           idp_account_hash_key_version=1) is AntiAbuseForm.web
    # Neither both nor neither: the CHECK's two arms are exclusive.
    with pytest.raises(InvariantError):
        anti_abuse_form(grant_source=ANONYMOUS)
    with pytest.raises(InvariantError):
        anti_abuse_form(grant_source=ANONYMOUS,
                        native_claim_provider=NativeClaimPlatform.ios_devicecheck,
                        idp_account_hash=b"a", idp_account_hash_key_version=1)
    # And the applied CHECK spells out the same two arms.
    assert ("native_claim_provider IS NOT NULL AND idp_account_hash IS NULL "
            "AND idp_account_hash_key_version IS NULL") in PER_SOURCE_CHECK
    assert ("native_claim_provider IS NULL AND idp_account_hash IS NOT NULL "
            "AND idp_account_hash_key_version IS NOT NULL") in PER_SOURCE_CHECK


# [utest->req~schema-access-grants-anti-abuse-registered-shape-required~1]
def test_the_registered_shape_requires_the_hash_pair_and_forbids_a_native_provider():
    assert ("grant_source = 'registered_account_grant' AND native_claim_provider IS NULL "
            "AND idp_account_hash IS NOT NULL AND idp_account_hash_key_version IS NOT NULL"
            ) in PER_SOURCE_CHECK
    assert anti_abuse_form(grant_source=REGISTERED, idp_account_hash=b"a",
                           idp_account_hash_key_version=1) is AntiAbuseForm.registered
    with pytest.raises(InvariantError):
        anti_abuse_form(grant_source=REGISTERED)
    with pytest.raises(InvariantError):
        anti_abuse_form(grant_source=REGISTERED,
                        native_claim_provider=NativeClaimPlatform.android_play_integrity,
                        idp_account_hash=b"a", idp_account_hash_key_version=1)


# [utest->req~schema-access-grants-anti-abuse-conformance-test-tuples~1]
@pytest.mark.parametrize("candidate", VALID_EVIDENCE_TUPLES,
                         ids=[tuple_.label for tuple_ in VALID_EVIDENCE_TUPLES])
def test_the_four_valid_evidence_tuples_are_accepted(candidate):
    expected = {"native_ios": AntiAbuseForm.native, "native_android": AntiAbuseForm.native,
                "web_anonymous": AntiAbuseForm.web, "registered": AntiAbuseForm.registered}
    assert evidence_tuple_form(candidate) is expected[candidate.label]


# [utest->req~schema-access-grants-anti-abuse-conformance-test-tuples~1]
@pytest.mark.parametrize("candidate", MALFORMED_EVIDENCE_TUPLES,
                         ids=[tuple_.label for tuple_ in MALFORMED_EVIDENCE_TUPLES])
def test_the_malformed_rows_are_rejected(candidate):
    with pytest.raises(InvariantError):
        evidence_tuple_form(candidate)


# [utest->req~schema-access-grants-anti-abuse-conformance-test-tuples~1]
def test_the_android_claim_path_records_android_play_integrity_and_never_ios_devicecheck():
    row = anonymous_device_grant_row(grant_id=uuid7(), platform=DevicePlatform.android)
    assert row["native_claim_provider"] is NativeClaimPlatform.android_play_integrity
    assert row["native_claim_provider"] is not NativeClaimPlatform.ios_devicecheck
    assert NATIVE_CLAIM_PROVIDERS[DevicePlatform.android] is ANDROID_ENUM_VALUE


# --- The native form across platforms -----------------------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-native-form-cross-platform~1]
def test_the_native_form_is_identical_on_both_platforms_but_for_the_recorded_provider():
    ios = anonymous_device_grant_row(grant_id=uuid7(), platform=DevicePlatform.ios)
    android = anonymous_device_grant_row(grant_id=uuid7(), platform=DevicePlatform.android)
    differing = {key for key in ios if ios[key] != android[key]}
    assert differing <= {"grant_id", "native_claim_provider", "created_at"}
    assert native_claim_write_order(DevicePlatform.ios) == native_claim_write_order(
        DevicePlatform.android)
    # The vendor bit is confirmed before either row is inserted, and both rows go in one commit.
    assert native_claim_write_order(DevicePlatform.ios) == (
        "vendor_bit_write_confirmed", "anti_abuse_row_insert", "grant_row_insert", "commit")


# [utest->req~schema-access-grants-anti-abuse-native-form-cross-platform~1]
def test_a_commit_failure_after_the_vendor_write_is_not_compensated():
    assert not VENDOR_BIT_COMPENSATIONS
    assert VENDOR_BIT_FALLBACK == "registered_sign_up"


# [utest->req~schema-access-grants-anti-abuse-no-hash-from-attestation~1]
def test_no_idp_account_hash_is_synthesized_from_attestation_material():
    assert_hash_not_derived_from_attestation(["provider_uid_from_admin_lookup"])
    for artifact in sorted(ATTESTATION_ARTIFACTS):
        with pytest.raises(GrantSchemaError):
            assert_hash_not_derived_from_attestation([artifact])
    # The native row's evidence is the vendor bit itself, with no hash at all.
    row = anonymous_device_grant_row(grant_id=uuid7(), platform=DevicePlatform.android)
    assert row["idp_account_hash"] is None
    assert row["idp_account_hash_key_version"] is None


# [utest->req~schema-access-grants-anti-abuse-android-enum-additive~1]
def test_adding_the_android_enum_value_is_additive_with_no_backfill():
    assert ANDROID_ENUM_VALUE.value in APPLIED.enums["core.native_claim_provider"]
    assert not ANDROID_ROLLOUT_BACKFILLS
    assert_android_enum_rollout_additive()
    with pytest.raises(GrantSchemaError):
        assert_android_enum_rollout_additive(rows_affected=["existing_ios_rows"])
    # The enum value and the corrected CHECK land before the Android grant path deploys.
    with pytest.raises(GrantSchemaError):
        assert_android_enum_rollout_additive(deploy_order=list(reversed(ANDROID_ROLLOUT_ORDER)))
    # Existing iOS, web anonymous and registered rows stay valid under the corrected CHECK.
    for candidate in VALID_EVIDENCE_TUPLES:
        assert evidence_tuple_form(candidate) in set(AntiAbuseForm)


# --- Gate uniqueness -----------------------------------------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-registered-gate-global-uniqueness~1]
def test_a_provider_account_receives_at_most_one_registered_free_credit_claim_globally():
    consumptions = APPLIED.tables[GATE_CONSUMPTIONS_TABLE]
    assert ("PRIMARY KEY (" + ", ".join(GATE_CONSUMPTIONS_KEY) + ")"
            in consumptions.constraints)
    assert gate_for(REGISTERED) is GateConsumptionKind.registered_account_grant
    gates = ProviderAccountGates()
    account = ProviderAccount(IdentityProvider.google, "google-uid-1")
    gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
    # A different Firebase account, user or device resolving to the same provider UID is blocked.
    with pytest.raises(GateAlreadyConsumedError):
        gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())


# [utest->req~schema-access-grants-anti-abuse-web-gate-uniqueness~1]
def test_the_web_anonymous_gate_is_a_separate_row_with_its_own_uniqueness():
    assert gate_for(ANONYMOUS) is GateConsumptionKind.web_anonymous_gate
    assert gate_for(ANONYMOUS) is not gate_for(REGISTERED)
    gates = ProviderAccountGates()
    account = ProviderAccount(IdentityProvider.apple, "apple-uid-1")
    gates.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())
    # The same account may still hold one of the other kind: distinct rows, distinct brakes.
    gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
    with pytest.raises(GateAlreadyConsumedError):
        gates.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())
    # The enforced conflict is the gate row's, not the hash alias'.
    assert IDP_ACCOUNT_HASH_IS_AUTHORITATIVE is False


# [utest->req~schema-access-grants-anti-abuse-registered-activation-rules~1]
def test_registered_activation_is_governed_by_the_registered_grant_rules():
    assert REGISTERED_ACTIVATION_RULES_OWNER == "claim_registered_grant"
    assert_registered_activation_not_native_state()
    for native_input in ("ios_registered_bit", "device_check_state", "play_integrity_recall"):
        with pytest.raises(GrantSchemaError):
            assert_registered_activation_not_native_state([native_input])


# --- What the row never stores -------------------------------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-no-raw-material-stored~1]
def test_the_row_stores_no_raw_vendor_token_hash_or_provider_identifier():
    assert_no_raw_anti_abuse_material([column.name for column in ANTI_ABUSE_COLUMNS])
    for forbidden in ("devicecheck_token", "play_integrity_token", "bot_check_token",
                      "device_check_state_hash", "stable_device_principal_hash", "provider_uid"):
        with pytest.raises((GrantSchemaError, InvariantError)):
            assert_no_raw_anti_abuse_material(["grant_id", forbidden])
    # Nor are any of these columns of the applied table — web anonymous rows included.
    for forbidden in ("devicecheck_token", "play_integrity_token", "bot_check_token",
                      "device_principal_hash", "provider_uid"):
        assert forbidden not in ANTI_ABUSE.columns


# --- Duplicate free-credit claims ----------------------------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-native-duplicate-result~1]
def test_a_native_duplicate_is_audited_native_claim_already_claimed_and_rolls_back():
    rejection = duplicate_claim_rejection(DuplicateDetection.native_device_check_state)
    assert str(rejection.result) == "native_claim_already_claimed"
    assert rejection.client_class is ClientErrorClass.device_grant_exhausted
    assert rejection.rolls_back_grant_insert is True
    outside = duplicate_claim_rejection(DuplicateDetection.native_device_check_state,
                                        inside_activation=False)
    assert outside.rolls_back_grant_insert is False


# [utest->req~schema-access-grants-anti-abuse-web-duplicate-rollback~1]
def test_a_web_duplicate_rolls_the_grant_insert_back_in_the_same_transaction():
    rejection = duplicate_claim_rejection(DuplicateDetection.web_gate)
    assert rejection.rolls_back_grant_insert is True
    assert str(rejection.result) == "anti_abuse_already_claimed"
    assert rejection.client_class is ClientErrorClass.device_grant_exhausted
    # The conflict itself is the gate-consumption row's uniqueness.
    gates = ProviderAccountGates()
    account = ProviderAccount(IdentityProvider.google, "google-uid-2")
    gates.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())
    with pytest.raises(GateAlreadyConsumedError) as raised:
        gates.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())
    assert raised.value.result is rejection.result


# [utest->req~schema-access-grants-anti-abuse-registered-duplicate-result~1]
def test_a_registered_duplicate_surfaces_as_account_already_claimed():
    rejection = duplicate_claim_rejection(DuplicateDetection.registered_gate)
    assert str(rejection.result) == "idp_account_already_claimed"
    assert rejection.client_class is ClientErrorClass.account_already_claimed
    assert rejection.client_class is not ClientErrorClass.verification_required


# --- The composite foreign key and the three bounds ----------------------------------------------

# [utest->req~schema-access-grants-anti-abuse-composite-fk-properties~1]
def test_the_composite_foreign_key_supplies_three_properties_at_once():
    fk = next(c for c in ANTI_ABUSE.constraints if c.startswith("FOREIGN KEY"))
    assert fk == ("FOREIGN KEY (grant_id, grant_source) "
                  f"REFERENCES {ACCESS_GRANTS_TABLE} (id, source) "
                  "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED")
    # One key, replacing the prior single-column reference: there is no second FK on grant_id.
    assert len([c for c in ANTI_ABUSE.constraints if c.startswith("FOREIGN KEY")]) == 1
    assert ANTI_ABUSE_COMPOSITE_FK.columns == ("grant_id", "grant_source")
    assert ANTI_ABUSE_COMPOSITE_FK.deferrable is True
    # `grant_source` gets no trigger, function or permission-boundary protection either.
    assert not GRANT_SOURCE_PROVENANCE_MECHANISMS
    assert not COMPETING_ROW_SHAPE_ENUMERATIONS


# [utest->req~schema-access-grants-anti-abuse-no-row-for-other-sources~1]
def test_no_row_can_exist_for_a_subscription_or_manual_grant():
    assert ANTI_ABUSE_SOURCE_CHECK in " ".join(ANTI_ABUSE.constraints)
    for source in (AccessGrantSource.subscription, AccessGrantSource.manual):
        assert source.value not in ANTI_ABUSE_SOURCE_CHECK
        with pytest.raises(InvariantError):
            anti_abuse_form(grant_source=source, idp_account_hash=b"a",
                            idp_account_hash_key_version=1)


# [utest->req~schema-access-grants-anti-abuse-exactly-one-declarative~1]
def test_the_three_bounds_are_all_declarative():
    bounds = anti_abuse_row_bounds()
    assert len(bounds) == 3
    # The upper bound is the primary key, the source restriction is the FK plus the CHECK, and
    # the lower bound is the deferrable foreign key from the grant table's generated column.
    assert ANTI_ABUSE.columns[ANTI_ABUSE_KEY] == "UUID PRIMARY KEY"
    assert any("anti_abuse_required_grant_id" in alter for alter in APPLIED.alters)
    assert "DEFERRABLE INITIALLY DEFERRED" in next(
        alter for alter in APPLIED.alters if "anti_abuse_required_grant_id" in alter)
