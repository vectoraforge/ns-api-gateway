---
phase: 34-schema
plan: 01
subsystem: environment
tags: [postgresql, provisioning, env, blocking-gate]
status: complete
requires: []
provides:
  - "A reachable, empty PostgreSQL 17.11 database named nativespeaker"
  - ".env with the five DB_* keys both consumers interpolate"
affects: [34-02, 34-03, 34-04]
tech_stack:
  added: []
  patterns:
    - "Database credentials live only in gitignored .env; DB_* is the canonical prefix, POSTGRES_* is the container-image prefix"
key_files:
  created: []
  modified:
    - .env
decisions:
  - "Added the five DB_* keys rather than teaching the consumers to read POSTGRES_*: pyproject.toml [tool.pogo] database_config and AppConfig.db both resolve DB_*, and .env.example declares DB_*, so the file was wrong, not the consumers"
  - "Renamed the dead key POSTGRES_NAME to POSTGRES_DB — the postgres:17 image reads POSTGRES_DB, which is the direct cause of the container provisioning only the default postgres database"
  - "Mirrored DB_* values from the existing POSTGRES_* values instead of hardcoding, so the two prefixes cannot drift apart"
  - "Did NOT mark SCHEMA-01 or SCHEMA-08 complete — this plan provisions environment state and produces no product artifact; both requirements belong to plans 34-02/03/04"
  - "Left the developer's uncommitted docker-compose.yml edit untouched: it is their change, not this plan's, and this plan is forbidden from modifying that file"
metrics:
  duration: "~10 min"
  completed: 2026-08-20
actuals:
  tokens: 900
  tasks: 2
  commits: 1
---

# Phase 34 Plan 01: Database Gate Summary

**The gate is green: PostgreSQL `17.11 (Debian 17.11-1.pgdg13+2)` is reachable on
`localhost:5432`, the `nativespeaker` database exists and is genuinely empty, and `.env` now
carries the five `DB_*` keys its two consumers actually read.**

## Outcome

Task 1's `<done>` condition holds. This is a continuation run: a previous executor found no
PostgreSQL at all and halted at task 2's blocking gate. The developer has since started a
PostgreSQL 17 container, and this run finished the substance of task 1 — which turned out to be
two real defects in `.env`, not merely "type in the connection details".

## The Observed `server_version`

```
17.11 (Debian 17.11-1.pgdg13+2)
```

Recorded because plan 34-03 needs it, per this plan's `<output>` and task 1's `<manual>` step.

**RESEARCH.md assumption A1 remains open and is now actionable.** RESEARCH.md's introspection
constants (Code Example 4) were captured on PostgreSQL **16.2**; the real target is **17.11**.
Plan 34-03 task 1 must re-capture those constants against this server rather than copying them.
A1 closes at that reconciliation, not here.

## The Two Defects Fixed in `.env`

The file existed but reached nothing useful. Both defects were silent — neither produces an error
at write time, and both would have surfaced much later as confusing failures.

**1. The five `DB_*` keys were missing.** `.env` defined `POSTGRES_HOST/PORT/USER/PASSWORD/NAME`.
Both consumers want `DB_*`:

| Consumer | What it reads | Evidence |
|----------|---------------|----------|
| `pyproject.toml` `[tool.pogo]` | `database_config = 'postgres://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'` | verified in file, unmodified |
| `src/nativespeaker/api/config.py` | `AppConfig.db: DatabaseConfig` under `env_nested_delimiter="_"`, `env_nested_max_split=1` → `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME` | verified by instantiating the project's own `DatabaseConfig` against the live environment |
| `.env.example` | declares `DB_*`, never `POSTGRES_*` | verified, unmodified |

Added all five, with values mirrored from the corresponding `POSTGRES_*` entries so the two
prefixes cannot drift. Nested resolution was then confirmed live: `db.host=localhost`,
`db.port=5432`, `db.user=postgres`, `db.name=nativespeaker`, and `db.password` loading as a
non-empty `SecretStr` whose `repr` is `SecretStr('**********')`.

**2. `POSTGRES_NAME` was a dead key — renamed to `POSTGRES_DB`.** The `postgres:17` image reads
`POSTGRES_DB`. `POSTGRES_NAME` means nothing to it, which is exactly why the container came up
holding only the default `postgres` database instead of `nativespeaker`. `docker-compose.yml`'s
`db` service uses `env_file: .env`, so the misnamed key was being handed to the image and ignored.

