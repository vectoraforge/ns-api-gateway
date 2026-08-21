---
phase: 35-foundation
reviewed: 2026-08-21T12:05:00Z
depth: standard
files_reviewed: 69
files_reviewed_list:
  - config/config.yaml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/errors.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/audit.py
  - src/nativespeaker/api/auth/barrier.py
  - src/nativespeaker/api/auth/budgets.py
  - src/nativespeaker/api/auth/challenges.py
  - src/nativespeaker/api/auth/context.py
  - src/nativespeaker/api/auth/identity.py
  - src/nativespeaker/api/auth/__init__.py
  - src/nativespeaker/api/auth/keys.py
  - src/nativespeaker/api/auth/modesignal.py
  - src/nativespeaker/api/auth/registry.py
  - src/nativespeaker/api/auth/telemetry.py
  - src/nativespeaker/api/auth/verification.py
  - src/nativespeaker/api/auth/wire.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/database/__init__.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/models/api.py
  - src/nativespeaker/api/models/auth.py
  - src/nativespeaker/api/models/identities.py
  - src/nativespeaker/api/models/__init__.py
  - src/nativespeaker/api/models/users.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/__init__.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/__init__.py
  - tests/e2e/conftest.py
  - tests/e2e/test_audit_writer.py
  - tests/e2e/test_barrier_admission.py
  - tests/e2e/test_barrier_wire_contract.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_chat_queries.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_error_cases.py
  - tests/e2e/test_examples.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_isolation.py
  - tests/e2e/test_model_queries.py
  - tests/e2e/test_root.py
  - tests/e2e/test_startup_assertion.py
  - tests/unit/conftest.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_audit_details.py
  - tests/unit/test_audit_writer.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_barrier_wire_contract.py
  - tests/unit/test_budgets.py
  - tests/unit/test_challenge_ids.py
  - tests/unit/test_config.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_hmac_keys.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_identity_resolution.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_logging.py
  - tests/unit/test_models.py
  - tests/unit/test_mode_signal.py
  - tests/unit/test_route_registry.py
  - tests/unit/test_services.py
  - tests/unit/test_users.py
findings:
  critical: 1
  warning: 7
  info: 4
  total: 12
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-08-21T12:05:00Z
**Depth:** standard
**Files Reviewed:** 69
**Status:** issues_found

## Summary

Phase 35 delivers the auth barrier, the shared error registry, the typed identity context, the
keyed-hashing seam, the audit writer, and the challenge store. The admission ordering in
`auth/barrier.py` is correct as written: the wire contract genuinely precedes verification,
verification precedes resolution, and every rejection leaves through one `_reject` that records
telemetry and writes the audit row *before* awaiting the response. `resolve_identity` issues exactly
one statement per call against a `UNIQUE (issuer, subject)` key (confirmed in
`migrations/20260818_01_initial-release.sql`), so `.first()` cannot return the wrong row, and the
`isouter=True` pin is genuinely load-bearing. The redaction walk in `auth/audit.py` recurses through
mappings *and* sequences, and `build_details`' keyword-only signature really does make a seventh top
level key a `TypeError`. The 890 unit tests pass. Several tests are stronger than usual —
`test_challenge_ids.py::test_a_cleared_preauth_hash_is_not_compared_at_all` (exploding keyring) and
`test_audit_writer.py::TestTheBarriersAuditHook` (AST ordering) assert properties no input can
distinguish.

The defects are concentrated in two places the phase did not look at.

**The one blocker is in step 3.** `AuthBarrierMiddleware.__call__` calls `JWTVerifier.verify()` —
a *synchronous* function that performs blocking `urllib.request.urlopen` network I/O — directly on
the event loop. Any unauthenticated request carrying a JWT with an unrecognised `kid` forces
`PyJWKClient` to re-fetch the JWKS set, stalling the entire process. Measured below: three requests,
three fetches, one contiguous 1.2 s stall at a 0.4 s simulated round trip. The configured timeout is
PyJWT's 30 s default. This is not a rate-limiting gap (Envoy's job, deliberately) — a single request
is enough, and rate limiting cannot make a blocked event loop serve anyone.

