---
phase: quick
plan: 260317-nbq
type: execute
wave: 1
depends_on: []
files_modified:
  - app/config.py
  - config/config.yaml
  - tests/e2e/conftest.py
autonomous: true
requirements: ["dedup-test-env"]
must_haves:
  truths:
    - "e2e conftest has no manual DB URL construction -- uses app config"
    - "e2e conftest creates DB sessions via the app's session factory, not a second engine"
    - "e2e conftest reads Firebase API key from app config, not os.environ directly"
    - "FIREBASE_TEST_EMAIL and FIREBASE_TEST_PASSWORD remain as direct env vars (test-only)"
    - "All e2e tests pass unchanged"
  artifacts:
    - path: "app/config.py"
      provides: "JWTConfig with api_key field"
      contains: "api_key"
    - path: "tests/e2e/conftest.py"
      provides: "Deduplicated fixtures reusing app code"
  key_links:
    - from: "tests/e2e/conftest.py"
      to: "app/config.py"
      via: "MainConfig import for config access"
      pattern: "MainConfig|app\\.state\\.config"
---

<objective>
Remove duplicated env-reading and DB-session logic from e2e test conftest. Reuse the app's
config parsing (MainConfig/DatabaseConfig) and session factory instead of hand-rolling a
second DB URL builder and engine. Add Firebase API key to JWTConfig so tests read it from
app config rather than raw os.environ.

Purpose: Single source of truth for config -- test infra drifts when it duplicates app logic.
Output: Cleaned e2e conftest, updated app config with api_key field.
</objective>

<execution_context>
@/Users/vay/.claude/get-shit-done/workflows/execute-plan.md
@/Users/vay/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@app/config.py
@app/api/main.py
@tests/e2e/conftest.py
@config/config.yaml

<interfaces>
<!-- From app/config.py -->
```python
class DatabaseConfig(BaseModel):
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    user: str = Field(default="postgres")
    password: SecretStr = Field(default=SecretStr("postgres"))
    name: str = Field(default="nativespeaker")
    schema: str = Field(default="public")
    pool_size: int = Field(default=5, ge=1)

    @property
    def url(self) -> str:  # <-- this is what _db_url() duplicates

class JWTConfig(BaseModel):
    project_id: str
    jwks_url: str = ...
    leeway_seconds: int = ...
    jwks_cache_ttl_seconds: float = ...

class MainConfig(BaseConfig):
    config_dir: Path = Field(default=Path("config/"))
    app_config: AppConfig | None = None
    # model_validator loads config_dir/*.yaml + prompt + examples into app_config
```

<!-- From app/api/main.py lifespan -->
```python
# After lifespan runs (via TestClient(app)):
app.state.config      # AppConfig instance
app.state.session_factory  # async_sessionmaker bound to config.db.url engine
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add api_key to JWTConfig and config.yaml</name>
  <files>app/config.py, config/config.yaml</files>
  <action>
In app/config.py, add an `api_key` field to JWTConfig:
```python
api_key: str = Field(default="")
```
Place it after `project_id`. This is the Firebase Web API Key used by client-side auth flows
(and by tests to obtain real tokens). Default to empty string so the server still starts
without it (it's not needed for JWT verification at runtime).

In config/config.yaml, add `api_key` under the `jwt` section:
```yaml
jwt:
  project_id: ns-api-gateway-488021
  api_key: ""           # Set via JWT_API_KEY env var; used by e2e tests
  jwks_cache_ttl_seconds: 3600
