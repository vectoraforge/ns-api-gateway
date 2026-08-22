---
schema_version: 1
open_count: 2
waived_count: 0
fixed_count: 0
total_count: 2
last_updated: 2026-08-22T02:31:48.290Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 36 | unrun-verify | src/nativespeaker/api/models/grants.py |  | No committed test round-trips AccessGrant/AccessTier/UserMonthlyUsage against the live schema; verified once by an uncommitted ad-hoc script (36-01 D3) | open |  | 2026-08-22T02:01:11.364Z |  |
| 2 | 36 | stub | src/nativespeaker/api/quota.py |  | consume_quota implements §8.4 step 1 only; a caller holding an effective grant passes the gate uncharged until plan 36-04 lands steps 2-4 | open |  | 2026-08-22T02:31:48.290Z |  |

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
  }
]
````
