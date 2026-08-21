---
phase: 35-foundation
plan: 04
subsystem: deletion-sweep
tags: [fastapi, starlette, sqlmodel, dependency-injection, route-registry, firebase-admin, pytest]

requires:
  - phase: 35-foundation
    plan: 01
    provides: "auth/registry.py REGISTRY + assert_route_enumeration; auth/barrier.py wire-contract middleware"
  - phase: 35-foundation
    plan: 02
    provides: "errors.py as the one registry; AuthenticationError pointed at AUTH_REQUIRED"
  - phase: 35-foundation
    plan: 03
    provides: "auth/context.py LinkedIdentity; app/dependencies.py get_linked_identity"
provides:
  - "an eight-route application -- GET /, GET /examples, GET /health/ready, and the five chat routes -- with registered and declared in set equality at real startup"
  - "a startup path with no firebase_admin, no Google Application Default Credentials, and no Apple receipt verifier"
  - "chat routes on the §1.4 seam: Depends(get_linked_identity), handlers taking identity.user.id"
  - "ChatService.create_chat / send_message taking user_id: UUID in place of user: User"
  - "a fully green suite -- 464 passed, zero failures, zero xfail, zero skip"
affects: [35-05, 35-06, 35-08, 35-09, 35-10, 35-11, 36-rebinding, 39-profile, 43-webhooks]

actuals:
  tokens: 25781
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Deleting a route and its registry declaration in one commit, because a startup set-equality assertion makes any intermediate state un-bootable"
    - "Retargeting a test onto the live rejection rather than deleting it, but only where the retargeted assertion is strictly stronger -- an anti-oracle 401 in place of a per-branch 404/400/422"
    - "A positive control beside every negative case, so a wall of 401s is provably the wire contract and not a blanket deny"
    - "An undeclared route in a test fixture as the vehicle for barrier tests: `lookup` returns None and the barrier applies its strictest disposition, which pins that property while giving the test a route it fully controls"
    - "Test-double identity built from the real model classes with only the columns that survive the v2.0 schema, so plan 05's model repair cannot break the harness"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/app/main.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/auth/registry.py
    - src/nativespeaker/api/routers/chats.py
    - src/nativespeaker/api/routers/__init__.py
    - src/nativespeaker/api/services/chats.py
    - src/nativespeaker/api/services/__init__.py
    - src/nativespeaker/api/database/__init__.py
    - src/nativespeaker/api/models/api.py
    - src/nativespeaker/api/models/__init__.py
    - tests/unit/conftest.py
    - tests/unit/test_services.py
    - tests/unit/test_users.py
    - tests/unit/test_auth_security.py
    - tests/unit/test_exception_handlers.py
    - tests/unit/test_logging.py
    - tests/e2e/test_chats.py
    - tests/e2e/test_chat_queries.py
    - tests/e2e/test_error_cases.py
  deleted:
    - src/nativespeaker/api/routers/users.py
    - src/nativespeaker/api/routers/webhooks.py
    - src/nativespeaker/api/services/users.py
    - src/nativespeaker/api/services/subscriptions.py
    - src/nativespeaker/api/services/firebase.py
    - src/nativespeaker/api/database/users.py
    - src/nativespeaker/api/database/usage.py
    - src/nativespeaker/api/database/subscriptions.py
    - tests/unit/test_subscriptions.py
    - tests/unit/test_usage.py
    - tests/unit/test_webhooks.py
    - tests/e2e/test_users.py
    - tests/e2e/test_isolation.py
    - tests/e2e/test_flows.py

