---
phase: 40-post-auth-upgrade-anonymous
plan: 03
subsystem: testing
tags: [e2e, firebase, oauth, identity-toolkit, pytest-fixture, credentials]

requires:
  - phase: 37-post-auth-create-user
    provides: "`anonymous_firebase_credential`, the Identity Toolkit REST fixture shape this one mirrors, and `FirebaseAdminLookup` as the production read seam"
  - phase: 40-01
    provides: "the four-label `core.auth_operation` the endpoint plans build against (not read by this plan)"
provides:
  - "`google_linked_firebase_credential` — a per-run Firebase session whose real providerData carries exactly one `google.com` entry, built by exchange-and-link with no signing credential"
  - "`tests/e2e/test_upgrade_anonymous.py` — the endpoint's e2e home, opening with the credential canary plans 40-04, 40-05 and 40-07 extend"
  - "the three `FIREBASE_TEST_GOOGLE_*` variables documented in `.env.example` with the by-hand consent procedure and the revocation route"
  - "the observed call surface of exchange, sign-up, link, Admin read and Admin delete against firebase-admin 7.3.0"
affects: [40-04, 40-05, 40-07]

actuals:
  tokens: 5100
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "A real third-party session is obtained by exchange-and-link, never by minting: one by-hand consent yields a refresh token, and each run redeems it, links it onto a throwaway anonymous user, and deletes that user"
    - "A shared single-holder external resource gets a recovery preamble, not just a teardown: find the leftover holder by its provider uid and delete it before creating a new one, so an interrupted run cannot poison the next"
    - "A credential fixture that must never skip states that structurally — subscripted `os.environ` reads and no guard — so absence is a KeyError at the reading line rather than a green run proving nothing"
    - "A teardown contract is asserted by an autouse module fixture whose finalizer runs after the fixture under test, since autouse fixtures are set up first and therefore torn down last"

key-files:
  created:
    - tests/e2e/test_upgrade_anonymous.py
  modified:
    - .env.example
    - tests/e2e/conftest.py

key-decisions:
  - "The `google_linked_firebase_credential` fixture reaches the Admin app through `firebase_admin.get_app(name=f\"issuer:{issuer}\")` rather than building a second app, so no credential of any kind is passed anywhere in the test layer"
  - "The Google ID token's `sub` is decoded with `verify_signature=False`: the claim is used only to find a leftover Firebase user, and Firebase itself verifies the token during the link call"
  - "The teardown-contract case is a real test node that asserts the user is present now and records its local id; the not-found read runs in an autouse module fixture's finalizer, which is the only point in the module that is after the credential's teardown"
  - "One comment line was reworded so `grep -c` over the three variable names in `.env.example` returns exactly 3 as the acceptance criterion states, rather than 4"

patterns-established:
  - "Task 1's probe-then-build shape: execute every call once against the live service, record the exact names and response keys, and let no downstream line assert a name that was not observed"

requirements-completed: []

coverage:
  - id: D1
    description: "A test run obtains a Firebase session whose real providerData carries exactly one `google.com` entry, with no signing credential anywhere"
    requirement: "UPGRADE-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py::TestTheGoogleLinkedCredential::test_the_linked_user_reports_exactly_one_google_provider_entry"
        status: pass
      - kind: command
        ref: "grep -rn \"create_custom_token\\|serviceAccountId\" src tests  # returns nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "The read that proves the shape ran through the production lookup class, so a substituted fake cannot satisfy it"
    requirement: "UPGRADE-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py::TestTheGoogleLinkedCredential::test_the_read_ran_through_the_production_lookup"
        status: pass
    human_judgment: false
  - id: D3
    description: "Teardown deletes the Firebase user, so the Google account is free to be linked again on the next run"
    requirement: "UPGRADE-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py::TestTheGoogleLinkedCredential::test_the_firebase_user_is_deleted_when_the_module_tears_down plus the _google_user_deleted_after_teardown finalizer"
        status: pass
      - kind: command
        ref: "an independent post-run Admin read for lXyPGKRxUFPtPFSXNO1yaHya19f2 raised firebase_admin._auth_utils.UserNotFoundError"
        status: pass
    human_judgment: false
  - id: D4
    description: "An absent credential fails the run; it never skips"
    requirement: "UPGRADE-01"
    verification:
      - kind: command
        ref: "GSD_UNSET_REFRESH=1 ... uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q -> `1 passed, 5 warnings, 2 errors`, zero skipped, cause `KeyError: 'FIREBASE_TEST_GOOGLE_REFRESH_TOKEN'`"
        status: pass
    human_judgment: false
  - id: D5
    description: "The three variables, the by-hand consent procedure and the revocation route are written down"
    requirement: "UPGRADE-01"
    verification:
      - kind: command
        ref: "grep -c on the three names -> 3; grep -in \"offline\\|openid\" -> 2 lines; grep -in \"revok\" -> 1 line; git diff --stat -> 30 insertions, 0 deletions"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-09-02
