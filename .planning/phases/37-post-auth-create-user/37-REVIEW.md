---
phase: 37-post-auth-create-user
reviewed: 2026-08-24T01:03:39Z
depth: standard
files_reviewed: 46
files_reviewed_list:
  - docker-compose.yml
  - .env.example
  - migrations/20260818_01_initial-release.sql
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/challenges.py
  - src/nativespeaker/api/auth/classifier.py
  - src/nativespeaker/api/auth/creation.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/auth/__init__.py
  - src/nativespeaker/api/auth/registry.py
  - src/nativespeaker/api/auth/retry.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/models/auth.py
  - src/nativespeaker/api/models/__init__.py
  - src/nativespeaker/api/models/purchase_tokens.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/__init__.py
  - tests/e2e/conftest.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_create_user.py
  - tests/schema/test_constraints.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_store_purchase_tokens.py
  - tests/unit/conftest.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_challenge_ids.py
  - tests/unit/test_config.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_create_user_modes.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_models.py
  - tests/unit/test_provider_classifier.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_route_registry.py
findings:
  critical: 2
  warning: 4
  info: 0
  total: 6
status: issues_found
---

# Phase 37: Code Review Report

**Reviewed:** 2026-08-24T01:03:39Z
**Depth:** standard
**Files Reviewed:** 46
**Status:** issues_found

## Summary

The transaction shape in `auth/creation.py` holds up under scrutiny. The savepoint wraps all three
business inserts, `savepoint.rollback()` genuinely precedes `classify_insert_conflict`, the
classifier reads `constraint_name` off the driver chain rather than message text, the re-resolution
is inside the transaction and is not strengthened into an arbiter, and the constraint literals
match the names PostgreSQL will generate for the migration's `UNIQUE (user_id)` /
`UNIQUE (issuer, subject)` table constraints. Rejection precedence in `routers/auth.py` matches the
numbered spec order, all five challenge rejections return a byte-identical `challenge_required`
body with the specific result confined to the audit row, and no `details` object built anywhere in
the phase carries the public handle at any depth. `email_to_persist` is evaluated at exactly one
site and passed through unconditionally. The two tenacity policies do match their seams'
control flow for the outcomes their seams actually produce.

Two defects break that record, both on paths the tests do not reach because they are all served by
fakes or by the one arm that happens to be safe:

1. `FirebaseAdminLookup._read` claims "everything that can raise happens here" but catches only
   three exception types. `google.auth.exceptions.GoogleAuthError` — the family a credential
   refresh failure raises, and the one this deployment is most exposed to because ADC is its only
   credential route — escapes the adapter, escapes the result-based retry policy, and lands as an
   unhandled 500 with the challenge unconsumed and no audit row written.
2. `_prepare` reads an ORM attribute after `await session.rollback()`, the exact hazard
   `_challenge_rejected` documents and guards against 260 lines later. Reproduced empirically.

Four warnings follow, three of them about the audit obligation and the boot/shutdown symmetry the
phase already tried once to fix.

## Structural Findings (fallow)

None supplied — no structural pre-pass accompanied this review. `ruff check src/ tests/` passes
clean; `ty check src/` reports three errors, covered under WR-02.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: A Firebase credential-refresh failure escapes the adapter, the retry policy, and the router — 500 instead of 503, with no consumption and no audit row

**File:** `src/nativespeaker/api/auth/firebase.py:150-179` (the `_read` `try` block)
**Severity:** BLOCKER

**Issue:**

`_read` catches exactly `auth.UserNotFoundError`, `ValueError`, and `exceptions.FirebaseError`.
`firebase-admin` only converts transport problems into `FirebaseError` for the narrow case it
explicitly wraps:

```python
# firebase_admin/_user_mgt.py::UserManager._make_request
try:
    return self.http_client.body_and_response(method, url, **kwargs)
except requests.exceptions.RequestException as error:
    raise _auth_utils.handle_auth_backend_error(error)
```

