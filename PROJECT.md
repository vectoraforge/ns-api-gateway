# SpeakNative API Gateway - Project Specification

## Overview
SpeakNative API Gateway is a FastAPI service that analyzes non-native phrasing and suggests more natural alternatives. It supports multi-language prompts and maintains per-user chat history to allow follow-up questions. The service uses OpenAI via LangChain, stores chats/messages in Postgres, and exposes a small REST API.

## Goals
- Provide phrase analysis that identifies issues, suggests corrected alternatives, and summarizes naturalness.
- Support follow-up questions within a chat session.
- Support multiple languages via configurable prompt + example sets.
- Persist chats and message history for pagination and continued context.

## Non-Goals
- No user management beyond reading a `user_id` claim from the provided JWT.
- No JWT signature verification or token introspection.
- No external orchestration or workflow engine; logic lives in the API service.

## Runtime Architecture
- **FastAPI app**: `app.main` creates the app, config, database engine, and the analysis service in an async lifespan.
- **Routers**: `app/routers/*` expose REST endpoints.
- **Service layer**: `AnalysisService` builds prompts, calls the LLM, validates output, and persists messages.
- **Persistence**: Async SQLModel + SQLAlchemy, PostgreSQL with partitioned `messages` table.
- **Health**: `/health/ready` verifies DB connectivity and LLM model availability, cached for a short TTL.

## API
All endpoints return JSON.

### `GET /`
Returns service metadata.

Response:
```json
{
  "name": "SpeakNative API Gateway",
  "version": "1.0.0",
  "supported_languages": ["en", "es"]
}
```

### `GET /prompts/examples?lang=en`
Returns example phrases for a language. No auth required.

Response:
```json
{
  "lang": "en",
  "examples": ["I am going to home.", "He do not like it."]
}
```

Errors:
- `400` if language is unsupported or examples are missing.

### `POST /prompts/analyze`
Analyze a phrase and optionally create/continue a chat. Requires `Authorization: Bearer <jwt>` with a `user_id` claim.

Request:
```json
{
  "text": "I am going to home.",
  "lang": "en",
  "chat_id": "uuid-optional"
}
```

Response (`AnalyzeResponse`):
```json
{
  "text": "I am going to home.",
  "lang": "en",
  "chat_id": "uuid",
  "issues": [{"text_part": "to home", "explanation": "..."}],
  "alternatives": ["I am going home."],
  "assessment": "Minor preposition error"
}
```

Behavior:
- If `chat_id` is omitted, a new chat is created for the user.
- If `chat_id` is provided, the language is taken from the chat, not the request.

### `POST /chats/{chat_id}/messages`
Send a follow-up message in an existing chat. Requires auth.

Request:
```json
{
  "text": "Why is that wrong?"
}
```

Response: same shape as `AnalyzeResponse`.

### `GET /chats/{chat_id}/messages?limit=50&cursor=...`
List chat messages with cursor pagination. Requires auth.

Response:
```json
{
  "messages": [
    {"id": 12, "role": "assistant", "content": "{...}", "created_at": "2026-02-25T12:34:56+00:00"}
  ],
  "next_cursor": "base64..."
}
```

Behavior:
- Messages are ordered by `created_at` DESC, then `id` DESC.
- `cursor` is a base64-encoded `created_at|id` pair.
- `limit` is capped by `messages_max_page_size` (default 100).

### `DELETE /chats/{chat_id}`
Delete a chat and its messages. Requires auth. Returns `204 No Content`.

### `GET /health/ready`
Readiness check for DB and LLM model availability. No auth required.

Response (200 or 503):
```json
{
  "status": "ok" | "degraded",
  "db": "ok" | "error",
  "llm": "ok" | "error",
  "errors": {"db": null | "...", "llm": null | "..."}
}
```

## Authentication
Endpoints requiring auth use a simple JWT parsing strategy:
- Must include `Authorization: Bearer <jwt>`.
- The JWT is decoded without signature verification.
- The `user_id` claim is required and used for chat ownership.

## LLM Workflow
- System prompt loaded from `config/prompt.txt`.
- Examples loaded from `config/examples.yaml` and used to serve `/prompts/examples` and validate supported languages.
- Prompt template: system prompt + chat history + `"Analyze this phrase: {phrase}"`.
- LLM output must be valid JSON matching the schema:
  - `assessment` (string, required)
  - `issues` (list of `{text_part, explanation}`)
  - `alternatives` (list of strings)
- Output is parsed with `JsonOutputParser` and validated against `AnalyzeResponse`.
- Messages are saved to DB as plain strings; assistant content stores the stringified parsed response.

Reliability controls:
- **Concurrency gate**: `pool_size` active calls + `queue_size` queued requests.
- **Queue full** returns `503` with `Retry-After`.
- **Circuit breaker**: opens after N failures and returns `503` with `Retry-After`.
- **Retry**: exponential backoff for transient LLM errors.

## Data Model
PostgreSQL tables created by `migrations/001_create_tables.sql`:

- `chats`
  - `id` UUID (PK)
  - `user_id` TEXT (nullable, indexed)
  - `lang` TEXT
  - `created_at` TIMESTAMPTZ (default now)

- `messages` (partitioned by `created_at`)
  - `id` BIGSERIAL
  - `chat_id` UUID (FK, cascade delete)
  - `role` TEXT (`human` | `assistant`)
  - `content` TEXT
  - `created_at` TIMESTAMPTZ (default now)
  - PK (`id`, `created_at`)

Partitioning:
- Uses `pg_partman` to create daily partitions.
- Retention is set to 30 days.

## Configuration
Configuration is loaded by `MainConfig` in this order:
1. YAML config file (default `config/config.yaml`).
2. Prompt and examples files (default `config/prompt.txt`, `config/examples.yaml`).
3. Environment variables can override settings via nested names (delimiter `_`).

Key settings (`config/config.yaml`):
- `log_level`
- `model.*` (name, temperature, max_tokens, pool_size, queue_size, retry config, circuit breaker config)
- `history_max_human_messages`, `history_max_assistant_messages`
- `message_max_chars`
- `messages_max_page_size`
- `readiness_cache_seconds`

Environment variables (`.env.example`):
- `CONFIG_DIR`, `PROMPT_PATH`, `EXAMPLES_PATH`
- `OPENAI_API_KEY`
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`

Database URL format:
`postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}`

## Error Handling
Custom errors are mapped to HTTP responses:
- `UnsupportedLanguageError` -> `400`
- `InvalidChatError` -> `404`
- `QueueFullError` -> `503` (with `Retry-After`)
- `CircuitOpenError` -> `503` (with `Retry-After`)
- `ChatHistoryLimitError` -> `409`
- `MessageTooLargeError` -> `413`
- Validation errors -> `422`
- Unhandled errors -> `500`

## Limits
- `text` max length: 4096 chars (request validation).
- Chat history caps: `history_max_human_messages` and `history_max_assistant_messages`.
- Pagination: `messages_max_page_size`.

## Deployment
- **Local**: `uv sync` then `uvicorn app.main:app --reload`.
- **Docker**: `Dockerfile` builds a slim image with `uv` and runs `uvicorn` on port 8000.
- **Docker Compose**: `docker-compose.yml` runs Postgres 17 and initializes schema via migration.

## Testing
- `pytest` with unit and integration tests.
- LLM tests are marked with `@pytest.mark.llm` and skipped by default (`-m 'not llm'`).
