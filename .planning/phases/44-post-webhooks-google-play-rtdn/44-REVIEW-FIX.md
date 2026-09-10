---
phase: 44-post-webhooks-google-play-rtdn
fixed_at: 2026-09-10T00:00:00Z
review_path: .planning/phases/44-post-webhooks-google-play-rtdn/44-REVIEW.md
fix_scope: critical_warning
findings_in_scope: 12
fixed: 12
skipped: 0
iteration: 1
status: all_fixed
---

# Phase 44: Code Review Fix Report

**Review:** `44-REVIEW.md` (commit `a0199f0`, 29 findings: 1 critical, 11 warning, 17 info)  
**Fix scope:** critical + warning (12 findings). Info findings were out of scope.  
**Status:** all_fixed — 12 fixed, 0 skipped.

Three fixers ran **strictly sequentially**, never in parallel, each committing one
commit per finding staging only that finding's files.

## Fix commits

| Finding | Commit | Subject |
| --- | --- | --- |
| CR-20 | `14ab725` | hide bound parameters on the one engine |
| WR-20 | `3741223` | make the quieted-library pin a ceiling, never a floor |
| WR-21 | `4599664` | prove the database at boot, bounded, before the pod reports Ready |
| WR-50 | `061823f` | declare google-auth's requests extra, which src/ imports at boot |
| WR-01 | `0b7eaa4` | cap the Play credential refresh at the module's own timeout |
| WR-02 | `6824d52` | serialize the push verifier rebuild and floor its retry rate |
| WR-10 | `c9366a0` | take the canonical row on the clock the guard decided on |
| WR-11 | `fe24a26` | classify the commit-time violation and name the code it carried |
| WR-30 | `5fbb157` | pin every field the Play read carries, not the status alone |
| WR-31 | `e00d317` | read the two store ids back out of their own columns |
| WR-32 | `668d6d4` | read old_tier_id back off the audit row on both sides of a transition |
| WR-40 | `30b8b7b` | drive the real attribution conflict instead of scripting an unreachable one |

## Verification (orchestrator, after all 12 fixes)

| Gate | Baseline at `62ebf5b` | After fixes |
| --- | --- | --- |
| `ruff check src tests` | clean | **clean** |
| `pytest tests/unit` | 1867 passed | **1898 passed** |
| `pytest tests/schema -m schema` | 277 passed | **282 passed** |
| `pytest tests/e2e -m e2e` | 357 passed | **360 passed** |
| `ty check src` | 0 diagnostics | **0 diagnostics** |

No suite regressed. The counts rose because the fixes added cases: 31 unit, 5 schema
and 3 e2e. No test was weakened to make a fix pass.

## Corrections to the review

Four findings were fixed at their root cause but **not** with the remedy the review
proposed, because the proposed remedy was wrong. Each is recorded in full under its
finding below.

- **WR-21** — the review's bare `db_engine.connect()` is unbounded (asyncpg defaults to
  60 s and the chart ships no `startupProbe`), which would have falsified the review's
  own appendix. Capped at 8.0 s, matching `PLAY_HTTP_TIMEOUT_SECONDS`.
- **WR-01** — the review's shared module-level `Request()` would share one
  `requests.Session` across every anyio worker thread. Subclassed `Request` instead,
  keeping per-call construction.
- **WR-10** — the review's CAS-inside-the-ORM-UPDATE form leaves `subscription.user_id`
  stale for the caller, and re-setting it re-dirties the instance so the session flush
  emits a second unconditional `UPDATE ... WHERE id` that defeats the CAS. Used a
  separate conditional take whose row lock covers the mutations behind it. The review's
  "44 D-06" citation is really 45-CONTEXT D-06; the consequence stands.
- **WR-31** — the review's suggested assertion does not catch its own probe:
  `_RecordingSubscriptions.insert_purchase` builds its `StorePurchase` from the same
  kwargs the case already reads and never reaches the real crud, so a crud-level swap
  stays invisible. Replaced with an e2e case that selects both columns back out of
  `core.store_purchases`.
- **WR-32** — the review's one-liner catches the reviewer's probe but pins only the NULL
  side; a second probe (`old_tier_id=None`) survives it. Added a tier-transition case
  that pins both sides.

---

## Fixer 1 — app wiring / cross-cutting

