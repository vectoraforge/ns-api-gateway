---
phase: 41-post-auth-claim-anonymous-grant
reviewed: 2026-09-10T00:52:47Z
depth: standard
files_reviewed: 142
files_reviewed_list:
  - .dockerignore
  - .env.example
  - .gitignore
  - AGENTS.md
  - Dockerfile
  - config/config.yaml
  - docker-compose.yml
  - k8s/templates/NOTES.txt
  - k8s/templates/deployment.yaml
  - k8s/templates/httproute-app.yaml
  - k8s/templates/httproute-auth.yaml
  - k8s/templates/httproute-health.yaml
  - k8s/templates/httproute-webhooks.yaml
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
  - src/nativespeaker/api/crud/__init__.py
  - src/nativespeaker/api/crud/chats.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/crud/violations.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/logs.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/__init__.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/routers/webhooks.py
  - src/nativespeaker/api/schemas/api.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/schemas/llm.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/llm.py
  - src/nativespeaker/api/services/quota.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/services/sync.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/chats.py
  - src/nativespeaker/api/tables/grants.py
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
  - tests/unit/test_users.py
  - tests/unit/test_users_me.py
  - uv.lock
findings:
  critical: 1
  warning: 37
  info: 35
  total: 73
status: issues_found
---

# Phase 41: Code Review Report

**Reviewed:** 2026-09-10T00:52:47Z
**Depth:** standard
**Files Reviewed:** 142
**Status:** issues_found

This is an incremental re-review. The scope is every source and test file changed since the previous 41-REVIEW.md commit (`def8063`) — 521 commits of phase 35 through 40 review-and-fix work. It was split across seven parallel reviewers over disjoint module groups with disjoint finding-ID blocks (A infra/app, B auth/schemas, C crud/tables, D services/routers, E e2e+schema tests, F unit tests A-G, G unit tests H-Z) and merged here.

## Summary

### Reviewer A



### Reviewer B



### Reviewer C



### Reviewer D



### Reviewer E



### Reviewer F



### Reviewer G



## Critical Issues

### CR-80: The e2e lifespan fixture leaks `setup_logging`'s global state, and the full suite is red

**File:** `tests/e2e/conftest.py:213-217`
**Issue:** `_app_lifespan` enters the real application lifespan, which calls
`nativespeaker.api.logs.setup_logging()`. That function clears the root handler list,
sets the root level, and pins the nine `_QUIETED_LIBRARIES` loggers to `WARNING`
(`src/nativespeaker/api/logs.py:18-20,58-64`). The fixture restores none of it, and
`logging` state is process-global, so every later test in the session inherits it.

`tests/unit/test_logging.py:319-327` is a tripwire written for exactly this
(`"A level still pinned here escaped this file and would silence those nine for every
later test in the session."`). It fails whenever an e2e module runs before it in the same
process — which is the default collection order, because `tests/e2e` sorts before
`tests/unit`.

Reproduced on a clean tree:

```
$ .venv/bin/pytest -q -p no:cacheprovider -m ""
FAILED tests/unit/test_logging.py::test_no_quieted_library_level_outlives_the_test_that_set_it
1 failed, 2346 passed in 126.17s

$ .venv/bin/pytest tests/e2e/test_challenge_store.py tests/unit/test_logging.py -q -m ""
E   AssertionError: assert {'google.auth': 30, 'httpcore': 30, 'httpx': 30, 'langchain': 30, ...} == {}
```

It is invisible in normal use only because `pyproject.toml`'s default
`addopts = -m 'not e2e and not schema'` deselects the polluter. The consequence beyond the
red test is that the nine libraries stay silenced for the rest of the session, so any
later case that depends on library log output reads a quieted logger.

**Fix:** snapshot and restore the state `setup_logging` writes, in the fixture that causes
it to run:

```python
import logging

from nativespeaker.api.logs import _QUIETED_LIBRARIES


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def _app_lifespan():
    """Start app lifespan (config, DB engine, verifier, LLM service).

    The lifespan calls `setup_logging`, which mutates process-global `logging` state: the
    root handlers and level, plus the nine quieted library levels. None of it is scoped to
    this fixture, so it is snapshotted here and put back -- `tests/unit/test_logging.py`
    carries the tripwire that fails when it is not.
    """
    root = logging.getLogger()
    pinned = {name: logging.getLogger(name).level for name in _QUIETED_LIBRARIES}
    restore = (list(root.handlers), root.level)
    try:
        async with app.router.lifespan_context(app):
            yield app
    finally:
        for name, level in pinned.items():
            logging.getLogger(name).setLevel(level)
        root.handlers[:] = restore[0]
        root.setLevel(restore[1])
```

Verify with `.venv/bin/pytest -q -p no:cacheprovider -m ""` — it must be fully green.

## Warnings

### WR-01: The circuit breaker relights its whole tally after every reset window, so a long outage runs mostly closed

**File:** `src/nativespeaker/api/resilience.py:53-63`, `src/nativespeaker/api/resilience.py:81-88`

**Issue:** `before_call` zeroes `_failure_count` on the elapsed arm (`resilience.py:60`), and
`record_failure` returns early for the whole time the breaker is open (`resilience.py:83`).
There is no half-open probe. So once `circuit_breaker_reset_seconds` (60) elapses against a
provider that is still down, the breaker needs `circuit_breaker_failure_threshold` (5) fresh
failures to reopen — and each of those five requests spends a full `tenacity` chain first:
three attempts at a 30s `asyncio.wait_for` plus backoff, about 91.5s (`AGENTS.md:80-85`).
With `resilience.pool_size: 5` the five run concurrently, so the breaker reopens roughly 91.5s
after each reset. The duty cycle over a multi-hour OpenAI outage is therefore about 60s open
and 91.5s closed: **the majority of an outage is spent in the state the breaker exists to
prevent**, and the five requests per cycle that repopulate the tally are exactly the case
`AGENTS.md:84-85` names — "without the breaker a client is told to retry in 2 seconds while the
provider is down". Those five clients also each waited ~91.5s for a 503 that a half-open probe
would have delivered in one attempt.

Note the asymmetry that makes this provable rather than a matter of taste: `record_success` is
already generation-stamped (`resilience.py:70-79`) precisely so a straggler cannot zero a fresh
tally, and the elapsed arm then zeroes that same tally unconditionally two lines earlier.

**Fix:** Prime the tally instead of clearing it, so the first failure after the window reopens
the breaker. `record_success` already clears it for a current-generation success, so a genuinely
recovered provider still resets on its first good answer, and a stale straggler still cannot.

```python
    async def before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._reset_seconds:
                self._opened_at = None
                # Half-open: one failure after the window reopens the breaker, rather than a
                # fresh tally of `_failure_threshold`. `record_success` clears it on the first
                # current-generation success, so a recovered provider still resets.
                self._failure_count = self._failure_threshold - 1
                return
            retry_after = max(1, int(self._reset_seconds - elapsed))
            raise CircuitOpenError(retry_after)
```

### WR-02: An empty configured Play package name makes the package-name pin vacuous

**File:** `src/nativespeaker/api/app/dependencies.py:217-219`

**Issue:** The pin is an equality comparison against the configured value:

```python
if notification.packageName != request.app.state.config.google_play.package_name:
    raise NotificationRejected(stage="package_name_mismatch")
```

`GooglePlayConfig.package_name` is `str | None` with no emptiness handling
(`config.py:121`), so `GOOGLE_PLAY_PACKAGE_NAME=""` — trivially produced by
`kubectl create secret --from-literal=GOOGLE_PLAY_PACKAGE_NAME=` or by a Helm
`--set env[n].value=""` — parses to `""`. `DeveloperNotification.packageName` is declared
`str` with no `min_length` (`auth/google_play.py:112`), so an RTDN carrying
`"packageName": ""` compares equal and the check passes. The deployment is then reading Play
for an application it does not serve: `PlayDeveloperSubscriptions.read` guards
`purchase_token` with `_names_one_path_segment` (`auth/google_play.py:254`) but applies no
guard at all to `package_name`, so `""` reaches the URL as an empty path segment.

Every sibling optional setting is guarded by truthiness and therefore does read `""` as
absent — `build_app_store_verifier`'s `not (store.bundle_id and ...)` (`lifespan.py:60`),
`build_google_push_verifier`'s `not (play.push_audience and ...)` (`lifespan.py:81`), and the
DeviceCheck arm's `not (config.devicecheck.key_id and ...)` (`lifespan.py:159`). This one line
is the only place in the boot path where an empty configured value is treated as configured.
The lifespan even logs `google_play_configuration_absent` for it (`lifespan.py:184` tests
`not config.google_play.package_name`) while the route keeps enforcing nothing.

**Fix:** Refuse when the deployment names no package, rather than comparing against nothing:

```python
    expected_package = request.app.state.config.google_play.package_name
    if not expected_package or notification.packageName != expected_package:
        # Refused before the Play call: this delivery names an application this deployment does not serve.
        raise NotificationRejected(stage="package_name_mismatch")
```

### WR-03: `.env.example` ships `GOOGLE_APPLICATION_CREDENTIALS` uncommented, which breaks the `gcloud` ADC route the same block recommends

**File:** `.env.example:70-79`

**Issue:** Lines 70-74 offer two routes to Application Default Credentials: an ADC file, "**or**
use a `gcloud auth application-default login` session". Line 79 then ships the variable
**uncommented** with a placeholder path:

```
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/outside/this/repo/application_default_credentials.json
```

`google.auth.default()` prefers an explicitly set `GOOGLE_APPLICATION_CREDENTIALS` over the
well-known `gcloud` session file, so a developer who took the second route and copied
`.env.example` to `.env` gets (verified by running it):

```
google.auth.exceptions.DefaultCredentialsError:
File /absolute/path/outside/this/repo/application_default_credentials.json was not found.
```

`_application_default_credential` catches `GoogleAuthError` and returns `None`
(`auth/firebase.py:59-67`), `build_admin_apps` returns `{}`, and **every account-creation route
answers 503 `verification_temporarily_unavailable` for the life of the process** behind a
`firebase_admin_credential_absent` warning that is indistinguishable from a genuinely
unconfigured environment. A working `gcloud` session sits one line away, unused.

This is the exact failure the two store blocks in the same file already defend against, in
their own words: "They ship commented out, with values that parse if you uncomment them,
because a copied line is read at boot by the whole service" (`.env.example:122-123` and
`:164-165`). The rule is stated twice and then not applied to the one variable where the
consequence is worst — the store blocks' placeholders only keep an already-503 route at 503,
whereas this one turns a working credential into a broken one.

**Fix:** Ship it commented out, like the two store blocks, and say why:

```
# So uncomment and fill this, or leave it out entirely. It ships commented out, with a value
# that parses if you uncomment it: an explicit path outranks a `gcloud auth
# application-default login` session, so a copied placeholder replaces a working credential
# with a 503 on every account-creation route.
#GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/outside/this/repo/application_default_credentials.json
```

### WR-04: The container process owns its own code and virtualenv, and the `chown` duplicates the venv into a second image layer

**File:** `Dockerfile:31-35`

**Issue:**

```dockerfile
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser
```

Nothing under `/app` is written at runtime: `uv sync` produced the venv in the builder stage,
`config/` is read by `EnvironmentConfig` and never written, and `useradd -m` already gives the
process a writable `/home/appuser` for any library cache. The recursive `chown` therefore buys
nothing and costs two things. First, it makes the running process the owner of its own
interpreter, site-packages and `config/`, so anything that achieves code execution in the
container can rewrite the application's own code — the k8s chart's `readOnlyRootFilesystem: true`
(`k8s/templates/deployment.yaml:38`) masks this in the cluster, but the image is also the artifact
a plain `docker run` or a compose service uses, where no such mask exists. Second, changing
ownership of every file forces an overlayfs copy-up of the whole tree, so the virtualenv is
stored twice in the image.

`uv sync` writes world-readable files, so the process does not need to own them to import them.

**Fix:** Drop the `chown`; keep the user.

```dockerfile
# Create non-root user for security. uid 1000 matches the chart's `runAsUser`.
# No `chown`: nothing under /app is written at runtime, and the venv is world-readable,
# so the process reads its own code without owning it.
RUN useradd -m -u 1000 appuser

USER appuser
```

### WR-20: `ty` reports three errors, and all three are in these files — the rest of the repo is clean

**File:** `src/nativespeaker/api/auth/app_store.py:145`, `src/nativespeaker/api/auth/devicecheck.py:153`

**Issue:** `.venv/bin/ty check src` over the whole repository finds exactly three
diagnostics, and every one is in an assigned file. The repo pins `ty` as a
dependency and a prior pass already filed this exact class (`41-REVIEW.md`
WR-07), so the baseline this regresses against is zero.

```
error[invalid-argument-type]  src/nativespeaker/api/auth/app_store.py:145:38
    status = _APPLE_STATUSES.get(data.status)
    Expected `Status`, found `Unknown | Status | None`
    info: Element `None` of this union is not assignable to `Status`

error[invalid-argument-type]  src/nativespeaker/api/auth/devicecheck.py:153:30  ("bit0")
error[invalid-argument-type]  src/nativespeaker/api/auth/devicecheck.py:153:51  ("bit1")
    bit0, bit1 = payload.get("bit0"), payload.get("bit1")
    Expected `Never`, found `Literal["bit0"]`
