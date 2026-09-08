# Phase 45: POST /auth/restore-subscription — Research

**Researched:** 2026-09-07
**Domain:** Native store-artifact verification (Apple StoreKit 2 JWS, Google Play `subscriptionsv2`) and
conditional subscription-ownership transfer inside one locked PostgreSQL transaction.
**Confidence:** HIGH on the codebase inventory and the schema; MEDIUM on the two store libraries' wire
semantics; LOW on nothing that this phase must decide.

**Nothing new is installed.** Every symbol this phase needs already exists in `src/` or in a package
already pinned in `pyproject.toml`. The research below is therefore an inventory of what is reusable,
what must be added, and the six places where the existing code will fight a naive implementation.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Copied verbatim from `45-CONTEXT.md` § Implementation Decisions.

**The body and the surface gate**

- **D-01: Two fields.** The request model carries `provider` and `restore_proof`, both required
  and non-empty (`min_length=1`, framework 422 otherwise). `provider` is a plain `str`, as
  `ChallengeRequest.operation` is, never a `Literal` or the enum: a value outside
  `PurchaseProvider` is the handler's 403 `operation_not_allowed` through a new leaf, not a 422.
  The provider only picks which verifier runs. A wrong declaration cannot succeed: an Apple JWS
  sent as `google_play` fails the Play read, a Play token sent as `apple` fails the chain check.

- **D-02: The proof is the gate.** RESTORE-02's "non-native surface" is a caller that declares no
  store-artifact family (D-01's 403) or presents an artifact that does not verify (`proof_rejected`).
  Nothing else is checked: no platform header, no `native_claim_platform` comparison, no attempt to
  tell an iPhone from an Android phone. A web client cannot obtain a store artifact, and a fabricated
  one fails verification. "One store's artifact presented from the other platform" is not detected:
  the server has no signal for it, and Apple's signed word about an Apple subscription is the same
  from any device. **FLAGGED CONFLICT** against `10-restore-subscription.md` § Request contract
  (the web-call and other-platform clauses of the surface gate).

- **D-03: Anonymous accounts may restore.** The route sits behind `get_linked_identity` and reads
  no provider column. `restore_destination_anonymous` is not built. The user's reasoning: with
  D-10's cap, one receipt serves at most two accounts in a month, an accepted loss on a sub-$5
  subscription; a stolen proof is a risk of restore in any form and anonymous adds none.
  **FLAGGED CONFLICT** against the brief's "Destination must be an active, **registered** account"
  and its `restore_destination_anonymous` result.

**The store checks**

- **D-04: Apple is verified locally, never live.** The Apple proof is the StoreKit 2 signed
  transaction (`Transaction.jwsRepresentation`). The existing `SignedDataVerifier` on
  `app.state.app_store_notifications` verifies it with `verify_and_decode_signed_transaction`:
  signature and chain against the vendored root, bundle id, environment. No App Store Server API
  client, no new Apple key, no `Get All Subscription Statuses` call on adoption (44 D-13 stands).
  Accepted blind spot: a subscription this server has never heard of, refunded after the proof was
  signed, gets a grant until the next webhook. **FLAGGED CONFLICT** against brief steps 8 and 17
  and the rule "the current row's status is necessary but not sufficient".
  — **Reversibility:** reversible.

- **D-05: Google's one call is both checks.** The Google proof is the purchase token. The existing
  `PlayDeveloperSubscriptions` class makes the one `purchases.subscriptionsv2.get` call, which is
  the proof check (package, product) and the live state at once. No second Play client. A gone
  token (404/410) is `proof_rejected`; a transport failure or absent credential is 503
  `verification_temporarily_unavailable`, not the webhook's 500. `package_name` comes from
  `GooglePlayConfig` (44 D-18).

- **D-06: Entitlement is decided by the local row where one exists, by the proof where none does.**
  Where a `core.subscriptions` row exists for `(provider, external_id)`, its `status` decides
  entitlement (`ENTITLED_STATUSES`: `active`, `grace_period`), and restore never updates that
  status from the proof — canonical state belongs to the webhooks. Where no row exists
  (adoption-with-creation), the row is created at the proof's own state and tier, and that state
  decides. A verified proof whose subscription is not entitled answers `restore_not_found` with
  nothing written. One rule for both providers, fail-closed toward the record.

**The write path**

- **D-07: The webhook's writer writes the grant.** A successful restore calls
  `SubscriptionsDB.write_subscription_grant` as-is: the grant's `ends_at` is the paid period's end
  (grace window during grace), every held active grant of the destination is expired first, the new
  row gets its own usage row, and an active grant for this subscription with the same term and tier
  writes nothing (`replayed`), so a repeat restore never resets a counter. A free grant the
  destination holds is superseded exactly as a webhook supersedes it, so the brief's
  `restore_destination_already_entitled` has no trigger. **FLAGGED CONFLICT** against the brief's
  `ends_at IS NULL` adoption grant, its UPDATE reactivation of the same row, and "never mints a
  fresh monthly counter for the same paid entitlement".
  — **Reversibility:** costly.

- **D-08: A conditional UPDATE settles owner changes; no subscription-row lock.** Inside the
  transaction, after the grant locks: the grant rows of the current owner (where one exists) and of
  the destination are locked together, ascending by id, then their usage rows. Then the owner
  update runs as one statement whose `WHERE` restates what the pre-transaction read saw —
  `user_id IS NOT DISTINCT FROM :owner_read AND last_cross_account_transfer_month IS NOT DISTINCT
  FROM :month_read`. Zero rows updated means another attempt won: roll back, re-read the row, and
  answer as the new state earns (the sync body if the destination now owns it, otherwise the
  refusal). `ix_access_grants_one_per_subscription` is the backstop, read as SQLSTATE 23505 only.
  No `FOR UPDATE` on `core.subscriptions` (43 D-16 stands). **FLAGGED CONFLICT** against brief
  step 9(a), which locks the subscription row ahead of the grant tier.

- **D-09: An owner, once set, is kept by ingestion.** Follows from D-10. Today
  `SubscriptionsDB.upsert_subscription` lets a notification's attribution token overwrite
  `user_id`. After a move to account B, a renewal carrying the original buyer's token would set the
  owner back to A, expire nothing of B's, and hit `ix_access_grants_one_per_subscription` on every
  retry. The rule becomes: the token attributes an **unowned** row only; a row with an owner keeps
  it. The owner is changed by restore alone. Amends 43 D-19 and 43-03's "an owner is added, never
  cleared" (it is now also never replaced by ingestion). Touches `crud/subscriptions.py` and the
  43/44 tests that pin the old rule. — **Reversibility:** reversible.

- **D-10: The subscription may move once per UTC calendar month.** `core.subscriptions.user_id`
  is the tie; `restore_bound_user_id` is not written and stays NULL. A move (owner is another
  account) writes `last_cross_account_transfer_month` as the first day of `evaluated_at`'s UTC
  month, expires the old owner's subscription grant in the same transaction (the old owner loses
  access at that moment), and inserts the destination's. A move is refused with
  `restore_transfer_rejected` when the stored month equals the current month; nothing is written.
  Adoption (owner NULL) and same-account restores do not count and do not write the month. The cap
  is per subscription, which the proof names, never per user. **FLAGGED CONFLICT** against the
  brief's lifetime binding, its `store_transaction_already_linked` result, and its DELETIONS line
  forbidding any read or write of `last_cross_account_transfer_month`.
  — **Reversibility:** one-way in principle; cheap today because there are no users.

**Rejections and the response**

- **D-11: Two new codes.** `ErrorCode` grows by `restore_not_found` (the proof verified, but no
  paid subscription stands behind it: not entitled, or the recorded purchase attribution differs
  from the carried token) and `restore_transfer_rejected` (the cap, D-10). Both are terminal 4xx
  with no `Retry-After`. Reused, never redefined: `operation_not_allowed` (D-01),
  `proof_rejected` through the existing `ProofRejected` leaf with a `stage` (chain, bundle,
  environment, gone token, package mismatch), `verification_temporarily_unavailable` (D-05),
  `internal_error` for an unmapped store product (`UnmappedStoreProduct`). The brief's
  `restore_store_state_unverified`, `restore_destination_anonymous`,
  `restore_destination_already_entitled`, `store_transaction_already_linked`,
  `restore_source_user_inactive`, `restore_subscription_grant_owner_mismatch`,
  `restore_branch_inconsistent` and `restore_temporarily_unavailable` have no trigger after D-03,
  D-04, D-07, D-08 and D-10 and are not added. One class per outcome, body and status identical
  across its arms.

- **D-12: The response is `SyncResponse`,** read after the commit by `SyncService.read_entitlement`,
  with `Cache-Control: no-store`, `identity_provider` the stored provider (42 D-12). The repeat,
  the adoption, the move and the race loser who finds the destination owning the row all return
  the same shape.

**Documentation deliverables**

- **D-13: Amend RESTORE-01 and RESTORE-02 in `.planning/REQUIREMENTS.md`** with dated entries:
  D-02, D-03, D-04, D-07, D-08 and D-10 as flagged conflicts against `10-restore-subscription.md`
  by line; D-09 as a dated amendment under APPLEHOOK-01 and in `STATE.md` § Decisions; the Phase 40
  forward flag on the `restore_subscription` operation label answered (**no label is needed**);
  the obligations already dead before this phase. Update the header's conflict counts. Mark ROADMAP
  criteria 2, 3 and 4 answered, criterion 3 as D-01/D-02 answers it.
- **D-14: `10-restore-subscription.md` and `SHARED-INVARIANTS.md` are NOT edited** (43 D-27).
  Divergences live in REQUIREMENTS.md.
- **D-15: Every comment this phase writes is ASD-STE100, inline where possible** (43 D-25),
  under `AGENTS.md` § "Comments and docstrings".

**Carried forward — decided earlier, binding here, do NOT rebuild**

A planner reading `10-restore-subscription.md` alone will try to build all of these. **None exists.**

- No route registry, no `Category`, no `RouteMetadata`, no named-verifier table (37.1 D-06/D-10).
  The route joins `routers/auth.py` under `get_linked_identity`; `tests/unit/test_app_wiring.py`
  gains `/auth/restore-subscription` in its narrowed-route lists.
- No foundation store-verification or vendor-proof interface (37.2 D-09).
- No rate limiting, no provider budgets, no coalescing, no proof fingerprints (35 D-05). Record the
  exposure as 41 D-20 and 42 D-16 did, closing with the v2.1 gateway contract.
- No `audit.auth_events` row, no operation enum value, no audit result value (37.1 D-01, 38 D-03,
  40 D-11). Log event names come from exception class names.
- Outcomes are exception classes, never an enum (37.3 D-12).
- `IntegrityError` is caught by SQLSTATE 23505 only (42-07).
- Lock order: grant rows ascending by id, then usage rows; no other tier ahead (43 D-16). D-08.
- No network call while a lock is held or a transaction is open. Both proof checks run in the
  service before the transaction opens, as 41 and 42 call Apple before theirs.
- One captured instant per request (`get_evaluated_at`).
- `commit()` and `rollback()` live in `services/` (AGENTS.md).
- No success log line (38 D-02).
- No challenge, no prepare mode, no attestation, no Firebase read on this route.
- Product→tier maps live in each provider's class (44 D-16); `external_id` is Apple's
  `originalTransactionId` and Google's purchase token (43 D-08, 44 D-10).
