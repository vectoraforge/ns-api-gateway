---
phase: 43-post-webhooks-app-store
reviewed: 2026-09-04T23:43:27Z
depth: standard
files_reviewed: 34
files_reviewed_list:
  - config/config.yaml
  - .env.example
  - k8s/templates/httproute-webhooks.yaml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/__init__.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/routers/__init__.py
  - src/nativespeaker/api/routers/webhooks.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/purchases.py
  - tests/e2e/conftest.py
  - tests/e2e/test_app_store_webhook.py
  - tests/schema/helpers.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_config.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_users.py
findings:
  critical: 4
  warning: 6
  info: 6
  total: 16
status: issues_found
---

# Phase 43: Code Review Report

**Reviewed:** 2026-09-04T23:43:27Z
**Depth:** standard
**Files Reviewed:** 34
**Status:** issues_found

## Summary

The JWS verification seam itself is sound and unusually well tested. The vendored root was
independently confirmed genuine (`sha256 63:34:3A:BF:...:91:79`, `CN=Apple Root CA - G3`, valid to
2039); the environment enum really does exclude the library's two verification-skipping values; the
nested transaction and renewal payloads are each verified on their own rather than trusted through
the envelope's signature; the refusal vocabulary is a single class with a closed-set `stage` label
and leaks no payload text. `ruff` is clean and 1089 unit tests pass.

The defects are all downstream of verification, in the state machine that turns a verified
notification into a subscription row and a grant. Three of them were reproduced by driving the real
`SubscriptionsService` over the phase's own test stubs. In each case the store notification verifies
correctly and the resulting entitlement is wrong.

- **CR-01** and **CR-02** cost a paying customer their access.
- **CR-03** puts a subscription into a permanently-500ing state from which it never recovers.
- **CR-04** turns an App Store misconfiguration into a whole-service boot crash, which is the exact
  opposite of the recorded "answers 503, route stays registered" guarantee — and `.env.example`
  ships the value that triggers it.

Out of scope, as instructed, and therefore not reported: the route being publicly reachable with no
credential and no rate limiter; online revocation checks being off; an incomplete configuration
answering 503.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: An out-of-order notification downgrades a live subscription and revokes the buyer's grant

**File:** `src/nativespeaker/api/services/subscriptions.py:17-33`, `:87-94`, `:120-131`
**Also:** `src/nativespeaker/api/crud/subscriptions.py:84-125`, `:183-252`

**Issue:** `status_at` derives the status from the incoming notification's dates *alone*, and
`upsert_subscription` then writes it over the stored row unconditionally. Nothing compares the
incoming notification against what is already recorded — not `stored.updated_at`, not the
transaction's `purchaseDate`, not `expiresDate`, not `signedDate`. The only replay guard is
`read_event(notification_uuid)` at `:77`, and two *different* notifications for the same subscription
carry two different UUIDs, so it does not fire.

Apple does not guarantee notification order. A `DID_RENEW` for term N+1 followed by a delayed
`EXPIRED` for term N therefore ends with the buyer marked expired: the older payload's `expiresDate`
is in the past, `status_at` returns `expired`, `entitled` is false in
`write_subscription_grant`, and the buyer's active grant is flipped to `expired` with
`ends_at = evaluated_at`.

Reproduced against the real service over the phase's own stubs
(`tests/unit/test_subscription_attribution.py` recorders):

```
after DID_RENEW    -> SubscriptionStatus.active
after late EXPIRED -> SubscriptionStatus.expired
grant writes: [(active,  2026-10-04 12:00 UTC),
               (expired, 2026-09-04 11:59:59 UTC)]
```

The buyer paid for a term running to 2026-10-04 and holds no grant. No test covers this — a repo-wide
search for out-of-order/monotonicity handling finds nothing in `src/`, in `tests/`, or in the phase
artifacts. `tests/schema/test_subscription_ingestion.py:277` is named
`TestTheNewestPurchaseWins`, but what the code actually implements is "the newest *delivery* wins".

**Fix:** Make the write monotonic in the store's own clock. Carry the signing instant across the
seam and refuse to regress:

```python
# auth/app_store.py — add to VerifiedNotification
signed_at: datetime | None          # from payload.signedDate

# services/subscriptions.py — in ingest(), after read_subscription()
if (stored is not None and notification.signed_at is not None
        and stored.updated_at > notification.signed_at):
    # A payload the store signed before the recorded state: record the event, change no status.
    logger.info("store_notification_superseded", event_type=notification.event_type)
    await self.subscriptions_db.append_event(...)   # audit trail still lands
    await self.session.commit()
    return
```

