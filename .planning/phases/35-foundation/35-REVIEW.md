---
phase: 35-foundation
reviewed: 2026-09-08T00:00:00Z
depth: standard
files_reviewed: 149
files_reviewed_list:
  - AGENTS.md
  - config/config.yaml
  - docker-compose.yml
  - .env.example
  - .gitignore
  - k8s/templates/httproute-webhooks.yaml
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
  - src/nativespeaker/api/auth/__init__.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/challenges.py
  - src/nativespeaker/api/crud/chats.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/__init__.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/__init__.py
  - src/nativespeaker/api/logs.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/__init__.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/routers/webhooks.py
  - src/nativespeaker/api/schemas/api.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/schemas/__init__.py
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
  - src/nativespeaker/api/tables/users.py
  - src/nativespeaker/__init__.py
  - tests/conftest.py
  - tests/e2e/conftest.py
  - tests/e2e/test_admission.py
  - tests/e2e/test_app_store_webhook.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_chat_queries.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/e2e/test_create_user.py
  - tests/e2e/test_error_cases.py
  - tests/e2e/test_examples.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_google_play_webhook.py
  - tests/e2e/test_isolation.py
  - tests/e2e/test_llm_schema.py
  - tests/e2e/test_model_queries.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/e2e/test_root.py
  - tests/e2e/test_sign_out_all.py
  - tests/e2e/test_sync.py
  - tests/e2e/test_unauthenticated_access.py
  - tests/e2e/test_upgrade_anonymous.py
  - tests/e2e/test_users_me.py
  - tests/schema/conftest.py
  - tests/schema/helpers.py
  - tests/schema/test_apply_rollback.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_constraints.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_inventory.py
  - tests/schema/test_registration_pairing.py
  - tests/schema/test_restore_race.py
  - tests/schema/test_store_purchase_tokens.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/schema/test_sync_lock_freedom.py
  - tests/unit/conftest.py
  - tests/unit/error_tree.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_challenge_ids.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_config.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_docstring_bar.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_identities_crud.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_jwks_offload.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_llm_chain_schema.py
  - tests/unit/test_logging.py
  - tests/unit/test_models.py
  - tests/unit/test_purchases_crud.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_services.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_sync_audit_removal.py
  - tests/unit/test_sync_clock_capture.py
  - tests/unit/test_sync_error_reuse.py
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users_me.py
  - tests/unit/test_users.py
  - uv.lock
findings:
  critical: 1
  warning: 8
  info: 7
  total: 16
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-09-08
**Depth:** standard
**Files Reviewed:** 149
**Status:** issues_found

## Summary

Incremental re-review of every non-planning file changed since `4f40fce`. The authentication,
entitlement and store-ingestion core is in good shape: the challenge lifecycle serializes on a
single conditional `UPDATE`, the grant writers take both lock tiers in one declared order and treat
the partial unique indexes as the arbiter, the restore owner change is a compare-and-swap on the
pre-transaction read, and the quota charge locks the grant then the usage row in its own session.
`ruff check .` is clean and `1283` unit tests pass.

The defects below are concentrated in three places: one ordering problem between an irreversible
Apple side effect and the local commit, several places where the schema and configuration comments
now state the opposite of what the code does, and one dev-environment regression introduced by this
change set.

Cross-file checks performed: `identity.user is not None` implies `identity.identity is not None`
(`crud/identities.py:44-53`), so every `identity.identity.<x>` access behind `get_linked_identity`
is safe. The restore transfer cap has no bypass: the month is carried into the CAS predicate.
`violation.orig.sqlstate` resolves correctly under `asyncpg` (SQLAlchemy 2.0.46 copies `sqlstate`
onto the translated DBAPI error).

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: The DeviceCheck bit is written to Apple before the local transaction commits

**File:** `src/nativespeaker/api/services/auth.py:194` and `src/nativespeaker/api/services/auth.py:239`
**Issue:**
`write_bits_with_retry` sets the device's grant bit at Apple, and only afterwards does the code
flush the grant (`activate_anonymous_device_grant`), settle the outcome, and return to `_complete`,
which commits at `services/auth.py:356`. Several database round trips sit inside that window.

