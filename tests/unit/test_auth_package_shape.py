"""How big the auth package is, as a number rather than a claim.

The package was trimmed from a recorded historical shape, and this file is where that shrink is
checked instead of described. Both shapes are written as literals: deriving either one from the
package would make the file measure itself and agree with anything. Widening the numbers is meant
to be an edit someone makes on purpose and a reviewer sees in the diff.
"""
import ast
from pathlib import Path

import pytest

from nativespeaker.api import auth as auth_package

AUTH_PACKAGE = Path(auth_package.__file__).parent

# What the package measured before it was trimmed: modules, classes, functions.
BASELINE = (14, 28, 57)

# What it measures now. Growing the package past this fails the second case below.
CURRENT = (10, 19, 44)

AXES = (("modules", 0), ("classes", 1), ("functions", 2))


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
    """Fewer modules, fewer classes and fewer functions than before -- all three axes, not two of them."""

    @pytest.mark.parametrize("axis,index", AXES, ids=[axis for axis, _ in AXES])
    def test_it_is_strictly_smaller_than_the_baseline_on_every_axis(self, axis, index):
        measured = _measure(AUTH_PACKAGE)[index]
        assert measured < BASELINE[index], f"{axis}: {measured} is not below {BASELINE[index]}"

    def test_it_still_measures_the_recorded_current_shape(self):
        """A later phase that grows the package has to come here and write the new number down."""
        assert _measure(AUTH_PACKAGE) == CURRENT


class TestTheMeasurementFires:
    """The controls: a measurement that quietly returned nothing would pass both cases above."""

    def test_a_package_at_the_baseline_shape_is_not_strictly_smaller_control(self, tmp_path):
        modules, classes, functions = BASELINE
        for index in range(modules):
            body = "pass\n"
            if index == 0:
                body = ("".join(f"class C{n}: pass\n" for n in range(classes))
                        + "".join(f"def f{n}(): pass\n" for n in range(functions)))
            (tmp_path / f"m{index}.py").write_text(body)

        assert _measure(tmp_path) == BASELINE
        assert not all(measured < baseline
                       for measured, baseline in zip(_measure(tmp_path), BASELINE, strict=True))

    def test_a_method_and_a_nested_helper_both_count_control(self, tmp_path):
        """The baseline came from a full walk, so a top-level-only count would not be comparable to it."""
        (tmp_path / "m.py").write_text("class C:\n"
                                       "    def method(self):\n"
                                       "        def helper(): pass\n"
                                       "        return helper\n"
                                       "async def top(): pass\n")
        assert _measure(tmp_path) == (1, 1, 3)
