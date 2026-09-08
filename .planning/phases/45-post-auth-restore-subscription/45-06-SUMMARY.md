---
phase: 45-post-auth-restore-subscription
plan: 06
subsystem: auth
tags: [google-play, ssrf, url-encoding, pydantic, input-validation, restore, security]

# Dependency graph
requires:
  - phase: 45-post-auth-restore-subscription
    provides: "45-02's Play restore read (`read_for_restore`, the shared `_get`) and 45-01's two-refusal surface gate"
  - phase: 43-post-webhooks-app-store
    provides: "the webhook entry point `read()`, which shares `_get` and is fixed by the same line"
provides:
  - "Both path segments of the Play read URL are percent-escaped in the shared `_get`"
  - "A caller-supplied `restore_proof` names exactly one path segment and can carry no query string"
  - "`RestoreRequest.provider` is bounded at 32 characters and `RestoreRequest.restore_proof` at 8192"
  - "Four unit cases asserting the request URL's wire form, three of them red against the pre-fix source"
  - "Four e2e cases pinning both length boundaries, two of them red against the pre-fix schema"
affects: [45 verification re-run, 45-07, 45-08, 45-09, v2.0 milestone close]

actuals:
  tokens: 2437
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Every caller-supplied value interpolated into an outbound URL is escaped at the single shared choke point, never at each entry point"
    - "A URL-shape assertion reads `httpx.Request.url.raw_path`, because `url.path` percent-decodes and would hide the escaping under test"

key-files:
  created: []
  modified:
    - src/nativespeaker/api/auth/google_play.py
    - src/nativespeaker/api/schemas/auth.py
    - tests/unit/test_restore_proof.py
    - tests/e2e/test_restore_subscription.py

key-decisions:
  - "The URL assertions read `request.url.raw_path`, not `request.url.path` as the plan wrote: httpx percent-decodes the `path` property, so a correct fix reads identically to the defect there and the case could never go green"
  - "The escaping lives only in `_get`; `read_for_restore` adds no second site, so the webhook `read()` is confined by the same line and the two entry points cannot drift"
  - "`external_id` stays the raw purchase token: the escaping is the URL's alone, and the control case asserts the persisted value is unescaped (44 D-10)"
  - "No `pattern=` is added to either request field: the store name is the handler's membership check (D-01) and the artifact's shape is the store's to judge"
  - "`routers/auth.py` is byte-unchanged; its comment claiming the logged provider is bounded is now true in fact rather than only in its text"

patterns-established:
  - "Escape at the choke point: one escaping site inside the private sender serves every public entry point above it"
  - "Assert the wire form: a transport-level case measures `raw_path` and `query` bytes, after the client library's own normalisation, because that normalisation is what the attack uses"

requirements-completed: [RESTORE-01, RESTORE-02]