Any failure in the window — a pod eviction, a Postgres failover, a dropped connection, or the
`ClaimRefusedUnderLock` raised by `_settle` at `services/auth.py:258` — leaves Apple's bit
permanently set while nothing is written locally. On the client's retry, `read_bits_with_retry`
reports `bit0` (or `bit1`) already set and `_claim_anonymous_grant` raises `DeviceGrantExhausted`
(403) forever.

There is no compensating path anywhere in the repository: no route, task, or admin surface calls
`write_bits` to clear a bit, so the device's one free-grant slot is unrecoverable. The failure needs
no attacker and no race — an ordinary Kubernetes pod restart is enough.

**Fix:** Move the irreversible external write after the local commit, and accept the inverse risk.
Per `AGENTS.md` the theft threat model is explicitly not worth over-engineering for, so failing open
(a crashed request leaves the device able to claim again) is the cheaper failure than permanently
burning a paying-adjacent user's free trial.

```python
# services/auth.py -- _claim_anonymous_grant
state = await read_bits_with_retry(self.devicecheck, device_token)
if state.bit0:
    raise DeviceGrantExhausted(stage="devicecheck_read", cause="already_set")

outcome = await self.grants_db.activate_anonymous_device_grant(
    user_id=identity.user.id,
    identity_row=identity.identity,
    tier_id=ANONYMOUS_TIER_ID,
    evaluated_at=self.evaluated_at)
await self._settle(identity, outcome)
await self.session.commit()          # the grant is durable before Apple is told

# Fail-open on purpose: a crash here costs one device slot, never a user's granted trial.
await write_bits_with_retry(self.devicecheck, device_token, bit0=True, bit1=state.bit1)
```

If failing open is unacceptable, the alternative is a durable intent row written in the same
transaction as the grant plus a reconciliation pass — but that is materially more machinery than
this product's threat model justifies.

## Warnings

### WR-01: `Chat.messages` has no ordering, so the LLM sees the conversation in unspecified order

**File:** `src/nativespeaker/api/tables/chats.py:44`, consumed at `src/nativespeaker/api/services/chats.py:50-54`
**Issue:** `messages: list[Message] = Relationship(cascade_delete=True, passive_deletes=True)` declares
no `order_by`, and `ChatsDB.get_chat` (`crud/chats.py:19-24`) loads it with a bare
`selectinload(Chat.messages)` whose SELECT carries no `ORDER BY`. PostgreSQL gives no ordering
guarantee for such a query; the observed order is physical row order, which changes after `VACUUM`,
page splits, or a plan change to a bitmap scan. `ask_llm` builds `history` by iterating that list, so
a multi-turn follow-up can present the model with the turns shuffled. No test asserts message order.

**Fix:**

```python
# tables/chats.py
messages: list["Message"] = Relationship(
    cascade_delete=True,
    passive_deletes=True,
    sa_relationship_kwargs={"order_by": "Message.id"},   # uuid7: id is time-ordered
)
```

### WR-02: `GET /chats/{chat_id}` documents chronological order and returns reverse-chronological

**File:** `src/nativespeaker/api/crud/chats.py:45`, documented at `src/nativespeaker/api/routers/chats.py:32`
**Issue:** The route description reads "Returns all messages in a chat session, ordered
chronologically." The query is `.order_by(col(Message.id).desc())`. `Message.id` is `uuid7`
(`tables/chats.py:26`), so descending id is newest-first — the opposite of the documented contract.
A client that renders the array top-to-bottom shows the conversation backwards.

**Fix:** Pick one and make the other match.

```python
# crud/chats.py -- get_messages
.order_by(col(Message.id).asc())
```

### WR-03: `core.auth_challenges` is never swept — unbounded growth and indefinite plaintext subject retention

