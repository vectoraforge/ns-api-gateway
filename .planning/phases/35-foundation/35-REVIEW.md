---
phase: 35-foundation
reviewed: 2026-08-21T21:58:33Z
depth: standard
files_reviewed: 70
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
  - tests/unit/test_barrier_jwks_offload.py
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
  warning: 14
  info: 10
  total: 25
status: issues_found
---

# Phase 35: Code Review Report

**Reviewed:** 2026-08-21T21:58:33Z
**Depth:** standard
**Files Reviewed:** 70
**Status:** issues_found

## Summary

Re-review of the phase-35 foundation slice after 35-12 closed the previous round's CR-01. The
event-loop fix itself is verified good: `barrier.py:123` now goes through `run_in_threadpool`,
`test_barrier_jwks_offload.py` measures it with a real `PyJWKClient` over a stubbed transport and
carries a permanent negative control, and the fetch is bounded by an explicit `timeout=3.0` instead
of PyJWT's 30-second default. 906 unit tests pass.

The barrier's admission ordering re-verified clean: the §1.1 wire contract counts header *instances*
before inspecting any value, verification precedes resolution, resolution issues exactly one
statement, the session is closed before dispatch, and every rejection leaves through one `_reject`
that records telemetry and writes the audit row before awaiting the response. `redact()` recurses
through mappings and sequences. `BudgetGate.charge_all` really is all-or-nothing. An unmatched route
falls through to the router's own 404/405 without an unauthenticated 307, and `redirect_slashes` is
off.

**The blocker is in the fix.** 35-12 moved `JWTVerifier.verify` onto the anyio worker threadpool and,
in the same change, gave it mutable per-instance state — the negative-`kid` `OrderedDict`. That state
is mutated from every worker thread with no lock. Reproduced in seconds: `RuntimeError: OrderedDict
mutated during iteration` out of `_record_unknown`, plus a `KeyError` window in `_is_known_unknown`.
Neither is a `PyJWTError`, so both escape `verify` — whose Protocol contract is "Never raises" —
escape `run_in_threadpool`, and reach a barrier that catches nothing. Confirmed end to end: the
caller gets `500 {"code":"internal_error"}` where the design owes `401 {"code":"auth_required"}`. An
unauthenticated caller sending concurrent tokens with a bogus or absent `kid` triggers it, because
every absent `kid` collapses onto the one shared sentinel key.

Three further defects sit in the same 20 lines: `verify` is not total against non-PyJWT exceptions
(a non-JSON JWKS body reaches the barrier as a 500), the negative cache records a `kid` on a
*degraded-endpoint* error and can therefore blackhole every legitimate token for its TTL, and the
cache is per-`kid` and LRU-bounded at 256, so `kid` churn walks straight past it.

Outside the verifier, the material findings are configuration-shaped: a DSN built without
percent-encoding, config files read under the process locale while containing non-ASCII, a required
`JWT_API_KEY` no runtime code reads, and the committed HMAC key material (accepted as D-20, but it is
baked into the image by `COPY config ./config/` and, by explicit design, cannot be overridden by
environment).

