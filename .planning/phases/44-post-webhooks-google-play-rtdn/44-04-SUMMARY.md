---
phase: 44-post-webhooks-google-play-rtdn
plan: 04
subsystem: infra
tags: [google-play, config, pydantic-settings, yaml, environment, subscriptions]

requires:
  - phase: 44-post-webhooks-google-play-rtdn
    provides: "plan 44-01's GooglePlayConfig and AppConfig.google_play, and plan 44-02's three documented GOOGLE_PLAY_ deployer values"
provides:
  - "google_play.products in config/config.yaml — the operator-edited Play product-to-tier map"
  - "TestTheThreeGooglePlayVariablesLandOnTheConfig — the three deployer variables proved to reach the model by loading the real config"
  - "The google / google_play field-name ambiguity closed by a named case"
affects: [44-05, 44-06, 44-07, 45-restore-subscription]

actuals:
  tokens: 921
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A deployment value is proved to land by loading the real config, never by reading the settings declaration"
    - "Each provider's catalogue is a tracked map beside the others, and only the catalogue is tracked"

key-files:
  created: []
  modified:
    - config/config.yaml
    - tests/unit/test_config.py

key-decisions:
  - "The tracked Play product id is nativespeaker.subscription.monthly, the id the e2e seam already uses, not a second spelling invented here"
  - "Only products is declared in the YAML: init_settings outranks env_settings, so a deployer value written here could never be overridden"
  - "The two long test docstrings were rewritten as comments, because the project's own docstring bar is three lines and it is a ratchet at zero"

patterns-established:
  - "The falsification case for a nested settings block asserts exact values, so a variable that fails to split fails here in a second rather than as a 503 in every environment"

requirements-completed: []

coverage:
  - id: D1
    description: "The Google catalogue is an operator-editable map in the tracked config file, holding real access tier ids, beside the App Store map it mirrors"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "test \"$(grep -c '^google_play:' config/config.yaml)\" = \"1\""
        status: pass
      - kind: other
        ref: "test \"$(grep -c '^app_store:' config/config.yaml)\" = \"1\" — the inherited Apple block is unchanged"
        status: pass
      - kind: other
        ref: "PyYAML load of config/config.yaml: google_play.products is non-empty and its values are a subset of {anonymous, registered, paid} (1 entry)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_config.py#TestTheThreeGooglePlayVariablesLandOnTheConfig::test_the_tracked_product_map_merges_with_the_environment_nesting"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each of the three GOOGLE_PLAY_ deployer variables reaches its GooglePlayConfig field, proved by loading the real config rather than by reading env_nested_max_split=1 from the source (assumption A5)"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py#TestTheThreeGooglePlayVariablesLandOnTheConfig::test_every_google_play_variable_lands_on_the_nested_model"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'GOOGLE_PLAY_' tests/unit/test_config.py)\" -ge 3 — 7 occurrences, all three names exercised"
        status: pass
    human_judgment: false
  - id: D3
    description: "AppConfig declares no sibling field name that would make a GOOGLE_PLAY_ variable ambiguous, the direct analogue of the appstore / app_store case"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py#TestTheThreeGooglePlayVariablesLandOnTheConfig::test_the_model_declares_no_sibling_field_that_would_make_a_variable_ambiguous"
        status: pass
    human_judgment: false
  - id: D4
    description: "The application still boots against the edited tracked file and the whole inherited suite stays green"
    verification:
      - kind: other
        ref: "EnvironmentConfig(_env_file=None).app_config loaded against the real config/config.yaml — both product maps returned"
        status: pass
      - kind: unit
        ref: "uv run pytest -q — 1181 passed; uv run pytest -m e2e -q — 277 passed; uv run pytest -m schema -q — 189 passed; uv run ruff check src tests clean"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-09-05
status: complete
---

# Phase 44 Plan 04: The Google catalogue and the three variables, falsified Summary

