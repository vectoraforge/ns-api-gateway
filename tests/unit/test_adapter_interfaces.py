"""The adapter seams: interfaces only, and this fails the moment `auth/adapters.py` grows an implementation."""
import ast
import subprocess
import sys
import typing
from dataclasses import FrozenInstanceError, is_dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import pytest

from nativespeaker.api.auth import adapters as adapters_module
from nativespeaker.api.auth.adapters import (
    ClaimKind,
    DeviceBitState,
    FirebaseAdminAdapter,
    ProviderDataEntry,
    ProviderDataOutcome,
    ProviderDataResult,
    RevocationOutcome,
    StoreAdapter,
    StoreState,
    VendorProofAdapter,
    VerifiedNotification,
    VerifiedTransaction,
)
from nativespeaker.api.auth.verification import VerifiedClaims

SOURCE_PATH = Path(adapters_module.__file__)
SOURCE = SOURCE_PATH.read_text()
TREE = ast.parse(SOURCE)

SRC_ROOT = SOURCE_PATH.parents[2]

PROTOCOLS = (FirebaseAdminAdapter, StoreAdapter, VendorProofAdapter)
ENUMS = (ProviderDataOutcome, RevocationOutcome, ClaimKind, DeviceBitState)
FROZEN = (ProviderDataEntry, ProviderDataResult, VerifiedNotification, VerifiedTransaction, StoreState)

# Every method across the three seams. Foundation names none of them outside adapters.py.
ADAPTER_METHODS = ("verify_id_token", "get_user_provider_data", "revoke_refresh_tokens",
                   "verify_provider_callback", "verify_store_artifact", "fetch_subscription_state",
                   "read_device_bit", "write_device_bit", "verify_integrity_verdict",
                   "verify_bot_check")

# Only the standard library and this project; a provider SDK or credential source here is the drift.
ALLOWED_IMPORT_ROOTS = {"dataclasses", "datetime", "enum", "typing", "uuid", "nativespeaker"}

# Modules permitted to name an adapter method, each mapped to the exact methods it may name.
ADAPTER_IMPLEMENTORS: dict[str, frozenset[str]] = {
    "api/auth/retry.py": frozenset({"get_user_provider_data"}),
    "api/auth/firebase.py": frozenset({"get_user_provider_data"}),
}


def _classes() -> list[ast.ClassDef]:
    return [node for node in TREE.body if isinstance(node, ast.ClassDef)]


def _is_stub_statement(stmt: ast.stmt) -> bool:
    """True for a docstring or a bare `...` -- the only two statements a declaration may hold."""
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)


def _adapter_method_offenders(sources, implementors=None) -> list[str]:
    """Sorted `path: method` strings for every adapter method named outside its permitted set."""
    permitted = ADAPTER_IMPLEMENTORS if implementors is None else implementors
    return sorted(f"{path}: {method}"
                  for path, text in sources
                  for method in ADAPTER_METHODS
                  if method in text and method not in permitted.get(path, frozenset()))


class TestClosedOutcomeSets:
    """The outcome sets are closed: a fifth member is a spec change, not a refactor."""

    def test_provider_data_outcome_has_exactly_the_four_71_members(self):
        assert [m.value for m in ProviderDataOutcome] == [
            "ok", "user_not_found", "retryable_failure", "selection_failure",
        ]

    def test_revocation_outcome_is_two_valued(self):
        """`confirmed` only when the provider confirmed; every other outcome is `unconfirmed`."""
        assert [m.value for m in RevocationOutcome] == ["confirmed", "unconfirmed"]

    def test_claim_kind_is_exactly_anonymous_and_registered(self):
        assert [m.value for m in ClaimKind] == ["anonymous", "registered"]

    def test_device_bit_state_has_exactly_three_members(self):
        assert [m.value for m in DeviceBitState] == ["set", "unset", "unavailable"]

    def test_every_enum_member_value_repeats_its_name(self):
        """The repo convention (models/chats.py) -- the wire value cannot drift from the member."""
        for enum in ENUMS:
            assert all(member.value == member.name for member in enum), enum.__name__