> **This rename only takes effect on a fresh volume.** The `postgres` image runs its
> initialization — including `POSTGRES_DB` — only when the data directory is empty. The running
> container will not gain a `nativespeaker` database from this rename; it already has one because
> this plan created it explicitly (below). The rename's payoff is the *next*
> `docker compose down -v && docker compose up -d db`, which will now provision the right database
> instead of silently provisioning the wrong one again.

Every pre-existing key was preserved: `CONFIG_DIR`, `APPLE_CERTS_DIR`, the four remaining
`POSTGRES_*`, `OPENAI_API_KEY`, `JWT_PROJECT_ID`, `JWT_API_KEY`, `FIREBASE_TEST_EMAIL`,
`FIREBASE_TEST_PASSWORD`. Key-name sets were diffed before and after to prove it: nothing removed
except the intended rename, six keys added. **No value from this file was printed at any point** —
it holds live third-party secrets, so all checks reported key names, booleans, and equality
comparisons rather than contents.

## The Drop-and-Recreate (`00-schema.md §9.13`)

Ran as mandated, connecting to the `postgres` maintenance database:
`DROP DATABASE IF EXISTS "nativespeaker" WITH (FORCE)` then `CREATE DATABASE "nativespeaker"`.

**The `DROP` had zero victims.** Measured immediately before executing it:
`SELECT count(*) FROM pg_database WHERE datname='nativespeaker'` returned **0**. Before this run
the server held exactly one non-template database, `postgres`. Nothing was destroyed — no
developer data existed on this fresh container to destroy. Threat `T-34-01-03`'s destructive
scenario did not materialize.

## Task 2 — the Blocking Gate

The gate is recorded as satisfied, not re-halted, on the developer's explicit instruction.

**What the developer was shown before resuming**, and what this run independently re-verified
rather than taking on trust:

| Fact shown to the developer | Re-verified here |
|---|---|
| `localhost:5432` listening on IPv4 and IPv6 | yes — `ss -ltn` shows both |
| `SHOW server_version` → `17.11 (Debian 17.11-1.pgdg13+2)`, major exactly 17 | yes |
| Connecting role `postgres` has `rolcreatedb = true` | yes, and exercised for real (below) |
| Only `['postgres']` existed; `nativespeaker` absent, so the §9.13 drop destroys nothing | yes — count was 0 immediately pre-drop |

The developer's words on resuming: *"Now I fixed it for sure. Use localhost:5432."* They were told
the drop-and-recreate would run and that it had no pre-existing database to destroy. Per the gate's
`how-to-verify` step 3, the destructive action was disclosed before it ran, and it proved to be a
no-op against an empty server.

## Verification

Task 1's `<automated>` block ran **verbatim from the plan**, unmodified, and exited 0:

```
OK PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2) - empty, CREATEDB available
VERIFY_EXIT=0
```

| # | Acceptance criterion | Result |
|---|----------------------|--------|
| 1 | Verify block exits 0, prints `OK PostgreSQL 17…` | **PASS** — output above |
| 2 | `.env` defines all five `DB_*` | **PASS** |
| 3 | `git status --porcelain .env` empty | **PASS** — empty; `git check-ignore` → `.gitignore:9`; `git ls-files --error-unmatch .env` → not in index |
| 4 | `.env.example` unmodified | **PASS** — `git diff HEAD` empty; crc32 `0x71bef7f9` |
| 5 | `core`/`audit` schema count = 0 | **PASS** |
| 6 | `public._pogo_migration` absent or empty | **PASS** — table absent |
| 7 | `rolcreatedb OR rolsuper` true | **PASS** |
| 8 | `pyproject.toml` unmodified, no package installed | **PASS** — `git diff HEAD` empty; crc32 `0x1cd44c12` |

Beyond the letter of the criteria, the `CREATEDB` capability was **exercised, not just read off a
catalog flag**: `ns_schema_test` — the exact database name plan 34-03's session fixture uses — was
created and dropped successfully. A `true` in `pg_roles` and a working `CREATE DATABASE` are not
the same claim, and 34-03 depends on the latter.

Plan `<verification>` regression check: `pytest tests/unit -q` → **163 passed**, matching
RESEARCH.md A6's baseline. Introducing `DB_*` into the environment that pytest-dotenv loads changed
no unit-test behavior.