**The rest are leaks and vacuous tests.** `validation_error_handler` writes raw request-body values
into the log through `exc_info`, which contradicts the redaction discipline the phase built
everywhere else. The `_digest` message encoding is ambiguous and, by the checkpoint's own
one-way-reversibility rule, permanently so. Three tests assert something that holds regardless of
the behaviour under test — one of them, `test_two_verifications_issue_no_additional_jwks_fetch`,
claims in its docstring precisely the property CR-01 violates, which is how the blocker survived
this phase.

Deliberate design decisions named in the phase context (no 403 in `STATUS_TO_CLASS`, `isouter=True`,
committed key material under D-20, Protocol-only seams, the `actor_subject_matches` indirection) were
verified as implemented and are **not** reported. Items already in `deferred-items.md`
(D-35-06-A, D-35-11-A, `actor_provider` NULL on rejections) are not duplicated.

## Critical Issues

### CR-01: The barrier performs blocking network I/O on the event loop; an unauthenticated request can stall the whole process

**File:** `src/nativespeaker/api/auth/barrier.py:113`, `src/nativespeaker/api/auth/verification.py:100-124`

**Issue:**
Step 3 of the barrier is a plain synchronous call from inside `async def __call__`:

```python
claims, reason = scope["app"].state.jwt_verifier.verify(token)
```

`JWTVerifier.verify` calls `self._jwks_client.get_signing_key_from_jwt(token)`. In PyJWT 2.12.1
(the installed version) that reads the **unverified** `kid` header and, on a cache miss, does:

```python
def get_signing_key(self, kid):
    signing_keys = self.get_signing_keys()
    signing_key = self.match_kid(signing_keys, kid)
    if not signing_key:
        signing_keys = self.get_signing_keys(refresh=True)   # bypasses the JWK-set cache
        ...
# fetch_data():
    with urllib.request.urlopen(r, timeout=self.timeout, context=self.ssl_context) as response:
```

`urlopen` is blocking. `JWTVerifier.__init__` never passes `timeout=`, so PyJWT's default of **30
seconds** applies. Three consequences, all reachable by an unauthenticated caller before any identity
work happens:

1. **Event-loop stall.** Nothing else in the process — no other request, no health probe, no
   in-flight LLM response — runs while `urlopen` blocks. Measured against the real `PyJWKClient`
   with a 0.4 s stubbed round trip:

   ```
   JWKS fetches triggered by 3 unauthenticated requests: 3
   longest event-loop stall (s): 1.206
   ```

   A slow or hung JWKS endpoint scales that to 30 s per request.
2. **No negative caching.** Every distinct `kid` re-fetches. An attacker sending random `kid`s gets
   one outbound HTTPS round trip per request, serialized on the loop.
3. **Outbound amplification** against Google's JWKS endpoint, attributable to this service.

This survives Envoy's rate limiting: rate limiting bounds *how many* such requests arrive, but one
request already blocks every concurrent caller, and the gateway cannot un-block an event loop.
`/health/ready` is served by the same loop, so a sustained trickle also fails the readiness probe and
can cascade into pod restarts.

The barrier's own docstring is explicit that step 4 opens one short session so that "no lock is held
and no network call is made while it is open" — step 3 makes exactly that network call, one line
earlier, and blocks harder than a session would.

**Fix:** Offload the verifier and bound the fetch. `verify` stays sync (D-01 needs it to return
rather than raise); only the call site changes:

```python
# barrier.py
from starlette.concurrency import run_in_threadpool
...
        # Step 3 -- verification. `verify` is synchronous and may perform a blocking JWKS fetch on
        # a `kid` miss, so it never runs on the event loop.
        claims, reason = await run_in_threadpool(scope["app"].state.jwt_verifier.verify, token)
```

