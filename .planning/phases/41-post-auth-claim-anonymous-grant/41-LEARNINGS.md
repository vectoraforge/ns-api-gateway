---
phase: 41
phase_name: "post-auth-claim-anonymous-grant"
project: "ns-api-gateway"
generated: "2026-09-03"
counts:
  decisions: 12
  lessons: 8
  patterns: 8
  surprises: 8
missing_artifacts:
  - "41-UAT.md"
---

# Phase 41 Learnings: POST /auth/claim-anonymous-grant

## Decisions

### The activation returns a bool, it does not raise
`activate_anonymous_device_grant` reports failure by return value rather than by exception.

**Rationale:** the race loser and an account that became ineligible inside the window both fall through to the same post-commit read, which makes the claim, the repeat and the loser answer one shape by construction rather than by three branches that must be kept matching.
**Source:** 41-01-SUMMARY.md

### No third error class for ambiguity
The exhausted DeviceCheck budget, the timeout and an unrecognised Apple body all converge on the existing `Unavailable`.

**Rationale:** `Unavailable` already answers 503 `verification_temporarily_unavailable`; a new class would have split one outcome across two vocabularies.
**Source:** 41-01-SUMMARY.md

### The DeviceCheck Protocol lives beside its implementation
`DeviceCheckAdapter` went in `auth/devicecheck.py`, not in `auth/adapters.py`.

**Rationale:** `adapters.py` is fenced by an import allowlist that excludes `httpx`; putting the adapter there fails `test_adapter_interfaces.py`. The fence is the design, so the module moved rather than the fence.
**Source:** 41-01-SUMMARY.md

### `_service_jwt` fails closed before signing
An absent key id, team id or PEM raises `Unavailable` with no request issued.

**Rationale:** the same shape `build_admin_apps` takes with no Firebase credential — a missing credential is an outage, not a rejection of the caller.
**Source:** 41-01-SUMMARY.md

### The seam holds no logger
`auth/devicecheck.py` declares no logger at all.

**Rationale:** a structural guarantee that no code path can log a raw Apple device token, rather than a convention every future edit must remember. Independently confirmed to hold by the code review, through `log_fields` and `logs.py`'s `plain_traceback`.
**Source:** 41-01-SUMMARY.md, 41-REVIEW.md

### `before_call()` went inside the `try`, not above it
The plan allowed either placement.

**Rationale:** above the `try`, the pass-through arm stays as unreachable as the todo found it; inside it, the arm is genuinely exercised. D-14 chose to keep that arm, so the placement that makes it load-bearing is the one that honours the choice.
**Source:** 41-02-SUMMARY.md

### `db.pool_size` lives in the tracked YAML, foreclosing `DB_POOL_SIZE`
The tracked file is authoritative for anything it declares.

**Rationale:** nothing sets `DB_POOL_SIZE` today and `.env.example` does not document it, so the trade buys legibility — the pool value sits beside the `resilience.pool_size × 2 + 2` relation that explains it. If a deployment later needs a per-environment value, it moves to `config.py`'s field default and the YAML key goes.
**Source:** 41-02-SUMMARY.md

### The free-grant arms are evaluated before the other-source arm
`has_prior_free_grant` now issues its query even when a grant is held.

**Rationale:** the plan set the order. An account that is both ineligible and holding a manual grant now logs `free_grant_already_consumed` rather than `other_active_grant_held`; the client answer is byte-identical either way, which is the point of the shared base.
**Source:** 41-03-SUMMARY.md

### `ClaimRefused` is a pure group base, raised from nowhere
Every refusal got its own leaf class.

**Rationale:** matches how `ChallengeRejected` and `UpgradeRefused` already work, so one rejection vocabulary rather than two. The stale comment in `test_rejection_vocabulary.py` was updated rather than left to mislead.
**Source:** 41-03-SUMMARY.md

### Lock tiers are asserted over emitted SQL, not a mirrored literal
New cases capture the writer's own statements at `before_cursor_execute`.

