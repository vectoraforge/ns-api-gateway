---
phase: quick-phase-1-gaps
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - app/auth.py
  - app/chats.py
  - app/routers/prompts.py
  - app/services.py
  - tests/unit/test_exception_handlers.py
autonomous: true
requirements: [EXCP-01, EXCP-02]

must_haves:
  truths:
    - "A request with an expired JWT (exp claim in the past) receives a 401 ExpiredTokenError, not 200"
    - "A request from user A accessing user B's existing chat receives a 404 ChatOwnershipError, not InvalidChatError"
    - "A request accessing a chat that does not exist at all receives a 404 InvalidChatError"
    - "All 17 existing exception handler tests continue to pass"
  artifacts:
    - path: "app/auth.py"
      provides: "exp claim check raising ExpiredTokenError"
      contains: "ExpiredTokenError"
    - path: "app/chats.py"
      provides: "get_chat_owned helper that distinguishes not-found from wrong-owner"
      exports: ["get_chat_owned"]
    - path: "app/routers/prompts.py"
      provides: "ChatOwnershipError raise sites replacing InvalidChatError for ownership failures"
    - path: "app/services.py"
      provides: "ChatOwnershipError raise site replacing InvalidChatError for ownership failures"
    - path: "tests/unit/test_exception_handlers.py"
      provides: "Integration tests confirming expired token returns 401 and ownership mismatch returns 404"
  key_links:
    - from: "app/auth.py"
      to: "app/exceptions.py"
      via: "raises ExpiredTokenError when payload exp < time.time()"
      pattern: "ExpiredTokenError"
    - from: "app/chats.py"
      to: "app/exceptions.py"
      via: "get_chat_owned raises ChatOwnershipError on mismatch"
      pattern: "ChatOwnershipError"
    - from: "app/routers/prompts.py"
      to: "app/chats.py"
      via: "calls get_chat_owned instead of get_chat"
      pattern: "get_chat_owned"
---

<objective>
Wire the two Phase 1 exception raise sites that exist only as dead code: `ExpiredTokenError` in auth and `ChatOwnershipError` in the router/service layer.

Purpose: Phase 1 VERIFICATION.md scores 5/7 because these two exceptions have handlers and tests but no production raise sites. This plan closes both gaps.
Output: `auth.py` rejects expired tokens with 401; the router/service distinguishes ownership failures (404 ChatOwnershipError) from genuinely missing chats (404 InvalidChatError).
</objective>

<execution_context>
@/Users/otto/.claude/get-shit-done/workflows/execute-plan.md
@/Users/otto/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/STATE.md

<interfaces>
<!-- Key contracts the executor needs. No codebase exploration required. -->

From app/exceptions.py:
```python
class ExpiredTokenError(AuthError):
    def __init__(self):
        super().__init__("Expired token")

class ChatOwnershipError(ServiceError):
    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")

class InvalidChatError(ServiceError):
    def __init__(self, chat_id):
        self.chat_id = chat_id
        super().__init__(f"Chat '{chat_id}' not found")
```

From app/auth.py (current get_user_id — lines to modify):
```python
async def get_user_id(authorization: str | None = Header(None)) -> str:
    ...
    try:
        payload = _decode_jwt_payload(token)
    except Exception:
        raise InvalidTokenError() from None
    user_id = payload.get("user_id")
    if not user_id:
        raise InvalidTokenError()
    return str(user_id)
    # MISSING: no exp claim check between payload decode and user_id check
```

From app/chats.py (current get_chat):
```python
async def get_chat(self, db: AsyncSession, chat_id: UUID, user_id: str | None = None) -> dict | None:
    if user_id is None:
        chat = await db.get(Chat, chat_id)
    else:
        statement = select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
        chat = (await db.exec(statement)).first()
    return {"id": chat.id, "lang": chat.lang, "user_id": chat.user_id} if chat else None
    # get_chat with user_id returns None for BOTH "not found" and "wrong owner" — indistinguishable
```

From app/routers/prompts.py (raise sites to fix):
- Line 74: `raise InvalidChatError(chat_id)` — after get_chat returns None (could be ownership failure)
- Line 105: `raise InvalidChatError(chat_id)` — after delete_chat returns False (could be ownership failure)

From app/services.py:
- Line 162 (_get_chat_lang): `raise InvalidChatError(chat_id)` — after get_chat returns None
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Wire ExpiredTokenError in auth.py</name>
  <files>app/auth.py</files>
  <action>
Import `time` and `ExpiredTokenError` in `app/auth.py`. After successfully decoding the payload dict, read `payload.get("exp")`. If `exp` is present and `exp < time.time()`, raise `ExpiredTokenError()`. Place this check BEFORE the `user_id` check so expiry is evaluated first.

The resulting check order in `get_user_id` after the try/except block:
1. Check `exp` claim — raise `ExpiredTokenError()` if expired
2. Check `user_id` — raise `InvalidTokenError()` if missing

Add a dep_client integration test to `tests/unit/test_exception_handlers.py` that crafts a token with `"exp": 1` (Unix epoch, definitely expired) and `"user_id": "u1"`, sends it to `/protected`, and asserts 401 with `{"status": 401, "error": ...}`.

Helper to craft the test token (add inside the test or as a module-level helper):
```python
import base64, json, time as _time
def _make_token(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{encoded}.sig"
```

