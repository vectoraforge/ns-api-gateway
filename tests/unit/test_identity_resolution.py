"""FOUND-01 / §1.3: the four-outcome admission matrix as logic, plus the §1.2 counter.

`tests/e2e/test_barrier_admission.py` proves the matrix against real rows over the real transport.
This module proves the branches the *database* cannot produce. `core.identity_state` is a
two-value `NOT NULL` enum and `core.external_identities.user_id` carries a `RESTRICT` foreign key,
so a NULL state, an unrecognized state, and a dangling user reference are all unreachable through
PostgreSQL -- and §1.3 requires each of them to fail closed rather than fall through to pre-auth.
A stub session is the only way to put such a row in front of `resolve_identity`.

The stub also makes the query-count claim checkable directly: it counts its own `exec` calls, so
"exactly one SELECT per resolution" is asserted rather than read off the source.
"""
from uuid import uuid7

import pytest

from nativespeaker.api.auth.identity import Admit, Reject, resolve_identity
from nativespeaker.api.auth.registry import Category, RouteMetadata
from nativespeaker.api.auth.telemetry import RejectionCounter, record_rejection
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    INTERNAL_ERROR,
    PREAUTH_IDENTITY_NOT_ALLOWED,
)
from nativespeaker.api.models.auth import AuthEventResult
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.models.users import User

ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "subject-under-test"


class _StubResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _StubSession:
    """Stands in for the one short session the barrier opens, and keeps what it was asked to run."""

    def __init__(self, row=None):
        self._row = row
        self.statements = []

    @property
    def executed(self) -> int:
        return len(self.statements)

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._row)


def _meta(*, preauth_callable: bool = False) -> RouteMetadata:
    return RouteMetadata(method="GET", path="/chats", category=Category.authenticated,
                         preauth_callable=preauth_callable)


def _row(*, identity_state=IdentityState.active, user_active: bool = True, user=...):
    """An `(identity, user)` pair shaped exactly as the single joined statement returns one."""
    user_id = uuid7()
    identity = ExternalIdentity(id=uuid7(), user_id=user_id, issuer=ISSUER, subject=SUBJECT,
                                provider=IdentityProvider.google, provider_uid="google-account-1",
                                identity_state=identity_state)
    if user is ...:
        user = User(id=user_id, active=user_active)
    return identity, user


async def _resolve(row, *, preauth_callable: bool = False):
    session = _StubSession(row)
    decision = await resolve_identity(session, issuer=ISSUER, subject=SUBJECT,
                                      meta=_meta(preauth_callable=preauth_callable))
    return decision, session


class TestOutcomeOneNoMatchingRow:
    """§1.3 outcomes 1 and 1' -- the only two readings of "this pair was never linked"."""

    async def test_a_preauth_callable_route_admits_the_verified_pair(self):
        decision, _ = await _resolve(None, preauth_callable=True)
        assert isinstance(decision, Admit)
        assert decision.identity.issuer == ISSUER
        assert decision.identity.subject == SUBJECT

    async def test_the_preauth_variant_carries_nothing_else(self):
        decision, _ = await _resolve(None, preauth_callable=True)
        assert not hasattr(decision.identity, "user")
        assert not hasattr(decision.identity, "identity")

    async def test_any_other_route_rejects_preauth_identity_not_allowed(self):
        decision, _ = await _resolve(None)
        assert isinstance(decision, Reject)
        assert decision.error_class is PREAUTH_IDENTITY_NOT_ALLOWED
        assert decision.result is AuthEventResult.preauth_identity_not_allowed

    async def test_the_rejection_carries_the_verified_actor(self):
        """Pitfall 10: the audit CHECK admits all-NULL actors only for `invalid_external_jwt`."""
        decision, _ = await _resolve(None)
        assert (decision.actor_issuer, decision.actor_subject) == (ISSUER, SUBJECT)


class TestOutcomeTwoIdentityStateIsNotExactlyActive:
    """§1.3 outcome 2 -- `historical`, NULL, and any future member land on one branch."""

    @pytest.mark.parametrize("state", [IdentityState.historical, None, "retired", ""])
    async def test_a_state_other_than_active_rejects_account_unavailable(self, state):
        decision, _ = await _resolve(_row(identity_state=state))
        assert isinstance(decision, Reject)
        assert decision.error_class is ACCOUNT_UNAVAILABLE
        assert decision.result is AuthEventResult.historical_identity

    @pytest.mark.parametrize("state", [IdentityState.historical, None, "retired", ""])
    async def test_it_never_falls_through_to_pre_auth(self, state):
        """Even on the one route that may admit a pre-auth principal (§1.3 outcome 2, "any route")."""
        decision, _ = await _resolve(_row(identity_state=state), preauth_callable=True)
        assert isinstance(decision, Reject)
        assert decision.result is AuthEventResult.historical_identity

    async def test_a_retired_identity_never_surfaces_preauth_identity_not_allowed(self):
        """T-35-06-02: identity rows are never deleted, so a retired pair still has a row."""
        decision, _ = await _resolve(_row(identity_state=IdentityState.historical))
        assert decision.error_class is not PREAUTH_IDENTITY_NOT_ALLOWED


