---
phase: 35-foundation
plan: 10
subsystem: challenge-store
tags: [sqlmodel, postgresql, bytea, native-enum, secrets, base64url, conditional-update, asyncio]

requires:
  - phase: 35-foundation
    plan: 06
    provides: "auth/context.py's LinkedIdentity / PreAuthIdentity, and the e2e seed_identity + rollback harness"
  - phase: 35-foundation
    plan: 08
    provides: "HmacKeyring.actor_subject_hash and actor_subject_matches -- the derivation and the constant-time comparison this store calls rather than reimplements"
  - phase: 35-foundation
    plan: 09
    provides: "models/auth.py's enums and table idiom, and the audit writer that shares this store's key family"
provides:
  - "models.auth.AuthChallenge -- core.auth_challenges, lifecycle by column nullability and no key-version column"
  - "auth/challenges.py: CHALLENGE_TTL_SECONDS, CHALLENGE_ID_BYTES, new_challenge_id, ChallengeRejection, ChallengeStore"
  - "ChallengeStore.claim -- the single serialization point for all four challenge-bearing operations"
  - "ChallengeStore.consume -- one UPDATE that sets consumed_at and clears preauth_subject_hash together"
  - "ChallengeStore.verify_binding -- §6.4's comparison, through the shared compare_digest seam"
  - "auth/modesignal.py: ModeSignal, classify_mode_signal -- the §6.5 syntactic partition"
  - "app.state.challenge_store, sharing the lifespan's one HmacKeyring object with the audit writer"

affects: [35-11, 37-create-user, 40-upgrade, 41-idp-account, 42-claim-grant]

actuals:
  tokens: 23341
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "Asserting an alphabet as set equality over ~22,000 sampled characters, because a single-sample containment check is both flaky and blind to a substitution that stays inside the alphabet"
    - "A keyring stub that raises on every method, so `not compared at all` is asserted as a property of the code path rather than inferred from the returned value"
    - "Planting a fixed row rather than a generated one when the case mangles it, so no mangling can coincidentally equal the original and turn the case into a silent skip"
    - "Driving real database contention from independent connections released by an asyncio.Barrier, and asserting `no contender raised` before any count, so a broken harness cannot masquerade as arbitration"
    - "Deleting by exact value in a fixture teardown when a case must commit outside the rollback transaction -- a test tidying its own fixture, distinct from the cleanup job the product forbids"

key-files:
  created:
    - src/nativespeaker/api/auth/challenges.py
    - src/nativespeaker/api/auth/modesignal.py
    - tests/unit/test_challenge_ids.py
    - tests/unit/test_mode_signal.py
    - tests/e2e/test_challenge_store.py
  modified:
    - src/nativespeaker/api/models/auth.py
    - src/nativespeaker/api/models/__init__.py
    - src/nativespeaker/api/app/lifespan.py
  deleted: []

key-decisions:
  - "The plan's prescribed concurrency harness does not work and would have produced a vacuously green test. Eight sessions from the swapped `test_factory` share ONE connection, so they are not concurrent, and their interleaved savepoints break seven of the eight outright -- one returns True and the rest raise. 'Exactly one True' passes on that while seven contenders never reach the UPDATE. The race runs on eight independent connections instead, with its one committed row deleted by exact value on teardown."
  - "`verify_binding` contains no literal `compare_digest` call. Plan 08 shipped `actor_subject_matches` as the seam precisely so plans 09 and 10 would not each write their own comparison; the plan's acceptance probe pre-dates it. The probe still prints True via the docstring that explains the indirection, and the real property is pinned on the AST -- a call to `actor_subject_matches`, and no `==`/`!=` anywhere against `preauth_subject_hash`."
  - "Every store method is transaction-neutral: `issue` flushes, and neither `claim`, `consume` nor `issue` commits. §6.1 pins this only for `consume`; extending it to `issue` keeps the store uniform and stops a prepare committing inside a handler that later fails."
  - "`ChallengeRejection` member values are exactly `core.auth_event_result` member values, pinned by a test, so phases 37+ can write `AuthEventResult(rejection)` rather than each maintaining a private mapping table."
  - "No operation or operation-variant comparison ships in the store. §6.4 puts the two on opposite sides of the claim -- operation before it, variant after it as a consuming rejection -- so a single helper would have to encode which side its caller is on. The enum carries both rejections and the module docstring carries the ordering."
  - "Task 3 ran no RED phase. It is a test-only task against a module task 1 already shipped, so every case would have passed on first write. 26 mutations were run against the shipped source instead; three first-pass survivors were real gaps in the tests and were closed."

requirements-completed: [FOUND-07]

