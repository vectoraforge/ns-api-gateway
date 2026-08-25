"""The stable import root for the auth subsystem: later phases import these names from here, not deeper."""
__all__ = [
    "ACTOR_SUBJECT_PREFIX", "AdmissionDecision", "Admit",
    "BoundedReason", "CHALLENGE_ID_BYTES", "CHALLENGE_TTL_SECONDS", "ChallengeRejection",
    "ChallengeStore", "ClaimKind", "DeviceBitState",
    "FIREBASE_HTTP_TIMEOUT_SECONDS", "FIREBASE_LOOKUP_ATTEMPTS", "FirebaseAdminAdapter",
    "FirebaseAdminLookup", "HmacConfig", "HmacKeyring", "IDP_ACCOUNT_PREFIX", "IdentityKind",
    "JWTVerifier", "LinkedIdentity", "ModeSignal", "PreAuthIdentity",
    "ProviderDataEntry", "ProviderDataOutcome", "ProviderDataResult",
    "Reject", "RequestContext", "RevocationOutcome",
    "StoreAdapter", "StoreState", "TokenVerifier", "VendorProofAdapter",
    "VerificationResult", "VerifiedClaims", "VerifiedNotification", "VerifiedTransaction",
    "build_admin_apps", "classify_mode_signal",
    "classify_provider_data", "email_to_persist", "extract_bearer",
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
from nativespeaker.api.auth.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengeRejection,
    ChallengeStore,
    new_challenge_id,
)
from nativespeaker.api.auth.classifier import classify_provider_data, email_to_persist
from nativespeaker.api.auth.context import (
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
    # Annotations only: these three are in `__all__`, so ruff reads them as re-exports.
    from nativespeaker.api.auth.firebase import (
        FIREBASE_HTTP_TIMEOUT_SECONDS,
        FirebaseAdminLookup,
        build_admin_apps,
    )

# Lazy: an ordinary import here would pull firebase_admin into every importer of the adapters seam.
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
