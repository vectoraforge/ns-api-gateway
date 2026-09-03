---
phase: 41-post-auth-claim-anonymous-grant
reviewed: 2026-09-03T06:47:07Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - .env.example
  - .gitignore
  - AGENTS.md
  - config/config.yaml
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/auth/devicecheck.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/grants.py
  - tests/e2e/conftest.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_grant_locks.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_config.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_sync_clock_capture.py
  - tests/unit/test_upgrade_precedence.py
findings:
  critical: 2
  warning: 10
  info: 7
  total: 19
status: issues_found
---

# Phase 41: Code Review Report

**Reviewed:** 2026-09-03T06:47:07Z
**Depth:** standard
**Files Reviewed:** 38
**Status:** issues_found

## Summary

`POST /auth/claim-anonymous-grant` is well factored and the rejection precedence, the
challenge lifecycle and the "no vendor call under a lock" property all hold as written.
Two defects nevertheless block: the race-loser arm raises `InvalidRequestError` under the
real dependency wiring (it refreshes ORM instances that are detached from the request
session), and the two-token body leaves the DeviceCheck read and the DeviceCheck write
unbound to the same device, which is the one thing the device gate exists to enforce.

Both are invisible to the suite. `tests/schema/test_claim_race.py` resolves the identity
on the *same* session the service uses, and `tests/unit/test_claim_precedence.py` stubs
`refresh` to a no-op — neither reproduces `app/dependencies.py::get_identity`, which
returns from inside its own `async with` block. 950 unit tests pass, `ruff` is clean,
and `ty` reports 22 diagnostics of which 9 are new in this phase.

The three items the phase's executors flagged were checked directly:
- **No logger in `devicecheck.py`:** the property holds. There is no logger, no token
  reaches `log_fields()`, and `logs.py` configures `structlog.dev.plain_traceback`, which
  renders no frame locals — so the unhandled-exception path cannot leak a token either.
- **Expire-after-rollback on other paths:** the other rollback (`services/auth.py:134`)
  is safe, but for the opposite reason to the one assumed — the caller's rows were never
  in that session at all. That is exactly what makes CR-01 fire.
- **Single writer / fixed lock order:** `crud/grants.py` is the single writer, but the
  "never a third tier" claim in its docstring is false on the success path (WR-05).

## Critical Issues

### CR-01: The race-loser arm raises `InvalidRequestError` and answers 500, not the D-13 200

**File:** `src/nativespeaker/api/services/auth.py:180-185`
**Issue:** When `activate_anonymous_device_grant` returns `False`, the loser rolls back and
then refreshes the caller's rows:

```python
if not activated:
    await self.session.rollback()
    # The rollback expired both rows the caller was handed; reload them here, where an await still can.
    await self.session.refresh(identity.user)
    await self.session.refresh(identity.identity)
```

The premise is wrong. `identity.user` and `identity.identity` were loaded by
`app/dependencies.py::get_identity`, which returns from **inside** its own
`async with request.app.state.session_factory() as session:` block (dependencies.py:51-54).
Closing that session expunges both instances, so they are **detached** — not merely
expired, and not members of `self.session` (the separate `get_db` session that
`get_auth_service` injects). `Session.refresh()` on a detached instance raises.

Reproduced against the installed SQLAlchemy 2.0.46 using the exact dependency shape:

```
after get_identity -> detached: True
BOOM: InvalidRequestError -> Instance '<U at 0x...>' is not persistent within this Session
```

`InvalidRequestError` is not an `AppError`, so `_complete`'s `except AppError` at
services/auth.py:132 does not catch it. It escapes to `generic_error_handler` and the
client receives **500 `internal_error`** on the one path D-13 specifies must answer
200 with the winner's entitlement. The challenge is left `claimed_at IS NOT NULL,
consumed_at IS NULL`, which `ChallengesDB.claim` can never re-match, so the caller must
obtain a fresh handle.

Neither test catches it: `tests/schema/test_claim_race.py:207` resolves the identity on
the *same* session it hands to `AuthService`, and `tests/unit/test_claim_precedence.py:107`
defines `async def refresh(self, obj): return None`.

**Fix:** the rows are detached, so nothing expired them and nothing needs reloading —
delete both refreshes. If a fresh read is genuinely wanted, it must be a re-query, not a
refresh of a foreign instance:

```python
        if not activated:
            # The unique indexes are the arbiter, and the loser answers exactly as the repeat does.
            await self.session.rollback()
