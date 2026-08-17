# Phase 7: PEP8 Compliance - Research

**Researched:** 2026-02-27
**Domain:** Python code style enforcement with ruff
**Confidence:** HIGH

## Summary

This phase is straightforward: add a `[tool.ruff]` configuration section to `pyproject.toml`, run auto-fixes and formatting, manually resolve 6 remaining violations, move `ruff` and `ty` from runtime `[project] dependencies` to `[dependency-groups] dev`, and verify all tests still pass.

The codebase has 25 Python files (~1,070 lines of app code + ~1,000 lines of test code). Ruff 0.15.2 and ty 0.0.17 are already installed. With the target configuration (rules E, W, F, I, UP; line-length=120), there are 37 total violations. Of those, 30 are auto-fixable by `ruff check --fix` and `ruff format`. The remaining 6 require manual intervention: 4 re-export warnings in `__init__.py`, 1 unused variable assignment (side-effect call), and 1 mid-file import in a test file.

**Primary recommendation:** Add `[tool.ruff]` config first, then run `ruff check --fix`, then `ruff format`, then manually resolve the 6 remaining violations, then move ruff/ty to dev deps, then run tests.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STYLE-01 | Add `[tool.ruff]` config to `pyproject.toml` (rules: E, W, F, I, UP; line-length=120), run `ruff check --fix` and `ruff format`, move ruff/ty from runtime to dev dependencies | Full pipeline tested in temp copy -- 30/37 violations auto-fixed, 6 remaining need manual fixes (detailed below), all 72 tests pass after changes |
</phase_requirements>

## Standard Stack

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| ruff | 0.15.2 | Linter + formatter (replaces flake8, isort, pyupgrade, black) | Already installed; single tool for all style enforcement |
| ty | 0.0.17 | Type checker companion to ruff | Already installed; requirement says move to dev deps |

### Supporting
No additional tools needed. Ruff handles linting, import sorting, and formatting in one binary.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ruff format | black | Ruff is faster and already installed; black is separate dep |
| ruff check (I rules) | isort | Ruff handles import sorting natively; isort is separate dep |

**Installation:**
Already installed. Just need to move from `[project] dependencies` to `[dependency-groups] dev`:
```toml
# Remove from [project] dependencies:
#   "ruff>=0.15.2",
#   "ty>=0.0.17",

# Add to [dependency-groups] dev:
[dependency-groups]
dev = [
    # ...existing entries...
    "ruff >=0.15.2",
    "ty >=0.0.17",
]
```

Then regenerate lock file: `uv lock`

## Architecture Patterns

### Recommended Execution Order

The correct order is critical to avoid formatting fights:

1. **Add `[tool.ruff]` config** to `pyproject.toml`
2. **Manual fixes first** -- resolve the 6 non-auto-fixable violations (these changes would be overwritten or conflict if done after auto-fix)
3. **`ruff check --fix .`** -- auto-fix 30 violations (unused imports, import sorting)
4. **`ruff format .`** -- reformat all 25 files to consistent style
5. **Verify**: `ruff check .` exits 0, `ruff format --check .` exits 0
6. **Move deps** -- ruff/ty from runtime to dev in `pyproject.toml`
7. **`uv lock`** -- regenerate lock file
8. **Run tests** -- `python -m pytest tests/ -x`

### pyproject.toml Configuration

```toml
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP"]
```

Note: `target-version = "py312"` aligns with the project's `requires-python = ">=3.12"` and ensures UP rules suggest Python 3.12+ idioms.

### Anti-Patterns to Avoid
- **Running format before fix:** Import sorting by `ruff check --fix` (I001) changes line content, which `ruff format` then re-wraps. Run fix first, format second.
- **Skipping `ruff format --check`:** `ruff check` only checks lint rules. Formatting compliance requires the separate `ruff format --check` command.
- **Using `--unsafe-fixes` blindly:** There is 1 hidden unsafe fix (F841 in prompts.py). The unsafe fix would delete the entire `await service.chats.get_chat_owned(...)` call, removing the ownership check side effect. This MUST be handled manually.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Import sorting | Manual reordering | `ruff check --fix --select I` | isort-compatible, handles all edge cases |
| Line wrapping | Manual line breaks | `ruff format` | Consistent, deterministic output |
| Unused import removal | Manual grep | `ruff check --fix --select F401` | Handles re-export detection, conditional imports |

**Key insight:** Ruff's auto-fix handles 30 of 37 violations. The 6 manual fixes are all semantic decisions, not formatting busywork.

## Common Pitfalls

### Pitfall 1: Re-export F401 in `__init__.py`
**What goes wrong:** Ruff flags imports in `__init__.py` as unused when they're intentional re-exports for public API convenience.
**Why it happens:** Ruff's F401 rule cannot distinguish "import for re-export" from "accidentally imported."
**How to avoid:** Add `__all__` to `app/routers/__init__.py` listing the re-exported names. This tells ruff (and other tools) these imports are intentional.
**Concrete fix:**

```python
__all__ = ["chats_router", "health_router", "prompts_router", "root_router"]

from routers.health import router as health_router
from routers import chats_router
from routers import router as prompts_router
from routers.root import router as root_router
```

### Pitfall 2: F841 Unused Variable Hiding a Side Effect
**What goes wrong:** `chat = await service.chats.get_chat_owned(db, chat_id, user_id)` at `app/routers/prompts.py:82` is flagged as unused variable. The `--unsafe-fixes` option would delete the entire call, breaking the ownership check.
**Why it happens:** The call is made for its side effect (raising `ChatOwnershipError` on unauthorized access), not for its return value.
**How to avoid:** Remove the assignment but keep the call:
```python
await service.chats.get_chat_owned(db, chat_id, user_id)
```

