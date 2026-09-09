---
phase: 46-post-auth-sign-out-all
reviewed: 2026-09-08T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/routers/auth.py
  - tests/e2e/test_sign_out_all.py
  - tests/unit/conftest.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_rejection_vocabulary.py
findings:
  critical: 0
  warning: 5
  info: 8
  total: 13
status: issues_found
---

# Phase 46: Code Review Report

**Reviewed:** 2026-09-08
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the Phase 46 diff (`git diff phase-45..HEAD`) across the four source files and the eight
test files. The change adds `revoke_refresh_tokens` to the `FirebaseAdminAdapter` Protocol and to
`FirebaseAdminLookup`, a `RevocationUnconfirmed` (503) leaf, and the `POST /auth/sign-out-all`
handler with its own retry wrapper.

Empirical baseline established during the review: `ruff check src tests` passes, `pytest tests/unit`
passes (1281 tests), and `ty check src` reports 53 diagnostics, **three of them new and introduced
by this phase** (`routers/auth.py:206:38`, `206:64`, `208:63`).

No finding rises to BLOCKER: I could not prove an incorrect answer on any reachable path. The retry
policy, the `except` ordering (`UserNotFoundError` before the `FirebaseError` it subclasses), the
`app=` explicitness, the fail-closed issuer selection and the error-tree totality all hold up under
tracing. The five warnings below are a log-hygiene defect that contradicts the phase's own stated
invariant, a provenance choice that diverges from D-01 and adds the three type errors, a wiring test
that asserts nothing, an OpenAPI description that overstates what the call achieves, and a Protocol
that no implementation can satisfy.

## Warnings

### WR-01: The malformed-subject arm writes the Firebase subject into the log

**File:** `src/nativespeaker/api/auth/firebase.py:91-94` (the `logger.warning` at :93)
**Issue:** `firebase_admin._auth_utils.validate_uid` raises
`ValueError('Invalid uid: "{uid}". The uid must be a non-empty string ...')` — the message embeds
the uid verbatim. `_revoke` then does `logger.warning("firebase_revoke_subject_malformed",
detail=str(error))`, so the caller's Firebase `sub` lands in a WARNING record.

This contradicts D-07 ("Never the subject, never a token") and contradicts the phase's own e2e
assertion `test_no_record_of_any_outcome_carries_the_subject_or_the_provider_uid`
(`tests/e2e/test_sign_out_all.py:306-327`), which claims no record of any outcome carries the
subject. That test passes only because it never exercises this arm.

Reachability today is low but not structural: the route needs a linked row, and a row can only be
linked through `/auth/create-user`, whose `_read` path hits the same 128-character check first. The
guard is therefore one edit away from becoming reachable (an operator-seeded row, a subject-length
change, or any future arm reusing `detail=str(error)`). The identical defect already exists at
`_read` (`firebase.py:117-119`), where it *is* reachable from `/auth/create-user`; that one is
pre-existing, but Phase 46 copied the pattern instead of fixing it.

**Fix:** drop the provider text from this arm — the class and the stage already say everything an
operator needs, and the SDK message adds only the uid.
```python
        except ValueError:
            # The SDK checks the uid before it sends the request, so another attempt answers the same.
            # The SDK's own message embeds the uid, so it is not admissible here.
            logger.warning("firebase_revoke_subject_malformed")
            raise RevocationUnconfirmed(stage="subject_rejected") from None
```

### WR-02: The handler takes the issuer and subject from the stored row, not from the verified token

**File:** `src/nativespeaker/api/routers/auth.py:206`, `:208`
**Issue:** D-01 specifies the Admin app is selected "by the **request-verified** issuer". The
handler instead reads `identity.identity.issuer` and `identity.identity.subject` — the
`ExternalIdentity` ORM row. `Identity` already carries the verified pair as `identity.issuer` and
`identity.subject`, and that is what every other caller uses (`services/auth.py:162`,
`crud/challenges.py:46-47,101-103`, `crud/identities.py:96-97`). This handler is the only place in
`src/` that reads the pair off the row.

Two consequences, both provable:
1. The provenance of the value sent to the provider is a database row rather than the credential the
   request presented. The two are equal today only because `IdentitiesDB.resolve` looks the row up
   by that exact pair (`crud/identities.py:33-35`). Nothing enforces it.
2. `identity.identity` is typed `ExternalIdentity | None` and `get_linked_identity` narrows only
   `identity.user`, so `ty check src` now reports three new `unresolved-attribute` errors at
   `206:38`, `206:64` and `208:63` that did not exist at `phase-45`.

**Fix:** use the verified pair for the call. The log line's `identity.identity.id` has no equivalent
on `Identity` and stays as is.
```python
    await revoke_with_retry(adapter, identity.issuer, identity.subject)
```

