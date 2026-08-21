---
phase: 35-foundation
plan: 09
subsystem: audit-writer
tags: [sqlmodel, postgresql, jsonb, bytea, native-enum, structlog, asgi-middleware, redaction]

requires:
  - phase: 35-foundation
    plan: 06
    provides: "the §1.5 barrier, Reject carrying actor_issuer/actor_subject on every verified branch, and record_rejection as the one funnel a rejection already passes through"
  - phase: 35-foundation
    plan: 07
    provides: "auth/adapters.py and auth/budgets.py as Protocol-only seams, and the src-wide adapter-method scan this plan must not trip"
  - phase: 35-foundation
    plan: 08
    provides: "HmacKeyring.actor_subject_hash and active_version -- the one derivation this writer calls rather than reimplements"
provides:
  - "models.auth.AuthEvent -- the audit.auth_events table, the first model in this codebase outside the core schema"
  - "auth/audit.py: DETAILS_SCHEMA_VERSION, build_details, redact, AuditWriter"
  - "AuditWriter.write_standalone / write_in_transaction -- the §4.1 two modes over one row builder"
  - "the actor guard: a row the all-or-nothing CHECK would reject raises with a message instead"
  - "app.state.audit_writer and app.state.route_registry -- two new runtime state keys"
  - "the barrier's audited-path hook, gated only on the matched route carrying an operation"
  - "registry.lookup(method, path, registry) -- one resolution site, parameterised per request"
affects: [35-10, 35-11, 37-create-user, 39-profile, 41-idp-account, 43-webhooks]

actuals:
  tokens: 31442
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "Redacting by dropping keys rather than masking them, because the field name is sometimes the disclosure on its own"
    - "Substring key matching in a redactor, accepting deliberate over-redaction as the safe direction and pinning the resulting naming convention with a test"
    - "A positive control over the fields a record must still reconstruct, so a redactor that returned {} could not pass the drop cases"
    - "A guard that refuses to build a row a database CHECK would reject, so a caller contract error reads as a message rather than a constraint violation"
    - "Declaring a route with a path parameter in a test registry, because a template and a request path are byte-identical for a route without one"
    - "Asserting statement order and argument provenance on the AST, for properties an in-process ASGI transport cannot distinguish"

key-files:
  created:
    - src/nativespeaker/api/auth/audit.py
    - tests/unit/test_audit_writer.py
    - tests/unit/test_audit_details.py
    - tests/e2e/test_audit_writer.py
  modified:
    - src/nativespeaker/api/models/auth.py
    - src/nativespeaker/api/models/__init__.py
    - src/nativespeaker/api/app/lifespan.py
    - src/nativespeaker/api/auth/barrier.py
    - src/nativespeaker/api/auth/registry.py
    - tests/unit/test_auth_security.py
  deleted: []

key-decisions:
  - "The redactor matches key-name substrings and therefore over-redacts: `proof_families_checked` -- the metadata §4.4 itself asks `verification` to carry -- is dropped along with `restore_proof`. Kept, because under-redaction is a durable leak and over-redaction is not, and pinned with its own case so the resulting naming convention is discoverable from a failing test rather than from a field that silently vanished."
  - "`actor_provider` is NULL on every barrier rejection this phase can produce, including `historical_identity` and `blocked_user` where a stored provider does exist. `Reject` does not carry the identity row, and plumbing it through `auth/identity.py` is outside this plan's file list for a phase that writes zero production rows. §4.2's rule -- never fabricated, never from claims -- is what holds; Phase 37 owns the widening."
  - "The writer refuses to build a row the table would reject, in both directions of the all-or-nothing CHECK. The plan asked only for the missing-actor direction; an `invalid_external_jwt` row carrying an actor violates the same CHECK and means the caller invented one."
  - "`build_details` and `redact` coerce UUIDs and datetimes to strings. Left raw they reach the driver and fail the insert, which the writer's own failure rule would then swallow -- making a lost audit row the quiet outcome."
  - "`registry.lookup` gained a registry parameter rather than the barrier growing its own scan. Two resolution sites for one `(method, path)` is exactly the drift the registry exists to prevent."
  - "Task 2 ran no RED phase. It is a test-only task against a module task 1 had already shipped, so every case would have passed on first write and a green run would have proved nothing. Fifteen mutations were run against the shipped source instead."

requirements-completed: [FOUND-05]

