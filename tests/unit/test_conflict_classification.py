"""The consuming transaction's rejection arms at unit speed; savepoint durability needs a real crud."""
import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.auth import create_user
from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.auth.create_user import create_user
from nativespeaker.api.auth.exceptions import (
    AccountUnavailable,
    AuthRejected,
    IdentityAlreadyLinked,
    ProviderAccountAlreadyLinked,
)
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    IDENTITY_ALREADY_LINKED,
    OPERATION_NOT_ALLOWED,
)
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.tables.users import User

ISSUER = "https://securetoken.google.com/ns-conflict-test"
SUBJECT = "conflict-classification-subject"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

# PostgreSQL's generated names for the two UNIQUE rules on external_identities, and the partial
# UNIQUE index asyncpg reports by name exactly as it reports a constraint. The production arm now
# writes these as literals inline, and this file is the only other place that names them: a rename
# on one side and not the other fails this suite loudly rather than drifting.
RACE_ISSUER_SUBJECT_KEY = "external_identities_issuer_subject_key"
RACE_USER_ID_KEY = "external_identities_user_id_key"
PROVIDER_ACCOUNT_INDEX = "ix_external_identities_provider_account"

RACE_CONSTRAINT_NAMES = (RACE_ISSUER_SUBJECT_KEY, RACE_USER_ID_KEY)


class _DriverViolation(Exception):
    """Stands in for the asyncpg exception SQLAlchemy wraps: it carries `constraint_name`."""

    def __init__(self, constraint_name: str) -> None:
        super().__init__(f"duplicate key value violates unique constraint {constraint_name!r}")
        self.constraint_name = constraint_name


def _integrity_error(constraint_name: str | None) -> IntegrityError:
    """A SQLAlchemy `IntegrityError` shaped like the real one: driver wrapper, asyncpg cause."""
    wrapper = Exception("dialect-level wrapper")
    if constraint_name is not None:
        wrapper.__cause__ = _DriverViolation(constraint_name)
    return IntegrityError("INSERT INTO core.external_identities ...", {}, wrapper)


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

    async def begin_nested(self):
        raise AssertionError("a no-mutation arm must not open the business savepoint")

    def add(self, instance) -> None:
        raise AssertionError(f"a no-mutation arm must not add {type(instance).__name__}")

    async def flush(self) -> None:
        raise AssertionError("a no-mutation arm must not flush")

    async def rollback(self) -> None:
        raise AssertionError("a no-mutation arm has nothing to roll back")


class _Savepoint:
    """Records the two boundaries the conflict arm is required to use, and rejects the third."""

    def __init__(self) -> None:
        self.rollbacks = 0
        self.commits = 0

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def commit(self) -> None:
        self.commits += 1


class _ConflictingSession:
    """Finds no existing row, opens the savepoint, then fails the identity insert as PostgreSQL would."""

    def __init__(self, conflict: IntegrityError) -> None:
        self._conflict = conflict
        self.savepoint = _Savepoint()
        self.added: list[object] = []
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0

    async def exec(self, statement):
        return _Result(None)

    async def begin_nested(self) -> _Savepoint:
        return self.savepoint

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


class _ConsumingStore:
    """Consumes successfully and records that it was asked, which the success path must do."""

    def __init__(self) -> None:
        self.consumed: list[str] = []

    async def consume(self, session, *, challenge_id, claim_attempt_id, now) -> bool:
        self.consumed.append(challenge_id)
        return True


def _context() -> RequestContext:
    identity = PreAuthIdentity(issuer=ISSUER, subject=SUBJECT)
    return RequestContext(identity=identity,
                          route="/auth/create-user",
                          evaluated_at=NOW,
                          attempt_id=uuid4())


def _identity_row(*, state: IdentityState, user_id=None) -> ExternalIdentity:
    return ExternalIdentity(user_id=user_id or uuid4(),
                            issuer=ISSUER,
                            subject=SUBJECT,
                            provider=IdentityProvider.google,
                            provider_uid="provider-uid",
                            identity_state=state,
                            created_at=NOW,
                            updated_at=NOW)


