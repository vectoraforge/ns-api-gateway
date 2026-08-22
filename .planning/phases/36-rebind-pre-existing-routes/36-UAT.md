---
status: complete
phase: 36-rebind-pre-existing-routes
source: 36-01-SUMMARY.md, 36-02-SUMMARY.md, 36-03-SUMMARY.md, 36-04-SUMMARY.md, 36-05-SUMMARY.md
started: 2026-08-22T05:03:51Z
updated: 2026-08-22T06:12:16Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running server/service. Clear ephemeral state (temp DBs, caches, lock files). Start the application from scratch — `pogo apply` against a fresh `nativespeaker` database, then `uv run uvicorn nativespeaker.api.app.main:app`. The app boots without errors (the 10-condition route-registry assertion passes at startup), the three access tiers seed, and `GET /health/ready` returns 200 `{"status":"up"}` unauthenticated.
result: pass

### 2. v2.0 models round-trip a real row
expected: Against a live PostgreSQL 17 with the v2.0 migration applied, `AccessTier`, `AccessGrant` and `UserMonthlyUsage` read and write real rows through SQLModel with no column-name or type mismatch. 36-01 proved this once with an uncommitted ad-hoc script; plans 36-03/36-04/36-05 now drive the same three models against the live database from `tests/e2e/test_quota.py` and `tests/schema/`. Confirm the committed suite now covers what the throwaway script showed, so a schema edit would be caught in CI.
context: 36-01 D3 — reason=human_judgment. "The round-trip was proven once against the developer's live PostgreSQL 17, but no committed test re-proves it, so it will not rerun in CI or after a schema edit."
result: pass
note: "Confirmed by inspection — tests/e2e/conftest.py:274-288 writes AccessGrant/UserMonthlyUsage to the live DB, tests/e2e/test_quota.py:84-93 reads them back; a column mismatch now fails CI."

### 3. No lock held and no network call while the quota session is open
expected: While the app waits on the AI provider (which can take seconds), it must not be holding a database row locked — that would make the same user's other requests queue up behind it. Expected: the credit is counted, the transaction commits, and the connection closes, all *before* the AI call starts.
context: 36-03 D8 — reason=human_judgment. Originally proven by code reading plus a FastAPI ordering probe rather than by observing a held lock; 36-05's `tests/schema/test_grant_locks.py` (4 cases, two live asyncpg connections) is the contention-level evidence.
result: pass
note: "Verified by Claude, not by human judgment. quota.py:213 opens the charge session with 'async with self._session_factory()' and commits inside it; resilience.py:126-130 fully awaits on_admitted() before 'return await operation()' (the provider call). No create_task/gather/TaskGroup anywhere in the chain, so nothing can reorder it. tests/unit/test_quota_resolver.py -k 'TestGrantThenUsageOrder or TestTheLockingStatements' -> 11 passed."

### 4. Two effective grants raise instead of tie-breaking
expected: A user should only ever hold one active grant at a time, and the database enforces that with a unique index. This checks what the app does if that rule were somehow violated anyway: it should error out (500) rather than quietly guess which grant to charge. Because the database makes the situation impossible to create for real, the only proof is a simulated (stubbed) test. Your call: is a simulated test good enough for this tripwire?
context: 36-04 D4 — reason=human_judgment. "Whether a stub-only proof is sufficient for a tripwire is a judgment call — recorded rather than claimed as behavioural coverage."
result: pass
note: "User accepted: stub-only coverage is sufficient for a tripwire the database makes unreachable. Testing it for real would require dropping ix_access_grants_one_active_per_user."

### 5. Lazy rollover and the increment commit atomically
expected: The monthly quota resets lazily — the first request of a new month zeroes the counter, instead of a scheduled job doing it. This checks the reset and the charge happen as one unit: a user who was maxed out last month gets served, and their counter afterwards reads 1 for the current month (not 0, not 2).
context: 36-04 D5 — reason=human_judgment. Atomicity was argued from the code (one session, one caller-owned commit, no intermediate flush), not observed under a competing reader; 36-05's `tests/schema/test_grant_locks.py` supplies the two-connection evidence.
result: pass
note: "Verified by Claude against the live database. tests/unit/test_quota_resolver.py -k TestLazyRollover -> 4 passed; tests/e2e/test_quota.py -k rollover (real app + real PostgreSQL 17) -> 1 passed."

