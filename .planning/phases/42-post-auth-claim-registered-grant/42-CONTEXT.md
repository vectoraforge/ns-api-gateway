# Phase 42: POST /auth/claim-registered-grant - Context

**Gathered:** 2026-09-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship `POST /auth/claim-registered-grant`. It is the completion route for the challenge-bearing
operation `claim_registered_grant`, and the only code path that writes a `core.access_grants` row
with `source='registered_account_grant'`. Prepare is the existing `POST /auth/challenge`, which
already issues for this operation to a linked caller.

One successful claim has one of two destinations, chosen inside one locked transaction:

- **New grant.** The caller has no free-grant history and no active grant. The claim writes the
  registered grant on the `registered` tier (50 credits), its usage row, and
  `free_grant_consumed_at`.
- **Conversion.** The caller holds an active `anonymous_device_grant`. The claim expires that row
  and writes the registered grant, and the usage row moves across unchanged. One allowance
  changes tier. No second allowance is issued.

**The device gate is Apple DeviceCheck bit1, on a new grant only** (D-01, D-02). **Claimants are
registered identities only** — stored provider `google` or `apple` (D-05). **No Firebase read on
this route** (D-05). **No account table beyond `external_identities`** (D-06).

**Also in scope — a schema deletion** (D-07, D-08): `core.access_grants_anti_abuse`,
`core.provider_accounts` and `core.provider_account_gate_consumptions` leave the initial
migration, with everything that only they need, and Phase 41's writer stops writing its
anti-abuse row.

**Out of scope:** Android and web branches (another milestone, Phase 41 D-01); any HMAC or key;
`account_already_claimed`, `verification_required`, `held_grant_ends_at`; every rate-limit entry
and vendor budget; any `audit.auth_events` row; a `?challenge=true` mode; `claim_attempt_id`.

</domain>

<decisions>
## Implementation Decisions

### The device gate

- **D-01: A new registered grant burns DeviceCheck bit1.** Before the transaction, the service
  reads the device's bits with the one token in the body. If bit1 is set, the claim refuses with
  Phase 41's 403 `device_grant_exhausted` — same class, same copy, no device state in the body.
  If bit1 is clear, the service writes `bit1=True` and carries bit0 forward from the read, exactly
  as Phase 41 carries bit1 forward. Phase 41 D-06's rules apply as written, with bit1 in place of
  bit0: fail-closed write, load-bearing, retried through `tenacity`, no cache, every outcome after
  the claim consumes the challenge, a crash after the write burns the slot and is not compensated.
  — **Reversibility:** one-way — a set bit1 cannot be cleared by this system.

- **D-02: The conversion path makes no Apple call.** A caller who holds an active anonymous grant
  already paid one device slot (bit0 is the only way that grant can exist). Conversion issues no
  new allowance, so it spends no new slot. The device token in the body goes unused on this path.
  Consequence: one device can pay for two allowances (one anonymous, one registered-new) instead
  of one. Accepted. **FLAGGED CONFLICT** against `07-claim-registered-grant.md` steps 7–8 and 10,
  which gate every iOS claim.

- **D-03: The database decides before Apple is asked.** Order after the claim: read the stored
  identity row and the grant history → choose the destination (D-09) → if and only if the
  destination is a new grant: Apple read → Apple write → the activation transaction. D-02 forces
  this order; it is also Phase 41 D-03.

- **D-04: One device token, always required.** The body carries `challenge_id` and one DeviceCheck
  token. An absent or empty token is the framework's 422, as on the anonymous claim. Phase 41's
  fix bound the read and the write to one token; this route keeps that shape. **FLAGGED CONFLICT**
  against the brief's separate query and update tokens (step 7), as Phase 41 recorded for its route.

### Who claims

- **D-05: Registered identities only, from the stored row, with no Firebase read.** The route sits
  behind `get_linked_identity`. The service requires `identity.identity.provider` to be `google` or
  `apple`. An anonymous caller is refused with 403 `operation_not_allowed` through a new
  `ClaimRefused` leaf — the mirror of Phase 41's `ClaimantNotAnonymous`. `verification_required`
  is not added. The claim does not write the identity binding, so there is no drift to prevent,
  and the unique index (D-06) guards the stored value; a live read would add nothing to
  uniqueness. **FLAGGED CONFLICT** against brief step 2 (`verification_required`) and step 6 (the
  mandatory `getUser` confirmation). Inside the transaction the identity row is re-read by a plain
  read, as Phase 41 does; a row that is no longer `google`/`apple` is refused the same way.

