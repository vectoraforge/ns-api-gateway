---
phase: 44-post-webhooks-google-play-rtdn
plan: 02
subsystem: infra
tags: [google-play, pubsub, rtdn, envoy, gateway-api, helm, google-auth, uv, deployment]

requires:
  - phase: 43-post-webhooks-app-store
    provides: httproute-webhooks.yaml with the App Store exact-path match, and the APP_STORE_ block in .env.example whose voice this plan follows
  - phase: 44-post-webhooks-google-play-rtdn
    provides: "plan 44-01 registered POST /webhooks/google-play/rtdn, GooglePlayConfig, and the google_play_configuration_absent boot warning this block documents"
provides:
  - "The Envoy exact-path match for POST /webhooks/google-play/rtdn, outside the JWT SecurityPolicy, with the Authorization header reaching the backend unchanged"
  - "google-auth as a declared direct dependency in pyproject.toml and uv.lock"
  - "The GOOGLE_PLAY_ block in .env.example: the three deployer values, both egress hosts, the wrong-audience failure mode and the Android client's attribution obligation"
  - "44-USER-SETUP.md — the Play Console, Pub/Sub and Android-client steps this repository cannot perform"
affects: [44-03, 44-04, 44-06, 44-07, 45-restore-subscription]

actuals:
  tokens: 1274
  tasks: 2
  commits: 2

tech-stack:
  added: ["google-auth>=2.49 (promoted from a firebase-admin transitive edge to a direct one; nothing installed)"]
  patterns:
    - "One HTTPRoute rule carries every exact path of the provider-callback partition, so the single backendRefs block is reused rather than duplicated"
    - "A deployment value is documented only after it is loaded through the real config object, never from a naming precedent"

key-files:
  created:
    - .planning/phases/44-post-webhooks-google-play-rtdn/44-USER-SETUP.md
  modified:
    - k8s/templates/httproute-webhooks.yaml
    - pyproject.toml
    - uv.lock
    - .env.example

key-decisions:
  - "The Google callback is a second `matches` entry on the existing rule, not a second rule, because D-19 asks for the existing backendRefs block reused unchanged"
  - "The three GOOGLE_PLAY_ variable names were verified against GooglePlayConfig by loading them, not inferred from the APP_STORE_ precedent"
  - "The comment above `rules` now states both providers' credential shapes, because the inherited one-line comment was true of Apple and false of Google"

patterns-established:
  - "Every exact path in the provider-callback partition is a match on one rule with one backendRefs block"
  - "An .env.example block states what a wrong value costs, not only where the right value is read"

requirements-completed: []

coverage:
  - id: D1
    description: "Envoy routes POST /webhooks/google-play/rtdn to the backend by exact path, outside the JWT SecurityPolicy, with the Authorization header unchanged"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "test \"$(grep -c 'value: /webhooks/google-play/rtdn' k8s/templates/httproute-webhooks.yaml)\" = \"1\""
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'value: /webhooks/app-store' k8s/templates/httproute-webhooks.yaml)\" = \"1\" — the inherited match survives"
        status: pass
      - kind: other
        ref: "PyYAML parse of the substituted template: rules=1, matches=[('Exact','/webhooks/app-store','POST'),('Exact','/webhooks/google-play/rtdn','POST')], one backendRefs, rule keys exactly ['backendRefs','matches']"
        status: pass
      - kind: other
        ref: "security-policy.yaml targetRefs names only -app-routes and -llm-routes, so -webhook-routes is outside the JWT SecurityPolicy"
        status: pass
    human_judgment: false
  - id: D2
    description: "No rate-limit entry, BackendTrafficPolicy or filters block is attached to either webhook path (43 D-06's deferral inherited)"
    verification:
      - kind: other
        ref: "test \"$(grep -vE '^\\s*#' k8s/templates/httproute-webhooks.yaml | grep -ciE 'rateLimit|BackendTrafficPolicy|filters:')\" = \"0\""
        status: pass
      - kind: other
        ref: "The parsed rule carries exactly two keys, backendRefs and matches — no filters key exists"
        status: pass
    human_judgment: false
  - id: D3
    description: "google-auth is a declared direct dependency rather than an accident of firebase-admin's dependency tree, and the environment still imports it"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "uv lock && uv sync && uv run python -c 'import google.auth; print(google.auth.__version__)' — 2.49.1"
        status: pass
      - kind: other
        ref: "test \"$(grep -c 'google-auth' pyproject.toml)\" = \"1\""
        status: pass
      - kind: other
        ref: "git diff uv.lock — two added lines only, the dependencies entry and the requires-dist specifier; no package version changed"
        status: pass
      - kind: unit
        ref: "uv run pytest -q — 1105 passed, unchanged from 44-01's close; uv run ruff check src tests clean"
        status: pass
    human_judgment: false
  - id: D4
    description: "A deployer can read from .env.example alone which three values to set, where each is read, and what the route does while they are absent"
    requirement: "PLAYHOOK-01"
    verification:
      - kind: other
        ref: "test \"$(grep -c '^#GOOGLE_PLAY_' .env.example)\" = \"3\""
        status: pass
      - kind: other
        ref: "test \"$(grep -ciE 'verification_temporarily_unavailable' .env.example)\" -ge 2"
        status: pass
      - kind: other
        ref: "The three shipped example values loaded through EnvironmentConfig().app_config.google_play and returned unchanged — the block's own 'values that parse' promise, executed"
        status: pass
      - kind: other
        ref: "google_play_configuration_absent exists at src/nativespeaker/api/app/lifespan.py:131 with the consequence string this block quotes"
        status: pass
    human_judgment: false
  - id: D5
    description: "The deployment surface is documented including the failure mode that looks like nothing at all: a wrong audience, both egress hosts, and the Android client's obfuscatedAccountId obligation"
    verification:
      - kind: other
        ref: "test \"$(grep -c 'androidpublisher.googleapis.com' .env.example)\" -ge 1"
        status: pass
      - kind: other
        ref: "test \"$(grep -ciE 'obfuscated' .env.example)\" -ge 1"
        status: pass
    human_judgment: true
    rationale: "The greps prove the words are present. Whether the prose actually lets an unfamiliar deployer set the values correctly, and whether it reads in the APP_STORE_ block's own voice, is a reading judgment no command makes. This is the deliverable a human should read before the phase is verified."
  - id: D6
    description: "The Play Console grant, the Pub/Sub push subscription, the RTDN topic and the Android client's obfuscatedAccountId are recorded as human steps in 44-USER-SETUP.md"
    verification: []
    human_judgment: true
    rationale: "Every item is an action in an external console or in the Android application. None can be performed or observed from this repository, and none can be verified until a real Play deployment exists."

