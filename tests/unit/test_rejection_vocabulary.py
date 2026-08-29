"""The rejection family's log vocabulary, written down rather than derived from whatever the classes spell.

Both sides are literals. Deriving the expected set from the classes would make the file measure
itself and agree with any rename -- and a rename here is not a refactor: the class name *is* the
structured log event name (D-02), so renaming one silently re-keys every grep and every dashboard
that reads it. Extending the family is meant to be an edit someone makes on purpose and a reviewer
sees in the diff.

The second case guards the other direction: the base's `error_class` is `INTERNAL_ERROR` so a
subclass that forgets to declare one fails closed, and this file is what stops that fail-closed
default from becoming a silent 500 nobody notices.
"""
import pytest

from nativespeaker.api.app.error_handlers import camel_to_snake
from nativespeaker.api.auth import exceptions as exceptions_module
from nativespeaker.api.auth.exceptions import (
    AuthRejected,
    ChallengeConsumed,
    ChallengeExpired,
    ChallengeIdentityMismatch,
    ChallengeNotFound,
    ChallengeOperationMismatch,
    ChallengeRejected,
    NotLinked,
    Unavailable,
    UserNotFound,
)
from nativespeaker.api.errors import IDENTITY_ALREADY_LINKED, INTERNAL_ERROR

# The five leaves under one 409 base, listed here rather than derived, for the same reason the event
# names below are: this file is where a change to the family is meant to become a visible edit.
CHALLENGE_ARMS = (ChallengeNotFound, ChallengeExpired, ChallengeConsumed,
                  ChallengeIdentityMismatch, ChallengeOperationMismatch)

FAMILY_MODULE = exceptions_module.__name__

# One entry per class in the family. Plans 02, 03 and 04 each append their own arms here.
EVENT_NAMES = frozenset({
    "identity_already_linked",
    "provider_account_already_linked",
    "invalid_external_jwt",
    # Deliberately `pre_auth_...`, while the client-visible code stays `preauth_...`: the class name
    # follows `PreAuthIdentity` in `auth/context.py`, and D-02 makes the event whatever it spells.
    "pre_auth_identity_not_allowed",
    "identity_unresolvable",
    # The lookup arms. The group base is listed too: it is a member of the family the walk finds,
    # even though nothing raises it -- an intermediate base is not a place to hide from this file.
    "provider_lookup_error",
    "user_not_found",
    "unavailable",
    "not_linked",
    # The challenge arms, on the same terms: the group base is a member of the family too.
    "challenge_rejected",
    "challenge_not_found",
    "challenge_expired",
    "challenge_consumed",
    "challenge_identity_mismatch",
    "challenge_operation_mismatch",
})


def _family(root: type) -> list[type]:
    """Every class under `root`, at any depth -- an intermediate base is not a place to hide."""
    found: list[type] = []
    for subclass in root.__subclasses__():
        found.append(subclass)
        found.extend(_family(subclass))
    return found


def _production_family() -> list[type]:
    """The family as D-01 places it: one module. A synthetic subclass built by a control cannot join."""
    return [cls for cls in _family(AuthRejected) if cls.__module__ == FAMILY_MODULE]


def _undeclared(classes: list[type], *, root: type) -> list[str]:
    """Leaves that would answer the base's fail-closed default because nothing below the base declares.

    Reported all at once rather than one per run, the way `error_handlers.py::assert_registry_total` reports
    registry defects: finding the second defect should not cost a second edit-and-rerun.
    """
    problems: list[str] = []
    for cls in classes:
        if cls.__subclasses__():
            # An intermediate base answers through its leaves; D-14's one-409 base is exactly this.
            continue
        declared = any(ancestor is not root and "error_class" in vars(ancestor)
                       for ancestor in cls.__mro__)
        if not declared:
            problems.append(f"{cls.__name__} declares no error_class and inherits none below "
                            f"{root.__name__}, so it would answer {root.error_class.code!r}")
    return problems


class TestTheEventVocabularyIsWrittenDown:
    """The class names are the log vocabulary, so the set of them is the contract."""

    def test_the_family_spells_exactly_the_recorded_event_names(self):
        derived = {camel_to_snake(cls.__name__) for cls in _production_family()}
        assert derived == EVENT_NAMES

    def test_every_class_lives_in_the_one_module_the_family_was_given(self):
        """D-01 names one path; a second home would mean two vocabularies and one of them unwatched."""
        assert FAMILY_MODULE == "nativespeaker.api.auth.exceptions"
        assert _production_family(), "the walk found no subclasses at all"


