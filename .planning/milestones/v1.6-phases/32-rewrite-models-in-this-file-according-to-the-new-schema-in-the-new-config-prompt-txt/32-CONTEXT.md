# Phase 32: Rewrite Models to Match Prompt Schema - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Align all Pydantic content models with the LLM input/output contract defined in `config/prompt.txt`. Reorganize model files: delete `content.py`, move `schema.py` to `models/api.py`, create `models/llm.py` for LLM validation models. Internal content representation becomes plain `dict`. Add `OutOfScopeError` for LLM reject responses.

</domain>

<decisions>
## Implementation Decisions

### Output Model Structure
- **D-01:** Discriminated union with 3 separate response models: `AnalyzeResponse` (resolved_mode="analyze", response, issues, suggestions), `FollowUpResponse` (resolved_mode="follow_up", response), `RejectResponse` (resolved_mode="reject", response)
- **D-02:** `AnalyzeResponse.issues` and `AnalyzeResponse.suggestions` are always present (non-optional), possibly empty lists. No `None` values.

### Input Model Structure
- **D-03:** Discriminated union with 2 input models: `AnalyzeInput` (mode="analyze", phrase, context?) and `FollowUpInput` (mode="follow_up", question)
- **D-04:** These models are used to construct and validate LLM input, then `.model_dump(exclude_none=True)` produces the dict stored as content

### Internal Content Representation
- **D-05:** `Message.content` is a plain `dict` everywhere — DB column, service layer, API responses. No Pydantic model wrapping at the persistence or transport layer.
- **D-06:** `Message.content` column defined as `dict = Field(sa_type=JSONB)`. `PydanticJSONB` and `ContentUnion` deleted entirely.
- **D-07:** `MessageResponse.content` is `dict` — no typed content in API responses. OpenAPI shows it as `object`.

### Reject Handling
- **D-08:** LLM `resolved_mode="reject"` raises `OutOfScopeError` → HTTP 400 with `out_of_scope` error code
- **D-09:** On reject, neither the human message nor the AI response is persisted to the database
- **D-10:** `out_of_scope` added as new value to `ErrorCode` Literal

### API Contract Changes
- **D-11:** `ChatRequest.comment` renamed to `ChatRequest.context` (optional str, max 4096)
- **D-12:** `MessageRequest.comment` renamed to `MessageRequest.question` (required str, max 4096)
- **D-13:** Breaking API change accepted — no backward compatibility needed

### File Reorganization
- **D-14:** `schema.py` moved to `models/api.py`
- **D-15:** New `models/llm.py` for LLM validation models (`Issue`, `AnalyzeInput`, `FollowUpInput`, `AnalyzeResponse`, `FollowUpResponse`, `RejectResponse`)
- **D-16:** `models/content.py` deleted entirely
- **D-17:** `models/__init__.py` re-exports from both `api.py` and `llm.py`

### LLM Validation
- **D-18:** Manual dispatch on `response["resolved_mode"]` in `ChatService.ask_llm` — check for reject first, then validate against `AnalyzeResponse` or `FollowUpResponse`. No union type or TypeAdapter needed.
- **D-19:** LLM input built via `AnalyzeInput`/`FollowUpInput` models, then `.model_dump(exclude_none=True)` to get dict. Optional fields (like `context`) excluded when None to match prompt spec.

### Serialization
- **D-20:** History messages serialized with a fast minimal JSON serializer (e.g., `orjson`) since content is now plain dict

### Database
- **D-21:** Database will be wiped and recreated — no data migration needed for existing JSONB content

### Claude's Discretion
- Choice of fast JSON serializer for history serialization (orjson or similar minimal dependency)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### LLM Contract
- `config/prompt.txt` — Defines the exact input/output JSON schemas the LLM expects and returns. All model shapes must match this file.

### Current Implementation (to be modified)
- `src/nativespeaker/api/models/content.py` — Current content models to be deleted
- `src/nativespeaker/api/schema.py` — Current API schemas to be moved to models/api.py
- `src/nativespeaker/api/services/chats.py` — ChatService.ask_llm needs LLM validation rewrite
- `src/nativespeaker/api/services/llm.py` — LLM chain (JsonOutputParser stays as-is)
- `src/nativespeaker/api/exceptions.py` — Add OutOfScopeError and out_of_scope ErrorCode
- `src/nativespeaker/api/models/chats.py` — Message.content column type change
- `src/nativespeaker/api/models/__init__.py` — Re-export updates
- `src/nativespeaker/api/routers/chats.py` — Import path updates, field renames

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ErrorCode` Literal and `ServiceError` hierarchy in `exceptions.py` — `OutOfScopeError` follows the same pattern
- `JsonOutputParser` in `llm.py` already returns raw dict — aligns with new approach

### Established Patterns
- Exception classes carry HTTP metadata (`status_code`, `error_code`) — single handler reads class attrs
- All dependencies in `app/dependencies.py` with `Depends()`-only routes
- `models/__init__.py` uses re-export pattern for clean imports

### Integration Points
- `ChatService.ask_llm` — primary integration point for LLM response validation and reject handling
- `ChatService.create_chat` / `send_message` — build HumanContent → AnalyzeInput/FollowUpInput
- `chats.py` router — import path changes from schema → models.api
- `app/dependencies.py` — import path changes
- All test files referencing `HumanContent`, `AIContent`, `schema.py` imports

</code_context>

<specifics>
## Specific Ideas

No specific requirements — standard implementation following the prompt.txt contract exactly.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 32-rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt*
*Context gathered: 2026-03-25*