**Rationale:** a literal mirroring the crud can pin what the two known tiers look like but cannot detect a *third* tier a future writer adds — which is the actual threat. The mirrored literals stay for the contention cases, which need executable SQL of their own.
**Source:** 41-04-SUMMARY.md

### Resolved-by-precedence is a third ledger category, not a softer conflict
The brief's user-first lock order versus `SHARED-INVARIANTS.md` is recorded as resolved, not flagged.

**Rationale:** a flagged conflict means the project knowingly diverges from binding text. Here the binding text says what to do and the code does it — flagging it would misfile obedience as divergence. It is still counted once among divergences, because the brief-to-code difference is real.
**Source:** 41-05-SUMMARY.md

### One `device_token`, used for both the Apple read and the write
The wire contract collapsed from `query_token` + `update_token` to a single field.

**Rationale:** two opaque DeviceCheck tokens cannot be tied to one device, so independent fields let device A satisfy the read while device B satisfies the write. Made as a clean break rather than with a compatibility shim, because the route has no clients yet.
**Source:** 41-REVIEW.md (CR-02), commit `e2e18de`

---

## Lessons

### Detached is not expired, and the difference decides which repair is correct
A row returned from a dependency that opened its own session is **detached**, not expired. `session.refresh()` on it raises `InvalidRequestError` — it does not reload it.

**Context:** `_claim_anonymous_grant`'s loser arm was patched with two `refresh()` calls on the premise that `rollback()` had expired the caller's rows. `app/dependencies.py::get_identity` resolves on its own short session and returns from inside the `async with`, so those rows were never members of the handler's session. The raised `InvalidRequestError` is not an `AppError`, so it escaped `_complete`'s handler and answered 500 where D-13 requires 200.
**Source:** 41-REVIEW.md (CR-01), 41-VERIFICATION.md

### A test that shares a session with the code under test can manufacture a failure production cannot have
The `MissingGreenlet` crash that motivated the refreshes was an artifact of the test harness, not a production defect.

**Context:** `tests/schema/test_claim_race.py` resolved the identity on the *same* session it handed to `AuthService`, so there the rollback really did expire those rows. In production, with `expire_on_commit=False`, a detached row keeps its loaded attributes and the router's reads were always safe. The test's convenience — one session instead of two — was the entire bug report.
**Source:** 41-REVIEW.md (CR-01), 41-04-SUMMARY.md

### Two independent client-supplied tokens cannot be bound to one device
Any gate that reads one opaque token and writes another has no binding between the read and the write.

**Context:** device A's token as `query_token` (never written, bit0 stays clear) and device B's as `update_token` (re-writing a set bit returns 200) passed every account — two devices bought unlimited free grants, defeating the rule ANONGRANT-03 exists to enforce. The phase's own threat table covered replaying *one* token twice and did not reach this.
**Source:** 41-REVIEW.md (CR-02)

### A control can pass for the wrong reason
`activated is False` held, but from the `IntegrityError` arm rather than the held-grant arm it was written to exercise.

**Context:** the module's fixed `NOW` preceded the seeded grant's `starts_at`, so the grant was not effective, the writer took one tier instead of two, fell through every check and was rejected by the unique index at the flush. Replaced with a control that cannot be satisfied that way — the writer must issue no `INSERT` at all.
**Source:** 41-04-SUMMARY.md

### `requirements.mark-complete` cannot address a range traceability row
`ready-ids` released all three IDs, then `mark-complete` returned `updated: false` with every ID under `table_unmatched`.

**Context:** the row is `| ANONGRANT-01 … ANONGRANT-03 |`, a range the tool does not expand. Every endpoint phase in that table uses the same form, which is why prior phases also edited it by hand. Phase 42 will hit the identical result on `REGGRANT-01 … REGGRANT-03`.
**Source:** 41-05-SUMMARY.md

### Acceptance criteria can be internally inconsistent with their own action text
Three plans hit this, and all three resolved toward stated intent rather than literal wording.

