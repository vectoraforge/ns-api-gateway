---
phase: 37-post-auth-create-user
plan: 10
subsystem: auth
tags: [e2e, firebase-admin, adc, anonymous-identity, provider-account-reservation, email-copy-rule, credential-provisioning]
status: complete

# Dependency graph
requires:
  - plan: "37-07"
    provides: "the tracer's e2e module, the adapter-swapping fixture, and create_account's field derivations"
  - plan: "37-08"
    provides: "the rejection precedence on the wire, and CLIENT_CLASS_FOR_RESULT's operation_not_allowed arm"
  - plan: "37-09"
    provides: "PROVIDER_ACCOUNT_INDEX_NAME -> provider_account_already_linked, and the rollback-to-savepoint arm this exercises end to end"
  - plan: "37-05"
    provides: "ProviderDataResult.email / .email_verified (the Phase 35 foundation amendment), classify_provider_data, email_to_persist, build_admin_apps"
provides:
  - "tests/e2e/conftest.py::anonymous_firebase_credential — a genuinely anonymous Firebase user, minted for real"
  - "The real-anonymous end-to-end proof: the real Admin SDK returns entries == () and a real completion succeeds"
  - "Registered-flow coverage for google and apple, and §02 step 10's five email cases"
  - "The provider-account reservation on the wire, for an ACTIVE and for a historical owner"
  - "Symmetric Firebase app lifecycle: the lifespan deletes the named apps it created"
affects: [38, 39, 40, 41, 42, 46]

actuals:
  tokens: 71000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A credential-availability predicate that calls the same two functions the production builder calls, in the same order, rather than re-reading the environment"
    - "Asserting the SHAPE in a case separate from the CONSEQUENCE — consequences can be right for the wrong reason"
    - "isinstance(adapter, FirebaseAdminLookup) as an explicit guard that a case is unsubstituted, because 'deliberately did not request the fixture' is invisible in a diff"
    - "Mutation-checking every new group before trusting it green"

key-files:
  created: []
  modified:
    - tests/e2e/test_create_user.py
    - tests/e2e/conftest.py
    - .env.example
    - src/nativespeaker/api/app/lifespan.py
    - .planning/phases/37-post-auth-create-user/37-VALIDATION.md

key-decisions:
  - "D-08 AMENDED: the Admin credential now arrives through Application Default Credentials, not a key in .env. Forced by the org policy iam.disableServiceAccountKeyCreation — no key is mintable on this project at all. See § The D-08 Deviation."
  - "The skip predicate asks whether build_admin_apps would find a credential, by calling its two source probes, rather than testing os.environ['FIREBASE_SERVICE_ACCOUNT_JSON'] as the plan's acceptance criterion literally asked. The literal form would have skipped the one case that can now run."
  - "The real-anonymous coverage is two cases, not one: the completion asserts the consequence, and a separate case asserts the providerData shape the classifier actually depends on."
  - "No delete_user teardown. T-37-50 accepted; the coordinator confirmed the user did not ask for the teardown variant."
  - "The lifespan now deletes the Firebase apps it created. Whoever registers a process-global handle destroys it."

patterns-established:
  - "A test-package predicate that must agree with a production decision should CALL the production code, not restate its inputs"
  - "When a plan's grep-style acceptance criterion has been invalidated by a change landing mid-plan, satisfy the intent and record the divergence rather than satisfying the letter"

requirements-completed: [CREATE-01, CREATE-03]

