"""The docstring bar of AGENTS.md, measured rather than asserted.

This is the ratchet whose recorded baselines plans 06 through 09 drive to zero.
"""
from pathlib import Path


def over_long(root: Path, *, recurse: bool = True) -> list[tuple[str, str, int]]:
    """Every docstring under `root` whose stripped body runs past three lines."""
    raise NotImplementedError


class TestTheMeasurementFires:
    """The control: a gate that quietly reported nothing would pass every recorded baseline."""

    def test_a_four_line_docstring_is_reported(self, tmp_path):
        """Four lines is the first length over the bar."""
        (tmp_path / "m.py").write_text('"""One.\n\nTwo.\nThree.\n"""\n')
        assert over_long(tmp_path) == [("m.py", "<module>", 4)]

    def test_a_three_line_docstring_is_not_reported(self, tmp_path):
        """The boundary case, which a gate reporting everything would fail."""
        (tmp_path / "m.py").write_text('"""One.\nTwo.\nThree.\n"""\n')
        assert over_long(tmp_path) == []

    def test_the_walk_reaches_a_method_inside_a_class(self, tmp_path):
        """A module-level-only read would report nothing here."""
        (tmp_path / "m.py").write_text("class C:\n"
                                       "    def method(self):\n"
                                       '        """One.\n'
                                       "\n"
                                       "        Two.\n"
                                       "        Three.\n"
                                       '        """\n'
                                       "        return None\n")
        assert over_long(tmp_path) == [("m.py", "C.method", 4)]

    def test_a_file_without_docstrings_contributes_nothing(self, tmp_path):
        """Absence is not an error."""
        (tmp_path / "m.py").write_text("x = 1\n")
        assert over_long(tmp_path) == []