class TestZeroImplementations:
    """The seam declares. It never does."""

    def test_no_class_defines_a_method_body(self):
        offenders = [f"{cls.name}.{fn.name}"
                     for cls in _classes()
                     for fn in cls.body
                     if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and any(not _is_stub_statement(stmt) for stmt in fn.body)]
        assert offenders == []

    def test_the_module_declares_no_function_at_all(self):
        assert [node.name for node in TREE.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))] == []

    def test_no_class_subclasses_a_protocol_to_implement_it(self):
        for name, value in vars(adapters_module).items():
            if not isinstance(value, type) or value in PROTOCOLS:
                continue
            for protocol in PROTOCOLS:
                assert protocol not in value.__mro__, f"{name} implements {protocol.__name__}"

    @pytest.mark.parametrize("protocol", PROTOCOLS, ids=lambda p: p.__name__)
    def test_the_protocols_cannot_be_instantiated(self, protocol):
        with pytest.raises(TypeError):
            protocol()

    @pytest.mark.parametrize("protocol", PROTOCOLS, ids=lambda p: p.__name__)
    def test_no_protocol_is_runtime_checkable(self, protocol):
        """`isinstance` against these must stay a TypeError: a duck-typed pass proves nothing."""
        assert getattr(protocol, "_is_runtime_protocol", False) is False

    def test_foundation_calls_no_adapter_method_anywhere_in_src(self):
        """Foundation calls every adapter method zero times; the allow-list names the one module permitted one."""
        sources = [(path.relative_to(SRC_ROOT).as_posix(), path.read_text())
                   for path in sorted(SRC_ROOT.rglob("*.py")) if path != SOURCE_PATH]
        assert _adapter_method_offenders(sources) == []

    def test_every_allow_listed_path_resolves_to_a_file_that_exists(self):
        """A stale entry cannot silently widen the scan after a module is renamed or deleted."""
        assert ADAPTER_IMPLEMENTORS, "an empty allow-list would make the two controls vacuous"
        for relative in ADAPTER_IMPLEMENTORS:
            assert (SRC_ROOT / relative).is_file(), f"{relative} does not exist under {SRC_ROOT}"

    def test_a_non_exempt_file_naming_an_adapter_method_is_still_reported_control(self):
        """The positive control: the guarantee this file exists for still fires."""
        sources = [("api/app/main.py", "result = adapter.get_user_provider_data(issuer, subject)")]
        assert _adapter_method_offenders(sources) == ["api/app/main.py: get_user_provider_data"]

    def test_an_entry_permits_the_methods_it_names_and_no_others_control(self):
        """The entry-scope control: an exemption admits one method, not a module."""
        listed = next(iter(ADAPTER_IMPLEMENTORS))
        sources = [(listed, "outcome = adapter.revoke_refresh_tokens(issuer, subject)")]
        assert _adapter_method_offenders(sources) == [f"{listed}: revoke_refresh_tokens"]


