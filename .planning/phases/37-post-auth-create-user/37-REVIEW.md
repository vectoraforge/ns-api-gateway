---
phase: 37-post-auth-create-user
reviewed: 2026-09-09T00:00:00Z
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
  critical: 2
  warning: 9
  info: 8
  total: 19
status: issues_found
---

# Phase 37: Code Review Report

**Reviewed:** 2026-09-09
**Depth:** standard
**Files Reviewed:** 150 (re-review; scope = everything changed since commit f0857b1)
**Status:** issues_found

## Summary

The Python source is disciplined: fail-closed defaults, a single error registry, one
captured evaluation instant per request, a consistent grant/usage lock order, and a
test suite that passes clean (1324 unit tests, `ruff` clean). The rejection vocabulary
and the anti-oracle rules in `SHARED-INVARIANTS.md` are honoured in the handler and
service layers.

The defects concentrate at the two edges the unit suite cannot reach: the wire size of
real store payloads, and the Kubernetes gateway manifests. Two of them are shipping
blockers — the App Store callback body bound is smaller than a real Apple notification,
and no `HTTPRoute` matches `/auth/*` at all, so the entire authentication and
entitlement surface this milestone built returns 404 behind Envoy.

A second cluster of warnings sits around observability (three failure paths that answer
500 with no log line naming them) and around the gateway rate-limit policy, which keys
on an identity header that `SHARED-INVARIANTS.md` explicitly forbids and that nothing
ever populates.

Note on prior fixes: the phase 35 and 36 code-review-fix passes are treated as current,
intentional code. Nothing below re-flags them. WR-02 concerns behaviour that is
deliberate and covered by a passing test — it is raised anyway, with that fact stated,
because it denies service to a paying customer.

## Structural Findings (fallow)

No `<structural_findings>` block was supplied for this run.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: The App Store callback body bound is smaller than a real Apple notification

**File:** `src/nativespeaker/api/schemas/webhooks.py:9`
(and the test that locks the value in: `tests/unit/test_models.py:298`)

**Issue:** `signedPayload` is capped at `max_length=16384`. A real App Store Server
Notification V2 envelope is larger than that, so every genuine Apple delivery carrying a
transaction would be refused with a 422 `validation_error` before `verify_app_store_notification`
ever runs. Apple retries on a schedule and then gives up; the result is that no Apple
subscription is ever ingested, no `core.subscriptions` row is written, and paying
subscribers receive no grant.

The size arithmetic: the notification carries Apple's certificate chain **three times** in
one body — once in the outer JWS header, and once inside each of the two nested JWS
strings (`data.signedTransactionInfo`, `data.signedRenewalInfo`), which are themselves
embedded in the outer payload and therefore pay a second base64 inflation of 4/3. The
vendored root alone (`config/certs/AppleRootCA-G3.cer`) is 583 DER bytes → 780 base64
characters, and the intermediate and leaf are each larger. With a conservative 3.4 KB
base64 chain, certificate material alone is roughly `3.4 + (4/3 × 2 × 3.4) ≈ 12.5 KB`,
before any claims. The realistic envelope lands in the 18–24 KB range.

Nothing in the suite catches this: `tests/e2e/test_app_store_webhook.py:41` uses
`ENVELOPE = "signed-payload-that-only-the-scripted-seam-reads"`, and
`tests/unit/test_models.py` asserts the 16384 bound rather than testing a real envelope.
The same constant is reused for `PubSubPushMessage.data`, where an RTDN is a few hundred
bytes — one number was chosen for two payloads with wildly different sizes.

**Fix:** Raise the Apple bound and keep the Google one tight, then regression-test the
new bound against a captured real envelope rather than a synthetic string.

```python
# src/nativespeaker/api/schemas/webhooks.py
# Apple transmits its certificate chain three times in one envelope (outer header plus
# both nested JWS payloads), so a real V2 notification runs to roughly 20 KB.
APP_STORE_ENVELOPE_LIMIT = 65536
# An RTDN is a few hundred bytes of base64; this bound stays where it is.
PUBSUB_DATA_LIMIT = 16384


class AppStoreNotificationRequest(BaseModel):
    signedPayload: str = Field(..., min_length=1, max_length=APP_STORE_ENVELOPE_LIMIT)
```

Update `tests/unit/test_models.py` to parameterise the two limits separately, and add a
case that a captured production-shaped envelope (chain included) validates.

---

### CR-02: No `HTTPRoute` matches `/auth/*` or `/`, so the whole auth surface is unreachable

