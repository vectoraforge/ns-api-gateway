---
phase: 42-post-auth-claim-registered-grant
reviewed: 2026-09-10T03:01:16Z
depth: standard
files_reviewed: 142
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
  - src/nativespeaker/api/crud/__init__.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/crud/violations.py
  - src/nativespeaker/api/errors.py
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
  - src/nativespeaker/api/tables/chats.py
  - src/nativespeaker/api/tables/grants.py
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
  critical: 0
  warning: 40
  info: 60
  total: 100
status: issues_found
---

# Phase 42: Code Review Report

**Reviewed:** 2026-09-10T03:01:16Z
**Depth:** standard
**Files Reviewed:** 142
**Status:** issues_found

## Summary

Incremental re-review of phase 42 (post-auth claim-registered-grant). The scope is every file changed since the previous 42-REVIEW.md commit (`e422395`), computed by the three-tier scoping in the code-review workflow: the changed 42-07-SUMMARY.md supplied 11 files and the git-diff cross-check added the rest, giving 142 files across infrastructure, the `src/nativespeaker/api` package, and all three test suites.

One reviewer could not read 40,781 lines at standard depth. The identical scope was therefore split by module across eight parallel `gsd-code-reviewer` agents with disjoint finding-ID blocks, then merged here. The scope was not narrowed. The partition was verified disjoint and lossless against the computed scope, and the merged finding IDs were verified free of collisions.

No Critical finding survived verification. The phase-42 core is sound. The D-09 destination ladder is implemented in the ratified order in both the preflight and the locked writer. The DeviceCheck bit1 read and write pairing is load-bearing, proven by mutation. The grant-tier-then-usage-tier lock order holds across all four writers with no cycle. The SQLAlchemy tables mirror `migrations/20260818_01_initial-release.sql` exactly. The SQLSTATE that the writers key on is correct. The refusal vocabulary is the single 403 `operation_not_allowed` that the ratified decisions require.

Reviewers dropped many candidate findings that contradicted ratified decisions. The decisions cited most were 42-D-02, D-05, D-06, D-09 and D-16 in `42-CONTEXT.md`, and Phase 35 D-05. Where a spec and the code diverge because a decision settled the point, the reviewers recorded a flagged conflict and not a defect.

The 40 warnings fall into three groups. The first group is adapter-layer failure classification: a case-sensitivity mismatch in the DeviceCheck body matcher, and a hoisted-guard gap in the Google Play read. Each can turn a recoverable condition into a silent permanent failure. The second group is two service-layer defects: a lost-race settle in `services/auth.py` that decides the outcome from the existence of an effective grant instead of its source, and a lock held across response transmission in `services/subscriptions.py`. The third and largest group is guard holes in the test suites. Almost all were proven by mutation probes that were reverted in the same tool call. Several tests stay green while the behaviour they claim to pin is deleted or inverted. These are test-reliability defects, not style, and they are what makes the remaining source risk hard to see.

## Warnings

### WR-01: `container.port` is a knob that silently breaks the deployment — the image hardcodes `--port 8000`

**File:** `k8s/values.yaml:21-22` (also `Dockerfile:42`, `k8s/templates/deployment.yaml:47`)

**Issue:** `values.yaml:33-34` claims "both probes dial the container port by its name `http`, so `container.port` is the one place the port is set and moving it cannot leave a probe on the old number." The premise is false. `deployment.yaml:47` renders `containerPort: {{ .Values.container.port }}`, but the process is started by the image's own `CMD ["uvicorn", ..., "--port", "8000"]` (`Dockerfile:42`), which the chart never overrides with `command:`/`args:`. Setting `--set container.port=9000` therefore renders a pod whose `containerPort` (and, through `targetPort: http` in `service.yaml:12`, the Service and both probes) points at 9000 while uvicorn still listens on 8000. Every probe fails, the pod never becomes Ready, and the only symptom is `connection refused` on a port nothing was ever asked to serve. The comment actively encourages an operator to move it.

**Fix:** Make the value load-bearing rather than decorative — pass it to uvicorn in `deployment.yaml`, next to the `ports:` block:

```yaml
        args: ["--host", "0.0.0.0", "--port", "{{ .Values.container.port }}"]
        ports:
        - name: http
          containerPort: {{ .Values.container.port }}
```

(`args` alone is enough: it replaces the image `CMD` while keeping the `ENTRYPOINT`-less `CMD ["uvicorn", ...]`, so also move `uvicorn`/`nativespeaker.api.app.main:app` into `args`, or set `ENTRYPOINT ["uvicorn", "nativespeaker.api.app.main:app"]` in the `Dockerfile` and keep `args` as the flags.) If that is not wanted, delete `container:` from `values.yaml` and hardcode `containerPort: 8000` in the template, and delete the comment at `values.yaml:33-34`.

### WR-02: Deployer-tunable values are pinned in the tracked `config.yaml`, where no deployment can override them

**File:** `config/config.yaml:1-4, 5-13, 17-18`

**Issue:** `config.yaml:21-24` states its own rule — "A value declared here outranks the environment... Add a key here only when it must NOT vary per deployment" — and Phase 44 D-16 ratified exactly that rule ("the three deployer values stay in the environment, because `init_settings` outranks `env_settings` and a deployer value written into the tracked file could never be overridden"; `.planning/REQUIREMENTS.md:400`). Three blocks in this file break it:

- `db.pool_size: 12` (line 18) — consumed at `app/lifespan.py:118` as SQLAlchemy `pool_size` with `max_overflow=0`. Connections held is `replicaCount × 12`. When Postgres `max_connections` is reached there is no lever: `DB_POOL_SIZE` is outranked by this file, and `k8s/values.yaml:89-94` states plainly that a setting declared here "cannot be overridden" through the chart's `env:` list.
- `model.name` / `model.temperature` / `model.max_tokens` (lines 1-4) — switching model during an OpenAI incident is a deployer decision and now requires an image rebuild and redeploy.
- `resilience.*` (lines 5-13) — `pool_size`/`queue_size` are the in-flight and queue caps (`resilience.py:154-155`) and `circuit_breaker_*` the outage policy; all are capacity settings that vary between a one-replica staging install and production.

The chart offers no ConfigMap mount either, so `CONFIG_DIR` cannot be redirected at a different config tree. `LOG_LEVEL` is genuinely the only lever the deployment has.

**Fix:** Delete the `model:`, `resilience:` and `db:` blocks from `config/config.yaml` and let `config.py`'s field defaults stand (they already match the values here except `db.pool_size`, whose default is 5 — set `MODEL_NAME`, `RESILIENCE_POOL_SIZE`, `DB_POOL_SIZE` etc. from the chart's `env:` list or the credentials Secret where a deployment needs a non-default). Keep in this file only what must not vary: `app_store.products`, `google_play.products`, `chats_limit`, `messages_limit`, `jwt.jwks_cache_ttl_seconds`.

### WR-03: `AGENTS.md` sends a new exception handler to the wrong module

**File:** `AGENTS.md:52-54` (also `AGENTS.md:29-37`)

**Issue:** Package-layout exception 1 reads "`errors.py` owns the client-visible error response shape, the statuses, the copy **and the handlers**." It does not. `src/nativespeaker/api/errors.py` contains only `ErrorResponse`, `AppError` and its subclasses; every exception handler and the `register_exception_handlers` registration live in `src/nativespeaker/api/app/error_handlers.py:33-91`, which `app/main.py:6,54` imports. A developer following this binding instruction file adds a handler to `errors.py`, where nothing registers it, and the exception falls through to `generic_error_handler` as a 500 — a silent behaviour change with no import error to catch it.

Relatedly, the section opens with "Every file has exactly one home" and then enumerates six packages, omitting `app/` (`dependencies.py`, `error_handlers.py`, `lifespan.py`, `main.py`) and top-level `logs.py` entirely, so those files have no stated home at all.

**Fix:** Amend `AGENTS.md:52-54` to split the two owners, and add `app/` to the package list:

```markdown
1. `errors.py` owns the client-visible error response shape, the statuses and the
   copy; `app/error_handlers.py` owns the handlers and their registration.
   Nothing about errors moves to `schemas/`. Ground: `SHARED-INVARIANTS.md`
   § Errors — one shared registry.
```

```markdown
- `app/` — process wiring: `main.py`, `lifespan.py`, `dependencies.py`,
  `error_handlers.py`.
```

### WR-20: The never-set DeviceCheck body is matched case-sensitively while the sibling classifier on the same response casefolds

**File:** `src/nativespeaker/api/auth/devicecheck.py:142`

**Issue:**

```python
_NEVER_SET_BODIES = frozenset({"Failed to find bit state", "Bit State Not Found"})   # :36
...
if _DEVICE_TOKEN_FAULT in response.text.casefold():                                   # :127
...
body = response.text.strip()                                                          # :141
if body in _NEVER_SET_BODIES and response.status_code // 100 != 5:                     # :142
    return BitState(bit0=False, bit1=False)
```

Two classifiers read the same `httpx.Response` body and disagree on case. `_DEVICE_TOKEN_FAULT`
is matched against `response.text.casefold()` at :127 — deliberately tolerant, because :41-43
records that these literals are `[ASSUMED]` from secondary sources. `_NEVER_SET_BODIES` is matched
by exact-case set membership at :142 — intolerant, on literals carrying the *same* `[ASSUMED]`
provenance and, per :42, the higher consequence.

Trace what a single case drift costs. Apple answers `200` with `failed to find bit state`:
:142 misses, `_reject_or_retry` sees a 2xx and returns, `_decoded` calls `.json()` on plain text
and answers `None` (:151), and :153 raises `RetryableDeviceCheckError("unrecognised body")`. Three
attempts later `_read_exhausted` raises `Unavailable(stage="devicecheck_read")` — HTTP 503
`verification_temporarily_unavailable`. The never-set state is the *only* state the anonymous
grant is issued for, so the failure is not partial: **every first-ever device claim answers 503,
permanently, with no log line naming the cause** (this module holds no logger by design, :2). The
comment at :144-146 states that this exact outcome already happened once and that ordering was
changed to prevent it; the case asymmetry reopens the same hole through a different door.

**Fix:** Casefold both sides, as the sibling classifier already does.

```python
# Casefolded like `_DEVICE_TOKEN_FAULT` at :127: both literal sets are [ASSUMED] from secondary
# sources (41-RESEARCH.md A3), so neither may turn on Apple's choice of capitalisation.
_NEVER_SET_BODIES = frozenset({"failed to find bit state", "bit state not found"})
...
body = response.text.strip().casefold()
```

### WR-21: `get_devicecheck_adapter` is unannotated, so `DeviceCheckAdapter` binds at no seam the wiring passes through

**File:** `src/nativespeaker/api/app/dependencies.py:151`

**Issue:**

```python
def get_devicecheck_adapter(request: Request):
    """The device-gate seam the lifespan built, deliberately unannotated."""
    return request.app.state.devicecheck_adapter
```

The docstring says "deliberately" and then names no reason, and the decision contradicts the rule
this repo states twice for the identical situation:

- `devicecheck.py:216-217` — *"Annotated with the Protocol both consume: unannotated, the one
  declaration that would catch a wrong-shaped double or a renamed method caught nothing at all."*
- `google_play.py:223-224` — *"a Protocol nothing is typed against catches no wrong-shaped double
  at all."*

The sibling accessor two lines above (`get_firebase_adapter`, :145) *is* annotated with its
Protocol. Downstream, `get_auth_service(..., devicecheck=Depends(get_devicecheck_adapter))` (:159)
is unannotated too and `AuthService.__init__(..., devicecheck)` (`services/auth.py:70`) is
unannotated as well, so the value flows from `app.state` to `read_bits_with_retry` /
`write_bits_with_retry` with **no** declaration binding `DeviceCheckAdapter` anywhere on the
wiring path. The two retry helpers annotate their `adapter` parameter, but they are called with
`self.devicecheck` — an unannotated attribute — so a checker has nothing to compare.

There is no technical obstacle: `AppleDeviceCheck` satisfies the Protocol (verified —
`typing.get_protocol_members(DeviceCheckAdapter) <= set(dir(AppleDeviceCheck))` is `True`), and
importing `DeviceCheckAdapter` into `dependencies.py` creates no cycle (verified by import).

**Fix:**

```python
from nativespeaker.api.auth.devicecheck import DeviceCheckAdapter
...
def get_devicecheck_adapter(request: Request) -> DeviceCheckAdapter:
    """The device-gate seam the lifespan built, declared like its Firebase sibling above."""
    return request.app.state.devicecheck_adapter
```

and annotate `devicecheck: DeviceCheckAdapter` on `get_auth_service` (:159).

### WR-22: `VerifiedClaims.payload` carries the whole verified JWT and no production code ever reads it

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:254`

**Issue:**

```python
    payload: dict | None = None        # :76
...
        return VerifiedClaims(issuer=claims.issuer, subject=claims.subject, payload=payload), None
```

`.payload` has exactly one reader in the whole tree, and it is a test asserting the field is
`None` on the *other* branch (`tests/unit/test_jwt_security.py:218`). No production caller reads
it: `dependencies.get_identity` (:82-93) uses `claims.issuer` and `claims.subject` only, and
`PubSubPushTokens.verify` (`google_play.py:228-236`) reads nothing but `claims is None`.

The branch that populates it is the required-claims branch — the push-token verifier — so the
value attached is a Google service-account ID token payload (`email`, `sub`, `azp`, `aud`, the
raw `exp`/`iat`). This module's whole discipline is that credential material never travels further
than it must: `verify` deliberately narrows to two strings (:71-73, *"Exactly the verified `iss`
and `sub`"*), and `VerificationResult` is documented as never client-visible (:79). A dead field
that re-widens the value type to the full claim set is the one thing that makes the narrowing
untrue, and it will be read by the next caller who finds it there.

**Fix:** Delete the field and the branch that fills it.

```python
@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub`, never reconstructed from transport metadata."""
    issuer: str
    subject: str
```

and at :251-254:

```python
        return claims_from_payload(payload)
```

If a future caller genuinely needs a pinned claim, return that claim, not the payload.

### WR-23: The `exc_info` decision reads the unclamped log level the line above it just clamped

**File:** `src/nativespeaker/api/app/error_handlers.py:45`

**Issue:**

```python
level = exc.log_level if exc.log_level in _LOGGABLE else logging.ERROR      # :38
record = getattr(logger, logging.getLevelName(level).lower())               # :39
record(camel_to_snake(type(exc).__name__),
       exc_info=exc if exc.log_level >= logging.ERROR else False, **exc.log_fields())   # :45
```

