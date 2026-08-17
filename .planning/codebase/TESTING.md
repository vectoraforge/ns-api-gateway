# Testing Patterns

**Analysis Date:** 2026-02-24

## Test Framework

**Runner:**
- Pytest 9.0+
- Config: `pyproject.toml` `[tool.pytest.ini_options]`

**Assertion Library:**
- Pytest's built-in assertions (`assert`)

**Run Commands:**
```bash
pytest                          # Run all tests excluding LLM tests
pytest -m "not llm"             # Explicitly exclude LLM tests (default)
pytest -m llm                   # Run only LLM tests
pytest -v                       # Verbose output (set in addopts)
pytest --tb=short               # Short traceback format (set in addopts)
pytest -cov                     # Coverage report
pytest tests/unit               # Run only unit tests
pytest tests/integration        # Run only integration tests
```

**Configuration Details from pyproject.toml:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
env_files = [".env"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "-v --tb=short -m 'not llm'"
markers = [
    "llm: marks tests requiring calls to external LLM (deselect with -m 'not llm')",
]
```

## Test File Organization

**Location:**
- Unit tests co-located by module: `tests/unit/test_services.py`, `tests/unit/test_config.py`, `tests/unit/test_models.py`
- Integration tests by feature: `tests/integration/test_prompts_endpoints.py`, `tests/integration/test_root_endpoint.py`
- LLM tests isolated: `tests/llm/test_real_llm.py` (marked with `@pytest.mark.llm`, excluded by default)
- Shared fixtures in: `tests/conftest.py`

**Naming:**
- File pattern: `test_*.py` (matches pytest discovery)
- Test class pattern: `Test[Feature]` (PascalCase): `TestAnalyze`, `TestChat`, `TestGetExamples`
- Test function pattern: `test_[scenario]`: `test_success`, `test_invalid_chat_id`, `test_unsupported_language`

**Directory Structure:**
```
tests/
├── conftest.py              # Shared fixtures (client, mocks)
├── unit/
│   ├── test_services.py     # AnalysisService, CircuitBreaker, LLMExecutionGate
│   ├── test_config.py       # Config loading and validation
│   └── test_models.py       # SQLModel definitions (if tested)
├── integration/
│   ├── test_prompts_endpoints.py  # /prompts/analyze, /prompts/examples, /chats/*
│   └── test_root_endpoint.py      # Root route
└── llm/
    └── test_real_llm.py     # Tests hitting actual OpenAI API
```

## Test Structure

**Suite Organization:**

From `tests/unit/test_services.py`:
```python
@pytest.fixture
def service(examples, mock_chats):
    gate = LLMExecutionGate(max_concurrency=1, max_queue=1, retry_after_seconds=1)
    circuit_breaker = CircuitBreaker(failure_threshold=3, reset_seconds=60)
    return AnalysisService(
        prompt="Analyze {lang} phrase: {phrase}",
        examples=examples,
        llm=MagicMock(),
        gate=gate,
        circuit_breaker=circuit_breaker,
        # ... more params
    )

class TestAnalyze:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        llm_response = {"issues": [...], "alternatives": [...], "assessment": "..."}

        with patch("app.services.ChatPromptTemplate") as mock_prompt, \
             patch("app.services.JsonOutputParser") as mock_parser:
            # Setup chain mocks
            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = llm_response
            # ... attach to pipe

            result = await service.analyze(mock_db, "I am going to home", "en", "user-1")

            assert isinstance(result, AnalyzeResponse)
            assert result.text == "I am going to home"
```

**Patterns:**
- Setup: Fixtures provide dependencies; `with patch()` for mocking complex chains
- Teardown: Implicit (pytest handles fixture cleanup)
- Assertion: Direct `assert` statements with specific values
- Async tests: Marked with `@pytest.mark.asyncio`, automatically awaited by pytest-asyncio

## Mocking

**Framework:** `unittest.mock` (Python standard library)

**Patterns:**

From `tests/conftest.py`:
```python
@pytest.fixture
def mock_chats():
    chats = AsyncMock()
    chats.create_chat = AsyncMock()
    chats.get_chat = AsyncMock(return_value=None)
    chats.load_history = AsyncMock(return_value=[])
    chats.get_message_counts = AsyncMock(return_value={"human": 0, "assistant": 0})
    chats.save_messages = AsyncMock()
    return chats

@pytest.fixture
def client(mock_config, mock_examples, mock_chats, mock_db, auth_header):
    app = FastAPI()
    app.include_router(root_router)
    app.include_router(prompts_router)
    app.include_router(chats_router)
    register_exception_handlers(app)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.state.config = mock_config

    mock_llm = MagicMock()
    gate = LLMExecutionGate(max_concurrency=1, max_queue=1, retry_after_seconds=1)
    # ... setup service

    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.headers.update(auth_header)
        yield test_client
```

From `tests/integration/test_prompts_endpoints.py`:
```python
# Mocking service methods directly
client.app.state.service.analyze = AsyncMock(return_value=mock_response)

# Patching internal functions
with patch("app.services.ChatPromptTemplate") as mock_prompt, \
     patch("app.services.JsonOutputParser") as mock_parser:
    mock_chain = AsyncMock()
    mock_chain.ainvoke.return_value = llm_response
    mock_prompt_inst = mock_prompt.from_messages.return_value
    mock_pipe = mock_prompt_inst.__or__.return_value
    mock_pipe.__or__.return_value = mock_chain
```

**What to Mock:**
- External service calls (LLM via mocked chain)
- Database operations (AsyncMock for `Chats` methods)
- Configuration (MagicMock with attribute access)
- Dependency injection targets (via `app.dependency_overrides`)

**What NOT to Mock:**
- Core business logic (AnalysisService, CircuitBreaker, LLMExecutionGate)
- Request validation (let Pydantic validate)
- Exception handlers (test their behavior with real exceptions)

## Fixtures and Factories

**Test Data:**

From `tests/conftest.py`:
```python
@pytest.fixture
def mock_examples():
    return {
        "en": ["I am going to home.", "He do not like it."],
        "es": ["Yo soy va a casa."],
    }

def _make_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8")).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": user_id}).encode("utf-8")).rstrip(b"=")
    return f"{header.decode('utf-8')}.{payload.decode('utf-8')}.signature"

