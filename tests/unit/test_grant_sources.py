"""ANONGRANT-01 and REGGRANT-01's single-writer claims, as a walk over `src/` rather than a sentence.
Each free grant source is written from exactly one site, its crud activation writer, and the
free-grant membership is one named constant rather than a repeated pair.
"""
import ast
from pathlib import Path

import pytest

from nativespeaker.api import crud as crud_package
from nativespeaker.api.crud.grants import GrantsDB
from nativespeaker.api.tables.grants import FREE_GRANT_SOURCES, AccessGrantSource

SRC = Path(crud_package.__file__).parents[3]

MEMBER = "anonymous_device_grant"
ENUM = "AccessGrantSource"
WRITER = "activate_anonymous_device_grant"

# Every module under `src/` that names the member off its enum. A new entry is a new site to justify.
NAMING_MODULES = {
    "nativespeaker/api/crud/grants.py",
    "nativespeaker/api/services/auth.py",
    "nativespeaker/api/tables/grants.py",
}

MEMBER_REGISTERED = "registered_account_grant"
WRITER_REGISTERED = "activate_registered_account_grant"

# Every module under `src/` that names the registered member off its enum. A new entry is a new site.
NAMING_MODULES_REGISTERED = {
    "nativespeaker/api/crud/grants.py",
    "nativespeaker/api/services/auth.py",
    "nativespeaker/api/tables/grants.py",
}


def _modules() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)