coverage:
  - id: CH1
    description: "challenge_id is 16 CSPRNG bytes, base64url without padding, yielding a 22-character handle"
    requirement: FOUND-07
    verification:
      - kind: unit
        ref: "tests/unit/test_challenge_ids.py::TestTheOpaqueHandle (7 cases: length, no padding, alphabet as set equality over 1000 handles, 1000 distinct, decodes to 16 bytes, not a UUID, secrets not random)"
        status: pass
      - kind: other
        ref: "mutation C15 (uuid4().hex[:22]) -> passed everything until the alphabet was asserted as set equality, then 1 failed; C17 (standard base64) and C18 (8 bytes) likewise"
        status: pass
    human_judgment: false
  - id: CH2
    description: "expires_at is the supplied server clock plus exactly 300 seconds, with no per-operation override, grace period, or renewal"
    requirement: FOUND-07
    verification:
      - kind: unit
        ref: "::TestTheUniversalTTL (14 cases incl. all seven operation/variant arms, and a fixed `now` years from the wall clock)"
        status: pass
      - kind: other
        ref: "mutation C10 (issue reads datetime.now) -> 39 failed, 4 errors; C11 (600-second TTL) -> 2 failed"
        status: pass
    human_judgment: false
  - id: CH3
    description: "locate compares byte-for-byte with no trimming, re-encoding, case-folding or defaulting, and no raw identifier is logged"
    requirement: FOUND-07
    verification:
      - kind: unit
        ref: "::TestLocateIsByteForByte (10 cases asserting the bound parameter, not a returned row); ::test_the_module_logs_nothing"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_challenge_store.py::TestLocateIsByteForByteAgainstPostgres (9 cases against a planted fixed handle: cased, spaced, repadded, truncated, extended, unknown)"
        status: pass
      - kind: other
        ref: "mutation C19 (locate trims) -> 5 failed; C20 (ILIKE) -> 2 failed"
        status: pass
    human_judgment: false
  - id: CH4
    description: "Exactly one of N concurrent claims wins; every other attempt matches zero rows and mutates nothing"
    requirement: FOUND-07
    verification:
      - kind: e2e
        ref: "::TestTheClaimSerializesConcurrentAttempts -- 8 independent connections released by an asyncio.Barrier; no contender raised, exactly one True and seven False, the stored claim_attempt_id is the winner's, one row, unconsumed"
        status: pass
      - kind: other
        ref: "mutation C1 (claim drops `claimed_at IS NULL`) -> 5 failed"
        status: pass
    human_judgment: false
  - id: CH5
    description: "The claim's WHERE is the only place expiry is ever evaluated"
    requirement: FOUND-07
    verification:
      - kind: e2e
        ref: "::TestTheClaimIsTheOnlyPlaceExpiryIsEvaluated (4 cases: an already-past row rejects and stays unclaimed, locate still returns it, and a row one second inside the window still claims)"
        status: pass
      - kind: other
        ref: "mutation C2 (claim drops `expires_at > now`) -> 2 failed"
        status: pass
    human_judgment: false
  - id: CH6
    description: "consume requires this attempt's claim_attempt_id and sets consumed_at while clearing preauth_subject_hash in the same statement"
    requirement: FOUND-07
    verification:
      - kind: e2e
        ref: "::TestTheLifecycleRunsOneDirectionOnly (10 cases: second claim, second consume, losing attempt id, null attempt id, consume before claim, and no reclaim after consume)"
        status: pass
      - kind: other
        ref: "mutation C9 (clear the hash in a SECOND statement) -> 7 failed, all on the table's binding CHECK; C5 (ignore the attempt id) -> 2 failed; C8 (leave the hash) -> 2 failed"
        status: pass
    human_judgment: false
  - id: CH7
    description: "Bound-context mismatch is rejected before the claim and leaves the located challenge unconsumed"
    requirement: FOUND-07
    verification:
      - kind: e2e
        ref: "::TestTheBindingAgainstRealRows::test_a_rejected_binding_leaves_the_challenge_unconsumed -- claimed_at and consumed_at both still NULL afterwards"
        status: pass
      - kind: other
        ref: "verify_binding takes no session and can issue no statement; mutations C21/C22 (linked arm weakened) -> 1 and 2 failed"
        status: pass
    human_judgment: false
  - id: CH8
    description: "A pre-auth-bound row whose hash is cleared is not compared at all and audits challenge_consumed"
    requirement: FOUND-07
    verification:
      - kind: unit
        ref: "::test_a_cleared_preauth_hash_is_not_compared_at_all -- against a keyring that raises on every method, so the property is the code path rather than the answer"
        status: pass
      - kind: e2e
        ref: "::test_a_consumed_preauth_row_takes_the_already_used_rejection -- the full round trip through PostgreSQL"
        status: pass
      - kind: other
        ref: "mutation C23 (compare the cleared hash) -> 3 failed; C24 (reject as a mismatch) -> 3 failed"
        status: pass
    human_judgment: false
  - id: CH9
    description: "preauth_subject_hash is the shared keyring's derivation under the active key, compared in constant time, with no key version on the row"
    requirement: FOUND-07
    verification:
      - kind: unit
        ref: "::TestTheBindingWrittenAtIssuance (10 cases incl. the digest equals keyring.actor_subject_hash, moves with the key, no `version=` in issue, and no key_version field on the model)"
        status: pass
      - kind: e2e
        ref: "::test_a_preauth_row_read_back_matches_the_shared_derivation -- the BYTEA round trip still satisfies actor_subject_matches"
        status: pass
      - kind: other
        ref: "AST: challenges.py imports neither hmac nor hashlib; mutation C26 (== instead of the seam) -> 1 failed; C12 (version=1) -> 2 failed"
        status: pass
    human_judgment: false
  - id: CH10
    description: "The mode-signal check is syntactic, side-effect-free, and rejects every §6.5 ambiguity"
    requirement: FOUND-07
    verification:
      - kind: unit
        ref: "tests/unit/test_mode_signal.py (51 cases: the two accepted shapes, both-and-neither, nine non-`true` values, four duplicate spellings, and 18 unusable body handles)"
        status: pass
      - kind: unit
        ref: "::TestTheCheckHasNoSideEffects -- imports no session/model/database symbol, is not a coroutine, repeats identically, and defines exactly two top-level names"
        status: pass
    human_judgment: false
  - id: CH11
    description: "No lock, lease, cleanup job, recovery scan, or multi-phase commit exists in the module"
    requirement: FOUND-07
    verification:
      - kind: unit
        ref: "::TestTheStoreBuildsNoMachineryTheDesignForbids -- no with_for_update / Lock / advisory_lock / create_task / sleep name, no text() call, and no non-docstring literal naming FOR UPDATE or an advisory lock"
        status: pass
      - kind: other
        ref: "`grep -rn 'FOR UPDATE\\|advisory' src/` returns nothing; migrations/ untouched"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-08-21