```python
# verification.py -- bound the blocking call and stop unbounded refetching
    def __init__(self, *, jwks_url, audience, issuer, leeway=30, cache_ttl_seconds=3600,
                 fetch_timeout_seconds: float = 3.0):
        self._jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True,
                                        lifespan=cache_ttl_seconds,
                                        timeout=fetch_timeout_seconds)
```

Add a negative cache so a repeated unknown `kid` costs no fetch — a bounded
`{kid: monotonic_deadline}` dict checked before `get_signing_key_from_jwt`, or wrap the client so a
refresh runs at most once per `refresh_cooldown_seconds`. Pin it with a test that drives `verify`
against a `PyJWKClient` whose transport is stubbed and asserts the fetch count for N distinct unknown
`kid`s is bounded — see WR-05, which is the test that currently claims this property and does not
check it.

## Warnings

### WR-01: The barrier's 401 omits `WWW-Authenticate`, and is therefore distinguishable from the accessor's 401

**File:** `src/nativespeaker/api/auth/barrier.py:170`, `src/nativespeaker/api/errors.py:67-76`

**Issue:** `_reject` builds its response with `error_response(error_class)` and never passes
`headers`. Verified against the real middleware:

```
barrier 401: 401 {'code': 'auth_required'} | WWW-Authenticate: None
```

Two problems. RFC 7235 §3.1: *"The server generating a 401 response MUST send a WWW-Authenticate
header field."* Clients and gateways use that header to decide whether to refresh a token rather than
sign the user out. And `errors.AuthenticationError.extra_headers()` **does** return
`{"WWW-Authenticate": "Bearer"}`, so the 401 raised by `get_linked_identity` /
`get_preauth_identity` / `get_request_context` carries the header while the barrier's does not. Two
401s from one service that differ in headers is exactly the observable asymmetry §3.1's
anti-oracle rule closes for bodies. `test_barrier_admission.py::test_the_two_responses_are_identical_
in_status_body_and_headers` compares two 403s only, so nothing pins this.

**Fix:** Give the class its headers, so every emitter agrees:

```python
# errors.py -- a class may declare the headers its status requires
@dataclass(frozen=True, slots=True)
class ErrorClass:
    name: str
    status: int
    code: ErrorCode
    copy: str
    headers: tuple[tuple[str, str], ...] = ()

AUTH_REQUIRED = register_class(ErrorClass(..., headers=(("WWW-Authenticate", "Bearer"),)))

def error_response(cls, *, headers=None):
    merged = {**dict(cls.headers), **(headers or {})}
    return JSONResponse(status_code=cls.status,
                        content=ErrorResponse(code=cls.code).model_dump(),
                        headers=merged or None)
```

Then assert header equality between a barrier 401 and an accessor 401 in
`tests/unit/test_identity_accessors.py`.

### WR-02: `validation_error_handler` writes raw request-body values into the log

**File:** `src/nativespeaker/api/app/errors.py:38-40`

**Issue:**

```python
async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Validation error", exc_info=exc)
```

`RequestValidationError.__str__` renders every error dict, `input` value included. Confirmed:

```
fastapi.exceptions.RequestValidationError: 1 validation error:
  {'type': 'string_type', 'loc': ('body', 'challenge_id'), 'msg': 'Input should be a valid string',
   'input': 'SECRET-CHALLENGE-HANDLE-xyz'}
LEAKS: True
```

`setup_logging` installs `structlog.dev.plain_traceback`, so this reaches the log verbatim. Live
today: a `ChatRequest.phrase` or `MessageRequest.message` over the 4096-character limit puts the
user's entire submitted text in the operator's log — the private content of a grammar-fixing product.
It becomes a **§6 violation** the moment phases 37/40/41/42 add a `challenge_id` body field, because
§6.1 makes the handle a secret capability that "must never reach a URL, an audit row, a log, a trace,
analytics, or error text", and `auth/challenges.py` holds no logger precisely to make that
structural. This handler undoes it from two modules away.