**File:** `k8s/templates/httproute-app.yaml:11-24`, `k8s/templates/httproute-llm.yaml:11-19`,
`k8s/templates/httproute-health.yaml:11-17`, `k8s/templates/httproute-webhooks.yaml:15-24`

**Issue:** The chart registers exactly four route sets, and their combined match list is
`/chats`, `/users`, `/examples` (app-routes), `POST /chats` (llm-routes), `/health`
(health-routes), and the two exact webhook paths. `k8s/templates/NOTES.txt:7` states the
same four.

Every route this milestone added is outside that set:

- `POST /auth/challenge`
- `POST /auth/create-user`
- `POST /auth/upgrade-anonymous`
- `POST /auth/claim-anonymous-grant`
- `POST /auth/claim-registered-grant`
- `POST /auth/restore-subscription`
- `POST /auth/sync`
- `POST /auth/sign-out-all`
- `GET /` (`src/nativespeaker/api/routers/root.py:13`)

Envoy Gateway answers an unmatched path with 404 at the listener, so none of these reach
the pod in a deployed cluster. Account creation, entitlement sync, grant claims, restore
and sign-out are all dead in production. `tests/unit/test_app_wiring.py` proves the
routes are registered on the FastAPI app; nothing proves they are reachable through the
gateway.

**Fix:** Add an `HTTPRoute` for the auth surface and the root, and put it under the JWT
`SecurityPolicy` alongside app-routes and llm-routes.

```yaml
# k8s/templates/httproute-auth.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{ include "ns-api-gateway.fullname" . }}-auth-routes
  namespace: {{ .Values.namespace }}
  labels:
    {{- include "ns-api-gateway.labels" . | nindent 4 }}
spec:
  parentRefs:
  - name: {{ .Values.gateway.name }}
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /auth
    - path:
        type: Exact
        value: /
    backendRefs:
    - name: {{ include "ns-api-gateway.fullname" . }}
      port: {{ .Values.service.port }}
```

Then add `-auth-routes` to `spec.targetRefs` in `k8s/templates/security-policy.yaml`, and
update the route enumeration in `k8s/templates/NOTES.txt`.

Note that `POST /auth/create-user` and `POST /auth/challenge` are pre-auth-callable by
design (`tests/unit/test_app_wiring.py:19`), so if the Envoy JWT filter is applied to
this route it must not reject a caller whose token verifies but whose identity is
unlinked — the token is present in both phases, so a plain JWT `SecurityPolicy` is
correct here; the unlinked-caller decision stays in the backend barrier.

## Warnings

### WR-01: `ChallengeRequest.operation` is unbounded and is logged verbatim

**File:** `src/nativespeaker/api/schemas/auth.py:15`, logged at
`src/nativespeaker/api/routers/auth.py:60`

**Issue:** `operation: str` carries no `max_length`. On the rejection path the handler
writes `logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)`,
so an arbitrary-length caller-supplied string reaches the log pipeline intact. There is
no application-level body size limit (FastAPI and uvicorn impose none), so a single
request can push megabytes into the log stream, and embedded newlines forge additional
lines under `structlog.dev.ConsoleRenderer`.

This is the exact hazard the sibling field already guards against —
`RestoreRequest.provider` at `src/nativespeaker/api/schemas/auth.py:42` is bounded with
the comment *"Bounded well above every store name, because the handler's refusal log
carries this value."* The same reasoning was not applied to `operation`, which is logged
by the same pattern one route over.

**Fix:**

```python
class ChallengeRequest(BaseModel):
    """The issuance body. `operation` is a plain `str`, never a Literal: an unissuable value is the handler's 400."""
    # Bounded well above every member of core.auth_operation, because the handler's refusal log carries this value.
    operation: str = Field(..., min_length=1, max_length=64)
```

---

### WR-02: An Apple subscription in `grace_period` can never be restored

**File:** `src/nativespeaker/api/services/restore.py:58-67`, with the root cause at
`src/nativespeaker/api/auth/app_store.py:147`

**Issue:** `restore()` takes the **status** from the canonical row and the **term** from
the proof:

```python
status = proof.status if stored is None else stored.status          # line 58
term_ends_at = (proof.grace_period_expires_at
                if status is SubscriptionStatus.grace_period else proof.expires_at)  # 63-64
if term_ends_at is None or term_ends_at <= self.evaluated_at:
    raise RestoreSubscriptionNotEntitled                              # 65-67
```

