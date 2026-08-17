"""The three free-grant proof adapters, and the native claim sequence they run inside."""

from typing import Any
from uuid import uuid7

import pytest
from pydantic import SecretStr

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.external_identities import NativeClaimPlatform
from nativespeaker.api.auth.invariants import DevicePlatform, InvariantError, ProofUse
from nativespeaker.api.auth.operations import AuthOperation
from nativespeaker.api.auth.proof_adapters import (
    DEVICECHECK_BIT_MEANING,
    TURNSTILE_TEST_SECRETS,
    TURNSTILE_TEST_SITEKEYS,
    AndroidClaimMaterial,
    AppleCredentials,
    ChallengeClaimOutcome,
    ClaimBranch,
    ClaimState,
    DeviceCheckAdapter,
    DeviceCheckBit,
    DeviceCheckEnvironment,
    DeviceGrantExhausted,
    ExecutionContext,
    GateLayer,
    GoogleCredentials,
    IosClaimMaterial,
    NativeClaimLedger,
    NativeClaimStep,
    NativeClaimUnavailable,
    NativeClaimWriteFailed,
    PlayIntegrityAdapter,
    ProofAdapterError,
    ProofRejected,
    RecallState,
    ReleaseKey,
    ReleasePolicyRegistry,
    ReleaseRecallPolicy,
    TurnstileConfig,
    TurnstileDenied,
    TurnstileEnvironment,
    TurnstileMisconfigured,
    TurnstileUnavailable,
    anonymous_device_grant_row,
    anonymous_grant_gate_layer,
    assert_action_cdata_not_matched,
    assert_completion_unbounded_by_clock,
    assert_configured_credentials,
    assert_execution_context,
    assert_fail_closed_scope,
    assert_no_vendor_evidence_age,
    assert_platform_supported,
    assert_same_device_race_bounded,
    assert_untrusted_client_assertions,
    assert_vendor_state_access,
    claim_challenge_before_vendor,
    claim_challenge_ttl,
    claim_state_for,
    consume_claimed_challenge,
    consume_siteverify_budget,
    devicecheck_bit_for,
    devicecheck_role,
    ledger_authority,
    native_claim,
    play_integrity_role,
    recall_state_for,
    registered_claim_requires_recall,
    retry_after_failed_claim,
    stranded_slot_remediation,
    turnstile_remoteip,
    turnstile_replay_bound,
    turnstile_siteverify,
    untrusted_vendor_material,
    web_gate_requirements,
)
from nativespeaker.api.auth.proof_material import ProofMaterialError
from nativespeaker.api.ratelimit.config import (
    TURNSTILE_ENTRY,
    RateLimitEntry,
    RateLimitsConfig,
    Strategy,
)
from nativespeaker.api.ratelimit.keys import (
    UNRESOLVED_ADDRESS_KEY,
    AddressSource,
    GatewayResolvedAddress,
)
from nativespeaker.api.ratelimit.limiter import RateLimiter
from nativespeaker.api.ratelimit.ordering import DeviceBitCall, DeviceBitWriteError

APPLE = AppleCredentials(team_id="TEAM123456", key_id="KEY1", private_key=SecretStr("pem"))
GOOGLE = GoogleCredentials(package_name="com.nativespeaker.app",
                           service_account_email="svc@example.iam.gserviceaccount.com",
                           private_key=SecretStr("pem"))
IOS_MATERIAL = IosClaimMaterial(query_token="q-token", update_token="u-token")
ANDROID_MATERIAL = AndroidClaimMaterial(integrity_token="integrity-token")


class FakeDeviceCheck:
    """A DeviceCheck server-to-server transport that records what the adapter sent it."""

    def __init__(self, *, bits: dict[str, Any] | None = None,
                 query_error: Exception | None = None,
                 update_error: Exception | None = None,
                 acknowledgment: Any = None):
        self.bits = {"bit0": False, "bit1": False} if bits is None else bits
        self.query_error = query_error
        self.update_error = update_error
        self.acknowledgment = {"acknowledged": True} if acknowledgment is None else acknowledgment
        self.queries: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    def query_two_bits(self, *, query_token: str, team_id: str,
                       environment: DeviceCheckEnvironment) -> Any:
        self.queries.append({"query_token": query_token, "team_id": team_id,
                             "environment": environment})
        if self.query_error is not None:
            raise self.query_error
        return self.bits

    def update_two_bits(self, *, update_token: str, team_id: str,
                        environment: DeviceCheckEnvironment, bits: Any) -> Any:
        self.updates.append({"update_token": update_token, "team_id": team_id,
                             "environment": environment, "bits": dict(bits)})
        if self.update_error is not None:
            raise self.update_error
        return self.acknowledgment


class FakePlayIntegrity:
    """A Play Integrity transport that records the token it was handed."""

    def __init__(self, *, verdict: Any = None, decode_error: Exception | None = None,
                 write_error: Exception | None = None, acknowledgment: Any = None):
        self.verdict = ({"deviceRecall": {"anonymous_device_grant_recall": False,
                                          "registered_account_grant_recall": False}}
                        if verdict is None else verdict)
        self.decode_error = decode_error
        self.write_error = write_error
        self.acknowledgment = {"confirmed": True} if acknowledgment is None else acknowledgment
        self.decodes: list[str] = []
        self.writes: list[dict[str, Any]] = []

    def decode_verdict(self, *, integrity_token: str, credentials: GoogleCredentials) -> Any:
        self.decodes.append(integrity_token)
        if self.decode_error is not None:
            raise self.decode_error
        return self.verdict

    def write_recall(self, *, integrity_token: str, credentials: GoogleCredentials,
                     state: RecallState, value: bool) -> Any:
        self.writes.append({"integrity_token": integrity_token, "state": state, "value": value})
        if self.write_error is not None:
            raise self.write_error
        return self.acknowledgment


