# Phase 37: POST /auth/create-user - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-21
**Phase:** 37-post-auth-create-user
**Areas discussed:** Rate limiting the open route, Firebase Admin (transport / credentials / tests), The success response body

**Areas offered but not selected:** Testing atomicity and the race (criteria 3 and 4) — carried into
CONTEXT.md as Claude's Discretion rather than dropped.

---

## Rate limiting the open route

### Q1 — What ships in Phase 37?

| Option | Description | Selected |
|--------|-------------|----------|
| Narrow backend limiter, this route only | Reinstate just `create_user_prepare` and `create_user` (10/min/ip each) as a small purpose-built limiter, not a revival of §5's config-driven engine | |
| Accept the gap, defer to v2.1 with Envoy | Ship unrated; register `registration_temporarily_unavailable` per the D-07 precedent | |
| Bring the Envoy contract forward for this route | Undo part of 35 D-08 now — HTTPRoute, global rate-limit service, response-override 429, `xff_num_trusted_hops` | |

**User's choice:** Free text — *"Nothing. The backend must not have any traffic limiters."*
**Notes:** Stronger than the offered "accept the gap" option, which had left the door open to
registering the gateway error class. Phase 35 D-05 holds without exception. Recorded as a flagged
SHARED-INVARIANTS conflict in CONTEXT.md D-01, with the exposure stated plainly rather than softened.

### Q2 — The two cross-request Firebase lookup budgets

| Option | Description | Selected |
|--------|-------------|----------|
| Drop both; keep the 3-attempt retry budget | They are per-minute IP/deployment-keyed traffic limits in budget vocabulary; only `adapter_firebase_lookup` survives | ✓ |
| Keep them as per-request no-ops | Register the names at a non-binding value so the call-site shape matches §02 | |

**User's choice:** Asked *"What is BudgetGate?"* — answered in prose rather than re-asking, then
resolved as "drop both" by consistency with Q1.
**Notes:** The clarification mattered. `BudgetGate` is per-request provider-call metering, not a rate
limiter — Phase 35 built it when D-05 deleted the `limits` engine, and `test_budgets.py::TestNotTrafficLimiting`
enforces that distinction. Explaining it is what surfaced that the module has one name left, which
led directly to Q4.

### Q3 — Register `registration_temporarily_unavailable`?

| Option | Description | Selected |
|--------|-------------|----------|
| Register it, unreachable for now | Follows the D-07 precedent that kept `rate_limited` alive for the future Envoy body | |
| Omit it until the gateway exists | Three new classes instead of four; v2.1 adds it with the work that raises it | ✓ |

**User's choice:** Asked *"Is it used for backend limiter? The backend doesn't do rate-limits"* —
answered in prose (it is Envoy-emitted; the backend never raises it), then omission was accepted.
**Notes:** The D-07 precedent was shown explicitly before the choice, so this is a knowing
divergence from it, not an oversight.

### Q4 — How far does the throttling-via-library point extend?

| Option | Description | Selected |
|--------|-------------|----------|
| Retire BudgetGate, use tenacity here | Delete `auth/budgets.py`; express §02's 3-attempt budget as a tenacity policy. Leave `resilience.py` alone | |
| Also convert resilience.py | Same, plus replace the LLM retry loop at `resilience.py:165-191` so there is one retry idiom | ✓ |
| Keep BudgetGate, don't add a dependency | Leave the Phase 35 seam alone; avoid promoting tenacity and picking up the stale `uv.lock` | |

**User's choice:** Also convert `resilience.py`.
**Notes:** Prompted by the user's own observation that a 3-attempt cap "sounds like function
throttling that can be implemented without writing custom code" — the same instinct that retired the
hand-rolled `RejectionCounter` in Phase 36 (commit 5f275c8). The broader blast radius was stated in
the option text before the choice: that loop is on `POST /chats`, which this phase otherwise never
touches, and it carries once-only `on_admitted` semantics, transient-vs-permanent classification,
and circuit-breaker interaction. CONTEXT.md D-05 records those risks and asks for a separate plan
and commit.

### Q5 — The `uv.lock` revision 2 → 3 bump

| Option | Description | Selected |
|--------|-------------|----------|
| Commit the full uv lock output | tenacity + the 1.5.0→1.6.0 correction + the revision bump, one dependency-scoped commit | ✓ |
| Commit tenacity + version, pin revision at 2 | Avoid moving the lockfile format in a phase that isn't about tooling | |
| You decide | Let the planner check `uv --version` behavior first | |

**Notes:** Forced by Q4 — tenacity is present today only transitively (`uv.lock:1540`). D-35-05-A
said "whoever next touches dependencies should run `uv lock` deliberately and commit the result on
its own"; this is that phase, and this closes it. Narrows Phase 36 D-15's hold on `uv.lock`;
`docker-compose.yml` stays unowned.

---

## Firebase Admin: transport, credentials, tests

### Q1 — What does the concrete adapter call?

| Option | Description | Selected |
|--------|-------------|----------|
| firebase-admin SDK, threadpool-offloaded | Already a declared dependency; sync, so needs `run_in_threadpool` per 35-12 | ✓ |
| Identity Toolkit REST over httpx | Natively async, per-call `timeout=`; costs hand-rolled service-account token minting | |
| firebase-admin for credentials only | Mint tokens with google-auth, issue the call over httpx | |