- **D-06: Account uniqueness rests on what the schema already has.**
  `ix_external_identities_provider_account` — `UNIQUE (issuer, provider, provider_uid)`, no state
  predicate — allows one identity row per Google or Apple account, ever. `UNIQUE (user_id)` ties
  that row to one user. `ix_access_grants_one_free_grant_per_user_source` and
  `free_grant_consumed_at` allow that user one free grant. So one account cannot reach a second
  registered grant, and nothing new is needed. `core.provider_accounts` and
  `core.provider_account_gate_consumptions` are not written (they are deleted, D-07), and
  `account_already_claimed` is not added. **FLAGGED CONFLICT** against brief step 5 and the
  uniqueness hardening.

### The schema deletion

- **D-07: Delete `core.access_grants_anti_abuse`, `core.provider_accounts` and `core.provider_account_gate_consumptions` from `migrations/20260818_01_initial-release.sql`.**
  With them go everything only they need: the `core.gate_consumption_kind` enum,
  `ix_access_grants_anti_abuse_idp_account_hash`, `ix_gate_consumptions_grant_id`, the generated
  columns `anti_abuse_required_grant_id` and `active_registered_account_grant_id` on
  `core.access_grants` and their two deferred foreign keys, and `UNIQUE (id, source)` on
  `core.access_grants` if the planner confirms it exists only as that composite FK target.
  `core.native_claim_provider` stays — `external_identities.native_claim_platform` uses it, and
  that column remains the record of the device platform. In code: remove `AccessGrantAntiAbuse`
  from `tables/grants.py` and `tables/__init__.py`, remove the anti-abuse row from
  `crud/grants.py::activate_anonymous_device_grant` and the comments that describe the CHECK, and
  update the tests that read the table (`tests/unit/test_grant_sources.py`,
  `tests/e2e/test_claim_anonymous_grant.py`, `tests/e2e/conftest.py`,
  `tests/schema/test_claim_race.py`, `tests/schema/test_constraints.py`,
  `tests/schema/test_inventory.py`). The development database is rebuilt.
  **Why:** the anti-abuse row was a receipt, and every fact on it exists elsewhere — the grant's
  `source`, the identity row's `native_claim_platform`, the identity row's `provider_uid`. It
  decided nothing. The controls are Apple's bits, the unique index on `external_identities`, the
  two partial unique indexes on `access_grants`, and `free_grant_consumed_at`. The two provider
  tables were never written. **FLAGGED CONFLICT** against `06-schema-reference.md`
  § `core.access_grants_anti_abuse` and the two provider tables, brief steps 3 and 5, and any
  `SHARED-INVARIANTS.md` passage that names an anti-abuse row.
  — **Reversibility:** one-way — a migration edit; cheap today because there are no users.

- **D-08: No HMAC, no key, `provider_uid` stays raw.** A hash of `provider_uid` protects nothing
  while `provider_uid`, `subject` and `email` are stored in plain text beside it, and a key would
  become a single point of failure for identity matching. The web branch, when it exists, can add
  a table that records the IdP account of an anonymous claimant; nothing is built for it now.

### Destinations and the transaction

- **D-09: Destination selection, run in the preflight and again inside the locked transaction.**
  In this order:
  (a) an active `registered_account_grant` → **repeat**: nothing written, 200 with the current
  entitlement (Phase 41 D-09);
  (b) any other active grant that is not `anonymous_device_grant` (`subscription`, `manual`) →
  403 `operation_not_allowed` through `OtherActiveGrantHeld`, **no field** — `held_grant_ends_at`
  is not added;
  (c) an active `anonymous_device_grant` → **conversion** (D-10);
  (d) no free-grant row in history and no active grant → **new grant** (D-11);
  (e) free-grant history with no active free grant (a revoked anonymous grant) → 403
  `operation_not_allowed` through `FreeGrantAlreadyConsumed`.
  **Trap for the planner:** `free_grant_consumed_at` is already set on the conversion path, and
  `has_prior_free_grant` is true there too. Neither can be the blanket guard this route uses.
  The guard is the grant history read by source and status. **FLAGGED CONFLICT** against brief
  step 11.2(b) (`held_grant_ends_at`).

