---
phase: quick
plan: 260317-waa
type: execute
wave: 1
depends_on: []
files_modified:
  - app/config.py
  - app/api/main.py
  - config/config.yaml
  - tests/e2e/conftest.py
  - tests/unit/test_config.py
autonomous: true
must_haves:
  truths:
    - "Unit tests pass (python -m pytest tests/unit/ -x)"
    - "E2e tests pass against real Postgres and Firebase (python -m pytest tests/e2e/ -m e2e -x)"
    - "App starts without AttributeError on config.resilience"
    - "asyncpg connect() receives search_path via server_settings, not URL options"
    - "JWT api_key is populated from JWT_API_KEY env var, not overridden by empty YAML value"
  artifacts:
    - path: "app/config.py"
      provides: "DatabaseConfig with connect_args property, env_nested_max_split on AppConfig, correct JWTConfig types"
    - path: "app/api/main.py"
      provides: "Correct config.model.resilience references, connect_args passed to engine"
    - path: "config/config.yaml"
      provides: "JWT section without project_id or api_key (sourced from env)"
    - path: "tests/e2e/conftest.py"
      provides: "Engine creation with connect_args"
  key_links:
    - from: "app/config.py DatabaseConfig.connect_args"
      to: "app/api/main.py create_async_engine call"
      via: "config.db.connect_args kwarg"
    - from: "app/config.py DatabaseConfig.connect_args"
      to: "tests/e2e/conftest.py ensure_tables"
      via: "_app_config.db.connect_args kwarg"
    - from: "config/config.yaml jwt section"
      to: "app/config.py JWTConfig"
      via: "YAML data passed as kwargs to AppConfig"
---

<objective>
Fix all e2e test failures caused by three independent bugs: (1) asyncpg rejects `?options=` in SQLAlchemy URL, (2) YAML `api_key: ""` overrides JWT_API_KEY env var, (3) uncommitted changes broke `config.model.resilience` path and type annotations. Also revert broken uncommitted changes and apply correct fixes.

Purpose: Restore passing e2e test suite so the codebase has working end-to-end coverage.
Output: Clean commit with all five files fixed, both unit and e2e tests passing.
</objective>

<execution_context>
@/Users/vay/.claude/get-shit-done/workflows/execute-plan.md
@/Users/vay/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@app/config.py
@app/api/main.py
@config/config.yaml
@tests/e2e/conftest.py
@tests/unit/test_config.py
@.planning/quick/260317-waa-fix-e2e-tests/260317-waa-RESEARCH.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Revert uncommitted changes and fix all config/engine bugs</name>
  <files>app/config.py, app/api/main.py, config/config.yaml, tests/e2e/conftest.py, tests/unit/test_config.py</files>
  <action>
First, revert ALL uncommitted changes in these files back to HEAD:
```bash
git checkout HEAD -- app/api/main.py app/config.py config/config.yaml tests/unit/test_config.py
```

Then apply these correct fixes:

**app/config.py** -- three changes:

1. DatabaseConfig: Remove `?options=-csearch_path={self.db_schema}` from the `url` property. Add a new `connect_args` property:
   ```python
   @property
   def url(self) -> str:
       return (f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
               f"@{self.host}:{self.port}/{self.name}")

   @property
   def connect_args(self) -> dict:
       return {"server_settings": {"search_path": self.db_schema}}
   ```
   This avoids the `TypeError: connect() got an unexpected keyword argument 'options'` from asyncpg when SQLAlchemy extracts URL query params.

2. AppConfig: Add `env_nested_max_split=1` directly on AppConfig (NOT on BaseConfig, because pydantic-settings metaclass resets inherited SettingsConfigDict values):
   ```python
   class AppConfig(BaseConfig):
       model_config = SettingsConfigDict(env_nested_delimiter="_",
                                         env_nested_max_split=1)
   ```
   BaseConfig keeps only `env_nested_delimiter="_"` (no max_split). This ensures `JWT_API_KEY` env var maps to `jwt.api_key` (split once) instead of `jwt.api.key`.

3. config.yaml: Remove `api_key: ""` line from the `jwt:` section. Keep `project_id: native-speaker-488021`. When api_key is absent from YAML, pydantic-settings picks up `JWT_API_KEY` from env. The `api_key` field in JWTConfig already has `default=""` so it won't fail if env var is also absent (just empty).

**app/api/main.py** -- one change:

Pass `connect_args` to `create_async_engine`:
```python
db_engine = create_async_engine(config.db.url,
                                connect_args=config.db.connect_args,
                                pool_size=config.db.pool_size,
                                max_overflow=0)
```
Keep `config.model.resilience` references (the committed version already has this correct; the revert restores it).

**tests/e2e/conftest.py** -- one change:

Pass `connect_args` to `create_async_engine` in `ensure_tables`:
```python
engine = create_async_engine(_app_config.db.url,
                             connect_args=_app_config.db.connect_args,
                             pool_size=1, max_overflow=0)
```

**config/config.yaml** -- after revert, remove only the `api_key: ""` line. Final jwt section:
```yaml
jwt:
  project_id: ns-api-gateway-488021
  jwks_cache_ttl_seconds: 3600
```

**tests/unit/test_config.py** -- no changes needed (revert restores to working committed state).
  </action>
  <verify>
    <automated>cd /Users/vay/Work/git/native-speaker && python -m pytest tests/unit/ -x --tb=short 2>&1 | tail -20</automated>
  </verify>
  <done>All unit tests pass. git diff shows only the intended fixes (connect_args property, AppConfig env_nested_max_split, api_key removed from YAML, connect_args passed in main.py and conftest.py).</done>
</task>

<task type="auto">
  <name>Task 2: Run e2e tests to confirm full fix</name>
  <files></files>
  <action>
Run the full e2e test suite to verify all fixes work together against real infrastructure:
```bash
python -m pytest tests/e2e/ -m e2e -x --tb=short
```

If any test fails, diagnose and fix based on the error output. The most likely remaining issue would be:
- If `JWT_API_KEY` is still not picked up: verify `AppConfig.model_config` has `env_nested_max_split=1` and `config.yaml` does NOT contain `api_key`.
- If DB connection fails: verify `connect_args` is passed in both `main.py` lifespan and `conftest.py` `ensure_tables`.

All 18 e2e tests should pass.
  </action>
  <verify>
    <automated>cd /Users/vay/Work/git/native-speaker && python -m pytest tests/e2e/ -m e2e -x --tb=short 2>&1 | tail -20</automated>
  </verify>
  <done>All e2e tests pass (18 passed). Both unit and e2e test suites are green.</done>
</task>

</tasks>

<verification>
- `python -m pytest tests/unit/ -x --tb=short` -- all unit tests pass
- `python -m pytest tests/e2e/ -m e2e -x --tb=short` -- all 18 e2e tests pass
- `git diff HEAD` shows only the intended changes (no leftover uncommitted debris)
- No `?options=` in any URL construction
- No `config.resilience` (only `config.model.resilience`)
- No `api_key` in config.yaml
</verification>

<success_criteria>
Both `python -m pytest tests/unit/ -x` and `python -m pytest tests/e2e/ -m e2e -x` pass with zero failures.
</success_criteria>

<output>
After completion, create `.planning/quick/260317-waa-fix-e2e-tests/260317-waa-SUMMARY.md`
</output>
