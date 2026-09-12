"""The term-open predicate a restore judges a paid entitlement by, over the pure helper that takes
its instant. The boundary is the whole subject: the comparison is `>` and never `>=`, so a term
ending exactly at the instant the request is evaluated is over.
"""
from datetime import UTC, datetime, timedelta

import pytest

from nativespeaker.api.services.restore import _open_term

INSTANT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
A_TICK = timedelta(microseconds=1)
A_MONTH_OUT = INSTANT + timedelta(days=30)


class TestATermEndingAtTheInstantIsNotOpen:
    """T-47-14: a `>=` here attaches a paid grant for a term that has already ended. A live clock
    never lands on the equality, so the helper that takes its instant is where it is pinned."""

    @pytest.mark.parametrize(("candidate", "expected"), [
        (INSTANT - A_TICK, None),
        (INSTANT, None),
        (INSTANT + A_TICK, INSTANT + A_TICK),
    ], ids=["one-tick-before", "the-instant-itself", "one-tick-after"])
    def test_only_a_term_ending_after_the_instant_is_open(self, candidate, expected):
        assert _open_term([candidate], INSTANT) == expected


class TestTheFirstOpenCandidateIsTheAnswer:
    """The recorded term is offered before the proof's, so a restore keeps the term it already wrote."""

    def test_the_first_candidate_that_is_open_wins(self):
        assert _open_term([A_MONTH_OUT, INSTANT + A_TICK], INSTANT) == A_MONTH_OUT

    def test_a_missing_candidate_is_passed_over(self):
        assert _open_term([None, A_MONTH_OUT], INSTANT) == A_MONTH_OUT

    def test_a_closed_candidate_is_passed_over(self):
        assert _open_term([INSTANT - A_TICK, A_MONTH_OUT], INSTANT) == A_MONTH_OUT

    def test_a_sequence_of_missing_candidates_answers_none(self):
        assert _open_term([None, None], INSTANT) is None

    def test_an_empty_sequence_answers_none(self):
        assert _open_term([], INSTANT) is None
