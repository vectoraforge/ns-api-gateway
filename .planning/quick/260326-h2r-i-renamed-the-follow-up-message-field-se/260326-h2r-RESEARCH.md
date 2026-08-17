# Quick Task: Fix tests after follow-up field rename - Research

**Researched:** 2026-03-26
**Domain:** Test fixes after `question` -> `message` field rename
**Confidence:** HIGH

## Summary

Commit `bdf5d45` renamed the `question` field to `message` in `MessageRequest` (API), `FollowUpInput` (LLM), and all downstream code. The rename itself was applied correctly across source and test files. However, two test assertions were incorrectly changed by overzealous find-and-replace -- the word `content` or `content` was changed to `message` in contexts where `content` is an unrelated attribute (not the renamed field).

**Primary recommendation:** Revert two incorrect renames in unit tests; the e2e failure is pre-existing and unrelated.

## Project Constraints (from CLAUDE.md)

- Opening delimiter alignment style for multiline constructs
- Don't use string-based module references in Python tests
- Don't commit .planning dir

## Failing Tests

### Unit Tests (2 failures)

**1. `tests/unit/test_services.py::TestCreateChat::test_new_chat_with_context` (line 57)**

```python
# CURRENT (broken):
assert human_msg.message["context"] == "Is this too formal?"

# FIX (revert to):
assert human_msg.content["context"] == "Is this too formal?"
```

**Root cause:** `Message` is a SQLModel/Pydantic model with a `content` field (JSONB dict). The rename commit incorrectly changed `.content` to `.message`. The `content` attribute on `Message` has nothing to do with the `question -> message` rename -- it stores the full message payload dict.

**2. `tests/unit/test_webhooks.py::TestAppleWebhook::test_receives_notification` (line 16)**

```python
# CURRENT (broken):
assert response.message == b""

# FIX (revert to):
assert response.content == b""
```

**Root cause:** `response` is an httpx `Response` object. Its `.content` attribute returns raw bytes. The rename commit incorrectly changed `.content` to `.message`. httpx `Response` has no `.message` attribute.

### E2E Tests (1 failure -- PRE-EXISTING, NOT caused by rename)

**`tests/e2e/test_chats.py::TestCreateChat::test_create_chat_autodetect_lang`**

This test sends `{"phrase": "I am going home."}` (a grammatically correct sentence) to the real OpenAI LLM. The LLM returns a response without `issues` and `suggestions` fields, which fails `AnalyzeResponse.model_validate()` validation. This error is reproducible on the previous commit as well -- it is a pre-existing LLM response validation issue, not caused by the `question -> message` rename.

**Recommendation:** Fix this separately. The `AnalyzeResponse` model requires `issues: list[Issue]` and `suggestions: list[str]` but the LLM omits them when the sentence is correct. Options: (a) make those fields optional with defaults, (b) change the test phrase to something with actual errors, or (c) use `with_structured_output(strict=True)` to force the LLM schema. This is out of scope for the current rename fix task.

## Files to Change

| File | Line | Change | Why |
|------|------|--------|-----|
| `tests/unit/test_services.py` | 57 | `human_msg.message["context"]` -> `human_msg.content["context"]` | `Message.content` is the JSONB field, not related to rename |
| `tests/unit/test_webhooks.py` | 16 | `response.message` -> `response.content` | `httpx.Response.content` returns raw bytes, not related to rename |

## Verification

After fixes, expected test results:
- `python -m pytest tests/unit/` -- all 163 tests pass (0 failures)
- `python -m pytest tests/e2e/` -- 1 pre-existing failure remains (`test_create_chat_autodetect_lang`)

## Sources

- Commit diff `bdf5d45` -- direct inspection of all changes
- `grep -r "question"` across `src/` and `tests/` -- confirms no remaining old field references
- Test runs with full output on current commit