class TestNoProviderDependency:
    """No `firebase_admin` in `sys.modules`, so a convenience import anywhere in the auth package fails this too."""

    def test_importing_the_module_does_not_import_firebase_admin(self):
        result = _run("import sys, nativespeaker.api.auth.adapters; "
                      "print('firebase_admin' in sys.modules)")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "False"

    def test_the_source_names_firebase_admin_nowhere_as_an_import(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("firebase_admin") for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("firebase_admin")

    def test_the_source_imports_only_the_stdlib_and_this_project(self):
        roots = set()
        for node in ast.walk(TREE):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            if isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        assert roots <= ALLOWED_IMPORT_ROOTS, f"unexpected imports: {sorted(roots - ALLOWED_IMPORT_ROOTS)}"


class TestImportIsSideEffectFree:
    """No I/O at import time, and nothing to make a concurrency claim about."""

    def test_the_module_body_holds_only_declarations(self):
        for node in TREE.body:
            assert isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef,
                                     ast.Assign, ast.AnnAssign)) or _is_stub_statement(node), \
                f"module-level {type(node).__name__} is not a declaration"

    def test_importing_twice_returns_the_same_module_object(self):
        import importlib
        assert (importlib.import_module("nativespeaker.api.auth.adapters")
                is importlib.import_module("nativespeaker.api.auth.adapters"))

    def test_reloading_produces_no_output_and_no_failure(self):
        result = _run("import importlib, nativespeaker.api.auth.adapters as a; "
                      "b = importlib.reload(a); print(True)")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "True"

    def test_no_module_level_mutable_state(self):
        mutable = {name for name, value in vars(adapters_module).items()
                   if not name.startswith("_") and isinstance(value, (dict, list, set))}
        assert mutable == set()


class TestResultTypesAreImmutable:
    """Every result type is a frozen dataclass or a StrEnum; none is mutable."""

    @pytest.mark.parametrize("result_type", FROZEN, ids=lambda t: t.__name__)
    def test_every_dataclass_is_frozen_and_slotted(self, result_type):
        assert is_dataclass(result_type)
        assert result_type.__dataclass_params__.frozen is True
        assert hasattr(result_type, "__slots__")

    def test_a_constructed_result_cannot_be_reassigned(self):
        result = ProviderDataResult(outcome=ProviderDataOutcome.user_not_found)
        with pytest.raises(FrozenInstanceError):
            result.outcome = ProviderDataOutcome.ok  # ty: ignore[invalid-assignment]

    def test_every_enum_is_a_strenum(self):
        for enum in ENUMS:
            assert issubclass(enum, StrEnum)

    def test_every_public_class_is_a_protocol_a_frozen_dataclass_or_a_strenum(self):
        declared = {node.name for node in _classes()}
        assert declared == {t.__name__ for t in PROTOCOLS + ENUMS + FROZEN}

    def test_provider_data_entries_default_to_an_empty_tuple(self):
        """A non-`ok` outcome carries no entries, and the empty default is immutable."""
        result = ProviderDataResult(outcome=ProviderDataOutcome.retryable_failure)
        assert result.entries == ()


class TestFirebaseAdminAdapter:
    """Three methods, one issuer-selected client, and no fallback expressible."""

    def test_it_declares_exactly_the_three_71_methods(self):
        assert self._methods(FirebaseAdminAdapter) == {
            "verify_id_token", "get_user_provider_data", "revoke_refresh_tokens",
        }

    def test_verify_id_token_returns_verified_claims(self):
        assert self._returns(FirebaseAdminAdapter.verify_id_token) is VerifiedClaims

    def test_get_user_provider_data_returns_a_provider_data_result(self):
        assert self._returns(FirebaseAdminAdapter.get_user_provider_data) is ProviderDataResult

    def test_revoke_refresh_tokens_returns_a_revocation_outcome(self):
        assert self._returns(FirebaseAdminAdapter.revoke_refresh_tokens) is RevocationOutcome

    def test_the_lookup_methods_take_the_issuer_so_selection_is_per_call(self):
        """No ambient, default, global or fallback client is expressible through the seam."""
        import inspect
        for method in (FirebaseAdminAdapter.get_user_provider_data,
                       FirebaseAdminAdapter.revoke_refresh_tokens):
            assert "issuer" in inspect.signature(method).parameters

    @staticmethod
    def _methods(protocol) -> set[str]:
        return {name for name, value in vars(protocol).items()
                if callable(value) and not name.startswith("_")}

    @staticmethod
    def _returns(method):
        import inspect
        return inspect.signature(method).return_annotation


