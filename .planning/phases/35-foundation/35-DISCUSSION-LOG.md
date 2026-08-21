# Phase 35: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-20
**Phase:** 35-Foundation
**Areas discussed:** Barrier wiring mechanism, Error registry vs existing stack, Verification with a dead app, HMAC key material, Module layout, Envoy §9 deliverable

---

## Barrier wiring mechanism

### How the barrier attaches

| Option | Description | Selected |
|--------|-------------|----------|
| ASGI middleware | Genuinely default-on; matches route itself for metadata, session from `app.state.session_factory`, returns error responses directly since middleware sits outside `ExceptionMiddleware` | ✓ |
| Custom APIRoute class | DI and exception handlers work normally, but opt-in per router — "default-on" becomes the assertion's job | |
| Router-level Depends() | Closest to existing convention; weakest default-on story | |

**User's choice:** ASGI middleware.

### Handler-facing seam

| Option | Description | Selected |
|--------|-------------|----------|
| Depends() accessor | Typed accessors in `app/dependencies.py` reading one request-scoped object off `request.state`; raise when the barrier did not run | ✓ |
| Direct request.state access | Fewer moving parts, but routes touch `Request` again and each of 7 phases re-implements the fail-loudly check | |
| You decide | | |

**User's choice:** Depends() accessor.

### FastAPI's auto-registered doc routes

| Option | Description | Selected |
|--------|-------------|----------|
| Turn them off | `docs_url=None`, `redoc_url=None`, `openapi_url=None`; registered set contains only declared routes | ✓ |
| Declare them authenticated | Honest, but /docs behind a Firebase token is unusable | |
| Exclude from the assertion | Creates a registered-but-undeclared category — the hole §2.3 exists to close | |

**User's choice:** Turn them off.

### Rate-limit engine placement

| Option | Description | Selected |
|--------|-------------|----------|
| Separate middleware, ahead | RequestLogging → RateLimitAdmission → Barrier | (voided) |
| One combined middleware | Admission and barrier as sequential phases in one middleware | |
| You decide | | |

**User's choice:** "Separate middleware, ahead" — then voided by the next answer, which removed backend rate limiting entirely.

---

## Rate limiting (raised by the user mid-area)

**User's intervention:** "Let's remove all rate-limiting from the python app. Everything will be handled by the Envoy Gateway, not in the scope of this milestone."

Blast radius presented before confirming: FOUND-06 dropped; `SHARED-INVARIANTS.md` § Rate limits and `01-foundation.md §5` contradicted, requiring a flagged override; `quota_checked_request` keyed on the internal `core.users.id` cannot move to a gateway that only sees the JWT `sub`, so Phase 36's REBIND-04 changes; §7.1 provider-call budgets are in-request call metering no gateway can express; `rate_limited` stays in the registry either way because §9 requires Envoy's 429 override to name it.

| Option | Description | Selected |
|--------|-------------|----------|
| Drop traffic limits, keep call budgets | No limits library, Redis, or config block; keep the §7.1 budget seam as in-process counters for phases 37/40/41/42 | ✓ |
| Drop all of it | Nothing rate-limit-shaped at all; §7.1 budget gating disappears | |
| Defer, don't delete | FOUND-06 to backlog rather than reversed | |

**User's choice:** Drop traffic limits, keep call budgets.

---

## Error registry vs existing stack

### Module shape

| Option | Description | Selected |
|--------|-------------|----------|
| One module absorbs both | Registry owns the seven auth classes plus existing business classes, codes and statuses verbatim | ✓ |
| Auth registry alongside | Smaller diff; two modules own client-visible shapes | |
| You decide | | |

**User's choice:** One module absorbs both.

### The existing 401 code

| Option | Description | Selected |
|--------|-------------|----------|
| Retire "unauthorized" | `auth_required` becomes the only 401; tests and k8s references updated | ✓ |
| Keep both | Nothing breaks, but two 401 codes mean the same thing to a client | |
| You decide | | |

**User's choice:** Retire it.

### Framework-generated errors and `_STATUS_REMAP`

**User's question:** "Why do I need to remap the status codes?"

Answered: the remap is a v1.3 artifact of the five-status-code lock, which v2.0 reverses — and its `409 → 400` entry now collides with `challenge_required`.

| Option | Description | Selected |
|--------|-------------|----------|
| Delete it; declare the classes | Registry declares a class for every emittable status; each framework exception maps to one declared class with its honest status | ✓ |
| Keep a minimal remap | Drop the 409 entry, keep the rest | |
| You decide | | |

**User's choice:** Delete it; declare the classes.

### Anti-oracle timing

| Option | Description | Selected |
|--------|-------------|----------|
| Structural only | Identical status/body/copy per class, both `account_unavailable` branches through the same path and query; no timing padding, documented | ✓ |
| Add timing normalization | Pad rejections to a fixed floor | |
| You decide | | |

**User's choice:** Structural only.

---

## Verification with a dead app

### What "verified" means

| Option | Description | Selected |
|--------|-------------|----------|
| Make it boot | Repair the model layer here; assertion runs at real startup against the real router | ✓ |
| Synthetic test app | Verify against a fixture-built app; first real proof lands in Phase 36 | |
| Only what the routes need | Rewrite just foundation's models; assertion still cannot run at startup | |

**User's choice:** Make it boot.

### How far "boots" reaches

| Option | Description | Selected |
|--------|-------------|----------|
| Starts clean, chat paths still broken | Imports, lifespan, startup succeed; chat quota path fails at runtime until Phase 36 | ✓ |
| Fully working chat routes | Absorbs REBIND-04/05 into an already 8-subsystem phase | |
| You decide | | |

