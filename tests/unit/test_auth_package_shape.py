"""How big the auth package is, as a number rather than a claim.

The shape is written as a literal: deriving it from the package would make the file measure itself
and agree with anything. Growing the package is meant to be an edit someone makes on purpose and a
reviewer sees in the diff -- a later phase that adds to `auth/` has to come here and write the new
number down.

This file also carried a one-way ratchet: a `BASELINE` the package had to measure strictly below on
every axis. Phase 37.3 removed it by deliberate decision, not by widening it. That phase replaced a
44-member outcome enum, three mapping tables and five classifier functions with seventeen
declarative one-line exception classes, which is a large simplification that the class count
reports as growth. The proxy had stopped pointing at complexity for this package, so the ceiling
went rather than being quietly relaxed to whatever the next number happened to be.
"""
import ast
from pathlib import Path

from nativespeaker.api import auth as auth_package

AUTH_PACKAGE = Path(auth_package.__file__).parent

# What it measures now: modules, classes, functions.
CURRENT = (8, 12, 34)


def _measure(directory: Path) -> tuple[int, int, int]:
    """Count the top-level modules, and every class and function they define at any nesting depth."""
    modules = sorted(directory.glob("*.py"))
    classes = functions = 0
    for module in modules:
        tree = ast.parse(module.read_text())
        # Walked rather than read off the module's top level, so a method or a nested helper counts.
        classes += sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
        functions += sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                         for node in ast.walk(tree))
    return len(modules), classes, functions


class TestThePackageShrank:
    """The recorded shape, checked instead of described."""

    def test_it_still_measures_the_recorded_current_shape(self):
        """A later phase that grows the package has to come here and write the new number down."""
        assert _measure(AUTH_PACKAGE) == CURRENT


class TestTheMeasurementFires:
    """The control: a measurement that quietly returned nothing would pass the case above."""

    def test_a_method_and_a_nested_helper_both_count_control(self, tmp_path):
        """The recorded shape came from a full walk, so a top-level-only count would not match it."""
        (tmp_path / "m.py").write_text("class C:\n"
                                       "    def method(self):\n"
                                       "        def helper(): pass\n"
                                       "        return helper\n"
                                       "async def top(): pass\n")
        assert _measure(tmp_path) == (1, 1, 3)
