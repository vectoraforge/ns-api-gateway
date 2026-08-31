"""The four-outcome admission matrix as logic: the branches a real crud cannot produce."""
import contextlib
from uuid import uuid7

import pytest

from nativespeaker.api.app.error_handlers import camel_to_snake
from nativespeaker.api.crud.identities import IdentitiesDB
from nativespeaker.api.errors import (
    AccountUnavailable,
    AppError,
    BlockedUser,
    HistoricalIdentity,
    IdentityUnresolvable,
    PreAuthIdentityNotAllowed,
)
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.users import User

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
    """The admitting half: resolution returns the `Identity` it resolved."""
    session = _StubSession(row)
    identity = await IdentitiesDB(session).resolve(issuer=ISSUER, subject=SUBJECT,
                                                   allow_preauth=preauth_callable)
    return identity, session


async def _rejected(row, expected: type[BaseException], *, preauth_callable: bool = False):
    """The rejecting half: resolution raises, and the raised instance is what the cases read."""
    session = _StubSession(row)
    with pytest.raises(expected) as caught:
        await IdentitiesDB(session).resolve(issuer=ISSUER, subject=SUBJECT,
                                            allow_preauth=preauth_callable)
    return caught.value, session


async def _drive(row, *, preauth_callable: bool = False) -> _StubSession:
    """Run resolution for its effect on the session, whichever way the outcome goes."""
    session = _StubSession(row)
    with contextlib.suppress(AppError):
        await IdentitiesDB(session).resolve(issuer=ISSUER, subject=SUBJECT,
                                            allow_preauth=preauth_callable)
    return session


class TestOutcomeOneNoMatchingRow:
    """The only two readings of a pair that was never linked."""

    async def test_a_preauth_callable_route_admits_the_verified_pair(self):
        identity, _ = await _resolve(None, preauth_callable=True)
        assert identity.issuer == ISSUER
        assert identity.subject == SUBJECT

    async def test_the_unlinked_identity_carries_no_row(self):
        """Unlinked is both row fields `None` together, which is what the store branches on."""
        identity, _ = await _resolve(None, preauth_callable=True)
        assert identity.user is None
        assert identity.identity is None

    async def test_any_other_route_rejects_preauth_identity_not_allowed(self):
        rejection, _ = await _rejected(None, PreAuthIdentityNotAllowed)
        assert (rejection.status, rejection.code) == (403, "preauth_identity_not_allowed")

    async def test_the_rejection_carries_no_actor_material(self):
        """The verified pair is not a field on any rejection, so it cannot reach the log line."""
        rejection, _ = await _rejected(None, PreAuthIdentityNotAllowed)
        assert rejection.log_fields() == {}
        for absent in ("issuer", "subject", "actor_issuer", "actor_subject"):
            assert not hasattr(rejection, absent)


class TestOutcomeTwoIdentityStateIsNotExactlyActive:
    """`historical`, NULL and any future member all land on one branch."""

    @pytest.mark.parametrize("state", [IdentityState.historical, None, "retired", ""])
    async def test_a_state_other_than_active_rejects_account_unavailable(self, state):
        rejection, _ = await _rejected(_row(identity_state=state), HistoricalIdentity)
        assert (rejection.status, rejection.code) == (403, "account_unavailable")

    @pytest.mark.parametrize("state", [IdentityState.historical, None, "retired", ""])
    async def test_it_never_falls_through_to_pre_auth(self, state):
        """Even on the one route that may admit a pre-auth principal."""
        rejection, _ = await _rejected(_row(identity_state=state), HistoricalIdentity,
                                       preauth_callable=True)
        assert isinstance(rejection, AccountUnavailable)

    async def test_a_retired_identity_never_surfaces_preauth_identity_not_allowed(self):
        """Identity rows are never deleted, so a retired pair still has a row."""
        rejection, _ = await _rejected(_row(identity_state=IdentityState.historical),
                                       HistoricalIdentity)
        assert not isinstance(rejection, PreAuthIdentityNotAllowed)
        assert rejection.code != "preauth_identity_not_allowed"


class TestOutcomeThreeUserIsNotExactlyTrue:
    """A positive test on the user column, not a truthiness test."""

    async def test_an_inactive_user_rejects_account_unavailable(self):
        rejection, _ = await _rejected(_row(user_active=False), BlockedUser)
        assert (rejection.status, rejection.code) == (403, "account_unavailable")

    @pytest.mark.parametrize("value", [None, 1, "true", "yes"])
    async def test_a_truthy_non_boolean_is_not_coerced_into_an_admission(self, value):
        """`user.active is not True` rejects; `not user.active` would admit 1, 'true' and 'yes'."""
        rejection, _ = await _rejected(_row(user_active=value), BlockedUser)
        assert isinstance(rejection, AccountUnavailable)


class TestOutcomeFourLinkedAndActive:
    """The only admission that carries a user row."""

    async def test_it_admits_with_the_resolved_rows(self):
        row = _row()
        identity, _ = await _resolve(row)
        assert identity.identity is row[0]
        assert identity.user is row[1]

    async def test_the_admitted_identity_carries_the_verified_pair(self):
        identity, _ = await _resolve(_row())
        assert (identity.issuer, identity.subject) == (ISSUER, SUBJECT)

    async def test_the_classifier_is_the_stored_provider_column(self):
        identity, _ = await _resolve(_row())
        assert identity.identity.provider is IdentityProvider.google


