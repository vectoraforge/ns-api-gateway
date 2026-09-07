# Phase 45: POST /auth/restore-subscription - Context

**Gathered:** 2026-09-07
**Status:** Ready for planning

<domain>
## Phase Boundary

One authenticated route, `POST /auth/restore-subscription`. The body names a store and carries
that store's artifact. The server verifies the artifact, resolves the subscription it names, and
attaches the paid entitlement to the caller's account through one of three server-chosen outcomes:
same-account (nothing to change), adoption of an unowned subscription (creating the canonical row
when none exists), or a move from another account, capped at one move per UTC calendar month.
Success returns the sync body.

**In scope:** the request model, the route, a restore service, the two proof checks built on the
store classes Phases 43 and 44 shipped, the grant write through the webhook's writer, the
conditional owner update, the cap, two new error codes, tests on the 43/44 model, and the
REQUIREMENTS.md amendments.

**Out of scope:** a transfer endpoint or flag, attestation of any kind, a Firebase read, an App
Store Server API client, rate limits and provider budgets, an audit row, an operation enum label,
any change to `SHARED-INVARIANTS.md` or the brief, and any change to the two webhook routes beyond
D-09.

</domain>

<decisions>
## Implementation Decisions

### The body and the surface gate

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

### The store checks

- **D-04: Apple is verified locally, never live.** The Apple proof is the StoreKit 2 signed
  transaction (`Transaction.jwsRepresentation`). The existing `SignedDataVerifier` on
  `app.state.app_store_notifications` verifies it with `verify_and_decode_signed_transaction`:
  signature and chain against the vendored root, bundle id, environment. No App Store Server API
  client, no new Apple key, no `Get All Subscription Statuses` call on adoption (44 D-13 stands).
  Accepted blind spot: a subscription this server has never heard of, refunded after the proof was
  signed, gets a grant until the next webhook. **FLAGGED CONFLICT** against brief steps 8 and 17
  and the rule "the current row's status is necessary but not sufficient".
  — **Reversibility:** reversible — adding the live call later is one class, one config block and
  one call before the transaction; nothing written depends on its absence.

- **D-05: Google's one call is both checks.** The Google proof is the purchase token. The existing
  `PlayDeveloperSubscriptions` class makes the one `purchases.subscriptionsv2.get` call, which is
  the proof check (package, product) and the live state at once. No second Play client. A gone
  token (404/410) is `proof_rejected`; a transport failure or absent credential is 503
  `verification_temporarily_unavailable`, not the webhook's 500 (the webhook wants a redelivery,
  the app wants a later retry). `package_name` comes from `GooglePlayConfig` (44 D-18).

- **D-06: Entitlement is decided by the local row where one exists, by the proof where none does.**
  Where a `core.subscriptions` row exists for `(provider, external_id)`, its `status` decides
  entitlement (`ENTITLED_STATUSES`: `active`, `grace_period`), and restore never updates that
  status from the proof — canonical state belongs to the webhooks. Where no row exists
  (adoption-with-creation), the row is created at the proof's own state and tier, and that state
  decides. A verified proof whose subscription is not entitled answers `restore_not_found` with
  nothing written. One rule for both providers, fail-closed toward the record.

### The write path

- **D-07: The webhook's writer writes the grant.** A successful restore calls
  `SubscriptionsDB.write_subscription_grant` as-is: the grant's `ends_at` is the paid period's end
  (grace window during grace), every held active grant of the destination is expired first, the new
  row gets its own usage row, and an active grant for this subscription with the same term and tier
  writes nothing (`replayed`), so a repeat restore never resets a counter. A free grant the
  destination holds is superseded exactly as a webhook supersedes it, so the brief's
  `restore_destination_already_entitled` has no trigger. **FLAGGED CONFLICT** against the brief's
  `ends_at IS NULL` adoption grant, its UPDATE reactivation of the same row, and "never mints a
  fresh monthly counter for the same paid entitlement".
  — **Reversibility:** costly — a second grant shape would have to be handled by the writer, the
  renewal path, `SyncService` and the tests that pin the term model (43 D-15).

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
  it. The owner is changed by restore alone. Amends 43 D-19's "owner change updates the grant" and
  43-03's "an owner is added, never cleared" (it is now also never replaced by ingestion).
  Touches `crud/subscriptions.py` and the 43/44 tests that pin the old rule.
  — **Reversibility:** reversible — one comparison in one crud method.

