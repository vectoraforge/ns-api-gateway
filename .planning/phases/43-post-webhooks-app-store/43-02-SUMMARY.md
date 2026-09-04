---
phase: 43-post-webhooks-app-store
plan: 02
subsystem: infra
tags: [envoy-gateway, httproute, helm, app-store, pydantic-settings, deployment]

# Dependency graph
requires:
  - phase: 43-post-webhooks-app-store
    provides: "plan 43-01's registered route literal `/webhooks/app-store` and `AppStoreConfig` in `config.py`"
  - phase: 35-foundation
    provides: "D-05 and D-08 — the v2.1 gateway contract owns every gateway limit, so no limiter is added here"
provides:
  - "The gateway rule matches the same literal the application registers: `POST /webhooks/app-store`, Exact"
  - "The `.env.example` App Store block: the three deployer variables, where each comes from, and the unconfigured behaviour"
  - "A written ground, in the template itself, for why this one route carries no JWT `SecurityPolicy`"
affects: [43-06, 44-webhook-google-play-rtdn]

actuals:
  tokens: 611
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A credential-free gateway rule carries a one-line comment naming why it is outside the JWT SecurityPolicy"

key-files:
  created: []
  modified:
    - k8s/templates/httproute-webhooks.yaml
    - .env.example

key-decisions:
  - "The `.env.example` block names no variable in its prose, only on the three assignment lines: the plan's own verification counts matching LINES, so a variable named twice would fail its own gate."
  - "`APP_STORE_ROOT_CERTIFICATE_PATH` is not named anywhere in `.env.example`, not even in a comment. The block states the default path instead, so a reader learns why no path variable is listed without learning a variable name they should not set."
  - "The three placeholders are `...`, matching the DeviceCheck block. A copied-through `...` fails config load loudly with a message naming `sandbox` and `production`, which is verified below, so the placeholder cannot become a silently wrong environment."
  - "APPLEHOOK-01 is NOT marked complete by this plan — see Deviations, and 43-01's departure 4, which this follows."

patterns-established:
  - "A deployment-surface plan verifies its own claims against the running config loader, not against the plan text: the three documented names, the stated default and the stated no-default were each read back off `EnvironmentConfig`"

requirements-completed: []

coverage:
  - id: D1
    description: "The gateway path literal and the FastAPI route literal are the same string, so Apple's POST reaches the handler rather than a 404 it retries five times and abandons"
    requirement: APPLEHOOK-01
    verification:
      - kind: other
        ref: "grep -n 'value: /webhooks' k8s/templates/httproute-webhooks.yaml == grep -n 'router.post' src/nativespeaker/api/routers/webhooks.py — both `/webhooks/app-store`"
        status: pass
      - kind: other
        ref: "grep -rn '/webhooks/apple' k8s/ — no output; the old literal is gone from the whole tree"
        status: pass
    human_judgment: false
  - id: D2
    description: "The rule is still one Exact POST match with no rate-limit entry and no filter chain, and the route is still absent from the JWT `SecurityPolicy` targetRefs"
    requirement: APPLEHOOK-02
    verification:
      - kind: other
        ref: "grep -c 'type: Exact' == 1; grep -vE '^\\s*#' ... | grep -ciE 'rateLimit|BackendTrafficPolicy|filters:' == 0"
        status: pass
      - kind: other
        ref: "git status --porcelain -- k8s/templates/security-policy.yaml — empty; git diff --stat -- k8s/ names exactly one file"
        status: pass
    human_judgment: false
  - id: D3
    description: "`.env.example` documents the three App Store variables with placeholders, where each comes from, why they stay out of the tracked YAML, and what an unconfigured deployment does"
    requirement: APPLEHOOK-01
    verification:
      - kind: other
        ref: "grep -c 'APP_STORE_BUNDLE_ID\\|APP_STORE_APP_APPLE_ID\\|APP_STORE_ENVIRONMENT' .env.example == 3; APP_STORE_ROOT_CERTIFICATE_PATH on non-comment lines == 0; verification_temporarily_unavailable present"
        status: pass
      - kind: other
        ref: "EnvironmentConfig() with the three documented names set — bundle_id, app_apple_id (int) and environment (StoreEnvironment.production) all land; root_certificate_path is the documented default"
        status: pass
    human_judgment: false
  - id: D4
    description: "Apple actually posts to the documented URL: the Production and Sandbox Server URLs are set in App Store Connect and a test notification returns one 200"
    requirement: APPLEHOOK-01
    verification: []
    human_judgment: true
    rationale: "The dashboard fields can only be set by a person with App Store Connect access, against a deployed gateway. The plan's `user_setup` block owns this step and this plan documents it; there is no iOS app and no App Store Connect record yet, so nothing was set."

