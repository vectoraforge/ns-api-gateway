"""The adapter seam: the one value type it declares, the one Protocol, and no provider SDK import."""
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

AUTH_PACKAGE = SOURCE_PATH.parent
# Every auth module that may never reach the provider SDK. `firebase` is excluded: it imports
# `firebase_admin` by design, and it is the only module that may.
SDK_FREE_MODULES = tuple(sorted({path.stem for path in AUTH_PACKAGE.glob("*.py")}
                                - {"__init__", "firebase"}))

PROTOCOLS = (FirebaseAdminAdapter,)
FROZEN = (VerifiedProviderIdentity,)

# Only the standard library and this project; a provider SDK or credential source here is the drift.
ALLOWED_IMPORT_ROOTS = {"dataclasses", "datetime", "enum", "typing", "uuid", "nativespeaker"}


def _classes() -> list[ast.ClassDef]:
    return [node for node in TREE.body if isinstance(node, ast.ClassDef)]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)


class TestTheOutcomeVocabularyLeftTheSeam:
    """The seam carries the success value only: no outcome enum, and exactly one value type."""

    def test_the_seam_declares_no_enum_at_all(self):
        from enum import Enum
        offenders = [name for name, value in vars(adapters_module).items()
                     if isinstance(value, type) and issubclass(value, Enum)
                     and value.__module__ == adapters_module.__name__]
        assert offenders == []

    def test_the_seam_declares_exactly_one_value_type(self):
        """One type crosses the seam on success, counted in the module rather than in this file."""
        declared = {node.name for node in _classes()} - {p.__name__ for p in PROTOCOLS}
        assert declared == {"VerifiedProviderIdentity"}


class TestNoProviderDependency:
    """No `firebase_admin` in `sys.modules` after importing any auth module but `firebase`.

    Package-wide is not assertable as one import: `auth/__init__.py` exposes nothing, so importing
    `adapters` loads no sibling and says nothing about them. The set is read off the directory
    instead, so a module added later is covered without editing this file."""

    @pytest.mark.parametrize("sdk_free_module", SDK_FREE_MODULES)
    def test_importing_the_module_does_not_import_firebase_admin(self, sdk_free_module):
        result = _run(f"import sys, nativespeaker.api.auth.{sdk_free_module}; "
                      "print('firebase_admin' in sys.modules)")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "False"

    def test_the_set_is_every_auth_module_but_the_one_excluded_by_design(self):
        """The control: a glob that matched nothing, or that quietly swept `firebase` in, would
        make the case above vacuous or permanently red."""
        on_disk = {path.stem for path in AUTH_PACKAGE.glob("*.py")} - {"__init__"}

        assert set(SDK_FREE_MODULES) == on_disk - {"firebase"}
        assert len(SDK_FREE_MODULES) > 1
        assert "adapters" in SDK_FREE_MODULES

    def test_the_excluded_module_is_the_one_that_really_holds_the_sdk(self):
        """The control: `firebase` is excluded because it imports the SDK legitimately. If that
        stopped being true the exclusion would be hiding a module this class should be walking."""
        result = _run("import sys, nativespeaker.api.auth.firebase; "
                      "print('firebase_admin' in sys.modules)")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "True"

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
    """Two methods, one issuer-selected client, and no fallback expressible."""

    def test_it_declares_exactly_the_two_surviving_methods(self):
        assert self._methods(FirebaseAdminAdapter) == {"get_user_provider_data",
                                                       "revoke_refresh_tokens"}

    @pytest.mark.parametrize("name", ("get_user_provider_data", "revoke_refresh_tokens"))
    def test_every_method_is_declared_async(self, name):
        """Every implementation is `async def`, so a synchronous declaration is one nothing satisfies."""
        assert inspect.iscoroutinefunction(getattr(FirebaseAdminAdapter, name))

    def test_get_user_provider_data_returns_the_verified_identity(self):
        """The seam's whole return surface: what the coroutine resolves to, or a raise."""
        assert self._returns(FirebaseAdminAdapter.get_user_provider_data) is VerifiedProviderIdentity

    def test_the_lookup_method_takes_the_issuer_so_selection_is_per_call(self):
        parameters = inspect.signature(FirebaseAdminAdapter.get_user_provider_data).parameters
        assert "issuer" in parameters

    def test_revoke_refresh_tokens_returns_nothing_at_all(self):
        """The revocation reports no value: the coroutine resolves to `None`, or it raises."""
        assert self._returns(FirebaseAdminAdapter.revoke_refresh_tokens) is None

    def test_the_revocation_method_takes_the_issuer_so_selection_is_per_call(self):
        parameters = inspect.signature(FirebaseAdminAdapter.revoke_refresh_tokens).parameters
        assert "issuer" in parameters

    @staticmethod
    def _methods(protocol) -> set[str]:
        return {name for name, value in vars(protocol).items()
                if callable(value) and not name.startswith("_")}

    @staticmethod
    def _returns(method):
        return inspect.signature(method).return_annotation
