---
phase: 37
iteration: 1
fixed_at: 2026-09-09
review_path: .planning/phases/37-post-auth-create-user/37-REVIEW.md
fix_scope: critical_warning
findings_in_scope: 11
fixed: 10
skipped: 1
status: partial
---

# Phase 37: Code Review Fix Report

**Source review:** `.planning/phases/37-post-auth-create-user/37-REVIEW.md`
**Iteration:** 1
**Branch:** `gsd/v2.0-authentication-entitlements`

## Summary

- Findings in scope: 11 (CR-01, CR-02, WR-01 through WR-09)
- Fixed: 10
- Skipped: 1 (WR-02)

Info findings IN-01 through IN-08 were out of scope and were not touched.

## Verification

All three gates ran in the main checkout, on this repository's branch. No worktree
was used. Every gate ran after each fix and again at the end.

| Gate | Baseline at `7593fb3` | Final at `b872ca4` |
|---|---|---|
| `.venv/bin/ruff check src tests` | clean | clean |
| `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1325 passed | 1352 passed |
| `.venv/bin/ty check src` | 47 diagnostics | 39 diagnostics |

The unit suite grew by 27 cases. The `ty` count fell by 8: WR-08 removed the eight
`unresolved-attribute` reports on `violation.orig.sqlstate`.

`git status --short` is clean apart from this uncommitted report.

## Fixed Issues

### CR-01 — already fixed

**Commit:** `7593fb3` "fix(37): CR-01 raise the App Store callback body bound"

Fixed before this pass. `APP_STORE_ENVELOPE_LIMIT` is 65536 and `PUBSUB_DATA_LIMIT`
stays at 16384, with the two bounds parameterised separately in
`tests/unit/test_models.py`. Not re-fixed.

### CR-02 — no `HTTPRoute` matched `/auth/*` or `/`

**Commit:** `eb9c03a`
**Files:** `k8s/templates/httproute-auth.yaml` (new),
`k8s/templates/security-policy.yaml`, `k8s/templates/NOTES.txt`

A new `auth-routes` `HTTPRoute` matches `PathPrefix /auth` and `Exact /`, and joins
`app-routes` and `llm-routes` in the JWT `SecurityPolicy` `targetRefs`. The route
enumeration in `NOTES.txt` names it. Every route this milestone added now reaches the
pod. The pre-auth-callable routes keep the JWT policy: an unlinked caller still
presents a verified token, and the unlinked decision stays in the backend barrier.

### WR-01 — `ChallengeRequest.operation` was unbounded and is logged verbatim

**Commit:** `dda83be`
**Files:** `src/nativespeaker/api/schemas/auth.py`,
`tests/unit/test_challenge_endpoint.py`

`operation` now carries `max_length=64`, matching the sibling `RestoreRequest.provider`
and standing well above the 31-character longest member of `core.auth_operation`.

`min_length=1` was **not** applied, against the review's suggestion.
`tests/unit/test_challenge_endpoint.py:154` lists the empty string in
`_OUTSIDE_THE_VOCABULARY` and requires it to answer 400 `invalid_request` like every
other unissuable string. A `min_length` would answer 422 for the empty string alone
and make it distinguishable, breaking the anti-oracle rule and a passing test. The
finding's root cause is the unbounded length, and that is what the fix removes.

Three new cases read the bound off the model, assert an oversized value is the
framework's 422 and never reaches the store, and assert a value at the bound is still
the handler's 400.

### WR-03 — three failure paths answered 500 with no log line

**Commit:** `b80f377`
**Files:** `src/nativespeaker/api/auth/google_play.py`,
`src/nativespeaker/api/auth/app_store.py`, `src/nativespeaker/api/errors.py`,
`tests/unit/test_google_play_notifications.py`,
`tests/unit/test_app_store_notifications.py`,
`tests/unit/test_rejection_vocabulary.py`

- `_play_answer_is_usable` logs `google_play_read_refused` with the status code.
- `read()` logs `google_play_read_transport_failed` with the exception class name
  only. The exception text carries the URL, and the URL is the purchase token.
- `app_store.py` raises the new `UnknownStoreSubscriptionStatus(InternalError)` at
  `log_level = ERROR`, carrying the provider name. A named class rather than a logger,
  because that module holds attribution tokens and deliberately has no logger.

`UnknownStoreSubscriptionStatus` was added to the recorded event vocabulary and to the
constructor table in `test_rejection_vocabulary.py`, which are the two registries a new
error class must join. New cases assert each of the three log lines.

### WR-04 — the burst limit keyed on a forbidden, never-populated, forgeable header

**Commit:** `ed99b1c`
**Files:** `k8s/templates/security-policy.yaml`,
`k8s/templates/backend-traffic-policy.yaml`, `k8s/values.yaml`,
`k8s/templates/NOTES.txt`

`claimToHeaders` is gone from the `SecurityPolicy`. `SHARED-INVARIANTS.md` forbids it:
*"the gateway forwards `Authorization` unchanged, injects no identity headers, and the
backend ignores every client/proxy identity header"*, and *"No claim-header
authentication or header-derived identity"*. Nothing read the header.

The four tier rules keyed on `x-user-plan` are replaced by one rule with no
`clientSelectors`: one bucket per Envoy pod for `POST /chats`, which no client header
can influence. `values.yaml` collapses to `rateLimits.burst.requests` (60) and
`unit`. The tier names had no counterpart in the entitlement model
(`anonymous`/`registered`/`paid`) either.

**Not done, and why.** The bucket is route-wide per pod, not per source address.
A distinct-per-IP key is an Envoy Gateway *global* rate limit, which needs a
rate-limit service deployment. That is infrastructure work, and the phase-45 context
already defers it ("Gateway rate limits on the auth surface ... the v2.1 gateway
contract"). No Envoy Gateway CRD is vendored here and there is no network, so a
`sourceCIDR` selector could not be verified; a field the controller rejects would
leave the policy unreconciled, which is worse than what stands. The backend still
charges the monthly allowance per grant and caps in-flight work.

### WR-05 — the gateway 429 named the wrong error class

**Commit:** `e565412`
**File:** `k8s/templates/backend-traffic-policy.yaml`

The `responseOverride` body is now `{"code":"rate_limited"}`, the foundation-registered
429 class `SHARED-INVARIANTS.md` names. `quota_exceeded` is the registered
specialization for the monthly allowance, raised only by `QuotaService.charge`, and it
tells the client the month is spent and must not be retried — the opposite of a burst
rejection.

**Not done, and why.** `Retry-After` was not added. Envoy Gateway's `responseOverride`
`response` block exposes `contentType` and `body`; no header field is verifiable here
(no vendored CRD, no network), and guessing one would leave the policy unreconciled.
The review's alternative, a `ResponseHeaderModifier` on the `llm-routes` rule, cannot
match on response status, so it would stamp `Retry-After` on every 200 as well. That
is a new defect, not a fix. The header remains open work for the gateway phase.

### WR-06 — lint and type-check tooling shipped as runtime dependencies

**Commit:** `a9bd143`
**Files:** `pyproject.toml`, `uv.lock`

`ruff==0.15.7` and `ty==0.0.24` are removed from `[project].dependencies`. The `dev`
group already declares both, so the local `.venv` is unchanged and all three gates
still run. `uv lock --offline` refreshed the lockfile; the diff is four lines, all of
them the two removed entries.

**Observed, not fixed.** `Dockerfile:8` runs `uv sync --frozen --no-group test`, and
there is no `test` group — the group is named `dev` — so the image still syncs the dev
group and still installs both linters. That is a separate defect in a file the review
did not raise, and the same Dockerfile also copies from `/nativespeaker/app/.venv`,
a path the builder stage never creates. Both belong in their own finding.

### WR-07 — a test-only Firebase secret was a required boot parameter

**Commit:** `16e06ed`
**Files:** `src/nativespeaker/api/config.py`, `tests/e2e/conftest.py`,
`tests/unit/test_config.py`, `.env.example`

`JWTConfig.api_key` is now `SecretStr | None`, defaulting to `None`. No request path
reads it; only the e2e harness does, to mint tokens against Identity Toolkit. A
deployment no longer carries a credential it never uses, and the value no longer
renders in a `repr` or a model dump.

`tests/e2e/conftest.py` reads it through one new accessor, `_identity_toolkit_key`,
which unwraps the secret and holds the loud assertion. Four call sites went through it,
replacing three duplicated reads. Two new unit cases assert a deployment without the
key boots, and that the key appears in neither a `repr` nor a dump.

### WR-08 — `violation.orig` was dereferenced without a null check in eight places

**Commit:** `f05bba8`
**Files:** `src/nativespeaker/api/crud/violations.py` (new),
`src/nativespeaker/api/crud/grants.py`,
`src/nativespeaker/api/crud/subscriptions.py`,
`tests/unit/test_restore_proof.py`

One new crud module holds `UNIQUE_VIOLATION` and `is_unique_violation`, which reads
the code with `getattr(violation.orig, "sqlstate", None)`. All eight arms call it.
An absent or unreadable code is not a race, so the caller re-raises rather than
swallowing a broken invariant as a lost race.

`pgcode` is not also read. This deployment runs asyncpg, the DSN is
`postgresql+asyncpg`, and a second driver's attribute would be untested speculation.
The `getattr` already fails closed for any other driver, which is the right answer.

Six new cases: the arbiter's own code is a race, four other codes are not, an absent
DBAPI exception is not, another driver's shape is not, and an `IntegrityError` with
`orig` unset propagates through the writer as `IntegrityError` rather than
`AttributeError`.

The eight `ty` diagnostics this finding named are gone; the count fell 47 to 39.

### WR-09 — a missing usage row on the conversion minted a fresh allowance

**Commit:** `b872ca4`
**Files:** `src/nativespeaker/api/crud/grants.py`,
`tests/unit/test_conversion_carries_usage.py` (new)

`activate_registered_account_grant` now separates the two cases the single expression
conflated. A superseded grant whose usage row is missing raises
`MissingUsageRowError`; `carried is None` below now means "no superseded grant" alone.
`SHARED-INVARIANTS.md`: *"A missing usage row for an existing grant fails closed —
never lazily minted."*

The raise sits before the expiry write, so the refused attempt mutates no row.

A new unit file drives the writer directly, because every other unit suite replaces the
whole writer with a recorder. Four cases: the control carries the period and the count
across; the missing row raises and names the grant; the refusal adds nothing and leaves
the superseded grant active; and a control proves the carried month is not the captured
month, so neither case passes vacuously.

Both schema fixtures that drive this writer (`_registered_writer_run` and
`_account_holding` in `tests/schema/test_grant_locks.py`) seed a usage row for every
grant, so no schema test is affected.

## Skipped Issues

### WR-02 — an Apple subscription in `grace_period` can never be restored

**Verdict:** skipped — open design decision, recorded and deliberate.
**File:** `src/nativespeaker/api/services/restore.py:58-67`, root cause at
`src/nativespeaker/api/auth/app_store.py:147`.

The finding holds. It is also a recorded decision, not a defect that a review fix may
settle.

`10-restore-subscription.md` step 8 requires the fix the review calls option 1:
*"Adoption only: **live store-state verification** — exactly **one** outbound provider
call (Apple App Store Server API, e.g. Get All Subscription Statuses, for the verified
`originalTransactionId` ...)"*.

Phase 45 decided against it and recorded the conflict against that clause.
`.planning/phases/45-post-auth-restore-subscription/45-CONTEXT.md` D-04:

> **D-04: Apple is verified locally, never live.** ... No App Store Server API client,
> no new Apple key, no `Get All Subscription Statuses` call on adoption (44 D-13
> stands). Accepted blind spot: a subscription this server has never heard of, refunded
> after the proof was signed, gets a grant until the next webhook. **FLAGGED CONFLICT**
> against brief steps 8 and 17 ...

The same file defers the second route to a fix under "Deferred Ideas":

> **Apple live status from the App Store Server API** (`Get All Subscription Statuses`)
> — declined again (D-04). Reopen if the refund blind spot ever costs more than it
> saves; it is one class, one key and one call before the transaction.
>
> **The renewal-info JWS as a second Apple proof field** — would make grace and billing
> retry visible on restore. Not this phase.

Building either means a new Apple credential, a new outbound integration and a new
config surface. That is a product and infrastructure decision, the `needs-decision`
kind in `specs/oft-conventions.md`, and it belongs to the restore phase rather than to
this fix pass.

The review's option 2 — restating the limitation in the `restore()` docstring and in
the route `description=` — was not applied either. It changes no behaviour, and the
client-visible OpenAPI description is a wire-contract edit that the same decision
should settle. The limitation is currently visible in the name of the passing test
`tests/e2e/test_restore_subscription.py:323`,
`test_a_stored_grace_row_and_an_apple_proof_attaches_nothing`.

**Open question for the restore phase.** An Apple subscriber in `grace_period` is told
they have no subscription on a new device. Decide between the live App Store Server API
read (spec-conforming, needs a key) and the renewal-info JWS as a second proof field
(no key, needs a client change), or accept the limitation in writing.

---

_Fixed: 2026-09-09_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
