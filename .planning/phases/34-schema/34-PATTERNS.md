# Phase 34: Schema - Pattern Map

**Mapped:** 2026-08-19
**Files analyzed:** 11 (7 created, 1 deleted, 2 modified, 1 conditional)
**Analogs found:** 8 / 11 (3 mechanisms have no in-repo precedent at all)

---

## File Classification

| New/Modified File | Action | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|--------|------|-----------|----------------|---------------|
| `migrations/20260818_01_initial-release.sql` | create | migration (DDL) | batch / one-shot transactional apply | `migrations/20260322_01_initial-release.sql` | **exact** |
| `migrations/20260322_01_initial-release.sql` | **delete** | migration (DDL) | — | — (P-3: must be `git rm`'d in the same commit) | n/a |
| `tests/schema/__init__.py` | create | test package marker | — | `tests/unit/__init__.py`, `tests/e2e/__init__.py` (both 0 bytes) | **exact** |
| `tests/schema/conftest.py` | create | test config / fixture | resource lifecycle + per-test transaction rollback | `tests/e2e/conftest.py` (fixture *shape* only — **never** its imports) | role-match |
| `tests/schema/helpers.py` | create | test utility (seeding) | CRUD insert, returns id | `tests/e2e/conftest.py:92-120` (`create_chat`) | partial (SQLModel, not raw driver) |
| `tests/schema/test_inventory.py` | create | test (introspection) | read-only query + exact-set assert | `tests/unit/test_exception_handlers.py` (module-level case table + parametrize) | role-match |
| `tests/schema/test_constraints.py` | create | test (negative / rejection) | CRUD write, expect exception | `tests/unit/test_usage.py:43-50`, `tests/unit/test_models.py:39-42` | role-match |
| `tests/schema/test_apply_rollback.py` | create | test (lifecycle) | batch apply/rollback | `tests/e2e/test_health.py` (minimal marker + class shape) | partial |
| `pyproject.toml` | modify | config | — | itself, `[tool.pytest.ini_options] markers` lines 58-60 | **exact** (in-place list extension) |
| `.planning/PROJECT.md` | modify | docs | — | itself, "Known areas for future work" lines 161-165 | **exact** (append a bullet) |
| `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` | modify (conditional) | docs | — | — | CONFLICT-1 — planner surfaces, does not decide |

---

## Pattern Assignments

### `migrations/20260818_01_initial-release.sql` (migration, batch DDL)

**Analog:** `migrations/20260322_01_initial-release.sql` — same tool, same schema, same one-shot-apply data flow. This is the file being replaced; copy its *shape*, replace its *content*.

**Header pattern** (analog lines 1-4) — copy this exact 4-line prologue, changing only the description text:

```sql
-- initial release with users, subscriptions, and usage
-- depends:

-- migrate: apply
```

Line 1 is the one-line description, line 2 is `-- depends:` (empty per D-03), then a blank line, then the `-- migrate: apply` marker. The regex at `pogo_core/migration.py:49` requires description on line 1 and `-- depends:` on line 2 with nothing between them (RESEARCH Pattern 2 / P-2). D-04 rewrites line 1 only. Any extra prose goes *after* `-- depends:`.

**Schema + enum block pattern** (analog lines 6-11):

```sql
CREATE SCHEMA IF NOT EXISTS core;

CREATE TYPE core.chat_role AS ENUM ('human', 'ai');
CREATE TYPE core.subscription_plan AS ENUM ('free', 'silver', 'gold', 'platinum');
CREATE TYPE core.subscription_provider AS ENUM ('apple');
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');
```

Conventions to carry forward: `CREATE SCHEMA IF NOT EXISTS`; every type schema-qualified as `core.<snake_case>`; one `CREATE TYPE` per line; all enum types created before any table. Two of these four survive verbatim into v2.0 (`core.chat_role`, `core.subscription_status` — RESEARCH Pattern 1); `core.subscription_plan` is deleted (SCHEMA-07) and `core.subscription_provider` gains a second label.

**Table + index pattern** (analog lines 25-33):

```sql
CREATE TABLE core.chats (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id),
    title TEXT NOT NULL,
    lang TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_chats_user_id ON core.chats (user_id);
```

Conventions: 4-space column indent, uppercase SQL keywords, `REFERENCES core.x (id)` with a space before the paren, index named `ix_<table>_<columns>`, index declared immediately after its table, blank line between statements. `core.chats`, `core.messages` (analog lines 35-41) and `ix_chats_user_id` are among the seven baseline survivors the new file must reproduce verbatim (RESEARCH Pattern 1 table).

**Partial unique index pattern** (analog lines 56-58) — the exact shape the five v2.0 unique indexes need:

```sql
CREATE UNIQUE INDEX ix_subscriptions_user_provider_active
    ON core.subscriptions (user_id, provider)
    WHERE status NOT IN ('expired', 'revoked');
```

Note: this *specific* index is NOT recreated in v2.0 (`00-schema.md:333`) — copy the formatting (continuation lines indented 4, `WHERE` on its own line), not the index.

**Rollback pattern** (analog lines 82-94):

```sql
-- migrate: rollback

DROP TABLE IF EXISTS core.subscription_events;
DROP TABLE IF EXISTS core.subscriptions;
...
DROP SCHEMA IF EXISTS core;
```

D-05 **deliberately replaces** this ~11-statement reverse-order list with two statements, because the list drifts:

```sql
-- migrate: rollback

DROP SCHEMA IF EXISTS audit CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
```

Keep the analog's `-- migrate: rollback` marker followed by a blank line, and the `IF EXISTS` idiom.

**What has no analog here:** banner-comment section dividers (D-06), inline comments inside a statement, and a `CREATE SCHEMA audit`. The baseline migration has zero comments in its body. Use RESEARCH Code Example 1 for the banner shape — verified safe: column-0 comments are stripped by `pogo_core/migration.py:22` before reaching PostgreSQL, indented comments pass through, and banner-only blocks collapse to `""` and are skipped.

---

### `tests/schema/__init__.py` (test package marker)

**Analog:** `tests/unit/__init__.py` and `tests/e2e/__init__.py` — both exist and both are **0 bytes**.

**Pattern:** create an empty file. This is load-bearing, not decorative — see the *Test module import rooting* shared pattern below.

---

### `tests/schema/conftest.py` (test config, resource lifecycle + per-test rollback)

**Analog:** `tests/e2e/conftest.py` — the only conftest in the repo that manages real infrastructure. **Copy its fixture architecture; copy none of its imports** (D-13: zero `nativespeaker.api` imports).

**Imports pattern to AVOID** (analog lines 1-13) — this is exactly what makes `tests/e2e/` unrunnable while the app is broken:

```python
import os
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.app.main import app          # <-- the poison line
from nativespeaker.api.config import EnvironmentConfig
from nativespeaker.api.models import Chat, ChatRole, Message, User
```

Carry forward only the ordering convention: stdlib block, blank line, third-party block, blank line, first-party block (ruff `I` rule, `pyproject.toml:67`). `tests/schema/conftest.py`'s third block is empty.

**Session-scoped setup fixture pattern** (analog lines 16-19) — one-line docstring, leading underscore for private fixtures:

```python
@pytest.fixture(scope="session")
def _app_config():
    """Load app config once -- single source of truth for DB URL, Firebase keys, etc."""
    return EnvironmentConfig().app_config
```

**Per-test transaction rollback pattern** (analog lines 66-89) — the *intent* `tests/schema/` reproduces on a raw connection:

```python
@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def _db_transaction(_app_lifespan):
    """Wrap each test in a transaction that rolls back on completion."""
    original_factory = _app_lifespan.state.session_factory
    engine = original_factory.kw["bind"]

    async with engine.connect() as connection:
        transaction = await connection.begin()
        test_factory = async_sessionmaker(
            bind=connection,
            class_=SQLModelAsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        _app_lifespan.state.session_factory = test_factory
        try:
            yield test_factory
        finally:
            _app_lifespan.state.session_factory = original_factory
            await transaction.rollback()
```

Structural elements to keep: `begin()` before `yield`, `try/finally` with `rollback()` in `finally`, one-line docstring. Structural elements to **change**: the async engine/sessionmaker becomes `asyncpg.connect()` + `conn.transaction()`, and the `finally` block needs the P-6 swallow (`except Exception: pass` around `tx.rollback()`) because deferred-FK failures poison the transaction object. See RESEARCH Code Example 2 for the verified target shape.

**Loop-scope convention observed in the analog:** every async fixture carries an explicit `loop_scope=` (`scope="module", loop_scope="module"` at lines 44 and 51; `loop_scope="module"` at line 66) because `pyproject.toml:56` sets `asyncio_default_fixture_loop_scope = "function"`. RESEARCH's recommendation sidesteps this entirely with a **sync** session fixture wrapping `asyncio.run()` plus a plain function-scoped `@pytest_asyncio.fixture` — no `loop_scope=` anywhere.

**No analog for:** `asyncpg.connect()`, `CREATE DATABASE` / `DROP DATABASE … WITH (FORCE)`, and `pogo_core.util.testing.apply()`. Zero precedent in the repo (`grep -rn asyncpg src tests` returns exactly one hit — a DSN f-string in `src/nativespeaker/api/config.py:29`). Use RESEARCH Code Example 2 verbatim; it was executed against this project's own interpreter and pytest config.

**DSN construction reference** (`src/nativespeaker/api/config.py:27-30`) — the only DSN-building code in the repo, and the reason the fixture must strip the SQLAlchemy dialect prefix:

```python
    @property
    def url(self) -> str:
        return (f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
                f"@{self.host}:{self.port}/{self.name}")
```

`asyncpg.connect()` needs `postgres://` or `postgresql://` — **not** `postgresql+asyncpg://`. The env var names are fixed by `.env.example:4-8`: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`. `.env` is absent and gitignored, so `env_files = [".env"]` (`pyproject.toml:54`) loads nothing — the fixture needs a default for each (see `docker-compose.yml`, `postgres:17` on port 5432).

---

### `tests/schema/helpers.py` (test utility, CRUD seeding)

**Analog:** `tests/e2e/conftest.py:92-120` — `create_chat`, the repo's only seed helper.

**Seed-helper pattern** (analog lines 92-120, abridged):

```python
async def create_chat(factory, user_id: str):
    """Insert a chat with human+AI message pair, return chat_id.

    Creates a User record for the given Firebase UID if one doesn't exist,
    then creates a Chat referencing the user's UUID primary key.
    """
    async with factory() as session:
        ...
        chat_id = uuid4()
        chat = Chat(id=chat_id, user_id=user.id, title="test phrase")
        ...
        session.add(chat)
        await session.commit()
    return chat_id
```

Conventions to carry forward: module-level `async def`, first parameter is the connection/factory handle, **returns the new id**, docstring with a one-line summary then a blank line then detail. D-15 asks for exactly this signature shape (`insert_user(conn)`, `insert_tier(conn)`, `insert_grant(conn, ...)` → new id).

Conventions to **drop**: the `async with factory() as session:` / `session.add()` / `await session.commit()` SQLModel mechanism, and the get-or-create lookup. `tests/schema/helpers.py` uses `await conn.execute("INSERT INTO core.users (...) VALUES ($1, ...)", ...)` with asyncpg's `$1` positional placeholders (see RESEARCH Code Example 2's deferred-constraint snippet for the verified call shape) and must **not** commit — the per-test transaction owns the boundary.

Note: `create_chat` lives *inside* `conftest.py`, not in a separate module. D-15 and RESEARCH's structure both put the schema helpers in a dedicated `helpers.py`; that is a deliberate improvement, not a break with convention (the import mechanism is identical either way — see below).

---

### `tests/schema/test_inventory.py` (test, introspection / read-only query)

**Analog:** `tests/unit/test_exception_handlers.py` — the only test in the repo built around a module-level data table plus `parametrize`, which is the shape an exact-set inventory suite wants.

**Module-level case table pattern** (analog lines 29-46):

```python
CASES = [
    ("missing_token", AuthenticationError("Missing Bearer token"), 401),
    ("invalid_token", AuthenticationError("Invalid token"), 401),
    ...
    ("permanent_llm", PermanentLLMError("bad response format"), 503),
]
```

**Parametrized test pattern** (analog lines 76-89) — note the assertion-message convention on the non-obvious assert:

```python
@pytest.mark.parametrize("name,exc,expected_status", CASES)
def test_handler(handler_client, name, exc, expected_status):
    response = handler_client.get(f"/raise/{name}")
    assert response.status_code == expected_status
    body = response.json()
    assert list(body.keys()) == ["code"], f"Expected only 'code' key, got {list(body.keys())}"
    assert body["code"] in {
        "invalid_request",
        "unauthorized",
        ...
    }
```

Carry forward: `UPPER_SNAKE` module constants for expected data, `@pytest.mark.parametrize("a,b,c", CASES)` with a comma-joined single string, an explanatory `f`-string on asserts whose failure output would otherwise be opaque. Put RESEARCH Code Example 4's `EXPECTED_ENUM_LABEL_COUNTS`, `EXPECTED_CORE_TABLES`, `EXPECTED_AUDIT_TABLES`, `EXPECTED_CORE_INDEXES`, `EXPECTED_AUDIT_INDEXES`, `EXPECTED_INDEX_PREDICATES` at module level in exactly this style — copied verbatim from the live capture, never derived from spec prose (RESEARCH Anti-Patterns).

**Class-grouping pattern** (`tests/unit/test_usage.py:13-25`) — for the non-parametrized inventory groups:

```python
class TestQuotaExceededError:
    """Error contract: QuotaExceededError returns 429 with quota_exceeded code."""

    def test_status_code(self):
        assert QuotaExceededError.status_code == 429
```

`Test<Subject>` classes, no `unittest.TestCase` base, one-line class docstring stating the invariant. Applies to the SCHEMA-07 legacy-absence group (`-k legacy` selects it, per the VALIDATION test map).

**Module docstring pattern** (`tests/unit/test_usage.py:1`):

```python
"""Tests for monthly quota enforcement via require_quota dependency and QuotaExceededError contract."""
```

Single line, no blank line before the imports.

**No analog for:** `pg_catalog` / `information_schema` queries. Use RESEARCH Code Example 3 (`ENUMS`, `TABLES`, `INDEXES`, `USER_TRIGGERS`, `VIEWS`, `MATVIEWS`, `GONE`) as `UPPER_SNAKE` module constants — the naming style already matches the analog's `CASES`.

---

### `tests/schema/test_constraints.py` (test, negative / rejection)

**Analog:** `tests/unit/test_usage.py:43-50` (async + `pytest.raises`) and `tests/unit/test_models.py:39-42` (`pytest.raises` with message inspection).

**Async rejection pattern** (`tests/unit/test_usage.py:43-50`):

```python
    @pytest.mark.asyncio
    async def test_require_quota_raises_when_exhausted(self, mock_db, mock_config):
        """require_quota raises QuotaExceededError when try_increment returns False."""
        mock_usage = AsyncMock()
        mock_usage.try_increment = AsyncMock(return_value=False)
        with patch.object(dep_module, "UsageDB", return_value=mock_usage):
            with pytest.raises(QuotaExceededError):
                await require_quota(user=TEST_USER, db=mock_db, config=mock_config)
```

Carry forward: one-line docstring naming the exact behavior, `with pytest.raises(<ExceptionClass>):` wrapping the single offending call. Drop the explicit `@pytest.mark.asyncio` — `asyncio_mode = "auto"` (`pyproject.toml:55`) makes it optional; `tests/unit/test_usage.py` includes it, `tests/e2e/` uses `@pytest.mark.asyncio(loop_scope="module")` only to pin the loop. A plain `async def test_...` is sufficient here.

**Exception-message inspection pattern** (`tests/unit/test_models.py:39-42`) — use sparingly:

```python
    def test_missing_phrase(self):
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(lang="en")
        assert "phrase" in str(exc_info.value)
```

Applies where the *index name* must be confirmed (`ix_access_grants_one_active_per_user`, `ix_access_grants_one_free_grant_per_user_source`, `access_grants_anti_abuse_grant_source_check`) — index and named-constraint names are stable. Do **not** apply it to auto-generated CHECK names (`auth_events_check1`, `access_grants_check` …); those are positional and order-fragile (P-8). Assert the exception class only.

**Deliberate-omission comment convention** (`tests/unit/test_models.py:61-64`) — copy this when a test intentionally writes an invalid row:

```python
    def test_issue_missing_fields(self):
        with pytest.raises(ValidationError):
            # Omitting the required field is the point of this test.
            Issue(text_part="going to home")  # ty: ignore[missing-argument]
```

**No analog for:** the explicit-`BEGIN`/`COMMIT` shape the three deferred-constraint cases require (P-6: LB, E1/E2, OWN). Use RESEARCH Code Example 2's second snippet verbatim; do not call `ROLLBACK` after a failed `COMMIT`.

---

### `tests/schema/test_apply_rollback.py` (test, lifecycle / batch)

**Analog:** `tests/e2e/test_health.py` — the repo's smallest real-infrastructure test module, and the right template for a 2-3 test lifecycle module.

**Full analog** (all 11 lines):

```python
import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio(loop_scope="module")
class TestHealthEndpoint:
    async def test_health_ready_returns_up(self, async_client):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "up"}
