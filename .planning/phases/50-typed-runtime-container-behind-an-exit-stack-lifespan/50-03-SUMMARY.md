---
phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
plan: 03
subsystem: app
tags: [runtime, lifespan, dependencies, dataclass, pytest]

requires:
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "`GooglePlayNotifications` as the one Play class (50-01), so the container has one Play field"
  - phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan
    provides: "builders whose `None` means an absent setting only (50-02)"
provides:
  - "`Runtime`, the frozen slotted container with the eight D-02 fields"
  - "`app.state.runtime`, the one write plans 50-04 to 50-06 converge on"
  - "`get_runtime(request: Request) -> Runtime`, the dependency every later plan declares"
  - "`make_runtime(**overrides)` in `tests/unit/conftest.py`"
affects: [50-04, 50-05, 50-06, 50-07]

actuals:
  tokens: 12200
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "The lifespan binds each built object to a local, assigns the local to `app.state`, and builds the container from the same locals, so the two readings stay one object"
    - "A test factory returns the real production type and fills the fields the case does not name (`fields | overrides`, as `_play_config` does)"

key-files:
  created:
    - src/nativespeaker/api/app/runtime.py
  modified:
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/app/dependencies.py
    - tests/unit/conftest.py
    - tests/unit/test_app_wiring.py

key-decisions:
  - "`make_runtime` sits below `FakeFirebaseAdapter`, not beside `make_test_verifier`, so it forward-references nothing"
  - "The stand-in fields use `MagicMock()`; the two cheap store classes are real, as the plan asks"
  - "The `Runtime` docstring states the no-default rule, because a reader cannot see it in the field list"

requirements-completed: []

coverage:
  - id: D1
    description: "`Runtime` is a frozen, slotted dataclass with the eight D-02 fields in build order, in its own module under `app/`"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheRuntimeContainerIsFrozenAndSlotted::test_the_container_is_a_frozen_slotted_dataclass"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheRuntimeContainerIsFrozenAndSlotted::test_the_eight_fields_are_declared_in_build_order"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheRuntimeContainerIsFrozenAndSlotted::test_the_container_lives_in_its_own_module_under_app"
        status: pass
    human_judgment: false
  - id: D2
    description: "A built container refuses a rebind and carries no instance dict (threat T-50-03-02)"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheRuntimeContainerIsFrozenAndSlotted::test_a_field_cannot_be_reassigned"
        status: pass
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheRuntimeContainerIsFrozenAndSlotted::test_a_built_container_carries_no_instance_dict"
        status: pass
    human_judgment: false
  - id: D3
    description: "The lifespan builds the container from its own locals and assigns `app.state.runtime` before `yield`; `POST /chats` is then served off `runtime.config` and `runtime.llm_service`"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_chats.py#TestCreateChat::test_create_chat_english"
        status: pass
      - kind: e2e
        ref: ".venv/bin/pytest -q -p no:cacheprovider -m e2e"
        status: pass
    human_judgment: false
  - id: D4
    description: "`get_config` is gone from `src` and `get_runtime` is the added `app.state` read"
    verification:
      - kind: other
        ref: "test -z \"$(grep -rn 'get_config' src --include='*.py')\""
        status: pass
      - kind: other
        ref: "grep -c 'request.app.state' src/nativespeaker/api/app/dependencies.py — 14, one fewer than 15"
        status: pass
    human_judgment: false
  - id: D5
    description: "`make_runtime()` builds a whole `Runtime` from the unit fakes, with no mirror class"
    verification:
      - kind: unit
        ref: "tests/unit/test_app_wiring.py#TestTheRuntimeContainerIsFrozenAndSlotted::test_a_built_container_carries_no_instance_dict"
        status: pass
      - kind: other
        ref: "grep -c 'class .*Runtime' tests/unit/conftest.py — 0"
        status: pass
    human_judgment: false

duration: 10 min
completed: 2026-09-18
status: complete
---

# Phase 50 Plan 03: Runtime, get_runtime and one consumer end to end Summary

