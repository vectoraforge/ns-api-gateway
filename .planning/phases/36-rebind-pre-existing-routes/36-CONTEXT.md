# Phase 36: Rebind Pre-existing Routes - Context

**Gathered:** 2026-08-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Put the nine pre-existing routes behind the barrier and rewire the chat quota path onto the grant
model, restoring a running application — `01-foundation.md §8`, requirements REBIND-01 … REBIND-06.

**Most of §8 already landed in Phase 35.** The scout found REBIND-01, -02, -03 and the handler side
of -06 already implemented, so this phase is much narrower than the roadmap entry suggests:

| Requirement | State entering Phase 36 |
|---|---|
| REBIND-01 partition membership | **Done.** `auth/registry.py:68-77` declares all eight routes with §8.1 metadata; the enumeration assertion runs at real startup (D-14). |
| REBIND-02 off the audited path | **Done.** `auth/telemetry.py` ships the bounded counter and the structured security log; the barrier writes no audit row for these routes. |
| REBIND-03 shared error taxonomy | **Done.** The unified registry at `errors.py` (Phase 35 D-09) owns auth and business classes alike. |
| REBIND-04 | **Void.** Phase 35 D-05 deleted backend rate limiting; the `quota_checked_request` admission entry does not exist. |
| REBIND-05 quota on grants | **Not started.** The whole of this phase. No model, DB layer, or dependency exists for `core.access_grants`, `core.access_tiers`, or `core.user_monthly_usage`. |
| REBIND-06 v1.6 behavior restored | **Partial.** Handlers already read `get_linked_identity()`; the chat POSTs currently enforce no quota at all. |

So the work is: the grant-backed quota flow, its wiring, its failure branches, and proving the four
already-done requirements hold. Planning should verify the table above against the code rather than
assume it — but should not rebuild what is already there.

**Out of scope:** any `/auth/*` route, `GET /users/me`, the provider-callback routes, grant or
identity *mutation* of any kind (Phase 41/42 create grants; this phase only reads and increments
usage), and the Envoy contract (§9, deferred to v2.1 per Phase 35 D-08).

</domain>

<decisions>
## Implementation Decisions

### Tier seeding — ALREADY IMPLEMENTED, NOT YET COMMITTED