```

Then add a regression case that wires `identity` from a *closed* session, as
`get_identity` does, rather than from the service's own session.

### CR-02: The DeviceCheck read and write are not bound to the same device

**File:** `src/nativespeaker/api/schemas/auth.py:33-36`, `src/nativespeaker/api/services/auth.py:168-173`
**Issue:** The body accepts two independent, client-supplied device tokens, and the claim
reads bit0 from one and writes bit0 to the other:

```python
state = await read_bits_with_retry(self.devicecheck, query_token)
if state.bit0:
    raise DeviceGrantExhausted(...)
await write_bits_with_retry(self.devicecheck, update_token, bit0=True, bit1=state.bit1)
```

Nothing ties `query_token` to `update_token`. Apple's two-bit ledger is per device, and
the server has no way to tell that two opaque tokens name the same device. So the
one-grant-per-device invariant is defeated with two devices: always send device A's token
as `query_token` (A is never written, so its bit0 stays `False` forever) and device B's
token as `update_token` (writing an already-set bit is a 200). Every account then passes
the gate. The account-side lifetime marker still holds one grant per *account*, but the
device gate — the only anti-abuse control on the anonymous free tier — stops binding.

This is not covered by the phase's threat table (41-RESEARCH.md lists "Replaying a device
token to claim twice" but not two tokens from two devices), and D-02's "each used once,
the query token never reused for the update" is stated as a hygiene rule with no analysis
of what the separation costs.

Judged against AGENTS.md: this is not over-engineering for a high-value target, it is the
gate doing what it was built to do. The fix is one field, not a new subsystem.

**Fix:** take one token and use it for both calls — Apple accepts the same device token
for `query_two_bits` and `update_two_bits` within its validity window, and one field is
what makes the read and the write provably the same device:

```python
class AnonymousGrantClaimRequest(BaseModel):
    """The claim body: the handle and the device token."""
    challenge_id: str = Field(..., min_length=1, max_length=64)
    device_token: str = Field(..., min_length=1, max_length=4096)
```

```python
state = await read_bits_with_retry(self.devicecheck, device_token)
if state.bit0:
    raise DeviceGrantExhausted(stage="devicecheck_read", cause="already_set")
await write_bits_with_retry(self.devicecheck, device_token, bit0=True, bit1=state.bit1)
```

If two tokens must be kept, the update token has to be re-queried for `bit0` before the
write, and a set bit0 there must raise `DeviceGrantExhausted` — otherwise the binding is
still absent.

## Warnings

### WR-01: Every `IntegrityError` is read as a race loss, so a schema or seed fault answers 200 with no entitlement

**File:** `src/nativespeaker/api/crud/grants.py:128-133`
**Issue:**

```python
try:
    await self.session.flush()
except IntegrityError:
    # The unique indexes are the arbiter; the constraint is never named and the message never parsed.
    return False
```

The flush emits an `INSERT` into `core.access_grants` (FK to `core.users` and to
`core.access_tiers`), an `INSERT` into `core.access_grants_anti_abuse` (exclusive-or
CHECK), an `INSERT` into `core.user_monthly_usage`, and an `UPDATE` of
`core.external_identities`. Any of their FK or CHECK violations is an `IntegrityError`,
and all of them are classified as "the unique index arbitrated". The caller then answers
as a repeat: `200` carrying whatever the post-commit read finds, which for a genuine
integrity fault is `entitlement.type = "none"` — after Apple's bit0 has already been
burned for that device.

41-RESEARCH.md A6 records that the `"anonymous"` tier id was **assumed** and the seeding
migration was never opened. If that literal is wrong, every claim silently burns a device
slot and returns a 200 with no entitlement, in production, with no error log at all.

**Fix:** keep the unique indexes as the arbiter but narrow the arm to them, and let
anything else fail loudly:

```python
        try:
            await self.session.flush()
        except IntegrityError as conflict:
            if not isinstance(getattr(conflict, "orig", None), UniqueViolationError):
                raise
            return False
        return True
```

(`from asyncpg.exceptions import UniqueViolationError` — the driver's exception type, not
the constraint name and not the message text, so the "never parsed" rule still holds.)

### WR-02: A never-set device answered with a non-2xx status is misread as `ProofRejected`

**File:** `src/nativespeaker/api/auth/devicecheck.py:98-110`
**Issue:** `_parse_bit_state` runs `_reject_or_retry` **before** it inspects the plain-text
body, so the status classification wins:

```python
_reject_or_retry(response, stage=stage)      # 400 -> ProofRejected, other non-2xx -> retryable
body = response.text.strip()
if body in _NEVER_SET_BODIES:
    return BitState(bit0=False, bit1=False)