coverage:
  - id: AU1
    description: "Exactly one audit.auth_events row per on-path attempt, written before the response returns"
    requirement: FOUND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_audit_writer.py::TestAnOnPathRejectionWritesExactlyOneRow (12 cases, every count asserted as exactly 1, never 'at least 1')"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_writer.py::TestTheBarriersAuditHook::test_the_row_is_written_before_the_response_is_sent -- AST statement order, because ASGITransport runs the whole app coroutine before the client sees a byte"
        status: pass
      - kind: other
        ref: "mutation B3 (audit after the response is sent) -> passed 963 before the AST pin, 1 failed after"
        status: pass
    human_judgment: false
  - id: AU2
    description: "A barrier rejection on an operation-carrying route produces one row whose result is invalid_external_jwt with all four actor columns NULL and the bounded reason in details.failure"
    requirement: FOUND-05
    verification:
      - kind: e2e
        ref: "::test_that_row_carries_no_actor_at_all; ::test_the_bounded_reason_is_in_details_failure; ::test_the_bounded_reason_is_absent_from_the_response"
        status: pass
      - kind: other
        ref: "live probe against the applied schema: the all-NULL row inserts and reads back (see The observed row, below)"
        status: pass
    human_judgment: false
  - id: AU3
    description: "A rejection whose token was verified carries all three actor fields, populated from the verified (issuer, subject) -- RESEARCH Pitfall 10"
    requirement: FOUND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_audit_writer.py::TestAVerifiedActorIsRecordedAsAKeyedHash (6 cases: unlinked, historical, blocked, the shared derivation, the raw subject absent, actor_provider NULL)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_writer.py::TestTheActorGuard (11 cases over the four results foundation emits, both directions of the CHECK, and both write modes)"
        status: pass
      - kind: other
        ref: "mutation B4 (admission rejections lose their actor) -> 6 failed"
        status: pass
    human_judgment: false
  - id: AU4
    description: "actor_provider comes only from the stored core.external_identities.provider column and is never fabricated or taken from claims, headers, or client input"
    requirement: FOUND-05
    verification:
      - kind: e2e
        ref: "::test_actor_provider_stays_null_when_no_identity_row_resolved"
        status: pass
      - kind: other
        ref: "mutation B10 (fabricate actor_provider=google) -> 16 failed"
        status: pass
      - kind: other
        ref: "`grep -n actor_provider src/` -- the column, the writer parameter, the guard, and a single `actor_provider=None` at the one call site; no assignment from a claim or a header exists"
        status: pass
    human_judgment: false
  - id: AU5
    description: "A route whose metadata carries operation = None writes no row at any outcome, and admission-phase rejections write none either"
    requirement: FOUND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_audit_writer.py::TestOffPathRequestsWriteNothing (9 cases: six foundation routes rejected, one served 200, a wrong-method 405, an unknown-path 404)"
        status: pass
      - kind: other
        ref: "mutation B1 (gate dropped) -> 6 failed; B2 (gate inverted) -> 27 failed"
        status: pass
      - kind: other
        ref: "live boot: app.state.route_registry is 8 entries and the set of declared operations is {None}"
        status: pass
    human_judgment: false
  - id: AU6
    description: "details top level is exactly {schema_version, context, verification, resolved, mutation, failure}, every subobject present and empty {} when unused"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_details.py::TestTheSixKeyShape (18 cases, incl. the seventh-key TypeError and the copy-not-alias rule)"
        status: pass
      - kind: e2e
        ref: "::test_details_round_trips_as_exactly_the_six_keys -- read back out of JSONB, so the table's six CHECKs accepted it"
        status: pass
      - kind: other
        ref: "mutation M3 (omit an empty subobject) -> 32 failed; M12 (shape guard off) -> 1 failed"
        status: pass
    human_judgment: false
  - id: AU7
    description: "Redaction runs before write and drops the full §4.4 list at any nesting depth; the public challenge_id never reaches a row while challenge_row_id does"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_details.py::TestRedactionDropsTheFullForbiddenList (159 cases: 53 key names x top level, two levels deep, and inside a list of objects)"
        status: pass
      - kind: unit
        ref: "::test_the_non_secret_challenge_row_id_survives_while_the_public_handle_does_not; ::TestRedactionKeepsWhatTheRowMustReconstruct (the positive control, 44 cases)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_audit_writer.py::test_redaction_runs_before_the_row_reaches_the_session -- a writer property, asserted on the object handed to the session"
        status: pass
      - kind: other
        ref: "mutation M1 (no recursion into mappings) -> 121 failed; M4 (fragments ignored) -> 127 failed; M6 (no recursion into lists) -> 59 failed; M14 (redaction skipped in build_row) -> 1 failed"
        status: pass
    human_judgment: false
  - id: AU8
    description: "No raw client address, device identifier, install identifier, or other stable per-client identifier is recorded -- only the client-IP bucket kind (the plan's prohibition)"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_details.py::test_the_client_ip_bucket_kind_survives_while_a_raw_address_does_not, and the parameterized clause covering client_ip / ip / ip_address / client_address / remote_addr / peer_address / x_forwarded_for"
        status: pass
      - kind: e2e
        ref: "::test_context_carries_the_route_template_and_the_bucket_kind_not_the_address; ::test_the_path_parameter_appears_nowhere_in_the_row"
        status: pass
      - kind: other
        ref: "mutation B11 (label with scope['path']) -> passed 963 until a parameterised audited route existed, then 2 failed"
        status: pass
    human_judgment: false
  - id: AU9
    description: "Standalone mode opens its own session from the factory passed in and commits; in-transaction mode takes the caller's session and does not commit"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_writer.py::TestTheStandaloneDurableMode (5 cases) and ::TestTheInTransactionMode (2, incl. both modes building the identical row)"
        status: pass
      - kind: e2e
        ref: "::TestTheRollbackStillIsolatesIt -- the row is visible to the test transaction and invisible to a second connection, which is the savepoint property stated as an assertion"
        status: pass
      - kind: other
        ref: "mutation M11 (write_in_transaction commits) -> 2 failed"
        status: pass
    human_judgment: false
  - id: AU10
    description: "An audit write failure is logged and the client still receives the outcome the attempt earned"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_writer.py::TestAFailedWriteNeverChangesTheOutcome (3 cases, incl. the log carrying no raw subject and no details)"
        status: pass
      - kind: e2e
        ref: "::TestAFailedAuditWriteNeverChangesTheOutcome -- an exploding session factory and a missing audit writer both still answer 401 auth_required"
        status: pass
      - kind: other
        ref: "mutation M13 (writer re-raises) -> 2 failed; B9 (barrier hook unwrapped) -> 1 failed"
        status: pass
    human_judgment: false
  - id: AU11
    description: "actor_subject_hash is derived through the shared keyring with its version recorded, never reimplemented locally"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_audit_writer.py::TestTheDerivationRunsThroughTheSharedKeyring (3 cases, incl. an AST assertion that audit.py imports no hmac, hashlib, base64, or binascii)"
        status: pass
      - kind: e2e
        ref: "::test_the_stored_hash_is_the_shared_keyrings_derivation -- the stored bytes equal keyring.actor_subject_hash(...) and satisfy actor_subject_matches"
        status: pass
      - kind: other
        ref: "mutation M10 (record key version 1 instead of the active one) -> 1 failed"
        status: pass
    human_judgment: false

