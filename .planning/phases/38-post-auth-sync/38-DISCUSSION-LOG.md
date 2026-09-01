# Phase 38: POST /auth/sync - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-01
**Phase:** 38-post-auth-sync
**Areas discussed:** SYNC-03 audit obligation, Response body shape, Tripwire parity with quota

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| SYNC-03 — the audit obligation | Rebuild a durable record, or drop the row for the structured log | ✓ |
| Response body shape | Flat or nested; where `identity_provider` sits | ✓ |
| Tripwire parity with quota | Sync and quota disagreeing on broken data | ✓ |
| Sharing the grant predicate | Non-locking read vs parameterising `lock_effective_grants` | |

Not selected → left to the planner as Claude's discretion, recorded in CONTEXT.md.

Todo cross-reference: four keyword matches offered, none folded.

---

## SYNC-03 — the audit obligation

### Q1: rebuild the durable record, or drop it?

| Option | Description | Selected |
|--------|-------------|----------|
| Drop the row — structured log only | Option (b). No table, no migration rewrite, no HMAC hashing, no details schema, no pre-barrier route metadata. Rejections already emit their events; only a success event would be new | ✓ |
| Rebuild the durable record — full | Option (a). `audit.auth_events` back in the migration with the whole subsystem; honours SHARED-INVARIANTS § Audit as written | |
| Minimal durable row — sync only | Option (c). Table returns, writer stays small; rejection rows from the exception handler | |

**User's choice:** Drop the row — structured log only.
**Notes:** The cost of (a) is almost entirely the table, not the writer — the v2.0 one-migration
constraint means rewriting `20260818_01_initial-release.sql` under a new id, not adding a file.

### Q2: what does the success path emit?

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated event, closed-set branch label only | `auth_sync_succeeded` naming whether an effective grant exists | |
| Dedicated event plus the user id | Actor-attributable telemetry without HMAC hashing; costs bounded cardinality | |
| Nothing new — the request line is the record | The middleware already logs every attempt with path and status | ✓ |

**User's choice:** Free text — "Do you mean whether to write a log line on successful request in
addition to middleware? Of course not, that makes no sense."
**Notes:** The question was first asked in internal shorthand ("the success arm", "the rejection
arm") and rejected: "What arm? Speak English." Re-asked in plain language and answered
unambiguously. No success event is to be added.

### Q3: how is the divergence from SHARED-INVARIANTS recorded?

| Option | Description | Selected |
|--------|-------------|----------|
| Amend SYNC-03, keep the conflict flagged | Dated amendment; FOUND-05 stays in the unresolved-conflicts table as knowingly accepted | |
| Amend and close the conflict | Strike the conflict on the grounds that the owning phase has now decided | |
| Amend SYNC-03 only | Leave roadmap criterion and conflict table for a later phase | |

**User's choice:** Free text — "Remove the invariant." Then, on scope: "Remove all invariants that
require auditing. I have audit removal as a part of this milestone."
**Notes:** None of the three offered options was taken. The developer removed the premise instead:
after the edit there is no surviving invariant text to conflict with, so no entry goes into the
flagged-conflicts table at all. Same move as Phase 37.4, where the invariant asserting the wire
contract was removed rather than carried as a permanent flagged conflict. Scope is milestone-wide,
not sync-specific. The phase briefs are marked verbatim and stay unedited.

### Q4: who performs the removal?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 38 does it | Lands as a task in this phase's plan, since 38 is the first phase that needs it | ✓ |
| Already handled separately | Phase 38 builds against the post-removal spec and touches no spec file | |

**User's choice:** Phase 38 does it.

---

## Response body shape

**Finding surfaced before the question:** the shape is already pinned by
`req~sessions-sync-entitlement-response-shape~1` at
`specs/auth-refactor/01-sessions-and-identity-resolution.md:1078` — the only place the literal JSON
appears in any spec file. Most of this area was therefore not open, and the question was narrowed to
the one field the shape omits.

| Option | Description | Selected |
|--------|-------------|----------|
| Top level, next to `entitlement` | The block is a closed six-field enumeration; the provider is a separate fact about the account | ✓ |
| Inside the `entitlement` block | One flat object for the client; costs a documented divergence from the pinned shape | |

**User's choice:** Top level, next to `entitlement`.

---

## Tripwire parity with quota

| Option | Description | Selected |
|--------|-------------|----------|
| Also 500 — reuse quota's existing errors | `MultipleEffectiveGrantsError`, `MissingUsageRowError`, `UnknownTierError` raised unchanged | ✓ |
| Report zero and null — follow the spec's words | Sync is a reporter, not a validator; only the two spec-named failures fail closed | |
| Split it by whether a grant exists | Same practical outcome as option 1, reached by naming the two cases separately | |

**User's choice:** Also 500 — reuse quota's existing errors.
**Notes:** A deliberate divergence from the brief's literal words, taken because roadmap success
criterion 1 requires every reported value to be what quota would independently act on at the same
instant. Reporting "0 of 500 used" to a client whose every chat request returns 500 is the exact
failure that criterion exists to prevent.

---

## Closing

| Option | Description | Selected |
|--------|-------------|----------|
| Write it | Capture the three decisions; 43/44/46 keep their "owning phase decides" wording | |
| Settle 43/44/46 too | Rewrite APPLEHOOK-02, PLAYHOOK-03 and SIGNOUT-02's audit half here | ✓ |
| More gray areas | Something else about the endpoint is still open | |

**User's choice:** Settle 43/44/46 too.
**Notes:** Consequence flagged during the summary: removing the invariants unblocks all three
sibling requirements by the same stroke, leaving three requirement entries pointing at a mechanism
the milestone has removed. SIGNOUT-01 and SIGNOUT-02's fail-closed half stay fully binding — only
the audit half is settled.

## Claude's Discretion

- How the effective-grant predicate stays one definition across the locking (quota) and non-locking
  (sync) readers.
- Where the route lives, given `routers/auth.py`'s deliberately unnarrowed router-level dependency.
- Test placement and depth within the existing `tests/unit` + `tests/e2e` split.

## Deferred Ideas

- Grace-period transparency; `X-RateLimit-Remaining` proactive quota warnings — both in PROJECT.md
  § "Known areas for future work", neither in sync's pinned response shape.
- Restoring rate limiting to the `/auth` surface — knowingly absent this milestone.
- Four pending todos reviewed, none folded: `admission-holds-a-db-connection`,
  `breaker-check-moved-to-admission`, `message-ordering-is-unspecified`, `secret-manager-integration`.