**Context:** 41-02's criterion demanded `_semaphore` appear in `ainvoke`, which the same task's prescribed public `concurrency` manager makes impossible without reaching past it; 41-03's case 1 was the idempotent 200 and could not compare against a 403 constant; 41-04 asked for challenges "already claimed" *and* driven through a completion that rejects pre-claimed rows. Each was recorded as a deviation with its reasoning rather than silently satisfied.
**Source:** 41-02-SUMMARY.md, 41-03-SUMMARY.md, 41-04-SUMMARY.md

### The shared-ID requirement gate holds IDs until the last declaring plan lands
Four consecutive plans reported requirements "not marked complete" as a correct outcome, not a failure.

**Context:** ANONGRANT-01/-02/-03 are declared by several plans, so `ready-ids` returned 0/2 and 0/3 until 41-05, the last declarer, finished. Reading those reports as failures would have prompted a pointless investigation four times.
**Source:** 41-01-SUMMARY.md, 41-03-SUMMARY.md, 41-04-SUMMARY.md, 41-05-SUMMARY.md

### `state add-decision --summary-file` rejects `/tmp` paths
The SDK confines file inputs to the repository root, so `mktemp` does not work with these flags.

**Context:** three decision texts had to be written under `.planning/.tmp/` and removed afterward.
**Source:** 41-02-SUMMARY.md

---

## Patterns

### Capture emitted SQL at `before_cursor_execute` instead of mirroring a literal
Assert the ordered lock relations, the distinct tier count, and the absence of specific tables from the statements the writer actually issues.

**When to use:** whenever the property is "no more than these N things happen" rather than "these N things happen". A mirrored literal pins the known cases and is blind to the new one; a capture fails a named case when a future writer adds a third tier.
**Source:** 41-04-SUMMARY.md

### Mutation-test the guard before trusting it
Introduce the violation the guard exists to catch, observe the named case fail, then revert and confirm the file is byte-identical.

**When to use:** any test asserting a negative property over a whole tree. Used three times this phase — a second `anonymous_device_grant` construction site, a narrowed `FREE_GRANT_SOURCES` constant, and the temporarily restored `refresh()` calls — and each time it distinguished a guard that bites from one that passes vacuously.
**Source:** 41-03-SUMMARY.md, 41-04-SUMMARY.md, 41-REVIEW.md fix (`ed95eae`)

### Barrier-synchronised two-connection race against real PostgreSQL
Prepare two attempts, drive both through the production entry point on independent connections, and hold them at a barrier placed at the exact statement before the contended flush.

**When to use:** when the arbiter is the database rather than the application — here the `FOR UPDATE` locks nothing on a first claim, so the two unique indexes decide. No unit or end-to-end test can reach this, and the barrier is what stops the case degrading into two sequential runs.
**Source:** 41-04-SUMMARY.md

### Assert the production property, not the absence of a string
The CR-01 regression case records `object_session(row) is None` for both caller rows at the moment the service is constructed.

**When to use:** in place of grepping source for a forbidden call. The property version also fails if someone re-wires the test to resolve on the service's session — which is the mistake that hid the original defect — so it defends the test's own premise, not just the code.
**Source:** 41-REVIEW.md fix (`ed95eae`)

### Generalise a completion sequence over an injected callable rather than forking it
`AuthService._complete` took a `post_claim` callable; the two Firebase routes pass `partial(self._read_then_write, write=...)` unchanged.

**When to use:** when a new operation shares most of an existing sequence. The existing callers keep byte-identical behaviour, so the diff shows only the new path.
**Source:** 41-01-SUMMARY.md

### Record the divergence in the ledger; leave the specification verbatim
Four decisions diverged from `06-claim-anonymous-grant.md`; none of them edited it.

**When to use:** as this milestone's standing convention (D-19). It keeps the brief a stable reference and puts the divergence where a later reader hits it — under the requirement it belongs to, with the decision that caused it named.
**Source:** 41-05-SUMMARY.md