The existing `test_valid_bearer_token_resolves_user` already uses a similar pattern — factor or duplicate as appropriate, keep it minimal.
  </action>
  <verify>pytest tests/unit/test_exception_handlers.py -x -q 2>&1 | tail -5</verify>
  <done>All 18 tests pass (17 existing + 1 new expired-token test). A token with exp=1 returns 401; a token with no exp field continues to return 200 for valid user_id.</done>
</task>

<task type="auto">
  <name>Task 2: Wire ChatOwnershipError in chats, router, and service</name>
  <files>app/chats.py, app/routers/prompts.py, app/services.py</files>
  <action>
**Problem:** `get_chat(db, chat_id, user_id=user_id)` returns `None` whether the chat doesn't exist or belongs to another user — callers cannot distinguish the two cases.

**Solution:** Add `get_chat_owned` method to `Chats` in `app/chats.py`. This method fetches by `chat_id` only first, then checks ownership:

```python
async def get_chat_owned(
        self, db: AsyncSession, chat_id: UUID, user_id: str
) -> dict:
    """Return chat dict if owned by user_id. Raise ChatOwnershipError if exists but wrong owner,
    InvalidChatError if it doesn't exist."""
    from exceptions import ChatOwnershipError, InvalidChatError
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise InvalidChatError(chat_id)
    if chat.user_id != user_id:
        raise ChatOwnershipError(chat_id)
    return {"id": chat.id, "lang": chat.lang, "user_id": chat.user_id}
```

Import `ChatOwnershipError` and `InvalidChatError` at the top of `chats.py` (move the import from inside the method to module level).

**Update `app/services.py` `_get_chat_lang`:**
Replace:
```python
chat = await self.chats.get_chat(db, chat_id, user_id=user_id)
if not chat:
    raise InvalidChatError(chat_id)
return chat["lang"]
```
With:
```python
chat = await self.chats.get_chat_owned(db, chat_id, user_id)
return chat["lang"]
```
Remove the `InvalidChatError` import from services.py only if it is no longer used elsewhere (it is still used in the except-block path — check first, leave if still used).

**Update `app/routers/prompts.py` list_chat_messages (line 72-74):**
Replace:
```python
chat = await service.chats.get_chat(db, chat_id, user_id=user_id)
if not chat:
    raise InvalidChatError(chat_id)
```
With:
```python
chat = await service.chats.get_chat_owned(db, chat_id, user_id)
```
Add `ChatOwnershipError` to the imports at top of `prompts.py`. Remove the now-unused `InvalidChatError` import only if nothing else in the file uses it (the delete path at line 105 still raises `InvalidChatError` — see next paragraph).

**Update `app/routers/prompts.py` delete_chat (line 103-105):**
`delete_chat` in chats.py already filters by `user_id`, returning `False` for both "not found" and "wrong owner". Update `delete_chat` in `chats.py` similarly — rename or add a `delete_chat_owned` that distinguishes:

```python
async def delete_chat_owned(self, db: AsyncSession, chat_id: UUID, user_id: str) -> None:
    """Delete chat owned by user_id. Raise ChatOwnershipError if exists but wrong owner,
    InvalidChatError if doesn't exist."""
    from exceptions import ChatOwnershipError, InvalidChatError
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise InvalidChatError(chat_id)
    if chat.user_id != user_id:
        raise ChatOwnershipError(chat_id)
    await db.delete(chat)
    await db.commit()
```

Update `prompts.py` delete_chat route to call `service.chats.delete_chat_owned(db, chat_id, user_id)` and remove the `if not deleted: raise InvalidChatError(chat_id)` block. Update the response to `return Response(status_code=204)` unchanged.

**Note:** Keep the original `delete_chat` method on `Chats` if it is tested elsewhere. Check tests first. If no test covers it directly, removing is safe — but safer to keep both.

All imports needed in `prompts.py`:
- Add `ChatOwnershipError` to the existing `from app.exceptions import ...` line.
  </action>
  <verify>pytest tests/unit/test_exception_handlers.py -x -q 2>&1 | tail -5</verify>
  <done>
- All 18 tests pass (no regressions).
- `app/chats.py` exports `get_chat_owned` and `delete_chat_owned`.
- `app/services.py._get_chat_lang` calls `get_chat_owned` (no post-call None check).
- `app/routers/prompts.py` list route calls `get_chat_owned`; delete route calls `delete_chat_owned`.
- Neither `prompts.py` nor `services.py` raises `InvalidChatError` directly for the ownership-checked paths.
  </done>
</task>

</tasks>

<verification>
```bash
pytest tests/unit/test_exception_handlers.py -v 2>&1 | tail -25
```

All tests pass. Confirm:
- `test_expired_token_returns_401` (new) — passes
- All 13 parametrized handler cases — pass
- All 3 dep_client integration tests — pass
- `test_validation_error_handler` — passes
</verification>

<success_criteria>
1. A token with `"exp": 1` returns `{"status": 401, "error": "Expired token"}` from `/protected`
2. A token with no `exp` field and valid `user_id` continues to return 200 (backward-compatible)
3. `Chats.get_chat_owned` raises `ChatOwnershipError` when chat exists but `user_id` mismatches
4. `Chats.get_chat_owned` raises `InvalidChatError` when chat does not exist at all
5. `Chats.delete_chat_owned` applies the same distinction for the delete path
6. All 18+ pytest tests pass with no regressions
</success_criteria>

<output>
After completion, create `.planning/quick/1-implement-phase-1-gaps/1-SUMMARY.md` following the summary template.
</output>