class FakeSiteverify:
    def __init__(self, payload: Any = None, error: Exception | None = None):
        self.payload = ({"success": True, "hostname": "app.nativespeaker.io"}
                        if payload is None else payload)
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def post(self, *, secret: str, response: str, remoteip: str | None) -> Any:
        self.calls.append({"secret": secret, "response": response, "remoteip": remoteip})
        if self.error is not None:
            raise self.error
        return self.payload


def production_turnstile(**overrides: Any) -> TurnstileConfig:
    fields: dict[str, Any] = {
        "environment": TurnstileEnvironment.production,
        "sitekey": "0x4AAAAAAAreal",
        "secret": SecretStr("0x4AAAAAAAsecret"),
        "hostname_allow_list": ("app.nativespeaker.io",),
    }
    fields.update(overrides)
    return TurnstileConfig(**fields)


def limiter(limit: str = "10/minute") -> RateLimiter:
    config = RateLimitsConfig(enabled=True, storage_uri="memory://",
                              strategy=Strategy.moving_window,
                              default=RateLimitEntry(limit="120/minute", key="ip"),
                              entries={TURNSTILE_ENTRY: RateLimitEntry(limit=limit,
                                                                       key="deployment")})
    return RateLimiter(config)


def run_ios_claim(adapter: DeviceCheckAdapter, *, eligible: bool = True,
                  operation: AuthOperation = AuthOperation.claim_anonymous_grant,
                  material: IosClaimMaterial = IOS_MATERIAL) -> tuple[Any, list[str]]:
    inserted: list[str] = []

    def insert() -> Any:
        grant_id = uuid7()
        inserted.append(str(grant_id))
        return grant_id

    outcome = native_claim(adapter, operation, material,
                           database_eligibility=lambda: eligible, insert_grant=insert)
    return outcome, inserted


# --- Anonymous device grant anti-abuse layers ---------------------------------------------------


# [utest->req~proof-anonymous-grant-no-degraded-mode~1]
def test_every_branch_has_one_mandatory_gate_and_no_degraded_mode():
    assert anonymous_grant_gate_layer(ClaimBranch.native_ios) is GateLayer.ios_devicecheck_state
    assert (anonymous_grant_gate_layer(ClaimBranch.native_android)
            is GateLayer.android_device_recall_state)
    assert anonymous_grant_gate_layer(ClaimBranch.web) is GateLayer.web_firebase_sign_in_gate
    with pytest.raises(ProofAdapterError):
        anonymous_grant_gate_layer(ClaimBranch.native_ios, degraded_mode="cached_positive")
    with pytest.raises(ProofAdapterError):
        anonymous_grant_gate_layer(ClaimBranch.web, attestation_key_proof="assertion")
    assert web_gate_requirements() == (
        "stored_provider_is_google_or_apple",
        "complete_provider_data_passes_closed_classifier",
        "idp_account_hash_uniqueness_per_provider_account")


# [utest->req~proof-distinct-per-device-claim-states~1]
def test_the_two_native_claims_use_distinct_per_device_states():
    anonymous = claim_state_for(AuthOperation.claim_anonymous_grant)
    registered = claim_state_for(AuthOperation.claim_registered_grant)
    assert anonymous is ClaimState.anonymous_device_grant_claimed
    assert registered is ClaimState.registered_account_grant_claimed
    assert anonymous is not registered
    with pytest.raises(ProofAdapterError):
        claim_state_for(AuthOperation.restore_subscription)


# [utest->req~proof-ios-devicecheck-bit-split~1]
# [utest->req~proof-devicecheck-bit-assignment~1]
def test_bit0_is_the_anonymous_claim_and_bit1_the_registered_one():
    assert (DEVICECHECK_BIT_MEANING[DeviceCheckBit.bit0]
            is ClaimState.anonymous_device_grant_claimed)
    assert (DEVICECHECK_BIT_MEANING[DeviceCheckBit.bit1]
            is ClaimState.registered_account_grant_claimed)
    assert devicecheck_bit_for(AuthOperation.claim_anonymous_grant) is DeviceCheckBit.bit0
    assert devicecheck_bit_for(AuthOperation.claim_registered_grant) is DeviceCheckBit.bit1
    with pytest.raises(ProofAdapterError):
        devicecheck_bit_for(AuthOperation.sync)


# [utest->req~proof-ios-devicecheck-bit-split~1]
def test_the_anonymous_claim_reads_and_writes_bit0_alone():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    run_ios_claim(adapter)
    assert transport.updates[0]["bits"] == {"bit0": True}