On the Apple path `verify_transaction` hardcodes `grace_period_expires_at=None`
(`app_store.py:147`) because a signed transaction carries no renewal payload. So whenever
a webhook has already recorded `stored.status = grace_period` — a normal state during a
billing hiccup — an Apple restore takes the grace branch, reads `None`, and answers 404
`restore_not_found`. The Google path is unaffected, because `read_for_restore` populates
the window from `lineItems[0].expiryTime` (`google_play.py:296`). The asymmetry is the
tell.

Spec `10-restore-subscription.md` step 11 states that `active` and `grace_period` are
both product-entitled and that restore should proceed, so this is a deviation.

**This behaviour is deliberate and tested** —
`tests/e2e/test_restore_subscription.py:323` is
`test_a_stored_grace_row_and_an_apple_proof_attaches_nothing`. It is raised here anyway
because the user-visible outcome is a paying subscriber in grace being told they have no
subscription on a new device.

**Fix — needs a decision, not a blind edit.** `core.subscriptions` has no term columns, so
the end date genuinely cannot come from stored state, and falling back to
`proof.expires_at` does not help (in grace the paid term has already lapsed, so the guard
at line 65 still rejects). The two real options are:

1. Add a single App Store Server API `Get All Subscription Statuses` read on the Apple
   restore path, mirroring what `read_for_restore` already does for Play. This is the
   option that matches the spec and the Google path.
2. Accept the limitation explicitly: state it in the `restore()` docstring and in the
   route `description=` so the client can render an accurate message, rather than leaving
   it visible only in an e2e test name.

---

### WR-03: Three failure paths answer 500 with no log line naming them

**File:** `src/nativespeaker/api/auth/google_play.py:168`,
`src/nativespeaker/api/auth/google_play.py:222`,
`src/nativespeaker/api/auth/app_store.py:108`

**Issue:** `InternalError` sets `log_level = None` (`src/nativespeaker/api/errors.py:142`),
so `app_error_handler` writes nothing for it. That is correct for the generic 500 because
every meaningful subclass overrides the level and every other raise site logs first
(`services/subscriptions.py:39`, `services/subscriptions.py:150`,
`services/restore.py:193`). These three do not:

- `google_play.py:168` — every Play read answer that is neither 2xx nor 404/410 (401, 403,
  429, 500) raises a bare `InternalError`. This is precisely the misconfiguration
  `.env.example:133-138` warns is invisible from the outside.
- `google_play.py:222` — a transport failure on the RTDN read raises `InternalError from failure`
  with the cause discarded.
- `app_store.py:108` — a subscription payload whose `data.status` is outside Apple's own
  enum raises a bare `InternalError`; the comment claims "Apple retries and it is visible",
  but nothing makes it visible.

The only trace is the middleware access line (`status_code=500`), which names no cause.
This also breaks the `SHARED-INVARIANTS.md` rule that a rejection leaves exactly one
structured log line carrying its stable internal result.

**Fix:** Log the closed-set label before each raise, matching the existing style. Note
that `app_store.py` deliberately holds no logger (attribution tokens flow through it), so
raise a logging subclass there rather than importing a logger into that module.

```python
# google_play.py, in _play_answer_is_usable
    logger.error("google_play_read_refused", status_code=response.status_code)
    raise InternalError

# google_play.py, in read()
        except httpx.HTTPError as failure:
            logger.error("google_play_read_transport_failed", failure=type(failure).__name__)
            raise InternalError from failure
```

```python
# errors.py — a named class, so app_store.py needs no logger of its own
class UnknownStoreSubscriptionStatus(InternalError):
    """A verified store payload whose status is outside the provider's own enum."""
    log_level = logging.ERROR

    def __init__(self, provider: PurchaseProvider) -> None:
        self.provider = provider
        super().__init__(f"{provider.value} reported a status outside its own enum")

    def log_fields(self) -> dict[str, str | None]:
        return {"provider": str(self.provider)}
```

and at `app_store.py:108`: `raise UnknownStoreSubscriptionStatus(PurchaseProvider.apple)`.

---

### WR-04: The LLM burst limit keys on a forbidden, never-populated, client-forgeable header

**File:** `k8s/templates/security-policy.yaml:21-24`,
`k8s/templates/backend-traffic-policy.yaml:13-40`, `k8s/values.yaml:47-57`

**Issue:** Three problems in one policy:

