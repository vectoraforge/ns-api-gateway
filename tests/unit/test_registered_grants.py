"""`claim_registered_grant`: its required rules, its three destinations, and its audit details."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
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
    idp_account_hash,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import (
    BindingDivergenceError,
    ExternalIdentityRow,
    IdentityError,
    IdentityState,
    NativeClaimPlatform,
)
from nativespeaker.api.auth.free_grants import (
    ClaimEvidence,
    FreeGrantError,
    FreeGrantRejected,
)
from nativespeaker.api.auth.grant_failures import GrantFailureError
from nativespeaker.api.auth.invariants import (
    GateConsumptionKind,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.locks import LockingPath, LockLedger
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_adapters import (
    AndroidClaimMaterial,
    AppleCredentials,
    DeviceCheckAdapter,
    DeviceGrantExhausted,
    GoogleCredentials,
    IosClaimMaterial,
    NativeClaimLedger,
    PlayIntegrityAdapter,
    ProofRejected,
    ReleaseKey,
    ReleasePolicyRegistry,
    ReleaseRecallPolicy,
)
from nativespeaker.api.auth.proof_endpoints import ClaimBranch
from nativespeaker.api.auth.registered_grants import (
    ACCOUNT_LAYER_BINDINGS,
    CLIENT_REACHABLE_GRANT_ENDERS,
    GRANT_DROPPING_CALLS,
    GRANT_PROVIDERS,
    GRANT_VALUE_RANKINGS,
    PENDING_CLAIM_QUEUES,
    REGISTERED_TO_ANONYMOUS_DOWNGRADES,
    SERVER_VERIFIABLE_PLATFORM_CLAIM,
    RegisteredClaimStep,
    RegisteredDestination,
    RegisteredDestinationBlocked,
    RegisteredGrantClaim,
    assert_account_grant_history,
    assert_firebase_uid_not_anchor,
    assert_no_device_proof_as_identity,
    assert_no_raw_provider_ids,
    assert_one_active_grant,
    assert_registered_provider,
    backstop_reachable,
    confirm_stored_binding_live,
    consume_registered_gate,
    destination_rejection,
    manual_grant_end,
    platform_spoof_bound,
    registered_account_alias,
    registered_audit_details,
    registered_eligibility,
    registered_grant_operation,
    registered_provider_account,
    registered_recall_required,
    resolve_claim_kind,
    select_destination,
    supersession_write_order,
)
from nativespeaker.api.quota.grants import GrantRow

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
FREE_TIER = "free_registered"
APPLE = AppleCredentials(team_id="TEAM123456", key_id="KEY1", private_key=SecretStr("pem"))
GOOGLE = GoogleCredentials(package_name="com.nativespeaker.app",
                           service_account_email="svc@example.iam.gserviceaccount.com",
                           private_key=SecretStr("pem"))
IOS_EVIDENCE = ClaimEvidence(devicecheck_query_token="q-token", devicecheck_update_token="u-token")
ANDROID_EVIDENCE = ClaimEvidence(play_integrity_token="integrity-token")
WEB_EVIDENCE = ClaimEvidence(turnstile_token="cf-token")
IOS_MATERIAL = IosClaimMaterial(query_token="q-token", update_token="u-token")
ANDROID_MATERIAL = AndroidClaimMaterial(integrity_token="integrity-token")
ENUMERATED_RELEASE = ReleaseKey(package_name="com.nativespeaker.app",
                                signing_certificate_digest="AA:BB", release="2026.08.1")
APP_INTEGRITY = {"packageName": ENUMERATED_RELEASE.package_name,
                 "certificateSha256Digest": [ENUMERATED_RELEASE.signing_certificate_digest],
                 "release": ENUMERATED_RELEASE.release}
RECALL_REQUIRED = ReleasePolicyRegistry({ENUMERATED_RELEASE:
                                         ReleaseRecallPolicy.device_recall_required})
NO_RECALL = ReleasePolicyRegistry({ENUMERATED_RELEASE: ReleaseRecallPolicy.no_device_recall})
GOOGLE_PROVIDER_DATA: list[Any] = [{"providerId": "google.com", "uid": "google-account-1"}]
OTHER_PROVIDER_DATA: list[Any] = [{"providerId": "google.com", "uid": "google-account-2"}]


# --- fixtures and doubles -------------------------------------------------------------------------


def google_row(**overrides: Any) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.google,
                              "provider_uid": "google-account-1",
                              "identity_state": IdentityState.active}
    fields.update(overrides)
    return ExternalIdentityRow(id=fields.pop("row_id", None) or uuid7(),
                               user_id=fields.pop("user_id", None) or uuid7(),
                               issuer="https://securetoken.google.com/test-project",
                               subject="firebase-subject", **fields)


def context_for(row: ExternalIdentityRow,
                outcome: ResolutionOutcome = ResolutionOutcome.linked) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=row.issuer, subject=row.subject, outcome=outcome,
                                   user_id=row.user_id, external_identity_id=row.id,
                                   provider=row.provider)


def key_ring() -> KeyRing:
    return KeyRing(KeyFamily.k_idp_account, current=HmacKey(version=1, secret=b"i" * 32))


def alias_index(ring: KeyRing | None = None,
                gates: ProviderAccountGates | None = None) -> IdpAccountAliasIndex:
    return IdpAccountAliasIndex(gates or ProviderAccountGates(), ring or key_ring())


def grant_row(source: AccessGrantSource,
              *,
              user_id: UUID | None = None,
              status: AccessGrantStatus = AccessGrantStatus.active,
              starts_at: datetime | None = None,
              ends_at: datetime | None = None,
              grant_id: UUID | None = None) -> GrantRow:
    return GrantRow(grant_id=grant_id or uuid7(), user_id=user_id or uuid7(), tier_id=FREE_TIER,
                    source=source, status=status, starts_at=starts_at or (NOW - timedelta(days=1)),
                    ends_at=ends_at)


class FakeDeviceCheck:
    def __init__(self, *, bits: dict[str, Any] | None = None, acknowledged: bool = True):
        self.bits = {"bit0": False, "bit1": False} if bits is None else bits
        self.acknowledged = acknowledged
        self.updates: list[dict[str, Any]] = []

    def query_two_bits(self, *, query_token: str, team_id: str, environment: Any) -> Any:
        return self.bits

    def update_two_bits(self, *, update_token: str, team_id: str, environment: Any,
                        bits: Any) -> Any:
        self.updates.append(dict(bits))
        return {"acknowledged": self.acknowledged}


class FakePlayIntegrity:
    def __init__(self, *, recall: dict[str, Any] | None = None):
        self.recall = {"registered_account_grant_recall": False} if recall is None else recall
        self.writes: list[dict[str, Any]] = []

    def decode_verdict(self, *, integrity_token: str, credentials: Any) -> Any:
        return {"appIntegrity": APP_INTEGRITY, "deviceRecall": self.recall}

    def write_recall(self, *, integrity_token: str, credentials: Any, state: Any,
                     value: bool) -> Any:
        self.writes.append({"state": str(state), "value": value})
        return {"confirmed": True}


def claim_to_kind(kind: ClaimBranch,
                  row: ExternalIdentityRow,
                  index: IdpAccountAliasIndex,
                  *,
                  provider_data: list[Any] | None = None) -> RegisteredGrantClaim:
    """One attempt, run up to and including the mandatory confirmation."""
    evidence = {ClaimBranch.native_ios: IOS_EVIDENCE,
                ClaimBranch.native_android: ANDROID_EVIDENCE,
                ClaimBranch.web: WEB_EVIDENCE}[kind]
    claim = RegisteredGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(lambda: ClaimOutcome.claimed)
    claim.resolve_identity(context_for(row), row)
    claim.resolve_kind(evidence)
    claim.confirm_binding(row, provider_data or GOOGLE_PROVIDER_DATA, index)
    return claim


def run_web_claim(*,
                  row: ExternalIdentityRow | None = None,
                  index: IdpAccountAliasIndex | None = None,
                  grants: tuple[GrantRow, ...] = (),
                  committed: tuple[AccessGrantSource, ...] = (),
                  carried_usage: tuple[str, int] | None = None,
                  grant_id: UUID | None = None) -> Any:
    row = row if row is not None else google_row()
    index = index if index is not None else alias_index()
    claim = claim_to_kind(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    claim.check_database_eligibility(grants=grants, committed_free_sources=committed, now=NOW)
    transaction = object()
    return claim, claim.activate(row=row, grant_id=grant_id or uuid7(), tier_id=FREE_TIER,
                                 alias_index=index, transaction=transaction,
                                 locks=LockLedger(LockingPath.claim_registered_grant_completion),
                                 consume_challenge=lambda: True, carried_usage=carried_usage,
                                 now=NOW)


def run_ios_claim(*,
                  bits: dict[str, Any] | None = None,
                  row: ExternalIdentityRow | None = None,
                  index: IdpAccountAliasIndex | None = None) -> Any:
    row = row if row is not None else google_row(
        native_claim_platform=NativeClaimPlatform.ios_devicecheck)
    index = index if index is not None else alias_index()
    transport = FakeDeviceCheck(bits=bits)
    adapter = DeviceCheckAdapter(APPLE, transport)
    ledger = NativeClaimLedger()
    claim = claim_to_kind(ClaimBranch.native_ios, row, index)
    claim.read_registered_state(native=(adapter, IOS_MATERIAL, ledger))
    claim.check_database_eligibility(grants=(), committed_free_sources=(), now=NOW, ledger=ledger)
    write = claim.write_registered_bit(adapter, IOS_MATERIAL, ledger=ledger)
    transaction = object()
    activation = claim.activate(row=row, grant_id=uuid7(), tier_id=FREE_TIER, alias_index=index,
                                transaction=transaction,
                                locks=LockLedger(LockingPath.claim_registered_grant_completion),
                                consume_challenge=lambda: True, write=write, now=NOW)
    return claim, transport, activation


# --- The operation, and its provider vocabulary ---------------------------------------------------


# [utest->req~grants-registered-operation-definition~1]
def test_the_registered_grant_is_the_uniform_backstop_and_ranks_no_grant():
    definition = registered_grant_operation()
    assert definition.source is AccessGrantSource.registered_account_grant
    assert definition.gate_kind.value == "registered_account_grant"
    assert definition.gates == ("user_own_grant_history", "stored_provider_classification",
                                "registered_account_grant_gate_consumption")
    assert definition.platform_uniform
    assert definition.convertible_source is AccessGrantSource.anonymous_device_grant
    # No ranking, no queue behind a held grant, and no call that drops one.
    assert not (GRANT_VALUE_RANKINGS or PENDING_CLAIM_QUEUES or GRANT_DROPPING_CALLS)
    # It never outranks a grant the user already holds: refused while one is active, and
    # reachable again once it is not.
    assert not backstop_reachable(active_grant_source=AccessGrantSource.subscription)
    assert not backstop_reachable(active_grant_source=AccessGrantSource.manual)
    assert backstop_reachable(active_grant_source=AccessGrantSource.anonymous_device_grant)
    assert backstop_reachable(active_grant_source=None)


# [utest->req~grants-reg-rule-provider-google-apple~1]
def test_only_a_google_or_apple_stored_provider_claims_the_registered_grant():
    assert GRANT_PROVIDERS == (IdentityProvider.anonymous, IdentityProvider.google,
                               IdentityProvider.apple)
    assert assert_registered_provider(google_row()) is IdentityProvider.google
    apple = google_row(provider=IdentityProvider.apple, provider_uid="apple-sub-1")
    assert assert_registered_provider(apple) is IdentityProvider.apple
    with pytest.raises(FreeGrantRejected) as rejected:
        assert_registered_provider(google_row(provider=IdentityProvider.anonymous,
                                              provider_uid=None))
    assert rejected.value.result is AuthEventResult.idp_account_not_eligible
    assert rejected.value.error_code == "verification_required"


# --- The rules, in order -------------------------------------------------------------------------


# [utest->req~grants-reg-rule-identity-barrier~1]
def test_the_barrier_supplies_the_linked_active_identity_and_nothing_else_does():
    row = google_row()
    claim = RegisteredGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(lambda: ClaimOutcome.claimed)
    assert claim.resolve_identity(context_for(row), row) is row
    assert claim.steps[-1] is RegisteredClaimStep.identity_barrier

    # A pre-auth caller of this linked-only endpoint is refused.
    unlinked = RegisteredGrantClaim()
    unlinked.admit(pre_consumption_passed=True, handler_admission_passed=True)
    unlinked.claim_challenge(lambda: ClaimOutcome.claimed)
    with pytest.raises(FreeGrantRejected) as refused:
        unlinked.resolve_identity(context_for(row, ResolutionOutcome.pre_auth), row)
    assert refused.value.error_code == "preauth_identity_not_allowed"

    # A historical identity is not an active external identity.
    historical = google_row(identity_state=IdentityState.historical)
    stale = RegisteredGrantClaim()
    stale.admit(pre_consumption_passed=True, handler_admission_passed=True)
    stale.claim_challenge(lambda: ClaimOutcome.claimed)
    with pytest.raises(FreeGrantRejected) as unavailable:
        stale.resolve_identity(context_for(historical), historical)
    assert unavailable.value.error_code == "account_unavailable"

    # The barrier's `(issuer, subject)` is mandatory, and the resolved row is the same row.
    empty = RegisteredGrantClaim()
    empty.admit(pre_consumption_passed=True, handler_admission_passed=True)
    empty.claim_challenge(lambda: ClaimOutcome.claimed)
    with pytest.raises(FreeGrantError):
        empty.resolve_identity(
            VerifiedIdentityContext(issuer="", subject="", outcome=ResolutionOutcome.linked), row)
    other = RegisteredGrantClaim()
    other.admit(pre_consumption_passed=True, handler_admission_passed=True)
    other.claim_challenge(lambda: ClaimOutcome.claimed)
    with pytest.raises(FreeGrantError):
        other.resolve_identity(context_for(google_row()), row)


# [utest->req~grants-reg-rule-no-device-proof-as-identity~1]
def test_no_device_proof_is_identity_ownership_or_account_resolution_evidence():
    assert_no_device_proof_as_identity()
    for offered in ("app_attest_assertion", "android_keystore_proof", "attestation_key_proof"):
        with pytest.raises(FreeGrantError):
            assert_no_device_proof_as_identity(required=[offered])
        with pytest.raises(FreeGrantError):
            assert_no_device_proof_as_identity(accepted=[offered])
        with pytest.raises(FreeGrantError):
            assert_no_device_proof_as_identity(evaluated=[offered])
    # The barrier step refuses an attempt that offers device proof as an identity input.
    row = google_row()
    claim = RegisteredGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.claim_challenge(lambda: ClaimOutcome.claimed)
    with pytest.raises(FreeGrantError):
        claim.resolve_identity(context_for(row), row,
                               offered_identity_inputs=["app_attest_attestation"])


# [utest->req~grants-reg-rule-server-owned-claim-kind~1]
def test_the_claim_kind_is_server_resolved_from_exactly_one_complete_evidence_set():
    assert resolve_claim_kind(IOS_EVIDENCE) is ClaimBranch.native_ios
    assert resolve_claim_kind(ANDROID_EVIDENCE) is ClaimBranch.native_android
    assert resolve_claim_kind(WEB_EVIDENCE) is ClaimBranch.web

    # Zero, multiple and partial evidence sets are `proof_rejected` request-shape errors.
    for evidence in (ClaimEvidence(),
                     ClaimEvidence(devicecheck_query_token="q", turnstile_token="cf"),
                     ClaimEvidence(devicecheck_query_token="q")):
        with pytest.raises(FreeGrantRejected) as rejected:
            resolve_claim_kind(evidence)
        assert rejected.value.error_code == "proof_rejected"
        assert rejected.value.result is AuthEventResult.proof_malformed

    # Never from a client-supplied platform header, and never by treating material as optional.
    with pytest.raises(FreeGrantError):
        resolve_claim_kind(IOS_EVIDENCE, platform_header="ios")
    with pytest.raises(FreeGrantError):
        resolve_claim_kind(IOS_EVIDENCE, optional_material=["devicecheck_update_token"])
    with pytest.raises(FreeGrantError):
        resolve_claim_kind(WEB_EVIDENCE, consulted=["user_agent"])

    # Omitting the iOS update token cannot turn a native claim into an account-only claim.
    with pytest.raises(FreeGrantRejected) as partial:
        resolve_claim_kind(ClaimEvidence(devicecheck_query_token="q-token"))
    assert partial.value.error_code == "proof_rejected"


# [utest->req~grants-reg-rule-android-release-policy~1]
def test_android_device_recall_follows_the_checked_in_release_policy():
    assert registered_recall_required(RECALL_REQUIRED, ENUMERATED_RELEASE) is True
    assert registered_recall_required(NO_RECALL, ENUMERATED_RELEASE) is False
    # An unrecognized, unenumerated release is rejected outright.
    unknown = ReleaseKey(package_name="com.nativespeaker.app",
                         signing_certificate_digest="AA:BB", release="2026.09.9")
    with pytest.raises(ProofRejected):
        registered_recall_required(RECALL_REQUIRED, unknown)
    # Omitted client material never selects the no-recall branch.
    with pytest.raises(ProofRejected):
        registered_recall_required(NO_RECALL, ENUMERATED_RELEASE, client_omitted_material=True)
    # A verdict is still read on a `no_device_recall` release, which carries no registered bit.
    transport = FakePlayIntegrity()
    adapter = PlayIntegrityAdapter(GOOGLE, transport, release_policy=NO_RECALL)
    ledger = NativeClaimLedger()
    adapter.verify_material(AuthOperation.claim_registered_grant, ANDROID_MATERIAL, ledger)
    assert adapter.read_claimed(AuthOperation.claim_registered_grant, ANDROID_MATERIAL,
                                ledger) is False


# [utest->req~grants-reg-rule-accepted-platform-spoof-bound~1]
def test_the_platform_spoof_bound_still_costs_one_brand_new_provider_account():
    assert not SERVER_VERIFIABLE_PLATFORM_CLAIM
    assert platform_spoof_bound(account_bindings=ACCOUNT_LAYER_BINDINGS) == 1
    # Drop any one account-layer binding and the bound no longer holds.
    for binding in ACCOUNT_LAYER_BINDINGS:
        weakened = [name for name in ACCOUNT_LAYER_BINDINGS if name != binding]
        with pytest.raises(FreeGrantError):
            platform_spoof_bound(account_bindings=weakened)


# [utest->req~grants-reg-rule-mandatory-providerdata-confirmation~1]
def test_every_call_confirms_the_stored_binding_and_a_divergence_mutates_nothing():
    row = google_row()
    assert confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA) == "google-account-1"
    # Exactly one lookup per call, through the issuer-selected Admin client, on every branch.
    with pytest.raises(FreeGrantError):
        confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA, lookups=2)
    with pytest.raises(FreeGrantError):
        confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA,
                                    issuer_selected_admin_client=False)
    with pytest.raises(FreeGrantError):
        confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA, mutations=["core.users"])
    # A divergent live result is a conflict that rewrites nothing.
    with pytest.raises(BindingDivergenceError):
        confirm_stored_binding_live(row, OTHER_PROVIDER_DATA)
    assert (row.provider, row.provider_uid) == (IdentityProvider.google, "google-account-1")
    # The idempotent repeat performs it too: the claim counts one lookup per attempt.
    index = alias_index()
    claim = claim_to_kind(ClaimBranch.web, row, index)
    assert claim.provider_data_lookups == 1
    with pytest.raises(FreeGrantError):
        claim.confirm_binding(row, GOOGLE_PROVIDER_DATA, index)


# [utest->req~grants-reg-rule-hash-from-stored-provider-uid~1]
def test_the_canonical_account_identifier_is_the_stored_provider_uid():
    account = registered_provider_account(google_row())
    assert account == ProviderAccount(provider=IdentityProvider.google,
                                      provider_uid="google-account-1")
    # The table's CHECK makes a registered row with no stored `provider_uid` unrepresentable, so
    # the row shape that stores none is the anonymous one: it is not eligible either.
    with pytest.raises(FreeGrantRejected) as rejected:
        registered_provider_account(google_row(provider=IdentityProvider.anonymous,
                                               provider_uid=None))
    assert rejected.value.result is AuthEventResult.idp_account_not_eligible
    assert rejected.value.error_code == "verification_required"
    assert registered_provider_account(
        google_row(provider=IdentityProvider.apple,
                   provider_uid="apple-sub-1")).provider_uid == "apple-sub-1"


# [utest->req~grants-reg-rule-firebase-uid-not-anchor~1]
def test_the_firebase_uid_is_never_the_uniqueness_anchor():
    assert str(assert_firebase_uid_not_anchor()) == "stable_provider_uid"
    for offered in ("firebase_uid", "subject", "uid", "actor_subject_hash"):
        with pytest.raises(FreeGrantError):
            assert_firebase_uid_not_anchor([offered])


# [utest->req~grants-reg-rule-hash-derivation~1]
def test_the_alias_is_derived_over_the_stored_binding_with_a_persisted_key_version():
    ring = key_ring()
    index = alias_index(ring)
    account = registered_provider_account(google_row())
    alias = registered_account_alias(index, account)
    assert alias.key_version == 1
    assert len(alias.digest) == 32
    # The same HMAC derivation this document defines, over the stored provider and stored uid.
    assert alias.digest == idp_account_hash(account.provider, account.provider_uid, ring).digest
    other = registered_account_alias(index, ProviderAccount(provider=IdentityProvider.google,
                                                            provider_uid="google-account-2"))
    assert other.digest != alias.digest


# [utest->req~grants-reg-rule-gate-consumption-uniqueness~1]
def test_the_registered_gate_is_consumable_once_per_provider_account():
    index = alias_index()
    account = registered_provider_account(google_row())
    transaction = object()
    first = uuid7()
    alias = consume_registered_gate(index, account, first, transaction=transaction,
                                    grant_transaction=transaction)
    assert index.consumed(account, GateConsumptionKind.registered_account_grant) == first
    assert alias.key_version == 1
    with pytest.raises(FreeGrantRejected) as conflict:
        consume_registered_gate(index, account, uuid7(), transaction=transaction,
                                grant_transaction=transaction)
    assert conflict.value.result is AuthEventResult.idp_account_already_claimed
    assert conflict.value.error_code == "account_already_claimed"
    # The consumption is inserted with its grant, in one transaction.
    with pytest.raises(FreeGrantError):
        consume_registered_gate(alias_index(), account, uuid7(), transaction=object(),
                                grant_transaction=object())


# [utest->req~grants-reg-rule-no-raw-provider-ids~1]
def test_no_raw_provider_account_identifier_is_persisted_outside_the_registry():
    assert_no_raw_provider_ids(columns=["idp_account_hash", "idp_account_hash_key_version"],
                               tables=["core.external_identities", "core.provider_accounts"])
    for column in ("provider_uid", "provider_account_id", "google_uid", "apple_sub"):
        with pytest.raises(GrantFailureError):
            assert_no_raw_provider_ids(columns=[column])
    for table in ("audit.auth_events", "core.access_grants_anti_abuse"):
        with pytest.raises(IdentityError):
            assert_no_raw_provider_ids(tables=[table])


# [utest->req~grants-reg-rule-account-grant-history~1]
def test_the_account_history_allows_one_free_grant_and_one_conversion():
    assert_account_grant_history(())
    # The conversion of the user's own active anonymous grant is the one permitted transition.
    assert_account_grant_history((AccessGrantSource.anonymous_device_grant,),
                                 converting_active_anonymous=True)
    # Any committed free grant refuses a new issuance.
    for held in (AccessGrantSource.anonymous_device_grant,
                 AccessGrantSource.registered_account_grant):
        with pytest.raises(FreeGrantRejected) as rejected:
            assert_account_grant_history((held,))
        assert rejected.value.error_code == "operation_not_allowed"
    # A committed registered grant is not convertible either.
    with pytest.raises(FreeGrantRejected):
        assert_account_grant_history((AccessGrantSource.registered_account_grant,),
                                     converting_active_anonymous=True)
    # An upgraded account never gets carried anonymous credits plus a fresh registered grant.
    with pytest.raises(FreeGrantRejected):
        assert_account_grant_history((), carried_anonymous_credits=True)


# [utest->req~grants-reg-rule-stored-state-only~1]
def test_eligibility_reads_stored_state_and_never_registered_at_or_live_state():
    row = google_row()
    assert registered_eligibility(row, provider_data_confirmed=True) == (
        IdentityProvider.google, "google-account-1")
    assert not REGISTERED_TO_ANONYMOUS_DOWNGRADES
    # `registered_at` is reporting data and is never consulted for eligibility.
    with pytest.raises(FreeGrantError):
        registered_eligibility(row, provider_data_confirmed=True, consulted=["registered_at"])
    # A divergent live provider refuses this free grant and reclassifies nothing.
    with pytest.raises(FreeGrantRejected) as rejected:
        registered_eligibility(row, provider_data_confirmed=True,
                               live_provider=IdentityProvider.anonymous)
    assert rejected.value.error_code == "verification_required"
    assert row.provider is IdentityProvider.google
    # A row with no stored `provider_uid` — the anonymous shape — is not eligible.
    with pytest.raises(FreeGrantRejected):
        registered_eligibility(google_row(provider=IdentityProvider.anonymous,
                                          provider_uid=None), provider_data_confirmed=True)
    # And an unconfirmed binding is not eligible either.
    with pytest.raises(FreeGrantRejected):
        registered_eligibility(row, provider_data_confirmed=False)


# [utest->req~grants-reg-rule-device-checked-kinds-bit~1]
def test_the_device_checked_kinds_read_check_write_then_activate_and_a_set_bit_is_exhausted():
    claim, transport, activation = run_ios_claim()
    assert claim.steps == [RegisteredClaimStep.admission, RegisteredClaimStep.challenge_claim,
                           RegisteredClaimStep.identity_barrier, RegisteredClaimStep.claim_kind,
                           RegisteredClaimStep.provider_data_confirmation,
                           RegisteredClaimStep.device_state_read,
                           RegisteredClaimStep.database_eligibility,
                           RegisteredClaimStep.registered_bit_write,
                           RegisteredClaimStep.activation]
    # The registered claim writes its own bit and leaves the anonymous one alone.
    assert transport.updates == [{"bit1": True}]
    assert activation.grant["source"] is AccessGrantSource.registered_account_grant

    # An already-set registered bit is durable exhaustion, on either device-checked kind.
    with pytest.raises(DeviceGrantExhausted) as exhausted:
        run_ios_claim(bits={"bit0": False, "bit1": True})
    assert exhausted.value.result is AuthEventResult.native_claim_already_claimed

    android_row = google_row(native_claim_platform=NativeClaimPlatform.android_play_integrity)
    index = alias_index()
    android = claim_to_kind(ClaimBranch.native_android, android_row, index)
    adapter = PlayIntegrityAdapter(
        GOOGLE, FakePlayIntegrity(recall={"registered_account_grant_recall": True}),
        release_policy=RECALL_REQUIRED)
    with pytest.raises(DeviceGrantExhausted):
        android.read_registered_state(native=(adapter, ANDROID_MATERIAL, NativeClaimLedger()))

    # The web kind has no such bit: it relies on the account rules plus the Turnstile pass.
    web = claim_to_kind(ClaimBranch.web, google_row(), alias_index())
    assert web.read_registered_state(turnstile=lambda: True) is False
    web.check_database_eligibility(grants=(), committed_free_sources=(), now=NOW)
    with pytest.raises(FreeGrantError):
        web.write_registered_bit(DeviceCheckAdapter(APPLE, FakeDeviceCheck()), IOS_MATERIAL,
                                 ledger=NativeClaimLedger())
    denied = claim_to_kind(ClaimBranch.web, google_row(), alias_index())
    with pytest.raises(FreeGrantRejected) as turnstile:
        denied.read_registered_state(turnstile=lambda: False)
    assert turnstile.value.error_code == "verification_required"


# [utest->req~grants-reg-rule-one-active-grant~1]
def test_the_operation_never_leaves_two_active_grants_or_two_allowances():
    assert_one_active_grant(active_after=1)
    with pytest.raises(FreeGrantError):
        assert_one_active_grant(active_after=2)
    with pytest.raises(FreeGrantError):
        assert_one_active_grant(active_after=1, second_allowance=True)
    # The conversion keeps exactly one active grant: the old row is deactivated in the same
    # transaction that inserts the new one.
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    _claim, activation = run_web_claim(grants=(anonymous,),
                                       committed=(AccessGrantSource.anonymous_device_grant,),
                                       carried_usage=("2026-08", 4))
    assert activation.superseded is not None
    assert activation.superseded["status"] is AccessGrantStatus.expired
    assert activation.grant["status"] is AccessGrantStatus.active
    # And a destination that would leave another effective grant standing never activates.
    row = google_row()
    index = alias_index()
    claim = claim_to_kind(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    decision = claim.check_database_eligibility(grants=(), committed_free_sources=(), now=NOW)
    claim.decision = replace(decision, effective_grants=1)
    with pytest.raises(FreeGrantError):
        claim.activate(row=row, grant_id=uuid7(), tier_id=FREE_TIER, alias_index=index,
                       transaction=object(),
                       locks=LockLedger(LockingPath.claim_registered_grant_completion),
                       consume_challenge=lambda: True, now=NOW)


# --- The destination rules -------------------------------------------------------------------------


# [utest->req~grants-dest-incompatible-active-grant~1]
def test_an_incompatible_active_grant_blocks_the_destination():
    ends = NOW + timedelta(days=20)
    held = grant_row(AccessGrantSource.subscription, ends_at=ends)
    with pytest.raises(RegisteredDestinationBlocked) as blocked:
        select_destination(grants=(held,), committed_free_sources=(), now=NOW)
    assert blocked.value.result is AuthEventResult.registered_grant_destination_incompatible
    assert blocked.value.error_code == "operation_not_allowed"
    assert blocked.value.held_grant_ends_at == ends
    # The user's own committed registered grant is the idempotent repeat, determined first.
    own = grant_row(AccessGrantSource.registered_account_grant, ends_at=ends)
    decision = select_destination(grants=(own,), committed_free_sources=(), now=NOW)
    assert decision.destination is RegisteredDestination.idempotent_repeat
    # An active anonymous device grant is the one grant this operation may move aside.
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    converted = select_destination(grants=(anonymous,),
                                   committed_free_sources=(
                                       AccessGrantSource.anonymous_device_grant,),
                                   now=NOW)
    assert converted.destination is RegisteredDestination.supersession_conversion


# [utest->req~grants-dest-rejection-is-a-wait~1]
def test_the_destination_rejection_is_a_wait_that_mutates_nothing():
    held = grant_row(AccessGrantSource.subscription, ends_at=NOW + timedelta(days=5))
    assert destination_rejection(held).held_grant_ends_at == held.ends_at
    with pytest.raises(FreeGrantError):
        destination_rejection(held, mutations=["core.access_grants"])
    # The destination check runs in the preflight, ahead of the registered-bit write.
    with pytest.raises(FreeGrantError):
        destination_rejection(held, registered_bit_written=True)
    # A held grant whose `ends_at` has passed does not block, even before the lazy flip; this
    # operation's own insert performs that flip.
    lapsed = grant_row(AccessGrantSource.subscription, ends_at=NOW - timedelta(minutes=1))
    decision = select_destination(grants=(lapsed,), committed_free_sources=(), now=NOW)
    assert decision.destination is RegisteredDestination.new_grant
    assert decision.lapsed_grant_ids == (lapsed.grant_id,)
    # And the same claim succeeds once the held grant is no longer active.
    _claim, activation = run_web_claim(grants=(lapsed,))
    assert activation.lapsed_grant_ids == (lapsed.grant_id,)


# [utest->req~grants-dest-manual-open-ended~1]
def test_an_open_ended_manual_grant_blocks_with_no_end_to_report():
    open_ended = grant_row(AccessGrantSource.manual, ends_at=None)
    assert manual_grant_end(open_ended) is None
    assert not CLIENT_REACHABLE_GRANT_ENDERS
    with pytest.raises(RegisteredDestinationBlocked) as blocked:
        select_destination(grants=(open_ended,), committed_free_sources=(), now=NOW)
    assert blocked.value.held_grant_ends_at is None
    finite = grant_row(AccessGrantSource.manual, ends_at=NOW + timedelta(days=2))
    assert manual_grant_end(finite) == finite.ends_at
    # Only an operator-managed source has this open-ended lifecycle.
    with pytest.raises(FreeGrantError):
        manual_grant_end(grant_row(AccessGrantSource.subscription))


# [utest->req~grants-dest-idempotent-repeat~1]
def test_the_idempotent_repeat_returns_the_same_grant_and_a_foreign_consumption_conflicts():
    own = grant_row(AccessGrantSource.registered_account_grant)
    decision = select_destination(grants=(own,), committed_free_sources=(
        AccessGrantSource.registered_account_grant,), now=NOW,
        gate_consumption_grant_id=own.grant_id)
    assert decision.destination is RegisteredDestination.idempotent_repeat
    assert decision.grant is own
    with pytest.raises(FreeGrantRejected) as conflict:
        select_destination(grants=(own,), committed_free_sources=(), now=NOW,
                           gate_consumption_grant_id=uuid7())
    assert conflict.value.result is AuthEventResult.idp_account_already_claimed

    # The repeat runs after the same mandatory live confirmation, and writes nothing.
    row = google_row()
    index = alias_index()
    claim = claim_to_kind(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    repeat = claim.check_database_eligibility(
        grants=(own,), committed_free_sources=(AccessGrantSource.registered_account_grant,),
        now=NOW, gate_consumption_grant_id=own.grant_id)
    assert repeat.destination is RegisteredDestination.idempotent_repeat
    alias = registered_account_alias(index, registered_provider_account(row))
    event = claim.repeat(row, alias=alias, grant=own)
    assert event.result is AuthEventResult.succeeded
    with pytest.raises(FreeGrantError):
        claim.activate(row=row, grant_id=uuid7(), tier_id=FREE_TIER, alias_index=index,
                       transaction=object(),
                       locks=LockLedger(LockingPath.claim_registered_grant_completion),
                       consume_challenge=lambda: True, now=NOW)


# [utest->req~grants-dest-supersession-conversion~1]
def test_the_conversion_supersedes_the_anonymous_grant_and_carries_its_usage_across():
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    grant_id = uuid7()
    _claim, activation = run_web_claim(grants=(anonymous,),
                                       committed=(AccessGrantSource.anonymous_device_grant,),
                                       carried_usage=("2026-07", 9), grant_id=grant_id)
    assert activation.destination is RegisteredDestination.supersession_conversion
    # The superseded row expires at the conversion time and keeps its source forever.
    assert activation.superseded == {"id": anonymous.grant_id,
                                     "source": AccessGrantSource.anonymous_device_grant,
                                     "status": AccessGrantStatus.expired,
                                     "ends_at": NOW}
    # Its anti-abuse row is left completely untouched: only the new grant has one here.
    assert activation.anti_abuse["grant_id"] == grant_id
    assert activation.anti_abuse["grant_source"] is AccessGrantSource.registered_account_grant
    # The allowance is transferred, not reissued: period and counter carry across unchanged.
    assert (activation.usage.monthly_period, activation.usage.monthly_used) == ("2026-07", 9)
    assert supersession_write_order(activation)[:2] == ("expire_anonymous_grant",
                                                        "insert_registered_grant")
    # The conversion cannot run without the superseded grant's usage state.
    with pytest.raises(FreeGrantError):
        run_web_claim(grants=(anonymous,),
                      committed=(AccessGrantSource.anonymous_device_grant,))
    # A uniqueness conflict on the gate rolls the whole transaction back, leaving the anonymous
    # grant active and unchanged.
    gates = ProviderAccountGates()
    index = alias_index(gates=gates)
    account = registered_provider_account(google_row())
    consume_registered_gate(index, account, uuid7(), transaction=None, grant_transaction=None)
    row = google_row()
    with pytest.raises(FreeGrantRejected) as conflict:
        run_web_claim(row=row, index=index, grants=(anonymous,),
                      committed=(AccessGrantSource.anonymous_device_grant,),
                      carried_usage=("2026-07", 9))
    assert conflict.value.result is AuthEventResult.idp_account_already_claimed
    assert anonymous.status is AccessGrantStatus.active


# [utest->req~grants-dest-new-grant-creation~1]
def test_new_grant_creation_inserts_a_fresh_grant_and_a_zeroed_usage_row():
    _claim, activation = run_web_claim()
    assert activation.destination is RegisteredDestination.new_grant
    assert activation.superseded is None
    assert activation.grant["source"] is AccessGrantSource.registered_account_grant
    assert activation.grant["status"] is AccessGrantStatus.active
    assert activation.grant["subscription_id"] is None
    assert (activation.usage.monthly_period, activation.usage.monthly_used) == ("2026-08", 0)
    assert activation.anti_abuse["idp_account_hash_key_version"] == 1
    # A committed free grant of either source that is not the convertible active anonymous grant
    # receives no new issuance.
    for held in (AccessGrantSource.anonymous_device_grant,
                 AccessGrantSource.registered_account_grant):
        with pytest.raises(FreeGrantRejected):
            run_web_claim(committed=(held,))
    # Only the conversion path carries an existing usage row across.
    with pytest.raises(FreeGrantError):
        run_web_claim(carried_usage=("2026-07", 3))


# --- Audit details -----------------------------------------------------------------------------------


# [utest->req~grants-reg-audit-details~1]
def test_the_audit_details_carry_the_stored_provider_and_key_version_and_no_raw_identifier():
    row = google_row()
    index = alias_index()
    alias = registered_account_alias(index, registered_provider_account(row))
    details = registered_audit_details(row, alias=alias,
                                       destination=RegisteredDestination.new_grant,
                                       grant_id=UUID(int=7),
                                       account_context={"issuer": row.issuer})
    assert details["identity"]["provider"] == "google"
    assert details["identity"]["issuer"] == row.issuer
    assert details["anti_abuse"]["idp_account_hash_key_version"] == 1
    assert details["mutation"]["destination"] == "new_grant"
    assert str(row.provider_uid) not in str(details)
    # Support context never carries a raw provider account identifier.
    with pytest.raises(FreeGrantError):
        registered_audit_details(row, alias=alias,
                                 account_context={"account": "google-account-1"})
    with pytest.raises(GrantFailureError):
        registered_audit_details(row, alias=alias, account_context={"provider_uid": "x"})
    # The success audit of a real activation carries the same details.
    _claim, activation = run_web_claim(row=row)
    assert activation.audit.details["identity"]["provider"] == "google"
    assert activation.audit.actor.issuer == row.issuer
    assert activation.audit.actor.subject_hash is None
    assert activation.audit.operation is AuthOperation.claim_registered_grant
