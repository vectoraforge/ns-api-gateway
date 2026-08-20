# Phase 6: LLM Output Parsing Hardening - Research

**Researched:** 2026-02-27
**Domain:** LangChain structured output / OpenAI Structured Outputs API
**Confidence:** HIGH

## Summary

The current chain pipeline in `app/services.py` uses `prompt_template | self.llm | JsonOutputParser()`, which parses raw LLM text into a dict, then validates it with `AnalyzeResponse.model_validate()`. This is fragile: if the LLM returns malformed JSON (extra text, missing fields, wrong types), the `JsonOutputParser` raises `OutputParserException` and the entire request fails.

LangChain's `ChatOpenAI.with_structured_output()` eliminates this by using OpenAI's Structured Outputs API (`response_format` with `json_schema`), which applies constrained decoding at the API level -- the model is physically incapable of producing invalid JSON. The chain becomes `prompt_template | structured_llm`, where `structured_llm = self.llm.with_structured_output(AnalyzeResponseLLM, method='json_schema', strict=True)`, and the output is a validated Pydantic instance, not a raw dict.

All required infrastructure is already in place: `langchain-openai==1.1.10` supports `with_structured_output` with `method='json_schema'` and `strict=True`; `openai==2.21.0` handles the Pydantic-to-JSON-schema conversion (including `additionalProperties: false` and all-properties-required); `gpt-4o-mini` supports the Structured Outputs API. No new dependencies are needed.

**Primary recommendation:** Replace `JsonOutputParser()` with `self.llm.with_structured_output(AnalyzeResponseLLM, method='json_schema', strict=True)` in the chain, introduce `AnalyzeResponseLLM` Pydantic model in `app/schema.py`, and update test mocks to return `AnalyzeResponseLLM` instances.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LLM-01 | Replace `JsonOutputParser()` with `self.llm.with_structured_output(AnalyzeResponseLLM)` for schema-guaranteed LLM responses; introduce `AnalyzeResponseLLM` intermediate Pydantic model; update test mocks accordingly | Verified: `with_structured_output(schema, method='json_schema', strict=True)` on `langchain-openai==1.1.10` returns a `RunnableSequence` that pipes cleanly with `ChatPromptTemplate`. Output is a Pydantic instance, not a dict. See Architecture Patterns and Code Examples sections. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langchain-openai | 1.1.10 (installed) | `ChatOpenAI.with_structured_output()` | Built-in method on the LLM class; uses OpenAI's native Structured Outputs API |
| langchain-core | 1.2.14 (installed) | `ChatPromptTemplate`, LCEL piping | Already used throughout the codebase |
| openai | 2.21.0 (installed) | `to_strict_json_schema()` handles Pydantic-to-strict-schema conversion internally | Transparent to user code; handles `additionalProperties: false` and required-fields automatically |
| pydantic | 2.12+ (installed) | `AnalyzeResponseLLM` model definition | Already used for all schema definitions |

### Supporting
No additional libraries needed. Everything is already installed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `method='json_schema'` | `method='function_calling'` (the default) | `function_calling` uses tool-calling API which also works but `json_schema` uses OpenAI's constrained decoding for guaranteed schema compliance; `json_schema` is the newer, purpose-built API |
| `strict=True` | `strict=None` or `strict=False` | Without strict, OpenAI does not guarantee schema compliance -- model can still hallucinate extra fields or wrong types |

## Architecture Patterns

### Pattern 1: Structured LLM as Runnable (chain composition)
**What:** `with_structured_output()` returns a `RunnableSequence` (LLM + parser). It pipes directly with `ChatPromptTemplate` using LCEL `|` operator.
**When to use:** Whenever the LLM must return a known schema.
**Example:**
```python
# Source: Verified against langchain-openai 1.1.10 source + local testing
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

structured_llm = self.llm.with_structured_output(
    AnalyzeResponseLLM, method="json_schema", strict=True
)
chain = prompt_template | structured_llm  # No separate parser step
response = await chain.ainvoke(params)     # Returns AnalyzeResponseLLM instance
```

### Pattern 2: Separate LLM and API response schemas
**What:** `AnalyzeResponseLLM` represents what the LLM produces (issues, alternatives, assessment). `AnalyzeResponse` represents the API output (adds text, lang, chat_id). The LLM schema is a strict subset of the API schema.
**When to use:** When the API response enriches the LLM output with request-context fields.
**Example:**
```python
# app/schema.py
class AnalyzeResponseLLM(BaseModel):
    """Schema for LLM structured output -- fields the model generates."""
    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    alternatives: list[str] = Field(default_factory=list, description="Corrected alternatives")
    assessment: str = Field(..., description="Overall assessment of naturalness")

# In service, converting LLM output to API response:
response: AnalyzeResponseLLM = await self._invoke(chain, params)
return AnalyzeResponse(
    text=text, lang=lang, chat_id=chat_id,
    **response.model_dump()
)
```

