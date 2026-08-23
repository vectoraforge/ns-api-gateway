---
phase: 37-post-auth-create-user
plan: 08
subsystem: auth
tags: [challenge-protocol, rejection-precedence, audit, firebase-admin, tenacity, error-classes]
status: complete

# Dependency graph
requires:
  - plan: "37-07"
    provides: "the tracer's `_challenge_rejected` / `_lookup_rejected` stubs, the shared FakeFirebaseAdapter, and `_complete`'s claim-commits-before-lookup shape"
  - plan: "37-05"
    provides: "classify_provider_data and email_to_persist — the closed classifier whose rejection this maps"
  - plan: "37-03"
    provides: "OPERATION_NOT_ALLOWED (403); AUTH_REQUIRED (401) and VERIFICATION_TEMPORARILY_UNAVAILABLE (503) were already registered"
  - plan: "37-02"
    provides: "lookup_with_retry plus LOOKUP_UNAVAILABLE_RESULT / LOOKUP_UNAVAILABLE_ERROR_CLASS — the exhaustion mapping as one named fact"
  - plan: "37-01"
    provides: "ChallengeStore.issue without operation_variant, and ChallengeRejection's value-equals-AuthEventResult property"
provides:
  - "Every rejection arm of POST /auth/create-user's completion mode: nine internal results over four client classes"
  - "`_challenge_rejected` — the five §6 rejections, each with its own standalone-durable audit row, none consuming"
  - "`_consuming_rejection` — every rejection at or after the Admin lookup, consuming inside one transaction with its audit row"
  - "`_LOOKUP_REJECTIONS` and `_classification_cause` — the ProviderDataOutcome -> (AuthEventResult, ErrorClass) table and the bounded cause"
  - "`_completion_details` — §4.4's six-key object for a completion rejection"
  - "tests/unit/test_create_user_precedence.py — 25 cases, five of them compound precedence proofs"
affects: [37-09, 37-10, 38, 39, 40, 41, 42]

actuals:
  tokens: 24982
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "A rejection helper per consumption disposition, not per rejection: the boundary is the shape, so the two helpers ARE the two dispositions"
    - "Distinguishing two claim-failure reasons by re-reading the located row's `claimed_at`, never by a second conditional update and never by re-reading the deadline"
    - "A fake store that mirrors both conditional-update WHERE clauses exactly, while delegating the pure binding comparison to the real store"
    - "Compound unit cases that make two things wrong at once, so precedence is proven by conflict rather than asserted by reading order"

key-files:
  created:
    - tests/unit/test_create_user_precedence.py
  modified:
    - src/nativespeaker/api/routers/auth.py
    - tests/e2e/test_create_user.py
    - tests/unit/test_create_user_modes.py

key-decisions:
  - "Within §02 step 4 the identity binding is checked BEFORE the operation. The spec names both and orders neither; the binding runs first because the sentence itself does and because `verify_binding` owns the comparison the step is named for. Pinned by an explicit unit case."
  - "The claim loser distinguishes expired from consumed by `session.refresh(challenge)` and reading `claimed_at` alone. Reading the deadline would be a second expiry evaluation; a second conditional update would be a second serialization point."
  - "The two helpers are split by consumption disposition rather than by spec step: `_challenge_rejected` (standalone-durable, consumes nothing) and `_consuming_rejection` (consume + audit in one transaction)."
  - "`_LOOKUP_REJECTIONS` is a dict of kwargs rather than a tuple, so a new outcome cannot be added without naming both halves of its mapping at the table."
  - "`_classification_cause`'s `empty` branch is kept although unreachable from this route, because the bounded vocabulary is shared with phases 40/41/42, which do require a linked provider."
  - "37-07's mode-signal stub session now records `rollback` instead of raising — the `challenge_not_found` arm legitimately releases its read transaction before the standalone write."

patterns-established:
  - "Read a correlation id off an ORM instance BEFORE any rollback: SQLAlchemy expires every instance on rollback and a later attribute touch is a lazy load off the event loop"
  - "A grep-based acceptance criterion is kept as a live detector by keeping the forbidden literal out of prose too, rather than by deleting the prose"

requirements-completed: [CREATE-01, CREATE-02]

