"""The tree's log vocabulary, written down as a literal rather than derived from the classes.

A class name *is* its structured log event name (D-02), so a rename re-keys every grep that reads it.
"""
from uuid import uuid7

import pytest

from nativespeaker.api import errors as errors_module
from nativespeaker.api.app.error_handlers import camel_to_snake
from nativespeaker.api.auth.jwt_verifier import BoundedReason
from nativespeaker.api.errors import (
    AppError,
    ChallengeConsumed,
    ChallengeExpired,
    ChallengeIdentityMismatch,
    ChallengeNotFound,
    ChallengeOperationMismatch,
    ChallengeRejected,
    NotLinked,
    Unavailable,
    UserNotFound,
    _family,
)
from nativespeaker.api.tables.purchases import PurchaseProvider
from unit.error_tree import undeclared

# The five leaves under one 409 base, listed rather than derived, so a change here is a visible edit.
CHALLENGE_ARMS = (ChallengeNotFound, ChallengeExpired, ChallengeConsumed,
                  ChallengeIdentityMismatch, ChallengeOperationMismatch)

FAMILY_MODULE = errors_module.__name__

# One entry per class in the tree.
EVENT_NAMES = frozenset({
    # The generic answer for each bare framework status.
    "invalid_request",
    "auth_required",
    "not_found",
    "method_not_allowed",
    "challenge_required",
    "validation_error",
    "rate_limited",
    "internal_error",
    "service_unavailable",
    # The service arms.
    "unsupported_language_error",
    "chat_history_limit_error",
    "out_of_scope_error",
    "invalid_chat_error",
    "quota_exceeded_error",
    "analysis_error",
    "transient_llm_error",
    "permanent_llm_error",
    "missing_usage_row_error",
    "multiple_effective_grants_error",
    "unknown_tier_error",
    "missing_purchase_token_error",
    "queue_full_error",
    "circuit_open_error",
    # The admission arms.
    "invalid_external_jwt",
    # `pre_auth_...` here and `preauth_...` on the wire: the event is whatever the class name spells.
    "pre_auth_identity_not_allowed",
    "identity_unresolvable",
    # D-05's shared base and its two leaves, told apart in the log and nowhere else.
    "account_unavailable",
    "historical_identity",
    "blocked_user",
    # The creation arms.
    "identity_already_linked",
    # The lookup arms, group base included: the walk finds it, even though nothing raises it.
    "provider_lookup_error",
    "user_not_found",
    "unavailable",
    "not_linked",
    # The challenge arms, on the same terms.
    "challenge_rejected",
    "challenge_not_found",
    "challenge_expired",
    "challenge_consumed",
    "challenge_identity_mismatch",
    "challenge_operation_mismatch",
})


def _production_family() -> list[type[AppError]]:
    """The tree as A-01 places it: one module. A synthetic subclass built by a control cannot join."""
    return [cls for cls in _family(AppError) if cls.__module__ == FAMILY_MODULE]


class TestTheEventVocabularyIsWrittenDown:
    """The class names are the log vocabulary, so the set of them is the contract."""

    def test_the_tree_spells_exactly_the_recorded_event_names(self):
        derived = {camel_to_snake(cls.__name__) for cls in _production_family()}
        assert derived == EVENT_NAMES

    def test_every_class_lives_in_the_one_module_the_tree_was_given(self):
        """A-01 names one path; a second home would mean two vocabularies and one of them unwatched."""
        assert FAMILY_MODULE == "nativespeaker.api.errors"
        assert _production_family(), "the walk found no subclasses at all"


