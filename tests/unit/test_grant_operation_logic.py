"""The operation logic of the two free-credit claims, and the device-check bypass boundary.

`claim_anonymous_grant` and `claim_registered_grant` each have an entry condition, a numbered step
sequence, a set of alternate paths, and a failure rule. This file exercises those, step by step and
outcome by outcome, against the modules that decide them.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from pydantic import SecretStr

from nativespeaker.api.auth.audit import AuthAttempt, AuthEventResult, KeyedSubjectHasher
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import (
    ChallengeRow,
    ChallengeState,
    ClaimOutcome,
    IdentityBinding,
)
from nativespeaker.api.auth.claim_endpoints import (
    ClaimEndpointError,
    anonymous_identity_shape,
    anonymous_native_vendor_tokens,
    anonymous_web_evidence,
    assert_no_attestation_material,
    assert_no_client_provider_identifier,
    assert_no_registered_device_identity_proof,
    assert_no_registered_restore_proof,
    registered_endpoint_reads_and_enforces,
    registered_identity_linked_active,
    registered_platform_proof_set,
    registered_provider_requirement,
)
from nativespeaker.api.auth.derived_identifiers import (
    HmacKey,
    IdpAccountAliasIndex,
    KeyFamily,
    KeyRing,
)
from nativespeaker.api.auth.entitlement import AccessGrantSource, AccessGrantStatus
from nativespeaker.api.auth.external_identities import (
    ExternalIdentityRow,
    IdentityState,
    NativeClaimPlatform,
    ProviderLookupFailedError,
    free_grant_available,
)
from nativespeaker.api.auth.free_grants import (
    ANONYMOUS_CLAIM_GATING,
    BYPASS_ENVIRONMENTS,
    BYPASSABLE_GATES,
    CLIENT_SELECTABLE_BYPASS_SIGNALS,
    DEVELOPMENT_FLAG_FRAMEWORKS,
    AnonymousGrantClaim,
    ClaimEvidence,
    ClaimStep,
    DeploymentEnvironment,
    FreeGrantError,
    FreeGrantRejected,
    WebGateRead,
    android_anonymous_path_available,
    anonymous_claim_gating,
    anonymous_claim_source,
    assert_challenge_valid_for_claim,
    assert_no_enrolled_key,
    device_check_bypass_enabled,
    recall_absence_alternate,
    reconfirm_claimant,
    registered_backstop,
)
from nativespeaker.api.auth.grant_admission import (
    GRANT_ADMISSION_KEYS,
    GrantAdmissionError,
    admission_rejection_leaves_challenge_unclaimed,
    anonymous_completion_admission,
)
from nativespeaker.api.auth.grant_failures import (
    ANON_FAILURES,
    ANON_SHARED_RESULTS,
    PENDING_STATE_MACHINES,
    PROTECTED_OPERATIONS,
    VENDOR_STATE_RECONCILERS,
    AnonFailureCondition,
    BurnedSlotCause,
    ClaimStepFailed,
    GrantFailureError,
    RetryableStep,
    accepted_burned_slot,
    anonymous_failure_class,
    burned_slot_retry_outcome,
    classify_anonymous_failure,
    completion_rejection,
    device_grant_exhausted_outcome,
    exhausted_alternate_path,
    grants_client_class,
    retry_claim_step,
    verification_required_outcome,
    verification_temporarily_unavailable_outcome,
)
from nativespeaker.api.auth.integration import FirebaseIntegration, FirebaseIntegrations
from nativespeaker.api.auth.invariants import (
    GateConsumptionKind,
    ProviderAccount,
    ProviderAccountGates,
)
from nativespeaker.api.auth.locks import LockingPath, LockLedger
from nativespeaker.api.auth.modes import RequestMode
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.proof_adapters import (
    AndroidClaimMaterial,
    AppleCredentials,
    ClaimRejection,
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
    TurnstileDenied,
    TurnstileUnavailable,
)
from nativespeaker.api.auth.proof_endpoints import (
    ClaimBranch,
    GateDenied,
    ProofArtifact,
    gate_lookup_unavailable,
)
from nativespeaker.api.auth.registered_grant_failures import (
    DURABLE_REGISTERED_CLASSES,
    RegClaimCondition,
    classify_registered_failure,
    registered_durable_rejection,
)
from nativespeaker.api.auth.registered_grants import (
    DEFERRED_KEY_CHECK_POINT,
    RegisteredClaimStep,
    RegisteredDestination,
    RegisteredDestinationBlocked,
    RegisteredGrantClaim,
    assert_deferred_keys_checked_at_commit,
    assert_no_device_proof_as_identity,
    assert_one_active_grant,
    confirm_stored_binding_live,
    reconfirm_registered_claimant,
    registered_grant_operation,
    registered_provider_account,
    repeated_grant_state,
    resolve_claim_kind,
    returned_grant_state,
    select_destination,
    supersession_write_order,
)
from nativespeaker.api.auth.taxonomy import ClientErrorClass, surface
from nativespeaker.api.quota.grants import GrantRow
from nativespeaker.api.quota.usage import period_of
from nativespeaker.api.ratelimit.limiter import LimitDecision
from nativespeaker.api.ratelimit.ordering import AdmissionLedger
from nativespeaker.api.ratelimit.rejection import SecurityTelemetry

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
FREE_TIER = "free_anonymous"
ISSUER = "https://securetoken.google.com/test-project"
APPLE = AppleCredentials(team_id="TEAM123456", key_id="KEY1", private_key=SecretStr("pem"))
GOOGLE = GoogleCredentials(package_name="com.nativespeaker.app",
                           service_account_email="svc@example.iam.gserviceaccount.com",
                           private_key=SecretStr("pem"))
IOS_MATERIAL = IosClaimMaterial(query_token="q-token", update_token="u-token")
ANDROID_MATERIAL = AndroidClaimMaterial(integrity_token="integrity-token")
IOS_EVIDENCE = ClaimEvidence(devicecheck_query_token="q-token", devicecheck_update_token="u-token")
ANDROID_EVIDENCE = ClaimEvidence(play_integrity_token="integrity-token")
WEB_EVIDENCE = ClaimEvidence(turnstile_token="cf-token")
IOS_VERIFIED = ("apple_team_id", "devicecheck_environment")
WEB_VERIFIED = ("hostname", "action")
ANDROID_VERIFIED = ("package_name", "signing_certificate_digest")
ENUMERATED_RELEASE = ReleaseKey(package_name="com.nativespeaker.app",
                                signing_certificate_digest="sha256:abcdef", release="1.4.0")
APP_INTEGRITY = {"packageName": ENUMERATED_RELEASE.package_name,
                 "certificateSha256Digest": [ENUMERATED_RELEASE.signing_certificate_digest],
                 "release": ENUMERATED_RELEASE.release}
RECALL_POLICY = ReleasePolicyRegistry({ENUMERATED_RELEASE:
                                       ReleaseRecallPolicy.device_recall_required})
GOOGLE_PROVIDER_DATA: list[Any] = [{"providerId": "google.com", "uid": "google-account-1"}]
SUBJECT_HASHER = KeyedSubjectHasher(key=b"s" * 32, key_version=3)
ANON_ROUTE = ("POST", "/auth/claim-anonymous-grant")


# --- fixtures and doubles -------------------------------------------------------------------------


def identity_row(**overrides: Any) -> ExternalIdentityRow:
    fields: dict[str, Any] = {"provider": IdentityProvider.anonymous, "provider_uid": None,
                              "identity_state": IdentityState.active}
    fields.update(overrides)
    return ExternalIdentityRow(id=fields.pop("row_id", None) or uuid7(),
                               user_id=fields.pop("user_id", None) or uuid7(),
                               issuer=ISSUER, subject="firebase-subject", **fields)


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


def alias_index(gates: ProviderAccountGates | None = None) -> IdpAccountAliasIndex:
    ring = KeyRing(KeyFamily.k_idp_account, current=HmacKey(version=1, secret=b"i" * 32))
    return IdpAccountAliasIndex(gates or ProviderAccountGates(), ring)


class _Verifier:
    def verify_id_token(self, token: str) -> Any:  # pragma: no cover - never called here
        raise AssertionError("the web gate verifies no token")


ADMIN_CLIENT = object()


def integrations(issuer: str = ISSUER) -> FirebaseIntegrations:
    return FirebaseIntegrations([FirebaseIntegration(issuer=issuer, project_id="test-project",
                                                    verifier=_Verifier(),
                                                    admin_client=ADMIN_CLIENT)])


def web_gate_read(row: ExternalIdentityRow,
                  *,
                  bot_check: bool = True,
                  provider_data: list[Any] | None = None,
                  issuer: str | None = None,
                  clients: list[Any] | None = None) -> WebGateRead:
    def read(client: Any) -> list[Any] | None:
        if clients is not None:
            clients.append(client)
        return GOOGLE_PROVIDER_DATA if provider_data is None else provider_data

    return WebGateRead(row=row, bot_check=lambda: bot_check, integrations=integrations(),
                       issuer=issuer if issuer is not None else row.issuer,
                       read_provider_data=read)


class FakeChallenge:
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
    def __init__(self, *, bits: dict[str, Any] | None = None, acknowledgment: Any = None):
        self.bits = {"bit0": False, "bit1": False} if bits is None else bits
        self.acknowledgment = {"acknowledged": True} if acknowledgment is None else acknowledgment
        self.updates: list[dict[str, Any]] = []

    def query_two_bits(self, *, query_token: str, team_id: str, environment: Any) -> Any:
        return self.bits

    def update_two_bits(self, *, update_token: str, team_id: str, environment: Any,
                        bits: Any) -> Any:
        self.updates.append(dict(bits))
        return self.acknowledgment


class FakePlayIntegrity:
    def __init__(self, *, verdict: Any = None):
        self.verdict = ({"appIntegrity": APP_INTEGRITY,
                         "deviceRecall": {"anonymous_device_grant_recall": False,
                                          "registered_account_grant_recall": False}}
                        if verdict is None else verdict)
        self.writes: list[dict[str, Any]] = []

    def decode_verdict(self, *, integrity_token: str, credentials: Any) -> Any:
        return self.verdict

    def write_recall(self, *, integrity_token: str, credentials: Any, state: Any,
                     value: bool) -> Any:
        self.writes.append({"state": str(state), "value": value})
        return {"confirmed": True}


def challenge_row(row: ExternalIdentityRow,
                  *,
                  operation: AuthOperation = AuthOperation.claim_anonymous_grant,
                  state: ChallengeState = ChallengeState.issued,
                  expires_at: datetime | None = None,
                  bound: UUID | None = None) -> ChallengeRow:
    return ChallengeRow(challenge_id="ch-1", operation=operation, operation_variant=None,
                        binding=IdentityBinding(
                            bound_external_identity_id=bound if bound is not None else row.id),
                        expires_at=expires_at if expires_at is not None else NOW + timedelta(
                            minutes=5),
                        state=state,
                        claim_attempt_id=None if state is ChallengeState.issued else uuid7())


def native_claim(adapter: Any,
                 material: Any,
                 evidence: ClaimEvidence,
                 verified: tuple[str, ...],
                 *,
                 row: ExternalIdentityRow | None = None,
                 challenge: FakeChallenge | None = None) -> tuple[AnonymousGrantClaim,
                                                                  ExternalIdentityRow,
                                                                  NativeClaimLedger,
                                                                  FakeChallenge]:
    """One anonymous native attempt, run up to and including the platform-gate read."""
    row = row if row is not None else identity_row()
    challenge = challenge or FakeChallenge()
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.resolve_identity(context_for(row), row)
    claim.claim_challenge(challenge)
    claim.select_branch(evidence, row, verified=verified)
    ledger = NativeClaimLedger()
    claim.read_platform_gate(native=(adapter, material, ledger))
    return claim, row, ledger, challenge


def activate_native(claim: AnonymousGrantClaim,
                    row: ExternalIdentityRow,
                    adapter: Any,
                    material: Any,
                    ledger: NativeClaimLedger,
                    challenge: FakeChallenge,
                    *,
                    identity_row: ExternalIdentityRow | None = None) -> Any:
    write = claim.write_native_bit(adapter, material, ledger=ledger)
    transaction = object()
    return claim.activate(user_id=row.user_id, grant_id=uuid7(), tier_id=FREE_TIER,
                          transaction=transaction,
                          locks=LockLedger(LockingPath.claim_anonymous_grant_completion),
                          reconfirm=lambda: True, challenge=challenge, write=write,
                          identity_row=identity_row if identity_row is not None else row,
                          now=NOW)


def web_claim(*,
              row: ExternalIdentityRow | None = None,
              index: IdpAccountAliasIndex | None = None,
              bot_check: bool = True,
              provider_data: list[Any] | None = None,
              challenge: FakeChallenge | None = None) -> tuple[AnonymousGrantClaim,
                                                               ExternalIdentityRow,
                                                               IdpAccountAliasIndex,
                                                               Any,
                                                               FakeChallenge]:
    """One anonymous web attempt, run up to and including the platform-gate read."""
    row = row if row is not None else google_row()
    index = index if index is not None else alias_index()
    challenge = challenge or FakeChallenge()
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.resolve_identity(context_for(row), row)
    claim.claim_challenge(challenge)
    claim.select_branch(WEB_EVIDENCE, row, verified=WEB_VERIFIED)
    reading = claim.read_platform_gate(
        web=web_gate_read(row, bot_check=bot_check, provider_data=provider_data), index=index)
    return claim, row, index, reading, challenge


def grant_row(source: AccessGrantSource,
              *,
              user_id: UUID | None = None,
              status: AccessGrantStatus = AccessGrantStatus.active,
              ends_at: datetime | None = None,
              grant_id: UUID | None = None) -> GrantRow:
    return GrantRow(grant_id=grant_id or uuid7(), user_id=user_id or uuid7(), tier_id=FREE_TIER,
                    source=source, status=status, starts_at=NOW - timedelta(days=1),
                    ends_at=ends_at)


def registered_claim(kind: ClaimBranch,
                     row: ExternalIdentityRow,
                     index: IdpAccountAliasIndex,
                     *,
                     provider_data: list[Any] | None = None) -> RegisteredGrantClaim:
    evidence = {ClaimBranch.native_ios: IOS_EVIDENCE,
                ClaimBranch.native_android: ANDROID_EVIDENCE,
                ClaimBranch.web: WEB_EVIDENCE}[kind]
    claim = RegisteredGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.resolve_identity(context_for(row), row)
    claim.claim_challenge(lambda: ClaimOutcome.claimed)
    claim.resolve_kind(evidence)
    claim.confirm_binding(row, provider_data or GOOGLE_PROVIDER_DATA, index)
    return claim


def registered_web_activation(*,
                              row: ExternalIdentityRow | None = None,
                              index: IdpAccountAliasIndex | None = None,
                              grants: tuple[GrantRow, ...] = (),
                              committed: tuple[AccessGrantSource, ...] = (),
                              carried_usage: tuple[str, int] | None = None) -> Any:
    row = row if row is not None else google_row()
    index = index if index is not None else alias_index()
    claim = registered_claim(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    claim.check_database_eligibility(grants=grants, committed_free_sources=committed, now=NOW)
    return claim, claim.activate(row=row, grant_id=uuid7(), tier_id=FREE_TIER, alias_index=index,
                                 transaction=object(),
                                 locks=LockLedger(LockingPath.claim_registered_grant_completion),
                                 consume_challenge=lambda: True, subject_hasher=SUBJECT_HASHER,
                                 carried_usage=carried_usage, now=NOW)


# --- `claim_anonymous_grant`: purpose and entry condition ------------------------------------------


# [utest->req~grants-anon-logic-purpose~1]
def test_the_anonymous_claim_is_one_explicit_source_gated_per_branch() -> None:
    for branch in ClaimBranch:
        assert anonymous_claim_source(branch) is AccessGrantSource.anonymous_device_grant
    # Native is gated by durable device state; web by the complete providerData stored-binding
    # check plus the bot-check gate. Nothing else gates either.
    assert anonymous_claim_gating(ClaimBranch.native_ios) == ("durable_device_state",)
    assert anonymous_claim_gating(ClaimBranch.native_android) == ("durable_device_state",)
    assert anonymous_claim_gating(ClaimBranch.web) == (
        "closed_classifier_and_stored_binding_provider_data", "bot_check_gate")
    assert set(ANONYMOUS_CLAIM_GATING) == set(ClaimBranch)
    with pytest.raises(FreeGrantError):
        anonymous_claim_gating("native_windows")  # type: ignore[arg-type]


# [utest->req~grants-anon-entry-barrier~1]
def test_the_claim_takes_the_barriers_verified_pair_and_resolved_identity() -> None:
    row = identity_row()
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    assert claim.resolve_identity(context_for(row), row) is row
    # A barrier outcome other than `linked` never reaches the claim's own rules.
    for outcome in (ResolutionOutcome.pre_auth, ResolutionOutcome.blocked_user,
                    ResolutionOutcome.historical_identity):
        other = AnonymousGrantClaim()
        other.admit(pre_consumption_passed=True, handler_admission_passed=True)
        with pytest.raises(FreeGrantRejected):
            other.resolve_identity(context_for(row, outcome), row)
    # A barrier that produced no verified pair resolves nothing here either.
    empty = AnonymousGrantClaim()
    empty.admit(pre_consumption_passed=True, handler_admission_passed=True)
    with pytest.raises(FreeGrantError):
        empty.resolve_identity(
            VerifiedIdentityContext(issuer="", subject="", outcome=ResolutionOutcome.linked), row)


# [utest->req~grants-anon-entry-identity-classification~1]
def test_the_stored_provider_alone_classifies_the_claimant_on_each_path() -> None:
    # Native: an anonymous identity, or a registered one whose stored provider is google/apple.
    for branch in (ClaimBranch.native_ios, ClaimBranch.native_android):
        assert anonymous_identity_shape(identity_row(), branch) is IdentityProvider.anonymous
        assert anonymous_identity_shape(google_row(), branch) is IdentityProvider.google
    # Web: a registered identity with a stored provider and a stored provider_uid.
    assert anonymous_identity_shape(google_row(), ClaimBranch.web) is IdentityProvider.google
    # The only row shape that stores no `provider_uid` is the anonymous one, and web refuses it:
    # the web alias has nothing to derive from without a stored provider account identifier.
    with pytest.raises(FreeGrantRejected):
        anonymous_identity_shape(identity_row(), ClaimBranch.web)
    # A historical identity is refused on every path.
    with pytest.raises(ClaimEndpointError):
        anonymous_identity_shape(google_row(identity_state=IdentityState.historical),
                                 ClaimBranch.web)
    # `registered_at` is not an eligibility input.
    with pytest.raises(ClaimEndpointError):
        anonymous_identity_shape(google_row(), ClaimBranch.web, consulted=("registered_at",))


# [utest->req~grants-anon-entry-no-restore-proof~1]
def test_the_anonymous_claim_request_carries_no_restore_proof() -> None:
    assert_no_attestation_material({"devicecheck_query_token": "q"})
    with pytest.raises(ClaimEndpointError) as refused:
        assert_no_attestation_material({"restore_proof": {"store": "apple"}})
    assert "restore_proof" in str(refused.value)


# [utest->req~grants-anon-entry-challenge-valid~1]
def test_the_challenge_must_be_valid_for_this_operation_before_it_is_claimed() -> None:
    row = identity_row()
    context = context_for(row)
    assert assert_challenge_valid_for_claim(challenge_row(row), context, now=NOW).challenge_id \
        == "ch-1"
    cases = {
        AuthEventResult.challenge_operation_mismatch:
            challenge_row(row, operation=AuthOperation.claim_registered_grant),
        AuthEventResult.challenge_identity_mismatch: challenge_row(row, bound=uuid7()),
        AuthEventResult.challenge_consumed: challenge_row(row, state=ChallengeState.claimed),
        AuthEventResult.challenge_expired:
            challenge_row(row, expires_at=NOW - timedelta(seconds=1)),
    }
    for result, presented in cases.items():
        with pytest.raises(FreeGrantRejected) as refused:
            assert_challenge_valid_for_claim(presented, context, now=NOW)
        assert refused.value.result is result
        assert refused.value.error_code == "challenge_required"
    # The mismatching cases reject before the claim, so nothing is claimed or consumed.
    challenge = FakeChallenge()
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.resolve_identity(context, row)
    with pytest.raises(FreeGrantRejected):
        claim.claim_challenge(challenge,
                              row=challenge_row(row,
                                                operation=AuthOperation.claim_registered_grant),
                              context=context, now=NOW)
    assert (challenge.claims, challenge.consumes) == (0, 0)
    assert ClaimStep.challenge_claim not in claim.steps


# [utest->req~grants-anon-entry-vendor-material~1]
def test_each_branch_supplies_its_own_untrusted_vendor_material() -> None:
    ios = anonymous_native_vendor_tokens(ClaimBranch.native_ios)
    assert ios == {ProofArtifact.devicecheck_query_token, ProofArtifact.devicecheck_update_token}
    android = anonymous_native_vendor_tokens(ClaimBranch.native_android)
    assert android == {ProofArtifact.play_integrity_verdict}
    with pytest.raises(ClaimEndpointError):
        anonymous_native_vendor_tokens(ClaimBranch.web)
    # Web supplies bot-check evidence only; the sign-in half is read from providerData.
    row = google_row()
    account = anonymous_web_evidence(web_gate_read(row),
                                     body_evidence=(ProofArtifact.turnstile_token,))
    assert account.canonical_provider_account_id == "google-account-1"
    with pytest.raises(ClaimEndpointError):
        anonymous_web_evidence(web_gate_read(row),
                               body_evidence=(ProofArtifact.turnstile_token,
                                              ProofArtifact.devicecheck_query_token))


# [utest->req~grants-anon-entry-no-app-attest~1]
def test_no_app_attest_enrolled_key_or_android_pre_rejection_applies() -> None:
    assert_no_enrolled_key()
    for offered in ("app_attest_assertion", "attestation_key_proof", "enrolled_key_proof"):
        with pytest.raises(ClaimEndpointError):
            assert_no_attestation_material({offered: "x"})
    with pytest.raises(FreeGrantError):
        assert_no_enrolled_key(participants=("app_attest_key",))
    with pytest.raises(FreeGrantError):
        assert_no_enrolled_key(uniqueness_rows=("attestation_key_uniqueness",))
    # Where Device Recall is available the Android path is not pre-rejected.
    assert android_anonymous_path_available(device_recall_available=True) is True
    transport = FakePlayIntegrity()
    adapter = PlayIntegrityAdapter(GOOGLE, transport, release_policy=RECALL_POLICY)
    claim, row, ledger, challenge = native_claim(adapter, ANDROID_MATERIAL, ANDROID_EVIDENCE,
                                                 ANDROID_VERIFIED)
    claim.check_database_eligibility(committed_free_sources=(), ledger=ledger)
    activated = activate_native(claim, row, adapter, ANDROID_MATERIAL, ledger, challenge)
    assert activated.grant["source"] is AccessGrantSource.anonymous_device_grant


# [utest->req~grants-anon-logic-admission-applies~1]
def test_the_handler_side_admission_limits_apply_to_this_operation() -> None:
    ledger = AdmissionLedger(*ANON_ROUTE, mode=RequestMode.completion)
    ledger.verify_jwt()
    ledger.admit_barrier()
    ip_entry, user_entry = anonymous_completion_admission(ledger, identity_resolved=True)
    assert GRANT_ADMISSION_KEYS[user_entry]
    assert set(ledger.evaluated) >= {ip_entry, user_entry}
    # Admission runs after identity resolution and before every expensive step.
    fresh = AdmissionLedger(*ANON_ROUTE, mode=RequestMode.completion)
    fresh.verify_jwt()
    fresh.admit_barrier()
    with pytest.raises(GrantAdmissionError):
        anonymous_completion_admission(fresh, identity_resolved=False)
    # Its rejection behaviour is 08's, and it leaves the challenge unclaimed.
    decision = LimitDecision(allowed=False, limiter=user_entry, retry_after_seconds=30)
    rejection = admission_rejection_leaves_challenge_unclaimed(
        AuthAttempt(*ANON_ROUTE), SecurityTelemetry(), decision)
    assert rejection.challenge_state is ChallengeState.issued
    assert rejection.audit_rows == 0
    with pytest.raises(GrantAdmissionError):
        admission_rejection_leaves_challenge_unclaimed(
            AuthAttempt(*ANON_ROUTE), SecurityTelemetry(), decision,
            challenge_state=ChallengeState.claimed)


# --- `claim_anonymous_grant`: the numbered steps ---------------------------------------------------


# [utest->req~grants-anon-step-01-resolve-identity~1]
def test_step_01_resolves_the_identity_and_enforces_the_pinned_platform() -> None:
    # A first verified attestation pins the platform in the activation transaction.
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    claim, row, ledger, challenge = native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
    claim.check_database_eligibility(committed_free_sources=(), ledger=ledger)
    activated = activate_native(claim, row, adapter, IOS_MATERIAL, ledger, challenge)
    assert activated.identity is not None
    assert activated.identity.native_claim_platform is NativeClaimPlatform.ios_devicecheck
    # Material from the other platform is rejected once the identity is pinned.
    pinned = identity_row(native_claim_platform=NativeClaimPlatform.android_play_integrity)
    other = AnonymousGrantClaim()
    other.admit(pre_consumption_passed=True, handler_admission_passed=True)
    other.resolve_identity(context_for(pinned), pinned)
    other.claim_challenge(FakeChallenge())
    with pytest.raises(FreeGrantRejected) as refused:
        other.select_branch(IOS_EVIDENCE, pinned, verified=IOS_VERIFIED)
    assert refused.value.error_code == "operation_not_allowed"
    # An anonymous identity may not take the web branch at all.
    web = AnonymousGrantClaim()
    web.admit(pre_consumption_passed=True, handler_admission_passed=True)
    anon = identity_row()
    web.resolve_identity(context_for(anon), anon)
    web.claim_challenge(FakeChallenge())
    with pytest.raises(FreeGrantRejected):
        web.select_branch(WEB_EVIDENCE, anon, verified=WEB_VERIFIED)


# [utest->req~grants-anon-step-02-read-platform-gate~1]
def test_step_02_reads_the_branch_gate_only_after_the_claim() -> None:
    # The gate read cannot run before the branch was selected, which follows the claim.
    early = AnonymousGrantClaim()
    early.admit(pre_consumption_passed=True, handler_admission_passed=True)
    row = identity_row()
    early.resolve_identity(context_for(row), row)
    early.claim_challenge(FakeChallenge())
    with pytest.raises(FreeGrantError):
        early.read_platform_gate(native=(DeviceCheckAdapter(APPLE, FakeDeviceCheck()),
                                         IOS_MATERIAL, NativeClaimLedger()))
    # iOS requires both tokens up front and queries the anonymous-claimed bit.
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    claim, _, ledger, _ = native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
    assert ClaimStep.platform_gate in claim.steps
    with pytest.raises(ProofRejected):
        DeviceCheckAdapter(APPLE, FakeDeviceCheck()).verify_material(
            AuthOperation.claim_anonymous_grant,
            IosClaimMaterial(query_token="q", update_token=""), NativeClaimLedger())
    # Web selects the Admin client by the request's verified issuer and derives from the sole entry.
    clients: list[Any] = []
    google = google_row()
    web = AnonymousGrantClaim()
    web.admit(pre_consumption_passed=True, handler_admission_passed=True)
    web.resolve_identity(context_for(google), google)
    web.claim_challenge(FakeChallenge())
    web.select_branch(WEB_EVIDENCE, google, verified=WEB_VERIFIED)
    reading = web.read_platform_gate(web=web_gate_read(google, clients=clients),
                                     index=alias_index())
    assert clients == [ADMIN_CLIENT]
    assert reading.web_account is not None
    assert reading.web_account.provider is IdentityProvider.google
    # An extra or unrecognized entry rejects rather than being ignored — no preference order.
    for provider_data in ([{"providerId": "google.com", "uid": "google-account-1"},
                           {"providerId": "apple.com", "uid": "apple-account-1"}],
                          [{"providerId": "google.com", "uid": "google-account-1"},
                           {"providerId": "phone", "uid": "+15550100"}],
                          [{"providerId": "google.com", "uid": "other-account"}]):
        with pytest.raises(GateDenied):
            web_claim(row=google_row(), provider_data=provider_data)


# [utest->req~grants-anon-step-03-gate-state-and-dependencies~1]
def test_step_03_maps_every_gate_state_and_dependency_outcome() -> None:
    # An already-set native bit audits its own result and rejects as device_grant_exhausted.
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck(bits={"bit0": True, "bit1": False}))
    with pytest.raises(DeviceGrantExhausted):
        native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
    exhausted = classify_anonymous_failure(AnonFailureCondition.ios_anonymous_bit_set)
    assert exhausted.result is AuthEventResult.native_claim_already_claimed
    assert exhausted.client_class is ClientErrorClass.device_grant_exhausted
    # A verdict lacking Device Recall is proof_rejected, with the registered path as alternate.
    no_recall = FakePlayIntegrity(verdict={"appIntegrity": APP_INTEGRITY})
    with pytest.raises(ProofRejected):
        native_claim(PlayIntegrityAdapter(GOOGLE, no_recall, release_policy=RECALL_POLICY), ANDROID_MATERIAL,
                     ANDROID_EVIDENCE, ANDROID_VERIFIED)
    assert recall_absence_alternate() is AuthOperation.claim_registered_grant
    # A retryable dependency failure is retried twice more, then rejects as VTU.
    attempts: list[int] = []

    def flaky(spent: int) -> str:
        attempts.append(spent)
        if spent < 3:
            raise ClaimStepFailed(RetryableStep.web_firebase_provider_data, retryable=True)
        return "read"

    assert retry_claim_step(RetryableStep.web_firebase_provider_data, flaky).attempts == 3
    assert attempts == [1, 2, 3]

    def always_down(_spent: int) -> str:
        raise ClaimStepFailed(RetryableStep.cloudflare_validation, retryable=True)

    with pytest.raises(ClaimRejection) as spent:
        retry_claim_step(RetryableStep.cloudflare_validation, always_down)
    assert spent.value.error_code == ClientErrorClass.verification_temporarily_unavailable
    # A durable vendor read denial, a Cloudflare denial and a completed web lookup with no
    # stored-binding match all follow the durable verification_required path.
    for condition in (AnonFailureCondition.device_check_read_denied,
                      AnonFailureCondition.cloudflare_bot_check_denied,
                      AnonFailureCondition.web_stored_binding_mismatch):
        outcome = verification_required_outcome(condition)
        assert outcome.client_class is ClientErrorClass.verification_required
        assert outcome.durable is True
    with pytest.raises(GateDenied):
        web_claim(bot_check=False)


# [utest->req~grants-anon-step-04-db-eligibility~1]
def test_step_04_checks_the_marker_and_the_history_before_any_slot_is_burned() -> None:
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    # A set free-grant-consumed marker refuses the claim, and no bit is written.
    consumed = identity_row(free_grant_consumed_at=NOW - timedelta(days=30))
    claim, _, ledger, _ = native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED,
                                       row=consumed)
    with pytest.raises(ClaimRejection) as refused:
        claim.check_database_eligibility(committed_free_sources=(), identity=consumed,
                                         ledger=ledger)
    assert refused.value.result is AuthEventResult.anti_abuse_already_claimed
    assert transport.updates == []
    # Any committed free grant of either source refuses it too.
    for source in (AccessGrantSource.anonymous_device_grant,
                   AccessGrantSource.registered_account_grant):
        held, _, held_ledger, _ = native_claim(DeviceCheckAdapter(APPLE, FakeDeviceCheck()),
                                               IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
        with pytest.raises(ClaimRejection):
            held.check_database_eligibility(committed_free_sources=(source,), ledger=held_ledger)
    # An existing *active* anonymous grant takes the specific active-grant invariant path, and is
    # never an idempotent success.
    active, _, active_ledger, _ = native_claim(DeviceCheckAdapter(APPLE, FakeDeviceCheck()),
                                               IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
    with pytest.raises(FreeGrantRejected) as invariant:
        active.check_database_eligibility(
            committed_free_sources=(),
            active_sources=(AccessGrantSource.anonymous_device_grant,),
            ledger=active_ledger)
    assert invariant.value.result is AuthEventResult.policy_rejected
    assert invariant.value.error_code == "operation_not_allowed"
    # The gate read comes first: no database grant may suppress it.
    unread = AnonymousGrantClaim()
    unread.admit(pre_consumption_passed=True, handler_admission_passed=True)
    row = identity_row()
    unread.resolve_identity(context_for(row), row)
    unread.claim_challenge(FakeChallenge())
    unread.select_branch(IOS_EVIDENCE, row, verified=IOS_VERIFIED)
    with pytest.raises(FreeGrantError):
        unread.check_database_eligibility(committed_free_sources=())


# [utest->req~grants-anon-step-05-write-bit~1]
def test_step_05_writes_the_bit_before_activation_and_never_grants_around_it() -> None:
    transport = FakeDeviceCheck()
    adapter = DeviceCheckAdapter(APPLE, transport)
    claim, row, ledger, challenge = native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
    claim.check_database_eligibility(committed_free_sources=(), ledger=ledger)
    write = claim.write_native_bit(adapter, IOS_MATERIAL, ledger=ledger)
    assert write.confirmed is True
    assert transport.updates == [{"bit0": True}]
    # An ambiguous acknowledgment refuses with no grant.
    ambiguous = DeviceCheckAdapter(APPLE, FakeDeviceCheck(acknowledgment={}))
    other, _, other_ledger, other_challenge = native_claim(ambiguous, IOS_MATERIAL, IOS_EVIDENCE,
                                                           IOS_VERIFIED)
    other.check_database_eligibility(committed_free_sources=(), ledger=other_ledger)
    with pytest.raises(ClaimRejection):
        other.write_native_bit(ambiguous, IOS_MATERIAL, ledger=other_ledger)
    assert other_challenge.consumes == 0
    # Only a native branch writes a bit, and only after the eligibility preflight.
    web_claim_obj, _, _, _, _ = web_claim()
    web_claim_obj.check_database_eligibility(committed_free_sources=())
    with pytest.raises(FreeGrantError):
        web_claim_obj.write_native_bit(adapter, IOS_MATERIAL, ledger=NativeClaimLedger())


# [utest->req~grants-anon-step-06-activation-transaction~1]
def test_step_06_locks_and_reconfirms_the_claimant_under_the_lock() -> None:
    assert reconfirm_claimant(identity_row(), ClaimBranch.native_ios).provider \
        is IdentityProvider.anonymous
    # A historical identity, a set marker, and a pin mismatch each refuse inside the transaction.
    with pytest.raises(ClaimRejection) as historical:
        reconfirm_claimant(identity_row(identity_state=IdentityState.historical),
                           ClaimBranch.native_ios)
    assert historical.value.result is AuthEventResult.historical_identity
    with pytest.raises(ClaimRejection) as marked:
        reconfirm_claimant(identity_row(free_grant_consumed_at=NOW), ClaimBranch.native_ios)
    assert marked.value.result is AuthEventResult.anti_abuse_already_claimed
    with pytest.raises(FreeGrantRejected):
        reconfirm_claimant(
            identity_row(native_claim_platform=NativeClaimPlatform.android_play_integrity),
            ClaimBranch.native_ios)
    # A registered claimant must still carry the stored binding the gate used.
    _, _, _, reading, _ = web_claim()
    google = google_row()
    assert reconfirm_claimant(google, ClaimBranch.web,
                              web_account=reading.web_account) is google
    diverged = google_row(provider_uid="google-account-2")
    with pytest.raises(FreeGrantRejected) as mismatch:
        reconfirm_claimant(diverged, ClaimBranch.web, web_account=reading.web_account)
    assert mismatch.value.error_code == "verification_required"
    # `registered_at` is not consulted by the reconfirmation.
    with pytest.raises(FreeGrantError):
        reconfirm_claimant(google, ClaimBranch.web, web_account=reading.web_account,
                           consulted=("registered_at",))
    # The whole activation refuses when the reconfirmation fails, and consumes the claim.
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    claim, row, ledger, challenge = native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
    claim.check_database_eligibility(committed_free_sources=(), ledger=ledger)
    with pytest.raises(ClaimRejection):
        activate_native(claim, row, adapter, IOS_MATERIAL, ledger, challenge,
                        identity_row=replace(row, free_grant_consumed_at=NOW))
    assert challenge.consumes == 1


# [utest->req~grants-anon-step-07-insert-rows~1]
def test_step_07_writes_every_row_sets_the_marker_and_maps_the_gate_conflict() -> None:
    index = alias_index()
    claim, row, index, reading, challenge = web_claim(index=index)
    claim.check_database_eligibility(committed_free_sources=())
    transaction = object()
    activated = claim.activate(user_id=row.user_id, grant_id=uuid7(), tier_id=FREE_TIER,
                               transaction=transaction,
                               locks=LockLedger(LockingPath.claim_anonymous_grant_completion),
                               reconfirm=lambda: True, challenge=challenge,
                               web_account=reading.web_account, index=index, identity_row=row,
                               now=NOW)
    assert activated.grant["source"] is AccessGrantSource.anonymous_device_grant
    assert activated.grant["tier_id"] == FREE_TIER
    assert activated.anti_abuse["idp_account_hash"] is not None
    assert activated.anti_abuse["idp_account_hash_key_version"] == 1
    assert activated.usage.grant_id == activated.grant["id"]
    assert challenge.consumes == 1
    assert activated.audit.result is AuthEventResult.succeeded
    assert activated.audit.details["verification"]["platform"] == "web_signin_plus_cloudflare_" \
                                                                 "bot_check"
    # The canonical provider account row and the web_anonymous_gate consumption row both exist.
    account = ProviderAccount(provider=IdentityProvider.google, provider_uid="google-account-1")
    assert index.consumed(account, GateConsumptionKind.web_anonymous_gate) \
        == activated.grant["id"]
    # The claimant identity's permanent free-grant-consumed marker is set in this transaction.
    assert activated.identity is not None
    assert activated.identity.free_grant_consumed_at == NOW
    assert free_grant_available(activated.identity, AuthOperation.claim_anonymous_grant) is False
    # A second attempt whose gate read passed but which loses the race conflicts on the stable
    # provider UID inside its own transaction: anti_abuse_already_claimed surfacing as
    # device_grant_exhausted, never account_already_claimed.
    second_row = google_row()
    race = alias_index()
    second, _, _, second_reading, second_challenge = web_claim(row=second_row, index=race)
    second.check_database_eligibility(committed_free_sources=())
    # The winner commits between this attempt's gate read and its transaction.
    race.consume(account, GateConsumptionKind.web_anonymous_gate, uuid7())
    with pytest.raises(ClaimRejection) as conflict:
        second.activate(user_id=second_row.user_id, grant_id=uuid7(), tier_id=FREE_TIER,
                        transaction=object(),
                        locks=LockLedger(LockingPath.claim_anonymous_grant_completion),
                        reconfirm=lambda: True, challenge=second_challenge,
                        web_account=second_reading.web_account, index=race,
                        identity_row=second_row, now=NOW)
    assert conflict.value.result is AuthEventResult.anti_abuse_already_claimed
    assert conflict.value.error_code == ClientErrorClass.device_grant_exhausted
    assert conflict.value.error_code != ClientErrorClass.account_already_claimed
    assert second_challenge.consumes == 1


# [utest->req~grants-anon-step-08-crash-outcomes~1]
def test_step_08_accepts_the_burned_slot_and_never_repairs_it() -> None:
    for cause in (BurnedSlotCause.crash_after_confirmed_write,
                  BurnedSlotCause.lost_or_ambiguous_write_acknowledgment,
                  BurnedSlotCause.comparable_operational_failure):
        assert accepted_burned_slot(cause, write_confirmed=True,
                                    grant_activated=False) is AccessGrantSource.manual
    # An unconfirmed write burns nothing, and a burned slot never coexists with a grant.
    with pytest.raises(GrantFailureError):
        accepted_burned_slot(BurnedSlotCause.crash_after_confirmed_write, write_confirmed=False,
                             grant_activated=False)
    with pytest.raises(GrantFailureError):
        accepted_burned_slot(BurnedSlotCause.crash_after_confirmed_write, write_confirmed=True,
                             grant_activated=True)
    # A whole-claim retry with fresh material reads the set bit and returns device_grant_exhausted.
    for branch in (ClaimBranch.native_ios, ClaimBranch.native_android):
        outcome = burned_slot_retry_outcome(branch)
        assert outcome.client_class is ClientErrorClass.device_grant_exhausted
        assert outcome.durable is True
    # There is no pending-state machine and nothing reconciles vendor state from the database.
    assert PENDING_STATE_MACHINES == frozenset()
    assert VENDOR_STATE_RECONCILERS == frozenset()
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    claim, _, ledger, _ = native_claim(adapter, IOS_MATERIAL, IOS_EVIDENCE, IOS_VERIFIED)
    with pytest.raises(FreeGrantError):
        claim.check_database_eligibility(committed_free_sources=(), reconcile_vendor_state=True,
                                         ledger=ledger)


# --- `claim_anonymous_grant`: alternate paths and the failure rule ---------------------------------


# [utest->req~grants-anon-alt-exhausted-to-registered~1]
def test_an_exhausted_device_or_web_gate_sends_the_client_to_the_registered_claim() -> None:
    for condition in (AnonFailureCondition.ios_anonymous_bit_set,
                      AnonFailureCondition.android_recall_anonymous_state_set,
                      AnonFailureCondition.web_gate_already_consumed):
        outcome = device_grant_exhausted_outcome(condition)
        assert outcome.client_class is ClientErrorClass.device_grant_exhausted
        assert outcome.next_route == "/auth/claim-registered-grant"
    assert exhausted_alternate_path(google_row(), active_grant_source=None) \
        is AuthOperation.claim_registered_grant
    # The alternate needs a google or apple identity to be reachable at all.
    with pytest.raises(FreeGrantRejected):
        exhausted_alternate_path(identity_row(), active_grant_source=None)


# [utest->req~grants-anon-alt-proof-rejected-to-registered~1]
def test_a_proof_rejected_claimant_takes_the_same_registered_alternate() -> None:
    assert recall_absence_alternate() is AuthOperation.claim_registered_grant
    proof = classify_anonymous_failure(AnonFailureCondition.client_proof_missing_or_malformed)
    assert proof.client_class is ClientErrorClass.proof_rejected
    # Withheld material and a verdict lacking Device Recall are the same outcome: the backend
    # never distinguishes absent capability from a withheld token.
    withheld = FakePlayIntegrity(verdict={"appIntegrity": APP_INTEGRITY})
    with pytest.raises(ProofRejected):
        native_claim(PlayIntegrityAdapter(GOOGLE, withheld, release_policy=RECALL_POLICY), ANDROID_MATERIAL,
                     ANDROID_EVIDENCE, ANDROID_VERIFIED)
    # A partial evidence set is the same client-visible class, as a request-shape error.
    claim = AnonymousGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    row = identity_row()
    claim.resolve_identity(context_for(row), row)
    claim.claim_challenge(FakeChallenge())
    with pytest.raises(FreeGrantRejected) as partial:
        claim.select_branch(ClaimEvidence(devicecheck_query_token="q"), row, verified=IOS_VERIFIED)
    assert partial.value.error_code == "proof_rejected"


# [utest->req~grants-anon-alt-not-guaranteed~1]
def test_the_registered_alternate_has_its_own_gates_and_no_guarantee() -> None:
    assert registered_backstop(google_row(), active_grant_source=None) \
        is AuthOperation.claim_registered_grant
    # It refuses outright where its own gates are unsatisfied, so it is a path, not a promise.
    with pytest.raises(FreeGrantRejected):
        registered_backstop(identity_row(), active_grant_source=None)
    with pytest.raises(FreeGrantRejected) as blocked:
        registered_backstop(google_row(), active_grant_source=AccessGrantSource.subscription)
    assert blocked.value.error_code == "operation_not_allowed"
    exhausted = device_grant_exhausted_outcome(AnonFailureCondition.web_gate_already_consumed)
    assert exhausted.guaranteed_alternate is False


# [utest->req~grants-anon-alt-verification-required-no-alternate~1]
def test_verification_required_promises_no_free_credit_alternate() -> None:
    for condition in (AnonFailureCondition.device_check_read_denied,
                      AnonFailureCondition.anonymous_grant_policy_rejected,
                      AnonFailureCondition.web_stored_binding_mismatch,
                      AnonFailureCondition.cloudflare_bot_check_denied):
        outcome = verification_required_outcome(condition)
        assert outcome.guaranteed_alternate is False
        assert outcome.next_route is None
        assert outcome.durable is True
    # A retryable dependency failure is not this class.
    with pytest.raises(GrantFailureError):
        verification_required_outcome(AnonFailureCondition.firebase_provider_data_unavailable)


# [utest->req~grants-anon-failure-rejection-conditions~1]
def test_the_rejection_conditions_cover_every_named_cause() -> None:
    required = {
        AnonFailureCondition.client_proof_missing_or_malformed,
        AnonFailureCondition.cloudflare_bot_check_denied,
        AnonFailureCondition.web_stored_binding_mismatch,
        AnonFailureCondition.firebase_provider_data_unavailable,
        AnonFailureCondition.web_gate_already_consumed,
        AnonFailureCondition.ios_anonymous_bit_set,
        AnonFailureCondition.android_recall_anonymous_state_set,
        AnonFailureCondition.device_check_read_denied,
        AnonFailureCondition.device_state_write_failed,
        AnonFailureCondition.devicecheck_read_unavailable,
        AnonFailureCondition.play_integrity_recall_read_unavailable,
        AnonFailureCondition.anonymous_grant_policy_rejected,
    }
    assert required <= set(ANON_FAILURES)
    for condition in required:
        assert classify_anonymous_failure(condition).client_class in {
            ClientErrorClass.proof_rejected, ClientErrorClass.verification_required,
            ClientErrorClass.device_grant_exhausted,
            ClientErrorClass.verification_temporarily_unavailable}
    # An active-grant invariant violation is a rejection condition too, under its own class.
    assert grants_client_class(AuthEventResult.policy_rejected,
                               operation=AuthOperation.claim_anonymous_grant,
                               structural=True) is ClientErrorClass.operation_not_allowed


# [utest->req~grants-anon-failure-class-mapping~1]
def test_every_internal_result_maps_to_its_one_client_visible_class() -> None:
    anonymous = AuthOperation.claim_anonymous_grant
    # auth_required covers external token acceptance failure, and — the fold point — the
    # non-retryable Firebase `user-not-found` at the required web read.
    assert grants_client_class(AuthEventResult.invalid_external_jwt,
                               operation=anonymous) is ClientErrorClass.auth_required
    not_found = ProviderLookupFailedError(AuthEventResult.firebase_user_unresolved,
                                          ClientErrorClass.auth_required, retryable=False)
    returned = gate_lookup_unavailable(not_found)
    assert returned.result is AuthEventResult.firebase_user_unresolved
    assert returned.client_class is ClientErrorClass.auth_required
    assert returned.retryable is False
    assert grants_client_class(AuthEventResult.firebase_user_unresolved,
                               operation=anonymous) is ClientErrorClass.auth_required
    # A lookup with no failure object is the transient default instead.
    assert gate_lookup_unavailable(None).client_class \
        is ClientErrorClass.verification_temporarily_unavailable
    # The rest of the mapping, class by class.
    assert grants_client_class(AuthEventResult.preauth_identity_not_allowed,
                               operation=anonymous) is ClientErrorClass.preauth_identity_not_allowed
    for result in (AuthEventResult.blocked_user, AuthEventResult.historical_identity):
        assert grants_client_class(result, operation=anonymous) \
            is ClientErrorClass.account_unavailable
    for result in (AuthEventResult.challenge_not_found, AuthEventResult.challenge_expired,
                   AuthEventResult.challenge_consumed,
                   AuthEventResult.challenge_identity_mismatch,
                   AuthEventResult.challenge_operation_mismatch):
        assert grants_client_class(result, operation=anonymous) \
            is ClientErrorClass.challenge_required
    assert grants_client_class(AuthEventResult.proof_malformed,
                               operation=anonymous) is ClientErrorClass.proof_rejected
    assert grants_client_class(AuthEventResult.policy_rejected, operation=anonymous,
                               structural=True) is ClientErrorClass.operation_not_allowed
    for result in (AuthEventResult.native_claim_already_claimed,
                   AuthEventResult.anti_abuse_already_claimed):
        assert grants_client_class(result, operation=anonymous) \
            is ClientErrorClass.device_grant_exhausted
    assert grants_client_class(AuthEventResult.policy_rejected,
                               operation=anonymous) is ClientErrorClass.verification_required
    for result in (AuthEventResult.native_claim_unavailable,
                   AuthEventResult.native_claim_write_failed,
                   AuthEventResult.firebase_lookup_unavailable,
                   AuthEventResult.devicecheck_read_budget_exhausted,
                   AuthEventResult.devicecheck_write_budget_exhausted,
                   AuthEventResult.device_recall_read_budget_exhausted,
                   AuthEventResult.device_recall_write_budget_exhausted,
                   AuthEventResult.verification_temporarily_unavailable):
        assert grants_client_class(result, operation=anonymous) \
            is ClientErrorClass.verification_temporarily_unavailable
    # A Cloudflare dependency failure records the class value itself as its audited result.
    turnstile = classify_anonymous_failure(AnonFailureCondition.cloudflare_dependency_failed)
    assert turnstile.result is AuthEventResult.verification_temporarily_unavailable
    # Every condition's declared class agrees with the shared registry.
    for condition in ANON_FAILURES:
        assert anonymous_failure_class(condition) is ANON_FAILURES[condition].client_class


# [utest->req~grants-anon-audit-specific-internal-result~1]
def test_the_audit_row_records_the_specific_internal_result() -> None:
    for result in (AuthEventResult.native_claim_already_claimed,
                   AuthEventResult.anti_abuse_already_claimed,
                   AuthEventResult.native_claim_write_failed,
                   AuthEventResult.firebase_lookup_unavailable):
        rejection = completion_rejection(result,
                                         operation=AuthOperation.claim_anonymous_grant)
        # The audited value is the specific result, and it never reaches the client body.
        assert rejection.audit_result is result
        assert str(result) not in set(rejection.body.values())
        # It is never less specific than the class returned.
        assert str(result) != str(rejection.client_class)
    # The shared results the claim can also audit stay specific under their shared classes.
    for shared in ANON_SHARED_RESULTS:
        client_class, _status = surface(shared)
        assert client_class


# [utest->req~grants-anon-taxonomy-shared-never-blocks-paid~1]
def test_the_taxonomy_is_shared_and_fail_closed_handling_blocks_no_paid_path() -> None:
    # The same taxonomy governs every auth completion endpoint.
    for operation in (AuthOperation.create_user, AuthOperation.upgrade_anonymous_to_registered,
                      AuthOperation.claim_anonymous_grant, AuthOperation.claim_registered_grant):
        assert grants_client_class(AuthEventResult.challenge_expired, operation=operation) \
            is ClientErrorClass.challenge_required
    assert PROTECTED_OPERATIONS == frozenset({AuthOperation.create_user,
                                              AuthOperation.upgrade_anonymous_to_registered,
                                              AuthOperation.sync,
                                              AuthOperation.restore_subscription})
    outcome = verification_temporarily_unavailable_outcome(
        AnonFailureCondition.firebase_provider_data_unavailable)
    assert outcome.client_class is ClientErrorClass.verification_temporarily_unavailable
    for protected in PROTECTED_OPERATIONS:
        with pytest.raises(GrantFailureError):
            verification_temporarily_unavailable_outcome(
                AnonFailureCondition.firebase_provider_data_unavailable, blocks=(protected,))


# --- `claim_registered_grant`: purpose and entry condition -----------------------------------------


# [utest->req~grants-reg-logic-purpose~1]
def test_the_registered_claim_produces_or_converts_to_its_own_source() -> None:
    definition = registered_grant_operation()
    assert definition.source is AccessGrantSource.registered_account_grant
    assert definition.gate_kind is GateConsumptionKind.registered_account_grant
    assert definition.convertible_source is AccessGrantSource.anonymous_device_grant
    assert set(definition.gates) == {"user_own_grant_history", "stored_provider_classification",
                                     "registered_account_grant_gate_consumption"}
    _claim, created = registered_web_activation()
    assert created.grant["source"] is AccessGrantSource.registered_account_grant
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    _claim, converted = registered_web_activation(
        grants=(anonymous,), committed=(AccessGrantSource.anonymous_device_grant,),
        carried_usage=("2026-08", 7))
    assert converted.destination is RegisteredDestination.supersession_conversion
    assert converted.grant["source"] is AccessGrantSource.registered_account_grant


# [utest->req~grants-reg-entry-barrier~1]
def test_the_registered_entry_needs_a_linked_active_identity_and_active_user() -> None:
    row = google_row()
    assert registered_identity_linked_active(context_for(row), row, user_active=True) is row
    with pytest.raises(ClaimEndpointError):
        registered_identity_linked_active(context_for(row, ResolutionOutcome.pre_auth), row,
                                          user_active=True)
    with pytest.raises(ClaimEndpointError):
        registered_identity_linked_active(context_for(row), row, user_active=False)
    historical = google_row(identity_state=IdentityState.historical)
    with pytest.raises(ClaimEndpointError):
        registered_identity_linked_active(context_for(historical), historical, user_active=True)


# [utest->req~grants-reg-entry-provider~1]
def test_the_registered_entry_needs_a_google_or_apple_stored_provider() -> None:
    for provider in (IdentityProvider.google, IdentityProvider.apple):
        row = google_row(provider=provider, provider_uid="account-1")
        assert registered_provider_requirement(row) is provider
    with pytest.raises(FreeGrantRejected) as refused:
        registered_provider_requirement(identity_row())
    assert refused.value.result is AuthEventResult.idp_account_not_eligible
    assert refused.value.error_code == "verification_required"


# [utest->req~grants-reg-entry-provider-uid~1]
def test_the_registered_entry_needs_a_stored_provider_uid() -> None:
    row = google_row()
    assert registered_provider_account(row).provider_uid == "google-account-1"
    # The row shape that stores no `provider_uid` is the anonymous one; it is not eligible.
    uidless = identity_row()
    with pytest.raises(FreeGrantRejected) as refused:
        registered_provider_account(uidless)
    assert refused.value.result is AuthEventResult.idp_account_not_eligible
    with pytest.raises(FreeGrantRejected):
        registered_endpoint_reads_and_enforces(uidless, alias_index())


# [utest->req~grants-reg-entry-mandatory-confirmation~1]
def test_every_registered_branch_performs_the_mandatory_confirmation() -> None:
    row = google_row()
    assert confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA) == "google-account-1"
    # No branch skips it, and no branch performs it twice.
    for destination in RegisteredDestination:
        assert confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA,
                                           destination=destination) == "google-account-1"
    with pytest.raises(FreeGrantError):
        confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA, lookups=0)
    with pytest.raises(FreeGrantError):
        confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA, lookups=2)
    with pytest.raises(FreeGrantError):
        confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA, issuer_selected_admin_client=False)
    with pytest.raises(ClaimEndpointError):
        registered_endpoint_reads_and_enforces(row, alias_index(),
                                              provider_data_confirmations=0)


# [utest->req~grants-reg-entry-no-restore-proof~1]
def test_the_registered_claim_request_carries_no_restore_proof() -> None:
    assert_no_registered_restore_proof({"turnstile_token": "cf"})
    with pytest.raises(ClaimEndpointError):
        assert_no_registered_restore_proof({"restore_proof": {"store": "google"}})


# [utest->req~grants-reg-entry-no-device-identity-proof~1]
def test_no_device_material_is_required_accepted_or_evaluated_as_identity() -> None:
    assert_no_registered_device_identity_proof()
    for role in ("required", "accepted", "evaluated"):
        with pytest.raises(FreeGrantError):
            assert_no_registered_device_identity_proof(**{role: ("app_attest_assertion",)})
    with pytest.raises(FreeGrantError):
        assert_no_device_proof_as_identity(evaluated=("android_keystore_proof",))


# [utest->req~grants-reg-entry-claim-kind-proof-set~1]
def test_the_selected_claim_kinds_complete_proof_set_must_be_present() -> None:
    assert registered_platform_proof_set(ClaimBranch.native_ios) == {
        ProofArtifact.devicecheck_query_token, ProofArtifact.devicecheck_update_token}
    assert registered_platform_proof_set(ClaimBranch.native_android) == {
        ProofArtifact.play_integrity_verdict}
    assert registered_platform_proof_set(ClaimBranch.web) == {ProofArtifact.turnstile_token}
    # A missing, partial or ambiguous set rejects as proof_rejected before any vendor call.
    for evidence in (ClaimEvidence(),
                     ClaimEvidence(devicecheck_query_token="q"),
                     ClaimEvidence(devicecheck_query_token="q", devicecheck_update_token="u",
                                   turnstile_token="cf")):
        with pytest.raises(FreeGrantRejected) as refused:
            resolve_claim_kind(evidence)
        assert refused.value.error_code == "proof_rejected"


# [utest->req~grants-reg-entry-no-client-provider-id~1]
def test_no_client_supplied_provider_account_identifier_is_accepted() -> None:
    assert_no_client_provider_identifier({"turnstile_token": "cf"})
    for field in ("provider_uid", "provider_account_id", "idp_account_hash", "google_uid",
                  "apple_uid", "sub", "email"):
        with pytest.raises(ClaimEndpointError):
            assert_no_client_provider_identifier({field: "value"})


# [utest->req~grants-reg-mutation-challenge-claim-order~1]
def test_the_registered_claim_claims_the_challenge_before_every_vendor_call() -> None:
    row = google_row()
    index = alias_index()
    claim = RegisteredGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    claim.resolve_identity(context_for(row), row)
    claim.claim_challenge(lambda: ClaimOutcome.claimed)
    assert claim.provider_data_lookups == 0
    assert claim.vendor_calls == 0
    claim.resolve_kind(WEB_EVIDENCE)
    claim.confirm_binding(row, GOOGLE_PROVIDER_DATA, index)
    assert claim.provider_data_lookups == 1
    assert claim.steps.index(RegisteredClaimStep.challenge_claim) \
        < claim.steps.index(RegisteredClaimStep.provider_data_confirmation)
    # The alias is derivable before the claim: it needs no Firebase or vendor call.
    early = alias_index()
    assert early.alias(registered_provider_account(row)).digest
    # A duplicate that loses the claim is rejected there, having spent nothing.
    loser = RegisteredGrantClaim()
    loser.admit(pre_consumption_passed=True, handler_admission_passed=True)
    loser.resolve_identity(context_for(row), row)
    with pytest.raises(FreeGrantError):
        loser.claim_challenge(lambda: ClaimOutcome.already_used)
    assert loser.vendor_calls == 0
    assert loser.provider_data_lookups == 0


# --- `claim_registered_grant`: the pre-activation gates --------------------------------------------


# [utest->req~grants-reg-gate-resolve-identity~1]
def test_the_registered_gate_resolves_the_identity_from_stored_state_alone() -> None:
    row = google_row()
    claim = RegisteredGrantClaim()
    claim.admit(pre_consumption_passed=True, handler_admission_passed=True)
    assert claim.resolve_identity(context_for(row), row) is row
    # A pre-auth caller, a historical identity and an ineligible provider each take their own class.
    preauth = RegisteredGrantClaim()
    preauth.admit(pre_consumption_passed=True, handler_admission_passed=True)
    with pytest.raises(FreeGrantRejected) as unlinked:
        preauth.resolve_identity(context_for(row, ResolutionOutcome.pre_auth), row)
    assert unlinked.value.error_code == "preauth_identity_not_allowed"
    historical = google_row(identity_state=IdentityState.historical)
    stale = RegisteredGrantClaim()
    stale.admit(pre_consumption_passed=True, handler_admission_passed=True)
    with pytest.raises(FreeGrantRejected) as retired:
        stale.resolve_identity(context_for(historical), historical)
    assert retired.value.result is AuthEventResult.historical_identity
    assert retired.value.error_code == "account_unavailable"
    anonymous = identity_row()
    wrong = RegisteredGrantClaim()
    wrong.admit(pre_consumption_passed=True, handler_admission_passed=True)
    with pytest.raises(FreeGrantRejected) as ineligible:
        wrong.resolve_identity(context_for(anonymous), anonymous)
    assert ineligible.value.result is AuthEventResult.idp_account_not_eligible
    assert ineligible.value.error_code == "verification_required"


# [utest->req~grants-reg-gate-compute-hash-and-confirm~1]
def test_the_gate_computes_the_alias_from_stored_values_and_confirms_it_live() -> None:
    row = google_row()
    index = alias_index()
    claim = registered_claim(ClaimBranch.web, row, index)
    assert claim.alias is not None
    assert claim.alias.key_version == 1
    # The alias comes from the stored provider and stored provider_uid, and matches the index's.
    assert claim.alias.digest == index.alias(registered_provider_account(row)).digest
    # A divergent live result is a conflict that mutates nothing and rewrites no stored binding.
    diverged = google_row()
    diverging = RegisteredGrantClaim()
    diverging.admit(pre_consumption_passed=True, handler_admission_passed=True)
    diverging.resolve_identity(context_for(diverged), diverged)
    diverging.claim_challenge(lambda: ClaimOutcome.claimed)
    diverging.resolve_kind(WEB_EVIDENCE)
    with pytest.raises(Exception) as conflict:
        diverging.confirm_binding(diverged,
                                  [{"providerId": "google.com", "uid": "someone-else"}],
                                  alias_index())
    assert not isinstance(conflict.value, AssertionError)
    assert diverged.provider_uid == "google-account-1"
    # A transient failure after the budget is VTU; user-not-found is non-retryable auth_required.
    transient = classify_registered_failure(RegClaimCondition.firebase_provider_data_unavailable)
    assert transient.result is AuthEventResult.firebase_lookup_unavailable
    assert transient.client_class is ClientErrorClass.verification_temporarily_unavailable
    not_found = classify_registered_failure(RegClaimCondition.firebase_user_not_found)
    assert not_found.result is AuthEventResult.firebase_user_unresolved
    assert not_found.client_class is ClientErrorClass.auth_required
    assert not_found.retryable is False


# [utest->req~grants-reg-gate-resolve-claim-kind~1]
def test_the_claim_kind_is_resolved_server_side_from_the_evidence_it_carries() -> None:
    assert resolve_claim_kind(IOS_EVIDENCE) is ClaimBranch.native_ios
    assert resolve_claim_kind(ANDROID_EVIDENCE) is ClaimBranch.native_android
    assert resolve_claim_kind(WEB_EVIDENCE) is ClaimBranch.web
    # No client-supplied platform header participates, and no material is optional.
    with pytest.raises(FreeGrantError):
        resolve_claim_kind(WEB_EVIDENCE, platform_header="ios")
    with pytest.raises(FreeGrantError):
        resolve_claim_kind(WEB_EVIDENCE, optional_material=("turnstile_token",))
    # An already-set registered bit is device_grant_exhausted, before any eligibility check.
    row = google_row(native_claim_platform=NativeClaimPlatform.ios_devicecheck)
    index = alias_index()
    claim = registered_claim(ClaimBranch.native_ios, row, index)
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck(bits={"bit0": False, "bit1": True}))
    with pytest.raises(DeviceGrantExhausted):
        claim.read_registered_state(native=(adapter, IOS_MATERIAL, NativeClaimLedger()))
    # On the web kind, a Turnstile denial is verification_required and a dependency failure VTU.
    denied = registered_claim(ClaimBranch.web, google_row(), alias_index())

    def deny() -> bool:
        raise TurnstileDenied("hostname mismatch")

    with pytest.raises(FreeGrantRejected) as refused:
        denied.read_registered_state(turnstile=deny)
    assert refused.value.error_code == "verification_required"
    unavailable = registered_claim(ClaimBranch.web, google_row(), alias_index())

    def outage() -> bool:
        raise TurnstileUnavailable("siteverify timed out")

    with pytest.raises(FreeGrantRejected) as transient:
        unavailable.read_registered_state(turnstile=outage)
    assert transient.value.error_code == "verification_temporarily_unavailable"


# [utest->req~grants-reg-gate-db-history-destination~1]
def test_the_gate_inspects_the_history_and_selects_one_destination() -> None:
    # No free-grant history at all selects new-grant creation.
    fresh = select_destination(grants=(), committed_free_sources=(), now=NOW)
    assert fresh.destination is RegisteredDestination.new_grant
    # An active anonymous grant is eligible only for the conversion path.
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    converted = select_destination(
        grants=(anonymous,), committed_free_sources=(AccessGrantSource.anonymous_device_grant,),
        now=NOW)
    assert converted.destination is RegisteredDestination.supersession_conversion
    # An existing committed registered grant selects the idempotent repeat.
    registered = grant_row(AccessGrantSource.registered_account_grant)
    repeat = select_destination(
        grants=(registered,),
        committed_free_sources=(AccessGrantSource.registered_account_grant,), now=NOW)
    assert repeat.destination is RegisteredDestination.idempotent_repeat
    # An incompatible active grant rejects under its own class, and discloses only its end.
    subscription = grant_row(AccessGrantSource.subscription, ends_at=NOW + timedelta(days=10))
    with pytest.raises(RegisteredDestinationBlocked) as blocked:
        select_destination(grants=(subscription,), committed_free_sources=(), now=NOW)
    assert blocked.value.result is AuthEventResult.registered_grant_destination_incompatible
    assert blocked.value.held_grant_ends_at == NOW + timedelta(days=10)
    # A committed free grant that selects no branch below refuses a new issuance.
    with pytest.raises(FreeGrantRejected):
        select_destination(grants=(),
                           committed_free_sources=(AccessGrantSource.anonymous_device_grant,),
                           now=NOW)


# --- `claim_registered_grant`: the completion transaction ------------------------------------------


# [utest->req~grants-reg-completion-transaction-entry~1]
def test_the_completion_transaction_is_entered_only_behind_its_own_gates() -> None:
    # The web kind enters after the preflight and the mandatory Turnstile validation.
    claim, activation = registered_web_activation()
    assert RegisteredClaimStep.activation in claim.steps
    assert claim.steps.index(RegisteredClaimStep.database_eligibility) \
        < claim.steps.index(RegisteredClaimStep.activation)
    assert activation.grant["status"] is AccessGrantStatus.active
    # A device-checked kind cannot enter it without this attempt's own confirmed write.
    row = google_row(native_claim_platform=NativeClaimPlatform.ios_devicecheck)
    index = alias_index()
    unwritten = registered_claim(ClaimBranch.native_ios, row, index)
    ledger = NativeClaimLedger()
    adapter = DeviceCheckAdapter(APPLE, FakeDeviceCheck())
    unwritten.read_registered_state(native=(adapter, IOS_MATERIAL, ledger))
    unwritten.check_database_eligibility(grants=(), committed_free_sources=(), now=NOW,
                                         ledger=ledger)
    with pytest.raises(FreeGrantError):
        unwritten.activate(row=row, grant_id=uuid7(), tier_id=FREE_TIER, alias_index=index,
                           transaction=object(),
                           locks=LockLedger(LockingPath.claim_registered_grant_completion),
                           consume_challenge=lambda: True, subject_hasher=SUBJECT_HASHER, now=NOW)


# [utest->req~grants-reg-txn-step-01-lock-and-reconfirm~1]
def test_txn_step_01_locks_and_reconfirms_the_user_identity_and_binding() -> None:
    row = google_row()
    account = registered_provider_account(row)
    assert reconfirm_registered_claimant(row, account, NOW,
                                         destination=RegisteredDestination.new_grant) is row
    # A historical identity is audited under its own result and surfaced as account_unavailable.
    historical = google_row(identity_state=IdentityState.historical)
    with pytest.raises(FreeGrantRejected) as retired:
        reconfirm_registered_claimant(historical, account, NOW,
                                      destination=RegisteredDestination.new_grant)
    assert retired.value.result is AuthEventResult.historical_identity
    assert retired.value.error_code == "account_unavailable"
    # The exact stored provider and provider_uid the hash used must still apply.
    moved = google_row(provider_uid="google-account-2")
    with pytest.raises(FreeGrantError):
        reconfirm_registered_claimant(moved, account, NOW,
                                      destination=RegisteredDestination.new_grant)
    # The whole activation takes the lock before it reconfirms.
    locks = LockLedger(LockingPath.claim_registered_grant_completion)
    index = alias_index()
    claim = registered_claim(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    claim.check_database_eligibility(grants=(), committed_free_sources=(), now=NOW)
    claim.activate(row=row, grant_id=uuid7(), tier_id=FREE_TIER, alias_index=index,
                   transaction=object(), locks=locks, consume_challenge=lambda: True,
                   subject_hasher=SUBJECT_HASHER, now=NOW)
    assert locks.grant_locks and locks.holds_locks


# [utest->req~grants-reg-txn-step-02-select-destination~1]
def test_txn_step_02_reconfirms_the_marker_then_selects_exactly_one_destination() -> None:
    row = google_row()
    account = registered_provider_account(row)
    # A set marker refuses a new issuance under the one-free-grant-per-account rule.
    consumed = google_row(free_grant_consumed_at=NOW - timedelta(days=5))
    with pytest.raises(FreeGrantRejected) as refused:
        reconfirm_registered_claimant(consumed, registered_provider_account(consumed), NOW,
                                      destination=RegisteredDestination.new_grant)
    assert refused.value.error_code == "operation_not_allowed"
    # The conversion transitions the same already-marked lineage, so it is admitted.
    assert reconfirm_registered_claimant(
        consumed, registered_provider_account(consumed), NOW,
        destination=RegisteredDestination.supersession_conversion) is consumed
    # A conversion never predates the lineage it transitions.
    with pytest.raises(Exception):
        reconfirm_registered_claimant(
            consumed, registered_provider_account(consumed), NOW - timedelta(days=10),
            destination=RegisteredDestination.supersession_conversion)
    # The repeat is determined first, so a repeat whose own grant is active is not a conflict.
    own = grant_row(AccessGrantSource.registered_account_grant, user_id=row.user_id)
    decision = select_destination(
        grants=(own,), committed_free_sources=(AccessGrantSource.registered_account_grant,),
        now=NOW, gate_consumption_grant_id=own.grant_id)
    assert decision.destination is RegisteredDestination.idempotent_repeat
    # A consumption row belonging to a different grant is a conflict.
    with pytest.raises(FreeGrantRejected) as conflict:
        select_destination(grants=(own,),
                           committed_free_sources=(AccessGrantSource.registered_account_grant,),
                           now=NOW, gate_consumption_grant_id=uuid7())
    assert conflict.value.result is AuthEventResult.idp_account_already_claimed
    assert reconfirm_registered_claimant(row, account, NOW,
                                         destination=RegisteredDestination.new_grant) is row


# [utest->req~grants-reg-txn-step-03-supersession-conversion~1]
def test_txn_step_03_expires_the_anonymous_grant_and_inserts_the_registered_one() -> None:
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    _claim, activation = registered_web_activation(
        grants=(anonymous,), committed=(AccessGrantSource.anonymous_device_grant,),
        carried_usage=("2026-08", 12))
    superseded = activation.superseded
    assert superseded is not None
    assert superseded["status"] is AccessGrantStatus.expired
    assert superseded["ends_at"] == NOW
    # Its source stays anonymous forever and its anti-abuse row is untouched.
    assert superseded["source"] is AccessGrantSource.anonymous_device_grant
    assert "anti_abuse" not in superseded
    # The new grant is active with its own anti-abuse row carrying the alias and key version.
    assert activation.grant["status"] is AccessGrantStatus.active
    assert activation.anti_abuse["idp_account_hash"] == activation.alias.digest
    assert activation.anti_abuse["idp_account_hash_key_version"] == activation.alias.key_version
    # The usage row carries the superseded grant's period and used count across.
    assert (activation.usage.monthly_period, activation.usage.monthly_used) == ("2026-08", 12)
    # The old row is deactivated before the new one is inserted, in the one transaction.
    assert supersession_write_order(activation) == (
        "expire_anonymous_grant", "insert_registered_grant", "insert_anti_abuse_row",
        "insert_gate_consumption_row", "insert_usage_row")


# [utest->req~grants-reg-txn-step-04-new-grant-creation~1]
def test_txn_step_04_creates_the_new_grant_with_its_own_rows() -> None:
    _claim, activation = registered_web_activation()
    assert activation.destination is RegisteredDestination.new_grant
    assert activation.grant["source"] is AccessGrantSource.registered_account_grant
    assert activation.grant["status"] is AccessGrantStatus.active
    assert activation.superseded is None
    assert activation.anti_abuse["grant_id"] == activation.grant["id"]
    assert activation.anti_abuse["idp_account_hash"] == activation.alias.digest
    assert activation.anti_abuse["idp_account_hash_key_version"] == activation.alias.key_version
    assert activation.usage.grant_id == activation.grant["id"]
    assert activation.usage.monthly_used == 0
    # The new-grant path never carries an existing usage row across.
    with pytest.raises(FreeGrantError):
        registered_web_activation(carried_usage=("2026-08", 4))


# [utest->req~grants-reg-txn-step-05-gate-consumption~1]
def test_txn_step_05_consumes_the_gate_sets_the_marker_and_defers_the_keys() -> None:
    index = alias_index()
    row = google_row()
    _claim, activation = registered_web_activation(row=row, index=index)
    # The canonical provider account row and its registered gate-consumption row exist.
    account = registered_provider_account(row)
    assert index.consumed(account, GateConsumptionKind.registered_account_grant) \
        == activation.grant["id"]
    # The identity record's permanent marker is set in this same transaction.
    assert activation.identity is not None
    assert activation.identity.free_grant_consumed_at == NOW
    # The deferred foreign keys are checked at commit, and nowhere else.
    assert DEFERRED_KEY_CHECK_POINT == "commit"
    assert_deferred_keys_checked_at_commit(object())
    with pytest.raises(FreeGrantError):
        assert_deferred_keys_checked_at_commit(object(), check_point="statement")
    # A gate conflict on the stable UID rolls back, audits idp_account_already_claimed and
    # returns account_already_claimed — final regardless of the hash key version.
    other = google_row()
    with pytest.raises(FreeGrantRejected) as conflict:
        registered_web_activation(row=other, index=index)
    assert conflict.value.result is AuthEventResult.idp_account_already_claimed
    assert conflict.value.error_code == "account_already_claimed"


# [utest->req~grants-reg-txn-step-06-consume-challenge-audit~1]
def test_txn_step_06_consumes_the_challenge_and_appends_the_success_audit() -> None:
    row = google_row()
    index = alias_index()
    consumes: list[bool] = []
    claim = registered_claim(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    claim.check_database_eligibility(grants=(), committed_free_sources=(), now=NOW)
    grant_id = uuid7()
    activation = claim.activate(
        row=row, grant_id=grant_id, tier_id=FREE_TIER, alias_index=index, transaction=object(),
        locks=LockLedger(LockingPath.claim_registered_grant_completion),
        consume_challenge=lambda: bool(consumes.append(True)) or True,
        subject_hasher=SUBJECT_HASHER, now=NOW)
    assert consumes == [True]
    audit = activation.audit
    assert audit.result is AuthEventResult.succeeded
    assert audit.actor is not None
    assert audit.actor.provider is IdentityProvider.google
    assert audit.actor.subject_hash is not None
    assert audit.details["identity"]["provider"] == "google"
    assert audit.details["anti_abuse"]["idp_account_hash_key_version"] == 1
    assert audit.details["mutation"]["destination"] == "new_grant"
    assert audit.details["mutation"]["grant_id"] == str(grant_id)
    # No raw provider identifier appears anywhere in the details.
    for section in audit.details.values():
        assert row.provider_uid not in set(str(value) for value in section.values())
    # A challenge that will not consume refuses the transaction.
    failing = registered_claim(ClaimBranch.web, google_row(), alias_index())
    failing.read_registered_state(turnstile=lambda: True)
    failing.check_database_eligibility(grants=(), committed_free_sources=(), now=NOW)
    with pytest.raises(FreeGrantError):
        failing.activate(row=google_row(), grant_id=uuid7(), tier_id=FREE_TIER,
                         alias_index=alias_index(), transaction=object(),
                         locks=LockLedger(LockingPath.claim_registered_grant_completion),
                         consume_challenge=lambda: False, subject_hasher=SUBJECT_HASHER, now=NOW)


# [utest->req~grants-reg-txn-step-07-return-grant~1]
def test_txn_step_07_returns_the_grant_its_tier_and_the_current_usage_state() -> None:
    _claim, activation = registered_web_activation()
    state = returned_grant_state(activation)
    assert state.grant_id == activation.grant["id"]
    assert state.status is AccessGrantStatus.active
    assert state.tier_id == FREE_TIER
    assert state.monthly_used == 0
    assert state.monthly_period == activation.usage.monthly_period
    # The conversion returns the carried usage state, not a reset one.
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    _claim, converted = registered_web_activation(
        grants=(anonymous,), committed=(AccessGrantSource.anonymous_device_grant,),
        carried_usage=("2026-08", 9))
    assert returned_grant_state(converted).monthly_used == 9
    # The idempotent repeat returns the held grant's own live state.
    held = grant_row(AccessGrantSource.registered_account_grant)
    repeated = repeated_grant_state(held, ("2026-08", 3))
    assert (repeated.grant_id, repeated.monthly_used) == (held.grant_id, 3)
    with pytest.raises(FreeGrantError):
        repeated_grant_state(grant_row(AccessGrantSource.subscription), ("2026-08", 0))


# [utest->req~grants-reg-never-second-allowance~1]
def test_the_operation_never_creates_a_second_free_credit_allowance() -> None:
    assert_one_active_grant(active_after=1)
    with pytest.raises(FreeGrantError):
        assert_one_active_grant(active_after=1, second_allowance=True)
    with pytest.raises(FreeGrantError):
        assert_one_active_grant(active_after=2)
    with pytest.raises(FreeGrantError):
        assert_one_active_grant(
            active_after=1,
            committed_free_sources=(AccessGrantSource.registered_account_grant,
                                    AccessGrantSource.registered_account_grant))
    # Only one destination executes: the conversion supersedes rather than adding a second row.
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    _claim, converted = registered_web_activation(
        grants=(anonymous,), committed=(AccessGrantSource.anonymous_device_grant,),
        carried_usage=("2026-08", 2))
    assert converted.superseded is not None
    assert converted.superseded["status"] is AccessGrantStatus.expired
    # A committed free grant with no convertible active row refuses a fresh issuance.
    with pytest.raises(FreeGrantRejected):
        registered_web_activation(committed=(AccessGrantSource.registered_account_grant,))


# [utest->req~grants-reg-proof-vs-dependency-mapping~1]
def test_client_proof_failures_and_dependency_failures_never_share_a_class() -> None:
    for condition in (RegClaimCondition.incomplete_platform_proof_set,
                      RegClaimCondition.evidence_set_shape_invalid):
        failure = classify_registered_failure(condition)
        assert failure.result is AuthEventResult.proof_malformed
        assert failure.client_class is ClientErrorClass.proof_rejected
    for condition in (RegClaimCondition.device_check_vendor_outage,
                      RegClaimCondition.registered_bit_write_failed,
                      RegClaimCondition.turnstile_dependency_failed):
        failure = classify_registered_failure(condition)
        assert failure.client_class is ClientErrorClass.verification_temporarily_unavailable
        assert failure.client_class is not ClientErrorClass.proof_rejected
        assert failure.after_retry_budget is True


# --- Inheritance and new-allowance rules -----------------------------------------------------------


# [utest->req~grants-inherit-conversion-carryover~1]
def test_the_conversion_inherits_the_existing_monthly_usage_exactly() -> None:
    anonymous = grant_row(AccessGrantSource.anonymous_device_grant)
    for period, used in (("2026-08", 0), ("2026-07", 41), ("2026-08", 1000)):
        _claim, converted = registered_web_activation(
            grants=(anonymous,), committed=(AccessGrantSource.anonymous_device_grant,),
            carried_usage=(period, used))
        # No clamping, no reset, no prorating and no top-up: the values cross unchanged.
        assert converted.usage.monthly_period == period
        assert converted.usage.monthly_used == used
    # The conversion path must be given the superseded grant's usage state.
    row = google_row()
    index = alias_index()
    claim = registered_claim(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    claim.check_database_eligibility(
        grants=(anonymous,), committed_free_sources=(AccessGrantSource.anonymous_device_grant,),
        now=NOW)
    with pytest.raises(FreeGrantError):
        claim.activate(row=row, grant_id=uuid7(), tier_id=FREE_TIER, alias_index=index,
                       transaction=object(),
                       locks=LockLedger(LockingPath.claim_registered_grant_completion),
                       consume_challenge=lambda: True, subject_hasher=SUBJECT_HASHER, now=NOW)


# [utest->req~grants-inherit-new-grant-zero-used~1]
def test_the_new_grant_path_opens_the_current_period_at_zero_used() -> None:
    _claim, activation = registered_web_activation()
    assert activation.usage.monthly_used == 0
    assert activation.usage.monthly_period == period_of(NOW)
    assert activation.usage.grant_id == activation.grant["id"]


# --- Registered account identifier rules -----------------------------------------------------------


# [utest->req~grants-reg-id-mandatory-confirmation~1]
def test_the_confirmation_runs_on_every_call_and_rewrites_no_stored_binding() -> None:
    row = google_row()
    before = (row.provider, row.provider_uid)
    assert confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA) == "google-account-1"
    assert (row.provider, row.provider_uid) == before
    # A confirmation that mutated anything is refused outright.
    with pytest.raises(FreeGrantError):
        confirm_stored_binding_live(row, GOOGLE_PROVIDER_DATA, mutations=("provider_uid",))
    # The idempotent repeat confirms too: the repeat step demands the one lookup happened.
    index = alias_index()
    own = grant_row(AccessGrantSource.registered_account_grant, user_id=row.user_id)
    claim = registered_claim(ClaimBranch.web, row, index)
    claim.read_registered_state(turnstile=lambda: True)
    decision = claim.check_database_eligibility(
        grants=(own,), committed_free_sources=(AccessGrantSource.registered_account_grant,),
        now=NOW, gate_consumption_grant_id=own.grant_id)
    assert decision.destination is RegisteredDestination.idempotent_repeat
    assert claim.provider_data_lookups == 1
    assert claim.alias is not None
    event = claim.repeat(row, alias=claim.alias, grant=own, subject_hasher=SUBJECT_HASHER)
    assert event.result is AuthEventResult.succeeded


# [utest->req~grants-reg-id-canonical-provider-uid~1]
def test_the_stored_provider_uid_is_the_canonical_provider_account_identifier() -> None:
    row = google_row()
    account = registered_provider_account(row)
    assert account.provider_uid == row.provider_uid
    assert account.provider is row.provider
    # An ineligible provider or an absent provider_uid is idp_account_not_eligible.
    # An ineligible provider, and the same row shape as the one that stores no `provider_uid`.
    with pytest.raises(FreeGrantRejected) as refused:
        registered_provider_account(identity_row())
    assert refused.value.result is AuthEventResult.idp_account_not_eligible
    assert refused.value.error_code == "verification_required"
    assert registered_provider_account(
        google_row(provider=IdentityProvider.apple,
                   provider_uid="apple-sub-1")).provider_uid == "apple-sub-1"


# [utest->req~grants-reg-id-gate-conflict-mapping~1]
def test_a_registered_gate_conflict_on_the_stable_uid_is_account_already_claimed() -> None:
    index = alias_index()
    registered_web_activation(row=google_row(), index=index)
    # A different Firebase account, external identity and internal user — same provider account.
    with pytest.raises(FreeGrantRejected) as conflict:
        registered_web_activation(row=google_row(), index=index)
    assert conflict.value.result is AuthEventResult.idp_account_already_claimed
    assert conflict.value.error_code == "account_already_claimed"
    failure = classify_registered_failure(RegClaimCondition.registered_gate_consumed)
    assert failure.result is AuthEventResult.idp_account_already_claimed
    assert failure.client_class is ClientErrorClass.account_already_claimed


# [utest->req~grants-reg-durable-rejections-final~1]
def test_a_durable_registered_rejection_promises_no_alternate_and_is_final() -> None:
    assert DURABLE_REGISTERED_CLASSES == frozenset({ClientErrorClass.verification_required,
                                                    ClientErrorClass.account_already_claimed})
    for client_class in DURABLE_REGISTERED_CLASSES:
        alternate, actions = registered_durable_rejection(client_class)
        # No free-credit alternate is promised: continued access needs a paid entitlement.
        assert alternate is None
        assert actions == ("active_subscription", "non_free_entitlement")
    with pytest.raises(GrantFailureError):
        registered_durable_rejection(ClientErrorClass.verification_temporarily_unavailable)


# --- Development and simulator bypass boundary -----------------------------------------------------


# [utest->req~grants-devcheck-bypass-non-production-only~1]
def test_the_device_check_bypass_exists_only_outside_production_and_never_by_client_input() -> None:
    # It can be in effect in a non-production configuration, from server-side state alone.
    for environment in BYPASS_ENVIRONMENTS:
        assert device_check_bypass_enabled(environment=environment,
                                          server_configured=True) is True
        assert device_check_bypass_enabled(environment=environment,
                                          server_configured=False) is False
    assert DeploymentEnvironment.production not in BYPASS_ENVIRONMENTS
    # Production never has it, and configuring it there is a hard failure rather than an ignore.
    assert device_check_bypass_enabled(environment=DeploymentEnvironment.production,
                                      server_configured=False) is False
    with pytest.raises(FreeGrantError):
        device_check_bypass_enabled(environment=DeploymentEnvironment.production,
                                    server_configured=True)
    # No client-supplied signal of any kind can enable it.
    for signal in ("x-devicecheck-bypass", "simulator", "bypass_device_check", "dev_mode"):
        with pytest.raises(FreeGrantError):
            device_check_bypass_enabled(environment=DeploymentEnvironment.development,
                                        server_configured=True, client_signals={signal: "1"})
    assert CLIENT_SELECTABLE_BYPASS_SIGNALS == frozenset()
    # Production service credentials never enable it either.
    with pytest.raises(FreeGrantError):
        device_check_bypass_enabled(environment=DeploymentEnvironment.development,
                                    server_configured=True, production_credentials=True)
    # It governs the device-check gate alone: no other gate gains a symmetric bypass.
    assert BYPASSABLE_GATES == frozenset({"device_check"})
    for gate in ("cloudflare", "turnstile", "firebase_provider_data", "operation_challenge"):
        with pytest.raises(FreeGrantError):
            device_check_bypass_enabled(environment=DeploymentEnvironment.development,
                                        server_configured=True, gate=gate)
    # And there is no generalized development-flag framework.
    assert DEVELOPMENT_FLAG_FRAMEWORKS == frozenset()