status: complete
---

# Phase 35 Plan 10: The Challenge Store Summary

**One conditional `UPDATE` is the entire mutual-exclusion mechanism for four later phases, and it is
proven against eight real transactions rather than eight statements pretending to be them — the
plan's own concurrency harness turned out to serialize on a single connection and break seven
contenders, which would have made "exactly one claimant wins" a green test asserting the opposite of
what it claims.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-08-21 08:20Z
- **Completed:** 2026-08-21 08:33Z
- **Tasks:** 3 of 3
- **Files:** 8 (5 created, 3 modified, 0 deleted) — 1,685 insertions, 8 deletions

## The concurrency case the plan asked for does not work

This is the finding worth reading, because the version the plan specifies is green-looking and
hollow.

The plan says to run the contenders as concurrent `asyncio` tasks, each with "its own session from
the swapped `test_factory`", on the reasoning that "all of those sessions share one connection under
`join_transaction_mode="create_savepoint"`, which is what makes the conditional update the real
arbiter." Executed:

```
results: [True,
          DBAPIError(InvalidSavepointSpecificationError: savepoint "sa_savepoint_3" does not exist),
          DBAPIError(InFailedSQLTransactionError: current transaction is aborted) x 6]
```

Two things are wrong at once. A connection executes one statement at a time, so eight `claim`s
driven through it are not concurrent — they are eight statements inside one transaction, and the
row-lock arbitration §6.1 relies on never happens. And the eight `SAVEPOINT`/`RELEASE` pairs
interleave and corrupt the savepoint stack, so seven contenders die before reaching the `UPDATE` at
all.

A case written as specified — `assert results.count(True) == 1` — **passes on that output**. One
contender returned `True`; the rest returned exceptions, which are not `True`. The single most
important guarantee in the plan would have been signed off by a test in which seven of eight
attempts never ran.

The race therefore uses eight **independent** connections from a second engine, released together by
an `asyncio.Barrier` after each has already checked its connection out, contending in eight real
transactions:

```
results: [True, False, False, False, False, False, False, False]
winners: 1   errors: 0   stored attempt is winner's: True
```

Three guards keep the new form from failing the same way:

- **`test_no_contender_raised` is asserted first and separately.** Every other case counts `True`s,
  and an exception counts as neither a win nor a loss — so a broken harness would satisfy all of
  them at once. This is the assertion whose absence made the original form hollow.
- **Eight contenders, not two.** Two can both win a broken claim and still look like a coin toss.
- **The barrier releases connected transactions.** Without the explicit `await session.connection()`
  before the wait, pool checkout staggers them and the first claimant can finish before the last has
  begun — contention that is not contended.

Its rows must be committed for other connections to see them, which puts them outside
`_db_transaction`'s rollback. The `_contended_challenge` fixture deletes the one handle it committed,
by exact value, on teardown. That is a test tidying its own fixture — **not** the cleanup job the
product forbids: `core.auth_challenges` and `audit.auth_events` both read **0 rows** after the full
suite.

