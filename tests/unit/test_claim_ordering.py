"""ANONGRANT-02 and REGGRANT-02's no-network-under-a-lock claims, as checks rather than prose.
The read runs before the transaction opens and the write after it commits, neither crud writer
names a seam member at all, and importing that module pulls in no HTTP client.
"""
import ast
import inspect
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sqlmodel import SQLModel

from nativespeaker.api.crud import grants as crud_grants
from nativespeaker.api.services import auth as auth_service
from nativespeaker.api.tables.identities import ExternalIdentity

CRUD_SOURCE = Path(crud_grants.__file__).read_text()
SERVICE_SOURCE = Path(auth_service.__file__).read_text()

WRITER = "activate_anonymous_device_grant"
CLAIM = "_claim_anonymous_grant"

WRITER_REGISTERED = "activate_registered_account_grant"
CLAIM_REGISTERED = "_claim_registered_grant"

# The registered claim's one arm that reaches Apple: the block guarded by `if not held:`.
NEW_GRANT_ARM_GUARD = "held"

# The local that arm binds, and that the post-commit write is guarded on: `None` means no bit to set.
STATE_NAME = "state"

WROTE_NAME = "wrote"

# Every name the device-gate seam exposes. None of them may appear inside the crud writer.
SEAM_NAMES = frozenset({"devicecheck", "read_bits", "write_bits",
                        "read_bits_with_retry", "write_bits_with_retry",
                        "DeviceCheckAdapter", "AppleDeviceCheck", "BitState"})

# The crud module's import roots: the standard library, the ORM it is written in, and this project.
# `enum` joins `datetime` and `uuid` as a named stdlib module; the driver is still not one of them.
ALLOWED_IMPORT_ROOTS = {"datetime", "enum", "uuid", "sqlalchemy", "sqlmodel", "nativespeaker"}

# An HTTP client reachable from the crud module is exactly the drift this file exists to catch.
FORBIDDEN_MODULES = ("httpx", "requests", "aiohttp", "urllib3")


def _function(source: str, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in the source given")


def _called_names(node: ast.AST) -> list[str]:
    """Every call in `node`, in source order, named by its function or attribute."""
    calls = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            calls.append((child.lineno, child.col_offset, child.func.id))
        elif isinstance(child.func, ast.Attribute):
            calls.append((child.lineno, child.col_offset, child.func.attr))
    return [name for _, _, name in sorted(calls)]


def _order(node: ast.AST, names: tuple[str, ...]) -> list[int]:
    """Where each of `names` first appears among the calls of `node`, in that order."""
    called = _called_names(node)
    for name in names:
        assert name in called, f"{name} is not called at all"
    return [called.index(name) for name in names]


def _new_grant_arm(claim: ast.AST) -> ast.If:
    """The one `if not held:` block of `claim`, which is the only arm that reaches the seam."""
    arms = [node for node in ast.walk(claim)
            if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not) and isinstance(node.test.operand, ast.Name)
            and node.test.operand.id == NEW_GRANT_ARM_GUARD]
    assert len(arms) == 1, f"expected one `if not {NEW_GRANT_ARM_GUARD}:` arm, found {len(arms)}"
    return arms[0]


def _calls_outside(claim: ast.AST, arm: ast.AST) -> list[str]:
    """Every call of `claim` that `arm` does not contain, which is what the other arms run."""
    inside = {id(node) for node in ast.walk(arm)}
    outside = ast.Module(body=[node for node in claim.body if id(node) not in inside],
                         type_ignores=[])
    return _called_names(outside)


