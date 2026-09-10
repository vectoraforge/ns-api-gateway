"""How big the auth package is, as a number rather than a claim.

The shape is a literal: derived from the package, it would measure itself and agree with anything.
"""
import ast
from pathlib import Path

from nativespeaker.api import auth as auth_package

AUTH_PACKAGE = Path(auth_package.__file__).parent

# What it measures now: modules, classes, functions.
# 65: `store_notifications.term_end_for`, the one spelling of the term both write paths read.
# 66, 67: the two `__post_init__` coercions that make the declared `status` type true, so the
# identity and value comparisons its readers use cannot answer one field two ways.
# 68: `StoreNotificationVerifier.verify_transaction`, the second member `RestoreService` calls of
# the seam it is now annotated against, so a double that omits it is a type error rather than an
# `AttributeError` inside a handler.
# 25, 69: `google_play.CappedRefreshRequest` and its `__call__`, which cap the credential refresh
# at the module's own timeout instead of google-auth's 120-second default (44 WR-01).
# 70: `PlayDeveloperSubscriptions._credential_in_hand`, the lazy rebuild that keeps a metadata
# server blip at boot from disabling the Play read for the pod's whole life (45 WR-51).
CURRENT = (8, 25, 70)


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