Findings carried forward from the previous round were each re-verified against the current tree:
WR-04, WR-08, WR-09, WR-13, WR-14, IN-01..IN-04 still hold. The previous WR-05 (the vacuous
`get_signing_keys.call_count` test) is **gone** — 35-12 deleted it — and is not re-reported.
Deliberate decisions named in the phase context (no 403 in `STATUS_TO_CLASS`, `isouter=True`, the
`actor_subject_matches` indirection, Protocol-only seams, D-13's rejection of timing normalization)
were verified as implemented and are not reported. Items in `deferred-items.md` are not duplicated.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: The negative-`kid` cache is unsynchronized shared state on a multi-threaded path; an unauthenticated caller can turn a 401 into a 500

**File:** `src/nativespeaker/api/auth/verification.py:136`, `:157-181`, `:192-217`; reached from `src/nativespeaker/api/auth/barrier.py:123`

**Issue:**
35-12 made two changes at once: `verify` now runs on the anyio worker threadpool
(`await run_in_threadpool(...jwt_verifier.verify, token)`), and `verify` gained mutable instance
state (`self._unknown_kids: OrderedDict[str, float]`). Before the offload, `verify` ran on the event
loop and was single-threaded by construction. It is not any more — `run_in_threadpool` dispatches to
anyio's default 40-thread limiter, so concurrent requests execute `verify` on distinct OS threads
**simultaneously**, against one shared `OrderedDict`, with no lock anywhere.

Three unguarded check-then-act sequences:

```python
def _is_known_unknown(self, key: str) -> bool:
    deadline = self._unknown_kids.get(key)
    if deadline is None:
        return False
    if deadline <= time.monotonic():
        del self._unknown_kids[key]          # (1) two threads past the same check -> KeyError
        return False
    return True

def _record_unknown(self, key: str) -> None:
    ...
    for expired in [k for k, deadline in self._unknown_kids.items() if deadline <= now]:
        del self._unknown_kids[expired]      # (2) iteration + (3) delete, both racy
    ...
    while len(self._unknown_kids) > self._unknown_kid_cache_size:
        self._unknown_kids.popitem(last=False)   # (4) racy pop after a racy length check
```

Reproduced against the real class (8 threads, mixed sentinel and distinct keys, seconds to fire):

```
RACE REPRODUCED: RuntimeError OrderedDict mutated during iteration
  File ".../auth/verification.py", line 176, in _record_unknown
    for expired in [k for k, deadline in self._unknown_kids.items() if deadline <= now]:
```

`RuntimeError` and `KeyError` are not `PyJWTError`, so neither `except PyJWKClientError` nor
`except PyJWTError` catches them. They escape `verify` — violating the `TokenVerifier` Protocol's
"Never raises", which the whole D-01 return-don't-raise design rests on — escape
`run_in_threadpool`, and reach `AuthBarrierMiddleware.__call__`, which has no guard at step 3.
Confirmed end to end with a verifier that raises `KeyError("")` at exactly that seam:

```
status: 500 body: {"code":"internal_error"}
```

Reachability is not theoretical. `_cache_key_for` maps every absent, empty, or non-string `kid` onto
the single `_ABSENT_KID_SENTINEL = ""` key, so two concurrent kid-less tokens contend for the *same*
dict entry; and an attacker cycling distinct `kid` values keeps the dict large and the insert rate
high, which is exactly what makes window (2) wide. The caller needs no credential to get there —
step 3 runs before any identity work.

Impact: unauthenticated callers can drive 5xx error rates at will, the shared error contract is
violated (a 500 where §1.2 owes the identical `auth_required`), and the barrier's own invariant that
a rejection "returns rather than raises" no longer holds.

**Fix:** Give the cache a lock. It is the only mutable state on the threaded path, and every
operation on it is O(cache size), so a plain `threading.Lock` costs nothing measurable:

```python
import threading
...
        self._unknown_kids: OrderedDict[str, float] = OrderedDict()
        # `verify` runs on the anyio worker threadpool (barrier.py step 3), so every access below
        # is concurrent across OS threads. Unsynchronized, the expiry `del` races into a KeyError
        # and the sweep races into "OrderedDict mutated during iteration" -- neither is a
        # PyJWTError, so both escape `verify`, whose contract is that it never raises.
        self._unknown_kids_lock = threading.Lock()

    def _is_known_unknown(self, key: str) -> bool:
        now = time.monotonic()
        with self._unknown_kids_lock:
            deadline = self._unknown_kids.get(key)
            if deadline is None:
                return False
            if deadline <= now:
                self._unknown_kids.pop(key, None)
                return False
            return True

    def _record_unknown(self, key: str) -> None:
        if self._unknown_kid_ttl <= 0:
            return
        now = time.monotonic()
        with self._unknown_kids_lock:
            for expired in [k for k, d in list(self._unknown_kids.items()) if d <= now]:
                self._unknown_kids.pop(expired, None)
            self._unknown_kids[key] = now + self._unknown_kid_ttl
            self._unknown_kids.move_to_end(key)
            while len(self._unknown_kids) > self._unknown_kid_cache_size:
                self._unknown_kids.popitem(last=False)
```

Pin it with a case that hammers `verify` (or the two helpers) from `concurrent.futures.ThreadPoolExecutor`
with a mix of the sentinel key and distinct keys under a very short `unknown_kid_ttl_seconds`, and
asserts no exception escapes and every result is `(None, BoundedReason.bad_signature)`. Fix WR-01
as well: the lock closes this instance of the hole, a defensive catch closes the class of it.

## Warnings

### WR-01: `verify()` is not total — a non-JSON JWKS body reaches the client as a 500

**File:** `src/nativespeaker/api/auth/verification.py:198-222`

**Issue:** `verify` catches `PyJWKClientError` and `PyJWTError` only, on the stated reasoning that
"only PyJWT's own taxonomy is mapped". But PyJWT 2.12.1's `PyJWKClient.fetch_data` wraps only
`URLError`/`TimeoutError`:

```python
        try:
            with urllib.request.urlopen(r, timeout=self.timeout, ...) as response:
                jwk_set = json.load(response)
        except (URLError, TimeoutError) as e:
            ...raise PyJWKClientConnectionError(...)
```

`json.load` on a non-JSON body — a proxy error page, a captive-portal interception, a truncated
response — raises `json.JSONDecodeError` (a `ValueError`), which is *not* a `PyJWTError`. It escapes
`verify` exactly as the CR-01 race does, and produces the same `500 {"code":"internal_error"}` where
the contract owes `401 {"code":"auth_required"}`. The `TokenVerifier` Protocol docstring promises
"Never raises"; nothing enforces it.

**Fix:** Make the promise true at the seam that makes it, keeping the bounded reason
indistinguishable from every other verification failure:

```python
        except PyJWTError as exc:
            return None, bounded_reason_for(exc)
        except Exception:
            # `verify` never raises (D-01): the barrier is outside ExceptionMiddleware, so anything
            # escaping here is a 500 where the contract owes the identical `auth_required`. PyJWT
            # does not wrap every transport failure -- a non-JSON JWKS body surfaces as
            # json.JSONDecodeError -- so the catch is by contract, not by taxonomy.
            logger.exception("jwt_verification_error")
            return None, BoundedReason.bad_signature
```

(The module currently holds no logger; add one, or drop the log line — the return value is the
load-bearing half.)

### WR-02: The negative cache records a `kid` on a *degraded-endpoint* error, blackholing every legitimate token for the TTL

**File:** `src/nativespeaker/api/auth/verification.py:209-218`

**Issue:** The carve-out is `not isinstance(exc, PyJWKClientConnectionError)`, on the stated reasoning
that anything else "means the key id is bogus". That is not what the exception taxonomy says.
`PyJWKClient.get_signing_keys` raises a plain `PyJWKClientError` when the fetched document contains
no *usable* signing keys, and `get_jwk_set` raises one when the endpoint did not return a JSON object:

```python
        if not signing_keys:
            raise PyJWKClientError("The JWKS endpoint did not contain any signing keys")
...
        if not isinstance(data, dict):
            raise PyJWKClientError("The JWKS endpoint did not return a JSON object")
```

Both are *endpoint* conditions, both are recorded as if the `kid` were bogus. Every legitimate token
in the fleet carries the same one or two `kid`s, so one such response poisons that `kid` and rejects
**all** authenticated traffic for `unknown_kid_ttl_seconds` — including after the endpoint recovers.
That is precisely the "outage amplifier" the comment above the branch says it is avoiding; the
carve-out is just too narrow. Compounding it, PyJWT clears its own JWK-set cache on any failed fetch
(`fetch_data`'s `finally: self.jwk_set_cache.put(jwk_set)` with `jwk_set is None`), so the recovery
path has no warm cache to fall back on.

**Fix:** Record only the definitive miss — the one PyJWT raises *after* a successful refresh failed
to match:

```python
_DEFINITIVE_KID_MISS = "Unable to find a signing key that matches"

        except PyJWKClientError as exc:
            # Record only the definitive "refreshed, still no match" case. A connection failure, an
            # empty signing-key list, and a non-JSON document are all *endpoint* conditions: caching
            # them against a kid every legitimate token shares would reject the whole fleet for the
            # TTL, and keep rejecting it after the endpoint recovered.
            if cache_key is not None and _DEFINITIVE_KID_MISS in str(exc):
                self._record_unknown(cache_key)
            return None, bounded_reason_for(exc)
```

Add a case per endpoint-failure shape (connection error, `{"keys": []}`, non-JSON body) asserting
that a subsequent request for the *same* `kid` still reaches the transport.

### WR-03: `kid` churn walks past the negative cache — one outbound JWKS fetch and one worker thread per unauthenticated request

**File:** `src/nativespeaker/api/auth/verification.py:131-142`, `:180-181`

**Issue:** The cache is keyed per `kid` and bounded to 256 entries with insertion-order eviction. An
unauthenticated caller that never repeats a `kid` therefore never hits it: each request takes
`get_signing_key_from_jwt` -> `get_signing_keys(refresh=True)` -> one outbound HTTPS round trip to
Google (up to `fetch_timeout_seconds`, 3 s), and holds one of anyio's 40 default worker threads for
the duration. ~40 concurrent such requests exhaust the threadpool; the event loop keeps serving (the
CR-01 fix holds and `/health/ready` still answers), but *every* legitimate verification queues behind
them, and the service issues one attributable outbound fetch per attacker request.

The comment at `:137-142` states the guarantee too strongly — "An unrecognized one costs at most one
bounded, off-loop fetch for the life of its negative-cache entry" — which is true per `kid` and false
per request. Envoy bounds a single-source flood; it does not bound a distributed one, and it cannot
make the 257th distinct `kid` cheap.

**Fix:** Bound the *refresh*, not just the `kid`. A single global cooldown makes the cost independent
of how many distinct `kid`s an attacker invents:

```python
        self._refresh_cooldown = refresh_cooldown_seconds   # e.g. 10.0
        self._next_refresh_allowed = 0.0

    def _may_refresh(self) -> bool:
        """One JWKS refresh per cooldown, whatever `kid` asked for it.

        The per-kid negative cache is bypassed by simply never repeating a kid; this is not, because
        the budget is global. A real rotation is picked up within one cooldown.
        """
        with self._unknown_kids_lock:
            now = time.monotonic()
            if now < self._next_refresh_allowed:
                return False
            self._next_refresh_allowed = now + self._refresh_cooldown
            return True
```

Consult it before `get_signing_key_from_jwt` when `_cache_key_for` returns a `kid` absent from the
*cached* key set, and return `(None, BoundedReason.bad_signature)` when it refuses. Extend
`test_barrier_jwks_offload.py` with a case that drives N > cache-size distinct `kid`s and asserts
`len(transport)` stays bounded.

### WR-04: `validation_error_handler` writes raw request-body values into the log

**File:** `src/nativespeaker/api/app/errors.py:38-40`

**Issue:** (Carried from the previous round; re-verified against the current tree — unchanged.)

```python
async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Validation error", exc_info=exc)
```

`RequestValidationError.__str__` renders every error dict, `input` included, and `setup_logging`
installs `structlog.dev.plain_traceback`, so it reaches the log verbatim. Reproduced against the real
handler and the real logging pipeline:

```
LEAKS challenge value: True
LEAKS user text: True
fastapi.exceptions.RequestValidationError: 2 validation errors:
  {'type': 'string_type', 'loc': ('body', 'challenge_id'), ..., 'input': 12345}
  {'type': 'string_too_long', 'loc': ('body', 'phrase'), ..., 'input': 'SECRET-USER-TEXT-abcdef'}
```

Live today, an over-length `ChatRequest.phrase` puts the user's submitted text in the operator's log —
the private content of a grammar-fixing product. It becomes a §6 violation the moment phases
37/40/41/42 add a `challenge_id` body field: `auth/challenges.py` deliberately holds no logger so
that "the raw malformed identifier is never logged" is structural, and this handler undoes it from
two modules away. The correct precedent is one function up — `service_error_handler` passes
`exc_info=(exc.log_level >= logging.ERROR)`.

**Fix:** Log the field paths, never the values:

```python
async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Never `exc_info`: RequestValidationError renders `input` -- the client's raw body -- into the
    # traceback. Locations identify the defect; values are the caller's content and, from phase 37,
    # the secret challenge handle (§6.1).
    assert isinstance(exc, RequestValidationError)
    locations = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    logger.warning("validation_error", fields=sorted(set(locations)))
    return error_response(VALIDATION_ERROR)
```

Pin it in `tests/unit/test_exception_handlers.py` with a sentinel body value asserted absent from
every captured record.

### WR-05: The barrier's 401 omits `WWW-Authenticate`; the accessor's 401 carries it

**File:** `src/nativespeaker/api/auth/barrier.py:180`, `src/nativespeaker/api/errors.py:67-76`, `:392-393`

**Issue:** (Carried; re-verified.) `_reject` builds `error_response(error_class)` with no `headers`,
while `errors.AuthenticationError.extra_headers()` returns `{"WWW-Authenticate": "Bearer"}` and
`service_error_handler` forwards it. So the same `auth_required` class is emitted two ways that
differ observably. RFC 9110 §11.6.1 requires the header on a 401, and clients use it to decide
between "refresh the token" and "sign the user out". `test_barrier_admission.py` compares two 403s
only; nothing pins the 401 headers.

**Fix:** Attach the headers to the class so every emitter agrees:

```python
@dataclass(frozen=True, slots=True)
class ErrorClass:
    name: str
    status: int
    code: ErrorCode
    copy: str
    headers: tuple[tuple[str, str], ...] = ()

AUTH_REQUIRED = register_class(ErrorClass(..., headers=(("WWW-Authenticate", "Bearer"),)))

def error_response(cls: ErrorClass, *, headers: dict[str, str] | None = None) -> JSONResponse:
    merged = {**dict(cls.headers), **(headers or {})}
    return JSONResponse(status_code=cls.status,
                        content=ErrorResponse(code=cls.code).model_dump(),
                        headers=merged or None)
```

Then assert header equality between a barrier 401 and an accessor 401.

### WR-06: `DatabaseConfig.url` does not percent-encode credentials — a password with `@` or `/` silently retargets the connection

**File:** `src/nativespeaker/api/config.py:34-37`

**Issue:**

```python
    @property
    def url(self) -> str:
        return (f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
                f"@{self.host}:{self.port}/{self.name}")
```

`user`, `password`, `host` and `name` are interpolated raw. Generated database passwords routinely
contain `@`, `/`, `:` and `#`. Demonstrated with SQLAlchemy's own parser for
`DB_PASSWORD=p@ss/w0rd`, `DB_HOST=db.internal`, `DB_NAME=ns`:

```
parsed host= ss  user= appuser  password= p  db= w0rd@db.internal:5432/ns  port= None
```

The engine is built against a host, port and database nobody configured. In the best case startup
fails with a confusing DNS error; in the worst case the parsed host resolves to something real. The
failure is silent at config-validation time because `url` is a plain f-string.

**Fix:** Build the URL with the library that owns the grammar, or quote:

```python
from urllib.parse import quote

    @property
    def url(self) -> str:
        # Credentials are percent-encoded: a generated password containing '@', '/' or ':' is
        # otherwise re-parsed as host/port/database (verified: 'p@ss/w0rd' yields host='ss').
        return (f"postgresql+asyncpg://{quote(self.user, safe='')}:"
                f"{quote(self.password.get_secret_value(), safe='')}"
                f"@{self.host}:{self.port}/{self.name}")
```

Add a `tests/unit/test_config.py` case asserting `make_url(cfg.url)` round-trips a password
containing `@`, `/` and `:`.

### WR-07: Config, prompt and examples are read under the process locale while containing non-ASCII

**File:** `src/nativespeaker/api/config.py:107-116`

**Issue:**

```python
        yaml_data = yaml.safe_load(config_path.read_text())
        self.app_config = AppConfig(**yaml_data,
                                    prompt=prompt_path.read_text(),
                                    examples=yaml.safe_load(examples_path.read_text()))
```

`Path.read_text()` with no `encoding` uses `locale.getpreferredencoding(False)`. All three files
contain non-ASCII today (`config.yaml` 1 line, `prompt.txt` 4 lines, `examples.yaml` 6 lines). PEP
538/540 coercion saves the common `LANG` unset / `C` case, but a container that sets a non-UTF-8
`LANG` (or a base image that ships one) either crashes at startup with `UnicodeDecodeError` or —
worse, for a latin-1-family locale — decodes silently wrong and feeds a mojibake system prompt into
every LLM call. Nothing about that is visible in logs or tests.

**Fix:** State the encoding; the files are ours and they are UTF-8:

```python
        yaml_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.app_config = AppConfig(**yaml_data,
                                    prompt=prompt_path.read_text(encoding="utf-8"),
                                    examples=yaml.safe_load(examples_path.read_text(encoding="utf-8")))
```

### WR-08: `_digest` builds an ambiguous message, and the encoding is pinned one-way

**File:** `src/nativespeaker/api/auth/keys.py:67-69`

**Issue:** (Carried; re-verified — independently confirmed.)

```python
def _digest(key: bytes, prefix: bytes, issuer: str, subject: str) -> bytes:
    return hmac.new(key, prefix + issuer.encode() + b":" + subject.encode(), hashlib.sha256).digest()
```

`":"` is not reserved in either field, and issuers are URLs that always contain one. So
`(issuer="https://x.com", subject="a:b")` and `(issuer="https://x.com:a", subject="b")` produce a
byte-identical message and an identical digest. Not reachable today — one issuer is pinned by
`JWTVerifier` and `verify_binding` compares `preauth_issuer` in plaintext first — but this is the
shared derivation behind `actor_subject_hash`, `preauth_subject_hash` and phase 41's
`idp_account_hash`, and the module's own docstring pins the encoding as **reversibility one-way**:
"Once one `audit.auth_events` or `core.auth_challenges` row exists there is no migration back". An
ambiguous encoding fixed after the first row is written is not fixable at all.

**Fix:** Length-prefix both fields and bump the domain-separation version so the two families are
visibly distinct:

```python
ACTOR_SUBJECT_PREFIX = b"actor-subject:v2:"
IDP_ACCOUNT_PREFIX = b"idp-account:v2:"

def _framed(value: str) -> bytes:
    """Length-prefixed, so no (issuer, subject) split can be re-read as another one."""
    raw = value.encode()
    return len(raw).to_bytes(4, "big") + raw

def _digest(key: bytes, prefix: bytes, issuer: str, subject: str) -> bytes:
    return hmac.new(key, prefix + _framed(issuer) + _framed(subject), hashlib.sha256).digest()
```

```python
def test_the_issuer_subject_split_is_unambiguous(self):
    ring = keyring()
    assert (ring.actor_subject_hash("https://x.com", "a:b")
            != ring.actor_subject_hash("https://x.com:a", "b"))
```

### WR-09: `actor_subject_matches` silently pins the active key while audit rows record a version

**File:** `src/nativespeaker/api/auth/keys.py:140-164`

**Issue:** (Carried; re-verified.) `actor_subject_hash` accepts `version: int | None = None`;
`actor_subject_matches` accepts none and always recomputes under `self.active_version`. For
`core.auth_challenges` that is correct and documented (D-21: no version column). For
`audit.auth_events` it is not — that table carries `actor_subject_hash_key_version` precisely so a
historical row can be recomputed under the key that produced it, and `warn_missing_older` exists
because older keys are expected to remain configured. The method is exported from
`nativespeaker.api.auth` as the one blessed comparison, with a docstring that frames it generically,
so a later phase reconciling audit history gets silent `False`s for every row written before the last
rotation.

**Fix:**

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

and make the store's choice explicit at its call site (`challenges.py::verify_binding`,
`version=None  # active key only, per D-21`).

### WR-10: `JWTConfig.api_key` is a required production credential that no runtime code reads

**File:** `src/nativespeaker/api/config.py:53-54`, consumed only at `tests/e2e/conftest.py:35`

**Issue:** `api_key: str` has no default, so it is mandatory at startup. Verified — with every other
variable present and `JWT_API_KEY` removed:

```
STARTUP FAILS WITHOUT JWT_API_KEY: ValidationError
jwt.api_key
  Field required [type=missing]
```

`grep` over `src/` finds exactly one reference: the field declaration. Its only consumer is the e2e
fixture that signs a test user in through the Identity Toolkit REST API. So every deployment must
provision a live GCP API key into the production environment for a code path the service does not
have — an avoidable secret in the deployment surface and an avoidable boot failure mode, in a phase
whose stated posture is normal security measures without over-engineering.

**Fix:** Move it out of the runtime config and into the test environment:

```python
class JWTConfig(BaseModel):
    project_id: str = Field(description="GCP project ID")
    # No `api_key`: nothing in src/ reads one. The e2e Firebase sign-in helper reads
    # FIREBASE_TEST_API_KEY from the environment directly -- a test credential does not belong in
    # the config the production deployment must satisfy.
```

and in `tests/e2e/conftest.py`, `api_key = os.environ["FIREBASE_TEST_API_KEY"]`.

### WR-11: Live HMAC key material is committed, image-baked, and un-overridable by environment

**File:** `config/config.yaml:34-39`

**Issue:** The `hmac.keys` and `hmac.idp_account_keys` base64 values are real 32-byte keys in a
git-tracked file, `Dockerfile` does `COPY config ./config/`, and — by explicit design recorded in the
file itself — `AppConfig(**yaml_data, ...)` ranks `init_settings` above `env_settings`, so **no
environment variable can override them**. The only way to deploy different material is to edit the
tracked file, which means the default path for any production rollout is to ship the committed key.

This is recorded and accepted (D-20) with a tracked mitigation
(`.planning/todos/pending/secret-manager-integration.md`), which is why it is a warning rather than a
blocker for this phase. The residual risk is worth stating precisely so the follow-up is not deferred
past the first deploy: these keys derive `actor_subject_hash` and `preauth_subject_hash`, so anyone
with read access to the repository (or to any image layer) can recompute the hash of any subject they
can guess and thereby de-anonymize `audit.auth_events` and `core.auth_challenges` — the exact property
those columns exist to provide. Rotation does not repair it; git history keeps the predecessor.

**Fix:** Before the first production deploy, remove the entries from the YAML (do not shadow them),
make the source explicit, and let the fail-closed D-22 path do its job when the secret is absent:

```yaml
hmac:
  active_version: 1
  # Key material is NOT declared here. YAML ranks above env, so an entry here cannot be overridden
  # and would become the production key. Supply HMAC_KEYS / HMAC_IDP_ACCOUNT_KEYS from the secret
  # manager; a missing active key fails configuration load closed (D-22).
```

Verify the env path resolves (`env_nested_delimiter`/`env_nested_max_split` must reach
`hmac.keys`) and add a startup-time check that the active key did not come from a tracked file.

### WR-12: `GET /chats/{chat_id}` documents chronological order and returns reverse-chronological

**File:** `src/nativespeaker/api/routers/chats.py:30-43` (cause: `src/nativespeaker/api/database/chats.py:45`)

**Issue:** The route's OpenAPI description is "Returns all messages in a chat session, ordered
chronologically." The query behind it is

```python
            .order_by(col(Message.id).desc())
```

and `Message.id` is `uuid7`, which is time-ordered — so `.desc()` is newest-first. There is no
pagination or limit that would justify descending order; the full transcript comes back reversed, and
a client rendering it in order shows the conversation backwards. No test asserts the order: the e2e
chat cases check status codes and payload shape only, and `test_chat_queries.py` never inspects
sequence.

**Fix:** Order ascending and pin it:

```python
            .order_by(col(Message.id).asc())   # uuid7 is time-ordered: chronological, as documented
```

```python
async def test_messages_come_back_in_send_order(...):
    body = (await async_client.get(f"/chats/{chat_id}")).json()
    assert [m["role"] for m in body] == ["human", "ai"]
```

If newest-first was intended, change the description instead — but pick one, and test it.

### WR-13: `test_exception_handlers.py::test_handler` never pins the exception-to-code mapping

**File:** `tests/unit/test_exception_handlers.py:70-83`

**Issue:** (Carried; re-verified — unchanged.) Sixteen exception classes are driven through the
handler and the code assertion is membership in a six-element set:

```python
    assert body["code"] in {
        "invalid_request", "auth_required", "not_found",
        "service_unavailable", "internal_error", "out_of_scope",
    }
```

`OutOfScopeError` regressing to `invalid_request` passes (same status). `UnsupportedLanguageError`
regressing to `out_of_scope` passes. That matters more than usual here: D-09/D-12 replaced the v1.6
`status_code`/`error_code` pair precisely because the two could disagree, and the test that should
prove each exception lands on the right class checks only that it lands on *some* class.

**Fix:** Put the expected code in the case table beside the status and assert the whole body:

```python
CASES = [
    ("missing_token",    AuthenticationError("Missing Bearer token"), 401, "auth_required"),
    ("db_not_init",      DatabaseNotInitializedError(),               500, "internal_error"),
    ("unsupported_lang", UnsupportedLanguageError("fr", ["en"]),      400, "invalid_request"),
    ("out_of_scope",     OutOfScopeError(),                           400, "out_of_scope"),
    ...
]

@pytest.mark.parametrize("name,exc,expected_status,expected_code", CASES)
def test_handler(handler_client, name, exc, expected_status, expected_code):
    response = handler_client.get(f"/raise/{name}")
    assert response.status_code == expected_status
    assert response.json() == {"code": expected_code}
```

### WR-14: `test_the_previous_rows_were_rolled_back` asserts the absence of rows it never creates

**File:** `tests/e2e/test_model_queries.py:106-118`

**Issue:** (Carried; re-verified — unchanged.) The rows it looks for are written by the *previous*
test in the class and rolled back by the function-scoped `_db_transaction` fixture. Run alone,
reordered, filtered by `-k`, or with the preceding case skipped, it passes without the isolation
guarantee ever having been exercised — nothing wrote the rows. It is the module's only proof that e2e
runs do not seed the developer's database, and it is the one assertion that holds regardless of the
behaviour under test.

**Fix:** Make it self-contained — write the row inside a transaction the case itself controls, assert
it is visible inside and gone outside:

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
        async with factory() as session:
            assert (await session.exec(select(User).where(User.id == marker))).first() is not None
        await transaction.rollback()
    async with _app_lifespan.state.session_factory() as session:
        assert (await session.exec(select(User).where(User.id == marker))).first() is None
```

## Info

### IN-01: `assert result.all() is not None` asserts nothing

**File:** `tests/e2e/test_model_queries.py:47`, `:52`

**Issue:** `Result.all()` returns a list and can never be `None`. The cases do carry value — the
`await session.exec(...)` above raises `UndefinedColumnError` on schema drift — but the assertion
implies a check that does not exist, and a reader trimming the "redundant" query would leave a
green test asserting nothing.

**Fix:** Drop the assertion and let the `exec` stand, matching the generalised case at line 65 which
already does exactly that.

### IN-02: Five `ServiceError` subclasses have no raise site, and the test suite exercises four of them

**File:** `src/nativespeaker/api/errors.py:327-339`, `:364-365`, `:396-407`

**Issue:** No raise site anywhere in `src/` for `InvalidCursorError`, `PageSizeLimitError`,
`QuotaExceededError`, `WebhookVerificationError`, `DatabaseNotInitializedError`.
`WebhookVerificationError`'s docstring still describes webhook handling D-16 deleted. Some are
genuinely reserved (`quota_exceeded` for phase 36); nothing in the file distinguishes reserved from
dead, which is the defect D-11 corrected for the retired `unauthorized` code.

**Fix:** One reservation comment naming the owning phase above each class with no current raise site,
and delete `WebhookVerificationError` — phase 43 writes `/webhooks/app-store` from scratch.

### IN-03: `RouteMetadata.quota_checked` is dead surface that contradicts a recorded decision

**File:** `src/nativespeaker/api/auth/registry.py:35`

**Issue:** Declared, never set by any entry, never read by `assert_route_enumeration`, never read by
the barrier. `app/dependencies.py:98-100` records why: D-05 deleted backend rate limiting, voiding
§8.4's `quota_checked_request` admission entry. Unlike `named_verifier` (conditions 4/5) and
`operation` (condition 8), nothing validates or consumes it.

**Fix:** Remove the field; leave the sibling-style comment recording that phase 36 declares whatever
allowance metadata the grant needs.

### IN-04: `_bucket_kind` is derived twice per audited rejection

**File:** `src/nativespeaker/api/auth/barrier.py:152`, `:217`

**Issue:** `__call__` derives it for the admitted `RequestContext`; `_audit` derives it again for
`details.context`. Two derivations of one request-scoped value sit awkwardly beside the module's own
"one evaluation time and one attempt id per request" rule, and the second site is the one a later
phase edits without noticing the first.

**Fix:** Derive once beside `evaluated_at`/`attempt_id` and thread it through `_reject`/`_audit`.

### IN-05: `AppConfig.json_log_path` is declared and never read

**File:** `src/nativespeaker/api/config.py:79`

**Issue:** `json_log_path: str | None` describes "Path for JSON log file output"; `setup_logging`
takes a `log_stream` and no path, and `grep` finds no other reference. An operator setting
`JSON_LOG_PATH` gets silence.

**Fix:** Delete the field, or wire it into `setup_logging` and test it.

### IN-06: `ErrorClass.copy` never reaches a client

**File:** `src/nativespeaker/api/errors.py:39-46`, `:67-76`

**Issue:** Every registered class carries carefully neutral `copy`, `ErrorResponse` has exactly one
field (`code`), and `error_response` emits only that. The single reference to `.copy` in the whole
repository is `test_error_registry.py:98` asserting it is non-empty. Either it is documentation
living in the wrong place, or a client-facing requirement that was never wired.

**Fix:** Say which, in one line above the field — e.g. "not serialized: §3.1 pins the body to `code`
alone; this is the copy clients render locally, kept here so status/code/copy cannot drift."

### IN-07: Exception handlers use `assert` for runtime type narrowing

**File:** `src/nativespeaker/api/app/errors.py:29`, `:51`

**Issue:** `assert isinstance(exc, ServiceError)` / `assert isinstance(exc, StarletteHTTPException)`
are stripped under `python -O`, in which case a mis-registered handler raises `AttributeError`
*inside* the error path — the one place an exception is most expensive.

**Fix:** Narrow with an explicit branch that falls back to `INTERNAL_ERROR`, or accept the typed
parameter and keep the `# ty: ignore` convention already used in `main.py`.

### IN-08: `write_in_transaction` swallows a failed flush and returns as if the row were written

**File:** `src/nativespeaker/api/auth/audit.py:305-309`

**Issue:** Deliberate and tested
(`test_audit_writer.py::test_a_failing_flush_is_logged_and_not_re_raised`), and correct for
`write_standalone` where there is nothing to be atomic with. In the in-transaction mode the effect is
different: a failed flush marks the caller's transaction rollback-only, so the caller's *next*
statement raises `PendingRollbackError` attributed to itself rather than to the audit row. Atomicity
survives — the state change cannot commit without the row — but the failure surfaces at the wrong
site, and the `-> None` signature gives phases 37-45 no success signal.

**Fix:** Log and re-raise in `write_in_transaction` (the caller owns the transaction this row
describes), keeping the swallow in `write_standalone`.

### IN-09: `os.environ.setdefault("FIREBASE_TEST_USER_ID", ...)` lets a stale environment win

**File:** `tests/e2e/conftest.py:50`

**Issue:** `setdefault` keeps a pre-existing exported value in preference to the `localId` just
returned by Firebase. If one is left over in a shell or CI environment, `test_user_id` returns a
subject that does not match the token, `linked_firebase_identity` seeds the wrong pair, and every
admission case fails with a confusing 403.

**Fix:** `os.environ["FIREBASE_TEST_USER_ID"] = data["localId"]` — the fixture that fetched the token
is the authority for its subject.

### IN-10: Readiness never checks readiness, and the engine leaks on a failed lifespan

**File:** `src/nativespeaker/api/app/lifespan.py:70-95`

**Issue:** Two small things in one place. `create_async_engine` is built at `:70`, but any exception
raised between there and `yield` skips the `await db_engine.dispose()` at `:95`, leaking the pool on
a crashing start. And nothing in the lifespan opens a connection, while `/health/ready` returns
`{"status": "up"}` unconditionally — so Kubernetes routes traffic to a pod whose database is
unreachable, and every request answers 500 instead of the probe failing.

**Fix:** Wrap the post-engine setup in `try/except` with `await db_engine.dispose(); raise`, and give
the lifespan one `SELECT 1` so an unreachable database fails the boot the way an unreachable JWKS
endpoint already does.

---

_Reviewed: 2026-08-21T21:58:33Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