coverage:
  - id: D1
    description: "An adversarial restore_proof carrying `../` or `?` reaches Google as one path segment of the intended resource, with an empty query string"
    requirement: RESTORE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestThePlayRequestUrlIsConfinedToOneResource::test_a_token_carrying_path_traversal_names_one_segment_and_no_other_path"
        status: pass
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestThePlayRequestUrlIsConfinedToOneResource::test_a_token_carrying_a_query_string_leaves_the_query_empty"
        status: pass
    human_judgment: false
  - id: D2
    description: "The `applications/{package_name}` guard cannot be escaped from the package-name side either, and an ordinary token still produces the exact path the read produced before"
    requirement: RESTORE-01
    verification:
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestThePlayRequestUrlIsConfinedToOneResource::test_a_package_name_carrying_a_separator_is_escaped_too"
        status: pass
      - kind: unit
        ref: "tests/unit/test_restore_proof.py#TestThePlayRequestUrlIsConfinedToOneResource::test_an_ordinary_token_reaches_the_expected_path_control"
        status: pass
    human_judgment: false
  - id: D3
    description: "The webhook's own Play read gets the same escaping, because both entry points share `_get`"
    requirement: RESTORE-01
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_google_play_notifications.py -q (73 passed)"
        status: pass
      - kind: other
        ref: "test \"$(grep -v '^ *#' src/nativespeaker/api/auth/google_play.py | grep -c 'quote(')\" = \"2\""
        status: pass
    human_judgment: false
  - id: D4
    description: "Both caller-controlled request fields carry a length bound: 32 for the store name, 8192 for the artifact, with the framework's 422 ahead of both refusals of the two-refusal gate"
    requirement: RESTORE-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSurfaceGateIsTheStoreNameAndTheProof::test_a_store_name_at_the_bound_still_reaches_the_gates_own_refusal"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSurfaceGateIsTheStoreNameAndTheProof::test_a_store_name_past_the_bound_is_the_frameworks_own_refusal"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSurfaceGateIsTheStoreNameAndTheProof::test_a_proof_at_the_bound_still_reaches_the_store_check"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSurfaceGateIsTheStoreNameAndTheProof::test_a_proof_past_the_bound_is_refused_before_any_store_call"
        status: pass
    human_judgment: false
  - id: D5
    description: "The two prohibitions: a refusal carries no part of the presented artifact, and neither bound is low enough to refuse a legitimate StoreKit 2 transaction or Play purchase token"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_restore_subscription.py#TestTheSurfaceGateIsTheStoreNameAndTheProof (the 422 body is the framework's own and names no value); tests/unit/test_restore_proof.py#TestThePlayRefusalNamesNoPartOfTheToken"
        status: pass
    human_judgment: true
    rationale: "Both are judgment calls the plan marked `verification: judgment`. That a 422 body carries no artifact content is asserted; that 8192 is comfortably above every real Apple JWS and Play token is a sizing judgment no case in this repository can prove, because no live store artifact is available to it."

# Metrics
duration: 9 min
completed: 2026-09-08
status: complete
---

# Phase 45 Plan 06: The Play read URL is confined and both request fields are bounded — Summary

**`quote(..., safe="")` on both interpolated segments of the Play read URL inside the shared `_get`, plus `max_length` on `RestoreRequest.provider` and `restore_proof`, closing VERIFICATION truth 7 (45-REVIEW CR-01) and WR-02.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-09-08T20:43:20Z
- **Completed:** 2026-09-08T20:52:20Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- A `restore_proof` of `a/../../../../v3/applications/evil/edits` now reaches Google as one escaped path segment of `/androidpublisher/v3/applications/com.nativespeaker.app/purchases/subscriptionsv2/tokens/`, and no longer relocates the deployment's own `androidpublisher`-scoped GET (T-45-06-01, T-45-06-02).
- A `restore_proof` carrying `?alt=media` now produces an empty query string; before this change the caller chose a query parameter on that signed request.
- The package-name segment is escaped on the same terms, so the `applications/{package_name}` guard `read_for_restore`'s own comment relies on cannot be escaped from either side.
- The webhook entry point `read()` is fixed by the same line, because both entry points share `_get` and no second escaping site was added.
- `provider` is bounded at 32 characters and `restore_proof` at 8192, so an abusive payload is the framework's 422 before the handler's refusal log, Apple's JWS decoder and the outbound URL (T-45-06-03).
- Eight cases were added, five of which were observed RED against the pre-fix source and green after it; three of the eight are controls that make the other five non-vacuous.

## Task Commits

Each task was committed atomically, RED then GREEN:

1. **Task 1 (tracer, tdd): The Play read URL is confined to one resource** — `72bac61` (test, RED) then `b3aca96` (feat, GREEN)
2. **Task 2 (auto, tdd): The two request fields carry a length bound** — `7332975` (test, RED) then `bc01e99` (feat, GREEN)

## Files Created/Modified

- `src/nativespeaker/api/auth/google_play.py` — `from urllib.parse import quote`; both interpolated values in `_get` pass through `quote(..., safe="")`; one new one-line comment at the send site. `PLAY_URL`, the method signature and every entry point are unchanged.
- `src/nativespeaker/api/schemas/auth.py` — `RestoreRequest.provider` gains `max_length=32`, `RestoreRequest.restore_proof` gains `max_length=8192`; one new one-line comment above each, stating why the bound exists. `min_length=1` is kept on both.
- `tests/unit/test_restore_proof.py` — module constant `PLAY_TOKENS_PATH`, module helper `_capturing_reader`, and `TestThePlayRequestUrlIsConfinedToOneResource` with four cases.
- `tests/e2e/test_restore_subscription.py` — module constants `MAX_PROVIDER_LENGTH` and `MAX_PROOF_LENGTH`, and four cases added to `TestTheSurfaceGateIsTheStoreNameAndTheProof`.

