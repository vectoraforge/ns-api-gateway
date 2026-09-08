# Phase 46: POST /auth/sign-out-all - Research

**Researched:** 2026-09-08
**Domain:** One FastAPI route calling `firebase_admin.auth.revoke_refresh_tokens` through an issuer-selected Admin app
**Confidence:** HIGH

## Summary

Nothing new is designed here. Every mechanism this phase needs already exists and is read directly
from the tree: the issuer-keyed apps dict, the `run_in_threadpool` call pattern, the tenacity policy,
the `ProviderLookupError` leaf shape, the route-level `Depends(get_linked_identity)` narrowing, the
204 handler shape, and the two scriptable fakes. The phase adds one method to `FirebaseAdminLookup`,
one line to the `FirebaseAdminAdapter` Protocol, one error leaf, one route and one INFO log line.

The SDK behaviour CONTEXT.md D-02/D-03/D-05/D-06 assumes is confirmed against the pinned source:
`revoke_refresh_tokens` returns `None`, raises `ValueError` on a malformed uid before any network
call, and raises `FirebaseError` subclasses for every transport, timeout and backend failure. The
unknown-uid case reaches `auth.UserNotFoundError` through the same `USER_NOT_FOUND` mapping
`get_user` uses.

The real planning risk is not the route — it is four existing tests that this phase's edits break by
construction. Each is a literal that must be re-written, not a test that will simply keep passing.

**Primary recommendation:** mirror `_read`/`lookup_with_retry` arm for arm; plan the four breaking
test-literal edits as named tasks with `grep -c` source assertions, not as incidental fallout.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: A second method on `FirebaseAdminLookup`.** `auth/firebase.py` gains
  `revoke_refresh_tokens(issuer, subject)` beside `get_user_provider_data`. It selects the Admin
  app from the same apps dict by the request-verified issuer, and it calls
  `firebase_admin.auth.revoke_refresh_tokens(subject, app=app)` through `run_in_threadpool`, as
  the read does. No app for the issuer fails closed with no call made. The `FirebaseAdminAdapter`
  Protocol in `auth/adapters.py` grows by this one method. This answers the FOUND-08 forward flag
  the way it directs: the seam is declared beside its first implementation. The class name
  `Lookup` is now imprecise; a rename is at Claude's discretion.
  — **Reversibility:** reversible — one method, one Protocol line, one fake.

- **D-02: The same retry budget as `getUser`.** Three attempts through the existing tenacity
  policy and the existing attempts constant. Retryable: `FirebaseError` and `GoogleAuthError`.
  Definitive after one attempt: Firebase `UserNotFoundError` (D-06) and the SDK's `ValueError` on
  a malformed uid (D-05). The recorded cost: each attempt can hold up to two SDK transport tries
  at the app-level 8s timeout, so a Firebase outage holds one request for about 48s before the
  client is told to retry (the 37-10 measurement). The user chose one retry rule for every
  Firebase call over a shorter sign-out-specific budget.

- **D-03: Confirmation is the SDK call returning without raising.** No read-back and no
  `getUser` call. The brief forbids a providerData read on this route, and the SDK returns
  nothing on success.

- **D-04: 204 No Content.** The brief defines no response fields, the client is about to discard
  its local state, and entitlement did not change. The handler declares `get_linked_identity` and
  the Firebase seam accessor only: no `get_db`, so no session is opened for the request beyond the
  barrier's own short one. No service is earned: the handler body is one awaited call, which
  `AGENTS.md` § "Package layout" keeps in the handler.

- **D-05: One leaf for every unconfirmed outcome.** `RevocationUnconfirmed(ProviderLookupError)`
  in `errors.py`, status 503, code `verification_temporarily_unavailable`, the code every Firebase
  Admin failure already maps to. It is raised for a Firebase error response, a transport failure,
  a timeout, an exhausted retry budget, no app for the issuer, and a malformed uid. The `stage`
  field distinguishes them in the WARNING log line and nowhere else. No new `ErrorCode` member.
  The user chose a leaf of its own over `Unavailable` with a stage so the attempt that neither
  confirmed nor demonstrably failed is found in the logs by its own event name.

- **D-06: Firebase "no such user" answers 401 `auth_required`.** The existing `UserNotFound` leaf
  is raised with a revocation stage. The token verified and the identity row is linked, but the
  IDP has no account behind the uid: nothing exists to revoke and no token can be minted for it
  again. The client's 401 handling ends the session. The alternative, 503 on every attempt for up
  to an hour until the ID token expires, was declined. **FLAGGED CONFLICT** against
  `11-sign-out-all.md` § "Error classes and triggers": the brief lists `auth_required` for
  barrier failures only and puts every non-confirmed revocation on the server-error surface.
  — **Reversibility:** reversible — one `except` arm.

- **D-07: One INFO line on confirmation.** Event `sign_out_all_confirmed` carrying
  `identity_row_id`, a field `UpgradeRefused` already logs. For an anonymous account this route
  is the one-way door, and the middleware `request` line carries no id, so without this line no
  operator can answer "did account X sign out everywhere". Never the subject, never a token.
  This narrows 38 D-02 ("no success log line") to sync; it does not reopen it there. The
  SIGNOUT-02 amendment by Phase 38 permits exactly this: "Phase 46 may still choose to log more
  on its own terms".

- **D-08: No operation label; the Phase 40 flag is closed.** Sign-out is not challenge-bearing
  and writes no audit row, so the enum's one surviving consumer,
  `core.auth_challenges.operation`, never reads it. `core.auth_operation` keeps its four values
  and the single migration is not edited. Same reasoning and same outcome as RESTORE-01's twin,
  decided here on this route's own terms as the flag requires.

- **D-09: Amend `.planning/REQUIREMENTS.md` on the Phase 45 model, in full.** Dated entries under
  SIGNOUT-01 and SIGNOUT-02: the two forward flags closed (the adapter seam, the label); one new
  flagged conflict (D-06) by brief line; the inventory of obligations already dead before this
  phase, each by brief line and by the phase that removed its mechanism — the route registry and
  its inventory table (Phase 37.1 D-06, FOUND-01), the audit row and the `revocation_unconfirmed`
  and `succeeded` result values (Phase 37.1 D-01, Phase 38 D-03), the backend rate-limit exemption
  clauses (Phase 35 D-05), coalescing (Phase 35 D-05), the exactly-one-`Authorization` wire
  contract at `:42` (developer removal 2026-08-30, FOUND-01), the gateway per-IP and per-user
  entries (v2.1 gateway contract); the unbounded Firebase revocation write per attempt recorded
  as an uncounted divergence on the Phase 40 D-22 precedent (one subject looping on itself, a
  valid token for a linked account required first); the header's counts re-derived. Mark
  SIGNOUT-01 and SIGNOUT-02 met on measured suite counts. In `ROADMAP.md`, rewrite success
  criterion 3 from "Phase 46 must decide" the audit question to what is built (D-05, D-07, the
  middleware line, no row), and record criteria 1, 2 and 4 as met when they are.