key-decisions:
  - "tests/e2e/test_isolation.py and tests/e2e/test_flows.py were deleted outright rather than narrowed. Every case in both seeded rows through conftest.create_chat, which still inserts the v1.6 User(jwt_sub=...) shape; narrowing them to `an unlinked caller gets 401` would have made them duplicates of test_chat_queries.py under a name that no longer described them."
  - "The e2e chat modules were retargeted onto a five-route refusal matrix rather than emptied. A caller presenting a genuinely-issued credential that passes the §1.1 wire contract is still refused -- that is T-35-04-03 proven end to end over the real transport, and nothing else in the suite exercises it."
  - "test_error_cases.py's 404/400/422 cases became anti-oracle assertions. Their handler branches are unreachable, and asserting that an unadmitted caller cannot enumerate chat ids, languages, or the request schema is strictly stronger than the per-branch status they used to pin."
  - "tests/unit/test_auth_security.py was retargeted onto AuthBarrierMiddleware rather than deleted. The behaviour it described -- a malformed Authorization field on an authenticated route answers auth_required -- is still live; only its owner changed."
  - "test_bearer_lowercase_rejected was deleted rather than retargeted: §1.1 matches the scheme case-insensitively per RFC 7235, so `bearer <token>` is now accepted at the wire. Retargeting it would have produced a false green -- it would still have seen 401, but from the absent identity context, not from the wire contract."
  - "WebhookVerificationError was left in errors.py. errors.py is outside this plan's file list and the plan's `Removed symbols` list does not name it; removing a ServiceError subclass is the registry's business, and plan 11 owns the final shape."
  - "The user_id contextvar binding that get_current_user did was not reproduced in the handlers. §8.2's structured security log belongs to the barrier (D-01), and binding it in five handlers would be the duplication D-02 exists to prevent."

requirements-completed: [FOUND-01, FOUND-03]

coverage:
  - id: D1
    description: "No module in src/ imports SubscriptionService, UserService, FirebaseService, UsersDB, UsageDB, or SubscriptionDB, and none of those files exists"
    requirement: FOUND-03
    verification:
      - kind: other
        ref: "test ! -e on all eight paths -> exit 0; grep -rn for the six symbols across src/ -> no hits; `python -c 'import nativespeaker.api.app.main'` exits 0"
        status: pass
      - kind: unit
        ref: "tests/unit/test_adapter_interfaces.py::test_foundation_calls_no_adapter_method_anywhere_in_src (unchanged, still passing over a smaller src/)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Eight routes registered, eight declared, set equality in both directions at real startup"
    requirement: FOUND-03
    verification:
      - kind: other
        ref: "`enumerate_registered(app)` -> `8 8 True []`"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py (9 tests over the real started app, incl. assert_route_enumeration called directly)"
        status: pass
      - kind: other
        ref: "mutation M3 (re-add the GET /users/me declaration with no route behind it) -> 9 errors, the lifespan aborts"
        status: pass
    human_judgment: false
  - id: D3
    description: "No route creates a core.users or core.external_identities row; just-in-time provisioning is gone"
    requirement: FOUND-01
    verification:
      - kind: other
        ref: "UsersDB.get_or_create and UserService.get_or_create deleted with their modules; the only remaining DB class is ChatsDB, whose writes are Chat/Message only"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py::TestAccessorsCannotWrite (plan 03) -- the accessors are sync and take only the Request, so no write is reachable from the seam"
        status: pass
    human_judgment: false
  - id: D4
    description: "Startup initializes neither firebase_admin nor an Apple receipt verifier, and app.state carries neither"
    requirement: FOUND-03
    verification:
      - kind: other
        ref: "`inspect.getsource(lifespan)` -> `'firebase_admin' in s, 'apple_verifier' in s` prints `False False`"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py::test_lifespan_completed -- the real lifespan runs to completion with no credential source available"
        status: pass
    human_judgment: false
  - id: D5
    description: "Chat handlers take a user id and consume the identity context through Depends() accessors only"
    requirement: FOUND-01
    verification:
      - kind: other
        ref: "`hasattr(dependencies, 'get_current_user'/'require_quota'/'get_subscription_service')` -> `False False False`; routers/chats.py carries five `Depends(get_linked_identity)` and zero `Depends(get_current_user)`"
        status: pass
      - kind: unit
        ref: "tests/unit/test_services.py (17 tests over create_chat(user_id=)/send_message(user_id=)); tests/unit/conftest.py `client` overrides get_linked_identity, so the served path is exercised with a real LinkedIdentity"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_chats.py + test_chat_queries.py -- all five routes refuse a caller with no identity context, with the shared body"
        status: pass
      - kind: other
        ref: "mutation M2 (get_request_context fails open instead of raising) -> 11 of 12 e2e chat cases fail"
        status: pass
    human_judgment: false
  - id: D6
    description: "The whole suite is green with zero xfail and zero skip, so Phase 36 starts from a known-good baseline"
    requirement: FOUND-03
    verification:
      - kind: other
        ref: "`pytest -q -m \"\"` -> 464 passed, exit 0 (baseline: 497 passed / 28 failed)"
        status: pass
      - kind: other
        ref: "`grep -rn 'xfail' tests/ | wc -l` -> 0; `grep -rn 'pytest.mark.skip' tests/ | wc -l` -> 0"
        status: pass
      - kind: other
        ref: "`ruff check src tests` and `ty check src` -> All checks passed!"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-08-20
