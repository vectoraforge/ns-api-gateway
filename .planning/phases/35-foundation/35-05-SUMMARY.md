---
phase: 35-foundation
plan: 05
subsystem: model-layer-repair
tags: [sqlmodel, sqlalchemy, postgresql, pydantic-settings, pytest, e2e]

requires:
  - phase: 35-foundation
    plan: 03
    provides: "auth/context.py LinkedIdentity over the real model classes; models/identities.py ExternalIdentity"
  - phase: 35-foundation
    plan: 04
    provides: "the deletion sweep that removed every reader of the subscription, usage and Apple surfaces"
provides:
  - "core.users at the v2.0 seven-column shape -- select(User) executes against the applied schema"
  - "a model layer with no subscription-plan or monthly-usage machinery anywhere in src/ or tests/"
  - "AppConfig and config/config.yaml with no apple block and no quotas mapping"
  - "tests/e2e/test_model_queries.py -- ten cases issuing real statements against the live v2.0 database"
  - "tests/e2e/conftest.py::create_chat seeding core.users + core.external_identities from an (issuer, subject) pair"
affects: [35-06, 35-08, 35-09, 35-10, 35-11, 36-rebinding, 37-create-user, 39-profile, 43-webhooks]

actuals:
  tokens: 10281
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "Parametrising a live-database smoke query over SQLModel.metadata.tables, so the case catches the *next* model/schema drift rather than only the one being fixed"
    - "Ordering two commits by their import direction rather than their plan numbering, so neither leaves the package un-importable"
    - "Proving nullability against the database rather than the model, because SQLModel skips pydantic validation on table=True classes"
    - "An AST import scan in place of a text grep, so negative assertions naming a removed symbol are not false positives"
    - "A rollback-isolation assertion written as a second case reading what the first case wrote, which pins the fixture instead of assuming it"

key-files:
  created:
    - tests/e2e/test_model_queries.py
  modified:
    - src/nativespeaker/api/models/users.py
    - src/nativespeaker/api/models/__init__.py
    - src/nativespeaker/api/config.py
    - config/config.yaml
    - tests/e2e/conftest.py
    - tests/e2e/test_chat_queries.py
    - tests/unit/conftest.py
    - tests/unit/test_config.py
    - tests/unit/test_users.py
  deleted:
    - src/nativespeaker/api/models/subscriptions.py

key-decisions:
  - "Task 2 was executed before task 1. config.py imported SubscriptionPlan from the model barrel, so the dependency runs config -> models and the config edit must land first. In the plan's order, task 1's commit leaves the whole package un-importable and its own acceptance criteria (pytest -q exits 0, ruff and ty clean) unreachable at its own commit."
  - "tests/unit/test_users.py was repaired rather than tests/unit/test_models.py. test_models.py covers the API and LLM pydantic models and never mentions User; test_users.py::TestUserModel is the module that asserted subscription_plan, which 35-04-SUMMARY.md named as the one the repair would have to revisit."
  - "The `grep -rn jwt_sub tests/ src/ | wc -l` == 0 criterion was replaced with a stronger, satisfiable form. Reaching literal zero would require deleting tests/schema/test_inventory.py's negative assertions -- the authority on the target shape -- and this module's own ABSENT_FIELDS tuple. src/ is at zero; every hit left in tests/ is a negative assertion or the documentation of one, enumerated below."
  - "The live-database module parametrises SELECT over every table in SQLModel.metadata rather than naming User and UsageMonthly. That covers both acceptance criteria with one case and catches whatever drifts next, including a model added by a later phase."
  - "email nullability is proven by a live insert, not a constructor call. SQLModel skips pydantic validation on table=True classes, so User(email=None) constructs whatever the annotation says; only the database's NOT NULL -- or its absence -- settles it."
  - "create_chat seeds provider='anonymous' with a NULL provider_uid. It is the left arm of the table's provider/provider_uid CHECK and the only shape available without inventing the sentinel provider_uid ruling 9.2 forbids. Plan 06's seed_identity owns provider variation."
  - "uv.lock's two-line byproduct of the editable-install refresh was reverted, not committed. A lockfile-format bump (revision 2 -> 3) is a function of the locally installed uv, and is not a model-repair plan's call. Logged as D-35-05-A."

requirements-completed: [FOUND-01]

