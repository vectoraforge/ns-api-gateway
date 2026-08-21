---
phase: 35-foundation
plan: 11
subsystem: public-seam
tags: [python, setuptools, pytest, httpx, asgi, sqlmodel, postgresql, openai, mutation-testing]

requires:
  - phase: 35-foundation
    plan: 07
    provides: "auth/adapters.py and auth/budgets.py -- the Protocol-only seams the barrel re-exports"
  - phase: 35-foundation
    plan: 10
    provides: "auth/challenges.py and auth/modesignal.py -- the last seven symbols the barrel needed"
  - phase: 35-foundation
    plan: 06
    provides: "tests/e2e/conftest.py::seed_identity and ::stub_verifier, and linked_firebase_identity"
  - phase: 35-foundation
    plan: 05
    provides: "tests/e2e/conftest.py::create_chat seeding against the v2.0 identity tables"
provides:
  - "nativespeaker.api.auth -- one import root exporting 58 symbols, __all__-first and alphabetized"
  - "all 19 e2e cases plan 04 removed for this plan, restored against seeded identities"
  - "tests/e2e/test_isolation.py and tests/e2e/test_flows.py, recreated"
  - "COVERAGE.md -- the seal-time no-external-API declaration and every accepted v2.0 gap in one place"
  - "a phase-end suite of 1137 passed, zero failures, zero xfail, zero skip, both gates clean"
affects: [36-rebinding, 37-create-user, 38-claim-sync, 39-profile, 40-upgrade, 41-idp-account, 42-claim-grant, 43-webhooks]

actuals:
  tokens: 12323
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Pairing a restored per-branch case with the anti-oracle case on the identical request, so each half is the other's control -- 404/400/422 for an admitted caller beside one 403 for an unadmitted one"
    - "Seeding a second user's row inside a case that asserts ownership, because `== [mine]` and `== [everything]` are the same list when the transaction holds one row"
    - "Carrying the owner's own 200 inline in every cross-user negative case, since a 404 has two causes and only the owner's success separates them"
    - "Recording a defect found while restoring a case, and restoring the case against an input that does not trip it -- rather than pinning the defect as an expected 500, which would make it look intended"

key-files:
  created:
    - tests/e2e/test_isolation.py
    - tests/e2e/test_flows.py
    - .planning/phases/35-foundation/COVERAGE.md
  modified:
    - src/nativespeaker/api/auth/__init__.py
    - tests/e2e/test_chats.py
    - tests/e2e/test_chat_queries.py
    - tests/e2e/test_error_cases.py
    - .planning/phases/35-foundation/deferred-items.md
  deleted: []

key-decisions:
  - "All 19 cases assigned to this plan are restored. None was dropped, none was softened, and no xfail or skip was added anywhere."
  - "`test_create_chat_autodetect_lang` is restored against the incorrect phrase its four neighbours use, not its original correct one. The original input trips D-35-11-A -- a grammatically correct phrase makes POST /chats answer 500 -- which is a pre-existing defect in models/llm.py and config/prompt.txt, both outside this phase, and which §8.3 forbids this phase from changing. The assertions are unweakened and the property under test (an omitted `lang` is served) is unchanged."
  - "No test asserts the 500. Pinning a bug as expected behaviour makes it look intended and has to be deleted the moment it is fixed; the defect is recorded in deferred-items.md and COVERAGE.md instead."
  - "test_isolation.py drives both sides of the boundary as real callers through stub_verifier, rather than the v1.6 shape where only the Firebase user made requests. A 404 has two causes -- wrong owner, or no such row -- and only the owner's own 200 against the same id separates them."
  - "The editable install was not re-run. `__editable__.ns_api_gateway-1.6.0.pth` contains one line adding `src/` to sys.path, so the auth/ subpackage is discovered dynamically and no re-run can change anything; re-running would rewrite uv.lock (D-35-05-A) for no effect."
  - "Four symbols beyond the plan's enumerated list are exported -- ProviderDataEntry, NamedVerifier, VERIFIERS, VerificationResult -- because each is named in a signature or an assertion condition a later phase must satisfy. The error registry is deliberately not re-exported (D-10)."
  - "The restored per-branch cases in test_error_cases.py were kept alongside plan 04's anti-oracle retargets rather than replacing them. They are complementary: unadmitted callers learn nothing, admitted callers get the honest status."

requirements-completed: [FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06, FOUND-07, FOUND-08]