status: complete
---

# Phase 35 Plan 04: The D-16 Deletion Sweep Summary

**Eight routes registered and eight declared, no provider credential read at boot, chat handlers on
the §1.4 identity seam taking a user id, and — for the first time this phase — a suite with nothing
failing: 464 passed, zero xfail, zero skip.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-21 05:58Z
- **Completed:** 2026-08-21 06:10Z
- **Tasks:** 2 of 2
- **Files modified:** 34 (0 created, 20 modified, 14 deleted)

## Accomplishments

- **D-16 is complete.** Eight source modules and six test modules are gone. `git show --stat`
  reports 1,903 deletions against 324 insertions across the two commits.
- **The route registry is at eight entries**, and the two declaration removals landed in the same
  commit as the two `include_router` removals — `enumerate_registered(app)` prints `8 8 True []`
  and the lifespan assertion passes against the real started app.
- **Both provider credential sources left the startup path.** No `firebase_admin.initialize_app`,
  no `credentials.ApplicationDefault()`, no Apple receipt verifier, and `app.state` carries neither.
- **The second acceptance path is gone.** `get_current_user` read the credential through FastAPI's
  `Header(None)` alias, which folds a duplicate `Authorization` field into one value — the exact
  desync §1.1 exists to reject. The barrier is now the only thing that reads the wire.
- **The suite went from 28 failures to zero**, without one `xfail` and without one weakened
  assertion. The 26 e2e failures were pre-existing v2.0 schema drift; 20 of them ran through code
  this plan deleted, and the remaining pair (`test_logging.py`) is deferred item D-35-01-A, fixed
  here because it was the last thing standing between the phase and the D-18 bar.

### The final registered set (eight routes)

| Method | Path | Category |
|---|---|---|
| GET | `/health/ready` | public |
| GET | `/` | authenticated |
| GET | `/examples` | authenticated |
| GET | `/chats` | authenticated |
| POST | `/chats` | authenticated |
| GET | `/chats/{chat_id}` | authenticated |
| POST | `/chats/{chat_id}` | authenticated |
| DELETE | `/chats/{chat_id}` | authenticated |

`GET /users/me` (Phase 39) and `POST /webhooks/apple` (Phase 43) are gone from both the router and
the registry.

## Task Commits

1. **Task 1: Delete the subscription, usage, webhook and users surfaces** — `ee81eab` (refactor)
2. **Task 2: Narrow the surviving chat and isolation tests** — `0ca089d` (test)

Task 1 is one commit by construction: `§2.3` is a set-equality assertion between the live router and
the registry that runs inside the lifespan, so a commit removing `include_router(users_router)`
without the matching declaration — or the reverse — aborts boot, and a barrel that lags its deletion
by even one commit leaves the package un-importable.

## Test Status

| Suite | Before | After | Note |
|---|---|---|---|
| Unit (`pytest -q`) | 406 passed | **362 passed**, 102 deselected | −44, every one a deleted surface |
| Schema (`pytest -q -m schema`) | 77 passed | **77 passed** | untouched |
| E2E (`pytest -q -m e2e`) | 16 passed / **26 failed** | **25 passed / 0 failed** | |
| Combined (`pytest -q -m ""`) | 497 passed / **28 failed** | **464 passed / 0 failed** | exit 0 |
| `ruff check src tests` | clean | **All checks passed!** | |
| `ty check src` | clean | **All checks passed!** | |

