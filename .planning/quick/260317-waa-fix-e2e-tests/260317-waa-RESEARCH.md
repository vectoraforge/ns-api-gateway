# Quick Task: Fix E2E Tests - Research

**Researched:** 2026-03-17
**Domain:** Test infrastructure, pydantic-settings env var resolution, SQLAlchemy asyncpg
**Confidence:** HIGH

## Summary

All e2e tests fail before reaching any test body. There are **three independent root causes**, two in committed code and one introduced by uncommitted changes currently in the working tree. The uncommitted changes were an incomplete attempt to fix one of the committed bugs but introduced a new one.

**Primary recommendation:** Fix all three issues together in a single coherent commit, reverting the broken uncommitted changes and applying correct fixes.

## Root Causes

### Issue 1: asyncpg `options` query parameter (COMMITTED - HIGH confidence)

**File:** `app/config.py` line 31 (DatabaseConfig.url property)
**Introduced in:** commit `7a1ed7e` (feat(260317-nbq): add api_key field to JWTConfig and config.yaml)

The `DatabaseConfig.url` property generates:
```
postgresql+asyncpg://...?options=-csearch_path=api
```

SQLAlchemy's asyncpg dialect parses `?options=` from the URL and passes it as a keyword argument to `asyncpg.connect()`, which rejects it:
```
TypeError: connect() got an unexpected keyword argument 'options'
```

Raw `asyncpg.connect()` handles the URL fine, but SQLAlchemy's `PGDialect_asyncpg.connect()` extracts query params and passes them as kwargs, and asyncpg does not accept `options` as a kwarg.

**Fix:** Use `connect_args={"server_settings": {"search_path": "api"}}` when creating the engine instead of embedding `options` in the URL. Verified working:
```python
engine = create_async_engine(url_without_options, connect_args={"server_settings": {"search_path": schema}})
```

The `DatabaseConfig.url` property should drop the `?options=` query param, and a separate property or the callers should pass `connect_args`. Alternatively, store `server_settings` as a property on `DatabaseConfig`.

### Issue 2: JWT api_key always empty string (COMMITTED - HIGH confidence)

**File:** `app/config.py` (JWTConfig) + `config/config.yaml`
**Introduced in:** commit `7a1ed7e`

In the committed code, `config.yaml` has `api_key: ""` under `jwt`. When `MainConfig.load_config()` creates `AppConfig(**yaml_data, ...)`, the `api_key: ""` from YAML is passed as an explicit kwarg, which takes **precedence over env vars** in pydantic-settings. So `JWT_API_KEY` from `.env` is ignored.

The e2e conftest reads `api_key = _app_config.jwt.api_key` and asserts it's truthy, which fails:
```
AssertionError: JWT_API_KEY env var required for e2e tests
```

