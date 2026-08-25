"""The consuming transaction's rejection arms at unit speed; savepoint durability needs a real database."""
import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from nativespeaker.api.auth import creation
from nativespeaker.api.auth.context import PreAuthIdentity, RequestContext
from nativespeaker.api.auth.creation import (
    CLIENT_CLASS_FOR_RESULT,
    PROVIDER_ACCOUNT_INDEX_NAME,
    RACE_CONSTRAINT_NAMES,
    classify_insert_conflict,
    create_account,
)
from nativespeaker.api.errors import (
    ACCOUNT_UNAVAILABLE,
    IDENTITY_ALREADY_LINKED,
    OPERATION_NOT_ALLOWED,
)
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider, IdentityState
from nativespeaker.api.models.users import User

ISSUER = "https://securetoken.google.com/ns-conflict-test"
SUBJECT = "conflict-classification-subject"
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


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


class _ConsumingStore:
    """Consumes successfully and records that it was asked, which every arm must do."""

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


async def _run(rows: list[object | None]) -> tuple[AuthEventResult, _NoMutationSession,
                                                   _ConsumingStore]:
    """Drive `create_account` over a scripted read sequence and return everything observable."""
    session = _NoMutationSession(rows)
    store = _ConsumingStore()
    context = _context()
    challenge = AuthChallenge(challenge_id="scripted-handle",
                              operation=AuthOperation.create_user,
                              preauth_issuer=ISSUER,
                              preauth_subject_hash=b"\x00" * 32,
                              expires_at=NOW,
                              created_at=NOW)
    result = await create_account(session,
                                  context=context,
                                  identity=context.identity,
                                  challenge=challenge,
                                  provider=IdentityProvider.anonymous,
                                  provider_uid=None,
                                  email=None,
                                  challenge_store=store)
    return result, session, store


class TestTheConstraintNamesAreDeclaredAsConstants:
    """The mapping is data, in one place, rather than a chain of string comparisons."""

    def test_exactly_the_two_race_constraints(self):
        """Two arbiters and only two; a third would mean another rule had been folded into the race."""
        assert RACE_CONSTRAINT_NAMES == frozenset({"external_identities_issuer_subject_key",
                                                   "external_identities_user_id_key"})

    def test_the_provider_account_reservation_is_a_separate_name(self):
        assert PROVIDER_ACCOUNT_INDEX_NAME == "ix_external_identities_provider_account"
        assert PROVIDER_ACCOUNT_INDEX_NAME not in RACE_CONSTRAINT_NAMES


class TestConflictDiscriminationByConstraintName:
    """Three live names, two internal results, two client classes."""

    @pytest.mark.parametrize("constraint_name", sorted(RACE_CONSTRAINT_NAMES))
    def test_a_race_constraint_is_the_already_linked_result(self, constraint_name):
        """Both unique constraints mean the same thing to the caller: an account exists, reconcile it."""
        assert classify_insert_conflict(_integrity_error(constraint_name)) is \
            AuthEventResult.identity_already_linked

    def test_the_provider_account_index_is_a_different_result(self):
        """asyncpg reports a standalone partial unique index by name exactly as it reports a constraint."""
        assert classify_insert_conflict(_integrity_error(PROVIDER_ACCOUNT_INDEX_NAME)) is \
            AuthEventResult.provider_account_already_linked

    def test_the_two_outcomes_are_distinct_results_and_distinct_client_classes(self):
        """Distinctness is asserted on both layers, because either one collapsing loses a client instruction."""
        linked = classify_insert_conflict(_integrity_error("external_identities_issuer_subject_key"))
        provider_account = classify_insert_conflict(_integrity_error(PROVIDER_ACCOUNT_INDEX_NAME))

        assert linked is not provider_account
        assert CLIENT_CLASS_FOR_RESULT[linked] is IDENTITY_ALREADY_LINKED
        assert CLIENT_CLASS_FOR_RESULT[provider_account] is OPERATION_NOT_ALLOWED
        assert CLIENT_CLASS_FOR_RESULT[linked] is not CLIENT_CLASS_FOR_RESULT[provider_account]
        assert CLIENT_CLASS_FOR_RESULT[linked].status == 409
        assert CLIENT_CLASS_FOR_RESULT[provider_account].status == 403

    def test_both_unavailable_results_share_one_client_class(self):
        """The mutually-indistinguishable pair: the internal results differ, the answer does not."""
        assert CLIENT_CLASS_FOR_RESULT[AuthEventResult.historical_identity] is ACCOUNT_UNAVAILABLE
        assert CLIENT_CLASS_FOR_RESULT[AuthEventResult.blocked_user] is ACCOUNT_UNAVAILABLE