- **D-10: The subscription may move once per UTC calendar month.** `core.subscriptions.user_id`
  is the tie; `restore_bound_user_id` is not written and stays NULL. A move (owner is another
  account) writes `last_cross_account_transfer_month` as the first day of `evaluated_at`'s UTC
  month, expires the old owner's subscription grant in the same transaction (the old owner loses
  access at that moment), and inserts the destination's. A move is refused with
  `restore_transfer_rejected` when the stored month equals the current month; nothing is written.
  Adoption (owner NULL) and same-account restores do not count and do not write the month. The cap
  is per subscription, which the proof names, never per user. **FLAGGED CONFLICT** against the
  brief's lifetime binding ("never changed once set"), its `store_transaction_already_linked`
  result, and its DELETIONS line forbidding any read or write of
  `last_cross_account_transfer_month`.
  — **Reversibility:** one-way in principle — a published product behaviour once an app ships;
  cheap today because there are no users.

### Rejections and the response

- **D-11: Two new codes.** `ErrorCode` grows by `restore_not_found` (the proof verified, but no
  paid subscription stands behind it: not entitled, or the recorded purchase attribution differs
  from the carried token) and `restore_transfer_rejected` (the cap, D-10). Both are terminal 4xx
  with no `Retry-After`. Reused, never redefined: `operation_not_allowed` (D-01),
  `proof_rejected` through the existing `ProofRejected` leaf with a `stage` (chain, bundle,
  environment, gone token, package mismatch), `verification_temporarily_unavailable` (D-05),
  `internal_error` for an unmapped store product (`UnmappedStoreProduct`, an operator error as on
  the webhooks). The brief's `restore_store_state_unverified`, `restore_destination_anonymous`,
  `restore_destination_already_entitled`, `store_transaction_already_linked`,
  `restore_source_user_inactive`, `restore_subscription_grant_owner_mismatch`,
  `restore_branch_inconsistent` and `restore_temporarily_unavailable` have no trigger after D-03,
  D-04, D-07, D-08 and D-10 and are not added. One class per outcome, body and status identical
  across its arms.

- **D-12: The response is `SyncResponse`,** read after the commit by `SyncService.read_entitlement`,
  with `Cache-Control: no-store`, `identity_provider` the stored provider (42 D-12). The repeat,
  the adoption, the move and the race loser who finds the destination owning the row all return
  the same shape.

### Documentation deliverables

- **D-13: Amend RESTORE-01 and RESTORE-02 in `.planning/REQUIREMENTS.md`** with dated entries:
  D-02, D-03, D-04, D-07, D-08 and D-10 as flagged conflicts against `10-restore-subscription.md`
  by line; D-09 as a dated amendment under APPLEHOOK-01 and in `STATE.md` § Decisions; the Phase 40
  forward flag on the `restore_subscription` operation label answered (**no label is needed**:
  restore is not challenge-bearing and writes no audit row); the obligations already dead before
  this phase (route registry, foundation store-verification and vendor-proof interfaces, the audit
  row, the eleven rate-limit entries, the provider budgets, coalescing, the freshness bound, the
  attempt-identity retry). Update the header's conflict counts. Mark ROADMAP criteria 2, 3 and 4
  answered, criterion 3 as D-01/D-02 answers it.
- **D-14: `10-restore-subscription.md` and `SHARED-INVARIANTS.md` are NOT edited** (43 D-27).
  Divergences live in REQUIREMENTS.md.
- **D-15: Every comment this phase writes is ASD-STE100, inline where possible** (43 D-25),
  under `AGENTS.md` § "Comments and docstrings".

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `10-restore-subscription.md` alone will try to build all of these. **None exists.**

- **No route registry, no `Category`, no `RouteMetadata`, no named-verifier table** (Phase 37.1
  D-06/D-10). The route joins `routers/auth.py` under `get_linked_identity`;
  `tests/unit/test_app_wiring.py` gains `/auth/restore-subscription` in its narrowed-route lists.
- **No foundation store-verification or vendor-proof interface** (Phase 37.2 D-09). The two store
  classes exist beside their Protocols in `auth/app_store.py` and `auth/google_play.py`.
- **No rate limiting, no provider budgets, no coalescing, no proof fingerprints** (Phase 35 D-05).
  The Play call per restore attempt is bounded by nothing but the proof check before it; record the
  exposure as 41 D-20 and 42 D-16 did, closing with the v2.1 gateway contract.
- **No `audit.auth_events` row, no operation enum value, no audit result value** (37.1 D-01,
  38 D-03, 40 D-11). Log event names come from exception class names.