coverage:
  - id: D1
    description: "A completion whose providerData carries exactly one google.com (resp. apple.com) entry creates an ACTIVE identity with that provider, the entry's uid verbatim as provider_uid, and a non-NULL registered_at"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheRegisteredFlow::test_one_recognized_entry_creates_a_registered_account (2 params: google, apple)"
        status: pass
    human_judgment: false
  - id: D2
    description: "§02 step 10's email copy rule end to end: the address lands in core.users.email only when the same getUser response carried a non-empty address AND emailVerified true"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestStep10sEmailCopyRule (5 params: verified, unverified, empty, whitespace-only, absent)"
        status: pass
      - kind: other
        ref: "Mutation check: deleting the `email_verified` guard from classifier.email_to_persist turns the `non-empty-but-unverified` case red; reverted and verified byte-identical"
        status: pass
    human_judgment: true
  - id: D3
    description: "display_name is NULL and no entitlement row exists after every completion in the module, on every branch"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py::_assert_step_10s_global_invariants, called by all 10 completion-driving cases"
        status: pass
    human_judgment: false
  - id: D4
    description: "A provider account already reserved by another (issuer, subject) refuses a second subject with 403 operation_not_allowed audited provider_account_already_linked — and retirement does not free it"
    requirement: CREATE-03
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheProviderAccountReservation (2 params: owner-active, owner-historical)"
        status: pass
      - kind: other
        ref: "Mutation check: perturbing the scripted uid by one suffix turns both cases red, so the 403 is the index firing and not an unrelated arm"
        status: pass
    human_judgment: true
  - id: D5
    description: "A genuinely anonymous Firebase user, minted through accounts:signUp, completes account creation through the REAL Admin SDK with nothing substituted"
    requirement: CREATE-01
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheRealAnonymousCompletion::test_a_genuinely_anonymous_user_completes_through_the_real_admin_sdk"
        status: pass
    human_judgment: false
  - id: D6
    description: "The real Admin SDK returns outcome=ok with entries == () for an anonymous user — the assumption the closed classifier rests on, and the one that otherwise fails silently in production"
    requirement: CREATE-01
    verification:
      - kind: integration
        ref: "tests/e2e/test_create_user.py#TestTheRealAnonymousCompletion::test_the_real_sdk_returns_empty_provider_data_for_an_anonymous_user"
        status: pass
    human_judgment: false
  - id: D7
    description: "With no Admin credential of either kind the suite still runs green, skipping the real-anonymous cases with a reason naming both variables"
    requirement: CREATE-01
    verification:
      - kind: integration
        ref: "GOOGLE_APPLICATION_CREDENTIALS=/nonexistent/adc.json .venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py -rs -> 19 passed, 2 skipped, 0 failed"
        status: pass
    human_judgment: false
  - id: D8
    description: "The lifespan releases the process-global Firebase app registry entries it created, so a second boot in one process succeeds"
    verification:
      - kind: integration
        ref: ".venv/bin/pytest -q -m \"\" -> 1522 passed, 0 errors (was 1321 passed / 201 errors)"
        status: pass
      - kind: other
        ref: "Mutation check: removing the delete_app loop restores 21 errors across two e2e modules; reverted and verified byte-identical"
        status: pass
    human_judgment: true

# Metrics
duration: ~55 min active (wall clock spans the Task 2 checkpoint)
completed: 2026-08-23
---

# Phase 37 Plan 10: D-09's Split, Both Halves Summary

**A genuinely anonymous Firebase user now goes from no account to an account through the real Admin SDK with nothing substituted — and the empty-providerData shape every other test in the phase merely scripts is asserted against the live SDK rather than assumed.**

## Performance

- **Started:** 2026-08-23T17:20Z
- **Completed:** 2026-08-24T00:55Z
- **Duration:** ~55 min active, split across the Task 2 checkpoint (the wall-clock span includes the credential-provisioning pause)
- **Tasks:** 3
- **Files:** 5 modified, 0 created, **0 deleted**
- **Tests:** e2e 224 → 235 (+11), unit 1158 → 1160, schema 127 unchanged. Combined `-m ""`: **1522 passed, 0 failed, 0 errors.**

## Task Commits

1. **Task 1: the registered flow and the field rules** — `e2947cc` (test)
2. **Task 2: provision the credential** — checkpoint, resolved by the coordinator as ADC (see below). No commit.
3. **Task 3: the real-anonymous proof** — `58399df` (fix, the blocking lifespan defect) → `74b74c1` (test)

Task 1 is marked `tdd="true"` in the plan but is **test-only**: its subject was implemented by 37-05, 37-07, 37-08 and 37-09, so a genuinely failing-first test was not available and writing production code to manufacture one would have been theatre. The same call 37-07 Task 3 made, for the same reason. What replaced the RED gate is a **mutation check per group** — see the two `human_judgment: true` coverage entries.

## The D-08 Deviation: ADC, Not a Key

