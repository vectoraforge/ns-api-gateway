# Architecture

**Analysis Date:** 2026-02-24

## Pattern Overview

**Overall:** Layered service architecture with strict separation between HTTP handler layer, business logic layer, and data access layer. Uses FastAPI for HTTP routing, LangChain for LLM integration, and SQLAlchemy for async database operations.

**Key Characteristics:**
- FastAPI async-first application lifecycle management with startup/shutdown hooks
- Dependency injection through FastAPI's `Depends()` for database sessions and authentication
- Service layer (`AnalysisService`) containing all business logic and LLM orchestration
- Resilience patterns: circuit breaker and execution gate (semaphore + queue) for LLM concurrency control
- Chat history persistence across requests through database records
- JWT token validation for user ownership and access control

## Layers

**HTTP Router Layer:**
- Purpose: Accept and validate HTTP requests, delegate to services, return responses
- Location: `app/routers/`
- Contains: Three routers (`prompts.py`, `root.py`, `health.py`) define endpoints with request/response schemas
- Depends on: `AnalysisService`, database session, authentication
- Used by: HTTP clients

**Business Logic Layer:**
- Purpose: Orchestrate phrase analysis, manage LLM invocations, handle chat state
- Location: `app/services.py`
- Contains: `AnalysisService` class with analysis chain building, history management, and resilience control
- Depends on: LangChain LLM client, circuit breaker, execution gate, chat manager, database
- Used by: HTTP routers

**Resilience & Control Layer:**
- Purpose: Manage LLM concurrency limits, circuit breaking for cascading failures
- Location: `app/services.py` (classes: `LLMExecutionGate`, `CircuitBreaker`)
- Contains: Token-based queue (slots), semaphore for concurrency, failure counting with time-based reset
- Depends on: asyncio primitives
- Used by: `AnalysisService._invoke()`

**Chat & History Layer:**
- Purpose: Manage chat sessions, persist messages, load history for LLM context
- Location: `app/chats.py`
- Contains: `Chats` class with methods for chat CRUD, message persistence, history retrieval, cursor-based pagination
- Depends on: SQLAlchemy async session
- Used by: `AnalysisService`

**Data Access Layer:**
- Purpose: Database connection lifecycle and session management
- Location: `app/database.py`
- Contains: Async SQLAlchemy engine initialization, session factory, dependency injection function
- Depends on: SQLAlchemy async driver (asyncpg)
- Used by: All database operations

**Models & Schema Layer:**
- Purpose: Define database schemas and API request/response contracts
- Location: `app/models.py` (ORM models), `app/schema.py` (Pydantic schemas)
- Contains: SQLModel `Chat` and `Message` tables; Pydantic `AnalyzeRequest`, `AnalyzeResponse`, chat schemas
- Depends on: SQLAlchemy, Pydantic
- Used by: Routers, services, database layer

**Configuration & Initialization:**
- Purpose: Load application config from YAML, environment variables; initialize services
- Location: `app/config.py` (config models), `app/main.py` (lifespan context manager)
- Contains: Pydantic config models for app/db/model settings; FastAPI lifespan setup
- Depends on: YAML files, environment
- Used by: Routers and services via `request.app.state`

**Error Handling & Authentication:**
- Purpose: Convert exceptions to HTTP responses; validate JWT tokens
- Location: `app/errors.py` (exception handlers), `app/auth.py` (JWT decoding)
- Contains: Exception handler registration; simple JWT payload extraction and `user_id` claim validation
- Depends on: Custom exception hierarchy
- Used by: FastAPI middleware and dependency injection

## Data Flow

**Phrase Analysis Flow:**

1. HTTP POST `/prompts/analyze` with text, language, optional chat_id
2. Router dependency injection: `get_user_id()` extracts user from JWT, `get_db()` provides session
3. Router calls `AnalysisService.analyze(db, text, lang, user_id, chat_id)`
4. Service validates message size and language support
5. Service creates new chat (if no chat_id) or retrieves existing chat lang (if chat_id provided)
6. Service loads message history from database: `Chats.load_history()`
7. Service constructs LangChain prompt template with history placeholder
8. Service invokes LLM through `_invoke()` method:
   - Circuit breaker checks if open (fails with 503 if so)
   - Execution gate acquires slot (queues or fails with 503 if queue full)
   - Semaphore enforces max concurrency
   - Timeout wraps chain.ainvoke()
   - Transient errors trigger exponential backoff retry
   - Non-transient errors fail immediately
9. Service parses JSON response from LLM
10. Service validates response size
11. Service saves user query + assistant response to database: `Chats.save_messages()`
12. Router returns `AnalyzeResponse` with analysis results and chat_id

**Chat Continuation Flow:**

1. HTTP POST `/chats/{chat_id}/messages` with text
2. Router validates user owns chat via `Chats.get_chat(db, chat_id, user_id=user_id)`
3. Service ensures history capacity not exceeded via `Chats.get_message_counts()`
4. Service loads history, builds chain, invokes LLM (same as analysis step 7-8)
5. Service persists messages and returns response

**Message Retrieval Flow:**

1. HTTP GET `/chats/{chat_id}/messages?limit=50&cursor=...`
2. Service validates chat ownership
3. Service calls `Chats.list_messages(db, chat_id, limit, cursor)` for cursor-based pagination
4. Cursor encodes `(created_at, message_id)` as base64 for stateless pagination
5. Router returns paginated messages with next_cursor if more results exist

