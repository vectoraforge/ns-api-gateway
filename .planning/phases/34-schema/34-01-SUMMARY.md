---
phase: 34-schema
plan: 01
subsystem: environment
tags: [postgresql, provisioning, env, blocking-gate]
status: blocked
requires: []
provides: []
affects: [34-02, 34-03, 34-04]
tech_stack:
  added: []
  patterns: []
key_files:
  created:
    - .env
  modified: []
decisions:
  - "Rejected the only PostgreSQL on this machine (pgserver's bundled 16.2) on two independent grounds: it is a [SUS] package the plan forbids, and it is major version 16, so it cannot satisfy the 'exactly 17' criterion even if permitted"
  - "Left docker-compose.yml placeholders unsubstituted — no container runtime exists to run it, so substituting would only put unverifiable values into a tracked file"
  - "Wrote .env from .env.example defaults with an explicit UNVERIFIED header rather than inventing plausible-looking credentials"
metrics:
  duration: "~3 min"
  completed: 2026-08-20
actuals:
  tokens: 177
  tasks: 1
  commits: 0
---

# Phase 34 Plan 01: Database Gate Summary

**Provisioning failed honestly: no PostgreSQL 17 is reachable or obtainable in this
environment, so the phase halts at task 2's blocking human gate with no schema work begun.**

## Outcome

Task 1 did **not** achieve its `<done>` condition. No database was provisioned. The run stops
at task 2 and hands control to the developer, which is exactly what that gate exists to do.

The one thing this plan owns — the database gate — is **red**. Plans 34-02, 34-03, and 34-04
have not started and must not start until it is green.

## What Was Tried

All three sanctioned provisioning paths from task 1's `<action>` were attempted in order.

| Path | Attempt | Result |
|------|---------|--------|
| (a) | Probe an already-running server | **Fail.** `ConnectionRefused` on `127.0.0.1`, `::1`, and `localhost` at both 5432 and 5433. `ss -ltnp` shows only ports 22 and 53 listening. No `/var/run/postgresql/` and no `/tmp/.s.PGSQL.*` unix socket. |
| (b) | `docker compose up -d db` | **Fail.** No container runtime exists: `docker`, `podman`, `nerdctl`, `docker-compose`, `podman-compose` all absent from PATH and absent from `/usr/bin`, `/usr/local/bin`, `/snap/bin`, `/opt/homebrew/bin`. No `/var/run/docker.sock` and no rootless socket under `$XDG_RUNTIME_DIR`. |
| (c) | Any other PostgreSQL the developer has | **Fail.** No `psql`, `pg_ctl`, `postgres`, `initdb`, `pg_isready`, `pg_config`, or `createdb` on PATH. No `/usr/lib/postgresql`, `/var/lib/postgresql`, or `/etc/postgresql`. No `DB_*`, `DATABASE_URL`, or `PG*` variables in the environment pointing at a remote host. |

A filesystem-wide search (`find / -xdev`) found PostgreSQL server binaries in exactly one place:
`/home/init/.cache/uv/archive-v0/ccCQEcN3rAHfZ1Lt/pgserver/pginstall/bin/` — the residue of the
research session's throwaway `/tmp` venv.

**These were deliberately not used.** Two independent disqualifiers, either sufficient alone:

1. **Forbidden.** `pgserver` is `[SUS]` in RESEARCH.md's Package Legitimacy Audit. Task 1's
   action names it as a forbidden fallback and threat `T-34-01-02` / `T-34-01-SC` turn that into
   a mitigation this plan must uphold. The binaries already sitting in a cache does not change
   the trust posture — *executing* unvetted native code is the substance of the risk the audit
   was written about, and is if anything a larger action than installing it.
2. **Wrong version anyway.** Read out of the binary's metadata without executing it
   (`strings`, and `#define PG_MAJORVERSION "16"` in its headers): **PostgreSQL 16.2**. Task 1's
   verify block asserts `ver.split(".")[0] == "17"` and success criterion 1 requires major
   version exactly 17. Using it could not have produced a legitimate pass — only a failing
   assertion, or a fabricated green obtained by weakening the assertion.

RESEARCH.md assumption **A4 is confirmed** by this reading: pgserver 0.1.4 bundles PG 16.2.

## What Was Produced

`.env` (gitignored, untracked), copied from `.env.example` with its defaults intact and a header
stating plainly that the values are unverified and reached nothing. No credential was invented;
`OPENAI_API_KEY` and the three `FIREBASE_*` keys remain at their `.env.example` placeholders, per
task 1's instruction that this phase must not materialize secrets it does not need.

The file exists so the developer has something concrete to correct at the gate. It is **not**
evidence that must-have truth #1 holds — it does not.