1. `SecurityPolicy` declares `claimToHeaders: [{claim: plan, header: x-user-plan}]`.
   `SHARED-INVARIANTS.md` forbids this outright: *"the gateway forwards `Authorization`
   unchanged, **injects no identity headers**, and the backend ignores every
   client/proxy identity header"*, and the global-deletions section says *"No
   claim-header authentication or header-derived identity"*. The backend reads
   `x-user-plan` nowhere, so it is also dead.
2. Nothing in this codebase ever sets a `plan` custom claim on a Firebase ID token
   (`grep -rn "plan" src/` finds none), so the claim is always absent, the header is
   never written from the token, and no `clientSelector` matches. The local rate limit on
   `POST /chats` therefore never fires.
3. Because Envoy only overwrites the header when the claim is present, a client-supplied
   `x-user-plan: platinum` survives to the selector, and a client that omits the header
   matches no rule at all — i.e. the caller chooses their own bucket, or none.

The tier names (`free`/`silver`/`gold`/`platinum`) also have no counterpart in the
entitlement model this milestone built (`anonymous`/`registered`/`paid`, seeded at
`migrations/20260818_01_initial-release.sql:123-126`), so even if the claim existed the
buckets would not line up.

Impact is bounded — `QuotaService.charge` still caps monthly consumption per grant, and
`LLMExecutionGate` caps in-flight work — so this is burst shaping that does not shape,
not an unbounded-spend hole. That is why it is a warning and not a blocker.

**Fix:** Remove `claimToHeaders` from `security-policy.yaml` (the invariant forbids it,
and nothing reads it), and re-key the `BackendTrafficPolicy` on a value the gateway
controls rather than one the client can send:

```yaml
# backend-traffic-policy.yaml
  rateLimit:
    local:
      rules:
      # No clientSelectors: one bucket per source address, which Envoy resolves from the
      # trusted proxy chain and no client header can influence.
      - limit:
          requests: {{ .Values.rateLimits.burst.perClient }}
          unit: {{ .Values.rateLimits.burst.unit }}
```

and collapse `values.yaml rateLimits.burst.*` to the single value that is actually used.

---

### WR-05: The gateway 429 body names the wrong error class and carries no `Retry-After`

**File:** `k8s/templates/backend-traffic-policy.yaml:42-51`

**Issue:** The `responseOverride` for status 429 returns `{"code":"quota_exceeded"}`.
That code is the registered specialization for the in-app monthly allowance
(`src/nativespeaker/api/errors.py:195-198`, raised only by `QuotaService.charge`), and it
tells the client "your monthly allowance is spent" — a terminal condition the client
should not retry. A gateway burst rejection is the opposite: retry in a moment.

`SHARED-INVARIANTS.md` names the correct class: *"`rate_limited`, the foundation-registered
429 class, except where a registered specialization applies"*, and requires
`Retry-After` where computable. A local rate limit's window is known, so it is computable.

**Fix:**

```yaml
  responseOverride:
  - match:
      statusCodes:
      - type: Value
        value: 429
    response:
      contentType: application/json
      body:
        type: Inline
        inline: '{"code":"rate_limited"}'
```

and add the `Retry-After` header for the configured window via a `ResponseHeaderModifier`
filter on the llm-routes rule.

---

### WR-06: Lint and type-check tooling ships as runtime dependencies

**File:** `pyproject.toml:20-21`

**Issue:** `ruff==0.15.7` and `ty==0.0.24` are listed under `[project].dependencies`, not
under `[dependency-groups].dev` (where they also appear, at lines 37-38). Anything
installing this package for production — the container image included — pulls both
linters in. That is dead weight in the image and unnecessary supply-chain surface for a
service that never invokes either at runtime.

**Fix:** Delete lines 20-21 from `[project].dependencies`. The `dev` group already
declares both.

---

### WR-07: A test-only Firebase secret is a required boot parameter and is not redacted

**File:** `src/nativespeaker/api/config.py:63`

**Issue:** `JWTConfig.api_key: str` has no default, so `JWT_API_KEY` must be present or
the pod fails to boot. Its only reader is the e2e harness
(`tests/e2e/conftest.py:64`, `:102`, `:135`, `:144`, `:151`), which uses it to mint tokens
against Google's Identity Toolkit REST API. No production code path reads it.

Two consequences: every production deployment must carry a credential it never uses, and
the field is typed `str` rather than `SecretStr` — unlike `DatabaseConfig.password` at
`config.py:34` — so it renders in plain text in any `repr(config)` or model dump.
`hide_input_in_errors=True` covers validation errors but not those.

