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
from nativespeaker.api.app.errors import camel_to_snake
from nativespeaker.api.auth import exceptions as exceptions_module
from nativespeaker.api.auth.exceptions import AuthRejected
from nativespeaker.api.errors import IDENTITY_ALREADY_LINKED, INTERNAL_ERROR

FAMILY_MODULE = exceptions_module.__name__

# One entry per class in the family. Plans 02, 03 and 04 each append their own arms here.
EVENT_NAMES = frozenset({
    "identity_already_linked",
    "provider_account_already_linked",
    "account_unavailable",
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

    Reported all at once rather than one per run, the way `errors.py::assert_registry_total` reports
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