Comparing the transaction's `expiresDate` against the stored term is an acceptable alternative, but
`signedDate` is the value Apple actually orders by. Whichever is chosen, add a schema test that
delivers `DID_RENEW` then a stale `EXPIRED` and asserts the grant survives.

---

### CR-02: A grace-period notification writes a grant whose term has already ended

**File:** `src/nativespeaker/api/services/subscriptions.py:26-29`, `:120-131`
**Also:** `src/nativespeaker/api/crud/subscriptions.py:25`, `:193`, `:227-234`

**Issue:** `status_at` returns `grace_period` exactly when `expires_at <= evaluated_at` and
`grace_period_expires_at > evaluated_at` — that is, the paid term is over and Apple is covering the
gap. `ENTITLED_STATUSES` includes `grace_period`, so `write_subscription_grant` takes the entitled
branch: it expires **every** grant in `marked_active` (`crud/subscriptions.py:203`) and inserts a
replacement with `ends_at = notification.expires_at` — the expiry that is *already in the past*.

`_effective_grants_statement` (`crud/grants.py:24-36`) requires `ends_at IS NULL OR ends_at >
evaluated_at`, so the new grant is never effective. The buyer holds an `active`-marked row that
occupies the one-active-per-user slot, yields zero allowance, and has replaced the grant they had a
moment earlier.

Reproduced:

```
status_at -> grace_period
grant status=grace_period  starts_at=2026-08-05 12:00Z  ends_at=2026-09-03 12:00Z
evaluated_at = 2026-09-04 12:00Z
effective? ends_at > now: False
```

This is not a deliberate product call. `migrations/20260818_01_initial-release.sql` generates
`core.subscriptions.product_entitled_subscription_id` over `('active','grace_period')` precisely so a
grace-period buyer *can* hold a grant, and `43-01-SUMMARY.md:215` states the arm order exists so
entitlement is not dropped "from a subscriber Apple is still serving". The label is right; the row
written under it is inert. No test exercises `grace_period` through
`write_subscription_grant` — `grace_period_expires_at` is `None` in every service-level fixture
(`tests/unit/test_subscription_attribution.py:45`, `tests/e2e/test_app_store_webhook.py:123`,
`tests/schema/test_subscription_ingestion.py:50`).

**Fix:** The grant's term is the interval the buyer is entitled for, which during grace is the grace
window, not the lapsed paid term:

```python
# services/subscriptions.py, in the write_subscription_grant call
ends_at=(notification.grace_period_expires_at
         if status is SubscriptionStatus.grace_period
         else notification.expires_at),
```

Note the CHECK `ends_at > starts_at` on `core.access_grants` still holds, because
`grace_period_expires_at > evaluated_at > purchased_at`. Add a schema case asserting a grace-period
delivery leaves the buyer with an *effective* grant, not merely an active-marked one.

---

### CR-03: A purchase first seen without an `appAccountToken` can never be attributed, and 500s forever

**File:** `src/nativespeaker/api/services/subscriptions.py:83-85`, `:99-109`

**Issue:** When a notification carries no attribution token, `insert_purchase` stores a
server-generated `str(uuid7())` in `identity_value` (`:101-103`). The conflict guard at `:83` then
reads:

```python
if recorded is not None and token is not None and recorded.identity_value != token:
    raise AttributionConflict(...)
```

The generated UUID is compared as if it were a store-supplied token. Every subsequent notification
for that subscription that *does* carry an `appAccountToken` therefore raises `AttributionConflict`,
which is an `InternalError` (500). The state is permanent and unrecoverable through this route: no
status update, no event row, no grant, forever. Apple retries for three days and gives up.

Reproduced:

```
stored identity_value: 01a06ec9-6d3a-72dd-9341-58eec9c2c62f   (server-minted)
AttributionConflict -> Store purchase 'original-fixed' of apple presents another attribution value | status 500
```

The mirror case is tested and passes
(`test_a_later_delivery_without_a_token_is_no_conflict`); this direction is not tested at all. The
asymmetry is invisible because `identity_value` has no discriminator — Apple's `appAccountToken` is
itself a UUID (see `ATTRIBUTION_TOKEN` in `tests/unit/test_app_store_notifications.py:49`), so a
server-minted value and a store-supplied one are indistinguishable in the column. See WR-06.