**The plan's Task 2 asked for something this project cannot produce.** Service-account key creation is blocked by the organization policy `iam.disableServiceAccountKeyCreation`, so `FIREBASE_SERVICE_ACCOUNT_JSON` cannot be populated at all — not "was not", *cannot be*. The credential is Application Default Credentials via `GOOGLE_APPLICATION_CREDENTIALS`, pointing at a `type: authorized_user` file stored outside the repo at mode 600.

This is a **change of credential source, not of the wire contract**. What D-08 exists to prevent is an ambient `[DEFAULT]` app that a call site could reach by forgetting `app=`, silently reading some other project's users (T-37-14). That property is untouched: `build_admin_apps` still constructs one **named** app per issuer with an explicit `projectId`, still creates no `[DEFAULT]` app, and selection is still an exact-match dict lookup that fails closed. Only the object handed to `initialize_app` changed — `credentials.ApplicationDefault()` instead of `credentials.Certificate(...)`.

It is also the better arrangement on its own merits, independent of the policy. Google's guidance ranks federation and ADC above key files and says keys "are a security risk if not managed correctly" — a long-lived private key on a developer's disk is a credential with no expiry and no revocation story short of rotating it everywhere. T-37-47's whole mitigation was hygiene around a key that now does not exist to be mishandled.

`projectId` remains explicitly passed, and that is load-bearing here in a way it was not before: user-scoped ADC carries **no project**, so an inferred one would be absent rather than wrong. The probe logs `No project ID could be determined` from `google.auth` on every boot — expected and harmless, because the Admin app never consults it.

Two commits landed while this plan was paused at the checkpoint and are its foundation: `3ed8f54` (three credential sources, tried in order) and `9973b77` (the `no_adc` fixture, without which the absent-credential unit cases silently stop testing the absent state on any machine that has ADC).

## The Two Halves, and Why Neither Substitutes for the Other

D-09 splits this coverage because the two halves are not interchangeable:

| | Registered (google / apple) | Anonymous |
|---|---|---|
| Can it be minted from a test? | **No** — linking a Google or Apple provider needs a real consent screen | **Yes** — `accounts:signUp` with no email and no password |
| Instrument | Substituted adapter | The real SDK, nothing substituted |
| What bounds the risk | The anonymous half proving the SDK's shape (T-37-51) | Nothing needs to — it *is* the real thing |

The plan's phrasing is exact and worth preserving: **the substituted half cannot stand in for the real half.** Every scripted `entries=()` in this module encodes an assumption about what Firebase returns. If the real SDK returned a single entry with `providerId: "anonymous"`, or `None` instead of an empty sequence, every anonymous completion in production would take the classifier's reject arm and return 403 — while the suite stayed green. That is the failure mode the real half exists to close, and it is why the shape is asserted in a **case of its own**, separate from the completion: the completion asserts a consequence, and consequences can be right for the wrong reason.

The real case carries `assert isinstance(adapter, FirebaseAdminLookup)`. Not requesting `scripted_firebase_adapter` is what makes the case real, and "deliberately did not request a fixture" is invisible in a diff — one careless argument would turn the phase's only unsubstituted proof into another scripted one.

## RESEARCH A1 — CLOSED, CONFIRMED

`returnSecureToken` is absent from the Identity Platform field list for `accounts:signUp` but present in the Firebase Auth REST reference. Measured against the live endpoint: `accounts:signUp` with `{"returnSecureToken": true}` and no `email`/`password` returns **200** with keys `['expiresIn', 'idToken', 'kind', 'localId', 'refreshToken']`. The field is honoured; the resulting user is genuinely anonymous, and the real Admin `getUser` for its `localId` returned `outcome=ok, entries=(), email=None, email_verified=False` in 0.274s.

## RESEARCH A5 — CLOSED, MEASURED, With a Finding

37-05 left A5 unmeasured for want of a live credential, and 37-07 recorded 37-10's real fixture as "the earliest detector". It is now measured — not by the ordinary fast call, which proves nothing about a timeout, but by pointing the SDK at a blackholed `FIREBASE_AUTH_EMULATOR_HOST` (`10.255.255.1:9099`, packets dropped) and timing the abort:

| `httpTimeout` | Outcome | Wall clock | Ratio |
|---|---|---|---|
| 3s | `DeadlineExceededError` | 6.01s | **2.00×** |
| 8s (production value) | `DeadlineExceededError` | 16.02s | **2.00×** |