**File:** `migrations/20260818_01_initial-release.sql:317`, `src/nativespeaker/api/crud/challenges.py:26-105`
**Issue:** `ChallengesDB` has four operations — `issue`, `locate`, `claim`, `consume` — and none
deletes. No other module, migration, or Kubernetes manifest deletes from the table either
(`grep -rn` over `src`, `migrations`, `k8s` for a challenge delete returns nothing). Two consequences:

1. Every `POST /auth/challenge` inserts a row that is never removed. Envoy rate-limits per user, but
   the table still grows monotonically for the life of the deployment.
2. `preauth_subject` — the verified external subject in plaintext, per the column comment at
   `migrations:296` — is cleared only by `consume` (`crud/challenges.py:86`). A challenge that is
   issued and abandoned, which is the normal outcome of any interrupted sign-up, retains that
   subject forever.

`CREATE INDEX ix_auth_challenges_expires_at` at `migrations:317` has no reader: `locate` keys on
`challenge_id`, and `claim`'s `expires_at > now` predicate is satisfied by the unique index on
`challenge_id`. The index exists for a sweep that was never written.

**Fix:** Add a delete keyed on the existing index and call it on a schedule (a `CronJob`, or a
best-effort call from the issue path).

```python
async def sweep_expired(self, session: AsyncSession, *, now: datetime) -> int:
    """Delete challenges past expiry. Consumed rows already cleared their subject; these never will."""
    result = await session.exec(
        delete(AuthChallenge).where(col(AuthChallenge.expires_at) <= now))
    return result.rowcount
```

### WR-04: `docker-compose.yml` no longer supplies the keys the `postgres:17` image needs

**File:** `docker-compose.yml:3-5`
**Issue:** This change set replaced the explicit environment block with `env_file: [.env]`:

```
-    environment:
-      POSTGRES_USER: {DB_USER}
-      POSTGRES_PASSWORD: {DB_PASSWORD}
-      POSTGRES_DB: {DB_NAME}
+    env_file:
+      - .env
```

`.env.example` — also changed in this scope — declares only `DB_HOST/PORT/USER/PASSWORD/NAME`. The
`postgres:17` entrypoint reads `POSTGRES_PASSWORD` and `POSTGRES_DB` and ignores the `DB_*` prefix
entirely. A developer following `README.md:43` (`cp .env.example .env`) then starting the compose
service gets `Database is uninitialized and superuser password is not specified`; if a password is
later added but `POSTGRES_DB` is not, the container provisions `postgres` while `AppConfig.db.name`
and `[tool.pogo] database_config` both point at `nativespeaker`, so every migration fails.

**Fix:** Document the container-prefix keys alongside the application ones in `.env.example`, since
the compose file now forwards the whole file verbatim.

```
# App
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=nativespeaker

# The same three values under the prefix the postgres:17 image reads. docker-compose.yml
# forwards this whole file to the container, which ignores DB_*.
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=nativespeaker
```

### WR-05: `log_level: FATAL` passes validation and then crashes the pod at boot

**File:** `src/nativespeaker/api/config.py:9`, consumed at `src/nativespeaker/api/logs.py:31`
**Issue:** `LogLevel = StrEnum("LogLevel", {k: k for k in logging.getLevelNamesMapping()})` admits
`CRITICAL, FATAL, ERROR, WARN, WARNING, INFO, DEBUG, NOTSET`. `setup_logging` forwards that string to
`structlog.make_filtering_bound_logger(log_level.upper())`, whose `NAME_TO_LEVEL` map holds
`critical, debug, error, exception, info, notset, warn, warning` — no `fatal`. Verified:

```
>>> structlog.make_filtering_bound_logger('FATAL')
KeyError: 'fatal'
```

`setup_logging` runs at `app/lifespan.py:97`, before any exception handler exists, so a config value
the schema accepts crashloops the pod with a bare `KeyError`.

**Fix:** Restrict the enum to the levels both libraries share.

```python
_SUPPORTED_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
LogLevel = StrEnum("LogLevel", {name: name for name in _SUPPORTED_LEVELS})
```

### WR-06: The migration says `last_cross_account_transfer_month` is written by nothing; the restore path writes it