## Red-then-green record (plan `<verification>` item 4)

Observed against the pre-fix source, and again after the fix:

| Case | Pre-fix | Post-fix |
|---|---|---|
| `test_a_token_carrying_path_traversal_names_one_segment_and_no_other_path` | FAILED — the sent path was `/androidpublisher/v3/applications/com.nativespeaker.app/v3/applications/evil/edits` | passed |
| `test_a_token_carrying_a_query_string_leaves_the_query_empty` | FAILED — `url.query` was `b'alt=media'` | passed |
| `test_a_package_name_carrying_a_separator_is_escaped_too` | FAILED — the segment between `applications/` and `/purchases` was `com.nativespeaker.app/evil` | passed |
| `test_an_ordinary_token_reaches_the_expected_path_control` | passed (the control) | passed |
| `test_a_store_name_past_the_bound_is_the_frameworks_own_refusal` | FAILED — a 33-character name reached the handler and answered 403 | passed |
| `test_a_proof_past_the_bound_is_refused_before_any_store_call` | FAILED — an 8193-character proof reached the scripted store | passed |
| `test_a_store_name_at_the_bound_still_reaches_the_gates_own_refusal` | passed (the control) | passed |
| `test_a_proof_at_the_bound_still_reaches_the_store_check` | passed (the control) | passed |

RED run 1: `3 failed, 1 passed` of the new unit class. RED run 2: `2 failed, 4 passed` of the e2e class.

## Verification

| Check | Result |
|---|---|
| `uv run pytest tests/unit/test_restore_proof.py -q` | 39 passed |
| `uv run pytest tests/unit/test_google_play_notifications.py -q` | 73 passed |
| `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q` | 27 passed |
| `test "$(grep -v '^ *#' .../google_play.py \| grep -c 'quote(')" = "2"` | passed |
| `grep -c 'purchases/subscriptionsv2/tokens/{purchase_token}' .../google_play.py` | `1` (PLAY_URL unchanged) |
| `test "$(grep -c 'max_length' .../schemas/auth.py)" = "2"` | passed |
| `grep -c 'pattern=' .../schemas/auth.py` | `0` |
| `git diff --quiet -- src/nativespeaker/api/routers/auth.py` | byte-unchanged |
| `uv run ruff check src tests` | clean |
| Full suite | `uv run pytest -q` 1250 passed (was 1246), `-m e2e` 325 passed (was 321), `-m schema` 222 passed |

## Decisions Made

- **The URL assertion reads `raw_path`, not `path`.** httpx 0.28.1's `URL.path` property percent-decodes before returning, so after a correct fix it reports `/.../tokens/a/../../../../v3/applications/evil/edits` exactly as the defect did. Asserting there would make the case unable to pass against the very fix it demands. `url.raw_path` is the wire form and is what the transport sends, so every path case measures it. `url.query` is already raw bytes, so that case follows the plan verbatim.
- **One escaping site, not two.** `_get` is the choke point both `read()` and `read_for_restore()` already share. Escaping in `read_for_restore` as well would double-encode and would leave the webhook path unfixed.
- **`external_id` stays the raw token.** The control case asserts the returned `RestoredSubscription.external_id` equals the unescaped `PURCHASE_TOKEN`, so the value written to `core.subscriptions.external_id` remains the handle Google issued (44 D-10).
- **`routers/auth.py` was left byte-unchanged, deliberately.** Its comment — "The rejected string is caller-supplied and bounded, so logging it is safe" — was an unbacked claim before this plan and is now a true statement about `RestoreRequest.provider`. A later reader should not re-open WR-02 against it.
- **The bounds are sized to refuse abuse, never a real artifact.** The longest `PurchaseProvider` member is `google_play` at 11 characters, far below 32. A StoreKit 2 signed transaction (a three-part JWS carrying one certificate chain) and a Play purchase token are both far below 8192.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The plan's stated assertion target could not pass against a correct fix**

