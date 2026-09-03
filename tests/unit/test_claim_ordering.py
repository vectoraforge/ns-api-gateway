"""ANONGRANT-02's no-network-under-a-lock claim, as a check rather than as prose.
Both vendor calls run strictly before the activation transaction opens, the crud writer
names no seam member at all, and importing that module pulls in no HTTP client.
"""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

from nativespeaker.api.crud import grants as crud_grants
from nativespeaker.api.services import auth as auth_service

CRUD_SOURCE = Path(crud_grants.__file__).read_text()
SERVICE_SOURCE = Path(auth_service.__file__).read_text()

WRITER = "activate_anonymous_device_grant"
CLAIM = "_claim_anonymous_grant"

# Every name the device-gate seam exposes. None of them may appear inside the crud writer.
SEAM_NAMES = frozenset({"devicecheck", "read_bits", "write_bits",
                        "read_bits_with_retry", "write_bits_with_retry",
                        "DeviceCheckAdapter", "AppleDeviceCheck", "BitState"})

# The crud module's import roots: the standard library, the ORM it is written in, and this project.
ALLOWED_IMPORT_ROOTS = {"datetime", "uuid", "sqlalchemy", "sqlmodel", "nativespeaker"}

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


class TestBothVendorCallsPrecedeTheActivation:
    """The sequence is the rule, so an order assertion over the body is a fair check of it."""

    def test_the_read_and_the_write_both_appear_before_the_activation_call(self):
        claim = _function(SERVICE_SOURCE, CLAIM)
        read, write, activate = _order(claim, ("read_bits_with_retry",
                                                "write_bits_with_retry",
                                                WRITER))
        assert read < write < activate

    def test_the_claim_takes_no_lock_of_its_own_before_reaching_the_seam(self):
        """Locking is the crud writer's job alone, and it runs last; a lock here would straddle the call."""
        claim = _function(SERVICE_SOURCE, CLAIM)
        assert {"lock_effective_grants", "lock_usage",
                "lock_identity_and_user"} & set(_called_names(claim)) == set()


class TestTheOrderAssertionFires:
    """The control: a body with the calls in the wrong order must fail the same assertion."""

    def test_a_reversed_synthetic_body_reports_the_reversed_positions(self):
        source = ("async def _claim_anonymous_grant(self):\n"
                  "    await self.grants_db.activate_anonymous_device_grant()\n"
                  "    state = await read_bits_with_retry(self.devicecheck, token)\n"
                  "    await write_bits_with_retry(self.devicecheck, token)\n")
        read, write, activate = _order(_function(source, CLAIM),
                                       ("read_bits_with_retry", "write_bits_with_retry", WRITER))
        # The same expression the real case asserts, which this ordering makes false.
        assert not (read < write < activate)

    def test_a_synthetic_writer_naming_the_seam_is_caught(self):
        source = ("async def activate_anonymous_device_grant(self):\n"
                  "    await self.devicecheck.write_bits(token)\n")
        writer = _function(source, WRITER)
        assert _mentioned_names(writer) & SEAM_NAMES == {"devicecheck", "write_bits"}

    @pytest.mark.parametrize("missing", ["read_bits_with_retry", WRITER])
    def test_a_body_missing_one_of_the_calls_is_reported_rather_than_passed(self, missing):
        """A silently absent call would make `index` raise; it is named instead, so the failure reads."""
        source = "async def _claim_anonymous_grant(self):\n    await write_bits_with_retry(t)\n"
        with pytest.raises(AssertionError, match=f"{missing} is not called at all"):
            _order(_function(source, CLAIM), (missing,))
