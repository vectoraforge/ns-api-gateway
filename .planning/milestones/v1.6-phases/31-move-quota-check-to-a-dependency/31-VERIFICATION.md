---
phase: 31-move-quota-check-to-a-dependency
verified: 2026-03-25T09:00:00Z
status: passed
score: 6/6 must-haves verified
---

# Phase 31: Move Quota Check to a Dependency Verification Report

**Phase Goal:** Quota enforcement extracted from ChatService into a centralized `require_quota` FastAPI dependency, applied to chat-mutating endpoints only
**Verified:** 2026-03-25T09:00:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `require_quota` async dependency exists in `dependencies.py`, calls `UsageDB.try_increment`, raises `QuotaExceededError` on failure | VERIFIED | `dependencies.py` lines 70-78: async function calls `usage_db.try_increment` and raises `QuotaExceededError("Monthly quota exceeded")` |
| 2 | `ChatService` has no `quotas`, `usage_db`, or `try_increment` references | VERIFIED | grep for `quotas\|usage_db\|try_increment\|QuotaExceededError\|SubscriptionPlan` in `services/chats.py` returns zero matches |
| 3 | POST /chats and POST /chats/{chat_id} routes include `_quota: None = Depends(require_quota)` | VERIFIED | `routers/chats.py` line 16 and line 29 both contain `_quota: None = Depends(require_quota)` |
| 4 | GET and DELETE chat routes do NOT include `require_quota` | VERIFIED | `list_chats` (line 39), `get_chat_messages` (line 48), `delete_chat` (line 61) have no `_quota` parameter or `require_quota` reference |
| 5 | Full unit test suite passes with zero failures | VERIFIED | `pytest tests/unit/ -x -v` exits 0: 148 passed, 0 failures (run during verification) |
| 6 | SubscriptionService still uses `UsageDB.reset_usage` independently (unchanged) | VERIFIED | `subscriptions.py` line 66: `self.usage_db = UsageDB(db)`, line 163: `await self.usage_db.reset_usage(subscription.user_id, month)` |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/app/dependencies.py` | `require_quota` dependency function | VERIFIED | Lines 70-78: async function with correct signature `(user, db, config)`, uses `UsageDB.try_increment`, raises `QuotaExceededError` |
| `src/nativespeaker/api/services/chats.py` | ChatService without quota logic | VERIFIED | `__init__` has 5 params (db, llm_service, examples, messages_limit, chats_limit). Zero references to quotas, usage_db, try_increment, QuotaExceededError, SubscriptionPlan |
| `src/nativespeaker/api/routers/chats.py` | Routes with require_quota dependency | VERIFIED | `require_quota` imported at line 5; `Depends(require_quota)` in `create_chat` (line 16) and `send_message` (line 29) only |
| `tests/unit/conftest.py` | Updated fixtures without quota mocking in ChatService | VERIFIED | `service` fixture (line 143) creates ChatService without `quotas` or `usage_db`; `client` fixture (line 186) has `require_quota` override |
| `tests/unit/test_usage.py` | Quota tests targeting the dependency | VERIFIED | `TestRequireQuota` (4 tests) and `TestQuotaViaHTTP` (2 tests) target `require_quota` directly; no ChatService quota testing |
| `tests/unit/test_services.py` | ChatService tests with no quota references | VERIFIED | Zero references to `quota`, `usage_db`, `try_increment`, or `QuotaExceededError` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `routers/chats.py` | `dependencies.py` | `Depends(require_quota)` in POST route signatures | VERIFIED | Lines 16, 29: `_quota: None = Depends(require_quota)` |
| `dependencies.py` | `database/usage.py` | `UsageDB(db).try_increment` in require_quota | VERIFIED | Line 76-77: `usage_db = UsageDB(db)` then `await usage_db.try_increment(user.id, month, monthly_quota)` |
| `conftest.py` | `dependencies.py` | `dependency_overrides[require_quota] = lambda: None` | VERIFIED | Line 186: `app.dependency_overrides[require_quota] = lambda: None` |
| `test_usage.py` | `dependencies.py` | Direct invocation of require_quota function | VERIFIED | Lines 49, 57, 66, 79: `await require_quota(user=..., db=..., config=...)` |

### Data-Flow Trace (Level 4)

Not applicable -- this phase refactors a side-effect guard dependency (quota enforcement), not a data-rendering artifact.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full unit suite green | `pytest tests/unit/ -x -v` | 148 passed, 0 failures, 1.64s | PASS |
| require_quota importable and async | `python -c "import inspect; from nativespeaker.api.app.dependencies import require_quota; assert inspect.iscoroutinefunction(require_quota)"` | (verified via test suite) | PASS |
| ChatService has no quotas param | `python -c "import inspect; from nativespeaker.api.services.chats import ChatService; assert 'quotas' not in inspect.signature(ChatService.__init__).parameters"` | (verified via test suite) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEP-01 | 31-01, 31-02 | `require_quota` dependency raises `QuotaExceededError` when `try_increment` returns False | SATISFIED | `dependencies.py` line 78; `test_usage.py` `test_require_quota_raises_when_exhausted` passes |
| DEP-02 | 31-01, 31-02 | `require_quota` dependency passes silently when under quota | SATISFIED | `dependencies.py` returns None; `test_usage.py` `test_require_quota_passes_when_under_limit` passes |
| DEP-03 | 31-01, 31-02 | POST /chats returns 429 when quota exhausted (via dependency, not ChatService) | SATISFIED | `routers/chats.py` line 16: `_quota: None = Depends(require_quota)`; `test_usage.py` `test_create_chat_returns_429_when_quota_exhausted` passes |
| DEP-04 | 31-01, 31-02 | POST /chats/{chat_id} returns 429 when quota exhausted (via dependency, not ChatService) | SATISFIED | `routers/chats.py` line 29: `_quota: None = Depends(require_quota)`; `test_usage.py` `test_send_message_returns_429_when_quota_exhausted` passes |
| DEP-05 | 31-01, 31-02 | ChatService has no quotas, usage_db, or try_increment references | SATISFIED | grep returns zero matches for any of those terms in `services/chats.py` |
| DEP-06 | 31-02 | SubscriptionService still works with UsageDB.reset_usage (unchanged) | SATISFIED | `subscriptions.py` lines 66, 163: `self.usage_db = UsageDB(db)` and `await self.usage_db.reset_usage(...)` present; subscription tests pass |

No orphaned requirements found -- all 6 DEP-* requirements mapped in REQUIREMENTS.md to Phase 31 are covered by plan frontmatter and verified above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | - |

No TODO, FIXME, PLACEHOLDER, or stub patterns found in any modified file.

### Human Verification Required

None -- all truths are verifiable programmatically.

### Gaps Summary

No gaps found. All 6 observable truths verified, all 6 artifacts pass three-level checks (exist, substantive, wired), all 4 key links confirmed, all 6 requirements satisfied, 148 unit tests pass, zero anti-patterns detected.

---

_Verified: 2026-03-25T09:00:00Z_
_Verifier: Claude (gsd-verifier)_