- **D-10: `11-sign-out-all.md` and `SHARED-INVARIANTS.md` are NOT edited** (43 D-27, 45 D-14).
  Divergences live in REQUIREMENTS.md.

- **D-11: Every comment this phase writes is ASD-STE100, inline where possible** (45 D-15), under
  `AGENTS.md` § "Comments and docstrings".

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `11-sign-out-all.md` alone will try to build all of these. **None exists.**

- **No route registry, no route metadata, no inventory table** (Phase 37.1 D-06/D-10). The
  route joins `routers/auth.py` under a route-level `Depends(get_linked_identity)`;
  `tests/unit/test_app_wiring.py` gains `/auth/sign-out-all` in its two narrowed-route lists.
- **No `audit.auth_events` row, no audit writer, no `core.auth_event_result` value**
  (Phase 37.1 D-01, Phase 38 D-03/D-04). The record is the middleware `request` line, one
  WARNING per rejection from `app_error_handler`, and D-07's INFO line.
- **No backend rate limit, no provider budget, no coalescing** (Phase 35 D-05). `/auth` paths
  are in no HTTPRoute today; the gateway contract is v2.1.
- **Outcomes are exception classes, never an enum** (Phase 37.3 D-12). Log event names come from
  the class name.
- **The barrier is `get_identity` then `get_linked_identity`** and is not re-implemented. Every
  barrier rejection this route owes already exists: `InvalidExternalJwt` (401),
  `PreAuthIdentityNotAllowed` (403), `HistoricalIdentity` and `BlockedUser` (403
  `account_unavailable`), `IdentityUnresolvable` (500). No route-specific exception for blocked
  or retired subjects.
- **One named Admin app per issuer on Application Default Credentials, never a `[DEFAULT]` app**
  (Phase 37 D-08 as amended by 37-10, Phase 37.2 D-06…D-08). An absent credential returns an
  empty apps dict at boot and the route fails closed as D-05.
- **Every synchronous SDK call runs in `run_in_threadpool`** (35-12).
- **No provider read, no `checkRevoked`, no retry queue, no durable revocation state, no
  per-device sign-out, no challenge** — the brief's own deletions, unchanged.

### Claude's Discretion

- **Names:** the class rename (`FirebaseAdminLookup` to something covering both calls, or left),
  the attempts constant rename, the `stage` strings on `RevocationUnconfirmed` and on the
  `UserNotFound` arm, the INFO event name if `sign_out_all_confirmed` reads badly.
- **The retry wrapper:** a second `*_with_retry` function beside `lookup_with_retry`, or one
  generic wrapper both calls share. The exhausted-budget callback must raise
  `RevocationUnconfirmed`, not `Unavailable`.
- **The handler's declaration order** and the OpenAPI `summary` and `description`, including
  whether the description states that an anonymous account becomes unreachable after this call.
- **Test shape, on the 43 D-24 / 44 / 45 model:** unit tests script
  `firebase_admin.auth.revoke_refresh_tokens` as `tests/unit/test_firebase_adapter.py` scripts
  `get_user`; attempt counts per outcome as `tests/unit/test_firebase_retry.py` does;
  `FakeFirebaseAdapter` in `tests/unit/conftest.py` gains the method; e2e cases through the real
  router with the scripted fake: confirmed answers 204 with an empty body and one INFO line,
  a scripted `FirebaseError` answers 503 with the shared body, no such user answers 401, no app
  for the issuer answers 503, and every barrier rejection is byte-identical to `/auth/sync`'s.
  Whether to add a session stand-in proving the handler runs zero statements after the barrier,
  as Phase 45 did, is the planner's call.
- **Plan wave order.**

### Deferred Ideas (OUT OF SCOPE)

- **Gateway rate limits on the auth surface**, including the Firebase revocation write per
  attempt — the v2.1 gateway contract (Phase 35 D-05, 41 D-20).
- **`/auth` paths in the gateway HTTPRoutes** — absent today; a gateway concern.
- **Phase 44.1, the feature-sliced restructure** — after this phase, as recorded in 44-CONTEXT.
- **One test asserting each Python enum's values equal its `core.*` type's labels** — still
  deferred.
- **Renaming `FirebaseAdminLookup`** if left as is under D-01's discretion.
- **Reviewed todos, not folded:** `message-ordering-is-unspecified` and
  `secret-manager-integration`. Both selected then withdrawn by the user. Neither is in scope.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIGNOUT-01 | The endpoint revokes the verified subject's Firebase refresh tokens through the issuer-selected Firebase Admin client, returning success only on Firebase-confirmed revocation | § "The SDK call, verified" — `revoke_refresh_tokens` returns `None` on success and raises on every other outcome, so "returned without raising" is the whole confirmation test (D-03). § "The existing seam" gives the issuer-selection code to mirror. |
| SIGNOUT-02 | Fail-closed half only (audit half settled by Phase 38): an indeterminate or failed revocation fails closed rather than reporting success | § "The SDK call, verified" enumerates every raise the SDK can produce; § "Error-tree facts" shows `RevocationUnconfirmed` is legal at the same code and status as `Unavailable`; `tests/unit/test_firebase_retry.py::TestTheExhaustionConversion` is the ready-made model for the exhausted-budget case. |

Both requirements are checkbox items at `.planning/REQUIREMENTS.md:540` and `:545`, currently
unchecked. D-09 marks them met on measured suite counts.

## Project Constraints (from AGENTS.md)

`/home/init/native-speaker/AGENTS.md` (root, product framing) and
`/home/init/native-speaker/ns-api-gateway/AGENTS.md` (repo, code rules) both bind. The repo file is
94 lines; every rule below is quoted or paraphrased from it. [VERIFIED: ns-api-gateway/AGENTS.md:1-94]

- **Docstrings — three lines maximum.** "State what the function, class, or module does. Nothing
  else." Do not describe what lives elsewhere or what the entity is not. Enforced by
  `tests/unit/test_docstring_bar.py`, whose `BASELINE` is `0` for every root — a four-line
  docstring anywhere fails the suite. [VERIFIED: tests/unit/test_docstring_bar.py:42-48]
- **Comments — only where necessary, one line each.** Default to none. Never explain the design or
  a rule enforced in another module.
- **Package layout:** `auth/` is "external-SDK seams only: `adapters.py`, `firebase.py` and
  `jwt_verifier.py`". `routers/` is "HTTP handlers, `Depends()` only, calling `crud/` or a service".
- **A service is earned by complexity, not assumed by category.** "One awaited read is neither, so
  it stays in the handler." This is the ground under D-04 — no `SignOutService`.
- **`Depends()` only still binds the handler:** take the barrier and any seam from a dependency,
  never construct a class in the body.