**File:** `migrations/20260818_01_initial-release.sql:136-137`
**Issue:** The column comment reads "Written by nothing: cross-account restore transfer is never
performed, so this stays NULL." Both halves are false as of this change set.
`RestoreService.restore` performs cross-account transfer (`services/restore.py:100-116`) and
`SubscriptionsDB.claim_subscription_owner` writes the column (`crud/subscriptions.py:166-168`); the
value is the sole input to the D-10 cap that raises `RestoreTransferRejected`
(`services/restore.py:81-83`). A maintainer trusting the comment would read the column as dead and
could drop it in a follow-up migration, silently removing the one-move-per-month limit on
subscription sharing.

**Fix:**

```sql
    -- Set by RestoreService when a restore moves this subscription between accounts (D-10);
    -- claim_subscription_owner carries it in the CAS predicate, and the cap reads it.
    last_cross_account_transfer_month DATE,
```

### WR-07: `restore_bound_user_id` documents a lifetime binding that no code ever writes

**File:** `migrations/20260818_01_initial-release.sql:138-139`, mapped at `src/nativespeaker/api/tables/purchases.py:61`
**Issue:** The comment reads "Lifetime restore binding: NULL until the first successful restore, then
never changed." Nothing writes it. `grep -rn restore_bound_user_id src` returns only the SQLModel
field declaration; the e2e suite asserts the opposite of the comment at
`tests/e2e/test_restore_subscription.py:867`, `:911`, `:937`, `:958`, `:974` — every one of them
`assert ... .restore_bound_user_id is None` after a successful restore, adoption, move and repeat.

The documented control does not exist. The only limit on subscription sharing is the monthly transfer
cap of WR-06, and the schema currently claims a stronger guarantee than the code delivers.

**Fix:** State what is true, or implement the binding. The honest comment:

```sql
    -- Reserved for a future lifetime restore binding. NOT written by any code path today;
    -- the only sharing limit in force is last_cross_account_transfer_month (D-10).
    restore_bound_user_id UUID REFERENCES core.users (id),
```

### WR-08: `config/config.yaml` documents committed HMAC key material that is not in the file and not used anywhere

**File:** `config/config.yaml:22-34`
**Issue:** Thirteen lines describe "HMAC key material for the §4.3 / §6.4 keyed subject hashes",
warn that "THIS FILE IS TRACKED IN GIT ... The keys below are therefore committed, and rotating one
leaves its predecessor readable in history for good", and instruct that a Secret Manager follow-up
"must REMOVE these entries, not shadow them."

No keys follow. The next stanza is the public `app_store.products` map. `grep -rni 'hmac|subject_hash|blake2|sha256'`
over `src`, `config`, `migrations` and `k8s` matches only this comment — there is no keyed subject
hash anywhere, and `AppConfig` declares no such field (`config.py:119-134`). The subject is stored in
plaintext instead (`migrations:79`, `:297`).

This is a security-relevant comment that is actively wrong in both directions: it tells an operator
that committed secrets exist in a file where none do, and it points a future Secret Manager task at
entries that cannot be removed because they were never added.

**Fix:** Delete the block, or replace it with the current fact.

```yaml
# No secret material lives in this file. It is tracked in git (D-20, accepted), so it carries only
# public reference data: the model settings, the resilience knobs, and the two store product maps.
# Every credential is an environment variable or a file path -- see .env.example.
```

## Info

### IN-01: `AppConfig.json_log_path` is declared and never read

**File:** `src/nativespeaker/api/config.py:121`
**Issue:** `json_log_path: str | None = Field(default=None, description="Path for JSON log file output")`.
`grep -rn json_log_path` over the whole repository matches only this line. `setup_logging`
(`logs.py:17-53`) writes to `sys.stderr` only and never consults it. Setting it in `config.yaml` or
the environment does nothing.
**Fix:** Remove the field, or wire it into a second handler in `setup_logging`.

### IN-02: `Chat.human_messages` is dead, and `Chat.user` is an async-unsafe unused relationship

