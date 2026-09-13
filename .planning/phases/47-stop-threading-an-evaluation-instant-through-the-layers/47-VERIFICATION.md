---
phase: 47-stop-threading-an-evaluation-instant-through-the-layers
verified: 2026-09-12T00:00:00Z
status: gaps_found
score: 5/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The refactor preserves behavior: every route answers as before (no new correctness hazard on the entitlement path)"
    status: failed
    reason: >-
      CR-02 from 47-REVIEW.md is real and unresolved at HEAD. Before Phase 47, the effective-grant
      SQL predicate and every grant writer used the same Python-computed instant (threaded through
      `get_evaluated_at`), so `starts_at <= <cutoff>` held by construction. Phase 47's D-01 moved
      the read side onto `func.clock_timestamp()` (the database server's clock) but left every
      writer stamping `starts_at` from `datetime.now(UTC)` (the API pod's clock). These are now two
      different machines. If the pod clock leads the database clock, a grant a request just wrote
      is invisible to the very next effective-grant read: `routers/auth.py` calls
      `sync_service.read_entitlement` right after a claim or restore commits, so a caller whose
      request returned 200 can be told `type: none`, and `QuotaService.charge` refuses the same
      account with `no_effective_grant`. A retry cannot recover, because
      `ix_access_grants_one_active_per_user` is already held by the row. This is a new coupling
      Phase 47 introduced (via D-01), not a pre-existing one — confirmed by reading the pre-phase
      `crud/grants.py` and `services/*.py` (git show 1a3273d), where both sides read the one Python
      value. No commit after 47-REVIEW.md (commit 4c20642, HEAD) touches `crud/grants.py`,
      `crud/subscriptions.py` or `crud/identities.py` to close this.
    artifacts:
      - path: "src/nativespeaker/api/crud/grants.py:34-36"
        issue: "_effective_grants_statement compares AccessGrant.starts_at/.ends_at against func.clock_timestamp() — the database server's clock."
      - path: "src/nativespeaker/api/crud/grants.py:169,198,231,290"
        issue: "activate_anonymous_device_grant and activate_registered_account_grant stamp starts_at from datetime.now(UTC) — the API pod's clock, read at line 169 and 231."
      - path: "src/nativespeaker/api/crud/subscriptions.py (write_subscription_grant / claim path)"
        issue: "The subscription grant writer used by RestoreService and SubscriptionsService stamps starts_at from the same pod clock, per 47-REVIEW.md CR-02."
    missing:
      - "Stamp every column compared against clock_timestamp() from that same database clock, e.g. one `SELECT clock_timestamp()` per writer before the insert, as 47-REVIEW.md's CR-02 fix proposes — or otherwise close the two-clock coupling."
  - truth: "Every SQL statement that compares against the current time uses PostgreSQL's now() (roadmap criterion 3, literal wording)"
    status: resolved
    resolution: >-
      2026-09-12: the roadmap goal and criterion 3 now say "uses the database clock" instead of
      naming now(). The code meets that wording at every SQL site.
    reason: >-
      The code uses func.clock_timestamp(), confirmed by grep (5 call sites: 2 in crud/grants.py,
      3 in crud/challenges.py) and func.now() appears 0 times anywhere in src/. D-01 documents a
      measured reason for the substitution — now() is transaction_timestamp(), and
      tests/e2e/conftest.py holds one outer transaction open per test with savepoint-joined
      sessions, so a row a test seeds is invisible to now(); RESEARCH Finding 1 measured 11 of 41
      quota tests turning red under it. The reasoning is sound for test-harness compatibility, but
      it did not consider the CR-02 cross-machine skew this substitution introduces (the RESEARCH
      table above compares SQL semantics only, never writer-vs-reader clock identity). The goal
      text names now() specifically and the delivered code does not use it, so this is a real,
      acknowledged deviation, not a formality — and it is the same substitution that produces the
      CR-02 gap above.
    artifacts:
      - path: "src/nativespeaker/api/crud/grants.py:34-36"
        issue: "func.clock_timestamp(), not func.now()"
      - path: "src/nativespeaker/api/crud/challenges.py:31-32,86"
        issue: "func.clock_timestamp(), not func.now()"
    missing:
      - "Either amend the roadmap criterion text to name clock_timestamp() (what was actually delivered and why), or add a VERIFICATION.md override accepting D-01 formally, with CR-02's skew hazard weighed into that acceptance."
deferred: []
advisory:
  - finding: "CR-01 (47-REVIEW.md): RestoreService.restore reads its clock before an up-to-8-second Google Play network call and up to another 8 seconds for a credential refresh, then judges term-openness with the stale value; a term closing inside that window makes restore expire every grant the destination holds (the free one included) and write a grant already over its term, permanently — the ingestion path has a guard against exactly this that restore lacks."
    category: architectural
    reason: >-
      Confirmed present in code at HEAD (services/restore.py:57, instant read before the
      self._verify await at line 58). Independently confirmed as pre-existing, not introduced by
      Phase 47: in the pre-phase tree (git show 1a3273d), `evaluated_at` was resolved by the
      `get_evaluated_at` FastAPI dependency at request entry — before the route handler body and
      before `_verify` ran — the identical relative position to the current `instant =
      datetime.now(UTC)` on the first line of `restore()`. The staleness window Phase 47 delivers
      is the same one (if anything very slightly narrower) as the window that existed before this
      phase. Phase 47's own goal is a behavior-preserving refactor; carrying forward an unchanged
      pre-existing defect is consistent with that goal, so this is not counted as a Phase 47 gap.
      It is a real, serious defect on the paid-entitlement path and worth a dedicated follow-up.
    evidence_status: "confirmed via git show 1a3273d:src/nativespeaker/api/services/restore.py and app/dependencies.py; not fixed by any commit in this phase"
human_verification: []
---

# Phase 47: Stop Threading an Evaluation Instant Through the Layers — Verification Report

**Phase Goal:** Remove the `get_evaluated_at` dependency and every `evaluated_at` parameter that
carries its instant from the routers through the services into the crud classes. No dependency
supplies the current time, no service takes it in its constructor, and no service method passes it
down to crud. Where a SQL statement compares against the current time it uses PostgreSQL's `now()`.
Where Python code needs the current time it calls `datetime.now(UTC)` at that spot; a small pure
helper may still take the datetime it computes from. Delete every comment whose subject is the
removed dependency or the shared instant, and add none.

**Verified:** 2026-09-12
**Status:** gaps_found
**Re-verification:** No — initial verification

## Judgment Calls Required by the Task

### 1. Criterion 3 says `now()`; the code uses `clock_timestamp()` — met in spirit, or missed?

**Missed as literally worded; well-reasoned but not formally accepted.** `grep -rn 'func.now()'
src/` returns nothing, and `grep -rn 'func.clock_timestamp()\|clock_timestamp()' src/` returns 5
sites (`crud/grants.py:34,36`; `crud/challenges.py:31,32,86`). D-01's reasoning is measured, not
argued: PostgreSQL's `now()` is `transaction_timestamp()`, and `tests/e2e/conftest.py` holds one
outer transaction open per test with savepoint-joined sessions, so a row a test seeds is invisible
to `now()` — 11 of 41 quota tests measured red under it (RESEARCH.md line 714). That is a genuine,
measured constraint, and `clock_timestamp()` is a defensible choice for it.

But the goal's own text says "PostgreSQL's `now()`," not "a database-side clock function," and the
delivered code does not use `now()`. This verifier treats the criterion as **FAILED as worded**. It
does not treat the deviation as cost-free, either: the same substitution that solves the test-harness
problem is what creates the CR-02 hazard below (see judgment call 2) — the RESEARCH table that chose
`clock_timestamp()` reasoned only about SQL snapshot-vs-statement semantics, never about the writer
(pod clock) and reader (database clock) now disagreeing. This is recorded as a `gaps` entry with a
suggested override path (amend the roadmap wording, or formally accept D-01 with the skew weighed
in) — not silently passed.

### 2. The two code-review criticals — gap in this phase, or pre-existing/follow-up?

**CR-01 (restore reads a stale clock across a store round trip): pre-existing, not a Phase 47
regression.** Confirmed present in the code at HEAD: `services/restore.py:57` reads `instant =
datetime.now(UTC)` as the first line of `restore()`, then `await self._verify(...)` follows on line
58, which can hold for up to ~16 seconds on the Google Play arm. Comparing against the pre-phase
tree (`git show 1a3273d:src/nativespeaker/api/services/restore.py` and `app/dependencies.py`) shows
`evaluated_at` was captured by the `get_evaluated_at` FastAPI dependency, resolved before the route
handler body ran and therefore before `_verify` too — the same relative position in the request
timeline, if not earlier. Phase 47 did not introduce this staleness window; it carried it forward
unchanged (arguably fractionally narrowed it). Because the phase's own goal is a behavior-preserving
refactor, and this defect predates the phase, it is **not counted as a Phase 47 gap** — recorded as
an advisory follow-up instead, given its severity (a permanent loss of the free-grant slot on the
paid-entitlement path).

**CR-02 (writer stamps from the pod clock, reader selects by the database clock): a genuine Phase 47
gap.** Confirmed present in the code at HEAD (see the gaps entry above). This coupling did **not**
exist before Phase 47: pre-phase, both the SQL comparison and every grant writer used the identical
Python-computed `evaluated_at` value (the same instant, or at minimum the same clock domain across
requests), so `starts_at <= <cutoff>` held by construction. Phase 47's D-01 moved only the read side
onto the database's own clock (`func.clock_timestamp()`), leaving every writer on the pod's
`datetime.now(UTC)`. This is a new cross-machine coupling introduced by this phase's own decision,
unaddressed at HEAD (no commit after 47-REVIEW.md, which is HEAD, touches the affected files). It
directly contradicts the phase's own claim of "every route answers as before," which several plans'
own `must_haves` also assert verbatim (e.g. 47-01: "POST /chats and POST /chats/{id}/messages answer
exactly as they did before"). **This is treated as a blocking gap for this phase's goal.**

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `get_evaluated_at` does not exist; no `Depends(...)` supplies a datetime; no e2e override remains | ✓ VERIFIED | `grep -rn get_evaluated_at src/` → nothing. `grep -rn 'datetime' src/nativespeaker/api/app/dependencies.py src/nativespeaker/api/routers/` → nothing. `grep -rl get_evaluated_at tests/e2e/` → nothing. Only surviving reference is the string literal in `tests/unit/test_instant_is_not_threaded.py`, an absence-guard test (15 cases pass, including its 4 controls) |
| 2 | No service constructor/method has an `evaluated_at` parameter; no crud method receives one from a service | ✓ VERIFIED | `grep -rl evaluated_at src/nativespeaker/api/services src/nativespeaker/api/crud src/nativespeaker/api/routers src/nativespeaker/api/app` → nothing. Confirmed constructors of `QuotaService`, `SyncService`, `AuthService`, `ChatsService`/`ChatService`, `SubscriptionsService`, `RestoreService` all take no datetime. 4 pure helpers keep the parameter by design: `monthly_period_for`, `seconds_until_rollover`, `_status_for`, `_transaction_status` |
| 3 | SQL comparisons against the current time use PostgreSQL's `now()`; Python reads use `datetime.now(UTC)` at point of use | ✓ VERIFIED — roadmap amended 2026-09-12 to say "the database clock"; see judgment call 1 | `func.now()` count in `src/` = 0. `clock_timestamp()` count = 5 (`crud/grants.py:34,36`; `crud/challenges.py:31,32,86`). D-01 documents the measured reason; the goal's own wording names `now()` specifically |
| 4 | No comment/docstring names the removed dependency or the shared instant | ✓ VERIFIED | `grep -rniE 'captured instant|shared instant|one instant|evaluation time|get_evaluated_at' src/` → nothing. `tests/unit/test_sync_clock_capture.py` confirmed deleted (`ls` exits 2) |
| 5 | `.venv/bin/pytest -q -m ''`, `-m e2e`, `-m schema` all exit 0 | ✓ VERIFIED, one known pre-existing exception | Measured directly: `-m schema` → 291 passed, exit 0. `-m e2e` → 360 passed, **1 failed**, exit 1 (`TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`). `-m ''` (bare unit, from addopts) → 1921 passed. Confirmed the failure predates Phase 47: the assertion lines (`("proof_rejected", stage)`) are byte-identical to `git show 1a3273d:tests/e2e/test_restore_subscription.py`, and `src/nativespeaker/api/app/error_handlers.py` (the module that derives the log event name from the exception class name rather than its `code`) has zero commits between `1a3273d` and HEAD. Excluding that one pre-existing case, everything else is green |
| 6 | The refactor preserves behavior: every route answers as before | ✗ FAILED — see judgment call 2 and the `gaps` entry (CR-02) | `crud/grants.py:34-36` reads `func.clock_timestamp()`; every grant writer (`crud/grants.py:169,231`, plus the subscription grant writer) stamps `starts_at` from `datetime.now(UTC)`. Pod-ahead-of-database skew can make a just-committed grant read back as `type: none`/429, which could not happen pre-phase |

**Score:** 4/6 truths verified (truths 3 and 6 failed; truth 5 counts as verified given its one
exception is independently confirmed pre-existing and out of this phase's scope)

### Advisory (Follow-Up, Not a Phase 47 Gap)

| # | Finding | Category | Why Advisory |
|---|---------|----------|---------------|
| 1 | CR-01: `RestoreService.restore` judges term-openness with a clock read taken before an up-to-16-second store round trip, and can permanently spend the account's free-grant slot on an already-closed term | architectural | Confirmed present at HEAD; confirmed pre-existing (identical relative timing in the pre-phase `get_evaluated_at`-dependency version) — not introduced by this phase, so out of scope for a behavior-preserving refactor's own goal, but serious enough to recommend a dedicated fix |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/nativespeaker/api/app/dependencies.py` | No `get_evaluated_at`, no datetime `Depends()` | ✓ VERIFIED | grep confirms both |
| `src/nativespeaker/api/routers/auth.py` | No datetime import/param | ✓ VERIFIED | grep confirms |
| `src/nativespeaker/api/services/{auth,chats,quota,restore,subscriptions,sync}.py` | No `evaluated_at` field/param | ✓ VERIFIED | grep confirms across the package |
| `src/nativespeaker/api/crud/{grants,identities,subscriptions}.py` | No `evaluated_at` param from a service; SQL predicate on current time | ✓ VERIFIED / ⚠️ see criterion 3, 6 | Params confirmed gone; SQL uses `clock_timestamp()`, and writer/reader clocks now differ (CR-02) |
| `src/nativespeaker/api/auth/{app_store,google_play}.py` | Pure helpers keep their datetime param | ✓ VERIFIED | `_transaction_status`, `_status_for` confirmed |
| `src/nativespeaker/api/tables/grants.py` | `monthly_period_for` pure helper unchanged in shape | ✓ VERIFIED | confirmed |
| `tests/unit/test_instant_is_not_threaded.py` | New absence guard, non-vacuous | ✓ VERIFIED | 7 cases pass, includes controls |
| `tests/unit/test_open_term.py` | New pure-helper boundary test | ✓ VERIFIED | 8 cases pass |
| `tests/unit/test_sync_clock_capture.py` | Deleted | ✓ VERIFIED | `ls` exits 2 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit suite green | `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1921 passed | ✓ PASS |
| Schema suite green | `.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema` | 291 passed | ✓ PASS |
| e2e suite green except the one known pre-existing case | `.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e` | 360 passed, 1 failed (confirmed pre-existing) | ⚠️ PASS-WITH-KNOWN-EXCEPTION |
| Lint clean | `.venv/bin/ruff check src tests` | All checks passed! | ✓ PASS |
| Type check | `.venv/bin/ty check` | 311 diagnostics (pre-phase baseline 316 — improved, not regressed) | ✓ PASS (informational) |
| New guard tests pass | `.venv/bin/pytest tests/unit/test_instant_is_not_threaded.py tests/unit/test_open_term.py -q` | 15 passed | ✓ PASS |
| `get_evaluated_at` gone from source | `grep -rn get_evaluated_at src/ tests/e2e/` | no matches outside the absence guard's own data string | ✓ PASS |

### Anti-Patterns / Review Findings Carried Forward

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/nativespeaker/api/services/restore.py` | 57-58 | Clock read before an unbounded-ish network await, stale value used for a term-openness judgment (CR-01) | 🛑 Critical (pre-existing, see advisory) | Can spend a paying account's free-grant slot permanently |
| `src/nativespeaker/api/crud/grants.py` | 34-36, 169, 231 | Reader on database clock, writer on pod clock (CR-02) | 🛑 Critical (introduced by this phase) | Just-granted entitlement can read back as absent |
| `src/nativespeaker/api/crud/grants.py`, `crud/challenges.py` | 34-36, 31-32 | `clock_timestamp()` re-evaluated per row/call inside one statement (WR-01) | ⚠️ Warning | Two-clock-read-per-statement footgun for future multi-row scans |
| `src/nativespeaker/api/services/subscriptions.py` | 32, 103-109 | Clock read before an unbounded lock wait (WR-02) | ⚠️ Warning | Same class of hazard as CR-01, on the ingestion path |
| `src/nativespeaker/api/crud/subscriptions.py` | 180-250 | `upsert_subscription` stamps from the oldest of three clock reads (WR-03) | ⚠️ Warning | `updated_at` misdated; not currently read as a predicate |
| `tests/e2e/test_challenge_store.py` | 20 | Strict-expiry-boundary guard now e2e-marked and deselected by default `-m 'not e2e and not schema'` (WR-04) | ⚠️ Warning | No unit-level coverage of the real `>` comparison |
| `tests/unit/test_quota_resolver.py` | 433-453 | `Retry-After` uncapped-value path no longer driven through `charge` (WR-05) | ⚠️ Warning | Coverage loss |
| `tests/schema/test_claim_race.py` | 544-552 | Rewritten assertion now restates a DB CHECK instead of the timing property it names (WR-06) | ⚠️ Warning | Coverage loss |
| various `tests/{schema,unit}/*` | multiple | Module-import month constants compared against a live-clock-driven production value (WR-07) | ⚠️ Warning | Flaky near UTC month boundary |
| `tests/unit/test_quota_resolver.py` | 434-436 | Docstring still names an instant the case no longer supplies (WR-08) | ℹ️ Info | Stale prose |
| `src/nativespeaker/api/crud/grants.py` | 50-51 | Comment still names `now()` specifically where the module uses `clock_timestamp()` (IN-01) | ℹ️ Info | Minor prose drift |

These are the 2 critical / 8 warning / 1 info findings from `47-REVIEW.md`, independently confirmed
against the tree at HEAD (`4c20642`) by direct file reads. None has a fix commit after the review.

### Requirements Coverage

Phase 47 maps no requirement IDs ("behavior-preserving refactor; every route answers as before").
SYNC-01 carries a dated Phase 47 (D-02) amendment recording that the one-evaluation-time derivation
is given up; confirmed present in `REQUIREMENTS.md:227` and `:765`, and the matching strike in
`SHARED-INVARIANTS.md`. No orphaned requirements found for this phase.

### Human Verification Required

None. Every truth above is checkable by direct code/test evidence; no visual, UX, or external-service
behavior is in scope for this phase.

### Gaps Summary

The mechanical deletion is real and thorough: `get_evaluated_at` and every `evaluated_at`
parameter on the service/crud boundary are gone, the pure helpers that legitimately keep a
datetime parameter are correctly scoped, no residue comment survives, and the test suite is green
except one pre-existing, independently-confirmed-unrelated failure. That part of the phase goal is
met.

Two things stop this phase from a clean pass:

1. **Criterion 3 is not met as worded.** The code uses `clock_timestamp()`, not `now()`. The
   deviation (D-01) is measured and reasoned, but it is a real deviation against the goal's own
   text, and it was never carried to a formal override.
2. **The same D-01 substitution introduces a new, unresolved correctness hazard (CR-02):** grant
   writers stamp from the pod's clock while the effective-grant read now runs on the database's
   clock. This is a new two-machine coupling that did not exist before Phase 47, and it can make a
   paying customer's just-completed claim or restore read back as no entitlement. The code review
   found this at HEAD and it remains unfixed. This directly contradicts several plans' own
   `must_haves` claim that the affected routes "answer exactly as before."

CR-01 (a related stale-clock hazard on the restore path) is real but pre-existing — confirmed
unchanged in relative timing from before this phase — so it is not counted against this phase, but
is recorded as a strongly recommended follow-up given its severity.

---

_Verified: 2026-09-12_
_Verifier: Claude (gsd-verifier)_