coverage:
  - id: S1
    description: "nativespeaker.api.auth exports the full public seam every later phase imports, __all__-first and alphabetized"
    requirement: FOUND-08
    verification:
      - kind: other
        ref: "`len(a.__all__)` -> 58 (>= 40); `[n for n in a.__all__ if not hasattr(a,n)]` -> []; `a.__all__ == sorted(a.__all__)` -> True"
        status: pass
      - kind: other
        ref: "`from nativespeaker.api.auth import AuthBarrierMiddleware, ChallengeStore, AuditWriter, HmacKeyring, BudgetGate, resolve_identity, classify_mode_signal, assert_route_enumeration` -> `seam ok`"
        status: pass
      - kind: other
        ref: "`hasattr(a,'ErrorResponse'), hasattr(a,'ServiceError')` -> `False False` -- D-10's registry stays at package root"
        status: pass
      - kind: unit
        ref: "890 unit tests pass over the rewritten barrel; ruff `I` accepts the import ordering"
        status: pass
    human_judgment: false
  - id: S2
    description: "Every e2e case removed during plan 04 and assigned to plan 11 is restored against seeded identities"
    requirement: FOUND-03
    verification:
      - kind: e2e
        ref: "19 of 19 restored: test_chats.py 5, test_chat_queries.py 3, test_isolation.py 5, test_flows.py 1, test_error_cases.py 5. Named individually in the table below."
        status: pass
      - kind: e2e
        ref: "e2e suite 148 -> 170; the five modules go 12 -> 34 cases"
        status: pass
      - kind: other
        ref: "eight mutations against the shipped handlers, each caught by the case that names the property"
        status: pass
    human_judgment: false
  - id: S3
    description: "The whole suite passes with zero failures, zero errors, zero xfail markers and zero skip markers"
    requirement: FOUND-03
    verification:
      - kind: other
        ref: "`pytest -q -m \"\"` -> 1137 passed, 0 failed, exit 0 (890 unit + 170 e2e + 77 schema)"
        status: pass
      - kind: other
        ref: "`grep -rn 'xfail\\|pytest.mark.skip\\|pytest.skip' tests/ | wc -l` -> 0"
        status: pass
      - kind: other
        ref: "`ruff check --no-cache src tests` and `ty check src` -> All checks passed!"
        status: pass
    human_judgment: false
  - id: S4
    description: "The application starts for real: the package imports, the lifespan runs to completion, the HMAC keyring validates, and the enumeration assertion executes against the real router"
    requirement: FOUND-03
    verification:
      - kind: other
        ref: "live boot: `registered 8 | declared 8 | set-equal True | problems []`, `enumeration assertion: passed`, `keyring active version: 1`, all five app.state keys present, `lifespan completed`"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py (9 cases) inside the 132-case core-module run"
        status: pass
    human_judgment: false
  - id: S5
    description: "COVERAGE.md records the reasoned no-external-API declaration and every accepted v2.0 gap"
    requirement: FOUND-08
    verification:
      - kind: other
        ref: "first content line is the declaration verbatim; `grep -c 'No external API integration'` -> 1; `grep -c 'FOUND-08'` -> 1; nine gap entries; zero table rows (no capability matrix)"
        status: pass
      - kind: other
        ref: "the three unowned items are marked unowned, not closed: D-35-06-A, the NULL actor_provider, D-35-11-A"
        status: pass
    human_judgment: false
  - id: S6
    description: "No test module asserts a quota outcome on a chat route"
    requirement: FOUND-03
    verification:
      - kind: other
        ref: "`grep -rn quota tests/` -> only config-schema assertions that `quotas` is absent, and the error-registry code list. No chat-route case asserts an allowance."
        status: pass
    human_judgment: false

duration: 29min
completed: 2026-08-21
status: complete
---

# Phase 35 Plan 11: Publishing the Seam and Closing the Phase Summary

**Fifty-eight symbols behind one import root, all nineteen deleted e2e cases restored rather than
excused, and a suite that ends the phase at 1137 passed with nothing behind a marker — plus one
finding the restoration itself produced: `POST /chats` answers 500 for a grammatically correct
phrase, which is the primary route of a grammar-fixing product failing for exactly the input a user
gets when their sentence is already right.**

## Performance

- **Duration:** 29 min
- **Started:** 2026-08-21 08:39Z
- **Completed:** 2026-08-21 09:08Z
- **Tasks:** 3 of 3
- **Files:** 8 (3 created, 5 modified, 0 deleted) — 719 insertions, 68 deletions