async def _create(session, store: _ConsumingStore):
    """Drive `create_account` over whichever session the case scripted."""
    context = _context()
    challenge = AuthChallenge(challenge_id="scripted-handle",
                              operation=AuthOperation.create_user,
                              preauth_issuer=ISSUER,
                              preauth_subject_hash=b"\x00" * 32,
                              expires_at=NOW,
                              created_at=NOW)
    return await create_user(session,
                             context=context,
                             identity=context.identity,
                             challenge=challenge,
                             provider=IdentityProvider.anonymous,
                             provider_uid=None,
                             email=None,
                             challenge_store=store)


async def _run(rows: list[object | None]) -> tuple[_NoMutationSession, _ConsumingStore]:
    """Drive the re-resolution over a scripted read sequence; every arm of it raises."""
    session = _NoMutationSession(rows)
    store = _ConsumingStore()
    await _create(session, store)
    return session, store


async def _insert(constraint_name: str | None, *, expect: type[BaseException] = AuthRejected,
                  conflict: IntegrityError | None = None):
    """Drive the insert arm into its `except IntegrityError` branch and return all it left behind."""
    conflict = conflict if conflict is not None else _integrity_error(constraint_name)
    session = _ConflictingSession(conflict)
    store = _ConsumingStore()
    with pytest.raises(expect) as raised:
        await _create(session, store)
    return raised.value, conflict, session, store


class TestTheArmNamesExactlyTheThreeLiveConstraints:
    """Two race arbiters and one reservation; a fourth would mean another rule folded into the race."""

    def test_the_code_names_exactly_the_three_constraints_this_file_names(self):
        """Asserted against the code with prose stripped, so a name mentioned only in a comment misses."""
        named = {node.value for node in ast.walk(ast.parse(_code_only(_CREATION_SOURCE)))
                 if isinstance(node, ast.Constant) and isinstance(node.value, str)
                 and "external_identities" in node.value}
        assert named == {RACE_ISSUER_SUBJECT_KEY, RACE_USER_ID_KEY, PROVIDER_ACCOUNT_INDEX}

    def test_the_reservation_is_not_one_of_the_race_arbiters(self):
        assert PROVIDER_ACCOUNT_INDEX not in RACE_CONSTRAINT_NAMES


class TestConflictDiscriminationByConstraintName:
    """Three live names, two rejections, two client classes."""

    @pytest.mark.parametrize("constraint_name", RACE_CONSTRAINT_NAMES)
    async def test_a_race_constraint_raises_already_linked(self, constraint_name):
        """Both unique constraints mean the same thing to the caller: an account exists, reconcile it."""
        rejection, _, _, _ = await _insert(constraint_name, expect=IdentityAlreadyLinked)
        assert rejection.error_class is IDENTITY_ALREADY_LINKED

    async def test_the_provider_account_index_raises_a_different_rejection(self):
        """asyncpg reports a standalone partial unique index by name exactly as it reports a constraint."""
        rejection, _, _, _ = await _insert(PROVIDER_ACCOUNT_INDEX,
                                           expect=ProviderAccountAlreadyLinked)
        assert rejection.error_class is OPERATION_NOT_ALLOWED

    async def test_the_two_outcomes_are_distinct_classes_and_distinct_client_classes(self):
        """Distinctness is asserted on both layers, because either one collapsing loses a client instruction."""
        linked, _, _, _ = await _insert(RACE_ISSUER_SUBJECT_KEY)
        provider_account, _, _, _ = await _insert(PROVIDER_ACCOUNT_INDEX)

        assert type(linked) is not type(provider_account)
        assert linked.error_class is not provider_account.error_class
        assert linked.error_class.status == 409
        assert provider_account.error_class.status == 403

    async def test_the_conflict_rolls_back_the_savepoint_and_commits_nothing(self):
        """Until the rollback runs the session refuses every further statement, including the consume."""
        _, _, session, _ = await _insert(RACE_ISSUER_SUBJECT_KEY)
        assert (session.savepoint.rollbacks, session.savepoint.commits) == (1, 0)

    async def test_the_conflict_leaves_the_consume_to_the_route(self):
        """D-04: the raising arms consume in `_complete`'s except arm, so the handle is spent once."""
        _, _, session, store = await _insert(PROVIDER_ACCOUNT_INDEX)
        assert store.consumed == []
        assert session.commits == 0

    async def test_the_violation_survives_as_the_rejections_cause(self):
        """The rejection is the client's answer; the violation is the reason, and the traceback keeps it."""
        rejection, conflict, _, _ = await _insert(RACE_USER_ID_KEY)
        assert rejection.__cause__ is conflict


