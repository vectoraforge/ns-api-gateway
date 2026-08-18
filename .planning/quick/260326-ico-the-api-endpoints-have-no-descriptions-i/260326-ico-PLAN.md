---
phase: quick
plan: 260326-ico
type: execute
wave: 1
depends_on: []
files_modified:
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/health.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/routers/webhooks.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Every endpoint in /docs shows a summary and description"
    - "Endpoints are grouped by tags in /docs sidebar"
    - "openapi.json contains summary and description for all operations"
  artifacts:
    - path: "src/nativespeaker/api/routers/chats.py"
      provides: "Tags + summary/description on 5 chat endpoints"
    - path: "src/nativespeaker/api/routers/examples.py"
      provides: "Tags + summary/description on examples endpoint"
    - path: "src/nativespeaker/api/routers/health.py"
      provides: "Tags + summary/description on health endpoint"
    - path: "src/nativespeaker/api/routers/root.py"
      provides: "Tags + summary/description on root endpoint"
    - path: "src/nativespeaker/api/routers/users.py"
      provides: "Tags + summary/description on users endpoint"
    - path: "src/nativespeaker/api/routers/webhooks.py"
      provides: "Summary/description on webhooks endpoint (tags already set)"
  key_links: []
---

<objective>
Add OpenAPI summary, description, and tags to all 10 API endpoints so /docs and openapi.json show useful documentation.

Purpose: The /docs UI and openapi.json currently show bare endpoint paths with no descriptions, making the API hard to discover and use.
Output: All 6 router files updated with summary/description in decorators and tags on APIRouter constructors.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/quick/260326-ico-the-api-endpoints-have-no-descriptions-i/260326-ico-RESEARCH.md
@src/nativespeaker/api/routers/chats.py
@src/nativespeaker/api/routers/examples.py
@src/nativespeaker/api/routers/health.py
@src/nativespeaker/api/routers/root.py
@src/nativespeaker/api/routers/users.py
@src/nativespeaker/api/routers/webhooks.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add tags to APIRouter constructors and summary/description to all endpoint decorators</name>
  <files>
    src/nativespeaker/api/routers/chats.py
    src/nativespeaker/api/routers/examples.py
    src/nativespeaker/api/routers/health.py
    src/nativespeaker/api/routers/root.py
    src/nativespeaker/api/routers/users.py
    src/nativespeaker/api/routers/webhooks.py
  </files>
  <action>
    For each router file, make two changes:

    1. Add `tags` to the `APIRouter()` constructor (skip webhooks.py -- already has tags):
       - chats.py: `router = APIRouter(tags=["chats"])`
       - examples.py: `router = APIRouter(tags=["examples"])`
       - health.py: `router = APIRouter(tags=["health"])`
       - root.py: `router = APIRouter(tags=["root"])`
       - users.py: `router = APIRouter(tags=["users"])`

    2. Add `summary` and `description` kwargs to each route decorator, using the project's opening-delimiter alignment style. Use these exact texts:

       **root.py** -- `GET /`:
       - summary="API information"
       - description="Returns API name, version, and supported languages."

       **chats.py** -- 5 endpoints:
       - `GET /chats`: summary="List chats", description="Returns all chat sessions belonging to the authenticated user."
       - `GET /chats/{chat_id}`: summary="Get chat messages", description="Returns all messages in a chat session, ordered chronologically."
       - `POST /chats`: summary="Start new analysis", description="Analyzes a phrase and creates a new chat session with the AI response. Consumes one request from the user's monthly quota.", response_description="AI analysis message"
       - `POST /chats/{chat_id}`: summary="Send follow-up message", description="Sends a follow-up message in an existing chat session. Consumes one request from the user's monthly quota.", response_description="AI follow-up message"
       - `DELETE /chats/{chat_id}`: summary="Delete chat", description="Permanently deletes a chat session and all its messages."

       **examples.py** -- `GET /examples`:
       - summary="Get example phrases"
       - description="Returns example phrases for a given language to help users get started."

       **users.py** -- `GET /users/me`:
       - summary="Get current user profile"
       - description="Returns the authenticated user's profile, subscription plan, and current month's usage."

       **webhooks.py** -- `POST /webhooks/apple`:
       - summary="Apple subscription webhook"
       - description="Receives Apple App Store Server Notifications v2 for subscription lifecycle events."

       **health.py** -- `GET /health/ready`:
       - summary="Readiness probe"
       - description="Kubernetes readiness check. Returns 200 when the service is ready."

    Alignment style example (each decorator kwarg on its own line, aligned to opening paren):
    ```python
    @router.get("/chats",
                response_model=list[ChatResponse],
                summary="List chats",
                description="Returns all chat sessions belonging to the authenticated user.")
    ```

    Do NOT add `tags` to individual route decorators -- tags are set on the router constructor only (avoids duplication).
  </action>
  <verify>
    <automated>cd /Users/vay/Work/git/native-speaker/ns-api-gateway && python -c "
from nativespeaker.api.app.main import app
schema = app.openapi()
paths = schema['paths']
missing = []
for path, methods in paths.items():
    for method, detail in methods.items():
        if method in ('get','post','delete','put','patch'):
            if not detail.get('summary'):
                missing.append(f'{method.upper()} {path} missing summary')
            if not detail.get('description'):
                missing.append(f'{method.upper()} {path} missing description')
if missing:
    print('FAIL:'); [print(f'  - {m}') for m in missing]; exit(1)
else:
    print(f'PASS: All {sum(len([m for m in methods if m in (\"get\",\"post\",\"delete\",\"put\",\"patch\")]) for methods in paths.values())} endpoints have summary and description')
"</automated>
  </verify>
  <done>All 10 API endpoints have summary and description in openapi.json. All routers have tags set. Existing tests still pass (pytest).</done>
</task>

</tasks>

<verification>
1. `pytest` -- all existing tests pass (descriptions are additive, no behavior change)
2. Python script validates every endpoint in openapi.json has summary and description fields
</verification>

<success_criteria>
- All 10 endpoints show summary and description in /docs and openapi.json
- Endpoints grouped by tag (chats, examples, health, root, users, webhooks)
- All existing tests pass unchanged
</success_criteria>

<output>
After completion, create `.planning/quick/260326-ico-the-api-endpoints-have-no-descriptions-i/260326-ico-SUMMARY.md`
</output>