- `store_purchase_tokens.identity_value` is the server-minted attribution token per user per store.
- The purchase row is inserted once and never updated (43 D-17/D-19): restore inserts it when
  missing, with a `uuid7()` `identity_value` when the transaction carries no token.

### Claude's Discretion

- **The service.** `services/restore.py` as its own class rather than a fourth completion on
  `AuthService`. Its dependency in `app/dependencies.py` follows `get_subscriptions_service`.
- **Apple's status from a bare transaction.** `revocationDate` set → `revoked`; `expiresDate` after
  `evaluated_at` → `active`; else `expired`. Grace and billing retry are not visible without the
  renewal-info JWS; do not ask the app for it this phase. Record the choice.
- **How the Play class is called without the webhook's fields** (`event_type`, `notification_uuid`,
  `signed_at`), and how its `InternalError` on transport failure becomes the 503 of D-05: a second
  entry point on the class, or a caught-and-mapped call. No second client.
- **The crud method that locks two users' grant rows in one ascending statement** (D-08), and where
  `AttributionConflict` maps (D-11 says `restore_not_found`).
- **The HTTP statuses of the two new codes** (404 and 409 fit; both are terminal 4xx).
- **The leaf names**: the unknown-provider 403, the not-found and transfer-rejected leaves, and
  whether they share a base as `ClaimRefused`'s do.
- **The request model's name** (`RestoreRequest`), and the Apple verifier's accessor: the
  `AppStoreNotifications` class grows a `verify_transaction` method, or the verifier is exposed
  beside it; the chain, bundle and environment checks must be the library's, not re-implemented.
- **Test shape, on the 43 D-24 / 44 model**: unit tests mint a real signed transaction against the
  throwaway chain `tests/unit/test_app_store_notifications.py` already builds; the Play read is
  scripted with `httpx.MockTransport`; e2e cases script fakes behind the two Protocols in
  `tests/e2e/conftest.py`; `tests/schema` measures on real PostgreSQL: two adopters racing for one
  unowned subscription, a move and a second move in the same month, and a restore interrupted at
  commit.
- **Plan wave order.** D-09 edits Phase 43's crud and tests; it lands before or with the restore
  writer, never after.

### Deferred Ideas (OUT OF SCOPE)

- Apple live status from the App Store Server API (`Get All Subscription Statuses`) — declined (D-04).
- The renewal-info JWS as a second Apple proof field.
- Dropping `restore_bound_user_id`.
- Gateway rate limits on the auth surface, including the Play call per restore attempt — v2.1.
- `/auth` paths in the gateway HTTPRoutes.
- The Android and web claim branches.
- Phase 44.1, the feature-sliced restructure.
- One test asserting each Python enum's values equal its `core.*` type's labels.
- `secret-manager-integration` and `message-ordering-is-unspecified` todos — reviewed, not folded.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESTORE-01 | The endpoint verifies a native store artifact (`restore_proof`) directly against Apple or Google and attaches verified paid-subscription entitlement through one of two server-determined branches | § Standard Stack (both verifiers already ship), § Architecture Patterns Pattern 1–4 (the verify→resolve→lock→write sequence), § Code Examples 1–4. **Departure to record:** D-10 makes the branch set *three* (same-account, adoption, move), not two, and D-13 files that as a flagged conflict. |
| RESTORE-02 | The endpoint is a native-only surface; other surfaces receive `operation_not_allowed` | § Architecture Patterns Pattern 0 (the provider gate), § Pitfall 6. D-01's unknown-`provider` 403 and D-02's `proof_rejected` are the whole gate; § Code Examples 1 shows the request model and the handler branch. |

Both IDs are amended by D-13 rather than satisfied verbatim — the planner must budget a
documentation task for `.planning/REQUIREMENTS.md`, and that task is a phase deliverable, not
bookkeeping.
</phase_requirements>

## Summary

This phase adds **one route, one request model, one service, two crud methods, four exception
classes and two error codes**. It adds **no package, no migration, no configuration key and no
adapter interface**. Every store call it makes is a method on a class that Phases 43 and 44 already
put on `app.state`, and every row it writes goes through a writer Phase 43 already shipped.

The engineering risk is not the store integration — that is largely done. The risk lives in three
places the existing code will actively fight a naive implementation:

1. **`UnmappedStoreProduct` and `AttributionConflict` are both subclasses of `InternalError`**
   (`errors.py:262`, `errors.py:277`). D-05 requires a Play transport failure — which the Play class
   raises as a bare `InternalError` — to become a 503 `verification_temporarily_unavailable`, while
   D-11 requires an unmapped product to stay a 500. A `try/except InternalError` around
   `PlayDeveloperSubscriptions.read` therefore swallows exactly the case D-11 says must not be
   swallowed. This is the single most likely defect in this phase.

2. **`core.access_grants` carries two `DEFERRABLE INITIALLY DEFERRED` foreign keys into
   `core.subscriptions`**, one on `(id, user_id)` and one on the generated
   `product_entitled_subscription_id`. Together they mean the database itself enforces D-06 and
   D-08's ordering — but it enforces them **at COMMIT**, as SQLSTATE 23503, not at the flush where
   every existing `except IntegrityError` guard in `crud/` is waiting. A mis-ordered restore does
   not fail where this codebase is trained to look.

3. **Two hard-coded ratchets fail the moment this phase touches `auth/`**:
   `tests/unit/test_auth_package_shape.py`'s `CURRENT = (8, 23, 53)` counts every function in
   `src/nativespeaker/api/auth/`, so adding one method to `AppStoreNotifications` breaks it; and
   `tests/unit/test_docstring_bar.py`'s baseline of `0` over-long docstrings across all four roots
   binds every docstring this phase writes to three lines.

**Primary recommendation:** structure the phase as *verify → resolve → lock → write → commit → read
back*, put the store call as the **first statement of the service method** so no session statement
precedes it, give both store classes a **second, restore-specific entry point** rather than reusing
the webhook entry point (Apple's `verify()` answers 401 `auth_required` on a bad chain, which is the
wrong answer for a client-presented proof), and land D-09's one-line crud change in an earlier wave
than the restore writer.

## Architectural Responsibility Map

There is no browser or CDN tier in this project. The tiers here are the layers `AGENTS.md`
§ "Package layout" names.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Accept and shape the request body | `schemas/` | — | `AGENTS.md`: "Pydantic request and response bodies, and domain value types". `RestoreRequest` joins `GrantClaimRequest`. |
| Reject an unknown `provider` (D-01) | `routers/` | `errors.py` | A body-shape rejection with no database work; the same place `issue_challenge` rejects an unissuable `operation` (`routers/auth.py:49-52`). |
| Verify the Apple proof | `auth/app_store.py` | — | `AGENTS.md`: "`auth/` — external-SDK seams only". The `SignedDataVerifier` lives there already. |
| Verify the Google proof and read live state | `auth/google_play.py` | — | Same rule; `PlayDeveloperSubscriptions` and the httpx client live there already. |
| Decide the outcome, own the transaction, `commit()` | `services/restore.py` | — | `AGENTS.md` exception 3: "`commit()` and `rollback()` are transaction boundaries and therefore business logic; they live in `services/`". |
| Lock two users' grant rows ascending by id | `crud/grants.py` | — | The lock statements already live there (`_active_grants_statement`, `lock_active_grants`). |
| Conditionally update `core.subscriptions.user_id` and the transfer month | `crud/subscriptions.py` | — | Database access; the statement is a `WHERE`-guarded UPDATE and carries no business rule beyond restating the read. |
| Write the grant, expire the superseded ones, mint the usage row | `crud/subscriptions.py` | — | `write_subscription_grant` already does all three (D-07). Do not fork it. |
| Read the entitlement back for the response | `services/sync.py` | — | `SyncService.read_entitlement`, exactly as both claim routes do (`routers/auth.py:116`, `:140`). |
| Wire the service and the store classes into the request | `app/dependencies.py` | — | `AGENTS.md`: routes are `Depends()`-only. |

**Tier check the plan-checker should run:** no store call may appear in `services/restore.py` other
than as a call *into* an `auth/` class, and no `session.exec` may appear before that call.

## Standard Stack

### Core

Every row below is already in `pyproject.toml`. Versions are the ones installed in this repo's
`.venv`, read at research time.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `app-store-server-library` | 3.0.0 `[VERIFIED: uv run importlib.metadata]` | `SignedDataVerifier.verify_and_decode_signed_transaction` is the entire Apple proof check (D-04) | Apple's own library. Phase 43 already vendored the root CA and proved the chain walk runs for real. |
| `httpx` | 0.28.1 `[VERIFIED: uv run importlib.metadata]` | The one `AsyncClient` `PlayDeveloperSubscriptions` holds | Already built in `lifespan` at `PLAY_HTTP_TIMEOUT_SECONDS`; restore reuses it, adding no second client (D-05). |
| `google-auth` | 2.49.1 `[VERIFIED: uv run importlib.metadata]` | ADC credential signing the Play read | Phase 44 D-14; `_play_credential()` in `lifespan.py:81-87`. |
| `sqlmodel` / `sqlalchemy` | 0.0.37 / 2.0.46 `[VERIFIED: uv run importlib.metadata]` | The conditional UPDATE and the two-user grant lock | `ColumnOperators.is_not_distinct_from` is present on this version `[VERIFIED: uv run hasattr check]` — D-08's `IS NOT DISTINCT FROM` needs no raw SQL. |
| `pydantic` | 2.12.5 `[VERIFIED: uv run importlib.metadata]` | `RestoreRequest` with `min_length=1` on both fields | The exact shape `GrantClaimRequest` uses (`schemas/auth.py:31-35`). |
| `fastapi` | 0.135.1 `[VERIFIED: uv run importlib.metadata]` | The route and `Depends()` | — |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-asyncio` | 9.0.2 / installed `[VERIFIED: uv run importlib.metadata]` | Every test | Always. |
| `asyncpg` | 0.31.0 `[VERIFIED: uv run importlib.metadata]` | `tests/schema/` real-PostgreSQL harness | The race and atomicity cases only. |
| `cryptography` (transitive) | installed | Minting the throwaway certificate chain in unit tests | `tests/unit/test_app_store_notifications.py:105 _build_chain` already does this — reuse it, do not rebuild it. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Local JWS verification of the Apple proof (D-04) | `AppStoreServerAPIClient.get_all_subscription_statuses` from the same installed library | Closes the refund blind spot; costs one new Apple key, one config block and one network call. **Declined by D-04 and re-declined in Deferred Ideas.** Do not plan it. |
| Reusing `PlayDeveloperSubscriptions.read` with synthesized `event_type`/`notification_uuid` | A second entry point on the same class | The second entry point is preferred — see § Pitfall 1; either is allowed by CONTEXT's discretion, but the synthesized-fields route must still solve the `InternalError` problem. |
| A new value type for the restore result | Reusing `VerifiedNotification` | `VerifiedNotification` requires non-optional `notification_uuid: str` and `event_type: str` (`auth/store_notifications.py:14-15`) which restore has no source for and never writes. See § Open Questions Q1. |

**Installation:** none. This phase runs `uv sync` against an unchanged `pyproject.toml`.

**Version verification performed:**
```bash
uv run python -c "import importlib.metadata as md; print(md.version('app-store-server-library'))"
# -> 3.0.0
```

## Package Legitimacy Audit

**This phase installs no external package.** The audit below covers the four already-pinned
packages whose APIs this phase newly exercises, run through the legitimacy seam for completeness.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `app-store-server-library` | PyPI | latest release 2026-06-01 | unknown (PyPI publishes none) | none declared in metadata | `SUS` | **Kept, no checkpoint needed.** Already installed and in production use since Phase 43. Verdict is driven only by `unknown-downloads` and `no-repository`, both of which are PyPI-metadata gaps, not risk signals. Publisher is `apple` on Context7 and the package is the one Apple documents. |
| `google-auth` | PyPI | latest release 2026-09-04 | unknown | `github.com/googleapis/google-cloud-python` | `SUS` | **Kept, no checkpoint needed.** Verdict driven by `too-new` (a release three days old) and `unknown-downloads`. This repo pins `>=2.49` and has 2.49.1 installed; the phase adds no new call. |
| `httpx` | PyPI | recent release | unknown | declared | `SUS` | **Kept.** Same metadata-gap reasons. In use since Phase 41. |
| `sqlmodel` | PyPI | — | unknown | declared | `SUS` (assumed, same class of signals) | **Kept.** In use since Phase 34. |

**Packages removed due to `SLOP` verdict:** none.
**Packages flagged as suspicious:** all four, for the same two metadata-gap reasons. **The planner
should NOT insert `checkpoint:human-verify` tasks for these.** The seam's `SUS` verdict on PyPI is
dominated by `unknown-downloads`, which PyPI does not expose at all, so it fires on every PyPI
package including the standard ones. None of these is being newly introduced; each has been in
`pyproject.toml` and under test for at least two completed phases.

## Architecture Patterns

### System Architecture Diagram

```
POST /auth/restore-subscription
  body { provider, restore_proof }
  header Authorization: Bearer <Firebase ID token>
        │
        ▼
