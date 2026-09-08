---
phase: "46"
slug: "post-auth-sign-out-all"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-09-08"
---

# Phase 46 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest with `pytest-asyncio`, `asyncio_mode = "auto"` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]` |
| **Quick run command** | `uv run pytest tests/unit/<file> -q` |
| **Full suite command** | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` |
| **Estimated runtime** | one unit file ~2s measured; the three suites together well under 5 minutes |

Measured baseline before this phase: unit **1255** passed, e2e **333** passed, schema **229** passed.
Schema is untouched by this phase and must still read 229.

---

## Sampling Rate

- **After every task commit:** the named file(s) that task touched, for example
  `uv run pytest tests/unit/test_firebase_adapter.py tests/unit/test_firebase_retry.py -q`
- **After every plan wave:** `uv run pytest -q`, plus
  `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` for any wave touching the router
- **Before `/gsd:verify-work`:** all three suites green and `uv run ruff check src tests` clean
- **Max feedback latency:** under 10 seconds for a single unit file
- **One deliberate red window:** the unit suite is red between plan 46-01 and plan 46-02. Plan 46-01
  changes the shape four hand-written literals record, and plan 46-02 re-writes them. `uv run pytest -q`
  is therefore not a gate of plan 46-01, and plan 46-03 depends on 46-02 because its own gate is the
  whole unit suite. Plan 46-04 runs in wave 2 beside 46-02, because its gates are `-m e2e` only and a
  failing unit assertion does not stop e2e collection.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 46-01-01 | 01 | 1 | SIGNOUT-01 | T-46-02 / T-46-03 | The seam passes `app=` explicitly; the INFO line carries `identity_row_id` only | e2e | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | ✅ created by this task | ⬜ pending |
| 46-02-01 | 02 | 2 | SIGNOUT-01 | T-46-11 | The recorded Protocol, ratchet and rejection vocabulary state the shape 46-01 left | unit | `uv run pytest tests/unit/test_adapter_interfaces.py tests/unit/test_auth_package_shape.py tests/unit/test_rejection_vocabulary.py -q` | ✅ | ⬜ pending |
| 46-02-02 | 02 | 2 | SIGNOUT-01, SIGNOUT-02 | T-46-05 | The route is pinned as narrowed and as declaring no database session | unit | `uv run pytest -q` | ✅ | ⬜ pending |
| 46-03-01 | 03 | 3 | SIGNOUT-01 | T-46-02 | No ambient Admin client is reachable; an unconfigured issuer calls nothing | unit | `uv run pytest tests/unit/test_firebase_adapter.py -q` | ✅ | ⬜ pending |
| 46-03-02 | 03 | 3 | SIGNOUT-02 | T-46-01 / T-46-07 | An exhausted budget raises `RevocationUnconfirmed`, never `Unavailable` or `RetryError` | unit | `uv run pytest tests/unit/test_firebase_retry.py -q` | ✅ | ⬜ pending |
| 46-04-01 | 04 | 2 | SIGNOUT-02 | T-46-01 / T-46-04 | Every unconfirmed outcome is a refusal at the wire, and the two 503 bodies are equal | e2e | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | ✅ after 46-01 | ⬜ pending |
| 46-04-02 | 04 | 2 | SIGNOUT-01, SIGNOUT-02 | T-46-05 / T-46-03 | Barrier rejections match `/auth/sync` byte for byte; no record carries the subject | e2e | `uv run pytest -m e2e -q` | ✅ after 46-01 | ⬜ pending |
| 46-05-01 | 05 | 4 | SIGNOUT-01, SIGNOUT-02 | T-46-08 | The departure and the accepted exposure are recorded, and the brief is unedited | CLI | `sha256sum -c --status` over the two spec files | ✅ | ⬜ pending |
| 46-05-02 | 05 | 4 | SIGNOUT-01, SIGNOUT-02 | T-46-09 | The recorded suite counts come from a green run made in the plan | full suite | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. There is one missing test file,
`tests/e2e/test_sign_out_all.py`, and it is created inside the phase's first task rather than by a
separate Wave 0 plan, because that task is the tracer: the file and its one confirmed-204 case are
the tracer's own end-to-end verification.

- [x] `tests/e2e/test_sign_out_all.py` — created by task 46-01-01, the tracer
- [x] The `_LogSpy` / `_spy_on` helpers for that file — copied by task 46-01-01 from
      `tests/e2e/test_app_store_webhook.py:60-101`, because a module-level logger caches its binding
- [x] Framework install: none. pytest, `pytest-asyncio`, `seed_identity`, `make_token` and
      `scripted_firebase_adapter` all exist. `tests/e2e/conftest.py` needs no edit.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A real Firebase project answers `accounts:update` for a deleted account with `USER_NOT_FOUND`, so D-06's 401 arm fires in production | SIGNOUT-02 | Assumption A1. Both suites script the exception directly and pass either way, so the exposure is production-only and no automated case can see it. | With Application Default Credentials present, call `firebase_admin.auth.revoke_refresh_tokens` for a uid deleted from the project and confirm `auth.UserNotFoundError` is raised. Record the result under SIGNOUT-01. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 46s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