```

Carry forward: module-level `pytestmark = pytest.mark.<marker>` immediately after the imports, a `Test<Subject>` class, `async def test_...` methods taking fixtures as parameters. Substitute `pytest.mark.schema` for `pytest.mark.e2e` and drop the `@pytest.mark.asyncio(loop_scope=...)` decorator (no module-scoped async fixtures in this suite).

**No analog for:** `pogo_core.util.testing.rollback(...)` and the "exactly one `.sql` in `migrations/`" assertion (`len(list(MIGRATIONS.glob("*.sql"))) == 1`, P-3). Both come from RESEARCH.

---

### `pyproject.toml` (config)

**Analog:** itself. The `markers` list already exists at lines 58-60 — extend it in place:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
env_files = [".env"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "-v --tb=short -m 'not e2e'"
markers = [
    "e2e: marks end-to-end tests requiring real infrastructure (deselect with -m 'not e2e')",
]
```

Convention: one marker per line, `"<name>: <sentence description> (deselect with -m 'not <name>')"`. The new entry mirrors it exactly.

**Load-bearing detail for the planner:** `addopts` deselects only `e2e`. If `tests/schema/` carries `pytestmark = pytest.mark.schema`, a bare `pytest` invocation still **selects** it and will fail on any machine without PostgreSQL. Either extend `addopts` to `-m 'not e2e and not schema'` (and run the suite explicitly as `pytest tests/schema -m schema`), or leave `addopts` alone and accept that the default run requires a database. RESEARCH does not decide this; the plan should state which, because it changes the "quick run command" in every task's verification step.