**User's choice:** Starts clean, chat paths still broken.

### Test placement

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse unit + e2e | Pure logic in unit, real-PostgreSQL/running-app coverage in e2e; `tests/schema` untouched | ✓ |
| New tests/foundation/ package | Third topology, duplicating e2e fixtures once the app boots | |
| You decide | | |

**User's choice:** Reuse unit + e2e.

### Database access from middleware

| Option | Description | Selected |
|--------|-------------|----------|
| SQLModel session factory | Both take sessions from `app.state.session_factory`; audit writer accepts a caller session for in-transaction mode | ✓ |
| Raw asyncpg for the barrier | Faster hot path; second DB idiom and second pool | |
| You decide | | |

**User's choice:** SQLModel session factory.

### Legacy v1.6 surfaces

| Option | Description | Selected |
|--------|-------------|----------|
| Delete what later phases replace | Remove `/webhooks/apple`, subscription service/DB, old usage DB, and `/users/me` unless it serves unchanged | ✓ |
| Keep and repair minimally | Real work on code with a known deletion date | |
| You decide | | |

**User's choice:** Delete what later phases replace.

### Test passing bar

| Option | Description | Selected |
|--------|-------------|----------|
| Delete dead tests, keep the rest green | Phase 36 starts from a known-good baseline | ✓ |
| Mark them xfail | Explicit checklist for Phase 36, but the phase ends with known failures | |
| You decide | | |

**User's choice:** Delete dead tests, keep the rest green.

---

## HMAC key material

### Where key material lives

| Option | Description | Selected |
|--------|-------------|----------|
| Env-only, versioned map | Active version integer plus version→SecretStr map from environment | |
| Single key, no map | One key plus a version integer | |
| You decide | | |

**User's choice (free text):** "For now, let's store everything in the config file, including secrets." Plus a request to capture a todo for retrieving all secrets via `google.cloud.secretmanager`.

Flagged in response: `config/config.yaml` is tracked in git while `.env` is not, so this would commit key material.

| Option | Description | Selected |
|--------|-------------|----------|
| Untrack config.yaml | Single file with secrets, gitignored, with a committed `config.example.yaml` | |
| Tracked, secrets committed | Clone and run; keys permanently in history | |
| Keep .env for secrets only | No change to secret handling | |

**User's choice (free text):** "Use pydantic-settings to use both the config file and the environment variables. Store HMAC in the config file, keep the existing secrets in .env." — i.e. the existing split is kept, with HMAC key material added to the tracked config file. Consequence accepted knowingly; the Secret Manager todo is the mitigation.

### Key coupling

| Option | Description | Selected |
|--------|-------------|----------|
| One shared key | Same key for audit `actor_subject_hash` and challenge `preauth_subject_hash`, per §4.3/§6.4; rotation invalidates outstanding challenges | ✓ |
| Separate keys per purpose | Operationally gentler; contradicts two explicit spec statements | |

**User's choice:** One shared key.

### Missing key versions at startup

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed only on the active key | Missing older version is a warning; no request path needs it | ✓ |
| Fail closed on any gap | Keys can never be retired; losing an old key bricks the app | |
| You decide | | |

**User's choice:** Fail closed only on the active key.

---

## Module layout

### Where the subsystems live

| Option | Description | Selected |
|--------|-------------|----------|
| New auth/ subpackage | `src/nativespeaker/api/auth/` absorbing the existing `auth.py`; one import root for phases 36–46 | ✓ |
| Flat modules alongside | Seven more files at package root, nothing marking them as one seam | |
| You decide | | |

**User's choice:** New auth/ subpackage.

### Where the error registry lives

| Option | Description | Selected |
|--------|-------------|----------|
| Package root | Registry owns every client-visible class, not just auth ones; `auth/` holds only auth machinery | ✓ |
| Inside auth/ | One unambiguous module; quota and LLM errors under an auth package | |
| You decide | | |

**User's choice:** Package root.

---

## Envoy §9 deliverable

| Option | Description | Selected |
|--------|-------------|----------|
| Helm config + contract doc | Update `k8s/` for real plus a short contract doc | |
| Document the contract only | Doc now, chart later | |
| Full gateway rework | Whole chart including the global rate-limit service | |

**User's choice (free text):** "The gateway contract should be moved to the next milestone. I don't want to do it now."

**Notes:** Consequences stated and accepted — v2.0 ships with no new rate limiting anywhere, Envoy's 429s keep their empty body, and `xff_num_trusted_hops` stays unpinned so the client address recorded in audit `details` is trusted rather than proven. None affects foundation's correctness; §9 is explicit that the backend is the sole authoritative verifier.

---

## Claude's Discretion

- Exact `hmac:` config block shape and its Pydantic model
- How the barrier middleware resolves the matched route to read metadata before dispatch
- Raw ASGI middleware vs `BaseHTTPMiddleware`
- Module and file split inside `auth/`, and naming of the typed identity-context classes
- Which class covers 405/415
- Whether the canonical client IP stays in the request context now that it keys nothing
- Whether `GET /users/me` can serve unchanged or is deleted
- Test file organization within `tests/unit` and `tests/e2e`
- Inline commenting depth on redaction rules and the admission matrix

## Deferred Ideas

- Envoy gateway contract (FOUND-09 / §9) — next milestone
- Backend rate limiting (§5) — removed, not deferred; recorded for if abuse traffic appears
- `quota_checked_request` admission (Phase 36 REBIND-04) — void
- Timing normalization for anti-oracle guarantees — explicitly not built
- Google Secret Manager for all secrets — `.planning/todos/pending/secret-manager-integration.md`
- Fully working chat routes in Phase 35 — rejected; Phase 36's REBIND-04/05