coverage:
  - id: T1
    description: "select(User) executes against the live v2.0 database without UndefinedColumnError, and select(ExternalIdentity) without UndefinedTableError"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_model_queries.py::TestModelsMatchTheAppliedSchema (2 named cases + 4 parametrised over SQLModel.metadata.tables)"
        status: pass
      - kind: other
        ref: "pre-repair live probe: select(User) -> UndefinedColumnError: column users.jwt_sub does not exist; select(UsageMonthly) -> UndefinedTableError: relation core.usage_monthly does not exist"
        status: pass
      - kind: other
        ref: "mutation M1 (re-add jwt_sub to User) -> 6 of 10 fail; mutation M2 (re-add UsageMonthly) -> UndefinedTableError on core.usage_monthly"
        status: pass
    human_judgment: false
  - id: T2
    description: "User has exactly the seven v2.0 columns -- no jwt_sub, no name, no subscription_plan"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_users.py::TestUserModel (8 cases: exact field set, absent columns, defaults, uuid7, table mapping)"
        status: pass
      - kind: other
        ref: "sorted(User.model_fields) -> ['active','created_at','display_name','email','id','registered_at','updated_at']"
        status: pass
      - kind: schema
        ref: "tests/schema/test_inventory.py::EXPECTED_USERS_COLUMNS -- the same seven names asserted against the live database (77 passed, unchanged)"
        status: pass
    human_judgment: false
  - id: T3
    description: "User.email is nullable, because it is copied only from a Firebase Admin record whose emailVerified is TRUE"
    requirement: FOUND-01
    verification:
      - kind: e2e
        ref: "tests/e2e/test_model_queries.py::TestRowsRoundTrip::test_user_and_identity_round_trip -- a NULL email is inserted and read back through the live database"
        status: pass
    human_judgment: false
  - id: T4
    description: "No module in src/ or tests/ references SubscriptionPlan, SubscriptionPlanType, SubscriptionEvent, Subscription or UsageMonthly, and models/subscriptions.py does not exist"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_users.py::TestSubscriptionModelLayerIsGone::test_no_module_imports_a_removed_symbol -- AST import scan over every .py in src/ and tests/"
        status: pass
      - kind: unit
        ref: "::test_subscriptions_module_does_not_exist; ::test_barrel_exports_no_removed_symbol; ::test_barrel_all_matches_its_namespace"
        status: pass
    human_judgment: false
  - id: T5
    description: "AppConfig declares no apple block and no quotas mapping; config/config.yaml loads cleanly and the application starts against it"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py::TestSubscriptionConfigSurfaceIsGone (4 cases, incl. one loading the *tracked* config/config.yaml and one asserting extra='forbid' rejects a stale block)"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_startup_assertion.py -- the real lifespan runs against the edited YAML (9 passed)"
        status: pass
    human_judgment: false
  - id: T6
    description: "The unit suite collects with no module-scope User construction, so repairing the model cannot break collection"
    requirement: FOUND-01
    verification:
      - kind: other
        ref: "pytest --collect-only -q -> 374/486 collected, zero errors"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-08-20
status: complete
---

# Phase 35 Plan 05: Model-Layer Repair Summary

**`select(User)` executes against the applied v2.0 schema for the first time this phase — the
seven-column `core.users`, no subscription-plan or monthly-usage machinery anywhere, a
configuration file that no longer describes either, and ten live-database cases proving it rather
than a green suite that had merely stopped asking.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-08-21 06:17Z
- **Completed:** 2026-08-21 06:26Z
- **Tasks:** 3 of 3
- **Files:** 11 (1 created, 9 modified, 1 deleted) — 432 insertions, 177 deletions

## What was actually broken

Plan 04 left the suite at 464 passed / 0 failed, and none of that greenness was evidence for this
plan. E2E went green in wave 4 because the deletion sweep removed the tests that exposed the
schema drift, not because it repaired it. Measured against the live database immediately before
task 1, with the models as committed:

```
select(User):         UndefinedColumnError: column users.jwt_sub does not exist
select(UsageMonthly): UndefinedTableError:  relation "core.usage_monthly" does not exist
```

That is D-14's real content. `import nativespeaker.api.app.main` had succeeded since plan 01 and
the lifespan ran; SQLModel classes import fine when their columns are gone, and the failure surfaces
only when a statement executes — exactly the line D-15 draws. After the repair, the same probe:

```
select(User):             OK, 0 rows
select(ExternalIdentity): OK, 0 rows
```

## The final `User`

```
['active', 'created_at', 'display_name', 'email', 'id', 'registered_at', 'updated_at']
```