**Fix:** Remove `api_key` from `config.yaml` entirely (don't even include it as empty string). The env var `JWT_API_KEY` will then be picked up by pydantic-settings via `env_nested_delimiter="_"`.

**However**, this leads to Issue 3.

### Issue 3: env_nested_max_split=1 not inherited by AppConfig (UNCOMMITTED - HIGH confidence)

**File:** `app/config.py` (BaseConfig.model_config)

The uncommitted changes add `env_nested_max_split=1` to `BaseConfig.model_config`. This was intended to make `JWT_PROJECT_ID` -> `jwt.project_id` instead of `jwt.project.id`. **But it does not work.**

`SettingsConfigDict` fills in defaults for all unset keys during metaclass processing. When `AppConfig(BaseConfig)` is defined, pydantic-settings merges configs and the explicit `env_nested_max_split=1` from `BaseConfig` gets reset to `None` (the default). Verified:
```python
>>> AppConfig.model_config.get('env_nested_max_split')
None
```

So `JWT_PROJECT_ID` is still split as `jwt.project.id` and validation fails:
```
jwt.project_id: Field required [type=missing, input_value={'project': {'id': 'test-...
```

**Fix:** Each `BaseSettings` subclass that needs `env_nested_max_split` must declare it explicitly in its own `model_config`. But this is fragile with `_` as delimiter and multi-word field names like `project_id`.

**Better fix:** Keep `project_id` and `api_key` in `config.yaml` (not as empty strings, but with real/default values), OR read them via env var aliases rather than relying on nested delimiter splitting. The cleanest approach is to use `env_prefix` or `AliasChoices` on the specific fields.

### Issue 4: config.resilience reference (UNCOMMITTED - HIGH confidence)

**File:** `app/api/main.py` lines 48, 57

The uncommitted `main.py` changes `config.model.resilience` to `config.resilience`. But `AppConfig` has no top-level `resilience` field -- it's nested at `config.model.resilience`. This would cause `AttributeError` at startup.

**Fix:** Revert to `config.model.resilience`.

### Issue 5: JWTConfig defaults (UNCOMMITTED - LOW severity)

**File:** `app/config.py` JWTConfig

The uncommitted changes set `audience: str = None` and `issuer: str = None`. While this works (the model_validator replaces None), it's technically a type annotation lie (`str` annotated but `None` default). Should be `str | None = None`.

## Recommended Fix Strategy

1. **Revert all uncommitted changes** -- they are an incomplete fix attempt that introduced new bugs.

2. **Fix the DB URL** (Issue 1): Change `DatabaseConfig` to NOT include `?options=` in the URL. Add a `server_settings` property instead:
   ```python
   @property
   def url(self) -> str:
       return (f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
               f"@{self.host}:{self.port}/{self.name}")

   @property
   def connect_args(self) -> dict:
       return {"server_settings": {"search_path": self.db_schema}}
   ```
   Then update `main.py` lifespan and `e2e/conftest.py` `ensure_tables` to pass `connect_args=config.db.connect_args`.

3. **Fix JWT api_key** (Issue 2): Remove `api_key: ""` from `config.yaml`. Keep `project_id` in YAML (it has a real value). For `api_key`, either:
   - (a) Leave it out of YAML so env vars can fill it via pydantic-settings, OR
   - (b) Add a `validation_alias` to read directly from `JWT_API_KEY` env var

   Option (a) is simpler but depends on `env_nested_delimiter="_"` working correctly for `JWT_API_KEY` -> `jwt.api_key`. Since `API_KEY` has one underscore, with default delimiter `_` it splits to `jwt.api.key` (wrong). So option (a) requires `env_nested_max_split=1` on `AppConfig` specifically (not just BaseConfig).

   **Recommended approach:** Keep `api_key` with empty default in JWTConfig (`api_key: str = Field(default="")`), remove it from `config.yaml`, and set `env_nested_max_split=1` directly on `AppConfig.model_config` (not just BaseConfig):
   ```python
   class AppConfig(BaseConfig):
       model_config = SettingsConfigDict(env_nested_delimiter="_",
                                          env_nested_max_split=1)
   ```
   But verify this doesn't break other env vars like `DB_HOST`, `DB_PORT` etc. With `max_split=1`, `DB_HOST` -> `db.host` (correct), `DB_PASSWORD` -> `db.password` (correct). `OPENAI_API_KEY` -> `openai.api_key` (ignored since no `openai` field -- fine).

## Verification Commands

```bash
# Unit tests (should stay green)
python -m pytest tests/unit/ -x --tb=short

# E2e tests (need real infra -- Postgres + Firebase)
python -m pytest tests/e2e/ -m e2e -x --tb=short
```

## Sources

### Primary (HIGH confidence)
- Direct testing of asyncpg 0.31.0 + SQLAlchemy 2.0.46 connection behavior
- Direct testing of pydantic-settings 2.13.1 `env_nested_max_split` inheritance
- Committed code inspection via `git show`
- [SQLAlchemy PostgreSQL docs](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html) - asyncpg `server_settings` via `connect_args`
- [pydantic-settings env_nested_delimiter docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