class TestOutcomeThreeUserIsNotExactlyTrue:
    """§1.3 outcome 3 -- a positive test on the user column, not a truthiness test."""

    async def test_an_inactive_user_rejects_account_unavailable(self):
        decision, _ = await _resolve(_row(user_active=False))
        assert isinstance(decision, Reject)
        assert decision.error_class is ACCOUNT_UNAVAILABLE
        assert decision.result is AuthEventResult.blocked_user

    @pytest.mark.parametrize("value", [None, 1, "true", "yes"])
    async def test_a_truthy_non_boolean_is_not_coerced_into_an_admission(self, value):
        """`user.active is not True` rejects; `not user.active` would admit 1, 'true' and 'yes'."""
        decision, _ = await _resolve(_row(user_active=value))
        assert isinstance(decision, Reject)
        assert decision.result is AuthEventResult.blocked_user


class TestOutcomeFourLinkedAndActive:
    """§1.3 outcome 4 -- the only admission that carries a user row."""

    async def test_it_admits_with_the_resolved_rows(self):
        row = _row()
        decision, _ = await _resolve(row)
        assert isinstance(decision, Admit)
        assert decision.identity.identity is row[0]
        assert decision.identity.user is row[1]

    async def test_the_admitted_context_carries_the_verified_pair(self):
        decision, _ = await _resolve(_row())
        assert (decision.identity.issuer, decision.identity.subject) == (ISSUER, SUBJECT)

    async def test_the_classifier_is_the_stored_provider_column(self):
        decision, _ = await _resolve(_row())
        assert decision.identity.identity.provider is IdentityProvider.google


class TestUnresolvableUser:
    """T-35-06-07 -- an identity row whose user row is missing fails closed, never inline repair."""

    async def test_it_rejects_as_an_internal_error(self):
        decision, _ = await _resolve(_row(user=None))
        assert isinstance(decision, Reject)
        assert decision.error_class is INTERNAL_ERROR
        assert decision.result is AuthEventResult.internal_error

    async def test_it_is_not_read_as_an_unlinked_pair(self):
        """The outer join is what keeps this case distinct from outcome 1."""
        decision, _ = await _resolve(_row(user=None), preauth_callable=True)
        assert isinstance(decision, Reject)

    async def test_the_rejection_carries_the_verified_actor(self):
        decision, _ = await _resolve(_row(user=None))
        assert (decision.actor_issuer, decision.actor_subject) == (ISSUER, SUBJECT)


class TestOneQueryOneCodePath:
    """D-13's whole anti-oracle guarantee, asserted structurally rather than by timing."""

    @pytest.mark.parametrize("row", [
        None,
        _row(),
        _row(identity_state=IdentityState.historical),
        _row(user_active=False),
        _row(user=None),
    ], ids=["unlinked", "linked-active", "historical", "blocked", "unresolvable"])
    async def test_every_outcome_issues_exactly_one_statement(self, row):
        _decision, session = await _resolve(row)
        assert session.executed == 1

    async def test_both_account_unavailable_branches_carry_the_same_class_object(self):
        """One class, one status, one body, one copy -- differing only in the internal result."""
        historical, _ = await _resolve(_row(identity_state=IdentityState.historical))
        blocked, _ = await _resolve(_row(user_active=False))
        assert historical.error_class is blocked.error_class
        assert historical.result is not blocked.result

    async def test_no_timing_normalisation_is_present(self):
        """D-13 rejects padding and constant-time delays for this product -- deliberately absent."""
        import inspect

        from nativespeaker.api.auth import identity as identity_module
        source = inspect.getsource(identity_module)
        assert "sleep" not in source
        assert "perf_counter" not in source