class TestAnUnrecognisedConflictIsReRaised:
    """Swallowing one would turn a programming error into a plausible client response."""

    def test_the_provider_agreement_check_is_not_a_business_branch(self):
        """`provider_uid` is derived so this CHECK cannot fire; reaching it is a defect here, not a client fact."""
        error = _integrity_error("external_identities_check")
        with pytest.raises(IntegrityError) as raised:
            classify_insert_conflict(error)
        assert raised.value is error

    def test_a_cause_chain_with_no_constraint_name_is_re_raised(self):
        error = _integrity_error(None)
        with pytest.raises(IntegrityError) as raised:
            classify_insert_conflict(error)
        assert raised.value is error

    def test_an_integrity_error_with_no_orig_at_all_is_re_raised(self):
        error = IntegrityError("INSERT INTO core.external_identities ...", {}, None)
        with pytest.raises(IntegrityError) as raised:
            classify_insert_conflict(error)
        assert raised.value is error

    def test_an_unknown_constraint_name_is_re_raised(self):
        """A name nobody mapped -- a new constraint, or a rename -- must be loud, not guessed."""
        error = _integrity_error("external_identities_some_future_key")
        with pytest.raises(IntegrityError) as raised:
            classify_insert_conflict(error)
        assert raised.value is error


class TestTheReResolutionsThreeNoMutationArms:
    """An already-present identity row means this attempt creates nothing."""

    async def test_an_active_linked_row_is_already_linked_and_inserts_nothing(self):
        """The pre-check at prepare is racy and never authoritative; this read decides."""
        user_id = uuid4()
        rows = [_identity_row(state=IdentityState.active, user_id=user_id),
                User(id=user_id, active=True, created_at=NOW, updated_at=NOW)]
        result, session, store = await _run(rows)

        assert result is AuthEventResult.identity_already_linked
        assert CLIENT_CLASS_FOR_RESULT[result] is IDENTITY_ALREADY_LINKED

    async def test_a_historical_row_is_the_historical_result(self):
        """`historical` is a permanent tombstone: no creation, and no `preauth_identity_not_allowed`."""
        result, _, _ = await _run([_identity_row(state=IdentityState.historical)])

        assert result is AuthEventResult.historical_identity
        assert CLIENT_CLASS_FOR_RESULT[result] is ACCOUNT_UNAVAILABLE

    async def test_an_active_row_whose_user_is_blocked_is_the_blocked_result(self):
        """Distinct from `historical_identity` internally, identical to the caller."""
        user_id = uuid4()
        rows = [_identity_row(state=IdentityState.active, user_id=user_id),
                User(id=user_id, active=False, created_at=NOW, updated_at=NOW)]
        result, _, _ = await _run(rows)

        assert result is AuthEventResult.blocked_user
        assert CLIENT_CLASS_FOR_RESULT[result] is ACCOUNT_UNAVAILABLE

    async def test_the_two_unavailable_arms_are_indistinguishable_to_the_caller(self):
        """The pair a client must not be able to tell apart, asserted rather than assumed."""
        historical, _, _ = await _run([_identity_row(state=IdentityState.historical)])
        blocked_user_id = uuid4()
        blocked, _, _ = await _run([
            _identity_row(state=IdentityState.active, user_id=blocked_user_id),
            User(id=blocked_user_id, active=False, created_at=NOW, updated_at=NOW)])

        assert historical is not blocked
        assert CLIENT_CLASS_FOR_RESULT[historical] is CLIENT_CLASS_FOR_RESULT[blocked]

    async def test_a_missing_user_row_fails_closed(self):
        """The FK makes this unreachable; if it ever happens, refuse rather than invent or reassign an identity."""
        rows = [_identity_row(state=IdentityState.active), None]
        result, _, _ = await _run(rows)

        assert result is AuthEventResult.blocked_user
        assert CLIENT_CLASS_FOR_RESULT[result] is ACCOUNT_UNAVAILABLE

    async def test_every_no_mutation_arm_still_consumes_and_commits(self):
        """A rejection that skipped consumption would leave the challenge replayable."""
        _, session, store = await _run([_identity_row(state=IdentityState.historical)])

        assert store.consumed == ["scripted-handle"]
        assert session.commits == 1

    async def test_the_historical_arm_reads_only_the_identity_row(self):
        """A historical row is already decisive, so reading the user row would be work done to reach the same answer."""
        _, session, _ = await _run([_identity_row(state=IdentityState.historical)])

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
        assert handlers, "no `except IntegrityError` arm in auth/creation.py"

        rollbacks = [node for handler in handlers for node in ast.walk(handler)
                     if isinstance(node, ast.Attribute) and node.attr == "rollback"
                     and isinstance(node.value, ast.Name) and node.value.id == "savepoint"]
        assert rollbacks, "an `except IntegrityError` arm that does not roll back to the savepoint"
