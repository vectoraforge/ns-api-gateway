"""`create_user`: the mandatory Firebase Admin lookup and its closed classification, the account
and identity state the completion transaction writes, the profile rules that commit with it, and
the endpoint's own rejection classes."""

from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import pytest

from nativespeaker.api.auth.audit import AuthEventResult
from nativespeaker.api.auth.barrier import ResolutionOutcome
from nativespeaker.api.auth.challenges import ChallengeState
from nativespeaker.api.auth.create_user import (
    CREATE_FLOW_MISMATCH_CLASS,
    CREATE_USER_RESULTS,
    AdminLookupResult,
    CreateFlow,
    CreateUserEndpoint,
    CreateUserError,
    CreateUserRejection,
    NewUser,
    ProviderNotLinkedCause,
    assert_no_monthly_usage_row,
    assert_no_provider_header_requirement,
    assert_one_transaction,
    assert_pairing_enforced_in_code,
    assert_valid_without_grant,
    audited_result_for,
    classify_admin_provider_data,
    classify_lookup_error,
    confirm_declaration,
    create_flow_mismatch_response,
    create_user_client_class,
    lookup_failure,
    lost_response_recovery,
    mint_attribution_tokens,
    new_user_row,
    onboarding_audit_details,
    provider_not_linked_details,
    race_loser_rejection,
    rejects_before_commit,
    required_flow_for,
)
from nativespeaker.api.auth.external_identities import (
    ExternalIdentities,
    ExternalIdentityRow,
    IdentityAlreadyLinkedError,
    IdentityState,
    LookupFailure,
    ProviderLookupFailedError,
    provider_account_conflict,
)
from nativespeaker.api.auth.integration import FirebaseIntegration, FirebaseIntegrations
from nativespeaker.api.auth.invariants import AttributionTokens, StoreProvider
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider
from nativespeaker.api.auth.procedures import ChallengeRejection
from nativespeaker.api.auth.profile import AdminUserRecord
from nativespeaker.api.auth.taxonomy import ClientErrorClass
from nativespeaker.api.auth.tokens import FirebaseIdTokenVerifier, InvalidExternalJwtError
from unit.conftest import PUBLIC_KEY_PEM, TEST_ISSUER
from unit.test_auth_challenges import Harness
from unit.test_auth_challenges import preauth_context as preauth_challenge_context

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _lookup_error(failure: LookupFailure) -> ProviderLookupFailedError:
    return lookup_failure(failure)


def entries(provider_id: str, uid: str = "provider-account-uid") -> tuple[dict[str, str], ...]:
    return ({"provider_id": provider_id, "uid": uid},)


GOOGLE = AdminLookupResult(provider_data=entries("google.com", "google-account-id"),
                           email="user@example.com", email_verified=True)
APPLE = AdminLookupResult(provider_data=entries("apple.com", "apple-user-id"))
ANONYMOUS = AdminLookupResult()


class FakeAccounts:
    """The database half of the onboarding transaction: the two uniqueness rules the completion
    can lose against, and the rows it writes."""

    def __init__(self, outcome: ResolutionOutcome = ResolutionOutcome.pre_auth) -> None:
        self.identities = ExternalIdentities()
        self.attribution = AttributionTokens()
        self.users: dict[Any, NewUser] = {}
        self.reserved: dict[tuple[str, str, str], Any] = {}
        self.outcome = outcome
        self.sessions: list[Any] = []
        self.raises: Exception | None = None

    async def resolve(self, session, issuer, subject) -> ResolutionOutcome:
        return self.outcome

    def _snapshot(self):
        return (dict(self.users), deepcopy(self.identities), deepcopy(self.attribution),
                dict(self.reserved))

    def _restore(self, snapshot) -> None:
        self.users, self.identities, self.attribution, self.reserved = snapshot

    async def insert_account(self, session, *, user, identity, tokens) -> None:
        self.sessions.append(session)
        # The rows land in the transaction before the constraint that may reject them, exactly
        # as the real inserts do, and the session's savepoint is what takes them back out again.
        session.on_rollback(self._restore_to(self._snapshot()))
        self.users[user.id] = user
        self.identities.link(identity)
        for store, value in tokens.items():
            self.attribution.mint(user.id, StoreProvider(store), value)
        key = (identity.issuer, str(identity.provider), identity.provider_uid or "")
        if identity.provider_uid is not None:
            if key in self.reserved:
                raise provider_account_conflict(AuthOperation.create_user)
            self.reserved[key] = user.id
        if self.raises is not None:
            raise self.raises

    def _restore_to(self, snapshot):
        return lambda: self._restore(snapshot)