## Acceptance Criteria

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Verify block exits 0, prints `OK PostgreSQL 17` | **FAIL** — exit 1, `OSError: [Errno 111] Connect call failed ('::1', 5432), ('127.0.0.1', 5432)` |
| 2 | `.env` defines all five `DB_*` | PASS |
| 3 | `git status --porcelain .env` empty | PASS — ignored at `.gitignore:9`, not staged, not committed |
| 4 | `.env.example` unmodified | PASS — hash `f14716aa` unchanged |
| 5 | `count(*) FROM pg_namespace WHERE nspname IN ('core','audit')` = 0 | **UNVERIFIABLE** — no database to query |
| 6 | `public._pogo_migration` absent or empty | **UNVERIFIABLE** — no database to query |
| 7 | `rolcreatedb OR rolsuper` true | **UNVERIFIABLE** — no database to query |
| 8 | `pyproject.toml` unmodified | PASS — hash `23008805` unchanged; no package installed |

`docker-compose.yml` also verified unmodified (hash `0e81ae31`).

Plan `<verification>` regression check: `pytest tests/unit -q` → **163 passed**, matching
RESEARCH.md A6's recorded baseline. Creating `.env` — which pytest-dotenv now loads where it
previously loaded nothing — changed no unit-test behavior.

## Critical Open Item for Plan 34-03

**The `server_version` string was NOT observed.** Task 1's `<manual>` step and the plan's
`<output>` both require recording it, and it could not be captured because no server was reached.

RESEARCH.md **assumption A1 therefore stays open**, and OQ-1's resolution (plan 34-03 task 1
re-capturing the introspection constants against real PG 17) is *unstarted*. Plan 34-03 must not
copy RESEARCH.md's Code Example 4 constants, which were captured on PostgreSQL 16.2.

## Actions NOT Taken

Recorded so no downstream plan assumes otherwise:

- No database was created, dropped, or recreated. The `DROP DATABASE ... WITH (FORCE)` /
  `CREATE DATABASE` cycle mandated by `00-schema.md §9.13` **has not run**.
- `CREATEDB` on the connecting role was never confirmed; no role was granted anything.
- No package was installed. `pyproject.toml` is byte-identical to its pre-task state and
  `import pgserver` fails in the project venv — none of the three `[SUS]` packages are present.
- `docker-compose.yml` placeholders were left as shipped.
- No commit was made. Task 1's only artifact is gitignored, so it produced zero tracked-file
  changes; there was nothing to commit and no empty commit was manufactured.

## Deviations from Plan

**1. [Rule 3 - Blocking] Task 1 could not reach its `<done>` state — surfaced, not worked around**

- **Found during:** Task 1, all three provisioning paths
- **Issue:** No PostgreSQL 17 is reachable or obtainable without developer action.
- **Handling:** Escalated to task 2's blocking gate rather than auto-fixed. The only available
  workaround (pgserver 16.2) is forbidden by the plan and by threat `T-34-01-02`, and is the
  wrong major version regardless. Rule 3 explicitly excludes package-manager installs.
- **Commit:** none

**2. [Rule 2 - Correctness] `.env` written with an explicit unverified-values header**

- **Found during:** Task 1, after all three paths failed
- **Issue:** Task 1 says to fill `.env` with values "that actually reach the server found above."
  No server was found, so no such values exist. Writing the example defaults silently would
  present unverified values as working ones.
- **Handling:** Wrote the `.env.example` defaults verbatim under a header stating they are
  unverified and connect to nothing. The residual failure mode is loud, not silent — `pogo apply`
  against `localhost:5432` fails with connection-refused rather than corrupting anything.
- **Commit:** none (`.env` is gitignored)

## Threat Mitigations Upheld

- **T-34-01-01** (credential disclosure): `.env` untracked and unstaged — `git ls-files
  --error-unmatch .env` reports it is not in the index. No real secret was written into it.
- **T-34-01-02 / T-34-01-SC** (supply chain): zero packages installed; `pyproject.toml` hash
  unchanged; all three `[SUS]` packages absent from the project venv. The one cached `[SUS]`
  binary set on the machine was found and deliberately not executed.
- **T-34-01-03** (destructive drop): the drop did not occur, and per its mitigation it will not
  occur until the developer confirms it at task 2's gate.

## Blocker

**A reachable PostgreSQL 17 is required and absent.** This gates every remaining task in phase 34.
Resolution options, in the plan's own words: start one (`docker compose up -d db` after
substituting the `{DB_USER}`/`{DB_PASSWORD}`/`{DB_NAME}` placeholders in `docker-compose.yml` —
requires installing a container runtime first, which is a developer decision, not an executor
one), point `.env` at an existing PostgreSQL 17, or stop the phase here.

## Self-Check: PASSED

- `.env` — FOUND at `/home/init/native-speaker/ns-api-gateway/.env`
- Commits claimed: none. Consistent with zero tracked-file changes; nothing to verify.
- No claim of a working database appears in this summary.
