# Phase 22: Apple Subscription Integration - Research

**Researched:** 2026-03-20
**Domain:** Apple App Store Server Notifications V2, Firebase Admin SDK, subscription lifecycle management
**Confidence:** HIGH

## Summary

This phase adds a webhook endpoint to receive Apple App Store Server Notifications V2, verify JWS signatures, process subscription lifecycle events, update user plan tiers in the local DB (authoritative), and sync plan changes to Firebase custom claims (non-blocking). The implementation uses Apple's official `app-store-server-library` Python SDK for JWS verification and payload decoding, and `firebase-admin` Python SDK for custom claim writes.

The core technical challenges are: (1) correctly configuring `SignedDataVerifier` with Apple root CA certificates, (2) mapping Apple's notification type/subtype matrix to subscription status changes, (3) ensuring idempotency via UNIQUE constraint on `notificationUUID`, and (4) wrapping the synchronous `firebase-admin` call with `asyncio.to_thread()` to avoid blocking the event loop.

**Primary recommendation:** Use `app-store-server-library` v3.0.0 for JWS verification (handles chain verification, payload decoding into typed models), `firebase-admin` v7.3.0 for custom claims, and follow the existing project patterns (session-in-init DB, service wrapping DB, StrEnum models in models.py).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- New `app/routers/webhooks.py` router -- separate module for webhook routes (different auth domain from JWT-protected routes)
- Endpoint: `POST /webhooks/apple` (matches SUBS-01, aligns with Phase 23 ENVOY-03 bypass route)
- JWS verification via `apple-app-store-server-library` (Apple's official Python library) -- handles chain verification, root CA pinning, payload decoding
- Library-bundled Apple root CAs -- no manual certificate management
- Both sandbox and production environments supported -- configurable via AppConfig (environment enum)
- Synchronous processing -- process notification fully before returning 200. If processing fails, Apple retries
- Success response: HTTP 200 with empty body (Apple ignores response content)
- Failed JWS verification: HTTP 400 VALIDATION_ERROR using existing error contract -- no details about why verification failed (security)
- Product ID to PlanTier mapping is config-driven (in config.yaml) -- changeable without code deploy
- Flat product ID mapping (no subscription group awareness needed)
- One active subscription per user -- new subscription replaces old
- Trust Apple's lifecycle state machine -- apply notification's stated event directly, no transition validation
- Grace period and billing retry: user keeps current tier (Apple is still trying to collect payment)
- Expiration and revocation: user falls back to `free` tier
- Update subscription in-place on plan changes -- events log captures change history
- Provider-agnostic `Subscription` table (not Apple-specific) -- supports future providers
- `SubscriptionProvider` StrEnum in models.py: `apple` (extensible to google, stripe, etc.)
- `SubscriptionStatus` StrEnum: `active`, `grace_period`, `billing_retry`, `expired`, `revoked`
- Subscription fields: user_id (FK), provider (StrEnum), external_id (original_transaction_id), plan (PlanTier), status (SubscriptionStatus), timestamps
- Partial unique index on (user_id, provider) WHERE active -- DB-level enforcement of one active sub per provider
- User lookup from webhook: find subscription by original_transaction_id, get user from FK
- All new models in existing `models.py` (consistent with Chat, Message, User)
- `SubscriptionEvent` table for audit trail -- normalized, provider-agnostic
- Fields: subscription_id (FK), event_type (enum), notification_uuid (UNIQUE), old_tier, new_tier, timestamp
- UNIQUE constraint on notification_uuid -- idempotency via ON CONFLICT (SUBS-04)
- Retain events indefinitely -- storage is cheap, audit trail is valuable
- `FirebaseService` class in `app/services/firebase_service.py` -- wraps firebase-admin SDK, testable via mock
- Custom claim key: `"plan"` (matches User.plan field, used by Envoy in Phase 23)
- firebase-admin SDK initialized at app startup (lifespan) -- fail-fast if credentials missing, stored on app.state
- Credentials via GOOGLE_APPLICATION_CREDENTIALS env var (standard GCP approach) -- no duplication with JWT verification (PyJWT uses public JWKS, firebase-admin uses service account)
- Sync via `asyncio.to_thread()` -- wraps blocking firebase-admin call without blocking event loop (SUBS-07)
- Webhook-only sync -- JIT-provisioned users default to free, no Firebase call on first request. Absence of claim = free
- Sync failure: best-effort with error logging -- DB is authoritative, Firebase claim will be stale until next successful sync
- Duplicate notification detection via UNIQUE constraint on notification_uuid in subscription_events table
- Duplicate notification response: HTTP 200 silently -- no state change, no errors (SUBS-04)
- Event insertion + subscription update + user plan update in single DB transaction -- leverages existing get_db dependency commit/rollback

### Claude's Discretion
- Exact SubscriptionService method signatures and internal structure
- How SubscriptionDB is organized (follows session-in-init pattern)
- Firebase sync error handling details (retry count, logging level)
- Apple notification type/subtype enum mapping implementation
- Config schema for product ID to tier mapping and Apple environment
- Migration SQL structure for new tables
- Test structure for webhook endpoint and subscription processing

### Deferred Ideas (OUT OF SCOPE)
- Google Play subscription integration -- future phase (subscription table already provider-agnostic)
- Stripe subscription integration -- future phase
- App Store Server API polling for retry reconciliation -- v2 requirement (USAGE-03)
- Admin subscription management -- out of scope
- Subscription analytics/dashboard -- future phase
- Grace period transparency in GET /users/me -- v2 requirement (USAGE-02)

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SUBS-01 | App receives Apple Store Server Notifications V2 via `POST /webhooks/apple` | `app-store-server-library` v3.0.0 provides `SignedDataVerifier.verify_and_decode_notification()` which decodes the `signedPayload` from Apple's POST body |
| SUBS-02 | Apple notifications are verified using JWS signature chain verification | `SignedDataVerifier` handles full X.509 chain verification, root CA pinning, environment validation; raises `VerificationException` on failure |
| SUBS-03 | Webhook processes full subscription lifecycle (active, grace period, billing retry, expired, revoked) | `NotificationTypeV2` enum covers all lifecycle events; `Subtype` enum provides event detail; mapping research complete (see Architecture Patterns) |
| SUBS-04 | Duplicate Apple notifications are safely ignored (idempotency on `notificationUUID`) | `ResponseBodyV2DecodedPayload.notificationUUID` field available after verification; PostgreSQL UNIQUE constraint + ON CONFLICT DO NOTHING pattern (same as existing `get_or_create`) |
| SUBS-05 | User's plan tier stored in local DB as authoritative source | Existing `User.plan` column (PlanTier StrEnum) updated within same transaction as subscription + event mutations |
| SUBS-06 | Plan changes sync to Firebase custom claims for JWT propagation | `firebase_admin.auth.set_custom_user_claims(uid, {"plan": tier})` -- synchronous API, wrap in `asyncio.to_thread()` |
| SUBS-07 | Firebase claim sync does not block the event loop | `asyncio.to_thread()` wraps the blocking `set_custom_user_claims` call; confirmed firebase-admin has no native async auth API |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| app-store-server-library | 3.0.0 | JWS verification, notification payload decoding | Apple's official Python SDK; handles X.509 chain verification, root CA pinning, typed payload models |
| firebase-admin | 7.3.0 | Firebase custom claim writes | Google's official SDK; `auth.set_custom_user_claims()` for plan tier propagation to JWT |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SQLModel | >=0.0.22 | Subscription + SubscriptionEvent models | Already in project; extend with new tables |
| SQLAlchemy | (via SQLModel) | Partial unique index, ON CONFLICT | Already in project; `Index` with `postgresql_where` for partial unique |
| structlog | >=25.5 | Webhook request logging | Already in project; webhook logging follows existing patterns |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| app-store-server-library | Manual JWS verification with PyJWT + cryptography | Would need to implement certificate chain verification, OCSP checks, root CA pinning manually -- extremely error-prone |
| firebase-admin | Firebase REST API directly | Would need to manage OAuth2 tokens manually, no benefit over SDK |

**Installation:**
```bash
uv add app-store-server-library firebase-admin
```

**Version verification:** Verified via PyPI on 2026-03-20:
- `app-store-server-library` 3.0.0 released 2026-03-13
- `firebase-admin` 7.3.0 released 2026-03-19

## Architecture Patterns

### Recommended Project Structure
```
app/
├── routers/
│   └── webhooks.py            # POST /webhooks/apple (no JWT auth)
├── services/
│   ├── subscription_service.py # SubscriptionService (orchestrates DB + Firebase)
│   └── firebase_service.py     # FirebaseService (wraps firebase-admin SDK)
├── database/
│   └── subscriptions_db.py     # SubscriptionDB (session-in-init pattern)
├── models.py                   # + Subscription, SubscriptionEvent, SubscriptionProvider, SubscriptionStatus
└── config.py                   # + AppleConfig (environment, product_id_to_tier, bundle_id, root_cert_paths)
```

### Pattern 1: Apple Notification Verification Flow
**What:** Receive signedPayload, verify JWS, decode to typed payload, extract notification details
**When to use:** Every incoming `POST /webhooks/apple` request

The Apple webhook sends a JSON body with a single `signedPayload` field:
```json
{"signedPayload": "<JWS_TOKEN>"}
```

The verification flow:
```python
# Source: https://github.com/apple/app-store-server-library-python README
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.Subtype import Subtype
from appstoreserverlibrary.models.ResponseBodyV2DecodedPayload import ResponseBodyV2DecodedPayload

# Initialize once at startup (store on app.state)
verifier = SignedDataVerifier(
    root_certificates,       # List[bytes] -- Apple root CA .cer files read as bytes
    enable_online_checks,    # bool -- OCSP checks
    environment,             # Environment.SANDBOX or Environment.PRODUCTION
    bundle_id,               # str -- e.g. "com.example.app"
    app_apple_id             # int | None -- required for Production
)

# Per-request verification
try:
    payload: ResponseBodyV2DecodedPayload = verifier.verify_and_decode_notification(signed_payload)
except VerificationException:
    # Return 400 -- invalid signature
    raise WebhookVerificationError()
```

### Pattern 2: Notification Type to Subscription Status Mapping
**What:** Map Apple's notification type/subtype combinations to our SubscriptionStatus enum
**When to use:** After successful JWS verification, before DB mutation

Key lifecycle mapping:
```
SUBSCRIBED + INITIAL_BUY      -> status=active, plan=product_to_tier(productId)
SUBSCRIBED + RESUBSCRIBE      -> status=active, plan=product_to_tier(productId)
DID_RENEW                     -> status=active (plan unchanged)
DID_RENEW + BILLING_RECOVERY  -> status=active (recovered from billing retry)
DID_FAIL_TO_RENEW + GRACE_PERIOD -> status=grace_period (keep current tier)
DID_FAIL_TO_RENEW             -> status=billing_retry (keep current tier)
EXPIRED + VOLUNTARY           -> status=expired, plan=free
EXPIRED + BILLING_RETRY       -> status=expired, plan=free
EXPIRED + PRICE_INCREASE      -> status=expired, plan=free
REVOKE                        -> status=revoked, plan=free
DID_CHANGE_RENEWAL_PREF + UPGRADE   -> status=active, plan=product_to_tier(new productId)
DID_CHANGE_RENEWAL_PREF + DOWNGRADE -> no immediate change (takes effect at next renewal)
```

Notifications to ignore (no subscription state change needed):
```
TEST                          -> no-op (Apple connectivity test)
CONSUMPTION_REQUEST           -> no-op (refund consideration, not state change)
REFUND_DECLINED               -> no-op
PRICE_INCREASE                -> no-op (user hasn't acted yet)
RENEWAL_EXTENDED              -> no-op (grace extension by developer)
EXTERNAL_PURCHASE_TOKEN       -> no-op (not applicable)
ONE_TIME_CHARGE               -> no-op (not subscription)
```

### Pattern 3: Idempotent Subscription Event Processing
**What:** Use UNIQUE constraint on notification_uuid with ON CONFLICT to silently ignore duplicates
**When to use:** Every notification processing -- ensures duplicate Apple retries are safe

```python
# Follow existing pattern from UsersDB.get_or_create
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = (
    pg_insert(SubscriptionEvent)
    .values(
        subscription_id=subscription.id,
        event_type=event_type,
        notification_uuid=payload.notificationUUID,
        old_tier=old_tier,
        new_tier=new_tier,
    )
    .on_conflict_do_nothing(index_elements=["notification_uuid"])
)
result = await session.exec(stmt)

# If rowcount == 0, this was a duplicate -- skip further processing
if result.rowcount == 0:
    return  # Duplicate, return 200 silently
```

### Pattern 4: Firebase Claim Sync (Non-Blocking)
**What:** Update Firebase custom claims in a background thread after DB commit
**When to use:** After subscription update changes user's plan tier

```python
import asyncio
import firebase_admin
from firebase_admin import auth, credentials

# Initialization at startup (in lifespan)
cred = credentials.ApplicationDefault()  # Uses GOOGLE_APPLICATION_CREDENTIALS
firebase_app = firebase_admin.initialize_app(cred)

# Non-blocking sync in service
async def sync_plan_to_firebase(self, jwt_sub: str, plan: str) -> None:
    try:
        await asyncio.to_thread(
            auth.set_custom_user_claims, jwt_sub, {"plan": plan}
        )
    except Exception:
        # Best-effort -- DB is authoritative. Log warning, don't raise
        logger.warning("firebase_claim_sync_failed", jwt_sub=jwt_sub, plan=plan)
```

### Pattern 5: Partial Unique Index for One Active Subscription Per Provider
**What:** PostgreSQL partial unique index enforcing one active subscription per user per provider
**When to use:** Subscription model definition

```python
from sqlalchemy import Index, text

class Subscription(BaseTable, table=True):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "ix_subscriptions_user_provider_active",
            "user_id", "provider",
            unique=True,
            postgresql_where=text("status NOT IN ('expired', 'revoked')")
        ),
    )
```

### Pattern 6: Webhook Router Without JWT Auth
**What:** Register webhooks router without JWT auth dependency (Apple sends its own JWS auth)
**When to use:** Webhook routes that have their own authentication mechanism

The webhooks router is registered separately from authenticated routes. It does NOT use `get_current_user` dependency. The `get_db` dependency is still used for transactional DB access.

```python
# app/routers/webhooks.py
router = APIRouter(tags=["webhooks"])

@router.post("/webhooks/apple", status_code=200)
async def apple_webhook(request: Request,
                         db: AsyncSession = Depends(get_db)) -> Response:
    body = await request.json()
    signed_payload = body.get("signedPayload")
    # ... verify and process
    return Response(status_code=200)
```

### Anti-Patterns to Avoid
- **Validating notification state transitions:** Do NOT build a state machine to validate transitions (e.g., "can only go from active to expired"). Trust Apple's lifecycle -- they handle the state machine. Apply the stated event directly.
- **Blocking Firebase calls in async path:** Do NOT call `auth.set_custom_user_claims()` directly in an async function. Always wrap in `asyncio.to_thread()`.
- **Storing raw Apple payloads:** Do NOT store the raw JWS or full decoded payload. Use normalized, provider-agnostic event models.
- **Returning non-200 for duplicate notifications:** Always return 200 for duplicates. Returning errors causes Apple to retry indefinitely.
- **Using UniqueConstraint for partial index:** SQLAlchemy's `UniqueConstraint` does NOT support `postgresql_where`. Must use `Index(..., unique=True, postgresql_where=...)`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWS verification | Manual JWT decode + X.509 chain verification | `SignedDataVerifier.verify_and_decode_notification()` | Certificate chain verification, OCSP checks, root CA pinning, payload typing -- extremely complex to get right |
| Apple notification models | Manual JSON parsing of notification payloads | `ResponseBodyV2DecodedPayload`, `NotificationTypeV2`, `Subtype` from library | Apple maintains these models; they change with API versions |
| Firebase auth operations | Direct REST API calls to Firebase | `firebase_admin.auth.set_custom_user_claims()` | OAuth2 token management, retry logic, error handling built into SDK |
| Idempotency mechanism | Application-level duplicate tracking (in-memory set, Redis) | PostgreSQL UNIQUE constraint + ON CONFLICT DO NOTHING | DB-level guarantee, survives restarts, zero extra infrastructure |

**Key insight:** The Apple JWS verification is the single most important thing not to hand-roll. It involves X.509 certificate chain validation with OCSP revocation checks against Apple's root CAs. The official library handles all of this with a single method call.

## Common Pitfalls

### Pitfall 1: Root Certificates Not Bundled
**What goes wrong:** The `app-store-server-library` does NOT bundle Apple root CA certificates. You must download them separately from https://www.apple.com/certificateauthority/ and provide them as `List[bytes]` to `SignedDataVerifier`.
**Why it happens:** Apple keeps certificate management separate from the library for security (certificates expire and need updates).
**How to avoid:** Download Apple Root CA certificates (AppleRootCA-G2.cer, AppleRootCA-G3.cer, AppleComputerRootCertificate.cer, AppleIncRootCertificate.cer) and bundle them with the application (e.g., in a `certs/` directory or as package data). Load them as bytes at startup.
**Warning signs:** `VerificationException` with `INVALID_CERTIFICATE` or `INVALID_CHAIN` status at runtime.

**NOTE:** The CONTEXT.md states "Library-bundled Apple root CAs -- no manual certificate management". This is INCORRECT based on research. The library requires externally provided root certificates. Implementation must handle certificate loading. This does not change the verification approach (still use `SignedDataVerifier`), just requires adding certificate files to the project and loading them at startup.

### Pitfall 2: Transaction Info is Also JWS-Signed
**What goes wrong:** The `data.signedTransactionInfo` and `data.signedRenewalInfo` fields within the decoded notification are themselves JWS-signed strings that need separate verification and decoding.
**Why it happens:** Apple signs each layer independently for security.
**How to avoid:** After decoding the notification, use `verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)` to get `JWSTransactionDecodedPayload` with `originalTransactionId`, `productId`, etc.
**Warning signs:** Getting string values where you expected typed objects for transaction details.

### Pitfall 3: app_apple_id Required for Production
**What goes wrong:** `SignedDataVerifier` constructor requires `app_apple_id` (integer) for Production environment but it's optional for Sandbox.
**Why it happens:** Production verification has stricter requirements.
**How to avoid:** Include `app_apple_id` in config. For sandbox testing, it can be `None`. For production, it must be the numeric Apple ID from App Store Connect.
**Warning signs:** `VerificationException` with `INVALID_APP_IDENTIFIER` in production but tests pass in sandbox.

### Pitfall 4: Firebase set_custom_user_claims Uses Firebase UID, Not JWT sub
**What goes wrong:** `auth.set_custom_user_claims(uid, claims)` expects the Firebase UID, which in this project IS the `jwt_sub` (the `sub` claim from Firebase tokens). But confirm this assumption.
**Why it happens:** Firebase UID is the `localId` from Firebase Auth, which appears as `sub` in Firebase ID tokens.
**How to avoid:** Use `user.jwt_sub` (which stores the Firebase `sub` claim) as the `uid` parameter for `set_custom_user_claims`.
**Warning signs:** "User not found" errors from Firebase when syncing claims.

### Pitfall 5: Partial Unique Index in Migrations vs SQLModel
**What goes wrong:** SQLModel's `create_all()` may not correctly create partial indexes with `postgresql_where` conditions.
**Why it happens:** The `postgresql_where` clause in `Index.__table_args__` may not be handled properly by `create_all()` in all SQLAlchemy versions.
**How to avoid:** Define the partial index in the migration SQL explicitly: `CREATE UNIQUE INDEX ... ON subscriptions (user_id, provider) WHERE status NOT IN ('expired', 'revoked')`. Keep the `__table_args__` definition for documentation, but rely on migration for actual creation.
**Warning signs:** Tests pass (using `create_all`) but production fails (using migrations), or vice versa.

### Pitfall 6: Error Code Mismatch for JWS Failure
**What goes wrong:** CONTEXT.md specifies "HTTP 400 VALIDATION_ERROR" for JWS failures. The project's `_CODE_MAP` maps 400 to `"invalid_request"`, not `"validation_error"`. The `"validation_error"` code maps to 422.
**Why it happens:** The CONTEXT.md label "VALIDATION_ERROR" may refer to the concept, not the literal error code string.
**How to avoid:** Create a `WebhookVerificationError(ServiceError)` with `status_code = 400` and `error_code = "validation_error"` -- this is valid because ServiceError subclasses bypass the `_CODE_MAP` and use their own `error_code` directly. Alternatively, use `error_code = "invalid_request"` to match the 400-status convention. Either works within the contract.
**Warning signs:** Inconsistent error codes in API responses for JWS failures.

### Pitfall 7: DID_CHANGE_RENEWAL_PREF DOWNGRADE is Deferred
**What goes wrong:** Processing a DOWNGRADE subtype as an immediate plan change when Apple only applies it at next renewal.
**Why it happens:** Confusing "preference changed" with "plan changed".
**How to avoid:** For `DID_CHANGE_RENEWAL_PREF + DOWNGRADE`, log the event but do NOT change the current plan. The actual plan change happens at the next `DID_RENEW` with the new product ID.
**Warning signs:** User's plan downgrades immediately instead of at end of billing period.

## Code Examples

Verified patterns from official sources:

### Apple Notification Webhook Endpoint

```python
# Source: https://github.com/apple/app-store-server-library-python README
# + project patterns from app/routers/users.py, app/api/dependencies.py

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from exceptions import ServiceError

router = APIRouter(tags=["webhooks"])


class WebhookVerificationError(ServiceError):
    """JWS signature verification failed."""
    status_code = 400
    error_code = "validation_error"


@router.post("/webhooks/apple", status_code=200)
async def apple_webhook(request: Request,
                        db: AsyncSession = Depends(get_db)) -> Response:
    body = await request.json()
    signed_payload = body.get("signedPayload")
    if not signed_payload:
        raise WebhookVerificationError("Missing signedPayload")

    # SubscriptionService handles verification + processing + Firebase sync
    subscription_service = SubscriptionService(db=db, ...)
    await subscription_service.process_apple_notification(signed_payload)

    return Response(status_code=200)
```

### Loading Apple Root Certificates
```python
# Source: https://www.apple.com/certificateauthority/
from pathlib import Path

def load_apple_root_certificates(cert_dir: Path) -> list[bytes]:
    """Load Apple root CA certificates as bytes for SignedDataVerifier."""
    cert_files = [
        "AppleComputerRootCertificate.cer",
        "AppleIncRootCertificate.cer",
        "AppleRootCA-G2.cer",
        "AppleRootCA-G3.cer",
    ]
    certs = []
    for filename in cert_files:
        cert_path = cert_dir / filename
        certs.append(cert_path.read_bytes())
    return certs
```

### Firebase Service Initialization
```python
# Source: https://firebase.google.com/docs/admin/setup
# + project pattern from app/api/main.py lifespan
import firebase_admin
from firebase_admin import auth, credentials

# In lifespan:
cred = credentials.ApplicationDefault()  # Uses GOOGLE_APPLICATION_CREDENTIALS env var
firebase_app = firebase_admin.initialize_app(cred)
app.state.firebase_app = firebase_app

# In FirebaseService:
class FirebaseService:
    async def set_plan_claim(self, firebase_uid: str, plan: str) -> None:
        await asyncio.to_thread(
            auth.set_custom_user_claims, firebase_uid, {"plan": plan}
        )
```

### Subscription and SubscriptionEvent Models
```python
# Following project patterns from app/models.py
from sqlalchemy import Index, text

class SubscriptionProvider(StrEnum):
    apple = "apple"

class SubscriptionStatus(StrEnum):
    active = "active"
    grace_period = "grace_period"
    billing_retry = "billing_retry"
    expired = "expired"
    revoked = "revoked"

class Subscription(BaseTable, table=True):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "ix_subscriptions_user_provider_active",
            "user_id", "provider",
            unique=True,
            postgresql_where=text("status NOT IN ('expired', 'revoked')")
        ),
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    provider: SubscriptionProvider = Field(sa_type=Text())
    external_id: str = Field(sa_type=Text())  # original_transaction_id
    plan: PlanTier = Field(sa_type=Text())
    status: SubscriptionStatus = Field(sa_type=Text())
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC),
                                  sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC),
                                  sa_type=DateTime(timezone=True))

class SubscriptionEvent(BaseTable, table=True):
    __tablename__ = "subscription_events"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    subscription_id: UUID = Field(foreign_key="subscriptions.id", index=True)
    event_type: str = Field(sa_type=Text())  # e.g. "SUBSCRIBED", "DID_RENEW"
    notification_uuid: str = Field(unique=True, sa_type=Text())
    old_tier: str | None = Field(default=None, sa_type=Text())
    new_tier: str | None = Field(default=None, sa_type=Text())
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC),
                                  sa_type=DateTime(timezone=True))
```

### Migration SQL for New Tables
```sql
-- Subscription table
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscriptions_user_id ON subscriptions (user_id);
CREATE INDEX ix_subscriptions_external_id ON subscriptions (external_id);
CREATE UNIQUE INDEX ix_subscriptions_user_provider_active
    ON subscriptions (user_id, provider)
    WHERE status NOT IN ('expired', 'revoked');

-- Subscription events table
CREATE TABLE subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES subscriptions (id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_tier TEXT,
    new_tier TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscription_events_subscription_id ON subscription_events (subscription_id);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| App Store Server Notifications V1 | V2 (JWS-signed payloads) | 2022 (WWDC22) | V2 is required; V1 deprecated |
| Manual JWS verification | `app-store-server-library` official SDK | 2023 (initial release) | Eliminates manual crypto code |
| `firebase-admin` 6.x | 7.x | July 2025 | Python 3.9 deprecated; no async auth API change |
| `app-store-server-library` 2.x | 3.0.0 | March 2026 | Breaking: ConsumptionRequest -> V2 variant (does not affect subscription notifications) |

**Deprecated/outdated:**
- App Store Server Notifications V1: Fully deprecated by Apple. V2 is the only supported format.
- `receiptData` / `verifyReceipt` endpoint: Deprecated. Use App Store Server API and Server Notifications V2.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 with pytest-asyncio >=1.3 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python3 -m pytest tests/unit/ -x` |
| Full suite command | `python3 -m pytest -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SUBS-01 | POST /webhooks/apple receives notifications | unit | `python3 -m pytest tests/unit/test_webhooks.py::TestAppleWebhook::test_receives_notification -x` | Wave 0 |
| SUBS-02 | Invalid JWS signatures rejected before state mutation | unit | `python3 -m pytest tests/unit/test_webhooks.py::TestAppleWebhook::test_invalid_jws_rejected -x` | Wave 0 |
| SUBS-03 | Subscription lifecycle events processed correctly | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestSubscriptionLifecycle -x` | Wave 0 |
| SUBS-04 | Duplicate notifications silently ignored | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestIdempotency -x` | Wave 0 |
| SUBS-05 | User plan tier stored in local DB | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestPlanTierUpdate -x` | Wave 0 |
| SUBS-06 | Plan changes sync to Firebase custom claims | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestFirebaseSync -x` | Wave 0 |
| SUBS-07 | Firebase sync uses asyncio.to_thread (non-blocking) | unit | `python3 -m pytest tests/unit/test_subscriptions.py::TestFirebaseSync::test_uses_to_thread -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/unit/ -x`
- **Per wave merge:** `python3 -m pytest -x` (full suite excluding e2e)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_webhooks.py` -- covers SUBS-01, SUBS-02
- [ ] `tests/unit/test_subscriptions.py` -- covers SUBS-03, SUBS-04, SUBS-05, SUBS-06, SUBS-07
- [ ] Unit test fixtures for mocking `SignedDataVerifier` and `FirebaseService`
- [ ] Framework install: `uv add app-store-server-library firebase-admin` -- new dependencies required

## Open Questions

1. **Error code for JWS verification failure**
   - What we know: CONTEXT.md says "HTTP 400 VALIDATION_ERROR". The project maps 400 to "invalid_request" in `_CODE_MAP`, but ServiceError subclasses use their own `error_code` directly (bypass `_CODE_MAP`).
   - What's unclear: Whether "VALIDATION_ERROR" in CONTEXT.md means the literal code `"validation_error"` or the concept.
   - Recommendation: Use `status_code=400, error_code="validation_error"` as CONTEXT.md states. This is valid within the ServiceError system.

2. **Apple root CA certificate delivery in deployment**
   - What we know: Root CAs must be downloaded from Apple PKI and loaded at startup. Not bundled with library.
   - What's unclear: STATE.md lists "Apple root CA certificate delivery method (ConfigMap, secret, or baked into image)" as a blocker.
   - Recommendation: For development and testing, include certificate files in the repo under a `certs/` directory. Deployment delivery method is an ops concern and can be deferred (config path in AppConfig).

3. **app_apple_id value for sandbox vs production**
   - What we know: Required for Production, optional for Sandbox.
   - What's unclear: The specific app_apple_id numeric value.
   - Recommendation: Make it an optional config field. Tests use Sandbox (None). Production must provide it.

4. **DID_CHANGE_RENEWAL_PREF with UPGRADE timing**
   - What we know: Upgrades take effect immediately (Apple upgrades the subscription right away). Downgrades are deferred to next renewal.
   - What's unclear: Whether the UPGRADE subtype on DID_CHANGE_RENEWAL_PREF means the subscription is already upgraded (signedTransactionInfo reflects new product) or if the actual change comes via a separate SUBSCRIBED notification.
   - Recommendation: For UPGRADE, check signedTransactionInfo for the new productId and update plan immediately. Log the event regardless.

## Sources

### Primary (HIGH confidence)
- [app-store-server-library PyPI](https://pypi.org/project/app-store-server-library/) - version 3.0.0, installation, API overview
- [apple/app-store-server-library-python GitHub](https://github.com/apple/app-store-server-library-python) - README, SignedDataVerifier usage, Environment enum
- [Apple library Python docs](https://apple.github.io/app-store-server-library-python/) - SignedDataVerifier API, VerificationStatus enum, method signatures
- [NotificationTypeV2 source](https://apple.github.io/app-store-server-library-python/_modules/appstoreserverlibrary/models/NotificationTypeV2.html) - Complete enum values
- [Subtype source](https://github.com/apple/app-store-server-library-python/blob/main/appstoreserverlibrary/models/Subtype.py) - Complete Subtype enum values
- [JWSTransactionDecodedPayload source](https://github.com/apple/app-store-server-library-python/blob/main/appstoreserverlibrary/models/JWSTransactionDecodedPayload.py) - Transaction payload fields
- [firebase-admin PyPI](https://pypi.org/project/firebase-admin/) - version 7.3.0
- [firebase-admin auth.py source](https://github.com/firebase/firebase-admin-python/blob/main/firebase_admin/auth.py) - set_custom_user_claims signature, synchronous-only API confirmed
- [Firebase custom claims docs](https://firebase.google.com/docs/auth/admin/custom-claims) - Usage patterns, claim size limits
- [Apple PKI](https://www.apple.com/certificateauthority/) - Root CA certificate downloads

### Secondary (MEDIUM confidence)
- [Apple Developer - signedPayload](https://developer.apple.com/documentation/appstoreserverapi/signedpayload) - Webhook POST body format (single `signedPayload` field)
- [SQLAlchemy partial unique index](https://www.johbo.com/2016/creating-a-partial-unique-index-with-sqlalchemy-in-postgresql.html) - `Index(..., unique=True, postgresql_where=...)` syntax
- [Firebase Python SDK asyncio](https://hiranya911.medium.com/firebase-python-admin-sdk-with-asyncio-d65f39463916) - Confirmed `run_in_executor` / `to_thread` pattern for blocking calls

### Tertiary (LOW confidence)
- None -- all findings verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official Apple and Firebase SDKs, versions verified on PyPI
- Architecture: HIGH - Patterns follow existing project conventions (session-in-init, service wrapping DB, StrEnum models) and verified library APIs
- Pitfalls: HIGH - Root certificate requirement verified via GitHub source inspection and changelog review; Firebase sync pattern confirmed via SDK source code

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (stable APIs, 30-day window)
