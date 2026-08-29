"""The adapter seam: an interface only, and this fails the moment `auth/adapters.py` grows an implementation."""
import ast
import inspect
import subprocess
import sys
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest

from nativespeaker.api.auth import adapters as adapters_module
from nativespeaker.api.auth.adapters import FirebaseAdminAdapter, VerifiedProviderIdentity
from nativespeaker.api.tables.identities import IdentityProvider

SOURCE_PATH = Path(adapters_module.__file__)
SOURCE = SOURCE_PATH.read_text()
TREE = ast.parse(SOURCE)

SRC_ROOT = SOURCE_PATH.parents[2]

PROTOCOLS = (FirebaseAdminAdapter,)
FROZEN = (VerifiedProviderIdentity,)

# Every method on the seam. Foundation names it only where the allow-list below permits it.
ADAPTER_METHODS = ("get_user_provider_data",)

# Only the standard library and this project; a provider SDK or credential source here is the drift.
ALLOWED_IMPORT_ROOTS = {"dataclasses", "datetime", "enum", "typing", "uuid", "nativespeaker"}

# Modules permitted to name an adapter method, each mapped to the exact methods it may name.
ADAPTER_IMPLEMENTORS: dict[str, frozenset[str]] = {
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


class TestTheOutcomeVocabularyLeftTheSeam:
    """The seam carries the success value only; every failure is a raised member of the rejection family.

    This replaces a closed four-member `ProviderDataOutcome` and the two result types that wrapped
    it. The closure property did not evaporate -- it moved to `test_rejection_vocabulary.py`, where
    the same "a fifth member is a spec change" rule is enforced over the exception family. What
    belongs *here* is the narrower claim that the seam declares no outcome vocabulary of its own,
    because a second one would put failure classification back on the value path D-09 removed it
    from.
    """

    def test_the_seam_declares_no_enum_at_all(self):
        from enum import Enum
        offenders = [name for name, value in vars(adapters_module).items()
                     if isinstance(value, type) and issubclass(value, Enum)
                     and value.__module__ == adapters_module.__name__]
        assert offenders == []

    def test_the_seam_declares_exactly_one_value_type(self):
        """One type crosses the seam on success. A second would be an outcome discriminator again."""
        assert [t.__name__ for t in FROZEN] == ["VerifiedProviderIdentity"]


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
        """Foundation calls the adapter method zero times; the allow-list names the modules permitted one."""
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
        """The entry-scope control: an exemption admits a named method, not the module holding it."""
        listed = next(iter(ADAPTER_IMPLEMENTORS))
        sources = [(listed, "result = adapter.get_user_provider_data(issuer, subject)")]
        assert _adapter_method_offenders(sources, {listed: frozenset()}) == [
            f"{listed}: get_user_provider_data",
        ]


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


class TestTheValueTypeIsImmutable:
    """The one type that crosses the seam is a frozen, slotted dataclass and nothing else."""

    @pytest.mark.parametrize("value_type", FROZEN, ids=lambda t: t.__name__)
    def test_every_dataclass_is_frozen_and_slotted(self, value_type):
        assert is_dataclass(value_type)
        assert value_type.__dataclass_params__.frozen is True
        assert hasattr(value_type, "__slots__")

    def test_a_constructed_identity_cannot_be_reassigned(self):
        identity = VerifiedProviderIdentity(provider=IdentityProvider.google,
                                            provider_uid="google-uid-1")
        with pytest.raises(FrozenInstanceError):
            identity.provider_uid = "somebody-elses-uid"  # ty: ignore[invalid-assignment]

    def test_a_constructed_identity_carries_no_instance_dict(self):
        """Slotted, so a field this type never declared cannot be smuggled onto an instance."""
        identity = VerifiedProviderIdentity(provider=IdentityProvider.anonymous, provider_uid=None)
        assert not hasattr(identity, "__dict__")
        with pytest.raises(AttributeError):
            identity.email_verified = True  # ty: ignore[unresolved-attribute]

    def test_every_public_class_is_a_protocol_or_a_frozen_dataclass(self):
        declared = {node.name for node in _classes()}
        assert declared == {t.__name__ for t in PROTOCOLS + FROZEN}

    def test_the_email_defaults_to_none(self):
        """An anonymous record has no verified address, so the field it would ride on defaults absent."""
        identity = VerifiedProviderIdentity(provider=IdentityProvider.anonymous, provider_uid=None)
        assert identity.email is None


class TestFirebaseAdminAdapter:
    """One method, one issuer-selected client, and no fallback expressible."""

    def test_it_declares_exactly_the_one_surviving_method(self):
        assert self._methods(FirebaseAdminAdapter) == {"get_user_provider_data"}

    def test_get_user_provider_data_returns_the_verified_identity(self):
        """The seam's whole return surface: the verified identity, or a raise. No result wrapper."""
        assert self._returns(FirebaseAdminAdapter.get_user_provider_data) is VerifiedProviderIdentity

    def test_the_lookup_method_takes_the_issuer_so_selection_is_per_call(self):
        """No ambient, default, global or fallback client is expressible through the seam."""
        parameters = inspect.signature(FirebaseAdminAdapter.get_user_provider_data).parameters
        assert "issuer" in parameters

    @staticmethod
    def _methods(protocol) -> set[str]:
        return {name for name, value in vars(protocol).items()
                if callable(value) and not name.startswith("_")}

    @staticmethod
    def _returns(method):
        return inspect.signature(method).return_annotation


class TestSharedAdapterRules:
    """The preamble binds the concrete adapter, and the seam is where those rules belong."""

    @pytest.mark.parametrize("phrase", [
        "no provider call while a crud lock is held",
        "5-10 seconds",
        "never leak provider text to clients",
    ])
    def test_the_module_docstring_records_the_shared_rules(self, phrase):
        assert phrase in adapters_module.__doc__