- **Function shape:** "Delete a function that is only a step." Inline it, then read the call site;
  if the call site now needs a comment, the function stays. Relevant to the discretion choice
  between a second `*_with_retry` and one generic wrapper.
- **The `limits` library is deleted from the product, not deferred** (Phase 35 D-05). No backend
  rate limit is to be added here under any framing.
- Root `AGENTS.md`: "Keep specs short: programming this app should not consume many tokens." The
  plan set should be small; nine plans as in Phase 45 is the ceiling, not the target.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Token acceptance and identity resolution | Barrier dependency (`app/dependencies.py`) | — | `SHARED-INVARIANTS.md` § "The barrier": the only place identity happens; the handler consumes the typed context. |
| Issuer → Admin app selection | `auth/firebase.py` seam | — | The apps dict lives on the seam class; selection is per call so no attempt can reach an ambient client. |
| The revocation SDK call | `auth/firebase.py` seam, off-loop | — | `firebase-admin` is synchronous on `requests`; `run_in_threadpool` is the standing rule (35-12). |
| Retry budget and exhaustion conversion | `auth/firebase.py` module function | — | `lookup_with_retry` already owns this tier for the read; the twin belongs beside it. |
| Outcome → status/code/log event | `errors.py` leaf + `app/error_handlers.py` | — | One shared registry; the class name *is* the log event name. |
| HTTP shape (204, no body) | `routers/auth.py` handler | — | `Depends()` only, one awaited call, no service earned. |
| Attempt record | `logs.py` middleware + `app_error_handler` + D-07 INFO line | — | No audit row exists to write (Phase 37.1 D-01, Phase 38 D-03). |

## Standard Stack

No new dependency. Everything is already installed and pinned.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `firebase-admin` | 7.3.0 | `auth.revoke_refresh_tokens` | Already the only Firebase Admin path in the tree [VERIFIED: uv.lock:339-341, pyproject.toml:24 `"firebase-admin>=7.3.0"`] |
| `tenacity` | (installed) | `AsyncRetrying`, `stop_after_attempt`, `retry_if_exception_type` | The existing budget `lookup_with_retry` uses [VERIFIED: src/nativespeaker/api/auth/firebase.py:11] |
| `starlette` | (installed) | `run_in_threadpool` | The standing off-loop rule [VERIFIED: src/nativespeaker/api/auth/firebase.py:10] |
| `structlog` | (installed) | the INFO line and the handler's WARNING | The one log pipeline [VERIFIED: src/nativespeaker/api/auth/firebase.py:9,18] |

**Installation:** none. No `uv add`, no `uv.lock` change, no `pyproject.toml` edit.

## Package Legitimacy Audit

Not applicable: this phase installs no external package. Every import it needs is already a
declared dependency in `pyproject.toml` and pinned in `uv.lock`.

## The SDK call, verified

Read this session from the installed source, not from memory.

**Success returns `None`.** [VERIFIED: .venv/lib/python3.14/site-packages/firebase_admin/auth.py:290-311]

```python
def revoke_refresh_tokens(uid, app=None):
    """Revokes all refresh tokens for an existing user.
    ...
    Raises:
        ValueError: If the user ID is None, empty or malformed.
        FirebaseError: If an error occurs while revoking the refresh token.
    """
    client = _get_client(app)
    client.revoke_refresh_tokens(uid)
```

There is no `return`. D-03's "confirmation is the call returning without raising" is exactly the
contract the SDK states.

**The call underneath is `accounts:update` with `validSince`.**
[VERIFIED: .venv/.../firebase_admin/_auth_client.py:142-161]

```python
    def revoke_refresh_tokens(self, uid):
        ...
        self._user_manager.update_user(uid, valid_since=int(time.time()))
```

`update_user` calls `_auth_utils.validate_uid(uid, required=True)` before building the payload, then
`self._make_request('post', '/accounts:update', json=payload)`.
[VERIFIED: .venv/.../firebase_admin/_user_mgt.py:712-761]

**The `ValueError` arm is local and pre-network.**
[VERIFIED: .venv/.../firebase_admin/_auth_utils.py:86-93]

```python
def validate_uid(uid, required=False):
    if uid is None and not required:
        return None
    if not isinstance(uid, str) or not uid or len(uid) > 128:
        raise ValueError(
            f'Invalid uid: "{uid}". The uid must be a non-empty string with no more than 128 '
            'characters.')
    return uid
```

Malformed means: not a `str`, empty, or longer than 128 characters. No network call is made. This is
why D-05 classes it definitive after one attempt — retrying could never change the answer.
**Note the divergence from `_read`:** in `_read` the `ValueError` arm is *retryable*, because there
it catches a lazy `provider_data` materialization failure, not a uid validation failure
[VERIFIED: src/nativespeaker/api/auth/firebase.py:86-88]. The revocation arm must **not** copy that
classification. This is the single most likely mirroring mistake in the phase.

**Unknown uid raises `auth.UserNotFoundError`.** The backend `USER_NOT_FOUND` code is mapped by the
shared table every Auth call shares [VERIFIED: .venv/.../firebase_admin/_auth_utils.py:429-444]:

```python
_CODE_TO_EXC_TYPE = {
    ...
    'USER_NOT_FOUND': UserNotFoundError,
```

`UserNotFoundError` subclasses `exceptions.NotFoundError`
[VERIFIED: .venv/.../firebase_admin/_auth_utils.py:363-366], which is a `FirebaseError` — so, exactly
as in `_read`, the `except auth.UserNotFoundError` arm **must be listed before** the
`except exceptions.FirebaseError` arm or it is unreachable. That the Identity Toolkit answers
`accounts:update` on a deleted account with this code is corroborated by the upstream issue report
"There is no user record corresponding to the provided identifier" raised from `revokeRefreshTokens`
[CITED: github.com/firebase/firebase-admin-node/issues/550].

**Every transport failure is already a `FirebaseError`.**
[VERIFIED: .venv/lib/python3.14/site-packages/firebase_admin/_utils.py:219-230]

```python
    if isinstance(error, requests.exceptions.Timeout):
        return exceptions.DeadlineExceededError(...)
    if isinstance(error, requests.exceptions.ConnectionError):
        return exceptions.UnavailableError(...)
    if error.response is None:
        return exceptions.UnknownError(...)
```

So a timeout, a lost connection and an unparseable response all land in the single
`except exceptions.FirebaseError` arm. No separate `requests` arm is needed, and none exists in
`_read`. `update_user` can additionally raise `UnexpectedResponseError` (an `UnknownError`, hence a
`FirebaseError`) when the response body carries no `localId`
[VERIFIED: .venv/.../firebase_admin/_user_mgt.py:758-760, _auth_utils.py:356-360].

**`GoogleAuthError` still needs its own arm.** It is raised during credential refresh, before the
request is sent, and is not a `FirebaseError` — the comment on `_read`'s arm says exactly this
[VERIFIED: src/nativespeaker/api/auth/firebase.py:89-92].