status: complete
---

# Phase 40 Plan 03: The Google-Linked Firebase Session Summary

**A per-run Firebase session whose real `providerData` carries exactly one `google.com` entry, built by redeeming a stored Google refresh token and linking it onto a throwaway anonymous user — no service-account key, no signer, and nothing minted by this project.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-09-02T13:00Z
- **Tasks:** 3 (Task 1 produced knowledge only and has no commit)
- **Files:** 1 created, 2 modified

## Accomplishments

- Every call the fixture makes was executed once by hand against the live project before a line of it was written, and the surface recorded below. Nothing downstream asserts a method name, parameter name or response key that Task 1 did not observe.
- `.env.example` gained the three `FIREBASE_TEST_GOOGLE_*` variables under their own heading, with the one-off consent procedure (offline access plus the `openid` scope), the Firebase Google-provider requirement for the client id, the revocation route, and the explicit statement that absence is a broken environment rather than a supported skip.
- `google_linked_firebase_credential` yields `(id_token, local_id)` — the same pair shape `anonymous_firebase_credential` yields, so a test can swap one for the other. It carries a recovery preamble that releases the Google account from any user a previous run left behind.
- `tests/e2e/test_upgrade_anonymous.py` opened with three cases: the exact one-element `google.com` comparison, the control that the adapter really is `FirebaseAdminLookup`, and the teardown contract. Plans 40-04, 40-05 and 40-07 add the endpoint's own cases below them.

## Task Commits

1. **Task 1: Establish the exchange, link and teardown surface by execution** — no commit. Its deliverable is the record below; the working tree was left unchanged and the probe's Firebase user was deleted.
2. **Task 2: Document the three variables and the by-hand consent** — `76d2381` (docs)
3. **Task 3: The per-run linked-session fixture and its canary** (TDD)
   - `056c876` (test) — RED
   - `9778ca9` (feat) — GREEN
   - No refactor commit: the fixture landed in the shape `anonymous_firebase_credential` already uses, with nothing to clean up.

## Task 1: the observed call surface

Every row below was produced by one throwaway script run under `uv run python`, against the live `native-speaker-488021` project and the installed `firebase-admin 7.3.0` / Python 3.14.7. The script was deleted afterwards; the Firebase user it created (`LoDGXjKZTHVVsG2R092OouGgGir2`) was deleted by its own step 5.