duration: 28min
completed: 2026-08-21
status: complete
---

# Phase 35 Plan 09: The Audit Writer Summary

**`audit.auth_events` gets its table, its writer, its six-key `details` object and its redactor —
and the barrier gets the hook that fires on exactly one condition. Twenty-six mutations against the
shipped source; four survived the first pass and every one of them was a real hole, including an
audit row that recorded the request path instead of the route template.**

## Performance

- **Duration:** 28 min
- **Started:** 2026-08-21 07:40Z
- **Completed:** 2026-08-21 08:08Z
- **Tasks:** 3 of 3
- **Files:** 10 (4 created, 6 modified, 0 deleted) — 1,786 insertions, 25 deletions

## No production route in Phase 35 is on the audited attempt path

Stated plainly, because a later reviewer will otherwise read the zero production rows as a defect.

All eight routes the application registers declare `operation = None`, and `§8.2` puts them off the
path **permanently** — not pending, not deferred. A barrier rejection on `GET /`, `GET /examples`,
or any `/chats` route writes no `audit.auth_events` row and never will; it keeps its internal result
in the structured security log and increments the counter metric. Confirmed against the started
application:

```
$ # live boot
app.state.audit_writer   : AuditWriter(key_version=1)
app.state.route_registry : 8 entries; operations: {None}
```

The writer is therefore proven against a **test-local** app declaring `POST /auth/sync` with
`operation = AuthOperation.sync` and `POST /auth/claim/{grant_id}` with
`operation = AuthOperation.claim_registered_grant`. Phases 37–45 supply the real call sites. The
`app.state.route_registry` indirection exists for exactly this reason and for no other: without it
the audited-path branch is unreachable from anything, and an unreachable branch is an untested one.

## The observed row for the all-NULL actor case

Read back out of the live database, written by the real barrier over a real ASGI transport in
response to `POST /auth/sync` carrying no `Authorization` field:

```
result                        : invalid_external_jwt
operation                     : sync
actor_issuer                  : None
actor_subject_hash            : None
actor_subject_hash_key_version: None
actor_provider                : None
challenge_row_id              : None
created_at                    : 2026-08-21T08:0x:xx+00:00   (tz-aware)
details                       : {'schema_version': 1,
                                 'context': {'route': '/auth/sync',
                                             'method': 'POST',
                                             'operation': 'sync',
                                             'attempt_id': '0198f0d2-...',
                                             'client_ip_bucket_kind': 'unresolved'},
                                 'verification': {},
                                 'resolved': {},
                                 'mutation': {},
                                 'failure': {'stage': 'barrier',
                                             'reason': 'missing_token',
                                             'retryable': False}}
```

All four actor columns NULL — `actor_provider` included, which the CHECK requires and which is easy
to miss, since the spec sentence names three fields and the constraint names four. The client
received `401 {"code":"auth_required"}` and nothing else: `missing_token` appears in the row and in
the counter, and in no byte of the response.

The actor-bearing counterpart, for a verified subject with no identity row:

```
result                        : preauth_identity_not_allowed
actor_issuer                  : https://securetoken.google.com/test-project
actor_subject_hash            : 32 bytes, == keyring.actor_subject_hash(issuer, subject)
actor_subject_hash_key_version: 1
actor_provider                : None
```

## What stops the derivation drifting from the challenge store's

There is no second derivation to drift. `audit.py` imports no `hmac`, no `hashlib`, no `base64`,
and no `binascii` — asserted on the module's AST rather than by reading it, because the failure mode
is silent: a local reimplementation produces a plausible 32-byte digest, raises nothing, and only
one of the two candidates matches the rows already written. The one call is
`keyring.actor_subject_hash(actor_issuer, actor_subject)`, the same method plan 10 will call for
`preauth_subject_hash`.

## Task Commits

| # | Task | Commit | Type |
|---|---|---|---|
| 1 | Task 1 RED: failing tests for the writer, the table, and the actor guard | `718711c` | test |
| 2 | Task 1 GREEN: the AuthEvent table, audit.py, and the lifespan wiring | `9be4acf` | feat |
| 3 | Task 2: the details shape and every redaction rule, plus two redactor fixes | `75a5071` | test |
| 4 | Task 3 RED: the live-database audited-path matrix | `dee8811` | test |
| 5 | Task 3 GREEN: the barrier hook and the per-request registry seam | `2bc39ed` | feat |

Both TDD tasks ran a real RED. `718711c` failed at collection against the absent
`nativespeaker.api.auth.audit`; `dee8811` failed 16 of 31 cases against a barrier that wrote nothing
and a registry that lived only in a module. The 15 that passed in `dee8811` are the zero-row
invariants, which held vacuously then and hold meaningfully now — mutations B1 and B2 confirm they
are no longer vacuous.

## Test Status

| Suite | Before | After | Δ |
|---|---|---|---|
| Unit (`pytest -q`) | 489 | **782** | +293 |
| E2E (`pytest -q -m e2e`) | 76 | **113** | +37 |
| Schema (`pytest -q -m schema`) | 77 | **77** | untouched |
| Combined (`pytest -q -m ""`) | 642 | **972 passed, 0 failed** | +330 |
| `ruff check src tests` | clean | **All checks passed!** | |
| `ty check src` | clean | **All checks passed!** | |

`782 + 113 + 77 = 972`. Zero `xfail`, zero `pytest.mark.skip` — `grep -rn "xfail\|pytest.mark.skip"
tests/` returns 0 lines.

New modules: `test_audit_details.py` (258), `test_audit_writer.py` unit (35), `test_audit_writer.py`
e2e (37). `test_auth_security.py` is unchanged in count. The unit count is dominated by the
redaction matrix: 53 forbidden key names × three nesting shapes, plus a 44-case positive control.

## Decisions Made

- **The redactor over-redacts, deliberately, and the naming convention that follows is documented
  rather than discovered.** Key matching is on name substrings, so it cannot tell `restore_proof`
  (the artifact `§4.4` forbids) from `proof_families_checked` (the metadata `§4.4` asks
  `verification` to carry). It drops both. Under-redaction is a durable leak into an append-only
  table; over-redaction is a field a developer has to rename. The consequence — write
  `families_checked`, not `proof_families_checked`; `signature_algorithm` and `payload_bytes` go the
  same way — is stated in `audit.py` beside the fragment list and pinned by
  `test_metadata_named_after_a_secret_is_dropped_with_it`, so a later phase meets it as a failing
  test rather than as a field that silently vanished.
- **Keys are dropped, not masked.** A `"raw_token": "[REDACTED]"` entry still tells a reader which
  field was present, and for `challenge_id` the name is the disclosure. This is also what the plan's
  own acceptance probe requires: `'raw_token' in str(redact(...))` must be `False`, which masking
  would not satisfy.
