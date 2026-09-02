---
phase: 40-post-auth-upgrade-anonymous
plan: 02
subsystem: auth
tags: [errors, structured-logging, pydantic, fastapi, anti-oracle]

# Dependency graph
requires:
  - phase: 37.3-machine-generated-refactor-2
    provides: "the raised-exception error tree, `ChallengeRejected`'s base-plus-silent-leaves shape, and `camel_to_snake` as the log-event derivation"
  - phase: 37-post-auth-create-user
    provides: "`NotLinked` declaring 403 `operation_not_allowed`, and `CreateUserRequest` as the completion body"
  - phase: 37.5-machine-generated-refactor-4
    provides: "`tests/unit/error_tree.py`'s totality walk and the layering rule in AGENTS.md"
provides:
  - "`UpgradeRefused`, a 403 `operation_not_allowed` base declared once"
  - "`ProviderTransitionNotAllowed` and `ProviderAccountAlreadyLinked`, two silent leaves distinguished only by their log-event names"
  - "`CompletionRequest`, the one completion body model for every challenge-bearing route"
  - "the vocabulary ratchets naming all three new classes"
affects: [40-04-upgrade-service, 40-05, 40-06, 41-claim-anonymous-grant, 42-claim-registered-grant]

# Actuals (#2632) — same estimateTokens scale (chars/4) as the plan's estimate.
actuals:
  tokens: 11466
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "base-plus-silent-leaves: the status and code declared once on a shared base, so an anti-oracle property is structural rather than asserted"
    - "constructor-carried scalars stringified in `log_fields()`, with exclusion of a sensitive identifier enforced by a signature assertion"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/errors.py
    - src/nativespeaker/api/schemas/auth.py
    - src/nativespeaker/api/routers/auth.py
    - tests/unit/test_rejection_vocabulary.py
    - tests/unit/test_create_user_body.py

key-decisions:
  - "The `UpgradeRefused` base is `AppError`-derived rather than `ProviderLookupError`-derived: it carries a different field set (row id + two providers, not stage + cause), and inheriting would have dragged `stage`/`cause` into a log line D-06 closes at exactly three keys"
  - "`super().__init__` receives only the lowercased class name — no provider values in the exception message — so `str(exc)` cannot become a second, unwatched disclosure channel alongside `log_fields()`"
  - "`requirements-completed` is empty: this plan delivers vocabulary and a request model with no caller, and completes neither UPGRADE-01 nor UPGRADE-02. Plan 40-04 does. Same treatment as 36-01/REBIND-05 and 37-01/CREATE-02"

patterns-established:
  - "A refusal that must not disclose an identifier states that as a constructor signature, asserted by `inspect.signature`, rather than as a convention callers are trusted to follow"
  - "A new error base is registered in three places in one commit: the class, `EVENT_NAMES`, and `CONSTRUCTOR_ARGUMENTS` — the ratchets reject any two of the three"

requirements-completed: []

coverage:
  - id: D1
    description: "Two upgrade refusals under one shared 403 `operation_not_allowed` base, producing two distinct structured-log event names and one identical client body"
    requirement: "UPGRADE-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_rejection_vocabulary.py#TestTheTwoUpgradeArmsAnswerOneThingAndLogThree"
        status: pass
      - kind: unit
        ref: "tests/unit/test_rejection_vocabulary.py#TestTheEventVocabularyIsWrittenDown::test_the_tree_spells_exactly_the_recorded_event_names"
        status: pass
      - kind: unit
        ref: "tests/unit/test_error_registry.py#TestTreeTotality"
        status: pass
    human_judgment: false
  - id: D2
    description: "One `CompletionRequest` model serving `/auth/create-user` and, from plan 40-04, `/auth/upgrade-anonymous`; `CreateUserRequest` retired with no alias and no re-export"
    requirement: "UPGRADE-02"
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_body.py#TestTheModelArmsDirectly"
        status: pass
      - kind: other
        ref: "grep -rn \"CreateUserRequest\" src tests  # returns nothing"
        status: pass
    human_judgment: false