---

### `.planning/PROJECT.md` (docs)

**Analog:** itself, lines 161-165. Append one bullet to the existing list:

```markdown
Known areas for future work:
- Proactive quota warnings via `X-RateLimit-Remaining` header
- Grace period transparency in `GET /users/me` — `core.subscriptions.status` models `grace_period`, but `04-users-me.md` does not surface it in the response
- Webhook retry reconciliation via App Store Server API polling
- Startup exhaustiveness check for quota config (QUOTA-06)
```

Convention: single-line bullet, backticked identifiers, em-dash for the "but here is the catch" clause, a parenthesized requirement id where one exists. D-11's entry names `REVOKE DELETE ON core.external_identities` and the fact that no database role exists in this repo.

**Also present at lines 176-215:** a `## Key Decisions` table whose last row already records the migration-rewrite override (`| Rewrite 20260322_01_initial-release.sql in place … | — Pending — v2.0 |`). D-02 renames rather than rewrites in place, so that row's text and CONFLICT-1 are the same conflict surfacing in a third file. Same disposition: surface, do not silently resolve.

**Out of scope but worth knowing:** the repo-root `PROJECT.md` (a different file from `.planning/PROJECT.md`) has a `## Data Model` section at lines 150-169 that is already badly stale — it describes `migrations/001_create_tables.sql`, `pg_partman` daily partitions, and a `messages.role` of `human | assistant`. None of that has existed since v1.6. It was stale before this phase and the phase boundary does not touch it. Do not expand scope; do not use it as a schema reference.