class FakeLookup:
    """The one `getUser(subject)` read, counted."""

    def __init__(self, result: AdminLookupResult | None = None,
                 failures: Sequence[Exception] = ()) -> None:
        self.result = result if result is not None else ANONYMOUS
        self.failures = list(failures)
        self.calls = 0
        self.clients: list[Any] = []

    async def __call__(self, client, subject) -> AdminLookupResult:
        self.calls += 1
        self.clients.append(client)
        if self.failures:
            raise self.failures.pop(0)
        return self.result


ADMIN_CLIENT = object()


def integrations(admin: Any = ADMIN_CLIENT) -> FirebaseIntegrations:
    verifier = FirebaseIdTokenVerifier(issuer=TEST_ISSUER, audience="test-project",
                                       key_resolver=lambda _token: PUBLIC_KEY_PEM)
    return FirebaseIntegrations([FirebaseIntegration(issuer=TEST_ISSUER,
                                                     project_id="test-project",
                                                     verifier=verifier, admin_client=admin)])


class Flow:
    """One prepare-and-complete run of the real endpoint through the shared procedures."""

    def __init__(self, *, lookup: FakeLookup | None = None,
                 accounts: FakeAccounts | None = None,
                 admin: Any = ADMIN_CLIENT) -> None:
        self.h = Harness()
        self.accounts = accounts or FakeAccounts()
        self.lookup = lookup or FakeLookup()
        self.endpoint = CreateUserEndpoint(integrations=integrations(admin),
                                           accounts=self.accounts, lookup=self.lookup,
                                           clock=lambda: NOW)
        self.context = preauth_challenge_context(f"preauth-{uuid7()}")

    async def prepare(self, variant: IdentityProvider = IdentityProvider.anonymous):
        await self.h.service.prepare(AuthOperation.create_user, variant, self.context,
                                     self.endpoint)
        return self.h.store.only()

    async def complete(self, declared: str | None = "anonymous", *,
                       variant: IdentityProvider = IdentityProvider.anonymous,
                       body: dict[str, Any] | None = None):
        row = await self.prepare(variant)
        payload: dict[str, Any] = {"challenge_id": row.challenge_id, "provider": declared}
        if body is not None:
            payload = body if "challenge_id" in body else {**payload, **body}
        return await self.h.service.complete(AuthOperation.create_user, declared,
                                             row.challenge_id, self.context, self.endpoint,
                                             body=payload)

    def row(self):
        return self.h.store.only()

    def audited(self) -> list[AuthEventResult]:
        return self.h.sink.results()


# --- Mutation rules 1 to 4: the declaration, the lookup and the classifier --------------------


