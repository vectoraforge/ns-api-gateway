"""Free-credit grants and anti-abuse: the two claim operations and the anonymous claim's rules."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid7

import pytest
from pydantic import SecretStr

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import ClaimOutcome
from nativespeaker.api.auth.derived_identifiers import (
    HmacKey,
    IdpAccountAliasIndex,
    KeyFamily,
    KeyRing,
    WebGateAccount,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import (
    ExternalIdentityRow,
    IdentityState,
    NativeClaimPlatform,
)
from nativespeaker.api.auth.free_grants import (
    ANONYMOUS_CLAIM_STEPS,
    ANONYMOUS_PLATFORM_AUDIT_DETAIL,
    BRANCH_SELECTION_INPUTS,
    BRANCH_VENDOR_GATE,
    CLAIM_FINALIZATION_TABLES,
    DEVICE_RECORD_TABLES,
    ENROLLED_KEY_PARTICIPANTS,
    FREE_GRANT_OPERATIONS,
    GATE_CONSUMPTIONS_UNIQUE_ON,
    LIFETIME_FREE_GRANTS_PER_ACCOUNT,
    NON_ALLOCATING_FLOWS,
    PER_DEVICE_GRANT_STATES,
    PER_KEY_UNIQUENESS_ROWS,
    PERSISTS_ACROSS,
    POSTGRES_NEVER_STORES,
    PROVIDER_ACCOUNTS_UNIQUE_ON,
    RAW_PROVIDER_ACCOUNT_TABLES,
    REGISTERED_IDENTITY_PURPOSES,
    USAGE_STATE_FACTS,
    USAGE_STATE_OWNER,
    AnonymousGrantClaim,
    BranchShapeError,
    ClaimEvidence,
    ClaimStep,
    DeviceGrantState,
    FreeGrantError,
    FreeGrantRejected,
    android_anonymous_path_available,
    android_gate,
    anonymous_claim_source,
    anonymous_platform_detail,
    assert_branch_verified,
    assert_claimant_eligible,
    assert_database_bounds,
    assert_device_check_is_anti_abuse_only,
    assert_device_states_persist,
    assert_free_credit_source_operation,
    assert_no_claim_finalization_table,
    assert_no_enrolled_key,
    assert_no_free_credit_allocation,
    assert_no_gate_bypass,
    assert_no_general_device_records,
    assert_no_installation_ids,
    assert_no_raw_attestation_tokens,
    assert_no_raw_cloudflare_tokens,
    assert_no_raw_device_ids,
    assert_postgres_does_not_store,
    assert_provider_account_id_store,
    assert_vendor_state_not_client_supplied,
    assert_write_material_present,
    claim_admission_pair,
    claim_identity,
    consume_free_grant_gate,
    device_grant_exhausted,
    device_states_for,
    free_grant_anti_abuse_row,
    free_grant_operation,
    free_grant_usage_row,
    further_free_credit_path,
    gate_recorded_by,
    ios_gate_bits,
    native_eligible,
    non_accusatory_copy,
    pin_native_platform,
    platform_gate,
    read_web_gate,
    registered_account_blocked,
    registered_backstop,
    registered_claim_plan,
    registered_eligibility_inputs,
    registered_identity_is_not_a_free_path,
    select_branch,
    validate_grant_source,
    web_eligible,
    web_hash_provider_component,
)
from nativespeaker.api.auth.invariants import (
    DevicePlatform,
    GateAlreadyConsumedError,
    GateConsumptionKind,
    InvariantError,
    ProofUse,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.locks import LockingPath, LockLedger
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_adapters import (
    AndroidClaimMaterial,
    AppleCredentials,
    ClaimRejection,
    DeviceCheckAdapter,
    DeviceGrantExhausted,
    ExecutionContext,
    GoogleCredentials,
    IosClaimMaterial,
    NativeClaimLedger,
    NativeClaimWriteFailed,
    PlayIntegrityAdapter,
    ProofAdapterError,
    ProofRejected,
    ReleaseKey,
    ReleasePolicyRegistry,
    ReleaseRecallPolicy,
)
from nativespeaker.api.auth.proof_endpoints import ClaimBranch, GateDenied, ProofArtifact
from nativespeaker.api.quota.grants import (
    GrantRow,
    TooManyActiveGrantsError,
    select_effective_grant,
)
from nativespeaker.api.ratelimit.ordering import (
    ANONYMOUS_GRANT_ADMISSION,
    DeviceBitCall,
    DeviceBitWrite,
    DeviceBitWriteError,
)

MIGRATION = (Path(__file__).resolve().parents[2] / "migrations"
             / "20260816_01_auth-refactor-schema.sql")
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
APPLE = AppleCredentials(team_id="TEAM123456", key_id="KEY1", private_key=SecretStr("pem"))
GOOGLE = GoogleCredentials(package_name="com.nativespeaker.app",
                           service_account_email="svc@example.iam.gserviceaccount.com",
                           private_key=SecretStr("pem"))
IOS_MATERIAL = IosClaimMaterial(query_token="q-token", update_token="u-token")
ANDROID_MATERIAL = AndroidClaimMaterial(integrity_token="integrity-token")
ENUMERATED_RELEASE = ReleaseKey(package_name="com.nativespeaker.app",
                                signing_certificate_digest="sha256:abcdef",
                                release="1.4.0")
APP_INTEGRITY = {"packageName": ENUMERATED_RELEASE.package_name,
                 "certificateSha256Digest": [ENUMERATED_RELEASE.signing_certificate_digest],
                 "release": ENUMERATED_RELEASE.release}
RECALL_POLICY = ReleasePolicyRegistry({ENUMERATED_RELEASE:
                                       ReleaseRecallPolicy.device_recall_required})
IOS_EVIDENCE = ClaimEvidence(devicecheck_query_token="q-token", devicecheck_update_token="u-token")
ANDROID_EVIDENCE = ClaimEvidence(play_integrity_token="integrity-token")
WEB_EVIDENCE = ClaimEvidence(turnstile_token="cf-token")
GOOGLE_PROVIDER_DATA: list[Any] = [{"providerId": "google.com", "uid": "google-account-1"}]
FREE_TIER = "free_anonymous"


# --- fixtures and doubles -----------------------------------------------------------------------


def identity_row(*,
                 provider: IdentityProvider = IdentityProvider.anonymous,
                 provider_uid: str | None = None,
                 native_claim_platform: NativeClaimPlatform | None = None,
                 identity_state: IdentityState = IdentityState.active,
                 row_id: UUID | None = None,
                 user_id: UUID | None = None) -> ExternalIdentityRow:
    return ExternalIdentityRow(id=row_id or uuid7(), user_id=user_id or uuid7(),
                               issuer="https://securetoken.google.com/test-project",
                               subject="firebase-subject",
                               provider=provider, provider_uid=provider_uid,
                               identity_state=identity_state,
                               native_claim_platform=native_claim_platform)


def google_row(**overrides: Any) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.google,
                              "provider_uid": "google-account-1"}
    fields.update(overrides)
    return identity_row(**fields)


def context_for(row: ExternalIdentityRow,
                outcome: ResolutionOutcome = ResolutionOutcome.linked) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=row.issuer, subject=row.subject, outcome=outcome,
                                   user_id=row.user_id, external_identity_id=row.id,
                                   provider=row.provider)


def alias_index() -> IdpAccountAliasIndex:
    ring = KeyRing(KeyFamily.k_idp_account, current=HmacKey(version=1, secret=b"i" * 32))
    return IdpAccountAliasIndex(ProviderAccountGates(), ring)


class FakeChallenge:
    """The two atomic conditional updates, as this claim sees them."""

    def __init__(self, outcome: ClaimOutcome = ClaimOutcome.claimed, consumed: bool = True):
        self.outcome = outcome
        self.consumed = consumed
        self.claims = 0
        self.consumes = 0

    def claim(self) -> ClaimOutcome:
        self.claims += 1
        return self.outcome

    def consume(self) -> bool:
        self.consumes += 1
        return self.consumed


class FakeDeviceCheck:
    def __init__(self, *, bits: dict[str, Any] | None = None,
                 acknowledgment: Any = None):
        self.bits = {"bit0": False, "bit1": False} if bits is None else bits
        self.acknowledgment = {"acknowledged": True} if acknowledgment is None else acknowledgment
        self.queries: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    def query_two_bits(self, *, query_token: str, team_id: str, environment: Any) -> Any:
        self.queries.append({"query_token": query_token, "team_id": team_id})
        return self.bits

    def update_two_bits(self, *, update_token: str, team_id: str, environment: Any,
                        bits: Any) -> Any:
        self.updates.append({"update_token": update_token, "bits": dict(bits)})
        return self.acknowledgment


class FakePlayIntegrity:
    def __init__(self, *, verdict: Any = None, acknowledgment: Any = None):
        self.verdict = ({"appIntegrity": APP_INTEGRITY,
                         "deviceRecall": {"anonymous_device_grant_recall": False,
                                          "registered_account_grant_recall": False}}
                        if verdict is None else verdict)
        self.acknowledgment = {"confirmed": True} if acknowledgment is None else acknowledgment
        self.decodes: list[str] = []
        self.writes: list[dict[str, Any]] = []

    def decode_verdict(self, *, integrity_token: str, credentials: Any) -> Any:
        self.decodes.append(integrity_token)
        return self.verdict

    def write_recall(self, *, integrity_token: str, credentials: Any, state: Any,
                     value: bool) -> Any:
        self.writes.append({"state": state, "value": value})
        return self.acknowledgment


def run_native_claim(adapter: Any,
                     material: Any,
                     evidence: ClaimEvidence,
                     verified: tuple[str, ...],
                     *,
                     row: ExternalIdentityRow | None = None,
                     committed: tuple[AccessGrantSource, ...] = (),
                     challenge: FakeChallenge | None = None) -> tuple[AnonymousGrantClaim, Any]:
    row = row if row is not None else identity_row()
    challenge = challenge or FakeChallenge()
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(challenge)
    claim.resolve_identity(context_for(row), row)
    claim.select_branch(evidence, row, verified=verified)
    ledger = NativeClaimLedger()
    claim.read_platform_gate(native=(adapter, material, ledger))
    claim.check_database_eligibility(committed_free_sources=committed, ledger=ledger)
    write = claim.write_native_bit(adapter, material, ledger=ledger)
    transaction = object()
    activated = claim.activate(user_id=row.user_id, grant_id=uuid7(), tier_id=FREE_TIER,
                               transaction=transaction,
                               locks=LockLedger(LockingPath.claim_anonymous_grant_completion),
                               reconfirm=lambda: True, challenge=challenge, write=write, now=NOW)
    return claim, activated


def run_web_claim(*,
                  row: ExternalIdentityRow | None = None,
                  index: IdpAccountAliasIndex | None = None,
                  provider_data: list[Any] | None = None,
                  bot_check: bool = True,
                  committed: tuple[AccessGrantSource, ...] = (),
                  challenge: FakeChallenge | None = None) -> tuple[AnonymousGrantClaim, Any]:
    row = row if row is not None else google_row()
    index = index if index is not None else alias_index()
    challenge = challenge or FakeChallenge()
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(challenge)
    claim.resolve_identity(context_for(row), row)
    claim.select_branch(WEB_EVIDENCE, row, verified=("hostname", "action"))
    reading = claim.read_platform_gate(
        web=(row, lambda: bot_check,
             provider_data if provider_data is not None else GOOGLE_PROVIDER_DATA),
        index=index)
    claim.check_database_eligibility(committed_free_sources=committed)
    transaction = object()
    activated = claim.activate(user_id=row.user_id, grant_id=uuid7(), tier_id=FREE_TIER,
                               transaction=transaction,
                               locks=LockLedger(LockingPath.claim_anonymous_grant_completion),
                               reconfirm=lambda: True, challenge=challenge,
                               web_account=reading.web_account, index=index, now=NOW)
    return claim, activated


def migration_sql() -> str:
    return MIGRATION.read_text()


def migration_tables() -> set[str]:
    return set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?([\w.]+)", migration_sql()))


def migration_columns() -> set[str]:
    body = "\n".join(line for line in migration_sql().splitlines()
                     if not line.strip().startswith("--"))
    return {match.lower() for match in re.findall(r"^\s{4}(\w+)\s", body, flags=re.MULTILINE)}


# --- Access grants own monthly usage state -------------------------------------------------------


# [utest->req~grants-usage-state-owned-by-quota-spec~1]
def test_a_free_grant_is_an_ordinary_grant_with_per_grant_usage_and_one_active_bound():
    assert USAGE_STATE_OWNER == "07-quota-and-access-enforcement.md"
    assert any("per-grant" in fact for fact in USAGE_STATE_FACTS)
    transaction = object()
    grant_id = uuid7()
    usage = free_grant_usage_row(grant_id, transaction=transaction, now=NOW)
    # The usage row is keyed by the grant, not by the user, and starts the month at zero.
    assert usage.grant_id == grant_id
    assert (usage.monthly_period, usage.monthly_used) == ("2026-08", 0)
    # The row initializes usage state only: no allowance and no entitlement field on it.
    assert set(type(usage).__dataclass_fields__) == {"grant_id", "monthly_period", "monthly_used"}
    # The one-active-grant bound applies to free grants exactly as to every other source.
    user_id = uuid7()
    rows = [GrantRow(grant_id=uuid7(), user_id=user_id, tier_id=FREE_TIER,
                     source=source, status=AccessGrantStatus.active, starts_at=NOW)
            for source in (AccessGrantSource.anonymous_device_grant,
                           AccessGrantSource.registered_account_grant)]
    with pytest.raises(TooManyActiveGrantsError):
        select_effective_grant(rows, NOW)


# --- The two free-credit grant operations --------------------------------------------------------


# [utest->req~grants-only-two-grant-operations~1]
def test_free_credit_is_granted_only_through_the_two_claim_operations():
    assert FREE_GRANT_OPERATIONS == {
        AccessGrantSource.anonymous_device_grant: AuthOperation.claim_anonymous_grant,
        AccessGrantSource.registered_account_grant: AuthOperation.claim_registered_grant,
    }
    assert (free_grant_operation(AccessGrantSource.anonymous_device_grant)
            is AuthOperation.claim_anonymous_grant)
    with pytest.raises(FreeGrantError):
        free_grant_operation(AccessGrantSource.subscription)
    with pytest.raises(FreeGrantError):
        assert_free_credit_source_operation(AuthOperation.create_user,
                                            AccessGrantSource.anonymous_device_grant)
    with pytest.raises(FreeGrantError):
        # Neither claim creates the other's source.
        assert_free_credit_source_operation(AuthOperation.claim_anonymous_grant,
                                            AccessGrantSource.registered_account_grant)


# [utest->req~grants-never-allocated-at-creation-or-sync~1]
def test_no_creation_sync_restore_or_upgrade_flow_allocates_free_credit():
    for operation in (AuthOperation.create_user, AuthOperation.sync,
                      AuthOperation.restore_subscription,
                      AuthOperation.upgrade_anonymous_to_registered,
                      AuthOperation.sign_out_all):
        assert operation in NON_ALLOCATING_FLOWS
        with pytest.raises(FreeGrantError):
            assert_no_free_credit_allocation(operation)
    assert_no_free_credit_allocation(AuthOperation.claim_anonymous_grant)
    assert_no_free_credit_allocation(AuthOperation.claim_registered_grant)


# [utest->req~grants-claim-anonymous-operation~1]
def test_every_branch_produces_one_anonymous_device_grant_for_its_allowed_claimant():
    for branch in ClaimBranch:
        assert anonymous_claim_source(branch) is AccessGrantSource.anonymous_device_grant
    assert set(BRANCH_VENDOR_GATE) == set(ClaimBranch)
    anonymous = identity_row()
    registered = google_row()
    # Native: an active anonymous identity, or an active registered google/apple identity.
    assert assert_claimant_eligible(ClaimBranch.native_ios, anonymous) is IdentityProvider.anonymous
    assert assert_claimant_eligible(ClaimBranch.native_android, registered) is IdentityProvider.google
    # Web: a registered claimant only.
    assert assert_claimant_eligible(ClaimBranch.web, registered) is IdentityProvider.google
    with pytest.raises(FreeGrantRejected):
        assert_claimant_eligible(ClaimBranch.web, anonymous)
    with pytest.raises(FreeGrantRejected):
        assert_claimant_eligible(ClaimBranch.native_ios,
                                 identity_row(identity_state=IdentityState.historical))


# [utest->req~grants-claim-registered-operation~1]
def test_the_registered_claim_supersedes_an_anonymous_grant_and_always_confirms():
    row = google_row()
    plan = registered_claim_plan(row, active_grant_source=AccessGrantSource.anonymous_device_grant,
                                 provider_data_confirmed=True)
    assert plan.source is AccessGrantSource.registered_account_grant
    assert plan.gate_kind is GateConsumptionKind.registered_account_grant
    assert plan.supersedes_anonymous_grant is True
    assert registered_claim_plan(row, active_grant_source=None,
                                 provider_data_confirmed=True).supersedes_anonymous_grant is False
    with pytest.raises(FreeGrantError):
        # Every call performs the mandatory fail-closed confirmation, the repeat included.
        registered_claim_plan(row, active_grant_source=None, provider_data_confirmed=False)
    with pytest.raises(FreeGrantRejected):
        registered_claim_plan(identity_row(), active_grant_source=None,
                              provider_data_confirmed=True)
    with pytest.raises(FreeGrantRejected):
        registered_claim_plan(row, active_grant_source=AccessGrantSource.subscription,
                              provider_data_confirmed=True)


# [utest->req~grants-android-device-recall-availability~1]
def test_android_without_device_recall_has_no_anonymous_device_check_path():
    assert android_anonymous_path_available(device_recall_available=True) is True
    assert android_anonymous_path_available(device_recall_available=False) is False
    assert android_gate(device_recall_available=True)[0] == "verify_play_integrity"
    # No anonymous path at all: the claim falls back to the registered account grant.
    assert android_gate(device_recall_available=False) is AuthOperation.claim_registered_grant


# [utest->req~grants-two-per-device-grant-states~1]
def test_two_per_device_states_and_the_non_accusatory_exhausted_copy():
    assert PER_DEVICE_GRANT_STATES == (DeviceGrantState.anonymous_claimed,
                                       DeviceGrantState.registered_claimed)
    assert device_states_for(DevicePlatform.ios) == PER_DEVICE_GRANT_STATES
    assert device_states_for(DevicePlatform.android) == PER_DEVICE_GRANT_STATES
    # Web has no durable device-check state at all.
    assert device_states_for(DevicePlatform.web) == ()
    with pytest.raises(DeviceGrantExhausted) as exhausted:
        device_grant_exhausted(anonymous_claimed=True, registered_claimed=True)
    assert exhausted.value.error_code == "device_grant_exhausted"
    assert exhausted.value.result is AuthEventResult.native_claim_already_claimed
    assert non_accusatory_copy() in str(exhausted.value)
    assert "abuse" not in non_accusatory_copy().lower()
    device_grant_exhausted()


# [utest->req~grants-grant-ordering-two-ledgers~2]
def test_the_web_ordering_runs_admission_gate_eligibility_then_activation():
    claim, activated = run_web_claim()
    assert claim.steps == [ClaimStep.admission, ClaimStep.challenge_claim,
                           ClaimStep.identity_barrier, ClaimStep.branch_selection,
                           ClaimStep.platform_gate, ClaimStep.database_eligibility,
                           ClaimStep.activation]
    assert activated.alias is not None
    assert activated.alias.key_version == 1
    # No step may run out of that order: the gate cannot be read before the branch is selected.
    out_of_order = AnonymousGrantClaim()
    out_of_order.admit(pre_consumption_passed=True, handler_admission_passed=True)
    out_of_order.claim_challenge(FakeChallenge())
    with pytest.raises(FreeGrantError):
        out_of_order.read_platform_gate(web=(google_row(), lambda: True, GOOGLE_PROVIDER_DATA))


# [utest->req~grants-anonymous-exhausted-registered-backstop~1]
def test_the_registered_grant_is_the_backstop_once_the_anonymous_gate_is_closed():
    with pytest.raises(ClaimRejection) as conflict:
        device_grant_exhausted(web_gate_consumed=True)
    assert conflict.value.error_code == "device_grant_exhausted"
    assert conflict.value.result is AuthEventResult.anti_abuse_already_claimed
    row = google_row()
    assert (registered_backstop(row, active_grant_source=None)
            is AuthOperation.claim_registered_grant)
    assert (registered_backstop(row,
                                active_grant_source=AccessGrantSource.anonymous_device_grant)
            is AuthOperation.claim_registered_grant)
    with pytest.raises(FreeGrantRejected):
        # It requires a Google or Apple linked identity.
        registered_backstop(identity_row(), active_grant_source=None)
    with pytest.raises(FreeGrantRejected):
        # And no active grant other than a convertible anonymous device grant.
        registered_backstop(row, active_grant_source=AccessGrantSource.subscription)


# [utest->req~grants-registered-rejection-final~1]
def test_a_durable_registered_rejection_closes_every_remaining_free_path():
    for result in (AuthEventResult.idp_account_not_eligible,
                   AuthEventResult.idp_account_already_claimed,
                   AuthEventResult.policy_rejected):
        assert further_free_credit_path(result) is None
    assert (further_free_credit_path(AuthEventResult.native_claim_unavailable)
            is AuthOperation.claim_registered_grant)
    # The duplicate block is keyed by the provider account, so it holds for every other
    # Firebase user, identity, internal user, reinstall and device.
    gates = ProviderAccountGates()
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid="google-account-1")
    assert registered_account_blocked(gates, account) is False
    gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())
    assert registered_account_blocked(gates, account) is True
    with pytest.raises(GateAlreadyConsumedError):
        gates.consume(account, GateConsumptionKind.registered_account_grant, uuid7())


# [utest->req~grants-registered-identity-not-a-free-path~1]
def test_a_registered_identity_alone_is_not_a_free_credit_path():
    assert "free_credit_grant" not in REGISTERED_IDENTITY_PURPOSES
    row = google_row()
    registered_identity_is_not_a_free_path(row, anti_abuse_evidence_present=True)
    with pytest.raises(FreeGrantRejected):
        registered_identity_is_not_a_free_path(row, anti_abuse_evidence_present=False)
    with pytest.raises(FreeGrantRejected):
        registered_identity_is_not_a_free_path(identity_row(), anti_abuse_evidence_present=True)


# [utest->req~grants-anti-abuse-table-separate~1]
def test_anti_abuse_fields_live_on_their_own_row_keyed_by_grant_id():
    grant_id = uuid7()
    native = free_grant_anti_abuse_row(grant_id=grant_id,
                                       source=AccessGrantSource.anonymous_device_grant,
                                       platform=DevicePlatform.ios, created_at=NOW)
    assert native["grant_id"] == grant_id
    assert native["native_claim_provider"] is NativeClaimPlatform.ios_devicecheck
    assert native["idp_account_hash"] is None
    web = free_grant_anti_abuse_row(grant_id=uuid7(),
                                    source=AccessGrantSource.anonymous_device_grant,
                                    idp_account_hash=b"h" * 32, idp_account_hash_key_version=1,
                                    created_at=NOW)
    assert web["idp_account_hash"] == b"h" * 32 and web["idp_account_hash_key_version"] == 1
    registered = free_grant_anti_abuse_row(grant_id=uuid7(),
                                           source=AccessGrantSource.registered_account_grant,
                                           idp_account_hash=b"h" * 32,
                                           idp_account_hash_key_version=1, created_at=NOW)
    assert registered["native_claim_provider"] is None
    # The entitlement row's own column shape never varies per source.
    with pytest.raises(InvariantError):
        free_grant_anti_abuse_row(grant_id=uuid7(),
                                  source=AccessGrantSource.anonymous_device_grant,
                                  platform=DevicePlatform.ios,
                                  grant_columns=("id", "source", "device_check_state"))
    with pytest.raises(FreeGrantError):
        free_grant_anti_abuse_row(grant_id=uuid7(), source=AccessGrantSource.subscription)


# [utest->req~grants-gate-uniqueness-on-stable-uid~1]
def test_gate_uniqueness_is_enforced_on_the_stable_uid_and_written_with_its_grant():
    assert PROVIDER_ACCOUNTS_UNIQUE_ON == ("provider", "provider_uid")
    assert GATE_CONSUMPTIONS_UNIQUE_ON == ("provider_account_id", "consumption_kind")
    index = alias_index()
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid="google-account-1")
    transaction = object()
    alias = consume_free_grant_gate(index, account, GateConsumptionKind.web_anonymous_gate,
                                    uuid7(), transaction=transaction,
                                    grant_transaction=transaction)
    assert alias.key_version == 1
    # A second consumption of the same gate conflicts on the gate-consumption insert.
    with pytest.raises(GateAlreadyConsumedError):
        consume_free_grant_gate(index, account, GateConsumptionKind.web_anonymous_gate, uuid7(),
                                transaction=transaction, grant_transaction=transaction)
    # The two kinds are distinct rows, and the row is written with its grant.
    consume_free_grant_gate(index, account, GateConsumptionKind.registered_account_grant, uuid7(),
                            transaction=transaction, grant_transaction=transaction)
    with pytest.raises(FreeGrantError):
        consume_free_grant_gate(index,
                                ProviderAccount(provider=IdentityProvider.apple,
                                                provider_uid="apple-account-1"),
                                GateConsumptionKind.web_anonymous_gate, uuid7(),
                                transaction=object(), grant_transaction=object())


# [utest->req~grants-source-enumeration-closed~1]
def test_the_grant_source_enumeration_is_closed_and_never_encodes_platform():
    assert {str(source) for source in AccessGrantSource} == {
        "anonymous_device_grant", "registered_account_grant", "subscription", "manual"}
    assert validate_grant_source("manual") is AccessGrantSource.manual
    for rejected in ("promo", "introductory", "future_reserved", ""):
        with pytest.raises(FreeGrantError):
            validate_grant_source(rejected)
    # Platform detail travels in audit detail; the canonical source is the same on all branches.
    sources = {anonymous_platform_detail(branch)[0] for branch in ClaimBranch}
    assert sources == {AccessGrantSource.anonymous_device_grant}
    assert len(set(ANONYMOUS_PLATFORM_AUDIT_DETAIL.values())) == 3
    assert anonymous_platform_detail(ClaimBranch.web)[1] == "web_signin_plus_cloudflare_bot_check"


# --- What the schema does and does not store ------------------------------------------------------


# [utest->req~grants-postgres-does-not-store~1]
def test_the_shipped_schema_stores_none_of_the_seven_families():
    assert len(POSTGRES_NEVER_STORES) == 7
    assert_postgres_does_not_store(tables=migration_tables(), columns=migration_columns())
    with pytest.raises(FreeGrantError):
        assert_postgres_does_not_store(columns=("id", "device_id"))


# [utest->req~grants-no-raw-device-ids~1]
def test_no_raw_device_id_is_stored():
    assert_no_raw_device_ids(migration_columns())
    for column in ("device_id", "vendor_identifier", "android_id"):
        with pytest.raises(FreeGrantError):
            assert_no_raw_device_ids(("grant_id", column))


# [utest->req~grants-no-installation-ids~1]
def test_no_installation_id_is_stored():
    assert_no_installation_ids(migration_columns())
    for column in ("installation_id", "firebase_installation_id", "app_instance_id"):
        with pytest.raises(FreeGrantError):
            assert_no_installation_ids(("grant_id", column))


# [utest->req~grants-no-general-device-records~1]
def test_no_general_device_record_table_exists():
    assert DEVICE_RECORD_TABLES == frozenset()
    assert_no_general_device_records(migration_tables(), migration_columns())
    assert not any("device" in table for table in migration_tables())
    with pytest.raises(FreeGrantError):
        assert_no_general_device_records(("core.users", "core.devices"))
    for column in ("device_principal", "stable_device_principal_hash", "device_check_state"):
        with pytest.raises(FreeGrantError):
            assert_no_general_device_records((), ("grant_id", column))


# [utest->req~grants-no-raw-attestation-tokens~1]
def test_no_raw_devicecheck_or_play_integrity_token_is_stored():
    assert_no_raw_attestation_tokens(migration_columns())
    for column in ("devicecheck_token", "play_integrity_token", "attestation_token"):
        with pytest.raises(FreeGrantError):
            assert_no_raw_attestation_tokens(("grant_id", column))


# [utest->req~grants-no-raw-cloudflare-tokens~1]
def test_no_raw_cloudflare_bot_check_token_is_stored():
    assert_no_raw_cloudflare_tokens(migration_columns())
    for column in ("turnstile_token", "bot_check_token", "cf_turnstile_response"):
        with pytest.raises(FreeGrantError):
            assert_no_raw_cloudflare_tokens(("grant_id", column))


# [utest->req~grants-no-raw-provider-ids-outside-registry~1]
def test_a_raw_provider_account_id_lives_only_in_the_identity_row_and_the_registry():
    assert RAW_PROVIDER_ACCOUNT_TABLES == {"core.external_identities", "core.provider_accounts"}
    for table in RAW_PROVIDER_ACCOUNT_TABLES:
        assert assert_provider_account_id_store(table) == table
    for table in ("core.access_grants_anti_abuse", "audit.auth_events", "core.users"):
        with pytest.raises(FreeGrantError):
            assert_provider_account_id_store(table)
    # And the shipped schema keeps `provider_uid` in exactly those two tables.
    holders = {table for table, body in re.findall(r"CREATE TABLE ([\w.]+) \((.*?)\n\);",
                                                   migration_sql(), flags=re.S)
               if re.search(r"^\s+provider_uid\s", body, flags=re.M)}
    assert holders == set(RAW_PROVIDER_ACCOUNT_TABLES)


# [utest->req~grants-no-claim-finalization-table~1]
def test_no_separate_claim_finalization_table_exists():
    assert CLAIM_FINALIZATION_TABLES == frozenset()
    assert_no_claim_finalization_table(migration_tables())
    assert not any("claim" in table for table in migration_tables())
    with pytest.raises(FreeGrantError):
        assert_no_claim_finalization_table(("core.access_grants", "core.free_grant_claims"))


# --- Eligibility ----------------------------------------------------------------------------------


# [utest->req~grants-native-eligibility-both-ledgers~1]
def test_native_eligibility_needs_both_ledgers_and_web_needs_the_whole_gate():
    assert native_eligible(vendor_bit_set=False, database_eligible=True) is True
    assert native_eligible(vendor_bit_set=True, database_eligible=True) is False
    assert native_eligible(vendor_bit_set=False, database_eligible=False) is False
    assert web_eligible(stored_provider=IdentityProvider.google, classifier_passed=True,
                        provider_uid_matched=True, bot_check_passed=True) is True
    # Each half of the web gate is load-bearing on its own.
    assert web_eligible(stored_provider=IdentityProvider.google, classifier_passed=False,
                        provider_uid_matched=True, bot_check_passed=True) is False
    assert web_eligible(stored_provider=IdentityProvider.google, classifier_passed=True,
                        provider_uid_matched=False, bot_check_passed=True) is False
    assert web_eligible(stored_provider=IdentityProvider.google, classifier_passed=True,
                        provider_uid_matched=True, bot_check_passed=False) is False
    assert web_eligible(stored_provider=IdentityProvider.anonymous, classifier_passed=True,
                        provider_uid_matched=True, bot_check_passed=True) is False
    with pytest.raises(FreeGrantError):
        web_eligible(stored_provider=IdentityProvider.google, classifier_passed=True,
                     provider_uid_matched=True, bot_check_passed=True,
                     persisted_device_state=("web_device_bit",))


# [utest->req~grants-registered-eligibility-inputs~1]
def test_registered_eligibility_reads_stored_state_and_never_registered_at():
    row = google_row()
    assert registered_eligibility_inputs(row, provider_data_confirmed=True) == (
        IdentityProvider.google, "google-account-1")
    with pytest.raises(FreeGrantError):
        registered_eligibility_inputs(row, provider_data_confirmed=True,
                                      consulted=("registered_at",))
    with pytest.raises(FreeGrantError):
        registered_eligibility_inputs(row, provider_data_confirmed=True,
                                      consulted=("client_supplied_provider_account_id",))
    # A row with no stored provider_uid rejects as idp_account_not_eligible.
    with pytest.raises(FreeGrantRejected) as rejected:
        registered_eligibility_inputs(identity_row(), provider_data_confirmed=True)
    assert rejected.value.result is AuthEventResult.idp_account_not_eligible
    with pytest.raises(FreeGrantRejected):
        registered_eligibility_inputs(row, provider_data_confirmed=False)


# [utest->req~grants-device-check-not-identity~1]
def test_the_device_check_signal_is_anti_abuse_state_and_nothing_else():
    assert (assert_device_check_is_anti_abuse_only(ProofUse.anti_abuse_gate)
            is ProofUse.anti_abuse_gate)
    for use in (ProofUse.identity, ProofUse.ownership, ProofUse.recovery, ProofUse.upgrade,
                ProofUse.account_resolution):
        with pytest.raises(InvariantError):
            assert_device_check_is_anti_abuse_only(use)
    with pytest.raises(FreeGrantError):
        assert_device_check_is_anti_abuse_only(ProofUse.anti_abuse_gate,
                                               resolves_account="user-1")
    with pytest.raises(FreeGrantError):
        assert_device_check_is_anti_abuse_only(ProofUse.anti_abuse_gate,
                                               recovers=("chats", "subscriptions"))


# --- The anti-abuse layers ------------------------------------------------------------------------


# [utest->req~grants-no-degraded-verification-mode~1]
def test_there_is_no_degraded_verification_mode_on_any_branch():
    for branch in ClaimBranch:
        assert platform_gate(branch)[-1] == "activate_grant"
        assert len(platform_gate(branch)) >= 5
    with pytest.raises(FreeGrantError):
        platform_gate("cached_positive")  # type: ignore[arg-type]
    # Omitting or substituting any step of the gate is refused.
    with pytest.raises(FreeGrantError):
        assert_no_gate_bypass(ClaimBranch.web, completed=platform_gate(ClaimBranch.web)[:-1])


# [utest->req~grants-platform-gate-ios~1]
def test_the_ios_gate_reads_the_bit_checks_eligibility_then_writes_before_activating():
    assert platform_gate(ClaimBranch.native_ios) == (
        "verify_devicecheck_proof", "read_anonymous_claimed_bit", "database_per_user_eligibility",
        "write_bit_and_await_apple_confirmation", "activate_grant")
    anonymous_bit, registered_bit = ios_gate_bits()
    assert anonymous_bit == "bit0" and registered_bit == "bit1"
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    claim, activated = run_native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE,
                                        ("apple_team_id", "devicecheck_environment"))
    # The read happened before the write, and the write before the grant row.
    assert transport.queries and transport.updates
    assert transport.updates[0]["bits"] == {"bit0": True}
    assert activated.grant["source"] is AccessGrantSource.anonymous_device_grant
    # An already-set bit exhausts the device and writes nothing.
    claimed = FakeDeviceCheck(bits={"bit0": True, "bit1": False})
    with pytest.raises(DeviceGrantExhausted):
        run_native_claim(DeviceCheckAdapter(APPLE, claimed), IOS_MATERIAL, IOS_EVIDENCE,
                         ("apple_team_id", "devicecheck_environment"))
    assert claimed.updates == []


# [utest->req~grants-platform-gate-android~1]
def test_the_android_gate_reads_recall_then_writes_and_awaits_googles_confirmation():
    assert platform_gate(ClaimBranch.native_android)[1] == "read_device_recall_anonymous_claimed"
    transport = FakePlayIntegrity()
    adapter = PlayIntegrityAdapter(GOOGLE, transport, release_policy=RECALL_POLICY)
    claim, activated = run_native_claim(adapter, ANDROID_MATERIAL, ANDROID_EVIDENCE,
                                        ("package_name", "signing_certificate_digest"))
    assert transport.decodes and transport.writes[0]["value"] is True
    assert activated.anti_abuse["native_claim_provider"] is NativeClaimPlatform.android_play_integrity
    # An unconfirmed recall write creates no grant.
    unconfirmed = FakePlayIntegrity(acknowledgment={"confirmed": False})
    with pytest.raises(NativeClaimWriteFailed):
        run_native_claim(PlayIntegrityAdapter(GOOGLE, unconfirmed, release_policy=RECALL_POLICY),
                         ANDROID_MATERIAL, ANDROID_EVIDENCE,
                         ("package_name", "signing_certificate_digest"))


# [utest->req~grants-platform-gate-web~1]
def test_the_web_gate_classifies_matches_and_derives_with_the_stored_provider():
    row = google_row()
    account, alias = read_web_gate(row, bot_check=lambda: True,
                                   provider_data=GOOGLE_PROVIDER_DATA, index=alias_index())
    assert account.provider is IdentityProvider.google
    assert account.canonical_provider_account_id == "google-account-1"
    assert alias is not None and alias.key_version == 1
    assert web_hash_provider_component(row, account) is row.provider
    # A bot check that does not pass denies the grant before the classifier runs.
    with pytest.raises(GateDenied):
        read_web_gate(row, bot_check=lambda: False, provider_data=GOOGLE_PROVIDER_DATA)
    # A live record whose uid does not equal the stored provider_uid is denied.
    with pytest.raises(GateDenied):
        read_web_gate(row, bot_check=lambda: True,
                      provider_data=[{"providerId": "google.com", "uid": "someone-else"}])
    # And so is a shape the closed classifier rejects.
    with pytest.raises(GateDenied):
        read_web_gate(row, bot_check=lambda: True,
                      provider_data=[{"providerId": "google.com", "uid": "google-account-1"},
                                     {"providerId": "apple.com", "uid": "apple-1"}])
    with pytest.raises(GateDenied):
        web_hash_provider_component(
            row, WebGateAccount(provider=IdentityProvider.apple,
                                canonical_provider_account_id="apple-1"))


# [utest->req~grants-no-gate-bypass~1]
def test_no_grant_is_activated_by_relaxing_or_bypassing_the_gate():
    ios = platform_gate(ClaimBranch.native_ios)
    confirmed = DeviceBitWrite(call=DeviceBitCall.devicecheck_write, confirmed=True)
    assert_no_gate_bypass(ClaimBranch.native_ios, completed=ios, write=confirmed)
    with pytest.raises(FreeGrantError):
        # Omitting the vendor write step.
        assert_no_gate_bypass(ClaimBranch.native_ios,
                              completed=[step for step in ios
                                         if step != "write_bit_and_await_apple_confirmation"],
                              write=confirmed)
    with pytest.raises(FreeGrantError):
        # Substituting a step of its own.
        assert_no_gate_bypass(ClaimBranch.native_ios, completed=(*ios, "trust_client_assertion"),
                              write=confirmed)
    with pytest.raises(DeviceBitWriteError):
        # Activating before the vendor confirms the write.
        assert_no_gate_bypass(ClaimBranch.native_ios, completed=ios,
                              write=DeviceBitWrite(call=DeviceBitCall.devicecheck_write,
                                                   confirmed=False))
    with pytest.raises(DeviceBitWriteError):
        assert_no_gate_bypass(ClaimBranch.native_ios, completed=ios, write=None)


# [utest->req~grants-per-device-states-persist~1]
def test_the_per_device_states_persist_and_the_database_bounds_hold():
    assert PERSISTS_ACROSS == ("app_reinstall", "device_reset")
    assert_device_states_persist()
    for event in PERSISTS_ACROSS:
        with pytest.raises(FreeGrantError):
            assert_device_states_persist(cleared_by=(event,))
    # The accepted same-device race is bounded to one extra grant.
    assert_device_states_persist(extra_grants_from_race=1)
    with pytest.raises(ProofAdapterError):
        assert_device_states_persist(extra_grants_from_race=2)
    # The database bounds are independent of any device.
    assert_database_bounds(committed_free_sources=(AccessGrantSource.anonymous_device_grant,),
                           active_grants=1)
    with pytest.raises(FreeGrantError):
        assert_database_bounds(
            committed_free_sources=(AccessGrantSource.anonymous_device_grant,
                                    AccessGrantSource.anonymous_device_grant),
            active_grants=1)
    with pytest.raises(FreeGrantError):
        assert_database_bounds(committed_free_sources=(), active_grants=2)


# [utest->req~grants-vendor-state-never-client-supplied~1]
def test_no_client_supplied_vendor_state_is_ever_accepted_as_verified():
    assert assert_vendor_state_not_client_supplied({"devicecheck_query_token": "q"})
    for claimed in ("device_check_state", "bit0", "recall_state", "bot_check_passed",
                    "provider_data", "signed_in_with_google"):
        with pytest.raises(ProofRejected):
            assert_vendor_state_not_client_supplied({claimed: True})
    with pytest.raises(ProofAdapterError):
        # Nor is vendor material ever read as identity.
        assert_vendor_state_not_client_supplied({"play_integrity_token": "t", "user_id": "u"})
    # Withheld write material refuses the claim before a grant exists.
    assert_write_material_present(ClaimBranch.native_ios,
                                  (ProofArtifact.devicecheck_query_token,
                                   ProofArtifact.devicecheck_update_token))
    with pytest.raises(ProofRejected):
        assert_write_material_present(ClaimBranch.native_ios,
                                      (ProofArtifact.devicecheck_query_token,))
    with pytest.raises(ProofRejected):
        assert_write_material_present(ClaimBranch.native_android, ())


# [utest->req~grants-anti-abuse-row-records-gate~1]
def test_each_anonymous_row_records_its_gate_and_no_device_principal():
    native = free_grant_anti_abuse_row(grant_id=uuid7(),
                                       source=AccessGrantSource.anonymous_device_grant,
                                       platform=DevicePlatform.android, created_at=NOW)
    assert gate_recorded_by(native) == "android_play_integrity"
    assert "device_principal" not in native and "device_principal_hash" not in native
    web = free_grant_anti_abuse_row(grant_id=uuid7(),
                                    source=AccessGrantSource.anonymous_device_grant,
                                    idp_account_hash=b"h" * 32, idp_account_hash_key_version=2,
                                    created_at=NOW)
    assert gate_recorded_by(web) == BRANCH_VENDOR_GATE[ClaimBranch.web]
    assert "provider_uid" not in web
    with pytest.raises(FreeGrantError):
        gate_recorded_by({"grant_source": AccessGrantSource.registered_account_grant})
    with pytest.raises(FreeGrantError):
        gate_recorded_by({"grant_source": AccessGrantSource.anonymous_device_grant,
                          "device_principal_hash": b"x"})


# --- Branch selection -----------------------------------------------------------------------------


# [utest->req~grants-branch-selection-deterministic~1]
def test_branch_selection_resolves_exactly_one_evidence_set():
    assert select_branch(IOS_EVIDENCE) is ClaimBranch.native_ios
    assert select_branch(ANDROID_EVIDENCE) is ClaimBranch.native_android
    assert select_branch(WEB_EVIDENCE) is ClaimBranch.web
    # Zero sets, more than one set, and a partial set are all request-shape errors.
    with pytest.raises(BranchShapeError):
        select_branch(ClaimEvidence())
    with pytest.raises(BranchShapeError):
        select_branch(ClaimEvidence(play_integrity_token="t", turnstile_token="c"))
    with pytest.raises(BranchShapeError) as partial:
        select_branch(ClaimEvidence(devicecheck_query_token="q"))
    # It is audited as `proof_malformed` with the shape cause, and surfaces as `proof_rejected`.
    assert partial.value.result is AuthEventResult.proof_malformed
    assert partial.value.error_code == "proof_rejected"
    assert "partial" in partial.value.audit_detail()["failure"]["shape_cause"]


# [utest->req~grants-branch-selection-deterministic~1]
def test_branch_selection_reads_only_the_evidence_the_request_carries():
    assert set(BRANCH_SELECTION_INPUTS) == {"devicecheck_query_token", "devicecheck_update_token",
                                            "play_integrity_token", "turnstile_token"}
    with pytest.raises(FreeGrantError):
        select_branch(WEB_EVIDENCE, declared_channel="web")
    for consulted in ("user_agent", "stored_provider", "x-platform", "authorization"):
        with pytest.raises(FreeGrantError):
            select_branch(WEB_EVIDENCE, consulted=(consulted,))
    # The selected set is verified server-side before that branch's eligibility is evaluated.
    assert_branch_verified(ClaimBranch.native_android,
                           ("package_name", "signing_certificate_digest"))
    with pytest.raises(ProofRejected):
        assert_branch_verified(ClaimBranch.native_android, ("package_name",))
    with pytest.raises(ProofRejected):
        assert_branch_verified(ClaimBranch.web, ())


# [utest->req~grants-branch-pinning-and-shared-admission~1]
def test_an_anonymous_identity_is_pinned_to_one_native_branch_and_shares_one_budget():
    fresh = identity_row()
    assert (pin_native_platform(fresh, ClaimBranch.native_ios)
            is NativeClaimPlatform.ios_devicecheck)
    pinned = identity_row(native_claim_platform=NativeClaimPlatform.ios_devicecheck)
    assert pin_native_platform(pinned, ClaimBranch.native_ios) is NativeClaimPlatform.ios_devicecheck
    with pytest.raises(FreeGrantRejected):
        # The same anonymous identity cannot switch to the other platform's material.
        pin_native_platform(pinned, ClaimBranch.native_android)
    with pytest.raises(FreeGrantRejected):
        # An anonymous identity may use only the device-attestation branches.
        pin_native_platform(fresh, ClaimBranch.web)
    with pytest.raises(ProofRejected):
        pin_native_platform(fresh, ClaimBranch.native_ios, attestation_verified=False)
    # A registered claimant is not pinned and may use the web gate from any surface.
    assert pin_native_platform(google_row(), ClaimBranch.web) is None
    # Every branch shares the one endpoint-level admission pair.
    pairs = {claim_admission_pair(branch) for branch in ClaimBranch}
    assert pairs == {ANONYMOUS_GRANT_ADMISSION["complete"]}
    assert claim_admission_pair(ClaimBranch.web, "prepare") == ANONYMOUS_GRANT_ADMISSION["prepare"]


# --- The required rules for `claim_anonymous_grant` -----------------------------------------------


# [utest->req~grants-anon-rule-pre-consumption-then-challenge~1]
def test_admission_and_the_challenge_claim_precede_every_vendor_call():
    assert ANONYMOUS_CLAIM_STEPS[:2] == (ClaimStep.admission, ClaimStep.challenge_claim)
    claim = AnonymousGrantClaim()
    with pytest.raises(FreeGrantError):
        # No vendor call, Cloudflare validation or Admin lookup precedes admission.
        claim.admit(pre_consumption_passed=True, handler_admission_passed=True,
                    vendor_calls_made=1)
    refused = AnonymousGrantClaim()
    with pytest.raises(FreeGrantError):
        refused.admit(pre_consumption_passed=True, handler_admission_passed=False)
    ordered = AnonymousGrantClaim()
    ordered.admit(pre_consumption_passed=True, handler_admission_passed=True)
    with pytest.raises(FreeGrantError):
        # The identity step cannot run before the challenge is claimed.
        ordered.resolve_identity(context_for(identity_row()), identity_row())
    challenge = FakeChallenge(outcome=ClaimOutcome.already_used)
    with pytest.raises(FreeGrantError):
        ordered.claim_challenge(challenge)
    assert challenge.claims == 1


# [utest->req~grants-anon-rule-identity-barrier~1]
def test_the_claim_takes_its_identity_from_the_shared_barrier():
    row = identity_row()
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(FakeChallenge())
    assert claim.resolve_identity(context_for(row), row) is row
    # A pre-auth context never reaches the claim's rules.
    unlinked = AnonymousGrantClaim()
    unlinked.admit(pre_consumption_passed=True, handler_admission_passed=True)
    unlinked.claim_challenge(FakeChallenge())
    with pytest.raises(FreeGrantRejected):
        unlinked.resolve_identity(context_for(row, ResolutionOutcome.pre_auth), row)
    # Nor does a historical identity row.
    historical = identity_row(identity_state=IdentityState.historical)
    another = AnonymousGrantClaim()
    another.admit(pre_consumption_passed=True, handler_admission_passed=True)
    another.claim_challenge(FakeChallenge())
    with pytest.raises(FreeGrantRejected):
        another.resolve_identity(context_for(historical), historical)
    # Web requires a registered claimant; the native branches also accept the anonymous one.
    with pytest.raises(FreeGrantRejected):
        claim.select_branch(WEB_EVIDENCE, row, verified=("hostname", "action"))


# [utest->req~grants-anon-rule-read-platform-gate~1]
def test_the_claim_reads_the_platform_gate_of_the_branch_it_selected():
    transport = FakeDeviceCheck()
    claim, _ = run_native_claim(DeviceCheckAdapter(APPLE, transport), IOS_MATERIAL, IOS_EVIDENCE,
                                ("apple_team_id", "devicecheck_environment"))
    assert transport.queries, "the native gate read the per-device state"
    web_claim, _ = run_web_claim()
    assert ClaimStep.platform_gate in web_claim.steps
    # A native branch cannot be read through the web gate's inputs, and vice versa.
    native_only = AnonymousGrantClaim()
    native_only.admit(pre_consumption_passed=True, handler_admission_passed=True)
    native_only.claim_challenge(FakeChallenge())
    row = identity_row()
    native_only.resolve_identity(context_for(row), row)
    native_only.select_branch(IOS_EVIDENCE, row,
                              verified=("apple_team_id", "devicecheck_environment"))
    with pytest.raises(FreeGrantError):
        native_only.read_platform_gate(web=(google_row(), lambda: True, GOOGLE_PROVIDER_DATA))


# [utest->req~grants-anon-rule-web-classifier-and-hash~1]
def test_the_web_branch_persists_the_derived_hash_and_key_version_on_its_row():
    index = alias_index()
    _, activated = run_web_claim(index=index)
    assert activated.alias is not None
    assert activated.anti_abuse["idp_account_hash"] == activated.alias.digest
    assert activated.anti_abuse["idp_account_hash_key_version"] == 1
    assert activated.anti_abuse["native_claim_provider"] is None
    # The hash is derived with the stored provider as the HMAC provider component.
    row = google_row()
    account, alias = read_web_gate(row, bot_check=lambda: True,
                                   provider_data=GOOGLE_PROVIDER_DATA, index=index)
    expected = index.alias(ProviderAccount(provider=IdentityProvider.google,
                                           provider_uid="google-account-1"))
    assert alias is not None and alias.digest == expected.digest
    # A live record that classifies as the other provider never reaches the derivation.
    apple_row = identity_row(provider=IdentityProvider.apple, provider_uid="apple-1")
    with pytest.raises(GateDenied):
        read_web_gate(apple_row, bot_check=lambda: True, provider_data=GOOGLE_PROVIDER_DATA,
                      index=index)


# [utest->req~grants-anon-rule-already-consumed-rejects~1]
def test_an_already_claimed_state_or_consumed_web_gate_rejects_without_granting():
    claimed = FakeDeviceCheck(bits={"bit0": True, "bit1": False})
    with pytest.raises(DeviceGrantExhausted) as exhausted:
        run_native_claim(DeviceCheckAdapter(APPLE, claimed), IOS_MATERIAL, IOS_EVIDENCE,
                         ("apple_team_id", "devicecheck_environment"))
    assert exhausted.value.error_code == "device_grant_exhausted"
    assert claimed.updates == []
    # The web gate is consumed per provider account: the second claim is rejected.
    index = alias_index()
    run_web_claim(index=index)
    with pytest.raises(ClaimRejection) as conflict:
        run_web_claim(index=index, row=google_row())
    assert conflict.value.error_code == "device_grant_exhausted"


# [utest->req~grants-anon-rule-device-recall-fails-closed~1]
def test_a_verdict_without_device_recall_is_rejected_with_no_grant():
    without_recall = FakePlayIntegrity(verdict={"appIntegrity": APP_INTEGRITY})
    adapter = PlayIntegrityAdapter(GOOGLE, without_recall, release_policy=RECALL_POLICY)
    with pytest.raises(ProofRejected) as rejected:
        run_native_claim(adapter, ANDROID_MATERIAL, ANDROID_EVIDENCE,
                         ("package_name", "signing_certificate_digest"))
    assert rejected.value.result is AuthEventResult.proof_malformed
    assert without_recall.writes == []
    # A client assertion explaining the absence changes nothing.
    asserted = FakePlayIntegrity(verdict={"appIntegrity": APP_INTEGRITY,
                                          "deviceRecallUnsupported": True})
    with pytest.raises(ProofRejected):
        run_native_claim(PlayIntegrityAdapter(GOOGLE, asserted, release_policy=RECALL_POLICY),
                         ANDROID_MATERIAL, ANDROID_EVIDENCE,
                         ("package_name", "signing_certificate_digest"))


# [utest->req~grants-anon-rule-db-eligibility-lifetime-slot~1]
def test_any_committed_free_grant_refuses_the_claim_and_is_never_an_idempotent_success():
    for held in (AccessGrantSource.anonymous_device_grant,
                 AccessGrantSource.registered_account_grant):
        transport = FakeDeviceCheck()
        with pytest.raises(ClaimRejection) as refused:
            run_native_claim(DeviceCheckAdapter(APPLE, transport), IOS_MATERIAL, IOS_EVIDENCE,
                             ("apple_team_id", "devicecheck_environment"), committed=(held,))
        # An existing grant is an ineligible database state, not a success shortcut.
        assert refused.value.result is AuthEventResult.anti_abuse_already_claimed
        assert transport.updates == []
    assert LIFETIME_FREE_GRANTS_PER_ACCOUNT == 1
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(FakeChallenge())
    row = identity_row()
    claim.resolve_identity(context_for(row), row)
    claim.select_branch(IOS_EVIDENCE, row, verified=("apple_team_id", "devicecheck_environment"))
    ledger = NativeClaimLedger()
    claim.read_platform_gate(native=(DeviceCheckAdapter(APPLE, FakeDeviceCheck()), IOS_MATERIAL,
                                     ledger))
    with pytest.raises(FreeGrantError):
        # The backend never reconciles vendor state from a grant row.
        claim.check_database_eligibility(committed_free_sources=(), reconcile_vendor_state=True)


# [utest->req~grants-anon-rule-native-bit-write~1]
def test_only_a_vendor_confirmed_write_permits_activation():
    ambiguous = FakeDeviceCheck(acknowledgment={})
    with pytest.raises(NativeClaimWriteFailed):
        run_native_claim(DeviceCheckAdapter(APPLE, ambiguous), IOS_MATERIAL, IOS_EVIDENCE,
                         ("apple_team_id", "devicecheck_environment"))
    refused = FakeDeviceCheck(acknowledgment={"acknowledged": False})
    with pytest.raises(NativeClaimWriteFailed):
        run_native_claim(DeviceCheckAdapter(APPLE, refused), IOS_MATERIAL, IOS_EVIDENCE,
                         ("apple_team_id", "devicecheck_environment"))
    # The write step cannot run before the database eligibility check.
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(FakeChallenge())
    row = identity_row()
    claim.resolve_identity(context_for(row), row)
    claim.select_branch(IOS_EVIDENCE, row, verified=("apple_team_id", "devicecheck_environment"))
    ledger = NativeClaimLedger()
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    claim.read_platform_gate(native=(adapter, IOS_MATERIAL, ledger))
    with pytest.raises(FreeGrantError):
        claim.write_native_bit(adapter, IOS_MATERIAL, ledger=ledger)


# [utest->req~grants-anon-rule-activation-transaction~1]
def test_the_activation_transaction_writes_every_row_and_consumes_the_challenge():
    challenge = FakeChallenge()
    _, activated = run_native_claim(DeviceCheckAdapter(APPLE, FakeDeviceCheck()), IOS_MATERIAL,
                                    IOS_EVIDENCE, ("apple_team_id", "devicecheck_environment"),
                                    challenge=challenge)
    assert activated.grant["source"] is AccessGrantSource.anonymous_device_grant
    assert activated.grant["status"] is AccessGrantStatus.active
    assert activated.grant["tier_id"] == FREE_TIER
    assert activated.grant["subscription_id"] is None
    assert activated.anti_abuse["native_claim_provider"] is NativeClaimPlatform.ios_devicecheck
    assert activated.anti_abuse["idp_account_hash"] is None
    assert activated.usage.grant_id == activated.grant["id"]
    assert challenge.consumes == 1
    assert activated.audit.result is AuthEventResult.succeeded
    # The platform lives in audit detail and never in the source value.
    assert activated.audit.details["verification"]["platform"] == "ios_devicecheck"
    assert "ios" not in str(activated.grant["source"])
    # A web row carries the alias instead of the native provider.
    _, web = run_web_claim()
    assert web.anti_abuse["native_claim_provider"] is None
    assert web.anti_abuse["idp_account_hash"] is not None


# [utest->req~grants-anon-rule-reconfirm-in-transaction~1]
def test_the_live_state_is_reconfirmed_inside_the_activation_transaction():
    claim = AnonymousGrantClaim()
    challenge = FakeChallenge()
    row = identity_row()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(challenge)
    claim.resolve_identity(context_for(row), row)
    claim.select_branch(IOS_EVIDENCE, row, verified=("apple_team_id", "devicecheck_environment"))
    ledger = NativeClaimLedger()
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    claim.read_platform_gate(native=(adapter, IOS_MATERIAL, ledger))
    claim.check_database_eligibility(committed_free_sources=(), ledger=ledger)
    write = claim.write_native_bit(adapter, IOS_MATERIAL, ledger=ledger)
    transaction = object()
    with pytest.raises(ClaimRejection):
        claim.activate(user_id=row.user_id, grant_id=uuid7(), tier_id=FREE_TIER,
                       transaction=transaction,
                       locks=LockLedger(LockingPath.claim_anonymous_grant_completion),
                       reconfirm=lambda: False, challenge=challenge, write=write, now=NOW)
    assert challenge.consumes == 0


# [utest->req~grants-anon-rule-uncancellable-context~1]
def test_the_read_write_activate_sequence_runs_in_a_disconnect_shielded_context():
    claim = AnonymousGrantClaim()
    challenge = FakeChallenge()
    row = identity_row()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(challenge)
    claim.resolve_identity(context_for(row), row)
    claim.select_branch(IOS_EVIDENCE, row, verified=("apple_team_id", "devicecheck_environment"))
    ledger = NativeClaimLedger()
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    claim.read_platform_gate(native=(adapter, IOS_MATERIAL, ledger))
    claim.check_database_eligibility(committed_free_sources=(), ledger=ledger)
    write = claim.write_native_bit(adapter, IOS_MATERIAL, ledger=ledger)
    with pytest.raises(ProofAdapterError):
        claim.activate(user_id=row.user_id, grant_id=uuid7(), tier_id=FREE_TIER,
                       transaction=object(),
                       locks=LockLedger(LockingPath.claim_anonymous_grant_completion),
                       reconfirm=lambda: True, challenge=challenge, write=write,
                       context=ExecutionContext.request_cancellation_scope)
    assert challenge.consumes == 0


# [utest->req~grants-anon-rule-no-enrolled-key~1]
def test_no_enrolled_key_or_per_key_uniqueness_row_participates():
    assert ENROLLED_KEY_PARTICIPANTS == frozenset()
    assert PER_KEY_UNIQUENESS_ROWS == frozenset()
    assert_no_enrolled_key()
    with pytest.raises(FreeGrantError):
        assert_no_enrolled_key(participants=("app_attest_key",))
    with pytest.raises(FreeGrantError):
        assert_no_enrolled_key(uniqueness_rows=("attestation_key_uniqueness",))


# [utest->req~grants-anon-proof-not-identity~1]
def test_the_proof_and_bot_check_are_never_identity():
    row = identity_row()
    assert claim_identity(context_for(row)) == (row.issuer, row.subject)
    for offered in ("devicecheck_query_token", "play_integrity_token", "turnstile_token"):
        with pytest.raises(FreeGrantError):
            claim_identity(context_for(row), offered=(offered,))
    with pytest.raises(FreeGrantError):
        claim_identity(VerifiedIdentityContext(issuer="", subject="",
                                               outcome=ResolutionOutcome.linked))