- **`actor_provider` is NULL on every barrier rejection this phase produces.** For
  `historical_identity` and `blocked_user` a stored provider does exist and `§4.2` arguably permits
  recording it — but `Reject` carries only `(issuer, subject)`, and widening it means changing
  `auth/identity.py` and its 45 unit cases for a phase that writes zero production rows. What
  `§4.2` actually forbids — fabricating it, or taking it from claims, headers, or client input —
  holds absolutely: there is one `actor_provider=` at one call site and it is `None`. Phase 37 owns
  the widening, and the writer parameter is already there for it.
- **The actor guard checks both directions of the CHECK.** The plan asked for the missing-actor
  direction (Pitfall 10). An `invalid_external_jwt` row carrying an actor violates the same
  constraint and means the caller invented one from an unverified token, which is the more
  dangerous of the two errors.
- **`build_details` and `redact` coerce UUIDs and datetimes to strings.** `attempt_id` is a `UUID`
  and every later phase will want `evaluated_at` in `context`. Left raw they reach the driver and
  fail the insert — which the writer's own failure rule then swallows, making a lost audit row the
  *quiet* outcome. Coercion is the cheap insurance against exactly the failure mode `§4.1` exists to
  prevent.
- **`registry.lookup` took a registry parameter rather than the barrier growing its own scan.** Two
  places resolving one `(method, path)` is precisely the drift the registry exists to prevent. The
  default keeps the production path on the prebuilt index.
- **The counter in the e2e fixture is fresh per test, not the lifespan's.** The plan says to take
  app state from the started app so the rollback fixture governs; that reasoning is about
  `session_factory` and does not apply to an in-memory counter. A shared accumulating counter would
  have forced every count assertion into a before/after diff, which is weaker than an exact
  snapshot.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] The redactor did not drop `x_forwarded_for`**

- **Found during:** Task 2, writing the parameterized case for the plan's own prohibition.
- **Issue:** the prohibition reads "MUST NOT record the raw client IP address … or any other stable
  per-client identifier". `client_ip`, `ip_address`, `client_address`, `remote_addr` and
  `peer_address` were all caught by the `addr` fragment or an exact name — `x_forwarded_for` and
  `x_real_ip`, the two spellings an address most often arrives under, were caught by neither. A
  `details` object carrying either would have been written verbatim into an append-only table.
- **Fix:** added the `forwarded` and `real_ip` fragments. Both are covered by the parameterized
  clause for the prohibition, at all three nesting shapes.
- **Committed in:** `75a5071`.

**2. [Rule 2 - Missing coverage] Task 1 named no test file, and four of its behaviours need one**

- **Found during:** Task 1, choosing where the TDD RED commit goes.
- **Issue:** the plan marks task 1 `tdd="true"` but assigns `test_audit_details.py` to task 2 and
  `test_audit_writer.py` (e2e) to task 3, leaving task 1 with nothing to fail. Four of its stated
  behaviours belong to neither: the actor guard raising *before* the database, `write_in_transaction`
  not committing, a failed write not re-raising, and the derivation running through the shared
  keyring. None is reachable e2e — the guard fires before any statement is issued, and a real
  session cannot be asked to fail on demand without breaking the enclosing transaction.
- **Fix:** added `tests/unit/test_audit_writer.py` (35 cases) driving the writer against a recording
  stub session. It is also where the barrier hook's three AST pins ended up, so they run in the fast
  suite rather than only under `-m e2e`.
- **Committed in:** `718711c` (RED), `9be4acf` (GREEN), `2bc39ed` (the AST pins).

**3. [Rule 2 - Missing critical functionality] `details` had no shape guard**

- **Found during:** Task 1, writing `build_row`.
- **Issue:** the plan gives the writer an actor guard so the all-or-nothing CHECK produces a
  diagnosable message rather than a constraint violation. The six-key `details` shape is CHECK-ed
  the same way, by six separate constraints, and had no equivalent guard — a caller shipping five
  keys would have got a raw `CheckViolation` from inside a swallowed write, i.e. nothing at all.
- **Fix:** `_assert_details_shape`, raising with the same shape of message as the actor guard and
  naming `build_details()` as the fix.
- **Committed in:** `9be4acf`.

**4. [Rule 3 - Blocking] `auth/registry.py` needed the registry parameter**

- **Found during:** Task 3, wiring the per-request registry read.
- **Issue:** the plan lists `barrier.py` and `lifespan.py` but not `registry.py`. `lookup` resolved
  against a module-level `_INDEX` with no way to pass a different table, so the barrier would have
  had to grow its own scan — a second resolution site for one `(method, path)`.
- **Fix:** `lookup(method, path, registry=REGISTRY)`, keeping the prebuilt index on the default
  path. Its three existing callers are unaffected.
