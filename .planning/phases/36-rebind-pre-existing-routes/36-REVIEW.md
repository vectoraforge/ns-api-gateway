---
phase: 36-rebind-pre-existing-routes
reviewed: 2026-09-08T00:00:00Z
depth: standard
files_reviewed: 150
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
  - tests/unit/test_chats_crud.py
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
  warning: 7
  info: 7
  total: 15
status: issues_found
---

# Phase 36: Code Review Report

**Reviewed:** 2026-09-08
**Depth:** standard
**Files Reviewed:** 150
**Status:** issues_found

## Summary

Incremental re-review of the whole tree as it stands after Phase 46 and the Phase 35 fix pass
(`11b5573..42c4e55`). Those fixes are treated as current code and are not re-flagged; I agree with
all eight of them on the merits.

Baseline measurements taken during this review: `ruff check .` is clean, `pytest` is 1296 passed /
577 deselected, `ty check src` reports 50 diagnostics (all annotation gaps, none of which I could
turn into a live failure except WR-06).

The rejection taxonomy, the lock ordering in `crud/grants.py` and `crud/subscriptions.py`, the
fail-closed reads in `services/quota.py` and `services/sync.py`, and the adapter seams in `auth/`
are the strongest parts of the tree and I found nothing wrong in them. The concentration of defects
is at the edges: connection lifetime, DSN construction, request-body bounds, and one read that is
issued twice with two different conclusions drawn from it.

One BLOCKER. `QuotaService.charge` opens a second database session while the request session is
already holding a connection, and the pool is sized for a concurrency figure five times smaller than
the one the resilience gate actually admits. Twelve concurrent chat POSTs exhaust the pool with
every request holding one connection and waiting for a second.

I did **not** flag the absent challenge-row reaper: `SHARED-INVARIANTS.md:59` binds "no scheduled
cleanup, purge, reconciliation, recovery-scan, or background-healer job of any kind (challenge rows
... indefinite retention)". The unbounded growth of `core.auth_challenges` is a decision, not a
defect.

## Critical Issues

### CR-01: Two connections per in-flight chat POST against a pool sized for one

**File:** `src/nativespeaker/api/services/quota.py:30`, `src/nativespeaker/api/services/chats.py:92-94`,
`src/nativespeaker/api/app/lifespan.py:145`, `config/config.yaml:16-19`

**Issue:** A chat POST holds two database connections at once, and the pool cannot supply them.

The sequence for `POST /chats` is:

1. `ChatService.create_chat` calls `self.chats_db.count_chats(user_id)` (`services/chats.py:84`) on
   the request session that `Depends(get_db)` supplied. That statement checks a connection out of
   the pool and opens a transaction; `get_db` does not commit until the handler has returned
   (`app/dependencies.py:43-50`), so the connection stays held for the rest of the request —
   including the whole OpenAI round trip.
2. Inside `async with self.llm_service.admission()`, `services/chats.py:93` calls
   `QuotaService.charge`, which opens a **second** session from `app.state.session_factory`
   (`services/quota.py:30`) on the same engine. That needs a second connection at the same instant.

`POST /chats/{chat_id}` is identical: `get_chat` at `services/chats.py:106` checks the first
connection out, `charge` at line 117 asks for the second.

The pool is `pool_size=12, max_overflow=0` (`app/lifespan.py:145`, `config/config.yaml:19`), so the
engine hands out at most 12 connections and never overflows. The number of requests that can be
inside `admission()` simultaneously is `resilience.pool_size + resilience.queue_size` = 5 + 25 = 30
(`resilience.py:76-80` — `inflight_slot` takes from a queue of `max_concurrency + max_queue`
tokens; the semaphore of 5 is only taken later, inside `ainvoke`).

So with 12 concurrent chat POSTs, all 12 hold their request-session connection and all 12 then ask
for a quota connection. Nothing is free. Every one of them blocks in `QueuePool._do_get` for
`pool_timeout` (SQLAlchemy default 30 s) and then raises `sqlalchemy.exc.TimeoutError`, which the
generic handler turns into a 500. Fewer than 12 also degrade: with 7 concurrent POSTs, 12 - 7 = 5
quota connections are available for 7 requests, so 2 of them stall.

