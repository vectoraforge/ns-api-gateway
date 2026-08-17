# Deferred Items - Phase 22

## Pre-existing Test Failure

- **File:** `tests/unit/test_config.py::test_main_config_loads_yaml_and_content`
- **Issue:** Test YAML fixture does not include required `apple.bundle_id` and `apple.product_id_to_tier` fields added in Plan 01. Fails with pydantic ValidationError for missing fields.
- **Discovered during:** Plan 03 regression test run
- **Impact:** Low -- only affects config test, not application functionality
- **Fix:** Update test YAML fixture to include apple config section