**Fix:**

```python
class JWTConfig(BaseModel):
    project_id: str = Field(description="GCP project ID")
    # Optional and secret: read only by the e2e harness to mint tokens, never by a request path.
    api_key: SecretStr | None = Field(default=None, description="GCP API key, e2e harness only")
```

and update `tests/e2e/conftest.py` to call `.get_secret_value()`. The existing assertion
at `tests/e2e/conftest.py:65` already fails loudly when it is absent, which is the right
place for the requirement to live.

---

### WR-08: `violation.orig` is dereferenced without a null check in eight places

**File:** `src/nativespeaker/api/crud/grants.py:191`, `:249`, `:278`;
`src/nativespeaker/api/crud/subscriptions.py:116`, `:223`, `:249`, `:296`, `:326`

**Issue:** Each unique-violation arm reads `violation.orig.sqlstate`. SQLAlchemy types
`IntegrityError.orig` as `BaseException | None`, and `ty` reports all eight
(`unresolved-attribute: Object of type BaseException | None has no attribute sqlstate`).
When `orig` is `None` — an `IntegrityError` raised by SQLAlchemy itself rather than
wrapped from the DBAPI — the expression raises `AttributeError` *inside an except block*,
which then escapes the race-detection logic entirely. Instead of the intended
`lost_race` or the intended re-raise, the caller gets an unclassified 500 and the
`_settle` rollback never runs, leaving the session in a failed state for the request's
remaining work.

`sqlstate` is also asyncpg-specific; a psycopg-backed driver exposes `pgcode`.

**Fix:** Add one shared helper and use it at all eight sites.

```python
# src/nativespeaker/api/crud/__init__.py (or a small shared module)
UNIQUE_VIOLATION = "23505"


def is_unique_violation(violation: IntegrityError) -> bool:
    """Whether this IntegrityError is the unique-index arbiter speaking, read fail-closed."""
    # `orig` is Optional and driver-specific, so an absent or unrecognised code is not a race.
    return getattr(violation.orig, "sqlstate", None) == UNIQUE_VIOLATION
```

```python
        except IntegrityError as violation:
            if not is_unique_violation(violation):
                raise
            return ActivationOutcome.lost_race
```

---

### WR-09: A missing usage row on the grant conversion silently mints a fresh allowance

**File:** `src/nativespeaker/api/crud/grants.py:239`, `:262-267`

**Issue:** The anonymous → registered conversion carries the superseded grant's counters
forward:

```python
carried = locked_usage.get(superseded.id) if superseded is not None else None
...
self.session.add(UserMonthlyUsage(
    grant_id=activated.id,
    monthly_period=evaluated_at.strftime("%Y-%m") if carried is None else carried.monthly_period,
    monthly_used=0 if carried is None else carried.monthly_used,
```

`locked_usage[grant.id]` is whatever `lock_usage` returned, which is `None` when the
usage row is missing (`grants.py:207-209`). So a *superseded grant with no usage row*
takes the `carried is None` branch and the new grant is minted with `monthly_used=0` —
exactly the "lazily minted allowance" that `SHARED-INVARIANTS.md` forbids
(*"A missing usage row for an existing grant fails closed — never lazily minted"*) and
that `MissingUsageRowError` exists to catch (`errors.py:220-227`, honoured by
`SyncService.read_entitlement` and `QuotaService.charge`). Here the same broken invariant
is silently repaired into a free allowance.

The `carried is None` branch is only correct for the *no superseded grant* case, which
the code cannot currently distinguish from the *superseded grant with no usage row* case.

**Fix:** Separate the two.

```python
        carried = None
        if superseded is not None:
            carried = locked_usage.get(superseded.id)
            if carried is None:
                # Fail closed, never mint: a grant without a usage row is a failed write,
                # and reading it as a fresh allowance hands out free credits.
                raise MissingUsageRowError(superseded.id)
```

(`MissingUsageRowError` is already imported into this layer's callers; add it to the
`nativespeaker.api.errors` import at `grants.py:12`.)

## Info

### IN-01: Redundant branch in the transient-error classifier

**File:** `src/nativespeaker/api/resilience.py:30-36`
**Issue:** The `isinstance(exc, APIStatusError)` arm extracts a status code and compares it
against a set, and lines 34-36 immediately repeat the identical extraction and comparison
unconditionally. The first arm can never change the outcome.
**Fix:** Delete lines 30-33; keep the unconditional check.

### IN-02: Dead configuration surfaces