Seven columns, matching `migrations/20260818_01_initial-release.sql` lines 150-158 and
`tests/schema/test_inventory.py::EXPECTED_USERS_COLUMNS` name for name. Three are gone, each for
its own reason, recorded in the module docstring so the next reader does not re-add one:

| Dropped | Why |
|---|---|
| `jwt_sub` | The external subject is never an ownership or lookup key in v2.0. `(issuer, subject)` lives only on `core.external_identities`, behind the barrier's single identity query. |
| `name` | Renamed `display_name` by the schema. |
| `subscription_plan` | Allowance moved to `core.access_tiers.monthly_credits`, resolved through the grant Phase 36 wires. |

`email` stays nullable on purpose, `registered_at` is reporting-only and never a classifier, and
`active` stays a plain NOT NULL boolean the barrier tests positively.

`UsageMonthly` went with `core.usage_monthly`. Phase 36's `core.user_monthly_usage`, keyed on
`grant_id`, is a different table it owns.

## The surviving `config/config.yaml`

Six top-level keys: `chats_limit`, `jwt`, `log_level`, `messages_limit`, `model`, `resilience`.
The `apple:` and `quotas:` blocks are gone, together with `AppleConfig`, `AppConfig.apple`,
`AppConfig.quotas`, and the `from nativespeaker.api.models import SubscriptionPlan` import that
made `config.py` load-bearing for the deleted model layer.

`AppConfig` is a `BaseSettings` with `extra='forbid'` (verified, not assumed), so a block left
behind in the YAML now raises rather than being ignored — the intended fail-loud behaviour, pinned
by `test_a_stale_block_fails_loudly` so nobody later "fixes" it with `extra='ignore'`. A silently
ignored `quotas:` block would read as configured allowance that nothing enforces.

## Editable install