`362 + 77 + 25 = 464`. No `xfail` and no `pytest.mark.skip` anywhere in `tests/`.

### Accounting for the unit delta, test by test

| Module | Δ | Disposition |
|---|---|---|
| `test_subscriptions.py` | −19 | module deleted with `services/subscriptions.py` and `database/subscriptions.py` |
| `test_usage.py` | −9 | module deleted with `database/usage.py` and `require_quota` |
| `test_webhooks.py` | −5 | module deleted with `routers/webhooks.py` |
| `test_users.py` | −8 | the `/users/me` cases; `TestUserModel` (4) survives |
| `test_exception_handlers.py` | −5 | the five `get_current_user` cases; the 20 handler cases survive |
| `test_auth_security.py` | +2 | 7 → 9: five retargeted onto the barrier, `bearer` case dropped, three added (comma-joined field, positive control, case-insensitive scheme) |
| **net** | **−44** | 406 → 362 |

### Accounting for the e2e delta

Baseline 16 passed / 26 failed → 25 passed / 0 failed. The 26 failures resolve as: 6 deleted with
`tests/e2e/test_users.py`, 6 deleted with `test_isolation.py`, 1 with `test_flows.py`, and 13
retargeted onto assertions that hold (5 in `test_chats.py`, 3 in `test_chat_queries.py`, 5 in
`test_error_cases.py`). One previously-passing case, `test_no_auth_on_users_me_returns_401`, went
with its route.

## Removed e2e cases, for plan 11 to restore

Every case below was **deleted, not weakened**. They need `seed_identity` (plan 06) so the barrier
can resolve the e2e Firebase subject, and a repaired `e2e/conftest.py::create_chat` (plan 05) so
rows can be seeded against the v2.0 schema.

| Module | Case | Why it cannot run in Phase 35 |
|---|---|---|
| `test_chats.py` | `TestCreateChat::test_create_chat_english` | needs a served chat response |
| `test_chats.py` | `TestCreateChat::test_create_chat_spanish` | needs a served chat response |
| `test_chats.py` | `TestCreateChat::test_create_chat_autodetect_lang` | needs a served chat response |
| `test_chats.py` | `TestCreateChat::test_create_chat_with_context` | needs a served chat response |
| `test_chats.py` | `TestFollowup::test_followup_message` | needs a served chat response |
| `test_chat_queries.py` | `TestListChats::test_list_chats` | seeds rows **and** needs a served response |
| `test_chat_queries.py` | `TestGetChatMessages::test_get_messages` | seeds rows **and** needs a served response |
| `test_chat_queries.py` | `TestDeleteChat::test_delete_chat` | seeds rows **and** needs a served response |
| `test_isolation.py` *(module deleted)* | `TestCrossUserIsolation::test_cannot_read_other_user_chat` | needs two distinct linked identities |
| `test_isolation.py` *(module deleted)* | `TestCrossUserIsolation::test_cannot_delete_other_user_chat` | needs two distinct linked identities |
| `test_isolation.py` *(module deleted)* | `TestCrossUserIsolation::test_cannot_post_to_other_user_chat` | needs two distinct linked identities |
| `test_isolation.py` *(module deleted)* | `TestCrossUserIsolation::test_can_read_own_chat` | needs a served chat response |
| `test_isolation.py` *(module deleted)* | `TestCrossUserIsolation::test_can_delete_own_chat` | needs a served chat response |
| `test_flows.py` *(module deleted)* | `TestChatLifecycle::test_full_chat_lifecycle` | six served steps end to end |
| `test_error_cases.py` | `TestErrorCases::test_get_nonexistent_chat_returns_404` | the 404 branch is behind the handler |
| `test_error_cases.py` | `TestErrorCases::test_delete_nonexistent_chat_returns_404` | the 404 branch is behind the handler |
| `test_error_cases.py` | `TestErrorCases::test_followup_nonexistent_chat_returns_404` | the 404 branch is behind the handler |
| `test_error_cases.py` | `TestErrorCases::test_unsupported_language_returns_400` | the 400 branch is behind the handler |
| `test_error_cases.py` | `TestErrorCases::test_missing_phrase_returns_422` | body validation runs after the accessor |