class TestAnUnrecognisedConflictIsReRaised:
    """Swallowing one would turn a programming error into a plausible client response."""

    async def test_the_provider_agreement_check_is_not_a_business_branch(self):
        """`provider_uid` is derived so this CHECK cannot fire; reaching it is a defect here, not a client fact."""
        raised, conflict, _, _ = await _insert("external_identities_check", expect=IntegrityError)
        assert raised is conflict

    async def test_a_cause_chain_with_no_constraint_name_is_re_raised(self):
        raised, conflict, _, _ = await _insert(None, expect=IntegrityError)
        assert raised is conflict

    async def test_an_integrity_error_with_no_orig_at_all_is_re_raised(self):
        error = IntegrityError("INSERT INTO core.external_identities ...", {}, None)
        raised, conflict, _, _ = await _insert(None, expect=IntegrityError, conflict=error)
        assert raised is conflict is error

    async def test_an_unknown_constraint_name_is_re_raised(self):
        """A name nobody mapped -- a new constraint, or a rename -- must be loud, not guessed.

        Written out rather than routed through the helper: this case is the 500 tripwire's only
        guard, and it should be findable by searching for the exception type it insists on.
        """
        conflict = _integrity_error("external_identities_some_future_key")
        session = _ConflictingSession(conflict)

        with pytest.raises(IntegrityError) as raised:
            await _create(session, _ConsumingStore())

        assert raised.value is conflict

    async def test_the_unmapped_arm_is_not_a_member_of_the_rejection_family(self):
        """The tripwire's whole point: a 500, never a benign 409 the caller could believe."""
        raised, _, _, _ = await _insert("external_identities_some_future_key",
                                        expect=IntegrityError)
        assert not isinstance(raised, AuthRejected)

    async def test_the_unmapped_arm_still_rolled_the_savepoint_back_first(self):
        """A poisoned session would fail the request differently from the way this one is meant to fail."""
        _, _, session, store = await _insert("external_identities_some_future_key",
                                             expect=IntegrityError)
        assert session.savepoint.rollbacks == 1
        assert store.consumed == []