```

The wire shapes are `[ASSUMED]` (the module's own test file says so, and 41-RESEARCH.md A5
records the risk). If Apple answers a never-set device with `400 Failed to find bit state`
rather than `200`, every first-ever claim gets **403 `proof_rejected`** and the feature is
dead. A5 claims the failure mode would be "a 503, an outage not a breach"; the code as
written produces a definitive 403 instead, which is neither retried nor obviously an
outage in the logs.

**Fix:** the never-set body is a state regardless of the status Apple attached to it, so
read it first:

```python
def _parse_bit_state(response: httpx.Response, *, stage: str) -> BitState:
    body = response.text.strip()
    if body in _NEVER_SET_BODIES:
        return BitState(bit0=False, bit1=False)
    _reject_or_retry(response, stage=stage)
    ...
```

### WR-03: `bool()` on an untyped JSON value can fabricate `bit1=True` and destroy device state irrecoverably

**File:** `src/nativespeaker/api/auth/devicecheck.py:110`
**Issue:** `return BitState(bit0=bool(payload["bit0"]), bit1=bool(payload["bit1"]))`.
The membership guard on the line above only checks that the keys exist. If Apple ever
answers `{"bit0": "false", "bit1": "false"}`, `bool("false")` is `True` for both. `bit0`
fails closed (`DeviceGrantExhausted`), but `bit1` is carried into the update at
services/auth.py:173 and written back to Apple — and the module's own comment says a
fabricated bit1 "destroys state nothing can recover". `ty` also flags this line.

**Fix:** validate positively rather than coerce, and let anything else take the existing
"unrecognised body" arm:

```python
    bit0, bit1 = payload.get("bit0"), payload.get("bit1")
    if not isinstance(bit0, bool) or not isinstance(bit1, bool):
        raise RetryableDeviceCheckError("unrecognised body")
    return BitState(bit0=bit0, bit1=bit1)
```

### WR-04: The Apple round trips run with the request's database transaction open

**File:** `src/nativespeaker/api/services/auth.py:156-173`
**Issue:** `read_effective_grants` and `has_prior_free_grant` open a transaction on
`self.session` (the `get_db` session), and it stays open across
`read_bits_with_retry` and `write_bits_with_retry` — it is only released when
`activate_anonymous_device_grant` flushes and `_consume_and_commit` commits. Each Apple
call is up to 3 attempts at `DEVICECHECK_HTTP_TIMEOUT_SECONDS = 8`, so one claim can pin
a pooled connection for ~48 s. `config/config.yaml` sets `db.pool_size: 12` with
`max_overflow=0` (lifespan.py:52), and `get_identity` briefly holds a second connection
per request.

This contradicts the principle the phase itself just wrote into AGENTS.md ("no gate hold
spans a database round trip") applied in the other direction: here a database hold spans a
vendor round trip. A DeviceCheck slowdown takes the whole service down, not just the claim
route.

**Fix:** close the read transaction before reaching the vendor. The preflight is read-only,
so a `rollback()` after it costs nothing:

```python
        if held:
            raise OtherActiveGrantHeld
        # The preflight is read-only; the connection is not held across the vendor call.
        await self.session.rollback()

        state = await read_bits_with_retry(self.devicecheck, ...)