The config comment at `config/config.yaml:16-17` states the intended arithmetic and shows where the
reasoning went wrong: "Two connections per possible in-flight chat plus two spare, at the
resilience.pool_size of 5 above" — 5 x 2 + 2 = 12. But `resilience.pool_size` is the *provider
permit* count, not the number of requests past admission. `queue_size: 25` is the other 25.

**Fix:** Release the request-session connection before the quota charge, so a chat POST never needs
two connections at the same time. The request session has no uncommitted work at that point —
`count_chats` and `get_chat` are reads.

```python
# services/chats.py, both create_chat and send_message, before entering admission()
# Ends the read transaction and returns the connection to the pool; the session reopens
# lazily when the handler writes the chat rows after the provider answers.
await self.chats_db.session.rollback()
async with self.llm_service.admission() as admitted:
    await self.quota_service.charge(user_id=user_id, evaluated_at=self.evaluated_at)
    ai_message = await self.ask_llm(chat, human_message, admitted)
```

If the two-connection shape is kept deliberately instead, then `db.pool_size` must cover
`2 * (resilience.pool_size + resilience.queue_size)` = 60, not 12, and the comment in
`config/config.yaml:16-17` must name `queue_size` rather than `pool_size`. A `pool_timeout` shorter
than the 30 s default should be set either way, so an exhausted pool answers fast instead of pinning
a worker.

## Warnings

### WR-01: The database DSN interpolates the password without percent-encoding

**File:** `src/nativespeaker/api/config.py:38-40`, `pyproject.toml:328`

**Issue:** `DatabaseConfig.url` builds the DSN by f-string. A password containing any of `@ / : ? #`
re-partitions the URL. Demonstrated against the installed SQLAlchemy:

```
make_url("postgresql+asyncpg://postgres:p@ss/w0rd@db.internal:5432/ns")
  -> host='ss'  user='postgres'  password='p'  database='w0rd@db.internal:5432/ns'
```

The application then tries to reach a host named `ss` and sends it the user `postgres` and the
password `p`. In a cluster that is a credential sent to whatever `ss` resolves to, not a clean boot
failure. `pyproject.toml:328` builds the pogo DSN the same way and has the same behaviour during
migrations.

**Fix:** Build the URL with the library rather than by string, so every component is escaped:

```python
from sqlalchemy.engine import URL

@property
def url(self) -> str:
    return URL.create("postgresql+asyncpg",
                      username=self.user,
                      password=self.password.get_secret_value(),
                      host=self.host,
                      port=self.port,
                      database=self.name).render_as_string(hide_password=False)
```

### WR-02: The restore reads the subscription twice and the second read can overwrite webhook-owned state

**File:** `src/nativespeaker/api/services/restore.py:53`, `:58`, `:85-95`;
`src/nativespeaker/api/crud/subscriptions.py:117-143`

**Issue:** `RestoreService.restore` reads the canonical row at line 53 and, when it is `None`, takes
the "adoption-with-creation" branch at line 85. `upsert_subscription` then issues its **own**
`read_subscription` at `crud/subscriptions.py:117`. Both statements run under READ COMMITTED, which
takes a fresh snapshot per statement, so the second read can see a row a concurrent webhook
committed in between.

When it does, `upsert_subscription` falls into the `else` branch at line 129 and **updates the
canonical row in place** with `tier_id=proof.tier_id` and `status=proof.status`. That is exactly the
write D-06 forbids: the service already decided at `restore.py:58`
(`status = proof.status if stored is None else stored.status`) that a row which exists decides with
its own status "because canonical state is the webhooks'". The two reads reach opposite conclusions
and the second one wins the write.

Concrete failure: a webhook records `expired` for the subscription between the two reads; the
restore, holding a proof that still parses as `active`, writes `active` back over it. The grant that
`write_subscription_grant` then mints at `restore.py:134` uses the *first* read's `status`
(`proof.status`), so the caller receives an entitlement the store has already withdrawn, bounded
only by `term_ends_at`.

