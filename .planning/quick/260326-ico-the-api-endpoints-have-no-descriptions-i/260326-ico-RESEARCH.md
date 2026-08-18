# Quick Task: Add API endpoint descriptions to /docs and openapi.json

**Researched:** 2026-03-26
**Domain:** FastAPI OpenAPI documentation
**Confidence:** HIGH

## Summary

All 10 API endpoints currently lack `summary` and `description` parameters in their route decorators. The `FastAPI()` app itself already has good top-level metadata (title, description, version, global error responses). The routers are created as bare `APIRouter()` instances without `tags` (except webhooks). The fix is adding `summary`, `description`, `response_description`, and `tags` to each route decorator, and `tags` to each `APIRouter`.

**Primary recommendation:** Add `summary`/`description`/`tags` to every `@router.get`/`@router.post`/`@router.delete` decorator, and set `tags` on each `APIRouter()` constructor.

## Project Constraints (from CLAUDE.md)

- Opening delimiter alignment style for multiline constructs
- Don't commit .planning dir
- Use Context7 MCP for library documentation

## Current State Audit

### App-level metadata (main.py) -- ALREADY GOOD

```python
app = FastAPI(title="NativeSpeaker API Gateway",
              description="API Gateway for linguistic analysis of phrases",
              version=version("ns-api-gateway"),
              responses={400: ..., 401: ..., 404: ..., 422: ..., 429: ..., 500: ..., 503: ...})
```

Global error responses already have descriptions. Title, description, and version are set.

### Router-level tags -- MISSING

| Router file | Current `APIRouter()` args | Needs |
|-------------|---------------------------|-------|
| chats.py | `APIRouter()` | `tags=["chats"]` |
| examples.py | `APIRouter()` | `tags=["examples"]` |
| health.py | `APIRouter()` | `tags=["health"]` |
| root.py | `APIRouter()` | `tags=["root"]` |
| users.py | `APIRouter()` | `tags=["users"]` |
| webhooks.py | `APIRouter(tags=["webhooks"])` | Already has tags |

### Endpoint-level descriptions -- ALL MISSING

| Endpoint | File | Current decorator kwargs | Missing |
|----------|------|-------------------------|---------|
| `GET /` | root.py | none | summary, description |
| `GET /chats` | chats.py | `response_model` | summary, description |
| `GET /chats/{chat_id}` | chats.py | `response_model` | summary, description |
| `POST /chats` | chats.py | `response_model`, `dependencies` | summary, description, response_description |
| `POST /chats/{chat_id}` | chats.py | `response_model`, `dependencies` | summary, description, response_description |
| `DELETE /chats/{chat_id}` | chats.py | `status_code=204` | summary, description |
| `GET /examples` | examples.py | `response_model` | summary, description |
| `GET /users/me` | users.py | `response_model` | summary, description |
| `POST /webhooks/apple` | webhooks.py | `status_code=200` | summary, description |
| `GET /health/ready` | health.py | none | summary, description |

## FastAPI OpenAPI Parameters

FastAPI route decorators accept these OpenAPI-relevant kwargs (HIGH confidence -- FastAPI 0.135.1 installed locally):

| Parameter | Purpose | Type |
|-----------|---------|------|
| `summary` | Short one-liner shown in the endpoint list in /docs | `str` |
| `description` | Longer Markdown text shown when endpoint is expanded | `str` |
| `response_description` | Description of the success response (default: "Successful Response") | `str` |
| `tags` | Groups endpoints in the /docs sidebar (inherits from router) | `list[str]` |
| `deprecated` | Marks endpoint as deprecated in /docs | `bool` |
| `operation_id` | Custom operationId in openapi.json (auto-generated from function name if omitted) | `str` |

### Note on docstrings

FastAPI uses the **function docstring** as the `description` if no explicit `description=` is passed. This is a valid alternative. However, explicit `description=` in the decorator is clearer and keeps the OpenAPI concern separate from code documentation.

**Recommendation:** Use explicit `summary=` and `description=` in decorators for consistency and clarity, since none of the existing endpoints have docstrings either.

## Implementation Pattern

For each endpoint, add `summary` and `description` to the decorator. Follow the project's opening-delimiter alignment style:

```python
@router.get("/chats",
            response_model=list[ChatResponse],
            summary="List chats",
            description="Returns all chat sessions belonging to the authenticated user.")
async def list_chats(user: User = Depends(get_current_user),
                     service: ChatService = Depends(get_chat_service)):
```

For each router constructor, add `tags`:

```python
router = APIRouter(tags=["chats"])
```

## Suggested Descriptions

| Endpoint | Summary | Description |
|----------|---------|-------------|
| `GET /` | API information | Returns API name, version, and supported languages. |
| `GET /chats` | List chats | Returns all chat sessions belonging to the authenticated user. |
| `GET /chats/{chat_id}` | Get chat messages | Returns all messages in a chat session, ordered chronologically. |
| `POST /chats` | Start new analysis | Analyzes a phrase and creates a new chat session with the AI response. Consumes one request from the user's monthly quota. |
| `POST /chats/{chat_id}` | Send follow-up message | Sends a follow-up message in an existing chat session. Consumes one request from the user's monthly quota. |
| `DELETE /chats/{chat_id}` | Delete chat | Permanently deletes a chat session and all its messages. |
| `GET /examples` | Get example phrases | Returns example phrases for a given language to help users get started. |
| `GET /users/me` | Get current user profile | Returns the authenticated user's profile, subscription plan, and current month's usage. |
| `POST /webhooks/apple` | Apple subscription webhook | Receives Apple App Store Server Notifications v2 for subscription lifecycle events. |
| `GET /health/ready` | Readiness probe | Kubernetes readiness check. Returns 200 when the service is ready. |

## Common Pitfalls

1. **Forgetting `response_description`**: Default is "Successful Response" which is generic. Worth setting for POST endpoints that return analysis results.
2. **Tags on both router and decorator**: If you set `tags` on both `APIRouter()` and the individual `@router.get(tags=...)`, they get merged. Set it only on the router to avoid duplication.
3. **Multiline string alignment**: The project uses opening-delimiter alignment. Long descriptions should be a single string, not a multiline `"""` block in the decorator.

## Files to Modify

1. `src/nativespeaker/api/routers/chats.py` -- 5 endpoints + router tags
2. `src/nativespeaker/api/routers/examples.py` -- 1 endpoint + router tags
3. `src/nativespeaker/api/routers/health.py` -- 1 endpoint + router tags
4. `src/nativespeaker/api/routers/root.py` -- 1 endpoint + router tags
5. `src/nativespeaker/api/routers/users.py` -- 1 endpoint + router tags
6. `src/nativespeaker/api/routers/webhooks.py` -- 1 endpoint (tags already set)

No changes needed to `main.py` (app-level metadata is already good).

## Validation

After changes, verify by:
1. Run existing tests: `pytest` (descriptions don't affect behavior)
2. Start server and check `http://localhost:8000/docs` -- all endpoints should show summaries and grouped by tags
3. Check `http://localhost:8000/openapi.json` -- verify `summary` and `description` fields are present on all operations
