---
phase: 44-post-webhooks-google-play-rtdn
reviewed: 2026-09-05T00:00:00Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - config/config.yaml
  - .env.example
  - k8s/templates/httproute-webhooks.yaml
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/routers/webhooks.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/subscriptions.py
  - tests/e2e/conftest.py
  - tests/e2e/test_app_store_webhook.py
  - tests/e2e/test_google_play_webhook.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_config.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_subscription_attribution.py
  - uv.lock
findings:
  critical: 2
  warning: 9
  info: 7
  total: 18
status: issues_found
---

# Phase 44: Code Review Report

**Reviewed:** 2026-09-05
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

The Google Play RTDN callback is well-partitioned: the verifier resolves before any
database session, the refusal vocabulary is one class with one body, no closed-set log
label carries a token, and the state map fails closed on every value Google has not
published. The unit and e2e suites are unusually rigorous — several cases are named
`_control` precisely to prove the measurement fires.

Three classes of defect survive that rigour.

First, an **unbounded grant**. `expiryTime` is optional on the parsed line item, and an
entitled state with no expiry writes an access grant with `ends_at = NULL`, which
`_effective_grants_statement` treats as effective forever. The schema suite records this
outcome as expected behaviour rather than catching it.

Second, **an invisible outage**. Every non-2xx Play answer outside 404/410, and every
transport failure, raises a bare `InternalError`, whose `log_level` is `None`. The 500 that
makes Pub/Sub redeliver is emitted with no diagnostic record of any kind — including for
the single most likely Play misconfiguration, a 403 from `androidpublisher`.

Third, **assumptions that are not declared**. `google-auth` does not depend on `requests`,
yet `google_play.py` imports `google.auth.transport.requests` at module scope; the
`package_name` absence path answers 401 forever instead of the documented 503; and the two
provider-callback routes carry neither the JWT SecurityPolicy nor any rate-limit policy.

The declared dependency edge (`google-auth>=2.49`) is correctly reflected in `uv.lock`
(google-auth 2.49.1); the lockfile was checked for that edge only, as scoped.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: An entitled Google state with no line-item expiry grants access forever

**File:** `src/nativespeaker/api/auth/google_play.py:206-233`
(with `src/nativespeaker/api/services/subscriptions.py:127-132` and
`src/nativespeaker/api/crud/grants.py:32-33`)

**Issue:** `PlaySubscriptionLineItem.expiryTime` is `datetime | None`, and `read()` copies
it through without a guard:

```python
expiry = None if line_item is None else line_item.expiryTime
in_grace = subscription.subscriptionState == GRACE_STATE
...
expires_at=expiry,
grace_period_expires_at=expiry if in_grace else None,
```

The product id is required (`UnmappedStoreProduct` is raised when it is absent), but the
expiry is not. Trace the entitled path with `expiry = None`:

1. `_status_for("SUBSCRIPTION_STATE_ACTIVE", None, ...)` returns `SubscriptionStatus.active`
   — the `_STATES` lookup never reads the expiry.
2. `VerifiedNotification` carries `expires_at=None` and `grace_period_expires_at=None`.
3. `SubscriptionsService.ingest` computes
   `ends_at = grace_period_expires_at if grace else expires_at` → `None`.
4. `write_subscription_grant` sees `status in ENTITLED_STATUSES`, supersedes every held
   grant, and inserts `AccessGrant(ends_at=None)`.
5. `_effective_grants_statement` is
   `or_(col(AccessGrant.ends_at).is_(None), col(AccessGrant.ends_at) > evaluated_at)` —
   a NULL `ends_at` is effective at every future instant.

The result is a permanent paid entitlement written from provider-supplied data, on a
sub-$5/month product. The same path is reachable through
`SUBSCRIPTION_STATE_IN_GRACE_PERIOD`, and
`tests/schema/test_subscription_ingestion.py:691` already records that outcome as
correct — `assert [row["ends_at"] for row in await buyer.grants()] == [None]` under the
name `test_an_absent_grace_end_writes_a_grant_carrying_no_end_at_all_control`.