Credential acquisition happens *before* that call, in
`google.auth.transport.requests.AuthorizedSession.request`, which invokes
`self.credentials.before_request(...)` with no wrapping at all. Failures there raise
`google.auth.exceptions.RefreshError`, `TransportError`, or `DefaultCredentialsError` — verified in
this environment as `('RefreshError', 'GoogleAuthError', 'Exception', ...)`. None of them is a
`requests.RequestException`, none is a `ValueError`, and none is a `FirebaseError`. They pass
straight through `_read`.

The failure then propagates through the whole chain untouched:

* `run_in_threadpool` re-raises it out of `get_user_provider_data`;
* `lookup_with_retry`'s predicate is `retry_if_result`, and tenacity's `retry_if_result.__call__`
  returns `False` for a failed outcome — so `BaseRetrying.iter` calls `fut.result()`, which
  re-raises. **No retry is spent**, and `retry_error_callback` never fires because exhaustion never
  happens;
* `_complete` has no `try` around `lookup_with_retry`, so the exception leaves the handler.

Concrete failure scenario — and it is the deployment's expected steady state, not an exotic one.
`.env.example` and `config.py` both state that this project's org policy sets
`iam.disableServiceAccountKeyCreation`, so **ADC is the only usable credential source**. When the
ADC session expires, when the workload identity token endpoint is briefly unreachable, or when the
service account loses the `firebaseauth.users.get` permission, `google.auth` raises `RefreshError`
("invalid_grant", "Reauthentication is needed", …). The result:

* the client receives **500 `internal_error`** instead of the **503
  `verification_temporarily_unavailable`** that `adapters.py` and `retry.py` both go to some length
  to pin. Those two say opposite things to a client: "something is broken, this is permanent-looking"
  versus "back off and retry the whole operation";
* the challenge was already claimed **and committed** before the provider call, but
  `_consuming_rejection` is never reached — so **the claim is never consumed** and §02 step 13's
  "every rejection at or after the provider read consumes" is violated;
* **no `audit.auth_events` row is written at all** for an attempt on the audited path (§4.1 requires
  exactly one row per on-path attempt for its terminal outcome);
* the transient cause that the 3-attempt budget exists for is the one cause that gets zero retries.

`tests/unit/test_firebase_adapter.py` exercises only `UserNotFoundError`, `ValueError`, and
`FirebaseError` (`TestFailureMapping`), so the gap is invisible to the suite. Note the module
already imports `google.auth.exceptions` for `_application_default_credential` — the import is
present, the catch is not.

**Fix:**

```python
# src/nativespeaker/api/auth/firebase.py, inside _read
        except auth.UserNotFoundError:
            logger.info("firebase_get_user_not_found")
            return ProviderDataResult(ProviderDataOutcome.user_not_found)
        except ValueError as error:
            logger.warning("firebase_provider_data_malformed", detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        except exceptions.FirebaseError as error:
            logger.warning("firebase_get_user_failed", code=error.code, detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        except google.auth.exceptions.GoogleAuthError as error:
            # Credential acquisition, not the Auth backend call: RefreshError, TransportError and
            # a late DefaultCredentialsError are raised by `AuthorizedSession.request` BEFORE
            # firebase-admin's own `requests.RequestException` wrapper can see them, so they are
            # not FirebaseError and would otherwise escape this adapter entirely. Transient by
            # nature -> retryable_failure -> verification_temporarily_unavailable.
            logger.warning("firebase_credential_unusable", detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
```

Then make the contract structural rather than enumerated, since the seam's whole value is "never
raises". Either add a final `except Exception` arm returning `retryable_failure` (logging at
`exception` level), or — better, because it also covers a future adapter — wrap the call in
`retry.py` so no substituted adapter can break the router either:

```python
# src/nativespeaker/api/auth/retry.py
async def _call(adapter, issuer: str, subject: str) -> ProviderDataResult:
    """The seam contract, enforced rather than assumed: an adapter that raises is a
    retryable_failure, never an exception the router has no arm for."""
    try:
        return await adapter.get_user_provider_data(issuer, subject)
    except Exception:
        logger.exception("provider_lookup_raised")
        return ProviderDataResult(ProviderDataOutcome.retryable_failure)
```
and call `retrying(_call, adapter, issuer, subject)`.