duration: 4min
completed: 2026-09-04
status: complete
---

# Phase 43 Plan 02: The Deployment Surface Matches the Route — Summary

**The Envoy gateway now matches the exact literal the FastAPI router registers, `POST /webhooks/app-store`, and `.env.example` tells a deployer the three values to set, where to read each one, why they stay out of the tracked YAML, and what the service does until they are set.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-04T22:12:36Z
- **Completed:** 2026-09-04T22:16:26Z
- **Tasks:** 2 of 2
- **Files modified:** 2 (0 created, 2 modified)

## Accomplishments

- **The two literals are now one string.** `k8s/templates/httproute-webhooks.yaml:16` reads `/webhooks/app-store` and `src/nativespeaker/api/routers/webhooks.py:17` reads `/webhooks/app-store`. Before this plan the gateway matched `/webhooks/apple`, so every Apple delivery would have been a 404 that Apple retries five times and then abandons. Nothing anywhere in the repository names the old path any more.
- **The rule did not grow.** One `Exact` match, one `POST`, one backend. No rate-limit entry, no `BackendTrafficPolicy` reference and no filter chain were added, and `k8s/templates/security-policy.yaml` was not touched, so the route stays outside the JWT `SecurityPolicy` by the same absence that already made it credential-free.
- **The template now says why it is credential-free.** One line above `rules:` states that the route is outside the JWT `SecurityPolicy` and that Apple sends no Authorization header. Without it the absence reads as an oversight to the next person who edits this file.
- **`.env.example` carries an App Store block in the DeviceCheck block's shape** — 26 lines naming where the bundle id and the numeric Apple id are read, that the environment has no default and why, that the three values are public but still stay out of `config/config.yaml`, that the root certificate defaults to the committed file, and that an unconfigured deployment boots, logs one warning and answers 503.
- **Every claim in that block was read back off the real config loader,** not asserted from the plan text. See Verification.

## Task Commits

1. **Task 1: The gateway route serves the path the application registers** — `0d63665` (fix)
2. **Task 2: A deployer can find out what to set** — `cb36a59` (docs)

## Files Created/Modified

**Modified**

- `k8s/templates/httproute-webhooks.yaml` — the path literal `/webhooks/apple` → `/webhooks/app-store`, plus one comment line naming why the route is outside the JWT `SecurityPolicy`. Two insertions, one deletion.
- `.env.example` — the App Store Server Notification block, appended after the DeviceCheck block: `APP_STORE_BUNDLE_ID`, `APP_STORE_APP_APPLE_ID`, `APP_STORE_ENVIRONMENT`, each `...`, under prose carrying the four facts the plan names. 26 insertions.

## Decisions Made

1. **The prose names no variable; only the three assignment lines do.** The plan's own verification is `grep -c 'APP_STORE_BUNDLE_ID\|APP_STORE_APP_APPLE_ID\|APP_STORE_ENVIRONMENT' == 3`, and `grep -c` counts matching *lines*. A comment that helpfully repeated a variable name would have made the count 4 and failed the gate. The prose therefore speaks of "the environment" and "the bundle id" and lets the assignment lines carry the names.

2. **`APP_STORE_ROOT_CERTIFICATE_PATH` is not written anywhere in the file.** The plan forbids it only on non-comment lines, so a comment naming it would have passed. It is still omitted: the block's purpose is to list what a deployer sets, and naming a variable while saying not to set it invites exactly the edit the omission is meant to prevent. The line states the default path instead, which is what a reader actually needs to know.

3. **The placeholders are `...`, matching the DeviceCheck block, and this is safe.** A `...` copied through into a real `.env` fails config load with `Input should be 'sandbox' or 'production'` — measured, below. The placeholder cannot degrade into a wrong environment silently, which is the failure mode the no-default rule exists to prevent.