The module comment at `google_play.py:214-215` states the intent — "Left as None, every
grace-period subscriber's grant would be written with no end date" — but the code only
chooses *which field* to copy, never guards the `None` itself. Once written, the row is
corrected only if a later RTDN arrives; if the purchase token later reads as gone
(404/410), `read()` returns `None`, nothing is written, and the perpetual grant stands.

**Fix:** refuse the entitlement rather than granting it unbounded. In
`PlayDeveloperSubscriptions.read`:

```python
expiry = None if line_item is None else line_item.expiryTime
status = _status_for(subscription.subscriptionState, expiry, self._evaluated_at_source())
if status in {SubscriptionStatus.active, SubscriptionStatus.grace_period} and expiry is None:
    # An entitled term with no end is an unbounded grant; 500 here and Play's retry re-reads.
    logger.error("google_play_entitled_state_without_expiry")
    raise InternalError
```

Consider the symmetric guard on the Apple path (`app_store.py:59`, `expiresDate`) and
tighten the schema case at `tests/schema/test_subscription_ingestion.py:691` to assert the
refusal instead of the NULL.

**Resolution (2026-09-06): accepted as an override, not fixed.** Entitled-with-no-expiry has no
producer: `expiryTime` is optional only in this project's model, Google documents no state that
omits it, and the two states that plausibly could (pending, paused) both resolve to `expired` and
never reach the grant write. The value comes from the signed Play read, not the push payload. Full
reasoning in `44-VERIFICATION.md` § Gap Resolution. The one source change is a comment on the field.

### CR-02: Every failed Play read answers 500 with no log record at all

**File:** `src/nativespeaker/api/auth/google_play.py:151` and `:246-247`
(with `src/nativespeaker/api/errors.py:136-141` and
`src/nativespeaker/api/app/error_handlers.py:36-41`)

**Issue:** `_play_answer_is_usable` logs `google_play_purchase_token_gone` for 404 and 410
only. Every other non-2xx status falls through to a bare `raise InternalError` with no log
call, and `_get` converts every `httpx.HTTPError` into `raise InternalError from failure`,
also with no log call. `InternalError` declares `log_level = None`
(`errors.py:140`), and `app_error_handler` short-circuits on exactly that:

```python
if exc.log_level is not None:
    ...
```

So the whole class of Play-read failures — 401 (expired credential), **403 (the
`androidpublisher` permission not granted in Play Console, the documented and most likely
misconfiguration)**, 429, 5xx, DNS failure, TLS failure, timeout — produces a 500 with no
event, no `stage`, no exception, and no status code. The only surviving trace is
`RequestLoggingMiddleware`'s generic `request status_code=500` line
(`logs.py:71-73`), which cannot distinguish a Play 403 from a lost write race or an
unmapped product.

This is confirmed by the suite's own event inventory:
`tests/e2e/test_google_play_webhook.py:518-523` enumerates every event a delivery can
produce, and no event corresponds to a failed Play read. Meanwhile
`.env.example:133-138` asserts that "The `stage` field on the refusal log line is the only
signal that separates 'this deployment is misconfigured' from 'this token is not
Google's'" — this path emits no such line.

Consequence: on a permission mistake, Pub/Sub redelivers every notification until message
retention expires, no subscriber is ever ingested, no grant is ever written, and nothing in
the logs names the cause. A revenue-path outage is invisible for as long as it lasts.

**Fix:** log before raising, with closed-set labels only (a status code and a stage are
both server-side values):

```python
def _play_answer_is_usable(response: httpx.Response) -> bool:
    if response.status_code // 100 == 2:
        return True
    if response.status_code in _GONE_STATUSES:
        logger.error("google_play_purchase_token_gone", status_code=response.status_code)
        return False
    logger.error("google_play_read_failed", status_code=response.status_code)
    raise InternalError
```

and in `_get`:

```python
except httpx.HTTPError as failure:
    logger.error("google_play_read_unreachable", cause=type(failure).__name__)
    raise InternalError from failure
```

Add an e2e case asserting that a scripted 403 produces a `google_play_read_failed` record,
so the event inventory at line 518 keeps the guarantee.

## Warnings

### WR-01: `requests` is imported at module scope but is not a declared dependency

**File:** `src/nativespeaker/api/auth/google_play.py:7` (with `pyproject.toml:25`)