```

The `app_store` one is not pure noise: it is the checker pointing at the fact
that line 145 deliberately depends on `dict.get(None)` returning `None`, which
the declared key type forbids. The `devicecheck` pair is the consequence of
narrowing `_decoded`'s `object | None` with a bare `isinstance(payload, dict)`,
which leaves the key type as `Never`.

**Fix:** Both are behaviour-preserving. I applied both to a scratch copy and
confirmed `ty check src` then reports **All checks passed!**

```python
# app_store.py:145 -- same outcome, and the None case is now stated rather than implied
status = None if data.status is None else _APPLE_STATUSES.get(data.status)
```

```python
# devicecheck.py:115-120 -- move the object-shape test into the decoder
def _decoded(response: httpx.Response) -> dict[str, object] | None:
    """The response body as a JSON object, or `None` when it is neither."""
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


# devicecheck.py:150-152
payload = _decoded(response)
if payload is None:
    raise RetryableDeviceCheckError("unrecognised body")
```

### WR-21: two concurrent claims on one device silently reopen each other's DeviceCheck slot

**File:** `src/nativespeaker/api/auth/devicecheck.py:176-180`, `src/nativespeaker/api/auth/devicecheck.py:222-225`

**Issue:** `write_bits` sends **both** bits in one Apple call, and
`write_bits_with_retry` takes both from the caller. Both claim routes read the
pair first and then write the pair back with one member replaced:

- `services/auth.py:206` reads, `services/auth.py:231` writes
  `bit0=True, bit1=state.bit1`
- `services/auth.py:277` reads, `services/auth.py:297` writes
  `bit0=state.bit0, bit1=True`

`state` is captured **before** the grant transaction opens (this is required —
SHARED-INVARIANTS forbids a provider call while a lock is held), so the window
between the read and the write spans a whole database transaction and commit.
Nothing serialises two claims against the same physical device: the anonymous
claim needs `identity.provider is anonymous` (`services/auth.py:177`) and the
registered claim needs google/apple (`services/auth.py:240`), so the two run
against **different `core.users` rows** and the per-user grant locks never
intersect. `DEVICECHECK_HTTP_TIMEOUT_SECONDS` is 8 with up to three attempts, so
the window is seconds wide, not microseconds.

Interleave them and the later write carries the earlier writer's stale member:
final state `(bit0=True, bit1=False)` after a registered claim had already set
bit1, or `(bit0=False, bit1=True)` after an anonymous claim had already set bit0.
Either way one device slot is reopened and a second free grant becomes claimable
on that device from a fresh account. The carry-forward at `state.bit1` /
`state.bit0` prevents *fabricating* the other bit, which is what
`41-SECURITY.md` T-41-06 records as mitigating "destroying Phase 42's bit1
state" — it does not prevent *losing* a value another request wrote in the
meantime, so T-41-06 is marked `closed` on evidence that does not cover this
case.

Filed as Warning, not Critical, on the merits: the loss is one free-tier grant
on a sub-$5 product, and the mitigations that would actually close it are
explicitly forbidden — SHARED-INVARIANTS bans device-check components in any
rate-limit key ("No device-fingerprint or device-check component in any
rate-limit key, in any form") and bans "distributed lock, lease, or
multi-phase-commit machinery". Apple's `update_two_bits` offers no
compare-and-swap, so there is no in-bounds code fix.

**Fix:** Record the residual instead of claiming it closed. Two concrete edits:

1. In `devicecheck.py`, state the contract the helper actually has, so the next
   caller does not assume it is safe:

```python
async def write_bits_with_retry(adapter: DeviceCheckAdapter, device_token: str, *,
                                bit0: bool, bit1: bool) -> None:
    """Call the adapter's update up to `DEVICECHECK_ATTEMPTS` times; return on confirmation or raise.

    Apple writes both bits in one call and offers no compare-and-swap, so this is a blind
    overwrite, not a merge: the bit the caller carries forward is the value it read BEFORE its
    own transaction. Two claims racing on one device therefore lose one write. Do not read this
    helper as making the pair atomic.
    """
```

2. Reopen `41-SECURITY.md` T-41-06 as `residual` with the concurrent case named,
   rather than `closed` — the carry-forward evidence
   (`TestTheBit1CarryForward`) exercises the fabrication case only.

### WR-22: five cross-file line citations point at the wrong lines

**File:** `src/nativespeaker/api/schemas/api.py:10`, `src/nativespeaker/api/schemas/auth.py:41`, `src/nativespeaker/api/auth/firebase.py:163`, `src/nativespeaker/api/auth/store_notifications.py:31`, `src/nativespeaker/api/auth/app_store.py:141`

**Issue:** This codebase deliberately puts its design record in comments, and
those comments cite specific lines as the evidence for a rule. Five of them in
these files now point somewhere else. I read every cited line:

| Comment | Cites | What is actually there | What it means |
|---|---|---|---|
| `schemas/api.py:10` | `services/chats.py:96` | `human_message = Message(...)` | the charge is `chats.py:101` (and `:130`) |
| `schemas/auth.py:41` | `devicecheck.py:93` | `return text` in `read_private_key` | the relay into Apple's body is `_shared_body`, `devicecheck.py:110` |
| `firebase.py:163` | `crud/identities.py:155` | `if user.registered_at is None:` | the refuse-to-overwrite-email guard is `crud/identities.py:161-163` |
| `store_notifications.py:31` | `crud/subscriptions.py:300` | `old_tier_id=old_tier_id,` (an argument) | the identity comparison is `crud/subscriptions.py:345-346` |
| `app_store.py:141` | "exactly as line 98 above" | `self._products = products` | the arm meant is `app_store.py:124-127` |

`firebase.py:163` is the worst of the five: it points a reader at the
`registered_at` guard as the evidence for a rule about `email`, which is a
different guard six lines away with different semantics.

**Fix:** Cite the symbol, not the line — the numbers go stale on the next commit
that touches the target file, and the symbol does not. For example:

```python
# firebase.py:161-166
# Firebase leaves the record-level `email` populated after a client unlinks its last
# provider, and copied onto the account `crud/identities.py::IdentitiesDB.upgrade_identity`
# then refuses to overwrite it (its `if user.email is None:` guard) -- so a genuine upgrade
# kept the stale address forever, on a route tree `04-users-me.md` gives no repair path.
```

```python
# schemas/auth.py:41 -- `devicecheck.py::_shared_body`, not a line number
# body this service posts to Apple (`devicecheck.py::_shared_body`), at this service's expense
```

Same treatment for the other three, and change `app_store.py:141`'s "exactly as
line 98 above" to "exactly as the data-less arm above".

### WR-23: four different operator faults on the restore read collapse into one indistinguishable log line

**File:** `src/nativespeaker/api/auth/google_play.py:304-338`

**Issue:** `read_for_restore` raises `Unavailable(stage=RESTORE_READ_STAGE)` from
four structurally different conditions:

- `:311` — no Play credential at all (ADC absent in this environment)
- `:314` — `package_name` absent or dot-only (a broken deployment config)
- `:324` — transport failure or a refused credential refresh
- `:331` — Play answered a non-2xx that is not 404/410

`Unavailable` inherits `log_level = logging.WARNING` and its `log_fields()`
returns `{"stage": self.stage}` (`errors.py:426-431`), so all four produce the
byte-identical line `stage=play_restore_read`. An operator watching every restore
answer 503 cannot tell "the pod has no credential" from "Play is returning 403
because the service account lost the androidpublisher scope" from "package_name
is unset" — three faults with three different repairs.

The webhook arm of the same class does this correctly:
`_play_answer_is_usable` (`:188-199`) logs `google_play_read_refused` with
`status_code` before raising. `read_for_restore` is the paying-customer path and
has less diagnostic output than the machine-to-machine one.

`stage` reaches `log_fields()` only; `ErrorResponse` carries exactly one field
(`code`, `errors.py:34-37`), so distinguishing the stages discloses nothing to a
client and does not breach the anti-oracle rule. The module comment at
`google_play.py:46` calls `RESTORE_READ_STAGE` "its whole log vocabulary" —
that is the choice this finding disputes.

**Fix:** Keep one class and one client-visible answer; widen the internal label.

```python
# google_play.py:46-48
RESTORE_READ_STAGE = "play_restore_read"
RESTORE_TOKEN_GONE_STAGE = "play_token_gone"
RESTORE_UNCONFIGURED_STAGE = "play_restore_unconfigured"
RESTORE_TRANSPORT_STAGE = "play_restore_transport"
```

```python
        if self._credential is None:
            raise Unavailable(stage=RESTORE_UNCONFIGURED_STAGE)
        if not package_name or not _names_one_path_segment(package_name):
            raise Unavailable(stage=RESTORE_UNCONFIGURED_STAGE)
        ...
        except (httpx.HTTPError, google.auth.exceptions.GoogleAuthError) as failure:
            raise Unavailable(stage=RESTORE_TRANSPORT_STAGE) from failure
        ...
        if response.status_code // 100 != 2:
            # The status alone, as the webhook arm already logs: no Play value travels with it.
            logger.error("google_play_restore_read_refused", status_code=response.status_code)
            raise Unavailable(stage=RESTORE_READ_STAGE)
```

### WR-24: `claims_from_payload` raises `KeyError` on a missing `iss`, inside a verifier whose contract is "never raises"

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:108-113`

**Issue:**

```python
def claims_from_payload(payload: dict) -> VerificationResult:
    """Turn an already-verified payload into claims, enforcing the non-empty-`sub` rule."""
    subject = payload.get("sub")
    if not subject:
        return None, BoundedReason.empty_subject
    return VerifiedClaims(issuer=str(payload["iss"]), subject=str(subject)), None
```