- **Outcomes are exception classes, never an enum** (Phase 37.3 D-12).
- **`IntegrityError` is caught by SQLSTATE 23505 only** (Phase 42-07).
- **Lock order:** grant rows ascending by id, then usage rows; no other tier ahead
  (SHARED-INVARIANTS § Locks, 43 D-16). D-08.
- **No network call while a lock is held or a transaction is open.** Both proof checks run in
  the service before the transaction opens, as 41 and 42 call Apple before theirs.
- **One captured instant per request** (`get_evaluated_at`).
- **`commit()` and `rollback()` live in `services/`** (AGENTS.md).
- **No success log line** (Phase 38 D-02); `RequestLoggingMiddleware` writes the one request line.
- **No challenge, no prepare mode, no attestation, no Firebase read on this route** (the brief's
  own deletions, and 41 D-08 / 42 D-05 for the Firebase read).
- **Product→tier maps live in each provider's class** (44 D-16); `external_id` is Apple's
  `originalTransactionId` and Google's purchase token (43 D-08, 44 D-10).
- **`store_purchase_tokens.identity_value` is the server-minted attribution token** per user per
  store; Apple's `appAccountToken` and Google's `obfuscatedExternalAccountId` resolve against it
  (43 D-16, 44 carried forward).
- **The purchase row is inserted once and never updated** (43 D-17/D-19): restore inserts it when
  missing, with a `uuid7()` `identity_value` when the transaction carries no token.

### Claude's Discretion

- **The service.** Restore is a transaction with three outcomes and two proof checks: earned as its
  own class (`services/restore.py` is the natural home) rather than a fourth completion on
  `AuthService`, which is shaped around challenges. Its dependency in `app/dependencies.py`
  follows `get_subscriptions_service`.
- **Apple's status from a bare transaction.** A signed transaction carries no `data.status`
  (that is the notification's). Derive it from the transaction alone: `revocationDate` set →
  `revoked`; `expiresDate` after `evaluated_at` → `active`; else `expired`. Grace and billing
  retry are not visible without the renewal-info JWS; do not ask the app for it this phase. This is
  the rule 43 D-13 used before 44 D-11 retired it for the webhook; record the choice.
- **How the Play class is called without the webhook's fields** (`event_type`,
  `notification_uuid`, `signed_at`), and how its `InternalError` on transport failure becomes the
  503 of D-05: a second entry point on the class, or a caught-and-mapped call. No second client.
- **The crud method that locks two users' grant rows in one ascending statement** (D-08), and
  where `AttributionConflict` maps (D-11 says `restore_not_found`).
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
  unowned subscription (exactly one grant, loser answers the sync body or the refusal), a move and
  a second move in the same month (refused, nothing written), and a restore interrupted at commit
  (neither the owner nor the grant changes).
- **Plan wave order.** D-09 edits Phase 43's crud and tests; it lands before or with the restore
  writer, never after.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding brief and its invariants
- `/home/init/native-speaker/specs/auth-refactor-phases/10-restore-subscription.md` — the phase
  brief. Read it for the step list and the mapping table, then read the decisions above for what
  this phase departs from and why. Not edited (D-14).
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — § "Locks and
  transactions", § "Grants and evaluation time", § "Fail-closed defaults", § "Errors" bind every
  line of this phase. Not edited (D-14).
- `.planning/REQUIREMENTS.md` § RESTORE — RESTORE-01/02 and their forward-flag notes (the deleted
  adapter seam, the deleted operation label). D-13 amends this block.

### Prior-phase decisions this phase builds on
- `.planning/phases/43-post-webhooks-app-store/43-CONTEXT.md` — the Apple class and verifier
  (D-07…D-11), the service and writer (D-12…D-19), the term model (D-15), no subscription lock
  (D-16), the unattributed case restore links later (D-17), the replay and race rules (D-20).
- `.planning/phases/44-post-webhooks-google-play-rtdn/44-CONTEXT.md` — the two Google classes
  behind one dependency, the second built for this phase (D-08); `external_id` is the purchase
  token (D-10); the status mapping (D-11); ADC and the httpx client (D-14/D-15); product maps in
  each class (D-16); `GooglePlayConfig` (D-18).
- `.planning/phases/42-post-auth-claim-registered-grant/42-CONTEXT.md` — the sync body as the
  response (D-12), the live two-connection race test (D-13), the Apple-exposure record (D-16).

### Conventions
- `AGENTS.md` (repo root) — package layout, when a service is earned, comment and docstring
  rules, `commit()` in `services/`.
