"""FOUND-06: the §7.1 provider-call budget gate (D-06).

This is per-request provider-call metering, not traffic limiting. D-05 deleted §5 from the product
outright, so a test here that reached for an IP, user, or route key would be pinning machinery that
must not exist -- `TestNotTrafficLimiting` asserts its absence instead.

`NARROW` below is a test-local stand-in for the endpoint-layer budget names phases 37/40/41/42 add.
Foundation ships exactly one name, and `test_exactly_one_budget_name_ships` proves it.
"""
import inspect
from pathlib import Path

import pytest

from nativespeaker.api.auth import budgets as budgets_module
from nativespeaker.api.auth.budgets import (
    ADAPTER_FIREBASE_LOOKUP,
    FIREBASE_LOOKUP_ATTEMPTS,
    BudgetExhausted,
    BudgetGate,
)
from nativespeaker.api.errors import VERIFICATION_TEMPORARILY_UNAVAILABLE
from nativespeaker.api.models.auth import AuthEventResult

GLOBAL = ADAPTER_FIREBASE_LOOKUP
NARROW = "test_local_endpoint_entry"


class TestFirebaseLookupBudget:
    """§7.1: 3 attempts total -- the initial call plus up to two additional."""

    def test_the_shipped_attempt_count_is_three(self):
        assert FIREBASE_LOOKUP_ATTEMPTS == 3

    def test_three_attempts_are_permitted(self):
        gate = BudgetGate({GLOBAL: FIREBASE_LOOKUP_ATTEMPTS})
        for _ in range(FIREBASE_LOOKUP_ATTEMPTS):
            assert gate.check_all([GLOBAL]) is None
            gate.charge_all([GLOBAL])

    def test_the_fourth_attempt_is_exhausted(self):
        gate = BudgetGate({GLOBAL: FIREBASE_LOOKUP_ATTEMPTS})
        for _ in range(FIREBASE_LOOKUP_ATTEMPTS):
            gate.charge_all([GLOBAL])
        assert gate.check_all([GLOBAL]) == GLOBAL
        assert gate.remaining(GLOBAL) == 0

    def test_exactly_one_budget_name_ships(self):
        """Every endpoint-layer name belongs to a later phase; foundation invents none."""
        shipped = {name for name, value in vars(budgets_module).items()
                   if name.isupper() and not name.startswith("_") and isinstance(value, str)}
        assert shipped == {"ADAPTER_FIREBASE_LOOKUP"}

    def test_the_shipped_name_is_the_spec_string(self):
        assert ADAPTER_FIREBASE_LOOKUP == "adapter_firebase_lookup"


class TestCheckAllIsNonDestructive:
    """§7.1: all applicable budgets are checked non-destructively first."""

    def test_ten_checks_leave_remaining_unchanged(self):
        gate = BudgetGate({GLOBAL: 3})
        for _ in range(10):
            gate.check_all([GLOBAL])
        assert gate.remaining(GLOBAL) == 3

    def test_checking_an_exhausted_budget_does_not_move_its_counter(self):
        gate = BudgetGate({GLOBAL: 0})
        for _ in range(10):
            assert gate.check_all([GLOBAL]) == GLOBAL
        assert gate.remaining(GLOBAL) == 0

    def test_exhausted_is_non_destructive_too(self):
        gate = BudgetGate({GLOBAL: 2, NARROW: 1})
        for _ in range(10):
            gate.exhausted([GLOBAL, NARROW])
        assert (gate.remaining(GLOBAL), gate.remaining(NARROW)) == (2, 1)

    def test_remaining_is_non_destructive(self):
        gate = BudgetGate({GLOBAL: 3})
        for _ in range(10):
            gate.remaining(GLOBAL)
        assert gate.remaining(GLOBAL) == 3


class TestCheckAllOrdering:
    """§7.1: one deterministic order, broadest to narrowest; the global budget is primary."""

    def test_returns_none_when_every_named_budget_has_capacity(self):
        gate = BudgetGate({GLOBAL: 3, NARROW: 1})
        assert gate.check_all([GLOBAL, NARROW]) is None

    def test_returns_the_broadest_when_more_than_one_is_exhausted(self):
        gate = BudgetGate({GLOBAL: 0, NARROW: 0})
        assert gate.check_all([GLOBAL, NARROW]) == GLOBAL

    def test_returns_the_narrow_one_when_only_it_is_exhausted(self):
        gate = BudgetGate({GLOBAL: 3, NARROW: 0})
        assert gate.check_all([GLOBAL, NARROW]) == NARROW

    def test_the_first_exhausted_name_follows_the_given_order(self):
        """The order is the caller's, not the mapping's -- reversing the argument reverses the answer."""
        gate = BudgetGate({GLOBAL: 0, NARROW: 0})
        assert gate.check_all([NARROW, GLOBAL]) == NARROW