duration: 5min
completed: 2026-09-05
status: complete
---

# Phase 44 Plan 02: The gateway route, the declared dependency and the deployment surface Summary

**Envoy now routes `POST /webhooks/google-play/rtdn` to the backend by exact path with the Authorization bearer intact, `google-auth` is a declared direct edge in `pyproject.toml` and `uv.lock`, and `.env.example` carries the three deployer values together with the failure mode that looks like nothing at all.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-05T11:05:53Z
- **Completed:** 2026-09-05T11:10:32Z
- **Tasks:** 2
- **Files modified:** 4 (plus `44-USER-SETUP.md` created)

## Accomplishments

- `k8s/templates/httproute-webhooks.yaml` carries both callback paths as exact POST matches on **one rule**, sharing the one `backendRefs` block and its Helm expressions. The route is still outside the JWT `SecurityPolicy`, which was re-read and names only `-app-routes` and `-llm-routes`.
- The comment above `rules` no longer states a fact that is true of one provider only. It now says that Apple sends no `Authorization` header, and that Google sends `Authorization: Bearer <OIDC token>` which must reach the backend unchanged, because it is that route's only credential.
- `google-auth>=2.49` is a declared dependency. `uv lock` added exactly two lines and changed no package version: 2.49.1 was already resolved through `firebase-admin` and already imported by `auth/firebase.py`, so this promotes a transitive edge and installs nothing.
- `.env.example` gained a `GOOGLE_PLAY_` block in the App Store block's own voice, stating the five operational facts the plan named, plus both egress hosts — `www.googleapis.com`, which Firebase already needs, and `androidpublisher.googleapis.com`, which this application has never called.
- `44-USER-SETUP.md` records the steps this repository cannot perform: the `androidpublisher` grant made in Play Console rather than in GCP IAM, the Pub/Sub topic and push subscription, and the Android client's `obfuscatedAccountId` obligation.

## Task Commits

1. **Task 1: the gateway route and the declared dependency** - `6b0170c` (feat)
2. **Task 2: what a deployer must set, and what it costs to get it wrong** - `2d4f05b` (docs)

**Plan metadata:** the `docs(44-02)` commit that carries this file.

## Files Created/Modified

- `k8s/templates/httproute-webhooks.yaml` - the second exact POST match, and the corrected credential comment
- `pyproject.toml` - `google-auth>=2.49` in `[project].dependencies`
- `uv.lock` - the direct edge recorded, two added lines, no version change
- `.env.example` - the `GOOGLE_PLAY_` block: the three values, both egress hosts, the wrong-audience cost, the attribution obligation
- `.planning/phases/44-post-webhooks-google-play-rtdn/44-USER-SETUP.md` - the external-console and Android-client steps

## Decisions Made