**The answer is yes-with-a-caveat, and the caveat is the finding.** `httpTimeout` genuinely bounds `get_user` — the ratio is exactly proportional, so the option is applied. But the SDK makes **two transport attempts per `get_user` call**, so one call is bounded at **2 × httpTimeout ≈ 16s**, not the 8s §7's "fixed configured per-attempt timeout on the order of 5-10 seconds" reads like if "attempt" is taken to mean one `get_user`.

Composed with `auth/retry.py`'s 3 attempts on `retryable_failure`, a worst-case completion can spend **~48 seconds** at the provider before answering 503. Two things are already right and are worth stating so nobody re-derives them:

- `DeadlineExceededError` subclasses `exceptions.FirebaseError` (verified), so `FirebaseAdminLookup._read`'s existing arm maps it to `retryable_failure`. It fails closed; no unhandled 500 is reachable from a timeout.
- The caveat is about **latency**, not correctness.

**Not fixed here, deliberately.** Changing the timeout budget or the retry count is a policy decision about a shared value with consequences for phases 40/41/42 — deviation Rule 4 territory, not something to slip into a test plan. Recorded below as a deferred item. The measurement was taken against a blackholed endpoint rather than a genuinely slow production one; the transport is the same `requests` session either way, but the honest statement is that the *mechanism* is proven and the exact production tail is not.

## Deviations from Plan

### 1. [Rule 3 — Blocking] The lifespan leaked its Firebase apps, and the credential made it fatal

- **Found during:** Task 3's `-m ""` gate — **201 errors**, `ValueError: Firebase app named "issuer:..." already exists`.
- **Issue:** `firebase_admin` keeps its apps in a **process-global** registry, and `initialize_app` raises on a repeated name. The lifespan created one named app per boot and never deleted it. The e2e suite starts the lifespan **once per test module**, so every module after the first died in fixture setup.
- **Why it was invisible until now:** with no credential, `build_admin_apps` returned `{}` without registering anything. `3ed8f54`'s ADC support made the registration path reachable — on every developer machine with a gcloud login, and in any CI with a credential. Not caused by this plan; surfaced by it.
- **Fix:** the lifespan deletes the apps it created on shutdown. Symmetry — whoever registers a process-global handle destroys it. `firebase_apps` is now a local so shutdown can reach the same mapping.
- **Scope:** `src/nativespeaker/api/app/lifespan.py`, outside this plan's declared `files_modified`. Fixed rather than deferred because Task 3's own acceptance criterion is `.venv/bin/pytest -q -m "" exits 0`, which was unreachable otherwise.
- **Mutation-checked:** removing the loop restores 21 errors across two e2e modules.
- **Commit:** `58399df`

### 2. [Rule 1 — Bug] The plan's skip predicate would have skipped the case it exists to run

- **Acceptance criterion, verbatim:** "The fixture and the real-anonymous test skip with a reason naming `FIREBASE_SERVICE_ACCOUNT_JSON` when it is unset."
- **Issue:** that variable is unset here and will stay unset — no key is mintable. A literal implementation would have skipped the real-anonymous proof on the very machine that can run it, and reported green. This is the `acceptance_criteria_caveat` pattern the coordinator flagged: a criterion invalidated by a change landing mid-plan.
- **Resolution — intent, not letter:** `_admin_credential_configured` calls the **same two source probes `build_admin_apps` calls, in the same order** — `config.firebase.credential_dict()` then `_application_default_credential()` — rather than re-reading `os.environ`. A predicate that can disagree with the thing it predicts is worse than no predicate. The skip **reason names both variables**, so the criterion's actual purpose (a contributor without a credential learns what to set) is served better than the literal form would have served it.
- **Verified:** `GOOGLE_APPLICATION_CREDENTIALS=/nonexistent/adc.json .venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py -rs` → **19 passed, 2 skipped**, reason naming both variables.

### 3. [Rule 1 — Bug] `_identity_and_user` hardcoded the stub issuer