**`config/config.yaml` now carries the `google_play.products` map beside Apple's, and the three `GOOGLE_PLAY_` deployer variables are proved to reach `GooglePlayConfig` by loading the real config — the split that `env_nested_max_split=1` performs on a two-word section name is executed, not read.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-05T11:29:50Z
- **Completed:** 2026-09-05T11:36:30Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `config/config.yaml` gained a `google_play:` block whose only key is `products:`, mapping `nativespeaker.subscription.monthly` onto the `paid` tier. Its one-line comment carries Google's own retry rather than Apple's: an unmapped verified product id is a 500 and **Pub/Sub redelivers**.
- Only `products` is declared there. The package name, the push audience and the push service account are deployer values, and this file is tracked in git, so a value written here could not be overridden by any environment variable — `init_settings` outranks `env_settings`, exactly as the comment block above it already states.
- `TestTheThreeGooglePlayVariablesLandOnTheConfig` executes assumption A5. All three variables land on their `GooglePlayConfig` fields with the exact values set. This is the case whose failure would otherwise have surfaced as "the route answers 503 in every environment and nothing is logged".
- The tracked map is proved to coexist with the environment nesting while all three variables are simultaneously present, which is what D-16 and D-18 ask for and what the App Store class already proves for its own block.
- The `google` / `google_play` ambiguity is closed by a named case: `google_play` is in `AppConfig.model_fields` and `google` is not.

## Task Commits

1. **Task 1: the tracked Google product map** - `7306094` (feat)
2. **Task 2: the three variables actually land, falsified rather than assumed** - `b895c24` (test)

**Plan metadata:** the `docs(44-04)` commit that carries this file.

## Files Created/Modified

- `config/config.yaml` - the `google_play: products:` block and its one-line operator comment
- `tests/unit/test_config.py` - `_GOOGLE_PLAY_ENV` and the three-case class beside the App Store one

## Decisions Made

- **The tracked Play product id is `nativespeaker.subscription.monthly`.** `tests/e2e/conftest.py` already ships that exact id as `GOOGLE_PRODUCT_ID`, and it is the id the end-to-end proof drives through `PlayDeveloperSubscriptions`. Inventing a second spelling for the tracked file would have made the map and the only executed Google purchase path disagree about the catalogue. Note that it is not Apple's id: Apple's is `com.nativespeaker.subscription.monthly`, and the two stores' ids are independent strings.
- **Only `products` is tracked.** The plan's reasoning holds on inspection of the file: the comment block above `app_store:` already states that `AppConfig` is built as `AppConfig(**yaml_data, ...)` and that pydantic-settings ranks `init_settings` above `env_settings`. A `package_name` written here would be unoverridable by `GOOGLE_PLAY_PACKAGE_NAME`, which is the opposite of what a deployer value needs.
- **Assumption A5 is now falsifiable and holds.** The concern was real rather than theoretical: `env_nested_max_split=1` splits at one delimiter, and `GOOGLE_PLAY_PACKAGE_NAME` has four words. pydantic-settings matches the longest known field name first, so all three land on `google_play`. That is a library behaviour this repository now measures instead of assuming.
- **The two test docstrings became comments.** See the deviation below — this project runs a docstring-length ratchet whose baseline is zero, so the explanatory prose had to move above the `def` rather than inside it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The two new test docstrings broke the project's docstring-length ratchet**