- **Found during:** Task 1 (writing the RED cases)
- **Issue:** The plan's `<action>` specifies asserting on `request.url.path`. httpx's `URL.path` property calls `unquote` on the reference's path before returning it, so a percent-escaped segment is reported decoded. Empirically confirmed against httpx 0.28.1 before writing the cases: after the fix, `url.path` reports `/androidpublisher/v3/applications/com.nativespeaker.app/purchases/subscriptionsv2/tokens/a/../../../../v3/applications/evil/edits`, whose `.split("/")` contains `"evil"`. The three adversarial cases would have been red before AND after the fix.
- **Fix:** Every path assertion reads `request.url.raw_path.decode()`, the wire form the transport sends. The query assertion is unchanged from the plan (`url.query` is already raw bytes). A one-line comment at the first case records why.
- **Files modified:** `tests/unit/test_restore_proof.py`
- **Verification:** The three cases go red against the pre-fix source and green after it, which is exactly the behaviour the plan's acceptance criteria demand; `raw_path` is the string httpx puts on the wire, so the assertion is strictly stronger than the plan's.
- **Committed in:** `72bac61` (Task 1 RED commit)

**2. [Rule 3 - Blocking] The `_get` comment the plan asked to replace does not exist**

- **Found during:** Task 1 (applying the fix)
- **Issue:** The plan says to "replace the comment at `_get`" with the new escaping line and not to leave the old one standing. `_get` carries exactly one comment today, and it is about the credential refresh never running on the event loop — unrelated to URL construction and still true. There is no URL-construction comment to replace.
- **Fix:** The new one-line ASD-STE100 comment was added at the send site; the refresh comment was left in place. No duplicate or stale comment about URL construction exists. `read_for_restore`'s comment at lines 261-262, which relies on the `applications/{package_name}` segment, was also left as written — this change makes its claim enforceable rather than false.
- **Files modified:** `src/nativespeaker/api/auth/google_play.py`
- **Verification:** `uv run ruff check src tests` clean; both comments read as one line each.
- **Committed in:** `b3aca96` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Neither changes what the plan set out to prove. Deviation 1 makes the assertion stronger than written and was required for the plan's own red-then-green criterion to be satisfiable at all. Deviation 2 preserves an unrelated true comment. No scope creep: no file outside `<files_modified>` was touched.

## Estimate vs actuals

The plan estimated 25000 tokens; the realized diff is 9746 characters, so 2437 on the same `chars/4` scale — roughly a tenth of the estimate. The estimate is not adjusted to look closer. The plan's own artifact list was accurate (one import, two `quote(...)` calls, two `Field(...)` keywords, eight test cases); the estimate appears to have been carried from sibling plans of this phase rather than sized to this diff.

## Issues Encountered

None. Both preconditions held: PostgreSQL was reachable on the repo's `.env` credentials before Task 2, and no package install was needed — `quote` is `urllib.parse`, standard library, so `uv.lock` is untouched (T-45-06-SC).

## Known Stubs

None. No debt marker, placeholder or hardcoded empty value was introduced.

## Threat Flags

None. No new network endpoint, auth path, file access pattern or schema change at a trust boundary was introduced. Every threat this plan touches is already in its own `<threat_model>`: T-45-06-01 and T-45-06-02 are mitigated by the escaping, T-45-06-03 by the two bounds, and T-45-06-04 and T-45-06-SC were accepted at planning time and are unchanged.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- VERIFICATION truth 7 can be re-run and answered VERIFIED: the Play verification request reaches the endpoint and package the server intends, and a case in the suite now asserts it on the wire form.
- Truths 1 and 6 (45-REVIEW CR-02 and CR-03) remain open and are 45-07's and 45-08's to close. Nothing in this plan touches `services/restore.py` or `crud/subscriptions.py`, so neither is disturbed.
- 45-09 records the phase's REQUIREMENTS.md entries; WR-02 is now closed in fact and should be recorded there as INCORPORATED, together with the note that `routers/auth.py`'s "bounded" comment is now true.