4. **The comment in the Helm template is one line.** `AGENTS.md` says comments are for resolving a genuine ambiguity and never explain a decision made elsewhere. A rule that alone among four routes carries no credential requirement is a genuine ambiguity in this file, so the line is earned; it is kept to one sentence pair and states no design.

## Deviations from Plan

### Auto-fixed Issues

None. Both tasks executed exactly as written.

### Departures from the plan's letter, taken deliberately

**1. `requirements.mark-complete` was NOT run for APPLEHOOK-01.** The plan declares `requirements: [APPLEHOOK-01]`, and all six plans in phase 43 declare it. Checking that box after plan 2 of 6 would assert that "the endpoint ingests Apple App Store Server Notifications outside the auth dependency" is finished, when the store purchase row (43-03), the entitlement grant (43-04) and the two-connection race proof (43-05) are all still owed under it — and this plan renamed a path and wrote documentation. 43-CONTEXT.md D-26 gives 43-06 the dated REQUIREMENTS.md amendments and 43-01 left both boxes open for the same reason. `requirements-completed` above is empty to match. REQUIREMENTS.md is therefore unchanged by this plan.

**2. Task 2's `<precondition>` is prose, not a runnable check.** It states that the three values come from App Store Connect and that this task documents rather than obtains them. That is a scope statement about the task, and it is satisfied by construction: no value was obtained and every committed value is a placeholder. No checkpoint was raised.

---

**Total deviations:** 0 auto-fixed, 2 recorded departures.
**Impact on plan:** None. Both files are exactly the two in `files_modified`, and no third file was touched.

## Verification

Every automated check in the plan, run at completion:

| Check | Expected | Actual |
|---|---|---|
| `grep -rhvE '^\s*#' k8s/templates/ \| grep -c "/webhooks/apple"` | `0` | **0** |
| `grep -c "value: /webhooks/app-store" k8s/templates/httproute-webhooks.yaml` | `1` | **1** |
| `grep -vE '^\s*#' httproute-webhooks.yaml \| grep -ciE "rateLimit\|BackendTrafficPolicy\|filters:"` | `0` | **0** |
| `grep -c "type: Exact" k8s/templates/httproute-webhooks.yaml` | `1` | **1** |
| `grep -rn "/webhooks/apple" k8s/ \| grep -vE ':\s*#'` | empty | **empty** |
| `git status --porcelain -- k8s/templates/security-policy.yaml` | empty | **empty** |
| `git diff --stat -- k8s/` | one file | **one file** |
| `grep -c "APP_STORE_BUNDLE_ID\|APP_STORE_APP_APPLE_ID\|APP_STORE_ENVIRONMENT" .env.example` | `3` | **3** |
| `grep -vE '^\s*#' .env.example \| grep -c "APP_STORE_ROOT_CERTIFICATE_PATH"` | `0` | **0** |
| `grep -ciE "verification_temporarily_unavailable" .env.example` | non-zero | **3** |
| `grep -c "APP_STORE" config/config.yaml` | `0` | **0** |

Suite gates, unchanged from the 43-01 baseline because no Python was touched:

| Command | Result | Baseline |
|---|---|---|
| `uv run pytest -q` | **1048 passed**, 412 deselected | 1048 |
| `uv run ruff check src tests` | **All checks passed!** | clean |

`-m e2e` and `-m schema` were not re-run: this plan changes no Python, no SQL and no fixture, and no test reads either modified file. The two matches for `.env.example` in `tests/schema/conftest.py:34` and `tests/e2e/conftest.py:106` are both prose in a docstring and a comment; neither parses the file, and the schema conftest's `DB_*` fallbacks are hardcoded, not read from it.

**The `.env.example` block was verified against the running config loader, not against the plan text.** Three separate reads off `EnvironmentConfig`:

- With the three documented names exported: `bundle_id='com.example.app'`, `app_apple_id=1234567890` (an `int`), `environment=StoreEnvironment.production`. So the names the block tells a deployer to set are the names that actually land through `env_nested_delimiter="_"` with `env_nested_max_split=1`, and the `app_store` two-word section name is not the hazard it reads as (RESEARCH P-14, re-measured here).
- With the environment unexported: `environment=None`. The block's "NO default" claim is the loader's actual behaviour, not a documentation aspiration.
- With `APP_STORE_ENVIRONMENT=...` — the placeholder copied through unchanged: config load fails with `app_store.environment: Input should be 'sandbox' or 'production'`. The placeholder style this file already uses is therefore safe for a typed field; a deployer who forgets this line gets a refused boot naming the two values, not a running service in the wrong store environment.
- `root_certificate_path` read back as `config/certs/AppleRootCA-G3.cer`, which is the path the block names as the default, and `products` deep-merged from the tracked YAML alongside the three environment values — the partial-block merge P-13 predicted.

## Known Stubs

None. The three committed values are `...` placeholders, which is the file's established style for a value a deployer supplies, and the file is a documented example rather than a live configuration.

The `com.nativespeaker.subscription.monthly` placeholder in `config/config.yaml` is 43-01's and is recorded in that plan's summary; this plan did not touch that file.

## Issues Encountered

**None.** No package was installed, no dependency file was edited, no authentication gate was reached, and no architectural decision arose. The two tasks are a one-literal edit and an append.

**One measurement worth carrying:** the plan estimated 10,000 tokens and the realized diff is 611 on the same `chars/4` scale — a 16x overestimate. The number is recorded unrounded in `actuals` above rather than flattered, because the pair is what calibrates later estimates. The cause looks structural: this plan's two tasks are a single-line change and a documentation append, and the estimate appears to have been drawn from the phase's average plan rather than from this plan's own two `<files>` lists, each of which names exactly one file.

## User Setup Required

**Yes — three values and two dashboard fields, and nothing here can be done by this repository.**

Set in the deployment's gitignored `.env`, exactly as `.env.example` now documents:

| Variable | Where to read it |
|---|---|
| `APP_STORE_BUNDLE_ID` | App Store Connect → Apps → your app → General → App Information → Bundle ID |
| `APP_STORE_APP_APPLE_ID` | The same page → Apple ID, the numeric one. The library requires it in Production. |
| `APP_STORE_ENVIRONMENT` | A deployer decision: `sandbox` or `production`. No default. |

Then in App Store Connect → Apps → your app → General → App Information → App Store Server Notifications:

1. Set both the Production Server URL and the Sandbox Server URL to `https://<gateway host>/webhooks/app-store`.
2. Request a Test Notification and confirm one request log line and a 200.

Until the three values are set, the service boots, logs one `app_store_configuration_absent` warning and answers 503 `verification_temporarily_unavailable`. That is the designed and tested behaviour from 43-01, not a defect, and Apple retries on its own schedule.

Step 2 cannot be performed yet: there is no iOS app and no App Store Connect record for it. It is the phase's one genuinely human deliverable (D4 above) and stays open past this plan.

## Next Phase Readiness

**The deployment surface is done and is independent of the remaining four plans.** 43-03, 43-04 and 43-05 all change Python behind a path literal that no longer moves, and none of them touches `k8s/` or `.env.example`.

- **43-06** writes the dated REQUIREMENTS.md amendments and closes APPLEHOOK-01 and APPLEHOOK-02. Two items belong to it from here: the deferral recorded below, and the fact that neither box was checked by this plan.

**The one deferral this plan records.** The brief requires per-IP and per-URL gateway limits on this route, and none was added, on D-06 and the Phase 35 D-05/D-08 precedent that the v2.1 gateway contract owns every gateway limit. It is a deferral, not an omission. It compounds with the residual 43-01 flagged: this route is publicly reachable with no credential and no limiter at either layer, and each request costs a full certificate-path build plus up to three ES256 verifications. 43-06 should record the two together in the v2.1 gateway contract's wording rather than as two separate notes — the limit that closes the deferral is the same limit that closes the residual.

**For Phase 44 (Google Play):** `k8s/templates/httproute-webhooks.yaml` is now the file a second provider callback joins, and its shape is set — one `Exact` match per provider path under one `rules:` entry per rule, credential-free by absence from `security-policy.yaml`, with the reason written in the file. The RTDN route is a second match in the same template, not a second template.

## Self-Check: PASSED

Both modified files exist on disk with the asserted content, and both task commits are present in `git log`.

---
*Phase: 43-post-webhooks-app-store*
*Completed: 2026-09-04*