### 6. Grant-then-usage lock order holds under real contention
expected: When two requests from the same user land at the same moment, they must grab database locks in the same order or they can deadlock. A test opens two real database connections and makes them fight: the second waits for the first, and locking in the reverse order genuinely produces a deadlock — which is what proves the fixed order is doing real work.
context: 36-04 D6 — reason=human_judgment. "Statement-level, not contention-level" when recorded; 36-05 D4 supplied the contention-level proof afterward.
result: pass
note: "Verified by Claude against the live database. tests/schema/test_grant_locks.py -m '' -> 4 passed (lock exclusion, release, reverse-order DeadlockDetectedError, fixed-order safe path) using two real asyncpg connections."

### 7. A grant pointing at an unknown tier fails closed
expected: Every grant points at a tier (anonymous / registered / paid) that sets the monthly allowance. This checks what happens if a grant points at a tier that does not exist: the app should error (500) — not treat it as “zero allowance” (which would look like a normal out-of-credits message) and not as “unlimited” (which would serve for free). Like test 4, a foreign key makes this impossible in practice, so the test is simulated.
context: 36-04 D9 — reason=human_judgment. Same stub-only situation as test 4.
result: pass
note: "User accepted, same reasoning as test 4 — the foreign key makes the state unreachable."

### 8. REBIND-02's counter-metric scope for quota 429s
expected: This one is a decision for you, not a test. Requirement REBIND-02 says rejected requests should bump a counter metric. The team built the new out-of-credits rejection (429) to write a log line but *not* bump a counter, and flagged that they were unsure whether the requirement was meant to cover this new kind of rejection at all. Your call: (a) log-only is fine, requirement satisfied, no code change — or (b) out-of-credits rejections need a counter too, file a follow-up. This is the only item keeping phase 36 from being marked verified.
context: 36-05 D2 (reason=human_judgment) and 36-VERIFICATION.md `human_verification[1]` — the sole reason phase verification sits at `human_needed` rather than `passed`.
result: pass
note: "Resolved by removal, not by ruling. The user rejected maintaining a hand-rolled metric subsystem; RejectionCounter was deleted in 5f275c8. Rejections keep their structured security log event, from which rejection rate is derived by the deployment's log pipeline. REQUIREMENTS.md REBIND-02 reworded to match. There is no counter left to decide about."

### 9. Three seeded access tiers survive a fresh apply
expected: core.access_tiers holds exactly the three seeded reference rows after a fresh pogo apply — anonymous=10, registered=50, paid=1000 — and registered >= anonymous.
result: pass
source: automated
coverage_id: 36-01-D1

### 10. Models resolve to the core schema with the right defaults
expected: AccessTier, AccessGrant and UserMonthlyUsage import from the models barrel, resolve to the core schema and the right table names, construct with the documented defaults, and map none of the four generated columns.
result: pass
source: automated
coverage_id: 36-01-D2

### 11. Single definition of the usage INSERT helper
expected: tests/schema/helpers.py::insert_usage is the single definition of the core.user_monthly_usage INSERT, binding every caller value as a $N parameter.
result: pass
source: automated
coverage_id: 36-01-D4

### 12. A correct phrase validates instead of 500-ing
expected: A grammatically correct phrase — the case where the model returns neither issues nor suggestions — validates to 200 with `issues == []` and `suggestions == []` instead of the 500 recorded as D-35-11-A.
result: pass
source: automated
coverage_id: 36-02-D1

### 13. Empty-list defaults are per-instance
expected: The two defaults are per-instance, so mutating one response's `issues` does not leak into another's.
result: pass
source: automated
coverage_id: 36-02-D2

### 14. Shared auth error contract undisturbed
expected: The D-12 exception did not disturb the shared auth error contract — REBIND-03's proof is still green.
result: pass
source: automated
coverage_id: 36-02-D3

### 15. PROJECT.md does not over-claim constrained decoding
expected: Neither PROJECT.md claim asserts constrained decoding as shipped; both cite D-13, the decisions row cites D-35-11-A as evidence, and the real fix is an open backlog item.
result: pass
source: automated
coverage_id: 36-02-D4