- **D-10: Conversion, in one transaction.** Lock the effective grants ascending by id, then their
  usage rows (the fixed global order; a user-row lock never comes first). Re-read the identity row
  by a plain read and re-check D-05. Then: set the anonymous row to `status='expired'`,
  `ends_at = evaluated_at`, `source` unchanged; **then** insert the registered grant — the update
  must precede the insert because `ix_access_grants_one_active_per_user` is not deferrable.
  Insert the new usage row with the old row's `monthly_period` and `monthly_used` copied exactly.
  Set `free_grant_consumed_at` where unset. An `IntegrityError` is caught without naming a
  constraint, the transaction rolls back, and the loser re-reads and answers 200.
  — **Reversibility:** one-way in principle — a published behaviour; cheap pre-launch.

- **D-11: New grant.** `tier_id='registered'`, `starts_at = evaluated_at`, `ends_at` NULL, a usage
  row with the current period and `monthly_used = 0`, `free_grant_consumed_at = evaluated_at`.
  The unique indexes are the arbiter of the race, as in Phase 41 D-13.

- **D-12: The response is `SyncResponse`,** `Cache-Control: no-store`, read after commit by
  `SyncService.read_entitlement`, `identity_provider` = the stored provider. The repeat and the
  race loser return the same body by construction.

- **D-13: A live two-connection race in `tests/schema`,** for both destinations: two challenges,
  two attempts on independent connections. New grant: exactly one grant row, one usage row,
  `free_grant_consumed_at` set once, both challenges consumed, loser 200. Conversion: the anonymous
  row expired exactly once, one active grant, the usage carried exactly once.

### Documentation deliverables

- **D-14: Amend REGGRANT-01 … REGGRANT-03 in `.planning/REQUIREMENTS.md`** with dated entries
  covering D-02, D-04, D-05, D-06, D-07/D-08 and D-09(b) as flagged conflicts against
  `07-claim-registered-grant.md` and `06-schema-reference.md`, and the obligations already dead
  before this phase (rate limits and budgets, the audit row, the mode signal, `claim_attempt_id`,
  the keyring, the two Firebase-confirmation points), as Phase 41 D-17 did. Amend the ANONGRANT
  entries and any STATE.md decision that describes Phase 41's anti-abuse row, so a later reader
  does not look for it. Update the header's conflict counts.
- **D-15: `07-claim-registered-grant.md` and `06-schema-reference.md` are NOT edited.** Divergences
  live in REQUIREMENTS.md.
- **D-16: Record the Apple exposure** for this route as Phase 41 D-20 did: an eligible registered
  account can make the backend call Apple as often as it can prepare challenges; the preflight
  refuses ineligible accounts before Apple; closes with the v2.1 gateway contract.

### Carried forward — decided earlier, binding here, do NOT rebuild

A planner reading `07-claim-registered-grant.md` alone will try to build all of these. **None exists.**

- **No rate limiting and no vendor budgets** (Phase 35 D-05). The Apple call is bounded only by `tenacity`.
- **No `audit.auth_events` row** (Phase 37.1 D-01, Phase 38 D-03). Internal result names survive
  only as structured-log event names from exception class names.
- **No `?challenge=true` mode and no `classify_mode_signal`** — prepare is `/auth/challenge`.
- **No route registry, no `BudgetGate`** (Phase 37.1 D-06, Phase 37 D-04).
- **No `claim_attempt_id`** (Phase 37.4 D-03). A failed commit leaves the challenge claimed and dead.
- **No HMAC keyring** (Phase 37.4 D-11, and D-08 here).
- **No Firebase read on any claim route** (Phase 41 D-08, D-05 here).
- **No success log line** (Phase 38 D-02). **No new HTTP status.** Every refusal here is a 403 already registered.
- **Consume on every post-claim outcome; nothing consumes before the claim** (Phase 40 D-14).
- **Lock order:** grant rows ascending, then usage rows; identity and user rows by plain re-read (Phase 41 D-13).

### Claude's Discretion

- **How `AuthService` grows the completion** — a `partial` post-claim seam as
  `complete_claim_anonymous_grant` uses; whether the preflight is shared with the anonymous claim
  or written beside it.
- **The `crud/grants.py` writer(s)** for the two destinations — one method with a branch or two
  methods; `activate_anonymous_device_grant` is the model.
- **The request model** — reuse `AnonymousGrantClaimRequest` under a shared name, or a sibling.
- **The `ClaimRefused` leaf name** for the anonymous-caller refusal.
- **Whether the schema deletion (D-07) is its own plan wave.** It edits Phase 41's writer and
  tests, so it lands before or with the new writer, never after.