## Self-Check: PASSED

All four modified files exist on disk; all four task commits (`72bac61`, `b3aca96`, `7332975`, `bc01e99`) are present in `git log`.

---
*Phase: 45-post-auth-restore-subscription*
*Completed: 2026-09-08*

---

## Addendum — CR-01 reopened and closed

**Date:** 2026-09-08
**Commits:** `f28047a` (test, RED), `513ef70` (fix, GREEN), and this record.

### What the first closure missed, and why

The first closure escaped both interpolated values with `quote(value, safe="")` and asserted the
result on `request.url.raw_path`. The assertion was right and the escaping is real, but the closure
picked the input that passes rather than the input that breaks the rule.

`urllib.parse.quote` never escapes the unreserved set `A-Za-z0-9_.-~`, so a `.` survives, and httpx
performs RFC 3986 dot-segment removal when it builds the `URL`. The guarding case used
`"a/../../../../v3/applications/evil/edits"`, whose `/` characters **are** escaped. Escaping the
separators makes the whole token one segment, which neutralises that particular traversal — but for
the wrong reason. It says nothing about a token that **is** a dot segment. The comment the closure
wrote at the send site ("a caller's token names one segment and never a path") was therefore false
as written, and the plan's own acceptance criteria could not catch it: every criterion was about the
presence of `quote`, not about the shape of the path a dot-only token produces.

### The observed paths, before the fix

Driven through the production `PlayDeveloperSubscriptions.read_for_restore` over the module's own
`_capturing_reader()` recording transport, against the unchanged source at `6e0801b`:

```
'.'      sent=1 outcome=no raise paths=['/androidpublisher/v3/applications/com.nativespeaker.app/purchases/subscriptionsv2/tokens']
'..'     sent=1 outcome=no raise paths=['/androidpublisher/v3/applications/com.nativespeaker.app/purchases/subscriptionsv2']
'....'   sent=1 outcome=no raise paths=['/androidpublisher/v3/applications/com.nativespeaker.app/purchases/subscriptionsv2/tokens/....']
```

This reproduces the reviewer's two paths exactly. Each request carried the deployment's own
`androidpublisher`-scoped bearer. `'....'` is not a dot segment, so it stays in the path and names
one segment — it is included below because the rule the guard states is "a token of dots alone is
not a name", which is the property that can be checked before the client normalises anything.

### The RED run

`tests/unit/test_restore_proof.py::TestThePlayRequestUrlIsConfinedToOneResource`, extended with the
dot-only cases and run against the unchanged source:

```
tests/unit/test_restore_proof.py ....FFFF.                               [100%]
E   Failed: DID NOT RAISE <class 'nativespeaker.api.errors.ProofRejected'>   [.]
E   Failed: DID NOT RAISE <class 'nativespeaker.api.errors.ProofRejected'>   [..]
E   Failed: DID NOT RAISE <class 'nativespeaker.api.errors.ProofRejected'>   [....]
E   Failed: DID NOT RAISE <class 'nativespeaker.api.errors.Unavailable'>     (dot-only package name)
============ 4 failed, 5 passed, 35 deselected, 1 warning in 0.19s =============
```

The 5 passing are the four original cases plus the new control
`test_a_token_carrying_dots_among_other_characters_is_still_read_control`, which passes before and
after and proves the guard is not over-broad. That control matters: a real Play purchase token
carries dots, so a guard that refused every dot would refuse every live restore.

### The fix

`src/nativespeaker/api/auth/google_play.py`:

- One module-level predicate `_names_one_path_segment(value)`, returning `bool(value.strip("."))`.
- `read_for_restore` refuses, in this order: no credential, then an absent or dot-only
  `package_name` as `Unavailable(stage=RESTORE_READ_STAGE)`, then a dot-only `purchase_token` as
  `ProofRejected(stage=RESTORE_TOKEN_GONE_STAGE)`.
- The send-site comment now reads "Escaping confines each value to one segment, except dots, which
  `read_for_restore` refuses."

