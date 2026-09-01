# Phase 38: POST /auth/sync - Context

**Gathered:** 2026-09-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `POST /auth/sync` — the strictly read-only auth-state reconciliation surface clients call
after sign-in, after a lost response from a state-changing auth operation, and after losing the
create-user race. One request returns the caller's effective grant, the current period, the
month's usage and the stored registration state, all derived from one captured evaluation time.
The handler mutates nothing.

The phase also lands the milestone's **audit removal** in the binding specification (D-03, D-04):
the decision Phase 37.1 flagged forward as SYNC-03 is made here, and the spec text that mandated
the deleted mechanism is removed rather than left as a standing conflict.

**Out of scope:** the `auth_sync` backend rate-limit entry the phase brief mandates (the engine was
deleted from the product by Phase 35 D-05, and Phase 37.2 found no HTTPRoute matches `/auth` at
all — the auth surface is knowingly unlimited this milestone); `GET /users/me` (Phase 39, which
re-reports `identity_provider` from the same column); any grant creation, flip, repair or rollover;
challenge machinery; any Firebase Admin or `providerData` read.

</domain>

<decisions>
## Implementation Decisions

### The audit obligation (SYNC-03)

- **D-01: No durable audit record. The obligation is dropped, not rebuilt.** Phase 37.1 (D-01)
  deleted `audit.auth_events`, its writer and every call site before this phase was built; SYNC-03
  was flagged forward for Phase 38 to decide. **Decided: option (b).** Rebuilding the subsystem —
  the table back in the migration, HMAC-SHA-256 actor hashing with key versioning, the
  `{schema_version, context, verification, resolved, mutation, failure}` details shape, route→
  operation metadata readable before the barrier — is not warranted for a read-only endpoint's
  attempt telemetry, and would reopen the cost argument that removed it. SYNC-02 makes sync
  strictly read-only, so the row was never a mutation record.
  — **Reversibility:** costly — rebuilding means rewriting `migrations/20260818_01_initial-release.sql`
  under a new id (the v2.0 constraint forbids incremental migrations), not adding a file.

- **D-02: Nothing new is logged either. No success event is added.**
  `RequestLoggingMiddleware` (`src/nativespeaker/api/logs.py`) already emits one `request` line per
  attempt carrying `request_id`, `method`, `path` and `status_code`, and `/auth/sync` is not in
  `_EXCLUDED_PATHS`. Rejections already emit their own named events through `app_error_handler`,
  under exactly the internal-result names the spec uses — `invalid_external_jwt`,
  `pre_auth_identity_not_allowed`, `historical_identity`, `blocked_user` — because
  `AppError.log_level` defaults to `WARNING`. A second line saying a 200 succeeded is duplication.
  **Do not add an `auth_sync_succeeded` event, a user id label, or any per-attempt telemetry.**

- **D-03: The audit invariants are removed from `SHARED-INVARIANTS.md`, not diverged from.**
  Strike § "Audit" and every other clause in that file that requires an audit row. Audit removal is
  a milestone-level decision by the developer, not a sync-specific carve-out. No new entry goes into
  the flagged-conflicts table: after the edit there is no surviving invariant text to conflict with.
  This follows the precedent set in Phase 37.4, where the developer removed the invariant asserting
  the wire contract rather than carry a permanent flagged conflict.
  — **Reversibility:** one-way in practice — this edits the binding specification at
  `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md`, which overrides every
  phase brief. Restoring it would require re-deciding the milestone's audit posture.

- **D-04: Phase 38 also settles the three sibling requirements blocked on the same mechanism.**
  `APPLEHOOK-02` (Phase 43), `PLAYHOOK-03` (Phase 44) and `SIGNOUT-02`'s audit half (Phase 46) were
  each flagged forward by Phase 37.1 with "the owning phase must decide". Removing the invariants
  settles all three by the same stroke, so their REQUIREMENTS.md entries are rewritten here to say
  the obligation is gone — rather than leaving three requirements pointing at a mechanism the
  milestone has removed and three later phases re-deciding a settled question.
  **`SIGNOUT-01` and `SIGNOUT-02`'s fail-closed half are untouched and stay fully binding**: an
  indeterminate or failed revocation must still never report success. Only the audit half is settled.

- **D-05: Documentation deliverables.** A dated `SYNC-03` amendment in `.planning/REQUIREMENTS.md`
  recording the decision and its grounds; roadmap success criterion 4 for Phase 38 rewritten from
  the durable-row obligation to what is actually built; the three sibling requirement entries
  amended per D-04. The phase briefs under `specs/auth-refactor-phases/` are marked
  "verbatim — do not edit" and are **not** edited; the removed invariants and the amendment carry
  the decision.

