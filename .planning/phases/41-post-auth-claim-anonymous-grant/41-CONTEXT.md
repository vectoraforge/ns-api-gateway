# Phase 41: POST /auth/claim-anonymous-grant - Context

**Gathered:** 2026-09-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `POST /auth/claim-anonymous-grant` — the completion route for the challenge-bearing operation
`claim_anonymous_grant`, and the only code path that writes a `core.access_grants` row with
`source='anonymous_device_grant'`. One successful claim writes, in one locked transaction: the grant
row on the `anonymous` tier, its `core.access_grants_anti_abuse` row, its `core.user_monthly_usage`
row, and `external_identities.free_grant_consumed_at`. Prepare is the existing `POST /auth/challenge`,
which already issues for this operation (Phase 40 D-11).

**The device gate is Apple DeviceCheck only** (D-01): the app sends the device's one-time tokens, the
backend asks Apple whether the device's bit is already set, and sets it before activating the grant.
**Claimants are anonymous identities only** (D-08). There is no iOS app yet, so nothing can produce a
real device token today (D-04).

**Also in scope — two folded todos on the chat path** (D-14, D-15, D-16): the circuit breaker is
consulted before every attempt, the quota charge runs before the provider permit is taken, and the
database pool is raised to 12.

**Out of scope:** the Android Play Integrity branch and the web Cloudflare Turnstile branch of the
gate, with everything only they need — the Firebase providerData read on this route, the HMAC
`idp_account_hash`, `core.provider_accounts` and `core.provider_account_gate_consumptions` writes,
the `verification_required` error code (all deferred to another milestone); registered claimants;
every rate-limit entry and vendor budget the brief names; any `audit.auth_events` row; a
`?challenge=true` mode on this endpoint; any dev or simulator bypass; anything of Phase 42 (the
registered grant and its supersession of an anonymous one); schema changes — **none are needed**.

</domain>

<decisions>
## Implementation Decisions

### The device gate

- **D-01: iOS DeviceCheck only. Android and web are deferred to another milestone.** The developer
  first chose to build all three branches, then reversed within the same discussion. The brief scopes
  all three into this phase; nothing for any of them exists in the code, and the anti-abuse schema
  already carries every column all three need, so the deferred branches slot in beside the iOS
  adapter later without a migration. **FLAGGED CONFLICT** against `06-claim-anonymous-grant.md`
  § Scope and completion step 6 — recorded in `.planning/REQUIREMENTS.md`, not resolved (D-17).
  — **Reversibility:** reversible — adding a branch is new code beside the existing adapter.

- **D-02: With one branch, branch selection collapses to one body shape.** The completion body carries
  the challenge handle plus the two DeviceCheck tokens the brief requires — separate query and
  update tokens, each used once, the query token never reused for the update. No client platform
  field exists or is read. `native_claim_platform` is still written as `ios_devicecheck` at the first
  verified claim, immutable, so a later Android phase's other-platform rule has data to act on.