- **Found during:** Task 2
- **Issue:** `tests/unit/test_docstring_bar.py::TestTheBarHolds::test_each_root_matches_its_recorded_baseline[tests/unit]` asserts **equality**, not `<=`, against a recorded baseline of `0` over-long docstrings. Two of the three cases I wrote carried five- and six-line docstrings, so `_measure("tests/unit")` returned `2` and the full-suite run failed with `assert 2 == 0`. The bar is three lines; neither the plan nor `AGENTS.md`'s excerpt names the enforcing test, so it surfaced only at `uv run pytest -q`.
- **Fix:** Both docstrings were cut to one line and the explanatory prose moved to `#` comments directly above the `def`. No assertion changed, and nothing was deleted — the reasoning that makes each case legible is still in the file, just above the signature instead of below it.
- **Files modified:** tests/unit/test_config.py
- **Verification:** `uv run pytest tests/unit/test_config.py tests/unit/test_docstring_bar.py -q` — 43 passed; `uv run pytest -q` — 1181 passed
- **Committed in:** `b895c24` (the fix landed before the task's single commit, so there is no broken commit in history)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** None. Both tasks' `<action>` blocks were followed literally and all six `<verify>` commands across the two tasks were run and passed. No file outside the plan's `files_modified` was touched.

## Issues Encountered

None.

## User Setup Required

None new in this plan. The three `GOOGLE_PLAY_` variables were documented by plan **44-02** in `.env.example` and `44-USER-SETUP.md`, not here — `44-01-SUMMARY.md` § User Setup Required carries a stale forward reference saying 44-04 documents them, which 44-02's summary already corrects and which is left in place rather than rewritten.

An operator who deploys against a real Play account must also confirm that the product id in `google_play.products` matches the subscription id created in Play Console. A mismatch raises `UnmappedStoreProduct`, which answers 500, and Pub/Sub then redelivers the notification until the map names the product. Nothing is written meanwhile, so no subscriber is over-entitled by the mismatch.

## Known Stubs

None. This plan added no code path, and the tracked map holds one real entry rather than a placeholder.

## Threat Flags

None. Every surface this plan touches is in the plan's own threat register:

- **T-44-18 (mitigate)** — the product-to-tier map is server-side and tracked, and a `productId` absent from it raises `UnmappedStoreProduct` before any write rather than defaulting to a tier. `google_play.products` values are asserted to be a subset of the three real tier ids in both a shell check and a test case.
- **T-44-19 (mitigate)** — `push_audience` is now proved to reach the model by an executed case, so a silently empty audience cannot leave the Pub/Sub token's audience pin unenforced. This was the register entry the plan existed to close: an audience that never lands looks identical, from outside, to a deployment that works.
- **T-44-20 (accept)** — the tracked file gained one product id and one tier name. No secret was added.
- **T-44-SC (accept)** — no package was installed.

## Next Phase Readiness

- The Google seam is fully configured: plan 44-01 built it, 44-02 routed and documented it, 44-03 completed its state map, and this plan supplies its catalogue. Plans 44-05, 44-06 and 44-07 land on a seam with no configuration gap.
- **`PLAYHOOK-01` is not marked complete.** `requirements.ready-ids` reported 0 of 1 ready: the ID is declared by sibling plans in this phase that have no summary yet, and it stays open until the last declaring plan produces one.
- Plan 45 reads the same `google_play.products` map through `PlaySubscriptionSource`, so a restore route inherits this catalogue rather than declaring a second one.
- No real Play product id has ever been verified against a real Play Console entry, and none can be until a Play deployment exists. That is the standing fact this map shares with the Apple map above it.

---
*Phase: 44-post-webhooks-google-play-rtdn*
*Completed: 2026-09-05*

## Self-Check: PASSED

- Both modified files exist on disk with the changes described: `config/config.yaml` carries the `google_play:` block, `tests/unit/test_config.py` carries `_GOOGLE_PLAY_ENV` and the three-case class.
- Both task commits exist in `git log`: `7306094`, `b895c24`.
- Every `coverage[].ref` naming a test names a case that exists in the file it names.
- Both tasks' acceptance criteria were re-run at close: 4 of 4 for Task 1, 4 of 4 for Task 2.
- Plan verification re-run at close: `uv run pytest -q` 1181 passed, `uv run pytest -m e2e -q` 277 passed, `uv run pytest -m schema -q` 189 passed, `uv run ruff check src tests` clean, and the tracked file loads through `EnvironmentConfig` returning both product maps.
- `git status --short` is clean and `git diff --diff-filter=D HEAD~2 HEAD` names no deletion.