`sub` is fetched defensively and answered with a bounded reason; `iss` is
subscripted directly. Today both are in `DECODE_OPTIONS["require"]` (`:53`) and
the only callers are `verify()`'s two sites (`:235`, `:246`), so the `KeyError`
is unreachable — but this is a module-public function in a module that documents
itself as the shared source for exactly this kind of reuse ("module-level so a
test double substituting only the key lookup imports them rather than restating
them", `:48-49`). `TokenVerifier.verify`'s Protocol docstring (`:85`) promises
"Never raises", and `JWTVerifier.verify` goes to the length of a bare
`except Exception` at `:226` to make that structural — a `KeyError` escaping
`claims_from_payload` would land outside every one of those guards, because it is
raised after the `try` block closes at `:232`. The result would be a 500 for a
caller owed a 401, which is precisely the outcome the `:227` comment says cannot
happen.

`BoundedReason.issuer_mismatch` already exists for this and is already the label
`_MISSING_CLAIM_REASONS` gives an absent `iss` (`:59`), so the answer is
determined; only the code path is missing.

**Fix:**

```python
def claims_from_payload(payload: dict) -> VerificationResult:
    """Turn an already-verified payload into claims, enforcing the non-empty-`sub` rule."""
    subject = payload.get("sub")
    if not subject:
        return None, BoundedReason.empty_subject
    issuer = payload.get("iss")
    if not issuer:
        # The same label `_MISSING_CLAIM_REASONS` gives an absent `iss`, so the two agree.
        return None, BoundedReason.issuer_mismatch
    return VerifiedClaims(issuer=str(issuer), subject=str(subject)), None
```

### WR-40: Both grant writers take a detached ORM row whose attributes are a barrier-time snapshot

**File:** `src/nativespeaker/api/crud/grants.py:147`, `:166-175`, `:221`, `:234-237`

**Issue:** `activate_anonymous_device_grant` and `activate_registered_account_grant`
each take `identity_row: ExternalIdentity` and immediately throw it away — they read
only `.issuer` and `.subject` off it and then re-resolve the row into their own
session as `stored`, which is what every eligibility test and every mutation uses.

That re-resolution is load-bearing, because `identity_row` is **detached**: the
barrier resolves it inside its own short session (`app/dependencies.py:90-93`)
which closes before the handler runs, so its attributes are frozen at barrier time
and are never refreshed. I verified the detachment matters — a probe against the
dev database showed that an ORM row whose session has ended raises
`MissingGreenlet` on attribute access rather than silently refreshing, which is
exactly why nothing in this app re-reads through that object.

Nothing in the signature or the type says any of this. A whole entity is offered
where two strings are used, next to a same-named local (`stored`) holding the fresh
copy, and the caller one frame up already reads the stale copy for its preflight
(`services/auth.py:189`, `identity.identity.free_grant_consumed_at`). A future line
that writes `identity_row.free_grant_consumed_at` or
`identity_row.native_claim_platform` instead of `stored....` compiles, type-checks,
passes the unit suites (which pass a hand-built row), and silently defeats the
platform pin at `:170-175` and the lifetime-slot refusal at `:182` — the two
refusals the whole endpoint exists to enforce.

**Fix:** narrow the parameter to what is actually consumed, so the stale object
cannot reach the writer at all.

```python
async def activate_anonymous_device_grant(self, *,
                                          user_id: UUID,
                                          # The verified pair only: the row this re-resolves is the
                                          # one every test and every mutation below reads. The
                                          # barrier's own row is detached and frozen at admission.
                                          issuer: str,
                                          subject: str,
                                          claim_platform: NativeClaimProvider,
                                          tier_id: str,
                                          evaluated_at: datetime) -> ActivationOutcome:
    ...
    stored = await IdentitiesDB(self.session).resolve_existing(issuer=issuer, subject=subject)
```

and the same for `activate_registered_account_grant`; callers pass
`issuer=identity.issuer, subject=identity.subject` (`services/auth.py:210`, `:281`),
which are plain strings on `LinkedIdentity` and not ORM attributes.

---

### WR-41: The conversion's usage carry-over is correct only because of a seed relationship nothing asserts

**File:** `src/nativespeaker/api/crud/grants.py:299-306`

**Issue:** The conversion inserts the registered grant's usage row carrying the
superseded anonymous grant's `monthly_used` verbatim:

```python
# The carried period and count are safe because the registered tier's allowance is the larger one.
self.session.add(UserMonthlyUsage(
    grant_id=activated.id,
    monthly_period=(monthly_period_for(evaluated_at) if carried is None else carried.monthly_period),
    monthly_used=0 if carried is None else carried.monthly_used,
    ...))
```

The claimed safety is real today — `migrations/20260818_01_initial-release.sql:124-125`
seeds `anonymous` at 10 and `registered` at 50 — but it is asserted by **nothing**
executable. `grep -rn monthly_credits tests/` finds no case comparing the two
tiers; `tests/schema/test_constraints.py:441-448` only checks that a tier's credits
are non-negative. The relationship is stated twice in prose (the SQL comment at
`:122` and the code comment at `:299`) and enforced nowhere.

If a later seed edit lowers `registered` below `anonymous`, a converting user's
carried count exceeds the new allowance and `services/quota.py:97`
(`remaining = max(allowance - usage.monthly_used, 0)`) returns 0 for the rest of
the month. The user is charged for an upgrade that took credits away, with no
error, no log line, and no failing test. This is the same class of coupling the
codebase already binds elsewhere: `FREE_GRANT_SOURCES` is tied to the live index
predicate by `tests/schema/test_grant_locks.py::TestTheFreeGrantSourceSetMatchesTheIndex`
precisely so the constant cannot drift from the schema.

**Fix:** bind the constant the way the sibling invariant is bound — a schema case
that reads the applied seed rows rather than restating them.

```python
# tests/schema/test_constraints.py
class TestTheTierSizingInvariant:
    """`crud/grants.py:299` copies `monthly_used` across a conversion unclamped; that is safe
    only while every registered tier's allowance is at least the anonymous tier's."""

    async def test_the_registered_allowance_is_never_below_the_anonymous_one(self, conn):
        seeded = dict(await conn.fetch(
            "SELECT id, monthly_credits FROM core.access_tiers WHERE id IN ('anonymous','registered')"))
        assert seeded["registered"] >= seeded["anonymous"]
```

---

### WR-42: `Chat.user` is an unused lazy relationship that raises `MissingGreenlet` on first touch

**File:** `src/nativespeaker/api/tables/chats.py:54`

**Issue:** `user: User = Relationship()` is declared with default lazy loading and
is read by nothing — `grep -rn` over `src/` and `tests/` finds no access to it, and
`ChatsDB.get_chat` eager-loads only `Chat.messages` (`crud/chats.py:23`).

Because every `Chat` in this app lives in an `AsyncSession`, the first reader gets a
crash, not a row. I proved this against the dev database:

```
chat = (await s.exec(select(Chat).where(col(Chat.id) == cid))).first()
chat.user
-> MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here
```

That is an unhandled exception, so it surfaces as an opaque 500 on whichever chat
route first touches it. The attribute reads as a normal, supported accessor; nothing
marks it as unusable. Every other collection in this package is either eager-loaded
at the query (`selectinload(Chat.messages)`) or ordered explicitly, so this is the
one mapped attribute with no safe read path.

**Fix:** delete it — `Chat.user_id` is what every caller actually uses
(`routers/chats.py:23,36,54,71,85` all pass `identity.user.id`). If a link is wanted
later, declare it so a mistake fails loudly at the mapper rather than at runtime:

```python
    # Deleted: nothing reads it, and a lazy load inside an AsyncSession raises MissingGreenlet.
    # If it returns, it must be eager-only:
    #   user: User = Relationship(sa_relationship_kwargs={"lazy": "raise"})
```

### WR-60: the restore writes the grant at the pre-lock tier, having re-read only the status under the locks

**File:** `src/nativespeaker/api/services/restore.py:57`, `:62`, `:99-103`, `:136-137`, `:169-179`

**Issue:** `stored` is loaded by a plain, unlocked read at `:57`. The grant locks are taken
at `:91`. Under those locks the code deliberately re-reads the **status** at `:99`
(`read_status`, a column select) and refuses on divergence at `:100-103`, with a comment
that states the reason: "the webhooks own canonical state, and one that revoked or expired
this subscription inside the window leaves this path writing an entitled grant against a
row that no longer entitles anything".

The **tier** is not re-read. `tier_id = stored.tier_id` at `:137` is still the `:57`
snapshot, and it is what `write_subscription_grant(..., tier_id=tier_id, ...)` at `:173`
writes into the new `core.access_grants` row. `read_status` is a column select, so it does
not refresh `stored`; nothing between `:57` and `:137` does.

A tier-change webhook that commits inside that window is therefore silently reverted: the
restore supersedes the buyer's grants and inserts a new one at the *old* tier, which is
what `GrantsDB.monthly_credits(grant.tier_id)` then hands `QuotaService.charge` and
`SyncService.read_entitlement`. The account is billed against the wrong allowance until the
next delivery for that subscription arrives — `write_subscription_grant`'s replay check
(`crud/subscriptions.py:333-335`) compares `grant.tier_id == tier_id`, so the next webhook
does supersede and re-insert correctly. Self-healing, and it needs a concurrent delivery,
which is why this is a warning and not a blocker — but it is exactly the defect
`7c83212 fix(37.4): WR-61 re-read the subscription's status under the grant locks before
writing` fixed for the sibling column, left unfixed for this one.

**Fix:** capture the tier beside the status at `:62`, then re-read the whole row under the
locks instead of the status column, and refuse on either divergence:

```python
        status = proof.status if stored is None else stored.status
        tier_read = None if stored is None else stored.tier_id
...
        # Re-read under the grant locks: the webhooks own the status and the tier alike.
        settled = await self.subscriptions_db.read_subscription(proof.provider, proof.external_id)
        if settled is not None and (settled.status != status or settled.tier_id != tier_read):
            raise RestoreSubscriptionNotEntitled
```

`read_subscription` carries `populate_existing=True` (`crud/subscriptions.py:109`), so it
refreshes `stored` in place and `:137`'s `tier_id = stored.tier_id` then reads the settled
value. `read_status` loses its only caller and can go with it.

---

### WR-61: the appended subscription event names a tier the row no longer carried when it was written

**File:** `src/nativespeaker/api/services/subscriptions.py:53`, `:86-87`, `:163`

**Issue:** `old_tier_id` is copied out of the pre-lock `stored` read at `:53`. The grant
locks are taken at `:60`, and the row is deliberately re-read under them at `:86-87` as
`settled` — the comment at `:79-85` gives the reason and names the exact failure it fixed
("gating on the pre-lock `stored` skipped the guard entirely when the rival's insert is
what that read missed").

`read_subscription` uses `populate_existing=True`, so `:86` refreshes the same instance —
but `old_tier_id` was already copied to a local at `:53` and is not refreshed with it. The
`audit.subscription_events` row appended at `:158-164` therefore records a transition from
a tier the subscription no longer had when the write happened, and records `NULL` whenever
a rival's insert is what the pre-lock read missed. That is the audit trail operators read
to reconstruct a disputed subscription, so a wrong value in it is worse than no value.

**Fix:** derive it from the row read under the locks. Delete `:53` and add, after `:87`:

```python
        # The tier as of the locks, never the pre-lock snapshot: the write below is made against this row.
        old_tier_id = None if settled is None else settled.tier_id
```

`old_tier_id` has no reader between `:53` and `:163`, so the move is safe.

---

### WR-62: nine distinct refusals collapse into one log line that names none of them

**File:** `src/nativespeaker/api/services/auth.py:304-316`; `src/nativespeaker/api/services/restore.py:64`, `:103`, `:117`, `:207`

**Issue:** `AuthService._settle` turns every non-`activated`, non-re-readable outcome into a
bare `raise ClaimRefusedUnderLock` at `:316`. `ActivationOutcome.refused` is returned from
four sites in `activate_anonymous_device_grant` (`crud/grants.py:169`, `:175`, `:184`,
`:187` — a non-anonymous stored row, a platform-pin mismatch, a grant this window could not
see, a spent lifetime slot) and four in `activate_registered_account_grant` (`:238`,
`:250`, `:254`, `:266`), plus `lost_race` with nothing to re-read. `ClaimRefused` inherits
`AppError.log_fields()`, which returns `{}`, so all nine leave the single line
`claim_refused_under_lock` with no field at all. An operator cannot tell "this device is
pinned to the other platform" from "this attempt lost a race", and the class name actively
misreports the permanent refusals as races.

`RestoreService` has the same shape: `RestoreSubscriptionNotEntitled` is raised from four
places (`:64` the pre-lock status, `:103` the status that moved under the locks, `:117` the
closed term, `:207` the state a winning attempt left) and `RestoreRefused` likewise carries
no `log_fields`.

This is not a client-visible problem — SHARED-INVARIANTS § Errors requires the branches
within a class to stay indistinguishable to the client, and they do. It is an operability
problem: the invariant also requires that "a rejection leaves exactly one structured
security-log line carrying its **stable internal result**", and the internal result these
lines carry is the same string for nine different conditions.

**Fix:** use the pattern this codebase already has for exactly this — `ProviderLookupError`
(`errors.py:418-432`) takes `stage`/`cause` and surfaces them through `log_fields()` while
leaving `status` and `code` untouched. Give `ClaimRefused` and `RestoreRefused` the same
optional `cause`:

```python
class ClaimRefused(AppError):
    """The claim's refusals share this shape, and its leaves add only their own name."""
    status = 403
    code = "operation_not_allowed"

    def __init__(self, *args, cause: str | None = None, **kwargs) -> None:
        self.cause = cause
        super().__init__(*args, **kwargs)

    def log_fields(self) -> dict[str, str | None]:
        return {} if self.cause is None else {"cause": self.cause}
```

then make the writers say which arm fired — split `ActivationOutcome.refused` into named
members, or return `(outcome, cause)` — and pass it through:
`raise ClaimRefusedUnderLock(cause=outcome_cause)` at `auth.py:316`, and
`raise RestoreSubscriptionNotEntitled(cause="status_moved_under_the_locks")` at
`restore.py:103` and its three siblings. Do **not** add a second `logger` call: Phase 40
WR-51 already removed a double log line for a refusal, and the invariant allows exactly
one.

---

### WR-63: multi-line narrating comment blocks, which this repository's AGENTS.md forbids

**File:** `src/nativespeaker/api/services/subscriptions.py:79-85`, `:125-130`, `:62-65`, `:117-119`, `:182-184`; `src/nativespeaker/api/services/restore.py:66-70`, `:93-98`, `:114-116`, `:120-125`, `:186-188`; `src/nativespeaker/api/services/chats.py:133-137`; `src/nativespeaker/api/services/auth.py:53-55`, `:200-202`, `:219-221`, `:226-229`, `:234-237`, `:293-295`, `:376-379`; `src/nativespeaker/api/services/quota.py:23-26`, `:50-53`, `:70-72`; `src/nativespeaker/api/services/sync.py:55-58`

**Issue:** `ns-api-gateway/AGENTS.md` § "Comments and docstrings" binds all code in this
repository: "**One line each.** A comment explains the specific line or lines below it. It
never explains the design, the request lifecycle, a rule enforced in another module, or a
decision that was made elsewhere." Twenty-two standalone comment runs of three to seven
lines survive in these files, and the longest ones violate the second sentence as well:

- `subscriptions.py:79-85` — seven lines reconstructing a past two-delivery race and what
  the previous version of the guard did wrong.
- `restore.py:93-98` — six lines whose subject is `SubscriptionsService.ingest`, a rule
  enforced in another module, plus the 500 an earlier version produced.
- `restore.py:120-125` — six lines on the lock ordering and a deadlock in another module's
  buy-then-restore race.
- `subscriptions.py:125-130` — six lines on the one-active-slot design.
- `chats.py:133-137` — five lines narrating a foreign-key failure the previous version hit.
- `restore.py:66-70` — five lines quoting `10-restore-subscription.md:84(3)`.

Docstrings are clean — I checked every module, class and function in scope with `ast` and
none exceeds the three-line bar. Only the comment rule is being broken, and it is broken in
the same way Phase 38 WR-32 ("cut the narrating comment blocks AGENTS.md outlawed") already
fixed elsewhere.

**Fix:** for each block, keep the one line that resolves the ambiguity at the line below it
and delete the rest; the design rationale belongs in the phase context files, which already
hold it. For example, `restore.py:93-98` reduces to:

```python
        # Re-read under the grant locks: the webhooks own the status, and a plain read predates them.
        settled_status = await self.subscriptions_db.read_status(proof.provider, proof.external_id)
```

Do this per block rather than in one sweep, so a comment that is genuinely load-bearing
(`auth.py:219-221`, which explains why the commit precedes the irreversible Apple write) is
compressed rather than lost.

### WR-80: `spy_on` freezes a structlog level onto the module logger for the rest of the session

**File:** `tests/e2e/conftest.py:65-73`
**Issue:** `monkeypatch.setattr(f"{target}.{level}", spy.record)` patches an attribute of a
`structlog._config.BoundLoggerLazyProxy`. The proxy has no `warning`/`error`/`info` in its
`__dict__`; it builds one on demand in `__getattr__`. `monkeypatch` reads the old value with
`getattr`, so on undo it re-`setattr`s a *bound method of a throwaway `BoundLogger`* onto the
proxy instead of deleting the attribute. From then on the module-level logger is
permanently pinned to whatever structlog configuration was in force at patch time, and a
later `setup_logging()` (which the module-scoped `_app_lifespan` of the next e2e module
runs) no longer reaches it.

Proven:

```
$ .venv/bin/python -c "..."   # setattr via MonkeyPatch, then undo
before: False
during: True
after undo: True                       # <- the attribute survives the undo
frozen attr: <bound method ... of <BoundLoggerFilteringAtNotset(...)>>
emitted through frozen binding: []     # a later structlog.configure() is ignored
```

**Fix:** patch the module's `logger` name — which does live in the module `__dict__`, so
monkeypatch restores it exactly — rather than the proxy's per-level attributes:

```python
class _SpyLogger:
    """Stands in for a module's `logger`; only the levels a route spies on are recorded."""

    def __init__(self, spy: LogSpy, levels: tuple[str, ...]) -> None:
        for level in levels:
            setattr(self, level, spy.record)


def spy_on(monkeypatch, targets: tuple[str, ...], levels: tuple[str, ...]) -> LogSpy:
    """A spy, not `capture_logs`: the module-level logger caches its binding, so capture sees
    nothing. The whole `logger` name is replaced, never its level attributes: structlog's lazy
    proxy makes those on demand, so monkeypatch's undo would freeze one onto the proxy for the
    rest of the session."""
    spy = LogSpy()
    for target in targets:
        monkeypatch.setattr(target, _SpyLogger(spy, levels))
    return spy
```

`spy_on` is already called with the module path plus `.logger` (`_LOGGERS` in
`test_app_store_webhook.py:89-90`, `test_google_play_webhook.py:232-235`,
`test_sign_out_all.py:28-29`, `test_restore_subscription.py:84`), so no call site changes.

### WR-81: Both Firebase credential fixtures can leak a permanent user in the shared project

**File:** `tests/e2e/conftest.py:145-149`, `tests/e2e/conftest.py:190-197`
**Issue:** both fixtures state the invariant and then break it.
`anonymous_firebase_credential` says at :137-138 *"Between the user starting to exist and
the try that deletes it nothing may raise, or the minted user is permanent in this shared
project"* — but `data = resp.json()` (:146) and `local_id = data["localId"]` (:148) sit
outside the `try` at :149, and both run after `accounts:signUp` has already created the
user. `google_linked_firebase_credential` says at :194-196 *"The try opens where the user
starts existing"* — but `anonymous = signup.json()` (:191) and
`local_id = anonymous["localId"]` (:192) sit outside the `try` at :197.

A non-JSON body or a response missing `localId` therefore abandons a real Firebase user in
a shared project, permanently, and one accumulates per run — the exact failure the
comments were written to prevent.

**Fix:** open the `try` at the statement after `httpx.post` returns, and move the parsing
inside. For `anonymous_firebase_credential`:

```python
    resp = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signUp"
        f"?key={_identity_toolkit_key(_app_config)}",
        json={"returnSecureToken": True},
    )
    local_id = None
    try:
        resp.raise_for_status()
        data = resp.json()
        # Subscripting rather than .get(): if returnSecureToken were ever ignored, this fails loudly.
        local_id = data["localId"]
        yield data["idToken"], local_id
    finally:
        # The parse is inside the try because signUp has already minted the user by the time it runs.
        if local_id is not None:
            auth.delete_user(local_id, app=admin_app)
```

Apply the same shape to `google_linked_firebase_credential` (move :191-192 inside the
existing `try`, and guard the `delete_user` on `local_id is not None`).

### WR-82: The restore term boundary case never reaches the boundary it is named for

**File:** `tests/e2e/test_restore_subscription.py:417-435`
**Issue:** `test_a_term_ending_at_the_captured_instant_is_not_open` scripts
`expires_at=datetime.now(UTC) - timedelta(milliseconds=1)` (:429). The request's own
`evaluated_at` is captured *after* that, so the proof's term is strictly in the past and
the case never exercises `term_ends_at == evaluated_at`. The predicate under test is
`if term_ends_at is None or term_ends_at <= self.evaluated_at:`
(`src/nativespeaker/api/services/restore.py:113`), and flipping `<=` to `<` — the exact
mutation the case name forbids — leaves the whole file green:

```
$ sed -i '113s/<= self.evaluated_at/< self.evaluated_at/' src/nativespeaker/api/services/restore.py
$ .venv/bin/pytest tests/e2e/test_restore_subscription.py -q -m e2e
35 passed
```

The module already owns the tool to fix this: `pinned_evaluation_instant` (:110-120)
overrides `get_evaluated_at`, so the equality case is one fixture away.

**Fix:**

```python
    async def test_a_term_ending_at_the_captured_instant_is_not_open(
            self, restore_client, _db_transaction, scripted_app_store_notifications,
            pinned_evaluation_instant):
        """The closed side of the boundary, at the instant itself: the predicate is `<=`, so a
        term ending exactly when the request was evaluated is over. Only a pinned instant can
        name that equality -- a live clock never lands on it."""
        user, _ = await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=SUBJECT,
                                      provider=IdentityProvider.google)
        external_id = f"e2e-boundary-{uuid4()}"
        await seed_subscription(_db_transaction, external_id=external_id, user_id=user.id,
                                tier_id=PAID_TIER_ID)
        before = await _four_counts(_db_transaction, user.id, external_id)
        scripted_app_store_notifications.script_restore(
            _proof(external_id, expires_at=pinned_evaluation_instant))

        refused = await _restore(restore_client)

        assert refused.status_code == 404
        assert refused.content == RESTORE_NOT_FOUND_BODY
        assert await _four_counts(_db_transaction, user.id, external_id) == before
```

Re-run the `<=` → `<` mutation afterwards; it must go red.

### WR-83: The anonymous claim's three Apple-failure arms never assert the lifetime marker stayed NULL

**File:** `tests/e2e/test_claim_anonymous_grant.py:362-415`
**Issue:** `free_grant_consumed_at` is one-way: once set, `_claim_anonymous_grant` refuses
every future claim (`src/nativespeaker/api/services/auth.py:188-191`), so a writer that
set it on a refusal permanently denies the account the only free grant it will ever get.
The registered twin asserts the marker stays NULL on all three of its Apple-failure arms
(`tests/e2e/test_claim_registered_grant.py:535`, `:555`, `:575`). The anonymous file
asserts only `_row_counts(...) == (0, 0)` (:378, :396, :414) — and the marker lives on
`core.external_identities`, which `_row_counts` does not read.

Proven: burning the marker on the spent-device arm leaves all three anonymous
Apple-failure cases green.

```python
        if state.bit0:
            identity.identity.free_grant_consumed_at = self.evaluated_at   # MUTANT
            self.session.add(identity.identity)
            await self.session.commit()
            raise DeviceGrantExhausted(stage="devicecheck_read", cause="already_set")
```
```
$ .venv/bin/pytest tests/unit tests/schema tests/e2e -q -m ""
4 failed, 2343 passed     # all four are unit commit-counting cases; every e2e claim case passed
```

The mutant is caught today only by `tests/unit/test_claim_precedence.py` counting commits.
A regression that set the marker inside an existing commit would ship.

**Fix:** the file already has `_identity_of`. Add one line to each of the three cases, as
the registered twin does:

```python
        assert await _row_counts(_db_transaction, user.id) == (0, 0)
        # The one-way marker: a refusal that sets it denies this account its only free grant forever.
        assert (await _identity_of(_db_transaction, subject)).free_grant_consumed_at is None
        assert (await _challenge_for(_db_transaction, handle)).consumed_at is not None
```

### WR-84: The anonymous D-09 repeat case proves row counts, not "writes nothing"

**File:** `tests/e2e/test_claim_anonymous_grant.py:214-240`
**Issue:** the case is named
`test_a_repeat_answers_the_fresh_claim_body_writes_nothing_and_never_reaches_apple`, but
the only state assertion is `await _row_counts(_db_transaction, user.id) == after_first`
(:239) — a pair of counts. The registered twin reads the rows themselves
(`tests/e2e/test_claim_registered_grant.py:329-333`): grant id and `updated_at`, then the
usage row's `monthly_period`, `monthly_used` and `updated_at`.

Proven: a repeat arm that rewrites the row it found leaves both e2e claim files green.

```python
        if any(grant.source is AccessGrantSource.anonymous_device_grant for grant in held):
            held[0].updated_at = self.evaluated_at        # MUTANT
            self.session.add(held[0])
            await self.session.commit()
            return
```
```
$ .venv/bin/pytest tests/e2e/test_claim_anonymous_grant.py tests/e2e/test_claim_registered_grant.py -q -m e2e
27 passed
```

(The unit suite catches this particular mutant by counting commits; a rewrite folded into
an existing commit would not be caught anywhere.)

**Fix:** mirror the registered twin. The file already imports `select`/`col` and has
`_grants_of`; add a `_usage_of` helper identical to
`tests/e2e/test_claim_registered_grant.py:103-107` and assert:

```python
        granted = (await _grants_of(_db_transaction, user.id))[0]
        usage_before = await _usage_of(_db_transaction, granted.id)
        ...
        unchanged = (await _grants_of(_db_transaction, user.id))[0]
        assert (unchanged.id, unchanged.updated_at) == (granted.id, granted.updated_at)
        usage_after = await _usage_of(_db_transaction, granted.id)
        assert (usage_after.monthly_period, usage_after.monthly_used, usage_after.updated_at) == (
            usage_before.monthly_period, usage_before.monthly_used, usage_before.updated_at)
```

### WR-85: The challenge-expiry boundary is a magic 299 and pins nothing

**File:** `tests/e2e/test_challenge_store.py:170-178`
**Issue:** `test_a_row_one_second_from_expiry_still_claims` claims at `now + 299 s`, one
second inside a TTL that is `CHALLENGE_TTL_SECONDS = 300`
(`src/nativespeaker/api/crud/challenges.py:15`). 299 is written as a literal rather than
derived from the exported constant, and the case its docstring calls "the boundary from
the other side" never touches the boundary: the predicate is
`col(AuthChallenge.expires_at) > now` (`challenges.py:72`), and flipping it to `>=` leaves
the module green.

```
$ sed -i '72s/expires_at) > now/expires_at) >= now/' src/nativespeaker/api/crud/challenges.py
$ .venv/bin/pytest tests/e2e/test_challenge_store.py tests/unit -q -m ""
1773 passed  (the single failure was CR-80, unrelated)
```

**Fix:** derive both sides from the constant and add the closed half:

```python
from nativespeaker.api.crud.challenges import CHALLENGE_TTL_SECONDS

    async def test_a_row_one_second_from_expiry_still_claims(self, store, _db_transaction):
        """The boundary from the other side, so the case above cannot pass for a claim that rejects all."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            claimed = await store.claim(
                session, challenge_id=handle,
                now=now + timedelta(seconds=CHALLENGE_TTL_SECONDS - 1))
            await session.commit()
        assert claimed is True

    async def test_a_row_claimed_exactly_at_its_expiry_is_refused(self, store, _db_transaction):
        """`expires_at > now` is strict, so the instant of expiry is already too late; without this
        an inclusive comparison passes every case in this class."""
        now = datetime.now(UTC)
        handle, expires_at = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            assert await store.claim(session, challenge_id=handle, now=expires_at) is False
            await session.commit()
```

### WR-110: three suites mirror `get_db` with the commit that WR-01 deleted from production

**File:** `tests/unit/test_create_user_precedence.py:139-149`, `tests/unit/test_claim_precedence.py:246-255`, `tests/unit/test_claim_precedence_registered.py:146-155`

**Issue:** Each of the three `client` fixtures overrides `get_db` with a hand-written generator:

```python
# An async generator, not a plain callable: `get_db` releases the read transaction itself, and a
# callable has no `try`/`except` to do it with. Mirrors `app/dependencies.py::get_db` exactly.
async def _db():
    try:
        yield session
        await session.commit()          # <-- production does not do this
    except Exception:
        await session.rollback()
        raise
```

Production `src/nativespeaker/api/app/dependencies.py:44-55` is:

```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    """The request session: it rolls back on the way out, and never commits."""
    async with request.app.state.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

Two provable divergences: the mirror commits after the yield (removed by `a91f9c9`,
"fix(40): WR-01 stop get_db committing after the response is sent"), and it never enters the
session's `async with`, so the factory/exit path is not exercised. The `test_create_user_precedence.py`
comment asserting the mirror is exact is now factually false.

This is the same failure mode `tests/unit/test_exception_handlers.py:289-292` already names in
prose — *"the real dependency rather than a line-for-line copy of it … against a mirror, deleting
that arm from `app/dependencies.py` left the whole unit suite green"* — and then fixes correctly by
supplying `app.state.session_factory` and letting the real `get_db` run. These three suites did not
get the same treatment.

No assertion depends on the extra commit today (`timeline.index("commit")` finds the challenge
claim's own commit, which precedes it; no case asserts `session.commits` in these three files), so
this is drift and a false comment rather than a false pass — but the drift is in the exact respect
WR-01 classified as a bug.

**Fix:** Delete the mirror and drive the real dependency, as `generator_session_client` already
does. Give the stub session the two context-manager methods and drop the `get_db` override:

```python
# tests/unit/test_claim_precedence.py :: _StubSession  (and _StubSession in
# test_create_user_precedence.py; test_claim_precedence_registered.py inherits it)
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False
```

```python
# in each `client` fixture, replacing the `_db` generator and its override
    app.state.session_factory = lambda: session
    # `get_db` is left un-overridden: it reads only `app.state.session_factory`, and this is the
    # suite whose subject is what it does on the way out.
```

### WR-111: the Play dependency helper passes a `Depends` sentinel where the request instant belongs

**File:** `tests/unit/test_google_play_notifications.py:279-281`

**Issue:** `_verify` calls the real dependency positionally with three arguments:

```python
async def _verify(body: PubSubPushRequest, *, credential=PUSH_CREDENTIAL, **stub):
    """Run the real dependency over a stubbed request, which is what the route resolves."""
    return await verify_google_play_notification(_stub_request(**stub), body, credential)
```

`verify_google_play_notification` (`src/nativespeaker/api/app/dependencies.py:197-232`) declares a
fourth parameter, `evaluated_at: datetime = Depends(get_evaluated_at)`, and forwards it verbatim
into `play_subscriptions.read(..., evaluated_at=evaluated_at)`. Called directly, that default is
the `Depends` object itself. Verified empirically:

```
$ PYTHONPATH=tests .venv/bin/python -c "...await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), play=play)..."
evaluated_at -> <class 'fastapi.params.Depends'> Depends(dependency=<function get_evaluated_at ...>)
```

The docstring's claim ("which is what the route resolves") is false for this argument. Nothing fails
today only because every `_verify`-driven case uses `_RecordingPlay`/`_UncallablePlay`, which never
read the value. The consequence is that the WR-27 property the file spends a whole class on —
*"the adapter's entitlement decision and the grant write are made at the one instant FastAPI cached
for this request"* (`TestTheEntitlementDecisionUsesTheInstantTheRequestCaptured`, lines 420-444) —
is asserted only against `PlayDeveloperSubscriptions.read` called by hand; the dependency-level
wiring that actually delivers the instant is untested, and the first case that asserts on
`play.calls[0]["evaluated_at"]` will be comparing against a sentinel.

**Fix:** Supply the instant explicitly and assert it lands:

```python
async def _verify(body: PubSubPushRequest, *, credential=PUSH_CREDENTIAL,
                  evaluated_at: datetime = EVALUATED_AT, **stub):
    """Run the real dependency over a stubbed request, with every argument the route resolves."""
    return await verify_google_play_notification(_stub_request(**stub), body, credential,
                                                 evaluated_at)
```

and add to `TestTheEntitlementDecisionUsesTheInstantTheRequestCaptured`:

```python
    async def test_the_dependency_forwards_the_solver_resolved_instant_to_the_read(self):
        """WR-27's other half: the instant reaches the adapter through the dependency, not by hand."""
        play = _RecordingPlay()

        await _verify(_push(_rtdn(**SUBSCRIPTION_BODY)), play=play)

        assert play.calls[0]["evaluated_at"] == EVALUATED_AT
```

### WR-112: the push-token stub hook exists but is never driven, so "decoded only after the token check" is untested

**File:** `tests/unit/test_google_play_notifications.py:229-233, 270-276`

**Issue:** `_stub_request` takes a `tokens=` parameter, defaulting to `_AcceptingTokens` (whose
`verify` always returns `None`). A repository-wide grep shows `tokens=` is supplied by no case —
line 270 is the only occurrence outside the definition. So `google_push_tokens.verify` is never made
to raise through the dependency.

That leaves the ordering property the production code states in a comment unasserted:

```python
    await request.app.state.google_push_tokens.verify(credential.credentials)
    # Decoded only after the token check, so a forged body is never parsed.
    notification = developer_notification_from(body.message.data)
```
(`src/nativespeaker/api/app/dependencies.py:207-209`)

Moving the decode above the `verify` call would keep every case in this file green:
`TestTheUndecodableBody` uses the accepting stub, and `TestTheRefusalsDifferOnlyInStage` reaches its
refusal via `credential=None`, which returns before `verify` is called either way. The token-arm
cases in `TestThePushTokenCheck` drive `PubSubPushTokens.verify` directly and never touch the
dependency.

**Fix:** Add a rejecting stub and one ordering case:

```python
class _RefusingTokens:
    """A push token that does not verify, which is what makes the ordering below observable."""

    async def verify(self, bearer: str) -> None:
        raise NotificationRejected(stage="bad_signature")


class TestTheTokenIsCheckedBeforeTheBodyIsParsed:
    """A forged body must never be decoded, so the refusal comes from the token and nothing else."""

    async def test_an_unverifiable_token_refuses_before_the_body_is_decoded(self, play_logs):
        with pytest.raises(NotificationRejected) as refusal:
            await _verify(PubSubPushRequest(message={"messageId": "2280000000000003",
                                                     "data": "this is not base64 at all!!"}),
                          tokens=_RefusingTokens())

        assert refusal.value.stage == "bad_signature"
        # The decode's own ERROR line is what a body parsed ahead of the token check would leave.
        assert play_logs.records("error") == []
```

### WR-113: the anonymous claim's race-loss case does not pin `write_calls == []`, which is the whole of WR-46

**File:** `tests/unit/test_claim_precedence.py:484-497`

**Issue:** `test_the_race_loser_answers_two_hundred_and_still_consumes` requests the `devicecheck`
fixture and never reads it (confirmed by an AST scan of unused test parameters). It asserts only
`status_code == 200`, `store.consume_calls == 1` and `grants.activates == 1`. Deleting the
`if wrote:` guard from `AuthService._claim_anonymous_grant`
(`src/nativespeaker/api/services/auth.py:216-218`) leaves all three true, because
`_ScriptedDeviceCheck.write_bits` records the call and returns normally. The parametrized sweep
does not close the gap either: `_race_lost` in `POST_CLAIM_OUTCOMES` reaches only
`test_each_outcome_consumes_exactly_once`, which asserts consumption alone.

The registered sibling gets this right at
`tests/unit/test_claim_precedence_registered.py:408-427`, which ends with
`assert devicecheck.write_calls == []` under a comment naming WR-64. The anonymous route's
equivalent rule — "a race lost to a grant of any other source must not burn this device's slot" —
is left to the AST check in `test_claim_ordering.py:173-177`, which pins the guard's *shape* but not
its effect.

**Fix:** Add the same assertion the registered sibling carries:

```python
        assert response.status_code == 200
        assert store.consume_calls == 1
        assert grants.activates == 1
        # WR-46: the insert's unique arbiter is any active grant of any source, so the winner is not
        # always another anonymous claim; setting bit0 spends this device's slot on a grant this
        # attempt did not write, and nothing in this product ever clears an Apple bit.
        assert devicecheck.write_calls == []
```

Do the same in `test_a_lost_race_whose_re_read_finds_nothing_is_refused_rather_than_reported_as_a_grant`
(line 515), whose `devicecheck` parameter is likewise unused.

### WR-114: `ActiveGrantOutsideItsTerm` is the one claim arm with no route-level status or body assertion

**File:** `tests/unit/test_claim_precedence.py:668-670, 704-722`, `tests/unit/test_claim_precedence_registered.py:577-581, 615-634`

**Issue:** Every other post-claim arm on both routes has a named case asserting the exact
`(status, body)` pair — `ClaimantNotAnonymous`, `ClaimantNotRegistered`, `FreeGrantAlreadyConsumed`,
`OtherActiveGrantHeld`, `DeviceGrantExhausted`, `ProofRejected`, `Unavailable`,
`ClaimRefusedUnderLock`, the repeat, the conversion and the success. `ActiveGrantOutsideItsTerm` —
the one-active-index tripwire at `services/auth.py:194-196` and `:255-257` — appears only as
`_marked_outside_its_term` inside `POST_CLAIM_OUTCOMES`, and the only case that consumes that tuple
asserts `store.consume_calls == 1` and `store.row.consumed_at is not None`.

So if that branch were changed to raise a different class (say `MultipleEffectiveGrantsError`, a
500, or a class carrying a distinguishable code), both claim suites stay green. The class's own
`(403, operation_not_allowed)` contract is pinned in `test_rejection_vocabulary.py`, but nothing
pins that this route reaches *that* class.

**Fix:** Give the arm a named case in each file, beside its siblings. For the anonymous route:

```python
    def test_a_grant_the_one_active_index_sees_outside_this_window_is_refused_and_still_consumes(
            self, client, store, account, grants, devicecheck):
        """The row the status-only read finds and the effective read cannot: the insert below would
        be refused by the one-active index, so this fails closed rather than racing it."""
        identity_row, _ = account
        grants.marked_active = [_a_grant(AccessGrantSource.anonymous_device_grant)]
        store.row = _issued_row(bound_to=identity_row.id)

        response = _claim(client)

        assert response.status_code == 403
        assert response.json() == REFUSED
        assert store.consume_calls == 1
        assert grants.activates == 0
        assert devicecheck.read_calls == []
```

and the registered mirror using that file's `_marked_outside_its_term` setup (`held` = one anonymous
grant, `marked_active` = one subscription).

### WR-115: six wall-clock tests do not carry the project's `timing` marker

**File:** `tests/unit/test_devicecheck_adapter.py:292-325`, `tests/unit/test_firebase_retry.py:156-186`

**Issue:** `pyproject.toml` declares the marker and its purpose:
`"timing: marks tests whose assertion is wall-clock dependent (report separately with -m timing)"`,
and `tests/unit/test_jwks_offload.py:160,179` applies it. Both `TestTheAttemptsAreSeparatedInTime`
classes assert on `time.monotonic()` deltas — three cases each — and neither class nor any of its
methods is marked. Two of the six (`test_a_budget_that_was_not_exhausted_pays_no_wait_control`)
carry an *upper* bound (`< FLOOR_SECONDS`), which is the direction that goes flaky under load; the
convention exists precisely so those can be reported apart from the deterministic suite.

**Fix:** Mark both classes:

```python
@pytest.mark.timing
class TestTheAttemptsAreSeparatedInTime:
    """WR-21: the budget was spent inside a few milliseconds, so it bought nothing against a blip."""
```

### WR-116: a test name states the opposite of what the test asserts

**File:** `tests/unit/test_exception_handlers.py:186-192`

**Issue:**

```python
    def test_the_two_forbidden_arms_answer_the_same_status_and_body(self, handler_client):
        """`operation_not_allowed` and `account_unavailable` are both 403 and must stay distinct codes."""
        ...
        assert forbidden.status_code == unavailable.status_code == 403
        assert forbidden.json() != unavailable.json()
```

The name promises the same status **and body**; the assertion requires the bodies to *differ*, which
is what the docstring and the contract actually want. In a file whose subject is the anti-oracle
rule — where several *other* classes genuinely must be byte-identical
(`TestAnAccountUnavailableArmTravelsTheWholeErrorPath::test_the_two_arms_are_indistinguishable_to_the_client`
at line 405 uses `_comparable(...) == _comparable(...)`) — a name reading "answer the same body" is
a live invitation for a later fixer to "repair" the `!=` into `==` and collapse two distinct 403
codes.

**Fix:** Rename to match the assertion:

```python
    def test_the_two_forbidden_arms_share_a_status_and_keep_distinct_codes(self, handler_client):
```

### WR-140: The restore's COMMIT-time case is driven with an exception carrying no SQLSTATE, so it proves the opposite of its own name

**File:** `tests/unit/test_restore_proof.py:764-779`

**Issue:** `TestTheDeferredKeysAreClassifiedWhereTheyAreEvaluated` is documented as
"the grant keys are DEFERRABLE INITIALLY DEFERRED, so COMMIT is their only evaluation", and the case
is named `test_a_violation_at_commit_is_the_lost_race_the_flushes_report`. But line 770 builds

```python
session = _CommittingSession(IntegrityError("COMMIT", {}, Exception("23503")))
```

`Exception("23503")` is a bare exception whose `"23503"` is only its *message*. It carries no
`sqlstate` attribute, so `is_unique_violation` (`src/nativespeaker/api/crud/violations.py:13`,
`getattr(violation.orig, "sqlstate", None) == "23505"`) reads it as `False`. Three consequences:

1. The deferred **unique** violation (23505) the docstring names is never exercised. The case
   passes for *any* `IntegrityError`, so narrowing or widening the catch at
   `src/nativespeaker/api/services/restore.py:185` cannot fail it.
2. It certifies that a foreign-key / NOT NULL / CHECK failure at COMMIT is recorded as
   `restore_grant_race_lost` — the exact opposite of what this same file asserts for the flush path
   at line 959-964 ("A NOT NULL or a foreign key is a broken invariant, and swallowing it would
   hide it") and what `test_identity_flip.py:84` asserts ("a CHECK or a foreign key is divergent
   stored state, never a reservation this write lost").
3. The file already owns the right helper — `_violation(sqlstate)` at line 923, backed by `_Orig`
   at line 898 — and this one case bypasses it.

This is `41-REVIEW.md` **WR-01** on the restore path. Behaviourally the client sees 500 either way,
so this is not data loss; the damage is an operator log line that names a broken invariant as a
race, and a test that cannot detect it.

**Fix:** Use the file's own helper and split the two classes apart.

```python
    async def test_a_deferred_unique_violation_at_commit_is_the_lost_race(self, race_warnings):
        session = _CommittingSession(_violation(UNIQUE_VIOLATION))

        with pytest.raises(InternalError):
            await _same_account_restore(EVALUATED_AT - timedelta(days=1), session=session)

        assert (session.commits, session.rollbacks) == (1, 1)
        assert race_warnings == [("restore_grant_race_lost", {"provider": "apple"})]

    @pytest.mark.parametrize("sqlstate", ["23502", "23503", "23514"])
    async def test_every_other_integrity_failure_at_commit_is_not_a_race(self, sqlstate,
                                                                         race_warnings):
        """A CHECK or a foreign key is divergent stored state, exactly as the flush arms read it."""
        session = _CommittingSession(_violation(sqlstate))

        with pytest.raises(IntegrityError):
            await _same_account_restore(EVALUATED_AT - timedelta(days=1), session=session)

        assert race_warnings == []
```

The second case requires narrowing `restore.py:185` to `except IntegrityError as conflict:` +
`if not is_unique_violation(conflict): raise`. If that narrowing is deliberately refused, the case
should instead assert the current behaviour explicitly and say so, rather than leaving the file
looking as though it tested 23505.

### WR-141: The same COMMIT-time case in the subscriptions suite has the same defect

**File:** `tests/unit/test_subscription_attribution.py:72-77, 717-733`

**Issue:** `_RefusingSession.commit` raises `IntegrityError("COMMIT", {}, Exception("23503"))` — the
identical no-SQLSTATE exception, driving the identical arm at
`src/nativespeaker/api/services/subscriptions.py:181-185`. The class docstring again names the
deferred keys, and again no 23505 is ever presented. Unlike `test_restore_proof.py`, this file has
no `_violation` helper at all, which is what made the shortcut easy.

The consequence is the same: `test_a_violation_at_commit_is_the_lost_race_the_flushes_report`
(line 721) asserts `store_notification_race_lost` for what is presented as a foreign-key failure.

**Fix:** Add the helper this file lacks and parameterise the session.

```python
class _Orig(Exception):
    """The DBAPI exception SQLAlchemy wraps, carrying the one attribute the writer reads."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


class _RefusingSession(_StubSession):
    """The stub session whose commit raises what the deferred entitlement keys raise at COMMIT."""

    def __init__(self, sqlstate: str = UNIQUE_VIOLATION) -> None:
        super().__init__()
        self._sqlstate = sqlstate

    async def commit(self) -> None:
        self.commits += 1
        raise IntegrityError("COMMIT", {}, _Orig(self._sqlstate))
```

Then keep `_RefusingSession()` for the race case and add a `_RefusingSession("23503")` case
asserting whatever the ratified answer for a broken invariant at COMMIT is — see WR-140.

### WR-142: `_UpsertResult.rowcount` is hard-coded to 1, so the upsert's `lost_race` arm is unreachable in the file that owns it

**File:** `tests/unit/test_subscription_attribution.py:80-101`

**Issue:** `_UpsertResult.__init__` pins `self.rowcount = 1` with the comment "One, because nothing
else writes this row inside a case here". That makes the conditional owner claim inside the real
`SubscriptionsDB.upsert_subscription` always succeed, so the recorder can only ever return
`applied` or `replayed`.

But `SubscriptionsService.ingest` calls `await self._settle(outcome, notification)` on the upsert's
outcome at `src/nativespeaker/api/services/subscriptions.py:141`, and `_settle` rolls back, writes
`store_notification_race_lost` and raises `InternalError` when that outcome is `lost_race`. No case
in this file can produce it. Worse, the file's own WR-49 note at lines 168-171 explicitly names
`lost_race` as an outcome production answers with — the very reason the stand-in was replaced by the
real writer — yet the session it runs over makes that outcome impossible.

`tests/unit/test_subscription_store_clock.py:169-175` covers the crud returning `lost_race`, but
nothing covers the *service's* response to it.

**Fix:** Give the session the flag `test_subscription_store_clock.py::_StubSession` already has, and
add the missing case.

```python
class _UpsertResult:
    def __init__(self, row: Subscription | None, rowcount: int = 1) -> None:
        self._row = row
        self.rowcount = rowcount


class _UpsertSession:
    def __init__(self, stored: Subscription | None, claimed: bool = True) -> None:
        self._stored = stored
        self._claimed = claimed
        self.added: list = []

    async def exec(self, statement) -> _UpsertResult:  # noqa: ARG002
        return _UpsertResult(self._stored, 1 if self._claimed else 0)
```

Thread a `claim_wins: bool = True` through `_RecordingSubscriptions.__init__` into
`_UpsertSession(...)` at line 172, then:

```python
    async def test_a_restore_that_took_the_unowned_row_first_refuses_this_delivery(
            self, session, writer, race_warnings):
        """The upsert's own lost race: the service must roll back and write nothing further."""
        writer.claim_wins = False
        _seed_owned(writer, None, external_id=(external_id := f"original-{uuid4()}"))
        service = _service(session, writer, ORIGINAL_BUYER)

        with pytest.raises(InternalError):
            await service.ingest(_notification(attribution_token=TOKEN, external_id=external_id))

        assert session.rollbacks == 1
        assert (writer.granted, writer.inserted) == ([], [])
        assert race_warnings == [("store_notification_race_lost", {"provider": "apple"})]
```

### WR-143: `RestoreService`'s lost owner claim and `_answer_as_the_winner_left_it` have no unit case at all

**File:** `tests/unit/test_restore_proof.py:619-645, 692-718`

**Issue:** `src/nativespeaker/api/services/restore.py:139-151` runs the adoption/move owner claim,
and on `claimed is False` returns `await self._answer_as_the_winner_left_it(proof, destination)`
(restore.py:196-207) — a branch that rolls back, re-reads the canonical row, returns quietly when
the winner was this same account, and raises `RestoreSubscriptionNotEntitled` for every other state.

Neither double in this file can reach it:

- `_GrantRecorder` (line 692) does not define `claim_subscription_owner` at all. Its
  `read_subscription` returns a row whose `user_id` is the caller, so `owner_read == destination`
  and restore.py:139 skips the whole block. Add the branch back and the recorder would fail with
  `AttributeError`, not with a meaningful assertion.
- `_InsertOnlyRecorder` (line 619) raises `_Stop` from `insert_subscription`, which is upstream of
  the claim.

`grep -rn "_answer_as_the_winner_left_it" tests/` returns nothing.
`grep -rn "claim_subscription_owner" tests/` returns one hit,
`tests/schema/test_restore_race.py:465`, which drives the *crud* method and is deselected from the
default run by `pyproject.toml:64` (`addopts = "-v --tb=short -m 'not e2e and not schema'"`).
`tests/e2e/test_restore_subscription.py` covers the adoption success path and the transfer cap, not
the lost claim. So the rollback-and-re-read branch ships with zero coverage in the default suite.

**Fix:** Teach `_GrantRecorder` the method and script both outcomes of the re-read.

```python
class _GrantRecorder:
    def __init__(self, destination, settled_status=SubscriptionStatus.active, *,
                 owner=..., claim_wins: bool = True, winner_owner=None) -> None:
        ...
        self._claim_wins = claim_wins
        # What the re-read after the rollback finds, which is what the winner left behind.
        self._winner_owner = winner_owner

    async def claim_subscription_owner(self, **fields) -> bool:
        self.claims.append(fields)
        if not self._claim_wins:
            self._stored.user_id = self._winner_owner
        return self._claim_wins
```

Build the recorder with `owner=None` (an unowned row, so restore.py:139 is entered), then two cases:

```python
    async def test_a_claim_the_same_account_already_won_returns_without_raising(self):
        """The winner was another attempt of this same account, so its rows are there to read."""
        # claim_wins=False, winner_owner=caller.user.id -> returns, no grant written
    async def test_a_claim_another_account_won_is_not_this_accounts_to_restore_from(self):
        # claim_wins=False, winner_owner=uuid4() -> RestoreSubscriptionNotEntitled
```

Both must also assert `session.rollbacks == 1` and `recorder.granted == []`.

### WR-144: The restore suite drives the service with an `Identity` shape the barrier cannot produce

**File:** `tests/unit/test_restore_proof.py:536-538`

**Issue:**

```python
def _caller() -> Identity:
    return Identity(issuer="https://issuer.test", subject="restore-ordering-subject",
                    user=User(), identity=None)
```

`RestoreService.restore` is declared `identity: LinkedIdentity`
(`src/nativespeaker/api/services/restore.py:50`), and `LinkedIdentity`
(`src/nativespeaker/api/schemas/auth.py:113-121`) narrows both rows to non-`None` precisely so a
linked-only path "dereferences both rows without an `assert` that `python -O` strips". A `user`
present with `identity=None` is a state `IdentitiesDB.resolve` cannot return — it sets the two
together or neither (`crud/identities.py:44-52`) — and
`test_identity_accessors.py:313-319` asserts exactly that ("nullability is the whole distinction the
store branches on").

`tests/unit/conftest.py:119-121` writes the rule down verbatim for the same reason:

> `LinkedIdentity`, because this is what `get_linked_identity` is overridden with: a plain
> `Identity` here would stand in for a narrowing the production dependency cannot return.

Every other suite obeys it (`test_users_me.py:75-83`, `conftest.py:121-132`). This one does not, and
the type annotation on `_caller()` makes the divergence look deliberate.

**Fix:** Build the shape the barrier actually hands the handler.

```python
def _caller() -> LinkedIdentity:
    user = User()
    return LinkedIdentity(issuer="https://issuer.test", subject="restore-ordering-subject",
                          user=user,
                          identity=ExternalIdentity(user_id=user.id,
                                                    issuer="https://issuer.test",
                                                    subject="restore-ordering-subject",
                                                    provider=IdentityProvider.google,
                                                    provider_uid="google-account-restore"))
```

with `LinkedIdentity`, `ExternalIdentity` and `IdentityProvider` added to the imports.

### WR-145: The "written exactly once" period scan matches only one of the two legal quote spellings

**File:** `tests/unit/test_monthly_period.py:11, 43-47`

**Issue:** `TestTheDerivationIsWrittenExactlyOnce` exists because "Five copies is what let two of
them each claim to be the only one". The scan is:

```python
FORMAT = '"%Y-%m"'
...
return sorted(path for path in SRC.rglob("*.py") if FORMAT in path.read_text())
```

`FORMAT` is the *double-quoted* literal, so the walk sees `strftime("%Y-%m")` and misses
`strftime('%Y-%m')`. Ruff's configured rule set is `select = ["E", "W", "F", "I", "UP"]`
(`pyproject.toml:76`) — no `Q` / flake8-quotes — and the codebase already mixes styles:
`src/nativespeaker/api/tables/identities.py:30-33` uses `name='identity_provider'`. So a
single-quoted second copy is both legal and invisible here. Verified:

```
double-quoted copy seen: True
single-quoted copy seen: False
fstring spec copy seen:  False
```

The class name is a guarantee the test does not deliver.

**Fix:** Match on the format string itself and on both quotings, so a copy cannot hide behind a
quote character.

```python
# Both legal quotings, and the format-spec form: ruff enforces no quote style in this repo.
SPELLINGS = ('"%Y-%m"', "'%Y-%m'", ":%Y-%m}")


def _files_formatting_a_period(self) -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py")
                  if any(spelling in path.read_text() for spelling in SPELLINGS))
```

`src/nativespeaker/api/logs.py:49` carries `"%Y-%m-%d %H:%M:%S"`, which none of the three spellings
matches, so the assertion `== [DERIVATION]` still holds.

### WR-146: The flip's "sets where unset" class asserts only one of the two columns it is named for

**File:** `tests/unit/test_identity_flip.py:106-139`

**Issue:** `TestTheFlipSetsWhereUnsetAndNeverOverwrites` is documented as
"`req~users-upgrade-step-07~1` sets `registered_at` if it is NULL, as `email` already is", and
`oft-conventions.md:122-123` lists that requirement as a known fold point whose assertions must be
enumerated individually. Four cases follow. Three cover `registered_at` (stamped when NULL,
preserved when stored, `updated_at` moves either way) and one covers `email` *not* being
overwritten. Nothing covers `email` being written when it is NULL.

`IdentitiesDB.flip_provider` does write it (`src/nativespeaker/api/crud/identities.py:160-162`):

```python
        if user.email is None:
            user.email = email
```

Delete those three lines and all nine cases in this file still pass. `grep -rn "user.email" tests/`
shows the only assertion that would catch it is `tests/e2e/test_upgrade_anonymous.py:134`, and the
e2e suite is deselected from the default run by `pyproject.toml:64`. The upgrade route's own suite
does not help: `test_upgrade_precedence.py:95-103`'s `_RecordingUpgrade.flip` records `email` and
never applies it.

So the default `pytest` run has no case at all for the flip copying a verified address.

**Fix:** Add the missing half beside its sibling, and rename the parameter case for symmetry.

```python
    async def test_an_unset_email_takes_the_verified_address(self):
        """The other half of step 07: NULL is filled, and the fill is what the route reports back."""
        identity_row, user = _account()

        await _flip(_StubSession(), identity_row, user)

        assert user.email == EMAIL
```

### WR-147: The `/users/me` refusal case promises a cache-header assertion its body never makes

**File:** `tests/unit/test_users_me.py:219-227`

**Issue:** `test_the_refusal_carries_no_cache_header_and_no_identifier` asserts three things — the
body has exactly one key, and neither store token appears in the text — and never touches
`response.headers`. The `no cache header` half of the name is unbacked, and a reader auditing the
secrecy of the 500 path will believe it was checked.

The route sets the header on the injected `Response` (`src/nativespeaker/api/routers/users.py:24`),
which is bypassed when the shared exception handler builds its own `JSONResponse`. I drove both
paths:

```
500 path: 500 {'content-length': '25', 'content-type': 'application/json'}
200 path: 200 no-store
```

so the assertion is true today and adding it is safe.

**Fix:** Assert what the name claims.

```python
        assert response.status_code == 500
        # The name's other half: the refusal renders through the shared handler, which sets none.
        assert "cache-control" not in response.headers
        assert set(response.json()) == {"code"}
```

## Info

### IN-01: A comment names `llm-routes`, a template deleted in this range

**File:** `k8s/templates/httproute-auth.yaml:14`

**Issue:** "Under the JWT SecurityPolicy, as app-routes and llm-routes are."
`k8s/templates/httproute-llm.yaml` was deleted in this diff range (`git show
def8063:k8s/templates/httproute-llm.yaml` still has it); `/chats` now lives on `app-routes`
(`httproute-app.yaml:18`) and the SecurityPolicy targets exactly two routes
(`security-policy.yaml:9-15`).

**Fix:** "Under the JWT SecurityPolicy, as app-routes is."

### IN-02: `resilence_config` is misspelled at every one of its call sites

**File:** `src/nativespeaker/api/app/lifespan.py:206`, `src/nativespeaker/api/services/llm.py:18`, `src/nativespeaker/api/services/llm.py:26`

**Issue:** The keyword parameter is `resilence_config`, not `resilience_config`. It is a public
keyword-argument name, so the typo has propagated to five sites (`lifespan.py:206`,
`services/llm.py:18`, `services/llm.py:26`, `tests/unit/test_config.py:100`,
`tests/e2e/test_llm_schema.py:38`) and it disagrees with `ResilienceConfig`,
`ResiliencePolicy`, `resilience.py` and `config.resilience` everywhere else.

**Fix:** Rename to `resilience_config` at all five sites.

### IN-03: `exc_info` is decided from the unclamped level while the log line is emitted at the clamped one

**File:** `src/nativespeaker/api/app/error_handlers.py:38`, `src/nativespeaker/api/app/error_handlers.py:45`

**Issue:** Line 38 clamps an out-of-set level to `logging.ERROR` (`level = exc.log_level if
exc.log_level in _LOGGABLE else logging.ERROR`), but line 45 tests the raw value
(`exc_info=exc if exc.log_level >= logging.ERROR else False`). A class declaring, say,
`log_level = 25` would be recorded at ERROR — the level whose whole point here is that it
carries the stack — with `exc_info=False` and no traceback. No class does this today, so it is
latent, not live.

**Fix:** Test the value that is actually used: `exc_info=exc if level >= logging.ERROR else False`.

### IN-04: An unreachable `except asyncio.QueueFull: pass` would silently leak an in-flight slot if it ever fired

**File:** `src/nativespeaker/api/resilience.py:110-113`

**Issue:** The token being returned was taken out of the same fixed-size queue five lines above
(`resilience.py:104`), so `put_nowait` cannot raise `QueueFull`. The arm is dead. If the
invariant were ever broken it would swallow the failure and permanently shrink the gate's
capacity by one slot, which is the one outcome a bare `pass` should not choose here.

**Fix:** Return the token unconditionally; the try/except adds nothing.

```python
        try:
            yield
        finally:
            self._slots.put_nowait(token)
```

### IN-05: Two superseded Apple root certificates ship in the image beside the one that is used

**File:** `Dockerfile:29`

**Issue:** `COPY config ./config/` ships `config/certs/AppleIncRootCertificate.cer` and
`config/certs/AppleRootCA-G2.cer` alongside `AppleRootCA-G3.cer`. Neither is referenced
anywhere — `grep -rn 'AppleIncRootCertificate\|AppleRootCA-G2' src tests config k8s Dockerfile
.env.example` returns nothing; `config.py:167` derives only the G3 path. They are a trap rather
than dead weight: `build_app_store_verifier` validates only that the file parses as DER
(`lifespan.py:67`), so `APP_STORE_ROOT_CERTIFICATE_PATH` pointed at either one builds a verifier
that boots clean, logs no warning, and then refuses every genuine Apple notification with 401 —
which Apple retries on its own schedule, so nothing looks broken from outside.

**Fix:** Delete the two unused `.cer` files from `config/certs/`, leaving the one root the
derived default names.

### IN-06: The comment above `_SUPPORTED_LEVELS` is wrong about which names structlog rejects

**File:** `src/nativespeaker/api/config.py:9-11`

**Issue:** The comment says `logging` "also admits FATAL, WARN and NOTSET, which
`structlog.make_filtering_bound_logger` has no entry for and crashloops the pod at startup."
`structlog._log_levels.NAME_TO_LEVEL` in the pinned structlog 25.5.0 is
`['critical', 'debug', 'error', 'exception', 'info', 'notset', 'warn', 'warning']` — it
accepts both `warn` and `notset`. Only `fatal` is absent, and it maps to the same integer as
`critical` anyway. The narrowing is still right (this service has no use for NOTSET); the
stated reason is not.

**Fix:** Restate the ground — these are the five levels the service supports, and NOTSET is
excluded because "log everything" is not a level this service offers.

### IN-07: `values.yaml` cites a line number that has moved

**File:** `k8s/values.yaml:67`

**Issue:** "`DEVICECHECK_PRIVATE_KEY_PATH` is a path (`config.py:81`)". The field is
`DeviceCheckConfig.private_key_path` at `src/nativespeaker/api/config.py:79`.

**Fix:** Cite the symbol rather than the line — `DeviceCheckConfig.private_key_path` — so the
next edit to `config.py` cannot silently invalidate it.

---

_Reviewed: 2026-09-10T00:40:36Z_
_Reviewer: Claude (gsd-code-reviewer), part A of 7_
_Depth: standard_

### IN-20: `PubSubPushRequest.subscription` is declared and read nowhere

**File:** `src/nativespeaker/api/schemas/webhooks.py:40`

**Issue:** `subscription: str | None = None` has no reader anywhere in `src/` —
`dependencies.py:196-232` consumes `body.message.data` and nothing else. This is
the exact case the sibling field's comment argues against: `PubSubPushMessage`
drops `messageId` because "nothing read it ... in exchange for validating a value
the service never used" (`:22-26`). Being optional it costs no 422, so this is
cleanup rather than a defect — but the class docstring ("one message, and the
subscription that delivered it") describes a field the service does not have.

**Fix:** Delete the field and trim the docstring to "The Cloud Pub/Sub push body:
one message." Pydantic ignores what is not declared, so a delivery still carrying
`subscription` is unaffected — the same argument the `messageId` comment already
makes.

### IN-21: the never-set bodies are matched case-sensitively while the same-provenance fault phrase is casefolded

**File:** `src/nativespeaker/api/auth/devicecheck.py:36`, `src/nativespeaker/api/auth/devicecheck.py:126`, `src/nativespeaker/api/auth/devicecheck.py:141`

**Issue:** `_DEVICE_TOKEN_FAULT` is matched as a casefolded substring
(`:126`) precisely because "these literals are [ASSUMED] from secondary sources".
`_NEVER_SET_BODIES` comes from the *same* [ASSUMED] source
(`41-RESEARCH.md:333`, `:691` A5) yet is matched by exact, case-sensitive
equality (`:141`). The two members already disagree on casing convention
("Failed to find bit state" vs "Bit State Not Found"), which is itself evidence
that the exact strings are not known.

Consequence if the casing differs from what was assumed: the body falls through
to `_reject_or_retry`, a 200 passes it, `_decoded` cannot parse plain text, and
every first-ever claim answers 503. `41-RESEARCH.md` A5 already records this
("If the string differs, every first claim 503s ... Widen `_NEVER_SET_BODIES`
when a real response is seen"), so the risk is acknowledged — this is the cheap
half of that widening, available now without a real Apple response.

**Fix:** Still a whitelist, so it cannot fail open:

```python
_NEVER_SET_BODIES = frozenset({"failed to find bit state", "bit state not found"})
...
    body = response.text.strip().casefold()
```

### IN-22: `_names_one_path_segment`'s docstring is narrower than the rule it implements

**File:** `src/nativespeaker/api/auth/google_play.py:183-185`

**Issue:** The docstring justifies the guard by httpx's dot-segment removal, but
the implementation (`bool(value.strip("."))`) refuses **any** all-dots value. I
put the quoted values through `httpx.URL` and confirmed httpx collapses only `.`
and `..`; `"..."` and `"...."` survive as ordinary segments. So the guard is
strictly stronger than its stated reason — which is the right direction (fail
closed), but a future reader comparing the two will read it as a bug and may
"correct" it to `value not in {".", ".."}`, reintroducing nothing today but
narrowing the guard for no reason.

**Fix:** Say what it does.

```python
def _names_one_path_segment(value: str) -> bool:
    """Refuse any all-dots value. httpx deletes the `.` and `..` segments `quote` leaves
    unescaped; the wider all-dots rule costs nothing and needs no per-version check."""
    return bool(value.strip("."))
```

---

_Reviewed: 2026-09-10T00:44:52Z_
_Reviewer: Claude (gsd-code-reviewer), part B of 7_
_Depth: standard_

### IN-40: `Chat.human_messages` is dead code

**File:** `src/nativespeaker/api/tables/chats.py:60-62`
**Issue:** `ai_messages` has one reader (`services/chats.py:121`); `human_messages`
has none in `src/` or `tests/`. It is the only property in the package with no
caller.
**Fix:** delete it; re-add it beside its first reader.

### IN-41: `Chat.created_at` and `Message.created_at` mint a second clock read

**File:** `src/nativespeaker/api/tables/chats.py:32`, `:45`
**Issue:** Both use `default_factory=lambda: datetime.now(UTC)` while
`ChatsService` already holds one captured `self.evaluated_at`
(`services/chats.py:45`) and charges quota against it. So one request stamps a chat,
its message and its usage row from three different instants. `tables/grants.py:111`
states the opposite rule for the entitlement tables ("the creating transaction owns
the clock"), and `tests/unit/test_tables_metadata.py::TestTheEntitlementTablesHoldNoSecondClock`
enforces it — but only over `AccessTier`/`AccessGrant`/`UserMonthlyUsage`. Filed as
Info on the precedent of `.planning/REQUIREMENTS.md:529` IN-01, where the same
second-clock-read was deferred as millisecond skew.
**Fix:** drop both `default_factory` values and pass `created_at=self.evaluated_at`
from `services/chats.py:94-96`, matching the entitlement tables.

### IN-42: `count_chats` is the one crud read that bypasses `session.exec` and `col()`

**File:** `src/nativespeaker/api/crud/chats.py:26-28`
**Issue:** Three small inconsistencies in one method: it calls
`self.session.scalar(...)` where every other read in the package uses
`session.exec`; it writes `Chat.user_id == user_id` where every sibling wraps the
attribute in `col()`; and it is annotated `-> int` while `AsyncSession.scalar`
yields `Any | None`, so `services/chats.py:91` (`chats_count >= self.chats_limit`)
carries an unproven non-`None`. `SELECT count(*)` always returns a row, so this
cannot fire.
**Fix:** `return (await self.session.exec(select(func.count()).select_from(Chat)
.where(col(Chat.user_id) == user_id))).one()`.

### IN-43: `crud/grants.py` imports one package two ways

**File:** `src/nativespeaker/api/crud/grants.py:14-22` and `:23`
**Issue:** Lines 14-22 import from `nativespeaker.api.tables`; line 23 imports
`ExternalIdentity`, `IdentityProvider` and `NativeClaimProvider` from
`nativespeaker.api.tables.identities`. All three are re-exported by the package
`__init__` (`tables/__init__.py:9-11`, `:27-32`), and no import cycle forces the
split.
**Fix:** fold line 23 into the package import above it.

### IN-44: `GrantsDB` builds an `IdentitiesDB` inline at two call sites

**File:** `src/nativespeaker/api/crud/grants.py:166`, `:234`
**Issue:** `IdentitiesDB(self.session)` is constructed inside each writer, while the
sibling crud holds its collaborator once (`crud/subscriptions.py:76`,
`self.grants_db = GrantsDB(session)`). Two spellings of the same dependency.
**Fix:** `self.identities_db = IdentitiesDB(session)` in `GrantsDB.__init__`.

### IN-45: The anonymous writer's multiple-grant tripwire is ordered after its identity refusals

**File:** `src/nativespeaker/api/crud/grants.py:168-178` vs `:236-243`
**Issue:** In `activate_registered_account_grant` the
`MultipleEffectiveGrantsError` tripwire is read at `:240`, immediately after the
provider test, with the comment "read before the source tests below". In
`activate_anonymous_device_grant` the same tripwire sits at `:176`, after the
provider refusal at `:168` and the platform-pin refusal at `:170`. So an account
that has both a two-effective-grant integrity break and a divergent identity row is
answered with a 403 refusal and the integrity break is never logged. Both refusals
precede every source test in either writer, so no source is ranked either way; the
index makes the state unreachable regardless.
**Fix:** move the `len(grants) > 1` check in the anonymous writer to sit directly
after the `stored is None` guard, matching the sibling's ordering and comment.

---

_Reviewed: 2026-09-09_
_Reviewer: Claude (gsd-code-reviewer), part C of 7_
_Depth: standard_
_No source file was modified. Two throwaway rows were written to the dev database by
the empirical probes behind WR-40 and WR-42 and deleted by the same scripts._

### IN-60: the auth service's module docstring counts three completions; there are four

**File:** `src/nativespeaker/api/services/auth.py:1`

**Issue:** `"""The three completions: ..."""`. The class exposes four:
`complete` (:83), `complete_upgrade` (:91), `complete_claim_anonymous_grant` (:99) and
`complete_claim_registered_grant` (:110). The count is stale from before Phase 42 added the
fourth, and the trailing list — "the rejection precedence, the claim, the post-claim work
and the spend" — has four items too, so the number is not describing that either.

**Fix:** `"""The completions: the rejection precedence, the claim, the post-claim work and the spend."""`

---

### IN-61: one file, two spellings of `raise`

**File:** `src/nativespeaker/api/services/auth.py:132`, `:137`, `:145`, `:147`, `:178`, `:192`, `:194`, `:198`, `:244`, `:255`, `:259`, `:263`, `:270`, `:316`, `:337`, `:398`, `:402`, `:403`

**Issue:** the challenge rejections are raised as instances (`raise ChallengeNotFound()`,
`raise ChallengeExpired()`, `raise ChallengeConsumed()`, `raise ChallengeOperationMismatch()`,
`raise IdentityAlreadyLinked()`) and the claim rejections as bare classes
(`raise ClaimantNotAnonymous`, `raise FreeGrantAlreadyConsumed`, …). Both work. The bare
form is the majority across the package, so the parenthesized calls in this one file are
the outliers.

**Fix:** drop the empty parentheses on `:132`, `:145`, `:147`, `:137`, `:403` so the file
reads one way throughout.

---

### IN-62: `resilence_config` is misspelled in a constructor signature

**File:** `src/nativespeaker/api/services/llm.py:18`

**Issue:** the parameter is `resilence_config`; the type is `ResilienceConfig` and the
module it comes from is `resilience`. `lifespan.py` has to spell the typo at the call site
to construct the service.

**Fix:** rename to `resilience_config` here and at the one construction site in
`app/lifespan.py`.

---

### IN-63: four callables in scope carry no return annotation

**File:** `src/nativespeaker/api/services/llm.py:15-19`, `:37`; `src/nativespeaker/api/routers/chats.py:21-22`; `src/nativespeaker/api/routers/root.py:15`

**Issue:** `LLMService.__init__` has no `-> None`, `LLMService.admission` has no return
type, and the handlers `list_chats` and `root` have none while every sibling handler in
their own files does (`get_chat_messages -> list[MessageResponse]`, `create_chat ->
MessageResponse`, `delete_chat -> Response`). `ty` passes either way, so nothing is broken;
the inconsistency is the whole of it.

**Fix:** `def admission(self) -> Admitted:` — `Admitted` is already imported at `llm.py:10`
— `def __init__(...) -> None:`, `async def list_chats(...) -> list[ChatResponse]:`, and
`async def root(...) -> dict[str, object]:`.

---

_Reviewed: 2026-09-09T18:05:00Z_
_Reviewer: Claude (gsd-code-reviewer), part D_
_Depth: standard_

### IN-80: The claim race's device fake records calls nobody reads

**File:** `tests/schema/test_claim_race.py:154-166`
**Issue:** `_NeverSetDevice` maintains `read_calls` and `write_calls`, and no case in the
file asserts either. The loser of `TestTwoSimultaneousFirstClaimsAllocateOnce` takes the
`lost_race` arm — precisely the branch the `if wrote:` guard at
`src/nativespeaker/api/services/auth.py:225` protects, whose own comment reads *"a race
lost to a grant of any other source must not burn this device's slot"*. The observable is
already collected on a real two-connection race; nothing looks at it.
(`tests/unit/test_claim_ordering.py` covers the guard against a stub, so this is a missed
cheap assertion rather than an uncovered behaviour.)
**Fix:** in `run_attempt`, carry the fake onto the `_Attempt`, then assert
`raced["by_role"]["lost_at_flush"].write_calls == []` and that the winner's is
`[(f"device-{winner.name}", True, False)]`.

### IN-81: Stale comment names a table Phase 42 deleted

**File:** `tests/e2e/test_claim_anonymous_grant.py:282`
**Issue:** `# The revoked row and its anti-abuse row are still the only ones: nothing was
written.` `core.access_grants_anti_abuse` was removed by Phase 42 D-07 (`.planning/STATE.md:624`)
and appears nowhere in `migrations/`. The two numbers `_row_counts` returns are the grant
row and the usage row.
**Fix:** `# The revoked row and its usage row are still the only ones: nothing was written.`

### IN-82: `insert_usage` defaults to a month that is now in the past

**File:** `tests/schema/helpers.py:117`
**Issue:** `monthly_period: str = "2026-08"` is a fixed literal, and today is 2026-09.
No current case depends on the default matching the current month, but
`tests/schema/test_sync_lock_freedom.py:325-328` had to override it with the comment
*"The seeded period must match the evaluated instant, or every read reports zero used
instead of the count"* — so the trap is already known and is one careless call away from
a case that passes for the wrong reason.
**Fix:** default to the current month and let the two race files that pin a fixed `NOW`
keep passing theirs explicitly:

```python
    monthly_period: str | None = None,
    ...
    # The caller's month where one is named; otherwise this month, never a literal that ages.
    monthly_period = monthly_period or datetime.now(UTC).strftime("%Y-%m")
```

### IN-83: The inventory query selects `is_unique` and no case reads it

**File:** `tests/schema/test_inventory.py:22`
**Issue:** `INDEXES` selects `ix.indisunique AS is_unique`, and every consumer reads only
`index_name`, `schema` and `predicate`. The comment at :154 asserts
`ix_subscriptions_provider_external_id` is *"Unique with no predicate"*, but only the
predicate half is checked — dropping `UNIQUE` from that index would pass this file.
**Fix:** either drop the column from the query, or add
`EXPECTED_UNIQUE_INDEXES` and a case asserting
`{r["index_name"] for r in rows if r["is_unique"]} == EXPECTED_UNIQUE_INDEXES`.

### IN-84: One of the four sensitive values is never put on the wire

**File:** `tests/e2e/test_app_store_webhook.py:85`, `:532`
**Issue:** `SENSITIVE_VALUES = (ENVELOPE, TOKEN, OTHER_TOKEN, STORE_TOKEN)`, but
`_drive_every_recording_arm` (:499-511) delivers `STORE_TOKEN` and `OTHER_TOKEN` only —
`TOKEN` reaches no request in this class, so `assert TOKEN not in rendered` is vacuous.
**Fix:** drop `TOKEN` from `SENSITIVE_VALUES`, or make the walk's first attributed
delivery carry `TOKEN` so the assertion has something to prove.

### IN-85: Comment counts ten connections where eight are held

**File:** `tests/e2e/test_challenge_store.py:79`
**Issue:** `# ... the gather holds ten connections against max_overflow=0`. `CONTENDERS = 8`
(:24), so the gather holds eight; ten is the pool size (`CONTENDERS + 2`, :76).
**Fix:** `# ... the gather holds one connection per contender against max_overflow=0`.

---

_Reviewed: 2026-09-09T18:05:00Z_
_Reviewer: Claude (gsd-code-reviewer), part E of 7_
_Depth: standard_

### IN-110: a test named for added rows asserts flush counts instead

**File:** `tests/unit/test_conflict_classification.py:181-184`

**Issue:** `test_no_further_row_is_added_after_the_failure` asserts `session.flushes == 2`. It never
reads `session.added`, which `_ConflictingSession` does record. The identically named test in
`tests/unit/test_create_user_rollback.py:114-118` does the honest thing
(`assert session.added == session.added_at_failure`). A row added after the conflict without a
further flush would pass here.

**Fix:** Either rename to `test_no_further_flush_is_issued_after_the_failure`, or give
`_ConflictingSession` the `added_at_failure` snapshot `_FlushFailingSession` already has and assert
on it as the sibling does.

### IN-111: an unreachable guard in the challenge suite's session stub

**File:** `tests/unit/test_challenge_endpoint.py:67-68`

**Issue:** `_RecordingSession.rollback` raises `AssertionError("no path in this module may roll
back")`, but the fixture overrides `get_db` with `lambda: session` (line 88) — a plain callable with
no exit path — so nothing in the module can ever call it. The guard reads as an enforced invariant
and enforces nothing.

**Fix:** Either drop the method, or switch the fixture to the real `get_db` via
`app.state.session_factory` (see WR-110) so the guard becomes live.

### IN-112: inert setup on the refused-write cases

**File:** `tests/unit/test_claim_precedence.py:499-513`, `tests/unit/test_claim_precedence_registered.py:429-445`

**Issue:** Both set `grants.won_by = [...]` under the comment *"A readable grant after the rollback,
so only the outcome itself can produce the 403 below."* `AuthService._settle`
(`services/auth.py:304-317`) short-circuits: `if outcome is ActivationOutcome.lost_race and await
self.grants_db.read_effective_grants(...)`. With `outcome = refused` the left operand is false, so
the re-read never runs and `won_by` is never read. The setup and its comment describe a condition
the code cannot reach.

**Fix:** Drop `grants.won_by` from both cases, or keep it and change the comment to say the read is
short-circuited — the point stands either way, but the current comment claims a mechanism that is
not exercised.

### IN-113: the P-03 shape the `require` case exists for is never sent

**File:** `tests/unit/test_google_play_notifications.py:706-712, 809-812`

**Issue:** `test_email_is_compared_after_decode_rather_than_required` justifies itself with
*"In `require`, a Google token shape without `email` would fail like a forgery (P-03)"*, and asserts
only the structural fact `"email" not in _require_list()`. `_push_token` always emits an `email`
claim, and `TOKEN_REFUSALS` varies its *value* and `email_verified` but never omits it, so no case
sends the shape P-03 names. (Production is correct — `jwt_verifier.py:238` compares
`payload.get(claim) != expected`, so an absent claim yields `required_claim_mismatch` — but that is
unasserted.)

**Fix:** Add the omission to `TOKEN_REFUSALS` by letting `_push_token` drop the claim:

```python
def _push_token(*, ..., email: str | None = PUSH_SERVICE_ACCOUNT, ...) -> str:
    return make_token(PUSH_SUBJECT, aud=aud, iss=iss, email_verified=email_verified,
                      extra_claims={} if email is None else {"email": email},
                      private_key=private_key, headers={"kid": PUSH_KID})
```

```python
TOKEN_REFUSALS = [
    ...,
    # P-03: an absent claim is a claim mismatch, not a signature failure.
    ({"email": None}, "required_claim_mismatch"),
]
TOKEN_REFUSAL_IDS = [..., "no-email"]
```

---

_Reviewed: 2026-09-09_
_Reviewer: Claude (gsd-code-reviewer), part F of 7_
_Depth: standard_
_Baseline: 1743 unit tests passing; ruff clean on all 25 assigned files_

### IN-140: Two of the three bounded-field cases take a `realistic` parameter they never read

**File:** `tests/unit/test_models.py:349-369`

**Issue:** `test_an_oversized_value_is_refused` and `test_an_empty_value_is_still_refused` both
declare `realistic` in their signature and never use it; only
`test_the_bound_stands_well_above_the_real_value` does. The same shape repeats for
`_BOUNDED_WEBHOOK_FIELDS`, whose `other` entry is always `{}` (line 317-319), so the `**other`
splat is dead in all three webhook cases.

**Fix:** Drop the unused names with `_realistic` / `_other`, or split the tuple so each case takes
only what it reads.

### IN-141: Two cases pass a throwaway recording list they never inspect

**File:** `tests/unit/test_spent_free_grant_refusal.py:88, 94, 106`

**Issue:** `_with_registered_row(monkeypatch, present=False, asked=[])` builds a fresh list purely to
satisfy a required parameter. Only `test_the_question_asked_is_the_registered_source` (line 114)
actually reads it. A literal `[]` default in a helper signature is also a mutable-default hazard if
the helper is ever refactored to accept one.

**Fix:** Give `asked` a default of `None` and build the list inside the helper, returning it:

```python
def _with_registered_row(monkeypatch, *, present: bool) -> list:
    asked: list = []
    ...
    return asked
```

### IN-142: The Pub/Sub bound-boundary case silently requires `PUBSUB_DATA_LIMIT % 4 == 0`

**File:** `tests/unit/test_models.py:431-442`

**Issue:** `decoded_limit = PUBSUB_DATA_LIMIT // 4 * 3` produces an encoded payload of exactly
`PUBSUB_DATA_LIMIT` characters only when the bound is a multiple of four. It is today (16384,
`src/nativespeaker/api/schemas/webhooks.py:10`), but if the bound is retuned to, say, 16000 the case
fails on `assert len(payload) == PUBSUB_DATA_LIMIT` — an opaque arithmetic failure that reads as a
decoder regression rather than as a retuned constant.

**Fix:** Name the precondition so the failure explains itself:

```python
    assert PUBSUB_DATA_LIMIT % 4 == 0, "the bound must be a whole number of base64 quartets"
```

### IN-143: `_take_every_permit` mutates a private semaphore counter and can over-credit it

**File:** `tests/unit/test_quota_seam.py:105-110`

**Issue:**

```python
def _take_every_permit(policy: ResiliencePolicy) -> asyncio.Semaphore:
    semaphore = policy._gate._semaphore
    while not semaphore.locked():
        semaphore._value -= 1
    return semaphore
```

If the semaphore is already at zero the loop body never runs, and the caller's later
`semaphore.release()` (lines 493, 574) raises the count *above* its configured ceiling for the rest
of the test — silently granting an extra provider permit. Unreachable today (each case builds a
fresh `RecordingLLM` with `pool_size=4`), but the helper gives no signal if that changes, and
`asyncio.Semaphore._value` is a private CPython attribute.

**Fix:** Take the permits through the public API and return a releaser that gives back exactly what
was taken:

```python
def _take_every_permit(policy: ResiliencePolicy) -> asyncio.Semaphore:
    semaphore = policy._gate._semaphore
    taken = 0
    while semaphore._value > 0:
        semaphore._value -= 1
        taken += 1
    assert taken, "the permit budget was already exhausted, so this case measures nothing"
    return semaphore
```

### IN-144: The logging-leak backstop asserts session-global state and depends on collection order

**File:** `tests/unit/test_logging.py:320-327`

**Issue:** `test_no_quieted_library_level_outlives_the_test_that_set_it` reads the *process-wide*
level of all nine quieted loggers and asserts every one is `NOTSET`. It passes only because it is
the last function in the file and no earlier-sorted module calls `setup_logging` — I checked:
`grep -rn "setup_logging" tests/` outside this file finds only
`tests/unit/test_config.py:283-285`, which reads the signature and never calls it. Should any module
sorting before `test_logging.py` ever call `setup_logging` without the autouse fixture, the failure
would be reported against this file and be misread as a leak in `test_logging.py` itself.

**Fix:** Make the message name the real cause, so a future failure points at the caller rather than
at this file:

```python
    assert pinned == {}, (f"a logger level outlived its test: {pinned}. Some module collected "
                          f"before this one called setup_logging without _reset_logging.")
```

---

_Reviewed: 2026-09-09T17:45:00Z_
_Reviewer: Claude (gsd-code-reviewer), part G_
_Depth: standard_

---

_Reviewed: 2026-09-10T00:52:47Z_
_Reviewer: Claude (gsd-code-reviewer x7, merged)_
_Depth: standard_