**Issue:** `import google.auth.transport.requests` runs at import time, and that module's
first statement is `import requests`, raising `ImportError` if it is absent. `uv.lock`
shows `google-auth 2.49.1` depends on `cryptography` and `pyasn1-modules` only — not on
`requests`. `requests` is present in this environment purely by accident, pulled in by
`google-api-core`, `firebase-admin` and `tiktoken`.

Because the import is at module scope and `google_play.py` is imported by
`app/dependencies.py`, which is imported by every router, losing that transitive edge does
not degrade one route — **the whole application fails to import**. That is the opposite of
the fail-closed posture every other Google absence in this phase honours.

**Fix:** declare the extra that provides the transport:

```toml
"google-auth[requests]>=2.49",
```

### WR-02: Both provider-callback routes are unauthenticated *and* unrate-limited

**File:** `k8s/templates/httproute-webhooks.yaml:15-24`
(with `k8s/templates/backend-traffic-policy.yaml:9-12` and
`k8s/templates/security-policy.yaml:9-15`)

**Issue:** The SecurityPolicy targets `-app-routes` and `-llm-routes`; the rate-limit
BackendTrafficPolicy targets `-llm-routes` alone. The new `-webhook-routes` HTTPRoute
appears in neither, so the two POST paths reaching the pod have no gateway authentication
(intended, and correct) and **no rate limit at all** (not stated anywhere).

Both routes do unauthenticated cryptographic work per request on Starlette's bounded
threadpool before any credential decision:

- `/webhooks/app-store`: `verify_app_store_notification` is a `def`, so FastAPI runs it in
  the threadpool, where `SignedDataVerifier.verify_and_decode_notification` performs full
  X.509 chain validation of attacker-supplied bytes.
- `/webhooks/google-play/rtdn`: `PubSubPushTokens.verify` runs RS256 verification via
  `run_in_threadpool`.

That same threadpool serves every authenticated request's `get_identity`
(`dependencies.py:63`). A trivial unauthenticated flood on either webhook path therefore
degrades authentication for the entire service. The rate-limit rules that do exist key on
`x-user-plan`, a header only the JWT provider injects, so they could not be reused as
written.

**Fix:** add a second policy (or a second `targetRefs` entry with an IP-keyed rule) for the
webhook route:

```yaml
  targetRefs:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: {{ include "ns-api-gateway.fullname" . }}-webhook-routes
  rateLimit:
    local:
      rules:
      - limit: { requests: 60, unit: Minute }
```

Keep the limit generous — Apple and Google both back off on 429 — but non-infinite.

### WR-03: An absent `package_name` refuses every delivery forever, and boot says nothing

**File:** `src/nativespeaker/api/app/lifespan.py:128-135`
(with `src/nativespeaker/api/app/dependencies.py:179-181`)

**Issue:** The absence check is

```python
if google_push_verifier is None or play_credential is None:
    logger.warning("google_play_configuration_absent", consequence="... until the Play package
                   name, push audience, push service account and Application Default
                   Credentials are available ...")
```

The warning text names the package name, but the condition does not test it —
`build_google_push_verifier` requires only `push_audience` and
`push_service_account_email`. With the audience and the service account set and
`package_name` left `None`, boot is silent and every genuine RTDN hits

```python
if notification.packageName != request.app.state.config.google_play.package_name:
    raise NotificationRejected(stage="package_name_mismatch")
```

which is a 401. Pub/Sub treats 401 as a NACK and redelivers until retention expires.
`tests/unit/test_google_play_notifications.py:332` pins this as the intended behaviour
(`test_an_unconfigured_package_refuses_every_delivery`), but `.env.example:128-131`
promises the opposite: "Everything except the notification runs without these three: the
service boots, it logs one `google_play_configuration_absent` warning, and the route fails
closed as 503." Three documents disagree, and a partly-configured deployment gets the worst
of the three: no boot warning, a refusal whose `stage` reads like a forged delivery, and an
unbounded retry loop.

**Fix:** make the absence check total, and answer the documented 503:

```python
if (google_push_verifier is None or play_credential is None
        or not config.google_play.package_name):
    logger.warning("google_play_configuration_absent", consequence=...)
```

and in the dependency, separate "not configured" from "wrong app":