```

### WR-05: The "never a third tier" lock invariant is false on the success path, and the schema test does not exercise it

**File:** `src/nativespeaker/api/crud/grants.py:1-2, 106-129`; `tests/schema/test_grant_locks.py:266-283`
**Issue:** The module docstring states *"Global lock order: grant rows ascending by id,
then usage rows, and never a third tier."* On the branch that actually writes, the flush
takes two more locks:

- `INSERT INTO core.access_grants` takes a `FOR KEY SHARE` lock on the referenced
  `core.users` row (Postgres FK enforcement).
- `stored.free_grant_consumed_at = ...` (line 123-125) emits `UPDATE core.external_identities`,
  a row-exclusive lock on the identity row.

`IdentitiesDB.lock_identity_and_user` takes `SELECT ... FOR UPDATE` on
`core.external_identities` **and** `core.users` in the opposite order. A concurrent
`/auth/upgrade-anonymous` and `/auth/claim-anonymous-grant` for one account can therefore
deadlock: the claim holds `KEY SHARE` on the user row and waits for the identity row; the
upgrade holds the identity row and waits for `FOR UPDATE` on the user row. Postgres kills
one with `DeadlockDetected`, which is **not** an `IntegrityError`, so it escapes the arm at
grants.py:130 and surfaces as a 500.

`TestTheActivationAddsNoThirdLockTier` cannot see this: its fixture seeds a held `manual`
grant so `activated is False`, and the test asserts `not [statement ... startswith("INSERT")]`
— it deliberately measures the branch that writes nothing.

**Fix:** either correct the docstring to name all four relations the write path touches and
record why the deadlock is acceptable, or add a lock-tier case whose fixture reaches the
flush (`activated is True`) and asserts the relations the successful statement set touches.

### WR-06: Lifespan teardown has no `try`/`finally`, so a failing dispose leaks the HTTP client and the Firebase apps

**File:** `src/nativespeaker/api/app/lifespan.py:46-77`
**Issue:** `devicecheck_client` is created at line 46 and closed at line 71, with no
protection in between. Two leaks:

1. If anything between line 46 and the `yield` raises (`create_async_engine`,
   `JWTVerifier`, `LLMService`, `init_chat_model` reaching the network), the client is
   never closed.
2. If `await db_engine.dispose()` at line 70 raises, neither `devicecheck_client.aclose()`
   nor the `firebase_admin.delete_app` loop runs — and line 73's own comment says a second
   boot raises without that loop.

**Fix:**

```python
    try:
        yield
    finally:
        try:
            await db_engine.dispose()
        finally:
            await devicecheck_client.aclose()
            for firebase_app in firebase_apps.values():
                firebase_admin.delete_app(firebase_app)
            logger.info("shutdown")
```

### WR-07: The phase adds 9 new `ty` errors to a repo that ships `ty` as a pinned dependency

**File:** `src/nativespeaker/api/services/auth.py:153, 156, 161, 162, 176, 177`; `src/nativespeaker/api/routers/auth.py:117, 120`; `src/nativespeaker/api/auth/devicecheck.py:110`
**Issue:** `ty check src` reports 22 diagnostics; 9 of them are on lines this phase added.
Six are `identity.identity`/`identity.user` on `ExternalIdentity | None` / `User | None` —
`get_linked_identity` only narrows `user`, never `identity`, so the type says both may be
`None` on every access the claim makes. The repo already uses `# ty: ignore[...]` comments
elsewhere, so the tool is treated as a gate, and this phase silently widened the baseline.

**Fix:** give the linked case its own type instead of suppressing site by site — a
`LinkedIdentity` dataclass with non-optional `user: User` and `identity: ExternalIdentity`,
constructed in `get_linked_identity`, removes all eight `unresolved-attribute` errors and
makes `activate_anonymous_device_grant`'s signature check. Fix devicecheck.py:110 via WR-03.

### WR-08: The DeviceCheck retry has no backoff

**File:** `src/nativespeaker/api/auth/devicecheck.py:154-161`
**Issue:** `_retrying` passes `stop` and `retry` but no `wait`, so tenacity uses
`wait_none()`. A transient Apple failure produces three requests back to back with no
delay — the pattern `resilience.py:167` deliberately avoids for the LLM provider, and the
one most likely to be counted against a vendor quota during an incident.

**Fix:**

```python
    return AsyncRetrying(
        stop=stop_after_attempt(DEVICECHECK_ATTEMPTS),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(RetryableDeviceCheckError),
        retry_error_callback=exhausted,
    )
```

### WR-09: No upper bound on the device token fields

**File:** `src/nativespeaker/api/schemas/auth.py:33-36`
**Issue:** All three fields carry `min_length=1` and no `max_length`. An unbounded string
is accepted and forwarded verbatim in the JSON body sent to `api.devicecheck.apple.com`.
A real DeviceCheck token is a few hundred bytes; there is no reason to relay a multi-megabyte
one to a third party at the service's own expense. Envoy's body limit is a different layer
and does not make the field bound.

**Fix:** `Field(..., min_length=1, max_length=4096)` on both tokens (and a `max_length` on
`challenge_id`, which `ChallengesDB.new_challenge_id` fixes at 22 characters).