# The arguments each class's own `__init__` insists on.
CONSTRUCTOR_ARGUMENTS: dict[type, tuple[tuple, dict]] = {
    errors_module.UnsupportedLanguageError: (("fr", ["en"]), {}),
    errors_module.ChatHistoryLimitError: ((), {"max_messages": 50}),
    errors_module.InvalidChatError: (("chat-id",), {}),
    errors_module.MissingUsageRowError: ((uuid7(),), {}),
    errors_module.MultipleEffectiveGrantsError: ((2, uuid7()), {}),
    errors_module.UnknownTierError: (("registered", uuid7()), {}),
    errors_module.MissingPurchaseTokenError: ((uuid7(), [PurchaseProvider.apple]), {}),
    errors_module.QueueFullError: ((30,), {}),
    errors_module.CircuitOpenError: ((60,), {}),
    errors_module.InvalidExternalJwt: ((), {"bounded_reason": BoundedReason.expired}),
    errors_module.ProviderLookupError: ((), {"stage": "provider_lookup", "cause": "bounded"}),
    errors_module.UserNotFound: ((), {"stage": "provider_lookup"}),
    errors_module.Unavailable: ((), {"stage": "issuer_selection"}),
    errors_module.NotLinked: ((), {"stage": "provider_classification", "cause": "invalid-shape"}),
}


def _sample(cls: type[AppError]) -> AppError:
    """One live instance of `cls`, so the assertion runs against a real `log_fields()` call."""
    args, kwargs = CONSTRUCTOR_ARGUMENTS.get(cls, ((), {}))
    return cls(*args, **kwargs)


class TestEveryLeafKeepsItsLogFieldsToPlainScalars:
    """An ORM row here is the expired-attribute 500 the scalars-only rule exists to prevent."""

    def test_the_coverage_is_the_whole_tree_and_not_a_subset(self):
        """The coverage is the whole tree, not the subset an earlier file settled for."""
        assert len(_production_family()) > 8

    def test_the_constructor_table_names_only_classes_that_are_in_the_tree(self):
        """The control: a stale entry here would let a real class fall back to a no-arg build."""
        assert set(CONSTRUCTOR_ARGUMENTS) <= set(_production_family())

    @pytest.mark.parametrize("cls", _production_family(), ids=lambda c: c.__name__)
    def test_every_class_in_the_tree_contributes_only_scalars(self, cls):
        for key, value in _sample(cls).log_fields().items():
            assert isinstance(value, str | None), f"{cls.__name__}.{key} is not a scalar"


class TestTheLookupArmsCarryStageAndOnlyABoundedCause:
    """`stage` always, `cause` only when there is one, and nothing else reaches a log line."""

    @pytest.mark.parametrize("rejection,status", [
        (UserNotFound(stage="provider_lookup"), 401),
        (Unavailable(stage="provider_lookup"), 503),
        (NotLinked(stage="provider_classification", cause="invalid-shape"), 403),
    ], ids=["user_not_found", "unavailable", "not_linked"])
    def test_each_arm_answers_the_status_the_returned_outcome_earned(self, rejection, status):
        assert rejection.status == status

    def test_an_arm_with_no_cause_emits_no_cause_key_at_all(self):
        """Not `{"cause": None}`: with no cause the key is absent, not present and empty."""
        assert UserNotFound(stage="provider_lookup").log_fields() == {"stage": "provider_lookup"}
        assert Unavailable(stage="issuer_selection").log_fields() == {"stage": "issuer_selection"}

    def test_the_classification_arm_emits_both_keys(self):
        assert NotLinked(stage="provider_classification", cause="invalid-shape").log_fields() == {
            "stage": "provider_classification", "cause": "invalid-shape",
        }


