# Phase 40: POST /auth/upgrade-anonymous - Context

**Gathered:** 2026-09-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `POST /auth/upgrade-anonymous` — the completion route for operation
`upgrade_anonymous_to_registered`. It records an upgrade that already happened on the client: the
app called Firebase's `linkWithCredential`, attaching a Google or Apple credential to the same
Firebase UID the anonymous account already used. The backend confirms that with Firebase Admin and
flips the existing `core.external_identities` row's provider in place — `anonymous` → `google`/
`apple`, assigning `provider_uid`, setting `users.registered_at`, and copying a verified email into
an empty slot. Same user row, same identity row, same purchase-attribution tokens, same grants. The
endpoint is also the idempotent repair path for an upgrade whose backend call was lost.

Prepare is served by the existing `POST /auth/challenge`, widened to issue for every challenge-
bearing operation (D-09, D-10).

`core.auth_operation` is shrunk to its four challenge-bearing values and the now-redundant
`auth_challenges` CHECK is dropped (D-11).

**Out of scope:** every backend rate-limit entry the brief names (`upgrade_anonymous_prepare`,
`upgrade_anonymous_to_registered_firebase_identity_lookup`, `adapter_firebase_lookup`) — the engine
was deleted from the product by Phase 35 D-05; the Envoy `gateway_rate_limits.upgrade_anonymous`
3/hour entry (v2.1 per Phase 35 D-08); any `audit.auth_events` row (the table, its writer and the
invariants requiring it were removed by Phase 37.1 D-01 and Phase 38 D-03); any grant creation,
flip, repair or rollover; any device-check, attestation or `restore_proof` handling; any new
identity row, historical marking, retire-and-attach, reverse flip or registered-to-registered
rebinding; any `display_name` population; any attribution-token regeneration; operator repair
tooling for a drifted row.

</domain>

<decisions>
## Implementation Decisions

### The target-provider declaration — removed

- **D-01: There is no client-supplied target provider. The server derives it solely from the
  Firebase Admin providerData read.** This is the direct continuation of Phase 37 D-12, which
  deleted create-user's `provider` declaration for the same reason, and it is the answer to the
  question Phase 37 D-13 flagged forward when it dropped `core.auth_challenges.operation_variant`.

  Consequences, all in scope:
  - **Brief steps 3 and 4 dissolve.** No REQUIRED `provider` field at prepare, no normalization, no
    persisted variant, and no byte-for-byte variant re-check at completion.
  - **`operation_variant` stays deleted.** No column returns; no migration change on this account.
  - **`NotLinked`'s bounded causes stay `empty | invalid-shape`.** The brief's third cause,
    `supported-provider-mismatch`, cannot occur — there is no declaration to mismatch. Phase 37 D-12
    removed it and this phase does not restore it.
  - The case matrix collapses to what the stored row and the live read say, with no third input.
  — **Reversibility:** one-way in principle (published request contract), cheap in practice —
  pre-launch, no clients.

- **D-02: A caller cannot distinguish a recoverable refusal from a terminal one, and that is
  deliberate.** The brief's client contract has the repair loop retrying "not linked yet" and
  stopping permanently on a binding conflict. Both answer an identical 403 `operation_not_allowed`
  with a one-field body, because the anti-oracle rule forbids differing bodies within one error
  class and a differing body here would let any token holder probe which provider accounts are
  already taken. The client derives the distinction from state it already holds: it compares its own
  SDK providerData against `/auth/sync` before calling, so if Firebase shows a registered provider
  and the backend keeps refusing, that is the terminal conflict and the client bounds its own
  retries. Operators tell the three apart in the structured log (D-05).

