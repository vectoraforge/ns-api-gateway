---
phase: 21-user-management
plan: 01
subsystem: database
tags: [sqlmodel, dataclass, postgresql, upsert, uuid7]

# Dependency graph
requires:
  - phase: 18-error-handling
    provides: AuthenticationError exception class used in auth.py
provides:
  - UserIdentity frozen dataclass with sub/email/name
  - PlanTier StrEnum with free/silver/gold/platinum
  - User SQLModel with uuid7 PK and jwt_sub unique index
  - UsersDB with race-safe get_or_create via pg_insert ON CONFLICT
  - UserService wrapping UsersDB
  - Updated migration SQL with users table and UUID FK
affects: [21-02-PLAN, 21-03-PLAN, 22-subscriptions]

# Tech tracking
tech-stack:
  added: [sqlalchemy.dialects.postgresql.insert]
  patterns: [pg_insert ON CONFLICT DO NOTHING for race-safe upsert, frozen dataclass for immutable identity tokens]

key-files:
  created:
    - app/database/users_db.py
    - app/services/user_service.py
  modified:
    - app/auth.py
    - app/models.py
    - app/database/__init__.py
    - app/services/__init__.py
    - migrations/20260317_01_bvi4l-initial-release.sql

key-decisions:
  - "UserIdentity is a frozen dataclass (not Pydantic) for lightweight immutable token payload"
  - "get_or_create uses INSERT ON CONFLICT DO NOTHING + SELECT (not RETURNING) for guaranteed row return"
  - "Chat.user_id changed from str/Text to UUID FK with ON DELETE RESTRICT"

patterns-established:
  - "Frozen dataclass for auth identity payloads"
  - "pg_insert ON CONFLICT DO NOTHING for race-safe user provisioning"

requirements-completed: [USER-01, USER-03]

# Metrics
duration: 3min
completed: 2026-03-20
---

# Phase 21 Plan 01: User Data Foundation Summary

**UserIdentity dataclass, PlanTier enum, User SQLModel with uuid7 PK, race-safe UsersDB upsert via pg_insert ON CONFLICT, and UserService wrapper**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-20T09:00:02Z
- **Completed:** 2026-03-20T09:03:20Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- UserIdentity frozen dataclass with sub/email/name extracted from JWT payload
- User model with uuid7 PK, jwt_sub unique index, PlanTier enum (free/silver/gold/platinum)
- Race-safe get_or_create using PostgreSQL INSERT ON CONFLICT DO NOTHING
- Chat.user_id changed from str to UUID FK referencing users.id

## Task Commits

Each task was committed atomically:

1. **Task 1: Add UserIdentity dataclass and update TokenVerifier** - `1256021` (feat)
2. **Task 2: Add PlanTier enum, User model, update Chat FK, and rewrite migration** - `cff6443` (feat)
3. **Task 3: Create UsersDB, UserService, and update package re-exports** - `f29eea7` (feat)

## Files Created/Modified
- `app/auth.py` - Added UserIdentity dataclass; updated TokenVerifier/JWTVerifier return type
- `app/models.py` - Added PlanTier StrEnum and User model; changed Chat.user_id to UUID FK
- `app/database/users_db.py` - UsersDB with get_or_create (pg_insert upsert) and get_by_id
- `app/database/__init__.py` - Re-export UsersDB
- `app/services/user_service.py` - UserService wrapping UsersDB
- `app/services/__init__.py` - Re-export UserService
- `migrations/20260317_01_bvi4l-initial-release.sql` - Users table before chats, UUID FK

## Decisions Made
- UserIdentity is a frozen dataclass (not Pydantic) -- lightweight, immutable, no validation overhead for token payloads
- get_or_create uses INSERT ON CONFLICT DO NOTHING followed by SELECT (not RETURNING) because DO NOTHING returns no rows on conflict
- Chat.user_id changed from str/Text to UUID FK with ON DELETE RESTRICT to enforce referential integrity

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All types, models, and data access patterns are in place for Plan 02 (dependency chain, routes, JIT provisioning)
- Plan 03 (tests) will need to update existing test fixtures for UserIdentity return type and UUID user_id FK

## Self-Check: PASSED

All 7 files verified present. All 3 task commits verified (1256021, cff6443, f29eea7).

---
*Phase: 21-user-management*
*Completed: 2026-03-20*