No new error leaf. `ProofRejected(stage=RESTORE_TOKEN_GONE_STAGE)` is the answer a token Google
reports as gone already earns, so the client-visible body is byte-identical to today's: 403
`proof_rejected`. The `restore_not_found` family 45-07 pinned to one body is not touched at all.

**Why the guard sits in `read_for_restore` and not in the shared `_get`.** A rejection needs a
vocabulary, and the two entry points do not share one — `_get`'s own docstring already says "each
entry point classifies a transport failure its own way". `ProofRejected` raised from `_get` would
escape the webhook's `read()` as a 403 to Pub/Sub, which is not an answer that path may give;
`Unavailable` raised from `_get` would turn the caller's dead token into a 503 that invites a retry
that can never succeed, changing the client-visible body. `read_for_restore` is also the whole
attack surface: the webhook's package name is compared byte-for-byte against config before the read
(`app/dependencies.py:191`) and its purchase token arrives inside a Google-signed RTDN, so neither
of its two values is caller-supplied.

**Why not escape `.` to `%2E`.** It was considered and measured. httpx 0.28.1 does **not**
re-normalise a percent-encoded dot — `%2E%2E` survives to `raw_path` intact — so the mechanism works
at the transport. It was rejected on merits anyway: it rewrites the wire form of **every**
legitimate request, including the package name (`com%2Enativespeaker%2Eapp`), and whether Google's
own front end normalises `%2E` back to `.` before routing cannot be tested from here. Trading a
proven-safe refusal of an input no real token uses for an untestable bet on a live billing API is
the worse deal.

### The green run

Re-driving the same recording transport with the same three tokens, after the fix:

```
'.'      sent=0 outcome=ProofRejected paths=[]
'..'     sent=0 outcome=ProofRejected paths=[]
'....'   sent=0 outcome=ProofRejected paths=[]
```

Nothing reaches the transport.

| Command | Result |
|---|---|
| `uv run pytest tests/unit/test_restore_proof.py -q` | 44 passed |
| `uv run pytest -q` | 1255 passed, 562 deselected |
| `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q` | 35 passed |
| `uv run ruff check src tests` | All checks passed |

### Deviations in this follow-up

**1. [Rule 1 - Bug] An absent `package_name` was a 500, and the new guard would have been an `AttributeError`**

- **Found during:** the first full run after the fix.
- **Issue:** `GooglePlayConfig.package_name` is `str | None`, but `RestoreService.package_name` and
  `read_for_restore` both declare `str`. On a deployment with a credential and no package name,
  `quote(None, safe="")` already raised `TypeError` -> 500. Placing the dot guard ahead of the
  credential check turned `test_an_unconfigured_credential_is_temporarily_unavailable` into an
  `AttributeError` on `None.strip`.
- **Fix:** the credential check stays first, and the package guard reads
  `if not package_name or not _names_one_path_segment(package_name)`. An unconfigured deployment now
  answers 503 `verification_temporarily_unavailable` — the meaning it always had — instead of 500.
- **Verification:** `uv run pytest -m e2e tests/e2e/test_restore_subscription.py -q`, 35 passed.
- **Committed in:** `513ef70`.

**2. [Rule 3 - Blocking] The recorded auth package shape had to be rewritten**

- **Found during:** the first full unit run after the fix.
- **Issue:** `tests/unit/test_auth_package_shape.py` asserts a literal `(modules, classes,
  functions)` triple. The new `_names_one_path_segment` made it `(8, 24, 59)` against a recorded
  `(8, 24, 58)`.
- **Fix:** `CURRENT` updated to `(8, 24, 59)`, which is what that case's own docstring instructs a
  later phase to do.
- **Verification:** `uv run pytest -q`, 1255 passed.
- **Committed in:** `513ef70`.

### What this leaves open

The webhook entry point `read()` carries no equivalent guard. Its two values are not caller-supplied
(see above), so no caller can reach it, but the invariant "every value interpolated into the Play
read URL names one path segment" holds at `read_for_restore` and not at `_get`. If a later phase
gives `read()` a value from an untrusted source, the guard has to move down or be repeated there.
