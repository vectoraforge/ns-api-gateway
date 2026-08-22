"""The one stable import root for the auth subsystem (D-23).

Phases 36-46 import these names from `nativespeaker.api.auth` and nothing deeper, so the seam is
visibly one thing and a later internal split inside `auth/` costs no edit outside this file.
Everything a later phase is expected to name is re-exported here: the barrier and its §1.1 wire
contract, the §2.2 route registry with its §2.3 startup assertion, the §1.4 typed context, §1.3
identity resolution, §1.2 verification, §8.2 rejection logging, the §4.3/§6.4 shared keyed
hashing, the §4 audit writer, the §6 challenge store and its §6.5 mode signal, the §7.1 provider
call budget, and the §7 adapter interfaces.

**The error registry is deliberately absent.** `nativespeaker.api.errors` owns every client-visible
class in the service -- quota, LLM and framework classes as well as the seven foundation ones -- so
D-10 places it at package root rather than inside `auth/`. A reviewer looking for
`from nativespeaker.api.auth import ErrorResponse` should read D-10: importing `quota_exceeded`
from an auth package would misdescribe where that class comes from.

`__all__` comes first and is alphabetized, matching `models/__init__.py`; ruff's `I` rule enforces
the import ordering below it.
"""
__all__ = [
    "ACTOR_SUBJECT_PREFIX", "ADAPTER_FIREBASE_LOOKUP", "AdmissionDecision", "Admit", "AuditWriter",
    "AuthBarrierMiddleware", "BoundedReason", "BudgetExhausted", "BudgetGate",
    "CHALLENGE_ID_BYTES", "CHALLENGE_TTL_SECONDS", "Category", "ChallengeRejection",
    "ChallengeStore", "ClaimKind", "ClientIpBucketKind", "DETAILS_SCHEMA_VERSION",
    "DeviceBitState", "FIREBASE_LOOKUP_ATTEMPTS", "FirebaseAdminAdapter", "HmacConfig",
    "HmacKeyring", "IDP_ACCOUNT_PREFIX", "IdentityKind", "JWTVerifier", "LinkedIdentity",
    "ModeSignal", "NamedVerifier", "PreAuthIdentity", "ProviderDataEntry", "ProviderDataOutcome",
    "ProviderDataResult", "REGISTRY", "REQUEST_CONTEXT_SCOPE_KEY", "Reject",
    "RequestContext", "RevocationOutcome", "RouteMetadata", "StoreAdapter", "StoreState",
    "TokenVerifier", "VERIFIERS", "VendorProofAdapter", "VerificationResult", "VerifiedClaims",
    "VerifiedNotification", "VerifiedTransaction", "assert_route_enumeration", "build_details",
    "classify_mode_signal", "enumerate_registered", "extract_bearer", "lookup", "new_challenge_id",
    "record_rejection", "redact", "resolve_identity",
]

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
from nativespeaker.api.auth.audit import (
    DETAILS_SCHEMA_VERSION,
    AuditWriter,
    build_details,
    redact,
)
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.auth.budgets import (
    ADAPTER_FIREBASE_LOOKUP,
    FIREBASE_LOOKUP_ATTEMPTS,
    BudgetExhausted,
    BudgetGate,
)
from nativespeaker.api.auth.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengeRejection,
    ChallengeStore,
    new_challenge_id,
)
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
from nativespeaker.api.auth.telemetry import record_rejection
from nativespeaker.api.auth.verification import (
    JWTVerifier,
    TokenVerifier,
    VerificationResult,
    VerifiedClaims,
)
from nativespeaker.api.auth.wire import BoundedReason, extract_bearer