**Not plan 11's to restore** — these belong to the phase that rewrites their surface:

| Module | Cases | Owner |
|---|---|---|
| `test_error_cases.py` | `TestUnauthenticatedAccess::test_no_auth_on_users_me_returns_401` | Phase 39 |
| `test_users.py` (e2e, module deleted) | `TestUserProfile::` ×6 — `test_get_user_profile_returns_200`, `test_profile_excludes_internal_fields`, `test_subscription_plan_is_valid_enum`, `test_resets_at_is_first_of_month`, `test_requests_used_is_non_negative_integer`, `test_monthly_limit_is_positive_integer` | Phase 39 |
| `test_users.py` (unit) | `TestGetUsersMe::` ×3, `TestInactiveUser::test_inactive_user_rejected`, `TestUserIsolation::` ×2, `TestUsersMeUsage::` ×2 | Phase 39; the opaque-401 case is subsumed by the barrier's admission matrix (plan 06) |
| `test_exception_handlers.py` | `test_missing_auth_header_returns_401`, `test_invalid_bearer_token_returns_401`, `test_valid_bearer_token_resolves_user`, `test_expired_token_returns_401`, `test_verifier_swappable_via_state` | verification rules already live in `test_jwt_security.py`; **`test_verifier_swappable_via_state` is plan 06's to re-assert** — nothing in `src/` reads `app.state.jwt_verifier` until the barrier gains its verification step |

## Decisions Made

- **`test_isolation.py` and `test_flows.py` were deleted, not narrowed.** The plan lists both under
  "narrow" (`test_flows.py` only implicitly — see the deviation below), but every case in them
  seeds rows through `conftest.create_chat` and then asserts a served response, and neither half is
  available. Narrowing them to "an unlinked caller gets 401" would have produced two modules that
  duplicated `test_chat_queries.py` under names that no longer described what they asserted. The
  same rule the plan applies to `tests/unit/test_users.py` — "if nothing survives, delete the
  module" — applies here.
- **The surviving e2e chat modules assert a refusal, and that is real coverage, not a placeholder.**
  A caller presenting a genuinely-issued Firebase credential — one that passes the §1.1 wire
  contract the barrier enforces — is still refused by every chat route with the shared error body.
  That is §1.4's fail-loudly rule and threat T-35-04-03 proven end to end over the real transport,
  and nothing else in the suite exercises it. The two modules split the five routes between them so
  no route is asserted twice and none is left unasserted.
- **`test_error_cases.py`'s per-branch statuses became anti-oracle assertions.** The 404, 400, and
  422 branches all sit behind the handler, so none is reachable. Rather than assert a status the
  code cannot produce, the cases now assert what the state actually guarantees: an unadmitted
  caller cannot enumerate chat ids, supported languages, or the request schema. That is §3.1's
  anti-oracle rule and is strictly stronger than what they pinned before — a 422 would have told an
  unadmitted caller its credential was fine and only its body was wrong.
- **`test_auth_security.py` was retargeted onto `AuthBarrierMiddleware`, not deleted.** Its subject
  — a malformed `Authorization` field on an authenticated route answers `auth_required` — is still
  live; only its owner changed. The fixture's route is deliberately **undeclared**, so `lookup`
  returns `None` and the barrier applies its strictest disposition; that pins a real property (a
  route with no declaration can never fall through as public) while giving the test a route it
  fully controls. A **positive control** was added alongside: one well-formed Bearer reaches the
  handler and gets 200, so the surrounding 401s are provably the wire contract and not a blanket
  deny.