# [utest->req~proof-android-recall-state-split~1]
def test_android_uses_a_distinct_recall_state_per_operation():
    anonymous = recall_state_for(AuthOperation.claim_anonymous_grant)
    registered = recall_state_for(AuthOperation.claim_registered_grant)
    assert anonymous is not registered
    transport = FakePlayIntegrity()
    adapter = PlayIntegrityAdapter(GOOGLE, transport)
    native_claim(adapter, AuthOperation.claim_anonymous_grant, ANDROID_MATERIAL,
                 database_eligibility=lambda: True, insert_grant=uuid7)
    assert transport.writes[0]["state"] is anonymous


# [utest->req~proof-vendor-state-via-configured-credentials~1]
def test_vendor_state_uses_configured_credentials_and_never_client_state():
    assert_configured_credentials(APPLE)
    with pytest.raises(ProofAdapterError):
        assert_configured_credentials(APPLE, client_supplied_state={"bit0": False})
    with pytest.raises(ProofAdapterError):
        assert_configured_credentials(
            AppleCredentials(team_id="", key_id="KEY1", private_key=SecretStr("pem")))
    with pytest.raises(ProofAdapterError):
        DeviceCheckAdapter(
            GoogleCredentials(package_name="", service_account_email="",
                              private_key=SecretStr("")),  # type: ignore[arg-type]
            FakeDeviceCheck())


# [utest->req~proof-client-vendor-material-untrusted~1]
def test_client_vendor_material_is_never_identity_and_resolves_no_account():
    assert untrusted_vendor_material({"devicecheck_query_token": "q"})
    with pytest.raises(InvariantError):
        untrusted_vendor_material({"devicecheck_query_token": "q"}, use=ProofUse.identity)
    with pytest.raises(ProofAdapterError):
        untrusted_vendor_material({"play_integrity_token": "t"}, resolves_account="user-1")
    with pytest.raises(ProofAdapterError):
        untrusted_vendor_material({"subject": "sub-1"})


# [utest->req~proof-native-claim-sequence-mandatory~1]
def test_the_native_claim_steps_may_not_be_reordered_or_skipped():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    ledger = NativeClaimLedger()
    with pytest.raises(ProofAdapterError):
        # The vendor read cannot run before the material has been verified.
        adapter.read_claimed(AuthOperation.claim_anonymous_grant, IOS_MATERIAL, ledger)
    adapter.verify_material(AuthOperation.claim_anonymous_grant, IOS_MATERIAL, ledger)
    with pytest.raises(ProofAdapterError):
        # The write cannot skip the database eligibility step.
        adapter.write_claimed(AuthOperation.claim_anonymous_grant, IOS_MATERIAL, ledger)
    outcome, _ = run_ios_claim(DeviceCheckAdapter(APPLE, FakeDeviceCheck()))
    assert outcome.state is ClaimState.anonymous_device_grant_claimed


# [utest->req~proof-native-claim-verify-vendor-material~1]
# [utest->req~proof-ios-missing-update-material-fails-early~1]
# [utest->req~proof-devicecheck-client-material-proof-rejected~1]
def test_withheld_update_material_fails_before_any_vendor_call_and_before_any_grant():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    with pytest.raises(ProofRejected) as rejected:
        run_ios_claim(adapter, material=IosClaimMaterial(query_token="q", update_token=None))
    assert rejected.value.result is AuthEventResult.proof_malformed
    assert rejected.value.error_code == "proof_rejected"
    assert transport.queries == [] and transport.updates == []


# [utest->req~proof-native-claim-verify-vendor-material~1]
def test_android_carries_one_token_for_both_recall_calls():
    transport = FakePlayIntegrity()
    adapter = PlayIntegrityAdapter(GOOGLE, transport)
    native_claim(adapter, AuthOperation.claim_anonymous_grant, ANDROID_MATERIAL,
                 database_eligibility=lambda: True, insert_grant=uuid7)
    assert transport.decodes == ["integrity-token"]
    assert transport.writes[0]["integrity_token"] == "integrity-token"
    with pytest.raises(ProofRejected):
        native_claim(adapter, AuthOperation.claim_anonymous_grant,
                     AndroidClaimMaterial(integrity_token=" "),
                     database_eligibility=lambda: True, insert_grant=uuid7)


# [utest->req~proof-native-claim-vendor-read~1]
def test_a_read_failure_fails_closed_and_an_already_claimed_device_is_exhausted():
    unavailable = DeviceCheckAdapter(APPLE, FakeDeviceCheck(query_error=TimeoutError("apple")))
    with pytest.raises(NativeClaimUnavailable):
        run_ios_claim(unavailable)
    claimed = FakeDeviceCheck(bits={"bit0": True, "bit1": False})
    adapter = DeviceCheckAdapter(APPLE, claimed)
    with pytest.raises(DeviceGrantExhausted) as exhausted:
        run_ios_claim(adapter)
    assert exhausted.value.result is AuthEventResult.native_claim_already_claimed
    assert exhausted.value.error_code == "device_grant_exhausted"
    assert claimed.updates == []


# [utest->req~proof-native-claim-database-eligibility~1]
def test_database_eligibility_runs_after_the_read_and_before_the_write():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    with pytest.raises(ProofAdapterError):
        run_ios_claim(adapter, eligible=False)
    assert transport.queries and transport.updates == []