class TestTheReResolutionsThreeNoMutationArms:
    """An already-present identity row means this attempt creates nothing."""

    async def test_an_active_linked_row_raises_already_linked_and_inserts_nothing(self):
        """The pre-check at prepare is racy and never authoritative; this read decides."""
        user_id = uuid4()
        rows = [_identity_row(state=IdentityState.active, user_id=user_id),
                User(id=user_id, active=True, created_at=NOW, updated_at=NOW)]
        with pytest.raises(IdentityAlreadyLinked) as raised:
            await _run(rows)
        assert raised.value.error_class is IDENTITY_ALREADY_LINKED

    async def test_a_historical_row_raises_account_unavailable(self):
        """`historical` is a permanent tombstone: no creation, and no `preauth_identity_not_allowed`."""
        with pytest.raises(AccountUnavailable) as raised:
            await _run([_identity_row(state=IdentityState.historical)])

        assert raised.value.error_class is ACCOUNT_UNAVAILABLE
        assert raised.value.cause == "historical_identity"

    async def test_an_active_row_whose_user_is_blocked_raises_account_unavailable(self):
        """Distinct from the historical arm in the log alone, identical to the caller."""
        user_id = uuid4()
        rows = [_identity_row(state=IdentityState.active, user_id=user_id),
                User(id=user_id, active=False, created_at=NOW, updated_at=NOW)]
        with pytest.raises(AccountUnavailable) as raised:
            await _run(rows)

        assert raised.value.error_class is ACCOUNT_UNAVAILABLE
        assert raised.value.cause == "blocked_user"

    async def test_the_two_unavailable_arms_are_indistinguishable_to_the_caller(self):
        """The pair a client must not be able to tell apart, asserted rather than assumed."""
        with pytest.raises(AccountUnavailable) as historical:
            await _run([_identity_row(state=IdentityState.historical)])

        blocked_user_id = uuid4()
        with pytest.raises(AccountUnavailable) as blocked:
            await _run([_identity_row(state=IdentityState.active, user_id=blocked_user_id),
                        User(id=blocked_user_id, active=False, created_at=NOW, updated_at=NOW)])

        # One class, one client class: the only difference is the field that reaches the log.
        assert type(historical.value) is type(blocked.value)
        assert historical.value.error_class is blocked.value.error_class
        assert historical.value.cause != blocked.value.cause

    async def test_a_missing_user_row_fails_closed(self):
        """The FK makes this unreachable; if it ever happens, refuse rather than invent or reassign an identity."""
        with pytest.raises(AccountUnavailable) as raised:
            await _run([_identity_row(state=IdentityState.active), None])

        assert raised.value.cause == "blocked_user"

    async def test_every_no_mutation_arm_leaves_the_consume_to_the_route(self):
        """D-04 moved the post-claim consume to `_complete`; consuming here too would spend the handle twice."""
        session = _NoMutationSession([_identity_row(state=IdentityState.historical)])
        store = _ConsumingStore()
        with pytest.raises(AccountUnavailable):
            await _create(session, store)

        assert store.consumed == []
        assert session.commits == 0

    async def test_the_historical_arm_reads_only_the_identity_row(self):
        """A historical row is already decisive, so reading the user row would be work done to reach the same answer."""
        session = _NoMutationSession([_identity_row(state=IdentityState.historical)])
        with pytest.raises(AccountUnavailable):
            await _create(session, _ConsumingStore())

        assert len(session.statements) == 1


# Structural guards read the code with prose stripped, since a text search would also match the prose.

_CREATION_SOURCE = Path(creation.__file__).read_text()


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
    """The UNIQUE constraints are the sole arbiters, and nothing else may be added."""

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

    def test_the_constraint_name_is_read_off_the_driver_and_not_the_message(self):
        """The cause-chain walk moved inline when the helper was deleted; the rule it carried did not move."""
        code = _code_only(_CREATION_SOURCE)
        assert "constraint_name" in code
        assert "__cause__" in code


class TestTheSavepointRollbackArmIsStructurallyPresent:
    """Without this arm a conflict poisons the session and the consumption is lost."""

    def test_the_business_inserts_open_a_savepoint(self):
        assert "begin_nested" in _code_only(_CREATION_SOURCE)

    def test_an_integrity_error_handler_rolls_back_to_the_savepoint(self):
        """Asserted on the handler, so a rollback sitting where the conflict never reaches would not satisfy it."""
        tree = ast.parse(_CREATION_SOURCE)
        handlers = [node for node in ast.walk(tree)
                    if isinstance(node, ast.ExceptHandler)
                    and isinstance(node.type, ast.Name) and node.type.id == "IntegrityError"]
        assert handlers, "no `except IntegrityError` arm in auth/create_user.py"

        rollbacks = [node for handler in handlers for node in ast.walk(handler)
                     if isinstance(node, ast.Attribute) and node.attr == "rollback"
                     and isinstance(node.value, ast.Name) and node.value.id == "savepoint"]
        assert rollbacks, "an `except IntegrityError` arm that does not roll back to the savepoint"

    def test_the_rollback_is_the_first_await_in_the_arm(self):
        """Rollback FIRST, classify second: until then the session refuses every further statement."""
        tree = ast.parse(_CREATION_SOURCE)
        handler = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.ExceptHandler)
                       and isinstance(node.type, ast.Name) and node.type.id == "IntegrityError")
        first_await = next(node for statement in handler.body for node in ast.walk(statement)
                           if isinstance(node, ast.Await))
        assert isinstance(first_await.value, ast.Call)
        assert first_await.value.func.attr == "rollback"
        assert first_await.value.func.value.id == "savepoint"
