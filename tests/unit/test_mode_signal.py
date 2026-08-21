"""FOUND-07 / §6.5: the shared syntactic mode-signal partition.

Two signals decide which mode a challenge-bearing endpoint is in -- `challenge=true` in the query
string, and a `challenge_id` in the body. Exactly one of them must be present. Both together and
neither at all are the same `invalid_request`, and prepare is never *inferred* from a missing
challenge.

The check is syntactic and has no side effects, which is why every case here is a pure call. It
issues nothing, looks nothing up, consumes nothing, and changes no state -- a corrected retry may
reuse the same unexpired challenge, and it can only do so because this check never touched the row.
It belongs to the admission phase, has no internal `core.auth_event_result`, and writes no audit
row (§4.1): a rejection here is recorded in the structured security log and the counter metric
alone.

The query string arrives as the raw ASGI `scope["query_string"]` bytes, the same way `auth/wire.py`
takes the raw header list, and for the same reason: a first-value-wins accessor silently folds the
duplicate this contract exists to reject.
"""

import ast
import inspect
from pathlib import Path

import pytest

from nativespeaker.api.auth.modesignal import ModeSignal, classify_mode_signal

HANDLE = "AbCdEfGhIjKlMnOpQrStUv"


def module_ast() -> ast.Module:
    return ast.parse(Path(inspect.getfile(ModeSignal)).read_text())


class TestThePartition:
    """§6.5's two accepted shapes."""

    def test_challenge_true_alone_is_prepare(self):
        assert classify_mode_signal(b"challenge=true", None) is ModeSignal.prepare

    def test_a_body_handle_alone_is_completion(self):
        assert classify_mode_signal(b"", HANDLE) is ModeSignal.completion

    def test_challenge_true_survives_other_query_parameters(self):
        """Only the `challenge` parameter is this check's business; an endpoint's own parameters
        are not evidence either way."""
        assert classify_mode_signal(b"lang=en&challenge=true&x=1", None) is ModeSignal.prepare

    def test_a_body_handle_survives_other_query_parameters(self):
        assert classify_mode_signal(b"lang=en", HANDLE) is ModeSignal.completion


class TestTheAmbiguityRejections:
    """`None` means `invalid_request`. Six shapes, none of which is resolved by preferring one
    signal over the other."""

    def test_both_signals_present_is_invalid(self):
        """One signal is never silently preferred over the other. A client that sent both does not
        know which mode it is in, and guessing for it is how a prepare consumes a challenge."""
        assert classify_mode_signal(b"challenge=true", HANDLE) is None

    def test_neither_signal_present_is_invalid(self):
        """Prepare is never *inferred* from a missing challenge (§6.5)."""
        assert classify_mode_signal(b"", None) is None

    @pytest.mark.parametrize("raw_query", [
        b"challenge=True", b"challenge=TRUE", b"challenge=1", b"challenge=yes", b"challenge=",
        b"challenge", b"challenge=true%20", b"challenge=+true", b"challenge=truex",
    ])
    def test_any_value_other_than_exactly_true_is_invalid(self, raw_query):
        """`challenge=True` is the one worth naming: a `bool()`-style coercion accepts it, and the
        spec says *exactly* `true`."""
        assert classify_mode_signal(raw_query, None) is None

    @pytest.mark.parametrize("raw_query", [
        b"challenge=true&challenge=true", b"challenge=true&challenge=false",
        b"challenge=false&challenge=true", b"x=1&challenge=true&y=2&challenge=true",
    ])
    def test_a_duplicated_challenge_parameter_is_invalid(self, raw_query):
        """Its own `invalid_request` case, and the reason this reads the raw query rather than a
        first-value-wins accessor: `.get()` folds every one of these into a single `true`.

        Both-values-`true` is the case that matters. A duplicate-detector that only noticed
        *disagreeing* values would pass the first row and fail this one.
        """
        assert classify_mode_signal(raw_query, None) is None

    @pytest.mark.parametrize("body", ["", "   ", "\t", "\n"])
    def test_an_empty_or_whitespace_only_body_handle_is_invalid(self, body):
        assert classify_mode_signal(b"", body) is None

    @pytest.mark.parametrize("body", [123, 0, 1, True, False, [], {}, ["x"], {"challenge_id": "x"},
                                      b"AbCdEfGhIjKlMnOpQrStUv", 1.5, object()])
    def test_a_wrongly_typed_body_handle_is_invalid(self, body):
        """`True` and `1` are the ones a truthiness check would wave through, and `b"..."` is the
        one an `isinstance(x, (str, bytes))` would."""
        assert classify_mode_signal(b"", body) is None

    @pytest.mark.parametrize("body", ["", "   ", 123, True, [], b"x"])
    def test_an_invalid_body_handle_is_invalid_even_beside_challenge_true(self, body):
        """A present-but-unusable handle is itself `invalid_request` (§6.5), so it cannot be read
        as "no body handle" and quietly promoted to prepare. `None` is the absent case."""
        assert classify_mode_signal(b"challenge=true", body) is None


