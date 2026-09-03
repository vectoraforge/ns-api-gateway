# Phase 41: POST /auth/claim-anonymous-grant - Research

**Researched:** 2026-09-02
**Domain:** Apple DeviceCheck server-to-server integration + a locked multi-row grant activation transaction, on an existing FastAPI/SQLModel/PostgreSQL auth stack
**Confidence:** MEDIUM (HIGH on everything in this repo, read this session; LOW on Apple's wire format, which no official page could be fetched for)

## Summary

Almost nothing here is a technology choice. Every library this phase needs is already installed and already used by a sibling: `PyJWT[crypto]` signs the ES256 service JWT, `httpx` makes the HTTPS call, `tenacity` bounds the retry exactly as `auth/firebase.py::lookup_with_retry` does, and `SQLModel`/`asyncpg` carry the transaction. **No new dependency is required** — with one correction to the context file: `httpx` is currently a **dev-group** dependency only, not a `[project]` dependency, so a production adapter importing it needs a one-line `pyproject.toml` move.

The research that actually matters is (a) Apple's DeviceCheck wire contract, which contains two traps that will silently break the phase if the plan does not encode them, and (b) the exact database facts the activation transaction turns on, all of which are in the single migration and were read this session.

**Trap 1: `update_two_bits` writes *both* bits in one call.** Apple's update body carries `bit0` **and** `bit1`. The specification says the transaction "must not modify `bit1`", but the API offers no way to write one bit alone — so the adapter must carry `bit1`'s value forward from the query response and write it back unchanged. Get this wrong and Phase 41 silently clears Phase 42's registered-claim bit on every claim.

**Trap 2: an unclaimed device answers HTTP 200 with a plain-text body, not JSON.** A device whose bits were never set returns `200` with the body `Failed to find bit state`. That is the *normal, eligible* case — it is the answer every first-ever claim gets. Calling `.json()` on it raises; treating it as ambiguity makes the endpoint permanently unusable; treating any unparseable body as "never set" fails open. The adapter needs an exact match on that known string and a fail-closed `Unavailable` for everything else.

**Primary recommendation:** Build `auth/devicecheck.py` as a self-contained seam (Protocol + implementation + its own `tenacity` wrapper, mirroring `auth/firebase.py` line for line), keep `auth/adapters.py` untouched, put the four writes in one new `crud/grants.py` method whose `try` catches `IntegrityError` at the flush, and generalise `AuthService._complete`'s hardwired `lookup_with_retry` into an injected post-claim callable rather than forking the sequence.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01: iOS DeviceCheck only. Android and web are deferred to another milestone.** FLAGGED CONFLICT against `06-claim-anonymous-grant.md` § Scope and completion step 6.
- **D-02: With one branch, branch selection collapses to one body shape.** The completion body carries the challenge handle plus the two DeviceCheck tokens — separate query and update tokens, each used once, the query token never reused for the update. No client platform field exists or is read. `native_claim_platform` is still written as `ios_devicecheck` at the first verified claim, immutable.
- **D-03: The database is checked before Apple is asked.** Order: eligibility preflight (`free_grant_consumed_at` and the account's grant history) → Apple bit read → Apple bit write → activation transaction. The check is repeated inside the locked transaction regardless. FLAGGED CONFLICT against the brief's steps 8–9.
- **D-04: No iOS app exists, so the suite drives the endpoint with a scripted fake DeviceCheck adapter**, a sibling of `tests/e2e/conftest.py::scripted_firebase_adapter`. The Apple adapter's request signing and response parsing get unit tests against Apple's documented shapes.
- **D-05: Apple's credentials live in `.env`** — key ID, team ID and the private key — read by the same pydantic-settings loader through its nested delimiter. The key is a multi-line PEM, stored base64-encoded or as a path to a mounted file; the planner picks. Never in `config.yaml`.
- **D-06: Rules from the brief implemented as written:** bit0 only, never bit1; never accept client-supplied bit values; the write is fail-closed and load-bearing; every claim performs its own read and its own write, no caching or coalescing; the Apple call is retried through `tenacity` three attempts total; once the claim is won, **every** outcome consumes the challenge; pre-claim rejections neither claim nor consume; raw tokens never reach a log, a row or an error message. A crash after a confirmed bit write and before commit burns the device slot with no grant — accepted and uncompensated.
- **D-08: Anonymous identities only.** Route behind `get_linked_identity`; the handler or service then requires `identity.identity.provider is IdentityProvider.anonymous`. A registered caller is refused with the existing 403 `operation_not_allowed`. Inside the transaction the identity row is re-read, and a row that flipped to registered in the window is refused the same way. FLAGGED CONFLICT against the brief.
- **D-09: A repeat claim answers 200 with the same body as a fresh claim.** Two other states still refuse with 403 `operation_not_allowed`: a free grant consumed but no longer active, and an active grant of another source. FLAGGED CONFLICT against the brief's "never idempotent success".
- **D-10: A successful claim returns exactly what `POST /auth/sync` returns** — `SyncResponse` unchanged. Assembled after commit by the same read `services/sync.py::SyncService.read_entitlement` performs, taking no lock. `Cache-Control: no-store`.
- **D-11: Two new client-visible error codes, both 403:** `proof_rejected` and `device_grant_exhausted`. `verification_required` is **not** added. `ErrorCode` grows from 16 to 18. The new classes follow `ProviderLookupError`'s shape: bounded `stage`/`cause` log fields from a closed set.
- **D-12: A live two-connection race in `tests/schema`,** modelled on `test_create_race.py`.
- **D-13: The loser answers 200, as a repeat would.** The arbiter is the database: `ix_access_grants_one_free_grant_per_user_source` and `ix_access_grants_one_active_per_user` refuse the second insert. The `IntegrityError` is caught without naming a constraint or parsing a message. **Lock order:** grant rows `FOR UPDATE` ascending by id, then their usage rows; identity and user rows revalidated by plain re-read or locked only after the grant locks. `SHARED-INVARIANTS.md` wins over the brief's step 11.
- **D-14: The circuit breaker is consulted before every attempt**, not only at admission.
- **D-15: The quota charge runs before the provider permit is taken.** The semaphore moves into `ainvoke()`, around the whole retry loop.
- **D-16: `db.pool_size` is raised from 5 to 12.** The two config values stay independent numbers; the relation is a comment.
- **D-17…D-21: documentation deliverables** — amend REQUIREMENTS.md ANONGRANT-01…03, reword ROADMAP criterion 4, do NOT edit `06-claim-anonymous-grant.md`, record the Apple exposure, close the two todo files and A-15, align `AGENTS.md` § Resilience.

### Claude's Discretion

- **The DeviceCheck seam:** its module in `auth/`, the Protocol defined beside this first implementation, the HTTP client and the ES256 signing. Which Apple environment the adapter targets is config; production only.
- **Missing or malformed tokens in the body:** default to required non-empty string fields (framework 422); `proof_rejected` covers a present token Apple rejects. If that default stands, record the divergence from the brief's `proof_malformed → proof_rejected` under D-17.
- **How `AuthService` grows a completion whose post-claim work is not a Firebase read.**
- **The request model** carrying the handle and the two tokens, and its name.
- **The crud writer** for grant, anti-abuse row, usage row and marker, and the `AccessGrantAntiAbuse` SQLModel.
- **How the identity and user rows are revalidated inside the transaction** without a lock tier ahead of the grant locks.
- **Test placement and depth**, and whether the folded todos land as their own plan wave.

### Deferred Ideas (OUT OF SCOPE)

The Android branch; the web branch (Turnstile, Firebase providerData read on this route, HMAC `idp_account_hash`, the keyring, `core.provider_accounts` and `core.provider_account_gate_consumptions` writes, `verification_required`); registered claimants on the iOS gate; a dev or simulator bypass; a real-device check of the Apple round trip; rate limiting the auth surface and any vendor budget; deriving `db.pool_size` from `resilience.pool_size`; the enum-values-equal-database-labels test; operator tooling for a burned device slot.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ANONGRANT-01 | The endpoint is the only operation that may create a `core.access_grants` row with `source='anonymous_device_grant'` | § Architecture Pattern 3 (the single crud writer) and § Don't Hand-Roll — the writer is one method, and `tests/e2e/conftest.py::seed_grant` already defaults to `source=manual` because no other path may mint a free grant. A test asserting `AccessGrantSource.anonymous_device_grant` appears in exactly one `src/` write site is the cheap enforcement. Criterion 4's "mode partition with a server-determined branch" is dead machinery — see § State of the Art. |
| ANONGRANT-02 | The grant transaction honors the fixed global lock order — grant rows `FOR UPDATE` ascending by id, then their `core.user_monthly_usage` rows — with no provider or network call while a lock is held | § Architecture Pattern 4 and Pitfalls 5, 6, 7. `GrantsDB.lock_effective_grants` / `lock_usage` already carry the order; `IdentitiesDB.lock_identity_and_user` **must not** be used here. `tests/schema/test_grant_locks.py` is the existing lock-order proof to extend. |
| ANONGRANT-03 | The one-free-grant-per-account rule is enforced here; no grant row, free credit, or usage row is created as a side effect of any other path | § Code Example 4 and Pitfall 7. The database-level enforcement is `ix_access_grants_one_free_grant_per_user_source`, verified to carry **no status predicate**; the application-level preflight is `free_grant_consumed_at`. `QuotaService.charge` never mints a usage row (verified), so the claim must create it. |

## Project Constraints (from CLAUDE.md / AGENTS.md)

`./CLAUDE.md` is a single `@AGENTS.md` include; the directives live in `/home/init/native-speaker/AGENTS.md` and `ns-api-gateway/AGENTS.md`. All quoted verbatim.

| # | Directive | Source | Effect on this phase |
|---|-----------|--------|----------------------|
| C-1 | *"Keep specs short: programming this app should not consume many tokens."* | `native-speaker/AGENTS.md` | Plans stay terse; no restating of CONTEXT.md decisions in task bodies. |
| C-2 | *"The product's value is not great enough to make stealing it attractive — don't over-engineer for that threat model. But don't skip normal security measures just because there are no users yet."* | `native-speaker/AGENTS.md` | The device gate is anti-abuse, not anti-adversary. Do not add attestation, replay ledgers or defence-in-depth the spec does not name. |
| C-3 | *"The app runs in a Kubernetes cluster behind Envoy Gateway, which authenticates by JWT and rate-limits by IP, user, URL, etc."* | `native-speaker/AGENTS.md` | The absence of backend rate limiting on this route (D-20) is by design, not an omission. |
| C-4 | **Docstrings — three lines maximum.** *"State what the function, class, or module does. Nothing else."* | `ns-api-gateway/AGENTS.md` | Gated by `tests/unit/test_docstring_bar.py`, baseline **0 on every root** [VERIFIED: tests/unit/test_docstring_bar.py:42-48 — `BASELINE: dict[str, int] = {"src": 0, "tests": 0, "tests/e2e": 0, "tests/schema": 0, "tests/unit": 0,}`]. New code breaks the suite if it exceeds the bar. |
| C-5 | **Comments — only where necessary, one line each.** *"Default to none."* | `ns-api-gateway/AGENTS.md` | Same gate. |
| C-6 | Package layout: `services/` orchestration and transaction boundaries, `crud/` database access, `schemas/` bodies, `tables/` tables, `routers/` handlers `Depends()`-only, **`auth/` external-SDK seams only**. | `ns-api-gateway/AGENTS.md` | The DeviceCheck module belongs in `auth/`; the request model in `schemas/auth.py`; the writer in `crud/grants.py`; the `AccessGrantAntiAbuse` model in `tables/grants.py`; the two error classes in `errors.py`. |
| C-7 | *"`commit()` and `rollback()` are transaction boundaries and therefore business logic; they live in `services/`, not in `crud/`."* | `ns-api-gateway/AGENTS.md` exception 3 | The crud writer flushes; `AuthService` commits. |
| C-8 | *"A fail-closed read may raise its own rejection, so the rejection stays with the query in `crud/`."* | `ns-api-gateway/AGENTS.md` exception 4 | The `IntegrityError → 200-repeat` conversion may live in `crud/grants.py`, following `crud/identities.py::insert_account`. |
| C-9 | *"Delete a function that is only a step. Keep one that states a rule or marks a boundary, where a boundary is a lock, a transaction, or a callable a library requires."* | `ns-api-gateway/AGENTS.md` § Function shape | No single-caller step helpers in the new code. |
| C-10 | *"`CircuitBreaker` and `LLMExecutionGate` in `resilience.py` are deliberate. They are not awaiting replacement."* | `ns-api-gateway/AGENTS.md` § Resilience | D-14/D-15 edit them in place; they are never swapped for a library. This section is also the one D-21 must realign. |
| C-11 | No nested `try`; a `try` holds only the statement that can raise. | Phase 40 D-17, binding here | Shapes the `IntegrityError` and Apple-call error handling. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| JWT acceptance, identity resolution, active/blocked admission | Auth dependency (`app/dependencies.py::get_linked_identity`) | — | The barrier is the only place identity happens; the handler never re-verifies. Already built. |
| "Is the caller anonymous?" (D-08) | API / service | — | An authorization rule over the barrier's resolved row, not an identity decision — `identity.identity.provider`, the stored column, is the sole classifier. |
| Challenge locate / bind / claim / consume | Database (`crud/challenges.py`) | Service (orchestration) | The claim's conditional `UPDATE` is the single serialization point. **No change to `ChallengesDB` is needed** — it already issues for `claim_anonymous_grant`. |
| Device-slot state (bit0) | External vendor (Apple DeviceCheck) | — | The two-ledger model: the database is authoritative for "user received a grant", Apple's bit is authoritative for "device slot spent". Neither derives the other. |
| ES256 service-JWT minting, HTTPS transport, response parsing | External-SDK seam (`auth/devicecheck.py`) | — | `AGENTS.md` § Package layout puts external-SDK seams in `auth/` and nowhere else. |
| Eligibility preflight (marker + grant history) | Database read via `crud/` | Service (ordering) | Cheap, and it saves an Apple round trip for an ineligible account (D-03). |
| The four-row activation write | Database (`crud/grants.py`), one method | Service (owns commit/rollback) | C-7: the transaction boundary is the service's; the statements are the crud's. |
| One-free-grant-per-account arbitration under concurrency | Database (unique indexes) | — | Never the application. `FOR UPDATE` locks nothing when there is no row, so only the index can decide (D-13). |
| Response assembly | Service (`SyncService.read_entitlement`) | Router | D-10 reuses the read verbatim; no near-twin model. |
| LLM breaker / permit / quota ordering (folded todos) | `resilience.py` | `services/chats.py` unchanged | Independent of the endpoint — a natural parallel wave. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `PyJWT[crypto]` | 2.12.1 installed; `>=2.9.0` declared | Sign the ES256 DeviceCheck service JWT | Already a `[project]` dependency and already the JWT library of this codebase (`auth/jwt_verifier.py`). Apple requires ES256; PyJWT supports it via `cryptography`. [VERIFIED: pyproject.toml `[project].dependencies` contains `"PyJWT[crypto]>=2.9.0"`; `uv pip list` reports `pyjwt 2.12.1`] |
| `cryptography` | 46.0.5 installed | ES256 backend for PyJWT; PEM loading | Pulled in by the `[crypto]` extra. Not declared separately and should not be. [VERIFIED: `uv pip list`] |
| `httpx` | 0.28.1 installed | The DeviceCheck HTTPS calls | The project's only async HTTP client, already used in `tests/e2e/conftest.py`. **Currently declared under `[dependency-groups] dev` only — see Pitfall 3.** [VERIFIED: pyproject.toml `[dependency-groups] dev` contains `"httpx >=0.28"`; `[project].dependencies` does not] |
| `tenacity` | 9.1.4 installed | Bound the Apple calls to three attempts | Already a `[project]` dependency and already the retry shape D-06 mirrors. [VERIFIED: pyproject.toml `[project].dependencies` contains `"tenacity>=9.1.4"`] |
| `sqlmodel` / `asyncpg` | 0.0.37 / >=0.30 | The activation transaction | Unchanged from every other phase. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx.MockTransport` | ships with httpx 0.28.1 | Unit-test the Apple adapter's signing and parsing without a network | D-04 requires unit tests against Apple's documented shapes. **`respx` is not installed** and should not be added — `MockTransport` is built in and sufficient. [VERIFIED: `uv pip list` shows no `respx`] |
| `pydantic-settings` | 2.13.1 | Load `DEVICECHECK_*` from `.env` (D-05) | Already how `DB_*` and `JWT_*` arrive. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-built ES256 JWT via PyJWT | An Apple/DeviceCheck SDK | No Python DeviceCheck SDK of any standing exists; DeviceCheck is a signed HTTPS call, as the context already records. Adding one would be a new unaudited dependency for ~15 lines of code. |
| `httpx` | `firebase-admin`'s bundled `requests` | `requests` is synchronous and would need `run_in_threadpool` like `auth/firebase.py` does. `httpx` is already present and native-async — no threadpool hop, no second HTTP stack. |
| Re-reading `bit1` from the query to preserve it | Writing `bit1: false` unconditionally | The second silently destroys registered-claim state Phase 42 depends on. Not an option — see Pitfall 1. |

**Installation:** none. One `pyproject.toml` edit only:

```toml
# [project].dependencies — httpx becomes a runtime dependency because auth/devicecheck.py imports it
"httpx >=0.28",
```

**Version verification** (`pip index versions` is unavailable in this sandbox; verified against the installed environment instead, which is the stronger check for an already-vendored dependency):

```bash
uv pip list | grep -iE "pyjwt|httpx|tenacity|cryptography"
# pyjwt 2.12.1 · httpx 0.28.1 · tenacity 9.1.4 · cryptography 46.0.5
```

## Package Legitimacy Audit

No package is newly introduced. All four below are already installed in `.venv` and three are already `[project]` dependencies; `httpx` moves from the dev group to the runtime group.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `httpx` | PyPI | published 2024-12-06 | unknown (PyPI publishes none) | github.com/encode/httpx | SUS (`unknown-downloads`) | Approved — already vendored and used in `tests/e2e/conftest.py`; verdict is a seam artifact |
| `pyjwt` | PyPI | published 2026-05-21 | unknown | github.com/jpadilla/pyjwt | SUS (`unknown-downloads`) | Approved — already a `[project]` dependency |
| `cryptography` | PyPI | published 2026-08-25 | unknown | none reported | SUS (`too-new`, `unknown-downloads`, `no-repository`) | Approved — transitive via `PyJWT[crypto]`, not declared by this phase |
| `tenacity` | PyPI | published 2026-02-07 | unknown | github.com/jd/tenacity | SUS (`unknown-downloads`) | Approved — already a `[project]` dependency |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all four, on `unknown-downloads` — **PyPI exposes no download counts to the seam, so every PyPI package scores this way.** The `too-new` flag on `cryptography` reflects its recent release date, not a new package. No `checkpoint:human-verify` task is warranted: nothing is being newly introduced, every one of these is already resolved in the project's lockfile and importable today, and each is verified present by `uv pip list` run this session. **No package name in this document came from a web search or from training memory** — all four were read out of `pyproject.toml` and the installed environment.

## Architecture Patterns

### System Architecture Diagram

```
POST /auth/claim-anonymous-grant
  body: { challenge_id, device_token_query, device_token_update }
        │
        ▼
  [ get_linked_identity ]  ── unlinked ──▶ 403 preauth_identity_not_allowed
        │                  ── historical/blocked ──▶ 403 account_unavailable
        │                  ── no/bad JWT ──▶ 401 auth_required
        │  Identity(issuer, subject, user, identity)   evaluated_at captured once
        ▼
  [ D-08 claimant check: identity.provider is anonymous? ]
        │  no ──▶ 403 operation_not_allowed          (nothing claimed, nothing consumed)
        ▼ yes
  ┌─────────────── shared completion sequence (AuthService) ───────────────┐
  │  locate challenge ──▶ verify_binding ──▶ operation == claim_anonymous_grant │
  │        │ any failure ──▶ 409 challenge_required   (NOT claimed, NOT consumed)│
  │        ▼                                                                    │
  │  CLAIM (one conditional UPDATE — the only expiry check, the only            │
  │         serialization point)  ──▶ COMMIT                                    │
  │        │  lost ──▶ 409 challenge_required                                   │
  └────────┼────────────────────────────────────────────────────────────────────┘
           ▼  ═══ from here every outcome CONSUMES the challenge ═══
    (1) DB eligibility preflight  [D-03: database before Apple]
           │  active anon grant already held ──▶ 200 (D-09 repeat, no Apple call)
           │  marker set / inactive free grant / other active grant ──▶ 403 operation_not_allowed
           ▼ eligible
    (2) Apple  POST /v1/query_two_bits          ── ES256 JWT, 3 attempts, no lock held
           │  bit0 = true          ──▶ 403 device_grant_exhausted
           │  token rejected       ──▶ 403 proof_rejected
           │  exhausted/ambiguous  ──▶ 503 verification_temporarily_unavailable
           ▼ bit0 = false  (incl. "Failed to find bit state")   ── carry bit1 forward ──┐
    (3) Apple  POST /v1/update_two_bits  { bit0: true, bit1: <carried> }                │
           │  anything but confirmed success ──▶ 503 verification_temporarily_unavailable
           ▼ Apple confirmed  ── no network call past this line ──
    (4) ACTIVATION TRANSACTION  (database-only, short)
           lock grant rows FOR UPDATE asc by id  ──▶  lock their usage rows
           re-read identity + user (NO FOR UPDATE ahead of the grant locks)
           re-check eligibility
           INSERT core.access_grants (source=anonymous_device_grant, tier=anonymous, active)
           INSERT core.access_grants_anti_abuse (native_claim_provider=ios_devicecheck)
           INSERT core.user_monthly_usage (period=YYYY-MM, used=0)
           SET external_identities.free_grant_consumed_at, native_claim_platform
           │  IntegrityError (unique index) ──▶ rollback ──▶ re-read ──▶ 200 (D-13 loser)
           ▼
    (5) CONSUME challenge + COMMIT
           ▼
    (6) read_entitlement (no lock, post-commit) ──▶ 200 SyncResponse, Cache-Control: no-store
```

### Recommended Project Structure

```
src/nativespeaker/api/
├── auth/devicecheck.py     # NEW — Protocol + Apple impl + tenacity wrapper (the only new module)
├── crud/grants.py          # + one activation writer method
├── tables/grants.py        # + AccessGrantAntiAbuse SQLModel
├── schemas/auth.py         # + the completion request model
├── errors.py               # + ProofRejected, DeviceGrantExhausted; ErrorCode 16 → 18
├── services/auth.py        # _complete generalised; new complete_claim_anonymous_grant
├── routers/auth.py         # + the route (docstring route count grows 4 → 5)
├── app/lifespan.py         # + build the adapter; db pool_size follows config
├── app/dependencies.py     # + get_devicecheck_adapter, wire into get_auth_service
├── config.py               # + DeviceCheckConfig; db.pool_size default (D-16)
└── resilience.py           # D-14 / D-15 (independent — can be its own wave)
```

### Pattern 1: The external-SDK seam, copied from `auth/firebase.py`

**What:** Protocol beside the implementation, module-level constants for the budget, an internal `Retryable*Error` marker that never escapes, a `_exhausted` callback converting an exhausted budget into `Unavailable`, and a `*_with_retry` free function holding the `AsyncRetrying`.
**When to use:** for both DeviceCheck calls. FOUND-08's forward-flag treatment requires the Protocol to be declared beside its first implementation — so it goes in `auth/devicecheck.py`, **not** in `auth/adapters.py`.
**Why this placement is load-bearing:** `auth/adapters.py` is guarded by an import allowlist that does not include `httpx` [VERIFIED: tests/unit/test_adapter_interfaces.py:23 — `ALLOWED_IMPORT_ROOTS = {"dataclasses", "datetime", "enum", "typing", "uuid", "nativespeaker"}`]. Putting the DeviceCheck Protocol there and importing `httpx` for the implementation would fail that test.

**The exact shape to mirror** [VERIFIED: src/nativespeaker/api/auth/firebase.py:134-147]:

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

Note `retry_error_callback=_exhausted` rather than `reraise=True`: an exhausted budget becomes the client's owed 503, and the internal marker never escapes. `Unavailable` already answers 503 `verification_temporarily_unavailable` [VERIFIED: src/nativespeaker/api/errors.py:372-375 — `class Unavailable(ProviderLookupError): ... status = 503; code = "verification_temporarily_unavailable"`], so D-06's "any exhausted failure, timeout or ambiguity → `verification_temporarily_unavailable`" needs **no new class** for that arm.

### Pattern 2: Generalising `AuthService._complete`

**What:** `_complete` today hardwires the Firebase read between claim and write [VERIFIED: src/nativespeaker/api/services/auth.py:98-107]:

```python
        try:
            facts = await lookup_with_retry(self.adapter, identity.issuer, identity.subject)
            # The provider the transaction settled on, which a divergence makes different from the read's.
            settled = await write(identity, facts)
        except AppError:
            # A conflicting write leaves the transaction unusable, and the spend below needs it back.
            await self.session.rollback()
            await self._consume_quietly(challenge_id=challenge_id,
                                        challenge_row_id=challenge_row_id)
            raise
```

**Recommended change — the smallest one that satisfies Phase 40 D-16 ("`AuthService` grows rather than forks"):** replace the two hardwired statements with a single injected `post_claim` callable, `Callable[[Identity], Awaitable[T]]`. Create-user and upgrade pass a closure that does the Firebase read then their `write`; the claim passes a closure that does preflight → Apple read → Apple write → activation. Everything else — the rejection precedence, the claim, the deliberate commit, the `except AppError` rollback-then-consume arm, the final consume-and-commit — is untouched and shared. The current `Write` alias generalises rather than gaining a sibling.

**Why not a savepoint:** there is no `begin_nested()` anywhere in the completion path today, and the rollback arm depends on that. Do not introduce one.

**Why the return type must generalise:** `_complete` currently returns `IdentityProvider`; this route returns a `SyncResponse`-shaped entitlement. Make `_complete` generic over the post-claim result rather than widening it to a union.

### Pattern 3: The single crud writer

**What:** one method in `crud/grants.py` performing all four writes and flushing once, with `IntegrityError` caught at the flush — exactly `crud/identities.py::insert_account`'s shape.
**When to use:** for the activation body only. The commit stays in `services/` (C-7).
**The precedent, verbatim** [VERIFIED: src/nativespeaker/api/crud/identities.py:112-115]:

```python
            await self.session.flush()
            return user.id
        except IntegrityError as conflict:
            raise IdentityAlreadyLinked() from conflict
```

The constraint is never named and the message never parsed (Phase 40 D-08). Here the raise is not an error at all — it is D-13's race loser, which answers 200. Two shapes are available: raise a private sentinel the service converts to the re-read path, or return a boolean the service branches on. Either is fine; a boolean avoids an exception class with no client-visible answer.

### Pattern 4: The activation transaction's lock order

**What:** `GrantsDB.lock_effective_grants(user_id, evaluated_at)` then `GrantsDB.lock_usage(grant.id)` per grant, ascending by id. Both already exist and already carry the order [VERIFIED: src/nativespeaker/api/crud/grants.py:37-53 — `lock_effective_grants` docstring reads *"Lock and return every effective grant for `user_id` at `evaluated_at`, ascending by id."*; `lock_usage` reads *"Lock and return `grant_id`'s usage row, or `None`. Second in the lock order and never first."*].

**The binding rule** [VERIFIED: specs/auth-refactor-phases/SHARED-INVARIANTS.md:34]:

> Fixed global lock order on every path touching grants, binding every current and future path: grant row(s) `FOR UPDATE` first in ascending grant id, then their `core.user_monthly_usage` rows in the same order. Never the reverse, and never an account/user-row lock tier ahead of the grant locks.

That last clause is why `IdentitiesDB.lock_identity_and_user` — which the upgrade uses — **cannot** be reused here: it takes `FOR UPDATE` on the identity and user rows [VERIFIED: src/nativespeaker/api/crud/identities.py:61-74, statement ends `.with_for_update()`]. The re-read D-08 needs must either be a plain `SELECT` (no `FOR UPDATE`) or a locking read issued strictly **after** `lock_effective_grants`. `IdentitiesDB.resolve_existing` is already the non-locking re-resolution and is the natural fit [VERIFIED: src/nativespeaker/api/crud/identities.py:55-59 — docstring *"The re-resolution, issued inside the transaction. Not the race arbiter, and never to be one."*].

### Anti-Patterns to Avoid

- **Writing `bit1: false` in the update call.** Apple writes both bits per call. See Pitfall 1.
- **Calling `response.json()` on a DeviceCheck reply without checking the content first.** See Pitfall 2.
- **Using `challenge_id` as the Apple `transaction_id`.** The handle is a secret that travels only in the prepare response and completion request bodies. Mint a fresh `uuid4()` per Apple call.
- **Locking the identity or user row before the grant rows.** Forbidden by `SHARED-INVARIANTS.md:34`.
- **Treating `FOR UPDATE` as the race arbiter for a first claim.** It locks nothing when there is no grant row. Only the unique index decides.
- **Minting a usage row lazily in the quota path.** `QuotaService.charge` deliberately never does [VERIFIED: src/nativespeaker/api/services/quota.py:47-51 — *"Fail closed, never mint: a grant without a usage row is a failed write, not a fresh allowance."*]; the claim must create it.
- **Adding a `verification_required` error code.** D-11 excludes it; it arrives with the web branch.
- **A nested `try`, or a `try` wrapping more than the raising statement** (C-11).
- **Deriving the claimant class from anything but the stored `provider` column.** `SHARED-INVARIANTS.md` § Identity and ownership makes the stored column the sole per-request classifier.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ES256 JWT for Apple | Manual DER→JOSE signature conversion over `cryptography` | `jwt.encode(payload, key, algorithm="ES256", headers={"kid": ...})` | ECDSA JOSE signatures are raw `r‖s`, not the DER that `cryptography`'s signer emits. Converting by hand is the classic silent-failure bug. PyJWT does it. [CITED: PyJWT usage docs via Context7] |
| Bounded retry with a converted terminal failure | A `for` loop with counters | `tenacity.AsyncRetrying` + `retry_error_callback` | Already the shape at `auth/firebase.py:139-147`; a second hand-rolled loop is a second place the budget can drift. |
| Concurrency arbitration for "one free grant" | An advisory lock, a `SELECT … FOR UPDATE` on the user, or a read-then-insert check | The two existing unique indexes | The indexes already exist and are already correct. `SHARED-INVARIANTS.md:64` forbids *"distributed lock, lease, or multi-phase-commit machinery"* outright. |
| The entitlement response body | A new `ClaimResponse` model | `SyncResponse` + `SyncService.read_entitlement` | D-10. "Fewer copies of one fact" is an explicit developer preference recorded in CONTEXT.md § Specific Ideas. |
| The challenge protocol | Anything | `crud/challenges.py::ChallengesDB` unchanged | It already issues for `claim_anonymous_grant` and already binds a linked caller. Zero edits. |
| The 403 anti-oracle grouping | Per-branch bodies | A shared base declaring `status`/`code` once | `errors.py`'s `ChallengeRejected` and `UpgradeRefused` both do this; `tests/unit/test_rejection_vocabulary.py` asserts no leaf re-declares. |
| A circuit breaker | A library | The existing `resilience.py::CircuitBreaker` | `AGENTS.md` § Resilience: *"They are not awaiting replacement."* Nothing installed replaces one. |

**Key insight:** this phase's genuinely new code is small — one HTTP seam, one SQL writer, one request model, two error classes, one route. Everything else already exists and is already correct. The failure mode for this phase is not "we built the wrong thing", it is "we rebuilt something that existed" or "we missed one of the six database facts the transaction turns on". Both are prevented by reading, not by designing.

## Common Pitfalls

### Pitfall 1: `update_two_bits` writes both bits, so bit1 must be carried forward

**What goes wrong:** the plan writes `{"bit0": true, "bit1": false}` because the spec says "bit0 only, never bit1". Every anonymous claim then clears the registered-claim bit that Phase 42 will depend on, and there is no way to detect it after the fact — Apple's bits are never auto-reconciled and never cleared by anyone else.
**Why it happens:** the specification's language (*"the same DeviceCheck transaction must not modify `bit1`"*) describes an intent that Apple's API cannot express directly. `update_two_bits` takes both booleans in one body. [ASSUMED — Apple's own documentation page could not be fetched; two independent secondary sources agree the update body carries both `bit0` and `bit1`, and one states explicitly that it *"modifies both bits simultaneously in a single operation"*.]
**How to avoid:** the query response's `bit1` is an input to the update. Model the adapter as `read() -> BitState(bit0, bit1)` then `write(bit0=True, bit1=state.bit1)`. When the query returned the never-set answer there is no prior `bit1`, so `false` is correct and is the only value that can be correct. Assert this in a unit test that scripts a query returning `bit1=true` and checks the update body carries `bit1=true`.
**Warning signs:** an update-body builder that takes only one bit; a `BitState` type that discards `bit1`; a test that only ever scripts `bit1=false`.

### Pitfall 2: an unclaimed device answers 200 with a plain-text body

**What goes wrong:** `response.json()` raises on the very first real claim any device ever makes, and the generic `except` classifies it as ambiguity → 503. The endpoint then never succeeds for anyone, and the failure only appears once a real iOS app exists — which, per D-04, is after this phase ships.
**Why it happens:** Apple returns HTTP **200** with the plain-text body `Failed to find bit state` (also reported as `Bit State Not Found`) when the device's bits were never set. That is the *eligible* case, not an error. Errors generally arrive as plain-text bodies too. [ASSUMED — corroborated by multiple Apple Developer Forums threads and two independent engineering write-ups; no official Apple page was fetchable this session.]
**How to avoid:** parse in this order — (1) non-2xx → retryable/`Unavailable`; (2) body parses as JSON with both `bit0` and `bit1` present → that state; (3) body matches the known never-set string exactly → `bit0=False, bit1=False`; (4) anything else → `Unavailable`, never a default. Step 4 is what keeps it fail-closed: an unrecognised plain-text body is ambiguity, and D-06 requires ambiguity to refuse. Unit-test all four arms; the third and fourth are the ones a reviewer will otherwise not believe exist.
**Warning signs:** a single `response.json()` with no guard; a `.get("bit0", False)` default; any branch that reads a parse failure as "unclaimed".

### Pitfall 3: `httpx` is a dev-group dependency, not a runtime one

**What goes wrong:** `auth/devicecheck.py` imports `httpx`, the tests pass locally (the dev group is installed), and the container image built from `[project].dependencies` alone fails at import.
**Why it happens:** the context file states *"the HTTP client (`httpx` is installed)"*, which is true of the environment but not of the runtime dependency set. [VERIFIED: pyproject.toml — `[project].dependencies` lists fastapi, uvicorn, pydantic, pydantic-settings, pyyaml, orjson, langchain, langchain-openai, langchain-core, openai, asyncpg, sqlmodel, greenlet, `PyJWT[crypto]`, ruff, ty, structlog, app-store-server-library, firebase-admin, tenacity — and **no httpx**; `[dependency-groups] dev` lists `"httpx >=0.28"`.]
**How to avoid:** add `"httpx >=0.28",` to `[project].dependencies` in the same task that creates the module. Leaving the dev-group entry is harmless.
**Warning signs:** a plan whose only `pyproject.toml` change is the version pin, or none at all.

### Pitfall 4: `tests/unit/test_auth_package_shape.py` is a hard literal ratchet

**What goes wrong:** adding `auth/devicecheck.py` fails a test that has nothing to do with DeviceCheck, and the failure reads as unrelated.
**Why it happens:** the file records the package's measured shape as a literal that a growing phase must come and update. [VERIFIED: tests/unit/test_auth_package_shape.py:13 — `CURRENT = (4, 8, 18)`, with the surrounding comment `# What it measures now: modules, classes, functions.` and the case docstring *"A later phase that grows the package has to come here and write the new number down."*]
**How to avoid:** make updating `CURRENT` an explicit task step in the same plan that adds the module, not a fix-up. The count is `(top-level .py modules, ClassDefs at any depth, FunctionDefs/AsyncFunctionDefs at any depth)` — methods and nested helpers count.
**Warning signs:** no mention of `test_auth_package_shape` anywhere in the plan.

### Pitfall 5: `FOR UPDATE` locks nothing on a first claim, so the index is the only arbiter

**What goes wrong:** the plan reasons "we lock the grant set, so the second attempt waits" and omits the `IntegrityError` arm. Two concurrent first claims then both pass the preflight, both call Apple, and the second insert surfaces as a 500.
**Why it happens:** a first claimant has no grant row, so `lock_effective_grants` returns an empty list and takes no lock at all. D-13 already names this; the plan must carry it into a task.
**How to avoid:** the `IntegrityError` arm is mandatory, not defensive. The race test (D-12) is what proves it, and `tests/schema/test_create_race.py` already provides `_Harness`, the private-issuer fixture and the FK-ordered cleanup to extend [VERIFIED: tests/schema/test_create_race.py:31-36, `@dataclass class _Harness` with fields `engine`, `factory`, `issuer`, `owned_user_ids`].
**Warning signs:** a plan that mentions the lock order but not the unique indexes.

### Pitfall 6: the anti-abuse FK is deferred, so its violation appears at COMMIT

**What goes wrong:** the `try` wraps only the flush (copying `insert_account`), the two unique indexes are caught correctly — but a missing anti-abuse row surfaces as an `IntegrityError` out of `session.commit()`, well outside any handler, as a 500.
**Why it happens:** the two FKs joining `core.access_grants` and `core.access_grants_anti_abuse` are deferred to commit time, while the unique indexes are ordinary and fire at statement time. [VERIFIED: migrations/20260818_01_initial-release.sql:304-307 — `FOREIGN KEY (grant_id, grant_source) REFERENCES core.access_grants (id, source) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED`; and :316-322 — `ALTER TABLE core.access_grants ADD FOREIGN KEY (anti_abuse_required_grant_id) REFERENCES core.access_grants_anti_abuse (grant_id) DEFERRABLE INITIALLY DEFERRED, ADD FOREIGN KEY (active_registered_account_grant_id) REFERENCES core.access_grants_anti_abuse (registered_account_grant_id) DEFERRABLE INITIALLY DEFERRED`. Contrast :267-269 — `CREATE UNIQUE INDEX ix_access_grants_one_active_per_user ON core.access_grants (user_id) WHERE status = 'active';` preceded by the comment `-- Non-deferrable and per-statement; a correct caller makes it unreachable by expiring before activating.`]
**How to avoid:** correct code never trips the deferred FK — insert grant and anti-abuse row together in the same flush. But the plan should know *where* each class of failure lands, and the race test should assert the loser's `IntegrityError` arrives at the flush, not the commit.
**Warning signs:** a plan that inserts the grant and the anti-abuse row in separate flushes, or that describes "the FK will catch it".

### Pitfall 7: the lifetime free-grant index has no status predicate

**What goes wrong:** the plan implements D-09's three-way branch by reading `status` and concludes a revoked grant frees the slot. The database disagrees and the insert fails.
**Why it happens:** the index is deliberately unconditional on status. [VERIFIED: migrations/20260818_01_initial-release.sql:324-327 — comment `-- No status predicate on purpose: expiry or revocation never reopens the lifetime free-grant slot.` above `CREATE UNIQUE INDEX ix_access_grants_one_free_grant_per_user_source ON core.access_grants (user_id, source) WHERE source IN ('anonymous_device_grant', 'registered_account_grant');`]
**How to avoid:** this is exactly D-09's second refusal arm ("a free grant that was consumed but is no longer active → 403 `operation_not_allowed`"), and the database enforces it independently. The application preflight and the index agree; state that they agree rather than treating one as backup.
**Warning signs:** a preflight predicate that includes `status == active` when testing for a *prior* free grant.

### Pitfall 8: the anti-abuse CHECK dictates the exact NULL pattern for the iOS arm

**What goes wrong:** the row is written with the hash columns populated, or with `native_claim_provider` left NULL, and the CHECK rejects it.
**Why it happens:** the CHECK is an exclusive-or over the two population shapes. [VERIFIED: migrations/20260818_01_initial-release.sql:286-302 — `CHECK ( (grant_source = 'anonymous_device_grant' AND ( (native_claim_provider IS NOT NULL AND idp_account_hash IS NULL AND idp_account_hash_key_version IS NULL) OR (native_claim_provider IS NULL AND idp_account_hash IS NOT NULL AND idp_account_hash_key_version IS NOT NULL) )) OR (grant_source = 'registered_account_grant' AND native_claim_provider IS NULL AND idp_account_hash IS NOT NULL AND idp_account_hash_key_version IS NOT NULL) )`]
**How to avoid:** the iOS row is exactly `grant_source='anonymous_device_grant'`, `native_claim_provider='ios_devicecheck'`, both hash columns NULL. That is also why D-01's deferral costs no migration: the web branch is the *other* arm of the same CHECK.
**Warning signs:** an `AccessGrantAntiAbuse` model giving the hash columns non-NULL defaults.

### Pitfall 9: `AccessGrantAntiAbuse` must leave its GENERATED column unmapped

**What goes wrong:** the new SQLModel maps `registered_account_grant_id`, and every insert fails because PostgreSQL rejects an explicit value for a generated column.
**Why it happens:** the same rule `AccessGrant` already documents. [VERIFIED: src/nativespeaker/api/tables/grants.py:44 — `# The table's four GENERATED ALWAYS AS STORED columns are deliberately unmapped: Postgres rejects an explicit value.`; and migrations/20260818_01_initial-release.sql:279-281 — `registered_account_grant_id UUID GENERATED ALWAYS AS ( CASE WHEN grant_source = 'registered_account_grant' THEN grant_id END ) STORED,`]
**How to avoid:** map `grant_id` (PK), `grant_source`, `native_claim_provider`, `idp_account_hash`, `idp_account_hash_key_version`, `created_at`. Nothing else. Note `created_at` is `NOT NULL` with **no** database default, so the model must supply it — the same asymmetry `UserMonthlyUsage` already carries [VERIFIED: src/nativespeaker/api/tables/grants.py:74 — `# NOT NULL with no crud DEFAULT, unlike every other table: these factories are the only source of a value.`; migration :282 — `created_at TIMESTAMPTZ NOT NULL,`].

### Pitfall 10: three unrelated things are called "apple"

**What goes wrong:** an enum is reused across domains and the type checker is happy.
**Why it happens:** `IdentityProvider.apple` is Sign in with Apple [VERIFIED: src/nativespeaker/api/tables/identities.py:11-16 — `class IdentityProvider(StrEnum): anonymous = "anonymous"; google = "google"; apple = "apple"`]; `PurchaseProvider.apple` is the App Store; and Apple-the-DeviceCheck-vendor has no enum at all. The value this phase writes is `NativeClaimProvider.ios_devicecheck` [VERIFIED: src/nativespeaker/api/tables/identities.py:24-27 — `class NativeClaimProvider(StrEnum): """Mirrors \`core.native_claim_provider\` -- the platform a native claim is pinned to, immutably."""; ios_devicecheck = "ios_devicecheck"; android_play_integrity = "android_play_integrity"`].
**How to avoid:** name the config block and the module for the vendor API (`devicecheck`), never `apple`.

### Pitfall 11: `ErrorCode` needs editing but the registry test does not

**What goes wrong:** the plan budgets a task for teaching `test_error_registry.py` the two new codes, and a reviewer looks for an edit that should not exist.
**Why it happens:** D-11 says the test *"learns both"*, but the assertion is symmetric and self-maintaining. [VERIFIED: tests/unit/test_error_registry.py:71-72 — `def test_the_error_code_literal_equals_the_set_the_tree_carries(self): assert set(get_args(ErrorCode)) == {cls.code for cls in _family(AppError)}`. No literal count of 16 appears in `test_error_registry.py`, `test_error_contract.py` or `test_rejection_vocabulary.py`.]
**How to avoid:** the only edit is appending the two members to the `ErrorCode` Literal in `errors.py` and declaring them on the two new classes. The test then passes because both sides grew together — and fails loudly if only one did, which is exactly the guard wanted. Also satisfied automatically: `test_no_code_is_declared_at_two_different_statuses` (both new codes are 403 and declared once) and `test_every_class_declares_status_and_code_together_or_neither`.
**Warning signs:** a task named "update the error registry test".

### Pitfall 12: D-15's semaphore is not separable with today's `LLMExecutionGate` API

**What goes wrong:** the plan says "move the semaphore into `ainvoke`" and finds `admission()` calls a single `hold()` that takes both the slot and the semaphore together.
**Why it happens:** [VERIFIED: src/nativespeaker/api/resilience.py:97-102 — `@asynccontextmanager async def hold(self): """Hold an in-flight slot and the concurrency semaphore, or raise \`QueueFullError\`.""" async with self._inflight_slot(): async with self._semaphore: yield`; and :133-138 — `@asynccontextmanager async def admission(self): """Admit one request: the breaker is consulted and a slot is held for the caller's whole body.""" await self._circuit_breaker.before_call(); async with self._gate.hold(): yield Admitted()`]
**How to avoid:** `LLMExecutionGate` gains a second public context manager (the slot alone) and `hold()` either splits or is replaced by the pair; `admission()` takes the slot, `ainvoke()` wraps its whole `AsyncRetrying` in the semaphore. Both docstrings change, and so do the `test_quota_seam.py` cases that assert admission holds a permit.
**Warning signs:** a task that edits only `admission()`.

### Pitfall 13: D-14 makes an existing `except` reachable — and it must stay first

**What goes wrong:** `before_call()` is added to the top of `attempt()` but below the `try`, so the `CircuitOpenError` it raises is swallowed by the generic arm, recorded as a breaker failure, and rewrapped as a 503 `service_unavailable` instead of carrying its `Retry-After`.
**Why it happens:** `attempt()`'s generic arm records a failure and reclassifies everything it sees. [VERIFIED: src/nativespeaker/api/resilience.py:143-154 — the `except (QueueFullError, CircuitOpenError): raise` arm sits immediately above `except Exception as e:` which calls `await self._circuit_breaker.record_failure()` and raises `TransientLLMError`/`PermanentLLMError`.]
**How to avoid:** `await self._circuit_breaker.before_call()` goes at the top of `attempt()` **outside** the `try`, or inside it above `asyncio.wait_for` with the existing pass-through arm ordered first. D-14 explicitly wants that arm reachable again — assert it with a case that opens the breaker mid-flight and checks the request answers 503 with `Retry-After` rather than spending its remaining attempts.

### Pitfall 14: D-16's config edit has a working precedent — use it

**What goes wrong:** the plan assumes adding a `db:` block to `config.yaml` will break the `DB_*` env nesting, and instead only edits the Python default — or does add the block and worries it clobbered the credentials.
**Why it happens:** the file's own comment warns that YAML wins over env for anything it declares. But partial blocks deep-merge, and the repo already proves it: `config.yaml` declares `jwt: jwks_cache_ttl_seconds: 3600` while `JWT_PROJECT_ID` and `JWT_API_KEY` still arrive from `.env` and `JWTConfig` requires them with no defaults. [VERIFIED: config/config.yaml:15-16 — `jwt:` / `  jwks_cache_ttl_seconds: 3600`; src/nativespeaker/api/config.py:45-47 — `class JWTConfig(BaseModel): project_id: str = Field(description="GCP project ID"); api_key: str = Field(description="GCP API key")`; .env.example — `JWT_PROJECT_ID=...` / `JWT_API_KEY=...`]
**How to avoid:** either option works. `db: pool_size: 12` in `config.yaml` mirrors the `jwt` precedent and is where `resilience.pool_size: 5` already lives, making the "×2+2" comment readable next to its operand. Editing `config.py`'s default instead [VERIFIED: src/nativespeaker/api/config.py:25 — `pool_size: int = Field(default=5, ge=1, description="Connection pool size")`] keeps `DB_POOL_SIZE` overridable from `.env`, which YAML would foreclose. Recommend the YAML block, because it puts both numbers on adjacent screens and D-16 wants the relation legible.

### Pitfall 15: raw DeviceCheck tokens must not reach the error message either

**What goes wrong:** a debugging `raise ProofRejected(f"Apple rejected {token}")` ships. The body never leaks it (the response carries one field) but the log line does.
**Why it happens:** `AppError.__init__` accepts message args freely, and `ProviderLookupError` builds its message from safe parts only. [VERIFIED: src/nativespeaker/api/errors.py:346-359 — `class ProviderLookupError(AppError): def __init__(self, *, stage: str, cause: str | None = None) -> None: # Plain strings, both of them ours: no provider text is ever admissible in either field.` … `super().__init__(f"{type(self).__name__.lower()} at {stage}")`; and :32-34 — `class ErrorResponse(BaseModel): """The single shared error body shape. Exactly one field -- do not add more."""; code: ErrorCode`]
**How to avoid:** copy `ProviderLookupError`'s keyword-only `stage`/`cause` signature exactly, with values from a closed set, and give `auth/devicecheck.py` no logger that could see a token — the same discipline `crud/challenges.py` states for handles [VERIFIED: src/nativespeaker/api/crud/challenges.py:1 — *"A handle is a secret capability: this module holds no logger, so none is logged."*].

## Code Examples

### 1. The two new error classes

```python
# errors.py — appended after the Upgrade arms. Both 403; each declares its own pair.
# The Literal grows in the same edit: ErrorCode gains "proof_rejected" and "device_grant_exhausted".

class ProofRejected(ProviderLookupError):
    """Apple refused the device tokens, or they were present but unusable."""
    status = 403
    code = "proof_rejected"


class DeviceGrantExhausted(ProviderLookupError):
    """This device already spent its one anonymous grant slot."""
    status = 403
    code = "device_grant_exhausted"
```

Inheriting `ProviderLookupError` buys the bounded `stage`/`cause` log fields for free and satisfies `test_every_class_declares_status_and_code_together_or_neither`. `Unavailable` (503, `verification_temporarily_unavailable`) is reused unchanged for every ambiguity arm — no third class. [VERIFIED against errors.py:346-381, quoted in Pitfall 15 and Pattern 1.]

### 2. The DeviceCheck request bodies and JWT

```python
# auth/devicecheck.py — the wire shapes. [ASSUMED: Apple's own docs were not fetchable;
# corroborated by two independent secondary sources. Treat the field names as the first
# thing to check against a real 400 when an iOS app exists.]

DEVICECHECK_PRODUCTION_HOST = "https://api.devicecheck.apple.com"
QUERY_PATH = "/v1/query_two_bits"
UPDATE_PATH = "/v1/update_two_bits"

# Three attempts total, mirroring FIREBASE_LOOKUP_ATTEMPTS.
DEVICECHECK_ATTEMPTS = 3

def _service_jwt(key_id: str, team_id: str, private_key: str, now: datetime) -> str:
    """Mint the ES256 bearer Apple's server-to-server API requires."""
    return jwt.encode({"iss": team_id, "iat": int(now.timestamp())},
                      private_key,
                      algorithm="ES256",
                      headers={"kid": key_id})

# Query body — transaction_id is a fresh uuid4, never the challenge handle.
{"device_token": "<base64 from the device>",
 "transaction_id": str(uuid4()),
 "timestamp": int(now.timestamp() * 1000)}          # milliseconds, not seconds

# Update body — BOTH bits, with bit1 carried forward from the query (Pitfall 1).
{"device_token": "<the SEPARATE update token>",
 "transaction_id": str(uuid4()),
 "timestamp": int(now.timestamp() * 1000),
 "bit0": True,
 "bit1": state.bit1}
```

`jwt.encode(..., algorithm="ES256", headers={"kid": ...})` is the documented PyJWT form. [CITED: https://github.com/jpadilla/pyjwt/blob/master/docs/usage.md — *"Use ES256 for ECDSA encoding and decoding. Requires the 'cryptography' module."*, and the `headers={"kid": ...}` example.]

### 3. The four parse arms (Pitfall 2)

```python
# The order is the rule. Nothing falls through to a default.
_NEVER_SET_BODIES = {"Failed to find bit state", "Bit State Not Found"}

if response.status_code != 200:
    raise RetryableDeviceCheckError(f"status {response.status_code}")

body = response.text.strip()
if body in _NEVER_SET_BODIES:
    # The eligible first-ever claim: no bits were ever written for this device.
    return BitState(bit0=False, bit1=False)

# Only the flush of a genuine JSON object is a state; anything else is ambiguity.
try:
    payload = response.json()
except ValueError as unparseable:
    raise RetryableDeviceCheckError("unparseable body") from unparseable

if not isinstance(payload, dict) or "bit0" not in payload or "bit1" not in payload:
    raise RetryableDeviceCheckError("missing bits")
return BitState(bit0=bool(payload["bit0"]), bit1=bool(payload["bit1"]))
```

### 4. The eligibility facts the preflight and the transaction both read

```sql
-- The marker (D-03), read off the identity row the barrier already resolved.
-- core.external_identities.free_grant_consumed_at TIMESTAMPTZ
--   "Set once when the account consumes its one lifetime free grant, and never cleared."

-- Prior free grant of EITHER source, regardless of status — this is what the index enforces.
SELECT 1 FROM core.access_grants
 WHERE user_id = :user_id
   AND source IN ('anonymous_device_grant', 'registered_account_grant');

-- The active-grant read is the existing shared predicate, via GrantsDB.
--   status = 'active' AND starts_at <= :evaluated_at
--   AND (ends_at IS NULL OR ends_at > :evaluated_at)
```

[VERIFIED: migrations/20260818_01_initial-release.sql:88-89 — `-- Set once when the account consumes its one lifetime free grant, and never cleared.` above `free_grant_consumed_at TIMESTAMPTZ,`; :324-327 quoted in Pitfall 7; and src/nativespeaker/api/crud/grants.py:11-23, whose `_effective_grants_statement` carries the predicate with the comment `# \`== active\`, not \`!= revoked\`: a NULL or a future member must fail closed here.`]

### 5. The usage row the claim must mint

```python
# The values are fixed by the existing contract; nothing here is a choice.
UserMonthlyUsage(grant_id=grant.id,
                 monthly_period=evaluated_at.strftime("%Y-%m"),
                 monthly_used=0,
                 created_at=evaluated_at,
                 updated_at=evaluated_at)
```

`%Y-%m` is the one derivation, and it comes from the request's captured instant [VERIFIED: src/nativespeaker/api/services/sync.py:26-27 — `# The only place the period is derived, and always from the request's captured instant.` above `period = self.evaluated_at.strftime("%Y-%m")`; the identical line and comment appear in services/quota.py]. `monthly_period` is free text with no format CHECK [VERIFIED: src/nativespeaker/api/tables/grants.py:71-72 — `# Free text in YYYY-MM; the crud enforces no format.`].

### 6. The tier the grant points at

```python
# tables/grants.py::AccessGrantSource — the value this phase writes, verbatim:
#   anonymous_device_grant = "anonymous_device_grant"
# The tier id is the seeded "anonymous" row (monthly_credits = 10, per STATE.md 36-01).
AccessGrant(user_id=user.id,
            tier_id="anonymous",
            source=AccessGrantSource.anonymous_device_grant,
            status=AccessGrantStatus.active,   # the model's default anyway
            subscription_id=None,              # the CHECK requires NULL for every non-subscription source
            starts_at=evaluated_at,
            created_at=evaluated_at,
            updated_at=evaluated_at)
```

[VERIFIED: src/nativespeaker/api/tables/grants.py:11-16 — `class AccessGrantSource(StrEnum): """Mirrors \`core.access_grant_source\`. Only \`subscription\` carries a \`subscription_id\`."""; subscription = "subscription"; anonymous_device_grant = "anonymous_device_grant"; registered_account_grant = "registered_account_grant"; manual = "manual"` and :19-23 for `AccessGrantStatus`: `active = "active"; revoked = "revoked"; expired = "expired"`. The subscription CHECK is verbatim at migrations/20260818_01_initial-release.sql:237-242 — `-- source='subscription' requires subscription_id; every other source forbids it.` The tier id string `"anonymous"` is **[ASSUMED]** — the seed row is asserted in STATE.md's Phase 36-01 note (`anonymous=10, registered=50, paid=1000`) but the migration's `INSERT INTO core.access_tiers` was not opened this session; a planner should read it before writing the literal.]

### 7. The completion request model

```python
# schemas/auth.py, beside CompletionRequest. min_length=1 makes an absent or empty
# token the framework's 422, exactly as CompletionRequest already does for the handle.
class AnonymousGrantClaimRequest(BaseModel):
    """The claim body: the handle, and the two single-use DeviceCheck tokens."""
    challenge_id: str = Field(..., min_length=1)
    query_token: str = Field(..., min_length=1)
    update_token: str = Field(..., min_length=1)
```

[VERIFIED: src/nativespeaker/api/schemas/auth.py:24-28 — `class CompletionRequest(BaseModel): """The completion body: the handle obtained from \`/auth/challenge\`, and nothing else."""; # Required and non-empty, so an unusable handle is the framework's 422 rather than a not-found 409.; # The length counts characters, so a padded handle stays a distinct value and reaches the store untrimmed.; challenge_id: str = Field(..., min_length=1)`. The class name above is a suggestion, not a verified fact — naming is Claude's discretion per CONTEXT.md.]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `?challenge=true` mode-signal partition on each endpoint | `POST /auth/challenge` issues for all four operations | Phase 37.2 (D-01/D-03/D-05) | ROADMAP criterion 4 describes machinery that does not exist. D-18 rewords it. `ChallengesDB` needs **zero** edits. |
| Backend rate-limit engine (`limits`, Redis) | Deleted from the product; Envoy is the sole enforcement point | Phase 35 D-05 | The brief's six named budgets for this route have nothing to sit on. The Apple call is bounded only by `tenacity`. |
| `audit.auth_events` durable rows | Structured log lines only | Phase 37.1 D-01, Phase 38 D-03 | The brief's internal result names (`native_claim_already_claimed`, `native_claim_write_failed`, …) survive only as exception class names snake_cased by `app/error_handlers.py::camel_to_snake`. **This is a design input:** name the two error classes so their snake_case reads as the internal result you want in the log. |
| `claim_attempt_id` on the consume condition | `claimed_at IS NOT NULL AND consumed_at IS NULL` | Phase 37.4 D-03 | Verified in the live consume statement [VERIFIED: src/nativespeaker/api/crud/challenges.py:83-86 — `.where(col(AuthChallenge.challenge_id) == challenge_id, col(AuthChallenge.claimed_at).is_not(None), col(AuthChallenge.consumed_at).is_(None))`]. No retry-under-attempt-identity exists. |
| HMAC `idp_account_hash` keyring | Deleted | Phase 37.4 D-11 | Only the deferred web branch needed one. Phase 42 inherits the question. |
| Route registry / `BudgetGate` / `auth/budgets.py` | Deleted | Phase 37.1 D-06, Phase 37 D-04 | Route membership is carried by `tests/unit/test_app_wiring.py` literals alone. |

**Deprecated/outdated:**
- `06-claim-anonymous-grant.md` steps 3, 8 (budget clauses), 11 (user-first lock), and the whole audit paragraph at `:88` describe machinery deleted in phases 35–38. Read CONTEXT.md § "Carried forward" before implementing anything from the brief.
- The brief's `proof_malformed` internal result: D-11 and Claude's Discretion collapse it into the framework's 422 for absent/empty fields and `proof_rejected` for Apple's refusal. Record the divergence under D-17.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 17 | schema tests, dev database | ✓ | 17.11 (per STATE.md 34-01) | — |
| Python | runtime | ✓ | `>=3.14` required by pyproject | — |
| `httpx` | the DeviceCheck adapter | ✓ installed | 0.28.1 | — (but must move to `[project]`, Pitfall 3) |
| `PyJWT[crypto]` + `cryptography` | ES256 signing | ✓ | 2.12.1 / 46.0.5 | — |
| `tenacity` | Apple retry budget | ✓ | 9.1.4 | — |
| Apple DeviceCheck credentials (key ID, team ID, ES256 private key) | a real Apple round trip | ✗ | — | **The scripted fake (D-04).** The adapter's signing and parsing get unit tests; the endpoint gets e2e cases through the fake. |
| An iOS app producing real device tokens | any real end-to-end proof | ✗ | — | None. This is a recorded fact, not a gap the phase can close (D-04). |
| Firebase Admin credential (ADC) | the anonymous e2e sign-in fixture | ? environment-dependent | — | Existing cases already `pytest.skip` with a named reason [VERIFIED: tests/e2e/conftest.py:72-76 — `_NO_ADMIN_CREDENTIAL = ("no Firebase Admin credential: set GOOGLE_APPLICATION_CREDENTIALS (Application Default Credentials) in .env")`]. |
| `respx` | mocking httpx | ✗ | — | `httpx.MockTransport`, built in. Do not add `respx`. |

**Missing dependencies with no fallback:** an iOS app. Accepted by D-04; the plan must not contain a task requiring one.
**Missing dependencies with fallback:** Apple credentials → the scripted fake plus unit tests against documented shapes.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 with pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest -q` (unit only — `addopts = "-v --tb=short -m 'not e2e and not schema'"` deselects the rest) |
| Full suite command | `uv run pytest -q && uv run pytest -m 'e2e or schema' -q && uv run ruff check src tests` |

All values [VERIFIED: pyproject.toml `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `env_files = [".env"]`, `asyncio_mode = "auto"`, `addopts = "-v --tb=short -m 'not e2e and not schema'"`, and the two markers `e2e` and `schema`].

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ANONGRANT-01 | `anonymous_device_grant` is written from exactly one site in `src/` | unit (AST/grep over `src/`) | `uv run pytest tests/unit/test_grant_sources.py -q` | ❌ Wave 0 |
| ANONGRANT-01 | A successful claim returns 200 with the `SyncResponse` body and `Cache-Control: no-store` | e2e via fake gate | `uv run pytest tests/e2e/test_claim_anonymous_grant.py -m e2e -q` | ❌ Wave 0 |
| ANONGRANT-01 | The route is registered, narrowed to linked identities, and in neither exemption set | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ (add the path to the two parametrize lists) |
| ANONGRANT-02 | Grant rows lock ascending by id, then usage rows; no other lock tier first | schema | `uv run pytest tests/schema/test_grant_locks.py -m schema -q` | ✅ extend |
| ANONGRANT-02 | No network call while a lock is held or a transaction is open | unit (structural) | `uv run pytest tests/unit/test_claim_ordering.py -q` | ❌ Wave 0 |
| ANONGRANT-03 | Two concurrent claims yield one grant, one usage row, one anti-abuse row, marker set once, both challenges consumed, loser 200 | schema (two connections) | `uv run pytest tests/schema/test_claim_race.py -m schema -q` | ❌ Wave 0 (D-12) |
| ANONGRANT-03 | Repeat claim on an active free grant answers 200 without reaching Apple | e2e | `uv run pytest tests/e2e/test_claim_anonymous_grant.py -m e2e -q` | ❌ Wave 0 |
| ANONGRANT-03 | Consumed-but-inactive free grant, and an active grant of another source, both answer 403 | e2e | same file | ❌ Wave 0 |
| D-06 | Apple adapter: JWT header/claims, both body shapes, bit1 carried forward, four parse arms | unit (`httpx.MockTransport`) | `uv run pytest tests/unit/test_devicecheck_adapter.py -q` | ❌ Wave 0 |
| D-06 | Every post-claim outcome consumes the challenge; pre-claim rejections do not | e2e + unit | `uv run pytest tests/unit/test_claim_precedence.py -q` | ❌ Wave 0 (mirror `test_upgrade_precedence.py`) |
| D-11 | Both new codes are 403; `ErrorCode` and the tree agree in both directions | unit | `uv run pytest tests/unit/test_error_registry.py tests/unit/test_rejection_vocabulary.py -q` | ✅ no edit needed (Pitfall 11) |
| D-14 | A request in flight when the breaker opens fails on its next attempt with 503 + `Retry-After` | unit | `uv run pytest tests/unit/test_resilience_retry.py -q` | ✅ extend |
| D-15 | The charge commits and releases its connection before a provider permit is taken; the twenty billing cases stay green | unit | `uv run pytest tests/unit/test_quota_seam.py -q` | ✅ reword + extend |
| D-16 | `db.pool_size` resolves to 12 | unit | `uv run pytest tests/unit/test_config.py -q` | ✅ extend |
| C-4/C-5 | Docstring and comment bar stays 0 on every root | unit | `uv run pytest tests/unit/test_docstring_bar.py -q` | ✅ no edit |
| — | `auth/` package shape literal updated | unit | `uv run pytest tests/unit/test_auth_package_shape.py -q` | ✅ **must edit `CURRENT`** |

### Sampling Rate

- **Per task commit:** `uv run pytest -q` (unit; ~2 s, no infrastructure)
- **Per wave merge:** `uv run pytest -q && uv run pytest -m 'e2e or schema' -q`
- **Phase gate:** full suite green plus `uv run ruff check src tests` clean, before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/test_devicecheck_adapter.py` — the adapter's signing and all four parse arms (D-04, D-06)
- [ ] `tests/e2e/test_claim_anonymous_grant.py` + a `scripted_devicecheck_adapter` fixture in `tests/e2e/conftest.py` — covers ANONGRANT-01/03 (D-04)
- [ ] `tests/schema/test_claim_race.py` — covers ANONGRANT-03 (D-12)
- [ ] `tests/unit/test_claim_precedence.py` — rejection precedence and consume-on-every-post-claim-outcome (D-06)
- [ ] `tests/unit/test_grant_sources.py` — the single-writer assertion for ANONGRANT-01
- [ ] `tests/unit/test_claim_ordering.py` — the no-network-under-lock structural assertion for ANONGRANT-02
- [ ] `tests/unit/test_auth_package_shape.py::CURRENT` — **edit**, not create (Pitfall 4)

No framework install is needed.

## Security Domain

`security_enforcement` is not set in `.planning/config.json`; absent means enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Unchanged and not this phase's to build — `get_linked_identity` is the sole place JWT acceptance and identity resolution happen. The route adds no credential path. The DeviceCheck tokens are explicitly **not** identity material. |
| V3 Session Management | yes | The challenge is a single-use capability, never a bearer credential: 300 s TTL, one-way issued→claimed→consumed, one expiry evaluation in the claim's `WHERE`. Already built and unchanged. |
| V4 Access Control | yes | D-08's anonymous-only rule is the new access-control decision. It reads the stored `provider` column and nothing else, and is re-checked inside the transaction against the row a concurrent upgrade may have flipped. |
| V5 Input Validation | yes | Pydantic `Field(..., min_length=1)` on all three body fields; anything absent or empty is the framework's 422 before any business logic. Apple's response is validated positively (Pitfall 2 code) with no permissive default. |
| V6 Cryptography | yes | `PyJWT[crypto]` for ES256. **Never hand-roll the DER→JOSE conversion.** The private key is a PEM secret: `.env` only, never `config.yaml` (which is tracked in git — the file says so itself). |
| V7 Error Handling & Logging | yes | One-field error body; the anti-oracle rule means every 403 `operation_not_allowed` branch is byte-identical to the client. Bounded `stage`/`cause` log fields from a closed set. No logger in the token-handling module. |
| V9 Communications | yes | HTTPS to `api.devicecheck.apple.com`; `httpx` verifies certificates by default and that default must not be disabled anywhere, including in tests (use `MockTransport`, never `verify=False`). |
| V14 Configuration | yes | Production DeviceCheck environment only. The development host must not be reachable by any client input — environment selection is server config, and D-01's deferral of a dev bypass makes it a non-target. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Client asserts its own DeviceCheck bit state | Spoofing | Never accept client-supplied bit values; the backend performs its own read every claim, with no caching or coalescing (D-06). |
| Replaying a device token to claim twice | Elevation of privilege | Two-ledger model: Apple's bit0 is authoritative for the device slot and is set *before* activation; the unique indexes are authoritative for the account. Neither substitutes for the other. |
| Enumerating which accounts hold grants via differing 403 bodies | Information disclosure | All three D-09 refusals share one `operation_not_allowed` class with one body, declared once on a base so no leaf can drift (the `ChallengeRejected`/`UpgradeRefused` pattern; `tests/unit/test_rejection_vocabulary.py` enforces it). |
| A raw device token in a log line, a row, or an error string | Information disclosure | No logger in the seam module; `stage`/`cause` from a closed set; the error body carries one field (Pitfall 15). |
| Unbounded Apple calls from one eligible token holder | Denial of service (against Apple, and the vendor budget) | Knowingly accepted and recorded as D-20, on the Phase 37 D-01 precedent. Mitigating: one account looping on itself, and D-03's preflight refuses ineligible accounts before Apple is reached. Closes with the v2.1 gateway contract. |
| A crash between the confirmed bit write and the commit | Denial of service (self-inflicted, one device) | Accepted and uncompensated by D-06; remediation is an operator `manual` grant. Do **not** build a pending-state machine or a reconciler — `SHARED-INVARIANTS.md:59` forbids *"scheduled cleanup, purge, reconciliation, recovery-scan, or background-healer job of any kind"*. |
| Failing open on an ambiguous Apple response | Tampering / elevation | The fourth parse arm raises rather than defaulting; an exhausted budget becomes `Unavailable`, never success (`SHARED-INVARIANTS.md:27`: *"never treat an exhausted retry or budget as success"*). |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DeviceCheck hosts are `https://api.devicecheck.apple.com` (production) and `https://api.development.devicecheck.apple.com`; paths `/v1/query_two_bits` and `/v1/update_two_bits` | Code Example 2, Diagram | Every Apple call 404s. Cheap to detect against a real credential; invisible until then. Two independent sources agree. |
| A2 | The service JWT is ES256 with `kid` in the header and `iss` (team ID) + `iat` (seconds) as claims, sent as `Authorization: Bearer <jwt>` | Code Example 2 | 401 from Apple on every call. **One source additionally claims `sub` (bundle ID) and `exp` are required; the other does not mention them.** Sources disagree — see OQ-1. |
| A3 | Query and update bodies carry `device_token`, `transaction_id`, `timestamp` (ms since epoch); the update adds `bit0` and `bit1` | Code Example 2 | 400 from Apple. Field names came from secondary sources only. |
| A4 | `update_two_bits` writes both bits, so `bit1` must be carried forward from the query | Pitfall 1, Code Example 2 | If wrong in the *other* direction (bit1 omissible), carrying it forward is harmless. If right and ignored, Phase 42's bit is silently destroyed. **Asymmetric — implement as if true.** |
| A5 | A never-set device answers HTTP 200 with plain text `Failed to find bit state` / `Bit State Not Found` | Pitfall 2, Code Example 3 | If the string differs, every first claim 503s. The fourth parse arm makes this fail closed rather than open, so the cost is an outage, not a breach. Widen `_NEVER_SET_BODIES` when a real response is seen. |
| A6 | The seeded anonymous tier's `access_tiers.id` is the literal `"anonymous"` | Code Example 6 | FK violation on every insert. Asserted in STATE.md (36-01) but the migration's `INSERT INTO core.access_tiers` was **not opened this session** — read it before writing the literal. |
| A7 | `pip index versions` being unavailable, package currency was verified against the installed environment rather than the registry | Standard Stack | Low: nothing is newly introduced, and the installed set is what actually runs. |
| A8 | Adding `db: pool_size: 12` to `config.yaml` deep-merges with `DB_*` env nesting rather than replacing the block | Pitfall 14 | If wrong, the app fails to boot on missing `db.host`. The `jwt` block is a live, working precedent for the same shape, so confidence is high — but pydantic-settings' merge semantics were reasoned about, not executed. **Cheap to settle: boot the app once after the edit.** |

**Every `[ASSUMED]` claim above is about Apple's wire format or one unread file.** Every claim about this repository's code, schema, tests and configuration was read from source this session and is tagged `[VERIFIED]` with a path, a line range and a verbatim quote.

## Open Questions

1. **Does Apple's DeviceCheck JWT require `sub` (bundle ID) and `exp`?**
   - What we know: both sources agree on ES256, `kid`, `iss` (team ID) and `iat`. One adds `sub` = bundle ID and `exp`.
   - What's unclear: whether the extra claims are required, ignored, or that source conflating DeviceCheck with App Attest / App Store Connect JWTs (which do require them).
   - Recommendation: include `iss`/`iat` for certain. Make the claim set a single private function so adding `sub`/`exp` is a one-line change when a real 401 says so. Do not guess a bundle ID into config that nothing verifies.

2. **How is the ES256 private key carried in `.env` — base64 or a mounted path?** (D-05 explicitly leaves this to the planner.)
   - What we know: it is a multi-line PEM, and `.env` is line-oriented. `.env.example`'s existing precedent for Firebase ADC is a **path** to a file kept outside the repo, mode 600.
   - Recommendation: follow that precedent — `DEVICECHECK_PRIVATE_KEY_PATH`, read once at boot in `lifespan`. It matches the neighbouring secret, avoids an encode/decode step, and keeps the key out of process environment dumps. Base64 is the better answer only if the deployment cannot mount a file, which is unknown here.

3. **Does the plan fold the two todos into their own wave?** (D-15 flags this as discretion.)
   - What we know: `resilience.py`, `services/llm.py`, `tests/quota_seam.py` and `config.py`/`config.yaml` share no file with the endpoint work.
   - Recommendation: yes — a separate parallel wave. Zero file overlap means zero merge risk, and the endpoint wave is the long pole.

4. **Should `_complete` become generic, or should the claim get its own sibling method?**
   - What we know: Phase 40 D-16 forbids duplicating the locate-claim-commit-spend sequence; `_complete` returns `IdentityProvider` today and this route returns an entitlement.
   - Recommendation: generic over the post-claim result, with `post_claim` injected. A sibling method would copy the rejection precedence, which is the exact thing D-16 exists to prevent. If the generic version reads badly to the plan-checker, the fallback is `_complete` returning the post-claim callable's result untyped — worse, but still one sequence.

5. **Where does the D-08 claimant check live — router or service?**
   - What we know: `AGENTS.md` says a service is earned by complexity and a router may call `crud/` directly; the check must *also* happen inside the transaction, where only the service is.
   - Recommendation: service only. A router-level pre-check would be a second copy of one rule, against the developer's stated "fewer copies of one fact". The transaction-internal re-read is the authoritative one; put the early refusal immediately beside it in the same method.

## Sources

### Primary (HIGH confidence)

- `ns-api-gateway` source, read this session: `services/auth.py`, `services/sync.py`, `services/quota.py`, `crud/grants.py`, `crud/identities.py`, `crud/challenges.py`, `tables/grants.py`, `tables/identities.py`, `tables/auth.py`, `errors.py`, `routers/auth.py`, `schemas/auth.py`, `config.py`, `resilience.py`, `app/dependencies.py`, `app/lifespan.py`, `auth/firebase.py`, `auth/adapters.py`
- `migrations/20260818_01_initial-release.sql` lines 70-109, 205-330, 360-382 — every schema fact quoted above
- `tests/unit/test_auth_package_shape.py`, `test_error_registry.py`, `test_app_wiring.py`, `test_docstring_bar.py`, `test_adapter_interfaces.py`; `tests/schema/test_create_race.py`; `tests/e2e/conftest.py`
- `pyproject.toml`, `config/config.yaml`, `.env.example`, `.planning/config.json`, `uv pip list`
- `specs/auth-refactor-phases/SHARED-INVARIANTS.md` §§ Fail-closed defaults, Locks and transactions, Grants and evaluation time, Errors, Global deletions
- `specs/auth-refactor-phases/06-claim-anonymous-grant.md` (the brief, verbatim)
- `specs/auth-refactor/03-free-credit-grants-and-anti-abuse.md` §§ iOS Device-Check Adapter, `POST /auth/claim-anonymous-grant`; `05-proof-adapters-and-derived-identifiers.md` § iOS Proof Adapter
- `.planning/phases/41-post-auth-claim-anonymous-grant/41-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `AGENTS.md`

### Secondary (MEDIUM confidence)

- PyJWT official usage documentation via Context7 — ES256 encoding and custom `kid` headers: https://github.com/jpadilla/pyjwt/blob/master/docs/usage.md

### Tertiary (LOW confidence — Apple's own documentation could not be fetched)

- https://adjoe.io/company/engineer-blog/prevent-fraud-on-ios-with-apple-devicecheck-and-app-attest/ — hosts, paths, JWT shape, body fields, both-bits update, `last_update_time` format
- https://blog.restlesslabs.com/john/ios-device-check — development host, three paths, JWT header/claims, request/response bodies, `Failed to find bit state`
- https://developer.apple.com/forums/thread/128746 and https://developer.apple.com/forums/thread/651944 — the 200-with-plain-text never-set response, reported independently by multiple developers
- https://github.com/rinchsan/device-check-go — an independent implementation carrying an `ErrBitStateNotFound` sentinel, corroborating that the never-set case is a distinct non-error state
- **Attempted and failed:** `https://developer.apple.com/documentation/devicecheck/accessing-and-modifying-per-device-data` returned only a page title (JavaScript-rendered). A planner or executor with a real Apple Developer account should confirm A1–A5 against that page before the first live call.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — nothing new; every version read from the installed environment and `pyproject.toml` this session.
- In-repo architecture, schema and test facts: **HIGH** — every claim carries a path, a line range and a verbatim quote from a file opened this session.
- Apple DeviceCheck wire format: **LOW** — no official page was fetchable; two independent secondary sources plus an independent implementation agree, which is corroboration but not authority. Assumptions A1–A5 are the ones to confirm first, and A4's asymmetry means the safe implementation is also the correct one if A4 holds.
- Pitfalls: **HIGH** for 3–15 (all verified in-repo), **LOW** for 1–2 (they rest on A4 and A5).
- The two folded todos: **HIGH** — `resilience.py` was read in full and every line cited.

**Research date:** 2026-09-02
**Valid until:** 2026-10-02 for the in-repo facts (stable, and the phase should land well inside it). The Apple facts have no expiry but no floor either — treat the first real 400 or 401 from Apple as authoritative over anything in this document.