Add a regression case to `tests/unit/test_firebase_adapter.py::TestFailureMapping` using
`StubUserRecord(raises=google.auth.exceptions.RefreshError("invalid_grant"))`, asserting
`ProviderDataOutcome.retryable_failure` and that the provider text appears in no field of the
result (the existing `TestNoProviderTextLeaks` parametrisation is the right home).

---

### CR-02: `_prepare` reads an expired ORM attribute after `session.rollback()` — the already-linked race arm raises `MissingGreenlet` and loses its audit row

**File:** `src/nativespeaker/api/routers/auth.py:189-210`
**Severity:** BLOCKER

**Issue:**

```python
    linked = await _already_linked(session, identity=identity)
    if linked is not None:
        await session.rollback()
        await audit_writer.write_standalone(
            session_factory,
            ...
            actor_provider=linked.provider,   # <-- expired instance, lazy load off the event loop
```

`Session.rollback()` calls `SessionTransaction._restore_snapshot(dirty_only=False)` for an outer
transaction, which expires **every** state in the identity map. `linked.provider` then triggers an
attribute load outside `greenlet_spawn`. Reproduced in this environment against the same
`async_sessionmaker(..., expire_on_commit=False)` shape:

```
RAISED: MissingGreenlet greenlet_spawn has not been called; can't call await_only() here.
```

This is precisely the hazard `_challenge_rejected` names and guards at line 486:

```python
    # Read the correlation id BEFORE the rollback: SQLAlchemy expires every instance on rollback,
    # and touching an expired attribute afterwards emits a lazy load off the event loop.
    challenge_row_id = None if challenge is None else challenge.id
```

`_prepare` has the same shape and no such guard.

Reachability. `_already_linked` has two arms:

* the `LinkedIdentity` arm returns `identity.identity`, which the barrier loaded in its own short
  session (`barrier.py:133`) and which is **detached** by the time the handler runs — its loaded
  attributes survive, so this arm is safe. This is the only arm `tests/e2e/test_create_user.py::TestPrepareRejectsAnAlreadyLinkedCaller` exercises, which is why the suite is green;
* the **pre-auth** arm issues `resolve_existing_identity(session, ...)` inside the handler's own
  session, so the returned `ExternalIdentity` **is** in that session's identity map and **is**
  expired by the rollback.

The pre-auth arm is exactly the race the function exists to catch: `resolve_identity` returns
`PreAuthIdentity` only when no row existed at barrier time, so reaching this branch means a row for
the same `(issuer, subject)` was committed between the barrier's query and the handler's. It is
narrow, but it is the one condition this code was written for, and when it fires the caller gets a
**500 instead of the 409 `identity_already_linked`**, and the audited attempt writes **no
`audit.auth_events` row at all** because the exception precedes `write_standalone`. The unit tests
override `get_db` with a fake whose `rollback()` is a counter (`test_create_user_precedence.py:169`),
so nothing in the suite can see this.

**Fix:** read the value before the rollback, mirroring `_challenge_rejected`.

```python
    linked = await _already_linked(session, identity=identity)
    if linked is not None:
        # Read the stored provider column BEFORE the rollback, for the same reason
        # `_challenge_rejected` reads the challenge row id first: rollback expires every instance
        # in this session's identity map, and the pre-auth arm above loaded this row *in* it.
        actor_provider = linked.provider
        await session.rollback()
        await audit_writer.write_standalone(
            session_factory,
            ...
            actor_provider=actor_provider,
            ...)
```

Add a unit case that drives `_prepare` with a `PreAuthIdentity` against a real session where the row
appears after the context is built — or, cheaper, an e2e case that seeds the identity row *inside*
the request window is impractical, so assert the ordering directly: have the fake session's
`rollback()` mark a flag and assert `write_standalone` receives a concrete `IdentityProvider`
rather than raising.

## Warnings