Note the correct precedent one function up: `service_error_handler` passes
`exc_info=(exc.log_level >= logging.ERROR)`, so `AuthenticationError` (WARNING) logs no traceback.

**Fix:** Log the field paths, never the values:

```python
async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Never `exc_info`: RequestValidationError renders `input` -- the client's raw body -- into the
    # traceback. The locations identify the defect; the values are the caller's content and, from
    # phase 37, the secret challenge handle (§6.1).
    assert isinstance(exc, RequestValidationError)
    locations = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    logger.warning("validation_error", fields=sorted(set(locations)))
    return error_response(VALIDATION_ERROR)
```

Add a case in `tests/unit/test_exception_handlers.py` posting a body with a sentinel value and
asserting the sentinel appears in no captured log record.

### WR-03: `_digest` builds an ambiguous message; the encoding is pinned one-way

**File:** `src/nativespeaker/api/auth/keys.py:67-69`

**Issue:**

```python
def _digest(key: bytes, prefix: bytes, issuer: str, subject: str) -> bytes:
    return hmac.new(key, prefix + issuer.encode() + b":" + subject.encode(), hashlib.sha256).digest()
```

`":"` is not a reserved byte in either field. Issuers are URLs and *always* contain a colon
(`https://securetoken.google.com/...`), so the separator carries no separating power:
`(issuer="https://x.com", subject="a:b")` and `(issuer="https://x.com:a", subject="b")` produce a
byte-identical message and therefore an identical digest. Not exploitable today — `JWTVerifier` pins
one issuer, and `verify_binding` compares `preauth_issuer` in plaintext before consulting the hash —
but the seam is the shared derivation for `actor_subject_hash`, `preauth_subject_hash` and
`idp_account_hash`, and phase 41 is described as a "parallel family". The moment a second issuer is
configured, one provider's subject can collide with another's.

What makes this worth fixing now rather than later: `keys.py`'s own docstring pins the encoding as
**reversibility one-way** — "Once one `audit.auth_events` or `core.auth_challenges` row exists there
is no migration back, because the raw subject was never stored." An ambiguous encoding fixed after
the first row is written is not fixable at all.

**Fix:** Make the framing unambiguous with length prefixes, and bump the domain-separation version
so old and new digests are visibly different families:

```python
ACTOR_SUBJECT_PREFIX = b"actor-subject:v2:"
IDP_ACCOUNT_PREFIX = b"idp-account:v2:"

def _framed(value: str) -> bytes:
    """Length-prefixed, so no `issuer`/`subject` split can be re-read as another one."""
    raw = value.encode()
    return len(raw).to_bytes(4, "big") + raw

def _digest(key: bytes, prefix: bytes, issuer: str, subject: str) -> bytes:
    return hmac.new(key, prefix + _framed(issuer) + _framed(subject), hashlib.sha256).digest()
```

Add a case to `tests/unit/test_hmac_keys.py`:

```python
def test_the_issuer_subject_split_is_unambiguous(self):
    ring = keyring()
    assert (ring.actor_subject_hash("https://x.com", "a:b")
            != ring.actor_subject_hash("https://x.com:a", "b"))
```

### WR-04: `actor_subject_matches` silently pins the active key while audit rows record a version

**File:** `src/nativespeaker/api/auth/keys.py:140-164`

**Issue:** `actor_subject_hash` takes `version: int | None = None`; `actor_subject_matches` takes no
version and always recomputes under `self.active_version`:

```python
def actor_subject_matches(self, stored: bytes, issuer: str, subject: str) -> bool:
    return hmac.compare_digest(stored, self.actor_subject_hash(issuer, subject))
```

For the challenge store that is correct and documented (D-21: `core.auth_challenges` records no key
version). For `audit.auth_events` it is not: that table *does* carry
`actor_subject_hash_key_version`, precisely so a historical row can be recomputed under the key that
produced it. `actor_subject_matches` is exported from `nativespeaker.api.auth` as the one blessed
comparison and its docstring frames it generically — "the only comparison in the codebase that
touches keyed material" — with no hint that it answers `False` for any audit row written before the
last rotation. A phase-39 "show me this actor's audit history" query written against this seam
returns silently wrong results after any rotation, and `warn_missing_older` exists precisely because
older keys are expected to still be configured.

