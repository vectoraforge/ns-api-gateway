---
phase: 36-rebind-pre-existing-routes
plan: 05
subsystem: api
tags: [quota, fastapi-dependencies, row-locking, postgres, deadlock, audit, route-registry]

# Dependency graph
requires:
  - phase: 36-04
    provides: consume_quota complete (§8.4 steps 1-5), GrantsDB.lock_usage, seed_grant's full parameter surface, the usage_rows read-back helper
  - phase: 36-03
    provides: require_quota's own-session boundary, require_quota_create_chat as the wrapper template, registry condition 10 and its function-scope wrapper tuple, GrantsDB.lock_effective_grants
  - phase: 36-01
    provides: the four schema.helpers seeders and the AccessGrant / UserMonthlyUsage tables the lock test contends over
  - phase: 35-foundation
    provides: the barrier, the route registry and its startup enumeration assertion, the audited-path gate on meta.operation
provides:
  - require_quota_send_message — the second D-14 wrapper, declaring chat_id AND body so a malformed path segment 422s before the own-session commit
  - quota_checked=True on POST /chats/{chat_id}, and the two-element condition-10 wrapper tuple
  - tests/schema/test_grant_locks.py — the repo's first two-connection contention test; the enforcement mechanism for SHARED-INVARIANTS:33
  - the -k audit and -k malformed classes in tests/e2e/test_quota.py
  - TestOffPathRequestsWriteNothing at seven pairs — every pre-existing route that answers 401
affects: [38 auth-sync, 41 claim-anonymous-grant, 42 claim-registered-grant, 45 subscription grants]

actuals:
  tokens: 13400
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "A per-route quota wrapper declares every untrusted parameter the route takes -- body AND path -- because FastAPI's pre-dependency validation is driven by the dependency's own signature"
    - "Lock-contention testing with `SET LOCAL lock_timeout` rather than NOWAIT or asyncio.wait_for: deterministic, server-side, leaves the connection usable, and keeps lock modifiers out of statements that mirror production ones"
    - "A committed-seed fixture with try/finally teardown, used only where uncommitted rows would make the test pass vacuously"

key-files:
  created:
    - tests/schema/test_grant_locks.py
  modified:
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/routers/chats.py
    - src/nativespeaker/api/auth/registry.py
    - tests/unit/conftest.py
    - tests/e2e/test_quota.py
    - tests/e2e/test_audit_writer.py
    - tests/e2e/test_error_cases.py
    - tests/e2e/test_isolation.py

key-decisions:
  - "`require_quota_send_message` declares `chat_id: UUID` as well as `body: MessageRequest`. Mutation-probed: dropping only `chat_id` fails the malformed-path case and nothing else, so the second declaration is load-bearing rather than symmetric."
  - "The refusal cases are parametrized over both `(path, body)` pairs at class level rather than duplicated, so a route carrying the flag but missing its wrapper cannot pass by being tested only on the other one."
  - "`tests/schema/test_grant_locks.py` seeds with `source='manual'`. The helper's `anonymous_device_grant` default populates the generated `anti_abuse_required_grant_id`, whose DEFERRABLE FK fires **at commit** -- which the rest of the schema suite never reaches because it never commits."
  - "`lock_timeout` is set on both connections in the deadlock case, at 5s -- comfortably above PostgreSQL's 1s `deadlock_timeout`, so the detector always wins and a *missed* detection fails the case instead of hanging the suite. `deadlock_timeout` itself is left alone: it is superuser-only and a test that silently needs superuser breaks on the first runner that is not one."
  - "`tests/e2e/test_isolation.py::owned_chat` seeds a grant for STRANGER only. The owner never POSTs there; giving the stranger one is what keeps `test_cannot_post_to_other_user_chat` about ownership rather than about the allowance."

patterns-established:
  - "Mutation-probing a wiring change: three probes (drop both wrapper declarations, drop only `chat_id`, drop the contender's reverse-order lock) each fail exactly the cases they should, which is the evidence that a green suite alone does not supply."
  - "A committed-seed fixture is justified by naming the specific way the default rolled-back fixture would make the test pass vacuously, in the fixture docstring."

requirements-completed: [REBIND-01, REBIND-02, REBIND-05]