**`Runtime` is a frozen, slotted dataclass of the eight objects boot builds; the lifespan assigns it to `app.state.runtime`, `get_runtime` returns it, and `POST /chats` is now served entirely off `runtime.config` and `runtime.llm_service`.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-09-18T08:17:29Z
- **Completed:** 2026-09-18T08:27:35Z
- **Tasks:** 3
- **Files created or modified:** 5

## Accomplishments

- `src/nativespeaker/api/app/runtime.py` holds one `@dataclass(frozen=True, slots=True)` class with the eight D-02 fields in build order. No field has a default.
- `session_factory` is annotated `async_sessionmaker[SQLModelAsyncSession]` on the field and on the local the lifespan fills it from (D-04).
- The lifespan binds every built object to a local, assigns each local to its old `app.state` attribute, and builds one `Runtime` from those same locals right before `yield`. The two readings are one object.
- Every other `app.state` attribute stays in place. Plans 50-04 to 50-06 remove them one group at a time, and the tests still read them.
- `get_runtime` is defined at the top of `dependencies.py`, above every dependency that declares it.
- `get_config` is deleted, with the `AppConfig` import it was the last user of.
- `get_chat_service` declares `runtime: Runtime = Depends(get_runtime)` and takes no `Request`. It reads `runtime.llm_service` and three `runtime.config` values.
- `make_runtime(**overrides)` in `tests/unit/conftest.py` returns the real `Runtime` and fills every field a case does not name.
- Five cases in `tests/unit/test_app_wiring.py` pin criterion 4: frozen, slotted, the eight names as a literal tuple, no instance dict, `FrozenInstanceError` on a rebind, and the module location.

## Task Commits

1. **Task 1 (tracer): `Runtime`, `get_runtime`, and one consumer end to end** — `dc642cc`
2. **Task 2: `make_runtime` for unit tests** — `94f586e`
3. **Task 3: the criterion 4 case** — `a2240a9`

## Files Created/Modified

- `src/nativespeaker/api/app/runtime.py` (new) — the `Runtime` class, a two-line docstring, eight typed fields.
- `src/nativespeaker/api/app/lifespan.py` — seven new locals, the annotated session-factory local, and one `Runtime(...)` call assigned to `app.state.runtime` before `yield`.
- `src/nativespeaker/api/app/dependencies.py` — `get_runtime` added at the top, `get_config` and the `AppConfig` import deleted, `get_chat_service` rewritten.
- `tests/unit/conftest.py` — `make_runtime`, plus the three imports it needs.
- `tests/unit/test_app_wiring.py` — `TestTheRuntimeContainerIsFrozenAndSlotted`, five cases.

## Decisions Made

- `make_runtime` is defined below `FakeFirebaseAdapter` rather than beside `make_test_verifier`. Both fakes it builds from are then already on the page. Python would resolve the name either way, but a reader of the factory would have had to search 90 lines down for the class it calls.
- The four fields with no cheap real value — `config`, `session_factory`, `devicecheck_adapter`, `llm_service` — and the Play httpx client default to `MagicMock()`. A case that reads one of them overrides it. `MagicMock` answers any attribute, so a later case that reads `runtime.config.google_play.package_name` must pass a real config rather than trust the default.
- One `# ty: ignore[invalid-argument-type]` on the `Runtime(**(fields | overrides))` line covers the whole call. The same comment on the `client=MagicMock()` argument was unused, and `ty` reported it as unused, so it was removed.
- The `Runtime` docstring carries the no-default rule in its second line. The rule is the reason the class has no `X | None` field, and nothing in the field list states it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] `make_runtime` placement moved**

- **Found during:** Task 2
- **Issue:** The plan asks for the factory "beside `make_test_verifier`" (line 106). It builds a `FakeFirebaseAdapter`, which is defined at line 196. The call would have resolved at run time, but the definition would read as a forward reference.
- **Fix:** Defined `make_runtime` after the `fake_firebase_adapter` fixture, so both fakes it uses are above it. Its shape still follows `make_test_verifier` and the `fields | overrides` idiom of `_play_config`.
- **Files modified:** `tests/unit/conftest.py`
- **Verification:** `.venv/bin/pytest -q` exits 0; `grep -c 'def make_runtime' tests/unit/conftest.py` is 1.
- **Commit:** `94f586e`