**The 48s figure D-02 records, re-derived.** The SDK's default urllib3 retry is
[VERIFIED: .venv/.../firebase_admin/_http_client.py:42-44]:

```python
DEFAULT_RETRY_CONFIG = retry.Retry(
    connect=1, read=1, status=4, status_forcelist=[500, 503],
    raise_on_status=False, backoff_factor=0.5, **_ANY_METHOD)
```

`connect=1, read=1` means at most two transport tries per SDK call. At the app-level
`httpTimeout` of 8 seconds [VERIFIED: src/nativespeaker/api/auth/firebase.py:21
`FIREBASE_HTTP_TIMEOUT_SECONDS = 8`], one tenacity attempt costs up to 16s and three attempts up to
48s. D-02's number is correct. Separately, `status=4` on 500/503 responses allows up to five *status*
tries per call with ~7s of cumulative backoff, but those return promptly rather than timing out.

## The existing seam, quoted

`src/nativespeaker/api/auth/firebase.py:64-72` — the pattern D-01 mirrors verbatim:

```python
    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """Read `subject`'s providerData through the app `issuer` selects: the identity, or a raise."""
        app = self._apps.get(issuer)
        if app is None:
            # Fails closed with no call made: there is no ambient app to fall back to, by design.
            raise Unavailable(stage="issuer_selection")
        # `firebase-admin` is built on `requests` and has no async client, so it runs off the loop.
        return await run_in_threadpool(self._read, app, subject)
```

For revocation the `raise Unavailable(stage="issuer_selection")` becomes
`raise RevocationUnconfirmed(stage=...)` per D-05.

`src/nativespeaker/api/auth/firebase.py:134-147` — the retry tier:

```python
def _exhausted(retry_state) -> NoReturn:
    """Convert an exhausted retry budget into the `Unavailable` rejection the client is owed."""
    raise Unavailable(stage="provider_lookup") from retry_state.outcome.exception()


async def lookup_with_retry(adapter, issuer: str, subject: str) -> VerifiedProviderIdentity:
    """Call the adapter up to `FIREBASE_LOOKUP_ATTEMPTS` times; return the identity or raise."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        # Only the internal marker retries, so `UserNotFound` and `NotLinked` propagate after one attempt.
        retry=retry_if_exception_type(RetryableLookupError),
        retry_error_callback=_exhausted,
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
```

`RetryableLookupError` at `:27-28` is the sole retry predicate target. If the phase takes the
"one generic wrapper" discretion option, the wrapper must take the bound method *and* the
exhaustion callback as arguments — the two calls need different exhaustion leaves
(`Unavailable` vs `RevocationUnconfirmed`).

`src/nativespeaker/api/auth/adapters.py:21-26` — the Protocol D-01 grows:

```python
class FirebaseAdminAdapter(Protocol):
    """One configured integration, one client selected by issuer match, and no ambient fallback."""

    def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """The providerData read: the verified identity, or a raise."""
        ...
```

`adapters.py` is fenced by an import allowlist asserted in
`tests/unit/test_adapter_interfaces.py:24`:
`ALLOWED_IMPORT_ROOTS = {"dataclasses", "datetime", "enum", "typing", "uuid", "nativespeaker"}`.
The revocation method returns nothing, so it introduces no new import and no new value type —
`test_the_seam_declares_exactly_one_value_type` and
`test_every_public_class_is_a_protocol_or_a_frozen_dataclass` stay green.

## Error-tree facts

`errors.py:382-412` — the base and the two leaves that matter:

```python
class ProviderLookupError(AppError):
    """The provider lookup's rejections share this shape; only its leaves are raised."""

    def __init__(self, *, stage: str, cause: str | None = None) -> None:
        # Plain strings, both of them ours: no provider text is ever admissible in either field.
        self.stage = stage
        self.cause = cause
        super().__init__(f"{type(self).__name__.lower()} at {stage}")
```

```python
class UserNotFound(ProviderLookupError):
    """The provider stated the account does not exist: definitive, and it spends no retry budget."""
    status = 401
    code = "auth_required"

    def extra_headers(self) -> dict[str, str]:
        # The signature verified but names no live principal, so the credential is invalid in substance.
        return {"WWW-Authenticate": 'Bearer error="invalid_token"'}
```

```python
class Unavailable(ProviderLookupError):
    """The read could not be completed: an exhausted retry budget, or no app configured."""
    status = 503
    code = "verification_temporarily_unavailable"
```

**The totality walk permits `RevocationUnconfirmed` at the same code and status as `Unavailable`.**
The only conflict the walk reports is one code claimed at *two different* statuses
[VERIFIED: tests/unit/error_tree.py:37-45]:

```python
        owner, owned_status = status_of_code.get(code, (None, status))
        if owner is not None and owned_status != status:
            problems.append(f"code {code!r} is claimed at status {owned_status} by {owner} and at "
                            f"status {status} by {cls.__name__}")
```

Same code + same status is legal. This is the same precedent Phase 45 used for
`RestoreProviderUnknown` sharing `operation_not_allowed` at 403
[VERIFIED: .planning/STATE.md:682]. The leaf must declare **both** `status` and `code` or neither
[VERIFIED: tests/unit/error_tree.py:31-35], and declaring neither would make it answer the base 500
default and fail `undeclared()` [VERIFIED: tests/unit/error_tree.py:8-20].

**No `ErrorCode` member is added** (D-05), so `ErrorCode` at `errors.py:14-33` is unedited and
`tests/unit/test_error_contract.py::test_openapi_error_response_code_is_enum` keeps passing against
its `CONTRACT_CODES` literal at `:20`.

**The class name is the log event name.** `app_error_handler` writes
`camel_to_snake(type(exc).__name__)` as the event
[VERIFIED: src/nativespeaker/api/app/error_handlers.py:33-44], so `RevocationUnconfirmed` logs as
`revocation_unconfirmed` at WARNING with `stage` (and `cause` when set) as fields from
`ProviderLookupError.log_fields()`.

## Files this phase touches

| File | Change |
|------|--------|
| `src/nativespeaker/api/auth/adapters.py` | one Protocol method (D-01) |
| `src/nativespeaker/api/auth/firebase.py` | `revoke_refresh_tokens`, its synchronous body, its retry wrapper and exhaustion callback (D-01, D-02) |
| `src/nativespeaker/api/errors.py` | `RevocationUnconfirmed(ProviderLookupError)` (D-05) |
| `src/nativespeaker/api/routers/auth.py` | the eighth route, 204, `Depends(get_linked_identity)` + `Depends(get_firebase_adapter)`, D-07's INFO line; module docstring names seven routes today and must be re-counted within three lines |
| `tests/unit/test_adapter_interfaces.py` | **breaks** — see below |
| `tests/unit/test_auth_package_shape.py` | **breaks** — see below |
| `tests/unit/test_rejection_vocabulary.py` | **breaks** — see below |
| `tests/unit/test_app_wiring.py` | **breaks** — see below |
| `tests/unit/conftest.py` | `FakeFirebaseAdapter` gains the method |
| `tests/e2e/conftest.py` | no change needed — `scripted_firebase_adapter` wraps the same fake |
| `tests/unit/test_firebase_adapter.py`, `test_firebase_retry.py` | new cases on the existing models |
| `tests/e2e/test_sign_out_all.py` | new |
| `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` | D-09 |
| `k8s/`, `migrations/`, `pyproject.toml`, `uv.lock` | **no change** |