### Pitfall 3: E402 Mid-File Import in Test
**What goes wrong:** `tests/unit/test_exception_handlers.py:94` has `from app.auth import ...` after module-level code (the `CASES` list and fixtures).
**Why it happens:** The import was placed near the tests that use it for readability.
**How to avoid:** Move the import to the top of the file with the other imports. The `UnsafeBase64Verifier` and `get_user_id` imports have no ordering dependency on the `CASES` list.

### Pitfall 4: Lock File Drift After Dependency Move
**What goes wrong:** Moving ruff/ty between dependency sections without running `uv lock` leaves the lock file inconsistent.
**Why it happens:** `uv.lock` tracks which dependency group each package belongs to.
**How to avoid:** Run `uv lock` after editing `pyproject.toml` dependency sections.

### Pitfall 5: Formatting Changes Breaking Test Assertions
**What goes wrong:** String-matching tests could break if ruff reformats string literals or multiline expressions.
**Warning signs:** Tests that compare exact output strings, error messages with specific formatting.
**How to avoid:** Run the full test suite (`python -m pytest tests/ -x`) after formatting. In this codebase, tests were confirmed to pass after auto-fix + format (72 passed in temp copy test).

## Code Examples

### Target `[tool.ruff]` Configuration
```toml
# Source: verified against ruff 0.15.2 installed on this system
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP"]
```

### Fixed `app/routers/__init__.py`

```python
__all__ = ["chats_router", "health_router", "prompts_router", "root_router"]

from routers.health import router as health_router
from routers import chats_router
from routers import router as prompts_router
from routers.root import router as root_router
```

### Fixed F841 in `app/routers/prompts.py:82`
```python
# Before (F841):
chat = await service.chats.get_chat_owned(db, chat_id, user_id)

# After:
await service.chats.get_chat_owned(db, chat_id, user_id)
```

### Fixed E402 in `tests/unit/test_exception_handlers.py`

```python
# Move to top of file alongside other imports:
from auth import UnsafeBase64Verifier, get_user_id
```

### Moving Dependencies in `pyproject.toml`
```toml
# Before:
[project]
dependencies = [
    # ...runtime deps...
    "ruff>=0.15.2",
    "ty>=0.0.17",
]

[dependency-groups]
dev = [
    "pytest >=9.0",
    # ...test deps only...
]

# After:
[project]
dependencies = [
    # ...runtime deps only, ruff/ty removed...
]

[dependency-groups]
dev = [
    "pytest >=9.0",
    # ...existing test deps...
    "ruff >=0.15.2",
    "ty >=0.0.17",
]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| flake8 + isort + black (3 tools) | ruff (1 tool) | ruff 0.1+ (2023) | Single config, faster execution, fewer deps |
| `setup.cfg` for tool config | `pyproject.toml` `[tool.ruff]` | PEP 518/621 | All config in one file |
| `[project.optional-dependencies] dev` | `[dependency-groups] dev` | PEP 735 (Python 3.12+, uv) | Cleaner separation, not installable as extras |

**Deprecated/outdated:**
- flake8 + isort + black combo: ruff replaces all three
- `[tool.ruff] select` at top level: moved to `[tool.ruff.lint] select` in ruff 0.2+

## Open Questions

None. This phase is fully scoped:
- Exact violations counted and categorized (37 total, 30 auto-fixable, 6 manual, 1 resolved by format)
- Manual fixes identified with concrete solutions
- Tests confirmed passing after changes
- Dependency move path clear (remove from `[project]`, add to `[dependency-groups] dev`, `uv lock`)

## Current Violation Inventory

| Code | Count | Auto-fixable | Files |
|------|-------|-------------|-------|
| I001 (unsorted imports) | 20 | Yes (`--fix`) | 14 files across app/ and tests/ |
| F401 (unused imports) | 11 | 7 yes, 4 no (re-exports) | app/chats.py, app/routers/__init__.py, app/routers/prompts.py, tests/*.py |
| E501 (line too long) | 2 | 1 by format, 1 by F401 fix | app/errors.py, tests/unit/test_services.py |
| F841 (unused variable) | 1 | No (side effect) | app/routers/prompts.py:82 |
| E402 (import not at top) | 1 | No (semantic) | tests/unit/test_exception_handlers.py:94 |
| W292 (no newline at EOF) | 1 | Yes (`--fix`) | app/resilience.py |
| UP035 (deprecated import) | 1 | Yes (`--fix`) | app/routers/health.py |
| **Total** | **37** | **30 auto + 1 format** | **6 manual** |

## Sources

### Primary (HIGH confidence)
- Direct `ruff check` and `ruff format` execution against codebase -- exact violation counts
- Temp-copy pipeline test -- confirmed auto-fix + format flow, 72/72 tests pass
- `ruff --version` output: ruff 0.15.2
- `pyproject.toml` inspection -- current dependency layout

### Secondary (MEDIUM confidence)
- Ruff configuration syntax (`[tool.ruff.lint] select`) -- verified by running with `--select` flags, consistent with ruff 0.2+ convention

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- ruff already installed, versions confirmed, config syntax verified by execution
- Architecture: HIGH -- full pipeline tested in temp copy, exact violation counts known
- Pitfalls: HIGH -- every non-auto-fixable violation inspected, root cause understood, fix verified

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable domain, ruff config rarely changes between patch versions)
