---
phase: quick
plan: 260325-jrd
type: execute
wave: 1
depends_on: []
files_modified:
  - src/nativespeaker/api/schema.py
  - tests/unit/test_models.py
  - tests/e2e/test_chats.py
autonomous: true
requirements: [FIX-SERIALIZATION, FIX-E2E-ASSERTIONS, FIX-UNIT-SERIALIZATION]
must_haves:
  truths:
    - "MessageResponse.model_dump() serializes content with actual fields (response, issues, suggestions for AI; phrase, comment for Human)"
    - "E2E tests for POST /chats verify content dict has expected AI content keys, not just existence"
    - "Unit tests verify .model_dump() produces non-empty content dict with correct fields"
  artifacts:
    - path: "src/nativespeaker/api/schema.py"
      provides: "MessageResponse with ContentUnion typed content field"
      contains: "content: HumanContent | AIContent"
    - path: "tests/unit/test_models.py"
      provides: "Serialization regression tests for MessageResponse"
      contains: "model_dump"
    - path: "tests/e2e/test_chats.py"
      provides: "E2E assertions on content field structure"
      contains: "response"
  key_links:
    - from: "src/nativespeaker/api/schema.py"
      to: "nativespeaker.api.models.content"
      via: "import HumanContent, AIContent"
      pattern: "from nativespeaker\\.api\\.models\\.content import.*HumanContent.*AIContent"
---

<objective>
Fix MessageResponse.content serialization bug and harden tests to prevent regression.

Purpose: POST /chats returns `"content": {}` because MessageResponse.content is typed as BaseModel, which Pydantic v2 serializes without knowledge of the actual model fields. Tests don't catch this because e2e tests only check key presence and unit tests only check Python object equality.

Output: Fixed schema type, hardened e2e assertions, new unit serialization test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/nativespeaker/api/schema.py
@src/nativespeaker/api/models/content.py
@tests/unit/test_models.py
@tests/e2e/test_chats.py

<interfaces>
From src/nativespeaker/api/models/content.py:
```python
class HumanContent(BaseModel):
    phrase: str
    comment: str | None = None

class AIContent(BaseModel):
    response: str
    issues: list[Issue] | None = None
    suggestions: list[str] | None = None

ContentUnion = Annotated[
    Annotated[HumanContent, Tag("human")] | Annotated[AIContent, Tag("ai")],
    Discriminator(content_discriminator),
]
```

From src/nativespeaker/api/models/__init__.py:
```python
from nativespeaker.api.models.content import (
    HumanContent, AIContent, content_discriminator, ContentUnion, PydanticJSONB,
)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix MessageResponse.content type and add serialization regression test</name>
  <files>src/nativespeaker/api/schema.py, tests/unit/test_models.py</files>
  <behavior>
    - Test: MessageResponse with AIContent serializes to dict with "response" key present in content
    - Test: MessageResponse with AIContent containing issues serializes content.issues as list of dicts with text_part and explanation
    - Test: MessageResponse with HumanContent serializes to dict with "phrase" key present in content
    - Test: MessageResponse.model_dump()["content"] is never an empty dict when given valid content
  </behavior>
  <action>
1. In `src/nativespeaker/api/schema.py`:
   - Add `HumanContent` to the import from `nativespeaker.api.models.content` (AIContent is already imported)
   - Change line 39 from `content: BaseModel` to `content: HumanContent | AIContent`
   - Remove the `BaseModel` import from pydantic if it is no longer used elsewhere in the file (check: ErrorResponse, ChatRequest, ChatResponse, MessageRequest, ExamplesResponse, UserProfileResponse all inherit from BaseModel, so keep it)

2. In `tests/unit/test_models.py`:
   - Add `HumanContent` to the import from `nativespeaker.api.models`
   - Add `Issue` import if not present (it is already imported from `nativespeaker.api.models.content`)
   - In `TestMessageResponse`, keep the existing `test_valid_response` test
   - Add `test_ai_content_serialization`: construct MessageResponse with AIContent(response="Looks good", issues=[Issue(text_part="going to home", explanation="Drop 'to'")], suggestions=["going home"]), call .model_dump(), assert dumped["content"]["response"] == "Looks good", assert len(dumped["content"]["issues"]) == 1, assert dumped["content"]["issues"][0]["text_part"] == "going to home", assert dumped["content"]["suggestions"] == ["going home"]
   - Add `test_human_content_serialization`: construct MessageResponse with HumanContent(phrase="Hello", comment="Test"), call .model_dump(), assert dumped["content"]["phrase"] == "Hello", assert dumped["content"]["comment"] == "Test"
   - Add `test_content_never_empty`: construct MessageResponse with AIContent(response="Ok"), call .model_dump(), assert dumped["content"] != {}, assert "response" in dumped["content"]

Use the project's opening-delimiter alignment style for any multiline function calls.
  </action>
  <verify>
    <automated>cd /Users/vay/Work/git/native-speaker/ns-api-gateway && python -m pytest tests/unit/test_models.py::TestMessageResponse -xvs</automated>
  </verify>
  <done>MessageResponse.content is typed as HumanContent | AIContent. Unit tests verify .model_dump() produces non-empty content dicts with correct field names for both AI and Human content types.</done>
</task>

<task type="auto">
  <name>Task 2: Harden e2e test assertions on content structure</name>
  <files>tests/e2e/test_chats.py</files>
  <action>
In `tests/e2e/test_chats.py`, strengthen the content assertions. Every test that currently asserts `"content" in data` should instead verify the content dict has the expected AI response structure.

1. `test_create_chat_english`: After `assert "content" in data`, add:
   - `assert isinstance(data["content"], dict)`
   - `assert "response" in data["content"]`
   - `assert data["content"] != {}`

2. `test_create_chat_spanish`: After `assert "content" in data`, add:
   - `assert "response" in data["content"]`
   - `assert data["content"] != {}`

3. `test_create_chat_with_comment`: After `assert "content" in data`, add:
   - `assert "response" in data["content"]`
   - `assert data["content"] != {}`

4. `test_followup_message`: After `assert "content" in data`, add:
   - `assert "response" in data["content"]`
   - `assert data["content"] != {}`

Keep all existing assertions intact. Only add new ones after the existing `"content" in data` checks.
  </action>
  <verify>
    <automated>cd /Users/vay/Work/git/native-speaker/ns-api-gateway && python -m pytest tests/e2e/test_chats.py -xvs</automated>
  </verify>
  <done>E2e tests assert that the serialized content dict contains "response" key and is non-empty, catching any future BaseModel-style serialization regression.</done>
</task>

</tasks>

<verification>
Run the full test suite to ensure no regressions:
```bash
python -m pytest tests/ -x --tb=short
```
</verification>

<success_criteria>
- `MessageResponse.content` typed as `HumanContent | AIContent` (not `BaseModel`)
- `python -m pytest tests/unit/test_models.py::TestMessageResponse -xvs` passes with serialization tests
- `python -m pytest tests/e2e/test_chats.py -xvs` passes with hardened content assertions
- Full test suite passes with no regressions
</success_criteria>

<output>
After completion, create `.planning/quick/260325-jrd-fix-tests-post-chats-returns-empty-conte/260325-jrd-SUMMARY.md`
</output>