### The response

- **D-06: The `entitlement` block is spec-pinned; `identity_provider` sits beside it at top level.**

  ```json
  {"entitlement": {"type": "...", "status": "...", "tier_id": null,
                   "monthly_credits": null, "current_period": "2026-09", "monthly_used": 0},
   "identity_provider": "google"}
  ```

  The six-field block comes verbatim from `req~sessions-sync-entitlement-response-shape~1`. The
  provider is a separate fact about the account, not part of the entitlement, and the block is a
  closed enumeration. `expired` and `revoked` never appear: the public status enum is exactly
  `none | active`. `current_period` and `monthly_used` are never null.
  — **Reversibility:** costly — a published client contract; Phase 39's `/users/me` reports the same
  `identity_provider` value from the same column and should read consistently.

### Broken data

- **D-07: Sync fails closed exactly where quota fails closed, reusing the existing error classes.**
  `MultipleEffectiveGrantsError`, `MissingUsageRowError` and `UnknownTierError` (all in
  `src/nativespeaker/api/errors.py`, all `InternalError` at `log_level = ERROR`) are raised by sync
  unchanged. This is a **deliberate divergence from the spec's literal words**: the brief says
  `monthly_used` is `0` whether the usage row is missing or names an earlier period, and it says
  only two failures are tripwires. But `services/quota.py::charge` refuses a grant whose usage row
  is missing or whose tier has no row, and roadmap success criterion 1 requires every reported value
  to be what quota would independently act on at the same instant. Reporting "0 of 500 used" to a
  client whose every chat request returns 500 is the exact lie that criterion exists to prevent.
  The zero-grant case is unaffected: no effective grant reports `type = none, status = none,
  monthly_used = 0`, which is consistent with quota's own refusal on that path.

### Claude's Discretion

- **How the effective-grant predicate stays one definition.** `GrantsDB.lock_effective_grants`
  (`src/nativespeaker/api/crud/grants.py`) holds the predicate the spec calls shared, but takes
  `SELECT … FOR UPDATE`; sync must take no locks. Whether that becomes a non-locking sibling method,
  a parameter on the existing one, or something else is the planner's call — the binding constraint
  is that sync and quota must not carry two copies of the predicate that can drift apart.
- **Where the route lives.** `routers/auth.py`'s router-level dependency is `Depends(get_identity)`,
  deliberately unnarrowed so an already-linked caller gets a 409 on create-user. `/auth/sync` needs
  `get_linked_identity` (403 `preauth_identity_not_allowed` for an unlinked caller) — as a
  route-level dependency, a separate router, or otherwise. Planner's call.
- **Test placement and depth**, within the existing `tests/unit` + `tests/e2e` split.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding specification (overrides phase briefs on conflict)
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — binds every phase.
  **This phase edits it**: § "Audit" and every other audit-row clause are removed (D-03). § "Rate
  limits" is already dead per Phase 35 D-05. Read § "Global deletions" and § "Fail-closed defaults"
  before planning.
- `/home/init/native-speaker/specs/auth-refactor-phases/03-sync.md` — the phase brief. Marked
  verbatim, not edited. Its audit obligations under "This phase adds" and "Security hardenings" are
  superseded by D-01/D-02; its `auth_sync` rate-limit entry is superseded by Phase 35 D-05.

### The source specification
- `/home/init/native-speaker/specs/auth-refactor/01-sessions-and-identity-resolution.md`
  § "/auth/sync Read-Only Contract" (:1057) and § "API: POST /auth/sync" (:1272).
  **`req~sessions-sync-entitlement-response-shape~1` (:1078) is the literal response shape** —
  the only place it appears anywhere.
- `/home/init/native-speaker/specs/auth-refactor/07-quota-and-access-enforcement.md`
  § "Effective Access Tier" — `req~quota-shared-effective-grant-predicate~1` (:92) is the one
  definition of grant currentness, applied identically by quota enforcement and by sync;
  `req~quota-auth-sync-no-grant-defaults~1` (:85) is the zero-grant answer.

### Project planning
- `.planning/REQUIREMENTS.md` § SYNC (:190-197) — SYNC-01/02/03 and the flagged-forward note this
  phase resolves. Also § UPGRADE/APPLEHOOK/PLAYHOOK/SIGNOUT entries amended per D-04, and the
  flagged-conflicts table at :461.