class TestTheHandleIsPassedThroughUntouched:
    """The check decides *whether* a handle is present; it never normalizes one."""

    @pytest.mark.parametrize("body", [" " + HANDLE, HANDLE + " ", HANDLE.lower(), HANDLE + "=="])
    def test_a_non_empty_handle_is_completion_however_odd_it_looks(self, body):
        """A handle with stray whitespace or the wrong case is completion mode with a handle that
        will not locate a row -- `challenge_not_found`, not `invalid_request`. Trimming here would
        turn a byte-for-byte lookup (§6.1) into a fuzzy one from two modules away."""
        assert classify_mode_signal(b"", body) is ModeSignal.completion

    def test_the_check_does_not_trim_the_value_it_was_given(self):
        """The emptiness test uses `.strip()`; the value itself must not be. Asserted on the AST,
        because this function returns a mode rather than a handle -- there is no output in which a
        trimmed value would be visible, and the damage would land in the caller's `locate`."""
        tree = module_ast()
        returns_a_stripped_value = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "strip"
        ]
        assert returns_a_stripped_value == []


class TestTheCheckHasNoSideEffects:
    """§6.5: it issues nothing, looks up nothing, consumes nothing, and changes no state."""

    def test_the_module_imports_no_session_model_or_database_symbol(self):
        """The structural half of "no side effects": there is nothing here to have one *with*."""
        tree = module_ast()
        imported = {alias.name for node in ast.walk(tree)
                    if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        for forbidden in ("sqlmodel", "sqlalchemy", "asyncpg", "nativespeaker.api.models",
                          "nativespeaker.api.auth.challenges", "nativespeaker.api.database"):
            assert not any(name.startswith(forbidden) for name in imported), imported

    def test_the_function_is_not_a_coroutine(self):
        """Nothing to await means nothing to await *on* -- no lookup, no issue, no consume."""
        assert not inspect.iscoroutinefunction(classify_mode_signal)

    def test_repeated_calls_are_identical(self):
        """A check that consumed or issued anything would answer differently the second time."""
        assert [classify_mode_signal(b"", HANDLE) for _ in range(5)] == [ModeSignal.completion] * 5
        assert [classify_mode_signal(b"challenge=true", None) for _ in range(5)] == [
            ModeSignal.prepare] * 5

    def test_the_module_defines_only_the_partition(self):
        """Foundation ships the shared check and nothing more (§6.5). Mode-signal *dispatch*,
        provider normalization, proof verification and the consuming-transaction body belong to the
        endpoint phases; growing any of them here would put five phases' logic in one module."""
        tree = module_ast()
        top_level = {node.name for node in tree.body
                     if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)}
        assert top_level == {"ModeSignal", "classify_mode_signal"}

    def test_the_partition_has_exactly_two_members(self):
        assert [member.value for member in ModeSignal] == ["prepare", "completion"]