# [utest->req~proof-native-claim-vendor-write-gate~1]
# [utest->req~proof-devicecheck-bit0-write-before-grant~1]
def test_only_a_confirmed_vendor_write_permits_a_grant():
    for acknowledgment in ({"acknowledged": False}, {}, "ok"):
        transport = FakeDeviceCheck(acknowledgment=acknowledgment)
        adapter = DeviceCheckAdapter(APPLE, transport)
        with pytest.raises(NativeClaimWriteFailed) as failed:
            run_ios_claim(adapter)
        assert failed.value.result is AuthEventResult.native_claim_write_failed
    timed_out = DeviceCheckAdapter(APPLE, FakeDeviceCheck(update_error=TimeoutError("apple")))
    with pytest.raises(NativeClaimWriteFailed):
        run_ios_claim(timed_out)


# [utest->req~proof-native-claim-insert-grant~1]
def test_the_grant_row_is_inserted_only_after_the_vendor_confirms():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    outcome, inserted = run_ios_claim(adapter)
    assert outcome.write.confirmed and outcome.write.call is DeviceBitCall.devicecheck_write
    assert len(inserted) == 1
    failing = FakeDeviceCheck(acknowledgment={"acknowledged": False})
    with pytest.raises(NativeClaimWriteFailed):
        run_ios_claim(DeviceCheckAdapter(APPLE, failing))


# [utest->req~proof-two-authoritative-ledgers~1]
def test_the_database_and_the_vendor_state_are_two_authoritative_ledgers():
    assert str(ledger_authority("database")) == "user_received_a_grant"
    assert str(ledger_authority("vendor_per_device_state")) == "device_consumed_its_slot"
    with pytest.raises(ProofAdapterError):
        ledger_authority("cached_bit_copy")
    assert_same_device_race_bounded(1)
    with pytest.raises(ProofAdapterError):
        assert_same_device_race_bounded(2)
    assert str(stranded_slot_remediation()) == "manual"
    assert_vendor_state_access(AuthOperation.claim_anonymous_grant)
    for operation in (AuthOperation.upgrade_anonymous_to_registered,
                      AuthOperation.restore_subscription, AuthOperation.sync):
        with pytest.raises(ProofAdapterError):
            assert_vendor_state_access(operation)


# [utest->req~proof-native-claim-retry-and-execution-context~1]
def test_a_retry_is_a_whole_new_claim_in_a_disconnect_shielded_context():
    assert_execution_context(ExecutionContext.disconnect_shielded_task)
    with pytest.raises(ProofAdapterError):
        assert_execution_context(ExecutionContext.request_cancellation_scope)
    fresh = IosClaimMaterial(query_token="q2", update_token="u2")
    assert retry_after_failed_claim(fresh, previous_material=IOS_MATERIAL) is fresh
    with pytest.raises(ProofAdapterError):
        retry_after_failed_claim(IOS_MATERIAL, previous_material=IOS_MATERIAL)
    assert_fail_closed_scope(AuthOperation.claim_anonymous_grant)
    for operation in (AuthOperation.sync, AuthOperation.restore_subscription):
        with pytest.raises(ProofAdapterError):
            assert_fail_closed_scope(operation)


# [utest->req~proof-anonymous-device-grant-row-contents~1]
def test_the_anonymous_device_grant_row_carries_no_attestation_material():
    grant_id = uuid7()
    row = anonymous_device_grant_row(grant_id=grant_id, platform=DevicePlatform.ios)
    assert row["native_claim_provider"] is NativeClaimPlatform.ios_devicecheck
    assert row["idp_account_hash"] is None
    web = anonymous_device_grant_row(grant_id=grant_id, idp_account_hash=b"h" * 32,
                                     idp_account_hash_key_version=1)
    assert web["native_claim_provider"] is None
    with pytest.raises(ProofMaterialError):
        anonymous_device_grant_row(grant_id=grant_id, platform=DevicePlatform.ios,
                                   extra={"attestation_key_id": "k-1"})
    with pytest.raises(ProofMaterialError):
        anonymous_device_grant_row(grant_id=grant_id, platform=DevicePlatform.ios,
                                   extra={"attestation_provider": "app_attest"})
    with pytest.raises(InvariantError):
        # A row carrying neither evidence shape is not one the schema owner allows.
        anonymous_device_grant_row(grant_id=grant_id)


# --- The iOS proof adapter ------------------------------------------------------------------------


# [utest->req~proof-ios-devicecheck-role~1]
def test_devicecheck_is_anti_abuse_state_and_no_ios_endpoint_requires_app_attest():
    assert devicecheck_role() == "apple_devicecheck"
    for role in (ProofUse.identity, ProofUse.ownership, ProofUse.recovery, ProofUse.upgrade,
                 ProofUse.account_resolution):
        with pytest.raises(InvariantError):
            devicecheck_role(role)


# [utest->req~proof-ios-devicecheck-mandatory~1]
def test_devicecheck_is_mandatory_on_both_claims_and_production_rejects_development():
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    ledger = NativeClaimLedger()
    adapter.verify_material(AuthOperation.claim_registered_grant, IOS_MATERIAL, ledger)
    with pytest.raises(ProofAdapterError):
        adapter.verify_material(AuthOperation.sync, IOS_MATERIAL, NativeClaimLedger())
    with pytest.raises(ProofAdapterError):
        DeviceCheckAdapter(APPLE, FakeDeviceCheck(),
                           environment=DeviceCheckEnvironment.development)
    sandbox = AppleCredentials(team_id="TEAM123456", key_id="KEY1",
                               private_key=SecretStr("pem"), production=False)
    DeviceCheckAdapter(sandbox, FakeDeviceCheck(),
                       environment=DeviceCheckEnvironment.development)


