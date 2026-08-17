---
phase: quick-phase-1-gaps
plan: 1
subsystem: auth, chats, services, router
tags: [exception-handling, auth, ownership, gap-closure]
requirements: [EXCP-01, EXCP-02]
dependency_graph:
  requires: []
  provides: [ExpiredTokenError raise site in auth, ChatOwnershipError raise site in chats/router/service]
  affects: [app/auth.py, app/chats.py, app/routers/prompts.py, app/services.py]
tech_stack:
  added: []
  patterns: [raise-before-return ownership check, two-phase fetch (exists then owner check)]
key_files:
  created: []
  modified:
    - app/auth.py
    - app/chats.py
    - app/routers/prompts.py
    - app/services.py
    - tests/unit/test_exception_handlers.py
    - tests/unit/test_services.py
decisions:
  - exp claim check added before user_id check so expiry takes precedence over missing user identity
  - get_chat_owned fetches by chat_id only first, then checks user_id — two queries but enables clear error distinction
  - delete_chat_owned follows identical fetch-then-check pattern for consistency
  - InvalidChatError removed from services.py imports (no longer raised directly after get_chat_owned delegation)
  - ChatOwnershipError import added but unused directly in prompts.py (exceptions bubble from chats layer)
metrics:
  duration: ~10 min
  completed: 2026-02-27
  tasks_completed: 2
  files_modified: 6
---

# Phase quick-phase-1-gaps Plan 1: Implement Phase 1 Gaps Summary

**One-liner:** Wire ExpiredTokenError in auth JWT validation and ChatOwnershipError via two-phase ownership fetch in chats, distinguishing not-found from wrong-owner across router and service layers.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire ExpiredTokenError in auth.py | e30de72 | app/auth.py, tests/unit/test_exception_handlers.py |
| 2 | Wire ChatOwnershipError in chats, router, and service | 86aec52 | app/chats.py, app/routers/prompts.py, app/services.py, tests/unit/test_services.py |

## What Was Built

### Task 1: ExpiredTokenError in auth

`app/auth.py` now checks the `exp` claim after decoding the JWT payload. If `exp` is present and less than `time.time()`, it raises `ExpiredTokenError()` before checking `user_id`. Tokens without an `exp` field continue to work (backward-compatible).

New test `test_expired_token_returns_401` crafts a token with `"exp": 1` and asserts the response is 401 with `{"status": 401, "error": ...}`.

### Task 2: ChatOwnershipError in chats/router/service

Two new methods added to `Chats`:

- `get_chat_owned(db, chat_id, user_id)` — fetches by `chat_id` only, then checks ownership. Raises `InvalidChatError` if not found, `ChatOwnershipError` if wrong owner.
- `delete_chat_owned(db, chat_id, user_id)` — same two-phase pattern for the delete path.

`services._get_chat_lang` now calls `get_chat_owned` directly — no post-call None check needed.

Router list route calls `get_chat_owned` (no explicit raise needed). Router delete route calls `delete_chat_owned` (no explicit raise needed).

## Verification

```
tests/unit/test_exception_handlers.py::test_handler[expired_token-exc2-401] PASSED
tests/unit/test_exception_handlers.py::test_expired_token_returns_401 PASSED
tests/unit/test_exception_handlers.py (all 18) PASSED
tests/unit/test_services.py (all 11) PASSED
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_services.py mocks to use get_chat_owned**
- **Found during:** Task 2
- **Issue:** `test_services.py` mocked `chats.get_chat` for the `_get_chat_lang` path. After `_get_chat_lang` was changed to call `get_chat_owned`, 4 tests broke: `test_with_existing_chat_id`, `test_invalid_chat_id` (both TestAnalyze and TestChat), and `test_success` (TestChat).
- **Fix:** Added `get_chat_owned = AsyncMock(return_value=None)` to the `mock_chats` fixture; updated the 4 affected test cases to set `mock_chats.get_chat_owned.return_value` / `.side_effect` instead of `mock_chats.get_chat`.
- **Files modified:** tests/unit/test_services.py
- **Commit:** 86aec52

## Self-Check: PASSED

- app/auth.py: FOUND
- app/chats.py: FOUND
- app/routers/prompts.py: FOUND
- app/services.py: FOUND
- 1-SUMMARY.md: FOUND
- commit e30de72: FOUND
- commit 86aec52: FOUND
