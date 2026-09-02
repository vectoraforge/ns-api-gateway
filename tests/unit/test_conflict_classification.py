"""The consuming transaction's rejection arms at unit speed; durability needs a real crud."""
import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.crud import identities as identities_crud
from nativespeaker.api.crud.challenges import ChallengesDB
from nativespeaker.api.errors import (
    AccountUnavailable,
    AppError,
    BlockedUser,
    HistoricalIdentity,
    IdentityAlreadyLinked,
)
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.services import auth as auth_service
from nativespeaker.api.services.auth import AuthService
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.users import User

ISSUER = "https://securetoken.google.com/ns-conflict-test"
SUBJECT = "conflict-classification-subject"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _integrity_error() -> IntegrityError:
    """A SQLAlchemy `IntegrityError` shaped like the real one: a dialect wrapper around a driver error."""
    return IntegrityError("INSERT INTO core.external_identities ...", {},
                          Exception("dialect-level wrapper"))


class _Result:
    """The one method `session.exec(...)` results are consumed through in this module."""

    def __init__(self, row: object | None) -> None:
        self._row = row

    def first(self) -> object | None:
        return self._row


class _NoMutationSession:
    """Answers reads from a script and raises on every write entry point, so a mutating branch fails here."""

    def __init__(self, rows: list[object | None]) -> None:
        self._rows = list(rows)
        self.statements: list[object] = []
        self.commits = 0

    async def exec(self, statement):
        self.statements.append(statement)
        assert self._rows, "the re-resolution issued more reads than this script answers"
        return _Result(self._rows.pop(0))

    async def commit(self) -> None:
        self.commits += 1

    def add(self, instance) -> None:
        raise AssertionError(f"a no-mutation arm must not add {type(instance).__name__}")

    async def flush(self) -> None:
        raise AssertionError("a no-mutation arm must not flush")

    async def rollback(self) -> None:
        raise AssertionError("a no-mutation arm has nothing to roll back")


class _ConflictingSession:
    """Finds no existing row, then fails the identity insert as PostgreSQL would."""

    def __init__(self, conflict: BaseException) -> None:
        self._conflict = conflict
        self.added: list[object] = []
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0

    async def exec(self, statement):
        return _Result(None)

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        # The second flush is the one carrying the identity row, so that is where the race is lost.
        self.flushes += 1
        if self.flushes >= 2:
            raise self._conflict

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _identity() -> Identity:
    return Identity(issuer=ISSUER, subject=SUBJECT)


def _identity_row(*, state: IdentityState, user_id=None) -> ExternalIdentity:
    return ExternalIdentity(user_id=user_id or uuid4(),
                            issuer=ISSUER,
                            subject=SUBJECT,
                            provider=IdentityProvider.google,
                            provider_uid="provider-uid",
                            identity_state=state,
                            created_at=NOW,
                            updated_at=NOW)


async def _create(session):
    """Drive `AuthService.create_user` over whichever session the case scripted."""
    service = AuthService(db=session, challenge_store=ChallengesDB(), adapter=None,
                          evaluated_at=NOW)
    return await service.create_user(identity=_identity(),
                                     provider=IdentityProvider.anonymous,
                                     provider_uid=None,
                                     email=None)


async def _run(rows: list[object | None]) -> _NoMutationSession:
    """Drive the re-resolution over a scripted read sequence; every arm of it raises."""
    session = _NoMutationSession(rows)
    await _create(session)
    return session


async def _insert(*, expect: type[BaseException] = AppError,
                  conflict: BaseException | None = None):
    """Drive the insert arm into its `except IntegrityError` branch and return all it left behind."""
    conflict = conflict if conflict is not None else _integrity_error()
    session = _ConflictingSession(conflict)
    with pytest.raises(expect) as raised:
        await _create(session)
    return raised.value, conflict, session


class TestEveryConflictCollapsesToOneAlreadyLinkedAnswer:
    """D-06: the constraint-name classification is gone, so one answer covers every integrity violation."""

    async def test_an_integrity_error_raises_already_linked(self):
        """An account exists for this pair: reconcile it, do not create a second."""
        rejection, _, _ = await _insert(expect=IdentityAlreadyLinked)
        assert (rejection.status, rejection.code) == (409, "identity_already_linked")

    async def test_the_violation_survives_as_the_rejections_cause(self):
        """The rejection is the client's answer; the violation is the reason, and the traceback keeps it."""
        rejection, conflict, _ = await _insert()
        assert rejection.__cause__ is conflict

    async def test_the_conflict_commits_nothing(self):
        """The route's except arm rolls back and spends the handle; this function must leave both to it."""
        _, _, session = await _insert()
        assert (session.commits, session.rollbacks) == (0, 0)

    async def test_no_further_row_is_added_after_the_failure(self):
        """A retry here would be a second race entrant under the same claim."""
        _, _, session = await _insert()
        assert session.flushes == 2

    async def test_a_non_integrity_failure_is_not_caught_at_all(self):
        """A connection drop must not be reshaped into a uniqueness conflict."""
        error = RuntimeError("the connection went away mid-flush")
        raised, _, session = await _insert(expect=RuntimeError, conflict=error)
        assert raised is error
        assert not isinstance(raised, AppError)
        assert session.commits == 0