# [utest->req~proof-ios-separate-query-update-tokens~1]
def test_the_query_token_is_not_reusable_for_the_update():
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    with pytest.raises(ProofRejected):
        run_ios_claim(adapter, material=IosClaimMaterial(query_token="same", update_token="same"))
    with pytest.raises(ProofRejected):
        run_ios_claim(adapter, material=IosClaimMaterial(query_token=None, update_token="u"))


# [utest->req~proof-ios-tokens-untrusted~1]
# [utest->req~proof-devicecheck-configured-team-id~1]
def test_each_token_goes_only_to_its_own_apple_call_under_the_configured_team_id():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    run_ios_claim(adapter)
    assert transport.queries[0]["query_token"] == "q-token"
    assert transport.updates[0]["update_token"] == "u-token"
    assert transport.queries[0]["team_id"] == APPLE.team_id == adapter.team_id
    assert transport.updates[0]["team_id"] == APPLE.team_id
    with pytest.raises(ProofAdapterError):
        assert_configured_credentials(APPLE, client_supplied_state={"bit0": True})


# [utest->req~proof-devicecheck-bit0-read-semantics~1]
def test_bit0_true_is_claimed_and_false_or_never_set_is_unclaimed():
    ledger = NativeClaimLedger()
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck(bits={"bit0": None, "bit1": None}))
    adapter.verify_material(AuthOperation.claim_anonymous_grant, IOS_MATERIAL, ledger)
    assert adapter.read_claimed(AuthOperation.claim_anonymous_grant, IOS_MATERIAL, ledger) is False
    false_ledger = NativeClaimLedger()
    false_adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck(bits={"bit0": False, "bit1": True}))
    false_adapter.verify_material(AuthOperation.claim_anonymous_grant, IOS_MATERIAL, false_ledger)
    assert false_adapter.read_claimed(AuthOperation.claim_anonymous_grant, IOS_MATERIAL,
                                      false_ledger) is False
    true_ledger = NativeClaimLedger()
    true_adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck(bits={"bit0": True, "bit1": False}))
    true_adapter.verify_material(AuthOperation.claim_anonymous_grant, IOS_MATERIAL, true_ledger)
    assert true_adapter.read_claimed(AuthOperation.claim_anonymous_grant, IOS_MATERIAL,
                                     true_ledger) is True


# [utest->req~proof-devicecheck-bit0-write-before-grant~1]
def test_the_bit0_write_precedes_the_grant_and_leaves_bit1_alone():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    ledger = NativeClaimLedger()
    inserted: list[str] = []

    def insert() -> Any:
        assert transport.updates, "the vendor write precedes the grant insert"
        grant_id = uuid7()
        inserted.append(str(grant_id))
        return grant_id

    native_claim(adapter, AuthOperation.claim_anonymous_grant, IOS_MATERIAL,
                 database_eligibility=lambda: True, insert_grant=insert, ledger=ledger)
    assert "bit1" not in transport.updates[0]["bits"]
    assert ledger.steps == list(NativeClaimStep)
    assert len(inserted) == 1


# [utest->req~proof-devicecheck-bit1-registered-claim~1]
def test_the_registered_claim_writes_bit1_only_and_rejects_missing_material():
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    run_ios_claim(adapter, operation=AuthOperation.claim_registered_grant)
    assert transport.updates[0]["bits"] == {"bit1": True}
    with pytest.raises(ProofRejected) as rejected:
        run_ios_claim(DeviceCheckAdapter(APPLE, FakeDeviceCheck()),
                      operation=AuthOperation.claim_registered_grant,
                      material=IosClaimMaterial(query_token="q", update_token=None))
    assert rejected.value.error_code == "proof_rejected"


# [utest->req~proof-devicecheck-vendor-failure-audit-codes~1]
def test_apple_failures_audit_as_unavailable_or_write_failed_and_create_no_grant():
    for bits in ({"bit1": False}, {"bit0": "yes", "bit1": False}, "malformed"):
        transport = FakeDeviceCheck(bits=bits)  # type: ignore[arg-type]
        with pytest.raises(NativeClaimUnavailable) as unavailable:
            run_ios_claim(DeviceCheckAdapter(APPLE, transport))
        assert unavailable.value.result is AuthEventResult.native_claim_unavailable
        assert unavailable.value.error_code == "verification_temporarily_unavailable"
        assert transport.updates == []
    auth_failure = FakeDeviceCheck(query_error=PermissionError("apple integration auth"))
    with pytest.raises(NativeClaimUnavailable):
        run_ios_claim(DeviceCheckAdapter(APPLE, auth_failure))
    ambiguous = FakeDeviceCheck(acknowledgment={"acknowledged": None})
    with pytest.raises(NativeClaimWriteFailed) as failed:
        run_ios_claim(DeviceCheckAdapter(APPLE, ambiguous))
    assert failed.value.result is AuthEventResult.native_claim_write_failed
    assert failed.value.error_code == "verification_temporarily_unavailable"


# --- The Android proof adapter --------------------------------------------------------------------


# [utest->req~proof-android-play-integrity-role~1]
def test_play_integrity_is_anti_abuse_state_and_never_a_challenge_bound_proof():
    assert play_integrity_role() == "play_integrity_device_recall"
    for role in (ProofUse.identity, ProofUse.ownership, ProofUse.recovery, ProofUse.upgrade,
                 ProofUse.account_resolution):
        with pytest.raises(InvariantError):
            play_integrity_role(role)