```

With pydantic-settings env_nested_delimiter="_", the env var `JWT_API_KEY` will populate
`jwt.api_key`. This replaces the standalone `FIREBASE_API_KEY` env var. Update the comment
in config.yaml to document this.

IMPORTANT: The existing env var is named FIREBASE_API_KEY. With nested delimiter, the
pydantic-settings path is JWT_API_KEY. So also rename the env var from FIREBASE_API_KEY
to JWT_API_KEY in .env.example if it exists (or note in done criteria).
  </action>
  <verify>
    <automated>cd /Users/vay/Work/git/native-speaker && python -c "from app.config import JWTConfig; j = JWTConfig(project_id='test'); print(j.api_key)"</automated>
  </verify>
  <done>JWTConfig has api_key field with empty default. config.yaml has api_key placeholder under jwt.</done>
</task>

<task type="auto">
  <name>Task 2: Rewrite e2e conftest to reuse app config and session factory</name>
  <files>tests/e2e/conftest.py</files>
  <action>
Rewrite the e2e conftest.py to eliminate all duplicated logic:

1. **Remove _db_url() entirely.** No manual URL construction.

2. **Remove ensure_tables fixture.** The app lifespan creates the engine. For table creation,
   add a session-scoped `_app_config` fixture that loads `MainConfig().app_config` once, then
   use its `db.url` to run `SQLModel.metadata.create_all`. This reuses the app's config
   parsing instead of hand-rolled env var reading.

   ```python
   @pytest.fixture(scope="session")
   def _app_config():
       """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
       return MainConfig().app_config

   @pytest.fixture(scope="session")
   def ensure_tables(_app_config):
       async def _create():
           engine = create_async_engine(_app_config.db.url, pool_size=1, max_overflow=0)
           async with engine.begin() as conn:
               await conn.run_sync(SQLModel.metadata.create_all)
           await engine.dispose()
       asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_create())
   ```

3. **Rewrite firebase_token** to read API key from `_app_config.jwt.api_key` instead of
   `os.environ["FIREBASE_API_KEY"]`. Keep `FIREBASE_TEST_EMAIL` and `FIREBASE_TEST_PASSWORD`
   as direct `os.environ` reads since those are test-only credentials not in app config.

   ```python
   @pytest.fixture(scope="session")
   def firebase_token(_app_config):
       api_key = _app_config.jwt.api_key
       assert api_key, "JWT_API_KEY env var required for e2e tests"
       email = os.environ["FIREBASE_TEST_EMAIL"]
       password = os.environ["FIREBASE_TEST_PASSWORD"]
       # ... rest unchanged
   ```

4. **Rewrite db_session** to use app.state.session_factory from the running TestClient app.
   Since every test using db_session also uses real_client, make db_session depend on
   real_client:

   ```python
   @pytest.fixture
   async def db_session(real_client):
       factory = real_client.app.state.session_factory
       async with factory() as session:
           yield session
           await session.rollback()
   ```

   This eliminates the second engine entirely. The db_session now shares the same connection
   pool as the app. Remove the `ensure_tables` dependency from db_session (real_client
   already depends on ensure_tables).

5. **Keep create_chat and cleanup_chat** unchanged -- they take a session and are fine.

6. **Keep real_client** mostly the same but ensure it depends on ensure_tables (already does).

Use the opening delimiter alignment style for multiline constructs per CLAUDE.md.
  </action>
  <verify>
    <automated>cd /Users/vay/Work/git/native-speaker && python -m pytest tests/e2e/ -x --timeout=120 -m e2e 2>&1 | tail -30</automated>
  </verify>
  <done>
All e2e tests pass. conftest.py has no _db_url(), no manual DB URL construction, no
os.environ["FIREBASE_API_KEY"]. DB session comes from app.state.session_factory.
Firebase API key comes from _app_config.jwt.api_key. Only FIREBASE_TEST_EMAIL and
FIREBASE_TEST_PASSWORD remain as direct os.environ reads.
  </done>
</task>

</tasks>

<verification>
1. `python -m pytest tests/e2e/ -x --timeout=120 -m e2e` -- all e2e tests pass
2. `grep -c "os.environ" tests/e2e/conftest.py` -- should be exactly 2 (TEST_EMAIL, TEST_PASSWORD) plus 1 for setdefault(FIREBASE_TEST_USER_ID)
3. `grep "_db_url\|DB_USER\|DB_PASSWORD\|DB_HOST\|DB_PORT\|DB_NAME" tests/e2e/conftest.py` -- no matches
4. `grep "FIREBASE_API_KEY" tests/e2e/conftest.py` -- no matches
</verification>

<success_criteria>
- Zero duplicated env-reading logic in e2e conftest
- DB sessions sourced from app's session factory (single engine)
- Firebase API key read from app config (JWTConfig.api_key)
- Only test-specific credentials (email, password) read directly from os.environ
- All existing e2e tests pass without modification
</success_criteria>

<output>
After completion, create `.planning/quick/260317-nbq-don-t-duplicate-the-logic-of-reading-env/260317-nbq-SUMMARY.md`
</output>