- **D-03: The wire models are shared with create-user.** `CreateUserRequest` is renamed to a
  neutral name (planner's call on the exact name) and both routes take it; `CompletionResponse` is
  reused unchanged. With D-01 the upgrade completion body is exactly `{challenge_id}` and the
  success body is exactly `{identity_provider}` — byte-identical to create-user's. Phases 41 and 42
  are also challenge-bearing completions and will want the same request shape. Two models that must
  stay identical are one model.

- **D-04: A repeat call that changed nothing answers identically to one that performed the flip** —
  200 with the same `{identity_provider}` body. No `changed` flag, no distinct status. The client's
  repair loop only needs to know the backend now reports the registered provider, and it stops when
  its own Firebase state and the backend agree; nothing needs to know which call did the work.
  — **Reversibility:** one-way in principle (published response contract), cheap pre-launch.

### The three refusals

Three distinct internal results, one identical client answer (403 `operation_not_allowed`):

| Case | Meaning | Recoverable? |
|---|---|---|
| Firebase still reports anonymous while the row stores `anonymous` | the client called before its own linking finished | yes — link, then call again |
| The stored row is registered and the live read disagrees (different provider, different uid, or anonymous) | stored data and Firebase have drifted apart | no — manual repair |
| The target `(issuer, provider, provider_uid)` is already held by another identity row | two accounts cannot share one provider account | no — manual repair |

- **D-05: Three separate exception classes, not one class with a field.** Case 1 reuses the existing
  `NotLinked` (cause `empty`). Two new classes are added for cases 2 and 3 — names are the planner's
  call, but they must snake-case to the brief's internal result names,
  `provider_transition_not_allowed` and `provider_account_already_linked`.
  `app/error_handlers.py::app_error_handler` writes `camel_to_snake(type(exc).__name__)` as the log
  event name, so distinct classes produce the brief's three distinct internal results with no extra
  field. Searching for "accounts needing manual repair" is then a match on two event names rather
  than a filter on a field value.

- **D-06: The two new refusals log our identity row id plus the stored and live provider names.**
  Enough to find the row and to know what kind of disagreement it was without opening a database
  session. Both provider values come from the three-member `IdentityProvider` enum, so neither is
  free text from Firebase. **The provider account uid is deliberately excluded** — it is the user's
  real identifier at Google or Apple, it is already on the row for whoever investigates, and putting
  it in a log line copies it into wherever logs are shipped and retained.

- **D-07: All three refusals log at WARNING.** Case 1 will be the most frequent and means nothing is
  wrong, and dropping it to INFO was offered and declined. Every refusal in the codebase logs at the
  `AppError` default; this phase does not introduce a second convention.

- **D-08: The already-taken case is found by catching the database's refusal, not by checking
  first.** A pre-check cannot answer without a race — two requests can both look, both see nothing,
  and one still fails at write time — so the catch is required regardless and a pre-check would be a
  second path saying the same thing, exercised only by a race that is hard to trigger in a test.
  **No constraint name is stored or compared and no error message is parsed.** `crud/identities.py`
  already catches `IntegrityError` and converts it without naming anything; the flip does the same.
  The only other constraint that statement can breach is the provider/provider_uid pairing CHECK,
  which can fire only if this phase's own code sets a contradictory pair — a bug, not a user
  conflict.

### Where prepare lives

- **D-09: Prepare is served by the existing `POST /auth/challenge`, not by a `?challenge=true` mode
  on this endpoint.** Phase 37.2 already replaced the spec's mode-signal partition with a dedicated
  issuance route and amended CREATE-01/02 to say so; `classify_mode_signal` does not exist in the
  codebase. `ChallengesDB.issue` already binds a linked caller to `bound_external_identity_id`,
  which is exactly the binding the brief's step 4 requires, so **the challenge store needs no change
  at all.**

- **D-10: A caller with no account asking for anything but create-user is rejected in the challenge
  handler, by one derived condition.** `/auth/challenge` is deliberately behind unnarrowed
  `Depends(get_identity)` so an unlinked caller can prepare create-user. The rule is: any operation
  other than `create_user` with `identity.identity is None` raises `PreAuthIdentityNotAllowed`.
  Create-user is the only operation an account-less caller may ever prepare because create-user is
  the only route in the application that admits unlinked callers — a fact already pinned in
  `tests/unit/test_app_wiring.py::PREAUTH_CALLABLE_PATHS` — so the condition stays correct for
  Phases 41 and 42 with nobody touching it.

  **Rejected, with reasons the planner should not re-litigate:**
  - *Putting the rule in `ChallengesDB.issue`.* The store knows nothing about what operations mean;
    moving the check there makes it learn that sign-up is special, which is a second copy of that
    fact in a second file.
  - *A per-operation admission table.* The user pushed back hard on anything requiring parallel
    lists to be kept in step. There is no route-path list anywhere in this design.
  - *Deriving the issuable set from FastAPI route metadata* — either `openapi_extra` on the
    decorator, or a marker decorator setting attributes read back through `route.endpoint`. **Both
    were verified working against live FastAPI**, and the pattern itself is ordinary (Django's
    `csrf_exempt`, Starlette's `requires`). Rejected because it configures one endpoint's behaviour
    from metadata attached to other endpoints, so a forgotten marker fails silently as an
    unexplained 400 rather than at the point you are reading; it needs a startup build step, an
    app-state stash, a dependency and a forgotten-marker test as permanent machinery; and
    `openapi_extra` additionally publishes the flag into `/openapi.json`. D-11 removes the need
    entirely.

- **D-11: `core.auth_operation` is shrunk to its four challenge-bearing values, so no issuable-
  operation list is written anywhere.** The membership test becomes `body.operation not in
  AuthOperation` — verified against the live enum with both a member string and a garbage string.

  The three dropped values (`sync`, `restore_subscription`, `sign_out_all`) existed only for
  `audit.auth_events`, which Phase 37.1 D-01 deleted; `core.auth_operation` now has exactly one
  consumer left, `core.auth_challenges.operation`, confirmed by reading the migration. The
  `auth_challenges` CHECK narrowing the type to four values becomes redundant — the type itself says
  it — and is dropped with them. Nothing in `tests/schema/test_constraints.py` names that CHECK.

  **Accepted cost:** for one phase each, a client can obtain a `claim_anonymous_grant` or
  `claim_registered_grant` challenge with no endpoint to spend it at. The handle expires in 300
  seconds, nothing can consume it, and D-10's condition still refuses an account-less caller. This
  was chosen over a two-entry issuable list because the user is optimising for fewer copies of the
  same fact to keep aligned, not for tidiness — a dead handle costs nothing, a list has to be
  maintained forever.

  **Fallout:** the enum definition and the CHECK in `migrations/20260818_01_initial-release.sql`,
  the members in `tables/auth.py`, and the three labels in
  `tests/schema/test_inventory.py::EXPECTED_ENUM_LABELS`. The single migration is edited in place
  and the dev/test database rebuilt — the same move Phase 37 D-13 made, and what SCHEMA-01 requires.
  — **Reversibility:** one-way (destructive schema change), cheap pre-launch.

### The flip itself

- **D-12: One crud method is the sole writer of both halves of the flip, backed by a schema-level
  test.** `users.registered_at IS NOT NULL` iff the identity's provider is google/apple is an
  invariant spanning `core.users` and `core.external_identities`, so no CHECK constraint can express
  it. One method issuing both writes inside the caller's transaction means no code path can write
  one without the other — the invariant is structural rather than asserted. A test in
  `tests/schema/` (asyncpg, outside the e2e rollback fixture) scans for rows in the third state,
  mirroring how `test_constraints.py` already covers the provider/provider_uid CHECK. Rejected: a
  runtime re-read and assertion, which costs a query per successful upgrade to check something the
  same transaction just wrote.

- **D-13: The verified email is copied only when the stored email is still NULL.**
  `auth/firebase.py::_verified_email` already returns the address only when it is non-empty and
  `emailVerified` is true, so the flip adds exactly one guard. A non-NULL stored value is never
  overwritten and a divergent live address is not a rejection — it is simply not copied. Everything
  comes from the same `getUser` response; nothing re-reads. `display_name` is never populated.
  This endpoint is the only path in the milestone that ever fills `core.users.email` for an upgraded
  account: create-user leaves it NULL for an anonymous signup, and Phase 39 D-01 ships it on
  `/users/me`.

- **D-14: The challenge is consumed on every outcome at or after the Firebase call, including
  `provider_not_linked`.** One rule — once the provider was called, the handle is spent — with no
  branch on which rejection occurred, so a handle can never be replayed to probe provider state.
  This matches what `services/auth.py::complete` already does for create-user. **Known cost,
  accepted:** the repair loop pays a fresh prepare round-trip on every retry, including the common
  "client called a moment early" case. Rejections *before* the Firebase call (challenge not found,
  identity mismatch, operation mismatch) neither claim nor consume, per the brief.

- **D-15: The identity and user rows are locked and revalidated at the top of the completion
  transaction, but this phase does not test that the lock blocks.** The challenge claim is already a
  single atomic conditional update that only one attempt can win, so two simultaneous upgrades on
  one account require two separately prepared challenges — and even then both would read `anonymous`
  and write identical values. A concurrency test in the schema suite was offered and declined: they
  are the slowest and flakiest kind, and here they would guard against writing the same values
  twice. Phases 41 and 42 create grants, where a lost update actually costs something; that is where
  one earns its keep. Dropping the lock entirely was also offered and declined — the safety argument
  depends on the challenge protocol staying exactly as it is, and the next reader would have to
  re-derive it.

### Where the logic lives

- **D-16: The upgrade completion is added to the existing `AuthService`, not given its own class.**
  Both endpoints run the identical sequence — locate the challenge, verify it belongs to the caller,
  claim it, commit the claim, call Firebase, write, spend the handle — and that sequence is the
  trickiest code on the auth path. Only the operation checked for and the write performed differ.
  A separate service would copy it; extracting a shared base was offered and declined as more
  refactoring of shipped code than this phase needs. Create-user's existing code is edited to make
  room, and `AuthService` grows to serve two endpoints.

- **D-17: No nested exception handling, and `try` blocks stay narrow.** Stated by the user directly
  when reviewing a sketch. A `try` contains only the statement that can raise — an ORM attribute
  assignment sends nothing to the database and does not belong inside one. Where a failure must be
  swallowed so the caller's rejection survives as the client's answer, the swallow goes in a small
  named function whose whole job is not raising, rather than a `try` nested inside an `except` at
  the call site. `services/auth.py` currently has such a nested block for create-user; **whether to
  clean that up is not decided and is not this phase's obligation** — the rule binds the new code.

### Testing

- **D-18: A real, permanently Google-linked Firebase account covers the successful flip.** One
  Firebase user has a Google credential attached by hand, once. Each test run mints a custom token
  for that UID through the Admin SDK and exchanges it for an ID token at the same Identity Toolkit
  REST endpoint `tests/e2e/conftest.py` already uses — **no per-run OAuth consent flow and no stored
  refresh token.** `firebase_admin.auth.create_custom_token` was verified present in the installed
  7.3.0. The ID token's `firebase.sign_in_provider` is irrelevant: nothing reads it, and
  `getUser` reports the Google entry regardless of how the caller signed in.

  The Firebase side is **read-only** for this test — the flip mutates rows in this database, not in
  Firebase — so the account is fixed test data rather than shared mutable state. The identity row is
  seeded fresh as `anonymous` per test, so the flip is repeatable indefinitely.

  **Two things the planner must schedule rather than discover:**
  1. **Someone creates the account by hand and records what it is** — the UID in config or `.env`
     plus a note on how it was made, or the next person cannot rebuild it.
  2. **Minting custom tokens needs signing rights.** With a real service-account key it works
     directly. `auth/firebase.py` currently uses Application Default Credentials, and if those
     resolve to a developer's own gcloud login rather than a service account, signing fails unless
     that principal holds token-creator permission. **Verify this early** — it is the most likely
     thing to make D-18 awkward, and it is the same gap as Phase 37 D-08 planning for a key in
     `.env` while the shipped code went with ADC.

  The test skips when the account is not configured, as `anonymous_firebase_credential` already
  does. Rejected: everything against the fake (nothing in the phase would ever call Firebase, so a
  shape mismatch would surface in production); one real refusal-path test only (offered as the
  cheaper option and declined in favour of real success-path coverage).

- **D-19: The scripted fake covers everything the real account cannot produce on demand** — the
  not-yet-linked refusal, the drift conflict, the already-taken conflict, and the idempotent repeat.
  `tests/e2e/conftest.py::scripted_firebase_adapter` already exists for exactly this, added by
  Phase 37. A second hand-made permanently anonymous account was offered for the refusal path and
  declined: the fake covers it identically and it would be a second piece of test data to document.

- **D-20: One e2e flow test proves roadmap criteria 3 and 4.** Upgrade, then call `/users/me` and
  `/auth/sync` and confirm both report the new provider, and read the purchase-attribution tokens
  either side of the flip and confirm they are identical. It drives the success path with the
  scripted fake, so it needs no hand-made Firebase account. `tests/e2e/test_flows.py` is the
  existing home. Both criteria hold by construction — the two read endpoints take the provider off
  the identity row the flip writes, and nothing in the flip touches `core.store_purchase_tokens` —
  but criterion 3 names two endpoints, so it is proven through the endpoints a client calls, not by
  reading rows.

### Documentation deliverables

- **D-21: Amend UPGRADE-01 and UPGRADE-02 in `.planning/REQUIREMENTS.md`** with a dated entry
  covering the three decisions new to this phase: D-01's removal of the client declaration and why;
  D-11's operation-enum shrink; and D-22's accepted Firebase exposure with its mitigating facts.
  Also state that the brief's rate-limit and audit obligations are already dead by earlier decisions
  (Phase 35 D-05, Phase 37.1 D-01, Phase 38 D-03), so a later reader does not treat the brief as
  unmet.

- **D-22: Record the accepted Firebase exposure explicitly.** Every completion makes one Firebase
  Admin `getUser`, including an idempotent repeat that changes nothing, and the brief forbids
  skipping it — the lookup is the only thing that detects a diverged binding, so skipping it on an
  already-registered row would let a corrupted row report success forever. With the rate-limit
  engine deleted (Phase 35 D-05) and the Envoy 3/hour limit deferred to v2.1 (Phase 35 D-08), a
  looping client can call it unbounded. **Accepted and flagged, as Phase 37 D-01 did for unlimited
  account creation.** Mitigating facts, for the record: the caller must already hold a valid token
  for an existing linked account, so this is one account looping on its own subject rather than a
  fan-out; the client contract says only call when Firebase state and backend state disagree; the
  exposure closes when the Envoy gateway contract lands. A narrow per-route limiter was offered and
  declined.

- **D-23: Note the enum shrink under SCHEMA-01.** D-11 edits the single migration in place and drops
  a constraint. Without a note, the next person diffing that file sees a schema shape that never ran
  on any machine and has nothing explaining why — the same reviewer-confusion cost Phase 37 D-13
  discharged with its own note.

- **D-24: Reword ROADMAP.md Phase 40 success criterion 2.** It reads "Prepare and completion modes
  both work"; prepare is a separate route here, not a mode on this endpoint. The criterion is still
  satisfied — the wording describes the design Phase 37.2 replaced.

- **D-25: `specs/auth-refactor-phases/05-upgrade-anonymous.md` is NOT edited.** The phase briefs are
  marked verbatim and every prior phase carried divergences in `.planning/REQUIREMENTS.md` instead.
  Editing this one would make it agree with the code at the cost of breaking that pattern for every
  other brief.

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `05-upgrade-anonymous.md` alone will try to build all of these. **None of them
exists.**

- **No `audit.auth_events` row, and nothing to write one with.** The table, its writer and every
  call site were deleted by Phase 37.1 D-01; Phase 38 D-03 struck § "Audit" from
  `SHARED-INVARIANTS.md` outright. The brief's completion step 11 and its entire audit hardening
  paragraph are dead. The "distinct internal results" obligation survives only in the structured
  log, which D-05 satisfies.
- **No rate limiting of any kind.** The brief names three backend entries and one Envoy entry.
  Phase 35 D-05 deleted the backend engine **from the product, not deferred** — `AGENTS.md`
  § Resilience states this and `limits` is absent from `pyproject.toml`. Phase 37 D-01 rejected a
  narrow per-route reinstatement and Phase 37 D-02 dropped the cross-request Firebase lookup
  budgets. The Envoy contract is v2.1 (Phase 35 D-08).
- **No `BudgetGate` and no `auth/budgets.py`.** Retired by Phase 37 D-04. The brief's step 5 budget
  ordering has nothing to sit on. The 3-attempt retry is `tenacity`, already built as
  `auth/firebase.py::lookup_with_retry`.
- **No mode-signal partition.** `classify_mode_signal` was deleted; Phase 37.2 amended CREATE-01/02
  to record that the prepare/completion partition is by route. D-09 follows it.
- **No route registry and no startup enumeration assertion.** `auth/registry.py` was deleted by
  Phase 37.1 D-06; Phase 37.5 turned the startup totality walk into a test. Route categorisation is
  carried by `tests/unit/test_app_wiring.py` alone. **Do not reintroduce anything registry-shaped**
  — see D-10's rejected alternatives.
- **No incremental migration file.** SCHEMA-01 and
  `tests/schema/test_apply_rollback.py::test_exactly_one_sql_file` both require exactly one; D-11
  edits it in place.
- **No new client-visible error code.** All three refusals answer the existing 403
  `operation_not_allowed`. D-05 adds two *internal* classes only. `ErrorResponse` stays one field.
- **No success log line.** `RequestLoggingMiddleware` already emits one `request` line per attempt;
  Phase 38 D-02 rejected a second and Phase 39 restated it.
- **No `provider_uid` mutation once set, no reverse flip, no registered-to-registered rebinding, no
  auto-rewrite of a divergent binding.** These are brief rules this phase implements, not decisions
  reopened here.

### Claude's Discretion

- **The names of the two new exception classes**, subject to D-05's constraint that they snake-case
  to `provider_transition_not_allowed` and `provider_account_already_linked`, and where they sit in
  the tree in `errors.py`.
- **The new neutral name for `CreateUserRequest`** (D-03), and whether the rename lands in its own
  commit ahead of the new route.
- **The crud method's name and signature** (D-12), and how the locked-and-revalidated rows reach it.
- **How the lock-and-revalidate query is issued** — one joined statement taking `FOR UPDATE` on both
  tables, or two ordered statements.
- **How `AuthService` accommodates the second completion** (D-16) — the internal shape is open, the
  constraint is that the shared sequence is not duplicated.
- **Test placement and depth**, within the existing `tests/unit` + `tests/e2e` + `tests/schema`
  split, and whether the enum shrink lands in its own commit.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding specification (overrides phase briefs on conflict)

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — binds every phase.
  Read § "Identity and ownership", § "The barrier", § "Fail-closed defaults", § "Locks and
  transactions" and § "Global deletions". § "Audit" was removed by Phase 38 D-03 and § "Rate limits"
  is dead per Phase 35 D-05. **This phase does not edit it.**
- `/home/init/native-speaker/specs/auth-refactor-phases/05-upgrade-anonymous.md` — the phase brief.
  Marked verbatim and **not edited** (D-25). Read the whole specification block, especially the
  completion-flow step numbering (which is the rejection precedence), the case matrix at step 8, the
  stranded-upgrade repair semantics, and the DELETIONS list. **Its steps 3 and 4 are dissolved by
  D-01, its step 11 and audit hardening are dead, and every rate-limit entry it names is dead** —
  read "Carried forward" above before implementing any of them.

### The source specification

- `/home/init/native-speaker/specs/auth-refactor/02-user-creation-and-anonymous-continuity.md` — the
  source the brief was cut from; the anonymous-to-registered continuity rules.
- `/home/init/native-speaker/specs/auth-refactor/06-schema-reference.md` — `external_identities`
  shape, the partial unique index on `(issuer, provider, provider_uid)`, and the provider/
  provider_uid pairing rule.

### Project planning

- `.planning/REQUIREMENTS.md` § UPGRADE (:233-236) — UPGRADE-01 and UPGRADE-02. **This phase appends
  its own dated amendments here** (D-21, D-22) and a note under SCHEMA-01 (D-23).
- `.planning/ROADMAP.md` Phase 40 (:533-543) — the four success criteria; criterion 2 is reworded by
  D-24.
- `.planning/phases/37-post-auth-create-user/37-CONTEXT.md` — **the closest precedent.** D-12 (the
  declaration removal this phase continues), **D-13 (the `operation_variant` removal that flagged
  this phase's provider-binding question forward)**, D-01/D-02 (rate limiting and the flagged
  exposure D-22 mirrors), D-04 (tenacity), D-07/D-08 (the Firebase adapter and its credential
  question, live again in D-18), D-09 (the real-versus-fake test split D-18/D-19 extend).
- `.planning/phases/38-post-auth-sync/38-CONTEXT.md` — D-01/D-03 (audit removal), D-02 (no success
  log), D-06 (`identity_provider` reads consistently across endpoints), D-08 (rate limiting absent).
- `.planning/phases/39-get-users-me/39-CONTEXT.md` — D-01 (the `/users/me` body D-20 asserts
  against), D-05 (the router-may-call-crud rule, now in `AGENTS.md`), D-06 (the `InternalError`
  subclass pattern), and its "Carried forward" list, most of which applies here unchanged.
- `.planning/PROJECT.md` § Constraints — the one-migration rule and the spec-authority rule. **Note
  it says Python 3.12; the environment runs 3.14.7.** Stale, not this phase's business.

### Repo conventions

- `ns-api-gateway/AGENTS.md` — § "Package layout" (a router may call `crud/` directly; a service is
  earned by complexity), § "Function shape", § "Comments and docstrings" (three-line docstrings,
  comments only to resolve genuine ambiguity), § "Resilience" (the `limits` engine is deleted, not
  deferred).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/dependencies.py::get_linked_identity` — the barrier this route needs. Already raises every
  admission rejection the endpoint owes: `InvalidExternalJwt` (401), `PreAuthIdentityNotAllowed`
  (403) for an unlinked caller, `HistoricalIdentity`/`BlockedUser` (403 `account_unavailable`),
  `IdentityUnresolvable` (500). **No admission error path needs building.**
- `crud/challenges.py::ChallengesDB` — `issue` already binds a linked caller to
  `bound_external_identity_id`; `locate`, `claim` (the single serialization point and the only
  expiry check), `consume`, and `verify_binding` (which compares the identity row id for a linked
  caller). **D-09 means this module needs no change at all.**
- `auth/firebase.py::lookup_with_retry` and `FirebaseAdminLookup.get_user_provider_data` — the
  mandatory `getUser` read, already retried three times through `tenacity`, already offloaded via
  `run_in_threadpool`, already failing closed to `Unavailable` (503) when the issuer selects no app.
- `auth/firebase.py::_resolve_provider` — the closed classifier: empty → anonymous, exactly one
  `google.com` → google, exactly one `apple.com` → apple, everything else raises `NotLinked` with
  cause `invalid-shape`. Reused unchanged.
- `auth/firebase.py::_verified_email` — already returns the address only when non-empty and
  `emailVerified`; D-13 adds only the stored-is-NULL guard.
- `services/auth.py::AuthService.complete` — the sequence D-16 extends, including the deliberate
  commit of the claim before the provider call and the rollback-then-consume path on rejection.
  **Note: no savepoint. `tests/unit/test_conflict_classification.py::test_the_inserts_open_no_savepoint_of_their_own`
  asserts `begin_nested` does not appear in the creation path.** Phase 37's CONTEXT said a savepoint
  would ship; it did not, and the shipped design is the one to follow.
- `crud/identities.py::insert_account` — the `except IntegrityError` → typed rejection pattern D-08
  copies, naming no constraint.
- `errors.py::NotLinked` / `ProviderLookupError` — case 1's existing class and the shared
  `stage`/`cause` shape.
- `app/error_handlers.py::camel_to_snake` — why D-05's class names *are* the internal result names.
- `tests/e2e/conftest.py::scripted_firebase_adapter` — the fake D-19 scripts;
  `anonymous_firebase_credential` — the real-signup fixture and the skip-when-unconfigured pattern
  D-18 follows.
- `tests/schema/test_store_purchase_tokens.py::_asyncpg_cause` and `_constraint_name_for` — proof
  the repo reads constraint names off the driver and asks the database for the live name, rather
  than parsing messages or hardcoding strings. Relevant only if D-08's catch ever needs narrowing.

### Established Patterns

- **Layering** (`AGENTS.md` § Package layout): handler in `routers/`, transaction boundaries and
  orchestration in `services/`, queries in `crud/`, bodies in `schemas/`, tables in `tables/`.
  `commit()`/`rollback()` live in `services/`.
- **One captured instant per request** — every service takes `evaluated_at=datetime.now(UTC)` from
  its dependency and nothing downstream reads the clock again.
- **No provider call while a database lock is held or a transaction is open.** The brief sequences
  this correctly: the Admin lookup runs strictly before the write transaction opens. Preserve that
  ordering literally.
- **Blocking I/O on the request path goes through `run_in_threadpool`.**
- **`Depends()` only in handlers**; all DI in `app/dependencies.py`.
- **Structured-log labels come from a closed set** — a fixed branch name, never raw provider text.
- **Docstring and comment bar is 0 by default** — three lines maximum, comments only where they
  resolve a genuine ambiguity.

### Integration Points

- `routers/auth.py` — `issue_challenge` gains the membership test and D-10's condition; the new
  completion route is added here (the router-level `Depends(get_identity)` is unnarrowed, so the
  route needs its own `get_linked_identity`, as `/auth/sync` does).
- `services/auth.py` — the second completion (D-16).
- `crud/identities.py` — the locking re-resolution and the flip method (D-12).
- `errors.py` — two appended classes (D-05).
- `schemas/auth.py` — the request-model rename (D-03).
- `tables/auth.py` + `migrations/20260818_01_initial-release.sql` +
  `tests/schema/test_inventory.py` — the enum shrink (D-11).
- `tests/unit/test_app_wiring.py` — `PUBLIC_PATHS` and `PREAUTH_CALLABLE_PATHS` are deliberate
  literals; `/auth/upgrade-anonymous` belongs in neither.
- `tests/e2e/test_flows.py` — the criteria-3-and-4 flow test (D-20).

### Naming Hazard

`IdentityProvider` (`anonymous`/`google`/`apple`) and `PurchaseProvider` (`apple`/`google_play`)
both use the value `"apple"` for different things. Keep them distinct at every seam; never derive
one from the other. D-20 reads both in the same test.

</code_context>

<specifics>
## Specific Ideas

- **The user makes the decisions, and options must be argued on their merits.** Said directly:
  "Would you take option 1 just because some rule doesn't allow something? I make the decisions, so
  stop justifying anything by some existing rule." Present what each choice costs and buys. An
  existing convention may be stated as context, never as the reason.
- **Duplication of the same fact across files is the thing to avoid**, and it drove three separate
  decisions here — D-10's rejection of an admission table, D-11's enum shrink over an issuable list,
  and D-03's shared wire models. The concern was raised as "I'm worried that I will have to keep 2
  lists (actually 3 with the database enum) in sync." Worth internalising: every enum in this repo
  currently exists in three places — the migration, the `tables/` mirror, and the hardcoded literal
  in `tests/schema/test_inventory.py` — and nothing mechanically checks the Python mirror against
  the database.
- **Plain English, with an introduction before the question.** Jargon-first framing was rejected
  outright mid-discussion: "I have no idea what you're talking about. At least make an introduction
  before asking." Terms like "stand-in" for a test fake were also called out.
- **Do not parse database error messages or maintain constraint-name strings.** Raised as a direct
  concern and answered by what the repo already does (D-08).
- **A code sketch answers a question and then stops.** Iterating on it, reviewing its style, or
  proposing refactors of shipped code is plan- and execute-phase work: "This is a discuss phase,
  you're not writing the code here."
- The two style constraints in D-17 came out of exactly that exchange and are the user's, not
  inferred.

</specifics>

<deferred>
## Deferred Ideas

- **One test asserting each Python enum's values equal its `core.*` database type's labels.** Would
  collapse three copies to two-plus-a-check for all ten enums at once, and would close the gap that
  nothing currently checks the `tables/` mirror against the database. Raised while deciding D-11;
  out of scope for Phase 40 because it touches every enum, not this one.
- **Cleaning up create-user's nested exception block** to match D-17. A one-line change to shipped,
  tested code; explicitly not decided here.
- **Operator tooling for a drifted row.** Two of the three refusals mean "a person must fix this,"
  and there is nothing to fix it with — the operator writes SQL. Out of scope for an endpoint phase.
- **A real Google-linked account for a genuinely registered create-user flow.** Phase 37 declined
  this as unreproducible shared CI state; D-18 creates exactly such an account, so Phase 37's
  registered-flow coverage could be revisited once it exists.
- **A second permanently anonymous Firebase account** for the not-yet-linked refusal path. Offered
  and declined (D-19) — the fake covers it identically.
- **`PROJECT.md` § Constraints says Python 3.12; the environment runs 3.14.7.** Stale doc, noticed
  while verifying enum membership behaviour. Not this phase's business.
- **Restoring rate limiting to the auth surface** — knowingly absent this milestone (Phase 35 D-05,
  Phase 37 D-01, Phase 38 D-08); the Envoy gateway contract is deferred to v2.1, and D-22's exposure
  closes with it.
- **Secret Manager integration** (`.planning/todos/pending/secret-manager-integration.md`) — D-18's
  service-account signing question touches the same credential handling this todo exists to fix.

### Reviewed Todos (not folded)

All four keyword matches reviewed; none touches an identity-flip endpoint:

- `admission-holds-a-db-connection` (score 0.6) — LLM admission and the quota charge.
- `breaker-check-moved-to-admission` (score 0.6) — LLM provider resilience.
- `message-ordering-is-unspecified` (score 0.6) — chats.
- `secret-manager-integration` (score 0.2) — config; reviewed and declined for the eighth
  consecutive phase, though D-18 gives it a new adjacency (see Deferred Ideas above).

</deferred>

---

*Phase: 40-post-auth-upgrade-anonymous*
*Context gathered: 2026-09-02*