class TestStoreAdapter:
    """Three methods, and a rejection that distinguishes nothing."""

    def test_it_declares_exactly_the_three_72_methods(self):
        assert TestFirebaseAdminAdapter._methods(StoreAdapter) == {
            "verify_provider_callback", "verify_store_artifact", "fetch_subscription_state",
        }

    @pytest.mark.parametrize("method_name,payload", [
        ("verify_provider_callback", VerifiedNotification),
        ("verify_store_artifact", VerifiedTransaction),
        ("fetch_subscription_state", StoreState),
    ])
    def test_every_rejection_is_the_same_indistinguishable_none(self, method_name, payload):
        """Rejection never distinguishes malformed from unverifiable material."""
        annotation = TestFirebaseAdminAdapter._returns(getattr(StoreAdapter, method_name))
        assert set(typing.get_args(annotation)) == {payload, type(None)}

    def test_verify_store_artifact_takes_the_submitted_artifact_not_a_resolved_pair(self):
        import inspect
        parameters = set(inspect.signature(StoreAdapter.verify_store_artifact).parameters)
        assert "artifact" in parameters
        assert "external_id" not in parameters

    def test_a_verified_transaction_carries_the_72_resolution(self):
        """The resolved pair, the transaction's stable identity, any purchase UUID, and context."""
        transaction = VerifiedTransaction(provider="apple",
                                          external_id="ext-1",
                                          transaction_identity="original-txn-1",
                                          purchase_uuid=uuid4(),
                                          app_id="com.example.app",
                                          product_id="sub.monthly",
                                          environment="Production")
        assert transaction.provider == "apple"
        assert transaction.external_id == "ext-1"

    def test_a_carried_purchase_uuid_is_optional(self):
        transaction = VerifiedTransaction(provider="google",
                                          external_id="ext-2",
                                          transaction_identity="token-2",
                                          purchase_uuid=None,
                                          app_id="com.example.app",
                                          product_id="sub.monthly",
                                          environment="Production")
        assert transaction.purchase_uuid is None


class TestVendorProofAdapter:
    """The adapter pins the device slot, and no value here becomes an identifier."""

    def test_it_declares_exactly_the_four_73_methods(self):
        assert TestFirebaseAdminAdapter._methods(VendorProofAdapter) == {
            "read_device_bit", "write_device_bit", "verify_integrity_verdict", "verify_bot_check",
        }

    @pytest.mark.parametrize("method_name", ["read_device_bit", "write_device_bit"])
    def test_every_device_slot_method_takes_a_claim_kind(self, method_name):
        """The adapter pins the bit, so one phase's flow cannot reach another's slot."""
        import inspect
        parameter = inspect.signature(getattr(VendorProofAdapter, method_name)).parameters["claim_kind"]
        assert parameter.annotation is ClaimKind

    def test_read_device_bit_returns_the_three_state_bit(self):
        assert TestFirebaseAdminAdapter._returns(VendorProofAdapter.read_device_bit) is DeviceBitState

    def test_no_non_slot_method_takes_a_claim_kind(self):
        """Only the two slot methods address a slot; widening that is an EoP surface."""
        import inspect
        for method_name in ("verify_integrity_verdict", "verify_bot_check"):
            method = getattr(VendorProofAdapter, method_name)
            assert "claim_kind" not in inspect.signature(method).parameters

    def test_the_seam_records_the_no_rate_limit_key_prohibition(self):
        """A docstring-level prohibition that no future implementer can miss."""
        assert "rate-limit key" in VendorProofAdapter.__doc__
        assert "device principal" in VendorProofAdapter.__doc__


class TestSharedAdapterRules:
    """The preamble binds every concrete adapter, and the seam is where those rules belong."""

    @pytest.mark.parametrize("phrase", [
        "no provider call while a database lock is held",
        "5-10 seconds",
        "never leak provider text to clients",
    ])
    def test_the_module_docstring_records_the_shared_rules(self, phrase):
        assert phrase in adapters_module.__doc__

    def test_the_coalescing_seam_is_recorded_as_a_later_phase_obligation(self):
        assert "coalesc" in StoreAdapter.__doc__.lower()