---

## Shared Patterns

### Test module import rooting (applies to every file under `tests/schema/`)

**Source:** `tests/e2e/test_isolation.py:1-5` and `tests/unit/test_usage.py:10`

```python
import pytest

from e2e.conftest import create_chat

pytestmark = pytest.mark.e2e
```

```python
from unit.conftest import TEST_USER
```

Cross-module test imports are rooted at `tests/`, **not** at the repo root: `from e2e.conftest import …`, `from unit.conftest import …`. This works because `tests/` has no `__init__.py` while `tests/unit/` and `tests/e2e/` do, so pytest's rootdir walk stops at `tests/` and inserts it on `sys.path`.

**Consequence:** `tests/schema/__init__.py` is mandatory, and the import in the test modules is `from schema.helpers import insert_grant, insert_tier, insert_user` — not `from tests.schema.helpers import …`. Getting this wrong produces a `ModuleNotFoundError` at collection.

### Marker declaration (applies to all three `tests/schema/test_*.py`)

**Source:** `tests/e2e/test_isolation.py:5`, `tests/e2e/test_health.py:3`, `tests/e2e/test_chat_queries.py:5` — every e2e module, without exception

```python
pytestmark = pytest.mark.e2e
```

Module-level, placed after the imports and before any constant or class. `tests/schema/` uses `pytestmark = pytest.mark.schema`. Never reuse `e2e` — `addopts` deselects it and this phase's only proof would vanish silently.

