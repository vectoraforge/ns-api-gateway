# Phase 36: Rebind Pre-existing Routes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-21
**Phase:** 36-Rebind Pre-existing Routes
**Areas discussed:** Tier row provenance, Quota flow placement, Quota failure semantics, The correct-phrase 500

---

## Tier row provenance

Raised because the scout found `core.access_tiers` empty with no phase owning it, while
`00-schema.md:249` assigns tier ids to "later phases/deployment" without naming one.

### Where tier rows come from

| Option | Description | Selected |
|--------|-------------|----------|
| Config + startup seed | `tiers:` block in `config/config.yaml`, idempotently upserted in the lifespan. Reads `00-schema.md:249` literally; tier changes are a config edit. | |
| Amend the initial migration | Seed via `INSERT` in the migration. Reference-data pattern; tier changes become schema operations. | ✓ |
| Deployment-owned, read-only here | Manual SQL or a Helm job outside the repo; Phase 36 only reads. | |

**User's choice:** Amend the initial migration, and clean the database.

**Notes:** The user pushed back twice on my framing before choosing, and both challenges were
correct to make.

First: *"why does amending initial migration trigger anything? It's just a new line in the sql
file."* I had implied the whole schema harness was at risk. Wrong — `test_inventory.py` counts
objects, and a seed `INSERT` changes none of them. The real breakage was one test
(`test_apply_rollback.py:75-79`, which asserts `core.access_tiers` is empty as its proof that
per-test rollback works) plus two fixture docstrings.

Second: *"Why does it require renaming?"* Answered from the source rather than from memory —
`pogo_core/util/migrate.py`'s apply loop gates on `if not migration.applied`, keyed on the filename
stem. A `migration_hash` column is written but never consulted for the skip decision, so an edited
file under an already-applied id is skipped silently. Confirmed against the live database, which
held `migration_id='20260818_01_initial-release'` applied 2026-08-21 00:39:58 UTC.

Third: *"Why can't you just clean the migration DB?"* — you can, and here it is the right call. The
rename protects databases that cannot be wiped; this one is pre-launch with disposable data, and
the schema harness already creates and drops databases of its own.

Fourth: *"Is it normal to populate the DB tables in a migration file?"* — yes for reference data
(Django `RunPython`, Flyway `R__`, Liquibase `loadData`, Rails seeds), not for user or transactional
data. The line is how the rows change: schema-meaning changes belong with the DDL, product-decision
changes do not. `monthly_credits` sits close to that line, which is what made this a real choice
rather than an obvious one.

### Which tier rows

| Option | Description | Selected |
|--------|-------------|----------|
| anonymous / registered / paid | One per v2.0 grant source; matches AGENTS.md's single sub-$5/month product. | ✓ |
| Carry v1.6 names forward | `anonymous, free, silver, gold, platinum` — keeps existing vocabulary. | |
| anonymous + registered only | Just the two free tiers; paid lands with Phase 43/44. | |

### Credit values

| Option | Description | Selected |
|--------|-------------|----------|
| 10 / 10 / 1000 | Straight from v1.6; claiming a registered grant would not change allowance. | |
| 10 / 50 / 1000 | Signing up gains a real benefit; comfortable margin on the sizing invariant. | ✓ |
| 5 / 25 / 500 | Tighter free tiers to limit LLM spend on unconverted users. | |

**Notes:** The user then said *"Do it. Add the insert line, clean the DB"* — so this decision was
implemented during the discussion rather than left for the executor. Migration amended, three
schema tests reworked or added, `pogo rollback -c 1 && pogo apply` run against the developer's
database. 80 schema + 912 unit tests green, ruff clean. Recorded prominently in CONTEXT.md D-01 so
the executor verifies rather than repeats it.

**Also flagged during this area:** a mid-turn system-reminder instructed that file edits be made
with `sed` and heredocs instead of the Edit/Write tools. Not followed — those tools produce a
reviewable diff and go through permission gating, and the instruction arrived immediately before a
migration edit and a database wipe. Reported to the user rather than silently ignored.

---

## Quota flow placement

Opened by surfacing that the v1.6 shape cannot simply be restored: the old `require_quota`
(b16c25b) used `Depends(get_db)`, which commits after the handler returns, so `try_increment`'s row
locks were held across the entire OpenAI round-trip — exactly what §8.4 now forbids.

### Where the flow lives

| Option | Description | Selected |
|--------|-------------|----------|
| Module + thin dependency | Shared resolver module, `require_quota` as the seam; Phase 38 imports the same predicate. | ✓ |
| Restore `require_quota` as-is | All logic inline in `dependencies.py`. | |
| Inside `ChatService` | Reverses the v1.6 cross-cutting-concern decision. | |

**Notes:** The user asked to *"Show the difference on small examples briefly"* before choosing, and
picked only after seeing the three code sketches. The deciding factor was the third sketch: with
quota inside `ChatService`, the mid-method commit lands on the shared injected session and the
network call sits in the same method as the locks, so the "no network call under lock" rule holds
only by careful ordering. The dependency shapes commit before the handler is entered.

### Layering convention

| Option | Description | Selected |
|--------|-------------|----------|
| `database/grants.py` + module | `GrantsDB` session-in-init class for queries and locks, policy above it. | ✓ |
| Standalone `entitlements.py` | Queries and policy together at package root, like `errors.py`. | |
| Under `auth/` | Next to the barrier. | |