## Tests that break by construction

These are not risks — they are certainties. Each is a hand-written literal that the phase's own
edits invalidate. Plan them as named tasks.

**1. `tests/unit/test_adapter_interfaces.py:111`** — the Protocol method set:

```python
        assert self._methods(FirebaseAdminAdapter) == {"get_user_provider_data"}
```

Adding the second Protocol method fails this. The enclosing case is named
`test_it_declares_exactly_the_one_surviving_method` and its class docstring reads "One method, one
issuer-selected client" — the name, the docstring and the literal all need rewriting together.

**2. `tests/unit/test_auth_package_shape.py:13`** — the measured package shape:

```python
CURRENT = (8, 24, 59)
```

The tuple is (modules, classes, functions), counted by an AST walk at any nesting depth
[VERIFIED: tests/unit/test_auth_package_shape.py:15-26], so the new Protocol method, the new seam
method, its synchronous body and the retry wrapper each increment the third element. The case
docstring says "A later phase that grows the package has to come here and write the new number
down." Re-measure, do not guess.

**3. `tests/unit/test_rejection_vocabulary.py`** — `EVENT_NAMES` is a frozenset with one entry per
class in the tree, asserted equal to the derived set
[VERIFIED: tests/unit/test_rejection_vocabulary.py:67-140,152-155]. `revocation_unconfirmed` must be
added beside the existing lookup arms (`"user_not_found"`, `"unavailable"`, `"not_linked"`). If the
new leaf's `__init__` needs no arguments beyond `stage`, no `CONSTRUCTOR_ARGUMENTS` entry is needed
— `ProviderLookupError` subclasses without an entry are constructed with `()` and would raise on the
keyword-only `stage`, so **add an entry** following the `Unavailable` model at `:181`:
`errors_module.Unavailable: ((), {"stage": "issuer_selection"})`.

**4. `tests/unit/test_app_wiring.py:70-73` and `:80-83`** — the two narrowed-route lists, identical
parametrize tuples on two cases:

```python
    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant",
                                      "/auth/restore-subscription", "/users/me"))
```

`/auth/sign-out-all` joins both. Note the generic case at `:47-53`
(`test_every_route_but_the_two_exemptions_requires_a_linked_identity`) would already fail if the
route were registered without the route-level narrowing — so a missed `Depends(get_linked_identity)`
fails loudly rather than silently.

## Test-scaffolding models to copy

**Scripting the SDK (unit).** `tests/unit/test_firebase_adapter.py:100-115` is the fixture shape;
the revocation twin scripts `auth.revoke_refresh_tokens` on the same terms:

```python
@pytest.fixture
def get_user_calls(monkeypatch):
    """Monkeypatches `auth.get_user` to record its calls; the test scripts the answer."""
    calls: list[dict] = []

    def script(answer):
        def fake_get_user(uid, app=None):
            calls.append({"uid": uid, "app": app})
            if isinstance(answer, BaseException):
                raise answer
            return answer
        monkeypatch.setattr(auth, "get_user", fake_get_user)
        return calls

    return script
```

For revocation the scripted "success" answer is `None`, not a record. `RecordingApp` at `:75-79` and
the `adapter` fixture at `:100-102` are reusable unchanged. `TestSelection` at `:159-188` is the
model for the four selection cases (unconfigured issuer, empty mapping, the 503 pair, explicit
`app=`) — note `test_a_configured_issuer_passes_its_own_app_explicitly` asserts
`calls == [{"uid": SUBJECT, "app": app}]`, which is what proves no `[DEFAULT]` app is reachable.

**Counting attempts (unit).** `tests/unit/test_firebase_retry.py` provides `CountingAdapter` /
`AsyncCountingAdapter` (`:33-56`) that raise `AssertionError` on script overrun, and the `DEFINITIVE`
table (`:25-30`). The revocation twin's `DEFINITIVE` table is: a completed call (`None`),
`UserNotFound`, `RevocationUnconfirmed(stage="issuer_selection")` and
`RevocationUnconfirmed(stage=<malformed-uid stage>)`. `TestTheExhaustionConversion` (`:120-180`) is
the model for the six exhaustion cases, including
`test_neither_the_retry_error_nor_the_internal_marker_escapes`, which is the case that actually
enforces SIGNOUT-02's fail-closed rule at the retry tier.

**The fakes.** `tests/unit/conftest.py:192-210` — `FakeFirebaseAdapter` records calls and does
raise-or-return; the revocation method needs its own `answer` and `calls` attributes on the
`FakeDeviceCheckAdapter` two-method model (`tests/e2e/conftest.py:238-266`), which already
demonstrates the separate-answer-per-method shape. `tests/e2e/conftest.py:226-235`
(`scripted_firebase_adapter`) swaps `app.state.firebase_adapter` for the same class, so it needs
**no edit**.

**Log assertions in e2e.** `capture_logs()` does not work against a module-level logger, because the
binding is cached. `tests/e2e/test_app_store_webhook.py:70-101` uses a monkeypatched spy instead —
its own docstring says "A spy, not `capture_logs`: the module-level logger caches its binding, so
capture sees nothing." D-07's INFO line lives in `routers/auth.py`, whose `logger` is module-level
at `:39`, so the e2e assertion **must** use the spy. `capture_logs()` is fine in unit tests
(`tests/unit/test_logging.py:72,85,94`).

**Seeding a linked identity (e2e).** `tests/e2e/conftest.py:523-543` (`seed_identity`) inserts the
`core.users` and `core.external_identities` pair and takes `identity_state`, `user_active` and
`provider`, which is exactly the surface the barrier-rejection cases need.
`tests/unit/conftest.py:46-56` (`make_token`) mints the signed JWT.

**The 204 handler.** `src/nativespeaker/api/routers/chats.py:78-86`:

```python
@router.delete("/chats/{chat_id}",
               status_code=204,
               summary="Delete chat",
               description="Permanently deletes a chat session and all its messages.")
async def delete_chat(chat_id: UUID,
                      identity: Identity = Depends(get_linked_identity),
                      service: ChatService = Depends(get_chat_service)) -> Response:
    await service.delete_chat(chat_id, identity.user.id)
    return Response(status_code=204)
```