| Step | Exact call | Observed answer |
|---|---|---|
| 1. Redeem the refresh token | `httpx.post("https://oauth2.googleapis.com/token", data={"client_id", "client_secret", "refresh_token", "grant_type": "refresh_token"})` | HTTP 200. Keys `['access_token', 'expires_in', 'id_token', 'scope', 'token_type']`. `id_token` **present**. Granted scope: `.../auth/userinfo.profile openid .../auth/userinfo.email` |
| 2. Read the Google subject | `jwt.decode(id_token, options={"verify_signature": False})` (PyJWT, already installed) | Claim keys `['at_hash', 'aud', 'azp', 'email', 'email_verified', 'exp', 'iat', 'iss', 'sub']`. The subject claim is **`sub`** — a 21-character all-digit string |
| 3. Create the anonymous user | `httpx.post(".../v1/accounts:signUp?key={api_key}", json={"returnSecureToken": True})` | HTTP 200. Keys `['expiresIn', 'idToken', 'kind', 'localId', 'refreshToken']` |
| 4. Link the Google credential | `httpx.post(".../v1/accounts:signInWithIdp?key={api_key}", json={"postBody": "id_token=<google>&providerId=google.com", "requestUri": "http://localhost", "returnSecureToken": True, "idToken": <anon>})` | HTTP 200. Keys `['email', 'emailVerified', 'expiresIn', 'federatedId', 'idToken', 'kind', 'localId', 'oauthIdToken', 'providerId', 'rawUserInfo', 'refreshToken']`. `providerId` is `google.com` |
| 5a. Reach the Admin app | `firebase_admin.get_app(name=f"issuer:{issuer}")`, signature `(name='[DEFAULT]')` | Returns **the same object** the lifespan's `build_admin_apps` put under that issuer key (`is` comparison true) |
| 5b. Read the linked user | `auth.get_user(local_id, app=app)` | `provider_data` is a **one-element** sequence: `[('google.com', uid present)]` |
| 5c. Read through the production seam | `FirebaseAdminLookup(apps).get_user_provider_data(issuer, local_id)` | `IdentityProvider.google`, `provider_uid` non-empty, `email` non-None |
| 5d. Find a user by its Google provider uid | `auth.ProviderIdentifier(provider_id, provider_uid)` — signature `(self, provider_id, provider_uid)`; passed to `auth.get_users(identifiers, app=None)` | Returns `GetUsersResult`; `.users` held exactly `['LoDGXjKZTHVVsG2R092OouGgGir2']`, `.not_found` was empty |
| 5e. Delete | `auth.delete_user(uid, app=None)` — signature `(uid, app=None)` | After it, `auth.get_user` raised `firebase_admin._auth_utils.UserNotFoundError`, and the provider lookup returned `users: 0, not_found: 1` |

**Steps 3 and 4 returned the same Firebase local id** (`LoDGXjKZTHVVsG2R092OouGgGir2`, compared as `step4["localId"] == step3["localId"] -> True`). That is the whole point of linking rather than signing in: no second Firebase user appears, and the anonymous user this phase's endpoint flips is the same row that ends up carrying the Google entry.

### Contradictions with the written record

- **`40-CONTEXT.md` D-18 as originally decided is contradicted, and knowingly so.** Its text says each run "mints a custom token for that UID through the Admin SDK" and names `firebase_admin.auth.create_custom_token`. Nothing of the kind happens here: no custom token is minted, and `create_custom_token` appears nowhere in `src` or `tests`. D-18 already carries a dated 2026-09-02 note recording that its mechanism was reversed at planning time, so this is the planned reversal landing, not a new divergence. D-18's *purpose* — a genuine `google.com` `providerData` response — is met exactly.
- **D-18 also says the Firebase side is "read-only for this test" and the account is "fixed test data rather than shared mutable state".** That is no longer true of the shipped mechanism. Each run creates and deletes a Firebase user, and the Google account can hold only one Firebase link at a time, which is precisely why the fixture needs the recovery preamble (T-40-03-03). The next reader should take the mechanism from this summary, not from D-18's body.
- **No contradiction with `40-RESEARCH.md`** was found: its Q1 already describes exchange-and-link, and its "Package Legitimacy Audit -> Not applicable" holds — this plan installed nothing and did not touch `pyproject.toml`.
- One small thing the plan did not predict: the link response carries `email`, `emailVerified`, `federatedId`, `oauthIdToken` and `rawUserInfo` in addition to the token pair. Nothing reads them; they are recorded so a future reader does not mistake their presence for a shape change.

## Task 3: the RED, recorded verbatim

`uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q` before the fixture existed:

```
ERROR tests/e2e/test_upgrade_anonymous.py::TestTheGoogleLinkedCredential::test_the_linked_user_reports_exactly_one_google_provider_entry
ERROR tests/e2e/test_upgrade_anonymous.py::TestTheGoogleLinkedCredential::test_the_firebase_user_is_deleted_when_the_module_tears_down
=================== 1 passed, 5 warnings, 2 errors in 0.56s ====================
```

with the cause `fixture 'google_linked_firebase_credential' not found`. The one passing case is `test_the_read_ran_through_the_production_lookup`, which asserts only on the adapter the lifespan installed and correctly does not need the credential.

## The no-skip proof

The plan requires that an absent credential *fails* rather than skips, and that the absence of a skip be measured rather than asserted. `pytest-dotenv` loads `.env` at initial-conftest time, so simply clearing the shell variable proves nothing. The variable was therefore removed from `os.environ` in a throwaway `-p` plugin's `pytest_configure`, which runs after that load:

```
GSD_UNSET_REFRESH=1 PYTHONPATH=/tmp uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q -s -p gsdprobe_plugin
```

Summary line:

```
=================== 1 passed, 5 warnings, 2 errors in 0.45s ====================
```

**Zero skipped**, and the cause is `KeyError: 'FIREBASE_TEST_GOOGLE_REFRESH_TOKEN'` — raised at the subscripted read in `_google_id_token`, which is where the fixture states its refusal to tolerate a missing variable. The plugin was deleted after the run.

## The local id this run created, and its post-teardown read

The verification run's fixture created Firebase user **`lXyPGKRxUFPtPFSXNO1yaHya19f2`**. Two independent confirmations that it is gone:

1. The module's `_google_user_deleted_after_teardown` finalizer performed `auth.get_user(local_id, app=admin_app)` inside `pytest.raises(auth.UserNotFoundError)` after the credential fixture was torn down. The run reported `3 passed` with no teardown error, so the not-found outcome held.
2. A separate process, run after pytest exited, read the same local id through a freshly built Admin app: `POST-TEARDOWN READ: lXyPGKRxUFPtPFSXNO1yaHya19f2 -> UserNotFoundError (deleted)`.

## Files Created/Modified

- `.env.example` — a new `# --- The Google-linked session the upgrade e2e cases need ---` block between the existing test-account pair and the Admin-credential block: the three variables, the consent procedure, the scope requirement, the Firebase-provider requirement, the revocation route, and the no-skip statement. 30 insertions, 0 deletions.
- `tests/e2e/conftest.py` — `firebase_admin`, `jwt as pyjwt` and `firebase_admin.auth` imports; the module-level helpers `_google_id_token` and `_release_google_account`; and the module-scoped `google_linked_firebase_credential` fixture, placed immediately above `_app_lifespan`.
- `tests/e2e/test_upgrade_anonymous.py` — new. The `e2e` module marker, the `_google_user_deleted_after_teardown` autouse module fixture, and `TestTheGoogleLinkedCredential` with its three cases.

## Decisions Made

- **The Admin app is reached, never built.** `firebase_admin.get_app(name=f"issuer:{issuer}")` returns the very object `build_admin_apps` created — confirmed by identity comparison in Task 1. Building a second app in the test layer would have meant handing it a credential, which is exactly what T-40-03-02 forbids. `build_admin_apps` and `_application_default_credential` were not touched.
- **The Google `sub` is read unverified.** The claim is used for one thing: finding a Firebase user that a previous run left holding the account. Firebase verifies the token itself during `accounts:signInWithIdp`, so a second verification here would add a JWKS dependency to the test layer and prove nothing the link call does not already prove.
- **The teardown contract needed a finalizer, not just a test.** Nothing inside a module runs after that module's fixtures are torn down, so a plain test cannot observe the post-teardown state. An autouse module-scoped fixture is set up before the non-autouse credential fixture and therefore finalized after it, which is the one place the read can happen. The test node that pairs with it asserts the user is present *now* and records the local id; a failure in the finalizer surfaces as a teardown ERROR, so the guarantee cannot quietly lapse.
- **One `.env.example` comment was reworded.** The revocation paragraph originally opened with the variable name, which made the acceptance criterion's `grep -c` return 4 rather than the stated 3. The sentence now reads "The refresh token below is the one real, long-lived secret in this block." — same meaning, and the criterion is checkable as written.
- **`requirements-completed` is empty.** This plan delivers a test credential and a canary; no endpoint exists yet. UPGRADE-01 is completed by the plan that ships the route.