- `migrations/20260818_01_initial-release.sql` — `core.subscriptions` (`user_id`,
  `restore_bound_user_id`, `last_cross_account_transfer_month`,
  `product_entitled_subscription_id`), `core.store_purchases`, `core.access_grants` and its four
  indexes, the two deferrable foreign keys.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auth/app_store.py` — `AppStoreNotifications` holds the `SignedDataVerifier`;
  `verify_and_decode_signed_transaction` is the Apple proof check (D-04). `_APPLE_STATUSES` is
  the notification's mapping, not usable for a bare transaction.
- `auth/google_play.py` — `PlayDeveloperSubscriptions.read` is the Google proof check and live
  state (D-05); `PlaySubscription` is the response model; `_status_for` the status rule.
- `crud/subscriptions.py` — `read_subscription`, `read_purchase`, `insert_purchase`,
  `write_subscription_grant`, `lock_grants` (one user; D-08 needs two), `ENTITLED_STATUSES`,
  `WriteOutcome`. `upsert_subscription` changes under D-09.
- `crud/purchases.py` — `resolve_user` maps an attribution token to a user, no lock.
- `crud/grants.py` — the lock statements and `ActivationOutcome`.
- `services/sync.py` — `read_entitlement` for the response (D-12).
- `errors.py` — `ProofRejected(stage=…)`, `Unavailable(stage=…)`, `UnmappedStoreProduct`,
  `AttributionConflict`, `ClaimRefused` as the model for a shared 403 base.
- `schemas/auth.py` — `GrantClaimRequest` as the model for the request body; `SyncResponse`.
- `tables/purchases.py` — `Subscription` maps every column D-08 and D-10 write.

### Established Patterns
- A route under `get_linked_identity`, a thin handler, a service that owns the transaction and
  the `commit()`, crud that writes rows and receives plain values.
- Provider calls before the transaction; the locked phase is database-only.
- Expire-then-insert under `ix_access_grants_one_active_per_user`; a 23505 is a lost race.
- The loser of a race re-reads and answers as the winner's state earns (42 D-10, 43 D-20).

### Integration Points
- `routers/auth.py` — the seventh auth route.
- `app/dependencies.py` — the restore service's accessor; the two store classes are already on
  `app.state`.
- `tests/unit/test_app_wiring.py` — the narrowed-route lists.
- `k8s/` — no change: `/auth` paths are not in any HTTPRoute today, as prior auth phases left
  them.

</code_context>

<specifics>
## Specific Ideas

- **Plain English.** The user asked for it by name mid-discussion. The questions that landed
  named no layer, no file and no column: "how does the server say no to a caller that is not one
  of the two apps".
- **Answer the question, then stop.** Twice the user pushed back on an explanation that went past
  the question ("Answer my question", "Stop confusing me"). The answer that worked was one
  sentence: it is forever only if we build it that way.
- **The user checks premises.** "Do I have a transfer cap?" and "the security implication is
  stealing the receipt, right?" were tests of the reasoning. Answer what is true, including that a
  rule is a product choice and not a technical limit.
- **Give the best option, keep one answer, one question at a time** — 43 and 44 notes still hold.
- **Use the codebase's own terms** and **ASD-STE100** for prose and comments (D-15).

</specifics>

<deferred>
## Deferred Ideas

- **Apple live status from the App Store Server API** (`Get All Subscription Statuses`) — declined
  again (D-04). Reopen if the refund blind spot ever costs more than it saves; it is one class,
  one key and one call before the transaction.
- **The renewal-info JWS as a second Apple proof field** — would make grace and billing retry
  visible on restore. Not this phase.
- **Dropping `restore_bound_user_id`** — unused under D-10; a migration edit while there are no
  users, if the column is judged noise.
- **Gateway rate limits on the auth surface, including the Play call per restore attempt** —
  the v2.1 gateway contract (Phase 35 D-05, 41 D-20).
- **`/auth` paths in the gateway HTTPRoutes** — absent today; a gateway concern, not this phase.
- **The Android and web claim branches** — as in Phases 41 and 42.
- **Phase 44.1, the feature-sliced restructure** — after this phase, as recorded in 44-CONTEXT.
- **One test asserting each Python enum's values equal its `core.*` type's labels** — still
  deferred.

### Reviewed Todos (not folded)

- `secret-manager-integration` (score 0.6) — declined. D-04 adds no Apple key, so this phase adds
  no secret; the todo's scope is unchanged.
- `message-ordering-is-unspecified` (score 0.2) — chats; matched on the word "phase". Unrelated.

</deferred>

---

*Phase: 45-post-auth-restore-subscription*
*Context gathered: 2026-09-07*