coverage:
  - id: D1
    description: "All five challenge rejections return a byte-identical 409 `challenge_required` while each writes its own internal result — challenge_not_found, challenge_expired, challenge_consumed, challenge_identity_mismatch, challenge_operation_mismatch"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections (8 cases)"
        status: pass
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestCompletionRejectionsOnTheWire::test_an_unknown_handle_is_challenge_required_and_audited"
        status: pass
    human_judgment: false
  - id: D2
    description: "Unknown-handle, identity-mismatch and operation-mismatch rejections occur BEFORE the claim and leave the located challenge unclaimed and unconsumed"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections::test_a_challenge_bound_to_another_subject_is_an_identity_mismatch and ::test_a_challenge_for_another_operation_is_an_operation_mismatch (claimed_at / consumed_at both NULL afterwards)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A pre-auth row whose preauth_subject_hash was already cleared skips the hash comparison entirely and takes the already-used rejection audited challenge_consumed"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections::test_a_cleared_binding_hash_is_already_used_and_is_never_compared (keyring spy comparison count 0)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The claim loser performs no work at all: no Firebase Admin lookup, no mutation, and never the claim-holder's stored outcome"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections::test_an_already_claimed_challenge_is_challenge_consumed and ::test_a_still_issued_but_expired_challenge_is_challenge_expired (adapter call count 0)"
        status: pass
    human_judgment: false
  - id: D5
    description: "A Firebase user_not_found maps to internal firebase_user_unresolved and client auth_required (401), never verification_temporarily_unavailable, and persists nothing"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheProviderStageRejections::test_user_not_found_is_auth_required_and_persists_nothing (401, adapter call count 1, creator never called)"
        status: pass
    human_judgment: false
  - id: D6
    description: "A retryable_failure surviving all 3 attempts and a selection_failure both map to firebase_lookup_unavailable and verification_temporarily_unavailable (503), persisting nothing"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheProviderStageRejections::test_an_exhausted_retry_budget_is_verification_temporarily_unavailable (call count 3) and ::test_a_selection_failure_is_unavailable_on_its_first_attempt (call count 1)"
        status: pass
    human_judgment: false
  - id: D7
    description: "A providerData shape the closed classifier rejects maps to provider_not_linked with bounded cause invalid-shape and client operation_not_allowed (403), persisting nothing"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheProviderStageRejections::test_a_rejecting_provider_data_shape_is_operation_not_allowed (3 parametrized shapes)"
        status: pass
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestCompletionRejectionsOnTheWire::test_a_password_entry_is_operation_not_allowed_and_consumes_the_challenge (details.failure.cause asserted on a real row)"
        status: pass
    human_judgment: false
  - id: D8
    description: "Every rejection at or after the Admin lookup consumes the challenge, clearing preauth_subject_hash; a retry requires a fresh prepare"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestEveryProviderStageRejectionConsumes::test_the_challenge_is_consumed_and_its_binding_cleared (4 parametrized outcomes)"
        status: pass
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestCompletionRejectionsOnTheWire::test_a_password_entry_is_operation_not_allowed_and_consumes_the_challenge (consumed_at set, hash NULL, on a real row)"
        status: pass
    human_judgment: false
  - id: D9
    description: "Running a completion twice with the same challenge_id rejects the second as challenge_consumed and mints nothing — no idempotent replay"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestEveryProviderStageRejectionConsumes::test_a_replay_after_a_rejection_is_challenge_required_and_mints_nothing"
        status: pass
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestCompletionRejectionsOnTheWire::test_the_same_handle_replayed_after_a_rejection_mints_nothing"
        status: pass
    human_judgment: false
  - id: D10
    description: "Rejection precedence follows §02's numbered order — the earliest failed step is the one reported — proven by conflict rather than by reading order"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestThePrecedenceItself (5 compound cases: 3>8, 4>5, binding>operation, 5>8, 8>9)"
        status: pass
    human_judgment: false
  - id: D11
    description: "Exactly one audit.auth_events row per on-path completion attempt, and the audited internal result is never less specific than the client class returned"
    requirement: CREATE-02
    verification:
      - kind: unit
        ref: "tests/unit/test_create_user_precedence.py#TestTheFiveChallengeRejections::test_every_rejection_writes_exactly_one_audit_row_correlated_on_the_row_id and the len(writer.rows) == 1 assertion in TestEveryProviderStageRejectionConsumes"
        status: pass
      - kind: integration
        ref: "tests/e2e/test_create_user.py — one row correlated on challenge_row_id, and the challenge_not_found count delta of exactly 1"
        status: pass
    human_judgment: false
  - id: D12
    description: "CREATE-01's observable half: one unlinked token is admitted at POST /auth/create-user?challenge=true (200) and refused at GET /examples with preauth_identity_not_allowed (403)"
    requirement: CREATE-01
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestCreate01AdmittedHereAndRefusedEverywhereElse::test_one_unlinked_token_is_admitted_at_create_user_and_refused_at_examples"
        status: pass
    human_judgment: false