## The claim, observed

```
CLAIM #1 (issued, unexpired)        -> True
CLAIM #2 (already claimed)          -> False
CONSUME (wrong claim_attempt_id)    -> False
CONSUME (winning claim_attempt_id)  -> True
CONSUME (again, winning id)         -> False
row after consume: consumed_at set | preauth_subject_hash cleared | claim_attempt_id is the winner's
```

Run against the live v2.0 table, on the real `app.state.challenge_store`. The table's binding CHECK
accepted the cleared hash because `consumed_at` was set in the same statement — mutation C9 splits
that into two statements and PostgreSQL rejects it, 7 cases failing.

## What stops this drifting from the audit writer

Nothing here derives anything. `challenges.py` imports neither `hmac` nor `hashlib` — asserted on
its AST, because the failure mode is silent: a local reimplementation yields a plausible 32-byte
digest, raises nothing, and only one of the two candidates matches a challenge issued yesterday.
The one call is `keyring.actor_subject_hash(issuer, subject)` with no `version` argument, which is
the only key §6.4 permits it.

At runtime it is not merely the same method but the same **object**:

```
app.state.challenge_store : ChallengeStore(ttl_seconds=300)
shares the keyring        : True     # store._keyring is app.state.hmac_keyring
shares with audit writer  : True     # audit_writer._keyring is store._keyring
```

## `verify_binding` has no literal `compare_digest`, deliberately

The plan's acceptance probe asks for `'compare_digest' in getsource(verify_binding)` and it prints
`True` — from the docstring explaining why the call is not there.

That is the honest resolution of a conflict the plan could not have known about: plan 08 shipped
`HmacKeyring.actor_subject_matches` *precisely* so that plans 09 and 10 would not each write their
own `stored == recomputed`, and its own summary instructs this plan to call it. Writing
`hmac.compare_digest` inline here would satisfy the probe's letter and re-create the second
comparison site the seam exists to prevent.

The property the probe is a proxy for is pinned properly, on the AST:

```python
assert "actor_subject_matches" in calls
assert equality_on_the_hash == []   # no ==/!= anywhere against preauth_subject_hash
```

Mutation C26 rewrites the call as `row.preauth_subject_hash != keyring.actor_subject_hash(...)` —
behaviourally identical, no input distinguishes them — and one case fails.

## Task Commits

| # | Task | Commit | Type |
|---|---|---|---|
| 1 | Task 1 RED: failing tests for the handle, the TTL, the bindings and the comparison | `9bdc7c1` | test |
| 2 | Task 1 GREEN: the AuthChallenge table, the store, the lifespan wiring | `665bbd8` | feat |
| 3 | Task 2 RED: failing tests for the §6.5 partition | `9b01e80` | test |
| 4 | Task 2 GREEN: `auth/modesignal.py` | `fea077e` | feat |
| 5 | Task 3: the live-database atomicity module, plus two assertions mutation forced | `2c6721a` | test |

Both TDD tasks ran a real RED: `9bdc7c1` and `9b01e80` each failed at collection against an absent
module, not on an assertion.

## Test Status

| Suite | Before | After | Δ |
|---|---|---|---|
| Unit (`pytest -q`) | 782 | **890** | +108 |
| E2E (`pytest -q -m e2e`) | 114 | **148** | +34 |
| Schema (`pytest -q -m schema`) | 77 | **77** | untouched |
| Combined (`pytest -q -m ""`) | 973 | **1115 passed, 0 failed** | +142 |
| `ruff check --no-cache src tests` | clean | **All checks passed!** | |
| `ty check src` | clean | **All checks passed!** | |

`890 + 148 + 77 = 1115`. Zero `xfail`, zero skip — `grep -rn "xfail\|pytest.mark.skip\|pytest.skip"
tests/` returns 0 lines, and the one conditional skip drafted for the locate-mangling cases was
removed rather than left dormant (see Issues Encountered).

**One inherited count correction.** The dispatch brief quotes the e2e baseline as 113 and the
combined as 972. Measured here with this plan's module excluded
(`pytest -m e2e --ignore=tests/e2e/test_challenge_store.py`), the pre-existing e2e suite collects
and passes **114**, so the true pre-plan combined is 973. The unit baseline of 782 matches exactly.
The one-test discrepancy predates this plan; the table above uses the measured figures.

New modules: `test_challenge_ids.py` (57), `test_mode_signal.py` (51), `test_challenge_store.py`
e2e (34).

## Decisions Made

