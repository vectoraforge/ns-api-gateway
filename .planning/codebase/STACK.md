# Technology Stack

**Analysis Date:** 2026-02-24

## Languages

**Primary:**
- Python 3.12 - API service backend implementation
- YAML - Configuration files

**Secondary:**
- SQL - Database schema and queries
- JSON - API responses and request/response payloads

## Runtime

**Environment:**
- Python 3.12+

**Package Manager:**
- UV (modern Python package manager)
- Lockfile: `pyproject.toml` with version pinning

## Frameworks

**Core:**
- FastAPI 0.129+ - ASGI web framework for HTTP API endpoints
- Uvicorn 0.41+ (standard extras) - ASGI server

**LLM Integration:**
- LangChain 1.2+ - LLM orchestration and prompt management
- LangChain-OpenAI 1.1+ - OpenAI integration
- LangChain-Core 1.2+ - Base abstractions for LLM chains
- OpenAI 2.21+ - Direct OpenAI API client

**Data:**
- SQLModel 0.0.22+ - SQLAlchemy ORM with Pydantic validation
- AsyncPG 0.30+ - Async PostgreSQL database driver
- SQLAlchemy 2.0.46+ (via SQLModel) - Database ORM

**Configuration:**
- Pydantic 2.12+ - Data validation and settings management
- Pydantic-Settings 2.13+ - Environment variable loading
- PyYAML 6.0+ - YAML configuration parsing

**Development/Utilities:**
- Ruff 0.15.2+ - Python linter/formatter
- ty 0.0.17 - Type hint utilities

## Key Dependencies

**Critical:**
- `langchain-openai` (1.1+) - Connects to OpenAI API for GPT-4o-mini LLM calls
- `asyncpg` (0.30+) - Async database driver for PostgreSQL connectivity
- `sqlmodel` (0.0.22+) - ORM for database entity mapping and async queries
- `fastapi` (0.129+) - Web framework defining HTTP endpoints
- `pydantic` (2.12+) - Request/response validation for all API contracts

**Infrastructure:**
- OpenAI SDK provides chat model initialization and error handling
- LangChain provides chain composition, prompt templating, message history management
- SQLModel/SQLAlchemy provides database connection pooling and async session management

## Configuration

**Environment:**
- Loaded via Pydantic BaseSettings from environment variables with `_` delimiter nesting (e.g., `DB_HOST`, `DB_PORT`)
- Config file: `config/config.yaml` (path from `CONFIG_DIR` env var)
- Prompt template: `config/prompt.txt` (path from `PROMPT_PATH` env var)
- Examples: `config/examples.yaml` (path from `EXAMPLES_PATH` env var)

**Key Configs Required:**
- `OPENAI_API_KEY` - API key for OpenAI LLM access
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` - PostgreSQL connection details
- `CONFIG_DIR`, `PROMPT_PATH`, `EXAMPLES_PATH` - Paths to YAML/text configuration files
- Database connection: Format is `postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}`

**Build:**
- Build config: `pyproject.toml` - setuptools-based package build
- Packages defined: `["app", "app.routers"]`

## Testing

**Framework:**
- pytest 9.0+ - Test runner
- pytest-asyncio 1.3+ - Async test support
- pytest-cov 7.0+ - Coverage reporting
- pytest-dotenv 0.5+ - Load .env in tests
- httpx 0.28+ - Async HTTP client for testing

**Configuration:**
- Test config: `pyproject.toml` under `[tool.pytest.ini_options]`
- Test path: `tests/`
- Markers: `@pytest.mark.llm` for LLM integration tests (excluded by default)
- Asyncio mode: auto (function scope)

## Platform Requirements

**Development:**
- Python 3.12+
- PostgreSQL database (local or remote)
- OpenAI API access

**Production:**
- Python 3.12+ runtime
- PostgreSQL 12+ database
- OpenAI API access
- ASGI-compatible server (Uvicorn)
- Environment variables configured as per `.env.example`

---

*Stack analysis: 2026-02-24*