```python
configured = request.app.state.config.google_play.package_name
if not configured:
    raise Unavailable(stage="google_play_package_name_absent")
if notification.packageName != configured:
    raise NotificationRejected(stage="package_name_mismatch")
```

Update the unit case at line 332 to expect `Unavailable`.

### WR-04: The purchase token is interpolated into the Play URL path unescaped

**File:** `src/nativespeaker/api/auth/google_play.py:33-34` and `:243-245`

**Issue:**

```python
PLAY_URL = (".../applications/{package_name}/purchases/subscriptionsv2/tokens/{purchase_token}")
...
return await self._client.get(
    PLAY_URL.format(package_name=package_name, purchase_token=purchase_token), ...)
```

The purchase token is the body's own value, not a signed claim: the Pub/Sub push token
authenticates the *pusher*, not the message content. Interpolating it raw into a path lets
its bytes change the request target. Measured against the real `httpx.URL`:

- `abc?alt=json#frag` →
  `.../tokens/abc?alt=json#frag` — the token has introduced a query string and a fragment.
- `../../../v3/applications/other/purchases/x` →
  `.../applications/com.x/v3/applications/other/purchases/x` — dot segments are normalized
  and the read addresses a different Play resource.

The exposure is bounded by whoever can publish to the RTDN topic, so this is
defence-in-depth rather than a live hole — but the fix is one call and the current code
carries no comment claiming the value is safe.

**Fix:**

```python
from urllib.parse import quote
...
PLAY_URL.format(package_name=quote(package_name, safe=""),
                purchase_token=quote(purchase_token, safe=""))
```

### WR-05: The "a body Google adds later" log line names nothing

**File:** `src/nativespeaker/api/auth/google_play.py:122-128`

**Issue:**

```python
logger.info("google_play_notification_ignored",
            bodies=sorted(set(notification.model_fields_set) - _ENVELOPE_FIELDS))
```

`DeveloperNotification` does not set `model_config`, so pydantic's default `extra="ignore"`
applies: an undeclared field is dropped and never enters `model_fields_set`. Verified
directly — an RTDN carrying `subscriptionRefundNotification` parses, and the computed
`bodies` value is `[]`.

So the exact case the design exists for — the presence test rather than a name list, so "a
body Google adds later must not fall through here" — produces a log line that names no
body, indistinguishable from a malformed envelope. The corresponding test,
`test_a_body_google_adds_later_answers_here_rather_than_falling_through`
(`tests/unit/test_google_play_notifications.py:311`), asserts only the `None` return and
never inspects `bodies`, so it passes with the diagnostic empty. Its sibling at line 303
passes only because all four `OTHER_BODIES` names are declared fields.

**Fix:** keep the extras so the log can name them:

```python
class DeveloperNotification(BaseModel):
    model_config = ConfigDict(extra="allow")
    ...

def subscription_notification_from(notification):
    if notification.subscriptionNotification is None:
        present = set(notification.model_fields_set) | set(notification.model_extra or {})
        logger.info("google_play_notification_ignored",
                    bodies=sorted(present - _ENVELOPE_FIELDS))
    return notification.subscriptionNotification
```

Extend the line 311 case to assert `"subscriptionRefundNotification"` appears in the record.

### WR-06: The credential refresh runs with a 120-second timeout on a shared threadpool

**File:** `src/nativespeaker/api/auth/google_play.py:236-241`

**Issue:**

```python
if not self._credential.valid:
    await run_in_threadpool(self._credential.refresh,
                            google.auth.transport.requests.Request())
```