### Pattern 3: Storing structured output as chat history
**What:** The current code does `assistant_payload = str(response)`. When `response` is a Pydantic model, `str()` produces `"issues=[Issue(...)] alternatives=[...] assessment='...'"` (repr-like), not dict-like output. Use `str(response.model_dump())` to preserve the existing format, or `response.model_dump_json()` for proper JSON.
**When to use:** Any place that serializes the LLM response to a string for storage.

### Anti-Patterns to Avoid
- **Calling `with_structured_output` in the hot path:** Create the structured LLM once during `__init__` or as a cached property, not on every `analyze()`/`chat()` call. The `with_structured_output()` method constructs a `RunnableSequence` which is cheap but unnecessary to rebuild repeatedly.
- **Using `include_raw=True` unless needed:** The raw response wrapper adds complexity. `include_raw=False` (the default) directly returns the Pydantic instance or raises on failure -- exactly what we want.
- **Keeping `JsonOutputParser` import:** After the switch, `JsonOutputParser` should be removed from `app/services.py` imports entirely.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON output validation | Manual `json.loads()` + `try/except` + `model_validate()` | `with_structured_output(schema, method='json_schema', strict=True)` | OpenAI's constrained decoding guarantees valid schema at the token-generation level |
| Schema-to-response-format conversion | Custom `model_json_schema()` + manual `additionalProperties` injection | The `openai` library's `to_strict_json_schema()` (called automatically) | Handles all strict-mode requirements: `additionalProperties: false`, all properties required, default removal |
| Output retry/repair | `OutputFixingParser`, regex extraction, JSON repair | `strict=True` structured output | Eliminates the root cause (malformed JSON) rather than treating symptoms |

**Key insight:** OpenAI's Structured Outputs API shifts JSON validation from client-side (after generation) to server-side (during generation). There is nothing to repair because the output is guaranteed valid.

## Common Pitfalls

### Pitfall 1: Chain returns Pydantic instance, not dict
**What goes wrong:** Code that does `{**response, "text": text}` (dict unpacking) breaks because `response` is now an `AnalyzeResponseLLM` instance, not a dict.
**Why it happens:** `with_structured_output` with a Pydantic class returns a Pydantic instance.
**How to avoid:** Use `response.model_dump()` to get a dict: `AnalyzeResponse(text=text, lang=lang, chat_id=chat_id, **response.model_dump())`.
**Warning signs:** `TypeError: 'AnalyzeResponseLLM' object is not a mapping` at runtime.

### Pitfall 2: Test mocks must return Pydantic instances, not dicts
**What goes wrong:** Tests that mock `chain.ainvoke()` to return a dict `{"issues": [], ...}` will fail because the real chain now returns `AnalyzeResponseLLM(...)`.
**Why it happens:** The mock's return type doesn't match the structured output's return type.
**How to avoid:** Update mock return values to `AnalyzeResponseLLM(issues=[], alternatives=[], assessment="...")`.
**Warning signs:** Tests pass but with wrong return types; or code expecting `.model_dump()` gets `AttributeError`.

### Pitfall 3: `str(response)` format change for chat history
**What goes wrong:** `str(pydantic_model)` produces `"issues=[Issue(...)] alternatives=[...] assessment='...'"` which differs from `str(dict)` output `"{'issues': [...], ...}"`.
**Why it happens:** Pydantic `__str__` uses repr-like format.
**How to avoid:** Either use `str(response.model_dump())` to preserve old format, or switch to `response.model_dump_json()` for cleaner JSON storage. Since this data is stored in chat history and fed back as `AIMessage` content, the exact format matters for conversation continuity -- but the LLM is flexible about this.
**Warning signs:** Subtle conversation quality changes in multi-turn chats (LOW risk).

### Pitfall 4: `method` default is `function_calling`, not `json_schema`
**What goes wrong:** Omitting `method='json_schema'` uses function/tool calling instead of OpenAI's Structured Outputs API.
**Why it happens:** `BaseChatOpenAI.with_structured_output` defaults to `method='function_calling'` (verified in source).
**How to avoid:** Always pass `method='json_schema'` explicitly.
**Warning signs:** Works functionally but does not get constrained decoding guarantees.

### Pitfall 5: Both `analyze()` and `chat()` methods build identical chains
**What goes wrong:** Forgetting to update one of the two methods. Both `analyze()` (line 129) and `chat()` (line 152) independently construct `prompt_template | self.llm | JsonOutputParser()`.
**Why it happens:** Code duplication.
**How to avoid:** Update both methods, or better, extract the chain construction to a single place.
**Warning signs:** One endpoint works with structured output, the other still uses `JsonOutputParser`.

## Code Examples

### Current code (to be replaced)
```python
# app/services.py lines 124-139 (analyze method)
prompt_template = ChatPromptTemplate.from_messages([
    ("system", self.prompt),
    MessagesPlaceholder("history"),
    ("human", "Analyze this phrase: {phrase}"),
])
chain = prompt_template | self.llm | JsonOutputParser()
# ...
response = await self._invoke(chain, {"lang": lang, "phrase": text, "history": history})
# ...
return AnalyzeResponse.model_validate({**response, "text": text, "lang": lang, "chat_id": chat_id})
```

