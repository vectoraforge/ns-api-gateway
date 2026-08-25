"""The one stable import root for the auth subsystem (D-23).

Phases 36-46 import these names from `nativespeaker.api.auth` and nothing deeper, so the seam is
visibly one thing and a later internal split inside `auth/` costs no edit outside this file.
Everything a later phase is expected to name is re-exported here: the barrier and its §1.1 wire
contract, the §2.2 route registry with its §2.3 startup assertion, the §1.4 typed context, §1.3
identity resolution, §1.2 verification, §8.2 rejection logging, the §4.3/§6.4 shared keyed
hashing, the §6 challenge store and its §6.5 mode signal, the §7.1 Firebase
lookup retry policy, the §7 adapter interfaces, the concrete issuer-selected Firebase Admin
integration, §02's closed providerData classifier, and §02 step 10's email-copy predicate. Phases
40/41/42 reach all three of those last ones through this one root per D-23, rather than importing
`auth.firebase` or `auth.classifier` directly.

**The three `auth/firebase.py` names arrive lazily, and that is what makes D-23 affordable.** This
file imports every sibling eagerly, and Python imports a parent package before its submodule, so
`import nativespeaker.api.auth.adapters` executes *this* module first. An ordinary
`from nativespeaker.api.auth.firebase import ...` line here would therefore put the provider SDK
into `sys.modules` for every importer of the adapters seam -- and §7.1's no-provider-dependency
guarantee would become unmeasurable, because a probe of the seam would be measuring this file's
convenience imports instead
(`tests/unit/test_adapter_interfaces.py::TestNoProviderDependency`). A PEP 562 module-level
`__getattr__` resolves them on first access instead, so the SDK is imported when a caller actually
names one. `from nativespeaker.api.auth import build_admin_apps` still works and still returns the
same object as the direct import -- this is a re-export, not a copy.

**The error registry is deliberately absent.** `nativespeaker.api.errors` owns every client-visible
class in the service -- quota, LLM and framework classes as well as the seven foundation ones -- so
D-10 places it at package root rather than inside `auth/`. A reviewer looking for
`from nativespeaker.api.auth import ErrorResponse` should read D-10: importing `quota_exceeded`
from an auth package would misdescribe where that class comes from.

`__all__` comes first and is alphabetized, matching `models/__init__.py`; ruff's `I` rule enforces
the import ordering below it.
"""
__all__ = [
    "ACTOR_SUBJECT_PREFIX", "AdmissionDecision", "Admit", "AuthBarrierMiddleware",
    "BoundedReason", "CHALLENGE_ID_BYTES", "CHALLENGE_TTL_SECONDS", "Category", "ChallengeRejection",
    "ChallengeStore", "ClaimKind", "ClientIpBucketKind", "DeviceBitState",
    "FIREBASE_HTTP_TIMEOUT_SECONDS", "FIREBASE_LOOKUP_ATTEMPTS", "FirebaseAdminAdapter",
    "FirebaseAdminLookup", "HmacConfig", "HmacKeyring", "IDP_ACCOUNT_PREFIX", "IdentityKind",
    "JWTVerifier", "LinkedIdentity", "ModeSignal", "NamedVerifier", "PreAuthIdentity",
    "ProviderDataEntry", "ProviderDataOutcome", "ProviderDataResult", "REGISTRY",
    "REQUEST_CONTEXT_SCOPE_KEY", "Reject", "RequestContext", "RevocationOutcome", "RouteMetadata",
    "StoreAdapter", "StoreState", "TokenVerifier", "VERIFIERS", "VendorProofAdapter",
    "VerificationResult", "VerifiedClaims", "VerifiedNotification", "VerifiedTransaction",
    "assert_route_enumeration", "build_admin_apps", "classify_mode_signal",
    "classify_provider_data", "email_to_persist", "enumerate_registered", "extract_bearer", "lookup",
    "lookup_with_retry", "new_challenge_id", "record_rejection", "resolve_identity",
]

from importlib import import_module
from typing import TYPE_CHECKING

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
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.auth.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengeRejection,
    ChallengeStore,
    new_challenge_id,
)

# Eager, unlike the Firebase block below: `auth/classifier.py` imports `auth/adapters.py` and
# `models/identities.py` and drags in nothing new.
from nativespeaker.api.auth.classifier import classify_provider_data, email_to_persist
from nativespeaker.api.auth.context import (
    REQUEST_CONTEXT_SCOPE_KEY,
    ClientIpBucketKind,
    IdentityKind,
    LinkedIdentity,
    PreAuthIdentity,
    RequestContext,
)
from nativespeaker.api.auth.identity import AdmissionDecision, Admit, Reject, resolve_identity
from nativespeaker.api.auth.keys import (
    ACTOR_SUBJECT_PREFIX,
    IDP_ACCOUNT_PREFIX,
    HmacConfig,
    HmacKeyring,
)
from nativespeaker.api.auth.modesignal import ModeSignal, classify_mode_signal
from nativespeaker.api.auth.registry import (
    REGISTRY,
    VERIFIERS,
    Category,
    NamedVerifier,
    RouteMetadata,
    assert_route_enumeration,
    enumerate_registered,
    lookup,
)
from nativespeaker.api.auth.retry import (
    FIREBASE_LOOKUP_ATTEMPTS,
    lookup_with_retry,
)
from nativespeaker.api.auth.telemetry import record_rejection
from nativespeaker.api.auth.verification import (
    JWTVerifier,
    TokenVerifier,
    VerificationResult,
    VerifiedClaims,
)
from nativespeaker.api.auth.wire import BoundedReason, extract_bearer

if TYPE_CHECKING:
    # Static resolution for annotations only. These three are in `__all__`, so ruff reads them as
    # re-exports rather than unused imports, and no `firebase_admin` import happens at runtime.
    from nativespeaker.api.auth.firebase import (
        FIREBASE_HTTP_TIMEOUT_SECONDS,
        FirebaseAdminLookup,
        build_admin_apps,
    )

# The three names reached lazily, and the module each one comes from. See the module docstring:
# an ordinary import block here would import `firebase_admin` for every importer of any `auth`
# submodule, including the adapters seam whose freedom from the provider SDK is a Phase 35
# guarantee with a test behind it.
_LAZY_NAMES: dict[str, str] = {
    "FIREBASE_HTTP_TIMEOUT_SECONDS": "nativespeaker.api.auth.firebase",
    "FirebaseAdminLookup": "nativespeaker.api.auth.firebase",
    "build_admin_apps": "nativespeaker.api.auth.firebase",
}


def __getattr__(name: str) -> object:
    """PEP 562: resolve the lazy re-exports on first access, then cache them in `globals()`."""
    module_path = _LAZY_NAMES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_path), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Introspection still shows the whole root, lazy names included."""
    return sorted(__all__)