### CR-20 — FIXED
**Commit:** 14ab725
**Root cause:** `build_db_engine` (`src/nativespeaker/api/app/lifespan.py:137-142`) called
`create_async_engine` without `hide_parameters`, so SQLAlchemy's default `False` stood. A
`StatementError.__str__` renders `[parameters: {...}]`, and any such error escaping the crud layer
reaches `generic_error_handler` (`app/error_handlers.py:84`), which logs the whole chain.
**Reproduced before editing:** built the real engine against the live PostgreSQL and issued a
statement binding two marker values. `hide_parameters = False`; `LEAKS handle: True`,
`LEAKS token: True`; rendered text carried
`[parameters: ('CHALLENGE-HANDLE-SECRET-123', 'PURCHASE-TOKEN-SECRET')]`.
**Change:** set `hide_parameters=True` on the one engine, with a comment naming the four bound
secrets (challenge handle, DeviceCheck token, user email, purchase token inside
`notification_uuid`) and stating that the SQL text is deliberately kept. This is the root cause
rather than a symptom: the point fix at `services/auth.py:410-413` covers one `except` block, the
engine flag covers every one of them. Re-running the same reproduction after the edit gives
`hide_parameters = True`, `LEAKS handle: False`, `LEAKS token: False`, and
`[SQL parameters hidden due to hide_parameters=True]` with the SQL text intact.
Added `TestAFailedStatementCarriesNoBoundParameterIntoTheLogs` in `tests/unit/test_config.py`: one
case on the flag, one reading a real rendered `StatementError` back. Proved the second case is
non-vacuous — the same construction with `hide_parameters=False` renders the marker.
**Correction to the review:** none. The review's snippet was correct as written.
**Verification:** ruff clean; unit 1869 passed; ty 0 diagnostics.

### WR-20 — FIXED
**Commit:** 3741223
**Root cause:** `src/nativespeaker/api/logs.py:64` did an unconditional
`logging.getLogger(name).setLevel(logging.WARNING)` for the nine `_QUIETED_LIBRARIES`. A level set
on a child outranks the root in both directions, so the intended ceiling was also a floor.
**Reproduced before editing:** against the real `setup_logging("ERROR")` —
`app_warning_should_be_hidden: not emitted`, `httpx_noise: EMITTED`,
`sqlalchemy_noise: EMITTED`, `other_lib_noise: not emitted`. Exactly the inversion the review
describes: the application's own WARNING vocabulary is lost and library chatter survives.
**Change:** `setLevel(max(logging.WARNING, root.level))` — a ceiling, never a floor — and corrected
the comment at `:14`, which claimed the opposite of what the code did. Used `root.level` rather than
a fresh `getLevelNamesMapping()` lookup because `root.setLevel` two lines above is what turns the
configured name into a number, so no new failure mode is introduced for an unknown level.
After the edit all four probes read `not emitted`, and the 37.5 WR-03 ceiling still holds:
`openai_body_at_debug: not emitted` while `other_lib_debug: EMITTED` at `LOG_LEVEL=DEBUG`.
Added `TestQuietingALibraryNeverRaisesItAboveTheApplication` in `tests/unit/test_logging.py`
(parametrised over all nine, plus a DEBUG-direction control). Mutation-proved: restoring the flat
`setLevel(logging.WARNING)` turns 9 of the 10 new cases red.
**Correction to the review:** none.
**Verification:** ruff clean; unit 1879 passed; ty 0 diagnostics.