- **Found during:** Task 3's first run — the real-anonymous completion returned **200** and the case still failed with `NoResultFound`.
- **Issue:** the helper filtered on `TEST_ISSUER` (the stub verifier's `.../test-project`). The real case's rows carry the **live project's** issuer, so the query matched nothing and reported a successful creation as "no account was created". A defect in the assertion, not in the product — and the dangerous direction, since the inverse (a helper that over-matches) would have passed silently.
- **Fix:** `issuer` is a parameter defaulting to `TEST_ISSUER`; the real case passes `_app_config.jwt.issuer`. The docstring records what the default hid.
- **Commit:** `74b74c1`

### 4. [Rule 2 — Missing] `.env.example` documented a variable the code stopped reading

- `.env.example` carried `FIREBASE_API_KEY`, but the config reads **`JWT_API_KEY`** — a rename a prior quick-plan made and explicitly left as an outstanding follow-up ("`.env.example` still references `FIREBASE_API_KEY`"). A contributor copying the example would set a key that is silently ignored as an extra, then watch every e2e Firebase fixture fail on an empty API key.
- Renamed to `JWT_API_KEY`, added the missing `JWT_PROJECT_ID`, and documented `GOOGLE_APPLICATION_CREDENTIALS` beside the key placeholder as an equally valid route with the org-policy reason. `.env.example` carries **placeholders only**; no real value.
- Checked first that nothing depends on the old spelling: `tests/unit/test_config.py:273` *uses* `FIREBASE_API_KEY` as its example of an ignored extra key, which is unaffected.

### 5. [Rule 2 — Missing] A stale comment in `lifespan.py` asserted the opposite of the new behaviour

The Phase 37 amendment note claimed the adapter is built "never as an ambient startup client **or from Application Default Credentials**". True when written, false since `3ed8f54`. Rewritten to state what is actually invariant (named per-issuer app, explicit `projectId`, no `[DEFAULT]`) and to record that the credential source may now be ADC, with the reason. Comments that contradict the code are how the next reader gets misled into "fixing" the code.

### 6. Scope note — five email cases, not three

The plan asks for three (verified+non-empty, unverified+non-empty, empty+verified). Two more are free and cover the same rule's edges: whitespace-only (the `.strip()` in `email_to_persist` is a non-empty **test**, not a transform) and absent (`email=None`). All three named cases are present.

### 7. Scope note — the global invariants were added to the four pre-existing completion cases

"Every case asserts 0 `access_grants` / 0 `user_monthly_usage`" and "every case asserts `display_name IS NULL`" are read as *every case that drives a completion* — the tracer's, 37-08's three, and this plan's six. Prepare-only cases mutate no business state and are excluded. The assertions are global rather than per-user on purpose: a per-user check answers "this account got no grant", the global one answers "this request created no entitlement **anywhere**", which is the invariant §02 actually states.

### Not encountered

- **No architectural decision (Rule 4) was needed**, with one thing deliberately left at its edge: the A5 latency finding, which is a policy change to a shared budget and is deferred rather than slipped in.
- **The `ADAPTER_IMPLEMENTORS` docstring scan never fired.** The one `src/` file this plan touched (`lifespan.py`) names no adapter method in code or prose; `tests/unit/test_adapter_interfaces.py` passes.
- **The D-16 guard never fired.** `StorePurchaseToken` / `PurchaseProvider` throughout; no `subscription_*` Python name appears.

## Known Stubs

**None.** No stub, no placeholder, no TODO, and no skipped test was introduced. The two real-anonymous cases skip **conditionally**, on a credential the environment either has or does not, with a reason naming what to set — that is a guarded environmental dependency, not a disabled test, and it runs green here.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: latency-budget | `src/nativespeaker/api/auth/firebase.py` | Measured: one `get_user` costs up to **2 × `httpTimeout`** (16s at the configured 8s) because the SDK retries the transport once. Composed with `auth/retry.py`'s 3 attempts, a worst-case completion holds ~48s before its 503. Fails closed throughout (`DeadlineExceededError` → `FirebaseError` → `retryable_failure`), so this is a **latency** exposure, not a correctness one — a slow-loris-ish resource cost on the completion path. Not changed here: the budget is shared with phases 40/41/42. |

Every `mitigate` disposition in the plan's register has a passing assertion or a recorded resolution:

| Threat | Status |
|---|---|
| T-37-47 (key committed or left on disk) | **Dissolved rather than mitigated** — no key exists to leak. ADC file lives outside the repo at mode 600; `.env` is gitignored (`.gitignore:9`); `.env.example` carries placeholders only. No real key material was echoed, logged, or committed at any point. |
| T-37-48 (Admin credential for the wrong project) | Verified live: the app builds against `native-speaker-488021`, which is what `JWT_PROJECT_ID` names, and the real-anonymous case asserts `identity.issuer == _app_config.jwt.issuer` on the created row. |
| T-37-49 (a green completion test that never asserts a 200) | Closed from both sides. The real case asserts `entries == ()` **and** a 200; 37-08 separately asserts the `password` shape yields 403. The success test cannot be silently testing the rejection arm. |
| T-37-50 (anonymous users accumulating) | **Accepted, unchanged.** No `delete_user` teardown — the user did not ask for the teardown variant. Two permanent anonymous users per full e2e run, plus one from the A1 probe. |
| T-37-51 (the fake drifting from the real SDK) | **Accepted and now bounded** for the anonymous shape, which is asserted against the live SDK. Google/apple remain scripted and unbounded, exactly as 37-CONTEXT.md § Deferred Ideas records. |
| T-37-SC (package installs) | No install in this plan. |

## Verification Commands Run

| Command | Result |
|---|---|
| `.venv/bin/pytest -q -m ""` | **1522 passed**, 0 failed, 0 errors |
| `.venv/bin/pytest -q` | 1160 passed, 362 deselected |
| `.venv/bin/pytest -q -m e2e` | 235 passed (baseline 224) |
| `.venv/bin/pytest -q -m schema` | 127 passed |
| `.venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py` | 21 passed (baseline 10) |
| `GOOGLE_APPLICATION_CREDENTIALS=/nonexistent .venv/bin/pytest -q -m e2e tests/e2e/test_create_user.py -rs` | 19 passed, **2 skipped**, reason names both variables |
| `.venv/bin/ruff check src/ tests/` | All checks passed |
| Mutation: perturb the reserved `provider_uid` | both reservation cases red → reverted, byte-identical |
| Mutation: delete `email_verified` guard in `classifier.py` | `non-empty-but-unverified` red → reverted, byte-identical |
| Mutation: delete the `delete_app` loop in `lifespan.py` | 21 errors across two modules → reverted, byte-identical |
| `git show --stat e2947cc` | `tests/e2e/test_create_user.py` only — Task 1 touched no `src/` |
| `git diff --diff-filter=D --name-only 1a63da1..HEAD` | empty — no file deleted |

## Deferred Items

1. **The A5 latency composition** (~48s worst case at the provider). A policy decision on a shared budget — candidates are lowering `httpTimeout`, lowering the retry count, or bounding the whole `lookup_with_retry` call in wall clock. Belongs with phases 40/41/42, which share the seam.
2. **`.planning/todos/pending/secret-manager-integration.md`** now covers a smaller surface: the ADC file and the HMAC keys, no service-account key.
3. **Real Google/Apple e2e accounts** remain rejected as unreproducible shared CI state (37-CONTEXT.md § Deferred Ideas), to revisit if T-37-51's drift ever appears.

## Next Phase Readiness

- **Phase 37 is complete.** All ten plans executed; `37-VALIDATION.md` has `wave_0_complete: true` and a populated per-task map. `status: draft` / `nyquist_compliant: false` are left for `/gsd:validate-phase`.
- **Phases 40/41/42** reuse `classify_provider_data`, `email_to_persist`, the adapter seam and all five `Depends()` accessors unchanged. They inherit the A5 latency composition above — read it before setting their own budgets.
- **Phase 46** (sign-out-all) adds the revocation adapter method and must widen `ADAPTER_IMPLEMENTORS` deliberately; the lifespan's app teardown is now in place for it to reuse.

## Self-Check: PASSED

- Modified files exist: `tests/e2e/test_create_user.py`, `tests/e2e/conftest.py`, `.env.example`, `src/nativespeaker/api/app/lifespan.py`, `37-VALIDATION.md`.
- All three commits present in `git log 1a63da1..HEAD`: `e2947cc`, `58399df`, `74b74c1`.
- `git diff --diff-filter=D --name-only 1a63da1..HEAD` → empty. No file deleted by this plan.
- Branch verified `gsd/phase-37-post-auth-create-user` before every commit.
- No real key material appears in any committed file; credential presence was tested, never printed.

---
*Phase: 37-post-auth-create-user*
*Completed: 2026-08-23*