- **The Google callback is a second `matches` entry on the existing rule, not a second rule.** D-19 asks for the existing `backendRefs` block reused unchanged. Gateway API ORs the matches inside one rule, so one rule with two exact POST matches and one `backendRefs` is the literal reuse. A second rule would have duplicated the block and both its Helm expressions, which is the thing D-19 asked to avoid.
- **The three variable names were verified, not inferred.** `BaseConfig` sets `env_nested_delimiter="_"` with `env_nested_max_split=1`, so how a two-word section name splits is not obvious from the setting. All three were loaded through `EnvironmentConfig` — first with probe values, then with the exact values `.env.example` ships — and each reached its `GooglePlayConfig` field. Documenting them from the `APP_STORE_` precedent alone would have been an assumption.
- **The `rules` comment was rewritten rather than extended.** The inherited line, "Apple sends no Authorization header", becomes actively misleading once a second path exists whose only credential is that header. A reader deciding whether a header-stripping filter is safe would have read the old line and been wrong.
- **`helm template` was not run, because helm is not installed here.** The template was checked by substituting the Helm expressions and parsing the result with PyYAML, which proves the YAML structure and the two matches but not the Helm rendering. Recorded in `.planning/WINDOWS.md` as an `unrun-verify`, not claimed as a pass.

## Deviations from Plan

None - plan executed exactly as written.

Both tasks' `<action>` blocks were followed literally, and all nine `<verify>` commands across the two tasks were run and passed. No file outside the plan's `files_modified` was touched by Task 1 or Task 2.

---

**Total deviations:** 0
**Impact on plan:** None.

## Issues Encountered

None.

## User Setup Required

**External services require manual configuration.** See [44-USER-SETUP.md](./44-USER-SETUP.md) for:

- The three `GOOGLE_PLAY_` environment variables and where each is read
- The `androidpublisher` grant, made in **Play Console → Users and permissions**, not in GCP IAM
- The Pub/Sub topic and the push subscription with an OIDC token, and the Play Console RTDN setting
- Egress to `www.googleapis.com` and `androidpublisher.googleapis.com`
- The Android client's `BillingFlowParams` `obfuscatedAccountId` obligation, which is outside this repository

Until these are complete the route stays registered, answers 503 `verification_temporarily_unavailable`, and the boot log carries one `google_play_configuration_absent` warning.

## Known Stubs

None. This plan added no code path.

The two stubs recorded by plan 44-01 — the single-entry `_STATES` map and the undifferentiated non-2xx Play arm — are untouched here and remain plan 44-03's work.

## Threat Flags

None. Every surface this plan touches is in the plan's own threat register: the exact-path, POST-only admission (T-44-08), the non-secret example values (T-44-09), the accepted absence of a gateway limit (T-44-10), the documented misconfigured-audience failure mode (T-44-11), and the no-install dependency promotion (T-44-SC).

One register entry is worth restating rather than leaving as a table row. **T-44-10 is accepted, and this plan is where it becomes reachable.** `/webhooks/google-play/rtdn` joins `/webhooks/app-store` as a path anyone on the internet can reach with no gateway limit. It is narrower than the Apple path recorded under 43-06: an unverified Google request costs one RS256 verification against a cached JWKS document, and it fails before `get_db` and before any Play call, so no session is opened and no network call is made. It closes with the same v2.1 gateway contract.

## Next Phase Readiness

- The route is reachable from Envoy, so plan 44-03's expansion of `auth/google_play.py` and plan 44-06 both land on a routed path.
- Plan 44-04 owns the configuration and environment work. Its author should read the `GOOGLE_PLAY_` block in `.env.example` before writing: this plan already documents the three variables, both egress hosts and the ADC credential, so 44-04's remaining surface is `google_play.products` in `config/config.yaml`. **Note a stale forward reference:** `44-01-SUMMARY.md` § User Setup Required says the three deployment values "are documented by plan 44-04". They are documented here, in 44-02.
- `PLAYHOOK-01` is **not** marked complete. It is declared by 44-02, 44-03, 44-04, 44-06 and 44-07; `requirements.ready-ids` reported 0 of 1 ready, and it stays open until the last declaring plan produces its summary.
- No real Pub/Sub push has ever reached this route, and none can until the topic, the push subscription and an Android client exist. That is the same standing fact recorded for Apple under 43-06, and the gateway match cannot be exercised end to end before then.

---
*Phase: 44-post-webhooks-google-play-rtdn*
*Completed: 2026-09-05*

## Self-Check: PASSED

- Every file named above exists on disk: `k8s/templates/httproute-webhooks.yaml`, `pyproject.toml`, `uv.lock`, `.env.example`, `44-USER-SETUP.md`, and this summary.
- Both task commits exist in `git log`: `6b0170c`, `2d4f05b`.
- Both tasks' acceptance criteria were re-run at close and pass: 5 of 5 for Task 1, 5 of 5 for Task 2.
- Plan verification re-run at close: the substituted template parses to one rule with the two expected exact POST matches and one `backendRefs`; `uv sync` leaves the environment importable (`google.auth` 2.49.1); `uv run pytest -q` 1105 passed, 466 deselected; `uv run ruff check src tests` clean.
- One verification is recorded as NOT run: `helm template` itself, because helm is absent from this environment. Logged in `.planning/WINDOWS.md`.