# Metrics
duration: ~40 min
completed: 2026-08-23
---

# Phase 37 Plan 08: The Completion Rejection Precedence Summary

**Every rejection arm of `POST /auth/create-user` now carries its own internal result, its own client class and its own consumption disposition — including the `user_not_found` arm the tracer was returning at 503 where §02 earns 401 — with the precedence proven by compound cases that make two things wrong at once.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 3
- **Files:** 4 (1 created, 3 modified, 0 deleted)
- **Tests:** unit 1105 → 1122, e2e 220 → 224. Zero failures at every gate.

## Task Commits

1. **Task 1: the five challenge rejections** (TDD) — `52c19fa` (test, RED: 8 failing) → `1a6d6b3` (feat, GREEN)
2. **Task 2: the provider-stage outcomes** (TDD) — `9bac010` (test, RED: 11 failing) → `c3484ff` (feat, GREEN)
3. **Task 3: the precedence, by conflict and on the wire** — `dc91c2e` (test)
4. Follow-up: `559bc27` — keeping a grep detector live (see Deviations 3)

No REFACTOR commit: neither GREEN implementation needed cleanup.

## The Live Bug That Was Fixed First

`_lookup_rejected` mapped **every** non-`ok` `ProviderDataOutcome` to `verification_temporarily_unavailable` (503). `user_not_found` is one of those outcomes, and §02's error table earns it `auth_required` (401).

The two are one letter apart in intent and incompatible in effect. 503 tells a client "the lookup failed, back off and retry the whole operation" — so a caller holding a valid token for a **deleted** Firebase user would retry forever against a fact Firebase has already stated permanently. 401 tells it the truth: re-authenticate. It is now a distinct arm with a distinct internal result (`firebase_user_unresolved`), and T-37-38's whole point is that the pair cannot collapse again without failing a test that asserts both statuses.

## The Three Things the Plan Asked This Summary to Record

### 1. Inside §02 step 4, the identity binding is checked before the operation

§02 step 4 names both checks in one sentence and orders neither: *"Verify binding: request's verified issuer == `preauth_issuer` AND recomputed HMAC verifier == `preauth_subject_hash` ...; operation must be `create_user`."*

**The binding runs first.** Two reasons, neither of them "that is how the tracer happened to write it":

- the sentence itself introduces the binding as the step's subject and appends the operation as a second clause;
- `ChallengeStore.verify_binding` is the method the step is *named* for, and it owns the keyed comparison. Putting the cheaper operation check ahead of it would mean a challenge legitimately bound to the presenter but issued for another operation is reported ahead of one bound to somebody else — inverting which fact the audit trail records for a wrong-endpoint attack.

Both are pre-claim rejections collapsing to the same client class, so the choice is observable **only** in the audit row. That is exactly why it needed to be a decision on the record: `TestThePrecedenceItself::test_the_identity_binding_is_checked_before_the_operation` presents a challenge that is simultaneously bound to another subject *and* issued for another operation, and asserts `challenge_identity_mismatch`.

### 2. The bounded `provider_not_linked` causes written into `details.failure`

Two members, D-12 having removed the third with the declaration it described:

| Value | Written when | Reachable from this route? |
|---|---|---|
| `invalid-shape` | Every shape the closed classifier rejects: both providers at once, multiple entries, an unrecognized `provider_id` (`password`, `facebook.com`), or a recognized entry with an empty `uid` | **Yes** — this is the only cause `create_user` can emit |
| `empty` | An account with no providerData **in a context that required one** | **No.** The closed classifier answers `anonymous` to an empty read and never rejects it, so `create_user` cannot reach this branch |