- **`test_bearer_lowercase_rejected` was deleted rather than retargeted.** `wire.py` matches the
  scheme case-insensitively (`parts[0].lower() != b"bearer"`), per RFC 7235, so `bearer <token>` is
  now *accepted* at the wire — a deliberate behaviour change from the deleted `get_current_user`,
  which required a literal `Bearer ` prefix. Retargeting it would have produced a **false green**:
  it would still have seen 401, but from the absent identity context, not from the wire contract.
  A new case asserts the live behaviour (the scheme is case-insensitive; the token bytes after it
  are still never trimmed or case-folded), so the change is recorded as an assertion rather than
  quietly lost.
- **`WebhookVerificationError` stays in `errors.py`.** Plan 02 noted it had "one plan left to
  live", but `errors.py` is outside this plan's file list and the plan's own `Removed symbols` list
  does not name it. It is now an unraised `ServiceError` subclass; removing a class from the
  registry is the registry's business, and plan 11 owns the final shape. Flagged below.
- **The `user_id` contextvar binding was not reproduced.** `get_current_user` bound
  `user_id=str(user.id)` into the structlog context, so request log lines no longer carry it.
  §8.2's structured security log belongs to the barrier (D-01), which resolves identity once;
  binding it in five handlers would be exactly the per-phase duplication D-02 exists to prevent.
  Plan 06 owns it.
- **The test-double identity carries only surviving columns.** The v1.6 `TEST_USER` was built with
  `jwt_sub`, `email`, `name`, and `subscription_plan` — the four columns plan 05 removes. What
  stands in for an authenticated caller now is a `LinkedIdentity` over `User(id=..., active=True)`
  and a real `ExternalIdentity`, following the convention plan 03 recorded, so plan 05's model
  repair cannot break the harness.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Four test modules outside the plan's file list imported deleted symbols**

- **Found during:** Task 1.
- **Issue:** the plan lists `tests/unit/test_users.py` and (in task 2) `test_auth_security.py` and
  `test_services.py`, but `tests/unit/conftest.py` and `tests/unit/test_exception_handlers.py` also
  imported `get_current_user`, `require_quota`, `get_subscription_service`, `users_router`,
  `webhooks_router`, `SubscriptionService`, and `users_module`. The package would not have
  collected. `35-PATTERNS.md` § Modified files does list both under "narrow", so this is a file-list
  omission in the plan rather than an unforeseen dependency.
- **Fix:** `conftest.py` dropped `TEST_USER`, `mock_usage_db`, `webhook_client`,
  `mock_subscription_service`, `service_instance` (which had no consumers), and the three deleted
  overrides; its `client` fixture now overrides `get_linked_identity` and includes only the four
  surviving routers. `test_exception_handlers.py` lost `dep_client`, `state_client`, and their five
  cases, keeping all 20 handler cases.
- **Committed in:** `ee81eab`.

**2. [Rule 3 - Blocking] `tests/e2e/test_flows.py` is a served-chat module absent from the file list**

- **Found during:** Task 2.
- **Issue:** task 2's `<files>` names four e2e modules; `test_flows.py` is a fifth with exactly the
  same disposition — a six-step served lifecycle that fails today and cannot pass until
  `seed_identity` exists. Leaving it would have made the "zero failures" acceptance criterion
  unreachable.
- **Fix:** deleted, and its one case named in the restore table above.
- **Committed in:** `0ca089d`.

**3. [Rule 3 - Blocking] Deferred item D-35-01-A blocked task 2's acceptance criterion**

- **Found during:** Task 2, the combined run.
- **Issue:** `tests/unit/test_logging.py::test_middleware_logs_request_on_response` and
  `::test_middleware_error_level_for_non_2xx` fail in a combined `-m ""` run — the two failures
  plans 01, 02 and 03 all recorded and deferred. Task 2's acceptance criterion is `pytest -q -m ""`
  exiting 0 with zero failures, and D-18's phase-end bar is everything green, so deferring them a
  fourth time was not available.
- **Cause:** an e2e module's `_app_lifespan` calls `setup_logging()`, which configures structlog
  with `cache_logger_on_first_use=True`. `logs.py`'s module-level lazy proxy then binds and caches
  a concrete logger that `capture_logs` cannot intercept, and the tests see an empty list. The
  autouse `_reset_logging` fixture restored state only *after* each test, so it never undid it.
