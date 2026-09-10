---
phase: 44-post-webhooks-google-play-rtdn
reviewed: 2026-09-10T00:00:00Z
depth: standard
files_reviewed: 140
files_reviewed_list:
  - AGENTS.md
  - config/config.yaml
  - docker-compose.yml
  - Dockerfile
  - .dockerignore
  - .env.example
  - .gitignore
  - k8s/templates/deployment.yaml
  - k8s/templates/httproute-app.yaml
  - k8s/templates/httproute-auth.yaml
  - k8s/templates/httproute-health.yaml
  - k8s/templates/httproute-webhooks.yaml
  - k8s/templates/NOTES.txt
  - k8s/templates/security-policy.yaml
  - k8s/values.yaml
  - migrations/20260818_01_initial-release.sql
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/error_handlers.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/devicecheck.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/chats.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/crud/violations.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/logs.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/schemas/api.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/schemas/llm.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/llm.py
  - src/nativespeaker/api/services/quota.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/services/sync.py
  - src/nativespeaker/api/tables/auth.py
  - src/nativespeaker/api/tables/chats.py
  - src/nativespeaker/api/tables/grants.py
  - src/nativespeaker/api/tables/identities.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/purchases.py
  - tests/e2e/conftest.py
  - tests/e2e/refusal_sites.py
  - tests/e2e/test_app_store_webhook.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/e2e/test_create_user.py
  - tests/e2e/test_google_play_webhook.py
  - tests/e2e/test_llm_schema.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/e2e/test_sign_out_all.py
  - tests/e2e/test_sync.py
  - tests/e2e/test_users_me.py
  - tests/schema/conftest.py
  - tests/schema/test_apply_rollback.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_constraints.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_harness_guards.py
  - tests/schema/test_inventory.py
  - tests/schema/test_registration_pairing.py
  - tests/schema/test_restore_race.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_sync_lock_freedom.py
  - tests/unit/conftest.py
  - tests/unit/error_tree.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_chats_crud.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_config.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_conversion_carries_usage.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_identities_crud.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_identity_flip.py
  - tests/unit/test_jwks_offload.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_logging.py
  - tests/unit/test_models.py
  - tests/unit/test_monthly_period.py
  - tests/unit/test_purchases_crud.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_services.py
  - tests/unit/test_spent_free_grant_refusal.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_subscription_grant_write.py
  - tests/unit/test_subscription_store_clock.py
  - tests/unit/test_sync_clock_capture.py
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_tables_metadata.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users_me.py
  - tests/unit/test_users.py
  - uv.lock
findings:
  critical: 1
  warning: 11
  info: 17
  total: 29
status: issues_found
---

# Phase 44: Code Review Report (incremental re-review)

**Reviewed:** 2026-09-10  
**Depth:** standard  
**Files Reviewed:** 140  
**Scope:** every file changed since the previous `44-REVIEW.md` commit `c296f9d`  
**Status:** issues_found

## Summary

This is an incremental re-review. The scope is the 140 files that changed since the
previous phase-44 review was committed, which is the whole surface the phase 35-43
review-and-fix passes moved. Six reviewers took disjoint module partitions of that one
scope — auth adapters and the webhook schema; services, crud and tables; app wiring,
handlers and the cross-cutting modules; the unit suite; the e2e and schema suites; and
deployment, configuration, packaging and the migration — with disjoint finding-ID blocks,
merged here without narrowing.

The Google-signed OIDC path itself held up under attack. Expired, wrong-`aud`,
wrong-`iss`, `exp`-less and HS256-over-the-public-key tokens are all refused against the
installed PyJWT; key rotation resolves on a `kid` miss; the purchase token cannot escape
its URL path segment; and the Play state map fails closed on every value Google has not
published. What survives falls into four groups: two unbounded blocking calls on the
shared threadpool that also serves every authenticated request's identity check; one
concurrency hole where newest-wins is serialized by a lock that is not always taken; a
logging configuration that puts bound SQL parameters — including a store purchase token —
into the log store on a failed write; and a set of tests that pass whether or not the
code under them is correct, three of them mutation-proved.

Each partition's dropped candidates are recorded in the appendix, with the ratified
decision that settled the point or the measurement that disproved it.

## Partition notes

**Partition A — auth adapters + webhook schema**

The Google-signed OIDC path itself holds up under attack. I proved empirically, against the
installed PyJWT 2.12.1, that `DECODE_OPTIONS` + `DECODE_ALGORITHMS` refuse an expired token, a
wrong `aud`, a wrong `iss`, an absent `exp`, and HS256-over-the-public-key; that `required_claims`
pins `email`/`email_verified` after decode on verified claims only; and that `PyJWKClient.
get_signing_key` still refreshes on a `kid` miss, so rotation works and `_DEFINITIVE_KID_MISS`
matches the real message text. I also proved that httpx really does delete a `..` path segment
(`.../tokens/..` → `.../subscriptionsv2`), so `_names_one_path_segment` is load-bearing and
correct, and that `AwareDatetime` refuses a naive Play stamp. The state map fails closed on every
unlisted `subscriptionState`, and `ENTITLED_STATUSES` excludes `billing_retry`, so Play's
`ON_HOLD` (whose line-item expiry is already in the past) cannot reach the service's term guard
and poison the queue.

What survives is one unbounded blocking call and one unbounded rebuild, both on the threadpool
that also serves every authenticated request's identity check, plus documentation that has
drifted from the code.
## Findings

## Critical

### CR-20: The engine leaks bound parameters, so a failed write writes the challenge handle and the store purchase token into the log store

**File:** `src/nativespeaker/api/app/lifespan.py:126-130` (with `src/nativespeaker/api/app/error_handlers.py:79-85`)
**Issue:** `build_db_engine` builds the one engine with `pool_size`, `max_overflow`, `pool_pre_ping`
and `pool_recycle`, and does **not** set `hide_parameters=True`. `grep -rn hide_parameters src tests`
returns nothing, so the SQLAlchemy default `False` stands. Every `DBAPIError` / `StatementError`
therefore renders `[parameters: {...}]` in its `__str__`, and every one of them that escapes the CRUD
layer reaches `generic_error_handler`, which records it with the full chain:

```python
logger.error("unhandled_exception", exc_info=exc)     # error_handlers.py:84
```