┌───────────────────────────────────────────┐
│ get_identity  →  get_linked_identity      │  the barrier; unlinked → 403 preauth_identity_not_allowed
└───────────────────────────────────────────┘
        │  Identity (user + identity row)
        ▼
┌───────────────────────────────────────────┐
│ routers/auth.py  restore_subscription()   │
│   provider not in PurchaseProvider?  ─────┼──► 403 operation_not_allowed   (D-01, RESTORE-02)
└───────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────────────────┐
│ services/restore.py  RestoreService.restore()                      │
│                                                                    │
│  ── NO SESSION STATEMENT MAY PRECEDE THIS BOX ──                   │
│  ┌──────────────────┐                    ┌──────────────────────┐  │
│  │ apple branch     │                    │ google_play branch   │  │
│  │ app.state        │                    │ app.state            │  │
│  │  .app_store_     │                    │  .play_subscriptions │  │
│  │  notifications   │                    │                      │  │
│  │ verify signed    │                    │ subscriptionsv2.get  │  │
│  │ transaction      │                    │  (network)           │  │
│  │  (local only)    │                    │                      │  │
│  └────────┬─────────┘                    └──────────┬───────────┘  │
│           │ chain/bundle/env fail                   │ 404/410      │
│           └──────────► ProofRejected(stage=…) ◄─────┘              │
│                        403 proof_rejected  (D-02, D-05)            │
│           │ unmapped product                        │ transport    │
│           └──► UnmappedStoreProduct 500 ◄───────────┘ 503 Unavail. │
│                                                                    │
│  proof → (provider, external_id, tier_id, status, term, token)     │
└───────────────────────────────┬────────────────────────────────────┘
                                │  first session statement starts here
                                ▼
        ┌───────────────────────────────────────────────┐
        │ NON-LOCKING READS                             │
        │  read_subscription(provider, external_id)     │
        │  read_purchase(provider, external_id)         │
        │  resolve_user(provider, carried_token)        │
        └───────────────────┬───────────────────────────┘
                            │
                 ┌──────────┴───────────┐
                 │  branch decision      │
                 ▼                       ▼
   owner == destination           owner is NULL / no row        owner is another account
   (same-account)                 (adoption / adoption-         (move, D-10)
                                   with-creation)                     │
                 │                       │                            │
                 │                       │            stored month == this month?
                 │                       │                   yes ──► 409 restore_transfer_rejected
                 │                       │                            │ no
                 └───────────┬───────────┴────────────────────────────┘
                             ▼
        entitled?  (D-06: local row status where a row exists,
                    proof status where none does)
                             │ no ──► 404 restore_not_found (nothing written)
                             ▼ yes
        ┌──────────────────────────────────────────────────────────────┐
        │ LOCKED TRANSACTION — database only, no network               │
        │  1. lock grant rows of {old owner?, destination} ASC by id   │
        │  2. lock their core.user_monthly_usage rows                  │
        │  3. conditional UPDATE core.subscriptions                    │
        │       SET user_id = destination [, last_cross_account_       │
        │           transfer_month = first-of-month on a move]         │
        │     WHERE user_id IS NOT DISTINCT FROM :owner_read           │
        │       AND last_cross_account_transfer_month                  │
        │           IS NOT DISTINCT FROM :month_read                   │
        │     0 rows ──► rollback, re-read, answer as the winner earns │
        │  4. insert core.store_purchases if missing (once, never      │
        │       updated; uuid7() identity_value when no carried token) │
        │  5. write_subscription_grant(...)  ← expires old owner's and │
        │       destination's held grants, inserts the new grant and   │
        │       its usage row                                          │
        │  6. commit()   ← deferred FKs are checked HERE, as 23503     │
        └───────────────────────────┬──────────────────────────────────┘
                                    ▼
        SyncService.read_entitlement(destination)  →  SyncResponse
        + Cache-Control: no-store                     (D-12)
```

### Recommended Project Structure

No new directory. Files touched:

```
src/nativespeaker/api/
├── auth/
│   ├── app_store.py        # + verify_transaction()  → the Apple restore proof (D-04)
│   └── google_play.py      # + a restore entry point → the Play restore proof (D-05)
├── crud/
│   ├── grants.py           # + lock two users' grant rows ascending by id (D-08)
│   └── subscriptions.py    # + the conditional owner UPDATE (D-08); MODIFY upsert_subscription (D-09)
├── schemas/
│   └── auth.py             # + RestoreRequest
├── services/
│   ├── __init__.py         # + RestoreService in __all__ and the import block
│   └── restore.py          # NEW — the whole outcome decision and the one commit()
├── routers/
│   └── auth.py             # + the seventh auth route
├── app/
│   └── dependencies.py     # + get_restore_service()
└── errors.py               # + 2 ErrorCode literals, + 4 classes (see § Pattern 5)
```

### Pattern 0: The surface gate is two rejections and nothing else (D-01, D-02 → RESTORE-02)

**What:** `provider` is a plain `str` on the model. The handler tests membership in
`PurchaseProvider` and raises a 403 leaf. Everything else that is "not a native surface" arrives as
a proof that does not verify.

**Precedent in this repo, verbatim** `[VERIFIED: src/nativespeaker/api/routers/auth.py:49-52]`:
```python
    if body.operation not in AuthOperation:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest
