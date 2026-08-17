"""`upgrade_anonymous_to_registered`: the two purposes, the stranded state, the entry conditions,
the complete case matrix the flip and the idempotent no-op follow, and the endpoint's own
rejection classes and audit record."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome, VerifiedIdentityContext
from nativespeaker.api.auth.challenges import ChallengeState
from nativespeaker.api.auth.create_user import ProviderNotLinkedCause, provider_not_linked_details
from nativespeaker.api.auth.entitlement import IntroductoryEntitlementError
from nativespeaker.api.auth.external_identities import (
    ExternalIdentityRow,
    IdentityState,
    ProviderLookupFailedError,
    provider_account_conflict,
)
from nativespeaker.api.auth.operations import (
    AuthOperation,
    IdentityProvider,
    InvalidOperationVariantError,
)
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.profile import AdminUserRecord, ProfileError
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.auth.tokens import InvalidExternalJwtError
from nativespeaker.api.auth.upgrade import (
    ABANDONED_ACCOUNT_MECHANISMS,
    ABANDONED_ACCOUNT_MUTATIONS,
    ATTRIBUTION_TOKEN_MUTATIONS,
    IDENTITY_LOCK_ORDER,
    PRESERVED_BUSINESS_STATE,
    REPAIR_MECHANISMS,
    REPAIR_READ_SURFACES,
    REPAIR_ROLE_OPTIMIZATIONS,
    STRANDED_ACCOUNT_GRANTS,
    STRANDING_SIDE_EFFECTS,
    TRANSITION_REJECTION_MUTATIONS,
    UPGRADE_AUDIT_BEST_EFFORT,
    UPGRADE_AUDIT_ROWS,
    UPGRADE_CREATED_IDENTITY_ROWS,
    UPGRADE_DEVICE_GRANT_BITS,
    UPGRADE_GRANT_WRITES,
    UPGRADE_RETIRED_IDENTITY_ROWS,
    LockedRows,
    RepairRetry,
    TransitionDivergence,
    UpgradeBranch,
    UpgradedAccount,
    UpgradeEndpoint,
    UpgradeError,
    UpgradePurpose,
    UpgradeRejection,
    UpgradeUser,
    abandoned_anonymous_account,
    assert_identity_metadata_only,
    assert_in_place,
    assert_reservation_scope,
    assert_rows_active,
    assert_state_preserved,
    assert_upgrade_transaction,
    audited_upgrade_result,
    credential_already_in_use_route,
    entry_linked_identity,
    entry_no_restore_proof,
    entry_target_provider,
    link_completed,
    linking_flip,
    mutable_path_rejection,
    provider_conflict_rejection,
    repair_disposition,
    repair_needed,
    resolved_and_locked,
    stranded_upgrade,
    transition_rejection,
    upgrade_attempt_audit,
    upgrade_branch,
    upgrade_client_class,
    upgrade_failure_result,
    upgrade_purpose,
    upgraded_user,
)
from nativespeaker.api.auth.users import UpgradeDecision, UsersError
from unit.conftest import TEST_ISSUER
from unit.test_auth_challenges import Harness, preauth_context
from unit.test_create_user import ADMIN_CLIENT, ANONYMOUS, APPLE, GOOGLE, FakeLookup, entries
from unit.test_create_user import integrations as firebase_integrations

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
UPGRADE = AuthOperation.upgrade_anonymous_to_registered
SUBJECT = "linked-subject"

GOOGLE_UID = "google-account-id"
APPLE_UID = "apple-user-id"

# Everything the operation must leave exactly as it found it.
PRESERVED: dict[str, Any] = {
    "chats": ("chat-1", "chat-2"),
    "access_grants": ("grant-1",),
    "introductory_value": 10,
    "grant_monthly_usage": 4,
    "subscriptions": ("sub-1",),
    "core.store_purchase_tokens": ("apple-token", "google-token"),
}


def identity_row(provider: IdentityProvider = IdentityProvider.anonymous,
                 provider_uid: str | None = None,
                 state: IdentityState = IdentityState.active,
                 user_id: Any = None) -> ExternalIdentityRow:
    return ExternalIdentityRow(id=uuid7(), user_id=user_id or uuid7(), issuer=TEST_ISSUER,
                               subject=SUBJECT, provider=provider, provider_uid=provider_uid,
                               identity_state=state)


def upgrade_context(row: ExternalIdentityRow) -> VerifiedIdentityContext:
    return VerifiedIdentityContext(issuer=row.issuer, subject=row.subject,
                                   outcome=ResolutionOutcome.linked,
                                   user_id=row.user_id,
                                   external_identity_id=row.id,
                                   provider=row.provider)


class FakeIdentities:
    """The database half of the upgrade transaction: the locked rows, the preserved business
    state, and the one uniqueness rule the flip can lose against."""

    def __init__(self, identity: ExternalIdentityRow, user: UpgradeUser, *,
                 conflict: bool = False, missing: bool = False,
                 locked: tuple[str, ...] = IDENTITY_LOCK_ORDER) -> None:
        self.identity = identity
        self.user = user
        self.conflict = conflict
        self.missing = missing
        self.locked = locked
        self.preserved = dict(PRESERVED)
        self.sessions: list[Any] = []
        self.flips: list[tuple[ExternalIdentityRow, UpgradeUser]] = []

    async def lock_identity(self, session, issuer, subject) -> LockedRows | None:
        self.sessions.append(session)
        if self.missing or self.identity.issuer != issuer or self.identity.subject != subject:
            return None
        return LockedRows(identity=self.identity, user=self.user, locked=self.locked,
                          transaction=session)

    async def preserved_state(self, session, user_id) -> dict[str, Any]:
        return dict(self.preserved)

    async def flip_provider(self, session, *, identity, user) -> None:
        self.sessions.append(session)
        if self.conflict:
            raise provider_account_conflict(UPGRADE)
        self.identity = identity
        self.user = user
        self.flips.append((identity, user))


class Flow:
    """One prepare-and-complete run of the real endpoint through the shared procedures."""

    def __init__(self, *,
                 stored: IdentityProvider = IdentityProvider.anonymous,
                 provider_uid: str | None = None,
                 state: IdentityState = IdentityState.active,
                 user: UpgradeUser | None = None,
                 lookup: FakeLookup | None = None,
                 admin: Any = ADMIN_CLIENT,
                 conflict: bool = False,
                 missing: bool = False,
                 locked: tuple[str, ...] = IDENTITY_LOCK_ORDER) -> None:
        self.h = Harness()
        self.identity = identity_row(stored, provider_uid, state)
        self.user = (replace(user, id=self.identity.user_id) if user is not None
                     else UpgradeUser(id=self.identity.user_id))
        self.identities = FakeIdentities(self.identity, self.user, conflict=conflict,
                                         missing=missing, locked=locked)
        self.lookup = lookup or FakeLookup(GOOGLE)
        self.endpoint = UpgradeEndpoint(integrations=firebase_integrations(admin),
                                        identities=self.identities, lookup=self.lookup,
                                        clock=lambda: NOW)
        self.context = upgrade_context(self.identity)

    async def prepare(self, variant: IdentityProvider = IdentityProvider.google):
        await self.h.service.prepare(UPGRADE, variant, self.context, self.endpoint)
        return self.h.store.only()

    async def complete(self, declared: str | None = "google", *,
                       variant: IdentityProvider = IdentityProvider.google,
                       body: dict[str, Any] | None = None) -> UpgradedAccount:
        row = await self.prepare(variant)
        payload: dict[str, Any] = {"challenge_id": row.challenge_id, "provider": declared}
        if body is not None:
            payload = body if "challenge_id" in body else {**payload, **body}
        return await self.h.service.complete(UPGRADE, declared, row.challenge_id, self.context,
                                             self.endpoint, body=payload)

    def row(self):
        return self.h.store.only()

    def audited(self) -> list[AuthEventResult]:
        return self.h.sink.results()

    def details(self) -> dict[str, Any]:
        return self.h.sink.events[-1]["details"]


# --- Purpose ---------------------------------------------------------------------------------


class TestPurpose:
    # [utest->req~users-upgrade-purpose-link~1]
    async def test_the_completion_flips_the_anonymous_row_in_place_for_the_same_uid(self):
        flow = Flow()
        before = flow.identity
        account = await flow.complete("google")
        assert account.identity.provider is IdentityProvider.google
        assert account.identity.provider_uid == GOOGLE_UID
        # The same Firebase UID keeps the same identity row and the same user.
        assert (account.identity.id, account.identity.user_id) == (before.id, before.user_id)
        assert (account.identity.issuer, account.identity.subject) == (before.issuer,
                                                                       before.subject)
        assert flow.audited() == [AuthEventResult.succeeded]

    # [utest->req~users-upgrade-purpose-link~1]
    def test_only_the_mutable_branch_flips_and_only_from_anonymous(self):
        row = identity_row()
        context = upgrade_context(row)
        session = object()
        idempotent = UpgradeDecision(UpgradeBranch.idempotent, IdentityProvider.google, GOOGLE_UID)
        with pytest.raises(UpgradeError):
            linking_flip(row, idempotent, context=context, transaction=session)
        registered = identity_row(IdentityProvider.google, GOOGLE_UID)
        mutable = UpgradeDecision(UpgradeBranch.mutable, IdentityProvider.google, GOOGLE_UID)
        with pytest.raises(UpgradeError):
            linking_flip(registered, mutable, context=upgrade_context(registered),
                         transaction=session)

    # [utest->req~users-upgrade-purpose-repair~1]
    async def test_a_stranded_upgrade_is_repaired_by_this_same_operation(self):
        # The client linked at Firebase and the backend completion never landed: the account is
        # stranded, and this operation is what repairs it.
        flow = Flow()
        stranded = stranded_upgrade(flow.identity, flow.user, live_provider=IdentityProvider.google)
        assert stranded is not None
        assert upgrade_purpose(stranded) is UpgradePurpose.stranded_repair
        account = await flow.complete("google")
        assert account.purpose is UpgradePurpose.stranded_repair
        assert account.branch is UpgradeBranch.mutable
        # The repair role is required: nothing optimizes it away, however idempotent a completed
        # upgrade is. A repeat after the repair is the idempotent no-op, not a second repair.
        assert REPAIR_ROLE_OPTIMIZATIONS == frozenset()
        assert upgrade_purpose(None) is UpgradePurpose.link_completion
        repeat = Flow(stored=IdentityProvider.google, provider_uid=GOOGLE_UID,
                      user=UpgradeUser(id=uuid7(), registered_at=NOW))
        again = await repeat.complete("google")
        assert again.branch is UpgradeBranch.idempotent
        assert again.purpose is UpgradePurpose.link_completion


class TestStrandedDefinition:
    # [utest->req~users-stranded-upgrade-definition~1]
    def test_stranding_is_a_live_registered_provider_over_a_stored_anonymous_row(self):
        row = identity_row()
        user = UpgradeUser(id=row.user_id)
        for provider in (IdentityProvider.google, IdentityProvider.apple):
            stranded = stranded_upgrade(row, user, live_provider=provider)
            assert stranded is not None
            assert stranded.identity is row and stranded.user is user
            assert stranded.live_provider is provider
        # Not stranded: no registered provider linked live.
        assert stranded_upgrade(row, user, live_provider=IdentityProvider.anonymous) is None
        # Not stranded: the backend already completed the transition.
        assert stranded_upgrade(identity_row(IdentityProvider.google, GOOGLE_UID), user,
                                live_provider=IdentityProvider.google) is None
        assert stranded_upgrade(row, replace(user, registered_at=NOW),
                                live_provider=IdentityProvider.google) is None

    # [utest->req~users-stranded-upgrade-definition~1]
    def test_stranding_causes_no_historical_transition_no_sign_out_and_no_grant(self):
        assert STRANDING_SIDE_EFFECTS == frozenset()
        assert STRANDED_ACCOUNT_GRANTS == frozenset()
        retired = identity_row(state=IdentityState.historical)
        with pytest.raises(UpgradeError):
            stranded_upgrade(retired, UpgradeUser(id=retired.user_id),
                             live_provider=IdentityProvider.google)
        blocked = identity_row()
        with pytest.raises(UpgradeError):
            stranded_upgrade(blocked, UpgradeUser(id=blocked.user_id, active=False),
                             live_provider=IdentityProvider.google)
        # It is one account throughout: the identity row's user is the stranded user.
        other = identity_row()
        with pytest.raises(UpgradeError):
            stranded_upgrade(other, UpgradeUser(id=uuid7()),
                             live_provider=IdentityProvider.google)


# --- Entry conditions ------------------------------------------------------------------------


class TestEntryConditions:
    # [utest->req~users-upgrade-entry-token-resolves-linked-identity~1]
    def test_the_verified_pair_must_resolve_to_the_linked_identity_row(self):
        row = identity_row()
        context = upgrade_context(row)
        assert entry_linked_identity(context, row=row) == row.id
        # A pre-auth identity is not an upgrade caller at all.
        with pytest.raises(UsersError):
            entry_linked_identity(preauth_context("some-preauth-subject"))
        # A row for a different subject is not the one the verified pair resolves to.
        other = replace(row, subject="another-subject")
        with pytest.raises(UpgradeError):
            entry_linked_identity(context, row=other)
        # A historical row is not an entry condition either.
        with pytest.raises(UsersError):
            entry_linked_identity(context, row=replace(row, identity_state=IdentityState.historical))

    # [utest->req~users-upgrade-entry-token-resolves-linked-identity~1]
    async def test_any_valid_token_for_the_pair_suffices_at_any_freshness(self):
        flow = Flow()
        # The endpoint compares no `auth_time`, issue time or re-authentication window.
        account = await flow.complete("google")
        assert account.identity.provider is IdentityProvider.google

    # [utest->req~users-upgrade-entry-declared-target-provider~1]
    def test_the_entry_declares_google_or_apple_and_nothing_else(self):
        from nativespeaker.api.auth.modes import RequestMode

        assert entry_target_provider("google", phase=RequestMode.prepare) is IdentityProvider.google
        assert entry_target_provider("apple", phase=RequestMode.prepare) is IdentityProvider.apple
        for declared in ("anonymous", None, "Google", "facebook"):
            with pytest.raises(InvalidOperationVariantError):
                entry_target_provider(declared, phase=RequestMode.prepare)

    # [utest->req~users-upgrade-entry-mutable-vs-idempotent~1]
    def test_the_stored_provider_selects_the_branch_after_the_live_confirmation(self):
        assert upgrade_branch(identity_row(), lookups=1) is UpgradeBranch.mutable
        assert upgrade_branch(identity_row(IdentityProvider.google, GOOGLE_UID),
                              lookups=1) is UpgradeBranch.idempotent
        assert upgrade_branch(identity_row(IdentityProvider.apple, APPLE_UID),
                              lookups=1) is UpgradeBranch.idempotent
        # No branch is taken without the mandatory live confirmation on this same call.
        for lookups in (0, 2):
            with pytest.raises(UpgradeError):
                upgrade_branch(identity_row(IdentityProvider.google, GOOGLE_UID), lookups=lookups)

    # [utest->req~users-upgrade-entry-client-link-completed~1]
    async def test_empty_provider_data_means_the_client_never_completed_the_link(self):
        assert link_completed(()) is False
        assert link_completed(entries("google.com")) is True
        flow = Flow(lookup=FakeLookup(ANONYMOUS))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert raised.value.cause is ProviderNotLinkedCause.empty_provider_data
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-entry-no-restore-proof~1]
    async def test_a_restore_proof_is_absent_from_the_request(self):
        entry_no_restore_proof({"challenge_id": "x", "provider": "google"})
        with pytest.raises(UsersError):
            entry_no_restore_proof({"restore_proof": {"receipt": "..."}})
        flow = Flow()
        with pytest.raises(UsersError):
            await flow.complete("google", body={"provider": "google",
                                                "restore_proof": {"receipt": "..."}})
        assert flow.identities.flips == []


# --- Mutation rules 1 to 6 --------------------------------------------------------------------


class TestDeclarationAndLookup:
    # [utest->req~users-upgrade-step-01~1]
    async def test_the_completion_provider_must_equal_the_bound_variant_byte_for_byte(self):
        flow = Flow()
        row = await flow.prepare()
        with pytest.raises(ChallengeRejection) as raised:
            await flow.h.service.complete(UPGRADE, "google", row.challenge_id, flow.context,
                                          flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "Google"})
        assert raised.value.result is AuthEventResult.challenge_operation_mismatch
        assert raised.value.error_code == ClientErrorClass.challenge_required
        # The mismatch is decided before any Firebase Admin lookup, and it consumes the row.
        assert flow.lookup.calls == 0
        assert flow.row().state is ChallengeState.consumed

    # [utest->req~users-upgrade-step-01~1]
    async def test_a_missing_provider_is_a_mismatch_and_never_defaulted(self):
        flow = Flow()
        row = await flow.prepare()
        with pytest.raises(ChallengeRejection) as raised:
            await flow.h.service.complete(UPGRADE, "google", row.challenge_id, flow.context,
                                          flow.endpoint,
                                          body={"challenge_id": row.challenge_id})
        assert raised.value.result is AuthEventResult.challenge_operation_mismatch
        assert flow.lookup.calls == 0
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-step-02~1]
    async def test_every_branch_performs_exactly_one_live_confirmation(self):
        mutable = Flow()
        await mutable.complete("google")
        assert mutable.lookup.calls == 1
        assert mutable.lookup.clients == [ADMIN_CLIENT]
        idempotent = Flow(stored=IdentityProvider.google, provider_uid=GOOGLE_UID,
                          user=UpgradeUser(id=uuid7(), registered_at=NOW))
        await idempotent.complete("google")
        assert idempotent.lookup.calls == 1

    # [utest->req~users-upgrade-step-02~1]
    async def test_a_second_lookup_in_one_completion_is_refused(self):
        flow = Flow()
        await flow.complete("google")
        with pytest.raises(UpgradeError):
            await flow.endpoint.mandatory_lookup(flow.context)

    # [utest->req~users-upgrade-step-02~1]
    async def test_an_unselectable_admin_client_fails_closed_before_any_write(self):
        flow = Flow(admin=None)
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert flow.lookup.calls == 0
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-step-03~1]
    @pytest.mark.parametrize("provider_data", [
        entries("google.com") + entries("apple.com"),
        entries("google.com") + entries("google.com"),
        entries("facebook.com"),
        entries(""),
    ])
    async def test_every_shape_the_closed_classifier_refuses_rejects_the_mutable_path(
            self, provider_data):
        from nativespeaker.api.auth.create_user import AdminLookupResult

        flow = Flow(lookup=FakeLookup(AdminLookupResult(provider_data=provider_data)))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert raised.value.cause is ProviderNotLinkedCause.invalid_provider_data_shape
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-step-03~1]
    async def test_the_classified_provider_must_equal_the_declaration(self):
        flow = Flow(lookup=FakeLookup(APPLE))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert raised.value.cause is ProviderNotLinkedCause.supported_provider_mismatch
        assert flow.identities.flips == []
        # The matching declaration is confirmed and flips the row.
        apple = Flow(lookup=FakeLookup(APPLE))
        account = await apple.complete("apple", variant=IdentityProvider.apple)
        assert account.identity.provider is IdentityProvider.apple
        assert account.identity.provider_uid == APPLE_UID

    # [utest->req~users-upgrade-step-03~1]
    async def test_a_matching_entry_without_a_uid_is_a_malformed_lookup_result(self):
        from nativespeaker.api.auth.create_user import AdminLookupResult

        flow = Flow(lookup=FakeLookup(AdminLookupResult(provider_data=entries("google.com", ""))))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert raised.value.error_code == ClientErrorClass.verification_temporarily_unavailable
        assert flow.identities.flips == []


class TestTransactionAndLocking:
    # [utest->req~users-upgrade-step-04~1]
    async def test_every_write_shares_the_one_completion_transaction(self):
        flow = Flow()
        await flow.complete("google")
        assert len(set(map(id, flow.identities.sessions))) == 1
        session = object()
        assert assert_upgrade_transaction(session, session, session) is session
        with pytest.raises(UpgradeError):
            assert_upgrade_transaction(session, object())

    # [utest->req~users-upgrade-step-05~1]
    async def test_the_row_is_resolved_by_the_verified_pair_and_locked_with_its_user(self):
        flow = Flow()
        await flow.complete("google")
        session = object()
        rows = LockedRows(identity=flow.identity, user=flow.user, locked=IDENTITY_LOCK_ORDER,
                          transaction=session)
        assert resolved_and_locked(rows, issuer=TEST_ISSUER, subject=SUBJECT,
                                   session=session) is rows
        # Locking only one of the two rows, or locking them out of order, is not enough.
        for locked in ((), ("core.external_identities",), ("core.users",),
                       ("core.users", "core.external_identities")):
            with pytest.raises(UpgradeError):
                resolved_and_locked(replace(rows, locked=locked), issuer=TEST_ISSUER,
                                    subject=SUBJECT, session=session)
        # The row must be the one the verified pair resolves to, in this same transaction.
        with pytest.raises(UpgradeError):
            resolved_and_locked(rows, issuer=TEST_ISSUER, subject="another", session=session)
        with pytest.raises(UpgradeError):
            resolved_and_locked(rows, issuer=TEST_ISSUER, subject=SUBJECT, session=object())

    # [utest->req~users-upgrade-step-05~1]
    async def test_an_unresolvable_identity_rejects_without_mutation(self):
        flow = Flow(missing=True)
        with pytest.raises(ChallengeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.preauth_identity_not_allowed
        assert flow.identities.flips == []
        assert flow.audited() == [AuthEventResult.preauth_identity_not_allowed]

    # [utest->req~users-upgrade-step-06~1]
    async def test_an_inactive_identity_or_user_rejects_before_any_mutation(self):
        historical = Flow(state=IdentityState.historical)
        with pytest.raises(ChallengeRejection) as retired:
            await historical.complete("google")
        assert retired.value.result is AuthEventResult.historical_identity
        assert historical.identities.flips == []

        blocked = Flow()
        blocked.identities.user = replace(blocked.user, active=False)
        with pytest.raises(ChallengeRejection) as raised:
            await blocked.complete("google")
        assert raised.value.result is AuthEventResult.blocked_user
        assert blocked.identities.flips == []

    # [utest->req~users-upgrade-step-06~1]
    def test_both_rows_must_be_active(self):
        row = identity_row()
        user = UpgradeUser(id=row.user_id)
        rows = LockedRows(identity=row, user=user, locked=IDENTITY_LOCK_ORDER)
        assert assert_rows_active(rows) is rows
        with pytest.raises(UpgradeRejection):
            assert_rows_active(replace(rows, identity=replace(
                row, identity_state=IdentityState.historical)))
        with pytest.raises(UpgradeRejection):
            assert_rows_active(replace(rows, user=replace(user, active=False)))


# --- Mutation rule 7: the complete case matrix -------------------------------------------------


class TestCaseMatrix:
    # [utest->req~users-upgrade-step-07~1]
    async def test_the_mutable_flip_sets_provider_uid_registered_at_and_a_verified_email(self):
        flow = Flow()
        account = await flow.complete("google")
        assert account.identity.provider is IdentityProvider.google
        # `provider_uid` comes from the matching `providerData.uid`, and nowhere else.
        assert account.identity.provider_uid == GOOGLE_UID
        assert account.user.registered_at == NOW
        assert account.user.email == "user@example.com"

    # [utest->req~users-upgrade-step-07~1]
    def test_the_flip_never_overwrites_a_stored_email_or_registered_at(self):
        stored = UpgradeUser(id=uuid7(), email="kept@example.com", registered_at=LATER)
        upgraded = upgraded_user(stored, AdminUserRecord(email="new@example.com",
                                                         email_verified=True),
                                 provider=IdentityProvider.google, now=NOW)
        assert upgraded.email == "kept@example.com"
        assert upgraded.registered_at == LATER

    # [utest->req~users-upgrade-step-07~1]
    @pytest.mark.parametrize("record", [
        None,
        AdminUserRecord(email="user@example.com", email_verified=False),
        AdminUserRecord(email="", email_verified=True),
    ])
    def test_the_email_is_copied_only_from_a_verified_non_empty_admin_address(self, record):
        user = UpgradeUser(id=uuid7())
        upgraded = upgraded_user(user, record, provider=IdentityProvider.google, now=NOW)
        assert upgraded.email is None
        assert upgraded.registered_at == NOW

    # [utest->req~users-upgrade-step-07~1]
    async def test_an_agreeing_registered_row_is_idempotent_no_op_success(self):
        flow = Flow(stored=IdentityProvider.google, provider_uid=GOOGLE_UID,
                    user=UpgradeUser(id=uuid7(), registered_at=LATER, email="kept@example.com"))
        before = flow.identity
        account = await flow.complete("google")
        assert account.branch is UpgradeBranch.idempotent
        assert account.identity == before
        assert account.user is flow.user
        # Nothing at all was written: the no-op reaches no persistence call.
        assert flow.identities.flips == []
        assert flow.audited() == [AuthEventResult.succeeded]

    # [utest->req~users-upgrade-step-07~1]
    async def test_a_row_created_directly_as_registered_repeats_idempotently(self):
        # No anonymous phase ever existed for this account; the repeat still confirms live and
        # still mutates nothing.
        flow = Flow(stored=IdentityProvider.apple, provider_uid=APPLE_UID,
                    user=UpgradeUser(id=uuid7(), registered_at=LATER),
                    lookup=FakeLookup(APPLE))
        account = await flow.complete("apple", variant=IdentityProvider.apple)
        assert account.branch is UpgradeBranch.idempotent
        assert flow.lookup.calls == 1
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-step-07~1]
    async def test_an_unconfirming_live_result_rejects_the_mutable_path_without_mutation(self):
        for lookup, cause in ((FakeLookup(ANONYMOUS), ProviderNotLinkedCause.empty_provider_data),
                              (FakeLookup(APPLE),
                               ProviderNotLinkedCause.supported_provider_mismatch)):
            flow = Flow(lookup=lookup)
            with pytest.raises(UpgradeRejection) as raised:
                await flow.complete("google")
            assert raised.value.result is AuthEventResult.provider_not_linked
            assert raised.value.cause is cause
            assert flow.identities.identity.provider is IdentityProvider.anonymous
            assert flow.identities.identity.provider_uid is None
            assert flow.identities.flips == []

    # [utest->req~users-upgrade-step-07~1]
    async def test_a_divergent_live_uid_on_an_idempotent_repeat_is_the_transition_conflict(self):
        from nativespeaker.api.auth.create_user import AdminLookupResult

        flow = Flow(stored=IdentityProvider.google, provider_uid="stored-google-uid",
                    user=UpgradeUser(id=uuid7(), registered_at=LATER),
                    lookup=FakeLookup(AdminLookupResult(
                        provider_data=entries("google.com", "different-google-uid"))))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_transition_not_allowed
        # The stored provider and `provider_uid` remain unchanged.
        assert flow.identities.identity.provider is IdentityProvider.google
        assert flow.identities.identity.provider_uid == "stored-google-uid"
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-step-07~1]
    async def test_a_stored_registered_provider_other_than_the_declared_one_is_never_rewritten(self):
        flow = Flow(stored=IdentityProvider.apple, provider_uid=APPLE_UID,
                    user=UpgradeUser(id=uuid7(), registered_at=LATER),
                    lookup=FakeLookup(GOOGLE))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_transition_not_allowed
        assert flow.identities.identity.provider is IdentityProvider.apple
        assert flow.identities.identity.provider_uid == APPLE_UID
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-step-07~1]
    async def test_divergent_live_provider_data_on_an_idempotent_repeat_is_not_provider_not_linked(
            self):
        flow = Flow(stored=IdentityProvider.google, provider_uid=GOOGLE_UID,
                    user=UpgradeUser(id=uuid7(), registered_at=LATER),
                    lookup=FakeLookup(ANONYMOUS))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_transition_not_allowed
        assert raised.value.cause is None
        assert flow.identities.flips == []


# --- Mutation rules 8 to 14 --------------------------------------------------------------------


class TestPersistenceRules:
    # [utest->req~users-upgrade-step-08~1]
    async def test_a_reserved_provider_account_rejects_and_changes_nothing(self):
        flow = Flow(conflict=True)
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.provider_account_already_linked
        assert raised.value.error_code == ClientErrorClass.operation_not_allowed
        assert flow.identities.identity.provider is IdentityProvider.anonymous
        assert flow.identities.identity.provider_uid is None
        assert flow.identities.user.registered_at is None
        assert flow.identities.preserved == PRESERVED
        assert flow.audited() == [AuthEventResult.provider_account_already_linked]

    # [utest->req~users-upgrade-step-08~1]
    def test_the_flip_writes_under_the_partial_reservation_that_spans_historical_rows(self):
        assert assert_reservation_scope() is None

    # [utest->req~users-upgrade-step-09~1]
    async def test_the_upgrade_creates_no_row_and_retires_none(self):
        assert UPGRADE_CREATED_IDENTITY_ROWS == frozenset()
        assert UPGRADE_RETIRED_IDENTITY_ROWS == frozenset()
        flow = Flow()
        before = flow.identity
        account = await flow.complete("google")
        assert account.identity.id == before.id
        assert account.identity.identity_state is IdentityState.active
        assert len(flow.identities.flips) == 1

    # [utest->req~users-upgrade-step-09~1]
    def test_no_path_flips_a_registered_row_back_or_rebinds_it(self):
        registered = identity_row(IdentityProvider.google, GOOGLE_UID)
        assert assert_in_place(registered, registered) is None
        with pytest.raises(UpgradeError):
            assert_in_place(registered, replace(registered, provider=IdentityProvider.anonymous,
                                                provider_uid=None))
        with pytest.raises(UpgradeError):
            assert_in_place(registered, replace(registered, provider=IdentityProvider.apple,
                                                provider_uid=APPLE_UID))
        anonymous = identity_row()
        with pytest.raises(UpgradeError):
            assert_in_place(anonymous, replace(anonymous, identity_state=IdentityState.historical))
        with pytest.raises(UpgradeError):
            assert_in_place(anonymous, replace(anonymous, id=uuid7()))

    # [utest->req~users-upgrade-step-10~1]
    async def test_the_provider_uid_registered_at_and_email_commit_together(self):
        flow = Flow()
        account = await flow.complete("google")
        identity, user = flow.identities.flips[0]
        assert (identity.provider, identity.provider_uid) == (IdentityProvider.google, GOOGLE_UID)
        assert user.registered_at == NOW and user.email == "user@example.com"
        assert (account.identity, account.user) == (identity, user)

    # [utest->req~users-upgrade-step-10~1]
    def test_registered_at_is_set_because_and_only_because_the_provider_is_registered(self):
        user = UpgradeUser(id=uuid7())
        # An anonymous provider can never pair with a set `registered_at`: the code in the
        # transaction enforces the pairing, with no cross-table trigger behind it.
        with pytest.raises(ProfileError):
            upgraded_user(user, None, provider=IdentityProvider.anonymous, now=NOW)

    # [utest->req~users-upgrade-step-10~1]
    async def test_display_name_is_not_populated_from_auth_context(self):
        flow = Flow(user=UpgradeUser(id=uuid7(), display_name=None))
        account = await flow.complete("google")
        assert account.user.display_name is None
        kept = upgraded_user(UpgradeUser(id=uuid7(), display_name="Chosen"),
                             AdminUserRecord(email="user@example.com", email_verified=True),
                             provider=IdentityProvider.google, now=NOW)
        assert kept.display_name == "Chosen"

    # [utest->req~users-upgrade-step-11~1]
    async def test_chats_grants_usage_subscriptions_and_tokens_all_survive(self):
        flow = Flow()
        await flow.complete("google")
        assert flow.identities.preserved == PRESERVED
        # A completion that lost any of them fails closed rather than committing.
        for name in PRESERVED_BUSINESS_STATE:
            with pytest.raises(UpgradeError):
                assert_state_preserved(PRESERVED, {**PRESERVED, name: "changed"})

    # [utest->req~users-upgrade-step-11~1]
    def test_no_attribution_token_is_generated_moved_or_retired(self):
        assert ATTRIBUTION_TOKEN_MUTATIONS == frozenset()
        owner = uuid7()
        assert assert_state_preserved(PRESERVED, PRESERVED, user_id=owner,
                                      attribution_owners=(owner, owner)) is None
        with pytest.raises(UpgradeError):
            assert_state_preserved(PRESERVED, PRESERVED, user_id=owner,
                                   attribution_owners=(owner, uuid7()))

    # [utest->req~users-upgrade-step-12~1]
    async def test_the_completion_updates_identity_metadata_only(self):
        assert UPGRADE_GRANT_WRITES == frozenset()
        assert UPGRADE_DEVICE_GRANT_BITS == frozenset()
        flow = Flow()
        await flow.complete("google")
        assert flow.identities.preserved["access_grants"] == PRESERVED["access_grants"]
        assert assert_identity_metadata_only() is None
        with pytest.raises(IntroductoryEntitlementError):
            assert_identity_metadata_only(grants=["registered_account_grant"])
        with pytest.raises(UpgradeError):
            assert_identity_metadata_only(device_bits=["ios_devicecheck"])
        with pytest.raises(UpgradeError):
            assert_identity_metadata_only(registered_grant_claimed=True)

    # [utest->req~users-upgrade-step-13~1]
    async def test_the_success_row_carries_the_movement_context_and_the_stored_provider(self):
        flow = Flow()
        account = await flow.complete("google")
        details = account.audit_details
        resolved = details["resolved"]
        assert resolved["source_user_id"] is not None
        assert resolved["source_user_id"] == resolved["destination_user_id"]
        assert resolved["source_external_identity_id"] == \
            resolved["destination_external_identity_id"]
        assert str(resolved["destination_external_identity_id"]) == str(account.identity.id)
        assert details["mutation"]["movement_classification"] == "upgrade"
        assert details["mutation"]["current_identity_provider"] == "google"
        assert resolved["challenge_row_id"] is not None
        assert "challenge_id" not in str(details)
        # The row is written in the same transaction as the consumption and the flip.
        assert flow.audited() == [AuthEventResult.succeeded]
        assert flow.row().state is ChallengeState.consumed

    # [utest->req~users-upgrade-step-13~1]
    async def test_the_idempotent_no_op_records_the_stored_provider_after_the_decision(self):
        flow = Flow(stored=IdentityProvider.apple, provider_uid=APPLE_UID,
                    user=UpgradeUser(id=uuid7(), registered_at=LATER),
                    lookup=FakeLookup(APPLE))
        account = await flow.complete("apple", variant=IdentityProvider.apple)
        assert account.audit_details["mutation"]["current_identity_provider"] == "apple"

    # [utest->req~users-upgrade-step-14~1]
    async def test_the_response_is_backend_state_with_no_backend_token(self):
        flow = Flow()
        account = await flow.complete("google")
        assert isinstance(account, UpgradedAccount)
        assert account.backend_token is None
        assert account.identity.provider is IdentityProvider.google


# --- The client's obligations and the two untouched accounts -----------------------------------


class TestRepairObligation:
    # [utest->req~users-client-repair-obligation~1]
    def test_repair_is_needed_while_firebase_is_ahead_of_the_backend(self):
        assert repair_needed(backend_provider=IdentityProvider.anonymous,
                             firebase_provider=IdentityProvider.google) is True
        assert repair_needed(backend_provider=IdentityProvider.anonymous,
                             firebase_provider=IdentityProvider.anonymous) is False
        assert repair_needed(backend_provider=IdentityProvider.google,
                             firebase_provider=IdentityProvider.google) is False
        # The two surfaces the comparison reads the backend's classification from.
        assert REPAIR_READ_SURFACES == (("POST", "/auth/sync"), ("GET", "/users/me"))
        # No challenge type, webhook, polling mechanism or scheduled reconciliation job.
        assert REPAIR_MECHANISMS == frozenset()

    # [utest->req~users-client-repair-obligation~1]
    def test_an_operation_not_allowed_conflict_is_terminal_and_the_rest_is_retried(self):
        assert repair_disposition(ClientErrorClass.operation_not_allowed) is RepairRetry.terminal
        assert repair_disposition(ClientErrorClass.challenge_required) is \
            RepairRetry.fresh_challenge
        for client_class in (ClientErrorClass.verification_temporarily_unavailable,
                             ClientErrorClass.auth_required):
            assert repair_disposition(client_class) is RepairRetry.retry


class TestUntouchedAccounts:
    # [utest->req~users-credential-already-in-use-handling~1]
    async def test_a_failed_client_link_never_mutates_the_source_anonymous_account(self):
        # The client called the endpoint anyway: mandatory Admin confirmation fails and the
        # source anonymous account is left exactly as it was, with no grant minted.
        flow = Flow(lookup=FakeLookup(ANONYMOUS))
        with pytest.raises(UpgradeRejection):
            await flow.complete("google")
        assert flow.identities.identity == flow.identity
        assert flow.identities.user == flow.user
        assert flow.identities.preserved == PRESERVED

    # [utest->req~users-credential-already-in-use-handling~1]
    def test_the_new_pair_goes_through_normal_resolution_with_no_special_case(self):
        assert credential_already_in_use_route(ResolutionOutcome.linked) is None
        assert credential_already_in_use_route(ResolutionOutcome.pre_auth) == \
            ("POST", "/auth/create-user")
        with pytest.raises(UpgradeRejection) as historical:
            credential_already_in_use_route(ResolutionOutcome.historical_identity)
        assert historical.value.result is AuthEventResult.historical_identity
        with pytest.raises(UpgradeRejection) as blocked:
            credential_already_in_use_route(ResolutionOutcome.blocked_user)
        assert blocked.value.result is AuthEventResult.blocked_user

    # [utest->req~users-abandoned-anonymous-account-untouched~1]
    def test_the_abandoned_anonymous_account_is_left_exactly_as_it_is(self):
        assert ABANDONED_ACCOUNT_MUTATIONS == frozenset()
        assert ABANDONED_ACCOUNT_MECHANISMS == frozenset()
        row = identity_row()
        user = UpgradeUser(id=row.user_id)
        assert abandoned_anonymous_account(row, user, grants=("grant-1",)) == (row, user)
        with pytest.raises(UpgradeError):
            abandoned_anonymous_account(replace(row, identity_state=IdentityState.historical), user)
        with pytest.raises(UpgradeError):
            abandoned_anonymous_account(row, replace(user, active=False))
        with pytest.raises(UpgradeError):
            abandoned_anonymous_account(row, UpgradeUser(id=uuid7()), grants=("grant-1",))


# --- Failure classification and the audit row ---------------------------------------------------


class TestFailures:
    # [utest->req~users-upgrade-failure-scope~1]
    @pytest.mark.parametrize(("condition", "expected"), [
        ("identity_not_resolved", AuthEventResult.preauth_identity_not_allowed),
        ("identity_inactive", AuthEventResult.historical_identity),
        ("user_inactive", AuthEventResult.blocked_user),
        ("declared_provider_missing_or_invalid", AuthEventResult.challenge_operation_mismatch),
        ("live_confirmation_failed", AuthEventResult.provider_not_linked),
        ("stored_live_binding_divergence", AuthEventResult.provider_transition_not_allowed),
        ("provider_account_uniqueness_conflict",
         AuthEventResult.provider_account_already_linked),
        ("lookup_failed_after_retry_budget", AuthEventResult.firebase_lookup_unavailable),
        ("lookup_non_retryable", AuthEventResult.firebase_user_unresolved),
        ("policy_rejected", AuthEventResult.policy_rejected),
    ])
    def test_every_named_rejection_condition_has_its_internal_result(self, condition, expected):
        assert upgrade_failure_result(condition) is expected
        with pytest.raises(UpgradeError):
            upgrade_failure_result("some_unnamed_condition")

    # [utest->req~users-upgrade-error-class-mapping~1]
    @pytest.mark.parametrize(("result", "expected"), [
        (AuthEventResult.invalid_external_jwt, "auth_required"),
        (AuthEventResult.firebase_user_unresolved, "auth_required"),
        (AuthEventResult.preauth_identity_not_allowed, "preauth_identity_not_allowed"),
        (AuthEventResult.historical_identity, "account_unavailable"),
        (AuthEventResult.blocked_user, "account_unavailable"),
        (AuthEventResult.challenge_not_found, "challenge_required"),
        (AuthEventResult.challenge_expired, "challenge_required"),
        (AuthEventResult.challenge_consumed, "challenge_required"),
        (AuthEventResult.challenge_identity_mismatch, "challenge_required"),
        (AuthEventResult.challenge_operation_mismatch, "challenge_required"),
        (AuthEventResult.policy_rejected, "operation_not_allowed"),
        (AuthEventResult.provider_not_linked, "operation_not_allowed"),
        (AuthEventResult.provider_transition_not_allowed, "operation_not_allowed"),
        (AuthEventResult.provider_account_already_linked, "operation_not_allowed"),
        (AuthEventResult.firebase_lookup_unavailable, "verification_temporarily_unavailable"),
    ])
    def test_each_internal_result_maps_to_its_client_class(self, result, expected):
        assert upgrade_client_class(result) == expected
        with pytest.raises(UpgradeError):
            upgrade_client_class(AuthEventResult.internal_error)

    # [utest->req~users-upgrade-mutable-path-provider-not-linked-audit~1]
    @pytest.mark.parametrize("cause", list(ProviderNotLinkedCause))
    def test_the_bounded_cause_travels_in_the_audit_details(self, cause):
        rejection = mutable_path_rejection(cause)
        assert rejection.result is AuthEventResult.provider_not_linked
        assert rejection.error_code == ClientErrorClass.operation_not_allowed
        assert rejection.detail == cause.value
        assert provider_not_linked_details(cause)["failure"]["reason"] == cause.value

    # [utest->req~users-upgrade-mutable-path-provider-not-linked-audit~1]
    async def test_the_mutable_path_audits_provider_not_linked_with_its_cause(self):
        flow = Flow(lookup=FakeLookup(APPLE))
        with pytest.raises(UpgradeRejection):
            await flow.complete("google")
        assert flow.audited() == [AuthEventResult.provider_not_linked]
        assert flow.details()["failure"]["reason"] == \
            ProviderNotLinkedCause.supported_provider_mismatch.value

    # [utest->req~users-upgrade-provider-transition-not-allowed-audit~1]
    @pytest.mark.parametrize("divergence", list(TransitionDivergence))
    def test_every_registered_binding_divergence_is_the_one_transition_conflict(self, divergence):
        assert TRANSITION_REJECTION_MUTATIONS == frozenset()
        rejection = transition_rejection(divergence)
        assert rejection.result is AuthEventResult.provider_transition_not_allowed
        assert rejection.error_code == ClientErrorClass.operation_not_allowed
        assert rejection.divergence is divergence

    # [utest->req~users-upgrade-provider-account-already-linked-audit~1]
    async def test_the_provider_account_conflict_is_audited_distinctly(self):
        rejection = provider_conflict_rejection()
        assert rejection.result is AuthEventResult.provider_account_already_linked
        assert rejection.error_code == ClientErrorClass.operation_not_allowed
        flow = Flow(conflict=True)
        with pytest.raises(UpgradeRejection):
            await flow.complete("google")
        assert flow.audited() == [AuthEventResult.provider_account_already_linked]
        assert flow.identities.flips == []

    # [utest->req~users-upgrade-firebase-user-not-found~1]
    async def test_a_deleted_subject_is_non_retryable_and_persists_nothing(self):
        from nativespeaker.api.auth.create_user import lookup_failure
        from nativespeaker.api.auth.external_identities import LookupFailure

        failure = lookup_failure(LookupFailure.user_not_found)
        flow = Flow(lookup=FakeLookup(failures=[failure] * 3))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.firebase_user_unresolved
        assert raised.value.error_code == ClientErrorClass.auth_required
        # It consumes no retry budget: the single attempt is not retried.
        assert flow.lookup.calls == 1
        assert flow.identities.flips == []
        assert flow.audited() == [AuthEventResult.firebase_user_unresolved]

    # [utest->req~users-upgrade-lookup-unavailable~1]
    @pytest.mark.parametrize("failure", ["transient", "infrastructure", "malformed_response",
                                         "indeterminate"])
    async def test_an_indeterminate_lookup_surfaces_after_the_retry_budget(self, failure):
        from nativespeaker.api.auth.create_user import lookup_failure
        from nativespeaker.api.auth.external_identities import LookupFailure

        error = lookup_failure(LookupFailure(failure))
        flow = Flow(lookup=FakeLookup(failures=[error] * 3))
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert raised.value.error_code == ClientErrorClass.verification_temporarily_unavailable
        assert flow.lookup.calls == 3
        assert flow.identities.flips == []
        assert flow.audited() == [AuthEventResult.firebase_lookup_unavailable]

    # [utest->req~users-upgrade-lookup-unavailable~1]
    async def test_an_issuer_mismatch_is_rejected_before_the_lookup(self):
        flow = Flow()
        other = replace(flow.context, issuer="https://securetoken.google.com/other")
        with pytest.raises(InvalidExternalJwtError):
            await flow.endpoint.mandatory_lookup(other)
        assert flow.lookup.calls == 0

    # [utest->req~users-upgrade-rejection-consumes-challenge~1]
    async def test_a_rejection_at_or_after_the_lookup_consumes_the_challenge(self):
        flow = Flow(lookup=FakeLookup(APPLE))
        row = await flow.prepare()
        with pytest.raises(UpgradeRejection):
            await flow.h.service.complete(UPGRADE, "google", row.challenge_id, flow.context,
                                          flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "google"})
        assert flow.row().state is ChallengeState.consumed
        # A retry requires a freshly prepared challenge.
        with pytest.raises(ChallengeRejection) as retry:
            await flow.h.service.complete(UPGRADE, "google", row.challenge_id, flow.context,
                                          flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "google"})
        assert retry.value.result is AuthEventResult.challenge_consumed

    # [utest->req~users-upgrade-audit-specific-result~1]
    async def test_the_audited_result_is_the_specific_internal_one(self):
        flow = Flow(conflict=True)
        with pytest.raises(UpgradeRejection) as raised:
            await flow.complete("google")
        assert raised.value.error_code == ClientErrorClass.operation_not_allowed
        assert flow.audited() == [AuthEventResult.provider_account_already_linked]

    # [utest->req~users-upgrade-audit-specific-result~1]
    def test_two_results_sharing_a_class_stay_distinct_in_the_row(self):
        for result in (AuthEventResult.historical_identity, AuthEventResult.blocked_user):
            assert audited_upgrade_result(result, "account_unavailable") is result
        for result in (AuthEventResult.provider_not_linked,
                       AuthEventResult.provider_transition_not_allowed,
                       AuthEventResult.provider_account_already_linked,
                       AuthEventResult.policy_rejected):
            assert audited_upgrade_result(result, "operation_not_allowed") is result
        with pytest.raises(UpgradeError):
            audited_upgrade_result(AuthEventResult.internal_error, "internal_error")

    # [utest->req~users-upgrade-audit-row-requirements~1]
    def test_a_rejected_attempt_records_null_for_what_it_could_not_resolve(self):
        assert UPGRADE_AUDIT_BEST_EFFORT is False
        details = upgrade_attempt_audit(result=AuthEventResult.provider_not_linked,
                                        occurred_at=NOW)
        resolved = details["resolved"]
        for key in ("source_user_id", "source_external_identity_id", "destination_user_id",
                    "destination_external_identity_id", "challenge_row_id"):
            assert resolved[key] is None
        assert details["mutation"]["movement_classification"] == "upgrade"
        assert "challenge_id" not in str(details)

    # [utest->req~users-upgrade-audit-row-requirements~1]
    def test_an_attempt_writes_only_the_auth_events_row(self):
        assert UPGRADE_AUDIT_ROWS == ("audit.auth_events",)
        with pytest.raises(UpgradeError):
            upgrade_attempt_audit(result=AuthEventResult.provider_not_linked, occurred_at=NOW,
                                  rows_written=("audit.auth_events", "core.upgrade_attempts"))

    # [utest->req~users-upgrade-audit-row-requirements~1]
    async def test_every_attempt_that_reaches_the_audited_path_writes_its_row(self):
        for flow, expected in ((Flow(), AuthEventResult.succeeded),
                               (Flow(lookup=FakeLookup(ANONYMOUS)),
                                AuthEventResult.provider_not_linked),
                               (Flow(conflict=True),
                                AuthEventResult.provider_account_already_linked)):
            try:
                await flow.complete("google")
            except (UpgradeRejection, ProviderLookupFailedError):
                pass
            assert flow.audited() == [expected]
            assert flow.details()["mutation"]["movement_classification"] == "upgrade"
            assert "challenge_id" not in str(flow.details())
            # Both ends of the movement are the one locked identity row and its user, on the
            # rejections as well as on the success: nothing known is recorded as NULL.
            resolved = flow.details()["resolved"]
            assert resolved["source_user_id"] == flow.user.id
            assert resolved["destination_user_id"] == flow.user.id
            assert resolved["source_external_identity_id"] == flow.identity.id
            assert resolved["destination_external_identity_id"] == flow.identity.id
            assert resolved["challenge_row_id"] == flow.row().id

    # [utest->req~users-upgrade-audit-row-requirements~1]
    async def test_a_step_06_rejection_records_the_rows_it_locked(self):
        for flow in (Flow(state=IdentityState.historical),
                     Flow(user=UpgradeUser(id=uuid7(), active=False))):
            with pytest.raises(UpgradeRejection):
                await flow.complete("google")
            resolved = flow.details()["resolved"]
            assert resolved["source_user_id"] == flow.user.id
            assert resolved["source_external_identity_id"] == flow.identity.id
            assert flow.details()["mutation"]["current_identity_provider"] == \
                str(flow.identity.provider)