# Metrics
duration: 16min
completed: 2026-09-02
status: complete
---

# Phase 40 Plan 02: Upgrade Refusal Vocabulary and the Shared Completion Body Summary

**Two new upgrade refusals sharing one 403 `operation_not_allowed` base — distinct only as `provider_transition_not_allowed` and `provider_account_already_linked` in the structured log — plus `CreateUserRequest` collapsed into a single `CompletionRequest` model.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-09-02T10:27:00Z
- **Completed:** 2026-09-02T10:43:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `UpgradeRefused(AppError)` declares `status = 403` and `code = "operation_not_allowed"` exactly once. `ProviderTransitionNotAllowed` and `ProviderAccountAlreadyLinked` declare nothing at all — no status, no code, no `log_level` — so the anti-oracle property (T-40-02-02) holds structurally: making one refusal answer differently would take an override a reviewer sees, not an omission a reviewer misses.
- `log_fields()` returns exactly three stringified scalars — `identity_row_id`, `stored_provider`, `live_provider`. The provider account uid is excluded at the constructor: `UpgradeRefused.__init__` is keyword-only and its parameter set is asserted by `inspect.signature`, so a later caller cannot pass one even by accident (T-40-02-01).
- `ErrorCode` and `ErrorResponse` are untouched. `operation_not_allowed` already existed at 403 on `NotLinked`; the two new classes join it rather than introducing a client-visible code, and the response body stays exactly one field.
- The vocabulary ratchets moved with the classes: three new `EVENT_NAMES` entries (base included, on the same terms as `provider_lookup_error` and `challenge_rejected`), three `CONSTRUCTOR_ARGUMENTS` rows, and a seven-case group test mirroring `TestTheTwoAccountArmsDeclareNothingEither`.
- `CreateUserRequest` is now `CompletionRequest`, with its class body, docstring and both comments byte-identical. The `min_length=1` constraint — the reason an unusable handle is the framework's 422 rather than a not-found 409 — survives the rename, verified on `model_fields` directly.

## Task Commits

Each task was committed atomically:

1. **Task 1: The two upgrade refusals under one shared 403 base** (TDD)
   - `0e27638` (test) — the failing vocabulary ratchets and the group test
   - `32727c3` (feat) — `UpgradeRefused` and its two silent leaves
   - No refactor commit: the implementation landed in the shape the existing `ChallengeRejected`/`AccountUnavailable` neighbours already use, with nothing to clean up.
2. **Task 2: One completion request model for both routes** — `e76965a` (refactor)

## Files Created/Modified

- `src/nativespeaker/api/errors.py` — the new `# --- Upgrade arms ---` section between the lookup and challenge arms: one base, two leaves, and an `IdentityProvider` import
- `src/nativespeaker/api/schemas/auth.py` — `CreateUserRequest` renamed to `CompletionRequest`, one line changed
- `src/nativespeaker/api/routers/auth.py` — the schema import (re-sorted) and the create-user body annotation
- `tests/unit/test_rejection_vocabulary.py` — `UPGRADE_ARMS`, `UPGRADE_SAMPLE`, three `EVENT_NAMES` entries, three `CONSTRUCTOR_ARGUMENTS` rows, and `TestTheTwoUpgradeArmsAnswerOneThingAndLogThree`
- `tests/unit/test_create_user_body.py` — three references renamed; no assertion moved

## Decisions Made

- **`UpgradeRefused` derives from `AppError`, not from `ProviderLookupError`.** The plan named `ProviderLookupError`'s *body shape* as the model to copy (assign the scalars, then `super().__init__`), which is what was copied — but the base itself is `AppError`. Inheriting `ProviderLookupError` would have inherited its `stage`/`cause` `log_fields()`, and D-06 closes this log line at exactly three keys.
- **The exception message carries no provider values.** `super().__init__(type(self).__name__.lower())` — the plan's "a short message built from the class name," read literally. `str(exc)` is not routed to the log by `app_error_handler`, but a message interpolating the two providers would be a second field channel outside `log_fields()`, which is the one channel `AppError` documents.
- **`requirements-completed` is empty.** UPGRADE-01 and UPGRADE-02 are in this plan's `requirements` frontmatter, but this plan ships vocabulary and a request model that nothing calls yet. Marking them complete would close requirements whose behaviour does not exist. The repository has settled this the same way twice before (36-01 for REBIND-05, 37-01 for CREATE-02): the plan that delivers the behaviour claims the requirement. That is plan 40-04.