The `empty` branch is kept deliberately. Phases 40/41/42 do require a linked provider and reach the same bounded vocabulary, and one function owning both members is what keeps the vocabulary a single fact rather than one per caller. The key is `details.failure.cause`, present **only** for `provider_not_linked` — absent rather than `None`-valued everywhere else, so a reader cannot mistake "not applicable" for "applicable and unknown".

`supported-provider-mismatch` appears nowhere in `src/` as code — see Deviations 2 for the one prose occurrence and why it stays.

### 3. No `tenacity.RetryError` reaches a client on any arm — confirmed

Three independent facts, each asserted:

- `lookup_with_retry` installs `retry_error_callback`, which hands the last `ProviderDataResult` back instead of raising. 37-02 owns that and its unit suite pins it.
- This handler never wraps the call in a `try`, so there is no path where a `RetryError` could be caught-and-relabelled into something else either.
- End to end, `test_an_exhausted_retry_budget_is_verification_temporarily_unavailable` drives three consecutive `retryable_failure` results through the real router with `raise_server_exceptions=False` and asserts **503 with the `verification_temporarily_unavailable` body**. A `RetryError` escaping would surface as a 500 there, which is precisely the failure the case is shaped to catch. The adapter call count of exactly 3 in the same case proves the budget is neither short-circuited nor unbounded.

## How the Two Helpers Are Split

Not one helper per spec step, and not one per rejection — **one per consumption disposition**, because the consumption boundary is the architectural fact and everything else follows from which side of it a rejection sits on.

| | `_challenge_rejected` | `_consuming_rejection` |
|---|---|---|
| Covers | §02 steps 3–5 (five internal results) | §02 steps 8–9 (four internal results) |
| Client classes | one: `challenge_required` (409) | three: 401 / 503 / 403 |
| Consumes | **never** | **always** |
| Audit mode | `write_standalone` after `session.rollback()` | `write_in_transaction`, committed with the consume |
| Why | no consuming transaction exists yet; there is nothing for the row to be atomic with | a row written outside that transaction could describe a consumption that did not happen |

**None of the five challenge rejections consumes**, and the code says so once at the call sites rather than five times: `challenge_not_found` has no row; the identity and operation mismatches are pre-claim *on purpose*, so a wrong presenter cannot burn the rightful user's in-flight challenge; and the two claim losers never held a claim, so they have nothing to consume.

## The Claim Loser Reads `claimed_at`, Never the Deadline

`ChallengeStore.claim` returning `False` has two causes, and `challenges.py:168-172` instructs the caller to distinguish them by **re-reading the located row** rather than by issuing a second conditional update. The handler does `await session.refresh(challenge)` and then reads `claimed_at` alone:

- still `NULL` → the row is issued, so the claim can only have failed its deadline → `challenge_expired`
- non-`NULL` → somebody else already holds it → `challenge_consumed`

Reading the deadline column here would be a **second expiry evaluation**, which is the single thing the claim's `WHERE` exists to be. A second conditional update would be a second serialization point that can disagree with the first. The deadline column's name appears nowhere in this handler outside prepare-mode response construction, verified by AST (see Verification Commands).

## Step 7 Is Recorded, Not Silently Skipped

§02 step 7 gates the Admin lookup on three budgets. D-02 drops two of them —
`create_user_firebase_identity_lookup` (60/min, key `deployment`) and
`create_user_firebase_identity_lookup_ip` (10/min, key client IP) — because both are per-minute IP- and deployment-keyed **traffic limits written in budget vocabulary**, and building anything that could carry them is what D-01 rules out for this route. Only the retry budget survives, expressed by D-04 as `tenacity`.

A comment at the lookup call site names D-01/D-02 as a **flagged SHARED-INVARIANTS conflict, recorded and not silently resolved**, so a reader comparing this handler to §02 finds the answer there rather than assuming an omission. T-37-40 is `accept`, unchanged: one request still costs at most three provider calls, each timeout-bounded.

## Deviations from Plan

### 1. [Rule 3 — Blocking] 37-07's mode-signal stub session had to stop raising on `rollback`