### WR-01: The lifespan's Firebase app cleanup is not in a `try`/`finally`, so the leak commit 58399df fixed still happens on any error path

**File:** `src/nativespeaker/api/app/lifespan.py:24-124`
**Severity:** WARNING

**Issue:** `build_admin_apps` registers a **process-global** named app, and the compensating
`firebase_admin.delete_app(...)` loop sits after the bare `yield` with nothing protecting it. Three
reachable paths skip it:

* any statement between `build_admin_apps` (line ~85) and `yield` raising — `create_async_engine`
  with a bad URL, `JWTVerifier` construction, `LLMService` construction;
* the application's serving window raising through the lifespan context — an e2e module whose
  fixture setup fails inside `async with app.router.lifespan_context(app)`;
* the ASGI server cancelling the lifespan task.

In each case `db_engine.dispose()` is skipped too. The consequence is the exact symptom the commit
message for 58399df describes — "every e2e module after the first errored in fixture setup", because
`initialize_app` raises `ValueError: ... already exists` for a repeated name. The fix made the happy
path symmetric; it did not make the guarantee unconditional, and the comment in the file states the
rule as "whoever creates a globally-registered handle destroys it", which `try`/`finally` is the
only way to actually mean.

**Fix:**

```python
    firebase_apps = build_admin_apps(config)
    app.state.firebase_adapter = FirebaseAdminLookup(firebase_apps)
    db_engine = create_async_engine(...)
    try:
        ...  # remaining setup
        yield
    finally:
        await db_engine.dispose()
        for firebase_app in firebase_apps.values():
            firebase_admin.delete_app(firebase_app)
        logger.info("shutdown")
```

If restructuring the whole body is undesirable, at minimum move `build_admin_apps` to the last
setup step and wrap from there down.

---

### WR-02: `_LOOKUP_REJECTIONS` is typed `dict[str, object]`, so `ty` fails on the exact mapping the module calls a client-contract invariant

**File:** `src/nativespeaker/api/routers/auth.py:518-532` and the call at `:431`
**Severity:** WARNING

**Issue:** `uv run ty check src/` reports three `invalid-argument-type` errors, all at line 431:

```
Expected `AuthEventResult`, found `object`
Expected `ErrorClass`,      found `object`
Expected `str | None`,      found `object`
```

The phase ships a failing type check. Worse, the erasure is on the one table whose comment says
"collapsing any pair is a client-contract bug": `**dict[str, object]` means a wrong value type, a
misspelled key, or a missing `error_class` is a runtime `TypeError`/`KeyError` inside a rejection
path rather than a static error. The third diagnostic (`cause`) shows the checker cannot even prove
the spread supplies only the intended two keys.

**Fix:** make the row a typed record, which restores checking and removes the spread:

```python
@dataclass(frozen=True, slots=True)
class _LookupRejection:
    result: AuthEventResult
    error_class: ErrorClass


_LOOKUP_REJECTIONS: dict[ProviderDataOutcome, _LookupRejection] = {
    ProviderDataOutcome.user_not_found:
        _LookupRejection(AuthEventResult.firebase_user_unresolved, AUTH_REQUIRED),
    ProviderDataOutcome.retryable_failure:
        _LookupRejection(LOOKUP_UNAVAILABLE_RESULT, LOOKUP_UNAVAILABLE_ERROR_CLASS),
    ProviderDataOutcome.selection_failure:
        _LookupRejection(LOOKUP_UNAVAILABLE_RESULT, LOOKUP_UNAVAILABLE_ERROR_CLASS),
}

rejection = _LOOKUP_REJECTIONS[provider_data.outcome]
return await _consuming_rejection(..., result=rejection.result,
                                  error_class=rejection.error_class, ...)
```

---

### WR-03: The consuming transaction's audit row never records whether the challenge was consumed, while the router's rejection row does

**File:** `src/nativespeaker/api/auth/creation.py:135-158, 339-371` vs
`src/nativespeaker/api/routers/auth.py:281-317`
**Severity:** WARNING