## The 19 restored cases, one by one

Every case 35-04-SUMMARY.md assigned to this plan. **None was dropped, none was softened, and no
`xfail`, `skip`, or weakened assertion was introduced anywhere.**

| Module | Case | Restored | How it is now reachable |
|---|---|---|---|
| `test_chats.py` | `TestCreateChat::test_create_chat_english` | yes | `linked_firebase_identity` |
| `test_chats.py` | `TestCreateChat::test_create_chat_spanish` | yes | `linked_firebase_identity` |
| `test_chats.py` | `TestCreateChat::test_create_chat_autodetect_lang` | yes* | `linked_firebase_identity`; input changed, see below |
| `test_chats.py` | `TestCreateChat::test_create_chat_with_context` | yes | `linked_firebase_identity` |
| `test_chats.py` | `TestFollowup::test_followup_message` | yes | `linked_firebase_identity` |
| `test_chat_queries.py` | `TestListChats::test_list_chats` | yes | `linked_firebase_identity` + `create_chat` |
| `test_chat_queries.py` | `TestGetChatMessages::test_get_messages` | yes | `linked_firebase_identity` + `create_chat` |
| `test_chat_queries.py` | `TestDeleteChat::test_delete_chat` | yes | `linked_firebase_identity` + `create_chat` |
| `test_isolation.py` | `TestCrossUserIsolation::test_cannot_read_other_user_chat` | yes | `stub_verifier` + two `seed_identity` pairs |
| `test_isolation.py` | `TestCrossUserIsolation::test_cannot_delete_other_user_chat` | yes | same |
| `test_isolation.py` | `TestCrossUserIsolation::test_cannot_post_to_other_user_chat` | yes | same |
| `test_isolation.py` | `TestCrossUserIsolation::test_can_read_own_chat` | yes | same |
| `test_isolation.py` | `TestCrossUserIsolation::test_can_delete_own_chat` | yes | same |
| `test_flows.py` | `TestChatLifecycle::test_full_chat_lifecycle` | yes | `linked_firebase_identity` |
| `test_error_cases.py` | `TestErrorCases::test_get_nonexistent_chat_returns_404` | yes | `linked_firebase_identity` |
| `test_error_cases.py` | `TestErrorCases::test_delete_nonexistent_chat_returns_404` | yes | `linked_firebase_identity` |
| `test_error_cases.py` | `TestErrorCases::test_followup_nonexistent_chat_returns_404` | yes | `linked_firebase_identity` |
| `test_error_cases.py` | `TestErrorCases::test_unsupported_language_returns_400` | yes | `linked_firebase_identity` |
| `test_error_cases.py` | `TestErrorCases::test_missing_phrase_returns_422` | yes | `linked_firebase_identity` |

**\* the one qualification, stated plainly.** `test_create_chat_autodetect_lang` originally sent
`"I am going home."` — correct English. That input answers **500** (deferred item D-35-11-A, below),
so the case is restored against `"I am going to home."`, the incorrect phrase its four neighbours
already use. Its assertions are the originals, unchanged, and the property it names — a request
omitting `lang` is served — is exactly what it still proves. The input moved; the claim did not.
The docstring says so at the point of use, so nobody has to read this file to learn it.

**Not this plan's, and not adopted** — all still owned where 35-04 put them:

| Module | Cases | Owner |
|---|---|---|
| `test_error_cases.py` | `TestUnauthenticatedAccess::test_no_auth_on_users_me_returns_401` | Phase 39 |
| `test_users.py` (e2e) | `TestUserProfile::` ×6 | Phase 39 |
| `test_users.py` (unit) | `TestGetUsersMe::` ×3, `TestInactiveUser::`, `TestUserIsolation::` ×2, `TestUsersMeUsage::` ×2 | Phase 39 |
| `test_exception_handlers.py` | 5 cases | verification rules live in `test_jwt_security.py`; `test_verifier_swappable_via_state` was re-asserted by plan 06 |

## The defect the restoration found

**`POST /chats` returns 500 for a grammatically correct phrase.** `config/prompt.txt` asks the
model for `issues` and `suggestions` *conditionally* — "if issues exist → provide 3 to 5 distinct
suggestions" — while `models/llm.py::AnalyzeResponse` declares both **required**. A phrase with
nothing to correct comes back as `{resolved_mode, response}`, `model_validate` raises, and the
request 500s.

Probed four ways before concluding anything, because "the LLM was flaky" is the comfortable reading:

| Request | Result |
|---|---|
| `{"phrase": "I am going home."}` (correct, no `lang`) | **500** |
| `{"phrase": "I am going home.", "lang": "en"}` (correct) | **500** |
| `{"phrase": "I am going to home."}` (incorrect, no `lang`) | 200 |
| `{"phrase": "I am going to home.", "lang": "en"}` (incorrect) | 200 |

Phrase correctness is the variable. `lang` is not, which is what rules out the autodetect path and
makes this a defect on the route rather than on the case.

**Not fixed here, deliberately.** `models/llm.py` and `config/prompt.txt` are outside this plan's
file list and outside Phase 35 — this is the auth foundation, and §8.3 requires existing non-auth
contracts to stay unchanged. The fix is also a real choice rather than a typo: default both fields
to `[]` (a correct phrase then returns 200 with empty arrays, changing the client contract), or
change the prompt to always emit them. That is a product decision with an owner, not an auto-fix.

**Why nobody saw it.** The only e2e case that ever sent a correct phrase is the autodetect one,
absent since plan 04's sweep and failing on schema drift before that. No unit test covers the
served LLM path at all. Recorded as **D-35-11-A** in `deferred-items.md` and as gap 9 in
`COVERAGE.md`.

## Mutation verification

Eight mutations against the shipped handlers and DB layer. Each anchor was confirmed to match
exactly once before its result was read, and `git diff --exit-code -- src/` reported the tree
byte-identical after every restore.

| Mutation | Caught by |
|---|---|
| M1 — `get_messages` drops the `user_id` filter | `test_cannot_read_other_user_chat` |
| M2 — `delete` drops the `user_id` filter | `test_cannot_delete_other_user_chat` |
| M3 — `list_chats` drops the `user_id` filter | `test_list_chats`, `test_the_stranger_is_admitted_not_refused` |
| M4 — the `create_chat` handler writes a fresh uuid instead of `identity.user.id` | 7 cases, incl. `test_the_created_chat_belongs_to_the_resolved_user` |
| M5 — `delete_chat` tolerates a rowcount of zero | `test_cannot_delete_other_user_chat`, `test_delete_nonexistent_chat_returns_404` |
| M6 — `create_chat` skips the supported-language check | `test_unsupported_language_returns_400` |
| M7 — `get_messages` returns `[]` instead of raising | 6 cases |
| M8 — `send_message` ignores chat ownership | `test_cannot_post_to_other_user_chat`, `test_followup_nonexistent_chat_returns_404` |

Every mutation is caught by the case that **names** the property, not by an unrelated neighbour.

**M3 is the one worth reading, because it caught one of my own restored cases being vacuous.**
`test_list_chats` asserted `[c["chat_id"] for c in data] == [str(chat_id)]`, which looks like it
pins ownership. It does not, when the transaction holds exactly one chat: `== [the seeded one]` and
`== [every row in the table]` are the same list. The mutant passed it, and was caught only by the
two-identity control I had added to `test_isolation.py`. Seeding a second user's chat inside
`test_list_chats` makes the assertion mean what it appears to mean, and M3 now fails there too.

This is the same shape plan 06 hit with the inner join and plan 10 hit with `uuid4().hex[:22]`: an
assertion that reads as a guarantee while its fixture quietly makes it unfalsifiable. It is worth
noting that it appeared in a case written *in this plan*, with the warning fresh — writing the
strengthened-looking assertion is not the same as writing a strong one.

## The seam

58 symbols, `__all__` first and alphabetized, matching `models/__init__.py`.