# [utest->req~proof-android-verdict-mandatory~1]
def test_a_play_integrity_verdict_is_mandatory_on_every_android_claim():
    transport = FakePlayIntegrity()
    adapter = PlayIntegrityAdapter(GOOGLE, transport)
    for operation in (AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant):
        with pytest.raises(ProofRejected):
            adapter.verify_material(operation, AndroidClaimMaterial(integrity_token=None),
                                    NativeClaimLedger())
    with pytest.raises(ProofAdapterError):
        adapter.verify_material(AuthOperation.sync, ANDROID_MATERIAL, NativeClaimLedger())


# [utest->req~proof-android-release-policy-enumeration~1]
def test_an_unenumerated_release_is_rejected_and_omission_never_picks_no_recall():
    key = ReleaseKey(package_name="com.nativespeaker.app", signing_certificate_digest="AA:BB",
                     release="2026.08.1")
    registry = ReleasePolicyRegistry({key: ReleaseRecallPolicy.device_recall_required})
    assert registry.policy_for(key) is ReleaseRecallPolicy.device_recall_required
    with pytest.raises(ProofRejected):
        registry.policy_for(ReleaseKey(package_name="com.nativespeaker.app",
                                       signing_certificate_digest="AA:BB", release="2026.09.9"))
    with pytest.raises(ProofRejected):
        registry.policy_for(ReleaseKey(package_name="com.other.app",
                                       signing_certificate_digest="AA:BB", release="2026.08.1"))
    assert registered_claim_requires_recall(ReleaseRecallPolicy.device_recall_required) is True
    assert registered_claim_requires_recall(ReleaseRecallPolicy.no_device_recall) is False
    with pytest.raises(ProofRejected):
        registered_claim_requires_recall(ReleaseRecallPolicy.no_device_recall,
                                         client_omitted_material=True)


# [utest->req~proof-android-single-token-untrusted~1]
def test_no_client_supplied_android_assertion_is_a_fact():
    assert_untrusted_client_assertions(["challenge_id"])
    for claimed in ("package_name", "signing_certificate_digest", "verdict_summary",
                    "recall_state", "device_labels", "device_check_state"):
        with pytest.raises(ProofAdapterError):
            assert_untrusted_client_assertions([claimed])


# [utest->req~proof-android-recall-from-decoded-verdict~1]
def test_a_verdict_without_device_recall_is_proof_rejected():
    transport = FakePlayIntegrity(verdict={"appIntegrity": {"verdict": "PLAY_RECOGNIZED"}})
    adapter = PlayIntegrityAdapter(GOOGLE, transport)
    with pytest.raises(ProofRejected) as rejected:
        native_claim(adapter, AuthOperation.claim_anonymous_grant, ANDROID_MATERIAL,
                     database_eligibility=lambda: True, insert_grant=uuid7)
    assert rejected.value.error_code == "proof_rejected"
    assert transport.writes == []
    claimed = FakePlayIntegrity(
        verdict={"deviceRecall": {"anonymous_device_grant_recall": True,
                                  "registered_account_grant_recall": False}})
    with pytest.raises(DeviceGrantExhausted):
        native_claim(PlayIntegrityAdapter(GOOGLE, claimed), AuthOperation.claim_anonymous_grant,
                     ANDROID_MATERIAL, database_eligibility=lambda: True, insert_grant=uuid7)


# [utest->req~proof-android-recall-write-gate~1]
def test_google_must_confirm_the_recall_write_before_any_grant():
    for acknowledgment in ({"confirmed": False}, {}, "ok"):
        transport = FakePlayIntegrity(acknowledgment=acknowledgment)
        with pytest.raises(NativeClaimWriteFailed):
            native_claim(PlayIntegrityAdapter(GOOGLE, transport),
                         AuthOperation.claim_anonymous_grant, ANDROID_MATERIAL,
                         database_eligibility=lambda: True, insert_grant=uuid7)
    timed_out = FakePlayIntegrity(write_error=TimeoutError("google"))
    with pytest.raises(NativeClaimWriteFailed):
        native_claim(PlayIntegrityAdapter(GOOGLE, timed_out), AuthOperation.claim_anonymous_grant,
                     ANDROID_MATERIAL, database_eligibility=lambda: True, insert_grant=uuid7)


# [utest->req~proof-android-gates-no-ios-only-rejection~1]
def test_android_claims_are_supported_and_no_ios_only_rejection_applies():
    for operation in (AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant):
        assert_platform_supported(DevicePlatform.android, operation)
        assert_platform_supported(DevicePlatform.ios, operation)
    with pytest.raises(ProofAdapterError):
        assert_platform_supported(DevicePlatform.web, AuthOperation.claim_anonymous_grant)
    with pytest.raises(ProofAdapterError):
        assert_platform_supported(DevicePlatform.android, AuthOperation.sync)


# --- The web bot-check adapter --------------------------------------------------------------------