## Deviations from Plan

**None on the code.** All three `files_modified` were changed and nothing else was. Task 1 produced no commit, exactly as its own instruction required ("leave the working tree unchanged apart from the summary").

Two mechanical notes, neither a change of substance:

- **[Rule 3 - Blocking] `.env` had to be copied into the worktree.** It is gitignored, so the parallel worktree was created without it, and neither the probe nor `tests/e2e` can reach Google, Firebase or PostgreSQL without it. Copied from the main checkout as the dispatch directed. It was never staged and never committed — `git status --short` is empty at every commit and `.gitignore:9` lists it.
- **The `-p` plugin used for the no-skip proof and the local-id capture lived in `/tmp`,** outside the repository, and was deleted after use. Nothing about the verification is reproducible from the repository alone, which is why both commands and both summary lines are quoted above in full.

## Issues Encountered

None blocking. The one-off consent had already been performed with the `openid` scope, so Task 1 step 1's blocked-precondition branch — "the developer must redo the consent" — did not apply.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q` | 3 passed, **0 skipped** |
| the same command with `FIREBASE_TEST_GOOGLE_REFRESH_TOKEN` unset | 1 passed, 2 errors, **0 skipped** — `KeyError` on the variable |
| `uv run pytest -q` | 819 passed, 326 deselected |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed — the new file measures zero |
| `uv run ruff check src tests` | All checks passed! |
| `git status --porcelain src/` | empty — no production source file touched |
| `grep -rn "create_custom_token\|serviceAccountId" src tests` | nothing |
| `grep -c` the three variable names in `.env.example` | 3 |
| `grep -in "offline\|openid" .env.example` | 2 lines |
| `grep -in "revok" .env.example` | 1 line |
| `git diff --stat .env.example` (pre-commit) | 30 insertions(+), 0 deletions |
| `grep -rnE "1//[A-Za-z0-9_-]{20,}" .env.example` | nothing — no real token pasted in |

## Known Stubs

None.

## Threat Flags

None new. The register's five entries are addressed as written:

- **T-40-03-01 (refresh-token disclosure).** The token lives only in the gitignored `.env`. `.env.example` carries the name and a `...` placeholder; the token-shaped grep over it returns nothing; no probe, script or test printed the value; and the revocation route is written into `.env.example`.
- **T-40-03-02 (signing credentials).** None introduced. The repository-wide grep returns nothing, `build_admin_apps` is untouched, and the test layer reaches the existing Admin app by name rather than constructing one.
- **T-40-03-03 (blocking the shared Firebase project).** `_release_google_account` deletes any leftover holder found by `auth.ProviderIdentifier("google.com", sub)` *before* the new user is created, so the free-again guarantee does not depend on a clean exit. Teardown deletes this run's user as well.
- **T-40-03-04 (coverage honesty).** Measured, not asserted — see "The no-skip proof".
- **T-40-03-SC (package installs).** Nothing installed; `pyproject.toml` untouched.

## Self-Check: PASSED

- `.planning/phases/40-post-auth-upgrade-anonymous/40-03-SUMMARY.md` — FOUND
- `.env.example`, `tests/e2e/conftest.py`, `tests/e2e/test_upgrade_anonymous.py` — all FOUND
- Commits `76d2381`, `056c876`, `9778ca9` — all FOUND in `git log`
- `.env` present in the worktree, gitignored, and absent from every commit; working tree clean before this summary was written
