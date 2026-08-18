# Phase 21: User Management - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Local user table with JIT provisioning from JWT identity. First authenticated API request auto-creates a user record. `GET /users/me` returns profile. Concurrent first requests are race-safe. Users cannot access other users' data. No user registration endpoint, no profile editing, no subscription logic (Phase 22).

</domain>

<decisions>
## Implementation Decisions

### User data model
- User table with uuid7 PK (consistent with Chat/Message), `jwt_sub` column (UNIQUE, indexed) for Firebase identity
- Fields: id (uuid7), jwt_sub (str, unique), email (str, required), name (str, nullable), plan (PlanTier StrEnum, default "free"), active (bool, default True), created_at (datetime)
- PlanTier as StrEnum: free/silver/gold/platinum — same pattern as Role enum in models.py
- `active` field for soft-delete: inactive users get opaque 401 AUTH_FAILED (no "account deactivated" reveal)
- Email required from JWT, name optional (nullable) — some Firebase accounts lack name claim

### JWT claim extraction
- JWTVerifier.verify() return type changes from `str` to `UserIdentity` dataclass (sub, email, name)
- TokenVerifier Protocol updated to match: `verify(token) -> UserIdentity`
- All implementations (JWTVerifier + test stubs) updated in one pass

### JIT provisioning flow
- Provisioning happens inside `get_user_id` dependency, renamed to `get_current_user`, returns User model object
- `get_current_user` adds a DB session via `Depends(get_db)` for provisioning
- INSERT ON CONFLICT DO NOTHING on jwt_sub, then SELECT to get existing record
- Snapshot at creation — email/name NOT synced from JWT on subsequent requests
- Inactive users rejected with AuthenticationError (opaque 401)
- New UsersDB class in `app/database/users_db.py` following session-in-init pattern
- New UserService class in `app/services/user_service.py` wrapping UsersDB — consistent with ChatService pattern, ready for Phase 22

### Chat-to-user FK migration
- chats.user_id changes from TEXT (Firebase sub) to UUID FK referencing users.id
- ON DELETE RESTRICT on the FK — prevents accidental hard-deletes
- Rewrite pogo-migrate SQL in migrations/ (no existing data to migrate)
- Chat model gets SQLAlchemy Relationship to User (consistent with Chat.messages pattern)
- ChatsDB methods switch from `user_id: str` to `user_id: UUID` throughout
- All chat routes change from `user_id: str = Depends(get_user_id)` to `user: User = Depends(get_current_user)`, passing `user.id`

### Profile endpoint
- `GET /users/me` in new `app/routers/users.py` router
- Returns: email, name, plan, created_at (no internal id exposed)
- Basic profile only — usage/quota data deferred to Phase 23 (ENVOY-05)
- DB errors during provisioning return 500/INTERNAL_ERROR via existing error handler

### Test impact
- Transaction rollback (Phase 18) handles JIT-created user records — no test infra changes needed
- E2E tests work as-is: Firebase tokens trigger JIT provisioning, rollback cleans up

### Claude's Discretion
- Pydantic response schema for GET /users/me
- UserIdentity dataclass location (auth.py or separate module)
- Exact UsersDB method signatures and query patterns
- UserService method signatures
- Test structure for new user endpoints

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Auth layer (verify return type change)
- `app/auth.py` — TokenVerifier Protocol and JWTVerifier implementation. verify() currently returns str, must return UserIdentity dataclass
- `app/api/dependencies.py` — get_user_id() dependency to be renamed get_current_user(), needs DB session param added

### Database layer (UsersDB pattern source)
- `app/database/chats_db.py` — Session-in-init pattern to follow for UsersDB
- `app/database/__init__.py` — Re-export pattern with `__all__`

### Service layer (UserService pattern source)
- `app/services/chat_service.py` — Service wrapping DB class pattern to follow for UserService
- `app/services/__init__.py` — Re-export pattern with `__all__`

### Models (User model location)
- `app/models.py` — Chat/Message models, Role StrEnum, uuid7 factory, BaseTable. Add User model and PlanTier StrEnum here

### Migration (rewrite)
- `migrations/20260317_01_bvi4l-initial-release.sql` — Add users table, change chats.user_id to UUID FK

### Routes (chat route signature changes)
- `app/routers/chats.py` — All chat routes use `user_id: str = Depends(get_user_id)`, must change to `user: User = Depends(get_current_user)`
- `app/routers/root.py` — Uses get_user_id in chat-related endpoint
- `app/routers/examples.py` — May use get_user_id

### Error handling
- `app/exceptions.py` — AuthenticationError class used for inactive user rejection
- `app/api/errors.py` — Existing error handlers, no changes needed

### Config
- `app/config.py` — AppConfig, no changes needed for Phase 21

### Tests (JWT stub updates)
- `tests/unit/conftest.py` — Test JWT stubs must return UserIdentity instead of str
- `tests/e2e/conftest.py` — E2E fixtures, transaction rollback handles user cleanup

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `uuid7` factory in models.py — reuse for User.id default
- `BaseTable(SQLModel)` — base class for User model
- `Role(StrEnum)` — pattern to follow for PlanTier enum
- `ChatsDB` session-in-init pattern — template for UsersDB
- `ChatService` — template for UserService
- `__init__.py` re-export with `__all__` — established in both packages

### Established Patterns
- All FastAPI dependencies in `app/api/dependencies.py`
- HTTP metadata on exception classes, single data-driven error handler
- Session-in-init on DB classes (session passed at construction)
- `dependency_overrides` for DI swapping in tests
- structlog contextvars for request-scoped logging (user_id already bound in get_user_id)

### Integration Points
- `app/api/dependencies.py:get_user_id()` — rename to get_current_user, add DB session, return User model
- `app/api/main.py` — register new users router
- `app/database/__init__.py` — add UsersDB re-export
- `app/services/__init__.py` — add UserService re-export
- `migrations/*.sql` — rewrite to include users table + FK

</code_context>

<specifics>
## Specific Ideas

- Column name `jwt_sub` for Firebase identity (user's explicit choice over firebase_uid or external_id)
- Soft-delete via `active` field — no hard deletes, inactive users get opaque 401 (same as invalid token, no information leakage)
- No existing data to migrate — rewrite the pogo-migrate SQL directly

</specifics>

<deferred>
## Deferred Ideas

- Profile sync from JWT on subsequent requests (update email/name when JWT claims change) — future enhancement
- User profile editing (PUT /users/me) — future phase if needed
- User deactivation mechanism (admin endpoint or self-service) — future phase
- Usage/quota data in GET /users/me response — Phase 23 (ENVOY-05)

</deferred>

---

*Phase: 21-user-management*
*Context gathered: 2026-03-20*
