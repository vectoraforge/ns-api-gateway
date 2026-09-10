"""WR-43: `YYYY-MM` is derived in one place, and that place normalizes to UTC before it formats."""
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from nativespeaker.api.tables import monthly_period_for

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "nativespeaker"

SPELLINGS = ('"%Y-%m"', "'%Y-%m'", ":%Y-%m}")
DERIVATION = SRC / "api" / "tables" / "grants.py"


class TestThePeriodIsTheCapturedInstantsUtcMonth:
    """`core.user_monthly_usage.monthly_period` is a UTC calendar month, so the offset decides nothing."""

    def test_a_utc_instant_names_its_own_month(self):
        assert monthly_period_for(datetime(2026, 3, 15, 12, 0, tzinfo=UTC)) == "2026-03"

    def test_an_offset_instant_before_the_boundary_names_the_utc_month(self):
        """Local March 1st at +14:00 is still February in UTC, and February is what the row stores."""
        ahead = datetime(2026, 3, 1, 6, 0, tzinfo=timezone(timedelta(hours=14)))

        assert monthly_period_for(ahead) == "2026-02"

    def test_an_offset_instant_after_the_boundary_names_the_utc_month(self):
        """The mirror case: local February 28th at -11:00 is already March in UTC."""
        behind = datetime(2026, 2, 28, 20, 0, tzinfo=timezone(timedelta(hours=-11)))

        assert monthly_period_for(behind) == "2026-03"

    def test_the_stored_wall_clock_is_not_what_is_reported_control(self):
        """The control: an unconverted `strftime` would answer the two cases above with the local month."""
        ahead = datetime(2026, 3, 1, 6, 0, tzinfo=timezone(timedelta(hours=14)))

        assert ahead.strftime("%Y-%m") != monthly_period_for(ahead)


class TestTheDerivationIsWrittenExactlyOnce:
    """Five copies is what let two of them each claim to be the only one; the claim is now checkable."""

    def _files_formatting_a_period(self) -> list[Path]:
        return sorted(path for path in SRC.rglob("*.py")
                      if any(spelling in path.read_text() for spelling in SPELLINGS))

    def test_only_the_one_function_formats_a_period(self):
        assert self._files_formatting_a_period() == [DERIVATION]

    def test_the_walk_reads_the_whole_package_control(self):
        """The control: a walk that found no file at all would pass the case above on an empty list."""
        assert len(list(SRC.rglob("*.py"))) > 20

    def test_no_spelling_of_the_derivation_hides_from_the_walk_control(self):
        """The control: matching one quoting only, a second copy spelled either of the other two
        stood beside the derivation and the case above still read it as the only one."""
        copies = ('    return evaluated_at.astimezone(UTC).strftime("%Y-%m")',
                  "    return evaluated_at.astimezone(UTC).strftime('%Y-%m')",
                  '    return f"{evaluated_at.astimezone(UTC):%Y-%m}"')

        assert all(any(spelling in copy for spelling in SPELLINGS) for copy in copies)

    def test_the_neighbouring_timestamp_format_is_not_one_of_them_control(self):
        """The mirror: `logs.py` formats a whole datetime, which none of the three may claim."""
        assert not any(spelling in '    TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True)'
                       for spelling in SPELLINGS)