class TestUnresolvableUser:
    """An identity row whose user row is missing fails closed, never inline repair."""

    async def test_it_rejects_as_an_internal_error(self):
        rejection, _ = await _rejected(_row(user=None), IdentityUnresolvable)
        assert (rejection.status, rejection.code) == (500, "internal_error")

    async def test_it_is_not_read_as_an_unlinked_pair(self):
        """The outer join is what keeps this case distinct from outcome 1."""
        rejection, _ = await _rejected(_row(user=None), IdentityUnresolvable,
                                       preauth_callable=True)
        assert not isinstance(rejection, PreAuthIdentityNotAllowed)

    async def test_the_rejection_carries_no_actor_material(self):
        rejection, _ = await _rejected(_row(user=None), IdentityUnresolvable)
        assert rejection.log_fields() == {}
        for absent in ("issuer", "subject", "actor_issuer", "actor_subject"):
            assert not hasattr(rejection, absent)


class TestOneQueryOneCodePath:
    """The anti-oracle guarantee asserted structurally rather than by timing."""

    @pytest.mark.parametrize("row", [
        None,
        _row(),
        _row(identity_state=IdentityState.historical),
        _row(user_active=False),
        _row(user=None),
    ], ids=["unlinked", "linked-active", "historical", "blocked", "unresolvable"])
    async def test_every_outcome_issues_exactly_one_statement(self, row):
        session = await _drive(row)
        assert session.executed == 1

    async def test_both_account_unavailable_branches_carry_the_same_client_answer(self):
        """Two classes, one answer: the 403 is declared on the base and neither leaf restates it."""
        historical, _ = await _rejected(_row(identity_state=IdentityState.historical),
                                        HistoricalIdentity)
        blocked, _ = await _rejected(_row(user_active=False), BlockedUser)
        assert type(historical) is not type(blocked)
        assert (historical.status, historical.code) == (blocked.status, blocked.code)
        for leaf in (HistoricalIdentity, BlockedUser):
            assert "status" not in vars(leaf) and "code" not in vars(leaf)

    async def test_no_timing_normalisation_is_present(self):
        """Padding and constant-time delays are deliberately absent for this product."""
        import inspect

        from nativespeaker.api.crud import identities as identities_module
        source = inspect.getsource(identities_module)
        assert "sleep" not in source
        assert "perf_counter" not in source


class TestTheResolutionStatement:
    """The join kind keeps the dangling-user branch alive: an inner join would make it silently vanish."""

    async def test_it_outer_joins_so_a_dangling_user_is_not_read_as_unlinked(self):
        _identity, session = await _resolve(_row())
        assert "LEFT OUTER JOIN" in str(session.statements[0])

    async def test_it_joins_the_identity_table_to_the_user_table(self):
        _identity, session = await _resolve(_row())
        compiled = str(session.statements[0])
        assert "core.external_identities" in compiled
        assert "core.users" in compiled

    async def test_it_filters_on_issuer_and_subject_and_nothing_else(self):
        """Resolution is on the verified pair; `core.users.id` is never an authentication key."""
        _identity, session = await _resolve(_row())
        where = str(session.statements[0]).split("WHERE", 1)[1]
        assert "external_identities.issuer" in where
        assert "external_identities.subject" in where
        assert "identity_state" not in where and "active" not in where

    async def test_the_state_columns_are_read_in_python_not_filtered_in_sql(self):
        """Filtering in SQL would collapse the two unavailable outcomes and put them on different paths."""
        session = await _drive(_row(identity_state=IdentityState.historical))
        historical_sql = str(session.statements[0])
        session = await _drive(_row(user_active=False))
        assert historical_sql == str(session.statements[0])


class TestTheRejectionSaysNothingItWasNotAsked:
    """Resolution's rejections reach exactly one log line, and carry only what D-02 sanctions."""

    async def test_the_account_arms_are_told_apart_by_class_name_and_carry_no_field(self):
        """The distinction is the log event name, so neither arm needs a field that could leak."""
        historical, _ = await _rejected(_row(identity_state=IdentityState.historical),
                                        HistoricalIdentity)
        blocked, _ = await _rejected(_row(user_active=False), BlockedUser)
        assert historical.log_fields() == blocked.log_fields() == {}
        assert camel_to_snake(type(historical).__name__) == "historical_identity"
        assert camel_to_snake(type(blocked).__name__) == "blocked_user"

    async def test_every_logged_value_is_a_plain_scalar(self):
        """An ORM instance here is the expired-attribute 500 the family's scalars-only rule prevents."""
        for row, expected in ((None, PreAuthIdentityNotAllowed),
                              (_row(user=None), IdentityUnresolvable),
                              (_row(user_active=False), BlockedUser)):
            rejection, _ = await _rejected(row, expected)
            for key, value in rejection.log_fields().items():
                assert isinstance(value, str | None), f"{expected.__name__}.{key} is not a scalar"

    def test_the_arm_never_reaches_the_client(self):
        """The distinction lives in the security log only; the body carries one field."""
        from nativespeaker.api.errors import ErrorResponse
        assert list(ErrorResponse.model_fields) == ["code"]