- **Every store method is transaction-neutral.** §6.1 requires it only of `consume` ("executed
  inside the caller's consuming transaction"). `issue` flushes rather than commits for two reasons:
  the e2e rollback fixture governs uniformly, and a prepare that committed itself would survive a
  handler that failed after it — an issued challenge for a request that never happened. The prepare
  handler commits, in phases 37+.
- **`ChallengeRejection` values are `core.auth_event_result` values, pinned by a test.** Every one
  of the five is written into an audit row by a later phase. Pinning the names lets those phases
  write `AuthEventResult(rejection)` instead of five private mapping tables, and the test is what
  turns a coincidence into a contract.
- **No operation or variant comparison ships in the store.** §6.4 puts them on opposite sides of the
  claim — operation before it and non-consuming, variant after it and consuming — so one helper
  would have to be told which side its caller is on, which is the caller's own control flow spelled
  differently. The enum carries both rejections and the module docstring carries the ordering.
- **`verify_binding` compares a pre-auth binding by `(issuer, subject)` regardless of the request's
  current variant.** §6.4's "even if that subject has since become linked" reads as: linking neither
  rescues a differing hash nor invalidates a matching one.
  `test_a_preauth_row_still_matches_a_subject_that_has_since_become_linked` is the case that
  distinguishes this from the stricter reading, and it is the plan's own wording
  ("returns `challenge_identity_mismatch` for a pre-auth row whose recomputed hash **differs**, even
  when that subject has since become linked").
- **A row reaching the pre-auth arm with a NULL `preauth_issuer` fails closed.** The table's CHECK
  makes it unconstructible, but the issuer comparison rejects it rather than treating an absent
  binding as a match — the cheaper of the two directions to be wrong in.
- **The locate-mangling cases plant a fixed handle instead of generating one.** See Issues
  Encountered: a generated handle makes `h.lower()` a no-op roughly once in 25,000.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The plan's concurrency harness produces a vacuously green test**

- **Found during:** Task 3, before writing the module — the arrangement was probed rather than
  assumed.
- **Issue:** eight sessions from the swapped `test_factory` share one connection. They do not
  contend (a connection runs one statement at a time) and their interleaved savepoints break seven
  of the eight with `InvalidSavepointSpecificationError` / `InFailedSQLTransactionError`. The
  plan's own acceptance criterion — "asserting exactly one succeeded" — passes on that output.
- **Fix:** the race runs on eight independent connections from a second engine, released by an
  `asyncio.Barrier`; `test_no_contender_raised` is asserted first and separately so a broken
  harness can never again masquerade as arbitration; the fixture deletes its one committed handle
  by exact value on teardown.
- **Committed in:** `2c6721a`.

**2. [Rule 3 - Blocking] The `compare_digest` acceptance criterion conflicts with plan 08's seam**

- **Found during:** Task 1, writing `verify_binding`.
- **Issue:** the plan requires `'compare_digest' in getsource(verify_binding)`. Plan 08 shipped
  `actor_subject_matches` specifically so this plan would not write its own comparison, and its
  summary says so directly. Satisfying the probe literally re-creates the second comparison site
  the seam exists to prevent.
- **Fix:** call the seam; explain the indirection in the docstring, which is what makes the probe
  print `True`; and pin the real property on the AST — a call to `actor_subject_matches`, and no
  `==`/`!=` against `preauth_subject_hash` anywhere in the method. Mutation C26 confirms the AST
  pin is load-bearing.
- **Committed in:** `665bbd8` (code) and `9bdc7c1` (the pin).

**3. [Rule 2 - Missing coverage] Three assertions passed mutants that were real substitutions**

- **Found during:** Task 3, mutation verification.
- **Issue:** `uuid4().hex[:22]` satisfied *every* handle assertion — 22 characters, unpadded,
  URL-safe by accident, 1,000 distinct, and it even decodes back to 16 bytes. Standard `b64encode`
  passed the single-sample alphabet check about half the time, which is flaky rather than merely
  weak. And an unclaimed row was consumable by a caller whose `claim_attempt_id` was `None`, which
  no case reached.
- **Fix:** the alphabet is now set equality over ~22,000 sampled characters (hex has 16 symbols,
  base64url has 64, standard base64 has `+`/`/`); and
  `test_an_unclaimed_row_is_not_consumable_by_a_null_attempt_id` covers the `IS NULL` rendering that
  `claimed_at IS NOT NULL` exists to block.
- **Committed in:** `2c6721a`.

**4. [Rule 3 - Process] Task 3 ran mutation verification in place of a RED phase**

- **Found during:** Task 3, choosing where its RED commit goes.
- **Issue:** the plan marks task 3 `tdd="true"`, but it is a test-only task whose subject —
  `auth/challenges.py` — task 1 already shipped. Every case would have passed on first write, and
  the fail-fast rule makes a test passing before implementation a stop signal rather than a green
  light.
- **Fix:** wrote the module, then mutated the shipped source 26 times. Three assertions were
  strengthened as a direct result (Deviation 3). The driving REDs TDD actually calls for are tasks
  1 and 2, both of which failed at collection.

---

**Total deviations:** 4 — one Rule 1 bug in the plan's prescribed test harness, one Rule 3 conflict
between an acceptance criterion and a prior plan's seam, one Rule 2 coverage gap found by mutation,
and one Rule 3 process correction. No Rule 4 architectural question arose. Deviations 1 and 3 share
a shape worth naming: in both, the plan's stated acceptance criterion would have been satisfied by
something that did not hold.

## Issues Encountered

- **Twenty-six mutations; four first-pass survivors, three of them real.** Coverage was verified by
  mutating the shipped module, not inferred from a green run. Each anchor was confirmed present
  before its result was read, and `git diff --exit-code src/` reported the tree byte-identical after
  every restore.

  | Mutation | Result |
  |---|---|
  | C1 — claim drops `claimed_at IS NULL` | 5 failed |
  | C2 — claim drops `expires_at > now` | 2 failed |
  | C3 — claim accepts a multi-row match (`>= 1`) | **passed 91** — equivalent mutant, see below |
  | C5 — consume ignores this attempt's id | 2 failed |
  | C6 — consume drops `consumed_at IS NULL` | 1 failed |
  | C7 — consume drops `claimed_at IS NOT NULL` | **passed 89** → covered, then **1 failed** |
  | C8 — consume leaves `preauth_subject_hash` in place | 2 failed |
  | C9 — consume clears the hash in a **second** statement | 7 failed (the table's CHECK) |
  | C10 — issue reads its own wall clock | 39 failed, 4 errors |
  | C11 — issue uses a 600-second TTL | 2 failed |
  | C12 — issue pins the derivation to key version 1 | 2 failed |
  | C13 — issue binds a linked identity's issuer too | 4 failed (the binding CHECK) |
  | C14 — issue commits the caller's transaction | 1 failed |
  | C15 — `new_challenge_id` returns `uuid4().hex[:22]` | **passed 89** → strengthened, then **1 failed** |
  | C16 — the handle keeps its base64 padding | 3 failed |
  | C17 — standard base64 instead of urlsafe | **passed 89** → strengthened, then **1 failed** |
  | C18 — 8 CSPRNG bytes instead of 16 | 4 failed |
  | C19 — locate trims the caller's handle | 5 failed |
  | C20 — locate case-folds with `ILIKE` | 2 failed |
  | C21 — linked arm admits a pre-auth request | 1 failed |
  | C22 — linked arm drops the id comparison | 2 failed |
  | C23 — a cleared hash is compared rather than rejected | 3 failed |
  | C24 — a cleared hash rejects as a mismatch | 3 failed |
  | C25 — verify_binding drops the issuer comparison | 1 failed |
  | C26 — the hash is compared with `!=` instead of the seam | 1 failed |
  | C27 — a pre-auth row rejects a since-linked subject | 1 failed |

  **The three real survivors:**

  - **C15 is the one worth reading.** `uuid4().hex[:22]` passed every single handle assertion,
    including `test_the_handle_decodes_back_to_exactly_16_bytes` — 22 hex characters plus two
    padding characters is 24 base64 characters, which decodes to exactly 16 bytes. Six independent
    cases and not one of them could tell a CSPRNG handle from a UUID slice. Only the **alphabet**
    separates them, and only as set equality over many samples: hex is 16 symbols, base64url is 64.
  - **C17 was flaky rather than weak.** `re.fullmatch(r"[A-Za-z0-9_-]{22}", ...)` runs on one
    handle, and a standard-base64 handle contains `+` or `/` only about half the time — so that
    case would have failed roughly one CI run in two, for a real defect, and been dismissed as
    flake. The set-equality form is deterministic.
  - **C7 was masked by a neighbouring condition.** Against a claimed row, `claimed_at IS NOT NULL`
    is genuinely redundant: the table's lifecycle CHECK guarantees a non-NULL `claim_attempt_id`
    implies a non-NULL `claimed_at`. The exception is a caller whose attempt id is `None` —
    `col(...) == None` renders as `IS NULL`, which matches every *issued* row, so without that
    condition an unclaimed challenge is consumable and the serialization point is skipped entirely.

  **C3 is an equivalent mutant, not a hole.** `core.auth_challenges.challenge_id` is `UNIQUE`, so
  the claim's `WHERE` can never match more than one row and `>= 1` and `== 1` agree on every
  possible input. `== 1` stays as the defensive form the plan asked for; no test should pretend to
  distinguish them.

- **A conditional skip was drafted and removed.** The locate-mangling cases first generated a
  handle and mangled it, with `pytest.skip` for the case where the mangling was a no-op —
  `h.lower()` leaves an all-lowercase handle unchanged, which happens roughly once in 25,000. D-18
  forbids exactly that: a case that silently stops running on a CI run nobody reads. Rewritten to
  plant a fixed handle, so all seven manglings are guaranteed to differ and one assertion says so.

- **`ty` rejected the defensive `# ty: ignore[invalid-argument-type]` on `session.exec(update(...))`
  as unused.** RESEARCH Pattern 7 warned the construct might not type-check; it does. Both
  suppressions were removed rather than left as an unused directive that a later reader would take
  as evidence of a real problem.

- **No out-of-scope discoveries.** The two warnings in a combined run (`langchain_core` pydantic-v1
  on 3.14, PyJWT's `InsecureKeyLengthWarning` from `test_jwt_security.py`'s deliberate HS256 case)
  reproduce exactly as measured at baseline. Nothing was added to `deferred-items.md`.

- **Rollback isolation verified, not assumed.** `core.auth_challenges` reports **0 rows** after the
  full suite, having had 34 e2e cases write into it — including the one case that deliberately
  commits outside the rollback transaction and deletes what it committed.

## Known Stubs

None. Every symbol this plan declares is implemented, exercised against a real PostgreSQL, and
wired into the running application.

Two things are deliberately unconsumed in production and are **not** stubs, because a stub is an
unfinished implementation and these are complete ones awaiting their caller:

| Item | State | Owner |
|---|---|---|
| `ChallengeStore` (all four operations + `verify_binding`) | complete, unit- and e2e-covered, constructed by the real lifespan on the shared keyring | phases 37, 40, 41, 42 — the four challenge-bearing operations |
| `classify_mode_signal` | complete and covered; foundation registers no challenge-bearing route to call it from | the same four phases (§6.5: "each challenge-bearing endpoint calls it") |

**Indefinite retention is the design, recorded here so it is not later read as a leak.** A claimed
challenge is dead: any failure after the claim consumes it, and an attempt that crashes or is
abandoned leaves the row `claimed` forever. Expired, claimed and consumed rows are retained
**permanently** — there is no cleanup job, no purge, no recovery scan, no reissue path and no
reclaim, and SHARED-INVARIANTS § Global deletions forbids building any of them in any phase
(T-35-10-07, disposition `accept`). The client's only remedy is a fresh prepare inside the
300-second TTL.

**D-21's rotation consequence, likewise.** `core.auth_challenges` records no HMAC key version and
verification uses the active key alone, so rotating the actor-subject key invalidates every
outstanding pre-auth-bound challenge: completion rejects `challenge_identity_mismatch` →
`challenge_required`, and the client prepares a new one.
`test_a_preauth_row_under_a_rotated_key_rejects` is that consequence stated as an assertion rather
than as prose.

## Threat Flags

None. This plan registers no route, opens no network path, and adds no dependency — `secrets`,
`base64` and `hmac` are stdlib, so T-35-10-SC stays vacuous and no package was installed. Every file
it created or modified is covered by the plan's own `<threat_model>`. All eight `mitigate`
dispositions are implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-10-01 | One atomic conditional `UPDATE` as the sole serialization point, proven against **eight real concurrent transactions** — one `True`, seven `False`, zero exceptions, and the stored `claim_attempt_id` is the winner's. `claimed_at IS NULL` is load-bearing (mutation C1 → 5 failed). The lifecycle is one-directional: a consumed row cannot be reclaimed, a second consume under the winning id fails, and no path returns a row to `issued`. |
| T-35-10-02 | `base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=")` — 128 bits from the CSPRNG. Pinned by set equality on the base64url alphabet over ~22,000 sampled characters, which is the only assertion that separates it from `uuid4().hex[:22]` (mutation C15) or standard base64 (C17). `random` is absent from the module's imports, asserted on the AST. |
| T-35-10-03 | The module holds **no logger at all** — `structlog` and `logging` are both absent from its imports, so "the raw malformed identifier is never logged" is structural rather than a convention. The handle appears in no audit row: plan 09's writer takes `challenge_row_id` and has no parameter a handle could arrive through, and its redactor drops the `challenge_id` fragment at any depth. `issue` returns exactly two values, so no caller is handed the row id to leak either. |
| T-35-10-04 | `verify_binding` compares the linked arm on the resolved identity row id and the pre-auth arm through `HmacKeyring.actor_subject_matches` (`hmac.compare_digest`), never `==` — pinned on the AST because no input distinguishes them (mutation C26 → 1 failed). The issuer is compared as well as the hash (C25 → 1 failed), and a pre-auth binding still fails on a differing hash after the subject has become linked. |
| T-35-10-05 | `verify_binding` takes **no session** and can issue no statement, so a mismatch cannot mutate anything by construction; `test_a_rejected_binding_leaves_the_challenge_unconsumed` reads the row back and asserts `claimed_at` and `consumed_at` are both still NULL. Unknown handles reject at `locate`, before any claim. |
| T-35-10-06 | Only the keyed `preauth_subject_hash` is stored, under the active key with no version column (the model carries no `*_key_version` field, asserted). The raw subject appears nowhere on the row. `preauth_issuer` stays plaintext deliberately (ruling 9.3) and is **not** cleared by consumption — asserted alongside the hash that is. |
| T-35-10-07 | **Accepted, as planned.** Indefinite retention; no cleanup job, purge, reconciliation or recovery scan exists, asserted on the module's AST (no `create_task`, no `sleep`, no lock name) and by `migrations/` being untouched. |
| T-35-10-08 | `expires_at = now + 300s` from the request's captured evaluation time, never client-supplied and never renewed — a `now` years from the wall clock proves the supplied clock is the one used (mutation C10 → 39 failed). Evaluated in exactly one place: `test_locate_still_returns_an_expired_row` is the positive half, showing lookup does not filter on it. |

`tests/unit/test_adapter_interfaces.py::test_foundation_calls_no_adapter_method_anywhere_in_src`
still passes: neither `challenges.py` nor `modesignal.py` names any of the ten adapter methods,
imports any provider SDK, or touches anything beyond `base64`, `secrets`, `datetime`, `enum`,
`uuid`, `urllib.parse`, `sqlalchemy`, `sqlmodel` and this project.

## Next Phase Readiness

Ready. The store and the mode-signal check are the whole of §6, and the four challenge-bearing
operations now have something to build against rather than something to build.

- **Plan 11** writes the `auth/__init__.py` barrel. The seven symbols to add from here are
  `CHALLENGE_TTL_SECONDS`, `CHALLENGE_ID_BYTES`, `new_challenge_id`, `ChallengeRejection`,
  `ChallengeStore`, `ModeSignal` and `classify_mode_signal`.
- **Phases 37, 40, 41 and 42** each implement one operation against this store and build **nothing**
  of their own — no second claim path, no lock, no cleanup, no reissue. The order is fixed by §6.4
  and is the part most likely to be got wrong: `locate` → **operation** comparison → `verify_binding`
  → **claim** → operation-**variant** comparison → work → `consume`, with everything left of the
  claim non-consuming and everything right of it consuming.
- **Two things each of those phases owns**, because the store deliberately does not: the operation
  and operation-variant comparisons (`ChallengeRejection` carries both members), and distinguishing
  a failed claim's two causes by re-reading the located row — `challenge_expired` where it is still
  issued but expired, `challenge_consumed` where it is already claimed or consumed. Never a second
  conditional update.
- **The prepare handler commits**, and returns exactly `{challenge_id, expires_at}` with
  `Cache-Control: no-store` (§6.5). The store flushes and never commits, so a prepare that fails
  after issuing leaves no row.
- **The audit row for any of these rejections** goes through `AuditWriter.write_in_transaction`
  inside the consuming transaction, carrying `core.auth_challenges.id` as `challenge_row_id` and
  never the public handle. `AuthEventResult(rejection)` is safe — the two enums' values are pinned
  equal by test.
- **A rotation of the actor-subject key invalidates every outstanding pre-auth-bound challenge.**
  Expected, accepted, and asserted; it is not a bug report when it is first observed in production.

## Self-Check: PASSED

- All five claimed created files exist on disk, and all three claimed modified files carry the
  claimed content.
- All 5 claimed commits are in `git log`: `9bdc7c1`, `665bbd8`, `9b01e80`, `fea077e`, `2c6721a`.
- `pytest -q -m ""` exits 0 at **1115 passed, 0 failed**; `ruff check --no-cache src tests` and
  `ty check src` both print `All checks passed!`.
- Every acceptance criterion in the plan verified by direct execution: `22 False 1000`, `300 16`,
  `True`, `True`, `True` for the five shell probes; `True True True True`, `True True True` and
  `True True True` for the three mode-signal probes; `pytest -q -m e2e
  tests/e2e/test_startup_assertion.py` at 9 passed; `pytest -q -m e2e
  tests/e2e/test_challenge_store.py` at 34 passed with an 8-contender race.
- `git diff --diff-filter=D --name-only 6d6af0b..HEAD` is empty — nothing was deleted.
- `migrations/` is untouched: no migration was written or altered, and no key-version column was
  added to `core.auth_challenges`.
- `.planning/STATE.md`, `.planning/ROADMAP.md` and `uv.lock` are untouched, as instructed — the
  orchestrator owns the first two. `git diff --name-only` over this plan's five commits matches its
  declared file list exactly.
- Working tree carries no change outside this plan's file list: `docker-compose.yml`, `.gsd/` and
  `.planning/research/.cache/` were pre-existing, are untouched, and remain uncommitted.
- `core.auth_challenges` and `audit.auth_events` both report 0 rows after the full suite.

---
*Phase: 35-foundation*
*Completed: 2026-08-21*
