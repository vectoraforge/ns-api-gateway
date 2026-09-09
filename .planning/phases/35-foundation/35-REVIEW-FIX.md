---
phase: 35-foundation
fixed_at: 2026-09-08
review_path: .planning/phases/35-foundation/35-REVIEW.md
iteration: 1
fix_scope: critical_warning
findings_in_scope: 9
fixed: 8
skipped: 1
status: partial
---

# Phase 35: Code Review Fix Report

**Source review:** `.planning/phases/35-foundation/35-REVIEW.md`
**Iteration:** 1
**Scope:** CR-01 and WR-01 … WR-08. The seven IN-* findings were out of scope and left alone.

## Summary

- Findings in scope: 9
- Fixed: 8
- Skipped: 1 (WR-03)

Two findings were decided against `specs/auth-refactor-phases/SHARED-INVARIANTS.md`, which binds
every phase and outranks any phase brief. That file settled CR-01 in favour of the fix and settled
WR-03 against it.

## Verification

Run in the main checkout on `gsd/v2.0-authentication-entitlements`, not in a worktree. The
repository is a git submodule, so no worktree was created. Each command was run after every fix and
once at the end; the numbers below are the final run.

```
.venv/bin/ruff check src tests        All checks passed!
.venv/bin/pytest tests/unit -q        1296 passed, 9 warnings
.venv/bin/ty check src                Found 50 diagnostics
```

Baseline was ruff clean, `1283 passed`, `50 diagnostics`. The unit count rises by 13: the fixes add
new cases and add no skips. The ty count is unchanged, so no fix introduced a diagnostic.

`tests/e2e` and `tests/schema` were not run — they need a database that is not available here.
Three fixes touch code those suites cover; the risk on each is noted below.

## Fixed Issues

### CR-01: The DeviceCheck bit is written to Apple before the local transaction commits

**Files:** `src/nativespeaker/api/services/auth.py`, `tests/unit/test_claim_ordering.py`,
`tests/unit/test_claim_precedence.py`
**Commit:** `11b5573`

Confirmed as described, on both claim paths (`auth.py:194` and `:239`). The read keeps its position
before the transaction opens; the write moves after `session.commit()`. The registered path binds
the read's `BitState` to a local so the conversion arm, which reaches no vendor, skips the write.

**The trade-off.** This fails open: a crash after the commit costs the device's bit rather than the
user's granted trial. The inverse — the shipped behaviour — was unrecoverable, because
`SHARED-INVARIANTS.md:59` forbids any reconciliation or background healer, so nothing can ever clear
a bit. The review's own alternative (a durable intent row plus a reconciliation pass) is therefore
not merely heavier, it is prohibited. Reordering was the only permitted fix.

**Why this does not break ANONGRANT-02 / REGGRANT-02.** The requirement (`REQUIREMENTS.md:308`) is
"no provider or network call **while a lock is held**", and `SHARED-INVARIANTS.md` § "Locks and
transactions" says "all remote work runs strictly before the transaction opens **or after it
commits**". Both positions are permitted; the code previously used the first for both calls and now
uses one of each. The runtime check that neither seam call sees an open transaction
(`devicecheck.transaction_open_during == [False, False]`) is unchanged and still passes.

The two ordering tests asserted the stricter of the two permitted positions, so they were updated
rather than deleted: they now assert `read < activate < commit < write`, with the AST test also
asserting the registered write is guarded on the local the new-grant arm binds. Two controls were
added — a synthetic body that writes before its commit, and a synthetic unguarded write — so the
new assertions are not vacuous.

### WR-01: `Chat.messages` has no ordering

**Files:** `src/nativespeaker/api/tables/chats.py`, `tests/unit/test_services.py`
**Commit:** `a899fa7`

Confirmed. Added `sa_relationship_kwargs={"order_by": "Message.id"}`. Verified on the mapper that
the relationship now carries `ORDER BY messages.id`; the control is the sibling `Chat.user`
relationship, whose `order_by` is `False`, so the new assertion fails on an unordered relationship.

### WR-02: `GET /chats/{chat_id}` documents chronological and returns reverse-chronological

**Files:** `src/nativespeaker/api/crud/chats.py`, `tests/unit/test_chats_crud.py` (new)
**Commit:** `7a1c66c`

Confirmed. Chose ascending over rewording the route: it is the client-facing contract already
published, and it matches the order WR-01 gives the LLM history. New unit file compiles the
statement against the postgresql dialect and separately reads the route description, so drift on
either side fails.

**e2e risk: low.** `tests/e2e/test_chat_queries.py::test_get_messages` asserts roles as a set and
does not depend on order.

### WR-04: `docker-compose.yml` no longer supplies the keys `postgres:17` needs

**File:** `docker-compose.yml`
**Commit:** `4ae3bfb`

Confirmed empirically with `docker-compose config` against a copy of `.env.example`: the container
resolved every `DB_*` key and no `POSTGRES_*` key.

**Deviated from the review's suggested fix.** The review proposed documenting `POSTGRES_USER`,
`POSTGRES_PASSWORD` and `POSTGRES_DB` in `.env.example` alongside the `DB_*` ones. That works, but
it stores the same three values twice where the copies can drift, and it leaves `env_file: [.env]`
forwarding the whole file — the Google refresh token, the Firebase test password and the OpenAI key
— into the database container, which needs three variables. Restoring the explicit `environment:`
block that this change set removed fixes the boot failure, needs no change to `.env.example`, and
gives the container exactly the three keys. Verified: it resolves to `POSTGRES_DB: nativespeaker`,
`POSTGRES_PASSWORD: postgres`, `POSTGRES_USER: postgres` and nothing else.