```
Restore raises a 403 `operation_not_allowed` leaf here instead of `InvalidRequest`, per D-01.

`PurchaseProvider` carries exactly two members
`[VERIFIED: src/nativespeaker/api/tables/purchases.py:10-13]`:
```python
class PurchaseProvider(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_provider` -- exactly two values."""
    apple = "apple"
    google_play = "google_play"
```

**When to use:** always; this is the whole of RESTORE-02.

### Pattern 1: The store call is the service's first statement

**What:** SHARED-INVARIANTS § "Locks and transactions" forbids any network call while a transaction
is open. SQLAlchemy's `AsyncSession` opens a database transaction on its **first statement**, not on
construction — so "no transaction open" means "no `session.exec` has run yet", not "no session
exists". `get_db` yields an unused session; that is fine.

Phase 42's completion path solves the same problem the other way — it commits deliberately before
reaching the provider `[VERIFIED: src/nativespeaker/api/services/auth.py:141-142]`:
```python
        # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
        await self.session.commit()
```
Restore has no challenge to claim, so it needs no such commit — it simply performs the store call
first. **The plan should state this as an ordering constraint the tests measure**, not as prose.

**Verification a test can run:** wrap the session in a recorder (the shape
`tests/schema/test_subscription_race.py:77 _RacedSession` already uses) and assert the store fake
was called before the first `exec`.

### Pattern 2: Reuse `write_subscription_grant` unchanged (D-07)

**What:** The writer already does everything the restore grant needs. Its contract, read from source:

- It supersedes **every** grant the destination holds when the new state is entitled, and only the
  same-subscription ones when it is not `[VERIFIED: src/nativespeaker/api/crud/subscriptions.py:207-208]`:
  ```python
        # Every held grant goes, the free one included: `ix_access_grants_one_active_per_user` allows one.
        superseded = list(marked_active) if entitled else held
  ```
  This is why D-07 says a free grant is superseded and `restore_destination_already_entitled` has no
  trigger.
- A repeat restore of the same term and tier writes nothing
  `[VERIFIED: src/nativespeaker/api/crud/subscriptions.py:203-205]`:
  ```python
        if entitled and [grant for grant in held
                         if grant.ends_at == ends_at and grant.tier_id == tier_id]:
            return WriteOutcome.replayed
  ```
  This is what makes the repeat restore idempotent without a counter reset.
- The expiries flush **alone and first**, because the one-active index is per-statement
  `[VERIFIED: src/nativespeaker/api/crud/subscriptions.py:217-219]`:
  ```python
        if superseded:
            # Flushed alone and first: the ORM emits inserts before updates, and the index is per-statement.
            try:
                await self.session.flush()
  ```

**Do not fork it.** The one thing the caller must supply correctly is `marked_active` — the list of
locked grant rows. On a move that list must contain **both** users' active grants, which is what
D-08's new crud method produces.

### Pattern 3: `write_subscription_grant`'s `ends_at` contract, restated by restore

`SubscriptionsService.ingest` computes the term this way
`[VERIFIED: src/nativespeaker/api/services/subscriptions.py:126-131]`:
```python
                # The captured instant stands in where the store gave no purchase date for this term.
                starts_at=(self.evaluated_at if notification.purchased_at is None
                           else notification.purchased_at),
                # During grace the term is Apple's grace window, because the paid term has lapsed.
                ends_at=(notification.grace_period_expires_at
                         if status is SubscriptionStatus.grace_period else notification.expires_at),
```
Restore must produce the identical expression, or the `WriteOutcome.replayed` comparison above
(`grant.ends_at == ends_at`) will never match and a repeat restore will mint a fresh usage row —
exactly the behaviour D-07 says must not happen. **This is a copy-the-expression requirement, and a
test should pin the two expressions to the same value for the same inputs.**

Note the Google grace subtlety Phase 44 fixed: `grace_period_expires_at` is set to the line item's
`expiryTime` only when the state is grace `[VERIFIED: src/nativespeaker/api/auth/google_play.py:234]`:
```python
            grace_period_expires_at=expiry if in_grace else None,
```

### Pattern 4: The conditional UPDATE, and what "0 rows" means (D-08)

**What:** One statement, no `FOR UPDATE` on `core.subscriptions`. `IS NOT DISTINCT FROM` because
both compared columns are nullable: `user_id` is NULL on an adoption and
`last_cross_account_transfer_month` is NULL until the first move.

Both columns are nullable in the migration
`[VERIFIED: migrations/20260818_01_initial-release.sql:130-137]`:
```sql
    -- Nullable: an unclaimed store subscription is ingested unowned, and restore is what first links it.
    user_id UUID REFERENCES core.users (id),
    provider core.subscription_provider NOT NULL,
    external_id TEXT NOT NULL,
    tier_id TEXT NOT NULL REFERENCES core.access_tiers (id),
    status core.subscription_status NOT NULL,
    -- Written by nothing: cross-account restore transfer is never performed, so this stays NULL.
    last_cross_account_transfer_month DATE,
```
The comment on line 136 becomes false when D-10 lands; the migration is **not** edited (one
migration, replaced never amended — STATE.md § v2.0), so the stale comment is a documentation item
for D-13, not a code change.

`ColumnOperators.is_not_distinct_from` exists on SQLAlchemy 2.0.46
`[VERIFIED: uv run python -c "from sqlalchemy import Column, Integer; print(hasattr(Column('x', Integer), 'is_not_distinct_from'))" → True]`, so this needs no `text()`.

**When to use:** on every branch that changes the owner — the adoption and the move. A same-account
restore changes no owner and should skip the statement entirely rather than run a no-op UPDATE that
would be indistinguishable from a lost race.

### Pattern 5: Two codes, four classes, and the totality check that will catch you

`ErrorCode` is a closed `Literal` `[VERIFIED: src/nativespeaker/api/errors.py:14-31]`:
```python
ErrorCode = Literal["auth_required",
                    "preauth_identity_not_allowed",
                    "account_unavailable",
                    "challenge_required",
                    "invalid_request",
                    "verification_temporarily_unavailable",
                    "rate_limited",
                    "validation_error",
                    "not_found",
                    "method_not_allowed",
                    "internal_error",
                    "service_unavailable",
                    "quota_exceeded",
                    "out_of_scope",
                    "identity_already_linked",
                    "operation_not_allowed",
                    "proof_rejected",
                    "device_grant_exhausted"]
```

`tests/unit/error_tree.py` enforces four properties simultaneously. Reading its source, adding a code
to the `Literal` **without** a class carrying it fails immediately:
`"ErrorCode declares codes the tree never carries"`. So the two D-11 codes and their classes must
land in the same commit.

The tree also forbids one code at two statuses and two `answers_framework_status` classes at one
status — `NotFound` already answers 404 and `ChallengeRequired` already answers 409, both with
`answers_framework_status = True`. **The new leaves must NOT set `answers_framework_status`**; they
carry new codes at those statuses, which the tree permits.

Suggested shape, following `ClaimRefused`'s one-base-declares-the-status model
(`errors.py:475-505`):

```python
class RestoreRefused(AppError):
    """The restore refusals share this shape, and its leaves add only their own name."""

    # The 404 is declared here and nowhere below, so the refusal cannot become an enumeration oracle.
    status = 404
    code = "restore_not_found"


class RestoreSubscriptionNotEntitled(RestoreRefused):
    """The proof verified, but the subscription behind it is not in the entitled set."""


class RestoreAttributionMismatch(RestoreRefused):
    """The recorded purchase attribution differs from the token this proof carries."""
```
plus a `RestoreTransferRejected(AppError)` at 409 `restore_transfer_rejected`, and a
`RestoreProviderUnknown` leaf for D-01's 403 — which may instead reuse the existing `ClaimRefused`
base if the planner judges the semantics close enough (CONTEXT leaves this to discretion; note that
`ClaimRefused`'s leaves all describe grant claims, so a fifth sibling reads oddly).

### Anti-Patterns to Avoid

- **Reusing `AppStoreNotifications.verify()` for the restore proof.** It expects a *notification*
  envelope, and on a verification failure it raises `NotificationRejected`, which answers **401
  `auth_required`** `[VERIFIED: src/nativespeaker/api/errors.py:459-463]`:
  ```python
  class NotificationRejected(ProviderLookupError):
      """The store notification did not verify: the signature, the chain, the app or the environment."""
      # One class for every arm, so the answer tells a caller nothing about which check refused it.
      status = 401
      code = "auth_required"
  ```
  A 401 on an authenticated route whose Firebase token was perfectly valid is wrong and would
  confuse the client into re-authenticating. D-11 requires `ProofRejected` (403 `proof_rejected`).
- **Catching `IntegrityError` broadly.** Every existing guard checks the SQLSTATE first
  (`crud/subscriptions.py:124-128`). Follow the same shape; a 23503 from a deferred FK is **not** a
  lost race and must not be answered as one.
- **Locking `core.subscriptions`.** 43 D-16 and D-08 both forbid it. The conditional UPDATE is the
  substitute.
- **Writing `restore_bound_user_id`.** D-10 replaces it; it stays NULL.
- **Updating `core.subscriptions.status` from the proof on the adoption path where a row exists.**
  D-06: canonical state belongs to the webhooks. Only the **creation** case sets a status.
- **Adding a `core.auth_challenges` row or an operation label.** D-13 answers the Phase 40 forward
  flag with *no label is needed*.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Verifying an Apple JWS signed transaction | A JWT decode + x5c chain walk | `SignedDataVerifier.verify_and_decode_signed_transaction` | The chain walk, the two Apple OIDs, the ES256 rule, the bundle-id and environment checks are all in the library, and `tests/unit/test_app_store_notifications.py` already proves they run for real against a throwaway root. CONTEXT: "the chain, bundle and environment checks must be the library's, not re-implemented." |
| Deriving a Google subscription's status | A state-string comparison in the service | `auth/google_play.py::_status_for` | It already handles the canceled-but-unexpired case and falls through to `expired` for every unknown state — Phase 44 measured all nine values. |
| Mapping a store product to a tier | A dict in the service | `AppStoreNotifications._tier_for` / the `products` map inside `PlayDeveloperSubscriptions.read` | 44 D-16: product→tier maps live in each provider's class, and both already raise `UnmappedStoreProduct` before any write. |
| Expiring old grants and inserting the new one under the one-active index | A bespoke expire-then-insert | `SubscriptionsDB.write_subscription_grant` | D-07. It already flushes the expiries alone and first, mints the usage row, and returns `replayed` for a no-op. |
| Locking one user's grant rows in the fixed order | New `FOR UPDATE` statements | `GrantsDB.lock_active_grants` + `lock_usage`, composed as `SubscriptionsDB.lock_grants` does | The lock order is a global invariant; `crud/subscriptions.py:57` calls a second pair of statements "a second thing to keep correct". Extend to two users by reusing the same statements, not by writing new ones. |
| Reading the entitlement back for the response | A grant query in the restore service | `SyncService.read_entitlement` | D-12; it already fails closed on a missing usage row and an unknown tier. |
| An "is this month" comparison | A string `strftime` compare | `date` arithmetic on `last_cross_account_transfer_month` | The column is a real `DATE` (`migrations:137`) and the model types it `date \| None` (`tables/purchases.py:60`). Compare dates, not `YYYY-MM` strings — `core.user_monthly_usage.monthly_period` is the string one and is a different thing. |

**Key insight:** this phase's failure mode is not *missing* code but *duplicated* code. Every one of
the seven rows above already exists and is already under test; a plan that reimplements any of them
will also have to re-prove it, and will drift from the webhook path the moment a store changes.

## Common Pitfalls

### Pitfall 1: `except InternalError` around the Play read swallows `UnmappedStoreProduct`

**What goes wrong:** D-05 requires a Play transport failure to answer 503
`verification_temporarily_unavailable`. `PlayDeveloperSubscriptions` signals a transport failure as a
bare `InternalError` `[VERIFIED: src/nativespeaker/api/auth/google_play.py:247-248]`:
```python
        except httpx.HTTPError as failure:
            raise InternalError from failure
```
and a non-2xx, non-gone status the same way (`google_play.py:152`). But it also raises
`UnmappedStoreProduct` from inside the same call
`[VERIFIED: src/nativespeaker/api/auth/google_play.py:209-211]`:
```python
        if product_id is None or product_id not in self._products:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(PurchaseProvider.google_play, str(product_id))
```
and `UnmappedStoreProduct` **is a subclass of `InternalError`**
`[VERIFIED: src/nativespeaker/api/errors.py:262-265]`:
```python
class UnmappedStoreProduct(InternalError):
    """A verified store product id with no entry in the configured product map."""
    # An operator edits the map and the store's next retry succeeds; nothing is written meanwhile.
    log_level = logging.ERROR
```

So `try: await play.read(...) except InternalError: raise Unavailable(...)` turns an operator
configuration error into a 503 that tells the operator nothing and that D-11 explicitly assigns to
`internal_error`. `AttributionConflict` is a subclass of `InternalError` too (`errors.py:277`),
though it cannot arise from inside `read`.

**Why it happens:** the class hierarchy encodes "answers 500", not "is a transport failure". Nothing
in the name warns you.

**How to avoid:** prefer a **second entry point** on `PlayDeveloperSubscriptions` that raises
`Unavailable(stage=...)` directly for the transport and non-2xx cases, leaving `UnmappedStoreProduct`
to propagate. If the caught-and-mapped route is chosen instead, the `except UnmappedStoreProduct:
raise` clause must come **first**.

**Warning signs:** a test that configures an unmapped Play product on the restore route and gets a
503 instead of a 500.

### Pitfall 2: The deferred foreign keys fail at COMMIT, not at flush

**What goes wrong:** `core.access_grants` carries two deferred FKs into `core.subscriptions`
`[VERIFIED: migrations/20260818_01_initial-release.sql:236-243]`:
```sql
    -- Deferred so ingestion and restore can write both rows in one transaction, in either order.
    FOREIGN KEY (active_subscription_grant_subscription_id, active_subscription_grant_user_id)
        REFERENCES core.subscriptions (id, user_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (active_subscription_grant_subscription_id)
        REFERENCES core.subscriptions (product_entitled_subscription_id)
        DEFERRABLE INITIALLY DEFERRED
```
The two generated columns they key on are non-NULL only for an **active subscription grant**
`[VERIFIED: migrations/20260818_01_initial-release.sql:221-226]`:
```sql
    active_subscription_grant_subscription_id UUID GENERATED ALWAYS AS (
        CASE WHEN source = 'subscription' AND status = 'active' THEN subscription_id END
    ) STORED,
    active_subscription_grant_user_id UUID GENERATED ALWAYS AS (
        CASE WHEN source = 'subscription' AND status = 'active' THEN user_id END
    ) STORED,
```
and the second FK's target is itself generated only for an entitled subscription
`[VERIFIED: migrations/20260818_01_initial-release.sql:140-143]`:
```sql
    -- The entitled set is fixed here; changing it is a future migration, never a runtime toggle.
    product_entitled_subscription_id UUID GENERATED ALWAYS AS (
        CASE WHEN status IN ('active', 'grace_period') THEN id END
    ) STORED,
```

**Two consequences the planner must design for:**

1. **The database enforces D-06.** An active `subscription`-source grant cannot exist at commit
   unless the subscription row's `status` is `active` or `grace_period`. Restore's own entitlement
   check is therefore a *nice* rejection ahead of a *hard* one — but if the two disagree the hard
   one fires at `commit()`.
2. **The database enforces D-08's ordering.** `(subscription_id, grant.user_id)` must match
   `(subscriptions.id, subscriptions.user_id)` at commit. On a move, the old owner's grant must be
   expired **in the same transaction** as the owner UPDATE, or the pair no longer matches.

Both surface as **SQLSTATE 23503** at `await self.session.commit()` — not at any `flush()`. Every
existing guard in `crud/` is `except IntegrityError` around a flush, testing for `23505`
(`crud/subscriptions.py:124-128`, `crud/grants.py:176-181`). None of them is positioned to see this.

**How to avoid:** order the writes as the diagram shows (owner UPDATE → grant expiries → grant
insert) and let the deferred FKs be a backstop, not a control flow. Add a `tests/schema` case that
deliberately mis-orders and asserts the error arrives at commit with SQLSTATE 23503, so a future
reader knows where to look.

**Warning signs:** an e2e restore test passing while the schema test fails, or a `commit()` raising
`IntegrityError` with no `except` in sight.

### Pitfall 3: The `auth/` package-shape ratchet fails on the first added method

**What goes wrong:** `tests/unit/test_auth_package_shape.py` counts modules, classes and functions in
`src/nativespeaker/api/auth/` and compares against a literal
`[VERIFIED: tests/unit/test_auth_package_shape.py:12-13]`:
```python
# What it measures now: modules, classes, functions.
CURRENT = (8, 23, 53)
```
It walks the AST, so a **method** counts `[VERIFIED: tests/unit/test_auth_package_shape.py:23-25]`:
```python
        # Walked rather than read off the module's top level, so a method or a nested helper counts.
        classes += sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
        functions += sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                         for node in ast.walk(tree))
```

Adding `verify_transaction` to `AppStoreNotifications` and a restore entry point to
`PlayDeveloperSubscriptions` takes the count from 53 to 55, and this test fails. Its own docstring
says so: *"A later phase that grows the package has to come here and write the new number down."*

**How to avoid:** budget a task step for updating `CURRENT`, and measure the new tuple rather than
guessing it.

### Pitfall 4: The docstring bar is zero on every root

**What goes wrong:** `tests/unit/test_docstring_bar.py` records a baseline of `0` over-long
docstrings across `src`, `tests`, `tests/e2e`, `tests/schema` and `tests/unit`
`[VERIFIED: tests/unit/test_docstring_bar.py:41-47]`:
```python
BASELINE: dict[str, int] = {
    "src": 0,
    "tests": 0,
    "tests/e2e": 0,
    "tests/schema": 0,
    "tests/unit": 0,
}
```
"Over-long" is a stripped body of more than three lines, measured on modules, classes, functions and
methods alike. Every new file, class, method and test class this phase writes is inside that walk.
This binds D-15 mechanically as well as stylistically.

### Pitfall 5: `ENTITLED_STATUSES` is two members, and `revoked` is Apple-only

**What goes wrong:** deriving entitlement from anything other than the named set.

`[VERIFIED: src/nativespeaker/api/crud/subscriptions.py:24-25]`:
```python
# The set `core.subscriptions.product_entitled_subscription_id` is generated over, named once for its readers.
ENTITLED_STATUSES = frozenset({SubscriptionStatus.active, SubscriptionStatus.grace_period})
```
and the five statuses `[VERIFIED: src/nativespeaker/api/tables/purchases.py:16-22]`:
```python
class SubscriptionStatus(StrEnum):
    """Mirrors the PostgreSQL type `core.subscription_status` -- exactly five values."""
    active = "active"
    grace_period = "grace_period"
    billing_retry = "billing_retry"
    expired = "expired"
    revoked = "revoked"
```

Two consequences for the Apple derivation CONTEXT leaves to discretion:
- `grace_period` and `billing_retry` are **unreachable** from a bare signed transaction, because
  neither is visible without the renewal-info JWS. The Apple adoption-with-creation path can
  therefore only ever create a row at `active`, `expired` or `revoked`. Say so in the plan; a
  reviewer will otherwise read the three-arm derivation as incomplete.
- `revoked` reaches the writer's revocation arm, which marks superseded grants `revoked` rather than
  `expired` (`crud/subscriptions.py:210-211`) — but a `revoked` proof is not entitled, so restore
  answers `restore_not_found` before reaching the writer. Do not plumb it.

### Pitfall 6: `Unavailable`, `ProofRejected` and `NotificationRejected` all need a `stage=` keyword

**What goes wrong:** all three inherit `ProviderLookupError`, whose `__init__` is keyword-only
`[VERIFIED: src/nativespeaker/api/errors.py:380-393]`:
```python
class ProviderLookupError(AppError):
    """The provider lookup's rejections share this shape; only its leaves are raised."""

    def __init__(self, *, stage: str, cause: str | None = None) -> None:
        # Plain strings, both of them ours: no provider text is ever admissible in either field.
        self.stage = stage
        self.cause = cause
        super().__init__(f"{type(self).__name__.lower()} at {stage}")
```
`raise ProofRejected()` is a `TypeError`. The `stage` values are a **closed set of our own strings**
— never a store value. Phase 43 pins that with a test that enumerates every reachable stage
(`tests/unit/test_app_store_notifications.py:432
test_every_reachable_stage_is_a_closed_set_name`); expect the planner to extend that closed set with
restore's stages and to keep the purchase token and the JWS out of every one of them.

D-11's listed stages: chain, bundle, environment, gone token, package mismatch. The first three come
free from `VerificationException.status.name`; the last two are ours to name.

### Pitfall 7: D-09's change is one comparison, but three fixtures mirror the old rule

**What goes wrong:** the rule lives in one place
`[VERIFIED: src/nativespeaker/api/crud/subscriptions.py:106-107]`:
```python
            # An owner is added, never cleared: a later notification without a token unlinks nobody.
            owner = stored.user_id if user_id is None else user_id
```
D-09 makes it `owner = stored.user_id if stored.user_id is not None else user_id`.

But the unit suite's fake writer **mirrors** the rule rather than importing it
`[VERIFIED: tests/unit/test_subscription_attribution.py:113-114]`:
```python
            # The same rule the crud holds: an owner is added, never cleared.
            stored.user_id = stored.user_id if fields["user_id"] is None else fields["user_id"]
```
so the fake must change with the real one or the unit tests will silently keep testing the old rule.

**What does NOT break:** `test_a_purchase_recorded_unattributed_accepts_a_later_real_token`
(`tests/unit/test_subscription_attribution.py:337-349`) still passes under D-09, because that
subscription's `user_id` was `None` on the first delivery — an unowned row is exactly the case D-09
still allows a token to attribute. The planner should say so, so a wave agent does not "fix" a test
that is already correct.

**Why D-09 is needed at all, in one sentence grounded in code:** the attribution guard in `ingest`
only fires when the *recorded* token differs from the *carried* one
(`services/subscriptions.py:78-82`), so a renewal carrying the **original buyer's own** token passes
the guard, `resolve_user` maps it back to account A, and today's `upsert_subscription` would silently
revert a restore move.

### Pitfall 8: two hard-coded error-vocabulary mirrors

Adding codes and classes trips two more literals besides `ErrorCode`:

- `[VERIFIED: tests/unit/test_error_contract.py:19-25]`:
  ```python
  # Written out rather than derived from the tree: the mirror that catches an undecided code shipping.
  CONTRACT_CODES = {"auth_required", "preauth_identity_not_allowed", "account_unavailable",
                    "challenge_required", "invalid_request", "verification_temporarily_unavailable",
                    "rate_limited", "validation_error", "not_found", "method_not_allowed",
                    "internal_error", "service_unavailable", "quota_exceeded", "out_of_scope",
                    "identity_already_linked", "operation_not_allowed", "proof_rejected",
                    "device_grant_exhausted"}
  ```
- `tests/unit/test_rejection_vocabulary.py`'s closed set of log-event names, which are the exception
  class names lower-cased (`errors.py:387` builds the message from `type(self).__name__.lower()`).
  Every new class adds one entry there.

## Code Examples

### Example 1 — The request model and the surface gate

```python
# schemas/auth.py — following GrantClaimRequest (schemas/auth.py:31-35) exactly
class RestoreRequest(BaseModel):
    """The restore body: the store the artifact came from, and the artifact."""
    # A plain str, as ChallengeRequest.operation is: an unserved store is the handler's 403.
    provider: str = Field(..., min_length=1)
    restore_proof: str = Field(..., min_length=1)
```

```python
# routers/auth.py — the seventh auth route
@router.post("/auth/restore-subscription",
             response_model=SyncResponse,
             summary="Attach a verified paid store subscription to the caller's account")
async def restore_subscription(body: RestoreRequest,
                               response: Response,
                               identity: Identity = Depends(get_linked_identity),
                               service: RestoreService = Depends(get_restore_service),
                               sync_service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    """Verify the store artifact and attach the entitlement it names."""
    if body.provider not in PurchaseProvider:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a proof never is.
        logger.warning("restore_provider_not_served", provider=body.provider)
        raise RestoreProviderUnknown()

    # Forwarded untouched and never logged: the store artifact is a secret.
    await service.restore(identity=identity,
                          provider=PurchaseProvider(body.provider),
                          restore_proof=body.restore_proof)
    entitlement = await sync_service.read_entitlement(identity.user.id)
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
```

The `Cache-Control` line is set on the injected `Response` rather than returned as a `JSONResponse`,
for the reason the two claim routes give `[VERIFIED: src/nativespeaker/api/routers/auth.py:141-143]`:
```python
    # Set on the injected response rather than returned as a JSONResponse, so the model still validates.
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
```

### Example 2 — The Apple restore proof

The library method is documented for exactly this input — *"a signed transaction obtained from the
App Store Server API, notification, **or device**"*
`[CITED: https://github.com/apple/app-store-server-library-python/blob/main/_autodocs/api-reference/SignedDataVerifier.md]`.
Its signature is `verify_and_decode_signed_transaction(self, signed_transaction: str) ->
JWSTransactionDecodedPayload`, raising `VerificationException` on failure.

```python
# auth/app_store.py — a new method on AppStoreNotifications
    def verify_transaction(self, signed_transaction: str,
                           evaluated_at: datetime) -> RestoredSubscription:
        """Verify one client-presented signed transaction and report what it names."""
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")
        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(signed_transaction)
        except VerificationException as failure:
            # ProofRejected, not NotificationRejected: this caller's Firebase token was valid.
            raise ProofRejected(stage=failure.status.name) from failure
        ...
```

**Measured, not assumed:** on the installed 3.0.0, `SignedDataVerifier` exposes exactly
`verify_and_decode_app_transaction`, `verify_and_decode_notification`,
`verify_and_decode_realtime_request`, `verify_and_decode_renewal_info`,
`verify_and_decode_signed_transaction`
`[VERIFIED: uv run python -c "from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier; print([m for m in dir(SignedDataVerifier) if not m.startswith('_')])"]`.

`VerificationStatus` has **eight** members on 3.0.0: `OK`, `VERIFICATION_FAILURE`,
`INVALID_APP_IDENTIFIER`, `INVALID_CERTIFICATE`, `INVALID_CHAIN_LENGTH`, `INVALID_CHAIN`,
`INVALID_ENVIRONMENT`, `RETRYABLE_VERIFICATION_FAILURE`
`[VERIFIED: uv run python -c "from appstoreserverlibrary.signed_data_verifier import VerificationStatus; print([s.name for s in VerificationStatus])"]`.
These are the `stage` values Pitfall 6 refers to, and they are what
`tests/unit/test_app_store_notifications.py:432` already enumerates.

Field types measured on the installed package rather than read from the docs
`[VERIFIED: uv run python -c "import attr; from appstoreserverlibrary.models.JWSTransactionDecodedPayload import JWSTransactionDecodedPayload as T; [print(f.name, f.type) for f in attr.fields(T)]"]`:
```
originalTransactionId -> str | None
purchaseDate          -> int | None
expiresDate           -> int | None
revocationDate        -> int | None
signedDate            -> int | None
appAccountToken       -> str | None
inAppOwnershipType    -> InAppOwnershipType | None
type                  -> Type | None
```

### Example 3 — Apple's status from a bare transaction (CONTEXT discretion)

`_instant` already converts Apple's millisecond stamps
`[VERIFIED: src/nativespeaker/api/auth/app_store.py:36-38]`:
```python
def _instant(milliseconds: int | None) -> datetime | None:
    """Convert one of Apple's UNIX-millisecond stamps, keeping an absent one absent."""
    return None if milliseconds is None else datetime.fromtimestamp(milliseconds / 1000, UTC)
```

```python
def _transaction_status(transaction, evaluated_at: datetime) -> SubscriptionStatus:
    """The status one signed transaction reports, with no renewal payload to consult."""
    if transaction.revocationDate is not None:
        return SubscriptionStatus.revoked
    expires_at = _instant(transaction.expiresDate)
    # Grace and billing retry need the renewal payload, which this proof does not carry.
    return (SubscriptionStatus.active if expires_at is not None and expires_at > evaluated_at
            else SubscriptionStatus.expired)
```

Note that `_APPLE_STATUSES` is **not** usable here — it keys on the *notification's* `data.status`,
which a bare transaction has no equivalent of `[VERIFIED: src/nativespeaker/api/auth/app_store.py:20-25]`:
```python
# Apple's five statuses, one to one onto `core.subscription_status`.
_APPLE_STATUSES = {Status.ACTIVE: SubscriptionStatus.active,
                   Status.EXPIRED: SubscriptionStatus.expired,
                   Status.BILLING_RETRY: SubscriptionStatus.billing_retry,
                   Status.BILLING_GRACE_PERIOD: SubscriptionStatus.grace_period,
                   Status.REVOKED: SubscriptionStatus.revoked}
```

### Example 4 — The Google restore proof

The endpoint, the scope and the response shape are already correct in this repo
`[VERIFIED: src/nativespeaker/api/auth/google_play.py:29-34]`:
```python
# The one scope `purchases.subscriptionsv2.get` accepts.
PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

# The purchase token is the only handle the read accepts, so it travels in the path.
PLAY_URL = ("https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            "{package_name}/purchases/subscriptionsv2/tokens/{purchase_token}")
```
Google documents the same call as
`GET https://www.googleapis.com/androidpublisher/v3/applications/{packageName}/purchases/subscriptionsv2/{token}`
with an empty request body and the `androidpublisher` scope
`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get]`.
Note the host differs (`androidpublisher.googleapis.com` here versus `www.googleapis.com` in the
reference) and the path has a `tokens/` segment here; **this is the shape Phase 44 shipped and it is
under test — do not "correct" it during this phase.** Changing it is out of scope and would be an
unmeasured change to a working webhook.

The gone-token statuses are already named `[VERIFIED: src/nativespeaker/api/auth/google_play.py:39-40]`:
```python
# The two Play statuses that say this purchase token is gone, which no later attempt can change.
_GONE_STATUSES = frozenset({404, 410})
```
D-05 maps that outcome — today a `None` return — to `proof_rejected`.

The response fields the restore path consumes are already modelled
`[VERIFIED: src/nativespeaker/api/auth/google_play.py:74-82]`:
```python
class PlaySubscription(BaseModel):
    """The `purchases.subscriptionsv2.get` response, keeping Google's own field names."""
    subscriptionState: str
    startTime: datetime | None = None
    latestOrderId: str | None = None
    # Parsed and not acted on: an upgrade's old token is the restore route's to read.
    linkedPurchaseToken: str | None = None
    lineItems: list[PlaySubscriptionLineItem] = Field(default_factory=list)
    externalAccountIdentifiers: PlayExternalAccountIdentifiers | None = None
```
Google's own sample response carries the same names — `subscriptionState`, `startTime`,
`latestOrderId`, `linkedPurchaseToken`, `externalAccountIdentifiers.obfuscatedExternalAccountId`,
`lineItems[].productId` and `lineItems[].expiryTime`
`[CITED: https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get]`.

**`linkedPurchaseToken` is parsed and not acted on**, and the comment on line 79 says *"an upgrade's
old token is the restore route's to read."* That comment names this phase. **It is not in CONTEXT's
scope and D-11 adds no code for it.** The planner should record it as a knowingly-unused field
rather than build the upgrade-relinking branch — see § Open Questions Q3.

### Example 5 — The conditional owner update

```python
# crud/subscriptions.py
    async def claim_subscription_owner(self, *,
                                       subscription_id: UUID,
                                       owner_read: UUID | None,
                                       month_read: date | None,
                                       destination: UUID,
                                       transfer_month: date | None,
                                       evaluated_at: datetime) -> bool:
        """Set the owner where the row still says what the pre-transaction read saw."""
        values = {"user_id": destination, "updated_at": evaluated_at}
        if transfer_month is not None:
            values["last_cross_account_transfer_month"] = transfer_month
        statement = (update(Subscription)
                     .where(col(Subscription.id) == subscription_id,
                            # Both columns are nullable, so equality would not match a NULL read.
                            col(Subscription.user_id).is_not_distinct_from(owner_read),
                            col(Subscription.last_cross_account_transfer_month)
                            .is_not_distinct_from(month_read))
                     .values(**values))
        return (await self.session.exec(statement)).rowcount == 1
```

`Subscription` maps every column this writes
`[VERIFIED: src/nativespeaker/api/tables/purchases.py:52-63]`:
```python
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    # Nullable: an unclaimed store subscription is ingested unowned, and restore is what first links it.
    user_id: UUID | None = Field(default=None, foreign_key="core.users.id")
    provider: PurchaseProvider = Field(sa_type=PurchaseProviderType)
    # Deliberately not `unique=True`: the table's rule is `ix_subscriptions_provider_external_id`.
    external_id: str = Field()
    tier_id: str = Field(foreign_key="core.access_tiers.id")
    status: SubscriptionStatus = Field(sa_type=SubscriptionStatusType)
    last_cross_account_transfer_month: date | None = Field(default=None)
    restore_bound_user_id: UUID | None = Field(default=None, foreign_key="core.users.id")
    created_at: datetime = Field(sa_type=DateTimeType)
    updated_at: datetime = Field(sa_type=DateTimeType)
```

**An ORM-level `update()` does not refresh objects already in the identity map.** The restore service
reads the `Subscription` row before the transaction; after this statement, that Python object still
carries the old `user_id`. Either pass `synchronize_session="fetch"`, or — simpler and matching this
codebase's style — never read the stale attribute again and re-read the row explicitly on the
zero-rows path, which D-08 requires anyway.

## Ratchets, Fixtures and Literals This Phase Must Update

Not a rename phase, so no Runtime State Inventory applies. But this repository carries several
deliberately hand-maintained mirrors, and every one of them fails loudly rather than silently.
Missing any of these is the most likely cause of a red suite at the end of the phase.

| Location | Literal | Why it changes |
|----------|---------|----------------|
| `src/nativespeaker/api/errors.py:14-31` | `ErrorCode` `Literal` | +2 codes (D-11) |
| `tests/unit/test_error_contract.py:19-25` | `CONTRACT_CODES` | mirror of the above |
| `tests/unit/test_rejection_vocabulary.py` | the closed log-event-name set | +1 per new exception class |
| `tests/unit/test_auth_package_shape.py:13` | `CURRENT = (8, 23, 53)` | +1 function per new `auth/` method (Pitfall 3) |
| `tests/unit/test_docstring_bar.py:41-47` | `BASELINE` all `0` | must stay 0 (Pitfall 4) |
| `tests/unit/test_app_wiring.py:70-72, 79-81` | the narrowed-route parametrize lists | + `/auth/restore-subscription` |
| `tests/unit/test_subscription_attribution.py:113-114` | the fake writer's owner rule | mirrors D-09 (Pitfall 7) |
| `src/nativespeaker/api/services/__init__.py:1-2` | `__all__` and the import block | + `RestoreService` |
| `src/nativespeaker/api/routers/auth.py:1-3` | the module docstring, which enumerates "the six auth routes" | now seven — and it is currently a 3-line docstring, so the rewrite must stay ≤3 lines |
| `.planning/REQUIREMENTS.md` | RESTORE-01/02, APPLEHOOK-01, the header conflict counts | D-13 |
| `.planning/STATE.md` § Decisions | D-09 as a dated amendment | D-13 |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Apple receipt validation via `verifyReceipt` (the base64 receipt blob POSTed to Apple) | StoreKit 2 `Transaction.jwsRepresentation`, verified locally against Apple Root CA G3 | StoreKit 2 / App Store Server API v1, adopted by this repo in Phase 43 | Restore needs **no network call to Apple at all** (D-04). A plan that reaches for `verifyReceipt` is years out of date and would also violate the no-new-credential constraint. `[ASSUMED]` for the deprecation framing; `[VERIFIED: this repo]` for what is actually installed and used. |
| Play `purchases.subscriptions.get` (v1 subscriptions resource) | `purchases.subscriptionsv2.get` returning `SubscriptionPurchaseV2` with `lineItems[]` | Google's v2 subscription model | Already the shape Phase 44 built. `[CITED: developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get]` |
| A `restore_bound_user_id` lifetime binding (the brief's model) | `core.subscriptions.user_id` plus a per-UTC-month move cap (D-10) | This phase | The migration's own comments on lines 136 and 138 become stale. D-13 records this; the migration is not edited. |

**Deprecated/outdated in this repo's own history:**
- The vendor-proof and store-verification Protocols (`VendorProofAdapter`, `ClaimKind`,
  `DeviceBitState`) — deleted by Phase 37.2 D-09 as zero-consumer code. Do not resurrect.
- `43 D-13`'s bare-transaction status rule, retired for the *webhook* by 44 D-11 — CONTEXT
  reinstates it for *restore* only, which is the correct scope.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No real Apple StoreKit signed transaction and no real Play purchase token has ever reached this deployment, so restore's wire behaviour against production stores is unverified. This is the standing fact STATE.md records for Phases 41 and 43, extended to this route. | § Environment Availability | Low as a *design* risk (both libraries are Apple's and Google's own, and Phase 43's chain walk runs for real against a throwaway root). Real as a *deployment* risk: the first real 400 from either store is authoritative over anything this phase writes. |
| A2 | A StoreKit 2 client can produce `Transaction.jwsRepresentation` for the current entitlement, and that is what the iOS app will put in `restore_proof`. | § Standard Stack, D-04 | If the app instead sends the App Store *receipt* or an `AppTransaction`, `verify_and_decode_signed_transaction` refuses it and every restore fails `proof_rejected`. There is no iOS app yet to check against. **Worth a confirmation checkpoint with the user before the plan locks the body contract.** |
| A3 | `verifyReceipt` being the superseded predecessor to StoreKit 2 JWS is training knowledge, not verified this session. | § State of the Art | None — it appears only as background for why no receipt path is planned. |
| A4 | The `SUS` verdicts in § Package Legitimacy Audit are driven by PyPI's absence of download statistics rather than by real risk. | § Package Legitimacy Audit | If wrong, four long-installed dependencies would warrant review — but none is newly introduced by this phase, so nothing this phase does changes the exposure. |
| A5 | A grant expired by a move leaves the old owner with no active grant, and `SyncService.read_entitlement` reports `type=none` for them on their next `/auth/sync`. Derived from `read_effective_grants` + the `Entitlement(type=none)` branch, not executed. | § Architecture Patterns | Low. If the old owner instead sees a stale entitlement, the move is not observable and D-10's "the old owner loses access at that moment" is not delivered. A test should assert it rather than assume it. |

## Open Questions (RESOLVED)

Every question below carries a Recommendation, and every Recommendation was adopted by the
plans. Each `RESOLVED:` line names the plan and task that carries it. The § Source Coverage
table in `45-01-PLAN.md` mirrors the same five mappings.

1. **What value type crosses the `auth/` seam on the restore path?**
   - What we know: both store classes today return `VerifiedNotification`, whose `notification_uuid`
     and `event_type` are non-optional `str` (`auth/store_notifications.py:14-15`). Restore writes no
     `audit.subscription_events` row, so it has no source for either and no use for them.
   - What's unclear: whether to synthesize placeholder values into `VerifiedNotification`, or add a
     small sibling dataclass beside it.
   - Recommendation: **a sibling frozen dataclass in `auth/store_notifications.py`** carrying only
     what restore consumes — `provider`, `external_id`, `product_id`, `tier_id`,
     `attribution_token`, `status`, `purchased_at`, `expires_at`, `grace_period_expires_at`. A
     synthesized `notification_uuid` is a value that means nothing and would eventually be written
     somewhere. Note this costs one class against the `test_auth_package_shape.py` ratchet.
   - **RESOLVED: adopted in 45-01 Task 1** — a frozen `RestoredSubscription` dataclass beside
     `VerifiedNotification` in `auth/store_notifications.py`, and the same task re-measures the
     `test_auth_package_shape.py` ratchet for the added class.

2. **Does the same-account repeat need the conditional UPDATE at all?**
   - What we know: D-08 describes the UPDATE as settling *owner changes*. A same-account restore
     changes no owner.
   - Recommendation: skip the statement on the same-account branch. Running it would return
     `rowcount == 1` harmlessly but would make "0 rows means a lost race" untrue for one branch.
   - **RESOLVED: adopted in 45-03 Task 2** — the same-account branch runs no owner UPDATE, asserted
     as a `<behavior>` line and gated by the `claim_subscription_owner` call-site check. 45-01
     Task 1 builds that branch without the statement, so the two plans agree.

3. **`linkedPurchaseToken` — the comment in `google_play.py:79` names this route.**
   - What we know: Google sets it when a subscription is upgraded/downgraded and a new purchase token
     replaces an old one. This repo parses it and does nothing with it.
   - What's unclear: whether a restore presenting the *new* token should also find and settle the
     *old* token's `core.subscriptions` row.
   - Recommendation: **out of scope.** CONTEXT names no such branch, D-11 adds no code for it, and
     inventing one would be an unflagged departure. Record it in Deferred Ideas and leave the comment
     stale — or, cheaper, note in the plan that the comment now over-promises.
   - **RESOLVED: adopted in 45-05 Task 1** — recorded out of scope in REQUIREMENTS.md, with the
     note that the `google_play.py` comment now over-promises. No plan adds code for it.

4. **Apple Family Sharing (`inAppOwnershipType`).**
   - What we know: the field is `PURCHASED` or `FAMILY_SHARED`
     `[CITED: app-store-server-library-python _autodocs/types.md]`, and it is present on the installed
     3.0.0 payload `[VERIFIED: attr.fields inspection above]`. This repo reads it nowhere.
   - What's unclear: whether a family member's shared transaction should be able to restore the
     subscription onto their own account — under D-10 that consumes the paying account's one monthly
     move.
   - Recommendation: **do not add a check this phase** (it is not in CONTEXT), but raise it to the
     user as a one-line product question, because a shared receipt plus D-10's cap can take the
     subscription away from the person who is paying for it. This is the sharpest edge D-10 has.
   - **RESOLVED: adopted in 45-05 Task 1** — no check is added this phase, and the question is
     raised to the developer in the requirement record. 45-05 also carries it as threat T-45-13
     with disposition `transfer`.

5. **Where does a `MissingPurchaseTokenError` land on this route?**
   - What we know: `PurchasesDB.read_tokens` raises it when a user lacks a row for either store
     (`crud/purchases.py:22-25`), but restore uses `resolve_user`, which returns `None` instead
     (`crud/purchases.py:33-34`).
   - Recommendation: use `resolve_user` only. Nothing on this route needs the completeness check.
   - **RESOLVED: adopted in 45-03 Task 2** — the service resolves attribution with `resolve_user`,
     gated by `grep -c 'read_tokens' src/nativespeaker/api/services/restore.py` returning 0.
     45-01 Task 1 writes the first call site the same way.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL 17 | `tests/schema/` real-database cases (races, atomicity, the deferred-FK case) | ✓ | 17.11 (Debian 17.11-1.pgdg13+2) `[VERIFIED: asyncpg connect with .env credentials, "show server_version"]` | — |
| `uv` | every command | ✓ | 0.12.5 `[VERIFIED: uv --version]` | — |
| Apple Root CA G3 (vendored) | building the real `SignedDataVerifier` | ✓ | `config/certs/AppleRootCA-G3.cer`, 583 bytes `[VERIFIED: ls -la "$APPLE_CERTS_DIR"]` | — |
| App Store configuration (`bundle_id`, `environment`, `app_apple_id`) | a *real* `SignedDataVerifier` at runtime | ✗ | — `[VERIFIED: no APP_STORE_* keys in .env; config/config.yaml:37-39 declares only app_store.products]` | Unit tests build their own verifier against the throwaway chain (`tests/unit/test_app_store_notifications.py:105-166`); e2e tests use `scripted_app_store_notifications` and `unconfigured_app_store_notifications` (`tests/e2e/conftest.py:296-310`). **No fallback is needed — this is how Phase 43 was built and verified.** |
| Google Play configuration (`package_name`, `push_audience`, ADC) | a *real* Play read at runtime | ✗ / partial | `GOOGLE_APPLICATION_CREDENTIALS` is set in `.env`, but no `GOOGLE_PLAY_*` keys exist `[VERIFIED: cut -d= -f1 .env]`; `config/config.yaml:41-43` declares only `google_play.products` | `real_google_play_seam` scripts the read at the httpx transport (`tests/e2e/conftest.py:343-394`); `scripted_play_subscriptions` and `unconfigured_google_play` cover the fake and unconfigured cases. **No fallback needed.** |
| `psql` CLI | nothing this phase runs | ✗ | — | `tests/schema/conftest.py` uses `asyncpg` directly (`create_database`, `apply_migration`). Not needed. |
| Docker | nothing this phase runs | ✗ (not running) | — | The developer's PostgreSQL is already reachable on `localhost`. Not needed. |
| `helm` | `helm template` verification | ✗ | — | Already recorded as an `unrun-verify` in `.planning/WINDOWS.md` by Phase 44. **This phase changes no `k8s/` file** (CONTEXT § Integration Points), so it is not owed. |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** the two store configurations. Both have established,
already-shipped test doubles. The consequence is § Assumptions Log A1: this phase cannot be verified
against a real store, and the plan must say so rather than imply integration confidence.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.2 with `pytest-asyncio` (`asyncio_mode = "auto"`) `[VERIFIED: pyproject.toml [tool.pytest.ini_options]]` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `env_files = [".env"]`, `addopts = "-v --tb=short -m 'not e2e and not schema'"`) |
| Quick run command | `uv run pytest` — 1190 unit tests, 503 deselected `[VERIFIED: uv run pytest --collect-only -q]` |
| Full suite command | `uv run pytest` && `uv run pytest -m e2e` && `uv run pytest -m schema` && `uv run ruff check src tests` |

**Measured baseline before this phase:** **1190 unit / 298 e2e / 205 schema**, out of 1693 collected
`[VERIFIED: uv run pytest --collect-only -q, three marker selections]`. This exactly matches the
figure STATE.md records for Phase 44, so nothing has drifted since that phase closed.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESTORE-01 | A real minted Apple signed transaction verifies through `verify_transaction` and yields the expected `(external_id, tier_id, status)` | unit | `uv run pytest tests/unit/test_restore_proof.py -x` | ❌ Wave 0 (but the chain fixture it needs exists at `tests/unit/test_app_store_notifications.py:105-171`) |
| RESTORE-01 | A scripted Play `subscriptionsv2.get` body yields the expected value type; a 404 and a 410 each yield `proof_rejected` | unit | `uv run pytest tests/unit/test_restore_proof.py -x` | ❌ Wave 0 (`httpx.MockTransport` pattern at `tests/e2e/conftest.py:343-394`) |
| RESTORE-01 | Adoption of an unowned subscription attaches a grant and returns the sync body | e2e | `uv run pytest tests/e2e/test_restore_subscription.py -m e2e -x` | ❌ Wave 0 (fixture shapes at `tests/e2e/conftest.py:396-441, 513, 536, 568`) |
| RESTORE-01 | Adoption-with-creation (no canonical row) creates the row at the proof's state and tier | e2e | same file | ❌ Wave 0 |
| RESTORE-01 | A move expires the old owner's grant and inserts the destination's, in one transaction | e2e + schema | `uv run pytest tests/schema/test_restore_race.py -m schema -x` | ❌ Wave 0 |
| RESTORE-01 | A repeat restore returns `WriteOutcome.replayed` — the grant keeps its id and the usage counter is untouched | e2e | e2e file | ❌ Wave 0 |
| RESTORE-01 | Both proof checks complete before the first session statement (no network call under lock) | unit | recorder session, shape at `tests/schema/test_subscription_race.py:77` | ❌ Wave 0 |
| RESTORE-02 | An unserved `provider` string answers 403 `operation_not_allowed` with a byte-identical body | e2e | e2e file | ❌ Wave 0 |
| RESTORE-02 | Every proof-rejection arm (bad chain, wrong bundle, wrong environment, gone token, package mismatch) answers a byte-identical 403 `proof_rejected` | unit + e2e | both files | ❌ Wave 0 |
| D-06 | A verified proof whose subscription is not entitled answers 404 `restore_not_found` and writes nothing | e2e | e2e file | ❌ Wave 0 |
| D-09 | A renewal carrying the original buyer's token does not revert a moved subscription's owner | unit | `uv run pytest tests/unit/test_subscription_attribution.py -x` | ✅ file exists; **new case + fixture edit at line 113-114** |
| D-10 | A second move in the same UTC month is refused with 409 and writes nothing | schema | `uv run pytest tests/schema/test_restore_race.py -m schema -x` | ❌ Wave 0 |
| D-08 | Two adopters racing one unowned subscription commit exactly one grant; the loser answers the sync body or the refusal | schema | same file | ❌ Wave 0 |
| D-08 | A restore interrupted at `commit()` changes neither the owner nor the grant | schema | same file | ❌ Wave 0 |
| Pitfall 1 | An unmapped Play product on the restore route answers 500 `internal_error`, not 503 | unit | `tests/unit/test_restore_proof.py` | ❌ Wave 0 — **this is the case the phase is most likely to get wrong; do not omit it** |
| Pitfall 2 | A mis-ordered restore surfaces SQLSTATE 23503 at commit, not 23505 at flush | schema | `tests/schema/test_restore_race.py` | ❌ Wave 0 |
| Wiring | `/auth/restore-subscription` declares `get_linked_identity` and is in neither exemption set | unit | `uv run pytest tests/unit/test_app_wiring.py -x` | ✅ file exists; **parametrize lists at lines 70-72 and 79-81 must gain the path** |
| Error tree | The tree stays total with the two new codes | unit | `uv run pytest tests/unit/test_error_registry.py tests/unit/test_error_contract.py -x` | ✅ files exist; `CONTRACT_CODES` must gain both codes |
| Ratchets | The `auth/` shape and the docstring bar still match their literals | unit | `uv run pytest tests/unit/test_auth_package_shape.py tests/unit/test_docstring_bar.py -x` | ✅ files exist; `CURRENT` must be re-measured |

### Sampling Rate

- **Per task commit:** `uv run pytest` (the 1190-test unit selection; 1.5s to collect, fast to run)
- **Per wave merge:** `uv run pytest && uv run pytest -m e2e && uv run pytest -m schema && uv run ruff check src tests`
- **Phase gate:** all three selections green, `ruff check src tests` clean, and the three baseline
  counts recorded in the summary as Phases 41–44 each did.

### Wave 0 Gaps

- [ ] `tests/unit/test_restore_proof.py` — the two proof checks, their rejection arms, and Pitfall 1
      (covers RESTORE-01, RESTORE-02)
- [ ] `tests/e2e/test_restore_subscription.py` — the four outcomes and the two refusals through the
      real route (covers RESTORE-01, RESTORE-02, D-06)
- [ ] `tests/schema/test_restore_race.py` — the two-connection race, the double move, the interrupted
      commit, and the deferred-FK case (covers D-08, D-10, Pitfall 2)
- [ ] Fixture additions to `tests/e2e/conftest.py` — a `seed_subscription` factory (one does not
      exist; `seed_grant` at line 536 and `seed_purchase_tokens` at line 568 are the models to follow)
- [ ] No framework install needed — `pytest`, `pytest-asyncio` and `asyncpg` are all present.

## Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json` `[VERIFIED: cat .planning/config.json]`, so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Unchanged. The route sits behind `get_identity` → `get_linked_identity`; this phase re-verifies nothing (SHARED-INVARIANTS § "The barrier"). |
| V3 Session Management | no | No backend session or token exists (SHARED-INVARIANTS § "Tokens and sessions"). |
| V4 Access Control | **yes — this is the phase's core security surface** | The store proof *is* the authorization for the entitlement. D-10's month cap is the only limit on how many accounts one stolen proof can reach. |
| V5 Input Validation | yes | Pydantic `min_length=1` on both fields; the `provider` membership test; neither store value is ever interpolated into SQL (the crud uses parameterized SQLModel statements throughout). |
| V6 Cryptography | yes | **Never hand-rolled.** `SignedDataVerifier` performs the chain build, the two Apple OID checks and the ES256 signature check; `google-auth` signs the Play bearer. This phase writes no cryptographic code. |
| V7 Error Handling & Logging | yes | The anti-oracle rule: one class per outcome with a byte-identical body across its arms (D-11, SHARED-INVARIANTS § Errors). |
| V8 Data Protection | yes | The proof, the purchase token and the JWS are bearer material and must never reach a log line, a `stage` value or an exception field. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A stolen store proof restored onto an attacker's account | Elevation of Privilege | D-10's one-move-per-UTC-month cap, accepted by the user as bounding the loss to two accounts per month on a sub-$5 subscription. **This is a recorded product decision, not a control this phase can strengthen without reopening D-10.** |
| A fabricated Apple JWS | Spoofing | The library's chain walk against the vendored Apple Root CA G3. Already proven for real in `tests/unit/test_app_store_notifications.py:252-271`. |
| A fabricated Play purchase token | Spoofing | `subscriptionsv2.get` returns 404/410 for an unknown token → `proof_rejected`. |
| The purchase token leaking into a log line or an error field | Information Disclosure | Phase 44 found and fixed exactly this leak (`AttributionConflict` was logging the token; it now logs the row's own primary key — `errors.py:288-291`). **The same hazard recurs here**: on the Google path `external_id` *is* the purchase token, so any `stage`, log field or exception message that carries `external_id` is a leak. `tests/unit/test_rejection_vocabulary.py` and the Phase 43 stage-name test are the existing enforcement. |
| Unbounded restore attempts driving unbounded Play API calls | Denial of Service | **Accepted, not mitigated.** No backend limiter exists (35 D-05) and the gateway contract is v2.1 (35 D-08). Record it as 41 D-20 / 42 D-16 / 43-06 did, under RESTORE-01. Narrower than the webhook cases: the caller must already hold a valid Firebase token for a linked account, and Apple costs no network call at all under D-04. |
| Timing or body differences distinguishing "no such subscription" from "not entitled" | Information Disclosure | D-11's one-class-per-outcome rule; `RestoreRefused`'s status and code declared on the base and nowhere below, exactly as `ClaimRefused` does (`errors.py:475-480`). |
| SQL injection through `provider` or `restore_proof` | Tampering | Not reachable — every statement is a SQLModel/SQLAlchemy construct with bound parameters. No `text()` is needed anywhere in this phase (see § Pattern 4). |

## Project Constraints (from CLAUDE.md / AGENTS.md)

`/home/init/native-speaker/CLAUDE.md` is a single `@AGENTS.md` include; the checked-in instruction
file is `/home/init/native-speaker/AGENTS.md`, and the repo carries its own
`/home/init/native-speaker/ns-api-gateway/AGENTS.md`. Directives extracted from both:

**Product-level (`native-speaker/AGENTS.md`):**
- First version, no users, will not attract many at first.
- The product is a sub-$5/month grammar-fixing AI chat. **Its value is not great enough to make
  stealing it attractive — do not over-engineer for that threat model.** This is the explicit
  authority for D-10's accepted loss and for not building attestation, fingerprinting or coalescing.
- **But do not skip normal security measures** because there are no users yet.
- **Keep specs short: programming this app should not consume many tokens.** A plan that adds seven
  files where four would do is in violation.
- The app runs in Kubernetes behind Envoy Gateway, which authenticates by JWT and rate-limits by IP,
  user and URL. This is why the deferred rate limits are a *record*, not a gap.

**Repo-level (`ns-api-gateway/AGENTS.md`):**
- **Docstrings — three lines maximum.** State what the entity does; nothing else. Do not describe
  what lives elsewhere, what the entity is not, or how the application works in general.
- **Comments — only where necessary.** One line each, explaining the lines below them. Never the
  design, the request lifecycle, or a rule enforced in another module. **Default to none.**
- **Package layout:** `services/` = business logic and transaction boundaries; `crud/` = database
  access; `schemas/` = Pydantic bodies and value types; `tables/` = SQLModel tables; `routers/` =
  `Depends()`-only handlers; `auth/` = external-SDK seams only.
- **A service is earned by complexity, not assumed by category.** CONTEXT's discretion section
  already argues restore earns one; the plan should carry that argument, not re-open it.
- **`Depends()` only binds the handler** — never construct a database class in a route body.
- **`commit()` and `rollback()` live in `services/`**, not `crud/`.
- **A fail-closed read may raise its own rejection**, so that rejection stays with the query in
  `crud/`.
- **Function shape:** delete a function that is only a step; keep one that states a rule or marks a
  boundary (a lock, a transaction, or a callable a library requires).
- **`errors.py` owns the client-visible response shape**; nothing about errors moves to `schemas/`.

**From the user's own working preferences (MEMORY.md, binding on prose this phase writes):**
- ASD-STE100 for all user-facing prose: short sentences, one idea each, no metaphors.
- Use the codebase's own terms — dependency, handler, service, crud, adapter, router, schema, table.
  Do not coin nouns.
- Fix root causes, never symptoms.
- `IS_WORKTREE` detection is unreliable in this submodule — **executors must be told it is false**,
  or tracking writes vanish.

## Sources

### Primary (HIGH confidence)
- This repository's source, read this session with `Read`: `src/nativespeaker/api/auth/app_store.py`,
  `auth/google_play.py`, `auth/store_notifications.py`, `services/subscriptions.py`, `services/auth.py`,
  `services/sync.py`, `crud/subscriptions.py`, `crud/grants.py`, `crud/purchases.py`,
  `routers/auth.py`, `routers/webhooks.py`, `schemas/auth.py`, `config.py`, `errors.py`,
  `app/dependencies.py`, `app/lifespan.py`, `tables/purchases.py`, `tables/grants.py`,
  `migrations/20260818_01_initial-release.sql`, `tests/unit/error_tree.py`,
  `tests/unit/test_auth_package_shape.py`, `tests/unit/test_docstring_bar.py`,
  `tests/unit/test_subscription_attribution.py`, `AGENTS.md`.
- Runtime inspection of the installed packages (`uv run python -c ...`) for versions, the
  `SignedDataVerifier` method set, the eight `VerificationStatus` members, the
  `JWSTransactionDecodedPayload` field types, and `ColumnOperators.is_not_distinct_from`.
- Live PostgreSQL 17.11 connection using this repo's `.env` credentials.
- `uv run pytest --collect-only -q` for the three suite baselines.
- `/home/init/native-speaker/specs/auth-refactor-phases/10-restore-subscription.md` and
  `SHARED-INVARIANTS.md`.
- `.planning/phases/45-post-auth-restore-subscription/45-CONTEXT.md`, `.planning/REQUIREMENTS.md`,
  `.planning/STATE.md`, `.planning/config.json`.

### Secondary (MEDIUM confidence)
- Context7 `/apple/app-store-server-library-python` — `verify_and_decode_signed_transaction`
  signature and the "API, notification, or device" wording; `JWSTransactionDecodedPayload` field
  table; `InAppOwnershipType`.
- Context7 `/websites/developers_google_android-publisher` — the `subscriptionsv2.get` endpoint,
  scope, and the `SubscriptionPurchaseV2` sample response.

### Tertiary (LOW confidence)
- Training knowledge for the `verifyReceipt` → StoreKit 2 JWS deprecation framing in § State of the
  Art (tagged A3 in the Assumptions Log). Nothing in the plan depends on it.

**A caution the planner should carry:** the Context7 autodocs for
`app-store-server-library-python` are **stale against the installed 3.0.0**. They list
`appAccountToken` as `Optional[UUID]` (the installed package declares `str | None`) and a six-member
`VerificationStatus` with names like `INVALID_SIGNATURE` and `INVALID_CERTIFICATE_CHAIN` that the
installed eight-member enum does not carry. Every Apple field type and status name in this document
comes from runtime inspection, not from the autodoc. **Any plan task that names an Apple enum member
must re-measure it rather than copy it from documentation.**

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — every version read from the installed environment; nothing new is added.
- Architecture: **HIGH** — every pattern is grounded in a quoted line of shipped source, and the two
  deferred foreign keys and the generated columns were read from the migration itself.
- Pitfalls: **HIGH** for 1, 3, 4, 5, 6, 7 and 8, each traced to a specific line. **MEDIUM** for
  Pitfall 2 — the deferred-FK semantics follow from the DDL and from PostgreSQL's documented
  `DEFERRABLE INITIALLY DEFERRED` behaviour, but this repository has no executed case proving the
  23503 arrives at commit. That is precisely why a `tests/schema` case for it is listed in Wave 0.
- Store wire behaviour: **MEDIUM** — both libraries are the vendors' own and both are already under
  test in this repo, but no request has ever reached a real store (Assumption A1).
- The iOS client's proof format: **LOW** — Assumption A2, and the one item that merits a user
  checkpoint before the request contract locks.

**Research date:** 2026-09-07
**Valid until:** 2026-10-07 (30 days). The two store APIs are stable; the volatile inputs are this
repo's own test-count baselines and the `test_auth_package_shape.py` literal, which change with the
next phase.