**Fix:** Compare against a value that is only ever store-supplied. `resolved_token_value` is
`NULL` for a server-minted row by construction (`:108`), and the table's CHECK pins it equal to
`identity_value` otherwise:

```python
if (recorded is not None and token is not None
        and recorded.resolved_token_value is not None
        and recorded.resolved_token_value != token):
    raise AttributionConflict(notification.provider, notification.external_id)
```

That still refuses a genuinely changed owner and stops refusing the first honest attribution of a
purchase recorded unattributed. Note this fixes only the *refusal*; adopting the token onto the
existing `core.store_purchases` row is a separate write the phase deliberately does not perform
("written once per lifecycle key and never updated", `tables/purchases.py:84`) — decide explicitly
whether ingestion or restore backfills it, because today neither does.

---

### CR-04: A malformed App Store variable crashes boot for the whole service, and `.env.example` ships one

**File:** `.env.example:105-107`
**Also:** `src/nativespeaker/api/config.py:74-77`, `src/nativespeaker/api/app/lifespan.py:50-52`

**Issue:** `.env.example` documents, in its own words at lines 102-104, that "Everything except the
store notification runs without these: the service boots, it logs one `app_store_configuration_absent`
warning, and the route fails closed as 503". That holds for *absent* values. It does not hold for the
placeholder values the file itself ships:

```
APP_STORE_APP_APPLE_ID=...
APP_STORE_ENVIRONMENT=...
```

`app_apple_id` is `int | None` and `environment` is `StoreEnvironment | None`, so `...` is a
`ValidationError`, not a `None`. `EnvironmentConfig()` raises inside `lifespan`, uvicorn's startup
fails, and the pod crash-loops. Verified:

```
ValidationError: 2 validation errors for EnvironmentConfig
app_store.app_apple_id  Input should be a valid integer, unable to parse string as an integer
app_store.environment   Input should be 'sandbox' or 'production'
```

Two consequences. A deployer who copies `.env.example` to `.env` — the workflow every other block in
the file assumes, since `OPENAI_API_KEY=...` and `JWT_PROJECT_ID=...` load fine as strings — takes
the *entire* API down, chat included, not just the webhook. And `pyproject.toml` sets
`env_files = [".env"]`, so the same copy breaks the whole test suite. This also contradicts the
phase's recorded fail-closed guarantee: an unusable App Store configuration is supposed to cost the
one route a 503, never the service its boot.

**Fix:** Two parts. Make the example file loadable — comment the three variables out, or give them
values that parse:

```
# Uncomment and fill both, or leave them out entirely; a half-filled value stops the pod.
#APP_STORE_BUNDLE_ID=com.example.yourapp
#APP_STORE_APP_APPLE_ID=1234567890
#APP_STORE_ENVIRONMENT=sandbox
```

And make the promise true by degrading a malformed value to an absent one, so the failure stays on
the route it belongs to:

```python
# config.py
@field_validator("app_apple_id", "environment", mode="before")
@classmethod
def _unset_placeholder(cls, value):
    # A malformed store setting costs this one route its 503, never the service its boot.
    return None if isinstance(value, str) and not value.strip(". ") else value
```

If you prefer to keep the strict parse, add a test asserting that `.env.example` itself loads, so the
two cannot drift again.

## Warnings

### WR-01: `signedPayload` has no length bound on an unauthenticated route

**File:** `src/nativespeaker/api/schemas/webhooks.py:8`
**Issue:** `signedPayload: str = Field(..., min_length=1)` bounds the empty case and nothing else.
Starlette buffers the whole body before validation and neither uvicorn nor Starlette imposes a
default request-size limit, so an anonymous POST of arbitrary size is read into memory. A real Apple
notification is a few kilobytes. This is separate from the deferred rate-limit contract: a bound on
one field is a normal, one-line input-validation measure that costs nothing.
**Fix:**
```python
# 64 KiB: an App Store envelope with both nested JWSs is a few KiB; this is generous headroom.
signedPayload: str = Field(..., min_length=1, max_length=65536)
```

---

### WR-02: The verifier dependency is declared twice, and correctness rests on undocumented FastAPI behaviour