# [utest->req~proof-turnstile-siteverify-validation~1]
def test_siteverify_carries_the_server_secret_and_the_resolved_client_address():
    transport = FakeSiteverify()
    config = production_turnstile()
    address = GatewayResolvedAddress(source=AddressSource.envoy_trusted_hop_chain,
                                     address="203.0.113.7")
    outcome = turnstile_siteverify(config, "token", transport, address=address)
    assert transport.calls[0]["secret"] == "0x4AAAAAAAsecret"
    assert transport.calls[0]["remoteip"] == "203.0.113.7"
    assert outcome.hostname == "app.nativespeaker.io"
    unresolved = GatewayResolvedAddress(source=AddressSource.unresolved)
    assert turnstile_remoteip(unresolved) == (None, UNRESOLVED_ADDRESS_KEY)
    assert turnstile_remoteip(None) == (None, UNRESOLVED_ADDRESS_KEY)
    second = FakeSiteverify()
    outcome = turnstile_siteverify(config, "token", second, address=unresolved)
    assert second.calls[0]["remoteip"] is None
    assert outcome.unresolved_address_key == UNRESOLVED_ADDRESS_KEY
    with pytest.raises(TurnstileDenied):
        turnstile_siteverify(config, None, FakeSiteverify(), address=address)


# [utest->req~proof-turnstile-success-and-hostname~1]
def test_only_success_with_an_allow_listed_hostname_passes():
    config = production_turnstile()
    address = GatewayResolvedAddress(source=AddressSource.envoy_direct_downstream,
                                     address="203.0.113.7")
    for payload in ({"success": False, "error-codes": ["invalid-input-response"]},
                    {"success": False, "error-codes": ["timeout-or-duplicate"]},
                    {"success": True, "hostname": "evil.example.org"},
                    {"success": True, "hostname": "sub.app.nativespeaker.io"},
                    {"success": True}):
        with pytest.raises(TurnstileDenied) as denied:
            turnstile_siteverify(config, "token", FakeSiteverify(payload), address=address)
        assert denied.value.error_code == "verification_required"


# [utest->req~proof-turnstile-dependency-failure-fails-closed~1]
def test_a_dependency_failure_fails_closed_and_never_open():
    config = production_turnstile()
    address = GatewayResolvedAddress(source=AddressSource.envoy_direct_downstream,
                                     address="203.0.113.7")
    for transport in (FakeSiteverify(error=TimeoutError("cloudflare")),
                      FakeSiteverify(error=ConnectionError("unreachable")),
                      FakeSiteverify(payload="<html>502</html>"),
                      FakeSiteverify(payload={"hostname": "app.nativespeaker.io"})):
        with pytest.raises(TurnstileUnavailable) as failure:
            turnstile_siteverify(config, "token", transport, address=address)
        assert failure.value.error_code == "verification_temporarily_unavailable"
        assert failure.value.status_code == 503
        assert not isinstance(failure.value, TurnstileDenied)


# [utest->req~proof-turnstile-misconfiguration-class~1]
def test_a_missing_or_invalid_server_secret_is_the_third_failure_class():
    config = production_turnstile()
    address = GatewayResolvedAddress(source=AddressSource.envoy_direct_downstream,
                                     address="203.0.113.7")
    alerts: list[str] = []
    for code in ("missing-input-secret", "invalid-input-secret"):
        transport = FakeSiteverify({"success": False, "error-codes": [code]})
        with pytest.raises(TurnstileMisconfigured) as failure:
            turnstile_siteverify(config, "token", transport, address=address,
                                 alert=alerts.append)
        assert failure.value.error_code == "verification_temporarily_unavailable"
        assert not isinstance(failure.value, TurnstileDenied)
    assert len(alerts) == 2
    with pytest.raises(TurnstileMisconfigured):
        turnstile_siteverify(production_turnstile(secret=SecretStr("")), "token",
                             FakeSiteverify(), address=address)


# [utest->req~proof-turnstile-token-ttl-single-use~1]
def test_the_vendor_ttl_and_one_time_use_are_the_whole_replay_bound():
    assert turnstile_replay_bound() == (300, "timeout-or-duplicate")
    config = production_turnstile()
    address = GatewayResolvedAddress(source=AddressSource.envoy_direct_downstream,
                                     address="203.0.113.7")
    replayed = FakeSiteverify({"success": False, "error-codes": ["timeout-or-duplicate"]})
    with pytest.raises(TurnstileDenied):
        turnstile_siteverify(config, "used-token", replayed, address=address)


# [utest->req~proof-turnstile-action-cdata-not-matched~1]
def test_action_and_cdata_are_never_matched_against_a_pinned_value():
    config = production_turnstile()
    address = GatewayResolvedAddress(source=AddressSource.envoy_direct_downstream,
                                     address="203.0.113.7")
    transport = FakeSiteverify({"success": True, "hostname": "app.nativespeaker.io",
                                "action": "some-other-action", "cdata": "unexpected"})
    outcome = turnstile_siteverify(config, "token", transport, address=address)
    assert outcome.hostname == "app.nativespeaker.io"
    assert_action_cdata_not_matched({"challenge_id": "c-1"})
    with pytest.raises(ProofAdapterError):
        assert_action_cdata_not_matched({"action": "web-grant"})
    with pytest.raises(ProofAdapterError):
        assert_action_cdata_not_matched({"cdata": "pinned"})


