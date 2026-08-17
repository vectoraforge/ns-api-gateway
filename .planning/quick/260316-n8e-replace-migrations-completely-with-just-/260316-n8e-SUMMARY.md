---
phase: quick
plan: 260316-n8e
subsystem: database
tags: [postgres, docker, ddl, schema]

# Dependency graph
requires: []
provides:
  - Single init.sql with DDL matching current SQLModel definitions
  - Clean docker-compose volume mount for fresh DB initialization
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single init.sql replaces incremental migrations for simple schema"

key-files:
  created:
    - init.sql
  modified:
    - docker-compose.yml

key-decisions:
  - "Single init.sql over incremental migrations -- schema is small and migrations were stale"
  - "ON DELETE CASCADE on messages.chat_id preserved for chat cleanup"
  - "JSONB (not JSON) for content column to enable future indexing"

patterns-established:
  - "Schema source of truth: app/models.py -> init.sql parity"

requirements-completed: [QUICK-replace-migrations]

# Metrics
duration: 1min
completed: 2026-03-16
---

# Quick Task 260316-n8e: Replace Migrations with init.sql Summary

**Single init.sql with UUID PKs, JSONB content, and correct column set replaces stale two-file migration setup**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-16T23:46:15Z
- **Completed:** 2026-03-16T23:48:10Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 1 modified, 2 deleted)

## Accomplishments
- Created init.sql with DDL matching current app/models.py exactly (UUID PKs, JSONB content, title column, NOT NULL constraints, indexes)
- Updated docker-compose.yml to mount init.sql instead of old migration file
- Deleted stale migrations/ directory (001 with partitioning/BIGSERIAL, 002 never mounted)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create init.sql and update docker-compose.yml** - `88dff16` (feat)
2. **Task 2: Delete migrations/ directory** - `0ee9a43` (chore)

## Files Created/Modified
- `init.sql` - DDL for chats and messages tables matching SQLModel definitions
- `docker-compose.yml` - Updated volume mount from migrations/001 to init.sql
- `migrations/001_create_tables.sql` - Deleted (stale: BIGSERIAL, partitioning, TEXT content)
- `migrations/002_add_chat_columns.sql` - Deleted (never mounted, adds phrase/comment not title)

## Decisions Made
None - followed plan as specified.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Note: if a Docker volume with the old schema already exists, run `docker compose down -v` to clear pgdata before `docker compose up`.

## Next Phase Readiness
- init.sql is the single source of DDL, matching app/models.py
- No blockers or concerns

---
*Plan: quick/260316-n8e*
*Completed: 2026-03-16*