## Deviations from Plan

**1. [Rule 1 - Bug] `.env` was missing the `DB_*` keys and carried a dead `POSTGRES_NAME`**

- **Found during:** Task 1
- **Issue:** The file's keys did not match what either consumer reads, and `POSTGRES_NAME` is not
  a key the `postgres:17` image recognizes. Left alone, `pogo apply` in plan 34-02 would fail on
  an unresolvable `{DB_USER}` interpolation and every future fresh-volume `docker compose up`
  would keep creating the wrong database.
- **Fix:** Added the five `DB_*` keys mirrored from the `POSTGRES_*` values; renamed
  `POSTGRES_NAME` → `POSTGRES_DB`.
- **Files modified:** `.env` (gitignored)
- **Commit:** none — `.env` is ignored at `.gitignore:9`, so this task produced zero tracked-file
  changes. No empty commit was manufactured.

**2. [Rule 4 - Scope] `SCHEMA-01` and `SCHEMA-08` deliberately NOT marked complete**

- **Found during:** State update
- **Issue:** This plan's frontmatter lists `requirements: [SCHEMA-01, SCHEMA-08]`, and the standard
  flow marks a plan's requirements complete on finish. But SCHEMA-01 is the initial migration file
  and SCHEMA-08 is "every acceptance check in `00-schema.md §10` passes" — neither exists yet.
  This plan states outright that it "produces no product artifact."
- **Handling:** Left both unchecked in REQUIREMENTS.md. They are earned by plans 34-02/03/04.
  Marking them here would have made the requirements ledger claim a migration that no one has
  written. Surfaced rather than silently applied.
- **Commit:** this plan's docs commit

**3. [Rule 3 - Blocking, informational] `docker-compose.yml` carries an uncommitted edit that is not this plan's**

- **Found during:** Task 1 pre-flight
- **Issue:** `git diff` shows `docker-compose.yml` modified — the explicit `POSTGRES_USER` /
  `POSTGRES_PASSWORD` / `POSTGRES_DB` environment block replaced by `env_file: - .env`. The prior
  summary recorded this file as unmodified, so the change is the developer's, made while starting
  their container. It is also what makes the `POSTGRES_NAME` rename matter.
- **Handling:** Left exactly as found — untouched and uncommitted. This plan is forbidden from
  modifying that file, and reverting a developer's working change would be worse than leaving it.
  Flagged here so it is not mistaken for drift later.
- **Commit:** none

## Threat Mitigations Upheld

- **T-34-01-01** (credential disclosure): `.env` remains untracked and unstaged — `git
  status --porcelain .env` empty, not in the index. No secret was echoed, cat'd, or quoted at any
  point in this run; all inspection was by key name and boolean. No new secret was invented.
- **T-34-01-02 / T-34-01-SC** (supply chain): zero packages installed. `pyproject.toml` is
  byte-identical to `HEAD`. `pgserver`, `pytest-postgresql`, and `testing.postgresql` remain absent
  from the project. The server used is the developer's own container, not a package.
- **T-34-01-03** (destructive drop): the drop ran with the developer's prior disclosure and
  destroyed nothing — zero matching databases existed at the moment it executed.
- **T-34-01-04** (`CREATEDB` on `DB_USER`): accepted as planned. The role is `postgres` on a local
  development container; no role was created or granted anything.

## Known Stubs

None. This plan produces environment state and one gitignored file; there is no product code to
stub.

## For Plan 34-02

- Connect with the five `DB_*` values in `.env` — `pogo`'s `database_config` now interpolates.
- The database is empty: no `core`, no `audit`, no `public._pogo_migration`. The
  `type "chat_role" already exists` failure this plan exists to prevent cannot occur.
- Do not re-run the drop; the database is already fresh.

## Self-Check: PASSED

- `.env` — FOUND at `/home/init/native-speaker/ns-api-gateway/.env`, untracked, all five `DB_*`
  keys present, `POSTGRES_DB` present, `POSTGRES_NAME` absent.
- Database `nativespeaker` — FOUND on `localhost:5432`, empty, on PostgreSQL 17.11.
- Task commits claimed: none for task 1, consistent with zero tracked-file changes. One docs commit
  for this summary and the state files.
- Every result quoted above is copied from a command that actually ran in this session. No
  assertion was weakened to obtain a pass.
