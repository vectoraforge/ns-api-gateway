# Phase 37: POST /auth/create-user - Context

**Gathered:** 2026-08-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `POST /auth/create-user` — operation `create_user`, challenge-bearing, prepare mode plus
completion mode — as `02-create-user.md` defines it. It is the only route the barrier admits an
unlinked caller to. Completion links a backend-verified Firebase `(issuer, subject)` to one new
`core.users` row plus exactly one ACTIVE `core.external_identities` row and both purchase-attribution
tokens, in one transaction. Requirements CREATE-01 … CREATE-04.

`02-create-user.md` is unusually prescriptive — 88 lines of near-verbatim normative text with a
numbered rejection precedence, a closed classifier, and an explicit DELETIONS list. Most of what
would ordinarily be a gray area is already pinned there. The decisions below are the ones the spec
genuinely leaves open, plus the ones where Phase 35's overrides put the spec out of reach.

**Foundation already provides all of this — call it, do not rebuild it.** The scout confirmed each
against the source:

| Machinery | Where | State |
|---|---|---|
| Barrier, pre-auth admission, typed identity context | `auth/barrier.py`, `auth/context.py` | Done (35 D-01/D-02) |
| `classify_mode_signal()` — §02's exhaustive mode-signal partition | `auth/modesignal.py` | Done, unit-tested |
| `ChallengeStore.issue/locate/claim/consume/verify_binding` | `auth/challenges.py` | Done, e2e-tested |
| Audit writer, both modes, `details` shape, redaction | `auth/audit.py` | Done |
| HMAC keyring — one shared key for `actor_subject_hash` + `preauth_subject_hash` | `auth/keys.py` | Done (35 D-21) |
| Error registry, one response model, one handler | `errors.py` | Done (35 D-09/D-10) |
| `FirebaseAdminAdapter` Protocol + `ProviderDataResult`/`ProviderDataEntry` | `auth/adapters.py` | Interface only — **no implementation anywhere** |
| All eleven `core.auth_event_result` values this phase emits | `models/auth.py`, migration | Already in the enum |

**This phase adds:** the concrete Firebase Admin adapter (the first one in the codebase), the
closed providerData classifier, three new error classes, the `create_user` route + registry entry +
`AuthOperation` wiring, the prepare and completion handlers, and the consuming transaction.

**Out of scope:** every other `/auth/*` route, `GET /users/me`, the provider-callback routes, any
access-grant or usage-row creation (§02 step 10 forbids it outright — a new account has zero
entitlement until Phase 41/42), and the Envoy gateway contract (§9, still deferred per 35 D-08).

</domain>

<decisions>
## Implementation Decisions

### Rate limiting — none, and the spec conflict this creates

- **D-01:** **No backend traffic limiter ships on this route, in any form.** `02-create-user.md:28`
  and `:84` name two backend IP-keyed entries — `create_user_prepare` 10/min/ip and `create_user`
  10/min/ip — and call the gateway limits "required and load-bearing". Neither exists and neither
  will. Phase 35 D-05 deleted `§5` from the product outright and the developer reaffirmed it here
  without exception, explicitly rejecting a narrow per-route reinstatement. **This is a flagged
  SHARED-INVARIANTS conflict, recorded and not silently resolved.**

  **The consequence the planner must carry, stated plainly:** `POST /auth/create-user` is reachable
  by anyone holding any valid Firebase ID token — which anyone can mint by signing up — and it is
  rate-limited by nothing. Each completion costs one Firebase Admin call and creates one account.
  The mitigating facts, for the record: a valid token is still required, accounts carry no
  entitlement at creation (§02 step 10), and the v1.6 Helm chart's existing Envoy limits remain in
  place untouched. — **Reversibility:** costly — reinstating means the config schema, a counter
  backend, and named entries across phases 37–46.

- **D-02:** **Both cross-request Firebase lookup budgets are dropped.**
  `create_user_firebase_identity_lookup` (60/min, key `deployment`) and
  `create_user_firebase_identity_lookup_ip` (10/min, key client IP) are per-minute IP- and
  deployment-keyed — traffic limits written in budget vocabulary. They cannot sit on the per-request
  gate `budgets.py` provides and building something that could is what D-01 rules out. Of §02 step
  7's three-budget `check_all` list, only the retry budget survives.