class TestTheChallengeArmsAnswerOneThingAndDeclareNothing:
    """D-14's anti-oracle property, held as structure rather than as five equal answers.

    The 409 is declared once on `ChallengeRejected`, so making one arm differ takes a visible override.
    """

    def test_the_five_are_exactly_the_leaves_under_the_shared_base(self):
        """A sixth arm added without coming here would be a rejection nobody checked the answer of."""
        assert set(_family(ChallengeRejected)) == set(CHALLENGE_ARMS)

    @pytest.mark.parametrize("arm", CHALLENGE_ARMS, ids=lambda c: c.__name__)
    def test_no_arm_declares_a_status_or_a_code_of_its_own(self, arm):
        """Deliberately unlike `AnalysisError`/`TransientLLMError`, which re-declares on the child."""
        assert "status" not in vars(arm)
        assert "code" not in vars(arm)

    @pytest.mark.parametrize("arm", CHALLENGE_ARMS, ids=lambda c: c.__name__)
    def test_every_arm_answers_the_one_challenge_required_class(self, arm):
        assert (arm.status, arm.code) == (409, "challenge_required")

    @pytest.mark.parametrize("arm", CHALLENGE_ARMS, ids=lambda c: c.__name__)
    def test_no_arm_can_carry_anything_into_its_log_line(self, arm):
        """No `__init__` and no fields, so the secret handle cannot be passed to one of these."""
        assert "__init__" not in vars(arm)
        assert arm().log_fields() == {}

    def test_the_five_are_still_five_distinct_log_events(self):
        """One answer to the client and five records in the log is the whole point of the shape."""
        events = [camel_to_snake(arm.__name__) for arm in CHALLENGE_ARMS]
        assert sorted(events) == sorted(set(events))
        assert set(events) == {"challenge_not_found", "challenge_expired", "challenge_consumed",
                               "challenge_identity_mismatch", "challenge_operation_mismatch"}


class TestTheTwoAccountArmsDeclareNothingEither:
    """D-05 copies D-14's shape: one answer on the base, two leaves that only name themselves."""

    @pytest.mark.parametrize("arm", (errors_module.HistoricalIdentity, errors_module.BlockedUser),
                             ids=lambda c: c.__name__)
    def test_no_arm_declares_a_status_or_a_code_of_its_own(self, arm):
        assert "status" not in vars(arm)
        assert "code" not in vars(arm)
        assert (arm.status, arm.code) == (403, "account_unavailable")

    def test_the_two_are_exactly_the_leaves_under_the_shared_base(self):
        assert set(_family(errors_module.AccountUnavailable)) == {errors_module.HistoricalIdentity,
                                                                  errors_module.BlockedUser}


class TestNoLeafSilentlyAnswersTheFailClosedDefault:
    """The base's 500 is a tripwire, not a default anybody is allowed to rely on."""

    def test_every_leaf_declares_its_answer_or_inherits_one_below_the_base(self):
        problems = undeclared(_production_family(), root=AppError)
        if problems:
            raise AssertionError("the error tree has undeclared leaves:\n  " + "\n  ".join(problems))


class TestTheMeasurementFires:
    """The controls: a walk that quietly returned nothing would pass every case above."""

    def test_a_leaf_declaring_nothing_is_reported_and_a_declaring_sibling_is_not(self):
        class _SyntheticBase(Exception):
            code = "internal_error"

        class _Intermediate(_SyntheticBase):
            pass

        class _SilentLeaf(_Intermediate):
            pass

        class _DeclaringLeaf(_SyntheticBase):
            code = "identity_already_linked"

        problems = undeclared(_family(_SyntheticBase), root=_SyntheticBase)

        assert len(problems) == 1
        assert problems[0].startswith("_SilentLeaf ")
        # The intermediate is skipped because it has a leaf, and the declaring sibling is fine.
        assert "_Intermediate" not in problems[0]
        assert "_DeclaringLeaf" not in problems[0]

    def test_a_leaf_that_inherits_from_a_declaring_intermediate_is_accepted(self):
        """D-14's shape: five leaves sharing one 409 base. None of them declares, and none is a defect."""
        class _SyntheticBase(Exception):
            code = "internal_error"

        class _DeclaringIntermediate(_SyntheticBase):
            code = "identity_already_linked"

        class _Leaf(_DeclaringIntermediate):
            pass

        assert undeclared(_family(_SyntheticBase), root=_SyntheticBase) == []

    def test_every_defect_is_reported_in_one_message(self):
        class _SyntheticBase(Exception):
            code = "internal_error"

        class _FirstSilent(_SyntheticBase):
            pass

        class _SecondSilent(_SyntheticBase):
            pass

        problems = undeclared(_family(_SyntheticBase), root=_SyntheticBase)
        assert sorted(problem.split()[0] for problem in problems) == ["_FirstSilent",
                                                                     "_SecondSilent"]