class TestTheLookupArmsCarryStageAndOnlyABoundedCause:
    """`stage` always, `cause` only when there is one, and nothing else reaches a log line."""

    @pytest.mark.parametrize("rejection,status", [
        (UserNotFound(stage="provider_lookup"), 401),
        (Unavailable(stage="provider_lookup"), 503),
        (NotLinked(stage="provider_classification", cause="invalid-shape"), 403),
    ], ids=["user_not_found", "unavailable", "not_linked"])
    def test_each_arm_answers_the_status_the_returned_outcome_earned(self, rejection, status):
        assert rejection.error_class.status == status

    def test_an_arm_with_no_cause_emits_no_cause_key_at_all(self):
        """Not `{"cause": None}`: the absent key is what the deleted `bounded = {} if ...` produced."""
        assert UserNotFound(stage="provider_lookup").log_fields() == {"stage": "provider_lookup"}
        assert Unavailable(stage="issuer_selection").log_fields() == {"stage": "issuer_selection"}

    def test_the_classification_arm_emits_both_keys(self):
        assert NotLinked(stage="provider_classification", cause="invalid-shape").log_fields() == {
            "stage": "provider_classification", "cause": "invalid-shape",
        }

    @pytest.mark.parametrize("rejection", [
        UserNotFound(stage="provider_lookup"),
        Unavailable(stage="provider_lookup"),
        NotLinked(stage="provider_classification", cause="invalid-shape"),
    ], ids=["user_not_found", "unavailable", "not_linked"])
    def test_every_logged_value_is_a_plain_string(self, rejection):
        """The provider's own text must never become a log value here; both fields are ours."""
        assert all(isinstance(value, str) for value in rejection.log_fields().values())


class TestTheChallengeArmsAnswerOneThingAndDeclareNothing:
    """D-14's anti-oracle property, asserted as structure rather than as five equal answers.

    Five equal answers is what a client sees; what makes it stay true is that there is only one
    answer to change. The 409 is declared once on `ChallengeRejected` and each of the five inherits
    it, so making one of them answer differently takes a deliberate override that a reviewer sees.
    """

    def test_the_five_are_exactly_the_leaves_under_the_shared_base(self):
        """A sixth arm added without coming here would be a rejection nobody checked the answer of."""
        assert set(_family(ChallengeRejected)) == set(CHALLENGE_ARMS)

    @pytest.mark.parametrize("arm", CHALLENGE_ARMS, ids=lambda c: c.__name__)
    def test_no_arm_declares_an_error_class_of_its_own(self, arm):
        """Deliberately unlike `AnalysisError`/`TransientLLMError` in `error_handlers.py`, which re-declares."""
        assert "error_class" not in vars(arm)
        assert arm.error_class is ChallengeRejected.error_class

    @pytest.mark.parametrize("arm", CHALLENGE_ARMS, ids=lambda c: c.__name__)
    def test_every_arm_answers_the_one_challenge_required_class(self, arm):
        assert arm.error_class.status == 409
        assert arm.error_class.code == "challenge_required"

    @pytest.mark.parametrize("arm", CHALLENGE_ARMS, ids=lambda c: c.__name__)
    def test_no_arm_can_carry_anything_into_its_log_line(self, arm):
        """No `__init__` and no fields, so the secret handle cannot be passed to one of these."""
        assert arm().log_fields() == {}

    def test_the_five_are_still_five_distinct_log_events(self):
        """One answer to the client and five records in the log is the whole point of the shape."""
        events = [camel_to_snake(arm.__name__) for arm in CHALLENGE_ARMS]
        assert sorted(events) == sorted(set(events))
        assert set(events) == {"challenge_not_found", "challenge_expired", "challenge_consumed",
                               "challenge_identity_mismatch", "challenge_operation_mismatch"}


class TestNoLeafSilentlyAnswersTheFailClosedDefault:
    """`INTERNAL_ERROR` on the base is a tripwire, not a default anybody is allowed to rely on."""

    def test_every_leaf_declares_its_class_or_inherits_one_below_the_base(self):
        problems = _undeclared(_production_family(), root=AuthRejected)
        if problems:
            raise AssertionError("the rejection family has undeclared leaves:\n  "
                                 + "\n  ".join(problems))


class TestTheMeasurementFires:
    """The controls: a walk that quietly returned nothing would pass both cases above."""

    def test_a_leaf_declaring_nothing_is_reported_and_a_declaring_sibling_is_not(self):
        class _SyntheticBase(Exception):
            error_class = INTERNAL_ERROR

        class _Intermediate(_SyntheticBase):
            pass

        class _SilentLeaf(_Intermediate):
            pass

        class _DeclaringLeaf(_SyntheticBase):
            error_class = IDENTITY_ALREADY_LINKED

        problems = _undeclared(_family(_SyntheticBase), root=_SyntheticBase)

        assert len(problems) == 1
        assert problems[0].startswith("_SilentLeaf ")
        # The intermediate is skipped because it has a leaf, and the declaring sibling is fine.
        assert "_Intermediate" not in problems[0]
        assert "_DeclaringLeaf" not in problems[0]

    def test_a_leaf_that_inherits_from_a_declaring_intermediate_is_accepted(self):
        """D-14's shape: five leaves sharing one 409 base. None of them declares, and none is a defect."""
        class _SyntheticBase(Exception):
            error_class = INTERNAL_ERROR

        class _DeclaringIntermediate(_SyntheticBase):
            error_class = IDENTITY_ALREADY_LINKED

        class _Leaf(_DeclaringIntermediate):
            pass

        assert _undeclared(_family(_SyntheticBase), root=_SyntheticBase) == []

    def test_every_defect_is_reported_in_one_message(self):
        class _SyntheticBase(Exception):
            error_class = INTERNAL_ERROR

        class _FirstSilent(_SyntheticBase):
            pass

        class _SecondSilent(_SyntheticBase):
            pass

        problems = _undeclared(_family(_SyntheticBase), root=_SyntheticBase)
        assert sorted(problem.split()[0] for problem in problems) == ["_FirstSilent",
                                                                     "_SecondSilent"]