- **Committed in:** `2bc39ed`.

**5. [Rule 3 - Blocking] `tests/unit/test_auth_security.py` drives the barrier over a bare app**

- **Found during:** Task 3, first full run after the barrier read `state.route_registry`.
- **Issue:** the module builds a bare `FastAPI()` and supplies the three attributes the lifespan
  supplies. A fourth is now required, and 11 cases failed with `AttributeError`.
- **Fix:** `app.state.route_registry = ()`, which strengthens the module's own premise rather than
  merely satisfying it: `/probe` is now undeclared *to the app under test*, not just absent from the
  production table. `test_the_probe_route_is_undeclared` asserts against both tables.
- **Committed in:** `2bc39ed`.

**6. [Rule 3 - Process] Task 2 ran mutation verification in place of a RED phase**

- **Found during:** Task 2, choosing where its RED commit goes.
- **Issue:** task 2 is test-only against `auth/audit.py`, which task 1 shipped. Every case would
  have passed on first write; committing that as a RED gate would have been a false one, and the
  fail-fast rule makes a test passing before implementation a stop signal rather than a green light.
- **Fix:** wrote the module, then mutated the shipped source fifteen times. Two cases in the module
  failed on their first run and both were real defects in the code, not in the tests — see
  Deviation 1 and the over-redaction decision. The driving RED that TDD calls for is task 1's
  `718711c`, which failed at collection.

---

**Total deviations:** 6 — three Rule 2 gaps (a leak, a missing test home, a missing guard), two
Rule 3 blockers, one Rule 3 process correction. No Rule 1 bug was found in code this plan wrote
before its own tests ran, and no Rule 4 architectural question arose. Deviations 4 and 5 are one
consequence: this is the plan where the registry stops being a module-level constant.

## Issues Encountered

- **Twenty-six mutations; four survivors, all four real.** Coverage was verified by mutating the
  shipped modules, not inferred from a green run. Fifteen against `auth/audit.py`:

  | Mutation | Result |
  |---|---|
  | M1 — `redact` does not recurse into mappings | 121 failed |
  | M2 — `redact` mutates its argument | 1 failed |
  | M3 — `build_details` omits an empty subobject | 32 failed |
  | M4 — `_is_forbidden` ignores the fragments | 127 failed |
  | M5 — `_is_forbidden` is case-sensitive | 4 failed |
  | M6 — `redact` does not recurse into lists | 59 failed |
  | M7 — `_jsonable` coerces nothing | 1 failed |
  | M8 — the actor guard skips the `invalid_external_jwt` direction | 2 failed |
  | M9 — the actor guard checks the subject only | 4 failed |
  | M10 — the row records key version 1 instead of the active one | 1 failed |
  | M11 — `write_in_transaction` commits | 2 failed |
  | M12 — the `details` shape guard accepts anything | 1 failed |
  | M13 — a failed write is re-raised | 2 failed |
  | M14 — `build_row` skips redaction | 1 failed |
  | M15 — `build_details` aliases the caller's mapping | 3 failed |

  and eleven against `auth/barrier.py`:

  | Mutation | Result |
  |---|---|
  | B1 — audit every rejection, gate dropped | 6 failed |
  | B2 — gate inverted | 27 failed |
  | B3 — audit *after* the response is sent | **passed 963** → pinned, then **1 failed** |
  | B4 — admission rejections lose their actor | 6 failed |
  | B5 — `record_rejection` removed | 7 failed |
  | B6 — the bounded reason also lands in `context` | **passed 963** → covered, then **1 failed** |
  | B7 — `created_at` is a fresh `now()`, not the capture | **passed 963** → pinned, then **2 failed** |
  | B8 — registry read from the module, not app state | 22 failed |
  | B9 — the audit call is unwrapped | 1 failed |
  | B10 — `actor_provider` fabricated | 16 failed |
  | B11 — the recorded route becomes `scope["path"]` | **passed 963** → covered, then **2 failed** |

  Each mutation's anchor was confirmed present before its result was read, and the source was
  asserted byte-identical after every restore. Two of the first-pass "mutations" (M3 and M11) were
  bad anchors that added dead code rather than changing behaviour; they were rewritten and re-run
  rather than counted as caught.

  **B11 is the one worth reading.** The audited route in the first draft of the e2e module was
  `POST /auth/sync` — which has no path parameter, so `meta.path` and `scope["path"]` are
  byte-identical and `context["route"] == "/auth/sync"` passed either way. Labelling the row with
  the request path would have put caller-influenced ids into an append-only table for good, which
  is the same concern plan 06 hit for the counter label and the same concern this plan's own
  prohibition names. The fix was a second audited route carrying `{grant_id}`, plus an assertion
  that the id appears **nowhere** in the row. A route without a parameter cannot test a template.

  **B3 and B7 are properties no input can distinguish.** `ASGITransport` runs the whole application
  coroutine before the client sees a byte, so a row written after `await response(...)` is
  indistinguishable from one written before — yet `§4.1` says "before the response is returned", and
  the difference is a lost row on any disconnect between the two. Likewise `datetime.now(UTC)` and
  the request's captured `evaluated_at` differ by microseconds. Both are asserted on the AST:
  statement order inside `_reject`, and that the `created_at` keyword's value is the `evaluated_at`
  *name*. A positive control (`datetime.now` appears in `__call__` and nowhere else) keeps the
  second from passing vacuously — the first draft searched the source text and matched its own
  docstring, the same trap plan 08 recorded.

  **B6 was a hole in the assertion, not the code.** `test_audit_details.py` asserted the bounded
  reason lives only under `failure` — of the object `build_details` *returned*. Nothing asserted it
  of the row PostgreSQL *stored*, so a barrier that also copied the reason into `context` passed.
  The stored-row form is now parameterized over the four other subobjects.