- **How the migration edit is verified** — `tests/schema/test_inventory.py` and
  `tests/schema/test_constraints.py` guard the migration; both change.
- **Test placement and depth.**

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The binding specification (overrides phase briefs on conflict)

- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md` — § "Identity and
  ownership", § "The barrier", § "Fail-closed defaults", § "Locks and transactions" (wins over the
  brief's user-first lock), § "Grants and evaluation time". § "Rate limits" is dead. Any passage
  that names an anti-abuse row is diverged from by D-07 — flag, do not edit.
- `/home/init/native-speaker/specs/auth-refactor-phases/07-claim-registered-grant.md` — the brief,
  verbatim, **not edited** (D-15). Read "This phase adds", the completion flow (steps 1–12), the
  error-class list, and DELETIONS. **Its two tokens (D-04), its `verification_required` and
  `getUser` confirmation (D-05), its `provider_accounts` writes and `account_already_claimed`
  (D-06, D-07), its `idp_account_hash` (D-08), its device gate on conversion (D-02), its
  `held_grant_ends_at` (D-09) and every rate-limit, budget, audit, mode-signal and
  `claim_attempt_id` obligation are diverged from or dead** — read "Carried forward" first.

### The source specification

- `/home/init/native-speaker/specs/auth-refactor/03-free-credit-grants-and-anti-abuse.md` —
  § `POST /auth/claim-registered-grant`, § `claim_registered_grant`, § supersession conversion,
  § tier-sizing invariant (registered ≥ anonymous makes D-10's carry-over safe).
- `/home/init/native-speaker/specs/auth-refactor/06-schema-reference.md` — § `core.access_grants`
  (:991), § `core.access_grants_anti_abuse` (:1127, **deleted by D-07**), § `core.provider_accounts`
  and § `core.provider_account_gate_consumptions` (**deleted by D-07**), § `core.user_monthly_usage`
  (:1297), § `core.external_identities` (:579).
- `/home/init/native-speaker/specs/auth-refactor/00-overview-and-shared-contracts.md` § Common
  Completion Requirements (:418).
- `/home/init/native-speaker/specs/auth-refactor/07-quota-and-access-enforcement.md` § Effective
  Access Tier.

### Project planning

- `.planning/REQUIREMENTS.md` § REGGRANT (:318-322) — **this phase appends its dated amendments
  here** (D-14); § ANONGRANT (:267-316) — amended where it describes the anti-abuse row.
- `.planning/ROADMAP.md` Phase 42 (:601-611) — the four success criteria, all still met.
- `.planning/phases/41-post-auth-claim-anonymous-grant/41-CONTEXT.md` — **the closest precedent.**
  D-03, D-06, D-08, D-09, D-10, D-11, D-13, and its "Carried forward" list bind here.
- `.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md` — D-04 (the idempotent repeat),
  D-08 (`IntegrityError` without a constraint name), D-16 (`AuthService` grows), D-17 (narrow `try`).
- `.planning/STATE.md` § Decisions — the two Phase 41 entries on `FREE_GRANT_SOURCES` and on bit1
  carry-forward; the anti-abuse mention is amended by D-14.

### Repo conventions

- `ns-api-gateway/AGENTS.md` — § "Package layout", § "Function shape", § "Comments and docstrings".

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `auth/devicecheck.py::read_bits_with_retry` / `write_bits_with_retry(adapter, token, *, bit0, bit1)`
  — the read and the write D-01 uses; the write takes both bits, so bit0 is carried forward from
  the read as Phase 41 carries bit1.
- `services/auth.py::AuthService._complete` and `_claim_anonymous_grant` — the completion sequence
  and the post-claim seam (`partial`) the registered claim mirrors; `ANONYMOUS_TIER_ID` is the
  model for a `REGISTERED_TIER_ID = "registered"`.
- `crud/grants.py::activate_anonymous_device_grant` — the writer model: lock grants, lock usage,
  plain re-read of the identity row, build rows, one `flush` in the `try`, `IntegrityError` →
  `False`. `read_effective_grants`, `has_prior_free_grant`, `_prior_free_grant_statement`.
- `errors.py` — `ClaimRefused` (403 `operation_not_allowed`) and its leaves `ClaimantNotAnonymous`,
  `FreeGrantAlreadyConsumed`, `OtherActiveGrantHeld`; `DeviceGrantExhausted`, `ProofRejected`,
  `Unavailable`.
- `routers/auth.py::claim_anonymous_grant` — the handler shape: route-level `get_linked_identity`,
  `SyncResponse`, `no-store` on the injected `Response`, `sync_service.read_entitlement` after commit.
- `schemas/auth.py::AnonymousGrantClaimRequest`, `SyncResponse`, `Entitlement` (no `ends_at` field).
- `tables/grants.py` — `AccessGrant`, `AccessGrantSource`, `AccessGrantStatus`, `FREE_GRANT_SOURCES`
  (bound to the live index predicate — do not narrow), `UserMonthlyUsage`, `AccessTier`;
  `AccessGrantAntiAbuse` is removed (D-07).
- `tables/identities.py` — `ExternalIdentity.provider`, `provider_uid`, `free_grant_consumed_at`,
  `native_claim_platform`.
- `tests/e2e/conftest.py` — the scripted DeviceCheck fake and the Firebase fake;
  `tests/schema/test_claim_race.py` — the two-connection harness D-13 extends;
  `tests/schema/test_grant_locks.py` — the lock-order proof.
- `migrations/20260818_01_initial-release.sql` — the one migration; D-07 edits it.

### Established Patterns

- Layering per `AGENTS.md`; `commit()`/`rollback()` in `services/`.
- One captured instant per request (`evaluated_at`).
- No network call while a lock is held or a transaction is open.
- Consume on every post-claim outcome.
- Fail-closed reads raise in `crud/`.
- No nested `try`; a `try` holds only the statement that can raise.
- Structured-log labels from a closed set, never a token.

### Integration Points

- `routers/auth.py` (route; docstring count grows to six), `services/auth.py`, `crud/grants.py`,
  `errors.py` (one `ClaimRefused` leaf), `schemas/auth.py` (request model), `tables/grants.py` and
  `tables/__init__.py` (model removal), `migrations/20260818_01_initial-release.sql`,
  `tests/unit/test_app_wiring.py` (the new route is in neither literal set), `tests/e2e/`,
  `tests/schema/`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`.