### WR-10: `AuthService.devicecheck` defaults to `None`, so an unwired seam fails as an AttributeError

**File:** `src/nativespeaker/api/services/auth.py:56`
**Issue:** `devicecheck=None` is the only collaborator with a default; `adapter`,
`challenge_store` and `evaluated_at` are all required. A construction site that forgets it
gets an `AttributeError: 'NoneType' object has no attribute 'read_bits'` at
services/auth.py:168 — after the challenge has already been claimed and committed
(services/auth.py:125), so the handle is burned by a wiring bug.

**Fix:** make it required, as the Firebase adapter is:

```python
    def __init__(self, db, challenge_store, adapter, devicecheck, evaluated_at) -> None:
```

## Info

### IN-01: `ainvoke`'s `admitted` parameter is never read, and `Admitted`'s docstring overstates what it proves

**File:** `src/nativespeaker/api/resilience.py:105-107, 140-142`
**Issue:** `Admitted` is documented as *"Proof that the breaker was closed and a slot is
held. Only `ResiliencePolicy.admission` mints one."* — but it is a public, frozen,
zero-field dataclass any caller can construct, and `ainvoke` never reads the parameter.
The type is a convention, not a proof.
**Fix:** either reword the docstring to say it is a convention, or give it a private field
`admission()` sets and `ainvoke` asserts.

### IN-02: `_is_transient_error` checks the same status set twice

**File:** `src/nativespeaker/api/resilience.py:30-36`
**Issue:** The `isinstance(exc, APIStatusError)` branch and the unconditional fallback below
it run identical logic over the identical set; the first is unreachable in effect.
**Fix:** delete lines 30-33 and keep the general `_extract_status_code` check.

### IN-03: `read_private_key` raises on an unreadable file despite promising `None`

**File:** `src/nativespeaker/api/auth/devicecheck.py:54-59`
**Issue:** The docstring says *"or return `None` when there is no usable file"*, but a file
that exists and is not readable (a mode-600 key owned by another user — precisely the
deployment `.env.example:74` prescribes) passes `is_file()` and then raises `PermissionError`
out of the lifespan, crashing boot rather than taking the documented fail-closed path.
**Fix:** `except OSError: return None` around the read.

### IN-04: `AccessGrantAntiAbuse.grant_id` declares no `foreign_key`, unlike its sibling

**File:** `src/nativespeaker/api/tables/grants.py:78`
**Issue:** `UserMonthlyUsage.grant_id` (line 95) declares `foreign_key="core.access_grants.id"`;
`AccessGrantAntiAbuse.grant_id` declares only `primary_key=True`. SQLAlchemy therefore has
no dependency edge to order that insert after the grant insert, and correctness rests
entirely on the database FK being `DEFERRABLE`. The comment at grants.py:127 knows this,
but the asymmetry between the two child tables is unexplained.
**Fix:** declare the foreign key on both, or state in one line why this one cannot.

### IN-05: `config.yaml`'s HMAC-key comment block now heads two integer limits

**File:** `config/config.yaml:22-37`
**Issue:** A 13-line block describes *"HMAC key material… The keys below are therefore
committed… The Secret Manager follow-up must REMOVE these entries"* and is immediately
followed by `chats_limit: 50` and `messages_limit: 50`. There is no key material in the
file. A reader following the instruction removes two live limits; a reader auditing for
committed secrets goes looking for keys that do not exist.
**Fix:** delete the block, or move it to the pending secret-manager TODO it references.

### IN-06: Two different ways to capture the request instant

**File:** `src/nativespeaker/api/app/dependencies.py:87, 107-109`
**Issue:** `get_auth_service` and `get_sync_service` share one instant through
`Depends(get_evaluated_at)` — which is what makes the claim route's write and its
post-commit read agree. `get_chat_service` calls `datetime.now(UTC)` inline instead, so a
chat request's instant is not shareable with any other dependency.
**Fix:** route `get_chat_service` through `Depends(get_evaluated_at)` too.

### IN-07: A silently swallowed slot leak in the execution gate

**File:** `src/nativespeaker/api/resilience.py:93-96`
**Issue:** `except asyncio.QueueFull: pass` in `inflight_slot`'s `finally`. The invariant
(one token out, one token back) makes it unreachable, but if it ever fired the gate would
lose a slot permanently with no signal.
**Fix:** log at ERROR instead of `pass`, so a broken invariant is observable.

---

_Reviewed: 2026-09-03T06:47:07Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