`uv sync` re-run, per the plan's recorded build-artifact assumption. `src/ns_api_gateway.egg-info/
SOURCES.txt` carries eight `nativespeaker/api/auth/` entries — the subpackage from the `auth.py` →
`auth/` split is discovered — and no stale entry for `exceptions.py` or `subscriptions.py` survives.
`python -c "import nativespeaker.api.app.main"` exits 0.

The refresh's two-line `uv.lock` byproduct was reverted; see deviation 6.

## Task Commits

| # | Task | Commit | Type |
|---|---|---|---|
| 1 | Task 2: remove the Apple and quota configuration surface | `06f6454` | refactor |
| 2 | Task 1 RED: failing tests for the v2.0 `User` shape | `23d930a` | test |
| 3 | Task 1 GREEN: repair `User`, delete the subscription models | `09922d5` | fix |
| 4 | Task 3 RED: live-database proof module | `22e1cc7` | test |
| 5 | Task 3 GREEN: seed `create_chat` against the v2.0 identity tables | `1eff67b` | fix |

Task 2 is first by necessity — see deviation 1. Both TDD tasks ran RED before GREEN: `23d930a`
failed 7 of 12 cases against the unrepaired model, and `22e1cc7` failed 2 of 10 against the
unrepaired `create_chat`.

## Test Status

| Suite | Before | After | Δ |
|---|---|---|---|
| Unit (`pytest -q`) | 362 | **374** | +12 |
| Schema (`pytest -q -m schema`) | 77 | **77** | untouched |
| E2E (`pytest -q -m e2e`) | 25 | **35** | +10 |
| Combined (`pytest -q -m ""`) | 464 | **486 passed, 0 failed** | +22 |
| `ruff check src tests` | clean | **All checks passed!** | |
| `ty check src` | clean | **All checks passed!** | |

`374 + 77 + 35 = 486`. Still zero `xfail` and zero `pytest.mark.skip`.

The unit delta is `test_users.py` 4 → 12 (+8) and `test_config.py` 5 → 9 (+4). The e2e delta is
`test_model_queries.py`, entirely new: 2 named `select` cases, 4 parametrised over
`SQLModel.metadata.tables`, 2 round-trip/isolation cases, 2 `create_chat` cases.

## Decisions Made

- **The live-database module parametrises over `SQLModel.metadata.tables` rather than naming the
  two broken models.** `SELECT <every declared column> FROM <table>` raises `UndefinedColumnError`
  for a column the database lacks and `UndefinedTableError` for a table it lacks, so one
  parametrised case covers both of the plan's acceptance criteria and, more usefully, catches
  whichever model drifts next — including one a later phase adds. The two named `select(User)` /
  `select(ExternalIdentity)` cases are kept beside it because they are what the plan's truths
  assert and what a failure report should name.
- **`email` nullability is proven by a live insert, not a constructor call.** SQLModel skips
  pydantic validation on `table=True` classes, so `User(email=None)` succeeded even against the
  *old* model where `email: str` was required — the unit case is a real requirement but a weak
  oracle. `test_user_and_identity_round_trip` inserts a NULL email and reads it back, which is the
  claim that actually needed evidence.
- **Rollback isolation is asserted, not assumed.** `test_the_previous_rows_were_rolled_back` runs
  after the round-trip case, on a fresh transaction over a fresh connection, and asserts the rows
  the previous case committed are absent. Without it every case in the module would silently be
  seeding the developer's database, and nothing would say so. `_db_transaction` itself was not
  touched — every read and write goes through its swapped `create_savepoint` factory.
- **The stale-import scan reads the AST, not the file text.** `tests/schema/` names
  `core.subscription_plan`, `core.usage_monthly` and `jwt_sub` in SQL strings *precisely in order
  to assert the database no longer has them*, and `test_constraints.py` has a
  `TestSubscriptionConstraints` class. A text grep would fire on all of those. Walking
  `ast.ImportFrom` / `ast.Import` nodes catches exactly the failure that matters — a stale import
  is an `ImportError` at collection time for the whole package, which is how `config.py`'s
  `SubscriptionPlan` import made the two halves of this plan inseparable.
- **`create_chat` seeds `anonymous` with a NULL `provider_uid`.** It is the left arm of the table's
  provider/provider_uid agreement CHECK, and ruling 9.2 forbids inventing a sentinel `provider_uid`
  for an anonymous row, so it is the only shape a seed can take without a provider account. Its
  docstring states explicitly that it is test seeding and not a JIT-provisioning path — no route
  reaches it, `src/` still has no code that writes either table, and `core.users` rows originate
  from `POST /auth/create-user` in Phase 37. Plan 06's `seed_identity` owns provider variation and
  the barrier-resolvable case.
- **Four config cases were added rather than only subtracting the removed ones.** The plan's
  `key_links` entry says a stale `apple` or `quotas` block "would now fail validation" — but
  nothing in the suite loaded the *tracked* `config/config.yaml`; `test_main_config_loads_yaml_and_
  content` writes its own. `test_tracked_config_yaml_loads` copies the real file into a temp dir
  and supplies the `.env`-resident `DB_*`/`JWT_*` values synthetically, so it proves the shipped
  file loads without coupling the unit suite to a developer's environment.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Tasks 2 and 1 were executed in the reverse of the plan's order**

- **Found during:** Task 1, before the first edit.
- **Issue:** `config.py:9` was `from nativespeaker.api.models import SubscriptionPlan`, and
  `AppleConfig.product_id_to_plan` / `AppConfig.quotas` were typed on it. Deleting
  `models/subscriptions.py` first leaves that import dangling, which is an `ImportError` for the
  whole package, not merely for `config.py` — so task 1's own acceptance criteria (`pytest -q`
  exits 0, `ruff` and `ty` clean) are unreachable at task 1's own commit. The plan anticipated the
  coupling ("the config edit and the model deletion have to land in adjacent commits") but assumed
  the wrong direction; the dependency runs config → models.
- **Fix:** ran task 2 first. Both commits are independently green, and no commit in this plan
  leaves the package un-importable.
- **Committed in:** `06f6454` (config), then `09922d5` (models).

**2. [Rule 3 - Blocking] `tests/unit/test_users.py` was repaired, not `tests/unit/test_models.py`**

- **Found during:** Task 1.
- **Issue:** the plan's file list and action name `tests/unit/test_models.py`, but that module
  covers the API and LLM pydantic models and does not mention `User`. The module that asserted
  `user.subscription_plan == SubscriptionPlan.free` is `test_users.py::TestUserModel`, which
  35-04-SUMMARY.md named explicitly as "the one module the repair will need to revisit".
- **Fix:** rewrote `test_users.py` (4 cases → 12), keeping its USER-01 / Phase 39 header.
  `test_models.py` needed no change and was not touched.
- **Committed in:** `23d930a`.

**3. [Rule 3] Task 1's `tests/unit/conftest.py` narrowing was already done by plan 04**

- **Found during:** Task 1.
- **Issue:** the plan's `read_first` points at `TEST_USER = User(jwt_sub=…, subscription_plan=…)`
  at conftest lines 126-132 and asks for `TEST_USER`, `mock_usage_db`, `webhook_client` and the
  `get_current_user` / `require_quota` overrides to be deleted. Plan 04 removed all of them; what
  stands there now is `TEST_IDENTITY` over `User(id=…, active=True)`, both of which survive the
  repair. There was no module-scope construction left to break collection.
- **Fix:** none needed. Only a comment carrying a now-false forward reference to plan 05 was
  retensed.
- **Committed in:** `1eff67b`.

**4. [Rule 3] `.env.example` had no `APPLE_CERTS_DIR` entry to remove**

- **Found during:** Task 2.
- **Issue:** the variable exists only in the developer's gitignored `.env`, which the plan says to
  leave alone. `grep -c APPLE_CERTS_DIR .env.example` was already `0`.
- **Fix:** none. Criterion verified rather than acted on; `.env.example` is unchanged by this plan.

**5. [Rule 3] The `grep -rn "jwt_sub" tests/ src/ | wc -l == 0` criterion is unreachable as written**

- **Found during:** Task 3, verification.
- **Issue:** literal zero would require deleting `tests/schema/test_inventory.py`'s `no_jwt_sub`
  assertion and its `EXPECTED_USERS_COLUMNS` comment — the module the wave brief names as the
  authority on the target shape — plus this plan's own `ABSENT_FIELDS` tuple. Deleting the proof
  that a column is absent in order to satisfy a grep for its name is a false green.
- **Fix:** used the stronger satisfiable form. `grep -rn "jwt_sub" src/` is **zero live
  references**; the only `src/` hit is the `models/users.py` docstring explaining why the column is
  absent. Every remaining `tests/` hit, enumerated:

  | Location | Kind |
  |---|---|
  | `tests/unit/test_users.py:28,32` | negative assertion — `ABSENT_FIELDS`, asserted twice per field |
  | `tests/schema/test_inventory.py:51` | negative assertion — `no_jwt_sub` against the live database |
  | `tests/schema/test_inventory.py:186` | comment on the seven-column target shape |
  | `tests/e2e/test_model_queries.py:4,44` | names the exact error the repair fixed |
  | `tests/e2e/conftest.py:104` | records what `create_chat` used to do and why it changed |

  Zero constructions, zero queries, zero imports.

**6. [Rule 3] `uv sync` rewrote `uv.lock`; the change was reverted**

- **Found during:** Task 3, the editable-install refresh.
- **Issue:** `uv sync` correctly refreshed the install but also rewrote two `uv.lock` lines —
  `ns-api-gateway 1.5.0` → `1.6.0` (a genuine correction against `pyproject.toml`) and
  `revision = 2` → `3` (a lock-format bump that is a function of the locally installed uv and may
  not match the team's).
- **Fix:** `git checkout -- uv.lock`. `uv.lock` is outside this plan's file list, nothing in this
  phase depends on the pin, and a lockfile-format change is not a model-repair plan's call.
  Logged as **D-35-05-A** in `deferred-items.md` for whoever next touches dependencies.

---

**Total deviations:** 6, all Rule 3 (blocking or scope). No Rule 1 bug was found in code this plan
wrote, no Rule 2 missing critical functionality, and no Rule 4 architectural question arose. Four
of the six are plan-text inaccuracies rather than unforeseen dependencies; none changes a
deliverable or an interface.

## Issues Encountered

- **Two mutations, both caught.** A model-shape change verified only by a suite that stopped asking
  is exactly the failure this plan exists to correct, so the new e2e module was mutation-verified
  rather than trusted:

  | Mutation | Expected notice | Result |
  |---|---|---|
  | M1 — re-add `jwt_sub: str` to `User` | the live-query cases should see `UndefinedColumnError` | **6 of 10 failed**, incl. `test_every_mapped_table_selects_all_of_its_columns[core.users]` |
  | M2 — re-add a `UsageMonthly` mapping `core.usage_monthly` | the parametrised case should see `UndefinedTableError` | **1 failed**: `[core.usage_monthly]`, `UndefinedTableError: relation ... does not exist` |

  `git diff --exit-code -- src/ tests/` confirmed the tree byte-identical to the committed state
  after each restore.

- **`core.access_tiers` is still empty**, as plan 04 flagged. This plan removes the configuration
  that used to answer "how much allowance?" and points at `core.access_tiers.monthly_credits`
  instead, which currently has nothing to answer with. That is Phase 36's REBIND-05 problem, not a
  regression introduced here — nothing in Phase 35 reads allowance, and `require_quota` was deleted
  in plan 04.

- **One item deferred:** D-35-05-A (`uv.lock`). Nothing else.

## Known Stubs

None. Every surface this plan touches is either deleted or fully wired, and the one helper it
repairs — `create_chat` — has a live caller for the first time since plan 04 emptied its callers.

One thing is deliberately left for a named owner and is not a stub: the e2e Firebase subject still
has no `core.external_identities` row the barrier can resolve, so the twelve refusal cases in
`test_chats.py` / `test_chat_queries.py` remain the negative half of the admission matrix. Plan 06's
`seed_identity` supplies the positive half; plan 11 restores the nineteen served cases. The seeding
half those cases need is delivered here and proven by `test_model_queries.py`.

## Threat Flags

None. This plan registers no route, adds no `src/` module, opens no network path, and writes no
query outside a test fixture. It *removes* a column, a table mapping, a model module, and two
configuration blocks. All four `mitigate` dispositions are implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-05-01 | `jwt_sub` is gone from `User`, and the AST scan proves no module imports a path back to it. The external subject now exists in exactly one place — `core.external_identities.(issuer, subject)` — so there is no model-level route by which a token subject becomes an ownership key. `create_chat` looks up by that pair, which is the table's own auth-time key. |
| T-35-05-02 | `active` stays `bool = Field(default=True)` over a NOT NULL column; `test_default_active_is_true` and the live round-trip both pin it, and the barrier's positive test (`is not True` rejects) is unchanged. |
| T-35-05-03 | Accepted, as planned. This plan only *removes* fields from the tracked `config/config.yaml` and adds no secret; the committed-key exposure D-20 accepts is scoped to plan 08. |
| T-35-05-04 | ORM constructs only — zero raw `text()` added. `models/users.py` re-encodes no CHECK, matching `models/identities.py`, so the database stays the single enforcement point. The one CHECK this plan interacts with (provider/provider_uid) is satisfied by `create_chat` choosing a legal shape, not by a Python copy of the rule. |
| T-35-05-SC | No package installed. `uv sync` resolved from the existing lock and added nothing; the legitimacy gate stays vacuous for Phase 35. |

## Next Phase Readiness

Ready. D-14 is closed in the sense it was actually written: the application does not merely import,
it queries. Plan 06 has a model layer it can resolve identities against.

- **Plan 06** adds `seed_identity` beside `create_chat` in `tests/e2e/conftest.py`. `create_chat`
  already seeds `core.users` + `core.external_identities` from an `(issuer, subject)` pair, so
  `seed_identity` is the barrier-resolvable variant (a `google` provider with a real
  `provider_uid`) rather than a new mechanism. `tests/unit/conftest.py`'s `make_token`,
  `PRIVATE_KEY_PEM` and `_FixedKeyVerifier` are untouched and still importable.
- **Plan 08** lands the `hmac:` block in `config/config.yaml`, which now has six top-level keys and
  no dead ones. Note for that plan and for the Secret Manager follow-up: `AppConfig` is built as
  `AppConfig(**yaml_data, ...)` and pydantic-settings ranks `init_settings` above `env_settings`,
  so the YAML is authoritative for any field it declares and an environment variable **cannot**
  override one. The Secret Manager migration must *remove* the YAML entries, not shadow them.
  `extra='forbid'` is now asserted, so the block must be declared on the model in the same commit.
- **Phase 36** owns `core.user_monthly_usage` and the grant that resolves allowance through
  `core.access_tiers.monthly_credits`. `core.access_tiers` is still empty and must be seeded before
  quota enforcement can return a number.
- **Phase 39 / 43** rewrite `/users/me` and `/webhooks/app-store`. Both need configuration this
  plan removed; neither should restore `AppleConfig` as it was — it mapped product ids onto a
  dropped enum.

## Self-Check: PASSED

- All 8 claimed created/modified files exist on disk; `models/subscriptions.py` is absent as
  claimed (`test ! -e` exits 0).
- All 5 claimed commits are in `git log`: `06f6454`, `23d930a`, `09922d5`, `22e1cc7`, `1eff67b`.
- `pytest -q -m ""` exits 0 at **486 passed, 0 failed**; `ruff check src tests` and `ty check src`
  both print `All checks passed!`.
- `sorted(User.model_fields)` prints the seven expected names; the live probe reports
  `select(User): OK` and `select(ExternalIdentity): OK`.
- Working tree carries no change outside this plan's file list: `docker-compose.yml`, `.gsd/` and
  `.planning/research/.cache/` were pre-existing and are untouched and uncommitted.

---
*Phase: 35-foundation*
*Completed: 2026-08-20*