class TestTheReResolutionsThreeNoMutationArms:
    """An already-present identity row means this attempt creates nothing."""

    async def test_an_active_linked_row_raises_already_linked_and_inserts_nothing(self):
        """The pre-check at prepare is racy and never authoritative; this read decides."""
        user_id = uuid4()
        rows = [_identity_row(state=IdentityState.active, user_id=user_id),
                User(id=user_id, active=True, created_at=NOW, updated_at=NOW)]
        with pytest.raises(IdentityAlreadyLinked) as raised:
            await _run(rows)
        assert (raised.value.status, raised.value.code) == (409, "identity_already_linked")

    async def test_a_historical_row_raises_account_unavailable(self):
        """`historical` is a permanent tombstone: no creation, and no `preauth_identity_not_allowed`."""
        with pytest.raises(HistoricalIdentity) as raised:
            await _run([_identity_row(state=IdentityState.historical)])

        assert (raised.value.status, raised.value.code) == (403, "account_unavailable")

    async def test_an_active_row_whose_user_is_blocked_raises_account_unavailable(self):
        """Distinct from the historical arm in the log alone, identical to the caller."""
        user_id = uuid4()
        rows = [_identity_row(state=IdentityState.active, user_id=user_id),
                User(id=user_id, active=False, created_at=NOW, updated_at=NOW)]
        with pytest.raises(BlockedUser) as raised:
            await _run(rows)

        assert (raised.value.status, raised.value.code) == (403, "account_unavailable")

    async def test_the_two_unavailable_arms_are_indistinguishable_to_the_caller(self):
        """The pair a client must not be able to tell apart, asserted rather than assumed."""
        with pytest.raises(AccountUnavailable) as historical:
            await _run([_identity_row(state=IdentityState.historical)])

        blocked_user_id = uuid4()
        with pytest.raises(AccountUnavailable) as blocked:
            await _run([_identity_row(state=IdentityState.active, user_id=blocked_user_id),
                        User(id=blocked_user_id, active=False, created_at=NOW, updated_at=NOW)])

        # Two classes, one answer: the difference reaches the log event name and nothing else.
        assert type(historical.value) is not type(blocked.value)
        assert (historical.value.status, historical.value.code) == (blocked.value.status,
                                                                    blocked.value.code)
        assert historical.value.log_fields() == blocked.value.log_fields() == {}

    async def test_a_missing_user_row_fails_closed(self):
        """The FK makes this unreachable; if it ever happens, refuse rather than invent or reassign an identity."""
        with pytest.raises(BlockedUser) as raised:
            await _run([_identity_row(state=IdentityState.active), None])

        assert (raised.value.status, raised.value.code) == (403, "account_unavailable")

    async def test_every_no_mutation_arm_commits_nothing(self):
        """Committing here would spend the claim on a request that created no account."""
        session = _NoMutationSession([_identity_row(state=IdentityState.historical)])
        with pytest.raises(AccountUnavailable):
            await _create(session)

        assert session.commits == 0

    async def test_the_historical_arm_reads_only_the_identity_row(self):
        """A historical row is already decisive, so reading the user row would be work done to reach the same answer."""
        session = _NoMutationSession([_identity_row(state=IdentityState.historical)])
        with pytest.raises(AccountUnavailable):
            await _create(session)

        assert len(session.statements) == 1


# Structural guards read the code with prose stripped, since a text search would also match the prose.

# Both halves of the creation path: the service holds the rule, the store holds the inserts.
_CREATION_SOURCE = "\n".join(Path(module.__file__).read_text()
                             for module in (auth_service, identities_crud))


class _StripDocstrings(ast.NodeTransformer):
    """Drop the leading string expression from every module, class and function body."""

    def _strip(self, node):
        self.generic_visit(node)
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
        return node

    visit_Module = _strip
    visit_ClassDef = _strip
    visit_FunctionDef = _strip
    visit_AsyncFunctionDef = _strip


def _code_only(source: str) -> str:
    """The module's executable text: comments dropped by the parse, docstrings dropped above."""
    return ast.unparse(_StripDocstrings().visit(ast.parse(source)))


class TestTheModuleUsesNoSecondRaceArbiter:
    """The UNIQUE constraints are the sole arbiters, and nothing else may be added.
    The upgrade path's row lock is revalidation, not arbitration: the challenge claim stays the
    only serialization point on both completion paths, so no second arbiter exists to disagree."""

    @pytest.mark.parametrize("forbidden", ["serializable", "advisory_lock", "pg_advisory",
                                           "isolation_level", "for update", "select_for_update"])
    def test_no_second_serialization_mechanism_appears_in_the_code(self, forbidden):
        """An advisory lock, a stricter isolation level or a row lock would each be an arbiter that can disagree."""
        assert forbidden not in _code_only(_CREATION_SOURCE).lower()

    def test_conflicts_are_never_discriminated_by_message_text(self):
        """Message text depends on the server's locale and would accept either rule naming the same table."""
        code = _code_only(_CREATION_SOURCE)
        assert "str(exc" not in code
        assert "str(e)" not in code

    def test_the_inserts_open_no_savepoint_of_their_own(self):
        """D-06: one transaction, owned by the route, so no nested boundary can outlive its owner."""
        assert "begin_nested" not in _code_only(_CREATION_SOURCE)