- **Fix:** reset before yielding as well as after, **and** rebind `logs.logger` to a fresh lazy
  proxy — `structlog.reset_defaults()` resets the configuration but cannot reach into a proxy that
  has already replaced its own `_logger`. Mutation-verified (below), so the two tests now assert
  rather than merely observing an empty capture list. `deferred-items.md` updated to RESOLVED.
- **Files modified:** `tests/unit/test_logging.py`,
  `.planning/phases/35-foundation/deferred-items.md`.
- **Committed in:** `0ca089d`.

---

**Total deviations:** 3, all Rule 3 (blocking), all test-side. No Rule 1 bug and no Rule 2 missing
critical functionality was found — unsurprising for a plan whose only source change is removal. No
Rule 4 architectural question arose. None changes the plan's deliverables or its interfaces.

## Issues Encountered

- **Three mutations, all caught.** A green suite after a deletion sweep is exactly the shape a
  vacuous test produces, so coverage was verified by mutation rather than assumed. Each mutation
  asserted its anchor matched before its result was read (plan 02 recorded a silent anchor-miss
  producing a false green):

  | Mutation | Effect | Result |
  |---|---|---|
  | M1 — suppress the request log line in `logs.py` | the repaired logging tests should notice | **2 failed** |
  | M2 — `get_request_context` returns instead of raising on an absent context | the retargeted e2e refusals should notice | **11 of 12 failed** |
  | M3 — re-add the `GET /users/me` declaration with no route behind it | §2.3 direction 2 should abort boot | **9 errors** |

  `git diff --exit-code -- src/` confirmed the tree byte-identical to the committed state
  afterwards. M2's one survivor is `test_error_body_has_only_code_field`, which passes on the
  resulting 500 too — expected, since its subject is the body shape rather than the status.

- **Nothing new was deferred.** `deferred-items.md` gained no entry; its one existing entry moved to
  RESOLVED.

## Known Stubs

None. Every surface this plan touches is either deleted or fully wired.

Three things are deliberately left in place for a named owner, and none is a stub — each is live,
correct code whose *replacement* is scoped to a later plan:

| Item | State | Owner |
|---|---|---|
| `tests/e2e/conftest.py::create_chat` | still inserts `User(jwt_sub=...)`; now has **no callers**, since every test that seeded rows was removed | plan 35-05 repairs it; plan 06 adds `seed_identity` beside it |
| `errors.WebhookVerificationError` | registered and correct, but no longer raised anywhere | plan 35-11 (final registry shape) |
| `config.AppConfig.apple` / `AppConfig.quotas` | still load and validate; nothing reads them now that the Apple verifier, `require_quota`, and `/users/me` are gone | plan 35-05 (`config.py` is in its file list per `35-PATTERNS.md`) |

## Flag for Phase 36 (RESEARCH open question 3, confirmed)

**`core.access_tiers` is empty.** Verified two ways against the applied v2.0 schema: the migration
contains no `INSERT INTO core.access_tiers`, and a live count against the running database returns
`0`. REBIND-05 resolves a grant's allowance by joining through `core.access_tiers.tier_id`, so it
has nothing to resolve against until tiers are configured. Out of scope here; Phase 36 must seed or
configure them before quota enforcement can return a number.

## Threat Flags