### New code (structured output)
```python
# app/services.py -- after refactoring
from app.schema import AnalyzeResponseLLM

# In __init__ or as cached property:
prompt_template = ChatPromptTemplate.from_messages([
    ("system", self.prompt),
    MessagesPlaceholder("history"),
    ("human", "Analyze this phrase: {phrase}"),
])
structured_llm = self.llm.with_structured_output(
    AnalyzeResponseLLM, method="json_schema", strict=True
)
chain = prompt_template | structured_llm

# In analyze()/chat():
response: AnalyzeResponseLLM = await self._invoke(chain, {"lang": lang, "phrase": text, "history": history})

assistant_payload = str(response.model_dump())
self._ensure_message_size(assistant_payload, "assistant")
await self.chats.save_messages(db, chat_id, f"Analyze this phrase: {text}", assistant_payload)

return AnalyzeResponse(
    text=text, lang=lang, chat_id=chat_id,
    **response.model_dump()
)
```

### AnalyzeResponseLLM model
```python
# app/schema.py
class AnalyzeResponseLLM(BaseModel):
    """Schema for LLM structured output. Separate from AnalyzeResponse (API schema)
    because the LLM does not produce text, lang, or chat_id fields."""
    issues: list[Issue] = Field(default_factory=list, description="Issues found in the phrase")
    alternatives: list[str] = Field(default_factory=list, description="Corrected alternatives")
    assessment: str = Field(..., description="Overall assessment of naturalness")
```

### Updated test mock pattern
```python
# tests/unit/test_services.py
from app.schema import AnalyzeResponseLLM

# Old: mock returns dict
llm_response = {"issues": [...], "alternatives": [...], "assessment": "..."}

# New: mock returns AnalyzeResponseLLM instance
llm_response = AnalyzeResponseLLM(
    issues=[Issue(text_part="going to home", explanation="Should be 'going home'")],
    alternatives=["I am going home."],
    assessment="Minor grammar issue",
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `JsonOutputParser()` (parse raw text) | `with_structured_output(method='json_schema', strict=True)` | OpenAI Aug 2024, langchain-openai 0.1.x+ | Guaranteed valid JSON from API; no client-side parsing errors |
| `method='function_calling'` (default) | `method='json_schema'` (recommended for schema-guaranteed output) | langchain-openai 0.1.x+ | Constrained decoding vs. tool-call extraction |

**Deprecated/outdated:**
- `JsonOutputParser()` for structured LLM output: Works but fragile; `with_structured_output` is the recommended replacement
- `OutputFixingParser` / retry-parse loops: Treats symptoms; out of scope per REQUIREMENTS.md

## Open Questions

1. **Prompt JSON instructions redundancy**
   - What we know: The prompt in `config/prompt.txt` contains detailed JSON schema instructions ("always respond with a single JSON object matching this schema..."). With `method='json_schema'`, the schema is enforced by the API.
   - What's unclear: Whether removing the JSON schema portion from the prompt improves or degrades output quality. The prompt also contains analysis instructions (error types, multi-pass validation) that must stay.
   - Recommendation: Keep the prompt as-is for Phase 6. Removing JSON instructions is a separate optimization that should be tested empirically. The JSON instructions in the prompt don't conflict with the structured output API.

2. **Chat history format stability**
   - What we know: `str(response)` format changes from dict-like to Pydantic-repr-like. History is stored as text and fed back as `AIMessage` content.
   - What's unclear: Whether the format change affects multi-turn conversation quality.
   - Recommendation: Use `str(response.model_dump())` to preserve the existing format. This is the safest approach since it produces identical output to the current `str(dict)` behavior.

## Sources

### Primary (HIGH confidence)
- `langchain-openai==1.1.10` source code -- `BaseChatOpenAI.with_structured_output` implementation inspected via `inspect.getsource()`. Verified: method parameter default is `'function_calling'`; `method='json_schema'` with Pydantic class uses `_oai_structured_outputs_parser`; returns `RunnableSequence`.
- `openai==2.21.0` -- `to_strict_json_schema()` inspected. Verified: automatically adds `additionalProperties: false` and makes all properties `required` for strict mode.
- Local testing -- Chain composition `prompt | structured_llm` verified to produce `RunnableSequence` with `ainvoke` support.
- `_is_transient_error()` in `app/resilience.py` -- Verified: `ValidationError`, `ValueError`, `OpenAIRefusalError`, `OutputParserException` all return `False` (non-transient). Parsing failures will NOT trigger retry loop.

### Secondary (MEDIUM confidence)
- OpenAI Structured Outputs API documentation -- `gpt-4o-mini` listed as supported model.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries installed and source-verified locally
- Architecture: HIGH - Chain composition pattern tested locally; return types verified
- Pitfalls: HIGH - Each pitfall identified by reading actual source code and testing behavior

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable libraries, unlikely to change)