**State Management:**

- **Configuration:** Loaded once at startup via YAML and environment, stored in `app.state.config`
- **Service instance:** Single `AnalysisService` created at startup, stored in `app.state.service`
- **Chat history:** Persisted in PostgreSQL `messages` table; loaded on-demand by service
- **LLM state:** Circuit breaker and execution gate maintain failure count and slot state in memory (lost on restart)
- **User context:** Extracted from JWT token on every request; enforces ownership checks

## Key Abstractions

**AnalysisService:**
- Purpose: Orchestrate phrase analysis workflow with resilience
- Examples: `app/services.py` class definition lines 124-268
- Pattern: Dependency injection container holding LLM, gate, circuit breaker, config; methods for `analyze()`, `chat()`, `get_examples()`

**LLMExecutionGate:**
- Purpose: Limit concurrent LLM requests and queue overload scenarios
- Examples: `app/services.py` lines 95-121
- Pattern: Token bucket via `asyncio.Queue` with size = max_concurrency + max_queue; semaphore for actual concurrency limit

**CircuitBreaker:**
- Purpose: Fail fast when LLM service degrades; automatically recover after timeout
- Examples: `app/services.py` lines 61-92
- Pattern: State machine (closed → open on failure threshold → half-open after timeout → closed on success)

**Chats:**
- Purpose: Encapsulate all chat and message database operations
- Examples: `app/chats.py` class definition lines 13-105
- Pattern: Static methods for cursor encoding/decoding; instance methods for CRUD operations; async session passed as parameter

**Router Dependency Chain:**
- Purpose: Compose request context (user, database, service)
- Examples: `app/routers/prompts.py` endpoint definitions
- Pattern: FastAPI `Depends()` with callables (`get_user_id`, `get_db`) that extract/inject parameters

## Entry Points

**Application Entry:**
- Location: `app/main.py` lines 81-93
- Triggers: When application server (Uvicorn) starts
- Responsibilities: Create FastAPI app instance, define lifespan context manager, register routers and exception handlers

**Lifespan Context Manager:**
- Location: `app/main.py` lines 31-78
- Triggers: On startup (before yield) and shutdown (after yield)
- Responsibilities: Initialize logging, database engine, LLM model, resilience controls; yield app to handler; cleanup on shutdown

**HTTP Endpoints:**
- `/` (GET) - `app/routers/root.py` - Returns API metadata and supported languages
- `/prompts/analyze` (POST) - `app/routers/prompts.py` - Analyze phrase, create/continue chat
- `/prompts/examples` (GET) - `app/routers/prompts.py` - Get language-specific examples
- `/chats/{chat_id}/messages` (POST) - `app/routers/prompts.py` - Add message to existing chat
- `/chats/{chat_id}/messages` (GET) - `app/routers/prompts.py` - List chat messages with cursor pagination
- `/chats/{chat_id}` (DELETE) - `app/routers/prompts.py` - Delete chat
- `/health/ready` (GET) - `app/routers/health.py` - Readiness probe (checks DB and LLM availability)

## Error Handling

**Strategy:** Convert domain exceptions to HTTP responses with appropriate status codes and retry-after headers where applicable.

**Patterns:**

- **UnsupportedLanguageError** → 400 with detail message
- **AnalysisError** (LLM failures) → 500 with generic detail (actual error logged)
- **InvalidChatError** (chat not found or not owned) → 404
- **QueueFullError** (LLM queue full) → 503 with Retry-After header
- **CircuitOpenError** (LLM circuit breaker open) → 503 with Retry-After header
- **ChatHistoryLimitError** (too many messages) → 409
- **MessageTooLargeError** (user or assistant message exceeds limit) → 413
- **RequestValidationError** (Pydantic validation) → 422 with generic detail
- **Generic exceptions** → 500 with generic detail (actual error logged)

All exceptions handled by `app/errors.py` registered in FastAPI via `register_exception_handlers()`.

## Cross-Cutting Concerns

**Logging:**
- Setup in `app/main.py` via `setup_logging()` which configures root logger and suppresses verbose httpx/httpcore logs
- Usage: Domain exceptions logged at INFO/ERROR level; LLM errors logged at ERROR with full traceback; validation errors logged at ERROR
- No correlation IDs or request-scoped context

**Validation:**
- Pydantic enforces schema validation on all HTTP inputs: `AnalyzeRequest`, `ChatMessageRequest`, `AnalyzeResponse`
- Service layer enforces business rules: language support, message size limits, history capacity, chat ownership
- Database layer relies on SQLModel for type safety

**Authentication:**
- Simple JWT validation in `app/auth.py`: extract `user_id` claim from token payload (no signature verification)
- Enforced as dependency: all analysis and chat endpoints require valid JWT
- Ownership enforced: service methods filter chats by `user_id` from token

**Concurrency Control:**
- Semaphore limits concurrent LLM requests to `model.pool_size`
- Queue enforces total inflight + queued requests ≤ `model.pool_size + model.queue_size`
- Retry backoff uses exponential strategy: 0.5s, 1s, 2s, etc. up to max 4s
- Circuit breaker prevents cascading failures: opens after N consecutive errors, half-opens after timeout

---

*Architecture analysis: 2026-02-24*