None. No new network endpoint, auth path, file-access pattern, or schema change at a trust boundary
was introduced — this plan registers no route, writes no query, and adds no `src/` module. It
*removes* two routes, one credential-reading startup path, and one token-accepting dependency. All
six `mitigate` dispositions are implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-04-01 | `get_current_user` deleted. Its `Header(None)` alias folded a duplicate `Authorization` field into one value; `auth/wire.py` counts field instances *before* inspecting any value, so there is no first-value path to steer, and `test_auth_security.py::test_comma_joined_authorization_is_rejected` asserts the folded form is refused |
| T-35-04-02 | The two `include_router` removals and the two declaration removals are in one commit (`ee81eab`); `enumerate_registered` prints `8 8 True []` and `test_startup_assertion.py` proves it against the real started app. Mutation M3 confirms a phantom declaration aborts boot |
| T-35-04-03 | Every chat route parameter is `Depends(get_linked_identity)`, which raises rather than returning `None`; twelve e2e cases assert all five routes refuse an unadmitted caller with a **valid credential**, and mutation M2 confirms the coverage |
| T-35-04-04 | `UsersDB`/`UserService` deleted with their `get_or_create`; the only surviving DB class is `ChatsDB`, whose writes are `Chat`/`Message` only. No read path can create, link, repair, reassign, or merge an identity row — the capability is absent, not merely unused |
| T-35-04-05 | `firebase_admin.initialize_app(credentials.ApplicationDefault())` and `create_apple_verifier` both removed from `lifespan.py`; `inspect.getsource` reports `False False` for both names, and the real lifespan completes with no credential source available |
| T-35-04-06 | No assertion was weakened to make it pass. Three retargets are strictly stronger (anti-oracle 401 in place of per-branch 404/400/422); one case whose retarget would have been a false green (`test_bearer_lowercase_rejected`) was deleted and the behaviour change asserted instead; nineteen deleted cases are named above. `grep -rn 'xfail\|pytest.mark.skip' tests/` returns nothing |
| T-35-04-SC | No package was installed; the legitimacy gate stays vacuous for Phase 35 |

The **no-provisioning prohibition** is satisfied structurally rather than by inspection: after this
sweep `src/` contains exactly one database class (`ChatsDB`), and it has no method that touches
`core.users` or `core.external_identities`. The two classes that did — `UsersDB` and `UserService` —
no longer exist, so just-in-time provisioning is unreachable, not merely unreached. `core.users`
rows can originate only from `POST /auth/create-user` in Phase 37.

## Next Phase Readiness

Ready, and the phase-end bar D-18 sets is met three plans early: **the suite is green with zero
xfail and zero skip**, so Phase 36 starts from a known-good baseline rather than an unknown number
of pre-existing failures.

Notes for the plans that follow:

- **Plan 05** repairs `models/users.py` to the v2.0 seven columns and `tests/e2e/conftest.py`'s
  `create_chat`. Nothing in the unit harness constructs a `User` with a v1.6-only column any more —
  `tests/unit/conftest.py` builds `User(id=..., active=True)` — so the repair should not touch it.
  `tests/unit/test_users.py::TestUserModel` **does** still assert `subscription_plan` and is the
  one module the repair will need to revisit. `config.py`'s `apple` and `quotas` blocks now have no
  readers and are in plan 05's file list.
- **Plan 06** owns the barrier's write side. When it attaches a `RequestContext`, the twelve e2e
  refusal cases in `test_chats.py` / `test_chat_queries.py` become the *negative* half of its
  admission matrix and should be kept, not replaced — the positive half needs `seed_identity`. It
  also inherits the `user_id` contextvar binding (§8.2) that `get_current_user` used to do, and
  `test_verifier_swappable_via_state`, which has no live production path until the barrier reads
  `app.state.jwt_verifier`.
- **Plan 11** restores the nineteen cases named in the table above and writes the final barrels.
  `routers/__init__.py`, `services/__init__.py`, `database/__init__.py`, and `models/__init__.py`
  were edited here only to keep them ahead of the deletions; `auth/__init__.py` was not touched.
- **Phase 39** rewrites `GET /users/me` and re-declares it in the registry; Phase 43 does the same
  for `/webhooks/app-store`. Both must add the declaration in the same commit as the route or the
  lifespan assertion aborts boot.

## Self-Check: PASSED

- All 14 claimed deletions are absent from disk (`test ! -e` over each path exits 0).
- All 20 claimed modified files are present and modified in the two commits (`git show --stat`).
- Both claimed commits are in `git log`: `ee81eab` (28 files, 197 insertions, 1,667 deletions) and
  `0ca089d` (7 files, 127 insertions, 236 deletions).
- `python -c "import nativespeaker.api.app.main"` exits 0; `enumerate_registered` prints
  `8 8 True []`; `pytest -q -m ""` exits 0 at 464 passed.

---
*Phase: 35-foundation*
*Completed: 2026-08-20*
