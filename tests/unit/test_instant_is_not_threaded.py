"""Roadmap criteria 1, 2 and 4, made executable: the dependency, the parameter and the prose are gone."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "nativespeaker"
TESTS = REPO / "tests"
THIS_FILE = Path(__file__).resolve()

API = SRC / "api"
THREADED_PACKAGES = ("app", "crud", "routers", "services")

DEPENDENCY = "get_evaluated_at"
PARAMETER = "evaluated_at"
BANNED_SPELLINGS = (DEPENDENCY, "captured instant", "shared instant", "one instant", "evaluation time")

KEEPERS = ("src/nativespeaker/api/auth/app_store.py",
           "src/nativespeaker/api/auth/google_play.py",
           "src/nativespeaker/api/tables/grants.py")


def _sources(*roots: Path) -> list[Path]:
    """Every `.py` file under `roots`, less this one, which carries every string the cases below forbid."""
    return sorted(path for root in roots for path in root.rglob("*.py") if path.resolve() != THIS_FILE)


def _spellings_in(text: str) -> list[str]:
    """Which of the banned spellings `text` carries, matched without regard to case."""
    lowered = text.lower()
    return [spelling for spelling in BANNED_SPELLINGS if spelling in lowered]


def _files_containing(needle: str, *roots: Path) -> list[str]:
    """The path of every walked file whose text carries `needle`, relative to the repository root."""
    return [str(path.relative_to(REPO)) for path in _sources(*roots) if needle in path.read_text()]


def _threaded_packages() -> list[Path]:
    return [API / package for package in THREADED_PACKAGES]


class TestTheDependencyIsGone:
    """Criterion 1: nothing in the package or in the suites defines, declares or overrides it."""

    def test_no_file_names_the_dependency(self):
        assert _files_containing(DEPENDENCY, SRC, TESTS) == []


class TestNoLayerIsHandedAnInstant:
    """Criterion 2, over app, crud, routers and services alone. `auth/` and `tables/` are excluded
    because their pure helpers take the datetime they compute from, which criterion 3 allows."""

    def test_no_threaded_package_names_the_parameter(self):
        assert _files_containing(PARAMETER, *_threaded_packages()) == []


class TestNoProseNamesTheRemovedSubject:
    """Criterion 4: a comment outliving its subject is what makes the next reader wrong."""

    def test_no_file_carries_a_banned_spelling(self):
        found = {str(path.relative_to(REPO)): _spellings_in(path.read_text())
                 for path in _sources(SRC, TESTS)}
        assert {path: spellings for path, spellings in found.items() if spellings} == {}


class TestTheWalkIsNotVacuous:
    """A guard whose walk read nothing, or whose matcher matched nothing, reports an absence it never looked for."""

    def test_the_walk_reads_real_files_on_both_sides(self):
        """The control: a walk that yielded no file passes all three cases above on an empty list."""
        assert (len(_sources(SRC)) > 20, len(_sources(TESTS)) > 20) == (True, True)

    def test_the_matcher_reports_a_spelling_it_is_given(self):
        """The control: a matcher that never matched would pass the criterion-4 case on every file."""
        assert _spellings_in("# One Instant per request, shared by construction") == ["one instant"]

    def test_a_near_miss_is_not_reported(self):
        """The mirror: neither the bare word nor the helper's own parameter is what the criteria forbid."""
        assert _spellings_in("instant = datetime.now(UTC)") == []
        assert _spellings_in("period = monthly_period_for(evaluated_at)") == []

    def test_the_threaded_walk_skips_the_helpers_that_keep_the_name(self):
        """The scope control: these three carry the name and are not reported, so widening the walk
        to `auth/` or `tables/` would rename four pure helpers for no reason."""
        assert all(PARAMETER in (REPO / path).read_text() for path in KEEPERS)

        walked = {str(path.relative_to(REPO)) for path in _sources(*_threaded_packages())}

        assert walked != set()
        assert walked & set(KEEPERS) == set()