- **`ruff`'s cache hid a real lint error for one commit's worth of time.** `ruff check src tests`
  printed `All checks passed!` while `ruff check --no-cache src tests` reported an unsorted import
  block, because the cached result predated the module the import referred to existing. Every lint
  gate in this plan after that point was run with `--no-cache`, and the final one is too.

- **No out-of-scope discoveries.** The two warnings in a combined run (`langchain_core` pydantic-v1
  on 3.14, PyJWT's `InsecureKeyLengthWarning` from `test_jwt_security.py`'s deliberate HS256 case)
  reproduce exactly as measured at baseline. Nothing was added to `deferred-items.md`.

- **Rollback isolation verified, not assumed.** `audit.auth_events` reports **0 rows** after the
  full suite, having had 37 e2e cases write into it. That is the operational proof that the writer
  reads its session factory per call rather than caching one — a cached factory would have written
  to the real database and left rows behind (Pitfall 5).

## Known Stubs

None. Every symbol this plan declares is implemented, wired into the running application, and
exercised against a real PostgreSQL.

Two things are deliberately unconsumed in production and are **not** stubs, because a stub is an
unfinished implementation and these are complete ones awaiting their caller:

| Item | State | Owner |
|---|---|---|
| `AuditWriter.write_in_transaction` | complete, unit-covered, both modes proven to build the identical row; no consuming transaction exists in Phase 35 to write inside | phases 37-45 (`§4.1`'s second mode) |
| The audited-path branch in the barrier | complete and e2e-covered against a test-local route carrying an operation; all eight production routes declare `operation = None` and `§8.2` keeps them there permanently | phases 37-45 (the routes that carry operations) |

`actor_provider` is the one field a later phase must widen rather than inherit: see Decisions Made.

## Threat Flags

None. This plan registers no production route, opens no network path, and adds no dependency
(`structlog`, `sqlmodel`, and `sqlalchemy` were all already present, so T-35-09-SC stays vacuous —
no package was installed). Every file it created or modified is covered by the plan's own
`<threat_model>`. All eight `mitigate` dispositions are implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-09-01 | `redact` runs inside `build_row`, before the row reaches any session, and drops 53 forbidden key names across the full §4.4 list at any nesting depth — through mappings, lists, tuples and sets. 159 parameterized cases at three nesting shapes, plus a 44-case positive control so a redactor returning `{}` could not pass. Mutations M1, M4, M6 and M14 confirm. |
| T-35-09-02 | Only `actor_subject_hash` is stored, with its key version, derived by the shared keyring; `audit.py` imports no hashing primitive, asserted on its AST. The raw subject is dropped from `details` by name (`sub`, `subject`, `actor_subject`, `raw_subject`), absent from the failure log, and asserted absent from the whole stored row. |
| T-35-09-03 | The `challenge_id` fragment drops the public handle at any depth while `challenge_row_id` — which does not contain it — survives; both asserted in one case so the pair cannot drift. The writer takes `challenge_row_id` and has no parameter through which a public handle could arrive. It appears in no log line: `_log_failure` carries the row id, the result, the operation, a boolean, and the challenge **row** id. |
| T-35-09-04 | The prohibition. Only `_bucket_kind`'s three-valued output reaches `context`; the address is never carried by `RequestContext` either (plan 03). `addr`, `forwarded`, `real_ip` and the exact bare forms are all dropped, and `client_ip_bucket_kind` survives — asserted together, since a redactor that failed either way would look correct against the other. The route recorded is the registry template, never the request path (mutation B11). |
| T-35-09-05 | Every e2e count is `== 1`, never `>= 1`. The write precedes the response send, pinned on the AST because the transport cannot distinguish it (mutation B3). Entry depends only on `meta.operation is not None` — mutations B1 and B2 confirm the gate is load-bearing in both directions. |
| T-35-09-06 | `actor_provider` has exactly one call site in `src/` and it passes `None`; no assignment from a claim, a header, or client input exists. Mutation B10 (fabricate `google`) fails 16 cases. The guard additionally rejects any `actor_provider` on an `invalid_external_jwt` row, which the CHECK also forbids. |
| T-35-09-07 | Two layers. `AuditWriter` catches every database failure, logs `audit_write_failed`, and re-raises nothing; the barrier wraps the whole call so a missing writer or an absent factory cannot escape either. Proven e2e with an exploding session factory and with `app.state.audit_writer` deleted — both still answer `401 auth_required` with the identical body. |
| T-35-09-08 | `_assert_actor_consistency` raises before any database work, in both directions of the all-or-nothing CHECK, with a message naming the missing field and why it is known at that point. 11 unit cases across the four results foundation emits and both write modes. `_assert_details_shape` does the same for the six-key CHECK. |

`tests/unit/test_adapter_interfaces.py::test_foundation_calls_no_adapter_method_anywhere_in_src`
still passes: `audit.py` names none of the ten adapter methods, imports no provider SDK, and touches
only `collections.abc`, `datetime`, `enum`, `typing`, `uuid`, `structlog`, `sqlmodel`, and this
project.

## Next Phase Readiness

Ready. The writer is the single site every later phase writes audit rows through, and it is wired
onto `app.state` with both modes complete.

- **Plan 10** (challenge store) writes no audit row itself, but its results —
  `challenge_not_found`, `challenge_expired`, `challenge_consumed`, `challenge_identity_mismatch`,
  `challenge_operation_mismatch` — are `§4.5` values that phases 37+ will hand to this writer, all
  of which require the three actor fields. It should pass `core.auth_challenges.id` as
  `challenge_row_id` and never the public handle; `redact` drops the handle at any depth if one
  reaches `details` anyway.
- **Plan 11** writes the `auth/__init__.py` barrel. The four symbols to add from here are
  `DETAILS_SCHEMA_VERSION`, `build_details`, `redact`, and `AuditWriter`.
- **Phase 37** owns the first production route carrying an `operation`, and inherits three things:
  the audited-path branch fires the moment its registry entry declares one; `write_in_transaction`
  is waiting for its first consuming transaction; and `actor_provider` is the one field to widen —
  `Reject` would need to carry the resolved identity row for `historical_identity` and
  `blocked_user` to record the stored provider, which is a change to `auth/identity.py`.
- **Every phase writing `details`** must read the naming convention in `audit.py` beside
  `FORBIDDEN_KEY_FRAGMENTS` first. Metadata named after a secret is dropped with it:
  `families_checked`, not `proof_families_checked`.
- **`app.state.route_registry` is now the barrier's source of truth**, set by the lifespan before
  the `§2.3` assertion runs against that same object. A phase adding a route changes `REGISTRY` as
  before; nothing else moves.

## Self-Check: PASSED

- All four claimed created files exist on disk, and all six claimed modified files carry the claimed
  content.
- All 5 claimed commits are in `git log`: `718711c`, `9be4acf`, `75a5071`, `dee8811`, `2bc39ed`.
- `pytest -q -m ""` exits 0 at **972 passed, 0 failed**; `ruff check --no-cache src tests` and
  `ty check src` both print `All checks passed!`.
- Every acceptance criterion in the plan verified by direct execution: the six sorted `details`
  keys, `schema_version` `1`, `False x` for the redaction probe, `{'schema': 'audit'}`,
  `'route_registry' in getsource(M)` → `True`, `pytest -q -m e2e tests/e2e/test_startup_assertion.py`
  at 9 passed, and `pytest -q -m e2e tests/e2e/test_audit_writer.py` at 37 passed.
- `git diff --diff-filter=D --name-only` over this plan's five commits is empty — nothing was
  deleted.
- `migrations/` is untouched: this plan wrote no migration and altered none.
- `.planning/STATE.md`, `.planning/ROADMAP.md` and `uv.lock` are untouched, as instructed — the
  orchestrator owns the first two.
- Working tree carries no change outside this plan's file list: `docker-compose.yml`, `.gsd/` and
  `.planning/research/.cache/` were pre-existing, are untouched, and remain uncommitted.

---
*Phase: 35-foundation*
*Completed: 2026-08-21*