## Deviations from Plan

None — plan executed exactly as written. The three decisions above are choices the plan left to the executor, not departures from it.

The one place the plan's letter and its intent could have diverged — "copy `ProviderLookupError`'s body shape" read as "subclass `ProviderLookupError`" — is recorded under Decisions rather than as a deviation, because the plan's own `<behavior>` Test 4 (exactly three keys) forecloses the subclassing reading.

## Issues Encountered

None. RESEARCH § Common Pitfalls 3 predicted the shape of the failure precisely: the three ratchet sites are `EVENT_NAMES`, `CONSTRUCTOR_ARGUMENTS` and the group test, and registering all three in the same commit as the classes meant the ratchets never went red for a reason other than the deliberate RED step.

Pitfalls 1 and 2 (`"for update"` as a forbidden literal, and `FOR UPDATE` on the nullable side of an outer join) did not arise: this plan edits neither `services/auth.py` nor `crud/identities.py` and issues no query.

## Verification

| Gate | Result |
|---|---|
| `uv run pytest -q` | 819 passed, 323 deselected |
| `uv run ruff check src tests` | All checks passed |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed — the bar holds at 0 on every root |
| Both leaves answer `(403, "operation_not_allowed")` | confirmed |
| Neither leaf declares `status`/`code`; the base declares no `log_level` | `False False False` |
| `UpgradeRefused.__init__` parameters | `['identity_row_id', 'live_provider', 'stored_provider']` |
| `grep -c "provider_uid" src/nativespeaker/api/errors.py` | `0` |
| `git diff` on `errors.py` touching `ErrorCode`/`ErrorResponse` | no such lines |
| `grep -rn "CreateUserRequest" src tests` | nothing |
| `CompletionRequest.model_fields['challenge_id'].metadata` | `[MinLen(min_length=1)]` |
| Task 2 `git diff --stat` | exactly the three named files, 6 insertions / 6 deletions |

## Known Stubs

None. Both classes are complete and raisable; they simply have no caller until plan 40-04.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or schema change. The two threats this plan owns are mitigated as the register specified: T-40-02-01 by the constructor signature assertion, T-40-02-02 by the single declaration on the shared base. T-40-02-03 holds via the re-baselined `EVENT_NAMES` exact-set assertion plus `assert_tree_total`. T-40-02-SC is unreachable — nothing was installed and `pyproject.toml` is unchanged.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Plan 40-04's service can raise `ProviderTransitionNotAllowed` and `ProviderAccountAlreadyLinked` by name and take `CompletionRequest` as its body. Two notes for whoever writes it:

- **The three refusals are one client answer.** Case 1 stays `NotLinked(stage=..., cause="empty")` at 403 `operation_not_allowed`; the two new classes answer identically. A test asserting the upgrade route's refusal body must not distinguish them, or it re-creates the enumeration oracle D-02 removed.
- **`ProviderAccountAlreadyLinked` is raised from D-08's `IntegrityError` catch**, which per AGENTS.md belongs in `crud/identities.py` with the query. That module is subject to RESEARCH § Common Pitfalls 1 — express D-15's lock as `.with_for_update()`, never as raw SQL text.

Phases 41 and 42 inherit `CompletionRequest` unchanged; neither should add a second model of the same shape.

---
*Phase: 40-post-auth-upgrade-anonymous*
*Completed: 2026-09-02*

## Self-Check: PASSED

- `.planning/phases/40-post-auth-upgrade-anonymous/40-02-SUMMARY.md` — FOUND
- `0e27638`, `32727c3`, `e76965a` — all FOUND in `git log`
- Working tree clean; no untracked files left behind