No `response_model`. The return annotation is `Response`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Confirming the revocation happened | A `getUser` read-back or a `tokens_valid_after` comparison | The call returning without raising | D-03; the brief forbids a providerData read on this route and the SDK returns nothing on success |
| Bounding the Firebase call | A new timeout, a new attempts constant, an `asyncio.wait_for` | `FIREBASE_LOOKUP_ATTEMPTS` and the app-level `httpTimeout` | D-02; both already exist and both are already asserted by tests |
| Transport/timeout classification | A `requests.exceptions` arm | `except exceptions.FirebaseError` | The SDK already converts `Timeout` and `ConnectionError` into `FirebaseError` subclasses |
| Recording the attempt | An audit row, a table, a writer | The middleware `request` line + the handler's WARNING + D-07's INFO line | Phase 37.1 D-01 deleted the subsystem; Phase 38 D-03 removed the obligation |
| Naming the outcome | An outcome enum or a `RevocationOutcome` value type | Exception classes | Phase 37.3 D-12; the class name is the log event name |
| Off-loop execution | `asyncio.to_thread`, a custom executor | `run_in_threadpool` | The standing rule (35-12) and what `_read` uses |

**Key insight:** every one of these was already built once in this repo, deleted deliberately, and
recorded as deleted. Rebuilding any of them is the failure mode this phase's CONTEXT.md was written
to prevent.

## Common Pitfalls

### Pitfall 1: copying `_read`'s `ValueError` classification
**What goes wrong:** the revocation arm marks a malformed uid retryable, so a permanently-bad uid
burns three attempts and answers 503 after ~0ms of useful work — and the "definitive after one
attempt" clause of D-02/D-05 is silently violated.
**Why it happens:** `_read`'s `ValueError` arm raises `RetryableLookupError`
[VERIFIED: src/nativespeaker/api/auth/firebase.py:86-88], and it is the natural line to copy.
**How to avoid:** in `_read` the `ValueError` comes from materializing lazy `provider_data`; in the
revocation path it comes from `validate_uid` before any network call. Classify it definitive.
**Warning signs:** a `test_a_definitive_answer_costs_exactly_one_attempt` case for the malformed uid
that reports 3.

### Pitfall 2: `except FirebaseError` placed before `except auth.UserNotFoundError`
**What goes wrong:** the unknown-uid case becomes unreachable, so D-06's 401 never fires and every
deleted account gets a 503 for an hour.
**Why it happens:** `UserNotFoundError` subclasses `NotFoundError` which subclasses `FirebaseError`;
Python takes the first matching arm.
**How to avoid:** mirror `_read`'s ordering, whose comment already says so — "listed before the
FirebaseError it subclasses" [VERIFIED: src/nativespeaker/api/auth/firebase.py:82-85].
**Warning signs:** the e2e "no such user answers 401" case returns 503.

### Pitfall 3: reusing `_exhausted` for the revocation wrapper
**What goes wrong:** an exhausted revocation budget raises `Unavailable`, not
`RevocationUnconfirmed`. The client answer is byte-identical (same 503, same code), so **no wire
assertion catches it** — only the log event name differs, which is the entire reason D-05 minted a
separate leaf.
**Why it happens:** `_exhausted` is right there and its signature fits.
**How to avoid:** CONTEXT.md § Discretion states the rule explicitly. Assert the *class*, not the
status: `assert isinstance(raised.value, RevocationUnconfirmed)`, on the model of
`test_exhaustion_is_not_the_user_not_found_mapping`
[VERIFIED: tests/unit/test_firebase_retry.py:174-180].

### Pitfall 4: `capture_logs()` in the e2e INFO-line case
**What goes wrong:** the assertion sees no records and either fails confusingly or, if written as
"no unexpected records", passes vacuously.
**How to avoid:** monkeypatch a spy onto the module logger, per
`tests/e2e/test_app_store_webhook.py:70-101`.

### Pitfall 5: forgetting the `routers/auth.py` module docstring
**What goes wrong:** the docstring says "The seven auth routes" and enumerates them
[VERIFIED: src/nativespeaker/api/routers/auth.py:1-3]. Eight routes with a docstring saying seven is
a stale claim, and the docstring is already three lines — adding a clause pushes it to four and
fails `tests/unit/test_docstring_bar.py`, whose `src` baseline is `0`.
**How to avoid:** rewrite the docstring to three lines or fewer including the new route.

### Pitfall 6: adding a `get_db` dependency out of habit
**What goes wrong:** D-04 explicitly declares only `get_linked_identity` and the seam accessor. A
`get_db` would open a request-scoped session for a handler that issues no statement.
**Warning signs:** if Phase 45's session stand-in idea is taken up, this is precisely what it
detects.

## Runtime State Inventory

Not applicable. This phase is additive: one route, one method, one error leaf. It renames nothing,
migrates nothing and deletes nothing.

- **Stored data:** none — no table is read or written. Verified: D-04 declares no `get_db`, and the
  brief's "No PostgreSQL business-state mutation" is unchanged.
- **Live service config:** none — `/auth` paths are in no HTTPRoute today (Phase 35 D-05,
  CONTEXT.md § Carried forward), so `k8s/` needs no edit.
- **OS-registered state:** none.
- **Secrets/env vars:** none — the Firebase credential is Application Default Credentials, already
  configured (`.env.example` § "Firebase Admin credential", Phase 37.2 D-06…D-08).
- **Build artifacts:** none — no `pyproject.toml` or `uv.lock` change, so no reinstall.

**Effect on Firebase state:** `revoke_refresh_tokens` advances the subject's
`tokens_valid_after_timestamp` at the IDP. That is the operation's whole point, it is idempotent
(re-revoking only re-asserts the timestamp), and it is not repo state.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `firebase-admin` | the revocation call | ✓ | 7.3.0 | — |
| `uv` + project venv | every test command | ✓ | Python 3.14 venv at `.venv/` | — |
| PostgreSQL | the e2e and schema suites | ✓ | e2e 333 passed, schema 229 passed this session | — |
| Application Default Credentials | the optional real-credential e2e case | not probed | — | that case skips when absent, per `.env.example` § "Firebase Admin credential" |