Line 38 exists precisely because `exc.log_level` may be a value outside the five standard levels
(structlog's filtering logger indexes only those and raises otherwise). Line 45 then throws that
clamp away and re-reads the raw attribute. For any non-standard level below 40 — `logging.INFO + 5`,
a `25` borrowed from a house convention — the record is *emitted at ERROR* (from `level`) but
carries `exc_info=False` (from `exc.log_level`): the highest-severity line this handler writes,
with the traceback deliberately stripped. That is the one combination the guard was added to
prevent, and it is silent — nothing reports the disagreement.

No class in `errors.py` declares such a level today, so this is latent rather than live; it is a
defect in the guard itself, which is only ever exercised by exactly the values that trip it.

**Fix:** Decide once, from the clamped value.

```python
level = exc.log_level if exc.log_level in _LOGGABLE else logging.ERROR
record = getattr(logger, logging.getLevelName(level).lower())
record(camel_to_snake(type(exc).__name__),
       # `level`, never `exc.log_level`: the clamp above is the level this record is written at,
       # so it is also the level the traceback decision has to be made against.
       exc_info=exc if level >= logging.ERROR else False, **exc.log_fields())
```

### WR-24: A transient ADC failure at pod start disables account creation for the life of the process, behind a warning that promises recovery

**File:** `src/nativespeaker/api/auth/firebase.py:61`

**Issue:**

```python
    try:
        google.auth.default()
    except google.auth.exceptions.GoogleAuthError:
        # ... also raises `RefreshError` and `TransportError` when the metadata server answers but
        # answers badly, a routine transient at pod start. ...
        return None
```

The comment names the failure correctly — *"a routine transient at pod start"* — and then converts
it into a permanent state. `build_admin_apps` runs exactly once, from `lifespan.py:155`, and
returns `{}`; `FirebaseAdminLookup._apps` is empty for the process's whole life; every
`get_user_provider_data` answers `Unavailable(stage="issuer_selection")` (`firebase.py:81-83`) —
HTTP 503 on every account-creation and upgrade route until someone restarts the pod. `_play_credential`
(`lifespan.py:124-132`) has the identical shape for the Play read.

Two things make this worse than a degraded mode:

1. **Nothing withdraws the pod from service.** `GET /health/ready` (`routers/health.py:7-11`)
   answers `200 {"status": "up"}` unconditionally, so Kubernetes marks the pod Ready and routes
   traffic to a replica that provably cannot serve. A crashloop, by contrast, is the recovery
   Kubernetes already implements for a transient — restart with backoff — and it is visible.
2. **The log line states the opposite of what the code does.** `lifespan.py:44-46` records
   `consequence="user creation fails closed as verification_temporarily_unavailable **until**
   Application Default Credentials are available in this environment"`. They will become available
   — the metadata server recovers in seconds — and this process will never notice, because the
   only read happened at boot. An operator reading that line waits for a recovery that cannot
   arrive. (`devicecheck_credential_absent`, `app_store_configuration_absent` and
   `google_play_configuration_absent` at `lifespan.py:160-189` carry the same "until ..." wording
   over the same boot-once reads.)

Phase 41 WR-03 addressed the *misconfiguration* case (`GOOGLE_APPLICATION_CREDENTIALS` copied from
`.env.example`) by changing `.env.example`; it did not address the transient, which is the case
this comment itself names.

**Fix:** Split the two outcomes the one `except` currently fuses — absence is permanent and
degrades, a transport/refresh failure is transient and must not be latched.

```python
    try:
        google.auth.default()
    except google.auth.exceptions.DefaultCredentialsError:
        # No credential in this environment at all: a real deployment state, degraded on purpose.
        return None
    except (google.auth.exceptions.RefreshError,
            google.auth.exceptions.TransportError) as failure:
        # A blip at pod start is transient, and latching it here would leave a Ready pod that can
        # never create a user. Kubernetes' restart backoff is the recovery for a transient.
        raise RuntimeError(f"Application Default Credentials unavailable at boot: "
                           f"{type(failure).__name__}") from failure
```

Apply the same split in `lifespan._play_credential`, and drop the word "until" from the four
`consequence=` strings that a boot-once read cannot honour.

### WR-25: Only half of the path-segment guard was hoisted into `read`, so a dot-only package name silently acknowledges every RTDN

**File:** `src/nativespeaker/api/auth/google_play.py:259`

**Issue:** `read` guards one of the two values it puts in the URL path:

```python
        if not _names_one_path_segment(purchase_token):
            # The same guard `read_for_restore` applies to the same value, hoisted because both
            # entry points reach the same `_get`. `quote` leaves a dot unescaped and httpx removes
            # a dot segment, so `..` addresses a different Play URL and `` addresses the collection.
```

The comment's stated reason — *"both entry points reach the same `_get`"* — applies equally to
`package_name`, and `read_for_restore` guards it (`:317-319`), but `read` does not. `_get`
(`:390-393`) interpolates both values into `PLAY_URL` through `quote(..., safe="")`, which by the
comment's own reasoning leaves `.` unescaped.

The reachable failure is a one-character configuration typo. Set `google_play.package_name` to
`"."` or `".."`: `verify_google_play_notification` (`dependencies.py:217-221`) compares the RTDN's
`packageName` against it and only forwards a delivery that *equals* it, so the value reaching
`read` is the bad one. httpx then removes the dot segment, the request lands on a URL that names
no application, Google answers 404, `_play_answer_is_usable` (`:197-200`) classifies it as
`_GONE_STATUSES`, and `read` returns `None`. The route acknowledges 200. **Every Play subscription
notification is discarded, permanently and irrecoverably** — Pub/Sub will not redeliver an
acknowledged message — and the only trace is `google_play_purchase_token_gone`, which accuses the
buyer's token rather than the deployment. `read_for_restore` refuses the same configuration loudly
with `Unavailable(stage=RESTORE_PACKAGE_STAGE)`; the webhook, which is the path where the loss is
permanent, does not.

**Fix:** Hoist the other half of the guard, matching `read_for_restore`'s classification of it as
a deployment fault rather than a payload fault.

```python
        if not package_name or not _names_one_path_segment(package_name):
            # The same guard `read_for_restore` applies at :317: an absent or dot-only application
            # name addresses a different Play URL, and acknowledging here would drop the delivery
            # for good. Refused loudly, so Pub/Sub redelivers once the deployment is repaired.
            logger.error("google_play_unusable_package_name")
            raise InternalError
```

### WR-40: The lock-taking readers hand back the identity map's pre-lock snapshot, so "revalidate under the lock" is not delivered

**File:** `src/nativespeaker/api/crud/grants.py:98` (also `:110`, `:116`, `:130`) and `src/nativespeaker/api/crud/subscriptions.py:89`
**Issue:** `lock_effective_grants`, `lock_active_grants`, `lock_active_grants_of` and `lock_usage` all issue `SELECT ... FOR UPDATE` without `execution_options(populate_existing=True)`. The row lock is really taken, but SQLAlchemy discards the freshly fetched column values for any instance already in the session's identity map and returns the instance as the earlier read left it. The sibling `SubscriptionsDB.read_subscription` (`crud/subscriptions.py:109-110`) already carries `populate_existing=True` for exactly this reason and says so in its comment; the lock-taking readers — the ones `SHARED-INVARIANTS.md` § "Locks and transactions" charges with *"re-resolve/revalidate the locked rows inside before writing"* — do not.

Proven, not inferred, against the live PostgreSQL on localhost:5432 (scratch table created and dropped in one command; tree and schema left clean):

```
preflight tier: anonymous
under FOR UPDATE, SQLAlchemy returns tier: anonymous     <- rival's committed value discarded
same instance as preflight: True
with populate_existing: CHANGED_BY_RIVAL
```

There is exactly one reachable path in this build where a grant row is loaded before it is locked in the *same* session: `services/auth.py::_claim_registered_grant` on the **conversion** arm. That arm reads `read_effective_grants` / `read_active_grants` in the preflight (`auth.py:234, 250`) and then, because `held` is non-empty, skips the `await self.session.rollback()` at `auth.py:263` that every other claim arm performs. It goes straight into `activate_registered_account_grant`, whose `lock_active_grants`/`lock_effective_grants` therefore return the preflight instances verbatim. The anonymous claim (`auth.py:199`), the registered new-grant arm (`auth.py:263`) and `QuotaService.charge` (its own short session) are all *accidentally* safe — safe because of a rollback or a fresh session, not because the reader guarantees freshness.

Today the consequence is latent rather than live: the only `AccessGrant` columns read off the locked rows (`id`, `source`, `tier_id`, `ends_at`, `user_id`, `subscription_id`) are never mutated in place while a row stays `status='active'`, and any row whose `status` did change drops out of the `WHERE` (which Postgres evaluates fresh). The defect is that the safety rests on an unstated immutability assumption instead of on the reader, and the two writers that *do* mutate a grant in place (`crud/grants.py:288-290`, `crud/subscriptions.py:337-339`) are one line away from breaking it. `crud/subscriptions.py:89` has the same hole for a two-account restore.

**Fix:** make freshness the reader's job, in `crud/grants.py`, so no caller has to arrange a rollback first:

```python
async def lock_effective_grants(self, user_id: UUID,
                                evaluated_at: datetime) -> list[AccessGrant]:
    """Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."""
    # `populate_existing` for the reason `SubscriptionsDB.read_subscription` gives: without it a
    # row already in the identity map is answered with the values the preflight read saw, so the
    # revalidation under the lock decides on a snapshot a concurrent commit has already replaced.
    statement = (_effective_grants_statement(user_id, evaluated_at)
                 .with_for_update()
                 .execution_options(populate_existing=True))
    return list((await self.session.exec(statement)).all())
```

Apply the identical two-line change to `lock_active_grants` (`:110`), `lock_active_grants_of` (`:116`) and `lock_usage` (`:130`). `read_usage` (`:135`) deserves it too, since `write_subscription_grant` reads `monthly_used` through it (`crud/subscriptions.py:367`) to decide what to carry.

### WR-41: `SubscriptionEvent.notification_uuid` states a schema rule the `tables` package forbids, and the guard test cannot see it

**File:** `src/nativespeaker/api/tables/purchases.py:78`
**Issue:** `notification_uuid: str = Field(unique=True)` compiles to `Column(..., unique=True)`, which SQLAlchemy files as a `UniqueConstraint` on `Table.constraints`. That directly contradicts the package's own stated rule at `tables/__init__.py:1-4` — *"`migrations/` owns every index and every referential action: no field here declares one, so `SQLModel.metadata` never states a second version of the schema that could drift from that file"* — and it is inconsistent with three sibling columns in the same file that carry explicit "Deliberately not `unique=True`" comments (`purchases.py:40`, `:56`, `:95`).

The guard written to catch exactly this, `tests/unit/test_tables_metadata.py::TestTheMetadataDeclaresNoIndex`, walks `table.indexes` only. `Column(unique=True)` without `index=True` never lands there, so the guard passes while the rule is broken. Verified against the live metadata:

```
core.auth_challenges       [(None, ['challenge_id'])]        indexes= set()
core.external_identities   [(None, ['user_id'])]             indexes= set()
audit.subscription_events  [(None, ['notification_uuid'])]   indexes= set()
```

Three metadata-declared uniqueness rules, zero of them visible to the guard. (The other two live in `tables/auth.py` and `tables/identities.py`, outside this slice — the same fix applies there.)

**Fix:** drop the declaration, since the migration's `notification_uuid TEXT NOT NULL UNIQUE` (`migrations/20260818_01_initial-release.sql:208`) plus `_flush_or_lose`'s SQLSTATE check is already the whole arbiter:

```python
    # Deliberately not `unique=True`: the table's rule is the migration's own `NOT NULL UNIQUE`,
    # and `is_unique_violation` is what reads its refusal.
    notification_uuid: str = Field()
```

and widen the guard so the next one is caught:

```python
class TestTheMetadataDeclaresNoUniquenessRule:
    def test_no_mapped_table_declares_one(self):
        declared = sorted(f"{name}.{column.name}"
                          for name, table in TABLES.items()
                          for constraint in table.constraints
                          if isinstance(constraint, UniqueConstraint)
                          for column in constraint.columns)

        assert declared == []
```

### WR-42: The App Store envelope bound turns an oversized notification into a permanently lost lifecycle event

**File:** `src/nativespeaker/api/schemas/webhooks.py:17`
**Issue:** `signedPayload: str = Field(..., min_length=1, max_length=APP_STORE_ENVELOPE_LIMIT)` rejects at the model, so an envelope over 64 KiB never reaches `verify_app_store_notification` (`app/dependencies.py:190-194`) and answers non-2xx through `validation_error_handler` (`app/error_handlers.py:51-62`). Apple retries a notification on non-2xx a bounded number of times and then gives up — and the payload size does not change between retries, so every attempt fails identically and the notification is dropped for good. For a `REVOKE` or `EXPIRED` delivery that means `write_subscription_grant` never runs, and the buyer keeps an `active` `subscription` grant for a subscription the store has withdrawn.

The sibling in the same file was rewritten specifically to avoid this shape: `PubSubPushMessage.data` (`:28-34`) is *"Deliberately unbounded HERE and bounded in `developer_notification_from` instead"*, precisely so that an over-limit body answers 200 and is dropped by the decoder rather than becoming a status the transport keeps retrying. Both routes are provider callbacks with the same problem and now solve it in opposite directions, and only one of the two directions was reasoned about. The bound itself is only ~2.7x the 18-24 KB the module's own comment calls typical, and the chain material it is sized around is the part most likely to grow.

**Fix:** move the size decision behind the transport, symmetric with the Pub/Sub sibling:

```python
class AppStoreNotificationRequest(BaseModel):
    """The App Store notification body: the signed envelope, and nothing else."""
    # Deliberately unbounded HERE and bounded in the verifier instead, for the reason
    # `PubSubPushMessage.data` gives: Apple retries every non-2xx a bounded number of times and
    # then drops the notification, so a body pydantic refuses is a lifecycle event lost for good.
    signedPayload: str = ""
```

and in `app/dependencies.py::verify_app_store_notification`, reject over-limit and empty envelopes there — logging the length from the closed-set label set, never the body — so the route keeps its 200-and-drop contract instead of asking Apple to redeliver something that can never succeed.

### WR-60: A registered claim that loses the one-active-grant index to a *subscription* or *manual* writer answers 200 having granted nothing

**File:** `src/nativespeaker/api/services/auth.py:300-304`
**Issue:** `_settle` decides the loser's answer from the mere *existence* of an effective grant, not from its source:

```python
if outcome is ActivationOutcome.lost_race:
    if await self.grants_db.read_effective_grants(identity.user.id, self.evaluated_at):
        return False          # -> caller commits, router answers 200 + SyncResponse
    raise ClaimRefusedUnderLock(cause="lost_race_without_a_readable_grant")
```

`crud/grants.py:323-330` returns `lost_race` for *any* unique violation on the second flush, and `ix_access_grants_one_active_per_user` (`migrations/20260818_01_initial-release.sql:263-265`, `UNIQUE (user_id) WHERE status='active'`) is arbitrated against every source, not just the free ones. The race is reachable: `_claim_registered_grant` and `SubscriptionsService.ingest` / `RestoreService.restore` both insert an active grant for the same user, and neither locks a row that does not yet exist (`lock_active_grants` on an empty set takes no lock). When the subscription writer commits first, the registered claim's insert raises, `_settle` re-reads and finds the *subscription* grant, returns `False`, and `_claim_registered_grant:279` commits an empty transaction. The route then answers **200** for a state that the deterministic preflight answers **403 `OtherActiveGrantHeld`** three lines earlier (`services/auth.py:243-244`, D-09(b)). The claimed challenge is consumed, so the client must re-prepare to get the correct refusal. The comment on line 302 ("the winner's row is there to read") is only true when the winner wrote *this claim's* grant.

**Fix:** make `_settle` prove the winner is the grant this attempt tried to write. Pass the source down and require it in the re-read:

```python
async def _settle(self, identity: LinkedIdentity, outcome: ActivationOutcome,
                  cause: str | None, *, source: AccessGrantSource) -> bool:
    if outcome is ActivationOutcome.activated:
        return True
    await self.session.rollback()
    if outcome is ActivationOutcome.lost_race:
        held = await self.grants_db.read_effective_grants(identity.user.id, self.evaluated_at)
        if any(grant.source is source for grant in held):
            return False
        raise ClaimRefusedUnderLock(cause="lost_race_without_a_readable_grant")
    raise ClaimRefusedUnderLock(cause=cause)
```

and call it with `source=AccessGrantSource.registered_account_grant` from `_claim_registered_grant:276` and `source=AccessGrantSource.anonymous_device_grant` from `_claim_anonymous_grant:215`.

### WR-61: The replayed store notification returns 200 while still holding the buyer's grant and usage row locks

**File:** `src/nativespeaker/api/services/subscriptions.py:71-73`
**Issue:** `lock_grants(owner)` at line 58-59 takes `FOR UPDATE` on every grant row of the buyer and then on each of their `core.user_monthly_usage` rows (`crud/subscriptions.py:86-97`). The replay branch then returns without committing or rolling back:

```python
if await self.subscriptions_db.read_event(notification.notification_uuid) is not None:
    return
```

`get_db` (`app/dependencies.py:44-55`) rolls back only on an exception; on a normal return the session is closed by the `async with` teardown, and that dependency's own docstring states the teardown runs "only after `await response(...)`". So the locks survive the serialization and transmission of the 200 to Apple/Google. That contradicts SHARED-INVARIANTS' "No provider, store, or other network call may run while any DB lock is held". Every other early exit in this slice is safe: `restore.py:186` rolls back before returning, and the raises at `subscriptions.py:69/105/117` reach `get_db`'s `except`.

**Fix:** release before returning, and preferably ask the replay question before spending the locks at all:

```python
        if await self.subscriptions_db.read_event(notification.notification_uuid) is not None:
            # The replay: nothing to write, so the buyer's locks are given back before answering.
            await self.session.rollback()
            return
```

(Moving the `read_event` call above line 58 removes the lock acquisition entirely for replays; it reads no row the locks protect.)

### WR-62: `GET /examples` rejects a configured language whose example list is empty, while `POST /chats` accepts it

**File:** `src/nativespeaker/api/services/chats.py:172-176`
**Issue:** `supported_languages` is `list(self.examples.keys())` (line 48-49), so `create_chat` accepts any configured key (line 87). `get_examples` instead tests the *value*:

```python
examples = self.examples.get(lang, [])
if not examples:
    raise UnsupportedLanguageError(lang, self.supported_languages)
```

For a configured key mapped to `[]`, `GET /examples?lang=X` answers 400 "not supported" while listing `X` among the supported languages in the same exception, and `POST /chats {"lang": "X"}` succeeds. Two routes disagree on the one membership question, and the disagreement is silent config drift rather than a code error the tests would catch.

**Fix:** test membership, and let an empty list be an empty list:

```python
    def get_examples(self, lang: str) -> ExamplesResponse:
        if lang not in self.examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)
        return ExamplesResponse(lang=lang, examples=self.examples[lang])
```

If an empty entry must stay unreachable, reject it at config load instead, where it is one check for every reader.

### WR-63: `chats_limit` is read, then the transaction is ended and a provider call is made before the insert, so concurrent requests exceed the limit with credits already spent

**File:** `src/nativespeaker/api/services/chats.py:90-109`
**Issue:** the guard and the write are separated by a commit and an LLM round trip:

```python
chats_count = await self.chats_db.count_chats(user_id)      # 90
if chats_count >= self.chats_limit:                         # 91
    raise ChatHistoryLimitError(self.chats_limit)
...
await self.session.commit()                                 # 99  ends the read transaction
async with self.llm_service.admission() as admitted:
    await self.quota_service.charge(...)                    # 101 commits a credit in its own session
    ai_message = await self.ask_llm(chat, human_message, admitted)
...
self.chats_db.create_chat(chat)                             # 106
```

`count_chats` takes no lock and the count is re-checked nowhere, so N concurrent `POST /chats` on an account at `chats_limit - 1` all pass line 91 and all insert. There is no database constraint behind the limit (`migrations/20260818_01_initial-release.sql:53-61` declares none), so the account keeps every extra chat, and each racing request has already committed its monthly credit at line 101 — the one thing `quota.py` never refunds. `send_message`'s sibling guard (line 121) has the same shape but is bounded by the per-chat message count, which the same account can also race.

**Fix:** re-assert the count inside the transaction that writes, after the provider call, before the insert — the same pattern line 134 already uses for the chat-existence re-read:

```python
        # Re-read in the transaction that writes: the count above was taken before the provider call.
        if await self.chats_db.count_chats(user_id) >= self.chats_limit:
            raise ChatHistoryLimitError(self.chats_limit)
        chat.messages.append(human_message)
```

### WR-80: The conversion case seeds a state the anonymous writer can never produce, so `free_grant_consumed_at` preservation is unpinned at every tier

**File:** `tests/e2e/test_claim_registered_grant.py:226-230` (assertions end at `:269`)
**Issue:** `TestTheConversionOfAnActiveAnonymousGrant` seeds the active `anonymous_device_grant` with `seed_grant`, which never writes `ExternalIdentity.free_grant_consumed_at`. In production that state is unreachable: `crud/grants.py::activate_anonymous_device_grant` sets `stored.free_grant_consumed_at = evaluated_at` unconditionally for every anonymous grant it writes. So the one e2e conversion case runs the `stored.free_grant_consumed_at is None` arm of `crud/grants.py:317-319` — the arm the real conversion path never takes — and it never asserts the column at all. D-10 and the spec (`07-claim-registered-grant.md:72`, "permanent non-PII state … never cleared") require the *original* instant to survive the conversion.

Proven by mutation (reverted in the same call): replacing

```python
if stored.free_grant_consumed_at is None:
    stored.free_grant_consumed_at = evaluated_at
```

at `src/nativespeaker/api/crud/grants.py:317-319` with an unconditional `stored.free_grant_consumed_at = evaluated_at` — i.e. the conversion silently overwrites the instant the account actually spent its free slot — left every claim test green at all three tiers: `tests/e2e/test_claim_registered_grant.py` 16 passed, `tests/unit/test_claim_precedence_registered.py` + `tests/unit/test_grant_sources.py` 78 passed, `tests/schema/test_claim_race.py` 30 passed. `tests/unit/test_claim_precedence_registered.py:518` only proves the *preflight* does not refuse when the marker is set; it drives a fake grants seam and never reaches the writer.

**Fix:** in `test_the_anonymous_grant_is_expired_and_its_usage_moves_to_the_registered_row`, seed the marker the way the anonymous claim leaves it and assert it survives:

```python
        anonymous, _ = await seed_grant(...)
        spent_at = datetime.now(UTC) - timedelta(hours=1)
        async with _db_transaction() as session:
            row = (await session.exec(
                select(ExternalIdentity).where(col(ExternalIdentity.issuer) == TEST_ISSUER,
                                               col(ExternalIdentity.subject) == subject))).one()
            row.free_grant_consumed_at = spent_at
            session.add(row)
            await session.commit()
        ...
        # The conversion spends no new slot, so the instant the anonymous claim recorded stands.
        assert (await _identity_of(_db_transaction, subject)).free_grant_consumed_at == spent_at
```

`_identity_of` already exists at `:110`.

### WR-81: `refusal_sites.py` reads the package source with the locale encoding, so both webhook control tests break outside a UTF-8 locale

**File:** `tests/e2e/refusal_sites.py:36`
**Issue:** `files_raising_the_refusal()` calls `path.read_text()` with no `encoding`, so it decodes with `locale.getpreferredencoding(False)`. Three files under `src/nativespeaker/api/` carry non-ASCII bytes (`errors.py`, `app/dependencies.py`, `schemas/webhooks.py`), and Python 3.14 has not yet made UTF-8 the default. Under an ASCII locale the whole scan raises before it can compare anything, taking down `test_no_raise_site_lives_where_neither_route_control_reads_it` in **both** `test_app_store_webhook.py:273` and `test_google_play_webhook.py:365` — the two controls whose only job is to notice a new `NotificationRejected` raise site.

Proven:

```
$ LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 .venv/bin/python -c "...read_text()..."
preferred: ANSI_X3.4-1968
FAILED: UnicodeDecodeError 'ascii' codec can't decode byte 0xc2 in position 13137: ordinal not in range(128)
```

**Fix:** pin the encoding, as the files themselves are:

```python
            if refusal_calls(path.read_text(encoding="utf-8"))}
```

### WR-82: `_SpyLogger` turns an unanticipated log line into an `AttributeError` inside a request handler

**File:** `tests/e2e/conftest.py:67-82` (the `setattr` loop at `:71-72`)
**Issue:** `spy_on` replaces a module's whole `logger` with an object that has **only** the level attributes the case named. Every other level is now missing from the object the production code calls. `nativespeaker.api.app.error_handlers` calls both `logger.warning` and `logger.error`; `services/subscriptions` calls `info`, `warning` and `error`; `auth/google_play` calls `info` and `error` — yet `refusal_records` installs `("warning",)` only, `error_records` installs `("error",)` only, and `info_records` installs `("info",)` only over two or three of those modules at once. Any log line the case did not anticipate raises inside the exception handler or the service, which surfaces as an unrelated 500 or a stack trace rather than as an extra recorded entry. It is latent today only because the current arms happen to log at exactly one level.

Proven:

```
$ PYTHONPATH=tests .venv/bin/python -c "from e2e.conftest import _SpyLogger, LogSpy; ..."
warning recorded: [('ok_event', {'a': 1})]
CRASH -> AttributeError '_SpyLogger' object has no attribute 'error'
```

**Fix:** record every level and let the case filter, so an extra line is visible instead of fatal:

```python
_ALL_LEVELS = ("debug", "info", "warning", "error", "critical", "exception")


class _SpyLogger:
    def __init__(self, spy: LogSpy, levels: tuple[str, ...]) -> None:
        for level in _ALL_LEVELS:
            # Every level is bound; only the declared ones reach the spy's list.
            setattr(self, level,
                    spy.record if level in levels else (lambda *a, **k: None))
```

### WR-83: the post-commit DeviceCheck write failure has no e2e case, and the seam built for it is dead code

**File:** `tests/e2e/conftest.py:313, 321-323, 332-334`
**Issue:** `FakeDeviceCheckAdapter.script_write` / `write_answer` exist solely to script a failing `write_bits`, and **no e2e test ever calls them** (`grep -rn "script_write\|write_answer" tests/` hits only `tests/e2e/conftest.py` and `tests/unit/test_claim_precedence*.py`, which use their own separate fake). The arm they were built for is real and load-bearing on this phase's route: `services/auth.py:283-290` commits the registered grant first, then attempts `write_bits_with_retry(..., bit1=True)` and **swallows every exception** into one `devicecheck_bit_write_failed` ERROR line. A caller therefore gets 200 with a durable `registered_account_grant` while Apple's bit1 stays clear — the same device can claim a second registered free grant on another account, which is precisely what bit1 exists to prevent (D-01). Nothing at the e2e tier pins the 200, the grant, or the single error record for that outcome.

**Fix:** add a case to `TestTheThreeAppleFailureArms` (or a new class) in `tests/e2e/test_claim_registered_grant.py` that uses the seam already provided:

```python
    async def test_a_failed_bit_write_still_answers_the_granted_body_and_records_it_once(
            self, claim_client, _db_transaction, scripted_devicecheck_adapter, monkeypatch):
        spy = spy_on(monkeypatch, ("nativespeaker.api.services.auth.logger",), ("error",))
        subject = "e2e-claim-registered-write-failed"
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                                      provider=IdentityProvider.google)
        scripted_devicecheck_adapter.script_write(
            RetryableDeviceCheckError("scripted write failure"))

        claim = await _claim(claim_client, subject, await _issue(claim_client, subject))

        # The grant is durable before Apple is told, so the burned-slot failure is not the caller's.
        assert claim.status_code == 200, claim.text
        assert await _row_counts(_db_transaction, user.id) == (1, 1)
        assert scripted_devicecheck_adapter.write_calls == [(DEVICE_TOKEN, False, True)]
        assert [event for event, _ in spy.entries] == ["devicecheck_bit_write_failed"]
        # The token and Apple's body reach no record.
        assert DEVICE_TOKEN not in repr(spy.entries)
```

### WR-84: the shared-error-body quota case asserts no status, so the 500 its docstring rules out passes it

**File:** `tests/e2e/test_quota.py:58-62`
**Issue:**

```python
    async def test_the_no_grant_refusal_carries_the_shared_error_body(...):
        """The 429 is the shared `{code: ...}` shape -- not a 500, and not a bespoke payload."""
        response = await async_client.post(path.format(chat_id=own_chat), json=body)
        assert list(response.json().keys()) == ["code"]
```

The only assertion is on the key list. A 500 answering `{"code": "internal_error"}` — exactly what the docstring says the case rules out — yields `["code"]` and passes, as does a 401 `{"code": "auth_required"}` from a broken barrier. Two other cases in this same file were already hardened against exactly this ("`# WR-90: the status the case is about. Any non-charging failure … leaves the counter here too`", `:169` and `:227`); this one was missed.

**Fix:**

```python
        assert response.status_code == 429, response.text
        assert response.json() == {"code": "quota_exceeded"}
```

(the equality subsumes the key-list check).

### WR-85: `_contended_challenge` is function-scoped, so the eight-way contention runs three times and the "asserted first" guard covers a different run

**File:** `tests/e2e/test_challenge_store.py:73-74` (decorator/def), consumers at `:115`, `:120`, `:126`
**Issue:** `@pytest_asyncio.fixture(loop_scope="module")` sets only the **event-loop** scope; `scope` still defaults to `function`. Verified: `pytest tests/e2e/test_challenge_store.py::TestTheClaimSerializesConcurrentAttempts --setup-show -m e2e` shows `SETUP ... _contended_challenge` **3** times for the 3 tests. Consequences:

1. `test_no_contender_raised`'s stated contract — "Asserted first: an exception is neither a win nor a loss, so the counts below would pass anyway" — is false: it inspects its own run's `results`, not the run that `test_exactly_one_of_eight_concurrent_claims_wins` and `test_the_losers_mutated_nothing` inspect. Each of the three tests judges an independent race.
2. Three separate `create_async_engine(..., pool_size=10, max_overflow=0)` engines are built, filled with 8 live transactions and disposed, against the shared PostgreSQL — three times the connection pressure the author intended, and three chances for the `asyncio.Barrier(8)` to stall on pool acquisition.

**Fix:** make the scope explicit so the one race is shared by the class, and pin the loop scope to match:

```python
@pytest_asyncio.fixture(scope="class", loop_scope="module")
async def _contended_challenge(_app_lifespan, store):
```

(`store` and `_app_lifespan` must be at least class-scoped for this; `store` is derived from `_app_lifespan.state` and can be widened to `scope="module"` unchanged.)

### WR-100: The registered claim's D-09(e) refusal is never driven — the recorder field that would drive it is dead
**File:** `tests/unit/test_claim_precedence_registered.py:126` (recorder: `tests/unit/test_claim_precedence.py:118,146-149`)
**Issue:** `_RecordingGrants.grant_of_source` (`test_claim_precedence.py:118`) is initialised to an empty `set()` and is **never assigned by any test in either precedence module**, nor anywhere else under `tests/`. It exists solely to drive `GrantsDB.holds_grant_of_source` true, which is the only way to reach the service's D-09(e) guard at `src/nativespeaker/api/services/auth.py:246-249` — the refusal that stops an account with a spent registered slot in history from converting its still-active anonymous grant. On the `held == []` arm that branch is redundant (`has_prior_free_grant` at auth.py:258 covers it); on the conversion arm it is the *only* guard, and no unit test exercises it.

Mutation-proved in a reverted-in-call probe: disabling the guard (`if False and await self.grants_db.holds_grant_of_source(...)`) left `test_claim_precedence_registered.py`, `test_claim_ordering.py`, `test_grant_sources.py` and `test_claim_precedence.py` at **145 passed**. `tests/unit/test_spent_free_grant_refusal.py` covers only the *crud-level* twin at `crud/grants.py:277`, and `tests/unit/test_conversion_carries_usage.py:79-81` pins the service-level call to `False` permanently. Only `tests/e2e/test_claim_registered_grant.py::TestASpentRegisteredSlotRefusesTheConversion` catches it, so the module whose stated subject is "its rejection precedence" has a hole exactly where its own scaffolding was built for it.
**Fix:** Add a case to `TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce` and a setup to `POST_CLAIM_OUTCOMES`:
```python
def test_a_spent_registered_slot_refuses_the_conversion_and_still_consumes(
        self, client, store, account, grants, devicecheck, timeline):
    identity_row, _ = account
    grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant)]
    grants.grant_of_source = {AccessGrantSource.registered_account_grant}
    store.row = _issued(bound_to=identity_row.id)

    response = _claim(client)

    assert response.status_code == 403
    assert response.json() == REFUSED
    assert "holds_grant_of_source" in timeline
    assert grants.activates == 0
    assert store.consume_calls == 1
    assert devicecheck.read_calls == []


def _registered_slot_spent(identity_row, grants, devicecheck) -> None:
    grants.held = [_a_grant(AccessGrantSource.anonymous_device_grant)]
    grants.grant_of_source = {AccessGrantSource.registered_account_grant}
```
and add `_registered_slot_spent` to `POST_CLAIM_OUTCOMES` (line 623).

### WR-101: No unit test can see the registered claim writing the wrong tier — the recorder drops `tier_id` and the sync stub is hardcoded
**File:** `tests/unit/test_claim_precedence_registered.py:73-82` (recorder: `tests/unit/test_claim_precedence.py:156-165`)
**Issue:** `_RecordingGrants.activate` records `self.claim_platforms.append(claim_platform)` but silently discards `tier_id`, and `_RegisteredStubSync.read_entitlement` (lines 76-82) returns a hand-built `Entitlement(type=registered_account_grant, tier_id="registered", monthly_credits=50, ...)` **regardless of what the service actually asked the writer to write**. The consequence is that `assert response.json()["entitlement"]["type"] == "registered_account_grant"` (line 340) is answered by the stub, not by the code under test.

Mutation-proved in a reverted-in-call probe: changing `_claim_registered_grant` to pass `tier_id=ANONYMOUS_TIER_ID` (a 10-credit allowance instead of 50 — a direct entitlement/billing defect) left `test_claim_precedence_registered.py`, `test_claim_ordering.py`, `test_grant_sources.py` and `test_conversion_carries_usage.py` at **107 passed**. Only `tests/e2e/test_claim_registered_grant.py:165-166` catches it.
**Fix:** Record the tier in the shared recorder and assert it on both mutating destinations:
```python
# tests/unit/test_claim_precedence.py, _RecordingGrants.__init__
self.tiers: list[str] = []

# ... in activate()
self.tiers.append(tier_id)
```
then in `test_claim_precedence_registered.py`, on `test_the_new_grant_reaches_the_writer_after_one_read_and_one_write` and `test_the_conversion_reaches_the_writer_without_reaching_apple_and_still_consumes`:
```python
assert grants.tiers == ["registered"]
```
(and the mirror `assert grants.tiers == ["anonymous"]` on the anonymous claim's success case at `test_claim_precedence.py:599`).

### WR-102: The retry-timing floor equals the actual total backoff to within ~2 ms, and the comment that justifies it states the wrong numbers
**File:** `tests/unit/test_firebase_retry.py:161-171` and `tests/unit/test_devicecheck_adapter.py:296-317`
**Issue:** Both files carry the identical comment: *"`wait_exponential(0.1, exp_base=2, max=0.5)` sleeps 0.2s then 0.4s. The floor is well under that…"* — and set `FLOOR_SECONDS = 0.3`. The premise is factually wrong. tenacity computes `multiplier * exp_base ** (attempt_number - 1)`, so with `FIREBASE_BACKOFF_BASE_SECONDS = 0.1` / `DEVICECHECK_BACKOFF_BASE_SECONDS = 0.1` the two gaps are **0.1 s then 0.2 s = 0.3 s total**, not 0.6 s. Measured five times on this machine: `0.301941, 0.302086, 0.302016, 0.301632, 0.302192` seconds against a `>= 0.3` floor — a margin of ~2 ms (0.6 %), not the 2x the comment claims. `pytest --durations` reports the four cases at 0.30–0.31 s.

The assertion passes today only because `asyncio.sleep` cannot undershoot. It has no room for a clamp change, a `max=` change, an event-loop policy change, or any platform whose timer granularity lets a sleep return marginally early — and, worse, it currently proves nothing beyond "some sleeping happened", because it cannot be raised without going red.
**Fix:** Fix the comment and give the floor real headroom by deriving it from the production constants rather than restating them:
```python
# tests/unit/test_firebase_retry.py
from nativespeaker.api.auth.firebase import FIREBASE_BACKOFF_BASE_SECONDS

# The gaps are `base * 2 ** (attempt - 1)`: 0.1s then 0.2s, 0.3s in all. Two thirds of that is
# far above the microseconds `wait_none()` costs and far below the sum, so it neither flakes
# nor passes unfixed. Derived, so a change to the base moves this floor with it.
FLOOR_SECONDS = 2 * (FIREBASE_BACKOFF_BASE_SECONDS + 2 * FIREBASE_BACKOFF_BASE_SECONDS) / 3
```
and the same, against `DEVICECHECK_BACKOFF_BASE_SECONDS`, in `test_devicecheck_adapter.py`.

### WR-120: The barrier's "no state filtering in SQL" guard reads only the text after `WHERE`, so a JOIN-ON predicate escapes it

**File:** `tests/unit/test_identities_crud.py:239-252`
**Issue:** `test_it_filters_on_issuer_and_subject_and_nothing_else` splits the compiled statement on `"WHERE"` and inspects only the tail, and `test_the_state_columns_are_read_in_python_not_filtered_in_sql` compares two compiled statements. `IdentitiesDB.resolve` builds its statement from `(issuer, subject)` alone, so the whole join condition sits *before* `WHERE` and is never read by either case.

Proved by mutation (reverted in the same call): rewriting `crud/identities.py:34` as

```python
.join(User, and_(col(ExternalIdentity.user_id) == col(User.id),
                 col(User.active).is_(True)), isouter=True)
```

leaves **all 38 tests in this file green**, while turning every blocked account's `BlockedUser` 403 into an `IdentityUnresolvable` 500. That breaks two ratified rules at once: SHARED-INVARIANTS § *The barrier* ("admits only `identity_state='active'` AND `users.active` exactly TRUE. Every other combination … rejects") and D-05's two-leaf shape this same file asserts at lines 206-214, because a blocked user would no longer answer `account_unavailable` at all. The stub session ignores the statement and returns the seeded row unconditionally, so no behavioural case in the file can catch it either.

**Fix:** Assert against the whole compiled statement, not the `WHERE` tail, and name the join predicate positively:

```python
async def test_it_filters_on_issuer_and_subject_and_nothing_else(self):
    _identity, session = await _resolve(_row())
    sql = str(session.statements[0])
    assert "identity_state" not in sql and "core.users.active" not in sql
    # The join is the equality alone: an extra term here is a filter moved out of Python.
    on_clause = sql.split("LEFT OUTER JOIN core.users ON", 1)[1].split("WHERE", 1)[0]
    assert on_clause.strip() == "core.users.id = core.external_identities.user_id"
```

### WR-121: The charge's three statements are never checked against the values they are keyed on, so a cross-tenant charge passes

**File:** `tests/unit/test_quota_resolver.py:299-347`
**Issue:** `TestTheLockingStatements` and `TestGrantThenUsageOrder` assert only the compiled *text* (`"core.access_grants.user_id = "`, `FOR UPDATE`, entity order). The compiled text renders every bound value as a placeholder, so the statement's key is unasserted. The read-only sibling path pins exactly this under WR-83 (`tests/unit/test_sync_resolver.py:223-252`, with the `_bound()` helper and the note "a wrong bound value is a cross-tenant read"); the *writing* path — the one that takes `FOR UPDATE` locks and spends a credit — has no `_bound()` helper at all.

Proved by three mutations of `services/quota.py` (each reverted in the same call), all of which leave **76/76 tests in `test_quota_resolver.py` + `test_quota_seam.py` green**:
- `lock_effective_grants(uuid4(), evaluated_at)` — locks and charges another tenant's grants;
- `lock_usage(uuid4())` — locks a usage row belonging to no grant in hand;
- `monthly_credits('some-other-tier')` — compares the count against another tier's allowance.

The first is a direct breach of SHARED-INVARIANTS § *Identity and ownership* ("Business data is keyed only by `core.users.id`").

**Fix:** Port `test_sync_resolver.py`'s `_bound()` helper into this file and add the three chaining cases:

```python
def _bound(statement) -> list:
    return list(statement.compile(dialect=postgresql.dialect()).params.values())

async def test_each_read_is_keyed_on_what_the_one_before_it_named(self):
    grant, usage = _one_effective_grant()
    session = await _consume(grants=(grant,), usage=usage)
    assert USER_ID in _bound(session.statements[0])
    assert [v for v in _bound(session.statements[0]) if isinstance(v, datetime)] == \
        [EVALUATED_AT, EVALUATED_AT]
    assert grant.id in _bound(session.statements[1])
    assert grant.tier_id in _bound(session.statements[2])
```

### WR-122: The transient-status set is parametrised over itself, so shrinking it fails nothing

**File:** `tests/unit/test_resilience_retry.py:419-430`
**Issue:** `test_a_retry_eligible_status_is_transient` is parametrised over `sorted(_TRANSIENT_STATUSES)` — the very frozenset the predicate reads. Dropping a member removes its case rather than failing one, and the control at line 427 lists only `(400, 401, 403, 404, 422)`, none of which overlaps the set. The class docstring claims the set "decides whether the breaker counts a failure", but nothing pins its contents.

Proved by mutation (reverted in the same call): replacing `resilience.py:28` with `_TRANSIENT_STATUSES = frozenset({408})` — so an OpenAI 429/500/502/503/504 is reclassified as `PermanentLLMError`, never retried and never counted by the breaker — leaves **58/58 tests in `test_resilience_retry.py` + `test_quota_seam.py` green**.

**Fix:** Write the set down as a literal, exactly as `test_rejection_vocabulary.py` writes down `EVENT_NAMES`:

```python
# Listed rather than derived, so a status leaving the set is a visible edit.
RETRY_ELIGIBLE = (408, 409, 429, 500, 502, 503, 504)

def test_the_set_is_exactly_the_statuses_worth_retrying(self):
    assert _TRANSIENT_STATUSES == frozenset(RETRY_ELIGIBLE)

@pytest.mark.parametrize("status", RETRY_ELIGIBLE)
def test_a_retry_eligible_status_is_transient(self, status):
    assert _is_transient_error(_StatusOnly(status))
```

### WR-123: `_BOUNDED_AUTH_FIELDS` claims to cover every authenticated auth-body string but omits both `RestoreRequest` fields

**File:** `tests/unit/test_models.py:338-343`
**Issue:** The comment reads "Every string an authenticated auth body carries, with the real value each one must stay above", and the class docstring justifies the bound for `device_token` because it "is relayed verbatim to Apple". `RestoreRequest.restore_proof` (`schemas/auth.py:52`, `max_length=8192`) is the same kind of value — the client's Apple signed transaction or Play purchase token, relayed verbatim to the store by `RestoreService.restore` — and `RestoreRequest.provider` (`:50`) is likewise bounded in source. Neither appears in `_BOUNDED_AUTH_FIELDS`, and `RestoreRequest` is referenced by no test in the repository.

Proved by mutation (reverted in the same call): replacing both declarations with bare `provider: str` / `restore_proof: str` — removing `min_length` and `max_length` together — leaves **883 tests green** across `test_models.py` and every unit file mentioning "restore".

**Fix:** Add both rows to the table so the three existing parametrised cases (oversize refused, bound above the real value, empty refused) cover them:

```python
# The upper end of a real Apple signed transaction, certificate chain included.
REALISTIC_RESTORE_PROOF = 4 * 1024

_BOUNDED_AUTH_FIELDS = [
    (CompletionRequest, "challenge_id", {}, CHALLENGE_ID_CHARACTERS),
    (GrantClaimRequest, "challenge_id", {"device_token": "t"}, CHALLENGE_ID_CHARACTERS),
    (GrantClaimRequest, "device_token", {"challenge_id": "c"}, REALISTIC_DEVICE_TOKEN),
    (RestoreRequest, "provider", {"restore_proof": "p"}, len("google_play")),
    (RestoreRequest, "restore_proof", {"provider": "apple"}, REALISTIC_RESTORE_PROOF),
]
```

(If `restore_proof`'s current 8192 does not clear the `limit >= 2 * realistic` control, that is itself the finding to settle before adding the row.)

### WR-124: The unminted-primary-key guard skips any `id` typed `UUID | None`, which is the spelling the bug it guards would arrive in

**File:** `tests/unit/test_tables_metadata.py:26-28`
**Issue:** `_UUID_KEYED_TABLES` filters on `model.model_fields["id"].annotation is UUID`. The idiomatic SQLModel spelling for a server-shaped primary key is `id: UUID | None = Field(default=None, primary_key=True)`, whose annotation is `UUID | None` — not `UUID` — so such a model is dropped from the walk entirely, and `test_no_uuid_keyed_table_leaves_its_id_unminted` passes on an empty check for it. That is exactly the WR-20 regression the class docstring describes (a NULL sent to the primary key, re-raised by every writer as an opaque 500).

Proved by mutation (reverted in the same call): rewriting `tables/grants.py:63` as `id: UUID | None = Field(default=None, primary_key=True)` leaves **both tests in `TestEveryUuidPrimaryKeyMintsItsOwnValue` green**. The same edit on `tables/chats.py` is caught only by accident, because `test_the_walk_sees_the_tables_control` happens to hardcode `Message` by name — a control that protects three of the nine UUID-keyed tables.

**Fix:** Select on the column, not the annotation, so the optional spelling cannot escape:

```python
def _is_uuid_key(model) -> bool:
    columns = model.__table__.primary_key.columns
    return len(columns) == 1 and isinstance(list(columns)[0].type, sqlalchemy.Uuid)

_UUID_KEYED_TABLES = tuple(model for model in _MAPPED_TABLES if _is_uuid_key(model))
```

and widen the control to the full expected set rather than three names:
`assert {m.__name__ for m in _UUID_KEYED_TABLES} == {"AccessGrant", "AuthChallenge", "Chat", "ExternalIdentity", "Message", "StorePurchase", "Subscription", "SubscriptionEvent", "User"}`.

### WR-125: Three of the registered-claim writer's five refusal labels are pinned nowhere

**File:** `tests/unit/test_spent_free_grant_refusal.py:134-155`
**Issue:** `TestEachRefusalNamesTheArmThatFiredIt` states the general property WR-62 exists for ("`refused` carried no label, so nine conditions left one identical, field-less line") but asserts only two labels: `spent_slot_without_a_registered_grant` and `identity_not_registered`. `GrantsDB.activate_registered_account_grant` returns three more — `other_grant_held` (`crud/grants.py:259`), `unseen_active_grant` (`:263`) and `registered_grant_held` (`:278`) — and `grep -rn` finds none of the three anywhere under `tests/`. Since this file is, by its own docstring, the one suite that drives the real writer, nothing in the tree holds them.

Proved by mutation (reverted in the same call): replacing all three with `None` — collapsing three distinguishable operator log lines back into one field-less `claim_refused` — leaves **114 tests green** across `test_claim_ordering.py`, `test_claim_precedence_registered.py`, `test_conversion_carries_usage.py`, `test_grant_sources.py` and this file.

**Fix:** Add one case per arm to `TestEachRefusalNamesTheArmThatFiredIt`, each reachable from the existing `writer` fixture:

```python
async def test_a_held_grant_of_another_source_names_its_own_arm(self, writer, identity_row,
                                                                monkeypatch):
    async def lock_effective(self, user_id, evaluated_at):
        return [AccessGrant(user_id=user_id, tier_id=TIER_ID,
                            source=AccessGrantSource.subscription,
                            status=AccessGrantStatus.active, starts_at=EVALUATED_AT)]
    monkeypatch.setattr(GrantsDB, "lock_effective_grants", lock_effective)
    _with_registered_row(monkeypatch, present=False, asked=[])

    assert await _cause(writer, identity_row) == "other_grant_held"
```

plus the mirrors for `unseen_active_grant` (a row returned by `lock_active_grants` that `lock_effective_grants` does not) and `registered_grant_held` (`has_prior_free_grant` False, `holds_grant_of_source` True).

### WR-126: `iat` temporal validity is named by the spec and pinned by no case

**File:** `tests/unit/test_jwt_security.py:319-347`
**Issue:** SHARED-INVARIANTS § *Wire contract* requires "`exp`/`iat` temporal validity". `test_requires_the_exp_claim` and `TestAnAbsentClaimIsNotLabelledAsForgery` pin only the *presence* of `iat` (through `DECODE_OPTIONS["require"]`), and `test_every_required_claim_is_mapped` compares two source-derived sets. `DECODE_OPTIONS` (`auth/jwt_verifier.py:53`) sets `require` and nothing else, so the future-`iat` rejection is entirely PyJWT's default behaviour. I confirmed it currently holds (a token with `iat = now + 365d` returns `BoundedReason.expired`) — but no assertion in the file would fail if a PyJWT upgrade, an added `options` entry, or a leeway change removed it, and `exp` gets both a leeway case and a past-leeway case while `iat` gets neither.

**Fix:** Add a case beside the two `exp` leeway cases, against the production verifier:

```python
def test_rejects_a_token_issued_in_the_future(self, real_verifier):
    """`iat` temporal validity, not just its presence (SHARED-INVARIANTS § Wire contract)."""
    now = time.time()
    assert rejected(real_verifier, make_token("u", iat=now + 3600, exp=now + 7200)) \
        is BoundedReason.expired

def test_accepts_a_token_issued_inside_the_same_leeway(self, real_verifier):
    """The control: clock skew inside the leeway is not a forgery."""
    now = time.time()
    assert accepted(real_verifier, make_token("u", iat=now + 10)).subject == "u"
```

### WR-140: The anonymous claim writer's lock-tier proof never runs the arm that writes
**File:** `tests/schema/test_grant_locks.py:291-382`
**Issue:** `activation_statements` (line 302) seeds a held `manual` grant, so `activate_anonymous_device_grant` always returns `ActivationOutcome.refused` — the fixture's own control asserts exactly that at line 378. Every case in `TestTheActivationAddsNoThirdLockTier` therefore measures the **refused** path only. The activating arm (`crud/grants.py:194-221`) — the one that adds the `AccessGrant`, adds the `UserMonthlyUsage`, writes `stored.free_grant_consumed_at` and `stored.native_claim_platform`, and flushes — is never observed for lock tiers at all. Proven empirically: replacing that entire arm with `raise RuntimeError(...)` leaves all three cases green (`3 passed`). The divergence between the two near-duplicate re-read helpers is the tell — the anonymous one (lines 375-376) filters only on `"core.external_identities" in statement and "FOR UPDATE" not in statement`, while the registered one (lines 404-406) additionally requires `statement.startswith("SELECT")`. The anonymous filter would count *two* statements on the activating arm (the SELECT plus the identity UPDATE) and fail, which is why it was never pointed at that arm. A third lock tier introduced on the anonymous writer's insert path — the SHARED-INVARIANTS:33 violation this class exists to catch — ships green. The registered writer has no such hole: `new_grant_statements` and `conversion_statements` both drive `ActivationOutcome.activated`.
**Fix:** Add a third fixture mirroring `new_grant_statements` — a clean anonymous account with no held grant — and assert on it:
```python
@pytest_asyncio.fixture
async def anonymous_activated_statements(_schema_db_uri):
    """The anonymous writer on a clean account: it activates, so the writing arm is the subject."""
    async with _anonymous_writer_run(_schema_db_uri, holding_grant=False) as run:
        yield run

async def test_the_activating_arm_locks_the_grant_tier_alone(self, anonymous_activated_statements):
    locked = locking(anonymous_activated_statements["statements"])
    taken = [relation_of(s) for s in locked]
    assert taken == ["core.access_grants", "core.access_grants"]
    assert "core.external_identities" not in taken and "core.users" not in taken
    assert_one_plain_identity_re_read(anonymous_activated_statements)   # the SELECT-filtered helper
```
and delete the divergent inline filter at lines 375-376 in favour of the shared `assert_one_plain_identity_re_read`.

### WR-141: `relation_of` and `locking` cannot see a third lock tier taken by a join or a non-`FOR UPDATE` lock
**File:** `tests/schema/test_grant_locks.py:277,280-288`
**Issue:** Two blind spots make the "never a third tier" assertions (lines 364-370, 503-509, 906-913) defeatable by the very drift they exist to catch.
1. `_LOCKED_RELATION = re.compile(r"FROM (core\.[a-z_]+)")` and `relation_of` return only the **first** match. A locking statement of the form `SELECT ... FROM core.access_grants JOIN core.external_identities ... FOR UPDATE` reports `core.access_grants`, so `assert "core.external_identities" not in taken` passes while the identity row is locked ahead of the usage tier.
2. `locking()` matches the literal substring `"FOR UPDATE"`. `SELECT ... FROM core.users ... FOR NO KEY UPDATE` and `... FOR SHARE` contain no such substring, so a third-tier lock taken with either form is dropped from `taken` entirely and every assertion still passes.
**Fix:** Match every relation in the statement and every row-lock spelling:
```python
_LOCK_CLAUSE = re.compile(r"FOR (?:NO KEY )?UPDATE|FOR (?:KEY )?SHARE")
_RELATIONS = re.compile(r"\b((?:core|audit)\.[a-z_]+)")

def locking(statements): return [s for s in statements if _LOCK_CLAUSE.search(s)]
def relations_of(statement): return sorted(set(_RELATIONS.findall(statement)))
```
and assert over the union of `relations_of(...)` across the locking statements, not over one relation per statement.

### WR-142: The "exact-set object inventory" pins no columns except `core.users`, and no index key columns at all
**File:** `tests/schema/test_inventory.py:66-70,118-156,190-192`
**Issue:** The file's docstring promises an "Exact-set object inventory", and `TestIndexes` claims "a renamed or stray index fails this suite". The column-level coverage is `USERS_COLUMNS` (line 66) plus the `jwt_sub`/`subscription_plan` negative checks — nothing else. Verified across the whole suite: `information_schema.columns` and `pg_attribute` appear only for `core.users` and for constraint-column extraction; `indkey` appears nowhere in `tests/schema/`. Consequences:
- A column added to or dropped from `core.access_grants`, `core.subscriptions`, `core.auth_challenges`, `core.store_purchases` or `core.external_identities` — or a `NOT NULL` / `DEFAULT` silently changed on any of them — passes the whole inventory green.
- An index re-keyed while keeping its name and predicate passes too: `ix_access_grants_one_active_per_user ON (user_id) WHERE status='active'` widened to `ON (user_id, tier_id)` matches `EXPECTED_CORE_INDEXES` and `EXPECTED_INDEX_PREDICATES` unchanged. The behavioural backstop does not catch it either — `test_constraints.py:257-267` inserts both grants on the same `tier` fixture, so a `(user_id, tier_id)` index still rejects the second one.
**Fix:** Add two exact-set cases keyed on the catalogue, in the same `assert_exact_set` style already used here:
```python
COLUMNS = """
SELECT c.relname || '.' || a.attname || ':' || format_type(a.atttypid, a.atttypmod)
       || CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END AS spec
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = $1 AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
"""
INDEX_KEYS = """
SELECT i.relname, pg_get_indexdef(ix.indexrelid) FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname IN ('core','audit')
"""
```
and pin both captures the same way the enum labels and FK delete actions already are.

### WR-143: The schema suite runs `DROP DATABASE ... WITH (FORCE)` against whatever host `.env` names
**File:** `tests/schema/conftest.py:33-49,60-69`
**Issue:** `_env` reads `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` from the environment with no constraint on the target, `admin_dsn()` connects to `DB_NAME` on that host, and `create_database` then issues `DROP DATABASE IF EXISTS ns_schema_test WITH (FORCE)` followed by `CREATE DATABASE`. `pyproject.toml:61` sets `env_files = [".env"]`, so pytest-dotenv loads whatever `.env` is present into `os.environ` before collection. A developer or CI job whose `.env` points at a shared or staging PostgreSQL runs a forced `DROP DATABASE` and a `CREATE DATABASE` on that server as a side effect of `pytest -m schema`. `_check_identifier` guards the identifier's *shape*, not the *server* it is executed on. The blast radius is bounded to a database named `ns_schema_test` plus the `CREATEDB` privilege the role must hold, but the operation is unconditional and silent.
**Fix:** Fail closed on a non-loopback target, in `admin_dsn()`:
```python
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

def admin_dsn() -> str:
    host = _env("DB_HOST")
    if host not in _LOCAL_HOSTS and not os.environ.get("NS_SCHEMA_TEST_ALLOW_REMOTE"):
        msg = f"refusing to create and drop scratch databases on {host!r}"
        raise RuntimeError(msg)
    return dsn_for(_env("DB_NAME"))
```

### WR-144: Two concurrent pytest sessions destroy each other's scratch database
**File:** `tests/schema/conftest.py:18,97-102`
**Issue:** `SCHEMA_TEST_DB` is the fixed constant `"ns_schema_test"` and the session fixture unconditionally drops and recreates it at setup — with `FORCE`, which terminates every other connection to it. Two schema runs against one PostgreSQL server (two developers, a CI matrix job, or any future `pytest -n` run once xdist is added) will terminate each other mid-test, producing `ConnectionDoesNotExistError` failures that point at whichever test happened to be running rather than at the cause.
**Fix:** Make the scratch name per-session:
```python
SCHEMA_TEST_DB = f"ns_schema_test_{os.getpid()}"
```
(the name still satisfies `_SAFE_IDENTIFIER`), and keep the teardown drop so the name is not left behind.

### WR-145: The `conn` fixture leaks its asyncpg connection when the transaction fails to start
**File:** `tests/schema/conftest.py:108-118`
**Issue:** `connection = await asyncpg.connect(...)` and `await tx.start()` both run **before** the `try:` at line 111. If `tx.start()` raises — a server at its connection limit, a lost socket, a `pg_hba` denial after the handshake — the `finally` that closes the connection never runs, and the socket stays open for the rest of the session. Because this fixture is used by every case in `test_constraints.py`, `test_inventory.py`, `test_apply_rollback.py` and `test_registration_pairing.py`, a transient failure converts into a monotonically growing pool of leaked connections and then into unrelated `too many clients` failures elsewhere in the run.
**Fix:**
```python
connection = await asyncpg.connect(_schema_db_uri)
try:
    tx = connection.transaction()
    await tx.start()
    try:
        yield connection
    finally:
        with contextlib.suppress(Exception):   # a deferred-constraint failure already aborted it
            await tx.rollback()
finally:
    await connection.close()
```

### WR-146: Setup outside the `try` leaks a connection and commits a tier row into the shared scratch database
**File:** `tests/schema/test_subscription_ingestion.py:729-732`
**Issue:** `conn = await asyncpg.connect(...)`, `tier_id = await insert_tier(conn)` and `user_id = await insert_user(conn)` all run before `try:` at line 732. `conn` is a raw asyncpg connection in autocommit, so `insert_tier` **commits** immediately. If `insert_user` (or `insert_tier` itself) raises, neither `_clean` nor `conn.close()` runs: the connection leaks and a `core.access_tiers` row is left permanently committed in the session-scoped `ns_schema_test` database, where every later module can see it. This is the only case in the file that seeds outside its cleanup guard — `_buyer` (line 257) and `_ingestion_run` get it right.
**Fix:** Move both seeds inside the `try`, and close the connection in an outer `finally`:
```python
conn = await asyncpg.connect(_schema_db_uri)
tier_id = user_id = None
try:
    tier_id = await insert_tier(conn)
    user_id = await insert_user(conn)
    ...
finally:
    if tier_id is not None:
        await _clean(conn, user_id=user_id, tier_id=tier_id)
    await conn.close()
```

### WR-147: `test_any_violation_the_loser_saw_was_the_unique_one` cannot fail on the SQLSTATE it names
**File:** `tests/schema/test_restore_race.py:352-356`
**Issue:** `attempt.sqlstate` is written in exactly two places — `_RecordingSession.flush` (line 122) and `_RecordingSession.commit` (line 130) — and both are reached only from an `except IntegrityError` whose superclass handler has already set `integrity_at_flush` or `integrity_at_commit` to `True`. Line 356 asserts both flags are `False`; given that, `loser.sqlstate` is necessarily `None` and `assert loser.sqlstate in (None, "23505")` is a tautology. The docstring's stated subject ("42-07: 23505 is the only integrity code a lost race may carry") is never exercised on this path: if the restore writer ever started classifying a `23503` as a lost race, this case would still be green. `test_subscription_race.py:210-213` shows the falsifiable form (`assert loser.sqlstate == "23505"`, on a path where the index really fires).
**Fix:** Either drop the vacuous line and keep only the flag assertion, or add a case that bypasses the CAS `UPDATE` so the unique index is the real arbiter and the loser genuinely carries `23505`:
```python
async def test_a_loser_arbitrated_by_the_index_carries_23505(self, harness):
    ...  # commit the winning subscription grant on a second connection between the CAS and the flush
    assert loser.sqlstate == "23505"
    assert (loser.integrity_at_flush, loser.integrity_at_commit) == (True, False)
```

## Info

### IN-01: `[tool.pogo] schema = 'api'` names a schema no migration ever creates

**File:** `pyproject.toml:85`

**Issue:** `pogo_core/util/sql.py:24` runs `SET search_path TO api` on every `pogo apply`/`rollback`, and `migrations/20260818_01_initial-release.sql:6-7` creates only `core` and `audit`. Postgres accepts a `search_path` entry for a non-existent schema silently. Verified end to end against a throwaway database: `pogo apply` and `pogo rollback` both succeed today only because every object in the one migration is schema-qualified. The value is also the `schema_name` label written into `public._pogo_migration` (`pogo_core/util/sql.py:43-52`), so changing it now makes pogo read the applied migration as unapplied and re-run it. The residual cost is a future migration containing one unqualified `CREATE TABLE`, which fails with "no schema has been selected to create in" and names nothing in this repository.

**Fix:** Either add `CREATE SCHEMA IF NOT EXISTS api;` to the migration so the search path resolves, or replace the value with `schema = 'core'` and rebuild the disposable development databases in the same stroke (cheap under SCHEMA-01 while there are no users). Whichever is chosen, add one line beside it saying which schema the label names.

### IN-02: The chart's `appVersion` is a minor release behind the package it deploys

**File:** `pyproject.toml:3` (against `k8s/Chart.yaml:6`)

**Issue:** `pyproject.toml` declares `version = "1.6.0"`; `k8s/Chart.yaml` declares `appVersion: "1.5.0"`. `_helpers.tpl:30` renders that into `app.kubernetes.io/version` on the Deployment, Service, both HTTPRoutes and the SecurityPolicy, so every object in the cluster is labelled with a version the image does not contain. Nothing reads the label today, which is why this is not a warning.

**Fix:** Set `appVersion: "1.6.0"` in `k8s/Chart.yaml`, and bump both in the same commit from now on.

### IN-03: `.gitignore` does not ignore `.ruff_cache/`, which `.dockerignore` does

**File:** `.gitignore:5-7`

**Issue:** `.dockerignore:26` lists `.ruff_cache/`; `.gitignore` lists `__pycache__/`, `.pytest_cache/` and `*.egg-info/` but not `.ruff_cache/`. The directory exists untracked in the working tree right now (`git check-ignore .ruff_cache` exits 1), so a `git add -A` commits ruff's binary cache.

**Fix:** Add `.ruff_cache/` beside `.pytest_cache/` in `.gitignore:6`.

### IN-04: Pytest accepts unknown markers, so a mistyped `e2e` or `schema` mark runs in the default suite

**File:** `pyproject.toml:64-69`

**Issue:** `addopts` deselects `e2e` and `schema` by marker, and `markers` declares all three, but `--strict-markers` is absent. A test written `@pytest.mark.e2ee` or `@pytest.mark.shema` raises only a `PytestUnknownMarkWarning` and then runs inside the default suite, where it reaches the network or expects a live PostgreSQL. The two markers that gate real infrastructure are exactly the ones a typo silently disarms.

**Fix:** `addopts = "-v --tb=short --strict-markers -m 'not e2e and not schema'"`.

### IN-05: `ix_auth_challenges_expires_at` has no reachable consumer

**File:** `migrations/20260818_01_initial-release.sql:322`

**Issue:** `expires_at` appears in exactly one query, the atomic claim at `crud/challenges.py:72`, where it sits beside `challenge_id = $1` — served by the `UNIQUE (challenge_id)` index, never by this one. The only workload that scans by `expires_at` alone is a sweep of expired rows, and `SHARED-INVARIANTS.md` § "Global deletions" forbids it outright ("No scheduled cleanup, purge, reconciliation, recovery-scan, or background-healer job of any kind (challenge rows... indefinite retention)"), as does `07-claim-registered-grant.md` § DELETIONS ("no scheduled cleanup of challenge rows"). The index is write amplification on the hottest insert in the auth path with no reader that the specs permit to exist.

The same file also carries `ix_external_identities_user_id` (line 110), fully redundant with the unique index `UNIQUE (user_id)` on line 100, and `ix_external_identities_user_active` (line 112), whose `identity_state` component is never a SQL predicate (`crud/identities.py:50` filters it in Python). Both are reproduced verbatim from `specs/auth-refactor/06-schema-reference.md`, so they are spec-conformant and are recorded here as context only.

**Fix:** Drop `ix_auth_challenges_expires_at` from the migration and rebuild the disposable databases, recording it as a flagged divergence from `06-schema-reference.md` alongside D-07's existing entry — the same mechanism this phase already used for three tables. If the index is instead kept as a hedge against a future retention policy, say so in the comment above it, because "no cleanup job may exist" and "an index that only a cleanup job would use" read as a contradiction to the next reader.

### IN-06: `core.access_grants` carries clock and status defaults that `tables/grants.py` says it does not

**File:** `migrations/20260818_01_initial-release.sql:222-223, 232-233`

**Issue:** `tables/grants.py:70-71` states the module's rule: "No default on any timestamp in this module: the creating transaction owns the clock, so a forgotten value is a NOT NULL violation rather than a second reading of it." The DDL gives `starts_at`, `created_at` and `updated_at` `DEFAULT CURRENT_TIMESTAMP` and `status` `DEFAULT 'active'`, so at the database level a forgotten value takes a second clock reading — a direct contradiction of `SHARED-INVARIANTS.md` § "Grants and evaluation time" ("Derive every time-dependent value from ONE captured evaluation time"). It is unreachable from the ORM (all four fields are required or explicitly set at `crud/grants.py:72-77`) and the defaults are verbatim from `specs/auth-refactor/06-schema-reference.md:239-241,254-255`, which is why this is informational and not a warning.

**Fix:** Leave the DDL as the spec writes it and correct the claim in `tables/grants.py:70-71` so it says what is true — the model layer supplies every clock because the fields are required here, not because the column would reject a missing value.

### IN-07: The public HTTPRoute matches a prefix where exactly one route exists

**File:** `k8s/templates/httproute-health.yaml:16-18`

**Issue:** `health-routes` is the one HTTPRoute outside the JWT `SecurityPolicy` (`security-policy.yaml:9-15`), and it matches `PathPrefix /health`. The backend registers one route under that prefix, `GET /health/ready` (`routers/health.py:7`). `SHARED-INVARIANTS.md` § "The barrier" scopes the public allowlist to "health/readiness probes only" and requires that a route with no declaration "never becomes public silently"; a prefix match means any `/health/*` route added later is admitted by the gateway without a chart change. The backend is authoritative here and `routers/health.py` carries the same prefix-wide absence of an auth dependency, so nothing the gateway does today weakens an enforced control.

**Fix:** Match the one route that exists, so adding a second is a visible chart edit:

```yaml
  - matches:
    - path:
        type: Exact
        value: /health/ready
```

### IN-20: `NotificationRejected(stage=str(reason))` can render the string `"None"` as a stage label

**File:** `src/nativespeaker/api/auth/google_play.py:236`

**Issue:** `PubSubPushTokens.verify` stringifies the bounded reason unguarded. `TokenVerifier.verify`
is typed `tuple[VerifiedClaims | None, BoundedReason | None]` (`jwt_verifier.py:80`), so `(None,
None)` is inside the declared contract, and `stage="None"` would reach the log as a population no
alert can name. `dependencies.py:85-87` guards the identical shape explicitly for exactly this
reason. The concrete `JWTVerifier` never returns `(None, None)`, so this is a contract gap rather
than a live bug — but `PubSubPushTokens` is typed against the Protocol, not the class.

**Fix:** `raise NotificationRejected(stage=str(reason or BoundedReason.bad_signature))`.

### IN-21: `AppConfig | None` and the `config is None` guard describe a state `load_config` cannot produce

**File:** `src/nativespeaker/api/config.py:186`

**Issue:** `app_config: AppConfig | None = None` is always assigned by the `model_validator(mode="after")`
at `:188-209`, which either sets it or raises. `lifespan.py:137-139`'s `if config is None: raise
RuntimeError("Configuration failed to load")` is therefore unreachable, and the optional type
forces every other reader to narrow a value that is never absent.

**Fix:** Build the `AppConfig` in the validator and expose it as a non-optional field (or a
property), then drop the guard.

### IN-22: The ten-entry `responses=` map documents nothing, because the schema route is off

**File:** `src/nativespeaker/api/app/main.py:30`

**Issue:** `responses={400: ..., ... 503: ...}` feeds OpenAPI generation only, and the same call
sets `openapi_url=None` (`:29`) — a Phase 35 D-04 decision — so no schema is ever served. Twelve
lines of configuration with no runtime and no documentary effect, and `ErrorResponse` is imported
solely to fill it.

**Fix:** Delete the block and the `ErrorResponse` import, or add a comment saying it is kept for a
locally re-enabled `/docs`.

### IN-23: Two unreachable exception arms in the execution gate

**File:** `src/nativespeaker/api/resilience.py:194`

**Issue:** `except (QueueFullError, CircuitOpenError):` inside `attempt` — `QueueFullError` is
raised only by `LLMExecutionGate.inflight_slot`, which is entered in `admission()` (`:166`), never
inside `ainvoke`; nothing in the `try` can raise it. Likewise `except asyncio.QueueFull: pass` at
`:113-114` guards a `put_nowait` returning a token to a queue sized to hold exactly the tokens it
minted, so it can never be full. Both read as live guards.

**Fix:** Narrow `:194` to `except CircuitOpenError:` and drop the `QueueFull` arm, or state in a
comment that they are structural assertions.

### IN-24: The shutdown line is written for a startup that never reached `yield`

**File:** `src/nativespeaker/api/app/lifespan.py:236`

**Issue:** `logger.info("shutdown")` sits in the `finally`, which also runs when `build_jwt_verifier`
raises (`:106`) or the config load fails. The pod then logs `shutdown` with no preceding `started`,
which reads as a clean stop rather than a boot failure.

**Fix:** Set a `serving = False` flag immediately before `yield` and guard the line on it, or move
the line into an `else:` on the `try`.

### IN-25: An Apple grace-period notification without `signedRenewalInfo` becomes a 500 Apple retries for days

**File:** `src/nativespeaker/api/auth/app_store.py:152`

**Issue:** `if data.signedRenewalInfo is None: return _crossed(payload, transaction, None, ...)`
leaves `grace_period_expires_at=None` (`:87`). For `status = BILLING_GRACE_PERIOD`,
`term_end_for` (`store_notifications.py:66-67`) reads that field, so `SubscriptionsService.ingest`
(`services/subscriptions.py:112-117`) finds an entitled status with no term and raises
`InternalError`. Apple retries a non-2xx on its full multi-day schedule, so the subscriber's grant
is never updated and the log fills with `store_notification_without_term`. Apple sends
`signedRenewalInfo` with every auto-renewable subscription notification, so this is defensive
rather than live — but it is the one arm where a missing optional produces an unbounded retry loop
instead of a drop.

**Fix:** Treat grace-with-no-renewal-payload as the same "verified and unwritable" arm the
`rawStatus is None` branch already uses at `:143`, so the delivery is acknowledged and dropped
rather than retried forever.

### IN-26: Each distinct unknown `kid` costs one synchronous JWKS refetch before the negative cache can hold it

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:205`

**Issue:** `PyJWKClient.get_signing_key_from_jwt` refetches the key set whenever a `kid` misses the
cache. `_record_unknown` suppresses *repeats* of a given `kid`, but the first occurrence of each
distinct value still spends one network fetch, up to `fetch_timeout_seconds=3.0` (`:130`), on a
`run_in_threadpool` worker (`dependencies.py:82`). A caller cycling unique `kid` values therefore
converts requests into blocked worker threads at a 1:1 rate. Envoy's per-IP limiting bounds this
for a single source, and the negative cache is the designed mitigation, so this is noted rather
than filed higher.

**Fix:** If it ever matters, add one monotonic "last forced refresh" stamp beside `_unknown_kids`
and skip the forced refresh when a refresh already happened inside the last `unknown_kid_ttl`.

### IN-27: `write_bits`' docstring claims a confirmation check the code does not make

**File:** `src/nativespeaker/api/auth/devicecheck.py:178`

**Issue:** *"Write both bits, accepting only Apple's explicit confirmation as success."* The body
calls `_reject_or_retry` (`:181`), which returns for any 2xx and inspects no body. The write is
accepted on the status class alone; there is no confirmation check. `write_bits_with_retry`'s own
comment at `:223` is accurate about the blind-write semantics, so the two disagree.

**Fix:** Reword to "accepting any 2xx as success", or check the body if Apple's response carries a
confirmable field.

### IN-28: A comment says "the raw int, never `status`" directly above the line that reads `data.status`

**File:** `src/nativespeaker/api/auth/app_store.py:142`

**Issue:** The comment at `:142` explains the `data.rawStatus is None` test on `:136` but sits at
the bottom of that branch, immediately above `status = None if data.status is None else
_APPLE_STATUSES.get(data.status)` (`:145`) — which reads exactly the attribute the comment says is
never read. The logic is correct (the two lines together classify present-but-unknown as
`UnknownStoreSubscriptionStatus`); only the placement misleads.

**Fix:** Move the comment up to `:136`, beside the `rawStatus` test it explains.

### IN-43: `Chat.human_messages` is dead code

**File:** `src/nativespeaker/api/tables/chats.py:57-59`
**Issue:** `human_messages` has no reader anywhere in `src/` or `tests/`. Its twin `ai_messages` has exactly one (`services/chats.py:121`, the follow-up message cap), so the pair was written symmetrically and only half of it was ever needed.
**Fix:** delete the property. A reader that needs it can filter `chat.messages` at the call site, as `services/chats.py` already does for its own limit.

### IN-44: `count_chats` declares a return type its expression cannot guarantee, and is the one crud predicate written without `col()`

**File:** `src/nativespeaker/api/crud/chats.py:26-28`
**Issue:** Two small inconsistencies in one two-line method. `AsyncSession.scalar` is typed to return `Any | None`, but the signature promises `int`; the caller `services/chats.py:91` does `chats_count >= self.chats_limit` with no guard, so the annotation is the only thing standing between a `None` and a `TypeError`. (`select(func.count())` cannot in fact return `None`, so this is a type-safety lie rather than a live bug.) Separately, `Chat.user_id == user_id` is the only filter predicate in the whole crud layer that omits `col()`; every other statement in this file and in `grants.py`, `identities.py`, `purchases.py` and `subscriptions.py` uses it.
**Fix:**

```python
    async def count_chats(self, user_id: UUID) -> int:
        statement = select(func.count()).select_from(Chat).where(col(Chat.user_id) == user_id)
        # `COUNT(*)` always returns a row, so the coalesce is documentation of that, not a fallback.
        return (await self.session.scalar(statement)) or 0
```

### IN-45: `PubSubPushRequest.subscription` is declared and never read

**File:** `src/nativespeaker/api/schemas/webhooks.py:40`
**Issue:** No code path reads `.subscription`. The sibling field `messageId` was removed from `PubSubPushMessage` on exactly this reasoning (`:22-26`: *"nothing read it ... so requiring it made an envelope shape change a permanent 422 in exchange for validating a value the service never used"*), and `subscription` survives the same argument only because it is optional. It is harmless but it reads as a value the push handler authenticates against, which it does not — the push token is (`app/dependencies.py:207`).
**Fix:** delete the field, or add a one-line comment saying it is carried for readability only and that authenticity rests on the bearer token alone.

### IN-46: The two sibling grant writers fail closed on a missing usage row at different points, so the same broken invariant answers 500 on one route and 403 on the other

**File:** `src/nativespeaker/api/crud/grants.py:164-169` versus `:240-241` and `:284-287`
**Issue:** `activate_anonymous_device_grant` raises `MissingUsageRowError` inside the lock loop, before any refusal branch is evaluated — so an account with a broken usage row gets an opaque 500 even when the real answer was `identity_not_anonymous`. `activate_registered_account_grant` stores the same lookups in `locked_usage` and only raises at `:287`, for the superseded grant alone — so the same broken row on a grant this call refuses over goes unreported, and the caller gets a 403. The comment at `:166-168` claims the anonymous writer behaves *"exactly as the registered sibling and `lock_grants_of` do"*, which is true of `lock_grants_of` (`crud/subscriptions.py:93-96`) and not true of the registered sibling. Both are fail-closed, so nothing is granted wrongly; what differs is which failure an operator sees for one state.
**Fix:** pick one and make the comment true. The registered writer's shape is the better one (a refusal that precedes any write should not be masked by an unrelated broken row), so defer the anonymous writer's raise to the grant it actually converts, or — if the tripwire is meant to be loud everywhere — raise in both loops and correct `:166-168`.

### IN-47: `EntitlementType` restates `AccessGrantSource` member-for-member, with the coupling enforced only at runtime

**File:** `src/nativespeaker/api/schemas/auth.py:60-66`
**Issue:** `EntitlementType` is `AccessGrantSource`'s four members plus `none`, and `services/sync.py:58` bridges them with `EntitlementType(grant.source.value)`. A fifth grant source added to `tables/grants.py:11-16` without a matching edit here becomes a `ValueError` — a 500 on `/auth/sync` and on the body every claim and restore reads back after commit. That is fail-closed, which is right, but the coupling is invisible from either file and nothing in `tests/` pins it.
**Fix:** derive the wire enum from the table enum, or add a one-line test that the two member sets agree:

```python
def test_the_wire_enum_covers_every_grant_source():
    assert {member.value for member in AccessGrantSource} | {"none"} \
        == {member.value for member in EntitlementType}
```

### IN-60: Dead disjunct in the store-term guard

**File:** `src/nativespeaker/api/services/subscriptions.py:112-114`
**Issue:** `starts_at = min(notification.purchased_at or self.evaluated_at, self.evaluated_at)` (line 110) makes `starts_at <= self.evaluated_at` unconditionally true, so `term_ends_at <= starts_at` implies `term_ends_at <= self.evaluated_at`. The middle disjunct can never be the one that fires; it reads as a third independent check that is not one.
**Fix:** drop `or term_ends_at <= starts_at`, or add a comment saying it is kept only to document the inverted-term case.

### IN-61: `resilence_config` is misspelled in the `LLMService` constructor

**File:** `src/nativespeaker/api/services/llm.py:18`
**Issue:** the parameter is `resilence_config` (missing `i`), so every caller must spell the typo. `app/lifespan.py` constructs the service, and any keyword call has to repeat it.
**Fix:** rename to `resilience_config` and update the construction site.

### IN-62: `/` and `/examples` build a `ChatService` — and therefore a database session and a `QuotaService` — for routes that touch no database

**File:** `src/nativespeaker/api/routers/examples.py:16`, `src/nativespeaker/api/routers/root.py:15`
**Issue:** both handlers only read `service.examples` / `service.supported_languages`, which come from `AppConfig`. `get_chat_service` (`app/dependencies.py:123-136`) pulls in `get_db` and `get_quota_service`, so every request to these two routes checks out a pooled connection it never uses.
**Fix:** give the two routes a config-only dependency (e.g. `Depends(get_config)`) and read `config.examples` directly, leaving `get_chat_service` for the routes that write.

### IN-63: The preflight and the locked writer evaluate the same four refusals in different orders

**File:** `src/nativespeaker/api/services/auth.py:235-259`
**Issue:** the preflight order is registered-repeat → `OtherActiveGrantHeld` → `holds_grant_of_source(registered)` → `ActiveGrantOutsideItsTerm` → `has_prior_free_grant`. `crud/grants.py:249-278` runs registered-repeat → `other_grant_held` → `unseen_active_grant` → `spent_slot` → `registered_grant_held`, i.e. the lifetime registered-grant question moves from third to last. Every one of these ends in the same 403 `operation_not_allowed`, so nothing is client-visible today, but two orderings of one decision are two things to keep in step, and D-09 states a single order.
**Fix:** reorder the crud's `holds_grant_of_source(registered_account_grant)` check to sit immediately after the `other_grant_held` arm, so both sites read in D-09's order top to bottom.

### IN-64: An existing chat with no messages is reported as a missing chat

**File:** `src/nativespeaker/api/services/chats.py:156-160`
**Issue:** `get_messages` raises `InvalidChatError` (404) when the message list is empty, conflating "this chat id addresses nothing you own" with "this chat is empty". `create_chat` always commits two messages with the chat, so the state is unreachable today — but `list_chats` would still advertise such a chat while `GET /chats/{id}` 404s on it.
**Fix:** resolve the chat first (`chats_db.get_chat`) and return `[]` for an owned chat that holds no messages.

### IN-65: `ask_llm` accepts either resolved mode from either call site

**File:** `src/nativespeaker/api/services/chats.py:66-75`
**Issue:** `create_chat` and `send_message` share `ask_llm`, which accepts `analyze` and `follow_up` interchangeably. A model answering `follow_up` to a first-turn analysis, or `analyze` to a follow-up, is persisted and returned rather than treated as a schema violation.
**Fix:** pass the expected mode in and reject the other one with `AnalysisError`, so the call site's contract is checked rather than assumed.

### IN-66: `list_chats` lacks the return annotation its four siblings carry

**File:** `src/nativespeaker/api/routers/chats.py:21-22`
**Issue:** every other handler in the file annotates its return type; `list_chats` does not, so only `response_model` documents the shape and the type checker validates nothing about the comprehension on line 24-26.
**Fix:** add `-> list[ChatResponse]`.

### IN-67: `/auth/sync` returns the same account-state body as the claim routes without `Cache-Control: no-store`

**File:** `src/nativespeaker/api/routers/auth.py:188-192`
**Issue:** `claim_anonymous_grant` (line 128), `claim_registered_grant` (line 151), `restore_subscription` (line 179) and `/users/me` (`routers/users.py:24`) all set `no-store` on responses carrying entitlement or account state; `/auth/sync` returns an identical `SyncResponse` and sets nothing. Nothing is exploitable — it is a POST, which no intermediary caches by default — but the header is the file's own convention for this body and it is missing on exactly one route.
**Fix:** take `response: Response` and set `response.headers["Cache-Control"] = "no-store"`, as the three sibling handlers do.

### IN-86: `_claim` and `_restore` silently discard their own defaults when a case passes a partial body

**File:** `tests/e2e/test_claim_registered_grant.py:72`, `tests/e2e/test_restore_subscription.py:148`
**Issue:** `payload = {"challenge_id": handle, "device_token": DEVICE_TOKEN} if not body else body` means the `handle` argument is silently ignored the moment any keyword is supplied. Today's only caller (`:288`) happens to re-supply `challenge_id`, but a future case writing `_claim(client, subject, handle, device_token="x")` would post a body with no `challenge_id` and take a 422 for a reason it is not testing. `_restore` has the same shape for `provider`/`restore_proof`.
**Fix:** merge rather than replace — `payload = {"challenge_id": handle, "device_token": DEVICE_TOKEN} | body` — and let a case pass `device_token=None`/`ChallengeSentinel` when it wants a field removed.

### IN-87: two `httpx.AsyncClient` instances are constructed per test and never closed

**File:** `tests/e2e/conftest.py:476`, `tests/e2e/conftest.py:577`
**Issue:** `real_google_play_seam` and `unconfigured_google_play` build `httpx.AsyncClient(transport=httpx.MockTransport(...))` inside `PlayDeveloperSubscriptions` and restore the previous state without closing them, so each test using either fixture leaks one client. The transport is a mock, so no socket is held, but the objects raise `ResourceWarning` under `-W error::ResourceWarning`.
**Fix:** keep a reference and `await client.aclose()` in the fixture's `finally`, or build the client with `async with` around the `yield`.

### IN-88: the raise-site control cannot see an aliased import of `NotificationRejected`

**File:** `tests/e2e/refusal_sites.py:21-30`
**Issue:** `_called_name` matches only the literal callee name `NotificationRejected`. A new module raising `from nativespeaker.api.errors import NotificationRejected as Rejected` and calling `Rejected(stage=...)` is invisible to both `files_raising_the_refusal()` and `raised_refusal_stages()`, so it shrinks both sides of the equalities at `test_app_store_webhook.py:270` / `test_google_play_webhook.py:361` instead of failing them — the exact failure mode the module docstring says it exists to prevent.
**Fix:** resolve the local binding too — walk `ast.ImportFrom` nodes for `module == "nativespeaker.api.errors"` and collect every `alias.asname or alias.name` bound to `NotificationRejected`, then match `_called_name` against that set.

### IN-89: mixed absolute/relative imports of the same helpers, and a private helper imported across test modules

**File:** `tests/e2e/test_challenge_store.py:12`, `tests/e2e/test_google_play_webhook.py:19,29` vs `tests/e2e/test_app_store_webhook.py:28-29`; `tests/e2e/test_users_me.py:12`
**Issue:** `refusal_sites` and `conftest` are imported as `from e2e.…` in two modules and `from .…` in two others, so the package's own import convention is decided per file. Separately, `test_users_me.py` does `from .test_sync import _stored_provider`, taking a private name from a sibling **test** module, which couples the two files' collection order and refactors.
**Fix:** settle on the relative form everywhere, and move `_stored_provider` into `tests/e2e/conftest.py` beside `seed_identity`, where both modules already import from.

### IN-90: `firebase_token` is session-scoped with a one-hour credential and no refresh

**File:** `tests/e2e/conftest.py:100-119`
**Issue:** the Identity Toolkit ID token is minted once per session and reused by `async_client` for every module. `test_sign_out_all.py:96-99` documents this exact hazard for tokens built at collection time ("`make_token` expires an hour later: a session that takes that long to reach this module would fail these cases at the JWT check instead of at the barrier"), but the session-scoped real credential carries the same expiry and no guard. A slow or partially-parallel e2e session fails late modules at the barrier with a misleading `auth_required`.
**Fix:** either narrow the fixture to `scope="module"`, or record `data["expiresIn"]` and re-sign in when the remaining lifetime drops below a margin.

### IN-91: the two claim e2e modules carry a verbatim duplicated helper block

**File:** `tests/e2e/test_claim_registered_grant.py:36-46, 77-115` vs `tests/e2e/test_claim_anonymous_grant.py:133-143, 160-200`
**Issue:** `REFUSED`, `REFUSED_BODY`, `SEEDED_AGO`, `LAPSED_AGO`, `_challenge_for`, `_row_counts`, `_grants_of`, `_usage_of` and `_identity_of` are byte-for-byte identical in both modules (only `_row_counts`'s ordering differs cosmetically). The refusal-body constants in particular are the contract both routes share, and two copies can drift apart silently — the same failure mode `refusal_sites.py`'s own docstring records for `REFUSAL_FILES`.
**Fix:** move the nine names into `tests/e2e/conftest.py` next to `seed_grant`/`seed_identity` and import them in both modules.

### IN-92: the rollback-isolation case depends on another class's fixture teardown having run in the same session

**File:** `tests/e2e/test_challenge_store.py:411-415`
**Issue:** `test_no_row_this_module_wrote_survives_its_test` asserts a global count of committed rows carrying `preauth_issuer == ISSUER` is zero. The only sweep of those rows lives in `_contended_challenge`'s teardown (`:104-110`), which runs only when `TestTheClaimSerializesConcurrentAttempts` runs. Selecting this class alone (`-k TestTheRollbackIsolates`) after any interrupted run leaves the case red with no path to self-heal, and the failure names rollback isolation rather than the leftover row that actually caused it.
**Fix:** move the delete-by-issuer sweep into a module-scoped autouse fixture that runs once at module setup as well as at teardown, so any module-owned leftovers are cleared before the first case reads the count.

### IN-100: Wall-clock upper bounds run in the default suite despite the `timing` marker existing to separate them
**File:** `tests/unit/test_firebase_retry.py:182-187`, `tests/unit/test_devicecheck_adapter.py:319-326`
**Issue:** `test_a_budget_that_was_not_exhausted_pays_no_wait_control` asserts `time.monotonic() - started < self.FLOOR_SECONDS` — an upper bound on wall clock, the classic flake shape, and the one assertion in this slice a loaded CI runner or a GC pause can fail for reasons unrelated to the code. `pyproject.toml` registers the `timing` marker as "report separately with `-m timing`", but `addopts = "-v --tb=short -m 'not e2e and not schema'"` does not deselect it, so these run on every unit invocation.
**Fix:** Either bound the control on the *number of attempts* rather than on elapsed time (`assert len(adapter.calls) == 1` already distinguishes it), or deselect the marker by default and run it in a separate CI step.

### IN-101: Three copies of the fresh-subprocess runner, two of them hardcoding the timeout the shared one names
**File:** `tests/unit/test_claim_ordering.py:130-131`, `tests/unit/test_adapter_interfaces.py:36-37`
**Issue:** `tests/unit/error_tree.py:19-26` already exports `fresh_interpreter(snippet)` with a named `SUBPROCESS_TIMEOUT_SECONDS = 120` and a `PYTHONPATH` that carries `tests/` into the child. Both files above redefine a private `_run` with the same body, a bare literal `timeout=120`, and no `PYTHONPATH`, so their snippets can never import a `unit.*` helper.
**Fix:** Import and use `unit.error_tree.fresh_interpreter` in both, and delete the two `_run` copies.

### IN-102: `httpx.AsyncClient` is constructed per call and never closed
**File:** `tests/unit/test_devicecheck_adapter.py:78`, `tests/unit/test_google_play_notifications.py:126`
**Issue:** `_adapter()` and `_play_reader()` each build a fresh `httpx.AsyncClient(transport=httpx.MockTransport(...))` on every invocation and never `aclose()` it. Harmless with `MockTransport`, but it leaves one unclosed client per parametrised case and will start emitting `ResourceWarning` the moment a case is pointed at a real transport.
**Fix:** Make them async fixtures that `yield` the adapter and `await client.aclose()` on teardown.

### IN-103: `assert assert_tree_total() is None` asserts the return type of a procedure, not the property under test
**File:** `tests/unit/test_error_registry.py:52`
**Issue:** `assert_tree_total` (`tests/unit/error_tree.py:90-94`) is annotated `-> None` and either raises or returns `None`; `is None` can only fail if the function grows a return value. The property actually under test is "does not raise", which the bare call already expresses.
**Fix:** `assert_tree_total()` on its own line, with the docstring stating that a raise is the failure.

### IN-104: Module-level exception instances are raised repeatedly against module-scoped clients
**File:** `tests/unit/test_exception_handlers.py:40-67`, `tests/unit/test_create_user_precedence.py:405-410`
**Issue:** `CASES`, `REJECTION_CASES`, `APP_ERROR_CASES` and the `EveryProviderStageRejectionConsumes` parametrisation construct exception *instances* at import time and hand the same object to `_make_raise_route` / `adapter.script` for the whole session. Re-raising one object appends to its existing `__traceback__` and can chain `__context__`, so the shared instances accumulate frames (and the request-scoped locals those frames hold) for as long as the module-scoped `handler_client` lives, and any assertion about `__cause__`/`__context__` becomes order-dependent.
**Fix:** Store the class plus its arguments and construct inside the route/parametrisation, e.g. `("queue_full", lambda: QueueFullError(30), 503, "service_unavailable")` with `_make_raise_route` calling the factory.

### IN-105: The slice gives two contradictory rules for spying on the structlog proxy, and the stated hazard does not reproduce
**File:** `tests/unit/test_claim_precedence.py:65-70` vs `tests/unit/test_exception_handlers.py:91-95,558-564,608-613`
**Issue:** `_handler_warnings` documents that patching a *level attribute* is forbidden because "structlog's lazy proxy builds those on demand, so monkeypatch's undo would freeze one onto the proxy for the rest of the session", yet six sites in this slice do exactly that (`test_exception_handlers.py`, `test_create_user_precedence.py:114-116`, `test_firebase_adapter.py:108-112`, `test_google_play_notifications.py:216-220`). The freeze is real — after undo, `vars(logger)["warning"]` is a bound method — but the consequence claimed is not: `structlog.testing.capture_logs` mutates the configured processor list in place, so a frozen binding is still captured (verified against the installed structlog). One of the two comments is misleading whichever way the codebase settles.
**Fix:** Pick one technique, apply it everywhere, and correct or delete the docstring at `test_claim_precedence.py:66-68`.

### IN-106: Test modules import fixtures and constants from sibling test modules
**File:** `tests/unit/test_app_store_notifications.py:32-38`, `tests/unit/test_config.py:37`, `tests/unit/test_google_play_notifications.py:43-44`
**Issue:** `test_app_store_notifications` imports `LAPSED`, `PUBLISHED_STATES`, `UNEXPIRED`, `UNKNOWN_STATE` and `_read` from `unit.test_google_play_notifications`; `test_config` imports `install_counted_transport` from `unit.test_jwks_offload`. Collecting one file now executes another whole test module, and a rename inside the Google file silently changes what the Apple file asserts (`TestRevokedIsAnAppleOnlyWord` at line 451 depends on it entirely). `conftest.py` and `error_tree.py` already exist as the sanctioned homes for shared scaffolding.
**Fix:** Move the shared Play state vocabulary and the `_read` helper into `tests/unit/conftest.py` (or a `tests/unit/store_notifications.py` helper module alongside `error_tree.py`), and import from there on both sides.

### IN-127: `test_the_state_columns_are_read_in_python_not_filtered_in_sql` cannot fail

**File:** `tests/unit/test_identities_crud.py:247-252`
**Issue:** The case drives resolution twice with differently seeded rows and asserts the two compiled statements are equal. `IdentitiesDB.resolve` constructs its statement from `(issuer, subject)` before it has seen any row, and the stub session returns the seeded row regardless of the statement — so the two strings are identical by construction for every possible implementation, filtering in SQL included. It is a green assertion that has never been shown to fail.
**Fix:** Delete it and rely on the strengthened WR-120 assertion, which measures the property the name claims.

### IN-128: Two assertions in `test_models.py` cannot fail

**File:** `tests/unit/test_models.py:136-146, 267-269`
**Issue:** `test_content_never_empty` builds `content={"response": "Ok"}` and then asserts `dumped["content"] != {}` and `"response" in dumped["content"]` — restatements of the literal it just passed in. `test_service_error_base` asserts `isinstance(AppError("Base error"), Exception)`, which holds for any class in the tree.
**Fix:** Drop both, or turn the first into the property it wants: `MessageResponse` must refuse an empty `content` (`pytest.raises(ValidationError)` on `content={}`), which is a rule that can actually be broken.

### IN-129: The quieted-library leak check is order-dependent and vacuous alone

**File:** `tests/unit/test_logging.py:320-327`
**Issue:** `test_no_quieted_library_level_outlives_the_test_that_set_it` reads process-global `logging` state and depends on being collected after every other case in the file. Run in isolation it passes without exercising anything (confirmed: 1 passed), and under any randomised or sharded ordering it becomes either vacuous or a spurious failure attributable to a module it does not own.
**Fix:** Make it a fixture-level assertion instead — have `_reset_logging` assert, in its teardown, that the levels it is about to restore are the ones it snapshotted — so the guarantee is checked per test rather than once at a position in the file.

### IN-130: `assert len(_production_family()) > 8` is a stale threshold

**File:** `tests/unit/test_rejection_vocabulary.py:204-206`
**Issue:** The tree currently holds roughly sixty classes; the control would still pass with fifty of them deleted. `test_the_tree_spells_exactly_the_recorded_event_names` (line 156) already pins the exact set, which makes this weaker check redundant rather than a second line of defence.
**Fix:** Replace with `assert len(_production_family()) == len(EVENT_NAMES)`, which ties the coverage control to the one written-down vocabulary.

### IN-131: The greppability walk exempts any computed event name

**File:** `tests/unit/test_logging.py:225-247`
**Issue:** `_literal_event_names` yields only `ast.Constant` first arguments, so `logger.warning(f"{prefix}_rejected")` or `logger.warning(EVENT)` is skipped rather than flagged — and a non-literal event name is precisely the record an `^[a-z_]+$` alert filter cannot key on. No such call exists today (51 logger calls, 0 non-literal), so the hole is latent.
**Fix:** Collect non-literal first arguments into a second offender list and assert it empty, with the same `_SRC` walk.

### IN-132: The upgrade suite's five challenge outcomes are decided by a hand-written copy of the store's conditional updates

**File:** `tests/unit/test_upgrade_precedence.py:26-29, 379-461`
**Issue:** `TestTheRejectionsThatSpendNothing` reaches `challenge_expired` and `challenge_consumed` through `conftest.FakeChallengeStore`, whose `claim`/`consume` restate the `WHERE` clauses of `ChallengesDB.claim`/`consume` in Python. The two agree today, and `verify_binding` is imported from production rather than copied — but the store is, by the file's own comment, "the system's only serialization point", and a drift there leaves these five green. `tests/schema/test_grant_locks.py` is the only place the real statements run, and it is deselected by the default `addopts`.
**Fix:** No change to the fake; add one unit case that compiles the real statements and asserts their predicate columns, so a `WHERE` clause dropped from `ChallengesDB.claim` fails inside the default selection.

### IN-133: The wall-clock JWKS cases run in the default unit selection

**File:** `tests/unit/test_jwks_offload.py:160, 179`
**Issue:** `pyproject.toml` documents the marker as "timing: marks tests whose assertion is wall-clock dependent (report separately with `-m timing`)", but `addopts = "-m 'not e2e and not schema'"` does not deselect it, so both 0.4-second heartbeat measurements run on every unit invocation. Three consecutive runs on this machine were stable (8 passed each), and the floor is derived from the observed window rather than pinned — so this is a note, not an observed flake.
**Fix:** Either deselect `timing` in `addopts` and run it as its own job, or delete the marker's "report separately" wording so the configuration and the documentation agree.

### IN-148: `_Harness.owned_user_ids` is dead in `test_create_race.py`
**File:** `tests/schema/test_create_race.py:36,59`
**Issue:** The field is declared and read in the teardown union at line 59, but nothing in the module ever appends to it — the list is always empty. It was copied from `test_create_atomicity.py`, where `commit_user` (line 82) and the happy-path case (line 350) do populate it. Harmless today because teardown also collects user ids via the identity rows, but a future case that commits a user with no identity row will silently leak.
**Fix:** Delete the field and the `{*subject.owned_user_ids, ...}` union, or populate it from the module's own committers.

### IN-149: `_Harness.connection()` is never called
**File:** `tests/schema/test_create_atomicity.py:37-39`
**Issue:** Dead method. Every caller in the file uses `harness.engine.begin()` directly (lines 53, 77, 89, 106, 121, 126, 277).
**Fix:** Remove it.

### IN-150: The tier-sizing invariant is asserted twice, in two files
**File:** `tests/schema/test_apply_rollback.py:82-88`
**Issue:** `test_registered_is_not_smaller_than_anonymous` and `test_constraints.py:459-466 test_the_registered_allowance_is_never_below_the_anonymous_one` assert the same property with different queries. The `test_constraints.py` copy is strictly stronger (it also pins that both seed ids still exist, so the comparison cannot go vacuous).
**Fix:** Keep the `test_constraints.py` copy and drop the one in `test_apply_rollback.py`.

### IN-151: The rollback proof only looks inside `core` and `audit`
**File:** `tests/schema/test_apply_rollback.py:42-65`
**Issue:** The migration's rollback is `DROP SCHEMA ... CASCADE` on those two schemas (migration:326-327), and the test checks exactly that plus an empty `_pogo_migration`. Any object a future migration edit creates outside them — a `CREATE EXTENSION`, a `public` type or function, a role, a `GRANT` — survives the rollback and this test stays green. The class docstring's claim ("The migration's own rollback section removes both schemas") is accurate; the file's docstring's claim ("a clean rollback") is broader than what is measured.
**Fix:** Snapshot the full object set before the apply and assert equality after the rollback:
```python
CATALOGUE = ("SELECT 'c:'||oid::regclass::text FROM pg_class WHERE relnamespace "
             "NOT IN ('pg_catalog'::regnamespace,'information_schema'::regnamespace) "
             "UNION SELECT 'n:'||nspname FROM pg_namespace "
             "UNION SELECT 'e:'||extname FROM pg_extension")
before = {r[0] for r in await connection.fetch(CATALOGUE)}
...  # apply, then rollback
assert {r[0] for r in await connection.fetch(CATALOGUE)} == before
```

### IN-152: Redundant status-range assertion
**File:** `tests/schema/test_restore_race.py:348-350`
**Issue:** `assert 400 <= status_of(loser) < 500` is fully subsumed by the next line's `assert status_of(loser) == 404`.
**Fix:** Drop line 349.

### IN-153: Typo in a class name
**File:** `tests/schema/test_constraints.py:455`
**Issue:** `TestTheTierSizingInvariantTheConversionRelisOn` — "Relis" for "Relies". The name appears in every test-id string this class produces.
**Fix:** Rename to `TestTheTierSizingInvariantTheConversionReliesOn`.

### IN-154: The challenge binding CHECK is never exercised for the "neither form" case
**File:** `tests/schema/test_constraints.py:586-596`
**Issue:** The CHECK at migration:311-319 rejects three shapes: both binding forms present (covered at line 586), the preauth arm with a NULL issuer, and a row carrying *neither* binding (`bound_external_identity_id`, `preauth_issuer` and `preauth_subject` all NULL). Only the first is tested. A future edit that relaxed the CHECK to `bound_external_identity_id IS NULL OR preauth_issuer IS NULL` would still reject the tested shape and admit an unbindable challenge row.
**Fix:** Add
```python
async def test_challenge_with_neither_binding_form_rejected(self, conn):
    """The third shape: a challenge bound to nothing can never be completed against a caller."""
    async with _rejects(conn, asyncpg.CheckViolationError):
        await _insert_challenge(conn, preauth_issuer=None, preauth_subject=None)
```

### IN-155: The per-round "partial read" bound in the sync race cannot be violated
**File:** `tests/schema/test_sync_lock_freedom.py:177-199`
**Issue:** `entitlement.monthly_used` is read from a single `core.user_monthly_usage` row, and the raced charge changes that row by exactly one. Under READ COMMITTED the value is therefore always either the pre-charge or the post-charge count, so `assert entitlement.monthly_used in (before, before + 1)` can never fail — a "partial read straddling the commit" is not a state a one-row read can produce. The genuinely load-bearing assertion in this case is the final `stored_usage(harness) == SEEDED_USED + ROUNDS` (line 201), which does prove no charge was lost across 12 races, and the `_DEADLINE_SECONDS`/`_NO_WAIT` instruments, which do prove sync took no lock.
**Fix:** Either state the case's real subject in the docstring (no lost update, no lock wait) and drop the per-round bound, or make the bound falsifiable by having the charge also move a second row the entitlement read joins, so a torn multi-row read becomes observable.

### IN-156: Underscore-private helpers shared across four schema modules
**File:** `tests/schema/test_grant_locks.py:29`
**Issue:** `test_grant_locks.py` imports `_clean` and `_notification` from `test_subscription_ingestion`; `test_restore_race.py:20` and `test_subscription_race.py:18` import `_RacingSession`, `read` and `scalar` from `test_claim_race`; `test_registration_pairing.py:14` imports the `harness` fixture from `test_create_atomicity`. Renaming any one of these private names breaks three other modules at collection time, and the reverse coupling (`test_grant_locks` depending on a *notification* fixture) is not discoverable from either file's docstring.
**Fix:** Promote the genuinely shared pieces (`_RacingSession`, `read`, `scalar`, `_clean`, `_notification`) into `tests/schema/helpers.py` under public names, and leave each `test_*.py` owning only what it alone uses.

### IN-157: "Refused ahead of the first write" is claimed but not measured
**File:** `tests/schema/test_subscription_ingestion.py:692-705,707-721`
**Issue:** Both cases assert only `await buyer.counts() == (0, 0, 0, 0)` and then comment "Refused ahead of the first write, so no half of the delivery is durable." An ingest that wrote both rows and *then* raised would produce exactly the same counts, because the session rolls back on exit. The file already has the instrument that distinguishes the two — `_InterruptedSession` / `buyer.interrupt()` (lines 92-110, 160-168) reads the transaction's own uncommitted state before failing, and `TestOneGoogleDeliveryIsOneTransaction` uses it to assert `held == (1, 1)`.
**Fix:** Assert the ordering, not just the durability — e.g. record statements with a `before_cursor_execute` listener and assert no `INSERT`/`UPDATE` was emitted, or reuse the interrupt session to show the transaction held `(0, 0)` at the moment of the refusal.

---

_Reviewed: 2026-09-10T03:01:16Z_
_Reviewer: Claude (gsd-code-reviewer, eight-way parallel split)_
_Depth: standard_
