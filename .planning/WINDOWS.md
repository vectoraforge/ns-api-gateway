---
schema_version: 1
open_count: 20
waived_count: 1
fixed_count: 10
total_count: 31
last_updated: 2026-09-12T08:04:34.354Z
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
| 14 | 42 | deviation | .planning/phases/42-post-auth-claim-registered-grant/42-06-PLAN.md |  | 42-06 Task 1: the acceptance criterion requiring 'git status --porcelain -- specs/' to be empty cannot pass — specs/auth-refactor-phases/ is untracked in the parent repo and reports '??' regardless. No spec file was modified; the tracked specs/auth-refactor/ is clean and both brief mtimes predate this phase. | open |  | 2026-09-03T20:43:36.530Z |  |
| 15 | 42 | deviation | .planning/phases/42-post-auth-claim-registered-grant/42-06-PLAN.md |  | 42-06 Task 2: the verify block's allow-list names only 41-*, 42-*, milestones/ and the two ledgers, but phases 34, 36, 37.4 and 37.5 all mention the deleted table in their own artifacts. The task action's rule (leave a completed phase's artifacts as written) was applied instead. | open |  | 2026-09-03T20:43:36.670Z |  |
| 16 | 43 | stub | config/config.yaml |  | Placeholder App Store product id com.nativespeaker.subscription.monthly in app_store.products; no iOS app exists yet, so an operator edits the map. An unmapped id is a logged 500 with nothing written. | open |  | 2026-09-04T22:09:58.987Z |  |
| 17 | 43 | deviation | .planning/REQUIREMENTS.md |  | APPLEHOOK-01 left unchecked by 43-05: 43-CONTEXT.md D-26 assigns the dated amendments and header counts to plan 43-06 | fixed |  | 2026-09-04T23:17:12.416Z | 2026-09-04T23:29:52.559Z |
| 18 | 43 | deviation | .planning/phases/43-post-webhooks-app-store/43-06-PLAN.md |  | 43-06 Task 2: the verify block requires six 43-0*-SUMMARY.md files at the time the task runs, which cannot hold — this plan's own summary is written after Task 2 by construction, as 41-05 and 42-06 both recorded. Read 5 at Task 2 time and 6 after the summary landed. | open |  | 2026-09-04T23:29:52.710Z |  |
| 19 | 44 | unrun-verify | k8s/templates/httproute-webhooks.yaml |  | helm is not installed in this environment, so 'the template still parses as a Helm template' was checked by substituting the Helm expressions and parsing the result with PyYAML, not by rendering with helm | open |  | 2026-09-05T11:11:39.493Z |  |
| 20 | 44 | deviation | tests/schema/test_subscription_ingestion.py |  | 44-05: the plan's absent-grace-end control expected an ineffective grant; a NULL ends_at is effective, so the control was split into an unbounded-grant case and a closed-window case | open |  | 2026-09-05T11:53:19.656Z |  |
| 21 | 44 | deviation | .planning/phases/44-post-webhooks-google-play-rtdn/44-07-PLAN.md |  | 44-07: the plan's specs/ cleanliness gate (git status --porcelain -- specs/) can never pass here — specs/auth-refactor-phases/ has never been tracked in the parent repo, so the gate fires on an untracked path, not an edit. D-22 proved instead by git status --untracked-files=no -- specs/ being empty and by no file under specs/ having a today mtime | open |  | 2026-09-05T12:31:21.640Z |  |
| 22 | 45 | stub | src/nativespeaker/api/services/restore.py | 81 | _verify refuses every provider that is not Apple; 45-02 replaces it with the Play read | fixed |  | 2026-09-08T01:04:03.689Z | 2026-09-08T01:17:08.716Z |
| 23 | 45 | stub | src/nativespeaker/api/services/restore.py | 45 | No stored subscription row raises RestoreSubscriptionNotEntitled; 45-03 replaces it with adoption-with-creation | fixed |  | 2026-09-08T01:04:03.824Z | 2026-09-08T01:39:49.905Z |
| 24 | 45 | stub | src/nativespeaker/api/services/restore.py | 54 | Any owner other than the caller raises RestoreSubscriptionNotEntitled; 45-03 and 45-04 replace it with adoption and the capped move | fixed |  | 2026-09-08T01:04:03.976Z | 2026-09-08T01:39:50.046Z |
| 25 | 45 | stub | src/nativespeaker/api/services/restore.py | 72 | An owner that is another account raises RestoreSubscriptionNotEntitled; 45-04 replaces it with the capped move | fixed |  | 2026-09-08T01:39:55.773Z | 2026-09-08T02:04:51.706Z |
| 26 | 45 | todo | tests/e2e/test_restore_subscription.py |  | TestTheTwoRefusalsOfTheRestoreNotFoundFamily is named for two arms but now holds three; 45-07 corrected the docstring only, because the plan named the class in its acceptance criteria | open |  | 2026-09-08T21:18:51.538Z |  |
| 27 | 45 | unrun-verify | .planning/phases/45-post-auth-restore-subscription/45-09-PLAN.md |  | 45-09 acceptance check 'git diff --quiet -- ../specs' cannot run: ../specs is in the parent superrepo, outside this repository. D-14 proved by file mtime instead. | open |  | 2026-09-08T21:30:16.158Z |  |
| 28 | 45 | todo | migrations/20260818_01_initial-release.sql | 136 | Stale comment: last_cross_account_transfer_month says 'Written by nothing' which D-10 made false. Should read: written by the capped cross-account move only (D-10); one move per subscription per UTC month. Migration not edited (D-14). | open |  | 2026-09-08T21:30:20.962Z |  |
| 29 | 47 | unrun-verify | tests/e2e/test_restore_subscription.py |  | Pre-existing failure not caused by plan 47-01: the four-arms refusal case expects log event proof_rejected, the code emits purchase_proof_rejected. Measured on HEAD 1a3273d with every 47-01 edit reverted. | open |  | 2026-09-12T05:56:25.182Z |  |
| 30 | 47 | unrun-verify | tests/schema/test_claim_race.py |  | Two assertions derive the expected monthly period from the live clock; a run straddling a UTC month boundary would fail | open |  | 2026-09-12T06:28:34.592Z |  |
| 31 | 47 | deviation | tests/unit/test_subscription_attribution.py | 964 | Plan 47-08 measured it red: the control case builds an open term one minute past a module-import NOW, so any run longer than a minute between collection and the case closes the term and ingest raises InternalError. Fails under -m '' (131 s), passes alone. Reproduced with a 65 s post-collection sleep. Introduced by 47-05; not fixed in 47-08, which writes no source. | open |  | 2026-09-12T08:04:34.354Z |  |

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
  },
  {
    "id": 14,
    "kind": "deviation",
    "phase": "42",
    "file": ".planning/phases/42-post-auth-claim-registered-grant/42-06-PLAN.md",
    "line": null,
    "description": "42-06 Task 1: the acceptance criterion requiring 'git status --porcelain -- specs/' to be empty cannot pass — specs/auth-refactor-phases/ is untracked in the parent repo and reports '??' regardless. No spec file was modified; the tracked specs/auth-refactor/ is clean and both brief mtimes predate this phase.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-03T20:43:36.530Z",
    "resolved_at": null
  },
  {
    "id": 15,
    "kind": "deviation",
    "phase": "42",
    "file": ".planning/phases/42-post-auth-claim-registered-grant/42-06-PLAN.md",
    "line": null,
    "description": "42-06 Task 2: the verify block's allow-list names only 41-*, 42-*, milestones/ and the two ledgers, but phases 34, 36, 37.4 and 37.5 all mention the deleted table in their own artifacts. The task action's rule (leave a completed phase's artifacts as written) was applied instead.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-03T20:43:36.670Z",
    "resolved_at": null
  },
  {
    "id": 16,
    "kind": "stub",
    "phase": "43",
    "file": "config/config.yaml",
    "line": null,
    "description": "Placeholder App Store product id com.nativespeaker.subscription.monthly in app_store.products; no iOS app exists yet, so an operator edits the map. An unmapped id is a logged 500 with nothing written.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-04T22:09:58.987Z",
    "resolved_at": null
  },
  {
    "id": 17,
    "kind": "deviation",
    "phase": "43",
    "file": ".planning/REQUIREMENTS.md",
    "line": null,
    "description": "APPLEHOOK-01 left unchecked by 43-05: 43-CONTEXT.md D-26 assigns the dated amendments and header counts to plan 43-06",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-04T23:17:12.416Z",
    "resolved_at": "2026-09-04T23:29:52.559Z"
  },
  {
    "id": 18,
    "kind": "deviation",
    "phase": "43",
    "file": ".planning/phases/43-post-webhooks-app-store/43-06-PLAN.md",
    "line": null,
    "description": "43-06 Task 2: the verify block requires six 43-0*-SUMMARY.md files at the time the task runs, which cannot hold — this plan's own summary is written after Task 2 by construction, as 41-05 and 42-06 both recorded. Read 5 at Task 2 time and 6 after the summary landed.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-04T23:29:52.710Z",
    "resolved_at": null
  },
  {
    "id": 19,
    "kind": "unrun-verify",
    "phase": "44",
    "file": "k8s/templates/httproute-webhooks.yaml",
    "line": null,
    "description": "helm is not installed in this environment, so 'the template still parses as a Helm template' was checked by substituting the Helm expressions and parsing the result with PyYAML, not by rendering with helm",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-05T11:11:39.493Z",
    "resolved_at": null
  },
  {
    "id": 20,
    "kind": "deviation",
    "phase": "44",
    "file": "tests/schema/test_subscription_ingestion.py",
    "line": null,
    "description": "44-05: the plan's absent-grace-end control expected an ineffective grant; a NULL ends_at is effective, so the control was split into an unbounded-grant case and a closed-window case",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-05T11:53:19.656Z",
    "resolved_at": null
  },
  {
    "id": 21,
    "kind": "deviation",
    "phase": "44",
    "file": ".planning/phases/44-post-webhooks-google-play-rtdn/44-07-PLAN.md",
    "line": null,
    "description": "44-07: the plan's specs/ cleanliness gate (git status --porcelain -- specs/) can never pass here — specs/auth-refactor-phases/ has never been tracked in the parent repo, so the gate fires on an untracked path, not an edit. D-22 proved instead by git status --untracked-files=no -- specs/ being empty and by no file under specs/ having a today mtime",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-05T12:31:21.640Z",
    "resolved_at": null
  },
  {
    "id": 22,
    "kind": "stub",
    "phase": "45",
    "file": "src/nativespeaker/api/services/restore.py",
    "line": 81,
    "description": "_verify refuses every provider that is not Apple; 45-02 replaces it with the Play read",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-08T01:04:03.689Z",
    "resolved_at": "2026-09-08T01:17:08.716Z"
  },
  {
    "id": 23,
    "kind": "stub",
    "phase": "45",
    "file": "src/nativespeaker/api/services/restore.py",
    "line": 45,
    "description": "No stored subscription row raises RestoreSubscriptionNotEntitled; 45-03 replaces it with adoption-with-creation",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-08T01:04:03.824Z",
    "resolved_at": "2026-09-08T01:39:49.905Z"
  },
  {
    "id": 24,
    "kind": "stub",
    "phase": "45",
    "file": "src/nativespeaker/api/services/restore.py",
    "line": 54,
    "description": "Any owner other than the caller raises RestoreSubscriptionNotEntitled; 45-03 and 45-04 replace it with adoption and the capped move",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-08T01:04:03.976Z",
    "resolved_at": "2026-09-08T01:39:50.046Z"
  },
  {
    "id": 25,
    "kind": "stub",
    "phase": "45",
    "file": "src/nativespeaker/api/services/restore.py",
    "line": 72,
    "description": "An owner that is another account raises RestoreSubscriptionNotEntitled; 45-04 replaces it with the capped move",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-09-08T01:39:55.773Z",
    "resolved_at": "2026-09-08T02:04:51.706Z"
  },
  {
    "id": 26,
    "kind": "todo",
    "phase": "45",
    "file": "tests/e2e/test_restore_subscription.py",
    "line": null,
    "description": "TestTheTwoRefusalsOfTheRestoreNotFoundFamily is named for two arms but now holds three; 45-07 corrected the docstring only, because the plan named the class in its acceptance criteria",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-08T21:18:51.538Z",
    "resolved_at": null
  },
  {
    "id": 27,
    "kind": "unrun-verify",
    "phase": "45",
    "file": ".planning/phases/45-post-auth-restore-subscription/45-09-PLAN.md",
    "line": null,
    "description": "45-09 acceptance check 'git diff --quiet -- ../specs' cannot run: ../specs is in the parent superrepo, outside this repository. D-14 proved by file mtime instead.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-08T21:30:16.158Z",
    "resolved_at": null
  },
  {
    "id": 28,
    "kind": "todo",
    "phase": "45",
    "file": "migrations/20260818_01_initial-release.sql",
    "line": 136,
    "description": "Stale comment: last_cross_account_transfer_month says 'Written by nothing' which D-10 made false. Should read: written by the capped cross-account move only (D-10); one move per subscription per UTC month. Migration not edited (D-14).",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-08T21:30:20.962Z",
    "resolved_at": null
  },
  {
    "id": 29,
    "kind": "unrun-verify",
    "phase": "47",
    "file": "tests/e2e/test_restore_subscription.py",
    "line": null,
    "description": "Pre-existing failure not caused by plan 47-01: the four-arms refusal case expects log event proof_rejected, the code emits purchase_proof_rejected. Measured on HEAD 1a3273d with every 47-01 edit reverted.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-12T05:56:25.182Z",
    "resolved_at": null
  },
  {
    "id": 30,
    "kind": "unrun-verify",
    "phase": "47",
    "file": "tests/schema/test_claim_race.py",
    "line": null,
    "description": "Two assertions derive the expected monthly period from the live clock; a run straddling a UTC month boundary would fail",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-12T06:28:34.592Z",
    "resolved_at": null
  },
  {
    "id": 31,
    "kind": "deviation",
    "phase": "47",
    "file": "tests/unit/test_subscription_attribution.py",
    "line": 964,
    "description": "Plan 47-08 measured it red: the control case builds an open term one minute past a module-import NOW, so any run longer than a minute between collection and the case closes the term and ingest raises InternalError. Fails under -m '' (131 s), passes alone. Reproduced with a 65 s post-collection sleep. Introduced by 47-05; not fixed in 47-08, which writes no source.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-12T08:04:34.354Z",
    "resolved_at": null
  }
]
````