### WR-03: `TestTheSignOutRouteOpensNoSession` asserts nothing — the same assertion passes for a route that does open a session

**File:** `tests/unit/test_app_wiring.py:111-116`
**Issue:** `_declared` (`:29-31`) returns only `route.dependant.dependencies` — the *direct* level.
No route in the app declares `get_db` directly; they declare services that depend on it. Verified
empirically:

```
/auth/sign-out-all ['get_identity', 'get_linked_identity', 'get_firebase_adapter'] | get_db direct: False
/auth/sync         ['get_identity', 'get_linked_identity', 'get_sync_service']     | get_db direct: False
```

`/auth/sync` opens a session through `get_sync_service` and would pass this test unchanged, so the
test cannot fail for the reason its docstring gives ("the handler declares no session"). The file
already defines the correct helper, `_flattened` (`:34-44`), which walks sub-dependencies.

**Fix:**
```python
    def test_sign_out_all_declares_no_database_session(self):
        # `_flattened` walks sub-dependencies, so a session taken through a service is visible here.
        assert get_db not in _flattened(_route_at("/auth/sign-out-all"))
```
(Confirm it still passes: the route's only barrier session is `get_identity`'s own short one, opened
from `session_factory`, not from `get_db`.)

### WR-04: The OpenAPI description overstates what the revocation achieves

**File:** `src/nativespeaker/api/routers/auth.py:201-202`
**Issue:** The description reads "The account cannot use its current sessions again." That is false
for up to one hour. `revoke_refresh_tokens` only moves `tokens_valid_after_timestamp`; the SDK's own
docstring states "existing ID tokens may remain active until their natural expiration (one hour)"
and that `verify_id_token(..., check_revoked=True)` is what detects revocation. This deployment
forbids `check_revoked` (SHARED-INVARIANTS § "Global deletions"), and Envoy Gateway verifies the JWT
signature only — `grep -rn "check_revoked" src/` returns nothing. So every already-minted ID token,
including a stolen one, keeps working on every route for the rest of its hour after a confirmed 204.

This is a published API contract with a security-relevant claim. A client that trusts it will not
clear local state, and an operator answering an account-compromise report will believe the tokens
are dead when they are not.

**Fix:** state what the call does, not what it is hoped to imply.
```python
             description="Revokes every refresh token the account holds, so no new session can be "
                         "minted for it. An ID token already issued stays valid until it expires "
                         "(up to one hour). An anonymous account cannot be signed in to again.",
```

### WR-05: The `FirebaseAdminAdapter` Protocol declares synchronous methods that no implementation satisfies

**File:** `src/nativespeaker/api/auth/adapters.py:21-31` (new method at `:28-30`)
**Issue:** Both Protocol methods are declared `def`, returning `VerifiedProviderIdentity` and `None`.
Every implementation — `FirebaseAdminLookup.get_user_provider_data` / `.revoke_refresh_tokens`
(`firebase.py:64`, `:73`), `tests/unit/conftest.py::FakeFirebaseAdapter`, the e2e
`scripted_firebase_adapter` — is `async def` and returns a coroutine. No object in the codebase
conforms to this Protocol, which is why `get_firebase_adapter` is "deliberately unannotated"
(`app/dependencies.py:115-118`) and why `revoke_with_retry(adapter, ...)` takes an untyped
`adapter`. The seam is unenforceable documentation.

The two new tests make this worse rather than better:
`test_revoke_refresh_tokens_returns_nothing_at_all`
(`tests/unit/test_adapter_interfaces.py:122-124`) asserts the declared return annotation is `None`,
which is precisely the annotation the real method contradicts. The test locks in the mismatch.

Phase 46 doubled the surface of a declaration that cannot be checked. Given AGENTS.md's
"don't over-engineer", the cheap fix is to make the Protocol true, not to delete it.

**Fix:**
```python
class FirebaseAdminAdapter(Protocol):
    """One configured integration, one client selected by issuer match, and no ambient fallback."""

    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """The providerData read: the verified identity, or a raise."""
        ...

    async def revoke_refresh_tokens(self, issuer: str, subject: str) -> None:
        """The revocation: a return that confirms it, or a raise."""
        ...
```
Then annotate `get_firebase_adapter` and the two `*_with_retry` wrappers with it, and update
`test_adapter_interfaces` to read the return annotation off the coroutine.

## Info

### IN-01: `_revoke`/`_read` and `revoke_with_retry`/`lookup_with_retry` are near-verbatim duplicates

