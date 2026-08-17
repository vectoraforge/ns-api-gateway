# Deferred Items - Phase 30

## Pre-existing Collection Errors (out of scope for 30-01)

1. **test_config.py** - `ImportError: cannot import name 'MainConfig' from 'nativespeaker.api.config'`
   - Caused by parallel worktree changes to config.py (MainConfig likely renamed)
   - Not caused by plan 30-01 changes

2. **test_error_contract.py** - `ModuleNotFoundError: No module named 'nativespeaker.api.app.main'`
   - Caused by parallel worktree rename of main.py -> app.py
   - Not caused by plan 30-01 changes