@pytest.fixture
def auth_header():
    token = _make_token("test-user")
    return {"Authorization": f"Bearer {token}"}
```

**Location:**
- Fixtures in `tests/conftest.py` for shared fixtures
- Test-local fixtures defined in test files when used by single test class
- Helper functions (like `_make_token`) defined inline in conftest

## Coverage

**Requirements:** No explicit coverage target in pyproject.toml

**View Coverage:**
```bash
pytest --cov=app                    # Show coverage for app package
pytest --cov=app --cov-report=html  # Generate HTML coverage report
```

## Test Types

**Unit Tests:**
- Location: `tests/unit/`
- Scope: Individual functions/methods in isolation
- Mocking: Heavy mocking of dependencies
- Examples:
  - `test_services.py`: Tests `AnalysisService` methods (`analyze()`, `chat()`, `get_examples()`)
  - `test_config.py`: Tests Pydantic config loading (`MainConfig`, `ModelConfig`)
  - `test_models.py`: Tests SQLModel definitions if they have custom logic

**Integration Tests:**
- Location: `tests/integration/`
- Scope: Full request/response cycle through FastAPI
- Mocking: Mock external dependencies (LLM, database) but test routing, exception handling, response shape
- Examples:
  - `test_prompts_endpoints.py`: Tests `/prompts/analyze`, `/prompts/examples`, `/chats/*/messages`, `/chats/*` DELETE
  - `test_root_endpoint.py`: Tests root route

**E2E Tests:**
- Framework: `tests/llm/test_real_llm.py` (marked `@pytest.mark.llm`)
- Not run by default; deselected by `addopts = "-m 'not llm'"`
- Would call real OpenAI API for end-to-end validation
- Run separately: `pytest -m llm`

## Common Patterns

**Async Testing:**

From `tests/unit/test_services.py`:
```python
@pytest.mark.asyncio
async def test_success(self, service, mock_db):
    llm_response = {...}

    with patch("app.services.ChatPromptTemplate") as mock_prompt, \
         patch("app.services.JsonOutputParser") as mock_parser:
        # ... setup
        result = await service.analyze(mock_db, "I am going to home", "en", "user-1")
        assert isinstance(result, AnalyzeResponse)
```

- `@pytest.mark.asyncio` decorator marks async tests
- `asyncio_mode = "auto"` in pytest config auto-detects async tests
- `AsyncMock` from unittest.mock for mocking async methods

**Error Testing:**

From `tests/unit/test_services.py`:
```python
@pytest.mark.asyncio
async def test_unsupported_language(self, service, mock_db):
    with pytest.raises(UnsupportedLanguageError) as exc_info:
        await service.analyze(mock_db, "Test", "fr", "user-1")

    assert exc_info.value.lang == "fr"
    assert "en" in exc_info.value.supported
```

- Use `pytest.raises()` context manager
- Access exception via `exc_info.value`
- Assert on exception attributes

**Response Testing:**

From `tests/integration/test_prompts_endpoints.py`:
```python
def test_analyze_success(self, client):
    client.app.state.service.analyze = AsyncMock(return_value=mock_response)

    response = client.post(
        "/prompts/analyze",
        json={"text": "I am going to home.", "lang": "en"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "I am going to home."
    assert data["lang"] == "en"
    assert data["chat_id"] == str(chat_id)
```

- Use `TestClient` from FastAPI for synchronous HTTP testing
- Post JSON directly: `json={"key": "value"}`
- Validate status code and parsed response with `response.json()`

**Assertion Patterns:**
- Status codes: `assert response.status_code == 200`
- Response types: `assert isinstance(result, AnalyzeResponse)`
- List length: `assert len(result.issues) == 1`
- Mock calls: `mock_chats.save_messages.assert_called_once()`
- Mock not called: `mock_chats.create_chat.assert_not_called()`

---

*Testing analysis: 2026-02-24*