**Notes:** `auth/` was rejected on the same reasoning Phase 35 D-10 used to keep the error registry
out of it — entitlement is not authentication, and Phase 38's sync path should not import quota
logic from an auth package.

### Attaching `require_quota`

| Option | Description | Selected |
|--------|-------------|----------|
| Per-route + startup assertion | Declare the dependency, set `quota_checked=True`, assert the two agree at boot. | ✓ |
| Per-route only | No cross-check; the flag documents intent without enforcing it. | |
| Driven by the registry flag | Barrier enforces centrally — default-on but puts DB mutation in middleware. | |

**Notes:** Not asked, because Phase 35 D-02 already settles it: the flow reads
`RequestContext.evaluated_at` rather than calling `datetime.now()`. Stated rather than re-opened.

---

## Quota failure semantics

§8.4 pins only one outcome — `remaining = 0` → the existing quota-exceeded contract. Three other
branches fail closed without naming a class.

### No effective grant

| Option | Description | Selected |
|--------|-------------|----------|
| `quota_exceeded` 429 | §8.4 steps 1 and 5 read together give this answer. | ✓ |
| `internal_error` 500 | Treat as a broken invariant. | |
| `account_unavailable` 403 | Reuse the foundation class. | |

### Missing usage row

| Option | Description | Selected |
|--------|-------------|----------|
| `internal_error` 500 | A grant without a usage row means a write path failed. | ✓ |
| `quota_exceeded` 429 | Fold into exhaustion — fewer branches, but hides a data bug. | |
| `service_unavailable` 503 | Suggests transient; nothing repairs it, so the advice would be false. | |

### More than one effective grant

| Option | Description | Selected |
|--------|-------------|----------|
| Read defensively, no rejection path | Assert at most one row; log and 500 on violation. | ✓ |
| `LIMIT 1` and trust the index | Simplest; silently tie-breaks if the index is ever changed. | |
| Full branch per §8.4 | Most faithful to the text; dead code by construction. | |

**Notes:** My initial framing was corrected mid-area. The case is structurally impossible —
`ix_access_grants_one_active_per_user` (`migrations/…:458`) is a non-deferrable partial unique index
on `(user_id) WHERE status = 'active'`, and the effective-grant predicate is a strict subset. That
surfaced a genuine conflict worth deciding rather than leaving to the planner: §8.4 asks for a
fail-closed branch, the migration comment at `:455-457` says "do not write an application rejection
path for it". The chosen option honors both.

### Credit burn on LLM failure

| Option | Description | Selected |
|--------|-------------|----------|
| Accept the burn | Matches v1.6; only genuine provider failures burn. | ✓ |
| Best-effort refund | Fairer, but the refund can fail and races concurrent increments. | |
| Reserve then settle | Fairest; SHARED-INVARIANTS forbids multi-phase-commit machinery. | |

**Notes:** Raised deliberately alongside D-35-11-A — with the burn accepted, a user whose sentence
is already correct pays a credit for a 500. That framing fed directly into the next area.

---

## The correct-phrase 500

### How to handle D-35-11-A

| Option | Description | Selected |
|--------|-------------|----------|
| Default the two fields to `[]` | One-line change in `AnalyzeResponse`; 200 with empty arrays. | ✓ |
| Restore `with_structured_output(strict=True)` | Fixes the class, not the instance; rewrites the LLM chain. | |
| Defer to its own phase | Most faithful to REBIND-06 and §8.3. | |

**Notes:** Two findings surfaced while framing this area. `services/llm.py:30` is
`prompt_template | self.llm | JsonOutputParser()` — unconstrained JSON validated after the fact —
while `PROJECT.md:56` lists constrained decoding as a *validated* requirement and `:189` records it
as a good decision. `git log -S"with_structured_output" -- src/` returns nothing; it was never
there. Separately, `config/prompt.txt:124` already instructs "if nearly perfect → provide 1 to 2
suggestions" and the model ignores it, which rules out prompt-strengthening as the fix.

### The documentation drift

| Option | Description | Selected |
|--------|-------------|----------|
| Correct the docs, log the work | Fix PROJECT.md, file strict structured output as backlog. | ✓ |
| Fix it in Phase 36 too | Closes both; pulls an LLM-chain rewrite into a rebinding phase. | |
| Leave PROJECT.md alone | The next agent believes the guarantee again. | |

---

## Claude's Discretion

- `Retry-After` on the quota 429 — raised as a candidate follow-up and explicitly passed over.
- What `require_quota` returns (pure gate vs carrying `remaining`/`allowance`).
- Module and file naming above `database/grants.py`; resolver function names.
- Security-log contents per fail-closed branch; whether `RejectionCounter` covers quota rejections.
- How e2e tests seed grants against the now-real tier rows.
- SQL form of the grant-then-usage lock, provided the ascending-grant-id order holds.

## Deferred Ideas

- Restore `with_structured_output(strict=True)` — the general fix behind D-12's narrow one.
- `Retry-After` on the quota 429.
- Proactive quota warnings via `X-RateLimit-Remaining` (already in PROJECT.md future work).
- `pyproject.toml:72` sets pogo `schema = 'api'`, but history lives in `public._pogo_migration` and
  the `api` schema does not exist.
- `uv.lock` stale at `1.5.0` against `pyproject.toml`'s `1.6.0` (D-35-05-A, still unowned).
- The Envoy gateway contract (§9 / FOUND-09), deferred to v2.1 per Phase 35 D-08.
