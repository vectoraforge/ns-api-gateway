# Phase 32: Rewrite Models to Match Prompt Schema - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 32-rewrite-models-in-this-file-according-to-the-new-schema-in-the-new-config-prompt-txt
**Areas discussed:** Output model structure, Input model structure, Reject handling, API contract impact, Existing data migration, Error code for out_of_scope, ContentUnion discriminator, with_structured_output / LLM validation, Where validation models live, LLM input construction, History serialization, Optional field serialization, models/ re-exports, Message column type

---

## Output Model Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Discriminated union | Three separate models (AnalyzeContent, FollowUpContent, RejectContent) with resolved_mode discriminator | ✓ |
| Single model + resolved_mode | Keep one AIContent, add resolved_mode field, keep issues/suggestions optional | |
| You decide | Claude picks | |

**User's choice:** Discriminated union
**Notes:** None

### Follow-up: Issues/suggestions optionality

| Option | Description | Selected |
|--------|-------------|----------|
| Always present, possibly empty | issues: list[Issue] and suggestions: list[str]. Empty list when no issues | ✓ |
| Optional (None when absent) | issues: list[Issue] | None = None | |

**User's choice:** Always present, possibly empty
**Notes:** Matches prompt schema which always includes the keys

---

## Input Model Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Discriminated union | Two models: AnalyzeInput (mode, phrase, context?) and FollowUpInput (mode, question) | ✓ |
| Single model with mode | One HumanContent with mode field and all fields optional | |
| You decide | Claude picks | |

**User's choice:** Discriminated union
**Notes:** None

---

## Reject Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Store as normal message | RejectContent stored in DB like any other AI message | |
| Raise as error | Convert reject to OutOfScopeError, no message persisted | ✓ |
| Store + flag | Store as message with rejected boolean flag | |

**User's choice:** Raise as error
**Notes:** Client gets 400 with "out_of_scope" as error code. Don't store the human message that produced this error in the database.

---

## API Contract Impact

| Option | Description | Selected |
|--------|-------------|----------|
| Rename API fields too | ChatRequest.comment → context, MessageRequest.comment → question. Breaking change. | ✓ |
| Keep API stable, map internally | Keep comment fields, service maps internally | |

**User's choice:** Rename API fields too
**Notes:** None

---

## Existing Data Migration

**User's clarification:** "Don't worry about the existing data, the database will be wiped and recreated"
**Notes:** No migration needed. Clean slate.

---

## Error Code for out_of_scope

| Option | Description | Selected |
|--------|-------------|----------|
| New 'out_of_scope' code | Add to ErrorCode Literal. Clients can distinguish bad input from out-of-scope. | ✓ |
| Reuse 'invalid_request' | No expansion. OutOfScopeError uses invalid_request. | |

**User's choice:** New 'out_of_scope' code
**Notes:** None

---

## ContentUnion Discriminator

**User's clarification:** "Shouldn't it choose between 5 models?" — pointed out the discriminator should route to all 5 concrete types, not just human/ai categories.

**Resolution:** Moot — user decided to remove all content models and use plain dict. No discriminator needed.

---

## LLM Validation (with_structured_output)

| Option | Description | Selected |
|--------|-------------|----------|
| Manual dispatch in service | Check resolved_mode, raise on reject, validate against specific model | ✓ |
| Pydantic field discriminator | AIResponse union with Discriminator('resolved_mode') | |

**User's choice:** Manual dispatch in service
**Notes:** No discriminator needed since reject is handled before validation

---

## Where Validation Models Live

**User's clarification:** "Keep them in models/llm.py and move schemas.py to models/api.py"
**Notes:** Not a choice from presented options — user specified exact file layout.

---

## LLM Input Construction

| Option | Description | Selected |
|--------|-------------|----------|
| Build via models, store as dict | Use AnalyzeInput/FollowUpInput to construct, model_dump() to get dict | ✓ |
| Build dicts directly | No model instantiation, construct dicts by hand | |

**User's choice:** Build via models, store as dict
**Notes:** None

---

## History Serialization

| Option | Description | Selected |
|--------|-------------|----------|
| json.dumps | Straightforward dict → JSON string | |
| You decide | Claude picks best serialization approach | ✓ |

**User's choice:** You decide
**Notes:** "Find a faster json serializer, minimal."

---

## Optional Field Serialization

**User's clarification:** Asked "What would be better for LLM prompt parsing?" — Claude recommended exclude_none=True since prompt defines context as optional (absent, not null), less noise for the model.
**Notes:** Going with model_dump(exclude_none=True)

---

## models/ Re-exports

| Option | Description | Selected |
|--------|-------------|----------|
| Re-export api.py only | API schemas broadly used, LLM models imported directly | |
| Re-export both | Both api.py and llm.py re-exported from __init__.py | ✓ |
| No re-exports for new files | Only keep existing DB model re-exports | |

**User's choice:** Re-export both
**Notes:** None

---

## Message Column Type

| Option | Description | Selected |
|--------|-------------|----------|
| Plain JSONB with dict type | content: dict = Field(sa_type=JSONB). No custom type decorator. | ✓ |
| You decide | Claude picks | |

**User's choice:** Plain JSONB with dict type
**Notes:** None

---

## Claude's Discretion

- Fast JSON serializer choice for history serialization (orjson or similar)

## Deferred Ideas

None — discussion stayed within phase scope.