def _call_line(node: ast.AST, name: str) -> int:
    """The line of the first call to `name` in `node`."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) \
                and child.func.attr == name:
            return child.lineno
    raise AssertionError(f"{name} is not called at all")


def _guard_of_the_write(claim: ast.AST) -> frozenset[str]:
    """The names the `if` around the vendor write tests, empty when the write is unguarded."""
    for node in ast.walk(claim):
        if not isinstance(node, ast.If):
            continue
        if "write_bits_with_retry" not in _called_names(ast.Module(body=node.body,
                                                                   type_ignores=[])):
            continue
        return frozenset(child.id for child in ast.walk(node.test) if isinstance(child, ast.Name))
    return frozenset()


def _mentioned_names(node: ast.AST) -> set[str]:
    """Every identifier `node` names, whether as a bare name or as an attribute."""
    found = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
    return found


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)


class TestTheCrudWriterCannotReachTheVendor:
    """The transaction that takes both lock tiers holds no path to a network call at all."""

    def test_the_writer_names_no_member_of_the_device_gate_seam(self):
        writer = _function(CRUD_SOURCE, WRITER)
        assert _mentioned_names(writer) & SEAM_NAMES == set()

    def test_the_registered_writer_names_no_member_of_the_device_gate_seam_either(self):
        writer = _function(CRUD_SOURCE, WRITER_REGISTERED)
        assert _mentioned_names(writer) & SEAM_NAMES == set()

    def test_the_module_imports_only_the_stdlib_the_orm_and_this_project(self):
        roots = set()
        for node in ast.walk(ast.parse(CRUD_SOURCE)):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            if isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        assert roots <= ALLOWED_IMPORT_ROOTS, f"unexpected: {sorted(roots - ALLOWED_IMPORT_ROOTS)}"

    def test_importing_the_module_pulls_in_no_http_client(self):
        """The transitive version: a convenience import anywhere below the crud module fails this too."""
        result = _run("import sys, nativespeaker.api.crud.grants; "
                      f"print([n for n in {FORBIDDEN_MODULES!r} if n in sys.modules])")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "[]"


def _mapped_parameters(function) -> list[str]:
    """Every parameter of `function` annotated with a mapped ORM row."""
    return [name for name, parameter in inspect.signature(function).parameters.items()
            if isinstance(parameter.annotation, type) and issubclass(parameter.annotation, SQLModel)]


class TestTheWritersTakeTheVerifiedPairAndNoOrmRow:
    """WR-40. The barrier resolves its identity row in a session that closes before the handler runs,
    so a row in either signature offers a frozen copy beside the `stored` re-read every rule reads."""

    @pytest.mark.parametrize("writer", [WRITER, WRITER_REGISTERED])
    def test_it_takes_the_issuer_and_the_subject_as_plain_strings(self, writer):
        parameters = inspect.signature(getattr(crud_grants.GrantsDB, writer)).parameters

        assert [parameters[name].annotation for name in ("issuer", "subject")] == [str, str]

    @pytest.mark.parametrize("writer", [WRITER, WRITER_REGISTERED])
    def test_no_parameter_of_either_writer_is_a_mapped_orm_row(self, writer):
        assert _mapped_parameters(getattr(crud_grants.GrantsDB, writer)) == []

    def test_a_signature_carrying_a_row_is_reported_control(self):
        """The control: a walk that found nothing would pass the two cases above."""
        def _widened(*, user_id: UUID, identity_row: ExternalIdentity) -> None: ...

        assert _mapped_parameters(_widened) == ["identity_row"]


class TestTheActivationSitsBetweenTheTwoVendorCalls:
    """The sequence is the rule, so an order assertion over the body is a fair check of it."""

    def test_the_read_precedes_the_activation_and_the_write_follows_its_commit(self):
        read, activate, commit, write = _order(_function(SERVICE_SOURCE, CLAIM),
                                               ("read_bits_with_retry", WRITER,
                                                "commit", "write_bits_with_retry"))
        assert read < activate < commit < write

    def test_the_claim_takes_no_lock_of_its_own_before_reaching_the_seam(self):
        """Locking is the crud writer's job alone, and it runs last; a lock here would straddle the call."""
        claim = _function(SERVICE_SOURCE, CLAIM)
        assert {"lock_effective_grants", "lock_active_grants", "lock_usage",
                "lock_identity_and_user"} & set(_called_names(claim)) == set()

    def test_the_write_is_guarded_on_this_attempt_having_written_the_grant(self):
        """WR-46: the writer also answers `lost_race` from the insert's unique violation, whose
        arbiter is any active grant of any source, so the winner is not always another anonymous
        claim and setting bit0 for it spends this device's slot on a grant nothing here wrote."""
        assert _guard_of_the_write(_function(SERVICE_SOURCE, CLAIM)) == {WROTE_NAME}

    def test_the_wrote_the_write_is_guarded_on_is_what_the_settlement_answered(self):
        """The guard is honest only if the settlement binds it: a second read would fail here."""
        claim = _function(SERVICE_SOURCE, CLAIM)
        settled = [node for node in ast.walk(claim)
                   if isinstance(node, ast.Assign) and "_settle" in _called_names(node)]
        assert [target.id for node in settled for target in node.targets] == [WROTE_NAME]