class TestExhausted:
    """§7.1: every exhausted limiter is recorded in metrics alongside the primary."""

    def test_returns_every_exhausted_name_not_just_the_first(self):
        gate = BudgetGate({GLOBAL: 0, NARROW: 0})
        assert gate.exhausted([GLOBAL, NARROW]) == [GLOBAL, NARROW]

    def test_preserves_the_given_order(self):
        gate = BudgetGate({GLOBAL: 0, NARROW: 0})
        assert gate.exhausted([NARROW, GLOBAL]) == [NARROW, GLOBAL]

    def test_omits_the_names_that_still_have_capacity(self):
        gate = BudgetGate({GLOBAL: 3, NARROW: 0})
        assert gate.exhausted([GLOBAL, NARROW]) == [NARROW]

    def test_returns_an_empty_list_when_all_have_capacity(self):
        gate = BudgetGate({GLOBAL: 3, NARROW: 1})
        assert gate.exhausted([GLOBAL, NARROW]) == []


class TestChargeAllIsAllOrNothing:
    """§7.1: no counter is incremented unless every applicable budget has capacity."""

    def test_charges_every_name_together(self):
        gate = BudgetGate({GLOBAL: 3, NARROW: 2})
        gate.charge_all([GLOBAL, NARROW])
        assert (gate.remaining(GLOBAL), gate.remaining(NARROW)) == (2, 1)

    def test_raises_rather_than_partially_charging(self):
        """The counter with capacity must not move when a sibling is exhausted."""
        gate = BudgetGate({GLOBAL: 3, NARROW: 0})
        with pytest.raises(BudgetExhausted):
            gate.charge_all([GLOBAL, NARROW])
        assert gate.remaining(GLOBAL) == 3
        assert gate.remaining(NARROW) == 0

    def test_raises_even_when_the_exhausted_name_is_charged_first(self):
        """Order must not create a partial-charge window: the narrow one is still untouched."""
        gate = BudgetGate({GLOBAL: 0, NARROW: 2})
        with pytest.raises(BudgetExhausted):
            gate.charge_all([GLOBAL, NARROW])
        assert gate.remaining(GLOBAL) == 0
        assert gate.remaining(NARROW) == 2

    def test_the_exception_names_the_primary_and_every_exhausted_limiter(self):
        gate = BudgetGate({GLOBAL: 0, NARROW: 0})
        with pytest.raises(BudgetExhausted) as excinfo:
            gate.charge_all([GLOBAL, NARROW])
        assert excinfo.value.primary == GLOBAL
        assert excinfo.value.exhausted == (GLOBAL, NARROW)

    def test_charging_after_check_all_returned_none_always_succeeds(self):
        gate = BudgetGate({GLOBAL: 2, NARROW: 2})
        while gate.check_all([GLOBAL, NARROW]) is None:
            gate.charge_all([GLOBAL, NARROW])
        assert (gate.remaining(GLOBAL), gate.remaining(NARROW)) == (0, 0)

    def test_once_charged_a_counter_stays_charged(self):
        """Budgets meter calls actually issued -- nothing refunds one, however the call resolved."""
        gate = BudgetGate({GLOBAL: 3})
        gate.charge_all([GLOBAL])
        assert gate.remaining(GLOBAL) == 2
        assert gate.check_all([GLOBAL]) is None
        assert gate.remaining(GLOBAL) == 2


class TestEmptySequences:
    """A call guarded by no budget is permitted and meters nothing."""

    def test_check_all_empty_returns_none(self):
        assert BudgetGate({}).check_all([]) is None

    def test_exhausted_empty_returns_an_empty_list(self):
        assert BudgetGate({}).exhausted([]) == []

    def test_charge_all_empty_charges_nothing(self):
        gate = BudgetGate({GLOBAL: 3})
        gate.charge_all([])
        assert gate.remaining(GLOBAL) == 3


class TestCounterFloor:
    """A remaining count never goes below zero and never wraps."""

    def test_remaining_never_returns_a_negative_value(self):
        gate = BudgetGate({GLOBAL: 1})
        gate.charge_all([GLOBAL])
        for _ in range(10):
            with pytest.raises(BudgetExhausted):
                gate.charge_all([GLOBAL])
            assert gate.remaining(GLOBAL) == 0
        assert gate.remaining(GLOBAL) >= 0

    def test_a_negative_limit_clamps_to_zero(self):
        gate = BudgetGate({GLOBAL: -5})
        assert gate.remaining(GLOBAL) == 0
        assert gate.check_all([GLOBAL]) == GLOBAL

    def test_a_float_limit_is_rejected(self):
        """There is no rounding path: a non-integer limit is unrepresentable, not truncated."""
        with pytest.raises(TypeError):
            BudgetGate({GLOBAL: 2.7})

    def test_counters_are_plain_ints(self):
        gate = BudgetGate({GLOBAL: 3})
        assert type(gate.remaining(GLOBAL)) is int