**Missing dependencies with no fallback:** none.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest with `pytest-asyncio` (`asyncio_mode = "auto"`) [VERIFIED: pyproject.toml:55-64] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]` |
| Default selection | `addopts = "-v --tb=short -m 'not e2e and not schema'"` — the bare command runs unit only |
| Quick run command | `uv run pytest tests/unit/<file> -q` |
| Full suite command | `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` |

**Measured baseline, this session** (the numbers D-09 re-derives against):

| Suite | Command | Result |
|-------|---------|--------|
| unit | `uv run pytest -q` | 1255 passed, 562 deselected |
| e2e | `uv run pytest -m e2e -q` | 333 passed, 1484 deselected |
| schema | `uv run pytest -m schema -q` | 229 passed, 1588 deselected |

Total 1817. Schema is untouched by this phase and must still read 229.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIGNOUT-01 | The seam selects the app by issuer and passes `app=` explicitly | unit | `uv run pytest tests/unit/test_firebase_adapter.py -q` | ✅ (add cases) |
| SIGNOUT-01 | An unconfigured issuer calls nothing and fails closed | unit | `uv run pytest tests/unit/test_firebase_adapter.py -q` | ✅ (add cases) |
| SIGNOUT-01 | A confirmed revocation answers 204 with an empty body | e2e | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | ❌ Wave 0 |
| SIGNOUT-01 | The route declares the linked-identity narrowing | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ (add path to both lists) |
| SIGNOUT-01 | The Protocol declares both methods | unit | `uv run pytest tests/unit/test_adapter_interfaces.py -q` | ✅ (rewrite literal) |
| SIGNOUT-02 | An exhausted budget raises `RevocationUnconfirmed`, never a success and never `RetryError` | unit | `uv run pytest tests/unit/test_firebase_retry.py -q` | ✅ (add cases) |
| SIGNOUT-02 | Each definitive outcome costs exactly one attempt | unit | `uv run pytest tests/unit/test_firebase_retry.py -q` | ✅ (add cases) |
| SIGNOUT-02 | A scripted `FirebaseError` answers 503 with the shared one-field body | e2e | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | ❌ Wave 0 |
| SIGNOUT-02 | No such user answers 401 (D-06) | e2e | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | ❌ Wave 0 |
| SIGNOUT-02 | The new leaf keeps the tree total | unit | `uv run pytest tests/unit/test_error_registry.py tests/unit/test_rejection_vocabulary.py -q` | ✅ (add event name) |
| D-07 | Exactly one INFO line on confirmation, carrying `identity_row_id` and never the subject | e2e | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | ❌ Wave 0 |
| D-04 | Barrier rejections are byte-identical to `/auth/sync`'s | e2e | `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** the named unit file(s) that task touched, e.g.
  `uv run pytest tests/unit/test_firebase_adapter.py tests/unit/test_firebase_retry.py -q`
- **Per wave merge:** `uv run pytest -q` and, for any wave touching the router,
  `uv run pytest -m e2e tests/e2e/test_sign_out_all.py -q`
- **Phase gate:** `uv run pytest -q && uv run pytest -m e2e -q && uv run pytest -m schema -q` all
  green before `/gsd:verify-work`

### Source assertions to pair with the pytest runs

Phase 45's plans paired every `<automated>` pytest command with a `test "$(grep -c ...)"` source
assertion, because a passing suite proves behaviour but not that the specific line was written
[VERIFIED: .planning/phases/45-post-auth-restore-subscription/45-02-PLAN.md:150,172,174]. The same
form applies here — each returns `0` today, so each is a real before/after:

```bash
test "$(grep -c 'def revoke_refresh_tokens' src/nativespeaker/api/auth/firebase.py)" = "1"
test "$(grep -c 'revoke_refresh_tokens' src/nativespeaker/api/auth/adapters.py)" = "1"
test "$(grep -c 'class RevocationUnconfirmed' src/nativespeaker/api/errors.py)" = "1"
test "$(grep -c 'auth/sign-out-all' src/nativespeaker/api/routers/auth.py)" = "1"
test "$(grep -c '/auth/sign-out-all' tests/unit/test_app_wiring.py)" = "2"
test "$(grep -c 'revocation_unconfirmed' tests/unit/test_rejection_vocabulary.py)" = "1"
```

Two assertions that must show **no** change, guarding the deletions:

```bash
test "$(grep -c 'get_db' src/nativespeaker/api/routers/auth.py)" = "2"   # unchanged: challenge only
test "$(grep -rc 'auth_events' src/nativespeaker/api/ | grep -v ':0' | wc -l)" = "0"
```

(Confirm the first number against the file at plan time; `get_db` appears in the import block and in
`issue_challenge` today.)

### Wave 0 Gaps

- [ ] `tests/e2e/test_sign_out_all.py` — covers SIGNOUT-01, SIGNOUT-02, D-04, D-06, D-07
- [ ] The logger spy fixture for that file, copied from `tests/e2e/test_app_store_webhook.py:70-101`
- [ ] Framework install: none — pytest, `pytest-asyncio` and the fixtures all exist

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | The shared barrier: `get_identity` then `get_linked_identity`; RS256 against cached Google securetoken keys; no re-verification in the handler |
| V3 Session Management | yes | Revocation at the IDP only. No backend token, session or generation counter — success criterion 4, and `SHARED-INVARIANTS.md` § "Tokens and sessions" |
| V4 Access Control | yes | Only a linked, active identity reaches the handler; no route-specific exception for blocked or retired subjects |
| V5 Input Validation | n/a | No request body, no query field, no path parameter. Nothing to validate. |
| V6 Cryptography | no | Nothing is signed, hashed or encrypted here. The HMAC actor-subject hashing the brief describes died with the audit writer (Phase 37.1 D-01). |
| V7 Error Handling & Logging | yes | One shared one-field body; the class name is the log event; provider text goes to the log and never to a body |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Reporting success on an ambiguous revocation | Repudiation | D-05: every unconfirmed outcome is one 503 leaf; the exhausted-budget callback is the tested chokepoint |
| Subject enumeration through the error surface | Information disclosure | One code and one status per class, and the body is a single `code` field [VERIFIED: errors.py:35-37] |
| Provider text reaching the client | Information disclosure | `ProviderLookupError.__init__` takes only `stage` and `cause`, "both of them ours"; the SDK's message goes to `logger.warning(... detail=...)` |
| The subject or a token in a log line | Information disclosure | D-07 logs `identity_row_id` only — the `UpgradeRefused` precedent, whose own comment says "the provider account uid is not admissible" |
| An unauthenticated caller costing a Firebase write | DoS | A valid Firebase ID token for a linked account is required first, so this is one subject looping on itself. Recorded as an uncounted divergence per D-09 on the Phase 40 D-22 precedent; the bound is the v2.1 gateway contract, deferred. |
| An issuer mismatch reaching an ambient Admin client | Spoofing | No `[DEFAULT]` app is ever created; selection is per call and `app=` is passed explicitly, asserted by `test_a_configured_issuer_passes_its_own_app_explicitly` |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `RevocationOutcome` value type on the seam | Exception classes; the seam returns nothing on success | Phase 37.2 D-09 / 37.3 D-12 | D-01 adds a method returning `None`, not a value type |
| `audit.auth_events` row per attempt | Middleware `request` line + one WARNING per rejection + D-07's INFO line | Phase 37.1 D-01, Phase 38 D-03/D-04 | Success criterion 3 is rewritten by D-09, not implemented |
| Route registry with per-route operation metadata | Router-level and route-level FastAPI dependencies; `tests/unit/test_app_wiring.py` is the structural replacement for the deleted startup assertion | Phase 37.1 D-06 | The route is registered like the other seven; the wiring lists are the inventory |
| Firebase service-account key file | Application Default Credentials | Phase 37.2 D-06…D-08 | An absent credential yields an empty apps dict at boot; the route fails closed as D-05 |
| Backend `limits` rate-limit engine | Deleted from the product | Phase 35 D-05 | The brief's rate-limit clauses are recorded as dead, never built |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Identity Toolkit answers `POST /accounts:update` for a non-existent `localId` with the backend code `USER_NOT_FOUND`, so D-06's 401 arm fires. The mapping table and the exception hierarchy are verified from the installed source; the backend's choice of code for this specific endpoint is corroborated only by an upstream issue report, not by a probe against a live project. | The SDK call, verified | D-06's `except auth.UserNotFoundError` arm never fires and a deleted account gets 503 for up to an hour. Cheap to settle: the e2e case scripts the exception directly, so the unit and e2e suites pass either way — the exposure is production-only. A real-credential probe against a deleted uid would settle it. |
| A2 | The `stage` strings on `RevocationUnconfirmed` are free choices with no consumer beyond the log line. | Error-tree facts | Low. `ProviderLookupError.log_fields()` is the only reader, and no test asserts a specific stage string for a new leaf. |
| A3 | The `get_db` count in `routers/auth.py` is 2 today (import + `issue_challenge`). | Validation Architecture | Low, and self-correcting: the plan author re-derives the number before writing the assertion. |