class TestDeclarationAndLookup:
    # [utest->req~users-create-user-step-01~1]
    async def test_the_completion_provider_must_equal_the_bound_variant_byte_for_byte(self):
        flow = Flow()
        row = await flow.prepare()
        with pytest.raises(CreateUserRejection) as raised:
            # The shared comparison passes and the endpoint reads the request body itself: a
            # case-folded declaration is a mismatch there too, with no re-normalization.
            await flow.h.service.complete(AuthOperation.create_user, "anonymous",
                                          row.challenge_id, flow.context, flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "Anonymous"})
        assert raised.value.result is AuthEventResult.challenge_operation_mismatch
        assert raised.value.error_code == ClientErrorClass.challenge_required
        # The mismatch is decided before any Firebase Admin lookup, and it consumes the row.
        assert flow.lookup.calls == 0
        assert flow.row().state is ChallengeState.consumed

    # [utest->req~users-create-user-step-01~1]
    async def test_a_missing_provider_is_a_mismatch_and_never_defaulted(self):
        flow = Flow()
        row = await flow.prepare()
        with pytest.raises(CreateUserRejection) as raised:
            await flow.h.service.complete(AuthOperation.create_user, "anonymous",
                                          row.challenge_id, flow.context, flow.endpoint,
                                          body={"challenge_id": row.challenge_id})
        assert raised.value.result is AuthEventResult.challenge_operation_mismatch
        assert flow.lookup.calls == 0

    # [utest->req~users-create-user-step-02~1]
    async def test_every_completion_performs_exactly_one_lookup_including_anonymous(self):
        flow = Flow()
        await flow.complete("anonymous")
        assert flow.lookup.calls == 1
        assert flow.lookup.clients == [ADMIN_CLIENT]

        registered = Flow(lookup=FakeLookup(GOOGLE))
        await registered.complete("google", variant=IdentityProvider.google)
        assert registered.lookup.calls == 1

    # [utest->req~users-create-user-step-02~1]
    async def test_the_lookup_uses_the_issuer_selected_client_and_no_branch_skips_it(self):
        flow = Flow()
        endpoint = flow.endpoint
        await flow.complete("anonymous")
        # A second lookup inside one completion is refused: the read is performed exactly once.
        with pytest.raises(CreateUserError):
            await endpoint.mandatory_lookup(flow.context)

    # [utest->req~users-create-user-step-02~1]
    async def test_an_unselectable_admin_client_fails_closed_before_any_write(self):
        flow = Flow(admin=None)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert raised.value.error_code == ClientErrorClass.verification_temporarily_unavailable
        assert flow.lookup.calls == 0
        assert flow.accounts.users == {}
        # The rejection is taken on the claimed row: it consumes the challenge and owes its row.
        assert flow.row().state is ChallengeState.consumed
        assert flow.audited() == [AuthEventResult.firebase_lookup_unavailable]

    # [utest->req~users-create-user-step-03~1]
    @pytest.mark.parametrize(("provider_data", "expected"), [
        ((), IdentityProvider.anonymous),
        (entries("google.com"), IdentityProvider.google),
        (entries("apple.com"), IdentityProvider.apple),
    ])
    def test_the_closed_classifier_reads_exactly_three_shapes(self, provider_data, expected):
        assert classify_admin_provider_data(provider_data) is expected

    # [utest->req~users-create-user-step-03~1]
    @pytest.mark.parametrize("provider_data", [
        entries("google.com") + entries("apple.com"),
        entries("google.com") + entries("google.com"),
        entries("facebook.com"),
        entries("google.com") + entries("facebook.com"),
        entries(""),
    ])
    def test_every_other_shape_is_invalid_and_rejects(self, provider_data):
        with pytest.raises(CreateUserRejection) as raised:
            classify_admin_provider_data(provider_data)
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert raised.value.cause is ProviderNotLinkedCause.invalid_provider_data_shape
        assert raised.value.error_code == ClientErrorClass.operation_not_allowed
        assert raised.value.required_flow is None

    # [utest->req~users-create-user-step-03~1]
    async def test_an_invalid_shape_persists_nothing(self):
        flow = Flow(lookup=FakeLookup(AdminLookupResult(provider_data=entries("facebook.com"))))
        with pytest.raises(CreateUserRejection):
            await flow.complete("anonymous")
        assert flow.accounts.users == {}

    # [utest->req~users-create-user-step-04~1]
    def test_the_sign_in_provider_claim_is_never_a_provider_source(self):
        with pytest.raises(CreateUserError):
            classify_admin_provider_data((), token_claims={"firebase":
                                                           {"sign_in_provider": "google.com"}})

    # [utest->req~users-create-user-step-04~1]
    def test_declared_anonymous_requires_empty_provider_data(self):
        assert confirm_declaration(IdentityProvider.anonymous, ANONYMOUS).provider is \
            IdentityProvider.anonymous
        with pytest.raises(CreateUserRejection) as raised:
            confirm_declaration(IdentityProvider.anonymous, GOOGLE)
        assert raised.value.cause is ProviderNotLinkedCause.supported_provider_mismatch
        assert raised.value.required_flow is CreateFlow.registered

    # [utest->req~users-create-user-step-04~1]
    def test_a_declared_registered_provider_requires_the_matching_classification(self):
        confirmed = confirm_declaration(IdentityProvider.google, GOOGLE)
        assert confirmed.provider is IdentityProvider.google
        assert confirmed.provider_uid == "google-account-id"
        with pytest.raises(CreateUserRejection) as empty:
            confirm_declaration(IdentityProvider.google, ANONYMOUS)
        assert empty.value.cause is ProviderNotLinkedCause.empty_provider_data
        assert empty.value.required_flow is CreateFlow.anonymous
        with pytest.raises(CreateUserRejection) as other:
            confirm_declaration(IdentityProvider.google, APPLE)
        assert other.value.cause is ProviderNotLinkedCause.supported_provider_mismatch

    # [utest->req~users-create-user-step-04~1]
    async def test_a_missing_uid_is_a_malformed_lookup_result_and_persists_nothing(self):
        blank = AdminLookupResult(provider_data=entries("google.com", ""))
        with pytest.raises(CreateUserRejection) as raised:
            confirm_declaration(IdentityProvider.google, blank)
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        # Through the endpoint it is a consuming rejection with its own audit row.
        flow = Flow(lookup=FakeLookup(blank))
        with pytest.raises(CreateUserRejection):
            await flow.complete("google", variant=IdentityProvider.google)
        assert flow.accounts.users == {}
        assert flow.row().state is ChallengeState.consumed
        assert flow.audited() == [AuthEventResult.firebase_lookup_unavailable]

    # [utest->req~users-create-user-step-04~1]
    def test_an_anonymous_creation_stores_no_provider_uid(self):
        assert confirm_declaration(IdentityProvider.anonymous, ANONYMOUS).provider_uid is None


