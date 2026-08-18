---
phase: quick
plan: 260317-kdo
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/unit/test_config.py
  - .env.example
autonomous: true
must_haves:
  truths:
    - "All unit tests pass (pytest tests/unit/ exits 0)"
    - "test_main_config_loads_yaml_and_content exercises the directory-based MainConfig constructor"
    - "test_main_config_missing_file exercises nonexistent directory"
    - ".env.example matches current MainConfig fields (CONFIG_DIR only, no PROMPT_PATH / EXAMPLES_PATH)"
  artifacts:
    - path: "tests/unit/test_config.py"
      provides: "Fixed MainConfig tests using config_dir directory approach"
    - path: ".env.example"
      provides: "Updated env example matching new config fields"
  key_links:
    - from: "tests/unit/test_config.py"
      to: "app/config.py:MainConfig"
      via: "constructor kwargs matching MainConfig fields"
      pattern: "MainConfig\\(config_dir="
---

<objective>
Fix the failing unit test `test_main_config_loads_yaml_and_content` and update `.env.example` to match the refactored `MainConfig`.

Purpose: `MainConfig` was refactored from separate `config_dir`/`prompt_path`/`examples_path` path fields to a single `config_dir` directory with `config_filename`/`prompt_filename`/`examples_filename` string fields. The test still passes the old kwargs, causing `extra_forbidden` validation errors. The `.env.example` also still lists the removed env vars.

Output: Green unit test suite, consistent `.env.example`.
</objective>

<execution_context>
@/Users/vay/.claude/get-shit-done/workflows/execute-plan.md
@/Users/vay/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@app/config.py (MainConfig with config_dir + filename fields)
@tests/unit/test_config.py (failing test using old prompt_path/examples_path kwargs)
@.env.example (still lists PROMPT_PATH, EXAMPLES_PATH)
</context>

<interfaces>
<!-- Current MainConfig constructor signature (from app/config.py) -->
```python
class MainConfig(BaseConfig):
    config_dir: Path = Field(default=Path("config/"))
    config_filename: str = Field(default="config.yaml")
    prompt_filename: str = Field(default="prompt.txt")
    examples_filename: str = Field(default="examples.yaml")
    app_config: AppConfig | None = None
```
<!-- MainConfig.load_config builds paths as config_dir / config_filename, etc. -->
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Fix test_config.py to use directory-based MainConfig</name>
  <files>tests/unit/test_config.py</files>
  <action>
Rewrite `test_main_config_loads_yaml_and_content` to match the new `MainConfig` interface:

1. Instead of writing three separate temp files, create a temp directory (via `tempfile.mkdtemp()`) and write:
   - `config.yaml` (the yaml_content)
   - `prompt.txt` (the prompt_content)
   - `examples.yaml` (the examples_content)
   into that directory using the default filenames.

2. Construct MainConfig with just `config_dir=Path(tmp_dir)` and `_env_file=None`. Do NOT pass `prompt_path` or `examples_path` -- those fields no longer exist.

3. Assertions remain the same (config.app_config.model.name, etc.).

4. Cleanup: remove the temp directory in `finally` block (use `shutil.rmtree`).

5. Update `_DOTENV_KEYS` to remove `"PROMPT_PATH"` and `"EXAMPLES_PATH"` since those env vars no longer exist. Keep only `"CONFIG_DIR"`.

6. Update `test_main_config_missing_file`: pass `config_dir=Path("/nonexistent/")` (a directory, not a file path). The FileNotFoundError still triggers because `load_config` tries to read `config_dir / config_filename`.

7. Remove the `_write_temp` helper if no longer used (it won't be after switching to directory-based approach).

Use opening delimiter alignment style per project conventions.
  </action>
  <verify>
    <automated>python -m pytest tests/unit/test_config.py -x -v 2>&1 | tail -20</automated>
  </verify>
  <done>All 4 tests in test_config.py pass: test_model_config_defaults, test_model_config_invalid_temperature, test_main_config_loads_yaml_and_content, test_main_config_missing_file</done>
</task>

<task type="auto">
  <name>Task 2: Verify full unit test suite passes</name>
  <files></files>
  <action>
Run the full unit test suite to confirm no regressions. If any test fails, diagnose and fix.
  </action>
  <verify>
    <automated>python -m pytest tests/unit/ -x --tb=short 2>&1 | tail -10</automated>
  </verify>
  <done>All 82 unit tests pass with 0 failures</done>
</task>

</tasks>

<verification>
- `python -m pytest tests/unit/ -x` exits 0 with all tests passing
- `test_main_config_loads_yaml_and_content` no longer uses `prompt_path` or `examples_path` kwargs
- `.env.example` has `CONFIG_DIR=config/` without `PROMPT_PATH` or `EXAMPLES_PATH`
</verification>

<success_criteria>
- Unit test suite is fully green (82/82 pass)
- test_config.py exercises the current MainConfig directory-based API
- .env.example matches current config field structure
</success_criteria>

<output>
After completion, create `.planning/quick/260317-kdo-fix-e2e-tests/260317-kdo-SUMMARY.md`
</output>