**Fix:** Mirror the derivation's signature and make the challenge store's choice explicit at its call
site:

```python
def actor_subject_matches(self, stored: bytes, issuer: str, subject: str, *,
                          version: int | None = None) -> bool:
    """Compare a stored hash against one recomputed under `version` (active when omitted).

    Pass the row's own `actor_subject_hash_key_version` for `audit.auth_events`.
    `core.auth_challenges` records no version, so the store omits it -- a rotation invalidates
    outstanding challenges by design (D-21).
    """
    return hmac.compare_digest(stored, self.actor_subject_hash(issuer, subject, version=version))
```

```python
# challenges.py::verify_binding -- unchanged behaviour, now stated rather than inherited
if not self._keyring.actor_subject_matches(row.preauth_subject_hash,
                                           identity.issuer, identity.subject,
                                           version=None):  # active key only, per D-21
```

### WR-05: `test_two_verifications_issue_no_additional_jwks_fetch` is vacuous, and asserts the property CR-01 breaks

**File:** `tests/unit/test_jwt_security.py:320-325`

**Issue:**

```python
def test_two_verifications_issue_no_additional_jwks_fetch(self, real_verifier, jwks_client):
    """§1.2: a request costs one local RSA verification and no per-request network call."""
    _, instance = jwks_client
    assert accepted(real_verifier, make_token("user-a")).subject == "user-a"
    assert accepted(real_verifier, make_token("user-b")).subject == "user-b"
    assert instance.get_signing_keys.call_count == 0
```

The whole `PyJWKClient` is a `MagicMock`, and `JWTVerifier.verify` calls
`get_signing_key_from_jwt` — a *different* mock attribute, stubbed to return `PUBLIC_KEY_PEM`
directly. `get_signing_keys` is therefore never called by the code under test under any
circumstances, and `call_count == 0` holds whatever the production code does. The real
`get_signing_key_from_jwt` is exactly the method that fetches; the mock replaces the behaviour being
asserted about. Both tokens also carry the same (absent) `kid`, so even a faithful client would not
exercise the miss path.

This is the load-bearing case: its docstring states "no per-request network call", which is the claim
CR-01 disproves, and its green result is why the blocker was not caught in-phase.

**Fix:** Stub the transport, not the client, and assert on the fetch count including the miss path:

```python
@pytest.fixture
def counted_transport(self, monkeypatch):
    """A real PyJWKClient over a counted stub of the one blocking call it makes."""
    calls = []
    def _urlopen(request, timeout=None, context=None):
        calls.append(timeout)
        return _jwks_response()          # io.BytesIO context manager over the test JWKS
    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    return calls

def test_a_repeated_unknown_kid_does_not_refetch_per_request(self, counted_transport):
    verifier = JWTVerifier(jwks_url="https://jwks.invalid/keys", audience=TEST_PROJECT_ID,
                           issuer=TEST_ISSUER)
    counted_transport.clear()
    for i in range(5):
        verifier.verify(make_token("u", headers={"kid": f"unknown-{i}"}))
    assert len(counted_transport) <= 1, "an unknown kid must not cost a JWKS fetch per request"

def test_the_blocking_fetch_carries_a_bounded_timeout(self, counted_transport):
    JWTVerifier(jwks_url="https://jwks.invalid/keys", audience=TEST_PROJECT_ID, issuer=TEST_ISSUER)
    assert counted_transport and all(t is not None and t <= 5 for t in counted_transport)
```

### WR-06: `test_the_previous_rows_were_rolled_back` asserts the absence of rows it never creates

**File:** `tests/e2e/test_model_queries.py:107-118`