# --- Mutation rules 5 to 14: the completion transaction -----------------------------------------


class TestCompletionTransaction:
    # [utest->req~users-create-user-step-05~1]
    async def test_an_identity_linked_since_prepare_rejects_as_already_linked(self):
        flow = Flow(accounts=FakeAccounts(ResolutionOutcome.linked))
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is AuthEventResult.identity_already_linked
        assert raised.value.error_code == ClientErrorClass.identity_already_linked
        assert flow.accounts.users == {}
        assert flow.audited() == [AuthEventResult.identity_already_linked]

    # [utest->req~users-create-user-step-05~1]
    @pytest.mark.parametrize(("outcome", "result"), [
        (ResolutionOutcome.historical_identity, AuthEventResult.historical_identity),
        (ResolutionOutcome.blocked_user, AuthEventResult.blocked_user),
    ])
    async def test_historical_and_blocked_keep_distinct_results_under_one_class(self, outcome,
                                                                               result):
        flow = Flow(accounts=FakeAccounts(outcome))
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is result
        assert raised.value.error_code == ClientErrorClass.account_unavailable
        assert flow.accounts.users == {}

    # [utest->req~users-create-user-step-06~1]
    # [utest->req~users-create-user-step-07~1]
    async def test_the_user_row_and_one_active_identity_row_are_written_together(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        created = await flow.complete("google", variant=IdentityProvider.google)
        assert flow.accounts.users[created.user.id] is created.user
        row = flow.accounts.identities.find(TEST_ISSUER, flow.context.subject)
        assert row is not None and row.id == created.identity.id
        assert row.user_id == created.user.id
        assert row.identity_state is IdentityState.active
        assert row.provider is IdentityProvider.google
        assert row.provider_uid == "google-account-id"

    # [utest->req~users-create-user-step-07~1]
    async def test_an_anonymous_row_stores_a_null_provider_uid_and_no_sentinel(self):
        flow = Flow()
        created = await flow.complete("anonymous")
        assert created.identity.provider is IdentityProvider.anonymous
        assert created.identity.provider_uid is None

    # [utest->req~users-create-user-step-08~1]
    async def test_a_reserved_provider_account_rejects_and_writes_nothing(self):
        accounts = FakeAccounts()
        accounts.reserved[(TEST_ISSUER, "google", "google-account-id")] = uuid7()
        flow = Flow(lookup=FakeLookup(GOOGLE), accounts=accounts)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("google", variant=IdentityProvider.google)
        assert raised.value.result is AuthEventResult.provider_account_already_linked
        assert raised.value.error_code == ClientErrorClass.operation_not_allowed
        # The user, identity and attribution rows the mutation had already written are rolled
        # back: no user, identity, grant, profile mutation or attribution token survives.
        assert accounts.users == {}
        assert accounts.identities.find(TEST_ISSUER, flow.context.subject) is None
        assert accounts.attribution.token_for(uuid7(), StoreProvider.apple) is None
        assert flow.h.factory.log.count("rollback_to_savepoint") == 1
        # The consumption and the rejected audit row survive that rollback.
        assert flow.row().state is ChallengeState.consumed
        assert flow.audited() == [AuthEventResult.provider_account_already_linked]

    # [utest->req~users-create-user-step-09~1]
    async def test_one_random_attribution_token_per_store_is_minted_once(self):
        flow = Flow()
        created = await flow.complete("anonymous")
        assert sorted(created.attribution_tokens) == ["apple", "google_play"]
        assert len(set(created.attribution_tokens.values())) == 2
        for store, value in created.attribution_tokens.items():
            assert flow.accounts.attribution.token_for(created.user.id,
                                                       StoreProvider(store)) == value
        # A second mint for the same user and store is refused for the life of the account.
        with pytest.raises(Exception):
            flow.accounts.attribution.mint(created.user.id, StoreProvider.apple, "another")

    # [utest->req~users-create-user-step-09~1]
    async def test_a_rejected_completion_mints_nothing(self):
        flow = Flow(accounts=FakeAccounts(ResolutionOutcome.linked))
        with pytest.raises(CreateUserRejection):
            await flow.complete("anonymous")
        assert flow.accounts.users == {}
        assert flow.accounts.attribution.owner_of(StoreProvider.apple, "any") is None

    # [utest->req~users-create-user-step-09~1]
    def test_each_store_gets_its_own_random_uuid(self):
        first, second = mint_attribution_tokens(), mint_attribution_tokens()
        assert sorted(first) == ["apple", "google_play"]
        assert set(first.values()).isdisjoint(second.values())

    # [utest->req~users-create-user-step-10~1]
    # [utest->req~users-profile-no-grant-required~1]
    def test_no_access_grant_is_created(self):
        user = NewUser(id=uuid7())
        assert assert_valid_without_grant(user) is user
        with pytest.raises(CreateUserError):
            assert_valid_without_grant(user, grants=["anonymous_free_credits"])

    # [utest->req~users-create-user-step-11~1]
    def test_no_monthly_usage_row_is_created(self):
        assert_no_monthly_usage_row()
        with pytest.raises(CreateUserError):
            assert_no_monthly_usage_row(["user_monthly_usage"])

    # [utest->req~users-create-user-state-only-no-credits~1]
    async def test_create_user_creates_account_and_identity_state_only(self):
        flow = Flow()
        created = await flow.complete("anonymous")
        assert flow.accounts.users.keys() == {created.user.id}
        assert flow.accounts.identities.find(TEST_ISSUER, flow.context.subject) is not None
        assert created.audit_details["mutation"]["registered"] is False

    # [utest->req~users-create-user-step-12~1]
    async def test_the_success_audit_row_captures_the_committed_mutation(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        created = await flow.complete("google", variant=IdentityProvider.google)
        assert flow.audited() == [AuthEventResult.succeeded]
        details = created.audit_details
        assert details["resolved"]["user_id"] == str(created.user.id)
        assert details["resolved"]["external_identity_id"] == str(created.identity.id)
        assert details["mutation"]["identity_provider"] == "google"
        assert details["mutation"]["registered"] is True
        assert details["mutation"]["attribution_stores"] == ["apple", "google_play"]

    # [utest->req~users-create-user-step-12~1]
    def test_a_record_that_does_not_capture_the_mutation_fails_closed(self):
        user = NewUser(id=uuid7())
        identity = ExternalIdentityRow(id=uuid7(), user_id=user.id, issuer=TEST_ISSUER,
                                       subject="s", provider=IdentityProvider.anonymous)
        tokens = mint_attribution_tokens()
        details = onboarding_audit_details(user=user, identity=identity, tokens=tokens)
        # The token values themselves are not part of the record.
        assert not any(value in str(details) for value in tokens.values())

    # [utest->req~users-create-user-step-13~1]
    async def test_every_write_shares_the_one_consuming_transaction_that_commits(self):
        flow = Flow()
        await flow.complete("anonymous")
        session = flow.accounts.sessions[-1]
        assert flow.h.factory.sessions == [session]
        assert session.committed is True
        assert flow.h.factory.log.count("commit") == 1

    # [utest->req~users-create-user-step-13~1]
    def test_a_write_outside_that_transaction_fails_closed(self):
        session = object()
        assert assert_one_transaction(session, session) is session
        with pytest.raises(CreateUserError):
            assert_one_transaction(session, object())

    # [utest->req~users-create-user-step-14~1]
    async def test_the_backend_state_is_returned_with_no_backend_token(self):
        flow = Flow()
        created = await flow.complete("anonymous")
        assert created.backend_token is None
        assert created.user.id == created.identity.user_id
        assert flow.row().state is ChallengeState.consumed


# --- The concurrent race ---------------------------------------------------------------------


class TestRaceArbitration:
    # [utest->req~users-create-user-race-arbitration~1]
    async def test_the_loser_rolls_back_and_returns_the_already_linked_conflict(self):
        accounts = FakeAccounts()
        accounts.raises = IdentityAlreadyLinkedError("the winner got there first")
        flow = Flow(accounts=accounts)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is AuthEventResult.identity_already_linked
        assert raised.value.error_code == ClientErrorClass.identity_already_linked
        assert raised.value.status_code == 409
        # Every business mutation the loser had already written rolls back.
        assert accounts.users == {}
        assert accounts.identities.find(TEST_ISSUER, flow.context.subject) is None
        assert flow.h.factory.log.count("rollback_to_savepoint") == 1

    # [utest->req~users-create-user-race-arbitration~1]
    async def test_the_losers_consumption_and_rejected_audit_row_survive(self):
        accounts = FakeAccounts()
        accounts.raises = IdentityAlreadyLinkedError("the winner got there first")
        flow = Flow(accounts=accounts)
        with pytest.raises(CreateUserRejection):
            await flow.complete("anonymous")
        assert flow.row().state is ChallengeState.consumed
        assert flow.audited() == [AuthEventResult.identity_already_linked]

    # [utest->req~users-create-user-race-arbitration~1]
    def test_the_violation_is_never_a_500_and_never_an_invalid_jwt(self):
        rejection = race_loser_rejection()
        assert rejection.status_code == 409
        assert rejection.result is not AuthEventResult.invalid_external_jwt
        assert rejection.result is not AuthEventResult.internal_error
        # The loser's remedy is `/auth/sync`, not a merge, an overwrite or idempotent success.
        assert lost_response_recovery() == ("POST", "/auth/sync")


# --- Profile rules ----------------------------------------------------------------------------


class TestProfileRules:
    # [utest->req~users-profile-anonymous-registered-at-null~1]
    def test_an_anonymous_creation_leaves_registered_at_null(self):
        user = new_user_row(IdentityProvider.anonymous, ANONYMOUS.record, now=NOW)
        assert user.registered_at is None
        assert user.email is None

    # [utest->req~users-profile-registered-at-set~1]
    @pytest.mark.parametrize("provider", [IdentityProvider.google, IdentityProvider.apple])
    def test_a_registered_creation_sets_registered_at(self, provider):
        assert new_user_row(provider, GOOGLE.record, now=NOW).registered_at == NOW

    # [utest->req~users-profile-email-copy-conditions~1]
    @pytest.mark.parametrize(("record", "expected"), [
        (AdminUserRecord(email="user@example.com", email_verified=True), "user@example.com"),
        (AdminUserRecord(email="user@example.com", email_verified=False), None),
        (AdminUserRecord(email=None, email_verified=True), None),
        (AdminUserRecord(email="", email_verified=True), None),
        (None, None),
    ])
    def test_the_initial_email_is_copied_only_when_verified_and_non_empty(self, record, expected):
        assert new_user_row(IdentityProvider.google, record, now=NOW).email == expected

    # [utest->req~users-profile-email-copy-conditions~1]
    def test_an_anonymous_creation_copies_no_email(self):
        record = AdminUserRecord(email="user@example.com", email_verified=True)
        assert new_user_row(IdentityProvider.anonymous, record, now=NOW).email is None

    # [utest->req~users-profile-registered-at-pairing~1]
    async def test_the_provider_registered_at_and_email_commit_together(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        created = await flow.complete("google", variant=IdentityProvider.google)
        assert created.identity.provider is IdentityProvider.google
        assert created.user.registered_at == NOW
        assert created.user.email == "user@example.com"
        anonymous = Flow()
        plain = await anonymous.complete("anonymous")
        assert plain.identity.provider is IdentityProvider.anonymous
        assert plain.user.registered_at is None

    # [utest->req~users-profile-registered-at-pairing~1]
    # [utest->req~users-profile-pairing-enforced-in-code~1]
    def test_code_in_the_transaction_enforces_the_pairing(self):
        assert_pairing_enforced_in_code(IdentityProvider.google, NOW)
        assert_pairing_enforced_in_code(IdentityProvider.anonymous, None)
        with pytest.raises(Exception):
            assert_pairing_enforced_in_code(IdentityProvider.anonymous, NOW)
        with pytest.raises(Exception):
            assert_pairing_enforced_in_code(IdentityProvider.google, None)

    # [utest->req~users-profile-display-name-not-populated~1]
    def test_display_name_is_never_populated_from_the_admin_record(self):
        for provider, lookup in ((IdentityProvider.google, GOOGLE),
                                 (IdentityProvider.anonymous, ANONYMOUS)):
            assert new_user_row(provider, lookup.record, now=NOW).display_name is None
        assert "display_name" not in onboarding_audit_details(
            user=NewUser(id=uuid7()),
            identity=ExternalIdentityRow(id=uuid7(), user_id=uuid7(), issuer=TEST_ISSUER,
                                         subject="s", provider=IdentityProvider.anonymous),
            tokens={})["mutation"]

    # [utest->req~users-profile-no-grant-required~1]
    async def test_a_new_user_exists_with_no_active_grant(self):
        flow = Flow()
        created = await flow.complete("anonymous")
        assert assert_valid_without_grant(created.user) is created.user


# --- Failure rules ----------------------------------------------------------------------------


class TestFailureRules:
    # [utest->req~users-create-user-failure-scope~1]
    @pytest.mark.parametrize("result", sorted(CREATE_USER_RESULTS, key=str))
    def test_every_endpoint_specific_failure_before_the_commit_is_a_rejection(self, result):
        assert rejects_before_commit(result, committed=False) is True

    # [utest->req~users-create-user-failure-scope~1]
    def test_after_the_commit_there_is_no_rejection_left(self):
        assert rejects_before_commit(AuthEventResult.succeeded, committed=True) is False
        assert rejects_before_commit(AuthEventResult.succeeded, committed=False) is False
        with pytest.raises(CreateUserError):
            rejects_before_commit(AuthEventResult.identity_already_linked, committed=True)

    # [utest->req~users-create-user-error-class-mapping~1]
    @pytest.mark.parametrize(("result", "expected"), [
        (AuthEventResult.invalid_external_jwt, "auth_required"),
        (AuthEventResult.firebase_user_unresolved, "auth_required"),
        (AuthEventResult.historical_identity, "account_unavailable"),
        (AuthEventResult.blocked_user, "account_unavailable"),
        (AuthEventResult.identity_already_linked, "identity_already_linked"),
        (AuthEventResult.challenge_not_found, "challenge_required"),
        (AuthEventResult.challenge_expired, "challenge_required"),
        (AuthEventResult.challenge_consumed, "challenge_required"),
        (AuthEventResult.challenge_identity_mismatch, "challenge_required"),
        (AuthEventResult.challenge_operation_mismatch, "challenge_required"),
        (AuthEventResult.policy_rejected, "operation_not_allowed"),
        (AuthEventResult.provider_account_already_linked, "operation_not_allowed"),
        (AuthEventResult.firebase_lookup_unavailable, "verification_temporarily_unavailable"),
    ])
    def test_each_internal_result_maps_to_its_client_class(self, result, expected):
        assert create_user_client_class(result) == expected

    # [utest->req~users-create-user-error-class-mapping~1]
    def test_the_provider_causes_split_between_two_classes(self):
        for cause in (ProviderNotLinkedCause.empty_provider_data,
                      ProviderNotLinkedCause.supported_provider_mismatch):
            assert create_user_client_class(AuthEventResult.provider_not_linked,
                                            cause=cause) == CREATE_FLOW_MISMATCH_CLASS
        assert create_user_client_class(
            AuthEventResult.provider_not_linked,
            cause=ProviderNotLinkedCause.invalid_provider_data_shape) == "operation_not_allowed"
        with pytest.raises(CreateUserError):
            create_user_client_class(AuthEventResult.provider_not_linked)
        with pytest.raises(CreateUserError):
            create_user_client_class(AuthEventResult.internal_error)

    # [utest->req~users-create-user-firebase-user-not-found~1]
    async def test_a_deleted_subject_is_non_retryable_and_persists_nothing(self):
        class UserNotFoundError(Exception):
            pass

        failure = classify_lookup_error(UserNotFoundError("no such user"))
        assert failure is LookupFailure.user_not_found
        lookup = FakeLookup(failures=[_lookup_error(LookupFailure.user_not_found)] * 3)
        flow = Flow(lookup=lookup)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is AuthEventResult.firebase_user_unresolved
        assert raised.value.error_code == ClientErrorClass.auth_required
        # It consumes no retry budget: the single attempt is not retried.
        assert lookup.calls == 1
        assert flow.accounts.users == {}
        # It is audited as the distinct result, and the rejection consumes the challenge.
        assert flow.audited() == [AuthEventResult.firebase_user_unresolved]
        assert flow.row().state is ChallengeState.consumed

    # [utest->req~users-create-user-lookup-unavailable~1]
    @pytest.mark.parametrize("failure", [LookupFailure.transient, LookupFailure.infrastructure,
                                         LookupFailure.malformed_response,
                                         LookupFailure.indeterminate])
    async def test_an_indeterminate_lookup_surfaces_after_the_retry_budget(self, failure):
        lookup = FakeLookup(failures=[_lookup_error(failure)] * 3)
        flow = Flow(lookup=lookup)
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is AuthEventResult.firebase_lookup_unavailable
        assert raised.value.error_code == \
            ClientErrorClass.verification_temporarily_unavailable
        assert lookup.calls == 3
        assert flow.accounts.users == {}
        assert flow.audited() == [AuthEventResult.firebase_lookup_unavailable]
        assert flow.row().state is ChallengeState.consumed

    # [utest->req~users-create-user-lookup-unavailable~1]
    async def test_an_issuer_mismatch_is_rejected_before_the_lookup(self):
        flow = Flow()
        other = type(flow.context)(issuer="https://securetoken.google.com/other",
                                   subject=flow.context.subject,
                                   outcome=flow.context.outcome)
        with pytest.raises(InvalidExternalJwtError):
            await flow.endpoint.mandatory_lookup(other)
        assert flow.lookup.calls == 0

    # [utest->req~users-create-user-provider-not-linked-audit~1]
    async def test_the_bounded_cause_is_audited_and_the_flow_named_from_the_lookup(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert raised.value.result is AuthEventResult.provider_not_linked
        assert raised.value.cause is ProviderNotLinkedCause.supported_provider_mismatch
        assert raised.value.error_code == CREATE_FLOW_MISMATCH_CLASS
        assert raised.value.response().body["required_flow"] == "registered"
        assert flow.audited() == [AuthEventResult.provider_not_linked]

    # [utest->req~users-create-user-provider-not-linked-audit~1]
    def test_the_invalid_shape_cause_names_no_flow(self):
        rejection = CreateUserRejection(AuthEventResult.provider_not_linked,
                                        cause=ProviderNotLinkedCause.invalid_provider_data_shape)
        assert rejection.error_code == ClientErrorClass.operation_not_allowed
        assert "required_flow" not in rejection.response().body
        for cause in ProviderNotLinkedCause:
            assert provider_not_linked_details(cause)["failure"]["reason"] == cause.value

    # [utest->req~users-create-flow-mismatch-class~1]
    def test_create_flow_mismatch_is_a_409_naming_the_flow_from_the_admin_result(self):
        response = create_flow_mismatch_response(CreateFlow.registered)
        assert response.status == 409
        assert response.body == {"code": "create_flow_mismatch", "required_flow": "registered"}
        assert required_flow_for(IdentityProvider.anonymous) is CreateFlow.anonymous
        assert required_flow_for(IdentityProvider.google) is CreateFlow.registered
        assert required_flow_for(IdentityProvider.apple) is CreateFlow.registered

    # [utest->req~users-create-flow-mismatch-class~1]
    def test_no_other_class_names_a_flow(self):
        with pytest.raises(CreateUserError):
            CreateUserRejection(AuthEventResult.policy_rejected,
                                required_flow=CreateFlow.anonymous)
        with pytest.raises(CreateUserError):
            CreateUserRejection(AuthEventResult.provider_not_linked,
                                cause=ProviderNotLinkedCause.empty_provider_data)

    # [utest->req~users-create-user-no-provider-header-requirement~1]
    async def test_a_missing_provider_header_is_not_a_rejection_reason(self):
        assert_no_provider_header_requirement()
        assert_no_provider_header_requirement(headers={}, token_claims={})
        assert_no_provider_header_requirement(
            headers={"x-provider": "apple"},
            token_claims={"firebase": {"sign_in_provider": "google.com"}})
        # A completion sending no provider header at all still creates the account, and the
        # token-presented value is not read.
        flow = Flow()
        created = await flow.complete("anonymous")
        assert created.identity.provider is IdentityProvider.anonymous

    # [utest->req~users-create-user-rejection-consumes-challenge~1]
    async def test_a_rejection_at_or_after_the_lookup_consumes_the_challenge(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        row = await flow.prepare()
        with pytest.raises(CreateUserRejection):
            await flow.h.service.complete(AuthOperation.create_user, "anonymous",
                                          row.challenge_id, flow.context, flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "anonymous"})
        assert flow.row().state is ChallengeState.consumed
        # A retry needs a freshly prepared challenge: the consumed one is already used.
        with pytest.raises(ChallengeRejection) as retry:
            await flow.h.service.complete(AuthOperation.create_user, "anonymous",
                                          row.challenge_id, flow.context, flow.endpoint,
                                          body={"challenge_id": row.challenge_id,
                                                "provider": "anonymous"})
        assert retry.value.result is AuthEventResult.challenge_consumed

    # [utest->req~users-create-user-audit-specific-result~1]
    async def test_the_audited_result_is_the_specific_internal_one(self):
        flow = Flow(lookup=FakeLookup(GOOGLE))
        with pytest.raises(CreateUserRejection) as raised:
            await flow.complete("anonymous")
        assert flow.audited() == [AuthEventResult.provider_not_linked]
        assert raised.value.error_code == CREATE_FLOW_MISMATCH_CLASS
        assert audited_result_for(raised.value.result, raised.value.error_code) is \
            AuthEventResult.provider_not_linked

    # [utest->req~users-create-user-audit-specific-result~1]
    def test_two_results_sharing_a_class_stay_distinct_in_the_row(self):
        for result in (AuthEventResult.historical_identity, AuthEventResult.blocked_user):
            assert audited_result_for(result, "account_unavailable") is result
        for result in (AuthEventResult.invalid_external_jwt,
                       AuthEventResult.firebase_user_unresolved):
            assert audited_result_for(result, "auth_required") is result
        with pytest.raises(CreateUserError):
            audited_result_for(AuthEventResult.internal_error, "internal_error")

    # [utest->req~users-create-user-lost-response-uses-sync~1]
    async def test_a_lost_response_after_the_commit_uses_a_later_sync(self):
        flow = Flow()
        await flow.complete("anonymous")
        assert flow.row().state is ChallengeState.consumed
        assert lost_response_recovery() == ("POST", "/auth/sync")
        # Replaying the consumed challenge is not one of the options.
        with pytest.raises(ChallengeRejection) as replay:
            await flow.h.service.complete(AuthOperation.create_user, "anonymous",
                                          flow.row().challenge_id, flow.context, flow.endpoint,
                                          body={"challenge_id": flow.row().challenge_id,
                                                "provider": "anonymous"})
        assert replay.value.result is AuthEventResult.challenge_consumed


