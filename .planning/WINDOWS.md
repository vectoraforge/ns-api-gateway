---
schema_version: 1
open_count: 7
waived_count: 1
fixed_count: 5
total_count: 13
last_updated: 2026-09-03T20:26:15.152Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 36 | unrun-verify | src/nativespeaker/api/models/grants.py |  | No committed test round-trips AccessGrant/AccessTier/UserMonthlyUsage against the live schema; verified once by an uncommitted ad-hoc script (36-01 D3) | open |  | 2026-08-22T02:01:11.364Z |  |
| 2 | 36 | stub | src/nativespeaker/api/quota.py |  | consume_quota implements §8.4 step 1 only; a caller holding an effective grant passes the gate uncharged until plan 36-04 lands steps 2-4 | open |  | 2026-08-22T02:31:48.290Z |  |
| 3 | 37 | deviation | .planning/phases/37-post-auth-create-user/37-01-SUMMARY.md |  | Phase 40 lost its database-level provider binding for upgrade_anonymous_to_registered; replacement binding is unowned until Phase 40 plans it | open |  | 2026-08-22T23:18:56.103Z |  |
| 4 | 37 | stub | src/nativespeaker/api/routers/auth.py |  | _lookup_rejected: user_not_found earns 503 where §02 earns 401 auth_required; no audit rows on the lookup/classifier rejections (owner: 37-08 Task 2) | open |  | 2026-08-23T23:13:47.905Z |  |
| 5 | 37 | stub | src/nativespeaker/api/auth/creation.py |  | _insert_account: begin_nested savepoint has no except IntegrityError rollback arm, so a genuine UNIQUE (issuer, subject) race surfaces as a 500 (owner: 37-09 Task 1) | fixed |  | 2026-08-23T23:13:48.007Z | 2026-08-23T23:39:41.117Z |
| 6 | 37 | stub | src/nativespeaker/api/routers/auth.py |  | _challenge_rejected: correct challenge_required class but no per-rejection internal result, audit row, or consumption disposition (owner: 37-08 Task 1) | open |  | 2026-08-23T23:13:48.109Z |  |
| 7 | 37 | stub | src/nativespeaker/api/auth/creation.py |  | _result_for_existing: no blocked-user discrimination; a non-active row audits as historical_identity (owner: 37-09) | fixed |  | 2026-08-23T23:13:48.214Z | 2026-08-23T23:39:44.915Z |
| 8 | 37 | stub | src/nativespeaker/api/routers/auth.py |  | _completion_response maps every non-succeeded result other than identity_already_linked to ACCOUNT_UNAVAILABLE, so provider_account_already_linked (now reachable via 37-09) returns code account_unavailable where §02 step 11 earns operation_not_allowed. Fix: return error_response(CLIENT_CLASS_FOR_RESULT[result]) from auth/creation.py. Not fixable by 37-09 — routers/auth.py is 37-08's file this wave. | open |  | 2026-08-23T23:39:50.861Z |  |
| 9 | 38 | unmet-truth | tests/e2e/test_sync.py |  | Sync's no-lock claim under a genuinely concurrent quota charge is inferred from compiled SQL carrying no FOR UPDATE, never observed live: the e2e harness binds every session to one connection inside an uncommitted transaction, so a second connection cannot see the seeded rows | fixed |  | 2026-09-01T08:38:02.614Z | 2026-09-01T21:16:12.688Z |
| 10 | 40 | deviation | migrations/20260818_01_initial-release.sql |  | Dev database nativespeaker was not re-applied from the edited single migration (40-01 Task 3): every route to a DROP/rollback was refused by the harness permission classifier. The database still holds the pre-shrink seven-label core.auth_operation and the deleted auth_challenges membership CHECK. Fix: run 'uv run pogo rollback --count 1 && uv run pogo apply' from the repo root. | fixed |  | 2026-09-02T10:54:14.489Z | 2026-09-02T10:57:07.747Z |
| 11 | 40 | stub | src/nativespeaker/api/services/auth.py |  | 40-04 tracer: AuthService._apply_upgrade answers three stored-versus-live combinations with the placeholder ProviderTransitionNotAllowed raise instead of their final outcome — (anonymous, anonymous) must become NotLinked(cause=empty), and (google, google) / (apple, apple) with a matching provider_uid must become D-04's idempotent 200. The branch does no uid comparison at all. Plan 40-05 owns the split. | fixed |  | 2026-09-02T20:14:50.902Z | 2026-09-02T20:30:29.466Z |
| 12 | 40 | unmet-truth | src/nativespeaker/api/services/auth.py | 126 | _apply_upgrade's docstring claims it revalidates the caller's locked rows, but only provider is re-checked; identity_state and user.active are not, unlike the admission-time path in crud/identities.py:48-52. An identity retired or a user blocked during the challenge-commit + Firebase round-trip window can still complete an upgrade. WR-01 from 40-VERIFICATION.md. | waived | Accepted for v1: no code path writes identity_state or user.active, so the race requires a manual ops block landing inside the few hundred ms of a specific user's upgrade. A user blocked mid-upgrade is rejected at admission on their very next request, so the worst outcome is a blocked account that is briefly marked registered. Revisit if an automated blocking path is ever added. | 2026-09-02T22:05:11.581Z | 2026-09-02T22:05:20.978Z |
| 13 | 42 | deviation | tests/schema/test_claim_race.py |  | 42-05: the conversion race's loser-separation observable differs from the plan's prediction — no IntegrityError is raised; recorded and asserted as measured | open |  | 2026-09-03T20:26:15.152Z |  |