class TestBothVendorCallsPrecedeTheRegisteredActivation:
    """The registered claim has five arms and one reaches Apple, so the order is asserted there."""

    def test_the_read_sits_in_the_new_grant_arm_and_the_write_follows_the_commit(self):
        """The read is the arm's own; the writer, the commit and the write all run past the arm."""
        claim = _function(SERVICE_SOURCE, CLAIM_REGISTERED)
        arm = _new_grant_arm(claim)
        arm_calls = _called_names(arm)
        assert "read_bits_with_retry" in arm_calls
        assert "write_bits_with_retry" not in arm_calls
        assert arm.end_lineno < _call_line(claim, WRITER_REGISTERED)
        activate, commit, write = _order(claim, (WRITER_REGISTERED, "commit",
                                                 "write_bits_with_retry"))
        assert activate < commit < write

    def test_the_conversion_arm_reads_no_bits_and_the_write_it_skips_is_guarded_on_that_read(self):
        """D-02 as a check: the conversion never reads, so the guard below skips its write too."""
        claim = _function(SERVICE_SOURCE, CLAIM_REGISTERED)
        outside = set(_calls_outside(claim, _new_grant_arm(claim)))
        # Only the read is arm-local now; the write moved past the commit and so is outside it.
        assert "read_bits_with_retry" not in outside
        # The control: the conversion still reaches the writer, so the set above is not empty by accident.
        assert WRITER_REGISTERED in outside
        assert _guard_of_the_write(claim) == {STATE_NAME, WROTE_NAME}

    def test_the_state_the_write_is_guarded_on_is_the_one_the_arm_binds(self):
        """The guard is only honest if the arm is what sets it: a rename on one side fails here."""
        arm = _new_grant_arm(_function(SERVICE_SOURCE, CLAIM_REGISTERED))
        bound = {target.id for node in ast.walk(arm) if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name)}
        assert STATE_NAME in bound

    def test_the_wrote_the_write_is_guarded_on_is_what_the_settlement_answered(self):
        """The other half of the guard: it names the settlement's own answer, not a second read."""
        claim = _function(SERVICE_SOURCE, CLAIM_REGISTERED)
        settled = [node for node in ast.walk(claim)
                   if isinstance(node, ast.Assign) and "_settle" in _called_names(node)]
        assert [target.id for node in settled for target in node.targets] == [WROTE_NAME]

    def test_the_claim_takes_no_lock_of_its_own_before_reaching_the_seam(self):
        """Locking is the crud writer's job alone, and it runs last; a lock here would straddle the call."""
        claim = _function(SERVICE_SOURCE, CLAIM_REGISTERED)
        assert {"lock_effective_grants", "lock_active_grants", "lock_usage",
                "lock_identity_and_user"} & set(_called_names(claim)) == set()


class TestTheOrderAssertionFires:
    """The control: a body with the calls in the wrong order must fail the same assertion."""

    def test_a_body_writing_before_its_commit_reports_the_reversed_positions(self):
        """The regression this ordering exists to prevent: Apple told before the grant is durable."""
        source = ("async def _claim_anonymous_grant(self):\n"
                  "    state = await read_bits_with_retry(self.devicecheck, token)\n"
                  "    await write_bits_with_retry(self.devicecheck, token)\n"
                  "    await self.grants_db.activate_anonymous_device_grant()\n"
                  "    await self.session.commit()\n")
        read, activate, commit, write = _order(_function(source, CLAIM),
                                               ("read_bits_with_retry", WRITER,
                                                "commit", "write_bits_with_retry"))
        # The same expression the real case asserts, which this ordering makes false.
        assert not (read < activate < commit < write)

    def test_a_synthetic_writer_naming_the_seam_is_caught(self):
        source = ("async def activate_anonymous_device_grant(self):\n"
                  "    await self.devicecheck.write_bits(token)\n")
        writer = _function(source, WRITER)
        assert _mentioned_names(writer) & SEAM_NAMES == {"devicecheck", "write_bits"}

    def test_a_synthetic_read_escaping_the_arm_is_caught(self):
        """The control on the registered pair: a read below the arm reaches the conversion and is seen."""
        source = ("async def _claim_registered_grant(self):\n"
                  "    if not held:\n"
                  "        pass\n"
                  "    state = await read_bits_with_retry(self.devicecheck, token)\n"
                  "    await self.grants_db.activate_registered_account_grant()\n")
        claim = _function(source, CLAIM_REGISTERED)
        assert "read_bits_with_retry" in _calls_outside(claim, _new_grant_arm(claim))

    def test_an_unguarded_synthetic_write_is_caught(self):
        """The control on the guard: a write the conversion arm also runs names no guard at all."""
        source = ("async def _claim_registered_grant(self):\n"
                  "    if not held:\n"
                  "        state = await read_bits_with_retry(self.devicecheck, token)\n"
                  "    await self.session.commit()\n"
                  "    await write_bits_with_retry(self.devicecheck, token)\n")
        assert _guard_of_the_write(_function(source, CLAIM_REGISTERED)) == frozenset()

    def test_a_body_without_the_new_grant_arm_is_reported_rather_than_passed(self):
        """A renamed guard would silently empty the arm; it is named instead, so the failure reads."""
        source = "async def _claim_registered_grant(self):\n    return None\n"
        with pytest.raises(AssertionError, match="expected one `if not held:` arm, found 0"):
            _new_grant_arm(_function(source, CLAIM_REGISTERED))

    @pytest.mark.parametrize("missing", ["read_bits_with_retry", WRITER])
    def test_a_body_missing_one_of_the_calls_is_reported_rather_than_passed(self, missing):
        """A silently absent call would make `index` raise; it is named instead, so the failure reads."""
        source = "async def _claim_anonymous_grant(self):\n    await write_bits_with_retry(t)\n"
        with pytest.raises(AssertionError, match=f"{missing} is not called at all"):
            _order(_function(source, CLAIM), (missing,))