def _construction_sites(source: str, member: str = MEMBER) -> list[int]:
    """Line numbers of every `AccessGrant(...)` built with `member` as its source."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "AccessGrant"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "source" and _names_the_member(keyword.value, member):
                found.append(node.lineno)
    return found


def _names_the_member(node: ast.AST, member: str = MEMBER) -> bool:
    """Whether `node` is the enum member read off its enum, which is the only admissible spelling."""
    return (isinstance(node, ast.Attribute) and node.attr == member
            and isinstance(node.value, ast.Name) and node.value.id == ENUM)


def _mentions(source: str, member: str = MEMBER) -> int:
    """How many times the member is read off its enum anywhere in `source`."""
    return sum(_names_the_member(node, member) for node in ast.walk(ast.parse(source)))


def _function(source: str, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in the source given")


CRUD_GRANTS = SRC / "nativespeaker/api/crud/grants.py"


class TestTheAnonymousDeviceGrantHasExactlyOneWriter:
    """A second writer added by a later phase has to come here and change a number someone reads."""

    def test_the_whole_tree_holds_exactly_one_construction_site(self):
        sites = {path.relative_to(SRC).as_posix(): _construction_sites(path.read_text())
                 for path in _modules()}
        found = {module: lines for module, lines in sites.items() if lines}
        assert list(found) == ["nativespeaker/api/crud/grants.py"]
        assert len(next(iter(found.values()))) == 1

    def test_the_one_site_is_inside_the_crud_activation_writer(self):
        """Not merely in the right module: in the one function that takes both lock tiers."""
        writer = _function(CRUD_GRANTS.read_text(), WRITER)
        # Two occurrences: the in-lock repeat test, and the one construction of the grant row.
        assert sum(_names_the_member(node) for node in ast.walk(writer)) == 2

    def test_only_the_recorded_modules_name_the_member_at_all(self):
        naming = {path.relative_to(SRC).as_posix() for path in _modules()
                  if _mentions(path.read_text())}
        assert naming == NAMING_MODULES


class TestTheRegisteredAccountGrantHasExactlyOneWriter:
    """A walk over today's `src/` tree, and only that: not a database-level guarantee, and not a
    promise about code that has not been written yet. It says where the one site is right now."""

    def test_the_whole_tree_holds_exactly_one_construction_site(self):
        sites = {path.relative_to(SRC).as_posix(): _construction_sites(path.read_text(),
                                                                      MEMBER_REGISTERED)
                 for path in _modules()}
        found = {module: lines for module, lines in sites.items() if lines}
        assert list(found) == ["nativespeaker/api/crud/grants.py"]
        assert len(next(iter(found.values()))) == 1

    def test_the_one_site_is_inside_the_crud_activation_writer(self):
        """Not merely in the right module: in the one function that takes both lock tiers."""
        writer = _function(CRUD_GRANTS.read_text(), WRITER_REGISTERED)
        # Three: the in-lock repeat test, the lifetime index's own question, and the one construction.
        assert sum(_names_the_member(node, MEMBER_REGISTERED) for node in ast.walk(writer)) == 3

    def test_only_the_recorded_modules_name_the_member_at_all(self):
        naming = {path.relative_to(SRC).as_posix() for path in _modules()
                  if _mentions(path.read_text(), MEMBER_REGISTERED)}
        assert naming == NAMING_MODULES_REGISTERED

    def test_the_writer_is_reachable_as_a_method_rather_than_a_free_function(self):
        """The control on the three cases above: they parse the module the class is defined in."""
        assert hasattr(GrantsDB, WRITER_REGISTERED)


class TestTheFreeGrantMembershipIsNamedOnce:
    """The lifetime rule is one constant, so a third free source cannot be added to only one of two places."""

    def test_the_constant_carries_exactly_two_members(self):
        assert len(FREE_GRANT_SOURCES) == 2
        assert FREE_GRANT_SOURCES == frozenset({AccessGrantSource.anonymous_device_grant,
                                                AccessGrantSource.registered_account_grant})

    def test_the_eligibility_read_filters_on_the_constant_and_not_on_a_literal_pair(self):
        statement = _function(CRUD_GRANTS.read_text(), "_prior_free_grant_statement")
        names = {node.id for node in ast.walk(statement) if isinstance(node, ast.Name)}
        assert "FREE_GRANT_SOURCES" in names
        # A literal pair here would be a second copy of the membership, drifting from the index.
        assert sum(_names_the_member(node) for node in ast.walk(statement)) == 0

    def test_the_writer_is_reachable_as_a_method_rather_than_a_free_function(self):
        """The control on the two cases above: they parse the module the class is actually defined in."""
        assert hasattr(GrantsDB, WRITER)


class TestTheWalkFires:
    """The control: a walk that quietly found nothing would pass every case above."""

    def test_a_synthetic_module_with_two_sites_is_counted_as_two(self):
        source = ("g = AccessGrant(user_id=u, source=AccessGrantSource.anonymous_device_grant)\n"
                  "def later():\n"
                  "    return AccessGrant(source=AccessGrantSource.anonymous_device_grant)\n")
        assert len(_construction_sites(source)) == 2

    @pytest.mark.parametrize("source", [
        "g = AccessGrant(source=AccessGrantSource.manual)",
        "g = AccessGrant(source=other.anonymous_device_grant)",
        "g = UserMonthlyUsage(source=AccessGrantSource.anonymous_device_grant)",
    ], ids=["another_source", "another_enum", "another_table_same_member"])
    def test_a_near_miss_is_not_counted(self, source):
        """The walk matches the construction it claims to, not anything that merely spells the word."""
        assert _construction_sites(source) == []

    def test_the_mention_count_distinguishes_a_read_from_a_definition(self):
        assert _mentions("x = AccessGrantSource.anonymous_device_grant") == 1
        assert _mentions("anonymous_device_grant = 'anonymous_device_grant'") == 0


class TestTheRegisteredWalkFires:
    """The same control for the registered member: a walk that quietly found nothing would pass."""

    def test_a_synthetic_module_with_two_sites_is_counted_as_two(self):
        source = ("g = AccessGrant(user_id=u, source=AccessGrantSource.registered_account_grant)\n"
                  "def later():\n"
                  "    return AccessGrant(source=AccessGrantSource.registered_account_grant)\n")
        assert len(_construction_sites(source, MEMBER_REGISTERED)) == 2

    @pytest.mark.parametrize("source", [
        "g = AccessGrant(source=AccessGrantSource.manual)",
        "g = AccessGrant(source=other.registered_account_grant)",
        "g = UserMonthlyUsage(source=AccessGrantSource.registered_account_grant)",
    ], ids=["another_source", "another_enum", "another_table_same_member"])
    def test_a_near_miss_is_not_counted(self, source):
        """The walk matches the construction it claims to, not anything that merely spells the word."""
        assert _construction_sites(source, MEMBER_REGISTERED) == []

    def test_the_mention_count_distinguishes_a_read_from_a_definition(self):
        assert _mentions("x = AccessGrantSource.registered_account_grant", MEMBER_REGISTERED) == 1
        assert _mentions("registered_account_grant = 'x'", MEMBER_REGISTERED) == 0

    def test_the_anonymous_member_is_not_counted_as_the_registered_one(self):
        """The two walks must not alias: each near-miss above would pass vacuously if they did."""
        source = "g = AccessGrant(source=AccessGrantSource.anonymous_device_grant)"
        assert _construction_sites(source, MEMBER_REGISTERED) == []
        assert len(_construction_sites(source)) == 1
