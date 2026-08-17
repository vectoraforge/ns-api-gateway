# Phase 22: Apple Subscription Integration - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Apple subscription lifecycle events update user plan tiers and propagate to Firebase for JWT enrichment. Webhook receives Apple Store Server Notifications V2, verifies JWS signatures, processes subscription lifecycle (purchase, renewal, grace, billing retry, expiration, revocation), updates local DB (authoritative), and syncs plan to Firebase custom claims (non-blocking). Envoy Gateway rate limiting is Phase 23.

</domain>

<decisions>
## Implementation Decisions

### Webhook design
- New `app/routers/webhooks.py` router — separate module for webhook routes (different auth domain from JWT-protected routes)
- Endpoint: `POST /webhooks/apple` (matches SUBS-01, aligns with Phase 23 ENVOY-03 bypass route)
- JWS verification via `apple-app-store-server-library` (Apple's official Python library) — handles chain verification, root CA pinning, payload decoding
- Library-bundled Apple root CAs — no manual certificate management
- Both sandbox and production environments supported — configurable via AppConfig (environment enum)
- Synchronous processing — process notification fully before returning 200. If processing fails, Apple retries
- Success response: HTTP 200 with empty body (Apple ignores response content)
- Failed JWS verification: HTTP 400 VALIDATION_ERROR using existing error contract — no details about why verification failed (security)

### Subscription mapping
- Product ID → PlanTier mapping is config-driven (in config.yaml) — changeable without code deploy
- Flat product ID mapping (no subscription group awareness needed)
- One active subscription per user — new subscription replaces old
- Trust Apple's lifecycle state machine — apply notification's stated event directly, no transition validation
- Grace period and billing retry: user keeps current tier (Apple is still trying to collect payment)
- Expiration and revocation: user falls back to `free` tier
- Update subscription in-place on plan changes — events log captures change history

### Subscription data model
- Provider-agnostic `Subscription` table (not Apple-specific) — supports future providers
- `SubscriptionProvider` StrEnum in models.py: `apple` (extensible to google, stripe, etc.)
- `SubscriptionStatus` StrEnum: `active`, `grace_period`, `billing_retry`, `expired`, `revoked`
- Subscription fields: user_id (FK), provider (StrEnum), external_id (original_transaction_id), plan (PlanTier), status (SubscriptionStatus), timestamps
- Partial unique index on (user_id, provider) WHERE active — DB-level enforcement of one active sub per provider
- User lookup from webhook: find subscription by original_transaction_id, get user from FK
- All new models in existing `models.py` (consistent with Chat, Message, User)

### Subscription events log
- `SubscriptionEvent` table for audit trail — normalized, provider-agnostic
- Fields: subscription_id (FK), event_type (enum), notification_uuid (UNIQUE), old_tier, new_tier, timestamp
- UNIQUE constraint on notification_uuid — idempotency via ON CONFLICT (SUBS-04)
- Retain events indefinitely — storage is cheap, audit trail is valuable

### Firebase claim sync
- `FirebaseService` class in `app/services/firebase_service.py` — wraps firebase-admin SDK, testable via mock
- Custom claim key: `"plan"` (matches User.plan field, used by Envoy in Phase 23)
- firebase-admin SDK initialized at app startup (lifespan) — fail-fast if credentials missing, stored on app.state
- Credentials via GOOGLE_APPLICATION_CREDENTIALS env var (standard GCP approach) — no duplication with JWT verification (PyJWT uses public JWKS, firebase-admin uses service account)
- Sync via `asyncio.to_thread()` — wraps blocking firebase-admin call without blocking event loop (SUBS-07)
- Webhook-only sync — JIT-provisioned users default to free, no Firebase call on first request. Absence of claim = free
- Sync failure: best-effort with error logging (Claude's discretion on details) — DB is authoritative, Firebase claim will be stale until next successful sync

### Idempotency
- Duplicate notification detection via UNIQUE constraint on notification_uuid in subscription_events table
- Duplicate notification response: HTTP 200 silently — no state change, no errors (SUBS-04)
- Event insertion + subscription update + user plan update in single DB transaction — leverages existing get_db dependency commit/rollback

### Claude's Discretion
- Exact SubscriptionService method signatures and internal structure
- How SubscriptionDB is organized (follows session-in-init pattern)
- Firebase sync error handling details (retry count, logging level)
- Apple notification type/subtype enum mapping implementation
- Config schema for product ID → tier mapping and Apple environment
- Migration SQL structure for new tables
- Test structure for webhook endpoint and subscription processing

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Auth layer (Firebase admin SDK — new)
- `app/auth.py` — TokenVerifier Protocol, JWTVerifier, UserIdentity dataclass. Firebase admin SDK is a SEPARATE concern (writing claims, not reading tokens)
- `app/api/dependencies.py` — get_current_user dependency, get_db session management

### Database layer (extend for subscriptions)
- `app/database/users_db.py` — UsersDB session-in-init pattern to follow for SubscriptionDB
- `app/database/chats_db.py` — ChatsDB pattern reference
- `app/database/__init__.py` — Re-export pattern with `__all__`

### Service layer (extend for subscriptions + Firebase)
- `app/services/user_service.py` — UserService pattern to follow for SubscriptionService
- `app/services/chat_service.py` — ChatService pattern reference
- `app/services/__init__.py` — Re-export pattern with `__all__`

### Models (add Subscription + SubscriptionEvent)
- `app/models.py` — All SQLModel tables, PlanTier StrEnum, uuid7 factory, BaseTable. Add Subscription, SubscriptionEvent, SubscriptionProvider, SubscriptionStatus here

### Routes (new webhooks router)
- `app/routers/chats.py` — Existing router pattern reference
- `app/routers/users.py` — Existing router pattern reference

### Config (Apple + Firebase settings)
- `app/config.py` — AppConfig structure. Add AppleConfig (environment, product mapping) and Firebase config

### App lifecycle
- `app/api/main.py` — FastAPI app, lifespan function. Register webhooks router, initialize firebase-admin

### Error handling
- `app/exceptions.py` — Exception classes with HTTP metadata. Existing VALIDATION_ERROR for bad JWS

### Migration
- `migrations/20260317_01_bvi4l-initial-release.sql` — Current migration. Add subscriptions + subscription_events tables

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PlanTier` StrEnum in models.py — already defines free/silver/gold/platinum tiers
- `User.plan` column — already exists, defaults to free, ready for updates
- `uuid7` factory — reuse for Subscription.id and SubscriptionEvent.id
- `BaseTable(SQLModel)` — base class for new models
- `get_db` dependency — provides transactional session (commit/rollback) for webhook processing
- `structlog` middleware — request correlation already set up, extend to webhook requests

### Established Patterns
- Session-in-init DB classes (ChatsDB, UsersDB) — follow for SubscriptionDB
- Service wrapping DB (ChatService, UserService) — follow for SubscriptionService
- All dependencies in `app/api/dependencies.py` — add webhook-specific dependencies there
- HTTP metadata on exception classes — use existing VALIDATION_ERROR for JWS failures
- StrEnum for typed enums (Role, PlanTier) — follow for SubscriptionProvider, SubscriptionStatus
- `__init__.py` re-export with `__all__` — established in services/ and database/ packages
- Lifespan initialization (JWTVerifier on app.state) — follow for firebase-admin app initialization

### Integration Points
- `app/api/main.py` — register webhooks router, initialize firebase-admin in lifespan
- `app/models.py` — add Subscription, SubscriptionEvent, SubscriptionProvider, SubscriptionStatus
- `app/database/__init__.py` — add SubscriptionDB re-export
- `app/services/__init__.py` — add SubscriptionService, FirebaseService re-export
- `app/config.py` — add AppleConfig and Firebase-related config
- `migrations/*.sql` — add subscriptions and subscription_events tables
- `pyproject.toml` — add apple-app-store-server-library and firebase-admin dependencies

</code_context>

<specifics>
## Specific Ideas

- Subscription table is provider-agnostic — not Apple-specific. Supports future providers (Google, Stripe) without schema changes
- Subscription events log is normalized — event_type enum, not raw Apple payloads
- User explicitly noted: "It can be not just Apple, but other subscription providers. Also, log subscription events in a separate table."
- No duplication between PyJWT (public JWKS for token verification) and firebase-admin (service account for writing custom claims) — different auth purposes
- Single transaction for all state mutations (event log + subscription + user plan) using existing get_db dependency

</specifics>

<deferred>
## Deferred Ideas

- Google Play subscription integration — future phase (subscription table already provider-agnostic)
- Stripe subscription integration — future phase
- App Store Server API polling for retry reconciliation — v2 requirement (USAGE-03)
- Admin subscription management — out of scope
- Subscription analytics/dashboard — future phase
- Grace period transparency in GET /users/me — v2 requirement (USAGE-02)

</deferred>

---

*Phase: 22-apple-subscription-integration*
*Context gathered: 2026-03-20*