class TestTheResolutionStatement:
    """The shape of the one statement, asserted because one of its properties is unobservable.

    The dangling-user branch above cannot be produced by the database -- `user_id` carries a
    `NOT NULL REFERENCES core.users (id)` foreign key, so no such row can exist -- which means no
    test at any level can reach that branch through real data. Only the join *kind* keeps the
    branch alive at all: swap `isouter=True` for an inner join and the row simply disappears, the
    dangling case silently becomes outcome 1, and every test above still passes. Asserting the
    compiled statement is the one thing that catches that.
    """

    async def test_it_outer_joins_so_a_dangling_user_is_not_read_as_unlinked(self):
        _decision, session = await _resolve(_row())
        assert "LEFT OUTER JOIN" in str(session.statements[0])

    async def test_it_joins_the_identity_table_to_the_user_table(self):
        _decision, session = await _resolve(_row())
        compiled = str(session.statements[0])
        assert "core.external_identities" in compiled
        assert "core.users" in compiled

    async def test_it_filters_on_issuer_and_subject_and_nothing_else(self):
        """§1.3 resolves the verified pair. `core.users.id` is never an authentication key."""
        _decision, session = await _resolve(_row())
        where = str(session.statements[0]).split("WHERE", 1)[1]
        assert "external_identities.issuer" in where
        assert "external_identities.subject" in where
        assert "identity_state" not in where and "active" not in where

    async def test_the_state_columns_are_read_in_python_not_filtered_in_sql(self):
        """Both `account_unavailable` branches must leave the *same* statement (D-13).

        A `WHERE identity_state = 'active'` would make outcome 2 return no row -- collapsing it
        into outcome 1, which §1.3 forbids -- and would put the two rejections on different paths.
        """
        _decision, session = await _resolve(_row(identity_state=IdentityState.historical))
        historical_sql = str(session.statements[0])
        _decision, session = await _resolve(_row(user_active=False))
        assert historical_sql == str(session.statements[0])


class TestRejectionCounter:
    """§1.2 / §8.2 -- the required alerting source, with cardinality bounded by construction."""

    def test_repeated_rejections_accumulate_under_one_key(self):
        counter = RejectionCounter()
        for _ in range(2):
            counter.increment(result="invalid_external_jwt", bounded_reason="missing_token",
                              route="/chats")
        assert list(counter.snapshot().values()) == [2]

    def test_the_key_is_result_by_reason_by_route(self):
        counter = RejectionCounter()
        counter.increment(result="invalid_external_jwt", bounded_reason="expired", route="/chats")
        assert list(counter.snapshot()) == [("invalid_external_jwt", "expired", "/chats")]

    def test_a_missing_bounded_reason_is_a_key_of_its_own(self):
        """Admission-matrix rejections carry no bounded reason; §1.1 failures always do."""
        counter = RejectionCounter()
        counter.increment(result="blocked_user", bounded_reason=None, route="/chats")
        counter.increment(result="invalid_external_jwt", bounded_reason="expired", route="/chats")
        assert len(counter.snapshot()) == 2

    def test_the_route_label_is_the_path_template_so_cardinality_stays_bounded(self):
        """T-35-06-05: a raw request path would make one label unbounded on its own."""
        counter = RejectionCounter()
        for _ in range(100):
            counter.increment(result="blocked_user", bounded_reason=None,
                              route="/chats/{chat_id}")
        assert len(counter.snapshot()) == 1

    def test_the_snapshot_is_a_copy(self):
        counter = RejectionCounter()
        counter.increment(result="blocked_user", bounded_reason=None, route="/chats")
        counter.snapshot().clear()
        assert len(counter.snapshot()) == 1


class _AppState:
    def __init__(self, counter=None):
        if counter is not None:
            self.rejection_counter = counter


class TestRecordRejection:
    """The barrier's one telemetry entry point -- it counts, it logs, it never raises."""

    def test_it_increments_the_counter_on_the_application(self):
        counter = RejectionCounter()
        record_rejection(_AppState(counter), result=AuthEventResult.blocked_user,
                         bounded_reason=None, route="/chats")
        assert counter.snapshot() == {("blocked_user", None, "/chats"): 1}

    def test_enum_labels_are_recorded_as_their_string_values(self):
        from nativespeaker.api.auth.wire import BoundedReason
        counter = RejectionCounter()
        record_rejection(_AppState(counter), result=AuthEventResult.invalid_external_jwt,
                         bounded_reason=BoundedReason.duplicate_authorization, route="/")
        assert counter.snapshot() == {("invalid_external_jwt", "duplicate_authorization", "/"): 1}

    def test_an_absent_counter_does_not_turn_a_rejection_into_a_500(self):
        """A telemetry gap must never change what the client is told."""
        record_rejection(_AppState(), result=AuthEventResult.blocked_user,
                         bounded_reason=None, route="/chats")

    def test_it_logs_the_rejection(self, monkeypatch):
        """A recording spy, not `structlog.testing.capture_logs` -- see 35-02's caching note."""
        from nativespeaker.api.auth import telemetry as telemetry_module
        events: list[tuple[str, dict]] = []
        monkeypatch.setattr(telemetry_module.logger, "warning",
                            lambda event, **kw: events.append((event, kw)))
        record_rejection(_AppState(RejectionCounter()), result=AuthEventResult.historical_identity,
                         bounded_reason=None, route="/examples")
        assert events == [("auth_rejected", {"result": "historical_identity",
                                             "bounded_reason": None,
                                             "route": "/examples"})]

    def test_the_bounded_reason_never_reaches_the_client(self):
        """§1.2: the reason lives in telemetry and audit `details.failure` only."""
        from nativespeaker.api.errors import ErrorResponse
        assert list(ErrorResponse.model_fields) == ["code"]