---

**Total deviations:** 1 auto-fixed (1 placement blocker). **Impact on plan:** none on behavior or on any acceptance criterion. Every later plan imports the factory by name, not by line.

## Issues Encountered

None. The unit suite grew from 1889 to 1894 cases, which is the five added here.

## Threat Notes

- T-50-03-01 (the container in a log record): no log call takes `Runtime` or `runtime.config`. `logger.info("started", ...)` still names `config.model.name`, `config.resilience.pool_size` and the example languages, and nothing else was added to it.
- T-50-03-02 (request-scoped mutation): `frozen=True, slots=True` holds, pinned by two cases.
- T-50-03-03 (the interim dual state): accepted, as planned. Both `app.state.jwt_verifier` and `app.state.runtime.jwt_verifier` exist for this plan. Only `get_chat_service` reads the container, and it reads no swapped field, so no e2e fixture is silently neutralised. The seven e2e fixtures still swap the old attributes and still pass.

## Verification Results

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -p no:cacheprovider` | 1894 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m e2e` | 361 passed, exit 0 |
| `.venv/bin/pytest -q -p no:cacheprovider -m schema` | 297 passed, exit 0 |
| `.venv/bin/ruff check src tests` | All checks passed! |
| `.venv/bin/ty check src` | All checks passed! |
| `test -z "$(grep -rn 'get_config' src --include='*.py')"` | empty, exit 0 |
| `grep -c '^class Runtime' src/.../app/runtime.py` | 1 |
| `grep -c 'frozen=True, slots=True' src/.../app/runtime.py` | 1 |
| `grep -c 'request.app.state' src/.../app/dependencies.py` | 14 (was 15) |
| `def get_runtime` line 40 vs `def get_chat_service` line 100 | get_runtime is higher in the file |
| `request: Request` in `get_chat_service` | 0 |
| `grep -c 'def make_runtime' tests/unit/conftest.py` | 1 |
| `grep -c 'class .*Runtime' tests/unit/conftest.py` | 0 |
| `grep -c 'FrozenInstanceError' tests/unit/test_app_wiring.py` | 2 |
| Field reordering fails the case | `config` and `session_factory` swapped: `test_the_eight_fields_are_declared_in_build_order` FAILED; edit reverted, `git diff` on the file is empty |

The schema suite is not a plan verify command. It was run as a regression check.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Criterion 4 is met and measured. The first clause of criterion 5 is met: `get_config` is gone.
- The rest of criterion 5 is open by design. `dependencies.py` still holds 14 `request.app.state` reads, and `get_session_factory`, `get_firebase_adapter` and `get_devicecheck_adapter` still exist. Plans 50-04 to 50-06 remove them one group at a time.
- Criterion 6 is untouched: nine test files still set lifespan-built attributes on `app.state`. `make_runtime` is the tool those plans use.
- Criteria 1, 2 and 3 (the `AsyncExitStack` and the builders) are untouched by this plan.
- Every later plan can now delete an `app.state` write and its matching dependency in one commit, because the container already holds the object.

## Self-Check: PASSED

- `src/nativespeaker/api/app/runtime.py` — FOUND
- `src/nativespeaker/api/app/lifespan.py` — FOUND
- `src/nativespeaker/api/app/dependencies.py` — FOUND
- `tests/unit/conftest.py` — FOUND
- `tests/unit/test_app_wiring.py` — FOUND
- commit `dc642cc` — FOUND
- commit `94f586e` — FOUND
- commit `a2240a9` — FOUND
- Every `<acceptance_criteria>` of all three tasks re-run after the last commit — PASS
- The plan `<verification>` block re-run after the last commit — PASS

---
*Phase: 50-typed-runtime-container-behind-an-exit-stack-lifespan*
*Completed: 2026-09-18*
