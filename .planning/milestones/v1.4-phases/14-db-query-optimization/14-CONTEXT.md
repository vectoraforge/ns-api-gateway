# Phase 14: DB Query Optimization - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Every request handler makes at most 1 DB read call by folding ownership checks into data queries, deriving capacity from loaded data, and removing all orphaned code. API behavior unchanged — same responses, errors, status codes for all success and failure cases.

</domain>

<decisions>
## Implementation Decisions

### Zero-row handling
- All paths: 0 rows from JOIN with user_id filter → 404 (InvalidChatError)
- No fallback existence check needed — invariant guarantees every chat has >= 1 message
- Invariant enforced by replacing `create_chat` with `create_chat_with_messages` — single atomic operation
- Defer chat creation until after LLM call succeeds; `create_chat_with_messages` inserts chat + first message pair
- `get_db` dependency handles commits — no explicit `db.commit()` in Chats methods
- Single session per request (no split read/write sessions)

### load_history changes
- Gains `user_id` parameter; query uses JOIN with user_id filter
- Raises `InvalidChatError` when 0 rows returned (chat doesn't exist or wrong user)
- For new chats: skip `load_history` entirely — empty history `[]` assigned directly

### list_messages changes
- Gains `user_id` parameter; query uses JOIN with user_id filter
- Raises `InvalidChatError` when 0 rows AND no cursor (first page request)
- With cursor, 0 rows = end of pagination (not an error)

### delete_chat changes
- Renamed from `delete_chat_owned` to `delete_chat`
- Single `DELETE WHERE id AND user_id` with rowcount check
- Rowcount 0 → raises `InvalidChatError` (404)

### Capacity derivation
- Derive from loaded history in Python — count `len(history)` from loaded messages
- Trust pairing invariant (`save_messages` always writes human + assistant pair)
- Simplify config: replace `history_max_human_messages` + `history_max_assistant_messages` with single `history_max_messages`
- Config key: `history_max_messages`, default: `50` (conversation turns)
- Capacity check: `len(history) >= history_max_messages * 2`
- Check happens before LLM call: load history → check capacity → invoke LLM
- Capacity check is inline in `chat()` method (no private helper method)
- LLM context window same as capacity limit (no separate config)
- `ChatHistoryLimitError` constructor updated: `ChatHistoryLimitError(max_messages=N)` — opaque 400 unchanged

### Method naming
- `list_messages`, `load_history` keep current names (user_id is a parameter, not in the name)
- `delete_chat_owned` → `delete_chat`
- `create_chat` → `create_chat_with_messages` (new combined method)

### Router layer
- Router keeps direct access to `service.chats` methods (no service wrappers for list_messages, delete_chat)
- `POST /chats` goes through `service.chat()` as before

### Cleanup boundary
- Clean discovered orphans — follow dependency chain of removals, don't do sweeping cleanup
- `ChatOwnershipError` handler removal: `InvalidChatError` handler already covers all cases
- Tests rewritten to match new query patterns (not minimal adaptation)
- Integration tests (cross-user access) rewritten for query-level filtering
- YAML config updated: `history_max_messages: 50` replaces both old keys

### Claude's Discretion
- Exact SQL query construction for JOINs (SQLAlchemy expression style)
- `create_chat_with_messages` internal implementation (reuses `save_messages`)
- Test structure and assertion patterns
- Removal order across files

</decisions>

<specifics>
## Specific Ideas

- Chats can't exist without at least one message — `create_chat` always happens alongside first `save_messages`. This invariant eliminates JOIN empty-result ambiguity entirely.
- Pool size (5) matches LLM concurrency gate (5), so holding DB session during LLM call is acceptable.
- `create_chat_with_messages` reuses `save_messages` internally — DRY for message insertion logic.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_db` dependency (`app/dependencies.py:21-29`): already handles commit/rollback — Chats methods can drop explicit commits
- `save_messages` (`app/chats.py:100-108`): reused inside `create_chat_with_messages`
- `InvalidChatError` (`app/exceptions.py:36-39`): absorbs all cases previously split with `ChatOwnershipError`
- `_encode_cursor` / `_decode_cursor` (`app/chats.py:16-24`): unchanged, still used by `list_messages`

### Established Patterns
- Chats class: static data access methods on `AsyncSession` — pattern continues
- Router → `service.chats.*` direct access for simple queries
- Router → `service.chat()` for business logic (LLM invocation)
- Opaque error contract: 5 status codes, fixed error codes — no new codes needed

### Integration Points
- `app/config.py:71-79`: `AppConfig` — replace two history fields with one
- `app/main.py:56-65`: `ChatService` construction — update constructor args
- `config/config.yaml`: YAML config — replace two keys with one
- `tests/conftest.py`, `tests/unit/test_services.py`, `tests/integration/conftest.py`: ChatService fixtures — update constructor
- `app/errors.py`: error handler registration — remove `ChatOwnershipError` handler

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-db-query-optimization*
*Context gathered: 2026-03-04*