### 16. ROADMAP Phase 36 goal says eight routes
expected: The ROADMAP Phase 36 goal says eight pre-existing routes, agreeing with auth/registry.py and its own success criterion 2, and explains where the ninth went.
result: pass
source: automated
coverage_id: 36-02-D5

### 17. No effective grant returns 429 quota_exceeded
expected: `POST /chats` from an admitted caller with no effective grant returns 429 `quota_exceeded` in the shared error shape — not a 500 and not a 200.
result: pass
source: automated
coverage_id: 36-03-D1

### 18. Non-effective grants are refused identically
expected: A grant row that is not effective — not yet started, already ended, or status not `active` — is refused identically, so the rejection is a property of the shared predicate rather than of an empty table.
result: pass
source: automated
coverage_id: 36-03-D2

### 19. A seeded active grant is admitted
expected: An admitted caller holding a seeded active grant is admitted, reaches the handler, and returns its v1.6 status.
result: pass
source: automated
coverage_id: 36-03-D3

### 20. Condition 10 enforces the quota_checked flag
expected: Condition 10 makes `quota_checked` enforcement: equal sets pass, and either direction of disagreement fails boot with a distinctly-labelled line naming the route.
result: pass
source: automated
coverage_id: 36-03-D4

### 21. Condition 10's error text is deterministic
expected: The condition-10 RuntimeError is deterministic: both set differences are emitted through `sorted()`, so the same disagreement produces byte-identical text.
result: pass
source: automated
coverage_id: 36-03-D5

### 22. Condition 10 is a no-op on empty input
expected: Condition 10 is a no-op on empty input — zero routes with a zero-length registry, and a registry declaring zero `quota_checked` entries, add no problem.
result: pass
source: automated
coverage_id: 36-03-D6

### 23. Effective-grant statement locks and orders by id
expected: The effective-grant statement takes row locks and orders ascending by grant id, with no row-count cap (SHARED-INVARIANTS:33, D-10).
result: pass
source: automated
coverage_id: 36-03-D7

### 24. The allowance is spent exactly at the boundary
expected: `monthly_used == allowance` rejects 429 without incrementing; `allowance - 1` is admitted and commits exactly at the allowance; the next request then rejects.
result: pass
source: automated
coverage_id: 36-04-D1

### 25. remaining never goes negative
expected: `remaining` is never negative — an already-over-allowance row clamps to zero and rejects rather than producing a negative count or a second charge.
result: pass
source: automated
coverage_id: 36-04-D2

### 26. A missing usage row fails closed
expected: A grant with zero `core.user_monthly_usage` rows returns 500 `internal_error` and no usage row is minted.
result: pass
source: automated
coverage_id: 36-04-D3

### 27. Grant window boundaries are inclusive/exclusive
expected: Both effective-grant boundaries behave as specified: `starts_at` inclusive, `ends_at` exclusive.
result: pass
source: automated
coverage_id: 36-04-D7

### 28. A correct phrase is served and charged over the wire
expected: A correct phrase returns 200 with `issues == []` and `suggestions == []` — the D-12 half of REBIND-06, over the real transport.
result: pass
source: automated
coverage_id: 36-04-D8

### 29. Exactly the two chat POSTs are quota-gated
expected: Both chat POSTs — and only those two of the eight pre-existing routes — carry a quota dependency and declare `quota_checked=True`; the other six serve unchanged (D-07).
result: pass
source: automated
coverage_id: 36-05-D1

### 30. A malformed request is not charged
expected: A malformed request on either chat POST returns 422 and leaves `monthly_used` unchanged — the quota dependency never ran, so no credit was burned (D-14).
result: pass
source: automated
coverage_id: 36-05-D3

### 31. Real two-connection lock exclusion and deadlock detection
expected: Under two real concurrent connections, a second transaction cannot take the grant row lock while the first holds it, and the reverse lock order is detected by PostgreSQL as a deadlock.
result: pass
source: automated
coverage_id: 36-05-D4

### 32. The follow-up route is charged exactly once
expected: The follow-up route is charged exactly once per request, and its charge goes through the same shared resolver as the first route.
result: pass
source: automated
coverage_id: 36-05-D5

## Summary

total: 32
passed: 32
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