**File:** `src/nativespeaker/api/auth/firebase.py:82-102` vs `:104-131`; `:186-194` vs `:170-178`
**Issue:** The two retry wrappers differ only in the callback and the method name; the two SDK
bodies share three of four `except` arms verbatim (`GoogleAuthError` and `FirebaseError` are
identical modulo the event name). D-02 allowed either shape. The cost is that a future fix to the
arm ordering or to WR-01 has to be made twice, and one of the two will be missed.
**Fix:** one wrapper parameterised by the method name and the exhaustion leaf, e.g.
`_with_retry(call, issuer, subject, *, exhausted)`.

### IN-02: The `Lookup` vocabulary now names a write path

**File:** `src/nativespeaker/api/auth/firebase.py:58` (`FirebaseAdminLookup`), `:24`
(`FIREBASE_LOOKUP_ATTEMPTS`), `:27` (`RetryableLookupError`)
**Issue:** The module docstring was updated to "two adapter methods", but the class, the attempts
constant and the retry marker still say "lookup" while the revocation is a write. D-01 left the
rename to discretion and it was declined; the constant and the marker were not considered.
**Fix:** if the rename is taken later, rename all three together (`FirebaseAdminClient`,
`FIREBASE_CALL_ATTEMPTS`, `RetryableCallError`) rather than the class alone.

### IN-03: Stale comment left by this phase in `app/dependencies.py`

**File:** `src/nativespeaker/api/app/dependencies.py:117`
**Issue:** "The concrete class implements the Protocol's one reachable method asynchronously, not
synchronously." The Protocol now has two. The file is not in the phase diff, but this phase is what
made the comment false.
**Fix:** "the Protocol's two methods asynchronously, not synchronously".

### IN-04: No test asserts the route makes no providerData read

**File:** `tests/e2e/test_sign_out_all.py:135-173`
**Issue:** The brief forbids a providerData read on this route, and the phase boundary repeats it
("no read of the stored provider"). `FakeFirebaseAdapter` already records reads in `.calls`
(`tests/unit/conftest.py:200`), but no test in this file ever asserts on it. A handler that grew a
`lookup_with_retry` call would pass every test here.
**Fix:** add `assert scripted_firebase_adapter.calls == []` to
`test_it_makes_exactly_one_revocation_call_for_the_verified_pair`.

### IN-05: A tautological assertion

**File:** `tests/unit/test_firebase_adapter.py:270`
**Issue:** `assert not isinstance(raised.value, RetryableLookupError)` inside
`with pytest.raises(RevocationUnconfirmed)`. `RevocationUnconfirmed` descends from `AppError` and
`RetryableLookupError` from `Exception`; the two trees are disjoint, so the assertion cannot fail
once `pytest.raises` has matched. The intent — "this arm does not spend retry budget" — is already
covered by `test_a_definitive_revocation_answer_costs_exactly_one_attempt`
(`tests/unit/test_firebase_retry.py:216`).
**Fix:** delete the line, or replace it with a budget assertion through `revoke_with_retry`.

### IN-06: The "every value of every record" assertion silently skips non-string fields

**File:** `tests/e2e/test_sign_out_all.py:324-327`
**Issue:** The comment claims "a field added later cannot slip an identifier past this", but the
comprehension filters on `isinstance(value, str)`. A field logged as a `UUID`, a `bytes`, a list or
any object whose `repr` carries the subject passes unchecked.
**Fix:** compare against `str(value)` for every value instead of filtering by type.

### IN-07: `subject_rejected` answers "temporarily unavailable" for a permanent condition

**File:** `src/nativespeaker/api/auth/firebase.py:91-94`; `src/nativespeaker/api/errors.py:414-417`
**Issue:** A uid the SDK refuses before sending will be refused identically forever, but the client
is told 503 `verification_temporarily_unavailable`, whose whole meaning is "come back". A client
following its own retry policy loops indefinitely. D-05 chose this deliberately ("one leaf for every
unconfirmed outcome"), and the path is effectively unreachable today (see WR-01), so this is
recorded rather than argued.
**Fix:** none required under D-05. If it is ever reachable, a 4xx leaf is the honest answer.

### IN-08: One unrate-limited provider write per request

**File:** `src/nativespeaker/api/routers/auth.py:198-209`
**Issue:** Every accepted request performs a Firebase Admin write, and up to three on a retryable
outcome. `/auth` paths are in no HTTPRoute today, so AGENTS.md's "the gateway rate-limits by IP,
user, URL" does not yet cover this route; the route itself imposes no budget. An authenticated
caller can loop on its own subject and burn Firebase Admin quota. Recorded by D-09 as an uncounted
divergence on the Phase 40 D-22 precedent, and deferred to the v2.1 gateway contract.
**Fix:** none this phase. Carry into the v2.1 gateway work as a named entry rather than a general
`/auth` rule.

---

_Reviewed: 2026-09-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