- **Found during:** Task 1 (the full unit suite, after GREEN — two cases in `tests/unit/test_create_user_modes.py` failed)
- **Issue:** That module's `_UnlinkedSession.rollback` raised `AssertionError("no path in this module may roll back")`. Its two completion cases reach `challenge_not_found`, which now writes a standalone-durable audit row — and that requires releasing the read transaction `locate` opened first, exactly as prepare's already-linked arm already did. The stub's assumption was true when written and false the moment the audit row existed.
- **Fix:** `rollback` records a count instead of raising, with the reason at the class docstring; `commit` still raises, because no path in that module may reach one. The count is kept so the release stays *observable* rather than merely tolerated.
- **File touched outside the declared three:** `tests/unit/test_create_user_modes.py`. It is 37-07's completed test file, is not in 37-09's `files_modified`, and the change is a harness correction rather than a production one — so it is merge-safe against the concurrent worktree.
- **Committed in:** `1a6d6b3`

### 2. [Self-invalidating acceptance criterion] `grep -c "supported-provider-mismatch" src/` cannot literally return 0

- **The criterion:** Task 2's acceptance list requires zero occurrences in `src/`.
- **The conflict:** 37-05 shipped `auth/classifier.py`'s module docstring, which explains the removal by naming the value: *"the third cause, `supported-provider-mismatch`, went with the declaration"*. That is one occurrence, in a file this plan does not own, documenting exactly the fact the criterion is checking for.
- **Resolution — the criterion's intent, not its letter:** the literal appears in **no code position anywhere in `src/`** — not as a string value, not as an identifier, not in the bounded-cause function. The single occurrence is line 26 of a module docstring, and it is substantive documentation of a spec amendment. Deleting it to satisfy a grep would remove the record of D-12 while leaving the codebase byte-identical in behaviour.
- **Nothing was dropped from either side**, and no new occurrence was introduced by this plan.

### 3. [Self-invalidating acceptance criterion] `grep -c "expires_at" src/.../auth.py` cannot literally return 0

- **The criterion:** Task 1 requires zero occurrences "outside the prepare-mode response construction".
- **The conflict:** prepare-mode construction itself accounts for four occurrences (the `PrepareResponse` field, the `issue` destructuring, the model construction, and a docstring line), so a bare `grep -c` can never be 0.
- **Resolution:** verified by **AST** instead — every `Name`, `Attribute`, `keyword` and annotation reference to the column resolves to `PrepareResponse` (line 104) or `_prepare` (lines 209, 213). **Zero references anywhere in `_complete` or any helper it calls.** Output recorded below.
- **A related self-imposed correction (`559bc27`):** the first draft of the claim-loser comment named the column and the constant-time comparison primitive in prose. 37-07 pinned zero greps for both in this module precisely so a grep stays a **live detector** of "somebody added a second expiry evaluation / a second keyed comparison here". Prose occurrences would blunt that detector permanently. Both comments were reworded to keep the full substance — *do not read the deadline here, do not write a comparison here, and here is what owns each* — while restoring the greps to zero. This is the opposite of dropping documentation: the note now says why the name is absent.

### Not encountered

- **No Rule 4 architectural decision.** Every branch fitted the shape the tracer left.
- **The src-wide adapter-method scan never fired.** No adapter method name appears in `routers/auth.py` in code or prose; `ADAPTER_IMPLEMENTORS` is untouched and `test_adapter_interfaces.py` passes at 56.
- **No file was deleted**, and `auth/creation.py`, `STATE.md` and `ROADMAP.md` were not modified.

## Known Stubs

**None from this plan.** Both branches 37-07 assigned here are complete.

The two remaining Known Stubs from 37-07 belong to **37-09** and are untouched by this plan, as required by the wave's file ownership:

| # | Gap | Owner | Site |
|---|---|---|---|
| 3 | `except IntegrityError` → rollback-to-savepoint + constraint-name discrimination | 37-09 | `auth/creation.py::_insert_account` |
| 4 | Blocked-user discrimination in the in-transaction re-resolution | 37-09 | `auth/creation.py::_result_for_existing` |

`_completion_response`'s rejection arms are likewise still 37-09's; this plan did not touch them.

## Threat Flags

None. No security-relevant surface appeared beyond what the plan's `<threat_model>` registered. Every `mitigate` disposition has a passing assertion:

| Threat | Status |
|---|---|
| T-37-34 (challenge-state enumeration oracle) | All five return a byte-identical body asserted by equality, not by key lookup; only the audit row differs |
| T-37-35 (burning another user's in-flight challenge) | Identity and operation mismatches assert `claimed_at` and `consumed_at` both still NULL afterwards |
| T-37-36 (idempotent replay returning the holder's outcome) | No stored-outcome replay and no `challenge_replayed` result exist; the replay asserts 409 and zero new rows, unit **and** e2e |
| T-37-37 (account for a deleted Firebase user) | `user_not_found` → 401, `creator.calls == []`, adapter call count 1 |
| T-37-38 (retry-forever on a definitive failure) | 401 and 503 asserted at distinct statuses with distinct internal results, in separate cases |
| T-37-39 (a rejection failing to consume) | Four parametrized outcomes assert `consumed_at` set and `preauth_subject_hash` NULL; the e2e case proves it on a real row and the replay proves the handle is dead |
| T-37-40 (unbounded provider calls per request) | **Accepted**, unchanged — recorded as a flagged D-01/D-02 conflict at the call site; a request costs at most three calls |
| T-37-SC (package installs) | No install in this plan |

## Verification Commands Run

| Command | Result |
|---|---|
| `pytest -q` | **1122 passed**, 320 deselected, 0 failed (baseline 1105) |
| `pytest -q -m e2e` | **224 passed**, 1218 deselected, 0 failed (baseline 220) |
| `pytest -q tests/unit/test_create_user_precedence.py` | 25 passed |
| `pytest -q -m e2e tests/e2e/test_create_user.py` | 10 passed (baseline 6) |
| `pytest -q tests/unit/test_adapter_interfaces.py` | 56 passed |
| `ruff check src/ tests/` | All checks passed |
| `python -c "import nativespeaker.api.app.main"` | exit 0 |
| AST: deadline-column references in `routers/auth.py` | `[(AnnAssign,104),(Name,104),(Name,209),(keyword,213),(Name,213)]` — all in `PrepareResponse` / `_prepare`, **zero** in the completion path |
| `grep -c "compare_digest" routers/auth.py` | 0 |
| `grep -c "rowcount" routers/auth.py` | 0 |
| `get_user_provider_data in routers/auth.py source` | `False` |
| `grep -rn "supported-provider-mismatch" src/` | 1 — `classifier.py:26`, a docstring (see Deviations 2) |
| `git diff --diff-filter=D --name-only <base>..HEAD` | empty — no file deleted |
| `git diff --stat <base>..HEAD` | 4 files, `auth/creation.py` / `STATE.md` / `ROADMAP.md` absent |

RED gates confirmed before each GREEN: Task 1 at 8 failures, Task 2 at 11 failures, each failing for the intended reason (no audit row / wrong class) rather than a harness error.

## Next Phase Readiness

- **37-09** is unblocked and unaffected: `auth/creation.py` is byte-identical to what 37-07 left, and `_completion_response`'s rejection arms are still its scope. The one change it will notice is that `_complete` now takes `session_factory` as its second positional parameter — a router-internal signature it does not call.
- **37-10** can drive `FakeFirebaseAdapter` through every outcome this plan mapped; the scripted-outcome fixture pattern and the call-count assertions are established in `tests/unit/test_create_user_precedence.py`.
- **Phases 40/41/42** reuse `_classification_cause`'s bounded vocabulary — including the `empty` member this route cannot reach — and the `_challenge_rejected` / `_consuming_rejection` split, which generalizes to any challenge-bearing route because the consumption boundary is the same one.
- **Still unmeasured, carried from 37-05/37-07:** RESEARCH A5 — whether `httpTimeout` bounds a genuinely slow `getUser`. Nothing here touched real Firebase.

## Self-Check: PASSED

- Created file exists: `tests/unit/test_create_user_precedence.py`.
- All six commits present in `git log 0ef83e1..HEAD`: `52c19fa`, `1a6d6b3`, `9bac010`, `c3484ff`, `dc91c2e`, `559bc27`.
- TDD gate sequence intact for both TDD tasks: `test(37-08)` precedes `feat(37-08)` in each pair.
- `git diff --diff-filter=D --name-only` → empty. No file deleted.
- Branch verified `worktree-agent-aa96e46855306a224` (per-agent namespace) before every commit; worktree descends from base `0ef83e1`.
- No modifications to `.planning/STATE.md`, `.planning/ROADMAP.md`, or `src/nativespeaker/api/auth/creation.py`.

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-23*