### Import ordering and formatting (applies to all Python files)

**Source:** `pyproject.toml:62-67`

```toml
[tool.ruff]
line-length = 120
target-version = "py314"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP"]
```

`I` enforces isort ordering: stdlib / third-party / first-party, blank line between groups, alphabetical within group. Line length 120. Every existing test file conforms; `ruff check` is a real gate. Note also the repo-wide comment style: `--` in place of an em dash in code comments and docstrings (`tests/conftest.py:1`, `tests/e2e/conftest.py:18`), and no emojis anywhere (AGENTS.md).

### Docstring convention (applies to all fixtures, helpers, and tests)

**Sources:** `tests/e2e/conftest.py:18,45,53,61,68,93`; `tests/unit/test_usage.py:1,14,28,45`

Every fixture and every helper has a one-line docstring stating what it provides. Test methods have a one-line docstring stating the behavior asserted — but only where the method name alone is not self-explanatory (`tests/unit/test_models.py` omits them entirely; `tests/unit/test_usage.py` includes them). Multi-line docstrings use summary line, blank line, detail (`tests/e2e/conftest.py:93-97`).

### Private fixture naming

**Source:** `tests/e2e/conftest.py:17,45,52,67` — `_app_config`, `_app_lifespan`, `_db_transaction`

Fixtures that exist only to build the environment carry a leading underscore; fixtures a test names directly (`async_client`, `test_user_id`, `firebase_token`) do not. For `tests/schema/`: `_admin_dsn` / `_schema_db_uri` private, `conn` public.