This defeats, on the error path, the rule the rest of the module enforces by hand:
`error_handlers.py:54-56` ("A rejected value can be a live secret -- a challenge handle in a
malformed body reaches this handler intact -- so only `loc` and `type` are logged, and `input` never
is"), `AttributionConflict.log_fields` (`errors.py:315-318`, "on the Google path the lifecycle key is
the purchase token itself (44 D-10), which is not admissible in a log line"), and the module rule at
`auth/google_play.py:1-2`. The project already recorded the mechanism once — the point fix at
`services/auth.py:410-413` logs `type(failure).__name__` instead of the exception precisely because
"a SQLAlchemy `StatementError` renders its bound parameters and the challenge handle is one of them"
(`.planning/phases/37.4-.../37.4-06-SUMMARY.md:117`). That fix covers one `except` block. The engine
flag, which covers all of them, was never set.

**Failure scenario:** reproduced against the real `setup_logging` + real `generic_error_handler`:

```
$ .venv/bin/python  # IntegrityError over an INSERT carrying a handle and a device token
LOG contains handle: True
LOG contains device token: True
2026-09-10 06:58:15 [error    ] unhandled_exception
sqlalchemy.exc.IntegrityError: (builtins.Exception) duplicate key value violates unique constraint
[SQL: INSERT INTO core.auth_challenges (challenge_id, subject, device_token) VALUES ($1,$2,$3)]
[parameters: {'challenge_id': 'CHALLENGE-HANDLE-SECRET-123', 'subject': 'firebase-uid-xyz',
              'device_token': 'APPLE-DEVICECHECK-TOKEN-SECRET'}]
```

Reachable, uncaught, on ordinary paths:

- `ChallengesDB.issue` (`crud/challenges.py:49-56`) does `session.add(AuthChallenge(challenge_id=...))`
  then a bare `await session.flush()` with no `except`. A serialization failure (SQLSTATE 40001), a
  statement timeout, a connection dropped mid-statement or a CHECK violation raises a
  `StatementError` whose parameters include the **live single-use challenge handle**. It escapes
  `issue_challenge`, is not an `AppError`, is not handled by `ExceptionMiddleware`, and lands in
  `generic_error_handler`.
- `IdentitiesDB.insert_account` (`crud/identities.py:125-131`) deliberately re-raises the original
  `IntegrityError` when `is_unique_violation` is false — that INSERT's parameters carry the user
  email, the issuer and the subject.
- `GrantsDB` (`crud/grants.py:240-244`) and `SubscriptionsDB` re-raise the same way; the
  subscriptions INSERT carries `notification_uuid`, which is
  `google_play:{purchase_token}:{millis}:{type}` — the Play purchase token in clear.
- The chat writes carry the user's phrase, the content 37.5 WR-03 went to the trouble of keeping out
  of the log store at DEBUG.

The logs are aggregated and retained (SHARED-INVARIANTS forbids a cleanup job), so a handle that is
valid for `CHALLENGE_TTL_SECONDS` and a store purchase token that is valid indefinitely both become
permanent log content.

**Fix:** one keyword on the one engine (verified accepted by `create_async_engine`; the exception
then renders `[SQL parameters hidden due to hide_parameters=True]` and keeps the SQL text, which
carries no secret):

```python
    return create_async_engine(db.url,
                               pool_size=db.pool_size,
                               max_overflow=0,
                               pool_pre_ping=True,
                               pool_recycle=_DB_POOL_RECYCLE_SECONDS,
                               # Every write here binds a secret -- the challenge handle, the
                               # DeviceCheck token, the purchase token inside `notification_uuid`.
                               # A StatementError renders its bound parameters, and
                               # `generic_error_handler` logs the whole chain.
                               hide_parameters=True)
```

Add one unit case asserting `build_db_engine(...).sync_engine.hide_parameters is True`, so the flag
cannot be dropped silently.

## Warning

### WR-01: The Play credential refresh runs with google-auth's 120-second default timeout

**File:** `src/nativespeaker/api/auth/google_play.py:377-380`

**Issue:** `_get` refreshes the credential off the loop but passes no timeout:

```python
if not self._credential.valid:
    await run_in_threadpool(self._credential.refresh,
                            google.auth.transport.requests.Request())
```

I checked the installed library rather than assuming. `google.auth.transport.requests.Request.
__call__` has the signature `(self, url, method='GET', body=None, headers=None, timeout=120,
**kwargs)`, and `service_account.Credentials._perform_refresh_token` reaches
`_client.jwt_grant(request, self._token_uri, assertion)`, which passes **no** `timeout` — so the
120-second default applies, and `_token_endpoint_request` runs with `can_retry=True`. The rest of
this module is explicitly capped for exactly this reason: `PLAY_HTTP_TIMEOUT_SECONDS = 8` on the
httpx client, `fetch_timeout_seconds=3.0` on the JWKS client. The one call that is not capped is
the one that blocks a real OS thread.

This was raised as WR-06 of the previous `44-REVIEW.md` and was never fixed: `git log` for this
file shows no commit touching the refresh block, and the enclosing `_get` was rewritten in this
diff (the `quote()` fix) without it. It carries no override note anywhere in the phase records —
only CR-01 was accepted as an override.

**Failure scenario:** `oauth2.googleapis.com` black-holes traffic (or ADC is a service-account key
file rather than the GKE metadata server — `.env.example` documents that deployment). Each pod's
credential expires roughly hourly. Every RTDN delivery and every `POST /auth/restore-subscription`
that finds `self._credential.valid` false now occupies one anyio worker thread for up to 120 s,
retried, so up to ~360 s per call. Starlette's threadpool defaults to 40 workers and is the same
pool `get_identity` uses via `run_in_threadpool`. Pub/Sub redelivers, and the restore route is
user-invoked, so the pool drains and **every authenticated route stops resolving identity** while
Google's token endpoint is down — a fault in a background revenue path taking out the whole API.

**Fix:** cap it the way the two sibling calls are capped, by wrapping the transport callable:

```python
_PLAY_REFRESH = google.auth.transport.requests.Request()

def _timed_refresh_request(url, method="GET", body=None, headers=None,
                           timeout=PLAY_HTTP_TIMEOUT_SECONDS, **kwargs):
    """`Request.__call__` defaults to 120 s; the one blocking call here gets the module's own cap."""
    return _PLAY_REFRESH(url, method, body, headers, timeout, **kwargs)
```

and pass `_timed_refresh_request` to `self._credential.refresh` instead of a bare `Request()`.

### WR-02: The push verifier is rebuilt — a blocking JWKS fetch — before any credential is checked, unserialized and unbounded

**File:** `src/nativespeaker/api/auth/google_play.py:219-231` (with
`src/nativespeaker/api/app/lifespan.py:209-212`)

**Issue:** the lazy rebuild added by `4bb7918 fix(43): WR-41` is right in intent — a JWKS blip at
boot should not permanently disable the route — but it is unguarded:

```python
async def verify(self, bearer: str) -> None:
    if self._verifier is None and self._build is not None:
        self._verifier = await run_in_threadpool(self._build)
    if self._verifier is None:
        raise Unavailable(stage="google_push_verify")
```

`self._build` is `lambda: build_google_push_verifier(config.google_play)`, and
`JWTVerifier.__init__` calls `self._jwks_client.get_signing_keys()` — a synchronous
`urllib.request.urlopen` to `https://www.googleapis.com/oauth2/v3/certs` with
`fetch_timeout_seconds=3.0`. Three properties make this a live hazard rather than a warm-up
detail: it runs **before** the bearer is examined at all, so no credential gates it; it is **not
serialized**, so N concurrent requests each build their own `PyJWKClient` and each make their own
fetch; and it is **unbounded in rate**, because nothing records that a rebuild was just attempted
and failed.

`/webhooks/google-play/rtdn` is one of only two routes outside the gateway's JWT policy, and
`k8s/templates/NOTES.txt:26` states plainly that no rate-limit policy ships in the chart, so this
is reachable by anyone who can POST to the path with any `Authorization: Bearer x` header.

**Failure scenario:** the pod boots while egress or DNS is not yet ready (routine in Kubernetes),
so `build_google_push_verifier` returns `None` at line 192 of `lifespan.py` and the route enters
the rebuild state. An attacker — or merely Pub/Sub's own redelivery backlog — sends 50 concurrent
POSTs with a junk bearer. All 40 anyio worker threads are consumed by 3-second JWKS fetches, plus
50 outbound HTTPS requests to `googleapis.com` per burst. That same pool serves `get_identity`, so
every authenticated request stalls. The state persists for as long as Google's key endpoint is
unreachable from the pod, and each burst re-pays the whole cost.

**Fix:** serialize the rebuild and put a floor under its retry rate, keeping the fix's intent:

```python
def __init__(self, *, verifier, build=None, rebuild_interval_seconds: float = 30.0) -> None:
    self._verifier = verifier
    self._build = build
    self._rebuild_lock = asyncio.Lock()
    self._rebuild_interval = rebuild_interval_seconds
    self._next_rebuild = 0.0

async def verify(self, bearer: str) -> None:
    if self._verifier is None and self._build is not None:
        async with self._rebuild_lock:
            # Re-read under the lock: a rival that just built one leaves nothing to do here.
            if self._verifier is None and time.monotonic() >= self._next_rebuild:
                self._next_rebuild = time.monotonic() + self._rebuild_interval
                self._verifier = await run_in_threadpool(self._build)
    ...
```

### WR-10: Newest-wins is serialized only by the buyer's grant locks, so an older delivery can become canonical for an unowned or grant-less subscription

**File:** `src/nativespeaker/api/services/subscriptions.py:63-99` (with `src/nativespeaker/api/crud/subscriptions.py:81-100, 216-228`)

**Issue:** The out-of-order guard rests on re-reading the canonical row *under the grant locks*:

```python
marked_active = ([] if owner is None
                 else await self.subscriptions_db.lock_grants(owner))          # :66-67
...
# The whole row under the grant locks: the pre-lock read misses a rival's newer clock, or its insert.
settled = await self.subscriptions_db.read_subscription(...)                   # :79-81
```

`lock_grants` → `lock_active_grants_of([user_id])` emits `SELECT ... WHERE user_id IN (...) AND status = 'active' ... FOR UPDATE` (`crud/grants.py:125-131`). When that statement matches **zero rows it takes no lock at all**, and when `owner is None` the statement is never issued. In both cases the re-read at `:79-81` is protected by nothing.

The write itself takes no lock either. `upsert_subscription`'s in-place arm is a plain ORM mutation (`crud/subscriptions.py:220-226`) flushed as `UPDATE core.subscriptions SET status=..., tier_id=..., store_signed_at=..., updated_at=... WHERE id = :id`. There is no CAS predicate (unlike `claim_subscription_owner`, which restates the read), no `version_id_col` on `Subscription` (`tables/purchases.py:87-106`), and no `FOR UPDATE` on the row (forbidden by 43 D-16). So two concurrent deliveries for one lifecycle key are last-writer-wins on `status`, `tier_id` and `store_signed_at`.

Note the two unique indexes that *do* serialize the first-ever delivery pair (`ix_subscriptions_provider_external_id` and `core.store_purchases`' `UNIQUE (provider, external_id)`) both go quiet once the rows exist: `read_purchase` returns a row, so `insert_purchase` is skipped (`services/subscriptions.py:132`), and `upsert_subscription` takes the update arm. Only `audit.subscription_events.notification_uuid` is still inserted, and two *different* notifications carry two different keys.

**Failure scenario:**
- Subscription `S = (google_play, tokenX)`, owner `U`, status `expired`, `store_signed_at = T0`. `U` holds no grant marked active — ingestion expired it when the term lapsed, and it never reactivates (spec 08:42).
- Pub/Sub delivers RTDN **A** (`eventTimeMillis = T1`, `SUBSCRIPTION_RENEWED`) and RTDN **B** (`eventTimeMillis = T2 > T1`, later state) concurrently to two workers.
- Both workers: `owner = U` → `lock_grants(U)` returns `[]` and locks nothing → `read_owner` returns `U` → guard passes → `settled` re-read shows `store_signed_at = T0` on both, so `notification.signed_at < settled.store_signed_at` is false for both and neither takes the superseded arm (`:84-99`).
- Worker B flushes and commits first (`status`/`tier_id` = B's, `store_signed_at = T2`). Worker A then commits (`status`/`tier_id` = A's, `store_signed_at = T1`).
- Canonical state is now the **older** delivery's, and `store_signed_at` has moved backwards from `T2` to `T1`, so a subsequent straggler signed between `T1` and `T2` is applied instead of refused.
- The wrong value is load-bearing on the restore path: `services/restore.py:62` takes entitlement from `stored.status` (D-06) and `services/restore.py:125` grants `stored.tier_id`. A tier change that lost this race is handed to the caller as their entitlement.

Same hole for `owner is None`, which is the state of every Play purchase whose `obfuscatedExternalAccountId` resolves to no binding.

**Fix:** give the in-place arm the CAS the owner arm already has, so a rival that moved the row wins the way the design says it should. In `upsert_subscription`, capture `stored.store_signed_at` before mutating and emit the update conditionally (mirroring `_claim_owner_statement`):

```python
clock_read = stored.store_signed_at
...
updated = (await self.session.exec(
    update(Subscription)
    .where(col(Subscription.id) == stored.id,
           # The clock the guard above decided on; a rival that advanced it wins.
           col(Subscription.store_signed_at).is_not_distinct_from(clock_read))
    .values(**values)
    .execution_options(synchronize_session=False))).rowcount
if updated != 1:
    return stored, WriteOutcome.lost_race
```

`_settle` then answers the 500 the store's resend recovers from, which is the behaviour every other lost race in this module already has.

### WR-11: A commit-time integrity failure is reported as a lost race with no diagnostic at all

**File:** `src/nativespeaker/api/services/subscriptions.py:169-186` (identically `src/nativespeaker/api/services/restore.py:172-177, 213-222`)

**Issue:** Every other integrity handler in this partition classifies before deciding — `crud/subscriptions.py:135-140`, `:272-277`, `:297-303`, `:359-365`, `:410-415` and `crud/grants.py:240-245`, `:318-323`, `:348-354` all run `if not is_unique_violation(violation): raise`, with the comment "a CHECK or a foreign key is a broken invariant, never a race this lost". The commit handler skips that step:

```python
try:
    await self.session.commit()
except IntegrityError:
    # The two entitlement keys are DEFERRABLE, so this statement is where they are evaluated.
    await self._settle(WriteOutcome.lost_race, notification)
```

The two DEFERRABLE constraints named in the comment are both **FOREIGN KEYs** on `core.access_grants` (migration `:242-247`), i.e. SQLSTATE 23503, not 23505. So the one violation class this handler exists for is exactly the class `is_unique_violation` was written to re-raise, and every other class (CHECK `ends_at > starts_at`, the `source`/`subscription_id` CHECK, NOT NULL) is swallowed with it.

`_settle` then discards the only diagnostic: it logs `store_notification_race_lost` with `provider` alone, and raises `InternalError`, whose `log_level` is `None` (`errors.py:138-142`), so `app_error_handler` short-circuits at `if exc.log_level is not None:` (`app/error_handlers.py:36`) and writes nothing. The `IntegrityError` — the only thing that names the constraint — never reaches a log line, and it is not chained (`raise InternalError`, no `from`).

**Failure scenario:** a writer bug leaves an active `source='subscription'` grant against a subscription this transaction moved out of the entitled set — the exact state `tests/schema/test_subscription_ingestion.py::TestTheDeferrableForeignKeyIsTheBackstop::test_a_grant_left_active_fails_the_commit` proves the deferred FK rejects. In production that deterministic, non-concurrent failure is logged once as `warning store_notification_race_lost provider=google_play`, the 500 makes Pub/Sub redeliver, the same commit fails again, and the loop runs to message retention. Nothing in the logs contains `access_grants`, `23503`, or a traceback, and the one line present points the operator at concurrency.

**Fix:** classify at the commit the way every flush already does, and keep the cause:

```python
except IntegrityError as violation:
    if not is_unique_violation(violation):
        # A deferred foreign key or a CHECK is a broken invariant, never a race this lost.
        logger.error("store_notification_commit_refused",
                     sqlstate=getattr(violation.orig, "sqlstate", None))
        raise
    await self._settle(WriteOutcome.lost_race, notification)
```

(`AppError` subclasses declaring `log_level = logging.ERROR` already render a traceback via `exc_info`, so re-raising the `IntegrityError` reaches the generic 500 handler with the constraint name intact.) Apply the same change to `RestoreService.restore`.

### WR-20: The quieted-library pin is a floor as well as a ceiling, so raising `LOG_LEVEL` inverts the signal

**File:** `src/nativespeaker/api/logs.py:61-64` (with `:12-20` and `.env.example:2-6`)
**Issue:** `setup_logging` sets the root level from config and then unconditionally does
`logging.getLogger(name).setLevel(logging.WARNING)` for the nine `_QUIETED_LIBRARIES`. A child
logger's level is evaluated at the call site and the record is then passed to every ancestor's
handlers regardless of the ancestors' levels, so `setLevel(WARNING)` raises those libraries above the
root whenever the root is above WARNING. The comment at `:12` claims the opposite — "Pinned **below**
the configured level" — and the intent recorded in 37.5 WR-03 was a ceiling for `DEBUG` only; the
`ERROR` direction was never considered.

**Failure scenario:** an operator raises `LOG_LEVEL` to `ERROR` during an incident to cut noise
(`.env.example:2-6` calls this "the one per-deployment logging lever"). Measured against the real
`setup_logging`:

```
setup_logging("ERROR")
log.warning("app_warning_should_be_hidden")                       -> not emitted
logging.getLogger("httpx").warning("...")                         -> EMITTED
logging.getLogger("sqlalchemy.engine").warning("...")             -> EMITTED
logging.getLogger("some.other.lib").warning("...")                -> not emitted
```

So the operator loses exactly the application's own WARNING vocabulary — `validation_error`,
`notification_rejected` with its `stage`, `google_play_configuration_absent`,
`devicecheck_credential_absent`, `firebase_revoke_failed`, `invalid_external_jwt` with its
`bounded_reason` — and keeps only httpx/httpcore/sqlalchemy/openai/langchain/urllib3/google.auth/
uvicorn.access chatter. `.env.example:133-138` names the `stage` field as "the only signal that
separates 'this deployment is misconfigured' from 'this token is not Google's'"; at `LOG_LEVEL=ERROR`
that signal is gone while library noise remains.

**Fix:** make the pin a ceiling only:

```python
    configured = logging.getLevelNamesMapping()[log_level.upper()]
    for name in _QUIETED_LIBRARIES:
        # A ceiling, never a floor: `setLevel` on a child outranks the root in both directions.
        logging.getLogger(name).setLevel(max(logging.WARNING, configured))
```

and correct the comment at `:12`, which currently states the behaviour the code does not have.

### WR-21: The database is the only backing service the lifespan never checks, so the pod reports Ready with an unusable one

**File:** `src/nativespeaker/api/app/lifespan.py:218-220` (with `:104-115` and
`k8s/values.yaml:32-42`)
**Issue:** `create_async_engine` opens no connection; SQLAlchemy connects lazily on first checkout.
`lifespan` therefore completes, logs `started`, and yields without ever having proved the database is
reachable. Every other dependency in the same function is checked and gets a named signal — the
Firebase credential (`firebase_admin_credential_absent`), DeviceCheck
(`devicecheck_credential_absent`), the App Store verifier and product map
(`app_store_configuration_absent`), the Play pins/credential/package/products
(`google_play_configuration_absent`), the push verifier warm-up
(`google_push_verifier_warm_up_failed`) — and `build_jwt_verifier` goes further and **fails boot**
on its own reasoning: "a pod without this verifier has nothing to be Ready for" (`:113-115`). That
argument applies verbatim to the database and is not applied to it.

`/health/ready` returns a literal 200 with no dependency check, and `k8s/values.yaml:35-41` points
both `readinessProbe` and `livenessProbe` at it.

**Failure scenario:** a rollout ships a wrong `DB_HOST` or a rotated `DB_PASSWORD` in the Secret.
The new pods boot, log `started model=... concurrency=... languages=[...]`, pass readiness within
`initialDelaySeconds: 5`, and the Deployment completes its rolling update — terminating the last
working pod. Every request then fails at `get_identity`'s `IdentitiesDB.resolve`, producing a 500 per
request and (see CR-20) an `unhandled_exception` traceback per request. There is no boot-time record
naming the database, and neither probe ever fails, so Kubernetes will not roll back or restart.

**Fix:** prove the connection once, at the point the engine is built, and treat it like the JWT
verifier:

```python
        db_engine = build_db_engine(config.db)
        # Proven once at boot, as the JWKS warm-up is: `create_async_engine` connects lazily, so
        # without this the pod is Ready before anything has reached Postgres.
        async with db_engine.connect():
            pass
```

An unreachable database then stops boot with the failure named, the pod never becomes Ready, and the
rollout halts on the previous ReplicaSet.

### WR-30: the Play webhook read's value type is unasserted — `signed_at`, `purchased_at` and `transaction_id` can be hard-coded to `None` and the whole test tree still passes

**File:** `tests/unit/test_google_play_notifications.py:140-203` (the `_read_through` / `_read`
helpers and the two classes that consume them), with `tests/unit/test_restore_proof.py:245-255`

**Issue:** `PlayDeveloperSubscriptions.read()` (`src/nativespeaker/api/auth/google_play.py:286-302`)
builds the twelve-field `VerifiedNotification` that the whole RTDN ingestion is derived from.
The phase-critical unit file drives that method 128 times but asserts **only** `status`,
`expires_at`, `grace_period_expires_at` and `provider`. `grep -n "attribution_token\|external_id\|
transaction_id\|purchased_at" tests/unit/test_google_play_notifications.py` returns nothing.
Contrast the sibling provider: every field of the Apple adapter's `_crossed()` is pinned by
`tests/unit/test_app_store_notifications.py` — I mutated all seven and every one failed a case.

**Failure scenario:** mutation-proved, apply-run-revert in one call, tree verified clean after each.

| probe on `google_play.py::read` | unit | e2e |
| --- | --- | --- |
| `signed_at=None, purchased_at=None` | **1867 passed** | **357 passed** |
| `transaction_id=None` | 460 passed (partition subset) | 28 passed (`test_google_play_webhook.py`) |
| `attribution_token=None` | 128 passed (`test_google_play_notifications.py`) | 2 failed — caught by e2e only |
| `external_id="x"` | 460 passed | 2 failed — caught by e2e only |

`PlayDeveloperSubscriptions` is constructed nowhere in `tests/schema`
(`grep -rn PlayDeveloperSubscriptions tests/` → `tests/e2e/conftest.py` and the two unit files
only), so the first row is a full-tree survivor. `signed_at` is the load-bearing one: it is the
sole input to `SubscriptionsService.ingest`'s out-of-order guard
(`services/subscriptions.py:84-86`, `notification.signed_at is not None and ... < settled.store_signed_at`).
With `signed_at` dropped, that guard can never fire on the Google path, and an RTDN redelivered
out of order after a renewal — Pub/Sub guarantees no ordering — is applied instead of superseded,
downgrading a paying subscriber's grant to `expired` with no test anywhere going red.
Two of the same family are also unpinned on the restore path:
`test_restore_proof.py:245-255` asserts six fields of `RestoredSubscription` but not
`purchased_at`, and hard-coding `read_for_restore`'s `purchased_at=None` passes its 220-test subset.

**Fix:** in `tests/unit/test_google_play_notifications.py`, add one case beside
`TestTheStateMap` that reads an ordinary `SUBSCRIPTION_STATE_ACTIVE` body through `_read_through`
and asserts the whole mapping against `_subscription_body`'s own constants — the shape
`test_restore_proof.py:245-255` already uses for `read_for_restore`:

```python
async def test_the_read_carries_every_field_the_ingestion_derives_from(self):
    notification = await _read_through(
        _play_reader(_answering(_subscription_body("SUBSCRIPTION_STATE_ACTIVE", expiry=UNEXPIRED))))

    assert notification.external_id == PURCHASE_TOKEN
    assert notification.transaction_id == ORDER_ID
    assert notification.attribution_token == ATTRIBUTION_TOKEN
    assert notification.notification_uuid == NOTIFICATION_KEY
    assert notification.event_type == EVENT_TYPE
    # The dependency's own instant, not a clock: the out-of-order guard reads only this field.
    assert notification.signed_at == SIGNED_AT
    assert notification.purchased_at == PURCHASED_AT
```

and add `assert restored.purchased_at == PURCHASED_AT` at `test_restore_proof.py:255`.

### WR-31: `test_the_two_store_ids_land_in_their_own_columns` asserts the recording stand-in, not the columns — the two ids can be swapped in the crud and the entire suite passes

**File:** `tests/unit/test_subscription_attribution.py:305-315`

**Issue:** the case is named for a column-level property and its docstring states the operational
reason for it ("an operator matches an App Store Connect record on these two, so the per-term id
is not the lifecycle key"). What it actually reads is `writer.inserted[0]`, i.e. the kwargs
`_RecordingSubscriptions.insert_purchase` (`:200-212`) captured — a stand-in for
`SubscriptionsDB.insert_purchase`. It proves the service passes the right two keyword arguments;
it says nothing about which column each lands in. No test anywhere reads either column back:
`grep -rn "store_transaction_id\|store_original_transaction_id" tests/` returns only
`tests/schema/test_inventory.py:309-310`, which asserts their SQL types.

**Failure scenario:** mutation-proved. Swapping the two assignments inside
`src/nativespeaker/api/crud/subscriptions.py:255-256`
(`store_transaction_id=store_original_transaction_id`, `store_original_transaction_id=store_transaction_id`)
leaves the whole tree green: **unit 291 passed** (partition subset), **schema 277 passed**,
**e2e 357 passed**. Every `core.store_purchases` row then records Apple's per-term
`transactionId` in the lifecycle column and the `originalTransactionId` in the per-term column
— and on the Google path, where both service arguments are the purchase token
(`services/subscriptions.py:138-140`), the swap is invisible forever, so the defect would only
surface as an operator failing to match an App Store Connect record during a refund dispute.

**Fix:** assert the columns, not the kwargs. `_RecordingSubscriptions.insert_purchase` already
builds a real `StorePurchase` from those kwargs (`:203-211`); read it back instead:

```python
stored = writer.purchases[(PurchaseProvider.apple, notification.external_id)]
assert stored.store_original_transaction_id == notification.external_id
assert stored.store_transaction_id == notification.transaction_id
```

That still measures the stand-in's own constructor, so pair it with one schema case that posts a
notification whose two ids differ and selects both columns back out of `core.store_purchases`.

### WR-32: `old_tier_id` is asserted only against the recording stand-in and is read back from the database nowhere — `append_event` can write the new tier into it and the whole suite passes

**File:** `tests/unit/test_subscription_attribution.py:576-615`
(`TestTheAppendedEventNamesTheTierTheLocksSettledOn`, assertions at `:590`, `:604`, `:614`)

**Issue:** this class exists specifically to protect `audit.subscription_events.old_tier_id`
(its docstring cites WR-61: "`old_tier_id` was copied out of the pre-lock read, which the
under-lock read replaced"). All three assertions read `writer.appended`, the kwargs captured by
`_RecordingSubscriptions.append_event` (`:214-218`). Nothing binds those kwargs to the column.
`grep -rn "old_tier_id" tests/` finds the column read back **nowhere** in the tree — only
`tests/schema/test_inventory.py:206,236` (its index and type). `new_tier_id` is read back
(`tests/e2e/test_google_play_webhook.py:287`, `tests/e2e/test_app_store_webhook.py:213`);
`old_tier_id` is not.

**Failure scenario:** mutation-proved. In `src/nativespeaker/api/crud/subscriptions.py:279-280`,
setting `old_tier_id=new_tier_id` leaves **unit 291 passed**, **schema 277 passed**,
**e2e 357 passed**. Every audit row would then record a no-op transition — `old == new` on the
free→paid purchase, on every mid-term tier change, and on the downgrade. The spec makes this row
the record of the transition (`09-webhook-google-play-rtdn.md`: "`old_tier_id`/`new_tier_id` NULL
when there is no tier transition"), and `44-REVIEW`/WR-61's stated motive is that "the audit trail
is what an operator reconstructs a disputed subscription from". The one class guarding it cannot
see the corruption.

**Fix:** extend the e2e case that already selects the event row. `tests/e2e/test_google_play_webhook.py:284-287`
holds `events[0]`; add the other half, driving a second delivery that moves the tier so the two
columns must differ:

```python
assert (events[0].old_tier_id, events[0].new_tier_id) == (None, PAID_TIER_ID)
```

(the first delivery for a new subscription has no prior row, so `old_tier_id` is NULL — which is
also the assertion that fails under the swap, because `new_tier_id` is not NULL).

### WR-40: the "attribution-conflict" arm of the shared-500 class scripts an exception the Play read seam cannot raise, so its "wrote nothing" assertions are true by construction

**File:** `tests/e2e/test_google_play_webhook.py:426-451`
**Issue:** `PLAY_FAILURES` (line 426-430) parametrises three exceptions as "the three failures of the read"
(class docstring, line 435-436). Two of them — `InternalError` and `UnmappedStoreProduct` — really are
raised inside `PlayDeveloperSubscriptions.read` (`src/nativespeaker/api/auth/google_play.py:270`, and
`_product_of` line 375). The third, `AttributionConflict`, is not: `grep -rn AttributionConflict src/`
returns exactly one raise site, `src/nativespeaker/api/services/subscriptions.py:109`, inside
`SubscriptionsService.ingest`. The Play seam has no code path that can produce it.

Because `scripted_google_play` swaps `app.state.play_subscriptions` for `FakePlaySubscriptions`, the
scripted `AttributionConflict` is raised from `read`, i.e. from
`verify_google_play_notification` — which FastAPI resolves *before* `get_subscriptions_service`
(`src/nativespeaker/api/app/dependencies.py:200-205`, and the docstring "before the handler and before
`get_db`"). No database session is ever opened on that arm. So the three assertions at lines 446-450
(`_counts(...) == before`, `_subscriptions_of(...) == []`, `_events_of(...) == []`) are guaranteed by
construction and can never fail, whatever the real guard does. The only non-vacuous thing the arm
proves is that `AttributionConflict` maps to a 500 body — which the unit error-contract tests and the
Apple twin (`tests/e2e/test_app_store_webhook.py:390-398`) already pin.

The consequence is a real gap: the Google RTDN route has **no** case that asserts the status or the
row effect of a *real* attribution conflict. The only case that drives one
(`TestNoRecordCarriesASensitiveValue._drive_every_recording_arm`, lines 494-513) discards every
response object.

**Failure scenario (mutation, applied and reverted in one call, tree verified clean afterwards):**
replace `raise AttributionConflict(notification.provider, recorded.id)` at
`src/nativespeaker/api/services/subscriptions.py:109` with `pass`, i.e. delete the guard that stops a
Play purchase token being re-attributed to a second account. Result:

```
FAILED .../TestNoRecordCarriesASensitiveValue::test_the_walk_sees_the_records_the_deliveries_produced
1 failed, 27 passed
```

`TestEveryFailedReadAnswersTheShared500::test_each_failure_answers_500_and_writes_nothing[attribution-conflict]`
stayed green through the removal of the very guard it is named for. The one detector is an incidental
set-equality over log event names in a hygiene control, not a case about the guard.

**Fix:** drop `AttributionConflict` from `PLAY_FAILURES`/`PLAY_FAILURE_IDS` (the class is about the
read, and the read cannot raise it), and add a case in `TestNoRecordCarriesASensitiveValue` — or a
class of its own — that drives the real conflict through the route and asserts the answer and the row
effect, mirroring the Apple twin:

```python
async def test_the_conflicting_delivery_answers_the_shared_500_and_writes_nothing(
        self, webhook_client, real_google_play_seam, _db_transaction):
    await _seed_store_token(_db_transaction, ATTRIBUTION_TOKEN)
    headers = {"Authorization": f"Bearer {_push_token()}"}
    for offset, attribution in ((0, ATTRIBUTION_TOKEN), (1000, OTHER_ATTRIBUTION_TOKEN)):
        real_google_play_seam.body = play_subscription_body(
            externalAccountIdentifiers={"obfuscatedExternalAccountId": attribution})
        body = _push_body(PURCHASE_TOKEN, event_time_millis=EVENT_TIME_MILLIS + offset)
        if offset == 0:
            assert (await webhook_client.post(PATH, json=body, headers=headers)).status_code == 200
            before = await _counts(_db_transaction)
            continue
        conflicting = await webhook_client.post(PATH, json=body, headers=headers)

    assert conflicting.status_code == 500
    assert conflicting.json() == INTERNAL
    # The second delivery carries its own replay key, so an accepted conflict would add an event row.
    assert await _counts(_db_transaction) == before
    assert await _events_of(
        _db_transaction, _replay_key_at(PURCHASE_TOKEN, EVENT_TIME_MILLIS + 1000)) == []
```

### WR-50: `requests` is imported at boot but is not a declared dependency

**File:** `pyproject.toml:31` (with `src/nativespeaker/api/auth/google_play.py:10`)
**Issue:** `pyproject.toml:31` declares `"google-auth>=2.49"` without the `requests` extra.
`uv.lock`'s `google-auth 2.49.1` entry lists exactly two dependencies, `cryptography` and
`pyasn1-modules` — `requests` is not one of them. Yet
`src/nativespeaker/api/auth/google_play.py:10` runs `import google.auth.transport.requests` at
module scope, and that module's body begins `import requests` (verified:
`inspect.getsource(google.auth.transport.requests)` contains `import requests`). `requests`
reaches this environment only through `app-store-server-library` (`uv.lock:46`) and
`cachecontrol` (`uv.lock:104`, via `firebase-admin`) — two edges this project does not control.

The import is on the boot path, not the route path: `app/lifespan.py:24` and
`app/dependencies.py:12` both import `auth.google_play` at module scope, so the failure is
whole-process, not one 503.

This re-raises `44-REVIEW.md` WR-01, which `44-VERIFICATION.md:208` recorded as "open, not
blocking". It is filed again because the convention it rests on has since been ratified twice
by the fix pass and applied to every other case: `e1ac461 fix(37.5): WR-77 declare sqlalchemy
and starlette, which src imports directly` and `4d63404 fix(43): WR-02 declare cryptography,
which src/ imports directly`. `pyproject.toml:7-11` now states that rule in the file itself
("Declared, not inherited: `src/` imports all three directly ... so a transitive range widening
would relock this project onto a version nothing here constrains"). google-auth's `requests`
edge is the one remaining case where the file does not do what its own comment says.

**Failure scenario:** `app-store-server-library` publishes a release that drops `requests`, or
`firebase-admin` drops the `cachecontrol` edge, and someone runs `uv lock --upgrade`.
`uv sync --frozen --no-dev --no-editable` (`Dockerfile:17`) then builds an image with no
`requests`. Every container from that image dies at import with
`ModuleNotFoundError: No module named 'requests'` before uvicorn binds a port, so both probes
fail and the Deployment CrashLoopBackOffs — the whole service, not just the RTDN route.

**Fix:** declare the extra that owns the module, at `pyproject.toml:31`:

```toml
    "google-auth[requests]>=2.49",
```

## Info

### IN-01: `PlaySubscription.linkedPurchaseToken` is parsed and read by nobody, and its comment names a reader that does not exist

**File:** `src/nativespeaker/api/auth/google_play.py:95-96`

**Issue:** the field carries the comment *"Parsed and not acted on: an upgrade's old token is the
restore route's to read."* `grep -rn "linkedPurchaseToken" src/ tests/` returns exactly one hit —
this declaration. `services/restore.py` never touches it, and neither does any test. The comment
asserts a consumer the codebase does not contain, which is worse than no comment: the next reader
of the upgrade path will go looking for the handling it promises.

**Fix:** delete the field, or, if it is being held for a later phase, say so honestly — *"Declared
so the response shape is complete; no code reads it today."*

### IN-02: `PubSubPushRequest.subscription` is dead, and the spec obligation it exists for is unmet and unrecorded

**File:** `src/nativespeaker/api/schemas/webhooks.py:25-28`

**Issue:** `subscription: str | None = None` is parsed and never read anywhere in `src/` or
`tests/`. `specs/auth-refactor-phases/09-webhook-google-play-rtdn.md` says the route must
*"validate the expected Play package name and expected subscription"*; the package name is
validated in `app/dependencies.py:220-224`, the Pub/Sub subscription is not, and there is no
`push_subscription` field in `GooglePlayConfig`. Unlike the other Play divergences, this one is
recorded nowhere: `grep -n "expected subscription" .planning/REQUIREMENTS.md
.planning/phases/44-*/*.md` returns nothing.

On the merits the check is close to worthless — the field is unauthenticated body content, and the
OIDC token's pinned `aud` plus pinned `email` already identify the push subscription far more
strongly. So the defect is the silence, not the missing check: an obligation from a binding spec
was dropped without a decision record, and a field survives to make it look satisfied.

**Fix:** either drop the field and record the divergence under PLAYHOOK-01 in
`.planning/REQUIREMENTS.md` with the reasoning above, or add `GooglePlayConfig.push_subscription`
and compare it in the dependency alongside the package name.

### IN-03: The module's "closed set" log guarantee is no longer true of its own `bodies` field

**File:** `src/nativespeaker/api/auth/google_play.py:1-2` and `:153-159`

**Issue:** the module docstring states *"Log labels come from a closed set: the purchase token, the
push token and every Play value are excluded."* Since the WR-05 fix added
`model_config = ConfigDict(extra="allow")` at line 112, `model_fields_set` includes every
undeclared key the RTDN JSON carried, and those keys are emitted verbatim:

```python
logger.info("google_play_notification_ignored",
            bodies=sorted(set(notification.model_fields_set) - _ENVELOPE_FIELDS))
```

I ran it: an RTDN carrying `{"brandNewThing": {...}, "voidedPurchaseNotification": {...}}` logs
`bodies=['brandNewThing', 'voidedPurchaseNotification']`. That is the whole point of the fix and it
works — but it is now the one place in the module where a payload-derived value reaches a log line,
which is exactly what the docstring says never happens. It is bounded (`PUBSUB_DATA_LIMIT` caps the
body at 16 KB before decoding) and structlog escapes the values, so there is no injection here; the
defect is that the module's stated invariant is now false and a later reader will trust it.

**Fix:** amend the docstring to name the one exception, e.g. *"...are excluded; the sole
payload-derived label is the `bodies` field-name list of an ignored notification, which is bounded
by `PUBSUB_DATA_LIMIT`."*

### IN-04: The RTDN body carries no bound before verification while the Apple envelope now does

**File:** `src/nativespeaker/api/schemas/webhooks.py:4-8` and `:18-22`

**Issue:** this diff added `max_length=APP_STORE_ENVELOPE_LIMIT` to `signedPayload` but
deliberately left `data` unbounded:

```python
class PubSubPushMessage(BaseModel):
    # No `messageId` and no bound here: Pub/Sub acknowledges 2xx alone, so anything pydantic
    # refuses is a 422 this subscription retries forever. `developer_notification_from` bounds it.
    data: str = ""
```

The retry reasoning is sound and I am not disputing it. What the comment does not account for is
that `PUBSUB_DATA_LIMIT` is enforced inside `developer_notification_from`, which
`app/dependencies.py:212` reaches only **after** `google_push_tokens.verify(...)` — whereas
FastAPI has already buffered the entire request body and parsed the whole JSON document to
construct `body: PubSubPushRequest` before the dependency's first statement runs. There is no
body-size middleware in `src/nativespeaker/api/app/main.py` and no `ClientTrafficPolicy` in
`k8s/`. So the constant protects the base64 decode, not the parse, and the two provider-callback
routes now have asymmetric protection against the same unauthenticated input.

The fix does not belong in this file — a pydantic `max_length` also runs after the parse and would
change nothing. Recording it here because this file is where the reasoning lives and the reasoning
is incomplete.

**Fix:** amend the comment to say what the bound does and does not cover, and raise the actual
remedy (a `Content-Length` / streaming guard in the app or an Envoy `ClientTrafficPolicy`
`bodyLimit`) with the owner of `app/main.py` and `k8s/`.

### IN-10: The never-reactivate arm reports `applied` for a write that wrote nothing

**File:** `src/nativespeaker/api/crud/subscriptions.py:330-333`
**Issue:** `WriteOutcome.applied` is documented as "it changed a row" (`:36-39`), and `replayed` as "it changed nothing". The lapsed-term arm returns `applied` having written nothing at all, which is the `replayed` case by the enum's own definition. Harmless today because both services only branch on `lost_race`, but the next reader of an outcome gets the wrong answer.
**Fix:** return `WriteOutcome.replayed` from `:333` and keep the comment that explains why nothing was written.

### IN-11: One log line passes a raw enum where every sibling passes `str(...)`

**File:** `src/nativespeaker/api/crud/subscriptions.py:350-351`
**Issue:** `logger.warning("manual_grant_superseded", grant_id=str(grant.id), source=grant.source)` passes `AccessGrantSource` unconverted, while `services/subscriptions.py:74`, `:184` and `services/restore.py:220` all pass `str(...)`. `AccessGrantSource` is a `StrEnum`, so a JSON renderer happens to agree, but a repr-based processor would emit `AccessGrantSource.manual` for this one field and `manual` everywhere else.
**Fix:** `source=str(grant.source)`.

### IN-12: `starts_at` on the Google path is the original subscription start, so every renewal grant records a start months in the past

**File:** `src/nativespeaker/api/services/subscriptions.py:113-114`
**Issue:** `starts_at = min(notification.purchased_at or self.evaluated_at, self.evaluated_at)`. On the Play path `purchased_at` is `SubscriptionPurchaseV2.startTime` (`auth/google_play.py:299`), which is when the subscription was first granted and does not move on renewal; on the Apple path it is the transaction's own `purchaseDate`, which does. Successive `core.access_grants` rows for one Play subscription therefore all carry the same `starts_at` and overlap completely in history. No read is affected — `_effective_grants_statement` only asks `starts_at <= evaluated_at`, and the `ends_at > starts_at` CHECK still holds — but the grant history is not comparable between the two stores.
**Fix:** either document that `starts_at` is the subscription's start and not the term's, or take the term start from the superseded grant's `ends_at` when one exists.

### IN-20: The `QueueFullError` / `CircuitOpenError` arm in `attempt` is unreachable, and its comment describes a guard it no longer is

**File:** `src/nativespeaker/api/resilience.py:181-185`
**Issue:** the arm reads:

```python
            try:
                result = await asyncio.wait_for(operation(), timeout=self._timeout_seconds)
            except (QueueFullError, CircuitOpenError):
                # First, and it must stay first: the breaker's own refusal is not the provider's failure.
                raise
```

The comment is a leftover from the shape before `aab00a7`, when `before_call()` was inside this
`try`. It now runs at `:176`, outside it, so the breaker's refusal can no longer arrive here. The
only remaining source is `operation()` itself, and the one `operation` is
`lambda: self.chain.ainvoke(...)` (`services/llm.py:44-45`) — a langchain chain that raises neither
class. The arm is dead and the comment now claims an ordering guarantee that protects nothing.
**Fix:** delete the arm, or keep it and replace the comment with what it actually is — a defensive
guard against a future `operation` that re-enters the gate.

### IN-21: `main.py` binds a module logger nothing uses

**File:** `src/nativespeaker/api/app/main.py:3,20`
**Issue:** `import structlog` and `logger = structlog.get_logger()` are module-level and `logger` is
referenced nowhere in the file. Ruff's `F` rules do not flag a module-level binding, so it survives
`ruff check src tests`. Every sibling module that binds `logger` uses it.
**Fix:** delete both lines.

### IN-30: every Pub/Sub body in the Google Play suite carries a `messageId` the model does not declare and pydantic silently drops

**File:** `tests/unit/test_google_play_notifications.py:280-283`, `:327`, `:342`

**Issue:** `_push()` builds `PubSubPushRequest(message={"messageId": "2280000000000001", "data": data})`,
but `PubSubPushMessage` (`src/nativespeaker/api/schemas/webhooks.py:18-22`) declares only `data`
and uses pydantic's default `extra="ignore"`, so `messageId` is discarded at validation. Three
call sites carry distinct-looking ids that reach nothing. This is misleading in exactly the place
it matters: OQ-4 deliberately rejected `message.messageId` as the replay key in favour of the
composite `google_play:{purchase_token}:{event_time_millis}:{event_type}`, and a reader of these
fixtures would reasonably infer the envelope's message id is still part of the contract.

**Fix:** drop the key from all three literals, or, if it is meant to document Pub/Sub's real wire
shape, say so in one comment on `_push` and keep it in one place rather than three.

### IN-31: two "control" cases in `test_monthly_period.py` compare literals in the same file and can never fail

**File:** `tests/unit/test_monthly_period.py:55-62` and `:64-67`

**Issue:** `test_no_spelling_of_the_derivation_hides_from_the_walk_control` asserts that three
hard-coded strings each contain one of the three hard-coded `SPELLINGS`; `test_the_neighbouring_timestamp_format_is_not_one_of_them_control`
asserts that a fourth hard-coded string contains none of them. Neither reads the source tree, so
neither can go red for any change to `src/`. They read as controls on the walk at `:44-49` but
control nothing about it — the walk's real control is `test_the_walk_reads_the_whole_package_control`
at `:51-53`, which does read the tree.

**Fix:** either delete both, or make them controls by writing the candidate spelling into a
`tmp_path` module and asserting `_files_formatting_a_period()` picks it up — the shape
`test_auth_package_shape.py:46-53` uses for the same purpose.

### IN-40: a tautological assertion on the fixture's own canned Play body

**File:** `tests/e2e/test_google_play_webhook.py:300`
**Issue:** `assert GOOGLE_PRODUCT_ID in json.dumps(real_google_play_seam.body)` reads
`ScriptedPlayApi.body`, which `tests/e2e/conftest.py:448` initialises to `play_subscription_body()`
and which this case never mutates. `play_subscription_body` (conftest.py:433-441) always writes
`{"productId": GOOGLE_PRODUCT_ID}` into `lineItems`. The expression is therefore
`GOOGLE_PRODUCT_ID in json.dumps(play_subscription_body())` — a statement about the test fixture that
holds regardless of anything the server did. The other two assertions in the case (lines 298-299) are
the ones that carry it.
**Failure scenario:** no server-side mutation can turn this assertion red; it survives the seam being
handed a different product map, the tier mapping being bypassed, or `_product_of` being deleted.
**Fix:** either delete the line, or turn it into a statement about the server by asserting the tier
the mapped product resolved to on the committed row, which is the property the case's title implies:

```python
subscriptions = await _subscriptions_of(_db_transaction, purchase_token)
assert subscriptions[0].tier_id == PAID_TIER_ID
```

### IN-41: a control whose docstring names a property it does not test

**File:** `tests/e2e/test_google_play_webhook.py:515-524`
**Issue:** `test_the_conflicting_delivery_left_the_first_owner_as_it_was` is documented as "The second
control: without a recorded owner the conflict above never fires." It asserts
`len(purchases) == 1` and `purchases[0].resolved_token_value == ATTRIBUTION_TOKEN`. Both hold whether
or not the conflict fires: `SubscriptionsService.ingest` writes `core.store_purchases` only when
`recorded is None` (`src/nativespeaker/api/services/subscriptions.py:129`) and never updates the row
afterwards, so a *accepted* second delivery leaves exactly the same purchase row an *refused* one does.
**Failure scenario:** the WR-40 mutation (guard replaced with `pass`) leaves this case green — the
second delivery then succeeds, writes a fresh subscription event and rewrites the buyer's grant, and
the assertions above still pass because they read only the purchase row.
**Fix:** make the control read the state the two outcomes actually differ in — the event row under the
second delivery's replay key, and the answer:

```python
assert conflicting.status_code == 500
assert await _events_of(_db_transaction,
                        _replay_key_at(PURCHASE_TOKEN, EVENT_TIME_MILLIS + 1000)) == []
```

(Once WR-40's case exists this control can simply be folded into it.)

### IN-50: A chart comment routes the reader to an HTTPRoute that was deleted

**File:** `k8s/templates/httproute-auth.yaml:14`
**Issue:** the comment reads "Under the JWT SecurityPolicy, as app-routes and llm-routes are."
`llm-routes` no longer exists: `918816e fix(37.4): WR-81 delete the duplicate llm-routes that
silently outranked app-routes` removed `k8s/templates/httproute-llm.yaml`, and `ls
k8s/templates/` confirms it is gone. `security-policy.yaml:9-15` targets exactly two routes,
`-app-routes` and `-auth-routes`. `NOTES.txt:23-24` already names the correct pair.
**Failure scenario:** an operator auditing which routes carry JWT validation reads this line,
looks for a third route under the policy, finds none, and cannot tell whether a route is
missing from the policy or the comment is stale — the exact question the chart exists to answer.
**Fix:** `# Under the JWT SecurityPolicy, as app-routes is.`

### IN-51: `httpx` carries two independent specifiers for one runtime dependency

**File:** `pyproject.toml:33` and `pyproject.toml:42`
**Issue:** `httpx >=0.28` is declared both in `[project].dependencies:33` and in
`[dependency-groups].dev:42`. `httpx` is a runtime dependency — `auth/google_play.py:11`,
`auth/devicecheck.py` and `app/lifespan.py:174` all construct `httpx.AsyncClient` on the request
path — so the dev entry adds nothing and misfiles it as a test tool.
**Failure scenario:** a future bump raises the dev floor alone (`httpx >=0.34` for a test-only
API). `uv` resolves the union, so tests keep passing locally, while `pyproject.toml:33` still
tells a reader — and any consumer resolving the runtime metadata without the dev group — that
0.28 is supported. The declared runtime contract and the tested one silently diverge.
**Fix:** delete line 42. The runtime declaration at line 33 already covers the test suite,
which `uv sync` installs alongside the dev group.

### IN-52: Two unused Apple root certificates ship in the production image

**File:** `config/certs/AppleRootCA-G2.cer`, `config/certs/AppleIncRootCertificate.cer` (with
`Dockerfile:29`)
**Issue:** `config.py:174` pins the one anchor this codebase uses, `certs/AppleRootCA-G3.cer`.
Grepping `src/` and `tests/` for `AppleRootCA-G2` and `AppleIncRoot` returns nothing — neither
file is read by any code path or any test. `Dockerfile:29` (`COPY config ./config/`) copies the
whole tree, so both land in every image beside the one that is real.
**Failure scenario:** `.env.example:120-121` tells the operator that
`APP_STORE_ROOT_CERTIFICATE_PATH` "outranks the derived value". An operator debugging App Store
verification sees three `.cer` files in the same directory and points that variable at
`AppleRootCA-G2.cer`. App Store Server Notifications v2 chains to G3, so
`build_app_store_verifier` fails and `POST /webhooks/app-store` answers 503
`verification_temporarily_unavailable` for the life of the deployment — behind the same
`app_store_configuration_absent` warning an unconfigured deployment emits, which points away
from the cause.
**Fix:** `git rm config/certs/AppleRootCA-G2.cer config/certs/AppleIncRootCertificate.cer`.

### IN-53: A `values.yaml` comment cites the wrong line of `config.py`

**File:** `k8s/values.yaml:67`
**Issue:** the comment reads "`DEVICECHECK_PRIVATE_KEY_PATH` is a path (`config.py:81`) and the
adapter reads it from disk". The field is `config.py:79`
(`private_key_path: str | None = Field(...)`); line 81 is blank and line 82 opens
`class AppStoreConfig`.
**Failure scenario:** a reader following the citation to justify why the chart mounts a file
rather than setting an environment variable lands inside a different config class and has to
re-derive the argument by hand.
**Fix:** cite `config.py:79`.

---

## Appendix: dropped candidates

Candidates each reviewer considered and dropped, with the ratified decision that
already settled the point or the evidence that disproved it.

### Partition A — auth adapters + webhook schema

- **`notification_uuid` is a payload-derived composite, not the Pub/Sub message ID (spec `:24`
  requires the message ID)** — dropped: ratified. `.planning/REQUIREMENTS.md:438` — *"FLAGGED
  CONFLICT — NEW (Phase 44, OQ-4, 2026-09-05). The replay key is a payload-derived composite, not
  the Pub/Sub message ID... decided by the user at plan 44-01's blocking checkpoint, rated
  one-way"*, and 44-01-SUMMARY OQ-4 and STATE.md § Decisions repeat it.
- **`PubSubPushMessage` no longer requires `messageId` although 44 D-04 says it must be present**
  — dropped: superseded by the same OQ-4 ratification; the previous review's IN-04 asked for
  exactly this relaxation.
- **An entitled Play state with no line-item expiry writes an unbounded grant** — dropped:
  `44-REVIEW.md:144` — *"Resolution (2026-09-06): accepted as an override, not fixed."* Also now
  moot at the service: `services/subscriptions.py:116-121` raises `InternalError` when
  `status in ENTITLED_STATUSES and term_ends_at is None`.
- **An Apple restore against a `grace_period` row always refuses because `verify_transaction` sets
  `grace_period_expires_at=None`** — disproven as new. I proved the mechanism runs
  (`term_end_for(grace_period, apple_proof)` returns `None`), then found it already pinned as
  intended behaviour by `tests/e2e/test_restore_subscription.py:359`
  `test_a_stored_grace_row_and_an_apple_proof_attaches_nothing`, whose docstring and CR-02/CR-25
  reference give the reason: a grant attached here would carry a NULL end. 45-CONTEXT § Deferred
  also records *"The renewal-info JWS as a second Apple proof field — would make grace and billing
  retry visible on restore. Not this phase."*
- **`_status_for` never yields `revoked`, so a Google refund marks the grant `expired`** —
  dropped: ratified. 44-CONTEXT **D-11** enumerates the Google map as seven-to-five and lists no
  `revoked` arm; `SUBSCRIPTION_STATE_PAUSED → expired` is named there too.
- **`_product_of` raising `InternalError` for `len(lineItems) != 1` poisons the Pub/Sub queue for
  a legitimate multi-line-item subscription** — dropped: the strict guard is the intended fix
  `cab0a44 fix(37.3): WR-05 refuse a line-item count that makes element zero a guess`, the same
  500-and-redeliver posture 44-CONTEXT **D-20** already ratifies for `UnmappedStoreProduct` and
  `AttributionConflict`, and I could not establish from `44-RESEARCH.md` or the API reference that
  Play ever returns two line items for this product shape. Not filed on an unproven premise.
- **`UnmappedStoreProduct` from `read_for_restore` answers a user-facing 500 rather than a 4xx** —
  dropped: 44-CONTEXT **D-20** ratifies *"500 for `AttributionConflict`, `UnmappedStoreProduct`, a
  lost race, or a failed Play call"*, and the classification comment at `google_play.py:307-308`
  is deliberate. The restore-route half belongs to the reviewer holding `services/restore.py`.
- **`ON_HOLD → billing_retry` with a past line-item expiry trips the service's term guard and
  500s forever** — disproven: `crud/subscriptions.py:32` is
  `ENTITLED_STATUSES = frozenset({active, grace_period})`, so `billing_retry` never reaches the
  `term_ends_at` check at `services/subscriptions.py:116`.
- **`term_end_for`'s `status is SubscriptionStatus.grace_period` identity test misfires on a raw
  string from the database** — disproven: `tables/purchases.py:59` types the column with
  `Enum(SubscriptionStatus, name='subscription_status', schema='core')`, so SQLAlchemy returns the
  member, and both value types coerce in `__post_init__` anyway.
- **`instant_from_millis` returning `None` erases the out-of-order watermark** — disproven:
  `crud/subscriptions.py:209-215` only ever advances it — *"Only ever advanced by a payload that
  carries one: an absent date clears nothing."*
- **`DECODE_OPTIONS` is a module-level mutable dict that `jwt.decode` mutates** — disproven
  against the installed PyJWT 2.12.1: `PyJWT.decode_complete` reads `options.get(...)` and calls
  `self._merge_options(options)`; it does not `setdefault` into the caller's dict.
- **`{"require": [...]}` replaces PyJWT's default option set, disabling `verify_exp` /
  `verify_aud` / `verify_iss`** — disproven by execution: expired, wrong-`aud`, wrong-`iss` and
  absent-`exp` tokens are all refused with these exact options.
- **Algorithm confusion / `alg: none` / HS256-over-the-public-key** — disproven:
  `algorithms=DECODE_ALGORITHMS` is `["RS256"]`, and PyJWT additionally refuses an asymmetric key
  as an HMAC secret at encode time.
- **A `kid` rotation stalls verification for the negative cache's 60 s TTL** — dropped:
  `PyJWKClient.get_signing_key` refreshes the set on a miss before raising (verified in the
  installed source), so a rotated-in key is found on its first use and never cached as unknown.
- **Distinct random `kid` values bypass the negative cache and each cost one outbound JWKS
  refresh** — dropped as speculative hardening for a pre-launch app: the behaviour is inherent to
  PyJWT's refresh-on-miss, and `AGENTS.md` places per-IP rate limiting at the gateway. Folded into
  WR-02, which is the part this codebase actually controls.
- **A purchase token or package name can escape its URL path segment** — disproven: `quote(...,
  safe="")` plus `_names_one_path_segment` covers it. I confirmed httpx really deletes `..` and
  `.` segments, and that `?`, `#`, `/` and `%` are all escaped.
- **A crafted `eventTimeMillis` freezes the subscription's watermark and blocks later RTDNs** —
  dropped: only a holder of a valid Google-signed token for the pinned `aud` and push service
  account can deliver a body at all, and the resulting grant is still bounded by its own
  `ends_at`, so a buyer gains nothing they had not already paid for.
- **`notification_key_for` can collide because colons are not escaped** — disproven: with
  `event_time_millis` an `int` and `event_type` a `str(int)`, no two distinct triples can produce
  the same string unless the purchase token itself contains colons, which Play tokens do not.
- **`SubscriptionNotification.purchaseToken` has no `min_length`** — disproven: an empty or
  dot-only token is caught by `_names_one_path_segment` at `google_play.py:257`, and a whitespace
  token is escaped to `%20` and answered 404 by Play.
- **`restore_proof` is unbounded and reaches the Play URL** — disproven:
  `schemas/auth.py:47` is `Field(..., min_length=1, max_length=8192)`.
- **An absent configured `package_name` answers 401 forever instead of the documented 503** —
  dropped from this partition: the live predicate is in `app/dependencies.py:220-224`, which a
  sibling reviewer owns. The mirror guard at `google_play.py:252-256` is unreachable on the
  webhook path and harmless.
- **The webhook routes carry no gateway rate-limit or JWT policy** — dropped: `k8s/` belongs to a
  sibling reviewer, and the shared brief forbids asking the app to re-implement what Envoy
  Gateway does.
- **DeviceCheck accepts a "bit state not found" body on any non-5xx status, which mints the free
  anonymous grant** — dropped: the comparison is exact after `strip().casefold()` against a
  two-element frozenset, the response comes from `https://api.devicecheck.apple.com` over TLS with
  no attacker-controlled content, and the 5xx exclusion is deliberate and commented. The
  `[ASSUMED]` literals are already labelled as such.
- **`read_private_key`'s bare `except Exception`** — dropped: deliberate and commented, and the
  degraded state is announced at boot by `devicecheck_credential_absent` in `lifespan.py:169-173`.
- **`read()` returning `None` for a 404 acknowledges and drops a notification that a Play-side
  propagation delay produced** — dropped: I could not establish that Play answers 404 transiently
  for a freshly purchased token, and the module's stated reasoning ("a token Google says is gone
  can never resolve, so a retry loops until retention") is sound on the evidence available. Not
  filed on speculation.
- **`if not package_name or not _names_one_path_segment(package_name)` — the first clause is
  dead** — dropped as a style-only nit; `"".strip(".")` is already falsy.

### Partition B — services / crud / tables

- **Ingestion never restores a grant after `SUBSCRIPTION_ON_HOLD` → `SUBSCRIPTION_RECOVERED`** (`crud/subscriptions.py:330-333`) — dropped: ratified. `specs/auth-refactor-phases/08-webhook-app-store.md:42` — "When state becomes entitled again, ingestion **never reactivates** the grant: reactivation belongs to user-invoked restore alone; the entitled-subscription/expired-grant state persists until restore." Restated by `09-webhook-google-play-rtdn.md:44` and 43 D-18, and built deliberately by 43-REVIEW CR-60's fix.
- **A newest-wins-superseded subscription's later notification leaves the buyer with no grant** — dropped: same spec sentence, 08:42 final clause.
- **`core.store_purchases` is never backfilled: a purchase first seen unattributed keeps its server-minted `identity_value` and NULL `resolved_token_value` for ever, which also defeats the attribution-conflict guard for that purchase** (`services/subscriptions.py:101-109, 132-144`) — dropped: recorded as an accepted residual in `43-VERIFICATION.md:221` item 1 ("Judged acceptable at this phase's scope — not a gap"), and the guard keyed on `resolved_token_value` rather than `identity_value` is 43 CR-03's ratified fix (`43-VERIFICATION.md:104, 168`).
- **An attribution conflict is a permanent poison message on the Google path** — dropped: already filed as 44-REVIEW WR-09 against this same file.
- **An entitled Play state with no `expiryTime` writes an unbounded grant** — dropped: 44-REVIEW CR-01, "**Resolution (2026-09-06): accepted as an override, not fixed.**"
- **A grace window already closed answers 500 and Pub/Sub redelivers** (`services/subscriptions.py:116-121`) — dropped: deliberate, CR-20, pinned by `tests/schema/test_subscription_ingestion.py:707` `test_a_grace_window_already_closed_is_refused_before_any_write`.
- **An Apple subscriber in grace can never restore** (`services/restore.py:62-67, 107-110`) — dropped: already filed as 45-REVIEW WR-01.
- **The three restore refusals log nothing** — dropped: already filed as 45-REVIEW WR-02.
- **The replay predicate (`held`) and the supersede predicate disagree on a move** (`crud/subscriptions.py:319-339`) — dropped: already filed as 45-REVIEW WR-03.
- **`restore_bound_user_id` is a dead column** (`tables/purchases.py:102`) — dropped: already filed as 45-REVIEW IN-07, and the migration comment `:141-143` declares it reserved.
- **`upsert_subscription`'s in-place arm overwrites `user_id` keyed on the id alone, losing a concurrent restore's move** — dropped: disproven. `owner = stored.user_id if stored.user_id is not None else user_id` (`:189`), so on the update-in-place arm `stored.user_id = owner` sets the attribute to its own loaded value; SQLAlchemy's `History.from_scalar_attribute` reports that as unchanged, so `user_id` is not emitted in the UPDATE at all. On the adoption arm the preceding `claim_subscription_owner` CAS holds the row lock for the rest of the transaction.
- **Restore mints a new grant row instead of reactivating the expired one, against `10-restore-subscription.md:77(b)`** — dropped: ratified as a FLAGGED CONFLICT accepted in 45-CONTEXT D-07 ("A successful restore calls `SubscriptionsDB.write_subscription_grant` as-is … **FLAGGED CONFLICT** against the brief's `ends_at IS NULL` adoption grant, its UPDATE reactivation of the same row").
- **A move hands the destination a fresh full monthly allowance while the old owner's count is stranded** (`crud/subscriptions.py:376-389`) — dropped: that is what 45-CONTEXT D-10's once-per-UTC-month transfer cap exists to bound.
- **A concurrent restore can move the row out from under `read_owner`'s guard, so the grant is written for a user whose grants were never locked** (`services/subscriptions.py:69-77, 155-167`) — dropped: disproven end to end. In every reachable variant either `has_prior_subscription_grant(subscription_id)` is true and `write_subscription_grant` writes nothing (`crud/subscriptions.py:331-333`), or the non-deferrable `ix_access_grants_one_active_per_user` refuses the insert as a `lost_race`, or the deferred `(active_subscription_grant_subscription_id, active_subscription_grant_user_id)` FK fails the commit. All three are fail-closed.
- **Naive/aware `datetime` comparison in `notification.signed_at < settled.store_signed_at` and `min(purchased_at, evaluated_at)`** — dropped: disproven. Play values are `AwareDatetime` (`auth/google_play.py:86, 93`) or built with `datetime.fromtimestamp(..., UTC)` (`:165`); Apple values go through `_instant`; `evaluated_at` is `datetime.now(UTC)` (`app/dependencies.py:118-120`).
- **`ends_at = evaluated_at` on a superseded grant can violate `CHECK (ends_at > starts_at)`** (`crud/subscriptions.py:352-353`) — dropped: reachable only if a grant's `starts_at` equals this request's `evaluated_at` to the microsecond; both writers clamp `starts_at` to their own captured instant, so it requires two requests sharing a microsecond. Not a plausible path.
- **`recorded_term[0]` can be `None` and turn an open-ended grant into `term_closed`** (`services/restore.py:101-107`) — dropped: no producer. Every subscription grant is written through `write_subscription_grant`, and both callers refuse an entitled status with no term first (`services/subscriptions.py:116-121`, `services/restore.py:108-110`).
- **`AttributionConflict` and the `read_owner` guard raise while FOR UPDATE locks are held, with no rollback** — dropped: disproven. `get_db` rolls back on the way out (`app/dependencies.py:45-51`), and nothing is written before either raise.
- **`SubscriptionStatus.revoked` is unreachable on the Google path, so a Play refund marks the grant `expired` rather than `revoked`** (`crud/subscriptions.py:344-345`) — dropped from this partition: the root cause is the state map in `auth/google_play.py:62-73`, which reviewer A owns. Filing it against the `ended = ...` line would be a symptom fix.
- **Two concurrent deliveries of the *same* `notification_uuid` both pass the `read_event` guard** (`services/subscriptions.py:46-52`) — dropped: disproven. `audit.subscription_events.notification_uuid` is `NOT NULL UNIQUE`; the loser's `append_event` flush returns `lost_race`, and `tests/schema/test_subscription_race.py:243-288` executes exactly this on the Google path.
- **`activate_registered_account_grant` locks usage rows only for effective grants while `lock_grants_of` locks them for every active grant, so a superseded row's usage could be unlocked** (`crud/grants.py:260-265`) — dropped: disproven. That writer supersedes `grants[0]` only, and refuses at `:286-287` if `marked_active` holds any row outside that set. Both writers take every grant-row lock before any usage lock, ascending by id, so no lock-order cycle exists.
- **`lock_grants_of` with an unsorted `accounts` list locks rows in caller order** (`services/restore.py:88-89`) — dropped: disproven. It is one statement with `ORDER BY id ASC ... FOR UPDATE`, so `LockRows` sits above the sort and one ascending order holds for both accounts.

### Partition C — app wiring / handlers / cross-cutting

- Provider-callback dependency order (verifier not element 0 / `get_db` taken first) — disproven:
  `routers/webhooks.py:23-25,38-40` declares each verifier as parameter 0, FastAPI solves
  `dependant.dependencies` in list order, and `tests/unit/test_app_wiring.py::TestTheProviderCallbackPartition`
  pins both properties (`test_the_verifier_is_the_routes_first_declared_dependency`,
  `test_the_verifier_resolves_before_any_session_is_taken`).
- An absent `google_play.package_name` answering 401 instead of the documented 503 — dropped:
  ratified by 41 WR-02 (`f013c56`, "read an empty configured Play package name as absent"), whose
  fix report explicitly kept `NotificationRejected` and whose unit case
  `test_an_unconfigured_package_refuses_every_delivery` pins it. Re-raised and re-decided since
  44-REVIEW WR-03.
- `build_google_push_verifier` catching only `PyJWTError`, so a non-JSON JWKS kills boot
  (44-REVIEW WR-07) — disproven: `JWTVerifier.__init__` (`auth/jwt_verifier.py:145-150`) now wraps
  every non-`PyJWTError` warm-up failure in `PyJWKClientError`, so the `except PyJWTError` at
  `lifespan.py:99` covers `json.JSONDecodeError`.
- Log forging through `path` / `operation` / `provider` in log values — disproven: `ConsoleRenderer`
  renders values with `repr`; a `\n` in `request.url.path` comes out as the two characters `\n`
  inside quotes. Measured.
- Secrets echoed by a boot-time pydantic ValidationError — disproven: measured with
  `DB_PASSWORD=pw-SECRET`, `OPENAI_API_KEY=sk-SUPERSECRET-VALUE`, `DB_PORT=notanint`; the message
  carries none of the three (`hide_input_in_errors=True` on `BaseConfig` plus `SecretStr`).
- `env_nested_max_split=1` breaking nested env binding for fields whose names contain underscores —
  disproven: measured that `APP_STORE_ROOT_CERTIFICATE_PATH`, `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL`,
  `DEVICECHECK_PRIVATE_KEY_PATH`, `RESILIENCE_CIRCUIT_BREAKER_FAILURE_THRESHOLD`,
  `JWT_LEEWAY_SECONDS` and `MODEL_MAX_TOKENS` all bind to the right leaf.
- `DatabaseConfig.url` mis-encoding a password — disproven: round-tripped `p@ss/w:o?r#d`, `a b+c`,
  `pass%20word` and `üñî` through `URL.create(...).render_as_string()` and `make_url`; all four
  parse back byte-identical.
- `exc_info=True` in the lifespan `finally` resolving to the wrong exception (the bug `414bedc`
  fixed in `app_error_handler`) — disproven: those calls sit inside their own `except Exception:`
  block, and the stdlib handler renders synchronously inside `logger.error(...)`, so
  `sys.exc_info()` is the exception just caught.
- Half-open circuit admitting unlimited concurrent probes (`resilience.py:55-59`) — dropped:
  bounded by `pool_size`, and the chosen semantics ("one failure reopens") are stated in the code
  and were ratified by 41 WR-01 (`99efd4f`).
- `QuotaExceededError` answering 429 with no `Retry-After` — disproven: both raise sites
  (`services/quota.py:60,93`) pass `retry_after_seconds`.
- Missing generic 403 in `class_answering_status`, so a framework 403 would 500 — dropped: no
  framework path produces one. `HTTPBearer` is constructed with `auto_error=False`
  (`dependencies.py:60`) and no `HTTPException` is raised anywhere in `src/`; the only statuses
  Starlette/FastAPI raise here are 400, 404 and 405, all of which have an answering class.
- `NotificationRejected` (401) carrying no `WWW-Authenticate` — dropped: already filed as
  44-REVIEW IN-03, conformance-only, and neither store reads the header.
- Unbounded HTTP request body on the two unauthenticated webhook routes (the `max_length` fields
  apply only after the body is fully buffered) — dropped: speculative hardening for a pre-launch app
  with no users, per the brief; the pod memory limit bounds the blast radius.
- No rate limit / shared threadpool exhaustion via the webhook routes — dropped: already filed as
  44-REVIEW WR-02, and the remedy is in `k8s/templates/`, another partition.
- `google.auth.transport.requests.Request()` refresh with the 120s default timeout
  (44-REVIEW WR-06, still unfixed at `auth/google_play.py:379-380`) — dropped: `auth/google_play.py`
  is another reviewer's partition.
- `get_examples` / `root` depending on `get_chat_service` and therefore on `get_db` — disproven as a
  cost: `AsyncSession` checks out no connection until a statement is issued, and neither handler
  issues one.
- `get_identity` returning ORM rows from a session it then closes — disproven: `expire_on_commit=False`
  plus a close without commit leaves the instances detached with their loaded columns intact, which
  is what the 357 e2e cases exercise.
- `LinkedIdentity` re-declaring `user`/`identity` under `frozen=True, slots=True` — disproven: the
  redeclaration replaces the parent's defaults without reordering fields, `ty` reports 0 diagnostics,
  and the type is constructed keyword-only at `dependencies.py:104-105`.
- Missing `Cache-Control: no-store` on `GET /chats`, `GET /chats/{id}`, `GET /examples`, `GET /` and
  `POST /auth/sync` — dropped: no validator and no freshness header means a heuristic cache must
  revalidate and has nothing to revalidate with; the routes are all `Authorization`-bearing, so no
  shared cache stores them. Speculative for this app.
- `mapping`-vs-env precedence letting `config/config.yaml` shadow an operator's env var — dropped:
  ratified and documented in `config/config.yaml:14-17` and `.env.example:2-6`; `deep_update` still
  lets env add leaves the YAML omits, which is the stated design.
- Dead schema classes in `schemas/llm.py` — disproven: `Issue`, `AnalyzeInput`, `FollowUpInput`,
  `AnalyzeResponse` and `FollowUpResponse` are all constructed in `services/chats.py:70-73,95,130`.
- `notification_uuid` overflowing its column or reaching a log — disproven: the column is
  `TEXT NOT NULL UNIQUE` (`migrations/20260818_01_initial-release.sql:208`) and no `logger` call in
  `src/` references it.
- Pool exhaustion / idle-in-transaction across the LLM call (`db.pool_size` 12 vs
  `resilience.pool_size + queue_size` 30) — dropped: out of scope for v1 (capacity), and the
  relation is ratified as comment-only by Phase 41 D-16 (`config/config.yaml:5-8`).

### Partition D — unit suite

- **The replay key is the payload-derived composite, not the Pub/Sub `messageId` the spec mandates**
  (`google_play.py::notification_key_for`, pinned by `test_google_play_notifications.py:398`, `:458`)
  — dropped: ratified as **OQ-4**, `44-01-SUMMARY.md:179` ("the Google replay key is the
  payload-derived composite `google_play:{purchaseToken}:{eventTimeMillis}:{notificationType}`,
  chosen by the user at the plan's checkpoint"), and recorded as a *counted flagged conflict*
  against `09-webhook-google-play-rtdn.md:24,:41` in `44-07-SUMMARY.md:179`. Not re-filed.
- **`test_an_unconfigured_package_refuses_every_delivery` (`test_google_play_notifications.py:440-442`)
  pins a 401 where `.env.example:149-151` promises a 503** — dropped: this is the already-open
  `44-REVIEW.md` **WR-03** ("An absent `package_name` refuses every delivery forever"), whose fix
  text explicitly says "Update the unit case at line 332 to expect `Unavailable`".
  `44-VERIFICATION.md:208` records it as "unchanged and remain open, not blocking". The boot half
  *was* since fixed (`lifespan.py:194-195` now tests `not config.google_play.package_name`); the
  dependency half and this test were not. Not re-filed as a new finding.
- **`test_auth_package_shape.py` is a pure churn tripwire** (`CURRENT = (8, 24, 68)`, `:19`, `:40`)
  — dropped: ratified design, `37.2-06-SUMMARY.md:13` ("the package size as a checked fact") and
  `:94` ("`CURRENT` … are literals, so growth is a deliberate edit a reviewer sees"). Every later
  plan updates the number on purpose.
- **`test_app_wiring.py` pins both callback routes as always registered, where the spec says the
  route "is not registered at all while the Google integration is unconfigured"** — dropped:
  recorded as a counted flagged conflict inherited from phase 43, `44-07-SUMMARY.md:178`
  ("the always-registered router answering 503 … counted again").
- **The RTDN route answers `NotificationRejected` with the shared one-field error body, where the
  spec says "plain HTTP status codes only"; pinned at `test_google_play_notifications.py:754-764`**
  — dropped: same counted flagged conflict, `44-07-SUMMARY.md:178` ("the shared one-field body").
- **CR-01 of the previous review (entitled Play state with no line-item expiry writes an unbounded
  grant)** — dropped twice over: accepted as an override per the brief, *and* disproven as still
  live — `services/subscriptions.py:116-121` now refuses `status in ENTITLED_STATUSES` with
  `term_ends_at is None`, and `test_subscription_attribution.py:887-1011` drives all four arms of
  that guard with two controls. My probe removing the `term_ends_at <= self.evaluated_at` clause
  failed a case (1 failed / 174 passed).
- **`TestThePushTokenCheck` (`:858-879`) has no expiry case, though the spec names expiry among the
  four things the Pub/Sub verifier must check** — dropped: disproven as a gap.
  `build_google_push_verifier` (`lifespan.py:93-98`) builds an ordinary `JWTVerifier`, whose `exp`
  handling is pinned by `test_jwt_security.py:312-334` (leeway both sides, `require` list, and the
  future-`iat` case), so no mutation that withdrew the expiry check could survive.
- **`_RecordingSubscriptions.upsert_subscription` is a stand-in that could drift from the writer**
  — dropped: disproven. `test_subscription_attribution.py:187-198` runs the *real*
  `SubscriptionsDB.upsert_subscription` over a one-row session, and `TestTheRecorderAnswersWithTheRealWriter`
  (`:707-737`) is the control on that. Probes on the writer's clock rule and its conditional owner
  claim (`rowcount == 1` → `>= 0`) both failed cases.
- **`insert_purchase`'s `resolved_token_value` / `purchase_user_id` are unpinned at unit level**
  — dropped: disproven at tree level. Both mutants (`=None`) survive the unit subset but fail e2e
  (`test_google_play_webhook.py:519-524` reads `purchases[0].resolved_token_value` back out of the
  database; the `purchase_user_id` probe failed 1 e2e case).
- **The Apple adapter's `_crossed()` field mapping might be unpinned like the Google one**
  — dropped: disproven. All seven probes (`signed_at`, `purchased_at`, `transaction_id`,
  `attribution_token`, `external_id`, `grace_period_expires_at`, `event_type`) each failed at least
  one case in `test_app_store_notifications.py`.
- **`test_rejection_vocabulary.py::EVENT_NAMES` might be derived from the tree it measures**
  — dropped: disproven, it is a 60-entry literal at `:67-145` compared against
  `camel_to_snake(cls.__name__)` for the live family.
- **`test_tables_metadata.py` / `test_monthly_period.py` source-scanning cases might be vacuous**
  — dropped: each carries a real control that reads the tree
  (`test_tables_metadata.py:113-119`, `test_monthly_period.py:51-53`).
- **`PubSubPushMessage.data` carries no `max_length`, so an oversized body is parsed before
  `developer_notification_from` bounds it** — dropped: out of partition (source, not tests), and
  the request-size bound is the gateway's per `AGENTS.md`; the model's own comment at
  `schemas/webhooks.py:20-22` states the deliberate reason (a pydantic 422 is a body Pub/Sub
  retries forever).

### Partition E — e2e + schema suites

- `real_google_play_seam` and `unconfigured_google_play` (`tests/e2e/conftest.py:485-490, 586-589`) build an `httpx.AsyncClient` that is never `aclose()`d — dropped: the transport is `httpx.MockTransport`, which owns no socket, file handle or thread, so nothing leaks; the brief forbids style-only nits for a pre-launch app.
- `_PUSH_REASONS` (`tests/e2e/test_google_play_webhook.py:206-208`) excludes `missing_token` and `duplicate_authorization`, possibly leaving two reachable arms untested — dropped: `JWTVerifier.verify` (`src/nativespeaker/api/auth/jwt_verifier.py:184-215`) can only return `bounded_reason_for(...)` or `claims_from_payload`'s two reasons, and neither of those two members is producible by either; the comment at lines 202-205 is accurate.
- `refusal_sites.py:36-39` matches only `NotificationRejected(...)` *calls*, so a bare `raise NotificationRejected` would escape both route controls — dropped: `ProviderLookupError.__init__` (`src/nativespeaker/api/errors.py:421`) declares `stage` keyword-only with no default, so a bare raise is a `TypeError` at construction and cannot exist in working code.
- `assert UUID(purchases[0].identity_value)` (`tests/e2e/test_app_store_webhook.py:470`) is a truthiness check on an always-truthy object — dropped: `UUID()` raises `ValueError` on a non-UUID string, so the parse *is* the assertion and it does fail on the mutation it targets (a server-minted placeholder that is not a UUID).
- `test_the_same_term_writes_nothing_to_either_table` (`tests/schema/test_subscription_ingestion.py:371-383`) survives mutating the out-of-order guard `signed_at < settled.store_signed_at` to `<=` — dropped: the `notification_uuid` replay guard sits ahead of it, so `<=` changes behaviour only for two *distinct* notifications carrying a byte-identical store clock, which neither store emits; `tests/unit/test_subscription_store_clock.py` owns that boundary.
- `test_every_column_spec_matches_capture` / `test_every_index_key_matches_capture` / `test_every_delete_action_matches_capture` (`tests/schema/test_inventory.py:474-513`) iterate only over `actual`, so a *dropped* column, index or FK is invisible — dropped: each is paired with a `test_..._set_is_exact` case using `assert_exact_set`, which reports the `expected - actual` half by name.
- `SET search_path TO ...` (not `SET LOCAL`) at `tests/schema/test_inventory.py:451, 477` and `test_grant_locks.py` leaks to later cases — dropped: PostgreSQL makes plain `SET` transactional, `conftest.conn` always rolls back (conftest.py:126-132), and every test gets a brand-new connection anyway.
- The schema "race" tests are actually serialised, so no race is exercised — dropped: `test_claim_race.py:314-319`, `test_create_race.py:217-220` and `test_restore_race.py:294-300` each pair two `asyncio.Event`s at a hook installed inside the writer (first flush / first `Update` / first commit) on two separate engine connections, and each class asserts its barrier premise (`grants_seen_at_barrier == [0, 0]`, `identities_seen_at_barrier == [0, 0]`, `owner_seen_at_barrier == [None, None]`) before reading any outcome.
- The lock-tier counts in `test_grant_locks.py:981-989` are inflated because `_RELATIONS` also matches relations named after a comma in the SELECT column list — dropped: compiled both production statements (`_effective_grants_statement(...).with_for_update()` and `_usage_statement(...).with_for_update()`); each names exactly one relation across its whole text, so `len(set(taken)) == 2` really does count two tiers.
- Constraint names or SQLSTATEs asserted in `tests/schema/test_constraints.py` do not match the DDL — dropped: checked every one against `migrations/20260818_01_initial-release.sql` — `store_purchases`' `CHECK (resolved_token_value IS NULL OR resolved_token_value = identity_value)` and its two FKs (:189-194), `auth_challenges`' lifecycle and binding CHECKs (:309-319), `access_grants`' source/subscription_id CHECK (:236-240) and the two deferred generated-column FKs, `user_monthly_usage_pkey`, `external_identities_issuer_subject_key`. All names and driver exception classes line up.
- `test_a_created_account_satisfies_both_halves` (`tests/schema/test_registration_pairing.py:122-142`) asserts two counts that are zero on either arm regardless — dropped: on the anonymous arm scan 1 turns non-zero the moment `AuthService.complete` sets `registered_at`, and on the google arm scan 2 turns non-zero the moment it does not; the two `TestTheScansSeeTheThirdState` controls demonstrate each scan counting a deliberately offending row.
- No e2e coverage for `google_play_message_without_data`, `google_play_message_out_of_range`, or a 404/410 gone purchase token on the RTDN path (all reachable arms of `developer_notification_from` and `_play_answer_is_usable`) — dropped: `tests/unit/test_google_play_notifications.py` carries 65 cases across those arms, the gone-token path is exercised end to end through the real class on the restore route (`tests/e2e/test_restore_subscription.py:812-826`), and the brief forbids "add more tests for the sake of it".
- `TestAnOpenCircuitStillAnswers503` (`tests/e2e/test_quota.py:423-435`) mutates module-scoped `llm_service.policy._circuit_breaker` privates — dropped: both fields are reset in a `finally`, and the autouse `_db_transaction` rollback makes case order irrelevant to everything else.
- `EVENT_TIME_MILLIS = 1789000000000` (`tests/e2e/test_google_play_webhook.py:60`) is a fixed instant that has now drifted into the past — dropped: nothing on the ingestion path compares `signed_at` to `evaluated_at`; the entitlement decision reads `expiryTime`, which `play_subscription_body()` places 30 days ahead of a live clock, and the out-of-order guard compares the RTDN clock only against a stored one.
- `test_no_record_of_any_outcome_carries_the_subject_or_the_provider_uid` (`tests/e2e/test_sign_out_all.py:323`) would blow up if `identity.provider_uid` were `None` — dropped: `None in str` raises `TypeError`, which is a loud red test, never a silent pass.
- `files_raising_the_refusal()` attributes an App Store refusal raised inside `app/dependencies.py` to the Google control, because `GOOGLE_PLAY_REFUSAL_FILES` claims that whole file — dropped: the outcome is a failing test with a confusing message, never a false pass, and `tests/e2e/refusal_sites.py:12-13` states the trade-off deliberately.
- `test_the_walk_sees_the_records_the_deliveries_produced` spies only three loggers and would miss a secret written by the access-log middleware or `jwt_verifier` — dropped: neither is handed the bearer, the envelope or the purchase token; filing it would be speculative hardening.
- `_ingestion_run` (`tests/schema/test_grant_locks.py:900-947`) drives the lock-order proof with `PurchaseProvider.apple` while the class is cited for the store callback generally — dropped: `SubscriptionsService.ingest` is provider-agnostic (the provider reaches only `read_*` predicates and a log label), so the Google path issues the identical statement sequence.

### Partition F — deployment / config / packaging / migration

- `APP_STORE_*` and `GOOGLE_PLAY_*` environment variables never reach their nested fields, because `BaseConfig` sets `env_nested_max_split=1` and those names split at the first underscore — **disproven**: ran `EnvironmentConfig()` with all six set; `google_play.push_service_account_email`, `app_store.bundle_id`, `app_store.app_apple_id` and `app_store.environment` all populated correctly.
- The levers `config/config.yaml:1-4` promises (`MODEL_NAME`, `RESILIENCE_POOL_SIZE` "and their siblings") do not exist, now that the block was deleted from the tracked file — **disproven**: ran with `MODEL_NAME`, `RESILIENCE_POOL_SIZE`, `RESILIENCE_CIRCUIT_BREAKER_RESET_SECONDS` and `LOG_LEVEL` set; every one took effect, and `db.pool_size` correctly stayed at the file's 12.
- `httproute-health.yaml:16-18` matches `PathPrefix /health` where the enforced allowlist is exactly `/health/ready` (`tests/unit/test_app_wiring.py:18,92-98`), so a `/health/*` route added later becomes public with no chart edit — **dropped**: already filed verbatim, with the identical `type: Exact / value: /health/ready` fix, as `42-REVIEW.md` IN-07, which concluded "nothing the gateway does today weakens an enforced control".
- `jwt.issuer` (`k8s/values.yaml:86`) and the Secret's `JWT_PROJECT_ID` are the same fact in two operator-supplied places, and a mismatch 401s every authenticated request while the `NOTES.txt:20` post-install check still passes — **dropped**: already filed as `39-REVIEW.md` IN-64, with the `jwt.projectId` + `printf` fix.
- `security-policy.yaml:28` `optional: true` covers only the absent token, so an *expired* Firebase ID token — the commonest real 401 — is refused at the gateway with Envoy's plain-text body, breaking the shared `{"code": ...}` contract — **dropped**: settled by `37.5-REVIEW-FIX.md:846`, "Envoy Gateway exposes no `allow_missing_or_failed`", and documented at `security-policy.yaml:25-26` and `NOTES.txt:9-10`.
- The Play `purchaseToken` is stored verbatim and unhashed, forever, in the append-only `audit.subscription_events.notification_uuid` (`migrations/20260818_01_initial-release.sql:208`, written from `auth/google_play.py:176`) — **dropped**: ratified by `44-01-SUMMARY.md:179` OQ-4, "the Google replay key is the payload-derived composite … chosen by the user at the plan's checkpoint … the components are not hashed".
- `Dockerfile:17` `uv sync` may resolve a *managed* CPython, leaving `/app/.venv/bin/python` a symlink into a path stage 2 does not copy, so every container fails to exec — **disproven**: uv's default `python-preference = managed` still prefers an already-installed system Python over downloading one, and `python:3.14-slim` supplies `/usr/local/bin/python3.14`, which both stages share.
- `k8s/values.yaml:36,40` point liveness and readiness at the same path, so a database outage would restart every pod — **disproven**: `src/nativespeaker/api/routers/health.py:7-11` returns a static `{"status": "up"}` with no dependency check (the same conclusion `39-REVIEW.md:361` reached).
- `uv.lock` has drifted from `pyproject.toml` after the ruff/ty and cryptography edits — **disproven**: `uv lock --check` reports "Resolved 111 packages" with no drift.
- HMAC key material is committed in the tracked `config/config.yaml` — **disproven for the submitted tree**: `8c8a3b0` removed it, and `grep -riE "hmac|hash_key|subject_hash|secret_key" src/` returns nothing, so no code path reads any such key; what remains in history is dead material, not a live credential.
- `readOnlyRootFilesystem: true` (`deployment.yaml:38`) leaves Python and the provider libraries nowhere to write — **disproven**: failed bytecode writes into `/app/.venv` are non-fatal in CPython, `/tmp` is an `emptyDir` (`deployment.yaml:100-104`), firebase-admin's `cachecontrol` uses an in-memory cache, and `google.auth.default()` only reads the ADC path.
- `.gitignore:14` `.env.*` swallows `.env.example`, so the one file a developer needs is untracked — **disproven**: `git check-ignore -v .env.example` matches no pattern; the `!.env.example` negation at line 15 wins, and `git ls-files` shows it tracked.
- The migration comments rewritten in this diff (`:136-139`, `:141-143`) no longer match the code — **disproven**: `crud/subscriptions.py:245` writes `last_cross_account_transfer_month` and `:61` carries it in the CAS predicate, and no path in `src/` writes `restore_bound_user_id`, exactly as the comments now claim.
- `config/config.yaml:20,24` could name a tier absent from `core.access_tiers`, turning the FK violation into a permanently redelivered Pub/Sub message — **dropped**: both entries map to `paid`, which the migration seeds at `:126`; guarding an operator typo here is speculative hardening, not a defect in the submitted code.
- `AGENTS.md:29-41` claims "Every file has exactly one home" but gives none to `src/nativespeaker/api/database/` or `models/` — **disproven**: both directories are empty and untracked; `git ls-files` lists no file under either.
- The chart ships no migration Job and `.dockerignore:22` excludes `migrations/` from the image, so a fresh install has no schema — **dropped**: `pogo-migrate` is a dev-group tool run by the operator against `DATABASE_URL` (`pyproject.toml:45,80-87`, `.env.example:16-20`); this is the declared design, not a defect in the submitted files.
- No `startupProbe`, so `deployment.yaml:61-66` kills a boot slower than ~100 s forever — **dropped**: speculative hardening for a pre-launch single-replica deployment whose lifespan network work is bounded and whose failure is loud.
- `pyproject.toml:66` puts a marker filter in `addopts`, so a user-supplied `-m timing` silently replaces it and pulls in e2e and schema cases — **dropped**: test-tooling nit with no product effect.

---

_Reviewed: 2026-09-10_  
_Reviewer: Claude (gsd-code-reviewer x6, partitioned)_  
_Depth: standard_