**Fix:** Make the create branch insert-only, so a row appearing between the two reads is a lost race
rather than a silent update. Give `SubscriptionsDB` a separate `insert_subscription` that adds the
row and returns `WriteOutcome.lost_race` on sqlstate 23505, and call that from `restore.py:87`
instead of `upsert_subscription`. `_settle` already turns `lost_race` into the 500 whose retry
re-reads the winner's row.

### WR-03: The two unauthenticated routes accept an unbounded request body

**File:** `src/nativespeaker/api/schemas/webhooks.py:8`, `:15`

**Issue:** `AppStoreNotificationRequest.signedPayload` and `PubSubPushMessage.data` declare only
`min_length=1`. `POST /webhooks/app-store` and `POST /webhooks/google-play/rtdn` are the only two
routes outside the Envoy JWT SecurityPolicy (`k8s/templates/httproute-webhooks.yaml:237-240`), so
they are the only two an unauthenticated caller reaches. On the Apple route the body is handed
straight to `SignedDataVerifier.verify_and_decode_notification` (`app/dependencies.py:170`) with no
credential checked first — the payload *is* the credential.

The asymmetry is the evidence that this is an oversight rather than a decision: the *authenticated*
`RestoreRequest.restore_proof` is capped at `max_length=8192` (`schemas/auth.py:44`) with the
comment "Bounded well above an Apple transaction and a Play token, which reach a decoder and a URL".
The same reasoning applies harder to the body nobody authenticated.

**Fix:** Bound both fields at the same order of magnitude as `restore_proof`, so the framework's 422
refuses an oversized body before any decoder runs:

```python
signedPayload: str = Field(..., min_length=1, max_length=16384)
data: str = Field(..., min_length=1, max_length=16384)
```

### WR-04: `tables/__init__.py` re-exports eleven `schemas/` types that nobody imports from there

**File:** `src/nativespeaker/api/tables/__init__.py:3-9`, `:13-27`

**Issue:** The package root re-exports `AnalyzeInput`, `AnalyzeResponse`, `ChatRequest`,
`ChatResponse`, `ExamplesResponse`, `FollowUpInput`, `FollowUpResponse`, `Issue`, `MessageRequest`,
`MessageResponse` and `RejectResponse` from `schemas/api.py` and `schemas/llm.py`.

I collected every `from nativespeaker.api.tables import ...` in `src/` and `tests/` by AST walk. The
complete set of names taken from that root is: `AccessGrant, AccessGrantSource, AccessGrantStatus,
AccessTier, Chat, ChatRole, ExternalIdentity, FREE_GRANT_SOURCES, IdentityProvider, IdentityState,
Message, PurchaseProvider, StorePurchase, StorePurchaseToken, Subscription, SubscriptionEvent,
SubscriptionStatus, User, UserMonthlyUsage`. Not one of the eleven appears. Every real consumer
imports them from `schemas.api` or `schemas.llm` directly.

Beyond being dead, they invert the layering `AGENTS.md` § "Package layout" fixes: `tables/` is
declared to hold "SQLModel tables and the enums mirroring database types", and this import makes the
tables package depend on the schemas package.

**Fix:** Delete lines 13-27 and the eleven names from `__all__`. Nothing imports them from here, so
the change cannot break a caller.

### WR-05: Compose publishes Postgres on every interface with the `.env` password

**File:** `docker-compose.yml:54-55`

**Issue:** `ports: - "5432:5432"` binds the container port to `0.0.0.0` on the host. The password is
`${DB_PASSWORD}`, which `.env.example:67` ships as `postgres`. On any developer machine on a shared
network — a café, a co-working space, a conference — that is an open Postgres with a guessable
password holding the plaintext `preauth_subject` values of `core.auth_challenges` and every
`store_purchase_tokens.identity_value`.