**Issue:** The test asserts that `LEAKED_USER_ID` is absent, but the rows are written by the
*previous* test in the class (`test_user_and_identity_round_trip`) and rolled back by the
function-scoped `_db_transaction` fixture. Run alone (`pytest -k
test_the_previous_rows_were_rolled_back`), reordered, filtered, or with the preceding test skipped,
it passes without the isolation guarantee having been exercised at all — because nothing ever wrote
the rows. Its own docstring names the dependency ("Runs after the case above… Ordering is source
order, which pytest preserves"), which makes the coupling deliberate but does not make the assertion
non-vacuous: this is the module's only proof that e2e runs do not seed the developer's database, and
it is the one assertion that holds regardless of the behaviour under test.

**Fix:** Make it self-contained by writing through a factory whose transaction is under the test's
own control:

```python
async def test_rows_written_in_a_test_transaction_do_not_survive_it(self, _app_lifespan):
    """Self-contained: this case writes the row itself, so it cannot pass by not having run."""
    marker = uuid7()
    engine = _app_lifespan.state.session_factory.kw["bind"]
    async with engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(bind=connection, class_=SQLModelAsyncSession,
                                     expire_on_commit=False,
                                     join_transaction_mode="create_savepoint")
        async with factory() as session:
            session.add(User(id=marker))
            await session.commit()
        async with factory() as session:      # visible inside the transaction
            assert (await session.exec(select(User).where(User.id == marker))).first() is not None
        await transaction.rollback()

    async with _app_lifespan.state.session_factory() as session:   # gone outside it
        assert (await session.exec(select(User).where(User.id == marker))).first() is None
```

### WR-07: `test_exception_handlers.py::test_handler` never pins the exception-to-code mapping

**File:** `tests/unit/test_exception_handlers.py:70-83`

**Issue:**

```python
assert body["code"] in {
    "invalid_request", "auth_required", "not_found",
    "service_unavailable", "internal_error", "out_of_scope",
}
```

Sixteen exception classes are driven through the handler, and the code assertion is membership in a
six-element set. `OutOfScopeError` regressing to `invalid_request` passes (both are 400).
`UnsupportedLanguageError` regressing to `out_of_scope` passes. `DatabaseNotInitializedError`
regressing to `service_unavailable` fails only because the *status* differs. That matters more here
than usual: D-09/D-12 are this phase's central rework — the whole point was that the v1.6
`status_code`/`error_code` pair could disagree ("which is how `WebhookVerificationError` came to
carry the 422 code at status 400"), and the replacement is a single `error_class`. The test that
should prove each exception now lands on the right class checks only that it lands on *some* class.
`test_error_registry.py` covers the registry's internal totality and the framework-status mapping;
neither covers the per-exception mapping.

**Fix:** Put the expected code in the case table, next to the status:

```python
CASES = [
    ("missing_token",     AuthenticationError("Missing Bearer token"), 401, "auth_required"),
    ("db_not_init",       DatabaseNotInitializedError(),               500, "internal_error"),
    ("unsupported_lang",  UnsupportedLanguageError("fr", ["en"]),      400, "invalid_request"),
    ("out_of_scope",      OutOfScopeError(),                           400, "out_of_scope"),
    ...
]

@pytest.mark.parametrize("name,exc,expected_status,expected_code", CASES)
def test_handler(handler_client, name, exc, expected_status, expected_code):
    response = handler_client.get(f"/raise/{name}")
    assert response.status_code == expected_status
    assert response.json() == {"code": expected_code}
```

Note that `("unsupported_lang", ..., 400)` and `("out_of_scope", ..., 400)` becoming distinguishable
is the point: they share a status and must not share a code.

## Info

### IN-01: `assert result.all() is not None` asserts nothing

**File:** `tests/e2e/test_model_queries.py:47`, `tests/e2e/test_model_queries.py:52`

**Issue:** `Result.all()` returns a list and can never be `None`. The tests do carry real value — the
`await session.exec(...)` above them raises `UndefinedColumnError` on schema drift, which is the
documented purpose — but the assertion line implies a check that does not exist, and a reader
trimming "redundant" queries would leave the assertion behind and the module would go green on
nothing.

**Fix:** Drop the assertion and let the statement stand, matching the generalised case at line 65
which already does exactly that:

```python
async def test_select_user_executes(self, _db_transaction):
    """`UndefinedColumnError: column users.jwt_sub does not exist` before the repair.

    The `exec` is the assertion: it raises on schema drift. There is nothing to check about the
    rows, and an empty table is a legitimate result.
    """
    async with _db_transaction() as session:
        await session.exec(select(User))
```

### IN-02: Five `ServiceError` subclasses have no raise site, and the test suite exercises them

**File:** `src/nativespeaker/api/errors.py:327-339`, `src/nativespeaker/api/errors.py:364-365`, `src/nativespeaker/api/errors.py:396-407`

**Issue:** `grep` over `src/` finds zero raise sites for `InvalidCursorError`, `PageSizeLimitError`,
`QuotaExceededError`, `WebhookVerificationError`, and `DatabaseNotInitializedError` — D-16 deleted
the webhook and quota surfaces that raised them. `WebhookVerificationError`'s docstring still
describes "incoming webhook" handling that no longer exists. `test_exception_handlers.py::CASES`
drives four of the five, which inflates apparent handler coverage with paths no request can reach.
This is the same defect D-11 corrected for the retired `unauthorized` 401 code ("keeping both would
leave a code no branch reaches, which §3.1 forbids"), applied inconsistently. Some are genuinely
reserved (`quota_exceeded` for phase 36's grant work, per §8.3's "existing non-auth error contracts
unchanged"); nothing in the file distinguishes reserved from dead.

**Fix:** Add a one-line reservation comment naming the owning phase above each class that has no
current raise site, so the next reader can tell the two apart — and delete
`WebhookVerificationError` outright, since phase 43 "writes `/webhooks/app-store` and whatever
configuration it needs from scratch" and a stale class describing a deleted route is the drift D-16
was closing.

### IN-03: `RouteMetadata.quota_checked` is dead surface that contradicts a recorded decision

**File:** `src/nativespeaker/api/auth/registry.py:35`

**Issue:** `quota_checked: bool = False` is declared, never set by any registry entry, never read by
`assert_route_enumeration`, and never read by the barrier. `app/dependencies.py:98-100` records why:
"the named `quota_checked_request` admission entry §8.4 described is void because D-05 deleted
backend rate limiting from the product." The field is the last trace of a subsystem the phase
deliberately removed, and unlike `named_verifier` (which conditions 4 and 5 actively validate) or
`operation` (which condition 8 validates and the barrier reads), nothing enforces or consumes it.

**Fix:** Remove the field and record the removal where the sibling decisions are recorded:

```python
    named_verifier: str | None = None
    # No `quota_checked`: D-05 deleted backend rate limiting, which voids §8.4's
    # `quota_checked_request` admission entry. Phase 36 resolves allowance through the grant
    # (REBIND-05) and declares whatever metadata that needs.
```

### IN-04: `_bucket_kind` is derived twice per audited rejection

**File:** `src/nativespeaker/api/auth/barrier.py:142`, `src/nativespeaker/api/auth/barrier.py:207`

**Issue:** `__call__` computes `_bucket_kind(scope.get("client"))` for the admitted `RequestContext`,
and `_audit` computes it again for `details.context`. Two derivations of one request-scoped value
sits awkwardly beside the module's own rule that "one evaluation time and one attempt id per request"
exist so "two reads within one request can never straddle a period boundary" — the same argument
applies to any request-scoped derivation, and the second call site is the one a later phase would
edit without noticing the first.

**Fix:** Derive once at the top of `__call__`, beside `evaluated_at` and `attempt_id`, and thread it
through as a `_reject`/`_audit` parameter:

```python
        evaluated_at = datetime.now(UTC)
        attempt_id = uuid7()
        bucket_kind = _bucket_kind(scope.get("client"))   # one derivation per request, like the two above
```

---

_Reviewed: 2026-08-21T12:05:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