- **D-03: The database is checked before Apple is asked.** Order after the claim: the eligibility
  preflight (`free_grant_consumed_at` and the account's grant history) → Apple bit read → Apple bit
  write → the activation transaction. An account that cannot receive a grant never costs an Apple
  round trip; an already-claimed device answers `device_grant_exhausted` only for an eligible account.
  The check is repeated inside the locked transaction regardless. **FLAGGED CONFLICT** against the
  brief's steps 8–9 ("no DB grant may substitute for or suppress the platform-gate read").

- **D-04: No iOS app exists, so the suite drives the endpoint with a scripted fake DeviceCheck adapter**,
  a sibling of `tests/e2e/conftest.py::scripted_firebase_adapter`. The Apple adapter's
  request signing and response parsing get unit tests against Apple's documented shapes. The first
  real round trip to Apple happens when an app exists; that is recorded here as a fact, not a gap
  the phase can close. Confirmed by the developer.

- **D-05: Apple's credentials live in `.env`** — key ID, team ID and the private key — beside `DB_*`,
  `JWT_*` and `OPENAI_API_KEY`, read by the same pydantic-settings loader through its nested
  delimiter. The key is a multi-line PEM, so it is stored base64-encoded or as a path to a mounted
  file; the planner picks. Never in `config.yaml`, which is tracked in git.

- **D-06: Rules from the brief this phase implements as written, listed so nobody re-derives them.**
  bit0 only, never bit1; never accept client-supplied bit values; the write is fail-closed and
  load-bearing (only Apple's explicit confirmation permits activation; any exhausted failure,
  timeout or ambiguity → `verification_temporarily_unavailable`, no grant); every claim performs its
  own read and its own write, no caching or coalescing; the Apple call is retried through `tenacity`
  three attempts total, mirroring `auth/firebase.py::lookup_with_retry`; once the claim is won,
  **every** outcome consumes the challenge — a preflight refusal, an Apple refusal, a write failure,
  a race loss, success — exactly as `services/auth.py` does after the Firebase call; pre-claim
  rejections (unknown handle, identity mismatch, operation mismatch) neither claim nor consume; raw
  tokens never reach a log, a row or an error message. A crash after a confirmed bit write and before
  commit burns the device slot with no grant — accepted and uncompensated, remediation is an operator
  `manual` grant.

### Who claims, and repeats

- **D-08: Anonymous identities only.** The route sits behind `get_linked_identity`; the handler or
  service then requires `identity.identity.provider is IdentityProvider.anonymous`. A registered
  caller (`google`/`apple`) is refused with the existing 403 `operation_not_allowed` and waits for
  Phase 42. Inside the transaction the identity row is re-read, and a row that flipped to registered
  in the window is refused the same way. **FLAGGED CONFLICT** against the brief, which admits
  registered native claimants and lets them burn the device bit for the same grant. Declined on the
  merits: one claimant class, and the grant means what its name says; the fallback the brief buys —
  a registered user whose Google or Apple account already spent its grant — is recorded under
  Deferred Ideas.

- **D-09: A repeat claim answers 200 with the same body as a fresh claim.** When the account already
  holds an *active* `anonymous_device_grant`, the preflight (D-03) returns before Apple is reached,
  nothing is written, and the response is the current entitlement (D-10). Two other states still
  refuse with 403 `operation_not_allowed`: a free grant that was consumed but is no longer active
  (revoked, expired or superseded — the lifetime rule), and an active grant of another source
  (subscription or manual — one active grant per user). This follows Phase 40 D-04 for the repeat
  upgrade. **FLAGGED CONFLICT** against the brief's "never idempotent success".
  — **Reversibility:** one-way in principle — a published response contract; cheap pre-launch.

### The response body

- **D-10: A successful claim returns exactly what `POST /auth/sync` returns** — `SyncResponse`
  unchanged: the six-field entitlement block plus `identity_provider`, which is always `anonymous`
  here and stays for the sake of one model. It is assembled after commit by the same read
  `services/sync.py::SyncService.read_entitlement` performs, taking no lock; the planner decides how
  that read is shared. The repeat (D-09) and the race loser (D-13) return the same body by
  construction. `Cache-Control: no-store`, as `/auth/challenge` and `/users/me` set it.
  — **Reversibility:** one-way in principle — a published contract; cheap pre-launch.

- **D-11: Two new client-visible error codes, both 403.** `proof_rejected` for device tokens Apple
  rejects or that are present but malformed, and `device_grant_exhausted` for a device whose bit is
  already set, with non-accusatory copy directing to the registered path and no device state in the
  body. `verification_required` is **not** added — nothing in this phase would raise it; it arrives
  with the web branch. `ErrorCode` grows from 16 to 18 and
  `tests/unit/test_error_registry.py::test_the_error_code_literal_equals_the_set_the_tree_carries`
  learns both. The new classes follow `ProviderLookupError`'s shape: bounded `stage`/`cause` log
  fields from a closed set, never provider text or a token.

### Proving the race

- **D-12: A live two-connection race in `tests/schema`,** modelled on `test_create_race.py`: two
  prepared challenges for one anonymous account, two attempts driven through the fake gate on
  independent connections. Asserts afterwards: exactly one grant row, one usage row, one anti-abuse
  row, `free_grant_consumed_at` set once, both challenges consumed, the loser answered 200 with the
  winner's grant. Phase 40 D-15 named this phase as where a concurrency test earns its keep.

- **D-13: The loser answers 200, as a repeat would.** For a first claim there is no grant row to lock,
  so the `FOR UPDATE` step locks nothing and the arbiter is the database: the unique indexes
  `ix_access_grants_one_free_grant_per_user_source` and `ix_access_grants_one_active_per_user` refuse
  the second insert. The `IntegrityError` is caught without naming a constraint or parsing a message
  (the `crud/identities.py::insert_account` pattern, Phase 40 D-08), the transaction rolls back, and
  the same path the repeat uses re-reads and returns.
  **Lock order, and a conflict inside the specification itself:** the brief's step 11 says "lock
  target user first, then the grant set"; `SHARED-INVARIANTS.md` § Locks says "never an account/
  user-row lock tier ahead of the grant locks". The invariants win: grant rows `FOR UPDATE` ascending
  by id, then their usage rows, and the identity and user rows are revalidated by a plain re-read or
  locked only after the grant locks. Recorded in REQUIREMENTS.md as resolved by precedence (D-17).

### The two folded todos

- **D-14: The circuit breaker is consulted before every attempt, not only at admission.**
  `CircuitBreaker.before_call()` runs at the top of each `attempt()` in `resilience.py::ainvoke` as
  well as in `admission()`. A request in flight when the breaker opens fails on its next attempt with
  the same 503 and `Retry-After` a new request gets, instead of spending the remaining attempts (about
  ninety seconds) against a dead provider. The `except (QueueFullError, CircuitOpenError): raise` at
  `resilience.py:147` becomes reachable again and stays. A request already charged is not refunded,
  which is already true when all three attempts fail. Closes `breaker-check-moved-to-admission`
  (37.5-REVIEW WR-02/WR-03).

- **D-15: The quota charge runs before the provider permit is taken.** `admission()` keeps the
  breaker check and the in-flight slot — both instantaneous, so an open breaker or a full queue still
  answers 503 having spent nothing. The semaphore that bounds concurrent provider calls moves into
  `ainvoke()`, around the whole retry loop. The charge therefore commits and releases its connection
  before the request waits for a permit, and a slow database no longer occupies a provider permit.
  `ChatService` is unchanged. `Admitted` is still minted only by `admission()`. The docstrings and the
  cases in `tests/unit/test_quota_seam.py` that say admission holds a permit are reworded; the
  twenty billing cases stay green in substance. Closes `admission-holds-a-db-connection`
  (37.5-REVIEW CR-01). Rejected: charging before admission (a 503 would have already paid, and the
  quota code deliberately has no refund path); widening the pool alone (fixes exhaustion, not the
  permit hold).

- **D-16: `db.pool_size` is raised from 5 to 12** — `resilience.pool_size × 2 + 2`, as STATE.md A-15
  computed: two connections per possible in-flight chat plus two spare. The two config values stay
  independent numbers; the relation is a comment, not code. Deriving one from the other was offered
  and declined. Closes STATE.md blocker A-15. The planner verifies how the value is set without
  breaking the `DB_*` env nesting (`config.py:25` holds the default; `config.yaml` declares no `db`
  block today).

### Documentation deliverables

- **D-17: Amend ANONGRANT-01 … ANONGRANT-03 in `.planning/REQUIREMENTS.md`** with dated entries
  covering: D-01 (iOS only, Android and web deferred), D-03 (database before Apple), D-08 (anonymous
  only) and D-09 (idempotent repeat) as **four new flagged conflicts** against
  `06-claim-anonymous-grant.md`; D-11 (`verification_required` not added, a consequence of D-01, not a
  conflict of its own); D-13's brief-versus-invariants lock-order conflict as resolved by
  `SHARED-INVARIANTS.md` precedence; and the brief's obligations that were already dead before this
  phase — every rate-limit entry and vendor budget (Phase 35 D-05), the audit row (Phase 37.1 D-01,
  Phase 38 D-03), the mode-signal partition (Phase 37.2), `claim_attempt_id` (Phase 37.4 D-03) and the
  HMAC keyring (Phase 37.4 D-11) — so a later reader does not treat them as unmet. Update the header's
  conflict count and the set-of-divergences count against whatever they read at planning time.
- **D-18: Reword ROADMAP.md Phase 41 success criterion 4.** "Prepare and completion modes partition on
  the mode signal with a server-determined branch" describes the design Phase 37.2 replaced; prepare
  is `/auth/challenge`, and the branch is iOS by construction. Same treatment as Phase 40 D-24.
- **D-19: `06-claim-anonymous-grant.md` is NOT edited.** The briefs are verbatim; divergences live in
  REQUIREMENTS.md.
- **D-20: Record the Apple exposure explicitly,** as Phase 40 D-22 recorded the Firebase one: with no
  rate limiting on the auth surface, an eligible token holder can make the backend call Apple as
  often as it can prepare challenges. Mitigating: one account looping on itself, and the preflight
  (D-03) refuses ineligible accounts before Apple; closes with the v2.1 gateway contract.
- **D-21: Close the two todo files** the way the repo records a finished todo, note A-15 closed in
  STATE.md, and align `AGENTS.md` § Resilience with D-14/D-15 where its wording no longer matches.

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `06-claim-anonymous-grant.md` alone will try to build all of these. **None exists.**

- **No rate limiting and no vendor budgets** — `claim_anonymous_grant_prepare`, `claim_anonymous_grant`,
  their `_ip` twins, `adapter_devicecheck_read/write`: the backend engine was deleted from the product
  (Phase 35 D-05); the brief's four "budget exhausted" internal results have nothing to sit on. The
  Apple call is bounded only by `tenacity`.
- **No `audit.auth_events` row** — table, writer and invariant are gone (Phase 37.1 D-01, Phase 38
  D-03). The brief's "internal audit result" values survive only as structured-log event names,
  produced by exception class names through `app/error_handlers.py::camel_to_snake`.
- **No `?challenge=true` mode and no `classify_mode_signal`** — prepare is `/auth/challenge` (Phase
  37.2; Phase 40 D-09).
- **No route registry, no `BudgetGate`, no `auth/budgets.py`** (Phase 37.1 D-06, Phase 37 D-04).
- **No `claim_attempt_id`** (Phase 37.4 D-03): consume is `claimed_at IS NOT NULL AND consumed_at IS NULL`.
  A transient commit failure is not retried under an attempt identity; it surfaces as the ordinary
  failure and leaves the challenge claimed and dead, as it does for create-user and upgrade.
- **No HMAC keyring** (Phase 37.4 D-11) — only the deferred web branch needed one.
- **No incremental migration, and no migration edit at all this phase.**
- **No success log line** (Phase 38 D-02). **No Firebase read on this route** — the stored provider
  is the sole classifier and D-08 admits only anonymous rows.
- **No new HTTP status.** Both new codes answer 403.

### Claude's Discretion

- **The DeviceCheck seam:** its module in `auth/` (an external-SDK seam beside `firebase.py`), the
  Protocol defined beside this first implementation (FOUND-08's forward-flag treatment), the HTTP
  client (`httpx` is installed) and the ES256 signing (`PyJWT[crypto]` is installed). Which Apple
  environment the adapter targets is config; the brief says production only.
- **Missing or malformed tokens in the body:** default to required non-empty string fields, so an
  absent or empty token is the framework's 422 as a missing `challenge_id` is (Phase 40 precedent),
  and `proof_rejected` covers a present token Apple rejects. If that default stands, record the
  divergence from the brief's `proof_malformed → proof_rejected` under D-17.
- **How `AuthService` grows a completion whose post-claim work is not a Firebase read** — the shared
  locate-claim-commit-spend sequence must not be duplicated (Phase 40 D-16), but `_complete`
  hardwires `lookup_with_retry` between claim and write today.
- **The request model** carrying the handle and the two tokens, and its name.
- **The crud writer** for grant, anti-abuse row, usage row and marker — one method in `crud/grants.py`
  is the natural home — and the `AccessGrantAntiAbuse` SQLModel, which does not exist yet (its
  `registered_account_grant_id` is GENERATED and stays unmapped like `AccessGrant`'s four).
- **How the identity and user rows are revalidated inside the transaction** without a lock tier ahead
  of the grant locks (D-13).
- **Test placement and depth**, and whether the folded todos land as their own plan wave (they are
  independent of the endpoint and can run in parallel with it).

### Folded Todos

- **`breaker-check-moved-to-admission`** — an admitted chat request burns all retries against a
  provider the breaker already opened. Resolved by D-14.
- **`admission-holds-a-db-connection`** — the LLM admission gate holds a provider permit across the
  quota charge's database round trip. Resolved by D-15; its "consider relating the two pool sizes"
  note by D-16.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding specification (overrides phase briefs on conflict)

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — § "Identity and
  ownership", § "The barrier", § "Fail-closed defaults", § "Locks and transactions" (**wins over the
  brief's step 11 user-first lock**, D-13), § "Grants and evaluation time", § "Global deletions".
  § "Rate limits" is dead per Phase 35 D-05. **This phase does not edit it.**
- `/home/init/native-speaker/specs/auth-refactor-phases/06-claim-anonymous-grant.md` — the brief,
  verbatim and **not edited** (D-19). Read § Scope, "This phase adds", the completion flow (steps 4–12
  are the rejection precedence), the error-class list, the security hardenings and the DELETIONS
  list. **Its Android and web material is deferred (D-01), its steps 8–9 order is reversed (D-03), its
  registered claimants are refused (D-08), its "never idempotent success" is overridden (D-09), and
  every rate-limit, budget, audit, mode-signal and `claim_attempt_id` obligation is dead** — read
  "Carried forward" above before implementing any of them.

### The source specification

- `/home/init/native-speaker/specs/auth-refactor/03-free-credit-grants-and-anti-abuse.md` — § Anonymous
  Device Grant Anti-Abuse Layers (:113), § Branch Selection (:147), § Required Rules (:157), § Failure
  Handling (:213), § `POST /auth/claim-anonymous-grant` (:781), § `claim_anonymous_grant` (:875),
  § iOS Device-Check Adapter (:1153).
- `/home/init/native-speaker/specs/auth-refactor/05-proof-adapters-and-derived-identifiers.md` — § Raw
  Proof Material, Storage, and Redaction (:143), § Anonymous Device Grant Anti-Abuse Layers (:213),
  § iOS Proof Adapter (:275), § Claim Challenge Lifetime (:401). Skip the Android and web sections.
- `/home/init/native-speaker/specs/auth-refactor/00-overview-and-shared-contracts.md` § Common
  Completion Requirements (:418) — step 14, "return the resulting backend state", is what D-10 answers.
- `/home/init/native-speaker/specs/auth-refactor/06-schema-reference.md` — § `core.external_identities`
  (:579), § `core.access_grants` (:991), § `core.access_grants_anti_abuse` (:1127),
  § `core.user_monthly_usage` (:1297).
- `/home/init/native-speaker/specs/auth-refactor/07-quota-and-access-enforcement.md` § Effective
  Access Tier — the shared effective-grant predicate D-10's read applies.

### Project planning

- `.planning/REQUIREMENTS.md` § ANONGRANT (:267-271) — **this phase appends its dated amendments here**
  (D-17); read the header's amendment convention and the current conflict counts first.
- `.planning/ROADMAP.md` Phase 41 (:571-582) — the four success criteria; criterion 4 is reworded (D-18).
- `.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md` — **the closest precedent.** D-03
  (shared wire models), D-04 (the idempotent repeat D-09 follows), D-08 (`IntegrityError` caught
  without naming a constraint), D-09/D-10/D-11 (prepare on `/auth/challenge`), D-14 (consume on every
  post-provider outcome), D-15 (the race-test pointer), D-16 (`AuthService` grows rather than forks),
  D-17 (no nested `try`, narrow `try` blocks — binds new code here), D-19 (the scripted fake),
  D-21…D-25 (the documentation-deliverable pattern D-17…D-20 repeat), and its "Carried forward" list.
- `.planning/phases/39-get-users-me/39-CONTEXT.md` — D-05 (a router may call `crud/` directly), D-06
  (the `InternalError` subclass pattern), D-09 (`Cache-Control: no-store` via injected `Response`).
- `.planning/phases/38-post-auth-sync/38-CONTEXT.md` — D-06 (the entitlement block D-10 returns), D-07
  (fail-closed reuse of `MultipleEffectiveGrantsError` / `MissingUsageRowError` / `UnknownTierError`).
- `.planning/phases/37-post-auth-create-user/37-CONTEXT.md` — D-01 (the unlimited-exposure precedent
  D-20 follows), D-09 (the real-versus-fake test split).
- `.planning/STATE.md` § Blockers/Concerns — A-15 (the pool finding D-16 closes).
- `.planning/todos/pending/admission-holds-a-db-connection.md` and
  `.planning/todos/pending/breaker-check-moved-to-admission.md` — the folded todos, with their
  "scope when picked up" sections; their source is `37.5-REVIEW.md` CR-01, WR-02 and WR-03.

### Repo conventions

- `ns-api-gateway/AGENTS.md` — § "Package layout" (external-SDK seams live in `auth/`; a service is
  earned by complexity), § "Function shape", § "Comments and docstrings", § "Resilience" (to be
  aligned with D-14/D-15 where needed, D-21).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/dependencies.py::get_linked_identity` — the barrier; a route-level dependency as on
  `/auth/upgrade-anonymous` and `/auth/sync`. Every admission rejection already exists.
- `routers/auth.py` — the router; the new route is added here and the docstring's route count grows.
- `services/auth.py::AuthService._complete` — the shared sequence (locate, `verify_binding`, operation
  check, claim, **commit**, provider work, write, spend) with the rollback-then-`_consume_quietly` arm
  on `AppError`. **It hardwires `lookup_with_retry` between claim and write**; this phase's post-claim
  work is D-03's preflight, the Apple read, the Apple write and the activation transaction, with no
  Firebase read. No savepoint anywhere in the completion path (see Phase 40 code_context).
- `crud/challenges.py::ChallengesDB` — **no change.** It already issues for `claim_anonymous_grant`,
  binds a linked caller to `bound_external_identity_id`, and `claim` is the only expiry check.
- `crud/grants.py::GrantsDB` — `lock_effective_grants` and `lock_usage` carry the lock order;
  `read_effective_grants`, `read_usage` and `monthly_credits` serve D-10's response read. The grant
  writer does not exist yet.
- `crud/identities.py::lock_identity_and_user` — the revalidation query the upgrade uses; **it takes
  `FOR UPDATE` on identity and user rows and therefore cannot run ahead of the grant locks here** (D-13).
- `services/sync.py::SyncService.read_entitlement` — the exact read behind D-10's body.
- `services/quota.py::QuotaService.charge` — never mints a usage row; the claim must create it with
  `monthly_period = evaluated_at.strftime("%Y-%m")` and `monthly_used = 0`.
- `tables/grants.py` — `AccessGrant`, `AccessGrantSource.anonymous_device_grant`, `UserMonthlyUsage`,
  `AccessTier`; the tier seed is `anonymous = 10`. **`AccessGrantAntiAbuse` is not modelled**
  (Phase 36-03 noted it), and `tests/e2e/conftest.py::seed_grant` defaults to `source=manual` for
  exactly that reason.
- `tables/identities.py` — `NativeClaimProvider.ios_devicecheck`, `ExternalIdentity.native_claim_platform`,
  `ExternalIdentity.free_grant_consumed_at`: all mapped, all unwritten so far.
- `auth/firebase.py::lookup_with_retry` / `_exhausted` — the `tenacity` shape D-06's Apple retry
  mirrors; `auth/adapters.py` — the Protocol-beside-implementation pattern and
  `tests/unit/test_adapter_interfaces.py::TestNoProviderDependency`.
- `errors.py::ProviderLookupError` — the `stage`/`cause` log-field shape for the two new classes;
  `Unavailable` (503 `verification_temporarily_unavailable`) is reused for an exhausted Apple retry.
- `app/error_handlers.py::camel_to_snake` — why class names are the brief's internal result names.
- `tests/e2e/conftest.py::scripted_firebase_adapter` (:212) — the fake pattern for D-04's DeviceCheck
  fake; `anonymous_firebase_credential` (:80) — the real anonymous sign-in fixture.
- `tests/schema/test_create_race.py` (`_Harness`, `_Attempt`, `barrier_for`) — the two-connection race
  harness D-12 extends; `tests/schema/test_grant_locks.py` — the lock-order proof.
- `tests/unit/test_app_wiring.py` — `PUBLIC_PATHS` and `PREAUTH_CALLABLE_PATHS` are deliberate
  literals; the new route belongs in neither and gets the sync-style dedicated cases.
- **For the folded todos:** `resilience.py::admission` (:133-138), `ainvoke`/`attempt` (:140-169) with
  the unreachable `except` at :147; `services/llm.py::admission` passthrough (:32); `services/chats.py`
  admission blocks (:92-94, :116-118); `tests/unit/test_quota_seam.py` — six classes, twenty cases,
  the billing property D-15 preserves; `app/lifespan.py:34` (`max_overflow=0`) and `config.py:25`.
- Installed: `PyJWT[crypto]` (ES256), `httpx`, `tenacity`, `firebase-admin`. No Apple SDK exists or
  is needed — DeviceCheck is a signed HTTPS call.

### Established Patterns

- **Layering** (`AGENTS.md`): handler in `routers/`, transaction boundaries and orchestration in
  `services/`, queries in `crud/`, bodies in `schemas/`, tables in `tables/`, external-SDK seams in
  `auth/`. `commit()`/`rollback()` live in `services/`.
- **One captured instant per request** — `evaluated_at` from the dependency; nothing downstream reads
  the clock. The grant's `starts_at`, the usage row's period and the marker all take it.
- **No network call while a lock is held or a transaction is open** — the Apple read and write run
  strictly before the activation transaction opens.
- **Consume on every post-claim outcome; nothing consumes before the claim.**
- **Fail-closed reads raise their own rejection in `crud/`** (AGENTS.md exception 4).
- **Structured-log labels from a closed set** — a branch name, never a token or provider text.
- **Docstring and comment bar is 0 by default** — three lines, comments only for genuine ambiguity.
- **No nested `try`; a `try` holds only the statement that can raise** (Phase 40 D-17).

### Integration Points

- `routers/auth.py`, `services/auth.py`, `crud/grants.py`, `tables/grants.py` (anti-abuse model),
  `schemas/auth.py` (request model), `errors.py` (two classes), `auth/` (the DeviceCheck seam),
  `config.py` + `.env.example` (D-05), `app/lifespan.py` and `app/dependencies.py` (build and expose
  the adapter as `firebase_adapter` is), `tests/unit/test_app_wiring.py`, `tests/e2e/` (fake and
  cases), `tests/schema/` (the race).
- Folded todos: `resilience.py`, `tests/unit/test_quota_seam.py`, `config.py`/`config.yaml` (pool),
  `AGENTS.md` § Resilience, `STATE.md` A-15, the two todo files.

### Naming Hazard

Three things are called "apple": `IdentityProvider.apple` (Sign in with Apple), `PurchaseProvider.apple`
(the App Store) and Apple as the DeviceCheck vendor. Keep them apart at every seam; never derive one
from another.

</code_context>

<specifics>
## Specific Ideas

- **Plain English, every time.** The developer stopped the discussion twice over phrasing: "Plain
  English", and, on "free grant capped per account", "WTF does that mean?" Say what a thing does,
  not a label for it; introduce a mechanism in a sentence before asking about it. A phrase that hides
  the point ("capped per account" for "anyone can sign in anonymously again and claim again") is
  worse than a longer sentence.
- **There is no iOS app yet.** Stated flatly when a phone-based test was proposed. Plan against that
  fact; do not assume a client exists to exercise anything.
- **Decisions change mid-discussion and the last one stands.** "Build all three" became "iOS only,
  Android and web deferred" one question later. Record the final answer, keep the trail in the log.
- **Argue on merits, not rules** (Phase 40): an existing convention is context, never the reason.
- **Fewer copies of one fact** (Phase 40): D-10 reuses `SyncResponse` rather than minting a near
  twin; D-16 keeps two independent numbers with a comment rather than a derived value with a validator.
- **Brevity.** Short answers, kernel first.

</specifics>

<deferred>
## Deferred Ideas

- **The Android branch** — Play Integrity token verification plus Device Recall read and write;
  `android_play_integrity` already exists in `core.native_claim_provider`. Another milestone.
- **The web branch** — Cloudflare Turnstile siteverify, the Firebase providerData read on this route,
  the HMAC `idp_account_hash` and the `k_idp_account_vN` keyring Phase 37.4 D-11 deleted,
  `core.provider_accounts` and `core.provider_account_gate_consumptions` writes, the
  `verification_required` code. Another milestone. **Phase 42 inherits the keyring question first:**
  its anti-abuse row requires `idp_account_hash` NOT NULL by the table's CHECK.
- **Registered claimants on the iOS gate** — the brief allows it as a fallback for a registered user
  whose Google or Apple account already spent its grant. Declined (D-08); revisit with Phase 42.
- **A dev or simulator bypass of the gate** — moot until an app exists; the brief permits one only by
  non-production server config.
- **A real-device check of the Apple round trip** — when an iOS app exists.
- **Rate limiting the auth surface, including a per-attempt Apple call budget** — knowingly absent
  (Phase 35 D-05); the exposure in D-20 closes with the v2.1 gateway contract.
- **Deriving `db.pool_size` from `resilience.pool_size`** — declined (D-16).
- **One test asserting each Python enum's values equal its `core.*` type's labels** — still deferred
  from Phase 40.
- **Operator tooling for a burned device slot with no grant** — the brief's remediation is a `manual`
  grant; there is nothing to issue one with but SQL.

### Reviewed Todos (not folded)

- `message-ordering-is-unspecified` (score 0.4) — chats; unrelated.
- `secret-manager-integration` (score 0.2) — config; declined for the ninth consecutive phase. D-05
  adds one more private key to `.env`, so the adjacency grows.

</deferred>

---

*Phase: 41-post-auth-claim-anonymous-grant*
*Context gathered: 2026-09-02*