**File:** `src/nativespeaker/api/routers/webhooks.py:13-14` and `:24`
**Issue:** `verify_app_store_notification` is declared both as a router-level dependency and as the
handler's parameter default. It currently runs once — `tests/e2e/test_app_store_webhook.py:208`
pins `calls == [ENVELOPE]` — but only because two separate FastAPI internals happen to line up:
the per-request dependency cache keyed on `(call, security_scopes)`, and
`_should_embed_body_fields`, which de-duplicates body params *by name*. If the latter changed, the
two `body: AppStoreNotificationRequest` params would count as two body fields and the endpoint would
demand `{"body": {"signedPayload": ...}}`, rejecting every real Apple delivery with a 422. The
failure is closed rather than open, but it is a silent total outage of the route.
**Fix:** Declare it once. Keep the handler parameter, since that is what actually consumes the value,
and drop the router-level copy — then update `tests/unit/test_app_wiring.py`, whose
`test_each_callback_route_declares_the_verifier_and_neither_identity` inspects
`route.dependant`, which still sees it. If the router-level declaration is wanted as the partition
marker, keep it and have the handler take the cached value through a thin distinct accessor rather
than re-declaring the same callable.

---

### WR-03: `violation.orig.sqlstate` is unguarded — five new sites, all flagged by `ty`, none suppressed

**File:** `src/nativespeaker/api/crud/subscriptions.py:121`, `:151`, `:177`, `:218`, `:248`
**Issue:** `IntegrityError.orig` is `BaseException | None`. When it is `None`, or when the DBAPI
exception carries no `sqlstate`, the attribute access raises `AttributeError` *from inside the
`except` block* — replacing a recoverable lost-race with an opaque 500 and burying the original
`IntegrityError` as `__context__`. `ty check src` reports all five as
`error[unresolved-attribute]`, unsuppressed, while this codebase does annotate the diagnostics it
accepts (`app/main.py:54`, `tests/unit/test_config.py`). Five new unacknowledged type errors in one
new file is a regression in the project's own standard.
**Fix:**
```python
if getattr(violation.orig, "sqlstate", None) != "23505":
    raise
```
Apply at all five sites, and to the two pre-existing copies in `crud/grants.py:178` and `:236` while
the helper is being extracted for WR-05.

---

### WR-04: The grant's `starts_at` is a store-supplied date with no clamp

**File:** `src/nativespeaker/api/services/subscriptions.py:128-129`
**Issue:** `starts_at` is `notification.purchased_at` verbatim. `_effective_grants_statement`
requires `starts_at <= evaluated_at`, so any `purchaseDate` ahead of this server's clock produces a
grant that is `active`-marked, occupies the one-active slot, expires the buyer's previous grant, and
is not effective until the skew passes. The value is Apple-signed, so this is a clock-skew and
data-quality concern rather than an attack, but the outcome is the same as CR-02 — an entitled buyer
with no allowance — and it is silent.
**Fix:**
```python
# The grant cannot begin after the instant that wrote it, whatever date the store supplied.
starts_at=min(notification.purchased_at or self.evaluated_at, self.evaluated_at),
```

---

### WR-05: The flush/`23505` block is copy-pasted five times in one new file

**File:** `src/nativespeaker/api/crud/subscriptions.py:117-125`, `:147-155`, `:172-181`, `:214-221`,
`:243-252`
**Issue:** Five byte-identical eight-line blocks, comments included, plus two more in
`crud/grants.py`. Every one of them carries the same latent bug (WR-03), which is exactly the cost
this duplication imposes: a fix has to be applied seven times and a reviewer has to confirm seven
times that it was. The file's own header claims "the one spelling of the lock order: a second pair of
statements would be a second thing to keep correct" (`:57`) — the same argument applies here and is
not followed.
**Fix:** One helper beside `WriteOutcome`:
```python
async def _flush_or_lose(session: AsyncSession) -> WriteOutcome:
    """Flush, answering `lost_race` for a unique violation and re-raising every other."""
    try:
        await session.flush()
    except IntegrityError as violation:
        # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
        if getattr(violation.orig, "sqlstate", None) != "23505":
            raise
        return WriteOutcome.lost_race
    return WriteOutcome.applied
```
`upsert_subscription` keeps its own `replayed` distinction by checking the returned outcome.

---

### WR-06: `identity_value` conflates a server-minted UUID with Apple's `appAccountToken`