**File:** `src/nativespeaker/api/config.py:131`, `k8s/values.yaml:53-57`
**Issue:** `AppConfig.json_log_path` is declared but `setup_logging` (`logs.py:17-53`)
never reads it — the only handler is a `StreamHandler` on stderr. `values.yaml`
`rateLimits.monthly.*` is referenced by no template.
**Fix:** Delete both, or wire `json_log_path` into `setup_logging` if JSON file output is
still wanted.

### IN-03: `Chat.id` has no default factory and uses uuid4 while every sibling uses uuid7

**File:** `src/nativespeaker/api/tables/chats.py:38`
**Issue:** `id: UUID = Field(primary_key=True)` with no `default_factory`, unlike
`Message`, `User`, `ExternalIdentity`, `AccessGrant`, `Subscription` and the rest, which
all use `default_factory=uuid7`. The single construction site
(`services/chats.py:89`) passes `id=uuid4()` explicitly; any future `Chat()` without an
explicit id becomes a NOT NULL violation at flush rather than a type error.
**Fix:** `id: UUID = Field(default_factory=uuid7, primary_key=True)` and drop the explicit
`id=uuid4()` at `services/chats.py:89`.

### IN-04: Two dependencies read the clock directly instead of using `get_evaluated_at`

**File:** `src/nativespeaker/api/routers/auth.py:56`,
`src/nativespeaker/api/app/dependencies.py:107`
**Issue:** `get_evaluated_at` exists precisely so one instant is shared per request by
construction (`dependencies.py:127-130`), and every other service dependency takes it.
`issue_challenge` and `get_chat_service` call `datetime.now(UTC)` themselves. Harmless
today because neither request combines the two sources, but it defeats the guarantee the
accessor was added for.
**Fix:** Take `evaluated_at: datetime = Depends(get_evaluated_at)` in both.

### IN-05: `assert` used for a runtime invariant in two request paths

**File:** `src/nativespeaker/api/app/error_handlers.py:35`, `:51`, `:62`;
`src/nativespeaker/api/routers/auth.py:212`
**Issue:** Under `python -O` these are stripped, and the following line dereferences the
value the assert was guarding (`row.id`, `exc.errors()`). It would surface as a 500 rather
than the intended answer.
**Fix:** Either document that `-O` is never used, or narrow with an explicit raise:
`if row is None: raise IdentityUnresolvable`.

### IN-06: A malformed Play 2xx body escapes `read_for_restore` as a 500

**File:** `src/nativespeaker/api/auth/google_play.py:279`
**Issue:** `PlaySubscription.model_validate(response.json())` can raise `ValueError`
(undecodable body) or `pydantic.ValidationError` (unexpected shape). Every other failure
in this method is classified into `Unavailable` (503) or `ProofRejected` (403); these two
fall through to the generic handler as `internal_error` (500). The method's docstring
promises "the value type, or the refusal it earned".
**Fix:** Wrap the parse and raise `Unavailable(stage=RESTORE_READ_STAGE)`.

### IN-07: The unknown-`kid` negative cache keys off a PyJWT message substring

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:35`, `:163`
**Issue:** `_DEFINITIVE_KID_MISS = "Unable to find a signing key that matches"` is matched
against `str(exc)`. A PyJWT wording change silently disables the negative cache — the
verifier stays correct but refetches the JWKS for every bogus `kid`, which is the DoS
vector the cache exists to close.
**Fix:** Pin the PyJWT minor version, or add a unit test that asserts the current PyJWT
raises a `PyJWKClientError` whose message still contains the sentinel.

### IN-08: 47 `ty` diagnostics in `src/`, dominated by optional-member access on `Identity`

**File:** across `src/`; run `uv run ty check src`
**Issue:** 22 of them are `Attribute 'id' is not defined on None in union 'User | None'`
(`identity.user.id`) and 8 more are the `violation.orig.sqlstate` cluster covered by
WR-08. The `identity.user` / `identity.identity` accesses are safe at runtime because
`IdentitiesDB.resolve` sets both together or neither (`crud/identities.py:41`, `:53`) and
`get_linked_identity` admits only the linked case — but the type checker cannot see it,
so a genuine future violation would be lost in the noise.
**Fix:** Add a narrow accessor that carries the guarantee in the type, e.g. a
`LinkedIdentity` dataclass with non-optional `user` and `identity` returned by
`get_linked_identity`, so handlers stop dereferencing `Identity | None` members.

---

_Reviewed: 2026-09-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
