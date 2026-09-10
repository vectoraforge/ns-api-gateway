"""ANONGRANT-01 and REGGRANT-01's single-writer claims, as a walk over `src/` rather than a sentence.
Each free grant source is written from exactly one site, its crud activation writer, and the
free-grant membership is one named constant rather than a repeated pair.
"""
import ast
from pathlib import Path

import pytest

from nativespeaker.api import crud as crud_package
from nativespeaker.api.crud.grants import GrantsDB
from nativespeaker.api.crud.subscriptions import SubscriptionsDB
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

MEMBER_SUBSCRIPTION = "subscription"
WRITER_SUBSCRIPTION = "write_subscription_grant"

# Every module under `src/` that names the subscription member off its enum. A new entry is a new site.
NAMING_MODULES_SUBSCRIPTION = {
    "nativespeaker/api/crud/subscriptions.py",
    "nativespeaker/api/services/restore.py",
}


def _modules() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)


def _tree_and_aliases(source: str) -> tuple[ast.Module, frozenset[str]]:
    """The parsed module, and every local name bound to the enum. `import ... as S` is the same
    enum under another name, and a walk that assumed the canonical spelling never saw it."""
    tree = ast.parse(source)
    aliases = {ENUM}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            aliases |= {alias.asname or alias.name for alias in node.names if alias.name == ENUM}
    return tree, frozenset(aliases)


def _is_access_grant(func: ast.AST) -> bool:
    """The grant class however it was reached: bare, or qualified as `tables.AccessGrant`."""
    return ((isinstance(func, ast.Name) and func.id == "AccessGrant")
            or (isinstance(func, ast.Attribute) and func.attr == "AccessGrant"))


def _construction_sites(source: str, member: str = MEMBER) -> list[int]:
    """Line numbers of every `AccessGrant(...)` built with `member` as its source."""
    tree, aliases = _tree_and_aliases(source)
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_access_grant(node.func)):
            continue
        for keyword in node.keywords:
            if keyword.arg == "source" and _names_the_member(keyword.value, member, aliases):
                found.append(node.lineno)
    return found


def _names_the_member(node: ast.AST, member: str = MEMBER,
                      aliases: frozenset[str] = frozenset({ENUM})) -> bool:
    """Whether `node` is the enum member read off its enum, under any name the enum is bound to."""
    return (isinstance(node, ast.Attribute) and node.attr == member
            and isinstance(node.value, ast.Name) and node.value.id in aliases)


def _reads_the_enum(node: ast.AST, aliases: frozenset[str]) -> bool:
    """Whether `node` reads some member off the enum. Which member is `_names_the_member`'s question."""
    return (isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name) and node.value.id in aliases)