coverage:
  - id: D1
    description: "Both chat POSTs -- and only those two of the eight pre-existing routes -- carry a quota dependency and declare `quota_checked=True`; the other six serve unchanged (D-07)."
    requirement: REBIND-01
    verification:
      - kind: other
        ref: "registry probe -> `two flags, eight routes`; app-route probe -> `exactly the two POSTs` (set equality, so a third gated route or a fourth left ungated fails it)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestTheOtherSixRoutesConsumeNothing (6 cases) -- each of the other six driven with a grant seeded, `monthly_used` still 0"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py (9 passed) and a real `uvicorn` boot -> 200 from /health/ready: condition 10 guards both routes and the app boots"
        status: pass
    human_judgment: false
  - id: D2
    description: "None of the eight pre-existing routes writes an `audit.auth_events` row, including `POST /chats/{chat_id}` and including on a quota 429."
    requirement: REBIND-02
    verification:
      - kind: e2e
        ref: "tests/e2e/test_audit_writer.py::TestOffPathRequestsWriteNothing -- parametrize list extended from six pairs to seven (the eighth route, GET /health/ready, is public and answers 200)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestAQuotaRejectionWritesNoAuditRow (3 cases, -k audit) -- a 429 on either POST, and a served+charged request, all leave the count unchanged"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_audit_writer.py::TestTelemetryFiresEitherWay -- undisturbed, so the counter half of REBIND-02 still holds for barrier rejections"
        status: pass
    human_judgment: true
    rationale: "The no-row half is behavioural and unambiguous. The counter half is asserted for *barrier* rejections only -- whether REBIND-02's 'rejections' also covers the quota rejections this phase invented is the plan's flagged assumption, restated below and deliberately not resolved by fiat."
  - id: D3
    description: "A malformed request on either chat POST returns 422 and leaves `monthly_used` unchanged -- the quota dependency never ran, so no credit was burned (D-14)."
    requirement: REBIND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestAMalformedRequestIsNotCharged (3 cases, -k malformed) -- body omitting `phrase`, body omitting `message`, and a non-UUID path segment; `monthly_used` read back before AND after each"
        status: pass
      - kind: other
        ref: "mutation probe: removing both wrapper declarations fails 2 of the 3; removing only `chat_id` fails exactly the path case"
        status: pass
    human_judgment: false
  - id: D4
    description: "Under two real concurrent connections, a second transaction cannot take the grant row lock while the first holds it, and the reverse lock order is detected by PostgreSQL as a deadlock."
    requirement: REBIND-05
    verification:
      - kind: other
        ref: "tests/schema/test_grant_locks.py (4 cases, real asyncpg, two live connections): exclusion, release, reverse-order DeadlockDetectedError, fixed-order safe path"
        status: pass
      - kind: other
        ref: "mutation probe: removing the contender's usage-first lock leaves zero deadlock victims and fails the case, so the reverse order is what produces it"
        status: pass
      - kind: other
        ref: "module run twice consecutively, both 4 passed; `tests/schema` full suite 84 passed including the seeded-tiers case that detects a leaked row"
        status: pass
    human_judgment: false
  - id: D5
    description: "The follow-up route is charged exactly once per request, and its charge goes through the same shared resolver as the first route."
    requirement: REBIND-05
    verification:
      - kind: e2e
        ref: "tests/e2e/test_quota.py::TestASeededGrantIsAdmitted::test_the_follow_up_route_is_admitted_and_charged_exactly_once -- counter read between the two POSTs, 1 then 2"
        status: pass
      - kind: e2e
        ref: "TestNoEffectiveGrant, all 5 cases parametrized over both routes (10 cases): the same five ways a grant can be non-effective refuse the follow-up route identically"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-08-22
status: complete
---

# Phase 36 Plan 05: Both Chat POSTs Gated, and the Lock Order Proven Summary

**`POST /chats/{chat_id}` now carries the same gate as `POST /chats` — wrapper, flag and identity tuple in one commit — and the phase's two structural claims are tests instead of assertions: nothing on the audited path for any of the eight routes, and a grant-then-usage lock order that PostgreSQL itself enforces under two live connections.**

## Performance

- **Duration:** 12 min (first task commit to last)
- **Tasks:** 3 of 3
- **Files:** 9 (1 created, 8 modified)
- **Suite:** 1234 → **1258** passing (+24, no regression)

## Accomplishments