### WR-05: `log_level: FATAL` passes validation and crashes the pod at boot

**Files:** `src/nativespeaker/api/config.py`, `tests/unit/test_logging.py`
**Commit:** `a359cc0`

Confirmed empirically: of the eight names `logging.getLevelNamesMapping()` yields, only `FATAL`
raises `KeyError` from `structlog.make_filtering_bound_logger`.

Narrowed to the five canonical levels, as the review suggested. `WARN` and `NOTSET` do work in both
libraries, so dropping them is a deliberate narrowing rather than part of the bug: one is a
deprecated alias, the other is not a threshold. `config/config.yaml` sets `INFO`, which survives.
The enum is not derived from `structlog.stdlib.NAME_TO_LEVEL` because that name is absent from
`structlog.stdlib.__all__` and structlog's own docstring calls it `_log_levels._NAME_TO_LEVEL`.

A parametrized case now calls `setup_logging` for every level the enum admits, which exercises the
stdlib `root.setLevel` path too, so a name either library cannot take fails in tests rather than at
startup. `import logging` became unused in `config.py` and was removed.

### WR-06: the migration says `last_cross_account_transfer_month` is written by nothing

**File:** `migrations/20260818_01_initial-release.sql`
**Commit:** `f3a7f9a`

Confirmed: `crud/subscriptions.py:168` writes it on the move branch, `services/restore.py:78` reads
it into `month_read`, and that value both feeds the D-10 cap and rides in the CAS predicate. Comment
now states the writer, the reader, and the consequence of dropping the column.

### WR-07: `restore_bound_user_id` documents a binding no code writes

**File:** `migrations/20260818_01_initial-release.sql`
**Commit:** `24d08af`

Confirmed: `grep -rn restore_bound_user_id src` returns only the SQLModel field, and five e2e
assertions check it is still NULL after a move, an adoption and a repeat. Comment now says the
column is reserved and unwritten, and names the monthly cap as the only limit in force. The column
itself is kept — `tests/schema/test_inventory.py` covers the schema surface, and dropping a column
is a decision beyond a comment fix.

### WR-08: `config/config.yaml` documents committed HMAC key material that is not there

**File:** `config/config.yaml`
**Commit:** `8c8a3b0`

Confirmed: the only match for `hmac|subject_hash|blake2|keyring` across `src`, `config`,
`migrations` and `k8s` is the comment itself.

Replaced the false block with the current fact. Kept the second paragraph, on YAML outranking the
environment, because it is true and load-bearing — verified that `MODEL_NAME=OVERRIDDEN` and
`CHATS_LIMIT=999` in the environment leave `gpt-4o-mini` and `50` in place, since
`AppConfig(**yaml_data, ...)` makes them `init_settings`. Also added the missing trailing newline.

## Skipped Issues

### WR-03: `core.auth_challenges` is never swept

**File:** `migrations/20260818_01_initial-release.sql:317`,
`src/nativespeaker/api/crud/challenges.py:26-105`
**Reason: the finding's premise is wrong — indefinite retention is specified, and both suggested
fixes are prohibited.**

The review's factual observations are correct: no code deletes from the table, and an abandoned
challenge keeps its plaintext `preauth_subject` forever. But this is not drift. `SHARED-INVARIANTS.md`
§ "Global deletions — build NONE of these, in any phase" line 59 reads:

> No scheduled cleanup, purge, reconciliation, recovery-scan, or background-healer job of any kind
> (**challenge rows**, empty anonymous users, accounts, vendor bits, provider state — **indefinite
> retention**).

Challenge rows are named explicitly, and indefinite retention is named as the intended state. Both
remedies the review offers — a `CronJob`, or a best-effort sweep from the issue path — are the thing
that clause forbids. That file binds every phase and wins over any phase brief, so a fix here would
be a spec violation, not a repair. Changing the rule is a spec decision, not a code-review fix.

One sub-observation does stand and is left for the orchestrator: `ix_auth_challenges_expires_at`
has no reader, because `locate` keys on `challenge_id` and `claim`'s expiry predicate is served by
the unique index on `challenge_id`. It is an index built for the sweep the invariants forbid.
Removing it needs a new migration and an edit to `tests/schema/test_inventory.py:110`, which lists
it, so it is out of scope for a review fix.

## Follow-ups for the orchestrator

Both are under `.planning/`, which this run did not stage or modify.

1. `.planning/todos/pending/secret-manager-integration.md` states as its rationale that "Phase 35
   puts the versioned HMAC key material … in `config/config.yaml`, which is tracked in git". WR-08
   establishes that this never happened. The todo's residual scope is still real — the DB password,
   the OpenAI key and the Firebase credentials do live in `.env` — but its stated "why now" is
   false and should be rewritten.
2. `.planning/todos/pending/message-ordering-is-unspecified.md` appears to cover the same ground as
   WR-01 and WR-02, which are now fixed. It may be closable.

---

_Fixed: 2026-09-08_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