**Fix:** Bind to loopback. The application connects from the host (`DB_HOST=localhost`), so nothing
needs the wider binding:

```yaml
    ports:
      - "127.0.0.1:5432:5432"
```

### WR-06: `tier_id` reaches a NOT NULL column guarded only by a comment about a different field

**File:** `src/nativespeaker/api/services/subscriptions.py:29`, `:36`, `:91`, `:117`, `:126`;
`src/nativespeaker/api/auth/store_notifications.py:19-21`

**Issue:** `VerifiedNotification.tier_id` is `str | None`. `SubscriptionsService.ingest` guards at
line 29 on `external_id` and `product_id` — never on `tier_id` — and then passes `tier_id` to
`upsert_subscription` (line 91), `append_event` (line 117) and `write_subscription_grant`
(line 126), all three of which declare the parameter `str`. `ty check src` reports all three.

The safety rests on the comment at `store_notifications.py:19-20` ("Resolved by the provider's own
class, so it is absent exactly when `product_id` is"). That holds today because both
`AppStoreNotifications._tier_for` (`auth/app_store.py:149-155`) and
`PlayDeveloperSubscriptions._product_of` (`auth/google_play.py:299-306`) raise
`UnmappedStoreProduct` rather than return `None`. But it is an invariant across three files with
nothing enforcing it. If a third adapter, or a change to either of those two, ever returns a
notification with a `product_id` and no `tier_id`, `AccessGrant.tier_id` is set to `NULL`, Postgres
raises 23502, `crud/subscriptions.py:300` re-raises it, and the store gets a 500 it retries forever.

**Fix:** Test the value the code actually consumes, next to the two it already tests:

```python
if (notification.external_id is None or notification.product_id is None
        or notification.tier_id is None):
    logger.info("store_notification_without_transaction", event_type=notification.event_type)
    return
tier_id = notification.tier_id  # now `str`, and the three call sites type-check
```

### WR-07: No access-log line is written for a 500 raised out of a handler

**File:** `src/nativespeaker/api/logs.py:68-73`, `src/nativespeaker/api/app/main.py:52-54`

**Issue:** `RequestLoggingMiddleware.dispatch` reaches its logging block only if `await call_next()`
returns. Starlette installs the handler registered for bare `Exception`
(`app/error_handlers.py:81`) on `ServerErrorMiddleware`, which sits *outside* every user middleware.
So an exception that no `AppError` handler claims propagates straight through `dispatch`, and lines
71-73 never run.

Verified against this build:

```
GET /boom (handler raises RuntimeError)
  status: 500 {'code': 'internal_error'}
  log events emitted: ['Unhandled exception']      # no 'request' line
```

The `logger.error` choice at line 72 shows the intent is that failures are logged loudest, and the
one class of request that reaches it never does. The 500s stemming from CR-01 above are exactly the
traffic this would have surfaced. `request_id` still correlates through contextvars, but
`status_code` and `duration_ms` are lost for every such request.

**Fix:** Wrap the call so the line is written on both exits:

```python
start = time.perf_counter()
try:
    response = await call_next(request)
except BaseException:
    if request.url.path not in _EXCLUDED_PATHS:
        logger.error("request", status_code=500,
                     duration_ms=round((time.perf_counter() - start) * 1000, 2))
    raise
```

## Info

### IN-01: `_is_transient_error` checks the status code twice

**File:** `src/nativespeaker/api/resilience.py:30-36`

**Issue:** Lines 30-33 extract the status code for an `APIStatusError` and test it against a set;
lines 34-36 extract it again for *any* exception and test it against the identical set literal. The
`APIStatusError` branch cannot produce an answer the unconditional check below would not. Two copies
of the same set literal will drift.

**Fix:** Delete lines 30-33 and hoist the set to a module constant.

### IN-02: `Chat.human_messages` has no caller

**File:** `src/nativespeaker/api/tables/chats.py:57-59`

**Issue:** Grepped across `src/` and `tests/`: the property is defined and never read. Its sibling
`ai_messages` is used at `services/chats.py:110`.

**Fix:** Delete it.

### IN-03: `RejectResponse` is never used outside its own test

**File:** `src/nativespeaker/api/schemas/llm.py:35-37`

**Issue:** `ChatService.ask_llm` handles the reject arm by raising `OutOfScopeError`
(`services/chats.py:63-64`) without constructing or validating `RejectResponse`. The only reference
anywhere is `tests/unit/test_models.py:219`, which keeps a class alive that production never builds.

**Fix:** Delete the class and its test, or state in the docstring that it exists as a schema
document for the reject arm rather than as a runtime type.

### IN-04: `ix_auth_challenges_expires_at` serves no query

**File:** `migrations/20260818_01_initial-release.sql:322`

**Issue:** The only statement filtering on `expires_at` is the claim UPDATE
(`crud/challenges.py:70-72`), and it already selects a single row by `challenge_id`, which is
UNIQUE. The `expires_at > now` term is evaluated against that one row. The index is the shape a
sweeper would need, and `SHARED-INVARIANTS.md:59` forbids the sweeper.

**Fix:** Drop it, or add a one-line comment saying it is deliberately kept for a future manual
purge, so the next reader does not go looking for the job that uses it.

### IN-05: One of the three 400s on `POST /chats` charges a credit and the other two do not

**File:** `src/nativespeaker/api/services/chats.py:81-86` vs `:63-64`, `src/nativespeaker/api/services/quota.py:2`

**Issue:** `UnsupportedLanguageError` and `ChatHistoryLimitError` are raised at lines 82 and 86,
before the charge at line 93, so a caller refused for those reasons keeps its credit.
`OutOfScopeError` is raised at line 64, after the charge has committed, so a caller refused for
being off-topic loses one. All three answer 400. The module docstring at `quota.py:2` covers "a
failed provider call is not refunded", which is not this case — the provider call succeeded and
returned `resolved_mode: "reject"`.

**Fix:** Either state the intent in the docstring ("a completed provider call is charged whatever
mode it resolved to"), or move the reject arm's refusal ahead of the charge. Charging for real
provider work is defensible; the silence about it is what makes it a finding.

### IN-06: `write_bits` accepts any 2xx while its docstring claims explicit confirmation

**File:** `src/nativespeaker/api/auth/devicecheck.py:129`, `:132`, `:89-95`

**Issue:** The docstring says "accepting only Apple's explicit confirmation as success", but the
implementation calls `_reject_or_retry`, which returns without raising for every status in the 2xx
range and never looks at the body. `read_bits` really does inspect the body
(`_parse_bit_state`); `write_bits` does not. Per `AGENTS.md` § "Comments and docstrings", the
docstring states something the function does not do.

**Fix:** Reword to what it does — "Write both bits; any 2xx is the confirmation, every other status
is refused or retried" — or check the body if Apple's update response carries one worth checking.

### IN-07: `violation.orig.sqlstate` reads an attribute off an Optional at eight sites

**File:** `src/nativespeaker/api/crud/grants.py:191`, `:249`, `:278`;
`src/nativespeaker/api/crud/subscriptions.py:150`, `:197`, `:223`, `:270`, `:300`

**Issue:** `StatementError.orig` is typed `BaseException | None` and `ty` reports all eight. In
practice SQLAlchemy always populates `orig` for a `DBAPIError`, and the asyncpg dialect does set
`.sqlstate` on the translated exception (verified in
`sqlalchemy/dialects/postgresql/asyncpg.py::_handle_exception`), so I could not turn this into a
live failure. It stays a finding because the failure mode if the assumption ever breaks is an
`AttributeError` raised *inside* an `except IntegrityError` block — the race branch would be lost
and the caller would see an opaque 500 instead of `lost_race`.

**Fix:** One shared helper, so the eight copies become one:

```python
def _is_unique_violation(violation: IntegrityError) -> bool:
    """Whether this integrity failure is a unique violation the indexes arbitrated."""
    return getattr(violation.orig, "sqlstate", None) == "23505"
```

---

_Reviewed: 2026-09-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