### Naming Hazard

Three things are called "apple": `IdentityProvider.apple`, `PurchaseProvider.apple`, and Apple as
the DeviceCheck vendor. Keep them apart at every seam.

</code_context>

<specifics>
## Specific Ideas

- **ASD-STE100.** The developer asked for Simplified Technical English by name after a dense
  explanation. Short sentences. One idea in each. No metaphors. The same word for the same thing.
- **Architecture before implementation.** When asked how something works, the developer wants the
  role it plays and the flow it is part of — not columns, constraints or file names. The sentence
  that landed: "which countable thing paid for this free grant?"
- **Verify before asserting.** A recommendation in this discussion rested on a hole that
  `ix_external_identities_provider_account` had already closed. The developer found it by asking
  "why not just make `provider_uid` unique?" Check the schema before claiming a gap in it.
- **The developer follows a chain to its root.** The hash question led to the keyring, the keyring
  to the provider tables, the provider tables to the anti-abuse table, and the anti-abuse table to
  deletion. Answer the question asked; expect the next one.
- **Fewer copies of one fact** (Phase 40, Phase 41): D-07 and D-08 are that rule applied to a table.
- **Plain English, brevity, argue on merits** — Phase 40 and 41 notes still hold.

</specifics>

<deferred>
## Deferred Ideas

- **The web branch's account record** — an anonymous claimant's IdP account has no identity row of
  its own; when the web branch exists it needs a table (and a derivation) to record and refuse a
  repeat. Deleted with D-07; rebuilt there, on its own terms.
- **The Android branch and the web branch** — as in Phase 41.
- **Registered claimants on the anonymous route** — declined in Phase 41 D-08; this phase gives
  them their own route and does not reopen it.
- **`held_grant_ends_at`** — declined (D-09). Reopen if a client needs the date.
- **`verification_required`** — not added (D-05).
- **A real-device check of the Apple round trip** — when an iOS app exists.
- **Rate limiting the auth surface** — v2.1 gateway contract.
- **One test asserting each Python enum's values equal its `core.*` type's labels** — still deferred.

### Reviewed Todos (not folded)

- `message-ordering-is-unspecified` (score 0.6) — chats; unrelated.
- `secret-manager-integration` (score 0.2) — config; declined. D-08 adds no new secret this phase.

</deferred>

---

*Phase: 42-post-auth-claim-registered-grant*
*Context gathered: 2026-09-03*