````json
[
  {
    "id": 1,
    "kind": "unrun-verify",
    "phase": "36",
    "file": "src/nativespeaker/api/models/grants.py",
    "line": null,
    "description": "No committed test round-trips AccessGrant/AccessTier/UserMonthlyUsage against the live schema; verified once by an uncommitted ad-hoc script (36-01 D3)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-22T02:01:11.364Z",
    "resolved_at": null
  },
  {
    "id": 2,
    "kind": "stub",
    "phase": "36",
    "file": "src/nativespeaker/api/quota.py",
    "line": null,
    "description": "consume_quota implements §8.4 step 1 only; a caller holding an effective grant passes the gate uncharged until plan 36-04 lands steps 2-4",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-22T02:31:48.290Z",
    "resolved_at": null
  },
  {
    "id": 3,
    "kind": "deviation",
    "phase": "37",
    "file": ".planning/phases/37-post-auth-create-user/37-01-SUMMARY.md",
    "line": null,
    "description": "Phase 40 lost its database-level provider binding for upgrade_anonymous_to_registered; replacement binding is unowned until Phase 40 plans it",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-22T23:18:56.103Z",
    "resolved_at": null
  },
  {
    "id": 4,
    "kind": "stub",
    "phase": "37",
    "file": "src/nativespeaker/api/routers/auth.py",
    "line": null,
    "description": "_lookup_rejected: user_not_found earns 503 where §02 earns 401 auth_required; no audit rows on the lookup/classifier rejections (owner: 37-08 Task 2)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-23T23:13:47.905Z",
    "resolved_at": null
  },
  {
    "id": 5,
    "kind": "stub",
    "phase": "37",
    "file": "src/nativespeaker/api/auth/creation.py",
    "line": null,
    "description": "_insert_account: begin_nested savepoint has no except IntegrityError rollback arm, so a genuine UNIQUE (issuer, subject) race surfaces as a 500 (owner: 37-09 Task 1)",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-23T23:13:48.007Z",
    "resolved_at": "2026-08-23T23:39:41.117Z"
  },
  {
    "id": 6,
    "kind": "stub",
    "phase": "37",
    "file": "src/nativespeaker/api/routers/auth.py",
    "line": null,
    "description": "_challenge_rejected: correct challenge_required class but no per-rejection internal result, audit row, or consumption disposition (owner: 37-08 Task 1)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-23T23:13:48.109Z",
    "resolved_at": null
  },
  {
    "id": 7,
    "kind": "stub",
    "phase": "37",
    "file": "src/nativespeaker/api/auth/creation.py",
    "line": null,
    "description": "_result_for_existing: no blocked-user discrimination; a non-active row audits as historical_identity (owner: 37-09)",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-08-23T23:13:48.214Z",
    "resolved_at": "2026-08-23T23:39:44.915Z"
  },
  {
    "id": 8,
    "kind": "stub",
    "phase": "37",
    "file": "src/nativespeaker/api/routers/auth.py",
    "line": null,
    "description": "_completion_response maps every non-succeeded result other than identity_already_linked to ACCOUNT_UNAVAILABLE, so provider_account_already_linked (now reachable via 37-09) returns code account_unavailable where §02 step 11 earns operation_not_allowed. Fix: return error_response(CLIENT_CLASS_FOR_RESULT[result]) from auth/creation.py. Not fixable by 37-09 — routers/auth.py is 37-08's file this wave.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-23T23:39:50.861Z",
    "resolved_at": null
  },
  {
    "id": 9,
    "kind": "unmet-truth",
    "phase": "38",
    "file": "tests/e2e/test_sync.py",
    "line": null,
    "description": "Sync's no-lock claim under a genuinely concurrent quota charge is inferred from compiled SQL carrying no FOR UPDATE, never observed live: the e2e harness binds every session to one connection inside an uncommitted transaction, so a second connection cannot see the seeded rows",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-01T08:38:02.614Z",
    "resolved_at": "2026-09-01T21:16:12.688Z"
  },
  {
    "id": 10,
    "kind": "deviation",
    "phase": "40",
    "file": "migrations/20260818_01_initial-release.sql",
    "line": null,
    "description": "Dev database nativespeaker was not re-applied from the edited single migration (40-01 Task 3): every route to a DROP/rollback was refused by the harness permission classifier. The database still holds the pre-shrink seven-label core.auth_operation and the deleted auth_challenges membership CHECK. Fix: run 'uv run pogo rollback --count 1 && uv run pogo apply' from the repo root.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-02T10:54:14.489Z",
    "resolved_at": "2026-09-02T10:57:07.747Z"
  },
  {
    "id": 11,
    "kind": "stub",
    "phase": "40",
    "file": "src/nativespeaker/api/services/auth.py",
    "line": null,
    "description": "40-04 tracer: AuthService._apply_upgrade answers three stored-versus-live combinations with the placeholder ProviderTransitionNotAllowed raise instead of their final outcome — (anonymous, anonymous) must become NotLinked(cause=empty), and (google, google) / (apple, apple) with a matching provider_uid must become D-04's idempotent 200. The branch does no uid comparison at all. Plan 40-05 owns the split.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-02T20:14:50.902Z",
    "resolved_at": "2026-09-02T20:30:29.466Z"
  },
  {
    "id": 12,
    "kind": "unmet-truth",
    "phase": "40",
    "file": "src/nativespeaker/api/services/auth.py",
    "line": 126,
    "description": "_apply_upgrade's docstring claims it revalidates the caller's locked rows, but only provider is re-checked; identity_state and user.active are not, unlike the admission-time path in crud/identities.py:48-52. An identity retired or a user blocked during the challenge-commit + Firebase round-trip window can still complete an upgrade. WR-01 from 40-VERIFICATION.md.",
    "status": "waived",
    "reason": "Accepted for v1: no code path writes identity_state or user.active, so the race requires a manual ops block landing inside the few hundred ms of a specific user's upgrade. A user blocked mid-upgrade is rejected at admission on their very next request, so the worst outcome is a blocked account that is briefly marked registered. Revisit if an automated blocking path is ever added.",
    "recorded_at": "2026-09-02T22:05:11.581Z",
    "resolved_at": "2026-09-02T22:05:20.978Z"
  },
  {
    "id": 13,
    "kind": "deviation",
    "phase": "42",
    "file": "tests/schema/test_claim_race.py",
    "line": null,
    "description": "42-05: the conversion race's loser-separation observable differs from the plan's prediction — no IntegrityError is raised; recorded and asserted as measured",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-03T20:26:15.152Z",
    "resolved_at": null
  }
]
````