- **D-03:** **`registration_temporarily_unavailable` is not registered.** §02 defines it as
  *Envoy-emitted* via response-override; the backend never raises it. Registering an unreachable
  class for a gateway contract that is not in this milestone is speculative structure. It lands in
  v2.1 alongside the Envoy work that emits it. Note this diverges from the D-07 precedent that kept
  `rate_limited` registered — deliberately, and the developer was shown that precedent before
  choosing. Phase 37 therefore registers **three** new classes, not four.

### Retry — tenacity replaces every hand-rolled loop

- **D-04:** **`auth/budgets.py` is retired and the Firebase retry is expressed with `tenacity`.**
  With D-02 removing the other two names, `BudgetGate`'s multi-name all-or-nothing charge protocol
  (150 lines: `check_all` / `charge_all` / `exhausted` / `_ordered_unique`) has exactly one name left
  and degenerates to "have I tried 3 times yet?" — which is `stop_after_attempt(3)`. §02 step 8's
  3-attempt budget on retryable causes, with `user_not_found` non-retryable and spending no budget,
  is a `retry_if_exception_type` predicate. Delete `auth/budgets.py` and `tests/unit/test_budgets.py`;
  `BudgetExhausted`'s mapping (internal `firebase_lookup_unavailable` → client
  `verification_temporarily_unavailable`) moves onto the tenacity exhaustion path and must be
  preserved exactly. **Phase 35 D-06 is superseded** — record it as such, since D-06 explicitly
  claimed phases 37/40/41/42 would import that seam. Same reasoning that retired the hand-rolled
  `RejectionCounter` in Phase 36 (commit 5f275c8). — **Reversibility:** costly — phases 40/41/42
  briefs reference the budget seam by name and will need the tenacity idiom instead.

- **D-05:** **`resilience.py:165-191`'s retry loop is converted to the same tenacity policy**, so the
  codebase has one retry idiom rather than two. The developer chose this over the narrower
  BudgetGate-only option.

  **Planner: this is the highest-risk item in the phase and it is not on the phase's own critical
  path.** That loop sits on `POST /chats`, the product's primary route, which Phase 37 otherwise
  never touches. It carries at least three non-obvious behaviors that a naive conversion will drop:
  `on_admitted` fires **at most once across every attempt** (`resilience.py:149-161` — the wrapper
  exists specifically so a retry cannot re-invoke it); transient-vs-permanent classification via
  `_is_transient_error` gates whether a retry happens at all; and `record_failure` must fire on
  provider failures but **not** on the non-provider path at `:176`. Treat existing behavior as the
  specification, convert under the existing tests, and give it its own plan and its own commit so it
  can be reverted without touching the endpoint. — **Reversibility:** reversible.

- **D-06:** **`uv lock` is run deliberately and its full output committed** in one dependency-scoped
  commit — the new `tenacity` direct dependency (it is present today only transitively via langchain,
  `uv.lock:1540`), the `1.5.0 → 1.6.0` project-version correction, and the `revision = 2 → 3`
  lockfile-format bump. This **closes D-35-05-A**, whose instruction was exactly "whoever next
  touches dependencies should run `uv lock` deliberately and commit the result on its own"
  (`35-foundation/deferred-items.md:60`). The working tree already carries the version and revision
  lines uncommitted. Note this narrows Phase 36 D-15, which held `uv.lock` unowned —
  `docker-compose.yml` stays unowned and untouched.

### The Firebase Admin adapter — the phase's largest unbuilt surface

Context: `firebase-admin>=7.3.0` is declared at `pyproject.toml:24` and imported **nowhere** in
`src/`. No service-account credential exists in any config file or `.env`. §02 requires exactly one
mandatory, fail-closed `getUser(subject)` providerData read immediately before the write
transaction, on **every** completion — anonymous and registered alike, no branch skips it.