---

## No Analog Found

Three mechanisms this phase needs have **zero precedent anywhere in the repository**. For these the planner must use RESEARCH.md, which executed all three against a live PostgreSQL 16.2 instance this session.

| Mechanism | Files affected | Reason | Use instead |
|-----------|----------------|--------|-------------|
| Raw `asyncpg` connection in a test | `tests/schema/conftest.py`, `helpers.py`, all three `test_*.py` | `grep -rn asyncpg src tests` returns exactly one hit — a DSN f-string at `src/nativespeaker/api/config.py:29`. Every DB access in the repo goes through SQLModel/SQLAlchemy. | RESEARCH Code Example 2 (verified against this project's interpreter and pytest config, 3/3 passed) |
| `pg_catalog` / `information_schema` introspection | `tests/schema/test_inventory.py` | No introspection query exists anywhere in `src/` or `tests/`. Schema correctness has never been asserted programmatically in this project. | RESEARCH Code Example 3 (queries) + Code Example 4 (expected sets, captured live) |
| In-process pogo apply / rollback (`pogo_core.util.testing`) | `tests/schema/conftest.py`, `test_apply_rollback.py` | pogo has only ever been driven by hand from the CLI. `grep -rn "migrat\|pogo" k8s/` finds nothing — no migration Job, no initContainer. | RESEARCH "Don't Hand-Roll" table + P-4 (use `pogo_core.util.testing`, **not** `pogo_migrate.testing`) |

Additionally, `migrations/` has never held a scratch-database lifecycle (`CREATE DATABASE` / `DROP DATABASE … WITH (FORCE)`) and `tests/` has never created one. D-14's session fixture is genuinely new construction.

---

## Metadata

**Analog search scope:** `migrations/`, `tests/` (all three packages), `src/nativespeaker/api/`, `pyproject.toml`, `docker-compose.yml`, `.env.example`, `.planning/PROJECT.md`, `PROJECT.md`, `.planning/milestones/v1.6-phases/27-migration/`

**Files scanned:** 21 read in full or in targeted ranges; 2 grep sweeps across `src/` + `tests/` (`asyncpg`, `parametrize`)

**Analog ranking applied:** same role + same data flow first (migration → migration, package marker → package marker, config → config); same role, different mechanism second (e2e conftest → schema conftest); most-recently-modified preferred (`tests/unit/test_usage.py` and `test_exception_handlers.py` are v1.6-era and reflect current conventions, unlike `tests/e2e/conftest.py`'s pre-v1.6 `create_chat`).

**Precedent note:** Phase 27 (v1.6) performed the same migration-rewrite operation on the same file. Its summary (`.planning/milestones/v1.6-phases/27-migration/27-01-SUMMARY.md`) records two `patterns-established` entries that still bind: *"PG enum type naming: `core.{python_strenum_class_name_snake_case}`"* and *"Rollback order: tables in reverse dependency order, then types, then schema"*. D-05 knowingly supersedes the second with two `DROP SCHEMA … CASCADE` statements. Phase 27 shipped **no schema tests** — validation was a one-off manual comparison against `models.py`. That gap is exactly what D-12/D-17 close, and it is why no test analog for DDL conformance exists in this repo.

**Pattern extraction date:** 2026-08-19