**File:** `src/nativespeaker/api/tables/purchases.py:91-92`,
`src/nativespeaker/api/services/subscriptions.py:101-103`
**Issue:** A row's `identity_value` is either a store-supplied `appAccountToken` or a server-minted
`uuid7()`, and nothing in the row records which. Both are UUID strings. This is the root cause that
makes CR-03 invisible, and it will make every future consumer — restore in particular — guess. The
`resolved_token_value IS NULL` test is a usable proxy today only because nothing backfills it; the
moment restore adopts a purchase, the proxy stops distinguishing "minted" from "adopted".
**Fix:** Record the provenance rather than inferring it. Either a nullable `identity_value_source`
column (`'store' | 'server'`), or make `identity_value` nullable and stop minting a placeholder — the
NOT NULL is the only reason the UUID exists at all. Whichever is chosen, CR-03's guard should key on
it instead of on `resolved_token_value`.

## Info

### IN-01: Misleading comment — FastAPI does run this dependency in a threadpool

**File:** `src/nativespeaker/api/app/dependencies.py:148`
**Issue:** "Never `run_in_threadpool`: with online checks off, no code path in the seam performs I/O."
`verify_app_store_notification` is a sync `def` dependency, so FastAPI's solver offloads it to the
anyio threadpool regardless. The comment reads as a statement about where the work runs, and it is
wrong; only the *explicit wrapper* is absent. A future reader reasoning about event-loop blocking
from this line will reason incorrectly.
**Fix:** Reword to what is true: "No explicit wrapper: the seam performs no I/O, and FastAPI already
solves a sync dependency off the loop."

### IN-02: `NotificationRejected` answers 401 with no `WWW-Authenticate`

**File:** `src/nativespeaker/api/errors.py:458-462`
**Issue:** RFC 7235 requires a `WWW-Authenticate` header on every 401. Its sibling in the same
family, `UserNotFound` (`:395-402`), overrides `extra_headers` to supply one; `InvalidExternalJwt`
does too. `NotificationRejected` inherits the base `None`. Apple ignores the header, so this costs
nothing operationally — it is an inconsistency inside one error family.
**Fix:** Either add the header for consistency, or note in the class docstring why this 401
deliberately carries no challenge (the route reads no `Authorization` header, so there is nothing to
challenge for).

### IN-03: `core.subscriptions` is read twice per ingestion

**File:** `src/nativespeaker/api/services/subscriptions.py:67-68` and
`src/nativespeaker/api/crud/subscriptions.py:92`
**Issue:** `read_subscription` runs in the service to capture `old_tier_id` and the fallback owner,
then again as the first statement of `upsert_subscription`. Correctness is unaffected (the identity
map returns the same object), but it is an extra round trip and a second place the read could drift.
**Fix:** Pass the already-read row: `upsert_subscription(..., stored=stored)`, defaulting to `None`
so the crud method still reads when a caller has none.

### IN-04: `_crossed`'s first parameter is untyped

**File:** `src/nativespeaker/api/auth/app_store.py:46`
**Issue:** `def _crossed(payload, transaction: ... , renewal: ...)` — the other two parameters are
annotated and `payload` is not, so `payload.notificationUUID` and `payload.rawNotificationType` are
unchecked. The module's stated purpose is that no Apple type escapes it, which makes annotating the
Apple type *inside* it the point rather than a contradiction.
**Fix:** `payload: ResponseBodyV2DecodedPayload`.

### IN-05: The new `app_store:` block reads as if it were the committed key material

**File:** `config/config.yaml:22-39`
**Issue:** The block was inserted directly beneath a comment that says "HMAC key material ... THIS
FILE IS TRACKED IN GIT (D-20, accepted). The keys below are therefore committed" and "The Secret
Manager follow-up must REMOVE these entries". No HMAC keys exist in the file any more, and the only
thing now "below" that warning is a public product map that must *not* be removed. A reader
following the Secret Manager todo would delete the wrong block.
**Fix:** Put a blank line and a `# --- App Store ---` separator before line 36, or move the product
map above the stale key-material comment — and, separately, delete or update that comment now that
it describes nothing.

### IN-06: The router-level verifier binds any future webhook route to Apple

**File:** `src/nativespeaker/api/routers/webhooks.py:12-14`
**Issue:** `dependencies=[Depends(verify_app_store_notification)]` sits on the router, so a Google
Play callback added to the same router in phase 44 would silently be verified against Apple's root
and rejected. `tests/unit/test_app_wiring.py` pins membership of the partition but not the
provider-to-verifier binding.
**Fix:** Move the dependency onto the route decorator, or add a second router per provider. If the
router-level form is kept as the partition marker (see WR-02), leave a comment naming this hazard
explicitly.

---

_Reviewed: 2026-09-04T23:43:27Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