# [utest->req~proof-turnstile-per-environment-keys~1]
def test_production_startup_rejects_test_keys_development_secrets_and_hostnames():
    production_turnstile().assert_startup_valid()
    with pytest.raises(TurnstileMisconfigured):
        production_turnstile(sitekey=sorted(TURNSTILE_TEST_SITEKEYS)[0]).assert_startup_valid()
    with pytest.raises(TurnstileMisconfigured):
        production_turnstile(
            secret=SecretStr(sorted(TURNSTILE_TEST_SECRETS)[0])).assert_startup_valid()
    with pytest.raises(TurnstileMisconfigured):
        production_turnstile(hostname_allow_list=("localhost",)).assert_startup_valid()
    with pytest.raises(TurnstileMisconfigured):
        production_turnstile(hostname_allow_list=("app.local",)).assert_startup_valid()
    with pytest.raises(TurnstileMisconfigured):
        production_turnstile(hostname_allow_list=()).assert_startup_valid()
    development = TurnstileConfig(environment=TurnstileEnvironment.development,
                                  sitekey=sorted(TURNSTILE_TEST_SITEKEYS)[0],
                                  secret=SecretStr(sorted(TURNSTILE_TEST_SECRETS)[0]),
                                  hostname_allow_list=("localhost",))
    development.assert_startup_valid()
    assert production_turnstile().hostname_allowed("app.nativespeaker.io") is True
    assert production_turnstile().hostname_allowed("evil.app.nativespeaker.io") is False


# [utest->req~proof-turnstile-siteverify-budget~1]
def test_siteverify_runs_under_its_named_fail_closed_budget():
    exhausted = limiter("1/minute")
    first = consume_siteverify_budget(exhausted, "global", endpoint_admission_passed=True)
    assert first is not None and first.limiter == TURNSTILE_ENTRY and first.allowed
    config = production_turnstile()
    address = GatewayResolvedAddress(source=AddressSource.envoy_direct_downstream,
                                     address="203.0.113.7")
    transport = FakeSiteverify()
    with pytest.raises(TurnstileUnavailable):
        turnstile_siteverify(config, "token", transport, address=address, limiter=exhausted)
    assert transport.calls == []
    with pytest.raises(ProofAdapterError):
        consume_siteverify_budget(limiter(), "global", endpoint_admission_passed=False)


# --- Claim challenge lifetime -----------------------------------------------------------------------


# [utest->req~proof-claim-no-vendor-evidence-age-limit~1]
def test_no_vendor_evidence_age_is_measured_and_only_the_challenge_ttl_bounds_anything():
    assert_no_vendor_evidence_age({"deviceRecall": {}})
    for aged in ({"timestampMillis": 1}, {"devicecheck_generated_at": 1},
                 {"evidence_age_seconds": 5}):
        with pytest.raises(ProofAdapterError):
            assert_no_vendor_evidence_age(aged)
    assert claim_challenge_ttl() == 300
    assert claim_challenge_ttl(AuthOperation.claim_registered_grant) == 300
    assert_completion_unbounded_by_clock(9_000.0, attempts=3)
    with pytest.raises(ProofAdapterError):
        assert_completion_unbounded_by_clock(1.0, attempts=4)


# [utest->req~proof-claim-challenge-mechanics~1]
def test_the_challenge_is_validated_and_claimed_before_any_vendor_call():
    calls: list[str] = []

    def claim() -> ChallengeClaimOutcome:
        calls.append("claim")
        return ChallengeClaimOutcome.claimed

    good = claim_challenge_before_vendor(exists=True, operation_matches=True,
                                         caller_context_matches=True, claim=claim)
    assert good.vendor_calls_allowed and calls == ["claim"]
    missing = claim_challenge_before_vendor(exists=False, operation_matches=True,
                                            caller_context_matches=True, claim=claim)
    assert missing.result is AuthEventResult.challenge_not_found
    assert not missing.vendor_calls_allowed and calls == ["claim"]
    wrong_operation = claim_challenge_before_vendor(exists=True, operation_matches=False,
                                                    caller_context_matches=True, claim=claim)
    assert wrong_operation.result is AuthEventResult.challenge_operation_mismatch
    lost = claim_challenge_before_vendor(
        exists=True, operation_matches=True, caller_context_matches=True,
        claim=lambda: ChallengeClaimOutcome.lost_the_claim)
    assert not lost.vendor_calls_allowed
    with pytest.raises(ProofAdapterError):
        claim_challenge_before_vendor(exists=True, operation_matches=True,
                                      caller_context_matches=True, claim=claim,
                                      vendor_calls_made=1)
    assert consume_claimed_challenge(in_final_transaction=True) == "consumed"
    with pytest.raises(ProofAdapterError):
        consume_claimed_challenge(in_final_transaction=False)
    with pytest.raises(ProofAdapterError):
        consume_claimed_challenge(in_final_transaction=True, deleted=True)
    with pytest.raises(ProofAdapterError):
        consume_claimed_challenge(in_final_transaction=True, returned_to_issued=True)


def test_a_grant_row_needs_the_shared_confirmed_write_guard():
    """The one guard lives in `ratelimit/ordering.py`; the claim path calls it."""
    transport = FakeDeviceCheck(acknowledgment={"acknowledged": True})
    adapter = DeviceCheckAdapter(APPLE, transport)
    outcome, _ = run_ios_claim(adapter)
    assert outcome.write.confirmed
    with pytest.raises(DeviceBitWriteError):
        from nativespeaker.api.ratelimit.ordering import assert_grant_row_permitted
        assert_grant_row_permitted(None)