- `.planning/ROADMAP.md` Phase 38 (:475-485) — success criteria; criterion 4 is rewritten by D-05.
- `.planning/PROJECT.md` § Constraints — the one-migration rule and the spec-authority rule.
- `ns-api-gateway/AGENTS.md` — the layering rule (37.5 D-01) and the docstring/comment rules
  (37.4 D-12) every file written by this phase must follow.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/dependencies.py::get_linked_identity` — the barrier, already built and already raising
  `PreAuthIdentityNotAllowed` (403) for an unlinked caller. `get_identity` above it raises
  `InvalidExternalJwt` (401) for a bad or absent token, and `IdentitiesDB.resolve` raises
  `HistoricalIdentity` / `BlockedUser` (403 `account_unavailable`) and `IdentityUnresolvable` (500)
  for the orphan-user case the spec names as a tripwire. **Every error path this endpoint owes
  already exists.** Sync consumes the resolved `Identity` and never re-verifies.
- `crud/grants.py::GrantsDB` — `lock_effective_grants` carries the exact effective-grant predicate
  (`status == active AND starts_at <= now AND (ends_at IS NULL OR ends_at > now)`, ordered by id,
  no `.limit()` so a second row is visible), `lock_usage`, and `monthly_credits`. All three take
  `FOR UPDATE`; sync needs the same reads without locks.
- `services/quota.py::QuotaService.charge` — the reference implementation of the same read: period
  as `evaluated_at.strftime("%Y-%m")`, the stale-period rule, and the three fail-closed tripwires
  D-07 reuses.
- `errors.py` — `MultipleEffectiveGrantsError`, `MissingUsageRowError`, `UnknownTierError`,
  `IdentityUnresolvable`. No new error class is needed by this phase.
- `schemas/auth.py::Identity` — the frozen dataclass carrying the resolved `User` and
  `ExternalIdentity` rows; `identity.provider` is the sole source of `identity_provider`.

### Established Patterns
- **Layering (37.5 D-01, in `AGENTS.md`):** handler in `routers/`, logic in `services/`, every query
  in `crud/`, response body in `schemas/`. A new response model belongs in `schemas/auth.py`.
- **One captured instant per request:** `get_chat_service` and `get_auth_service` both pass
  `evaluated_at=datetime.now(UTC)` from the dependency, and nothing downstream reads the clock
  again. Sync's single-evaluation-time rule is this pattern, not a new mechanism.
- **Structured-log labels come from a closed set** — a fixed branch name, never an id or raw path.
- **Docstring/comment bar is 0 by default** (37.5): a comment states a rule or a why, never a step.

### Integration Points
- `app/main.py` includes the routers; `tests/unit/test_app_wiring.py` asserts the public-path set
  and that the pre-auth-callable route resolves identity — a new route must satisfy it.
- `routers/auth.py` is currently two handlers behind an unnarrowed `Depends(get_identity)`.
- `migrations/20260818_01_initial-release.sql` is **not touched** — D-01 means no schema change,
  so `tests/schema/` (`EXPECTED_AUDIT_TABLES = {"subscription_events"}`) stays as is.

</code_context>

<specifics>
## Specific Ideas

- The developer's words on the success log: a second line for a successful request "makes no sense"
  when the middleware already logs one. Attempt telemetry is the middleware line — nothing more.
- On the standing conflict with the binding spec: "Remove all invariants that require auditing.
  I have audit removal as a part of this milestone." Audit removal is milestone-wide policy, not a
  concession negotiated per phase.
- Plain, concrete language is expected in questions and in writing. Internal shorthand ("the
  rejection arm", "the success arm") was rejected outright.

</specifics>

<deferred>
## Deferred Ideas

- **Grace-period transparency** and **`X-RateLimit-Remaining` proactive quota warnings** — listed in
  PROJECT.md § "Known areas for future work"; neither is in sync's spec-pinned response shape.
- **Restoring any rate limiting to the `/auth` surface** — knowingly absent this milestone
  (Phase 35 D-05, `37.2-SECURITY.md` AR-01); the gateway contract is deferred to v2.1 (D-08).

### Reviewed Todos (not folded)
All four keyword matches were reviewed and left out — none touches a read-only auth endpoint:
- `admission-holds-a-db-connection` — LLM admission/resilience, write path.
- `breaker-check-moved-to-admission` — LLM resilience.
- `message-ordering-is-unspecified` — chats.
- `secret-manager-integration` — config; reviewed and declined for the sixth consecutive phase.

</deferred>

---

*Phase: 38-post-auth-sync*
*Context gathered: 2026-09-01*