def _undecidable_sites(source: str) -> list[int]:
    """Every site this walk cannot rule on: a grant built from `**fields`, a `source=` handed an
    indirection, and any `getattr` on the enum. Reported rather than passed over as absent, which
    is how a second writer spelled any of these would arrive with every count above still green."""
    tree, aliases = _tree_and_aliases(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (isinstance(node.func, ast.Name) and node.func.id == "getattr" and node.args
                and isinstance(node.args[0], ast.Name) and node.args[0].id in aliases):
            found.append(node.lineno)
            continue
        if not _is_access_grant(node.func):
            continue
        if any(keyword.arg is None for keyword in node.keywords):
            found.append(node.lineno)
            continue
        for keyword in node.keywords:
            if keyword.arg == "source" and not _reads_the_enum(keyword.value, aliases):
                found.append(node.lineno)
    return sorted(found)


def _mentions(source: str, member: str = MEMBER) -> int:
    """How many times the member is read off its enum anywhere in `source`."""
    tree, aliases = _tree_and_aliases(source)
    return sum(_names_the_member(node, member, aliases) for node in ast.walk(tree))


def _function(source: str, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not defined in the source given")


CRUD_GRANTS = SRC / "nativespeaker/api/crud/grants.py"
CRUD_SUBSCRIPTIONS = SRC / "nativespeaker/api/crud/subscriptions.py"


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
        assert sum(_names_the_member(node, MEMBER_REGISTERED) for node in ast.walk(writer)) == 4

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


class TestTheSubscriptionGrantHasExactlyOneWriter:
    """APPLEHOOK-01. The third grant source, and the first with a walk behind it from its first day:
    Phase 45's restore is the specific future writer this keeps from arriving quietly."""

    def test_the_whole_tree_holds_exactly_one_construction_site(self):
        sites = {path.relative_to(SRC).as_posix(): _construction_sites(path.read_text(),
                                                                      MEMBER_SUBSCRIPTION)
                 for path in _modules()}
        found = {module: lines for module, lines in sites.items() if lines}
        assert list(found) == ["nativespeaker/api/crud/subscriptions.py"]
        assert len(next(iter(found.values()))) == 1

    def test_the_one_site_is_inside_the_crud_subscription_writer(self):
        """Not merely in the right module: in the one function the two lock tiers are taken for."""
        writer = _function(CRUD_SUBSCRIPTIONS.read_text(), WRITER_SUBSCRIPTION)
        assert sum(_names_the_member(node, MEMBER_SUBSCRIPTION) for node in ast.walk(writer)) == 3

    def test_only_the_recorded_modules_name_the_member_at_all(self):
        naming = {path.relative_to(SRC).as_posix() for path in _modules()
                  if _mentions(path.read_text(), MEMBER_SUBSCRIPTION)}
        assert naming == NAMING_MODULES_SUBSCRIPTION

    def test_the_writer_is_reachable_as_a_method_rather_than_a_free_function(self):
        """The control on the three cases above: they parse the module the class is defined in."""
        assert hasattr(SubscriptionsDB, WRITER_SUBSCRIPTION)


class TestTheSubscriptionWalkFires:
    """The same control for the subscription member: a walk that quietly found nothing would pass."""

    def test_a_synthetic_module_with_two_sites_is_counted_as_two(self):
        source = ("g = AccessGrant(user_id=u, source=AccessGrantSource.subscription)\n"
                  "def later():\n"
                  "    return AccessGrant(source=AccessGrantSource.subscription)\n")
        assert len(_construction_sites(source, MEMBER_SUBSCRIPTION)) == 2

    @pytest.mark.parametrize("source", [
        "g = AccessGrant(source=AccessGrantSource.manual)",
        "g = AccessGrant(source=other.subscription)",
        "g = UserMonthlyUsage(source=AccessGrantSource.subscription)",
    ], ids=["another_source", "another_enum", "another_table_same_member"])
    def test_a_near_miss_is_not_counted(self, source):
        """The walk matches the construction it claims to, not anything that merely spells the word."""
        assert _construction_sites(source, MEMBER_SUBSCRIPTION) == []

    def test_the_mention_count_distinguishes_a_read_from_a_definition(self):
        assert _mentions("x = AccessGrantSource.subscription", MEMBER_SUBSCRIPTION) == 1
        assert _mentions("subscription = 'subscription'", MEMBER_SUBSCRIPTION) == 0

    def test_the_free_members_are_not_counted_as_the_subscription_one(self):
        """The three walks must not alias: every near-miss above would pass vacuously if they did."""
        source = "g = AccessGrant(source=AccessGrantSource.registered_account_grant)"
        assert _construction_sites(source, MEMBER_SUBSCRIPTION) == []
        assert len(_construction_sites(source, MEMBER_REGISTERED)) == 1


class TestNoWriterArrivesInASpellingTheWalkCannotRead:
    """The counted walks above read one spelling of a construction and one of the enum. A module
    that reached either another way was passed over as absent, so a second writer could land with
    every count in this file still green. These close the gap from the other side."""

    def test_no_module_builds_a_grant_this_file_cannot_rule_on(self):
        undecidable = {path.relative_to(SRC).as_posix(): _undecidable_sites(path.read_text())
                       for path in _modules()}

        assert {module: lines for module, lines in undecidable.items() if lines} == {}

    @pytest.mark.parametrize("source", [
        'g = AccessGrant(**{"source": AccessGrantSource.subscription})',
        "g = AccessGrant(source=SOURCE)",
        'g = AccessGrant(source=getattr(AccessGrantSource, "subscription"))',
    ], ids=["kwargs_splat", "an_indirection", "getattr_on_the_enum"])
    def test_a_source_the_walk_cannot_read_is_reported(self, source):
        """The control on the case above: a detector that found nothing would pass it always."""
        assert _undecidable_sites(source) != []

    def test_a_plainly_spelled_construction_is_not_reported_control(self):
        """The other control: reporting everything would make the case above permanently red."""
        assert _undecidable_sites("g = AccessGrant(source=AccessGrantSource.subscription)") == []


class TestTheCountedWalksReadEverySpellingTheyCanDecide:
    """The two spellings the counted walks used to miss outright, now decided rather than skipped."""

    def test_a_grant_built_off_its_module_is_a_construction_site(self):
        source = "g = tables.AccessGrant(source=AccessGrantSource.subscription)"

        assert len(_construction_sites(source, MEMBER_SUBSCRIPTION)) == 1

    def test_an_aliased_enum_import_is_the_same_enum(self):
        source = ("from nativespeaker.api.tables import AccessGrantSource as S\n"
                  "g = AccessGrant(source=S.subscription)\n")

        assert len(_construction_sites(source, MEMBER_SUBSCRIPTION)) == 1
        assert _mentions(source, MEMBER_SUBSCRIPTION) == 1

    def test_an_unrelated_alias_is_still_not_the_enum_control(self):
        """The control: resolving every alias would count `other.subscription` as a site too."""
        source = ("from somewhere import SomethingElse as S\n"
                  "g = AccessGrant(source=S.subscription)\n")

        assert _construction_sites(source, MEMBER_SUBSCRIPTION) == []
        assert _mentions(source, MEMBER_SUBSCRIPTION) == 0