**File:** `src/nativespeaker/api/tables/chats.py:45`, `src/nativespeaker/api/tables/chats.py:51-53`
**Issue:** `human_messages` has no caller (`grep -rn human_messages src tests` matches only the
definition). `user: User = Relationship()` also has no caller and is never eager-loaded; touching it
on a `Chat` fetched through the async session would raise `MissingGreenlet` rather than return a
user, so it is a trap rather than a feature.
**Fix:** Delete both, or add `selectinload(Chat.user)` at the one place a user is actually needed.

### IN-03: `_is_transient_error` has an unreachable duplicate status check

**File:** `src/nativespeaker/api/resilience.py:30-36`
**Issue:**

```python
if isinstance(exc, APIStatusError):
    status = _extract_status_code(exc)
    if status in {408, 409, 429, 500, 502, 503, 504}:
        return True
status = _extract_status_code(exc)
if status in {408, 409, 429, 500, 502, 503, 504}:
    return True
```

The second block is unguarded and evaluates the identical predicate on the identical value, so the
first block can never change the outcome. The literal set is also duplicated.
**Fix:** Drop lines 30-33 and lift the set to a module constant.

### IN-04: `violation.orig.sqlstate` is dereferenced without a null guard at eight sites

**File:** `src/nativespeaker/api/crud/grants.py:191`, `:249`, `:278`; `src/nativespeaker/api/crud/subscriptions.py:150`, `:197`, `:223`, `:270`, `:300`
**Issue:** `IntegrityError.orig` is typed `BaseException | None`; `ty check src` reports all eight as
`Object of type BaseException | None has no attribute sqlstate`. Under `asyncpg` SQLAlchemy 2.0.46
always populates `orig` with a translated DBAPI error carrying `sqlstate`, so this works today, but
an `IntegrityError` without an original would raise `AttributeError` from inside the `except` and
turn a lost race into an unhandled 500 with the race-detection branch skipped.
**Fix:** `if getattr(violation.orig, "sqlstate", None) != "23505": raise` — or a shared
`_is_unique_violation(violation)` helper, since the seven-line block is copied eight times verbatim.

### IN-05: `/auth/sync` omits the `Cache-Control: no-store` its sibling routes set

**File:** `src/nativespeaker/api/routers/auth.py:190-194`
**Issue:** `claim_anonymous_grant`, `claim_registered_grant` and `restore_subscription` all set
`response.headers["Cache-Control"] = "no-store"` before returning a `SyncResponse`
(`auth.py:127`, `:151`, `:180`). `sync` returns the same model without it. The body carries no
secret, so this is a consistency gap rather than a leak, but four routes returning one shape should
not differ in their cache directive.
**Fix:** Take `response: Response` and set the same header.

### IN-06: `Chat.id` is minted with `uuid4()` while every other table uses `uuid7`

**File:** `src/nativespeaker/api/services/chats.py:88`, `src/nativespeaker/api/tables/chats.py:38`
**Issue:** `Chat.id: UUID = Field(primary_key=True)` has no `default_factory`, unlike `Message`,
`User`, `ExternalIdentity`, `AccessGrant`, `Subscription`, `StorePurchase`, `SubscriptionEvent` and
`AuthChallenge`, which all use `default_factory=uuid7`. The one construction site supplies
`uuid4()`. Chat ids are therefore not time-ordered and index inserts scatter across the B-tree, and
any second construction site that forgets the argument fails at flush with a NOT NULL violation.
**Fix:** `id: UUID = Field(default_factory=uuid7, primary_key=True)` and drop the explicit argument.

### IN-07: `ChatService.get_messages` reports an empty chat as 404

**File:** `src/nativespeaker/api/services/chats.py:128-130`
**Issue:** `if not messages: raise InvalidChatError(chat_id)` uses emptiness as a proxy for absence.
Today every chat is created with two messages so the two cases coincide, but the crud already has
`get_chat` to answer the ownership question directly, and coupling the 404 to row count means any
future path that creates a chat before its first message would answer "not found" for a chat the
caller owns.
**Fix:** Check ownership with `get_chat`, then return the (possibly empty) message list.