## Open Questions (RESOLVED)

Every question below carries a Recommendation, and every Recommendation was adopted by the plans.
Each `RESOLVED:` line names the plan and task that carries it.

1. **Does the phase take the generic-retry-wrapper discretion option?**
   - What we know: the two calls need different exhaustion leaves and different return types.
   - What's unclear: whether one wrapper taking a bound method plus a callback reads better than
     two near-identical functions, under `AGENTS.md` § "Function shape".
   - Recommendation: two wrappers. The generic one needs a comment at each call site to say which
     exhaustion leaf it will raise, which is precisely the § "Function shape" test for keeping the
     name — and here the name would be carrying *less* meaning, not more.
   - **RESOLVED: adopted in 46-01 Task 1** — `revoke_with_retry` and `_revocation_exhausted` are
     written beside `lookup_with_retry` and `_exhausted`, and the task says in words not to write one
     generic wrapper shared with the read. 46-03 Task 2 pins the separate exhaustion leaf by asserting
     the raised class is `RevocationUnconfirmed` and is not `Unavailable`.

2. **Does the phase rename `FirebaseAdminLookup`?**
   - What we know: the name is imprecise once it holds two calls. CONTEXT.md leaves it open and
     also lists the rename under Deferred if declined.
   - What's unclear: the blast radius. The name appears in `app/lifespan.py`,
     `tests/unit/test_firebase_adapter.py` and `tests/unit/test_firebase_retry.py`.
   - Recommendation: leave it. A rename adds churn to four files for no behavioural gain and
     CONTEXT.md already provides the deferred slot.
   - **RESOLVED: adopted in 46-01 Task 1** — the task instructs that the class name stays unchanged
     and the rename is deferred. No plan in this phase edits the name, and no plan touches
     `app/lifespan.py`.

3. **Is the session stand-in worth building?**
   - What we know: D-04 declares no `get_db`, and `tests/unit/test_app_wiring.py` already proves the
     declared dependency set.
   - Recommendation: skip it. `_declared(route)` in the wiring test names exactly the callables
     FastAPI resolved, so asserting `get_db not in _declared(route)` is a one-line case that proves
     the same property with none of the fixture cost.
   - **RESOLVED: adopted in 46-02 Task 2** — one case asserts
     `get_db not in _declared(_route_at("/auth/sign-out-all"))` and no stand-in fixture is built.
     46-01 Task 1 carries the matching source-side gate, a grep pinning the `get_db` count in
     `routers/auth.py` at two.

## Sources

### Primary (HIGH confidence)
- Installed `firebase-admin` 7.3.0 source at `.venv/lib/python3.14/site-packages/firebase_admin/` —
  `auth.py:290-311`, `_auth_client.py:142-161`, `_user_mgt.py:712-761`, `_auth_utils.py:86-93`,
  `:356-366`, `:429-444`, `_utils.py:201-231`, `_http_client.py:42-47`
- The repository tree, read this session — `src/nativespeaker/api/auth/firebase.py`,
  `auth/adapters.py`, `errors.py`, `app/dependencies.py`, `app/error_handlers.py`, `logs.py`,
  `routers/auth.py`, `routers/chats.py`, `crud/identities.py`, `app/lifespan.py`
- The test tree, read this session — `tests/unit/error_tree.py`, `test_error_registry.py`,
  `test_error_contract.py`, `test_rejection_vocabulary.py`, `test_adapter_interfaces.py`,
  `test_auth_package_shape.py`, `test_app_wiring.py`, `test_firebase_adapter.py`,
  `test_firebase_retry.py`, `test_docstring_bar.py`, `test_sync_audit_removal.py`, `conftest.py`;
  `tests/e2e/conftest.py`, `test_sync.py`, `test_app_store_webhook.py`, `test_restore_subscription.py`
- Measured suite runs this session: `uv run pytest -q`, `-m e2e -q`, `-m schema -q`
- `.planning/phases/46-post-auth-sign-out-all/46-CONTEXT.md`, `.planning/REQUIREMENTS.md`,
  `.planning/ROADMAP.md:754-765`, `.planning/STATE.md`,
  `.planning/phases/45-post-auth-restore-subscription/45-0*-PLAN.md`
- `/home/init/native-speaker/specs/auth-refactor-phases/11-sign-out-all.md`, `SHARED-INVARIANTS.md`
- `/home/init/native-speaker/ns-api-gateway/AGENTS.md`, `/home/init/native-speaker/AGENTS.md`

### Secondary (MEDIUM confidence)
- [github.com/firebase/firebase-admin-node/issues/550](https://github.com/firebase/firebase-admin-node/issues/550)
  — `revokeRefreshTokens` on a deleted user raises "There is no user record corresponding to the
  provided identifier"; corroborates A1 for the Node SDK against the same backend

### Tertiary (LOW confidence)
- None used.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency; every version read from `uv.lock` and the installed venv
- SDK behaviour: HIGH — read from the pinned installed source, except A1, which is MEDIUM
- Architecture: HIGH — every pattern quoted from the file it lives in, with line numbers
- Breaking tests: HIGH — each literal read and quoted this session
- Suite baselines: HIGH — measured, not recalled

**Research date:** 2026-09-08
**Valid until:** 2026-10-08 — the tree is the source of truth and moves only with this milestone;
re-measure the suite counts if any other phase lands first