### WR-21 — FIXED (not skipped — see the weighing below)
**Commit:** 4599664
**Root cause:** `create_async_engine` opens no connection; SQLAlchemy connects on first checkout.
`lifespan` built the engine at `app/lifespan.py:218`, logged `started` and yielded without ever
having reached Postgres, while `routers/health.py` answers `/health/ready` with a static 200 that
both probes read (`k8s/values.yaml:35-41`).
**Weighing the crash-loop risk the brief raised:** the remedy is boot-time only, so it can never
restart a *running* pod — a transient database blip after boot never reaches the line. What it does
change is that a pod which cannot reach Postgres fails to start, which halts the rolling update on
the previous ReplicaSet instead of terminating the last working pod. A pod booted without a database
can serve nothing but 500s and can never recover into readiness, because `/health/ready` is static.
That is verbatim the argument `build_jwt_verifier` already makes and the project already ratified
(`lifespan.py:118-121`, "a pod without this verifier has nothing to be Ready for"). So the remedy is
not worse than the defect, and it is four lines.
**Change:** added `_prove_database_reachable(engine, db)`, called immediately after
`build_db_engine`. It opens and drops one connection and raises `RuntimeError` naming
host, port and database name on any failure. `db_engine` is assigned before the call, so the
existing `finally` still disposes it.
**Correction to the review:** the review's proposed remedy — a bare `async with db_engine.connect():
pass` — is **unbounded**, and I did not apply it as written. Measured: a blackholed host does not
fail fast (asyncpg's own default is 60 s), whereas a refused port fails in 0.00 s and a wrong
password in 0.02 s. The chart ships no `startupProbe`, and this review's own Partition F appendix
dropped that candidate *on the premise* that "lifespan network work is bounded" — the review's
snippet would have falsified its own appendix's premise and let the liveness probe kill the pod
before boot named the reason. I therefore capped the connect with
`asyncio.timeout(_DB_CONNECT_TIMEOUT_SECONDS)` at 8.0 s, matching the module's existing convention
(`PLAY_HTTP_TIMEOUT_SECONDS = 8`, JWKS `fetch_timeout_seconds=3.0`), and named the failure the way
`build_jwt_verifier` names its own.
Also measured, because CR-20 is about exactly this: none of the three real failure texts (refused,
wrong password, unreachable) carries the password, so the raised message quotes the cause safely.
The message uses host/port/name and never `DatabaseConfig.url`, which does render the password.
**Empirical proof, both directions, through the real `lifespan`:** with `DB_HOST=127.0.0.1
DB_PORT=1` — `BOOT FAILED after 0.06s: RuntimeError: database unreachable at
127.0.0.1:1/nativespeaker: ConnectionRefusedError`. With the real `.env` — `BOOT COMPLETED`.
Added `TestBootProvesTheDatabaseBeforeThePodReportsReady` in `tests/unit/test_config.py`: the named
failure, the no-credential property, and a control on a reachable stand-in engine (a check that
raised unconditionally would pass the first two).
**Verification:** ruff clean; unit 1882 passed; e2e 357 passed (the e2e suite runs the real lifespan
against the real database, so it is the direct regression guard for this change); ty 0 diagnostics.
**Docstring ratchet:** tripped once, as the brief predicted — the new function's six-line docstring
took `src` from 0 to 1. Repaired in-run by keeping a one-line docstring and moving the reasoning
into a comment; `test_docstring_bar.py` back to baseline 0.

### WR-50 — FIXED
**Commit:** 061823f
**Root cause:** `pyproject.toml` declared `"google-auth>=2.49"` with no extra, while
`src/nativespeaker/api/auth/google_play.py:10` imports `google.auth.transport.requests` at module
scope, on the boot path (`app/lifespan.py` and `app/dependencies.py` both import the module).
**Verified every premise before editing:** `inspect.getsource(google.auth.transport.requests)`
contains `import requests` — True. `uv.lock`'s `google-auth 2.49.1` entry listed exactly two
dependencies, `cryptography` and `pyasn1-modules`. `requests` is a real declared extra of the
installed distribution (`Provides-Extra` includes `requests`, requiring `requests>=2.20,<3`).
**Precedents checked and followed:** `4d63404 fix(43): WR-02 declare cryptography, which src/
imports directly` and `e1ac461 fix(37.5): WR-77 declare sqlalchemy and starlette`. Both edit
`pyproject.toml` plus `uv.lock`, extend the "Declared, not inherited" comment block, and add no
test — I matched that shape exactly rather than inventing a new convention.
**Change:** `"google-auth[requests]>=2.49"`, with a comment naming the module-scope import, the
transport's own `import requests`, and the two uncontrolled edges (`app-store-server-library`,
`firebase-admin`'s `cachecontrol`) the environment was relying on. Regenerated the lock with
`uv lock` (uv 0.12.5 at `/home/init/.local/bin/uv`; there is no `uv` in `.venv/bin`) and committed
it with the same finding. `uv lock --check` reports "Resolved 111 packages" with no drift. The lock
diff is the intended edge only — no version churn: a `google-auth` `[package.optional-dependencies]
requests` block, and the project's own edge becoming `google-auth extra = ["requests"]`.
`uv tree` now shows `requests v2.32.5 (extra: requests)` hanging off the project's own google-auth.
**Correction to the review:** none. The review's `"google-auth[requests]>=2.49"` was correct.
**Verification:** ruff clean; unit 1882 passed; schema 277 passed; e2e 357 passed; ty 0 diagnostics.

---

## Final verification — all five commands, run in full after the last commit

    .venv/bin/ruff check src tests                          -> All checks passed!
    .venv/bin/pytest tests/unit -q -p no:cacheprovider      -> 1882 passed
    .venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema -> 277 passed
    .venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e      -> 357 passed
    .venv/bin/ty check src                                  -> All checks passed! (0 diagnostics)

Baseline was unit 1867 / schema 277 / e2e 357. The unit count rose by 15 — the new cases added by
CR-20 (2), WR-20 (10: nine parametrised plus one control) and WR-21 (3). Schema and e2e are
unchanged, ruff and ty are clean, and no existing test was weakened or deleted.

`git status --short` is empty. Four commits, one per finding, each staging only its own source
files: 14ab725, 3741223, 4599664, 061823f. No planning artifact was committed, no branch was
created or switched, no worktree was created, nothing was pushed, and no git command was run
outside `/home/init/native-speaker/ns-api-gateway`.

---

## Fixer 2 — adapters / services / crud

### WR-01 — FIXED
**Commit:** `0b7eaa4` fix(44): WR-01 cap the Play credential refresh at the module's own timeout
**Root cause:** `auth/google_play.py` `_get` passed a bare
`google.auth.transport.requests.Request()` to `self._credential.refresh`. Re-verified against the
installed library rather than the review: `inspect.signature(Request.__call__)` is
`(self, url, method='GET', body=None, headers=None, timeout=120, **kwargs)`;
`service_account.Credentials._perform_refresh_token` reaches
`_client.jwt_grant(request, self._token_uri, assertion)` — signature
`(request, token_uri, assertion, can_retry=True)`, no `timeout`; and inside
`_token_endpoint_request_no_throw` the only call is a bare `response = request(` with no `timeout`
kwarg (grepped the installed source for `timeout` — one hit, the parameter, never a pass-through).
So the 120 s default stands, on the one call in this module that occupies a real OS thread of the
pool `get_identity` shares.
**Change:** added `CappedRefreshRequest(google.auth.transport.requests.Request)`, whose `__call__`
re-declares the same positional signature with `timeout=PLAY_HTTP_TIMEOUT_SECONDS` and delegates to
`super().__call__`. `_get` now passes `CappedRefreshRequest()`. This is the root cause — the
default on the transport callable — not a symptom: it caps the trust-boundary lookup and every
other call google-auth makes through the same object, and a library caller that names its own
shorter timeout still wins.
**Correction to the review:** the review proposed a module-level `_PLAY_REFRESH = Request()` shared
by a wrapper function. That would share one `requests.Session` across every anyio worker thread
(`requests.Session` is not documented thread-safe) where the shipped code built a fresh transport
per refresh. A subclass keeps the per-call construction and also covers `_refresh_trust_boundary`'s
own use of the same callable, which a function wrapper around one shared object does not improve on.
**Tests:** three cases in `tests/unit/test_google_play_notifications.py`
(`TestTheCredentialRefreshIsCapped`) — the cap reaches `session.request` (measured through a
recording `requests`-shaped session, not the signature); an explicit timeout still wins; and the
read hands a stale credential the capped transport. `tests/unit/test_auth_package_shape.py`'s
recorded shape ratchet moved `(8, 24, 68) -> (8, 25, 69)` with the reason written down, as that
file's own docstring requires.
**Verification:** ruff clean; unit 1885 passed; e2e 357 passed; ty 0.

### WR-02 — FIXED
**Commit:** `6824d52` fix(44): WR-02 serialize the push verifier rebuild and floor its retry rate
**Root cause:** `PubSubPushTokens.verify` ran `self._verifier = await
run_in_threadpool(self._build)` before the bearer was examined at all, with nothing serializing it
and nothing recording that a rebuild had just been attempted. Each concurrent request therefore
built its own `PyJWKClient` and made its own blocking 3-second `urlopen`, on the threadpool
`get_identity` shares, on a route outside the gateway's JWT policy.
**Change:** `__init__` now holds an `asyncio.Lock` and a monotonic `_next_rebuild` deadline
(`PUSH_VERIFIER_REBUILD_INTERVAL_SECONDS = 30.0`, overridable per instance). `verify` takes the
lock, re-reads `self._verifier` under it, and stamps the next deadline *before* the fetch, so the
callers held behind one failed rebuild do not each inherit the right to make their own. Keeps
`4bb7918 fix(43): WR-41`'s intent exactly: the retry is delayed, never cancelled. No rate limiter,
no cache, no config knob — per-IP limiting stays at Envoy Gateway per `AGENTS.md`.
**Tests:** `TestTheRebuildIsSerializedAndFloored` — a burst of 8 concurrent deliveries costs one
JWKS fetch; five deliveries after a failed rebuild cost one; and with the interval elapsed the
route still recovers. Mutation-proved: replacing `async with self._rebuild_lock:` with `if True:`
fails the burst case; dropping the `time.monotonic() >= self._next_rebuild` term fails the floor
case.
**Verification:** ruff clean; unit 1888 passed; e2e 357 passed; ty 0.

### WR-10 — FIXED
**Commit:** `c9366a0` fix(44): WR-10 take the canonical row on the clock the guard decided on
**Root cause:** proved empirically before editing, with a throwaway schema probe against live
PostgreSQL (since deleted; its content is now the permanent case below).
- `lock_grants` -> `lock_active_grants_of` is a plain `... FOR UPDATE` (`crud/grants.py:124-130`);
  on zero rows it locks nothing, and with `owner is None` it is never issued.
- `upsert_subscription`'s in-place arm was a plain ORM mutation flushed as `UPDATE
  core.subscriptions ... WHERE id = :id`, with no predicate.
- `grep -rn "version_id_col\|__mapper_args__" src/` returns nothing, so `Subscription` carries no
  optimistic-lock column. All three premises hold.
The probe: an unattributed `(google_play, tokenX)` row at `store_signed_at = T0` **with its
`core.store_purchases` row already committed** (which is what silences both unique indexes), then a
delivery signed `T1` whose reads complete, then a delivery signed `T2 > T1` run to completion, then
the first one's write. Result: **both answered 200 and the canonical clock moved backwards from
`T2` to `T1`.** Without the pre-existing purchase row the older delivery loses at
`insert_purchase`'s `UNIQUE (provider, external_id)` — which is why this had never surfaced.
**Change:** `SubscriptionsDB.hold_subscription_clock` emits a conditional
`UPDATE core.subscriptions SET updated_at = ... WHERE id = :id AND store_signed_at IS NOT DISTINCT
FROM :clock_read`, and `upsert_subscription`'s in-place arm runs it — after the owner claim, only
when the arm will write something — returning `lost_race` on zero rows. The clock compared is
**not** a third read of the row: `upsert_subscription` now takes a `clock_read` parameter and
`ingest` passes `settled.store_signed_at`, the value its own out-of-order guard decided on. On a
match the statement's own row-level write lock serializes everything behind it, so the two rival
deliveries block rather than interleave, and Postgres' EvalPlanQual re-check makes the loser's
predicate fail. The loser answers the 500 the store's resend recovers from.
**Correction to the review:** two.
1. The review proposed folding the CAS into the ORM's own UPDATE (`update(Subscription)...
   .values(**values)`). Applied literally that breaks the arm: the ORM attributes the caller reads
   (`subscription.user_id` at `services/subscriptions.py:157`) would then be stale, and re-setting
   them re-dirties the instance so the session's flush emits a *second*, unconditional `UPDATE ...
   WHERE id` that defeats the CAS. A separate conditional take, whose row lock covers the plain
   mutations behind it, is the same guarantee without that trap.
2. The review cited "44 D-06" for the restore path's dependence on `stored.status`/`stored.tier_id`.
   44 D-06 is `VerifiedNotification` moving to `auth/store_notifications.py`. The decision meant is
   **45-CONTEXT D-06** ("Entitlement is decided by the local row where one exists ... restore never
   updates that status from the proof"). The consequence the review describes is real; only the
   citation was wrong.
**Decisions checked:** 43 D-16 forbids a subscription-row lock because "it would be a lock tier
ahead of the grant locks, and it does not exist on the first insert". Respected: this statement
takes no `FOR UPDATE`, it runs *after* `lock_grants` in `ingest` and after `lock_grants_of` in
`restore` (both writers reach `claim_subscription_owner`, which already takes the same row's write
lock at the same position), and it exists only on the in-place arm — never on the insert. No
`SHARED-INVARIANTS.md` § Locks clause is crossed.
**Tests:** `tests/schema/test_subscription_race.py::TestTwoDeliveriesCarryingDifferentStoreClocksCommitOnce`
— two real connections, released at a new "before the first write statement" barrier, each
recording the committed clock it decided against. Exactly one commits; the loser is an
`InternalError`; the settled clock is the winner's and never the last writer's; one row in each of
the three tables. Mutation-proved: disabling the take fails all five cases (both deliveries commit).
Plus `tests/unit/test_subscription_store_clock.py::TestTheCanonicalRowIsTakenOnTheClockItWasReadAt`
— the predicate, the bound value, no `FOR UPDATE`, the lost race, and a control that a delivery
recording nothing takes the row at all (or every replay would queue behind an in-flight delivery).
**Test call sites updated for the new keyword:** `tests/unit/test_subscription_store_clock.py`
(`_upsert`, `_adopt`) and `tests/unit/test_subscription_attribution.py` (`_upsert`), each passing
the clock the caller read, which is what `ingest` passes.
**Verification:** ruff clean; unit 1893 passed; schema 282 passed; e2e 357 passed; ty 0.

### WR-11 — FIXED
**Commit:** `fe24a26` fix(44): WR-11 classify the commit-time violation and name the code it carried
**Root cause:** `migrations/20260818_01_initial-release.sql:242-247` read directly. Confirmed: the
whole migration contains exactly two `DEFERRABLE` clauses (`grep -n DEFERRABLE` -> lines 244, 247)
and both are `FOREIGN KEY (...) REFERENCES core.subscriptions (...) DEFERRABLE INITIALLY DEFERRED`
— SQLSTATE **23503**, not 23505. The review is right. So `except IntegrityError: await
self._settle(WriteOutcome.lost_race, ...)` classified the one violation class the handler exists
for as the one class `is_unique_violation` was written to re-raise, and swallowed every CHECK and
NOT NULL with it. `_settle` then logged `store_notification_race_lost` with `provider` alone and
raised `InternalError`, whose `log_level` is `None`, so `app_error_handler` short-circuits and the
`IntegrityError` — the only thing naming the constraint — reached no log line at all.
**Change:** both commit handlers now run the same `if not is_unique_violation(violation): ... raise`
the flushes already run (`crud/subscriptions.py:135-140` and five siblings), logging
`store_notification_commit_refused` / `restore_commit_refused` with the SQLSTATE first. The
re-raised `IntegrityError` reaches `generic_error_handler`, which writes `unhandled_exception` with
`exc_info` — a full traceback carrying the constraint name — and still answers the same 500, so the
store still redelivers. `get_db` rolls back on the way out (`app/dependencies.py:45-51`), so no
transaction is left open. A genuine 23505 at COMMIT is unchanged: still the lost race.
**Correction to the review:** none — the SQLSTATE claim and the remedy both hold. The classifier
convention named in the review (`is_unique_violation`) was used rather than a new one.
**Tests:** `TestTheDeferredKeysAreClassifiedWhereTheyAreEvaluated` rewritten in both
`tests/unit/test_subscription_attribution.py` and `tests/unit/test_restore_proof.py` — those two
classes previously asserted the wrong behaviour (a 23503 at COMMIT answering as a lost race), so
they were updated to the correct expectation rather than weakened. Each now pins: the
`IntegrityError` escapes with its SQLSTATE; the new error line names the code; an unreadable code
is refused fail-closed; a 23505 is **still** the lost race (the control on the classification); and
a winning write reports neither. Mutation-proved: reverting the classification fails 6 of the 10.
**Verification:** ruff clean; unit 1897 passed; schema 282 passed; e2e 357 passed; ty 0.

## Final verification (all five, run in full at `fe24a26`)

    $ .venv/bin/ruff check src tests
    All checks passed!

    $ .venv/bin/pytest tests/unit -q -p no:cacheprovider
    1897 passed, 9 warnings in 55.41s

    $ .venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema
    282 passed, 1 warning in 32.45s

    $ .venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e
    357 passed, 159 warnings in 46.27s

    $ .venv/bin/ty check src 2>&1 | tail -1
    All checks passed!

`git status --short` prints nothing.

Counts moved from the handover baseline (unit 1882 -> **1897**, +15 cases; schema 277 -> **282**,
+5 cases). e2e and ty are unchanged.

## For fixer 3

- **`tests/unit/test_subscription_attribution.py` was edited by me**, so start from the current
  file. WR-31 (`:305-315`) and WR-32 (`:576-615`) are untouched and their line numbers are
  unchanged — my edits are the `_upsert` helper near the end of the file and the rewritten
  `TestTheDeferredKeysAreClassifiedWhereTheyAreEvaluated`, both below `:615`.
- **`tests/unit/test_google_play_notifications.py` was edited by me.** WR-30 asks for a case beside
  `TestTheStateMap` (still at `:155`) — unaffected. I added `TestTheCredentialRefreshIsCapped` and
  `TestTheRebuildIsSerializedAndFloored`, plus `asyncio`, `PLAY_HTTP_TIMEOUT_SECONDS` and
  `CappedRefreshRequest` to the imports. `_RecordingSession` and `_RefreshingCredential` are new
  module-level doubles; do not collide with those names.
- **`tests/unit/test_auth_package_shape.py`'s `CURRENT` is now `(8, 25, 69)`.** If WR-30/31/32 add
  anything under `src/nativespeaker/api/auth/`, that literal has to move again.
- **`tests/unit/test_restore_proof.py`:** WR-30's second half asks for
  `assert restored.purchased_at == PURCHASED_AT` at `:255`. That region is untouched; my edit is
  the rewritten deferred-keys class at ~`:805`.
- **No test finding is made moot by my fixes**, and no expected value in WR-30/31/32/40 changes.
  One thing to know: `SubscriptionsDB.upsert_subscription` now takes a required keyword-only
  `clock_read`, so any *new* direct call to it needs that argument.
- `tests/schema/test_subscription_race.py` gained `before_first_write` on `_RacedSession` /
  `run_attempt` (default `None`, so every existing caller is unchanged) and a `signed_at`
  passthrough on `notification_for`.

---

## Fixer 3 — test suites

### WR-30 — FIXED
**Commit:** 5fbb157
**Root cause:** `tests/unit/test_google_play_notifications.py` drove
`PlayDeveloperSubscriptions.read()` 128 times but read only four of the thirteen fields of the
`VerifiedNotification` it returns (`status`, `expires_at`, `grace_period_expires_at`, `provider`).
Nine fields — including `signed_at`, the sole input to `SubscriptionsService.ingest`'s
out-of-order guard that fixer 2 hardened under WR-10 — had no assertion anywhere in the unit tree.
`tests/unit/test_restore_proof.py` had the same hole for `read_for_restore`'s `purchased_at`.
**Change:** added `TestThePlayReadReportsTheNotificationValueType`, one case that reads an ordinary
`SUBSCRIPTION_STATE_ACTIVE` body through the existing `_read` helper and asserts **all thirteen**
fields against `_subscription_body`'s own constants — the shape
`test_restore_proof.py::TestThePlayReadReportsTheRestoreValueType` already uses. Added
`assert restored.purchased_at == PURCHASED_AT` to that restore case, importing `PURCHASED_AT`
alongside the constants that file already borrows from the Play unit module.
**Mutation proof:** four probes, each applied, run and reverted in one bash call, tree verified
clean after each (`git status --short`):

| probe (`src/nativespeaker/api/auth/google_play.py`) | targeted test |
| --- | --- |
| `:330 signed_at=signed_at` → `signed_at=None` | **1 failed** |
| `:331 purchased_at=subscription.startTime` → `purchased_at=None` | **1 failed** |
| `:324 transaction_id=subscription.latestOrderId` → `transaction_id=None` | **1 failed** |
| `:386 purchased_at=subscription.startTime` → `purchased_at=None` (restore arm) | **1 failed** |

On revert both cases go green again (1 passed each).
**Correction to the review:** none — the review's suggested assertion catches its own probe. I
widened it from the seven fields it listed to the whole value type, which costs nothing and closes
`product_id`/`tier_id` in the same case.
**Verification:** ruff clean; unit 1898 passed; schema 282 passed; e2e 357 passed; ty 0

### WR-31 — FIXED
**Commit:** e00d317
**Root cause:** `test_the_two_store_ids_land_in_their_own_columns` read `writer.inserted[0]`, the
kwargs `_RecordingSubscriptions.insert_purchase` captured. That stand-in **never calls the real
`SubscriptionsDB.insert_purchase`**, so no assertion under it can see which column each id lands
in. Swapping the two assignments in `crud/subscriptions.py:298-299` left the whole tree green.
**Change:** added
`tests/e2e/test_app_store_webhook.py::TestTheVerifiedNotificationReachesCommittedRows::test_the_two_store_ids_land_in_their_own_columns`,
which posts one verified Apple delivery (whose factory already gives `external_id !=
transaction_id`) and selects the row back out of `core.store_purchases` through the existing
`_purchases_of` helper, asserting `store_original_transaction_id == external_id` and
`store_transaction_id == transaction_id`. Renamed the unit case to
`test_the_two_store_ids_are_passed_in_their_own_arguments` and pointed its docstring at the e2e
case, so its name now states the service-level property it actually proves.
**Mutation proof:** swapped `store_transaction_id=` / `store_original_transaction_id=` at
`src/nativespeaker/api/crud/subscriptions.py:298-299` — the new e2e case **1 failed**; reverted in
the same call — **1 passed**. Tree clean afterwards.
**Correction to the review:** the review's suggested remedy is self-defeating and I did not apply
it. It proposes reading `writer.purchases[...]` — but that dictionary is built by
`_RecordingSubscriptions.insert_purchase`'s **own** constructor from the very kwargs the case
already reads, so it cannot fail on a mutation in the crud. I verified the premise directly: the
stand-in never reaches `SubscriptionsDB.insert_purchase`. The review concedes this ("That still
measures the stand-in's own constructor") and adds "pair it with one schema case that … selects
both columns back out of `core.store_purchases`" — that pairing is the whole remedy, and I put it
in e2e rather than schema because e2e already drives the real route, the real crud and a real
database, and already owns `_purchases_of`.
**Verification:** ruff clean; unit 1898 passed; schema 282 passed; e2e 358 passed; ty 0
(Note: the docstring ratchet `tests/unit/test_docstring_bar.py` tripped on a four-line docstring in
this change and was repaired in-run by shortening it to three.)

### WR-32 — FIXED
**Commit:** 668d6d4
**Root cause:** all three assertions in `TestTheAppendedEventNamesTheTierTheLocksSettledOn` read
`writer.appended`, the kwargs the recording stand-in captured; `audit.subscription_events.old_tier_id`
was selected back out of the database nowhere in the tree. `old_tier_id=new_tier_id` in
`SubscriptionsDB.append_event` therefore left every suite green.
**Change:** two reads of the real column.
1. `tests/e2e/test_google_play_webhook.py` — the existing event-row tracer now asserts
   `(events[0].old_tier_id, events[0].new_tier_id) == (None, PAID_TIER_ID)`.
2. `tests/e2e/test_app_store_webhook.py` — new case
   `test_a_tier_change_records_the_tier_the_row_moved_off`, which delivers two notifications for one
   `external_id` with different tiers and asserts both audit rows:
   `(None, "paid")` then `("paid", "registered")`.
**Mutation proof:** two probes on `src/nativespeaker/api/crud/subscriptions.py::append_event`,
applied/run/reverted in one call:
- `old_tier_id=old_tier_id` → `old_tier_id=new_tier_id` (the reviewer's own): **2 failed** (both
  new assertions).
- `old_tier_id=old_tier_id` → `old_tier_id=None`: **1 failed, 1 passed** — caught by the
  tier-change case only.
On revert, **2 passed**.
**Correction to the review:** the review's one-line remedy catches its own probe but only pins the
NULL side, so a second, equally real corruption — `old_tier_id` hard-coded to `None` — would still
pass the whole tree. The second probe above demonstrates that. I applied the review's line and
added the transition case that closes it. The transition is driven on the Apple path because the
Google product map has one product and therefore one reachable tier, so no Play delivery can move
the tier; `SubscriptionsService.ingest` is provider-agnostic (44-REVIEW appendix, partition E), so
one path proves the column.
**Verification:** ruff clean; unit 1898 passed; schema 282 passed; e2e 359 passed; ty 0

### WR-40 — FIXED
**Commit:** 30b8b7b
**Root cause:** `PLAY_FAILURES` parametrised `AttributionConflict` as one of "the three failures of
the read", but its only raise site is `services/subscriptions.py:109`, inside
`SubscriptionsService.ingest`. `scripted_google_play` raises the scripted exception from
`FakePlaySubscriptions.read`, i.e. from the `verify_google_play_notification` dependency, which
FastAPI resolves before `get_subscriptions_service`; no database session is opened on that arm, so
the arm's three "wrote nothing" assertions were true by construction. The Google route consequently
had no case at all that drove a real attribution conflict and read its answer.
**Change:** dropped `AttributionConflict` from `PLAY_FAILURES`/`PLAY_FAILURE_IDS` (and its now
unused import), stated the reason in the comment above the tuple, and added
`TestAChangedAttributionIsRefusedAndNothingIsWritten` mirroring the Apple twin: a shared
`_record_then_conflict` helper seeds a store token, delivers one purchase through the **real**
`real_google_play_seam` under that token (asserting the 200, which is the control that a purchase
row exists to conflict with), then delivers a later one naming a different owner. Two cases assert
the shared 500 body, and that the second delivery added no row of any of the three kinds — its own
replay key holds no event row and the purchase row count is still 1. Generalised `_replay_key` with
a keyword-only `event_time_millis` so the second delivery's key can be named.
**Mutation proof:** replaced the single raise site
`raise AttributionConflict(notification.provider, recorded.id)` in
`src/nativespeaker/api/services/subscriptions.py` with `pass` (the reviewer's exact probe, which
left the deleted parametrised arm green): both new cases **failed**. Reverted in the same call:
**2 passed**. Tree clean afterwards.
**Correction to the review:** the finding's premise and remedy are both correct. I placed the new
case in a class of its own rather than inside `TestNoRecordCarriesASensitiveValue`, which is a log
hygiene control, and used a fresh `purchase-token-{uuid4()}` per case rather than the shared module
constant, so the two cases cannot interfere.
**Verification:** ruff clean; unit 1898 passed; schema 282 passed; e2e 360 passed; ty 0

---

## Final verification (all five, run in full at 30b8b7b)

```
.venv/bin/ruff check src tests
  All checks passed!
.venv/bin/pytest tests/unit -q -p no:cacheprovider
  1898 passed, 9 warnings in 55.61s
.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema
  282 passed, 1 warning in 32.60s
.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e
  360 passed, 159 warnings in 48.28s
.venv/bin/ty check src 2>&1 | tail -1
  All checks passed!
git status --short
  (empty)
```

Deltas from the fixer-2 baseline: unit +1 (WR-30's value-type case), schema unchanged, e2e +3
(WR-31 one case, WR-32 one case, WR-40 two cases added and one parametrised arm removed).
No source file was changed by this fixer; every source mutation was a probe, applied and reverted
inside a single bash call, with `git status --short` verified clean afterwards.

---

_Fixed: 2026-09-10_  
_Fixer: Claude (gsd-code-fixer x3, sequential)_