| Module | Exported |
|---|---|
| `barrier` | `AuthBarrierMiddleware` |
| `wire` | `BoundedReason`, `extract_bearer` |
| `registry` | `Category`, `RouteMetadata`, `REGISTRY`, `lookup`, `enumerate_registered`, `assert_route_enumeration`, `NamedVerifier`, `VERIFIERS` |
| `context` | `REQUEST_CONTEXT_SCOPE_KEY`, `IdentityKind`, `ClientIpBucketKind`, `LinkedIdentity`, `PreAuthIdentity`, `RequestContext` |
| `identity` | `Admit`, `Reject`, `AdmissionDecision`, `resolve_identity` |
| `verification` | `VerifiedClaims`, `TokenVerifier`, `JWTVerifier`, `VerificationResult` |
| `telemetry` | `RejectionCounter`, `record_rejection` |
| `keys` | `ACTOR_SUBJECT_PREFIX`, `IDP_ACCOUNT_PREFIX`, `HmacConfig`, `HmacKeyring` |
| `audit` | `DETAILS_SCHEMA_VERSION`, `build_details`, `redact`, `AuditWriter` |
| `challenges` | `CHALLENGE_TTL_SECONDS`, `CHALLENGE_ID_BYTES`, `new_challenge_id`, `ChallengeRejection`, `ChallengeStore` |
| `modesignal` | `ModeSignal`, `classify_mode_signal` |
| `budgets` | `ADAPTER_FIREBASE_LOOKUP`, `FIREBASE_LOOKUP_ATTEMPTS`, `BudgetGate`, `BudgetExhausted` |
| `adapters` | `ProviderDataOutcome`, `ProviderDataEntry`, `ProviderDataResult`, `RevocationOutcome`, `FirebaseAdminAdapter`, `VerifiedNotification`, `VerifiedTransaction`, `StoreState`, `StoreAdapter`, `ClaimKind`, `DeviceBitState`, `VendorProofAdapter` |