**Issue:** `_completion_details` records `mutation.challenge_consumed` truthfully from the boolean
`consume` returned. `creation.py::_details` records `user_created`, `identity_created`,
`store_attribution_rows_minted`, `access_grant_created`, `monthly_usage_row_created` — and nothing
about the consumption, even though `create_account` computed the same boolean twenty lines earlier
and explicitly logged an error when it was `False`:

```python
    consumed = await challenge_store.consume(...)
    if not consumed:
        logger.error("challenge_consume_did_not_match", challenge_row_id=str(challenge.id))

    await audit_writer.write_in_transaction(
        ...
        details=_details(context, result=result, provider=provider, user_id=user_id),
```

`§4.4` asks `mutation` for "the actual committed state change, **including partial state on
fail-closed paths**". A challenge that this transaction moved `claimed -> consumed` is a committed
state change, and it is the disposition every other rejection in the phase reports. The result is
that the two audit-row builders for one route disagree about what `mutation` means, and the
lifecycle divergence that `logger.error` flags is discoverable only in the structured log — never
in the append-only table that is supposed to be sufficient to reconstruct "what state changed".

**Fix:** thread the boolean into the builder and record it, matching the router:

```python
def _details(context, *, result, provider, user_id, consumed: bool) -> dict:
    ...
        mutation={"user_created": succeeded,
                  "identity_created": succeeded,
                  "challenge_consumed": consumed,
                  "store_attribution_rows_minted": len(PurchaseProvider) if succeeded else 0,
                  "access_grant_created": False,
                  "monthly_usage_row_created": False},
```

---

### WR-04: An internal error inside completion writes no audit row, leaving the audited attempt with no terminal outcome on record

**File:** `src/nativespeaker/api/auth/creation.py:182-200`; `src/nativespeaker/api/routers/auth.py:325-461`
**Severity:** WARNING

**Issue:** `POST /auth/create-user` carries a non-`None` `operation`, which by `audit.py`'s own
statement of §4.1 puts it on the audited path: "exactly one row per on-path attempt, for its
terminal outcome, written before the response returns" — "never because of how far the handler ran
or which phase rejected". Several completion paths return a terminal 500 with no row at all:

* `classify_insert_conflict` re-raising an unmapped constraint (deliberately — but the re-raise
  still owes a row);
* `session.commit()` raising after `write_in_transaction` swallowed a flush failure — the
  `internal_error` case `audit.py` cites as RESEARCH Pitfall 10 is precisely "an `internal_error`
  row for an unresolvable user *cannot* carry NULL actors", so the writer is built for this row and
  nothing calls it;
* any database failure inside `locate`, which `challenges.py` documents as raising out rather than
  becoming `challenge_not_found`.

On each of those the challenge is already claimed-and-committed (so it is dead, which is fine) but
is never consumed and never audited. The registry has `AuthEventResult.internal_error` and
`errors.INTERNAL_ERROR` for exactly this outcome; the phase reaches for neither.

**Fix:** wrap the completion body once, at the outermost point that still has the actor and the
challenge row id, and write the terminal row before re-raising:

```python
async def _complete(session, session_factory, *, context, identity, challenge_id,
                    challenge_store, audit_writer, adapter) -> Response:
    try:
        return await _complete_inner(...)
    except Exception:
        # §4.1: the attempt's terminal outcome is a row, whatever it was. Standalone-durable --
        # the consuming transaction, if one was open, is being torn down by the caller.
        await session.rollback()
        await audit_writer.write_standalone(
            session_factory,
            operation=AuthOperation.create_user,
            result=AuthEventResult.internal_error,
            actor_issuer=identity.issuer, actor_subject=identity.subject, actor_provider=None,
            challenge_row_id=None,
            details=_completion_details(context, result=AuthEventResult.internal_error,
                                        stage="internal_error", provider_data_read=False,
                                        consumed=False),
            created_at=context.evaluated_at)
        raise
```

(Note the `challenge_row_id` must be captured before any rollback, per CR-02 — pass it down rather
than reading it off a possibly-expired instance.)

---

_Reviewed: 2026-08-24T01:03:39Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