- **The pair is complete, and provably exactly a pair.** `require_quota_send_message`, the
  decorator dependency, the `quota_checked=True` flag and the condition-10 wrapper tuple landed in
  one commit — they have to, because condition 10 now fails boot on either direction of
  disagreement. The app-route probe asserts **set equality** with `{POST /chats, POST /chats/{chat_id}}`,
  so a third gated route or a fourth left ungated fails it, and
  `TestTheOtherSixRoutesConsumeNothing` drives each of the other six with a grant seeded and reads
  the counter back at 0.
- **D-14's second half is real, not symmetric.** The follow-up wrapper declares `chat_id: UUID` as
  well as `body`. Removing only `chat_id` fails exactly one case — `POST /chats/not-a-uuid` with a
  perfectly good body, which without the declaration returns 422 **and** burns a credit. That is a
  client with a typo draining a paying user's allowance one request at a time.
- **The audit-coverage gap is closed at seven pairs.** `POST /chats/{chat_id}` — one of the two
  quota-checked routes, and the pair the parametrize list had been missing — now sits alongside the
  other six. The eighth route, `GET /health/ready`, is public and answers 200, so it has no
  rejection to write a row for; the served-outcome case covers that side.
- **A quota 429 writes no audit row, and neither does a served, charged request.** True by
  construction (audited-path entry is gated solely on `meta.operation is not None`, and all eight
  entries leave it `None`), and now asserted — because criterion 3's "including on barrier
  rejection" left the quota rejection, which is *not* a barrier rejection, otherwise unproven.
- **The lock order stopped being a convention.** `tests/schema/test_grant_locks.py` is the repo's
  first two-connection contention test. Grant-then-usage against usage-then-grant produces exactly
  one `DeadlockDetectedError`; both transactions using the fixed order simply serialise. Phases 41,
  42 and 45 are required to copy `GrantsDB`'s statement order, and this is now the thing that makes
  that a fact about the database rather than a request in a docstring.
- **Every new proof was mutation-probed.** Three probes — drop both wrapper declarations, drop only
  `chat_id`, drop the contender's reverse-order lock — each fail exactly the cases they should and
  nothing else. The source was restored and verified clean against HEAD after each.

## Task Commits

1. **Task 1 (RED): failing cases for the gate on the follow-up route** — `b3cfe54` (test)
2. **Task 1 (GREEN): wrapper, decorator, flag, tuple, override and two repoints** — `754b660` (feat)
3. **Task 2: the audit gap and the D-14 malformed-request proof** — `651f20d` (test)
4. **Task 3: the two-connection lock-order test** — `f2d9d0a` (test)

## Files Created/Modified

- `src/nativespeaker/api/app/dependencies.py` — `require_quota_send_message`, and the seam banner
  widened to say that a wrapper declares every untrusted parameter its route takes, not only the body
- `src/nativespeaker/api/routers/chats.py` — `dependencies=[Depends(require_quota_send_message)]`
- `src/nativespeaker/api/auth/registry.py` — `quota_checked=True` on the follow-up entry, the
  two-element wrapper tuple, and the comment rewritten from "36-05 will add it" to why exactly two
  of the eight carry it
- `tests/unit/conftest.py` — the second `dependency_overrides` line, with the non-cascading reason
- `tests/e2e/test_quota.py` — `QUOTA_ROUTES` / `UNCHARGED_ROUTES`, `auth_event_count`,
  `TestNoEffectiveGrant` parametrized over both routes, the charged-exactly-once follow-up case,
  `TestTheOtherSixRoutesConsumeNothing`, `TestAQuotaRejectionWritesNoAuditRow`,
  `TestAMalformedRequestIsNotCharged` (39 cases, was 20)
- `tests/e2e/test_audit_writer.py` — the parametrize list at seven pairs, with the reason the eighth
  route is absent
- `tests/e2e/test_error_cases.py`, `tests/e2e/test_isolation.py` — two cases repointed onto a grant
  so they keep their own subjects (see Deviations 1)
- `tests/schema/test_grant_locks.py` — 4 cases, 2 classes, the `committed_grant` and `contenders`
  fixtures

## Decisions Made

See the `key-decisions` block. The two worth restating:

**`source='manual'` in the lock test's seed.** `schema.helpers.insert_grant` defaults to
`anonymous_device_grant`, which populates the generated `anti_abuse_required_grant_id` column whose
`DEFERRABLE INITIALLY DEFERRED` FK is checked **at commit**. Every other case in `tests/schema/`
rolls back and so never reaches that check; this module is the only one that commits, and would have
failed in its own fixture on the default.

**`SET LOCAL lock_timeout` over the alternatives.** `FOR UPDATE NOWAIT` would put a lock modifier in
statements written to mirror production ones that deliberately do not carry it, and
`asyncio.wait_for` would abandon a still-running query on a connection the module goes on to reuse.
The timeout aborts server-side and leaves the connection usable. In the deadlock case it is set long
(5s, above PostgreSQL's 1s `deadlock_timeout`) so the detector always wins and a *missed* detection
fails the case rather than hanging the suite.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Two e2e cases outside `files_modified` had to be repointed onto a grant**

- **Found during:** Task 1, GREEN
- **Issue:** Attaching the gate to `POST /chats/{chat_id}` turns every admitted follow-up request
  without a grant into a 429 before the handler. Two cases drive that route as an admitted caller
  and assert a *handler* outcome:
  `test_error_cases.py::test_followup_nonexistent_chat_returns_404` (404 for a missing chat) and
  `test_isolation.py::test_cannot_post_to_other_user_chat` (404 for someone else's chat). Both
  would have turned 429 — and the isolation case would have stopped testing isolation while still
  looking like a passing security test, which is the worse of the two failures.
- **Fix:** `quota_grant` added to the error case; `owned_chat` extended to seed a grant for
  `STRANGER` only (the owner never POSTs in that module). Both carry a docstring paragraph saying
  the grant is what keeps the case about its own subject. Same call plan 36-03 made for the six
  `POST /chats` cases, for the same reason.
- **Files modified:** `tests/e2e/test_error_cases.py`, `tests/e2e/test_isolation.py`
- **Commit:** `754b660` — deliberately in the wiring commit, so no commit in the phase leaves the
  e2e suite red.

### Documented departures from the plan text

**2. Task 1's RED cases live in `tests/e2e/test_quota.py`, which task 1's `<files>` does list** —
no departure there, but the RED commit also carries `TestTheOtherSixRoutesConsumeNothing`, whose
subject (D-07) passes vacuously before the wiring. Kept in RED because it is the backstop that makes
the other cases mean something, and it is only vacuous before the feature exists.

**3. `test_the_no_grant_refusal_carries_the_shared_error_body[send_message]` passed during RED.**
It asserts the body has exactly one key, `code`, and a 404 `not_found` body satisfies that too. Same
shape as plan 36-04's departure 5: vacuous before the gate, load-bearing after. Kept rather than
sharpened, because sharpening it to also assert the status would duplicate the case above it.

**4. `-k OffPath` selects 10, not 7.** The plan's criterion says "seven cases, not six" — that is
the parametrized case, which went from six pairs to seven. The class also holds three unparametrized
cases (the admitted off-path request, the unknown path, and one more), so the selector total is 10.

**5. A `committed_grant` pytest fixture rather than an inline `try/finally` per case.** The plan
asks for the seed and the cleanup to be wrapped in `try/finally` in each case. A function-scoped
fixture whose body wraps its `yield` in `try/finally` gives the identical guarantee — teardown runs
on assertion failure, on deadlock, and on timeout — with one copy of the cleanup instead of four.
The nested-`finally` connection closing the plan asks for is in the `contenders` fixture, following
`test_apply_rollback.py:44-58`.

**6. REBIND-06 deliberately left unmarked.** See **Known Gaps** — this is a verified divergence,
not an omission.

---

**Total deviations:** 1 auto-fixed (Rule 3), 5 documented departures.
**Impact on plan:** No scope change to the three tasks. `docker-compose.yml` and `uv.lock` were
never staged (D-15) and remain modified and uncommitted.

## Flagged assumption carried forward — REBIND-02

Unchanged from the plan, and **still unresolved**: REBIND-02 says rejections on these routes
"increment the bounded-cardinality counter metric", and this plan reads "rejections" as
**barrier/auth rejections only**. Quota rejections get a structured log with closed-set labels and
no counter, because `record_rejection`'s `result` is typed to `AuthEventResult` — a closed 44-value
enum the migration forbids widening — and reaching for a non-member string would break exactly the
bounded-cardinality guarantee the counter exists to provide. The no-audit-row half of REBIND-02 is
proven for quota rejections regardless, since that half is unambiguous. REBIND-02 is marked complete
under this reading; if a reviewer disagrees, the resolution is a decision about whether to add a
second counter, not a re-plan.

## Issues Encountered

- **The Docker daemon socket is not accessible from this environment**, so the plan's manual step
  A1 (`docker compose up -d db`) could not be run as written. PostgreSQL was already listening on
  `localhost:5432` and every e2e and schema case ran against it, so nothing was skipped.
- **`gsd-tools query state.update-progress`** still fails with "Progress field not found in
  STATE.md", as all four previous plans reported. Known non-fatal tooling issue.
- **`requirements.mark-complete` reports `table_unmatched`** for the traceability surface. The table
  carries a collapsed range row (`| REBIND-01 … REBIND-06 | Phase 36 | Pending |`) the tool cannot
  match per-ID, and it correctly leaves the row alone. The checkboxes were flipped.

## Verification Results

| Check | Result |
|---|---|
| `uv run pytest -q -m ""` | **1258 passed** (baseline 1234; +24, no regression) |
| `uv run pytest -q` | 961 passed, 286 deselected |
| `uv run pytest tests/e2e -m e2e -q` | 213 passed (was 193) |
| `uv run pytest tests/e2e/test_quota.py -m e2e -q` | 39 passed (was 20) |
| `uv run pytest tests/schema -x -m schema -q` | 84 passed (was 80) |
| `uv run pytest tests/schema/test_grant_locks.py -m schema` | 4 passed in 2.6s, twice consecutively |
| `-k audit` / `-k malformed` / `-k OffPath` | 3 / 3 / 10 selected, all pass |
| `uv run pytest tests/e2e/test_startup_assertion.py -x -m e2e` | 9 passed |
| `uv run pytest tests/unit/test_route_registry.py -x` | passed (inside the unit run) |
| `uv run ruff check src tests` | clean |
| `uv run ty check src` | clean |
| registry probe | `two flags, eight routes` |
| app-route probe | `exactly the two POSTs` (set equality) |
| real `uvicorn` boot + `curl /health/ready` | "Application startup complete"; HTTP 200 `{"status":"up"}` |
| grep gates: `lock_timeout` / `DeadlockDetected` / `pytestmark` | 15 / 2 / 1 |
| mutation probe: drop both wrapper declarations | 2 of 3 `-k malformed` cases fail; restored clean |
| mutation probe: drop only `chat_id` | exactly the path case fails; restored clean |
| mutation probe: contender takes the fixed order | `test_the_reverse_order_deadlocks` fails (0 victims); restored clean |
| `git log --stat` for all 4 commits \| grep docker-compose\|uv.lock | 0 |
| `git status --porcelain` | `docker-compose.yml` and `uv.lock` still ` M`, unstaged (D-15) |
| deletion check across all 4 commits | no tracked file deleted |

## Threat Flags

No new network endpoint or trust boundary — the change is a gate in front of an existing route.
Against the plan's register:

- **T-36-drain:** mitigated **for the malformed-request surface it names**, and now proven at three
  shapes with a before-and-after read-back. A **residual** surface outside D-14's scope is recorded
  under Known Gaps below.
- **T-36-deadlock:** mitigated and, for the first time in this project, *enforced*. The reverse
  order deadlocks, the fixed order does not, and removing the contender's reverse lock collapses
  the deadlock — so the case is about the order, not about locking.
- **T-36-bypass:** mitigated. Both routes carry the gate, condition 10 fails boot on disagreement in
  either direction, and the app-route probe is a set equality rather than a containment check, so a
  third gated route cannot appear by accident and a fourth cannot be left ungated.
- **T-36-telemetry:** mitigated as read. No `record_rejection` call and no `AuthEventResult` member
  added; the closed 44-value set is untouched. The reading itself is the flagged assumption above,
  recorded rather than buried.
- **T-36-audit:** mitigated and now asserted rather than argued, for all seven 401-answering routes
  plus a served request and a quota 429.
- **T-36-testleak:** mitigated. `committed_grant` deletes the grant (usage cascades), the user and
  the tier in a `finally` that runs on assertion failure, deadlock and timeout alike. The module
  passes twice consecutively and `tests/schema` passes in full, including the seeded-tiers case that
  is the independent detector for a leaked tier row.
- **T-36-oracle:** accepted disposition unchanged. 422/429/500 remain distinguishable to the
  authenticated owner, which is intended, and none reveals another user's state.
- **T-36-SC:** upheld. Zero packages installed; `uv.lock` untouched.

## Known Stubs

None. No stub, placeholder, skipped test, or unrun `<verify>` was left behind.

## Known Gaps

**1. A post-gate 404 burns a credit — a verified REBIND-06 divergence, and a live instance of this
plan's own prohibition.** Probed directly: with a grant seeded,
`POST /chats/{nonexistent-uuid}` with a valid body answers **404** and moves `monthly_used`
**0 → 1**. In v1.6 the quota dependency was a `Depends(get_db)` yield-dependency whose commit ran
after the handler, so a handler exception rolled the increment back; D-04 replaced that with an
own-session commit so the grant locks would not span the LLM round trip, and nothing compensates.

This is exactly the prohibition this plan carries — *"A paying user must never be charged a credit
for a request the application itself rejected before the provider was contacted"* — whose status
moves from `flagged / unverified` to **violated / verified**. D-14 closes the *validation* face of
it (422 before the dependency runs); it does not and cannot close the *handler* face, because a 404
for a missing or someone-else's chat is only knowable after the gate has already committed.

**Not auto-fixed, on purpose.** Every available fix is one the phase's own decisions rule out: a
best-effort refund and reserve-then-settle are both explicitly rejected in D-11, and moving the
consumption after the ownership check means it can no longer be a decorator dependency, which
reopens the lock-window problem D-04 exists to solve. That makes this a Rule 4 architectural
decision, not a bug to patch inside an execution run. **REBIND-06 is therefore left unmarked** —
its text is "every pre-existing route behaves as it did in v1.6, apart from auth rejections now
using the shared error classes", and this is a behaviour change that is not an auth rejection.
The resolution is a decision about D-11's scope (accept the burn and amend REBIND-06's wording, or
fund a compensation path), and it belongs to `/gsd:verify-work` or a follow-up phase.

**2. REBIND-02's counter half rests on a reading, not a derivation.** See the flagged assumption
above.

**3. Two resolver branches remain stub-only.** `MultipleEffectiveGrantsError` and `UnknownTierError`
are unreachable through PostgreSQL (a partial unique index and a foreign key), so plan 36-04's
stub-session cases are still the only instrument. Unchanged by this plan.

**4. The lock test asserts the order, not `GrantsDB` itself.** Its statements are written directly
against the two tables because `tests/schema/` is asyncpg-based and has no SQLModel session. A
module comment says so and names the two methods it mirrors, so a change to either has a matching
test to update — but the coupling is by convention, not by import.

## User Setup Required

None. For anyone running the suite by hand: PostgreSQL must be listening
(`docker compose up -d db && uv run pogo apply`), and `set -a; . ./.env; set +a` is required before
running the app outside pytest.

## Next Phase Readiness

Phase 36 is code-complete. What later phases inherit:

- **Both quota-checked routes are wired and enforced at boot.** Adding a third means four edits in
  one commit — wrapper, decorator, registry flag, condition-10 tuple — and condition 10 fails boot
  if any is missing. The pattern is written twice now, which is what makes it a pattern.
- **`tests/schema/test_grant_locks.py` is the reference contention harness.** Phases 41, 42 and 45
  each take grant locks; they can copy `committed_grant`, `contenders`, `_begin` and the two
  statement constants rather than re-derive how to make two asyncpg connections contend.
- **One requirement is open by design.** REBIND-06 needs the D-11-scope decision in Known Gaps 1
  before it can be checked off. It is not blocked on code.
- `docker-compose.yml` and `uv.lock` remain modified and uncommitted per D-15.

---
*Phase: 36-rebind-pre-existing-routes*
*Completed: 2026-08-22*

## Self-Check: PASSED

All three claimed artifacts exist on disk (`tests/schema/test_grant_locks.py`,
`require_quota_send_message` in `app/dependencies.py`, this SUMMARY) and all four claimed commits
(`b3cfe54`, `754b660`, `651f20d`, `f2d9d0a`) resolve in `git log`. REBIND-01, REBIND-02 and
REBIND-05 are checked in `REQUIREMENTS.md`; REBIND-06 is deliberately not (Known Gaps 1).