class TestUnnamedBudgetFailsClosed:
    """A name the gate was not constructed with has no capacity -- it is never unlimited."""

    def test_an_unnamed_budget_has_no_capacity(self):
        gate = BudgetGate({GLOBAL: 3})
        assert gate.remaining("never_declared") == 0
        assert gate.check_all(["never_declared"]) == "never_declared"

    def test_charging_an_unnamed_budget_raises_and_moves_nothing(self):
        gate = BudgetGate({GLOBAL: 3})
        with pytest.raises(BudgetExhausted):
            gate.charge_all([GLOBAL, "never_declared"])
        assert gate.remaining(GLOBAL) == 3


class TestDuplicateNames:
    """One budget named twice is one budget, so check and charge cannot disagree."""

    def test_a_name_repeated_in_one_sequence_charges_once(self):
        gate = BudgetGate({GLOBAL: 1})
        assert gate.check_all([GLOBAL, GLOBAL]) is None
        gate.charge_all([GLOBAL, GLOBAL])
        assert gate.remaining(GLOBAL) == 0

    def test_exhausted_reports_a_repeated_name_once(self):
        gate = BudgetGate({GLOBAL: 0})
        assert gate.exhausted([GLOBAL, GLOBAL]) == [GLOBAL]


class TestInstanceIsolation:
    """Per-request, in-process. No counter is shared across requests or processes."""

    def test_two_gates_share_no_state(self):
        first = BudgetGate({GLOBAL: 3})
        second = BudgetGate({GLOBAL: 3})
        first.charge_all([GLOBAL])
        assert first.remaining(GLOBAL) == 2
        assert second.remaining(GLOBAL) == 3

    def test_the_limits_mapping_is_copied_not_aliased(self):
        limits = {GLOBAL: 3}
        gate = BudgetGate(limits)
        limits[GLOBAL] = 99
        assert gate.remaining(GLOBAL) == 3

    def test_charging_does_not_mutate_the_callers_mapping(self):
        limits = {GLOBAL: 3}
        gate = BudgetGate(limits)
        gate.charge_all([GLOBAL])
        assert limits == {GLOBAL: 3}


class TestNotTrafficLimiting:
    """D-05: Envoy Gateway is the sole request-rate enforcement point.

    These assertions fail the moment this module grows into the backend limiter §5 described and
    D-05 deleted.
    """

    def test_module_imports_no_rate_limiting_dependency(self):
        source = Path(budgets_module.__file__).read_text()
        for forbidden in ("import limits", "from limits", "import redis", "from redis",
                          "import valkey", "from valkey"):
            assert forbidden not in source, f"{forbidden!r} appears in budgets.py"

    def test_module_declares_no_module_level_mutable_state(self):
        mutable = {name for name, value in vars(budgets_module).items()
                   if not name.startswith("_") and isinstance(value, (dict, list, set))}
        assert mutable == set()

    def test_no_method_takes_an_ip_user_route_or_request_key(self):
        parameters = set()
        for name, member in vars(BudgetGate).items():
            if name.startswith("_") and name != "__init__":
                continue
            if callable(member):
                parameters |= set(inspect.signature(member).parameters)
        assert parameters == {"self", "limits", "names", "name"}


class TestExhaustionMapping:
    """§7.1: exhaustion maps to internal `firebase_lookup_unavailable` -> client 503.

    The mapping travels as data on the exception so the call site (phases 37/40/41/42) cannot get
    it wrong -- and must still act on it, writing the audit row this module never writes.
    """

    def test_budget_exhausted_carries_the_internal_audit_result(self):
        assert BudgetExhausted.audit_result is AuthEventResult.firebase_lookup_unavailable

    def test_budget_exhausted_carries_the_client_error_class(self):
        assert BudgetExhausted.error_class is VERIFICATION_TEMPORARILY_UNAVAILABLE
        assert BudgetExhausted.error_class.code == "verification_temporarily_unavailable"
        assert BudgetExhausted.error_class.status == 503

    def test_budget_exhausted_is_not_a_service_error(self):
        """It must not auto-convert to a 503: an unhandled one would skip the audit row."""
        from nativespeaker.api.errors import ServiceError
        assert not issubclass(BudgetExhausted, ServiceError)