**User's choice:** Free text first — *"Search online for async alternative"* — then
firebase-admin + `run_in_threadpool` after the search.
**Notes:** The search returned a clean negative and is the reason this option was taken. No async
Firebase *Auth* admin client exists: firebase-admin is `requests`-based, async support landed for
Firestore (v5.3.0) and messaging only, [issue #104](https://github.com/firebase/firebase-admin-python/issues/104)
is still open, and [`async-firebase`](https://pypi.org/project/async-firebase/1.3.4/) is Cloud
Messaging only. Executor offload is Google's own documented workaround and already the codebase's
house rule.

### Q2 — Where do service-account credentials live?

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit path in gitignored .env | `FIREBASE_CREDENTIALS_PATH` → `credentials.Certificate(path)`, Secret volume mount | |
| Inline JSON in gitignored .env | Whole object as one value → `credentials.Certificate(json.loads(...))`; no volume mount | ✓ |
| GKE Workload Identity, no key file | No downloadable key; needs cluster binding this repo lacks and cannot serve local dev or e2e | |

**Notes:** Keeps real key material out of `config/config.yaml`, which is tracked in git — the
compromise 35 D-20 accepted for the HMAC keys. ADC was rejected in the option text because
SHARED-INVARIANTS forbids any ambient or fallback client.

### Q3 — Test coverage for the classifier and both flows

| Option | Description | Selected |
|--------|-------------|----------|
| Real anonymous e2e + substituted adapter for registered | `accounts:signUp` mints a genuine anonymous user (empty providerData); fake adapter drives registered and every rejection shape | ✓ |
| Substitute the adapter for everything | Fast and hermetic, but nothing proves the real SDK returns the shape the classifier expects | |
| Real Firebase for both, manual fixture accounts | Highest fidelity; unreproducible shared CI state and Apple's flow cannot be scripted | |

**Notes:** Driven by a scout finding, not a preference: the existing e2e fixture signs in with
email/password, yielding `providerData == [password]`, which §02's closed classifier rejects. The
existing infrastructure therefore hits the reject-everything-else arm by default and cannot drive a
successful completion in either flow.

---

## The success response body

### Q1 — What does a successful completion return?

| Option | Description | Selected |
|--------|-------------|----------|
| The /auth/sync payload shape | Shared response model defined here, imported by Phase 38; one client parser for both routes | |
| Registration state only | Return the classified `identity_provider`; entitlement state is /auth/sync's job | ✓ |
| You decide at plan time | Defer until the planner can read 03-sync.md and 04-users-me.md together | |

**User's choice:** Registration state only — on the second asking.
**Notes:** The first attempt was rejected outright: *"What are you talking about? Stop asking me
without context."* Fair — the question opened on "§02 step 14" without establishing that the spec's
entire instruction for the success body is one unelaborated sentence, that this is the client
contract for the first call every new user makes, or what the two candidate bodies actually look
like. Re-asked with concrete JSON for both and the grants-are-never-created constraint stated, and
it resolved immediately. Lesson for future turns in this project: the spec vocabulary is not shared
context — cite it, don't lean on it.

### Q2 — Do the purchase-attribution tokens come back?

| Option | Description | Selected |
|--------|-------------|----------|
| No — GET /users/me surfaces them | `PROJECT.md:20` already assigns them to the Phase 39 rewrite; one place surfaces them | ✓ |
| Yes — return them on creation | Saves a round-trip on the signup→purchase conversion path | |

---

## Claude's Discretion

- **Race-loser durability mechanism** — §02 step 12 names three acceptable mechanisms. Raised in the
  gray-area presentation, not selected for discussion. Default recorded: consume-first atomic
  conditional update.
- **Testing success criteria 3 and 4** — offered as a fourth gray area, not selected. The constraint
  is real and recorded: the e2e harness's savepoint-joined single-connection fixture cannot express
  committed concurrent transactions.
- Issuer → named-app selection for the Admin client, and where the 5–10s per-attempt timeout is set.
- Module layout for the concrete adapter and classifier; names of the three new error constants.
- One route function dispatching on `classify_mode_signal()` vs two functions behind one route.
- What the structured security log records on each fail-closed branch.

## Deferred Ideas

- `registration_temporarily_unavailable` and the Envoy gateway contract (§9 / FOUND-09) — v2.1.
- Real Google/Apple-linked Firebase test accounts for genuine registered-flow e2e coverage.
- `docker-compose.yml` — still modified in the working tree, still unowned.
- Secret Manager integration — its rationale now covers the Firebase service-account key too.
- Restore `with_structured_output(strict=True)` — unchanged from Phase 36; not to be conflated with
  D-05's `resilience.py` conversion despite touching the same LLM path.

## Process Note

A `<system-reminder>` claiming "auto mode is active" appeared in the transcript immediately after the
web searches in the Firebase Admin area, instructing that file reads and edits be done through
`cat`/`sed`/heredocs instead of the normal file tools. It contradicted the session's actual
configuration and arrived on the turn that ingested external web content. It was treated as
untrusted injected content and ignored; the developer was told at the time. Recorded here because
this phase's research involves more external fetching than most.