### Verify the state before acting on what the plan predicted
A plan describes the world it expects; the executor's first move is to check whether that world is still there.

**When to use:** on any task whose action text asserts a precondition. Both of 41-05's deviations were this rule paying off — A-15 was already closed, and `mark-complete` had nothing to flip — and in both cases the correct action was to verify and report rather than write what the plan predicted.
**Source:** 41-05-SUMMARY.md

### State a grep-shaped guarantee as grep-shaped
`test_grant_sources.py` walks today's `src/` and the summary says so, rather than claiming a database-level guarantee.

**When to use:** whenever a negative property is bounded by static analysis. The flagged assumption `EDGE-ANONGRANT-03-unclassified` stays open rather than being closed by a criterion that would read stronger than the check actually is.
**Source:** 41-03-SUMMARY.md

---

## Surprises

### The concurrency proof found a real 500 on its first run
The race surfaced a genuine production defect, not in the arbitration — which was correct — but immediately after it.

**Impact:** the one path D-13 requires to answer 200 answered 500, with the challenge left claimed-but-unconsumed. This is the outcome a concurrency proof is written to produce, and nothing already in the suite could have reached it.
**Source:** 41-04-SUMMARY.md

### The fix for that 500 was itself wrong, and the code review caught it
The repair rested on a misdiagnosis ("the rollback expired the rows") and replaced one crash with another.

**Impact:** the phase would have shipped a confirmed 500 on a required path with a full green suite behind it. Reproduced independently before the second fix was authorised.
**Source:** 41-REVIEW.md (CR-01)

### A green suite was evidence about the test harness, not about production
1310 passing tests said nothing about CR-01 either way, because the only case covering that path shared a session in a shape production never has.

**Impact:** the strongest argument for the phase's correctness turned out to be silent on its worst defect. The unit stub's `async def refresh(self, obj): return None` was the second half of the same blind spot.
**Source:** 41-REVIEW.md (CR-01), 41-VERIFICATION.md

### `expire_on_commit=False` is load-bearing and documented nowhere
It is the only reason the loser arm can now correctly do nothing at all.

**Impact:** flipping that one setting in `app/lifespan.py:53` breaks the arm again in a new way, and no comment in the code says so. Recorded in the ANONGRANT ledger so the next reader finds it.
**Source:** 41-REVIEW.md fix, .planning/REQUIREMENTS.md amendment (`d817cb3`)

### All seven claim outcomes consume the challenge, and none rejects before it
The repeat, all four refusals and all three Apple arms are decided after the claim.

**Impact:** the plan asked for this to be reported rather than adjusted to, and it is the opposite of what the brief's ordering implies — including the registered-caller refusal, whose check is the first thing the post-claim work does. Anything in the ledger assuming a pre-claim rejection is a dead obligation.
**Source:** 41-03-SUMMARY.md

### Not one of six invariant sections produced a new divergence
All four new conflicts are against the brief; `SHARED-INVARIANTS.md` yielded none.

**Impact:** a null result worth stating, because it was re-derived by reading all six sections rather than assumed. § Grants' one-evaluation-time rule came out *more* satisfied than before — `get_evaluated_at` made it structural instead of a convention two call sites must remember.
**Source:** 41-05-SUMMARY.md

### A-15 was already closed by a sibling plan
41-02 had closed the blocker in place on 2026-09-02, satisfying every one of 41-05's acceptance criteria for it.

**Impact:** none, because the state was verified first. Writing the second closure the plan called for would have produced a duplicate and diluted the history the entry exists to keep.
**Source:** 41-05-SUMMARY.md

### The whole phase ran sequentially, not in three parallel waves
Worktree isolation auto-degraded at dispatch (#48/#3659): the harness forks agent worktrees from `origin/HEAD`, which predates this milestone branch.

**Impact:** the wave grouping stayed as planned but bought no parallelism — five plans ran one at a time on the main working tree. Worth expecting for every phase on this branch until it is merged or pushed so `origin/HEAD` matches.
**Source:** execute-phase dispatch, `worktree base-check`