`google.auth.transport.requests.Request.__call__` defaults to `timeout=120`, and no
override is passed. The Play HTTP client is deliberately capped at
`PLAY_HTTP_TIMEOUT_SECONDS = 8` for exactly this reason ("A per-request option because
every call sends one bearer") — the refresh in front of it silently gets fifteen times
that budget.

Starlette's threadpool is bounded (40 tokens by default) and is the same one that serves
every `get_identity` JWT verification. A hung token endpoint therefore holds worker tokens
for two minutes each and degrades authentication service-wide, on a route that any
unrate-limited caller can drive (see WR-02).

Secondary: the `valid`/`refresh` pair is unsynchronized across threadpool workers, so
concurrent deliveries can each fire a refresh against the same credential object.

**Fix:** bound the refresh to the same order of magnitude as the read:

```python
import requests

_PLAY_REFRESH_TIMEOUT_SECONDS = 8
_refresh_session = requests.Session()
...
await run_in_threadpool(
    self._credential.refresh,
    google.auth.transport.requests.Request(session=_refresh_session))
```

together with `asyncio.wait_for(..., timeout=PLAY_HTTP_TIMEOUT_SECONDS)`, or a
`threading.Lock` around the refresh if the duplicate calls also matter.

### WR-07: The JWKS warm-up guard catches only `PyJWTError`, so a non-JSON JWKS crashes boot

**File:** `src/nativespeaker/api/app/lifespan.py:69-78`

**Issue:**

```python
try:
    return JWTVerifier(...)
except PyJWTError:
    # The warm-up fetch raises on an unreachable JWKS, and one route's 503 beats a dead pod.
    return None
```

PyJWT's `PyJWKClient.fetch_data` converts only `URLError` and `TimeoutError` into
`PyJWKClientConnectionError`; the `json.load(response)` that follows is outside that
handler. A JWKS endpoint that answers 200 with HTML — a captive proxy, a misrouted egress
rule, a corporate interception box — raises `json.JSONDecodeError`, which is a `ValueError`,
not a `PyJWTError`. It escapes the guard, escapes `lifespan`, and kills the pod.

That is precisely the outcome the comment says the guard exists to prevent, and it takes
the whole service down for one route's misconfiguration.

**Fix:**

```python
except (PyJWTError, ValueError):
    return None
```

The same reasoning applies to the unguarded `JWTVerifier(...)` at `lifespan.py:149`, though
a broken Firebase JWKS arguably *should* stop boot; if so, state that asymmetry in a
comment.

### WR-08: `lineItems[0]` silently picks an arbitrary element

**File:** `src/nativespeaker/api/auth/google_play.py:206-212`

**Issue:** `line_item = subscription.lineItems[0] if subscription.lineItems else None`.
`SubscriptionPurchaseV2.lineItems` is a list, and both the product id and the expiry — the
tier granted and the term granted — are read from element zero. When the list carries more
than one entry (add-ons, or the transitional state of an upgrade), the code picks one
without checking, and the two values that decide the entitlement come from an unspecified
element. Nothing logs that more than one was present.

**Fix:** refuse rather than guess, so the condition is visible instead of silently resolved:

```python
if len(subscription.lineItems) != 1:
    logger.error("google_play_unexpected_line_item_count",
                 count=len(subscription.lineItems))
    raise InternalError
line_item = subscription.lineItems[0]
```

### WR-09: An attribution conflict is a permanent poison message on the Google path

**File:** `src/nativespeaker/api/services/subscriptions.py:74-82`
(with `src/nativespeaker/api/errors.py:277-291`)

**Issue:** When `recorded.resolved_token_value` disagrees with the presented token, the
service raises `AttributionConflict`, a 500. The refusal is deliberate and correct — this
route cannot verify a changed owner. What is not addressed is the consequence on the Google
path: Pub/Sub acknowledges only 102/200/201/202/204, so a single purchase whose
`obfuscatedExternalAccountId` changes will **redeliver on every retry until message
retention expires**, and every later event for that subscription (renewal, cancel, expiry)
is refused by the same guard. The subscription then never leaves its recorded state.

Apple's path is bounded by Apple's own finite retry schedule; Google's is not, and this
phase introduced that asymmetry without noting it.

**Fix:** keep the refusal, end the loop. Record the conflict as an event under the delivery's
replay key, commit, and answer 200:

```python
if (recorded is not None and token is not None
        and recorded.resolved_token_value is not None
        and recorded.resolved_token_value != token):
    await self._settle(await self.subscriptions_db.append_event(
        subscription=stored, event_type=notification.event_type,
        notification_uuid=notification.notification_uuid,
        old_tier_id=stored.tier_id, new_tier_id=stored.tier_id,
        evaluated_at=self.evaluated_at), notification)
    await self.session.commit()
    raise AttributionConflict(notification.provider, recorded.id)  # logged, not retried
```

If the 500 must remain, state the retention-bounded loop in `.env.example` alongside the
audience warning at line 133, so an operator can recognise it.

## Info

### IN-01: `PlaySubscriptionSource` is dead code

**File:** `src/nativespeaker/api/auth/google_play.py:103-109`
**Issue:** The Protocol is defined and referenced nowhere — no annotation, no test, no
`isinstance` check. Its App Store sibling `StoreNotificationVerifier` is at least asserted
against in `tests/unit/test_app_store_notifications.py:275`. A seam nothing types against
documents an intention rather than enforcing one.
**Fix:** annotate the state member or the test double against it, or delete it.

### IN-02: The Google request reads the clock twice

**File:** `src/nativespeaker/api/app/lifespan.py:143` (with
`src/nativespeaker/api/services/subscriptions.py:23-24`)
**Issue:** `evaluated_at_source=get_evaluated_at` hands a FastAPI dependency callable to the
Play reader as a plain clock. The instant that decides canceled-vs-expired is therefore a
different `datetime.now(UTC)` from the one FastAPI resolves for `SubscriptionsService`,
contradicting "One instant for this request; nothing below it reads the clock again."
**Fix:** pass the request's instant through the dependency, or name the source something
that is not a dependency (`evaluated_at_source=lambda: datetime.now(UTC)`) and drop the
"one instant" claim for this path.

### IN-03: The 401 refusals carry no `WWW-Authenticate` header

**File:** `src/nativespeaker/api/errors.py:459-463`
**Issue:** `NotificationRejected` declares `status = 401` and inherits
`ProviderLookupError`, which does not override `extra_headers`. RFC 9110 §15.5.2 requires a
`WWW-Authenticate` header on every 401. `InvalidExternalJwt` and `UserNotFound` both honour
this; this class does not.
**Fix:** add `extra_headers` returning `{"WWW-Authenticate": 'Bearer error="invalid_token"'}`.
Neither store reads it, so this is conformance only.

### IN-04: `messageId` is required but never read

**File:** `src/nativespeaker/api/schemas/webhooks.py:13`
**Issue:** `messageId: str` has no default, so an envelope without it is a 422 — for a field
no code path consumes. `subscription` beside it is correctly optional and documented as
"which this route never reads."
**Fix:** `messageId: str | None = None`, matching the `subscription` field's treatment.

### IN-05: The auth-package shape test is a churn tripwire

**File:** `tests/unit/test_auth_package_shape.py:13`
**Issue:** `CURRENT = (8, 23, 53)` counts modules, classes and functions by AST walk. Any
benign edit — extracting a helper, adding a guard clause as a nested function — fails the
suite with no correctness signal, and the only remedy is to write a new number down. The
`_control` case beside it tests the counter, not the package.
**Fix:** either assert a ceiling (`assert _measure(...) <= CURRENT`) so growth is what
trips it, or delete it in favour of the behavioural cases that already cover this package.

### IN-06: A stale comment in a tracked config file warns about secrets it no longer holds

**File:** `config/config.yaml:22-34`
**Issue:** The block states "HMAC key material for the §4.3 / §6.4 keyed subject hashes …
THIS FILE IS TRACKED IN GIT (D-20, accepted). The keys below are therefore committed, and
rotating one leaves its predecessor readable in history for good." No such keys exist below
it — the file goes straight to `app_store.products` — and `AppConfig` declares no field for
them. The rest of the block (the init_settings precedence rule, the Secret Manager
follow-up) is still correct and load-bearing.
**Fix:** delete the two paragraphs describing the absent keys; keep the precedence rule and
the Secret Manager pointer.

### IN-07: The linter and the type checker are runtime dependencies

**File:** `pyproject.toml:20-21` (with `:37-38`)
**Issue:** `ruff==0.15.7` and `ty==0.0.24` are pinned under `[project] dependencies`, so
they are installed into the production image, while the `dev` group separately declares
`ruff >=0.15.2` and `ty >=0.0.17`. Two specifiers for the same tool in one file is a
contradiction waiting to be resolved the wrong way, and neither tool is imported by any
runtime module. `httpx` is duplicated the same way, though it is genuinely a runtime
dependency there.
**Fix:** remove `ruff` and `ty` from `[project] dependencies`, leaving the `dev` group's
entries; drop the duplicate `httpx` line from `dev`.

---

_Reviewed: 2026-09-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
