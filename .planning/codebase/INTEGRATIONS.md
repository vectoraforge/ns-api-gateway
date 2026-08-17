# External Integrations

**Analysis Date:** 2026-02-24

## APIs & External Services

**LLM Service:**
- OpenAI GPT API - Linguistic analysis and phrase correction
  - SDK/Client: `langchain-openai` (ChatOpenAI model wrapper), `openai` (direct API)
  - Model: `gpt-4o-mini` (configurable via `config.yaml`)
  - Auth: `OPENAI_API_KEY` environment variable
  - Entry point: `app/services.py` AnalysisService class uses LangChain's init_chat_model
  - Used for: Analyzing phrases for grammatical issues and providing naturalness assessment

## Data Storage

**Databases:**
- PostgreSQL (primary)
  - Connection: Via `asyncpg` driver
  - Connection string: `postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}`
  - Environment config: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
  - Client: SQLAlchemy with sqlmodel ORM wrapper for async operations
  - Location: `app/database.py` - init_engine() initializes async connection pool
  - Pool configuration: `pool_size` (default 5), `max_overflow: 0`

**Tables:**
- `chats` - Stores conversation sessions with user ownership
  - Fields: id (UUID, PK), user_id (str, indexed), lang (str), created_at (datetime, server-side default)
  - Model: `app/models.py` Chat class

- `messages` - Stores individual messages within chats
  - Fields: id (int, PK, auto-increment), chat_id (UUID, FK→chats.id), role (str: "human"/"assistant"), content (str), created_at (datetime, server-side default, part of composite key)
  - Model: `app/models.py` Message class

**File Storage:**
- Local filesystem only
  - Configuration files in `config/` directory: `config.yaml`, `prompt.txt`, `examples.yaml`
  - No cloud storage integration

**Caching:**
- In-memory caching only
  - `ReadinessCache` in `app/routers/health.py` - configurable cache duration (default 60 seconds)
  - Chat history loaded on-demand from database

## Authentication & Identity

**Auth Provider:**
- Custom JWT validation
  - Implementation: Bearer token extraction and JWT payload decoding
  - Location: `app/auth.py` - get_user_id() dependency function
  - Mechanism: Decodes JWT without signature verification (trusts upstream)
  - Required claim: `user_id` (string) - extracted from JWT payload
  - Validation: Enforces user_id presence and Bearer token format
  - Applied to all prompts/chat endpoints via FastAPI dependency injection

**User Ownership:**
- All chats and messages are linked to user_id from JWT
- Endpoints enforce user_id ownership - users can only access their own chats
- Database queries filter by user_id to ensure data isolation

## Monitoring & Observability

**Error Tracking:**
- None - No external error tracking service integrated

**Logging:**
- Console/stdout logging only
  - Framework: Python's `logging` module
  - Location: `app/main.py` - setup_logging() configures handlers
  - Log level: Configurable via `log_level` config (default INFO)
  - Suppressed libraries: httpx and httpcore set to WARNING level
  - Logs to: stdout via StreamHandler

**Circuit Breaker & Resilience:**
- Custom circuit breaker in `app/services.py` CircuitBreaker class
  - Tracks OpenAI API failures
  - Tracks consecutive failures, opens circuit after threshold (default 5)
  - Auto-resets after timeout (default 60 seconds)

**Rate Limiting & Queueing:**
- Custom queue-based concurrency control in `app/services.py` LLMExecutionGate class
  - Max concurrent LLM calls: configurable (default 5)
  - Queue size: configurable (default 25)
  - Semaphore-based concurrency limiting
  - Queue overflow returns 429 with retry-after

## CI/CD & Deployment

**Hosting:**
- Not detected - expects ASGI server deployment (Uvicorn)

**CI Pipeline:**
- None detected in repository

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY` - OpenAI API authentication
- `DB_HOST` - PostgreSQL hostname (default: localhost)
- `DB_PORT` - PostgreSQL port (default: 5432)
- `DB_USER` - PostgreSQL username (default: postgres)
- `DB_PASSWORD` - PostgreSQL password (default: postgres)
- `DB_NAME` - PostgreSQL database name (default: nativespeaker)
- `CONFIG_DIR` - Path to config.yaml (default: config/config.yaml)
- `PROMPT_PATH` - Path to prompt.txt (default: config/prompt.txt)
- `EXAMPLES_PATH` - Path to examples.yaml (default: config/examples.yaml)

**Optional env vars:**
- `LOG_LEVEL` - Logging level (default: INFO)
- `MODEL_NAME` - LLM model name (default: gpt-4o-mini)
- `MODEL_TEMPERATURE` - LLM temperature (default: 0.3)
- `MODEL_MAX_TOKENS` - LLM max tokens (default: 1000)
- `MODEL_POOL_SIZE` - Max concurrent LLM calls (default: 5)
- `MODEL_QUEUE_SIZE` - LLM request queue size (default: 25)
- `MODEL_TIMEOUT_SECONDS` - LLM request timeout (default: 30)

**Secrets location:**
- `.env` file (not committed - see `.env.example` template)
- OPENAI_API_KEY must be in environment before startup

## Error Handling

**OpenAI API Errors:**
- Transient errors handled with exponential backoff retry
- Transient error classification: `app/services.py` _is_transient_error()
  - Timeout errors (asyncio.TimeoutError, TimeoutError)
  - Connection errors (APIConnectionError)
  - Rate limit errors (APITimeoutError, RateLimitError)
  - Server errors (InternalServerError)
  - HTTP 408, 409, 429, 500, 502, 503, 504
- Retry configuration: max_attempts (default 3), backoff_base (0.5s), backoff_max (4s)
- Non-transient errors fail immediately with AnalysisError

**Database Errors:**
- Auto-rollback on exception in `app/database.py` get_db()
- Foreign key constraints enforced by database

**Custom Exceptions:**
- `UnsupportedLanguageError` - Language not in examples
- `AnalysisError` - LLM analysis failure
- `InvalidChatError` - Chat session not found or not owned by user
- `QueueFullError` - LLM queue full (429 response)
- `CircuitOpenError` - Circuit breaker open (retry-after)
- `ChatHistoryLimitError` - Message history limit reached
- `MessageTooLargeError` - Message exceeds max_chars limit
- Location: `app/exceptions.py`

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-02-24*