- **D-07:** **`firebase-admin`, awaited through `starlette.concurrency.run_in_threadpool`.** Chosen
  after a web search the developer requested, which returned a clean negative: no async Firebase
  *Auth* admin client exists. `firebase-admin` is built on `requests`; async support landed for
  Firestore (v5.3.0) and messaging (`send_each_async`) but never for `auth`, and
  [firebase-admin-python#104](https://github.com/firebase/firebase-admin-python/issues/104) is still
  open. The one third-party async package,
  [`async-firebase`](https://pypi.org/project/async-firebase/1.3.4/), is Cloud Messaging only.
  Google's own documented workaround is executor offload, which is already this codebase's house
  rule — plan 35-12 pinned "any synchronous call on the barrier's request path that can perform I/O
  is awaited through `starlette.concurrency.run_in_threadpool` — never called inline." Rejected:
  Identity Toolkit REST over httpx, which is natively async and takes a per-call `timeout=`, but
  costs a new dependency for service-account token minting (`gcloud-aio-auth` or
  `google-auth[aiohttp]`, the latter dragging aiohttp in beside the httpx already in use) and makes
  you own the response parsing and error taxonomy.

- **D-08:** **Service-account credentials are inline JSON in the gitignored `.env`**, loaded with
  `credentials.Certificate(json.loads(...))`. No file mount, so the Helm chart needs only a plain
  Secret env var and local dev needs no path wiring. This keeps real key material out of
  `config/config.yaml`, which is tracked in git — the compromise 35 D-20 accepted for the HMAC keys
  and which the Secret Manager todo exists to undo. Rejected: `GOOGLE_APPLICATION_CREDENTIALS` /
  ADC, because SHARED-INVARIANTS forbids any ambient, default, or fallback client and ADC would
  silently pick up local gcloud user credentials in dev; and GKE Workload Identity, which is
  strictly better in production but cannot serve local dev or the e2e suite, so the `.env` path
  would have to exist anyway as a second code path.

- **D-09:** **Test coverage is split: real anonymous e2e, substituted adapter for everything else.**

  The scout found a blocker the planner must not rediscover: the existing e2e fixture
  (`tests/e2e/conftest.py:44-60`) signs a real Firebase user in with **email/password**, yielding
  `providerData == [{providerId: "password"}]`. §02 step 9's classifier is closed — empty →
  anonymous, exactly one `google.com` → google, exactly one `apple.com` → apple, **every other shape
  rejects**. So the existing fixture cannot drive a successful completion in either flow; it is a
  guaranteed `create_flow_mismatch`.

  - **Anonymous flow, for real.** Add a fixture minting a genuine anonymous Firebase user via
    Identity Toolkit `accounts:signUp` (the same REST idiom `conftest.py:49` already uses for
    `signInWithPassword`). Real token, real Admin lookup, genuinely empty providerData. This proves
    the SDK actually returns the shape the classifier expects — the assumption that otherwise fails
    silently in production.
  - **Registered flow and every rejection shape, substituted.** A fake `FirebaseAdminAdapter`
    returning synthetic `ProviderDataResult`s drives google, apple, both-providers, multiple-entries,
    unrecognized-provider, missing-uid, `user_not_found`, and retryable-failure. A real
    Google- or Apple-linked account cannot be scripted.

### The response body

- **D-10:** **A successful completion returns registration state only** — the classified
  `identity_provider`. §02 step 14 says only "return the resulting backend state" and pins no field,
  making this a genuine blank in an otherwise fully-specified route. Create-user reports what it
  actually did; entitlement state is `/auth/sync`'s job and is read there. Rejected: reusing the
  `/auth/sync` payload shape (`03-sync.md:44-48`) — for a new account every grant field is forced to
  null/none anyway, and it would have Phase 37 defining a contract Phase 38 owns. Cost, accepted:
  one extra client round-trip during signup. — **Reversibility:** one-way in principle (published
  response shape), cheap in practice — pre-launch, no clients.

- **D-11:** **The purchase-attribution tokens are not in the response.** They are minted eagerly in
  the create transaction on every branch per §02 step 10, but `PROJECT.md:20` already assigns
  surfacing them to the rewritten `GET /users/me` in Phase 39. One place surfaces them.

### The create-flow declaration — removed (spec amendment)

- **D-12:** **There is no client flow declaration. The server derives the account type solely from
  the Firebase Admin providerData classification.** A client asks to create a user; the account is
  created as whatever type Firebase reports. This **amends `02-create-user.md`**, which currently
  specifies an optional `provider` field at prepare (step 3, defaulting to `anonymous`, frozen as the
  challenge's immutable `operation_variant`), a REQUIRED byte-for-byte `provider` match at completion
  (step 6), and a declaration-match rejection at step 9. Consequences, all in scope for this phase:
  - **`create_flow_mismatch` is not registered**, and its mandatory `required_flow` field does not
    exist. This dissolves the one place §02 required a body shape the closed error registry forbids
    (`errors.py:49-52`, "Exactly one field -- do not add more"). `ErrorResponse` stays one field;
    Phase 35's registry contract is preserved intact, not reopened.
  - **Step 6's provider-variant check is removed** for `create_user`. `challenge_operation_mismatch`
    remains a live result for the other challenge-bearing operations.
  - **The closed classifier is unchanged**: empty → anonymous, exactly one `google.com` → google,
    exactly one `apple.com` → apple, every other shape (both providers, multiple entries,
    unrecognized, missing/empty uid) → reject. That rejection is an unclassifiable *account*, not a
    declaration mismatch, and still routes to `operation_not_allowed` via invalid-shape
    `provider_not_linked`.
  - **`provider_not_linked`'s bounded cause loses `supported-provider-mismatch`**; `empty` and
    `invalid-shape` remain.
  — **Reversibility:** one-way in principle (published request + response contract and a dropped
  column), cheap in practice — pre-launch, no clients.

- **D-13:** **The `core.auth_challenges.operation_variant` column is removed outright**, not made
  nullable. It exists only to freeze the declaration D-12 deletes, and it cannot be derived at
  prepare time — §02 step 8 pins exactly one Firebase Admin lookup, at completion, immediately before
  the write transaction. Requires a new migration dropping the column and rewriting the Ruling-9.8
  CHECK at `migrations/20260818_01_initial-release.sql:627-638`, plus `models/auth.py:127` and the
  `ChallengeStore.issue()` signature at `challenges.py:105,138`. Test fallout:
  `tests/unit/test_challenge_ids.py`, `tests/e2e/test_challenge_store.py`,
  `tests/schema/test_constraints.py`.
  - **Flagged forward, NOT this phase's to solve:** the same CHECK pins
    `upgrade_anonymous_to_registered` to `operation_variant IN ('google','apple')`. **Phase 40
    (`POST /auth/upgrade-anonymous`) loses its provider binding** and needs its own answer for how it
    binds the target provider. Phase 37 removes the column; it does not design Phase 40's
    replacement. The new CHECK must still be written so Phase 40's rows remain insertable.
  — **Reversibility:** one-way (destructive schema change), cheap pre-launch.
  - **FLAGGED CONFLICT — D-13's mechanism vs. SCHEMA-01. Resolved 2026-08-22 at plan 37-01 Task 1
    in favor of SCHEMA-01, recorded here rather than silently resolved.** D-13 above says the removal
    "requires a **new** migration". Two facts not visible when D-13 was written contradict that
    wording: (1) `REQUIREMENTS.md` SCHEMA-01 is shipped and checked, and reads "**no incremental
    migration files are added**"; (2) `tests/schema/test_apply_rollback.py::TestMigrationDirectory::test_exactly_one_sql_file`
    asserts `migrations/` holds exactly one `.sql` file and fails the moment a second appears — it
    exists precisely to enforce SCHEMA-01. **Resolution (option-a): the single initial migration
    `20260818_01_initial-release.sql` is edited in place and the dev/test database is dropped and
    re-applied.** Rationale: SCHEMA-01 is a locked, shipped requirement with a live test enforcing
    it, and the only thing a second migration file buys — an audit trail of a schema change — has no
    audience in a pre-launch repo with no deployed database (`37-RESEARCH.md` § Runtime State
    Inventory: zero `core.users` rows originate from `src/`; `tests/schema/` builds and drops a
    scratch database per session). **Consequences:** SCHEMA-01 survives unamended;
    `test_exactly_one_sql_file` stays green **unmodified** — if it ever fails, that is a real signal,
    not fallout to repair; the migration keeps reading as one from-empty apply, which every harness
    in the repo assumes. **Accepted cost:** the tracked migration is rewritten, so a reviewer diffing
    it sees a schema shape that never existed on any machine. Pre-launch with a disposable database,
    that cost is bounded to reviewer confusion, which this note discharges.

### Claude's Discretion

- **Race-loser durability mechanism — resolved by research, do not re-litigate.** §02 step 12 names
  three acceptable mechanisms. This CONTEXT originally defaulted to **consume-first conditional
  update**; `37-RESEARCH.md` **disproved it empirically**: an `IntegrityError` poisons the SQLAlchemy
  session, so the post-conflict `consume` and audit write both raise `PendingRollbackError` —
  violating step 12's "consumption + rejected audit row MUST survive the business rollback" and
  producing exactly the generic 500 step 12 forbids. `session.begin_nested()` was executed against
  live PostgreSQL 17.11 under the **exact** e2e harness config
  (`join_transaction_mode="create_savepoint"`) and works. The stated rationale for avoiding savepoints
  is therefore a non-issue. **Ship the savepoint around the business insert.** Whatever ships here
  becomes the reference phases 40/41/42 copy.
- **Testing success criteria 3 and 4.** Both need genuinely committed, concurrent transactions —
  a forced mid-transaction failure leaving no partial account, and two concurrent creates for the
  same `(issuer, subject)` yielding one account. The e2e harness wraps every test in one outer
  transaction with savepoint-joined sessions (`tests/e2e/conftest.py:93-115`), so "concurrent"
  sessions share one connection and neither criterion is expressible in it. Options the planner
  should weigh: a second escape-hatch fixture doing real commits with explicit cleanup, or pushing
  these two to `tests/schema/` which is asyncpg-based and already outside the rollback fixture.
- Issuer → named-app selection for the Admin client (SHARED-INVARIANTS forbids any ambient/default
  client, so an explicit issuer-keyed lookup that fails closed is required — its shape is open), and
  where the fixed 5–10s per-attempt timeout `adapters.py:14-20` mandates is configured on the SDK
  transport.
- Module layout for the concrete adapter and the classifier, and the names of the three new error
  classes' constants.
- Whether the prepare-mode handler and the completion-mode handler are one route function
  dispatching on `classify_mode_signal()` or two functions behind one registered route.
- What the structured security log records on each fail-closed branch.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Binding specification

- `/home/init/native-speaker/specs/auth-refactor-phases/02-create-user.md` — the phase
  specification. Lines 32-88 are verbatim normative text: the mode-signal partition (`:40-43`),
  prepare mode (`:45-50`), the 14-step completion flow whose numbering **is the rejection
  precedence** (`:52-66`), the error-class table (`:68-78`), and the security hardenings and
  DELETIONS list (`:80-87`). Read the whole file; it is 88 lines and nearly all of it is binding.
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — binds every phase and
  **wins over any conflicting phase brief**. Flag conflicts, never resolve them silently. D-01/D-02
  are flagged conflicts against its § Rate limits.
- `/home/init/native-speaker/specs/auth-refactor-phases/03-sync.md` `:44-48` — the `/auth/sync`
  response shape considered and rejected for D-10, and the endpoint the race loser and the
  `identity_already_linked` client are routed to. Phase 38 builds it.
- `/home/init/native-speaker/specs/auth-refactor-phases/01-foundation.md` §6 (challenge protocol),
  §7.1 (the Firebase Admin seam and its budget wiring) — what the foundation modules were built to.

### Project planning

- `.planning/REQUIREMENTS.md` `:55-58` — CREATE-01 … CREATE-04.
- `.planning/ROADMAP.md` — Phase 37 goal and its four success criteria. Criteria 3 and 4 are the
  ones the current e2e harness cannot express (see Claude's Discretion).
- `.planning/phases/35-foundation/35-CONTEXT.md` — D-01/D-02 (barrier, typed context, `evaluated_at`),
  D-05 (rate limiting deleted — the basis for D-01), **D-06 (budget seam — superseded by D-04)**,
  D-07/D-08 (`rate_limited` retained, Envoy deferred), D-09/D-10 (error registry), D-19 (session
  factory), D-20/D-21 (HMAC key material and the one shared key), D-23 (`auth/` layout).
- `.planning/phases/35-foundation/deferred-items.md` `:46-60` — D-35-05-A, the stale `uv.lock`, closed
  by D-06.
- `.planning/phases/36-rebind-pre-existing-routes/36-CONTEXT.md` — D-15 (`uv.lock` /
  `docker-compose.yml` held unowned; D-06 narrows the first half), and the precedent for retiring
  hand-rolled machinery in favour of a library.

### Current implementation

- `src/nativespeaker/api/auth/adapters.py` `:106-141` — the `FirebaseAdminAdapter` Protocol D-07
  implements, plus `ProviderDataOutcome` (`:47-61`), `ProviderDataEntry` (`:78-91`) and
  `ProviderDataResult` (`:93-104`). The shared adapter rules at `:14-20` (no provider call under a
  lock, fixed 5–10s per-attempt timeout, never leak provider text) are binding.
  `tests/unit/test_adapter_interfaces.py` fails if an implementation appears in this module — the
  concrete adapter goes elsewhere.
- `src/nativespeaker/api/auth/modesignal.py` — `classify_mode_signal(raw_query, body_challenge_id)`,
  returning `ModeSignal | None`. `None` is §02's `invalid_request`: no side effects, no audit row,
  no internal result. Already exactly what §02 `:40-43` describes.
- `src/nativespeaker/api/auth/challenges.py` — `CHALLENGE_TTL_SECONDS = 300`, `new_challenge_id()`
  (`:66`), and `ChallengeStore.issue` (`:107`) / `locate` (`:146`) / `claim` (`:161`) / `consume`
  (`:190`) / `verify_binding` (`:215`). `claim` is the single serialization point and holds the only
  expiry check in the protocol; `consume` clears `preauth_subject_hash` in the same statement
  because the table CHECK requires it. Read the docstrings — they encode §6 rules the handler must
  not re-derive.
- `src/nativespeaker/api/auth/registry.py` `:60` `_PREAUTH_CALLABLE_ROUTE` is already pinned to
  `("POST", "/auth/create-user")`, and `:52-58` already lists `create_user` as challenge-bearing.
  The new `RouteMetadata` entry goes in `REGISTRY` (`:66-88`); `assert_route_enumeration` (`:126`)
  enforces set-equality against the live router at startup, so the route and its declaration must
  land in the same commit.
- `src/nativespeaker/api/auth/budgets.py` — deleted by D-04. `BudgetExhausted` (`:53-73`) carries the
  `firebase_lookup_unavailable` → `VERIFICATION_TEMPORARILY_UNAVAILABLE` mapping that must survive
  the move to tenacity.
- `src/nativespeaker/api/resilience.py` `:139-191` — the loop D-05 converts. `:149-161` documents the
  once-only `on_admitted` contract; `:176` is the non-provider path that must not record a failure.
- `src/nativespeaker/api/errors.py` — where `identity_already_linked`, `create_flow_mismatch` (409,
  with its mandatory `required_flow` field) and `operation_not_allowed` are appended. Anti-oracle
  rule: within a class, body/status/copy identical across every triggering branch.
- `src/nativespeaker/api/models/auth.py` `:52-85` — every `AuthEventResult` value this phase emits
  already exists in the enum and in `migrations/20260818_01_initial-release.sql:98-131`. No enum
  change is needed.
- `src/nativespeaker/api/auth/context.py` `:82-93` — `RequestContext`, including the single captured
  `evaluated_at` and the attempt id. Never recompute either (35 D-02).
- `tests/e2e/conftest.py` `:44-60` (the email/password fixture that cannot drive a completion — see
  D-09), `:93-115` (the savepoint-joined rollback fixture that blocks criteria 3 and 4), `:49` (the
  Identity Toolkit REST call the `accounts:signUp` fixture mirrors).
- `config/config.yaml` `:34-40` — the `hmac` block whose active key derives `preauth_subject_hash`.
  Tracked in git by D-20's accepted compromise; D-08 keeps the Firebase key out of it.

### Stale — do not trust

- `.planning/codebase/*.md` — captured 2026-02-24, before the rename and the v1.4/v1.5/v1.6
  restructuring, and long before the v2.0 auth work. Read the source instead.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **The whole challenge protocol is built and tested.** `ChallengeStore` covers §02 completion steps
  3, 5 and 13 outright, and `verify_binding` covers step 4's pre-auth hash comparison including the
  cleared-hash case that must take the already-used rejection rather than a mismatch.
- **`classify_mode_signal()`** is §02 `:40-43` verbatim, already unit-tested
  (`tests/unit/test_mode_signal.py`).
- **`HmacKeyring.actor_subject_hash` / `actor_subject_matches`** — one shared key and one derivation
  helper (35 D-21). The handler never writes a `compare_digest` of its own.
- **The audit writer's in-consuming-transaction mode** is what §02 step 13 needs to write the audit
  row atomically with the consume and the mutation.
- **`tests/schema/helpers.py`** — `insert_user`, `insert_identity`, `insert_tier`, `insert_grant`
  against asyncpg, outside the e2e rollback fixture. Relevant to the criteria 3/4 harness question.

### Established Patterns

- **Zero raw `text()` SQL, ORM constructs only** (v1.6). The consuming transaction's inserts and the
  re-resolution query are SQLModel/SQLAlchemy constructs.
- **`Depends()`-only routes; all DI in `app/dependencies.py`** (v1.3). The handler takes
  `get_preauth_identity()` and `get_request_context()`, never `Request`.
- **HTTP metadata on exception classes, one data-driven handler.** The three new error classes need
  no handler changes — only registry entries. `create_flow_mismatch`'s mandatory `required_flow`
  field is the one shape that extends beyond the base body.
- **Blocking I/O on the request path goes through `run_in_threadpool`** (35-12). D-07 depends on it.
- **No provider call while a DB lock is held or a transaction is open** (SHARED-INVARIANTS § Locks).
  §02 sequences this correctly already: the Admin lookup at step 8 runs *before* the transaction
  opens at step 10. Preserve that ordering literally.

### Integration Points

- `auth/registry.py` — new `RouteMetadata(method="POST", path="/auth/create-user", ...)` with
  `preauth_callable=True` and `challenge_bearing=True`. It is the only route that may set the first
  flag (`:60`).
- `routers/` — a new module for the route; nothing existing is touched.
- `app/dependencies.py` — where the adapter and challenge store are exposed to the handler.
- `app/lifespan.py` — where the issuer-keyed Firebase app is initialized and where its credential
  loading fails closed at boot.
- `errors.py` — three appended classes.
- `pyproject.toml` + `uv.lock` — `tenacity` promoted to a direct dependency (D-06).

</code_context>

<specifics>
## Specific Ideas

- The developer's framing on the retry work was that a 3-attempt cap "sounds like function
  throttling that can be implemented without writing custom code" — the same instinct that retired
  the hand-rolled `RejectionCounter` in Phase 36. D-04 and D-05 follow from that instinct, not from
  a defect in `BudgetGate`, which is well-built for a job that D-02 removed.
- The `firebase-admin` transport decision was made *after* a search the developer asked for, and the
  search returned a negative: there is no async option. D-07 is a considered fallback to Google's own
  prescribed workaround, not a default.
- The e2e email/password fixture producing `providerData == [password]` is worth internalizing: it
  means the classifier's reject-everything-else arm is the arm the existing test infrastructure hits
  by default. A test that "passes" against that fixture is testing the rejection path.
- §02 step 10 creates no grant, so a brand-new account is immediately in the "no effective grant"
  state Phase 36 D-08 maps to `quota_exceeded` (429). Creating an account and then getting 429 on the
  first chat is correct behavior until Phase 41/42 ships, not a regression — the same caveat 36's
  context recorded.

</specifics>

<deferred>
## Deferred Ideas

- **`registration_temporarily_unavailable` and the Envoy gateway contract (§9 / FOUND-09)** —
  deferred to v2.1 per 35 D-08 and D-03 above. When it lands it brings the per-IP and
  deployment-wide create-user limits, the response-override 429 body, and the `xff_num_trusted_hops`
  pin. That is also when D-01's exposure closes.
- **Real Google- and Apple-linked Firebase test accounts** for genuine registered-flow e2e coverage.
  Rejected here as unreproducible shared CI state; worth revisiting if the substituted adapter ever
  drifts from the real SDK's providerData shape.
- **`docker-compose.yml`** — still modified in the working tree, still unowned, and explicitly not
  picked up by D-06. Phase 36 D-15 left it that way and nothing here changes that.
- **Secret Manager integration** (`.planning/todos/pending/secret-manager-integration.md`) — D-08
  puts a second real secret in `.env` rather than in tracked config, which is the right side of the
  line, but the todo's rationale now covers the Firebase service-account key as well as the HMAC
  keys.
- **Restore `with_structured_output(strict=True)`** — unchanged from Phase 36's deferred list; D-05's
  conversion of `resilience.py` touches the same LLM path and should not be conflated with it.

</deferred>

---

*Phase: 37-POST /auth/create-user*
*Context gathered: 2026-08-21*