- **D-01:** `core.access_tiers` is seeded **as reference data in the initial migration**, not from
  config at startup. Three rows, one per v2.0 grant source: `anonymous` (10 credits),
  `registered` (50), `paid` (1000). `manual` grants name whichever tier the issuance chooses rather
  than having their own. This **overrides `00-schema.md:249`** ("Phase 00 seeds NO tier rows — tier
  ids are configuration owned by later phases/deployment"), and is recorded here as the required
  SHARED-INVARIANTS conflict flag rather than resolved silently. Rationale: no phase in the roadmap
  ever claimed tier seeding, so the table stayed empty and every grant path (36, 41, 42, 43) had
  nothing to FK against. — **Reversibility:** costly — `monthly_credits` changes now require editing
  the migration and clearing pogo's history row (or renaming the file to a new id), not a config
  edit. `07-claim-registered-grant.md:59`'s sizing invariant (`registered >= anonymous`) constrains
  any future value change.

- **D-02:** `registered` (50) is deliberately larger than `anonymous` (10). That ordering is what
  makes `07-claim-registered-grant.md:59`'s carry-over safe: a registered claim moves the superseded
  anonymous grant's `monthly_used` across with no reset, clamp, or prorate, so the smaller-anonymous
  ordering guarantees the carried value can never exceed the new allowance.

**Executor: this is already applied to the working tree and the developer's database. Do not
redo it. Verify, then carry it into the phase's commits.** What exists:

- `migrations/20260818_01_initial-release.sql` — the `INSERT INTO core.access_tiers` and a comment
  block recording the override. The old "this migration seeds NO tier rows" comment is gone.
- `tests/schema/test_apply_rollback.py` — `test_previous_test_rows_were_rolled_back` no longer
  asserts `core.access_tiers` is empty; a new `test_only_the_seeded_tiers_survive` asserts the
  surviving ids equal the seeded set (stricter than a count, which a leak plus a missing seed row
  could cancel out). New `TestSeededTiers` pins the three credit values and the sizing invariant.
- `tests/schema/conftest.py` — the `tier` fixture docstring corrected; it inserts randomised
  `tier_<hex>` ids that do not collide with the seeded set.
- The developer's database was rolled back and re-applied (`pogo rollback -c 1 && pogo apply`).
  Every table was empty; nothing was lost. Verified: 17 tables, three tier rows, history row
  re-created.
- Verified green at the time of writing: 80 schema tests, 912 unit tests, ruff clean.

### Quota flow (REBIND-05)

- **D-03:** The flow lives in a **shared resolver module over a `database/grants.py` DB class, with
  `require_quota` as a thin `Depends()` seam**. `GrantsDB` follows the established session-in-init
  convention (`ChatsDB` is the model) and owns the queries and locks; the policy — effective-grant
  resolution, rollover, allowance arithmetic — sits above it; `require_quota` in
  `app/dependencies.py` is the FastAPI attachment point. Rationale: Phase 38 (`/auth/sync`) needs the
  identical effective-grant predicate and tier join, and its success criterion 1 demands sync "match
  what quota enforcement would independently act on at the same instant". One shared resolver makes
  that structurally true instead of two implementations hoping to agree. — **Reversibility:** costly
  — Phase 38 imports this seam by name.

- **D-04:** **The quota transaction commits before the LLM call.** `require_quota` opens its own
  session from `app.state.session_factory`, runs the locked transaction, and commits — it does not
  use `Depends(get_db)`. This is a real change from v1.6, not a restyling: the old `require_quota`
  (b16c25b) took `Depends(get_db)`, which commits *after* the handler returns, so `try_increment`'s
  row locks stayed open across the entire OpenAI round-trip. §8.4's "no store/provider/network call
  while the locks are held" forbids exactly that. Running as a dependency means the commit happens
  before the handler body is entered, so the rule holds by construction rather than by careful
  ordering inside a method that also makes the network call. — **Reversibility:** reversible.

- **D-05:** `require_quota` is **attached per-route on the two chat POSTs**, `quota_checked=True` is
  set on their registry entries, and **the lifespan assertion is extended to verify the two agree**.
  Without the cross-check the flag documents intent without enforcing it, and a route that declares
  `quota_checked` but forgets the dependency serves requests free — invisible until someone audits
  billing. This is the same drift §2.3 already polices for category membership. Rejected: driving
  enforcement from the registry flag inside the barrier — that puts DB locking and mutation in
  middleware, and §8.4 sequences quota as a separate step "evaluated only after barrier admission",
  not as part of it.

- **D-06:** The flow reads **`RequestContext.evaluated_at`** (`auth/context.py:92`) and never calls
  `datetime.now()`. Phase 35 D-02 already forbids recomputing it; §8.4 requires every derivation —
  grant selection, current-period computation, the usage read — to come from that one captured time,
  so two reads within a request cannot straddle a period boundary.

- **D-07:** `GET /chats`, `GET /chats/{chat_id}`, and `DELETE /chats/{chat_id}` are **not**
  quota-checked. Only the two POSTs consume credits.

### Quota failure branches

- **D-08:** **No effective grant → `quota_exceeded` (429).** §8.4 step 1 says "No effective grant →
  allowance 0" and step 5 routes allowance 0 to the existing quota-exceeded contract, so this is the
  spec's own answer read across two steps. It is also the honest one: until Phase 41/42 ship, every
  user is in this state, and "allowance used up" describes it better than a 500. **Consequence the
  planner must carry: after Phase 36 lands, every chat POST returns 429 until the claim phases
  exist.** That is correct behavior, not a regression — but it means "restoring a running
  application" means the app serves and enforces correctly, not that a chat request succeeds
  end-to-end without a hand-inserted grant.

- **D-09:** **Missing `core.user_monthly_usage` row → `internal_error` (500).** §8.4 step 3 requires
  failing closed and never lazily minting the row. A grant without a usage row means a write path
  failed — Phase 41/42/45 create both in one transaction — so this is a broken invariant, not an
  entitlement state. 500 keeps it distinguishable from ordinary exhaustion in logs and alerts.
  Rejected `service_unavailable` (503): nothing repairs it, since SHARED-INVARIANTS forbids
  background healers, so its "retry soon" advice would be false.

- **D-10:** **More than one effective grant is read defensively with no rejection path.** Query
  without `LIMIT 1`, assert at most one row, and on violation log and raise `internal_error`. This
  is a flagged conflict: §8.4 step 1 asks for "log and fail closed, no tie-break", while
  `migrations/20260818_01_initial-release.sql:455-457` says "do not write an application rejection
  path for it; correct callers make it unreachable". Both are honored — there is no recovery branch,
  only an assertion that cannot pass silently. Note the case is **structurally impossible**: the
  non-deferrable partial unique index `ix_access_grants_one_active_per_user` (`:458`) permits one
  `status='active'` row per user, and the effective-grant predicate is a strict subset of that.
  Rejected `LIMIT 1`: if the index is ever dropped or the predicate widened, it silently picks an
  arbitrary grant — the exact tie-break §8.4 forbids.

- **D-11:** **A failed LLM call burns the credit.** The increment is committed before the call
  (D-04) and nothing compensates it. Matches v1.6, so REBIND-06's "behaves as it did in v1.6" holds.
  Circuit-breaker trips and out-of-scope rejections already fail before the LLM call, so only genuine
  provider failures burn. Rejected: best-effort refund (the refund can itself fail, re-locks the same
  rows outside the original transaction, and races concurrent increments) and reserve-then-settle
  (SHARED-INVARIANTS' global deletions forbid multi-phase-commit machinery).

### The correct-phrase 500 (D-35-11-A)

- **D-12:** **Fix it in this phase** by defaulting both fields in
  `models/llm.py::AnalyzeResponse` — `issues: list[Issue] = []` and `suggestions: list[str] = []`.
  A grammatically correct phrase then returns 200 with empty arrays instead of 500. This is a client
  contract change and a knowing, narrow exception to §8.3's "existing non-auth error contracts
  unchanged": the phase's goal is a running application, this is the product's primary route, it
  fails for exactly the input a user gets when their sentence is already right, and under D-11 the
  user is now charged for it. — **Reversibility:** one-way in principle (it changes a published
  response shape), cheap in practice — pre-launch, no clients.

- **D-13:** **Constrained decoding is a documentation defect, corrected here and fixed later.**
  `PROJECT.md:56` lists "Schema-guaranteed LLM responses via `with_structured_output(strict=True)`"
  as a *validated* requirement and `:189` records it as a good decision, but `services/llm.py:30` is
  `prompt_template | self.llm | JsonOutputParser()` — unconstrained JSON validated after the fact.
  `git log -S"with_structured_output" -- src/` returns nothing: it was never in the source. That gap
  is why D-35-11-A is possible at all. This phase **corrects the two PROJECT.md claims** so they stop
  asserting a guarantee the code does not provide, and **files restoring strict structured output as
  a backlog item** with D-35-11-A as its evidence. It does not do the rewrite — that is an LLM-chain
  change needing real-provider e2e coverage, well outside a rebinding phase.

  Note for whoever picks that up: `config/prompt.txt:124` already instructs "if nearly perfect →
  provide 1 to 2 suggestions", and the model ignores it. Strengthening the prompt is not the fix;
  prompt instruction alone is demonstrably not holding.

### Plan-phase addenda (2026-08-21)

Two items `36-RESEARCH.md` surfaced that this CONTEXT.md did not cover. Both were put to the
developer during `/gsd:plan-phase 36` and answered; they are recorded here as binding.

- **D-14:** **Mitigate the D-04 422 credit burn.** The quota dependency must declare the route's
  request body model so FastAPI validates the body *before* the dependency commits. As specified,
  D-04's own-session commit runs ahead of body validation, so a malformed body burns a credit —
  verified by execution on the pinned FastAPI 0.135.1 (D-04 shape → `422 | calls: ['QUOTA-RAN']`,
  committed; the v1.6 `Depends(get_db)` shape → `['open','increment','ROLLBACK']`). That is a v1.6
  regression and REBIND-06 asks for v1.6 parity, so the ~8-line mitigation plus its two thin
  per-route wrappers is in scope. A Wave 0 e2e test (`test_quota.py -k malformed`) must prove a
  malformed body leaves `monthly_used` unchanged. — **Reversibility:** reversible.

- **D-15:** **`docker-compose.yml` and `uv.lock` are out of scope.** Both are modified in the
  working tree and neither is named by D-01. Phase 36 plans must not stage, commit, or revert
  either file; in particular the deferred D-35-05-A `uv.lock` change (including the local-uv
  `revision 2 → 3` bump `deferred-items.md` warns against committing) stays unowned and
  uncommitted. Every Phase 36 commit must scope its `git add` to named paths — no `git add -A`,
  no `git commit -a`. — **Reversibility:** reversible.

### Claude's Discretion

- Whether the `quota_exceeded` 429 carries `Retry-After`. §8.3 asks for it "where computable", and
  seconds to the next UTC month boundary is computable — but the existing `QuotaExceededError` sets
  no `extra_headers()` and v1.6 sent none. Raised in discussion and explicitly passed over.
- What `require_quota` returns — a pure gate (`None`, the v1.6 shape) or a small result carrying
  `remaining`/`allowance` for the `X-RateLimit-Remaining` header already in PROJECT.md future work.
- Module and file naming above `database/grants.py`, and the names of the resolver functions.
- What the structured security log records on each fail-closed branch, and whether the existing
  rejection counter is reused for quota rejections or left to auth rejections only.
- How e2e tests seed grants now that tier rows are real — fixture-inserted grants against the seeded
  tier ids, or randomised tiers via the existing `insert_tier` helper.
- Exact SQL form of the grant-then-usage lock (two statements vs a single locking join), provided
  the fixed ascending-grant-id order holds.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Binding specification

- `/home/init/native-speaker/specs/auth-refactor-phases/01-foundation.md` **§8** — the phase
  specification, roughly lines 396-434. §8.1 partition membership; §8.2 off the audited attempt
  path; §8.3 shared error body; §8.4 the quota flow and lazy rollover, whose five numbered steps are
  the spine of REBIND-05; §8.5 the deletions binding these routes. **§8.4's first paragraph
  (backend rate limits, the `quota_checked_request` entry) is void per Phase 35 D-05 — implement the
  "Quota flow and lazy rollover wiring" list only.**
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — binds every phase
  and **wins over any conflicting phase brief**. Flag conflicts, never resolve them silently. Its
  "Global deletions" list rules out the refund and reserve/settle alternatives in D-11.
- `/home/init/native-speaker/specs/auth-refactor-phases/00-schema.md` — §249 is the tier-seeding
  statement D-01 overrides. Read it before touching `core.access_tiers`.
- `/home/init/native-speaker/specs/auth-refactor-phases/03-sync.md` §42-45 — Phase 38's read path.
  D-03 exists to share the effective-grant predicate with it; read this to size the shared seam.
- `/home/init/native-speaker/specs/auth-refactor-phases/07-claim-registered-grant.md` §59 — the
  tier-sizing invariant and the `monthly_used` carry-over that depends on it (D-02).

### Project planning

- `.planning/REQUIREMENTS.md` — REBIND-01 … REBIND-06, lines 44-51. REBIND-04 is marked void there
  already.
- `.planning/ROADMAP.md` — Phase 36 goal and its five success criteria. Criterion 4's parenthetical
  already records the `quota_checked_request` entry as void.
- `.planning/PROJECT.md` — **needs editing this phase per D-13**: lines 56 and 189 claim constrained
  decoding the code has never had.
- `.planning/phases/35-foundation/35-CONTEXT.md` — Phase 35's D-01 … D-23. D-02 (typed identity
  context, `evaluated_at`), D-05 (rate limiting deleted), D-09/D-10 (error registry), D-16
  (deletions), D-19 (session factory) all bind here.
- `.planning/phases/35-foundation/deferred-items.md` — D-35-11-A in full, with the four-way
  reproduction table. The source for D-12.
- `.planning/phases/34-schema/34-CONTEXT.md` — D-01/D-02 on pogo migration ids, which is why D-01's
  database reset was needed rather than an in-place file edit.

### Current implementation

- `src/nativespeaker/api/auth/registry.py:68-77` — the eight declared routes and the `quota_checked`
  field D-05 sets. `assert_route_enumeration()` is where D-05's cross-check goes.
- `src/nativespeaker/api/app/dependencies.py:89-102` — the comment block recording exactly why
  `require_quota` and `get_current_user` were deleted, and what Phase 36 owes.
- `src/nativespeaker/api/auth/context.py:82-93` — `RequestContext`, including the `evaluated_at`
  D-06 reuses.
- `src/nativespeaker/api/database/chats.py` — `ChatsDB`, the session-in-init convention
  `database/grants.py` follows.
- `src/nativespeaker/api/errors.py:186-190, 364-365` — `QUOTA_EXCEEDED` and `QuotaExceededError`,
  reused unchanged by D-08.
- `src/nativespeaker/api/models/llm.py:22-26` — `AnalyzeResponse`, the two fields D-12 defaults.
- `src/nativespeaker/api/services/llm.py:25-30` — the `JsonOutputParser()` chain behind D-13.
- `migrations/20260818_01_initial-release.sql` — `core.access_tiers` and its seed (~:257-285),
  `core.access_grants` (:376), `ix_access_grants_one_active_per_user` (:458), and
  `core.user_monthly_usage` (:562). The models this phase writes must match these shapes exactly.
- `tests/schema/helpers.py`, `tests/schema/conftest.py` — `insert_tier`, `insert_grant`,
  `insert_user` and the `tier` fixture, already grant-aware.

### Stale — do not trust

- `.planning/codebase/*.md` — captured 2026-02-24, before the rename and the v1.4/v1.5/v1.6
  restructuring. Read the source instead.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `ChatsDB` (`database/chats.py`) is the session-in-init template `GrantsDB` copies — 54 lines, one
  session on `__init__`, ORM constructs only.
- `QuotaExceededError` and its `QUOTA_EXCEEDED` registry entry already exist with the right code and
  429 status. D-08 reuses them verbatim; no new error class is needed for the quota path.
- `RejectionCounter` / `record_rejection` (`auth/telemetry.py`) already implement the bounded
  counter, if quota rejections should be counted the same way.
- `RequestContext.evaluated_at` and `.identity.user.id` remove any need for the quota path to
  re-resolve time or identity.
- The schema test harness (`tests/schema/`) already has `insert_user`, `insert_grant`, `insert_tier`
  and transaction-rollback isolation — usable for grant-path coverage without new fixtures.

### Established Patterns

- **Zero raw `text()` SQL, ORM constructs only** (v1.6). The grant and usage locks must be
  `select(...).with_for_update()`, not raw SQL.
- **`Depends()`-only routes, all DI in `app/dependencies.py`** (v1.3) — D-03/D-05 keep the handlers
  untouched; only the route decorators gain a `dependencies=[...]` entry.
- **HTTP metadata on exception classes, one data-driven handler** — the quota rejections need no
  handler changes.
- **Per-test transaction rollback** — reused for the new grant tests.
- **Fixed global lock order: grant rows `FOR UPDATE` ascending by id, then their usage rows** — a
  v2.0 invariant repeated in Phases 41, 42 and 45. This phase is the first to implement it, so its
  shape becomes the reference the later phases copy.

### Integration Points

- `app/dependencies.py` — `require_quota` returns here, in the space the D-16 comment block reserved.
- `routers/chats.py:46, 62` — the two POST decorators gain the dependency; the handler bodies do not
  change.
- `auth/registry.py` — `quota_checked=True` on the two POST entries, and the new cross-check inside
  `assert_route_enumeration()`.
- `app/lifespan.py` — where D-05's assertion runs, alongside the existing enumeration assertion.
- `models/` — new SQLModel classes for `core.access_grants`, `core.access_tiers`, and
  `core.user_monthly_usage`; `models/users.py:10-14` already documents their arrival.

</code_context>

<specifics>
## Specific Ideas

- The tier ids are named for **grant sources, not price points** — `anonymous`, `registered`,
  `paid`. The v1.6 `free/silver/gold/platinum` vocabulary was considered and dropped: it carried
  four paid tiers for a product that sells one sub-$5/month subscription, and `free` versus
  `anonymous` both mapping to free grants was a name collision waiting to happen.
- D-01's database reset was a `pogo rollback` + `pogo apply`, not a file rename. The rename in
  `PROJECT.md:215` protects databases you cannot wipe; this one is pre-launch with disposable data,
  which is what made the cheaper path correct here. The mechanism is worth carrying forward:
  `pogo_core/util/migrate.py`'s apply loop gates on `if not migration.applied`, keyed on the
  filename stem. A `migration_hash` column is recorded but never consulted for the skip decision, so
  an edited file on an already-applied id is silently skipped, not detected.
- The multi-grant branch (D-10) is unreachable by construction, and that is the point — the
  assertion exists to make a future index change loud rather than to handle a live case.
- After this phase, a chat POST returns 429 for every user until Phase 41 or 42 mints a grant. Both
  the phase goal and its acceptance criteria should be read with that in mind: success is correct
  enforcement, not a successful chat.

</specifics>

<deferred>
## Deferred Ideas

- **Restore `with_structured_output(strict=True)`** — the real fix for the D-35-11-A class of bug,
  and the thing `PROJECT.md:56` already claims exists. Needs the three response models bound as a
  strict schema and real-provider e2e coverage. D-12 ships the narrow instance fix; this is the
  general one. File as a backlog item per D-13.
- **`Retry-After` on the quota 429** — §8.3 asks for it "where computable" and the next UTC month
  boundary is computable. Raised and explicitly passed over; left to Claude's discretion for now.
- **Proactive quota warnings via `X-RateLimit-Remaining`** — already in PROJECT.md's future-work
  list. Whether `require_quota` returns the remaining count (Claude's discretion above) decides how
  cheap this becomes later.
- **`pyproject.toml:72` sets pogo `schema = 'api'` but history lives in `public._pogo_migration`** —
  the `api` schema does not exist in the developer's database. Harmless today; the config line does
  not do what it reads like it does. Not this phase's to fix.
- **`uv.lock` is stale** — pins `1.5.0` against `pyproject.toml`'s `1.6.0` (D-35-05-A in
  `35-foundation/deferred-items.md`). Still unowned.
- **The Envoy gateway contract (§9 / FOUND-09)** — deferred to v2.1 per Phase 35 D-08. Relevant here
  only because §8.3's "gateway 429s carry the shared body" cannot hold until it lands.

</deferred>

---

*Phase: 36-Rebind Pre-existing Routes*
*Context gathered: 2026-08-21*