**Four beyond the plan's enumerated list**, each because a later phase must name it:
`ProviderDataEntry` (the element type of `ProviderDataResult.entries` — a caller reading a result
needs it), `NamedVerifier` and `VERIFIERS` (what §2.3 conditions 4 and 5 resolve a
`provider_callback` route's verifier against, which phases 43 and 44 register into), and
`VerificationResult` (`TokenVerifier.verify`'s return type).

**`errors.py` is deliberately absent**, per D-10 and the plan's recorded assumption. It owns every
client-visible class in the service, not only the auth ones; `from nativespeaker.api.auth import
quota_exceeded` would misdescribe where that class comes from. The barrel's docstring says so, so a
reviewer who expects it there finds the reason at the point of absence.

## Task Commits

| # | Task | Commit | Type |
|---|---|---|---|
| 1 | Publish the `auth/` public seam | `54fa68f` | feat |
| 2 | Restore the e2e coverage that holds again | `40bdd39` | test |
| 3 | Write the phase coverage declaration | `afa4b2f` | docs |

## Test Status

| Suite | Before | After | Δ |
|---|---|---|---|
| Unit (`pytest -q`) | 890 | **890** | untouched |
| E2E (`pytest -q -m e2e`) | 148 | **170** | +22 |
| Schema (`pytest -q -m schema`) | 77 | **77** | untouched |
| Combined (`pytest -q -m ""`) | 1115 | **1137 passed, 0 failed** | +22 |
| `ruff check --no-cache src tests` | clean | **All checks passed!** | |
| `ty check src` | clean | **All checks passed!** | |

`890 + 170 + 77 = 1137`. Zero `xfail`, zero skip: `grep -rn "xfail\|pytest.mark.skip\|pytest.skip"
tests/` returns 0 lines.

The +22 is 19 restored cases plus 3 added while restoring them, each closing a hole the restoration
exposed:

| Added case | Why |
|---|---|
| `test_chats.py::test_the_created_chat_belongs_to_the_resolved_user` | the four served cases assert response shape, which a handler ignoring the identity context entirely would also produce. This reads `core.chats.user_id` back and requires it to equal the seeded `core.users.id` |
| `test_isolation.py::test_the_stranger_is_admitted_not_refused` | without it, an unseeded stranger would produce 403s that read as "isolation holds" to anyone checking only that access failed |
| `test_error_cases.py::test_the_404_body_has_only_code_field` | the shared body shape was asserted on a barrier-raised class only; this pins it on a handler-raised one |

Module movement: `test_chats.py` 3→9, `test_chat_queries.py` 3→6, `test_error_cases.py` 6→12,
`test_isolation.py` 0→6, `test_flows.py` 0→1.

## Decisions Made

- **The editable install was not re-run, and could not have mattered.**
  `__editable__.ns_api_gateway-1.6.0.pth` is a single line adding
  `/home/init/native-speaker/ns-api-gateway/src` to `sys.path` — the plain-path strategy, not a
  static file map — so `auth/` and every file in it are discovered dynamically. Plan 05's `uv sync`
  already refreshed it (`SOURCES.txt` carries 8 `auth/` entries and no stale `auth.py`,
  `exceptions.py`, or `subscriptions.py`). Re-running would have rewritten `uv.lock` for no effect,
  which D-35-05-A explicitly asks the next toucher not to do incidentally.
- **The restored per-branch cases were kept beside plan 04's anti-oracle retargets, not swapped
  for them.** They are complementary and each is the other's control. Without the restored half,
  "every branch answers 403" is equally consistent with a service that *has* no branches — the 422
  case in particular would be satisfied by a route that never validates a body. Without the
  anti-oracle half, the per-branch statuses say nothing about what an unadmitted caller can learn.
  Both module docstrings say this, and the two 422 cases cross-reference each other by name.
- **`test_isolation.py` drives both sides as real callers.** The v1.6 form authenticated as the
  Firebase user and let `create_chat` invent an identity for `"other-user-not-in-firebase"`, so only
  one side ever made a request. Using `stub_verifier` for two seeded, linked, active subjects means
  every negative case can carry the owner's own 200 against the same chat id inline — which is what
  separates "the row belongs to someone else" from "the row does not exist". Without that control
  the entire module would pass unchanged against a service that had lost the chat rows.
- **`test_cannot_delete_other_user_chat` re-reads the chat after the refused delete.** A handler
  that deleted the row and *then* reported 404 satisfies both of the case's original assertions.
- **`test_cannot_post_to_other_user_chat` uses a read as its control rather than a write.** The
  owner posting would prove the same thing and cost an LLM call; the owner reading the same chat id
  establishes that the row exists and is theirs, which is all the 404 needs to be about ownership.
- **`test_flows.py` was restored under its own name** rather than folded into `test_chats.py`, since
  35-04-SUMMARY.md names it as its own module and it is the only case driving all five chat routes
  in sequence against one chat — the one that would notice a route serving correctly in isolation
  while leaving state a later route cannot read.
- **The served cases use the real Firebase credential where they do not need a specific identity
  state**, and `stub_verifier` where they do. `linked_firebase_identity` seeds the genuine
  credential's `(issuer, subject)`, so `test_chats.py`'s served and refused classes differ by
  **exactly one seeded row** and nothing else about the request path — which is what makes each
  class load-bearing for the other.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tests/e2e/test_flows.py` is absent from task 2's file list**

- **Found during:** Task 2, walking the restore table.
- **Issue:** task 2's `<files>` names four e2e modules. `test_flows.py` is a fifth, and
  35-04-SUMMARY.md's table assigns `TestChatLifecycle::test_full_chat_lifecycle` to this plan by
  name. The plan lists `test_isolation.py`, which plan 04 deleted as a whole module, but not
  `test_flows.py`, which it deleted the same way and in the same commit — the mirror image of plan
  04's own deviation 2, where the same module was missing from the deletion plan's file list.
- **Fix:** recreated `tests/e2e/test_flows.py` with its one case restored against
  `linked_firebase_identity`. Leaving it out would have made "every case assigned to this plan is
  restored" false.
- **Committed in:** `40bdd39`.

**2. [Rule 2 - Missing coverage] A restored assertion was vacuous under mutation**

- **Found during:** Task 2, mutation verification.
- **Issue:** `test_list_chats` asserted the returned chat ids equal `[the seeded one]`, which reads
  as an ownership guarantee. With one chat in the transaction it cannot distinguish that from "every
  row in the table", and mutation M3 — `list_chats` dropping its `user_id` filter — passed it.
- **Fix:** the case now seeds a second user's chat and asserts it is absent from the response. M3
  fails there. The docstring records why the second row exists, so a later reader does not tidy it
  away as redundant setup.
- **Committed in:** `40bdd39`.

**3. [Rule 3 - Scope] The plan's own file list would have hidden a defect**

- **Found during:** Task 2, restoring `test_create_chat_autodetect_lang`.
- **Issue:** the case's original input makes `POST /chats` answer 500. Fixing it means editing
  `models/llm.py` or `config/prompt.txt`, both outside this plan and outside Phase 35, and §8.3
  requires existing non-auth contracts unchanged. The three available moves were: fix out of scope,
  silently change the input, or drop the case.
- **Fix:** none of the three as stated. The case is restored against an input that exercises what it
  names, the change is documented in the test itself, and the defect is recorded as D-35-11-A in
  `deferred-items.md` and as gap 9 in `COVERAGE.md` — so the coverage survives and the defect is
  visible in three places rather than absorbed into a passing test.
- **Files modified:** `tests/e2e/test_chats.py`,
  `.planning/phases/35-foundation/deferred-items.md`.
- **Committed in:** `40bdd39`.

**4. [Rule 2 - Missing critical functionality] Four seam symbols beyond the plan's list**

- **Found during:** Task 1, building `__all__`.
- **Issue:** the plan enumerates 43 symbols plus "every Protocol and result type in `adapters.py`".
  `ProviderDataEntry` is the element type of `ProviderDataResult.entries`, so a phase reading a
  result cannot name what it got; `NamedVerifier` and `VERIFIERS` are what §2.3 conditions 4 and 5
  resolve a `provider_callback` route against, which phases 43 and 44 must register into; and
  `VerificationResult` is `TokenVerifier.verify`'s return type. A seam missing them forces a deeper
  import and defeats D-23's one-import-root purpose.
- **Fix:** exported, bringing the total to 58.
- **Committed in:** `54fa68f`.

**5. [Rule 3 - Process] Task 2 ran mutation verification in place of a RED phase**

- **Found during:** Task 2, choosing where its RED commit goes.
- **Issue:** the plan marks task 2 `tdd="true"`, but it adds no source — it restores tests against
  handlers plans 04 and 05 already shipped. Every restored case passes on first write, and the
  fail-fast rule makes a test passing before implementation a stop signal, not a green light.
- **Fix:** wrote the modules, then mutated the shipped source eight times. Deviation 2 above is a
  direct result. This follows plan 10's precedent for the same situation.

---

**Total deviations:** 5 — one Rule 3 file-list omission, one Rule 2 coverage gap found by mutation,
one Rule 3 scope call on an out-of-scope defect, one Rule 2 seam completion, one Rule 3 process
correction. No Rule 1 bug was introduced and no Rule 4 architectural question arose. Deviation 3 is
the one a reader should not skim: the honest handling of a defect a plan has no authority to fix is
to keep the coverage, change nothing about what the case claims, and make the defect louder — not
to route around it quietly.

## Issues Encountered

- **`ruff`'s cache was avoided throughout.** Every lint run used `--no-cache`, per the warning
  carried into this plan that the cache once produced a false `All checks passed!` on a file that
  genuinely failed.
- **The e2e suite calls the real OpenAI API.** Six restored cases drive `POST /chats` through the
  live model — eight calls, about 4 seconds each. `-m e2e` went from 3s to 22s, and the combined run
  from 11s to roughly 30s. This is the pre-existing shape of the e2e suite, not something this plan
  introduced, but it is now load-bearing again after eleven plans in which nothing called the model.
- **Rollback isolation verified, not assumed.** After the full suite the live database reports 0
  rows in `core.users`, `core.external_identities`, `core.chats`, `audit.auth_events`,
  `core.auth_challenges`, and `core.access_tiers`. The restored cases seed users, identities, chats
  and messages, and every row rolled back.
- **`core.access_tiers` is still empty (count 0)**, as plan 04 flagged for Phase 36. Unchanged here;
  recorded in `COVERAGE.md` gap 5.
- **`migrations/` is untouched**, as it has been by every plan in this phase.
- **No out-of-scope discoveries beyond D-35-11-A.** The two warnings in a combined run
  (`langchain_core` pydantic-v1 on 3.14, PyJWT's `InsecureKeyLengthWarning` from
  `test_jwt_security.py`'s deliberate HS256 case) reproduce exactly as measured at baseline.
- **`tests/unit/test_adapter_interfaces.py::test_foundation_calls_no_adapter_method_anywhere_in_src`
  still passes** and was not touched. Its named expiry (35-07) is unchanged: it is correct for
  foundation and wrong the moment a concrete adapter lands.

## Known Stubs

None. Every symbol the barrel exports is implemented and covered, and no test module in the suite
carries a placeholder, an `xfail`, a `skip`, or an assertion softened to make something pass.

Three things are **open and unowned**, and none is a stub — each is complete code or a real defect
rather than an unfinished implementation. All three are recorded in `COVERAGE.md` so the milestone
audit reads them in one place:

| Item | State | Owner |
|---|---|---|
| `RejectionCounter` has no exporter (D-35-06-A) | a correct, incrementing, correctly-labelled counter that nothing reads. §1.2 makes it the **only** detection path for a systemic verification break, so that alert is currently dark | **unowned** |
| `actor_provider` is NULL on every audit row | §4.2's never-fabricated rule holds; `Reject` simply does not carry the resolved identity row. Phase 35 writes zero production audit rows, so nothing is lost yet | Phase 37 owns the widening |
| `POST /chats` 500s on a correct phrase (D-35-11-A) | a live defect on the product's primary route, reproduced four ways | **unowned** — Phase 36 is the natural home but it is a product decision |

## Threat Flags

None. This plan registers no route, opens no network path, adds no dependency, writes no query, and
adds no `src/` module — its one source change re-exports names that already existed. All four
`mitigate` dispositions are implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-11-01 | `grep -rn 'xfail\|pytest.mark.skip\|pytest.skip' tests/` returns **0** lines, asserted as a gate rather than observed. No failing assertion is parked behind a marker anywhere in the phase, so Phase 36 inherits a suite where every case runs |
| T-35-11-02 | No assertion was weakened. All 19 assigned cases are restored with their original assertions; the one input change (`test_create_chat_autodetect_lang`) leaves every assertion intact and is documented at the point of use, in `deferred-items.md`, and in `COVERAGE.md`. The three added cases and the strengthened `test_list_chats` all move in the other direction, and eight mutations confirm the restored cases are load-bearing |
| T-35-11-03 | `COVERAGE.md` records nine accepted gaps — the deferred gateway contract and its four consequences, the removed backend limiting, the k8s 429 body inconsistency, the un-normalized timing, the empty `access_tiers`, the REBIND disposition, and the three open items — with the three unowned ones marked unowned rather than presented as closed |
| T-35-11-SC | No package was installed. The editable install was not even re-run (see Decisions), so `uv.lock` is byte-identical. The legitimacy gate stays vacuous for Phase 35 |

## Next Phase Readiness

Ready. D-18's bar is met: the suite is green at **1137 passed** with zero `xfail` and zero skip, both
gates are clean, and the application boots for real — `registered 8 | declared 8 | set-equal True`,
the enumeration assertion passing against the real router, the keyring validating, and the lifespan
running to completion.

- **Phase 36** imports from `nativespeaker.api.auth` and nothing deeper. Its three inherited facts:
  `core.access_tiers` is empty and must be seeded or configured before REBIND-05 can resolve an
  allowance; REBIND-04 is void; and every time-dependent value must derive from
  `RequestContext.evaluated_at`, never a fresh `now()`. It also inherits D-35-11-A, whose route it
  is rewriting — the natural moment to decide whether a correct phrase returns empty arrays or the
  prompt always emits them.
- **Phase 37** owns `POST /auth/create-user`, the only route that may declare
  `preauth_callable = True`, and the widening of `Reject` that populates `actor_provider`.
- **Phases 37, 40, 41, 42** each implement one challenge-bearing operation against the shipped
  store and build nothing of their own. The §6.4 order is fixed: `locate` → operation comparison →
  `verify_binding` → **claim** → operation-variant comparison → work → `consume`.
- **Phases 43 and 44** register their named verifiers into `VERIFIERS` and declare their
  `provider_callback` routes in the same commit as the routes themselves, or §2.3 aborts boot.
- **`test_foundation_calls_no_adapter_method_anywhere_in_src` must be deleted by the first phase
  that ships a concrete adapter.** It is correct for foundation and wrong from that moment.
- **The metrics exporter (D-35-06-A) is still unowned**, and it is the item most likely to be
  forgotten because nothing fails without it.

## Self-Check: PASSED

- All 3 claimed created files exist on disk (`tests/e2e/test_isolation.py`,
  `tests/e2e/test_flows.py`, `.planning/phases/35-foundation/COVERAGE.md`), and all 5 claimed
  modified files carry the claimed content.
- All 3 claimed commits are in `git log`: `54fa68f`, `40bdd39`, `afa4b2f`.
- `pytest -q -m ""` exits 0 at **1137 passed, 0 failed**; `ruff check --no-cache src tests` and
  `ty check src` both print `All checks passed!`.
- Every acceptance criterion verified by direct execution: `58`/`True` for the barrel probes, `[]`
  for missing names, `False False` for the error-registry absence, `seam ok` for the import probe,
  `0` for the marker grep, `132 passed` for the six core e2e modules, and the live boot printing
  `8 8 True []`.
- `git diff --diff-filter=D --name-only 76c4b58..HEAD` is **empty** — nothing was deleted.
- `git diff --name-only 76c4b58..HEAD` is exactly the 8 files listed above. `.planning/STATE.md`,
  `.planning/ROADMAP.md`, and `uv.lock` are untouched, as instructed — the orchestrator owns the
  first two.
- The three pre-existing working-tree changes that are not mine — `docker-compose.yml`, `.gsd/`,
  `.planning/research/.cache/` — are untouched and remain uncommitted.
- `migrations/` is untouched.

---
*Phase: 35-foundation*
*Completed: 2026-08-21*
